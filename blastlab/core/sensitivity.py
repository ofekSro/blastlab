"""HD1: the band around a number that is not calibrated.

WHY THIS EXISTS, AND WHY IT IS NOT OPTIONAL
-------------------------------------------
Nothing in `PROPELLANTS` is calibrated against a real material - that is
enforced by a test, not a hope - and the burn law is applied two to three
decades below the pressures a closed vessel measures it at. A single
peak pressure from that model is not a wrong number; it is an
incomplete one. The honest object is an interval, and the point of this
module is that the interval is COMPUTED rather than appended as a
percentage.

WHAT IS VARIED, AND WHY THOSE THREE
-----------------------------------
`n`   the Vieille exponent. The dominant error by a wide margin, because
      the answer goes as p**n and the model is evaluated two decades away
      from where n was fitted: a small error in n is amplified by the
      extrapolation, while the same error in `a` is not.
`a`   the coefficient. A closed-vessel reduction identifies `a / w`, not
      `a`, so the uncertainty here is really the web measurement wearing
      `a`'s name - see `core/calibration.py`.
`p_extinction`
      the low-pressure deflagration limit. It decides whether the burn
      goes out at all, so unlike the other two it can change the ANSWER
      rather than the number - a vented magazine can sit either side of
      it. It ships uncalibrated on every row.

CORNERS, NOT A GRID - AND THE RUN CHECKS THAT CORNERS ARE ENOUGH
-----------------------------------------------------------------
The envelope is taken over the 2**k corners of the uncertainty box. That
is only valid if the response is monotone in each parameter, which is
expected here and is not assumed: `band` also samples the face centres,
and if any of them falls outside the corner envelope it says so through
`corners_sufficient = False` instead of reporting a hull that is not one.
Eight corners and six faces against a full grid is the difference
between a band you will run and one you will not.

THE WIDTH OF THE BAND IS NOT ITSELF CITABLE
-------------------------------------------
The default ranges below are class-typical judgements, not measurements,
and they carry `ranges_sourced = False` for exactly the reason the
propellant rows carry `uncalibrated`. The band tells you which way the
answer moves and by roughly how much; it does not tell you there is a
95 % chance of anything. Pass your own ranges with a `source` and that
changes.
"""

import itertools

from dataclasses import replace

from . import deflagration as _d

#: Default half-width of the Vieille exponent, absolute. The plan's
#: figure, and the reason it is absolute rather than relative: n lives in
#: 0.7-1.0 for the materials here, so +-0.15 is the span of the class.
DEFAULT_DN = 0.15

#: Default multiplicative span on `a`. A judgement, not a measurement -
#: see the module docstring on `ranges_sourced`.
DEFAULT_A_FACTOR = 1.5

#: Default multiplicative span on the extinction limit. Wider than `a`
#: because no row has ever been measured: it is a literature threshold
#: for a material class.
DEFAULT_PEXT_FACTOR = 2.0

#: Default multiplicative span on the wall heat-transfer coefficient.
#: THE FOURTH AXIS, and it is here because it earns its cost. Nothing in
#: this repository calibrates `h_c` - it is a film coefficient someone
#: estimated - and it moves the state handed to the CFD by far more than
#: it moves any single pressure: measured at h_c = 200 against adiabatic
#: on a 20 kg magazine, the panel bursts 9.5 % later with 12.4 % more
#: mass burnt and alpha_expl 10.8 % higher. A band taken over the burn
#: law alone reports itself NARROWER THAN IT IS.
#:
#: A factor of two, which is the usual standing of a film coefficient
#: taken from a table rather than a rig, and a judgement like the rest -
#: see `ranges_sourced`.
DEFAULT_HC_FACTOR = 2.0

#: The axes of the box, in the order `signs` tuples carry them.
PARAMS = ('n', 'a', 'p_extinction', 'h_c')

#: What the envelope is taken over. `p_max` is the structural load,
#: `t_p_max` decides the loading regime (impulsive against quasi-static,
#: which decides WHICH check applies), and `Z_end` says whether the
#: charge burnt at all.
REPORTED = ('p_max', 't_p_max', 'Z_end', 'burnt_out', 'extinguished')


