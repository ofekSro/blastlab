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
`PROPELLANTS` rows are REPRESENTATIVE LITERATURE RANGES for classes of
material, not a calibrated table for any specific product, and the burn
coefficients in particular vary between lots. Nothing here is quotable
without a closed-vessel test of the actual material - the same standard
`materials.py` holds its non-TNT afterburn rows to. `calibrated=False` on
every row is deliberate and is checked by the test suite.
"""

import math
from dataclasses import dataclass

#: Ambient back-pressure for the vent [Pa]. Matches core.constants.P_AIR.
P_AMB = 101325.0

#: Web fraction below which a grain counts as burnt out. See the snap in
#: `simulate`: a degressive grain never reaches Z = 1 in finite time.
_BURNOUT_EPS = 1.0e-9


@dataclass(frozen=True)
class Propellant:
    """A deflagrating (HD 1.3) material.

    force        lambda = R * T_flame [J/kg]. The "impetus" or "force
                 constant" of interior ballistics; sets the pressure a
                 given mass reaches in a given volume.
    covolume     b [m^3/kg]. The Noble-Abel co-volume - roughly the volume
                 the product molecules themselves occupy. ~1e-3 for most
                 propellant gases, i.e. 1 litre per kg, which is NOT
                 negligible against a chamber of a few litres.
    rho          solid density [kg/m^3]
    T_flame      isochoric flame temperature [K]
    a, n         Vieille burn law r = a * p**n, r in m/s with p in Pa
    gamma        ratio of specific heats of the product gas
    web          w0 [m]: the burning distance from the surface to
                 burn-out. For a slab burning on both faces this is the
                 half-thickness; dZ/dt = sigma(Z) * r / w0.
    form         'neutral' | 'degressive' | 'progressive'
    theta        progressivity, used only by form='progressive'
    calibrated   False everywhere on purpose - see the module docstring.
    """
    force: float
    covolume: float
    rho: float
    T_flame: float
    a: float
    n: float
    gamma: float = 1.25
    web: float = 1.0e-3
    form: str = 'degressive'
    theta: float = 1.0
    calibrated: bool = False

    @property
    def R(self):
        """Specific gas constant [J/(kg K)] - force / flame temperature."""
        return self.force / self.T_flame

    @property
    def cv(self):
        return self.R / (self.gamma - 1.0)

    @property
    def cp(self):
        return self.gamma * self.cv


#: Representative classes, NOT product data. See the module docstring.
#: force/T_flame/covolume are the usual textbook ranges for each class;
#: the Vieille pair is where lot-to-lot variation really lives.
PROPELLANTS = {
    # nitrocellulose only - the lowest-energy, coolest of the three
    'single_base': Propellant(force=0.95e6, covolume=1.05e-3, rho=1600.0,
                              T_flame=2500.0, a=5.0e-8, n=0.85,
                              gamma=1.25, web=1.0e-3, form='degressive'),
    # NC + nitroglycerine - hotter and faster
    'double_base': Propellant(force=1.10e6, covolume=1.00e-3, rho=1650.0,
                              T_flame=3000.0, a=8.0e-8, n=0.90,
                              gamma=1.24, web=1.0e-3, form='degressive'),
    # AP/HTPB-like composite - lower pressure exponent, near-neutral burn
    'composite': Propellant(force=1.00e6, covolume=1.10e-3, rho=1750.0,
                            T_flame=3000.0, a=3.0e-6, n=0.35,
                            gamma=1.20, web=3.0e-3, form='neutral'),
}

PROPELLANT_NAMES = tuple(PROPELLANTS)


def form_factor(prop, Z):
    """sigma(Z) = S(Z)/S0, the burning surface relative to its initial value.

    neutral      a slab or a tube burning inward and outward at once, the
                 area changes cancel -> 1
    degressive   a sphere or a cord: the surface shrinks as it burns, and
                 for a sphere S ~ r^2 while the burnt fraction goes as
                 r^3, hence (1 - Z)^(2/3)
    progressive  a multi-perforated grain, whose internal perforations
                 grow faster than the outside shrinks -> 1 + theta*Z
    """
    Z = min(max(Z, 0.0), 1.0)
    if prop.form == 'neutral':
        return 1.0
    if prop.form == 'progressive':
        return 1.0 + prop.theta * Z
    return (1.0 - Z) ** (2.0 / 3.0)


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
    """(p, T, V_free) from the Noble-Abel EOS."""
    solid = charge_kg * (1.0 - Z) / prop.rho
    free = volume_m3 - solid - prop.covolume * m
    if free <= 1e-12 or m <= 1e-15:
        return P_AMB, 0.0, max(free, 1e-12)
    T = E / (m * prop.cv)
    if T <= 0.0:
        return P_AMB, 0.0, free
    return m * prop.R * T / free, T, free


def _derivs(prop, charge_kg, volume_m3, area, cd, p_amb, state):
    Z, m, E = state
    p, T, _free = _pressure(prop, charge_kg, volume_m3, Z, m, E)
    if Z >= 1.0:
        dZ = 0.0
    else:
        dZ = form_factor(prop, Z) * prop.a * (max(p, p_amb) ** prop.n) / prop.web
    mdot_gen = charge_kg * dZ
    mdot_out = _vent_mdot(p, T, prop, area, cd, p_amb)
    mdot_out = min(mdot_out, m / 1e-9) if m <= 0.0 else mdot_out
    return (dZ,
            mdot_gen - mdot_out,
            mdot_gen * prop.cv * prop.T_flame - mdot_out * prop.cp * T)


def simulate(prop, charge_kg, volume_m3, vent_area=0.0, cd=0.8,
             t_end=1.0, p_amb=P_AMB, max_steps=500_000, n_out=1000):
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

    # seed: a whisker of gas so T and p are defined at t = 0
    Z = 1.0e-9
    m = charge_kg * Z
    E = m * prop.cv * prop.T_flame
    t = 0.0
    h_max = t_end / 50.0
    sample_every = t_end / max(n_out, 2)

    out = dict(t=[], p=[], T=[], Z=[], m=[], mdot_out=[])
    p_max, t_p_max = 0.0, 0.0
    last_sample = -1.0

    def state_pT():
        return _pressure(prop, charge_kg, volume_m3, Z, m, E)[:2]

    def record():
        p, T = state_pT()
        out['t'].append(t)
        out['p'].append(p)
        out['T'].append(T)
        out['Z'].append(min(Z, 1.0))
        out['m'].append(m)
        out['mdot_out'].append(_vent_mdot(p, T, prop, vent_area, cd, p_amb))

    record()
    last_sample = 0.0
    args = (prop, charge_kg, volume_m3, vent_area, cd, p_amb)
    steps = 0
    while t < t_end and steps < max_steps:
        steps += 1
        s = (Z, m, E)
        k1 = _derivs(*args, s)
        h = h_max
        if k1[0] > 0.0:
            h = min(h, 0.005 / k1[0])          # <= 0.5 % of the burn
            # land ON Z = 1, never past it. Clipping an overshoot leaves
            # m and E integrated against a dZ taken beyond burn-out, which
            # showed up as m_end = 1.00066 * C - more gas than propellant.
            h = min(h, (1.0 - Z) / k1[0])
        if k1[1] < 0.0 and m > 0.0:
            # 1 %, not 5 %: the vent stops at ambient (there is no inflow
            # in this model), so a step that dumps too much mass at once
            # lands the chamber BELOW ambient and strands it there. At 5 %
            # a large vent finished at 0.58 bar against an ambient of 1.01.
            h = min(h, 0.01 * m / (-k1[1]))
        h = max(min(h, t_end - t), 1.0e-12)

        def add(base, k, f):
            return tuple(b + f * kk for b, kk in zip(base, k))

        k2 = _derivs(*args, add(s, k1, h / 2.0))
        k3 = _derivs(*args, add(s, k2, h / 2.0))
        k4 = _derivs(*args, add(s, k3, h))
        Z, m, E = (s[i] + h / 6.0 * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i])
                   for i in range(3))
        Z = min(Z, 1.0)
        # A degressive grain has sigma(Z) = (1 - Z)^(2/3), so dZ/dt -> 0 and
        # Z approaches 1 asymptotically, never reaching it. Combined with
        # the land-on-Z=1 step limit that grinds the integrator to a halt -
        # one case took the full 500k step cap to cover a sliver of web.
        # Snap the last 1e-9 to burnt out, converting the remaining
        # propellant to gas so mass and energy stay exact.
        if 0.0 < 1.0 - Z < _BURNOUT_EPS:
            left = 1.0 - Z
            Z = 1.0
            m += charge_kg * left
            E += charge_kg * left * prop.cv * prop.T_flame
        m = max(m, 0.0)
        E = max(E, 0.0)
        t += h

        p_now, _T = state_pT()
        if p_now > p_max:
            p_max, t_p_max = p_now, t
        if t - last_sample >= sample_every:
            record()
            last_sample = t
        # burnt out and vented down: nothing left to integrate
        if Z >= 1.0 and vent_area > 0.0 and p_now <= p_amb * 1.001:
            break

    if out['t'][-1] < t:
        record()
    out['p_max'] = p_max
    out['t_p_max'] = t_p_max
    out['burnt_out'] = Z >= 1.0
    out['steps'] = steps
    out['hit_step_cap'] = steps >= max_steps
    return out


def peak(result):
    """(p_max [Pa], t at the peak [s]) - taken over every integration step."""
    return result['p_max'], result['t_p_max']
