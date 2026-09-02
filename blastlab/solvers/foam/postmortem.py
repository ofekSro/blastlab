"""Load a finished blastFoam case directory into a Result without
re-running (`meta['case_dir']` runs are kept on the WSL disk exactly
for this).

`load_run` replays the backend's ingest headlessly: the saved case.json
rebuilds the CaseSpec through the same planner the run used, snapshot
picks re-apply the native radius-crossing rule from each written
frame's shock front, and the shared `_finalize_*` helpers assemble the
exact live-run Result shapes. Parallel leftovers (`processor*/`) get a
final reconstruct sweep first.
"""

import os

import numpy as np

from ...core.case import load_case
from ...core.constants import P_AIR
from ..hooks import RunHooks
from . import env, reader, writer
from .backend import (_ARRIVAL_P, _d_charge_3d, _finalize_1d,
                      _finalize_2d, _finalize_3d, _maybe_reconstruct,
                      _read_2d, _read_3d, _read_fo_fields)


def _paths(case_dir):
    """(posix, unc) for a case dir given either form, or a bare run
    name under env.RUNS_ROOT."""
    d = str(case_dir).rstrip('/\\')
    if d.startswith('\\\\'):
        tail = d.split('\\' + env.WSL_DISTRO + '\\', 1)
        if len(tail) != 2:
            raise ValueError(f'not a WSL UNC path: {case_dir}')
        posix = '/' + tail[1].replace('\\', '/')
    elif d.startswith('/'):
        posix = d
    else:
        posix = f'{env.RUNS_ROOT}/{d}'
    return posix, env.unc(posix)


def _n_procs_on_disk(case_unc):
    n = 0
    while os.path.isdir(os.path.join(case_unc, f'processor{n}')):
        n += 1
    return max(1, n)


def _snap_radii(case, spec):
    """The native snapshot trigger radii (mirror of the run loops)."""
    x0, y0, z0 = spec.center
    if case.dim == 2:
        axisym = case.geometry == 'axisymmetric'
        dists = []
        if case.bcs['x_hi'] == 'open':
            dists.append(case.Lx - x0)
        if case.bcs['x_lo'] == 'open' and not axisym:
            dists.append(x0)
        if case.bcs['y_lo'] == 'open':
            dists.append(y0)
        if case.bcs['y_hi'] == 'open':
            dists.append(case.Ly - y0)
        if not dists:
            corners = [(0.0, 0.0), (case.Lx, 0.0), (0.0, case.Ly),
                       (case.Lx, case.Ly)]
            dists.append(max(float(np.hypot(cx - x0, cy - y0))
                             for cx, cy in corners))
        n_snapshots = case.n_snapshots
    else:
        dists = [d for d, side in ((x0, 'x_lo'), (case.Lx - x0, 'x_hi'),
                                   (y0, 'y_lo'), (case.Ly - y0, 'y_hi'),
                                   (z0, 'z_lo'), (case.Lz - z0, 'z_hi'))
                 if case.bcs[side] == 'open']
        if not dists:
            dists = [max(float(np.hypot(np.hypot(cx - x0, cy - y0),
                                        cz - z0))
                         for cx in (0, case.Lx) for cy in (0, case.Ly)
                         for cz in (0, case.Lz))]
        n_snapshots = min(case.n_snapshots,
                          max(1, int(1.5e9 / (4 * spec.n_cells)) - 1))
    return list(np.linspace(spec.r_exp, min(dists),
                            n_snapshots + 1)[1:-1])


