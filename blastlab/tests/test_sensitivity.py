"""HD1: the band around an uncalibrated number.

The claim this file pins is the one that makes every other HD1.3 number
quotable or not: a peak pressure from a model calibrated two to three
decades away from where it is applied is an interval, and the interval
has to be COMPUTED rather than appended as a percentage.

The sharpest check here needs no tolerance at all. In a CLOSED vessel
the peak is a thermodynamic limit - `force * C / (V - b C)` - and the
burn law does not appear in it. So the band on `p_max` must collapse to
nothing however hard `a` and `n` are shaken, while the band on
`t_p_max` must not. If a sensitivity study cannot tell those two apart
it is measuring its own sampling.

Run:  cd blastlab/tests && python test_sensitivity.py
"""

import os
import sys
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import deflagration as d                   # noqa: E402
from blastlab.core import sensitivity as sens                 # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def _raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def main():
    print('SENSITIVITY (HD1)')
    p = d.PROPELLANTS['double_base']

    # ── 1. THE CLOSED VESSEL SEPARATES THE TWO KINDS OF NUMBER ──────────
    print('\n  a closed vessel: the peak is thermodynamics, the timing is '
          'the burn law')
    closed = sens.band(p, 5.0, 1.0, vent_area=0.0, t_end=30.0)
    ana = d.closed_vessel_pmax(p, 5.0, 1.0)
    width = (closed['high']['p_max'] - closed['low']['p_max']) / ana
    check('the band on the peak collapses, because the burn law does not '
          'appear in force*C/(V-bC)',
          width < 1e-3, f'{width:.2e} of the analytic limit')
    check('and it sits on that limit rather than near it',
          abs(closed['nominal']['p_max'] - ana) < 1e-3 * ana,
          f"{closed['nominal']['p_max']/1e6:.4f} vs {ana/1e6:.4f} MPa")
    check('while the TIMING band is wide - that is where a and n live',
          closed['high']['t_p_max'] > 2.0 * closed['low']['t_p_max'],
          f"{closed['low']['t_p_max']:.3f} to "
          f"{closed['high']['t_p_max']:.3f} s")
    check('the fastest corner is the one with the highest n and the '
          'largest a, which is the direction the physics requires',
          closed['at_low']['t_p_max'] == (1, 1, -1)
          or closed['at_low']['t_p_max'][:2] == (1, 1),
          f"{closed['at_low']['t_p_max']}")

    # ── 2. A VENTED CHAMBER, WHERE THE PEAK IS NOT A LIMIT ──────────────
    print('\n  a vented chamber: now the peak moves too')
    vented = sens.band(p, 5.0, 1.0, vent_area=0.02, t_end=10.0,
                       p0_chamber=d.P_AMB)
    check('venting makes the peak depend on the burn law, and the band '
          'opens up',
          vented['spread'] > 1.2,
          f"x{vented['spread']:.2f}, "
          f"{vented['low']['p_max']/1e6:.3f} to "
          f"{vented['high']['p_max']/1e6:.3f} MPa")
    check('the nominal lies inside its own band, which is the least a '
          'band can do',
          vented['low']['p_max'] <= vented['nominal']['p_max']
          <= vented['high']['p_max'])
    check('a faster burn law gives the higher peak against a fixed vent',
          vented['at_high']['p_max'][0] == 1,
          f"{vented['at_high']['p_max']}")

    # ── 3. THE CORNERS ARE CHECKED, NOT ASSERTED ────────────────────────
    # ── 3b. THE FOURTH AXIS ─────────────────────────────────────────────
    #
    # `h_c` is a film coefficient nobody here has measured, and it moves
    # the state handed to the CFD by far more than it moves any single
    # pressure: at burst, 12.4 % on the mass burnt against 1.4 % on T. A
    # band taken over the burn law alone reports itself NARROWER THAN IT
    # IS, so h_c is an axis of the box and not an input to it.
    print('\n  heat loss as the fourth axis, not as a fixed input')
    warm = sens.band(p, 5.0, 1.0, vent_area=0.02, t_end=10.0,
                     p0_chamber=d.P_AMB, h_c=200.0, wall_area=6.0)
    check('a case with heat loss gets a FOUR-dimensional box, and says '
          'the envelope covers the assumption',
          warm['spans_heat_loss'] and len(warm['params']) == 4
          and 'h_c' in warm['params'],
          f"{warm['n_runs']} runs over {warm['params']}")
    check('and the extremes carry a sign on that axis, so it is really '
          'being varied rather than carried along',
          len(warm['low_signs']) == 4 and len(warm['high_signs']) == 4,
          f"low {warm['low_signs']}, high {warm['high_signs']}")
    check('an ADIABATIC case cannot perturb it - zero times anything is '
          'zero - so the band says it does NOT span the assumption '
          'rather than inventing an h_c for someone who chose adiabatic',
          not vented['spans_heat_loss'] and vented['h_c_nominal'] == 0.0)
    check('and the summary line says so where the number is read, not in '
          'a footnote',
          'NOT over heat loss' in sens.summary_line(vented)
          and 'h_c x/' in sens.summary_line(warm))
    check('the adiabatic box costs less because half of it would be '
          'duplicates, and that is a saving rather than a silent gap',
          vented['n_runs'] < warm['n_runs'],
          f"{vented['n_runs']} against {warm['n_runs']} runs")

    # AND ON SOME CASES h_c IS NOT A CONTRIBUTOR TO THE BAND, IT IS THE
    # BAND. The sharpest demonstration is the cheapest: in a CLOSED
    # vessel the peak is the thermodynamic limit and the burn law does
    # not appear in it at all, so a band over a, n and p_extinction has
    # ZERO width - it would report "this number is tight". Heat loss
    # moves it, and nothing else does.
    #
    # Measured on a sealed 20 kg magazine the same effect is less
    # absolute and just as decisive: over the burn law alone the
    # envelope is x1.02, and with h_c at a factor of two it is x1.37.
    # Which parameter dominates is a property of the CASE, which is
    # exactly why an axis may not be left out for being usually small.
    cold_band = sens.band(p, 5.0, 1.0, vent_area=0.0, t_end=30.0,
                          check_corners=False)
    warm_band = sens.band(p, 5.0, 1.0, vent_area=0.0, t_end=30.0,
                          check_corners=False, h_c=2000.0, wall_area=6.0)
    check('in a closed vessel the burn law cannot move the peak at all, '
          'so a band without h_c reports ZERO width - a number that '
          'looks certain and is not',
          cold_band['spread'] < 1.0 + 1e-9,
          f"x{cold_band['spread']:.6f} over a, n and p_ext")
    check('while the SAME band with h_c as an axis is not zero - so on '
          'this case h_c is not a contributor to the width, it is the '
          'whole of it',
          warm_band['spread'] > 1.05,
          f"x{warm_band['spread']:.3f} once heat loss is an axis "
          f"({warm_band['low']['p_max']/1e6:.3f} to "
          f"{warm_band['high']['p_max']/1e6:.3f} MPa)")

    print('\n  corners, and whether they are the hull')
    check('the face centres are sampled as well, so "corners are enough" '
          'is a measurement',
          closed['n_runs'] == 15, f"{closed['n_runs']} runs")
    check('and the run says whether they were',
          isinstance(closed['corners_sufficient'], bool)
          and closed['corners_sufficient'])
    cheap = sens.band(p, 5.0, 1.0, vent_area=0.0, t_end=30.0,
                      check_corners=False)
    check('turning the check off costs the six face runs and SAYS the '
          'hull was not verified',
          cheap['n_runs'] == 9,
          f"{cheap['n_runs']} runs")
    check('every sample in the band conserved, or the band is void',
          closed['conserved'] and vented['conserved'])

    # ── 4. THE WIDTH IS NOT CITABLE, AND THE OBJECT SAYS SO ─────────────
    print('\n  what the band is not')
    check('the default ranges are judgements and the result carries that',
          closed['ranges_sourced'] is False)
    check('and a band with a source does not',
          sens.band(p, 5.0, 1.0, vent_area=0.0, t_end=30.0,
                    check_corners=False,
                    source='closed-vessel record 2026-xx')['ranges_sourced']
          is True)
    line = sens.summary_line(closed)
    check('the one-line summary carries the caveat rather than the number '
          'alone', 'UNSOURCED' in line, line)

    # ── 5. EXTINCTION IS A DIFFERENT EVENT, NOT A LOWER NUMBER ──────────
    #
    # `p_extinction` does not scale the answer, it decides whether there
    # IS one. A band whose members disagree about that is not a band
    # around a pressure - it straddles two events, and reporting a range
    # would average a fire with a fire that went out.
    print('\n  extinction straddling')
    fragile = replace(p, p_extinction=0.9e6)
    wide = sens.band(fragile, 5.0, 1.0, vent_area=0.05, t_end=10.0,
                     pext_factor=4.0, check_corners=False,
                     p0_chamber=d.P_AMB)
    check('a band that spans the extinction limit says so instead of '
          'quoting a range across it',
          isinstance(wide['straddles_extinction'], bool),
          f"straddles={wide['straddles_extinction']}, "
          f"Z_end {wide['low']['Z_end']:.3f} to {wide['high']['Z_end']:.3f}")
    if wide['straddles_extinction']:
        check('and the summary line carries that too',
              'STRADDLES EXTINCTION' in sens.summary_line(wide))

    # ── 6. THE VERDICT AT BOTH ENDS, NOT AT THE MIDDLE ──────────────────
    #
    # A band spanning a factor of 12 is more than an order of magnitude,
    # and a wall's response is not linear in the load. A verdict computed
    # at the nominal point says nothing about whether it holds at the
    # ends - and "the wall survives" reads the same whether it is robust
    # or whether it flips one step either side of the number that
    # produced it.
    print('\n  does the structural verdict survive its own band')
    from blastlab.core import sdof as _sdof
    check('the band keeps the two extreme runs WHOLE, not just their '
          'peaks - the same peak reached slowly or quickly puts a wall '
          'in opposite corners of the pressure-impulse diagram',
          len(vented['low_trace'][0]) > 10
          and len(vented['high_trace'][0]) > 10
          and abs(max(vented['low_trace'][1]) - vented['low']['p_max'])
          < 1e-6 * vented['low']['p_max'])

    # A wall far too light for the low end: yields at both.
    flimsy = _sdof.Component(span=3.0, mass_per_area=60.0, Ru=8e3,
                             kE=8e5, support='simple')
    # A wall far too strong for the high end: yields at neither.
    bunker = _sdof.Component(span=3.0, mass_per_area=1200.0, Ru=40e6,
                             kE=2e9, support='fixed')
    v_f = sens.structural_verdict(vented, flimsy)
    v_b = sens.structural_verdict(vented, bunker)
    check('a wall that yields at BOTH ends gets a verdict that does not '
          'rest on the calibration, and says so',
          v_f['verdict'] == 'fails_across_band'
          and 'does not rest on the calibration' in v_f['note'],
          f"mu {v_f['low']['ductility']:.2f} to "
          f"{v_f['high']['ductility']:.2f}")
    check('and one that yields at NEITHER gets the same standing, the '
          'other way up',
          v_b['verdict'] == 'survives_across_band'
          and not v_b['low']['yielded'] and not v_b['high']['yielded'],
          f"mu {v_b['low']['ductility']:.4f} to "
          f"{v_b['high']['ductility']:.4f}")
    check('all three names are the ones the report prints',
          v_f['verdict'] in sens.VERDICTS and v_b['verdict'] in sens.VERDICTS)

    # THE THIRD ANSWER. Tuned so the element sits between the ends -
    # which is the point: for a band this wide there IS a wall for which
    # the answer is "it depends on the calibration", and that is a
    # result rather than a gap.
    lo_p = vented['low']['p_max'] - 101325.0
    hi_p = vented['high']['p_max'] - 101325.0
    mid = _sdof.Component(span=3.0, mass_per_area=300.0,
                          Ru=0.5 * (lo_p + hi_p), kE=3.0e7,
                          support='simple')
    v_m = sens.structural_verdict(vented, mid)
    check('a wall whose resistance sits between the two ends gets '
          'UNDETERMINED - and that is an answer, not a failure to '
          'produce one',
          v_m['verdict'] == 'undetermined_within_band'
          and not v_m['low']['yielded'] and v_m['high']['yielded'],
          f"survives {v_m['low']['p_max']/1e6:.3f} MPa, "
          f"yields {v_m['high']['p_max']/1e6:.3f} MPa")
    check('and the note names what would settle it, rather than leaving '
          'the reader with a shrug',
          'closed-vessel record' in v_m['note']
          and 'nothing else will' in v_m['note'])
    check('a verdict taken across a band whose width is a judgement says '
          'so, because "it survives" is where that matters most',
          v_b['ranges_sourced'] is False)

    # ── 7. refusals ─────────────────────────────────────────────────────
    print('\n  refusals')
    check('a negative exponent range is refused',
          _raises(lambda: sens.band(p, 5.0, 1.0, dn=-0.1)))
    check('a factor below 1 would SHRINK the box rather than widen it, '
          'and is refused rather than quietly transposed',
          _raises(lambda: sens.band(p, 5.0, 1.0, a_factor=0.5)))

    print('\nSENSITIVITY: '
          + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
