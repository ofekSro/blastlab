"""HD1-11a: one HD 1.3 assessment as a case - saveable, validated, run.

Everything under it is a model with its own arguments. This is the layer
that turns a stored file into the whole answer: chamber pressure, the
open-air comparison, the structural response and the heat, in one call,
so a result is reproducible from a case file rather than from a
transcript of which function was called with what.

It also puts the warnings in ONE place. Up to here every caveat lived in
the module that knew about it, and a caller who forgot to look simply did
not see it. `validate` gathers them against the same
`core.case.ValidationReport` the blast cases use, which is what lets the
existing Setup validation card and Run gating display an HD 1.3 case with
no new plumbing.

WHAT VALIDATION IS FOR HERE
---------------------------
Not input sanitising - that is a small part of it. The real job is to
say, before anything is computed, which of the answers about to appear
rest on numbers nobody measured, and how far the model is being asked to
reach beyond where its burn law was fitted. An HD 1.3 assessment that
comes back without those statements is not a safer answer, it is the same
answer with the uncertainty hidden.
"""

import json
from dataclasses import asdict, dataclass, field, replace

from . import deflagration, scenario as _scenario, thermal, unconfined
from .case import ValidationReport
from .constants import P_AIR
from .fuels import PROPELLANTS

SCHEMA = 'blastlab-hd13'
VERSION = 1

CONFINEMENTS = ('confined', 'unconfined', 'both')


