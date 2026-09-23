"""HD1-3c: the hand-off from the 0-D chamber to the CFD mesh.

This is the conceptual core of the venting stage. Everything either side
of it is machinery; this is where one picture of a gas becomes another.

THE TWO PICTURES, AND THE MISTAKE THAT SLIPS IN BETWEEN THEM
------------------------------------------------------------
`core/deflagration.py` is a DALTON model: products and air each fill the
WHOLE chamber, each at its own partial pressure, sharing one temperature.
blastFoam is a VOLUME-FRACTION model: each phase occupies `alpha * V` at
the FULL pressure. These are not the same statement, and converting by
eye gets it wrong. The conversion is

    alpha_expl = m_p R_p / (m_p R_p + m_a R_a)     # the partial-pressure
    alpha_air  = 1 - alpha_expl                    #   share, at one T
    rho_expl   = p / (R_p T)                       # NOT m_p / V
    rho_air    = p / (R_a T)

and it is self-consistent because

    alpha_expl * rho_expl * V = (p_p/p)(p/(R_p T))V = p_p V/(R_p T) = m_p

`rho_expl` is the density of the products AT THE FULL PRESSURE, not the
chamber-averaged `m_p / V`. Writing `m_p / V` would put the right total
mass in the cells with the wrong split, and - this is the part worth
remembering - `check_handoff_energy` would NOT catch it, because it
checks the SUM. A wrong split that sums correctly passes it silently.
`mass_by_phase` exists for exactly that, and `test_vent.py` asserts it
per phase rather than in total.

PRODUCTS ARE NOT HOT AIR, AND THE ERROR SITS ON A THRESHOLD
------------------------------------------------------------
The gas in the chamber is combustion products: gamma ~ 1.25 and
M ~ 22-25 g/mol, against 1.40 and 28.97 for air. Filling the room with
air at the same p and T would be wrong twice over, and the second one is
nastier than the first:

  * at the same p, air carries only ~62 % of the energy
    (E ~ pV/(gamma-1), 0.25/0.40), so `check_handoff_energy` fails -
    or worse, passes, if E_total were taken from the hand-off dict
    rather than from the 0-D result. That is why `E_total` here is
    computed from the SOLVER's own energy and never from these numbers.
  * at the same p and T, the choked mass flow of air is ~15 % higher.
    The 2-D verification is pre-registered at 15 %, so this error would
    have PASSED it and been absorbed into the discharge coefficient,
    where nobody would ever have found it again.

CONSERVE MASS AND ENERGY, LET PRESSURE FOLLOW
---------------------------------------------
The mesh's cavity is not the volume the 0-D model ran at - see
`core/room.py`, where snapping costs an off-grid 5 m room 10.5 % of its
volume. So the hand-off carries `m_p`, `m_a` and `E` across unchanged
and lets `p` come out of the EOS on whatever volume the mesh actually
has. Two consequences, both wanted:

  * `T` does not move at all. Preserving m and E preserves e = E/m, and
    for a calorically perfect gas that IS constant T. So `T` is the
    quantity a golden should pin.
  * a cavity 10 % smaller simply arrives at a pressure 10 % higher,
    which is what the physics requires. A golden pinning `p == p_0D`
    would pin the bug this design exists to avoid.

THE OPENING: TWO WAYS IN, ONE CFD CASE
--------------------------------------
A burst panel and an opening that was never closed give the SAME CFD
case - a room at some pressure with a hole in it - and they differ
entirely in the 0-D stage that chooses the instant:

    burst   t_open is when p first crosses p_burst, on a run with the
            vent shut
    open    t_open is the peak of a run with the vent already open

But they are NOT of equal standing, and that distinction has to live in
the code rather than in someone's head. Initialising a room at peak
pressure against ambient outside is a SHOCK TUBE: an artificial
diaphragm rupture. For a burst panel that is the physics - the panel
really does let go suddenly - and peak and impulse mean what they say.
For an opening that was never closed there was no diaphragm and no wave:
the pressure rose slowly and the jet flowed the whole time. So in that
mode the first front is an ARTEFACT of initialisation, `first_front_is_artefact`
says so, and only steady-jet quantities after it has passed are
reportable.
"""

