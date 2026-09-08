#!/usr/bin/env python3
"""
2D Planar / Axisymmetric Blast Wave Solver
==========================================
Finite volume Godunov method for the 2D compressible Euler equations.
Supports ideal gas and JWL equations of state, reflective walls,
rectangular obstacles, point gauges and 2D field snapshots.

Physics
-------
Solves the Euler equations in conservative form on a uniform Cartesian
grid, U = [rho, rho*u, rho*v, E], with geometry entering only through
face areas A, cell volumes V and a geometric source term:

  planar (x-y)      : A_x = dy, A_y = dx, V = dx*dy, no source.
                      The charge is an INFINITE CYLINDER; its size is
                      given as line density [kg TNT per metre of length].
  axisymmetric (r-z): internal x = r, y = z (per radian; 2*pi cancels).
                      A_x = r_face*dz, A_y = r_c*dr, V = r_c*dr*dz,
                      radial momentum source S = p / r_c. The discrete
                      source exactly balances the face-area difference,
                      so uniform still air is preserved to round-off.
                      The charge is a true SPHERE centred on the axis.

Scheme: unsplit first-order Godunov; per-direction HLL sweeps with the
transverse momentum advected passively; forward-Euler in time.

Boundaries: 'open' (transmissive) or 'wall' (reflective) per side via
one ghost layer (mirror state with normal momentum negated). In
axisymmetric mode the left boundary (r=0) is the symmetry axis.
Rectangular obstacles are solid cell blocks whose faces get the same
mirror treatment.

Phase handling matches blast1d.py: a STATIC per-cell mask (0=air,
1=detonation products) set from the initial condition. Products that
expand past their initial cells are evaluated with the air EOS; JWL
tends to omega*rho*e (ideal-gas-like) at large expansion, so far-field
overpressure is only weakly affected. (Future upgrade: advect rho*Y.)

1D -> 2D remap
--------------
In axisymmetric mode the initial condition may be loaded from a radial
field profile written by blast1d.py (save_profile): the 1D spherical
solution is interpolated around the burst point (r=0, z=y0) and the run
continues in 2D from the profile time. Use this to evolve the blast
cheaply in 1D while it is still spherical, then study ground reflection
and obstacles in 2D.
"""

import time

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import animation
from ..core.constants import GAMMA_AIR, RHO_AIR, P_AIR, JWL_TNT, E_AIR
from ..core.eos import (air_pressure, air_soundspeed,
                        jwl_pressure, jwl_soundspeed)
from ..core.riemann import hll_fluxes
from ..core.bc import face_fluxes, solid_mask_2d as solid_mask
from ..core.grid import make_geometry
from ..core.profiles import (load_profile, save_profile_2d,
                             remap_profile_1d_to_2d as remap_profile)


# ── Physical constants ────────────────────────────────────────────────────────


# JWL parameters for TNT (Dobratz & Crawford, LLNL Explosives Handbook, 1985)


# ── Equations of state ────────────────────────────────────────────────────────





# ── Primitive variables from conserved ───────────────────────────────────────


from ..solvers.solver2d import primitives, _run_blast_2d
from ..solvers.hooks import ConsoleHooks


def run_blast_2d(geometry, Lx, Ly, cell_size_m,
                 charge=None, charge_center=None, profile=None,
                 eos='idealGas', bcs=None, obstacles=None,
                 cfl=0.4, n_snapshots=6, gauges=None,
                 record_frames=0, live=False):
    """Historical API: returns (snapshots, gauge_out, meta)."""
    hooks = ConsoleHooks(2, live=live)
    try:
        res = _run_blast_2d(geometry, Lx, Ly, cell_size_m, charge=charge,
                            charge_center=charge_center, profile=profile,
                            eos=eos, bcs=bcs, obstacles=obstacles, cfl=cfl,
                            n_snapshots=n_snapshots, gauges=gauges,
                            record_frames=record_frames, hooks=hooks)
    finally:
        hooks.close()
    return res.snapshots, res.gauges, res.meta


# ── HLL Riemann solver (directional, vectorized) ─────────────────────────────




# ── Geometry & obstacles ─────────────────────────────────────────────────────




# ── 1D profile loading & remap ───────────────────────────────────────────────




# ── Face fluxes with boundary conditions and obstacle walls ──────────────────




# ── Main solver ───────────────────────────────────────────────────────────────


# ── Plotting ──────────────────────────────────────────────────────────────────


from ..output.gauges import save_gauges_2d as save_gauges
from ..output.animation import write_animation
from ..output import plots as _plots
from ..output.pyplot_bridge import adopt_figure as _adopt


def plot_fields(snapshots, meta):
    for out, fig in _plots.figures_fields_2d(snapshots, meta):
        fig.savefig(out, dpi=150, bbox_inches='tight')
        print(f"Plot saved: {out}")
        _adopt(fig)
    plt.show()


def plot_gauges(gauge_out, meta):
    fig = _plots.figure_gauges_nd(gauge_out, meta)
    if fig is None:
        return
    out = 'blast_2d_gauges.png'
    fig.savefig(out, dpi=150, bbox_inches='tight')
    print(f"Plot saved: {out}")
    _adopt(fig)
    plt.show()


def save_animation(meta, filename='blast_2d_animation.gif', fps=15,
                   show_mesh=False):
    write_animation(meta, filename, fps, show_mesh=show_mesh)






# ── Gauge time-history plot ───────────────────────────────────────────────────


# ── Gauge output ─────────────────────────────────────────────────────────────


# ── 2D field profile output (for 2D -> 3D remapping) ─────────────────────────


# ── Live view & animation ─────────────────────────────────────────────────────





        # leave the final frame on screen; plt.show() at the end blocks on it



# ── Interactive prompt ────────────────────────────────────────────────────────

from ..cli import (_ask, _positive, _ask_eos, _ask_choice,
                   _ask_obstacles, _ask_gauges_2d,
                   ask_user_2d as ask_user)















def _main():
    params = ask_user()

    snapshots, gauge_out, meta = run_blast_2d(
        geometry      = params['geometry'],
        Lx            = params['Lx'],
        Ly            = params['Ly'],
        cell_size_m   = params['cell_size_m'],
        charge        = params['charge'],
        charge_center = params['charge_center'],
        profile       = params['profile'],
        eos           = params['eos'],
        bcs           = params['bcs'],
        obstacles     = params['obstacles'],
        n_snapshots   = params['n_snapshots'],
        gauges        = params['gauges'],
        record_frames = 150 if params['anim_file'] else 0,
        live          = params['live'],
    )

    if params['anim_file']:
        save_animation(meta, params['anim_file'],
                       show_mesh=params.get('anim_mesh', False))

    if params['profile2d_file']:
        save_profile_2d(meta, params['profile2d_file'])

    if params['gauges']:
        save_gauges(gauge_out, params['gauge_file'])
        plot_gauges(gauge_out, meta)

    plot_fields(snapshots, meta)


if __name__ == '__main__':
    _main()
