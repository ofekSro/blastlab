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

    print()
    if FAIL:
        print(f"CASE VALIDATE: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("CASE VALIDATE: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
