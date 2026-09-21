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

#: What the envelope is taken over. `p_max` is the structural load,
#: `t_p_max` decides the loading regime (impulsive against quasi-static,
#: which decides WHICH check applies), and `Z_end` says whether the
#: charge burnt at all.
REPORTED = ('p_max', 't_p_max', 'Z_end', 'burnt_out', 'extinguished')


def _perturb(prop, dn, fa, fp, signs):
    """One corner of the box. `signs` is (-1, 0, +1) per parameter."""
    sn, sa, sp = signs
    kw = {}
    if sn:
        kw['n'] = max(prop.n + sn * dn, 0.05)
    if sa:
        kw['a'] = prop.a * (fa ** sa)
    if sp and prop.p_extinction > 0.0:
        kw['p_extinction'] = prop.p_extinction * (fp ** sp)
    return replace(prop, **kw) if kw else prop


def _scalars(result):
    return {
        'p_max': result['p_max'],
        't_p_max': result['t_p_max'],
        'Z_end': result['Z'][-1],
        'burnt_out': float(bool(result['burnt_out'])),
        'extinguished': float(bool(result['extinguished'])),
    }


def band(prop, charge_kg, volume_m3, dn=DEFAULT_DN, a_factor=DEFAULT_A_FACTOR,
         pext_factor=DEFAULT_PEXT_FACTOR, source='', check_corners=True,
         **sim_kw):
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
        conserved        False if any sample failed its own conservation
                         check, which invalidates the whole band

    `sim_kw` goes straight to `deflagration.simulate`, so the band is
    taken around the case you actually ran, not around a stand-in.
    """
    if dn < 0 or a_factor < 1.0 or pext_factor < 1.0:
        raise ValueError('a range cannot be negative or shrink the box')
    # The cohort refinement is a property of the scenario, not of the
    # material, so it is answered once on the nominal run instead of
    # 2**k times over. Every sample shares one scenario.
    sim_kw.setdefault('refine_cohorts', True)

    def run(p_i):
        return _d.simulate(p_i, charge_kg, volume_m3, **sim_kw)

    nominal_result = run(prop)
    sim_kw['refine_cohorts'] = False
    nominal = _scalars(nominal_result)

    samples = [((0, 0, 0), nominal, nominal_result)]
    corner_signs = list(itertools.product((-1, 1), repeat=3))
    for signs in corner_signs:
        r = run(_perturb(prop, dn, a_factor, pext_factor, signs))
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
        for axis in range(3):
            for s in (-1, 1):
                signs = [0, 0, 0]
                signs[axis] = s
                r = run(_perturb(prop, dn, a_factor, pext_factor,
                                 tuple(signs)))
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
                   'pext_factor': pext_factor},
        'n_runs': len(all_rows),
        'conserved': all(r['stop_reason'] != 'conservation_violation'
                         for _g, _s, r in all_rows),
        'cohort_converged': nominal_result['cohort_converged'],
        # A band whose members do not agree on whether the charge burnt
        # is not a band around a pressure - it straddles two different
        # events, and averaging them would be meaningless.
        'straddles_extinction': (low['extinguished']
                                 != high['extinguished']),
    }


def summary_line(b):
    """One line for a report, written so the caveats cannot be dropped."""
    lo = b['low']['p_max'] / 1e6
    hi = b['high']['p_max'] / 1e6
    nom = b['nominal']['p_max'] / 1e6
    txt = (f'{nom:.3f} MPa, band {lo:.3f} to {hi:.3f} '
           f'(x{b["spread"]:.1f}) over n +-{b["ranges"]["dn"]:g}, '
           f'a x/{b["ranges"]["a_factor"]:g}, '
           f'p_ext x/{b["ranges"]["pext_factor"]:g}')
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
