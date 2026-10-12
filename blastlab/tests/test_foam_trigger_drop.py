"""P1-23 A5 (P1-24, Q2): blastFoam's trigger on a gauge the writer drops.

The writer drops a gauge outside the domain or in or ON a snapped wall
(foam/writer.py plan_case, the closed box test). blastFoam's T51 trigger
reads the pressure at the gauge's nearest display cell
(backend._trigger_cells) - measured here, in 2D and 3D, for a gauge
strictly inside the wall, exactly on its low face and exactly on its
high face:

  inside      the carved display cell, which holds the ambient fill, so
              the trigger never fires
  low face    an argmin tie: an exact one picks the lower index, the
              FLUID cell in front of the wall, so the trigger can fire
              (an inexact one goes by the centres' rounding)
  high face   the argmin tie picks the wall cell: never fires

"Never fires" is therefore false, and the owner chose parity with the
native solvers (Q2, 2026-10-12; D13 of GUI-15): with the writer's kept
list a trigger on a dropped gauge is disabled with hooks.trigger_index's
warn line, and validate_case says "Trigger disabled" for both solvers.

No WSL.  Run:  cd blastlab/tests && python test_foam_trigger_drop.py
"""

import dataclasses
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import Case2D, Case3D, validate_case   # noqa: E402
from blastlab.solvers.foam import backend, writer              # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


class _Hooks:
    def __init__(self):
        self.msgs = []

    def log(self, m):
        self.msgs.append(m)


def case_2d(**kw):
    """test_foam_writer's case2d_axi_obstacle: one wall, uniform grid."""
    return Case2D(Lx=4.0, Ly=4.0, cell_size_m=0.02, charge=1.0,
                  center=(0.0, 1.0), obstacles=[(2.0, 2.4, 0.0, 1.6)],
                  gauges=[(1.0, 1.0)], solver='blastfoam', material='TNT',
                  **kw)


def case_3d(**kw):
    """A small 3D AMR case shown at level 0 (a 16^3 display grid). The
    1/16 m cell makes every centre and face exact in binary, so a gauge
    on a face is an EXACT argmin tie and the lower index wins. On a
    0.05 m cell the same gauge sampled the wall instead: the tie is then
    broken by the centres' rounding, which is the erratic part."""
    return Case3D(Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.0625, charge=0.5,
                  center=(0.3, 0.5, 0.5), amr_levels=2, amr_display_level=0,
                  obstacles=[(0.625, 0.75, 0.3125, 0.6875, 0.0, 0.5625)],
                  gauges=[(0.9, 0.5, 0.5)], n_snapshots=2,
                  solver='blastfoam', material='TNT', **kw)


def with_gauges(make):
    """The case with G1 free, G2 inside the snapped wall, G3 on its low
    x face and G4 on its high x face, plus its rendered spec."""
    probe = writer.render_case(make())
    box = probe.obstacles[0]
    x0, x1 = box[0], box[1]
    mid = [0.5 * (box[2 * a] + box[2 * a + 1]) for a in range(probe.dim)]
    free = tuple(make().gauges[0])
    rest = tuple(mid[1:])
    gauges = [free, (mid[0],) + rest, (x0,) + rest, (x1,) + rest]
    case = dataclasses.replace(make(), gauges=gauges)
    return case, writer.render_case(case)


def trigger_checks(tag, make):
    case, spec = with_gauges(make)
    g = spec.grid
    keys = ('x_c', 'y_c', 'z_c')[:spec.dim]
    coords = tuple(g[k] for k in keys)
    shape = (spec.nx, spec.ny, spec.nz)[:spec.dim]
    solid = spec.solid
    print(f"\n{tag}: the writer keeps G1 only")
    check(f'{tag}: the kept list is G1 alone',
          [tuple(v) for v in spec.gauge_ids] == [tuple(case.gauges[0])],
          f'{spec.gauge_ids}')

    print(f"\n{tag}: the measurement (no kept list, as before A5)")
    cells = {}
    for n in (1, 2, 3, 4):
        k, cell = backend._trigger_cells(
            dataclasses.replace(case, trigger_gauge=n), coords, shape)
        cells[n] = cell
        check(f'{tag}: trigger G{n} is armed on a cell',
              k == n - 1 and cell is not None, f'{k} {cell}')
    check(f'{tag}: G1 (free air) samples a fluid cell',
          not solid[cells[1]])
    check(f'{tag}: G2 (inside the wall) samples a carved cell',
          bool(solid[cells[2]]))
    check(f'{tag}: G3 (on the low face) samples the FLUID cell in front '
          f'- it can fire', not solid[cells[3]])
    check(f'{tag}: G4 (on the high face) samples a carved cell',
          bool(solid[cells[4]]))

    print(f"\n{tag}: with the writer's kept list (A5)")
    for n in (2, 3, 4):
        h = _Hooks()
        got = backend._trigger_cells(
            dataclasses.replace(case, trigger_gauge=n), coords, shape,
            kept=spec.gauge_ids, hooks=h)
        check(f'{tag}: trigger G{n} (dropped) is disabled, with the '
              f'dropped warn line',
              got == (None, None) and len(h.msgs) == 1
              and f'Trigger gauge {n} was dropped' in h.msgs[0]
              and 'disabled' in h.msgs[0], f'{got} {h.msgs}')
    h = _Hooks()
    got = backend._trigger_cells(
        dataclasses.replace(case, trigger_gauge=1), coords, shape,
        kept=spec.gauge_ids, hooks=h)
    check(f'{tag}: trigger G1 (kept) keeps its cell, nothing logged',
          got == (0, cells[1]) and not h.msgs, f'{got} {h.msgs}')

    print(f"\n{tag}: validate_case")
    for n in (2, 3, 4):
        rep = validate_case(dataclasses.replace(case, trigger_gauge=n))
        warns = [w for w in rep.warnings if 'Trigger disabled' in w]
        check(f'{tag}: trigger G{n} warns "Trigger disabled", naming G{n}',
              len(warns) == 1 and f'G{n}' in warns[0], str(rep.warnings))
    rep = validate_case(dataclasses.replace(case, trigger_gauge=1))
    check(f'{tag}: trigger G1 gives no such warning',
          not any('Trigger disabled' in w for w in rep.warnings))


def main():
    trigger_checks('2D', case_2d)
    trigger_checks('3D', case_3d)
    print()
    if FAIL:
        print(f"FOAM TRIGGER DROP: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM TRIGGER DROP: PASS")


if __name__ == '__main__':
    main()
