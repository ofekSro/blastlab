"""The ONE form <-> Case mapping: plain `{field_name: value}` dicts in,
a Case out, and back.

docs/ARCHITECTURE_REVIEW.md section 5, Phase 5a (finding F4). Moved from
`ui/case_form.py` (`_f`, `_i`, `_trig`, `CaseForm._csv`,
`CaseForm._HD13_UNITS`, `CaseForm.get_case/_get_case_hd13`,
`CaseForm.set_case/_set_case_hd13/_set_trigger`, `_order_label`) with
`v[name].get()` replaced by `values[name]` and `v[name].set(x)` by an
entry in the returned dict. Toolkit-free: this module imports only
`core` and `models`, so a script or a test can build the case a form
would build without a QApplication.

The field names are the Setup form's (`ui/setup_spec.py`). A `values`
dict holds what the form's widgets hold:

  * a text / number / choice / file field: the str the widget shows;
  * a check box ('measured', 'record', 'anim_mesh'): a bool;
  * a point list ('gauges', 'obstacles', 'zones', 'det_pts',
    'extra_charges', 'standoffs', 'vent_gauges'): a list of float tuples.

`case_from_fields` reports EVERY bad numeric field rather than the first,
and never reads a field the active solver hides - that solver's default
goes into the case instead, so what the user sees is what runs and saves.
"""

import math

from ..core.bc import normalize_bc, normalize_bcs
from ..core.constants import ANIM_SCALE_LABELS, P_AIR, anim_scale_from_label
from .case import Case1D, Case2D, Case3D


# ── parsers ──────────────────────────────────────────────────────────────
def parse_float(raw, name):
    """Parse a float field with a helpful error.

    'nan'/'inf'/'1e400' parse as floats but are not usable geometry: they
    used to reach validation and produce messages like "r_exp = inf m
    pokes through the boundary" instead of being refused."""
    try:
        val = float(raw)
    except ValueError:
        raise ValueError(f"'{name}' is not a number: {raw!r}")
    if not math.isfinite(val):
        raise ValueError(f"'{name}' must be a finite number: {raw!r}")
    return val


def parse_int(raw, name):
    """Parse an integer field. A fractional entry is refused rather than
    silently truncated (n_snapshots = 2.7 used to become 2)."""
    try:
        val = float(raw)
    except ValueError:
        raise ValueError(f"'{name}' is not an integer: {raw!r}")
    if not math.isfinite(val) or val != int(val):
        raise ValueError(f"'{name}' must be a whole number: {raw!r}")
    return int(val)


def parse_trigger(raw):
    """The trigger-gauge box as a 1-based gauge number, or None when it
    is blank/zero. A non-numeric entry is treated as off here and caught
    by validate_case, which reports it with the other field errors."""
    raw = str(raw).strip()
    if not raw:
        return None
    try:
        n = int(float(raw))
    except ValueError:
        return None
    return n or None


def parse_csv(text, n):
    """`n` comma-separated numbers, or () when the field is blank.

    Blank is an ANSWER here, not a failure: every venting-stage row
    is optional and `DeflagrationCase.wants_vent` is what decides
    whether a CFD case gets built at all. A field with the WRONG
    COUNT also comes back as () rather than half a geometry -
    validation then refuses the case as half filled in, which is the
    message that helps, instead of the form silently keeping two of
    three coordinates.
    """
    parts = [p for p in str(text or '').replace(';', ',').split(',')
             if p.strip()]
    if len(parts) != n:
        return ()
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        return ()


def order_label(case):
    """The reconstruction-order choice text for a case's `order`."""
    return ('2 (MUSCL)' if int(getattr(case, 'order', 1) or 1) == 2
            else '1 (Godunov)')


