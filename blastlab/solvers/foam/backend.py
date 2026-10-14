"""blastFoam backend entry points (1D, 2D and 3D).

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
from ..hooks import (Result, RunHooks, StoppedBeforeStart, frame_budget,
                     trigger_index)
from . import dicts, env, reader, runner, writer
# part_counts/rd_scalar live in common.py since Phase 9 (runloop needs
# them without importing this module); re-exported, same objects
from .common import part_counts, rd_scalar
from .materials import MATERIALS
from .runloop import (ARRIVAL_P, BENIGN_WARN, STOP_UNSTABLE, FoamRunLoop,
                      PeakImpulse, WslVanished, amr_note, due_sparse,
                      level_counts, new_live)

#: dims with a working blastFoam backend
IMPLEMENTED = frozenset({1, 2, 3})

#: gamma_air - 1 as the literal 0.4 (NOT 1.4 - 1, which is not bit-equal):
#: ideal-gas specific energy e = p / ((gamma - 1) rho), the live-viewer
#: stand-in for the energy field (P2-2)
_AIR_GAMMA_M1 = 0.4
#: density floor (kg/m^3) so e = p / ((gamma - 1) rho) stays finite
_RHO_FLOOR = 1e-10


def _e_approx(p, rho):
    """Ideal-gas specific energy (J/kg) from p (Pa) and rho (kg/m^3)."""
    return p / (_AIR_GAMMA_M1 * np.maximum(rho, _RHO_FLOOR))


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
    if spec.n_procs > 1 and spec.amr and dicts.AMR_LOAD_BALANCE:
        # Parallel AMR rebalances the decomposition as the refined region
        # moves, and blastFoam's fvMeshBalance refuses to start without a
        # patch of type `internal` on the mesh:
        #   FOAM FATAL ERROR: When balancing is enabled, an internal patch
        #   should be added to the mesh ... "addEmptyPatch patchName
        #   internal -overwrite"   (fvMeshBalance.C:112)
        # It has to run after the fields exist (it patches their
        # boundaryField too) and before decomposePar. Without balancing a
        # 13-rank AMR run was measured at a 1:64 cell imbalance between
        # the busiest and idlest rank - most of the machine waiting.
        stages.append(('adding the internal patch for load balancing '
                       '(addEmptyPatch)',
                       'addEmptyPatch internal internal -overwrite'
                       + ('' if not spec.t_start else ' -latestTime')))
    if spec.n_procs > 1:
        # a profile stage's fields live at t0, not 0 (N7)
        stages.append((f'decomposing for {spec.n_procs} MPI ranks',
                       'decomposePar -force'
                       + ('' if not spec.t_start else ' -latestTime')))
    return stages


def _drop_centre_components(directory):
    """Delete the per-component cell-centre files Cx/Cy/Cz in `directory`."""
    for f in ('Cx', 'Cy', 'Cz'):        # C itself stays for post-mortem
        try:
            os.remove(os.path.join(directory, f))
        except OSError:
            pass


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
    _drop_centre_components(os.path.join(spec.case_unc, '0'))
    hooks.log(f'  [blastfoam] refined mesh: {len(C):,} cells matched the '
              f'predicted structure ({spec.lmax} level(s), finest '
              f'{spec.dx:.5g} m, displayed on a '
              f'{" x ".join(str(n) for n in spec.levels.shape)} grid)')


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
    _drop_centre_components(d0)
    hooks.log(f'  [blastfoam] AMR mesh at t = {spec.start_dir}: '
              f'{mm.n_cells:,} cells '
              f'({level_counts(mm.counts)}), displayed on a '
              f'{" x ".join(str(n) for n in mm.remap.shape)} grid at '
              f'level {spec.display_level} ({spec.dx:.5g} m)')


def _preflight(case, hooks):
    """Probe WSL, validate `case`, write the OpenFOAM case dir and return
    its spec (rank count resolved here; raises ValueError if invalid)."""
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
    hooks.scratch_posix = spec.case_posix      # OUT-1: foam\ copy + release
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
        # after every stage (decomposePar included: the ranks read the
        # root constant/phaseProperties) and before anything starts
        # blastFoam; not a stage, since stage commands are strings
        _fit_ignition(spec, hooks)
        build_remap(spec, hooks)
    return spec


def _fit_ignition(spec, hooks):
    """P1-23: a default ignition radius that lights no cell centre of the
    real t = 0 mesh (0/C, written by the mesh stages) is refitted to the
    nearest shell of centres (writer.fit_det_radii), so blastFoam does
    not abort with "No cells will be activated". Only the `radii` line of
    constant/phaseProperties changes, in `spec.files` and on disk; a
    radius that lights a cell leaves the file byte-identical.

    P2-22: explicit `det_radii` are the user's and are never refitted -
    one that lights no cell raises here, before blastFoam starts, with
    the point and the nearest centre (validation refuses only what the
    nominal lattice shows)."""
    rel = 'constant/phaseProperties'
    text = spec.files.get(rel, '')
    radii = writer.written_det_radii(text)
    points = spec.det_points or [c for c, _m in spec.charges]
    if not radii or len(radii) != len(points):
        return
    try:
        C = reader.read_cell_centres(spec.case_unc, spec.start_dir)
    except (OSError, ValueError):
        return                      # build_remap reports the same file
    new, fits = writer.fit_det_radii(points, radii, C)
    if not fits:
        return
    if spec.det_radii:
        i, old, _r, _n, d1 = fits[0]
        pt = ', '.join(f'{v:g}' for v in points[i])
        raise RuntimeError(
            f'detonation point {i + 1} ({pt}) m: the ignition radius '
            f'{old * 1e3:.4g} mm lights no cell of the t = 0 mesh - the '
            f'nearest cell centre is {d1 * 1e3:.4g} mm away, and blastFoam '
            f'would stop with "No cells will be activated". Set a radius '
            f'above {d1 * 1e3:.4g} mm, or leave the radii empty for the '
            f'default - case kept at {spec.case_unc}')
    spec.files[rel] = writer.with_det_radii(text, new)
    writer._write_files(spec, (rel,))
    for i, old, r, n_lit, d1 in fits:
        hooks.log(f'  [note] detonation point {i + 1}: the ignition radius '
                  f'{old * 1e3:.4g} mm lights no cell of the t = 0 mesh '
                  f'(nearest centre {d1 * 1e3:.4g} mm) - fitted to '
                  f'{r * 1e3:.4g} mm, {n_lit} cell(s) lit')


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


def _cell_index_uv(pts, ax_u, ax_v, dxf, shape):
    """In-plane (iu, iv) grid indices of sample points `pts` (m), clipped
    to `shape`; `dxf` is the finest cell size (m)."""
    iu = np.clip(np.floor(pts[:, ax_u] / dxf).astype(int), 0,
                 shape[0] - 1)
    iv = np.clip(np.floor(pts[:, ax_v] / dxf).astype(int), 0,
                 shape[1] - 1)
    return iu, iv


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
        iu, iv = _cell_index_uv(pts, ax_u, ax_v, dxf, shape)
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
    want = int(fluid.sum())
    if len(vals) == want:
        # boolean-mask assignment fills in C order (ax_v fastest), so
        # sort ax_u primary / ax_v secondary to match
        order = np.lexsort((pts[:, ax_v], pts[:, ax_u]))
        full = np.full(shape, float(P_AIR))
        full[fluid] = vals[order]
        return _surface_ok(spec, full)
    # N2-16: the python carve and foam's boxToCell can disagree by one
    # cell row when an obstacle face lands exactly on a cell-centre
    # line at this dx - measured on R2's obstacle case: every sample
    # carried 171,604 cells against a 171,580-cell mask, one 24-cell
    # row at the obstacle's top face. That is a STABLE count, not a
    # torn write, and refusing it silently killed the entire live path
    # for the whole run - the live view never updated and the live
    # arrival stop never saw an edge. A sample within a row's worth of
    # the expected count is placed by its coordinates instead (the
    # remap branch above already trusts coordinates); a genuinely
    # mid-write sample is short by far more and is still refused.
    # tolerance: 1% of the expected count. NOT a fixed floor - a first
    # cut used max(64, 1%) and test_foam_reader immediately objected: on
    # a 9-cell fixture that accepts a sample short by two rows, which IS
    # a torn write there. 1% covers the measured tie (24 of 171,580)
    # and rounds to zero on tiny grids, where the old strict behaviour
    # is the right one.
    if abs(len(vals) - want) > want // 100:
        return _surface_refused(spec, len(vals), want)
    dxf = float(getattr(spec, 'dx', 0) or 0)
    if not dxf > 0:
        return _surface_refused(spec, len(vals), want)
    iu, iv = _cell_index_uv(pts, ax_u, ax_v, dxf, shape)
    full = np.full(shape, float(P_AIR))
    full[iu, iv] = vals
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


def _arrival_pin(names, t_of, stop_reason, arrived, hooks):
    """N2-13: the write an arrival-stopped run should HAND ON, as
    opposed to wherever the solver had got to when Python noticed.

    The stop is `stopAt writeNow` requested by the ingest loop, and the
    ingest runs behind the solver (per-poll batch caps, the WSL 9p
    filesystem), so the overshoot past the arrival is WALL CLOCK: five
    runs of an identical chain fixture measured stage ends spread +/-7%
    (stage 1) and 2.3x (stage 2), which makes a chain unreproducible -
    every stage hands the next one a different state. The
    physics-determined instant is the first write at which the arrival
    criterion holds on the written data itself.

    ONLY the hand-off surface is pinned (1D final_profile, 2D
    final_state): gauges, snapshots, frames and the accumulated
    peak/impulse maps are OBSERVATIONS of the run that happened and
    keep their full record. (The first cut of this pinned the whole
    finalize - and an A/B report that straddled the edit promptly
    compared a full-length serial map against an arrival-length np2
    map, 45,803 cells vs 6,068. Observations and hand-offs are
    different things.)

    The pin is the last write BEFORE the arrival criterion holds. The
    crossing itself falls between scheduled writes and is detected on
    the live-sample cadence, so the only post-crossing write is usually
    the wall-clock-placed stopAt-writeNow one - measured on the isolated
    chain stage 1: identical detection in both runs (the stop reason
    carries p_last = 2.212e+06 Pa to the digit) yet writeNow states at
    1.318e-4 vs 1.150e-4 s. The last PRE-arrival write sits on the
    pinned schedule grid, so it is the same write in every identical
    run, whatever the overshoot - and physically it is the state the
    chain wants anyway: the shock still inside the domain, before any
    boundary interaction.

    Scans FORWARD for the first write at which `arrived` holds. A
    backward walk was tried first and is wrong: the criterion is NOT
    monotone over the whole record - the overshoot past arrival can be
    long (measured: detection at t = 5.2e-5 s, stopAt-writeNow landing
    at 1.16e-4 s, half the run again), and by then the boundary cell
    has vented back BELOW the arrival threshold, so the tail writes
    read arrived=False and the walk kept the wall-clock final write.
    Forward, the prefix is clean: quiet ... quiet, first arrived write,
    and the pin is the one before it. A predicate error aborts the pin
    (None) rather than guessing. Returns the pin name, or None when
    there is nothing usable (arrival on the very first write, or the
    criterion never holding on any write)."""
    if not str(stop_reason).startswith('shock arrived') or not names:
        return None
    first = None
    for i, name in enumerate(names):
        try:
            if arrived(name):
                first = i
                break
        except Exception:
            return None
    if not first:          # None (never arrived) or 0 (no quiet prefix)
        return None
    pin = names[first - 1]
    hooks.log(f'  [blastfoam] hand-off state pinned to the last write '
              f'before arrival, t = {t_of(pin)*1e3:.4f} ms '
              f'({len(names) - first} later write(s) remain part of '
              f'the run record) (N2-13)')
    return pin


def _track_pin(loop, pin, name, arrived):
    """OUT-2 (D1): keep the write `_arrival_pin` would pick on the VTK
    export's never-delete list while the run is still writing. That is the
    newest write whose arrival predicate is False, frozen at the first
    write where it holds (the forward scan's `names[first - 1]`); the
    candidate it replaces is released - for the pin only, so a write kept
    as a snapshot or trigger stays kept. `pin` is the caller's
    {'name', 'frozen'} state.

    The first write where it holds is kept too ('arrival'): a resume
    after deletion, and postmortem.load_run, re-run the forward scan on
    the writes left on disk, and the boundary can vent back below the
    threshold on later writes - without this one the replay never sees
    the arrival, never stops, and hands on the last write (D10)."""
    if pin['frozen']:
        return
    if arrived:
        pin['frozen'] = True
        loop.protect(name, 'arrival')
        return
    loop.unprotect(pin['name'], 'pin')
    pin['name'] = name
    loop.protect(name, 'pin')


def _arrived_2d_grid(pg, bcs):
    """The 2D arrival predicate on one write's `p` grid: any cell of a
    terminate side above ARRIVAL_P (finalize_2d's `arrived_2d`, and the
    run loop's on_frame for the OUT-2 cache)."""
    for side, sl in (('x_lo', np.s_[0, :]), ('x_hi', np.s_[-1, :]),
                     ('y_lo', np.s_[:, 0]), ('y_hi', np.s_[:, -1])):
        if bcs.get(side) == 'terminate' \
                and bool(np.any(pg[sl] > ARRIVAL_P)):
            return True
    return False


def _gauges_from_probes(spec, quiet=False):
    """blastProbes output -> the native gauges dict (1D: radii).
    `quiet`: the live read, see reader.read_probes."""
    empty = dict(times=np.array([]), radii=[], pressures=[])
    if not spec.probe_pts:
        return empty
    probes = reader.read_probes(spec.case_unc, quiet=quiet)
    if not probes:
        return empty
    radii = []
    for i, pt in enumerate(probes['points']):
        if np.isnan(pt[0]) and i < len(spec.gauge_ids):
            radii.append(float(spec.gauge_ids[i]))   # header fallback
        else:
            radii.append(float(pt[0]))               # snapped location
    return dict(times=probes['times'], radii=radii,
                **{k: probes[k] for k in reader.GAUGE_KEYS if k in probes},
                pressures=probes['pressures'])


#: how often the live gauge trace re-reads blastProbes' output. The file
#: is small - a few thousand rows - so a whole re-read costs less than
#: the bookkeeping an incremental tail would need, and it inherits
#: `read_probes`' merging of restart chunks for free. Throttled anyway,
#: because it is disk work on a path WSL shares with the solver.
GAUGE_LIVE_S = 1.0
_gauge_live = {'at': 0.0}


def _reset_gauge_live():
    """A run's first live gauge payload is due at once (D6): the
    throttle stamp is module state, and the last run's must not hold the
    next one back by up to GAUGE_LIVE_S."""
    _gauge_live['at'] = 0.0


def _emit_gauges(hooks, spec):
    """Hand the live gauge traces over, if anything is watching. Called
    with each emitted live frame - the written-time `on_frame` of 1D, 2D
    and 3D and the live-sample tail (D6; before it only 3D's `on_frame`
    did, so 1D and 2D gauges arrived only at the end)."""
    if not hooks.wants_gauges() or not spec.probe_pts:
        return
    now = _time.time()
    if now - _gauge_live['at'] < GAUGE_LIVE_S:
        return
    _gauge_live['at'] = now
    try:
        # quiet: a torn tail is the normal state of a file mid-write
        payload = _gauges_from_probes(spec, quiet=True)
    except Exception:
        return              # a probe file mid-write is not a run failure
    if payload and len(payload.get('times', ())):
        hooks.gauges(payload)


def _log_banner_1d(hooks, case, spec):
    """Log the run banner (mesh, charge, material) for a 1D blastFoam run."""
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
            _write_interval_line(spec),
            f'  Live profile    : p(r) sampled every '
            f'{spec.live_steps or writer.live_sample_steps(1)} steps',
            bar, ''):
        hooks.log(line)


#: P1-5: the per-step function objects whose fields blastFoam re-reads at
#: a restart. They are accumulators, so the restart CONTINUES them - which
#: is why an inconsistent one is fatal rather than ignorable.
#: OUT-4b: `impulseMax` (the Peak_Impulse fieldMinMax, writer.py) is one
#: too, written only when a VTK family asks for it.
_FO_FIELDS = ('pMax', 'impulse', 'impulseMax')


def _disable_fo_accumulators(spec, case, hooks):
    """Take the per-step pMax/impulse function objects out of a RESUMED
    AMR run, and say what that costs. Returns True when it applied.

    Measured on a reproduction of the owner's failure - a
    profile-initialised AMR stage stopped after 12 frames and resumed:

        Selected 17 cells for refinement out of 5138.
        Refined from 5138 to 5189 cells.
        --> FOAM Warning : fieldMinMax pMax cannot find required object p
        --> FOAM FATAL IO ERROR: size 5138 is not equal to the given
            value of 5189
        file: .../6.8841367e-05/pMax

    The written directory is not torn - mesh, p, pMax and impulse all
    hold 5138 values. The mismatch is made during the restart: `p` is not
    in the registry when the function objects are constructed, so they
    construct late, and by then the run-time refiner has already taken
    its first step and the mesh is 5189 cells. The FO then reads its
    stored 5138-value field onto that mesh and the solver dies before its
    first write. Deleting the stored fields does not help either - the FO
    then aborts with `pMax not found in table` (measured) - and nothing
    on our side can order the refiner against the FO construction.

    So the resumed leg runs without them. Peak and impulse are then
    tracked by the Python per-write accumulator, which covers the WHOLE
    run because the resume's ingest replays every write the stopped run
    left; the maps lose per-step resolution, not coverage, and
    `Result.meta['peak_source']` says so ('python-fallback'). A fresh run
    is untouched, and so is a resumed run on a fixed mesh, where the FOs
    restart correctly."""
    if not (spec.amr and spec.dim >= 2):
        return False                    # a fixed mesh restarts them fine
    spec.fo_accumulators = False
    path = os.path.join(spec.case_unc, 'system', 'controlDict')
    try:
        with open(path, 'w', encoding='ascii', newline='\n') as fh:
            fh.write(writer._controldict(spec, case))
    except OSError as exc:
        spec.fo_accumulators = True
        hooks.log(f'  [blastfoam] could not rewrite the controlDict for the '
                  f'resume ({exc}) - the run may abort on a mesh-size '
                  f'mismatch')
        return False
    hooks.log('  [blastfoam] the per-step pMax/impulse function objects are '
              'off for this resumed AMR run: blastFoam cannot restart them '
              'across a mesh change. Peak and impulse are accumulated per '
              'write instead (the whole run, including everything before '
              'the stop) - see peak_source in the result.')
    # OUT-2 (D4): the rewritten controlDict samples no pMax / impulse on
    # the VTK surfaces either (writer.vtk_surface_fields)
    surf = spec.vtk_surfaces or {}
    dropped = sorted({f for k in ('fields', 'obstacle_fields')
                      for f in surf.get(k, ())} & set(_FO_FIELDS))
    if dropped:
        hooks.log(f'  [blastfoam] VTK sections/obstacles: '
                  f'{" and ".join(dropped)} are not written for this resumed '
                  f'AMR leg (the function objects are off)')
    # OUT-4a: the same for the gauge impulse trace (writer.probe_fields)
    if 'impulse' in (spec.gauge_fields or ()):
        hooks.log('  [blastfoam] VTK gauges: impulse is not recorded for '
                  'this resumed AMR leg (the function object is off)')
    return True


def _time_is_whole(spec, name):
    """Can blastFoam restart from time `name`? (ok, detail)

    A write is only usable as a restart point when every field in it has
    the same number of values as that write's own mesh. On a dynamic-AMR
    run the accumulating function objects can miss a mesh update and land
    at the previous cell count, and the solver then dies on the FIRST
    read - `size 5138 is not equal to the given value of 5189` - before
    it has taken a step. The write's own cell centres (writeCellCentres,
    one per time dir on an AMR run) are the authority on how many cells
    it has; `p` stands in when they are absent (a uniform-mesh run, where
    the count cannot drift anyway)."""
    parts = spec.time_dirs(name)
    parts = parts if isinstance(parts, list) else [parts]
    for dpath in parts:
        n_mesh = None
        c_path = os.path.join(dpath, 'C')
        try:
            if os.path.isfile(c_path):
                n_mesh = len(reader.read_vector(c_path, None))
            else:
                n_mesh = reader.scalar_size(os.path.join(dpath, 'p'))
        except (OSError, ValueError) as exc:
            return False, f'{os.path.basename(dpath)}: {exc}'
        if n_mesh is None:              # uniform p and no C: nothing to compare
            continue
        for fname in _FO_FIELDS:
            fpath = os.path.join(dpath, fname)
            if not os.path.isfile(fpath):
                continue                # never written - the run has no FO
            try:
                n = reader.scalar_size(fpath)
            except (OSError, ValueError) as exc:
                return False, f'{fname}: {exc}'
            if n is not None and n != n_mesh:
                return False, (f'{fname} holds {n} values but the mesh '
                               f'written with it has {n_mesh} cells')
    return True, ''


def _resume_start_time(spec, times, hooks):
    """The newest written time blastFoam can actually restart from.

    Returns (name, skipped). `skipped` is the inconsistent writes newer
    than it - each one costs only re-solving an interval the run was
    going to re-solve anyway. Raises when nothing is whole, which is a
    refusal with a reason rather than a solver that dies at t0."""
    skipped = []
    for name in reversed(times):
        ok, detail = _time_is_whole(spec, name)
        if ok:
            return name, skipped
        skipped.append((name, detail))
        hooks.log(f'  [blastfoam] cannot restart from t = {name}: {detail}')
    raise RuntimeError(
        'no written time in this run can be restarted from - every one is '
        'internally inconsistent (' + '; '.join(f'{n}: {d}' for n, d
                                                in skipped[:3]) + ')')


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
    hooks.scratch_posix = spec.case_posix      # OUT-1: foam\ copy + release
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
    # OUT-2 (D10): writes the VTK export already removed are not replayed
    from .vtk_export import deleted_note, note_resume
    # OUT-3: ...and so are the older writes this stage's purge removed
    # (a W3 auto-resume on the same hooks)
    rec = getattr(hooks, 'fields_deleted', None)
    rec = rec if isinstance(rec, set) else None
    if getattr(hooks, 'vtk_dir', None) or rec:
        note_resume(getattr(hooks, 'vtk_dir', None), times, hooks.log,
                    deleted=rec)
    else:
        # owner decision P11: a resume from the run browser has no model
        # folder (P2-17), so find the run's vtk\ by its scratch and warn
        note = deleted_note(posix)
        if note:
            hooks.log(note)

    # a Stop leaves `stopAt writeNow` in the runTimeModifiable dict -
    # a resumed solver would exit immediately; and the run must pick up
    # at the last written time, not t = 0
    if not runner.rewrite_control_entry(posix, unc, 'stopAt', 'endTime',
                                        log=hooks.log):
        raise RuntimeError('could not reset stopAt in the controlDict')
    # P1-5: `latestTime` is right only while the latest time is WHOLE.
    # An AMR run can leave a write whose accumulating FO fields sit at
    # the previous cell count, and blastFoam dies reading it before it
    # takes a step. Walk back to the newest write that is consistent and
    # name it explicitly; the FO accumulators then continue from a state
    # that matches its mesh, which is what keeps the peak/impulse maps
    # continuous across the resume.
    start_name, skipped = _resume_start_time(spec, times, hooks)
    # OUT-2: the VTK export never deletes the time the solver restarts
    # from. After a P1-5 walk-back it is not among the newest writes the
    # replay ingests, so KEEP_NEWEST alone would not keep it.
    spec.restart_dir = start_name
    # ...and under AMR the accumulating FOs cannot be restarted at all
    _disable_fo_accumulators(spec, case, hooks)
    if skipped:
        if not runner.rewrite_control_entry(posix, unc, 'startTime',
                                            start_name, log=hooks.log):
            raise RuntimeError('could not set startTime for the resume')
        if not runner.rewrite_control_entry(posix, unc, 'startFrom',
                                           'startTime', log=hooks.log):
            raise RuntimeError('could not set startFrom startTime')
        hooks.log(f'  [blastfoam] restarting from t = {start_name} instead '
                  f'of the latest write: {len(skipped)} newer write(s) are '
                  f'internally inconsistent and would abort the solver. '
                  f'That interval is simply re-solved.')
    elif not runner.rewrite_control_entry(posix, unc, 'startFrom',
                                          'latestTime', log=hooks.log):
        raise RuntimeError('could not set startFrom latestTime')
    hooks.log(f'  [blastfoam] resuming {posix} from t = {start_name} '
              f'({len(times)} already on disk'
              + (f', {n_procs} MPI ranks' if n_procs > 1 else '') + ')')

    solve = {1: solve_1d_foam, 2: solve_2d_foam, 3: solve_3d_foam}[case.dim]
    return solve(case, hooks, adaptive_write=adaptive_write, spec=spec)


def _n_procs_on_disk(case_unc):
    """Number of consecutive `processor<N>` dirs in the case (0 = serial)."""
    n = 0
    while os.path.isdir(os.path.join(case_unc, f'processor{n}')):
        n += 1
    return n


#: W3 (2026-09-16): a run whose WSL distribution was torn down under it
#: (runloop.WslVanished) is resumed from its last written time instead of
#: being reported failed. This many times per run: three is "a hiccup",
#: not "WSL is broken tonight" - past that the run fails like any other,
#: case kept, and the run browser's manual resume still works.
WSL_RESUME_MAX = 3
#: how long one auto-resume waits for WSL to answer again. Asking it is
#: what brings a terminated distribution back (wsl.exe boots it), so the
#: first probe usually succeeds; the ceiling is for a VM that is truly
#: gone (host out of memory, `wsl --shutdown` from elsewhere).
WSL_RESUME_WAIT_S = 300.0
_WSL_RESUME_PROBE_S = 30


def _wait_for_wsl(hooks, wait_s=WSL_RESUME_WAIT_S):
    """Block until the blastFoam install answers again, the user stops,
    or `wait_s` runs out. Returns True when WSL is back."""
    deadline = _time.time() + wait_s
    while True:
        ok, detail = env.check_available(force=True,
                                         timeout=_WSL_RESUME_PROBE_S)
        if ok:
            hooks.log(f'  [blastfoam] WSL is back ({detail})')
            return True
        if hooks.should_stop():
            hooks.log('  [blastfoam] stopped while waiting for WSL')
            return False
        if _time.time() > deadline:
            hooks.log(f'  [blastfoam] WSL did not come back within '
                      f'{wait_s:.0f} s ({detail})')
            return False
        # short slices so a Stop lands within a second
        for _ in range(10):
            if hooks.should_stop():
                break
            _time.sleep(0.5)


def _resume_after_wsl(spec, hooks, adaptive_write, exc):
    """W3: the solver died because WSL went away (`exc`, a
    runloop.WslVanished). Wait for WSL, then `resume_run` the case -
    which re-enters the same `solve_*_foam` with a rebuilt spec, replays
    every write already on disk and follows the solver from there, so
    the caller returns its Result as the run's own. Re-raises `exc`
    unchanged when the attempt budget is spent, WSL stays down, or the
    user stops the wait - the failure then reads exactly as it did
    before W3, case kept.

    The attempt counter lives on `hooks`: it is the one object that
    survives the resume (spec and case are rebuilt from disk). The type
    guard is for test doubles whose __getattr__ answers everything."""
    n = getattr(hooks, 'wsl_resumes', 0)
    n = (n if isinstance(n, int) else 0) + 1
    hooks.wsl_resumes = n
    if n > WSL_RESUME_MAX:
        hooks.log(f'  [blastfoam] WSL went away under the solver again - '
                  f'{WSL_RESUME_MAX} auto-resumes already spent on this '
                  f'run, giving up. The case is kept and can be resumed '
                  f'from the run browser once WSL is stable.')
        raise exc
    hooks.log(f'  [blastfoam] WSL went away under the solver (its files '
              f'returned I/O errors) - that is not a solver failure, and '
              f'every write up to the last one is intact. Waiting for WSL, '
              f'then resuming from the last written time '
              f'(auto-resume {n} of {WSL_RESUME_MAX}).')
    if not _wait_for_wsl(hooks, wait_s=WSL_RESUME_WAIT_S):
        raise exc
    return resume_run(spec.case_posix, hooks, adaptive_write=adaptive_write)


def solve_1d_foam(case, hooks=None, adaptive_write=True, spec=None):
    """Run a Case1D on blastFoam. Returns a Result shaped exactly like
    the native solve_1d.

    `adaptive_write=False` pins writeInterval for the whole run - see
    CaseSpec.adaptive_write (B23); a caller-supplied `spec` skips the
    preflight (resume, N6/T43 - see solve_2d_foam).

    The case itself can also pin it (`case.adaptive_write = False`) -
    the chain panel does, because the adaptive controller keys on what
    the INGEST has kept up with (wall clock), so with it on the write
    schedule differs between identical runs and the arrival-pinned
    hand-off lands on a different write each time (N2-13). Either side
    saying False wins; same rule in solve_2d_foam / solve_3d_foam."""
    hooks = hooks or RunHooks()
    if spec is None:
        spec = _preflight(case, hooks)
    # OUT-2: VTK volumes pin the schedule too (their cadence IS it)
    spec.adaptive_write = (bool(adaptive_write)
                           and bool(getattr(case, 'adaptive_write', True))
                           and not getattr(spec, 'vtk_volumes', None))
    spec.hooks = hooks              # the live-slice canary logs through it
    # blastFoam cannot emit a frame per step: the live view moves at the
    # live-sample cadence, or at writeInterval without one (G7)
    hooks.cadence(dt=_write_cadence_dt(spec),
                  steps=spec.live_steps or writer.live_sample_steps(case.dim))
    r = spec.grid['r']
    # T is in the readiness tuple because finalize_1d re-reads it
    fields = ('p', 'rho', 'U', 'T', f'alpha.{spec.phase}')

    # T60: only a TERMINATE outer boundary ends the run
    terminates = normalize_bc(
        getattr(case, 'bc_outer', 'terminate')) == 'terminate'
    _log_banner_1d(hooks, case, spec)
    _log_dropped_gauges(hooks, case, spec)         # G15U-L2
    # T53: gauge radii for the live pane; GUI-16 (f): the kept ones by
    # their entered numbers, the dropped ones apart
    live, live_dropped = _live_gauges(case, spec)
    hooks.run_started(dict(dim=1, r=r, radius_m=case.radius_m,
                           gauges=live, gauges_dropped=live_dropped))
    _initial_frame(spec, hooks)
    _reset_gauge_live()

    store = {}                      # dirname -> dict(t, p, rho, u)
    pin = dict(name=None, frozen=False)     # OUT-2 (D1): see _track_pin

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
        # finalize_1d's own pin predicate, on the p already in hand
        _track_pin(loop, pin, name, float(entry['p'][-1]) > ARRIVAL_P)
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
            _emit_gauges(hooks, spec)
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
    loop.gauges = lambda: _emit_gauges(hooks, spec)     # D6: tail_live
    try:
        stop_reason = loop.run()
    except WslVanished as exc:          # W3: WSL died under the solver
        return _resume_after_wsl(spec, hooks, adaptive_write, exc)
    return finalize_1d(case, spec, store, hooks, stop_reason,
                       loop.st['step'],
                       conserved=conserved_meta(loop.st))


#: W2 (P1-2): every stop except the solver reaching its own endTime goes
#: through `stopAt writeNow`, and blastProbes flushes what it has buffered
#: only in the function-object destructors at a graceful End. The run loop
#: already waits up to 10 s for that End before its safety-net kill, but a
#: solver that is killed - or one whose End lands after the wait - takes
#: the tail with it (measured: 5 of ~600 samples, with or without a resume).
#: A real fix needs a foam-side flush knob, so until then the run says so.
_NATURAL_END = ('safety cap', 'end time reached')

#: Reasons that mean "this run did not get where it was going": they
#: leave the progress bar where it stopped and tag the result
#: ' (stopped)'. An instability stop belongs here - a run cut short by a
#: collapsing deltaT must not report a filled bar. A trigger gauge or a
#: terminate boundary does NOT: those runs achieved what they were asked.
_STOPPED_EARLY = ('stopped by user', STOP_UNSTABLE)


def _stopped_early(stop_reason):
    """Did the run end short of what it was asked to do?"""
    return stop_reason in _STOPPED_EARLY


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


def conserved_meta(st):
    """meta['conserved'] payload from the run loop's state, or None.

    N5-5. What blastFoam's conservedQuantities reported at its FIRST
    execute, beside the energy the writer put on the mesh. Only a
    profile-initialised stage has something to compare - a charge case
    has no hand-off, and its rhoE is not conserved anyway (E0 arrives
    as lambda goes 0 -> 1: measured +1169 % before the open boundary
    drains it), so `expected` is None there and only the readings are
    kept.
    """
    if not st or not st.get('cons0'):
        return None
    return dict(rhoE0=st['cons0'].get('rhoE'),
                rho0=st['cons0'].get('rho'),
                rhoE_end=(st.get('cons') or {}).get('rhoE'),
                rho_end=(st.get('cons') or {}).get('rho'),
                expected_rhoE0=st.get('E_expect'),
                rel=st.get('cons_rel'),
                source='foam-fo')


def finalize_1d(case, spec, store, hooks, stop_reason, n_steps,
                conserved=None):
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

    # N2-13: the profile handed to the next chain stage is pinned to the
    # arrival write; everything else below keeps describing the full run
    pin = _arrival_pin(names, lambda n: store[n]['t'], stop_reason,
                       lambda n: float(store[n]['p'][-1]) > ARRIVAL_P,
                       hooks)
    prof_name, prof_phase, prof_e = fin_name, phase, e_arr
    if pin is not None:
        try:
            prof_phase, prof_e = read_final(pin)
            prof_name = pin
        except (ValueError, OSError) as exc:
            hooks.log(f'  [warn] arrival write unreadable ({exc}) - '
                      f'hand-off falls back to the last write')
    prof = store[prof_name]

    snapshots = {}
    for name in _pick_snapshots(store, names, case.n_snapshots):
        e = store[name]
        label = f"t = {e['t']*1e3:.3f} ms"
        if label not in snapshots:
            snapshots[label] = dict(r=r.copy(), p=e['p'], rho=e['rho'],
                                    u=e['u'])
    snapshots[f"t = {fin['t']*1e3:.3f} ms (final)"] = dict(
        r=r.copy(), p=fin['p'], rho=fin['rho'], u=fin['u'])

    final_profile = dict(t=prof['t'], r=r.copy(), rho=prof['rho'].copy(),
                         u=prof['u'].copy(), e=prof_e,
                         p=prof['p'].copy(),
                         phase=prof_phase, charge_kg=case.charge_kg,
                         eos='JWL', r_exp=spec.r_exp,
                         radius_m=case.radius_m,
                         source_solver='blastfoam')      # N5-4

    hooks.log(f"\n  Done. {n_steps} solver steps, t_final = "
              f"{fin['t']*1e3:.3f} ms")
    hooks.log(f"  Stopped: {stop_reason}\n")
    note_gauge_tail(hooks, stop_reason)
    hooks.frame(np.array([r, fin['p']]), fin['t'])

    meta = dict(final_profile=final_profile, r=r, radius_m=case.radius_m,
                charge_kg=case.charge_kg, eos='JWL', r_exp=spec.r_exp,
                solver='blastfoam', material=spec.material,
                conserved=conserved,
                case_dir=spec.case_unc)
    return Result(snapshots, _gauges_from_probes(spec), meta,
                  stop_reason, _stopped_early(stop_reason))


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


def _obstacle_snap_lines(spec):
    """Banner lines for obstacle boxes the plan snapped outward onto
    base-cell faces ([] when every box was already face-aligned)."""
    lines = []
    for orig, snap in (getattr(spec, 'obstacles_moved', None) or []):
        o = ', '.join(f'{v:g}' for v in orig)
        s = ', '.join(f'{v:g}' for v in snap)
        lines.append(f'  Obstacle snapped: ({o}) -> ({s}) m '
                     f'(outward, to {spec.dx_base or spec.dx:g} m '
                     f'cell faces)')
    return lines


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
    for lev in range(1, spec.lmax + 1):
        n_l = int(counts[lev]) // (2 ** (dim * (spec.lmax - lev)))
        per.append(f'L{lev} {spec.dx_base / 2 ** lev:g} m: {n_l:,}')
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
    lines = [f'  Initialised from: {src} at t = {spec.t_start * 1e3:.3f} ms',
             f'  Source charge   : explosive radius {spec.r_exp:.4f} m '
             f'({spec.material})']
    n_fl = int(spec.init_state.get('n_floored', 0) or 0)
    if n_fl:
        # N2-14: say it when the hand-off carried near-vacuum cells the
        # remap replaced with quiescent thin gas - silence here is how a
        # 6% intermittent crash stayed unexplained for two nights
        lines.append(f'  Hand-off floor  : {n_fl} near-vacuum cell(s) '
                     f'replaced with quiescent thin gas (N2-14)')
    # N5-4: a native-sourced profile never gets this far (profile_state
    # raises), so the only thing left to say is when we cannot tell.
    # [warn] because both front-ends lift that prefix into the status
    # bar - ui/app.py on_log, gui/app.py _drain.
    if spec.init_state.get('source_solver', 'unknown') == 'unknown':
        lines.append('  [warn] this profile carries no solver stamp; if '
                     'it came from the native solver the hand-off '
                     'over-prices the product cells by ~33 %')
    return lines


def _log_banner_2d(hooks, case, spec, n_gauges, has_term):
    """Log the run banner (mesh, charge, BCs, gauges) for a 2D run."""
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
            *_obstacle_snap_lines(spec),
            f'  Gauges          : {n_gauges}',
            '  Stop condition  : '
            + ('shock arrival at a terminate boundary' if has_term
               else 'safety cap (no terminate boundaries)'),
            f'  Safety cap      : {spec.end_time*1e3:.1f} ms',
            _write_interval_line(spec),
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
    _resolve_adaptive_write(case, spec, adaptive_write)
    spec.hooks = hooks              # the live-slice canary logs through it
    # blastFoam cannot emit a frame per step: the live view moves at the
    # live-sample cadence, or at writeInterval without one (G7)
    hooks.cadence(dt=_write_cadence_dt(spec),
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
    trig_k, trig_cell = _trigger_cells(case, (x_c, y_c), (Nx, Ny),
                                       kept=spec.gauge_ids, hooks=hooks)
    trigger = {}
    d_charge = geometry.d_charge_2d(x_c, y_c, x0, y0)
    dists = geometry.stop_dists_2d(case.Lx, case.Ly, x0, y0, bcs,
                                   x_lo_counts=not axisym)
    stop_dist = min(dists)
    snap_radii = geometry.snap_radii(spec.r_exp, dists, case.n_snapshots)

    _log_banner_2d(hooks, case, spec, len(spec.probe_pts), has_term)
    _log_dropped_gauges(hooks, case, spec)         # G15U-L2
    live, live_dropped = _live_gauges(case, spec)
    run_info = dict(
        dim=2, x_face=g['x_face'], y_face=g['y_face'], solid=solid,
        xlabel='r [m]' if axisym else 'x [m]',
        ylabel='z [m]' if axisym else 'y [m]', title='',
        # T53: what the user asked for (the probes snap in the mesh);
        # GUI-16 (f): the writer's kept gauges, the dropped ones apart
        gauges=live, gauges_dropped=live_dropped,
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
    _reset_gauge_live()

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
    # OUT-2 (D1): the pin candidate the VTK export must keep, and each
    # write's arrival predicate for finalize_2d once its dir is gone
    pin = dict(name=None, frozen=False)
    arrived_cache = {}

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
        arrived_cache[name] = _arrived_2d_grid(p, bcs)
        _track_pin(loop, pin, name, arrived_cache[name])
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
                loop.protect(name)          # finalize_2d re-reads it
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
            _emit_gauges(hooks, spec)
            st['t_frame'] = t
            live['step'] = st['step']
            live['draw'] = _time.time()
        if trig_k is not None and not trigger \
                and p[trig_cell] > ARRIVAL_P:
            trigger.update(
                _trigger_fire(loop, hooks, case, trig_k, t,
                              float(p[trig_cell])),
                time_dir=name)
            if 'remap' in trigger['action']:
                loop.protect(name)          # finalize_2d reads its state
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

    # N2-15: evaluate the arrival stop on the LIVE sample as well. The
    # on_frame check above is ingest-gated - each written dir of a large
    # case is a full multi-field binary read over the WSL 9p mount, and
    # when the solver outwrites the ingest the stop recedes with the
    # backlog: R2's 171,604-cell case ran 8.7 h past a ~10 ms arrival
    # with 2,193 live samples pending. The live sample is one raw
    # surface, cheap, and tail_live always decodes the NEWEST one, so
    # this sees the current edge state however far the written ingest
    # has fallen behind. In 2D the live surface IS the display grid, so
    # term_edge indexes it directly; a shape surprise falls through to
    # the written-dir check, which is the pre-N2-15 status quo. (1D
    # never drowned only because its 100-cell dirs ingest faster than
    # the solver writes them; 3D's live sample is a single plane, not
    # the domain boundary, so its copy of this problem needs its own
    # design - see TODO.)
    if has_term:
        _base_decode = decode

        def decode(tdir):                                   # noqa: F811
            payload = _base_decode(tdir)
            if payload is not None and not loop.stop_requested:
                pl = payload[0] if isinstance(payload, tuple) else payload
                try:
                    if (pl[term_edge] > ARRIVAL_P).any():
                        loop.request_stop(
                            'shock arrived at a terminate boundary '
                            f'(p_edge = {pl[term_edge].max():.3e} Pa, '
                            f'live sample)')
                except (IndexError, TypeError):
                    pass
            return payload

    loop = FoamRunLoop(spec, hooks, fields, ingested, writer.LIVE_SLICE,
                       decode, read_dir, on_frame)
    loop.gauges = lambda: _emit_gauges(hooks, spec)     # D6: tail_live
    try:
        stop_reason = loop.run()
    except WslVanished as exc:          # W3: WSL died under the solver
        return _resume_after_wsl(spec, hooks, adaptive_write, exc)
    return finalize_2d(case, spec, hooks, stop_reason, loop.st['step'],
                       ingested, snap_names, frame_t, frame_p,
                       record_frames, acc, frame_lv=frame_lv,
                       trig_k=trig_k, trigger=trigger,
                       conserved=conserved_meta(loop.st),
                       arrived_cache=arrived_cache)


def finalize_2d(case, spec, hooks, stop_reason, n_steps, ingested,
                 snap_names, frame_t, frame_p, record_frames, acc,
                 frame_lv=None, trig_k=None, trigger=None, conserved=None,
                 arrived_cache=None):
    """Build the exact native-shaped 2D Result via a two-pass snapshot
    re-read (also used by postmortem.load_run).

    `trig_k` / `trigger` are the T51 trigger-gauge index and record from
    the run loop; postmortem.load_run has neither (it never watched the
    run) and passes nothing. `arrived_cache` (OUT-2, D1): the arrival
    predicate the run loop evaluated on each write's `p`, consulted only
    for a write whose directory the VTK export has deleted."""
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
                         **{k: probes[k] for k in reader.GAUGE_KEYS if k in probes})
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
                conserved=conserved,
                # what the USER asked for; gauge_out['points'] is where
                # the probes landed in the mesh (QA-33)
                gauges=[tuple(float(v) for v in gpt)
                        for gpt in (case.gauges or [])],
                case_dir=spec.case_unc, refine=spec.refine_meta())
    # per-step FO peak/impulse maps, falling back to the per-write Python
    # accumulator (B17: same policy as 3D)
    (meta['p_peak'], meta['impulse'],
     meta['peak_source']) = acc.final(fin['p'], dfin, t_fin, spec,
                                      mesh=mesh_fin)
    meta['final_state'] = dict(t=t_fin, rho=fin['rho'], u=fin['u'],
                               v=fin['v'], e=e_arr, p=fin['p'],
                               phase=phase)

    # N2-13: the state handed to the next chain stage is pinned to the
    # arrival write. Everything above - maps, snapshots, frames, gauges -
    # keeps describing the run that actually happened.
    # how the 2D pin keeps its cost bounded: arrived_2d reads one field per
    # probed write, and the forward scan touches only the quiet prefix plus
    # the crossing write itself - the long post-arrival tail is never read
    def arrived_2d(name):
        """The loop's own stop criterion ('shock arrived at a terminate
        boundary'), re-evaluated on the WRITTEN data of one time dir -
        deterministic where the stop instant is not. A write the VTK
        export deleted answers from the run loop's cache (OUT-2)."""
        dp = spec.time_dirs(name)
        if arrived_cache and name in arrived_cache \
                and not os.path.isdir(first_part(dp)):
            return arrived_cache[name]
        pg = read_2d(dp, spec, ('p',), mesh=mesh_at(spec, dp))['p']
        return _arrived_2d_grid(pg, bcs)

    pin = _arrival_pin(names, ingested.get, stop_reason, arrived_2d,
                       hooks)
    if pin is not None:
        try:
            pg, pphase, pe, _pm = read_final(pin)
            meta['final_state'] = dict(
                t=float(ingested[pin]), rho=pg['rho'], u=pg['u'],
                v=pg['v'], e=pe, p=pg['p'], phase=pphase)
        except (ValueError, OSError) as exc:
            hooks.log(f'  [warn] arrival write unreadable ({exc}) - '
                      f'hand-off falls back to the last write')
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
                  _stopped_early(stop_reason))


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


