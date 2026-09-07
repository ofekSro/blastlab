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

It also owns the run-directory lifecycle: unique names for fresh runs
(`new_case_dir`), the liveness of the solver recorded in a run's
`.run.pid` (`run_is_alive`/`runs_alive`, one wsl.exe round trip for a
whole list) and the reaping of solvers whose Windows-side owner died
(`reap_orphans`).
"""

import collections
import itertools
import os
import subprocess
import threading
import time
from dataclasses import dataclass

from ...core.constants import (BYTES_PER_CELL, CELLS_PER_RANK,
                               FOAM_CELLS_REFUSE, FOAM_CELLS_WARN,
                               RAM_GB_PER_RANK, RAM_REFUSE_FRACTION,
                               RAM_WARN_FRACTION)

WSL_DISTRO  = 'Ubuntu'
FOAM_BASHRC = '/root/OpenFOAM/OpenFOAM-9/etc/bashrc'
RUNS_ROOT   = '/root/blastlab_runs'

#: tools the backend pipeline needs (checked after sourcing the bashrc)
NEEDED_TOOLS = ('blastFoam', 'blockMesh', 'setRefinedFields', 'topoSet',
                'subsetMesh', 'refineMesh', 'postProcess')

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
_ram_gb = None              # cached WSL VM MemTotal in GiB (N17/T48)


def unc(posix_path):
    r"""'/root/x/y' -> '\\wsl.localhost\Ubuntu\root\x\y'."""
    return '\\\\wsl.localhost\\' + WSL_DISTRO \
        + posix_path.replace('/', '\\')


def case_paths(case_dir):
    """(posix, unc) for a run/case dir given as a WSL UNC path, a posix
    path, or a bare run name under RUNS_ROOT."""
    d = str(case_dir).rstrip('/\\')
    if d.startswith('\\\\'):
        tail = d.split('\\' + WSL_DISTRO + '\\', 1)
        if len(tail) != 2:
            raise ValueError(f'not a WSL UNC path: {case_dir}')
        posix = '/' + tail[1].replace('\\', '/')
    elif d.startswith('/'):
        posix = d
    else:
        posix = f'{RUNS_ROOT}/{d}'
    return posix, unc(posix)


def wsl_argv(script):
    """argv running `script` in WSL with the OpenFOAM env sourced."""
    return ['wsl.exe', '-d', WSL_DISTRO, '-e', 'bash', '-lc',
            f'source {FOAM_BASHRC} && {script}']


def wsl_plain_argv(script):
    """argv running `script` in WSL WITHOUT sourcing the OpenFOAM env.

    For the run-directory utilities (pid liveness, signals, rm): they
    must keep working when the blastFoam install itself is broken -
    sourcing a missing bashrc would fail the `&&` chain before the
    script ever ran."""
    return ['wsl.exe', '-d', WSL_DISTRO, '-e', 'bash', '-lc', script]


#: per-process run counter: makes two runs launched by the SAME process
#: within one wall-second distinct (next() on a count is atomic)
_dir_seq = itertools.count()


def new_case_dir(dim, stamp=None):
    """Fresh run-directory pair (posix, unc). Not created on disk yet -
    the writer creates it (exist_ok=False) when it writes the case.

    The name carries the launching process's pid and a per-process
    counter on top of the 1-second timestamp, so two runs started in the
    same second - parallel test processes, GUI + CLI, or back-to-back
    chain stages - can never share a directory. They used to: the second
    run rewrote the first one's controlDict and 0/ fields underneath it
    and both fought over the same `.run.pid`, so a stop signal could hit
    the wrong solver."""
    stamp = stamp or time.strftime('%Y%m%d-%H%M%S')
    posix = (f'{RUNS_ROOT}/{stamp}_{dim}d'
             f'_p{os.getpid()}-{next(_dir_seq):02d}')
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


def detect_ram_gb(timeout=30):
    """Total RAM of the WSL VM in GiB (cached; None when unavailable).

    The VM - not the Windows host - is what the solver runs in, and WSL
    hands it about half the host's RAM unless the user's .wslconfig says
    otherwise. None means "unknown": callers fall back to the fixed cell
    caps rather than guessing (N17/T48)."""
    global _ram_gb
    if _ram_gb is not None:
        return _ram_gb or None
    try:
        res = subprocess.run(wsl_argv('free -g'), capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL,
                             creationflags=CREATE_NO_WINDOW)
        _ram_gb = parse_free_gb(res.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        _ram_gb = 0
    return _ram_gb or None


def parse_free_gb(text):
    """`free -g` stdout -> total GiB (0 when the line is not there).

    Split out so the parse can be tested without WSL: the header row
    differs between distros, so the Mem: row is matched by name."""
    for line in (text or '').splitlines():
        parts = line.split()
        if parts and parts[0].rstrip(':').lower() == 'mem':
            try:
                return int(parts[1])
            except (IndexError, ValueError):
                return 0
    return 0


def hardware(probe=False):
    """dict(cores, logical, ram_gb) or None - CACHED VALUES ONLY.

    validate_case calls this on every keystroke, so it must never touch
    WSL: without `probe` it returns what earlier probes cached (or the
    numbers a previous session persisted, see `prime_hardware`), and
    None when nothing is known yet."""
    if probe:
        detect_cores()
        detect_slots()
        detect_ram_gb()
    if _slots is None and _cores is None and not _ram_gb:
        return None
    return dict(cores=_slots or _cores, logical=_cores,
                ram_gb=_ram_gb or None)


def prime_hardware(cores=None, ram_gb=None):
    """Seed the caches from persisted settings so the GUI can show real
    numbers before the first WSL round trip finishes. A live probe
    overwrites them."""
    global _slots, _ram_gb
    if _slots is None and cores:
        _slots = int(cores)
    if _ram_gb is None and ram_gb:
        _ram_gb = int(ram_gb)


def forget_hardware():
    """Drop the cached probe (the GUI Re-detect button, and tests)."""
    global _cores, _slots, _ram_gb
    _cores = _slots = _ram_gb = None


@dataclass(frozen=True)
class RunPlan:
    """What the hardware allows for one run: how many MPI ranks to ask
    for, and how many cells the machine can actually hold."""
    ranks: int
    cell_cap_warn: int
    cell_cap_refuse: int
    reason: str
    ram_gb: int = None
    cores: int = None

    @property
    def from_memory(self):
        """True when the caps came from measured VM RAM rather than the
        fixed FOAM_CELLS_* fallbacks."""
        return self.ram_gb is not None


def plan_run(n_req, n_cells, cores=None, ram_gb=None, dim=3, amr=0,
             headroom=1):
    """Pure planner: (requested ranks, cells, hardware) -> RunPlan.

    No I/O and no globals, so the decision table can be pinned in tests
    and the same rules serve the GUI, validate_case and the CLI. Rules,
    in order:

      * an explicit n_req >= 1 is honoured as the user asked;
      * 1D and dynamic-AMR runs are serial (AMR until T42);
      * a grid under AUTO_PARALLEL_MIN_CELLS stays serial - decompose
        and reconstruct cost more than the ranks save;
      * otherwise as many ranks as the cores (minus headroom), the
        cells-per-rank floor and the RAM-per-rank budget all allow.

    The cell caps come from measured VM RAM (BYTES_PER_CELL) when it is
    known and from the fixed FOAM_CELLS_* constants when it is not -
    those stay the no-WSL default and are never removed."""
    cores = int(cores or 0)
    ram = int(ram_gb) if ram_gb else None
    if ram:
        refuse = int(RAM_REFUSE_FRACTION * ram * 2 ** 30 / BYTES_PER_CELL)
        warn = int(RAM_WARN_FRACTION * ram * 2 ** 30 / BYTES_PER_CELL)
    else:
        refuse, warn = FOAM_CELLS_REFUSE, FOAM_CELLS_WARN

    def plan(ranks, reason):
        return RunPlan(max(1, int(ranks)), warn, refuse, reason,
                       ram_gb=ram, cores=cores or None)

    if n_req and int(n_req) >= 1:
        return plan(int(n_req), 'requested: %d MPI ranks' % int(n_req))
    if dim == 1:
        return plan(1, 'serial: 1D runs are a single wedge')
    # dynamic AMR runs in parallel since T42 (N16-b) - the ingest reads
    # processor*/ directly, so no reconstruction is needed
    if n_cells < AUTO_PARALLEL_MIN_CELLS:
        return plan(1, '1 rank: %s cells is below the %s-cell parallel '
                       'floor' % (format(int(n_cells), ','),
                                  format(AUTO_PARALLEL_MIN_CELLS, ',')))
    limits = [(MAX_AUTO_PROCS, 'the %d-rank cap' % MAX_AUTO_PROCS)]
    if cores:
        limits.append((cores - int(headroom),
                       '%d physical cores - %d headroom'
                       % (cores, int(headroom))))
    limits.append((int(n_cells) // CELLS_PER_RANK,
                   '%s cells at %s/rank'
                   % (format(int(n_cells), ','),
                      format(CELLS_PER_RANK, ','))))
    if ram:
        limits.append((ram // RAM_GB_PER_RANK,
                       '%d GB at %d GB/rank' % (ram, RAM_GB_PER_RANK)))
    ranks, why = min(limits, key=lambda kv: kv[0])
    if ranks < 1:
        return plan(1, '1 rank: %s leaves no room for more' % why)
    return plan(ranks, 'auto: %d MPI ranks (%s)' % (ranks, why))


def mpi_headroom(default=1):
    """Cores kept free for the rest of the machine (settings.json
    `mpi_headroom`). The old hard-coded -2 was never justified."""
    try:
        from ...gui import settings
        return max(0, int(settings.load().get('mpi_headroom', default)))
    except Exception:
        return default


def resolve_nprocs(n_req, n_cells, dim=3, amr=0, headroom=None):
    """Effective MPI rank count - a thin wrapper over the pure
    `plan_run` that supplies the probed hardware. Explicit n_req >= 1 is
    honored as-is (the runner adds mpirun opt-in flags when it exceeds
    the slot count)."""
    if headroom is None:
        headroom = mpi_headroom()
    return plan_run(n_req, n_cells, cores=detect_slots(),
                    ram_gb=detect_ram_gb(), dim=dim, amr=amr,
                    headroom=headroom).ranks


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


# ── run directories: liveness and orphan reaping ────────────────────────────

#: One run's `.run.pid`: the WSL-side solver pid (a session leader for
#: parallel runs, the solver itself for serial), the Windows-side owner
#: pid - the Python process that launched it - and whether the solver is
#: still running. `owner` is None for dirs written before the owner line
#: existed; `alive` is None when WSL could not be asked.
RunPid = collections.namedtuple('RunPid', 'dir pid owner alive')

#: Windows process-liveness constants (see _win_pid_alive)
_SYNCHRONIZE = 0x00100000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_ACCESS_DENIED = 5
_WAIT_OBJECT_0 = 0

_WSL_UTIL_S = 30


def run_dirs():
    """Posix paths of the run directories currently under RUNS_ROOT."""
    root = unc(RUNS_ROOT)
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    return [f'{RUNS_ROOT}/{n}' for n in names
            if os.path.isdir(os.path.join(root, n))]


def _int_or_none(text):
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


# ── run-dir hygiene (N8) ─────────────────────────────────────────────────────

_INFO_S = 120


def _info_script(dirs):
    quoted = ' '.join(f"'{d}'" for d in dirs)
    return (f'for d in {quoted}; do '
            'b=$(du -sb "$d" 2>/dev/null | cut -f1); '
            'm=$(stat -c %Y "$d" 2>/dev/null); '
            'echo "INFO|$d|$b|$m"; done')


def _parse_info(stdout, dirs):
    """Info-script output -> {dir: dict(bytes, mtime)} (None where the
    script said nothing / could not stat). Pure."""
    out = {d: dict(bytes=None, mtime=None) for d in dirs}
    for line in (stdout or '').splitlines():
        parts = line.strip().split('|')
        if len(parts) != 4 or parts[0] != 'INFO' or parts[1] not in out:
            continue
        out[parts[1]] = dict(bytes=_int_or_none(parts[2]),
                             mtime=_int_or_none(parts[3]))
    return out


def run_info(case_dirs=None, timeout=_INFO_S):
    """{posix_dir: dict(bytes, mtime)} for the run dirs in ONE wsl round
    trip (`du -sb` + `stat`); {} when WSL cannot be reached."""
    dirs = list(run_dirs() if case_dirs is None
                else [str(d).rstrip('/') for d in case_dirs])
    if not dirs:
        return {}
    try:
        res = subprocess.run(wsl_plain_argv(_info_script(dirs)),
                             capture_output=True, text=True,
                             timeout=timeout, stdin=subprocess.DEVNULL,
                             creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    return _parse_info(res.stdout, dirs)


def delete_runs(case_dirs, timeout=300):
    """rm -rf the given run dirs inside WSL. True when the command ran."""
    dirs = [str(d).rstrip('/') for d in case_dirs]
    if not dirs:
        return True
    try:
        res = subprocess.run(
            wsl_plain_argv('rm -rf ' + ' '.join(f"'{d}'" for d in dirs)),
            capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return res.returncode == 0


def cleanup_policy(records, now, max_bytes=None, max_age_s=None,
                   keep_recent=3):
    """Which run dirs an automatic sweep may delete. Pure.

    `records`: [dict(dir, bytes, mtime, alive)]. Never a run whose solver
    is alive or whose state is unknown (alive None), never one whose
    size/mtime could not be read, never the `keep_recent` most recently
    touched runs. Of the rest: everything older than `max_age_s`, then -
    oldest first - until the total of ALL runs fits under `max_bytes`.
    Returns the victims' dirs (oldest first)."""
    recs = [r for r in records if r.get('bytes') is not None
            and r.get('mtime') is not None]
    recs.sort(key=lambda r: r['mtime'])           # oldest first
    protected = {r['dir'] for r in recs[len(recs) - keep_recent:]}         if keep_recent > 0 else set()
    total = sum(int(r['bytes'] or 0) for r in records
                if r.get('bytes') is not None)
    victims = []
    for r in recs:
        if r['dir'] in protected or r.get('alive') is not False:
            continue
        too_old = max_age_s is not None and now - r['mtime'] > max_age_s
        too_big = max_bytes is not None and total > max_bytes
        if too_old or too_big:
            victims.append(r['dir'])
            total -= int(r['bytes'])
    return victims