import math

from .constants import P_AIR
from .deflagration import AIR_R, AIR_CV, mixture

#: Opening modes. See the module docstring on why they share a CFD case
#: and do not share a standing.
MODES = ('burst', 'open')

#: A CFD window this large a share of the chamber's drain time is not
#: resolving a transient any more, it is watching the room empty, and
#: the "the chamber is a reservoir" reading of the result stops holding.
#: Deliberately generous: a magazine drains in 0.1-0.2 s and a window
#: that can be afforded is ~0.1 s, so this is EXPECTED to trip. That is
#: not a fault - it is the correct statement that the answer is good for
#: the front and the early jet and not for the whole event.
WINDOW_FRACTION_WARN = 0.25


class ChamberState:
    """What the mesh is initialised with, and where it came from.

    Deliberately plain: this object is consumed by `writer.profile_state`
    and by the report, and both want numbers rather than behaviour.
    """

    __slots__ = ('p', 'T', 'm_p', 'm_a', 'E', 'volume',
                 'alpha_expl', 'alpha_air', 'rho_expl', 'rho_air',
                 'rho_mix', 'e_mix', 'R_p', 'gamma_p', 'mol_weight_p',
                 't_open', 'mode', 'first_front_is_artefact',
                 'volume_0d', 'p_0d', 'pressure_from_volume_shift',
                 'pressure_from_eos_shift',
                 'adiabatic_source', 'wall_loss_fraction', 'warnings')

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}

    def mass_by_phase(self, volume=None):
        """(products, air) mass the CELLS will hold, from alpha and rho.

        THE CHECK `check_handoff_energy` CANNOT DO. That one compares the
        total, so a wrong split between the phases that happens to sum
        correctly passes it in silence. This recomputes each phase from
        the numbers actually written and must return the 0-D model's
        `m_p` and `m_a`.
        """
        v = self.volume if volume is None else float(volume)
        return (self.alpha_expl * self.rho_expl * v,
                self.alpha_air * self.rho_air * v)

    def __repr__(self):
        return (f'<ChamberState {self.mode} at t={self.t_open:.4g} s: '
                f'{self.p / 1e6:.4f} MPa, {self.T:.1f} K, '
                f'alpha_expl={self.alpha_expl:.4f}'
                + (', first front is an artefact'
                   if self.first_front_is_artefact else '') + '>')


def open_time(result, mode='burst', p_burst=None):
    """The instant the mesh is initialised at, and why that instant.

    `burst` needs `p_burst` and takes the first crossing of it, on a run
    whose vent was shut. `open` takes the peak of a run whose vent was
    already open. Returns (t_open, index).
    """
    if mode not in MODES:
        raise ValueError(f'mode must be one of {MODES}, not {mode!r}')
    t, p = result['t'], result['p']
    if mode == 'open':
        i = max(range(len(p)), key=lambda k: p[k])
        return float(t[i]), i
    if p_burst is None or p_burst <= 0:
        raise ValueError(
            'a burst panel needs the pressure it lets go at. Without one '
            'there is no instant to pick, and taking the peak instead '
            'would silently turn this into the open-from-start case, '
            'whose first front is an initialisation artefact.')
    for i, pi in enumerate(p):
        if pi >= p_burst:
            return float(t[i]), i
    raise ValueError(
        f'the chamber never reached {p_burst / 1e6:.3f} MPa - it peaked '
        f'at {result["p_max"] / 1e6:.3f}. The panel does not burst, so '
        f'there is no venting stage to run: this magazine holds.')