@dataclass
class DeflagrationCase:
    """One HD 1.3 assessment. `dim = 0` mirrors Case1D/2D/3D, so a host
    can branch on it the way it already branches on dimension."""
    dim = 0
    name: str = ''
    propellant: str = 'double_base'
    #: Per-case overrides of propellant fields. The shipped rows are
    #: class-typical literature values, so a real assessment is expected
    #: to replace some of them - this is where that happens, in the saved
    #: case rather than in a patched table, so the run stays
    #: reproducible. It is also the only way to switch the extinction
    #: limit on, which the physics deliberately leaves off by default.
    overrides: dict = field(default_factory=dict)
    #: Overridden fields the user says they MEASURED. Those drop out of
    #: `uncalibrated`; an override with no measurement behind it is still
    #: an estimate, and silently promoting it would undo the whole
    #: per-field calibration scheme.
    measured: list = field(default_factory=list)

    charge_kg: float = 5.0
    volume_m3: float = 1.0
    vent_area_m2: float = 0.0
    discharge_coeff: float = 0.8
    p_ign: float = 0.0                 # 0 = let the model choose
    #: Air already in the room when the charge lights [Pa]. `simulate`
    #: defaults this to 0 so its analytic closed-vessel limit is
    #: untouched; a CASE is a room, never an evacuated vessel, so the
    #: default here is atmospheric. It matters: the case path ran
    #: evacuated until 2026-09-21, and at magazine loading density the
    #: resident air is comparable to the product gas.
    p0_chamber: float = P_AIR

    confinement: str = 'confined'
    scenario_kind: str = 'uniform'
    n_cohorts: int = 1
    spread_time: float = 0.0
    spread_geometry: str = 'line'

    t_end: float = 5.0
    n_out: int = 1000

    #: Run the uncertainty band around the confined peak. It costs 15
    #: extra solves, which is why it is not forced on - but nothing in
    #: `PROPELLANTS` is calibrated, so a peak quoted without it is a
    #: point estimate from a model applied two decades from where its
    #: burn law was fitted. See `core/sensitivity.py`.
    sensitivity: bool = False
    #: Where the ranges below came from. Empty means "a judgement", and
    #: the band says so on every line it produces.
    sensitivity_source: str = ''
    sens_dn: float = 0.15
    sens_a_factor: float = 1.5
    sens_pext_factor: float = 2.0
    #: The fourth axis. `h_c` is a film coefficient nobody here has
    #: measured, and it moves the state handed to a CFD run by more than
    #: any single burn-law parameter: 12.4 % on the mass burnt at burst
    #: against 1.4 % on T. A band that leaves it out reports itself
    #: narrower than it is.
    sens_hc_factor: float = 2.0

    # heat (0 = that part is not asked for)
    h_c: float = 0.0
    wall_area_m2: float = 0.0
    T_wall: float = 300.0
    standoffs_m: list = field(default_factory=list)

    #: HD1-3e. Quantity-distance rows, each a dict with name, k_factor,
    #: basis and SOURCE. Empty by default and empty on purpose: these
    #: are safety-siting factors out of a standard, a wrong one is
    #: invisible, and this tool ships none. See core/qd.py.
    qd_criteria: list = field(default_factory=list)

    # ── HD1-3f · the venting stage ──────────────────────────────────────
    #
    # All falsy by default: a 0-D assessment does not need any of it, and
    # `wants_vent` is what decides whether a CFD case gets built at all.
    # The room here is what the user TYPED; `build_vent_case` runs it
    # through `core.room.measure`, which aligns it to the mesh, and the
    # aligned volume is what the 0-D model is then re-run at.
    room_origin: tuple = (0.0, 0.0, 0.0)
    room_size: tuple = ()             # (Lx, Ly, Lz) outer, m
    room_wall_m: float = 0.0
    #: 'x_lo' | 'x_hi' | 'y_lo' | ... - which wall the opening is in
    vent_face: str = 'x_lo'
    #: (a0, a1, b0, b1) in that face's two in-plane axes
    vent_rect: tuple = ()
    #: 'burst' = a panel that lets go at `p_burst`; 'open' = an opening
    #: that was never closed. Same CFD case, different standing - see
    #: core/vent.py on why only one of them has a meaningful first front.
    open_mode: str = 'burst'
    p_burst: float = 0.0              # Pa; 0 with open_mode='burst' is
                                      # an error, not a default
    domain_size: tuple = ()           # (Lx, Ly, Lz) of the CFD domain
    cfd_dx_m: float = 0.0             # base cell
    cfd_window_s: float = 0.0         # how long the CFD runs
    n_snapshots_vent: int = 0         # 0 = 20
    #: (x, y, z) pressure gauges in the CFD domain - typically on the
    #: face of whatever structure the jet is aimed at
    vent_gauges: list = field(default_factory=list)

    @property
    def wants_vent(self):
        return bool(self.room_size and self.vent_rect and self.room_wall_m
                    and self.domain_size and self.cfd_dx_m
                    and self.cfd_window_s)

    # the structural component, or None to skip the response
    span_m: float = 0.0
    mass_per_area: float = 0.0
    Ru_pa: float = 0.0
    kE_pa_m: float = 0.0
    support: str = 'simple'
    rotation_limit_deg: float = 12.0

    @property
    def has_component(self):
        return all(v > 0 for v in (self.span_m, self.mass_per_area,
                                   self.Ru_pa, self.kE_pa_m))

    @property
    def wants_thermal(self):
        return (self.h_c > 0 and self.wall_area_m2 > 0) or bool(self.standoffs_m)

    def build_propellant(self):
        """The effective material: the table row with this case's
        overrides applied, and `uncalibrated` updated for whatever the
        user says was measured."""
        base = PROPELLANTS.get(self.propellant)
        if base is None:
            raise ValueError(f"Unknown propellant '{self.propellant}'")
        if not self.overrides and not self.measured:
            return base
        fields = set(type(base).__dataclass_fields__)
        bad = [k for k in self.overrides if k not in fields
               or k == 'uncalibrated']
        if bad:
            raise ValueError(f'not propellant properties: '
                             f'{", ".join(sorted(bad))}')
        unc = tuple(f for f in base.uncalibrated if f not in self.measured)
        return replace(base, **self.overrides, uncalibrated=unc)

    def build_scenario(self):
        return _scenario.IgnitionScenario(
            kind=self.scenario_kind, n_cohorts=self.n_cohorts,
            spread_time=self.spread_time, geometry=self.spread_geometry)


def case_to_dict(case):
    d = asdict(case)
    d['schema'] = SCHEMA
    d['version'] = VERSION
    return d


#: Fields that are fixed-length coordinates rather than open lists. JSON
#: has no tuple, so they come back as lists and a saved case would not
#: compare equal to the one that was saved - which is the whole point of
#: the round trip being tested.
_TUPLE_FIELDS = ('room_origin', 'room_size', 'vent_rect', 'domain_size')


def case_from_dict(d):
    if d.get('schema') != SCHEMA:
        raise ValueError(f'not an HD 1.3 case file (schema '
                         f'{d.get("schema")!r})')
    known = {f for f in DeflagrationCase.__dataclass_fields__}
    kw = {k: v for k, v in d.items() if k in known}
    for k in _TUPLE_FIELDS:
        if k in kw and kw[k] is not None:
            kw[k] = tuple(kw[k])
    if kw.get('vent_gauges'):
        kw['vent_gauges'] = [tuple(g) for g in kw['vent_gauges']]
    return DeflagrationCase(**kw)


