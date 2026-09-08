#!/usr/bin/env python3
"""
3D Cartesian Blast Wave Solver
==============================
Finite volume Godunov method for the 3D compressible Euler equations.
Supports ideal gas and JWL equations of state, reflective walls,
box obstacles, point gauges, slice heatmaps, shock-front isosurfaces,
a live slice view and slice animations.

Physics
-------
Solves the Euler equations in conservative form on a uniform Cartesian
grid of cubic cells, U = [rho, rho*u, rho*v, rho*w, E]. z is vertical;
the bottom boundary (z=0) defaults to a reflective ground plane.

Scheme: unsplit first-order Godunov; three directional HLL sweeps per
step (transverse momenta advected passively), all evaluated from the
same time level; forward-Euler in time. cfl is the SUM of the three
directional Courant numbers (default 0.30).

Initialization (choose one)
---------------------------
  charge     : spherical TNT charge [kg] at (x0, y0, z0). A charge
               crossing a wall boundary is truncated (surface burst).
  1D profile : radial field saved by blast1d.py (save_profile);
               interpolated spherically around the burst point.
  2D profile : axisymmetric r-z field saved by blast2d.py
               (save_profile_2d, .npz); rotated around the vertical
               axis through (x0, y0). The burst height comes from the
               profile. Planar 2D fields cannot be remapped (an
               infinite cylinder has no finite 3D equivalent).

Recommended workflow: resolve the near-field cheaply in 1D (spherical)
or 2D (axisymmetric, e.g. height-of-burst + ground reflection), save a
profile, then remap into 3D only for the part of the problem that is
truly three-dimensional (buildings, corners, asymmetric obstacles).

Phase handling matches blast1d/2d: a STATIC per-cell mask (0=air,
1=detonation products) set from the initial condition.

Performance: pure NumPy. Default grid 100^3 = 1e6 cells runs in
minutes; > 4e6 cells prints a warning; > 15e6 cells is refused.
"""

import time

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import animation
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from ..core.constants import (GAMMA_AIR, RHO_AIR, P_AIR, JWL_TNT,
                              E_AIR, CELLS_WARN, CELLS_REFUSE)
from ..core.eos import (air_pressure, air_soundspeed,
                        jwl_pressure, jwl_soundspeed)
from ..core.riemann import hll_fluxes
from ..core.bc import face_fluxes, solid_mask_3d as solid_mask
from ..core.grid import make_grid
from ..core.profiles import (load_profile, load_profile_2d,
                             remap_profile_1d_to_3d as remap_profile_1d,
                             remap_profile_2d_to_3d as remap_profile_2d)


try:
    from skimage import measure as _sk_measure
    HAVE_SKIMAGE = True
except ImportError:
    HAVE_SKIMAGE = False

# ── Physical constants ────────────────────────────────────────────────────────


# JWL parameters for TNT (Dobratz & Crawford, LLNL Explosives Handbook, 1985)



# ── Equations of state ────────────────────────────────────────────────────────





# ── Primitive variables from conserved ───────────────────────────────────────


from ..solvers.solver3d import primitives, _snapshot, _run_blast_3d
from ..solvers.hooks import ConsoleHooks


def run_blast_3d(Lx, Ly, Lz, cell_size_m,
                 charge=None, charge_center=None,
                 profile=None, profile2d=None,
                 eos='idealGas', bcs=None, obstacles=None,
                 cfl=0.30, n_snapshots=6, gauges=None,
                 record_frames=0, live=False, view3d=False,
                 charge_resolution='resolve', slice_axis='y',
                 slice_pos=None):
    """Historical API: returns (snapshots, gauge_out, meta)."""
    hooks = ConsoleHooks(3, live=live)
    if view3d:
        from ..viz3d.client import attach_on_start
        attach_on_start(hooks)   # opens the viewer at run_started
    try:
        res = _run_blast_3d(Lx, Ly, Lz, cell_size_m, charge=charge,
                            charge_center=charge_center, profile=profile,
                            profile2d=profile2d, eos=eos, bcs=bcs,
                            obstacles=obstacles, cfl=cfl,
                            n_snapshots=n_snapshots, gauges=gauges,
                            record_frames=record_frames, hooks=hooks,
                            charge_resolution=charge_resolution,
                            slice_axis=slice_axis, slice_pos=slice_pos)
    finally:
        hooks.close()
        if hooks.viewer3d is not None:
            try:
                reason = res.stop_reason
            except NameError:
                reason = 'run aborted'
            hooks.viewer3d.finish(reason)
            print("  [3D viewer stays open - close its window to let "
                  "the program exit]")
    return res.snapshots, res.gauges, res.meta


