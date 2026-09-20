"""HD1-1: a 0-D gas-generation model for a deflagrating (HD 1.3) charge.

WHY THIS IS NOT A blastFoam CASE
--------------------------------
HD 1.3 material deflagrates: a subsonic, pressure-dependent burn, not a
detonation. There is no CJ state, no detonation velocity and no shock to
resolve at the source, so the JWL + `initiation.points` path in
`solvers/foam/` models the wrong physics entirely. Entering an HD1.3
charge as a "TNT equivalent" fails in the dangerous direction: too fast a
rise, too high a peak, too short a duration - an impulsive load where the
real one is quasi-static.

What actually loads a structure is the **quasi-static pressure** that
builds while the charge burns inside a confinement, and then the outflow
once it vents. That is a lumped-volume problem, and solving it here costs
milliseconds. An explicit compressible CFD solve at acoustic CFL needs
~5e5 steps for half a second of burning, which is why the split is
0-D for the burn and CFD only for the vented jet - not a shortcut, the
only route that finishes. See TODO.md HD1.

WHAT THIS MODULE SOLVES
-----------------------
Three states in a single well-mixed chamber:

    Z    fraction of the propellant burnt          [-]
    m    product-gas mass currently in the chamber [kg]
    E    internal energy of that gas               [J]

    dZ/dt = (sigma(Z) / w0) * a * p**n                 Vieille + form function
    dm/dt = C * dZ/dt - mdot_out
    dE/dt = C * dZ/dt * cv * T_flame - mdot_out * cp * T

with the Noble-Abel (covolume) equation of state, which is the standard
EOS for propellant gases at the hundreds-of-bar densities reached here and
the reason an ideal-gas model over-predicts the vented mass:

    p * (V0 - C*(1 - Z)/rho_p - b*m) = m * R * T

The free volume subtracts BOTH the solid propellant not yet burnt and the
covolume the product gas itself occupies.

VERIFICATION
------------
Closed vessel (`vent_area = 0`) has an exact analytic limit, and
`closed_vessel_pmax` returns it:

    Z -> 1,  m -> C,  T -> T_flame,  p -> lambda*C / (V0 - b*C)

because lambda = (gamma - 1) * cv * T_flame = R * T_flame by definition of
the propellant force constant. `tests/test_deflagration.py` pins the
solver against that limit, against mass and energy conservation, and
against the monotonicity the burn law implies.

STATUS OF THE NUMBERS
---------------------
The material table lives in `core/fuels.py` and is re-exported here, so
`deflagration.PROPELLANTS` keeps working. Every row is a REPRESENTATIVE
LITERATURE RANGE for a class of material, not product data, and nothing
is quotable without a closed-vessel test of the actual material. See that
module's docstring for why the table is separate and what `calibrated`
means.
"""

import math

from . import scenario as _scenario
from .fuels import (Propellant, PROPELLANTS, PROPELLANT_NAMES,  # noqa: F401
                    form_factor)

#: Ambient back-pressure for the vent [Pa]. Matches core.constants.P_AIR.
P_AMB = 101325.0

#: Web fraction below which a grain counts as burnt out. See the snap in
#: `simulate`: a degressive grain never reaches Z = 1 in finite time.
_BURNOUT_EPS = 1.0e-9


def closed_vessel_pmax(prop, charge_kg, volume_m3):
    """Analytic peak pressure [Pa] of a CLOSED vessel, all propellant burnt.

        p_max = force * C / (V0 - b * C)

    This is the exact limit `simulate(vent_area=0)` must approach, and it
    is what `tests/test_deflagration.py` pins the integrator against.
    Raises if the charge cannot fit: at C >= V0/b the covolume alone fills
    the vessel and the Noble-Abel pressure is unbounded - a loading
    density no real magazine reaches, but an easy way to get silent
    nonsense out of the model.
    """
    free = volume_m3 - prop.covolume * charge_kg
    if free <= 0.0:
        raise ValueError(
            f'charge {charge_kg:g} kg has a co-volume of '
            f'{prop.covolume * charge_kg:g} m^3, which fills or exceeds the '
            f'{volume_m3:g} m^3 chamber - the Noble-Abel pressure is '
            f'unbounded there. Reduce the charge or enlarge the chamber.')
    return prop.force * charge_kg / free


