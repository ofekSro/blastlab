"""Foam live-refresh gating tests: _due_sparse must honor the GUI
refresh policy for the sporadically-polled ingest paths. Regression
for the 3D live view never updating in steps mode: the old gate used
RunHooks._due's `step % n == 0`, which a caller that only runs when a
time directory lands (at arbitrary step counts) almost never hits.

Also covers _progress_line's t/end_time fallback (B7): the progress
bar must move from the first solver step, not sit at 0 until the first
written time directory lands.

Pure python - no WSL required.

Run:  python test_foam_live_due.py
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.solvers.foam.runloop import (due_sparse as _due_sparse, new_live as _new_live, progress_line as _progress_line)  # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402
from blastlab.solvers.hooks import RunHooks                    # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def main():
    # fresh state: the very first frame is due immediately in both modes
    check('first frame due (steps)',
          _due_sparse(('steps', 50), 0, _new_live()))
    check('first frame due (seconds)',
          _due_sparse(('seconds', 10.0), 0, _new_live()))

    # steps mode gates on steps SINCE the last emitted frame, not on
    # step % n - the ingest paths run at arbitrary step counts
    last = dict(step=103, draw=time.time())
    check('steps: below threshold not due',
          not _due_sparse(('steps', 50), 137, last))
    check('steps: threshold reached due (odd step values)',
          _due_sparse(('steps', 50), 153, last))
    check('steps: non-divisible step still due',
          _due_sparse(('steps', 50), 999, last))
    check('steps: val<1 clamps to every step',
          _due_sparse(('steps', 0), last['step'] + 1, last))

    # seconds mode gates on wall time since the last emitted frame
    now = time.time()
    check('seconds: within interval not due',
          not _due_sparse(('seconds', 30.0), 5, dict(step=0, draw=now)))
    check('seconds: interval elapsed due',
          _due_sparse(('seconds', 0.2), 5, dict(step=0,
                                                draw=now - 1.0)))

    # ── B7: the t/end_time fallback must actually be armed ────────────
    class _Rec(RunHooks):
        def __init__(self):
            self.fracs = []

        def progress(self, p):
            self.fracs.append(p.frac)

        def log(self, msg):
            pass

    def _st():
        """Exactly what the three solve loops build (backend.py)."""
        return dict(step=0, t=0.0, dt=0.0, p_max=float(P_AIR),
                    frac=None, t_frame=-1.0)

    rec, st = _Rec(), _st()
    for t in ('1e-05', '2e-05', '3e-05'):
        _progress_line(f'Time = {t}', st, rec, end_time=1e-4)
    check('first solver step already reports progress (B7)',
          rec.fracs and rec.fracs[0] > 0.0,
          f'first frac = {rec.fracs[0] if rec.fracs else None}')
    check('fallback tracks t/end_time',
          rec.fracs == [0.1, 0.2, 0.3], str(rec.fracs))

    # once a written frame gives a real front fraction it takes over
    st['frac'] = 0.42
    _progress_line('Time = 4e-05', st, rec, end_time=1e-4)
    check('an ingested front fraction overrides the estimate',
          rec.fracs[-1] == 0.42, str(rec.fracs[-1]))

    # the estimate is clamped, never past 100%
    rec2, st2 = _Rec(), _st()
    _progress_line('Time = 5e-04', st2, rec2, end_time=1e-4)
    check('estimate clamps at 1.0', rec2.fracs == [1.0], str(rec2.fracs))

    print()
    if FAIL:
        print(f"FOAM LIVE DUE: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM LIVE DUE: PASS")


if __name__ == '__main__':
    main()
