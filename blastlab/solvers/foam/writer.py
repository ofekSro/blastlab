"""blastFoam case generation: render a blastlab Case as a complete
OpenFOAM-9 case tree.

Pure-text rendering (`render_case`) is separated from disk I/O
(`write_case`) so golden tests can pin the generated dicts without WSL.

Geometry mirrors the native solvers: the same effective cell size
(FOAM_EXP_CELLS across the charge radius, material-aware density) on the
same uniform grid built by core.grid, so field read-back lands
cell-for-cell on the native x_c/y_c/z_c arrays (a single-block
blockMesh numbers cells x-fastest -> reshape(..., order='F')).

Templates copied from the shipped v6.2.0 tutorials:
  mappedBuilding3D/sector  1D spherical sector (collapsed hex + wedges)
  axisymmetricCharge       2D wedge orientation and face sets
  freeField                3D box, fvSchemes/fvSolution/phaseProperties
The mesh is uniform, statically refined per zone (N15: topoSet +
refineMesh passes) or dynamically refined (N16: `adaptiveFvMesh`, whose
per-time structure the backend reads back from `C` + `cellLevel`); 3D
obstacle boxes are carved out of the block by topoSet/subsetMesh
(exposed faces -> 'obstacles' wall patch), keeping the retained cells
in blockMesh order so read-back scatters onto the same native grid.
Profile initialization is a later phase.
"""

import math
import os
from dataclasses import dataclass, field

import numpy as np

from ...core.constants import (GAMMA_AIR, RHO_AIR, P_AIR, MIN_EXP_CELLS,
                               FOAM_CELLS_WARN)
from ...core import refine
from ...core.bc import normalize_bc
from ...core.grid import make_grid_1d
from ...core.refine import effective_dx as _effective_dx
from ...core.refine import exp_cells as _exp_cells
from . import env
from .dicts import (AMR_ALLOWABLE_IMBALANCE, AMR_BALANCE_INTERVAL,
                    AMR_LOAD_BALANCE, FLUX_SCHEME, LOHNER_EPS, P_OPEN_BC,
                    TIME_PRECISION,
                    Raw, block, fmt, foam_file, tfmt)
from .materials import AFTERBURN, MATERIALS, E0, charge_radius

PHASE = 'expl'                  # fixed phase name for every material
HALF_ANGLE_DEG = 1.0            # wedge half-angle (1D sector, 2D axisym)
CV_AIR = 718.0                  # J/(kg K), freeField tutorial value
MOLW_AIR = 28.97
C_AMB = math.sqrt(GAMMA_AIR * P_AIR / RHO_AIR)
T_AMB = P_AIR / (RHO_AIR * (GAMMA_AIR - 1.0) * CV_AIR)
N_WRITES_MIN, N_WRITES_MAX = 40, 60
#: live sampling functionObjects: p(r) line (1D) / p plane cut (2D+3D)
LIVE_SET = 'liveLine'
LIVE_SLICE = 'liveSlice'


def live_sample_steps(dim):
    """Live-sample cadence in solver steps. 3D steps take seconds each,
    so every step feeds the live view; 1D/2D run tens of steps per
    second, where sparser sampling avoids pointless dir churn (the GUI
    poll consumes at most ~4 frames/s anyway)."""
    return {1: 10, 2: 5, 3: 1}[dim]


def live_steps_for(policy, dim):
    """Live-sample cadence [solver steps] for a live-view refresh policy
    (RunHooks.refresh): 'Refresh every N steps' samples every N steps
    so the live view follows the setting; seconds / automatic keep the
    per-dim default (the ingest tail applies the wall-clock gate)."""
    mode, val = policy
    if mode == 'steps':
        return max(1, int(val))
    return live_sample_steps(dim)

#: OpenFOAM dimension vectors
_DIMS = dict(p='[1 -1 -2 0 0 0 0]', T='[0 0 0 1 0 0 0]',
             U='[0 1 -1 0 0 0 0]', alpha='[0 0 0 0 0 0 0]',
             rho='[1 -3 0 0 0 0 0]')


@dataclass
class CaseSpec:
    """Everything the runner/reader need to drive and decode a case."""
    dim: int
    material: str
    phase: str = PHASE
    n_procs: int = 1                # effective MPI ranks (1 = serial)
    nx: int = 0
    ny: int = 1
    nz: int = 1
    dx: float = 0.0
    r_exp: float = 0.0
    center: tuple = (0.0, 0.0, 0.0)     # foam coordinates
    end_time: float = 0.0
    cap_is_end: bool = False        # end_time is the user's t_end
    write_interval: float = 0.0
    #: False pins writeInterval for the whole run: the adaptive
    #: controller never rewrites the controlDict, so two identical runs
    #: write at exactly the same times and stay bit-identical (B23)
    adaptive_write: bool = True
    #: HD1-15: N > 0 while the case's write budget is in effect (2D/3D,
    #: explicit end time): writeInterval is t_end / N for the whole run,
    #: the adaptive controller is off, and the run loop keeps the
    #: decomposed copy of the latest write only (runloop.DecomposedPurge).
    write_budget: int = 0
    grid: dict = None                    # core.grid product (per dim)
    charges: list = field(default_factory=list)   # [((x,y,z), mass_kg)]
    det_points: list = field(default_factory=list)  # [] = charge centres
    probe_pts: list = field(default_factory=list)   # foam (x,y,z)
    gauge_ids: list = field(default_factory=list)   # native radii/points
    #: blastProbes `adjustLocations`. Despite the name it does NOT move
    #: an interior probe: `movePts` is read only inside
    #: `if (nBadProbes > 0 && movePts)` (blastProbes.C:64/207/218), and
    #: `nBadProbes` counts probes found in NO cell. The sample is the raw
    #: value of whichever cell `findCell` elects; `elementLocations_`
    #: merely REPORTS that cell's centre.
    #:
    #: The old comment here said 'yes' pins the sample to a coarse cell
    #: that later refines under it. T40 tested exactly that and refuted
    #: it - turning the flag off moves AMR-vs-static arrival by 0.15 pp,
    #: "because blastProbes reports the containing cell's value either
    #: way" (DONE.md T40, 2026-09-07). The real +18 % there is a
    #: resolution difference at the gauge, not this flag. The comment was
    #: never updated after that measurement; corrected 20.09 (reverify).
    #:
    #: 'yes' matches the vendor tutorials and still governs probes that
    #: land outside the mesh, so the default stays.
    probe_adjust: str = 'yes'
    #: profile-initialised stage (N7): (rho, u, v, w, e, phase) arrays on
    #: the case grid plus the profile's start time. None = charge init.
    init_state: dict = None
    #: physical time the run starts at - 0 for a charge, the profile's
    #: own time for a stage continuing an earlier one (N7)
    t_start: float = 0.0
    #: `files` entries held back until the mesh stages have finished
    #: changing the cell count (T62). A profile stage's fields are
    #: nonuniform over the FINAL cells, so subsetMesh/refineMesh must
    #: not find them lying in the time dir - they read every field at
    #: the current mesh and abort on the count mismatch. A charge case
    #: writes uniform fields, which map onto any mesh, and defers none.
    deferred: tuple = ()
    #: P1-5: emit the per-step pMax/impulse function objects at all. True
    #: everywhere except the resumed leg of an AMR run, where blastFoam
    #: cannot restart them across a mesh change - see
    #: backend._disable_fo_accumulators. The Python per-write accumulator
    #: then carries the peak/impulse maps, which it can, because the
    #: resume's ingest replays every write the stopped run left.
    fo_accumulators: bool = True

    @property
    def burst_points(self):
        """Centres the shock front is measured from, as [(x, y, z), ...].
        The charge centres, or - for a profile-initialised stage, which
        has no charge list (N7) - the profile's own centre, which is
        `case.center`."""
        return [c for c, _m in self.charges] or [tuple(self.center)]

    @property
    def decomposed(self):
        """True while written times live in processor*/ instead of the
        case root. Uniform parallel runs are reconstructed back to the
        root by the run loop; a parallel AMR run cannot be (the mesh
        changes under reconstructPar), so its times stay per-rank and
        the ingest concatenates them - N16-b/T42."""
        return bool(self.amr and self.n_procs > 1)

    def time_root(self):
        """The directory whose subdirs name the written times."""
        return (os.path.join(self.case_unc, 'processor0')
                if self.decomposed else self.case_unc)

    def time_dirs(self, name):
        """Directory (or, decomposed, directories) holding time `name`.
        A list means "one part per rank, concatenate in order" - safe
        because the AMR remap is geometric, so cell order carries no
        meaning beyond matching C/cellLevel/fields within a part."""
        if not self.decomposed:
            return os.path.join(self.case_unc, name)
        return [os.path.join(self.case_unc, 'processor%d' % i, name)
                for i in range(self.n_procs)]

    @property
    def start_dir(self):
        """Name of the time directory the initial fields live in. A
        profile stage continues an earlier stage's clock, so its state
        is written at t0 and picked up with `startFrom latestTime` -
        which keeps the value it scanned and rebuilds the name from it,
        so the name has to be OpenFOAM's own (tfmt, not fmt) or the
        fields are asked for under a name nothing wrote (T62)."""
        return '0' if not self.t_start else tfmt(self.t_start)
    patches: list = field(default_factory=list)     # (name, kind)
    #: face-snapped by the plan (snap_obstacles) - never the raw case
    #: boxes; obstacles_moved keeps (original, snapped) for the run log
    obstacles: list = field(default_factory=list)   # (x0,x1,y0,y1,z0,z1)
    obstacles_moved: list = field(default_factory=list)
    solid: object = None            # (nx,ny,nz) bool mask, None = none
    files: dict = field(default_factory=dict)       # relpath -> text
    case_posix: str = ''
    case_unc: str = ''
    # local refinement (core.refine): nx/ny/nz/dx/grid/solid above are
    # the FINE display grid (dx = dx_base / 2**lmax); blockMesh is built
    # on the base counts `nb`, refineMesh passes realise `zones`
    dx_base: float = 0.0
    nb: tuple = ()                  # base (nx, ny[, nz]) for blockMesh
    grid_base: dict = None          # core.grid dict of the base grid
    levels: object = None           # int8 level map on the fine grid
    lmax: int = 0
    zones: list = field(default_factory=list)       # snapped (box.., level)
    solid_base: object = None       # obstacle mask on the base grid
    remap: object = None            # fine-grid int32 -> foam cell (T18)
    n_cells_actual: int = None      # foam cell count once the mesh exists
    # dynamic AMR (N16): max level below the base cell (0 = static mesh)
    # and the level of the display grid (`grid/nx/../dx` sit there; the
    # structure of every written time is read back from C + cellLevel)
    amr: int = 0
    display_level: int = 0
    mesh0: object = None            # AMR: the t = 0 MeshMap (build_remap)
    # live-sample cadence [solver steps] the case is written with
    # (0 = the per-dim default of live_sample_steps); the run loop
    # rewrites it when the GUI's refresh policy changes mid-run
    live_steps: int = 0

    @property
    def l_inf(self):
        """Relaxation length for pressureWaveTransmissive (N5-10).

        The largest domain extent: the length over which the outflow
        patch is told to return to `fieldInf`. Anything much shorter
        clamps the boundary towards ambient while the wave is still
        passing through it."""
        g = self.grid or {}
        keys = ('x_face', 'y_face', 'z_face') if self.dim >= 2 else ('r_face',)
        try:
            return max(float(g[k][-1]) for k in keys if k in g)
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    @property
    def dx_charge(self):
        """Finest spacing the charge region will actually see - the
        grid setFields marks whole cells on. An AMR case is refined to
        `amr` levels around the charge by setRefinedFields before the
        selection runs; a static case is already at its fine spacing.
        Mirrors what validate_case reports the charge cells at."""
        if self.amr:
            return self.dx_base / 2 ** self.amr
        return self.dx

    @property
    def n_cells(self):
        """Cell count of the ACTUAL mesh: obstacle cells are carved out
        by topoSet/subsetMesh, so field files hold only fluid values; a
        refined mesh counts its real cells (predicted until the mesh
        stages have run, then measured)."""
        if self.n_cells_actual is not None:
            return self.n_cells_actual
        if self.lmax:
            return refine.n_cells_from_levels(self.levels, self.lmax,
                                              self.solid)
        n = self.nx * self.ny * self.nz
        if self.solid is not None:
            n -= int(self.solid.sum())
        return n

    @property
    def init_grid(self):
        """The grid a profile-initialised stage's state is written on:
        the mesh that exists when those fields land (T70/N7).

        Uniform case: base and display grid are the same object, so this
        is `grid` as before. AMR: the t = 0 mesh IS the uniform base grid
        - blockMesh builds it from `nb` and adaptiveFvMesh refines only
        once the run is stepping - while `grid` sits at `display_level`,
        which would be 2**(dim*D) times too many values. A statically
        refined mesh never gets here (validation refuses zones for a
        profile stage: refineMesh renumbers the cells)."""
        return self.grid_base if self.amr else self.grid

    @property
    def init_solid(self):
        """Obstacle mask on `init_grid` (see there)."""
        return self.solid_base if self.amr else self.solid

    @property
    def mesh_fields(self):
        """Per-time mesh files the readiness gate must see (AMR only)."""
        return ('C', 'cellLevel') if self.amr else ()

    def apply_plan(self, plan):
        """Take the base/fine grids and zones from a core.refine.Plan."""
        self.amr = int(getattr(plan, 'amr', 0) or 0)
        self.display_level = int(getattr(plan, 'display_level', 0) or 0)
        self.dx_base = float(plan.dx_base)
        self.nb = tuple(int(plan.base[k]) for k in
                        (('Nx', 'Ny') if plan.dim == 2 else ('Nx', 'Ny', 'Nz')))
        self.grid_base = plan.base
        self.levels, self.lmax = plan.levels, plan.lmax
        self.zones = list(plan.zones)
        self.solid_base = plan.solid_base
        self.solid = plan.solid_fine
        # obstacle boxes SNAPPED outward to base-cell faces by the plan
        # (snap_obstacles): topoSet's boxToCell and the Python masks all
        # consume these, so they agree cell-for-cell by construction
        self.obstacles = [tuple(b) for b in
                          (getattr(plan, 'obstacles', None) or [])]
        self.obstacles_moved = list(
            getattr(plan, 'obstacles_moved', None) or [])

    def refine_meta(self):
        """meta['refine'] payload (None for a uniform mesh). For AMR the
        levels are the display-grid level map of the LAST written time
        (the backend fills it in at finalize)."""
        if not self.lmax and not self.amr:
            return None
        d = dict(levels=self.levels, lmax=self.lmax,
                 dx_base=self.dx_base, zones=list(self.zones))
        if self.amr:
            d.update(amr=self.amr, display_level=self.display_level)
        return d


