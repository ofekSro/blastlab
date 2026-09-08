"""2D blastFoam backend: axisymmetric native-vs-foam spot comparison
(looser gates than 1D - different schemes AND wedge vs r-z metrics)
plus a planar smoke run. Auto-SKIPs without WSL. Wall ~2-3 min.

Case: 8 kg TNT on the axis at height 1.25 m in a 2.5 x 2.5 m domain
(ground wall below); gauges inside the shock-arrival stop distance.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.case import Case2D                          # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402

#: T50: the pre-T50 solver default - every side lets the wave out
#: AND ends the run when it arrives (the plain 'transmit'
#: default would run this to the safety cap).
ALL_TERM = dict(x_lo='terminate', x_hi='terminate',
                y_lo='terminate', y_hi='terminate')

FAIL = []
GAUGES = [(0.6, 1.25), (1.0, 1.25)]
PEAK_RATIO = (0.5, 2.0)
# Arrival gate is wide because these gauges are extreme near field
# (1.1x and 1.9x the source radius): the native solver detonates the
# whole charge instantly while blastFoam's linear activation model
# burns it at vDet, so foam arrivals lag by a few tens of us - a large
# RELATIVE error only this close in (the 1D far-field test pins the
# same physics to within 3-11%).
ARRIVAL_TOL = 0.45


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def _axi_case(solver):
    return Case2D(Lx=2.5, Ly=2.5, cell_size_m=0.025, charge=8.0,
                  center=(0.0, 1.25), gauges=list(GAUGES),
                  n_snapshots=4, record_frames=100, eos='JWL',
                  solver=solver, material='TNT', bcs=ALL_TERM)


def _arrival(times, p):
    idx = np.nonzero(p > 1.1 * P_AIR)[0]
    return float(times[idx[0]]) if len(idx) else np.inf


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM 2D: SKIP")
        return

    from blastlab.solvers import get_solver
    print("--- native axisymmetric run ---")
    nat = get_solver(2, 'native')(_axi_case('native'))
    print("--- blastFoam axisymmetric run ---")
    foam = get_solver(2, 'blastfoam')(_axi_case('blastfoam'))

    check('foam stopped via arrival watcher',
          foam.stop_reason.startswith('shock arrived'), foam.stop_reason)
    for i, (gx, gy) in enumerate(GAUGES):
        pn = nat.gauges['pressures'][i]
        pf = foam.gauges['pressures'][i]
        peak_n = pn.max() - P_AIR
        peak_f = pf.max() - P_AIR
        ratio = peak_f / peak_n
        check(f'peak ratio at ({gx:g},{gy:g})',
              PEAK_RATIO[0] <= ratio <= PEAK_RATIO[1],
              f'native {peak_n/1e3:.0f} kPa, foam {peak_f/1e3:.0f} kPa, '
              f'ratio {ratio:.2f}')
        ta_n = _arrival(nat.gauges['times'], pn)
        ta_f = _arrival(foam.gauges['times'], pf)
        rel = abs(ta_f - ta_n) / ta_n
        check(f'arrival at ({gx:g},{gy:g})', rel <= ARRIVAL_TOL,
              f'native {ta_n*1e3:.3f} ms, foam {ta_f*1e3:.3f} ms, '
              f'diff {rel*100:.1f}%')

    # contract: snapshots {p,rho,speed}, meta incl. final_state
    snap = foam.snapshots[list(foam.snapshots)[-1]]
    # foam resolves the charge with 8 cells across the radius (T39),
    # native with 5, so the two grids no longer share a shape - the
    # contract is that the snapshot matches the FOAM run's own grid
    check('axi snapshot contract', set(snap) == {'p', 'rho', 'speed'}
          and snap['p'].shape == (len(foam.meta['x_c']),
                                  len(foam.meta['y_c'])))
    # T44/N12: a foam run records |U| and rho gauge traces alongside p
    check('axi gauge extras recorded (T44: speeds + rhos)',
          'speeds' in foam.gauges and 'rhos' in foam.gauges
          and len(foam.gauges['speeds']) == len(GAUGES)
          and all(len(sp) == len(foam.gauges['times'])
                  for sp in foam.gauges['speeds'])
          and max(sp.max() for sp in foam.gauges['speeds']) > 50.0)
    fs = foam.meta['final_state']
    check('axi final_state contract',
          set(fs) == {'t', 'rho', 'u', 'v', 'e', 'p', 'phase'}
          and fs['phase'].dtype.kind == 'i'
          and foam.meta['geometry'] == 'axisymmetric'
          and foam.meta['from_profile'] is False)
    fr = foam.meta['frames']
    check('axi frames whole-field',
          fr['pressures'][0].shape == snap['p'].shape
          and fr['pressures'][0].dtype == np.float32)

    # save_profile_2d must accept the foam final_state (3D remap path)
    import tempfile
    from blastlab.core.profiles import save_profile_2d, load_profile_2d
    fd, path = tempfile.mkstemp(suffix='.npz')
    os.close(fd)
    try:
        save_profile_2d(foam.meta, path)
        prof = load_profile_2d(path)
        check('axi profile export round-trips', prof is not None)
    finally:
        os.unlink(path)

    # planar smoke: geometric cylinder charge, one gauge in range
    print("--- blastFoam planar run ---")
    planar = Case2D(geometry='planar', Lx=2.0, Ly=2.0,
                    cell_size_m=0.025, charge=50.0, center=(1.0, 1.0),
                    gauges=[(0.5, 1.0)], n_snapshots=3,
                    record_frames=50, solver='blastfoam',
                    material='TNT', bcs=ALL_TERM)
    resp = get_solver(2, 'blastfoam')(planar)
    check('planar arrival stop',
          resp.stop_reason.startswith('shock arrived'), resp.stop_reason)
    pg = resp.gauges['pressures'][0]
    check('planar gauge shocked', pg.max() > 2 * P_AIR,
          f'{(pg.max()-P_AIR)/1e3:.0f} kPa')
    check('planar meta geometry',
          resp.meta['geometry'] == 'planar'
          and resp.snapshots[list(resp.snapshots)[-1]]['p'].shape
          == (len(resp.meta['x_c']), len(resp.meta['y_c'])))

    print()
    if FAIL:
        print(f"FOAM 2D: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM 2D: PASS")


if __name__ == '__main__':
    main()