#: Fraction of the charge an igniter converts before the burn carries
#: itself. A starter charge is a small part of the round; it is raised
#: only when that much gas cannot hold the deflagration limit.
Z_IGN_DEFAULT = 0.01


def sustains(prop, charge_kg, volume_m3):
    """Can this loading density reach its own deflagration limit?

    If the pressure the charge can generate with EVERYTHING burnt still
    sits below `p_extinction`, the material lights and goes out. That is
    a real and useful answer about a magazine - a small charge in a large
    room cannot sustain combustion - so `simulate` reports it as a result
    with `stop_reason = 'cannot sustain'` rather than raising.
    """
    if prop.p_extinction <= 0.0:
        return True
    return closed_vessel_pmax(prop, charge_kg, volume_m3) > prop.p_extinction


def ignition_fraction(prop, charge_kg, volume_m3, p_ign):
    """Burnt fraction Z0 whose product gas alone brings the chamber to
    `p_ign` [Pa]. Closed form, from the Noble-Abel EOS at T = T_flame:

        p (V0 - C(1-Z)/rho - b C Z) = C Z R T_flame = C Z * force
    =>  Z = p (V0 - C/rho) / (C (force - p (1/rho - b)))

    WHY IGNITION HAS TO BE MODELLED AT ALL. Once a low-pressure
    extinction limit exists, a burn cannot start itself: seeding a
    whisker of gas leaves the chamber at ambient, which is BELOW the
    limit, so the burn rate is zero and nothing ever happens. That is not
    a numerical nuisance - it is the physics. A real HD 1.3 event is
    igniter-driven, and the model has to be too.

    Taking the starter gas from the propellant itself, rather than adding
    igniter mass, is what keeps the closed-vessel limit exact: all C
    still ends up as gas, so p_max is untouched and the analytic check
    stays the model's own verification.
    """
    if p_ign <= 0.0:
        raise ValueError('ignition pressure must be positive')
    if p_ign <= prop.p_extinction:
        raise ValueError(
            f'ignition pressure {p_ign:g} Pa is at or below the extinction '
            f'limit {prop.p_extinction:g} Pa - the charge would go out as '
            f'soon as it was lit')
    solid_v = charge_kg / prop.rho
    denom = charge_kg * (prop.force - p_ign * (1.0 / prop.rho - prop.covolume))
    if denom <= 0.0 or volume_m3 <= solid_v:
        raise ValueError(
            f'cannot reach an ignition pressure of {p_ign:g} Pa in a '
            f'{volume_m3:g} m^3 chamber holding {charge_kg:g} kg')
    Z0 = p_ign * (volume_m3 - solid_v) / denom
    if not 0.0 < Z0 <= 1.0:
        raise ValueError(
            f'an ignition pressure of {p_ign:g} Pa needs {Z0:.3g} of the '
            f'charge burnt, which is not a fraction - lower p_ign or '
            f'enlarge the chamber')
    return Z0


def _vent_mdot(p, T, prop, area, cd, p_amb):
    """Mass flow [kg/s] out of a vent of `area`, isentropic, choked-aware.

    Returns 0 while the chamber is below ambient - this model has no
    inflow, and a magazine that has vented down to ambient has nothing
    left to drive.
    """
    if area <= 0.0 or p <= p_amb or T <= 0.0:
        return 0.0
    g = prop.gamma
    crit = ((g + 1.0) / 2.0) ** (g / (g - 1.0))
    coef = cd * area * p / math.sqrt(prop.R * T)
    if p / p_amb >= crit:                      # choked
        return coef * math.sqrt(g) * (2.0 / (g + 1.0)) ** ((g + 1.0)
                                                           / (2.0 * (g - 1.0)))
    pr = p_amb / p                             # subsonic
    return coef * math.sqrt(
        2.0 * g / (g - 1.0) * (pr ** (2.0 / g) - pr ** ((g + 1.0) / g)))


def _pressure(prop, charge_kg, volume_m3, Z, m, E):
    """(p, T, V_free) from the Noble-Abel EOS. `Z` is the OVERALL burnt
    fraction of the charge - the mass-weighted mean over the cohorts."""
    solid = charge_kg * (1.0 - Z) / prop.rho
    free = volume_m3 - solid - prop.covolume * m
    if free <= 1e-12 or m <= 1e-15:
        return P_AMB, 0.0, max(free, 1e-12)
    T = E / (m * prop.cv)
    if T <= 0.0:
        return P_AMB, 0.0, free
    return m * prop.R * T / free, T, free


