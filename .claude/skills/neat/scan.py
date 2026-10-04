"""Deterministic tidy scan for /neat - no model reads a file to find candidates.

    python .claude/skills/neat/scan.py blastlab/core          # ranked files
    python .claude/skills/neat/scan.py blastlab/ui --top 8
    python .claude/skills/neat/scan.py blastlab/ui/theme.py --detail

Findings are CANDIDATES, not verdicts: a name the grep never sees may still
be reached through getattr, a Qt slot string or a test. The agent that
writes the proposal confirms each one before it becomes an item.
"""

import argparse
import ast
import os
import re
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
PKG = os.path.join(ROOT, 'blastlab')

LONG_FUNC = 80      # lines
DEEP_NEST = 4       # if/for/while/with/try levels inside one function
CODE_LIKE = re.compile(r'^\s*#\s*(?:[\w.\[\]]+\s*=[^=]|(?:def|class|if|for|while|return|import|from|print)\b|\w+\()')

#: tier A - numbers that reach a Result, a gauge, a case file or a report
TIER_A = {
    'solvers/solver1d.py', 'solvers/solver2d.py', 'solvers/solver3d.py',
    'solvers/foam/writer.py', 'solvers/foam/dicts.py', 'solvers/foam/materials.py',
    'solvers/foam/reader.py',
}
TIER_A_CORE_EXCEPT = {'settings.py', 'mode.py', 'hardware.py', 'case.py',
                      'chain.py', '__init__.py'}
OFF_LIMITS = ('tests/baseline', 'tests/foam_fixtures', 'tests/foam_golden')


def tier(path):
    rel = os.path.relpath(path, PKG).replace(os.sep, '/')
    if rel.startswith(OFF_LIMITS):
        return 'X'
    if rel in TIER_A:
        return 'A'
    top, _, name = rel.partition('/')
    if top == 'core':
        return 'B' if name in TIER_A_CORE_EXCEPT else 'A'
    return {'ui': 'C', 'viz3d': 'D', 'gui': 'E', 'tests': 'T'}.get(top, 'B')


def py_files(target):
    if os.path.isfile(target):
        return [target]
    out = []
    for d, dirs, files in os.walk(target):
        dirs[:] = [x for x in dirs if x != '__pycache__' and
                   not os.path.join(d, x).replace(os.sep, '/').endswith(OFF_LIMITS)]
        out += [os.path.join(d, f) for f in files if f.endswith('.py')]
    return sorted(out)


def corpus_tokens():
    """Identifier counts over the whole repo's Python (tests included)."""
    c = Counter()
    for f in py_files(PKG):
        with open(f, encoding='utf-8', errors='replace') as h:
            c.update(re.findall(r'\b[A-Za-z_]\w*\b', h.read()))
    return c


def nest_depth(node, d=0):
    deep = d
    for ch in ast.iter_child_nodes(node):
        step = isinstance(ch, (ast.If, ast.For, ast.While, ast.With, ast.Try))
        # an `elif` is an If inside the orelse of an If - same level, not deeper
        if (isinstance(node, ast.If) and isinstance(ch, ast.If)
                and node.orelse == [ch]):
            step = 0
        deep = max(deep, nest_depth(ch, d + step))
    return deep


def scan_file(path, tokens):
    with open(path, encoding='utf-8', errors='replace') as h:
        src = h.read()
    lines = src.splitlines()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return {'err': str(e)}
    items = []

    # unused imports (module level; __init__ and legacy/ re-exports are the API)
    reexport = (path.endswith('__init__.py')
                or os.sep + 'legacy' + os.sep in path)
    if not reexport:
        own = Counter(re.findall(r'\b[A-Za-z_]\w*\b', src))
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if 'noqa' in lines[node.lineno - 1]:
                    continue
                for a in node.names:
                    name = (a.asname or a.name).split('.')[0]
                    if name != '*' and own[name] <= 1 and '__all__' not in src:
                        items.append((node.lineno, 'unused-import', name))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n = node.end_lineno - node.lineno + 1
            if n > LONG_FUNC:
                items.append((node.lineno, 'long-func', f'{node.name} ({n} lines)'))
            d = nest_depth(node)
            if d > DEEP_NEST:
                items.append((node.lineno, 'deep-nest', f'{node.name} (depth {d})'))
            if (node.name.startswith('_') and not node.name.startswith('__')
                    and tokens[node.name] <= 1):
                items.append((node.lineno, 'unreferenced', node.name))
        elif isinstance(node, ast.ExceptHandler):
            silent = all(isinstance(s, ast.Pass) for s in node.body)
            if node.type is None or silent:
                what = 'bare except' if node.type is None else 'except ... pass'
                items.append((node.lineno, 'silent-except', what))

    run = 0
    for i, ln in enumerate(lines + [''], 1):
        if CODE_LIKE.match(ln):
            run += 1
            continue
        if run >= 3:
            items.append((i - run, 'commented-code', f'{run} lines'))
        run = 0

    return {'lines': len(lines), 'items': sorted(items)}


WEIGHT = {'unused-import': 1, 'unreferenced': 3, 'commented-code': 2,
          'silent-except': 3, 'long-func': 2, 'deep-nest': 2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('target')
    ap.add_argument('--top', type=int, default=12)
    ap.add_argument('--detail', action='store_true')
    args = ap.parse_args()
    target = os.path.join(ROOT, args.target) if not os.path.isabs(args.target) else args.target

    tokens = corpus_tokens()
    rows = []
    for f in py_files(target):
        t = tier(f)
        if t in ('X', 'T') and not os.path.isfile(target):
            continue
        r = scan_file(f, tokens)
        rel = os.path.relpath(f, ROOT).replace(os.sep, '/')
        if 'err' in r:
            print(f'{rel}: parse error {r["err"]}')
            continue
        score = sum(WEIGHT[k] for _, k, _ in r['items'])
        rows.append((score, rel, t, r))

    if args.detail:
        for _, rel, t, r in rows:
            print(f'{rel}  tier {t}  {r["lines"]} lines')
            for ln, kind, what in r['items']:
                print(f'  L{ln:<5} {kind:<15} {what}')
        return 0

    rows.sort(reverse=True)
    print(f'{len(rows)} files scanned; top {min(args.top, len(rows))} by score '
          '(tier: A numerics, B plumbing, C Qt, D viewer, E Tk)')
    for score, rel, t, r in rows[:args.top]:
        kinds = Counter(k for _, k, _ in r['items'])
        summary = ', '.join(f'{v} {k}' for k, v in kinds.most_common())
        print(f'{score:>3}  {t}  {rel} ({r["lines"]})  {summary or "-"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
