"""2D planar / axisymmetric blast solver (unsplit Godunov + HLL)."""

import math
import time

import numpy as np

from ..core import geometry as core_geometry
from ..core.constants import (GAMMA_AIR, RHO_AIR, P_AIR, JWL_TNT,
                              E_AIR, MIN_EXP_CELLS,
                              CELLS_2D_WARN, CELLS_2D_MAX)
from ..core.eos import pressure_soundspeed
from ..core.bc import face_fluxes, solid_mask_2d as solid_mask
from ..core.grid import make_geometry
from ..core.profiles import remap_profile_1d_to_2d as remap_profile
from .hooks import ConsoleHooks, Progress, Result

def primitives(U, phase, eos):
    """
    Recover rho, u, v, e, p, c from conserved U = [rho, rho*u, rho*v, E_vol].
    phase: integer array (0=air, 1=explosive products)
    """
    rho = np.maximum(U[0], 1e-10)
    u   = U[1] / rho
    v   = U[2] / rho
    e   = np.maximum((U[3] - 0.5 * rho * (u**2 + v**2)) / rho, 1.0)  # floor at 1 J/kg

    # the identical air/products dispatch lived in all three solvers
    # (A4); eos.pressure_soundspeed is that same block, verbatim
    p, c = pressure_soundspeed(rho, e, phase, eos)

    return rho, u, v, e, p, c