def _derivs(prop, charge_kg, volume_m3, area, cd, p_amb, fracs, t_ign,
            state, t):
    """d/dt of (Z_0 .. Z_{k-1}, m, E) at time `t`.

    Non-autonomous, because cohorts light at their own times. Every
    cohort sees the SAME chamber pressure, which is why they are
    integrated together - see core/scenario.py on why convolution does
    not work here.
    """
    k = len(fracs)
    Zs, m, E = state[:k], state[k], state[k + 1]
    z_total = sum(f * Z for f, Z in zip(fracs, Zs))
    p, T, _free = _pressure(prop, charge_kg, volume_m3, z_total, m, E)
    # The pressure is used RAW here. It used to be max(p, p_amb), an
    # ambient floor that silently made extinction impossible: a magazine
    # that had vented down to atmospheric went on burning for ever at the
    # ambient rate. Below the low-pressure deflagration limit a solid
    # propellant does not sustain a flame, and that is now what happens.
    burning = p >= prop.p_extinction
    dZs = []
    for Z, ti in zip(Zs, t_ign):
        if Z >= 1.0 or t < ti or not burning:
            dZs.append(0.0)
        else:
            dZs.append(form_factor(prop, Z) * prop.a * (p ** prop.n)
                       / prop.web)
    mdot_gen = charge_kg * sum(f * dZ for f, dZ in zip(fracs, dZs))
    mdot_out = _vent_mdot(p, T, prop, area, cd, p_amb)
    mdot_out = min(mdot_out, m / 1e-9) if m <= 0.0 else mdot_out
    return tuple(dZs) + (
        mdot_gen - mdot_out,
        mdot_gen * prop.cv * prop.T_flame - mdot_out * prop.cp * T)


