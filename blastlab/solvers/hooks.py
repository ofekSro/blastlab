"""Run hooks: how a running solver talks to the outside world.

The solvers never print or draw directly; they call the hooks. The CLI
uses ConsoleHooks (reproduces the historical console output and the
matplotlib live window); the GUI supplies its own hooks that forward to
a Tk-safe queue.
"""

import threading
import time

#: serialises run.log appends: the solver thread and the blastFoam run
#: loop's helper threads can log at once
_LOG_FILE_LOCK = threading.Lock()


#: memory budget for the recorded replay frames [bytes]. The record
#: is a convenience (the Animation tab and the exported video), not
#: the run's result, so it must never be what makes a run run out of
#: RAM - which is what happened on a 640^2 AMR run holding 614 MB of
#: frames while blastFoam and the GUI wanted the same memory.
FRAME_MEM_BUDGET = 200_000_000


def frame_mem_budget(host_ram_gb=None):
    """N21: the same budget, sized to the host. Unlike the viewer's
    playback store this one lives in the GUI process itself - the one
    that actually dies of a MemoryError - so a small machine must get
    less than the fixed 200 MB."""
    from ..core.hardware import memory_budget
    return memory_budget(host_ram_gb, 0.03, 50_000_000, FRAME_MEM_BUDGET)


