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
from dataclasses import replace as _dc_replace

from . import scenario as _scenario
from .fuels import (Propellant, PROPELLANTS, PROPELLANT_NAMES,  # noqa: F401
                    form_factor)

#: Ambient back-pressure for the vent [Pa]. Matches core.constants.P_AIR.
P_AMB = 101325.0

#: Web fraction below which a grain counts as burnt out. See the snap in
#: `simulate`: a degressive grain never reaches Z = 1 in finite time.
_BURNOUT_EPS = 1.0e-9

#: Cash-Karp RK4(5). Six stages, two answers: a fifth-order solution to
#: advance with and a fourth-order one to measure it against. Their
#: difference IS the local error estimate, which is what lets the step
#: be chosen from what the equations are doing rather than from a
#: heuristic about what they might do.
#:
#: This replaces a fixed-form RK4 whose step came from rate-based rules.
#: Those rules are blind in two ways that cost real answers here: they
#: cannot see a transient that is slow at the step start and violent
#: inside it, and a limiter on a NET rate sees nothing at all when two
#: large fluxes cancel - measured at one failing step, a burn feeding
#: 3.4 MW against a vent removing 3.35 MW left a net mass rate of
#: 5e-3 kg/s and a permitted step of 0.217 s, while the chamber held
#: 0.11 kg against an outflow of 0.73 kg/s.
_CK_NODES = (0.0, 1.0 / 5.0, 3.0 / 10.0, 3.0 / 5.0, 1.0, 7.0 / 8.0)
_CK_A = (
    (),
    (1.0 / 5.0,),
    (3.0 / 40.0, 9.0 / 40.0),
    (3.0 / 10.0, -9.0 / 10.0, 6.0 / 5.0),
    (-11.0 / 54.0, 5.0 / 2.0, -70.0 / 27.0, 35.0 / 27.0),
    (1631.0 / 55296.0, 175.0 / 512.0, 575.0 / 13824.0,
     44275.0 / 110592.0, 253.0 / 4096.0),
)
#: fifth-order weights (the solution that is kept)
_CK_B5 = (37.0 / 378.0, 0.0, 250.0 / 621.0, 125.0 / 594.0, 0.0,
          512.0 / 1771.0)
#: fourth-order weights (the yardstick)
_CK_B4 = (2825.0 / 27648.0, 0.0, 18575.0 / 48384.0, 13525.0 / 55296.0,
          277.0 / 14336.0, 1.0 / 4.0)

#: step-control tolerances and the factors that keep it from thrashing
_RTOL = 1.0e-8
_SAFETY = 0.9
_H_SHRINK_MIN = 0.1
_H_GROW_MAX = 5.0
_MAX_REJECTS = 60

#: Conservation residual, relative, above which a run is declared
#: broken. Cash-Karp holds this near machine precision on every case
#: measured; 1e-6 is loose enough that only a real failure trips it.
_CONSERVATION_TOL = 1.0e-6

#: THE BUG THIS INTEGRATOR WAS BROUGHT IN TO FIX, kept because it is the
#: reason the design says what it says. With the previous fixed-step RK4
#: and its rate-based limiters, a loading density above roughly
#: 50 kg/m^3 blew up in the ignition transient:
#:
#:     C/V = 200    reported 0.101 MPa against an analytic 275
#:     C/V = 100    reported 263 MPa against an analytic 122
#:
#: with stop_reason 't_end', 51 steps and no warning of any kind. It
#: survived because the suite only covered C/V of 0.5 to 5 - and C/V of
#: tens to hundreds is CLOSED-VESSEL density, the regime a calibration
#: lives in, so the one place the model had to be right was the one
#: place nothing looked.
#:
#: Cash-Karp returns 275.000 and 122.222 exactly, in fewer steps than the
#: old scheme took to get them wrong. The suite now spans 0.2 to 200.
_VERIFIED_LOADING_RANGE = (0.2, 200.0)

