"""3D Cartesian blast solver (unsplit Godunov + HLL)."""

import math
import time

import numpy as np

from ..core import geometry as core_geometry
from ..core.constants import (GAMMA_AIR, RHO_AIR, P_AIR, JWL_TNT,
                              E_AIR, CELLS_WARN, CELLS_REFUSE,
                              MIN_EXP_CELLS)
from ..core.eos import pressure_soundspeed
from ..core.bc import face_fluxes, solid_mask_3d as solid_mask
from ..core.grid import make_grid
from ..core.profiles import (remap_profile_1d_to_3d as remap_profile_1d,
                             remap_profile_2d_to_3d as remap_profile_2d)
from .hooks import ConsoleHooks, Progress, Result

def primitives(U, phase, eos):
    """
    Recover rho, u, v, w, e, p, c from U = [rho, rho*u, rho*v, rho*w, E].
    phase: integer array (0=air, 1=explosive products)
    """
    rho = np.maximum(U[0], 1e-10)
    u   = U[1] / rho
    v   = U[2] / rho
    w   = U[3] / rho
    e   = np.maximum((U[4] - 0.5 * rho * (u**2 + v**2 + w**2)) / rho, 1.0)

    # the identical air/products dispatch lived in all three solvers
    # (A4); eos.pressure_soundspeed is that same block, verbatim
    p, c = pressure_soundspeed(rho, e, phase, eos)

    return rho, u, v, w, e, p, c


def _snapshot(p, rho, u, v, w, j0, k0, t=0.0):
    """Snapshot payload: full 3D overpressure + 2D slices of rho/speed.
    `t` and the decimated 3D density (`rho3`) feed the interactive 3D
    viewer's playback; existing consumers access keys by name."""
    from ..viz3d.sampling import choose_stride, decimate
    speed = np.sqrt(u**2 + v**2 + w**2)
    rho_stride = choose_stride(rho.shape)
    return dict(p=p.astype(np.float32),
                rho_xz=rho[:, j0, :].astype(np.float32),
                rho_xy=rho[:, :, k0].astype(np.float32),
                speed_xz=speed[:, j0, :].astype(np.float32),
                speed_xy=speed[:, :, k0].astype(np.float32),
                t=float(t),
                rho3=decimate(rho, rho_stride))


