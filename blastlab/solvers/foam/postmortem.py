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
from ..hooks import RunHooks
from . import env, reader, writer
from .backend import (_ARRIVAL_P, _PeakImpulse, _d_charge_3d,
                      _finalize_1d, _finalize_2d, _finalize_3d,
                      _maybe_reconstruct, _stop_dists_3d,
                      _read_2d, _read_3d)


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
        dists = _stop_dists_3d(case, spec)
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
    if case.dim in (1, 2):              # _finalize_1d/2d re-read T
        fields += ('T',)
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

    # sanity: the re-planned grid must match what is on disk. A run
    # killed mid-write can leave a torn newest dir, so walk back until
    # one dir reads - a real grid mismatch fails on every one of them.
    for _t, name in reversed(times):
        try:
            reader.read_scalar(os.path.join(unc, name, 'p'),
                               spec.n_cells)
            break
        except (ValueError, OSError):
            continue
    else:
        raise RuntimeError(
            f'no readable time directory in {unc} - the grid does not '
            f'match case.json, or every write is truncated')

    def _skip(name, exc):
        hooks.log(f'  [postmortem] time dir {name} unreadable '
                  f'({exc}) - skipped')

    if case.dim == 1:
        store = {}
        for _t, name in times:
            dpath = os.path.join(unc, name)
            try:
                t, _dt = reader.read_time(dpath)
                entry = dict(
                    t=t,
                    p=reader.read_scalar(os.path.join(dpath, 'p'),
                                         spec.n_cells),
                    rho=reader.read_scalar(os.path.join(dpath, 'rho'),
                                           spec.n_cells),
                    u=reader.read_vector(os.path.join(dpath, 'U'),
                                         spec.n_cells)[:, 0])
            except (ValueError, OSError) as exc:
                _skip(name, exc)
                continue
            store[name] = entry
        if not store:
            raise RuntimeError(f'no readable time directory in {unc}')
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
    acc = _PeakImpulse()
    for _t, name in times:
        dpath = os.path.join(unc, name)
        try:
            t, _dt = reader.read_time(dpath)
            p = (_read_2d(dpath, spec)['p'] if case.dim == 2
                 else _read_3d(dpath, spec)['p'])
        except (ValueError, OSError) as exc:
            _skip(name, exc)
            continue
        if not acc.add(p, t, dpath, spec, hooks):
            continue
        ingested[name] = t
        shocked = p > _ARRIVAL_P
        r_front = float(d_charge[shocked].max()) if shocked.any() else 0.0
        while snap_radii and r_front >= snap_radii[0]:
            snap_radii.pop(0)
            if name not in snap_names:
                snap_names.append(name)

    if not ingested:
        raise RuntimeError(f'no readable time directory in {unc}')
    if case.dim == 2:
        return _finalize_2d(case, spec, hooks, stop_reason, 0,
                            ingested, snap_names, [], [], 0, acc)
    return _finalize_3d(case, spec, hooks, stop_reason, 0,
                        ingested, snap_names, [], [], 0, acc)


def list_runs(check_alive=False):
    """[(name, unc, alive)] of run directories under env.RUNS_ROOT,
    newest first (missing root -> empty).

    `alive` is True/False when `check_alive` asks WSL whether each run's
    recorded solver pid is still running (one round trip for the whole
    list, via env.runs_alive), and None when the question was not asked
    or WSL did not answer - so a caller can never mistake "not checked"
    for "not running"."""
    root = env.unc(env.RUNS_ROOT)
    try:
        names = sorted(os.listdir(root), reverse=True)
    except OSError:
        return []
    names = [n for n in names if os.path.isdir(os.path.join(root, n))]
    alive = (env.runs_alive([f'{env.RUNS_ROOT}/{n}' for n in names])
             if check_alive and names else {})
    return [(n, os.path.join(root, n),
             alive.get(f'{env.RUNS_ROOT}/{n}')) for n in names]
