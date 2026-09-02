"""Stop/pause regression for the blastFoam backend: a scripted hooks
object pauses the run at the second written frame (SIGSTOP round-trip
through _gated_step), resumes, then requests a user stop - the run
must end via `stopAt writeNow` with a clean partial Result. Auto-SKIPs
without WSL. Wall ~1 min."""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.case import Case2D                          # noqa: E402
from blastlab.solvers.hooks import RunHooks                    # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


class ScriptedHooks(RunHooks):
    """Pause 2 s at the 2nd ingested frame, then stop at the 4th."""

    PAUSE_AT, STOP_AT, PAUSE_S = 2, 4, 2.0

    def __init__(self):
        self.frames = 0
        self.paused = False
        self.pause_done = False
        self.pause_wall = 0.0
        self._stop = False

    def frame(self, field2d, t):
        self.frames += 1
        if self.frames >= self.STOP_AT:
            self._stop = True

    # force a frame() + step_gate() on every ingested write
    refresh = ('steps', 1)

    def exec_will_pause(self):
        return (not self.pause_done) and self.frames >= self.PAUSE_AT

    def exec_paused(self):
        return self.exec_will_pause()

    def step_gate(self):
        if self.exec_will_pause():
            # backend suspends the WSL solver around this block
            self.paused = True
            t0 = time.time()
            time.sleep(self.PAUSE_S)
            self.pause_wall = time.time() - t0
            self.pause_done = True

    def should_stop(self):
        return self._stop


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM STOP: SKIP")
        return

    from blastlab.solvers import get_solver
    case = Case2D(geometry='axisymmetric', Lx=2.5, Ly=2.5,
                  cell_size_m=0.02, charge=8.0, center=(0.0, 1.25),
                  gauges=[(0.8, 1.25)], n_snapshots=4, record_frames=0,
                  solver='blastfoam', material='TNT')
    hooks = ScriptedHooks()
    res = get_solver(2, 'blastfoam')(case, hooks)

    check('pause was exercised', hooks.paused and hooks.pause_done,
          f'frames={hooks.frames}')
    check('pause actually held the gate',
          hooks.pause_wall >= 0.9 * ScriptedHooks.PAUSE_S,
          f'{hooks.pause_wall:.2f}s')
    check('stopped by user', res.stop_reason == 'stopped by user',
          res.stop_reason)
    check('stopped_early flag', res.stopped_early is True)
    check('partial result has snapshots', len(res.snapshots) >= 1
          and list(res.snapshots)[-1].endswith('(final)'))
    check('partial gauges recorded',
          len(res.gauges['pressures']) == 1
          and len(res.gauges['times']) > 10
          and np.isfinite(res.gauges['pressures'][0]).all())
    check('meta contract intact',
          res.meta.get('case_dir') and 'final_state' in res.meta)

    print()
    if FAIL:
        print(f"FOAM STOP: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM STOP: PASS")


if __name__ == '__main__':
    main()