# ── HD 1.3, dim 0 (HD1-11c) ──────────────────────────────────────────────
# A deflagration case shares no field with the blast ones, so it gets
# its own pair rather than branches threaded through theirs. The unit
# conversions live here and only here: the form speaks kPa, MPa, mm
# and mm/s because that is what an engineer writes down, and the case
# is SI throughout.
HD13_UNITS = (
    # (form key, case/override key, factor form -> SI)
    ('ov_n', 'n', 1.0),
    ('ov_a', 'a', 1.0),
    ('ov_r_atm', 'r_atm', 1e-3),           # mm/s
    ('ov_web', 'web', 1e-3),               # mm
    ('ov_p_ext', 'p_extinction', 1e6),     # MPa
    ('ov_secondary', 'secondary_heat', 1e6),   # MJ/kg
)


def hd13_case_from_fields(values):
    """`(DeflagrationCase, errors, bad_field_names)` from the 0-D form's
    values."""
    # deferred, as it was in the form: only the 0-D form needs it
    from .hd13_case import DeflagrationCase
    v = values
    errs, bad = [], []

    def num(name, label, factor=1.0, blank=None):
        raw = v[name].strip()
        if not raw:
            return blank
        try:
            return parse_float(v[name], label) * factor
        except ValueError as exc:
            errs.append(str(exc))
            bad.append(name)
            return blank if blank is not None else 0.0

    overrides, measured = {}, []
    for key, field_name, factor in HD13_UNITS:
        got = num(key, field_name, factor)
        if got is not None:
            overrides[field_name] = got
            measured.append(field_name)
    if not v['measured']:
        measured = []

    try:
        cohorts = parse_int(v['n_cohorts'], 'Cohorts') or 1
    except ValueError as exc:
        errs.append(str(exc))
        bad.append('n_cohorts')
        cohorts = 1
    try:
        n_out = parse_int(v['n_out'], 'Samples') or 1000
    except ValueError as exc:
        errs.append(str(exc))
        bad.append('n_out')
        n_out = 1000
    # 0 means "the builder's default", so a blank box is not an error
    try:
        snap_vent = (parse_int(v['n_snap_vent'], 'Vent snapshots')
                     if v['n_snap_vent'].strip() else 0)
    except ValueError as exc:
        errs.append(str(exc))
        bad.append('n_snap_vent')
        snap_vent = 0

    span = num('span_m', 'Span', blank=0.0) or 0.0
    case = DeflagrationCase(
        name=v['name'].strip(),
        propellant=v['propellant'],
        overrides=overrides, measured=measured,
        charge_kg=num('charge_kg', 'Charge', blank=0.0) or 0.0,
        volume_m3=num('volume_m3', 'Chamber volume', blank=0.0) or 0.0,
        vent_area_m2=num('vent_area', 'Vent area', blank=0.0) or 0.0,
        discharge_coeff=num('cd', 'Discharge coefficient',
                            blank=0.8) or 0.8,
        p_ign=(num('p_ign', 'Igniter pressure', 1e6, blank=0.0) or 0.0),
        # blank means "the room has air in it", not "evacuate it" -
        # a blank field must never silently pick the rarer physics.
        # An explicit 0 still means an evacuated vessel.
        p0_chamber=num('p0_chamber', 'Air in the room', 1e6,
                       blank=P_AIR),
        confinement=v['confinement'],
        scenario_kind=v['scenario_kind'],
        n_cohorts=cohorts,
        spread_time=num('spread_time', 'Spread time', blank=0.0) or 0.0,
        spread_geometry=v['spread_geometry'],
        t_end=num('t_end', 'End time', blank=0.0) or 0.0,
        n_out=n_out,
        h_c=num('h_c', 'Wall heat transfer', blank=0.0) or 0.0,
        wall_area_m2=num('wall_area', 'Wall area', blank=0.0) or 0.0,
        T_wall=num('t_wall', 'Wall temperature', blank=300.0) or 300.0,
        standoffs_m=[float(r[0]) for r in v['standoffs']],
        span_m=span,
        mass_per_area=num('mass_per_area', 'Mass', blank=0.0) or 0.0,
        Ru_pa=num('ru_kpa', 'Ultimate resistance', 1e3, blank=0.0) or 0.0,
        kE_pa_m=num('ke_mpa_m', 'Elastic stiffness', 1e6,
                    blank=0.0) or 0.0,
        support=v['support'],
        rotation_limit_deg=num('rot_limit', 'Collapse rotation',
                               blank=12.0) or 12.0,
        # HD1-3f. Blank means NO venting stage, which is the common
        # case: a 0-D assessment is complete without one.
        room_origin=(parse_csv(v['room_origin'], 3)
                     or (0.0, 0.0, 0.0)),
        room_size=parse_csv(v['room_size'], 3),
        room_wall_m=num('room_wall', 'Wall thickness', blank=0.0) or 0.0,
        vent_face=v['vent_face'],
        vent_rect=parse_csv(v['vent_rect'], 4),
        open_mode=v['open_mode'],
        p_burst=(num('p_burst', 'Burst pressure', 1e6, blank=0.0)
                 or 0.0),
        domain_size=parse_csv(v['domain_size'], 3),
        cfd_dx_m=num('cfd_dx', 'Base cell', blank=0.0) or 0.0,
        cfd_window_s=num('cfd_window', 'CFD window', blank=0.0) or 0.0,
        n_snapshots_vent=snap_vent,
        vent_gauges=[tuple(float(c) for c in r)
                     for r in v['vent_gauges']],
    )
    # a uniform scenario has no spread; saying so here keeps the form
    # from building a case its own validator would reject
    if case.scenario_kind == 'uniform':
        case.spread_time = 0.0
        case.n_cohorts = 1
    return case, errs, bad


