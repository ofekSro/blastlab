"""Unit tests for the adaptive-writeInterval controller (pure function,
no WSL)."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.solvers.foam.backend import _next_interval       # noqa: E402
from blastlab.solvers.foam.writer import (N_WRITES_MIN,        # noqa: E402
                                          N_WRITES_MAX)

FAIL = []
I0 = 1e-4


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def main():
    # nominal pace: no change
    check('on-pace hold',
          _next_interval(20, 20 / 50.0, I0, I0) is None)

    # far too dense: 40 frames at 10% progress projects 400 total
    check('dense -> double', _next_interval(40, 0.10, I0, I0) == 2 * I0)

    # early frames with ~zero progress: progress floor prevents panic
    check('progress floor',
          _next_interval(2, 0.0, I0, I0) is None)

    # sparse late run: 5 frames at 40% projects ~12 < 0.7*N_WRITES_MIN
    check('sparse -> halve',
          _next_interval(5, 0.40, I0, I0) == 0.5 * I0)

    # sparse but too early to judge (progress <= 0.15): hold
    check('sparse early hold',
          _next_interval(2, 0.10, I0, I0) is None)

    # bounds: repeated doubling clamps at 8x the initial interval
    iv = I0
    for _ in range(8):
        new = _next_interval(1000, 0.5, iv, I0)
        if new is None:
            break
        iv = new
    check('upper bound 8x', iv == 8 * I0, f'{iv/I0:g}x')
    check('at cap -> no change',
          _next_interval(1000, 0.5, 8 * I0, I0) is None)

    # bounds: repeated halving clamps at 1/4 the initial interval
    iv = I0
    for _ in range(8):
        new = _next_interval(3, 0.9, iv, I0)
        if new is None:
            break
        iv = new
    check('lower bound 1/4', iv == I0 / 4.0, f'{iv/I0:g}x')

    # band sanity against writer constants
    check('band constants sane', N_WRITES_MIN < N_WRITES_MAX)

    print()
    if FAIL:
        print(f"ADAPTIVE INTERVAL: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("ADAPTIVE INTERVAL: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
