"""blastFoam backend entry points (phased bring-up).

Signatures mirror the native solvers exactly
(`solve_1d_foam(case, hooks=None) -> Result`) and the returned Result
reproduces the native per-dim shapes, so the GUI results panel, gauge
writers, profile export and chain remap work unchanged.

The run loop itself (stdout pumping, time-dir polling and ordered
ingest, stop -> writeNow -> kill escalation, adaptive writeInterval,
cleanup) lives in `runloop.FoamRunLoop`; each `solve_*_foam` here is
preflight -> per-dim read/frame callbacks -> `FoamRunLoop.run()` ->
`finalize_*`. Shared domain geometry (open-edge masks, stop distances,
snapshot radii) is `core.geometry`.

`IMPLEMENTED` gates pre-flight validation so a not-yet-available dim
errors while editing the form instead of at launch.
"""

import os
import re
import threading
import time as _time

import numpy as np

from ...core.bc import normalize_bc
from ...core import geometry, refine
from ...core.constants import P_AIR, RHO_AIR
from ..hooks import Result, RunHooks, StoppedBeforeStart
from . import env, reader, runner, writer
from .materials import MATERIALS
from .runloop import (ARRIVAL_P, BENIGN_WARN, FoamRunLoop, PeakImpulse,
                      due_sparse, new_live)
from .runloop import amr_note, level_counts
from ..hooks import frame_budget

#: dims with a working blastFoam backend (grows per phase)
IMPLEMENTED = frozenset({1, 2, 3})


def _stop_check(hooks, where):
    """Raise if the user has asked to stop before the solver exists."""
    if hooks.should_stop():
        raise StoppedBeforeStart(f'stopped before start ({where})')


def _check_available_stoppable(hooks, poll=0.25):
    """The WSL/blastFoam probe, logged and interruptible.

    `env.check_available` can take minutes on a cold WSL start (3
    retries x up to 90 s). Run straight, it left the user staring at a
    cleared log and a dead Stop button; here it runs on a helper thread
    while the caller polls `should_stop`. The probe thread is left to
    finish on its own - it only fills env's cache."""
    hooks.log('  [blastfoam] checking WSL / blastFoam availability...')
    box = {}

    def probe():
        box['res'] = env.check_available()

    th = threading.Thread(target=probe, daemon=True)
    th.start()
    while th.is_alive():
        _stop_check(hooks, 'WSL availability check')
        th.join(poll)
    ok, detail = box.get('res', (False, 'availability check did not run'))
    if not ok:
        raise RuntimeError(f"blastFoam backend unavailable: {detail}")
    hooks.log(f'  [blastfoam] {detail}')


def _mesh_stages(spec, hooks):
    """[(log label, shell command)] for the mesh/charge-init pipeline.

    -noRefine: v1 keeps the mesh uniform (grid already sized to resolve
    the charge), so no refiner configuration is needed. Parallel runs
    initialize serially, then decompose: the global mass normalization
    of sphericalMassToCell is trivially correct that way, and
    decomposePar distributes the initialized fields."""
    stages = [('meshing (blockMesh)', 'blockMesh')]
    if spec.obstacles:
        # carve the obstacle boxes: cellSet 'fluid' (boxes inverted),
        # keep it, exposed faces land on the 'obstacles' wall patch
        carve = (f'carving {len(spec.obstacles)} obstacle box(es) '
                 f'({int(spec.solid.sum()):,} cells)')
        stages += [(f'{carve} - topoSet', 'topoSet'),
                   (f'{carve} - subsetMesh',
                    'subsetMesh fluid -patch obstacles -overwrite')]
    # local refinement: one topoSet + refineMesh pass per level, coarse
    # to fine (each pass re-selects on the current mesh); the charge is
    # initialised afterwards on the final mesh, and the cell centres are
    # written (serial, before any decomposition) so the reader can match
    # the mesh against core.refine's prediction
    for lv in (range(1, spec.lmax + 1) if not spec.amr else ()):
        lbl = (f'refining level {lv} '
               f'({spec.dx_base / 2 ** lv:.4g} m cells)')
        stages += [(f'{lbl} - topoSet',
                    f'topoSet -dict system/topoSetDict.refine{lv}'),
                   (f'{lbl} - refineMesh',
                    f'refineMesh -dict system/refineMeshDict.{lv} '
                    f'-overwrite')]
    if not spec.charges:
        # profile-initialised stage (N7): the state IS the initial
        # condition, so setRefinedFields is skipped entirely (it would
        # overwrite alpha with the dict's defaultFieldValues). The
        # state lands here rather than with the rest of the case: it is
        # nonuniform over the final cells, and subsetMesh/refineMesh
        # read every field they find at the mesh they start from, so an
        # earlier write aborts them on the count mismatch (T62)
        stages.append(('writing the remapped state', writer.write_deferred))
    elif spec.amr:
        # dynamic AMR (N16): setRefinedFields refines the charge region
        # to `maxRefinement` at t = 0 and writes the hexRef cellLevel the
        # run-time refiner continues from - the static path's -noRefine
        # would leave the charge on the base grid
        stages.append((f'charge init + t = 0 refinement to level '
                       f'{spec.amr} (setRefinedFields)',
                       'setRefinedFields'))
    else:
        stages.append(('charge init (setRefinedFields)',
                       'setRefinedFields -noRefine'))
    if spec.lmax or spec.amr:
        # the start dir, which a profile stage names t0, not 0 (N7)
        stages.append(('writing cell centres (writeCellCentres)',
                       'postProcess -func writeCellCentres '
                       f'-time {spec.start_dir}'))
    if spec.n_procs > 1:
        # a profile stage's fields live at t0, not 0 (N7)
        stages.append((f'decomposing for {spec.n_procs} MPI ranks',
                       'decomposePar -force'
                       + ('' if not spec.t_start else ' -latestTime')))
    return stages


def build_remap(spec, hooks):
    """Refined mesh -> fine-grid gather map. Reads the cell centres the
    mesh stages wrote (0/C), matches them against the predicted
    structure and stores `spec.remap` / `spec.n_cells_actual`. Any
    mismatch is fatal (the case dir is kept for inspection): silently
    mis-mapping cells would put values in the wrong place. Dynamic-AMR
    runs take the per-time path instead (`mesh_at` on the 0/ dir)."""
    if spec.amr:
        return _build_remap_amr(spec, hooks)
    try:
        C = reader.read_cell_centres(spec.case_unc, spec.start_dir)
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f'refined mesh: cannot read cell centres 0/C ({exc}) - case '
            f'kept at {spec.case_unc}') from exc
    ids = refine.fine_src(spec.levels, spec.lmax, spec.solid)
    try:
        spec.remap = refine.match_cells(C[:, :spec.dim], spec.grid, ids)
    except RuntimeError as exc:
        raise RuntimeError(
            f'blastFoam refined mesh does not match the refinement plan: '
            f'{exc} - case kept at {spec.case_unc}') from exc
    spec.n_cells_actual = int(len(C))
    for f in ('Cx', 'Cy', 'Cz'):        # C itself stays for post-mortem
        try:
            os.remove(os.path.join(spec.case_unc, '0', f))
        except OSError:
            pass
    hooks.log(f'  [blastfoam] refined mesh: {len(C):,} cells matched the '
              f'predicted structure ({spec.lmax} level(s), finest '
              f'{spec.dx:.5g} m, displayed on a '
              f'{" x ".join(str(n) for n in spec.levels.shape)} grid)')


def part_counts(spec, dpath):
    """Cells per part of a decomposed time, learned from each part's own
    `C` (memoised per time: every field read needs the same numbers, and
    a rank whose field happens to be `uniform` cannot report its own
    count). None for an ordinary single-directory time."""
    if not isinstance(dpath, (list, tuple)):
        return None
    key = tuple(dpath)
    memo = getattr(spec, '_part_n', None)
    if memo is None:
        memo = spec._part_n = {}
    if key not in memo:
        memo[key] = [len(reader.read_vector(os.path.join(d, 'C'), None))
                     for d in dpath]
    return memo[key]


def rd_scalar(spec, dpath, field, n_cells):
    """One scalar field of a time, whole or concatenated across ranks."""
    if isinstance(dpath, (list, tuple)):
        return np.concatenate([
            reader.read_scalar(os.path.join(d, field), k)
            for d, k in zip(dpath, part_counts(spec, dpath))])
    return reader.read_scalar(os.path.join(dpath, field), n_cells)


def rd_vector(spec, dpath, field, n_cells):
    """One vector field of a time, whole or concatenated across ranks."""
    if isinstance(dpath, (list, tuple)):
        return np.concatenate([
            reader.read_vector(os.path.join(d, field), k)
            for d, k in zip(dpath, part_counts(spec, dpath))])
    return reader.read_vector(os.path.join(dpath, field), n_cells)


def first_part(dpath):
    """The part that stands for the whole time dir (existence checks)."""
    return dpath[0] if isinstance(dpath, (list, tuple)) else dpath


