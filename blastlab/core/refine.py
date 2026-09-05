"""Static local mesh refinement: the predicted mesh structure.

A case has a BASE cell size and a list of axis-aligned refinement zones
`(x0, x1, y0, y1[, z0, z1], level)`; level l halves the cell l times
(level 1 = dx/2, level 2 = dx/4, ...). Zones may nest, and the
blastFoam backend realises them with one topoSet + refineMesh pass per
level. The native numpy solvers stay uniform - validation refuses zones
for them.

Everything the rest of blastlab needs to know about a refined mesh is
derived here from the base grid and the zones alone, WITHOUT the foam
mesh: the per-cell level map on the FINE grid (dx / 2**lmax - the
resolution every field is resampled to for display), the predicted cell
count, a unique "source cell" id per fine cell (`fine_src`) - the same
structure the real mesh is matched against after refineMesh - and the
cell-edge segments the "show mesh" overlays draw. So the setup preview,
the validation report, the case writer and the post-run overlays all
agree by construction.

Snapping rule: a level-l zone is snapped outward onto the faces of level
l-1 (spacing dx / 2**(l-1)) - exactly the cells refineMesh pass l can
select whole, and the finest granularity that keeps "cell inside the box
<=> all its children inside". The 2:1 grading rule (a level may not jump
by two between neighbouring cells) is checked on the fine grid.

Pure numpy; imports nothing from the GUI or the foam package.
"""

import math
from dataclasses import dataclass, field

import numpy as np

from .bc import solid_mask_2d, solid_mask_3d
from .constants import JWL_TNT, MIN_EXP_CELLS
from .grid import make_geometry, make_grid

#: deepest refinement level (dx / 16): the fine display grid grows as
#: 2**(dim*level), so deeper levels are not displayable anyway
MAX_LEVEL = 4

#: preview / overlay colours per level 1..MAX_LEVEL
LEVEL_COLORS = ('#4fc3f7', '#ffb74d', '#e57373', '#ba68c8')


def effective_dx(cell_size, r_exp, L):
    """The charge auto-refinement rule shared by the native solvers and
    the foam writer: >= MIN_EXP_CELLS cells across r_exp, and the refined
    spacing must divide L exactly (ceil: never coarser than
    r_exp / MIN_EXP_CELLS)."""
    if cell_size > r_exp / MIN_EXP_CELLS:
        return L / math.ceil(L / (r_exp / MIN_EXP_CELLS))
    return cell_size


def charge_radius(mass, rho0=None, planar=False):
    """Explosive radius for a mass (kg; kg/m in planar 2D) of density
    rho0 (TNT by default) - sphere, or cylinder per unit depth."""
    rho0 = JWL_TNT['rho0'] if rho0 is None else rho0
    if planar:
        return math.sqrt(mass / (math.pi * rho0))
    return (3.0 * mass / (4.0 * math.pi * rho0)) ** (1.0 / 3.0)


# ── zones ────────────────────────────────────────────────────────────────────

def zone_level(zone):
    return int(round(float(zone[-1])))


def snap_zone(zone, dx_base, dim):
    """Zone edges moved OUTWARD onto the faces of level (l - 1), i.e.
    multiples of dx_base / 2**(l-1). Returns (snapped_zone, moved)."""
    box = [float(v) for v in zone[:2 * dim]]
    level = zone_level(zone)
    h = dx_base / (2 ** max(level - 1, 0))
    out = []
    for a in range(dim):
        lo, hi = box[2 * a], box[2 * a + 1]
        out.append(math.floor(lo / h + 1e-6) * h)
        out.append(math.ceil(hi / h - 1e-6) * h)
    moved = any(abs(o - b) > 1e-9 * max(1.0, h) for o, b in zip(out, box))
    return (*out, level), moved


def level_map(centres, zones):
    """int8 array (Nx, Ny[, Nz]) of the max zone level whose box holds
    the cell centre (inclusive - the boxToCell criterion, as in
    core.bc.solid_mask_*). `centres` are the FINE grid axes."""
    dim = len(centres)
    shape = tuple(len(c) for c in centres)
    lv = np.zeros(shape, dtype=np.int8)
    for zone in zones:
        box, level = zone[:2 * dim], zone_level(zone)
        m = np.ones(shape, dtype=bool)
        for a in range(dim):
            c = centres[a].reshape([-1 if i == a else 1 for i in range(dim)])
            m &= (c >= box[2 * a]) & (c <= box[2 * a + 1])
        lv = np.maximum(lv, np.where(m, level, 0).astype(np.int8))
    return lv


