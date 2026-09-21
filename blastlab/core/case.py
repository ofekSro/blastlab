"""Case definitions: everything needed to run a simulation, serializable
to JSON case files (used by the GUI, the chain workflow, and scripting).

`validate_case` is the GUI's pre-flight check: it mirrors the guard rails
the solvers enforce at run start (which remain authoritative) so problems
surface while editing a form instead of at launch.
"""

import json
import math
import os
from dataclasses import dataclass, field, asdict

import numpy as np

from .bc import BC_KINDS, normalize_bc, normalize_bcs
from .constants import (ANIM_SCALES, JWL_TNT, MIN_EXP_CELLS,
                        FOAM_EXP_CELLS,
                        CELLS_2D_WARN, CELLS_2D_MAX,
                        CELLS_WARN, CELLS_REFUSE,
                        FOAM_CELLS_WARN, FOAM_CELLS_REFUSE,
                        FOAM_VM_GB_ASSUMED,
                        BYTES_PER_CELL)
from . import hardware as _hardware

#: T51 trigger-gauge actions (2D/3D only - T63 removed the 1D trigger).
#: 'remap' writes the remap file at the arrival instant and lets the run
#: continue; the other two end it.
TRIGGER_ACTIONS = ('terminate', 'remap', 'remap+terminate')

SCHEMA = 'blastlab-case'
VERSION = 13    # v2: n_procs, activation, charges, det_points (foam)
                # v3: refine_zones, charge_refine (foam local refinement)
                # v4: afterburn (foam Miller afterburn model)
                # v5: amr_* (foam dynamic mesh refinement, N16)
                # v6: anim_mesh (cell-edge overlay in the run's
                #     exported animation)
                # v7: boundary kinds transmit|reflect|terminate
                #     (T50; 'open'/'wall' still read and mapped)
                # v8: t_end on 1D/2D as well (T52)
                # v9: trigger_gauge / trigger_action / trigger_file (T51)
                # v10: bc_outer on Case1D (T60)
                # v11: the 1D trigger gauge is gone (T63); the keys are
                #      dropped from older 1D files rather than refused
                # v12: anim_scale / anim_clim (the exported animation's
                #      colour range: one for the whole video by default,
                #      per frame as before, or a range you pin)
                # v13: adaptive_write. The chain has always pinned it to
                #      False for reproducibility (N2-13), but as an
                #      ad-hoc attribute, which asdict() does not see - so
                #      the stage JSONs it saved "for reproducibility"
                #      lost exactly the flag that made them reproducible


@dataclass
class Case1D:
    dim = 1
    radius_m: float = 10.0
    charge_kg: float = 1.0
    cell_size_m: float = 0.001
    eos: str = 'idealGas'
    #: T60: the far end of the spherical sector - the same three kinds
    #: the 2D/3D sides take. 'terminate' is what 1D always did.
    bc_outer: str = 'terminate'
    cfl: float = 0.5
    t_end: float = 0.0                # stop at t_end [s]; 0 = auto (T52)
    n_snapshots: int = 5
    gauge_radii: list = field(default_factory=list)
    gauge_file: str = 'gauges.txt'
    profile_file: str = None          # save final field for 2D/3D remap
    #: T63: 1D has no trigger gauge. The whole 1D run is the hand-off
    #: (`profile_file` is written at the end) and `bc_outer='terminate'`
    #: already stops it at the sector's end, so a per-gauge trigger only
    #: ever duplicated those two - in blastFoam 1D it did nothing at all.
    solver: str = 'native'            # 'native' | 'blastfoam' (WSL)
    material: str = 'TNT'             # blastFoam charge material
    activation: str = 'linear'
    #: optional, aligned with det_points (N5-12): per-point ignition
    #: delay [s] and initiation radius [m]. None = all zero, blastFoam's
    #: own defaults. Guide 5.6.1: valid for any activation model.
    det_delays: list = None
    det_radii: list = None        # blastFoam detonation model:
                                      # 'linear' (burn at vDet) |
                                      # 'none' (instant)
    afterburn: str = 'none'           # blastFoam afterburn model:
                                      # 'none' | 'miller' (products
                                      # burning with atmospheric oxygen)
    #: native reconstruction order (T47/N10): 1 = the pinned Godunov
    #: path, 2 = opt-in limited MUSCL (native solvers only)
    order: int = 1
    #: blastProbes `adjustLocations`. A no-op for every gauge we write:
    #: it relocates only probes found in NO cell (blastProbes.C:218),
    #: and ours are interior. T40 measured it - arrival moves 0.15 pp
    #: with it off - and DONE.md records the old reading as REFUTED.
    probe_adjust: bool = True
    #: B23/N2-13: False pins writeInterval for the whole run. The
    #: adaptive controller rewrites it mid-run from what the ingest has
    #: kept up with - wall clock - so the set of write times differs
    #: between identical runs. The Chain tab pins it on every stage.
    adaptive_write: bool = True
    n_procs: int = 0                  # blastFoam MPI ranks (0 = auto;
                                      # 1D always runs serial)