# ── planning ────────────────────────────────────────────────────────────────

def _n_writes(n_snapshots):
    return min(N_WRITES_MAX, max(N_WRITES_MIN, 4 * n_snapshots))


def _timing(case, cap_dist, est_dist, n_snapshots):
    """(end_time, write_interval, cap_is_end), mirroring the native
    conventions: the safety cap is 10*cap_dist/c_amb (solver3d.py:298
    uses max(L)); t_end overrides it only when smaller (cap_is_end);
    writeInterval is sized from the native shock-transit estimate
    (1.5*est_dist/c_amb, est_dist = nearest open boundary) so an early
    shock-arrival stop still has a full frame record."""
    t_end = getattr(case, 't_end', 0.0) or 0.0
    cap = 10.0 * cap_dist / C_AMB
    # T52: an explicit end time wins, shorter OR longer than the cap.
    # `and t_end < cap` used to discard any end time past it, so a bigger
    # number in the field changed nothing (2026-09-18). writeInterval is
    # unaffected: t_est below stays bounded by the transit estimate, so a
    # long run writes at the same cadence rather than N times as often.
    cap_is_end = bool(t_end)
    end_time = t_end if cap_is_end else cap
    # reference speed 2*c_amb: the shock front outruns ambient sound
    # (strongly so in the near field), and frames/snapshots only exist
    # at write times - this keeps the pre-arrival record dense enough
    # without exploding the dir count on slow far-field runs.
    # The interval starts 4x DENSER than that sizing so the first live
    # frame appears quickly (near-field dt is tiny - at the nominal
    # interval a heavy charge shows nothing for thousands of steps);
    # the backend's adaptive controller doubles it back within bounds
    # [i0/4, i0*8] once frames accumulate.
    t_est = min(end_time, 1.5 * est_dist / (2.0 * C_AMB))
    budget = write_budget_of(case)
    if budget and cap_is_end:
        # HD1-15: a number of writes asked for, spread evenly over the
        # window asked for - not a transit estimate the controller then
        # has to chase. The end-time write (writeTimeList) coincides with
        # the last one, so it is neither lost nor doubled.
        return end_time, end_time / budget, cap_is_end
    return end_time, t_est / _n_writes(n_snapshots) / 4.0, cap_is_end


def write_budget_of(case):
    """HD1-15: the case's write budget N (> 0) when it can take effect -
    a 2D/3D case with an explicit end time - else 0. Validation refuses a
    budget without an end time; this just never pins one to the cap."""
    try:
        b = int(getattr(case, 'write_budget', 0) or 0)
    except (TypeError, ValueError):
        return 0
    if b <= 0 or not (getattr(case, 't_end', 0.0) or 0.0) > 0.0:
        return 0
    return b


def _apply_budget(spec, case):
    """Carry an effective write budget onto the spec: the interval
    `_timing` pinned stays pinned (no adaptive controller)."""
    spec.write_budget = write_budget_of(case) if spec.cap_is_end else 0
    if spec.write_budget:
        spec.adaptive_write = False


def plan_case(case):
    """Geometry/timing plan (no text yet). Returns a CaseSpec without
    `files`."""
    mat = getattr(case, 'material', 'TNT')
    m = MATERIALS[mat]

    if case.dim == 1:
        r_exp = charge_radius(case.charge_kg, m)
        dx = _effective_dx(case.cell_size_m, r_exp, case.radius_m,
                           _exp_cells(case))
        r_face, r, A_face, V_cell = make_grid_1d(case.radius_m, dx)
        grid = dict(r_face=r_face, r=r, A_face=A_face, V_cell=V_cell)
        spec = CaseSpec(dim=1, material=mat, nx=len(r), dx=dx,
                        r_exp=r_exp, center=(0.0, 0.0, 0.0), grid=grid)
        spec.charges = [((0.0, 0.0, 0.0), float(case.charge_kg))]
        R_out = r_face[-1]
        spec.patches = [('outlet',
                         normalize_bc(getattr(case, 'bc_outer',
                                              'terminate'))),
                        ('wedge', 'wedge')]
        gauges = [g for g in case.gauge_radii if 0.0 < g <= R_out]
        spec.gauge_ids = gauges
        spec.probe_pts = [(g, 0.0, 0.0) for g in gauges]
        spec.end_time, spec.write_interval, spec.cap_is_end = _timing(
            case, R_out, R_out, case.n_snapshots)
        return spec

    if case.dim == 2:
        planar = case.geometry == 'planar'
        init_mode = getattr(case, 'init_mode', 'charge')
        r_exp = (charge_radius(case.charge, m, planar=planar)
                 if init_mode == 'charge' else 0.0)
        # base spacing (charge auto-refine unless charge_refine='zone')
        # + zones -> the fine display grid the reader scatters onto
        plan = refine.plan_levels(case, rho0=m.rho0)
        grid, dx = plan.fine, plan.dx_fine
        Lx_eff, Ly_eff = grid['x_face'][-1], grid['y_face'][-1]
        x0 = 0.0 if not planar else case.center[0]
        y0 = case.center[1]
        spec = CaseSpec(dim=2, material=mat,
                        nx=grid['Nx'], ny=grid['Ny'], dx=dx, r_exp=r_exp,
                        center=(x0, y0, 0.0), grid=grid)
        spec.apply_plan(plan)
        spec.charges = ([((x0, y0, 0.0), float(case.charge))]
                        if init_mode == 'charge' else [])
        spec.det_delays = list(getattr(case, 'det_delays', None) or [])
        spec.det_radii = list(getattr(case, 'det_radii', None) or [])
        spec.det_points = [
            ((0.0 if not planar else float(px)), float(py), 0.0)
            for px, py in (getattr(case, 'det_points', None) or [])]
        if planar:
            spec.patches = [(s, case.bcs[s])
                            for s in ('x_lo', 'x_hi', 'y_lo', 'y_hi')]
            spec.patches.append(('frontAndBack', 'empty'))
        else:
            # collapsed x=0 face is the axis; x_lo never becomes a patch
            spec.patches = [(s, case.bcs[s])
                            for s in ('x_hi', 'y_lo', 'y_hi')]
            spec.patches.append(('wedge', 'wedge'))
        # obstacle rectangles in the (x, y) / (r, z) plane, carved out
        # by topoSet/subsetMesh exactly like the 3D boxes. apply_plan
        # already adopted the plan's FACE-SNAPPED boxes (snap_obstacles)
        # - the raw case boxes are never handed to the carve, so a box
        # edge can no longer tie with a cell-centre line (N2-16).
        if spec.obstacles:
            # mask evaluated on the BASE grid by the plan (boxToCell
            # carves before refinement) and expanded to the fine grid
            spec.patches.append(('obstacles', 'wall'))

        def _in_obstacle2(g):
            return any(x0 <= g[0] <= x1 and y0 <= g[1] <= y1
                       for x0, x1, y0, y1 in spec.obstacles)

        gauges = [g for g in case.gauges
                  if 0 <= g[0] <= Lx_eff and 0 <= g[1] <= Ly_eff
                  and not _in_obstacle2(g)]
        spec.gauge_ids = gauges
        spec.probe_pts = [(g[0], g[1], 0.0) for g in gauges]
        side_d = dict(x_lo=x0, x_hi=Lx_eff - x0,
                      y_lo=y0, y_hi=Ly_eff - y0)
        if not planar:
            side_d.pop('x_lo')      # collapsed wedge axis, never open
        opens = [d for s, d in side_d.items()
                 if normalize_bc(case.bcs.get(s)) != 'reflect']
        corners = [(cx, cy) for cx in (0.0, Lx_eff)
                   for cy in (0.0, Ly_eff)]
        far = max(math.hypot(cx - x0, cy - y0) for cx, cy in corners)
        est = min(opens) if opens else far
        spec.end_time, spec.write_interval, spec.cap_is_end = _timing(
            case, max(Lx_eff, Ly_eff), est, case.n_snapshots)
        _apply_budget(spec, case)
        return spec

    # 3D - the primary charge plus any extras; the grid resolves the
    # SMALLEST charge, snapshot radii start from the largest
    x0, y0, z0 = case.center
    init_mode = getattr(case, 'init_mode', 'charge')
    if init_mode == 'charge':
        charges = [((float(x0), float(y0), float(z0)), float(case.charge))]
        for ex, ey, ez, mass in getattr(case, 'charges', None) or []:
            charges.append(((float(ex), float(ey), float(ez)), float(mass)))
        r_exps = [charge_radius(mass, m) for _c, mass in charges]
        r_exp = max(r_exps)
    else:
        charges, r_exps, r_exp = [], [0.0], 0.0
    plan = refine.plan_levels(case, rho0=m.rho0)
    grid, dx = plan.fine, plan.dx_fine
    Ls = (grid['x_face'][-1], grid['y_face'][-1], grid['z_face'][-1])
    spec = CaseSpec(dim=3, material=mat,
                    nx=grid['Nx'], ny=grid['Ny'], nz=grid['Nz'],
                    dx=dx, r_exp=r_exp, center=(x0, y0, z0), grid=grid)
    spec.apply_plan(plan)
    spec.charges = charges
    spec.det_delays = list(getattr(case, 'det_delays', None) or [])
    spec.det_radii = list(getattr(case, 'det_radii', None) or [])
    spec.det_points = [tuple(float(v) for v in p)
                       for p in (getattr(case, 'det_points', None) or [])]
    spec.patches = [(s, case.bcs[s])
                    for s in ('x_lo', 'x_hi', 'y_lo', 'y_hi',
                              'z_lo', 'z_hi')]
    # obstacles: axis-aligned boxes carved out of the mesh by
    # topoSet(boxToCell)/subsetMesh. apply_plan already adopted the
    # plan's FACE-SNAPPED boxes (snap_obstacles), so boxToCell and the
    # Python-side mask (cell CENTRE inside, inclusive) agree by
    # construction and read-back scatters onto the full native grid.
    if spec.obstacles:
        spec.patches.append(('obstacles', 'wall'))   # mask: see apply_plan

    def _in_obstacle(g):
        return any(x0 <= g[0] <= x1 and y0 <= g[1] <= y1
                   and z0 <= g[2] <= z1
                   for x0, x1, y0, y1, z0, z1 in spec.obstacles)

    gauges = [g for g in case.gauges
              if all(0 <= v <= L for v, L in zip(g, Ls))
              and not _in_obstacle(g)]
    spec.gauge_ids = gauges
    spec.probe_pts = [tuple(g) for g in gauges]
    # per open side: distance from the NEAREST charge (B21), mirroring
    # core.geometry.stop_dists_3d so timing is sized for the front that
    # reaches the boundary first
    src = spec.burst_points     # the profile's own centre with no charges
    side_d = {s: min(d(c) for c in src) for s, d in (
        ('x_lo', lambda c: c[0]), ('x_hi', lambda c: Ls[0] - c[0]),
        ('y_lo', lambda c: c[1]), ('y_hi', lambda c: Ls[1] - c[1]),
        ('z_lo', lambda c: c[2]), ('z_hi', lambda c: Ls[2] - c[2]))}
    opens = [d for s, d in side_d.items()
             if normalize_bc(case.bcs.get(s)) != 'reflect']
    corners = [(cx, cy, cz) for cx in (0.0, Ls[0])
               for cy in (0.0, Ls[1]) for cz in (0.0, Ls[2])]
    far = max(math.sqrt((cx - x0) ** 2 + (cy - y0) ** 2
                        + (cz - z0) ** 2) for cx, cy, cz in corners)
    est = min(opens) if opens else far
    spec.end_time, spec.write_interval, spec.cap_is_end = _timing(
        case, max(Ls), est, case.n_snapshots)
    _apply_budget(spec, case)
    return spec


