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
import shutil
import threading
import time as _time

import numpy as np

from ...core.constants import P_AIR, RHO_AIR
from ..hooks import Progress, Result, RunHooks, StoppedBeforeStart
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

#: FOAM warnings that are inherent to the collapsed-hex sector/wedge
#: meshes (1D sector, 2D axisym): the apex face degenerates into the
#: default patch, and the 1-degree wedge planarity residual is ~1e-16
#: (pure float round-off - the vendor's own wedge tutorials print the
#: same). Summarized once instead of spamming the log.
_BENIGN_WARN = ('undefined faces in mesh; adding to default patch',
                'is not planar')


def _todo(dim):
    raise NotImplementedError(
        f"The blastFoam backend for {dim}D cases is not implemented yet "
        f"- select the 'native' solver for this case.")


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
    stages.append(('charge init (setRefinedFields)',
                   'setRefinedFields -noRefine'))
    if spec.n_procs > 1:
        stages.append((f'decomposing for {spec.n_procs} MPI ranks',
                       'decomposePar -force'))
    return stages


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
    n_procs = 1 if case.dim == 1 else env.resolve_nprocs(
        getattr(case, 'n_procs', 0), plan.n_cells)
    spec = writer.write_case(case, n_procs=n_procs)
    hooks.log(f"  [blastfoam] case directory: {spec.case_unc}")
    # one wsl call per stage (not one `&&` chain): that is what lets a
    # Stop land between stages and kill the running one, and it lets the
    # log name the stage the user is actually waiting on
    out = []
    for label, cmd in _mesh_stages(spec, hooks):
        _stop_check(hooks, label)
        hooks.log(f'  [blastfoam] {label}...')
        out.append(runner.run_stage_stoppable(
            spec.case_posix, cmd, should_stop=hooks.should_stop))
    # scanned once over every stage's output, as when this was a single
    # `&&` chain: the benign wedge warnings collapse into one note
    # instead of one per stage that emits them
    _scan_stage_warnings('\n'.join(out), hooks)
    return spec


def _scan_stage_warnings(out, hooks):
    """Surface FOAM warnings from the mesh/init stages (their output
    is otherwise discarded on success): benign sector-wedge warnings
    collapse into one note, anything else is logged with its message."""
    msgs = re.findall(
        r'--> FOAM Warning :[^\n]*\n'
        r'(?:\s*From [^\n]*\n)?(?:\s*in file[^\n]*\n)?\s*([^\n]+)', out)
    benign = [m for m in msgs if any(s in m for s in _BENIGN_WARN)]
    other = [m for m in msgs if not any(s in m for s in _BENIGN_WARN)]
    if benign:
        hooks.log('  [blastfoam] note: benign wedge-geometry warnings '
                  'from the sector mesh (collapsed apex / ~1e-16 '
                  'planarity round-off) - expected, harmless')
    for m in other:
        hooks.log(f'  [foam] mesh-stage Warning: {m.strip()}')


def _stop_grace(spec):
    """writeNow -> kill escalation window: a big mesh needs longer to
    finish the current step + final write."""
    return max(_STOP_GRACE_S, spec.n_cells / 2e5)


def _maybe_reconstruct(spec, fields, done=False):
    """Parallel runs: reconstruct processor time dirs that are complete
    on every rank and absent top-level, so the ingest loops read
    reconstructed dirs indistinguishable from serial output. Quietly
    retries next poll on failure. `done` lifts the per-poll batch cap
    (final sweep after the solver exits)."""
    if spec.n_procs <= 1:
        return
    proc_uncs = [os.path.join(spec.case_unc, f'processor{i}')
                 for i in range(spec.n_procs)]
    common = None
    for pu in proc_uncs:
        try:
            times = {name for _t, name in reader.list_times(pu)
                     if reader.time_ready(os.path.join(pu, name),
                                          fields)}
        except OSError:
            return
        common = times if common is None else (common & times)
    if not common:
        return
    have = {name for _t, name in reader.list_times(spec.case_unc)}
    todo = sorted(common - have, key=float)
    if not done:
        todo = todo[:4]             # bound per-poll reconstruct work
    if not todo:
        return
    try:
        runner.run_stage(
            spec.case_posix,
            [f'reconstructPar -newTimes -time {",".join(todo)}'],
            timeout=1800)
    except runner.FoamStageError:
        pass                        # transient (mid-write): next poll


def _progress_line(line, st, hooks, end_time):
    """Parse one solver stdout line into Progress state. st['frac'],
    when not None, overrides the t/end_time estimate (3D uses the
    shock-front radius, updated per ingested write). FOAM warning
    blocks are multi-line ('--> FOAM Warning :' then From/in file then
    the message) - the actual message is captured and logged; the
    benign sector-wedge warnings collapse into one note."""
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
    if 'FOAM FATAL' in line:
        hooks.log('  [foam] ' + line.rstrip())
        return
    if 'FOAM Warning' in line:
        st['warn_scan'] = 6         # look for the message just below
        return
    if st.get('warn_scan'):
        st['warn_scan'] -= 1
        ls = line.strip()
        if not ls or ls.startswith('From ') or ls.startswith('in file'):
            return
        st['warn_scan'] = 0
        if any(s in ls for s in _BENIGN_WARN):
            if not st.get('warn_benign_noted'):
                st['warn_benign_noted'] = True
                hooks.log('  [blastfoam] note: benign wedge-geometry '
                          'warnings from the sector mesh (collapsed '
                          'apex / ~1e-16 planarity round-off) - '
                          'expected, harmless')
        else:
            hooks.log('  [foam] Warning: ' + ls)


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


