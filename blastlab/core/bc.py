"""Face-flux assembly with boundary conditions and obstacle walls.

`_face_fluxes_axis0` is dimension-agnostic: it sweeps spatial axis 0 with
the normal momentum in row 1, and only slices axes 0/1, so any number of
trailing spatial axes works. `face_fluxes` dispatches other directions by
swapping momentum rows and moving the sweep axis to the front.
"""

import numpy as np

from .riemann import hll_fluxes


def _face_fluxes_axis0(U, p, c, bc_lo, bc_hi, solid):
    """
    HLL fluxes at all faces along spatial axis 0 (normal momentum = row 1),
    with one ghost layer per side ('open' copy / 'wall' mirror) and mirror
    treatment at fluid|solid faces. Returns F (N, Na+1, ...).
    """
    g_lo = U[:, :1].copy()
    if bc_lo == 'wall':
        g_lo[1] = -g_lo[1]
    g_hi = U[:, -1:].copy()
    if bc_hi == 'wall':
        g_hi[1] = -g_hi[1]

    U_ext = np.concatenate([g_lo, U, g_hi], axis=1)
    p_ext = np.concatenate([p[:1], p, p[-1:]], axis=0)
    c_ext = np.concatenate([c[:1], c, c[-1:]], axis=0)

    U_L, U_R = U_ext[:, :-1], U_ext[:, 1:]
    p_L, p_R = p_ext[:-1], p_ext[1:]
    c_L, c_R = c_ext[:-1], c_ext[1:]

    have_solid = solid.any()
    if have_solid:
        ghost = np.zeros((1,) + solid.shape[1:], dtype=bool)
        s_ext = np.concatenate([ghost, solid, ghost], axis=0)
        sL, sR = s_ext[:-1], s_ext[1:]

        U_L, U_R = U_L.copy(), U_R.copy()
        p_L, p_R = p_L.copy(), p_R.copy()
        c_L, c_R = c_L.copy(), c_R.copy()

        fs = ~sL & sR    # fluid | solid : solid side mirrors the fluid side
        if fs.any():
            U_R[:, fs] = U_L[:, fs]
            U_R[1, fs] = -U_R[1, fs]
            p_R[fs], c_R[fs] = p_L[fs], c_L[fs]
        sf = sL & ~sR    # solid | fluid
        if sf.any():
            U_L[:, sf] = U_R[:, sf]
            U_L[1, sf] = -U_L[1, sf]
            p_L[sf], c_L[sf] = p_R[sf], c_R[sf]

    F = hll_fluxes(U_L, U_R, p_L, p_R, c_L, c_R, n=1)

    if have_solid:
        ss = sL & sR     # solid | solid : no flux
        if ss.any():
            F[:, ss] = 0.0
    return F


def face_fluxes(U, p, c, n, bc_lo, bc_hi, solid):
    """
    Face fluxes for sweep direction n (1 = x, 2 = y, 3 = z). Directions
    beyond the first reuse the axis-0 core with momentum rows swapped and
    the sweep spatial axis moved to the front.
    """
    if n == 1:
        return _face_fluxes_axis0(U, p, c, bc_lo, bc_hi, solid)
    rows = list(range(U.shape[0]))
    rows[1], rows[n] = rows[n], rows[1]
    U_sw = np.moveaxis(U[rows], n, 1)              # U[rows] copies
    F_sw = _face_fluxes_axis0(U_sw,
                              np.moveaxis(p, n - 1, 0),
                              np.moveaxis(c, n - 1, 0),
                              bc_lo, bc_hi,
                              np.moveaxis(solid, n - 1, 0))
    return np.moveaxis(F_sw[rows], 1, n)


def solid_mask_2d(x_c, y_c, obstacles):
    """
    Boolean (Nx, Ny) mask of cells inside any axis-aligned rectangle.
    obstacles: list of (x0, x1, y0, y1).
    """
    solid = np.zeros((len(x_c), len(y_c)), dtype=bool)
    X = x_c[:, None]
    Y = y_c[None, :]
    for (x0, x1, y0, y1) in obstacles or []:
        solid |= (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
    return solid


def solid_mask_3d(x_c, y_c, z_c, obstacles):
    """
    Boolean (Nx,Ny,Nz) mask of cells inside any axis-aligned box.
    obstacles: list of (x0, x1, y0, y1, z0, z1).
    """
    solid = np.zeros((len(x_c), len(y_c), len(z_c)), dtype=bool)
    X = x_c[:, None, None]
    Y = y_c[None, :, None]
    Z = z_c[None, None, :]
    for (x0, x1, y0, y1, z0, z1) in obstacles or []:
        solid |= ((X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
                  & (Z >= z0) & (Z <= z1))
    return solid
