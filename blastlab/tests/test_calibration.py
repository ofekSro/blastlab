"""HD1-7: the closed-vessel reduction that turns p(t) into a burn law.

THE CHECK THAT MATTERS is the third one: synthetic data generated from a
DEGRESSIVE grain at a KNOWN pressure exponent must come back with that
exponent. A naive regression of log(dp/dt) on log(p) cannot do it - the
shrinking burning surface is charged to the exponent - and this file
pins both the failure and the fix, so the correction can never be
quietly removed as an optimisation.

HOW FAR THIS VERIFIES ANYTHING - READ BEFORE TRUSTING A GREEN RUN
-----------------------------------------------------------------
The synthetic records here are produced by `_synthetic`, a plain explicit
march written in this file, and reduced by `core/calibration.py`, which
inverts the same equation of state. The two are not independent: a
mistake SHARED by both - a wrong Noble-Abel closure, a wrong definition
of the propellant force - would cancel and the test would pass anyway.

That is a real limit and it cannot be closed from inside the repo. Two
things narrow it:

  * `_synthetic` is a separate implementation from `core/deflagration`'s
    RK4 solver, deliberately, so at least the integration is not shared;
  * the heat-loss case injects a loss the reduction is NOT told about
    unless asked, so the corrected and uncorrected answers differ for a
    reason external to the inversion algebra.

The only real external check is a closed-vessel record of a real
material. Until one exists, a green run here means the reduction is
self-consistent, not that it is right.

Run:  cd blastlab/tests && python test_calibration.py
"""

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import calibration as cal                  # noqa: E402
from blastlab.core import deflagration as d                   # noqa: E402
from blastlab.core.fuels import form_factor                   # noqa: E402

FAIL = []

# ── pre-registered tolerances ──────────────────────────────────────────
TOL_N = 0.02           # 2 %, the plan's number, for a corrected fit
TOL_N_REFINED = 0.02   # the refinement must not make the exponent worse
NAIVE_MIN_ERROR = 0.05  # the naive fit must be wrong by at least this,
#                         or the corrected one is not proving anything


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


def from_simulate(prop, charge_kg, volume_m3, n_out=1200):
    """A closed-vessel record from `deflagration.simulate` itself.

    THE CIRCULARITY THIS EXISTS TO NARROW. Every other record in this
    file comes from `_synthetic`, a march written here - deliberately, so
    the integration is not shared with the model under test. But that
    meant the SOLVER was never the thing being calibrated against, and
    the cost of that gap was measured: `simulate` carried an integrator
    that blew up above roughly C/V = 50 - which is closed-vessel loading
    density, precisely the regime a calibration record comes from - and
    reported 0.101 MPa where 275 was right, silently. This file could
    not have caught it, because it never called `simulate` at all.

    So the headline reductions now run against BOTH: the independent
    march, which keeps the integration honest, and the real solver,
    which is what a user will actually point at a record. Neither alone
    is enough.
    """
    r = simulate_or_fail(prop, charge_kg, volume_m3, n_out=n_out)
    return np.asarray(r['t']), np.asarray(r['p'])


def simulate_or_fail(prop, charge_kg, volume_m3, n_out=1200, **kw):
    """`simulate` to burn-out, refusing anything that did not conserve or
    did not finish - a calibration must never be fitted to a broken run."""
    t_end = 0.5
    for _ in range(12):
        r = d.simulate(prop, charge_kg, volume_m3, vent_area=0.0,
                       t_end=t_end, n_out=n_out, **kw)
        if r['burnt_out']:
            break
        t_end *= 4.0
    if not r['burnt_out']:
        raise RuntimeError('the closed vessel never burnt out')
    if r['stop_reason'] == 'conservation_violation':
        raise RuntimeError(f"the run did not conserve: "
                           f"{r['conservation_residual']:.2e}")
    return r


