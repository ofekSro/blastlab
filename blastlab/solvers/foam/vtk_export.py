"""OUT-2: VTK output for ParaView, converted and copied while the run runs.

docs/model-folder-and-vtk-plan.md sec. 3.5 / 3.6 and the batch plan
docs/batches/2026-09-27-out-2-vtk-output.md (D2, D8, D9, D14; owner answers
Q1-Q6). This module holds the pure pieces: which WSL time directories may
be deleted (`vtk_purge_plan`), the paths a delete may touch
(`time_dir_paths`), the foamToVTK command line (`vtk_argv_script`), which
surface-output time directories a sweep takes (`surface_sweep_plan`) and
where each file lands in the model folder (`dest_name`).

`VtkExport` is the executor the run loop drives after every ingest pass
and on the final sweep (Step 6).

The file layout is the owner's Viper-style one (docs/batches/2026-09-27-
out-2-surface-layout.md, decisions 1-6): one file per surface per sample
time holding every chosen field, one folder per series with its
`.vtk.series` beside it, readable array names, `pMax` written as the
peak overpressure, and the sample time inside every file.

No Qt, no services/, no backend import: the run loop owns the executor
and the backend only tells it which writes finalize still reads.
"""

import collections
import os
import posixpath
import re
import shutil
import subprocess
import threading
import time as _time

import numpy as np

from ...core.constants import P_AIR
from ...models.case import (VTK_ARRAY_NAMES, VTK_DECIMATE_WARNING,
                            VTK_FIELDS, vtk_fields_for)
from ...output import legacy_vtk, vtk_series
from .runloop import _CASE_POSIX, _is_time, _root_whole, rm_scripts
from .writer import VTK_OBSTACLES, VTK_SECTIONS

#: the model folder's vtk\ subfolders (plan sec. 3.6)
VOLUMES = 'volumes'
SECTIONS = 'sections'
OBSTACLES = 'obstacles'
KINDS = (VOLUMES, SECTIONS, OBSTACLES)
#: the surface function object -> its vtk\ family
_SURFACE_FAMILIES = ((VTK_SECTIONS, SECTIONS), (VTK_OBSTACLES, OBSTACLES))
#: the `family` of a not_converted entry for the export as a whole (an
#: unexpected error, VtkExport._broken)
EXPORT = 'export'

#: the newest complete writes a purge always keeps: a W3 resume restarts
#: from the newest, and `backend._final_read` falls back to the one before
#: it when the newest is torn
KEEP_NEWEST = 2

#: a surface or field name as it may appear in a path: the writer's plane
#: names (`slice_y_1.40`), `obstacles` and the VTK field names
#: (`alpha.expl`); never a separator and never `..`
_SAFE_NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.+-]*')


def _time_key(name):
    """Sort key of a time directory name: its value as a float."""
    return float(name)


def vtk_purge_plan(done, converted, copied_ok, newest_complete, start_dir,
                   reconstructed, protected=(), n_procs=1,
                   mesh_dirs=frozenset(), ordered=(), require_copy=True,
                   per_rank_ready=None, rank_mesh=None):
    """Pure. The written times whose WSL time directory may be deleted,
    sorted by time. A name qualifies only when all of these hold:

    * the ingest has read it (`done`), foamToVTK converted it
      (`converted`) and its file was copied and verified (`copied_ok`) -
      the last two only with `require_copy` (OUT-3: a run that keeps only
      its newest fields without VTK volumes passes False);
    * in parallel (`n_procs` > 1) a successful reconstructPar covered it
      (`reconstructed`), so the root copy is the whole write - or, on a
      decomposed (parallel AMR) run, `per_rank_ready` is given instead:
      the times complete on every rank (runloop.common_ready_times); only
      those count as complete, and only those may go (OUT-3, E6);
    * it is not `0`, not the run's `start_dir` and not `protected` (the
      writes finalize re-reads: snapshots, the arrival pin, the trigger);
    * it is older than the KEEP_NEWEST newest of `newest_complete`, the
      complete writes (with fewer than that, nothing qualifies);
    * D9: a time that holds its own `polyMesh/` (`mesh_dirs`, serial AMR)
      goes only when the next newer time that stays is a mesh time too -
      otherwise that kept time, which has no mesh of its own, would
      resolve to an older instance. `ordered` is every time on disk;
      without it the names given here stand for the listing.
      `rank_mesh` {rank: times holding processor<rank>/<t>/polyMesh/}
      applies the rule per rank, conservatively (E6): a time is a mesh
      time when ANY rank holds a mesh there, and the next kept time counts
      as a mesh time only when EVERY rank holds one there."""
    ok = set(done or ())
    if require_copy:
        ok &= set(converted or ()) & set(copied_ok or ())
    ready = None
    if per_rank_ready is not None:
        ready = {str(t) for t in per_rank_ready}
        ok &= ready
    elif int(n_procs or 1) > 1:
        ok &= set(reconstructed or ())
    complete = sorted({str(t) for t in (newest_complete or ())
                       if _is_time(t) and (ready is None or str(t) in ready)},
                      key=_time_key)
    if len(complete) < KEEP_NEWEST:
        return []
    floor = float(complete[-KEEP_NEWEST])
    keep = {'0', str(start_dir)} | {str(p) for p in (protected or ())}
    cand = {t for t in ok if _is_time(t) and t not in keep
            and float(t) < floor}
    if not cand:
        return []
    known = set(ordered or ()) or (set(done or ()) | set(complete) | cand
                                   | set(protected or ()))
    listing = sorted({str(t) for t in known if _is_time(t)}, key=_time_key)
    mesh_any = mesh_all = set(mesh_dirs or ())
    if rank_mesh:
        sets = [{str(t) for t in v} for v in rank_mesh.values()]
        mesh_any = set().union(*sets)
        mesh_all = set.intersection(*sets)
    out = set()
    next_kept_is_mesh = False
    for t in reversed(listing):            # newest first
        if t in cand and (t not in mesh_any or next_kept_is_mesh):
            out.add(t)
            continue
        next_kept_is_mesh = t in mesh_all
    return sorted(out, key=_time_key)


def _case_path(case_posix):
    """The run directory, checked: a plain absolute path directly under
    the runs root (the `purge_paths` guard)."""
    from .env import RUNS_ROOT
    case = str(case_posix or '').rstrip('/')
    parts = case.split('/')
    if (not _CASE_POSIX.fullmatch(case) or '..' in parts or '.' in parts
            or not case.startswith(RUNS_ROOT + '/')
            or len(parts) != len(RUNS_ROOT.split('/')) + 1):
        raise ValueError(f'not a run directory under {RUNS_ROOT}: {case!r}')
    return case


def _written_time(name):
    """`name` when it is a written time other than 0, else ValueError."""
    s = str(name)
    if not _is_time(s) or float(s) <= 0.0:
        raise ValueError(f'not a written time: {s!r}')
    return s


def time_dir_paths(case_posix, n_procs, names):
    """D8: the paths deleting the written times `names` removes: the root
    `<case>/<t>` and, in parallel, every `<case>/processor<N>/<t>`.
    Refuses (ValueError) a case that is not a plain run directory under
    the runs root, and any name that is not a written time - `0`,
    `constant`, `-1`, a path. The deleter never builds anything else."""
    case = _case_path(case_posix)
    n = int(n_procs or 1)
    if n < 1:
        raise ValueError(f'rank count {n_procs!r}')
    out = []
    for name in names:
        s = _written_time(name)
        out.append(f'{case}/{s}')
        if n > 1:
            out.extend(f'{case}/processor{i}/{s}' for i in range(n))
    return out


def volume_file_name(case_posix, name):
    """The file `foamToVTK -useTimeName` writes for time `name`:
    `VTK/<case name>_<time>.vtk` (OpenFOAM-9 foamToVTK.C: `fvPath/vtkName
    + "_" + timeDesc + ".vtk"`, vtkName = the case directory's name),
    relative to the case."""
    case = _case_path(case_posix)
    return f'VTK/{case.rsplit("/", 1)[1]}_{_written_time(name)}.vtk'


def volume_file_paths(case_posix, names):
    """The converted files of `names` inside WSL, for the delete."""
    case = _case_path(case_posix)
    return [f'{case}/{volume_file_name(case, n)}' for n in names]


def _sample_time(name):
    """`name` when it is a sample time (0 included: a surface function
    object samples the initial state too, measured on this build), else
    ValueError."""
    s = str(name)
    if not _is_time(s) or float(s) < 0.0:
        raise ValueError(f'not a sample time: {s!r}')
    return s


def surface_dir_paths(case_posix, fo_name, names):
    """`<case>/postProcessing/<fo_name>/<t>` for each sample time, the
    surface output a sweep has copied. `fo_name` must be one of the two
    VTK surface function objects the writer emits."""
    case = _case_path(case_posix)
    if fo_name not in (VTK_SECTIONS, VTK_OBSTACLES):
        raise ValueError(f'not a VTK surface function object: {fo_name!r}')
    return [f'{case}/postProcessing/{fo_name}/{_sample_time(n)}'
            for n in names]


