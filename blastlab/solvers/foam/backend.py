"""blastFoam backend entry points (phased bring-up).

Signatures mirror the native solvers exactly
(`solve_1d_foam(case, hooks=None) -> Result`) and the returned Result
reproduces the native per-dim shapes, so the GUI results panel, gauge
writers, profile export and chain remap work unchanged.

Run loop model: blastFoam streams stdout (every step prints `Time =`,
`deltaT =` and `max(p):` lines -> Progress), while written time
directories are polled and ingested as backend "steps" (live frames,
step_gate, stop conditions). Graceful stop and the shock-arrival
condition both go through `stopAt writeNow` so a final complete time
directory is always written.

`IMPLEMENTED` gates pre-flight validation so a not-yet-available dim
errors while editing the form instead of at launch.
"""

import os
import re
import time as _time

import numpy as np

from ...core.constants import P_AIR
from ..hooks import Progress, Result, RunHooks
from . import env, reader, runner, writer
from .materials import MATERIALS

#: dims with a working blastFoam backend (grows per phase)
IMPLEMENTED = frozenset({1, 2, 3})

_RE_TIME = re.compile(r'^Time = ([0-9.eE+-]+)s?$')
_RE_DT = re.compile(r'^deltaT = ([0-9.eE+-]+)$')
_RE_MAXP = re.compile(r'^max\(p\):\s*([0-9.eE+-]+)')

_ARRIVAL_P = 1.001 * P_AIR      # native shock-arrival threshold
_STOP_GRACE_S = 60.0            # writeNow -> kill escalation window
_POLL_S = 0.25


def _todo(dim):
    raise NotImplementedError(
        f"The blastFoam backend for {dim}D cases is not implemented yet "
        f"- select the 'native' solver for this case.")


def _preflight(case, hooks):
    ok, detail = env.check_available()
    if not ok:
        raise RuntimeError(f"blastFoam backend unavailable: {detail}")
    from ...core.case import validate_case
    rep = validate_case(case)
    if not rep.ok:
        raise ValueError("Invalid blastFoam case:\n  "
                         + "\n  ".join(rep.errors))
    spec = writer.write_case(case)
    hooks.log(f"  [blastfoam] case directory: {spec.case_unc}")
    hooks.log("  [blastfoam] meshing + charge init "
              "(blockMesh && setRefinedFields)...")
    # -noRefine: v1 keeps the mesh uniform (grid already sized to
    # resolve the charge), so no refiner configuration is needed
    runner.run_stage(spec.case_posix,
                     ['blockMesh', 'setRefinedFields -noRefine'])
    return spec


def _progress_line(line, st, hooks, end_time):
    """Parse one solver stdout line into Progress state. st['frac'],
    when not None, overrides the t/end_time estimate (3D uses the
    shock-front radius, updated per ingested write)."""
    m = _RE_TIME.match(line)
    if m:
        st['t'] = float(m.group(1))
        st['step'] += 1
        frac = st.get('frac')
        if frac is None:
            frac = min(1.0, st['t'] / end_time)
        hooks.progress(Progress(step=st['step'], t=st['t'], dt=st['dt'],
                                p_max=st['p_max'], frac=frac))
        return
    m = _RE_DT.match(line)
    if m:
        st['dt'] = float(m.group(1))
        return
    m = _RE_MAXP.match(line)
    if m:
        st['p_max'] = float(m.group(1))
        return
    if 'FOAM Warning' in line or 'FOAM FATAL' in line:
        hooks.log('  [foam] ' + line.rstrip())


def _note_pause(hooks, st, will_pause):
    """One-time note: foam Exec/Interrupt operates at written-frame
    granularity (not per solver step like the native solvers)."""
    if will_pause and not st.get('pause_noted'):
        st['pause_noted'] = True
        hooks.log('  [blastfoam] pausing at a written frame - the WSL '
                  'solver is suspended while paused; Exec advances by '
                  'written frames, Stop ends the run')


def _gated_step(run, hooks):
    """step_gate() with the WSL solver truly suspended while the GUI
    holds the gate (SIGSTOP/CONT around the blocking wait)."""
    paused = getattr(hooks, 'exec_paused', None)
    if paused is not None and paused() and not run.stop_requested:
        run.suspend()
        try:
            hooks.step_gate()
        finally:
            run.resume()
    else:
        hooks.step_gate()


def _pick_snapshots(store, names, n_snapshots):
    """n_snapshots evenly-spaced interior written times (t > 0), final
    excluded (it gets its own '(final)' label)."""
    interior = [n for n in names[:-1] if store[n]['t'] > 0.0]
    if not interior or n_snapshots <= 0:
        return []
    k = min(n_snapshots, len(interior))
    idx = np.unique(np.linspace(0, len(interior) - 1, k)
                    .round().astype(int))
    return [interior[i] for i in idx]


