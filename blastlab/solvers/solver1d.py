"""1D spherical blast solver (Godunov + HLL)."""

import math

import numpy as np

from ..core.constants import (GAMMA_AIR, RHO_AIR, P_AIR, JWL_TNT,
                              MIN_EXP_CELLS)
from ..core.eos import (air_pressure, jwl_pressure, material_jwl,
                        pressure_soundspeed)
from ..core.bc import normalize_bc
from ..core.riemann import hll_fluxes_1d as hll_fluxes
from ..core.grid import make_grid_1d
from .hooks import ConsoleHooks, Progress, Result

def primitives(U, phase, eos, jwl=JWL_TNT):
    """
    Recover rho, u, e, p, c from conserved variables U = [rho, rho*u, E_vol].
    phase: integer array (0=air, 1=explosive products)
    """
    rho = np.maximum(U[0], 1e-10)
    u   = U[1] / rho
    e   = np.maximum((U[2] - 0.5 * rho * u**2) / rho, 1.0)  # floor e at 1 J/kg

    # the identical air/products dispatch lived in all three solvers
    # (A4); eos.pressure_soundspeed is that same block, verbatim
    p, c = pressure_soundspeed(rho, e, phase, eos, jwl)

    return rho, u, e, p, c


def _run_blast_1d(radius_m, charge_kg, cell_size_m, material='TNT',
                  order=1,
                  eos='idealGas', cfl=0.5, n_snapshots=5,
                  gauge_radii=None, hooks=None, t_end=0.0,
                  bc_outer='terminate'):
    """
    Run a 1D spherical blast wave simulation. The run stops when the shock
    front reaches the outer boundary (detected via a pressure rise in the
    outermost cell). An internal safety cap prevents runaway loops.

    Parameters
    ----------
    radius_m    : float       Domain outer radius [m]
    charge_kg   : float       TNT equivalent charge weight [kg]
    cell_size_m : float       Uniform cell size [m]
    eos         : str         'JWL' or 'idealGas'
    cfl         : float       Courant-Friedrichs-Lewy number (< 1)
    n_snapshots : int         Number of solution snapshots to record,
                              including the final state; the others fire
                              as the shock front crosses evenly spaced
                              radii between the charge and the boundary
                              (same semantics as the 2D/3D solvers)
    gauge_radii : list[float] Radii [m] at which to record pressure history

    Returns
    -------
    snapshots     : dict      label -> dict(r, p, rho, u)
    gauge_out     : dict      with keys 'times', 'radii', 'pressures'
    final_profile : dict      full radial state at stop time (for 1D->2D remap)
    """
    if hooks is None:
        hooks = ConsoleHooks(1)
    # ── Grid ──────────────────────────────────────────────────────────────────
    # r=0 is at the left domain boundary; first cell centre at dr/2
    # core.grid.make_grid_1d owns the spherical metrics; this used to
    # take its faces and then rebuild r / A_face / V_cell inline (A4)
    r_face, r, A_face, V_cell = make_grid_1d(radius_m, cell_size_m)
    N      = len(r)
    # effective spacing: == cell_size_m unless it does not divide radius_m,
    # in which case the grid was fitted to the exact domain (core.grid)
    dr     = float(r_face[1])
    if dr != cell_size_m:
        hooks.log(f"  [note] Cell size adjusted {cell_size_m:g} -> {dr:.4g} m "
                  f"to fit {radius_m:g} m exactly")

    # ── Explosive sphere radius from charge weight ──────────────────────────
    # N11/T46: JWL parameters by charge material; 'TNT' IS the pinned
    # constants object, so default runs stay byte-identical
    jwl = material_jwl(material)
    rho_exp = jwl['rho0']
    r_exp   = (3.0 * charge_kg / (4.0 * np.pi * rho_exp)) ** (1.0 / 3.0)

    if r_exp >= radius_m:
        raise ValueError(f"Explosive radius {r_exp:.3f} m exceeds domain radius {radius_m} m")

    # Ensure at least 5 cells inside the explosive sphere — otherwise the
    # density contact surface is unresolved and HLL drains the cell in one step,
    # collapsing rho to the floor and making e (and c) blow up to near-infinity.
    if dr > r_exp / MIN_EXP_CELLS:
        # the largest spacing that keeps MIN_EXP_CELLS across the charge
        # AND divides the domain exactly (ceil: never coarser than r_exp/N)
        dr = radius_m / math.ceil(radius_m / (r_exp / MIN_EXP_CELLS))
        r_face, r, A_face, V_cell = make_grid_1d(radius_m, dr)
        N      = len(r)
        hooks.log(f"  [auto] Cell size reduced to {dr:.5f} m "
              f"({MIN_EXP_CELLS} cells inside explosive, {N} total)")

    # ── Initial conditions ──────────────────────────────────────────────────
    is_exp = r <= r_exp          # cells inside explosive sphere
    phase  = is_exp.astype(int)  # 0=air, 1=products  (fixed — no interface tracking)

    rho    = np.where(is_exp, rho_exp, RHO_AIR)
    u      = np.zeros(N)
    e_air  = P_AIR / ((GAMMA_AIR - 1.0) * RHO_AIR)
    e      = np.where(is_exp, jwl['e0'], e_air)

    # Pressure from chosen EOS
    p = np.empty(N)
    if eos == 'JWL':
        p[is_exp]  = jwl_pressure(rho[is_exp], e[is_exp], jwl)
    else:
        p[is_exp]  = air_pressure(rho[is_exp], e[is_exp])
    p[~is_exp] = air_pressure(rho[~is_exp], e[~is_exp])

    # Conservative state: U = [rho, rho*u, E_vol]  shape (3, N)
    U = np.array([rho,
                  rho * u,
                  rho * (e + 0.5 * u**2)])

    # ── Stop condition & snapshot scheduling ───────────────────────────────
    c_amb        = np.sqrt(GAMMA_AIR * P_AIR / RHO_AIR)        # ~340 m/s
    arrival_p    = P_AIR * 1.001                                # 0.1 % overpressure
    safety_cap   = 10.0 * radius_m / c_amb                      # absolute upper bound
    # T52: an explicit end time wins, shorter OR longer than the cap.
    # It used to win only when shorter (`and t_end < safety_cap`), which
    # meant a larger number was silently discarded and the run ended at
    # the cap - typing a bigger end time changed nothing. The cap is the
    # automatic stop for a run that said nothing, not a ceiling on what
    # can be said; validate_case warns about the wall clock (2026-09-18).
    cap_is_end   = bool(t_end)
    if cap_is_end:
        safety_cap = t_end

    # Snapshots are triggered by shock-front POSITION, not time, exactly as
    # in 2D/3D: the blast crosses the domain far faster than the acoustic
    # estimate that used to schedule them, which left the intermediate
    # snapshots untaken. They fire when the front crosses evenly spaced
    # radii between the charge and the outer boundary; the final state is
    # always recorded as well (n_snapshots total, including the final).
    snap_radii = list(np.linspace(r_exp, radius_m, n_snapshots + 1)[1:-1])

    # ── Gauge setup ────────────────────────────────────────────────────────
    if gauge_radii is None:
        gauge_radii = []
    gauge_radii = [g for g in gauge_radii if 0 < g <= radius_m]
    # Map each gauge radius to the index of its nearest cell centre
    gauge_indices = [int(np.argmin(np.abs(r - g))) for g in gauge_radii]
    # Actual cell-centre radii (may differ slightly from requested)
    gauge_actual  = [float(r[i]) for i in gauge_indices]
    gauge_times_list  = []
    gauge_press_lists = [[] for _ in gauge_radii]

    hooks.run_started(dict(dim=1, r=r, radius_m=radius_m,
                           gauges=[(n + 1, float(g), 0.0)
                                   for n, g in enumerate(gauge_actual)]))
    import time as _time
    _last_draw = 0.0

    # ── Print summary ───────────────────────────────────────────────────────
    p0_exp = p[is_exp].mean() if is_exp.any() else 0.0
    hooks.log(f"\n{'='*55}")
    hooks.log(f"  1D Spherical Blast Solver")
    hooks.log(f"{'='*55}")
    hooks.log(f"  Charge          : {charge_kg} kg TNT")
    hooks.log(f"  Explosive radius: {r_exp:.4f} m")
    hooks.log(f"  Domain radius   : {radius_m} m")
    hooks.log(f"  Cell size       : {dr} m  ({N} cells)")
    hooks.log(f"  EOS             : {eos}")
    hooks.log(f"  Initial p (exp) : {p0_exp:.3e} Pa  ({p0_exp/1e9:.2f} GPa)")
    hooks.log(f"  Outer boundary  : {bc_outer}")
    hooks.log(f"  Stop condition  : "
              + (f"shock arrival at r = {radius_m} m"
                 if bc_outer == 'terminate'
                 else "safety cap (the outer boundary does not stop it)"))
    hooks.log(f"  {'End time' if cap_is_end else 'Safety cap':<16}: "
              f"{safety_cap*1e3:.1f} ms")
    hooks.log(f"{'='*55}\n")

    # ── Time integration (Godunov, 1st order) ──────────────────────────────
    t          = 0.0
    step       = 0
    snapshots  = {}
    stop_reason = 'safety cap'

    while t < safety_cap:
        rho_f, u_f, e_f, p_f, c_f = primitives(U, phase, eos, jwl)

        # ── Record gauges (pressure at the current time t) ────────────────
        if gauge_indices:
            gauge_times_list.append(t)
            for k, idx in enumerate(gauge_indices):
                gauge_press_lists[k].append(p_f[idx])

        if hooks.should_stop():
            stop_reason = 'stopped by user'
            break

        if hooks.draw_due(step, _last_draw) or hooks.exec_will_pause():
            hooks.frame(np.array([r, p_f]), t)
            if gauge_indices and hooks.wants_gauges():
                from .solver2d import _gauge_payload
                hooks.gauges(_gauge_payload(
                    gauge_times_list, gauge_press_lists,
                    [(float(rr),) for rr in gauge_radii]))
            _last_draw = _time.time()

        # Stepped execution (GUI Exec N / Interrupt): may block here.
        hooks.step_gate()
        if hooks.should_stop():
            stop_reason = 'stopped by user'
            break

        # ── Stop condition: shock at a TERMINATE outer boundary ───────────
        if bc_outer == 'terminate' and p_f[-1] > arrival_p:
            stop_reason = f'shock arrived at outer boundary (p_last = {p_f[-1]:.3e} Pa)'
            break

        # Take any due snapshots before the update (front = outermost
        # cell above the arrival threshold, as in 2D/3D)
        shocked = p_f > arrival_p
        r_front = r[shocked].max() if shocked.any() else 0.0
        while snap_radii and r_front >= snap_radii[0]:
            snap_radii.pop(0)
            label = f"t = {t*1e3:.3f} ms"
            snapshots[label] = dict(r=r.copy(), p=p_f.copy(),
                                    rho=rho_f.copy(), u=u_f.copy())
            hooks.log(f"  Snapshot saved: {label}")

        # ── CFL time step ─────────────────────────────────────────────────
        dt = cfl * dr / np.max(np.abs(u_f) + c_f)
        dt = min(dt, safety_cap - t)
        if dt <= 0:
            break

        # ── Face fluxes ────────────────────────────────────────────────────
        if order == 2:
            # T47/N10: limited MUSCL face states; each side's p and c
            # are re-evaluated from ITS reconstructed state. Slopes are
            # zero at the two edge cells (np.diff pads nothing there),
            # so the axis and outer faces stay first order.
            from ..core.bc import minmod
            dq = np.diff(U, axis=1)
            sl = np.zeros_like(U)
            sl[:, 1:-1] = minmod(dq[:, :-1], dq[:, 1:])
            U_L = U[:, :-1] + 0.5 * sl[:, :-1]
            U_R = U[:, 1:] - 0.5 * sl[:, 1:]
            eL = (U_L[2] - 0.5 * U_L[1] ** 2 / np.maximum(U_L[0], 1e-10)) \
                / np.maximum(U_L[0], 1e-10)
            eR = (U_R[2] - 0.5 * U_R[1] ** 2 / np.maximum(U_R[0], 1e-10)) \
                / np.maximum(U_R[0], 1e-10)
            bad = (U_L[0] <= 1e-10) | (U_R[0] <= 1e-10) \
                | (eL <= 0.0) | (eR <= 0.0)
            if bad.any():
                U_L[:, bad] = U[:, :-1][:, bad]
                U_R[:, bad] = U[:, 1:][:, bad]
                eL = (U_L[2] - 0.5 * U_L[1] ** 2 / U_L[0]) / U_L[0]
                eR = (U_R[2] - 0.5 * U_R[1] ** 2 / U_R[0]) / U_R[0]
            pL, cL = pressure_soundspeed(np.maximum(U_L[0], 1e-10),
                                         np.maximum(eL, 1.0),
                                         phase[:-1], eos, jwl)
            pR, cR = pressure_soundspeed(np.maximum(U_R[0], 1e-10),
                                         np.maximum(eR, 1.0),
                                         phase[1:], eos, jwl)
            F_int = hll_fluxes(U_L, U_R, pL, pR, cL, cR)
        else:
            F_int = hll_fluxes(U[:, :-1], U[:, 1:],
                               p_f[:-1], p_f[1:],
                               c_f[:-1], c_f[1:])

        F = np.zeros((3, N + 1))
        F[:, 1:N] = F_int
        if bc_outer == 'reflect':
            # T60: a mirrored ghost through the same Riemann solver, as
            # core.bc does for a reflecting 2D/3D side
            g = U[:, -1:].copy()
            g[1] = -g[1]
            F[:, N:] = hll_fluxes(U[:, -1:], g, p_f[-1:], p_f[-1:],
                                  c_f[-1:], c_f[-1:])
        else:
            # transmit / terminate: transmissive outflow
            u_out = u_f[-1]
            F[:, N] = [U[0, -1] * u_out,
                       U[0, -1] * u_out**2 + p_f[-1],
                       (U[2, -1] + p_f[-1]) * u_out]

        # ── Divergence + spherical source ──────────────────────────────────
        div_F = (A_face[1:] * F[:, 1:] - A_face[:-1] * F[:, :-1]) / V_cell
        S      = np.zeros((3, N))
        S[1]   = 2.0 * p_f / np.maximum(r, 1e-10)

        # ── Forward Euler update ───────────────────────────────────────────
        U = U - dt * div_F + dt * S
        U[0] = np.maximum(U[0], 1e-10)

        # Pressure floor: prevent e -> infty when a cell is evacuated.
        rho_tmp = U[0]
        e_tmp   = (U[2] - 0.5 * U[1]**2 / rho_tmp) / rho_tmp
        e_floor = P_AIR / ((GAMMA_AIR - 1.0) * RHO_AIR) * 1e-6
        bad     = e_tmp < e_floor
        if bad.any():
            U[2, bad] = rho_tmp[bad] * (e_floor + 0.5 * (U[1, bad] / rho_tmp[bad])**2)

        t    += dt
        step += 1

        # P2-1: progress against what will ACTUALLY stop this run. 1D used
        # t / safety_cap unconditionally, and the safety cap is ~10x the
        # real length of a run that ends when the front arrives - so the
        # bar crawled to about a tenth and then jumped. 2D/3D have always
        # measured the front against the distance it has to cover; do the
        # same whenever the front is what ends the run, and keep the time
        # ratio when an end time or a non-terminating boundary means the
        # clock really is the bound (T52/T60).
        frac = (t / safety_cap if cap_is_end or bc_outer != 'terminate'
                else r_front / radius_m)
        hooks.progress(Progress(step=step, t=t, dt=dt, p_max=p_f.max(),
                                frac=min(1.0, max(0.0, frac))))

    # ── Final snapshot at stop time ────────────────────────────────────────
    rho_f, u_f, e_f, p_f, _ = primitives(U, phase, eos, jwl)
    # skip when the loop top already recorded this t (exit via break):
    # a duplicated last timestamp makes dt-based post-processing inf/nan
    if gauge_indices and (not gauge_times_list or gauge_times_list[-1] != t):
        gauge_times_list.append(t)
        for k, idx in enumerate(gauge_indices):
            gauge_press_lists[k].append(p_f[idx])
    label = f"t = {t*1e3:.3f} ms (final)"
    snapshots[label] = dict(r=r.copy(), p=p_f.copy(),
                            rho=rho_f.copy(), u=u_f.copy())

    # Full final state for 1D->2D remapping (see save_profile)
    final_profile = dict(t=t, r=r.copy(), rho=rho_f.copy(), u=u_f.copy(),
                         e=e_f.copy(), p=p_f.copy(), phase=phase.copy(),
                         charge_kg=charge_kg, eos=eos, r_exp=r_exp,
                         radius_m=radius_m,
                         # N5-4: stamped at the PRODUCER, not in
                         # jobs.solve_stage - save_profile is also
                         # reached from the Results-tab exports and the
                         # CLI, which solve_stage never sees.
                         source_solver='native')

    if stop_reason == 'safety cap' and cap_is_end:
        stop_reason = 'end time reached'
    hooks.log(f"\n  Done. {step} steps, t_final = {t*1e3:.3f} ms")
    hooks.log(f"  Stopped: {stop_reason}\n")

    gauge_out = dict(
        times    = np.array(gauge_times_list),
        radii    = gauge_actual,
        pressures= [np.array(lst) for lst in gauge_press_lists],
    )
    hooks.frame(np.array([r, p_f]), t)
    meta = dict(final_profile=final_profile, r=r, radius_m=radius_m,
                charge_kg=charge_kg, eos=eos, r_exp=r_exp)
    return Result(snapshots, gauge_out, meta, stop_reason,
                  stop_reason == 'stopped by user')


def solve_1d(case, hooks=None):
    """Run a Case1D. Returns a Result."""
    return _run_blast_1d(case.radius_m, case.charge_kg, case.cell_size_m,
                         material=getattr(case, 'material', 'TNT'),
                         order=int(getattr(case, 'order', 1) or 1),
                         eos=case.eos, cfl=case.cfl,
                         n_snapshots=case.n_snapshots,
                         gauge_radii=list(case.gauge_radii), hooks=hooks,
                         t_end=float(getattr(case, 't_end', 0.0) or 0.0),
                         bc_outer=normalize_bc(
                             getattr(case, 'bc_outer', 'terminate')))
