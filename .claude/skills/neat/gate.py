"""Test gate for /neat: run every fast suite, print one line per failure.

The point is tokens. A full test run prints thousands of lines; the agent
needs to know only which suites failed and why. Logs go to a scratch
folder, the console gets a summary, and `--against` reports only what
changed relative to a saved run (a suite red before the edit is not the
edit's fault).

    python .claude/skills/neat/gate.py --baseline     # prints its NAME
    python .claude/skills/neat/gate.py --against NAME
    python .claude/skills/neat/gate.py --only regression foam_writer

`--baseline` is keyed on HEAD plus the working-tree diff, and reuses a
saved run with the same key - a second apply on an unchanged tree does
not pay for the "before" run again.

Excluded on purpose: the WSL solve suites (minutes each, and they need an
idle VM - CLAUDE.md 8.6), `_e2e_*` and `_qa_*`. A tidy edit that cannot
change a number is fully covered by the byte-level regression plus the
fast suites; the solve suites are for physics changes, which /neat never
makes.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
TESTS = os.path.join(ROOT, 'blastlab', 'tests')
STATE = os.path.join(tempfile.gettempdir(), 'neat_gate')

#: real blastFoam solves inside WSL ("Auto-SKIPs without WSL", 1-16 min each)
WSL_SOLVES = {
    'test_foam_1d_vs_native.py', 'test_foam_2d.py', 'test_foam_3d_smoke.py',
    'test_foam_features.py', 'test_foam_kb_anchor.py', 'test_foam_parallel.py',
    'test_foam_postmortem.py', 'test_foam_stop.py',
}
#: run first: CLAUDE.md 6 - nothing else is trusted until this is green
FIRST = 'test_regression.py'
#: suites that build a Qt/Tk app or the viewer child run one at a time:
#: two apps at once, or a GUI suite starved of CPU, trip their own
#: internal waits (test_run_preflight's CLI run did, at 8 lanes)
GUI_SOURCE = re.compile(r'PySide6|tkinter|blastlab\.ui|blastlab\.gui|viz3d')
#: 8 lanes pushed test_blast3d from 10.6 to over 15 min (BLAS threads
#: oversubscribe the cores); 4 + the GUI lane measured clean
JOBS = 4
TIMEOUT_S = 1800
TAIL_LINES = 12


def suites(only):
    names = sorted(f for f in os.listdir(TESTS)
                   if f.startswith('test_') and f.endswith('.py')
                   and f not in WSL_SOLVES)
    if only:
        names = [n for n in names if any(o in n for o in only)]
    if FIRST in names:
        names.remove(FIRST)
        names.insert(0, FIRST)
    return names


def check_cleanup_off():
    """CLAUDE.md 8.2: GUI suites build the app; never with auto_cleanup on."""
    sys.path.insert(0, ROOT)
    from blastlab.core import settings
    if settings.load().get('auto_cleanup'):
        sys.exit('ABORT: auto_cleanup is ON in ' + str(settings.config_path())
                 + ' - a GUI suite could delete the run corpus (CLAUDE.md 8.2).')


def tree_key():
    """'base-<sha12>' of HEAD + `git diff HEAD` + untracked .py paths."""
    def git(*a):
        return subprocess.run(['git', *a], cwd=ROOT, capture_output=True).stdout
    h = hashlib.sha256()
    h.update(git('rev-parse', 'HEAD'))
    h.update(git('diff', 'HEAD', '--', 'blastlab'))
    h.update(git('ls-files', '--others', '--exclude-standard', '--', '*.py'))
    return 'base-' + h.hexdigest()[:12]


def run_one(name, logdir):
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, '-u', name], cwd=TESTS,
                           capture_output=True, text=True,
                           encoding='utf-8', errors='replace',
                           timeout=TIMEOUT_S)
        out, code = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        out, code = (e.stdout or '') + f'\nTIMEOUT after {TIMEOUT_S} s', -1
        if isinstance(out, bytes):
            out = out.decode('utf-8', 'replace')
    with open(os.path.join(logdir, name + '.log'), 'w', encoding='utf-8') as f:
        f.write(out)
    tail = [ln for ln in out.strip().splitlines() if ln.strip()][-TAIL_LINES:]
    return {'ok': code == 0, 'code': code, 's': round(time.time() - t0, 1),
            'tail': tail}


def past_durations():
    """Seconds per suite from the newest saved run, for longest-first order."""
    runs = [os.path.join(STATE, f) for f in os.listdir(STATE) if f.endswith('.json')]
    if not runs:
        return {}
    with open(max(runs, key=os.path.getmtime)) as f:
        return {n: r['s'] for n, r in json.load(f).items()}


def is_gui(name):
    with open(os.path.join(TESTS, name), encoding='utf-8', errors='replace') as f:
        return bool(GUI_SOURCE.search(f.read()))


def run_all(names, logdir, jobs):
    """GUI suites one at a time in their own lane (real windows, one Qt/Tk
    app per process, viewer child); everything else on `jobs` lanes,
    longest first so test_blast3d (~10 min) does not start last."""
    if jobs <= 1:
        return {n: run_one(n, logdir) for n in names}
    gui = [n for n in names if is_gui(n)]
    rest = [n for n in names if n not in gui]
    dur = past_durations()
    rest.sort(key=lambda n: -dur.get(n, 30))
    res = {}
    with ThreadPoolExecutor(max_workers=jobs + 1) as pool:
        lane = pool.submit(lambda: {n: run_one(n, logdir) for n in gui})
        futs = {pool.submit(run_one, n, logdir): n for n in rest}
        for fu, n in futs.items():
            res[n] = fu.result()
        res.update(lane.result())
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--baseline', action='store_true',
                    help='save (or reuse) a run keyed on the current tree')
    ap.add_argument('--save', metavar='NAME', help='store results under NAME')
    ap.add_argument('--against', metavar='NAME', help='report changes vs NAME')
    ap.add_argument('--only', nargs='+', metavar='SUBSTR',
                    help='run only suites whose filename contains SUBSTR')
    ap.add_argument('-j', '--jobs', type=int, default=JOBS,
                    help=f'parallel lanes for non-GUI suites (default {JOBS}; 1 = serial)')
    args = ap.parse_args()

    if args.baseline:
        args.save = tree_key()
        saved = os.path.join(STATE, args.save + '.json')
        if os.path.exists(saved) and not args.only:
            with open(saved) as f:
                bad = [n for n, r in json.load(f).items() if not r['ok']]
            print(f'BASELINE {args.save} (reused, tree unchanged); '
                  f'red: {", ".join(bad) or "none"}')
            return 0
        print(f'BASELINE {args.save}')

    check_cleanup_off()
    names = suites(args.only)
    tag = args.save or args.against or 'last'
    logdir = os.path.join(STATE, tag + ('-after' if args.against else ''))
    os.makedirs(logdir, exist_ok=True)

    t0 = time.time()
    res = run_all(names, logdir, args.jobs)
    res = {n: res[n] for n in names}
    wall = time.time() - t0

    if args.save:
        with open(os.path.join(STATE, args.save + '.json'), 'w') as f:
            json.dump(res, f)

    failed = [n for n, r in res.items() if not r['ok']]
    print(f'{len(names) - len(failed)}/{len(names)} suites green, '
          f'{wall / 60:.1f} min. Logs: {logdir}')
    reg = res.get(FIRST)
    if reg is not None:
        print('regression (byte-for-byte):', 'PASS' if reg['ok'] else 'FAIL')

    if args.against:
        with open(os.path.join(STATE, args.against + '.json')) as f:
            base = json.load(f)
        new = [n for n in failed if base.get(n, {}).get('ok', True)]
        fixed = [n for n, r in res.items() if r['ok'] and n in base
                 and not base[n]['ok']]
        old = [n for n in failed if n not in new]
        if old:
            print('red before AND after (not this edit):', ', '.join(old))
        if fixed:
            print('green now, red before:', ', '.join(fixed))
        for n in new:
            print(f'\nNEW FAILURE {n} (exit {res[n]["code"]}):')
            print('\n'.join('  ' + ln for ln in res[n]['tail']))
        print('\nGATE:', 'FAIL' if new else 'PASS')
        return 1 if new else 0

    for n in failed:
        print(f'\nFAIL {n} (exit {res[n]["code"]}):')
        print('\n'.join('  ' + ln for ln in res[n]['tail']))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
