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
                               FOAM_VM_GB_ASSUMED,
                               RAM_GB_PER_RANK, RAM_REFUSE_FRACTION,
                               RAM_WARN_FRACTION)
from ...core.hardware import (CACHED, MEASURED, UNKNOWN, cache_is_valid,
                              detect_host_ram_gb, host,
                              machine_fingerprint, parse_meminfo_kb,
                              prime_host)

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

#: where each cached number came from (N21). MEASURED is the only state
#: that suppresses a re-probe: a value primed from settings is shown
#: immediately but still verified, so a `.wslconfig` edit is noticed.
#: Before N21 any non-None cache short-circuited the probe, which meant
#: a primed session NEVER measured anything.
_cores_src = UNKNOWN
_slots_src = UNKNOWN
_ram_src = UNKNOWN

#: one probe attempt per field per session: a failure must not turn every
#: later call into another 30 s timeout
_cores_tried = False
_slots_tried = False
_ram_tried = False


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


def _wsl_line(script, timeout):
    """Last stdout line of `script` run in WSL, or None on any failure."""
    try:
        res = subprocess.run(wsl_argv(script), capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL,
                             creationflags=CREATE_NO_WINDOW)
        return res.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None


def detect_cores(timeout=30, default=4):
    """WSL-side logical core count (cached).

    Returns `default` when it cannot be measured, but does NOT cache the
    guess: `_cores` stays None and `_cores_src` stays UNKNOWN, so nothing
    downstream reports a fabricated number as if it had been probed."""
    global _cores, _cores_src, _cores_tried
    if _cores_src == MEASURED:
        return _cores
    if _cores_tried:
        return _cores if _cores is not None else default
    _cores_tried = True
    out = _wsl_line('nproc', timeout)
    try:
        _cores, _cores_src = int(out.strip().splitlines()[-1]), MEASURED
    except (AttributeError, ValueError, IndexError):
        return _cores if _cores is not None else default
    return _cores


def detect_slots(timeout=30):
    """Physical-core count inside WSL - Open MPI's default slot count,
    i.e. the most ranks mpirun accepts without opt-in flags (cached;
    falls back to the logical count when lscpu is unavailable)."""
    global _slots, _slots_src, _slots_tried
    if _slots_src == MEASURED:
        return _slots
    if _slots_tried:
        return _slots if _slots is not None else detect_cores()
    _slots_tried = True
    script = ("lscpu -p=Core,Socket 2>/dev/null | grep -v '^#' "
              "| sort -u | wc -l")
    out = _wsl_line(script, timeout)
    try:
        n = int(out.strip().splitlines()[-1])
    except (AttributeError, ValueError, IndexError):
        n = 0
    if n > 0:
        _slots, _slots_src = n, MEASURED
        return _slots
    # lscpu said nothing usable: the logical count is the honest
    # fallback, and it carries its own source
    fallback = detect_cores()
    if _cores_src == MEASURED:
        _slots, _slots_src = fallback, MEASURED
        return _slots
    return _slots if _slots is not None else fallback


def detect_ram_gb(timeout=30):
    """Total RAM of the WSL VM in GiB (cached; None when unavailable).

    The VM - not the Windows host - is what the solver runs in, and WSL
    hands it about half the host's RAM unless the user's .wslconfig says
    otherwise. None means "unknown", and since N21 that makes the caps
    CONSERVATIVE rather than permissive.

    Reads /proc/meminfo rather than `free -g`: the latter truncates to
    whole GiB, so a sub-GiB VM was indistinguishable from a failure."""
    global _ram_gb, _ram_src, _ram_tried
    if _ram_src == MEASURED:
        return _ram_gb or None
    if _ram_tried:
        return _ram_gb or None
    _ram_tried = True
    out = _wsl_line('cat /proc/meminfo', timeout)
    gb = parse_meminfo_gb(out)
    if gb is None:                      # older/odd distro: try `free -g`
        out = _wsl_line('free -g', timeout)
        gb = parse_free_gb(out) or None
    if gb is None:
        return _ram_gb or None
    _ram_gb, _ram_src = gb, MEASURED
    return _ram_gb or None


