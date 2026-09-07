"""Case definitions: everything needed to run a simulation, serializable
to JSON case files (used by the GUI, the chain workflow, and scripting).

`validate_case` is the GUI's pre-flight check: it mirrors the guard rails
the solvers enforce at run start (which remain authoritative) so problems
surface while editing a form instead of at launch.
"""

import json
import os
from dataclasses import dataclass, field, asdict

import numpy as np

from .constants import (JWL_TNT, MIN_EXP_CELLS, FOAM_EXP_CELLS,
                        CELLS_2D_WARN, CELLS_2D_MAX,
                        CELLS_WARN, CELLS_REFUSE,
                        FOAM_CELLS_WARN, FOAM_CELLS_REFUSE)

SCHEMA = 'blastlab-case'
VERSION = 5     # v2: n_procs, activation, charges, det_points (foam)
                # v3: refine_zones, charge_refine (foam local refinement)
                # v4: afterburn (foam Miller afterburn model)
                # v5: amr_* (foam dynamic mesh refinement, N16)


@dataclass
class Case1D:
    dim = 1
    radius_m: float = 10.0
    charge_kg: float = 1.0
    cell_size_m: float = 0.001
    eos: str = 'idealGas'
    cfl: float = 0.5
    n_snapshots: int = 5
    gauge_radii: list = field(default_factory=list)
    gauge_file: str = 'gauges.txt'
    profile_file: str = None          # save final field for 2D/3D remap
    solver: str = 'native'            # 'native' | 'blastfoam' (WSL)
    material: str = 'TNT'             # blastFoam charge material
    activation: str = 'linear'        # blastFoam detonation model:
                                      # 'linear' (burn at vDet) |
                                      # 'none' (instant)
    afterburn: str = 'none'           # blastFoam afterburn model:
                                      # 'none' | 'miller' (products
                                      # burning with atmospheric oxygen)
    #: blastProbes adjustLocations: True snaps each gauge onto the
    #: centre of the cell holding it at t = 0 (N16-a/T40)
    probe_adjust: bool = True
    n_procs: int = 0                  # blastFoam MPI ranks (0 = auto;
                                      # 1D always runs serial)


@dataclass
class Case2D:
    dim = 2
    geometry: str = 'axisymmetric'    # 'planar' | 'axisymmetric'
    Lx: float = 10.0
    Ly: float = 10.0
    cell_size_m: float = 0.025
    init_mode: str = 'charge'         # 'charge' | 'profile1d'
    charge: float = 1.0               # kg (axisym) / kg per m (planar)
    profile_file_in: str = None       # 1D profile to remap
    center: tuple = (0.0, 5.0)        # (x0, y0); axisym forces x0 = 0
    eos: str = 'idealGas'
    bcs: dict = field(default_factory=lambda: dict(
        x_lo='wall', x_hi='open', y_lo='wall', y_hi='open'))
    obstacles: list = field(default_factory=list)   # (x0,x1,y0,y1)
    refine_zones: list = field(default_factory=list)  # blastFoam local
                                      # refinement: (x0,x1,y0,y1,level),
                                      # level l = base cell / 2**l
    charge_refine: str = 'global'     # 'global': refine the whole grid to
                                      # resolve the charge (native rule) |
                                      # 'zone': keep the base cell, add
                                      # automatic nested zones (blastFoam)
    amr_levels: int = 0               # blastFoam dynamic refinement
                                      # (adaptiveFvMesh): levels below the
                                      # base cell the mesh may reach, 0 = off
    amr_estimator: str = 'densityGradient'   # 'densityGradient' | 'Lohner'
    amr_refine: float = 0.4           # lowerRefineLevel (refine above);
                                      # 0.4/0.2 measured on the 2D e2e:
                                      # 1.2x faster than uniform at ~3.6 %
                                      # gauge error (the tutorials' 0.1/0.1
                                      # refines nearly everything)
    amr_unrefine: float = 0.2         # unrefineLevel (unrefine below)
    amr_interval: int = 2             # refineInterval [steps]
    amr_buffer: int = 2               # nBufferLayers
    amr_max_cells: int = 0            # maxCells, 0 = FOAM_CELLS_WARN
    amr_display_level: int = None     # display grid level (None = deepest
                                      # level under the display cap)
    cfl: float = 0.4
    n_snapshots: int = 6
    gauges: list = field(default_factory=list)      # (x, y)
    gauge_file: str = 'gauges_2d.txt'
    anim_file: str = None
    record_frames: int = 150
    live: bool = True
    profile_file: str = None          # save .npz for 3D remap (axisym only)
    solver: str = 'native'            # 'native' | 'blastfoam' (WSL)
    material: str = 'TNT'             # blastFoam charge material
    activation: str = 'linear'        # blastFoam detonation model:
                                      # 'linear' (burn at vDet) |
                                      # 'none' (instant)
    afterburn: str = 'none'           # blastFoam afterburn model:
                                      # 'none' | 'miller' (products
                                      # burning with atmospheric oxygen)
    #: blastProbes adjustLocations: True snaps each gauge onto the
    #: centre of the cell holding it at t = 0 (N16-a/T40)
    probe_adjust: bool = True
    n_procs: int = 0                  # blastFoam MPI ranks (0 = auto)
    det_points: list = None           # blastFoam: detonation points
                                      # [(x, y), ...] (axisym: x = 0);
                                      # None = charge centre


