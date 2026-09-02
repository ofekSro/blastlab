"""WSL / blastFoam environment: discovery, availability caching and
Windows<->WSL path translation.

The availability check is a subprocess probe with three access styles:
  - status()               never blocks (safe for the GUI validation
                           debounce); a failed state past the retry
                           cooldown re-kicks the background probe;
  - ensure_check_started() kicks the probe on a daemon thread (GUI,
                           when the solver combo flips to blastfoam);
  - check_available()      blocking probe with cache (backend + CLI;
                           doubles as the WSL cold-start warm-up).

A failed check is cached only for FAIL_RETRY_COOLDOWN_S rather than
pinned for the process lifetime, so a transient WSL outage (service
wedge, cold-start timeout) heals without restarting the app.
"""

import subprocess
import threading
import time

WSL_DISTRO  = 'Ubuntu'
FOAM_BASHRC = '/root/OpenFOAM/OpenFOAM-9/etc/bashrc'
RUNS_ROOT   = '/root/blastlab_runs'

#: tools the backend pipeline needs (checked after sourcing the bashrc)
NEEDED_TOOLS = ('blastFoam', 'blockMesh', 'setRefinedFields')

CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

#: auto-parallel engages only above this cell count: below it the
#: decompose/reconstruct overhead outweighs the rank speed-up (and the
#: small verification cases keep exercising the plain serial path)
AUTO_PARALLEL_MIN_CELLS = 200_000
MAX_AUTO_PROCS = 16

#: how long a failed availability check stays cached before the next
#: status()/check_available() call retries it
FAIL_RETRY_COOLDOWN_S = 20.0

_lock = threading.Lock()
_state = 'unchecked'        # 'unchecked' | 'checking' | 'ok' | 'fail'
_detail = ''
_last_fail = 0.0            # wall time of the last failed probe
_cores = None               # cached WSL `nproc` result (logical CPUs)
_slots = None               # cached physical-core count (MPI slots)


def unc(posix_path):
    r"""'/root/x/y' -> '\\wsl.localhost\Ubuntu\root\x\y'."""
    return '\\\\wsl.localhost\\' + WSL_DISTRO \
        + posix_path.replace('/', '\\')


def wsl_argv(script):
    """argv running `script` in WSL with the OpenFOAM env sourced."""
    return ['wsl.exe', '-d', WSL_DISTRO, '-e', 'bash', '-lc',
            f'source {FOAM_BASHRC} && {script}']


def new_case_dir(dim, stamp=None):
    """Fresh run-directory pair (posix, unc). Not created on disk yet -
    the writer creates it when it writes the case files."""
    stamp = stamp or time.strftime('%Y%m%d-%H%M%S')
    posix = f'{RUNS_ROOT}/{stamp}_{dim}d'
    return posix, unc(posix)


def status():
    """(state, detail) without blocking. A failed state past the retry
    cooldown re-kicks the background probe (daemon thread) and reports
    'checking', so the GUI heals on its own once WSL recovers."""
    global _state
    with _lock:
        st, dt = _state, _detail
        retry = (st == 'fail'
                 and time.time() - _last_fail >= FAIL_RETRY_COOLDOWN_S)
        if retry:
            _state = 'checking'
    if retry:
        threading.Thread(target=_background_probe, daemon=True).start()
        return 'checking', dt
    return st, dt


def detect_cores(timeout=30):
    """WSL-side logical core count (cached; 4 on any failure)."""
    global _cores
    if _cores is not None:
        return _cores
    try:
        res = subprocess.run(wsl_argv('nproc'), capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL,
                             creationflags=CREATE_NO_WINDOW)
        _cores = int(res.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError,
            subprocess.TimeoutExpired):
        _cores = 4
    return _cores


def detect_slots(timeout=30):
    """Physical-core count inside WSL - Open MPI's default slot count,
    i.e. the most ranks mpirun accepts without opt-in flags (cached;
    falls back to the logical count when lscpu is unavailable)."""
    global _slots
    if _slots is not None:
        return _slots
    script = ("lscpu -p=Core,Socket 2>/dev/null | grep -v '^#' "
              "| sort -u | wc -l")
    try:
        res = subprocess.run(wsl_argv(script), capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL,
                             creationflags=CREATE_NO_WINDOW)
        n = int(res.stdout.strip().splitlines()[-1])
        _slots = n if n > 0 else detect_cores()
    except (OSError, ValueError, IndexError,
            subprocess.TimeoutExpired):
        _slots = detect_cores()
    return _slots


def resolve_nprocs(n_req, n_cells):
    """Effective MPI rank count for a run. Explicit n_req >= 1 is
    honored as-is (the runner adds mpirun opt-in flags when it exceeds
    the slot count); auto (0) uses physical cores - 2 capped, and stays
    serial for small grids where decompose overhead dominates. Physical
    cores, not logical: CFD is memory-bandwidth-bound (SMT adds ~nothing)
    and Open MPI refuses ranks beyond the physical count by default."""
    if n_req >= 1:
        return int(n_req)
    if n_cells < AUTO_PARALLEL_MIN_CELLS:
        return 1
    return max(1, min(MAX_AUTO_PROCS, detect_slots() - 2))


def check_available(force=False, timeout=90):
    """Blocking availability check with module-level cache. A cached
    failure past the retry cooldown is re-probed instead of returned.
    Returns (ok, detail)."""
    global _state
    with _lock:
        if _state == 'ok' and not force:
            return True, _detail
        if _state == 'fail' and not force \
                and time.time() - _last_fail < FAIL_RETRY_COOLDOWN_S:
            return False, _detail
        _state = 'checking'
    ok, detail = _probe(timeout)
    _record(ok, detail)
    return ok, detail


def ensure_check_started():
    """Idempotent: start the probe on a daemon thread if it never ran."""
    global _state
    with _lock:
        if _state != 'unchecked':
            return
        _state = 'checking'
    threading.Thread(target=_background_probe, daemon=True).start()


def _record(ok, detail):
    global _state, _detail, _last_fail
    with _lock:
        _state, _detail = ('ok' if ok else 'fail'), detail
        if not ok:
            _last_fail = time.time()


def _background_probe():
    ok, detail = _probe(timeout=90)
    _record(ok, detail)


def _probe(timeout):
    """A cold WSL start can transiently time out
    (Wsl/Service/CreateInstance/0x800705b4), so failures are retried
    before being cached as final."""
    last = ''
    for attempt in range(3):
        if attempt:
            time.sleep(3.0)
        ok, detail = _probe_once(timeout)
        if ok:
            return True, detail
        last = detail
        if 'wsl.exe not found' in detail:
            break               # no point retrying a missing binary
    return False, last


def _probe_once(timeout):
    script = ' && '.join(f'command -v {t}' for t in NEEDED_TOOLS)
    try:
        res = subprocess.run(wsl_argv(script), capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL,
                             creationflags=CREATE_NO_WINDOW)
    except FileNotFoundError:
        return False, 'wsl.exe not found on PATH'
    except subprocess.TimeoutExpired:
        return False, f'WSL did not answer within {timeout} s'
    except OSError as e:
        return False, f'could not launch wsl.exe: {e}'
    if res.returncode != 0:
        tail = (res.stderr or res.stdout or '').strip().splitlines()
        detail = 'blastFoam tools not found in WSL'
        if tail:
            detail += f' ({tail[-1].strip()})'
        return False, detail
    return True, f'blastFoam ready in WSL ({WSL_DISTRO})'