def _gauges_from_probes(spec):
    """blastProbes output -> the native gauges dict (1D: radii)."""
    empty = dict(times=np.array([]), radii=[], pressures=[])
    if not spec.probe_pts:
        return empty
    probes = reader.read_probes(spec.case_unc)
    if not probes:
        return empty
    radii = []
    for i, pt in enumerate(probes['points']):
        if np.isnan(pt[0]) and i < len(spec.gauge_ids):
            radii.append(float(spec.gauge_ids[i]))   # header fallback
        else:
            radii.append(float(pt[0]))               # snapped location
    return dict(times=probes['times'], radii=radii,
                pressures=probes['pressures'])


def _log_banner_1d(hooks, case, spec):
    m = MATERIALS[spec.material]
    bar = '=' * 55
    for line in (
            '', bar, '  1D Spherical Blast - blastFoam (WSL)', bar,
            f'  Charge          : {case.charge_kg} kg {spec.material}',
            f'  Explosive radius: {spec.r_exp:.4f} m',
            f'  Domain radius   : {case.radius_m} m',
            f'  Cell size       : {spec.dx:.5f} m  ({spec.nx} cells)',
            '  EOS             : JWL products + ideal-gas air',
            f'  vDet            : {m.vDet:g} m/s',
            f'  Safety cap      : {spec.end_time*1e3:.1f} ms',
            f'  Write interval  : {spec.write_interval*1e3:.4f} ms',
            bar, ''):
        hooks.log(line)


def solve_1d_foam(case, hooks=None):
    """Run a Case1D on blastFoam. Returns a Result shaped exactly like
    the native solve_1d."""
    hooks = hooks or RunHooks()
    spec = _preflight(case, hooks)
    m = MATERIALS[spec.material]
    r = spec.grid['r']
    fields = ('p', 'rho', 'U', f'alpha.{spec.phase}')

    _log_banner_1d(hooks, case, spec)
    hooks.run_started(dict(dim=1, r=r, radius_m=case.radius_m))

    store = {}                      # dirname -> dict(t, p, rho, u)
    st = dict(step=0, t=0.0, dt=0.0, p_max=float(P_AIR))
    stop_reason = 'safety cap'
    stop_deadline = None
    last_draw = 0.0

    run = runner.FoamRun(spec.case_posix, spec.case_unc)

    def request_stop(reason):
        nonlocal stop_reason, stop_deadline
        stop_reason = reason
        run.request_write_now()
        stop_deadline = _time.time() + _STOP_GRACE_S

    def ingest_ready():
        nonlocal last_draw
        for _t_disp, name in reader.list_times(spec.case_unc):
            if name in store:
                continue
            dpath = os.path.join(spec.case_unc, name)
            if not reader.time_ready(dpath, fields):
                continue
            try:
                t, _dt = reader.read_time(dpath)
                entry = dict(
                    t=t,
                    p=reader.read_scalar(
                        os.path.join(dpath, 'p'), spec.n_cells),
                    rho=reader.read_scalar(
                        os.path.join(dpath, 'rho'), spec.n_cells),
                    u=reader.read_vector(
                        os.path.join(dpath, 'U'), spec.n_cells)[:, 0])
            except (ValueError, OSError):
                continue            # mid-write over 9p; retry next poll
            store[name] = entry
            will_pause = hooks.exec_will_pause()
            if hooks.draw_due(st['step'], last_draw) or will_pause:
                hooks.frame(np.array([r, entry['p']]), entry['t'])
                last_draw = _time.time()
            if not run.stop_requested and entry['p'][-1] > _ARRIVAL_P:
                request_stop('shock arrived at outer boundary '
                             f"(p_last = {entry['p'][-1]:.3e} Pa)")
            _note_pause(hooks, st, will_pause)
            _gated_step(run, hooks)

    try:
        while True:
            for line in run.drain(_POLL_S):
                _progress_line(line, st, hooks, spec.end_time)
            ingest_ready()
            if hooks.should_stop() and not run.stop_requested:
                request_stop('stopped by user')
            if stop_deadline and run.running \
                    and _time.time() > stop_deadline:
                hooks.log('  [blastfoam] solver did not stop cleanly '
                          '- killing it')
                run.kill()
            if not run.running:
                for line in run.drain(0.05):
                    _progress_line(line, st, hooks, spec.end_time)
                ingest_ready()      # final sweep - files are complete
                break
    finally:
        if run.running:
            run.kill()

    if run.returncode not in (0, None) and not run.stop_requested:
        raise RuntimeError(
            f"blastFoam failed (exit {run.returncode}) - case kept at "
            f"{spec.case_unc}\n{run.tail()}")
    if not store:
        raise RuntimeError(
            "blastFoam produced no readable time steps - case kept at "
            f"{spec.case_unc}\n{run.tail()}")

    # ── finalize: exact native Result shapes ────────────────────────────
    names = sorted(store, key=lambda n: store[n]['t'])
    fin_name = names[-1]
    fin = store[fin_name]

    snapshots = {}
    for name in _pick_snapshots(store, names, case.n_snapshots):
        e = store[name]
        label = f"t = {e['t']*1e3:.3f} ms"
        if label not in snapshots:
            snapshots[label] = dict(r=r.copy(), p=e['p'], rho=e['rho'],
                                    u=e['u'])
    snapshots[f"t = {fin['t']*1e3:.3f} ms (final)"] = dict(
        r=r.copy(), p=fin['p'], rho=fin['rho'], u=fin['u'])

    dfin = os.path.join(spec.case_unc, fin_name)
    alpha = reader.read_scalar(
        os.path.join(dfin, f'alpha.{spec.phase}'), spec.n_cells)
    phase = (alpha > 0.5).astype(int)
    e_path = os.path.join(dfin, 'e')
    if os.path.isfile(e_path):
        e_arr = reader.read_scalar(e_path, spec.n_cells)
    else:                           # reconstruct from temperature
        T = reader.read_scalar(os.path.join(dfin, 'T'), spec.n_cells)
        e_arr = np.where(phase == 1, m.Cv_products, writer.CV_AIR) * T
    final_profile = dict(t=fin['t'], r=r.copy(), rho=fin['rho'].copy(),
                         u=fin['u'].copy(), e=e_arr, p=fin['p'].copy(),
                         phase=phase, charge_kg=case.charge_kg,
                         eos='JWL', r_exp=spec.r_exp,
                         radius_m=case.radius_m)

    hooks.log(f"\n  Done. {st['step']} solver steps, t_final = "
              f"{fin['t']*1e3:.3f} ms")
    hooks.log(f"  Stopped: {stop_reason}\n")
    hooks.frame(np.array([r, fin['p']]), fin['t'])

    meta = dict(final_profile=final_profile, r=r, radius_m=case.radius_m,
                charge_kg=case.charge_kg, eos='JWL', r_exp=spec.r_exp,
                solver='blastfoam', material=spec.material,
                case_dir=spec.case_unc)
    return Result(snapshots, _gauges_from_probes(spec), meta,
                  stop_reason, stop_reason == 'stopped by user')