def load_run(case_dir, hooks=None):
    """Rebuild a Result from a finished blastFoam case directory.

    `case_dir` may be a UNC path, a WSL posix path, or a bare run-dir
    name under /root/blastlab_runs. Requires the case.json the writer
    saves alongside the case (runs from before that feature cannot be
    loaded). Returns a Result shaped exactly like the live run's."""
    hooks = hooks or RunHooks()
    posix, unc = _paths(case_dir)
    cj = os.path.join(unc, 'case.json')
    if not os.path.isfile(cj):
        raise FileNotFoundError(
            f'no case.json in {unc} - this run predates post-mortem '
            f'support (re-run it once with the current blastlab)')
    case = load_case(cj)

    n_procs = _n_procs_on_disk(unc)
    spec = writer.render_case(case, n_procs=n_procs)
    spec.case_posix, spec.case_unc = posix, unc
    spec.files = None                   # nothing is written

    fields = ('p', 'rho', 'U', f'alpha.{spec.phase}')
    if n_procs > 1:
        hooks.log(f'  [postmortem] reconstructing leftover parallel '
                  f'times ({n_procs} ranks)...')
        _maybe_reconstruct(spec, fields, done=True)

    times = [(t, name) for t, name in reader.list_times(unc)
             if reader.time_ready(os.path.join(unc, name), fields)]
    if not times:
        raise RuntimeError(f'no complete time directories in {unc}')
    n_frames = len(times)
    hooks.log(f'  [postmortem] {unc}: {n_frames} written frames')
    stop_reason = f'loaded post-mortem ({n_frames} frames)'

    # sanity: the re-planned grid must match what is on disk
    probe = os.path.join(unc, times[-1][1], 'p')
    reader.read_scalar(probe, spec.n_cells)     # raises on mismatch

    if case.dim == 1:
        store = {}
        for _t, name in times:
            dpath = os.path.join(unc, name)
            t, _dt = reader.read_time(dpath)
            store[name] = dict(
                t=t,
                p=reader.read_scalar(os.path.join(dpath, 'p'),
                                     spec.n_cells),
                rho=reader.read_scalar(os.path.join(dpath, 'rho'),
                                       spec.n_cells),
                u=reader.read_vector(os.path.join(dpath, 'U'),
                                     spec.n_cells)[:, 0])
        return _finalize_1d(case, spec, store, hooks, stop_reason, 0)

    # 2D / 3D: replay the ingest - per-frame shock front drives the
    # native radius-crossing snapshot picks
    g = spec.grid
    x0, y0, z0 = spec.center
    if case.dim == 2:
        d_charge = np.sqrt((g['x_c'][:, None] - x0) ** 2
                           + (g['y_c'][None, :] - y0) ** 2)
    else:
        d_charge = _d_charge_3d(spec)
    snap_radii = _snap_radii(case, spec)
    ingested, snap_names = {}, []
    p_peak = impulse = None
    fo_peak = fo_imp = None
    t_prev = 0.0
    for _t, name in times:
        dpath = os.path.join(unc, name)
        t, _dt = reader.read_time(dpath)
        p = (_read_2d(dpath, spec)['p'] if case.dim == 2
             else _read_3d(dpath, spec)['p'])
        ingested[name] = t
        if case.dim == 3:
            if p_peak is None:
                p_peak = p.copy()
                impulse = np.zeros_like(p)
            else:
                np.maximum(p_peak, p, out=p_peak)
            impulse += (p - P_AIR) * (t - t_prev)
            t_prev = t
            got_peak, got_imp = _read_fo_fields(dpath, spec)
            if got_peak is not None:
                fo_peak, fo_imp = got_peak, got_imp
        shocked = p > _ARRIVAL_P
        r_front = float(d_charge[shocked].max()) if shocked.any() else 0.0
        while snap_radii and r_front >= snap_radii[0]:
            snap_radii.pop(0)
            if name not in snap_names:
                snap_names.append(name)

    if case.dim == 2:
        return _finalize_2d(case, spec, hooks, stop_reason, 0,
                            ingested, snap_names, [], [], 0)
    return _finalize_3d(case, spec, hooks, stop_reason, 0,
                        ingested, snap_names, [], [], 0,
                        p_peak, impulse, fo_peak, fo_imp)


def list_runs():
    """[(name, unc)] of run directories under env.RUNS_ROOT, newest
    first (missing root -> empty)."""
    root = env.unc(env.RUNS_ROOT)
    try:
        names = sorted(os.listdir(root), reverse=True)
    except OSError:
        return []
    return [(n, os.path.join(root, n)) for n in names
            if os.path.isdir(os.path.join(root, n))]