def _tail_live(spec, hooks, st, live, set_name, decode):
    """Shared live-sample tail (1D line / 2D+3D slice): poll the
    postProcessing/<set_name> dirs, emit at most one hooks.frame per
    call (the newest complete sample), delete consumed dirs so disk
    use stays bounded. `decode(tdir)` -> frame payload or None while
    the sample is still mid-write. The GUI refresh policy is honored:
    seconds mode throttles wall time, steps mode gates on solver steps
    since the last emitted live frame."""
    entries = reader.list_sample_times(spec.case_unc, set_name)
    fresh = [(t, n) for t, n in entries if n not in live['seen']]
    if not fresh:
        return
    if not _due_sparse(hooks.refresh, st['step'], live):
        return
    for t, name in reversed(fresh):
        payload = decode(name)
        if payload is None:
            continue
        if t >= st['t_frame']:
            hooks.frame(payload, t)
            st['t_frame'] = t
            live['step'] = st['step']
            live['draw'] = _time.time()
        for tt, nn in entries:
            if tt <= t and nn not in live['seen']:
                live['seen'].add(nn)
                shutil.rmtree(
                    os.path.join(spec.case_unc, 'postProcessing',
                                 set_name, nn),
                    ignore_errors=True)
        break


def _new_live():
    return dict(seen=set(), step=-(10 ** 9), draw=0.0)


def _due_sparse(policy, step, last):
    """Refresh-policy check for the foam ingest paths. Unlike the
    native solvers, these are evaluated only when output lands on disk
    - at arbitrary step counts - so steps mode gates on solver steps
    elapsed since the last emitted frame (RunHooks._due's `step % n`
    form would almost never hit here). `last` carries the previous
    emission: 'step' and 'draw' (wall time), as built by _new_live()."""
    mode, val = policy
    if mode == 'steps':
        return step - last['step'] >= max(1, int(val))
    return _time.time() - last['draw'] > float(val)


def _decode_surface(spec, tdir, shape, ax_u, ax_v, slice_mask=None):
    """One liveSlice raw sample -> grid-shaped p array or None while
    mid-write. The plane cuts one face per cell (interpolate and
    triangulate are off), so sorting the rows by their in-plane
    coordinates (ax_v primary, ax_u secondary) lands them in the
    native x-fastest cell order. `slice_mask` (obstacle-carved 3D
    meshes) marks the solid cells of the sampled layer: the sample
    then holds only that layer's fluid cells, which are scattered
    around the mask; solid cells display ambient pressure."""
    data = reader.read_surface_sample(spec.case_unc, writer.LIVE_SLICE,
                                      tdir)
    if data is None:
        return None
    pts, vals = data
    if slice_mask is None:
        if len(vals) != shape[0] * shape[1]:
            return None
        order = np.lexsort((pts[:, ax_u], pts[:, ax_v]))
        return vals[order].reshape(shape, order='F')
    fluid = ~slice_mask
    if len(vals) != int(fluid.sum()):
        return None
    # boolean-mask assignment fills in C order (ax_v fastest), so sort
    # ax_u primary / ax_v secondary to match
    order = np.lexsort((pts[:, ax_v], pts[:, ax_u]))
    full = np.full(shape, float(P_AIR))
    full[fluid] = vals[order]
    return full


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


_STALL_POLLS = 20   # polls a torn earlier dir may hold up ingest once later dirs are complete


class _OrderedIngest:
    """Strictly time-ordered time-dir ingest (B16).

    A pass over `pending()` stops at the first dir that is not ready yet,
    so a later write never lands before an earlier one (which used to
    feed a negative dt to the impulse accumulator and make the recorded
    frame timeline non-monotonic). A dir that stays unreadable for
    _STALL_POLLS polls *after a later dir is already complete* is skipped
    for good with one log line; on the final sweep (solver exited, files
    complete) any gap is skipped at once so nothing readable is lost."""

    def __init__(self, spec, fields, hooks):
        self.spec, self.fields, self.hooks = spec, fields, hooks
        self.stalls = {}
        self._times, self._i, self._done, self._final = [], 0, {}, False

    def pending(self, done, final=False):
        """Yield (name, dpath) in ascending time; ends at the first gap."""
        self._done, self._final = done, final
        self._times = reader.list_times(self.spec.case_unc)
        for i, (_t_disp, name) in enumerate(self._times):
            if name in done or self.stalls.get(name, 0) >= _STALL_POLLS:
                continue
            self._i = i
            dpath = os.path.join(self.spec.case_unc, name)
            if not reader.time_ready(dpath, self.fields):
                if self.unreadable(name):
                    continue
                return
            yield name, dpath

    def unreadable(self, name):
        """Register that `name` could not be ingested on this poll (not
        ready, or torn mid-write). True -> skip it permanently; False ->
        end the pass and retry it next poll."""
        if self._final:
            inc = _STALL_POLLS
        elif any(n2 not in self._done
                 and reader.time_ready(os.path.join(self.spec.case_unc, n2),
                                       self.fields)
                 for _t2, n2 in self._times[self._i + 1:]):
            inc = 1                 # later writes are complete: it should be too
        else:
            return False            # newest write still in progress: normal
        n = self.stalls.get(name, 0) + inc
        self.stalls[name] = n
        if n < _STALL_POLLS:
            return False
        if self._final:
            self.hooks.log(f'  [blastfoam] time dir {name} incomplete '
                           f'after the solver exited - skipped')
        else:
            self.hooks.log(f'  [blastfoam] time dir {name} stayed '
                           f'unreadable while later writes completed '
                           f'- skipped')
        return True

    def skip(self, name):
        """Never yield `name` again (the caller has already logged why)."""
        self.stalls[name] = _STALL_POLLS


