"""The blastFoam run loop shared by the 1D/2D/3D backends (ROADMAP A1).

Run loop model: blastFoam streams stdout (every step prints `Time =`,
`deltaT =` and `max(p):` lines -> Progress), while written time
directories are polled and ingested as backend "steps" (live frames,
step_gate, stop conditions). Graceful stop and the shock-arrival
condition both go through `stopAt writeNow` so a final complete time
directory is always written.

`FoamRunLoop` owns everything the three dims share: starting the solver,
stdout pumping, time-dir polling + readiness + strictly ordered ingest,
stop-request -> writeNow -> grace -> kill escalation, the final drain and
sweep, the adaptive writeInterval controller and the `finally` cleanup.
The per-dim work is two callbacks: `read_dir(name, dpath)` reads one
time dir (raising ValueError/OSError on a torn file, which the loop
treats as "retry next poll") and `on_frame(name, dpath, payload)` turns
that read into frames/snapshots/stop decisions (return False to have the
dir skipped for good). `solve_*_foam` in backend.py are thereby
preflight -> callbacks -> `FoamRunLoop(...).run()` -> `finalize_*`.

Every log string here is load-bearing: the GUI and the tests grep them.
"""

import os
import re
import shutil
import time as _time

import numpy as np

from ...core.constants import P_AIR
from ..hooks import Progress
from . import reader, runner, writer

_RE_TIME = re.compile(r'^Time = ([0-9.eE+-]+)s?$')
_RE_DT = re.compile(r'^deltaT = ([0-9.eE+-]+)$')
#: blastFoam prints `max(p): X, min(p): Y` on one line. The min was
#: parsed away for years; it is captured now for the instability message
#: only - a strong rarefaction can dip negative and recover, so it is NOT
#: a stop trigger. group(1) is unchanged, so every existing match is too.
_RE_MAXP = re.compile(r'^max\(p\):\s*([0-9.eE+-]+)'
                      r'(?:,\s*min\(p\):\s*([0-9.eE+-]+))?')

ARRIVAL_P = 1.001 * P_AIR       # native shock-arrival threshold
STOP_GRACE_S = 60.0             # writeNow -> kill escalation window
POLL_S = 0.25
#: polls a torn earlier dir may hold up ingest once later dirs are complete
STALL_POLLS = 20
#: adaptive writeInterval: act at most once per this many ingests
ADAPT_EVERY = 3
#: solver stdout lines tolerated before the first `Time = ` match. The
#: regex below is load-bearing - step counting, the progress bar and the
#: live-frame cadence all hang off it - so a blastFoam release that
#: reworded its time banner would silently freeze all three. One warning
#: after this many lines is the canary (A6). blastFoam's own header is
#: well under 100 lines.
TIME_CANARY_LINES = 500

#: A blastFoam run whose deltaT collapses toward zero does not fail fast:
#: it spins, the solver clock stops advancing at print precision, and it
#: finally dies inside compressibleBlastSystem::decode() dividing rhoU by
#: a zero density - SIGFPE, exit 136, no result at all. Measured on a
#: profile+AMR 3D case: deltaT fell 6.4e-06 -> 1e-08 -> 7.5e-12 over ~43
#: steps with the clock frozen, and the user just waited.
#: deltaT is compared to its own RUNNING MAXIMUM, so the small-and-growing
#: deltaT of a healthy start cannot trip this, and neither can a run with
#: adjustTimeStep off (dt == dt_max forever). The stalled-clock conjunct
#: is what separates "unstable" from "legitimately tiny fixed step".
DT_COLLAPSE_FRAC = 1e-3
COLLAPSE_STEPS = 15
COLLAPSE_STEPS_HARD = 60
CLOCK_STUCK_STEPS = 3
MIN_STABLE_STEPS = 20

#: stop_reason for the above. Deliberately NOT 'stopped by user' (the
#: exact string three backends key stopped_early off) and deliberately
#: not in backend._NATURAL_END, so the W2 gauge-tail note still fires.
STOP_UNSTABLE = 'numerical instability'