@dataclass
class Case2D:
    dim = 2
    geometry: str = 'axisymmetric'    # 'planar' | 'axisymmetric'
    # 4 m, not 10: resolving the default 1 kg charge with blastFoam's 8
    # cells across the radius (T39) makes a 10 m domain 2.3M cells,
    # which is ~6 GB inside the solver - more than a default 4 GB WSL VM
    # holds (T48 measured ~2.65 KB/cell). 4 m is 368k cells: valid and
    # warning-free out of the box on the smallest supported machine.
    Lx: float = 4.0
    Ly: float = 4.0
    cell_size_m: float = 0.025
    init_mode: str = 'charge'         # 'charge' | 'profile1d'
    charge: float = 1.0               # kg (axisym) / kg per m (planar)
    profile_file_in: str = None       # 1D profile to remap
    center: tuple = (0.0, 2.0)        # (x0, y0); axisym forces x0 = 0
    eos: str = 'idealGas'
    #: T50: 'transmit' (wave leaves, run carries on) | 'reflect' (wall)
    #: | 'terminate' (wave leaves AND ends the run - the pre-T50 'open')
    bcs: dict = field(default_factory=lambda: dict(
        x_lo='reflect', x_hi='transmit',
        y_lo='reflect', y_hi='transmit'))
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
    amr_estimator: str = 'Lohner'     # 'Lohner' | 'densityGradient'.
                                      # Default flipped 2026-09-20 (P1-6,
                                      # owner decision): densityGradient
                                      # holds the near-axis charge crater
                                      # refined until wedge cells drain to
                                      # vacuum -> SIGFPE (axisym); Lohner
                                      # (on p) ran the same case clean.
                                      # An explicit choice is honoured.
    amr_refine: float = 0.2           # lowerRefineLevel (refine above);
                                      # RE-TUNED 2026-09-10. 0.4/0.2 was
                                      # chosen for ~3.6 % gauge error, but
                                      # T39 (5 -> 8 cells across the charge
                                      # radius) moved the case underneath
                                      # it and the same sweep now measures
                                      # -11.8 %. Re-running that sweep:
                                      #   0.4/0.2  -11.8 %  55 s  17,425
                                      #   0.2/0.1   -3.9 %  54 s  20,224
                                      #   0.1/0.05  -2.9 %  54 s  20,377
                                      # 0.2/0.1 restores the accuracy the
                                      # default was picked for, at no wall
                                      # -time cost (the tutorials' 0.1/0.1
                                      # refines nearly everything)
    amr_unrefine: float = 0.1         # unrefineLevel (unrefine below)
    amr_interval: int = 2             # refineInterval [steps]
    amr_buffer: int = 2               # nBufferLayers
    amr_max_cells: int = 0            # maxCells, 0 = FOAM_CELLS_WARN
    amr_display_level: int = None     # display grid level (None = deepest
                                      # level under the display cap)
    cfl: float = 0.4
    t_end: float = 0.0                # stop at t_end [s]; 0 = auto (T52)
    n_snapshots: int = 6
    gauges: list = field(default_factory=list)      # (x, y)
    gauge_file: str = 'gauges_2d.txt'
    #: T51 trigger gauge: 1-based index into `gauges`, None = off. When
    #: the wave reaches it the run ends and/or the remap file is written
    #: at THAT instant - the chain hand-off that used to be possible
    #: only at the end of a run. 2D/3D only (T63).
    trigger_gauge: int = None
    trigger_action: str = 'terminate'
    trigger_file: str = None
    anim_file: str = None
    anim_mesh: bool = False           # overlay the cell edges on the
                                      # animation written after the run
    #: the animation's overpressure colour range: 'run' pins one range
    #: for the whole video (default), 'frame' rescales every frame,
    #: 'manual' uses anim_clim. See output/animation.SCALES.
    anim_scale: str = 'run'
    anim_clim: tuple = None           # (vmin, vmax) kPa for 'manual'
    record_frames: int = 150
    live: bool = True
    profile_file: str = None          # save .npz for 3D remap (axisym only)
    solver: str = 'native'            # 'native' | 'blastfoam' (WSL)
    material: str = 'TNT'             # blastFoam charge material
    activation: str = 'linear'
    #: optional, aligned with det_points (N5-12): per-point ignition
    #: delay [s] and initiation radius [m]. None = all zero, blastFoam's
    #: own defaults. Guide 5.6.1: valid for any activation model.
    det_delays: list = None
    det_radii: list = None        # blastFoam detonation model:
                                      # 'linear' (burn at vDet) |
                                      # 'none' (instant)
    afterburn: str = 'none'           # blastFoam afterburn model:
                                      # 'none' | 'miller' (products
                                      # burning with atmospheric oxygen)
    #: native reconstruction order (T47/N10): 1 = the pinned Godunov
    #: path, 2 = opt-in limited MUSCL (native solvers only)
    order: int = 1
    #: blastProbes `adjustLocations`. A no-op for every gauge we write:
    #: it relocates only probes found in NO cell (blastProbes.C:218),
    #: and ours are interior. T40 measured it - arrival moves 0.15 pp
    #: with it off - and DONE.md records the old reading as REFUTED.
    probe_adjust: bool = True
    adaptive_write: bool = True       # see Case1D.adaptive_write (B23)
    n_procs: int = 0                  # blastFoam MPI ranks (0 = auto)
    det_points: list = None           # blastFoam: detonation points
                                      # [(x, y), ...] (axisym: x = 0);
                                      # None = charge centre


