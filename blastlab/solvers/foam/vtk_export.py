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

from ...models.case import vtk_fields_for
from ...output import vtk_series
from .runloop import _CASE_POSIX, _is_time, _root_whole, rm_scripts
from .writer import VTK_OBSTACLES, VTK_SECTIONS

#: the model folder's vtk\ subfolders (plan sec. 3.6)
VOLUMES = 'volumes'
SECTIONS = 'sections'
OBSTACLES = 'obstacles'
KINDS = (VOLUMES, SECTIONS, OBSTACLES)
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
                                 capture_output=True, timeout=300,
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
        self.tail = collections.deque(maxlen=40)
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
                       + ' / '.join(ln for ln in list(self.tail)[-3:] if ln))

    def kill(self):
        try:
            self.proc.kill()
            self.proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass


def start_conversion(spec, names, fields):
    """The default `runner`: a Conversion of `names` in the run's case."""
    return Conversion(spec.case_posix, names, fields)


def note_resume(vtk_dir, times, log):
    """D10 / owner Q5: a resume replays the writes left on disk. When the
    VTK export of the run being resumed had already converted - and so
    possibly deleted - writes that are no longer there, say so once and
    set `replay_incomplete` in vtk\\manifest.json: the frames, and on AMR
    the Python peak/impulse, cover only the writes that are left. 2D/3D
    snapshots survive (their dirs are protected); a 1D run deletes no
    written time (P9), so it never gets here. True when it applied.
    `vtk_dir` is `hooks.vtk_dir`; a run without a model folder has none."""
    if not isinstance(vtk_dir, str) or not vtk_dir:
        return False
    state = vtk_series.load_vtk_manifest(vtk_dir)
    if not state:
        return False
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


def _size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return -1


def _nc_key(e):
    """Sort key of a not_converted entry: family, then time (the export's
    own entry has none)."""
    try:
        t = float(e.get('time'))
    except (TypeError, ValueError):
        t = -1.0
    return str(e.get('family')), t