# ── 2D ──────────────────────────────────────────────────────────────────────

def _read_2d(dpath, spec, what=('p',)):
    """Read fields of one time dir onto the native (Nx,Ny) layout."""
    out = {}
    n = spec.n_cells
    if 'p' in what:
        out['p'] = reader.to_grid(
            reader.read_scalar(os.path.join(dpath, 'p'), n), spec)
    if 'rho' in what:
        out['rho'] = reader.to_grid(
            reader.read_scalar(os.path.join(dpath, 'rho'), n), spec)
    if 'U' in what:
        flat = reader.read_vector(os.path.join(dpath, 'U'), n)
        out['u'] = reader.to_grid(flat[:, 0], spec)
        out['v'] = reader.to_grid(flat[:, 1], spec)
    return out


def _log_banner_2d(hooks, case, spec, n_gauges, has_open):
    m = MATERIALS[spec.material]
    bar = '=' * 60
    bc_lbl = ", ".join(f"{k}={v}" for k, v in case.bcs.items())
    x0, y0, _ = spec.center
    axisym = case.geometry == 'axisymmetric'
    charge_lbl = (f'{case.charge:g} kg {spec.material} (sphere) on axis '
                  f'at height {y0:g} m' if axisym else
                  f'{case.charge:g} kg {spec.material} per metre '
                  f'(infinite cylinder) at ({x0:g}, {y0:g}) m')
    for line in (
            '', bar, f'  2D Blast - blastFoam (WSL) ({case.geometry})',
            bar,
            f'  Charge          : {charge_lbl}',
            f'  Explosive radius: {spec.r_exp:.4f} m',
            f'  Domain          : {case.Lx:g} x {case.Ly:g} m,  cell '
            f'{spec.dx:g} m  ({spec.nx} x {spec.ny} = '
            f'{spec.n_cells:,} cells)',
            '  EOS             : JWL products + ideal-gas air '
            f'(vDet {m.vDet:g} m/s)',
            f'  Boundaries      : {bc_lbl}'
            + ('  (x_lo = symmetry axis)' if axisym else ''),
            f'  Gauges          : {n_gauges}',
            '  Stop condition  : '
            + ('shock arrival at an open boundary' if has_open
               else 'safety cap (no open boundaries)'),
            f'  Safety cap      : {spec.end_time*1e3:.1f} ms',
            f'  Write interval  : {spec.write_interval*1e3:.4f} ms',
            bar, ''):
        hooks.log(line)