class _PeakImpulse:
    """Per-write Python p_peak/impulse accumulator with blastFoam's
    per-step pMax/impulse function-object fields layered on top.
    Remembers the time each source last covered so `final()` can tell a
    fresh FO read from a stale one (B17)."""

    def __init__(self):
        self.p_peak = self.impulse = None
        self.t_py = None
        self.fo_peak = self.fo_imp = None
        self.t_fo = None
        self._noted = False

    def add(self, p, t, dpath, spec, hooks):
        """Accumulate one ingested write. False (logged) when t is before
        the last accumulated time - unreachable with _OrderedIngest, kept
        as the guard B16 asks for; the caller then skips the dir."""
        if self.t_py is not None and t < self.t_py:
            hooks.log(f'  [blastfoam] write t = {t*1e3:.3f} ms arrived '
                      f'after {self.t_py*1e3:.3f} ms - not accumulated')
            return False
        if self.p_peak is None:
            self.p_peak = p.copy()
            self.impulse = np.zeros_like(p)
            t_prev = 0.0
        else:
            np.maximum(self.p_peak, p, out=self.p_peak)
            t_prev = self.t_py
        self.impulse += (p - P_AIR) * (t - t_prev)
        self.t_py = t
        # per-step FO fields (preferred over the per-write accumulators
        # above); t=0 has no FO output yet
        got_peak, got_imp = _read_fo_fields(dpath, spec)
        if got_peak is not None:
            self.fo_peak, self.fo_imp, self.t_fo = got_peak, got_imp, t
        elif t > 0.0 and self.fo_peak is None and not self._noted:
            self._noted = True
            hooks.log('  [blastfoam] pMax/impulse fields not found '
                      '- peak/impulse tracked per write instead of '
                      'per step')
        return True

    def live(self):
        """(p_peak, impulse) for live frames: FO when it exists."""
        if self.fo_peak is not None:
            return self.fo_peak, self.fo_imp
        return self.p_peak, self.impulse

    def final(self, p_fin, dfin, t_fin, spec):
        """(p_peak, impulse, peak_source) for the Result.
        Order: the final dir's FO fields; an FO read that already covers
        t_fin; the Python accumulator - 'python-fallback' when FO data
        exists but is older than the final frame (the stale-FO case B17
        fixes), 'python-writes' when the case never produced FO fields."""
        if self.p_peak is None:
            self.p_peak = p_fin.copy()
            self.impulse = np.zeros_like(p_fin)
        np.maximum(self.p_peak, p_fin, out=self.p_peak)
        got_peak, got_imp = _read_fo_fields(dfin, spec)
        if got_peak is not None:
            return got_peak, got_imp, 'foam-fo'
        if self.fo_peak is not None and self.t_fo >= t_fin:
            return self.fo_peak, self.fo_imp, 'foam-fo'
        return (self.p_peak, self.impulse,
                'python-fallback' if self.fo_peak is not None
                else 'python-writes')


def _stop_dists_3d(case, spec):
    """Distances that drive the 3D arrival-stop progress and the snapshot
    radii: per open side, the distance from the NEAREST charge (B21 -
    the stop itself is pressure-based; this only sizes progress and
    snapshots); with no open side, the far corner from the primary
    charge (the safety cap stops such a run)."""
    x0, y0, z0 = spec.center
    dists = []
    for side, d_of in (('x_lo', lambda c: c[0]),
                       ('x_hi', lambda c: case.Lx - c[0]),
                       ('y_lo', lambda c: c[1]),
                       ('y_hi', lambda c: case.Ly - c[1]),
                       ('z_lo', lambda c: c[2]),
                       ('z_hi', lambda c: case.Lz - c[2])):
        if case.bcs[side] == 'open':
            dists.append(min(float(d_of(c)) for c, _m in spec.charges))
    if not dists:
        dists = [max(float(np.hypot(np.hypot(cx - x0, cy - y0), cz - z0))
                     for cx in (0, case.Lx) for cy in (0, case.Ly)
                     for cz in (0, case.Lz))]
    return dists


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
            f'  Write interval  : {spec.write_interval*1e3:.4f} ms '
            f'(initial, adaptive)',
            f'  Live profile    : p(r) sampled every '
            f'{writer.live_sample_steps(1)} steps',
            bar, ''):
        hooks.log(line)


