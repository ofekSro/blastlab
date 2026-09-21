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

    confinement: str = 'confined'
    scenario_kind: str = 'uniform'
    n_cohorts: int = 1
    spread_time: float = 0.0
    spread_geometry: str = 'line'

    t_end: float = 5.0
    n_out: int = 1000

    # heat (0 = that part is not asked for)
    h_c: float = 0.0
    wall_area_m2: float = 0.0
    T_wall: float = 300.0
    standoffs_m: list = field(default_factory=list)

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


def case_from_dict(d):
    if d.get('schema') != SCHEMA:
        raise ValueError(f'not an HD 1.3 case file (schema '
                         f'{d.get("schema")!r})')
    known = {f for f in DeflagrationCase.__dataclass_fields__}
    return DeflagrationCase(**{k: v for k, v in d.items() if k in known})


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
    return rep


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
               component=None)

    if case.confinement in ('confined', 'both'):
        out['confined'] = deflagration.simulate(
            prop, case.charge_kg, case.volume_m3,
            vent_area=case.vent_area_m2, cd=case.discharge_coeff,
            t_end=case.t_end, n_out=case.n_out, scenario=sc,
            p_ign=(case.p_ign or None))
    if case.confinement in ('unconfined', 'both'):
        out['unconfined'] = unconfined.burn(prop, case.charge_kg,
                                            scenario=sc)

    conf = out['confined']
    if conf is not None and case.h_c > 0 and case.wall_area_m2 > 0:
        out['thermal'] = thermal.wall_exposure(
            conf['t'], conf['T'], h_c=case.h_c, T_wall=case.T_wall)

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
    return out
