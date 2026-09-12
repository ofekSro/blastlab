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
from .constants import (JWL_TNT, MIN_EXP_CELLS, FOAM_EXP_CELLS,
                        CELLS_2D_MAX, CELLS_REFUSE,
                        FOAM_CELLS_WARN)
from .grid import make_geometry, make_grid

#: deepest refinement level (dx / 16): the fine display grid grows as
#: 2**(dim*level), so deeper levels are not displayable anyway
MAX_LEVEL = 4

#: preview / overlay colours per level 1..MAX_LEVEL
LEVEL_COLORS = ('#4fc3f7', '#ffb74d', '#e57373', '#ba68c8')

#: dynamic AMR (blastFoam adaptiveFvMesh, N16): deepest maxRefinement
#: accepted. Deeper than MAX_LEVEL because the DISPLAY grid may stop at
#: a coarser `display_level` (cells below it are box-averaged onto it).
MAX_AMR_LEVEL = 5
#: error estimators the case writer knows how to render
AMR_ESTIMATORS = ('densityGradient', 'Lohner')

#: A plan whose base or fine grid would exceed this many cells is refused
#: (ValueError) BEFORE any full-grid array is allocated: such a case is
#: already over every display/solver cap, so the caller reports it - but
#: the earlier code allocated the fine level map first and could OOM the
#: process on a stray cell size (e.g. the 10 m 3D default, or dx = 1e-9).
#: Comfortably above the 3D display cap (15M) so every runnable case still
#: builds its real plan and gets the precise cap message.
_PLAN_MAX_CELLS = 40_000_000

#: The AMR display grid is a single int8 array (n bytes), and validate_case
#: reports its own precise "display grid over the cap" message for a
#: user-forced display level, so the raw refusal only has to stop a grid
#: that would not fit in memory at all - a much higher bar than the static
#: fine grid (which also builds an int64 id array).
_AMR_MAX_DISPLAY = 400_000_000


def _grid_cells(dims, dx):
    """Predicted whole-cell count of a `dims` box at spacing `dx`, from
    arithmetic only (no arrays) - the guard uses it before building a
    grid so a tiny/huge dx cannot allocate a giant axis first."""
    n = 1
    for L in dims:
        n *= max(1, int(round(float(L) / dx)))
    return n


def _fit_shape(arr, shape):
    """Crop (or edge-pad) `arr` to `shape` per axis; a no-op when equal.

    `expand` doubles the BASE cells, but `make_grid` rounds each axis
    length independently, so along an axis that does not divide evenly by
    the base spacing the fine count differs from base x 2**lmax by one
    (Ly = 2 m at 0.006237 m -> 321 base, 641 fine, not 642). The fine grid
    shape is authoritative; keep it. Identical output when the shapes
    already match, so no obstacle golden moves."""
    arr = np.asarray(arr)
    shape = tuple(int(s) for s in shape)
    if arr.shape == shape:
        return arr
    arr = arr[tuple(slice(0, n) for n in shape)]
    pad = [(0, max(0, n - s)) for n, s in zip(shape, arr.shape)]
    if any(hi for _lo, hi in pad):
        arr = np.pad(arr, pad, mode='edge')
    return arr


def exp_cells(case):
    """Cells demanded across the charge radius: MIN_EXP_CELLS for the
    native solvers (byte-pinned), FOAM_EXP_CELLS for blastFoam, whose
    `sphericalMassToCell` deposits only the staircase mass (N5/T39)."""
    return (FOAM_EXP_CELLS
            if getattr(case, 'solver', 'native') == 'blastfoam'
            else MIN_EXP_CELLS)


def effective_dx(cell_size, r_exp, L, n_cells=MIN_EXP_CELLS):
    """The charge auto-refinement rule shared by the native solvers and
    the foam writer: >= `n_cells` cells across r_exp, and the refined
    spacing must divide L exactly (ceil: never coarser than
    r_exp / n_cells)."""
    if cell_size > r_exp / n_cells:
        return L / math.ceil(L / (r_exp / n_cells))
    return cell_size


def charge_radius(mass, rho0=None, planar=False):
    """Explosive radius for a mass (kg; kg/m in planar 2D) of density
    rho0 (TNT by default) - sphere, or cylinder per unit depth."""
    rho0 = JWL_TNT['rho0'] if rho0 is None else rho0
    if planar:
        return math.sqrt(mass / (math.pi * rho0))
    return (3.0 * mass / (4.0 * math.pi * rho0)) ** (1.0 / 3.0)