def mesh_at(spec, dpath):
    """Dynamic AMR (N16): the structure of ONE written time dir - a
    core.refine.MeshMap built from that dir's cell centres `C` (the
    writeCellCentres function object) and `cellLevel` (dumpLevel), or
    None on a static mesh so callers fall back to `spec.remap` exactly
    as before. At t = 0 (no cellLevel field yet) the hexRef labelList
    `polyMesh/cellLevel` that setRefinedFields wrote is used, and a base
    mesh without one is level 0 throughout. Torn files raise ValueError
    (the ingest loop retries next poll); a mesh that does not tile the
    display grid raises RuntimeError (fatal, case kept)."""
    if not spec.amr:
        return None
    C = rd_vector(spec, dpath, 'C', None)
    parts = dpath if isinstance(dpath, (list, tuple)) else [dpath]
    ns = part_counts(spec, dpath) or [len(C)]
    lv_chunks = []
    for d, k in zip(parts, ns):
        lv_path = os.path.join(d, 'cellLevel')
        if os.path.isfile(lv_path):
            lv_chunks.append(reader.read_scalar(lv_path, k))
            continue
        pm = os.path.join(d, 'polyMesh', 'cellLevel')
        chunk = (reader.read_label_list(pm) if os.path.isfile(pm)
                 else np.zeros(k, dtype=np.int64))
        if len(chunk) != k:
            raise ValueError(f'{pm}: {len(chunk)} levels for {k} cells')
        lv_chunks.append(chunk)
    lv = np.concatenate(lv_chunks) if len(lv_chunks) > 1 else lv_chunks[0]
    return refine.remap_from_centres(C[:, :spec.dim], lv, spec.grid,
                                     spec.display_level, spec.solid)


def _build_remap_amr(spec, hooks):
    """AMR twin of build_remap: read the start-time mesh (charge refined
    by setRefinedFields), keep its MeshMap on `spec.mesh0` for the
    initial frames and record the starting cell count. A profile stage
    starts at t0, not 0, and has no cellLevel there at all - mesh_at
    reads that as level 0 throughout, which is what its base mesh is
    (T70)."""
    d0 = os.path.join(spec.case_unc, spec.start_dir)
    try:
        mm = mesh_at(spec, d0)
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f'AMR mesh: cannot read the cell centres / levels of '
            f'{spec.start_dir} ({exc}) - case kept at '
            f'{spec.case_unc}') from exc
    except RuntimeError as exc:
        raise RuntimeError(
            f'AMR mesh at t = {spec.start_dir} does not tile the display '
            f'grid: {exc} - case kept at {spec.case_unc}') from exc
    spec.mesh0 = mm
    spec.n_cells_actual = int(mm.n_cells)
    for f in ('Cx', 'Cy', 'Cz'):        # C itself stays for post-mortem
        try:
            os.remove(os.path.join(d0, f))
        except OSError:
            pass
    hooks.log(f'  [blastfoam] AMR mesh at t = {spec.start_dir}: '
              f'{mm.n_cells:,} cells '
              f'({level_counts(mm.counts)}), displayed on a '
              f'{" x ".join(str(n) for n in mm.remap.shape)} grid at '
              f'level {spec.display_level} ({spec.dx:.5g} m)')


def _preflight(case, hooks):
    _check_available_stoppable(hooks)
    from ...core.case import validate_case
    rep = validate_case(case)
    if not rep.ok:
        raise ValueError("Invalid blastFoam case:\n  "
                         + "\n  ".join(rep.errors))
    _stop_check(hooks, 'before writing the case')
    # effective rank count: 1D always serial; auto stays serial for
    # small grids (decompose overhead beats the speed-up there)
    plan = writer.plan_case(case)
    # AMR runs go parallel too since T42 (N16-b): reconstructPar still
    # cannot follow a changing mesh, so those runs are ingested straight
    # from processor*/ instead of being reconstructed.
    n_procs = 1 if case.dim == 1 else env.resolve_nprocs(
        getattr(case, 'n_procs', 0), plan.n_cells,
        dim=case.dim, amr=plan.amr)
    # the live-sample cadence follows the GUI's "Refresh every N steps"
    # from the first step (the run loop re-syncs it on later changes)
    spec = writer.write_case(
        case, n_procs=n_procs,
        live_steps=writer.live_steps_for(hooks.refresh, case.dim))
    hooks.log(f"  [blastfoam] case directory: {spec.case_unc}")
    # one wsl call per stage (not one `&&` chain): that is what lets a
    # Stop land between stages and kill the running one, and it lets the
    # log name the stage the user is actually waiting on
    out = []
    for label, cmd in _mesh_stages(spec, hooks):
        _stop_check(hooks, label)
        hooks.log(f'  [blastfoam] {label}...')
        if callable(cmd):       # a Python stage, e.g. write_deferred
            cmd(spec)
            continue
        out.append(runner.run_stage_stoppable(
            spec.case_posix, cmd, should_stop=hooks.should_stop))
    # scanned once over every stage's output, as when this was a single
    # `&&` chain: the benign wedge warnings collapse into one note
    # instead of one per stage that emits them
    _scan_stage_warnings('\n'.join(out), hooks)
    _scan_set_mass('\n'.join(out), hooks, spec)
    if spec.lmax or spec.amr:
        build_remap(spec, hooks)
    return spec


#: setFields/setRefinedFields report what the charge region actually
#: got. 3D and planar meshes print "Set volume of cell: <V> m^3"; the
#: collapsed wedge/sector meshes (1D, 2D axisym) print the sector volume
#: and then the domain-equivalent one, "<sector> m^3 (<full> actual)".
#: The domain-equivalent number is the one to compare with the charge:
#: mass = V x rho0 is the staircase deposit the run starts from (N5/T39).
_RE_SET_VOLUME = re.compile(
    r'Set volume of cell:\s*([0-9.eE+-]+)\s*m\^3'
    r'(?:\s*\(\s*([0-9.eE+-]+)\s*actual\))?')


def _scan_set_mass(out, hooks, spec):
    """Forward blastFoam's own set-volume line as a [note] with the mass
    it implies and how that compares with the requested charge."""
    rho0 = MATERIALS[spec.material].rho0
    requested = [m for _c, m in (spec.charges or [])]
    for i, (plain, actual) in enumerate(_RE_SET_VOLUME.findall(out)):
        try:
            v = float(actual or plain)
        except ValueError:
            continue
        mass = v * rho0
        want = requested[i] if i < len(requested) else None
        tail = (f' ({mass / want:.2f} of the {want:g} kg requested)'
                if want else '')
        hooks.log(f'  [note] blastFoam set {mass:.4g} kg of explosive'
                  f'{tail}')


def _scan_stage_warnings(out, hooks):
    """Surface FOAM warnings from the mesh/init stages (their output
    is otherwise discarded on success): benign sector-wedge warnings
    collapse into one note, anything else is logged with its message."""
    msgs = re.findall(
        r'--> FOAM Warning :[^\n]*\n'
        r'(?:\s*From [^\n]*\n)?(?:\s*in file[^\n]*\n)?\s*([^\n]+)', out)
    benign = [m for m in msgs if any(s in m for s in BENIGN_WARN)]
    other = [m for m in msgs if not any(s in m for s in BENIGN_WARN)]
    if benign:
        hooks.log('  [blastfoam] note: benign wedge-geometry warnings '
                  'from the sector mesh (collapsed apex / ~1e-16 '
                  'planarity round-off) - expected, harmless')
    for m in other:
        hooks.log(f'  [foam] mesh-stage Warning: {m.strip()}')


#: consecutive live-slice samples refused before we say so. A sample
#: caught mid-write is refused legitimately and the next poll succeeds;
#: a face count that never matches means the live view is dead for the
#: rest of the run, which used to happen in complete silence (A7).
SURFACE_CANARY_TRIES = 20


def _surface_refused(spec, got, want):
    """Count a refused live-slice sample; log ONE line once the refusals
    stop looking like a mid-write race. Always returns None, so callers
    can `return _surface_refused(...)`."""
    n = getattr(spec, 'surface_bad', 0) + 1
    spec.surface_bad = n
    hooks = getattr(spec, 'hooks', None)
    if (hooks is not None and n >= SURFACE_CANARY_TRIES
            and not getattr(spec, 'surface_canary', False)):
        spec.surface_canary = True
        hooks.log(f'  [warn] live slice disabled: surface has {got} '
                  f'faces, expected {want} - the live view will stop '
                  f'updating (written times are unaffected)')
    return None


def _surface_ok(spec, value):
    """A sample decoded: clear the refusal streak."""
    spec.surface_bad = 0
    return value


def _decode_surface(spec, tdir, shape, ax_u, ax_v, slice_mask=None,
                    remap_sl=None):
    """One liveSlice raw sample -> grid-shaped p array or None while
    mid-write. The plane cuts one face per cell (interpolate and
    triangulate are off), so sorting the rows by their in-plane
    coordinates (ax_v primary, ax_u secondary) lands them in the
    native x-fastest cell order. `slice_mask` (obstacle-carved 3D
    meshes) marks the solid cells of the sampled layer: the sample
    then holds only that layer's fluid cells, which are scattered
    around the mask; solid cells display ambient pressure. `remap_sl`
    (refined meshes: the plane's slice of spec.remap) maps each sampled
    row - a cut-polygon centroid, i.e. the cell centre in-plane - to its
    foam cell via the fine cell it falls in, then gathers per fine cell
    so coarse cells show as blocks."""
    data = reader.read_surface_sample(spec.case_unc, writer.LIVE_SLICE,
                                      tdir)
    if data is None:
        return None
    pts, vals = data
    if remap_sl is not None:
        dxf = float(spec.dx)
        iu = np.clip(np.floor(pts[:, ax_u] / dxf).astype(int), 0,
                     shape[0] - 1)
        iv = np.clip(np.floor(pts[:, ax_v] / dxf).astype(int), 0,
                     shape[1] - 1)
        cells = remap_sl[iu, iv]
        fluid = remap_sl >= 0
        want = len(np.unique(remap_sl[fluid]))
        if (cells < 0).any() or len(vals) != want:
            return _surface_refused(spec, len(vals), want)
        val = np.full(int(spec.n_cells), np.nan)
        val[cells] = vals
        out = np.where(fluid, val[np.maximum(remap_sl, 0)], float(P_AIR))
        if np.isnan(out).any():
            return None
        return _surface_ok(spec, out)
    if slice_mask is None:
        if len(vals) != shape[0] * shape[1]:
            return _surface_refused(spec, len(vals), shape[0] * shape[1])
        order = np.lexsort((pts[:, ax_u], pts[:, ax_v]))
        return _surface_ok(spec, vals[order].reshape(shape, order='F'))
    fluid = ~slice_mask
    if len(vals) != int(fluid.sum()):
        return _surface_refused(spec, len(vals), int(fluid.sum()))
    # boolean-mask assignment fills in C order (ax_v fastest), so sort
    # ax_u primary / ax_v secondary to match
    order = np.lexsort((pts[:, ax_v], pts[:, ax_u]))
    full = np.full(shape, float(P_AIR))
    full[fluid] = vals[order]
    return _surface_ok(spec, full)


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