def handoff(result, prop, mode='burst', p_burst=None, volume_cfd=None,
            p_amb=P_AIR):
    """Turn a 0-D result at `t_open` into a `ChamberState`.

    `volume_cfd` is the cavity the MESH has, which is not the volume the
    0-D model ran at once obstacle snapping has had its way with the
    walls (`core/room.py`). Mass and energy cross unchanged and the
    pressure follows from the EOS on that volume - see the module
    docstring for why that way round.
    """
    t_open, i = open_time(result, mode=mode, p_burst=p_burst)
    m_p = float(result['m'][i])
    m_a = float(result['m_air'][i])
    T = float(result['T'][i])
    p_0d = float(result['p'][i])
    v_0d = float(result.get('volume_m3') or 0.0)
    if v_0d <= 0.0:
        # older results do not carry it; recover it from the state, which
        # is exact for the ideal-gas part and within the covolume for the
        # rest - and say so rather than guessing silently
        v_0d = (m_p * prop.R + m_a * AIR_R) * T / p_0d if p_0d > 0 else 0.0
    v = float(volume_cfd) if volume_cfd else v_0d
    if v <= 0.0:
        raise ValueError('the chamber volume must be positive')
    if m_p + m_a <= 0.0:
        raise ValueError('there is no gas in the chamber to hand over')

    # THE PRESSURE IS AN OUTPUT. blastFoam's phases are ideal gases with
    # no covolume, so this is the ideal-gas pressure of the same mass and
    # temperature on the mesh's own volume. At magazine pressures the
    # covolume correction the 0-D model carries is small; the difference
    # is reported rather than absorbed.
    p = (m_p * prop.R + m_a * AIR_R) * T / v

    # Dalton -> volume fractions. See the module docstring.
    pp_p = m_p * prop.R * T / v
    pp_a = m_a * AIR_R * T / v
    alpha_expl = pp_p / (pp_p + pp_a) if (pp_p + pp_a) > 0 else 1.0
    rho_expl = p / (prop.R * T)
    rho_air = p / (AIR_R * T)

    _R, cv_mix, _cp, _g = mixture(prop, m_p, m_a)
    E = (m_p + m_a) * cv_mix * T

    warnings = []
    if result.get('adiabatic', True):
        warnings.append(
            f'the 0-D run behind this state was ADIABATIC, so its '
            f'{T:.0f} K and {p / 1e6:.4f} MPa are upper bounds: a real '
            f'magazine gives heat to its walls over the seconds the fire '
            f'lasts, and both T and p come down with it. That is the '
            f'conservative choice for a pressure check and the wrong one '
            f'to write into a mesh without saying so. Set h_c and '
            f'wall_area on the 0-D run.')
    elif result.get('wall_loss_fraction', 0.0) > 0.5:
        warnings.append(
            f'the walls took {result["wall_loss_fraction"]:.0%} of the '
            f'energy released before the hand-off, so this state is a '
            f'long way below the adiabatic bound. Check that h_c is a '
            f'measurement and not a placeholder - nothing in this repo '
            f'calibrates it.')
    if not result.get('cohort_converged', True):
        warnings.append(
            f'the 0-D peak had not converged in cohort count '
            f'({result.get("cohort_refinement_error", 0.0):.0%} on '
            f'doubling), so the instant this state was taken at is set by '
            f'the ignition staircase rather than by the fire.')
    if result.get('stop_reason') == 'conservation_violation':
        raise ValueError(
            'the 0-D run did not conserve, so there is nothing worth '
            'handing to a mesh. Fix the run first.')

    return ChamberState(
        p=p, T=T, m_p=m_p, m_a=m_a, E=E, volume=v,
        alpha_expl=alpha_expl, alpha_air=1.0 - alpha_expl,
        rho_expl=rho_expl, rho_air=rho_air,
        rho_mix=(m_p + m_a) / v,
        e_mix=cv_mix * T,
        R_p=prop.R,
        gamma_p=prop.gamma,
        #: g/mol, which is the unit blastFoam's `molWeight` wants. NOT
        #: air's 28.97 - see the module docstring on the 15 % that would
        #: have hidden inside Cd.
        mol_weight_p=8314.46261815324 / prop.R,
        t_open=t_open, mode=mode,
        # A room initialised at pressure against ambient outside is a
        # shock tube. For a burst panel that IS the event; for an
        # opening that was never shut there was no diaphragm, so the
        # first front is something this initialisation invented.
        first_front_is_artefact=(mode == 'open'),
        volume_0d=v_0d, p_0d=p_0d,
        # TWO SHIFTS, AND THEY ARE NOT THE SAME THING. Reporting one
        # number for both hid a real effect behind a rounding-sized one:
        #   volume - the mesh cavity differs from the 0-D volume, and
        #            pressure scales with the ratio at constant m and E.
        #   eos    - the 0-D model is Noble-Abel and carries a covolume;
        #            blastFoam's phases are ideal gases and do not. At
        #            magazine density that is ~0.1 %, and at closed-
        #            vessel density it is not small at all, so it has to
        #            be visible rather than folded into the other one.
        pressure_from_volume_shift=(v_0d / v - 1.0) if v > 0 else 0.0,
        pressure_from_eos_shift=(
            ((m_p * prop.R + m_a * AIR_R) * T / v_0d) / p_0d - 1.0
            if p_0d > 0 and v_0d > 0 else 0.0),
        # WHETHER THE RUN THAT PRODUCED THIS GAVE THE WALLS ANYTHING.
        # `simulate` is adiabatic by default, which is the conservative
        # choice for a pressure check and the WRONG one to hand to a
        # mesh without saying so: T and therefore p are then upper
        # bounds, and `writer` is about to write them into a golden. The
        # state carries the answer rather than leaving it to whoever
        # called simulate.
        adiabatic_source=bool(result.get('adiabatic', True)),
        wall_loss_fraction=float(result.get('wall_loss_fraction', 0.0)),
        warnings=warnings,
    )


