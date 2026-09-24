"""Import layering of the blastlab package (Phase 0).

docs/ARCHITECTURE_REVIEW.md sections 2, 4 and 5 (Phase 0). Parses every
`import` statement under `blastlab/` with `ast` - nothing is imported, so
this is instant and needs no Qt, Tk or WSL - and asserts:

  * nothing under core/, solvers/, output/ or viz3d/ imports a GUI
    toolkit (tkinter, customtkinter, PySide6); viz3d/viewer.py is the one
    exception - it IS the viewer child process's Qt window;
  * core/ imports nothing outside core/ (it is the bottom layer);
  * ui/ (Qt) imports nothing from gui/ (Tk), and gui/ nothing from ui/.

`ALLOWED_UPWARD` records the edges that break those rules TODAY, so the
test is green on day 0; the later phases of the plan delete entries as
they remove the edges (Phase 1: the three `materials` entries). An entry
whose edge no longer exists fails the test, so the list cannot go stale.
Imports inside functions count the same as top-level ones: a deferred
import is still a dependency.

Run:  cd blastlab/tests && python test_layering.py      (or under pytest)
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, '..'))       # .../blastlab

TOOLKITS = {'tkinter', 'customtkinter', 'PySide6'}
NO_TOOLKIT = ('core', 'solvers', 'output', 'viz3d')
TOOLKIT_EXEMPT = {'viz3d.viewer'}

#: (importing module, imported module), both relative to `blastlab.`
ALLOWED_UPWARD = {
    ('core.eos', 'solvers.foam.materials'),
    ('core.case', 'solvers.foam.materials'),
    ('core.case', 'solvers.foam.backend'),
    ('core.case', 'solvers.foam.env'),
    ('ui.app', 'gui.run_browser'),
}


def modules():
    """{dotted name relative to blastlab: path} for every module outside
    tests/."""
    out = {}
    for root, dirs, files in os.walk(PKG):
        dirs[:] = sorted(d for d in dirs
                         if d not in ('tests', '__pycache__')
                         and not d.startswith('.'))
        for f in sorted(files):
            if not f.endswith('.py'):
                continue
            rel = os.path.relpath(os.path.join(root, f), PKG)
            parts = rel[:-3].split(os.sep)
            if parts[-1] == '__init__':
                parts = parts[:-1]
            out['.'.join(parts)] = os.path.join(root, f)
    return out


def _is_package(path):
    return os.path.basename(path) == '__init__.py'


def imports(name, path, known):
    """Every module `name` imports: ('toolkit', top-level name) or
    ('pkg', module relative to blastlab)."""
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read(), path)
    here = name.split('.') if name else []
    pkg = here if _is_package(path) else here[:-1]
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split('.')[0]
                if top in TOOLKITS:
                    out.add(('toolkit', top))
                elif top == 'blastlab':
                    out.add(('pkg', a.name[len('blastlab.'):]))
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 0:
            mod = node.module or ''
            top = mod.split('.')[0]
            if top in TOOLKITS:
                out.add(('toolkit', top))
                continue
            if top != 'blastlab':
                continue
            base = mod.split('.')[1:]
        else:
            up = node.level - 1
            base = (pkg[:len(pkg) - up] if up else list(pkg)) \
                + (node.module.split('.') if node.module else [])
        for a in node.names:
            # `from .foam import env` imports the module foam.env
            sub = '.'.join(base + [a.name])
            out.add(('pkg', sub if sub in known else '.'.join(base)))
    return out


def edges():
    known = modules()
    return {name: imports(name, path, known)
            for name, path in known.items()}


def _layer(mod):
    return mod.split('.')[0] if mod else ''


def violations():
    """(rule, importer, imported) for every import that breaks a rule and
    is not in ALLOWED_UPWARD, and the set of allowed edges seen."""
    bad, seen = [], set()
    for name, deps in sorted(edges().items()):
        layer = _layer(name)
        for kind, dep in sorted(deps):
            if kind == 'toolkit':
                if layer in NO_TOOLKIT and name not in TOOLKIT_EXEMPT:
                    bad.append(('toolkit', name, dep))
                continue
            if (name, dep) in ALLOWED_UPWARD:
                seen.add((name, dep))
                continue
            dl = _layer(dep)
            if layer == 'core' and dl != 'core':
                bad.append(('core imports upward', name, dep))
            elif (layer, dl) in (('ui', 'gui'), ('gui', 'ui')):
                bad.append(('ui/gui cross-import', name, dep))
    return bad, seen


def test_no_toolkit_below_the_gui():
    bad, _ = violations()
    bad = [v for v in bad if v[0] == 'toolkit']
    assert not bad, f'GUI toolkit imported below the GUI layer: {bad}'


def test_core_imports_only_core():
    bad, _ = violations()
    bad = [v for v in bad if v[0] == 'core imports upward']
    assert not bad, f'core/ imports outside core/: {bad}'


def test_ui_and_gui_do_not_import_each_other():
    bad, _ = violations()
    bad = [v for v in bad if v[0] == 'ui/gui cross-import']
    assert not bad, f'Qt and Tk GUIs import each other: {bad}'


def test_allowed_upward_is_current():
    _, seen = violations()
    stale = sorted(ALLOWED_UPWARD - seen)
    assert not stale, (f'ALLOWED_UPWARD entries whose edge is gone - '
                       f'delete them: {stale}')


def test_scan_sees_the_package():
    """Guard against a scan that silently finds nothing."""
    known = modules()
    for mod in ('core.case', 'solvers.foam.env', 'ui.app', 'gui.app',
                'viz3d.viewer', 'output.gauge_summary'):
        assert mod in known, f'{mod} not found under {PKG}'


def main():
    fails = []
    for fn in (test_scan_sees_the_package, test_no_toolkit_below_the_gui,
               test_core_imports_only_core,
               test_ui_and_gui_do_not_import_each_other,
               test_allowed_upward_is_current):
        try:
            fn()
        except AssertionError as exc:
            fails.append(fn.__name__)
            print(f'  [FAIL] {fn.__name__} - {exc}')
        else:
            print(f'  [PASS] {fn.__name__}')
    print()
    print('LAYERING: ' + ('PASS' if not fails else
                          f'FAIL ({len(fails)}): ' + ', '.join(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