def _final_read(hooks, names, t_of, read):
    """Re-read the newest ingested time dir, degrading to the previous
    write when it is torn.

    `time_ready` only checks that the field files exist and the ingest
    loops content-verify `p` alone, so a stop that escalated to
    `run.kill()` mid final write leaves a dir that passes readiness but
    whose alpha/T/U/rho is half-written. Finalizing straight off it used
    to raise and throw away every good frame of the run.

    Returns `(kept_names, value)` with `kept_names[-1]` the dir the read
    succeeded on; raises RuntimeError when nothing is readable."""
    kept = list(names)
    while True:
        try:
            return kept, read(kept[-1])
        except (ValueError, OSError) as exc:
            if len(kept) == 1:
                raise RuntimeError(
                    f'blastFoam final write (t = {t_of(kept[-1])*1e3:.3f} '
                    f'ms) is unreadable and no earlier write survived '
                    f'- case kept on disk') from exc
            hooks.log(f'  [blastfoam] final write '
                      f'{t_of(kept[-1])*1e3:.3f} ms unreadable - using '
                      f'previous write {t_of(kept[-2])*1e3:.3f} ms')
            kept.pop()


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
                **{k: probes[k] for k in ('speeds', 'rhos') if k in probes},
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
            f'  Write interval  : {spec.write_interval*1e3:.4f} ms '
            f'(initial, adaptive)',
            f'  Live profile    : p(r) sampled every '
            f'{spec.live_steps or writer.live_sample_steps(1)} steps',
            bar, ''):
        hooks.log(line)


def resume_run(case_dir, hooks=None, adaptive_write=True):
    """Continue a STOPPED blastFoam run from its last written time (N6).

    Rebuilds the spec the way postmortem does (case.json + render_case +
    the on-disk cell centres for a refined mesh), resets the controlDict
    a stop left behind (`stopAt writeNow` -> `endTime`) and points
    `startFrom` at `latestTime`, then re-enters the ordinary solve with
    that spec. Nothing else is special-cased: the shared run loop's
    ingest is disk-driven and ordered, so it first replays the times the
    stopped run wrote - rebuilding the accumulators, snapshots and
    recorded frames exactly as a live run would have - and then follows
    the solver's new writes. blastProbes appends a new chunk at the
    restart time and `reader.read_probes` already merges restart chunks,
    and the per-step FO accumulation fields (pMax/impulse) restart from
    the state stored in the latest time dir, so gauges and peak maps
    come out as one continuous run. Returns the merged Result."""
    hooks = hooks or RunHooks()
    posix, unc = env.case_paths(case_dir)
    cj = os.path.join(unc, 'case.json')
    if not os.path.isfile(cj):
        raise FileNotFoundError(
            f'no case.json in {unc} - this run predates post-mortem '
            f'support and cannot be resumed')
    from ...core.case import load_case
    case = load_case(cj)

    alive = env.run_is_alive(posix)
    if alive:
        raise RuntimeError(f'{posix} is still running - stop it before '
                           f'resuming')
    if alive is None:
        raise RuntimeError(f'cannot ask WSL whether {posix} is still '
                           f'running - not resuming blind')

    n_procs = max(1, _n_procs_on_disk(unc))
    spec = writer.render_case(
        case, n_procs=n_procs,
        live_steps=writer.live_steps_for(hooks.refresh, case.dim))
    spec.case_posix, spec.case_unc = posix, unc
    spec.files = None                   # everything is already on disk
    spec.adaptive_write = bool(adaptive_write)
    if spec.lmax or spec.amr:
        # a profile-initialised stage keeps its mesh at t0, not 0 (T70)
        if not os.path.isfile(os.path.join(unc, spec.start_dir, 'C')):
            raise RuntimeError(
                f'{unc} is a locally refined run without '
                f'{spec.start_dir}/C (cell centres) - cannot rebuild the '
                f'remap to resume')
        build_remap(spec, hooks)

    times = [n for _t, n in reader.list_times(spec.time_root())
             if float(_t) > 0 or n == '0']
    if len(times) < 1:
        raise RuntimeError(f'{unc} has no written times to resume from')

    # a Stop leaves `stopAt writeNow` in the runTimeModifiable dict -
    # a resumed solver would exit immediately; and the run must pick up
    # at the last written time, not t = 0
    if not runner.rewrite_control_entry(posix, unc, 'stopAt', 'endTime',
                                        log=hooks.log):
        raise RuntimeError('could not reset stopAt in the controlDict')
    if not runner.rewrite_control_entry(posix, unc, 'startFrom',
                                        'latestTime', log=hooks.log):
        raise RuntimeError('could not set startFrom latestTime')
    hooks.log(f'  [blastfoam] resuming {posix} from its latest written '
              f'time ({len(times)} already on disk'
              + (f', {n_procs} MPI ranks' if n_procs > 1 else '') + ')')

    solve = {1: solve_1d_foam, 2: solve_2d_foam, 3: solve_3d_foam}[case.dim]
    return solve(case, hooks, adaptive_write=adaptive_write, spec=spec)


def _n_procs_on_disk(case_unc):
    n = 0
    while os.path.isdir(os.path.join(case_unc, f'processor{n}')):
        n += 1
    return n


def solve_1d_foam(case, hooks=None, adaptive_write=True, spec=None):
    """Run a Case1D on blastFoam. Returns a Result shaped exactly like
    the native solve_1d.

    `adaptive_write=False` pins writeInterval for the whole run - see
    CaseSpec.adaptive_write (B23); a caller-supplied `spec` skips the
    preflight (resume, N6/T43 - see solve_2d_foam)."""
    hooks = hooks or RunHooks()
    if spec is None:
        spec = _preflight(case, hooks)
    spec.adaptive_write = bool(adaptive_write)
    spec.hooks = hooks              # the live-slice canary logs through it
    # blastFoam cannot emit a frame per step: the live view moves at the
    # live-sample cadence, or at writeInterval without one (G7)
    hooks.cadence(dt=spec.write_interval,
                  steps=spec.live_steps or writer.live_sample_steps(case.dim))
    r = spec.grid['r']
    # T is in the readiness tuple because finalize_1d re-reads it
    fields = ('p', 'rho', 'U', 'T', f'alpha.{spec.phase}')

    # T60: only a TERMINATE outer boundary ends the run
    terminates = normalize_bc(
        getattr(case, 'bc_outer', 'terminate')) == 'terminate'
    _log_banner_1d(hooks, case, spec)
    hooks.run_started(dict(dim=1, r=r, radius_m=case.radius_m,
                           # T53: gauge radii for the live pane
                           gauges=[(n + 1, float(g), 0.0) for n, g
                                   in enumerate(case.gauge_radii
                                                or [])]))
    _initial_frame(spec, hooks)

    store = {}                      # dirname -> dict(t, p, rho, u)

    def read_dir(name, dpath):
        t, _dt = reader.read_time(dpath)
        return dict(
            t=t,
            p=reader.read_scalar(os.path.join(dpath, 'p'), spec.n_cells),
            rho=reader.read_scalar(os.path.join(dpath, 'rho'),
                                   spec.n_cells),
            u=reader.read_vector(os.path.join(dpath, 'U'),
                                 spec.n_cells)[:, 0])

    def on_frame(name, dpath, entry):
        store[name] = entry
        st, live = loop.st, loop.live
        # shock-front position: real progress for the bar and for
        # the adaptive-interval controller
        shocked = entry['p'] > ARRIVAL_P
        r_front = float(r[shocked].max()) if shocked.any() else 0.0
        st['frac'] = min(1.0, r_front / float(r[-1]))
        loop.maybe_adapt(len(store))
        will_pause = hooks.exec_will_pause()
        due = (due_sparse(hooks.refresh, st['step'], live)
               and entry['t'] >= st['t_frame'])
        if due or will_pause:
            hooks.frame(np.array([r, entry['p']]), entry['t'])
            st['t_frame'] = entry['t']
            live['step'] = st['step']
            live['draw'] = _time.time()
        if not loop.stop_requested and terminates \
                and entry['p'][-1] > ARRIVAL_P:
            loop.request_stop('shock arrived at outer boundary '
                              f"(p_last = {entry['p'][-1]:.3e} Pa)")
        loop.note_pause(will_pause)
        loop.gated_step()

    def decode_line(tdir):
        data = reader.read_line_sample(spec.case_unc, writer.LIVE_SET,
                                       tdir)
        # the line's endpoints sit a quarter-cell inside the apex and
        # outlet cells, so lineCell drops those two cells and a
        # complete profile has exactly n_cells - 2 rows; anything
        # shorter is a mid-write file (or a stale 9p view of one)
        if data is None or len(data[0]) < spec.n_cells - 2:
            return None
        return np.array([data[0], data[1]])

    loop = FoamRunLoop(spec, hooks, fields, store, writer.LIVE_SET,
                       decode_line, read_dir, on_frame)
    stop_reason = loop.run()
    return finalize_1d(case, spec, store, hooks, stop_reason,
                       loop.st['step'])