#: D14 / Q6: cell data only, no per-patch files, no face zones, and no
#: function objects executed by the converter itself. `-useTimeName` names
#: the file by the time, `-poly` keeps polyhedral (AMR split-hex) cells
#: whole instead of decomposing them. OpenFOAM-9 `foamToVTK -help`, read
#: on this machine; `-time` keeps the old files in VTK/ (foamToVTK.C).
VTK_FLAGS = ('-poly', '-useTimeName', '-noFunctionObjects', '-noFaceZones',
             '-noPointValues', '-excludePatches', '\'(".*")\'')


def vtk_argv_script(names, fields):
    """The foamToVTK command line converting the written times `names`
    with `fields` (D14), for `cd <case> && ...` inside WSL. A field a time
    does not hold (pMax / impulse on a resumed AMR leg) is simply not
    written: foamToVTK reads the fields it finds (IOobjectList) and
    filters them by the list."""
    times = ','.join(_written_time(n) for n in names)
    if not times:
        raise ValueError('no time to convert')
    flds = [str(f) for f in fields]
    if not flds or not all(_SAFE_NAME.fullmatch(f) for f in flds):
        raise ValueError(f'bad field list {fields!r}')
    return (f"foamToVTK -time '{times}' -fields '({' '.join(flds)})' "
            + ' '.join(VTK_FLAGS))


def surface_sweep_plan(listing, final):
    """The time directories of one surface function object's output that a
    sweep takes, sorted by time: every one but the newest during the run
    (the function object may still be writing it), all of them at the
    final sweep. `listing` is the directory's entries; blastFoam's own
    `.vtk.series` files beside the time dirs are not times and are
    ignored."""
    times = sorted({str(n) for n in (listing or ()) if _is_time(n)},
                   key=_time_key)
    return times if final else times[:-1]


def _safe(name, what):
    """`name` as a string when it is a safe path component (`_SAFE_NAME`,
    no `..`), else ValueError naming `what`."""
    s = str(name)
    if not _SAFE_NAME.fullmatch(s) or '..' in s:
        raise ValueError(f'not a {what} name: {s!r}')
    return s


#: vtk\\ names a section plane may not take: the other series' folders
#: and the manifest (the writer names planes `slice_<axis>_<pos>`)
_RESERVED = (VOLUMES, OBSTACLES, SECTIONS, 'manifest')


def series_folder(kind, surface=None):
    """The folder of one series inside vtk\\ (owner decision 2,
    2026-09-27): `volumes`, the section plane's own name
    (`slice_x_0.20`), or `obstacles`."""
    if kind == VOLUMES:
        return VOLUMES
    if kind == SECTIONS:
        s = _safe(surface, 'surface')
        if s in _RESERVED:
            raise ValueError(f'a section plane cannot be named {s!r}')
        return s
    if kind == OBSTACLES:
        return OBSTACLES
    raise ValueError(f'not a VTK family: {kind!r}')


def dest_name(kind, surface, time):
    """Where a file lands inside the model folder's vtk\\, relative, '/'
    separators, with OpenFOAM's own time name never reformatted (owner
    decisions 1-2): `<series folder>/t_<time>.vtk` - `volumes/`,
    `slice_x_0.20/`, `obstacles/` - one file per surface per time holding
    every chosen field."""
    s = str(time)
    if not _is_time(s):
        raise ValueError(f'not a written time: {s!r}')
    return f'{series_folder(kind, surface)}/t_{s}.vtk'


def series_name(kind, surface=None):
    """The `.vtk.series` of one series, relative to vtk\\, beside its
    folder, every series at one level (owner decision 2):
    `volumes.vtk.series`, `slice_x_0.20.vtk.series`,
    `obstacles.vtk.series`. Each is opened on its own in ParaView
    (decision 3)."""
    return f'{series_folder(kind, surface)}{vtk_series.SERIES_SUFFIX}'


def readable_arrays(arrays, p_ambient=P_AIR):
    """The attribute arrays as they are written (owner decisions 4-5):
    renamed by VTK_ARRAY_NAMES (a name not in it - foamToVTK's `cellID` -
    kept), `pMax` turned into the peak overpressure pMax - `p_ambient`
    [Pa], and each array written the Viper way: one component as SCALARS,
    three (velocity) as VECTORS, anything else as a FIELD array. Pure;
    ValueError when two arrays end up with one name.

    blastFoam's pMax starts at 0, so at t = 0 a bare pMax - p_ambient
    reads -p_ambient everywhere. Owner decision (2026-09-27): the running
    max includes the current pressure - max(pMax, p) - p_ambient when `p`
    of the same length is among `arrays`, else max(pMax - p_ambient, 0).

    OUT-4b (owner Q2): `impulseMax` -> Peak_Impulse gets the same
    addendum - the running max includes the current value,
    max(impulseMax, impulse) when `impulse` of the same length is among
    `arrays`; else as written (no floor: the net impulse may be
    negative)."""
    p_now = next((np.asarray(a.values, dtype=np.float64) for a in arrays
                  if a.name == 'p'), None)
    i_now = next((np.asarray(a.values, dtype=np.float64) for a in arrays
                  if a.name == 'impulse'), None)
    out = []
    for a in arrays:
        vals = a.values
        if (a.name == 'impulseMax' and i_now is not None
                and i_now.shape == np.shape(vals)):
            vals = np.maximum(np.asarray(vals, dtype=np.float64), i_now)
        if a.name == 'pMax':
            # decision 4: peak OVERPRESSURE, over the ambient the gauges
            # use (core.constants.P_AIR; writer.py's pRef, gauge_summary)
            vals = np.asarray(vals, dtype=np.float64)
            if p_now is not None and p_now.shape == vals.shape:
                vals = np.maximum(vals, p_now) - float(p_ambient)
            else:
                vals = np.maximum(vals - float(p_ambient), 0.0)
        ncomp = a.ncomp
        if a.name == 'dynamicP' and ncomp == 3:
            # OUT-4a (owner Q5 interim): the magnitude of blastFoam's
            # dynamicP vector 0.5 rho U |U| is the dynamic pressure
            # q = 0.5 rho |U|^2 (blastFoam User Guide v6.0, sec. 15.9,
            # eq. 15.1, p. 125) - written as one scalar
            v = np.asarray(vals, dtype=np.float64).reshape(-1, 3)
            vals, ncomp = np.sqrt((v * v).sum(axis=1)), 1
        if ncomp == 1:
            kind = 'scalars'
        elif a.ncomp == 3 and a.vtk_type in ('float', 'double'):
            kind = 'vectors'
        else:
            kind = 'field'
        out.append(legacy_vtk.Array(VTK_ARRAY_NAMES.get(a.name, a.name),
                                    vals, a.vtk_type, kind))
    names = [a.name for a in out]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise ValueError(f'array name(s) given twice: {dup}')
    return out