# ── HLL Riemann solver (directional, vectorized) ─────────────────────────────




# ── Grid & obstacles ─────────────────────────────────────────────────────────




# ── 1D profile loading & remap ───────────────────────────────────────────────




# ── 2D axisymmetric profile loading & remap ──────────────────────────────────






# ── Face fluxes with boundary conditions and obstacle walls ──────────────────





# ── Main solver ───────────────────────────────────────────────────────────────




# ── Plotting: slice figures ───────────────────────────────────────────────────


from ..output.gauges import save_gauges_3d as save_gauges
from ..output.animation import write_animation
from ..output import plots as _plots
from ..output.plots import HAVE_SKIMAGE
from ..output.pyplot_bridge import adopt_figure as _adopt


def plot_fields(snapshots, meta):
    for out, fig in _plots.figures_fields_3d(snapshots, meta):
        fig.savefig(out, dpi=150, bbox_inches='tight')
        print(f"Plot saved: {out}")
        _adopt(fig)
    plt.show()


def plot_gauges(gauge_out, meta):
    fig = _plots.figure_gauges_nd(gauge_out, meta)
    if fig is None:
        return
    out = 'blast_3d_gauges.png'
    fig.savefig(out, dpi=150, bbox_inches='tight')
    print(f"Plot saved: {out}")
    _adopt(fig)


def plot_isosurfaces(snapshots, meta):
    if not HAVE_SKIMAGE:
        print("  [note] scikit-image not found - isosurfaces rendered as "
              "point clouds (pip install scikit-image for true surfaces)")
    fig = _plots.figure_isosurfaces_3d(snapshots, meta)
    out = 'blast_3d_isosurface.png'
    fig.savefig(out, dpi=150, bbox_inches='tight')
    print(f"Plot saved: {out}")
    _adopt(fig)


def save_animation(meta, filename='blast_3d_animation.gif', fps=15,
                   show_mesh=False):
    write_animation(meta, filename, fps, show_mesh=show_mesh)






# ── Plotting: shock-front isosurfaces ────────────────────────────────────────




# ── Live view & animation (vertical x-z slice through the burst) ─────────────








# ── Gauge time-history plot ───────────────────────────────────────────────────


# ── Gauge output ─────────────────────────────────────────────────────────────


# ── Interactive prompt ────────────────────────────────────────────────────────

from ..cli import (_ask, _positive, _ask_eos, _ask_choice,
                   _ask_obstacles_3d, _ask_gauges_3d,
                   ask_user_3d as ask_user)















def _main():
    params = ask_user()

    snapshots, gauge_out, meta = run_blast_3d(
        Lx            = params['Lx'],
        Ly            = params['Ly'],
        Lz            = params['Lz'],
        cell_size_m   = params['cell_size_m'],
        charge        = params['charge'],
        charge_center = params['charge_center'],
        charge_resolution = params['charge_resolution'],
        profile       = params['profile'],
        profile2d     = params['profile2d'],
        eos           = params['eos'],
        bcs           = params['bcs'],
        obstacles     = params['obstacles'],
        n_snapshots   = params['n_snapshots'],
        gauges        = params['gauges'],
        record_frames = 150 if params['anim_file'] else 0,
        live          = params['live'],
        view3d        = params.get('view3d', False),
    )

    if params['anim_file']:
        save_animation(meta, params['anim_file'],
                       show_mesh=params.get('anim_mesh', False))

    if params['gauges']:
        save_gauges(gauge_out, params['gauge_file'])
        plot_gauges(gauge_out, meta)

    plot_fields(snapshots, meta)
    plot_isosurfaces(snapshots, meta)
    plt.show()


if __name__ == '__main__':
    _main()
