"""Uniform-grid builders and geometric metrics for the three solvers.

Every builder spans its domain with N = round(L / dx) whole cells. When dx
does not divide L the spacing becomes dx_eff = L / N so the domain is exact:
the old `arange(0, L + dx/2, dx)` silently shrank it by up to one cell
(10 m at 0.3 m gave 9.9 m) while the summaries, stop distances and
containment checks kept using the nominal L. When dx does divide L the
faces are bit-identical to the historical i*dx values, so existing results
are unchanged.

Square/cubic cells are kept: 2D/3D take dx_eff from the x axis and lay the
other axes out in whole cells of that spacing. The solvers read the
effective spacing (`dx` in the returned dict) and extents (last face) back
and say so in the run summary whenever they differ from the request.
"""

import math

import numpy as np


def _faces(L, dx):
    """Face coordinates 0..L in N = round(L/dx) cells -> (faces, dx_eff).

    dx_eff snaps back to dx when it divides L (to 1e-12), so the faces are
    then exactly the historical i*dx values."""
    n = max(1, int(round(L / dx)))
    dx_eff = L / n
    if math.isclose(dx_eff, dx, rel_tol=1e-12, abs_tol=0.0):
        dx_eff = dx
    return np.arange(n + 1) * dx_eff, dx_eff


def _faces_shared(lengths, dx):
    """Faces for axes sharing one spacing: exact along the first axis,
    whole cells of that spacing along the others -> (faces, dx_eff)."""
    first, dx_eff = _faces(lengths[0], dx)
    faces = [first]
    for L in lengths[1:]:
        n = max(1, int(round(L / dx_eff)))
        faces.append(np.arange(n + 1) * dx_eff)
    return faces, dx_eff


def make_grid_1d(radius_m, dr):
    """
    Uniform 1D radial grid with spherical metrics.

    Returns r_face (N+1,), r (N,) cell centres, A_face (N+1,) = 4*pi*r^2,
    V_cell (N,) spherical shell volumes. The effective spacing is
    r_face[1] (== dr unless dr does not divide radius_m).
    """
    r_face, _ = _faces(radius_m, dr)
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
      dx, dy: the effective (square) spacing actually used
    """
    (x_face, y_face), dx = _faces_shared((Lx, Ly), dx)
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
    """Uniform cubic-cell 3D grid. Returns dict of centres, faces, counts
    and the effective spacing `dx` actually used."""
    (x_face, y_face, z_face), dx = _faces_shared((Lx, Ly, Lz), dx)
    x_c = 0.5 * (x_face[:-1] + x_face[1:])
    y_c = 0.5 * (y_face[:-1] + y_face[1:])
    z_c = 0.5 * (z_face[:-1] + z_face[1:])
    return dict(x_c=x_c, y_c=y_c, z_c=z_c,
                x_face=x_face, y_face=y_face, z_face=z_face,
                Nx=len(x_c), Ny=len(y_c), Nz=len(z_c), dx=dx)