@dataclass
class Case3D:
    dim = 3
    # P1-1: the same rule the 2D default follows, and the values the GUI's
    # 3D form has opened with since QA-14 - there is one shipped 3D default
    # now, not two. `resolve` forces dx = r_charge / 8 (blastFoam, T39)
    # across the WHOLE domain, so the domain a charge allows is set by the
    # charge: 1 kg in 10 m is 3.5 BILLION cells and is refused on every
    # backend, while 25 kg (r = 0.154 m -> dx = 0.0193 m) in 1.5 m is 474k
    # cells on blastFoam and 116k native - valid and warning-free out of
    # the box on the smallest supported machine. Keeping 1 kg here would
    # have meant a 0.74 m domain, which is not a free-air case at all.
    Lx: float = 1.5
    Ly: float = 1.5
    Lz: float = 1.5
    cell_size_m: float = 0.025
    init_mode: str = 'charge'         # 'charge' | 'profile1d' | 'profile2d'
                                      # | 'chamber' (HD1-3b)
    #: HD1-3b, both falsy by default so every existing golden is
    #: byte-identical. `room` is what `core/room.py:measure` returned -
    #: the ALIGNED geometry, not the numbers someone typed - and
    #: `chamber_state` is `core/vent.py:ChamberState.as_dict()`. The two
    #: must describe the same room: the state's volume is what the 0-D
    #: model ran at, and validation compares it with the cavity the
    #: boxes actually leave.
    room: dict = field(default_factory=dict)
    chamber_state: dict = field(default_factory=dict)
    #: Run at a PRESCRIBED time step instead of a Courant-controlled
    #: one. 0 = adaptive, which is what every real case wants and what
    #: every golden is written against.
    #:
    #: It exists for verification cases that are deliberately QUIESCENT.
    #: blastFoam takes its Courant number from the face fluxes, so a
    #: field that is exactly uniform and exactly at rest has Co = 0 and
    #: `Time::adjustDeltaT` divides by it - measured, a SIGFPE on the
    #: first step of `_e2e_gamma_interface.py`. A real chamber case is
    #: pressurised and gets a flux immediately, so this is not a
    #: limitation anyone else meets.
    fixed_dt: float = 0.0
    charge: float = 25.0
    charge_resolution: str = 'resolve'  # 'resolve' (refine grid to charge)
                                        # | 'smear' (keep cell size,
                                        #   energy-conserving source ball)
    profile_file_in: str = None
    center: tuple = (0.75, 0.75, 0.75)  # z ignored for profile2d
    eos: str = 'idealGas'
    #: see Case2D.bcs
    bcs: dict = field(default_factory=lambda: dict(
        x_lo='transmit', x_hi='transmit', y_lo='transmit',
        y_hi='transmit', z_lo='reflect', z_hi='transmit'))
    obstacles: list = field(default_factory=list)   # (x0,x1,y0,y1,z0,z1)
    refine_zones: list = field(default_factory=list)  # blastFoam local
                                      # refinement: (x0,x1,y0,y1,z0,z1,level)
    charge_refine: str = 'global'     # 'global' | 'zone' (see Case2D)
    amr_levels: int = 0               # blastFoam dynamic refinement
                                      # (adaptiveFvMesh): levels below the
                                      # base cell the mesh may reach, 0 = off
    amr_estimator: str = 'Lohner'     # 'Lohner' | 'densityGradient'.
                                      # Default flipped 2026-09-20 (P1-6,
                                      # owner decision): densityGradient
                                      # holds the near-axis charge crater
                                      # refined until wedge cells drain to
                                      # vacuum -> SIGFPE (axisym); Lohner
                                      # (on p) ran the same case clean.
                                      # An explicit choice is honoured.
    amr_refine: float = 0.2           # lowerRefineLevel (refine above);
                                      # RE-TUNED 2026-09-10. 0.4/0.2 was
                                      # chosen for ~3.6 % gauge error, but
                                      # T39 (5 -> 8 cells across the charge
                                      # radius) moved the case underneath
                                      # it and the same sweep now measures
                                      # -11.8 %. Re-running that sweep:
                                      #   0.4/0.2  -11.8 %  55 s  17,425
                                      #   0.2/0.1   -3.9 %  54 s  20,224
                                      #   0.1/0.05  -2.9 %  54 s  20,377
                                      # 0.2/0.1 restores the accuracy the
                                      # default was picked for, at no wall
                                      # -time cost (the tutorials' 0.1/0.1
                                      # refines nearly everything)
    amr_unrefine: float = 0.1         # unrefineLevel (unrefine below)
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
    #: see Case2D.trigger_gauge ('remap' is refused in 3D)
    trigger_gauge: int = None
    trigger_action: str = 'terminate'
    trigger_file: str = None
    anim_file: str = None
    anim_mesh: bool = False           # overlay the cell edges on the
                                      # animation written after the run
    #: see Case2D.anim_scale
    anim_scale: str = 'run'
    anim_clim: tuple = None           # (vmin, vmax) kPa for 'manual'
    record_frames: int = 150
    live: bool = True
    solver: str = 'native'            # 'native' | 'blastfoam' (WSL)
    material: str = 'TNT'             # blastFoam charge material
    activation: str = 'linear'
    #: optional, aligned with det_points (N5-12): per-point ignition
    #: delay [s] and initiation radius [m]. None = all zero, blastFoam's
    #: own defaults. Guide 5.6.1: valid for any activation model.
    det_delays: list = None
    det_radii: list = None        # blastFoam detonation model:
                                      # 'linear' (burn at vDet) |
                                      # 'none' (instant)
    afterburn: str = 'none'           # blastFoam afterburn model:
                                      # 'none' | 'miller' (products
                                      # burning with atmospheric oxygen)
    #: native reconstruction order (T47/N10): 1 = the pinned Godunov
    #: path, 2 = opt-in limited MUSCL (native solvers only)
    order: int = 1
    #: blastProbes `adjustLocations`. A no-op for every gauge we write:
    #: it relocates only probes found in NO cell (blastProbes.C:218),
    #: and ours are interior. T40 measured it - arrival moves 0.15 pp
    #: with it off - and DONE.md records the old reading as REFUTED.
    probe_adjust: bool = True
    adaptive_write: bool = True       # see Case1D.adaptive_write (B23)
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
    if int(dim) == 1:
        # T63: the 1D trigger gauge was removed. Case files written
        # before that still carry the three keys, and refusing to load
        # them would strand every saved 1D case and run (post-mortem
        # reads case.json) - drop them instead.
        for _k in ('trigger_gauge', 'trigger_action', 'trigger_file'):
            d.pop(_k, None)
    fields = {f for f in cls.__dataclass_fields__}
    unknown = set(d) - fields
    if unknown:
        raise ValueError(f"Unknown case keys: {sorted(unknown)}")
    case = cls(**d)
    if hasattr(case, 'center') and case.center is not None:
        case.center = tuple(case.center)
    if getattr(case, 'bcs', None):
        case.bcs = normalize_bcs(case.bcs)
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
    # JSON has no tuples: the animation colour range comes back a list
    if getattr(case, 'anim_clim', None) is not None:
        case.anim_clim = tuple(float(v) for v in case.anim_clim)
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


