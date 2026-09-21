"""HD1-7: turning a closed-vessel pressure record into a burn law.

This is what makes the rest of the HD1.3 track quotable. Every number
`core/deflagration.py` produces rests on the Vieille pair, and until the
pair comes from a test of the actual material the model is an exercise.

TWO WAYS THE OBVIOUS REDUCTION IS WRONG
---------------------------------------
The textbook shortcut is to regress log(dp/dt) against log(p) and read
the pressure exponent off the slope. It is wrong twice, and both errors
land on `n` - the parameter the whole extrapolation to magazine
pressures is most sensitive to.

1. THE FORM FUNCTION. The pressure rises at a rate set by the burning
   SURFACE as well as by the burn rate:

       dp/dt  proportional to  sigma(z) * a * p**n

   A degressive grain loses surface as it burns, so dp/dt falls for a
   reason that has nothing to do with pressure. Regressing the raw
   record charges that decline to the exponent and returns an `n` that is
   too small, by an amount that depends on the grain shape rather than on
   the propellant. The fix is to recover z(t) from p(t), differentiate,
   and divide by sigma(z) BEFORE the regression.

2. HEAT LOSS. Recovering z from p means inverting the equation of state,
   and doing that adiabatically assumes the gas kept all its energy. A
   closed vessel gives several per cent to its walls by the time it
   peaks, so the adiabatic inversion reads a systematically LOW z, and
   increasingly so as the burn goes on. That tilt goes straight into the
   slope. `deflagration.burnt_fraction_at` therefore takes the energy
   already lost, and the reduction marches it forward.

`reduce_closed_vessel` reports the exponent under all three treatments -
raw, form-corrected, form-and-heat-corrected - because the DIFFERENCES
are the evidence that the corrections did something, and a future reader
needs to see them rather than take the final number on trust.

WHAT A CLOSED VESSEL CAN AND CANNOT DETERMINE
---------------------------------------------
The burn law enters the model only as

    dz/dt = sigma(z) * (a / w) * p**n

so a closed-vessel record determines `n` and the RATIO a/w, never `a`
and the web thickness separately. That is not a gap: the ratio is the
whole of what the model uses. It does mean a fitted row's `a` is only as
meaningful as the `w` it was divided by, which is why `fit_closed_vessel`
writes both and leaves `web` in `uncalibrated` unless the caller says the
geometry was measured too.

ON TRUSTING THIS
----------------
A fit can only be as good as the grain shape it was given. If the sample
geometry is not known, the form correction is guesswork wearing a
correction's clothes, and `grain_known=False` blocks it rather than
letting it silently bias the answer in a new direction.
"""

import math

import numpy as np

from .deflagration import (burnt_fraction_at, closed_vessel_pmax,
                           free_volume_terms)
from .fuels import form_factor

#: Burnt-fraction window the regression uses. Below it the record is
#: still the igniter's; above it sigma -> 0 for a degressive grain and
#: dividing by it amplifies noise without limit.
Z_WINDOW = (0.1, 0.9)

HEAT_MODELS = ('none', 'scaled', 'convective')


def _z_history(prop, charge_kg, volume_m3, t, p, heat_loss='none',
               h_c=0.0, wall_area=0.0, T_wall=300.0):
    """Burnt fraction at each sample, with the chosen heat treatment.

    'none'        adiabatic - the biased baseline, kept so the report can
                  show what the correction is worth
    'scaled'      one number from the record itself: the shortfall of the
                  measured peak against the theoretical one is taken as a
                  uniform energy loss. Cheap, needs no extra inputs, and
                  gets the sign and rough size right
    'convective'  march Q = h_c A_w (T - T_wall) forward. The honest one,
                  and the one that needs an h_c nobody measured
    """
    if heat_loss not in HEAT_MODELS:
        raise ValueError(f'heat_loss must be one of {HEAT_MODELS}')
    A, B = free_volume_terms(prop, charge_kg, volume_m3)
    n = len(t)
    z = np.zeros(n)

    if heat_loss == 'scaled':
        # p_meas/p_theory at the peak is the fraction of the energy that
        # survived; fold it into the propellant force for the inversion
        eff = float(np.max(p)) / closed_vessel_pmax(prop, charge_kg,
                                                    volume_m3)
        eff = min(max(eff, 1e-6), 1.0)
        den = charge_kg * prop.force * eff - p * B
        return np.where(den > 0.0, p * A / np.where(den > 0.0, den, 1.0), 0.0)

    q = 0.0
    for i in range(n):
        z[i] = burnt_fraction_at(prop, charge_kg, volume_m3, float(p[i]),
                                 u_lost=q)
        if heat_loss == 'convective' and h_c > 0.0 and wall_area > 0.0:
            m = max(z[i], 1e-12) * charge_kg
            v_free = A + z[i] * B
            T = p[i] * v_free / (m * prop.R)
            if i + 1 < n:
                q += h_c * wall_area * max(T - T_wall, 0.0) * (t[i + 1] - t[i])
    return z