@dataclass
class Case3D:
    dim = 3
    Lx: float = 10.0
    Ly: float = 10.0
    Lz: float = 10.0
    cell_size_m: float = 0.1
    init_mode: str = 'charge'         # 'charge' | 'profile1d' | 'profile2d'
    charge: float = 1.0
    charge_resolution: str = 'resolve'  # 'resolve' (refine grid to charge)
                                        # | 'smear' (keep cell size,
                                        #   energy-conserving source ball)
    profile_file_in: str = None
    center: tuple = (5.0, 5.0, 5.0)   # z ignored for profile2d
    eos: str = 'idealGas'
    bcs: dict = field(default_factory=lambda: dict(
        x_lo='open', x_hi='open', y_lo='open', y_hi='open',
        z_lo='wall', z_hi='open'))
    obstacles: list = field(default_factory=list)   # (x0,x1,y0,y1,z0,z1)
    refine_zones: list = field(default_factory=list)  # blastFoam local
                                      # refinement: (x0,x1,y0,y1,z0,z1,level)
    charge_refine: str = 'global'     # 'global' | 'zone' (see Case2D)
    amr_levels: int = 0               # blastFoam dynamic refinement
                                      # (adaptiveFvMesh): levels below the
                                      # base cell the mesh may reach, 0 = off
    amr_estimator: str = 'densityGradient'   # 'densityGradient' | 'Lohner'
    amr_refine: float = 0.4           # lowerRefineLevel (refine above);
                                      # 0.4/0.2 measured on the 2D e2e:
                                      # 1.2x faster than uniform at ~3.6 %
                                      # gauge error (the tutorials' 0.1/0.1
                                      # refines nearly everything)
    amr_unrefine: float = 0.2         # unrefineLevel (unrefine below)
    amr_interval: int = 2             # refineInterval [steps]
    amr_buffer: int = 2               # nBufferLayers
    amr_max_cells: int = 0            # maxCells, 0 = FOAM_CELLS_WARN
    amr_display_level: int = None     # display grid level (None = deepest
                                      # level under the display cap)
    cfl: float = 0.30
    t_end: float = 0.0                # stop at t0 + t_end [s]; 0 = auto
    slice_axis: str = 'y'             # live-slice normal: 'x' | 'y' | 'z'
    slice_pos: float = None           # slice position [m]; None = burst point
    n_snapshots: int = 6
    gauges: list = field(default_factory=list)      # (x, y, z)
    gauge_file: str = 'gauges_3d.txt'
    anim_file: str = None
    record_frames: int = 150
    live: bool = True
    solver: str = 'native'            # 'native' | 'blastfoam' (WSL)
    material: str = 'TNT'             # blastFoam charge material
    activation: str = 'linear'        # blastFoam detonation model:
                                      # 'linear' (burn at vDet) |
                                      # 'none' (instant)
    afterburn: str = 'none'           # blastFoam afterburn model:
                                      # 'none' | 'miller' (products
                                      # burning with atmospheric oxygen)
    #: blastProbes adjustLocations: True snaps each gauge onto the
    #: centre of the cell holding it at t = 0 (N16-a/T40)
    probe_adjust: bool = True
    n_procs: int = 0                  # blastFoam MPI ranks (0 = auto)
    charges: list = None              # blastFoam: ADDITIONAL charges
                                      # [(x, y, z, mass_kg), ...] on top
                                      # of the primary charge/center
    det_points: list = None           # blastFoam: detonation points
                                      # [(x, y, z), ...]; None = every
                                      # charge centre


_CASE_TYPES = {1: Case1D, 2: Case2D, 3: Case3D}


def case_to_dict(case):
    d = asdict(case)
    d['schema'] = SCHEMA
    d['version'] = VERSION
    d['dim'] = case.dim
    return d