# ── blockMeshDict ───────────────────────────────────────────────────────────

def _bmd(vertices, block_line, boundary, convert=1):
    body = block({
        'convertToMeters': convert,
        'vertices': [tuple(v) for v in vertices],
        'blocks': [Raw(block_line)],
        'edges': Raw('( )'),
        'boundary': boundary,
        'mergePatchPairs': Raw('( )'),
    })
    return foam_file('blockMeshDict', body)


def _patch_type(kind):
    """OpenFOAM patch type for one boundary kind. The three T50 kinds
    map onto the same two OpenFOAM types the pre-T50 names did (a
    terminate side is an outflow patch; the run-ending part is ours, not
    the solver's), and the legacy spellings stay accepted - so a written
    case is byte-identical either way."""
    return dict(reflect='wall', wall='wall',
                transmit='patch', terminate='patch', open='patch',
                empty='empty', wedge='wedge')[kind]


def _blockmesh_1d(spec):
    """Spherical sector along +x (mappedBuilding3D/sector template):
    collapsed hex, apex at the origin, four wedge lateral faces."""
    R = spec.grid['r_face'][-1]
    a = math.radians(HALF_ANGLE_DEG)
    c, s = R * math.cos(a), R * math.sin(a)
    vertices = [(0, 0, 0), (c, -s, -s), (c, s, -s), (c, -s, s), (c, s, s)]
    boundary = [
        ('wedge0', {'type': 'wedge', 'faces': [(0, 1, 2, 0)]}),
        ('wedge1', {'type': 'wedge', 'faces': [(0, 3, 4, 0)]}),
        ('wedge2', {'type': 'wedge', 'faces': [(0, 2, 4, 0)]}),
        ('wedge3', {'type': 'wedge', 'faces': [(0, 1, 3, 0)]}),
        ('outlet', {'type': _patch_type(spec.patches[0][1]),
                    'faces': [(1, 2, 4, 3)]}),
    ]
    line = (f'hex (0 1 2 0 0 3 4 0) ({spec.nx} 1 1) '
            f'simpleGrading (1 1 1)')
    return _bmd(vertices, line, boundary)


def _blockmesh_2d_axisym(spec, case):
    """1-degree wedge, radial = +x, axial = +y (axisymmetricCharge
    template; the collapsed x=0 face is the axis)."""
    Lx = spec.grid['x_face'][-1]
    Ly = spec.grid['y_face'][-1]
    a = math.radians(HALF_ANGLE_DEG)
    xc, s = Lx * math.cos(a), Lx * math.sin(a)
    vertices = [(0, 0, 0), (xc, 0, -s), (xc, Ly, -s), (0, Ly, 0),
                (xc, 0, s), (xc, Ly, s)]
    boundary = [
        ('y_lo', {'type': _patch_type(case.bcs['y_lo']),
                  'faces': [(0, 1, 4, 0)]}),
        ('x_hi', {'type': _patch_type(case.bcs['x_hi']),
                  'faces': [(1, 2, 5, 4)]}),
        ('y_hi', {'type': _patch_type(case.bcs['y_hi']),
                  'faces': [(3, 2, 5, 3)]}),
        ('wedge0', {'type': 'wedge', 'faces': [(0, 1, 2, 3)]}),
        ('wedge1', {'type': 'wedge', 'faces': [(0, 4, 5, 3)]}),
    ]
    if spec.obstacles:
        boundary.append(('obstacles', {'type': 'wall', 'faces': []}))
    line = (f'hex (0 1 2 3 0 4 5 3) ({spec.nb[0]} {spec.nb[1]} 1) '
            f'simpleGrading (1 1 1)')
    return _bmd(vertices, line, boundary)


def _blockmesh_2d_planar(spec, case):
    """One-cell-thick slab with empty front/back."""
    Lx = spec.grid['x_face'][-1]
    Ly = spec.grid['y_face'][-1]
    zh = spec.dx_base / 2.0
    vertices = [(0, 0, -zh), (Lx, 0, -zh), (Lx, Ly, -zh), (0, Ly, -zh),
                (0, 0, zh), (Lx, 0, zh), (Lx, Ly, zh), (0, Ly, zh)]
    boundary = [
        ('x_lo', {'type': _patch_type(case.bcs['x_lo']),
                  'faces': [(0, 3, 7, 4)]}),
        ('x_hi', {'type': _patch_type(case.bcs['x_hi']),
                  'faces': [(1, 2, 6, 5)]}),
        ('y_lo', {'type': _patch_type(case.bcs['y_lo']),
                  'faces': [(0, 1, 5, 4)]}),
        ('y_hi', {'type': _patch_type(case.bcs['y_hi']),
                  'faces': [(3, 2, 6, 7)]}),
        ('frontAndBack', {'type': 'empty',
                          'faces': [(0, 1, 2, 3), (4, 5, 6, 7)]}),
    ]
    if spec.obstacles:
        boundary.append(('obstacles', {'type': 'wall', 'faces': []}))
    line = (f'hex (0 1 2 3 4 5 6 7) ({spec.nb[0]} {spec.nb[1]} 1) '
            f'simpleGrading (1 1 1)')
    return _bmd(vertices, line, boundary)


def _blockmesh_3d(spec, case):
    """Single uniform hex block (freeField template), six bc patches."""
    Lx = spec.grid['x_face'][-1]
    Ly = spec.grid['y_face'][-1]
    Lz = spec.grid['z_face'][-1]
    vertices = [(0, 0, 0), (Lx, 0, 0), (Lx, Ly, 0), (0, Ly, 0),
                (0, 0, Lz), (Lx, 0, Lz), (Lx, Ly, Lz), (0, Ly, Lz)]
    faces = dict(x_lo=(0, 3, 7, 4), x_hi=(1, 2, 6, 5),
                 y_lo=(0, 1, 5, 4), y_hi=(3, 2, 6, 7),
                 z_lo=(0, 1, 2, 3), z_hi=(4, 5, 6, 7))
    boundary = [(side, {'type': _patch_type(case.bcs[side]),
                        'faces': [faces[side]]})
                for side in ('x_lo', 'x_hi', 'y_lo', 'y_hi',
                             'z_lo', 'z_hi')]
    if spec.obstacles:
        # zero-face wall patch: subsetMesh -patch adds the faces the
        # obstacle carve exposes (the patch must pre-exist)
        boundary.append(('obstacles', {'type': 'wall', 'faces': []}))
    line = (f'hex (0 1 2 3 4 5 6 7) ({spec.nb[0]} {spec.nb[1]} '
            f'{spec.nb[2]}) simpleGrading (1 1 1)')
    return _bmd(vertices, line, boundary)


def _toposetdict(spec):
    """cellSet 'fluid' = everything OUTSIDE the obstacle boxes (one
    boxToCell per box, then invert); subsetMesh keeps this set and
    routes the exposed faces onto the 'obstacles' wall patch.

    2D rectangles become z-unbounded boxes: wedge and slab cell
    centres both sit at z = 0, so a symmetric z-span covering the
    whole mesh selects exactly the (x, y) footprint."""
    if spec.dim == 2:
        zpad = float(spec.grid['x_face'][-1])
        boxes = [(x0, x1, y0, y1, -zpad, zpad)
                 for x0, x1, y0, y1 in spec.obstacles]
    else:
        boxes = spec.obstacles
    acts = []
    for i, (x0, x1, y0, y1, z0, z1) in enumerate(boxes):
        acts.append(Raw(
            '{ name fluid; type cellSet; action %s; '
            'source boxToCell; '
            'sourceInfo { box (%s %s %s) (%s %s %s); } }'
            % ('new' if i == 0 else 'add',
               fmt(x0), fmt(y0), fmt(z0), fmt(x1), fmt(y1), fmt(z1))))
    acts.append(Raw('{ name fluid; type cellSet; action invert; }'))
    return foam_file('topoSetDict', block({'actions': acts}),
                     location='system')


def _refine_dicts(spec, case):
    """One topoSet + refineMesh dict pair per level: pass l selects every
    cell whose centre lies in a zone of level >= l (zones are snapped to
    level-(l-1) faces so the selection is whole cells) and halves it in
    the in-plane (2D) or all three (3D) directions. Directions are the
    global e1/e2/e3 of OpenFOAM-9's refineMesh; the wedge normal (e3)
    is never refined in 2D. hexRef8 (useHexTopology + 3 directions)
    gives exact 1:8 splits in 3D; the 2-direction cutter halves hexes at
    their midpoints."""
    files = {}
    if spec.dim == 2:
        zpad = float(spec.grid['x_face'][-1])
    for lv in range(1, spec.lmax + 1):
        acts = []
        for z in spec.zones:
            if refine.zone_level(z) < lv:
                continue
            if spec.dim == 2:
                x0, x1, y0, y1 = z[:4]
                z0, z1 = -zpad, zpad
            else:
                x0, x1, y0, y1, z0, z1 = z[:6]
            acts.append(Raw(
                '{ name refine%d; type cellSet; action %s; '
                'source boxToCell; '
                'sourceInfo { box (%s %s %s) (%s %s %s); } }'
                % (lv, 'new' if not acts else 'add',
                   fmt(x0), fmt(y0), fmt(z0), fmt(x1), fmt(y1), fmt(z1))))
        files[f'system/topoSetDict.refine{lv}'] = foam_file(
            'topoSetDict', block({'actions': acts}), location='system')
        three = spec.dim == 3
        files[f'system/refineMeshDict.{lv}'] = foam_file(
            'refineMeshDict', block({
                'set': Raw(f'refine{lv}'),
                'coordinateSystem': Raw('global'),
                'globalCoeffs': {'e1': (1, 0, 0), 'e2': (0, 1, 0)},
                'directions': Raw('(e1 e2 e3)' if three else '(e1 e2)'),
                'useHexTopology': three,
                'geometricCut': False,
                'writeMesh': False,
            }), location='system')
    return files


# ── system/ + constant/ dicts ───────────────────────────────────────────────