def required_level(dx_base, r_exp):
    """Levels needed below dx_base so that r_exp spans MIN_EXP_CELLS
    cells at the finest level (0 when the base already resolves it)."""
    need = dx_base / (r_exp / MIN_EXP_CELLS)
    return 0 if need <= 1.0 + 1e-12 else int(math.ceil(math.log2(need)))


def auto_charge_zones(dim, dx_base, dims, centres, r_exps, level_cap=None):
    """Nested boxes around each charge for `charge_refine='zone'`. The
    finest zone (level L) spans centre +- 2 r_exp; each coarser zone l
    adds one cell of level l (dx_base / 2**l) so, after snapping, every
    zone sits at least one cell of the next coarser level inside it (the
    2:1 grading rule). Returns (zones, L) with L the level the smallest
    charge needs (clamped by `level_cap`)."""
    L = max(required_level(dx_base, r) for r in r_exps)
    if level_cap is not None:
        L = min(L, level_cap)
    zones = []
    for c, r in zip(centres, r_exps):
        Lc = required_level(dx_base, r)
        if level_cap is not None:
            Lc = min(Lc, level_cap)
        for l in range(1, Lc + 1):
            half = 2.0 * r + sum(dx_base / (2 ** k) for k in range(l, Lc))
            box = []
            for a in range(dim):
                box += [max(0.0, c[a] - half), min(dims[a], c[a] + half)]
            zones.append((*box, l))
    return zones, L


# ── the plan ─────────────────────────────────────────────────────────────────

@dataclass
class Plan:
    dim: int
    dx_base: float
    base: dict                       # core.grid dict of the base grid
    fine: dict                       # core.grid dict of the fine grid
    levels: np.ndarray               # int8 on the FINE grid
    lmax: int
    zones: list                      # snapped, user + auto
    user_zones: list = field(default_factory=list)
    auto_zones: list = field(default_factory=list)
    auto_level: int = 0              # level the charge needs (zone mode)
    solid_base: object = None        # bool (base shape) or None
    n_pred: int = 0                  # predicted foam cell count
    n_fine: int = 0                  # fine display cells
    moved: list = field(default_factory=list)   # user zones that snapped

    @property
    def dx_fine(self):
        return self.dx_base / (2 ** self.lmax)

    @property
    def refined(self):
        return self.lmax > 0

    @property
    def solid_fine(self):
        return None if self.solid_base is None else expand(self.solid_base,
                                                            self.lmax)

    def meta(self):
        """The picklable record carried in a Result's meta."""
        return dict(levels=self.levels, lmax=self.lmax,
                    dx_base=self.dx_base, zones=list(self.zones))


def _charges(case, rho0):
    """[(centre tuple, r_exp)] for the primary charge (+ 3D extras)."""
    dim = case.dim
    planar = dim == 2 and case.geometry == 'planar'
    c0 = tuple(float(v) for v in case.center)
    if dim == 2 and case.geometry == 'axisymmetric':
        c0 = (0.0, c0[1])
    out = [(c0[:dim], charge_radius(float(case.charge), rho0, planar))]
    for ex in (getattr(case, 'charges', None) or []):
        out.append((tuple(float(v) for v in ex[:3]),
                    charge_radius(float(ex[3]), rho0)))
    return out