#: THE SAME FAILURE AGAIN, ONE LAYER UP - and this is why the check below
#: is on by default rather than offered.
#:
#: `n_cohorts` looks like a modelling choice and is a DISCRETISATION
#: parameter. A flame spread is continuous; cohorts replace it with n
#: instantaneous ignitions of C/n each. In a chamber that is already
#: quasi-steady - which is what a slow magazine fire produces - one such
#: step IS the entire pressure signal, so `p_max` is the size of the step
#: rather than a property of the fire. Measured on 5 kg in 1 m^3 vented
#: through 0.02 m^2 with chamber air, against the n-refined answer:
#:
#:     spread  0.5 s    n=20 is  +0.7 %      (converged)
#:     spread    2 s    n=20 is  +2.6 %
#:     spread   10 s    n=20 is   +37 %
#:     spread   60 s    n=20 is   +62 %      1.65 x ambient against 1.02
#:
#: The error grows with spread time because the slower the fire, the more
#: completely the chamber has settled between ignitions. So the model was
#: right where a fire is fast and wrong where it is slow - and a magazine
#: is the slow end. That is the third time this shape of bug has appeared
#: here (the integrator above, the chamber air in `air_mass`), and every
#: time the common factor is the same: verified in the regime it was
#: written for, applied in the one it was meant for.
#:
#: `scenario.cohorts()` claimed refining n "does not change the answer".
#: Splitting by mass makes it CONVERGE, first order - which is a weaker
#: statement, and the difference between them is a factor of 1.6.
_COHORT_TOL = 0.02

#: Air, for the chamber's own atmosphere (HD1-3-pre).
AIR_R = 287.05          # J/(kg K)
AIR_GAMMA = 1.4
AIR_CV = AIR_R / (AIR_GAMMA - 1.0)
AIR_T0 = 288.15         # K, the temperature the chamber air starts at


def air_mass(volume_m3, p0, T0=AIR_T0):
    """Mass of air [kg] initially filling the chamber.

    THE NUMBER THAT MAKES THIS NECESSARY. The model used to count only
    product gas, which is right where it was verified and wrong where it
    is applied:

        closed vessel   C/V = 50-200 kg/m3   air is under 3 % of the mass
        magazine        C/V = 0.1-5 kg/m3    air is comparable to the
                                             products, and often larger

    So the analytic closed-vessel check passed to 1e-6 and could never
    have caught this: the regime it pins is exactly the regime where the
    omission does not matter.

    `p0 = 0` means an evacuated vessel and returns 0, which is what keeps
    that analytic limit exactly as it was.
    """
    if p0 <= 0.0 or volume_m3 <= 0.0:
        return 0.0
    return p0 * volume_m3 / (AIR_R * T0)


def mixture(prop, m_p, m_a):
    """(R, cv, cp, gamma) of the product/air mixture, mass-weighted.

    Used for the chamber state AND for the vent. Leaving the products'
    own properties in `_vent_mdot` once air is present is a ~15 % error
    on the choked flow - the same size as the tolerance the CFD
    cross-check is run at, so it would be absorbed into the discharge
    coefficient and disappear.
    """
    m = m_p + m_a
    if m <= 0.0:
        return prop.R, prop.cv, prop.cp, prop.gamma
    yp, ya = m_p / m, m_a / m
    R = yp * prop.R + ya * AIR_R
    cv = yp * prop.cv + ya * AIR_CV
    cp = cv + R
    return R, cv, cp, (cp / cv if cv > 0 else prop.gamma)


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


def free_volume_terms(prop, charge_kg, volume_m3):
    """(A, B) such that the free gas volume at burnt fraction z is
    `A + z*B`:

        V_free(z) = (V0 - C/rho) + z * C * (1/rho - b)

    The solid that has not burnt yet and the co-volume of the gas that
    has both come out of the same chamber, and B is usually NEGATIVE -
    the gas occupies more space than the solid it came from.
    """
    A = volume_m3 - charge_kg / prop.rho
    B = charge_kg * (1.0 / prop.rho - prop.covolume)
    return A, B