def _controldict_time(spec, case):
    """controlDict run, time-step and write control: every top-level
    keyword before `functions`, in file order. These are standard
    OpenFOAM-9 controlDict keywords; the blastFoam User Guide v6.0 has no
    section on them (its only controlDict text is the `functions` entry,
    sec. 15, p. 122)."""
    d = {
        'application': 'blastFoam',
        # a profile-initialised stage continues an earlier stage's clock:
        # its state is the blast at t0, so the run starts there and every
        # gauge/frame time the user sees stays on one physical timeline
        # (the native solvers do the same with the remap's t0). N7/T41.
        'startFrom': 'startTime' if not spec.t_start else 'latestTime',
        'startTime': spec.t_start,
        'stopAt': 'endTime',
        'endTime': spec.t_start + spec.end_time,
        'deltaT': Raw('1e-7'),
        # overwritten below when the case asks for a fixed step
        'writeControl': 'adjustableRunTime',
        'writeInterval': spec.write_interval,
        'cycleWrite': 0,
        # binary halves write size and Python parse time; 1D stays
        # ascii (~10^3 cells, debuggability wins). The reader sniffs
        # the format per file, so both coexist.
        'writeFormat': 'ascii' if spec.dim == 1 else 'binary',
        'writePrecision': 6,
        'writeCompression': 'off',
        'timeFormat': 'general',
        'timePrecision': TIME_PRECISION,
        'runTimeModifiable': 'true',
        'adjustTimeStep': 'yes',
        'maxCo': case.cfl,
        'maxDeltaT': 1,
        # stop requests rewrite this file to `stopAt writeNow`; the
        # default 10 s fileModificationSkew can swallow that edit
        # forever (a fixed mtime never clears the skew window), so
        # tighten it to 1 s for this case. (inotify would be cleaner
        # but this OpenFOAM build lacks FOAM_USE_INOTIFY; the WSL-side
        # sed rewrite guarantees a fresh native mtime.)
        'OptimisationSwitches': {
            'fileModificationChecking': 'timeStampMaster',
            'fileModificationSkew': 1,
        },
    }
    # A QUIESCENT VERIFICATION CASE CANNOT USE A COURANT-CONTROLLED
    # STEP. blastFoam takes Co from the face fluxes, so a field that is
    # exactly uniform and exactly at rest has Co = 0 and
    # `Time::adjustDeltaT` divides by it - a SIGFPE on the first step,
    # measured. Falsy by default, so every golden is untouched.
    _dt = float(getattr(case, 'fixed_dt', 0.0) or 0.0)
    if _dt > 0.0:
        d['deltaT'] = Raw(fmt(_dt))
        d['adjustTimeStep'] = 'no'
        d['writeControl'] = 'runTime'
    return d


def _controldict_function_objects(spec):
    """The blastFoam function objects of the controlDict `functions`
    entry (blastFoam User Guide v6.0, sec. 15, pp. 122-126), in file
    order: conservedQuantities (sec. 15.4, p. 124), writeTimeList
    (sec. 15.3, p. 124), impulse (sec. 15.11, p. 126), fieldMinMax
    (sec. 15.2, p. 123), timeOfArrival (sec. 15.12, p. 126), overpressure
    (sec. 15.10, p. 126). blastProbes (sec. 15.1) is rendered last, by
    `_controldict_probes`."""
    functions = {}
    # N5-5: blastFoam's own volume integral of the conserved variables,
    # printed to the log at every write. The value here is NOT the drift
    # it reports: the guide says the FO "does not consider the removal
    # and injection of values into a domain", and every default case in
    # this repo has a transmit/terminate boundary, so mass and energy
    # legitimately leave and any drift threshold would either never fire
    # or fire always. What earns its place is the FIRST reading - what
    # blastFoam decoded from the fields we wrote into the start time
    # dir. That is exactly the seam B0 (lambda reset the products to
    # pRef) and B1 (+33 % from the wrong EOS) both broke, and neither
    # was visible from the Python side, which only ever sees what it
    # MEANT to write. Emitted for every dim - it costs one dict entry
    # and a line of log per write.
    # executeControl, NOT writeControl: conservedQuantities does its
    # integral and its Info<< in execute(), and its write() is a bare
    # `return true` (conservedQuantities.C:167). Left on the default
    # timeStep cadence it prints eight lines EVERY step - measured on a
    # 5 s 1D run: the teed log went from 0.22 MB to 7.63 MB, 35x, for
    # 10,531 samples nobody reads.
    functions['conserved'] = {
        'type': 'conservedQuantities',
        'libs': Raw('("libblastFunctionObjects.so")'),
        'executeControl': 'writeTime',
        'writeControl': 'writeTime',
        'fields': ['rho', 'rhoE'],
    }
    # T62 family: guarantee a write at the exact end time. writeInterval
    # is transit-sized and runtime-adapted (the backend doubles it up to
    # 8x mid-run), so endTime is NOT otherwise a write multiple - the
    # last frame, and with it a chain's hand-off surface, could land up
    # to one adapted interval short of the requested t_end, silently
    # discarding computed tail. The FO clips dt to land on the listed
    # time (timeToNextWrite) and forces the write via Time::writeNow
    # (writeTimeList.C:92-107); the dir it writes is named by the same
    # timeFormat/timePrecision the chain's tfmt mirrors, so the next
    # stage reads the seam it was promised. A time the run never
    # reaches (early shock-arrival stop) simply never fires.
    functions['writeTimes'] = {
        'type': 'writeTimeList',
        'libs': Raw('("libblastFunctionObjects.so")'),
        'times': [spec.t_start + spec.end_time],
    }
    if spec.dim >= 2 and spec.fo_accumulators:
        # Per-step peak-pressure / impulse accumulation on the foam side
        # (matches the native solvers' per-step tracking; the backend's
        # Python per-write accumulators remain as a fallback). Field
        # names written per time dir: 'pMax' and 'impulse'.
        functions['impulse'] = {
            'type': 'impulse',
            'libs': Raw('("libblastFunctionObjects.so")'),
            'writeControl': 'writeTime',
            'pName': 'p',
            'pRef': P_AIR,
        }
        functions['pMax'] = {
            'type': 'fieldMinMax',
            'libs': Raw('("libblastFunctionObjects.so")'),
            'writeControl': 'writeTime',
            'fields': ['p'],
            'minMax': 'max',
        }
    # N5-9: the third of the three standard blast outputs. peak (pMax)
    # and impulse were already here; arrival time was not, and it is
    # what the gauge summary reconstructs in Python from the traces.
    # `overpressure` is p - pRef as a field, which is what the probes
    # and the impulse FO are really about - guide 16.5 notes that
    # calculateImpulse detects an overpressure file and then zeroes its
    # own pRef, and burstingWindow_workshop samples it directly.
    if spec.dim >= 2:
        functions['arrival'] = {
            'type': 'timeOfArrival',
            'libs': Raw('("libblastFunctionObjects.so")'),
            'writeControl': 'writeTime',
            'pName': 'p',
        }
        functions['overpressure'] = {
            'type': 'overpressure',
            'libs': Raw('("libblastFunctionObjects.so")'),
            'writeControl': 'writeTime',
            'pRef': P_AIR,
            'store': True,
        }
    return functions


def _controldict_amr_fields(spec):
    """The function object an adaptively refined mesh needs in the
    controlDict: per-write cell centres (OpenFOAM's writeCellCentres).
    AMR itself is configured in constant/dynamicMeshDict
    (`_dynamicmeshdict`; blastFoam User Guide v6.0, ch. 11, p. 106), and
    so is load balancing (sec. 11.2, p. 112) - nothing of either lives
    in the controlDict."""
    functions = {}
    if spec.dim >= 2 and spec.amr:
        # AMR (N16): the cell count and order change every write, so
        # each time dir carries its own cell centres (this FO) next to
        # the refiner's `cellLevel` (dumpLevel); the backend rebuilds
        # the display remap from the pair.
        functions['cellCentres'] = {
            'type': 'writeCellCentres',
            'libs': Raw('("libfieldFunctionObjects.so")'),
            'writeControl': 'writeTime',
        }
    return functions


def _controldict_live_sampling(spec, case):
    """The live-view samplers: a p plane cut (`LIVE_SLICE`, 2D/3D) or a
    p(r) line (`LIVE_SET`, 1D), every few solver steps. OpenFOAM's own
    sampling-library function objects, which blastFoam loads by default
    (blastFoam User Guide v6.0, sec. 15, p. 122)."""
    functions = {}
    if spec.dim >= 2:
        # live p slice every few steps (same role as the 1D liveLine):
        # 2D cuts the z=0 mid-plane (the whole field, one face per
        # cell); 3D cuts the user's live-slice plane through the
        # nearest cell-centre layer. interpolate/triangulate off keep
        # one uncut face per cell with the cell value, so the backend
        # sorts the raw rows straight onto the grid. On an AMR mesh the
        # rows carry no cell size, but a hex-refined cell's centre pins
        # its level (refine.levels_from_centres), so the backend tiles
        # them onto the display grid like a written mesh.
        if spec.dim == 2:
            pt, nrm = (0.0, 0.0, 0.0), (0, 0, 1)
        else:
            axis = getattr(case, 'slice_axis', 'y') or 'y'
            ax_i = 'xyz'.index(axis)
            c = spec.grid[('x_c', 'y_c', 'z_c')[ax_i]]
            pos = (spec.center[ax_i]
                   if getattr(case, 'slice_pos', None) is None
                   else float(case.slice_pos))
            s0 = min(range(len(c)), key=lambda i: abs(float(c[i]) - pos))
            pos = float(c[s0])
            if spec.amr and spec.display_level < spec.amr:
                # cells finer than the display grid have faces at the
                # display-layer centre: cut through the centre of the
                # first finest-level sub-layer instead (a half-odd
                # multiple of the finest cell never lies on a face of
                # any level); in-plane centres are unaffected
                pos += (spec.dx_base / 2 ** spec.amr - spec.dx) / 2.0
            pt = tuple(pos if a == ax_i else 0.0 for a in range(3))
            nrm = tuple(1 if a == ax_i else 0 for a in range(3))
        functions[LIVE_SLICE] = {
            'type': 'surfaces',
            'libs': Raw('("libsampling.so")'),
            'writeControl': 'timeStep',
            'writeInterval': spec.live_steps or live_sample_steps(spec.dim),
            'surfaceFormat': 'raw',
            'interpolationScheme': 'cell',
            'fields': ['p'],
            'surfaces': [('slice', {
                'type': 'plane',
                'planeType': 'pointAndNormal',
                'pointAndNormalDict': {'point': pt, 'normal': nrm},
                'interpolate': False,
                'triangulate': False,
            })],
        }
    if spec.dim == 1:
        # Live p(r) profile every few solver steps: full time dirs
        # only appear once per writeInterval (hundreds of steps at
        # near-field dt), far too sparse for the live view. The
        # backend tails these tiny raw .xy dumps for hooks.frame and
        # deletes each one once consumed.
        functions[LIVE_SET] = {
            'type': 'sets',
            'libs': Raw('("libsampling.so")'),
            'writeControl': 'timeStep',
            'writeInterval': spec.live_steps or live_sample_steps(spec.dim),
            'setFormat': 'raw',
            'interpolationScheme': 'cell',
            'fields': ['p'],
            # endpoints a quarter-cell inside the apex/outlet: exact
            # boundary points spawn 'Particle ... outside of the mesh'
            # warnings from the set's tracking seeds; the line still
            # crosses every cell
            'sets': [('line', {
                'type': 'lineCell',
                'axis': 'x',
                'start': (0.25 * spec.dx, 0.0, 0.0),
                'end': (spec.grid['r_face'][-1] - 0.25 * spec.dx,
                        0.0, 0.0),
            })],
        }
    return functions


def _controldict_probes(spec):
    """The gauge probes: blastProbes (blastFoam User Guide v6.0,
    sec. 15.1, pp. 122-123), the last function object in the file."""
    functions = {}
    if spec.probe_pts:
        functions['gauges'] = {
            'type': 'blastProbes',
            'writeControl': 'timeStep',
            'writeInterval': 1,
            'adjustLocations': spec.probe_adjust,
            'append': 'yes',
            'probeLocations': [tuple(p) for p in spec.probe_pts],
            # p drives every existing consumer; U and rho are the T44
            # extras (velocity-magnitude + density gauge traces, N12)
            'fields': ['p', 'U', 'rho'],
        }
    return functions


def _controldict(spec, case):
    """system/controlDict: the time/write control, then the `functions`
    entry assembled section by section in the order the file has always
    had (docs/ARCHITECTURE_REVIEW.md section 5, Phase 10)."""
    d = _controldict_time(spec, case)
    functions = {}
    functions.update(_controldict_function_objects(spec))
    functions.update(_controldict_amr_fields(spec))
    functions.update(_controldict_live_sampling(spec, case))
    functions.update(_controldict_probes(spec))
    if functions:
        d['functions'] = functions
    return foam_file('controlDict', block(d), location='system')