def solve_1d_foam(case, hooks=None):
    """Run a Case1D on blastFoam. Returns a Result shaped exactly like
    the native solve_1d."""
    hooks = hooks or RunHooks()
    spec = _preflight(case, hooks)
    m = MATERIALS[spec.material]
    r = spec.grid['r']
    # T is in the readiness tuple because _finalize_1d re-reads it
    fields = ('p', 'rho', 'U', 'T', f'alpha.{spec.phase}')

    _log_banner_1d(hooks, case, spec)
    hooks.run_started(dict(dim=1, r=r, radius_m=case.radius_m))
    _initial_frame(spec, hooks)

    store = {}                      # dirname -> dict(t, p, rho, u)
    order = _OrderedIngest(spec, fields, hooks)
    # frac starts None on purpose: that is what arms _progress_line's
    # t/end_time estimate, so the bar moves from the first solver step
    # instead of sitting at 0 until the first ingested write (below)
    # computes a real shock-front fraction
    st = dict(step=0, t=0.0, dt=0.0, p_max=float(P_AIR), frac=None,
              t_frame=-1.0)
    live = _new_live()
    adapt = dict(interval=spec.write_interval, since=0)
    stop_reason = 'safety cap'
    stop_deadline = None

    run = runner.FoamRun(spec.case_posix, spec.case_unc,
                         n_procs=spec.n_procs, log=hooks.log)

    def request_stop(reason):
        nonlocal stop_reason, stop_deadline
        stop_reason = reason
        if not run.request_write_now():
            hooks.log('  [blastfoam] graceful stop request did not go '
                      'through - the solver will be killed')
        stop_deadline = _time.time() + _stop_grace(spec)

    def ingest_ready(final=False):
        _maybe_reconstruct(spec, fields)
        for name, dpath in order.pending(store, final):
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
                if order.unreadable(name):
                    continue
                break               # mid-write over 9p; retry next poll
            store[name] = entry
            # shock-front position: real progress for the bar and for
            # the adaptive-interval controller
            shocked = entry['p'] > _ARRIVAL_P
            r_front = float(r[shocked].max()) if shocked.any() else 0.0
            st['frac'] = min(1.0, r_front / float(r[-1]))
            _maybe_adapt(spec, st, adapt, run, hooks, len(store))
            will_pause = hooks.exec_will_pause()
            due = (_due_sparse(hooks.refresh, st['step'], live)
                   and entry['t'] >= st['t_frame'])
            if due or will_pause:
                hooks.frame(np.array([r, entry['p']]), entry['t'])
                st['t_frame'] = entry['t']
                live['step'] = st['step']
                live['draw'] = _time.time()
            if not run.stop_requested and entry['p'][-1] > _ARRIVAL_P:
                request_stop('shock arrived at outer boundary '
                             f"(p_last = {entry['p'][-1]:.3e} Pa)")
            _note_pause(hooks, st, will_pause)
            _gated_step(run, hooks)

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

    def ingest_live():
        _tail_live(spec, hooks, st, live, writer.LIVE_SET, decode_line)

    try:
        while True:
            for line in run.drain(_POLL_S):
                _progress_line(line, st, hooks, spec.end_time)
            ingest_live()
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
                _maybe_reconstruct(spec, fields, done=True)
                ingest_ready(final=True)   # final sweep - files complete
                break
    finally:
        if run.running:
            run.kill()
        # live samples are display-only; drop the leftovers so a kept
        # case dir holds just the real record (time dirs + probes)
        shutil.rmtree(os.path.join(spec.case_unc, 'postProcessing',
                                   writer.LIVE_SET), ignore_errors=True)

    if run.returncode not in (0, None) and not run.stop_requested:
        raise RuntimeError(
            f"blastFoam failed (exit {run.returncode}) - case kept at "
            f"{spec.case_unc}\n{run.tail()}")
    if not store:
        raise RuntimeError(
            "blastFoam produced no readable time steps - case kept at "
            f"{spec.case_unc}\n{run.tail()}")

    return _finalize_1d(case, spec, store, hooks, stop_reason,
                        st['step'])


def _finalize_1d(case, spec, store, hooks, stop_reason, n_steps):
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
    hooks.frame(np.array([r, fin['p']]), fin['t'])

    meta = dict(final_profile=final_profile, r=r, radius_m=case.radius_m,
                charge_kg=case.charge_kg, eos='JWL', r_exp=spec.r_exp,
                solver='blastfoam', material=spec.material,
                case_dir=spec.case_unc)
    return Result(snapshots, _gauges_from_probes(spec), meta,
                  stop_reason, stop_reason == 'stopped by user')


# ── 2D ──────────────────────────────────────────────────────────────────────