def solve_2d_foam(case, hooks=None):
    """Run a Case2D on blastFoam (axisymmetric wedge or planar slab).
    Returns a Result shaped exactly like the native solve_2d."""
    hooks = hooks or RunHooks()
    spec = _preflight(case, hooks)
    m = MATERIALS[spec.material]
    g = spec.grid
    x_c, y_c = g['x_c'], g['y_c']
    Nx, Ny = spec.nx, spec.ny
    x0, y0, _ = spec.center
    bcs = dict(case.bcs)
    axisym = case.geometry == 'axisymmetric'
    solid = np.zeros((Nx, Ny), dtype=bool)      # no obstacles in v1

    # open-boundary edge mask + distances (native logic, solver2d:236)
    open_edge = np.zeros((Nx, Ny), dtype=bool)
    sides = (('x_hi', np.s_[-1, :]), ('y_lo', np.s_[:, 0]),
             ('y_hi', np.s_[:, -1]))
    if not axisym:
        sides += (('x_lo', np.s_[0, :]),)
    for side, sl in sides:
        if bcs[side] == 'open':
            open_edge[sl] = True
    has_open = open_edge.any()
    d_charge = np.sqrt((x_c[:, None] - x0) ** 2
                       + (y_c[None, :] - y0) ** 2)
    dists = []
    if bcs['x_hi'] == 'open':
        dists.append(case.Lx - x0)
    if bcs['x_lo'] == 'open' and not axisym:
        dists.append(x0)
    if bcs['y_lo'] == 'open':
        dists.append(y0)
    if bcs['y_hi'] == 'open':
        dists.append(case.Ly - y0)
    if not dists:
        corners = [(0.0, 0.0), (case.Lx, 0.0), (0.0, case.Ly),
                   (case.Lx, case.Ly)]
        dists.append(max(float(np.hypot(cx - x0, cy - y0))
                         for cx, cy in corners))
    stop_dist = min(dists)
    snap_radii = list(np.linspace(spec.r_exp, min(dists),
                                  case.n_snapshots + 1)[1:-1])

    _log_banner_2d(hooks, case, spec, len(spec.probe_pts), has_open)
    hooks.run_started(dict(
        dim=2, x_face=g['x_face'], y_face=g['y_face'], solid=solid,
        xlabel='r [m]' if axisym else 'x [m]',
        ylabel='z [m]' if axisym else 'y [m]', title=''))

    record_frames = case.record_frames
    frame_t, frame_p = [], []
    fields = ('p', 'rho', 'U', f'alpha.{spec.phase}')
    ingested = {}               # dirname -> t (full arrays NOT retained)
    snap_names = []
    st = dict(step=0, t=0.0, dt=0.0, p_max=float(P_AIR), frac=0.0)
    stop_reason = 'safety cap'
    stop_deadline = None
    last_draw = 0.0

    run = runner.FoamRun(spec.case_posix, spec.case_unc)

    def request_stop(reason):
        nonlocal stop_reason, stop_deadline
        stop_reason = reason
        run.request_write_now()
        stop_deadline = _time.time() + _STOP_GRACE_S

    def ingest_ready():
        nonlocal last_draw, frame_t, frame_p
        for _t_disp, name in reader.list_times(spec.case_unc):
            if name in ingested:
                continue
            dpath = os.path.join(spec.case_unc, name)
            if not reader.time_ready(dpath, fields):
                continue
            try:
                t, _dt = reader.read_time(dpath)
                p = _read_2d(dpath, spec)['p']
            except (ValueError, OSError):
                continue            # mid-write; retry next poll
            ingested[name] = t

            shocked = p > _ARRIVAL_P
            r_front = float(d_charge[shocked].max()) if shocked.any() \
                else 0.0
            st['frac'] = min(1.0, r_front / stop_dist)
            while snap_radii and r_front >= snap_radii[0]:
                snap_radii.pop(0)
                if name not in snap_names:
                    snap_names.append(name)
                    hooks.log(f"  Snapshot saved: t = {t*1e3:.3f} ms  "
                              f"(front at {r_front:.2f} m)")
            if record_frames > 0:
                frame_t.append(t)
                frame_p.append(p.astype(np.float32))
                if len(frame_p) >= 2 * record_frames:
                    frame_t = frame_t[::2]
                    frame_p = frame_p[::2]
            will_pause = hooks.exec_will_pause()
            if hooks.draw_due(st['step'], last_draw) or will_pause:
                hooks.frame(p, t)
                last_draw = _time.time()
            if not run.stop_requested and has_open \
                    and (p[open_edge] > _ARRIVAL_P).any():
                request_stop('shock arrived at an open boundary '
                             f'(p_edge = {p[open_edge].max():.3e} Pa)')
            _note_pause(hooks, st, will_pause)
            _gated_step(run, hooks)

    try:
        while True:
            for line in run.drain(_POLL_S):
                _progress_line(line, st, hooks, spec.end_time)
            ingest_ready()
            if hooks.should_stop() and not run.stop_requested:
                request_stop('stopped by user')
            if stop_deadline and run.running \
                    and _time.time() > stop_deadline:
                hooks.log('  [blastfoam] solver did not stop cleanly '
                          '- killing it')
                run.kill()
            if not run.running:
                for line in run.drain(0.05):
                    _progress_line(line, st, hooks, spec.end_time)
                ingest_ready()
                break
    finally:
        if run.running:
            run.kill()

    if run.returncode not in (0, None) and not run.stop_requested:
        raise RuntimeError(
            f"blastFoam failed (exit {run.returncode}) - case kept at "
            f"{spec.case_unc}\n{run.tail()}")
    if not ingested:
        raise RuntimeError(
            "blastFoam produced no readable time steps - case kept at "
            f"{spec.case_unc}\n{run.tail()}")

    # ── finalize: two-pass snapshot re-read ─────────────────────────────
    names = sorted(ingested, key=ingested.get)
    fin_name = names[-1]
    snapshots = {}
    for name in snap_names:
        if name == fin_name:
            continue
        got = _read_2d(os.path.join(spec.case_unc, name), spec,
                       ('p', 'rho', 'U'))
        t = ingested[name]
        label = f"t = {t*1e3:.3f} ms"
        if label not in snapshots:
            snapshots[label] = dict(
                p=got['p'], rho=got['rho'],
                speed=np.sqrt(got['u'] ** 2 + got['v'] ** 2))
    dfin = os.path.join(spec.case_unc, fin_name)
    fin = _read_2d(dfin, spec, ('p', 'rho', 'U'))
    t_fin = ingested[fin_name]
    snapshots[f"t = {t_fin*1e3:.3f} ms (final)"] = dict(
        p=fin['p'], rho=fin['rho'],
        speed=np.sqrt(fin['u'] ** 2 + fin['v'] ** 2))

    if record_frames > 0 and (not frame_t or frame_t[-1] < t_fin):
        frame_t.append(t_fin)
        frame_p.append(fin['p'].astype(np.float32))
    hooks.frame(fin['p'], t_fin)

    # final_state for save_profile_2d -> 3D remap: e from T (per-phase
    # Cv - blastFoam writes no e field), phase from the products alpha
    alpha = reader.to_grid(reader.read_scalar(
        os.path.join(dfin, f'alpha.{spec.phase}'), spec.n_cells), spec)
    phase = (alpha > 0.5).astype(int)
    T = reader.to_grid(reader.read_scalar(
        os.path.join(dfin, 'T'), spec.n_cells), spec)
    e_arr = np.where(phase == 1, m.Cv_products, writer.CV_AIR) * T

    hooks.log(f"\n  Done. {st['step']} solver steps, t_final = "
              f"{t_fin*1e3:.3f} ms")
    hooks.log(f"  Stopped: {stop_reason}\n")

    probes = reader.read_probes(spec.case_unc) if spec.probe_pts else None
    if probes:
        gauge_out = dict(times=probes['times'],
                         points=[(pt[0], pt[1])
                                 for pt in probes['points']],
                         pressures=probes['pressures'])
    else:
        gauge_out = dict(times=np.array([]), points=[], pressures=[])

    meta = dict(x_c=x_c, y_c=y_c,
                x_face=g['x_face'], y_face=g['y_face'],
                solid=solid, geometry=case.geometry,
                Lx=case.Lx, Ly=case.Ly, dx=spec.dx,
                eos='JWL', bcs=bcs, obstacles=[],
                charge=case.charge, charge_center=(x0, y0),
                r_exp=spec.r_exp, from_profile=False,
                solver='blastfoam', material=spec.material,
                case_dir=spec.case_unc)
    meta['final_state'] = dict(t=t_fin, rho=fin['rho'], u=fin['u'],
                               v=fin['v'], e=e_arr, p=fin['p'],
                               phase=phase)
    if record_frames > 0:
        meta['frames'] = dict(times=np.array(frame_t), pressures=frame_p)
    return Result(snapshots, gauge_out, meta, stop_reason,
                  stop_reason == 'stopped by user')


