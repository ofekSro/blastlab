#!/usr/bin/env python3
"""
1D Spherical Blast Wave Solver
================================
Finite volume Godunov method for the 1D spherical Euler equations.
Supports ideal gas and JWL equations of state.

Physics
-------
Solves the 1D spherical Euler equations in conservative form:

  d(rho)/dt  + (1/r^2) d(r^2 * rho*u)/dr            = 0
  d(rho*u)/dt + (1/r^2) d(r^2 * (rho*u^2 + p))/dr   = 2*p/r
  d(E)/dt    + (1/r^2) d(r^2 * (E+p)*u)/dr           = 0

where E = rho*(e + 0.5*u^2) is total energy per unit volume.

EOS options
-----------
  idealGas : p = (gamma-1)*rho*e  (gamma=1.4, used for both air and products)
  JWL      : TNT products use Jones-Wilkins-Lee EOS;
             air uses ideal gas

Usage
-----
  python blast1d.py --charge 1.0 --radius 20 --cell-size 0.1 --eos JWL
  python blast1d.py --charge 5.0 --radius 50 --cell-size 0.2 --eos idealGas --snapshots 8
"""

import numpy as np
import matplotlib.pyplot as plt
from ..core.constants import GAMMA_AIR, RHO_AIR, P_AIR, JWL_TNT
from ..core.eos import (air_pressure, air_soundspeed,
                        jwl_pressure, jwl_soundspeed)
from ..core.riemann import hll_fluxes_1d as hll_fluxes
from ..core.profiles import save_profile


# ── Physical constants ────────────────────────────────────────────────────────


# JWL parameters for TNT (Dobratz & Crawford, LLNL Explosives Handbook, 1985)

# ── Equations of state ────────────────────────────────────────────────────────





# ── Primitive variables from conserved ───────────────────────────────────────


from ..solvers.solver1d import primitives, _run_blast_1d
from ..solvers.hooks import ConsoleHooks


def run_blast(radius_m, charge_kg, cell_size_m,
              eos='idealGas', cfl=0.5, n_snapshots=5,
              gauge_radii=None, bc_outer='terminate', t_end=0.0):
    """Historical API: returns (snapshots, gauge_out, final_profile)."""
    res = _run_blast_1d(radius_m, charge_kg, cell_size_m, eos=eos, cfl=cfl,
                        n_snapshots=n_snapshots, gauge_radii=gauge_radii,
                        bc_outer=bc_outer, t_end=t_end,
                        hooks=ConsoleHooks(1))
    return res.snapshots, res.gauges, res.meta['final_profile']


# ── HLL Riemann solver (vectorized) ──────────────────────────────────────────


# ── Main solver ───────────────────────────────────────────────────────────────


# ── Plotting ──────────────────────────────────────────────────────────────────


from ..output.gauges import save_gauges_1d as save_gauges
from ..output import plots as _plots
from ..output.pyplot_bridge import adopt_figure as _adopt


def plot_results(snapshots, eos, charge_kg, radius_m):
    fig = _plots.figure_results_1d(snapshots, eos, charge_kg, radius_m)
    out = 'blast_1d_results.png'
    fig.savefig(out, dpi=150, bbox_inches='tight')
    print(f"Plot saved: {out}")
    _adopt(fig)
    plt.show()


def plot_gauges(gauge_out, charge_kg, eos):
    fig = _plots.figure_gauges_1d(gauge_out, charge_kg, eos)
    if fig is None:
        return
    out = 'blast_1d_gauges.png'
    fig.savefig(out, dpi=150, bbox_inches='tight')
    print(f"Plot saved: {out}")
    _adopt(fig)
    plt.show()


# ── Gauge time-history plot ───────────────────────────────────────────────────



# ── Gauge output ─────────────────────────────────────────────────────────────



# ── Field profile output (for 1D -> 2D remapping) ────────────────────────────



# ── Interactive prompt ────────────────────────────────────────────────────────

from ..cli import (_ask, _positive, _ask_eos, _ask_gauges,
                   ask_user_1d as ask_user)











def _main():
    params = ask_user()

    snapshots, gauge_out, final_profile = run_blast(
        radius_m    = params['radius_m'],
        charge_kg   = params['charge_kg'],
        cell_size_m = params['cell_size_m'],
        eos         = params['eos'],
        bc_outer    = params.get('bc_outer', 'terminate'),
        n_snapshots = params['n_snapshots'],
        gauge_radii = params['gauge_radii'],
    )

    if params['profile_file']:
        save_profile(final_profile, params['profile_file'])

    if params['gauge_radii']:
        save_gauges(gauge_out, params['gauge_file'])
        plot_gauges(gauge_out, params['charge_kg'], params['eos'])

    plot_results(snapshots, params['eos'], params['charge_kg'], params['radius_m'])


if __name__ == '__main__':
    _main()
