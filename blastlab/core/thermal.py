"""HD1-8: the heat, which for HD 1.3 is usually the damage that matters.

WHY THIS IS AN EMPIRICAL MODULE AND NOT A SOLVER
------------------------------------------------
blastFoam does not solve radiation - every case this repo writes carries
`radiationModel none` - so there is no CFD route to a fireball here and
there is not going to be one. This is a standards-and-correlations path,
declared as such, and every number it produces is flagged accordingly.

It is in scope anyway because leaving it out answers the wrong question.
For an unconfined HD 1.3 event `core/unconfined.py` shows the blast is
negligible; what remains is thermal, and a tool that reports only
pressure would report that nothing happens.

THREE THINGS, AND THE THIRD IS THE ONE WITH A TRAP IN IT
--------------------------------------------------------
(a) WALL FLUX, CONFINED. The 0-D chamber already carries T(t); the heat
    it gives the walls is nearly free output. Surface temperature follows
    from Duhamel superposition on a semi-infinite solid, which has an
    exact constant-flux limit the tests check against.

(b) FIREBALL, UNCONFINED. Diameter and duration from mass correlations,
    a surface emissive power, a solid-flame view factor, atmospheric
    transmissivity, and the received flux integrated into a thermal dose.

    The fireball energy includes SECONDARY COMBUSTION. Propellant gases
    are fuel-rich - CO and H2 - and burning them in air releases energy
    that appears nowhere in the chamber's balance, because inside the
    chamber there is no oxygen. For the shipped rows it is comparable to
    the anaerobic energy, not a correction to it, so leaving it out makes
    the fireball substantially too small. It is treated as an upper
    bound: mixing with free air is never complete.

    The D = k M^(1/3) correlations come from BLEVE and hydrocarbon pool
    work. They are used because nothing better is published for
    propellant stacks, and they are flagged, not laundered.

(c) THE STRUCTURE. The obvious move is to reduce the yield strength with
    temperature and feed it into the SDOF. **That is wrong, and this
    module refuses to do it.** The timescales are two orders of magnitude
    apart: the pressure pulse acts in milliseconds to a few hundred
    milliseconds, and steel does not heat appreciably in that time. A
    time-varying Ru inside the dynamic response is not a refinement, it
    is a coupling that does not exist.

    So there are two SERIAL questions, answered separately and reported
    side by side:

        sdof(Ru at ambient, pressure trace)   did the wall survive the pulse?
        residual_capacity(thermal history)    what is left of it afterwards?

    `residual_capacity` returns a degraded resistance for the caller to
    use in a SECOND, later check. It never reaches into the first one,
    and `core/sdof.py` does not import this module.
"""

import math

import numpy as np

STEFAN_BOLTZMANN = 5.670374419e-8

#: EN 1993-1-2 Table 3.1 - effective yield strength reduction for
#: structural steel, k_y,theta against temperature in degrees C.
STEEL_KY = ((20, 1.00), (100, 1.00), (200, 1.00), (300, 1.00), (400, 1.00),
            (500, 0.78), (600, 0.47), (700, 0.23), (800, 0.11), (900, 0.06),
            (1000, 0.04), (1100, 0.02), (1200, 0.00))

#: EN 1992-1-2 Table 3.1 - compressive strength reduction for siliceous
#: aggregate concrete, k_c,theta.
CONCRETE_KC = ((20, 1.00), (100, 1.00), (200, 0.95), (300, 0.85),
               (400, 0.75), (500, 0.60), (600, 0.45), (700, 0.30),
               (800, 0.15), (900, 0.08), (1000, 0.04), (1100, 0.01),
               (1200, 0.00))

MATERIALS = {'steel': STEEL_KY, 'concrete': CONCRETE_KC}

#: Thermal dose thresholds in (kW/m^2)^(4/3) * s, the usual units of the
#: Eisenberg-type probit. Literature values (TNO Green Book and the
#: chemical-industry consequence literature), carried here so a computed
#: dose has something to be compared against - NOT derived in this repo.
DOSE_THRESHOLDS = (
    ('first-degree burn', 115.0),
    ('second-degree burn', 250.0),
    ('1 % fatality', 1060.0),
    ('50 % fatality', 2300.0),
)

#: Fireball correlations D = a M^(1/3) [m], t = b M^(1/3) [s], M in kg.
#: BLEVE / hydrocarbon origin - see the module docstring.
FIREBALL_D = 5.8
FIREBALL_T = 0.45