def obstacle_ids(points, polys, boxes, tol, axisym=False):
    """OUT-4b (owner Q3): the 1-based obstacle each face of the obstacles
    wall belongs to, as an int32 array - the first of `boxes` (the
    Obstacles table order) whose surface holds the face centroid, so a
    face on two coplanar touching boxes goes to the lower index. Pure;
    no mesh, patch or golden change (plan F5: one patch per obstacle
    would need createPatch).

    `points` (n, 3) [m]; `polys` one sequence of point indices per face;
    `boxes` the SNAPPED boxes (CaseSpec.obstacles): (x0, x1, y0, y1, z0,
    z1) in 3D, (x0, x1, y0, y1) in 2D, where the face is placed by its
    (x, y) - or, `axisym`, by (r, y) with r = hypot(x, z) per point, the
    wedge's radius. On the surface = inside the box grown by `tol` [m]
    and within `tol` of one of its face planes. ValueError when a face
    lies on no box: an untagged face is never written as 0."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    boxes = [tuple(float(v) for v in b) for b in boxes]
    if not boxes:
        raise ValueError('no obstacle box to tag the faces with')
    if len({len(b) for b in boxes}) != 1 or len(boxes[0]) not in (4, 6):
        raise ValueError(f'obstacle boxes must all be 2D (4) or 3D (6) '
                         f'values: {boxes!r}')
    if len(boxes[0]) == 4:
        u = np.hypot(pts[:, 0], pts[:, 2]) if axisym else pts[:, 0]
        pts = np.column_stack([u, pts[:, 1]])
    faces = [np.asarray(f, dtype=np.int64) for f in polys]
    if not faces:
        return np.zeros(0, dtype=np.int32)
    sizes = np.array([len(f) for f in faces])
    if sizes.min() < 1:
        raise ValueError('a face with no point')
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    cen = np.add.reduceat(pts[np.concatenate(faces)], starts,
                          axis=0) / sizes[:, None]
    ids = np.zeros(len(faces), dtype=np.int32)
    for i, b in enumerate(boxes, start=1):
        lo, hi = np.array(b[0::2]), np.array(b[1::2])
        inside = np.all((cen >= lo - tol) & (cen <= hi + tol), axis=1)
        on = np.any((np.abs(cen - lo) <= tol) | (np.abs(cen - hi) <= tol),
                    axis=1)
        ids[(ids == 0) & inside & on] = i
    bad = np.flatnonzero(ids == 0)
    if bad.size:
        raise ValueError(f'{bad.size} obstacle face(s) lie on no obstacle '
                         f'box, the first at {cen[bad[0]].tolist()}')
    return ids


def polygon_faces(vd):
    """The faces of a POLYDATA surface as point-index arrays (its
    POLYGONS block); ValueError for anything else."""
    blk = vd.block('POLYGONS') if vd.dataset == 'POLYDATA' else None
    if blk is None or any(vd.block(k) is not None for k in
                          ('VERTICES', 'LINES', 'TRIANGLE_STRIPS')):
        raise ValueError('the obstacles surface is not a POLYGONS-only '
                         'POLYDATA - its faces cannot be tagged')
    conn = np.asarray(blk.values, dtype=np.int64)
    out, i = [], 0
    while i < len(conn):
        n = int(conn[i])
        out.append(conn[i + 1:i + 1 + n])
        i += 1 + n
    return out


#: the VTK cell type of a polyhedron (foamToVTK -poly, VTK_FLAGS): its
#: CELLS entry is a face stream [n_faces, n_pts, ids..., n_pts, ids...]
_POLYHEDRON = 42


def decimation_of(fam):
    """OUT-4c (owner Q4): the decimation k of a normalised volumes family,
    1 when it is absent or not a whole number >= 1 (validation refuses
    that)."""
    k = (fam or {}).get('decimate', 1)
    if isinstance(k, bool) or not isinstance(k, (int, float)):
        return 1
    if k != int(k) or k < 1:
        return 1
    return int(k)


def _cell_centroids(pts, conn, ctype, n):
    """Walk the CELLS array `conn` of `n` cells: (centroids (n, 3) [m],
    start index of each cell's entry, its size entry, and a mask of the
    entries that are point ids). `pts` (m, 3) [m]; `ctype` the cell
    types. A polyhedron is a face stream (`_POLYHEDRON`)."""
    c = conn.tolist()
    starts = np.empty(n, dtype=np.int64)
    pos = 0
    for i in range(n):
        starts[i] = pos
        pos += 1 + c[pos]
    sizes = conn[starts]
    # which CELLS entries are point ids (not a cell size or a face size)
    is_id = np.ones(conn.size, dtype=bool)
    is_id[starts] = False
    cen = np.empty((n, 3))
    poly = ctype == _POLYHEDRON
    for i in np.flatnonzero(poly):
        s = int(starts[i]) + 1
        n_faces, j, ids = c[s], s + 1, []
        is_id[s] = False
        for _ in range(n_faces):
            is_id[j] = False
            ids += c[j + 1:j + 1 + c[j]]
            j += 1 + c[j]
        cen[i] = pts[np.unique(ids)].mean(axis=0)
    simple = ~poly
    if simple.any():
        s_st, s_sz = starts[simple], sizes[simple]
        if s_sz.min() < 1:
            raise ValueError('a cell with no point')
        off = np.concatenate([[0], np.cumsum(s_sz)[:-1]])
        idx = np.repeat(s_st + 1 - off, s_sz) + np.arange(int(s_sz.sum()))
        cen[simple] = np.add.reduceat(pts[conn[idx]], off,
                                      axis=0) / s_sz[:, None]
    return cen, starts, sizes, is_id


def decimate(vd, k, origin, dx_base):
    """OUT-4c (owner Q4, 2026-09-27): subsample the volume `vd` (an
    UNSTRUCTURED_GRID, foamToVTK's) per axis - keep the cells whose
    centroid lies in every k-th BASE-cell layer on each axis, i.e.
    floor((c - origin) / dx_base) % k == 0 for x, y and z, then re-index
    the points. Values are copied, never averaged, so a peak in a dropped
    cell is not shown: the files are for viewing only.

    AMR-safe: a refined cell lies inside its base cell, so it goes with
    it, and no cellSet per time is needed. `origin` (3,) [m] is the base
    grid's first face, `dx_base` [m] its cell. The centroid is the mean of
    the cell's distinct points (inside a convex cell). k = 1 returns `vd`
    itself; `vd` is never modified. ValueError on a bad k, grid or
    dataset. Pure: no WSL (plan OUT-4c C2)."""
    if isinstance(k, bool) or not isinstance(k, (int, np.integer)) or k < 1:
        raise ValueError(f'decimation must be a whole number >= 1, not {k!r}')
    if k == 1:
        return vd
    if vd.dataset != 'UNSTRUCTURED_GRID':
        raise ValueError(f'only an UNSTRUCTURED_GRID volume is decimated, '
                         f'not {vd.dataset}')
    origin = np.asarray(origin, dtype=np.float64).reshape(-1)
    dx_base = float(dx_base)
    if origin.shape != (3,) or not np.all(np.isfinite(origin)) \
            or not (np.isfinite(dx_base) and dx_base > 0):
        raise ValueError(f'decimation needs a 3D origin and a base cell > 0 '
                         f'(origin {origin.tolist()}, dx_base {dx_base!r})')
    pts_b, cells, types = (vd.block(kw) for kw in
                           ('POINTS', 'CELLS', 'CELL_TYPES'))
    if pts_b is None or cells is None or types is None:
        raise ValueError('the volume has no POINTS / CELLS / CELL_TYPES')
    pts = np.asarray(pts_b.values, dtype=np.float64).reshape(-1, 3)
    conn = np.asarray(cells.values, dtype=np.int64)
    ctype = np.asarray(types.values)
    n = int(cells.args[0])
    cen, starts, sizes, is_id = _cell_centroids(pts, conn, ctype, n)
    layer = np.floor((cen - origin) / dx_base).astype(np.int64)
    keep = np.all(layer % k == 0, axis=1)
    if not keep.any():
        # never an empty file in silence: a base grid that does not
        # match the mesh, or k past the base-cell count on an axis while
        # its first layer is carved out (a chamber wall)
        raise ValueError(f'decimation by {k} keeps no cell of {n} (base '
                         f'cell {dx_base:g} m from {origin.tolist()}) - '
                         f'lower k, or check the base grid')
    entry_keep = np.repeat(keep, sizes + 1)
    used = np.zeros(len(pts), dtype=bool)
    used[conn[is_id & entry_keep]] = True
    new_index = np.cumsum(used) - 1
    new_conn = conn[entry_keep]
    ids_new = is_id[entry_keep]
    new_conn[ids_new] = new_index[new_conn[ids_new]]
    n_keep, n_pts = int(keep.sum()), int(used.sum())
    geometry = []
    for b in vd.geometry:
        if b.keyword == 'POINTS':
            b = legacy_vtk.Block('POINTS', (n_pts, b.args[1]),
                                 np.asarray(b.values)[used])
        elif b.keyword == 'CELLS':
            b = legacy_vtk.Block('CELLS', (n_keep, new_conn.size), new_conn)
        elif b.keyword == 'CELL_TYPES':
            b = legacy_vtk.Block('CELL_TYPES', (n_keep,), ctype[keep])
        geometry.append(b)

    def cut(arrays, mask):
        return [legacy_vtk.Array(a.name, np.asarray(a.values)[mask],
                                 a.vtk_type, a.kind) for a in arrays]
    return legacy_vtk.VtkData(vd.dataset, geometry, list(vd.field_data),
                              cut(vd.cell_data, keep),
                              cut(vd.point_data, used), title=vd.title,
                              version=vd.version, binary=vd.binary)


def export_file(vd, t, p_ambient=P_AIR, title=None):
    """`vd` as it is written: readable arrays (cell and point data kept
    apart, as the source holds them) and the sample time `t` [s] inside
    (owner decision 6)."""
    vd.cell_data = readable_arrays(vd.cell_data, p_ambient)
    vd.point_data = readable_arrays(vd.point_data, p_ambient)
    names = vd.arrays()
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise ValueError(f'array name(s) given twice: {dup}')
    if title is not None:
        vd.title = title
    return legacy_vtk.with_time(vd, float(t))


def split_surface_file(filename, fields=()):
    """(field, surface) of a surface file `<field>_<surface>.vtk` as
    blastFoam's vtkTimeSeries writer names it (vtkTimeSeriesSurfaceWriter.C:
    `outputDir/fieldName + '_' + surfaceName + ".vtk"`), or None. The
    longest field of `fields` that prefixes the name wins; without one the
    name splits at its first '_' (no VTK field name holds one)."""
    name = str(filename)
    if not name.endswith('.vtk'):
        return None
    stem = name[:-4]
    for f in sorted((str(x) for x in fields), key=len, reverse=True):
        if stem.startswith(f + '_') and len(stem) > len(f) + 1:
            return f, stem[len(f) + 1:]
    field, sep, surface = stem.partition('_')
    if not sep or not field or not surface:
        return None
    return field, surface


# ── the executor (Step 6) ────────────────────────────────────────────────

#: test-only switch (batch plan Step 11, rule 2): with it set to 1 the
#: export converts and copies as usual but deletes nothing in WSL
NO_DELETE_ENV = 'BLASTLAB_VTK_NO_DELETE'
#: written times per foamToVTK call while the solver runs (one call at a
#: time, D13) and at the final sweep
BATCH_RUN = 8
BATCH_FINAL = 50
#: a failed conversion or copy is tried this many times in all, then the
#: time goes into `not_converted` (plan sec. 3.5)
ATTEMPTS = 2
#: the final sweep waits for foamToVTK up to max(this, n_cells / 1e3) s
FINAL_WAIT_MIN_S = 600.0
#: while the solver runs, the export looks at the disk at most this often
EVERY_S = 1.0
#: one `rm -rf` stage in WSL may take this long [s] before the delete fails
DELETE_TIMEOUT_S = 300
#: how long Conversion.kill waits for the killed foamToVTK to exit [s]
KILL_WAIT_S = 10
#: foamToVTK output lines kept for a failure detail
TAIL_LINES = 40
#: of those, the last this many go into the failure detail
DETAIL_LINES = 3

_T_FILE = re.compile(r't_(.+)\.vtk')


def final_wait_s(n_cells):
    """The final sweep's bound on waiting for foamToVTK [s]."""
    return max(FINAL_WAIT_MIN_S, float(n_cells or 0) / 1e3)