def save_case(case, path):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(case_to_dict(case), fh, indent=2)
    return path


def load_case(path):
    with open(path, encoding='utf-8') as fh:
        return case_from_dict(json.load(fh))


def validate(case):
    """Pre-flight report, in the same shape the blast cases use."""
    rep = ValidationReport()
    err, warn, note = (rep.errors.append, rep.warnings.append,
                       rep.notes.append)

    try:
        prop = case.build_propellant()
    except ValueError as exc:
        err(str(exc))
        return rep
    if case.overrides:
        note('Material overrides in this case: '
             + ', '.join(sorted(case.overrides)))
    unmeasured = [k for k in case.overrides if k not in case.measured]
    if unmeasured:
        warn('Overridden but not declared measured, so still carried as '
             'estimates: ' + ', '.join(sorted(unmeasured)))
    if prop.p_extinction > 0:
        note(f'Extinction limit switched on at '
             f'{prop.p_extinction / 1e6:.3f} MPa. It is binary to the '
             f'answer - the burn continues or it stops - so sweep it.')
    if case.charge_kg <= 0:
        err('Charge mass must be positive')
    if case.confinement not in CONFINEMENTS:
        err(f'Confinement must be one of {CONFINEMENTS}')
    if case.t_end <= 0:
        err('End time must be positive')
    if case.vent_area_m2 < 0:
        err('Vent area cannot be negative')
    if not 0 < case.discharge_coeff <= 1:
        err('Discharge coefficient must be in (0, 1]')
    try:
        case.build_scenario()
    except ValueError as exc:
        err(str(exc))

    wants_confined = case.confinement in ('confined', 'both')
    if wants_confined:
        if case.volume_m3 <= 0:
            err('Chamber volume must be positive for a confined case')
        elif case.charge_kg > 0:
            try:
                p_cap = deflagration.closed_vessel_pmax(
                    prop, case.charge_kg, case.volume_m3)
            except ValueError as exc:
                err(str(exc))
            else:
                note(f'Closed-vessel limit p_max = lambda C / (V - b C) = '
                     f'{p_cap / 1e6:.2f} MPa')
                note(f'Loading density C/V = '
                     f'{case.charge_kg / case.volume_m3:.3f} kg/m3')
                if case.vent_area_m2 > 0:
                    note(f'Vent parameter A/V^(2/3) = '
                         f'{case.vent_area_m2 / case.volume_m3 ** (2 / 3):.4f}')
                # the extrapolation warning, before anything is computed
                if p_cap < prop.p_valid_min:
                    warn(f'The burn law was measured between '
                         f'{prop.p_valid_min / 1e6:.0f} and '
                         f'{prop.p_valid_max / 1e6:.0f} MPa, and this '
                         f'chamber cannot exceed {p_cap / 1e6:.2f} MPa. The '
                         f'whole run will be an extrapolation BELOW the '
                         f'data, where the dominant error is in the '
                         f'exponent n rather than in a.')
                if not deflagration.sustains(prop, case.charge_kg,
                                             case.volume_m3):
                    warn('This loading cannot reach its own extinction '
                         'limit: the charge would light and go out.')

    wants_open = case.confinement in ('unconfined', 'both')
    if wants_open and prop.r_atm <= 0:
        err(f"'{case.propellant}' has no atmospheric burn rate, which the "
            f'unconfined model needs. It must be measured, not taken from '
            f'a p^n fit made at closed-vessel pressures.')

    if case.scenario_kind == 'uniform':
        warn('Uniform ignition lights the whole charge at once. That is a '
             'laboratory condition - a closed-vessel sample really is lit '
             'that way - and for a magazine it assumes away the '
             'entrainment, which moves the peak by more than any material '
             'property does.')
    if wants_open and case.scenario_kind == 'uniform':
        warn('In the open, simultaneous ignition is not conservative but '
             'impossible: a grain cannot burn before the flame reaches '
             'it. Treat the result as a limit.')

    if case.p0_chamber < 0:
        err('chamber air pressure cannot be negative')
    elif case.p0_chamber == 0 and case.confinement != 'unconfined':
        warn('The chamber is being run EVACUATED. That is the closed-vessel '
             'condition, not a room: at magazine loading density the air '
             'already in the room is comparable to the product gas and '
             'carries much of the pressure. Set p0_chamber to atmospheric '
             'unless this really is a sealed test vessel.')

    # Said before the run, because afterwards the measured version in
    # `run` is the one that counts. This one is the cheap a-priori
    # version: the artefact grows with spread time, so a slow fire cut
    # into few steps is the shape at risk. See deflagration._COHORT_TOL.
    if (case.scenario_kind == 'progressive_package'
            and case.spread_time > 0 and case.n_cohorts < 20):
        # Only the PACKAGE case is a staircase now - a flame spread is
        # entrained as a ramp and converges by n = 20 (scenario.windows).
        # A package letting go really is a step, so it keeps the warning.
        warn(f'{case.n_cohorts} packages over {case.spread_time:g} s is a '
             f'coarse staircase - each one releases '
             f'{case.charge_kg / max(case.n_cohorts, 1):.3g} kg at once, '
             f'and unlike a flame front that is a genuine step rather '
             f'than a discretisation. The run measures what refining '
             f'costs and says so.')

    # Pyrotechnics, marked rather than half-modelled. Out of scope until
    # decided otherwise (owner, 2026-09-21).
    if getattr(prop, 'gas_yield', 1.0) < 1.0 or getattr(
            prop, 'Cp_condensed', 0.0) > 0.0:
        warn('This row carries a condensed-residue fraction, which is the '
             'pyrotechnic case. It is NOT modelled: every kilogram burnt is '
             'treated as gas, so the pressure is over-predicted and the '
             'heat retained by solid residue is ignored. Out of scope by '
             'decision, not by oversight.')

    if prop.uncalibrated:
        warn('Not calibrated for this material: '
             + ', '.join(prop.uncalibrated)
             + '. These are class-typical literature values. A '
               'closed-vessel record fixes the burn law, but can never fix '
               'the extinction limit, the atmospheric rate or the '
               'secondary heat.')

    if case.has_component:
        note('A structural response will be computed at the AMBIENT '
             'resistance. Thermal weakening is reported separately, for a '
             'later load case - steel does not heat in the time the '
             'pressure pulse lasts.')
    if case.standoffs_m:
        warn('Fireball radiation uses correlations fitted to hydrocarbon '
             'and BLEVE data; nothing equivalent is published for '
             'propellant stacks.')

    # HD1-3e. Checked HERE rather than at run time, so a row with no
    # provenance stops the case instead of producing a plausible
    # distance in metres with no symptom. See core/qd.py.
    for row in (case.qd_criteria or ()):
        try:
            from . import qd as _qd
            _qd.QDCriterion(**row)
        except (TypeError, ValueError) as exc:
            err(f'QD criterion {row!r}: {exc}')
    if case.qd_criteria:
        note(f'{len(case.qd_criteria)} quantity-distance criteria, all '
             f'entered by the user - this tool ships none, and each '
             f'distance is printed with the source it came from.')

    # WHAT THE BAND WILL COST, BEFORE IT IS PAID. Five axes means up to
    # 43 solves, and on the form's own defaults that measured 15.6
    # minutes. No axis is cut for it: each one is there because it moves
    # the answer, and trimming the envelope for speed is the thing the
    # envelope exists to prevent. But nobody should discover the wait by
    # waiting.
    if case.sensitivity:
        from . import sensitivity as _sens
        secs, n_solves, how = _sens.estimate_seconds(case)
        warn(f'The sensitivity band will run about {n_solves} solves, '
             f'roughly {secs / 60.0:.0f} minutes ({how}). No axis is '
             f'dropped to make that shorter - each is in the envelope '
             f'because it moves the answer, and a band trimmed for speed '
             f'is the thing a band exists to prevent. Turn it off if you '
             f'only want the point estimate, and read that estimate as a '
             f'point.')

    # ── HD1-3f · the venting stage, checked before a mesh is planned ────
    #
    # INTENT COMES FROM THE GEOMETRY, not from the scalars. The form
    # pre-fills a wall thickness, a base cell and a window because those
    # are useful once someone starts, and keying "is a venting stage
    # wanted" off any-field-set made a BRAND NEW form refuse itself as
    # half filled in. Caught by _e2e_hd13_gui.py on a real window, which
    # is what that file is for: pressing Run on an untouched dim-0 case
    # raised out of the slot and took the process with it.
    _geom = (case.room_size, case.vent_rect, case.domain_size)
    if any(_geom) and not all(_geom):
        err('The venting stage is half filled in: it needs a room size, '
            'a vent rectangle AND a domain size. A partial geometry is '
            'not a smaller case, it is no case.')
    elif all(_geom) and not case.wants_vent:
        err('The venting stage has its geometry but not its numbers - it '
            'also needs a wall thickness, a base cell and a CFD window.')
    elif case.wants_vent:
        from . import room as _room
        if case.open_mode not in ('burst', 'open'):
            err("Opening mode must be 'burst' or 'open'")
        if case.open_mode == 'burst' and case.p_burst <= 0:
            err('A burst panel needs the pressure it lets go at. Without '
                'one there is no instant to hand over at, and taking the '
                'peak instead would silently turn this into the '
                'opened-from-the-start case, whose first front is an '
                'initialisation artefact.')
        if case.open_mode == 'open':
            warn('Opened from the start: the first front out of the '
                 'opening will be an ARTEFACT of initialising a '
                 'pressurised room against ambient. No peak or impulse '
                 'may be read from it - only steady-jet quantities after '
                 'it has passed.')
        try:
            m = _room.measure(case.room_origin, case.room_size,
                              case.room_wall_m, case.cfd_dx_m,
                              vent=(case.vent_face,)
                              + tuple(float(v) for v in case.vent_rect))
        except (TypeError, ValueError) as exc:
            err(f'Room: {exc}')
            m = None
        if m is not None:
            for e in m['errors']:
                err(f'Room: {e}')
            for w in m['warnings']:
                warn(f'Room: {w}')
            # TWELVE CELLS ACROSS THE OPENING, and the number is a
            # measurement. `room.MIN_VENT_CELLS` is six, which buys the
            # mass flow; a run that reports a LOAD needs the discharge
            # coefficient too, and that was measured moving 12.1 %
            # between six cells and twelve. Blocking, because the
            # symptom is a jet that is quietly weak rather than a run
            # that fails. See room.MIN_VENT_CELLS_LOAD.
            cells = m.get('vent_cells') or ()
            if cells and min(cells) < _room.MIN_VENT_CELLS_LOAD:
                err(f'The opening is {cells[0]} x {cells[1]} base cells. '
                    f'Six is enough for the mass flow, but this run '
                    f'reports a load on a structure and that needs the '
                    f'discharge coefficient as well - measured moving '
                    f'12.1 % between six cells and twelve, with the '
                    f'coarse mesh passing LESS. Refine to at least '
                    f'{_room.MIN_VENT_CELLS_LOAD} across, i.e. '
                    f'dx <= {m["vent_area"] ** 0.5 / _room.MIN_VENT_CELLS_LOAD:.4f} m.')
            elif cells:
                note(f'The opening is {cells[0]} x {cells[1]} base '
                     f'cells. At twelve the CFD flow may still be up to '
                     f'~10 % below the converged value, and the '
                     f'direction is known: less out, so a slightly weak '
                     f'jet. Cd is an axis of the sensitivity band for '
                     f'exactly this reason.')
            # The 0-D half of this case and the room have to describe the
            # same building. `build_vent_case` re-runs the 0-D model at
            # the aligned cavity, so this is a note rather than an error -
            # but a big gap usually means two different rooms.
            if m['volume'] > 0 and case.volume_m3 > 0 and \
                    abs(case.volume_m3 / m['volume'] - 1.0) > 0.1:
                warn(f'The 0-D chamber volume ({case.volume_m3:.3f} m3) '
                     f'and the meshed room ({m["volume"]:.3f} m3) differ '
                     f'by {case.volume_m3 / m["volume"] - 1.0:+.0%}. The '
                     f'venting stage re-runs the 0-D model at the meshed '
                     f'cavity, so the two answers in this report will not '
                     f'be for the same room.')
            dom = [float(v) for v in case.domain_size]
            cells = 1
            for L in dom:
                cells *= max(1, int(round(L / case.cfd_dx_m)))
            note(f'Venting stage: {cells:,} base cells over a '
                 f'{dom[0]:g} x {dom[1]:g} x {dom[2]:g} m domain at '
                 f'dx = {case.cfd_dx_m:g} m.')
            hi = [float(o) + float(s) for o, s
                  in zip(case.room_origin, case.room_size)]
            if any(h > L + 1e-9 for h, L in zip(hi, dom)):
                err(f'The room sticks out of the CFD domain: it reaches '
                    f'{tuple(round(h, 3) for h in hi)} m in a '
                    f'{tuple(dom)} m box.')
    return rep