def auto_cleanup(settings=None, log=None, now=None):
    """Sweep the runs root per the GUI settings (opt-out
    `auto_cleanup=False`). Returns (n_deleted, bytes_deleted). One log
    line when something was removed; silent otherwise."""
    from ...gui import settings as gui_settings
    cfg = dict(gui_settings.DEFAULTS)
    cfg.update(settings or {})
    if not cfg.get('auto_cleanup', True):
        return 0, 0
    dirs = run_dirs()
    if not dirs:
        return 0, 0
    info = run_info(dirs)
    if not info:
        return 0, 0
    alive = runs_alive(dirs)
    records = [dict(dir=d, bytes=info.get(d, {}).get('bytes'),
                    mtime=info.get(d, {}).get('mtime'), alive=alive.get(d))
               for d in dirs]
    victims = cleanup_policy(
        records, now if now is not None else time.time(),
        max_bytes=float(cfg.get('cleanup_max_gb', 20)) * 1024 ** 3,
        max_age_s=float(cfg.get('cleanup_max_age_days', 14)) * 86400.0,
        keep_recent=int(cfg.get('cleanup_keep_recent', 3)))
    if not victims:
        return 0, 0
    freed = sum(int(info[d]['bytes'] or 0) for d in victims)
    if not delete_runs(victims):
        if log:
            log('  [blastfoam] run-dir cleanup: WSL did not delete '
                f'{len(victims)} old run(s)')
        return 0, 0
    if log:
        log(f'  [blastfoam] run-dir cleanup: removed {len(victims)} old '
            f'run(s), {freed / 1024 ** 3:.1f} GB '
            f'({len(dirs) - len(victims)} kept)')
    return len(victims), freed


