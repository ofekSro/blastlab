"""Load a finished blastFoam case directory into a Result without
re-running (`meta['case_dir']` runs are kept on the WSL disk exactly
for this).

`load_run` replays the backend's ingest headlessly: the saved case.json
rebuilds the CaseSpec through the same planner the run used, snapshot
picks re-apply the native radius-crossing rule from each written
frame's shock front, and the shared `finalize_*` helpers assemble the
exact live-run Result shapes. Parallel leftovers (`processor*/`) get a
final reconstruct sweep first.
"""

import os

import numpy as np

from ...core import geometry
from ...core.case import load_case
from ..hooks import RunHooks
from . import backend, env, reader, writer
from .backend import (build_remap, finalize_1d, finalize_2d, finalize_3d,
                      first_part, mesh_at, read_2d, read_3d,
                      slice_geom_3d)
from .runloop import ARRIVAL_P, PeakImpulse, maybe_reconstruct


def _paths(case_dir):
    """(posix, unc) - see env.case_paths."""
    return env.case_paths(case_dir)


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
        dists = geometry.stop_dists_2d(case.Lx, case.Ly, x0, y0, case.bcs,
                                       x_lo_counts=not axisym)
        n_snapshots = case.n_snapshots
    else:
        dists = geometry.stop_dists_3d(case.Lx, case.Ly, case.Lz,
                                       spec.burst_points, case.bcs)
        n_snapshots = min(case.n_snapshots,
                          max(1, int(1.5e9 / (4 * spec.n_cells)) - 1))
    return geometry.snap_radii(spec.r_exp, dists, n_snapshots)


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
    if spec.lmax or spec.amr:
        # refined mesh: rebuild the fine-grid gather map from the cell
        # centres the run wrote (C is kept in the start-time dir for
        # exactly this - '0', or t0 for a profile stage, T70); AMR runs
        # rebuild the start map the same way and every later time dir
        # carries its own C + cellLevel (mesh_at)
        if not os.path.isfile(os.path.join(unc, spec.start_dir, 'C')):
            raise RuntimeError(
                f'{unc} is a locally refined run without '
                f'{spec.start_dir}/C (cell centres) - re-run it with the '
                f'current blastlab')
        build_remap(spec, hooks)

    fields = ('p', 'rho', 'U', f'alpha.{spec.phase}')
    if case.dim in (1, 2):              # finalize_1d/2d re-read T
        fields += ('T',)
    fields += spec.mesh_fields
    if n_procs > 1 and not spec.decomposed:
        hooks.log(f'  [postmortem] reconstructing leftover parallel '
                  f'times ({n_procs} ranks)...')
        maybe_reconstruct(spec, fields, done=True)
    elif spec.decomposed:
        # parallel AMR (T42/N16-b): nothing to reconstruct - the times
        # are read straight out of processor*/ and concatenated
        hooks.log(f'  [postmortem] reading {n_procs} decomposed ranks '
                  f'directly (AMR)')

    def _ready(name):
        d = spec.time_dirs(name)
        parts = d if isinstance(d, (list, tuple)) else [d]
        return all(reader.time_ready(p, fields) for p in parts)

    times = [(t, name) for t, name in reader.list_times(spec.time_root())
             if _ready(name)]
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
            dp = spec.time_dirs(name)
            mesh = mesh_at(spec, dp)
            backend.rd_scalar(spec, dp, 'p',
                              spec.n_cells if mesh is None
                              else mesh.n_cells)
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
            # 1D is never decomposed (no AMR), so this stays a plain
            # per-time directory
            dpath = spec.time_dirs(name)
            try:
                t, _dt = reader.read_time(first_part(dpath))
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
        return finalize_1d(case, spec, store, hooks, stop_reason, 0)

    # 2D / 3D: replay the ingest - per-frame shock front drives the
    # native radius-crossing snapshot picks
    g = spec.grid
    x0, y0, z0 = spec.center
    if case.dim == 2:
        d_charge = geometry.d_charge_2d(g['x_c'], g['y_c'], x0, y0)
    else:
        d_charge = geometry.d_charge_3d(g['x_c'], g['y_c'], g['z_c'],
                                        spec.burst_points)
    snap_radii = _snap_radii(case, spec)
    ingested, snap_names = {}, []
    acc = PeakImpulse()
    # replay frames: a loaded run used to reach the Animation tab with
    # nothing to play (QA-24). Every written time is a frame, thinned by
    # halving exactly like the live loop, and 3D keeps the same live
    # slice the run would have shown.
    record_frames = int(getattr(case, 'record_frames', 0) or 0) or 150
    live_sl = slice_geom_3d(case, spec)[4] if case.dim == 3 else None
    frame_t, frame_p, frame_lv = [], [], []
    for _t, name in times:
        # spec.time_dirs, NOT unc/name: a parallel AMR run is never
        # reconstructed (the mesh moves under reconstructPar), so its
        # times live in processor*/ and this returns one dir per rank.
        # Building the root path instead made every time dir miss, and
        # the loader then reported "no readable time directory" for a
        # run that had 96 of them (T42 added the decomposed layout and
        # the readiness check and the sanity walk-back below both use
        # time_dirs already - only this loop was left behind).
        dpath = spec.time_dirs(name)
        try:
            t, _dt = reader.read_time(first_part(dpath))
            mesh = mesh_at(spec, dpath)         # None on a static mesh
            p = (read_2d(dpath, spec, mesh=mesh)['p'] if case.dim == 2
                 else read_3d(dpath, spec, mesh=mesh)['p'])
        except (ValueError, OSError) as exc:
            _skip(name, exc)
            continue
        if not acc.add(p, t, dpath, spec, hooks, mesh=mesh):
            continue
        ingested[name] = t
        frame_t.append(t)
        frame_p.append((p if live_sl is None
                        else p[live_sl]).astype(np.float32))
        if mesh is not None:
            frame_lv.append(mesh.levels if live_sl is None
                            else mesh.levels[live_sl])
        if len(frame_p) >= 2 * record_frames:
            frame_t, frame_p = frame_t[::2], frame_p[::2]
            frame_lv = frame_lv[::2]
        shocked = p > ARRIVAL_P
        r_front = float(d_charge[shocked].max()) if shocked.any() else 0.0
        while snap_radii and r_front >= snap_radii[0]:
            snap_radii.pop(0)
            if name not in snap_names:
                snap_names.append(name)

    if not ingested:
        raise RuntimeError(f'no readable time directory in {unc}')
    if case.dim == 2:
        return finalize_2d(case, spec, hooks, stop_reason, 0,
                            ingested, snap_names, frame_t, frame_p,
                            record_frames, acc, frame_lv=frame_lv)
    return finalize_3d(case, spec, hooks, stop_reason, 0,
                        ingested, snap_names, frame_t, frame_p,
                        record_frames, acc, frame_lv=frame_lv)


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