def _fvschemes(afterburn='none'):
    """Schemes for the case. An afterburn model transports its own burn
    fraction c.<phase>, which needs its div/reconstruct entries - added
    only when the model is on, so unrefined/unafterburnt cases render
    exactly as before."""
    div = {
        'default': 'none',
        f'div(alphaRhoPhi.{PHASE},lambda.{PHASE})': 'Riemann',
    }
    if afterburn != 'none':
        div[f'div(alphaRhoPhi.{PHASE},c.{PHASE})'] = 'Riemann'
    body = block({
        'fluxScheme': FLUX_SCHEME,
        'ddtSchemes': {'default': 'Euler', 'timeIntegrator': 'RK2SSP'},
        'gradSchemes': {'default': Raw('cellMDLimited leastSquares 1.0')},
        'divSchemes': div,
        'laplacianSchemes': {'default': Raw('Gauss linear corrected')},
        'interpolationSchemes': {
            'default': 'cubic',
            'reconstruct(alpha)': 'vanAlbada',
            'reconstruct(rho)': 'vanAlbada',
            'reconstruct(U)': 'vanAlbadaV',
            'reconstruct(e)': 'vanAlbada',
            'reconstruct(p)': 'vanAlbada',
            'reconstruct(speedOfSound)': 'vanAlbada',
            f'reconstruct(lambda.{PHASE})': 'vanAlbada',
            **({f'reconstruct(c.{PHASE})': 'vanAlbada'}
               if afterburn != 'none' else {}),
        },
        'snGradSchemes': {'default': 'corrected'},
    })
    return foam_file('fvSchemes', body, location='system')


def _fvsolution():
    body = block({
        'solvers': {'"(rho|rhoU|rhoE|alpha|.*)"': {'solver': 'diagonal'}},
    })
    return foam_file('fvSolution', body, location='system')


def _setfieldsdict(spec, case):
    alpha = f'alpha.{PHASE}'
    m = MATERIALS[spec.material]

    def radius_k(r):
        """N5-2: multiplier that makes the marked staircase hold the
        mass the user asked for. setFields marks WHOLE cells, so the
        deposited mass is the staircase volume x rho0 - measured across
        representative cases at 0.98-1.05 of the request, scattering
        with where the charge centre happens to fall between cell
        centres. `scale` (massToCell.C:83) multiplies the source's
        VOLUME before it derives the radius, which cancels that while
        leaving alpha at 1 and rho at rho0."""
        from ...core.refine import mass_radius_scale
        if not r:
            return 1.0
        g = spec.grid
        try:
            if spec.dim == 1:
                dims, cen = (g['r_face'][-1],), (0.0, 0.0)
            elif spec.dim == 2:
                dims = (g['x_face'][-1], g['y_face'][-1])
                cen = (0.0 if case.geometry == 'axisymmetric'
                       else spec.center[0], spec.center[1])
            else:
                dims = (g['x_face'][-1], g['y_face'][-1], g['z_face'][-1])
                cen = tuple(float(v) for v in spec.center[:3])
            return mass_radius_scale(
                spec.dim, getattr(case, 'geometry', ''),
                spec.dx_charge, r, cen, dims)
        except (ValueError, ZeroDivisionError, IndexError, KeyError):
            return 1.0     # an odd geometry keeps the vendor behaviour

    def backup_radius(r):
        # the backup region catches the coarse cells around the charge
        # when none has its centre inside it. The static grid resolves
        # the charge, so 2 r always hits; an AMR base cell may be far
        # coarser than the charge - guarantee the cell holding the
        # centre (half-diagonal 0.87 dx in 3D), then setRefinedFields
        # refines from there and re-selects with the true radius
        return max(2.0 * r, 0.9 * spec.dx_base) if spec.amr else 2.0 * r

    if not spec.charges:
        # profile-initialised stage (N7): the state is already in 0/,
        # there is no charge sphere to mark and setRefinedFields is not
        # run at all (it would reset alpha to the default value)
        regions = []
    elif spec.dim == 2 and case.geometry == 'planar':
        x0, y0, _ = spec.center
        if spec.amr:
            # mass-based cylinder through the slab (per-metre charge x
            # slab thickness) - the only planar source with a backup
            # region, which the coarse AMR base grid needs
            mass = float(case.charge) * spec.dx_base
            regions = [('cylindericalMassToCell', {
                'centre': (x0, y0, 0.0),
                'rho': m.rho0,
                'mass': mass,
                'scale': radius_k(spec.r_exp) ** 3,
                'LbyD': spec.dx_base / (2.0 * spec.r_exp),
                'direction': (0, 0, 1),
                'backup': {'centre': (x0, y0, 0.0),
                           'radius': backup_radius(spec.r_exp),
                           'L': (0.0, 0.0, spec.dx_base)},
                'fieldValues': [Raw(f'volScalarFieldValue {alpha}    1')],
            })]
        else:
            regions = [('cylinderToCell', {
                'p1': (x0, y0, -spec.dx_base),
                'p2': (x0, y0, spec.dx_base),
                'radius': spec.r_exp * radius_k(spec.r_exp),
                'fieldValues': [Raw(f'volScalarFieldValue {alpha}    1')],
            })]
    else:
        regions = [('sphericalMassToCell', {
            'centre': centre,
            'rho': m.rho0,
            'mass': mass,
            'scale': radius_k(charge_radius(mass, m)) ** 3,
            'backup': {'centre': centre,
                       'radius': backup_radius(charge_radius(mass, m))},
            'fieldValues': [Raw(f'volScalarFieldValue {alpha}    1')],
        }) for centre, mass in spec.charges]
    d = {
        'fields': [alpha],
        'nBufferLayers': 1,
    }
    if spec.amr:
        # setRefinedFields (run WITHOUT -noRefine for AMR cases) refines
        # the charge region to this level at t = 0 and writes the
        # hexRef cellLevel the run-time refiner continues from
        d['maxRefinement'] = spec.amr
    d.update({
        'defaultFieldValues': [Raw(f'volScalarFieldValue {alpha} 0')],
        'regions': regions,
    })
    return foam_file('setFieldsDict', block(d), location='system')


#: Seed radius for `initiation.radii`, in cells of the mesh AT THE
#: DETONATION POINT. Must clear the corner case and stay under the
#: centre case:
#:   point on a cell corner - the adjacent centres sit at sqrt(2)/2 =
#:     0.707 dx (2D) and sqrt(3)/2 = 0.866 dx (3D), all equidistant, so
#:     a radius below that ignites NOTHING and blastFoam aborts with
#:     "No cells will be activated"
#:   point at a cell centre - the nearest neighbour centre is at 1.0 dx,
#:     so a radius at or above that would drag the neighbours in too
#: 0.9 sits between 0.866 and 1.0 with margin at both ends.
DET_RADIUS_CELLS = 0.9


def default_det_radius(spec):
    """Ignition seed radius [m] written when the case sets no `det_radii`.

    WHY THIS IS A DEFAULT (reverify, 20.09). With `radius_ = 0`,
    `detonationPoint::check`/`setActivated` take the `mesh.findCell`
    branch, and `findCell` is not decomposition-invariant for a point
    that lies on a cell face, edge or corner: `tetrahedron::inside` is
    inclusive on the shared plane, so every rank whose partition touches
    the point claims a cell of its own, and the reduction guards only
    `== 0`, never `> 1`. Measured on a uniform 160x160 planar case with
    the point on an interior corner: serial ignites 1 cell, `simple
    (2 1 1)` ignites 2, `simple (2 2 1)` and `scotch np=4` ignite 4 -
    one per rank - and `sum(lambda)` holds that N-fold ratio to endTime,
    so the extra initiation energy does not wash out.

    The `radius_ > small` branch instead tests cell CENTRES
    (`mag(mesh.C()[celli] - pt) < radius_`), and every cell centre lives
    on exactly one rank, so it is partition-invariant BY CONSTRUCTION,
    not merely by measurement. Measured parallel-vs-serial at the gauge:
    +0.006 % peak and 0.000 % on impulse and arrival, against +1.5 %
    peak for the `findCell` path.

    Exposure is not hypothetical: 117 of 140 detonation points in cases
    blastlab has actually written sit on at least one cell face, both
    shipped defaults land on a node (Case3D gives 0.75 = 39*dx on all
    three axes, a node shared by 8 cells), and 4 of 4 real 3D production
    runs at the default `scotch` np=2 have the point owned by two ranks.

    COST, stated plainly: this changes results. On the measured case the
    serial peak moves 19914 -> 19607 kPa (-1.5 %), because a ball of
    radius ~dx around a corner point seeds the 4 cells meeting there
    rather than the one cell `findCell` happened to pick. That is a
    deterministic physical region replacing an arbitrary choice, and it
    is the same in serial and in parallel - but it is NOT byte-compatible
    with results produced before 20.09.

    The radius follows the mesh at the charge, not the base mesh: both
    static refinement (`lmax`) and AMR (`amr`, realised at t = 0 by
    `setRefinedFields`) shrink the cells there, and a base-cell radius
    would seed 2**(dim*level) refined cells instead of a handful.
    """
    level = max(int(getattr(spec, 'lmax', 0) or 0),
                int(getattr(spec, 'amr', 0) or 0))
    dx_base = float(getattr(spec, 'dx_base', 0.0) or 0.0) or float(spec.dx)
    return DET_RADIUS_CELLS * dx_base / (2.0 ** level)


def _chamber_phaseproperties(spec, cs):
    """HD1-3b: both phases INERT ideal gases.

    The gas in a vented magazine is combustion products that have
    finished reacting on any timescale the CFD resolves, so there is
    nothing to detonate and nothing to burn. The guide (5.5, p. 68)
    gives `type basic` for exactly that, and it costs nothing here: the
    phase keeps its name, so none of the twelve places that hard-code
    `alpha.expl` / `rho.expl` change.

    AND IT IS NOT AIR, which is the mistake this dictionary exists to
    prevent. `gamma` and `molWeight` come from the propellant - measured
    on the shipped double-base row, 1.24 and 22.7 g/mol against air's
    1.40 and 28.97. Writing air instead would be wrong twice: 1.67x on
    the internal energy at the same p and V, and +17.9 % on the choked
    mass flow through the opening. The 2-D verification is
    pre-registered at 15 %, so the second one would have passed it and
    been absorbed into the discharge coefficient.

    BUG B0 CANNOT HAPPEN HERE, structurally rather than by care. The
    comment at the profile branch explains that `lambda.expl` must be
    written or blastFoam blends already-reacted products back to
    unreacted Murnaghan reactants. A `basic` phase has no reactant side
    and no `lambda` at all, so the trap does not exist - which is why
    the caller's lambda assertion is skipped for a chamber case rather
    than satisfied by writing a field the solver would ignore.
    """
    gamma = float(cs['gamma_p'])
    molw = float(cs['mol_weight_p'])
    # Cv from the two the state already carries, so the dictionary
    # cannot disagree with the EOS the hand-off priced itself with:
    # R = 8314.46/M and Cv = R/(gamma - 1).
    R = 8314.46261815324 / molw
    body = block({
        'phases': [PHASE, 'air'],
        'radiationModel': 'none',
        PHASE: {
            'type': 'basic',
            'thermoType': {'transport': 'const', 'thermo': 'eConst',
                           'equationOfState': 'idealGas'},
            'equationOfState': {'gamma': gamma},
            'specie': {'molWeight': molw},
            'transport': {'mu': 0, 'Pr': 1},
            'thermodynamics': {'type': 'eConst', 'Cv': R / (gamma - 1.0),
                               'Hf': 0},
            'residualRho': Raw('1e-6'),
            'residualAlpha': Raw('1e-10'),
        },
        'air': {
            'type': 'basic',
            'thermoType': {'transport': 'const', 'thermo': 'eConst',
                           'equationOfState': 'idealGas'},
            'equationOfState': {'gamma': GAMMA_AIR},
            'specie': {'molWeight': MOLW_AIR},
            'transport': {'mu': 0, 'Pr': 1},
            'thermodynamics': {'type': 'eConst', 'Cv': CV_AIR, 'Hf': 0},
            'residualRho': Raw('1e-6'),
            'residualAlpha': Raw('1e-10'),
        },
    })
    return foam_file('phaseProperties', body, location='constant')


