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

from .constants import (JWL_TNT, MIN_EXP_CELLS,
                        CELLS_2D_WARN, CELLS_2D_MAX,
                        CELLS_WARN, CELLS_REFUSE,
                        FOAM_CELLS_WARN, FOAM_CELLS_REFUSE)

SCHEMA = 'blastlab-case'
VERSION = 2     # v2: n_procs, activation, charges, det_points (foam)


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
        err("Profile initialization is not supported by the blastFoam "
            "backend yet")
    if getattr(case, 'charge_resolution', 'resolve') == 'smear':
        note("Charge resolution 'smear' is ignored by the blastFoam "
             "backend (the grid is refined to resolve the charge)")
    note("EOS setting is ignored by blastFoam (material JWL products "
         "+ ideal-gas air)")
    activation = getattr(case, 'activation', 'linear')
    if activation not in ('linear', 'none'):
        err(f"Unknown activation model '{activation}' "
            f"(use 'linear' or 'none')")
    elif activation == 'none':
        note("Instant detonation ('none'): the whole charge reacts "
             "at t = 0")
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


def validate_case(case):
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
        if dx > r_exp / MIN_EXP_CELLS:
            dx = r_exp / MIN_EXP_CELLS
            note(f"Cell size will be refined to {dx:.5f} m "
                 f"({MIN_EXP_CELLS} cells inside the charge)")
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
        elif dx > r_exp / MIN_EXP_CELLS:
            dx = r_exp / MIN_EXP_CELLS
            refined = True
            note(f"Cell size will be refined to {dx:.5f} m "
                 f"({MIN_EXP_CELLS} cells across the charge radius)")

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
            if dx > r_i / MIN_EXP_CELLS:
                dx = r_i / MIN_EXP_CELLS
                refined = True
                note(f"Cell size will be refined to {dx:.5f} m "
                     f"({MIN_EXP_CELLS} cells across the smallest "
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
        elif not os.path.exists(case.profile_file_in):
            err(f"Profile file not found: {case.profile_file_in}")
        if case.dim == 2 and init == 'profile1d' \
                and case.geometry != 'axisymmetric':
            err("1D profile remap is only valid in axisymmetric mode")

    rep.effective_dx = dx
    if case.dim == 2:
        n = int(case.Lx / dx) * int(case.Ly / dx)
        if foam:
            # blastFoam solves in WSL; Python only ingests written
            # frames, so the cap reflects wall time/disk, not RAM
            if n > FOAM_CELLS_REFUSE:
                err(f"~{n:,} cells exceeds the blastFoam cap of "
                    f"{FOAM_CELLS_REFUSE:,}")
            elif n > FOAM_CELLS_WARN:
                warn(f"Large grid: ~{n:,} cells - expect a long run "
                     f"and GBs of case files on the WSL disk")
        elif n > CELLS_2D_MAX:
            err(f"~{n:,} cells exceeds the 2D cap of {CELLS_2D_MAX:,}")
        elif n > CELLS_2D_WARN:
            warn(f"Large grid: ~{n:,} cells - expect a long run")
    else:
        n = int(case.Lx / dx) * int(case.Ly / dx) * int(case.Lz / dx)
        if foam:
            if n > FOAM_CELLS_REFUSE:
                err(f"~{n:,} cells exceeds the blastFoam cap of "
                    f"{FOAM_CELLS_REFUSE:,}")
            elif n > FOAM_CELLS_WARN:
                warn(f"Large grid: ~{n:,} cells - expect hours of wall "
                     f"time and GBs of case files on the WSL disk")
        elif n > CELLS_REFUSE:
            err(f"~{n:,} cells exceeds the 3D cap of {CELLS_REFUSE:,}"
                + (" - set charge resolution to 'smear' to keep your "
                   "cell size" if refined else ""))
        elif n > CELLS_WARN:
            warn(f"Large grid: ~{n:,} cells - expect a long run and GBs of RAM")
    rep.n_cells = n

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