def burnt_fraction_at(prop, charge_kg, volume_m3, p, u_lost=0.0):
    """Burnt fraction z whose gas holds the chamber at `p` [Pa].

    The exact inverse of the Noble-Abel closed-vessel pressure, from

        p * (A + z B) = z C lambda - (gamma - 1) * u_lost
    =>  z = (p A + (gamma - 1) u_lost) / (C lambda - p B)

    `u_lost` [J] is internal energy the gas has already given to the
    walls. It belongs here rather than in the caller because leaving it
    out is a REAL bias, not a refinement: a closed vessel loses several
    per cent of its energy by the time it peaks, and an adiabatic
    inversion reads that as less propellant burnt than really was -
    systematically, and more so late in the burn, which is exactly the
    shape that tilts a fitted pressure exponent. See core/calibration.py.
    """
    A, B = free_volume_terms(prop, charge_kg, volume_m3)
    den = charge_kg * prop.force - p * B
    if den <= 0.0:
        raise ValueError(
            f'no burnt fraction can hold {p:g} Pa in a {volume_m3:g} m^3 '
            f'chamber with {charge_kg:g} kg - the co-volume term has taken '
            f'over')
    return (p * A + (prop.gamma - 1.0) * u_lost) / den


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
    if volume_m3 <= charge_kg / prop.rho:
        raise ValueError(
            f'cannot reach an ignition pressure of {p_ign:g} Pa in a '
            f'{volume_m3:g} m^3 chamber holding {charge_kg:g} kg')
    Z0 = burnt_fraction_at(prop, charge_kg, volume_m3, p_ign)
    if not 0.0 < Z0 <= 1.0:
        raise ValueError(
            f'an ignition pressure of {p_ign:g} Pa needs {Z0:.3g} of the '
            f'charge burnt, which is not a fraction - lower p_ign or '
            f'enlarge the chamber')
    return Z0


def _vent_mdot(p, T, prop, area, cd, p_amb, m_p=None, m_a=0.0):
    """Mass flow [kg/s] out of a vent of `area`, isentropic, choked-aware.

    Returns 0 while the chamber is below ambient - this model has no
    inflow, and a magazine that has vented down to ambient has nothing
    left to drive.

    `m_p`/`m_a` give the MIXTURE its properties. What leaves the vent is
    whatever is in the chamber, so the choked flux has to use the
    mixture's gamma and R - see `mixture`. Omitting `m_p` keeps the
    products' own properties, which is the pre-HD1-3-pre behaviour and
    what an evacuated chamber reduces to anyway.
    """
    if area <= 0.0 or p <= p_amb or T <= 0.0:
        return 0.0
    if m_p is None:
        R, g = prop.R, prop.gamma
    else:
        R, _cv, _cp, g = mixture(prop, m_p, m_a)
    crit = ((g + 1.0) / 2.0) ** (g / (g - 1.0))
    coef = cd * area * p / math.sqrt(R * T)
    if p / p_amb >= crit:                      # choked
        return coef * math.sqrt(g) * (2.0 / (g + 1.0)) ** ((g + 1.0)
                                                           / (2.0 * (g - 1.0)))
    pr = p_amb / p                             # subsonic
    return coef * math.sqrt(
        2.0 * g / (g - 1.0) * (pr ** (2.0 / g) - pr ** ((g + 1.0) / g)))


def _pressure(prop, charge_kg, volume_m3, Z, m, E, m_a=0.0):
    """(p, T, V_free) from the Noble-Abel EOS. `Z` is the OVERALL burnt
    fraction of the charge - the mass-weighted mean over the cohorts.

    `m` is product gas, `m_a` the chamber's own air. The two share one
    temperature and their partial pressures add (Dalton):

        p = (m R_p + m_a R_a) T / (V_free - b m)

    The co-volume correction stays on the products alone; air at these
    densities is close enough to ideal that giving it one would be
    inventing a number. With `m_a = 0` every line below is what it was
    before HD1-3-pre, which is what keeps the analytic limit exact.
    """
    solid = charge_kg * (1.0 - Z) / prop.rho
    free = volume_m3 - solid - prop.covolume * m
    if free <= 1e-12 or (m + m_a) <= 1e-15:
        return P_AMB, 0.0, max(free, 1e-12)
    _R, cv_mix, _cp, _g = mixture(prop, m, m_a)
    T = E / ((m + m_a) * cv_mix)
    if T <= 0.0:
        return P_AMB, 0.0, free
    return (m * prop.R + m_a * AIR_R) * T / free, T, free