# ── 3D ──────────────────────────────────────────────────────────────────────

def _snapshot_payload(p, rho, U, j0, k0, t):
    """Native _snapshot (solver3d.py:49) rebuilt from foam arrays."""
    from ...viz3d.sampling import choose_stride, decimate
    speed = np.sqrt((U * U).sum(axis=-1))
    return dict(p=p.astype(np.float32),
                rho_xz=rho[:, j0, :].astype(np.float32),
                rho_xy=rho[:, :, k0].astype(np.float32),
                speed_xz=speed[:, j0, :].astype(np.float32),
                speed_xy=speed[:, :, k0].astype(np.float32),
                t=float(t),
                rho3=decimate(rho, choose_stride(rho.shape)))


def _read_3d(dpath, spec, what=('p',)):
    """Read fields of one time dir onto the native (Nx,Ny,Nz) layout."""
    out = {}
    n = spec.n_cells
    if 'p' in what:
        out['p'] = reader.to_grid(
            reader.read_scalar(os.path.join(dpath, 'p'), n), spec)
    if 'rho' in what:
        out['rho'] = reader.to_grid(
            reader.read_scalar(os.path.join(dpath, 'rho'), n), spec)
    if 'U' in what:
        flat = reader.read_vector(os.path.join(dpath, 'U'), n)
        out['U'] = np.stack([reader.to_grid(flat[:, i], spec)
                             for i in range(3)], axis=-1)
    return out


