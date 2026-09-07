"""Absolute anchoring of the blastFoam backend against literature:

1. Kingery-Bulmash free-air incident peak overpressure at scaled
   distances Z = R / W^(1/3): a 1 kg TNT sphere in a 5 m domain,
   gauges at 1/2/3/4 m. Gate is a WIDE band (ratio 0.65-1.35): a pure
   hydro code (JWL products, no afterburn) at this resolution lands
   below KB in the near/mid field - what we pin is "the right decade
   and the right decay", not the last percent. Measured 0.85-0.89 since
   the charge is resolved with 8 cells across its radius (T39); it was
   0.72-0.77 at the old 5-cell target.
2. Multi-material spot check: the same case with C4 must give peaks
   above the TNT ones (higher detonation energy and pressure). Measured
   1.11-1.17 at 8 cells across the radius (1.22-1.37 at 5 cells): the
   better-resolved TNT charge closed most of the gap, so the band is
   1.05-1.5 rather than the old 1.1-1.5.

`--afterburn` adds a third run with the Miller afterburn model on and
prints a KB comparison table (its own, upward band - the detonation-only
gate above is untouched).

Auto-SKIPs without WSL. Wall ~2 min (two 1D runs; ~3 with --afterburn).
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
#: band for the afterburn run (`--afterburn`): the model must not
#: overshoot KB badly and must not leave the detonation-only deficit
#: untouched. Measured with the 8-cell charge (T39): 1.20 at Z = 1,
#: 1.02-1.04 at Z = 2..4 (it was 0.95-1.03 across the board at 5 cells)
KB_AB_BAND = (0.80, 1.35)
C4_OVER_TNT = (1.05, 1.5)


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def _run(material, afterburn='none'):
    from blastlab.solvers import get_solver
    case = Case1D(radius_m=5.0, charge_kg=1.0, cell_size_m=0.02,
                  gauge_radii=sorted(KB_FREE_AIR), n_snapshots=2,
                  solver='blastfoam', material=material,
                  afterburn=afterburn)
    return get_solver(1, 'blastfoam')(case)


def _peaks(res):
    """{round(radius): peak overpressure [kPa]}."""
    return {round(r): (p.max() - P_AIR) / 1e3
            for r, p in zip(res.gauges['radii'], res.gauges['pressures'])}


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM KB ANCHOR: SKIP")
        return

    print('--- TNT run ---')
    tnt = _run('TNT')
    peaks_tnt = _peaks(tnt)

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

    if '--afterburn' in sys.argv:
        # N3: the same anchor with the Miller afterburn model on. Its
        # own (wider, upward) band - the detonation-only gate above is
        # left exactly as it is.
        print('--- TNT run, afterburn = miller ---')
        peaks_ab = _peaks(_run('TNT', afterburn='miller'))
        print('    Z     KB      no-ab    ratio    afterburn  ratio')
        for z, kb in sorted(KB_FREE_AIR.items()):
            a, b = peaks_tnt[int(z)], peaks_ab[int(z)]
            print(f'   {z:3g}  {kb:6.0f}  {a:7.0f}  {a/kb:6.2f}  '
                  f'{b:9.0f}  {b/kb:6.2f}')
        for z, kb in sorted(KB_FREE_AIR.items()):
            ratio = peaks_ab[int(z)] / kb
            check(f'afterburn KB anchor at Z = {z:g}',
                  KB_AB_BAND[0] <= ratio <= KB_AB_BAND[1],
                  f'foam {peaks_ab[int(z)]:.0f} kPa vs KB {kb:.0f} kPa '
                  f'(ratio {ratio:.2f})')
        check('afterburn raises the peaks it should',
              all(peaks_ab[int(z)] >= peaks_tnt[int(z)] - 1e-9
                  for z in KB_FREE_AIR))

    print()
    if FAIL:
        print(f"FOAM KB ANCHOR: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM KB ANCHOR: PASS")


if __name__ == '__main__':
    main()