def material_rho0(case):
    """rho0 of the case's material under ITS solver - the same lookup
    validate_case performs, exposed so the setup preview can plan with
    it (N2-07: preview_panel used to call plan_levels with NO rho0,
    which defaults to TNT's 1630 - so for any other material the
    preview drew a different mesh than the one validate_case reported
    and the writer built; measured on ANFO: a whole extra refinement
    level and a finest cell 2x too small, while the strip on the same
    screen showed the correct numbers). Returns None when the material
    is unknown to the table - callers then fall back to plan_levels'
    TNT default, and validation is already erroring about the material
    itself. Both solvers read the same table (N11/T46: the native
    solvers take their JWL set from blastFoam's material table), so one
    lookup serves either."""
    material = getattr(case, 'material', 'TNT') or 'TNT'
    try:
        from ..solvers.foam.materials import MATERIALS
        return float(MATERIALS[material].rho0)
    except (KeyError, ImportError, AttributeError):
        return None


def fmt_cells(n):
    """Cell counts for messages: thousands separators while the number is
    readable, scientific once it is not. `cell = 1e-9` on a 4 m domain
    used to print ~15,999,999,992,000,000,001 in the middle of a sentence
    (N2-06); nobody counts twenty digits, '1.6e+19' is the information."""
    n = int(n)
    return f'{n:,}' if n < 10 ** 9 else f'{n:.3g}'


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
    run_plan: object = None          # foam: env.RunPlan (N17/T48)

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
    warn = rep.warnings.append          # P1-4: the uncalibrated afterburn
    solver = getattr(case, 'solver', 'native')
    material = getattr(case, 'material', 'TNT')
    n_procs = getattr(case, 'n_procs', 0)
    if n_procs < 0:
        err("MPI ranks must be >= 0 (0 = auto)")
    # T47/N10: reconstruction order is a native-solver knob
    _order = int(getattr(case, 'order', 1) or 1)
    if _order not in (1, 2):
        err("Reconstruction order must be 1 or 2")
    elif _order == 2:
        if solver == 'blastfoam':
            note("Reconstruction order is a native-solver setting - "
                 "blastFoam uses its own schemes (ignored)")
        else:
            note("Order 2 (MUSCL): sharper fronts at the same grid; "
                 "keep CFL at or below 0.4 (limiter falls back to "
                 "order 1 where a slope would go unphysical)")
    # the exported animation's colour range (1D has no animation)
    if hasattr(case, 'anim_scale'):
        a_scale = getattr(case, 'anim_scale', 'run') or 'run'
        if a_scale not in ANIM_SCALES:
            err(f"Unknown animation colour scale '{a_scale}' "
                f"(use {', '.join(ANIM_SCALES)})")
        elif a_scale == 'manual':
            a_clim = getattr(case, 'anim_clim', None)
            try:
                lo, hi = float(a_clim[0]), float(a_clim[1])
            except (TypeError, ValueError, IndexError):
                lo = hi = None
            if lo is None:
                err("A manual animation colour range needs a minimum "
                    "and a maximum in kPa")
            elif not (np.isfinite(lo) and np.isfinite(hi)):
                err("The animation colour range must be finite")
            elif hi <= lo:
                err(f"The animation colour maximum ({hi:g} kPa) must be "
                    f"above the minimum ({lo:g} kPa)")
        elif a_scale == 'frame':
            note("The animation rescales its colours on every frame, so "
                 "the colour bar means something different in each one "
                 "and the shock will not appear to decay")
    if solver == 'native':
        # N11/T46: the native solvers take their JWL set from the same
        # material table as blastFoam
        from ..solvers.foam.materials import MATERIALS as _MATS
        if material not in _MATS:
            err(f"Unknown charge material '{material}'")
            return None
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
        return _MATS[material].rho0
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
        # N7: the stage's state is written straight into the start time
        # dir as nonuniform internalFields, in the mesh's cell order.
        # That order is only known ahead of time on a mesh blockMesh
        # alone builds - the uniform grid, or an AMR case's base grid
        # (which is the same thing at t0; T70). refineMesh renumbers,
        # so static zones stay out.
        if case.dim == 1:
            err("blastFoam 1D stages cannot start from a profile "
                "(a 1D profile IS the 1D state - run the next stage "
                "in 2D or 3D)")
        # Applies to a chamber case for the same reason it applies to a
        # profile one: the state is written into 0/ in the mesh's cell
        # order, and refineMesh renumbers.
        if (getattr(case, 'refine_zones', None)
                or getattr(case, 'charge_refine', 'global') == 'zone'):
            err("A profile-initialised blastFoam stage cannot use "
                "refinement zones yet - the remapped state is written "
                "on the uniform base mesh")
    if getattr(case, 'init_mode', 'charge') == 'chamber':
        # HD1-3b. A chamber case carries its own state rather than
        # loading one from a file, and the two halves have to agree
        # about which room they describe.
        room = getattr(case, 'room', None) or {}
        cs = getattr(case, 'chamber_state', None) or {}
        if not room:
            err("init_mode 'chamber' needs the room geometry - pass what "
                "core.room.measure() returned, which is the ALIGNED "
                "room and not the numbers that were typed")
        if not cs:
            err("init_mode 'chamber' needs a chamber_state - see "
                "core.vent.handoff()")
        if room and not room.get('ok', True):
            for e in room.get('errors', ()):
                err(f'Room: {e}')
        if room and cs:
            v_mesh = float(room.get('volume') or 0.0)
            v_state = float(cs.get('volume') or 0.0)
            if v_mesh > 0 and v_state > 0 and \
                    abs(v_state / v_mesh - 1.0) > 0.02:
                # NOT a rounding complaint - room.align makes snapping a
                # no-op, so a gap here means the hand-off was computed
                # for a different room than the one about to be meshed,
                # and the pressure written into the cells is wrong by
                # that ratio.
                err(f"The chamber state was computed at "
                    f"{v_state:.4f} m3 but the meshed cavity is "
                    f"{v_mesh:.4f} m3 ({v_state / v_mesh - 1.0:+.1%}). "
                    f"Re-run core.vent.handoff with volume_cfd set to "
                    f"the meshed cavity - it conserves mass and energy, "
                    f"so the pressure follows, but only if it is told "
                    f"the right volume.")
            # Defaults to True when the key is absent, because
            # `simulate` is adiabatic by default: a hand-written case
            # that simply omits the field must not be the quiet way past
            # this warning. Absence of evidence is the adiabatic case.
            if cs.get('adiabatic_source', True):
                warn("The chamber state came from an ADIABATIC 0-D run. "
                     "At a burst pressure the effect of that is NOT in T "
                     "- the pressure is fixed by the trigger, so T is "
                     "nearly set by the composition. It is in WHEN the "
                     "panel bursts and HOW MUCH has burnt by then: "
                     "measured at h_c = 200 on a 20 kg magazine, the "
                     "burst comes 9.5 % later with 12.4 % more mass "
                     "burnt and alpha_expl 10.8 % higher, while T moves "
                     "1.4 %. Set h_c and wall_area on the 0-D run, or "
                     "state that this is the adiabatic bound.")
            if cs.get('first_front_is_artefact'):
                warn("Opened-from-the-start: the first front out of the "
                     "opening is an artefact of initialising a "
                     "pressurised room against ambient. No peak or "
                     "impulse may be read from it - only steady-jet "
                     "quantities after it has passed.")
        if getattr(case, 'charge', None):
            note("Charge is ignored for a chamber case: the gas is "
                 "already made, and the 0-D model is what made it")
    # A PRESCRIBED STEP HAS NO CFL GUARD, which is the whole point and
    # also the whole risk. `adjustTimeStep no` means blastFoam will take
    # this step whatever the flow does, so a case that is not quiescent
    # can sail past the stability limit without a word - the run does
    # not stop, it produces a wrong answer. Estimated here against the
    # acoustic speed of ambient air, which is a LOWER bound on the wave
    # speed in a chamber case: hot products are faster, so a step that
    # is already marginal on this estimate is worse in reality.
    _dt = float(getattr(case, 'fixed_dt', 0.0) or 0.0)
    _dx = float(getattr(case, 'cell_size_m', 0.0) or 0.0)
    if _dt > 0.0 and _dx > 0.0:
        # THE SPEED HAS TO COME FROM THE GAS IN THE CASE, not from
        # ambient air. Ambient is a LOWER bound and a lower bound is the
        # wrong end to check a stability limit against: it makes a step
        # look safe that is not. A chamber case carries its own T and
        # gamma, so use them - and the wave that matters is |u| + c, not
        # c, so the estimate is doubled for the jet the opening makes.
        cs = getattr(case, 'chamber_state', None) or {}
        if cs.get('T') and cs.get('gamma_p') and cs.get('R_p'):
            c_gas = math.sqrt(float(cs['gamma_p']) * float(cs['R_p'])
                              * float(cs['T']))
            speed = 2.0 * c_gas
            basis = (f'|u| + c in the chamber gas, ~{speed:.0f} m/s at '
                     f'{float(cs["T"]):.0f} K')
        else:
            speed = 2.0 * 340.3
            basis = ('|u| + c in ambient air, ~680 m/s - a LOWER bound, '
                     'since this case declares no gas state to read')
        co = _dt * speed / _dx
        if co > case.cfl:
            err(f"A fixed time step of {_dt:g} s implies a Courant "
                f"number of {co:.2f} on a {_dx:g} m cell, against "
                f"{basis} - past the {case.cfl:g} this case asks for. "
                f"`adjustTimeStep` is off with a fixed step, so nothing "
                f"will catch this at run time: the run will not stop, it "
                f"will produce a wrong answer.")
        else:
            warn(f"Fixed time step {_dt:g} s: the Courant limiter is OFF, "
                 f"so this run will take that step whatever the flow "
                 f"does. It sits at Co = {co:.3f} against {basis}. This "
                 f"exists for QUIESCENT verification cases, where a "
                 f"Courant-controlled step divides by a zero flux - "
                 f"anything that actually moves should leave it at 0.")
    if getattr(case, 'charge_resolution', 'resolve') == 'smear':
        note("Charge resolution 'smear' is ignored by the blastFoam "
             "backend (the grid is refined to resolve the charge)")
    if getattr(case, 'eos', 'idealGas') != 'idealGas':
        # only worth saying when someone actually picked a non-default
        # EOS (the GUI hides the row in blastFoam mode, T34)
        note("EOS setting is ignored by blastFoam (material JWL products "
             "+ ideal-gas air)")
    activation = getattr(case, 'activation', 'linear')
    if activation not in ('linear', 'none', 'programmedIgnition'):
        err(f"Unknown activation model '{activation}' "
            f"(use 'linear', 'programmedIgnition' or 'none')")
    elif activation == 'programmedIgnition':
        # N5-12, guide 5.6.1.3 (Giroux): a cell reacts at a rate set by
        # vDet and the LOCAL grid size instead of flipping whole when
        # the front line crosses it - the better near-field model.
        note("programmedIgnition (Giroux): cells burn at "
             "vDet/(1.5 dx) from their ignition time instead of "
             "switching whole (guide 5.6.1.3)")
    elif activation == 'none':
        note("Instant detonation ('none'): the whole charge reacts "
             "at t = 0")
    # N5-12: per-point delays/radii must line up with the points
    # they time. `det_points or 1`: with no explicit points the charge
    # centre is the single implicit point.
    npts = len(getattr(case, 'det_points', None) or []) or 1
    for name in ('det_delays', 'det_radii'):
        vals = getattr(case, name, None)
        if vals is None:
            continue
        if activation == 'none':
            err(f"{name} needs detonation points, and activation "
                f"'none' has none (the whole charge reacts at t = 0)")
        elif len(vals) != npts:
            err(f"{name} has {len(vals)} value(s) for {npts} "
                f"detonation point(s) - one per point")
        elif any(float(v) < 0 for v in vals):
            err(f"{name} must be >= 0")

    afterburn = getattr(case, 'afterburn', 'none') or 'none'
    if afterburn not in ('none', 'miller'):
        err(f"Unknown afterburn model '{afterburn}' "
            f"(use 'none' or 'miller')")
    elif afterburn == 'miller':
        from ..solvers.foam.materials import AFTERBURN
        ab = AFTERBURN.get(material)
        if ab is None:
            err(f"No afterburn parameters for '{material}'")
        elif material == 'TNT':
            note(f"Afterburn (Miller): up to {ab.Q0/1e6:g} MJ/kg released "
                 f"as the products burn with atmospheric oxygen - "
                 f"calibrated against Kingery-Bulmash (DONE.md N3: the "
                 f"anchor reads 1.02-1.20 of KB with this model on)")
        else:
            # P1-4 (owner decision 2026-09-09): only TNT was ever
            # calibrated. Every other material's Q0 comes from its oxygen
            # balance alone - the right order of magnitude, but nothing
            # was fitted to data, and the note used to claim otherwise.
            warn(f"Afterburn for {material} is NOT calibrated: "
                 f"Q0 = {ab.Q0/1e6:g} MJ/kg is derived from the oxygen "
                 f"balance alone (only TNT is calibrated, against "
                 f"Kingery-Bulmash). The order of magnitude is right - do "
                 f"not quote these numbers without a source of your own.")
    if n_procs > 1 and case.dim == 1:
        note("1D cases always run serial (MPI ranks ignored)")
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


