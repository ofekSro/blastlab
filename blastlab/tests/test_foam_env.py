"""foam.env tests: path translation, availability caching, background
probe. The live WSL probe runs only when wsl.exe is on PATH (last
check, real environment)."""

import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.solvers.foam import env                          # noqa: E402
from blastlab.core.constants import (BYTES_PER_CELL,           # noqa: E402
                                     CELLS_PER_RANK,
                                     FOAM_CELLS_REFUSE,
                                     FOAM_CELLS_WARN,
                                     FOAM_VM_GB_ASSUMED)
from blastlab.solvers.foam.env import MAX_AUTO_PROCS           # noqa: E402
from blastlab.core import hardware                             # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


#: N21: the hardware cache is now a value + a source + a probe-attempt
#: flag per field, and only MEASURED suppresses a live probe. A test that
#: pokes the values alone would silently trigger a real WSL round trip
#: (and then plan against THIS machine), so save/restore all nine.
_HW_ATTRS = ('_cores', '_slots', '_ram_gb',
             '_cores_src', '_slots_src', '_ram_src',
             '_cores_tried', '_slots_tried', '_ram_tried')


def _save_hw():
    return tuple(getattr(env, a) for a in _HW_ATTRS)


def _restore_hw(saved):
    for a, v in zip(_HW_ATTRS, saved):
        setattr(env, a, v)


def _pin_hw(cores=None, slots=None, ram_gb=None):
    """Pin the caches as MEASURED so nothing probes WSL during a test."""
    env._cores, env._slots, env._ram_gb = cores, slots, ram_gb
    env._cores_src = hardware.MEASURED if cores else hardware.UNKNOWN
    env._slots_src = hardware.MEASURED if slots else hardware.UNKNOWN
    env._ram_src = hardware.MEASURED if ram_gb else hardware.UNKNOWN
    env._cores_tried = env._slots_tried = env._ram_tried = True


def _reset():
    with env._lock:
        env._state, env._detail = 'unchecked', ''



