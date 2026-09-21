"""What the Setup form contains, as data.

One descriptor per input row: its key in the form, its caption, how to
parse it, its default, which solver it belongs to and which sub-group
toggles it. `cards(dim)` returns the cards of one dimension in build
order. The engine in `fieldform.py` turns this into widgets; the
reactive behaviour that cannot be declared (the axisymmetric relabelling,
the AMR sub-group) stays imperative in `case_form.py`.

Toolkit-free on purpose: this module is the single place to look up what
a field is called, what it defaults to and who it applies to, and it can
be read by a test without a QApplication.

The defaults here are the FORM's, which are deliberately not always the
dataclass defaults - see the note on the boundary kinds below (UX-01).
"""

from dataclasses import dataclass, field

from ..core.bc import BC_KINDS
from ..core.case import TRIGGER_ACTIONS
from ..core.constants import ANIM_SCALE_LABELS
from ..core.refine import AMR_ESTIMATORS, MAX_AMR_LEVEL
from ..solvers.foam.materials import MATERIAL_NAMES

#: caption wrap width and the minimum width reserved for the input
#: column, so a value stays readable at the 1100x720 minimum window
LABEL_WRAP = 132
INPUT_MIN = 146


@dataclass(frozen=True)
class F:
    """One labelled input row.

    kind:   'text' | 'float' | 'int' | 'choice' | 'bool' | 'file' | 'points'
    scope:  None (both solvers) | 'native' | 'blastfoam'
    group:  a sub-group whose visibility a hook toggles ('amr', 'cref')
    dyn:    the caption is rewritten at runtime (axisymmetric r/z)
    cols:   'points' only - the column captions; the arity is len(cols)
    """

    name: str
    label: str
    kind: str = 'text'
    default: object = ''
    values: tuple = ()
    scope: str = None
    group: str = None
    dyn: bool = False
    cols: tuple = ()
    rows: int = 4                 # 'points': visible rows
    file: dict = None             # 'file': dialog title + filters


@dataclass(frozen=True)
class CardSpec:
    """A titled card in one of the two columns. `grid` > 1 lays the rows
    out as that many label+input pairs per line (the boundary grid)."""

    title: str
    col: int
    rows: tuple = ()
    scope: str = None
    grid: int = 1
    field_rows: int = 0           # 'points' cards: stretch this card


# ── shared row groups ────────────────────────────────────────────────────
def _numerics(dim):
    out = [
        F('eos', 'EOS', 'choice', 'idealGas',
          values=('idealGas', 'JWL'), scope='native'),
        # T47/N10: opt-in MUSCL reconstruction, native solvers only
        F('order', 'Order', 'choice', '1 (Godunov)',
          values=('1 (Godunov)', '2 (MUSCL)'), scope='native'),
        F('activation', 'Detonation', 'choice', 'linear',
          values=('linear', 'programmedIgnition', 'none'),
          scope='blastfoam'),
        F('afterburn', 'Afterburn', 'choice', 'none',
          values=('none', 'miller'), scope='blastfoam'),
    ]
    if dim > 1:
        # 'global' = refine the whole grid to resolve the charge; 'zone'
        # keeps the base cell and nests refinement zones around it. Goes
        # away while dynamic AMR is on, hence the group tag.
        out.append(F('charge_refine', 'Charge refinement', 'choice',
                     'global', values=('global', 'zone'),
                     scope='blastfoam', group='cref'))
    out.append(F('n_snapshots', 'Snapshots', 'int', 5 if dim == 1 else 6))
    out.append(F('cfl', 'CFL', 'float', {1: 0.5, 2: 0.4, 3: 0.30}[dim]))
    if dim > 1:
        # blastFoam MPI ranks; 1D always runs serial, so no field
        out.append(F('n_procs', 'MPI ranks (0 = auto)', 'int', 0,
                     scope='blastfoam'))
    # T52: every dimension can set an end time; whichever comes first
    # wins - a terminate boundary, the trigger gauge, or this
    out.append(F('t_end', 'End time [s] (0 = auto)', 'float', 0.0))
    if dim == 3:
        out.append(F('slice_axis', 'Live slice normal', 'choice', 'y',
                     values=('x', 'y', 'z')))
        out.append(F('slice_pos', 'Slice position [m]\n(blank = burst)',
                     'float'))
    return tuple(out)