#: ambient sound speed the stop conditions are scaled by [m/s]
C_AMB_AIR = float(np.sqrt(1.4 * 101325.0 / 1.225))


def cap_distance(case):
    """The domain length the automatic stop time is measured across:
    the radius in 1D, the longest side otherwise. Mirrors
    `solver{1,2,3}d.py` and `foam/writer._plan_*`."""
    if getattr(case, 'dim', 0) == 1:
        return float(getattr(case, 'radius_m', 0.0) or 0.0)
    Ls = [getattr(case, n, 0.0) or 0.0 for n in ('Lx', 'Ly', 'Lz')]
    return float(max(Ls))


def safety_cap_s(case):
    """The automatic end time [s]: ten domain crossings at ambient sound
    speed. This is what "End time 0 = auto" resolves to, and what
    bounds a run with no terminate boundary and no end time."""
    return 10.0 * cap_distance(case) / C_AMB_AIR


def long_run_note(case):
    """`(t_end, cap, ratio)` when an explicit end time runs past the
    automatic one, else None.

    Until 2026-09-18 such an end time was silently DISCARDED: every stop
    condition read `cap_is_end = bool(t_end) and t_end < cap`, so typing
    a bigger number changed nothing at all. Measured on a real native 2D
    run in a 1 m domain (cap 29.4 ms): t_end = 3 ms and 10 ms both
    stopped with `end time reached`, while t_end = 40 ms stopped with
    `safety cap` at 29.4 ms.

    The owner's decision is that an explicit end time wins - the cap is
    the automatic stop for when nothing was said, not a ceiling on what
    can be said - so the number is now honoured and this reports the
    cost instead, because ten times the simulated span is roughly ten
    times the wall clock.
    """
    t_end = float(getattr(case, 't_end', 0.0) or 0.0)
    cap = safety_cap_s(case)
    if t_end <= 0.0 or cap <= 0.0 or t_end <= cap:
        return None
    return t_end, cap, t_end / cap


