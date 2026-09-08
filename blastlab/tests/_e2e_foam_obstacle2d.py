"""Manual E2E: 2D blastFoam runs with an obstacle, on both 2D
geometries. Verifies the topoSet/subsetMesh carve against the real WSL
install - the axisym wedge is the risky one (boxToCell judges true
wedge-cell centres, which sit slightly off the uniform x_c):

  - field read-back count AND cell order (solid positions must read
    exactly ambient),
  - solid/obstacles meta wiring + revolve rings for the 3D view,
  - a pressure shadow behind the wall.

Run:  python _e2e_foam_obstacle2d.py [axi|planar|both]
      (default both; planar ~5 min, axisym ~30 min wall)
Auto-SKIPs when WSL/blastFoam is unavailable.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.case import Case2D, validate_case           # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def run_case(name, case, box):
    rep = validate_case(case)
    check(f'{name}: validate ok', rep.ok, str(rep.errors))
    if not rep.ok:
        return
    from blastlab.solvers import get_solver
    res = get_solver(2, 'blastfoam')(case)
    m = res.meta
    solid = m['solid']
    check(f'{name}: solid mask carved', solid.any(),
          f'{int(solid.sum())} solid cells')
    check(f'{name}: obstacles in meta', m['obstacles'] == [box],
          str(m['obstacles']))
    p_fin = list(res.snapshots.values())[-1]['p'].astype(np.float64)
    check(f'{name}: solid cells read back ambient',
          np.allclose(p_fin[solid], P_AIR),
          f'{p_fin[solid].min():.0f}..{p_fin[solid].max():.0f} Pa')
    xc, yc = m['x_c'], m['y_c']
    j = int(np.argmin(np.abs(yc - 0.5 * (box[2] + box[3]))))
    pk = m.get('p_peak')
    if pk is None:
        pk = p_fin
    p_b = pk[int(np.argmin(np.abs(xc - (box[1] + 0.3)))), j] - P_AIR
    p_f = pk[int(np.argmin(np.abs(xc - (box[0] - 0.3)))), j] - P_AIR
    check(f'{name}: pressure shadow behind the wall', p_b < p_f,
          f'{p_b/1e3:.0f} vs {p_f/1e3:.0f} kPa')
    fr = m.get('frames')
    check(f'{name}: frames recorded', bool(fr) and len(fr['times']) >= 3)
    return res


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM OBSTACLE 2D: SKIP")
        return
    which = sys.argv[1] if len(sys.argv) > 1 else 'both'

    if which in ('axi', 'both'):
        # ground burst, ring wall at r = 2.0..2.2 m, height 1 m
        box = (2.0, 2.2, 0.0, 1.0)
        case = Case2D(Lx=4.0, Ly=3.0, cell_size_m=0.04, charge=2.0,
                      center=(0.0, 0.0), obstacles=[box],
                      bcs=dict(x_lo='reflect', x_hi='terminate',
                               y_lo='reflect', y_hi='terminate'),
                      gauges=[(1.0, 0.5)], n_snapshots=3,
                      record_frames=40,
                      solver='blastfoam', material='TNT')
        res = run_case('axisym', case, box)
        if res is not None:
            # the revolved 3D view must carry the ring
            from blastlab.viz3d.sampling import Revolver
            rev = Revolver(dict(
                r_c=res.meta['x_c'], z_c=res.meta['y_c'],
                solid=res.meta['solid'], bcs=res.meta['bcs'],
                obstacles=res.meta['obstacles'],
                z0=0.0, r_exp=res.meta['r_exp'], R=4.0, Lz=3.0))
            check('axisym: revolve ring for the 3D view',
                  rev.scene3d['rings'] == [box],
                  str(rev.scene3d['rings']))

    if which in ('planar', 'both'):
        # slab wall between the charge and x_hi
        box = (1.6, 1.7, 0.0, 0.8)
        case = Case2D(geometry='planar', Lx=2.4, Ly=1.6,
                      cell_size_m=0.04, charge=20.0, center=(0.6, 0.0),
                      obstacles=[box],
                      bcs=dict(x_lo='reflect', x_hi='terminate',
                               y_lo='reflect', y_hi='terminate'),
                      gauges=[(1.2, 0.4)], n_snapshots=3,
                      record_frames=40,
                      solver='blastfoam', material='TNT')
        run_case('planar', case, box)

    print()
    if FAIL:
        print(f"FOAM OBSTACLE 2D: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM OBSTACLE 2D: PASS")


if __name__ == '__main__':
    main()
