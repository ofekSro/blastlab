"""WSL / blastFoam environment: discovery, availability caching and
Windows<->WSL path translation.

The availability check is a subprocess probe with three access styles:
  - status()               never blocks, never spawns (safe for the GUI
                           validation debounce);
  - ensure_check_started() kicks the probe on a daemon thread (GUI,
                           when the solver combo flips to blastfoam);
  - check_available()      blocking probe with cache (backend + CLI;
                           doubles as the WSL cold-start warm-up).
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

_lock = threading.Lock()
_state = 'unchecked'        # 'unchecked' | 'checking' | 'ok' | 'fail'
_detail = ''


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
    """(state, detail) without blocking or spawning anything."""
    with _lock:
        return _state, _detail


def check_available(force=False, timeout=90):
    """Blocking availability check with module-level cache.
    Returns (ok, detail)."""
    global _state, _detail
    with _lock:
        if _state in ('ok', 'fail') and not force:
            return _state == 'ok', _detail
        _state = 'checking'
    ok, detail = _probe(timeout)
    with _lock:
        _state, _detail = ('ok' if ok else 'fail'), detail
    return ok, detail


def ensure_check_started():
    """Idempotent: start the probe on a daemon thread if it never ran."""
    global _state
    with _lock:
        if _state != 'unchecked':
            return
        _state = 'checking'
    threading.Thread(target=_background_probe, daemon=True).start()


def _background_probe():
    global _state, _detail
    ok, detail = _probe(timeout=90)
    with _lock:
        _state, _detail = ('ok' if ok else 'fail'), detail


def _probe(timeout):
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