def _amr_card():
    """The dynamic-refinement card (blastFoam adaptiveFvMesh, N16). Every
    row but the level count belongs to the 'amr' group, so they exist
    only while AMR is on."""
    levels = tuple(str(i) for i in range(MAX_AMR_LEVEL + 1))
    return CardSpec('Dynamic refinement (AMR)', col=0, scope='blastfoam',
                    rows=(
        F('amr_levels', 'AMR levels (0 = off)', 'choice', '0',
          values=levels),
        F('amr_estimator', 'Error estimator', 'choice', 'Lohner',
          values=tuple(AMR_ESTIMATORS), group='amr'),
        F('amr_refine', 'Refine above', 'float', 0.4, group='amr'),
        F('amr_unrefine', 'Unrefine below', 'float', 0.2, group='amr'),
        F('amr_interval', 'Refine every [steps]', 'int', 2, group='amr'),
        F('amr_buffer', 'Buffer layers', 'int', 2, group='amr'),
        F('amr_max_cells', 'Max cells (0 = default)', 'int', 0,
          group='amr'),
        F('amr_display_level', 'Display level', 'choice', 'auto',
          values=('auto',) + levels, group='amr'),
    ))


#: UX-01: the FORM defaults give a new user one terminate side (x_hi -
#: the radial outer boundary in axisym, matching the 1D default), so the
#: very first screen validates clean instead of greeting them with the
#: red "No terminate boundary" warning about its own defaults. The
#: Case2D/3D dataclass defaults stay all-transmit: dozens of tests and
#: programmatic cases rely on them, and a case built in code earns the
#: warning honestly.
BC_DEFAULTS = {
    2: dict(x_lo='reflect', x_hi='terminate',
            y_lo='reflect', y_hi='transmit'),
    3: dict(x_lo='transmit', x_hi='terminate', y_lo='transmit',
            y_hi='transmit', z_lo='reflect', z_hi='transmit'),
}


def _boundaries(dim):
    if dim == 1:
        # T60: the apex is the symmetry centre, so there is one boundary
        return CardSpec('Boundaries', col=0, rows=(
            F('bc_outer', 'Outer boundary (r = R)', 'choice', 'terminate',
              values=tuple(BC_KINDS)),))
    sides = (('x_lo', 'x_hi', 'y_lo', 'y_hi') if dim == 2 else
             ('x_lo', 'x_hi', 'y_lo', 'y_hi', 'z_lo', 'z_hi'))
    d = BC_DEFAULTS[dim]
    return CardSpec('Boundaries', col=0, grid=2, rows=tuple(
        F(f'bc_{s}', s, 'choice', d[s], values=tuple(BC_KINDS))
        for s in sides))


def _anim_ext():
    """write_animation picks the writer from the extension: .mp4 when
    ffmpeg is on PATH, .gif otherwise. Default to what this machine can
    actually write, as the CLI already does."""
    try:
        from matplotlib import animation
        return '.mp4' if animation.FFMpegWriter.isAvailable() else '.gif'
    except Exception:
        return '.gif'


def _outputs(dim):
    out = [F('gauge_file', 'Gauge TSV', 'text',
             f'gauges_{dim}d.txt' if dim > 1 else 'gauges.txt')]
    if dim > 1:
        out.append(F('anim_file', 'Animation (.gif / .mp4)', 'text',
                     f'blast_{dim}d_animation{_anim_ext()}'))
        # the video's colour range: one for the whole video by default,
        # so the colour bar means the same thing in every frame
        out.append(F('anim_scale', 'Video colours', 'choice',
                     ANIM_SCALE_LABELS['run'],
                     values=tuple(ANIM_SCALE_LABELS.values())))
        out.append(F('anim_clim_min', 'Video min [kPa]', 'float', 0.0,
                     group='aclim'))
        out.append(F('anim_clim_max', 'Video max [kPa]', 'float', 500.0,
                     group='aclim'))
        out.append(F('record', 'Record replay frames', 'bool', True))
        out.append(F('anim_mesh', 'Mesh overlay in the animation', 'bool',
                     False))
    if dim == 1:
        out.append(F('profile_out', 'Profile out (.txt)', 'text',
                     'blast_profile.txt'))
    elif dim == 2:
        out.append(F('profile_out', 'Profile out (.npz)', 'text'))
    return CardSpec('Outputs', col=1, rows=tuple(out))


