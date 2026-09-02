"""Foam live-refresh gating tests: _due_sparse must honor the GUI
refresh policy for the sporadically-polled ingest paths. Regression
for the 3D live view never updating in steps mode: the old gate used
RunHooks._due's `step % n == 0`, which a caller that only runs when a
time directory lands (at arbitrary step counts) almost never hits.
Pure python - no WSL required.

Run:  python test_foam_live_due.py
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.solvers.foam.backend import (_due_sparse,        # noqa: E402
                                           _new_live)

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

    print()
    if FAIL:
        print(f"FOAM LIVE DUE: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM LIVE DUE: PASS")


if __name__ == '__main__':
    main()