def parse_meminfo_gb(text):
    """/proc/meminfo stdout -> total GiB, or None when unreadable.

    Rounds rather than truncating - a 7.7 GiB VM is much better described
    as 8 than as 7 - but never rounds a non-empty reading down to 0."""
    kb = parse_meminfo_kb(text)
    if not kb:
        return None
    return max(1, int(round(kb * 1024 / 2 ** 30)))


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
    """dict(cores, logical, ram_gb, cores_source, ram_source) or None -
    CACHED VALUES ONLY.

    validate_case calls this on every keystroke, so it must never touch
    WSL: without `probe` it returns what earlier probes cached (or the
    numbers a previous session persisted, see `prime_hardware`), and
    None when nothing is known yet.

    The `*_source` fields say whether each number was MEASURED this
    session, restored from settings (CACHED) or is UNKNOWN. They govern
    what gets persisted and what the user is told - never whether the
    value is used, so a value poked straight into the module globals
    (the tests do this) still plans exactly as before."""
    if probe:
        detect_cores()
        detect_slots()
        detect_ram_gb()
    if _slots is None and _cores is None and not _ram_gb:
        return None
    return dict(cores=_slots or _cores, logical=_cores,
                ram_gb=_ram_gb or None,
                cores_source=(_slots_src if _slots is not None
                              else _cores_src),
                ram_source=_ram_src)


def prime_hardware(cores=None, ram_gb=None, source=CACHED):
    """Seed the caches from persisted settings so the GUI can show real
    numbers before the first WSL round trip finishes.

    The seeded values are CACHED, not MEASURED, so the live probe still
    runs and overwrites them - that is what makes a `.wslconfig` change
    visible without clicking Re-detect."""
    global _slots, _ram_gb, _slots_src, _ram_src
    if _slots is None and cores:
        _slots, _slots_src = int(cores), source
    if _ram_gb is None and ram_gb:
        _ram_gb, _ram_src = int(ram_gb), source


def forget_hardware():
    """Drop the cached probe (the GUI Re-detect button, and tests)."""
    global _cores, _slots, _ram_gb, _cores_src, _slots_src, _ram_src
    global _cores_tried, _slots_tried, _ram_tried
    _cores = _slots = _ram_gb = None
    _cores_src = _slots_src = _ram_src = UNKNOWN
    _cores_tried = _slots_tried = _ram_tried = False


def prime_from_settings(st=None, now=None):
    """Seed the host + WSL caches from the persisted settings.

    The one implementation the GUI, the CLI and scripts share. Without
    it a non-GUI caller sizes every case against FOAM_VM_GB_ASSUMED (4
    GB) no matter what machine it is on: the probe result is
    process-local, and until now only gui/app.py persisted and restored
    it. A 62 GiB VM was being told it had 4.

    `st` is an already-loaded settings dict when the caller has one;
    None loads it here. Never raises. Gap-fills only - a value already
    known (live or primed) is left alone - and what it seeds stays
    CACHED, so the live probe still runs and a .wslconfig edit is still
    noticed.

    Deliberately NOT called at import time: the cap tests forget and
    prime their own hardware in setup, and an import-time prime would
    fight them. Entry points call it explicitly.

    Returns True when the VM numbers were accepted (this machine, inside
    the TTL), False otherwise.
    """
    try:
        if st is None:
            from ...core import settings as _settings
            st = _settings.load()
        # Unconditional and FIRST: machine_fingerprint hashes the host
        # RAM out of this same cache, so the fingerprint check below is
        # only meaningful once the host has been primed.
        prime_host(ram_gb=st.get('hw_host_ram_gb'))
        if not cache_is_valid(st.get('hw_fingerprint'), st.get('hw_stamp'),
                              machine_fingerprint(WSL_DISTRO),
                              time.time() if now is None else now):
            return False
        prime_hardware(cores=st.get('hw_cores'), ram_gb=st.get('hw_ram_gb'))
        return True
    except Exception:
        return False