#: FOAM warnings that are inherent to the collapsed-hex sector/wedge
#: meshes (1D sector, 2D axisym): the apex face degenerates into the
#: default patch, and the 1-degree wedge planarity residual is ~1e-16
#: (pure float round-off - the vendor's own wedge tutorials print the
#: same). Summarized once instead of spamming the log.
BENIGN_WARN = ('undefined faces in mesh; adding to default patch',
               'is not planar')


def stop_grace(spec):
    """writeNow -> kill escalation window: a big mesh needs longer to
    finish the current step + final write."""
    return max(STOP_GRACE_S, spec.n_cells / 2e5)


def maybe_reconstruct(spec, fields, done=False):
    """Parallel runs: reconstruct processor time dirs that are complete
    on every rank and absent top-level, so the ingest loops read
    reconstructed dirs indistinguishable from serial output. Quietly
    retries next poll on failure. `done` lifts the per-poll batch cap
    (final sweep after the solver exits)."""
    if spec.n_procs <= 1 or spec.decomposed:
        # `decomposed` (parallel AMR, N16-b/T42): reconstructPar cannot
        # follow a mesh that changes between writes, so those runs are
        # ingested straight from processor*/ instead.
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


def check_stability(st, hooks, t):
    """Latch st['unstable'] when the run has gone numerically unstable.

    Called once per `Time =` line, BEFORE st['t'] is overwritten, so `t`
    is the new value and st['t'] is still the previous one.

    Same shape as the A6 time canary: this only sets a flag and logs
    once - `progress_line` stays a pure module-level function with no
    reference to the loop, and the loop body decides what to do. Returns
    True once tripped.
    """
    if st.get('unstable'):
        return True
    dt, dt_max = st.get('dt', 0.0), st.get('dt_max', 0.0)
    if dt_max > 0.0 and 0.0 < dt < DT_COLLAPSE_FRAC * dt_max:
        st['dt_low'] = st.get('dt_low', 0) + 1
    else:
        st['dt_low'] = 0
    st['t_stuck'] = (st.get('t_stuck', 0) + 1) if t <= st.get('t', 0.0) else 0
    low, stuck = st['dt_low'], st['t_stuck']
    if st.get('step', 0) < MIN_STABLE_STEPS:
        return False
    if not (low >= COLLAPSE_STEPS_HARD
            or (low >= COLLAPSE_STEPS and stuck >= CLOCK_STUCK_STEPS)):
        return False
    st['unstable'] = STOP_UNSTABLE
    pmin = st.get('p_min')
    hooks.log(
        f"  [blastfoam] the solve has gone unstable: deltaT collapsed to "
        f"{dt:.2e} s ({dt / dt_max:.1e} of the {dt_max:.2e} s it had "
        f"reached)" + (f", min(p) = {pmin:.3e} Pa" if pmin is not None else "")
        + f", and the solver clock has not advanced for {stuck} steps at "
        f"t = {t:.6g} s.\n"
        f"  [blastfoam] stopping at the next written frame - waiting it "
        f"out ends in a divide-by-zero density (SIGFPE) with no result at "
        f"all. What is already written is kept; a lower CFL number or a "
        f"lower AMR level usually clears it.")
    return True


def progress_line(line, st, hooks, end_time):
    """Parse one solver stdout line into Progress state. st['frac'],
    when not None, overrides the t/end_time estimate (3D uses the
    shock-front radius, updated per ingested write). FOAM warning
    blocks are multi-line ('--> FOAM Warning :' then From/in file then
    the message) - the actual message is captured and logged; the
    benign sector-wedge warnings collapse into one note."""
    m = _RE_TIME.match(line)
    if not m and not st['step'] and not st.get('time_canary'):
        # never yet seen a `Time = ` line: count how long that lasts
        st['no_time'] = st.get('no_time', 0) + 1
        if st['no_time'] >= TIME_CANARY_LINES:
            st['time_canary'] = True
            hooks.log("  [warn] blastFoam output format changed? no "
                      "'Time =' lines yet - live cadence and progress "
                      "may stall")
    if m:
        t = float(m.group(1))
        check_stability(st, hooks, t)
        st['t'] = t
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
        st['dt_max'] = max(st.get('dt_max', 0.0), st['dt'])
        return
    m = _RE_MAXP.match(line)
    if m:
        st['p_max'] = float(m.group(1))
        if m.group(2) is not None:
            st['p_min'] = float(m.group(2))
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
        if any(s in ls for s in BENIGN_WARN):
            if not st.get('warn_benign_noted'):
                st['warn_benign_noted'] = True
                hooks.log('  [blastfoam] note: benign wedge-geometry '
                          'warnings from the sector mesh (collapsed '
                          'apex / ~1e-16 planarity round-off) - '
                          'expected, harmless')
        else:
            hooks.log('  [foam] Warning: ' + ls)