#: W2 (P1-2): every stop except the solver reaching its own endTime goes
#: through `stopAt writeNow`, and blastProbes flushes what it has buffered
#: only in the function-object destructors at a graceful End. The run loop
#: already waits up to 10 s for that End before its safety-net kill, but a
#: solver that is killed - or one whose End lands after the wait - takes
#: the tail with it (measured: 5 of ~600 samples, with or without a resume).
#: A real fix needs a foam-side flush knob, so until then the run says so.
_NATURAL_END = ('safety cap', 'end time reached')


def note_gauge_tail(hooks, stop_reason):
    """One line after `Stopped:` when the gauge record can be short."""
    if stop_reason in _NATURAL_END:
        return
    hooks.log('  [note] the run was stopped before its end time, so the '
              'last few gauge\n'
              '         samples may be missing (blastFoam flushes buffered '
              'probe samples\n'
              '         only at a graceful End; measured: 5 of ~600). Peaks '
              'and arrival\n'
              '         times already recorded are unaffected - the impulse '
              'tail is what\n'
              '         comes up short.\n')


def finalize_1d(case, spec, store, hooks, stop_reason, n_steps):
    """Build the exact native-shaped 1D Result from ingested time-dir
    entries (also used by postmortem.load_run)."""
    m = MATERIALS[spec.material]
    r = spec.grid['r']
    names = sorted(store, key=lambda n: store[n]['t'])

    def read_final(name):
        dfin = os.path.join(spec.case_unc, name)
        alpha = reader.read_scalar(
            os.path.join(dfin, f'alpha.{spec.phase}'), spec.n_cells)
        phase = (alpha > 0.5).astype(int)
        e_path = os.path.join(dfin, 'e')
        if os.path.isfile(e_path):
            e_arr = reader.read_scalar(e_path, spec.n_cells)
        else:                       # reconstruct from temperature
            T = reader.read_scalar(os.path.join(dfin, 'T'), spec.n_cells)
            e_arr = np.where(phase == 1, m.Cv_products,
                             writer.CV_AIR) * T
        return phase, e_arr

    names, (phase, e_arr) = _final_read(
        hooks, names, lambda n: store[n]['t'], read_final)
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

    final_profile = dict(t=fin['t'], r=r.copy(), rho=fin['rho'].copy(),
                         u=fin['u'].copy(), e=e_arr, p=fin['p'].copy(),
                         phase=phase, charge_kg=case.charge_kg,
                         eos='JWL', r_exp=spec.r_exp,
                         radius_m=case.radius_m)

    hooks.log(f"\n  Done. {n_steps} solver steps, t_final = "
              f"{fin['t']*1e3:.3f} ms")
    hooks.log(f"  Stopped: {stop_reason}\n")
    note_gauge_tail(hooks, stop_reason)
    hooks.frame(np.array([r, fin['p']]), fin['t'])

    meta = dict(final_profile=final_profile, r=r, radius_m=case.radius_m,
                charge_kg=case.charge_kg, eos='JWL', r_exp=spec.r_exp,
                solver='blastfoam', material=spec.material,
                case_dir=spec.case_unc)
    return Result(snapshots, _gauges_from_probes(spec), meta,
                  stop_reason, stop_reason == 'stopped by user')


# ── 2D ──────────────────────────────────────────────────────────────────────


def read_2d(dpath, spec, what=('p',), mesh=None):
    """Read fields of one time dir onto the native (Nx,Ny) layout.
    Obstacle-carved cells read back as still ambient. `mesh` is the
    dir's own MeshMap on a dynamic-AMR run (see `mesh_at`)."""
    out = {}
    n = spec.n_cells if mesh is None else mesh.n_cells
    if 'p' in what:
        out['p'] = reader.to_grid(rd_scalar(spec, dpath, 'p', n), spec,
                                  fill=P_AIR, mesh=mesh)
    if 'rho' in what:
        out['rho'] = reader.to_grid(rd_scalar(spec, dpath, 'rho', n), spec,
                                    fill=RHO_AIR, mesh=mesh)
    if 'U' in what:
        flat = rd_vector(spec, dpath, 'U', n)
        out['u'] = reader.to_grid(flat[:, 0], spec, mesh=mesh)
        out['v'] = reader.to_grid(flat[:, 1], spec, mesh=mesh)
    return out


def _refine_lines(spec):
    """Banner lines for a locally refined mesh ([] when uniform)."""
    if spec.amr:
        disp = ' x '.join(str(n) for n in spec.levels.shape)
        lines = [f'  Dynamic AMR     : up to level {spec.amr} '
                 f'({spec.dx_base / 2 ** spec.amr:g} m cells); displayed at '
                 f'level {spec.display_level} ({disp} grid at {spec.dx:g} m)',
                 f'  Mesh cells      : {spec.n_cells:,} at t = '
                 f'{spec.start_dir} (follows the shock)']
        # T70: a profile stage starts on the base mesh - the refiner has
        # nothing to refine until the run steps, so the base cell is what
        # the hand-off is resampled onto, however deep the AMR goes
        if spec.init_state is not None:
            lines.append(f'  Initial state   : written on the '
                         f'{spec.dx_base:g} m base mesh, refined from '
                         f'there')
            dx_src = float(spec.init_state.get('dx_src') or 0.0)
            if dx_src and spec.dx_base > 2.0 * dx_src:
                lines.append(f'  [warn] the profile was solved at '
                             f'{dx_src:g} m: this base cell coarsens it '
                             f'{spec.dx_base / dx_src:.1f}x at the '
                             f'hand-off - lower the base cell size')
        return lines
    if not spec.lmax:
        return []
    lv = np.asarray(spec.levels)
    dim = lv.ndim
    counts = np.bincount(lv.ravel().astype(np.int64), minlength=spec.lmax + 1)
    per = []
    for l in range(1, spec.lmax + 1):
        n_l = int(counts[l]) // (2 ** (dim * (spec.lmax - l)))
        per.append(f'L{l} {spec.dx_base / 2 ** l:g} m: {n_l:,}')
    disp = ' x '.join(str(n) for n in lv.shape)
    return [f'  Refinement      : {spec.lmax} level(s) - ' + ', '.join(per)
            + ' cells',
            f'  Mesh cells      : {spec.n_cells:,}  (displayed on the '
            f'{disp} grid at {spec.dx:g} m)']


def _source_lines(case, spec, charge_lbl):
    """Where the run's initial state comes from: the charge, or - for a
    chain stage fed by a profile (N7) - the file and the instant it was
    captured at. `case.charge` is meaningless for the latter (it keeps
    whatever the form last held), so it is not printed there."""
    if spec.init_state is None:
        return [f'  Charge          : {charge_lbl}',
                f'  Explosive radius: {spec.r_exp:.4f} m']
    src = os.path.basename(getattr(case, 'profile_file_in', '') or '?')
    return [f'  Initialised from: {src} at t = {spec.t_start * 1e3:.3f} ms',
            f'  Source charge   : explosive radius {spec.r_exp:.4f} m '
            f'({spec.material})']


def _log_banner_2d(hooks, case, spec, n_gauges, has_term):
    m = MATERIALS[spec.material]
    bar = '=' * 60
    bc_lbl = ", ".join(f"{k}={v}" for k, v in case.bcs.items())
    x0, y0, _ = spec.center
    axisym = case.geometry == 'axisymmetric'
    charge_lbl = None if spec.init_state is not None else (
        f'{case.charge:g} kg {spec.material} (sphere) on axis '
        f'at height {y0:g} m' if axisym else
        f'{case.charge:g} kg {spec.material} per metre '
        f'(infinite cylinder) at ({x0:g}, {y0:g}) m')
    for line in (
            '', bar, f'  2D Blast - blastFoam (WSL) ({case.geometry})',
            bar,
            *_source_lines(case, spec, charge_lbl),
            (f'  Domain          : {case.Lx:g} x {case.Ly:g} m,  cell '
             f'{spec.dx:g} m  ({spec.nx} x {spec.ny} = '
             f'{spec.n_cells:,} cells)') if not (spec.lmax or spec.amr)
            else
            (f'  Domain          : {case.Lx:g} x {case.Ly:g} m,  base '
             f'cell {spec.dx_base:g} m  ({spec.nb[0]} x {spec.nb[1]} '
             f'base cells)'),
            *_refine_lines(spec),
            '  EOS             : JWL products + ideal-gas air '
            f'(vDet {m.vDet:g} m/s)',
            f'  Boundaries      : {bc_lbl}'
            + ('  (x_lo = symmetry axis)' if axisym else ''),
            f'  Obstacles       : {len(spec.obstacles)}'
            + (' (carved out of the mesh, rigid walls)'
               if spec.obstacles else ''),
            f'  Gauges          : {n_gauges}',
            '  Stop condition  : '
            + ('shock arrival at a terminate boundary' if has_term
               else 'safety cap (no terminate boundaries)'),
            f'  Safety cap      : {spec.end_time*1e3:.1f} ms',
            f'  Write interval  : {spec.write_interval*1e3:.4f} ms '
            f'(initial, adaptive)',
            f'  Live slice      : p sampled every '
            f'{spec.live_steps or writer.live_sample_steps(2)} steps'
            + (' + every written time (AMR)' if spec.amr else ''),
            bar, ''):
        hooks.log(line)