def start_auto_cleanup(settings=None, log=None):
    """Run auto_cleanup on a daemon thread (GUI startup: WSL round trips
    must never block the window)."""
    import threading

    def work():
        try:
            auto_cleanup(settings, log)
        except Exception as exc:              # never kill the GUI for this
            if log:
                log(f'  [blastfoam] run-dir cleanup skipped: {exc}')

    th = threading.Thread(target=work, daemon=True,
                          name='blastlab-run-cleanup')
    th.start()
    return th


def _scan_script(dirs):
    quoted = ' '.join(f"'{d}'" for d in dirs)
    return (f'for d in {quoted}; do '
            'f="$d/.run.pid"; '
            'p=$(sed -n 1p "$f" 2>/dev/null); '
            'w=$(sed -n 2p "$f" 2>/dev/null); '
            'a=0; if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then a=1; fi; '
            'echo "RUN|$d|$p|$w|$a"; '
            'done')


def _parse_scan(stdout, dirs, alive_default=None):
    """Scan output -> {dir: RunPid}. Dirs the script said nothing about
    keep `alive_default` (None = 'could not tell'). Pure: the no-WSL
    tests drive this directly."""
    out = {d: RunPid(d, None, None, alive_default) for d in dirs}
    for line in (stdout or '').splitlines():
        parts = line.strip().split('|')
        if len(parts) != 5 or parts[0] != 'RUN' or parts[1] not in out:
            continue
        _, d, pid, owner, alive = parts
        out[d] = RunPid(d, _int_or_none(pid), _int_or_none(owner),
                        alive == '1')
    return out


