"""HD1-11a: the HD 1.3 assessment case - `DeflagrationCase` and its JSON
form. The model that runs it (`validate`, `run`) stays in
`core/assessment.py`, which re-exports every name here.

Moved verbatim from `core/assessment.py` in Phase 2 of
docs/ARCHITECTURE_REVIEW.md (section 5). This module imports only `core`.
"""

import json
from dataclasses import asdict, dataclass, field, replace

from ..core import scenario as _scenario
from ..core.constants import P_AIR
from ..core.fuels import PROPELLANTS

SCHEMA = 'blastlab-hd13'
VERSION = 1


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