def solve_2d_foam(case, hooks=None, adaptive_write=True, spec=None):
    """Run a Case2D on blastFoam (axisymmetric wedge or planar slab).
    Returns a Result shaped exactly like the native solve_2d.

    `adaptive_write=False` pins writeInterval for the whole run - see
    CaseSpec.adaptive_write (B23). A caller-supplied `spec` skips the
    preflight entirely - that is how `resume_run` re-enters a case whose
    directory, mesh and earlier writes already exist (N6/T43): the
    ingest below is disk-driven and ordered, so it first chews through
    the times the stopped run wrote and then follows the new ones."""
    hooks = hooks or RunHooks()
    if spec is None:
        spec = _preflight(case, hooks)
    spec.adaptive_write = bool(adaptive_write)
    spec.hooks = hooks              # the live-slice canary logs through it
    # blastFoam cannot emit a frame per step: the live view moves at the
    # live-sample cadence, or at writeInterval without one (G7)
    hooks.cadence(dt=spec.write_interval,
                  steps=spec.live_steps or writer.live_sample_steps(case.dim))
    g = spec.grid
    x_c, y_c = g['x_c'], g['y_c']
    Nx, Ny = spec.nx, spec.ny
    x0, y0, _ = spec.center
    bcs = dict(case.bcs)
    axisym = case.geometry == 'axisymmetric'
    solid = (spec.solid if spec.solid is not None
             else np.zeros((Nx, Ny), dtype=bool))

    # terminate-boundary edge mask + distances (native logic, solver2d):
    # the axisymmetric x_lo is the symmetry axis, carved cells read back
    # as ambient
    term_edge = geometry.terminate_edge_mask(
        (Nx, Ny), bcs, fluid=~solid,
        sides=geometry.SIDES_2D if not axisym else ('x_hi', 'y_lo', 'y_hi'))
    has_term = term_edge.any()
    trig_k, trig_cell = _trigger_cells(case, (x_c, y_c), (Nx, Ny))
    trigger = {}
    d_charge = geometry.d_charge_2d(x_c, y_c, x0, y0)
    dists = geometry.stop_dists_2d(case.Lx, case.Ly, x0, y0, bcs,
                                   x_lo_counts=not axisym)
    stop_dist = min(dists)
    snap_radii = geometry.snap_radii(spec.r_exp, dists, case.n_snapshots)

    _log_banner_2d(hooks, case, spec, len(spec.probe_pts), has_term)
    run_info = dict(
        dim=2, x_face=g['x_face'], y_face=g['y_face'], solid=solid,
        xlabel='r [m]' if axisym else 'x [m]',
        ylabel='z [m]' if axisym else 'y [m]', title='',
        # T53: what the user asked for (the probes snap in the mesh)
        gauges=[(n + 1, float(pt[0]), float(pt[1]))
                for n, pt in enumerate(case.gauges or [])],
        mesh_src=(refine.slice_src(spec.levels, spec.lmax,
                                   solid_fine=spec.solid)
                  if spec.lmax and not spec.amr else None),
        display_level=spec.display_level if spec.amr else None)
    if axisym:
        # live (r, z) frames can be revolved into a 3D cylinder view
        run_info['revolve3d'] = dict(
            r_c=x_c, z_c=y_c, solid=solid, bcs=bcs,
            obstacles=[tuple(o) for o in spec.obstacles],
            z0=y0, r_exp=spec.r_exp, R=case.Lx, Lz=case.Ly)
    hooks.run_started(run_info)
    _initial_frame(spec, hooks)

    record_frames = frame_budget(case.record_frames, Nx * Ny, hooks,
                                 amr=bool(spec.amr))
    frame_t, frame_p, frame_lv = [], [], []
    # T is in the readiness tuple because finalize_2d re-reads it;
    # AMR runs add the per-time mesh files (C, cellLevel)
    fields = ('p', 'rho', 'U', 'T', f'alpha.{spec.phase}') + spec.mesh_fields
    ingested = {}               # dirname -> t (full arrays NOT retained)
    snap_names = []
    acc = PeakImpulse()         # per-write Python + per-step FO accumulators
    slice_solid = solid if solid.any() else None

    def read_dir(name, dpath):
        t, _dt = reader.read_time(first_part(dpath))
        mesh = mesh_at(spec, dpath)         # None on a static mesh
        return t, read_2d(dpath, spec, mesh=mesh)['p'], mesh

    def on_frame(name, dpath, payload):
        nonlocal frame_t, frame_p, frame_lv
        t, p, mesh = payload
        if not acc.add(p, t, dpath, spec, hooks, mesh=mesh):
            return False
        ingested[name] = t
        st, live = loop.st, loop.live
        if mesh is not None:
            hooks.log(amr_note(mesh, st.get('n_prev'), t))
            st['n_prev'] = mesh.n_cells

        shocked = p > ARRIVAL_P
        r_front = float(d_charge[shocked].max()) if shocked.any() \
            else 0.0
        st['frac'] = min(1.0, r_front / stop_dist)
        loop.maybe_adapt(len(ingested))
        while snap_radii and r_front >= snap_radii[0]:
            snap_radii.pop(0)
            if name not in snap_names:
                snap_names.append(name)
                hooks.log(f"  Snapshot saved: t = {t*1e3:.3f} ms  "
                          f"(front at {r_front:.2f} m)")
        if record_frames > 0:
            frame_t.append(t)
            frame_p.append(p.astype(np.float32))
            if mesh is not None:
                frame_lv.append(mesh.levels)
            # thin AT the requested count, not at twice it: holding 2x
            # was half a gigabyte on a 640^2 AMR run, and nobody asked
            # for more frames than record_frames anyway
            if len(frame_p) > record_frames:
                frame_t = frame_t[::2]
                frame_p = frame_p[::2]
                frame_lv = frame_lv[::2]
        will_pause = hooks.exec_will_pause()
        due = (due_sparse(hooks.refresh, st['step'], live)
               and t >= st['t_frame'])
        if due or will_pause:
            _emit_frame(hooks, p, t, mesh)
            st['t_frame'] = t
            live['step'] = st['step']
            live['draw'] = _time.time()
        if trig_k is not None and not trigger \
                and p[trig_cell] > ARRIVAL_P:
            trigger.update(
                _trigger_fire(loop, hooks, case, trig_k, t,
                              float(p[trig_cell])),
                time_dir=name)
        if not loop.stop_requested and has_term \
                and (p[term_edge] > ARRIVAL_P).any():
            loop.request_stop('shock arrived at a terminate boundary '
                              f'(p_edge = {p[term_edge].max():.3e} Pa)')
        loop.note_pause(will_pause)
        loop.gated_step()
        return True

    if spec.amr:
        # AMR: the rows carry no cell size; their centres pin the level
        # and the sample tiles the display grid like a written mesh
        decode = lambda tdir: _decode_surface_amr(          # noqa: E731
            spec, tdir, 0, 1, (g['x_face'], g['y_face']), slice_solid)
    else:
        decode = lambda tdir: _decode_surface(              # noqa: E731
            spec, tdir, (Nx, Ny), 0, 1, slice_solid, remap_sl=spec.remap)
    loop = FoamRunLoop(spec, hooks, fields, ingested, writer.LIVE_SLICE,
                       decode, read_dir, on_frame)
    stop_reason = loop.run()
    return finalize_2d(case, spec, hooks, stop_reason, loop.st['step'],
                       ingested, snap_names, frame_t, frame_p,
                       record_frames, acc, frame_lv=frame_lv,
                       trig_k=trig_k, trigger=trigger)


