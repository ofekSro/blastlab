"""HLL approximate Riemann solvers (vectorized).

Two implementations exist on purpose:

- `hll_fluxes(..., n)` - generic N-row directional solver serving both the
  2D state [rho, rho*u, rho*v, E] and the 3D state
  [rho, rho*u, rho*v, rho*w, E]. Momentum rows are 1..N-2, energy is the
  last row; transverse momenta are advected passively.

- `hll_fluxes_1d` - the original blast1d solver for U = [rho, rho*u, E].
  It computes the mass flux as `rho*u` directly, whereas the generic one
  computes `rho * (rho*u / rho)`; these are NOT bitwise equal, and the 1D
  solver's outputs are pinned bit-for-bit by the regression suites, so it
  stays a separate function.
"""

import numpy as np


def hll_fluxes(U_L, U_R, p_L, p_R, c_L, c_R, n):
    """
    HLL numerical flux for a sweep whose face normal corresponds to
    momentum row `n` (1 = x, 2 = y, 3 = z). Works for any number of
    passive transverse momentum rows; energy is the last row.

    U_L, U_R : (N, ...) conserved state left/right of each face
    Returns F : (N, ...)
    """
    n_rows   = U_L.shape[0]
    mom_rows = range(1, n_rows - 1)
    rho_L = np.maximum(U_L[0], 1e-10)
    rho_R = np.maximum(U_R[0], 1e-10)
    un_L  = U_L[n] / rho_L          # normal velocity
    un_R  = U_R[n] / rho_R

    F_L = np.empty_like(U_L)
    F_L[0]  = U_L[0] * un_L
    F_L[n]  = U_L[n] * un_L + p_L
    for t in mom_rows:
        if t != n:
            F_L[t] = U_L[t] * un_L
    F_L[-1] = (U_L[-1] + p_L) * un_L

    F_R = np.empty_like(U_R)
    F_R[0]  = U_R[0] * un_R
    F_R[n]  = U_R[n] * un_R + p_R
    for t in mom_rows:
        if t != n:
            F_R[t] = U_R[t] * un_R
    F_R[-1] = (U_R[-1] + p_R) * un_R

    # Wave speed estimates (same as blast1d)
    s_L = np.minimum(un_L - c_L, un_R - c_R)
    s_R = np.maximum(un_L + c_L, un_R + c_R)
    ds  = np.maximum(s_R - s_L, 1e-10)

    F_hll = (s_R * F_L - s_L * F_R + s_L * s_R * (U_R - U_L)) / ds

    # Two-step upwind select; frees the large intermediates early (matters
    # near the 3D cell cap). Equivalent to the single nested np.where
    # because s_L >= 0 and s_R <= 0 cannot hold simultaneously (c > 0).
    F = np.where(s_L[np.newaxis] >= 0.0, F_L, F_hll)
    del F_L, F_hll
    F = np.where(s_R[np.newaxis] <= 0.0, F_R, F)
    del F_R
    return F


def hll_fluxes_1d(U_L, U_R, p_L, p_R, c_L, c_R):
    """
    HLL numerical flux at a set of faces (1D spherical solver's layout).

    Inputs
    ------
    U_L, U_R : (3, M)  conserved state left/right of each face
    p_L, p_R : (M,)    pressure
    c_L, c_R : (M,)    sound speed

    Returns
    -------
    F : (3, M)  HLL flux
    """
    rho_L, rhou_L, E_L = U_L
    rho_R, rhou_R, E_R = U_R
    u_L = rhou_L / rho_L
    u_R = rhou_R / rho_R

    F_L = np.array([rhou_L,
                    rhou_L * u_L + p_L,
                    (E_L + p_L) * u_L])
    F_R = np.array([rhou_R,
                    rhou_R * u_R + p_R,
                    (E_R + p_R) * u_R])

    # Roe-averaged wave speed estimates
    s_L = np.minimum(u_L - c_L, u_R - c_R)
    s_R = np.maximum(u_L + c_L, u_R + c_R)
    ds  = np.maximum(s_R - s_L, 1e-10)

    F_hll = (s_R * F_L - s_L * F_R + s_L * s_R * (U_R - U_L)) / ds

    # Select upwind / HLL based on wave-speed sign
    F = np.where(s_L[np.newaxis, :] >= 0.0, F_L,
        np.where(s_R[np.newaxis, :] <= 0.0, F_R, F_hll))
    return F