def hd13_fields_from_case(case):
    """The 0-D form's values for `case`, in the order the form sets
    them."""
    out = {}
    out['name'] = case.name
    out['propellant'] = case.propellant
    for key, field_name, factor in HD13_UNITS:
        got = case.overrides.get(field_name)
        out[key] = '' if got is None else f'{got / factor:g}'
    out['measured'] = bool(case.measured)
    for key, value in (
            ('charge_kg', case.charge_kg),
            ('volume_m3', case.volume_m3),
            ('vent_area', case.vent_area_m2),
            ('cd', case.discharge_coeff),
            ('p_ign', case.p_ign / 1e6),
            ('p0_chamber', case.p0_chamber / 1e6),
            ('n_cohorts', case.n_cohorts),
            ('spread_time', case.spread_time),
            ('t_end', case.t_end),
            ('n_out', case.n_out),
            ('h_c', case.h_c),
            ('wall_area', case.wall_area_m2),
            ('t_wall', case.T_wall),
            ('span_m', case.span_m),
            ('mass_per_area', case.mass_per_area),
            ('ru_kpa', case.Ru_pa / 1e3),
            ('ke_mpa_m', case.kE_pa_m / 1e6),
            ('rot_limit', case.rotation_limit_deg)):
        out[key] = f'{value:g}'
    for key, value in (('confinement', case.confinement),
                       ('scenario_kind', case.scenario_kind),
                       ('spread_geometry', case.spread_geometry),
                       ('support', case.support)):
        out[key] = value
    out['standoffs'] = [(r,) for r in case.standoffs_m]

    # HD1-3f. An empty tuple round-trips as an EMPTY BOX, not as
    # '0,0,0': blank is what "no venting stage" looks like, and
    # writing zeros back would turn a case that had none into one
    # with a degenerate room the validator then has to reject.
    def _csv_out(t):
        return ','.join(f'{x:g}' for x in t) if t else ''

    for key, value in (('room_size', case.room_size),
                       ('vent_rect', case.vent_rect),
                       ('domain_size', case.domain_size)):
        out[key] = _csv_out(value)
    out['room_origin'] = _csv_out(case.room_origin) or '0,0,0'
    for key, value in (('vent_face', case.vent_face),
                       ('open_mode', case.open_mode)):
        out[key] = value
    for key, value in (('room_wall', case.room_wall_m),
                       ('p_burst', case.p_burst / 1e6),
                       ('cfd_dx', case.cfd_dx_m),
                       ('cfd_window', case.cfd_window_s)):
        out[key] = f'{value:g}'
    out['n_snap_vent'] = (f'{case.n_snapshots_vent:g}'
                          if case.n_snapshots_vent else '')
    out['vent_gauges'] = [tuple(g) for g in case.vent_gauges]
    return out


