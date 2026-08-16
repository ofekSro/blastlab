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
IMPLEMENTED = frozenset({1})

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
    """Parse one solver stdout line into Progress state."""
    m = _RE_TIME.match(line)
    if m:
        st['t'] = float(m.group(1))
        st['step'] += 1
        hooks.progress(Progress(step=st['step'], t=st['t'], dt=st['dt'],
                                p_max=st['p_max'],
                                frac=min(1.0, st['t'] / end_time)))
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
            if hooks.draw_due(st['step'], last_draw) \
                    or hooks.exec_will_pause():
                hooks.frame(np.array([r, entry['p']]), entry['t'])
                last_draw = _time.time()
            if not run.stop_requested and entry['p'][-1] > _ARRIVAL_P:
                request_stop('shock arrived at outer boundary '
                             f"(p_last = {entry['p'][-1]:.3e} Pa)")
            hooks.step_gate()

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


def solve_2d_foam(case, hooks=None):
    _todo(2)


def solve_3d_foam(case, hooks=None):
    _todo(3)
