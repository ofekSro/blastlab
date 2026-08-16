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
"""

import collections
import os
import queue
import re
import subprocess
import threading
import time

from . import env


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


class FoamRun:
    """A running blastFoam process with streamed stdout."""

    def __init__(self, case_posix, case_unc, app='blastFoam'):
        self.case_posix = case_posix
        self.case_unc = case_unc
        self.lines = queue.Queue()
        self.log_tail = collections.deque(maxlen=80)
        self.stop_requested = False
        script = (f'cd {case_posix} && echo $$ > .run.pid && exec {app}')
        self.proc = subprocess.Popen(
            env.wsl_argv(script), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=env.CREATE_NO_WINDOW)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        with self.proc.stdout:
            for raw in self.proc.stdout:
                line = raw.decode('utf-8', 'replace').rstrip('\r\n')
                self.log_tail.append(line)
                self.lines.put(line)

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
        controlDict. The edit runs INSIDE WSL (sed -i) so the inotify
        watch fires natively; a UNC rewrite is the fallback."""
        if self.stop_requested:
            return
        self.stop_requested = True
        res = subprocess.run(
            env.wsl_argv(
                "sed -i 's/^stopAt.*$/stopAt          writeNow;/' "
                f'{self.case_posix}/system/controlDict'),
            capture_output=True, timeout=60,
            stdin=subprocess.DEVNULL,
            creationflags=env.CREATE_NO_WINDOW)
        if res.returncode == 0:
            return
        path = os.path.join(self.case_unc, 'system', 'controlDict')
        try:
            with open(path, encoding='ascii') as f:
                text = f.read()
            text = re.sub(r'^stopAt(\s+)\w+;', r'stopAt\1writeNow;',
                          text, count=1, flags=re.M)
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='ascii', newline='\n') as f:
                f.write(text)
            os.replace(tmp, path)
        except OSError:
            pass    # caller's stop deadline will escalate to kill()

    def kill(self):
        """TERM then KILL the Linux-side solver, then the relay."""
        for sig, wait_s in (('TERM', 5.0), ('KILL', 2.0)):
            if not self.running:
                return
            subprocess.run(
                env.wsl_argv(
                    f'kill -{sig} $(cat {self.case_posix}/.run.pid) '
                    f'2>/dev/null'),
                capture_output=True, timeout=30,
                stdin=subprocess.DEVNULL,
                creationflags=env.CREATE_NO_WINDOW)
            deadline = time.time() + wait_s
            while self.running and time.time() < deadline:
                time.sleep(0.2)
        if self.running:
            self.proc.kill()

    def tail(self, n=40):
        return '\n'.join(list(self.log_tail)[-n:])