def note_pause(hooks, st, will_pause):
    """One-time note: foam Exec/Interrupt operates at written-frame
    granularity (not per solver step like the native solvers)."""
    if will_pause and not st.get('pause_noted'):
        st['pause_noted'] = True
        hooks.log('  [blastfoam] pausing at a written frame - the WSL '
                  'solver is suspended while paused; Exec advances by '
                  'written frames, Stop ends the run')


def gated_step(run, hooks):
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


def tail_live(spec, hooks, st, live, set_name, decode):
    """Shared live-sample tail (1D line / 2D+3D slice): poll the
    postProcessing/<set_name> dirs, emit at most one hooks.frame per
    call (the newest complete sample), delete consumed dirs so disk
    use stays bounded. `decode(tdir)` -> frame payload or None while
    the sample is still mid-write; a `(field, levels)` tuple carries a
    dynamic-AMR frame's level map. The GUI refresh policy is honored:
    seconds mode throttles wall time, steps mode gates on solver steps
    since the last emitted live frame."""
    entries = reader.list_sample_times(spec.case_unc, set_name)
    fresh = [(t, n) for t, n in entries if n not in live['seen']]
    if not fresh:
        return
    mode, val = hooks.refresh
    if mode == 'steps' and live.get('fo_steps') == max(1, int(val)):
        pass    # the sample cadence IS the policy: every sample shows
    elif not due_sparse(hooks.refresh, st['step'], live):
        return
    for t, name in reversed(fresh):
        payload = decode(name)
        if payload is None:
            continue
        if t >= st['t_frame']:
            if isinstance(payload, tuple):
                hooks.frame(payload[0], t, levels=payload[1])
            else:
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


def new_live():
    return dict(seen=set(), step=-(10 ** 9), draw=0.0)


def due_sparse(policy, step, last):
    """Refresh-policy check for the foam ingest paths. Unlike the
    native solvers, these are evaluated only when output lands on disk
    - at arbitrary step counts - so steps mode gates on solver steps
    elapsed since the last emitted frame (RunHooks._due's `step % n`
    form would almost never hit here). `last` carries the previous
    emission: 'step' and 'draw' (wall time), as built by new_live()."""
    mode, val = policy
    if mode == 'steps':
        return step - last['step'] >= max(1, int(val))
    return _time.time() - last['draw'] > float(val)


def read_fo_fields(dpath, spec, mesh=None):
    """Optional per-step accumulation fields written by the impulse /
    fieldMinMax function objects (writer plants them for 2D/3D cases).
    Returns (p_peak, impulse) grids or (None, None) when either is
    missing/unreadable - the caller falls back to the Python per-write
    accumulators, so an FO failure degrades instead of stalling.
    `mesh` is the time dir's own structure on a dynamic-AMR run."""
    from . import backend
    n = spec.n_cells if mesh is None else mesh.n_cells
    try:
        peak = reader.to_grid(backend.rd_scalar(spec, dpath, 'pMax', n),
                              spec, fill=P_AIR, mesh=mesh)
        imp = reader.to_grid(backend.rd_scalar(spec, dpath, 'impulse', n),
                             spec, fill=0.0, mesh=mesh)
    except (ValueError, OSError):
        return None, None
    return peak, imp


def level_counts(counts):
    """'L0 4,753 / L1 5,776 / L2 161,600' from a MeshMap's counts."""
    return ' / '.join(f'L{l} {int(c):,}' for l, c in enumerate(counts))


def amr_note(mesh, n_prev, t):
    """The per-write AMR log line: cells of this write, change against
    the previous write and the per-level histogram."""
    d = mesh.n_cells - (mesh.n_cells if n_prev is None else int(n_prev))
    return (f'  [blastfoam] AMR t = {t*1e3:.3f} ms: {mesh.n_cells:,} cells '
            f'({d:+,}), {level_counts(mesh.counts)}')


