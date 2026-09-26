"""W3 (2026-09-16): a run whose WSL distribution is torn down under it.

A 13-rank 3D run died 11 minutes in. The log was not one solver error
but the filesystem going away for every process at once: blastFoam's
IOstream::check on its own gauge file, Open MPI unable to read its
STATIC help text (`help-mpi-api.txt: Input/output error`), PMIx losing
its dstore files - and `dmesg` on the WSL side said "Init has exited.
Terminating distribution" followed by the ext4 unmount. The written
time dirs up to the last flush were intact.

Three pieces, each covered here without WSL:

  1. `runloop.wsl_vanished` tells that signature from a genuine solver
     death, and `FoamRunLoop.run` raises `WslVanished` (a RuntimeError
     with the unchanged "blastFoam failed (exit N) - case kept at ..."
     message) only for it.
  2. `backend._resume_after_wsl` waits for WSL and hands the case to
     `resume_run`; it re-raises the ORIGINAL error, untouched, when the
     attempt budget is spent, WSL stays down, or the user stops.
  3. `runner.FoamRun` pins a second wsl.exe session (`sleep infinity`,
     no OpenFOAM bashrc) for the life of the run and releases it.

Run:  cd blastlab/tests && python test_foam_wsl_resume.py
"""
import io
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.solvers.foam import backend, runloop, runner     # noqa: E402
from blastlab.solvers.hooks import RunHooks                    # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


class Log(RunHooks):
    def __init__(self, stop=False):
        self.lines = []
        self._stop = stop

    def log(self, msg):
        self.lines.append(str(msg))

    def should_stop(self):
        return self._stop

    def text(self):
        return '\n'.join(self.lines)


# the tail of the run that motivated W3, verbatim
VANISHED_TAIL = """\
[0] file: /root/blastlab_runs/20260916-192303_3d_p22860-10/postProcessing/gauges/0.00053033187/rho at line 415.
[0]
[0]     From function virtual bool Foam::IOstream::check(const char*) const
[0]     in file db/IOstreams/IOstreams/IOstream.C at line 96.
[0]
FOAM parallel run exiting
[0]
--------------------------------------------------------------------------
Sorry!  You were supposed to get help about:
    mpi-abort
But I couldn't open the help file:
    /usr/share/openmpi/help-mpi-api.txt: Input/output error.  Sorry!
--------------------------------------------------------------------------
[cee-elsl-d:02257] PMIX ERROR: NO-PERMISSIONS in file ../../../../../../src/mca/common/dstore/dstore_base.c at line 238
"""

# a genuine solver death: deltaT collapse ending in decode()'s SIGFPE
NUMERIC_TAIL = """\
Time = 1.2345e-05s
deltaT = 7.5e-12
max(p): 4.2e+08, min(p): -1.1e+05
Floating point exception
--------------------------------------------------------------------------
mpirun noticed that process rank 3 with PID 0 on node cee exited on signal 8 (Floating point exception).
"""

# a genuine FOAM FATAL IO ERROR (the P1-5 restart mismatch)
MISMATCH_TAIL = """\
--> FOAM FATAL IO ERROR:
size 5138 is not equal to the given value of 5189
file: /root/blastlab_runs/x/6.8841367e-05/pMax
FOAM parallel run exiting
"""


def signature_checks():
    print('')
    print('1. the W3 signature vs genuine solver deaths')
    check('measured tail: WSL vanished', runloop.wsl_vanished(VANISHED_TAIL))
    check('SIGFPE tail: not WSL', not runloop.wsl_vanished(NUMERIC_TAIL))
    check('restart-mismatch tail: not WSL',
          not runloop.wsl_vanished(MISMATCH_TAIL))
    check('empty / None tail: not WSL',
          not runloop.wsl_vanished('') and not runloop.wsl_vanished(None))
    check('WslVanished is a RuntimeError (unaware callers unchanged)',
          issubclass(runloop.WslVanished, RuntimeError))


class FakeFoam:
    """A FoamRun that has already exited with `code` and said `tail`."""
    stop_requested = False

    def __init__(self, code, tail):
        self._code, self._tail = code, tail
        self.released = 0

    running = False
    returncode = property(lambda self: self._code)

    def drain(self, timeout=0.25):
        return iter(())

    def tail(self, n=40):
        return self._tail

    def kill(self):
        pass

    def release(self):
        self.released += 1