def set_mass_fraction(dim, geometry, dx, r_exp, centre, dims):
    """What blastFoam's `sphericalMassToCell` actually deposits (N5).

    It sets `alpha = 1` in the cells whose CENTRES fall inside r_exp and
    the mass that lands is therefore the staircase volume x rho0, not
    the sphere's: ~0.85 of the request at 5 cells across the radius.
    Returns `(n_cells, fraction)` against the charge volume clipped to
    the domain (a wall-truncated charge is a deliberate surface burst,
    so its outside part is not counted as missing). `centre` is
    (x0, y0[, z0]) with x0 = 0 on the axis in axisymmetric 2D."""
    from . import geometry as geom
    if not (dx > 0 and r_exp > 0):
        return 0, 0.0

    def axis(c, L):
        """Global cell centres (i + 0.5) dx within r_exp of c."""
        i0 = max(int(math.floor((c - r_exp) / dx)), 0)
        i1 = min(int(math.ceil((c + r_exp) / dx)), int(math.ceil(L / dx)))
        return (np.arange(i0, max(i1, i0) + 1) + 0.5) * dx

    r2 = r_exp * r_exp
    if dim == 3:
        x0, y0, z0 = centre
        X = axis(x0, dims[0])[:, None, None]
        Y = axis(y0, dims[1])[None, :, None]
        Z = axis(z0, dims[2])[None, None, :]
        inside = (X - x0) ** 2 + (Y - y0) ** 2 + (Z - z0) ** 2 <= r2
        n = int(inside.sum())
        V_disc = n * dx ** 3
        V_true = geom.charge_volume_3d(r_exp, x0, y0, z0, *dims)
    else:
        x0, y0 = centre[0], centre[1]
        xs, ys = axis(x0, dims[0]), axis(y0, dims[1])
        inside = (xs[:, None] - x0) ** 2 + (ys[None, :] - y0) ** 2 <= r2
        n = int(inside.sum())
        if geometry == 'axisymmetric':
            # per radian, exactly as core.grid's axisym cell volumes
            V_disc = float((inside * (xs[:, None] * dx * dx)).sum())
        else:
            V_disc = n * dx * dx        # per unit depth
        V_true = geom.charge_volume_2d(geometry, r_exp, x0, y0, *dims)
    return n, (V_disc / V_true if V_true > 0 else 0.0)


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
    core.bc.solid_mask_*). `centres` are the FINE grid axes.

    N2-05: this used to allocate a full-grid boolean mask PER ZONE
    (np.ones(shape) + three broadcast compares + a same-size np.where),
    so its cost scaled with the domain, not with the zones - on a
    320^3 fine grid (32.8 M cells) with a handful of zones it was
    ~1.8 s per plan_levels call, and set_case calls plan_levels twice.
    The axes are ascending, so each zone's inclusive box is exactly an
    index sub-block: searchsorted(lo, 'left') is the first centre
    >= lo and searchsorted(hi, 'right') the first > hi - the same
    cells the mask selected, updated in place on a view. Bit-identical
    by construction and verified against captured baselines
    (night_artifacts/NIGHT2/scripts/n2_levelmap_baseline.py)."""
    dim = len(centres)
    shape = tuple(len(c) for c in centres)
    lv = np.zeros(shape, dtype=np.int8)
    for zone in zones:
        box, level = zone[:2 * dim], zone_level(zone)
        idx = tuple(
            slice(np.searchsorted(centres[a], box[2 * a], side='left'),
                  np.searchsorted(centres[a], box[2 * a + 1], side='right'))
            for a in range(dim))
        sub = lv[idx]                      # a view - updated in place
        np.maximum(sub, np.int8(level), out=sub)
    return lv


def required_level(dx_base, r_exp, n_cells=MIN_EXP_CELLS):
    """Levels needed below dx_base so that r_exp spans `n_cells` cells
    at the finest level (0 when the base already resolves it)."""
    need = dx_base / (r_exp / n_cells)
    return 0 if need <= 1.0 + 1e-12 else int(math.ceil(math.log2(need)))


def auto_charge_zones(dim, dx_base, dims, centres, r_exps, level_cap=None,
                      n_cells=MIN_EXP_CELLS):
    """Nested boxes around each charge for `charge_refine='zone'`. The
    finest zone (level L) spans centre +- 2 r_exp; each coarser zone l
    adds one cell of level l (dx_base / 2**l) so, after snapping, every
    zone sits at least one cell of the next coarser level inside it (the
    2:1 grading rule). Returns (zones, L) with L the level the smallest
    charge needs (clamped by `level_cap`)."""
    L = max(required_level(dx_base, r, n_cells) for r in r_exps)
    if level_cap is not None:
        L = min(L, level_cap)
    zones = []
    for c, r in zip(centres, r_exps):
        Lc = required_level(dx_base, r, n_cells)
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
    amr: int = 0                     # dynamic AMR max level (0 = static)
    display_level: int = 0           # AMR: level of the display grid

    @property
    def dx_fine(self):
        return self.dx_base / (2 ** self.lmax)

    @property
    def refined(self):
        return self.lmax > 0

    @property
    def solid_fine(self):
        if self.solid_base is None:
            return None
        return _fit_shape(expand(self.solid_base, self.lmax),
                          self.levels.shape)

    def meta(self):
        """The picklable record carried in a Result's meta."""
        d = dict(levels=self.levels, lmax=self.lmax,
                 dx_base=self.dx_base, zones=list(self.zones))
        if self.amr:
            d.update(amr=self.amr, display_level=self.display_level)
        return d


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
    # cheap sanity before ANY array is built: a non-positive/non-finite
    # cell size or extent, or a non-finite charge, otherwise reaches
    # `_grid`/`charge_radius` as a ZeroDivisionError, an arange of billions
    # of cells or a nan -> int cast. Raised as ValueError so the setup
    # preview and validate_case both degrade gracefully (geometry only).
    dx0 = float(case.cell_size_m)
    if not (math.isfinite(dx0) and dx0 > 0):
        raise ValueError("cell size must be a positive number")
    for L in dims:
        if not (math.isfinite(float(L)) and float(L) > 0):
            raise ValueError("domain extents must be positive numbers")
    ch = getattr(case, 'charge', None)
    if ch is not None and not math.isfinite(float(ch)):
        raise ValueError("charge must be a finite number")
    amr = int(getattr(case, 'amr_levels', 0) or 0)
    if amr > 0:
        return _plan_amr(case, dims, amr)
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
    n_exp = exp_cells(case)
    if charges and mode != 'zone':
        dx = min(effective_dx(dx, r, case.Lx, n_exp) for _c, r in charges)
    # guard the BASE grid before building it (a tiny dx would arange
    # billions of faces; the global-charge rule already applied above)
    if _grid_cells(dims, dx) > _PLAN_MAX_CELLS:
        raise ValueError(
            f"grid of ~{_grid_cells(dims, dx):,} cells at dx = {dx:.4g} m "
            f"is too large to plan - use a coarser cell size or a smaller "
            f"domain")
    base = _grid(case, dx)
    dx_base = float(base['dx'])

    auto, auto_level = [], 0
    if charges and mode == 'zone':
        axisym = dim == 2 and case.geometry == 'axisymmetric'
        auto, auto_level = auto_charge_zones(
            dim, dx_base, dims, [c for c, _r in charges],
            [r for _c, r in charges], level_cap=1 if axisym else None,
            n_cells=n_exp)

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
    # guard the FINE display grid before allocating its level map / masks
    # (this is the array that OOM'd the setup preview on the 10 m 3D
    # default and the deep-zone checklist case)
    n_fine = 1
    for k in ('x_c', 'y_c', 'z_c')[:dim]:
        n_fine *= len(fine[k])
    if n_fine > _PLAN_MAX_CELLS:
        raise ValueError(
            f"refined display grid of ~{n_fine:,} cells (finest "
            f"{dx_base / (2 ** lmax):.4g} m) is too large to plan - use "
            f"fewer levels or a coarser base cell")
    centres = tuple(fine[k] for k in ('x_c', 'y_c', 'z_c')[:dim])
    levels = level_map(centres, [z for z in zones
                                 if 1 <= zone_level(z) <= MAX_LEVEL])

    plan = Plan(dim=dim, dx_base=dx_base, base=base, fine=fine,
                levels=levels, lmax=lmax, zones=zones, user_zones=user,
                auto_zones=auto, auto_level=auto_level,
                solid_base=_solid_base(case, base), moved=moved)
    plan.n_fine = int(levels.size)
    plan.n_pred = n_cells_from_levels(levels, lmax, plan.solid_fine)
    return plan