def reduce_closed_vessel(t, p, prop, charge_kg, volume_m3,
                         heat_loss='none', h_c=0.0, wall_area=0.0,
                         T_wall=300.0, form_correction=True,
                         z_window=Z_WINDOW, grain_known=True):
    """One pass of the reduction. Returns a dict with `n`, `a_over_w`,
    `a`, the fitted window and the residual.

    Set `form_correction=False` to reproduce the naive answer - which is
    what the test suite uses to show the correction is not cosmetic.
    """
    if not grain_known and form_correction and prop.form != 'neutral':
        raise ValueError(
            "the grain shape of the sample was not established, so the "
            "form correction would divide by a guessed surface law and "
            "trade one bias for another. Calibrate on a neutral-burning "
            "sample, or pass grain_known=True once the geometry is known.")
    t = np.asarray(t, float)
    p = np.asarray(p, float)
    if len(t) != len(p) or len(t) < 8:
        raise ValueError('need at least 8 aligned (t, p) samples')

    z = _z_history(prop, charge_kg, volume_m3, t, p, heat_loss=heat_loss,
                   h_c=h_c, wall_area=wall_area, T_wall=T_wall)
    dz = np.gradient(z, t)
    sigma = (np.array([form_factor(prop, float(v)) for v in z])
             if form_correction else np.ones_like(z))

    lo, hi = z_window
    ok = (z > lo) & (z < hi) & (dz > 0.0) & (sigma > 1e-6) & (p > 0.0)
    if ok.sum() < 5:
        raise ValueError(
            f'only {int(ok.sum())} usable samples inside z in {z_window} - '
            f'the record does not cover enough of the burn to fit')

    y = np.log(dz[ok] / sigma[ok])
    x = np.log(p[ok])
    slope, intercept = np.polyfit(x, y, 1)
    resid = float(np.sqrt(np.mean((y - (slope * x + intercept)) ** 2)))
    a_over_w = math.exp(intercept)
    return dict(n=float(slope), a_over_w=a_over_w,
                a=a_over_w * prop.web, rms_log_residual=resid,
                n_samples=int(ok.sum()),
                p_window=(float(p[ok].min()), float(p[ok].max())),
                heat_loss=heat_loss, form_correction=form_correction)


def _nelder_mead(f, x0, step, tol=1e-10, max_iter=400):
    """Two-parameter Nelder-Mead. Hand-written because this repo has no
    scipy (checked: requirements.txt is numpy/matplotlib/pillow/Qt) and
    the refinement is not worth a dependency."""
    pts = [np.array(x0, float)]
    for i in range(len(x0)):
        q = np.array(x0, float)
        q[i] += step[i]
        pts.append(q)
    vals = [f(q) for q in pts]
    for _ in range(max_iter):
        order = np.argsort(vals)
        pts = [pts[i] for i in order]
        vals = [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) <= tol * (abs(vals[0]) + tol):
            break
        centroid = np.mean(pts[:-1], axis=0)
        xr = centroid + (centroid - pts[-1])
        fr = f(xr)
        if fr < vals[0]:
            xe = centroid + 2.0 * (centroid - pts[-1])
            fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = centroid + 0.5 * (pts[-1] - centroid)
            fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                for i in range(1, len(pts)):
                    pts[i] = pts[0] + 0.5 * (pts[i] - pts[0])
                    vals[i] = f(pts[i])
    i = int(np.argmin(vals))
    return pts[i], vals[i]


