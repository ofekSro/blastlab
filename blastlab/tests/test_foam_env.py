"""foam.env tests: path translation, availability caching, background
probe. The live WSL probe runs only when wsl.exe is on PATH (last
check, real environment)."""

import os
import shutil
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
    posix, unc = env.new_case_dir(3, stamp='20260101-000000')
    check('case dir naming',
          posix == f'{env.RUNS_ROOT}/20260101-000000_3d'
          and unc == env.unc(posix))

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
    finally:
        env._probe = real_probe

    _reset()
    if shutil.which('wsl.exe'):
        ok, detail = env.check_available(force=True)
        check('live WSL probe', ok, detail)
    else:
        print('  [SKIP] live WSL probe (wsl.exe not on PATH)')

    print()
    if FAIL:
        print(f"FOAM ENV: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM ENV: PASS")


if __name__ == '__main__':
    main()
