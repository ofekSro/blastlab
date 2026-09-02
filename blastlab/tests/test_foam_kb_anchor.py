"""Absolute anchoring of the blastFoam backend against literature:

1. Kingery-Bulmash free-air incident peak overpressure at scaled
   distances Z = R / W^(1/3): a 1 kg TNT sphere in a 5 m domain,
   gauges at 1/2/3/4 m. Gate is a WIDE band (ratio 0.65-1.35): a pure
   hydro code (JWL products, no afterburn) at this resolution is known
   to land ~20-30% below KB in the near/mid field - what we pin is
   "the right decade and the right decay", not the last percent.
2. Multi-material spot check: the same case with C4 must give peaks
   ~1.1-1.5x the TNT ones (higher detonation energy and pressure).

Auto-SKIPs without WSL. Wall ~2 min (two 1D runs).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.case import Case1D                          # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402

FAIL = []

#: Kingery-Bulmash free-air incident peak overpressure [kPa] at
#: Z = R/W^(1/3) [m/kg^(1/3)] (standard KB polynomial values)
KB_FREE_AIR = {1.0: 904.0, 2.0: 186.0, 3.0: 80.0, 4.0: 47.0}
KB_BAND = (0.65, 1.35)
C4_OVER_TNT = (1.1, 1.5)


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def _run(material):
    from blastlab.solvers import get_solver
    case = Case1D(radius_m=5.0, charge_kg=1.0, cell_size_m=0.02,
                  gauge_radii=sorted(KB_FREE_AIR), n_snapshots=2,
                  solver='blastfoam', material=material)
    return get_solver(1, 'blastfoam')(case)


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM KB ANCHOR: SKIP")
        return

    print('--- TNT run ---')
    tnt = _run('TNT')
    peaks_tnt = {}
    for r_g, p_arr in zip(tnt.gauges['radii'], tnt.gauges['pressures']):
        z = round(r_g)
        peaks_tnt[z] = (p_arr.max() - P_AIR) / 1e3       # kPa overpressure

    for z, kb in sorted(KB_FREE_AIR.items()):
        got = peaks_tnt.get(int(z))
        ratio = got / kb if got else 0.0
        check(f'KB anchor at Z = {z:g}',
              got is not None and KB_BAND[0] <= ratio <= KB_BAND[1],
              f'foam {got:.0f} kPa vs KB {kb:.0f} kPa '
              f'(ratio {ratio:.2f})')

    zs = sorted(KB_FREE_AIR)
    check('decay follows KB ordering',
          all(peaks_tnt[int(a)] > peaks_tnt[int(b)]
              for a, b in zip(zs, zs[1:])))

    print('--- C4 run ---')
    c4 = _run('C4')
    peaks_c4 = {}
    for r_g, p_arr in zip(c4.gauges['radii'], c4.gauges['pressures']):
        peaks_c4[round(r_g)] = (p_arr.max() - P_AIR) / 1e3

    for z in (1, 2, 3):
        ratio = peaks_c4[z] / peaks_tnt[z]
        check(f'C4/TNT peak ratio at Z = {z}',
              C4_OVER_TNT[0] <= ratio <= C4_OVER_TNT[1],
              f'{ratio:.2f} (C4 {peaks_c4[z]:.0f} / '
              f'TNT {peaks_tnt[z]:.0f} kPa)')

    print()
    if FAIL:
        print(f"FOAM KB ANCHOR: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM KB ANCHOR: PASS")


if __name__ == '__main__':
    main()