def run_loop_with(tail, code=1):
    """FoamRunLoop.run() against a solver that died saying `tail`.
    Returns the exception raised (or None)."""
    root = tempfile.mkdtemp(prefix='w3_')
    spec = types.SimpleNamespace(
        case_unc=root, case_posix='/root/blastlab_runs/w3', n_procs=1,
        decomposed=False, time_root=lambda: root,
        time_dirs=lambda name: os.path.join(root, name),
        write_interval=1e-5, live_steps=0, dim=3, end_time=1.0,
        n_cells=10, adaptive_write=False, start_dir='0',
        init_state=None)          # WriterSpec's default; runloop reads it
    orig = runloop.runner.FoamRun
    foam = FakeFoam(code, tail)
    runloop.runner.FoamRun = lambda *a, **k: foam
    try:
        loop = runloop.FoamRunLoop(spec, Log(), ('p',), {}, None, None,
                                   lambda n, d: None, lambda n, d, p: None)
        try:
            loop.run()
        except RuntimeError as exc:
            return exc, foam
        return None, foam
    finally:
        runloop.runner.FoamRun = orig


def runloop_checks():
    print('')
    print('1b. FoamRunLoop.run raises the typed error only for the signature')
    exc, foam = run_loop_with(VANISHED_TAIL)
    check('vanished tail -> WslVanished', isinstance(exc, runloop.WslVanished),
          repr(exc))
    check('message unchanged: "blastFoam failed (exit 1) - case kept at"',
          str(exc).startswith('blastFoam failed (exit 1) - case kept at '),
          str(exc)[:80])
    check('message carries the tail', 'Input/output error' in str(exc))
    check('keepalive released in the finally', foam.released == 1,
          str(foam.released))
    exc, _ = run_loop_with(NUMERIC_TAIL, code=136)
    check('SIGFPE tail -> plain RuntimeError',
          type(exc) is RuntimeError, repr(exc))
    exc, _ = run_loop_with(MISMATCH_TAIL)
    check('mismatch tail -> plain RuntimeError',
          type(exc) is RuntimeError, repr(exc))


def resume_checks():
    print('')
    print('2. backend._resume_after_wsl')
    spec = types.SimpleNamespace(case_posix='/root/blastlab_runs/w3',
                                 case_unc=r'\\wsl$\Ubuntu\root\blastlab_runs\w3')
    orig_check, orig_resume = backend.env.check_available, backend.resume_run
    calls = []
    sentinel = object()

    def fake_resume(case_dir, hooks=None, adaptive_write=True):
        calls.append((case_dir, adaptive_write))
        return sentinel

    backend.resume_run = fake_resume
    try:
        # WSL answers at once: resume, with the posix path and the flag
        backend.env.check_available = lambda force=False, timeout=90: (
            True, 'blastFoam ok')
        hooks = Log()
        err = runloop.WslVanished('blastFoam failed (exit 1) - case kept')
        out = backend._resume_after_wsl(spec, hooks, False, err)
        check('returns resume_run\'s Result', out is sentinel)
        check('resume_run got the posix case dir + adaptive_write',
              calls == [('/root/blastlab_runs/w3', False)], str(calls))
        check('counter on hooks = 1', hooks.wsl_resumes == 1)
        check('log says it is not a solver failure and which attempt',
              'not a solver failure' in hooks.text()
              and 'auto-resume 1 of 3' in hooks.text(), hooks.text())
        check('log says WSL is back', 'WSL is back' in hooks.text())

        # budget spent: the ORIGINAL exception object, resume not called
        calls.clear()
        hooks = Log()
        hooks.wsl_resumes = backend.WSL_RESUME_MAX
        try:
            backend._resume_after_wsl(spec, hooks, True, err)
            got = None
        except RuntimeError as exc:
            got = exc
        check('over budget: re-raises the same exception object', got is err)
        check('over budget: resume_run not called', calls == [])
        check('over budget: log says giving up + run browser',
              'giving up' in hooks.text() and 'run browser' in hooks.text(),
              hooks.text())

        # a test double whose __getattr__ answers everything: the counter
        # guard must not add 1 to a lambda
        class Any:
            def __init__(self):
                self.lines = []

            def log(self, m):
                self.lines.append(m)

            def __getattr__(self, _n):
                return lambda *a, **k: None
        out = backend._resume_after_wsl(spec, Any(), True, err)
        check('duck-typed hooks: still resumes', out is sentinel)

        # WSL stays down: original error, no resume (ceiling shrunk so
        # the test does not wait the real 5 minutes)
        calls.clear()
        backend.env.check_available = lambda force=False, timeout=90: (
            False, 'WSL did not answer')
        orig_wait = backend.WSL_RESUME_WAIT_S
        backend.WSL_RESUME_WAIT_S = 0
        hooks = Log()
        try:
            backend._resume_after_wsl(spec, hooks, True, err)
            got = None
        except RuntimeError as exc:
            got = exc
        finally:
            backend.WSL_RESUME_WAIT_S = orig_wait
        check('WSL down: re-raises the same exception object', got is err)
        check('WSL down: resume_run not called', calls == [])
        check('WSL down: log says it did not come back',
              'did not come back' in hooks.text(), hooks.text())
    finally:
        backend.env.check_available = orig_check
        backend.resume_run = orig_resume

    print('')
    print('2b. backend._wait_for_wsl')
    orig_check = backend.env.check_available
    try:
        backend.env.check_available = lambda force=False, timeout=90: (
            False, 'down')
        hooks = Log()
        check('deadline 0: returns False without hanging',
              backend._wait_for_wsl(hooks, wait_s=0) is False)
        check('deadline: log names the wait', 'did not come back' in hooks.text(),
              hooks.text())
        hooks = Log(stop=True)
        check('user stop: returns False',
              backend._wait_for_wsl(hooks, wait_s=60) is False)
        check('user stop: log says stopped', 'stopped while waiting' in hooks.text())
        seen = []

        def flaky(force=False, timeout=90):
            seen.append(force)
            return (len(seen) >= 2), 'ok' if len(seen) >= 2 else 'down'
        backend.env.check_available = flaky
        hooks = Log()
        check('comes back on the 2nd probe: True',
              backend._wait_for_wsl(hooks, wait_s=60) is True)
        check('every probe is force=True (bypasses the ok cache)',
              seen and all(seen), str(seen))
    finally:
        backend.env.check_available = orig_check