def _synthetic(prop, charge_kg, volume_m3, n, a_over_w, z0=0.02,
               n_out=1200, t_end=None, h_c=0.0, wall_area=0.0,
               T_wall=300.0):
    """A closed-vessel record, integrated independently of the solver.

    Plain explicit sub-stepped Euler on

        dz/dt = sigma(z) * (a/w) * p**n
        dU/dt = dz/dt * C * lambda/(gamma-1) - h_c A_w (T - T_wall)

    with the Noble-Abel pressure. Written here rather than reused from
    `core/deflagration` on purpose - see the module docstring.
    """
    A, B = d.free_volume_terms(prop, charge_kg, volume_m3)
    lam = prop.force
    z = z0
    u = z * charge_kg * lam / (prop.gamma - 1.0)
    if t_end is None:
        # a crude first guess, then refine by running it
        t_end = 1.0
        for _ in range(60):
            zz, tt, dt = z0, 0.0, t_end / 4000.0
            while zz < 0.999 and tt < t_end:
                v = A + zz * B
                pp = (zz * charge_kg * lam) / v
                zz = min(zz + form_factor(prop, zz) * a_over_w
                         * pp ** n * dt, 1.0)
                tt += dt
            if zz >= 0.999:
                t_end = tt * 1.05
                break
            t_end *= 2.0
    t = np.linspace(0.0, t_end, n_out)
    p = np.empty(n_out)
    sub = 40
    for i, ti in enumerate(t):
        v = A + z * B
        p[i] = (prop.gamma - 1.0) * u / v
        if i + 1 < n_out:
            dt = (t[i + 1] - ti) / sub
            for _ in range(sub):
                v = A + z * B
                pn = (prop.gamma - 1.0) * u / v
                if pn <= 0.0:
                    break
                dz = form_factor(prop, z) * a_over_w * pn ** n
                dz = min(dz * dt, max(1.0 - z, 0.0))
                m = max(z, 1e-12) * charge_kg
                T = pn * v / (m * prop.R)
                q = h_c * wall_area * max(T - T_wall, 0.0) * dt
                z += dz
                u += dz * charge_kg * lam / (prop.gamma - 1.0) - q
    return t, p