def _warn_long_end_time(case, warn):
    """Warning, not error: the case is runnable and the result sound, it
    simply runs for longer than the automatic stop would have."""
    info = long_run_note(case)
    if info is None:
        return
    t_end, cap, ratio = info
    warn(f"End time {t_end * 1e3:.4g} ms is {ratio:.1f}x the automatic "
         f"stop time (~{cap * 1e3:.0f} ms = 10 domain crossings at "
         f"{C_AMB_AIR:.0f} m/s). It will be honoured, so expect roughly "
         f"{ratio:.0f}x the wall clock; the wave will have left the "
         f"domain long before the end.")


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

    # ── Trigger gauge (T51) ────────────────────────────────────────────
    trig = getattr(case, 'trigger_gauge', None)
    action = getattr(case, 'trigger_action', 'terminate') or 'terminate'
    if case.dim >= 2 and trig not in (None, 0, ''):
        n_g = len(case.gauges)
        try:
            trig_i = int(trig)
        except (TypeError, ValueError):
            trig_i = 0
            err("Trigger gauge must be a gauge number")
        if trig_i and not 1 <= trig_i <= n_g:
            err(f"Trigger gauge {trig_i}: the case has {n_g} gauge(s)")
        if action not in TRIGGER_ACTIONS:
            err(f"Trigger action '{action}': expected one of "
                f"{', '.join(TRIGGER_ACTIONS)}")
        elif 'remap' in action:
            if case.dim == 3:
                err("Trigger action 'remap' is not available in 3D - "
                    "there is no 3D remap format; use 'terminate'")
            elif case.dim == 2 and case.geometry != 'axisymmetric':
                err("Trigger action 'remap' needs an axisymmetric 2D "
                    "case (only those can be remapped into 3D)")
            elif not (getattr(case, 'trigger_file', None)
                      or case.profile_file):
                err("Trigger action 'remap' needs a remap filename "
                    "(trigger file, or the case's profile output)")
            else:
                note(f"Gauge {trig_i} will write the remap file when the "
                     f"wave reaches it"
                     + ("" if 'terminate' in action
                        else " (the run then continues)"))
        else:
            note(f"The run ends when the wave reaches gauge {trig_i}")

    if case.dim == 1:
        kind = normalize_bc(getattr(case, 'bc_outer', 'terminate'))
        if kind not in BC_KINDS:
            err(f"Outer boundary: unknown kind '{kind}' "
                f"(expected one of {', '.join(BC_KINDS)})")
        elif kind != 'terminate' and not getattr(case, 't_end', 0.0):
            c_air = float(np.sqrt(1.4 * 101325.0 / 1.225))
            warn(f"The outer boundary is '{kind}' and no end time is "
                 f"set: the run is bounded only by the safety cap "
                 f"(~{10.0 * case.radius_m / c_air * 1e3:.0f} ms).")
        _warn_long_end_time(case, warn)
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
    # ── Boundary kinds (T50) ───────────────────────────────────────────
    bcs = normalize_bcs(dict(case.bcs or {}))
    for side, kind in sorted(bcs.items()):
        if kind not in BC_KINDS:
            err(f"Boundary {side}: unknown kind '{kind}' "
                f"(expected one of {', '.join(BC_KINDS)})")
    ends_itself = any(k == 'terminate' for k in bcs.values())
    if not ends_itself and not getattr(case, 't_end', 0.0):
        c_air = float(np.sqrt(1.4 * 101325.0 / 1.225))
        cap_ms = 10.0 * max(dims) / c_air * 1e3
        warn(f"No terminate boundary and no end time: the run is bounded "
             f"only by the safety cap (~{cap_ms:.0f} ms). Set a side to "
             f"'terminate' to stop when the wave reaches it.")
    _warn_long_end_time(case, warn)
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
            # UX-04: this pin used to be silent - a case file carrying
            # x != 0 was quietly recentred without a word
            if case.geometry == 'axisymmetric' and center[0]:
                note(f"Axisymmetric: the charge sits on the axis - "
                     f"burst x = {center[0]:g} is ignored (r = 0)")
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
            if bcs.get(side) == 'reflect':
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
                if bcs.get(side) == 'reflect':
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
    elif init == 'chamber':
        # HD1-3b: nothing to load and nothing to resolve. The gas is
        # already made and the room is a set of obstacle boxes, so the
        # charge-sphere geometry checks above have nothing to say and
        # the profile-file checks below are about a file that does not
        # exist for this mode. Its own checks ran earlier, next to the
        # other blastFoam-specific ones.
        rep.r_exp = 0.0
    else:
        if not case.profile_file_in:
            err("A profile file is required for remap initialization")
        elif not (pending_inputs or os.path.exists(case.profile_file_in)):
            err(f"Profile file not found: {case.profile_file_in}")
        elif foam and not pending_inputs:
            # N5-4: the single-case path, where the user points at a
            # profile that already exists. The CHAIN path never reaches
            # here - its input is written by the stage before it and
            # provably does not exist yet (pending_inputs), which is why
            # chain.handoff_conflicts compares the two solvers directly
            # instead. Guarded this hard because validate_case runs on
            # every keystroke behind a 300 ms debounce: profile_source
            # is a memoised header-only read, one os.stat unless the
            # file actually changed.
            from . import chain as _chain          # deferred - chain
            from . import profiles as _profiles    # imports case
            src = _profiles.profile_source(case.profile_file_in)
            if src == 'native':
                err(_chain.HANDOFF_MSG[0].upper() + _chain.HANDOFF_MSG[1:])
            elif src == 'unknown':
                note("This profile carries no solver stamp (it predates "
                     "blastlab recording one). If it came from the "
                     "native solver the hand-off over-prices the "
                     "product cells by ~33 % - re-run the stage that "
                     "produced it to get a stamped profile.")
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
        # T70: a profile-initialised stage plans exactly the same way -
        # `_plan_amr` never looks at the charge and `validate_amr` skips
        # its "resolve the charge" rule when there is none
        if not rep.errors:
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
                if init != 'charge':
                    note(f"The remapped state is written on the "
                         f"{plan.dx_base:.5g} m base mesh and the AMR "
                         f"refines from there - the base cell, not the "
                         f"AMR level, sets how sharp the hand-off is")
                # T42/N16-b: AMR runs in parallel; the ingest reads
                # processor*/ directly (reconstructPar cannot follow a
                # mesh that changes between writes)
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

    # N17/T48: the caps come from the WSL VM's measured RAM when a probe
    # has run (BYTES_PER_CELL). N21: when it has NOT, they come from a
    # conservatively assumed VM rather than the fixed FOAM_CELLS_*
    # constants - an unknown machine must not be treated as a large one.
    # `hardware()` never touches WSL, so validation stays instant.
    from ..solvers.foam import env as _env
    _hw = _env.hardware() or {}
    _caps = _env.plan_run(0, 0, cores=_hw.get('cores'),
                          ram_gb=_hw.get('ram_gb'), dim=case.dim,
                          ram_source=_hw.get('ram_source'),
                          cores_source=_hw.get('cores_source'))
    cap_warn, cap_refuse = _caps.cell_cap_warn, _caps.cell_cap_refuse

    # N21: the native solvers run in THIS process on the host's RAM, so
    # they get their own plan. `host()` is cache-only (ctypes, no I/O on
    # the validation path) and the derived cap can only lower the fixed
    # CELLS_* constants - the solvers keep enforcing those unchanged.
    _nat = _hardware.plan_native(
        dim=case.dim, order=int(getattr(case, 'order', 1) or 1),
        n_snapshots=int(getattr(case, 'n_snapshots', 6) or 6),
        ram_gb=_hardware.host().get('ram_gb'))
    nat_warn, nat_refuse = _nat.cell_cap_warn, _nat.cell_cap_refuse

    def host_hint():
        """Why the native cap is what it is, when RAM set it."""
        if not _nat.from_memory or nat_refuse >= (
                CELLS_2D_MAX if case.dim == 2 else CELLS_REFUSE):
            return ""
        return (f" (~{_nat.est_bytes(nat_refuse) / 2 ** 30:.1f} GB of the "
                f"{_nat.ram_gb} GB this PC has, at "
                f"~{_nat.bytes_per_cell / 1000:.2f} KB/cell) - the native "
                f"solver runs inside this app, so it cannot page out")

    def ram_hint():
        """Why the cap is what it is, in the units the user can act on."""
        gb = f"~{cap_refuse * BYTES_PER_CELL / 2 ** 30:.1f} GB"
        kb = f"~{BYTES_PER_CELL / 1000:.1f} KB/cell"
        if not _caps.from_memory:
            return (f" ({gb} of an assumed {FOAM_VM_GB_ASSUMED} GB WSL VM "
                    f"at {kb} - the real size is unknown) - let the WSL "
                    f"hardware probe finish, or click Re-detect")
        return (f" ({gb} of the {_hw['ram_gb']} GB WSL VM at {kb}) - "
                f"shrink the case, raise `memory=` in "
                f"%USERPROFILE%\\.wslconfig, or use AMR")

    if foam and not _caps.from_memory:
        warn(f"WSL hardware not detected - cell caps assume a "
             f"{FOAM_VM_GB_ASSUMED} GB VM ({cap_refuse:,} cells). A case "
             f"that validated on another machine may be refused here; "
             f"click Re-detect once WSL is up. Headless callers should "
             f"call solvers.foam.env.prime_from_settings() at start-up.")
    elif foam and _caps.ram_source == _hardware.CACHED:
        note(f"Cell caps from hardware measured on this machine in an "
             f"earlier session ({_hw['ram_gb']} GB VM); re-checking in "
             f"the background.")

    rep.effective_dx = dx
    if plan is not None and plan.amr:
        # AMR: the mesh grows during the run up to maxCells, so that is
        # the number the blastFoam caps apply to (t = 0 is the base grid)
        n_max = (int(getattr(case, 'amr_max_cells', 0) or 0)
                 or cap_warn)
        if n_max > cap_refuse:
            err(f"AMR max cells {n_max:,} exceeds the blastFoam cap of "
                f"{cap_refuse:,}" + ram_hint())
        elif n_max > cap_warn:
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
            if n > cap_refuse:
                err(f"~{fmt_cells(n)} cells exceeds the blastFoam cap of "
                    f"{cap_refuse:,}" + ram_hint() + scale_hint())
            elif n > cap_warn:
                warn(f"Large grid: ~{n:,} cells - expect a long run "
                     f"and GBs of case files on the WSL disk")
        elif n > nat_refuse:
            err(f"~{fmt_cells(n)} cells exceeds the 2D cap of {nat_refuse:,}"
                + host_hint() + scale_hint())
        elif n > nat_warn:
            warn(f"Large grid: ~{n:,} cells - expect a long run"
                 f" and ~{_nat.est_bytes(n) / 2 ** 30:.1f} GB of RAM")
    else:
        n = int(case.Lx / dx) * int(case.Ly / dx) * int(case.Lz / dx)
        if plan is not None and (plan.refined or plan.amr):
            n = plan.n_pred
        if plan is not None and plan.amr:
            pass
        elif foam:
            if n > cap_refuse:
                err(f"~{fmt_cells(n)} cells exceeds the blastFoam cap of "
                    f"{cap_refuse:,}" + ram_hint() + scale_hint())
            elif n > cap_warn:
                warn(f"Large grid: ~{n:,} cells - expect hours of wall "
                     f"time and GBs of case files on the WSL disk")
        elif n > nat_refuse:
            err(f"~{fmt_cells(n)} cells exceeds the 3D cap of {nat_refuse:,}"
                + host_hint() + scale_hint())
        elif n > nat_warn:
            warn(f"Large grid: ~{n:,} cells - expect a long run and "
                 f"~{_nat.est_bytes(n) / 2 ** 30:.1f} GB of RAM")
    rep.n_cells = n
    if foam:
        # N17/T48: resolve the rank count with the real cell count and
        # say what was decided, for auto (0) as well as an explicit ask
        # every argument the RUN will use, so what validation reports is
        # what actually launches (N21: sources and the settings rank
        # limit included - without max_ranks the note would promise more
        # ranks than resolve_nprocs goes on to ask for)
        rep.run_plan = _env.plan_run(
            int(getattr(case, 'n_procs', 0) or 0), n,
            cores=_hw.get('cores'), ram_gb=_hw.get('ram_gb'),
            dim=case.dim, amr=amr, headroom=_env.mpi_headroom(),
            ram_source=_hw.get('ram_source'),
            cores_source=_hw.get('cores_source'),
            max_ranks=_env.mpi_max_ranks())
        if case.dim > 1:
            note("Parallel run: " + rep.run_plan.reason)
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
            continue
        # A wall carved a single cell thick is a numerical hazard: shock
        # diffraction over a one-cell blade collapses deltaT and can end
        # in SIGFPE (measured: 0.3 m wall on a 0.5 m base mesh). The
        # carve uses base-cell FACES (refine.snap_obstacles outward for
        # foam), so the count below is the snapped width, not len/dx.
        dxb = plan.dx_base if plan is not None else dx
        if dxb and dxb > 0:
            for ax, (a, b) in enumerate(zip(lo, hi)):
                n_side = (int(np.ceil(b / dxb - 1e-6))
                          - int(np.floor(a / dxb + 1e-6)))
                if n_side <= 1:
                    warn(f"Obstacle {box} is only one cell thick along "
                         f"{'xyz'[ax]} ({b - a:g} m wall, {dxb:g} m base "
                         f"cell) - shock reflection off a single-cell "
                         f"wall tends to go numerically unstable. Use a "
                         f"base cell <= {(b - a) / 2:g} m so the wall is "
                         f"at least 2 cells thick"
                         # the obvious "just add AMR" does not work, and
                         # the crashing run (20260915-090553) proved it:
                         # it ran amr_levels = 2 and still hit SIGFPE
                         + (" (AMR levels do not help: obstacles are "
                            "carved on the base mesh, so the wall stays "
                            "one base cell at every level)"
                            if foam else ""))
                    break

    if case.dim == 2 and case.profile_file and case.geometry != 'axisymmetric':
        err("2D profile export (for 3D remap) requires axisymmetric geometry")
    return rep