def _split_gauges(case, spec):
    """(kept, dropped): the case's gauges split by the writer's kept list
    (`spec.gauge_ids`, P1-23 A5), each [(entered number, point)] in the
    entered order; 1D points are radii. The writer keeps a 1D gauge at
    0 < r <= the outer face and a 2D/3D one inside the domain and not in
    or on a snapped wall (writer.plan_case)."""
    if case.dim == 1:
        entered = [float(r) for r in case.gauge_radii or []]
        keep = {float(r) for r in spec.gauge_ids}
    else:
        entered = [tuple(float(v) for v in g) for g in case.gauges or []]
        keep = {tuple(float(v) for v in g) for g in spec.gauge_ids}
    kept, dropped = [], []
    for n, pt in enumerate(entered, start=1):
        (kept if pt in keep else dropped).append((n, pt))
    return kept, dropped


def _live_gauges(case, spec, live_sl=None):
    """T53 + GUI-16 (f), D13: the live info's `gauges` and
    `gauges_dropped`, [(entered number, u, v)] - the gauges the writer
    kept and those it dropped, at the points the user entered (the probes
    snap in the mesh). 3D: the ones the live plane `live_sl` cuts, within
    one cell (geometry.plane_gauges)."""
    kept, dropped = _split_gauges(case, spec)
    if case.dim == 1:
        def at(items):
            return [(n, r, 0.0) for n, r in items]
    elif case.dim == 2:
        def at(items):
            return [(n, p[0], p[1]) for n, p in items]
    else:
        g = spec.grid
        coords = (g['x_c'], g['y_c'], g['z_c'])

        def at(items):
            return geometry.plane_gauges([p for _n, p in items], live_sl,
                                         coords, spec.dx,
                                         numbers=[n for n, _p in items])
    return at(kept), at(dropped)