def plan_levels(case, rho0=None):
    """Base grid, fine grid and level map for a 2D/3D case (any solver:
    an unrefined case yields lmax = 0 and fine is base). Raises
    ValueError only for zones that cannot be laid out at all (wrong
    arity / non-integer level); geometric problems are reported by
    validate_zones."""
    dim = case.dim
    dims = (case.Lx, case.Ly) if dim == 2 else (case.Lx, case.Ly, case.Lz)
    user = list(getattr(case, 'refine_zones', None) or [])
    for z in user:
        if len(z) != 2 * dim + 1:
            raise ValueError(f"Refinement zone {tuple(z)} needs "
                             f"{2 * dim} box edges and a level")
        if abs(float(z[-1]) - round(float(z[-1]))) > 1e-9:
            raise ValueError(f"Refinement zone {tuple(z)}: the level "
                             f"must be a whole number")
    mode = getattr(case, 'charge_refine', 'global')
    charges = (_charges(case, rho0)
               if getattr(case, 'init_mode', 'charge') == 'charge'
               and case.charge else [])

    # base spacing: today's global rule unless the charge is left to an
    # automatic zone
    dx = float(case.cell_size_m)
    if charges and mode != 'zone':
        dx = min(effective_dx(dx, r, case.Lx) for _c, r in charges)
    base = _grid(case, dx)
    dx_base = float(base['dx'])

    auto, auto_level = [], 0
    if charges and mode == 'zone':
        axisym = dim == 2 and case.geometry == 'axisymmetric'
        auto, auto_level = auto_charge_zones(
            dim, dx_base, dims, [c for c, _r in charges],
            [r for _c, r in charges], level_cap=1 if axisym else None)

    zones, moved = [], []
    for z in user + auto:
        lv = zone_level(z)
        if not 1 <= lv <= MAX_LEVEL:
            zones.append((*[float(v) for v in z[:2 * dim]], lv))
            continue                       # validate_zones reports it
        s, mv = snap_zone(z, dx_base, dim)
        zones.append(s)
        if mv and z in user:
            moved.append(z)
    lmax = max([min(zone_level(z), MAX_LEVEL) for z in zones], default=0)
    fine = base if lmax == 0 else _grid(case, dx_base / (2 ** lmax))
    centres = tuple(fine[k] for k in ('x_c', 'y_c', 'z_c')[:dim])
    levels = level_map(centres, [z for z in zones
                                 if 1 <= zone_level(z) <= MAX_LEVEL])

    obstacles = getattr(case, 'obstacles', None) or []
    solid_base = None
    if obstacles:
        solid_base = (solid_mask_2d(base['x_c'], base['y_c'], obstacles)
                      if dim == 2 else
                      solid_mask_3d(base['x_c'], base['y_c'], base['z_c'],
                                    obstacles))
    plan = Plan(dim=dim, dx_base=dx_base, base=base, fine=fine,
                levels=levels, lmax=lmax, zones=zones, user_zones=user,
                auto_zones=auto, auto_level=auto_level,
                solid_base=solid_base, moved=moved)
    plan.n_fine = int(levels.size)
    plan.n_pred = n_cells_from_levels(levels, lmax, plan.solid_fine)
    return plan


def _grid(case, dx):
    if case.dim == 2:
        return make_geometry(case.geometry, case.Lx, case.Ly, dx)
    return make_grid(case.Lx, case.Ly, case.Lz, dx)