def _perturb(prop, dn, fa, fp, fh, signs, h_c):
    """One corner of the box: (propellant, simulate-kwarg overrides).

    `signs` is (-1, 0, +1) per axis, in `PARAMS` order. Three of the four
    are propellant fields and the fourth is not - `h_c` is a property of
    the CHAMBER, not of the material - so this returns both halves
    rather than pretending they live in the same object.
    """
    sn, sa, sp, sh = signs
    kw = {}
    if sn:
        kw['n'] = max(prop.n + sn * dn, 0.05)
    if sa:
        kw['a'] = prop.a * (fa ** sa)
    if sp and prop.p_extinction > 0.0:
        kw['p_extinction'] = prop.p_extinction * (fp ** sp)
    sim = {}
    if sh and h_c > 0.0:
        sim['h_c'] = h_c * (fh ** sh)
    return (replace(prop, **kw) if kw else prop), sim


def _scalars(result):
    return {
        'p_max': result['p_max'],
        't_p_max': result['t_p_max'],
        'Z_end': result['Z'][-1],
        'burnt_out': float(bool(result['burnt_out'])),
        'extinguished': float(bool(result['extinguished'])),
    }


def band(prop, charge_kg, volume_m3, dn=DEFAULT_DN, a_factor=DEFAULT_A_FACTOR,
         pext_factor=DEFAULT_PEXT_FACTOR, hc_factor=DEFAULT_HC_FACTOR,
         source='', check_corners=True, **sim_kw):
    """Run the nominal case and the corners of the uncertainty box.

    Returns a dict with

        nominal          the scalars from the unperturbed run
        low, high        the envelope over every sample
        at_low, at_high  which corner produced each extreme, as signs
        spread           high/low for p_max, the one-number summary
        corners_sufficient
                         False if a face centre fell outside the corner
                         envelope, i.e. the response is not monotone and
                         the corners are not the hull. Reported, never
                         silently patched.
        ranges_sourced   False unless `source` was given. The band's
                         WIDTH rests on the ranges, and the defaults are
                         judgements - see the module docstring.
        n_runs           what it cost
        spans_heat_loss  False when the case is adiabatic, in which case
                         the h_c axis is degenerate and the envelope
                         does NOT cover the heat-loss assumption at all
        conserved        False if any sample failed its own conservation
                         check, which invalidates the whole band

    `sim_kw` goes straight to `deflagration.simulate`, so the band is
    taken around the case you actually ran, not around a stand-in - and
    `h_c` in it is the fourth axis rather than a fixed input.
    """
    if dn < 0 or a_factor < 1.0 or pext_factor < 1.0 or hc_factor < 1.0:
        raise ValueError('a range cannot be negative or shrink the box')
    # The cohort refinement is a property of the scenario, not of the
    # material, so it is answered once on the nominal run instead of
    # 2**k times over. Every sample shares one scenario.
    sim_kw.setdefault('refine_cohorts', True)
    h_c = float(sim_kw.get('h_c', 0.0) or 0.0)
    wall_area = float(sim_kw.get('wall_area', 0.0) or 0.0)
    # An ADIABATIC case has no h_c to perturb - zero times anything is
    # zero - so that axis is degenerate and the box is really three
    # dimensional. Widening it by inventing an h_c for someone who chose
    # adiabatic would be putting a number in their mouth, so instead the
    # band SAYS it does not span the assumption.
    spans_hc = h_c > 0.0 and wall_area > 0.0
    n_axes = len(PARAMS)

    def run(p_i, over=None):
        kw = dict(sim_kw, **(over or {}))
        return _d.simulate(p_i, charge_kg, volume_m3, **kw)

    nominal_result = run(prop)
    sim_kw['refine_cohorts'] = False
    nominal = _scalars(nominal_result)

    samples = [((0,) * n_axes, nominal, nominal_result)]
    corner_signs = list(itertools.product((-1, 1), repeat=n_axes))
    if not spans_hc:
        # drop the duplicate half of the box rather than paying for it
        corner_signs = [g for g in corner_signs if g[3] == 1]
    for signs in corner_signs:
        p_i, over = _perturb(prop, dn, a_factor, pext_factor, hc_factor,
                             signs, h_c)
        r = run(p_i, over)
        samples.append((signs, _scalars(r), r))

    def envelope(rows):
        lo = {k: min(s[k] for _g, s, _r in rows) for k in REPORTED}
        hi = {k: max(s[k] for _g, s, _r in rows) for k in REPORTED}
        return lo, hi

    corner_rows = samples[:]
    low, high = envelope(corner_rows)

    # THE CHECK THAT THE CORNERS ARE THE HULL. Cheap, and the alternative
    # is asserting monotonicity in a comment.
    faces, sufficient = [], True
    if check_corners:
        for axis in range(n_axes):
            if axis == 3 and not spans_hc:
                continue
            for s in (-1, 1):
                signs = [0] * n_axes
                signs[axis] = s
                p_i, over = _perturb(prop, dn, a_factor, pext_factor,
                                     hc_factor, tuple(signs), h_c)
                r = run(p_i, over)
                faces.append((tuple(signs), _scalars(r), r))
        tol = 1e-9
        for _g, s, _r in faces:
            for k in REPORTED:
                if s[k] < low[k] - tol * max(abs(low[k]), 1.0) or \
                        s[k] > high[k] + tol * max(abs(high[k]), 1.0):
                    sufficient = False
        if not sufficient:
            low, high = envelope(corner_rows + faces)

    all_rows = corner_rows + faces
    at_low = {k: min(all_rows, key=lambda row, k=k: row[1][k])[0]
              for k in REPORTED}
    at_high = {k: max(all_rows, key=lambda row, k=k: row[1][k])[0]
               for k in REPORTED}
    # THE TWO EXTREME RUNS ARE KEPT WHOLE, not just their peaks. A
    # structural verdict needs a pressure HISTORY, not a maximum: the
    # same peak reached slowly or quickly puts a wall in opposite corners
    # of the pressure-impulse diagram. Two traces is the whole cost of
    # being able to ask "does the answer survive its own uncertainty" -
    # see `structural_verdict`.
    lo_row = min(all_rows, key=lambda row: row[1]['p_max'])
    hi_row = max(all_rows, key=lambda row: row[1]['p_max'])
    return {
        'nominal': nominal,
        'low': low,
        'high': high,
        'at_low': at_low,
        'at_high': at_high,
        'spread': (high['p_max'] / low['p_max']
                   if low['p_max'] > 0 else float('inf')),
        'corners_sufficient': sufficient,
        'ranges_sourced': bool(source),
        'source': source,
        'ranges': {'dn': dn, 'a_factor': a_factor,
                   'pext_factor': pext_factor, 'hc_factor': hc_factor},
        'params': PARAMS,
        'n_runs': len(all_rows),
        #: False when the case is adiabatic. The h_c axis is then
        #: degenerate and this envelope does NOT cover the heat-loss
        #: assumption - which moves the hand-off by more than any single
        #: burn-law parameter does, so a band reported without it is
        #: narrower than the truth and has to say so.
        'spans_heat_loss': spans_hc,
        'h_c_nominal': h_c,
        #: the full traces of the two extremes, for `structural_verdict`
        'low_trace': (list(lo_row[2]['t']), list(lo_row[2]['p'])),
        'high_trace': (list(hi_row[2]['t']), list(hi_row[2]['p'])),
        'low_signs': lo_row[0],
        'high_signs': hi_row[0],
        'conserved': all(r['stop_reason'] != 'conservation_violation'
                         for _g, _s, r in all_rows),
        'cohort_converged': nominal_result['cohort_converged'],
        # A band whose members do not agree on whether the charge burnt
        # is not a band around a pressure - it straddles two different
        # events, and averaging them would be meaningless.
        'straddles_extinction': (low['extinguished']
                                 != high['extinguished']),
    }