def build_vent_case(case, dim=3):
    """HD1-3f: turn a 0-D assessment into the blastFoam case that
    resolves the jet leaving its opening.

    Returns `(Case3D, info)`. `info` carries the aligned room, the
    chamber state, the validity metrics and the warnings, because every
    one of those is a caveat that has to reach the report rather than
    being consumed here.

    THE ORDER MATTERS AND IS NOT THE OBVIOUS ONE. The room is aligned to
    the mesh FIRST, and only then is the 0-D model run - at the ALIGNED
    cavity volume, not at the volume the user typed. Doing it the other
    way round hands the mesh a state computed for a room that is up to
    10 % larger than the one about to be built (see core/room.py), and
    `validate_case` would rightly refuse it.
    """
    from . import room as _room, vent as _vent
    from .case import Case3D
    if not case.wants_vent:
        raise ValueError(
            'this case has no venting stage: it needs a room size, a wall '
            'thickness, a vent rectangle, a domain, a base cell and a CFD '
            'window. See DeflagrationCase.wants_vent.')
    if dim != 3:
        raise ValueError('only the 3D venting stage is implemented')

    dx = float(case.cfd_dx_m)
    vent_spec = (case.vent_face,) + tuple(float(v) for v in case.vent_rect)
    m = _room.measure(case.room_origin, case.room_size, case.room_wall_m,
                      dx, vent=vent_spec)
    if not m['ok']:
        raise ValueError('the room cannot be meshed: '
                         + '; '.join(m['errors']))

    # THE 0-D MODEL RUNS AT THE ALIGNED CAVITY. Not at `case.volume_m3`,
    # which is whatever the 0-D half of the assessment was set up with -
    # the two have to describe the same room or the pressure written
    # into the cells is wrong by their ratio.
    prop = case.build_propellant()
    sc = case.build_scenario()
    r = deflagration.simulate(
        prop, case.charge_kg, m['volume'],
        # the panel holds until it bursts, so the 0-D run that CHOOSES
        # the instant is sealed; an opening that was never closed is run
        # with its real area
        vent_area=(0.0 if case.open_mode == 'burst' else m['vent_area']),
        cd=case.discharge_coeff, t_end=case.t_end, n_out=case.n_out,
        scenario=sc, p_ign=(case.p_ign or None),
        p0_chamber=case.p0_chamber, h_c=case.h_c,
        wall_area=case.wall_area_m2, T_wall=case.T_wall)
    st = _vent.handoff(r, prop, mode=case.open_mode,
                       p_burst=(case.p_burst or None),
                       volume_cfd=m['volume'])
    val = _vent.validity(r, st, case.cfd_window_s, prop=prop,
                         vent_area=m['vent_area'])

    Lx, Ly, Lz = (float(v) for v in case.domain_size)
    cfd = Case3D(
        solver='blastfoam', Lx=Lx, Ly=Ly, Lz=Lz, cell_size_m=dx,
        init_mode='chamber', charge=0.0,
        room=m, chamber_state=st.as_dict(), obstacles=m['boxes'],
        # The ground reflects and everything else lets the wave out.
        # A reflection arriving back at the target inside the window
        # would be indistinguishable from the jet - see TODO.md HD1-3.
        bcs=dict(x_lo='transmit', x_hi='transmit', y_lo='transmit',
                 y_hi='transmit', z_lo='reflect', z_hi='transmit'),
        t_end=float(case.cfd_window_s),
        n_snapshots=case.n_snapshots_vent or 20,
        gauges=[tuple(g) for g in (case.vent_gauges or ())])
    return cfd, {
        'room': m, 'state': st, 'validity': val, 'zero_d': r,
        'warnings': list(st.warnings or ()) + list(val['warnings'])
        + list(m['warnings']),
    }