def _cadence(fam):
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
    2. copy `VTK/<case>_<t>.vtk` to `vtk\\volumes\\t_<t>.vtk`, size-check
       it against the source;
    3. sweep the surface function objects' output (`postProcessing/
       vtkSections|vtkObstacles/<t>/<field>_<surface>.vtk`, all but the
       newest sample until the final sweep) into `vtk\\sections\\<plane>\\
       <field>\\` and `vtk\\obstacles\\<field>\\`;
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
    reads `vtk\\manifest.json` back, so no time is exported twice."""

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
        self.active = bool(wanted and self.vtk_dir)
        decomposed = bool(getattr(spec, 'decomposed', False))
        self.volumes_on = bool(self.active and self.vol and not decomposed)
        self.no_delete = os.environ.get(NO_DELETE_ENV) == '1'
        dim = int(getattr(spec, 'dim', 3) or 3)
        #: P9: the written time dirs of a 1D run stay in WSL until the
        #: scratch is released (see _run)
        self.keep_time_dirs = dim == 1
        have = vtk_fields_for(dim)
        self.vol_fields = [f for f in (self.vol or {}).get('fields', ())
                           if f in have]
        surf = self.surf or {}
        self.surf_fields = {
            VTK_SECTIONS: (list(surf.get('fields', ())) if dim == 3
                           else []),
            VTK_OBSTACLES: list(surf.get('obstacle_fields', ()))}
        self._protect = {}              # name -> the reasons it is kept
        self.reconstructed = set()
        self.converted, self.copied, self.deleted = set(), set(), set()
        self.swept = {VTK_SECTIONS: set(), VTK_OBSTACLES: set()}
        self.failures = collections.Counter()
        self.not_converted = {}         # (family, time) -> manifest entry
        self.files = {}                 # dest rel -> (family, time)
        self.series = {}                # series rel -> {entry: time}
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
        if wanted and not self.vtk_dir:
            hooks.log('  [blastfoam] VTK output is on, but this run has no '
                      'model folder - nothing is converted and no written '
                      'time is deleted')
            return
        if not self.active:
            return
        if self.vol and decomposed:
            hooks.log('  [blastfoam] VTK volumes cannot be exported from a '
                      'parallel AMR run (reconstructPar cannot follow the '
                      'mesh) - sections and obstacles only')
        if self.volumes_on and int(getattr(spec, 'n_procs', 1) or 1) > 1:
            self.reconstructed |= _root_whole(spec, fields)
        # a resume's restart time (backend.resume_run): the solver reads
        # it at start, and after a P1-5 walk-back the replay ingests
        # newer writes, so it is not among the newest two
        self.protect(getattr(spec, 'restart_dir', None), 'restart')
        self._resume_state()
        fams = ([VOLUMES] if self.volumes_on else []) + [
            k for fo, k in ((VTK_SECTIONS, SECTIONS),
                            (VTK_OBSTACLES, OBSTACLES))
            if self.surf and self.surf_fields[fo]]
        hooks.log(f'  [blastfoam] VTK output ({", ".join(fams)}) into '
                  f'{self.vtk_dir}'
                  + (f' - WSL deletes off ({NO_DELETE_ENV})'
                     if self.no_delete else ''))

    # ── what the backend and the loop tell it ──
    def protect(self, name, why='read'):
        """Never delete written time `name`: finalize re-reads it. `why`
        keys the reason, so releasing one (the pin candidate moving on)
        never releases a write kept for another (a snapshot)."""
        if name is not None:
            self._protect.setdefault(str(name), set()).add(why)

    def unprotect(self, name, why='read'):
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
        return os.path.join(self.vtk_dir, *rel.split('/'))

    def _once(self, kind, msg):
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
                for entry, t in vtk_series.read_series(path):
                    rel = posixpath.normpath(posixpath.join(
                        posixpath.dirname(srel), entry))
                    m = _T_FILE.fullmatch(posixpath.basename(rel))
                    if not m or _size(self._dest(rel)) <= 0:
                        continue
                    self.files[rel] = (kind, m.group(1))
                    self.series.setdefault(str(srel), {})[entry] = \
                        m.group(1)
        for rel, (kind, t) in self.files.items():
            if kind == VOLUMES:
                self.converted.add(t)
                self.copied.add(t)
        for fo, kind in ((VTK_SECTIONS, SECTIONS),
                         (VTK_OBSTACLES, OBSTACLES)):
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
        kinds = ([VOLUMES] if self.volumes_on else []) + [
            k for fo, k in ((VTK_SECTIONS, SECTIONS),
                            (VTK_OBSTACLES, OBSTACLES))
            if self.surf and self.surf_fields[fo]]
        for kind in kinds:
            rels = [r for r, (k, _t) in self.files.items() if k == kind]
            fams[kind] = dict(
                count=len(rels),
                times=sorted({self.files[r][1] for r in rels},
                             key=_time_key),
                series=sorted(s for s in self.series
                              if s.startswith(kind + '/')),
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
        return dict(fields=fields, cadence=cadence, families=fams,
                    not_converted=nc,
                    deleted_in_wsl=sorted(self.deleted, key=_time_key),
                    replay_incomplete=self.replay_incomplete)

    def _add_file(self, rel, kind, surface, field, t):
        self.files[rel] = (kind, t)
        srel = series_name(kind, surface, field)
        entry = posixpath.relpath(rel, posixpath.dirname(srel))
        self.series.setdefault(srel, {})[entry] = t
        self.changed.add(srel)
        self._dirty = True

    def _fail(self, family, t, kind, why, path):
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
        names = []
        if self.volumes_on:
            self._convert(done, final)
            self._copy_volumes(final)
            # owner decision P9 (2026-09-27): a 1D run never deletes a
            # written time - 1D picks its snapshots at finalize from the
            # writes on disk (backend._pick_snapshots), and 1D writes are
            # small. Converted VTK/ files are still removed after the copy.
            if self.keep_time_dirs:
                names = []
            else:
                names = [n for n in self._plan(done)
                         if n not in self.deleted]
        if self.surf:
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
        rel = volume_file_name(self.spec.case_posix, name)
        return os.path.join(self.spec.case_unc, *rel.split('/'))

    def _todo(self, done):
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
        try:
            return self.runner(self.spec, names, self.vol_fields)
        except Exception as exc:        # noqa: BLE001 - recorded, retried
            self._finished(names, False, f'foamToVTK did not start: {exc}')
            return None

    def _finished(self, names, ok, detail):
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
                       f'vtk/{dest_name(VOLUMES, None, None, n)}')

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
                        path=f'vtk/{dest_name(VOLUMES, None, None, n)}')
                self._dirty = True
                break

    def _n_cells(self):
        try:
            return int(self.spec.n_cells or 0)
        except (AttributeError, TypeError, ValueError):
            return 0

    def _copy_one(self, src, rel):
        """Copy `src` to vtk\\<rel> and verify it; None, or why not."""
        dst = self._dest(rel)
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            self.copy(src, dst)
            want, got = os.path.getsize(src), os.path.getsize(dst)
        except OSError as exc:
            why = f'copy failed: {exc}'
        else:
            if got > 0 and got == want:
                return None
            why = ('the copy is empty' if got <= 0 else
                   f'the copy holds {got} of {want} bytes')
        try:
            os.remove(dst)              # never leave a torn file behind
        except OSError:
            pass
        return why

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
            rel = dest_name(VOLUMES, None, None, n)
            while True:
                why = self._copy_one(self._src_volume(n), rel)
                if why is None:
                    self.copied.add(n)
                    self._add_file(rel, VOLUMES, None, None, n)
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

    def _plan(self, done):
        names = [str(n) for n in done]
        if not vtk_purge_plan(names, self.converted, self.copied, names,
                              self.spec.start_dir, self.reconstructed,
                              self.protected,
                              getattr(self.spec, 'n_procs', 1)):
            return []
        ordered, mesh = self._mesh_listing(set(names))
        return vtk_purge_plan(names, self.converted, self.copied, names,
                              self.spec.start_dir, self.reconstructed,
                              self.protected,
                              getattr(self.spec, 'n_procs', 1),
                              mesh_dirs=mesh, ordered=ordered)

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
                    self._fail(kind, t, 'copy', why, f'vtk/{kind}')
                    if self._gave_up(kind, t, final):
                        break

    def _sweep_one(self, kind, fields, tdir, t):
        try:
            files = sorted(os.listdir(tdir))
        except OSError as exc:
            return f'cannot list the sample: {exc}'
        got = []
        for f in files:
            sp = split_surface_file(f, fields)
            if sp is None:
                return f'unexpected file {f}'
            field, surface = sp
            rel = dest_name(kind, surface, field, t)
            why = self._copy_one(os.path.join(tdir, f), rel)
            if why:
                return f'{f}: {why}'
            got.append((rel, kind, surface, field, t))
        for args in got:
            self._add_file(*args)
        return None

    # ── 5: the index, then the delete ──
    def _write_index(self):
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
                                 'nothing copied is lost')
            return
        self.rm_files.difference_update(files)
        self.rm_surface.difference_update(surf)
        if names:
            self.deleted.update(names)
            self._dirty = True
            self._write_index()

    def _summary(self):
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
