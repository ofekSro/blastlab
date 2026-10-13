"""Test gate for /neat and /bl-todo: run fast suites, print one line per failure.

The point is tokens. A full test run prints thousands of lines; the agent
needs to know only which suites failed and why. Logs go to a scratch
folder, the console gets a summary, and `--against` reports only what
changed relative to a saved run (a suite red before the edit is not the
edit's fault).

    python .claude/skills/neat/gate.py --baseline     # prints its NAME
    python .claude/skills/neat/gate.py --against NAME
    python .claude/skills/neat/gate.py --only regression foam_writer
    python .claude/skills/neat/gate.py --changed HEAD          # this edit
    python .claude/skills/neat/gate.py --for blastlab/ui/run_panel.py --deep

`--baseline` is keyed on HEAD plus the working-tree diff, and reuses a
saved run with the same key - a second apply on an unchanged tree does
not pay for the "before" run again.

`--changed REV` (files changed since REV, uncommitted and untracked
included) and `--for FILE...` (paths from the repo root) run only the
suites that import those files - anywhere in the suite, lazy imports and
dotted names in strings included, and through the test helpers. `--deep`
follows the imports through the package too, so a suite that builds the
MainWindow runs for a change to any widget it pulls in. Changed files no
fast suite imports, and WSL solve suites that would have been picked, are
printed - never silently dropped.

Excluded on purpose: the WSL solve suites (minutes each, and they need an
idle VM - CLAUDE.md 8.6), `_e2e_*` and `_qa_*`. A tidy edit that cannot
change a number is fully covered by the byte-level regression plus the
fast suites; the solve suites are for physics changes, which /neat never
makes.
"""

import argparse
import ast
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
#: below this much RAM the default is two lanes, not JOBS
LOW_RAM_GB = 16
#: below this much RAM the default is one lane: the home PC has 8 GB and
#: runs heavy suites one at a time (docs/agent-rules.md). The second lane
#: and /bl-todo's parallel mode share this threshold (owner 2026-10-13)
MIN_RAM_GB = 12
#: two gates at once (/bl-todo parallel, two worktrees) still run one GUI
#: suite at a time on the machine: a lock file all of them share
GUI_LOCK = 'gui-suite.lock'
TIMEOUT_S = 1800
TAIL_LINES = 12
#: a package module named inside a string (subprocess code, importlib)
DOTTED = re.compile(r'\bblastlab(?:\.\w+)+')
IMPORT_LINE = re.compile(r'^\s*(?:from|import)\s+([\w.]+)', re.M)


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


def module_name(path):
    """'<root>/blastlab/ui/run_panel.py' -> 'blastlab.ui.run_panel'
    (a package's `__init__.py` -> the package)."""
    parts = os.path.relpath(path, ROOT)[:-3].replace('\\', '/').split('/')
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def module_index():
    """{module name: path} for every package module outside tests/."""
    idx = {}
    for dirpath, dirs, files in os.walk(os.path.join(ROOT, 'blastlab')):
        dirs[:] = [d for d in dirs if d not in ('tests', '__pycache__')]
        for f in files:
            if f.endswith('.py'):
                p = os.path.join(dirpath, f)
                idx[module_name(p)] = p
    return idx


def imports_of(path, package=''):
    """Every name `path` imports, anywhere in the file; for
    `from X import Y` both X and X.Y. `package` resolves relative imports."""
    with open(path, encoding='utf-8-sig', errors='replace') as f:
        text = f.read()
    try:
        tree = ast.parse(text, path)
    except SyntaxError:  # the suite will fail anyway; select it by its text
        return set(IMPORT_LINE.findall(text)) | set(DOTTED.findall(text))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ''
            if node.level:
                base = package.split('.')[:len(package.split('.')) - node.level + 1]
                mod = '.'.join(base + ([mod] if mod else []))
            out.add(mod)
            out.update(mod + '.' + a.name for a in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.update(DOTTED.findall(node.value))
    return out


def with_parents(names):
    """Importing a.b.c runs a/__init__ and a/b/__init__ too."""
    out = set()
    for n in names:
        parts = n.split('.')
        out.update('.'.join(parts[:i]) for i in range(1, len(parts) + 1))
    return out


def closure(start, graph):
    seen, todo = set(), list(start)
    while todo:
        m = todo.pop()
        if m not in seen:
            seen.add(m)
            todo.extend(graph.get(m, ()))
    return seen


def changed_since(rev):
    """Repo-relative paths changed since `rev`: committed, staged,
    unstaged and untracked."""
    def git(*a):
        p = subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True)
        if p.returncode:
            sys.exit(f'git {" ".join(a)} failed: {p.stderr.strip()}')
        return p.stdout.splitlines()
    return sorted(set(git('diff', '--name-only', rev, '--'))
                  | set(git('ls-files', '--others', '--exclude-standard')))