def run(case):
    """Run the whole assessment. Returns a bundle ready for
    `output.hd13.save_hd13_report`."""
    rep = validate(case)
    if not rep.ok:
        raise ValueError('; '.join(rep.errors))
    prop = case.build_propellant()
    sc = case.build_scenario()
    out = dict(case=case, prop=prop, report=rep, confined=None,
               unconfined=None, thermal=None, radiation=(), sdof=None,
               component=None, band=None, sensitivity=None,
               sensitivity_note='', verdict=None, qd=None)

    if case.confinement in ('confined', 'both'):
        out['confined'] = deflagration.simulate(
            prop, case.charge_kg, case.volume_m3,
            vent_area=case.vent_area_m2, cd=case.discharge_coeff,
            t_end=case.t_end, n_out=case.n_out, scenario=sc,
            p_ign=(case.p_ign or None), p0_chamber=case.p0_chamber,
            # The same h_c the thermal path uses, now also taken OUT of
            # the gas. Until 2026-09-21 the wall flux was computed from a
            # gas that never gave the energy up, so T and p at the end of
            # the burn were the adiabatic ones while the wall was being
            # heated for free. Off unless both numbers are given.
            h_c=case.h_c, wall_area=case.wall_area_m2, T_wall=case.T_wall)
    if case.confinement in ('unconfined', 'both'):
        out['unconfined'] = unconfined.burn(prop, case.charge_kg,
                                            scenario=sc)

    conf = out['confined']
    # The cohort count is a mesh, and a peak that moves when it is halved
    # is not an answer. This has to be raised AFTER the run because it is
    # measured, not predicted - `validate` can only say the case looks
    # like one at risk. See deflagration._COHORT_TOL.
    if conf is not None and not conf['cohort_converged']:
        rep.warnings.append(
            f'The peak moved {conf["cohort_refinement_error"]:.0%} when the '
            f'cohort count was doubled from {conf["n_cohorts"]} to '
            f'{2 * conf["n_cohorts"]} ({conf["p_max"] / 1e6:.3f} MPa against '
            f'{conf["p_max_refined"] / 1e6:.3f}). The ignition staircase, '
            f'not the fire, is setting this peak. Raise n_cohorts until it '
            f'stops moving before quoting the number.')

    # THE BAND, and it is deliberately reported in the same units and
    # next to the same number it qualifies. `PROPELLANTS` ships
    # uncalibrated on every row, so the point estimate above is a point
    # estimate from a burn law fitted two decades away.
    if case.sensitivity and conf is not None:
        from . import sensitivity as _sens
        b = _sens.band(
            prop, case.charge_kg, case.volume_m3,
            dn=case.sens_dn, a_factor=case.sens_a_factor,
            pext_factor=case.sens_pext_factor,
            hc_factor=case.sens_hc_factor,
            source=case.sensitivity_source,
            vent_area=case.vent_area_m2, cd=case.discharge_coeff,
            t_end=case.t_end, n_out=case.n_out, scenario=sc,
            p_ign=(case.p_ign or None), p0_chamber=case.p0_chamber,
            h_c=case.h_c, wall_area=case.wall_area_m2, T_wall=case.T_wall)
        out['band'] = b
        out['sensitivity'] = {
            'peak pressure [MPa]': (b['low']['p_max'] / 1e6,
                                    b['high']['p_max'] / 1e6),
            'time to peak [s]': (b['low']['t_p_max'], b['high']['t_p_max']),
            'fraction burnt [-]': (b['low']['Z_end'], b['high']['Z_end']),
        }
        out['sensitivity_note'] = _sens.summary_line(b)
        rep.warnings.append(
            f'The peak is uncertain by a factor of {b["spread"]:.1f} over '
            f'the burn-law ranges alone ({b["low"]["p_max"]/1e6:.3f} to '
            f'{b["high"]["p_max"]/1e6:.3f} MPa). ' + (
                '' if b['ranges_sourced'] else
                'And the ranges themselves are judgements, not a record, '
                'so the WIDTH is not citable either.'))
        if not b['spans_heat_loss']:
            rep.warnings.append(
                'The band does NOT span the heat-loss assumption: this '
                'case is adiabatic, so h_c has nothing to perturb. That '
                'matters more than it sounds - h_c is not calibrated by '
                'anything here, and switching it on moves the state at '
                'burst by 12 % on the mass burnt where it moves T by 1 %. '
                'The envelope above is narrower than the truth by '
                'whatever the wall coefficient is worth.')
        if b['straddles_extinction']:
            rep.warnings.append(
                'The band straddles the extinction limit: part of it is a '
                'fire that goes out and part is one that does not. Those '
                'are two different events and a range across them is not '
                'a pressure interval.')
        if not b['conserved']:
            rep.errors.append('A sample inside the sensitivity band failed '
                              'its own conservation check, so the band is '
                              'void.')

    if conf is not None and case.h_c > 0 and case.wall_area_m2 > 0:
        out['thermal'] = thermal.wall_exposure(
            conf['t'], conf['T'], h_c=case.h_c, T_wall=case.T_wall)
        # The gas paid for this, which it did not before. Said out loud
        # because it cuts the peak pressure, i.e. it moves the structural
        # answer in the UN-conservative direction.
        rep.notes.append(
            f'Heat loss to the walls is taken OUT of the gas: '
            f'{conf["Q_wall"]/1e6:.2f} MJ, '
            f'{conf["wall_loss_fraction"]:.1%} of the energy released. '
            f'That lowers the peak pressure, so this run is NOT the '
            f'adiabatic upper bound - set h_c to 0 for that.')

    if case.standoffs_m:
        burnt = (out['unconfined']['z'][-1] if out['unconfined']
                 else (conf['Z'][-1] if conf else 0.0))
        energy, _ana, _sec = thermal.fireball_energy(
            prop, case.charge_kg * burnt)
        if energy > 0:
            fb = thermal.fireball(energy, mass_kg=case.charge_kg)
            out['fireball'] = fb
            out['radiation'] = [thermal.radiation_at(fb, float(r))
                                for r in case.standoffs_m]

    # HD1-3e. Always evaluated when standoffs were given, even with no
    # criteria - because a siting report that OMITS the comparison reads
    # as though it was not needed, while one that prints the sentence
    # says it was not done. Only the second is true.
    if case.standoffs_m or case.qd_criteria:
        from . import qd as _qd
        # Already validated - a bad row refuses the case before it runs,
        # because a siting distance from a remembered factor is worse
        # than no siting distance.
        crits = [_qd.QDCriterion(**row) for row in case.qd_criteria]
        fb = out.get('fireball')
        out['qd'] = _qd.compare(
            crits, case.standoffs_m, charge_kg=case.charge_kg,
            # `fireball` reports a DIAMETER; a criterion written against
            # the radius must be given a radius. Halving it here rather
            # than hoping the person entering K knew which one this
            # returns.
            fireball_radius=(0.5 * fb['diameter'] if fb else None))
        if not out['qd']['have_criteria']:
            rep.notes.append(_qd.NO_CRITERIA)

    if case.has_component and conf is not None:
        from . import sdof as _sdof
        comp = _sdof.Component(span=case.span_m,
                               mass_per_area=case.mass_per_area,
                               Ru=case.Ru_pa, kE=case.kE_pa_m,
                               support=case.support,
                               rotation_limit_deg=case.rotation_limit_deg)
        out['component'] = comp
        out['sdof'] = _sdof.response(conf['t'], conf['p'], comp,
                                     p_ref=P_AIR)
        if out['thermal'] is not None:
            out['residual'] = thermal.residual_capacity(
                case.Ru_pa, out['thermal']['T_surface_max'])

        # THE VERDICT AT BOTH ENDS OF THE BAND, not just at the nominal
        # point. The band on a vented magazine spans more than an order
        # of magnitude and a wall's response is not linear in the load,
        # so a verdict at the middle says nothing about whether it holds
        # at the ends. Three answers, and the third is an answer.
        if out['band'] is not None:
            from . import sensitivity as _sens
            v = _sens.structural_verdict(out['band'], comp)
            out['verdict'] = v
            if v['verdict'] == 'undetermined_within_band':
                rep.warnings.append(
                    f'STRUCTURAL VERDICT UNDETERMINED. The element '
                    f'survives the low end of the band '
                    f'({v["low"]["p_max"]/1e6:.3f} MPa, mu '
                    f'{v["low"]["ductility"]:.2f}) and yields at the high '
                    f'end ({v["high"]["p_max"]/1e6:.3f} MPa, mu '
                    f'{v["high"]["ductility"]:.2f}). Whether this wall '
                    f'holds depends on a burn law nobody has measured for '
                    f'this material; a closed-vessel record on the real '
                    f'propellant is what settles it, and nothing else '
                    f'will.')
            else:
                rep.notes.append(
                    f'Structural verdict: {v["verdict"].replace("_", " ")} '
                    f'(mu {v["low"]["ductility"]:.2f} at the low end, '
                    f'{v["high"]["ductility"]:.2f} at the high). '
                    + v['note']
                    + ('' if v['ranges_sourced'] else
                       ' The band it is taken across rests on ranges that '
                       'are a judgement, so this robustness is only as '
                       'wide as that judgement.'))
    return out