def _grid(case, dx):
    if case.dim == 2:
        return make_geometry(case.geometry, case.Lx, case.Ly, dx)
    return make_grid(case.Lx, case.Ly, case.Lz, dx)


def _solid_base(case, base):
    obstacles = getattr(case, 'obstacles', None) or []
    if not obstacles:
        return None
    if case.dim == 2:
        return solid_mask_2d(base['x_c'], base['y_c'], obstacles)
    return solid_mask_3d(base['x_c'], base['y_c'], base['z_c'], obstacles)


def _plan_amr(case, dims, amr):
    """Plan of a dynamic-AMR case. The base grid is the case cell size
    untouched (the charge is resolved by the run-time refinement, not by
    a global cut), the display grid sits at `display_level` <= amr (the
    deepest level whose display grid fits the native cap, unless the
    case names one) and the level map is all-zero: the real structure is
    read back per written time (`remap_from_centres`). Zones are ignored
    here - validation refuses them together with AMR."""
    dim = case.dim
    base = _grid(case, float(case.cell_size_m))
    dx_base = float(base['dx'])
    cap = CELLS_2D_MAX if dim == 2 else CELLS_REFUSE
    D = getattr(case, 'amr_display_level', None)
    if D is None:
        D = display_level_for(dims, dx_base, amr, cap)
    D = int(min(max(int(D), 0), amr))
    fine = base if D == 0 else _grid(case, dx_base / (2 ** D))
    shape = tuple(len(fine[k]) for k in ('x_c', 'y_c', 'z_c')[:dim])
    n_fine = 1
    for s in shape:
        n_fine *= s
    if n_fine > _AMR_MAX_DISPLAY:
        raise ValueError(
            f"AMR display grid of ~{n_fine:,} cells is too large to plan "
            f"- lower the display level or the base cell size")
    levels = np.zeros(shape, dtype=np.int8)
    plan = Plan(dim=dim, dx_base=dx_base, base=base, fine=fine,
                levels=levels, lmax=D, zones=[],
                solid_base=_solid_base(case, base), amr=amr,
                display_level=D)
    plan.n_fine = int(levels.size)
    # t = 0 mesh is the base grid (all display cells are level 0); compute
    # it arithmetically rather than through n_cells_from_levels, whose
    # int64 promotion of a forced-huge display grid could itself OOM.
    n_base = 1
    for k in ('x_c', 'y_c', 'z_c')[:dim]:
        n_base *= len(base[k])
    solid_n = 0 if plan.solid_base is None else int(plan.solid_base.sum())
    plan.n_pred = n_base - solid_n
    return plan


