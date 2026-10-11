"""P1-24: the native T51 trigger with a dropped gauge.

The case of GUI-14 B verify issue 1 (`docs/batches/2026-10-11-gui-14-
backlog-B.verify.md`): gauges G1 (0.3, 0.8), G2 (1.4, 0.3) inside Wall 1,
G3 (0.6, 0.5) and G4 (1.0, 1.0), trigger gauge 3, `terminate`. Gauges
are passive probes, so the run must stop exactly where the control - the
same case with G2 kept at (0.2, 0.2) - stops.

This first version characterises: it pins the no-drop control and prints
the drop case's current stop (recorded in the batch report).

Tiny grids, no WSL, no GUI.  Run:  cd blastlab/tests && python test_trigger_numbering.py
"""
import os
import sys

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
    """Keeps the log lines and the run_started info."""

    def __init__(self):
        self.lines = []
        self.info = None

    def log(self, msg):
        self.lines.append(msg)

    def run_started(self, info):
        self.info = info


def run(solve, case):
    hooks = Cap()
    return solve(case, hooks), hooks


#: the e2e native-warn case (`_e2e_gui_native_warn.py`) with four gauges
WALL_2D = (1.2, 1.6, 0.0, 0.6)


def case2d(g2, **kw):
    return Case2D(geometry='planar', Lx=2.4, Ly=1.6, cell_size_m=0.04,
                  charge=20.0, center=(0.6, 0.0), obstacles=[WALL_2D],
                  bcs=dict(x_lo='reflect', x_hi='terminate',
                           y_lo='reflect', y_hi='terminate'),
                  gauges=[(0.3, 0.8), g2, (0.6, 0.5), (1.0, 1.0)],
                  n_snapshots=1, record_frames=0, solver='native', **kw)


#: 3D likewise: a 1.2 m cube of 0.06 m cells, a smeared 1 kg charge, a
#: wall x 0.73-0.9 holding G2; every gauge on the live y plane
WALL_3D = (0.73, 0.9, 0.0, 1.2, 0.0, 1.2)


def case3d(g2, **kw):
    return Case3D(Lx=1.2, Ly=1.2, Lz=1.2, cell_size_m=0.06, charge=1.0,
                  center=(0.3, 0.57, 0.6), charge_resolution='smear',
                  obstacles=[WALL_3D],
                  bcs={s: 'transmit' for s in ('x_lo', 'x_hi', 'y_lo',
                                               'y_hi', 'z_lo', 'z_hi')},
                  gauges=[(0.3, 0.57, 0.9), g2, (0.5, 0.57, 0.6),
                          (0.3, 0.57, 0.2)],
                  n_snapshots=1, record_frames=0, t_end=1e-3,
                  solver='native', **kw)


KEPT_2D, IN_WALL_2D = (0.2, 0.2), (1.4, 0.3)
KEPT_3D, IN_WALL_3D = (0.1, 0.1, 0.1), (0.8, 0.57, 0.6)


def characterise(tag, solve, make, kept, in_wall):
    print(f'\n{tag}: the no-drop control (G2 kept), trigger 3, terminate')
    ctl, _ = run(solve, make(kept, trigger_gauge=3))
    trig = ctl.meta.get('trigger') or {}
    check(f'{tag} control: the run stops on the trigger gauge, G3',
          ctl.stop_reason.startswith('trigger gauge 3 reached')
          and trig.get('gauge') == 3 and ctl.meta['trigger_gauge'] == 3,
          f'{ctl.stop_reason!r} {trig}')
    check(f'{tag} control: G3 is the third series, at its snapped point',
          tuple(trig.get('point', ())) == tuple(ctl.gauges['points'][2]),
          f'{trig.get("point")} {ctl.gauges["points"]}')
    print(f'  control stop {ctl.stop_reason!r}, t = '
          f'{trig.get("t", 0.0) * 1e3:.3f} ms')
    drop, hooks = run(solve, make(in_wall, trigger_gauge=3))
    trig = drop.meta.get('trigger') or {}
    print(f'  drop case (G2 in the wall): stop {drop.stop_reason!r}, t = '
          f'{trig.get("t", 0.0) * 1e3:.3f} ms, '
          f'meta trigger_gauge {drop.meta.get("trigger_gauge")}, '
          f'live labels {[g[0] for g in hooks.info["gauges"]]}')
    two, _ = run(solve, make(in_wall, trigger_gauge=2))
    trig = two.meta.get('trigger') or {}
    print(f'  trigger 2 (the dropped gauge): stop {two.stop_reason!r}, '
          f't = {trig.get("t", 0.0) * 1e3:.3f} ms')
    return ctl, drop, hooks


def main():
    characterise('2D', solve_2d, case2d, KEPT_2D, IN_WALL_2D)
    characterise('3D', solve_3d, case3d, KEPT_3D, IN_WALL_3D)
    print()
    if FAILS:
        print(f'TRIGGER NUMBERING: FAIL ({len(FAILS)}): {", ".join(FAILS)}')
        return 1
    print('TRIGGER NUMBERING: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