# ── the blast cases, dims 1-3 ────────────────────────────────────────────
def case_from_fields(dim, values, mode):
    """`(case, errors, bad_field_names)` from a form's values.

    `mode` is the normalised solver mode ('native' | 'blastfoam'). EVERY
    bad numeric field is reported, not just the first one: the strip used
    to show a single message and the user fixed them one reload at a
    time. A bad field contributes 0 (or the knob's default) to the case,
    so the case is always built; the caller refuses it when `errors` is
    not empty.

    Fields hidden by the solver mode are STRIPPED, not read: the case
    carries that solver's defaults for them, and a stale bad value in
    a hidden box can never block a run."""
    if dim == 0:
        return hd13_case_from_fields(values)
    v = values
    errs, bad = [], []
    foam = mode == 'blastfoam'

    def _F(name, label):
        try:
            return parse_float(v[name], label)
        except ValueError as exc:
            errs.append(str(exc))
            bad.append(name)
            return 0.0

    def _I(name, label):
        try:
            return parse_int(v[name], label)
        except ValueError as exc:
            errs.append(str(exc))
            bad.append(name)
            return 0

    def _ORD():
        """The reconstruction order out of '1 (Godunov)'. A native
        knob: blastFoam uses its own schemes and validate_case says
        so, so in blastFoam mode the dataclass default goes in and
        the box is not read at all. Guarded, unlike the Tk form,
        where a mangled value raised IndexError out of get_case."""
        if foam:
            return 1
        raw = str(v['order'])
        try:
            return int(raw.split()[0] or 1)
        except (IndexError, ValueError):
            errs.append(f"'order' is not a reconstruction order: "
                        f"{raw!r}")
            bad.append('order')
            return 1

    def _eos():
        # likewise ignored by blastFoam (validate_case notes it)
        return v['eos'] if not foam else 'idealGas'

    if dim == 1:
        return Case1D(
            radius_m=_F('radius_m', 'radius'),
            charge_kg=_F('charge', 'charge'),
            cell_size_m=_F('cell', 'cell size'),
            eos=_eos(), cfl=_F('cfl', 'cfl'),
            order=_ORD(),
            bc_outer=v['bc_outer'],
            n_snapshots=_I('n_snapshots', 'snapshots'),
            t_end=_F('t_end', 'end time'),
            gauge_radii=[g[0] for g in v['gauges']],
            # `or None` like its neighbours: without it an empty box
            # became '' and a None round-tripped through the widget
            # as the string 'None', which the writer then used as a
            # FILE NAME - runs left a file called "None" behind
            gauge_file=v['gauge_file'] or None,
            profile_file=v['profile_out'] or None,
            solver=mode,
            material=v['material'] if foam else 'TNT',
            activation=v['activation'] if foam else 'linear',
            afterburn=v['afterburn'] if foam else 'none'), errs, bad

    bcs = {side: v[f'bc_{side}']
           for side in (('x_lo', 'x_hi', 'y_lo', 'y_hi') if dim == 2
                        else ('x_lo', 'x_hi', 'y_lo', 'y_hi',
                              'z_lo', 'z_hi'))}
    amr_levels = _I('amr_levels', 'AMR levels') if foam else 0
    amr_on = foam and amr_levels > 0
    # the two range boxes are read only while the scale is manual,
    # so a stale value in a hidden box cannot block a run
    _anim_scale = anim_scale_from_label(v['anim_scale'])
    common = dict(
        Lx=_F('Lx', 'Lx'), Ly=_F('Ly', 'Ly'),
        cell_size_m=_F('cell', 'cell size'),
        init_mode=v['init_mode'],
        charge=_F('charge', 'charge'),
        profile_file_in=v['profile_in'] or None,
        eos=_eos(), bcs=bcs,
        order=_ORD(),
        obstacles=v['obstacles'], cfl=_F('cfl', 'cfl'),
        n_snapshots=_I('n_snapshots', 'snapshots'),
        gauges=v['gauges'],
        gauge_file=v['gauge_file'] or None,
        t_end=_F('t_end', 'end time'),
        trigger_gauge=parse_trigger(v['trigger_gauge']),
        trigger_action=v['trigger_action'],
        trigger_file=(v['trigger_file'] or None
                      if dim < 3 else None),
        anim_file=v['anim_file'] or None,
        anim_mesh=bool(v['anim_mesh']),
        anim_scale=_anim_scale,
        anim_clim=((_F('anim_clim_min', 'video colour min'),
                    _F('anim_clim_max', 'video colour max'))
                   if _anim_scale == 'manual' else None),
        record_frames=150 if v['record'] else 0,
        solver=mode,
        material=v['material'] if foam else 'TNT',
        activation=v['activation'] if foam else 'linear',
        afterburn=v['afterburn'] if foam else 'none',
        n_procs=_I('n_procs', 'MPI ranks') if foam else 0,
        det_points=(v['det_pts'] or None) if foam else None,
        refine_zones=([(*z[:-1], int(round(z[-1])))
                       for z in v['zones']] if foam else []),
        charge_refine=(v['charge_refine']
                       if foam and not amr_on else 'global'),
        amr_levels=amr_levels,
        amr_estimator=(v['amr_estimator'] if amr_on
                       else 'Lohner'),
        amr_refine=(_F('amr_refine', 'AMR refine threshold')
                    if amr_on else 0.4),
        amr_unrefine=(_F('amr_unrefine', 'AMR unrefine threshold')
                      if amr_on else 0.2),
        amr_interval=(_I('amr_interval', 'AMR refine interval')
                      if amr_on else 2),
        amr_buffer=(_I('amr_buffer', 'AMR buffer layers')
                    if amr_on else 2),
        amr_max_cells=(_I('amr_max_cells', 'AMR max cells')
                       if amr_on else 0),
        amr_display_level=(
            None if not amr_on
            or v['amr_display_level'].strip() in ('', 'auto')
            else _I('amr_display_level', 'AMR display level')),
    )
    if dim == 2:
        return Case2D(geometry=v['geometry'],
                      center=(_F('cx', 'burst x'),
                              _F('cy', 'burst y')),
                      profile_file=v['profile_out'] or None,
                      **common), errs, bad
    slice_raw = v['slice_pos'].strip()
    return Case3D(Lz=_F('Lz', 'Lz'),
                  center=(_F('cx', 'burst x'),
                          _F('cy', 'burst y'),
                          _F('cz', 'burst z')),
                  charge_resolution=(v['charge_res']
                                     if not foam else 'resolve'),
                  slice_axis=v['slice_axis'],
                  slice_pos=(_F('slice_pos', 'slice position')
                             if slice_raw else None),
                  charges=((v['extra_charges'] or None)
                           if foam else None),
                  **common), errs, bad


