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

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def _reset():
    with env._lock:
        env._state, env._detail = 'unchecked', ''


def main():
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
    from blastlab.gui import settings as gs
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

    # slots-aware auto parallel (mocked counts: 12 physical / 20 logical)
    old_slots, old_cores = env._slots, env._cores
    try:
        env._slots, env._cores = 12, 20
        check('auto ranks = physical cores - 2',
              env.resolve_nprocs(0, 10 ** 6) == 10)
        check('auto stays serial on small grids',
              env.resolve_nprocs(0, 10 ** 5) == 1)
        check('explicit ranks honored as-is',
              env.resolve_nprocs(16, 10 ** 6) == 16)
    finally:
        env._slots, env._cores = old_slots, old_cores

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
