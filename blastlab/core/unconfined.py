"""HD1-9: the same charge burning in the open.

A SEPARATE MODEL, ON PURPOSE
----------------------------
The obvious way to get the unconfined case is to take the confined one
and open the vent all the way. It does not work, and the reason is worth
recording because it looks like it should.

Opening the vent drops the chamber to ambient. Ambient is BELOW the
low-pressure deflagration limit, so a model that knows about extinction
stops at t = 0 and reports that propellant in the open does not burn.
That is false, and it is produced by two individually correct pieces of
physics crossing each other. Worse, even with extinction switched off,
the burn rate would come from `a p**n` evaluated at 0.1 MPa using a pair
calibrated at 50-300 MPa - a three-decade extrapolation, the longest
reach anywhere in this tool, dressed up as a calculation.

So this is its own model with its own datum. It burns at `r_atm`, which
is measured at atmospheric pressure, and `a` and `n` take no part in it
at all. The two branches share the propellant table and the ignition
scenario and nothing else, which is what makes comparing them mean
something: same material, same fire, two declared models, rather than one
model asked a question outside its range.

WHAT IT SAYS ABOUT BLAST, AND WHY THAT IS A CALCULATION
-------------------------------------------------------
"Unconfined HD 1.3 makes no meaningful blast wave" is true and is in
every standard, but asserting it in a table is worthless when the whole
point of the comparison is to show it. So the model computes it.

Gas appears at a volumetric rate Qdot; it has to leave through the
surface of the burning stack at a velocity Qdot/A. Compared with the
ambient sound speed that gives an expansion Mach number, and a source
that pushes air away far below the speed of sound cannot steepen into a
shock - the air simply moves aside. That number, not a citation, is the
justification here.

The stack area is taken from the SOLID volume of the charge, which is the
smallest it can be, so the velocity and the Mach number come out as upper
bounds. A conservative bound that still lands far below one is an
argument; a best estimate would not be.

AND THE ANSWER IS CONDITIONAL, WHICH IS WORTH KNOWING
-----------------------------------------------------
Measured here on double-base, whose grain burns through its web in 5 s at
atmospheric pressure:

    charge   flame spread    expansion Mach
     5 kg    simultaneous        0.315
     5 kg      10 s              0.159
     5 kg      30 s              0.061
     5 kg      60 s              0.035
    50 kg    simultaneous        0.679
    50 kg     300 s              0.034

So "unconfined HD 1.3 makes no meaningful blast" is not a property of the
material on its own - it holds because the fire takes far longer to reach
the whole stack than any one item takes to burn. Entrain the same mass
fast enough and the expansion stops being quasi-static.

The simultaneous column is a LIMIT, not a scenario. In the open, a grain
can only burn once the flame has reached it, so lighting an entire pile
at once is not a conservative assumption - it is an impossible one, and
the model reports `simultaneous_limit` so the number is never read as a
prediction. It is left computable because knowing how far the real case
sits from it is the point.
"""

import math

from . import scenario as _scenario
from .constants import GAMMA_AIR, P_AIR, RHO_AIR
from .fuels import form_factor, web_burn_time

#: a grain is burnt out once this little web is left; a degressive grain
#: creeps the last sliver and an explicit march never quite lands on 1
_BURNOUT_EPS = 1.0e-6

#: ambient sound speed [m/s]
C_AMB = math.sqrt(GAMMA_AIR * P_AIR / RHO_AIR)

#: Below this expansion Mach number the release cannot steepen into a
#: shock and the event is thermal, not blast. Deliberately generous: the
#: cases this model is for come out two to three orders below it.
MACH_QUASI_STATIC = 0.05