def validity(result, state, t_cfd, prop=None, vent_area=None):
    """How much of the event a CFD window of `t_cfd` seconds covers.

    `vent_area` is the hole that will be OPEN during the window, and it
    has to be passed for a burst panel because the 0-D run that chose
    the instant had its vent SHUT. The first version of this function
    read the drain rate off that run and got the obvious answer: a
    blowdown fraction of MINUS 3.4 %, because a sealed chamber with a
    fire in it gains mass rather than losing it. The number looked
    computed and was not about the thing it named.

    The CFD runs tens to hundreds of milliseconds on a burn that lasts
    seconds, and what a reader is entitled to conclude depends on how
    much it missed. Returns a dict of measured fractions plus `warnings`.

    THE TWO MODES GET DIFFERENT METRICS, AND THAT IS NOT TIDINESS.

    For a BURST panel the two questions are genuinely separate: how much
    more gas the fire makes during the window (`burn_fraction`), and how
    far the chamber empties during it (`blowdown_fraction`). A chamber
    can be a good reservoir while the fire is still growing, or the
    reverse.

    For an opening that was never shut, `t_open` is the PEAK - and at
    the peak, production equals outflow by definition. So the two
    fractions coincide identically, and reporting both would be
    pretending there are two checks where there is one. That mode gets
    `window_over_drain` alone.
    """
    t_cfd = float(t_cfd)
    if t_cfd <= 0:
        raise ValueError('the CFD window must be positive')
    t, m, m_air, mdot = (result['t'], result['m'], result['m_air'],
                         result['mdot_out'])
    i = min(range(len(t)), key=lambda k: abs(t[k] - state.t_open))
    j = min(range(len(t)), key=lambda k: abs(t[k] - (state.t_open + t_cfd)))

    in_room = m[i] + m_air[i]

    # THE DRAIN RATE IS THROUGH THE HOLE THAT WILL BE OPEN, which for a
    # burst panel is not the hole the 0-D run had. Given the propellant
    # and the area, recompute it from the hand-off state; otherwise fall
    # back to the run's own outflow and SAY that is what happened.
    if prop is not None and vent_area:
        from .deflagration import _vent_mdot
        out_rate = _vent_mdot(state.p, state.T, prop, float(vent_area),
                              result.get('cd', 0.8) or 0.8, P_AIR,
                              m_p=state.m_p, m_a=state.m_a)
        rate_from = 'the vent that will be open'
    else:
        out_rate = float(mdot[i])
        rate_from = "the 0-D run's own vent"
    # e-folding time of the chamber at the instant it is handed over
    tau_drain = (in_room / out_rate) if out_rate > 0 else float('inf')
    window_over_drain = t_cfd / tau_drain if tau_drain > 0 else float('inf')

    out = {
        'mode': state.mode,
        't_open': state.t_open,
        't_cfd': t_cfd,
        'tau_drain': tau_drain,
        'window_over_drain': window_over_drain,
        'drain_rate_from': rate_from,
        'warnings': [],
    }
    if prop is None or not vent_area:
        out['warnings'].append(
            'the drain time was taken from the 0-D run rather than from '
            'the opening that will actually be there. For a burst panel '
            'that run was SEALED, so this number is not about the '
            'blowdown - pass prop and vent_area.')
    if state.mode == 'burst':
        made = result.get('charge_kg')
        z_i, z_j = result['Z'][i], result['Z'][j]
        # An UPPER bound: this is read off the sealed run, where the
        # pressure keeps climbing, and once the panel lets go the
        # pressure falls and the burn slows with it. Bounding it is
        # honest; pretending it is the burn after the panel opens is not.
        out['burn_fraction'] = float(z_j - z_i)
        out['burn_fraction_is_upper_bound'] = True
        # Estimated from the drain time, and labelled as an estimate -
        # NOT read off a sealed run, which is where this returned -3.4 %
        # and looked like a measurement.
        out['blowdown_fraction'] = (
            1.0 - math.exp(-window_over_drain)
            if math.isfinite(window_over_drain) else 1.0)
        out['blowdown_is_estimate'] = True
        out['charge_kg'] = made
        if out['burn_fraction'] > 0.05:
            out['warnings'].append(
                f'the fire makes at most another '
                f'{out["burn_fraction"]:.1%} of the charge during the '
                f'window, which the CFD does not model - the room is '
                f'treated as a fixed mass of gas once it is handed over. '
                f'An upper bound: it is read off the sealed run, and once '
                f'the panel lets go the pressure falls and the burn slows.')
        if out['blowdown_fraction'] > WINDOW_FRACTION_WARN:
            out['warnings'].append(
                f'the chamber loses about '
                f'{out["blowdown_fraction"]:.0%} of its contents inside '
                f'the window, so it is not a reservoir on this timescale. '
                f'The front and the early jet are valid; a steady-jet '
                f'reading is not.')
    else:
        # ONE metric, on purpose. At the peak, production == outflow, so
        # a burn fraction and a blowdown fraction are the same number
        # wearing two hats.
        out['single_metric_because'] = (
            'at the peak the fire and the vent balance by definition, so '
            'a burn fraction and a blowdown fraction are identically the '
            'same number - reporting both would look like two checks')
        if window_over_drain > WINDOW_FRACTION_WARN:
            out['warnings'].append(
                f'the window is {window_over_drain:.0%} of the chamber '
                f'drain time {tau_drain:.3f} s, so this covers the early '
                f'jet rather than the whole event.')
        out['warnings'].append(
            'opened-from-the-start: the first front out of the opening is '
            'an ARTEFACT of initialising a pressurised room against '
            'ambient. In reality the pressure rose slowly and the jet '
            'flowed throughout, so no peak or impulse may be read from '
            'that front - only steady-jet quantities after it has passed.')
    return out