def _log_dropped_gauges(hooks, case, spec):
    """G15U-L2: one `[warn] G2 (1.40, 0.30) m inside Wall 1 - dropped`
    line per gauge the writer dropped, in the native solvers' wording
    (solver1d / solver2d / solver3d, core.geometry.gauge_drop_reason): a
    1D radius past the outer face, a 2D/3D gauge outside the domain, or
    in or on a snapped wall (the writer's closed test on spec.obstacles;
    `inside` when strictly inside a wall as entered). blastFoam User
    Guide v6.0, sec. 15 (blastProbes): the writer hands blastFoam only
    the probes it kept. Returns the lines logged."""
    lines = []
    for n, pt in _split_gauges(case, spec)[1]:
        if case.dim == 1:
            lines.append(f"  [warn] G{n} (r {pt:.2f} m) "
                         f"{geometry.OUTSIDE_DOMAIN} - dropped")
            continue
        name = f"G{n} ({', '.join(f'{v:.2f}' for v in pt)}) m"
        g = spec.grid
        lengths = [g[k][-1] for k in ('x_face', 'y_face', 'z_face')
                   [:case.dim]]
        if any(not 0 <= v <= L for v, L in zip(pt, lengths)):
            why = geometry.OUTSIDE_DOMAIN
        else:
            wall = geometry._in_box_closed(pt, spec.obstacles or [])
            inside = geometry._in_obstacle_open(pt, case.obstacles or [])
            why = (geometry.gauge_drop_reason(inside or wall, bool(inside))
                   if inside or wall else 'inside an obstacle')
        lines.append(f"  [warn] {name} {why} - dropped")
    for line in lines:
        hooks.log(line)
    return lines