def delete_wsl(paths):
    """rm -rf `paths` inside WSL (no OpenFOAM env needed), one stage per
    `rm_scripts` chunk (the Windows command-line cap). True when every
    stage went through. The callers build `paths` with the guarded
    builders above only."""
    from . import env
    for script in rm_scripts(paths):
        try:
            res = subprocess.run(env.wsl_plain_argv(script),
                                 capture_output=True,
                                 timeout=DELETE_TIMEOUT_S,
                                 stdin=subprocess.DEVNULL,
                                 creationflags=env.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            return False
        if res.returncode != 0:
            return False
    return True


class Conversion:
    """One asynchronous foamToVTK call over several written times (D13):
    a Popen and a pump thread, as `runner.run_stage_stoppable`, polled
    once per lap so the ingest never blocks on it."""

    def __init__(self, case_posix, names, fields):
        from . import env
        self.names = list(names)
        script = (f'cd {_case_path(case_posix)} && '
                  + vtk_argv_script(self.names, fields))
        self.tail = collections.deque(maxlen=TAIL_LINES)
        self.proc = subprocess.Popen(
            env.wsl_argv(script), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=env.CREATE_NO_WINDOW)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        try:
            with self.proc.stdout as stream:
                for raw in stream:
                    self.tail.append(raw.decode('utf-8', 'replace').rstrip())
        except (OSError, ValueError):
            pass

    def poll(self):
        """None while it runs, else (ok, detail)."""
        rc = self.proc.poll()
        if rc is None:
            return None
        if rc == 0:
            return True, ''
        return False, (f'exit {rc}: '
                       + ' / '.join(ln for ln in list(self.tail)[-DETAIL_LINES:] if ln))

    def kill(self):
        """Kill the converter and wait for it; a failure is ignored."""
        try:
            self.proc.kill()
            self.proc.wait(timeout=KILL_WAIT_S)
        except (OSError, subprocess.TimeoutExpired):
            pass


def start_conversion(spec, names, fields):
    """The default `runner`: a Conversion of `names` in the run's case."""
    return Conversion(spec.case_posix, names, fields)


def note_resume(vtk_dir, times, log, deleted=None):
    """D10 / owner Q5: a resume replays the writes left on disk. When the
    VTK export of the run being resumed had already converted - and so
    possibly deleted - writes that are no longer there, say so once and
    set `replay_incomplete` in vtk\\manifest.json: the frames, and on AMR
    the Python peak/impulse, cover only the writes that are left. 2D/3D
    snapshots survive (their dirs are protected); a 1D run deletes no
    written time (P9), so it never gets here. True when it applied.
    `vtk_dir` is `hooks.vtk_dir`; a run without a model folder has none.

    OUT-3: without a vtk\\ manifest, `deleted` (`hooks.fields_deleted`,
    what this stage's purge removed) gives the same one line."""
    state = (vtk_series.load_vtk_manifest(vtk_dir)
             if isinstance(vtk_dir, str) and vtk_dir else None)
    if not state:
        gone = sorted({str(t) for t in (deleted or ())}
                      - {str(t) for t in times}, key=_time_key)
        if not gone:
            return False
        log(f'  [blastfoam] resuming after {len(gone)} older written '
            f'time(s) were deleted in WSL (only the newest writes are '
            f'kept): the replay rebuilds the frames (and, on AMR, the '
            f'per-write peak/impulse) from the {len(times)} left; the '
            f'snapshots are kept.')
        return True
    vol = (state.get('families') or {}).get(VOLUMES) or {}
    gone = sorted({str(t) for t in vol.get('times') or ()}
                  - {str(t) for t in times}, key=_time_key)
    if not gone:
        return False
    state['replay_incomplete'] = True
    try:
        vtk_series.write_vtk_manifest(vtk_dir, state)
    except OSError:
        pass                            # the log line still says it
    log(f'  [blastfoam] resuming after the VTK export removed {len(gone)} '
        f'written time(s) from WSL: the replay rebuilds the frames (and, '
        f'on AMR, the per-write peak/impulse) from the {len(times)} left; '
        f'the snapshots are kept. Recorded as replay_incomplete in '
        f'vtk\\manifest.json.')
    return True


def deleted_note(case_dir, vtk_dir=None):
    """Owner decision P11: the warning line for a reader of the finished
    run `case_dir` (UNC / posix / run name) whose VTK export deleted
    written times after converting them, else None. `vtk_dir` is the
    model's vtk\\ when the caller knows it (the Results tab); otherwise
    it is found under the settings' runs folder by the manifest's
    `scratch`. Never raises.

    OUT-3: a run with no VTK export that kept only its newest writes is
    found by the model root manifest's `wsl_scratch.posix`, and its
    `wsl_fields` gives the line (`vtk_series.fields_warning`)."""
    try:
        posix = runs_dir = None
        if not vtk_dir:
            from . import env
            from ...core import settings
            posix = env.case_paths(case_dir)[0]
            runs_dir = settings.load().get('runs_dir')
            vtk_dir = vtk_series.find_vtk_dir(posix, runs_dir)
        note = vtk_series.deleted_warning(vtk_dir) if vtk_dir else None
        if note:
            return note
        found = _manifest_found(vtk_dir, posix, runs_dir)
        return vtk_series.fields_warning(*found) if found else None
    except Exception:                   # noqa: BLE001 - a note, never a failure
        return None


def _manifest_found(vtk_dir, posix, runs_dir):
    """(path, state) of the model root manifest: beside `vtk_dir` when it
    is known, else found by the WSL path `posix`; None when absent."""
    if vtk_dir:
        path = os.path.join(os.path.dirname(os.path.normpath(vtk_dir)),
                            vtk_series.ROOT_MANIFEST)
        state = vtk_series.load_vtk_manifest(os.path.dirname(path))
        return (path, state) if state else None
    return vtk_series.find_model_manifest(posix, runs_dir)


def _size(path):
    """The size of `path` in bytes, -1 when it is absent."""
    try:
        return os.path.getsize(path)
    except OSError:
        return -1


def _field_order(part):
    """Sort key of a (field, file) part: VTK_FIELDS order, then name."""
    field = part[0]
    return (VTK_FIELDS.index(field) if field in VTK_FIELDS
            else len(VTK_FIELDS), field)


def _remove(path):
    """Delete the file `path`; a missing or locked file is ignored."""
    try:
        os.remove(path)
    except OSError:
        pass


def _nc_key(e):
    """Sort key of a not_converted entry: family, then time (the export's
    own entry has none)."""
    try:
        t = float(e.get('time'))
    except (TypeError, ValueError):
        t = -1.0
    return str(e.get('family')), t


def _cadence(fam):
    """The manifest's cadence entry of a family (mode, value, unit), or
    None when the family is off."""
    if not fam:
        return None
    # Time mode is in seconds (owner decision P22)
    return dict(mode=fam['mode'], value=fam['value'],
                unit='s' if fam['mode'] == 'time' else 'steps')


class VtkExport:
    """OUT-2 (plan sec. 3.5): convert, copy and verify every write of a
    blastFoam run into `<MODEL>\\vtk\\`, then delete the WSL copies the
    pure `vtk_purge_plan` allows.

    Active only when the case has a VTK family on AND the hooks carry a
    model folder (`hooks.vtk_dir`, set by model_folder.stage_solve; D12).
    Without a folder the export is inactive: one log line, no converter
    call, no delete.

    `run(done, final)` - after every ingest pass and on the final sweep:

    1. poll (or, final, wait for) the one asynchronous foamToVTK call
       (D13) and start the next one over ingested, unconverted times;
    2. copy `VTK/<case>_<t>.vtk` to a staging file beside its destination
       (size-checked against the source), rename its arrays, add the
       TIME field and write `vtk\\volumes\\t_<t>.vtk` atomically, then
       read it back with the strict parser (output/legacy_vtk.py);
    3. sweep the surface function objects' output (`postProcessing/
       vtkSections|vtkObstacles/<t>/<field>_<surface>.vtk`, all but the
       newest sample until the final sweep): per surface and time, stage
       every per-field file, check they share one geometry, and merge
       them into one `vtk\\<plane>\\t_<t>.vtk` / `vtk\\obstacles\\
       t_<t>.vtk` holding every field (owner decisions 1-6), written and
       verified the same way;
    4. rewrite the `.vtk.series` files and `vtk\\manifest.json` - BEFORE
       any delete, so a resume never meets a deleted write the manifest
       does not know was copied;
    5. delete in WSL, in one chunked rm: the planned time dirs
       (`time_dir_paths`), the copied `VTK/` files and the swept surface
       dirs; then the manifest again (`deleted_in_wsl`).

    Failures: a foamToVTK or copy failure logs one line per kind, keeps
    the WSL copy and is retried once; then the time goes into
    `not_converted`, which keeps the scratch (Q4). Nothing raises and the
    run is never stopped by its export. The final sweep converts every
    ingested write, protected ones included, but deletes only what the
    plan allows; it waits for foamToVTK up to `final_wait_s(n_cells)`.

    Why deleting is safe (D1) - what finalize reads from disk, and how it
    stays there (solvers/foam/backend.py, line numbers as of the Step 7
    verification):

    ==========================  =====================  ===================
    reader (backend.py:line)    what it re-reads       kept by
    ==========================  =====================  ===================
    _final_read (:480)          the newest write,      KEEP_NEWEST = 2
                                else the one before
    finalize_1d (:1167, :1180)  final dir; the         newest two; the pin
                                arrival-pin dir        candidate (:1041,
                                (snapshots come from   _track_pin :579)
                                `store`, in memory)
    finalize_2d (:1611, :1622,  final dir; every       newest two; each
    :1699, :1718)               snap_names dir; the    snapshot (:1479),
                                pin; the remap         the pin candidate
                                trigger dir            (:1464), the remap
                                                       trigger dir (:1509)
    finalize_2d arrived_2d      `p` of every write of  the run loop's
    (:1683)                     the quiet prefix       `arrived` cache,
                                                       read only for a
                                                       deleted dir
    finalize_3d (:2271, :2281)  final dir; every       newest two; each
                                snap_names dir         snapshot (:2132)
    PeakImpulse.final (:1674,   the final dir's pMax   newest two
    :2294)                      / impulse
    resume_run (:882)           the restart time       'restart' (set as
                                (the solver reads it)  spec.restart_dir)
    ==========================  =====================  ===================

    The first write where the arrival holds is kept as well ('arrival',
    `_track_pin`): a resume or a postmortem load re-runs the pin's
    forward scan on the writes left on disk, and the boundary can vent
    back below the threshold on later writes.

    A 1D run deletes no written time at all (owner decision P9): its
    snapshots are picked at finalize from the writes on disk, so a
    resumed 1D run still has every one. Every frame lives in memory; a
    2D/3D resume after deletion replays only what is left (D10,
    `note_resume`).

    A W3 auto-resume builds a new loop on the same hooks: construction
    reads `vtk\\manifest.json` back, so no time is exported twice.

    OUT-3 (docs/batches/2026-09-27-out-3-newest-fields.md): with
    `hooks.purge_fields` (every blastFoam stage with a model folder unless
    "Keep all fields in WSL" is ticked) the same plan deletes the older
    written times of a run with no VTK family too, without the copy gate
    (`require_copy=False` when volumes are off); no vtk\\ folder is made,
    and the deleted times go to `hooks.fields_deleted`. With
    `hooks.keep_all_fields` no written time is deleted at all (E8)."""

    def __init__(self, spec, hooks, fields, delete=None, runner=None,
                 copy=None, sleep=None, clock=None):
        self.spec, self.hooks, self.fields = spec, hooks, fields
        self.delete = delete or delete_wsl
        self.runner = runner or start_conversion
        self.copy = copy or shutil.copyfile
        self._sleep = sleep or _time.sleep
        self._clock = clock or _time.monotonic
        self.vtk_dir = getattr(hooks, 'vtk_dir', None)
        self.vol = getattr(spec, 'vtk_volumes', None) or None
        self.surf = getattr(spec, 'vtk_surfaces', None) or None
        wanted = bool(self.vol or self.surf)
        #: OUT-2: the VTK export proper (a family and a model folder)
        self.export_on = bool(wanted and self.vtk_dir)
        #: OUT-3: "Keep all fields in WSL" - no written time is deleted,
        #: by this purge or by the export (batch plan E8)
        self.keep_all = getattr(hooks, 'keep_all_fields', False) is True
        #: OUT-3: keep only the newest writes in WSL, whatever the
        #: families - set by model_folder.stage_solve (E4)
        self.purge_fields = (getattr(hooks, 'purge_fields', False) is True
                             and not self.keep_all)
        self.active = self.export_on or self.purge_fields
        decomposed = bool(getattr(spec, 'decomposed', False))
        self.volumes_on = bool(self.export_on and self.vol and not decomposed)
        self.no_delete = os.environ.get(NO_DELETE_ENV) == '1'
        dim = int(getattr(spec, 'dim', 3) or 3)
        #: P9: the written time dirs of a 1D run stay in WSL until the
        #: scratch is released (see _run)
        self.keep_time_dirs = dim == 1
        have = vtk_fields_for(dim)
        self.vol_fields = [f for f in (self.vol or {}).get('fields', ())
                           if f in have]
        #: OUT-4c (owner Q4): the volume files keep one base-cell layer
        #: in k per axis (`decimate`), 3D only (validation refuses it
        #: elsewhere; 1 here whatever the case says)
        self.decimate = decimation_of(self.vol) if dim == 3 else 1
        surf = self.surf or {}
        self.surf_fields = {
            VTK_SECTIONS: (list(surf.get('fields', ())) if dim == 3
                           else []),
            VTK_OBSTACLES: list(surf.get('obstacle_fields', ()))}
        #: OUT-4b (owner Q3): tag each obstacle file's faces (Obstacle_ID)
        self.tag_obstacles = 'obstacleID' in self.surf_fields[VTK_OBSTACLES]
        self._protect = {}              # name -> the reasons it is kept
        self.reconstructed = set()
        self.converted, self.copied, self.deleted = set(), set(), set()
        self.swept = {VTK_SECTIONS: set(), VTK_OBSTACLES: set()}
        self.failures = collections.Counter()
        self.not_converted = {}         # (family, time) -> manifest entry
        self.files = {}                 # dest rel -> (family, time)
        self.series = {}                # series rel -> {entry: time}
        self.series_kind = {}           # series rel -> family
        #: owner decision 4: Peak_Overpressure = pMax - this [Pa], the
        #: ambient the gauges' overpressure uses
        self.p_ambient = float(P_AIR)
        self.changed = set()            # series rels to rewrite
        self.rm_files, self.rm_surface = set(), set()
        self.mesh_cache = {}
        self.solo = set()               # writes of a failed batch call
        self.job = None
        self.replay_incomplete = False
        self._said = set()
        self._dirty = False
        self._next = 0.0
        self._summarised = False
        #: OUT-3: what this run has deleted so far, shared on the hooks
        #: so a W3 auto-resume (a new loop on the same hooks) and the
        #: model folder's manifest (`wsl_fields`) see it
        rec = getattr(hooks, 'fields_deleted', None)
        self._record = rec if isinstance(rec, set) else None
        if self._record:
            self.deleted.update(self._record)
        if self.keep_all:
            hooks.log('  [blastfoam] keeping all fields in WSL ("Keep all '
                      'fields in WSL" is ticked): no written time is '
                      'deleted, and the scratch is kept after the run')
        if wanted and not self.vtk_dir:
            hooks.log('  [blastfoam] VTK output is on, but this run has no '
                      'model folder - nothing is converted and no written '
                      'time is deleted')
        if not self.active:
            return
        if self.export_on and self.vol and decomposed:
            hooks.log('  [blastfoam] VTK volumes cannot be exported from a '
                      'parallel AMR run (reconstructPar cannot follow the '
                      'mesh) - sections and obstacles only')
        if ((self.volumes_on or self.purge_fields) and not decomposed
                and int(getattr(spec, 'n_procs', 1) or 1) > 1):
            self.reconstructed |= _root_whole(spec, fields)
        # a resume's restart time (backend.resume_run): the solver reads
        # it at start, and after a P1-5 walk-back the replay ingests
        # newer writes, so it is not among the newest two
        self.protect(getattr(spec, 'restart_dir', None), 'restart')
        if self.export_on:
            self._resume_state()
            fams = self._families()
            hooks.log(f'  [blastfoam] VTK output ({", ".join(fams)}) into '
                      f'{self.vtk_dir}'
                      + (f' - WSL deletes off ({NO_DELETE_ENV})'
                         if self.no_delete else ''))
            if self.volumes_on and self.decimate > 1:
                hooks.log(f'  [blastfoam] VTK volumes decimated: one base-cell '
                          f'layer in {self.decimate} per axis is written '
                          f'({VTK_DECIMATE_WARNING})')
        if self.purge_fields:
            if self.keep_time_dirs:
                # owner decision P9 (OUT-2), carried over (OUT-3 E3, Q1)
                hooks.log('  [blastfoam] 1D keeps every written time in WSL '
                          'until the scratch is released (P9)')
            else:
                hooks.log('  [blastfoam] keeping only the newest writes in '
                          'WSL: an older written time is deleted once it is '
                          'ingested and nothing reads it again ("Keep all '
                          'fields in WSL" turns this off)'
                          + (f' - WSL deletes off ({NO_DELETE_ENV})'
                             if self.no_delete else ''))

    def _families(self):
        """The active vtk\\ families, volumes first (needs `volumes_on`,
        `surf` and `surf_fields`)."""
        return ([VOLUMES] if self.volumes_on else []) + [
            k for fo, k in _SURFACE_FAMILIES
            if self.surf and self.surf_fields[fo]]

    # ── what the backend and the loop tell it ──
    def protect(self, name, why='read'):
        """Never delete written time `name`: finalize re-reads it. `why`
        keys the reason, so releasing one (the pin candidate moving on)
        never releases a write kept for another (a snapshot)."""
        if name is not None:
            self._protect.setdefault(str(name), set()).add(why)

    def unprotect(self, name, why='read'):
        """Release the reason `why` for keeping written time `name`; the
        time is deletable again once no reason is left."""
        keys = self._protect.get(str(name)) if name is not None else None
        if keys is not None:
            keys.discard(why)
            if not keys:
                del self._protect[str(name)]

    @property
    def protected(self):
        """The written times finalize will re-read (any reason)."""
        return set(self._protect)

    def covered(self, names):
        """Times a successful reconstructPar just covered (parallel)."""
        if names:
            self.reconstructed.update(str(n) for n in names)

    # ── state ──
    def _dest(self, rel):
        """The absolute path of the vtk\\-relative '/' path `rel`."""
        return os.path.join(self.vtk_dir, *rel.split('/'))

    def _once(self, kind, msg):
        """Log `msg` the first time `kind` is seen, then never again."""
        if kind not in self._said:
            self._said.add(kind)
            self.hooks.log(msg)

    def _resume_state(self):
        """Read back what an earlier loop on these hooks exported (a W3
        auto-resume): the manifest is written before any delete, so it
        is the record of what was copied and verified."""
        state = vtk_series.load_vtk_manifest(self.vtk_dir)
        if not state:
            return
        fams = state.get('families') or {}
        for kind in KINDS:
            for srel in (fams.get(kind) or {}).get('series') or ():
                path = self._dest(str(srel))
                for entry, _t in vtk_series.read_series(path):
                    rel = posixpath.normpath(posixpath.join(
                        posixpath.dirname(srel), entry))
                    m = _T_FILE.fullmatch(posixpath.basename(rel))
                    # _T_FILE keeps only `t_<time>.vtk` entries: a series
                    # entry under any other file name is skipped silently
                    # (mirrors dest_name)
                    if not m or _size(self._dest(rel)) <= 0:
                        continue
                    self.files[rel] = (kind, m.group(1))
                    self.series.setdefault(str(srel), {})[entry] = \
                        m.group(1)
                    self.series_kind[str(srel)] = kind
        for kind, t in self.files.values():
            if kind == VOLUMES:
                self.converted.add(t)
                self.copied.add(t)
        for fo, kind in _SURFACE_FAMILIES:
            self.swept[fo].update(
                str(t) for t in (fams.get(kind) or {}).get('times') or ())
        for e in state.get('not_converted') or ():
            if isinstance(e, dict) and 'time' in e:
                self.not_converted[(e.get('family', VOLUMES),
                                    str(e['time']))] = dict(e)
        self.deleted.update(str(t) for t in state.get('deleted_in_wsl') or ())
        self.replay_incomplete = bool(state.get('replay_incomplete'))

    def state(self):
        """The vtk\\ manifest (output.vtk_series.write_vtk_manifest)."""
        fams = {}
        for kind in self._families():
            rels = [r for r, (k, _t) in self.files.items() if k == kind]
            fams[kind] = dict(
                count=len(rels),
                times=sorted({self.files[r][1] for r in rels},
                             key=_time_key),
                series=sorted(s for s in self.series
                              if self.series_kind.get(s) == kind),
                # owner decision P4: the full file list lives here; the
                # model's root manifest keeps only the numbers
                files=sorted(rels, key=lambda r: (_time_key(
                    self.files[r][1]), r)))
        fields = {}
        if self.vol:
            fields[VOLUMES] = list(self.vol_fields)
        if self.surf:
            fields[SECTIONS] = list(self.surf_fields[VTK_SECTIONS])
            fields[OBSTACLES] = list(self.surf_fields[VTK_OBSTACLES])
        cadence = {}
        if self.vol:
            cadence[VOLUMES] = _cadence(self.vol)
        if self.surf:
            cadence['surfaces'] = _cadence(self.surf)
        nc = sorted(self.not_converted.values(), key=_nc_key)
        chosen = {f for fl in fields.values() for f in fl}
        # `scratch` (additive): the WSL run directory, so a reader that
        # holds only that (postmortem, the run browser) finds this
        # manifest - owner decision P11, deleted_note. `arrays` and
        # `p_ambient` (additive): the array name of each chosen field in
        # the files, and the ambient Peak_Overpressure is taken over
        # (owner decisions 4-5)
        out = dict(fields=fields, cadence=cadence, families=fams,
                   not_converted=nc,
                   deleted_in_wsl=sorted(self.deleted, key=_time_key),
                   replay_incomplete=self.replay_incomplete,
                   scratch=getattr(self.spec, 'case_posix', None),
                   arrays={f: VTK_ARRAY_NAMES.get(f, f)
                           for f in sorted(chosen)},
                   p_ambient=self.p_ambient)
        if self.vol:
            # OUT-4c (additive): the volumes' decimation k (1 = every cell)
            out['decimate'] = {VOLUMES: self.decimate}
        return out

    def _add_file(self, rel, kind, surface, t):
        """Record the written file `rel` (family `kind`, time `t`) and
        mark its series for rewriting."""
        self.files[rel] = (kind, t)
        srel = series_name(kind, surface)
        # entries relative to the series file, which sits beside the
        # series' folder at the top of vtk\ (decision 2)
        entry = posixpath.relpath(rel, posixpath.dirname(srel) or '.')
        self.series.setdefault(srel, {})[entry] = t
        self.series_kind[srel] = kind
        self.changed.add(srel)
        self._dirty = True

    def _fail(self, family, t, kind, why, path):
        """Count a failed `kind` (conversion / copy) of time `t`: retried
        once, then listed in `not_converted` (plan sec. 3.5)."""
        key = (kind, family, t)
        self.failures[key] += 1
        if self.failures[key] < ATTEMPTS:
            self._once(f'retry-{kind}',
                       f'  [blastfoam] VTK {family}: {kind} failed for t = '
                       f'{t} ({why}) - its WSL copy is kept and it is tried '
                       f'once more')
            return
        self.not_converted[(family, t)] = dict(time=t, family=family,
                                               why=why, path=path)
        self._dirty = True
        self._once(f'gave-up-{kind}',
                   f'  [warn] VTK {family}: {kind} failed twice for t = {t} '
                   f'({why}) - its WSL copy is kept, it is listed as not '
                   f'converted, and the scratch will not be released')

    # ── the run-loop entry ──
    def run(self, done, final=False):
        """One export pass (see the class docstring). Never raises."""
        if not self.active:
            return
        if not final:
            now = self._clock()
            if now < self._next:
                return
            self._next = now + EVERY_S
        try:
            self._run(done, final)
        except Exception as exc:        # noqa: BLE001 - never stops the run
            if not self.export_on:
                # OUT-3 alone: stop deleting, the run goes on
                self.active = False
                self.hooks.log(f'  [warn] WSL field purge: {exc!r} - the '
                               f'run goes on and nothing more is deleted '
                               f'in WSL')
                return
            self._once('error', f'  [warn] VTK export: {exc!r} - the run '
                                f'goes on; what was not exported stays in '
                                f'WSL, and the scratch is kept')
            self._broken(exc)

    def _broken(self, exc):
        """An unexpected error cut a pass short, so which writes it missed
        is unknown: record one `not_converted` entry for the export
        itself. write_all turns it into a failed row, and the WSL scratch
        that still holds those writes is kept (Q4) instead of being
        released as if the export were complete."""
        key = (EXPORT, 'None')
        if key not in self.not_converted:
            self.not_converted[key] = dict(
                time=None, family=EXPORT, path='vtk',
                why=f'the export stopped on {exc!r}; what it had not '
                    f'copied is still in the WSL scratch')
            self._dirty = True
        try:
            self._write_index()
        except Exception:               # noqa: BLE001 - the log line stands
            pass

    def _run(self, done, final):
        """One pass: convert and copy volumes, sweep surfaces, write the
        index, then delete in WSL what the plan allows."""
        names = []
        if self.volumes_on:
            self._convert(done, final)
            self._copy_volumes(final)
        # owner decision P9 (2026-09-27): a 1D run never deletes a
        # written time - 1D picks its snapshots at finalize from the
        # writes on disk (backend._pick_snapshots), and 1D writes are
        # small. Converted VTK/ files are still removed after the copy.
        # OUT-3 (E8): with "Keep all fields in WSL" no time dir goes.
        if ((self.volumes_on or self.purge_fields)
                and not self.keep_time_dirs and not self.keep_all):
            names = [n for n in self._plan(done) if n not in self.deleted]
        if self.export_on and self.surf:
            self._sweep(final)
        if not self._write_index():
            return                      # no delete the manifest cannot vouch for
        if not self.no_delete:
            self._delete(names)
        if final and not self._summarised:
            self._summarised = True
            self._summary()

    def close(self):
        """Kill a conversion still running (the loop's `finally`)."""
        job, self.job = self.job, None
        if job is not None and hasattr(job, 'kill'):
            job.kill()

    # ── 1-2: convert and copy the volumes ──
    def _src_volume(self, name):
        """The converted `VTK/<case>_<name>.vtk` as a UNC path on the
        Windows side."""
        rel = volume_file_name(self.spec.case_posix, name)
        return os.path.join(self.spec.case_unc, *rel.split('/'))

    def _todo(self, done):
        """The ingested written times still to convert, sorted by time."""
        running = set(self.job.names) if self.job is not None else set()
        out = []
        for n in done:
            n = str(n)
            if (not _is_time(n) or float(n) <= 0.0 or n in self.converted
                    or n in self.deleted or n in running
                    or (VOLUMES, n) in self.not_converted):
                continue
            out.append(n)
        return sorted(out, key=_time_key)

    def _batch(self, todo, n):
        """The next call's writes: a write of a failed batch alone, else
        up to `n` of them."""
        solo = [t for t in todo if t in self.solo]
        return solo[:1] or todo[:n]

    def _start(self, names):
        """Start the converter on `names`: the job, or None when it did
        not start (recorded through `_finished`)."""
        try:
            return self.runner(self.spec, names, self.vol_fields)
        except Exception as exc:        # noqa: BLE001 - recorded, retried
            self._finished(names, False, f'foamToVTK did not start: {exc}')
            return None

    def _finished(self, names, ok, detail):
        """Book the result of one foamToVTK call over `names`: a failed
        batch is split into single writes, else each write is converted
        (its VTK/ file exists) or goes to `_fail`."""
        if not ok and len(names) > 1:
            # one bad write fails the whole call: convert these one at a
            # time, so only the bad one is retried and given up
            self.solo.update(names)
            self._once('split', f'  [blastfoam] VTK volumes: foamToVTK '
                                f'failed on {len(names)} writes ({detail}) '
                                f'- converting them one at a time')
            return
        for n in names:
            if ok and _size(self._src_volume(n)) > 0:
                self.converted.add(n)
                continue
            why = detail if not ok else 'foamToVTK wrote no file'
            self._fail(VOLUMES, n, 'conversion', f'foamToVTK: {why}',
                       f'vtk/{dest_name(VOLUMES, None, n)}')

    def _wait(self, job, deadline):
        note = self._clock() + 60.0
        while True:
            res = job.poll()
            if res is not None:
                return res
            now = self._clock()
            if now > deadline:
                if hasattr(job, 'kill'):
                    job.kill()
                return False, 'timed out at the final sweep'
            if now >= note:
                note += 60.0
                self.hooks.log(f'  [blastfoam] VTK: waiting for foamToVTK '
                               f'({len(job.names)} write(s), '
                               f'{deadline - now:.0f} s left)')
            self._sleep(0.25)

    def _convert(self, done, final):
        if self.job is not None:
            res = (self.job.poll() if not final else
                   self._wait(self.job, self._clock()
                              + final_wait_s(self._n_cells())))
            if res is None:
                return                  # still converting: next lap
            job, self.job = self.job, None
            self._finished(job.names, *res)
        todo = self._todo(done)
        if not final:
            if todo:
                self.job = self._start(self._batch(todo, BATCH_RUN))
            return
        deadline = self._clock() + final_wait_s(self._n_cells())
        while todo:
            job = self._start(self._batch(todo, BATCH_FINAL))
            if job is not None:
                self._finished(job.names, *self._wait(job, deadline))
            todo = self._todo(done)
            if todo and self._clock() > deadline:
                for n in todo:
                    self.not_converted[(VOLUMES, n)] = dict(
                        time=n, family=VOLUMES,
                        why='the final sweep ran out of time',
                        path=f'vtk/{dest_name(VOLUMES, None, n)}')
                self._dirty = True
                break

    def _n_cells(self):
        try:
            return int(self.spec.n_cells or 0)
        except (AttributeError, TypeError, ValueError):
            return 0

    def _stage(self, src, folder):
        """Copy the WSL file `src` to a staging file in `folder` (beside
        its destination; a dot name no series lists) and size-check it
        against the source: (path, None) or (None, why not)."""
        stage = os.path.join(folder, f'.{os.path.basename(src)}.part')
        try:
            os.makedirs(folder, exist_ok=True)
            self.copy(src, stage)
            want, got = os.path.getsize(src), os.path.getsize(stage)
        except OSError as exc:
            why = f'copy failed: {exc}'
        else:
            if got > 0 and got == want:
                return stage, None
            why = ('the copy is empty' if got <= 0 else
                   f'the copy holds {got} of {want} bytes')
        _remove(stage)                  # never leave a torn file behind
        return None, why

    def _write_verified(self, vd, rel):
        """Write `vd` to vtk\\<rel> (atomic) and read it back with the
        strict parser; None, or why not (nothing left behind)."""
        dst = self._dest(rel)
        try:
            legacy_vtk.write(dst, vd)
            legacy_vtk.verify(dst, vd)
        except (OSError, ValueError) as exc:
            _remove(dst)
            return f'writing {rel} failed: {exc}'
        return None

    def _title(self, what, t):
        return (f'blastlab {what} t = {t} s '
                f'({os.path.basename(str(self.spec.case_posix))})')

    def _transfer_volume(self, src, rel, t):
        """vtk\\<rel> from foamToVTK's file `src`: staged, arrays renamed,
        TIME added (foamToVTK writes none - read on this build), written
        and verified; OUT-4c: decimated first when the family asks
        (`decimate`, owner Q4). None, or why not."""
        dst = self._dest(rel)
        stage, why = self._stage(src, os.path.dirname(dst))
        if why:
            return why
        try:
            try:
                vd = legacy_vtk.read(stage)
                # foamToVTK writes cellID rho p U: put them in the card's
                # field order (pressure first, as the surfaces), cellID last
                vd.cell_data.sort(key=lambda a: _field_order((a.name,)))
                vd.point_data.sort(key=lambda a: _field_order((a.name,)))
            except ValueError as exc:
                return f'not a readable VTK file: {exc}'
            if self.decimate > 1:
                try:
                    vd = decimate(vd, self.decimate, *self._base_grid())
                except (ValueError, TypeError, KeyError, IndexError,
                        AttributeError) as exc:
                    return f'decimation failed: {exc}'
            try:
                export_file(vd, t, self.p_ambient,
                            self._title('volumes', t))
            except ValueError as exc:
                return f'not a readable VTK file: {exc}'
            return self._write_verified(vd, rel)
        finally:
            _remove(stage)

    def _base_grid(self):
        """OUT-4c: (origin, dx_base) of the blockMesh base grid the
        decimation layers count on - its first face per axis [m] and its
        cell [m] (CaseSpec.grid_base / dx_base; a uniform case's grid)."""
        spec = self.spec
        g = getattr(spec, 'grid_base', None) or spec.grid
        origin = tuple(float(g[f'{a}_face'][0]) for a in 'xyz')
        dx = float(getattr(spec, 'dx_base', 0.0) or 0.0) or float(spec.dx)
        return origin, dx

    def _gave_up(self, family, t, final):
        """After a failed attempt: stop trying for now? The final sweep
        has no next pass, so it retries at once until `_fail` gives up -
        a copy that fails only there must still reach `not_converted`,
        or a finished run would release the scratch holding it (Q4)."""
        return not final or (family, t) in self.not_converted

    def _copy_volumes(self, final=False):
        for n in sorted(self.converted - self.copied, key=_time_key):
            if (VOLUMES, n) in self.not_converted:
                continue
            rel = dest_name(VOLUMES, None, n)
            while True:
                why = self._transfer_volume(self._src_volume(n), rel, n)
                if why is None:
                    self.copied.add(n)
                    self._add_file(rel, VOLUMES, None, n)
                    self.rm_files.update(
                        volume_file_paths(self.spec.case_posix, [n]))
                    break
                self._fail(VOLUMES, n, 'copy', why, f'vtk/{rel}')
                if self._gave_up(VOLUMES, n, final):
                    break

    # ── 3: the deletion plan ──
    def _mesh_listing(self, done):
        """(every time on disk, the ones holding polyMesh/) - D9, serial
        AMR only; a complete (ingested) write's answer is cached."""
        if not getattr(self.spec, 'amr', 0):
            return (), frozenset()
        from . import reader
        names = [n for _t, n in reader.list_times(self.spec.case_unc)]
        mesh = set()
        for n in names:
            has = self.mesh_cache.get(n)
            if has is None:
                has = os.path.isdir(os.path.join(self.spec.case_unc, n,
                                                 'polyMesh'))
                if n in done:
                    self.mesh_cache[n] = has
            if has:
                mesh.add(n)
        return names, frozenset(mesh)

    def _rank_listing(self, done):
        """(every time on any rank, {rank: times holding polyMesh/}) of a
        decomposed run (OUT-3, E6), or None when a rank dir cannot be
        listed. An ingested time's answer is cached, as `mesh_cache`."""
        from . import reader
        ordered, rank_mesh = set(), {}
        for i in range(int(self.spec.n_procs)):
            pu = os.path.join(self.spec.case_unc, f'processor{i}')
            try:
                names = [n for _t, n in reader.list_times(pu)]
            except OSError:
                return None
            ordered.update(names)
            mesh = set()
            for n in names:
                has = self.mesh_cache.get((i, n))
                if has is None:
                    has = os.path.isdir(os.path.join(pu, n, 'polyMesh'))
                    if n in done:
                        self.mesh_cache[(i, n)] = has
                if has:
                    mesh.add(n)
            rank_mesh[i] = mesh
        return sorted(ordered, key=_time_key), rank_mesh

    def _plan(self, done):
        names = [str(n) for n in done]
        # OUT-3: without VTK volumes nothing is converted or copied first
        kw = dict(require_copy=self.volumes_on)
        decomposed = bool(getattr(self.spec, 'decomposed', False))
        if decomposed:
            # E6: read per rank, so "complete on every rank" stands for
            # "reconstructed"; the newest such time is the restart anchor
            # and is one of the KEEP_NEWEST kept (runloop.common_ready_times)
            from .runloop import common_ready_times
            ready = common_ready_times(self.spec, self.fields)
            if not ready:
                return []
            kw['per_rank_ready'] = ready
        if not vtk_purge_plan(names, self.converted, self.copied, names,
                              self.spec.start_dir, self.reconstructed,
                              self.protected,
                              getattr(self.spec, 'n_procs', 1), **kw):
            return []
        if decomposed:
            listing = self._rank_listing(set(names))
            if listing is None:
                return []
            ordered, kw['rank_mesh'] = listing
            mesh = frozenset()
        else:
            ordered, mesh = self._mesh_listing(set(names))
        return vtk_purge_plan(names, self.converted, self.copied, names,
                              self.spec.start_dir, self.reconstructed,
                              self.protected,
                              getattr(self.spec, 'n_procs', 1),
                              mesh_dirs=mesh, ordered=ordered, **kw)

    # ── 4: the surfaces ──
    def _sweep(self, final):
        for fo, kind in ((VTK_SECTIONS, SECTIONS),
                         (VTK_OBSTACLES, OBSTACLES)):
            fields = self.surf_fields[fo]
            if not fields:
                continue
            root = os.path.join(self.spec.case_unc, 'postProcessing', fo)
            try:
                listing = os.listdir(root)
            except OSError:
                continue                # nothing sampled yet
            for t in surface_sweep_plan(listing, final):
                if t in self.swept[fo] or (kind, t) in self.not_converted:
                    continue
                while True:
                    why = self._sweep_one(kind, fields,
                                          os.path.join(root, t), t)
                    if why is None:
                        self.swept[fo].add(t)
                        self._dirty = True
                        self.rm_surface.update(surface_dir_paths(
                            self.spec.case_posix, fo, [t]))
                        break
                    self._fail(kind, t, 'copy', why,
                               'vtk' if kind == SECTIONS
                               else f'vtk/{OBSTACLES}')
                    if self._gave_up(kind, t, final):
                        break

    def _sweep_one(self, kind, fields, tdir, t):
        """One sample time of one surface function object: per surface,
        its per-field files merged into one file (owner decision 1). All
        surfaces of the time or none: a failure removes what this attempt
        wrote, so the WSL sample is kept whole for the retry."""
        try:
            files = sorted(os.listdir(tdir))
        except OSError as exc:
            return f'cannot list the sample: {exc}'
        by_surface = {}
        for f in files:
            sp = split_surface_file(f, fields)
            if sp is None:
                return f'unexpected file {f}'
            field, surface = sp
            by_surface.setdefault(surface, []).append((field, f))
        got = []
        for surface in sorted(by_surface):
            rel = dest_name(kind, surface, t)
            # the arrays in the card's field order, so `pressure` comes
            # first and is what ParaView colours by (as in Viper's files)
            parts = sorted(by_surface[surface], key=_field_order)
            why = self._merge_surface(kind, surface, parts, tdir, rel, t)
            if why:
                for done_rel, *_ in got:
                    _remove(self._dest(done_rel))
                return f'{surface}: {why}'
            got.append((rel, kind, surface, t))
        for args in got:
            self._add_file(*args)
        return None

    def _merge_surface(self, kind, surface, parts, tdir, rel, t):
        """vtk\\<rel> from one surface's per-field files `parts` [(field,
        file name)]: each staged and parsed, their geometry checked to be
        one, merged, renamed, TIME added, written and verified. The source
        association (cell or point data) is kept; nothing is
        interpolated. None, or why not."""
        folder = os.path.dirname(self._dest(rel))
        stages, loaded = [], []
        try:
            for field, name in parts:
                stage, why = self._stage(os.path.join(tdir, name), folder)
                if why:
                    return f'{name}: {why}'
                stages.append(stage)
                try:
                    loaded.append((field, legacy_vtk.read(stage)))
                except ValueError as exc:
                    return f'{name}: not a readable VTK file: {exc}'
            try:
                merged = legacy_vtk.merge(loaded)
                if kind == OBSTACLES and self.tag_obstacles:
                    merged.cell_data.append(legacy_vtk.Array(
                        'obstacleID', self._obstacle_ids(merged), 'int',
                        'scalars'))
                vd = export_file(merged, t, self.p_ambient,
                                 self._title(surface, t))
            except ValueError as exc:
                return str(exc)
            return self._write_verified(vd, rel)
        finally:
            for s in stages:
                _remove(s)

    def _obstacle_ids(self, vd):
        """OUT-4b: `obstacle_ids` of one merged obstacles file, against
        the spec's snapped boxes, to 1 % of the finest cell."""
        spec = self.spec
        cell = float(getattr(spec, 'dx_charge', None) or spec.dx)
        axisym = ('wedge', 'wedge') in (getattr(spec, 'patches', None) or ())
        return obstacle_ids(vd.block('POINTS').values, polygon_faces(vd),
                            spec.obstacles, 0.01 * cell, axisym=axisym)

    # ── 5: the index, then the delete ──
    def _write_index(self):
        if not self.export_on:
            # OUT-3 alone: no vtk\ folder and no vtk\ manifest; the record
            # is the hooks' `fields_deleted` (model folder `wsl_fields`)
            self._dirty = False
            return True
        if not self._dirty:
            return True
        try:
            for srel in sorted(self.changed):
                vtk_series.write_series(
                    self._dest(posixpath.dirname(srel)),
                    posixpath.basename(srel),
                    [(e, float(t)) for e, t in self.series[srel].items()])
            vtk_series.write_vtk_manifest(self.vtk_dir, self.state())
        except (OSError, ValueError) as exc:
            self._once('index', f'  [warn] VTK: could not write the series '
                                f'or vtk\\manifest.json ({exc}) - nothing '
                                f'is deleted in WSL until it can')
            return False
        self.changed.clear()
        self._dirty = False
        return True

    def _delete(self, names):
        paths = []
        if names:
            paths += time_dir_paths(self.spec.case_posix,
                                    getattr(self.spec, 'n_procs', 1), names)
        files, surf = sorted(self.rm_files), sorted(self.rm_surface)
        paths += files + surf
        if not paths:
            return
        try:
            ok = bool(self.delete(paths))
        except Exception:               # noqa: BLE001 - retried next pass
            ok = False
        if not ok:
            self._once('delete', '  [blastfoam] VTK: the WSL delete did not '
                                 'go through - retried at the next pass; '
                                 'nothing copied is lost' if self.export_on
                       else '  [blastfoam] the WSL delete of older written '
                            'times did not go through - retried at the next '
                            'pass; nothing ingested is lost')
            return
        self.rm_files.difference_update(files)
        self.rm_surface.difference_update(surf)
        if names:
            self.deleted.update(names)
            if self._record is not None:
                self._record.update(names)
            self._dirty = True
            self._write_index()

    def _summary(self):
        if not self.export_on:
            self.hooks.log(f'  [blastfoam] {len(self.deleted)} older written '
                           f'time(s) deleted in WSL (only the newest writes '
                           f'and the ones finalize reads are kept)')
            return
        st = self.state()
        parts = [f'{v["count"]} {k} file(s)'
                 for k, v in st['families'].items()]
        msg = (f'  [blastfoam] VTK: {", ".join(parts) or "nothing"} in '
               f'{self.vtk_dir}; {len(self.deleted)} written time(s) '
               f'deleted in WSL')
        if self.not_converted:
            msg += (f'; {len(self.not_converted)} not converted (listed in '
                    f'vtk\\manifest.json, the WSL scratch is kept)')
        self.hooks.log(msg)