def _derivs(prop, charge_kg, volume_m3, area, cd, p_amb, fracs, t_ign,
            state, t, h_c=0.0, wall_area=0.0, T_wall=300.0):
    """d/dt of (Z_0 .. Z_{k-1}, m, E) at time `t`.

    Non-autonomous, because cohorts light at their own times. Every
    cohort sees the SAME chamber pressure, which is why they are
    integrated together - see core/scenario.py on why convolution does
    not work here.
    """
    """State is (Z_0..Z_{k-1}, m, E, m_a, m_out_p, m_out_a, E_out, Q_wall).

    The last four are ACCUMULATORS - everything that has left, whether
    through the vent or into the walls, integrated alongside everything
    that stayed. They cost one addition each and they turn conservation
    into an identity the run can check on itself:

        m   + m_out_p           == charge * z    products
        m_a + m_out_a           == m_a0          air
        E   + E_out  + Q_wall   == E_in          energy

    That is what `_conservation_residual` reads, and it is the difference
    between an integrator that fails and one that fails SILENTLY.

    HEAT LOSS is `Q_wall = h_c * A_w * (T - T_wall)`, the lumped
    convective law, and it is OFF by default (`h_c = 0`) for a reason
    that is not convenience: adiabatic is the CONSERVATIVE case for a
    pressure check. Removing heat lowers T and therefore p, so switching
    this on makes the structural load smaller. It exists because
    `core/calibration.py` already inverts FOR heat loss - a closed-vessel
    record reduced with `heat_loss='convective'` was being matched
    against a forward model that had none - and because the wall
    temperature the thermal path reports is only meaningful if the gas it
    came from actually gave that energy up.

    `T_wall` is held fixed, which over-states the loss late in a long
    burn as a real wall heats up. That errs towards a lower pressure,
    i.e. NOT conservatively, which is the second reason the default is
    off rather than a plausible-looking number.
    """
    k = len(fracs)
    Zs, m, E, m_a = state[:k], state[k], state[k + 1], state[k + 2]
    z_total = sum(f * Z for f, Z in zip(fracs, Zs))
    p, T, _free = _pressure(prop, charge_kg, volume_m3, z_total, m, E, m_a)
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
    mdot_out = _vent_mdot(p, T, prop, area, cd, p_amb, m_p=m, m_a=m_a)
    mdot_out = min(mdot_out, m / 1e-9) if m <= 0.0 else mdot_out
    # The vent takes the MIXTURE, so each species leaves in proportion to
    # its share of the mass. Air that has left cannot come back - there
    # is no inflow in this model.
    tot = m + m_a
    yp = m / tot if tot > 0.0 else 1.0
    _R, _cv, cp_mix, _g = mixture(prop, m, m_a)
    e_out = mdot_out * cp_mix * T
    # The wall term is NOT here. It is linear in T and its time constant
    # m*cv/(h_c*A) collapses to ~1e-8 s while the chamber holds only the
    # igniter seed, so an explicit stage cannot carry it: the first
    # attempt drove E negative inside one step and every run with h_c > 0
    # died at the step cap with a zero peak. It is applied exactly
    # instead, in `_wall_relax`, split out of the Cash-Karp step.
    return tuple(dZs) + (
        mdot_gen - mdot_out * yp,
        mdot_gen * prop.cv * prop.T_flame - e_out,
        -mdot_out * (1.0 - yp),
        mdot_out * yp,                 # m_out_p
        mdot_out * (1.0 - yp),         # m_out_a
        e_out,                         # E_out
        0.0)                           # Q_wall - see _wall_relax