def run_plan_checks():
    """N17/T48: the pure planner, the `free -g` parse and the persisted
    hardware numbers."""
    print("\nT48: hardware-aware run plan")
    # (a) free -g parsing, with the header shapes distros actually print
    check('free -g: plain Mem: row',
          env.parse_free_gb('              total  used  free\n'
                            'Mem:              15     3    11\n'
                            'Swap:              4     0     4') == 15)
    check('free -g: lower-case and no Swap row',
          env.parse_free_gb('total used\nmem: 7 1') == 7)
    check('free -g: nothing usable -> 0',
          env.parse_free_gb('') == 0
          and env.parse_free_gb('Mem: notanumber') == 0
          and env.parse_free_gb('Total: 8') == 0)

    # (a2) N21: /proc/meminfo is the real probe now - `free -g` truncates,
    # so a sub-GiB VM and a failed probe both used to read as 0
    MI = 'MemTotal:       %d kB\nMemFree:  123 kB\nSwapTotal: 0 kB'
    check('meminfo: exact kB -> rounded GiB',
          env.parse_meminfo_gb(MI % 65_290_840) == 62
          and env.parse_meminfo_gb(MI % 133_000_000) == 127)
    check('meminfo: rounds up rather than truncating (7.7 GiB is not 7)',
          env.parse_meminfo_gb(MI % 8_074_000) == 8)
    check('meminfo: a sub-GiB VM is 1, never 0 - 0 means "unknown"',
          env.parse_meminfo_gb(MI % 700_000) == 1)
    check('meminfo: nothing usable -> None (distinct from a real 0)',
          env.parse_meminfo_gb('') is None
          and env.parse_meminfo_gb('MemTotal: notanumber') is None
          and env.parse_meminfo_gb(None) is None)

    # (b) pinned decision table: (n_req, cells, cores, ram, dim, amr) ->
    #     ranks, and whether the caps came from RAM
    P = env.plan_run
    table = [
        ('explicit request wins',      P(4, 10 ** 6, 8, 16, 3, 0), 4, True),
        ('explicit beats every floor', P(6, 1000, 8, 16, 3, 0), 6, True),
        ('1D is serial',               P(0, 10 ** 7, 8, 16, 1, 0), 1, True),
        ('AMR goes parallel (T42)',    P(0, 10 ** 7, 8, 16, 3, 2), 7, True),
        ('tiny grid is serial',        P(0, 120_000, 8, 16, 3, 0), 1, True),
        ('cores-limited',              P(0, 10 ** 7, 8, 64, 3, 0), 7, True),
        ('cells-limited',              P(0, 300_000, 32, 64, 3, 0), 6, True),
        ('RAM-limited',                P(0, 10 ** 7, 32, 8, 3, 0), 4, True),
        ('measured cores beat the rank cap (N21)',
                                       P(0, 10 ** 8, 64, 256, 3, 0), 63, True),
        ('unknown cores fall back to the rank cap',
                                       P(0, 10 ** 8, 0, 256, 3, 0), 16, True),
        ('unknown RAM -> conservative caps',
                                       P(0, 10 ** 7, 8, None, 3, 0), 7, False),
        ('single core still runs',     P(0, 10 ** 7, 1, 16, 3, 0), 1, True),
    ]
    for name, plan, want, from_mem in table:
        check(f'plan: {name} -> {want} rank(s)',
              plan.ranks == want and plan.from_memory is from_mem,
              f'{plan.ranks} ranks, from_memory={plan.from_memory}, '
              f'{plan.reason}')
    check('plan: every row explains itself',
          all(p.reason for _n, p, _w, _f in table))
    # N21: unknown hardware must TIGHTEN the caps, not loosen them. This
    # assertion used to pin the opposite (== FOAM_CELLS_*, i.e. 120M
    # cells on a machine nothing had been measured on).
    p_unknown = P(0, 10 ** 7, 8, None, 3, 0)
    p_assumed = P(0, 10 ** 7, 8, FOAM_VM_GB_ASSUMED, 3, 0)
    check('plan: unknown RAM -> the assumed-VM caps, not the ceilings',
          p_unknown.cell_cap_refuse == p_assumed.cell_cap_refuse
          and p_unknown.cell_cap_warn == p_assumed.cell_cap_warn
          and p_unknown.cell_cap_refuse < FOAM_CELLS_REFUSE,
          f'{p_unknown.cell_cap_refuse:,}')
    check('plan: unknown RAM is honest about it (from_memory False, '
          'ram_source UNKNOWN)',
          p_unknown.from_memory is False
          and p_unknown.ram_source == hardware.UNKNOWN)
    check('plan: FOAM_CELLS_* are a ceiling now - a huge VM cannot '
          'exceed them',
          P(0, 10 ** 7, 8, 4096, 3, 0).cell_cap_refuse == FOAM_CELLS_REFUSE
          and P(0, 10 ** 7, 8, 4096, 3, 0).cell_cap_warn == FOAM_CELLS_WARN)
    check('plan: a measured VM below the ceiling still sets the cap',
          P(0, 10 ** 7, 8, 62, 3, 0).cell_cap_refuse < FOAM_CELLS_REFUSE
          and P(0, 10 ** 7, 8, 62, 3, 0).from_memory is True)
    # N21: rank_ceiling - hard limits only, and silent when unknown
    rc = env.rank_ceiling
    check('ceiling: cores - headroom when RAM is unknown',
          rc(8, None, 1) == (7, '8 physical cores - 1 headroom'),
          str(rc(8, None, 1)))
    check('ceiling: RAM wins when it is the tighter limit',
          rc(64, 8, 1)[0] == 4, str(rc(64, 8, 1)))
    check('ceiling: nothing known -> None, so an explicit ask stands '
          '(the app must stay usable with WSL down)',
          rc(0, None, 1) == (None, ''))
    check('ceiling: never below 1',
          rc(1, 1, 1)[0] == 1 and rc(1, None, 4)[0] == 1)
    check('ceiling: ignores the cells/rank floor and the rank cap - '
          'those are efficiency, not physics',
          rc(64, 256, 1)[0] == 63)

    check('plan: an explicit request above the ceiling is clamped, and '
          'says so',
          P(99, 10 ** 7, 8, 16, 3, 0).ranks == 7
          and P(99, 10 ** 7, 8, 16, 3, 0).clamped is True
          and P(99, 10 ** 7, 8, 16, 3, 0).clamped_from == 99
          and 'clamped to 7' in P(99, 10 ** 7, 8, 16, 3, 0).reason,
          P(99, 10 ** 7, 8, 16, 3, 0).reason)
    check('plan: an explicit request that fits is untouched and not '
          'marked clamped',
          P(4, 10 ** 6, 8, 16, 3, 0).ranks == 4
          and P(4, 10 ** 6, 8, 16, 3, 0).clamped is False
          and P(4, 10 ** 6, 8, 16, 3, 0).requested == 4)
    check('plan: with no hardware known, an explicit request stands',
          P(32, 10 ** 7, 0, None, 3, 0).ranks == 32)
    p4 = P(0, 10 ** 6, 8, 4, 3, 0)
    check('plan: 4 GB VM -> ~1.1M cell refuse cap, warn at half',
          abs(p4.cell_cap_refuse - 0.70 * 4 * 2 ** 30 / BYTES_PER_CELL) < 1
          and p4.cell_cap_warn * 2 == p4.cell_cap_refuse
          or abs(p4.cell_cap_warn * 2 - p4.cell_cap_refuse) <= 1,
          f'{p4.cell_cap_warn:,} / {p4.cell_cap_refuse:,}')

    # (c) invariants over a sweep, not just the pinned rows
    bad = []
    for cores in (0, 1, 2, 4, 8, 16, 64):
        for ram in (None, 2, 4, 8, 16, 128):
            for cells in (0, 1000, 199_999, 200_000, 10 ** 6, 10 ** 8):
                for dim in (2, 3):
                    pl = P(0, cells, cores, ram, dim, 0)
                    if pl.ranks < 1:
                        bad.append((cores, ram, cells, 'ranks < 1'))
                    if cores and pl.ranks > max(1, cores - 1):
                        bad.append((cores, ram, cells, 'above cores'))
                    if pl.ranks > 1 and \
                            pl.ranks * CELLS_PER_RANK > cells:
                        bad.append((cores, ram, cells, 'below the floor'))
                    # N21: MAX_AUTO_PROCS bounds the plan only when the
                    # core count is unknown; a measured machine is
                    # bounded by its own cores instead (checked above)
                    if not cores and pl.ranks > MAX_AUTO_PROCS:
                        bad.append((cores, ram, cells, 'above the cap'))
    check('plan: sweep keeps every invariant '
          '(1 <= ranks <= cores - headroom, cells/rank floor, rank cap)',
          not bad, str(bad[:3]))

    # (d) the caches: primed from settings, dropped on demand
    old = _save_hw()
    try:
        env.forget_hardware()
        check('hardware(): None until something is known',
              env.hardware() is None)
        env.prime_hardware(cores=6, ram_gb=12)
        hw = env.hardware()
        check('hardware(): primed values are returned without a probe',
              hw == dict(cores=6, logical=None, ram_gb=12,
                         cores_source=hardware.CACHED,
                         ram_source=hardware.CACHED), str(hw))
        check('N21: primed values are CACHED, not MEASURED - so the live '
              'probe still runs and a .wslconfig change is noticed',
              env._slots_src == hardware.CACHED
              and env._ram_src == hardware.CACHED)
        env.prime_hardware(cores=99, ram_gb=99)
        check('hardware(): priming never overwrites a known value',
              env.hardware()['cores'] == 6
              and env.hardware()['ram_gb'] == 12)
        env.forget_hardware()
        check('forget_hardware(): back to unknown',
              env.hardware() is None)
        check('forget_hardware(): sources and probe-attempt flags reset too',
              env._slots_src == hardware.UNKNOWN
              and not env._ram_tried and not env._slots_tried)
    finally:
        _restore_hw(old)

    # (e) the hw_* keys survive a settings round trip
    import tempfile
    from blastlab.core import settings as st
    fd = os.path.join(tempfile.mkdtemp(), 'settings.json')
    st.save(dict(st.load(fd), hw_cores=8, hw_ram_gb=15,
                 hw_stamp='2026-09-07T12:00:00', mpi_headroom=2), fd)
    back = st.load(fd)
    check('settings: hw_cores / hw_ram_gb / hw_stamp / mpi_headroom '
          'round trip',
          (back['hw_cores'], back['hw_ram_gb'], back['mpi_headroom'])
          == (8, 15, 2) and back['hw_stamp'].startswith('2026-09-07'),
          str({k: back.get(k) for k in
               ('hw_cores', 'hw_ram_gb', 'hw_stamp', 'mpi_headroom')}))