def finalize_2d(case, spec, hooks, stop_reason, n_steps, ingested,
                 snap_names, frame_t, frame_p, record_frames, acc,
                 frame_lv=None, trig_k=None, trigger=None):
    """Build the exact native-shaped 2D Result via a two-pass snapshot
    re-read (also used by postmortem.load_run).

    `trig_k` / `trigger` are the T51 trigger-gauge index and record from
    the run loop; postmortem.load_run has neither (it never watched the
    run) and passes nothing."""
    m = MATERIALS[spec.material]
    g = spec.grid
    x_c, y_c = g['x_c'], g['y_c']
    x0, y0, _ = spec.center
    bcs = dict(case.bcs)
    solid = (spec.solid if spec.solid is not None
             else np.zeros((spec.nx, spec.ny), dtype=bool))

    names = sorted(ingested, key=ingested.get)

    # final_state for save_profile_2d -> 3D remap: e from T (per-phase
    # Cv - blastFoam writes no e field), phase from the products alpha
    def read_final(name):
        dpath = spec.time_dirs(name)
        mesh = mesh_at(spec, dpath)
        n = spec.n_cells if mesh is None else mesh.n_cells
        got = read_2d(dpath, spec, ('p', 'rho', 'U'), mesh=mesh)
        alpha = reader.to_grid(
            rd_scalar(spec, dpath, f'alpha.{spec.phase}', n),
            spec, fill=0.0, mesh=mesh)
        phase = (alpha > 0.5).astype(int)
        T = reader.to_grid(rd_scalar(spec, dpath, 'T', n), spec,
                           fill=writer.T_AMB, mesh=mesh)
        return got, phase, np.where(phase == 1, m.Cv_products,
                                    writer.CV_AIR) * T, mesh

    names, (fin, phase, e_arr, mesh_fin) = _final_read(
        hooks, names, ingested.get, read_final)
    fin_name = names[-1]
    dfin = spec.time_dirs(fin_name)
    snap_names = [n for n in snap_names if n in names]

    snapshots = {}
    for name in snap_names:
        if name == fin_name:
            continue
        dp = spec.time_dirs(name)
        got = read_2d(dp, spec, ('p', 'rho', 'U'), mesh=mesh_at(spec, dp))
        t = ingested[name]
        label = f"t = {t*1e3:.3f} ms"
        if label not in snapshots:
            snapshots[label] = dict(
                p=got['p'], rho=got['rho'],
                speed=np.sqrt(got['u'] ** 2 + got['v'] ** 2))
    t_fin = ingested[fin_name]
    snapshots[f"t = {t_fin*1e3:.3f} ms (final)"] = dict(
        p=fin['p'], rho=fin['rho'],
        speed=np.sqrt(fin['u'] ** 2 + fin['v'] ** 2))

    if record_frames > 0 and (not frame_t or frame_t[-1] < t_fin):
        frame_t.append(t_fin)
        frame_p.append(fin['p'].astype(np.float32))
        if mesh_fin is not None and frame_lv is not None:
            frame_lv.append(mesh_fin.levels)
    _emit_frame(hooks, fin['p'], t_fin, mesh_fin)

    hooks.log(f"\n  Done. {n_steps} solver steps, t_final = "
              f"{t_fin*1e3:.3f} ms")
    hooks.log(f"  Stopped: {stop_reason}\n")
    note_gauge_tail(hooks, stop_reason)

    probes = reader.read_probes(spec.case_unc) if spec.probe_pts else None
    if probes:
        gauge_out = dict(times=probes['times'],
                         points=[(pt[0], pt[1])
                                 for pt in probes['points']],
                         pressures=probes['pressures'],
                         **{k: probes[k] for k in ('speeds', 'rhos') if k in probes})
    else:
        gauge_out = dict(times=np.array([]), points=[], pressures=[])

    meta = dict(x_c=x_c, y_c=y_c,
                x_face=g['x_face'], y_face=g['y_face'],
                solid=solid, geometry=case.geometry,
                Lx=case.Lx, Ly=case.Ly, dx=spec.dx,
                eos='JWL', bcs=bcs,
                obstacles=[tuple(o) for o in spec.obstacles],
                charge=case.charge, charge_center=(x0, y0),
                r_exp=spec.r_exp, from_profile=False,
                solver='blastfoam', material=spec.material,
                # what the USER asked for; gauge_out['points'] is where
                # the probes landed in the mesh (QA-33)
                gauges=[tuple(float(v) for v in g)
                        for g in (case.gauges or [])],
                case_dir=spec.case_unc, refine=spec.refine_meta())
    # per-step FO peak/impulse maps, falling back to the per-write Python
    # accumulator (B17: same policy as 3D)
    (meta['p_peak'], meta['impulse'],
     meta['peak_source']) = acc.final(fin['p'], dfin, t_fin, spec,
                                      mesh=mesh_fin)
    meta['final_state'] = dict(t=t_fin, rho=fin['rho'], u=fin['u'],
                               v=fin['v'], e=e_arr, p=fin['p'],
                               phase=phase)
    # T51: the trigger's own instant, read back from its time dir when
    # the action asked for a remap the run did not stop at
    meta['trigger_gauge'] = None if trig_k is None else trig_k + 1
    if trigger:
        trigger = dict(trigger)
        tname = trigger.pop('time_dir', None)
        meta['trigger'] = trigger
        if 'remap' in trigger['action'] and tname:
            if tname == fin_name:
                meta['trigger_state'] = meta['final_state']
            else:
                try:
                    tg, tphase, te, _m = read_final(tname)
                    meta['trigger_state'] = dict(
                        t=float(trigger['t']), rho=tg['rho'], u=tg['u'],
                        v=tg['v'], e=te, p=tg['p'], phase=tphase)
                except Exception as exc:      # noqa: BLE001
                    hooks.log(f"  [warn] trigger remap state could not "
                              f"be read from time dir {tname}: {exc}")
    if record_frames > 0:
        meta['frames'] = dict(times=np.array(frame_t), pressures=frame_p)
    _amr_meta(meta, spec, mesh_fin, frame_lv, record_frames)
    return Result(snapshots, gauge_out, meta, stop_reason,
                  stop_reason == 'stopped by user')


# ── 3D ──────────────────────────────────────────────────────────────────────


def _levels_of(mesh):
    """{'levels': ...} for a 3D viewer frame of a dynamic-AMR run, {}
    otherwise (static payloads stay exactly as before)."""
    return {} if mesh is None else {'levels': mesh.levels}


def _emit_frame(hooks, p, t, mesh, sl=None):
    """hooks.frame with the frame's AMR level map when there is one;
    static runs keep the two-argument call so custom hooks that only
    accept (field, t) stay compatible."""
    field = p if sl is None else p[sl].copy()
    if mesh is None:
        hooks.frame(field, t)
    else:
        hooks.frame(field, t,
                    levels=mesh.levels if sl is None else mesh.levels[sl])


def _trigger_cells(case, coords, shape):
    """T51: (index, cell) for the trigger gauge on a display grid, or
    (None, None). `coords` are the cell centres per axis; the gauge is
    snapped to its nearest cell exactly as the native solvers do."""
    n = getattr(case, 'trigger_gauge', None)
    gauges = list(case.gauges or [])
    if n in (None, 0, '') or not gauges:
        return None, None
    try:
        k = int(n) - 1
    except (TypeError, ValueError):
        return None, None
    if not 0 <= k < len(gauges):
        return None, None
    pt = tuple(float(v) for v in gauges[k])
    cell = tuple(int(np.argmin(np.abs(np.asarray(c) - pt[a])))
                 for a, c in enumerate(coords))
    if any(not 0 <= c < s for c, s in zip(cell, shape)):
        return None, None
    return k, cell


def _trigger_fire(loop, hooks, case, k, t, p_at):
    """Log the arrival and ask the run loop to stop when the action says
    so. Returns the trigger record for meta."""
    action = getattr(case, 'trigger_action', 'terminate') or 'terminate'
    pt = tuple(float(v) for v in list(case.gauges)[k])
    hooks.log(f"  Trigger gauge {k + 1} ("
              + ", ".join(f"{v:.4f}" for v in pt)
              + f") m reached at t = {t*1e3:.3f} ms (p = {p_at:.3e} Pa)")
    if 'terminate' in action and not loop.stop_requested:
        loop.request_stop(f'trigger gauge {k + 1} reached')
    return dict(t=float(t), gauge=k + 1, point=pt, action=action)


def _amr_meta(meta, spec, mesh_fin, frame_lv, record_frames):
    """Dynamic AMR: meta['refine'] carries the LAST written mesh's
    display-grid level map + cell count (the static payload holds the
    predicted map), and the recorded frames carry their per-frame level
    maps so "Show mesh" can follow the replay. No-op on static runs."""
    if not spec.amr or mesh_fin is None:
        return
    meta['refine'] = dict(meta.get('refine') or {}, levels=mesh_fin.levels,
                          n_cells=mesh_fin.n_cells, counts=mesh_fin.counts)
    if record_frames > 0 and frame_lv:
        meta.setdefault('frames', {})['levels'] = frame_lv


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


def read_3d(dpath, spec, what=('p',), mesh=None):
    """Read fields of one time dir onto the native (Nx,Ny,Nz) layout.
    Obstacle-carved cells (absent from the mesh) read back as still
    ambient: p_atm / air density / zero velocity. `mesh` is the dir's
    own MeshMap on a dynamic-AMR run (see `mesh_at`)."""
    out = {}
    n = spec.n_cells if mesh is None else mesh.n_cells
    if 'p' in what:
        out['p'] = reader.to_grid(rd_scalar(spec, dpath, 'p', n), spec,
                                  fill=P_AIR, mesh=mesh)
    if 'rho' in what:
        out['rho'] = reader.to_grid(rd_scalar(spec, dpath, 'rho', n), spec,
                                    fill=RHO_AIR, mesh=mesh)
    if 'U' in what:
        flat = rd_vector(spec, dpath, 'U', n)
        out['U'] = np.stack([reader.to_grid(flat[:, i], spec, mesh=mesh)
                             for i in range(3)], axis=-1)
    return out


def _decode_surface_amr(spec, tdir, ax_u, ax_v, faces_uv, slice_solid=None):
    """AMR twin of _decode_surface (N16): one liveSlice raw sample of a
    dynamic-AMR run -> (p on the display plane, level map) or None while
    the sample is mid-write. The rows are cut-face centroids (= in-plane
    cell centres); refine.levels_from_centres reads each cell's level
    off its centre and refine.remap_from_centres tiles the rows onto
    the display plane exactly as a written time's C + cellLevel are -
    a torn or incomplete sample fails its exact-cover check (or has a
    row no level fits) and is retried next poll. `faces_uv` are the
    plane's display-grid face coordinates, `slice_solid` the carved
    cells of the plane (or None)."""
    data = reader.read_surface_sample(spec.case_unc, writer.LIVE_SLICE,
                                      tdir)
    if data is None:
        return None
    pts, vals = data
    C = pts[:, (ax_u, ax_v)]
    fu, fv = (np.asarray(f, dtype=float) for f in faces_uv)
    lv = refine.levels_from_centres(C, (fu[0], fv[0]), spec.dx_base,
                                    spec.amr)
    if len(lv) == 0 or (lv < 0).any():
        return _surface_refused(spec, len(lv),
                                'a level for every cut face')
    try:
        mm = refine.remap_from_centres(C, lv, dict(x_face=fu, y_face=fv),
                                       spec.display_level, slice_solid)
    except (RuntimeError, ValueError):
        # rows missing: mid-write sample, or a mesh the plane no longer
        # covers exactly
        return _surface_refused(spec, len(vals), 'an exact cover of the '
                                                 'display plane')
    return _surface_ok(spec, (mm.gather(vals, P_AIR), mm.levels))


def _initial_frame(spec, hooks, live_sl=None):
    """Emit the t=0 field as the first live frame: the run's 0/p is
    written by the case writer (uniform ambient before activation), so
    the plot shows a live view immediately instead of staying empty
    until the first time directory lands."""
    try:
        p0 = reader.read_scalar(
            os.path.join(spec.case_unc, spec.start_dir, 'p'), spec.n_cells)
    except (OSError, ValueError):
        return
    t0 = spec.t_start
    if spec.dim == 1:
        hooks.frame(np.array([spec.grid['r'], p0]), t0)
    else:
        p0 = reader.to_grid(p0, spec, fill=P_AIR, mesh=spec.mesh0)
        hooks.frame(p0 if live_sl is None else p0[live_sl].copy(), t0)


