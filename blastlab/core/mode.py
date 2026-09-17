"""App-level solver mode (T34).

The solver (native | blastfoam) is chosen once, in the sidebar, and every
panel lays itself out for it: controls that do not apply to the active
solver are hidden, never greyed.  `SolverMode` is a tiny observable that
holds the choice and fans changes out to the panels; it has no toolkit
dependency so it can be unit-tested without a window. (Moved from
`blastlab.gui.mode`, which re-exports it for the Tk GUI.)
"""

MODES = ('native', 'blastfoam')
LABELS = {'native': 'native', 'blastfoam': 'blastFoam'}
DEFAULT = 'blastfoam'

EXPLAIN = {
    'native': 'Pure-Python solver - fast, no WSL needed.',
    'blastfoam': 'blastFoam in WSL (OpenFOAM-9): materials, AMR, '
                 'refinement zones.',
}


def normalize(value):
    """'blastFoam' / ' BLASTFOAM ' -> 'blastfoam'; anything unknown ->
    DEFAULT (a bogus settings.json entry must not break the GUI)."""
    text = str(value or '').strip().lower()
    return text if text in MODES else DEFAULT


def label(mode):
    return LABELS[normalize(mode)]


def from_label(text):
    for m, lbl in LABELS.items():
        if str(text).strip() == lbl:
            return m
    return normalize(text)


class SolverMode:
    """Observable solver choice.  `set()` notifies subscribers in
    subscription order; a `set()` issued from inside a subscriber is
    applied after the current fan-out (never nested)."""

    def __init__(self, value=DEFAULT):
        self._value = normalize(value)
        self._subs = []
        self._notifying = False
        self._pending = None

    def get(self):
        return self._value

    def subscribe(self, fn):
        if fn not in self._subs:
            self._subs.append(fn)
        return fn

    def unsubscribe(self, fn):
        try:
            self._subs.remove(fn)
        except ValueError:
            pass

    def set(self, value):
        """Store `value`; return True when it changed (and subscribers
        were told), False for a no-op."""
        m = normalize(value)
        if self._notifying:
            self._pending = m
            return m != self._value
        if m == self._value:
            return False
        self._value = m
        self._notify()
        return True

    def _notify(self):
        self._notifying = True
        first_exc = None
        try:
            for fn in list(self._subs):
                try:
                    fn(self._value)
                except Exception as exc:     # one broken panel must not
                    if first_exc is None:    # stop the others re-laying out
                        first_exc = exc
        finally:
            self._notifying = False
        pending, self._pending = self._pending, None
        if pending is not None and pending != self._value:
            self._value = pending
            self._notify()
        if first_exc is not None:
            raise first_exc