def scan_runs(case_dirs=None, timeout=_WSL_UTIL_S):
    """{posix_dir: RunPid} for `case_dirs` (default: every run dir).

    ONE wsl.exe round trip for the whole list - a per-dir probe would
    pay a process spawn each. When WSL cannot be reached every record
    comes back with `alive=None` ('unknown'), never a bare False: the
    callers guard destructive work with this and must not read a failed
    probe as 'nothing is running'."""
    dirs = list(run_dirs() if case_dirs is None
                else [str(d).rstrip('/') for d in case_dirs])
    if not dirs:
        return {}
    try:
        res = subprocess.run(wsl_plain_argv(_scan_script(dirs)),
                             capture_output=True, text=True,
                             timeout=timeout, stdin=subprocess.DEVNULL,
                             creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return _parse_scan('', dirs)
    return _parse_scan(res.stdout, dirs)


def runs_alive(case_dirs=None, timeout=_WSL_UTIL_S):
    """{posix_dir: True | False | None} - is each run's solver still
    running? None means WSL could not be asked."""
    return {d: r.alive
            for d, r in scan_runs(case_dirs, timeout=timeout).items()}


def run_is_alive(case_dir, timeout=_WSL_UTIL_S):
    """True/False for one run dir, or None when WSL did not answer."""
    d = str(case_dir).rstrip('/')
    return runs_alive([d], timeout=timeout).get(d)


def _win_pid_alive(pid):
    """True when a Windows process with `pid` exists.

    Deliberately NOT os.kill(pid, 0): on Windows os.kill TERMINATES the
    target whatever the signal. Uses OpenProcess + a zero-timeout wait
    and errs towards 'alive' (access denied, no ctypes, odd errors), so
    a live owner is never mistaken for a dead one and reaping stays
    conservative."""
    if not pid or int(pid) <= 0:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL,
                                    wintypes.DWORD)
        k32.WaitForSingleObject.restype = wintypes.DWORD
        k32.WaitForSingleObject.argtypes = (wintypes.HANDLE,
                                            wintypes.DWORD)
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        h = k32.OpenProcess(
            _SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION,
            False, int(pid))
        if not h:
            # "access denied" means it exists and simply isn't ours
            return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
        try:
            # the process object signals once the process has exited
            return k32.WaitForSingleObject(h, 0) != _WAIT_OBJECT_0
        finally:
            k32.CloseHandle(h)
    except (AttributeError, OSError, ValueError):
        return True             # cannot tell -> never reap