def validate_zones(case, plan):
    """(errors, warnings) for the zones of a plan: in-domain boxes,
    integer levels in 1..MAX_LEVEL, the 2:1 grading rule (a level may
    not jump by 2 or more between neighbouring cells - nest each
    level-l zone at least one level-(l-1) cell inside a level-(l-1)
    zone), the axisymmetric axis rule (level <= 1 on the axis column:
    wedge axis cells are prisms, not hexahedra) and the charge zone
    fitting under MAX_LEVEL."""
    errors, warnings = [], []
    dim = plan.dim
    dims = (case.Lx, case.Ly) if dim == 2 else (case.Lx, case.Ly, case.Lz)
    axisym = dim == 2 and case.geometry == 'axisymmetric'
    for z in plan.user_zones:
        lo, hi = z[0:2 * dim:2], z[1:2 * dim:2]
        if any(a >= b for a, b in zip(lo, hi)) or \
           any(b > L or a < 0 for a, b, L in zip(lo, hi, dims)):
            errors.append(f"Refinement zone {tuple(z)} is not a valid "
                          f"in-domain box")
        lv = zone_level(z)
        if not 1 <= lv <= MAX_LEVEL:
            errors.append(f"Refinement zone {tuple(z)}: level must be "
                          f"1..{MAX_LEVEL}")
    for z in plan.moved:
        s, _ = snap_zone(z, plan.dx_base, dim)
        warnings.append(
            f"Refinement zone {tuple(z)} snapped outward to level-"
            f"{zone_level(z) - 1} cell faces: "
            f"{tuple(round(v, 6) for v in s[:-1])}")
    if getattr(case, 'charge_refine', 'global') == 'zone' and case.charge:
        need = max(required_level(plan.dx_base, r)
                   for _c, r in _charges(case, None))
        if need > MAX_LEVEL:
            errors.append(
                f"Resolving the charge needs level {need} (> {MAX_LEVEL}) "
                f"below the base cell - lower the base cell size to at "
                f"most {plan.dx_base * 2 ** (MAX_LEVEL - need):.5g} m")
        elif axisym and need > 1:
            errors.append(
                "Axisymmetric: only level 1 is possible on the axis, so "
                "the charge needs a base cell of at most "
                f"{plan.dx_base * 2 ** (1 - need):.5g} m (currently "
                f"{plan.dx_base:.5g} m)")
    if errors:
        return errors, warnings
    lv = plan.levels
    for a in range(dim):
        d = np.abs(np.diff(lv.astype(np.int16), axis=a))
        bad = np.argwhere(d >= 2)
        if len(bad):
            idx = tuple(int(i) for i in bad[0])
            axes = tuple(plan.fine[k] for k in ('x_c', 'y_c', 'z_c')[:dim])
            where = ', '.join(f"{c[i]:.3g}" for c, i in zip(axes, idx))
            errors.append(
                f"Refinement level jumps by 2 or more between neighbouring "
                f"cells near ({where}) m - nest each level-l zone inside a "
                f"level-(l-1) zone with at least one level-(l-1) cell of "
                f"margin")
            break
    if axisym and lv.ndim == 2 and (lv[0] >= 2).any():
        errors.append("Axisymmetric: refinement zones touching the "
                      "symmetry axis (x0 = 0) are limited to level 1 "
                      "(the wedge axis cells are prisms, not hexahedra)")
    return errors, warnings


# ── fine-grid structures ─────────────────────────────────────────────────────

def expand(arr, lmax):
    """Base-grid array -> fine grid (each cell repeated 2**lmax per axis)."""
    out = np.asarray(arr)
    if lmax == 0:
        return out
    for a in range(out.ndim):
        out = np.repeat(out, 2 ** lmax, axis=a)
    return out


def fine_src(levels, lmax, solid_fine=None):
    """int32 array on the fine grid: a unique id per predicted mesh cell
    (a level-l cell covers 2**(lmax-l) fine cells per axis), -1 inside
    carved (solid) cells. Ids are numbered x-fastest by block origin."""
    lv = np.asarray(levels).astype(np.int64)
    shift = lmax - lv                       # fine cells per cell = 2**shift
    shape = lv.shape
    grids = np.indices(shape, dtype=np.int64)
    origin = [(g >> shift) << shift for g in grids]  # block origin per axis
    key = np.ravel_multi_index(tuple(origin), shape, order='F')
    if solid_fine is not None:
        key = np.where(np.asarray(solid_fine), -1, key)
    fluid = key >= 0
    ids = np.full(shape, -1, dtype=np.int32)
    if fluid.any():
        _u, inv = np.unique(key[fluid], return_inverse=True)
        ids[fluid] = inv.astype(np.int32)
    return ids


def n_cells_from_levels(levels, lmax, solid_fine=None):
    """Predicted foam cell count: each fine cell contributes
    1 / 2**(dim*(lmax - l)) of a cell (solid cells nothing)."""
    lv = np.asarray(levels).astype(np.int64)
    dim = lv.ndim
    if solid_fine is not None:
        lv = lv[~np.asarray(solid_fine)]
    counts = np.bincount(lv.ravel(), minlength=lmax + 1)
    total = sum(int(c) / (2 ** (dim * (lmax - l)))
                for l, c in enumerate(counts))
    return int(round(total))


def slice_src(levels, lmax, axis=None, k_fine=None, solid_fine=None):
    """2D `fine_src` of a plane: the whole field for a 2D level map, or
    the fine layer `k_fine` along `axis` of a 3D one (ids unique within
    the plane - for drawing edges)."""
    lv = np.asarray(levels)
    if lv.ndim == 2:
        return fine_src(lv, lmax, solid_fine)
    sl = tuple(int(k_fine) if a == axis else slice(None) for a in range(3))
    sol = None if solid_fine is None else np.asarray(solid_fine)[sl]
    return fine_src(lv[sl], lmax, sol)