def _phaseproperties(spec, activation='linear', afterburn='none'):
    st = spec.init_state or {}
    if st.get('chamber'):
        return _chamber_phaseproperties(spec, st['chamber'])
    m = MATERIALS[spec.material]
    # 'linear' burns at vDet from the detonation points (tutorial
    # default); 'none' = fully reacted at t0 - the vendor's
    # burstingWindow pattern: initiation carries only E0
    if activation == 'none':
        initiation = {'E0': E0(m)}
    else:
        # P1-3: `det_points or charge centres` used to fall through to an
        # EMPTY list on a profile-initialised stage (N7), which has no
        # charge list on purpose - the same missing-fallback shape that
        # made T62's three blockers. Here the empty list is DELIBERATE and
        # must stay: that stage's material arrives already reacted from
        # the previous stage, so there is nothing to light, and lighting
        # the profile's centre (spec.burst_points) would detonate it a
        # second time. What must never be silent is the other way round -
        # a charge case that somehow reaches this with nothing to light.
        points = spec.det_points or [c for c, _mass in spec.charges]
        if not points and spec.charges:
            raise ValueError(
                'no detonation points for a charge case: '
                f'{len(spec.charges)} charge(s) but neither det_points nor '
                'their centres survived - refusing to write a '
                'phaseProperties that would never ignite')
        initiation = {
            'E0': E0(m),
            'points': points,
            'vDet': m.vDet,
        }
        # N5-12: per-point timing and ignition radius (guide 5.6.1,
        # the delayedDetonation tutorial's pattern).
        delays = getattr(spec, 'det_delays', None)
        if delays:
            initiation['delays'] = [float(v) for v in delays]
        # reverify/20.09: `radii` is now written BY DEFAULT, not only when
        # the case asks for it. See default_det_radius() for why.
        radii = [float(v) for v in (getattr(spec, 'det_radii', None) or ())]
        if points and not radii:
            radii = [default_det_radius(spec)] * len(points)
        if points and radii:
            initiation['radii'] = radii
        if activation == 'programmedIgnition':
            # guide 5.6.1.3: Giroux. programmedBeta = the compression
            # switch AND the programmed vDet/(1.5 dx) rate, whichever
            # is further along - the guide's own recommended pairing.
            initiation['Pcj'] = m.Pcj
            initiation['burnModel'] = 'programmedBeta'
    body = block({
        'phases': [PHASE, 'air'],
        'radiationModel': 'none',
        PHASE: {
            'type': 'detonating',
            'reactants': {
                'thermoType': {'transport': 'const', 'thermo': 'eConst',
                               'equationOfState': 'Murnaghan'},
                'equationOfState': {'rho0': m.rho0,
                                    'Gamma': m.Gamma_reactants,
                                    'pRef': P_AIR, 'K0': 0},
                'specie': {'molWeight': m.molWeight},
                'transport': {'mu': 0, 'Pr': 1},
                'thermodynamics': {'Cv': m.Cv_reactants, 'Hf': 0.0},
            },
            'products': {
                'thermoType': {'transport': 'const', 'thermo': 'eConst',
                               'equationOfState': 'JWL'},
                'equationOfState': {'rho0': m.rho0, 'A': m.A, 'B': m.B,
                                    'R1': m.R1, 'R2': m.R2,
                                    'omega': m.omega},
                'specie': {'molWeight': m.molWeight},
                'transport': {'mu': 0, 'Pr': 1},
                'thermodynamics': {'Cv': m.Cv_products, 'Hf': 0.0},
            },
            'activationModel': activation,
            'initiation': initiation,
            # afterburn: products burning with atmospheric oxygen
            # (Miller model; keys read straight from this phase dict)
            **_afterburn_entries(spec, afterburn),
            'residualRho': Raw('1e-6'),
            'residualAlpha': Raw('1e-10'),
        },
        'air': {
            'type': 'basic',
            'thermoType': {'transport': 'const', 'thermo': 'eConst',
                           'equationOfState': 'idealGas'},
            'equationOfState': {'gamma': GAMMA_AIR},
            'specie': {'molWeight': MOLW_AIR},
            'transport': {'mu': 0, 'Pr': 1},
            'thermodynamics': {'type': 'eConst', 'Cv': CV_AIR, 'Hf': 0},
            'residualRho': Raw('1e-6'),
            'residualAlpha': Raw('1e-10'),
        },
    })
    return foam_file('phaseProperties', body, location='constant')


def _afterburn_entries(spec, afterburn):
    """`afterburnModel` + its coefficients for the detonating phase
    ({} when off - the dict then renders exactly as before)."""
    if afterburn == 'none':
        return {}
    ab = AFTERBURN[spec.material]
    return {'afterburnModel': 'Miller', 'Q0': ab.Q0, 'a': ab.a,
            'n': ab.n, 'm': ab.m, 'pMin': ab.pMin}


def _unrefine_hold(spec):
    """Time to hold unrefinement until, in seconds (N5-13).

    The last detonation point has to have lit AND its burn crossed the
    charge before the mesh is allowed to coarsen anywhere. That is the
    largest per-point delay plus the time the detonation front needs to
    cross the charge radius at vDet - a few microseconds for any charge
    this code runs, so it costs a handful of refinement steps and buys
    the refined region staying put through ignition.

    0.0 (blastFoam's own default, and nothing is emitted) for a profile
    stage: its material arrives already reacted, there is no ignition
    to wait for, and holding unrefinement would just pin a mesh the
    run no longer needs.
    """
    if spec.init_state is not None or not spec.charges:
        return 0.0
    m = MATERIALS[spec.material]
    if not m.vDet:
        return 0.0
    burn = float(spec.r_exp) / float(m.vDet)
    delay = max([float(v) for v in (getattr(spec, 'det_delays', None)
                                    or [0.0])] + [0.0])
    return delay + burn


def _dynamicmeshdict(spec=None, case=None):
    """staticFvMesh, or the adaptiveFvMesh block of an AMR case (N16).
    Keys and defaults follow blastFoam 6.2.0's fvMeshRefiner /
    errorEstimator readers (probed 2026-09-05): `lowerRefineLevel`,
    `unrefineLevel` and `maxRefinement` are required, the rest optional;
    `dumpLevel` makes every write carry a `cellLevel` field."""
    if spec is None or not spec.amr:
        return foam_file('dynamicMeshDict',
                         block({'dynamicFvMesh': 'staticFvMesh'}),
                         location='constant')
    est = (getattr(case, 'amr_estimator', 'Lohner')
           or 'Lohner')
    d = {'dynamicFvMesh': 'adaptiveFvMesh', 'errorEstimator': est}
    if est == 'Lohner':
        d['field'] = 'p'
        d['epsilon'] = LOHNER_EPS
    d.update({
        'refineInterval': int(getattr(case, 'amr_interval', 2)),
        'lowerRefineLevel': float(getattr(case, 'amr_refine', 0.4)),
        'unrefineLevel': float(getattr(case, 'amr_unrefine', 0.2)),
        'nBufferLayers': int(getattr(case, 'amr_buffer', 2)),
        'maxRefinement': int(spec.amr),
        'maxCells': (int(getattr(case, 'amr_max_cells', 0) or 0)
                     or FOAM_CELLS_WARN),
        'dumpLevel': True,
    })
    # N5-13: hold the refinement around the charge until it has actually
    # detonated. `beginUnrefine` is a TIME in seconds (fvMeshRefiner.C:588
    # - the guide's own table says "number of time steps", which is wrong;
    # its PDF extraction shuffled the column). Before the charge lights,
    # the error estimator sees a quiet domain and happily coarsens the
    # cells the blast is about to need - which is exactly what the
    # `backup_radius` inflation in _setfieldsdict works around from the
    # Python side. Holding unrefinement past the ignition of the LAST
    # detonation point lets the mesh keep what setRefinedFields gave it.
    begin = _unrefine_hold(spec)
    if begin > 0.0:
        d['beginUnrefine'] = begin
    if spec.n_procs > 1:
        d['loadBalance'] = {
            'balance': bool(AMR_LOAD_BALANCE),
            'balanceInterval': AMR_BALANCE_INTERVAL,
            'allowableImbalance': AMR_ALLOWABLE_IMBALANCE,
        }
    return foam_file('dynamicMeshDict', block(d), location='constant')


def _decomposepardict(n_procs):
    """scotch decomposition (modeled on the building3DWorkshop
    tutorial); written only for parallel runs, so serial case trees
    stay byte-identical.

    N5-7 tried to replace this with a planar (`hierarchical`) split and
    a detonation-point nudge, and BOTH were reverted. The measurements
    are in TODO.md N5-7; the short version is that the pair fixed
    parallel consistency (3D parallel to -0.13 % of serial, 2D np1-vs-np2
    equivalence restored) at the cost of moving SERIAL results: the
    uniform reference in _e2e_foam_amr2d went from 986.3 to 947.3 Pa s
    of positive-phase impulse, a 3.7 % shift, and nothing in the suite
    anchors impulse to say which answer is right.

    The nudge's size turned out to be irrelevant - 1e-6, 1e-5 and 1e-3
    of a cell all give the same 947.3 - so it is not a gradual
    perturbation but a discrete flip: a point exactly on a cell corner
    has its surrounding cells equidistant and igniting together, and
    any offset at all breaks that symmetry. Which of the two states is
    physically right is the open question, and it needs an impulse
    anchor (Kingery-Bulmash publishes impulse as well as peak) rather
    than another opinion.
    """
    body = block({
        'numberOfSubdomains': n_procs,
        'method': 'scotch',
    })
    return foam_file('decomposeParDict', body, location='system')


# ── 0/ field files ──────────────────────────────────────────────────────────

def _bc_entry(fld, kind, p_value='$internalField', l_inf=None):
    """Boundary entry dict for one field on one patch kind.

    `p_value` is what the open-boundary pressure patch takes as its
    `value`. It is `$internalField` for the uniform (charge-init) fields,
    but a profile-initialised case has a NONUNIFORM internalField, and
    expanding that into a patch field would hand blastFoam a list the
    size of the mesh for a patch of a few hundred faces - the run aborts
    in advectiveFvPatchField's Field constructor. Those cases pass an
    explicit ambient value instead (the profile is ambient out there;
    validate_case warns when the shock already reaches a boundary)."""
    if kind == 'wedge':
        return {'type': 'wedge'}
    if kind == 'empty':
        return {'type': 'empty'}
    if kind in ('reflect', 'wall'):
        return {'type': 'slip'} if fld == 'U' else {'type': 'zeroGradient'}
    # transmit / terminate: both are outflow patches
    if fld == 'p':
        # N5-10: `fieldInf`/`lInf` make pressureWaveTransmissive relax
        # back towards ambient over a length scale instead of being a
        # pure advective outflow. Verified optional and only active
        # when lInf > small (pressureWaveTransmissiveFvPatchField.C:134).
        # The vendor tutorials leave them out, so this is measured
        # against the KB anchor before it is trusted - see N5-10 in
        # TODO. `l_inf` is None when the caller has no domain scale to
        # give, and then nothing is emitted and the patch is exactly
        # what it was.
        d = {'type': P_OPEN_BC, 'value': Raw(p_value)}
        if l_inf:
            d['fieldInf'] = P_AIR
            d['lInf'] = l_inf
        return d
    return {'type': 'zeroGradient'}


def _field_file(obj, fld, internal, spec, vector=False):
    bfield = {name: _bc_entry(fld, kind, l_inf=spec.l_inf)
              for name, kind in spec.patches}
    body = block({
        'dimensions': Raw(_DIMS[fld]),
        'internalField': Raw(f'uniform {internal}'),
        'boundaryField': bfield,
    })
    cls = 'volVectorField' if vector else 'volScalarField'
    return foam_file(obj, body, cls=cls)


def _zero_fields(spec):
    m = MATERIALS[spec.material]
    return {
        '0/p': _field_file('p', 'p', fmt(P_AIR), spec),
        '0/T': _field_file('T', 'T', fmt(T_AMB), spec),
        '0/U': _field_file('U', 'U', '(0 0 0)', spec, vector=True),
        f'0/alpha.{PHASE}': _field_file(f'alpha.{PHASE}', 'alpha',
                                        '0', spec),
        f'0/rho.{PHASE}': _field_file(f'rho.{PHASE}', 'rho',
                                      fmt(m.rho0), spec),
        '0/rho.air': _field_file('rho.air', 'rho', fmt(RHO_AIR), spec),
    }


# ── profile-initialised stages (N7) ─────────────────────────────────────────

def _profile_energy(rho, u, v, w, e, spec, case):
    """Total energy of a remapped state on its mesh [J], or None when
    the cell volumes cannot be worked out."""
    V = _init_cell_volumes(spec, case)
    if V is None:
        return None
    ke = 0.5 * (u ** 2 + v ** 2 + (0.0 if w is None else w ** 2))
    return float(np.sum(rho * (e + ke) * V))