def _trigger(dim):
    """T51: one gauge that ends the run and/or writes the remap file the
    moment the wave reaches it. 3D has no remap format, so only the
    terminating actions are offered there. 1D has no trigger at all
    (T63): its outer boundary already ends the run and the profile it
    writes at the end IS the hand-off."""
    acts = ([a for a in TRIGGER_ACTIONS if 'remap' not in a] if dim == 3
            else list(TRIGGER_ACTIONS))
    rows = [F('trigger_gauge', 'Gauge number\n(blank = off)', 'int'),
            F('trigger_action', 'On arrival', 'choice', 'terminate',
              values=tuple(acts))]
    if dim < 3:
        rows.append(F('trigger_file', 'Remap file\n(blank = profile out)',
                      'text'))
    return CardSpec('Trigger gauge', col=1, rows=tuple(rows))


# ── HD 1.3: the 0-D chamber (HD1-11c) ────────────────────────────────────
# A deflagration assessment has no mesh, no boundaries and no solver
# choice, so it shares no card with the blast forms. It is `dim = 0`
# because that is how core/assessment.DeflagrationCase labels itself and
# how a host already branches.
#
# Units here are the ones an engineer writes on paper - kPa, MPa, mm,
# mm/s - and case_form converts. The blast forms get away with SI because
# a charge really is in kilograms; a web thickness in metres reads as a
# typo.
#
# The override rows are blank by default and mean "use the table value".
# They exist because the shipped propellant rows are class-typical
# literature and a real assessment is expected to replace some of them -
# that was the owner's "generic-parametric" decision. Per-field control
# of which overrides are MEASURED lives in the case file; the form offers
# the one checkbox, because in practice a user either has data behind
# their numbers or does not.
def _hd13_cards():
    from ..core.fuels import PROPELLANT_NAMES
    from ..core.scenario import GEOMETRIES, KINDS
    from ..core.assessment import CONFINEMENTS
    from ..core.sdof import SUPPORTS

    return [
        CardSpec('Material', col=0, rows=(
            F('propellant', 'Propellant', 'choice', 'double_base',
              values=tuple(PROPELLANT_NAMES)),
            F('ov_n', 'Vieille n\n(blank = table)', 'float'),
            F('ov_a', 'Vieille a\n(blank = table)', 'float'),
            F('ov_r_atm', 'Burn rate at 1 atm\n[mm/s]', 'float'),
            F('ov_web', 'Web [mm]', 'float'),
            F('ov_p_ext', 'Extinction limit [MPa]\n(blank = not modelled)',
              'float'),
            F('ov_secondary', 'Secondary heat\nin air [MJ/kg]', 'float'),
            F('measured', 'The overrides above are measured', 'bool',
              False))),
        CardSpec('Charge and chamber', col=0, rows=(
            F('charge_kg', 'Charge [kg]', 'float', 5.0),
            F('volume_m3', 'Chamber volume [m3]', 'float', 1.0),
            F('vent_area', 'Vent area [m2]\n(0 = closed)', 'float', 0.02),
            F('cd', 'Discharge coefficient', 'float', 0.8),
            F('p_ign', 'Igniter pressure [MPa]\n(0 = automatic)', 'float',
              0.0),
            # A room, not a test vessel: the air already in it carries a
            # large share of the pressure at magazine loading density.
            # `simulate` defaults this to 0 to protect its own analytic
            # limit; a case is never evacuated unless someone says so.
            F('p0_chamber', 'Air in the room [MPa]\n(0 = evacuated)',
              'float', 0.101325),
            F('confinement', 'Assess', 'choice', 'both',
              values=tuple(CONFINEMENTS)))),
        CardSpec('Ignition', col=0, rows=(
            F('scenario_kind', 'How it catches', 'choice', 'flame_spread',
              values=tuple(KINDS)),
            # 80, not 10: the cohort count is a discretisation of the
            # flame spread, and a slow fire cut into ten steps reports
            # the size of one step as its peak. See
            # deflagration._COHORT_TOL.
            F('n_cohorts', 'Cohorts', 'int', 80),
            F('spread_time', 'Time to light it all [s]', 'float', 30.0),
            F('spread_geometry', 'Spread through a', 'choice', 'area',
              values=tuple(GEOMETRIES)))),
        CardSpec('Run', col=1, rows=(
            F('t_end', 'End time [s]', 'float', 60.0),
            F('n_out', 'Samples', 'int', 1000))),
        CardSpec('Heat', col=1, rows=(
            F('h_c', 'Wall heat transfer\n[W/m2K] (0 = skip)', 'float',
              200.0),
            F('wall_area', 'Wall area [m2]', 'float', 6.0),
            F('t_wall', 'Wall temperature [K]', 'float', 300.0))),
        CardSpec('Radiation standoffs [m]', col=1, field_rows=1, rows=(
            F('standoffs', 'Radiation standoffs [m]', 'points',
              cols=('R',), rows=3),)),
        CardSpec('Structure', col=1, rows=(
            F('span_m', 'Span [m]\n(0 = skip)', 'float', 3.0),
            F('mass_per_area', 'Mass [kg/m2]', 'float', 480.0),
            F('ru_kpa', 'Ultimate resistance [kPa]', 'float', 400.0),
            F('ke_mpa_m', 'Elastic stiffness [MPa/m]', 'float', 30.0),
            F('support', 'Supports', 'choice', 'simple',
              values=tuple(SUPPORTS)),
            F('rot_limit', 'Collapse rotation [deg]', 'float', 12.0))),
        CardSpec('Outputs', col=1, rows=(
            F('name', 'Run name', 'text', ''),
            F('report_file', 'Report file', 'file', 'hd13_report.html',
              file=dict(title='Write the HD 1.3 report',
                        filter='HTML (*.html);;All files (*.*)')))),
    ]


