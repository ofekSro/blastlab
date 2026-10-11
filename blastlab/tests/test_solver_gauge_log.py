"""GUI-15 (g), D8: the native solvers' dropped-gauge log lines, fast.

A tiny native 2D planar case and a smeared 3D case of 20^3 cells, each
with G1 kept, G2 inside Wall 1 and G3 outside the domain, run with a
hooks object that keeps every log line. The lines must name the gauge
as entered (G<n>), the wall and the drop - what `_e2e_gui_native_warn`
checks through the Tk GUI, here in seconds and for 3D too (GUI-15 (b)).

Meaning, not prose: each check looks for the gauge, the wall and the
word `dropped`, not the whole sentence.

Tiny grids, no WSL, no GUI.  Run:  cd blastlab/tests && python test_solver_gauge_log.py
"""
import os
import re
import sys
import time

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import Case2D, Case3D                   # noqa: E402
from blastlab.solvers.hooks import RunHooks                     # noqa: E402
from blastlab.solvers.solver2d import solve_2d                  # noqa: E402
from blastlab.solvers.solver3d import solve_3d                  # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


class Cap(RunHooks):
    """Keeps every log line."""

    def __init__(self):
        self.lines = []

    def log(self, msg):
        self.lines.append(msg)


def case2d():
    """The e2e native-warn case: G2 inside the box, G3 beyond x = 2.4."""
    return Case2D(geometry='planar', Lx=2.4, Ly=1.6, cell_size_m=0.04,
                  charge=20.0, center=(0.6, 0.0),
                  obstacles=[(1.2, 1.6, 0.0, 0.6)],
                  bcs=dict(x_lo='reflect', x_hi='terminate',
                           y_lo='reflect', y_hi='terminate'),
                  gauges=[(0.3, 0.8), (1.4, 0.3), (2.6, 0.5)],
                  n_snapshots=1, record_frames=0, solver='native')


def case3d():
    """A 1.2 m cube of 0.06 m cells (20^3), a smeared 1 kg charge, G2
    inside the wall x 0.73-0.9, G3 beyond x = 1.2."""
    return Case3D(Lx=1.2, Ly=1.2, Lz=1.2, cell_size_m=0.06, charge=1.0,
                  center=(0.3, 0.57, 0.6), charge_resolution='smear',
                  obstacles=[(0.73, 0.9, 0.0, 1.2, 0.0, 1.2)],
                  gauges=[(0.3, 0.57, 0.9), (0.8, 0.57, 0.6),
                          (1.5, 0.6, 0.6)],
                  n_snapshots=1, record_frames=0, t_end=2e-4,
                  solver='native')


def names(line, n):
    return re.search(rf'\bG{n}\b', line) is not None


def log_checks(tag, solve, case):
    print(f'\n{tag}: the dropped-gauge lines')
    hooks = Cap()
    t0 = time.time()
    res = solve(case, hooks)
    lines = hooks.lines
    check(f'{tag}: one series kept, G1', len(res.gauges['pressures']) == 1,
          str(len(res.gauges['pressures'])))
    check(f'{tag}: a line names G2, Wall 1 and dropped',
          any(names(ln, 2) and 'Wall 1' in ln and 'dropped' in ln
              for ln in lines),
          str([ln for ln in lines if 'G2' in ln]))
    check(f'{tag}: a line names G3 and outside the domain',
          any(names(ln, 3) and 'outside the domain' in ln
              and 'dropped' in ln for ln in lines),
          str([ln for ln in lines if 'G3' in ln]))
    check(f'{tag}: no line names G1 (the kept gauge)',
          not any(names(ln, 1) for ln in lines),
          str([ln for ln in lines if names(ln, 1)]))
    print(f'  ({time.time() - t0:.1f} s)')


def main():
    t0 = time.time()
    log_checks('2D planar', solve_2d, case2d())
    log_checks('3D', solve_3d, case3d())
    took = time.time() - t0
    check(f'the suite runs in under 60 s ({took:.1f} s)', took < 60.0)
    print()
    if FAILS:
        print(f'SOLVER GAUGE LOG: FAIL ({len(FAILS)}): {", ".join(FAILS)}')
        return 1
    print('SOLVER GAUGE LOG: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