def _is_orphan(rec):
    """A solver still running in WSL whose Windows-side owner is gone."""
    return bool(rec.alive and rec.owner and not _win_pid_alive(rec.owner))


def _signal_script(pids, sig):
    """Each pid gets both a direct `kill` (serial runs record the solver
    itself) and a session-wide `pkill -s` (parallel runs record the
    setsid session leader covering mpirun and every rank); whichever
    form does not apply simply matches nothing."""
    return '; '.join(
        f'kill -{sig} {p} 2>/dev/null; pkill -{sig} -s {p} 2>/dev/null'
        for p in pids) + '; true'


def _signal_pids(pids, sig, timeout=_WSL_UTIL_S):
    """Send one signal to a set of recorded run pids (one wsl call)."""
    if not pids:
        return True
    script = _signal_script(pids, sig)
    try:
        subprocess.run(wsl_plain_argv(script), capture_output=True,
                       timeout=timeout, stdin=subprocess.DEVNULL,
                       creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True


def reap_orphans(case_dirs=None, log=None, grace_s=5.0,
                 timeout=_WSL_UTIL_S):
    """TERM (then KILL) every run whose solver is alive in WSL but whose
    Windows-side owner process is gone.

    Without this, a Python process that dies hard leaves blastFoam
    running to `endTime` - hours of CPU for a big 3D - with nothing left
    to stop it. Conservative by construction: a run is reaped only when
    its `.run.pid` records BOTH pids and the owner is provably gone, so
    runs owned by another live window (or written before the owner line
    existed) are never touched. Returns the reaped RunPid records."""
    log = log or (lambda _msg: None)
    recs = scan_runs(case_dirs, timeout=timeout)
    orphans = [r for r in recs.values() if _is_orphan(r)]
    if not orphans:
        return []
    for r in orphans:
        log(f"  [blastfoam] reaping orphaned solver in "
            f"{r.dir.rsplit('/', 1)[-1]} (pid {r.pid}; owner process "
            f"{r.owner} is gone)")
    _signal_pids([r.pid for r in orphans], 'TERM', timeout=timeout)
    time.sleep(grace_s)
    left = scan_runs([r.dir for r in orphans], timeout=timeout)
    hard = [r.pid for r in orphans
            if left.get(r.dir) is not None and left[r.dir].alive]
    if hard:
        _signal_pids(hard, 'KILL', timeout=timeout)
    return orphans