def next_interval(n_frames, progress, interval, interval0):
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


def maybe_adapt(spec, st, adapt, run, hooks, n_frames):
    """Apply the adaptive-writeInterval controller (all dims; the
    controlDict is runTimeModifiable). Called once per ingested frame."""
    if not getattr(spec, 'adaptive_write', True):
        return                      # writeInterval pinned for this run
    adapt['since'] += 1
    if adapt['since'] < ADAPT_EVERY or run.stop_requested:
        return
    new_iv = next_interval(n_frames, st.get('frac') or 0.0,
                           adapt['interval'], spec.write_interval)
    if new_iv is not None and runner.rewrite_control_entry(
            spec.case_posix, spec.case_unc, 'writeInterval', new_iv,
            hooks.log):
        hooks.log(f"  [blastfoam] writeInterval "
                  f"{adapt['interval']*1e3:.4f} -> "
                  f"{new_iv*1e3:.4f} ms (adaptive)")
        adapt['interval'] = new_iv
        adapt['since'] = 0
        hooks.cadence(dt=new_iv)    # the live view says how fast it moves


class OrderedIngest:
    """Strictly time-ordered time-dir ingest (ROADMAP B16).

    A pass over `pending()` stops at the first dir that is not ready yet,
    so a later write never lands before an earlier one (which used to
    feed a negative dt to the impulse accumulator and make the recorded
    frame timeline non-monotonic). A dir that stays unreadable for
    STALL_POLLS polls *after a later dir is already complete* is skipped
    for good with one log line; on the final sweep (solver exited, files
    complete) any gap is skipped at once so nothing readable is lost."""

    def __init__(self, spec, fields, hooks):
        self.spec, self.fields, self.hooks = spec, fields, hooks
        self.stalls = {}
        self._times, self._i, self._done, self._final = [], 0, {}, False

    def _ready(self, name):
        """A time is ready when EVERY part of it is - on a decomposed
        AMR run the ranks finish their writes independently."""
        d = self.spec.time_dirs(name)
        parts = d if isinstance(d, (list, tuple)) else [d]
        return all(reader.time_ready(p, self.fields) for p in parts)

    def pending(self, done, final=False):
        """Yield (name, dpath) in ascending time; ends at the first gap.
        `dpath` is a list of per-rank dirs on a decomposed AMR run."""
        self._done, self._final = done, final
        self._times = reader.list_times(self.spec.time_root())
        for i, (_t_disp, name) in enumerate(self._times):
            if name in done or self.stalls.get(name, 0) >= STALL_POLLS:
                continue
            self._i = i
            dpath = self.spec.time_dirs(name)
            if not self._ready(name):
                # the writer's own initial-condition dir, not a solver
                # write: '0' for a charge case, t0 for a profile stage,
                # which under AMR has no cellLevel of its own to be
                # "ready" with (T70). Either way the initial state
                # reaches the view through _initial_frame.
                if _t_disp == 0.0 or name == self.spec.start_dir:
                    continue
                if self.unreadable(name):
                    continue
                return
            yield name, dpath

    def unreadable(self, name):
        """Register that `name` could not be ingested on this poll (not
        ready, or torn mid-write). True -> skip it permanently; False ->
        end the pass and retry it next poll."""
        if self._final:
            inc = STALL_POLLS
        elif any(n2 not in self._done and self._ready(n2)
                 for _t2, n2 in self._times[self._i + 1:]):
            inc = 1                 # later writes are complete: it should be too
        else:
            return False            # newest write still in progress: normal
        n = self.stalls.get(name, 0) + inc
        self.stalls[name] = n
        if n < STALL_POLLS:
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
        self.stalls[name] = STALL_POLLS