def _wall_relax(prop, m, m_a, E, h, h_c, wall_area, T_wall):
    """Energy the walls take over a step of `h`, applied EXACTLY.

    WHY THIS IS SPLIT OUT rather than being one more term in `_derivs`.
    Convective loss is linear in T, so over a step with m frozen the gas
    relaxes towards the wall on a time constant

        tau = m * cv / (h_c * A)

    and the solution is an exponential, not a polynomial. Two things
    follow, and the first is what forced this:

    STIFFNESS. At t = 0 the chamber holds only the igniter seed, so m is
    a whisker and tau collapses - measured at ~1e-8 s for a 5 kg charge
    in 1 m^3 against 6 m^2 of wall at h_c = 2000. An explicit stage sees
    a 32 MW sink against a few kJ of gas and drives E negative inside one
    step. That is not a bug in the integrator: Cash-Karp responded
    correctly, by shrinking h until it hit the step cap, and every run
    with h_c > 0 came back with a zero peak. The exponential form is
    unconditionally stable and needs no step control at all.

    AND IT CANNOT OVERSHOOT. `(1 - exp(-h/tau))` is bounded by 1, so the
    gas is driven towards the wall temperature and never past it,
    whatever the step. A polynomial term can and did sail through it.

    Conservation stays exact because the same number is subtracted from
    E and added to the Q_wall accumulator - see `_conservation_residual`.
    """
    if h_c <= 0.0 or wall_area <= 0.0 or h <= 0.0:
        return 0.0
    tot = m + m_a
    if tot <= 0.0:
        return 0.0
    _R, cv_mix, _cp, _g = mixture(prop, m, m_a)
    C_th = tot * cv_mix                      # J/K of the gas in there
    if C_th <= 0.0:
        return 0.0
    T = E / C_th
    x = h * h_c * wall_area / C_th           # = h / tau
    # math.expm1 keeps the small-x end accurate, where the loss is a tiny
    # fraction of a large energy and the difference of exponentials would
    # cancel to noise.
    return -C_th * (T - T_wall) * math.expm1(-x)


def _ck_step(derivs, s, t, h, n, k1=None):
    """One Cash-Karp step. Returns (y5, err_scaled_numerator, k1).

    `k1` does not depend on h, so a rejected step can hand it back and
    save one right-hand side evaluation per retry.
    """
    ks = []
    for stage in range(6):
        if stage == 0:
            if k1 is not None:
                ks.append(k1)
                continue
            y = s
        else:
            a = _CK_A[stage]
            y = tuple(s[i] + h * sum(a[j] * ks[j][i] for j in range(len(a)))
                      for i in range(n))
        ks.append(derivs(y, t + _CK_NODES[stage] * h))
    y5 = tuple(s[i] + h * sum(_CK_B5[j] * ks[j][i] for j in range(6))
               for i in range(n))
    err = tuple(h * sum((_CK_B5[j] - _CK_B4[j]) * ks[j][i] for j in range(6))
                for i in range(n))
    return y5, err, ks[0]


def _conservation_residual(prop, charge_kg, fracs, state, nZ, m_a0):
    """Largest relative violation of the three conservation identities.

    THE POINT OF THIS FUNCTION. The integrator bug this model shipped
    with did not crash, did not warn, and did not stop early - it
    reported 0.101 MPa where 275 was right and called it a normal
    finish. Nothing downstream could tell. Conservation is the one
    property that is true of the physics regardless of the answer, so
    checking it at the end of every run turns a silent failure into a
    loud one. It is only possible because the vented mass and energy are
    carried as accumulators - see `_derivs`.
    """
    Zs = state[:nZ]
    m, E, m_a = state[nZ], state[nZ + 1], state[nZ + 2]
    m_out_p, m_out_a, E_out = state[nZ + 3], state[nZ + 4], state[nZ + 5]
    q_wall = state[nZ + 6]
    z = sum(f * Z for f, Z in zip(fracs, Zs))
    made = charge_kg * z
    e_in = made * prop.cv * prop.T_flame + m_a0 * AIR_CV * AIR_T0
    worst = 0.0
    for got, want in (((m + m_out_p), made),
                      ((m_a + m_out_a), m_a0),
                      ((E + E_out + q_wall), e_in)):
        scale = max(abs(want), 1e-30)
        worst = max(worst, abs(got - want) / scale)
    return worst


