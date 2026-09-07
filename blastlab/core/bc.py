"""Face-flux assembly with boundary conditions and obstacle walls.

`_face_fluxes_axis0` is dimension-agnostic: it sweeps spatial axis 0 with
the normal momentum in row 1, and only slices axes 0/1, so any number of
trailing spatial axes works. `face_fluxes` dispatches other directions by
swapping momentum rows and moving the sweep axis to the front.
"""

import numpy as np

from .riemann import hll_fluxes


def minmod(a, b):
    """The minmod slope limiter: the smaller-magnitude of two one-sided
    differences when they agree in sign, zero at an extremum (T47/N10)."""
    return np.where(a * b > 0.0,
                    np.where(np.abs(a) < np.abs(b), a, b), 0.0)


def muscl_states(U_ext, solid_ext=None):
    """Limited MUSCL face states from a ghost-extended conserved state:
    for face i+1/2, L = U_i + s_i/2 and R = U_{i+1} - s_{i+1}/2 with
    minmod slopes along axis 1. Slopes are zeroed on solid cells and
    their fluid neighbours (the wall mirror handles those faces), and a
    face whose reconstructed density or internal energy is not positive
    falls back to the first-order pair - robust exactly where a strong
    blast front would make an unlimited slope unphysical."""
    dq = np.diff(U_ext, axis=1)
    slope = np.zeros_like(U_ext)
    slope[:, 1:-1] = minmod(dq[:, :-1], dq[:, 1:])
    if solid_ext is not None and solid_ext.any():
        near = solid_ext.copy()
        near[:-1] |= solid_ext[1:]
        near[1:] |= solid_ext[:-1]
        slope[:, near] = 0.0
    U_L = U_ext[:, :-1] + 0.5 * slope[:, :-1]
    U_R = U_ext[:, 1:] - 0.5 * slope[:, 1:]

    def bad(Us):
        rho = Us[0]
        ke = 0.5 * sum(Us[k] ** 2 for k in range(1, Us.shape[0] - 1)) \
            / np.maximum(rho, 1e-30)
        return (rho <= 1e-10) | (Us[-1] - ke <= 0.0)

    fall = bad(U_L) | bad(U_R)
    if fall.any():
        U_L = U_L.copy()
        U_R = U_R.copy()
        U_L[:, fall] = U_ext[:, :-1][:, fall]
        U_R[:, fall] = U_ext[:, 1:][:, fall]
    return U_L, U_R


def _face_fluxes_axis0(U, p, c, bc_lo, bc_hi, solid,
                       order=1, phase=None, pc_of=None):
    """
    HLL fluxes at all faces along spatial axis 0 (normal momentum = row 1),
    with one ghost layer per side ('open' copy / 'wall' mirror) and mirror
    treatment at fluid|solid faces. Returns F (N, Na+1, ...).

    `order=2` (T47/N10, opt-in) reconstructs the face states with
    limited MUSCL slopes and recomputes each side's p and c from its
    reconstructed state via `pc_of(rho, e, phase_side)` - the solver
    supplies it because the EOS dispatch (air/JWL + material) lives
    there. The default order-1 path is untouched and byte-identical.
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

    if order == 2:
        s_ext0 = None
        if solid is not None and solid.any():
            ghost = np.zeros((1,) + solid.shape[1:], dtype=bool)
            s_ext0 = np.concatenate([ghost, solid, ghost], axis=0)
        U_L, U_R = muscl_states(U_ext, s_ext0)
        ph_ext = np.concatenate([phase[:1], phase, phase[-1:]], axis=0)

        def side_pc(Us):
            rho = np.maximum(Us[0], 1e-10)
            ke = 0.5 * sum(Us[k] ** 2 for k in range(1, Us.shape[0] - 1)) \
                / rho
            e = np.maximum((Us[-1] - ke) / rho, 1.0)
            return e

        e_L, e_R = side_pc(U_L), side_pc(U_R)
        p_L, c_L = pc_of(np.maximum(U_L[0], 1e-10), e_L, ph_ext[:-1])
        p_R, c_R = pc_of(np.maximum(U_R[0], 1e-10), e_R, ph_ext[1:])
    else:
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


def face_fluxes(U, p, c, n, bc_lo, bc_hi, solid,
                order=1, phase=None, pc_of=None):
    """
    Face fluxes for sweep direction n (1 = x, 2 = y, 3 = z). Directions
    beyond the first reuse the axis-0 core with momentum rows swapped and
    the sweep spatial axis moved to the front.
    """
    if n == 1:
        return _face_fluxes_axis0(U, p, c, bc_lo, bc_hi, solid,
                                  order=order, phase=phase, pc_of=pc_of)
    rows = list(range(U.shape[0]))
    rows[1], rows[n] = rows[n], rows[1]
    U_sw = np.moveaxis(U[rows], n, 1)              # U[rows] copies
    F_sw = _face_fluxes_axis0(U_sw,
                              np.moveaxis(p, n - 1, 0),
                              np.moveaxis(c, n - 1, 0),
                              bc_lo, bc_hi,
                              np.moveaxis(solid, n - 1, 0),
                              order=order,
                              phase=(None if phase is None else
                                     np.moveaxis(phase, n - 1, 0)),
                              pc_of=pc_of)
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