def select(paths, deep):
    """Suites that import any of `paths`, plus changed suites themselves.
    Prints what it picked and what no fast suite covers; returns the names."""
    idx = module_index()
    helpers = {f[:-3]: os.path.join(TESTS, f) for f in os.listdir(TESTS)
               if f.endswith('.py') and not f.startswith(('test_', '_e2e_', '_qa_'))}
    keys, own, other = {}, set(), []
    for p in paths:
        full = os.path.normpath(p if os.path.isabs(p) else os.path.join(ROOT, p))
        rel = os.path.relpath(full, ROOT).replace('\\', '/')
        name = os.path.basename(full)
        if not rel.startswith('blastlab/'):
            continue
        if not rel.endswith('.py'):
            other.append(rel)
        elif os.path.dirname(full) == TESTS and name.startswith('test_'):
            own.add(name)
        elif os.path.dirname(full) == TESTS and name[:-3] in helpers:
            keys[name[:-3]] = rel
        elif rel.startswith('blastlab/tests/'):
            other.append(rel)
        else:
            keys[module_name(full)] = rel

    graph = {}
    if deep:
        for m, p in idx.items():
            pkg = m if p.endswith('__init__.py') else m.rpartition('.')[0]
            graph[m] = {x for x in with_parents(imports_of(p, pkg)) if x in idx}
    picked, wsl, hit = set(), set(), set()
    for name in sorted(f for f in os.listdir(TESTS)
                       if f.startswith('test_') and f.endswith('.py')):
        raw = imports_of(os.path.join(TESTS, name))
        for h in raw & helpers.keys():
            raw |= imports_of(helpers[h])
        reach = with_parents(raw)
        if deep:
            reach |= closure(reach & idx.keys(), graph)
        found = reach & keys.keys()
        if found or name in own:
            (wsl if name in WSL_SOLVES else picked).add(name)
            if name not in WSL_SOLVES:
                hit |= found

    how = 'imports, followed through the package' if deep else 'direct imports'
    print(f'{len(picked)} suites for {len(keys) + len(own)} changed files ({how})')
    uncovered = [keys[k] for k in keys if k not in hit] + other
    if uncovered:
        print('no fast suite imports (pick suites yourself, or try --deep):',
              ', '.join(sorted(uncovered)))
    if wsl:
        print('WSL solve suites not run (CLAUDE.md 8.6):', ', '.join(sorted(wsl)))
    return picked


def default_jobs():
    """JOBS lanes; two under LOW_RAM_GB; one under MIN_RAM_GB."""
    sys.path.insert(0, ROOT)
    from blastlab.core import hardware
    ram = hardware.detect_host_ram_gb()
    if ram and ram < MIN_RAM_GB:
        return 1
    return 2 if ram and ram < LOW_RAM_GB else JOBS


class gui_lock:
    """Hold the machine-wide GUI-suite lock (an OS file lock, released by the
    OS if the holder dies). Waits up to TIMEOUT_S, then runs anyway and says so."""

    def __enter__(self):
        os.makedirs(STATE, exist_ok=True)
        self.f = open(os.path.join(STATE, GUI_LOCK), 'a+b')
        t0 = time.time()
        while True:
            try:
                if os.name == 'nt':
                    import msvcrt
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.held = True
                return self
            except OSError:
                if time.time() - t0 > TIMEOUT_S:
                    print('GUI lock still taken after', TIMEOUT_S, 's - running without it')
                    self.held = False
                    return self
                time.sleep(2)

    def __exit__(self, *exc):
        if self.held:
            try:
                if os.name == 'nt':
                    import msvcrt
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        self.f.close()


def run_gui(name, logdir):
    with gui_lock():
        return run_one(name, logdir)


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
    gui = [n for n in names if is_gui(n)]
    if jobs <= 1:
        return {n: (run_gui if n in gui else run_one)(n, logdir) for n in names}
    rest = [n for n in names if n not in gui]
    dur = past_durations()
    rest.sort(key=lambda n: -dur.get(n, 30))
    res = {}
    with ThreadPoolExecutor(max_workers=jobs + 1) as pool:
        lane = pool.submit(lambda: {n: run_gui(n, logdir) for n in gui})
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
    ap.add_argument('--changed', metavar='REV',
                    help='run only the suites that import files changed since REV')
    ap.add_argument('--for', dest='files', nargs='+', metavar='FILE',
                    help='run only the suites that import FILE (repo-relative)')
    ap.add_argument('--deep', action='store_true',
                    help='with --changed / --for: follow imports through the package')
    ap.add_argument('-j', '--jobs', type=int, default=None,
                    help=f'parallel lanes for non-GUI suites (default {JOBS}, 2 under '
                         f'{LOW_RAM_GB} GB RAM, 1 under {MIN_RAM_GB} GB; 1 = serial)')
    args = ap.parse_args()
    picking = args.changed or args.files
    if picking and args.baseline:
        ap.error('--baseline keys a full run; do not combine it with --changed / --for')
    if args.jobs is None:
        args.jobs = default_jobs()

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

    names = suites(args.only)
    if picking:
        paths = (args.files or []) + (changed_since(args.changed) if args.changed else [])
        picked = select(paths, args.deep)
        names = [n for n in names if n in picked]
        if not names:
            print('nothing to run')
            return 0
    check_cleanup_off()
    # 'last' per checkout: two worktrees gating at once must not share logs
    tag = args.save or args.against or (
        'last-' + hashlib.sha256(ROOT.lower().encode()).hexdigest()[:8])
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
