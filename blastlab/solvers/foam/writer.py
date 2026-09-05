"""blastFoam case generation: render a blastlab Case as a complete
OpenFOAM-9 case tree.

Pure-text rendering (`render_case`) is separated from disk I/O
(`write_case`) so golden tests can pin the generated dicts without WSL.

Geometry mirrors the native solvers: the same effective cell size
(MIN_EXP_CELLS across the charge radius, material-aware density) on the
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

from ...core.constants import (GAMMA_AIR, RHO_AIR, P_AIR, MIN_EXP_CELLS,
                               FOAM_CELLS_WARN)
from ...core import refine
from ...core.grid import make_grid_1d
from ...core.refine import effective_dx as _effective_dx
from . import env
from .dicts import (FLUX_SCHEME, LOHNER_EPS, P_OPEN_BC, Raw, block, fmt,
                    foam_file)
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
    grid: dict = None                    # core.grid product (per dim)
    charges: list = field(default_factory=list)   # [((x,y,z), mass_kg)]
    det_points: list = field(default_factory=list)  # [] = charge centres
    probe_pts: list = field(default_factory=list)   # foam (x,y,z)
    gauge_ids: list = field(default_factory=list)   # native radii/points
    patches: list = field(default_factory=list)     # (name, kind)
    obstacles: list = field(default_factory=list)   # (x0,x1,y0,y1,z0,z1)
    solid: object = None            # (nx,ny,nz) bool mask, None = none
    files: dict = field(default_factory=dict)       # relpath -> text
    case_posix: str = ''
    case_unc: str = ''
    # local refinement (core.refine): nx/ny/nz/dx/grid/solid above are
    # the FINE display grid (dx = dx_base / 2**lmax); blockMesh is built
    # on the base counts `nb`, refineMesh passes realise `zones`
    dx_base: float = 0.0
    nb: tuple = ()                  # base (nx, ny[, nz]) for blockMesh
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
        self.levels, self.lmax = plan.levels, plan.lmax
        self.zones = list(plan.zones)
        self.solid_base = plan.solid_base
        self.solid = plan.solid_fine

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
    cap_is_end = bool(t_end) and t_end < cap
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
    return end_time, t_est / _n_writes(n_snapshots) / 4.0, cap_is_end


def plan_case(case):
    """Geometry/timing plan (no text yet). Returns a CaseSpec without
    `files`."""
    mat = getattr(case, 'material', 'TNT')
    m = MATERIALS[mat]

    if case.dim == 1:
        r_exp = charge_radius(case.charge_kg, m)
        dx = _effective_dx(case.cell_size_m, r_exp, case.radius_m)
        r_face, r, A_face, V_cell = make_grid_1d(case.radius_m, dx)
        grid = dict(r_face=r_face, r=r, A_face=A_face, V_cell=V_cell)
        spec = CaseSpec(dim=1, material=mat, nx=len(r), dx=dx,
                        r_exp=r_exp, center=(0.0, 0.0, 0.0), grid=grid)
        spec.charges = [((0.0, 0.0, 0.0), float(case.charge_kg))]
        R_out = r_face[-1]
        spec.patches = [('outlet', 'open'), ('wedge', 'wedge')]
        gauges = [g for g in case.gauge_radii if 0.0 < g <= R_out]
        spec.gauge_ids = gauges
        spec.probe_pts = [(g, 0.0, 0.0) for g in gauges]
        spec.end_time, spec.write_interval, spec.cap_is_end = _timing(
            case, R_out, R_out, case.n_snapshots)
        return spec

    if case.dim == 2:
        planar = case.geometry == 'planar'
        r_exp = charge_radius(case.charge, m, planar=planar)
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
        spec.charges = [((x0, y0, 0.0), float(case.charge))]
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
        # by topoSet/subsetMesh exactly like the 3D boxes (the Python
        # mask mirrors boxToCell's cell-centre criterion)
        spec.obstacles = [tuple(float(v) for v in box)
                          for box in (getattr(case, 'obstacles', None)
                                      or [])]
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
                 if case.bcs.get(s) == 'open']
        corners = [(cx, cy) for cx in (0.0, Lx_eff)
                   for cy in (0.0, Ly_eff)]
        far = max(math.hypot(cx - x0, cy - y0) for cx, cy in corners)
        est = min(opens) if opens else far
        spec.end_time, spec.write_interval, spec.cap_is_end = _timing(
            case, max(Lx_eff, Ly_eff), est, case.n_snapshots)
        return spec

    # 3D - the primary charge plus any extras; the grid resolves the
    # SMALLEST charge, snapshot radii start from the largest
    x0, y0, z0 = case.center
    charges = [((float(x0), float(y0), float(z0)), float(case.charge))]
    for ex, ey, ez, mass in getattr(case, 'charges', None) or []:
        charges.append(((float(ex), float(ey), float(ez)), float(mass)))
    r_exps = [charge_radius(mass, m) for _c, mass in charges]
    r_exp = max(r_exps)
    plan = refine.plan_levels(case, rho0=m.rho0)
    grid, dx = plan.fine, plan.dx_fine
    Ls = (grid['x_face'][-1], grid['y_face'][-1], grid['z_face'][-1])
    spec = CaseSpec(dim=3, material=mat,
                    nx=grid['Nx'], ny=grid['Ny'], nz=grid['Nz'],
                    dx=dx, r_exp=r_exp, center=(x0, y0, z0), grid=grid)
    spec.apply_plan(plan)
    spec.charges = charges
    spec.det_points = [tuple(float(v) for v in p)
                       for p in (getattr(case, 'det_points', None) or [])]
    spec.patches = [(s, case.bcs[s])
                    for s in ('x_lo', 'x_hi', 'y_lo', 'y_hi',
                              'z_lo', 'z_hi')]
    # obstacles: axis-aligned boxes carved out of the mesh by
    # topoSet(boxToCell)/subsetMesh; the Python-side mask mirrors
    # boxToCell's criterion (cell CENTRE inside the box, inclusive)
    # so read-back scatters fluid values onto the full native grid
    spec.obstacles = [tuple(float(v) for v in box)
                      for box in (getattr(case, 'obstacles', None)
                                  or [])]
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
    side_d = {s: min(d(c) for c, _m in charges) for s, d in (
        ('x_lo', lambda c: c[0]), ('x_hi', lambda c: Ls[0] - c[0]),
        ('y_lo', lambda c: c[1]), ('y_hi', lambda c: Ls[1] - c[1]),
        ('z_lo', lambda c: c[2]), ('z_hi', lambda c: Ls[2] - c[2]))}
    opens = [d for s, d in side_d.items() if case.bcs.get(s) == 'open']
    corners = [(cx, cy, cz) for cx in (0.0, Ls[0])
               for cy in (0.0, Ls[1]) for cz in (0.0, Ls[2])]
    far = max(math.sqrt((cx - x0) ** 2 + (cy - y0) ** 2
                        + (cz - z0) ** 2) for cx, cy, cz in corners)
    est = min(opens) if opens else far
    spec.end_time, spec.write_interval, spec.cap_is_end = _timing(
        case, max(Ls), est, case.n_snapshots)
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
    return dict(wall='wall', open='patch', empty='empty',
                wedge='wedge')[kind]


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

def _controldict(spec, case):
    d = {
        'application': 'blastFoam',
        'startFrom': 'startTime',
        'startTime': 0,
        'stopAt': 'endTime',
        'endTime': spec.end_time,
        'deltaT': Raw('1e-7'),
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
        'timePrecision': 8,
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
    functions = {}
    if spec.dim >= 2:
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
    if spec.dim >= 2 and spec.amr:
        # AMR (N16): the cell count and order change every write, so
        # each time dir carries its own cell centres (this FO) next to
        # the refiner's `cellLevel` (dumpLevel); the backend rebuilds
        # the display remap from the pair. No live slice: its raw rows
        # carry no cell size, so live frames come from written times.
        functions['cellCentres'] = {
            'type': 'writeCellCentres',
            'libs': Raw('("libfieldFunctionObjects.so")'),
            'writeControl': 'writeTime',
        }
    elif spec.dim >= 2:
        # live p slice every few steps (same role as the 1D liveLine):
        # 2D cuts the z=0 mid-plane (the whole field, one face per
        # cell); 3D cuts the user's live-slice plane through the
        # nearest cell-centre layer. interpolate/triangulate off keep
        # one uncut face per cell with the cell value, so the backend
        # sorts the raw rows straight onto the grid.
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
            pt = tuple(float(c[s0]) if a == ax_i else 0.0
                       for a in range(3))
            nrm = tuple(1 if a == ax_i else 0 for a in range(3))
        functions[LIVE_SLICE] = {
            'type': 'surfaces',
            'libs': Raw('("libsampling.so")'),
            'writeControl': 'timeStep',
            'writeInterval': live_sample_steps(spec.dim),
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
            'writeInterval': live_sample_steps(spec.dim),
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
    if spec.probe_pts:
        functions['gauges'] = {
            'type': 'blastProbes',
            'writeControl': 'timeStep',
            'writeInterval': 1,
            'adjustLocations': 'yes',
            'append': 'yes',
            'probeLocations': [tuple(p) for p in spec.probe_pts],
            'fields': ['p'],
        }
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
    if spec.dim == 2 and case.geometry == 'planar':
        x0, y0, _ = spec.center
        regions = [('cylinderToCell', {
            'p1': (x0, y0, -spec.dx_base),
            'p2': (x0, y0, spec.dx_base),
            'radius': spec.r_exp,
            'fieldValues': [Raw(f'volScalarFieldValue {alpha}    1')],
        })]
    else:
        m = MATERIALS[spec.material]
        regions = [('sphericalMassToCell', {
            'centre': centre,
            'rho': m.rho0,
            'mass': mass,
            'backup': {'centre': centre,
                       'radius': 2.0 * charge_radius(mass, m)},
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


def _phaseproperties(spec, activation='linear', afterburn='none'):
    m = MATERIALS[spec.material]
    # 'linear' burns at vDet from the detonation points (tutorial
    # default); 'none' = fully reacted at t0 - the vendor's
    # burstingWindow pattern: initiation carries only E0
    if activation == 'none':
        initiation = {'E0': E0(m)}
    else:
        initiation = {
            'E0': E0(m),
            'points': (spec.det_points
                       or [c for c, _mass in spec.charges]),
            'vDet': m.vDet,
        }
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
    est = (getattr(case, 'amr_estimator', 'densityGradient')
           or 'densityGradient')
    d = {'dynamicFvMesh': 'adaptiveFvMesh', 'errorEstimator': est}
    if est == 'Lohner':
        d['field'] = 'p'
        d['epsilon'] = LOHNER_EPS
    d.update({
        'refineInterval': int(getattr(case, 'amr_interval', 2)),
        'lowerRefineLevel': float(getattr(case, 'amr_refine', 0.1)),
        'unrefineLevel': float(getattr(case, 'amr_unrefine', 0.1)),
        'nBufferLayers': int(getattr(case, 'amr_buffer', 2)),
        'maxRefinement': int(spec.amr),
        'maxCells': (int(getattr(case, 'amr_max_cells', 0) or 0)
                     or FOAM_CELLS_WARN),
        'dumpLevel': True,
    })
    if spec.n_procs > 1:
        # fixed decomposition: balancing needs an `internal` patch
        # (addEmptyPatch) - the parallel follow-up decides
        d['loadBalance'] = {'balance': False}
    return foam_file('dynamicMeshDict', block(d), location='constant')


def _decomposepardict(n_procs):
    """scotch decomposition (modeled on the building3DWorkshop
    tutorial); written only for parallel runs, so serial case trees
    stay byte-identical."""
    body = block({
        'numberOfSubdomains': n_procs,
        'method': 'scotch',
    })
    return foam_file('decomposeParDict', body, location='system')


# ── 0/ field files ──────────────────────────────────────────────────────────

def _bc_entry(fld, kind):
    """Boundary entry dict for one field on one patch kind."""
    if kind == 'wedge':
        return {'type': 'wedge'}
    if kind == 'empty':
        return {'type': 'empty'}
    if kind == 'wall':
        return {'type': 'slip'} if fld == 'U' else {'type': 'zeroGradient'}
    # open
    if fld == 'p':
        return {'type': P_OPEN_BC, 'value': Raw('$internalField')}
    return {'type': 'zeroGradient'}


def _field_file(obj, fld, internal, spec, vector=False):
    bfield = {name: _bc_entry(fld, kind) for name, kind in spec.patches}
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


# ── top level ───────────────────────────────────────────────────────────────

def render_case(case, n_procs=1):
    """Plan + render every case file. Returns a CaseSpec whose `files`
    maps 'system/controlDict'-style relpaths to file text. n_procs > 1
    adds system/decomposeParDict (nothing else varies)."""
    spec = plan_case(case)
    spec.n_procs = max(1, int(n_procs))
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
            spec, getattr(case, 'activation', 'linear'), afterburn),
        'constant/dynamicMeshDict': _dynamicmeshdict(spec, case),
    }
    if spec.obstacles:
        spec.files['system/topoSetDict'] = _toposetdict(spec)
    if spec.lmax and not spec.amr:
        spec.files.update(_refine_dicts(spec, case))
    if spec.n_procs > 1:
        spec.files['system/decomposeParDict'] = \
            _decomposepardict(spec.n_procs)
    spec.files.update(_zero_fields(spec))
    return spec


def write_case(case, case_posix=None, n_procs=1):
    """Render and write the case tree into the WSL filesystem (over
    UNC, LF endings). Returns the CaseSpec with paths filled in.

    A fresh run (no `case_posix`) claims its own directory: the create
    is exist_ok=False, so a name collision fails loudly here instead of
    silently rewriting a concurrent run's controlDict and 0/ fields.
    Passing an explicit `case_posix` is the deliberate reuse path (a
    resume or post-mortem rewrite) and keeps the permissive create."""
    spec = render_case(case, n_procs=n_procs)
    fresh = case_posix is None
    if fresh:
        case_posix, case_unc = env.new_case_dir(case.dim)
    else:
        case_unc = env.unc(case_posix)
    spec.case_posix, spec.case_unc = case_posix, case_unc
    os.makedirs(case_unc, exist_ok=not fresh)
    for rel, text in spec.files.items():
        path = os.path.join(case_unc, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='ascii', newline='\n') as f:
            f.write(text)
    # the source Case rides along so a finished run can be reloaded
    # later (postmortem.load_run); disk-side only - not part of the
    # rendered case text pinned by the goldens
    from ...core.case import save_case
    save_case(case, os.path.join(case_unc, 'case.json'))
    return spec
