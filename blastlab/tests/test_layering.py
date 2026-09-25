"""Import layering of the blastlab package (Phase 0, locked in Phase 9).

docs/ARCHITECTURE_REVIEW.md sections 2, 4 and 5 (Phases 0 and 9). Parses
every `import` statement under `blastlab/` with `ast` - nothing is
imported, so this is instant and needs no Qt, Tk or WSL - and asserts:

  * nothing under core/, models/, services/, solvers/, output/ or viz3d/
    imports a GUI toolkit (tkinter, customtkinter, PySide6);
    viz3d/viewer.py is the one exception - it IS the viewer child
    process's Qt window;
  * core/ imports nothing from services/, solvers/ or output/ (Phase 3),
    and more generally nothing outside core/ (it is the bottom layer);
  * models/ imports nothing outside core/ and models/ (Phase 2);
  * core/ and models/ never import a re-export shim (`core.case`,
    `core.chain`): those modules carry services/ names, so code in the
    two bottom layers must name the real module and let this test see
    the edge (Phase 9);
  * services/ imports no GUI package (ui/, gui/) - and no toolkit, above;
  * the engines (solvers/, output/, viz3d/) import no GUI package, and
    nothing from services/ except the command-line ENTRY_POINTS;
  * ui/ (Qt) imports nothing from gui/ (Tk), and gui/ nothing from ui/;
  * solvers/foam/runloop.py and solvers/foam/common.py do not import
    solvers/foam/backend.py - backend drives the run loop, so the
    dependency runs one way (Phase 9).

Three allowlists, kept apart on purpose so that "no real upward edge"
means something:

  REEXPORT_SHIMS  compatibility re-exports at an old import path. Each
                  edge is checked to be PURE: a star import only in a
                  module that holds nothing but imports, otherwise no
                  imported name may be used by the importing module's
                  own code. A shim that grows code fails here.
  ALLOWED_UPWARD  real upward dependencies still in the code, each with
                  its reason. Phase 9 of the plan aimed for none; see
                  the entries.
  ENTRY_POINTS    engine-layer modules that are really command-line
                  front ends (peers of cli.py and the two GUIs) and may
                  therefore call services/.

An entry whose edge no longer exists fails the test, so no list can go
stale. Imports inside functions count the same as top-level ones: a
deferred import is still a dependency.

Known limit: an engine module that imports a core shim (`core.case`,
`core.chain`) reaches services/ through it, and the engine rule does not
follow shims - see the Phase 9 report and the ENGINES comment below.

Run:  cd blastlab/tests && python test_layering.py      (or under pytest)
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, '..'))       # .../blastlab

TOOLKITS = {'tkinter', 'customtkinter', 'PySide6'}
NO_TOOLKIT = ('core', 'models', 'services', 'solvers', 'output', 'viz3d')
TOOLKIT_EXEMPT = {'viz3d.viewer'}
#: the layers core/ must never reach, not even through a new shim
ABOVE_CORE = ('services', 'solvers', 'output')
GUIS = ('ui', 'gui')
#: the engine layer. It still reaches services/ through the core.case /
#: core.chain shims (validate_case, _charge_radius, HANDOFF_MSG); only
#: DIRECT imports of services/ are checked here.
ENGINES = ('solvers', 'output', 'viz3d')

#: (importing module, imported module), both relative to `blastlab.`:
#: compatibility re-exports that keep an old import path working.
#: Checked to be pure by test_reexport_shims_are_pure.
REEXPORT_SHIMS = {
    # Phase 2: the case dataclasses and ValidationReport moved to models/
    ('core.case', 'models.case'),
    ('core.case', 'models.result'),
    ('core.assessment', 'models.hd13_case'),
    # Phase 3: validation and the chain helpers moved to services/;
    # core.case and core.chain are now nothing but these lines
    ('core.case', 'services.validation'),
    ('core.chain', 'services.chain'),
}

#: real upward edges still in the code - code that USES a name from the
#: layer above, not a re-export
ALLOWED_UPWARD = {
    # core/assessment.py is the HD 1.3 orchestration (validate, run,
    # build_vent_case). Its `validate` builds a models.result
    # ValidationReport and `build_vent_case` a models.case Case3D; before
    # Phase 9 both came in through the core.case shim, where this test
    # could not see them. Closing them means moving that orchestration
    # out of core/ (it is services/hd13 material), which no phase of the
    # plan does yet.
    ('core.assessment', 'models.result'),
    ('core.assessment', 'models.case'),
}

#: engine-layer modules that are command-line front ends and may import
#: services/: `python -m blastlab --hd13` lives in output/ for history;
#: the orchestration it wraps is services/hd13.py (Phase 7). Moving the
#: module would change an import path tests and __main__ use.
ENTRY_POINTS = {'output.cli_hd13'}


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


def _parse(path):
    with open(path, encoding='utf-8') as f:
        return ast.parse(f.read(), path)


def _resolved(name, path, known, tree):
    """(node, alias, kind, dep) for every imported name: kind is
    'toolkit' (dep = top-level name) or 'pkg' (dep = module relative to
    blastlab)."""
    here = name.split('.') if name else []
    pkg = here if _is_package(path) else here[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split('.')[0]
                if top in TOOLKITS:
                    yield node, a, 'toolkit', top
                elif top == 'blastlab':
                    yield node, a, 'pkg', a.name[len('blastlab.'):]
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 0:
            mod = node.module or ''
            top = mod.split('.')[0]
            if top in TOOLKITS:
                for a in node.names:
                    yield node, a, 'toolkit', top
                continue
            if top != 'blastlab':
                continue
            base = mod.split('.')[1:]
        else:
            # relative import: level 1 is this package, each extra dot one up
            up = node.level - 1
            base = pkg[:len(pkg) - up]
            if node.module:
                base = base + node.module.split('.')
        for a in node.names:
            # `from .foam import env` imports the module foam.env
            sub = '.'.join(base + [a.name])
            yield node, a, 'pkg', sub if sub in known else '.'.join(base)


def imports(name, path, known):
    """Every module `name` imports: ('toolkit', top-level name) or
    ('pkg', module relative to blastlab)."""
    return {(kind, dep)
            for _n, _a, kind, dep in _resolved(name, path, known, _parse(path))}


def edges():
    """{module: its imports()} for every module outside tests/."""
    known = modules()
    return {name: imports(name, path, known)
            for name, path in known.items()}


def _layer(mod):
    """Top-level package of a module relative to blastlab ('' for the
    package root itself)."""
    return mod.split('.')[0]


def _import_only(tree):
    """True when a module holds nothing but a docstring and imports."""
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            continue
        if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)):
            continue
        return False
    return True


def shim_modules():
    """The REEXPORT_SHIMS importers that are nothing but imports."""
    known = modules()
    return {imp for imp, _ in REEXPORT_SHIMS
            if imp in known and _import_only(_parse(known[imp]))}


def violations():
    """(rule, importer, imported) for every import that breaks a rule and
    is not allowlisted, and the set of allowlisted edges seen."""
    bad, seen = [], set()
    shims = shim_modules()
    for name, deps in sorted(edges().items()):
        layer = _layer(name)
        for kind, dep in sorted(deps):
            if kind == 'toolkit':
                if layer in NO_TOOLKIT and name not in TOOLKIT_EXEMPT:
                    bad.append(('toolkit', name, dep))
                continue
            if (name, dep) in REEXPORT_SHIMS | ALLOWED_UPWARD:
                seen.add((name, dep))
                continue
            dl = _layer(dep)
            if layer in ('core', 'models') and dep in shims:
                bad.append(('bottom layer imports a shim', name, dep))
            elif layer == 'core' and dl in ABOVE_CORE:
                bad.append(('core imports services/solvers/output',
                            name, dep))
            elif layer == 'core' and dl != 'core':
                bad.append(('core imports upward', name, dep))
            elif layer == 'models' and dl not in ('core', 'models'):
                bad.append(('models imports upward', name, dep))
            elif layer == 'services' and dl in GUIS:
                bad.append(('services imports a GUI', name, dep))
            elif layer in ENGINES and dl in GUIS:
                bad.append(('engine imports a GUI', name, dep))
            elif layer in ENGINES and dl == 'services':
                if name in ENTRY_POINTS:
                    seen.add(('entry', name))
                else:
                    bad.append(('engine imports services', name, dep))
            elif (layer, dl) in (('ui', 'gui'), ('gui', 'ui')):
                bad.append(('ui/gui cross-import', name, dep))
    return bad, seen


def _only(rules):
    bad, _ = violations()
    return [v for v in bad if v[0] in rules]


def test_no_toolkit_below_the_gui():
    bad = _only({'toolkit'})
    assert not bad, f'GUI toolkit imported below the GUI layer: {bad}'


def test_core_imports_no_services_solvers_output():
    bad = _only({'core imports services/solvers/output'})
    assert not bad, f'core/ imports services/, solvers/ or output/: {bad}'


def test_core_imports_only_core():
    bad = _only({'core imports upward',
                 'core imports services/solvers/output'})
    assert not bad, f'core/ imports outside core/: {bad}'


def test_models_imports_only_core():
    bad = _only({'models imports upward'})
    assert not bad, f'models/ imports outside core/ and models/: {bad}'


def test_bottom_layers_do_not_import_through_a_shim():
    bad = _only({'bottom layer imports a shim'})
    assert not bad, (f'core/ or models/ imports a re-export shim - name '
                     f'the real module instead: {bad}')


def test_services_import_no_gui():
    bad = _only({'services imports a GUI'})
    assert not bad, f'services/ imports ui/ or gui/: {bad}'


def test_engines_import_no_gui_and_no_services():
    bad = _only({'engine imports a GUI', 'engine imports services'})
    assert not bad, (f'solvers/, output/ or viz3d/ import a GUI package, '
                     f'or services/ outside ENTRY_POINTS: {bad}')


def test_ui_and_gui_do_not_import_each_other():
    bad = _only({'ui/gui cross-import'})
    assert not bad, f'Qt and Tk GUIs import each other: {bad}'


def test_foam_runloop_does_not_import_backend():
    deps = edges()
    for mod in ('solvers.foam.runloop', 'solvers.foam.common'):
        assert ('pkg', 'solvers.foam.backend') not in deps[mod], (
            f'{mod} imports solvers.foam.backend: the backend <-> '
            f'runloop cycle is back')


def test_allowlists_are_current():
    _, seen = violations()
    stale = sorted((REEXPORT_SHIMS | ALLOWED_UPWARD) - seen)
    assert not stale, f'allowlisted edges that are gone - delete them: {stale}'
    stale = sorted(e for e in ENTRY_POINTS if ('entry', e) not in seen)
    assert not stale, (f'ENTRY_POINTS that no longer import services/ - '
                       f'delete them: {stale}')


def test_reexport_shims_are_pure():
    """Every REEXPORT_SHIMS edge only re-exports: a star import sits in a
    module of nothing but imports, and no explicitly imported name is
    used by the importing module's own code."""
    known = modules()
    impure = []
    for imp, target in sorted(REEXPORT_SHIMS):
        tree = _parse(known[imp])
        bound, star = set(), False
        for _node, a, kind, dep in _resolved(imp, known[imp], known, tree):
            if kind == 'pkg' and dep == target:
                if a.name == '*':
                    star = True
                else:
                    bound.add(a.asname or a.name)
        if star and not _import_only(tree):
            impure.append((imp, target, 'star import in a module with code'))
        used = {n.id for n in ast.walk(tree)
                if isinstance(n, ast.Name) and n.id in bound}
        if used:
            impure.append((imp, target, sorted(used)))
    assert not impure, f're-export shims whose names are used: {impure}'


def test_scan_sees_the_package():
    """Guard against a scan that silently finds nothing."""
    known = modules()
    for mod in ('core.case', 'solvers.foam.env', 'ui.app', 'gui.app',
                'viz3d.viewer', 'output.gauge_summary', 'models.case',
                'models.result', 'models.hd13_case', 'services.validation',
                'services.chain', 'services.foam_runs',
                'solvers.foam.common', 'output.cli_hd13'):
        assert mod in known, f'{mod} not found under {PKG}'
    assert shim_modules() == {'core.case', 'core.chain'}, shim_modules()


def main():
    fails = []
    for fn in (test_scan_sees_the_package, test_no_toolkit_below_the_gui,
               test_core_imports_no_services_solvers_output,
               test_core_imports_only_core,
               test_models_imports_only_core,
               test_bottom_layers_do_not_import_through_a_shim,
               test_services_import_no_gui,
               test_engines_import_no_gui_and_no_services,
               test_ui_and_gui_do_not_import_each_other,
               test_foam_runloop_does_not_import_backend,
               test_allowlists_are_current,
               test_reexport_shims_are_pure):
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