def main():
    run_plan_checks()
    check('unc translation',
          env.unc('/root/a/b') == r'\\wsl.localhost\Ubuntu\root\a\b',
          env.unc('/root/a/b'))
    argv = env.wsl_argv('echo hi')
    check('wsl argv shape',
          argv[:5] == ['wsl.exe', '-d', 'Ubuntu', '-e', 'bash']
          and argv[5] == '-lc' and env.FOAM_BASHRC in argv[6]
          and argv[6].endswith('echo hi'))
    # ── N4: case_paths accepts UNC / posix / bare name ──────────────────
    for given in (r'\\wsl.localhost\Ubuntu\root\blastlab_runs\r1',
                  '/root/blastlab_runs/r1', 'r1', 'r1/'):
        px, un = env.case_paths(given)
        check(f'case_paths({given!r})',
              px == '/root/blastlab_runs/r1'
              and un == r'\\wsl.localhost\Ubuntu\root\blastlab_runs\r1',
              f'{px} {un}')
    try:
        env.case_paths(r'\\other\share\x')
        check('case_paths rejects a foreign UNC', False)
    except ValueError:
        check('case_paths rejects a foreign UNC', True)
    from blastlab.solvers.foam.export_vtk import can_export
    check('can_export: native result -> False',
          not can_export(dict(solver='native', case_dir='C:/')))
    check('can_export: foam result with a missing dir -> False',
          not can_export(dict(solver='blastfoam',
                              case_dir=r'\\wsl.localhost\Ubuntu\nope')))
    check('can_export: foam result with an existing dir -> True',
          can_export(dict(solver='blastfoam', case_dir=os.getcwd())))

    # ── N8: run-dir info parsing, cleanup policy, settings ─────────────
    dirs = ['/root/blastlab_runs/a', '/root/blastlab_runs/b']
    info = env._parse_info('INFO|/root/blastlab_runs/a|1024|1700000000\n'
                           'junk\nINFO|/root/blastlab_runs/b||\n', dirs)
    check('run_info parse: bytes/mtime, blanks -> None',
          info['/root/blastlab_runs/a'] == dict(bytes=1024, mtime=1700000000)
          and info['/root/blastlab_runs/b'] == dict(bytes=None, mtime=None))
    now = 1_000_000.0
    day = 86400.0
    recs = [dict(dir='old_dead', bytes=5 * 1024 ** 3, mtime=now - 30 * day, alive=False),
            dict(dir='old_alive', bytes=5 * 1024 ** 3, mtime=now - 30 * day, alive=True),
            dict(dir='old_unknown', bytes=5 * 1024 ** 3, mtime=now - 30 * day, alive=None),
            dict(dir='mid', bytes=6 * 1024 ** 3, mtime=now - 5 * day, alive=False),
            dict(dir='new1', bytes=1 * 1024 ** 3, mtime=now - 3 * day, alive=False),
            dict(dir='new2', bytes=1 * 1024 ** 3, mtime=now - 2 * day, alive=False),
            dict(dir='new3', bytes=1 * 1024 ** 3, mtime=now - 1 * day, alive=False),
            dict(dir='nosize', bytes=None, mtime=now - 40 * day, alive=False)]
    v = env.cleanup_policy(recs, now, max_bytes=None, max_age_s=14 * day, keep_recent=3)
    check('policy: age rule deletes only dead, sized, non-recent runs',
          v == ['old_dead'], str(v))
    v = env.cleanup_policy(recs, now, max_bytes=10 * 1024 ** 3, max_age_s=None, keep_recent=3)
    check('policy: size rule deletes oldest first until under the cap',
          v == ['old_dead', 'mid'], str(v))
    v = env.cleanup_policy(recs, now, max_bytes=1 * 1024 ** 3, max_age_s=None, keep_recent=3)
    check('policy: the 3 most recent are never deleted even over the cap',
          set(v) == {'old_dead', 'mid'}, str(v))
    v = env.cleanup_policy(recs, now, max_bytes=1 * 1024 ** 3, max_age_s=None, keep_recent=0)
    check('policy: keep_recent=0 (CLI) frees everything deletable',
          v == ['old_dead', 'mid', 'new1', 'new2', 'new3'], str(v))
    check('policy: nothing when both limits are off',
          env.cleanup_policy(recs, now, None, None, 3) == [])
    from blastlab.core import settings as gs
    import tempfile
    sp = os.path.join(tempfile.mkdtemp(prefix='blastlab_set_'), 'settings.json')
    check('settings: defaults when the file is missing',
          gs.load(sp) == gs.DEFAULTS)
    gs.save(dict(gs.DEFAULTS, auto_cleanup=False, cleanup_max_gb=5), sp)
    got = gs.load(sp)
    check('settings: round trip keeps overrides and fills defaults',
          got['auto_cleanup'] is False and got['cleanup_max_gb'] == 5
          and got['cleanup_keep_recent'] == 3, str(got))
    with open(sp, 'w') as f:
        f.write('{ not json')
    check('settings: corrupt file -> defaults', gs.load(sp) == gs.DEFAULTS)
    check('auto_cleanup honours the opt-out without touching WSL',
          env.auto_cleanup(dict(auto_cleanup=False)) == (0, 0))

    # ── B13: run dirs are unique, not just timestamped ─────────────────
    posix, unc = env.new_case_dir(3, stamp='20260101-000000')
    check('case dir naming',
          posix.startswith(f'{env.RUNS_ROOT}/20260101-000000_3d_')
          and f'p{os.getpid()}-' in posix and unc == env.unc(posix),
          posix)
    again, _ = env.new_case_dir(3, stamp='20260101-000000')
    check('same second + same process -> different dir',
          again != posix, f'{posix} vs {again}')
    burst = {env.new_case_dir(2, stamp='20260101-000000')[0]
             for _ in range(5)}
    check('a burst of runs is collision-free', len(burst) == 5)

    real_probe = env._probe
    try:
        # caching: first probe result sticks until force=True
        _reset()
        env._probe = lambda timeout: (True, 'fake ok')
        ok, detail = env.check_available()
        check('probe result cached as ok', ok and detail == 'fake ok'
              and env.status() == ('ok', 'fake ok'))
        env._probe = lambda timeout: (False, 'fake bad')
        ok, _ = env.check_available()
        check('cache hit without force', ok)
        ok, detail = env.check_available(force=True)
        check('force re-probes', not ok and detail == 'fake bad'
              and env.status()[0] == 'fail')

        # background probe: status flips checking -> ok
        _reset()
        env._probe = lambda timeout: (time.sleep(0.2),
                                      (True, 'bg ok'))[1]
        env.ensure_check_started()
        st0 = env.status()[0]
        for _ in range(50):
            if env.status()[0] == 'ok':
                break
            time.sleep(0.05)
        check('background probe', st0 == 'checking'
              and env.status() == ('ok', 'bg ok'))
        env.ensure_check_started()      # no-op once resolved
        check('ensure is idempotent', env.status() == ('ok', 'bg ok'))

        # fail-retry: a cached failure heals after the cooldown
        _reset()
        env._probe = lambda timeout: (False, 'down')
        ok, _ = env.check_available()
        check('failure cached', not ok and env.status()[0] == 'fail')
        env._probe = lambda timeout: (True, 'healed')
        ok, _ = env.check_available()
        check('failure held within cooldown', not ok)
        with env._lock:
            env._last_fail = (time.time()
                              - env.FAIL_RETRY_COOLDOWN_S - 1)
        ok, detail = env.check_available()
        check('failure retried after cooldown', ok and detail == 'healed')

        # status() self-heal: a stale failure re-kicks the bg probe
        _reset()
        env._probe = lambda timeout: (False, 'down')
        env.check_available()
        env._probe = lambda timeout: (True, 'healed')
        with env._lock:
            env._last_fail = (time.time()
                              - env.FAIL_RETRY_COOLDOWN_S - 1)
        st0 = env.status()[0]
        for _ in range(50):
            if env.status()[0] == 'ok':
                break
            time.sleep(0.05)
        check('status self-heals after cooldown', st0 == 'checking'
              and env.status() == ('ok', 'healed'))
    finally:
        env._probe = real_probe

    # ── B14a: .run.pid scan parsing (pure - no WSL) ────────────────────
    dirs = ['/root/blastlab_runs/a_3d', '/root/blastlab_runs/b_3d']
    recs = env._parse_scan(f'RUN|{dirs[0]}|4242|777|1\n'
                           f'RUN|{dirs[1]}|||0\n', dirs)
    check('scan: alive run parsed (solver + owner pid)',
          recs[dirs[0]] == env.RunPid(dirs[0], 4242, 777, True),
          str(recs[dirs[0]]))
    check('scan: empty .run.pid -> dead, no pids',
          recs[dirs[1]] == env.RunPid(dirs[1], None, None, False),
          str(recs[dirs[1]]))
    check('scan: a dir WSL said nothing about stays unknown, not False',
          env._parse_scan('', dirs)[dirs[0]].alive is None)
    script = env._scan_script(dirs)
    check('scan script quotes each dir and uses kill -0',
          f"'{dirs[0]}'" in script and 'kill -0' in script, script)
    check('plain argv skips the OpenFOAM bashrc',
          env.FOAM_BASHRC not in env.wsl_plain_argv('true')[-1])

    # ── B14b: owner liveness + the orphan predicate ────────────────────
    dead = subprocess.Popen([sys.executable, '-c', 'pass'])
    dead.wait()
    check('own pid reads as alive', env._win_pid_alive(os.getpid()))
    check('exited pid reads as dead',
          not env._win_pid_alive(dead.pid), f'pid {dead.pid}')
    check('pid 0/None read as dead',
          not env._win_pid_alive(0) and not env._win_pid_alive(None))

    d = dirs[0]
    check('orphan: solver alive, owner gone',
          env._is_orphan(env.RunPid(d, 4242, dead.pid, True)))
    check('not an orphan: owner still alive',
          not env._is_orphan(env.RunPid(d, 4242, os.getpid(), True)))
    check('not an orphan: solver already dead',
          not env._is_orphan(env.RunPid(d, 4242, dead.pid, False)))
    check('not an orphan: no owner recorded (pre-owner run dir)',
          not env._is_orphan(env.RunPid(d, 4242, None, True)))
    check('not an orphan: liveness unknown',
          not env._is_orphan(env.RunPid(d, 4242, dead.pid, None)))

    sig = env._signal_script([11, 22], 'TERM')
    check('signal script: direct kill + session pkill for every pid',
          'kill -TERM 11 ' in sig and 'pkill -TERM -s 11 ' in sig
          and 'kill -TERM 22 ' in sig and 'pkill -TERM -s 22 ' in sig,
          sig)

    # slots-aware auto parallel (mocked counts: 12 physical / 20 logical,
    # RAM unknown so the rank count is not RAM-limited)
    old_hw = _save_hw()
    try:
        _pin_hw(cores=20, slots=12, ram_gb=None)
        check('auto ranks = physical cores - headroom (T48: 1, was 2)',
              env.resolve_nprocs(0, 10 ** 6, headroom=1) == 11,
              str(env.resolve_nprocs(0, 10 ** 6, headroom=1)))
        check('auto stays serial on small grids',
              env.resolve_nprocs(0, 10 ** 5) == 1)
        # N21: an explicit ask above what the machine has is clamped,
        # not honoured. This row used to pin 16 ranks on a 12-core VM.
        check('explicit ranks clamped to what the machine has',
              env.resolve_nprocs(16, 10 ** 6, headroom=1) == 11,
              str(env.resolve_nprocs(16, 10 ** 6, headroom=1)))
        check('explicit ranks below the ceiling are honoured exactly',
              env.resolve_nprocs(4, 10 ** 6, headroom=1) == 4)
    finally:
        _restore_hw(old_hw)

    _reset()
    if shutil.which('wsl.exe'):
        ok, detail = env.check_available(force=True)
        check('live WSL probe', ok, detail)

        # live .run.pid liveness round trip, in /tmp so no stray run dir
        probe = '/tmp/blastlab_alive_probe'

        def wsl(script):
            return subprocess.run(
                env.wsl_plain_argv(script), capture_output=True,
                timeout=60, stdin=subprocess.DEVNULL,
                creationflags=env.CREATE_NO_WINDOW)
        try:
            wsl(f'mkdir -p {probe} && echo 1 > {probe}/.run.pid')
            check('run_is_alive: pid 1 (init) reads as running',
                  env.run_is_alive(probe) is True)
            wsl(f'echo 4194303 > {probe}/.run.pid')
            check('run_is_alive: unused pid reads as not running',
                  env.run_is_alive(probe) is False)
            check('run_is_alive: missing dir reads as not running',
                  env.run_is_alive('/tmp/blastlab_no_such_run') is False)
        finally:
            wsl(f'rm -rf {probe}')
    else:
        print('  [SKIP] live WSL probe (wsl.exe not on PATH)')

    print()
    if FAIL:
        print(f"FOAM ENV: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM ENV: PASS")


if __name__ == '__main__':
    main()
