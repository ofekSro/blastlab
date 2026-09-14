"""Manual E2E: 3D blastFoam run with one obstacle slab between the
charge and the +x face (tiny 0.6 m box, ~1 min wall). Verifies the
topoSet/subsetMesh carve against the real WSL install:

  - field read-back count AND cell order (solid positions must read
    exactly ambient - an order mismatch would scatter shocked values
    into mask positions),
  - solid/obstacles meta wiring,
  - live-slice decode with carved cells (recorded frames),
  - a pressure shadow behind the slab (with no carve the wave would
    pass straight through).

Run:  python _e2e_foam_obstacle3d.py [--np4]    (--np4 = 4 MPI ranks)
Auto-SKIPs when WSL/blastFoam is unavailable.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.case import Case3D, validate_case           # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402

#: T50: the pre-T50 3D solver default - terminating sides over a
#: reflecting ground.
ALL_TERM_3D = dict(x_lo='terminate', x_hi='terminate',
                   y_lo='terminate', y_hi='terminate',
                   z_lo='reflect', z_hi='terminate')

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM OBSTACLE 3D: SKIP")
        return

    L, c = 0.6, 0.3
    box = (0.42, 0.48, 0.15, 0.45, 0.15, 0.45)
    case = Case3D(Lx=L, Ly=L, Lz=L, cell_size_m=0.025,
                  charge=8.0, center=(c, c, c), obstacles=[box],
                  gauges=[(0.54, c, c),      # behind the slab
                          (0.06, c, c)],     # mirrored free side
                  n_snapshots=3, record_frames=50,
                  solver='blastfoam', material='TNT',
                  n_procs=4 if '--np4' in sys.argv else 1, bcs=ALL_TERM_3D)
    rep = validate_case(case)
    check('validate ok', rep.ok, str(rep.errors))
    if not rep.ok:
        sys.exit(1)

    from blastlab.solvers import get_solver
    res = get_solver(3, 'blastfoam')(case)

    m = res.meta
    solid = m['solid']
    check('solid mask carved', solid.any(),
          f'{int(solid.sum())} solid cells')
    # since the face-snap (4e97108) meta carries the box the mesh was
    # REALLY carved with - every edge moved outward onto a base-cell
    # face - not the raw case box
    from blastlab.core import refine as _refine
    from blastlab.core.case import material_rho0
    plan = _refine.plan_levels(case, rho0=material_rho0(case))
    exp_obs, _mv = _refine.snap_obstacles([box], plan.dx_base, 3)
    check('obstacles in meta are the face-snapped boxes',
          m['obstacles'] == [tuple(exp_obs[0])]
          and all((s <= o) if i % 2 == 0 else (s >= o)
                  for i, (s, o) in enumerate(zip(exp_obs[0], box))),
          f"meta {m['obstacles']} vs snapped {exp_obs}")

    labels = list(res.snapshots)
    p_fin = res.snapshots[labels[-1]]['p'].astype(np.float64)
    check('solid cells read back ambient',
          np.allclose(p_fin[solid], P_AIR),
          f'{p_fin[solid].min():.0f}..{p_fin[solid].max():.0f} Pa')
    check('fluid cells populated', (p_fin[~solid] > 0).all())

    pk = m['p_peak']
    xc, yc, zc = m['x_c'], m['y_c'], m['z_c']
    j = int(np.argmin(np.abs(yc - c)))
    k = int(np.argmin(np.abs(zc - c)))
    p_b = pk[int(np.argmin(np.abs(xc - 0.54))), j, k] - P_AIR
    p_f = pk[int(np.argmin(np.abs(xc - 0.06))), j, k] - P_AIR
    check('pressure shadow behind the slab', p_b < p_f,
          f'{p_b/1e3:.0f} vs {p_f/1e3:.0f} kPa')

    check('gauges recorded', len(res.gauges['points']) == 2
          and (np.diff(res.gauges['times']) > 0).all())
    fr = m.get('frames')
    check('live frames recorded', bool(fr) and len(fr['times']) >= 3,
          str(len(fr['times']) if fr else 0))

    print()
    if FAIL:
        print(f"FOAM OBSTACLE 3D: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM OBSTACLE 3D: PASS")
    print("  case dir:", m['case_dir'])


if __name__ == '__main__':
    main()