def _read_2d(dpath, spec, what=('p',)):
    """Read fields of one time dir onto the native (Nx,Ny) layout.
    Obstacle-carved cells read back as still ambient."""
    out = {}
    n = spec.n_cells
    if 'p' in what:
        out['p'] = reader.to_grid(
            reader.read_scalar(os.path.join(dpath, 'p'), n), spec,
            fill=P_AIR)
    if 'rho' in what:
        out['rho'] = reader.to_grid(
            reader.read_scalar(os.path.join(dpath, 'rho'), n), spec,
            fill=RHO_AIR)
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
            f'  Obstacles       : {len(spec.obstacles)}'
            + (' (carved out of the mesh, rigid walls)'
               if spec.obstacles else ''),
            f'  Gauges          : {n_gauges}',
            '  Stop condition  : '
            + ('shock arrival at an open boundary' if has_open
               else 'safety cap (no open boundaries)'),
            f'  Safety cap      : {spec.end_time*1e3:.1f} ms',
            f'  Write interval  : {spec.write_interval*1e3:.4f} ms '
            f'(initial, adaptive)',
            f'  Live slice      : p sampled every '
            f'{writer.live_sample_steps(2)} steps',
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
    solid = (spec.solid if spec.solid is not None
             else np.zeros((Nx, Ny), dtype=bool))

    # open-boundary edge mask + distances (native logic, solver2d:236)
    open_edge = np.zeros((Nx, Ny), dtype=bool)
    sides = (('x_hi', np.s_[-1, :]), ('y_lo', np.s_[:, 0]),
             ('y_hi', np.s_[:, -1]))
    if not axisym:
        sides += (('x_lo', np.s_[0, :]),)
    for side, sl in sides:
        if bcs[side] == 'open':
            open_edge[sl] = True
    open_edge &= ~solid         # carved cells read back as ambient
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
    run_info = dict(
        dim=2, x_face=g['x_face'], y_face=g['y_face'], solid=solid,
        xlabel='r [m]' if axisym else 'x [m]',
        ylabel='z [m]' if axisym else 'y [m]', title='')
    if axisym:
        # live (r, z) frames can be revolved into a 3D cylinder view
        run_info['revolve3d'] = dict(
            r_c=x_c, z_c=y_c, solid=solid, bcs=bcs,
            obstacles=[tuple(o) for o in spec.obstacles],
            z0=y0, r_exp=spec.r_exp, R=case.Lx, Lz=case.Ly)
    hooks.run_started(run_info)
    _initial_frame(spec, hooks)

    record_frames = case.record_frames
    frame_t, frame_p = [], []
    # T is in the readiness tuple because _finalize_2d re-reads it
    fields = ('p', 'rho', 'U', 'T', f'alpha.{spec.phase}')
    ingested = {}               # dirname -> t (full arrays NOT retained)
    snap_names = []
    acc = _PeakImpulse()        # per-write Python + per-step FO accumulators
    order = _OrderedIngest(spec, fields, hooks)
    # frac starts None on purpose: that is what arms _progress_line's
    # t/end_time estimate, so the bar moves from the first solver step
    # instead of sitting at 0 until the first ingested write (below)
    # computes a real shock-front fraction
    st = dict(step=0, t=0.0, dt=0.0, p_max=float(P_AIR), frac=None,
              t_frame=-1.0)
    live = _new_live()
    adapt = dict(interval=spec.write_interval, since=0)
    stop_reason = 'safety cap'
    stop_deadline = None

    run = runner.FoamRun(spec.case_posix, spec.case_unc,
                         n_procs=spec.n_procs, log=hooks.log)

    def request_stop(reason):
        nonlocal stop_reason, stop_deadline
        stop_reason = reason
        if not run.request_write_now():
            hooks.log('  [blastfoam] graceful stop request did not go '
                      'through - the solver will be killed')
        stop_deadline = _time.time() + _stop_grace(spec)

    slice_solid = solid if solid.any() else None

    def ingest_live():
        _tail_live(spec, hooks, st, live, writer.LIVE_SLICE,
                   lambda tdir: _decode_surface(spec, tdir, (Nx, Ny),
                                                0, 1, slice_solid))

    def ingest_ready(final=False):
        nonlocal frame_t, frame_p
        _maybe_reconstruct(spec, fields)
        for name, dpath in order.pending(ingested, final):
            try:
                t, _dt = reader.read_time(dpath)
                p = _read_2d(dpath, spec)['p']
            except (ValueError, OSError):
                if order.unreadable(name):
                    continue
                break               # mid-write; retry next poll
            if not acc.add(p, t, dpath, spec, hooks):
                order.skip(name)    # refused for good, not retried
                continue
            ingested[name] = t

            shocked = p > _ARRIVAL_P
            r_front = float(d_charge[shocked].max()) if shocked.any() \
                else 0.0
            st['frac'] = min(1.0, r_front / stop_dist)
            _maybe_adapt(spec, st, adapt, run, hooks, len(ingested))
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
            due = (_due_sparse(hooks.refresh, st['step'], live)
                   and t >= st['t_frame'])
            if due or will_pause:
                hooks.frame(p, t)
                st['t_frame'] = t
                live['step'] = st['step']
                live['draw'] = _time.time()
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
            ingest_live()
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
                _maybe_reconstruct(spec, fields, done=True)
                ingest_ready(final=True)   # final sweep - files complete
                break
    finally:
        if run.running:
            run.kill()
        shutil.rmtree(os.path.join(spec.case_unc, 'postProcessing',
                                   writer.LIVE_SLICE),
                      ignore_errors=True)

    if run.returncode not in (0, None) and not run.stop_requested:
        raise RuntimeError(
            f"blastFoam failed (exit {run.returncode}) - case kept at "
            f"{spec.case_unc}\n{run.tail()}")
    if not ingested:
        raise RuntimeError(
            "blastFoam produced no readable time steps - case kept at "
            f"{spec.case_unc}\n{run.tail()}")

    return _finalize_2d(case, spec, hooks, stop_reason, st['step'],
                        ingested, snap_names, frame_t, frame_p,
                        record_frames, acc)


