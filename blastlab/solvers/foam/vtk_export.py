"""OUT-2: VTK output for ParaView, converted and copied while the run runs.

docs/model-folder-and-vtk-plan.md sec. 3.5 / 3.6 and the batch plan
docs/batches/2026-09-27-out-2-vtk-output.md (D2, D8, D9, D14; owner answers
Q1-Q6). This module holds the pure pieces: which WSL time directories may
be deleted (`vtk_purge_plan`), the paths a delete may touch
(`time_dir_paths`), the foamToVTK command line (`vtk_argv_script`), which
surface-output time directories a sweep takes (`surface_sweep_plan`) and
where each file lands in the model folder (`dest_name`).

No Qt, no services/, no backend import: the run loop owns the executor
and the backend only tells it which writes finalize still reads.
"""

import re

from .runloop import _CASE_POSIX, _is_time, rm_scripts   # noqa: F401
from .writer import VTK_OBSTACLES, VTK_SECTIONS

#: the model folder's vtk\ subfolders (plan sec. 3.6)
VOLUMES = 'volumes'
SECTIONS = 'sections'
OBSTACLES = 'obstacles'
KINDS = (VOLUMES, SECTIONS, OBSTACLES)

#: the newest complete writes a purge always keeps: a W3 resume restarts
#: from the newest, and `backend._final_read` falls back to the one before
#: it when the newest is torn
KEEP_NEWEST = 2

#: a surface or field name as it may appear in a path: the writer's plane
#: names (`slice_y_1.40`), `obstacles` and the VTK field names
#: (`alpha.expl`); never a separator and never `..`
_SAFE_NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.+-]*')


def _time_key(name):
    return float(name)


def vtk_purge_plan(done, converted, copied_ok, newest_complete, start_dir,
                   reconstructed, protected=(), n_procs=1,
                   mesh_dirs=frozenset(), ordered=()):
    """Pure. The written times whose WSL time directory may be deleted,
    sorted by time. A name qualifies only when all of these hold:

    * the ingest has read it (`done`), foamToVTK converted it
      (`converted`) and its file was copied and verified (`copied_ok`);
    * in parallel (`n_procs` > 1) a successful reconstructPar covered it
      (`reconstructed`), so the root copy is the whole write;
    * it is not `0`, not the run's `start_dir` and not `protected` (the
      writes finalize re-reads: snapshots, the arrival pin, the trigger);
    * it is older than the KEEP_NEWEST newest of `newest_complete`, the
      complete writes (with fewer than that, nothing qualifies);
    * D9: a time that holds its own `polyMesh/` (`mesh_dirs`, serial AMR)
      goes only when the next newer time that stays is a mesh time too -
      otherwise that kept time, which has no mesh of its own, would
      resolve to an older instance. `ordered` is every time on disk;
      without it the names given here stand for the listing."""
    ok = set(done or ()) & set(converted or ()) & set(copied_ok or ())
    if int(n_procs or 1) > 1:
        ok &= set(reconstructed or ())
    complete = sorted({str(t) for t in (newest_complete or ())
                       if _is_time(t)}, key=_time_key)
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
    mesh = set(mesh_dirs or ())
    out = set()
    next_kept_is_mesh = False
    for t in reversed(listing):            # newest first
        if t in cand and (t not in mesh or next_kept_is_mesh):
            out.add(t)
            continue
        next_kept_is_mesh = t in mesh
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


def surface_dir_paths(case_posix, fo_name, names):
    """`<case>/postProcessing/<fo_name>/<t>` for each written time, the
    surface output a sweep has copied. `fo_name` must be one of the two
    VTK surface function objects the writer emits."""
    case = _case_path(case_posix)
    if fo_name not in (VTK_SECTIONS, VTK_OBSTACLES):
        raise ValueError(f'not a VTK surface function object: {fo_name!r}')
    return [f'{case}/postProcessing/{fo_name}/{_written_time(n)}'
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
    s = str(name)
    if not _SAFE_NAME.fullmatch(s) or '..' in s:
        raise ValueError(f'not a {what} name: {s!r}')
    return s


def dest_name(kind, surface, field, time):
    """Where a converted file lands inside the model folder's vtk\\
    (D2 / owner Q1), relative, '/' separators, with OpenFOAM's own time
    name never reformatted:

    * volumes:   `volumes/t_<time>.vtk` (one file per time, every field);
    * sections:  `sections/<plane>/<field>/t_<time>.vtk`;
    * obstacles: `obstacles/<field>/t_<time>.vtk`.

    `surface` / `field` are ignored where the layout has no place for
    them."""
    s = str(time)
    if not _is_time(s):
        raise ValueError(f'not a written time: {s!r}')
    if kind == VOLUMES:
        return f'{VOLUMES}/t_{s}.vtk'
    if kind == SECTIONS:
        return (f'{SECTIONS}/{_safe(surface, "surface")}/'
                f'{_safe(field, "field")}/t_{s}.vtk')
    if kind == OBSTACLES:
        return f'{OBSTACLES}/{_safe(field, "field")}/t_{s}.vtk'
    raise ValueError(f'not a VTK family: {kind!r}')


def series_name(kind, surface, field):
    """The `.vtk.series` of one file series, relative to vtk\\ (owner Q1:
    one series per field, named after the field, beside the field's own
    folder, so one family's series sit together): `volumes/volumes.vtk.
    series`, `sections/<plane>/<field>.vtk.series`,
    `obstacles/<field>.vtk.series`."""
    if kind == VOLUMES:
        return f'{VOLUMES}/{VOLUMES}.vtk.series'
    if kind == SECTIONS:
        return (f'{SECTIONS}/{_safe(surface, "surface")}/'
                f'{_safe(field, "field")}.vtk.series')
    if kind == OBSTACLES:
        return f'{OBSTACLES}/{_safe(field, "field")}.vtk.series'
    raise ValueError(f'not a VTK family: {kind!r}')


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