class PeakImpulse:
    """Per-write Python p_peak/impulse accumulator with blastFoam's
    per-step pMax/impulse function-object fields layered on top.
    Remembers the time each source last covered so `final()` can tell a
    fresh FO read from a stale one (ROADMAP B17)."""

    def __init__(self):
        self.p_peak = self.impulse = None
        self.t_py = None
        self.fo_peak = self.fo_imp = None
        self.t_fo = None
        self._noted = False

    def add(self, p, t, dpath, spec, hooks, mesh=None):
        """Accumulate one ingested write. False (logged) when t is before
        the last accumulated time - unreachable with OrderedIngest, kept
        as the guard B16 asks for; the caller then skips the dir.
        `mesh` is the write's own structure on a dynamic-AMR run."""
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
        got_peak, got_imp = read_fo_fields(dpath, spec, mesh=mesh)
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

    def final(self, p_fin, dfin, t_fin, spec, mesh=None):
        """(p_peak, impulse, peak_source) for the Result.
        Order: the final dir's FO fields; an FO read that already covers
        t_fin; the Python accumulator - 'python-fallback' when FO data
        exists but is older than the final frame (the stale-FO case B17
        fixes), 'python-writes' when the case never produced FO fields."""
        if self.p_peak is None:
            self.p_peak = p_fin.copy()
            self.impulse = np.zeros_like(p_fin)
        np.maximum(self.p_peak, p_fin, out=self.p_peak)
        got_peak, got_imp = read_fo_fields(dfin, spec, mesh=mesh)
        if got_peak is not None:
            return got_peak, got_imp, 'foam-fo'
        if self.fo_peak is not None and self.t_fo >= t_fin:
            return self.fo_peak, self.fo_imp, 'foam-fo'
        return (self.p_peak, self.impulse,
                'python-fallback' if self.fo_peak is not None
                else 'python-writes')