def simulate(prop, charge_kg, volume_m3, vent_area=0.0, cd=0.8,
             t_end=1.0, p_amb=P_AMB, max_steps=500_000, n_out=1000,
             p_ign=None, scenario=None):
    """Integrate the chamber to `t_end` [s]. RK4 with an adaptive step.

    Returns a dict with the sampled trace (`t, p, T, Z, m, mdot_out`,
    about `n_out` points) plus:
        p_max, t_p_max   the peak over EVERY step, not just the samples
        burnt_out        True if Z reached 1 before t_end
        steps            steps actually taken
        hit_step_cap     True if `max_steps` stopped it early - the trace
                         is then a partial record and `p_max` is a lower
                         bound, so callers must check this rather than
                         quietly trusting a truncated peak
        extinguished     True if the burn went out below the propellant's
                         low-pressure deflagration limit with propellant
                         still unburnt
        stop_reason      '' | 'burnt out and vented' | 'extinction'
                         | 'step cap' | 't_end'
        Z0               burnt fraction the igniter started from
        extrapolated_fraction
                         share of the BURNING time (not of `t_end`) spent
                         with the chamber pressure outside the window the
                         Vieille pair was measured over. A closed-vessel
                         calibration lives at tens of MPa and a vented
                         magazine at ~1 MPa, so this routinely comes back
                         at 1.0 - and a peak pressure quoted without it is
                         a two-decade extrapolation presented as a
                         measurement. See core/fuels.py.

    `p_ign` [Pa] is the pressure the igniter brings the chamber to before
    the propellant's own burn takes over; `None` picks twice the
    extinction limit, or the legacy whisker-of-gas seed for a propellant
    that declares no limit. The starter gas comes from the charge itself,
    so the closed-vessel limit is untouched - see `ignition_fraction`.

    The step is set by the physics, not by a fixed dt: at most 1 % of the
    burn or 5 % of the chamber mass per step, capped at `t_end / 50`.  It
    must be able to GROW - an earlier version seeded it from a fixed
    1 microsecond and never grew, so a 5 s composite burn hit the step cap
    at t = 2 s and reported a peak 87 % low.

    `vent_area = 0` is the closed vessel, whose peak must match
    `closed_vessel_pmax` - that is the model's own verification and the
    first thing to re-run after any change here.
    """
    if charge_kg <= 0.0 or volume_m3 <= 0.0:
        raise ValueError('charge and chamber volume must both be positive')
    closed_vessel_pmax(prop, charge_kg, volume_m3)   # raises if it cannot fit
    if scenario is None:
        scenario = _scenario.uniform()
    coh = scenario.cohorts()
    fracs = tuple(f for f, _ti in coh)
    t_ign = tuple(ti for _f, ti in coh)

    # seed. With an extinction limit the burn cannot light itself, so the
    # igniter is part of the model; without one, keep the original
    # whisker of gas so a propellant that declares no limit behaves
    # exactly as it did before.
    can_sustain = sustains(prop, charge_kg, volume_m3)
    if p_ign is not None:
        Z = ignition_fraction(prop, charge_kg, volume_m3, p_ign)
    elif prop.p_extinction <= 0.0:
        Z = 1.0e-9                      # legacy: no limit, no igniter
    elif not can_sustain:
        # lights and goes out; the loop's extinction test ends it at once
        Z = Z_IGN_DEFAULT
    else:
        p_cap = closed_vessel_pmax(prop, charge_kg, volume_m3)
        p_need = min(1.05 * prop.p_extinction,
                     0.5 * (prop.p_extinction + p_cap))
        Z = max(Z_IGN_DEFAULT,
                ignition_fraction(prop, charge_kg, volume_m3, p_need))
    Z0 = Z
    # The igniter lights what is already exposed at t = 0, not the whole
    # stack, so its gas is charged to the cohorts lit then. With one
    # cohort this is exactly the old seed.
    lit_now = sum(f for f, ti in zip(fracs, t_ign) if ti <= 0.0)
    per = min(Z0 / lit_now, 1.0) if lit_now > 0.0 else 0.0
    Zs = [per if ti <= 0.0 else 0.0 for ti in t_ign]
    z_total = sum(f * Z for f, Z in zip(fracs, Zs))
    m = charge_kg * z_total
    E = m * prop.cv * prop.T_flame
    t = 0.0
    h_max = t_end / 50.0
    sample_every = t_end / max(n_out, 2)

    out = dict(t=[], p=[], T=[], Z=[], m=[], mdot_out=[], lit=[])
    p_max, t_p_max = 0.0, 0.0
    last_sample = -1.0

    def overall():
        return sum(f * Z for f, Z in zip(fracs, Zs))

    def state_pT():
        return _pressure(prop, charge_kg, volume_m3, overall(), m, E)[:2]

    def record():
        p, T = state_pT()
        out['t'].append(t)
        out['p'].append(p)
        out['T'].append(T)
        out['Z'].append(min(overall(), 1.0))
        out['m'].append(m)
        out['mdot_out'].append(_vent_mdot(p, T, prop, vent_area, cd, p_amb))
        out['lit'].append(sum(f for f, ti in zip(fracs, t_ign) if ti <= t))

    record()
    last_sample = 0.0
    args = (prop, charge_kg, volume_m3, vent_area, cd, p_amb, fracs, t_ign)
    nZ = len(fracs)
    steps = 0
    stop_reason = 't_end'
    extinguished = False
    t_burning = 0.0
    t_outside = 0.0
    while t < t_end and steps < max_steps:
        steps += 1
        s = tuple(Zs) + (m, E)
        k1 = _derivs(*args, s, t)
        dZ_max = max(k1[:nZ])
        h = h_max
        if dZ_max > 0.0:
            h = min(h, 0.005 / dZ_max)         # <= 0.5 % of the burn
            # land ON Z = 1, never past it. Clipping an overshoot leaves
            # m and E integrated against a dZ taken beyond burn-out, which
            # showed up as m_end = 1.00066 * C - more gas than propellant.
            for Z, dZ in zip(Zs, k1[:nZ]):
                if dZ > 0.0:
                    h = min(h, (1.0 - Z) / dZ)
        if k1[nZ] < 0.0 and m > 0.0:
            # 1 %, not 5 %: the vent stops at ambient (there is no inflow
            # in this model), so a step that dumps too much mass at once
            # lands the chamber BELOW ambient and strands it there. At 5 %
            # a large vent finished at 0.58 bar against an ambient of 1.01.
            h = min(h, 0.01 * m / (-k1[nZ]))
        # Land ON the next ignition, never across it. A cohort lighting
        # inside a step is a discontinuity in the right-hand side, and
        # RK4 averaged across one would smear the entrainment the whole
        # scenario exists to represent.
        later = [ti for ti in t_ign if ti > t + 1.0e-15]
        if later:
            h = min(h, min(later) - t)
        h = max(min(h, t_end - t), 1.0e-12)

        def add(base, k, f):
            return tuple(b + f * kk for b, kk in zip(base, k))

        k2 = _derivs(*args, add(s, k1, h / 2.0), t + h / 2.0)
        k3 = _derivs(*args, add(s, k2, h / 2.0), t + h / 2.0)
        k4 = _derivs(*args, add(s, k3, h), t + h)
        nxt = [s[i] + h / 6.0 * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i])
               for i in range(nZ + 2)]
        Zs = [min(v, 1.0) for v in nxt[:nZ]]
        m, E = nxt[nZ], nxt[nZ + 1]
        # A degressive grain has sigma(Z) = (1 - Z)^(2/3), so dZ/dt -> 0 and
        # Z approaches 1 asymptotically, never reaching it. Combined with
        # the land-on-Z=1 step limit that grinds the integrator to a halt -
        # one case took the full 500k step cap to cover a sliver of web.
        # Snap the last 1e-9 to burnt out, converting the remaining
        # propellant to gas so mass and energy stay exact.
        for i, Z in enumerate(Zs):
            if 0.0 < 1.0 - Z < _BURNOUT_EPS:
                left = (1.0 - Z) * fracs[i]
                Zs[i] = 1.0
                m += charge_kg * left
                E += charge_kg * left * prop.cv * prop.T_flame
        m = max(m, 0.0)
        E = max(E, 0.0)
        # Attribute the step BEFORE advancing t: k1 was evaluated at the
        # start of it, so that is the pressure the burn law saw.
        z_start = sum(f * Z for f, Z in zip(fracs, s[:nZ]))
        p_start = _pressure(prop, charge_kg, volume_m3, z_start, s[nZ],
                            s[nZ + 1])[0]
        if dZ_max > 0.0:
            t_burning += h
            if not prop.in_validity_window(p_start):
                t_outside += h
        t += h

        p_now, _T = state_pT()
        if p_now > p_max:
            p_max, t_p_max = p_now, t
        if t - last_sample >= sample_every:
            record()
            last_sample = t
        all_burnt = all(Z >= 1.0 for Z in Zs)
        # burnt out and vented down: nothing left to integrate
        if all_burnt and vent_area > 0.0 and p_now <= p_amb * 1.001:
            stop_reason = 'burnt out and vented'
            break
        # Went out below the deflagration limit with propellant left.
        # Terminal ONLY once everything has been lit: while cohorts are
        # still to come, a chamber below the limit is waiting, not dead.
        if (not all_burnt and p_now < prop.p_extinction
                and t >= max(t_ign)):
            extinguished = True
            stop_reason = 'extinction'
            break

    if out['t'][-1] < t:
        record()
    if steps >= max_steps:
        stop_reason = 'step cap'
    if extinguished and t_burning <= 0.0:
        # it never burned at all, which is a different statement about
        # the magazine than "it burned and then went out"
        stop_reason = 'cannot sustain'
    out['p_max'] = p_max
    out['t_p_max'] = t_p_max
    # every cohort, not a leaked loop variable: with cohorts there is no
    # single Z any more, and reading one was a real bug the scenario
    # tests caught
    out['burnt_out'] = all(Z >= 1.0 for Z in Zs)
    out['steps'] = steps
    out['hit_step_cap'] = steps >= max_steps
    out['extinguished'] = extinguished
    out['stop_reason'] = stop_reason
    out['Z0'] = Z0
    out['scenario'] = scenario
    # Always reported, never implied. Uniform ignition is the laboratory
    # condition; a magazine answer computed under it is one whose
    # entrainment was assumed away, and the report has to say so.
    out['scenario_kind'] = scenario.kind
    out['calibration_only_scenario'] = scenario.calibration_only
    out['n_cohorts'] = len(fracs)
    out['extrapolated_fraction'] = (t_outside / t_burning
                                    if t_burning > 0.0 else 0.0)
    return out


def peak(result):
    """(p_max [Pa], t at the peak [s]) - taken over every integration step."""
    return result['p_max'], result['t_p_max']
