"""The run clock of the 02 Run screen (GUI-6, plan §6, UX-19).

Run time is wall time since the run started with the held time (a run
paused, or held by Initialise and stepped) left out. It drives the
progress strip's elapsed line and its ETA, the 30 s rule of the Stop
confirmation, the dialog's "running for" and the finish notification's
"finished in". Display only: nothing here feeds a solver.

Toolkit-free on purpose. `now` is injectable, so the tests drive a fake
clock instead of sleeping.
"""

import time

#: the ETA appears only from this progress fraction on (plan §6: "only
#: after 5 %"); below it a linear extrapolation is mostly noise
ETA_MIN_FRAC = 0.05


def fmt_duration(s):
    """`12 s`, `4 min 18 s`, `1 h 02 min` - whole seconds, rounded, so
    59.6 s reads `1 min 0 s` (the one form pinned by the tests)."""
    n = max(0, int(round(float(s))))
    if n < 60:
        return f'{n} s'
    if n < 3600:
        return f'{n // 60} min {n % 60} s'
    return f'{n // 3600} h {(n % 3600) // 60:02d} min'


class RunClock:
    """start() a run, stage() a chain stage, hold(True/False) a pause,
    stop() to freeze. run_s() / stage_s() exclude the held time."""

    def __init__(self, now=time.monotonic):
        #: the time source (seconds, monotonic); replace it in tests
        self.now = now
        self._run0 = None           # when the run started
        self._stage0 = None         # when the current stage started
        self._held = 0.0            # closed holds, seconds
        self._hold0 = None          # the open hold's start, or None
        self._stage_held0 = 0.0     # held seconds before this stage
        self._stopped = None        # the frozen time, or None while live
        self._eta0 = None           # where the ETA's stage time starts
        self._eta_held0 = 0.0       # held seconds before that point

    # ── state ────────────────────────────────────────────────────────────
    def started(self):
        return self._run0 is not None

    def live(self):
        """A run is on the clock (started and not stopped)."""
        return self._run0 is not None and self._stopped is None

    def held(self):
        return self._hold0 is not None

    def _t(self):
        return self._stopped if self._stopped is not None else self.now()

    def _held_at(self, t):
        return self._held + (t - self._hold0 if self._hold0 is not None
                             else 0.0)

    # ── transitions ──────────────────────────────────────────────────────
    def start(self):
        """A new run: the counts start from zero."""
        t = self.now()
        self._run0 = self._stage0 = t
        self._held = self._stage_held0 = 0.0
        self._hold0 = None
        self._stopped = None
        self._eta0 = t
        self._eta_held0 = 0.0

    def stage(self):
        """A (chain) stage starts: stage_s() and the ETA restart."""
        if not self.live():
            self.start()
            return
        t = self.now()
        self._stage0 = t
        self._stage_held0 = self._held_at(t)
        self._eta0 = t
        self._eta_held0 = self._stage_held0

    def restart_eta(self):
        """The stage's solve begins after its mesh (GUI-16 round 2, D-R6):
        only the ETA restarts, stage_s() keeps counting from `stage()`."""
        if not self.live():
            return
        t = self.now()
        self._eta0 = t
        self._eta_held0 = self._held_at(t)

    def hold(self, on):
        """Pause (True) or resume (False) the count; repeats are
        ignored, and so is a hold outside a live run."""
        if not self.live():
            return
        t = self.now()
        if on and self._hold0 is None:
            self._hold0 = t
        elif not on and self._hold0 is not None:
            self._held += t - self._hold0
            self._hold0 = None

    def stop(self):
        """Freeze the clock at the run's end (an open hold closes)."""
        if not self.live():
            return
        t = self.now()
        if self._hold0 is not None:
            self._held += t - self._hold0
            self._hold0 = None
        self._stopped = t

    # ── readings ─────────────────────────────────────────────────────────
    def run_s(self):
        """Run time: wall time since start() minus the held time."""
        if self._run0 is None:
            return 0.0
        t = self._t()
        return max(0.0, (t - self._run0) - self._held_at(t))

    def stage_s(self):
        """The same for the current stage."""
        if self._stage0 is None:
            return 0.0
        t = self._t()
        return max(0.0, (t - self._stage0)
                   - (self._held_at(t) - self._stage_held0))

    def eta_s(self, frac):
        """Seconds left by linear extrapolation of the stage's progress
        fraction (plan §6), or None below ETA_MIN_FRAC, while held, or
        with no live run."""
        try:
            frac = float(frac)
        except (TypeError, ValueError):
            return None
        if not self.live() or self.held() or frac < ETA_MIN_FRAC:
            return None
        if frac >= 1.0:
            return 0.0
        t = self._t()
        solve_s = max(0.0, (t - self._eta0)
                      - (self._held_at(t) - self._eta_held0))
        return solve_s * (1.0 - frac) / frac
