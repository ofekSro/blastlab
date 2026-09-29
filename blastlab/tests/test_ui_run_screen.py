"""GUI-6 gate: the 02 Run screen (docs/gui-redesign-plan.md §6, boards
Run / Run_Finished; batch docs/batches/2026-09-29-gui-run.md).

 R1  three columns 280 / centre / 340; nothing clipped at 1100 x 720 with
     Step through open (the controls scroll); Stop / Run swap by
     visibility and enablement, `Run again` after a finished run; Min /
     Max only with the auto switch off; Step through collapsed, opened by
     an Initialise, its six buttons emit today's commands; the resolved
     model-folder line; the Setup link; 0-D hides (never greys) what an
     HD 1.3 assessment does not have.

Plain script, offscreen, throwaway settings, no solver run:
    cd blastlab/tests && python test_ui_run_screen.py
"""
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)

from blastlab.ui.testing import ensure_qapp, pump, use_model  # noqa: E402

app = ensure_qapp()

from PySide6.QtCore import Qt                                 # noqa: E402
from PySide6.QtTest import QTest                              # noqa: E402

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def quiet(win):
    """Stop the window's debounced validation, so a check's own
    set_validation is not overwritten 300 ms later."""
    win._validate_timer.stop()


def r1_layout(win):
    from test_ui_parity import clipped
    from blastlab.services.model_folder import folder_for
    from blastlab.ui import run_panel as RP
    from blastlab.ui.setup_strip import fmt_count
    rp = win.run_panel
    print('\nR1: three columns, the controls, the Setup link, 0-D')
    win.resize(1600, 1000)
    win._show('run')
    pump(300)
    c, m, g = rp.column_widths()
    check('1600 x 1000: controls 280, gauges 340 (±1 px)',
          abs(c - 280) <= 1 and abs(g - 340) <= 1, f'{c} / {m} / {g}')
    check('and the centre takes the rest', m > 800, str(m))

    win.resize(1100, 720)
    pump(300)
    c, m, g = rp.column_widths()
    check('1100 x 720: the side columns keep 280 / 340',
          (c, g) == (280, 340), f'{c} / {m} / {g}')
    rp.step_card.set_open(True)
    pump(200)
    bad = clipped(win)
    check('Step through open at 1100 x 720: nothing clipped', not bad,
          str(bad[:3]))
    sb = rp._ctrl_scroll.verticalScrollBar()
    check('the controls column scrolls instead (vertical only)',
          sb.maximum() > 0
          and rp._ctrl_scroll.horizontalScrollBarPolicy()
          == Qt.ScrollBarAlwaysOff, f'max {sb.maximum()}')
    rp.step_card.set_open(False)
    pump(100)

    # ── Stop / Run ───────────────────────────────────────────────────────
    quiet(win)
    rp.set_validation(True)
    check('idle: Run is visible, enabled and reads Run',
          rp.run_btn.isVisibleTo(rp) and rp.run_btn.isEnabled()
          and rp.run_btn.text() == 'Run', rp.run_btn.text())
    check('idle: Stop is hidden and disabled',
          rp.stop_btn.isHidden() and not rp.stop_btn.isEnabled())
    rp.set_running(True)
    pump(30)
    check('running: Run hidden and disabled, Stop shown and enabled',
          rp.run_btn.isHidden() and not rp.run_btn.isEnabled()
          and rp.stop_btn.isVisibleTo(rp) and rp.stop_btn.isEnabled())
    check("Stop has the `stop` property and is still named 'danger' (U3)",
          bool(rp.stop_btn.property('stop'))
          and rp.stop_btn.objectName() == 'danger',
          f'{rp.stop_btn.property("stop")!r} {rp.stop_btn.objectName()!r}')
    check('Stop is the board 48 px', rp.stop_btn.height() == 48,
          str(rp.stop_btn.height()))
    rp.set_run_again(True)          # T7 sets this; in 6a the test hook
    rp.set_running(False)
    pump(30)
    check('after a finished run the idle button reads Run again',
          rp.run_btn.text() == 'Run again' and rp.run_btn.isVisibleTo(rp)
          and rp.stop_btn.isHidden(), rp.run_btn.text())
    check('Run is the board 48 px', rp.run_btn.height() == 48,
          str(rp.run_btn.height()))
    check('the 3D square is 56 x 48, icon only, with its tooltip',
          (rp.view3d_btn.width(), rp.view3d_btn.height()) == (56, 48)
          and rp.view3d_btn.text() == ''
          and rp.view3d_btn.toolTip() == 'Open the 3D view',
          f'{rp.view3d_btn.width()} x {rp.view3d_btn.height()}')
    rp.set_run_again(False)

    # ── colour range ─────────────────────────────────────────────────────
    check('auto on: Min / Max hidden and disabled',
          rp.auto_clim.isChecked()
          and not rp.clim_min.isVisibleTo(rp)
          and not rp.clim_max.isVisibleTo(rp)
          and not rp.clim_min.isEnabled() and not rp.clim_max.isEnabled())
    check('the auto switch is a ToggleSwitch (a QCheckBox)',
          type(rp.auto_clim).__name__ == 'ToggleSwitch')
    rp.auto_clim.setChecked(False)
    rp.clim_min.setText('0')
    rp.clim_max.setText('50')
    rp._clim_changed()
    pump(30)
    check('auto off: Min / Max shown and enabled',
          rp.clim_min.isVisibleTo(rp) and rp.clim_max.isVisibleTo(rp)
          and rp.clim_min.isEnabled() and rp.clim_max.isEnabled())
    check('live_clim() as U6', rp.live_clim() == (0.0, 50.0),
          str(rp.live_clim()))
    rp.auto_clim.setChecked(True)
    check('auto back on: None again', rp.live_clim() is None)

    # ── Step through ─────────────────────────────────────────────────────
    check('Step through is collapsed by default, hint Exec 1 … 1000',
          not rp.step_card.is_open()
          and rp.step_card.hint_text() == 'Exec 1 … 1000',
          rp.step_card.hint_text())
    use_model(win, 'R1')
    starts = []
    real_start = win.ctrl.start_stages

    def fake_start(dim_cases, paused=False, **kw):
        starts.append(paused)
        win.on_running(True)        # what the controller's _launch does
        return True

    win.ctrl.start_stages = fake_start
    try:
        win._init_model()
        pump(50)
    finally:
        win.ctrl.start_stages = real_start
    check('an Initialise (paused=True) opens Step through',
          starts == [True] and rp.step_card.is_open(), str(starts))
    got = []
    rp.exec_requested.connect(got.append)
    for b in rp._exec_btns:
        b.click()
    check('the six buttons emit 1, 10, 100, 1000, run, pause',
          got == [1, 10, 100, 1000, 'run', 'pause'], str(got))
    check('their texts', [b.text() for b in rp._exec_btns]
          == ['+1', '+10', '+100', '+1000', 'To the end', 'Pause'],
          str([b.text() for b in rp._exec_btns]))
    rp.exec_requested.disconnect(got.append)
    win.on_running(False)
    rp.step_card.set_open(False)
    pump(30)

    # ── the resolved model folder ────────────────────────────────────────
    runs = tempfile.mkdtemp(prefix='blastlab_runs_r1_')
    rp.set_runs_dir(runs)
    rp.run_name.setText('ABC')
    pump(RP.PATH_DEBOUNCE_MS + 150)
    want = folder_for(runs, 'ABC') + os.sep
    check('the path line is folder_for(runs, model) + os.sep',
          rp.path_text() == want, f'{rp.path_text()!r} vs {want!r}')
    rp.run_name.setText('')
    pump(RP.PATH_DEBOUNCE_MS + 150)
    check('a blank box reads <Runs folder>\\<Model>\\',
          rp.path_text() == '<Runs folder>' + os.sep + '<Model>' + os.sep,
          rp.path_text())
    use_model(win, 'R1')

    # ── the Setup link ───────────────────────────────────────────────────
    quiet(win)
    rp.set_validation(True, n_cells=368449)
    want = f'Setup: Case OK · {fmt_count(368449)} cells'
    check('the link reads Setup: Case OK · 368 k cells',
          rp.setup_link_text() == want, f'{rp.setup_link_text()!r}')
    check("and its state is 'ok'", rp.setup_link.property('state') == 'ok')
    rp.set_validation(False, 3)
    check("U2's text is unchanged: '3 errors - see Setup'",
          rp._valid_lbl.text() == '3 errors - see Setup'
          and rp.setup_link.property('state') == 'error'
          and rp.setup_link.cells.isHidden(), rp._valid_lbl.text())
    rp.set_validation(True, n_cells=368449)
    rp.setup_link.click()
    pump(50)
    check('a click on the link shows Setup', win.current_tab() == 'setup',
          str(win.current_tab()))
    win._show('run')
    pump(50)

    # ── 0-D ──────────────────────────────────────────────────────────────
    hideable = dict(step=rp.step_card, live=rp.live_card,
                    view3d=rp.view3d_btn, time=rp._tile_time,
                    stepno=rp._tile_step, pmax=rp._tile_pmax)
    win.setup.set_dim(0)
    pump(100)
    check('0-D hides Step through, Live view, 3D and the three tiles',
          all(w.isHidden() for w in hideable.values()),
          str([k for k, w in hideable.items() if not w.isHidden()]))
    check('Runs folder, Model, Run and the log stay',
          all(w.isVisibleTo(rp) for w in (rp.runs_dir, rp.run_name,
                                           rp.run_btn, rp.log)))
    win.setup.set_dim(2)
    pump(100)
    check('2D shows them again',
          not any(w.isHidden() for w in hideable.values()),
          str([k for k, w in hideable.items() if w.isHidden()]))


def main():
    from blastlab.ui.app import MainWindow
    crashes = []
    sys.excepthook = lambda *a: crashes.append(a)
    win = MainWindow()
    win.show()
    pump(200)
    try:
        r1_layout(win)
    finally:
        check('nothing raised', not crashes, str(crashes[:1]))
        win.close()
        pump(100)
    bad = [m for m in sys.modules
           if m.split('.')[0] in ('vtk', 'vtkmodules', 'pyvista', 'pyvistaqt')
           or m == 'matplotlib.pyplot']
    check('no VTK / pyplot in the GUI process', not bad, str(bad[:3]))
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'UI RUN SCREEN: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
