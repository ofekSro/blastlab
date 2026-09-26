"""Background solver execution for the GUI front-ends.

SolverWorker runs one or more cases on a daemon thread and communicates
with the GUI main thread ONLY through a queue of tagged tuples:

    ('log', text)               a line of run output
    ('run_started', info)       grid info for the live view
    ('cadence', dt, steps)      blastFoam: how often live frames can come
    ('progress', Progress)      throttled to ~10 Hz (flushed on pause/end)
    ('paused', bool)            the stepped-execution gate holds / releases
    ('frame',)                  token: a fresh live frame is available
    ('frame3d',)                token: a fresh 3D payload is available
    ('stage', index, label)     a chain stage begins
    ('result', index, Result)   a stage finished (also on Stop)
    ('error', traceback_text)   a stage raised; after a failed hand-off
                                write (jobs.HandoffWriteError) the
                                stage's 'result' comes first and the
                                text is the error's message
    ('done',)                   worker finished

Live frames are coalesced into a single slot (latest wins) so a fast
solver cannot flood the queue; the drainer pulls `latest_frame()` /
`latest_frame3d()`. Toolkit-free: the Tk app (`blastlab.gui`) and the
Qt app (`blastlab.ui`) both drain this queue from their own timers.
"""

import queue
import threading
import time
import traceback

import numpy as np