def persist_hardware(hw):
    """Save ONLY what was measured this session.

    A failed probe must not overwrite a good measurement with
    hw_ram_gb=0 and a fabricated core count - a plausible lie is worse
    than a gap. Returns True when something was written.
    """
    import datetime
    try:
        upd = {}
        if hw.get('cores_source') == MEASURED and hw.get('cores'):
            upd['hw_cores'] = int(hw['cores'])
        if hw.get('ram_source') == MEASURED and hw.get('ram_gb'):
            upd['hw_ram_gb'] = int(hw['ram_gb'])
        if not upd:
            return False
        upd['hw_host_ram_gb'] = int(host().get('ram_gb') or 0)
        upd['hw_fingerprint'] = machine_fingerprint(WSL_DISTRO)
        upd['hw_stamp'] = datetime.datetime.now().isoformat(
            timespec='seconds')
        from ...core import settings as _settings
        _settings.update(**upd)
        # Verify rather than assume: `update` drops `save`'s result, so a
        # write that never landed is indistinguishable from one that did -
        # and losing the measurement silently sends the next headless run
        # back to the assumed 4 GB VM.
        back = _settings.load()
        return all(back.get(k) == v for k, v in upd.items())
    except Exception:
        return False


def probe_and_persist(timeout=30):
    """Blocking WSL probe + host RAM, saved for the next session.

    For an entry point that is about to launch a solver in that VM
    anyway and has already paid the cold-start cost. Returns the
    hardware() dict, or None."""
    try:
        hw = hardware(probe=True) or {}
        detect_host_ram_gb()
        persist_hardware(hw)
        return hw or None
    except Exception:
        return None


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
    ram_source: str = UNKNOWN
    cores_source: str = UNKNOWN
    requested: int = 0          # what the case asked for (0 = auto)
    clamped_from: int = None    # the ask, when it had to be reduced

    @property
    def from_memory(self):
        """True when the caps came from the VM's real RAM rather than
        the conservative assumption."""
        return self.ram_gb is not None

    @property
    def clamped(self):
        """True when an explicit rank request was cut to what fits."""
        return self.clamped_from is not None