#: The three answers a structural question can have once the band is
#: taken seriously. The third is an ANSWER and not a failure to produce
#: one - see `structural_verdict`.
VERDICTS = ('fails_across_band', 'survives_across_band',
            'undetermined_within_band')


def structural_verdict(b, component, p_ref=None):
    """Run the element at BOTH ends of the band, and say which of the
    three answers that gives.

    WHY A VERDICT AT THE NOMINAL POINT IS WORTH LITTLE. The band on a
    vented magazine spans a factor of 12.7 - more than an order of
    magnitude - and a wall's response is not linear in the load. A
    verdict computed at the middle of that says nothing about whether it
    holds at the ends, and "the wall survives" from an uncalibrated model
    is a sentence that reads the same whether it is robust or whether it
    flips one step either side of the number that produced it.

    So the element is run at the low end and at the high end:

        fails_across_band       it yields at both ends. The conclusion
                                does not depend on the calibration, and
                                that is worth saying.
        survives_across_band    it yields at neither. Same.
        undetermined_within_band
                                it yields at one. This is an ANSWER, not
                                a failure to produce one: the verdict
                                depends on a calibration that does not
                                exist, and the only honest report is to
                                say so and name what would settle it.

    The full traces are used rather than the two peaks, because the same
    peak reached slowly or quickly puts a wall in opposite corners of the
    pressure-impulse diagram.
    """
    from . import sdof as _sdof
    from .constants import P_AIR
    p_ref = P_AIR if p_ref is None else p_ref
    out = {}
    for end in ('low', 'high'):
        t, p = b[f'{end}_trace']
        r = _sdof.response(t, p, component, p_ref=p_ref)
        out[end] = {
            'p_max': b[end]['p_max'],
            'ductility': r.ductility,
            'support_rotation_deg': r.support_rotation_deg,
            'yielded': bool(r.yielded),
            'collapsed': bool(r.collapsed),
            'regime': r.regime,
            'signs': b[f'{end}_signs'],
        }
    lo_fails, hi_fails = out['low']['yielded'], out['high']['yielded']
    if lo_fails and hi_fails:
        verdict = 'fails_across_band'
        note = ('The element yields at BOTH ends of the band, so this '
                'conclusion does not rest on the calibration.')
    elif not lo_fails and not hi_fails:
        verdict = 'survives_across_band'
        note = ('The element yields at NEITHER end of the band, so this '
                'conclusion does not rest on the calibration.')
    else:
        verdict = 'undetermined_within_band'
        note = ('THE VERDICT FLIPS INSIDE THE BAND: the element survives '
                'the low end and yields at the high one. That is not a '
                'missing calculation, it is the answer - whether this '
                'wall holds depends on a burn law nobody has measured '
                'for this material. A closed-vessel record on the real '
                'propellant is what settles it, and nothing else will.')
    out['verdict'] = verdict
    out['note'] = note
    out['collapses_at_high_end'] = out['high']['collapsed']
    # A conclusion drawn from a band whose own width is a judgement is
    # weaker again, and saying "it survives" is where that matters most.
    out['ranges_sourced'] = b.get('ranges_sourced', False)
    return out


