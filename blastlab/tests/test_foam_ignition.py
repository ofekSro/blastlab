"""P1-23 / P2-22: the ignition seed blastFoam is handed at t = 0.

blastFoam lights a detonation point by testing cell CENTRES,
`mag(C - pt) < radius` (guide 5.6.1, p. 71, `radii`; the installed
`activationModel.C:111-137`), and dies at start-up with "No cells will
be activated" when none passes. These checks pin what the writer seeds
today on the three cases that died at t = 0 on 2026-10-11:

  P1-23  axisymmetric 10 x 10 m, 0.04 m cell, 100 kg C4 at (0, 0), zones
         level 1 + level 2 (`/root/blastlab_runs/20261011-081913_2d_p61324-00`)
  F05    planar 4 x 4 m, 0.1 m cell, AMR 3, 100 kg/m TNT at (2, 2)
  F06    3D 1.5 m cube, 0.05 m cell, AMR 2, 20 kg TNT at the centre
         (the two GUI-14 QA cases, `_qa_ui_harness.py` F2D_AMR / F3D_AMR)

The golden `radii` lines are pinned byte for byte by test_foam_writer.py
and are not pinned twice here. Pure text - no WSL.

Run:  cd blastlab/tests && python test_foam_ignition.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import Case2D, Case3D                  # noqa: E402
from blastlab.solvers.foam import writer                       # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def p123_case(**kw):
    """The P1-23 case as its case.json has it (t_end aside)."""
    base = dict(
        geometry='axisymmetric', Lx=10.0, Ly=10.0, cell_size_m=0.04,
        charge=100.0, center=(0.0, 0.0),
        bcs=dict(x_lo='reflect', x_hi='terminate', y_lo='reflect',
                 y_hi='transmit'),
        obstacles=[(5.0, 5.5, 0.0, 4.0), (7.5, 10.0, 0.0, 10.0)],
        refine_zones=[(0.0, 7.5, 0.0, 6.0, 1), (3.5, 7.5, 0.1, 5.9, 2)],
        charge_refine='zone', n_snapshots=6,
        gauges=[(7.49, y) for y in (0.1, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0,
                                    6.0)],
        solver='blastfoam', material='C4')
    base.update(kw)
    return Case2D(**base)


def f05_case(**kw):
    """`_qa_ui_harness.py` F2D_AMR."""
    base = dict(
        geometry='planar', Lx=4.0, Ly=4.0, cell_size_m=0.1, charge=100.0,
        center=(2.0, 2.0), gauges=[(3.2, 2.0)], n_snapshots=2,
        record_frames=60, solver='blastfoam', material='TNT', amr_levels=3,
        bcs=dict(x_lo='terminate', x_hi='terminate', y_lo='terminate',
                 y_hi='terminate'))
    base.update(kw)
    return Case2D(**base)


def f06_case(**kw):
    """`_qa_ui_harness.py` F3D_AMR."""
    base = dict(
        Lx=1.5, Ly=1.5, Lz=1.5, cell_size_m=0.05, charge=20.0,
        center=(0.75, 0.75, 0.75), gauges=[(1.25, 0.75, 0.75)],
        amr_levels=2, amr_display_level=1, amr_max_cells=150_000,
        n_snapshots=2, record_frames=30, solver='blastfoam', material='TNT',
        bcs={s: 'terminate' for s in ('x_lo', 'x_hi', 'y_lo', 'y_hi',
                                      'z_lo', 'z_hi')})
    base.update(kw)
    return Case3D(**base)


def written_radii(spec):
    """The `radii` list of the rendered phaseProperties, in metres."""
    m = re.search(r'^\s*radii \(([^)]*)\);',
                  spec.files['constant/phaseProperties'], re.M)
    return [float(v) for v in m.group(1).split()] if m else None


def seed_checks():
    """A1: today's written radius and charge spacing, before any change."""
    print("\nA1 - the seed as written today")
    for name, case, want in (('P1-23', p123_case(), 0.009),
                             ('F05', f05_case(), 0.01125),
                             ('F06', f06_case(), 0.01125)):
        spec = writer.render_case(case)
        r = written_radii(spec)
        check(f'{name}: one radius of {want * 1e3:g} mm is written',
              r is not None and len(r) == 1 and abs(r[0] - want) < 1e-12,
              f'{r}')
    sp = writer.render_case(p123_case())
    check('P1-23: the charge spacing is the global fine cell, 0.01 m',
          abs(sp.dx_charge - 0.01) < 1e-12, f'{sp.dx_charge}')


def main():
    seed_checks()
    print()
    if FAIL:
        print(f"FOAM IGNITION: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM IGNITION: PASS")


if __name__ == '__main__':
    main()