def _finalize_2d(case, spec, hooks, stop_reason, n_steps, ingested,
                 snap_names, frame_t, frame_p, record_frames, acc):
    """Build the exact native-shaped 2D Result via a two-pass snapshot
    re-read (also used by postmortem.load_run)."""
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
        dpath = os.path.join(spec.case_unc, name)
        got = _read_2d(dpath, spec, ('p', 'rho', 'U'))
        alpha = reader.to_grid(reader.read_scalar(
            os.path.join(dpath, f'alpha.{spec.phase}'), spec.n_cells),
            spec, fill=0.0)
        phase = (alpha > 0.5).astype(int)
        T = reader.to_grid(reader.read_scalar(
            os.path.join(dpath, 'T'), spec.n_cells), spec,
            fill=writer.T_AMB)
        return got, phase, np.where(phase == 1, m.Cv_products,
                                    writer.CV_AIR) * T

    names, (fin, phase, e_arr) = _final_read(
        hooks, names, ingested.get, read_final)
    fin_name = names[-1]
    dfin = os.path.join(spec.case_unc, fin_name)
    snap_names = [n for n in snap_names if n in names]

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
    t_fin = ingested[fin_name]
    snapshots[f"t = {t_fin*1e3:.3f} ms (final)"] = dict(
        p=fin['p'], rho=fin['rho'],
        speed=np.sqrt(fin['u'] ** 2 + fin['v'] ** 2))

    if record_frames > 0 and (not frame_t or frame_t[-1] < t_fin):
        frame_t.append(t_fin)
        frame_p.append(fin['p'].astype(np.float32))
    hooks.frame(fin['p'], t_fin)

    hooks.log(f"\n  Done. {n_steps} solver steps, t_final = "
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
                eos='JWL', bcs=bcs,
                obstacles=[tuple(o) for o in spec.obstacles],
                charge=case.charge, charge_center=(x0, y0),
                r_exp=spec.r_exp, from_profile=False,
                solver='blastfoam', material=spec.material,
                case_dir=spec.case_unc)
    # per-step FO peak/impulse maps, falling back to the per-write Python
    # accumulator (B17: same policy as 3D)
    (meta['p_peak'], meta['impulse'],
     meta['peak_source']) = acc.final(fin['p'], dfin, t_fin, spec)
    meta['final_state'] = dict(t=t_fin, rho=fin['rho'], u=fin['u'],
                               v=fin['v'], e=e_arr, p=fin['p'],
                               phase=phase)
    if record_frames > 0:
        meta['frames'] = dict(times=np.array(frame_t), pressures=frame_p)
    return Result(snapshots, gauge_out, meta, stop_reason,
                  stop_reason == 'stopped by user')


# ── 3D ──────────────────────────────────────────────────────────────────────

def _read_fo_fields(dpath, spec):
    """Optional per-step accumulation fields written by the impulse /
    fieldMinMax function objects (writer plants them for 2D/3D cases).
    Returns (p_peak, impulse) grids or (None, None) when either is
    missing/unreadable - the caller falls back to the Python per-write
    accumulators, so an FO failure degrades instead of stalling."""
    try:
        peak = reader.to_grid(reader.read_scalar(
            os.path.join(dpath, 'pMax'), spec.n_cells), spec,
            fill=P_AIR)
        imp = reader.to_grid(reader.read_scalar(
            os.path.join(dpath, 'impulse'), spec.n_cells), spec,
            fill=0.0)
    except (ValueError, OSError):
        return None, None
    return peak, imp


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
    """Read fields of one time dir onto the native (Nx,Ny,Nz) layout.
    Obstacle-carved cells (absent from the mesh) read back as still
    ambient: p_atm / air density / zero velocity."""
    out = {}
    n = spec.n_cells
    if 'p' in what:
        out['p'] = reader.to_grid(
            reader.read_scalar(os.path.join(dpath, 'p'), n), spec,
            fill=P_AIR)
    if 'rho' in what:
        out['rho'] = reader.to_grid(
            reader.read_scalar(os.path.join(dpath, 'rho'), n), spec,
            fill=RHO_AIR)
    if 'U' in what:
        flat = reader.read_vector(os.path.join(dpath, 'U'), n)
        out['U'] = np.stack([reader.to_grid(flat[:, i], spec)
                             for i in range(3)], axis=-1)
    return out


#: adaptive writeInterval: act at most once per this many ingests
_ADAPT_EVERY = 3


def _maybe_adapt(spec, st, adapt, run, hooks, n_frames):
    """Apply the adaptive-writeInterval controller (all dims; the
    controlDict is runTimeModifiable). Called once per ingested frame."""
    adapt['since'] += 1
    if adapt['since'] < _ADAPT_EVERY or run.stop_requested:
        return
    new_iv = _next_interval(n_frames, st.get('frac') or 0.0,
                            adapt['interval'], spec.write_interval)
    if new_iv is not None and runner.rewrite_control_entry(
            spec.case_posix, spec.case_unc, 'writeInterval', new_iv,
            hooks.log):
        hooks.log(f"  [blastfoam] writeInterval "
                  f"{adapt['interval']*1e3:.4f} -> "
                  f"{new_iv*1e3:.4f} ms (adaptive)")
        adapt['interval'] = new_iv
        adapt['since'] = 0


def _initial_frame(spec, hooks, live_sl=None):
    """Emit the t=0 field as the first live frame: the run's 0/p is
    written by the case writer (uniform ambient before activation), so
    the plot shows a live view immediately instead of staying empty
    until the first time directory lands."""
    try:
        p0 = reader.read_scalar(os.path.join(spec.case_unc, '0', 'p'),
                                spec.n_cells)
    except (OSError, ValueError):
        return
    if spec.dim == 1:
        hooks.frame(np.array([spec.grid['r'], p0]), 0.0)
    else:
        p0 = reader.to_grid(p0, spec, fill=P_AIR)
        hooks.frame(p0 if live_sl is None else p0[live_sl].copy(), 0.0)


def _initial_frame3d(spec, hooks):
    """Emit the t=0 state to an attached 3D viewer, mirroring
    _initial_frame for the plane: the first full write can be many
    solver steps in, and until then the 3D view would stay empty.
    The case's 0/ dir has no plain rho, so ambient density is used."""
    if not hooks.wants_frame3d():
        return
    try:
        p0 = reader.to_grid(reader.read_scalar(
            os.path.join(spec.case_unc, '0', 'p'), spec.n_cells), spec,
            fill=P_AIR)
    except (OSError, ValueError):
        return
    rho0 = np.full_like(p0, RHO_AIR)
    e0 = p0 / (0.4 * rho0)
    hooks.frame3d(0.0, dict(p=p0, rho=rho0, e=e0, p_peak=p0.copy(),
                            imp=np.zeros_like(p0)))


