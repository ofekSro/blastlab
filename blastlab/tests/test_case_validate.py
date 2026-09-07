"""validate_case cell-cap gating per solver backend (no WSL needed -
the env probe is never started by validate_case itself)."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import Case2D, Case3D, validate_case          # noqa: E402
from blastlab.core.constants import (CELLS_REFUSE, FOAM_CELLS_WARN,   # noqa: E402
                                     FOAM_CELLS_REFUSE)

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def cells_err(rep):
    return [e for e in rep.errors if 'cells exceeds' in e]


def amr_cap_checks():
    """N16: AMR caps apply to maxCells (the mesh grows) and to the
    display grid, never to the t=0 base count."""
    amr = dict(Lx=4.0, Ly=4.0, Lz=4.0, cell_size_m=0.1, charge=8.0,
               center=(2.0, 2.0, 2.0), solver='blastfoam', amr_levels=4)
    rep = validate_case(Case3D(**amr))
    check('amr: 64k base cells, no cell-cap error, display level auto = 2',
          not cells_err(rep) and not rep.errors and rep.display_level == 2
          and rep.n_cells == 64_000, f'{rep.errors} {rep.display_level}')
    rep = validate_case(Case3D(amr_max_cells=FOAM_CELLS_REFUSE + 1, **amr))
    check('amr: maxCells above the blastFoam cap refused',
          any('AMR max cells' in e for e in rep.errors), str(rep.errors))
    rep = validate_case(Case3D(amr_max_cells=FOAM_CELLS_WARN + 1, **amr))
    check('amr: maxCells above the warn level warned',
          any('AMR may grow' in w for w in rep.warnings), str(rep.warnings))
    rep = validate_case(Case3D(amr_display_level=4, **amr))
    check('amr: display grid over the 3D cap refused with the AMR hint',
          any('lower the AMR display level' in e for e in rep.errors),
          str(rep.errors))
    rep = validate_case(Case3D(solver='native', Lx=4.0, Ly=4.0, Lz=4.0,
                               cell_size_m=0.1, charge=8.0,
                               center=(2.0, 2.0, 2.0), amr_levels=2))
    check('amr on the native solver refused',
          any('AMR' in e for e in rep.errors), str(rep.errors))


def chain_stage_checks():
    """B5: an auto-wired chain must be validated per stage BEFORE it
    starts - a foam stage fed by a profile used to reach the backend and
    die there with a traceback."""
    from blastlab.gui.chain_panel import stage_errors
    from blastlab.core.case import Case1D

    def wired(solver2):
        """The 1D -> 2D wiring ChainPanel._run performs."""
        c1 = Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.02,
                    profile_file='p1.txt')
        c2 = Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                    cell_size_m=0.02, charge=1.0, center=(0.0, 1.0),
                    solver=solver2, init_mode='profile1d',
                    profile_file_in='p1.txt')
        return [1, 2], {1: c1, 2: c2}

    errs = stage_errors(*wired('blastfoam'))
    check('chain: foam stage fed by a profile is refused',
          bool(errs), str(errs))
    check('chain: the refusal names the stage and points at N7',
          any(e.startswith('Stage 2 (2D):') and 'ROADMAP N7' in e
              for e in errs), str(errs))
    check('chain: no duplicate generic profile-init error',
          sum('rofile' in e for e in errs) == 1, str(errs))

    check('chain: the same wiring is fine on the native solver',
          stage_errors(*wired('native')) == [],
          str(stage_errors(*wired('native'))))

    # the pending-input waiver must stay narrow: outside a chain a
    # missing profile is still an error, and it waives nothing else
    lone = Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                  cell_size_m=0.02, charge=1.0, center=(0.0, 1.0),
                  init_mode='profile1d', profile_file_in='nope.txt')
    check('missing profile refused by default',
          any('not found' in e for e in validate_case(lone).errors))
    check('pending_inputs waives only the existence check',
          not any('not found' in e for e in
                  validate_case(lone, pending_inputs=True).errors))
    check('pending_inputs does not waive a missing filename',
          any('required for remap' in e for e in validate_case(
              Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                     cell_size_m=0.02, charge=1.0, center=(0.0, 1.0),
                     init_mode='profile1d', profile_file_in=''),
              pending_inputs=True).errors))

    # ordinary per-stage errors are surfaced too, stage-prefixed
    stages, cases = wired('native')
    cases[2] = Case2D(geometry='axisymmetric', Lx=40.0, Ly=40.0,
                      cell_size_m=0.002, charge=1000.0,
                      center=(0.0, 20.0), solver='native')
    errs = stage_errors(stages, cases)
    check('chain: a plain validation error is stage-prefixed',
          bool(errs) and all(e.startswith('Stage ') for e in errs),
          str(errs))


def shared_constant_checks():
    """A5: validate_case and the solvers must gate on the SAME numbers.

    MIN_EXP_CELLS and the 2D caps used to be re-typed as literals in
    solver1d/2d/3d, so the strip could accept a case the solver then
    refused (or the other way round) after any edit to constants.py.
    """
    import inspect
    from blastlab.core import constants
    from blastlab.core import case as case_mod
    from blastlab.solvers import solver1d, solver2d, solver3d

    print("")
    print("A5: guard-rail constants are shared, not re-typed")
    for name in ('MIN_EXP_CELLS', 'CELLS_2D_WARN', 'CELLS_2D_MAX',
                 'CELLS_WARN', 'CELLS_REFUSE'):
        want = getattr(constants, name)
        check(f'{name} reaches validate_case unchanged',
              getattr(case_mod, name, None) == want)
    for mod, names in ((solver1d, ('MIN_EXP_CELLS',)),
                       (solver2d, ('MIN_EXP_CELLS', 'CELLS_2D_WARN',
                                   'CELLS_2D_MAX')),
                       (solver3d, ('MIN_EXP_CELLS', 'CELLS_WARN',
                                   'CELLS_REFUSE'))):
        for name in names:
            check(f'{mod.__name__.split(".")[-1]} uses '
                  f'constants.{name}',
                  getattr(mod, name, None) == getattr(constants, name))
        src = inspect.getsource(mod)
        check(f'{mod.__name__.split(".")[-1]} has no re-typed '
              f'MIN_EXP_CELLS literal', 'MIN_EXP_CELLS = ' not in src)
    src2 = inspect.getsource(solver2d)
    check('solver2d has no re-typed 2D cap literals',
          '8_000_000' not in src2 and '2_000_000' not in src2)


def main():
    # ~64M cells: 40 m cube at 0.1 m with a large charge (no refine)
    big3 = dict(Lx=40.0, Ly=40.0, Lz=40.0, cell_size_m=0.1,
                charge=1000.0, center=(20.0, 20.0, 20.0))

    # T1: native 3D refuses above CELLS_REFUSE
    rep = validate_case(Case3D(solver='native', **big3))
    check('native 3D big refused', bool(cells_err(rep)),
          f'errors={rep.errors}')
    check('native cap constant sane', rep.n_cells > CELLS_REFUSE)

    # T2: same grid on blastfoam is allowed (warn only)
    rep = validate_case(Case3D(solver='blastfoam', **big3))
    check('foam 3D big allowed', not cells_err(rep),
          f'errors={rep.errors}')
    check('foam 3D big warns', any('Large grid' in w for w in rep.warnings)
          and rep.n_cells > FOAM_CELLS_WARN)

    # T3: blastfoam still refuses beyond its own (much higher) cap
    huge3 = dict(big3, cell_size_m=0.05)          # ~512M cells
    rep = validate_case(Case3D(solver='blastfoam', **huge3))
    check('foam 3D huge refused', bool(cells_err(rep)))
    check('foam refuse names its cap',
          any(f'{FOAM_CELLS_REFUSE:,}' in e for e in cells_err(rep)))

    # T4: 2D - grid over the native 8M cap allowed on blastfoam
    big2 = dict(geometry='planar', Lx=80.0, Ly=80.0, cell_size_m=0.025,
                charge=1000.0, center=(40.0, 40.0))   # ~10.2M cells
    rep = validate_case(Case2D(solver='native', **big2))
    check('native 2D big refused', bool(cells_err(rep)))
    rep = validate_case(Case2D(solver='blastfoam', **big2))
    check('foam 2D big allowed', not cells_err(rep),
          f'errors={rep.errors}')

    # T6: obstacles on blastfoam - allowed in 3D, refused in 2D
    small3 = dict(Lx=5.0, Ly=5.0, Lz=5.0, cell_size_m=0.1,
                  charge=100.0, center=(2.5, 2.5, 2.5))
    rep = validate_case(Case3D(solver='blastfoam',
                               obstacles=[(3.5, 4.0, 2.0, 3.0, 0.0, 2.0)],
                               **small3))
    check('foam 3D obstacle allowed',
          not any('Obstacle' in e for e in rep.errors),
          f'errors={rep.errors}')
    check('foam 3D obstacle noted',
          any('carved out of the mesh' in n for n in rep.notes))
    rep = validate_case(Case2D(solver='blastfoam', geometry='planar',
                               Lx=5.0, Ly=5.0, cell_size_m=0.1,
                               charge=10.0, center=(2.5, 2.5),
                               obstacles=[(3.5, 4.0, 2.0, 3.0)]))
    check('foam 2D obstacle allowed',
          not any('Obstacle' in e for e in rep.errors)
          and any('carved out of the mesh' in n for n in rep.notes),
          f'errors={rep.errors}')
    rep = validate_case(Case3D(solver='blastfoam',
                               obstacles=[(2.4, 3.0, 2.4, 3.0, 2.4, 3.0)],
                               **small3))
    check('foam 3D charge-overlap still refused',
          any('overlaps obstacle' in e for e in rep.errors),
          f'errors={rep.errors}')

    # T5: small case unaffected on both backends (100 kg -> r_exp 0.245,
    # refined dx 0.049 -> ~1.1M cells, under every warn threshold)
    small = dict(Lx=5.0, Ly=5.0, Lz=5.0, cell_size_m=0.1,
                 charge=100.0, center=(2.5, 2.5, 2.5))
    for solver in ('native', 'blastfoam'):
        rep = validate_case(Case3D(solver=solver, **small))
        check(f'{solver} small clean', not cells_err(rep)
              and not any('Large grid' in w for w in rep.warnings))

    chain_stage_checks()
    shared_constant_checks()
    amr_cap_checks()

    print()
    if FAIL:
        print(f"CASE VALIDATE: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("CASE VALIDATE: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
