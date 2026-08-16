"""Uniform-grid builders and geometric metrics for the three solvers."""

import numpy as np


def make_grid_1d(radius_m, dr):
    """
    Uniform 1D radial grid with spherical metrics.

    Returns r_face (N+1,), r (N,) cell centres, A_face (N+1,) = 4*pi*r^2,
    V_cell (N,) spherical shell volumes.
    """
    r_face = np.arange(0.0, radius_m + 0.5 * dr, dr)
    r      = 0.5 * (r_face[:-1] + r_face[1:])
    A_face = 4.0 * np.pi * r_face**2
    V_cell = (4.0 / 3.0) * np.pi * (r_face[1:]**3 - r_face[:-1]**3)
    return r_face, r, A_face, V_cell


def make_geometry(geometry, Lx, Ly, dx):
    """
    Uniform square-cell 2D grid metrics ('planar' or 'axisymmetric').

    Returns dict with:
      x_c (Nx,), y_c (Ny,), x_face (Nx+1,), y_face (Ny+1,),
      A_xf (Nx+1,1), A_yf (Nx,1), V (Nx,1)   [broadcast over (Nx,Ny)]
    """
    x_face = np.arange(0.0, Lx + 0.5 * dx, dx)
    y_face = np.arange(0.0, Ly + 0.5 * dx, dx)
    x_c    = 0.5 * (x_face[:-1] + x_face[1:])
    y_c    = 0.5 * (y_face[:-1] + y_face[1:])
    Nx, Ny = len(x_c), len(y_c)
    dy     = dx

    if geometry == 'axisymmetric':
        # Per radian: the 2*pi factor cancels between A and V.
        # A_yf uses the exact integral of r over the cell: int r dr = x_c*dx,
        # which makes the p/x_c momentum source exactly well-balanced.
        A_xf = (x_face * dy)[:, None]          # (Nx+1, 1)
        A_yf = (x_c * dx)[:, None]             # (Nx, 1)
        V    = (x_c * dx * dy)[:, None]        # (Nx, 1)
    else:  # planar, per unit depth
        A_xf = np.full((Nx + 1, 1), dy)
        A_yf = np.full((Nx, 1), dx)
        V    = np.full((Nx, 1), dx * dy)

    return dict(x_c=x_c, y_c=y_c, x_face=x_face, y_face=y_face,
                A_xf=A_xf, A_yf=A_yf, V=V, Nx=Nx, Ny=Ny, dx=dx, dy=dy)


def make_grid(Lx, Ly, Lz, dx):
    """Uniform cubic-cell 3D grid. Returns dict of centres, faces, counts."""
    x_face = np.arange(0.0, Lx + 0.5 * dx, dx)
    y_face = np.arange(0.0, Ly + 0.5 * dx, dx)
    z_face = np.arange(0.0, Lz + 0.5 * dx, dx)
    x_c = 0.5 * (x_face[:-1] + x_face[1:])
    y_c = 0.5 * (y_face[:-1] + y_face[1:])
    z_c = 0.5 * (z_face[:-1] + z_face[1:])
    return dict(x_c=x_c, y_c=y_c, z_c=z_c,
                x_face=x_face, y_face=y_face, z_face=z_face,
                Nx=len(x_c), Ny=len(y_c), Nz=len(z_c), dx=dx)