def _next_interval(n_frames, progress, interval, interval0):
    """Pure controller for the adaptive writeInterval (3D runs): keep
    the projected total frame count inside the writer's N_WRITES band.
    Returns the new interval, or None for no change. Doubling backs
    off a too-dense start (near-field shock much faster than the sizing
    estimate); halving recovers frames when the front stalls."""
    est_total = n_frames / max(progress, 0.05)
    if est_total > 1.5 * writer.N_WRITES_MAX:
        new = interval * 2.0
    elif est_total < 0.7 * writer.N_WRITES_MIN and progress > 0.15:
        new = interval / 2.0
    else:
        return None
    new = min(max(new, interval0 / 4.0), interval0 * 8.0)
    if abs(new - interval) < 1e-15 * max(interval, 1e-30):
        return None
    return new


def _d_charge_3d(spec):
    """Distance to the NEAREST charge centre per cell (shock-front
    radius/progress metric; multi-charge aware)."""
    g = spec.grid
    d = None
    for (cx, cy, cz), _mass in spec.charges:
        di = np.sqrt((g['x_c'][:, None, None] - cx) ** 2
                     + (g['y_c'][None, :, None] - cy) ** 2
                     + (g['z_c'][None, None, :] - cz) ** 2)
        d = di if d is None else np.minimum(d, di)
    return d.astype(np.float32)


def _slice_geom_3d(case, spec):
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
            f'{spec.n_cells:,} cells'
            + (' (obstacle cells carved out)' if spec.obstacles else ''),
            '  EOS             : JWL products + ideal-gas air '
            f'(vDet {m.vDet:g} m/s)',
            f'  Boundaries      : {bc_lbl}',
            f'  Obstacles       : {len(spec.obstacles)} '
            f'(carved out of the mesh, rigid walls)'
            if spec.obstacles else '  Obstacles       : 0',
            f'  Gauges          : {n_gauges}',
            '  Stop condition  : '
            + ('shock arrival at an open boundary' if has_open
               else 'safety cap (no open boundaries)'),
            f'  {"End time" if spec.cap_is_end else "Safety cap":<16}: '
            f'{spec.end_time*1e3:.1f} ms',
            f'  Write interval  : {spec.write_interval*1e3:.4f} ms '
            f'(initial, adaptive)',
            '  Live slice      : p sampled every step',
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
    solid = (spec.solid if spec.solid is not None
             else np.zeros((Nx, Ny, Nz), dtype=bool))

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
    open_edge &= ~solid         # carved cells read back as ambient
    has_open = open_edge.any()
    d_charge = _d_charge_3d(spec)
    dists = _stop_dists_3d(case, spec)
    stop_dist = min(dists)
    snap_radii = list(np.linspace(spec.r_exp, min(dists),
                                  n_snapshots + 1)[1:-1])

    # burst-plane slice indices + user live slice (native conventions)
    (j0, k0, slice_axis, s0, live_sl, live_faces, live_labels,
     live_title) = _slice_geom_3d(case, spec)

    _log_banner_3d(hooks, case, spec, len(spec.probe_pts), has_open)
    hooks.run_started(dict(
        dim=3, x_face=live_faces[0], y_face=live_faces[1],
        solid=solid[live_sl], xlabel=live_labels[0],
        ylabel=live_labels[1], title=live_title,
        scene3d=dict(x_c=x_c, y_c=y_c, z_c=z_c, dx=dx, solid=solid,
                     obstacles=[tuple(o) for o in spec.obstacles],
                     Lx=case.Lx, Ly=case.Ly, Lz=case.Lz,
                     charge_center=(x0, y0, z0), r_exp=spec.r_exp,
                     bcs=bcs)))
    _initial_frame(spec, hooks, live_sl)
    _initial_frame3d(spec, hooks)

    record_frames = case.record_frames
    frame_t, frame_p = [], []
    fields = ('p', 'rho', 'U', f'alpha.{spec.phase}')
    ingested = {}               # dirname -> t (full arrays NOT retained)
    snap_names = []             # dirs picked by front-radius crossings
    acc = _PeakImpulse()        # per-write Python + per-step FO accumulators
    order = _OrderedIngest(spec, fields, hooks)
    adapt = dict(interval=spec.write_interval, since=0)
    # frac starts None on purpose: that is what arms _progress_line's
    # t/end_time estimate, so the bar moves from the first solver step
    # instead of sitting at 0 until the first ingested write (below)
    # computes a real shock-front fraction
    st = dict(step=0, t=0.0, dt=0.0, p_max=float(P_AIR), frac=None,
              t_frame=-1.0)
    live = _new_live()
    live3d = _new_live()        # frame3d throttle (viewer refresh policy)
    ax_i = 'xyz'.index(slice_axis)
    uv = [a for a in range(3) if a != ax_i]
    lshape = tuple((Nx, Ny, Nz)[a] for a in uv)
    # the live-slice sample skips carved cells: pass that layer's
    # solid mask so the decoder scatters around it
    slice_solid = solid[live_sl] if solid.any() else None
    stop_reason = 'safety cap'
    stop_deadline = None

    run = runner.FoamRun(spec.case_posix, spec.case_unc,
                         n_procs=spec.n_procs, log=hooks.log)

    def request_stop(reason):
        nonlocal stop_reason, stop_deadline
        stop_reason = reason
        if not run.request_write_now():
            hooks.log('  [blastfoam] graceful stop request did not go '
                      'through - the solver will be killed')
        stop_deadline = _time.time() + _stop_grace(spec)

    def ingest_live():
        _tail_live(spec, hooks, st, live, writer.LIVE_SLICE,
                   lambda tdir: _decode_surface(spec, tdir, lshape,
                                                uv[0], uv[1],
                                                slice_solid))

    def ingest_ready(final=False):
        nonlocal frame_t, frame_p
        _maybe_reconstruct(spec, fields)
        for name, dpath in order.pending(ingested, final):
            will_3d = (_due_sparse(hooks.refresh3d, st['step'], live3d)
                       or hooks.exec_will_pause()) and hooks.wants_frame3d()
            try:
                t, _dt = reader.read_time(dpath)
                got = _read_3d(dpath, spec,
                               ('p', 'rho') if will_3d else ('p',))
            except (ValueError, OSError):
                if order.unreadable(name):
                    continue
                break               # mid-write; retry next poll
            p = got['p']
            if not acc.add(p, t, dpath, spec, hooks):
                order.skip(name)    # refused for good, not retried
                continue
            ingested[name] = t

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

            # adaptive writeInterval (runTimeModifiable controlDict)
            _maybe_adapt(spec, st, adapt, run, hooks, len(ingested))

            if record_frames > 0:
                frame_t.append(t)
                frame_p.append(p[live_sl].astype(np.float32))
                if len(frame_p) >= 2 * record_frames:
                    frame_t = frame_t[::2]
                    frame_p = frame_p[::2]
            will_pause = hooks.exec_will_pause()
            due = (_due_sparse(hooks.refresh, st['step'], live)
                   and t >= st['t_frame'])
            if due or will_pause:
                hooks.frame(p[live_sl].copy(), t)
                st['t_frame'] = t
                live['step'] = st['step']
                live['draw'] = _time.time()
            if will_3d:
                rho = got['rho']
                e_approx = p / (0.4 * np.maximum(rho, 1e-10))
                pk_live, imp_live = acc.live()
                hooks.frame3d(t, dict(p=p, rho=rho, e=e_approx,
                                      p_peak=pk_live, imp=imp_live))
                live3d['step'] = st['step']
                live3d['draw'] = _time.time()
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
            ingest_live()
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
                _maybe_reconstruct(spec, fields, done=True)
                ingest_ready(final=True)   # final sweep - files complete
                break
    finally:
        if run.running:
            run.kill()
        shutil.rmtree(os.path.join(spec.case_unc, 'postProcessing',
                                   writer.LIVE_SLICE),
                      ignore_errors=True)

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

    return _finalize_3d(case, spec, hooks, stop_reason, st['step'],
                        ingested, snap_names, frame_t, frame_p,
                        record_frames, acc)


