"""Run hooks: how a running solver talks to the outside world.

The solvers never print or draw directly; they call the hooks. The CLI
uses ConsoleHooks (reproduces the historical console output and the
matplotlib live window); the GUI supplies its own hooks that forward to
a Tk-safe queue.
"""

import time
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Progress:
    step: int
    t: float            # simulation time [s]
    dt: float           # current time step [s]
    p_max: float        # max pressure this step [Pa]
    frac: float = 0.0   # 0..1 progress estimate (front/stop-distance or t/cap)


@dataclass
class Result:
    """What a solver run produces (also on early stop - finalization
    always runs, so snapshots/gauges/meta are complete for the time
    actually simulated)."""
    snapshots: dict
    gauges: dict
    meta: dict
    stop_reason: str = ''
    stopped_early: bool = False

    @property
    def legacy_tuple(self):
        return self.snapshots, self.gauges, self.meta


class StoppedBeforeStart(RuntimeError):
    """The user stopped a run before it produced anything at all.

    Raised only from the setup phase a solver goes through before its
    first step - for blastFoam the WSL availability probe and the
    mesh/charge-init stages, which can take minutes on a cold start. No
    partial Result exists at that point (there is no field to finalize),
    so this is *not* a failure and hosts must not report it as one: end
    the run quietly and post no result."""


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

    def log(self, msg):
        """A line of run output (summaries, notes, warnings)."""

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