def _run_blast_3d(Lx, Ly, Lz, cell_size_m,
                  charge=None, charge_center=None,
                  profile=None, profile2d=None,
                  eos='idealGas', bcs=None, obstacles=None,
                  cfl=0.30, n_snapshots=6, gauges=None,
                  record_frames=0, hooks=None,
                  charge_resolution='resolve', t_end=None,
                  slice_axis='y', slice_pos=None):
    """
    Run a 3D Cartesian blast simulation. z is vertical.

    Parameters
    ----------
    Lx, Ly, Lz    : float   Domain extent [m]
    cell_size_m   : float   Uniform cubic cell size [m]
    charge        : float   Direct init: spherical charge mass [kg TNT]
    charge_center : (x0,y0,z0) burst point [m]. For profile2d the z0
                            element is ignored (burst height comes from
                            the profile); a 2-tuple (x0,y0) is accepted.
    profile       : dict    load_profile(...) - 1D spherical remap
    profile2d     : dict    load_profile_2d(...) - axisymmetric remap
    eos           : 'JWL' or 'idealGas'
    bcs           : dict    {'x_lo','x_hi','y_lo','y_hi','z_lo','z_hi'}
                            -> 'open'|'wall'. Default: all open except
                            z_lo='wall' (ground).
    obstacles     : list of (x0,x1,y0,y1,z0,z1) boxes
    cfl           : float   Sum of the three directional Courant numbers
    n_snapshots   : int     3D overpressure snapshots (may be auto-reduced
                            to bound memory)
    gauges        : list of (x, y, z) gauge locations [m]
    record_frames : int     ~frames of the vertical x-z slice through the
                            burst kept for an animation (0 = off)
    live          : bool    Live window of that slice while running
    charge_resolution : 'resolve' | 'smear'. Direct charge init only.
                            'resolve' refines the grid so the charge
                            radius spans >= 5 cells (refinement is cubic
                            in 3D and can exceed the cell cap). 'smear'
                            keeps cell_size_m and deposits the charge's
                            mass and detonation energy into a source
                            ball of a few cells instead.
    t_end         : float   Optional simulation end time [s]; the run
                            stops at t0 + t_end even if the shock has
                            not reached an open boundary yet.
    slice_axis    : 'x'|'y'|'z'  Normal of the live-view / animation
                            slice (default 'y': the vertical x-z plane).
    slice_pos     : float   Slice position along that axis [m]; None
                            puts it through the burst point.

    Returns
    -------
    snapshots : dict  label -> dict(p [3D float32], rho_xz, rho_xy,
                                    speed_xz, speed_xy [2D slices])
    gauge_out : dict  'times', 'points', 'pressures'
    meta      : dict  grid, solid mask, run description, optional 'frames'
    """
    if hooks is None:
        hooks = ConsoleHooks(3)
    if bcs is None:
        bcs = dict(x_lo='open', x_hi='open', y_lo='open', y_hi='open',
                   z_lo='wall', z_hi='open')
    obstacles = obstacles or []
    dx = cell_size_m
    n_init = sum(x is not None for x in (charge, profile, profile2d))
    if n_init != 1:
        raise ValueError("Give exactly one of: charge, profile, profile2d")
    if charge_resolution not in ('resolve', 'smear'):
        raise ValueError("charge_resolution must be 'resolve' or 'smear'")

    # ── Burst point & charge geometry ───────────────────────────────────────
    rho_exp = JWL_TNT['rho0']
    smeared = False
    if profile2d is not None:
        x0, y0 = charge_center[0], charge_center[1]
        z0 = profile2d['y0']            # burst height from the 2D profile
        r_exp = r_src = profile2d['r_exp']
        if profile2d['eos'] != eos:
            hooks.log(f"  [warn] Profile EOS '{profile2d['eos']}' differs from "
                  f"run EOS '{eos}' - products will be evaluated with '{eos}'.")
        if z0 > Lz:
            raise ValueError(f"Profile burst height {z0:g} m exceeds "
                             f"domain height Lz = {Lz:g} m")
    elif profile is not None:
        x0, y0, z0 = charge_center
        r_exp = r_src = profile['r_exp']
        if profile['eos'] != eos:
            hooks.log(f"  [warn] Profile EOS '{profile['eos']}' differs from "
                  f"run EOS '{eos}' - products will be evaluated with '{eos}'.")
    else:
        if charge <= 0:
            raise ValueError("Charge must be > 0")
        x0, y0, z0 = charge_center
        r_exp = (3.0 * charge / (4.0 * np.pi * rho_exp)) ** (1.0 / 3.0)

        # Under-resolved charge: 'smear' keeps dx and enlarges the source
        # ball to a few cells (mass & energy conserving, see init below);
        # 'resolve' refines dx so the true radius spans MIN_EXP_CELLS.
        smeared = (charge_resolution == 'smear'
                   and dx > r_exp / MIN_EXP_CELLS)
        r_src = max(r_exp, 2.0 * dx) if smeared else r_exp

        if not (0 <= x0 <= Lx and 0 <= y0 <= Ly and 0 <= z0 <= Lz):
            raise ValueError(f"Charge centre ({x0:g}, {y0:g}, {z0:g}) is "
                             f"outside the domain")
        # Crossing a wall is a surface burst; poking an open boundary is not.
        for over, side in ((r_src - x0, 'x_lo'), (r_src - (Lx - x0), 'x_hi'),
                           (r_src - y0, 'y_lo'), (r_src - (Ly - y0), 'y_hi'),
                           (r_src - z0, 'z_lo'), (r_src - (Lz - z0), 'z_hi')):
            if over <= 0:
                continue
            if bcs[side] == 'wall':
                hooks.log(f"  [note] Charge is truncated by the {side} wall "
                      f"(surface burst)")
            else:
                raise ValueError(f"Charge (source radius = {r_src:.4f} m) "
                                 f"pokes through the open '{side}' boundary")
        for (ox0, ox1, oy0, oy1, oz0, oz1) in obstacles:
            cx = min(max(x0, ox0), ox1)
            cy = min(max(y0, oy0), oy1)
            cz = min(max(z0, oz0), oz1)
            if (cx - x0)**2 + (cy - y0)**2 + (cz - z0)**2 < r_src**2:
                raise ValueError("Charge overlaps an obstacle")

        if smeared:
            hooks.log(f"  [note] Charge under-resolved at dx = {dx:g} m "
                  f"(r_exp = {r_exp:.4f} m): mass & energy smeared into a "
                  f"{r_src:.4f} m source ball")
        elif dx > r_exp / MIN_EXP_CELLS:
            # Resolve the charge; refinement is CUBIC in cell count in 3D.
            # the largest spacing that keeps MIN_EXP_CELLS across the
            # charge AND divides Lx exactly (ceil: never coarser)
            dx = Lx / math.ceil(Lx / (r_exp / MIN_EXP_CELLS))
            n_est = int(Lx / dx) * int(Ly / dx) * int(Lz / dx)
            if n_est > CELLS_REFUSE:
                raise ValueError(
                    f"Resolving the charge needs dx = {dx:.5f} m -> "
                    f"~{n_est:,} cells (refinement is cubic in 3D). Shrink "
                    f"the domain, enlarge the charge, remap from 1D/2D, or "
                    f"use charge_resolution='smear' to keep your cell size.")
            hooks.log(f"  [auto] Cell size reduced to {dx:.5f} m "
                  f"({MIN_EXP_CELLS} cells across charge radius)")

    # ── Grid & solids ───────────────────────────────────────────────────────
    grid = make_grid(Lx, Ly, Lz, dx)
    if grid['dx'] != dx:
        # dx did not divide Lx: core.grid fitted the exact domain with a
        # slightly different (cubic) spacing - use it everywhere below
        hooks.log(f"  [note] Cell size adjusted {dx:g} -> {grid['dx']:.4g} m "
                  f"to fit {Lx:g} m exactly (domain {grid['x_face'][-1]:g} "
                  f"x {grid['y_face'][-1]:.4g} x {grid['z_face'][-1]:.4g} m)")
        dx = grid['dx']
        Lx, Ly, Lz = (float(grid['x_face'][-1]), float(grid['y_face'][-1]),
                      float(grid['z_face'][-1]))
    x_c, y_c, z_c = grid['x_c'], grid['y_c'], grid['z_c']
    Nx, Ny, Nz = grid['Nx'], grid['Ny'], grid['Nz']
    n_cells = Nx * Ny * Nz
    if n_cells > CELLS_REFUSE:
        raise ValueError(f"Grid {Nx} x {Ny} x {Nz} = {n_cells:,} cells "
                         f"exceeds the {CELLS_REFUSE:,} cap")
    if n_cells > CELLS_WARN:
        hooks.log(f"  [warn] Large grid: {Nx} x {Ny} x {Nz} = {n_cells:,} "
              f"cells - expect a long run and GBs of RAM")

    solid = solid_mask(x_c, y_c, z_c, obstacles)
    fluid = ~solid

    # Bound snapshot memory: full 3D float32 overpressure per snapshot.
    max_snaps = max(1, int(1.5e9 / (4 * n_cells)) - 1)
    if n_snapshots > max_snaps:
        hooks.log(f"  [note] n_snapshots reduced {n_snapshots} -> {max_snaps} "
              f"to bound snapshot memory")
        n_snapshots = max_snaps

    # ── Initial conditions ──────────────────────────────────────────────────
    r_shock = None
    if profile2d is not None:
        U, phase, t0 = remap_profile_2d(profile2d, x_c, y_c, z_c, x0, y0)
        shocked2 = profile2d['p'] > 1.001 * P_AIR
        if shocked2.any():
            R2 = profile2d['r_c'][:, None]
            Z2 = profile2d['z_c'][None, :]
            r_shock = float(np.sqrt(R2**2 + (Z2 - z0)**2)[shocked2].max())
        else:
            r_shock = r_exp
        if (x0 - r_shock < 0 or x0 + r_shock > Lx
                or y0 - r_shock < 0 or y0 + r_shock > Ly
                or z0 + r_shock > Lz):
            hooks.log(f"  [warn] 2D profile shock radius ({r_shock:.2f} m) "
                  f"already reaches a 3D boundary - remap may clip the field")
    elif profile is not None:
        U, phase, t0 = remap_profile_1d(profile, x_c, y_c, z_c, (x0, y0, z0))
        shocked1 = profile['p'] > 1.001 * P_AIR
        r_shock = (float(profile['r'][shocked1].max()) if shocked1.any()
                   else r_exp)
        if (min(x0, Lx - x0, y0, Ly - y0, z0, Lz - z0) < r_shock):
            hooks.log(f"  [warn] 1D profile shock radius ({r_shock:.2f} m) "
                  f"already reaches a 3D boundary - remap may clip the field")
    else:
        X = x_c[:, None, None]
        Y = y_c[None, :, None]
        Z = z_c[None, None, :]
        is_exp = ((X - x0)**2 + (Y - y0)**2 + (Z - z0)**2 <= r_src**2) & fluid
        phase = is_exp.astype(int)
        if smeared:
            # Energy-ball source: add the charge's total mass and
            # detonation energy on top of the ambient air in the source
            # cells, so yield is exact even though the ball is coarse.
            n_src = int(is_exp.sum())
            if n_src == 0:
                raise ValueError("Smeared charge covers no fluid cell - "
                                 "move the burst point or refine the grid")
            V_src   = n_src * dx**3
            rho_src = RHO_AIR + charge / V_src
            e_src   = (RHO_AIR * E_AIR + charge * JWL_TNT['e0'] / V_src) \
                / rho_src
            rho = np.where(is_exp, rho_src, RHO_AIR)
            e   = np.where(is_exp, e_src, E_AIR)
        else:
            rho = np.where(is_exp, rho_exp, RHO_AIR)
            e   = np.where(is_exp, JWL_TNT['e0'], E_AIR)
        zeros = np.zeros((Nx, Ny, Nz))
        U = np.array([rho, zeros, zeros.copy(), zeros.copy(), rho * e])
        t0 = 0.0
        r_shock = r_src

    # Warn if the remapped shocked region overlaps an obstacle
    if profile is not None or profile2d is not None:
        if solid.any():
            d3 = np.sqrt((x_c[:, None, None] - x0)**2
                         + (y_c[None, :, None] - y0)**2
                         + (z_c[None, None, :] - z0)**2)
            if (solid & (d3 <= r_shock)).any():
                hooks.log("  [warn] An obstacle lies inside the remapped shocked "
                      "region - the profile is not valid there")
            del d3

    phase = np.where(solid, 0, phase)
    U_solid = np.array([RHO_AIR, 0.0, 0.0, 0.0, RHO_AIR * E_AIR])
    if solid.any():
        U[:, solid] = U_solid[:, None]

    # ── Stop condition & snapshot scheduling ───────────────────────────────
    c_amb      = np.sqrt(GAMMA_AIR * P_AIR / RHO_AIR)
    arrival_p  = P_AIR * 1.001
    safety_cap = t0 + 10.0 * max(Lx, Ly, Lz) / c_amb
    cap_is_end = bool(t_end) and t0 + t_end < safety_cap
    if cap_is_end:
        safety_cap = t0 + t_end

    open_edge = core_geometry.open_edge_mask((Nx, Ny, Nz), bcs, fluid=fluid)
    has_open = open_edge.any()

    d_charge = core_geometry.d_charge_3d(x_c, y_c, z_c, [(x0, y0, z0)])
    dists = core_geometry.stop_dists_3d(Lx, Ly, Lz, [(x0, y0, z0)], bcs)
    snap_radii = core_geometry.snap_radii(r_shock, dists, n_snapshots)

    # ── Gauge setup ────────────────────────────────────────────────────────
    gauges = gauges or []
    gauge_ijk, gauge_actual = [], []
    for (gx, gy, gz) in gauges:
        if not (0 <= gx <= Lx and 0 <= gy <= Ly and 0 <= gz <= Lz):
            hooks.log(f"  [warn] Gauge ({gx:g}, {gy:g}, {gz:g}) outside domain "
                  f"- dropped")
            continue
        i = int(np.argmin(np.abs(x_c - gx)))
        j = int(np.argmin(np.abs(y_c - gy)))
        k = int(np.argmin(np.abs(z_c - gz)))
        if solid[i, j, k]:
            hooks.log(f"  [warn] Gauge ({gx:g}, {gy:g}, {gz:g}) inside an "
                  f"obstacle - dropped")
            continue
        gauge_ijk.append((i, j, k))
        gauge_actual.append((float(x_c[i]), float(y_c[j]), float(z_c[k])))
    gauge_times_list  = []
    gauge_press_lists = [[] for _ in gauge_ijk]

    # Slice indices for the 3D snapshots (always through the burst)
    j0 = int(np.argmin(np.abs(y_c - y0)))   # vertical x-z plane through burst
    k0 = int(np.argmin(np.abs(z_c - z0)))   # horizontal x-y plane at burst height

    # Live-view / animation slice: user-selectable normal + position
    if slice_axis not in ('x', 'y', 'z'):
        raise ValueError("slice_axis must be 'x', 'y' or 'z'")
    ax_i = 'xyz'.index(slice_axis)
    _coords = (x_c, y_c, z_c)
    _pos = (x0, y0, z0)[ax_i] if slice_pos is None else float(slice_pos)
    s0 = int(np.argmin(np.abs(_coords[ax_i] - _pos)))
    live_sl = tuple(s0 if a == ax_i else slice(None) for a in range(3))
    live_faces = {'x': (grid['y_face'], grid['z_face']),
                  'y': (grid['x_face'], grid['z_face']),
                  'z': (grid['x_face'], grid['y_face'])}[slice_axis]
    live_labels = {'x': ('y [m]', 'z [m]'), 'y': ('x [m]', 'z [m]'),
                   'z': ('x [m]', 'y [m]')}[slice_axis]
    live_title = f'{slice_axis} = {_coords[ax_i][s0]:.2f} m'

    # ── Print summary ───────────────────────────────────────────────────────
    bc_lbl = ", ".join(f"{k}={v}" for k, v in bcs.items())
    hooks.log(f"\n{'='*62}")
    hooks.log(f"  3D Blast Solver")
    hooks.log(f"{'='*62}")
    if profile2d is not None:
        hooks.log(f"  Init            : 2D axisym profile remap "
              f"({profile2d['charge_kg']:g} kg TNT, t0 = {t0*1e3:.3f} ms)")
    elif profile is not None:
        hooks.log(f"  Init            : 1D profile remap "
              f"({profile['charge_kg']:g} kg TNT, t0 = {t0*1e3:.3f} ms)")
    else:
        hooks.log(f"  Charge          : {charge:g} kg TNT (sphere)")
    hooks.log(f"  Burst point     : ({x0:g}, {y0:g}, {z0:g}) m")
    hooks.log(f"  Explosive radius: {r_exp:.4f} m"
          + (f" (smeared to {r_src:.4f} m)" if smeared else ""))
    hooks.log(f"  Domain          : {Lx:g} x {Ly:g} x {Lz:g} m,  cell {dx:g} m")
    hooks.log(f"  Grid            : {Nx} x {Ny} x {Nz} = {n_cells:,} cells")
    hooks.log(f"  EOS             : {eos}")
    hooks.log(f"  Boundaries      : {bc_lbl}")
    hooks.log(f"  Obstacles       : {len(obstacles)}")
    hooks.log(f"  Gauges          : {len(gauge_ijk)}")
    hooks.log(f"  Stop condition  : "
          + ("shock arrival at an open boundary" if has_open
             else "safety cap (no open boundaries)"))
    hooks.log(f"  {'End time' if cap_is_end else 'Safety cap':<16}: "
          f"{safety_cap*1e3:.1f} ms")
    hooks.log(f"  (3D steps are slow: expect roughly "
          f"{max(1, n_cells // 2_000_000)}-{max(1, n_cells // 500_000)} s/step)")
    hooks.log(f"{'='*62}\n")

    # ── Live view & animation frame recording (vertical x-z slice) ─────────
    hooks.run_started(dict(
        dim=3, x_face=live_faces[0], y_face=live_faces[1],
        solid=solid[live_sl], xlabel=live_labels[0],
        ylabel=live_labels[1], title=live_title,
        scene3d=dict(x_c=x_c, y_c=y_c, z_c=z_c, dx=dx, solid=solid,
                     obstacles=obstacles, Lx=Lx, Ly=Ly, Lz=Lz,
                     charge_center=(x0, y0, z0), r_exp=r_src, bcs=bcs)))
    frame_t, frame_p = [], []
    frame_stride     = 1
    last_draw        = 0.0
    last_draw3d      = 0.0

    # ── Time integration (unsplit Godunov, 1st order) ───────────────────────
    t           = t0
    step        = 0
    snapshots   = {}
    stop_reason = 'safety cap'
    p_peak      = None      # running peak pressure (viewer field)
    impulse     = None      # accumulated overpressure impulse [Pa s]

    while t < safety_cap:
        rho_f, u_f, v_f, w_f, e_f, p_f, c_f = primitives(U, phase, eos)
        if p_peak is None:
            p_peak = p_f.copy()
            impulse = np.zeros_like(p_f)
        else:
            np.maximum(p_peak, p_f, out=p_peak)

        # ── Record gauges ──────────────────────────────────────────────────
        if gauge_ijk:
            gauge_times_list.append(t)
            for g, (i, j, k) in enumerate(gauge_ijk):
                gauge_press_lists[g].append(p_f[i, j, k])

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

        # ── Snapshots when the front crosses the next radius ───────────────
        if snap_radii:
            while snap_radii and r_front >= snap_radii[0]:
                snap_radii.pop(0)
                label = f"t = {t*1e3:.3f} ms"
                snapshots[label] = _snapshot(p_f, rho_f, u_f, v_f, w_f,
                                             j0, k0, t)
                hooks.log(f"  Snapshot saved: {label}  (front at {r_front:.2f} m)")

        # ── Animation frames (adaptive stride) & live view ─────────────────
        if record_frames > 0 and step % frame_stride == 0:
            frame_t.append(t)
            frame_p.append(p_f[live_sl].astype(np.float32))
            if len(frame_p) >= 2 * record_frames:
                frame_t = frame_t[::2]
                frame_p = frame_p[::2]
                frame_stride *= 2
        will_pause = hooks.exec_will_pause()
        if hooks.draw_due(step, last_draw) or will_pause:
            hooks.frame(p_f[live_sl], t)
            last_draw = time.time()
        if (hooks.draw3d_due(step, last_draw3d) or will_pause) \
                and hooks.wants_frame3d():
            hooks.frame3d(t, dict(p=p_f, rho=rho_f, e=e_f,
                                  p_peak=p_peak, imp=impulse))
            last_draw3d = time.time()

        # Stepped execution (GUI Exec N / Interrupt): may block here.
        hooks.step_gate()
        if hooks.should_stop():
            stop_reason = 'stopped by user'
            break

        # ── CFL time step (fluid cells only) ───────────────────────────────
        wave = (np.abs(u_f) + np.abs(v_f) + np.abs(w_f) + 3.0 * c_f) / dx
        dt = cfl / wave[fluid].max()
        dt = min(dt, safety_cap - t)
        if dt <= 0:
            break
        del wave
        impulse += (p_f - P_AIR) * dt

        # ── Three HLL sweeps, memory-lean accumulation ──────────────────────
        U_new = U.copy()
        for n, lo, hi in ((1, 'x_lo', 'x_hi'),
                          (2, 'y_lo', 'y_hi'),
                          (3, 'z_lo', 'z_hi')):
            F = face_fluxes(U, p_f, c_f, n, bcs[lo], bcs[hi], solid)
            sl_hi = (slice(None),) + (slice(None),) * (n - 1) + (slice(1, None),)
            sl_lo = (slice(None),) + (slice(None),) * (n - 1) + (slice(None, -1),)
            U_new -= (dt / dx) * (F[sl_hi] - F[sl_lo])
            del F
        U = U_new
        U[0] = np.maximum(U[0], 1e-10)

        # Pressure floor: prevent e -> infty when a cell is evacuated.
        rho_tmp = U[0]
        e_tmp   = (U[4] - 0.5 * (U[1]**2 + U[2]**2 + U[3]**2) / rho_tmp) / rho_tmp
        e_floor = E_AIR * 1e-6
        bad     = e_tmp < e_floor
        if bad.any():
            ke = 0.5 * (U[1][bad]**2 + U[2][bad]**2 + U[3][bad]**2) / rho_tmp[bad]
            U[4][bad] = rho_tmp[bad] * e_floor + ke
        del e_tmp, bad

        # Re-freeze solid cells
        if solid.any():
            U[:, solid] = U_solid[:, None]

        t    += dt
        step += 1

        hooks.progress(Progress(step=step, t=t, dt=dt, p_max=p_f.max(),
                                frac=min(1.0, r_front / _stop_dist)))

    if stop_reason == 'safety cap' and cap_is_end:
        stop_reason = 'end time reached'

    # ── Final snapshot at stop time ────────────────────────────────────────
    rho_f, u_f, v_f, w_f, e_f, p_f, _ = primitives(U, phase, eos)
    if p_peak is None:
        p_peak = p_f.copy()
        impulse = np.zeros_like(p_f)
    else:
        np.maximum(p_peak, p_f, out=p_peak)
    # skip when the loop top already recorded this t (exit via break):
    # a duplicated last timestamp makes dt-based post-processing inf/nan
    if gauge_ijk and (not gauge_times_list or gauge_times_list[-1] != t):
        gauge_times_list.append(t)
        for g, (i, j, k) in enumerate(gauge_ijk):
            gauge_press_lists[g].append(p_f[i, j, k])
    label = f"t = {t*1e3:.3f} ms (final)"
    snapshots[label] = _snapshot(p_f, rho_f, u_f, v_f, w_f, j0, k0, t)

    if record_frames > 0:
        frame_t.append(t)
        frame_p.append(p_f[live_sl].astype(np.float32))
    hooks.frame(p_f[live_sl], t)
    hooks.frame3d(t, dict(p=p_f, rho=rho_f, e=e_f,
                          p_peak=p_peak, imp=impulse), force=True)

    hooks.log(f"\n  Done. {step} steps, t_final = {t*1e3:.3f} ms")
    hooks.log(f"  Stopped: {stop_reason}\n")

    gauge_out = dict(
        times    = np.array(gauge_times_list),
        points   = gauge_actual,
        pressures= [np.array(lst) for lst in gauge_press_lists],
    )
    from_profile = '2d' if profile2d is not None else (
                   '1d' if profile is not None else None)
    meta = dict(x_c=x_c, y_c=y_c, z_c=z_c,
                x_face=grid['x_face'], y_face=grid['y_face'],
                z_face=grid['z_face'], j0=j0, k0=k0,
                slice_axis=slice_axis, s0=s0,
                solid=solid, Lx=Lx, Ly=Ly, Lz=Lz, dx=dx,
                eos=eos, bcs=bcs, obstacles=obstacles,
                charge=charge, charge_center=(x0, y0, z0), r_exp=r_exp,
                r_src=r_src, from_profile=from_profile,
                # what the USER asked for; gauge_out['points'] is where
                # they landed after snapping to cell centres (QA-33)
                gauges=[tuple(float(v) for v in g) for g in (gauges or [])],
                # per-step running peak pressure and net overpressure
                # impulse (the viewer fields), same keys as the foam backend
                p_peak=p_peak, impulse=impulse)
    if record_frames > 0:
        meta['frames'] = dict(times=np.array(frame_t), pressures=frame_p)
    return Result(snapshots, gauge_out, meta, stop_reason,
                  stop_reason == 'stopped by user')


def solve_3d(case, hooks=None, profile=None, profile2d=None):
    """Run a Case3D. Returns a Result."""
    if case.init_mode == 'profile1d' and profile is None:
        from ..core.profiles import load_profile
        profile = load_profile(case.profile_file_in)
    if case.init_mode == 'profile2d' and profile2d is None:
        from ..core.profiles import load_profile_2d
        profile2d = load_profile_2d(case.profile_file_in)
    return _run_blast_3d(case.Lx, case.Ly, case.Lz, case.cell_size_m,
                         charge=case.charge if case.init_mode == 'charge' else None,
                         charge_center=tuple(case.center),
                         profile=profile, profile2d=profile2d,
                         eos=case.eos, bcs=dict(case.bcs),
                         obstacles=[tuple(o) for o in case.obstacles],
                         cfl=case.cfl, n_snapshots=case.n_snapshots,
                         gauges=[tuple(g) for g in case.gauges],
                         record_frames=case.record_frames, hooks=hooks,
                         charge_resolution=getattr(case, 'charge_resolution',
                                                   'resolve'),
                         t_end=getattr(case, 't_end', 0.0) or None,
                         slice_axis=getattr(case, 'slice_axis', 'y'),
                         slice_pos=getattr(case, 'slice_pos', None))
