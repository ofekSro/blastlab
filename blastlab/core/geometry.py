"""Domain geometry shared by the native 2D/3D solvers, the blastFoam
backend and the post-mortem loader (ROADMAP A2): terminating-boundary
edge masks, the charge-to-boundary distances that drive the arrival stop
/ progress / snapshot scheduling, the snapshot trigger radii and the
per-cell distance-to-charge fields; and the dropped-gauge tests and
wording every surface shares (GUI-15 (d)).

Two different questions are asked of `bcs` here and they no longer have
the same answer (T50): only a `terminate` side ENDS a run, while ANY
non-`reflect` side is one the wave leaves through, which is what sizes
the snapshot radii and the progress bar.

Every function is a pure drop-in for the inline code it replaced. The
native solvers' byte-pinned transcripts (test_regression) depend on the
numbers being identical, so keep the expressions exactly as they are.
"""

import numpy as np

from .bc import normalize_bc

SIDES_2D = ('x_lo', 'x_hi', 'y_lo', 'y_hi')
SIDES_3D = SIDES_2D + ('z_lo', 'z_hi')


def _side_slice(side, ndim):
    sl = [slice(None)] * ndim
    sl['xyz'.index(side[0])] = 0 if side.endswith('lo') else -1
    return tuple(sl)


def _leaves(bcs, side):
    """True where the wave leaves the domain: anything but a reflection."""
    return normalize_bc(bcs[side]) != 'reflect'


def terminate_edge_mask(shape, bcs, fluid=None, sides=None):
    """Cells on a TERMINATE boundary - the sides whose shock arrival ends
    the run. A reflection never does, and since T50 neither does a plain
    `transmit` side (pre-T50 `open` did both; normalize_bcs maps it).

    `fluid` (bool mask) drops solid/carved cells - they hold frozen
    ambient air; `sides` restricts which boundaries count (the backend's
    axisymmetric 2D skips x_lo, the symmetry axis)."""
    if sides is None:
        sides = SIDES_2D if len(shape) == 2 else SIDES_3D
    edge = np.zeros(shape, dtype=bool)
    for side in sides:
        if normalize_bc(bcs[side]) == 'terminate':
            edge[_side_slice(side, len(shape))] = True
    if fluid is not None:
        edge &= fluid
    return edge


def stop_dists_2d(Lx, Ly, x0, y0, bcs, x_lo_counts=True):
    """Charge-to-boundary distances over the sides the wave leaves
    through - transmit AND terminate, which is the pre-T50 `open` set, so
    snapshot radii and the progress bar are unchanged by the rename.
    `x_lo_counts=False` for axisymmetric runs, where x_lo is the axis.
    Fully reflecting box: the far corner, so snapshots cover the whole
    domain (the safety cap stops such a run)."""
    dists = []
    if _leaves(bcs, 'x_hi'):
        dists.append(Lx - x0)
    if _leaves(bcs, 'x_lo') and x_lo_counts:
        dists.append(x0)
    if _leaves(bcs, 'y_lo'):
        dists.append(y0)
    if _leaves(bcs, 'y_hi'):
        dists.append(Ly - y0)
    if not dists:   # fully reflecting box: cover the whole domain
        corners = [(0.0, 0.0), (Lx, 0.0), (0.0, Ly), (Lx, Ly)]
        dists.append(max(np.hypot(cx - x0, cy - y0) for cx, cy in corners))
    return dists


def stop_dists_3d(Lx, Ly, Lz, centers, bcs):
    """Charge-to-boundary distances (3D) over the sides the wave leaves
    through (see stop_dists_2d): per side the distance from the NEAREST
    charge centre (ROADMAP B21 - the stop itself is pressure-based; these
    only size progress and snapshots). Fully reflecting box: the far
    corner from the primary (first) centre."""
    if not centers:     # see d_charge_3d: pass the burst point instead
        raise ValueError('stop_dists_3d needs at least one centre')
    x0, y0, z0 = centers[0]
    dists = []
    for side, d_of in (('x_lo', lambda c: c[0]),
                       ('x_hi', lambda c: Lx - c[0]),
                       ('y_lo', lambda c: c[1]),
                       ('y_hi', lambda c: Ly - c[1]),
                       ('z_lo', lambda c: c[2]),
                       ('z_hi', lambda c: Lz - c[2])):
        if _leaves(bcs, side):
            dists.append(min(float(d_of(c)) for c in centers))
    if not dists:   # fully reflecting box: cover the whole domain
        dists = [max(float(np.hypot(np.hypot(cx - x0, cy - y0), cz - z0))
                     for cx in (0, Lx) for cy in (0, Ly)
                     for cz in (0, Lz))]
    return dists