def _trigger_cells(case, coords, shape, kept=None, hooks=None):
    """T51: (index, cell) for the trigger gauge on a display grid, or
    (None, None). `coords` are the cell centres per axis; the gauge is
    snapped to its nearest cell exactly as the native solvers do.

    P1-23 / P1-24 (Q2, owner 2026-10-12): `kept` is the writer's list of
    the gauges it kept (`spec.gauge_ids`). A trigger on a gauge the
    writer dropped (outside the domain, or in or on a snapped wall) is
    disabled, with hooks.trigger_index's warn line, as the native
    solvers do (D13). Left live it read a carved display cell (ambient,
    never fires) or, exactly on a snapped low face, the fluid cell in
    front of the wall (can fire): one rule for both solvers instead."""
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
    if kept is not None:
        keep = {tuple(float(v) for v in g) for g in kept}
        numbers = [i + 1 for i, g in enumerate(gauges)
                   if tuple(float(v) for v in g) in keep]
        if trigger_index(n, len(gauges), hooks or RunHooks(),
                         numbers) is None:
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
    hooks.log(f"  Trigger gauge G{k + 1} ("
              + ", ".join(f"{v:.4f}" for v in pt)
              + f") m reached at t = {t*1e3:.3f} ms (p = {p_at:.3e} Pa)")
    if 'terminate' in action and not loop.stop_requested:
        loop.request_stop(f'trigger gauge G{k + 1} reached')
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
    e0 = p0 / (_AIR_GAMMA_M1 * rho0)
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