def _initial_frame3d(spec, hooks):
    """Emit the t=0 state to an attached 3D viewer, mirroring
    _initial_frame for the plane: the first full write can be many
    solver steps in, and until then the 3D view would stay empty.
    The case's 0/ dir has no plain rho, so ambient density is used."""
    if not hooks.wants_frame3d():
        return
    try:
        p0 = reader.to_grid(reader.read_scalar(
            os.path.join(spec.case_unc, spec.start_dir, 'p'),
            spec.n_cells), spec, fill=P_AIR, mesh=spec.mesh0)
    except (OSError, ValueError):
        return
    rho0 = np.full_like(p0, RHO_AIR)
    e0 = p0 / (0.4 * rho0)
    hooks.frame3d(0.0, dict(p=p0, rho=rho0, e=e0, p_peak=p0.copy(),
                            imp=np.zeros_like(p0),
                            **_levels_of(spec.mesh0)))


def slice_geom_3d(case, spec):
    """Burst-plane + user live-slice indices (native conventions),
    shared by the live run loop and the finalizer/postmortem."""
    g = spec.grid
    x_c, y_c, z_c = g['x_c'], g['y_c'], g['z_c']
    x0, y0, z0 = spec.center
    j0 = int(np.argmin(np.abs(y_c - y0)))
    k0 = int(np.argmin(np.abs(z_c - z0)))
    slice_axis = getattr(case, 'slice_axis', 'y') or 'y'
    ax_i = 'xyz'.index(slice_axis)
    coords = (x_c, y_c, z_c)
    pos = ((x0, y0, z0)[ax_i] if getattr(case, 'slice_pos', None) is None
           else float(case.slice_pos))
    s0 = int(np.argmin(np.abs(coords[ax_i] - pos)))
    live_sl = tuple(s0 if a == ax_i else slice(None) for a in range(3))
    live_faces = {'x': (g['y_face'], g['z_face']),
                  'y': (g['x_face'], g['z_face']),
                  'z': (g['x_face'], g['y_face'])}[slice_axis]
    live_labels = {'x': ('y [m]', 'z [m]'), 'y': ('x [m]', 'z [m]'),
                   'z': ('x [m]', 'y [m]')}[slice_axis]
    live_title = f'{slice_axis} = {coords[ax_i][s0]:.2f} m'
    return (j0, k0, slice_axis, s0, live_sl, live_faces, live_labels,
            live_title)


def _log_banner_3d(hooks, case, spec, n_gauges, has_term):
    m = MATERIALS[spec.material]
    bar = '=' * 62
    bc_lbl = ", ".join(f"{k}={v}" for k, v in case.bcs.items())
    x0, y0, z0 = spec.center
    for line in (
            '', bar, '  3D Blast - blastFoam (WSL)', bar,
            *_source_lines(case, spec,
                           None if spec.init_state is not None else
                           f'{case.charge:g} kg {spec.material} (sphere)'),
            f'  Burst point     : ({x0:g}, {y0:g}, {z0:g}) m',
            f'  Domain          : {case.Lx:g} x {case.Ly:g} x '
            f'{case.Lz:g} m,  cell '
            f'{spec.dx if not (spec.lmax or spec.amr) else spec.dx_base:g} m'
            + (' (base)' if (spec.lmax or spec.amr) else ''),
            (f'  Grid            : {spec.nx} x {spec.ny} x {spec.nz} = '
             f'{spec.n_cells:,} cells'
             + (' (obstacle cells carved out)' if spec.obstacles else ''))
            if not (spec.lmax or spec.amr) else
            (f'  Grid            : {spec.nb[0]} x {spec.nb[1]} x '
             f'{spec.nb[2]} base cells'),
            *_refine_lines(spec),
            '  EOS             : JWL products + ideal-gas air '
            f'(vDet {m.vDet:g} m/s)',
            f'  Boundaries      : {bc_lbl}',
            f'  Obstacles       : {len(spec.obstacles)} '
            f'(carved out of the mesh, rigid walls)'
            if spec.obstacles else '  Obstacles       : 0',
            f'  Gauges          : {n_gauges}',
            '  Stop condition  : '
            + ('shock arrival at a terminate boundary' if has_term
               else 'safety cap (no terminate boundaries)'),
            f'  {"End time" if spec.cap_is_end else "Safety cap":<16}: '
            f'{spec.end_time*1e3:.1f} ms',
            f'  Write interval  : {spec.write_interval*1e3:.4f} ms '
            f'(initial, adaptive)',
            ('  Live slice      : p of every written time (AMR)'
             if spec.amr else '  Live slice      : p sampled every step'),
            bar, ''):
        hooks.log(line)


def solve_3d_foam(case, hooks=None, adaptive_write=True, spec=None):
    """Run a Case3D on blastFoam. Returns a Result shaped exactly like
    the native solve_3d (incl. viewer snapshots and frames).

    `adaptive_write=False` pins writeInterval for the whole run - see
    CaseSpec.adaptive_write (B23); a caller-supplied `spec` skips the
    preflight (resume, N6/T43 - see solve_2d_foam)."""
    hooks = hooks or RunHooks()
    if spec is None:
        spec = _preflight(case, hooks)
    spec.adaptive_write = bool(adaptive_write)
    spec.hooks = hooks              # the live-slice canary logs through it
    # blastFoam cannot emit a frame per step: the live view moves at the
    # live-sample cadence, or at writeInterval without one (G7)
    hooks.cadence(dt=spec.write_interval,
                  steps=spec.live_steps or writer.live_sample_steps(case.dim))
    g = spec.grid
    x_c, y_c, z_c = g['x_c'], g['y_c'], g['z_c']
    Nx, Ny, Nz = spec.nx, spec.ny, spec.nz
    dx = spec.dx
    x0, y0, z0 = spec.center
    bcs = dict(case.bcs)
    solid = (spec.solid if spec.solid is not None
             else np.zeros((Nx, Ny, Nz), dtype=bool))
    centers = spec.burst_points

    n_snapshots = case.n_snapshots
    n_disp = (spec.nx * spec.ny * spec.nz if (spec.lmax or spec.amr)
              else spec.n_cells)
    max_snaps = max(1, int(1.5e9 / (4 * n_disp)) - 1)
    if n_snapshots > max_snaps:
        hooks.log(f"  [note] n_snapshots reduced {n_snapshots} -> "
                  f"{max_snaps} to bound snapshot memory")
        n_snapshots = max_snaps

    # terminate-boundary edge mask + stop/snapshot distances (native
    # logic; carved cells read back as ambient, distances to the nearest
    # charge)
    term_edge = geometry.terminate_edge_mask((Nx, Ny, Nz), bcs,
                                             fluid=~solid)
    has_term = term_edge.any()
    trig_k, trig_cell = _trigger_cells(case, (x_c, y_c, z_c),
                                       (Nx, Ny, Nz))
    trigger = {}
    d_charge = geometry.d_charge_3d(x_c, y_c, z_c, centers)
    dists = geometry.stop_dists_3d(case.Lx, case.Ly, case.Lz, centers, bcs)
    stop_dist = min(dists)
    snap_radii = geometry.snap_radii(spec.r_exp, dists, n_snapshots)

    # burst-plane slice indices + user live slice (native conventions)
    (j0, k0, slice_axis, s0, live_sl, live_faces, live_labels,
     live_title) = slice_geom_3d(case, spec)

    _log_banner_3d(hooks, case, spec, len(spec.probe_pts), has_term)
    ax_i = 'xyz'.index(slice_axis)
    hooks.run_started(dict(
        dim=3, x_face=live_faces[0], y_face=live_faces[1],
        solid=solid[live_sl], xlabel=live_labels[0],
        ylabel=live_labels[1], title=live_title,
        gauges=geometry.plane_gauges(
            [tuple(float(v) for v in g) for g in (case.gauges or [])],
            live_sl, (x_c, y_c, z_c), dx),
        mesh_src=(refine.slice_src(spec.levels, spec.lmax, ax_i, s0,
                                   solid_fine=spec.solid)
                  if spec.lmax and not spec.amr else None),
        display_level=spec.display_level if spec.amr else None,
        scene3d=dict(x_c=x_c, y_c=y_c, z_c=z_c, dx=dx, solid=solid,
                     obstacles=[tuple(o) for o in spec.obstacles],
                     Lx=case.Lx, Ly=case.Ly, Lz=case.Lz,
                     charge_center=(x0, y0, z0), r_exp=spec.r_exp,
                     bcs=bcs, refine=spec.refine_meta())))
    _initial_frame(spec, hooks, live_sl)
    _initial_frame3d(spec, hooks)

    # the 3D record holds the live PLANE, not the volume
    record_frames = frame_budget(
        case.record_frames,
        solid[live_sl].size, hooks, amr=bool(spec.amr))
    frame_t, frame_p, frame_lv = [], [], []
    fields = ('p', 'rho', 'U', f'alpha.{spec.phase}') + spec.mesh_fields
    ingested = {}               # dirname -> t (full arrays NOT retained)
    snap_names = []             # dirs picked by front-radius crossings
    acc = PeakImpulse()         # per-write Python + per-step FO accumulators
    live3d = new_live()         # frame3d throttle (viewer refresh policy)
    uv = [a for a in range(3) if a != ax_i]
    lshape = tuple((Nx, Ny, Nz)[a] for a in uv)
    # the live-slice sample skips carved cells: pass that layer's
    # solid mask so the decoder scatters around it
    slice_solid = solid[live_sl] if solid.any() else None

    def read_dir(name, dpath):
        will_3d = (due_sparse(hooks.refresh3d, loop.st['step'], live3d)
                   or hooks.exec_will_pause()) and hooks.wants_frame3d()
        t, _dt = reader.read_time(first_part(dpath))
        mesh = mesh_at(spec, dpath)         # None on a static mesh
        got = read_3d(dpath, spec, ('p', 'rho') if will_3d else ('p',),
                      mesh=mesh)
        return t, got, will_3d, mesh

    def on_frame(name, dpath, payload):
        nonlocal frame_t, frame_p, frame_lv
        t, got, will_3d, mesh = payload
        p = got['p']
        if not acc.add(p, t, dpath, spec, hooks, mesh=mesh):
            return False
        ingested[name] = t
        st, live = loop.st, loop.live
        if mesh is not None:
            hooks.log(amr_note(mesh, st.get('n_prev'), t))
            st['n_prev'] = mesh.n_cells

        # shock-front progress + native snapshot scheduling
        shocked = p > ARRIVAL_P
        r_front = float(d_charge[shocked].max()) if shocked.any() \
            else 0.0
        st['frac'] = min(1.0, r_front / stop_dist)
        while snap_radii and r_front >= snap_radii[0]:
            snap_radii.pop(0)
            if name not in snap_names:
                snap_names.append(name)
                hooks.log(f"  Snapshot saved: t = {t*1e3:.3f} ms  "
                          f"(front at {r_front:.2f} m)")

        # adaptive writeInterval (runTimeModifiable controlDict)
        loop.maybe_adapt(len(ingested))

        if record_frames > 0:
            frame_t.append(t)
            frame_p.append(p[live_sl].astype(np.float32))
            if mesh is not None:
                frame_lv.append(mesh.levels[live_sl])
            # thin AT the requested count, not at twice it: holding 2x
            # was half a gigabyte on a 640^2 AMR run, and nobody asked
            # for more frames than record_frames anyway
            if len(frame_p) > record_frames:
                frame_t = frame_t[::2]
                frame_p = frame_p[::2]
                frame_lv = frame_lv[::2]
        will_pause = hooks.exec_will_pause()
        due = (due_sparse(hooks.refresh, st['step'], live)
               and t >= st['t_frame'])
        if due or will_pause:
            _emit_frame(hooks, p, t, mesh, live_sl)
            st['t_frame'] = t
            live['step'] = st['step']
            live['draw'] = _time.time()
        if will_3d:
            rho = got['rho']
            e_approx = p / (0.4 * np.maximum(rho, 1e-10))
            pk_live, imp_live = acc.live()
            hooks.frame3d(t, dict(p=p, rho=rho, e=e_approx,
                                  p_peak=pk_live, imp=imp_live,
                                  **_levels_of(mesh)))
            live3d['step'] = st['step']
            live3d['draw'] = _time.time()
        if trig_k is not None and not trigger \
                and p[trig_cell] > ARRIVAL_P:
            trigger.update(_trigger_fire(
                loop, hooks, case, trig_k, t,
                float(p[trig_cell])))
        if not loop.stop_requested and has_term \
                and (p[term_edge] > ARRIVAL_P).any():
            loop.request_stop('shock arrived at a terminate boundary '
                              f'(p_edge = {p[term_edge].max():.3e} Pa)')
        loop.note_pause(will_pause)
        loop.gated_step()
        return True

    if spec.amr:
        # AMR: the rows carry no cell size; their in-plane centres pin
        # the level and the sample tiles the display plane like a
        # written mesh (the writer cuts through a finest-level
        # sub-layer so no cell face lies on the plane)
        decode = lambda tdir: _decode_surface_amr(          # noqa: E731
            spec, tdir, uv[0], uv[1], live_faces, slice_solid)
    else:
        decode = lambda tdir: _decode_surface(              # noqa: E731
            spec, tdir, lshape, uv[0], uv[1], slice_solid,
            remap_sl=None if spec.remap is None else spec.remap[live_sl])
    loop = FoamRunLoop(spec, hooks, fields, ingested, writer.LIVE_SLICE,
                       decode, read_dir, on_frame)
    stop_reason = loop.run()
    if stop_reason == 'safety cap' and spec.cap_is_end:
        stop_reason = 'end time reached'

    return finalize_3d(case, spec, hooks, stop_reason, loop.st['step'],
                       ingested, snap_names, frame_t, frame_p,
                       record_frames, acc, frame_lv=frame_lv,
                       trig_k=trig_k, trigger=trigger)