#: Specific energy [J/kg] of the fuels those correlations were fitted to.
#:
#: They are quoted against MASS, but the variable underneath is ENERGY -
#: mass only works as a proxy inside one fuel class. A propellant carries
#: about 8 MJ/kg against a hydrocarbon's 46, so feeding propellant mass
#: into a hydrocarbon diameter law builds a fireball far too large for
#: the energy inside it, and the emissive power that follows comes out
#: near 50 kW/m^2 against the 200-350 measured on real fireballs. That
#: mismatch was the test catching a genuine error, not a loose tolerance.
#:
#: So the correlations are driven by an ENERGY-EQUIVALENT mass, which
#: makes them transferable between fuels and puts the derived emissive
#: power back in the published range - now as a consistency check rather
#: than an assumption.
REF_SPECIFIC_ENERGY = 46.0e6

#: fraction of the released energy that leaves as radiation
RADIATIVE_FRACTION = 0.3


def _interp(table, x):
    xs = [p[0] for p in table]
    ys = [p[1] for p in table]
    return float(np.interp(x, xs, ys))


# ── (a) the confined wall ──────────────────────────────────────────────

def wall_flux(T_gas, h_c, T_wall=300.0):
    """Convective flux to the wall [W/m^2] from a gas temperature."""
    T = np.asarray(T_gas, float)
    return h_c * np.clip(T - T_wall, 0.0, None)


def surface_temperature(t, q, k=45.0, rho=7850.0, cp=470.0, T0=300.0):
    """Inner-surface temperature [K] of a semi-infinite wall under a
    time-varying flux, by Duhamel superposition:

        T_s(t) - T0 = 2/sqrt(pi k rho c) * sum q_i (sqrt(t-t_{i-1})
                                                    - sqrt(t-t_i))

    whose constant-flux limit is the textbook 2 q sqrt(alpha t / pi) / k.
    Defaults are structural steel; pass concrete's properties for a
    magazine wall.

    Semi-infinite is the right idealisation for the first seconds of a
    thick wall and the wrong one once the back face starts to warm; it is
    used here because an HD 1.3 chamber transient is short against the
    diffusion time of any wall thick enough to matter.
    """
    t = np.asarray(t, float)
    q = np.asarray(q, float)
    if len(t) != len(q):
        raise ValueError('t and q must be the same length')
    coeff = 2.0 / math.sqrt(math.pi * k * rho * cp)
    out = np.full(len(t), float(T0))
    for n in range(1, len(t)):
        tn = t[n]
        prev = np.sqrt(np.clip(tn - t[:n], 0.0, None))
        nxt = np.sqrt(np.clip(tn - t[1:n + 1], 0.0, None))
        out[n] = T0 + coeff * float(np.sum(q[:n] * (prev - nxt)))
    return out


def wall_exposure(t, T_gas, h_c, T_wall=300.0, **kw):
    """Everything the confined side has to say about heat, in one call."""
    q = wall_flux(T_gas, h_c, T_wall)
    T_s = surface_temperature(t, q, T0=T_wall, **kw)
    return dict(q=q, T_surface=T_s, q_max=float(np.max(q)) if len(q) else 0.0,
                T_surface_max=float(np.max(T_s)) if len(T_s) else T_wall,
                heat_per_area=float(np.trapezoid(q, t)) if len(t) > 1 else 0.0)


# ── (b) the unconfined fireball ────────────────────────────────────────

def fireball_energy(prop, mass_burnt_kg, include_secondary=True):
    """(total, anaerobic, secondary) energy [J] available to the fireball.

    The secondary term is an UPPER bound - free-air mixing is never
    complete - and it is not small: for the shipped rows it is comparable
    to the propellant's own energy rather than a correction to it.
    """
    anaerobic = mass_burnt_kg * prop.force / (prop.gamma - 1.0)
    secondary = mass_burnt_kg * prop.secondary_heat if include_secondary else 0.0
    return anaerobic + secondary, anaerobic, secondary


