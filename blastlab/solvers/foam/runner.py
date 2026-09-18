"""Process lifecycle for a blastFoam case inside WSL.

Two invocations per run:
  1. `run_stage` - synchronous mesh/init pipeline (blockMesh,
     setRefinedFields); failures raise FoamStageError with the log tail
     attributed to the failing stage.
  2. `FoamRun` - the long-lived blastFoam solver: stdout is pumped by a
     daemon thread into a queue the backend drains between time-dir
     polls. Graceful stop = rewriting controlDict to `stopAt writeNow`
     (the case is runTimeModifiable), so blastFoam writes a final time
     directory and exits 0; the kill path escalates TERM -> KILL on the
     Linux pid recorded in .run.pid (never `wsl --terminate`, which
     would nuke the whole distro).

`.run.pid` holds two lines: the WSL-side solver pid (line 1, all the
signalling reads just that one) and the Windows-side pid of the Python
process that owns the run (line 2). The owner line is what lets
`env.reap_orphans` tell "someone else is still running this" from "the
process that started this is gone and nothing will ever stop it".
"""

import collections
import os
import queue
import re
import subprocess
import threading
import time

from . import env

#: solver stdout is teed here inside the case dir (N5-4)
LOG_NAME = 'log.blastFoam'


class FoamStageError(RuntimeError):
    def __init__(self, stage, log_tail):
        super().__init__(f"'{stage}' failed in WSL:\n{log_tail}")
        self.stage = stage
        self.log_tail = log_tail


def _tail(text, n=40):
    lines = (text or '').strip().splitlines()
    return '\n'.join(lines[-n:])


