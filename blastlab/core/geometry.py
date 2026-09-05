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