def _finalize_3d(case, spec, hooks, stop_reason, n_steps, ingested,
                 snap_names, frame_t, frame_p, record_frames, acc):
    """Build the exact native-shaped 3D Result via a two-pass snapshot
    re-read - bounds run-time memory (also used by postmortem)."""
    g = spec.grid
    x_c, y_c, z_c = g['x_c'], g['y_c'], g['z_c']
    dx = spec.dx
    x0, y0, z0 = spec.center
    bcs = dict(case.bcs)
    solid = (spec.solid if spec.solid is not None
             else np.zeros((spec.nx, spec.ny, spec.nz), dtype=bool))
    j0, k0, slice_axis, s0, live_sl = _slice_geom_3d(case, spec)[:5]

    names = sorted(ingested, key=ingested.get)
    names, fin = _final_read(
        hooks, names, ingested.get,
        lambda name: _read_3d(os.path.join(spec.case_unc, name), spec,
                              ('p', 'rho', 'U')))
    fin_name = names[-1]
    snap_names = [n for n in snap_names if n in names]

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
    t_fin = ingested[fin_name]
    snapshots[f"t = {t_fin*1e3:.3f} ms (final)"] = _snapshot_payload(
        fin['p'], fin['rho'], fin['U'], j0, k0, t_fin)

    # final-dir FO fields (per-step accumulation) supersede the per-write
    # Python accumulator; a stale FO read does not (B17)
    p_peak, impulse, peak_source = acc.final(
        fin['p'], os.path.join(spec.case_unc, fin_name), t_fin, spec)
    if record_frames > 0 and (not frame_t or frame_t[-1] < t_fin):
        frame_t.append(t_fin)
        frame_p.append(fin['p'][live_sl].astype(np.float32))
    hooks.frame(fin['p'][live_sl].copy(), t_fin)
    e_approx = fin['p'] / (0.4 * np.maximum(fin['rho'], 1e-10))
    hooks.frame3d(t_fin, dict(p=fin['p'], rho=fin['rho'], e=e_approx,
                              p_peak=p_peak, imp=impulse), force=True)

    hooks.log(f"\n  Done. {n_steps} solver steps, t_final = "
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
                eos='JWL', bcs=bcs,
                obstacles=[tuple(o) for o in spec.obstacles],
                charge=case.charge, charge_center=(x0, y0, z0),
                r_exp=spec.r_exp, r_src=spec.r_exp, from_profile=None,
                solver='blastfoam', material=spec.material,
                case_dir=spec.case_unc,
                p_peak=p_peak, impulse=impulse, peak_source=peak_source)
    if record_frames > 0:
        meta['frames'] = dict(times=np.array(frame_t), pressures=frame_p)
    return Result(snapshots, gauge_out, meta, stop_reason,
                  stop_reason == 'stopped by user')
