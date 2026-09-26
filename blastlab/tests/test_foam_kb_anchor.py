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

`--afterburn` adds two more runs with the Miller afterburn model on -
TNT against its KB band, then C4 as a sanity check that the Miller rate
(fitted on TNT alone in N5-3, then applied to all six materials) still
behaves for a charge nobody calibrated. The detonation-only gate above
is untouched.

`--materials` sweeps the afterburn lift across all six materials and
checks it follows oxygen balance - the shared Miller rate (N5-3, fitted
on TNT) is the only thing they have in common.

Auto-SKIPs without WSL. Wall ~2 min (two 1D runs; ~4 with --afterburn,
~12 with --materials, which adds twelve more; --impulse adds one
20 kg free-air run, ~5 min, checked against the SwisdakData.csv
table from blastFoam's own KingeryBulmash validation case).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.case import Case1D                          # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402
from blastlab.solvers.foam.materials import AFTERBURN          # noqa: E402

FAIL = []

#: Kingery-Bulmash free-air incident peak overpressure [kPa] at
#: Z = R/W^(1/3) [m/kg^(1/3)] (standard KB polynomial values)
KB_FREE_AIR = {1.0: 904.0, 2.0: 186.0, 3.0: 80.0, 4.0: 47.0}
KB_BAND = (0.65, 1.35)
#: N5-3: a SANITY band for C4 with afterburn on - wide on purpose.
#: Only TNT is calibrated (validate_case says so, P1-4), so this is
#: here to catch the shared Miller rate going wrong for a non-TNT
#: charge, not to assert a number anybody fitted.
C4_AB_BAND = (0.85, 1.60)
#: band for the afterburn run (`--afterburn`): the model must not
#: overshoot KB badly and must not leave the detonation-only deficit
#: untouched. Measured with the 8-cell charge (T39) after the N5-3
#: refit of the Miller rate: 1.06 at Z = 1, 0.95 at Z = 2..4. It was
#: 1.20 / 1.02-1.04 before that, on a rate still fitted at 5 cells -
#: see the sweep table in solvers/foam/materials.py.
KB_AB_BAND = (0.80, 1.35)
C4_OVER_TNT = (1.05, 1.5)

#: `--impulse` leg (N5-7 coverage gap: every anchor above measures
#: PEAK; a 3.7 % impulse shift once sailed through this whole file
#: green). Reference: SwisdakData.csv shipped with blastFoam's own
#: validation case (validation/blastFoam/KingeryBulmash), Swisdak's
#: simplified Kingery-Bulmash fits for a 10 kg TNT HEMISPHERICAL
#: surface burst: R [m] -> (peak overpressure [kPa], positive-phase
#: impulse [Pa s], arrival [ms]). A hemisphere on rigid ground is the
#: image of a 20 kg sphere in free air - the same symmetry blastFoam's
#: own wedge validation case leans on - so the leg runs 20 kg free air
#: and reads the table directly. The mapping inherits KB's real-ground
#: energy loss (the empirical 1.7-1.8 factor vs the ideal 2.0, worth
#: ~5-8 % on impulse), one more reason the band is a DECADE bar, not a
#: precision bar: it exists to catch factor-class impulse bugs (B0's
#: pRef collapse, a lost positive phase), not few-% ignition effects -
#: those belong to the mesh-convergence protocol in TODO N5-7.
KB_SURF_10KG = {
    3.0: (653.1, 403.7, 1.855),
    5.0: (202.4, 250.6, 4.811),
    7.0: (97.98, 185.9, 8.775),
    10.0: (49.27, 136.3, 15.82),
}
KB_IMP_BAND = (0.65, 1.35)


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

    if '--impulse' in sys.argv:
        print('--- impulse leg: 20 kg free air vs the vendor table ---')
        from blastlab.solvers import get_solver
        import numpy as np
        # open boundary + explicit t_end: with 'terminate' the run
        # stops on arrival at the domain edge, cutting off the 10 m
        # gauge's positive phase; 30 ms covers arrival there (15.8 ms)
        # plus its full positive duration with margin.
        case = Case1D(radius_m=12.0, charge_kg=20.0, cell_size_m=0.02,
                      gauge_radii=sorted(KB_SURF_10KG), n_snapshots=2,
                      bc_outer='open', t_end=0.030,
                      solver='blastfoam', material='TNT')
        res = get_solver(1, 'blastfoam')(case)
        t = np.asarray(res.gauges['times'])
        for r, p in zip(res.gauges['radii'], res.gauges['pressures']):
            kb_p, kb_i, kb_ta = KB_SURF_10KG[round(float(r), 1)]
            p = np.asarray(p)
            above = p > P_AIR
            if not above.any():
                check(f'impulse at R = {r:g} m', False, 'no signal')
                continue
            i0 = int(np.argmax(above))
            ipk = i0 + int(np.argmax(p[i0:]))
            rest = np.nonzero(~above[ipk:])[0]
            i1 = ipk + (int(rest[0]) if rest.size else len(p) - ipk)
            imp = float(np.trapezoid(p[i0:i1] - P_AIR, t[i0:i1]))
            ri = imp / kb_i
            rp = (p.max() - P_AIR) / 1e3 / kb_p
            check(f'impulse anchor at R = {r:g} m',
                  KB_IMP_BAND[0] <= ri <= KB_IMP_BAND[1],
                  f'foam {imp:.0f} Pa s vs KB {kb_i:.0f} '
                  f'(ratio {ri:.2f}); peak ratio {rp:.2f}, '
                  f'arrival KB {kb_ta:g} ms')
            check(f'and the peak there agrees too (R = {r:g} m)',
                  KB_BAND[0] <= rp <= KB_BAND[1],
                  f'ratio {rp:.2f}')

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

        # N5-3 fitted the Miller rate `a` on TNT alone and applied it to
        # all six materials (it is a model rate, not a material
        # property; only Q0 is per-material, from oxygen balance). That
        # left the other five moved by a factor of 20 with no coverage
        # at all - this leg is the cheapest thing that would notice the
        # shared rate going wrong for a non-TNT charge. It is a SANITY
        # band, not an anchor: validate_case warns, correctly, that
        # nothing but TNT is calibrated (P1-4), so asserting a KB ratio
        # here would be asserting a number nobody has fitted.
        print('--- C4 run, afterburn = miller ---')
        peaks_c4ab = _peaks(_run('C4', afterburn='miller'))
        for z in sorted(KB_FREE_AIR):
            zi = int(z)
            print(f'   Z = {z:g}   C4 {peaks_c4ab[zi]:7.0f} kPa   '
                  f'TNT {peaks_ab[zi]:7.0f} kPa   '
                  f'ratio {peaks_c4ab[zi] / peaks_ab[zi]:.2f}')
        check('C4 afterburn still beats TNT afterburn',
              all(peaks_c4ab[int(z)] > peaks_ab[int(z)]
                  for z in KB_FREE_AIR),
              str({int(z): round(peaks_c4ab[int(z)] / peaks_ab[int(z)], 3)
                   for z in KB_FREE_AIR}))
        # C4's Q0 is 0.57 MJ/kg against TNT's 2.0 (it is nearly
        # oxygen-balanced), so afterburn must lift it by LESS than it
        # lifts TNT even though its detonation energy is higher
        lift_c4 = peaks_c4ab[1] / peaks_c4[1]
        lift_tnt = peaks_ab[1] / peaks_tnt[1]
        check('and afterburn lifts C4 less than TNT (oxygen balance)',
              1.0 <= lift_c4 < lift_tnt,
              f'C4 x{lift_c4:.3f} vs TNT x{lift_tnt:.3f}')
        check('C4 afterburn stays inside the sanity band',
              all(C4_AB_BAND[0] <= peaks_c4ab[int(z)] / kb <= C4_AB_BAND[1]
                  for z, kb in KB_FREE_AIR.items()),
              str({int(z): round(peaks_c4ab[int(z)] / kb, 2)
                   for z, kb in KB_FREE_AIR.items()}))

    if '--materials' in sys.argv:
        # N5-3 fitted the Miller rate `a` on TNT alone and applied it to
        # all six materials. `--afterburn` covers TNT and C4; this
        # sweeps the remaining four so the shared rate is exercised
        # against every Q0 in the table.
        #
        # What is asserted is the ONE thing that is knowable without a
        # calibration per material: the ORDERING. Q0 comes from oxygen
        # balance - how much oxygen the molecule lacks to burn itself -
        # so afterburn must lift the fuel-rich explosives more than the
        # oxygen-balanced ones, in that order. Absolute KB ratios are
        # NOT asserted: validate_case warns, correctly, that nothing but
        # TNT is calibrated (P1-4).
        print('--- afterburn sweep, all five materials ---')
        lift = {}
        for mat in ('TNT', 'C4', 'HMX', 'PETN', 'ANFO'):
            no_ab = _peaks(_run(mat, afterburn='none'))
            with_ab = _peaks(_run(mat, afterburn='miller'))
            lift[mat] = with_ab[1] / no_ab[1]
            ab = AFTERBURN[mat]
            print(f'   {mat:5} Q0={ab.Q0/1e6:4.2f} MJ/kg  '
                  f'no-ab {no_ab[1]:7.0f} -> ab {with_ab[1]:7.0f} kPa  '
                  f'lift x{lift[mat]:.3f}')
            check(f'{mat}: afterburn does not lower the peak',
                  lift[mat] >= 1.0 - 1e-9, f'x{lift[mat]:.4f}')
            check(f'{mat}: the lift stays physical (< x2)',
                  lift[mat] < 2.0, f'x{lift[mat]:.4f}')
        # What the lift ordering actually supports, measured (RDX was
        # still in the table then; removed 2026-09-26, P1-14):
        #
        #   TNT 1.187 | RDX 1.052 | HMX 1.050 | C4 1.048
        #             | ANFO 1.022 | PETN 1.008
        #
        # TNT stands far apart, exactly as oxygen balance says it should
        # (-74 % against -21 % for the next group). But the bottom two
        # come out INVERTED against both Q0 (PETN 0.27 vs ANFO 0.10
        # MJ/kg) and Q0/e0 (0.046 vs 0.026), so a strict six-way
        # ordering is not a claim this can make - an earlier version of
        # this check asserted one and was wrong.
        #
        # The reason is that `lift` is relative to each material's OWN
        # detonation peak, and those differ by 50 % across the table
        # (PETN 1035 kPa, ANFO 685). The same added energy is a smaller
        # relative lift on a stronger baseline. At 1.008 vs 1.022 the
        # two are also close enough that the resolution and the shared
        # Miller rate plausibly decide the order between them.
        #
        # So: assert the separation that IS physical, and record the
        # rest as measurement rather than dressing it up as a law.
        check('TNT is lifted most, and by a wide margin',
              lift['TNT'] == max(lift.values())
              and lift['TNT'] - 1.0 > 2.0 * max(
                  v - 1.0 for k, v in lift.items() if k != 'TNT'),
              str({k: round(v, 3) for k, v in lift.items()}))
        check('every oxygen-balanced material stays a small correction',
              all(v < 1.10 for k, v in lift.items() if k != 'TNT'),
              str({k: round(v, 3) for k, v in lift.items() if k != 'TNT'}))

    print()
    if FAIL:
        print(f"FOAM KB ANCHOR: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM KB ANCHOR: PASS")


if __name__ == '__main__':
    main()