def rank_ceiling(cores, ram_gb, headroom=1):
    """(max ranks this machine can actually take, why) - pure.

    HARD limits only: cores and RAM. Deliberately NOT the cells-per-rank
    floor or MAX_AUTO_PROCS, which are efficiency heuristics - someone
    who types a rank count may ignore efficiency, but not physics.

    (None, '') when nothing is known, so an explicit request is honoured
    rather than clamped against a guess: the app stays usable with WSL
    down."""
    limits = []
    if cores:
        limits.append((max(1, int(cores) - int(headroom)),
                       '%d physical cores - %d headroom'
                       % (int(cores), int(headroom))))
    if ram_gb:
        limits.append((max(1, int(ram_gb) // RAM_GB_PER_RANK),
                       '%d GB at %d GB/rank'
                       % (int(ram_gb), RAM_GB_PER_RANK)))
    if not limits:
        return None, ''
    return min(limits, key=lambda kv: kv[0])


def _source_of(value, given):
    """Honesty label for a planner argument: what the caller said, or
    MEASURED/UNKNOWN inferred from whether there is a value at all."""
    if given:
        return given
    return UNKNOWN if not value else MEASURED


def plan_run(n_req, n_cells, cores=None, ram_gb=None, dim=3, amr=0,
             headroom=1, ram_source=None, cores_source=None,
             max_ranks=0):
    """Pure planner: (requested ranks, cells, hardware) -> RunPlan.

    No I/O and no globals, so the decision table can be pinned in tests
    and the same rules serve the GUI, validate_case and the CLI. Rules,
    in order:

      * an explicit n_req >= 1 is honoured up to `rank_ceiling` - what
        the machine physically has - and clamped past it (N21);
      * a grid under AUTO_PARALLEL_MIN_CELLS stays serial - decompose
        and reconstruct cost more than the ranks save;
      * otherwise as many ranks as the cores (minus headroom), the
        cells-per-rank floor and the RAM-per-rank budget all allow.

    The cell caps always come from a VM size at BYTES_PER_CELL: the
    measured one when it is known, and FOAM_VM_GB_ASSUMED when it is not
    (N21). Unknown hardware therefore TIGHTENS the caps - it used to
    loosen them to the fixed FOAM_CELLS_* constants, which now serve as
    a ceiling so a very large VM cannot propose a run whose wall time and
    disk cost are unreasonable whatever its RAM."""
    cores = int(cores or 0)
    ram = int(ram_gb) if ram_gb else None
    sized = ram or FOAM_VM_GB_ASSUMED
    refuse = min(int(RAM_REFUSE_FRACTION * sized * 2 ** 30 / BYTES_PER_CELL),
                 FOAM_CELLS_REFUSE)
    warn = min(int(RAM_WARN_FRACTION * sized * 2 ** 30 / BYTES_PER_CELL),
               FOAM_CELLS_WARN)

    ram_src = _source_of(ram, ram_source)
    cores_src = _source_of(cores, cores_source)

    def plan(ranks, reason, requested=0, clamped_from=None):
        return RunPlan(max(1, int(ranks)), warn, refuse, reason,
                       ram_gb=ram, cores=cores or None,
                       ram_source=ram_src, cores_source=cores_src,
                       requested=int(requested or 0),
                       clamped_from=clamped_from)

    if n_req and int(n_req) >= 1:
        # N21: an explicit request is a CEILING, not a command. n_procs
        # is serialized in the case file, so a case saved on a 20-core
        # box used to launch 16 ranks on a 4-core laptop (mpirun was
        # even handed --oversubscribe to make it possible) and imply
        # 32 GB of VM that machine did not have.
        n = int(n_req)
        ceiling, why = rank_ceiling(cores, ram, headroom)
        if ceiling is not None and n > ceiling:
            return plan(ceiling,
                        'requested %d MPI ranks, clamped to %d (%s)'
                        % (n, ceiling, why), requested=n, clamped_from=n)
        return plan(n, 'requested: %d MPI ranks' % n, requested=n)
    # P1-25: 1D follows the same rules (it was always serial). Its wedge
    # decomposes along r like any mesh; under the shared cell floor an
    # auto (0) 1D run of default size still stays serial (batch 1d-mpi D1)
    # dynamic AMR runs in parallel since T42 (N16-b) - the ingest reads
    # processor*/ directly, so no reconstruction is needed
    if n_cells < AUTO_PARALLEL_MIN_CELLS:
        return plan(1, '1 rank: %s cells is below the %s-cell parallel '
                       'floor' % (format(int(n_cells), ','),
                                  format(AUTO_PARALLEL_MIN_CELLS, ',')))
    # N21: MAX_AUTO_PROCS is the fallback for an UNKNOWN core count, not
    # a standing ceiling - a measured 20-core machine is better
    # information than a constant, and the old cap left 4 cores idle.
    # `mpi_max_ranks` in settings.json overrides it either way.
    limits = []
    if max_ranks:
        limits.append((int(max_ranks),
                       'the %d-rank limit in settings' % int(max_ranks)))
    if cores:
        limits.append((cores - int(headroom),
                       '%d physical cores - %d headroom'
                       % (cores, int(headroom))))
    else:
        limits.append((MAX_AUTO_PROCS,
                       'the %d-rank cap (core count unknown)'
                       % MAX_AUTO_PROCS))
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


#: (expiry, value) for mpi_headroom - validate_case runs on every
#: keystroke, and this used to open and parse settings.json each time
_headroom_cache = (0.0, None)
_max_ranks_cache = (0.0, None)
_HEADROOM_TTL_S = 2.0


def mpi_headroom(default=1):
    """Cores kept free for the rest of the machine (settings.json
    `mpi_headroom`). The old hard-coded -2 was never justified.

    Briefly cached: the value changes only when the user edits the
    settings file, and the caller is on the GUI's validation path."""
    global _headroom_cache
    expiry, value = _headroom_cache
    now = time.time()
    if value is not None and now < expiry:
        return value
    try:
        from ...core import settings
        value = max(0, int(settings.load().get('mpi_headroom', default)))
    except Exception:
        return default
    _headroom_cache = (now + _HEADROOM_TTL_S, value)
    return value


def mpi_max_ranks(default=0):
    """Hard rank limit from settings.json (`mpi_max_ranks`, 0 = auto).

    Cached like `mpi_headroom` - same per-keystroke validation path."""
    global _max_ranks_cache
    expiry, value = _max_ranks_cache
    now = time.time()
    if value is not None and now < expiry:
        return value
    try:
        from ...core import settings
        value = max(0, int(settings.load().get('mpi_max_ranks', default)))
    except Exception:
        return default
    _max_ranks_cache = (now + _HEADROOM_TTL_S, value)
    return value


def resolve_nprocs(n_req, n_cells, dim=3, amr=0, headroom=None):
    """Effective MPI rank count - a thin wrapper over the pure
    `plan_run` that supplies the probed hardware. Explicit n_req >= 1 is
    honored as-is (the runner adds mpirun opt-in flags when it exceeds
    the slot count)."""
    if headroom is None:
        headroom = mpi_headroom()
    return plan_run(n_req, n_cells, cores=detect_slots(),
                    ram_gb=detect_ram_gb(), dim=dim, amr=amr,
                    headroom=headroom, ram_source=_ram_src,
                    cores_source=_slots_src,
                    max_ranks=mpi_max_ranks()).ranks


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


def _cleanup_cfg(settings):
    """DEFAULTS updated with `settings`: the one merge the dry run and
    the sweep share, so they cannot disagree."""
    from ...core import settings as gui_settings
    cfg = dict(gui_settings.DEFAULTS)
    cfg.update(settings or {})
    return cfg


def cleanup_plan(settings=None, now=None):
    """P0-5 dry run: what the sweep WOULD delete under `settings`'
    thresholds, deleting nothing.

    Returns [dict(dir, name, bytes, mtime)] in `cleanup_policy` order
    (oldest first). The `auto_cleanup` flag is deliberately ignored, so
    the owner can see what switching the sweep on would take. [] when
    WSL cannot be reached or there are no runs. Never calls
    `delete_runs`."""
    return _plan_and_dirs(_cleanup_cfg(settings), now)[0]


def _plan_and_dirs(cfg, now, dirs=None, info=None):
    """(cleanup_plan's list, every run dir listed) for a merged cfg.
    `dirs` / `info` already listed are reused (one `du`, not two)."""
    dirs = run_dirs() if dirs is None else dirs
    if not dirs:
        return [], dirs
    info = run_info(dirs) if info is None else info
    if not info:
        return [], dirs
    alive = runs_alive(dirs)
    records = [dict(dir=d, bytes=info.get(d, {}).get('bytes'),
                    mtime=info.get(d, {}).get('mtime'), alive=alive.get(d))
               for d in dirs]
    victims = cleanup_policy(
        records, now if now is not None else time.time(),
        max_bytes=float(cfg.get('cleanup_max_gb', 20)) * 1024 ** 3,
        max_age_s=float(cfg.get('cleanup_max_age_days', 14)) * 86400.0,
        keep_recent=int(cfg.get('cleanup_keep_recent', 3)))
    return [dict(dir=d, name=d.rstrip('/').rsplit('/', 1)[-1],
                 bytes=int(info[d]['bytes'] or 0), mtime=info[d]['mtime'])
            for d in victims], dirs


def auto_cleanup(settings=None, log=None, now=None):
    """Sweep the runs root per the GUI settings - opt-in: it runs only
    when the settings say `auto_cleanup: true` (the default is off since
    2026-09-27, owner: deletion inside WSL is final, a full disk is
    recoverable). Returns (n_deleted, bytes_deleted). One log line when
    something was removed; silent otherwise.

    Built on `cleanup_plan` (P0-5): it deletes exactly the dirs the dry
    run lists. With the flag off it lists nothing and touches no WSL."""
    cfg = _cleanup_cfg(settings)
    if not cfg.get('auto_cleanup', False):
        return 0, 0
    plan, dirs = _plan_and_dirs(cfg, now)
    if not plan:
        return 0, 0
    victims = [r['dir'] for r in plan]
    freed = sum(r['bytes'] for r in plan)
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


# ── the disk warning that replaces the default sweep (owner 2026-09-27) ────

def disk_warning_text(total_bytes, limit_gb, n_plan, plan_bytes):
    """The one-line runs-root warning. Pure. Kept under the 200-character
    status line of both GUIs, so the command at its end stays visible."""
    gb = 1024 ** 3
    runs = 'run' if n_plan == 1 else 'runs'
    return (f'WSL runs folder holds {total_bytes / gb:.1f} GB, over the '
            f'{float(limit_gb):g} GB limit; cleanup is off, nothing was '
            f'deleted. Cleanup would delete {n_plan} {runs} '
            f'({plan_bytes / gb:.1f} GB): '
            f'python -m blastlab --clean-foam-runs')


def disk_warning(settings=None, now=None):
    """The warning text when the sweep is OFF and the runs root is over
    `cleanup_max_gb`; None otherwise (sweep on, under the limit, no runs,
    or WSL unreachable). Lists and sizes only - never calls
    `delete_runs`. One `du` round trip; `runs_alive` only when over."""
    cfg = _cleanup_cfg(settings)
    if cfg.get('auto_cleanup', False):
        return None
    dirs = run_dirs()
    if not dirs:
        return None
    info = run_info(dirs)
    if not info:
        return None
    total = sum(int(r.get('bytes') or 0) for r in info.values())
    limit_gb = float(cfg.get('cleanup_max_gb', 20))
    if total <= limit_gb * 1024 ** 3:
        return None
    plan = _plan_and_dirs(cfg, now, dirs, info)[0]
    return disk_warning_text(total, limit_gb, len(plan),
                             sum(r['bytes'] for r in plan))


def start_disk_warning(settings=None, warn=None, private_ok=False):
    """Run `disk_warning` on a daemon thread at GUI start and hand a
    non-None text to `warn` (from that thread - the caller marshals it
    to its GUI thread). Silent in the GUI on any error: WSL unreachable
    must never reach the user as a fault (an unexpected exception gets
    one stderr line). Deletes nothing.

    Not started (returns None) under a private settings file, i.e. with
    BLASTLAB_SETTINGS set, unless `private_ok`: every test and QA harness
    builds windows that way (CLAUDE.md 8.2), and none of them should run
    `du` over the real corpus or get a status line it did not ask for."""
    if os.environ.get('BLASTLAB_SETTINGS') and not private_ok:
        return None

    def work():
        try:
            text = disk_warning(settings)
            if text and warn:
                warn(text)
        except Exception as exc:              # never kill the GUI for this
            # WSL unreachable does not raise (run_dirs / run_info return
            # empty), so what lands here is a fault or a closed window:
            # one stderr line, never the GUI, never swallowed silently
            import sys
            print(f'[blastlab] disk warning skipped: '
                  f'{type(exc).__name__}: {exc}', file=sys.stderr)

    th = threading.Thread(target=work, daemon=True,
                          name='blastlab-disk-warning')
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