def case_from_dict(d):
    d = dict(d)
    if d.pop('schema', SCHEMA) != SCHEMA:
        raise ValueError("Not a blastlab case file")
    if d.pop('version', VERSION) > VERSION:
        raise ValueError("Case file from a newer blastlab version")
    dim = d.pop('dim')
    cls = _CASE_TYPES[int(dim)]
    fields = {f for f in cls.__dataclass_fields__}
    unknown = set(d) - fields
    if unknown:
        raise ValueError(f"Unknown case keys: {sorted(unknown)}")
    case = cls(**d)
    if hasattr(case, 'center') and case.center is not None:
        case.center = tuple(case.center)
    if hasattr(case, 'obstacles'):
        case.obstacles = [tuple(o) for o in case.obstacles]
    if getattr(case, 'refine_zones', None):
        case.refine_zones = [(*[float(v) for v in z[:-1]],
                              int(round(float(z[-1]))))
                             for z in case.refine_zones]
    for fld in ('amr_levels', 'amr_interval', 'amr_buffer', 'amr_max_cells'):
        if hasattr(case, fld):
            setattr(case, fld, int(getattr(case, fld) or 0))
    if getattr(case, 'amr_display_level', None) is not None:
        case.amr_display_level = int(case.amr_display_level)
    if hasattr(case, 'gauges'):
        case.gauges = [tuple(g) if isinstance(g, (list, tuple)) else g
                       for g in case.gauges]
    for fld in ('charges', 'det_points'):
        if getattr(case, fld, None):
            setattr(case, fld, [tuple(v) for v in getattr(case, fld)])
    return case