def display_level_for(dims, dx_base, amr_levels, cap):
    """Deepest level d <= amr_levels whose display grid (dx_base / 2**d
    over `dims`) holds at most `cap` cells; 0 when even the base grid
    is over the cap (validation reports that separately)."""
    for d in range(int(amr_levels), -1, -1):
        n = 1
        for L in dims:
            n *= int(round(L / (dx_base / (2 ** d))))
        if n <= cap:
            return d
    return 0


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


def _thin(mask, max_lines):
    """Drop FULL-span interior grid lines until at most `max_lines`
    remain. A line that does not span the whole plane marks a
    refinement-block boundary - the structure - and is always kept, as
    are the two domain edges. Without this a 200-cell axis draws 201
    lines that merge into a solid sheet on screen."""
    if not max_lines:
        return mask
    full = mask.all(axis=1)
    idx = np.flatnonzero(full)
    if len(idx) <= max_lines:
        return mask
    step = int(math.ceil(len(idx) / max_lines))
    keep = set(idx[::step].tolist()) | {0, len(mask) - 1}
    out = mask.copy()
    for i in idx:
        if int(i) not in keep:
            out[i] = False
    return out


def mesh_segments_2d(src2d, u_face, v_face, max_lines=None):
    """Cell-edge segments (N, 2, 2) of a plane: every face between two
    fine cells with different source ids, plus the domain boundary;
    `src2d=None` means a uniform mesh (every fine face). Consecutive
    faces on one line are merged into one segment. `max_lines` thins
    full-span lines per direction so a fine grid stays readable (see
    _thin) - refinement boundaries survive it."""
    u_face = np.asarray(u_face, dtype=float)
    v_face = np.asarray(v_face, dtype=float)
    nu, nv = len(u_face) - 1, len(v_face) - 1
    if src2d is None:
        vert = np.ones((nu + 1, nv), dtype=bool)
        horiz = np.ones((nu, nv + 1), dtype=bool)
    else:
        src = np.asarray(src2d)
        vert = np.ones((nu + 1, nv), dtype=bool)    # faces at u_face[i]
        vert[1:-1] = src[1:] != src[:-1]
        horiz = np.ones((nu, nv + 1), dtype=bool)   # faces at v_face[j]
        horiz[:, 1:-1] = src[:, 1:] != src[:, :-1]
    vert = _thin(vert, max_lines)
    horiz = _thin(horiz.T, max_lines).T
    segs = []
    for i in range(nu + 1):
        for j0, j1 in _runs(vert[i]):
            segs.append(((u_face[i], v_face[j0]), (u_face[i], v_face[j1])))
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


