"""Physics comparison: blastFoam 1D backend vs the native 1D solver on
the same case (1 kg TNT, R = 5 m, dx auto-refined to ~0.0105 m,
gauges at 1/2/3/4 m).

Different codes, schemes (Kurganov+RK2SSP vs Godunov+HLL) and EOS
treatment (two-phase JWL products vs fixed-phase JWL), so the gates are
tolerance bands, not byte equality:
  - per-gauge peak-overpressure ratio foam/native in [0.65, 1.5]
  - per-gauge arrival time (first crossing of 1.1*P_AIR) within 15 %
  - peaks strictly decreasing with radius in BOTH codes
  - the foam run must stop via the shock-arrival watcher, not the cap

Auto-SKIPs when WSL/blastFoam is unavailable. Wall time ~1 min.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.case import Case1D                          # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402

FAIL = []
GAUGES = [1.0, 2.0, 3.0, 4.0]
PEAK_RATIO = (0.65, 1.5)
ARRIVAL_TOL = 0.15


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def _case(solver):
    # --order2 (T47/N10) runs the NATIVE side with MUSCL; foam is
    # unaffected, so the gates measure how much closer the two get
    order = 2 if '--order2' in sys.argv and solver == 'native' else 1
    return Case1D(radius_m=5.0, charge_kg=1.0, cell_size_m=0.02,
                  gauge_radii=list(GAUGES), n_snapshots=3,
                  solver=solver, material='TNT', eos='JWL',
                  order=order)


def _arrival(times, p):
    idx = np.nonzero(p > 1.1 * P_AIR)[0]
    return float(times[idx[0]]) if len(idx) else np.inf


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM 1D VS NATIVE: SKIP")
        return

    from blastlab.solvers import get_solver
    print("--- native run ---")
    nat = get_solver(1, 'native')(_case('native'))
    print("--- blastFoam run ---")
    foam = get_solver(1, 'blastfoam')(_case('blastfoam'))

    check('foam stopped via arrival watcher',
          foam.stop_reason.startswith('shock arrived'),
          foam.stop_reason)
    check('gauge counts match',
          len(nat.gauges['radii']) == len(foam.gauges['radii']) == 4)

    nat_peaks, foam_peaks = [], []
    for i, g in enumerate(GAUGES):
        pn = nat.gauges['pressures'][i]
        pf = foam.gauges['pressures'][i]
        peak_n = pn.max() - P_AIR
        peak_f = pf.max() - P_AIR
        nat_peaks.append(peak_n)
        foam_peaks.append(peak_f)
        ratio = peak_f / peak_n
        check(f'peak ratio at r={g:g} m',
              PEAK_RATIO[0] <= ratio <= PEAK_RATIO[1],
              f'native {peak_n/1e3:.0f} kPa, foam {peak_f/1e3:.0f} kPa, '
              f'ratio {ratio:.2f}')
        ta_n = _arrival(nat.gauges['times'], pn)
        ta_f = _arrival(foam.gauges['times'], pf)
        rel = abs(ta_f - ta_n) / ta_n
        check(f'arrival at r={g:g} m',
              rel <= ARRIVAL_TOL,
              f'native {ta_n*1e3:.3f} ms, foam {ta_f*1e3:.3f} ms, '
              f'diff {rel*100:.1f}%')
    check('native peaks decay monotonically',
          all(a > b for a, b in zip(nat_peaks, nat_peaks[1:])))
    check('foam peaks decay monotonically',
          all(a > b for a, b in zip(foam_peaks, foam_peaks[1:])))

    # Result-contract spot checks (shapes the GUI/exports rely on)
    fp = foam.meta['final_profile']
    # The foam and native grids no longer have the same cell count: the
    # native rule keeps 5 cells across the charge radius (byte-pinned)
    # while blastFoam asks for 8 (T39), so only the profile's own arrays
    # have to agree in length.
    check('final_profile contract',
          sorted(fp) == sorted(('t', 'r', 'rho', 'u', 'e', 'p', 'phase',
                                'charge_kg', 'eos', 'r_exp', 'radius_m',
                                # N5-4: which solver wrote it, so a
                                # blastFoam stage can refuse a native
                                # profile (the ideal-gas state would be
                                # re-priced through the JWL products EOS)
                                'source_solver'))
          and fp['source_solver'] == 'blastfoam'
          and fp['phase'].dtype.kind == 'i'
          and len({len(fp[k]) for k in ('r', 'p', 'rho', 'u', 'e',
                                        'phase')}) == 1,
          f"foam {len(fp['r'])} cells, native {len(nat.meta['r'])}")
    check('snapshot labels contract',
          list(foam.snapshots)[-1].endswith('(final)')
          and all(k.startswith('t = ') for k in foam.snapshots))

    print()
    if FAIL:
        print(f"FOAM 1D VS NATIVE: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM 1D VS NATIVE: PASS")


if __name__ == '__main__':
    main()