def save_case(case, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(case_to_dict(case), f, indent=2)


def load_case(path):
    with open(path, encoding='utf-8') as f:
        case = case_from_dict(json.load(f))
    # profile paths are stored as given; resolve relative to the case file
    base = os.path.dirname(os.path.abspath(path))
    if getattr(case, 'profile_file_in', None):
        if not os.path.isabs(case.profile_file_in):
            case.profile_file_in = os.path.join(base, case.profile_file_in)
    return case


# ── Pre-flight validation (mirror of the solvers' run-time guard rails) ─────

@dataclass
class ValidationReport:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    effective_dx: float = None
    r_exp: float = None
    n_cells: int = None
    lmax: int = 0                    # local refinement levels (foam)
    dx_fine: float = None            # finest cell of a refined mesh
    n_fine: int = None               # display-grid cells of a refined run
    amr_levels: int = 0              # dynamic AMR levels (foam, N16)
    display_level: int = None        # AMR: level of the display grid
    charge_cells: int = None         # foam: cells setFields will mark
    charge_mass_frac: float = None   # foam: set mass / requested (N5)

    @property
    def ok(self):
        return not self.errors


def _charge_radius(case, rho0=None):
    rho0 = JWL_TNT['rho0'] if rho0 is None else rho0
    if case.dim == 2 and case.geometry == 'planar':
        return np.sqrt(case.charge / (np.pi * rho0))
    return (3.0 * case.charge / (4.0 * np.pi * rho0)) ** (1.0 / 3.0)


def _validate_solver(case, rep):
    """Solver-backend gating. Returns the unreacted charge density used
    to size r_exp (material-aware for blastfoam), or None on a fatal
    backend error."""
    err, note = rep.errors.append, rep.notes.append
    solver = getattr(case, 'solver', 'native')
    material = getattr(case, 'material', 'TNT')
    n_procs = getattr(case, 'n_procs', 0)
    if n_procs < 0:
        err("MPI ranks must be >= 0 (0 = auto)")
    if solver == 'native':
        if material != 'TNT':
            note("Charge material is ignored by the native solver "
                 "(TNT only)")
        if n_procs > 1:
            note("MPI ranks are ignored by the native solver")
        if getattr(case, 'charges', None) or \
                getattr(case, 'det_points', None):
            err("Multiple charges / detonation points require the "
                "blastFoam solver")
        if getattr(case, 'afterburn', 'none') not in ('none', None):
            err("The afterburn model requires the blastFoam solver")
        if getattr(case, 'amr_levels', 0):
            err("Dynamic mesh refinement (AMR) requires the blastFoam "
                "solver")
        return JWL_TNT['rho0']
    if solver != 'blastfoam':
        err(f"Unknown solver backend '{solver}'")
        return None
    from ..solvers.foam.materials import MATERIALS
    if material not in MATERIALS:
        err(f"Unknown charge material '{material}'")
        return None
    from ..solvers.foam import backend as foam_backend
    if case.dim not in foam_backend.IMPLEMENTED:
        err(f"The blastFoam backend for {case.dim}D cases is not "
            f"implemented yet")
    if getattr(case, 'obstacles', None):
        note("Obstacles: cells inside each box are carved out of "
             "the mesh (rigid walls)")
    if getattr(case, 'init_mode', 'charge') != 'charge':
        # N7: the stage's state is written straight into 0/ as
        # nonuniform internalFields, in the mesh's cell order. That
        # order is only known ahead of time on the uniform mesh, so a
        # profile stage cannot also refine locally in this version.
        if case.dim == 1:
            err("blastFoam 1D stages cannot start from a profile "
                "(a 1D profile IS the 1D state - run the next stage "
                "in 2D or 3D)")
        if int(getattr(case, 'amr_levels', 0) or 0):
            err("A profile-initialised blastFoam stage cannot use "
                "dynamic AMR yet - the remapped state is written on "
                "the uniform base mesh")
        if (getattr(case, 'refine_zones', None)
                or getattr(case, 'charge_refine', 'global') == 'zone'):
            err("A profile-initialised blastFoam stage cannot use "
                "refinement zones yet - the remapped state is written "
                "on the uniform base mesh")
    if getattr(case, 'charge_resolution', 'resolve') == 'smear':
        note("Charge resolution 'smear' is ignored by the blastFoam "
             "backend (the grid is refined to resolve the charge)")
    if getattr(case, 'eos', 'idealGas') != 'idealGas':
        # only worth saying when someone actually picked a non-default
        # EOS (the GUI hides the row in blastFoam mode, T34)
        note("EOS setting is ignored by blastFoam (material JWL products "
             "+ ideal-gas air)")
    activation = getattr(case, 'activation', 'linear')
    if activation not in ('linear', 'none'):
        err(f"Unknown activation model '{activation}' "
            f"(use 'linear' or 'none')")
    elif activation == 'none':
        note("Instant detonation ('none'): the whole charge reacts "
             "at t = 0")
    afterburn = getattr(case, 'afterburn', 'none') or 'none'
    if afterburn not in ('none', 'miller'):
        err(f"Unknown afterburn model '{afterburn}' "
            f"(use 'none' or 'miller')")
    elif afterburn == 'miller':
        from ..solvers.foam.materials import AFTERBURN
        ab = AFTERBURN.get(material)
        if ab is None:
            err(f"No afterburn parameters for '{material}'")
        else:
            note(f"Afterburn (Miller): up to {ab.Q0/1e6:g} MJ/kg released "
                 f"as the products burn with atmospheric oxygen - "
                 f"calibrated against Kingery-Bulmash, see ROADMAP N3")
    if n_procs > 1:
        if case.dim == 1:
            note("1D cases always run serial (MPI ranks ignored)")
        else:
            note(f"Parallel run: {n_procs} MPI ranks")
    from ..solvers.foam import env as foam_env
    st, detail = foam_env.status()
    if st == 'fail':
        err(f"blastFoam/WSL not available: {detail}")
    elif st == 'checking':
        note("Checking WSL blastFoam availability...")
    elif st == 'ok':
        note(detail)
    else:
        note("WSL blastFoam availability will be verified at run start")
    return MATERIALS[material].rho0


def validate_case(case, pending_inputs=False):
    """Full pre-run report for one case.

    `pending_inputs=True` means the case's profile input is produced by
    an earlier stage of the same chain run, so its absence on disk right
    now is expected rather than an error (everything else is still
    checked). Only the chain panel passes it."""
    rep = ValidationReport()
    err, warn, note = rep.errors.append, rep.warnings.append, rep.notes.append

    dx = case.cell_size_m
    if dx <= 0:
        err("Cell size must be > 0")
        return rep

    rho0 = _validate_solver(case, rep)
    if rho0 is None:
        return rep
    foam = getattr(case, 'solver', 'native') == 'blastfoam'
    # blastFoam wants more cells across the charge than the native
    # solvers: sphericalMassToCell deposits only the staircase mass
    # (N5/T39). Native stays byte-pinned at MIN_EXP_CELLS.
    n_exp = FOAM_EXP_CELLS if foam else MIN_EXP_CELLS
    cref = getattr(case, 'charge_refine', 'global')
    zones = list(getattr(case, 'refine_zones', None) or [])
    amr = int(getattr(case, 'amr_levels', 0) or 0) if foam else 0

    if case.dim == 1:
        if case.charge_kg <= 0:
            err("Charge must be > 0")
        if case.radius_m <= 0:
            err("Domain radius must be > 0")
        if rep.errors:
            return rep
        r_exp = (3.0 * case.charge_kg
                 / (4.0 * np.pi * rho0)) ** (1.0 / 3.0)
        rep.r_exp = r_exp
        if r_exp >= case.radius_m:
            err(f"Explosive radius {r_exp:.3f} m exceeds domain radius")
        if dx > r_exp / n_exp:
            dx = r_exp / n_exp
            note(f"Cell size will be refined to {dx:.5f} m "
                 f"({n_exp} cells inside the charge)")
        rep.effective_dx = dx
        rep.n_cells = int(case.radius_m / dx)
        return rep

    # 2D / 3D shared pieces
    dims = ((case.Lx, case.Ly) if case.dim == 2
            else (case.Lx, case.Ly, case.Lz))
    if any(L <= 0 for L in dims):
        err("Domain extents must be > 0")
        return rep
    if getattr(case, 't_end', 0.0) < 0:
        err("End time must be >= 0 (0 = automatic stop condition)")
    if case.dim == 3:
        s_ax = getattr(case, 'slice_axis', 'y')
        if s_ax not in ('x', 'y', 'z'):
            err("Live slice normal must be 'x', 'y' or 'z'")
        else:
            s_pos = getattr(case, 'slice_pos', None)
            L_ax = dict(x=case.Lx, y=case.Ly, z=case.Lz)[s_ax]
            if s_pos is not None and not 0 <= s_pos <= L_ax:
                warn(f"Live slice position {s_pos:g} m is outside the "
                     f"domain (0..{L_ax:g} m) - the nearest cell is used")

    init = getattr(case, 'init_mode', 'charge')
    refined = False
    if init == 'charge':
        if case.charge is None or case.charge <= 0:
            err("Charge must be > 0")
            return rep
        if getattr(case, 'charge_resolution', 'resolve') \
                not in ('resolve', 'smear'):
            err("Charge resolution must be 'resolve' or 'smear'")
            return rep
        r_exp = _charge_radius(case, rho0)
        rep.r_exp = r_exp
        # 3D 'smear' keeps dx and enlarges the source ball instead of
        # refining; use the ball radius for the geometry checks below.
        # (blastfoam always resolves - smear is native-only.)
        smeared = (case.dim == 3 and not foam
                   and getattr(case, 'charge_resolution',
                               'resolve') == 'smear'
                   and dx > r_exp / MIN_EXP_CELLS)
        r_exp = max(r_exp, 2.0 * dx) if smeared else r_exp
        center = case.center
        # containment vs open boundaries; walls allow surface bursts
        if case.dim == 2:
            x0, y0 = (0.0 if case.geometry == 'axisymmetric'
                      else center[0]), center[1]
            overhangs = [(r_exp - (case.Lx - x0), 'x_hi'),
                         (r_exp - y0, 'y_lo'),
                         (r_exp - (case.Ly - y0), 'y_hi')]
            if case.geometry == 'planar':
                overhangs.append((r_exp - x0, 'x_lo'))
            inside = 0 <= x0 <= case.Lx and 0 <= y0 <= case.Ly
        else:
            x0, y0, z0 = center
            overhangs = [(r_exp - x0, 'x_lo'), (r_exp - (case.Lx - x0), 'x_hi'),
                         (r_exp - y0, 'y_lo'), (r_exp - (case.Ly - y0), 'y_hi'),
                         (r_exp - z0, 'z_lo'), (r_exp - (case.Lz - z0), 'z_hi')]
            inside = (0 <= x0 <= case.Lx and 0 <= y0 <= case.Ly
                      and 0 <= z0 <= case.Lz)
        if not inside:
            err("Charge centre is outside the domain")
        for over, side in overhangs:
            if over <= 0:
                continue
            if case.bcs.get(side) == 'wall':
                note(f"Charge is truncated by the {side} wall (surface burst)")
            else:
                err(f"Charge (r_exp = {r_exp:.4f} m) pokes through the "
                    f"open '{side}' boundary")
        # obstacle overlap
        for box in case.obstacles:
            if case.dim == 2:
                ox0, ox1, oy0, oy1 = box
                cx = min(max(x0, ox0), ox1)
                cy = min(max(y0, oy0), oy1)
                d2 = (cx - x0)**2 + (cy - y0)**2
            else:
                ox0, ox1, oy0, oy1, oz0, oz1 = box
                cx = min(max(x0, ox0), ox1)
                cy = min(max(y0, oy0), oy1)
                cz = min(max(z0, oz0), oz1)
                d2 = (cx - x0)**2 + (cy - y0)**2 + (cz - z0)**2
            if d2 < r_exp**2:
                err(f"Charge overlaps obstacle {box}")
        if smeared:
            note(f"Charge under-resolved at dx = {dx:g} m - its mass & "
                 f"energy will be smeared into a {r_exp:.3f} m source ball")
        elif dx > r_exp / n_exp and not (foam and cref == 'zone') \
                and not amr:
            dx = r_exp / n_exp
            refined = True
            note(f"Cell size will be refined to {dx:.5f} m "
                 f"({n_exp} cells across the charge radius)")

        # blastFoam extra charges (3D only) + detonation points
        extras = getattr(case, 'charges', None) or []
        if extras and case.dim != 3:
            err("Additional charges are only supported for 3D "
                "blastFoam cases")
            extras = []
        spheres = [(x0, y0, (z0 if case.dim == 3 else 0.0), r_exp)]
        for ch in extras:
            if len(ch) != 4:
                err(f"Extra charge {tuple(ch)}: need (x, y, z, mass)")
                continue
            ex, ey, ez, mass = ch
            if mass is None or mass <= 0:
                err(f"Extra charge at ({ex:g}, {ey:g}, {ez:g}): "
                    f"mass must be > 0")
                continue
            r_i = (3.0 * mass / (4.0 * np.pi * rho0)) ** (1.0 / 3.0)
            if not (0 <= ex <= case.Lx and 0 <= ey <= case.Ly
                    and 0 <= ez <= case.Lz):
                err(f"Extra charge centre ({ex:g}, {ey:g}, {ez:g}) is "
                    f"outside the domain")
                continue
            for over, side in ((r_i - ex, 'x_lo'),
                               (r_i - (case.Lx - ex), 'x_hi'),
                               (r_i - ey, 'y_lo'),
                               (r_i - (case.Ly - ey), 'y_hi'),
                               (r_i - ez, 'z_lo'),
                               (r_i - (case.Lz - ez), 'z_hi')):
                if over <= 0:
                    continue
                if case.bcs.get(side) == 'wall':
                    note(f"Extra charge at ({ex:g}, {ey:g}, {ez:g}) is "
                         f"truncated by the {side} wall")
                else:
                    err(f"Extra charge (r_exp = {r_i:.4f} m) at "
                        f"({ex:g}, {ey:g}, {ez:g}) pokes through the "
                        f"open '{side}' boundary")
            for (px, py, pz, pr) in spheres:
                d = np.sqrt((ex - px) ** 2 + (ey - py) ** 2
                            + (ez - pz) ** 2)
                if d < r_i + pr:
                    err(f"Extra charge at ({ex:g}, {ey:g}, {ez:g}) "
                        f"overlaps another charge")
            spheres.append((ex, ey, ez, r_i))
            if dx > r_i / n_exp and not amr:
                dx = r_i / n_exp
                refined = True
                note(f"Cell size will be refined to {dx:.5f} m "
                     f"({n_exp} cells across the smallest "
                     f"charge radius)")
        for dp in getattr(case, 'det_points', None) or []:
            pt = tuple(dp) + ((0.0,) if case.dim == 2 else ())
            if len(pt) != 3:
                err(f"Detonation point {tuple(dp)}: need "
                    + ("(x, y)" if case.dim == 2 else "(x, y, z)"))
                continue
            px, py, pz = pt
            if case.dim == 2:
                px, py, pz = ((0.0 if case.geometry == 'axisymmetric'
                               else px), py, 0.0)
                inside = any(np.sqrt((px - sx) ** 2 + (py - sy) ** 2)
                             <= sr for sx, sy, _sz, sr in spheres)
            else:
                inside = any(np.sqrt((px - sx) ** 2 + (py - sy) ** 2
                                     + (pz - sz) ** 2) <= sr
                             for sx, sy, sz, sr in spheres)
            if not inside:
                err(f"Detonation point {tuple(dp)} lies outside every "
                    f"charge")
    else:
        if not case.profile_file_in:
            err("A profile file is required for remap initialization")
        elif not (pending_inputs or os.path.exists(case.profile_file_in)):
            err(f"Profile file not found: {case.profile_file_in}")
        if case.dim == 2 and init == 'profile1d' \
                and case.geometry != 'axisymmetric':
            err("1D profile remap is only valid in axisymmetric mode")
        # the remapped charge is still placed at `center`, so an out-of-
        # domain centre is just as invalid as for a fresh charge (a chain
        # stage fed a bad burst point used to reach the backend and die)
        cc = ((0.0, case.center[1])
              if case.dim == 2 and case.geometry == 'axisymmetric'
              else tuple(case.center)[:case.dim])
        if any(not (0 <= float(v) <= float(L)) for v, L in zip(cc, dims)):
            err("Charge centre is outside the domain")

    # blastFoam local refinement: zones and/or an automatic charge zone
    plan = None
    if amr and (zones or cref == 'zone'):
        err("Dynamic AMR and static refinement zones are mutually "
            "exclusive - clear the zones and set charge refinement to "
            "'global' (the charge is refined at t = 0 by the AMR itself)")
    elif amr:
        if init == 'charge' and not rep.errors:
            from .refine import plan_levels, validate_amr
            try:
                plan = plan_levels(case, rho0)
            except ValueError as exc:
                err(str(exc))
                return rep
            aerr, awarn, anote = validate_amr(case, plan, rho0)
            rep.errors.extend(aerr)
            rep.warnings.extend(awarn)
            rep.notes.extend(anote)
            if aerr:
                plan = None
            else:
                rep.amr_levels = plan.amr
                rep.display_level = plan.display_level
                rep.lmax = plan.lmax
                rep.dx_fine = plan.dx_base / 2 ** plan.amr
                rep.n_fine = plan.n_fine
                if getattr(case, 'n_procs', 0) > 1:
                    note("AMR runs serially in this version (MPI ranks "
                         "ignored)")
    elif case.dim >= 2 and (zones or cref == 'zone'):
        if not foam:
            err("Local mesh refinement (refinement zones / charge "
                "refinement 'zone') requires the blastFoam solver")
        elif cref not in ('global', 'zone'):
            err(f"Unknown charge refinement mode '{cref}' (use 'global' "
                f"or 'zone')")
        elif init == 'charge' and not rep.errors:
            from .refine import plan_levels, validate_zones
            try:
                plan = plan_levels(case, rho0)
            except ValueError as exc:
                err(str(exc))
            else:
                zerr, zwarn = validate_zones(case, plan)
                rep.errors.extend(zerr)
                rep.warnings.extend(zwarn)
                if zerr:
                    plan = None
                else:
                    if plan.refined:
                        note(f"Local refinement: {plan.lmax} level(s), "
                             f"finest cell {plan.dx_fine:.5g} m, "
                             f"~{plan.n_pred:,} mesh cells; results are "
                             f"resampled to a {plan.n_fine:,}-cell display "
                             f"grid")
                        rep.lmax = plan.lmax
                        rep.dx_fine = plan.dx_fine
                        rep.n_fine = plan.n_fine
                    if cref == 'zone':
                        note(f"Charge resolved by automatic level-"
                             f"{plan.auto_level} zones (base cell kept at "
                             f"{plan.dx_base:.5g} m)" if plan.auto_level
                             else "The base cell already resolves the "
                                  "charge - no automatic zone needed")

    def scale_hint():
        """Why a modest cell size turned into a huge grid: the charge, not
        the cell-size field, sets the spacing, and it applies to the WHOLE
        uniform domain. Without this the user only saw 'cell size will be
        refined' and a cell count two orders of magnitude off what they
        asked for."""
        if not refined or not rep.r_exp:
            return ""
        return (f" - resolving the {2 * rep.r_exp:.3g} m charge forces a "
                f"{dx:.4g} m cell across the whole {max(dims):g} m domain; "
                f"use a smaller domain, a larger charge"
                + (", or charge resolution 'smear'"
                   if case.dim == 3 and not foam else "")
                + (", or blastFoam charge refinement 'zone'" if foam else ""))

    # What blastFoam will actually deposit (N5/T39): setFields marks
    # whole cells, so the charge is a staircase whose mass is only
    # approximately the requested one. Reported for foam cases with a
    # direct charge, at the finest spacing the charge will see.
    if foam and init == 'charge' and rep.r_exp and not rep.errors:
        dx_charge = dx
        if plan is not None:
            dx_charge = (plan.dx_base / 2 ** plan.amr if plan.amr
                         else plan.dx_fine)
        try:
            from .refine import set_mass_fraction
            cen = ((0.0 if case.geometry == 'axisymmetric' else case.center[0],
                    case.center[1]) if case.dim == 2
                   else tuple(float(v) for v in case.center[:3]))
            n_set, frac = set_mass_fraction(
                case.dim, getattr(case, 'geometry', ''), dx_charge,
                rep.r_exp, cen, dims)
        except (ValueError, ZeroDivisionError, IndexError):
            n_set = 0
        if case.dim >= 2 and n_set:
            rep.charge_cells = n_set
            rep.charge_mass_frac = frac
            note(f"Charge cells: {n_set:,} at {dx_charge:.5g} m -> "
                 f"~{frac:.2f} of the {case.charge:g} kg set by "
                 f"blastFoam (whole cells are marked; "
                 f"{n_exp} cells across the radius)")

    rep.effective_dx = dx
    if plan is not None and plan.amr:
        # AMR: the mesh grows during the run up to maxCells, so that is
        # the number the blastFoam caps apply to (t = 0 is the base grid)
        n_max = (int(getattr(case, 'amr_max_cells', 0) or 0)
                 or FOAM_CELLS_WARN)
        if n_max > FOAM_CELLS_REFUSE:
            err(f"AMR max cells {n_max:,} exceeds the blastFoam cap of "
                f"{FOAM_CELLS_REFUSE:,}")
        elif n_max > FOAM_CELLS_WARN:
            warn(f"AMR may grow the mesh to {n_max:,} cells - expect a "
                 f"long run and GBs of case files on the WSL disk")
        # every written time keeps its own mesh (cell centres + levels), so
        # an AMR run's disk cost is much larger than a static one's
        n_w = max(int(getattr(case, 'n_snapshots', 6) or 6), 1)
        mb = plan.n_pred * 60 / 1e6            # ~60 B per cell per write
        if mb * n_w > 200:
            note(f"AMR keeps a mesh per written time: roughly "
                 f"{mb:.0f} MB per write, about {mb * n_w / 1000:.1f} GB "
                 f"for this run on the WSL disk - clean old runs with "
                 f"'Foam runs...' or --clean-foam-runs")
    if case.dim == 2:
        n = int(case.Lx / dx) * int(case.Ly / dx)
        if plan is not None and (plan.refined or plan.amr):
            n = plan.n_pred
        if plan is not None and plan.amr:
            pass
        elif foam:
            # blastFoam solves in WSL; Python only ingests written
            # frames, so the cap reflects wall time/disk, not RAM
            if n > FOAM_CELLS_REFUSE:
                err(f"~{n:,} cells exceeds the blastFoam cap of "
                    f"{FOAM_CELLS_REFUSE:,}" + scale_hint())
            elif n > FOAM_CELLS_WARN:
                warn(f"Large grid: ~{n:,} cells - expect a long run "
                     f"and GBs of case files on the WSL disk")
        elif n > CELLS_2D_MAX:
            err(f"~{n:,} cells exceeds the 2D cap of {CELLS_2D_MAX:,}"
                + scale_hint())
        elif n > CELLS_2D_WARN:
            warn(f"Large grid: ~{n:,} cells - expect a long run")
    else:
        n = int(case.Lx / dx) * int(case.Ly / dx) * int(case.Lz / dx)
        if plan is not None and (plan.refined or plan.amr):
            n = plan.n_pred
        if plan is not None and plan.amr:
            pass
        elif foam:
            if n > FOAM_CELLS_REFUSE:
                err(f"~{n:,} cells exceeds the blastFoam cap of "
                    f"{FOAM_CELLS_REFUSE:,}" + scale_hint())
            elif n > FOAM_CELLS_WARN:
                warn(f"Large grid: ~{n:,} cells - expect hours of wall "
                     f"time and GBs of case files on the WSL disk")
        elif n > CELLS_REFUSE:
            err(f"~{n:,} cells exceeds the 3D cap of {CELLS_REFUSE:,}"
                + scale_hint())
        elif n > CELLS_WARN:
            warn(f"Large grid: ~{n:,} cells - expect a long run and GBs of RAM")
    rep.n_cells = n
    if plan is not None and plan.refined:
        # Python holds the resampled fine grid per ingested write, so the
        # display grid is capped like a native run's grid
        cap = CELLS_2D_MAX if case.dim == 2 else CELLS_REFUSE
        cap_warn = CELLS_2D_WARN if case.dim == 2 else CELLS_WARN
        if plan.n_fine > cap:
            err(f"Refined results are resampled to a {plan.n_fine:,}-cell "
                f"display grid (finest cell {plan.dx_fine:.5g} m), above "
                f"the {cap:,} cap - "
                + ("lower the AMR display level or use a coarser base"
                   if plan.amr else "use fewer levels or a coarser base"))
        elif plan.n_fine > cap_warn:
            warn(f"Refined results are resampled to a {plan.n_fine:,}-cell "
                 f"display grid - expect GBs of RAM for frames and "
                 f"snapshots")

    # gauges / obstacles sanity
    for g in getattr(case, 'gauges', []):
        pt = g if isinstance(g, (list, tuple)) else (g,)
        limits = dims
        if any(not (0 <= v <= L) for v, L in zip(pt, limits)):
            warn(f"Gauge {tuple(pt)} outside domain - will be dropped")
    for box in case.obstacles:
        lo, hi = box[0::2], box[1::2]
        if any(a >= b for a, b in zip(lo, hi)) or \
           any(b > L or a < 0 for a, b, L in zip(lo, hi, dims)):
            err(f"Obstacle {box} is not a valid in-domain box")

    if case.dim == 2 and case.profile_file and case.geometry != 'axisymmetric':
        err("2D profile export (for 3D remap) requires axisymmetric geometry")
    return rep