def plane_gauges(points, sl, coords, tol, numbers=None):
    """The gauges a 3D live/animated plane actually cuts, as
    [(number, u, v), ...] in that plane's own coordinates (T53).

    `sl` is the plane selector (a tuple with one integer index), `coords`
    the (x_c, y_c, z_c) cell centres and `tol` the half-width that still
    counts as "on the plane" (one cell). A gauge a metre off the slice
    must not be drawn as if it sat on it. `numbers` (P1-24) labels each
    point with its entered gauge number; None numbers them 1, 2, ..."""
    axis = next(a for a, x in enumerate(sl) if not isinstance(x, slice))
    plane = float(coords[axis][int(sl[axis])])
    keep = [a for a in range(3) if a != axis]
    out = []
    for n, pt in enumerate(points):
        if abs(float(pt[axis]) - plane) > tol:
            continue
        num = n + 1 if numbers is None else int(numbers[n])
        out.append((num, float(pt[keep[0]]), float(pt[keep[1]])))
    return out


# ── Dropped gauges: the tests and the one wording (GUI-15 (d), D5) ──────────
# Shared by the validation warning (services/validation), the Run and
# Results screens (ui/run_gauges, ui/results_gauges) and the native
# solvers' log lines (solver2d / solver3d), so every surface names a
# dropped gauge alike.

#: why a gauge outside the domain is dropped (GUI-13 (e))
OUTSIDE_DOMAIN = 'outside the domain'


def gauge_drop_reason(wall, inside, outside=False):
    """`inside Wall 2` / `within a cell of Wall 2`: why the solver drops a
    gauge for obstacle `wall` (1-based, as the tree names it), or
    `outside the domain` when `outside`. A gauge not strictly inside is
    dropped because the cell it samples is solid: it lies within a cell
    of the wall, on whichever side (GUI-15 (d), the owner's wording).
    One wording for the validation warning, the Run and Results screens'
    dropped-gauge note and the native solvers' log (D201, GUI-12 A4,
    GUI-13 (e))."""
    if outside:
        return OUTSIDE_DOMAIN
    return f'inside Wall {wall}' if inside else f'within a cell of Wall {wall}'


def _in_box_closed(pt, boxes):
    """The 1-based index of the first box `pt` lies in, faces included
    (the closed test of core/bc.solid_mask_* and the foam writer's
    `_in_obstacle`), 0 when none."""
    for i, box in enumerate(boxes, start=1):
        if len(box) >= 2 * len(pt) and all(
                lo <= float(v) <= hi
                for v, lo, hi in zip(pt, box[0::2], box[1::2])):
            return i
    return 0


def _in_obstacle_open(pt, obstacles):
    """The 1-based index of the first obstacle box gauge `pt` lies
    strictly inside (open box, the test of ui/scaled_distance.where's
    `inside`), 0 when none. Only the
    wording of the drop warning now: whether a gauge is dropped at all
    is each solver's own rule (services/validation `_gauge_drop_rule`,
    F44), which keeps a native gauge within half a cell of an off-grid
    face and drops one on or just outside a face (verify 11b, UXR-2,
    D201)."""
    n = len(pt)
    if n < 2:
        return 0
    for i, box in enumerate(obstacles or [], start=1):
        if len(box) < 2 * n:
            continue
        if all(float(lo) < float(v) < float(hi)
               for v, lo, hi in zip(pt, box[0::2], box[1::2])):
            return i
    return 0


def snap_radii(r_start, dists, n_snapshots):
    """Native snapshot trigger radii: evenly spaced between the charge
    (or the remapped shock front) and the nearest stop distance, both
    endpoints excluded - the final state is always recorded on its own.
    Snapshots fire on shock-front POSITION, not time: a strong blast
    crosses the domain far faster than the acoustic estimate."""
    return list(np.linspace(r_start, min(dists), n_snapshots + 1)[1:-1])


def d_charge_2d(x_c, y_c, x0, y0):
    """Per-cell distance to the charge centre (shock-front radius metric)."""
    return np.sqrt((x_c[:, None] - x0) ** 2 + (y_c[None, :] - y0) ** 2)


def d_charge_3d(x_c, y_c, z_c, centers):
    """Per-cell distance to the NEAREST charge centre (multi-charge
    aware), float32 to bound memory on big grids."""
    if not len(centers):
        # a profile-initialised stage has no charge list - the caller
        # must pass the burst point (the profile's own centre) instead
        raise ValueError('d_charge_3d needs at least one centre')
    d = None
    for cx, cy, cz in centers:
        di = np.sqrt((x_c[:, None, None] - cx) ** 2
                     + (y_c[None, :, None] - cy) ** 2
                     + (z_c[None, None, :] - cz) ** 2)
        d = di if d is None else np.minimum(d, di)
    return d.astype(np.float32)


# ── Resolved-charge volumes (B24 / T36) ─────────────────────────────────────
# The resolved charge is a stair-stepped set of cells whose total volume
# is ±3 % off the true sphere depending on where the centre falls relative
# to the faces. The solvers rescale the products' specific energy by
# V_true / V_discretised so the initial energy equals the requested
# charge. V_true is the sphere CLIPPED to the domain (a charge crossing a
# wall is a deliberate surface burst - the part outside stays outside),
# in the same volume metric as the solver's cell volumes: planar 2D per
# unit depth, axisymmetric per radian, 3D absolute.