def burn(prop, charge_kg, scenario=None, t_end=None, n_out=600,
         stack_area=None, p_amb=P_AIR):
    """Burn `charge_kg` of `prop` in the open.

    Returns a dict with the trace (`t`, `z`, `mdot`, `edot`, `mach`,
    `lit`) and:
        burn_time        when the last cohort finishes [s]
        mdot_max         peak gas generation rate [kg/s]
        edot_max         peak anaerobic energy release rate [W]
        energy_total     total anaerobic energy [J]
        mach_max         peak expansion Mach number - an UPPER bound
        blast_negligible True when that stays under MACH_QUASI_STATIC
        spread_limited   True when the flame spread, not the burn rate,
                         sets the duration

    `edot` counts only the propellant's own (anaerobic) energy. A
    fuel-rich propellant releases more again when its products meet
    atmospheric oxygen, which is what makes the fireball bigger than this
    - that belongs to the thermal model, not here.
    """
    if charge_kg <= 0.0:
        raise ValueError('charge must be positive')
    if prop.r_atm <= 0.0:
        raise ValueError(
            f'this propellant has no atmospheric burn rate, so the '
            f'unconfined model has nothing to stand on. Set r_atm - and '
            f'do not derive it from a p**n fit made at closed-vessel '
            f'pressures, which is the extrapolation this model exists to '
            f'avoid.')
    if scenario is None:
        scenario = _scenario.uniform()
    coh = scenario.cohorts()
    fracs = [f for f, _t in coh]
    t_ign = [ti for _f, ti in coh]

    # A single grain burns out in web_burn_time - NOT web/r_atm, which is
    # only right for a neutral grain and cut a degressive burn off at a
    # third of its length. The event lasts that plus however long the
    # flame takes to reach the last item.
    grain_time = web_burn_time(prop, prop.r_atm)
    if t_end is None:
        t_end = (max(t_ign) + grain_time) * 1.05
    dt = t_end / max(n_out - 1, 1)

    # solid volume -> a sphere of that volume -> its area. Smallest
    # plausible surface, so the Mach number below is an upper bound.
    if stack_area is None:
        vol = charge_kg / prop.rho
        stack_area = 4.0 * math.pi * (3.0 * vol / (4.0 * math.pi)) ** (2.0 / 3.0)

    rho_gas = p_amb / (prop.R * prop.T_flame)
    e_specific = prop.force / (prop.gamma - 1.0)      # J/kg of gas made

    out = dict(t=[], z=[], mdot=[], edot=[], mach=[], lit=[])
    zs = [0.0] * len(fracs)
    mdot_max = mach_max = 0.0
    burn_time = 0.0
    for k in range(n_out):
        t = k * dt
        total_dz = 0.0
        for i, (f, ti) in enumerate(zip(fracs, t_ign)):
            if t < ti or zs[i] >= 1.0:
                continue
            total_dz += f * form_factor(prop, zs[i]) * prop.r_atm / prop.web
        mdot = charge_kg * total_dz
        edot = mdot * e_specific
        mach = (mdot / rho_gas) / stack_area / C_AMB
        out['t'].append(t)
        out['z'].append(sum(f * z for f, z in zip(fracs, zs)))
        out['mdot'].append(mdot)
        out['edot'].append(edot)
        out['mach'].append(mach)
        out['lit'].append(sum(f for f, ti in zip(fracs, t_ign) if ti <= t))
        mdot_max = max(mdot_max, mdot)
        mach_max = max(mach_max, mach)
        if any(z < 1.0 for z in zs):
            burn_time = t
        # advance, sub-stepped so a degressive grain does not overshoot
        sub = 4
        for _ in range(sub):
            for i, ti in enumerate(t_ign):
                if t < ti or zs[i] >= 1.0:
                    continue
                zs[i] = min(zs[i] + form_factor(prop, zs[i]) * prop.r_atm
                            / prop.web * dt / sub, 1.0)
                if 1.0 - zs[i] < _BURNOUT_EPS:
                    zs[i] = 1.0

    out['burn_time'] = burn_time
    out['mdot_max'] = mdot_max
    out['edot_max'] = mdot_max * e_specific
    out['energy_total'] = charge_kg * out['z'][-1] * e_specific
    out['mach_max'] = mach_max
    out['blast_negligible'] = mach_max < MACH_QUASI_STATIC
    # Lighting a whole pile at once is not a conservative assumption in
    # the open, it is an impossible one: a grain cannot burn before the
    # flame reaches it. The number is still computed, because how far the
    # real case sits from it is the useful part - but it is labelled.
    out['simultaneous_limit'] = (max(t_ign) <= 0.0)
    out['stack_area'] = stack_area
    out['grain_burn_time'] = grain_time
    out['spread_limited'] = max(t_ign) > grain_time
    out['scenario_kind'] = scenario.kind
    out['calibration_only_scenario'] = scenario.calibration_only
    out['burnt_out'] = all(z >= 1.0 for z in zs)
    # a and n take no part here, so there is nothing to extrapolate
    out['extrapolated_fraction'] = 0.0
    out['r_atm_calibrated'] = prop.is_calibrated('r_atm')
    return out


def compare(prop, charge_kg, volume_m3, vent_area=0.0, scenario=None,
            t_end=1.0, **kw):
    """Run both branches on one charge and one fire, and say which load
    governs.

    The two results come from two different models - see the module
    docstring - and the point of putting them side by side is exactly
    that the same material is negligible in the open and dangerous in a
    room. Returns (confined_result, unconfined_result, summary).
    """
    from . import deflagration
    conf = deflagration.simulate(prop, charge_kg, volume_m3,
                                 vent_area=vent_area, scenario=scenario,
                                 t_end=t_end, **kw)
    unconf = burn(prop, charge_kg, scenario=scenario)
    summary = dict(
        confined_p_max=conf['p_max'],
        confined_overpressure=conf['p_max'] - P_AIR,
        confined_pressure_ratio=conf['p_max'] / P_AIR,
        confined_extrapolated_fraction=conf['extrapolated_fraction'],
        unconfined_mach_max=unconf['mach_max'],
        unconfined_blast_negligible=unconf['blast_negligible'],
        unconfined_energy_total=unconf['energy_total'],
        simultaneous_limit=unconf['simultaneous_limit'],
        scenario_kind=unconf['scenario_kind'],
        governing_confined=('pressure' if conf['p_max'] > 2.0 * P_AIR
                            else 'thermal'),
        # In the open there is no structural pressure load to govern
        # anything - which is the entire reason the thermal path is in
        # scope rather than out of it.
        governing_unconfined=('thermal' if unconf['blast_negligible']
                              else 'pressure'),
    )
    return conf, unconf, summary