def simulate(prop, charge_kg, volume_m3, vent_area=0.0, cd=0.8,
             t_end=1.0, p_amb=P_AMB, max_steps=500_000, n_out=1000,
             p_ign=None, scenario=None, p0_chamber=0.0,
             refine_cohorts=True, h_c=0.0, wall_area=0.0, T_wall=300.0):
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

    `p0_chamber` [Pa] is the air already in the chamber when the charge
    lights. **It defaults to 0 - an evacuated vessel - on purpose**, so
    the analytic closed-vessel limit and the test that pins it stay
    exactly what they were, and the new physics enters only when it is
    asked for. A magazine passes `P_AMB`; at a magazine's loading density
    that air is comparable to the product gas and changes the answer.
    See `air_mass` for why the omission survived a 1e-6 verification.

    `refine_cohorts` runs the case a second time at twice the cohort
    count and reports how far `p_max` moved, as `cohort_refinement_error`
    and `cohort_converged`. It is ON by default, it never changes
    `p_max`, and it costs nothing on a uniform scenario, which is
    n-independent by construction. See `_COHORT_TOL` for the measurement
    that put it there: at a 60 s spread the usual n = 20 reports a peak
    62 % high with nothing in the result saying so.

    `h_c` [W/m2K], `wall_area` [m2] and `T_wall` [K] are the lumped
    convective heat loss to the chamber walls. **It is off by default
    (`h_c = 0`), and that default is the conservative one**: taking heat
    out lowers T and therefore p, so a run with heat loss reports a
    SMALLER structural load than the adiabatic bound. The energy removed
    is reported as `Q_wall` [J] and is carried in the conservation
    identity, so it cannot quietly go missing. See `_derivs`.
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
    nZ_seed = len(fracs)
    lit_now = sum(f for f, ti in zip(fracs, t_ign) if ti <= 0.0)
    per = min(Z0 / lit_now, 1.0) if lit_now > 0.0 else 0.0
    Zs = [per if ti <= 0.0 else 0.0 for ti in t_ign]
    z_total = sum(f * Z for f, Z in zip(fracs, Zs))
    m = charge_kg * z_total
    # The chamber's own air, and the energy it already holds. m_a0 = 0
    # for the default evacuated vessel, and then every line below is
    # arithmetically what it was before HD1-3-pre.
    m_a0 = air_mass(volume_m3, p0_chamber)
    m_a = m_a0
    E = m * prop.cv * prop.T_flame + m_a * AIR_CV * AIR_T0
    # what has left, integrated alongside what stayed - see `_derivs`
    m_out_p = m_out_a = E_out = Q_wall = 0.0
    t = 0.0
    h_max = t_end / 50.0
    sample_every = t_end / max(n_out, 2)

    # Absolute error floors, one per state component, so the error test
    # is meaningful for quantities that legitimately pass through zero:
    # the accumulators all start at 0, and a purely relative test would
    # divide by nothing on the first step.
    _e_scale = max(charge_kg * prop.cv * prop.T_flame, 1.0)
    _atol = ([1.0e-12] * nZ_seed
             + [1.0e-12 * max(charge_kg, 1.0),      # m
                1.0e-9 * _e_scale,                  # E
                1.0e-12 * max(m_a0, 1.0e-6),        # m_a
                1.0e-12 * max(charge_kg, 1.0),      # m_out_p
                1.0e-12 * max(m_a0, 1.0e-6),        # m_out_a
                1.0e-9 * _e_scale,                  # E_out
                1.0e-9 * _e_scale])                 # Q_wall

    out = dict(t=[], p=[], T=[], Z=[], m=[], m_air=[], mdot_out=[], lit=[])
    p_max, t_p_max = 0.0, 0.0
    last_sample = -1.0

    def overall():
        return sum(f * Z for f, Z in zip(fracs, Zs))

    def state_pT():
        return _pressure(prop, charge_kg, volume_m3, overall(), m, E, m_a)[:2]

    def record():
        p, T = state_pT()
        out['t'].append(t)
        out['p'].append(p)
        out['T'].append(T)
        out['Z'].append(min(overall(), 1.0))
        out['m'].append(m)
        out['m_air'].append(m_a)
        out['mdot_out'].append(_vent_mdot(p, T, prop, vent_area, cd, p_amb,
                                          m_p=m, m_a=m_a))
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
    def rhs(y, tt):
        return _derivs(*args, y, tt, h_c=h_c, wall_area=wall_area,
                       T_wall=T_wall)

    nstate = nZ + 7
    h = h_max
    rejected = 0
    while t < t_end and steps < max_steps:
        steps += 1
        s = tuple(Zs) + (m, E, m_a, m_out_p, m_out_a, E_out, Q_wall)
        # Land ON the next ignition, never across it. A cohort lighting
        # inside a step is a discontinuity in the right-hand side, and
        # no error estimate can repair an average taken across one - it
        # would just keep shrinking h at a point where the equations are
        # not differentiable. This one stays a hard constraint.
        later = [ti for ti in t_ign if ti > t + 1.0e-15]
        if later:
            h = min(h, min(later) - t)
        # ...and land ON Z = 1 for the same reason. Burn-out is an event,
        # not a smooth feature: past it the burn rate is identically
        # zero, so an error estimate taken across it is measuring a
        # discontinuity and would only shrink h for ever. Error control
        # replaced the RATE heuristics, not the event constraints.
        k1 = rhs(s, t)
        for Z, dZ in zip(Zs, k1[:nZ]):
            if dZ > 0.0 and Z < 1.0:
                h = min(h, (1.0 - Z) / dZ)
        h = max(min(h, t_end - t, h_max), 1.0e-14)

        # Cash-Karp with rejection: take the step, measure it against the
        # embedded fourth-order solution, and only keep it if the error
        # is inside tolerance. This is what a rate-based limiter cannot
        # do - it judges the step AFTER seeing what happened inside it.
        tries = 0
        while True:
            y5, err, _k1 = _ck_step(rhs, s, t, h, nstate, k1=k1)
            scale = max(
                abs(err[i]) / (_atol[i] + _RTOL * max(abs(s[i]),
                                                      abs(y5[i])))
                for i in range(nstate))
            if scale <= 1.0 or tries >= _MAX_REJECTS or h <= 1.0e-13:
                break
            tries += 1
            rejected += 1
            h = max(h * max(_SAFETY * scale ** -0.25, _H_SHRINK_MIN),
                    1.0e-14)
        dZ_max = max(k1[:nZ])
        h_used = h
        # grow for next time, from the same estimate
        h = min(h * min(_SAFETY * (scale ** -0.2 if scale > 0 else
                                   _H_GROW_MAX), _H_GROW_MAX), h_max)

        nxt = list(y5)
        m, E, m_a = nxt[nZ], nxt[nZ + 1], max(nxt[nZ + 2], 0.0)
        m_out_p, m_out_a, E_out = nxt[nZ + 3], nxt[nZ + 4], nxt[nZ + 5]
        Q_wall = nxt[nZ + 6]
        # Clipping an overshoot past Z = 1 has to take back the mass and
        # energy that were integrated along with it, or the chamber ends
        # up holding more gas than there was propellant. The old fixed
        # step hid this behind an exact landing; an error-controlled step
        # lands near Z = 1 rather than on it, so the correction has to be
        # explicit. Without it m_end came out at 1.00000002 * C - small,
        # but conservation is either exact or it is a tolerance argument.
        Zs = []
        for i, v in enumerate(nxt[:nZ]):
            if v > 1.0:
                over = (v - 1.0) * fracs[i]
                m -= charge_kg * over
                E -= charge_kg * over * prop.cv * prop.T_flame
                v = 1.0
            Zs.append(v)
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
        # The walls, applied exactly over the step just taken rather than
        # as a stage of it. See `_wall_relax` for why it cannot be a
        # stage: at the seed its time constant is ~1e-8 s and it made
        # every run with h_c > 0 die at the step cap.
        _q = _wall_relax(prop, m, m_a, E, h_used, h_c, wall_area, T_wall)
        E -= _q
        Q_wall += _q
        # Attribute the step BEFORE advancing t: k1 was evaluated at the
        # start of it, so that is the pressure the burn law saw.
        z_start = sum(f * Z for f, Z in zip(fracs, s[:nZ]))
        p_start = _pressure(prop, charge_kg, volume_m3, z_start, s[nZ],
                            s[nZ + 1], s[nZ + 2])[0]
        if dZ_max > 0.0:
            t_burning += h_used
            if not prop.in_validity_window(p_start):
                t_outside += h_used
        t += h_used

        p_now, _T = state_pT()
        if p_now > p_max:
            p_max, t_p_max = p_now, t
        if t - last_sample >= sample_every:
            record()
            last_sample = t
        all_burnt = all(Z >= 1.0 for Z in Zs)
        # burnt out and vented down: nothing left to integrate. Two ways
        # to be finished, and the second is the one that matters. The
        # chamber approaches ambient asymptotically and the step limiter
        # above shrinks with it, so waiting for a pressure threshold can
        # take tens of thousands of steps (22,613 for a 0.1 m^2 vent, and
        # the cap for 0.5 m^2). A converged step IS the answer: h this
        # small means the remaining excess over ambient is too, so stop
        # and report the chamber at ambient rather than chase it.
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
    # The run checks itself. Conservation is true of the physics whatever
    # the answer is, so a residual here means the integration is wrong -
    # and saying so is the whole point. The bug this replaced reported a
    # peak 2700x too low with stop_reason 't_end' and no other sign.
    resid = _conservation_residual(
        prop, charge_kg, fracs,
        tuple(Zs) + (m, E, m_a, m_out_p, m_out_a, E_out, Q_wall), nZ, m_a0)
    out['conservation_residual'] = resid
    if resid > _CONSERVATION_TOL:
        stop_reason = 'conservation_violation'
    elif extinguished and t_burning <= 0.0:
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
    #: Reported so a run outside the range the suite actually spans is
    #: visible. See _VERIFIED_LOADING_RANGE for why that range is three
    #: decades wide and not the half-decade it used to be.
    lo, hi = _VERIFIED_LOADING_RANGE
    out['loading_density'] = charge_kg / volume_m3
    out['loading_verified'] = lo <= charge_kg / volume_m3 <= hi
    out['m_air0'] = m_a0
    out['p0_chamber'] = p0_chamber
    #: energy given up to the walls over the whole run [J], and its share
    #: of the energy released. Zero unless heat loss was asked for.
    out['Q_wall'] = Q_wall
    out['h_c'] = h_c
    out['wall_area'] = wall_area
    _e_released = charge_kg * out['Z'][-1] * prop.cv * prop.T_flame
    out['wall_loss_fraction'] = (Q_wall / _e_released
                                 if _e_released > 0.0 else 0.0)
    out['adiabatic'] = (h_c <= 0.0 or wall_area <= 0.0)
    #: mass of chamber air relative to the product gas made. Above ~0.1
    #: the air is not a correction, and a run made with the default
    #: evacuated chamber is answering a different question.
    out['air_to_product_ratio'] = (m_a0 / (charge_kg * out['Z'][-1])
                                   if out['Z'][-1] > 0 else float('inf'))
    # Always reported, never implied. Uniform ignition is the laboratory
    # condition; a magazine answer computed under it is one whose
    # entrainment was assumed away, and the report has to say so.
    out['scenario_kind'] = scenario.kind
    out['calibration_only_scenario'] = scenario.calibration_only
    out['n_cohorts'] = len(fracs)
    out['extrapolated_fraction'] = (t_outside / t_burning
                                    if t_burning > 0.0 else 0.0)

    # THE COHORT COUNT IS A MESH, SO THE RUN REFINES IT AND SAYS WHAT
    # HAPPENED. Nothing here touches `p_max`: the reported peak stays the
    # one the caller's own scenario produced, and what gets added is
    # whether that peak survives halving the ignition step. A uniform
    # scenario is skipped because every cohort lights at t = 0 whatever n
    # is, so there is nothing to refine and no reason to pay for it.
    # See _COHORT_TOL.
    out['cohort_refinement_error'] = 0.0
    out['cohort_converged'] = True
    out['p_max_refined'] = p_max
    if (refine_cohorts and len(fracs) >= 2
            and scenario.kind != 'uniform'
            and stop_reason != 'conservation_violation'):
        fine = simulate(prop, charge_kg, volume_m3, vent_area=vent_area,
                        cd=cd, t_end=t_end, p_amb=p_amb,
                        max_steps=max_steps, n_out=2, p_ign=p_ign,
                        scenario=_dc_replace(scenario,
                                             n_cohorts=2 * len(fracs)),
                        p0_chamber=p0_chamber, refine_cohorts=False,
                        h_c=h_c, wall_area=wall_area, T_wall=T_wall)
        out['p_max_refined'] = fine['p_max']
        if p_max > 0.0:
            out['cohort_refinement_error'] = abs(fine['p_max'] - p_max) / p_max
        out['cohort_converged'] = (
            out['cohort_refinement_error'] <= _COHORT_TOL)
    return out


def peak(result):
    """(p_max [Pa], t at the peak [s]) - taken over every integration step."""
    return result['p_max'], result['t_p_max']