def run_stage(case_posix, cmds, timeout=600):
    """Run shell commands sequentially in the case dir (synchronous).
    Returns combined output; raises FoamStageError on nonzero exit."""
    script = f'cd {case_posix} && ' + ' && '.join(cmds)
    try:
        # stdin=DEVNULL everywhere: wsl.exe must never drain the CLI's
        # interactive stdin
        res = subprocess.run(env.wsl_argv(script), capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL,
                             creationflags=env.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise FoamStageError(' && '.join(cmds),
                             f'timed out after {timeout} s') from exc
    out = (res.stdout or '') + (res.stderr or '')
    if res.returncode != 0:
        raise FoamStageError(' && '.join(cmds), _tail(out))
    return out


def run_stage_stoppable(case_posix, cmd, timeout=600, should_stop=None,
                        poll=0.25):
    """`run_stage` for a single command, interruptible by the user.

    Same contract (returns combined output, raises FoamStageError on a
    nonzero exit), except that `should_stop()` is polled every `poll`
    seconds while the command runs. On a stop the wsl.exe relay is
    killed, which takes the WSL-side command with it - WSL ends the
    processes of a session once its relay exits - and
    StoppedBeforeStart is raised.

    `run_stage` keeps its own batch API for the callers that are not
    user-facing (the reconstruct sweeps)."""
    from ..hooks import StoppedBeforeStart
    script = f'cd {case_posix} && {cmd}'
    proc = subprocess.Popen(
        env.wsl_argv(script), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        creationflags=env.CREATE_NO_WINDOW)
    # drained on a thread: a mesh stage can outrun the ~64 KB pipe
    # buffer, and a blocked writer would never reach `poll() is not None`
    chunks = []

    def _pump():
        with proc.stdout as stream:
            for raw in stream:
                chunks.append(raw.decode('utf-8', 'replace'))

    threading.Thread(target=_pump, daemon=True).start()
    deadline = time.time() + timeout
    while proc.poll() is None:
        if should_stop is not None and should_stop():
            proc.kill()
            proc.wait(timeout=10)
            raise StoppedBeforeStart(f"stopped during '{cmd}'")
        if time.time() > deadline:
            proc.kill()
            proc.wait(timeout=10)
            raise FoamStageError(cmd, f'timed out after {timeout} s')
        time.sleep(poll)
    out = ''.join(chunks)
    if proc.returncode != 0:
        raise FoamStageError(cmd, _tail(out))
    return out


def _noop_log(_msg):
    pass


#: seconds to wait for a wsl.exe control/signal round trip
_WSL_EDIT_S = 60
#: mtime advance per controlDict rewrite - must exceed OpenFOAM's
#: fileModificationSkew (10 s in OpenFOAM-9's etc/controlDict)
SKEW_S = 40
_WSL_SIGNAL_S = 30


def _pid_file_cmd():
    """Shell writing `.run.pid`: solver pid on line 1, this Python
    process (the run's Windows-side owner) on line 2. Two plain `echo`s
    rather than one quoted printf - the parallel launch nests this
    inside `bash -c '...'`, where a quote of our own would break it."""
    return f'echo $$ > .run.pid && echo {os.getpid()} >> .run.pid'


def _start_keepalive(log):
    """A second wsl.exe session that does nothing but exist for the
    life of the run (W3, 2026-09-16).

    A 3D run died 11 minutes in with `Input/output error` on its own
    gauge file AND on OpenMPI's static help text: the WSL distribution
    had been terminated under the solver (`dmesg`: "Init has exited.
    Terminating distribution" -> ext4 unmounted), and every rank got EIO
    on its next file operation. WSL reaps a distribution it considers
    unused; the solver's own relay is one session, this is a second,
    independent one, so a hiccup on the relay side cannot leave the
    distribution with no session at all. It is a cheap extra hold, not
    a guarantee - the auto-resume in backend is what makes the failure
    survivable when it happens anyway.

    Runs WITHOUT the OpenFOAM bashrc (wsl_plain_argv): it must not care
    whether the install is healthy. Returns the Popen, or None when it
    could not start (logged; the run goes on without it)."""
    try:
        return subprocess.Popen(
            env.wsl_plain_argv('exec sleep infinity'),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=env.CREATE_NO_WINDOW)
    except OSError as exc:
        log(f'  [blastfoam] WSL keepalive session did not start ({exc})')
        return None


def rewrite_entry_text(text, key, value, within=None):
    """`key   value;` rewrite of a controlDict text: the first top-level
    `key ...;` line, or - `within` a function-object block as the writer
    lays it out (`    name` / `    {` / 8-space entries / `    }`) -
    that block's own `key` line. Unchanged text when the key is absent.
    Mirrors the WSL-side sed of rewrite_control_entry."""
    if isinstance(value, float):
        value = format(value, '.10g')
    if within is None:
        return re.sub(rf'^{re.escape(key)}(\s+)[^;]+;',
                      rf'{key}\g<1>{value};', text, count=1, flags=re.M)
    m = re.search(rf'^    {re.escape(within)}\n    \{{\n(.*?)^    \}}',
                  text, flags=re.M | re.S)
    if m is None:
        return text
    body = re.sub(rf'^(        {re.escape(key)}\s+)[^;]+;',
                  rf'\g<1>{value};', m.group(1), count=1, flags=re.M)
    return text[:m.start(1)] + body + text[m.end(1):]


def rewrite_control_entry(case_posix, case_unc, key, value, log=None,
                          within=None):
    """Rewrite one top-level `key   value;` line of the case's
    runTimeModifiable controlDict while the solver runs - or, with
    `within`, the `key` line inside that function-object block (the
    live-sample cadence). The edit runs INSIDE WSL (sed -i); a UNC
    rewrite is the fallback. Returns True when either path succeeded.

    OpenFOAM only notices a re-read when the file's mtime exceeds the
    one it last saw by more than `fileModificationSkew` (10 s default),
    so an edit within that window - a Stop or an arrival stop seconds
    after the solver started, an adaptive writeInterval right before a
    stop - was silently ignored and the run had to be killed. Every
    rewrite therefore pushes the mtime to max(now, current) + SKEW_S,
    monotonically, so each one is seen.

    A wedged WSL is exactly the moment a stop is being attempted, so a
    timeout degrades to False (the caller escalates) instead of raising
    out of the stop path."""
    log = log or _noop_log
    if isinstance(value, float):
        value = format(value, '.10g')
    cd = f'{case_posix}/system/controlDict'
    bump = (f'o=$(stat -c %Y {cd}); n=$(date +%s); '
            f'b=$(( o > n ? o : n )); touch -m -d @$(( b + {SKEW_S} )) {cd}')
    if within is None:
        expr = f"'s/^{key} .*$/{key}          {value};/'"
    else:
        expr = (f"'/^    {within}$/,/^    }}$/ "
                f"s/^\\(        {key} *\\).*$/\\1{value};/'")
    try:
        res = subprocess.run(
            env.wsl_argv(f'sed -i {expr} {cd} && {bump}'),
            capture_output=True, timeout=_WSL_EDIT_S,
            stdin=subprocess.DEVNULL,
            creationflags=env.CREATE_NO_WINDOW)
        if res.returncode == 0:
            return True
    except (subprocess.TimeoutExpired, OSError):
        log(f'  [blastfoam] WSL did not answer to the {key} rewrite '
            f'within {_WSL_EDIT_S} s - trying the UNC path')
    path = os.path.join(case_unc, 'system', 'controlDict')
    try:
        with open(path, encoding='ascii') as f:
            text = f.read()
        text = rewrite_entry_text(text, key, value, within)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='ascii', newline='\n') as f:
            f.write(text)
        old = os.stat(path).st_mtime
        os.replace(tmp, path)
        t = max(time.time(), old) + SKEW_S
        os.utime(path, (t, t))
        return True
    except OSError:
        log(f'  [blastfoam] could not rewrite {key} in the controlDict')
        return False    # caller decides (stop path escalates to kill)