# ── dynamic AMR: a written mesh mapped onto the display grid ────────────────

@dataclass
class MeshMap:
    """How one written mesh maps onto the display grid.

    `remap` (int32, display shape) holds the foam cell covering each
    display cell: -1 in carved (obstacle) cells, -2 where the mesh is
    FINER than the display grid (several foam cells per display cell;
    those are listed in `sub_cells` with their flat C-order display index
    `sub_idx` and weight `sub_w`, summing to 1 per display cell).
    `levels` (int8) is the level drawn there (capped at the display
    level). `counts` = foam cells per level (AMR only)."""
    remap: np.ndarray
    levels: np.ndarray
    n_cells: int
    counts: tuple = ()
    sub_cells: np.ndarray = None
    sub_idx: np.ndarray = None
    sub_w: np.ndarray = None

    @classmethod
    def from_remap(cls, remap, levels, n_cells):
        """Wrap a static `match_cells` remap (no sub-display cells)."""
        return cls(np.asarray(remap, dtype=np.int32),
                   np.asarray(levels, dtype=np.int8), int(n_cells))

    def gather(self, vals, fill=0.0):
        """Foam cell values -> display grid (box-averaging the cells
        finer than the display grid; `fill` in carved cells)."""
        vals = np.asarray(vals, dtype=float)
        out = np.full(self.remap.shape, float(fill))
        m = self.remap >= 0
        out[m] = vals[self.remap[m]]
        if self.sub_cells is not None and len(self.sub_cells):
            acc = np.bincount(self.sub_idx,
                              weights=vals[self.sub_cells] * self.sub_w,
                              minlength=out.size)
            flat = out.reshape(-1)
            k = np.flatnonzero(self.remap.reshape(-1) == -2)
            flat[k] = acc[k]
        return out


def levels_from_centres(C, x0, dx_base, lmax, tol=0.1):
    """Hex-refinement level of each cell from its centre alone (the
    live-slice rows of an AMR run carry no cell size). A level-l cell
    (size dx_base / 2**l) is centred at a half-odd multiple of its own
    size on every axis; at any finer size that centre is an integer
    multiple (half a cell off), so testing the levels finest-first and
    taking the first hit is unambiguous, and `tol` (in cells) only has
    to absorb the file's write precision. `C` (n, dim) are in-plane /
    in-domain centres, `x0` the grid origin. Returns int64 levels, -1
    where no level fits (a torn row of a mid-write sample)."""
    rel = np.asarray(C, dtype=float) - np.asarray(x0, dtype=float)
    out = np.full(len(rel), -1, dtype=np.int64)
    for l in range(int(lmax), -1, -1):
        q = rel / (float(dx_base) / 2 ** l) - 0.5
        hit = (np.abs(q - np.rint(q)) < tol).all(axis=1) & (out < 0)
        out[hit] = l
    return out