def _disc_quadrant_area(r, a, b):
    """Area of the disc |p| <= r inside the quadrant [0, a] x [0, b]
    (a, b >= 0 measured from the disc centre). Closed form."""
    a = min(a, r)
    b = min(b, r)
    if a <= 0.0 or b <= 0.0:
        return 0.0
    xs = np.sqrt(max(r * r - b * b, 0.0))      # where sqrt(r²-x²) == b
    if xs >= a:
        return a * b

    def F(x):                                  # ∫ sqrt(r²-x²) dx
        return 0.5 * (x * np.sqrt(max(r * r - x * x, 0.0))
                      + r * r * np.arcsin(min(x / r, 1.0)))
    return float(xs * b + F(a) - F(xs))


def disc_box_area(r, a1, a2, b1, b2):
    """Area of the disc |p| <= r clipped to [-a1, a2] x [-b1, b2] (the
    four numbers are the distances from the centre to the sides)."""
    return (_disc_quadrant_area(r, a1, b1) + _disc_quadrant_area(r, a2, b1)
            + _disc_quadrant_area(r, a1, b2) + _disc_quadrant_area(r, a2, b2))


def charge_volume_2d(geometry, r, x0, y0, Lx, Ly):
    """True volume of a resolved charge of radius r clipped to the 2D
    domain, in make_geometry's volume metric: planar = disc area per
    unit depth, axisymmetric = sphere volume PER RADIAN (the 2*pi cancels
    against the per-radian cell volumes)."""
    if geometry == 'planar':
        return disc_box_area(r, x0, Lx - x0, y0, Ly - y0)
    # Axisymmetric: the sphere sits on the axis; it is clipped by the
    # planes y = 0 / y = Ly and by the outer cylinder x = Lx. Per radian
    # the cross-section at s = y - y0 is ½ min(r² - s², Lx²): integrate
    # the two polynomial pieces exactly.
    s_lo, s_hi = -min(y0, r), min(Ly - y0, r)

    def G(s):                                  # ∫ ½ (r² - s²) ds
        return 0.5 * (r * r * s - s ** 3 / 3.0)
    if r <= Lx:
        return float(G(s_hi) - G(s_lo))
    sc = np.sqrt(r * r - Lx * Lx)              # |s| < sc: cylinder clips

    def sphere_part(a, b):
        return G(b) - G(a) if b > a else 0.0
    V = (sphere_part(s_lo, min(-sc, s_hi)) + sphere_part(max(sc, s_lo), s_hi)
         + 0.5 * Lx * Lx * max(min(sc, s_hi) - max(-sc, s_lo), 0.0))
    return float(V)


def charge_volume_3d(r, x0, y0, z0, Lx, Ly, Lz):
    """Volume of the ball of radius r about (x0, y0, z0) clipped to the
    box [0, Lx] x [0, Ly] x [0, Lz]. Exact for an untruncated charge;
    a clipped one integrates the closed-form disc-in-box area along z
    (Gauss-Legendre on the smooth pieces, ~1e-13 relative)."""
    a1, a2, b1, b2, c1, c2 = x0, Lx - x0, y0, Ly - y0, z0, Lz - z0
    if min(a1, a2, b1, b2, c1, c2) >= r:
        return 4.0 / 3.0 * np.pi * r ** 3
    # z - z0 = r sin(t): disc radius r cos(t), dz = r cos(t) dt. The
    # disc-in-box area is analytic between the radii where the disc
    # first reaches a side (d) or a corner (hypot); split there, and map
    # each piece through a smoothstep so the sqrt-type kinks at the
    # split points do not slow the quadrature down.
    t_lo, t_hi = -np.arcsin(min(c1, r) / r), np.arcsin(min(c2, r) / r)
    ds = [a1, a2, b1, b2] + [np.hypot(a, b) for a in (a1, a2)
                             for b in (b1, b2)]
    pts = {t_lo, t_hi}
    for d in ds:
        if 0.0 < d < r:
            t = float(np.arccos(d / r))
            pts.update(u for u in (t, -t) if t_lo < u < t_hi)
    pts = sorted(pts)
    nodes, weights = np.polynomial.legendre.leggauss(64)
    u = 0.5 * (nodes + 1.0)                    # [0, 1]
    smooth, dsmooth = 3 * u ** 2 - 2 * u ** 3, 6 * u * (1 - u)
    V = 0.0
    for ta, tb in zip(pts[:-1], pts[1:]):
        for s, dsu, w in zip(smooth, dsmooth, weights):
            t = ta + (tb - ta) * s
            rho = r * np.cos(t)
            V += (w * 0.5 * (tb - ta) * dsu
                  * disc_box_area(rho, a1, a2, b1, b2) * r * np.cos(t))
    return float(V)