class FoamRunLoop:
    """One blastFoam run from `FoamRun` start to solver exit.

    `done` is the caller's dirname -> ... mapping of ingested dirs (the
    1D `store`, the 2D/3D `ingested`); the loop only reads it for
    ordering and for the "no readable time steps" check. `live_set` is
    the postProcessing sample set (`writer.LIVE_SET` / `LIVE_SLICE`)
    decoded by `decode(tdir)` for live frames between writes; None
    (dynamic-AMR runs, whose live frames come from the written times)
    disables the live tail.

    Attributes the callbacks use: `st` (progress state: step/t/dt/
    p_max/frac/t_frame), `live` (live-frame throttle, see new_live),
    `stop_requested`, `request_stop(reason)`, `maybe_adapt(n_frames)`,
    `note_pause(will_pause)`, `gated_step()`. Constructing the loop
    starts the solver, exactly where the inline loops created FoamRun."""

    def __init__(self, spec, hooks, fields, done, live_set, decode,
                 read_dir, on_frame):
        self.spec, self.hooks, self.fields, self.done = (spec, hooks,
                                                         fields, done)
        self.live_set, self.decode = live_set, decode
        self.read_dir, self.on_frame = read_dir, on_frame
        self.order = OrderedIngest(spec, fields, hooks)
        # frac starts None on purpose: that is what arms progress_line's
        # t/end_time estimate, so the bar moves from the first solver
        # step instead of sitting at 0 until the first ingested write
        # computes a real shock-front fraction
        self.st = dict(step=0, t=0.0, dt=0.0, p_max=float(P_AIR),
                       frac=None, t_frame=-1.0)
        self.live = new_live()
        # live-sample cadence [solver steps] the case was written with;
        # _sync_live_steps follows the GUI's "Refresh every N steps"
        self.live_steps = int(getattr(spec, 'live_steps', 0)
                              or writer.live_sample_steps(spec.dim))
        self.live['fo_steps'] = self.live_steps
        self.adapt = dict(interval=spec.write_interval, since=0)
        self.stop_reason = 'safety cap'
        self.stop_deadline = None
        self.foam = runner.FoamRun(spec.case_posix, spec.case_unc,
                                   n_procs=spec.n_procs, log=hooks.log)

    @property
    def stop_requested(self):
        return self.foam.stop_requested

    def request_stop(self, reason):
        """Graceful stop: `stopAt writeNow`, then kill after the grace."""
        self.stop_reason = reason
        if not self.foam.request_write_now():
            self.hooks.log('  [blastfoam] graceful stop request did not '
                           'go through - the solver will be killed')
        self.stop_deadline = _time.time() + stop_grace(self.spec)

    def maybe_adapt(self, n_frames):
        maybe_adapt(self.spec, self.st, self.adapt, self.foam, self.hooks,
                    n_frames)

    def note_pause(self, will_pause):
        note_pause(self.hooks, self.st, will_pause)

    def gated_step(self):
        gated_step(self.foam, self.hooks)

    def _sync_live_steps(self):
        """'Refresh every N steps' -> the live-sample function object
        writes every N solver steps (the controlDict is
        runTimeModifiable), so the live view follows the setting
        instead of the fixed per-dim cadence; blank / seconds restore
        the default. One rewrite per change, never retried per poll."""
        if self.live_set is None:
            return
        want = writer.live_steps_for(self.hooks.refresh, self.spec.dim)
        if want == self.live_steps:
            return
        self.live_steps = want
        if runner.rewrite_control_entry(
                self.spec.case_posix, self.spec.case_unc, 'writeInterval',
                want, self.hooks.log, within=self.live_set):
            self.live['fo_steps'] = want
            self.hooks.cadence(steps=want)
            self.hooks.log(f'  [blastfoam] live sample every {want} '
                           f'solver step(s)')
        else:
            self.live['fo_steps'] = None    # tail falls back to due_sparse

    def _ingest_live(self):
        if self.live_set is None:
            return
        self._sync_live_steps()
        tail_live(self.spec, self.hooks, self.st, self.live, self.live_set,
                  self.decode)

    def _ingest_ready(self, final=False):
        maybe_reconstruct(self.spec, self.fields)
        for name, dpath in self.order.pending(self.done, final):
            try:
                payload = self.read_dir(name, dpath)
            except (ValueError, OSError):
                if self.order.unreadable(name):
                    continue
                break               # mid-write over 9p; retry next poll
            if self.on_frame(name, dpath, payload) is False:
                self.order.skip(name)   # refused for good, not retried

    def run(self):
        """Drive the solver to completion (or stop/kill). Returns the
        stop reason; raises RuntimeError when the solver failed or
        produced no readable time step (case dir kept either way)."""
        spec, hooks, foam = self.spec, self.hooks, self.foam
        try:
            while True:
                for line in foam.drain(POLL_S):
                    progress_line(line, self.st, hooks, spec.end_time)
                self._ingest_live()
                self._ingest_ready()
                if hooks.should_stop() and not foam.stop_requested:
                    self.request_stop('stopped by user')
                # after the user's stop, so an explicit stop still wins
                # and keeps its own reason
                if self.st.get('unstable') and not foam.stop_requested:
                    self.request_stop(STOP_UNSTABLE)
                if self.stop_deadline and foam.running \
                        and _time.time() > self.stop_deadline:
                    hooks.log('  [blastfoam] solver did not stop cleanly '
                              '- killing it')
                    foam.kill()
                if not foam.running:
                    for line in foam.drain(0.05):
                        progress_line(line, self.st, hooks, spec.end_time)
                    maybe_reconstruct(spec, self.fields, done=True)
                    self._ingest_ready(final=True)  # final sweep - files complete
                    break
        finally:
            # give a solver that is already tearing down a moment to
            # reach its graceful End: the ingest breaks out the instant
            # the final write LANDS, while blastProbes only flushes its
            # buffered gauge samples in the FO destructors - killing
            # here threw those samples away on every stopped run (and
            # on every resumed one, T43/N6: 5 of ~600 samples survived)
            for _ in range(100):
                if not foam.running:
                    break
                _time.sleep(0.1)
            if foam.running:
                foam.kill()
            # live samples are display-only; drop the leftovers so a kept
            # case dir holds just the real record (time dirs + probes)
            if self.live_set:
                shutil.rmtree(os.path.join(spec.case_unc, 'postProcessing',
                                           self.live_set),
                              ignore_errors=True)

        if foam.returncode not in (0, None) and not foam.stop_requested:
            raise RuntimeError(
                f"blastFoam failed (exit {foam.returncode}) - case kept at "
                f"{spec.case_unc}\n{foam.tail()}")
        if not self.done:
            raise RuntimeError(
                "blastFoam produced no readable time steps - case kept at "
                f"{spec.case_unc}\n{foam.tail()}")
        return self.stop_reason