def fields_from_case(case, dim=None):
    """The form's values for `case`, IN THE ORDER the form sets them.

    The order is part of the contract: setting a field fires the form's
    hooks, and the 2D `geometry` hook writes `cx` and `bc_x_lo`, which
    the case's own values then overwrite. `dim` is the form's dimension
    (default: the case's)."""
    if dim is None:
        dim = case.dim
    if dim == 0:
        return hd13_fields_from_case(case)
    out = {}
    if dim == 1:
        out['radius_m'] = f'{case.radius_m:g}'
        out['charge'] = f'{case.charge_kg:g}'
        out['material'] = getattr(case, 'material', 'TNT')
        out['activation'] = getattr(case, 'activation', 'linear')
        out['afterburn'] = getattr(case, 'afterburn', 'none') or 'none'
        out['cell'] = f'{case.cell_size_m:g}'
        out['eos'] = case.eos
        out['order'] = order_label(case)
        out['cfl'] = f'{case.cfl:g}'
        out['bc_outer'] = normalize_bc(
            getattr(case, 'bc_outer', 'terminate'))
        out['n_snapshots'] = str(case.n_snapshots)
        out['t_end'] = f'{getattr(case, "t_end", 0.0):g}'
        out['gauges'] = [(g,) for g in case.gauge_radii]
        out['gauge_file'] = case.gauge_file or ''
        out['profile_out'] = case.profile_file or ''
        return out
    if dim == 2:
        out['geometry'] = case.geometry
    out['Lx'] = f'{case.Lx:g}'
    out['Ly'] = f'{case.Ly:g}'
    if dim == 3:
        out['Lz'] = f'{case.Lz:g}'
    out['cell'] = f'{case.cell_size_m:g}'
    out['init_mode'] = case.init_mode
    out['charge'] = f'{case.charge:g}' if case.charge is not None else ''
    out['t_end'] = f'{getattr(case, "t_end", 0.0):g}'
    if dim == 3:
        out['charge_res'] = getattr(case, 'charge_resolution', 'resolve')
        out['slice_axis'] = getattr(case, 'slice_axis', 'y')
        sp = getattr(case, 'slice_pos', None)
        out['slice_pos'] = '' if sp is None else f'{sp:g}'
    out['profile_in'] = case.profile_file_in or ''
    out['cx'] = f'{case.center[0]:g}'
    out['cy'] = f'{case.center[1]:g}'
    if dim == 3 and len(case.center) > 2:
        out['cz'] = f'{case.center[2]:g}'
    out['material'] = getattr(case, 'material', 'TNT')
    out['activation'] = getattr(case, 'activation', 'linear')
    out['afterburn'] = getattr(case, 'afterburn', 'none') or 'none'
    out['charge_refine'] = getattr(case, 'charge_refine', 'global')
    out['amr_levels'] = str(int(getattr(case, 'amr_levels', 0) or 0))
    out['amr_estimator'] = (getattr(case, 'amr_estimator', 'Lohner')
                            or 'Lohner')
    for key, default in (('amr_refine', 0.4), ('amr_unrefine', 0.2),
                         ('amr_interval', 2), ('amr_buffer', 2),
                         ('amr_max_cells', 0)):
        out[key] = f'{getattr(case, key, default):g}'
    dl = getattr(case, 'amr_display_level', None)
    out['amr_display_level'] = 'auto' if dl is None else str(int(dl))
    out['n_procs'] = str(getattr(case, 'n_procs', 0))
    out['eos'] = case.eos
    out['order'] = order_label(case)
    out['cfl'] = f'{case.cfl:g}'
    out['n_snapshots'] = str(case.n_snapshots)
    # a case built in code (not loaded through case_from_dict) can
    # still carry the pre-T50 spellings; the combos only offer the
    # three canonical ones
    for side, val in normalize_bcs(dict(case.bcs)).items():
        out[f'bc_{side}'] = val
    out['gauges'] = case.gauges
    out['obstacles'] = case.obstacles
    out['zones'] = getattr(case, 'refine_zones', None) or []
    if dim == 3:
        out['extra_charges'] = getattr(case, 'charges', None) or []
    out['det_pts'] = getattr(case, 'det_points', None) or []
    out['gauge_file'] = case.gauge_file or ''
    out['anim_file'] = case.anim_file or ''
    out['anim_mesh'] = bool(getattr(case, 'anim_mesh', False))
    scale = anim_scale_from_label(getattr(case, 'anim_scale', 'run'))
    out['anim_scale'] = ANIM_SCALE_LABELS[scale]
    clim = getattr(case, 'anim_clim', None)
    if clim:
        out['anim_clim_min'] = f'{float(clim[0]):g}'
        out['anim_clim_max'] = f'{float(clim[1]):g}'
    out['record'] = case.record_frames > 0
    # T51 trigger rows (2D/3D - 1D has no trigger card since T63); 3D
    # has no remap file, so no trigger_file row
    n = getattr(case, 'trigger_gauge', None)
    out['trigger_gauge'] = '' if n in (None, 0) else str(int(n))
    out['trigger_action'] = (getattr(case, 'trigger_action', 'terminate')
                             or 'terminate')
    if dim < 3:
        out['trigger_file'] = getattr(case, 'trigger_file', None) or ''
    if dim == 2:
        out['profile_out'] = case.profile_file or ''
    return out