def _log_banner_3d(hooks, case, spec, n_gauges, has_open):
    m = MATERIALS[spec.material]
    bar = '=' * 62
    bc_lbl = ", ".join(f"{k}={v}" for k, v in case.bcs.items())
    x0, y0, z0 = spec.center
    for line in (
            '', bar, '  3D Blast - blastFoam (WSL)', bar,
            f'  Charge          : {case.charge:g} kg {spec.material} '
            f'(sphere)',
            f'  Burst point     : ({x0:g}, {y0:g}, {z0:g}) m',
            f'  Explosive radius: {spec.r_exp:.4f} m',
            f'  Domain          : {case.Lx:g} x {case.Ly:g} x '
            f'{case.Lz:g} m,  cell {spec.dx:g} m',
            f'  Grid            : {spec.nx} x {spec.ny} x {spec.nz} = '
            f'{spec.n_cells:,} cells',
            '  EOS             : JWL products + ideal-gas air '
            f'(vDet {m.vDet:g} m/s)',
            f'  Boundaries      : {bc_lbl}',
            f'  Gauges          : {n_gauges}',
            '  Stop condition  : '
            + ('shock arrival at an open boundary' if has_open
               else 'safety cap (no open boundaries)'),
            f'  {"End time" if spec.cap_is_end else "Safety cap":<16}: '
            f'{spec.end_time*1e3:.1f} ms',
            f'  Write interval  : {spec.write_interval*1e3:.4f} ms',
            bar, ''):
        hooks.log(line)