def _interval_label(spec):
    """The banner's word on the write schedule. The two pre-HD1-15
    phrasings are unchanged - the GUI and tests read this line - and a
    write budget gets its own."""
    if getattr(spec, 'write_budget', 0):
        return f'(pinned: write budget {spec.write_budget})'
    if getattr(spec, 'vtk_volumes', None):
        return '(pinned: VTK volumes)'
    return '(initial, adaptive)' if spec.adaptive_write else '(pinned schedule)'


def _write_interval_line(spec):
    """The banner's `Write interval` line. OUT-2: VTK volumes in Step
    mode write every N solver steps, and the line says so rather than
    quote the transit-sized estimate that no longer schedules anything."""
    if getattr(spec, 'write_steps', 0):
        return (f'  Write interval  : every {spec.write_steps} solver steps '
                f'(pinned: VTK volumes)')
    return (f'  Write interval  : {spec.write_interval*1e3:.4f} ms '
            + _interval_label(spec))


def _write_cadence_dt(spec):
    """hooks.cadence's `dt`: writeInterval [s], or None (unknown) when
    the writes come every N solver steps (OUT-2 Step mode)."""
    return None if getattr(spec, 'write_steps', 0) else spec.write_interval


def _resolve_adaptive_write(case, spec, adaptive_write):
    """Set `spec.adaptive_write` for a 2D/3D run (1D has no write-budget
    term and stays inline). Either side saying False pins the write
    schedule (N2-13; see the solve_1d_foam docstring), and so does a
    write budget (HD1-15)."""
    spec.adaptive_write = (bool(adaptive_write)
                           and bool(getattr(case, 'adaptive_write', True))
                           and not getattr(spec, 'write_budget', 0)
                           and not getattr(spec, 'vtk_volumes', None))