# ── the cards of one dimension, in build order ───────────────────────────
def cards(dim):
    dim = int(dim)
    if dim not in (0, 1, 2, 3):
        raise ValueError(f'dim must be 0, 1, 2 or 3, not {dim!r}')
    if dim == 0:
        return _hd13_cards()
    out = []

    # Domain -------------------------------------------------------------
    if dim == 1:
        out.append(CardSpec('Domain', col=0, rows=(
            F('radius_m', 'Domain radius [m]', 'float', 10.0),
            F('cell', 'Cell size [m]', 'float', 0.001))))
    else:
        # Both forms start from a case that actually validates on a 4 GB
        # WSL VM (QA-14 set the invariant; T48's memory-derived caps
        # re-sized it): 2D is 1 kg in a 4 m box, 3D is 25 kg in a 1.5 m
        # box - clean, no warnings, in both solver modes.
        L0 = 4.0 if dim == 2 else 1.5
        rows = []
        if dim == 2:
            rows.append(F('geometry', 'Geometry', 'choice', 'axisymmetric',
                          values=('axisymmetric', 'planar')))
        rows.append(F('Lx', 'Lx [m]', 'float', L0, dyn=(dim == 2)))
        rows.append(F('Ly', 'Ly [m]', 'float', L0, dyn=(dim == 2)))
        if dim == 3:
            rows.append(F('Lz', 'Lz [m]', 'float', L0))
        rows.append(F('cell', 'Cell size [m]', 'float', 0.025))
        out.append(CardSpec('Domain', col=0, rows=tuple(rows)))

    # Charge / initialization --------------------------------------------
    if dim == 1:
        out.append(CardSpec('Charge', col=0, rows=(
            F('charge', 'Charge [kg TNT]', 'float', 1.0),
            # N11/T46: the native solvers share the JWL material table,
            # so this row shows in both solver modes
            F('material', 'Material', 'choice', 'TNT',
              values=tuple(MATERIAL_NAMES)))))
    else:
        modes = (('charge', 'profile1d') if dim == 2
                 else ('charge', 'profile1d', 'profile2d'))
        c0 = 2.0 if dim == 2 else 0.75          # centre of L0
        rows = [F('init_mode', 'Initialize from', 'choice', 'charge',
                  values=modes),
                # UX-02: the unit follows the geometry (kg for axisym/3D,
                # kg per metre of depth for planar) via the hook
                F('charge', 'Charge [kg TNT]', 'float',
                  1.0 if dim == 2 else 25.0, dyn=(dim == 2)),
                F('material', 'Material', 'choice', 'TNT',
                  values=tuple(MATERIAL_NAMES))]
        if dim == 3:
            # blastFoam always resolves the charge (smear is ignored with
            # a note), so the choice is a native row
            rows.append(F('charge_res', 'Charge resolution', 'choice',
                          'resolve', values=('resolve', 'smear'),
                          scope='native'))
        rows.append(F('profile_in', 'Profile file', 'file', file=dict(
            title='Open profile file',
            filter='Profiles (*.txt *.npz);;All files (*.*)')))
        rows.append(F('cx', 'Burst x [m]', 'float',
                      0.0 if dim == 2 else c0, dyn=(dim == 2)))
        rows.append(F('cy', 'Burst y [m]', 'float', c0, dyn=(dim == 2)))
        if dim == 3:
            rows.append(F('cz', 'Burst z [m]', 'float', c0))
        out.append(CardSpec('Initialization', col=0, rows=tuple(rows)))

    # Numerics, AMR, boundaries ------------------------------------------
    out.append(CardSpec('Numerics', col=0, rows=_numerics(dim)))
    if dim > 1:
        out.append(_amr_card())
    out.append(_boundaries(dim))

    # right column -------------------------------------------------------
    if dim == 1:
        out.append(CardSpec('Gauge radii [m]', col=1, field_rows=1, rows=(
            F('gauges', 'Gauge radii [m]', 'points', cols=('r',)),)))
    else:
        gcols = ('x', 'y') if dim == 2 else ('x', 'y', 'z')
        ocols = (('x0', 'x1', 'y0', 'y1') if dim == 2
                 else ('x0', 'x1', 'y0', 'y1', 'z0', 'z1'))
        out.append(CardSpec('Gauges [m]', col=1, field_rows=1, rows=(
            F('gauges', 'Gauges [m]', 'points', cols=gcols),)))
        out.append(CardSpec('Obstacles [m]', col=1, field_rows=1, rows=(
            F('obstacles', 'Obstacles [m]', 'points', cols=ocols),)))
        # blastFoam local refinement zones: a box + a level (1 = base
        # cell / 2, 2 = / 4, ...); the whole card is hidden on native
        out.append(CardSpec('Refinement zones [m, level]', col=1,
                            scope='blastfoam', rows=(
            F('zones', 'Refinement zones', 'points',
              cols=ocols + ('level',), rows=3),)))
        if dim == 3:
            out.append(CardSpec('Extra charges [m, kg]', col=1,
                                scope='blastfoam', rows=(
                F('extra_charges', 'Extra charges', 'points',
                  cols=('x', 'y', 'z', 'kg'), rows=3),)))
        out.append(CardSpec('Detonation points [m]', col=1,
                            scope='blastfoam', rows=(
            F('det_pts', 'Detonation points', 'points', cols=gcols,
              rows=3),)))

    out.append(_outputs(dim))
    if dim > 1:
        out.append(_trigger(dim))
    return tuple(out)


# ── lookups ──────────────────────────────────────────────────────────────
def fields(dim):
    """Every F of a dimension, in build order."""
    return tuple(f for card in cards(dim) for f in card.rows)


def by_name(dim):
    return {f.name: f for f in fields(dim)}


#: captions the axisymmetric hook swaps in (2D only). The planar form
#: keeps the spec's own labels.
AXISYM_LABELS = {
    'Lx': 'Radius R [m]', 'Ly': 'Height Z [m]',
    'cx': 'Burst r [m]', 'cy': 'Burst z [m]',
    'charge': 'Charge [kg TNT]',
}
#: UX-02: planar charges are per metre of depth
PLANAR_LABELS = {'charge': 'Charge [kg TNT/m]'}
