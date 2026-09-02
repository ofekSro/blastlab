"""Background solver execution for the GUI.

SolverWorker runs one or more cases on a daemon thread and communicates
with the Tk main thread ONLY through a queue of tagged tuples:

    ('log', text)               a line of run output
    ('run_started', info)       grid info for the live view
    ('progress', Progress)      throttled to ~10 Hz
    ('frame',)                  token: a fresh live frame is available
    ('stage', index, label)     a chain stage begins
    ('result', index, Result)   a stage finished (also on Stop)
    ('error', traceback_text)   a stage raised
    ('done',)                   worker finished

Live frames are coalesced into a single slot (latest wins) so a fast
solver cannot flood the queue; the drainer pulls `latest_frame()`.
"""

import queue
import threading
import time
import traceback

import numpy as np

from ..solvers.hooks import RunHooks


class GuiHooks(RunHooks):
    def __init__(self, q, stop_event):
        self.q = q
        self._stop = stop_event
        self._lock = threading.Lock()
        self._latest = None
        self._frame_pending = False
        self._last_progress = 0.0
        self.scene3d = None
        self.auto3d = False           # attach the 3D feed at run start
        self.feed3d = None            # Feed3D once the 3D view is open
        self._latest3d = None
        self._frame3d_pending = False
        self._revolver = None         # 2D axisym -> 3D cylinder view
        self._rev_last = 0.0
        # stepped execution: 'run' streams, 'step' consumes a budget
        self._exec_lock = threading.Lock()
        self._exec_mode = 'run'
        self._exec_budget = 0
        self._exec_evt = threading.Event()
        self._exec_evt.set()

    def run_started(self, info):
        # 2D axisymmetric runs: revolve the live (r, z) frames into a
        # cylinder for the 3D view (pressure only, illustration)
        self._revolver = None
        rev = info.get('revolve3d')
        if rev is not None and self.auto3d:
            from ..viz3d.sampling import Revolver
            try:
                self._revolver = Revolver(rev)
                info = dict(info, scene3d=self._revolver.scene3d)
            except Exception:
                self._revolver = None
        # cached so the app can open the 3D viewer mid-run (Tk thread)
        self.scene3d = info.get('scene3d')
        if self.auto3d and self.scene3d is not None and self.feed3d is None:
            # Build the decimator here (pure NumPy, solver thread) so the
            # very first frames are captured; the Tk drainer builds the
            # scene from feed3d.init when it sees 'run_started'.
            from .view3d_panel import Feed3D
            try:
                self.feed3d = Feed3D(self.scene3d)
            except Exception:
                self.feed3d = None
        self.q.put(('run_started', info))

    def log(self, msg):
        self.q.put(('log', msg))

    def progress(self, p):
        now = time.monotonic()
        if now - self._last_progress >= 0.1:
            self._last_progress = now
            self.q.put(('progress', p))

    def frame(self, field2d, t):
        with self._lock:
            self._latest = (np.asarray(field2d, dtype=np.float32).copy(), t)
            if not self._frame_pending:
                self._frame_pending = True
                self.q.put(('frame',))
        # revolved 3D companion frame: rides the 2D cadence (already
        # gated by the user's refresh policy); in seconds mode the 3D
        # emission is additionally throttled by refresh3d
        rev = self._revolver
        if rev is not None and self.feed3d is not None:
            mode, val = self.refresh3d
            now = time.monotonic()
            if mode == 'steps' or now - self._rev_last >= float(val):
                self._rev_last = now
                try:
                    self.frame3d(t, dict(p=rev.revolve(field2d)))
                except ValueError:
                    pass          # not a full-grid (r, z) frame

    def latest_frame(self):
        with self._lock:
            self._frame_pending = False
            return self._latest

    # ── embedded 3D view: decimate on the solver thread, coalesce into a
    # latest-wins slot so the Tk queue never carries big arrays twice ────
    def wants_frame3d(self):
        return self.feed3d is not None

    def frame3d(self, t, fields, force=False):
        feed = self.feed3d
        if feed is None:
            return
        payload = feed.make_payload(fields)
        with self._lock:
            self._latest3d = (t, payload)
            if not self._frame3d_pending:
                self._frame3d_pending = True
                self.q.put(('frame3d',))

    def latest_frame3d(self):
        with self._lock:
            self._frame3d_pending = False
            return self._latest3d

    def should_stop(self):
        return self._stop.is_set()

    # ── stepped execution (VIPER-style Exec buttons) ──────────────────
    def set_exec(self, cmd):
        """'run' = free-running, 'pause' = hold at the gate, or an int
        n = allow n more steps then hold. Called from the Tk thread."""
        with self._exec_lock:
            if cmd == 'run':
                self._exec_mode = 'run'
                self._exec_budget = 0
            elif cmd == 'pause':
                self._exec_mode = 'step'
                self._exec_budget = 0
            else:
                self._exec_mode = 'step'
                self._exec_budget += max(0, int(cmd))
            self._exec_evt.set()

    def exec_paused(self):
        with self._exec_lock:
            return self._exec_mode == 'step' and self._exec_budget == 0

    def exec_will_pause(self):
        with self._exec_lock:
            return self._exec_mode == 'step' and self._exec_budget <= 1

    def step_gate(self):
        while not self._stop.is_set():
            with self._exec_lock:
                if self._exec_mode == 'run':
                    return
                if self._exec_budget > 0:
                    self._exec_budget -= 1
                    return
                self._exec_evt.clear()
            # paused: wake on set_exec()/Stop; timeout re-checks stop
            self._exec_evt.wait(0.2)


class SolverWorker(threading.Thread):
    """Runs [(label, solve_callable), ...] sequentially.

    Each solve_callable takes (hooks) and returns a Result. Between
    stages the worker checks the stop flag; a user stop ends the chain
    after the current stage's (finalized, partial) result is posted.
    """

    def __init__(self, stages):
        super().__init__(daemon=True)
        self.q = queue.Queue()
        self.stop_event = threading.Event()
        self.hooks = GuiHooks(self.q, self.stop_event)
        self._stages = stages
        self.results = [None] * len(stages)

    def run(self):
        try:
            for k, (label, solve) in enumerate(self._stages):
                self.q.put(('stage', k, label))
                try:
                    res = solve(self.hooks)
                except Exception:
                    self.q.put(('error', traceback.format_exc()))
                    break
                self.results[k] = res
                self.q.put(('result', k, res))
                if self.stop_event.is_set():
                    break
        finally:
            self.q.put(('done',))

    def stop(self):
        self.stop_event.set()