def solve_3d_foam(case, hooks=None):
    """Run a Case3D on blastFoam. Returns a Result shaped exactly like
    the native solve_3d (incl. viewer snapshots and frames)."""
    hooks = hooks or RunHooks()
    spec = _preflight(case, hooks)
    g = spec.grid
    x_c, y_c, z_c = g['x_c'], g['y_c'], g['z_c']
    Nx, Ny, Nz = spec.nx, spec.ny, spec.nz
    dx = spec.dx
    x0, y0, z0 = spec.center
    bcs = dict(case.bcs)
    solid = np.zeros((Nx, Ny, Nz), dtype=bool)   # no obstacles in v1

    n_snapshots = case.n_snapshots
    max_snaps = max(1, int(1.5e9 / (4 * spec.n_cells)) - 1)
    if n_snapshots > max_snaps:
        hooks.log(f"  [note] n_snapshots reduced {n_snapshots} -> "
                  f"{max_snaps} to bound snapshot memory")
        n_snapshots = max_snaps

    # open-boundary edge mask + stop/snapshot distances (native logic)
    open_edge = np.zeros((Nx, Ny, Nz), dtype=bool)
    for side, sl in (('x_lo', np.s_[0, :, :]), ('x_hi', np.s_[-1, :, :]),
                     ('y_lo', np.s_[:, 0, :]), ('y_hi', np.s_[:, -1, :]),
                     ('z_lo', np.s_[:, :, 0]), ('z_hi', np.s_[:, :, -1])):
        if bcs[side] == 'open':
            open_edge[sl] = True
    has_open = open_edge.any()
    d_charge = np.sqrt((x_c[:, None, None] - x0) ** 2
                       + (y_c[None, :, None] - y0) ** 2
                       + (z_c[None, None, :] - z0) ** 2).astype(np.float32)
    dists = [d for d, side in ((x0, 'x_lo'), (case.Lx - x0, 'x_hi'),
                               (y0, 'y_lo'), (case.Ly - y0, 'y_hi'),
                               (z0, 'z_lo'), (case.Lz - z0, 'z_hi'))
             if bcs[side] == 'open']
    if not dists:
        dists = [float(np.hypot(np.hypot(cx - x0, cy - y0), cz - z0))
                 for cx in (0, case.Lx) for cy in (0, case.Ly)
                 for cz in (0, case.Lz)]
        dists = [max(dists)]
    stop_dist = min(dists)
    snap_radii = list(np.linspace(spec.r_exp, min(dists),
                                  n_snapshots + 1)[1:-1])

    # burst-plane slice indices + user live slice (native conventions)
    j0 = int(np.argmin(np.abs(y_c - y0)))
    k0 = int(np.argmin(np.abs(z_c - z0)))
    slice_axis = getattr(case, 'slice_axis', 'y') or 'y'
    ax_i = 'xyz'.index(slice_axis)
    _coords = (x_c, y_c, z_c)
    _pos = ((x0, y0, z0)[ax_i] if getattr(case, 'slice_pos', None) is None
            else float(case.slice_pos))
    s0 = int(np.argmin(np.abs(_coords[ax_i] - _pos)))
    live_sl = tuple(s0 if a == ax_i else slice(None) for a in range(3))
    live_faces = {'x': (g['y_face'], g['z_face']),
                  'y': (g['x_face'], g['z_face']),
                  'z': (g['x_face'], g['y_face'])}[slice_axis]
    live_labels = {'x': ('y [m]', 'z [m]'), 'y': ('x [m]', 'z [m]'),
                   'z': ('x [m]', 'y [m]')}[slice_axis]
    live_title = f'{slice_axis} = {_coords[ax_i][s0]:.2f} m'

    _log_banner_3d(hooks, case, spec, len(spec.probe_pts), has_open)
    hooks.run_started(dict(
        dim=3, x_face=live_faces[0], y_face=live_faces[1],
        solid=solid[live_sl], xlabel=live_labels[0],
        ylabel=live_labels[1], title=live_title,
        scene3d=dict(x_c=x_c, y_c=y_c, z_c=z_c, dx=dx, solid=solid,
                     obstacles=[], Lx=case.Lx, Ly=case.Ly, Lz=case.Lz,
                     charge_center=(x0, y0, z0), r_exp=spec.r_exp,
                     bcs=bcs)))

    record_frames = case.record_frames
    frame_t, frame_p = [], []
    fields = ('p', 'rho', 'U', f'alpha.{spec.phase}')
    ingested = {}               # dirname -> t (full arrays NOT retained)
    snap_names = []             # dirs picked by front-radius crossings
    p_peak = None
    impulse = None
    t_prev = 0.0
    st = dict(step=0, t=0.0, dt=0.0, p_max=float(P_AIR), frac=0.0)
    stop_reason = 'safety cap'
    stop_deadline = None
    last_draw = 0.0
    last_draw3d = 0.0

    run = runner.FoamRun(spec.case_posix, spec.case_unc)

    def request_stop(reason):
        nonlocal stop_reason, stop_deadline
        stop_reason = reason
        run.request_write_now()
        stop_deadline = _time.time() + _STOP_GRACE_S

    def ingest_ready():
        nonlocal p_peak, impulse, t_prev, last_draw, last_draw3d
        nonlocal frame_t, frame_p
        for _t_disp, name in reader.list_times(spec.case_unc):
            if name in ingested:
                continue
            dpath = os.path.join(spec.case_unc, name)
            if not reader.time_ready(dpath, fields):
                continue
            will_3d = (hooks.draw3d_due(st['step'], last_draw3d)
                       or hooks.exec_will_pause()) and hooks.wants_frame3d()
            try:
                t, _dt = reader.read_time(dpath)
                got = _read_3d(dpath, spec,
                               ('p', 'rho') if will_3d else ('p',))
            except (ValueError, OSError):
                continue            # mid-write; retry next poll
            ingested[name] = t
            p = got['p']
            if p_peak is None:
                p_peak = p.copy()
                impulse = np.zeros_like(p)
            else:
                np.maximum(p_peak, p, out=p_peak)
            impulse += (p - P_AIR) * (t - t_prev)
            t_prev = t

            # shock-front progress + native snapshot scheduling
            shocked = p > _ARRIVAL_P
            r_front = float(d_charge[shocked].max()) if shocked.any() \
                else 0.0
            st['frac'] = min(1.0, r_front / stop_dist)
            while snap_radii and r_front >= snap_radii[0]:
                snap_radii.pop(0)
                if name not in snap_names:
                    snap_names.append(name)
                    hooks.log(f"  Snapshot saved: t = {t*1e3:.3f} ms  "
                              f"(front at {r_front:.2f} m)")

            if record_frames > 0:
                frame_t.append(t)
                frame_p.append(p[live_sl].astype(np.float32))
                if len(frame_p) >= 2 * record_frames:
                    frame_t = frame_t[::2]
                    frame_p = frame_p[::2]
            will_pause = hooks.exec_will_pause()
            if hooks.draw_due(st['step'], last_draw) or will_pause:
                hooks.frame(p[live_sl].copy(), t)
                last_draw = _time.time()
            if will_3d:
                rho = got['rho']
                e_approx = p / (0.4 * np.maximum(rho, 1e-10))
                hooks.frame3d(t, dict(p=p, rho=rho, e=e_approx,
                                      p_peak=p_peak, imp=impulse))
                last_draw3d = _time.time()
            if not run.stop_requested and has_open \
                    and (p[open_edge] > _ARRIVAL_P).any():
                request_stop('shock arrived at an open boundary '
                             f'(p_edge = {p[open_edge].max():.3e} Pa)')
            _note_pause(hooks, st, will_pause)
            _gated_step(run, hooks)

    try:
        while True:
            for line in run.drain(_POLL_S):
                _progress_line(line, st, hooks, spec.end_time)
            ingest_ready()
            if hooks.should_stop() and not run.stop_requested:
                request_stop('stopped by user')
            if stop_deadline and run.running \
                    and _time.time() > stop_deadline:
                hooks.log('  [blastfoam] solver did not stop cleanly '
                          '- killing it')
                run.kill()
            if not run.running:
                for line in run.drain(0.05):
                    _progress_line(line, st, hooks, spec.end_time)
                ingest_ready()
                break
    finally:
        if run.running:
            run.kill()

    if run.returncode not in (0, None) and not run.stop_requested:
        raise RuntimeError(
            f"blastFoam failed (exit {run.returncode}) - case kept at "
            f"{spec.case_unc}\n{run.tail()}")
    if not ingested:
        raise RuntimeError(
            "blastFoam produced no readable time steps - case kept at "
            f"{spec.case_unc}\n{run.tail()}")
    if stop_reason == 'safety cap' and spec.cap_is_end:
        stop_reason = 'end time reached'

    # ── finalize: two-pass snapshot re-read (bounds run-time memory) ────
    names = sorted(ingested, key=ingested.get)
    fin_name = names[-1]
    snapshots = {}
    for name in snap_names:
        if name == fin_name:
            continue
        dpath = os.path.join(spec.case_unc, name)
        got = _read_3d(dpath, spec, ('p', 'rho', 'U'))
        t = ingested[name]
        label = f"t = {t*1e3:.3f} ms"
        if label not in snapshots:
            snapshots[label] = _snapshot_payload(
                got['p'], got['rho'], got['U'], j0, k0, t)
    fin = _read_3d(os.path.join(spec.case_unc, fin_name), spec,
                   ('p', 'rho', 'U'))
    t_fin = ingested[fin_name]
    snapshots[f"t = {t_fin*1e3:.3f} ms (final)"] = _snapshot_payload(
        fin['p'], fin['rho'], fin['U'], j0, k0, t_fin)

    if p_peak is None:
        p_peak = fin['p'].copy()
        impulse = np.zeros_like(p_peak)
    np.maximum(p_peak, fin['p'], out=p_peak)
    if record_frames > 0 and (not frame_t or frame_t[-1] < t_fin):
        frame_t.append(t_fin)
        frame_p.append(fin['p'][live_sl].astype(np.float32))
    hooks.frame(fin['p'][live_sl].copy(), t_fin)
    e_approx = fin['p'] / (0.4 * np.maximum(fin['rho'], 1e-10))
    hooks.frame3d(t_fin, dict(p=fin['p'], rho=fin['rho'], e=e_approx,
                              p_peak=p_peak, imp=impulse), force=True)

    hooks.log(f"\n  Done. {st['step']} solver steps, t_final = "
              f"{t_fin*1e3:.3f} ms")
    hooks.log(f"  Stopped: {stop_reason}\n")

    probes = reader.read_probes(spec.case_unc) if spec.probe_pts else None
    if probes:
        gauge_out = dict(times=probes['times'],
                         points=[tuple(pt) for pt in probes['points']],
                         pressures=probes['pressures'])
    else:
        gauge_out = dict(times=np.array([]), points=[], pressures=[])

    meta = dict(x_c=x_c, y_c=y_c, z_c=z_c,
                x_face=g['x_face'], y_face=g['y_face'],
                z_face=g['z_face'], j0=j0, k0=k0,
                slice_axis=slice_axis, s0=s0,
                solid=solid, Lx=case.Lx, Ly=case.Ly, Lz=case.Lz, dx=dx,
                eos='JWL', bcs=bcs, obstacles=[],
                charge=case.charge, charge_center=(x0, y0, z0),
                r_exp=spec.r_exp, r_src=spec.r_exp, from_profile=None,
                solver='blastfoam', material=spec.material,
                case_dir=spec.case_unc)
    if record_frames > 0:
        meta['frames'] = dict(times=np.array(frame_t), pressures=frame_p)
    return Result(snapshots, gauge_out, meta, stop_reason,
                  stop_reason == 'stopped by user')