def fireball(energy_J, mass_kg=None, f_rad=RADIATIVE_FRACTION,
             d_coeff=FIREBALL_D, t_coeff=FIREBALL_T,
             ref_specific_energy=REF_SPECIFIC_ENERGY):
    """Fireball geometry and surface emissive power, driven by ENERGY.

    The published correlations are written against mass, but mass is only
    a proxy for energy within one fuel class - see REF_SPECIFIC_ENERGY.
    They are therefore evaluated at the energy-equivalent mass

        M_eq = E / ref_specific_energy

    so a propellant with a fifth of a hydrocarbon's specific energy gets
    a fireball sized for the energy it actually has. `mass_kg` is carried
    for reporting and takes no part in the geometry.

    The emissive power then follows from the same energy,

        SEP = f_rad * E / (pi D^2 * t)

    which lands back in the range measured on real fireballs. That
    agreement is a CONSISTENCY CHECK, not an input, and it is the only
    thing tying these hydrocarbon correlations to a propellant at all.
    """
    if energy_J <= 0:
        raise ValueError('fireball needs a positive energy')
    if mass_kg is not None and mass_kg <= 0:
        raise ValueError('fireball mass must be positive when given')
    m_eq = energy_J / ref_specific_energy
    scale = m_eq ** (1.0 / 3.0)
    D = d_coeff * scale
    dur = t_coeff * scale
    area = math.pi * D * D
    sep = f_rad * energy_J / (area * dur)
    return dict(diameter=D, duration=dur, area=area, sep=sep,
                energy=energy_J, mass=mass_kg, equivalent_mass=m_eq,
                f_rad=f_rad, centre_height=0.5 * D,
                correlation='hydrocarbon/BLEVE M^(1/3), driven by the '
                            'energy-equivalent mass - see module doc',
                calibrated=False)


def view_factor(fb, distance_m, height_m=None):
    """Solid-flame view factor from a spherical fireball to a receiver
    facing it. For a sphere, F = (D/2)^2 / L^2 with L the distance to the
    centre - exact, and the reason a sphere is the one flame shape worth
    doing analytically."""
    h = fb['centre_height'] if height_m is None else height_m
    L = math.hypot(distance_m, h)
    if L <= 0.5 * fb['diameter']:
        return 1.0                      # the receiver is inside it
    return (0.5 * fb['diameter'] / L) ** 2


def transmissivity(distance_m, humidity=0.5, T_amb=293.15):
    """Atmospheric transmissivity (TNO form):  tau = 2.02 (p_w R)^-0.09,
    with p_w the partial pressure of water vapour [Pa]."""
    p_sat = 610.78 * math.exp(17.2694 * (T_amb - 273.16) / (T_amb - 35.86))
    p_w = max(humidity * p_sat, 1.0)
    return min(1.0, 2.02 * (p_w * max(distance_m, 1.0)) ** -0.09)


def thermal_dose(t, q_w_m2):
    """Thermal dose in (kW/m^2)^(4/3) * s - the quantity the published
    injury thresholds are expressed in, which is why the flux is
    converted to kW before the exponent."""
    t = np.asarray(t, float)
    q_kw = np.clip(np.asarray(q_w_m2, float), 0.0, None) / 1e3
    if len(t) < 2:
        return 0.0
    return float(np.trapezoid(q_kw ** (4.0 / 3.0), t))


def dose_verdict(dose):
    """The most severe published threshold this dose exceeds."""
    worst = 'below the first-degree-burn threshold'
    for name, level in DOSE_THRESHOLDS:
        if dose >= level:
            worst = name
    return worst


def radiation_at(fb, distance_m, humidity=0.5, height_m=None):
    """Incident flux and dose at a standoff, for the whole fireball."""
    f = view_factor(fb, distance_m, height_m)
    tau = transmissivity(distance_m, humidity)
    q = fb['sep'] * f * tau
    dose = (q / 1e3) ** (4.0 / 3.0) * fb['duration']
    return dict(distance=distance_m, view_factor=f, transmissivity=tau,
                flux=q, dose=dose, verdict=dose_verdict(dose),
                inside_fireball=distance_m <= 0.5 * fb['diameter'],
                calibrated=False)


# ── (c) what is left of the structure afterwards ───────────────────────

def strength_factor(T_celsius, material='steel'):
    """Eurocode strength reduction factor at a temperature."""
    if material not in MATERIALS:
        raise ValueError(f'material must be one of {tuple(MATERIALS)}')
    return _interp(MATERIALS[material], T_celsius)


def residual_capacity(Ru, T_peak_K, material='steel'):
    """Ultimate unit resistance left after a thermal exposure.

    A SECOND, LATER check - never an input to the dynamic response of the
    same event. See the module docstring: the pressure pulse is over
    before the section has warmed, so feeding a degraded Ru into the SDOF
    would model a coupling that does not exist. The caller runs
    `sdof.response` with the ambient Ru for the pulse, and runs it again
    with this value if it wants to ask what a later load would do to the
    heated structure.
    """
    T_c = T_peak_K - 273.15
    k = strength_factor(T_c, material)
    return dict(Ru_ambient=Ru, Ru_degraded=Ru * k, factor=k,
                T_peak_C=T_c, material=material,
                note='apply to a SUBSEQUENT load case, not to the '
                     'pressure pulse that caused the heating')