class FakePopen:
    """Records argv; behaves like an exited-or-running process."""
    made = []

    def __init__(self, argv, **kw):
        self.argv, self.kw = argv, kw
        self.stdout = io.BytesIO(b'')
        self.killed = 0
        self._rc = None
        FakePopen.made.append(self)

    def poll(self):
        return self._rc

    def kill(self):
        self.killed += 1
        self._rc = -9

    def wait(self, timeout=None):
        return self._rc


def keepalive_checks():
    print('')
    print('3. runner.FoamRun keepalive session')
    orig = runner.subprocess.Popen
    runner.subprocess.Popen = FakePopen
    FakePopen.made = []
    try:
        run = runner.FoamRun('/root/blastlab_runs/w3', r'\\x', n_procs=1)
        ka, solver = FakePopen.made[:2]
        check('two sessions: keepalive first, then the solver',
              len(FakePopen.made) == 2 and run.keepalive is ka
              and run.proc is solver, str(len(FakePopen.made)))
        check('keepalive is `sleep infinity` with no OpenFOAM bashrc',
              'exec sleep infinity' in ka.argv[-1]
              and runner.env.FOAM_BASHRC not in ka.argv[-1], str(ka.argv))
        check('keepalive is on the same distro as the solver',
              ka.argv[:3] == ['wsl.exe', '-d', runner.env.WSL_DISTRO],
              str(ka.argv[:3]))
        check('solver still sources the bashrc',
              runner.env.FOAM_BASHRC in solver.argv[-1])
        check('keepalive has no stdin/stdout pipes to fill',
              ka.kw.get('stdin') is runner.subprocess.DEVNULL
              and ka.kw.get('stdout') is runner.subprocess.DEVNULL)
        run.release()
        check('release kills the keepalive only',
              ka.killed == 1 and solver.killed == 0)
        run.release()
        check('release is idempotent', ka.killed == 1)
        # kill() on an already-exited solver still releases the keepalive
        FakePopen.made = []
        run = runner.FoamRun('/root/blastlab_runs/w3', r'\\x', n_procs=1)
        ka, solver = FakePopen.made[:2]
        solver._rc = 1
        run._signal = lambda sig: True      # no wsl.exe here
        run.kill()
        check('kill() releases the keepalive', ka.killed == 1)
    finally:
        runner.subprocess.Popen = orig

    # the keepalive not starting must not stop the run
    def boom(argv, **kw):
        if 'sleep infinity' in argv[-1]:
            raise OSError('no wsl.exe')
        return FakePopen(argv, **kw)
    runner.subprocess.Popen = boom
    FakePopen.made = []
    try:
        log = []
        run = runner.FoamRun('/root/blastlab_runs/w3', r'\\x', n_procs=1,
                             log=log.append)
        check('keepalive failure: solver still launched, logged',
              run.keepalive is None and len(FakePopen.made) == 1
              and any('keepalive' in m for m in log), str(log))
        run.release()
        check('release with no keepalive is a no-op', True)
    finally:
        runner.subprocess.Popen = orig


def wiring_checks():
    print('')
    print('4. every solve_*_foam catches WslVanished around loop.run()')
    src = open(os.path.join(os.path.dirname(backend.__file__),
                            'backend.py'), encoding='utf-8').read()
    n_run = src.count('stop_reason = loop.run()')
    n_catch = src.count('except WslVanished as exc:')
    check('three loop.run() sites, three catches',
          n_run == 3 and n_catch == 3, f'{n_run} / {n_catch}')


if __name__ == '__main__':
    signature_checks()
    runloop_checks()
    resume_checks()
    keepalive_checks()
    wiring_checks()
    print('')
    if FAILS:
        print(f'{len(FAILS)} FAILED: ' + ', '.join(FAILS))
        sys.exit(1)
    print('all W3 checks passed')