def _log_banner_3d(hooks, case, spec, n_gauges, has_term):
    """Log the run banner (mesh, charge, BCs, gauges) for a 3D run."""
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
            *_obstacle_snap_lines(spec),
            f'  Gauges          : {n_gauges}',
            '  Stop condition  : '
            + ('shock arrival at a terminate boundary' if has_term
               else 'safety cap (no terminate boundaries)'),
            f'  {"End time" if spec.cap_is_end else "Safety cap":<16}: '
            f'{spec.end_time*1e3:.1f} ms',
            _write_interval_line(spec),
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
    _resolve_adaptive_write(case, spec, adaptive_write)
    spec.hooks = hooks             # the live-slice canary logs through it
    # blastFoam cannot emit a frame per step: the live view moves at the
    # live-sample cadence, or at writeInterval without one (G7)
    hooks.cadence(dt=_write_cadence_dt(spec),
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
                                       (Nx, Ny, Nz),
                                       kept=spec.gauge_ids, hooks=hooks)
    trigger = {}
    d_charge = geometry.d_charge_3d(x_c, y_c, z_c, centers)
    dists = geometry.stop_dists_3d(case.Lx, case.Ly, case.Lz, centers, bcs)
    stop_dist = min(dists)
    snap_radii = geometry.snap_radii(spec.r_exp, dists, n_snapshots)

    # burst-plane slice indices + user live slice (native conventions)
    (_j0, _k0, slice_axis, s0, live_sl, live_faces, live_labels,
     live_title) = slice_geom_3d(case, spec)

    _log_banner_3d(hooks, case, spec, len(spec.probe_pts), has_term)
    _log_dropped_gauges(hooks, case, spec)         # G15U-L2
    live, live_dropped = _live_gauges(case, spec, live_sl)
    ax_i = 'xyz'.index(slice_axis)
    hooks.run_started(dict(
        dim=3, x_face=live_faces[0], y_face=live_faces[1],
        solid=solid[live_sl], xlabel=live_labels[0],
        ylabel=live_labels[1], title=live_title,
        # GUI-16 (f): the writer's kept gauges, the dropped ones apart
        gauges=live, gauges_dropped=live_dropped,
        mesh_src=(refine.slice_src(spec.levels, spec.lmax, ax_i, s0,
                                   solid_fine=spec.solid)
                  if spec.lmax and not spec.amr else None),
        display_level=spec.display_level if spec.amr else None,
        scene3d=dict(x_c=x_c, y_c=y_c, z_c=z_c, dx=dx, solid=solid,
                     obstacles=[tuple(o) for o in spec.obstacles],
                     Lx=case.Lx, Ly=case.Ly, Lz=case.Lz,
                     charge_center=(x0, y0, z0), r_exp=spec.r_exp,
                     bcs=bcs, refine=spec.refine_meta(),
                     # where the live-slice plane sits, so the 3D scene
                     # can place the sample-cadence plane it is sent
                     slice_axis=slice_axis, slice_index=int(s0),
                     # P2-2: the live energy field is the ideal-gas
                     # stand-in this backend derives, not a solved one
                     solver='blastfoam')))
    _initial_frame(spec, hooks, live_sl)
    _initial_frame3d(spec, hooks)
    _reset_gauge_live()

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
                loop.protect(name)          # finalize_3d re-reads it
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
            _emit_gauges(hooks, spec)
            st['t_frame'] = t
            live['step'] = st['step']
            live['draw'] = _time.time()
        if will_3d:
            rho = got['rho']
            e_approx = _e_approx(p, rho)
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

    # N3-01: evaluate the arrival stop on the LIVE slice as well - the
    # 3D copy of N2-15. The on_frame check above is ingest-gated, and a
    # 3D write is the largest read of all over the WSL 9p mount, so the
    # stop recedes with the backlog exactly as R2's did in 2D; measured
    # here as the bimodal test_foam_3d_smoke gate (the overshoot
    # quantized to whichever terminal write the lagging ingest reached).
    # The live slice passes through the burst point, so the four
    # IN-PLANE boundaries are reached first ON this very plane - the
    # slice rim sees the arrival the step it happens, however far the
    # written ingest has fallen behind. A terminate side normal to the
    # slice axis stays invisible here and keeps the written-dir check
    # (the pre-N3-01 status quo); a shape surprise falls through the
    # same way.
    rim_edge = geometry.terminate_edge_mask(
        lshape,
        dict(x_lo=bcs[f'{"xyz"[uv[0]]}_lo'],
             x_hi=bcs[f'{"xyz"[uv[0]]}_hi'],
             y_lo=bcs[f'{"xyz"[uv[1]]}_lo'],
             y_hi=bcs[f'{"xyz"[uv[1]]}_hi']),
        fluid=None if slice_solid is None else ~slice_solid)
    if has_term and rim_edge.any():
        _base_decode3 = decode

        def decode(tdir):                                   # noqa: F811
            payload = _base_decode3(tdir)
            if payload is not None and not loop.stop_requested:
                pl = payload[0] if isinstance(payload, tuple) else payload
                try:
                    if (pl[rim_edge] > ARRIVAL_P).any():
                        loop.request_stop(
                            'shock arrived at a terminate boundary '
                            f'(p_edge = {pl[rim_edge].max():.3e} Pa, '
                            f'live slice)')
                except (IndexError, TypeError):
                    pass
            return payload

    loop = FoamRunLoop(spec, hooks, fields, ingested, writer.LIVE_SLICE,
                       decode, read_dir, on_frame)
    loop.gauges = lambda: _emit_gauges(hooks, spec)     # D6: tail_live
    try:
        stop_reason = loop.run()
    except WslVanished as exc:          # W3: WSL died under the solver
        return _resume_after_wsl(spec, hooks, adaptive_write, exc)
    if stop_reason == 'safety cap' and spec.cap_is_end:
        stop_reason = 'end time reached'

    return finalize_3d(case, spec, hooks, stop_reason, loop.st['step'],
                       ingested, snap_names, frame_t, frame_p,
                       record_frames, acc, frame_lv=frame_lv,
                       trig_k=trig_k, trigger=trigger,
                       conserved=conserved_meta(loop.st))


def finalize_3d(case, spec, hooks, stop_reason, n_steps, ingested,
                 snap_names, frame_t, frame_p, record_frames, acc,
                 frame_lv=None, trig_k=None, trigger=None, conserved=None):
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
    e_approx = _e_approx(fin['p'], fin['rho'])
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
                         **{k: probes[k] for k in reader.GAUGE_KEYS if k in probes})
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
                conserved=conserved,
                # what the USER asked for; gauge_out['points'] is where
                # the probes landed in the mesh (QA-33)
                gauges=[tuple(float(v) for v in gpt)
                        for gpt in (case.gauges or [])],
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
                  _stopped_early(stop_reason))