def _init_cell_volumes(spec, case):
    """Per-cell volume of the mesh a profile stage's state lands on, in
    the units blastFoam's own volume integrals use (N5-5).

    The shape matches `spec.init_grid`, so it multiplies the remapped
    state directly. The conventions are the ones the blockMesh writers
    above build:
      - axisymmetric: core.grid's V is PER RADIAN; the wedge spans
        2 * HALF_ANGLE_DEG (_blockmesh_2d_axisym), so that is the
        factor between the two.
      - planar 2D: one cell thick, -dx_base/2 .. +dx_base/2
        (_blockmesh_2d_planar).
      - 3D: cubes.
    Returns None for a geometry this cannot account for, so a caller
    reports nothing rather than reporting a wrong number.
    """
    g = spec.init_grid
    try:
        if spec.dim == 3:
            dx = float(g['x_face'][1] - g['x_face'][0])
            return dx ** 3
        dx = float(g['x_face'][1] - g['x_face'][0])
        dy = float(g['y_face'][1] - g['y_face'][0])
        if getattr(case, 'geometry', '') == 'axisymmetric':
            x_c = 0.5 * (g['x_face'][:-1] + g['x_face'][1:])
            wedge = 2.0 * math.radians(HALF_ANGLE_DEG)
            return (x_c * dx * dy * wedge)[:, None]
        return dx * dy * spec.dx_base
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def profile_state(case, spec):
    """Remap a chain stage's input profile onto this case's cell grid.

    Returns dict(rho, u, v, w, e, phase, t0) of arrays shaped like
    `spec.init_grid` - the same remap the native solvers use, so a chain
    hands blastFoam exactly the state a native stage would have started
    from. `w` is None in 2D. `dx_src` is the source profile's own cell
    size, which the banner compares against the mesh the state lands
    on (T70)."""
    from ...core import profiles
    mode = getattr(case, 'init_mode', 'charge')
    path = getattr(case, 'profile_file_in', None)
    if mode == 'chamber':
        return _chamber_state(case, spec)
    if mode == 'charge' or not path:
        return None
    g = spec.init_grid
    if spec.dim == 2:
        prof = profiles.load_profile(path)
        U, phase, t0 = profiles.remap_profile_1d_to_2d(
            prof, g['x_c'], g['y_c'], case.center[1])
        rho = U[0]
        u, v, w = U[1] / rho, U[2] / rho, None
        ke = 0.5 * (u ** 2 + v ** 2)
    elif mode == 'profile2d':
        prof = profiles.load_profile_2d(path)
        U, phase, t0 = profiles.remap_profile_2d_to_3d(
            prof, g['x_c'], g['y_c'], g['z_c'],
            case.center[0], case.center[1])
        rho = U[0]
        u, v, w = U[1] / rho, U[2] / rho, U[3] / rho
        ke = 0.5 * (u ** 2 + v ** 2 + w ** 2)
    else:
        prof = profiles.load_profile(path)
        U, phase, t0 = profiles.remap_profile_1d_to_3d(
            prof, g['x_c'], g['y_c'], g['z_c'], case.center)
        rho = U[0]
        u, v, w = U[1] / rho, U[2] / rho, U[3] / rho
        ke = 0.5 * (u ** 2 + v ** 2 + w ** 2)
    e = U[-1] / rho - ke

    # N2-14, corrected by N5-11: the AMPLIFICATION described below is
    # real, but the near-zero density it acts on is NOT made here. The
    # preserved crashing hand-off
    # (night_artifacts/.../gui_foam/stage2_profile.npz) already carries
    # 20 cells below 1e-3, down to 1.711e-04, in the 2D SOURCE field -
    # blastFoam produced them, and the remap inherits and spreads them
    # (20 -> 72 on a 48^3 grid). So this floor is a guard on state the
    # solver handed over, not on interpolation residue, and the way to
    # be rid of it is to stop the 2D stage producing near-vacuum in the
    # first place. See TODO.md N5-11.
    #
    # The remap interpolates CONSERVED quantities, so u = rhoU/rho
    # and e = rhoE/rho amplify interpolation residue into fabricated
    # state wherever the interpolated rho is near zero. Measured on the
    # preserved crashing stage-3 hand-off (night_artifacts/NIGHT2): 408
    # cells with rho down to 1.6e-6 kg/m3 carrying |U| up to 3.6e4 m/s
    # and T up to 8.3e6 K - and those cells seeded a density runaway that
    # SIGFPE'd blastFoam's decode() (rhoU/rho at rho ~ machine epsilon)
    # in ~6% of chain runs. A cell whose density landed below a physical
    # floor carries no usable information, so it becomes a QUIESCENT,
    # self-consistent thin gas instead: rho at the floor, at rest, at
    # ambient temperature (e = Cv(phase) * 288 K, so _profile_fields's
    # T = e/Cv and the EOS's p come out consistent). Flooring single
    # fields while keeping the fabricated e and U was measured to only
    # postpone the runaway (experiments B1/B2 vs C: the as-is case dies
    # +21 us after hand-off, single-field floors die at +255 us, the
    # full-state replacement survives past +530 us with max(T) six
    # orders of magnitude lower through the original window).
    RHO_MIN = 1e-3                                     # kg/m3
    bad = ~np.isfinite(rho) | (rho < RHO_MIN)
    for a in (u, v, e) + (() if w is None else (w,)):
        bad |= ~np.isfinite(a)
    if np.any(bad):
        m = MATERIALS[spec.material]
        cv = np.where(np.asarray(phase) == 1, m.Cv_products, CV_AIR)
        rho = np.where(bad, RHO_MIN, rho)
        u = np.where(bad, 0.0, u)
        v = np.where(bad, 0.0, v)
        if w is not None:
            w = np.where(bad, 0.0, w)
        e = np.where(bad, cv * 288.0, e)

    # N5-4: the last line of defence. validate_case refuses this at the
    # form (and chain.handoff_conflicts before that), but a hand-written
    # case JSON or a CLI caller reaches the writer directly, and the
    # symptom - a fireball a third too energetic - is not something a
    # user would ever spot in the output. ValueError, not RuntimeError:
    # run_controller.error_headline lifts the first non-indented line
    # out of the traceback, so this shows as a sentence.
    src_solver = str(prof.get('source_solver', 'unknown') or 'unknown')
    if src_solver == 'native':
        from ...core.chain import HANDOFF_MSG
        raise ValueError(HANDOFF_MSG[0].upper() + HANDOFF_MSG[1:])

    return dict(rho=rho, u=u, v=v, w=w, e=e, phase=phase, t0=float(t0),
                # the EOS the SOURCE stage ran with - _profile_fields
                # prices the hand-off with this, never with case.eos
                # (B1). A native stage exports 'idealGas', blastFoam
                # exports 'JWL' (backend.py:1117).
                eos=str(prof.get('eos', 'idealGas') or 'idealGas'),
                source_solver=src_solver,
                # N5-5: the total internal + kinetic energy this
                # state carries onto THIS mesh. Compared against what
                # blastFoam's conservedQuantities reports at the first
                # write, it answers the one question Python cannot ask
                # itself - "did blastFoam decode the fields I wrote as
                # the energy I meant?" - which is the seam B0 and B1
                # both broke.
                E_total=_profile_energy(rho, u, v, w, e, spec, case),
                r_exp=float(prof.get('r_exp', 0.0) or 0.0),
                n_floored=int(np.count_nonzero(bad)),
                dx_src=_source_dx(prof, mode))


def _chamber_state(case, spec):
    """HD1-3b: the room as an initial condition, uniform inside the
    cavity and ambient outside it.

    Same contract as the profile branch above - a dict shaped like
    `spec.init_grid` - and deliberately so, because everything
    downstream of `profile_state` is written against that contract and
    none of it needs to know a chamber from a chain stage. There is no
    interpolation at all here: the state is one number per field inside
    the cavity mask and ambient outside, so no remap kernel is involved
    and none was written.

    WHAT IS NOT DONE HERE, and it is the point of the design. The 0-D
    model has already decided the pressure, temperature and mixture (see
    `core/vent.py`), and `core/room.py` has already decided where the
    walls are. This function only puts the one on the other.
    """
    import numpy as _np
    cs = dict(getattr(case, 'chamber_state', None) or {})
    room = dict(getattr(case, 'room', None) or {})
    if not cs or not room:
        raise ValueError(
            "init_mode 'chamber' needs both `room` (from "
            "core.room.measure) and `chamber_state` (from "
            "core.vent.handoff) - neither is derivable from the other")
    g = spec.init_grid
    lo, hi = room['cavity_lo'], room['cavity_hi']
    # cell CENTRE inside, inclusive - the same criterion the obstacle
    # carve and foam's boxToCell use, so the cavity the state fills is
    # exactly the cavity the walls leave
    ax = [_np.asarray(g[k], dtype=float) for k in ('x_c', 'y_c', 'z_c')]
    inside = _np.ones((ax[0].size, ax[1].size, ax[2].size), dtype=bool)
    for i, a in enumerate(ax):
        shape = [1, 1, 1]
        shape[i] = a.size
        inside &= ((a >= lo[i] - 1e-12) & (a <= hi[i] + 1e-12)
                   ).reshape(shape)

    rho = _np.where(inside, float(cs['rho_mix']), RHO_AIR)
    e = _np.where(inside, float(cs['e_mix']), CV_AIR * 288.0)
    # alpha.expl is the products' VOLUME FRACTION, which in a magazine is
    # nothing like 1: the air that was already in the room carries most
    # of the partial pressure. See core/vent.py on Dalton against volume
    # fractions, and on why m_p/V is the wrong density to pair with it.
    alpha = _np.where(inside, float(cs['alpha_expl']), 0.0)
    zero = _np.zeros_like(rho)
    return dict(
        rho=rho, u=zero, v=zero.copy(), w=zero.copy(), e=e,
        phase=alpha, t0=0.0,
        # Both phases are ideal gases here: the chamber holds combustion
        # products that have finished reacting, so there is no JWL and
        # no reactant side. See `_phaseproperties`.
        eos='idealGas',
        # NOT 'native' - that raises HANDOFF_MSG, and rightly, for a
        # native blast profile. This state came from the 0-D
        # deflagration model, which is a different provenance with a
        # different meaning.
        source_solver='deflagration0d',
        # From the 0-D RESULT, carried through core/vent.py, never
        # recomputed from the numbers written below: computing it from
        # the hand-off would compare the hand-off with itself.
        E_total=float(cs['E']),
        r_exp=0.0, n_floored=0, dx_src=0.0,
        # carried for the report and the goldens, not used by the writer
        chamber=cs, room_volume=float(room['volume']),
        cavity_cells=int(_np.count_nonzero(inside)),
    )


def _source_dx(prof, mode):
    """Cell size of the profile the stage starts from, or 0.0 when it
    cannot be told. The mesh the state lands on should not be much
    coarser than this - see the T70 banner warning."""
    axes = ([prof['r_c'], prof['z_c']] if mode == 'profile2d'
            else [prof['r']])
    out = []
    for a in axes:
        a = np.asarray(a, dtype=float)
        if a.size > 1:
            d = np.diff(a)
            d = d[np.isfinite(d) & (d > 0)]
            if d.size:
                out.append(float(d.min()))
    return min(out) if out else 0.0


def _cell_order(arr, spec):
    """Grid array -> the mesh's cell order: x fastest (F order), and on
    an obstacle-carved mesh only the fluid cells, ascending - the exact
    inverse of reader.to_grid. The grid is `spec.init_grid`, which is
    the base mesh under AMR (T70)."""
    flat = np.asarray(arr).ravel(order='F')
    solid = spec.init_solid
    if solid is not None:
        flat = flat[~np.asarray(solid).ravel(order='F')]
    return flat


def _nonuniform(vals, vector=False):
    """`nonuniform List<scalar|vector> N ( ... )` for an internalField."""
    sep = chr(10)
    if vector:
        rows = ['(' + ' '.join(fmt(float(c)) for c in row) + ')'
                for row in vals]
        kind = 'vector'
    else:
        rows = [fmt(float(x)) for x in vals]
        kind = 'scalar'
    head = 'nonuniform List<' + kind + '>' + sep + str(len(rows))
    return Raw(head + sep + '(' + sep + sep.join(rows) + sep + ')')


