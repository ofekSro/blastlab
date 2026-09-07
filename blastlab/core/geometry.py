"""Domain geometry shared by the native 2D/3D solvers, the blastFoam
backend and the post-mortem loader (ROADMAP A2): open-boundary edge
masks, the charge-to-boundary distances that drive the arrival stop /
progress / snapshot scheduling, the snapshot trigger radii and the
per-cell distance-to-charge fields.

Every function is a pure drop-in for the inline code it replaced. The
native solvers' byte-pinned transcripts (test_regression) depend on the
numbers being identical, so keep the expressions exactly as they are.
"""

import numpy as np

SIDES_2D = ('x_lo', 'x_hi', 'y_lo', 'y_hi')
SIDES_3D = SIDES_2D + ('z_lo', 'z_hi')


def _side_slice(side, ndim):
    sl = [slice(None)] * ndim
    sl['xyz'.index(side[0])] = 0 if side.endswith('lo') else -1
    return tuple(sl)


def open_edge_mask(shape, bcs, fluid=None, sides=None):
    """Cells on an OPEN boundary (a wall reflection must not end a run).

    `fluid` (bool mask) drops solid/carved cells - they hold frozen
    ambient air; `sides` restricts which boundaries count (the backend's
    axisymmetric 2D skips x_lo, the symmetry axis)."""
    if sides is None:
        sides = SIDES_2D if len(shape) == 2 else SIDES_3D
    edge = np.zeros(shape, dtype=bool)
    for side in sides:
        if bcs[side] == 'open':
            edge[_side_slice(side, len(shape))] = True
    if fluid is not None:
        edge &= fluid
    return edge


def stop_dists_2d(Lx, Ly, x0, y0, bcs, x_lo_counts=True):
    """Charge-to-open-boundary distances (2D). `x_lo_counts=False` for
    axisymmetric runs, where x_lo is the axis. Closed box: the far
    corner, so snapshots cover the whole domain (the safety cap stops
    such a run)."""
    dists = []
    if bcs['x_hi'] == 'open':
        dists.append(Lx - x0)
    if bcs['x_lo'] == 'open' and x_lo_counts:
        dists.append(x0)
    if bcs['y_lo'] == 'open':
        dists.append(y0)
    if bcs['y_hi'] == 'open':
        dists.append(Ly - y0)
    if not dists:   # closed box: cover the whole domain
        corners = [(0.0, 0.0), (Lx, 0.0), (0.0, Ly), (Lx, Ly)]
        dists.append(max(np.hypot(cx - x0, cy - y0) for cx, cy in corners))
    return dists


def stop_dists_3d(Lx, Ly, Lz, centers, bcs):
    """Charge-to-open-boundary distances (3D): per open side the distance
    from the NEAREST charge centre (ROADMAP B21 - the stop itself is
    pressure-based; these only size progress and snapshots). Closed box:
    the far corner from the primary (first) centre."""
    x0, y0, z0 = centers[0]
    dists = []
    for side, d_of in (('x_lo', lambda c: c[0]),
                       ('x_hi', lambda c: Lx - c[0]),
                       ('y_lo', lambda c: c[1]),
                       ('y_hi', lambda c: Ly - c[1]),
                       ('z_lo', lambda c: c[2]),
                       ('z_hi', lambda c: Lz - c[2])):
        if bcs[side] == 'open':
            dists.append(min(float(d_of(c)) for c in centers))
    if not dists:   # closed box: cover the whole domain
        dists = [max(float(np.hypot(np.hypot(cx - x0, cy - y0), cz - z0))
                     for cx in (0, Lx) for cy in (0, Ly)
                     for cz in (0, Lz))]
    return dists


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