from .hooks import RunHooks, StoppedBeforeStart
from .jobs import HandoffWriteError


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
        #: Qt front-end: a viz3d.protocol.SharedFrameRing the viewer
        #: process reads; frames are published straight into it from
        #: this (solver) thread and never touch the GUI queue. None
        #: keeps the in-process latest-wins slot the Tk app drains.
        self.ring = None
        self._latest3d = None
        self._frame3d_pending = False
        self.live_gauges = False      # the Run tab's gauge view is open
        self._latest_gauges = None
        self._gauges_pending = False
        self._latest_surf3d = None
        self._surf3d_pending = False
        self._last_p = None           # newest Progress, for flush_progress
        self._revolver = None         # 2D axisym -> 3D cylinder view
        self._rev_last = 0.0
        # stepped execution: 'run' streams, 'step' consumes a budget
        self._exec_lock = threading.Lock()
        self._exec_mode = 'run'
        self._exec_budget = 0
        self._exec_evt = threading.Event()
        self._exec_evt.set()

    def run_started(self, info):
        # Each stage starts fresh: drop any 3D feed/revolver/scene left by
        # the PREVIOUS stage of a chain before deciding what this stage
        # needs. Without this a 2D axisym stage's revolved feed survived
        # into a following 3D stage (feed3d was not None, so the real 3D
        # feed was never built) and the first 3D frame crashed the run in
        # extract_loads with a shape mismatch (128 vs 40).
        with self._lock:
            self._latest3d = None
            self._frame3d_pending = False
            self._latest_gauges = None
            self._gauges_pending = False
            self._latest_surf3d = None
            self._surf3d_pending = False
        self.feed3d = None
        self.ring = None
        self.scene3d = None
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
        # cached so the app can open the 3D viewer mid-run (GUI thread)
        self.scene3d = info.get('scene3d')
        if self.auto3d and self.scene3d is not None and self.feed3d is None:
            # Build the decimator here (pure NumPy, solver thread) so the
            # very first frames are captured; the GUI drainer builds the
            # scene from feed3d.init when it sees 'run_started'.
            from ..viz3d.feed import Feed3D
            try:
                self.feed3d = Feed3D(self.scene3d)
            except Exception:
                self.feed3d = None
        self.q.put(('run_started', info))

    def cadence(self, dt=None, steps=None):
        self.q.put(('cadence', dt, steps))

    def log(self, msg):
        self.q.put(('log', msg))

    def progress(self, p):
        self._last_p = p
        now = time.monotonic()
        if now - self._last_progress >= 0.1:
            self._last_progress = now
            self.q.put(('progress', p))

    def flush_progress(self):
        """Post the newest Progress even if the ~10 Hz throttle just
        dropped it. The stat chips otherwise keep the step/time of the
        last message that got through, which is visibly wrong exactly
        when the model stops moving: at a step gate (Interrupt / Exec n)
        and at the end of a stage."""
        p = self._last_p
        if p is not None:
            self._last_progress = time.monotonic()
            self.q.put(('progress', p))

    def frame(self, field2d, t, levels=None):
        with self._lock:
            self._latest = (np.asarray(field2d, dtype=np.float32).copy(), t,
                            None if levels is None
                            else np.asarray(levels, dtype=np.int8).copy())
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

    # ── the live-slice plane, for the 3D view ────────────────────────────
    # Same latest-wins shape again. Gated on the 3D feed existing, so a
    # run with no 3D view attached never copies the array.
    def wants_surf3d(self):
        return self.feed3d is not None

    def surf3d(self, t, field2d):
        if self.feed3d is None or field2d is None:
            return
        with self._lock:
            self._latest_surf3d = (float(t),
                                   np.asarray(field2d,
                                              dtype=np.float32).copy())
            if not self._surf3d_pending:
                self._surf3d_pending = True
                self.q.put(('surf3d',))

    def latest_surf3d(self):
        with self._lock:
            self._surf3d_pending = False
            return self._latest_surf3d

    # ── live gauge traces ────────────────────────────────────────────────
    # Same latest-wins shape as `frame`: the payload is the whole series
    # so far, so a coalesced post loses nothing - the newest one contains
    # every earlier one.
    def wants_gauges(self):
        return self.live_gauges

    def gauges(self, payload):
        if not self.live_gauges or not payload:
            return
        with self._lock:
            self._latest_gauges = payload
            if not self._gauges_pending:
                self._gauges_pending = True
                self.q.put(('gauges',))

    def latest_gauges(self):
        with self._lock:
            self._gauges_pending = False
            return self._latest_gauges

    # ── embedded 3D view: decimate on the solver thread, coalesce into a
    # latest-wins slot so the GUI queue never carries big arrays twice ───
    def wants_frame3d(self):
        return self.feed3d is not None

    def frame3d(self, t, fields, force=False):
        feed = self.feed3d
        if feed is None:
            return
        payload = feed.make_payload(fields)
        ring = self.ring
        if ring is not None:
            # shared-memory path (Qt front-end): the viewer child polls
            # the ring itself, nothing to post to the GUI queue
            try:
                ring.write(t, payload, final=force)
            except Exception:
                pass          # a closed ring (run torn down) drops the frame
            return
        with self._lock:
            # coalesced latest-wins slot: keep `final` sticky so a forced
            # (run-ending) frame's flag survives being overwritten before
            # the GUI thread drains it (should not happen in practice -
            # the forced frame is always the last one emitted - but drop
            # it silently rather than lose finality if it ever does).
            prev_final = self._latest3d[2] if self._latest3d is not None else False
            self._latest3d = (t, payload, force or prev_final)
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
        n = allow n more steps then hold. Called from the GUI thread."""
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
        held = False
        while not self._stop.is_set():
            with self._exec_lock:
                if self._exec_mode == 'run':
                    break
                if self._exec_budget > 0:
                    self._exec_budget -= 1
                    break
                self._exec_evt.clear()
            if not held:
                # entering the hold: publish the true step/time and tell
                # the UI it is paused (it used to show only a log line)
                held = True
                self.flush_progress()
                self.q.put(('paused', True))
            # paused: wake on set_exec()/Stop; timeout re-checks stop
            self._exec_evt.wait(0.2)
        if held:
            self.q.put(('paused', False))


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
        #: traceback of the stage that failed, kept alongside `results`.
        #: The queue copy is the GUI's; this one survives for anyone
        #: inspecting the worker after is_alive() goes False - without it
        #: a failed stage is invisible to a caller that is not draining
        #: the queue (a chain's LAST stage is the usual victim).
        self.error = None
        self.error_stage = None

    def run(self):
        try:
            for k, (label, solve) in enumerate(self._stages):
                self.q.put(('stage', k, label))
                try:
                    res = solve(self.hooks)
                except StoppedBeforeStart as exc:
                    # the user stopped during setup (WSL probe, meshing):
                    # nothing was computed, so there is no partial Result
                    # to post - and it is not a failure either
                    self.q.put(('log', f'  [{exc}]'))
                    break
                except HandoffWriteError as exc:
                    # the solve finished but its hand-off file could not
                    # be written (UX 2): the result still reaches Results,
                    # then the chain stops like any failed stage - the
                    # next one would read a stale or missing profile
                    self.results[k] = exc.result
                    self.hooks.flush_progress()
                    self.q.put(('result', k, exc.result))
                    self.error_stage = k
                    self.error = str(exc)
                    self.q.put(('error', self.error))
                    break
                except Exception:
                    self.error_stage = k
                    self.error = traceback.format_exc()
                    self.q.put(('error', self.error))
                    break
                self.results[k] = res
                self.hooks.flush_progress()   # chips show the true final step
                self.q.put(('result', k, res))
                if self.stop_event.is_set():
                    break
        finally:
            self.q.put(('done',))

    def stop(self):
        self.stop_event.set()