def summary_line(b):
    """One line for a report, written so the caveats cannot be dropped."""
    lo = b['low']['p_max'] / 1e6
    hi = b['high']['p_max'] / 1e6
    nom = b['nominal']['p_max'] / 1e6
    txt = (f'{nom:.3f} MPa, band {lo:.3f} to {hi:.3f} '
           f'(x{b["spread"]:.1f}) over n +-{b["ranges"]["dn"]:g}, '
           f'a x/{b["ranges"]["a_factor"]:g}, '
           f'p_ext x/{b["ranges"]["pext_factor"]:g}')
    if b.get('spans_heat_loss'):
        txt += f', h_c x/{b["ranges"]["hc_factor"]:g}'
    else:
        txt += (' - and NOT over heat loss, because this case is '
                'adiabatic: the envelope is narrower than the truth by '
                'whatever the wall coefficient is worth')
    if not b['ranges_sourced']:
        txt += ' - RANGES UNSOURCED, the width is a judgement'
    if b['straddles_extinction']:
        txt += ' - AND THE BAND STRADDLES EXTINCTION: some of it is a '\
               'fire that goes out'
    if not b['corners_sufficient']:
        txt += ' - corners were not the hull, faces included'
    if not b['conserved']:
        txt += ' - A SAMPLE DID NOT CONSERVE, the band is void'
    return txt