def _forward_p(prop, charge_kg, volume_m3, t, n, a_over_w, z0):
    """p(t) of a closed vessel for a trial burn law, integrated with the
    same explicit march the reduction inverts. Used only by the
    refinement, so it stays deliberately simple."""
    A, B = free_volume_terms(prop, charge_kg, volume_m3)
    z = z0
    out = np.empty(len(t))
    for i, ti in enumerate(t):
        v_free = A + z * B
        p = z * charge_kg * prop.force / v_free if v_free > 0 else 0.0
        out[i] = p
        if i + 1 < len(t):
            dt = t[i + 1] - ti
            sub = 8
            for _ in range(sub):
                v_free = A + z * B
                p_now = z * charge_kg * prop.force / v_free
                z = min(z + form_factor(prop, z) * a_over_w
                        * p_now ** n * dt / sub, 1.0)
    return out


def fit_closed_vessel(t, p, prop, charge_kg, volume_m3, heat_loss='scaled',
                      h_c=0.0, wall_area=0.0, T_wall=300.0,
                      z_window=Z_WINDOW, grain_known=True, refine=True,
                      web_measured=False, source=''):
    """Fit `n` and `a` to a closed-vessel record and return
    `(fitted_propellant, report)`.

    The report carries the exponent under all three treatments, which is
    the point: `n_raw` against `n_form` is the size of the form-function
    bug, and `n_form` against `n_form_heat` the size of the heat one.
    """
    from dataclasses import replace

    raw = reduce_closed_vessel(t, p, prop, charge_kg, volume_m3,
                               heat_loss='none', form_correction=False,
                               z_window=z_window, grain_known=True)
    form = reduce_closed_vessel(t, p, prop, charge_kg, volume_m3,
                                heat_loss='none', form_correction=True,
                                z_window=z_window, grain_known=grain_known)
    best = reduce_closed_vessel(t, p, prop, charge_kg, volume_m3,
                                heat_loss=heat_loss, h_c=h_c,
                                wall_area=wall_area, T_wall=T_wall,
                                form_correction=True, z_window=z_window,
                                grain_known=grain_known)

    n_fit, aw_fit = best['n'], best['a_over_w']
    rms = float('nan')
    if refine:
        t = np.asarray(t, float)
        p = np.asarray(p, float)
        z0 = burnt_fraction_at(prop, charge_kg, volume_m3, float(p[0]))
        scale = max(float(np.max(p)), 1.0)

        def cost(q):
            nn, log_aw = float(q[0]), float(q[1])
            if not 0.0 < nn < 3.0:
                return 1e30
            try:
                pred = _forward_p(prop, charge_kg, volume_m3, t, nn,
                                  math.exp(log_aw), z0)
            except (ValueError, OverflowError):
                return 1e30
            return float(np.mean(((pred - p) / scale) ** 2))

        q, val = _nelder_mead(cost, [n_fit, math.log(aw_fit)],
                              [0.05, 0.2])
        if val < 1e29:
            n_fit, aw_fit = float(q[0]), math.exp(float(q[1]))
            rms = math.sqrt(val) * scale

    unc = tuple(f for f in prop.uncalibrated
                if f not in ('a', 'n', 'p_valid_min', 'p_valid_max')
                and not (web_measured and f == 'web'))
    fitted = replace(prop, n=n_fit, a=aw_fit * prop.web,
                     p_valid_min=float(np.min(p)), p_valid_max=float(np.max(p)),
                     uncalibrated=unc)
    report = dict(
        n_raw=raw['n'], n_form=form['n'], n_form_heat=best['n'],
        n=n_fit, a_over_w=aw_fit, a=fitted.a,
        form_bias=form['n'] - raw['n'],
        heat_bias=best['n'] - form['n'],
        heat_loss=heat_loss,
        p_max_measured=float(np.max(p)),
        p_max_theoretical=closed_vessel_pmax(prop, charge_kg, volume_m3),
        rms_pressure_residual=rms,
        p_valid=(fitted.p_valid_min, fitted.p_valid_max),
        still_uncalibrated=unc,
        source=source,
    )
    report['energy_retained'] = (report['p_max_measured']
                                 / report['p_max_theoretical'])
    return fitted, report