def _run_blast_2d(geometry, Lx, Ly, cell_size_m,
                  charge=None, charge_center=None, profile=None,
                  eos='idealGas', bcs=None, obstacles=None,
                  cfl=0.4, n_snapshots=6, gauges=None,
                  record_frames=0, hooks=None):
    """
    Run a 2D planar or axisymmetric blast simulation.

    Parameters
    ----------
    geometry      : 'planar' or 'axisymmetric'
    Lx, Ly        : float   Domain extent [m]. Axisym: Lx = radial extent,
                            Ly = axial (vertical) extent.
    cell_size_m   : float   Uniform square cell size [m]
    charge        : float   Direct init: axisym = charge mass [kg TNT],
                            planar = line density [kg TNT / m]. None if
                            starting from a 1D profile.
    charge_center : (x0,y0) Charge / burst point. Axisym: x0 is forced to 0.
    profile       : dict    Output of load_profile (axisym only) - remapped
                            1D initial condition instead of a fresh charge.
    eos           : 'JWL' or 'idealGas'
    bcs           : dict    {'x_lo','x_hi','y_lo','y_hi'} -> 'open'|'wall'.
                            Axisym x_lo is always the symmetry axis.
    obstacles     : list of (x0, x1, y0, y1) rectangles
    cfl           : float   2D CFL number (< 0.5 recommended for unsplit)
    n_snapshots   : int     Number of 2D field snapshots
    gauges        : list of (x, y) gauge locations [m]
    record_frames : int     ~number of pressure frames to keep for an
                            animation (0 = off). Captured every few steps
                            with adaptive decimation, so any run length
                            ends up with record_frames..2*record_frames
                            frames. Stored float32 -> meta['frames'].
    live          : bool    Show a live-updating pressure window while the
                            simulation runs (needs an interactive
                            matplotlib backend; silently skipped otherwise)

    Returns
    -------
    snapshots : dict  label -> dict(p, rho, speed)  (2D arrays)
    gauge_out : dict  'times', 'points', 'pressures'
    meta      : dict  grid, solid mask, run description, optional 'frames'
    """
    if hooks is None:
        hooks = ConsoleHooks(2)
    if geometry not in ('planar', 'axisymmetric'):
        raise ValueError(f"Unknown geometry '{geometry}'")
    if bcs is None:
        bcs = dict(x_lo='open', x_hi='open', y_lo='open', y_hi='open')
    if geometry == 'axisymmetric':
        bcs = dict(bcs, x_lo='wall')   # symmetry axis
    obstacles = obstacles or []
    dx = cell_size_m

    # ── Charge geometry (direct init) ───────────────────────────────────────
    rho_exp = JWL_TNT['rho0']
    if profile is not None:
        if geometry != 'axisymmetric':
            raise ValueError("1D profile remap is only valid in axisymmetric mode")
        if charge is not None:
            raise ValueError("Give either a charge or a 1D profile, not both")
        x0 = 0.0
        y0 = charge_center[1]
        r_exp = profile['r_exp']
        if profile['eos'] != eos:
            hooks.log(f"  [warn] Profile EOS '{profile['eos']}' differs from run "
                  f"EOS '{eos}' - products will be evaluated with '{eos}'.")
    else:
        if charge is None or charge <= 0:
            raise ValueError("Charge must be > 0")
        x0, y0 = charge_center
        if geometry == 'axisymmetric':
            x0 = 0.0
            r_exp = (3.0 * charge / (4.0 * np.pi * rho_exp)) ** (1.0 / 3.0)
        else:
            r_exp = np.sqrt(charge / (np.pi * rho_exp))   # kg per metre of length

        # Charge must not poke through an OPEN boundary; crossing a wall is
        # allowed (truncated charge = surface burst against that wall).
        if not (0 <= x0 <= Lx and 0 <= y0 <= Ly):
            raise ValueError(f"Charge centre ({x0:g}, {y0:g}) is outside the domain")
        overhangs = [(r_exp - (Lx - x0), 'x_hi'),
                     (r_exp - y0,        'y_lo'),
                     (r_exp - (Ly - y0), 'y_hi')]
        if geometry == 'planar':
            overhangs.append((r_exp - x0, 'x_lo'))   # axisym x_lo is the axis
        for over, side in overhangs:
            if over <= 0:
                continue
            if bcs[side] == 'wall':
                hooks.log(f"  [note] Charge is truncated by the {side} wall "
                      f"(surface burst)")
            else:
                raise ValueError(f"Charge (r_exp = {r_exp:.4f} m at "
                                 f"({x0:g}, {y0:g})) pokes through the open "
                                 f"'{side}' boundary")
        # ... and clear of every obstacle.
        for (ox0, ox1, oy0, oy1) in obstacles:
            cx = min(max(x0, ox0), ox1)
            cy = min(max(y0, oy0), oy1)
            if (cx - x0)**2 + (cy - y0)**2 < r_exp**2:
                raise ValueError(f"Charge overlaps obstacle "
                                 f"({ox0:g},{ox1:g},{oy0:g},{oy1:g})")

        # Resolve the charge with at least MIN_EXP_CELLS cells (as in blast1d),
        # but cap total cell count - refinement is quadratic in 2D.
        if dx > r_exp / MIN_EXP_CELLS:
            # the largest spacing that keeps MIN_EXP_CELLS across the
            # charge AND divides Lx exactly (ceil: never coarser)
            dx = Lx / math.ceil(Lx / (r_exp / MIN_EXP_CELLS))
            n_est = int(Lx / dx) * int(Ly / dx)
            if n_est > CELLS_2D_MAX:
                raise ValueError(
                    f"Resolving the charge needs dx = {dx:.5f} m -> ~{n_est:,} "
                    f"cells. Reduce the domain or enlarge the charge.")
            hooks.log(f"  [auto] Cell size reduced to {dx:.5f} m "
                  f"({MIN_EXP_CELLS} cells across charge radius)")

    # ── Grid, metrics, solids ───────────────────────────────────────────────
    geom = make_geometry(geometry, Lx, Ly, dx)
    if geom['dx'] != dx:
        # dx did not divide Lx: core.grid fitted the exact domain with a
        # slightly different (square) spacing - use it everywhere below
        hooks.log(f"  [note] Cell size adjusted {dx:g} -> {geom['dx']:.4g} m "
                  f"to fit {Lx:g} m exactly (domain {geom['x_face'][-1]:g} "
                  f"x {geom['y_face'][-1]:.4g} m)")
        dx = geom['dx']
        Lx, Ly = float(geom['x_face'][-1]), float(geom['y_face'][-1])
    x_c, y_c = geom['x_c'], geom['y_c']
    A_xf, A_yf, V = geom['A_xf'], geom['A_yf'], geom['V']
    Nx, Ny, dy = geom['Nx'], geom['Ny'], geom['dy']
    if Nx * Ny > CELLS_2D_MAX:
        raise ValueError(f"Grid {Nx} x {Ny} = {Nx*Ny:,} cells is too large")
    if Nx * Ny > CELLS_2D_WARN:
        hooks.log(f"  [warn] Large grid: {Nx} x {Ny} = {Nx*Ny:,} cells - "
              f"expect a long run")

    solid = solid_mask(x_c, y_c, obstacles)
    fluid = ~solid

    # ── Initial conditions ──────────────────────────────────────────────────
    if profile is not None:
        U, phase, t0 = remap_profile(profile, x_c, y_c, y0)
        # The shocked region must still be spherical: warn if it already
        # touches a wall, an obstacle or the domain edge.
        shocked = profile['p'] > 1.001 * P_AIR
        r_shock = profile['r'][shocked].max() if shocked.any() else profile['r'][0]
        touches = (r_shock > Lx or y0 - r_shock < 0 or y0 + r_shock > Ly)
        for (ox0, ox1, oy0, oy1) in obstacles:
            cx = min(max(0.0, ox0), ox1)
            cy = min(max(y0, oy0), oy1)
            touches |= cx**2 + (cy - y0)**2 < r_shock**2
        if touches:
            hooks.log(f"  [warn] 1D profile shock radius ({r_shock:.2f} m) already "
                  f"reaches a boundary/obstacle - remap is not spherical there.")
    else:
        is_exp = (x_c[:, None] - x0)**2 + (y_c[None, :] - y0)**2 <= r_exp**2
        is_exp &= fluid
        phase = is_exp.astype(int)

        # Energy-conserving stair-step (B24): the cell set holds +-3 % of
        # the true sphere depending on where the centre sits between the
        # faces. Keep rho_exp (JWL is exponential in rho0/rho: rescaling
        # the density would move the initial products pressure ~10 % for
        # a 3 % volume error, rescaling e moves it < 1 %) and scale e so
        # the total energy equals the requested charge's exactly; the
        # products' MASS keeps the rasterisation error. V_true is the
        # sphere clipped to the domain (surface bursts stay truncated).
        n_exp = int(is_exp.sum())
        if n_exp == 0:
            raise ValueError("Resolved charge covers no fluid cell - "
                             "move the burst point or refine the grid")
        V_disc  = float((V * is_exp).sum())
        V_true  = core_geometry.charge_volume_2d(geometry, r_exp, x0, y0,
                                                 Lx, Ly)
        e_scale = V_true / V_disc
        hooks.log(f"  [note] resolved charge: {n_exp} cells, energy "
                  f"scaled x{e_scale:.3f}")
        rho = np.where(is_exp, rho_exp, RHO_AIR)
        e   = np.where(is_exp, JWL_TNT['e0'] * e_scale, E_AIR)
        U = np.array([rho,
                      np.zeros((Nx, Ny)),
                      np.zeros((Nx, Ny)),
                      rho * e])
        t0 = 0.0

    phase = np.where(solid, 0, phase)   # solids are (frozen) ambient air

    # Frozen ambient state re-imposed on solid cells after every step
    U_solid = np.array([RHO_AIR, 0.0, 0.0, RHO_AIR * E_AIR])
    if solid.any():
        U[:, solid] = U_solid[:, None]

    # ── Stop condition & snapshot scheduling ───────────────────────────────
    c_amb      = np.sqrt(GAMMA_AIR * P_AIR / RHO_AIR)
    arrival_p  = P_AIR * 1.001
    safety_cap = t0 + 10.0 * max(Lx, Ly) / c_amb

    # Fluid cells adjacent to OPEN boundaries only (a wall reflection must
    # not end the run).
    open_edge = core_geometry.open_edge_mask((Nx, Ny), bcs, fluid=fluid)
    has_open = open_edge.any()

    # Snapshots are triggered by shock-front POSITION, not time: a strong
    # blast crosses the domain much faster than the acoustic estimate, which
    # would leave time-scheduled snapshots untaken. Intermediate snapshots
    # fire when the front crosses evenly spaced radii between the charge and
    # the stop distance; the final state is always recorded as well.
    d_charge = core_geometry.d_charge_2d(x_c, y_c, x0, y0)
    dists = core_geometry.stop_dists_2d(Lx, Ly, x0, y0, bcs,
                               x_lo_counts=(geometry == 'planar'))
    r_start = r_exp if profile is None else r_shock
    snap_radii = core_geometry.snap_radii(r_start, dists, n_snapshots)

    # ── Gauge setup ────────────────────────────────────────────────────────
    gauges = gauges or []
    gauge_ij, gauge_actual = [], []
    for (gx, gy) in gauges:
        if not (0 <= gx <= Lx and 0 <= gy <= Ly):
            hooks.log(f"  [warn] Gauge ({gx:g}, {gy:g}) outside domain - dropped")
            continue
        i = int(np.argmin(np.abs(x_c - gx)))
        j = int(np.argmin(np.abs(y_c - gy)))
        if solid[i, j]:
            hooks.log(f"  [warn] Gauge ({gx:g}, {gy:g}) inside an obstacle - dropped")
            continue
        gauge_ij.append((i, j))
        gauge_actual.append((float(x_c[i]), float(y_c[j])))
    gauge_times_list  = []
    gauge_press_lists = [[] for _ in gauge_ij]

    # ── Print summary ───────────────────────────────────────────────────────
    bc_lbl = ", ".join(f"{k}={v}" for k, v in bcs.items())
    hooks.log(f"\n{'='*60}")
    hooks.log(f"  2D Blast Solver ({geometry})")
    hooks.log(f"{'='*60}")
    if profile is not None:
        hooks.log(f"  Init            : 1D profile remap "
              f"({profile['charge_kg']:g} kg TNT, t0 = {t0*1e3:.3f} ms)")
    elif geometry == 'planar':
        hooks.log(f"  Charge          : {charge:g} kg TNT per metre "
              f"(infinite cylinder) at ({x0:g}, {y0:g}) m")
    else:
        hooks.log(f"  Charge          : {charge:g} kg TNT (sphere) "
              f"on axis at height {y0:g} m")
    hooks.log(f"  Explosive radius: {r_exp:.4f} m")
    hooks.log(f"  Domain          : {Lx:g} x {Ly:g} m,  cell {dx:g} m  "
          f"({Nx} x {Ny} = {Nx*Ny:,} cells)")
    hooks.log(f"  EOS             : {eos}")
    hooks.log(f"  Boundaries      : {bc_lbl}"
          + ("  (x_lo = symmetry axis)" if geometry == 'axisymmetric' else ""))
    hooks.log(f"  Obstacles       : {len(obstacles)}")
    hooks.log(f"  Gauges          : {len(gauge_ij)}")
    hooks.log(f"  Stop condition  : "
          + ("shock arrival at an open boundary" if has_open
             else "safety cap (no open boundaries)"))
    hooks.log(f"  Safety cap      : {safety_cap*1e3:.1f} ms")
    hooks.log(f"{'='*60}\n")

    # ── Live view & animation frame recording ───────────────────────────────
    run_info = dict(
        dim=2, x_face=geom['x_face'], y_face=geom['y_face'], solid=solid,
        xlabel='r [m]' if geometry == 'axisymmetric' else 'x [m]',
        ylabel='z [m]' if geometry == 'axisymmetric' else 'y [m]',
        title='')
    if geometry == 'axisymmetric':
        # live (r, z) frames can be revolved into a 3D cylinder view
        run_info['revolve3d'] = dict(
            r_c=geom['x_c'], z_c=geom['y_c'], solid=solid, bcs=bcs,
            obstacles=[tuple(o) for o in obstacles],
            z0=y0, r_exp=r_exp, R=Lx, Lz=Ly)
    hooks.run_started(run_info)
    frame_t, frame_p = [], []
    frame_stride     = 1
    last_draw        = 0.0

    # ── Time integration (unsplit Godunov, 1st order) ───────────────────────
    t           = t0
    step        = 0
    snapshots   = {}
    stop_reason = 'safety cap'
    p_peak      = None      # running peak pressure (as solver3d)
    impulse     = None      # accumulated net overpressure impulse [Pa s]

    while t < safety_cap:
        rho_f, u_f, v_f, e_f, p_f, c_f = primitives(U, phase, eos)
        if p_peak is None:
            p_peak = p_f.copy()
            impulse = np.zeros_like(p_f)
        else:
            np.maximum(p_peak, p_f, out=p_peak)

        # ── Record gauges ──────────────────────────────────────────────────
        if gauge_ij:
            gauge_times_list.append(t)
            for k, (i, j) in enumerate(gauge_ij):
                gauge_press_lists[k].append(p_f[i, j])

        if hooks.should_stop():
            stop_reason = 'stopped by user'
            break

        # ── Stop condition: shock at an open boundary ──────────────────────
        if has_open and (p_f[open_edge] > arrival_p).any():
            stop_reason = (f'shock arrived at an open boundary '
                           f'(p_edge = {p_f[open_edge].max():.3e} Pa)')
            break

        # Shock-front position (progress + snapshot triggers)
        shocked = (p_f > arrival_p) & fluid
        r_front = d_charge[shocked].max() if shocked.any() else 0.0
        _stop_dist = min(dists)

        # Take any due snapshots (shock front crossed the next radius)
        if snap_radii:
            while snap_radii and r_front >= snap_radii[0]:
                snap_radii.pop(0)
                label = f"t = {t*1e3:.3f} ms"
                snapshots[label] = dict(p=p_f.copy(), rho=rho_f.copy(),
                                        speed=np.sqrt(u_f**2 + v_f**2))
                hooks.log(f"  Snapshot saved: {label}  "
                      f"(front at {r_front:.2f} m)")

        # ── Animation frames (adaptive stride) & live view ─────────────────
        if record_frames > 0 and step % frame_stride == 0:
            frame_t.append(t)
            frame_p.append(p_f.astype(np.float32))
            if len(frame_p) >= 2 * record_frames:
                frame_t = frame_t[::2]
                frame_p = frame_p[::2]
                frame_stride *= 2
        if hooks.draw_due(step, last_draw) or hooks.exec_will_pause():
            hooks.frame(p_f, t)
            last_draw = time.time()

        # Stepped execution (GUI Exec N / Interrupt): may block here.
        hooks.step_gate()
        if hooks.should_stop():
            stop_reason = 'stopped by user'
            break

        # ── CFL time step (fluid cells only) ───────────────────────────────
        wave = (np.abs(u_f) + c_f) / dx + (np.abs(v_f) + c_f) / dy
        dt = cfl / wave[fluid].max()
        dt = min(dt, safety_cap - t)
        if dt <= 0:
            break
        # same (p at the step start) x (dt of this step) pairing as the
        # state update and as solver3d
        impulse += (p_f - P_AIR) * dt

        # ── Face fluxes (both sweeps) and divergence ───────────────────────
        Fx = face_fluxes(U, p_f, c_f, 1, bcs['x_lo'], bcs['x_hi'], solid)
        Fy = face_fluxes(U, p_f, c_f, 2, bcs['y_lo'], bcs['y_hi'], solid)

        div_F = ((A_xf[1:] * Fx[:, 1:, :] - A_xf[:-1] * Fx[:, :-1, :])
                 + A_yf * (Fy[:, :, 1:] - Fy[:, :, :-1])) / V

        # ── Forward Euler update (+ axisymmetric source) ────────────────────
        U = U - dt * div_F
        if geometry == 'axisymmetric':
            U[1] += dt * p_f / x_c[:, None]
        U[0] = np.maximum(U[0], 1e-10)

        # Pressure floor: prevent e -> infty when a cell is evacuated.
        rho_tmp = U[0]
        e_tmp   = (U[3] - 0.5 * (U[1]**2 + U[2]**2) / rho_tmp) / rho_tmp
        e_floor = E_AIR * 1e-6
        bad     = e_tmp < e_floor
        if bad.any():
            ke = 0.5 * (U[1][bad]**2 + U[2][bad]**2) / rho_tmp[bad]
            U[3][bad] = rho_tmp[bad] * e_floor + ke

        # Re-freeze solid cells
        if solid.any():
            U[:, solid] = U_solid[:, None]

        t    += dt
        step += 1

        hooks.progress(Progress(step=step, t=t, dt=dt, p_max=p_f.max(),
                                frac=min(1.0, r_front / _stop_dist)))

    # ── Final snapshot at stop time ────────────────────────────────────────
    rho_f, u_f, v_f, e_f, p_f, _ = primitives(U, phase, eos)
    if p_peak is None:
        p_peak = p_f.copy()
        impulse = np.zeros_like(p_f)
    else:
        np.maximum(p_peak, p_f, out=p_peak)
    # skip when the loop top already recorded this t (exit via break):
    # a duplicated last timestamp makes dt-based post-processing inf/nan
    if gauge_ij and (not gauge_times_list or gauge_times_list[-1] != t):
        gauge_times_list.append(t)
        for k, (i, j) in enumerate(gauge_ij):
            gauge_press_lists[k].append(p_f[i, j])
    label = f"t = {t*1e3:.3f} ms (final)"
    snapshots[label] = dict(p=p_f.copy(), rho=rho_f.copy(),
                            speed=np.sqrt(u_f**2 + v_f**2))

    if record_frames > 0:
        frame_t.append(t)
        frame_p.append(p_f.astype(np.float32))
    hooks.frame(p_f, t)

    hooks.log(f"\n  Done. {step} steps, t_final = {t*1e3:.3f} ms")
    hooks.log(f"  Stopped: {stop_reason}\n")

    gauge_out = dict(
        times    = np.array(gauge_times_list),
        points   = gauge_actual,
        pressures= [np.array(lst) for lst in gauge_press_lists],
    )
    meta = dict(x_c=x_c, y_c=y_c,
                x_face=geom['x_face'], y_face=geom['y_face'],
                solid=solid, geometry=geometry, Lx=Lx, Ly=Ly, dx=dx,
                eos=eos, bcs=bcs, obstacles=obstacles,
                charge=charge, charge_center=(x0, y0), r_exp=r_exp,
                from_profile=profile is not None,
                # what the USER asked for; gauge_out['points'] is where
                # they landed after snapping to cell centres (QA-33)
                gauges=[tuple(float(v) for v in g) for g in gauges],
                # per-step running peak pressure and net overpressure
                # impulse, same keys as the foam backend
                p_peak=p_peak, impulse=impulse)
    # Full final field (for save_profile_2d -> 3D remap)
    meta['final_state'] = dict(t=t, rho=rho_f, u=u_f, v=v_f, e=e_f, p=p_f,
                               phase=phase)
    if record_frames > 0:
        meta['frames'] = dict(times=np.array(frame_t), pressures=frame_p)
    return Result(snapshots, gauge_out, meta, stop_reason,
                  stop_reason == 'stopped by user')


def solve_2d(case, hooks=None, profile=None):
    """Run a Case2D. Returns a Result. `profile` overrides loading
    case.profile_file_in (used by the chain runner)."""
    if case.init_mode == 'profile1d' and profile is None:
        from ..core.profiles import load_profile
        profile = load_profile(case.profile_file_in)
    return _run_blast_2d(case.geometry, case.Lx, case.Ly, case.cell_size_m,
                         charge=case.charge if case.init_mode == 'charge' else None,
                         charge_center=tuple(case.center),
                         profile=profile, eos=case.eos, bcs=dict(case.bcs),
                         obstacles=[tuple(o) for o in case.obstacles],
                         cfl=case.cfl, n_snapshots=case.n_snapshots,
                         gauges=[tuple(g) for g in case.gauges],
                         record_frames=case.record_frames, hooks=hooks)
