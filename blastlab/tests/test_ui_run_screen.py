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
     the same way, plain Esc does nothing;
 R4  the dock: a new run keeps the last run's log as an earlier run
     (log_text() is the current run's), Earlier runs shows and copies it,
     Save log… writes the shown text as UTF-8 (a cancel writes nothing),
     notify() lands in Messages, the history caps at 20;
 R5  the live-gauge column (6b): Z of the entered gauge each snapped
     series belongs to, sorted by Z, `waiting` before arrival and
     summarize_trace's peak after it; planar sorts by R; a dropped gauge;
     the click and the trigger default; the now line; the collection
     rule; the last stage's full traces;
 R6  the end of a run (6b): the finish banner (stop_reason verbatim, the
     model folder), one desktop notification for a run that ended on
     its own (run time, highest peak from summarize_gauges), `✓ Done`
     in the title, `Run again`; a stopped run gets the banner only, an
     errored or result-less one nothing; the next start clears it all;
     close leaves no tray icon;
 R7  the chain hook (6b; GUI-9 builds the strip): `chain_slot` hidden at
     zero height for a single run, set_chain_strip shows a widget above
     the progress strip and None hides it again; `Chain 2/3 · …`;
 R8  the banner and the embedded 3D viewer (T9): show_finish shrinks the
     viewer's window by the banner's height first, only while the 3D view
     is on screen and the banner was hidden;
 R9  (GUI-10, F23) copying the wrapped model-folder path: Ctrl+C and the
     context menu's Copy give the path without U+200B; no QShortcut.
 R10 (GUI-10, F34) at 1100 x 720 a scientific P MAX keeps its unit: the
     tile's value face steps down, the tile keeps its height.
 R11 (GUI-11 T5, F12 / D206) the 0-D run flow: 02 Run, the greys, the
     note in place of the toolbar and the view, F5 while busy, `—` after.

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
from PySide6.QtWidgets import QToolButton                     # noqa: E402

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
    # T5 found the Progress tile never on screen: arrange() re-applied
    # the isHidden() of a parentless, never-shown frame
    s = rp.strip
    check('the Progress tile (bar, percent, time line) is on screen',
          s.progress_tile.isVisibleTo(rp) and rp.progress.isVisibleTo(rp)
          and s.time_lbl.isVisibleTo(rp) and s.pct_lbl.isVisibleTo(rp))
    check('1600 x 1000: the strip is one row, Progress 2.3 x a tile '
          '(board flex)', s.rows() == 1
          and abs(s.progress_tile.width() / rp._tile_time.width() - 2.3)
          < 0.1, f'{s.rows()} {s.progress_tile.width()} '
                 f'{rp._tile_time.width()}')

    win.resize(1100, 720)
    pump(300)
    c, m, g = rp.column_widths()
    check('1100 x 720: the side columns keep 280 / 340',
          (c, g) == (280, 340), f'{c} / {m} / {g}')
    check('1100 x 720: two rows, Progress on top of the three tiles',
          s.rows() == 2 and s.progress_tile.isVisibleTo(rp)
          and s.progress_tile.geometry().bottom()
          < rp._tile_time.geometry().top(),
          f'{s.rows()} {s.progress_tile.geometry()} '
          f'{rp._tile_time.geometry()}')
    check('and the view keeps >= 240 px of height (U15, risk 6)',
          rp._view_frame.height() >= 240
          and rp._view_frame.width() == rp._centre.width(),
          f'{rp._view_frame.width()} x {rp._view_frame.height()}')
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
    # the tab order (T1), walked through Qt's own focus chain while the
    # run is live and Step through open: the controls top to bottom,
    # the view toolbar, the dock's tabs, Copy, Save log…, the log last
    want = ([rp.runs_dir, rp.runs_browse, rp.run_name, rp.stop_btn,
             rp.step_card.header, *rp._exec_btns, rp.refresh_val,
             rp.refresh_mode, rp.auto_clim, rp.setup_link]
            + rp._view_seg.findChildren(QToolButton)
            + [rp.show_mesh]
            + [rp.dock.tabs.button(n) for n in rp.dock.tabs.names()]
            + [rp.dock.copy_btn, rp.dock.save_btn, rp.log])
    walked, w = [], rp.runs_dir
    for _ in range(5000):
        if rp.isAncestorOf(w) and w.isVisibleTo(win) and w.isEnabled() \
                and (w.focusPolicy() & Qt.TabFocus):
            walked.append(w)
        w = w.nextInFocusChain()
        if w is rp.runs_dir:
            break
    check('Tab walks the controls, the view toolbar, the dock, the log '
          'last', walked == want,
          ' -> '.join(type(x).__name__ for x in walked))
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


def contrast(fg, bg):
    """WCAG contrast ratio of two '#rrggbb' colours (plan §2.2; the
    formula of test_ui_theme, which cannot be imported: it moves
    theme.FONT_DIR at import)."""
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
        c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
             for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    a, b = lum(fg), lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def theme_qss_rule(name):
    """The app style sheet's rule for `QLabel#<name>` (its body)."""
    qss = app.styleSheet()
    i = qss.find(f'#{name} ')
    return qss[i:qss.find('}', i)] if i >= 0 else ''


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
        # T5: the PAUSED badge sits on `bg`, not on the tile's accent_bg
        # (light warn on accent_bg is 4.24:1)
        from blastlab.ui.theme import DARK, LIGHT
        check('the PAUSED badge shows while held, warn on bg >= 4.5:1',
              rp._paused_lbl.isVisibleTo(rp)
              and rp._paused_lbl.text() == 'PAUSED at step 11284'
              and 'background' in theme_qss_rule('pausedlbl')
              and min(contrast(p['warn'], p['bg']) for p in (DARK, LIGHT))
              >= 4.5)
        fake.t = 400.0
        win.on_paused(False)
        check('and hides when released', rp._paused_lbl.isHidden()
              and rp._paused_lbl.text() == '')
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


def r4_dock(win):
    from PySide6.QtWidgets import QApplication
    from blastlab.ui import dialogs
    from blastlab.ui import run_dock as RD
    rp = win.run_panel
    dock = rp.dock
    print('\nR4: the dock - Log · Messages · Earlier runs')
    check('three tabs, Copy and Save log… at the right',
          dock.tabs.names() == ['Log', 'Messages', 'Earlier runs']
          and dock.copy_btn.text() == 'Copy'
          and dock.save_btn.text() == 'Save log…',
          str(dock.tabs.names()))
    check('the Log page is the panel log (objectName log)',
          rp.log is dock.log and rp.log.objectName() == 'log')
    rp.log.clear()
    runs = tempfile.mkdtemp(prefix='blastlab_runs_r4_')
    f1 = os.path.join(runs, 'run1')
    rp.set_running(True, model='run1', folder=f1)
    rp.on_log('a')
    rp.on_log('b')
    rp.set_running(False)
    rp.mark_ended('done')
    rp.set_running(True, model='run2', folder=os.path.join(runs, 'run2'))
    hist = rp.log_history()
    check("run 2 starts: log_text() is '' (U14 holds)",
          rp.log_text() == '', repr(rp.log_text()))
    check("one entry, text 'a\\nb', named after run 1",
          len(hist) == 1 and hist[0]['text'] == 'a\nb'
          and hist[0]['model'] == 'run1' and hist[0]['folder'] == f1
          and hist[0]['how'] == 'done', str(hist[:1]))
    row = dock.earlier_list.item(0).text() if dock.earlier_list.count() \
        else ''
    check('the row reads `run1 · started HH:MM · finished · 2 lines`',
          row.startswith('run1 · started ')
          and row.endswith(' · finished · 2 lines'), row)
    check("its tooltip is the model folder's run.log",
          dock.earlier_list.item(0).toolTip()
          == os.path.join(f1, 'run.log'),
          dock.earlier_list.item(0).toolTip())
    rp.show_earlier(0)
    pump(30)
    check("selecting it shows 'a\\nb'",
          dock.tabs.get() == 'Earlier runs'
          and dock.earlier_text() == 'a\nb', repr(dock.earlier_text()))
    QApplication.clipboard().setText('')
    dock.copy_btn.click()
    check("Copy puts exactly 'a\\nb' on the clipboard",
          QApplication.clipboard().text() == 'a\nb',
          repr(QApplication.clipboard().text()))

    # ── Save log… ────────────────────────────────────────────────────────
    dock.tabs.set('Log')
    for line in ('dt = 0.25 µs', 'G1 → 296 kPa', 'last'):
        rp.on_log(line)
    real_save = dialogs.save_file
    out = os.path.join(tempfile.mkdtemp(prefix='blastlab_savelog_'),
                       'saved.log')
    calls = []

    def fake_save(title, filters='', parent=None, start='', **kw):
        calls.append(dict(title=title, filters=filters, start=start))
        return out

    dialogs.save_file = fake_save
    try:
        dock.save_btn.click()
    finally:
        dialogs.save_file = real_save
    shown = rp.log_text()
    with open(out, 'rb') as f:
        data = f.read()
    check('Save log… writes the shown text, UTF-8, \\n newlines',
          data == shown.encode('utf-8') and b'\r\n' not in data
          and 'µs' in shown and '→' in shown, repr(data[:60]))
    c = calls[0] if calls else {}
    check('the dialog: `Save log`, the Log filter, run-<model>-HHMMSS.log '
          'in the model folder',
          c.get('title') == 'Save log' and c.get('filters') == RD.LOG_FILTER
          and os.path.dirname(c.get('start', '')) == os.path.join(runs,
                                                                  'run2')
          and os.path.basename(c.get('start', '')).startswith('run-run2-')
          and c.get('start', '').endswith('.log'), str(c))
    dialogs.save_file = lambda *a, **k: ''
    before = set(os.listdir(os.path.dirname(out)))
    try:
        dock.save_btn.click()
    finally:
        dialogs.save_file = real_save
    check('a cancelled save writes nothing',
          set(os.listdir(os.path.dirname(out))) == before)
    # verify: an unwritable target says so through the dialog path
    # instead of raising out of the click
    errs = []
    real_err = dialogs.show_error
    dialogs.save_file = lambda *a, **k: os.path.join(
        os.path.dirname(out), 'no such folder', 'x.log')
    dialogs.show_error = lambda title, text, parent=None: errs.append(title)
    try:
        got = dock.save()
    finally:
        dialogs.save_file = real_save
        dialogs.show_error = real_err
    check('an unwritable path: one `Save log` error dialog, no exception',
          got is None and errs == ['Save log'], str(errs))
    rp.set_running(False)
    rp.mark_ended('stopped')

    # ── Messages ─────────────────────────────────────────────────────────
    win._status_timer.stop()
    win.notify('x', 'warn')
    msgs = rp.messages_text().splitlines()
    check('notify(x, warn) adds a Messages row `HH:MM:SS  warn  x`',
          bool(msgs) and msgs[-1].endswith('  warn  x')
          and len(msgs[-1].split('  ')[0]) == 8, repr(msgs[-1:]))
    check('and the status line and its 12 s timer behave as before',
          win._status.text() == 'x' and win._status_timer.isActive())
    dock.tabs.set('Messages')
    QApplication.clipboard().setText('')
    dock.copy()
    check('Copy on Messages copies the Messages text',
          QApplication.clipboard().text() == rp.messages_text())
    dock.tabs.set('Log')

    # ── the cap ──────────────────────────────────────────────────────────
    for i in range(21):
        rp.set_running(True, model=f'cap{i}', folder=None)
        rp.on_log(f'line {i}')
        rp.set_running(False)
    rp.set_running(True, model='cap-last', folder=None)
    hist = rp.log_history()
    check('21 more runs: the history caps at 20, newest first',
          len(hist) == RD.HISTORY_MAX == 20
          and hist[0]['model'] == 'cap20' and hist[-1]['model'] == 'cap1',
          f'{len(hist)} {hist[0]["model"]} {hist[-1]["model"]}')
    check('the tab reads `Earlier runs   20`',
          dock.tabs.label('Earlier runs') == 'Earlier runs   20',
          dock.tabs.label('Earlier runs'))
    rp.set_running(False)


def sample_case(**kw):
    """The boards' sample case (batch T6): 2D axisymmetric native, 1 kg
    TNT at z 2, 4 x 4 m, cell 25 mm, Wall 1 r 3.0-3.2 z 0-1.5, gauges G1
    (2.95, 0.50), G2 (2.95, 1.50), G3 (1.5, 0.5), G4 (3.30, 0.50) - G4
    behind the wall."""
    from blastlab.core.case import Case2D
    args = dict(solver='native', geometry='axisymmetric', Lx=4.0, Ly=4.0,
                cell_size_m=0.025, charge=1.0, center=(0.0, 2.0),
                obstacles=[(3.0, 3.2, 0.0, 1.5)],
                gauges=[(2.95, 0.5), (2.95, 1.5), (1.5, 0.5), (3.3, 0.5)],
                gauge_file=None, n_snapshots=2, record_frames=0,
                anim_file=None)
    args.update(kw)
    return Case2D(**args)


def snapped(pt, dx):
    """The cell centre the solver snaps `pt` to (within half a cell)."""
    import math
    return tuple((math.floor(v / dx) + 0.5) * dx for v in pt)


def flat_payload(points, n=200, t_end=5e-3):
    """A live payload in the solver's shape (lists, absolute Pa): every
    series at ambient."""
    import numpy as np
    from blastlab.core.constants import P_AIR
    times = list(np.linspace(0.0, t_end, n))
    return dict(times=times, points=[tuple(p) for p in points],
                pressures=[[P_AIR] * n for _ in points])


def rise(n=200, at=120, peak_pa=231e3):
    """An absolute-pressure series: ambient, then a jump to +peak at
    sample `at` and an exponential decay."""
    import numpy as np
    from blastlab.core.constants import P_AIR
    p = np.full(n, P_AIR)
    k = np.arange(n - at)
    p[at:] = P_AIR + peak_pa * np.exp(-k / 15.0)
    return list(p)


def theme_pal(key):
    from blastlab.ui import theme
    return theme.cur(key)


def r5_gauges(win):
    import numpy as np
    from blastlab.core.case import Case2D
    from blastlab.models.result import Result
    from blastlab.output.gauge_summary import summarize_trace
    from blastlab.ui import run_gauges as RG
    from blastlab.ui import scaled_distance as sd
    from blastlab.ui.live_gauges import NO_GAUGES
    rp = win.run_panel
    col = rp.gauge_col
    print('\nR5: the live-gauge column - sorted by Z, waiting, peak so far')
    case = sample_case()
    dx = case.cell_size_m
    pts = [snapped(g, dx) for g in case.gauges]
    check('the payload points are snapped (off the entered ones)',
          all(p != tuple(g) for p, g in zip(pts, case.gauges))
          and all(max(abs(a - b) for a, b in zip(p, g)) <= dx / 2 + 1e-12
                  for p, g in zip(pts, case.gauges)), str(pts))
    pay = flat_payload(pts)
    table = RG.rows(case, pay)
    want_z = {k + 1: sd.scaled_distance(case, g)
              for k, g in enumerate(case.gauges)}
    check('Z of each row is scaled_distance of its ENTERED gauge',
          all(abs(r['z'] - want_z[r['number']]) < 1e-12 for r in table),
          str([(r['number'], round(r['z'], 4)) for r in table]))
    check('G1 3.31, G2 2.99 as Setup shows them',
          RG.fmt_dist(want_z[1]) == '3.31' and RG.fmt_dist(want_z[2])
          == '2.99' and {r['number']: RG.fmt_dist(r['z']) for r in table}
          .get(2) == '2.99', str({r['number']: r['z'] for r in table}))
    zs = [r['z'] for r in table]
    check('the rows are in ascending Z', zs == sorted(zs)
          and [r['number'] for r in table]
          == sorted(want_z, key=lambda k: want_z[k]),
          str([r['number'] for r in table]))
    check('before any rise every row reads waiting',
          all(r['peak_text'] == 'waiting' and r['waiting'] for r in table))
    check('G4 (r 3.30, behind the wall) is named with Wall 1',
          {r['number']: r['where'] for r in table}[4] == 'Wall 1')

    # the column, fed through the panel as the controller does
    rp.set_gauge_case(case)
    rp.set_gauge_payload(pay)
    col.flush()
    pump(20)
    shown = [w.number for w in col.row_widgets()]
    check('the column lists the rows in the same order',
          shown == [r['number'] for r in table], str(shown))
    check('every row widget reads waiting',
          all(w.peak_text() == 'waiting' for w in col.row_widgets()))
    # T9's screenshot: the list showed one row (the scroll area stayed at
    # its minimum), the header clipped to `GAUGI`, and a waiting gauge's
    # flat trace autoranged to +-1e-305 kPa
    win._show('run')
    pump(50)
    check('at %d x %d the list shows all 4 rows (no scrolling needed)'
          % (win.width(), win.height()),
          col.scroll.height() >= 4 * RG.ROW_H
          and col.scroll.verticalScrollBar().maximum() == 0,
          f'{col.scroll.height()} px, bar max '
          f'{col.scroll.verticalScrollBar().maximum()}')
    head = col.list_head.geometry()
    check('the list header sits right on its rows (no floating gap), and '
          'the frame ends at the last row',
          0 <= col.scroll.geometry().top() - head.bottom() <= 2
          and col.list_frame.height() <= RG.LIST_HEAD_H + 4 * RG.ROW_H + 6,
          f'head {head.bottom()} rows {col.scroll.geometry().top()} '
          f'frame {col.list_frame.height()}')
    win.resize(1600, 1000)
    pump(200)
    check('1600 x 1000: the enlarged card keeps its content height (the '
          'spare goes under the list)',
          col.card.height() <= col.card.sizeHint().height() + 1
          and col.list_frame.geometry().top() - col.card.geometry().bottom()
          <= 16, f'card {col.card.height()} hint '
                 f'{col.card.sizeHint().height()}')
    win.resize(1100, 720)
    pump(200)
    # the rendered text width (a fixed-width label's sizeHint reports
    # the fixed width, so it cannot tell)
    check('the list header is not clipped',
          all(lbl.fontMetrics().horizontalAdvance(lbl.text())
              <= lbl.width() for lbl in col.head_lbls[:3]),
          str([(lbl.text(),
                lbl.fontMetrics().horizontalAdvance(lbl.text()),
                lbl.width()) for lbl in col.head_lbls[:3]]))
    lo, hi = col.card.y_range()
    check('a waiting (flat) trace gets a sane 1 kPa axis, not 1e-305',
          lo <= 0.0 and hi - lo >= 1.0, f'{lo:.3g} .. {hi:.3g}')
    check('the header is GAUGE · Z · TRACE · PEAK, the caption sorted by Z',
          col.header_text() == 'GAUGE · Z · TRACE · PEAK'
          and col.sub.text() == '4 gauges, sorted by Z. Click a row to '
          'enlarge it.', f'{col.header_text()!r} {col.sub.text()!r}')

    # a rise at G2 only
    g2 = rise()
    pay2 = dict(pay, pressures=[pay['pressures'][0], g2,
                                pay['pressures'][2], pay['pressures'][3]])
    s2 = summarize_trace(pay2['times'], g2)
    want = f"{s2['peak_kpa']:,.0f} kPa"
    rp.set_gauge_payload(pay2)
    col.flush()
    pump(20)
    got = {w.number: w.peak_text() for w in col.row_widgets()}
    check("after a rise at G2 only, G2 reads summarize_trace's peak",
          got[2] == want and want == '231 kPa', f'{got[2]!r} vs {want!r}')
    check('and the others still read waiting',
          all(got[k] == 'waiting' for k in (1, 3, 4)), str(got))
    check('the sparkline has the trace (decimated, <= 2 points a pixel)',
          0 < col.row_widget(2).spark.n_points() <= 2 * RG.SPARK_W + 1,
          str(col.row_widget(2).spark.n_points()))

    # default selection: no trigger -> the lowest Z; a click enlarges
    check('no trigger gauge: the lowest-Z row is enlarged',
          col.selected_number() == table[0]['number'],
          f'{col.selected_number()} vs {table[0]["number"]}')
    w2 = col.row_widget(2)
    QTest.mouseClick(w2, Qt.LeftButton)
    pump(20)
    num, meta, peak = col.card_texts()
    check('a click on G2 moves the enlarged card to it',
          col.selected_number() == 2 and num == 'G2'
          and meta == f'Z {RG.fmt_dist(want_z[2])} · Wall 1 · selected'
          and peak == f'peak {want}', f'{num} | {meta} | {peak}')
    check('the selected row has the gauge_bg fill',
          theme_pal('gauge_bg') in w2.styleSheet(), w2.styleSheet()[:60])
    rp.set_gauge_payload(pay2)
    col.flush()
    check('and the click persists over the next payload',
          col.selected_number() == 2)
    trig = sample_case(trigger_gauge=4)
    rp.set_running(True)
    rp.set_gauge_case(trig)
    rp.set_gauge_payload(pay2)
    col.flush()
    pump(20)
    check('with a trigger gauge (G4) it is the default enlarged row',
          col.selected_number() == 4 and col.card_texts()[0] == 'G4',
          str(col.selected_number()))
    check('the now line is visible while running', col.now_visible())
    # T9 contrast script: light accent_text on gauge_bg is 4.37:1
    from blastlab.ui import theme as TH
    got = {}
    for mode in ('light', 'dark'):
        TH.apply(app, mode)
        pump(20)
        got[mode] = contrast(col.card.now_line.label.color.name(),
                             TH.cur('gauge_bg'))
    check("the now label reads >= 4.5:1 on gauge_bg in both modes",
          min(got.values()) >= 4.5, str({k: round(v, 2)
                                         for k, v in got.items()}))
    rp.set_running(False)
    pump(20)
    check('and hidden after set_running(False)', not col.now_visible())

    # a dropped gauge: 3 series for 4 entered gauges
    drop = flat_payload([pts[0], pts[2], pts[3]])
    table = RG.rows(case, drop)
    by_no = {r['number']: r for r in table}
    check('a dropped gauge: G1…G3 in payload order',
          sorted(by_no) == [1, 2, 3], str(sorted(by_no)))
    check('each Z belongs to the matched entered gauge (G2 is entered 3)',
          by_no[2]['entered'] == 3
          and abs(by_no[2]['z'] - want_z[3]) < 1e-12
          and abs(by_no[3]['z'] - want_z[4]) < 1e-12,
          str({k: (r['entered'], r['z']) for k, r in by_no.items()}))
    # verify: blastFoam's live 3D payload is `radii` = the probes' x only
    # (solvers/foam/backend._gauges_from_probes); Z must still be the
    # entered gauge's, not x / W^(1/3). Two gauges share x = 1.5.
    from blastlab.core.case import Case3D
    from blastlab.core.constants import P_AIR
    c3 = Case3D(Lx=3.0, Ly=3.0, Lz=3.0, cell_size_m=0.05, charge=2.0,
                center=(0.5, 1.5, 0.5), solver='blastfoam',
                gauges=[(1.5, 1.5, 0.5), (1.5, 2.5, 1.5), (2.5, 1.5, 0.5)])
    foam = dict(times=np.linspace(0.0, 5e-3, 50),
                radii=[g[0] for g in c3.gauges],
                pressures=[np.full(50, P_AIR) for _ in c3.gauges])
    ftab = {r['number']: r for r in RG.rows(c3, foam)}
    check('blastFoam 3D live payload (x only): each row is its entered '
          "gauge, in order, with Setup's Z",
          all(ftab[k]['entered'] == k and abs(
              ftab[k]['z'] - sd.scaled_distance(c3, c3.gauges[k - 1]))
              < 1e-12 for k in (1, 2, 3)),
          str({k: (r['entered'], r['z']) for k, r in ftab.items()}))
    lone = RG.rows(c3, dict(foam, radii=[0.1], pressures=foam['pressures'][:1]))
    check('an x matching no gauge gives no R or Z (not one from x alone)',
          lone[0]['entered'] is None and lone[0]['z'] is None
          and lone[0]['r'] is None, str(lone[0]['z']))
    far = RG.rows(case, flat_payload([(0.5, 3.5)]))
    check('nothing entered within one cell: the payload position is used',
          far[0]['entered'] is None and abs(far[0]['z'] - sd.scaled_distance(
              case, (0.5, 3.5))) < 1e-12, str(far[0]['entered']))

    # planar 2D: R, not Z
    planar = Case2D(geometry='planar', Lx=2.0, Ly=1.2, cell_size_m=0.03,
                    charge=8.0, center=(0.4, 0.0),
                    gauges=[(1.6, 0.2), (1.0, 0.4)], gauge_file=None,
                    n_snapshots=2, record_frames=0, anim_file=None)
    ptab = RG.rows(planar, flat_payload([snapped(g, 0.03)
                                         for g in planar.gauges]))
    rs = [r['r'] for r in ptab]
    check('planar 2D: no Z, rows sorted by R',
          all(r['z'] is None for r in ptab) and rs == sorted(rs)
          and [r['number'] for r in ptab] == [2, 1], str(rs))
    rp.set_gauge_case(planar)
    pump(20)
    check('and the header reads R, the card R … m',
          col.header_text() == 'GAUGE · R · TRACE · PEAK'
          and 'sorted by R' in col.sub.text()
          and col.card_texts()[1].startswith('R ')
          and 'Z' not in col.header_text(), col.header_text())

    # many gauges at 1100 x 720: the list scrolls, nothing leaves the column
    many = sample_case(gauges=[(0.5 + 0.25 * k, 0.5) for k in range(12)])
    rp.set_gauge_case(many)
    pump(50)
    check('12 gauges at 1100 x 720: the list scrolls, the card and the '
          'footnote stay inside the column',
          col.scroll.verticalScrollBar().maximum() > 0
          and col.card.isVisibleTo(col)
          and col.foot.geometry().bottom() <= col.height()
          and col.scroll.height() >= RG.ROW_H,
          f'bar {col.scroll.verticalScrollBar().maximum()} list '
          f'{col.scroll.height()} foot {col.foot.geometry().bottom()} / '
          f'{col.height()}')

    # no gauges
    rp.set_gauge_case(sample_case(gauges=[]))
    pump(20)
    check('no gauges: the column says NO_GAUGES, no card, no list',
          col.empty.isVisibleTo(col) and col.empty.text() == NO_GAUGES
          and col.card.isHidden() and col.list_frame.isHidden())

    # the collection rule (decision D60)
    win._show('run')
    rp.show_slice_tab()
    pump(20)
    check('Run screen current: collecting (the column is on screen)',
          win.ctrl._live_gauges is True)
    win._show('setup')
    pump(20)
    check('Setup current, slice selected: not collecting',
          win.ctrl._live_gauges is False)
    rp.show_gauges_tab()
    pump(20)
    check('Setup current, Gauges selected: collecting (G3 as written)',
          win.ctrl._live_gauges is True)
    rp.show_slice_tab()
    pump(20)
    check('and off again when the segment goes back',
          win.ctrl._live_gauges is False)
    win._show('run')
    # D69 (the plan's fallback after T9's R-COST): the column must be
    # visible - a minimised window does not collect
    win.showMinimized()
    pump(50)
    off = win.ctrl._live_gauges
    win.showNormal()
    pump(50)
    check('minimised: not collecting; restored: collecting again (D69)',
          off is False and win.ctrl._live_gauges is True,
          f'{off} {win.ctrl._live_gauges}')

    # a refresh that changes no row's state re-styles nothing (T9 R-COST:
    # re-polishing every row on every refresh was most of the cost)
    rp.set_gauge_case(case)
    rp.set_gauge_payload(pay2)
    col.flush()
    pump(RG.REFRESH_MS + 50)
    styled = []
    widgets = [col.card, col.card.peak] + [
        x for w in col.row_widgets() for x in (w, w.num, w.dist, w.peak)]
    real = {id(w): w.setStyleSheet for w in widgets}
    for w in widgets:
        w.setStyleSheet = (lambda s, _w=w: styled.append(_w)
                           or real[id(_w)](s))
    try:
        rp.set_gauge_payload(dict(pay2))
        col.flush()
        pump(RG.REFRESH_MS + 50)
    finally:
        for w in widgets:
            del w.setStyleSheet
    check('a same-state refresh re-styles no widget (only texts and data)',
          styled == [] and RG.REFRESH_MS == 500, f'{len(styled)} restyled')

    # the hidden Gauges page is fed on demand, with the newest payload
    rp.set_gauge_payload(pay2)
    check('the Gauges page is not redrawn while hidden (it is owed)',
          rp._pending_gauges is pay2)
    rp.show_gauges_tab()
    pump(20)
    check('and gets the newest payload when shown',
          rp._pending_gauges is None
          and rp.gauges.n_points() == len(pay2['times']))
    rp.show_slice_tab()

    # the last stage's full traces arrive with on_result during a run
    import test_gui_results_fields as F
    res = F.fake_2d()
    full = dict(times=np.asarray(pay2['times']),
                points=[tuple(p) for p in pts],
                pressures=[np.asarray(x) for x in pay2['pressures']])
    res = Result(res.snapshots, full, res.meta, 'end time reached', False)
    win._run_cases = [case]
    win.ctrl._stage_dims = [2]
    try:
        win.on_running(True)
        check("a run start lists the run case's gauges, all waiting",
              col.case() is case and not col.has_data()
              and all(r['waiting'] for r in col.table()))
        win.on_result(0, 2, 'R5 - 2D', res)
        win.on_running(False)
        pump(20)
        got = {r['number']: r['peak_text'] for r in col.table()}
        check("the last stage's Result.gauges fill the column",
              col.has_data() and got[2] == want, str(got))
        check('the finished column has no now line', not col.now_visible())
    finally:
        win.ctrl._stage_dims = []
    win.on_finished(False, False)
    before = col.table()
    win.on_result(0, 2, 'R5 again - 2D', F.fake_2d())
    check('an on_result outside a run (tests feed them) changes nothing',
          [r['peak_text'] for r in col.table()]
          == [r['peak_text'] for r in before])


def r6_finish(win):
    from types import SimpleNamespace
    from blastlab.models.result import Result
    from blastlab.output.gauge_summary import summarize_gauges
    from blastlab.ui import dialogs
    from blastlab.ui.run_clock import fmt_duration
    import numpy as np
    import test_gui_results_fields as F
    rp = win.run_panel
    print('\nR6: the end of a run - banner, notification, Done')
    calls = []
    real_notify = dialogs.notify_desktop

    def rec(title, text, on_click=None, parent=None):
        calls.append(dict(title=title, text=text, on_click=on_click))
        return True

    fake = FakeClock()
    clock = win._run_clock
    real_now = clock.now
    runs = tempfile.mkdtemp(prefix='blastlab_runs_r6_')
    folder = os.path.join(runs, 'wall_A')
    saved = (win.ctrl._run_name, win.ctrl._model, win.ctrl._stage_dims,
             win._run_cases)
    base = F.fake_2d()
    t = np.linspace(0.0, 8e-3, 400)

    def result(peaks, reason='shock arrived at a terminate boundary (x_hi)',
               early=False):
        pts = [(1.0 + k, 0.5) for k in range(len(peaks))]
        pres = [np.asarray(rise(400, at, pk)) for at, pk in peaks]
        g = dict(times=t, points=pts, pressures=pres)
        return Result(base.snapshots, g, base.meta, reason, early)

    def fake_run(res, stopped=False, errored=False, end_at=331.0):
        fake.t = 0.0
        win.on_running(True)
        if res is not None:
            win.on_result(0, 2, 'wall_A - 2D', res)
        fake.t = end_at
        win.on_running(False)
        win.on_finished(stopped, errored)
        pump(20)

    dialogs.notify_desktop = rec
    clock.now = fake
    try:
        win.ctrl._run_name = 'wall_A'
        win.ctrl._model = SimpleNamespace(folder=folder)
        win.ctrl._stage_dims = [2]
        win._run_cases = [sample_case()]
        win._show('run')

        res = result([(250, 120e3), (180, 296e3), (300, 80e3)])
        fake_run(res)
        want = (f'Result ready: wall_A · {res.stop_reason}. Files in '
                f'{folder}{os.sep}')
        check('ended on its own: the banner is shown with the stop reason '
              'verbatim and the model folder',
              rp.banner.isVisibleTo(rp) and rp.banner_text() == want,
              repr(rp.banner_text()))
        # T9's screenshots: a word-wrapped path was clipped at 1100 x 720
        # and held the centre wide, narrowing both side columns
        win.resize(1100, 720)
        pump(150)
        msg = rp.banner.message
        fm = msg.fontMetrics()
        lines = msg.text().split('\n')
        check('1100 x 720: the banner is two unwrapped lines that fit, the '
              'whole text in the tooltip',
              len(lines) == 2 and lines[1].startswith('Files in ')
              and all(fm.horizontalAdvance(ln) <= msg.contentsRect().width()
                      for ln in lines)
              and msg.toolTip() == want, repr(lines))
        check('and the side columns keep 280 / 340 with the banner up',
              rp.column_widths()[0] == 280 and rp.column_widths()[2] == 340,
              str(rp.column_widths()))
        win.resize(1600, 1000)
        pump(150)
        check('1600 x 1000: the first line is whole',
              msg.text().split('\n')[0]
              == f'Result ready: wall_A · {res.stop_reason}.',
              repr(msg.text()))
        rows = summarize_gauges(res.gauges)
        k = max(range(len(rows)), key=lambda i: rows[i]['peak_kpa'])
        text = (f'wall_A finished in {fmt_duration(331.0)}. Highest peak: '
                f'G{k + 1}, {rows[k]["peak_kpa"]:,.0f} kPa at '
                f'{rows[k]["t_peak_ms"]:.2f} ms.')
        check('one notification: the run time and summarize_gauges\'s '
              'highest peak',
              len(calls) == 1 and calls[0]['title'] == 'BlastLab'
              and calls[0]['text'] == text and 'G2, 296 kPa' in text,
              repr(calls[0]['text'] if calls else None))
        check('the title starts with `✓ Done · `',
              win.windowTitle().startswith('✓ Done · '), win.windowTitle())
        check('the time line appends how it ended',
              rp.time_text() == f'Done in {fmt_duration(331.0)} · '
              f'{res.stop_reason}', rp.time_text())
        check('the idle button reads Run again',
              rp.run_btn.text() == 'Run again' and rp.run_btn.isVisibleTo(rp))
        rp.banner.action.click()
        pump(30)
        sel = win.results.sel
        check('Open in 03 Results → shows Results, the newest selected',
              win.current_tab() == 'results'
              and sel.currentIndex() == sel.count() - 1, str(sel.count()))
        n_before = len(calls)
        calls[0]['on_click']()
        pump(30)
        check('a click on the notification raises the window on Results',
              win.current_tab() == 'results' and len(calls) == n_before)
        win._show('run')

        # the next start clears the banner and the Done mark
        fake.t = 0.0
        win.on_running(True)
        pump(20)
        check('the next start hides the banner and clears ✓ Done',
              rp.banner.isHidden() and rp.banner_text() == ''
              and not win.windowTitle().startswith('✓'),
              win.windowTitle())
        win.on_running(False)
        win.on_finished(False, False)

        # stopped by the user: the banner, nothing else
        calls.clear()
        stopped = result([(180, 296e3)], 'stopped by user', early=True)
        fake_run(stopped, stopped=True, end_at=62.0)
        check('stopped: the banner, reading `· stopped by user.`',
              rp.banner.isVisibleTo(rp)
              and ' · stopped by user. Files in ' in rp.banner_text()
              and rp.time_text().endswith('stopped by user'),
              f'{rp.banner_text()!r} {rp.time_text()!r}')
        check('stopped: no notification and no ✓ Done',
              calls == [] and not win.windowTitle().startswith('✓'),
              f'{len(calls)} {win.windowTitle()}')

        # errored: nothing (the error dialog path is unchanged)
        fake_run(result([(180, 296e3)]), errored=True)
        check('errored: no banner and no notification',
              rp.banner.isHidden() and calls == []
              and rp.time_text().startswith('Failed after'),
              rp.time_text())

        # no result at all (StoppedBeforeStart): nothing
        fake_run(None)
        check('no result: no banner, no notification',
              rp.banner.isHidden() and calls == [])

        # no gauges: the sentence is left out
        fake_run(result([]))
        check('no gauges: the notification has no Highest peak',
              len(calls) == 1 and calls[0]['text']
              == f'wall_A finished in {fmt_duration(331.0)}.',
              repr(calls[0]['text'] if calls else None))
    finally:
        dialogs.notify_desktop = real_notify
        clock.now = real_now
        (win.ctrl._run_name, win.ctrl._model, win.ctrl._stage_dims,
         win._run_cases) = saved

    from PySide6.QtWidgets import QSystemTrayIcon
    avail = QSystemTrayIcon.isSystemTrayAvailable()
    got = dialogs.notify_desktop('BlastLab', 'x')
    check('offscreen (no system tray) notify_desktop does nothing',
          avail or (got is False and dialogs._tray is None),
          f'{avail} {got}')


def r7_chain_hook(win):
    from PySide6.QtWidgets import QLabel
    from blastlab.solvers.hooks import Progress
    rp = win.run_panel
    print('\nR7: the chain hook')
    win._show('run')
    win.resize(1600, 1000)
    saved = (win.ctrl._stage_dims, win._run_cases)
    try:
        win.ctrl._stage_dims = [2]
        win.on_running(True)
        pump(50)
        check('a single run leaves chain_slot hidden, height 0',
              rp.chain_slot.isHidden() and rp.chain_slot.height() == 0
              and rp.chain_strip() is None, str(rp.chain_slot.height()))
        win.on_running(False)
        lbl = QLabel('CHAIN · wall_A · 01 1D ✓ 9 s → 02 2D 78 %')
        rp.set_chain_strip(lbl)
        pump(50)
        check('set_chain_strip(widget) shows it above the progress strip',
              rp.chain_slot.isVisibleTo(rp) and rp.chain_strip() is lbl
              and lbl.isVisibleTo(rp) and rp.chain_slot.height() > 0
              and rp.chain_slot.geometry().bottom()
              < rp.strip.geometry().top(),
              f'{rp.chain_slot.geometry()} {rp.strip.geometry()}')
        rp.set_chain_strip(None)
        pump(50)
        check('set_chain_strip(None) empties and hides it again (height 0)',
              rp.chain_slot.isHidden() and rp.chain_slot.height() == 0
              and rp.chain_strip() is None and lbl.parent() is None,
              str(rp.chain_slot.height()))
        # the title of a 3-stage chain, stage 2 at 78 % (F6's format)
        win.ctrl._stage_dims = [1, 2, 3]
        win.on_running(True)
        win._chain_k = 2
        win.on_progress(Progress(step=1, t=1e-4, dt=1e-7, p_max=2e5,
                                 frac=0.78))
        check('a 3-stage chain still titles `Chain 2/3 · 78 % · …`',
              win.windowTitle().startswith('Chain 2/3 · 78 % · '),
              win.windowTitle())
        win.on_running(False)
    finally:
        win.ctrl._stage_dims, win._run_cases = saved


def r8_banner_viewer(win):
    """T9's Win32 sampler found the embedded viewer 70 px taller than its
    card for ~30 ms whenever the banner appeared above it; show_finish
    now shrinks the window first (View3DHost.shrink_ahead). The geometry
    itself is measured on the real platform (measurements-6b.md); here,
    that the call is made, with the right height, only when it applies."""
    from blastlab.ui.theme import GAP
    rp = win.run_panel
    host = rp.view3d
    print('\nR8: the banner shrinks the embedded viewer first')
    calls = []
    real = host.shrink_ahead
    host.shrink_ahead = calls.append
    win.resize(1600, 1000)
    win._show('run')
    try:
        rp.banner.hide()
        rp.show_3d_tab()
        pump(50)
        rp.show_finish('m', 'end time reached', None)
        pump(50)
        want = rp.banner.height() + GAP     # what the layout gave it
        check('3D view on screen: show_finish shrinks the viewer by the '
              "banner's height + GAP, before the banner shows",
              len(calls) == 1 and abs(calls[0] - want) <= 2
              and rp.banner.isVisibleTo(rp), f'{calls} vs {want}')
        calls.clear()
        rp.show_finish('m', 'end time reached', None)
        check('a banner already shown does not shrink it again',
              calls == [])
        rp.banner.hide()
        rp.show_slice_tab()
        pump(20)
        rp.show_finish('m', 'end time reached', None)
        check('the live slice on screen: no call', calls == [])
    finally:
        host.shrink_ahead = real
        rp.banner.hide()
        rp.show_slice_tab()
    try:
        host.shrink_ahead(70)
        ok = True
    except Exception as exc:        # noqa: BLE001 - reported
        ok = exc
    check('shrink_ahead is a no-op without a native window (offscreen)',
          ok is True, str(ok))


def r9_copy_path(win):
    """GUI-10 (F23, D181): the resolved-folder line wraps after each
    separator with a zero-width space, but what is copied is the path:
    Ctrl+C and the context menu's Copy strip U+200B; the text shown is
    unchanged and no QShortcut is added."""
    from PySide6.QtGui import QShortcut
    from PySide6.QtWidgets import QApplication
    from blastlab.ui import run_panel as RP
    from blastlab.ui.widgets import ZWSP
    print('\nR9: copying the wrapped model-folder path (F23)')
    rp = win.run_panel
    deep = tempfile.mkdtemp(prefix='blastlab_r9_')
    runs = os.path.join(deep, 'a very long runs folder', 'second level',
                        'third level of the runs folder')
    os.makedirs(runs, exist_ok=True)
    n_short = len(win.findChildren(QShortcut))
    rp.set_runs_dir(runs)
    rp.run_name.setText('A_LONG_MODEL_NAME_FOR_THE_COPY_TEST')
    pump(RP.PATH_DEBOUNCE_MS + 150)
    lbl = rp._path_lbl
    want = rp.path_text()
    check('the label shows the path with a ZWSP after each separator',
          lbl.text() == want.replace(os.sep, os.sep + ZWSP)
          and ZWSP in lbl.text(), repr(lbl.text()[:60]))
    clip = QApplication.clipboard()
    clip.setText('before')
    lbl.setSelection(0, len(lbl.text()))
    QTest.keyClick(lbl, Qt.Key_C, Qt.ControlModifier)
    pump(20)
    got = clip.text()
    check('select all + Ctrl+C copies path_text() exactly, no U+200B',
          got == want and ZWSP not in got, repr(got[:60]))
    clip.setText('before')
    menu = lbl._clean_copy.menu()
    names = [a.text() for a in menu.actions() if a.text()]
    check('the context menu holds Copy and Select all',
          names == ['Copy', 'Select all'], str(names))
    next(a for a in menu.actions() if a.text() == 'Copy').trigger()
    got = clip.text()
    check("the context menu's Copy gives the same text",
          got == want, repr(got[:60]))
    menu.deleteLater()
    lbl.setSelection(0, 0)
    clip.setText('before')
    menu = lbl._clean_copy.menu()
    copy = next(a for a in menu.actions() if a.text() == 'Copy')
    check('with nothing selected the menu\'s Copy is disabled',
          not copy.isEnabled())
    next(a for a in menu.actions() if a.text() == 'Select all').trigger()
    menu.deleteLater()
    menu = lbl._clean_copy.menu()
    next(a for a in menu.actions() if a.text() == 'Copy').trigger()
    check('Select all, then Copy, copies the whole path',
          clip.text() == want, repr(clip.text()[:60]))
    menu.deleteLater()
    check('the label is still a custom-menu, mouse-selectable label',
          lbl.contextMenuPolicy() == Qt.CustomContextMenu
          and bool(lbl.textInteractionFlags() & Qt.TextSelectableByMouse))
    check('no QShortcut was added (test_ui_frame F5 pins five)',
          len(win.findChildren(QShortcut)) == n_short,
          f'{n_short} -> {len(win.findChildren(QShortcut))}')
    use_model(win, 'R1')
    pump(RP.PATH_DEBOUNCE_MS + 150)


def r10_pmax_fit(win):
    """GUI-10 (F34): at 1100 x 720 a scientific P MAX (`2.799e+06 kPa`,
    any p max from 10 MPa on) lost its unit in the 115 px tile. The
    strip's tiles step their value face down until the readout fits; a
    short value stays at 21 px, and the tile's height does not change."""
    from PySide6.QtGui import QFont, QTextDocument
    print('\nR10: a long P MAX keeps its unit at 1100 x 720 (F34)')
    rp = win.run_panel
    size = (win.width(), win.height())
    win._show('run')
    win.resize(1100, 720)
    pump(250)

    def readout(pmax):
        rp._readout.update({'t [ms]': '1.828', 'step': '1355',
                            'dt [s]': '1.93e-06', 'p max [kPa]': pmax})
        rp._render_readouts()
        pump(150)
        lbl = rp._tile_pmax.value
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(QFont(lbl.font()))
        doc.setHtml(lbl.text())
        return (lbl.font().pixelSize(), doc.idealWidth(), lbl.width(),
                rp._tile_pmax.height(), lbl.text())

    px0, need0, has0, h0, _t = readout('345.7')
    check('a short P MAX stays at 21 px and fits',
          px0 == 21 and need0 <= has0, f'{px0} px, {need0:.0f} in {has0}')
    px, need, has, h, text = readout('2.799e+06')
    check('2.799e+06 kPa fits its tile, unit included',
          need <= has and 'kPa' in text, f'{px} px, {need:.0f} in {has}')
    check('by a smaller face, not a taller tile',
          px < 21 and h == h0, f'{px} px, height {h0} -> {h}')
    check('the readout string is unchanged (U4)',
          rp.chip_texts()['p max [kPa]'] == '2.799e+06',
          rp.chip_texts()['p max [kPa]'])
    px1, _n, _h, _hh, _t = readout('345.7')
    check('and back to 21 px for a short value', px1 == 21, f'{px1} px')
    rp._reset_readouts_text()
    win.resize(*size)
    pump(200)


def r11_hd13_flow(win):
    """GUI-11 T5 (UXR-8 + F12 + QA S3-3, D206): the 0-D run flow, with
    `assessment.run` blocked on an Event. Run on 0-D goes to 02 Run;
    Setup's Run F5 and Run chain grey while it works; the toolbar and
    the view hide behind one note; the last run's banner goes; F5 while
    busy says why; after it the tile reads `—` and Run F5 is back."""
    import threading
    import time
    import char_common as cc
    from PySide6.QtGui import QShortcut
    from blastlab.core import assessment
    from blastlab.ui.run_panel import HD13_NOTE
    print('\nR11: the 0-D run flow (GUI-11 T5, F12)')
    rp = win.run_panel
    gate = threading.Event()
    real_run = assessment.run

    def blocked(case):
        gate.wait(60)
        raise RuntimeError('released by the test')
    errors = []
    assessment.run = blocked
    win.show_error = lambda t, m: errors.append((t, m))
    try:
        win._show('setup')
        win.setup.set_dim(0)
        pump(100)
        win.setup.forms[0].set_case(cc.hd13_starter_case())
        use_model(win, 'GUI11_HD13')
        pump(400)
        check('0-D: the toolbar row and the view are hidden, the note shown',
              not rp._view_bar.isVisibleTo(rp)
              and not rp._view_frame.isVisibleTo(rp)
              and rp.hd13_note.isVisibleTo(rp)
              and rp.hd13_note.text() == HD13_NOTE)
        rp.show_finish('PREVIOUS', 'finished', None)
        rp.strip.pct_lbl.setText('100 %')
        check('(a previous run left its banner and its percent)',
              not rp.banner.isHidden() and rp.pct_text() == '100 %')
        win._run_single()
        pump(100)
        check('after Run on 0-D the window is on 02 Run',
              win._hd13_busy and win.current_tab() == 'run',
              f'busy={win._hd13_busy} tab={win.current_tab()}')
        check("Setup's Run F5 and Initialise are disabled while busy",
              not win.setup.strip.run_btn.isEnabled()
              and not win.setup.strip.init_btn.isEnabled())
        check('Run chain is disabled while busy',
              not win.chain.run_btn.isEnabled())
        check('the toolbar row and runview hidden, the note visible',
              not rp._view_bar.isVisibleTo(rp)
              and not rp._view_frame.isVisibleTo(rp)
              and rp.hd13_note.isVisibleTo(rp))
        check("the previous run's finish banner is hidden",
              rp.banner.isHidden())
        win._validate()             # a live check meanwhile keeps the grey
        pump(50)
        check('a validation while busy keeps Run F5 grey',
              not win.setup.strip.run_btn.isEnabled())
        f5 = [sc for sc in win.findChildren(QShortcut)
              if sc.key().toString() == 'F5']
        f5[0].activated.emit()
        pump(20)
        check('F5 while busy says so on the status line',
              win._status.text() == 'An HD 1.3 assessment is running.',
              repr(win._status.text()))
        gate.set()
        t0 = time.monotonic()
        while win._hd13_busy and time.monotonic() - t0 < 60:
            pump(50)
        pump(100)
        check('after release the progress tile reads —',
              not win._hd13_busy and rp.pct_text() == '—',
              repr(rp.pct_text()))
        check('Run F5 and Run chain are enabled again',
              win.setup.strip.run_btn.isEnabled()
              and win.chain.run_btn.isEnabled())
        check('(the blocked run ended in its error dialog)',
              errors and errors[-1][0] == 'HD 1.3 assessment', str(errors))
    finally:
        gate.set()
        assessment.run = real_run
        del win.show_error
        win.setup.set_dim(2)
        pump(150)
    check('back on 2D the toolbar and the view are visible, no note',
          rp._view_bar.isVisibleTo(rp) and rp._view_frame.isVisibleTo(rp)
          and not rp.hd13_note.isVisibleTo(rp))


def r5b_dropped(win):
    """UXR-2 / D201 (GUI-11 T8): G2 entered inside Wall 1 is dropped by
    the solver; the live column labels the two series G1 and G3 (as
    entered) and its caption names G2. The row keys stay D61's payload
    numbers."""
    from blastlab.ui import run_gauges as RG
    rp = win.run_panel
    col = rp.gauge_col
    print('\nR5b: a gauge the solver dropped (inside Wall 1)')
    case = sample_case(gauges=[(2.95, 0.5), (3.1, 0.5), (2.95, 1.5)])
    dx = case.cell_size_m
    rp.set_gauge_case(case)
    pump(20)
    check('before a payload: G1 G2 G3 by Z, no note',
          sorted(col.row_labels()) == ['G1', 'G2', 'G3']
          and 'dropped' not in col.caption_text(),
          f'{col.row_labels()} {col.caption_text()!r}')
    pay = flat_payload([snapped(case.gauges[0], dx),
                        snapped(case.gauges[2], dx)])
    col.set_payload(pay, final=True)
    col.flush()
    pump(20)
    check('two rows, labelled G3 (Z 2.99) then G1 (Z 3.31)',
          col.row_labels() == ['G3', 'G1'], str(col.row_labels()))
    check('the keys are still the payload numbers (D61)',
          [w.number for w in col.row_widgets()] == [2, 1]
          and [r['entered'] for r in col.table()] == [3, 1],
          str([(r['number'], r['entered']) for r in col.table()]))
    check('the caption names G2 and the wall',
          col.caption_text() == '2 gauges, sorted by Z. Click a row to '
          'enlarge it. G2 dropped by the solver (inside Wall 1).',
          col.caption_text())
    check('the enlarged card says G3', col.card_texts()[0] == 'G3',
          str(col.card_texts()))
    labels, dropped = RG.numbering(case, pay)
    check('numbering(): G1, G3 and G2 inside Wall 1',
          labels == ['G1', 'G3'] and dropped == [(2, 'inside Wall 1')],
          f'{labels} {dropped}')
    full = sample_case()
    pay4 = flat_payload([snapped(g, full.cell_size_m) for g in full.gauges])
    rp.set_gauge_case(full)
    col.set_payload(pay4, final=True)
    col.flush()
    pump(20)
    check('nothing dropped: each label is G<payload number>, no note',
          all(w.num.text() == f'G{w.number}' for w in col.row_widgets())
          and 'dropped' not in col.caption_text(),
          f'{col.row_labels()} {col.caption_text()!r}')


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
        r4_dock(win)
        r5_gauges(win)
        r5b_dropped(win)
        r6_finish(win)
        r7_chain_hook(win)
        r8_banner_viewer(win)
        r9_copy_path(win)
        r10_pmax_fit(win)
        r11_hd13_flow(win)
    finally:
        check('nothing raised', not crashes, str(crashes[:1]))
        # the recorder above is for Qt slots only: an exception out of a
        # check function must still print its traceback (it used to exit
        # 1 with no word of where)
        sys.excepthook = sys.__excepthook__
        # a notification's tray icon left over is removed at close
        from PySide6.QtWidgets import QSystemTrayIcon
        from blastlab.ui import dialogs
        dialogs._tray = QSystemTrayIcon()
        win.close()
        pump(100)
        check('closeEvent leaves no tray icon (R6)', dialogs._tray is None)
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