def _chamber_fields(spec, case):
    """HD1-3b: 0/ files for a room at pressure with a hole in it.

    A SEPARATE FUNCTION FROM `_profile_fields`, on purpose. That one is
    written for a SHARP two-phase split - the native profile carries one
    mixture density and an integer phase flag, so `alpha` is 0 or 1 and
    every `np.where(phase == 1, ...)` in it is exact. A chamber's alpha
    is a genuine fraction (0.115 on the measured magazine), and every
    one of those comparisons would quietly send every cell down the air
    branch. Generalising them would also put the existing goldens at
    risk for no gain, since the two cases share no EOS: this one is two
    ideal gases, that one is JWL products against air.

    `rho.expl` and `rho.air` are each phase's own density AT THE FULL
    PRESSURE, not the chamber average - see core/vent.py. Outside the
    room both are their ambient values, so the absent phase still has a
    physical density everywhere, which blastFoam requires.
    """
    st = spec.init_state
    cs = st['chamber']
    alpha = st['phase']
    inside = alpha > 0.0
    T_amb = 288.0
    T = np.where(inside, float(cs['T']), T_amb)
    p = np.where(inside, float(cs['p']), P_AIR)
    rho_expl = np.where(inside, float(cs['rho_expl']),
                        P_AIR / (float(cs['R_p']) * T_amb))
    rho_air = np.where(inside, float(cs['rho_air']), RHO_AIR)
    U = np.zeros((spec.n_cells, 3))
    if len(_cell_order(T, spec)) != spec.n_cells:
        raise RuntimeError(
            f'chamber state has {len(_cell_order(T, spec)):,} values for '
            f'a {spec.n_cells:,}-cell mesh - the room grid and the mesh '
            f'disagree')
    fields = {
        '0/p': ('p', 'p', _nonuniform(_cell_order(p, spec)), False),
        '0/T': ('T', 'T', _nonuniform(_cell_order(T, spec)), False),
        '0/U': ('U', 'U', _nonuniform(U, vector=True), True),
        f'0/alpha.{PHASE}': (f'alpha.{PHASE}', 'alpha',
                             _nonuniform(_cell_order(alpha, spec)), False),
        f'0/rho.{PHASE}': (f'rho.{PHASE}', 'rho',
                           _nonuniform(_cell_order(rho_expl, spec)), False),
        '0/rho.air': ('rho.air', 'rho',
                      _nonuniform(_cell_order(rho_air, spec)), False),
        # NO lambda.expl. A `basic` phase has no reactant side to blend
        # back to, so B0 - the bug that makes a profile stage lose its
        # fireball - cannot occur here. See `_chamber_phaseproperties`.
    }
    return _render_fields(fields, spec)


def _profile_fields(spec, case):
    """0/ files for a profile-initialised stage: every field carries the
    remapped state instead of an ambient uniform value.

    The two-phase split is sharp (the native profile carries one mixture
    density and an integer phase flag), so alpha is 0 or 1 and only the
    active phase's density is meaningful in a cell. T is the inverse of
    the reader's `e = Cv(phase) T`, and p comes from the native EOS the
    profile was produced with, so the handover is the same state the
    native solver would have continued from."""
    from ...core.eos import pressure_soundspeed, material_jwl
    st = spec.init_state
    m = MATERIALS[spec.material]
    phase = st['phase']
    rho, e = st['rho'], st['e']
    # B1/B2: the EOS is the one the profile was WRITTEN with, not the
    # one this case runs. `case.eos` is forced to 'idealGas' for every
    # blastFoam case (case_form.py:215, and validate_case says so), so
    # reading it here priced the products' cells with the air formula
    # p = (gamma_air - 1) rho e instead of JWL - a flat +33.3 % in p
    # (the ratio 0.4 / omega_TNT) on every foam->foam hand-off, which
    # 5.9 then inverts back into +33.3 % of internal energy. The
    # material's own JWL set has to come with it: pressure_soundspeed
    # defaults to TNT, which is another 20 % for C4 and 14 % for ANFO.
    p, _c = pressure_soundspeed(rho, e, phase,
                                st.get('eos', 'idealGas'),
                                material_jwl(spec.material))
    Cv = np.where(phase == 1, m.Cv_products, CV_AIR)
    T = e / Cv
    comps = [st['u'], st['v']]
    comps.append(st['w'] if st['w'] is not None else np.zeros_like(rho))
    U = np.stack([_cell_order(c, spec) for c in comps], axis=1)
    # the lists below are read by OpenFOAM against the mesh that exists
    # when they land; a mismatch is a FOAM FATAL three stages later, with
    # a message that names neither the cause nor this file (T70)
    if len(U) != spec.n_cells:
        raise RuntimeError(
            f'profile state has {len(U):,} values for a {spec.n_cells:,}'
            f'-cell mesh - the remap grid and the mesh disagree')
    fields = {
        '0/p': ('p', 'p', _nonuniform(_cell_order(p, spec)), False),
        '0/T': ('T', 'T', _nonuniform(_cell_order(T, spec)), False),
        '0/U': ('U', 'U', _nonuniform(U, vector=True), True),
        f'0/alpha.{PHASE}': (f'alpha.{PHASE}', 'alpha',
                             _nonuniform(_cell_order(
                                 phase.astype(float), spec)), False),
        f'0/rho.{PHASE}': (f'rho.{PHASE}', 'rho', _nonuniform(_cell_order(
            np.where(phase == 1, rho, m.rho0), spec)), False),
        '0/rho.air': ('rho.air', 'rho', _nonuniform(_cell_order(
            np.where(phase == 1, RHO_AIR, rho), spec)), False),
        # B0: the explosive arriving in a profile is ALREADY reacted -
        # it is expanded JWL product gas the previous stage handed over.
        # blastFoam builds lambda.<phase> READ_IF_PRESENT with a default
        # of 0 (activationModel.C:236), and a profile stage writes an
        # empty `points ()` on purpose, so linearActivation never raises
        # it: lambda stays 0 for the whole run. Equation 5.87 then
        # blends the phase back to the UNREACTED Murnaghan reactants,
        # and Murnaghan with K0 = 0 (the vendor's pattern) returns pRef
        # whatever the density is - the entire fireball is silently
        # reset to ambient. Measured on blastFoam 6.2.0: 4.43 MPa in,
        # 101,298 Pa out. `uniform 1` because a profile stage carries no
        # unreacted material anywhere in the domain, and lambda has no
        # meaning in the air cells (alpha.expl = 0) either way.
        # activationModel stays `linear`: with lambda already at 1 it is
        # a no-op, while `none` re-injects E0 and multiplies p by 8.3.
        f'0/lambda.{PHASE}': (f'lambda.{PHASE}', 'alpha',
                              Raw('uniform 1'), False),
    }
    return _render_fields(fields, spec)


def _render_fields(fields, spec):
    """(object, field, internalField, is_vector) -> the 0/ file text.

    Shared by the profile and the chamber branches, so the two cannot
    drift in how a field file is FRAMED - only in what goes inside it.
    """
    out = {}
    for rel, (obj, fld, internal, vec) in fields.items():
        bfield = {name: _bc_entry(fld, kind, f'uniform {fmt(P_AIR)}',
                                  l_inf=spec.l_inf)
                  for name, kind in spec.patches}
        body = block({
            'dimensions': Raw(_DIMS[fld]),
            'internalField': internal,
            'boundaryField': bfield,
        })
        cls = 'volVectorField' if vec else 'volScalarField'
        out[rel] = foam_file(obj, body, cls=cls)
    return out


# ── top level ───────────────────────────────────────────────────────────────

def render_case(case, n_procs=1, live_steps=0):
    """Plan + render every case file. Returns a CaseSpec whose `files`
    maps 'system/controlDict'-style relpaths to file text. n_procs > 1
    adds system/decomposeParDict; `live_steps` > 0 sets the live-sample
    function object's cadence (see live_steps_for) - nothing else
    varies."""
    spec = plan_case(case)
    spec.n_procs = max(1, int(n_procs))
    spec.live_steps = max(0, int(live_steps or 0))
    spec.probe_adjust = ('no' if getattr(case, 'probe_adjust', True) is False
                         else 'yes')
    # a chain stage fed by a profile carries its state instead of a
    # charge sphere (N7): remapped once here, emitted into 0/ below
    spec.init_state = profile_state(case, spec)
    if spec.init_state is not None:
        # snapped to the clock OpenFOAM can actually name (T62): the run
        # and every time this side writes or reads then agree digit for
        # digit, at a cost of <1e-8 relative on the start time
        spec.t_start = float(tfmt(spec.init_state['t0']))
        # keep the SOURCE charge radius so the next stage in the chain
        # (and the run meta) still knows how big the charge was
        spec.r_exp = spec.init_state['r_exp']
    afterburn = getattr(case, 'afterburn', 'none') or 'none' 
    if spec.dim == 1:
        bmd = _blockmesh_1d(spec)
    elif spec.dim == 2:
        bmd = (_blockmesh_2d_planar(spec, case)
               if case.geometry == 'planar'
               else _blockmesh_2d_axisym(spec, case))
    else:
        bmd = _blockmesh_3d(spec, case)
    spec.files = {
        'system/blockMeshDict': bmd,
        'system/controlDict': _controldict(spec, case),
        'system/fvSchemes': _fvschemes(afterburn),
        'system/fvSolution': _fvsolution(),
        'system/setFieldsDict': _setfieldsdict(spec, case),
        'constant/phaseProperties': _phaseproperties(
            spec,
            ('linear' if spec.init_state is not None
             else getattr(case, 'activation', 'linear')), afterburn),
        'constant/dynamicMeshDict': _dynamicmeshdict(spec, case),
    }
    if spec.obstacles:
        spec.files['system/topoSetDict'] = _toposetdict(spec)
    if spec.lmax and not spec.amr:
        spec.files.update(_refine_dicts(spec, case))
    if spec.n_procs > 1:
        spec.files['system/decomposeParDict'] = \
            _decomposepardict(spec.n_procs)
    if spec.init_state is None:
        spec.files.update(_zero_fields(spec))
    else:
        d = spec.start_dir
        chamber = bool(spec.init_state.get('chamber'))
        prof = {d + rel[1:]: text for rel, text
                in (_chamber_fields(spec, case) if chamber
                    else _profile_fields(spec, case)).items()}
        # B0 is silent when it regresses - the run still produces a
        # shock front (the AIR cells initialise correctly), it just
        # loses the fireball - so the invariant is asserted here rather
        # than left to a reviewer noticing a missing file.
        #
        # A CHAMBER CASE IS EXEMPT, and structurally rather than by
        # exception: its phase is `basic`, which has no reactant side
        # and no lambda at all, so there is nothing for blastFoam to
        # blend back to. Writing a lambda there would be writing a field
        # the solver does not read, which is worse than not writing one.
        if not chamber and f'{d}/lambda.{PHASE}' not in prof:
            raise RuntimeError(
                'a profile-initialised stage must write '
                f'lambda.{PHASE} - without it blastFoam treats the '
                'products as unreacted and resets them to pRef (B0)')
        spec.files.update(prof)
        spec.deferred = tuple(prof)     # written after the mesh stages
    return spec


def _write_files(spec, rels):
    """Write the named `spec.files` entries into the case dir."""
    for rel in rels:
        path = os.path.join(spec.case_unc, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='ascii', newline='\n') as f:
            f.write(spec.files[rel])


def write_deferred(spec):
    """Write the held-back initial state (see CaseSpec.deferred). Runs
    as a mesh stage, once the mesh has its final cells and before
    anything reads the time dir."""
    _write_files(spec, spec.deferred)


def write_case(case, case_posix=None, n_procs=1, live_steps=0):
    """Render and write the case tree into the WSL filesystem (over
    UNC, LF endings). Returns the CaseSpec with paths filled in.
    `live_steps` is passed to render_case.

    A fresh run (no `case_posix`) claims its own directory: the create
    is exist_ok=False, so a name collision fails loudly here instead of
    silently rewriting a concurrent run's controlDict and 0/ fields.
    Passing an explicit `case_posix` is the deliberate reuse path (a
    resume or post-mortem rewrite) and keeps the permissive create."""
    spec = render_case(case, n_procs=n_procs, live_steps=live_steps)
    fresh = case_posix is None
    if fresh:
        case_posix, case_unc = env.new_case_dir(case.dim)
    else:
        case_unc = env.unc(case_posix)
    spec.case_posix, spec.case_unc = case_posix, case_unc
    os.makedirs(case_unc, exist_ok=not fresh)
    _write_files(spec, (rel for rel in spec.files
                        if rel not in spec.deferred))
    # the source Case rides along so a finished run can be reloaded
    # later (postmortem.load_run); disk-side only - not part of the
    # rendered case text pinned by the goldens
    from ...core.case import save_case
    save_case(case, os.path.join(case_unc, 'case.json'))
    return spec