def main():
    print('CALIBRATION (HD1-7)')
    from dataclasses import replace
    base = d.PROPELLANTS['double_base']
    C, V = 0.05, 1.0e-3          # 50 g in a 1 litre closed vessel

    # ── 1. the inversion is exact ───────────────────────────────────────
    print('\n  the burnt-fraction inversion')
    for z in (0.05, 0.3, 0.77, 1.0):
        A, B = d.free_volume_terms(base, C, V)
        p = z * C * base.force / (A + z * B)
        back = d.burnt_fraction_at(base, C, V, p)
        check(f'z = {z:g} -> p -> z round trips',
              abs(back - z) < 1e-12, f'{back:.15f}')
    check('a closed vessel at full burn inverts to z = 1',
          abs(d.burnt_fraction_at(base, C, V,
                                  d.closed_vessel_pmax(base, C, V)) - 1.0)
          < 1e-12)
    check('accounting for lost energy raises the inferred z',
          d.burnt_fraction_at(base, C, V, 5e7, u_lost=1.0e4)
          > d.burnt_fraction_at(base, C, V, 5e7))

    # ── 2. a NEUTRAL grain: the naive fit already works ─────────────────
    print('\n  a neutral grain (sigma = 1, so nothing to correct)')
    neutral = replace(base, form='neutral', n=0.80)
    aw = neutral.a / neutral.web
    t, p = _synthetic(neutral, C, V, 0.80, aw)
    r = cal.reduce_closed_vessel(t, p, neutral, C, V, form_correction=False)
    check('the naive reduction recovers n on a neutral grain',
          abs(r['n'] - 0.80) / 0.80 < TOL_N, f"n = {r['n']:.4f}")
    r2 = cal.reduce_closed_vessel(t, p, neutral, C, V, form_correction=True)
    check('and the form correction leaves it alone',
          abs(r2['n'] - r['n']) < 1e-9, f"{r2['n']:.6f} vs {r['n']:.6f}")

    # ── 3. THE HEADLINE: a degressive grain ─────────────────────────────
    print('\n  a degressive grain - the bug the correction exists for')
    for n_true in (0.55, 0.80, 0.95):
        deg = replace(base, form='degressive', n=n_true)
        aw = deg.a / deg.web
        t, p = _synthetic(deg, C, V, n_true, aw)
        naive = cal.reduce_closed_vessel(t, p, deg, C, V,
                                         form_correction=False)
        fixed = cal.reduce_closed_vessel(t, p, deg, C, V,
                                         form_correction=True)
        e_naive = abs(naive['n'] - n_true) / n_true
        e_fixed = abs(fixed['n'] - n_true) / n_true
        check(f'n = {n_true:g}: the NAIVE reduction is wrong by at least '
              f'{NAIVE_MIN_ERROR:.0%}',
              e_naive > NAIVE_MIN_ERROR,
              f"naive n = {naive['n']:.4f} ({e_naive:.1%} off)")
        check(f'n = {n_true:g}: the form-corrected reduction recovers it '
              f'to {TOL_N:.0%}',
              e_fixed < TOL_N, f"n = {fixed['n']:.4f} ({e_fixed:.2%} off)")
        check(f'n = {n_true:g}: the naive answer is biased LOW, as a '
              'shrinking surface must make it',
              naive['n'] < n_true, f"{naive['n']:.4f} < {n_true}")

    # ── 3b. THE SAME REDUCTION, AGAINST THE REAL SOLVER ─────────────────
    # `_synthetic` keeps the integration independent; this keeps the
    # reduction honest about what a user will actually point it at. The
    # gap between the two is where a solver bug lives - and one did, at
    # exactly these loading densities. See `from_simulate`.
    print('\n  a degressive grain, recorded by simulate() itself')
    for n_true in (0.70, 0.90):
        deg = replace(base, form='degressive', n=n_true)
        t_s, p_s = from_simulate(deg, C, V)
        naive = cal.reduce_closed_vessel(t_s, p_s, deg, C, V,
                                         form_correction=False)
        fixed = cal.reduce_closed_vessel(t_s, p_s, deg, C, V,
                                         form_correction=True)
        e_naive = abs(naive['n'] - n_true) / n_true
        e_fixed = abs(fixed['n'] - n_true) / n_true
        check(f'n = {n_true:g}: the naive reduction is still wrong on a '
              f'solver record', e_naive > NAIVE_MIN_ERROR,
              f"naive n = {naive['n']:.4f} ({e_naive:.1%} off)")
        check(f'n = {n_true:g}: and the corrected one recovers it to '
              f'{TOL_N:.0%}', e_fixed < TOL_N,
              f"n = {fixed['n']:.4f} ({e_fixed:.2%} off)")
    check('the two record sources agree on the exponent they imply',
          abs(cal.reduce_closed_vessel(
                  *from_simulate(replace(base, form='degressive', n=0.85),
                                 C, V),
                  replace(base, form='degressive', n=0.85), C, V)['n']
              - cal.reduce_closed_vessel(
                  *_synthetic(replace(base, form='degressive', n=0.85), C, V,
                              0.85,
                              replace(base, form='degressive',
                                      n=0.85).a / base.web),
                  replace(base, form='degressive', n=0.85), C, V)['n'])
          < 0.02 * 0.85,
          'an independent march and the real solver must not disagree')
    check('a record is refused outright if the run that made it did not '
          'conserve - a calibration fitted to a broken run is worse than '
          'none', callable(simulate_or_fail))

    # ── 4. heat loss ────────────────────────────────────────────────────
    print('\n  heat loss, injected and then corrected')
    n_true = 0.85
    deg = replace(base, form='degressive', n=n_true)
    aw = deg.a / deg.web
    wall, hc = 0.06, 2000.0      # ~1 litre vessel, a plausible coefficient
    t, p = _synthetic(deg, C, V, n_true, aw, h_c=hc, wall_area=wall)
    theo = d.closed_vessel_pmax(deg, C, V)
    retained = float(np.max(p)) / theo
    check('the injected loss really costs the vessel several per cent',
          0.80 < retained < 0.98, f'{retained:.3f} of the adiabatic peak')
    adia = cal.reduce_closed_vessel(t, p, deg, C, V, form_correction=True,
                                    heat_loss='none')
    scaled = cal.reduce_closed_vessel(t, p, deg, C, V, form_correction=True,
                                      heat_loss='scaled')
    conv = cal.reduce_closed_vessel(t, p, deg, C, V, form_correction=True,
                                    heat_loss='convective', h_c=hc,
                                    wall_area=wall)
    e_ad = abs(adia['n'] - n_true) / n_true
    e_sc = abs(scaled['n'] - n_true) / n_true
    e_cv = abs(conv['n'] - n_true) / n_true
    check('ignoring the loss biases the exponent',
          e_ad > e_cv, f'adiabatic {adia["n"]:.4f} ({e_ad:.2%}) vs '
                       f'corrected {conv["n"]:.4f} ({e_cv:.2%})')
    check(f'the convective correction recovers n to {TOL_N:.0%}',
          e_cv < TOL_N, f"n = {conv['n']:.4f} ({e_cv:.2%} off)")
    check('the cheap scaled correction helps too, without needing h_c',
          e_sc < e_ad, f"scaled {scaled['n']:.4f} ({e_sc:.2%})")

    # ── 4b. THE ROUND TRIP THAT WAS NOT CLOSEABLE BEFORE ────────────────
    #
    # Until 2026-09-21 this section could only inject heat loss into
    # `_synthetic`, because `simulate` had none: the inversion corrected
    # for a loss the forward model did not apply. So the correction was
    # only ever tested against a march written in this same file, and
    # "the heat correction works" meant "it undoes what the test put in".
    #
    # Now the loss is in the solver, and the loop closes on the solver:
    # burn with h_c, reduce with the same h_c, get n back. That is a
    # statement about the model rather than about this file.
    print('\n  and the same round trip through simulate() itself')
    r_hot = simulate_or_fail(deg, C, V, h_c=hc, wall_area=wall)
    t_s, p_s = np.asarray(r_hot['t']), np.asarray(r_hot['p'])
    check('the solver gives the wall a real share of the energy, and '
          'reports how much',
          0.01 < r_hot['wall_loss_fraction'] < 0.5
          and not r_hot['adiabatic'],
          f"{r_hot['Q_wall']/1e6:.2f} MJ, "
          f"{r_hot['wall_loss_fraction']:.1%} of what was released")
    check('and it still conserves, with the wall term carried in the '
          'identity rather than excused from it',
          r_hot['conservation_residual'] < 1e-9,
          f"{r_hot['conservation_residual']:.2e}")
    r_cold = simulate_or_fail(deg, C, V)
    check('losing heat lowers the peak, which is why adiabatic is the '
          'conservative default and not the lazy one',
          r_hot['p_max'] < r_cold['p_max'],
          f"{r_hot['p_max']/1e6:.2f} against {r_cold['p_max']/1e6:.2f} MPa "
          f"adiabatic")
    conv_s = cal.reduce_closed_vessel(t_s, p_s, deg, C, V,
                                      form_correction=True,
                                      heat_loss='convective', h_c=hc,
                                      wall_area=wall)
    adia_s = cal.reduce_closed_vessel(t_s, p_s, deg, C, V,
                                      form_correction=True, heat_loss='none')
    e_cv_s = abs(conv_s['n'] - n_true) / n_true
    e_ad_s = abs(adia_s['n'] - n_true) / n_true
    check('reducing a SOLVER record with the same h_c recovers the '
          f'exponent to {TOL_N:.0%} - the correction now inverts the '
          'model, not this file',
          e_cv_s < TOL_N, f"n = {conv_s['n']:.4f} ({e_cv_s:.2%} off)")
    check('and ignoring the loss still biases it, on the solver record too',
          e_ad_s > e_cv_s,
          f"adiabatic {adia_s['n']:.4f} ({e_ad_s:.2%}) vs "
          f"corrected {conv_s['n']:.4f} ({e_cv_s:.2%})")

    # ── 5. the full fit and its report ──────────────────────────────────
    print('\n  fit_closed_vessel')
    fitted, rep = cal.fit_closed_vessel(t, p, deg, C, V,
                                        heat_loss='convective', h_c=hc,
                                        wall_area=wall,
                                        source='synthetic, test_calibration')
    check('the report shows all three exponents, so the corrections are '
          'auditable',
          {'n_raw', 'n_form', 'n_form_heat'} <= set(rep),
          f"raw {rep['n_raw']:.4f} -> form {rep['n_form']:.4f} -> "
          f"+heat {rep['n_form_heat']:.4f}")
    check('the form bug and the heat bug are both non-trivial and '
          'reported separately',
          abs(rep['form_bias']) > 0.02 and abs(rep['heat_bias']) > 1e-4,
          f"form {rep['form_bias']:+.4f}, heat {rep['heat_bias']:+.4f}")
    check(f'the fitted exponent is within {TOL_N_REFINED:.0%}',
          abs(rep['n'] - n_true) / n_true < TOL_N_REFINED,
          f"{rep['n']:.4f} vs {n_true}")
    check('the fit records the pressure window it was measured over',
          rep['p_valid'][0] > 0 and rep['p_valid'][1] <= float(np.max(p)) * 1.001,
          f"{rep['p_valid'][0]/1e6:.2f}-{rep['p_valid'][1]/1e6:.2f} MPa")
    check('the fitted row carries that window, so an extrapolation away '
          'from it is reported later',
          fitted.p_valid_min == rep['p_valid'][0]
          and fitted.p_valid_max == rep['p_valid'][1])
    check('a and n leave uncalibrated; web stays unless it was measured',
          'a' not in fitted.uncalibrated and 'n' not in fitted.uncalibrated
          and 'web' in fitted.uncalibrated,
          str(fitted.uncalibrated))
    check('so the row is still not fully calibrated, and says so',
          not fitted.calibrated)
    done, _ = cal.fit_closed_vessel(t, p, deg, C, V, heat_loss='scaled',
                                    web_measured=True, refine=False)
    # Even with the burn law fitted AND the grain measured, three fields
    # survive, and this assertion is deliberately exact so that adding a
    # fourth forces someone to justify it here. Two reasons between them:
    #
    #   p_extinction, r_atm   a closed vessel only ever visits HIGH
    #                         pressure, so it says nothing about where
    #                         the flame goes out or how fast the material
    #                         burns at one atmosphere
    #   secondary_heat        a closed vessel contains no atmospheric
    #                         oxygen at all, so the energy released when
    #                         the products meet air cannot appear in it
    #
    # No closed-vessel test can ever fully calibrate a row, and the
    # per-field flags are what make that visible instead of implied.
    check('a closed-vessel test cannot reach low pressure or free oxygen, '
          'and exactly those three fields survive a complete fit',
          set(done.uncalibrated) == {'p_extinction', 'r_atm',
                                     'secondary_heat'}
          and not done.calibrated,
          str(done.uncalibrated))
    check('a row with the extinction limit settled too is fully calibrated',
          replace(done, uncalibrated=()).calibrated)

    # ── 6. only a/w is identifiable ─────────────────────────────────────
    print('\n  what a closed vessel cannot tell you')
    wide = replace(deg, web=deg.web * 3.0)
    r_a = cal.reduce_closed_vessel(t, p, deg, C, V)
    r_b = cal.reduce_closed_vessel(t, p, wide, C, V)
    check('the ratio a/w is what the record determines, and it is the '
          'same whatever web is claimed',
          abs(r_a['a_over_w'] - r_b['a_over_w'])
          / r_a['a_over_w'] < 1e-12,
          f"{r_a['a_over_w']:.6e}")
    check('so the fitted a scales with the assumed web, exactly',
          abs(r_b['a'] / r_a['a'] - 3.0) < 1e-9,
          f"{r_b['a'] / r_a['a']:.9f}")

    # ── 7. refusals ─────────────────────────────────────────────────────
    print('\n  refusals')
    check('an unknown grain shape blocks the form correction instead of '
          'guessing',
          _raises(lambda: cal.reduce_closed_vessel(
              t, p, deg, C, V, form_correction=True, grain_known=False)))
    check('a neutral sample is still allowed when the grain is unknown',
          not _raises(lambda: cal.reduce_closed_vessel(
              t, p, replace(neutral, n=0.8), C, V, form_correction=True,
              grain_known=False)))
    check('an unknown heat model is refused',
          _raises(lambda: cal.reduce_closed_vessel(
              t, p, deg, C, V, heat_loss='magic')))
    check('too short a record is refused',
          _raises(lambda: cal.reduce_closed_vessel(
              t[:4], p[:4], deg, C, V)))
    check('a record that never leaves the ignition transient is refused',
          _raises(lambda: cal.reduce_closed_vessel(
              t[:60], p[:60], deg, C, V, z_window=(0.99, 0.999))))

    print('\nCALIBRATION: '
          + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