class FoamRun:
    """A running blastFoam solver (serial or MPI) with streamed stdout.

    Parallel runs launch through `setsid`, making the recorded pid a
    session leader whose session contains mpirun and every rank (the
    ranks live in their OWN process groups, so group signals would miss
    them - verified empirically); all signalling is session-wide via
    `pkill -s`. Serial keeps the historical single-pid path."""

    def __init__(self, case_posix, case_unc, app='blastFoam',
                 n_procs=1, log=None):
        self.case_posix = case_posix
        self.case_unc = case_unc
        self.n_procs = max(1, int(n_procs))
        self.log = log or _noop_log
        self.lines = queue.Queue()
        self.log_tail = collections.deque(maxlen=80)
        self.stop_requested = False
        if self.n_procs > 1:
            # setsid -w: new session (so .run.pid = session id covering
            # mpirun + all ranks) but the launcher WAITS - without -w a
            # forked setsid parent exits, wsl.exe closes the stdout
            # pipe and the detached solver dies on SIGPIPE
            # Open MPI's default slot count is the physical-core
            # count: ranks beyond it need explicit opt-in or mpirun
            # refuses to launch ("not enough slots").
            # Since N21 `plan_run` clamps the rank count to the cores
            # the machine has, so this is mostly defence in depth - but
            # it stays: a resume reads n_procs back off disk, and the
            # slot count at launch may differ from the one the plan saw.
            flags = ''
            if self.n_procs > env.detect_slots():
                flags = ' --use-hwthread-cpus'
                if self.n_procs > env.detect_cores():
                    flags += ' --oversubscribe'
            inner = (f'{_pid_file_cmd()} && exec mpirun '
                     f'--allow-run-as-root{flags} -np {self.n_procs} '
                     f'{app} -parallel')
            script = f"cd {case_posix} && setsid -w bash -c '{inner}'"
        else:
            script = (f'cd {case_posix} && {_pid_file_cmd()} '
                      f'&& exec {app}')
        # N5-4: tee stdout to the case dir. Until this existed the log
        # lived only in `log_tail` (80 lines) and was gone the moment the
        # process ended - so a run that died left almost no context,
        # postmortem.load_run could rebuild a Result from the written
        # times but never see what the solver SAID, and a diagnostic
        # printed by a function object could only be caught live or not
        # at all. Opened before the pump thread starts; the pump is the
        # only writer and closes it when stdout ends, so nothing races
        # with release()/kill().
        self._logfh = None
        try:
            self._logfh = open(os.path.join(case_unc, LOG_NAME), 'a',
                               encoding='utf-8', newline='\n')
        except OSError as exc:      # a missing or read-only case dir is
            self.log(f'  [note] no solver log file: {exc}')  # not fatal
        # pinned before the solver starts, released by `release()` (the
        # run loop's finally) or `kill()` - see _start_keepalive
        self.keepalive = _start_keepalive(self.log)
        self.proc = subprocess.Popen(
            env.wsl_argv(script), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=env.CREATE_NO_WINDOW)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        try:
            with self.proc.stdout:
                for raw in self.proc.stdout:
                    line = raw.decode('utf-8', 'replace').rstrip('\r\n')
                    self.log_tail.append(line)
                    self.lines.put(line)
                    if self._logfh is not None:
                        try:
                            self._logfh.write(line + '\n')
                        except (OSError, ValueError):
                            self._logfh = None   # disk gone: keep going
        finally:
            fh, self._logfh = self._logfh, None
            if fh is not None:
                try:
                    fh.close()
                except OSError:
                    pass

    @property
    def running(self):
        return self.proc.poll() is None

    @property
    def returncode(self):
        return self.proc.returncode

    def drain(self, timeout=0.25):
        """Yield queued stdout lines; waits up to `timeout` for the
        first one, then drains without blocking."""
        try:
            yield self.lines.get(timeout=timeout)
        except queue.Empty:
            return
        while True:
            try:
                yield self.lines.get_nowait()
            except queue.Empty:
                return

    def request_write_now(self):
        """Graceful stop: `stopAt writeNow` via the runTimeModifiable
        controlDict."""
        if self.stop_requested:
            return True
        self.stop_requested = True
        return rewrite_control_entry(self.case_posix, self.case_unc,
                                     'stopAt', 'writeNow', self.log)

    def _signal(self, sig):
        """Send one signal into WSL. Returns False (and logs) when WSL
        does not answer in time - kill() then escalates instead of
        raising out of a caller's `finally`."""
        # line 1 only: line 2 is the Windows owner pid, and a bare
        # `cat` would splice it into the signal's argument list
        pid = f'$(head -n1 {self.case_posix}/.run.pid)'
        if self.n_procs > 1:
            # whole session: mpirun + every rank (ranks sit in their
            # own process groups, so a group kill would miss them)
            cmd = f'pkill -{sig} -s {pid} 2>/dev/null'
        else:
            cmd = f'kill -{sig} {pid} 2>/dev/null'
        try:
            subprocess.run(
                env.wsl_argv(cmd),
                capture_output=True, timeout=_WSL_SIGNAL_S,
                stdin=subprocess.DEVNULL,
                creationflags=env.CREATE_NO_WINDOW)
        except (subprocess.TimeoutExpired, OSError):
            self.log(f'  [blastfoam] WSL did not answer to SIG{sig} '
                     f'within {_WSL_SIGNAL_S} s')
            return False
        return True

    def suspend(self):
        """SIGSTOP the solver (GUI Interrupt: freeze compute too)."""
        if self.running:
            self._signal('STOP')

    def resume(self):
        if self.running:
            self._signal('CONT')

    def kill(self):
        """TERM then KILL the Linux-side solver, then the relay; the
        keepalive session goes with it whichever way this exits."""
        try:
            self._signal('CONT')    # a stopped process ignores TERM
            for sig, wait_s in (('TERM', 5.0), ('KILL', 2.0)):
                if not self.running:
                    return
                self._signal(sig)
                deadline = time.time() + wait_s
                while self.running and time.time() < deadline:
                    time.sleep(0.2)
            if self.running:
                try:
                    self.proc.kill()    # last resort: the wsl.exe relay
                except OSError:
                    self.log('  [blastfoam] could not kill the wsl.exe '
                             'relay process')
        finally:
            self.release()

    def release(self):
        """End the keepalive session (idempotent). The solver is not
        touched: this is for after it has exited or been killed."""
        ka, self.keepalive = self.keepalive, None
        if ka is None or ka.poll() is not None:
            return
        try:
            ka.kill()
            ka.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def tail(self, n=40):
        return '\n'.join(list(self.log_tail)[-n:])