def energy_check(state, e_total_from_solver, tol=0.02):
    """Does the state about to be written carry the energy the 0-D model
    meant to hand over?

    `e_total_from_solver` must come from the deflagration RESULT, never
    from `state`. Taking it from the hand-off would compare the hand-off
    with itself, which is a check that can only pass.
    """
    got = state.E
    want = float(e_total_from_solver)
    rel = abs(got - want) / max(abs(want), 1e-30)
    return {
        'E_state': got,
        'E_solver': want,
        'rel': rel,
        'ok': rel <= tol,
        'tol': tol,
    }


def cfd_point_in_band(band, cells_across, cd_range=None):
    """Where the CFD's own answer sits inside the sensitivity envelope.

    THE CFD IS ONE POINT, NOT THE BAND, and a report that does not say
    so reads as though it were the answer. Every other parameter in the
    envelope can be swept cheaply in the 0-D model; `Cd` cannot, because
    the CFD does not take a discharge coefficient as INPUT - it produces
    one, and the value it produces is set by how well the opening is
    resolved. `_e2e_vent_verify.py` measured that:

        6 cells across    Cd_eff = 0.7227
        12 cells          Cd_eff = 0.8102

    So a CFD run at twelve cells is a sample at Cd ~ 0.81, which is one
    corner of a 0.72-0.90 axis - and the structural load it reports is
    the load AT THAT CORNER.

    Returns a dict with `cd_cfd`, where it falls in the range, and a
    `note` written for the report. When the band's own structural
    verdict is `undetermined_within_band`, the note says outright that
    this run does not close it: a single sample cannot settle a question
    whose answer changes across the interval it was drawn from.
    """
    lo, hi = cd_range or (0.72, 0.90)
    # the two measured points, interpolated in 1/dx - the only two this
    # repository has, and the reason the range exists at all
    cd_cfd = 0.7227 if cells_across < 9 else 0.8102
    pos = (cd_cfd - lo) / (hi - lo) if hi > lo else 0.0
    verdict = (band or {}).get('verdict')
    note = (f'The CFD ran at {cells_across} cells across the opening, '
            f'which makes it a sample at Cd ~ {cd_cfd:.2f} - '
            f'{pos:.0%} of the way up a {lo:g}-{hi:g} axis. Its '
            f'structural load is the load AT THAT POINT, not the '
            f'envelope: the CFD does not take Cd as an input, it '
            f'produces one, and what it produces depends on the mesh.')
    out = {'cd_cfd': cd_cfd, 'cd_range': (lo, hi), 'position': pos,
           'cells_across': cells_across, 'closes_verdict': True}
    if verdict == 'undetermined_within_band':
        out['closes_verdict'] = False
        note += (' AND IT DOES NOT SETTLE THE STRUCTURAL VERDICT: that '
                 'verdict is `undetermined_within_band`, meaning the '
                 'answer changes across the envelope, and one sample '
                 'drawn from inside an interval cannot decide a '
                 'question whose answer varies over it. What settles it '
                 'is a closed-vessel record on the real propellant.')
    out['note'] = note
    return out


def summary_line(state, val):
    """One line for the report, caveats attached."""
    txt = (f'{state.p / 1e6:.4f} MPa, {state.T:.0f} K, '
           f'alpha_expl {state.alpha_expl:.3f}, handed over at '
           f't = {state.t_open:.4g} s ({state.mode})')
    if abs(state.pressure_from_volume_shift) > 1e-6:
        txt += (f' - the mesh cavity differs from the 0-D volume, so the '
                f'pressure moved {state.pressure_from_volume_shift:+.1%} '
                f'at constant mass, energy and temperature')
    if abs(state.pressure_from_eos_shift) > 1e-3:
        txt += (f' | and {state.pressure_from_eos_shift:+.1%} again from '
                f'dropping the co-volume: the 0-D model is Noble-Abel and '
                f'the mesh phases are ideal gases')
    if state.adiabatic_source:
        txt += ' | ADIABATIC SOURCE: T and p are upper bounds'
    for w in tuple(state.warnings or ()) + tuple(val.get('warnings', ())):
        txt += f' | {w}'
    return txt
