"""The End time field: the automatic stop, and an explicit one PAST it.

`test_bc_trigger.py` already checks that a t_end below the automatic
stop is honoured - and that is precisely why the bug survived. Every
stop condition read

    cap_is_end = bool(t_end) and t_end < cap

so an end time at or above the automatic stop was silently discarded
and the run ended at the cap instead; a test that only ever set a
SHORTER end time could never see it. Measured before the fix, on a real
native 2D run in a 1 m domain (automatic stop 29.4 ms): 3 ms and 10 ms
gave `end time reached`, 40 ms gave `safety cap` at 29.4 ms. The foam
planner capped 50, 100 and 500 ms alike to 47.0 ms in a 1.6 m domain.

So every case here is on the far side of the cap. No WSL: the foam side
is checked through the planner, which is where the decision is made.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                              # noqa: E402

from blastlab.core.case import (Case1D, Case2D, Case3D,         # noqa: E402
                                cap_distance, long_run_note,
                                safety_cap_s, validate_case)
from blastlab.solvers.foam import writer                        # noqa: E402
from blastlab.solvers.hooks import RunHooks                     # noqa: E402
from blastlab.solvers.solver2d import solve_2d                  # noqa: E402

C_AIR = float(np.sqrt(1.4 * 101325.0 / 1.225))
FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


class Quiet(RunHooks):
    def log(self, line):
        pass


def case1(t_end=0.0):
    return Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.02,
                  bc_outer='transmit', solver='native', t_end=t_end)


def case2(t_end=0.0, Lx=1.0, Ly=1.0):
    return Case2D(geometry='planar', Lx=Lx, Ly=Ly, cell_size_m=0.02,
                  charge=1.0, center=(Lx / 2, Ly / 2), n_snapshots=2,
                  bcs=dict(x_lo='transmit', x_hi='transmit',
                           y_lo='transmit', y_hi='transmit'),
                  solver='native', t_end=t_end)


def case3(t_end=0.0):
    return Case3D(Lx=1.6, Ly=1.2, Lz=1.2, cell_size_m=0.02, charge=8.0,
                  center=(0.4, 0.6, 0.6), det_points=[(0.4, 0.6, 0.6)],
                  solver='blastfoam', material='TNT', t_end=t_end)


def main():
    print('END TIME')

    # ── 1. the automatic stop is 10 domain crossings ────────────────────
    print('\n  the automatic stop')
    check('1D measures across the radius',
          abs(cap_distance(case1()) - 2.0) < 1e-12)
    check('2D/3D measure across the longest side',
          abs(cap_distance(case3()) - 1.6) < 1e-12,
          f'{cap_distance(case3())}')
    for c, dist in ((case1(), 2.0), (case2(), 1.0), (case3(), 1.6)):
        want = 10.0 * dist / C_AIR
        check(f'{c.dim}D cap = 10 * {dist} / c_amb = {want * 1e3:.1f} ms',
              abs(safety_cap_s(c) - want) < 1e-12)

    # ── 2. the foam planner honours an end time PAST the cap ────────────
    print('\n  the blastFoam planner (cap 47.0 ms)')
    cap3 = safety_cap_s(case3())
    s = writer.plan_case(case3(0.0))
    check('t_end = 0 plans the cap',
          abs(s.end_time - cap3) < 1e-9 and not s.cap_is_end,
          f'{s.end_time * 1e3:.1f} ms')
    for t_ms in (5.0, 40.0, 50.0, 100.0, 500.0):
        s = writer.plan_case(case3(t_ms / 1e3))
        check(f't_end = {t_ms:g} ms is planned as itself',
              s.cap_is_end and abs(s.end_time - t_ms / 1e3) < 1e-12,
              f'{s.end_time * 1e3:.1f} ms')
    # the write cadence must NOT scale with a long end time: a 10x
    # longer run writing 10x as often would bury the disk
    i_auto = writer.plan_case(case3(0.0)).write_interval
    i_long = writer.plan_case(case3(0.5)).write_interval
    check('writeInterval is unchanged by a long end time',
          abs(i_long - i_auto) < 1e-15,
          f'{i_auto:.3e} vs {i_long:.3e} s')

    # ── 3. long_run_note / the validator warning ────────────────────────
    print('\n  what the user is told')
    for c, t_ms, want in ((case3(), 5.0, False), (case3(), 46.0, False),
                          (case3(), 50.0, True), (case3(), 500.0, True),
                          (case1(), 20.0, False), (case1(), 200.0, True),
                          (case2(), 10.0, False), (case2(), 40.0, True)):
        c.t_end = t_ms / 1e3
        got = long_run_note(c) is not None
        check(f'{c.dim}D t_end = {t_ms:g} ms -> '
              f'{"flagged" if want else "quiet"}', got == want)
    check('t_end = 0 is never flagged',
          all(long_run_note(c) is None
              for c in (case1(), case2(), case3())))
    note = long_run_note(case3(0.5))
    check('the note carries (t_end, cap, ratio)',
          note is not None and abs(note[0] - 0.5) < 1e-12
          and abs(note[2] - 0.5 / note[1]) < 1e-9,
          f'ratio {note[2]:.1f}x' if note else 'none')
    warns = [w for w in validate_case(case2(0.040)).warnings
             if 'automatic stop time' in w]
    check('the validator says so, with the ratio', len(warns) == 1,
          warns[0][:70] + '...' if warns else 'no warning')
    check('and stays quiet below the cap',
          not [w for w in validate_case(case2(0.010)).warnings
               if 'automatic stop time' in w])

    # ── 4. a real run, past the cap ─────────────────────────────────────
    # The check the planner-level ones cannot make: that the solver's own
    # loop agrees. Deliberately tiny - 0.3 m across, so the cap is 8.8 ms.
    #
    # The charge is LARGE for the domain on purpose. The native solver
    # refines dx to r_exp/5, so a small charge makes the mesh FINER, not
    # coarser: 0.01 kg forces dx = 2.3 mm and a 132^2 grid, which took
    # this file past ten minutes. 0.5 kg gives r_exp/5 = 8.4 mm, a 36^2
    # grid, and seconds. Nothing here depends on the charge size.
    print('\n  a real native 2D run')
    small = case2(0.0, Lx=0.3, Ly=0.3)
    small.charge = 0.5
    cap_s = safety_cap_s(small)
    check(f'the cap for a 0.3 m domain is {cap_s * 1e3:.1f} ms',
          abs(cap_s - 10.0 * 0.3 / C_AIR) < 1e-12)

    small.t_end = 0.5 * cap_s
    r = solve_2d(small, Quiet())
    check('an end time BELOW the cap still ends on the end time',
          r.stop_reason == 'end time reached', repr(r.stop_reason))

    small.t_end = 1.4 * cap_s          # past it: this used to be capped
    r = solve_2d(small, Quiet())
    check('an end time PAST the cap ends on the end time, not the cap',
          r.stop_reason == 'end time reached', repr(r.stop_reason))

    small.t_end = 0.0
    r = solve_2d(small, Quiet())
    check('and with no end time the cap still stops the run',
          r.stop_reason == 'safety cap', repr(r.stop_reason))

    print('\nEND TIME: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
