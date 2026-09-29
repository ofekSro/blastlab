"""GUI-6 gate: the 02 Run screen (docs/gui-redesign-plan.md §6, boards
Run / Run_Finished; batch docs/batches/2026-09-29-gui-run.md).

 R1  three columns 280 / centre / 340; nothing clipped at 1100 x 720 with
     Step through open (the controls scroll); Stop / Run swap by
     visibility and enablement, `Run again` after a finished run; Min /
     Max only with the auto switch off; Step through collapsed, opened by
     an Initialise, its six buttons emit today's commands; the resolved
     model-folder line; the Setup link; 0-D hides (never greys) what an
     HD 1.3 assessment does not have;
 R2  the run clock (fake `now`): fmt_duration, `10 s elapsed` below 5 %,
     elapsed + the linear ETA from 5 %, held time excluded, Done /
     Stopped / Ended, HD 1.3 busy (indeterminate bar, `HD 1.3
     assessment`), chip_texts() with U4's strings, dt in STEP's caption;
 R3  Stop (fake clock, patched `running`): at once under 30 s, asks from
     30 s with `Stop the run` / `Keep running`, the text (model, percent,
     run time, the blastFoam sentence, a chain's stage), no stop when the
     run ended meanwhile, held time excluded; Shift+Esc and the button go
     the same way, plain Esc does nothing.

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


class FakeClock:
    """A settable monotonic clock for RunClock.now."""

    def __init__(self, t=0.0):
        self.t = float(t)

    def __call__(self):
        return self.t


def r2_clock(win):
    from blastlab.solvers.hooks import Progress
    from blastlab.ui.run_clock import RunClock, fmt_duration
    rp = win.run_panel
    print('\nR2: the run clock, elapsed and ETA, the tiles')
    got = [fmt_duration(s) for s in (0, 12, 59.6, 60, 258, 331, 3720)]
    want = ['0 s', '12 s', '1 min 0 s', '1 min 0 s', '4 min 18 s',
            '5 min 31 s', '1 h 02 min']
    check('fmt_duration 0, 12, 59.6, 60, 258, 331, 3720 s', got == want,
          str(got))

    fake = FakeClock()
    real_now = win._run_clock.now
    win._run_clock.now = fake
    win.ctrl._stage_dims = [2]
    try:
        fake.t = 0.0
        win.on_running(True)
        check('the 1 s refresh runs while a run is live',
              rp._tick.isActive() and rp._tick.interval() == 1000)
        fake.t = 10.0
        win.on_progress(Progress(step=40, t=1e-4, dt=2.5e-7, p_max=2e5,
                                 frac=0.04))
        check('4 % at 10 s: `10 s elapsed`, no estimate yet',
              rp.time_text() == '10 s elapsed', rp.time_text())
        check('the percent reads 4 %', rp.pct_text() == '4 %',
              rp.pct_text())
        fake.t = 258.0
        win.on_progress(Progress(step=11284, t=4.9e-3, dt=4.1e-7,
                                 p_max=2.31e5, frac=0.78))
        eta = fmt_duration(258.0 * (1 - 0.78) / 0.78)
        want = f'4 min 18 s elapsed · about {eta} left'
        check('78 % at 258 s: elapsed and the linear ETA',
              rp.time_text() == want and eta == '1 min 13 s',
              f'{rp.time_text()!r} vs {want!r}')
        check('the tile strip shows 78 %', rp.pct_text() == '78 %')
        win.on_paused(True)
        check('held: `held at step N · … elapsed`, no ETA',
              rp.time_text() == 'held at step 11284 · 4 min 18 s elapsed',
              rp.time_text())
        fake.t = 400.0
        win.on_paused(False)
        check('released: held time is not run time',
              abs(win._run_clock.run_s() - 258.0) < 1e-9,
              str(win._run_clock.run_s()))
        fake.t = 450.0
        win.on_running(False)
        win.on_finished(False, False)
        check('a run with no result reads `Ended after …`',
              rp.time_text() == 'Ended after 5 min 8 s', rp.time_text())
        check('the refresh stops when idle', not rp._tick.isActive())
        win._run_got_result = True
        win.on_finished(False, False)
        check('a finished run reads `Done in …`',
              rp.time_text() == 'Done in 5 min 8 s', rp.time_text())
        win.on_finished(True, False)
        check('a stopped one `Stopped after …`',
              rp.time_text() == 'Stopped after 5 min 8 s', rp.time_text())
        # Initialise: the run starts held
        fake.t = 1000.0
        win._start_paused = True
        win.on_running(True)
        win._start_paused = False
        fake.t = 1100.0
        check('an Initialise start begins held (run time 0 after 100 s)',
              win._run_clock.held() and win._run_clock.run_s() == 0.0,
              f'{win._run_clock.held()} {win._run_clock.run_s()}')
        win.on_running(False)
    finally:
        win._run_clock.now = real_now
        win.ctrl._stage_dims = []

    c = RunClock(now=fake)
    fake.t = 0.0
    c.start()
    fake.t = 100.0
    c.hold(True)
    fake.t = 400.0
    c.hold(False)
    fake.t = 410.0
    check('hold 100 → 400 s, read at 410 s: run_s() is 110',
          abs(c.run_s() - 110.0) < 1e-9, str(c.run_s()))
    check('eta_s is None below 5 % and while held',
          c.eta_s(0.049) is None
          and (c.hold(True) or c.eta_s(0.5) is None))
    c.hold(False)
    fake.t = 500.0
    c.stage()
    fake.t = 520.0
    check('a stage restarts stage_s (ETA per stage), run_s goes on',
          abs(c.stage_s() - 20.0) < 1e-9 and c.run_s() > 110.0,
          f'{c.stage_s()} {c.run_s()}')

    # ── HD 1.3 busy ──────────────────────────────────────────────────────
    bar = rp.progress
    bar.setRange(0, 1000)
    bar.setValue(420)
    win._set_hd13_busy(True)
    try:
        check('HD 1.3 busy: the bar is indeterminate (0, 0)',
              (bar.minimum(), bar.maximum()) == (0, 0))
        check('the line starts with `HD 1.3 assessment`, percent —',
              rp.time_text().startswith('HD 1.3 assessment')
              and rp.pct_text() == '—',
              f'{rp.time_text()!r} {rp.pct_text()!r}')
    finally:
        win._set_hd13_busy(False)
    check('after it the old range and value are back',
          (bar.minimum(), bar.maximum(), bar.value()) == (0, 1000, 420),
          f'{bar.minimum()} {bar.maximum()} {bar.value()}')

    # ── the tiles keep U4's strings ──────────────────────────────────────
    rp.on_progress(Progress(step=1234, t=1.5e-3, dt=2.5e-7, p_max=345678.0,
                            frac=0.37))
    chips = rp.chip_texts()
    check("chip_texts() keeps U4's five keys and strings",
          chips == {'step': '1234', 't [ms]': '1.500', 'dt [s]': '2.50e-07',
                    'p max [kPa]': '345.7', 'cells': '—'}, str(chips))
    check("the STEP tile's caption reads `dt 2.50e-07 s`",
          rp._tile_step.caption.text() == 'dt 2.50e-07 s',
          rp._tile_step.caption.text())
    check('TIME is captioned simulated, P MAX in the field now',
          rp._tile_time.caption.text() == 'simulated'
          and rp._tile_pmax.caption.text() == 'in the field now')


def r3_stop(win):
    from types import SimpleNamespace
    from unittest.mock import PropertyMock, patch
    from PySide6.QtGui import QShortcut
    from blastlab.ui import dialogs
    from blastlab.ui.app import STOP_CONFIRM_S
    from blastlab.ui.run_clock import fmt_duration
    from blastlab.ui.run_controller import RunController
    rp = win.run_panel
    print('\nR3: Stop confirms after 30 s of run time')
    check('STOP_CONFIRM_S is 30 s', STOP_CONFIRM_S == 30.0)
    fake = FakeClock()
    clock = win._run_clock
    real_now, real_stop, real_ask = clock.now, win.ctrl.stop, \
        dialogs.ask_yes_no
    stops, asks, answers = [], [], []

    def ask(title, text, parent=None, **kw):
        asks.append(dict(title=title, text=text, **kw))
        ans = answers.pop(0) if answers else False
        if callable(ans):
            return ans()
        return ans

    def reset():
        stops.clear()
        asks.clear()
        answers.clear()

    running = patch.object(RunController, 'running',
                           new_callable=PropertyMock, return_value=True)
    pm = running.start()
    clock.now = fake
    win.ctrl.stop = lambda: stops.append(1)
    dialogs.ask_yes_no = ask
    saved = (win.ctrl._run_name, win._run_pct, win._chain_k, win._chain_n,
             win._run_cases)
    try:
        win.ctrl._run_name = 'wall_A'
        win._run_pct = 78
        win._chain_k, win._chain_n = 1, 1
        win._run_cases = [SimpleNamespace(solver='native')]
        fake.t = 0.0
        clock.start()

        fake.t = 29.9
        reset()
        win._stop()
        check('29.9 s: no question, stop at once',
              asks == [] and stops == [1], f'{asks} {stops}')

        fake.t = 30.0
        reset()
        win._stop()
        check('30.0 s: it asks once, and Keep running does not stop',
              len(asks) == 1 and stops == [], f'{len(asks)} {stops}')
        a = asks[0] if asks else {}
        check("title `Stop the run`, labels `Stop the run` / `Keep running`",
              a.get('title') == 'Stop the run'
              and a.get('yes') == 'Stop the run'
              and a.get('no') == 'Keep running', str(a))

        fake.t = 258.0
        reset()
        answers.append(True)
        win._stop()
        text = asks[0]['text'] if asks else ''
        check('258 s: the text names `wall_A at 78 %` and `4 min 18 s`',
              'Stop wall_A at 78 %?' in text
              and f'running for {fmt_duration(258)}.' in text
              and fmt_duration(258) == '4 min 18 s', repr(text))
        check('Stop the run: stop is called once', stops == [1],
              str(stops))
        check('no blastFoam sentence for a native stage',
              'blastFoam keeps' not in text, repr(text))

        reset()

        def ended_meanwhile():
            pm.return_value = False
            return True

        answers.append(ended_meanwhile)
        win._stop()
        pm.return_value = True
        check('the run ended while the dialog was open: stop not called',
              len(asks) == 1 and stops == [], f'{len(asks)} {stops}')

        # held time is excluded: hold 10 -> 500 s, press at 505 s
        fake.t = 0.0
        clock.start()
        fake.t = 10.0
        clock.hold(True)
        fake.t = 500.0
        clock.hold(False)
        fake.t = 505.0
        reset()
        win._stop()
        check('held 10 → 500 s, pressed at 505 s: 15 s of run time, '
              'stops at once', asks == [] and stops == [1]
              and abs(clock.run_s() - 15.0) < 1e-9,
              f'{asks} {stops} {clock.run_s()}')

        # the blastFoam sentence, and a chain's stage
        fake.t = 0.0
        clock.start()
        fake.t = 60.0
        win._run_cases = [SimpleNamespace(solver='native'),
                          SimpleNamespace(solver='blastfoam'),
                          SimpleNamespace(solver='native')]
        win._chain_k, win._chain_n = 2, 3
        reset()
        win._stop()
        text = asks[0]['text'] if asks else ''
        check('a chain reads `Stop wall_A (stage 2 of 3) at 78 %?`',
              text.startswith('Stop wall_A (stage 2 of 3) at 78 %?'),
              repr(text))
        check('a blastFoam stage adds the resume sentence',
              text.endswith(' blastFoam keeps what it has written, so you '
                            'can resume it later from the runs list.'),
              repr(text))
        win._chain_k, win._chain_n = 1, 1
        win._run_cases = [SimpleNamespace(solver='native')]

        # the keys: Shift+Esc asks at 30 s, plain Esc does nothing
        keys = {sc.key().toString() for sc in win.findChildren(QShortcut)}
        check("no QShortcut has the key `Esc`", 'Esc' not in keys,
              str(sorted(keys)))
        reset()
        for sc in win.findChildren(QShortcut):
            if sc.key().toString() == 'Shift+Esc':
                sc.activated.emit()
        pump(20)
        check('the Shift+Esc shortcut reaches the same path (asks at 60 s)',
              len(asks) == 1 and stops == [], f'{len(asks)} {stops}')
        reset()
        win._show('run')
        win.activateWindow()
        QTest.keyClick(win, Qt.Key_Escape)
        pump(20)
        check('plain Esc: neither the dialog nor stop',
              asks == [] and stops == [], f'{asks} {stops}')
        # the control: the same delivery with Shift held does reach it,
        # so the Esc check above is not vacuous
        QTest.keyClick(win, Qt.Key_Escape, Qt.ShiftModifier)
        pump(20)
        check('a real Shift+Esc key click asks (the control for Esc)',
              len(asks) == 1 and stops == [], f'{len(asks)} {stops}')
        reset()
        reset()
        rp.set_running(True)
        rp.stop_btn.click()
        pump(20)
        check('stop_btn.click() behaves as Shift+Esc (asks at 60 s)',
              len(asks) == 1 and stops == [], f'{len(asks)} {stops}')
        rp.set_running(False)
        check('the Stop tooltip names Shift+Esc and the 30 s rule',
              'Shift+Esc' in rp.stop_btn.toolTip()
              and '30 s' in rp.stop_btn.toolTip(), rp.stop_btn.toolTip())
    finally:
        running.stop()
        clock.now = real_now
        clock.stop()
        win.ctrl.stop = real_stop
        dialogs.ask_yes_no = real_ask
        (win.ctrl._run_name, win._run_pct, win._chain_k, win._chain_n,
         win._run_cases) = saved


def main():
    from blastlab.ui.app import MainWindow
    crashes = []
    sys.excepthook = lambda *a: crashes.append(a)
    win = MainWindow()
    win.show()
    pump(200)
    try:
        r1_layout(win)
        r2_clock(win)
        r3_stop(win)
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