def _runs(mask):
    """[(start, stop)] index runs of True in a 1D bool array."""
    if not mask.any():
        return []
    m = np.concatenate(([False], mask, [False]))
    d = np.diff(m.astype(np.int8))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def mesh_segments_2d(src2d, u_face, v_face):
    """Cell-edge segments (N, 2, 2) of a plane: every face between two
    fine cells with different source ids, plus the domain boundary;
    `src2d=None` means a uniform mesh (every fine face). Consecutive
    faces on one line are merged into one segment."""
    u_face = np.asarray(u_face, dtype=float)
    v_face = np.asarray(v_face, dtype=float)
    nu, nv = len(u_face) - 1, len(v_face) - 1
    segs = []
    if src2d is None:
        for u in u_face:
            segs.append(((u, v_face[0]), (u, v_face[-1])))
        for v in v_face:
            segs.append(((u_face[0], v), (u_face[-1], v)))
        return np.array(segs, dtype=float).reshape(-1, 2, 2)
    src = np.asarray(src2d)
    vert = np.ones((nu + 1, nv), dtype=bool)        # faces at u_face[i]
    vert[1:-1] = src[1:] != src[:-1]
    for i in range(nu + 1):
        for j0, j1 in _runs(vert[i]):
            segs.append(((u_face[i], v_face[j0]), (u_face[i], v_face[j1])))
    horiz = np.ones((nu, nv + 1), dtype=bool)       # faces at v_face[j]
    horiz[:, 1:-1] = src[:, 1:] != src[:, :-1]
    for j in range(nv + 1):
        for i0, i1 in _runs(horiz[:, j]):
            segs.append(((u_face[i0], v_face[j]), (u_face[i1], v_face[j])))
    return np.array(segs, dtype=float).reshape(-1, 2, 2)


def match_cells(C, fine, fine_ids):
    """Foam cell centres (n, >=dim) -> `remap`: int32 on the fine grid
    giving the foam cell index that covers each fine cell (-1 in carved
    regions). The mesh must have exactly the predicted structure: every
    predicted id hit by exactly one centre, none in a solid region.
    Raises RuntimeError naming the first offending centre otherwise."""
    fine_ids = np.asarray(fine_ids)
    dim = fine_ids.ndim
    C = np.asarray(C, dtype=float)
    idx = []
    for a, key in enumerate(('x_face', 'y_face', 'z_face')[:dim]):
        f = np.asarray(fine[key], dtype=float)
        dxf = f[1] - f[0]
        i = np.floor((C[:, a] - f[0]) / dxf).astype(np.int64)
        idx.append(np.clip(i, 0, len(f) - 2))
    ids = fine_ids[tuple(idx)]
    n_pred = int(fine_ids.max()) + 1
    bad = np.flatnonzero(ids < 0)
    if len(bad):
        raise RuntimeError(
            f"mesh cell {bad[0]} at {tuple(np.round(C[bad[0], :dim], 6))} "
            f"lies inside a carved (obstacle) region of the predicted mesh")
    if len(ids) != n_pred:
        raise RuntimeError(
            f"mesh has {len(ids):,} cells but the refinement plan predicts "
            f"{n_pred:,}")
    counts = np.bincount(ids, minlength=n_pred)
    if (counts != 1).any():
        k = int(np.flatnonzero(counts != 1)[0])
        hits = np.flatnonzero(ids == k)
        where = (tuple(np.round(C[hits[0], :dim], 6)) if len(hits)
                 else 'no centre')
        raise RuntimeError(
            f"predicted cell {k} is hit by {counts[k]} mesh cells "
            f"(first at {where}) - the refined mesh does not have the "
            f"predicted structure")
    cell_of_id = np.empty(n_pred, dtype=np.int32)
    cell_of_id[ids] = np.arange(len(ids), dtype=np.int32)
    return np.where(fine_ids >= 0, cell_of_id[np.maximum(fine_ids, 0)],
                    -1).astype(np.int32)