def remap_from_centres(C, cell_levels, disp, disp_level, solid_disp=None):
    """Written mesh (cell centres `C` (n, >=dim) + hexRef `cell_levels`
    (n,), 0 = base cell) -> MeshMap on the display grid `disp` (a
    core.grid dict at dx_base / 2**disp_level).

    A level-l cell with l <= D covers a block of s = 2**(D-l) display
    cells per axis whose origin is the block containing the centre,
    floor(C/dx_disp / s) * s - the centre only has to lie INSIDE its
    cell, which also holds for the volume centroids of axisymmetric
    wedge cells (shifted outward in r, up to 2/3 of the cell for the
    axis cell); a cell with l > D falls inside one
    display cell with weight 2**(-dim (l-D)). Every fluid display cell
    must be covered exactly once (weights summing to 1); anything else -
    a gap, an overlap, a centre inside a carved region - raises
    RuntimeError naming the spot, because a silently wrong picture is
    worse than a stopped run."""
    C = np.asarray(C, dtype=float)
    lv = np.asarray(cell_levels).astype(np.int64).ravel()
    if len(lv) != len(C):
        raise ValueError(f"{len(C)} cell centres but {len(lv)} cell levels")
    dim = 3 if 'z_face' in disp else 2
    faces = [np.asarray(disp[k], dtype=float)
             for k in ('x_face', 'y_face', 'z_face')[:dim]]
    shape = tuple(len(f) - 1 for f in faces)
    x0 = np.array([f[0] for f in faces])
    dxd = float(faces[0][1] - faces[0][0])
    D = int(disp_level)
    n = len(C)
    remap = np.full(shape, -1, dtype=np.int32)
    levels = np.full(shape, -1, dtype=np.int8)
    cover = np.zeros(shape, dtype=float)
    cover_flat, remap_flat, levels_flat = (cover.reshape(-1),
                                           remap.reshape(-1),
                                           levels.reshape(-1))
    idx = np.arange(n, dtype=np.int32)
    rel = (C[:, :dim] - x0) / dxd            # centres in display units
    shape_a = np.array(shape)
    subs = []
    for l in np.unique(lv):
        sel = np.flatnonzero(lv == l)
        if l <= D:
            s = 2 ** (D - l)
            origin = np.floor(rel[sel] / s).astype(np.int64) * s
            bad = ((origin < 0).any(axis=1)
                   | (origin + s > shape_a).any(axis=1))
            if bad.any():
                k = int(sel[np.flatnonzero(bad)[0]])
                raise RuntimeError(
                    f"mesh cell {k} at {tuple(np.round(C[k, :dim], 6))} "
                    f"(level {l}) does not fit the display grid")
            for o in np.indices((s,) * dim).reshape(dim, -1).T:
                ij = tuple((origin + o).T)
                remap[ij] = idx[sel]
                levels[ij] = l
                np.add.at(cover, ij, 1.0)
        else:
            i = np.floor(rel[sel]).astype(np.int64)
            bad = ((i < 0).any(axis=1) | (i >= shape_a).any(axis=1))
            if bad.any():
                k = int(sel[np.flatnonzero(bad)[0]])
                raise RuntimeError(
                    f"mesh cell {k} at {tuple(np.round(C[k, :dim], 6))} "
                    f"(level {l}) lies outside the display grid")
            flat = np.ravel_multi_index(tuple(i.T), shape)
            w = 2.0 ** (-dim * (l - D))
            np.add.at(cover_flat, flat, w)
            remap_flat[flat] = -2
            levels_flat[flat] = D
            subs.append((sel.astype(np.int32), flat, w))
    fluid = (np.ones(shape, dtype=bool) if solid_disp is None
             else ~np.asarray(solid_disp, dtype=bool))
    axes = [0.5 * (f[1:] + f[:-1]) for f in faces]

    def _where(k):
        return ', '.join(f"{a[i]:.4g}" for a, i in zip(axes, k))

    if solid_disp is not None:
        hit = (cover > 0) & ~fluid
        if hit.any():
            k = tuple(int(i) for i in np.argwhere(hit)[0])
            raise RuntimeError(
                f"the mesh covers display cell ({_where(k)}) m inside a "
                f"carved (obstacle) region")
    bad = fluid & (np.abs(cover - 1.0) > 1e-6)
    if bad.any():
        k = tuple(int(i) for i in np.argwhere(bad)[0])
        raise RuntimeError(
            f"display cell ({_where(k)}) m is covered {cover[k]:.4g} times "
            f"by the mesh (expected exactly once) - the written mesh does "
            f"not tile the display grid")
    sub_cells = sub_idx = sub_w = None
    if subs:
        sub_cells = np.concatenate([c for c, _f, _w in subs])
        sub_idx = np.concatenate([f for _c, f, _w in subs])
        sub_w = np.concatenate([np.full(len(f), w) for _c, f, w in subs])
    counts = tuple(int(c) for c in
                   np.bincount(lv, minlength=max(D, int(lv.max())) + 1))
    return MeshMap(remap, levels, n, counts, sub_cells, sub_idx, sub_w)


