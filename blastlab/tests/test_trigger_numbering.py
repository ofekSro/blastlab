"""P1-24: the native T51 trigger and live labels count gauges as entered.

The case of GUI-14 B verify issue 1 (`docs/batches/2026-10-11-gui-14-
backlog-B.verify.md`): gauges G1 (0.3, 0.8), G2 (1.4, 0.3) inside Wall 1,
G3 (0.6, 0.5) and G4 (1.0, 1.0), trigger gauge 3, `terminate`. Gauges
are passive probes, so the run must stop exactly where the control - the
same case with G2 kept at (0.2, 0.2) - stops. 3D likewise.

The characterisation (commit 4e4a40f) pinned the control; before the fix
the drop case stopped on G4's point (2D 0.284 ms against 0.091 ms) and a
trigger on the dropped G2 fired on G3. Now:

  * the drop case stops on G3, at the control's exact trigger time, with
    `meta['trigger_gauge'] == 3` and live labels [1, 3, 4];
  * a trigger on the dropped gauge is disabled: validate_case warns
    (native only, D13) and the run ends by its normal stop;
  * Results selects the trigger's row, G3, by default.

Tiny grids, no WSL; one offscreen Qt widget.
Run:  cd blastlab/tests && python test_trigger_numbering.py
"""
import os
import sys
import types

os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import geometry                              # noqa: E402
from blastlab.core.case import Case2D, Case3D                   # noqa: E402
from blastlab.services.validation import validate_case          # noqa: E402
from blastlab.solvers.hooks import RunHooks, trigger_index      # noqa: E402
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


def index_checks():
    print('\ntrigger_index with the entered numbers of the kept gauges')
    hooks = Cap()
    kept = [1, 3, 4]
    check('trigger 3 is the second kept gauge (index 1)',
          trigger_index(3, 4, hooks, numbers=kept) == 1)
    check('trigger 2, dropped: disabled with a "was dropped" line',
          trigger_index(2, 4, hooks, numbers=kept) is None
          and hooks.lines[-1].strip()
          == '[warn] Trigger gauge 2 was dropped - trigger disabled',
          str(hooks.lines))
    check('trigger 5 of 4 entered: does not exist, counted as entered',
          trigger_index(5, 4, hooks, numbers=kept) is None
          and '(4 gauge(s))' in hooks.lines[-1], str(hooks.lines))
    check('no numbers: the 1-based index, as before',
          trigger_index(3, 4, hooks) == 2)
    pts = [(0.1, 0.5, 0.2), (0.4, 0.5, 0.3), (0.7, 0.9, 0.3)]
    sl = (slice(None), 5, slice(None))
    coords = ([0.0], [0.05 + 0.1 * k for k in range(10)], [0.0])
    check('plane_gauges labels the points with their entered numbers',
          [g[0] for g in geometry.plane_gauges(pts, sl, coords, 0.1,
                                               numbers=[1, 3, 4])]
          == [1, 3]
          and [g[0] for g in geometry.plane_gauges(pts, sl, coords, 0.1)]
          == [1, 2])


def numbering(tag, solve, make, kept, in_wall):
    print(f'\n{tag}: G2 dropped, trigger 3, terminate - against the '
          f'control (G2 kept)')
    ctl, _ = run(solve, make(kept, trigger_gauge=3))
    ctl_trig = ctl.meta.get('trigger') or {}
    check(f'{tag} control: the run stops on the trigger gauge, G3',
          ctl.stop_reason.startswith('trigger gauge 3 reached')
          and ctl_trig.get('gauge') == 3 and ctl.meta['trigger_gauge'] == 3,
          f'{ctl.stop_reason!r} {ctl_trig}')
    check(f'{tag} control: G3 is the third series, at its snapped point',
          tuple(ctl_trig.get('point', ())) == tuple(ctl.gauges['points'][2]),
          f'{ctl_trig.get("point")} {ctl.gauges["points"]}')
    drop, hooks = run(solve, make(in_wall, trigger_gauge=3))
    trig = drop.meta.get('trigger') or {}
    check(f'{tag}: the run stops on G3\'s point, as the control does',
          drop.stop_reason == ctl.stop_reason
          and tuple(trig.get('point', ())) == tuple(ctl_trig['point']),
          f'{drop.stop_reason!r} vs {ctl.stop_reason!r}')
    check(f'{tag}: meta trigger t equals the control\'s exactly '
          f'({ctl_trig["t"] * 1e3:.3f} ms)',
          trig.get('t') == ctl_trig['t'],
          f'{trig.get("t")} vs {ctl_trig["t"]}')
    check(f'{tag}: meta trigger_gauge and trigger gauge are 3',
          drop.meta['trigger_gauge'] == 3 and trig.get('gauge') == 3,
          f'{drop.meta["trigger_gauge"]} {trig}')
    labels = [g[0] for g in hooks.info['gauges']]
    check(f'{tag}: live labels are the entered numbers [1, 3, 4]',
          labels == [1, 3, 4] and hooks.info['trigger_gauge'] == 3,
          f'{labels} {hooks.info["trigger_gauge"]}')
    check(f'{tag}: the log names Trigger gauge 3 and no "does not exist"',
          any(ln.strip().startswith('Trigger gauge 3 (')
              for ln in hooks.lines)
          and not any('does not exist' in ln for ln in hooks.lines))

    print(f'\n{tag}: trigger 2 - the dropped gauge')
    case = make(in_wall, trigger_gauge=2)
    warns = [w for w in validate_case(case).warnings
             if 'Trigger' in w and 'G2' in w]
    check(f'{tag}: validate_case warns once, naming G2 and the trigger',
          len(warns) == 1 and 'disabled' in warns[0], str(warns))
    foam = make(in_wall, trigger_gauge=2)
    foam.solver = 'blastfoam'
    check(f'{tag}: blastFoam gets no such warning (D13, native only)',
          not any('Trigger disabled' in w
                  for w in validate_case(foam).warnings))
    two, hooks = run(solve, case)
    check(f'{tag}: the trigger is disabled and the run ends by its '
          f'normal stop',
          not two.stop_reason.startswith('trigger')
          and 'trigger' not in two.meta
          and two.meta['trigger_gauge'] is None
          and any('Trigger gauge 2 was dropped - trigger disabled' in ln
                  for ln in hooks.lines),
          f'{two.stop_reason!r} {two.meta["trigger_gauge"]}')
    return drop


def results_check(res):
    print('\nResults on the 2D drop run')
    from PySide6.QtWidgets import QApplication
    from blastlab.ui.results_gauges import GaugesView
    app = QApplication.instance() or QApplication([])
    view = GaugesView()
    view.set_result(types.SimpleNamespace(result=res, dim=2))
    app.processEvents()
    sel = view.selected()
    check('Results selects G3, the trigger gauge, by default',
          view.label(sel) == 'G3'
          and view.readout_text()[0].startswith('G3'),
          f'{sel} {view.label(sel)} {view.readout_text()}')
    view.deleteLater()
    app.processEvents()


def main():
    index_checks()
    drop2 = numbering('2D', solve_2d, case2d, KEPT_2D, IN_WALL_2D)
    numbering('3D', solve_3d, case3d, KEPT_3D, IN_WALL_3D)
    results_check(drop2)
    print()
    if FAILS:
        print(f'TRIGGER NUMBERING: FAIL ({len(FAILS)}): {", ".join(FAILS)}')
        return 1
    print('TRIGGER NUMBERING: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