def finalize_3d(case, spec, hooks, stop_reason, n_steps, ingested,
                 snap_names, frame_t, frame_p, record_frames, acc,
                 frame_lv=None, trig_k=None, trigger=None):
    """Build the exact native-shaped 3D Result via a two-pass snapshot
    re-read - bounds run-time memory (also used by postmortem).

    `trig_k` / `trigger`: see finalize_2d (3D is terminate-only, so
    there is no remap state to carry)."""
    g = spec.grid
    x_c, y_c, z_c = g['x_c'], g['y_c'], g['z_c']
    dx = spec.dx
    x0, y0, z0 = spec.center
    bcs = dict(case.bcs)
    solid = (spec.solid if spec.solid is not None
             else np.zeros((spec.nx, spec.ny, spec.nz), dtype=bool))
    j0, k0, slice_axis, s0, live_sl = slice_geom_3d(case, spec)[:5]

    names = sorted(ingested, key=ingested.get)

    def read_final(name):
        dpath = spec.time_dirs(name)
        mesh = mesh_at(spec, dpath)
        return read_3d(dpath, spec, ('p', 'rho', 'U'), mesh=mesh), mesh

    names, (fin, mesh_fin) = _final_read(
        hooks, names, ingested.get, read_final)
    fin_name = names[-1]
    snap_names = [n for n in snap_names if n in names]

    snapshots = {}
    for name in snap_names:
        if name == fin_name:
            continue
        dpath = spec.time_dirs(name)
        got = read_3d(dpath, spec, ('p', 'rho', 'U'),
                      mesh=mesh_at(spec, dpath))
        t = ingested[name]
        label = f"t = {t*1e3:.3f} ms"
        if label not in snapshots:
            snapshots[label] = _snapshot_payload(
                got['p'], got['rho'], got['U'], j0, k0, t)
    t_fin = ingested[fin_name]
    snapshots[f"t = {t_fin*1e3:.3f} ms (final)"] = _snapshot_payload(
        fin['p'], fin['rho'], fin['U'], j0, k0, t_fin)

    # final-dir FO fields (per-step accumulation) supersede the per-write
    # Python accumulator; a stale FO read does not (B17)
    p_peak, impulse, peak_source = acc.final(
        fin['p'], spec.time_dirs(fin_name), t_fin, spec,
        mesh=mesh_fin)
    if record_frames > 0 and (not frame_t or frame_t[-1] < t_fin):
        frame_t.append(t_fin)
        frame_p.append(fin['p'][live_sl].astype(np.float32))
        if mesh_fin is not None and frame_lv is not None:
            frame_lv.append(mesh_fin.levels[live_sl])
    _emit_frame(hooks, fin['p'], t_fin, mesh_fin, live_sl)
    e_approx = fin['p'] / (0.4 * np.maximum(fin['rho'], 1e-10))
    hooks.frame3d(t_fin, dict(p=fin['p'], rho=fin['rho'], e=e_approx,
                              p_peak=p_peak, imp=impulse,
                              **_levels_of(mesh_fin)), force=True)

    hooks.log(f"\n  Done. {n_steps} solver steps, t_final = "
              f"{t_fin*1e3:.3f} ms")
    hooks.log(f"  Stopped: {stop_reason}\n")
    note_gauge_tail(hooks, stop_reason)

    probes = reader.read_probes(spec.case_unc) if spec.probe_pts else None
    if probes:
        gauge_out = dict(times=probes['times'],
                         points=[tuple(pt) for pt in probes['points']],
                         pressures=probes['pressures'],
                         **{k: probes[k] for k in ('speeds', 'rhos') if k in probes})
    else:
        gauge_out = dict(times=np.array([]), points=[], pressures=[])

    meta = dict(x_c=x_c, y_c=y_c, z_c=z_c,
                x_face=g['x_face'], y_face=g['y_face'],
                z_face=g['z_face'], j0=j0, k0=k0,
                slice_axis=slice_axis, s0=s0,
                solid=solid, Lx=case.Lx, Ly=case.Ly, Lz=case.Lz, dx=dx,
                eos='JWL', bcs=bcs,
                obstacles=[tuple(o) for o in spec.obstacles],
                charge=case.charge, charge_center=(x0, y0, z0),
                r_exp=spec.r_exp, r_src=spec.r_exp, from_profile=None,
                solver='blastfoam', material=spec.material,
                # what the USER asked for; gauge_out['points'] is where
                # the probes landed in the mesh (QA-33)
                gauges=[tuple(float(v) for v in g)
                        for g in (case.gauges or [])],
                case_dir=spec.case_unc, refine=spec.refine_meta(),
                p_peak=p_peak, impulse=impulse, peak_source=peak_source)
    if record_frames > 0:
        meta['frames'] = dict(times=np.array(frame_t), pressures=frame_p)
    _amr_meta(meta, spec, mesh_fin, frame_lv, record_frames)
    # T51 (3D is terminate-only: no remap state to carry)
    meta['trigger_gauge'] = None if trig_k is None else trig_k + 1
    if trigger:
        meta['trigger'] = dict(trigger)
    return Result(snapshots, gauge_out, meta, stop_reason,
                  stop_reason == 'stopped by user')