def validate_amr(case, plan, rho0=None):
    """(errors, warnings, notes) for the AMR settings of a case whose
    plan came from `plan_levels` with `amr_levels > 0`."""
    errors, warnings, notes = [], [], []
    amr = int(plan.amr)
    est = (getattr(case, 'amr_estimator', 'densityGradient')
           or 'densityGradient')
    if est not in AMR_ESTIMATORS:
        errors.append(f"Unknown AMR error estimator '{est}' (use "
                      + ' or '.join(repr(e) for e in AMR_ESTIMATORS) + ")")
    if not 1 <= amr <= MAX_AMR_LEVEL:
        errors.append(f"AMR levels must be 1..{MAX_AMR_LEVEL}")
    lo = float(getattr(case, 'amr_refine', 0.4))
    un = float(getattr(case, 'amr_unrefine', 0.2))
    if lo <= 0 or un <= 0:
        errors.append("AMR refine / unrefine thresholds must be > 0")
    elif un > lo:
        errors.append("The AMR unrefine threshold must not exceed the "
                      "refine threshold (cells would refine and unrefine "
                      "in turn)")
    interval = int(getattr(case, 'amr_interval', 2))
    buffer = int(getattr(case, 'amr_buffer', 2))
    if interval < 1:
        errors.append("AMR refine interval must be >= 1 step")
    if buffer < 1:
        errors.append("AMR buffer layers must be >= 1")
    max_cells = int(getattr(case, 'amr_max_cells', 0) or 0)
    if max_cells < 0:
        errors.append("AMR max cells must be >= 0 (0 = default)")
    D = getattr(case, 'amr_display_level', None)
    if D is not None and not 0 <= int(D) <= amr:
        errors.append(f"AMR display level must be 0..{amr} (the AMR "
                      f"levels)")
    dx_base = plan.dx_base
    if (getattr(case, 'init_mode', 'charge') == 'charge' and case.charge
            and 1 <= amr <= MAX_AMR_LEVEL):
        n_exp = exp_cells(case)
        need = max(required_level(dx_base, r, n_exp)
                   for _c, r in _charges(case, rho0))
        if need > amr:
            errors.append(
                f"Resolving the charge ({n_exp} cells across its "
                f"radius) needs AMR level {need} (finest "
                f"{dx_base / 2 ** need:.5g} m) - raise the AMR levels or "
                f"lower the base cell to at most "
                f"{dx_base * 2 ** (amr - need):.5g} m")
    if plan.dim == 2 and case.geometry == 'axisymmetric':
        warnings.append("Axisymmetric AMR: the wedge axis cells are prisms "
                        "and never refine, so the charge stays coarse on "
                        "the axis column (planar 2D refines everywhere)")
    if errors:
        return errors, warnings, notes
    Dp = plan.display_level
    notes.append(f"AMR ({est}): up to {amr} level(s) below the "
                 f"{dx_base:.5g} m base cell (finest "
                 f"{dx_base / 2 ** amr:.5g} m), refining every {interval} "
                 f"step(s) with {buffer} buffer layer(s)")
    if Dp < amr:
        notes.append(f"Results are displayed at level {Dp} "
                     f"({dx_base / 2 ** Dp:.5g} m, {plan.n_fine:,} cells); "
                     f"cells finer than that are box-averaged")
    else:
        notes.append(f"Results are resampled to the finest level "
                     f"({plan.n_fine:,} display cells)")
    notes.append(f"The mesh starts at ~{plan.n_pred:,} cells and may grow "
                 f"to {max_cells or FOAM_CELLS_WARN:,} (maxCells)")
    return errors, warnings, notes