def frame_budget(record_frames, n_disp, hooks=None, amr=False,
                 budget=None):
    """`record_frames` capped so the replay record fits the budget.

    One frame costs 4 bytes per display cell (the float32 pressure)
    plus 1 more on an AMR run, which also records that frame's int8
    level map."""
    if record_frames <= 0 or n_disp <= 0:
        return record_frames
    per_frame = (5 if amr else 4) * int(n_disp)
    if budget is None:
        from ..core.hardware import host
        budget = frame_mem_budget(host().get('ram_gb'))
    cap = max(8, int(budget // per_frame))
    if record_frames > cap and hooks is not None:
        hooks.log(f"  [note] Replay frames reduced {record_frames} -> "
                  f"{cap} to bound frame memory "
                  f"({per_frame / 1e6:.2f} MB per frame at "
                  f"{int(n_disp):,} display cells; a coarser cell or a "
                  f"lower AMR display level buys more frames)")
    return min(record_frames, cap)


def trigger_index(trigger_gauge, n_gauges, hooks):
    """The 0-based index of the T51 trigger gauge, or None.

    `trigger_gauge` is what the case carries: a 1-BASED gauge number so
    it reads like the gauge table and the plot labels. Out-of-range (or
    a run whose gauges were all dropped, outside the domain or in a
    wall) warns and disables the trigger rather than failing the run."""
    if trigger_gauge in (None, 0, ''):
        return None
    try:
        k = int(trigger_gauge) - 1
    except (TypeError, ValueError):
        k = -1
    if not 0 <= k < n_gauges:
        hooks.log(f"  [warn] Trigger gauge {trigger_gauge} does not exist "
                  f"({n_gauges} gauge(s)) - trigger disabled")
        return None
    return k


# Phase 2 (docs/ARCHITECTURE_REVIEW.md section 5): Progress, Result and
# StoppedBeforeStart live in models/result.py. Re-exported here, so
# `isinstance(x, Result)` holds whichever path Result came from.
from ..models.result import Progress, Result, StoppedBeforeStart  # noqa: F401


class RunHooks:
    """No-op base. Override any subset."""

    #: Optional 3D viewer client (duck-typed: .alive, .send_frame(t,
    #: fields)). Attached externally; the solver only talks to it through
    #: wants_frame3d()/frame3d() so nothing here imports pyvista.
    viewer3d = None

    #: Live-view refresh policy, ('seconds', s) or ('steps', n): how
    #: often the solvers emit frame()/frame3d(). The GUI exposes these
    #: as a Run-tab input; the defaults reproduce historical behaviour.
    refresh = ('seconds', 0.05)
    refresh3d = ('seconds', 0.2)

    #: OUT-1: the model folder's run.log while a stage writes into one,
    #: else None. `log` appends every line to it (see `log_to_file`).
    log_file = None

    #: OUT-1: the WSL scratch directory (posix) of the blastFoam run on
    #: these hooks, set by backend._preflight / resume_run once the case
    #: directory is known. None for a native run.
    scratch_posix = None

    #: OUT-2: `<stage folder>\vtk` while a blastFoam stage with a VTK
    #: family writes into a model folder (model_folder.stage_solve), else
    #: None - and then the run's VTK export is inactive (batch plan D12)
    vtk_dir = None

    #: OUT-3: set by model_folder.stage_solve for a blastFoam stage.
    #: `purge_fields`: keep only the newest writes in WSL (the default);
    #: `keep_all_fields`: the "Keep all fields in WSL" box - no written
    #: time is deleted. `fields_deleted`: the set of written times the
    #: run deleted in WSL (vtk_export.VtkExport), None outside a stage.
    purge_fields = False
    keep_all_fields = False
    fields_deleted = None

    @staticmethod
    def _due(policy, step, last_draw):
        mode, val = policy
        if mode == 'steps':
            return step % max(1, int(val)) == 0
        return time.time() - last_draw > float(val)

    def draw_due(self, step, last_draw):
        """True when a live frame() is due this step."""
        return self._due(self.refresh, step, last_draw)

    def draw3d_due(self, step, last_draw):
        """True when a frame3d() is due this step."""
        return self._due(self.refresh3d, step, last_draw)

    def run_started(self, info):
        """Called once after grid setup. `info` carries what a live view
        needs: dim, x_face, y_face (2D) / z_face + solid slice (3D),
        solid mask/slice, slice label. 3D runs add a 'scene3d' sub-dict
        (grid coords, solid mask, obstacles) for the 3D viewer."""

    def cadence(self, dt=None, steps=None):
        """How often live frames are expected.

        A blastFoam run cannot emit a frame per step: the live view moves
        at the live-sample cadence (`steps` solver steps) or, without one,
        at `writeInterval` (`dt` simulation seconds) - and both can move
        mid-run. Either argument may be None for "unchanged". Native runs
        never call this; they emit whenever the refresh policy allows.
        """

    def log(self, msg):
        """A line of run output (summaries, notes, warnings)."""

    def log_to_file(self, msg):
        """Append one log line to `log_file` (UTF-8, LF), when one is set.

        This is the model folder's run.log (OUT-1): the solver-side log,
        i.e. every line that goes through `log` - what the Run tab shows
        minus the lines the GUI adds itself ('[run finished]', the error
        dialog text). A failed append never disturbs the run: an
        unencodable character becomes '?', an unwritable file is skipped."""
        path = self.log_file
        if not path:
            return
        try:
            with _LOG_FILE_LOCK, open(path, 'a', encoding='utf-8',
                                      errors='replace', newline='\n') as f:
                f.write(f'{msg}\n')
        except (OSError, ValueError):
            pass

    def folder_written(self, stage_dir, manifest, notice=None):
        """OUT-1: a stage has finished writing its model folder. Called on
        the worker thread, before the stage's 'result' / 'error', with
        the manifest dict and a kept-scratch dialog text (or None). A
        front end that runs several stages on one hooks object reads the
        outcome from here, not from `hooks.stage_manifest`, which the
        next stage overwrites."""

    def progress(self, p: Progress):
        """Called every step (cheap; receivers throttle themselves)."""

    def frame(self, field2d, t, levels=None):
        """Live pressure field: 2D array (3D runs pass the x-z slice
        through the burst; 1D runs pass the (r, p) profile pair).
        `levels` (dynamic-AMR runs only) is that frame's level map on
        the same plane, for a mesh overlay that follows the run."""

    def wants_frame3d(self):
        """True while an interactive 3D viewer is attached and open."""
        v = self.viewer3d
        return v is not None and v.alive

    def frame3d(self, t, fields, force=False):
        """Full 3D fields for the interactive viewer. `fields` is a dict
        of references ({'p': ..., 'rho': ...}); the client copies what it
        sends, the solver arrays are never retained. force bypasses the
        client's throttle (the final frame of a run)."""
        if self.wants_frame3d():
            self.viewer3d.send_frame(t, fields, force=force)

    def wants_surf3d(self):
        """True while a 3D view is open AND the run can sample faster
        than it writes."""
        return False

    def surf3d(self, t, field2d):
        """The live-slice plane, at the SAMPLE cadence, for the 3D view.

        A blastFoam run can only emit `frame3d` when a full field has
        been written, which is every writeInterval - measured at one
        frame every 8.6 s on a real 3D run, while the 2D live slice was
        arriving about four times a second from the same case. The
        sampled plane is already being read for that 2D view; this hands
        the same array to the 3D scene so its burst plane moves at the
        rate the solver samples instead of the rate it writes.

        It is ONE plane: the rest of the scene stays at the last written
        frame, and the viewer says so rather than implying the whole
        volume is that fresh.
        """

    def wants_gauges(self):
        """True while something is watching the gauge traces live."""
        return False

    def gauges(self, payload):
        """The gauge series SO FAR, for a live trace.

        `payload` is the same shape the finished run reports -
        dict(times, pressures, points|radii, ...) - truncated at the
        current time rather than being a delta, because the receiver
        redraws whole traces anyway and a delta would need it to keep
        state the solver already has. Emitted on the live-frame cadence,
        so a run with no gauges or no watcher costs nothing.
        """

    def should_stop(self):
        """Return True to end the run after the current step."""
        return False

    def step_gate(self):
        """Called once per time step, after the live-frame emission and
        before the state update. May block to implement stepped
        execution (GUI 'Exec N' / 'Interrupt'); implementations must
        return promptly once should_stop() turns True. Default: never
        blocks."""

    def exec_will_pause(self):
        """True when the coming step_gate() call will block. The solver
        uses this to force a live frame out (bypassing draw throttles)
        so the paused state is what the user sees."""
        return False


_STEP_EVERY = {1: 1000, 2: 200, 3: 50}
_STEP_FMT = {
    1: "  step {step:7d}  t = {t:7.3f} ms  dt = {dt:.2e} s  p_max = {p:.3e} Pa",
    2: "  step {step:7d}  t = {t:7.3f} ms  dt = {dt:.2e} s  p_max = {p:.3e} Pa",
    3: "  step {step:6d}  t = {t:7.3f} ms  dt = {dt:.2e} s  p_max = {p:.3e} Pa",
}


class ConsoleHooks(RunHooks):
    """Reproduces the historical CLI behaviour: prints every log line,
    prints the step line at the historical cadence (1000/200/50 for
    1D/2D/3D), and optionally drives the matplotlib live window."""

    def __init__(self, dim, live=False):
        self.dim = dim
        self._viewer = None
        self._want_live = live
        self._info = None

    def run_started(self, info):
        self._info = info
        if self._want_live and self.dim != 1:
            import matplotlib
            if matplotlib.get_backend().lower().startswith('agg'):
                print("  [note] Non-interactive matplotlib backend - "
                      "live view off")
                self._want_live = False

    def log(self, msg):
        print(msg)
        self.log_to_file(msg)

    def progress(self, p: Progress):
        if p.step > 0 and p.step % _STEP_EVERY[self.dim] == 0:
            print(_STEP_FMT[self.dim].format(step=p.step, t=p.t * 1e3,
                                             dt=p.dt, p=p.p_max))

    def frame(self, field2d, t, levels=None):
        if not self._want_live or self.dim == 1:
            return
        if self._viewer is None:
            from ..output import live as live_mod
            self._viewer = live_mod.LiveView(self._info)
        self._viewer.update(field2d, t)

    def close(self):
        if self._viewer is not None:
            self._viewer.close()
            self._viewer = None
