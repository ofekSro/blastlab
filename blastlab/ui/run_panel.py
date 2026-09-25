"""Run tab: start/stop controls, progress readouts, stepped execution,
the scrolled log and the live view (2D slice in pyqtgraph | the 3D
viewer host). A port of gui/run_panel.py; the controller feeds it
through the same on_* methods."""

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QProgressBar,
                               QSplitter, QStackedWidget, QVBoxLayout,
                               QWidget)

from ..core import refine
from . import theme
from .live_gauges import NO_GAUGES, WAITING, LiveGaugePane
from .pg_plots import MESH_MAX_LINES, LiveSlicePane
from .theme import GAP, PAD
from .widgets import (Card, Chip, Segmented, WrapRow, button, hbox, label,
                      set_button_kind)


class RunPanel(QWidget):
    run_requested = Signal()
    stop_requested = Signal()
    view3d_requested = Signal()
    init_requested = Signal()
    exec_requested = Signal(object)      # 1/10/100/1000 | 'run' | 'pause'
    refresh_changed = Signal()
    #: the live gauge view was opened or left; the solver only collects
    #: traces while something is watching
    gauges_wanted = Signal(bool)

    #: share of the Run-tab width given to the log; the live/3D pane
    #: keeps the rest (>= 60 %, the QA-17 target)
    LOG_FRAC = 0.34
    LOG_MIN = 240
    VIEW_MIN = 420

    #: a dynamic-AMR run logs one of these per written time - 60+ lines
    #: for half a millisecond of simulation, which buried every other
    #: message. They are collapsed HERE rather than in the solver: the
    #: text itself is the e2e drivers' instrumentation (cells per write)
    #: and must keep reaching stdout and the transcript unchanged.
    _AMR_MARK = '[blastfoam] AMR t = '

    def __init__(self, view3d_host=None, parent=None):
        super().__init__(parent)
        self.view3d = view3d_host
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(PAD - 4)
        root.addWidget(label('Run', 'h1'))

        # ── control card ─────────────────────────────────────────────────
        ctl = Card()
        root.addWidget(ctl)
        bar = hbox()
        ctl.add_layout(bar)
        self.run_btn = button('Run', 'play', 'primary', width=110, height=38,
                              on_click=self.run_requested.emit)
        self.stop_btn = button('Stop', 'stop', 'default', width=100,
                               height=38, on_click=self.stop_requested.emit)
        self.stop_btn.setEnabled(False)
        self.view3d_btn = button('3D View', 'cube', 'default', width=110,
                                 height=38,
                                 on_click=self.view3d_requested.emit)
        self.view3d_btn.setEnabled(False)
        for b in (self.run_btn, self.stop_btn, self.view3d_btn):
            bar.addWidget(b)
        bar.addSpacing(PAD - GAP)
        # results used to be labelled by dim + a counter only, so three
        # runs of different cases read "Run 1 - 2D", "Run 2 - 2D" ... (N9)
        bar.addWidget(label('Name', 'muted'))
        self.run_name = QLineEdit()
        self.run_name.setFixedWidth(130)
        self.run_name.setToolTip('Names this run in the Results picker and '
                                 'in the exported file names; blank falls '
                                 'back to "Run N - 2D".')
        bar.addWidget(self.run_name)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMinimumWidth(120)
        self.progress.setFixedHeight(8)
        # takes the slack so the readouts on the right keep their width
        bar.addWidget(self.progress, 1)
        # stepped execution used to be visible only as a "[interrupted]"
        # line in the log; say it where the run state is read
        self._paused_lbl = label('', 'small')
        self._paused_lbl.setStyleSheet(f'color: {theme.cur("warn")};')
        bar.addWidget(self._paused_lbl)
        # the Setup strip is on another tab, so the Run tab used to give
        # no hint that the case was invalid until a modal appeared
        self._valid_lbl = label('', 'small')
        bar.addWidget(self._valid_lbl)
        bar.addSpacing(PAD - GAP)
        self._chip_step = Chip('step')
        self._chip_t = Chip('t [ms]')
        self._chip_dt = Chip('dt [s]')
        # kPa like every plot and colorbar (the chip used to be the one
        # readout in Pa, a 1000x mismatch against the live view beside it)
        self._chip_pmax = Chip('p max [kPa]')
        # dynamic AMR moves the cell count every write; it was only ever
        # visible as a log line (QA-32). Shown on the first frame that
        # carries a level map, so a static run keeps its four chips.
        self._chip_cells = Chip('cells')
        self._chip_cells.setToolTip('Cells of the dynamic (AMR) mesh on the '
                                    'live plane - a 3D run counts the slice, '
                                    'not the whole mesh.')
        self._chip_cells.hide()
        # the chips share this row with Run / Stop / 3D View / Name /
        # validation, and at 1100 px there is not enough for all of it:
        # 'p max [kPa]' came out 20 px short of its own caption. Let the
        # chips wrap rather than squeeze.
        self.chip_row = WrapRow()
        for chip in (self._chip_step, self._chip_t, self._chip_dt,
                     self._chip_pmax):
            self.chip_row.add(chip)
        # the AMR chip stays hidden until a frame carries a level map
        self.chip_row.add(self._chip_cells, hidden=True)
        bar.addWidget(self.chip_row, 1)

        # ── stepped execution row (VIPER-style) ──────────────────────────
        ebar = hbox()
        ctl.add_layout(ebar)
        # no fixed widths, and a row that wraps: 'Exec 1000' does not fit
        # 72 px and 'Interrupt' does not fit 88 with its icon, so these
        # read 'ec 100' and 'Interrup' on screen. Same defect as the
        # Results export row (N2-10); same cure.
        self.exec_row = WrapRow()
        self.init_btn = self.exec_row.add(
            button('Initialise Model', 'flag', height=32,
                   on_click=self.init_requested.emit))
        self._exec_btns = []

        def exec_btn(text, cmd, icon=None):
            b = self.exec_row.add(
                button(text, icon, height=32,
                       on_click=lambda c=cmd: self.exec_requested.emit(c)))
            b.setEnabled(False)
            self._exec_btns.append(b)
            return b

        for n in (1, 10, 100, 1000):
            exec_btn(f'Exec {n}', n)
        exec_btn('END', 'run', icon='end')
        exec_btn('Interrupt', 'pause', icon='pause')
        ebar.addWidget(self.exec_row, 1)
        # live-view refresh rate (2D slice + 3D view); blank = automatic
        ebar.addWidget(label('Refresh every', 'muted'))
        self.refresh_val = QLineEdit()
        self.refresh_val.setFixedWidth(64)
        self.refresh_val.setToolTip('How often the live view redraws; '
                                    'leave blank (or 0) for automatic.')
        self.refresh_val.editingFinished.connect(self.refresh_changed.emit)
        ebar.addWidget(self.refresh_val)
        self.refresh_mode = QComboBox()
        self.refresh_mode.addItems(['seconds', 'steps'])
        self.refresh_mode.setFixedWidth(104)
        self.refresh_mode.currentTextChanged.connect(
            lambda _t: self.refresh_changed.emit())
        ebar.addWidget(self.refresh_mode)

        # ── body: log | live view ────────────────────────────────────────
        self._body = QSplitter(Qt.Horizontal)
        self._body.setChildrenCollapsible(False)
        root.addWidget(self._body, 1)
        logcard = Card('Log', pad=12)
        logcard.setMinimumWidth(self.LOG_MIN)
        self.log = QPlainTextEdit()
        self.log.setObjectName('log')
        self.log.setReadOnly(True)
        self.log.setFont(theme.font('mono'))
        self.log.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.log.setMaximumBlockCount(50000)
        logcard.add(self.log, 1)
        self._body.addWidget(logcard)

        right = Card(pad=12)
        right.setMinimumWidth(self.VIEW_MIN)
        # this row carries the view switch, Show mesh and the whole
        # Min/Max colour range, which does not fit the live-view card at
        # 1100 px: 'Show mesh' came out 5 px short of its own caption.
        # WrapRow breaks it instead of squeezing, and each caption stays
        # glued to its field.
        self.view_row = WrapRow()
        right.add(self.view_row)
        self._view_seg = Segmented(['Live slice', 'Gauges', '3D view'])
        self._view_seg.setFixedWidth(300)
        self._view_seg.changed.connect(self._view_selected)
        self.view_row.add(self._view_seg)
        # cell edges over the live slice (true cells of a refined run)
        self.show_mesh = QCheckBox('Show mesh')
        self.show_mesh.toggled.connect(lambda _c: self._rebuild_overlay())
        self.view_row.add(self.show_mesh)
        # manual colour range for the 2D live pane, mirroring the 3D
        # viewer's Min/Max: a late weak frame used to rescale the whole
        # picture, so nothing could be compared across a run (G7)
        self.auto_clim = QCheckBox('Auto')
        self.auto_clim.setChecked(True)
        self.auto_clim.toggled.connect(lambda _c: self._clim_changed())
        self.view_row.add(self.auto_clim)
        self.clim_min = QLineEdit('0')
        self.clim_max = QLineEdit('')
        self._clim_entries = [self.clim_min, self.clim_max]
        for lbl, ent, tail in (('Min', self.clim_min, None),
                               ('Max', self.clim_max, 'kPa')):
            ent.setFixedWidth(64)
            ent.setFont(theme.font('small'))
            ent.editingFinished.connect(self._clim_changed)
            pair = QWidget()
            pl = hbox(pair)
            pl.addWidget(label(lbl, 'small'))
            pl.addWidget(ent)
            if tail:
                pl.addWidget(label(tail, 'small'))
            self.view_row.add(pair)
        self._sync_clim_state()
        self._stack = QStackedWidget()
        right.add(self._stack, 1)
        self.pane = LiveSlicePane()
        self._stack.addWidget(self.pane)
        self.gauges = LiveGaugePane()
        self._stack.addWidget(self.gauges)
        if self.view3d is None:
            self.view3d = _NoViewer()
        self._stack.addWidget(self.view3d)
        self._view_seg.set('Live slice')
        self._stack.setCurrentWidget(self.pane)
        self._body.addWidget(right)
        self._body.setStretchFactor(0, 34)
        self._body.setStretchFactor(1, 66)
        self._set_tab_order()
        self._sash_user = False
        self._sash_placed = False
        self._body.splitterMoved.connect(lambda *_: setattr(
            self, '_sash_user', True))

        self._solid = None
        self._mesh_geom = None      # (x_face, y_face, mesh_src) of the run
        self._mesh_levels = None
        self._disp_level = None
        self._last_step = None      # newest step, for the PAUSED readout
        self._amr_run = 0           # consecutive AMR log lines collapsed
        self._cadence = 0.0         # foam: seconds between live frames
        self._cadence_steps = 0     # foam: solver steps between live frames
        self._last_dt = 0.0         # newest solver time step [s]
        self._last_field = None     # newest 2D frame, for a clim redraw
        self._running = False
        self._busy = False          # a non-solve job (HD 1.3) is working
        self._bar_value = 0         # the bar's value before it went busy
        self._case_ok = True        # latest validation verdict (Setup tab)
        self._shape = None

    # ── run name ─────────────────────────────────────────────────────────
    def set_run_name(self, name):
        """Pre-fill the run name (Open case uses the file stem)."""
        if not self.run_name.text().strip():
            self.run_name.setText(str(name or ''))

    def current_run_name(self):
        return self.run_name.text().strip()

    # ── readouts, for the QA harness and the e2e suites ──────────────────
    def chip_texts(self):
        """The stat chips as {label: value}, so a test reads what the
        user reads instead of walking widgets."""
        return {c.caption: c.value.text() for c in
                (self._chip_step, self._chip_t, self._chip_dt,
                 self._chip_pmax, self._chip_cells)}

    def paused_text(self):
        """What the run state says about a stepped run being held."""
        return self._paused_lbl.text()

    # ── body sash ────────────────────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        self._place_sash()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_sash()

    def _place_sash(self):
        """Park the sash so the live pane keeps >= 60 % of the width
        until the user drags it (QA-17)."""
        if self._sash_user:
            return
        w = self._body.width()
        if w <= 1:
            return
        want = max(self.LOG_MIN, min(int(w * self.LOG_FRAC),
                                     w - self.VIEW_MIN))
        sizes = self._body.sizes()
        if not sizes or abs(sizes[0] - want) > 4:
            self._body.setSizes([want, max(1, w - want)])

    # ── live-view sub-tab switching ──────────────────────────────────────
    #: which widget each segment shows
    def _view_widget(self, value):
        return {'3D view': self.view3d,
                'Gauges': self.gauges}.get(value, self.pane)

    def _view_selected(self, value):
        self._stack.setCurrentWidget(self._view_widget(value))
        # the solver only does the work while someone is watching
        self.gauges_wanted.emit(value == 'Gauges')

    def show_3d_tab(self):
        self._view_seg.set('3D view')
        self._view_selected('3D view')

    def show_slice_tab(self):
        self._view_seg.set('Live slice')
        self._view_selected('Live slice')

    def show_gauges_tab(self):
        self._view_seg.set('Gauges')
        self._view_selected('Gauges')

    def watching_gauges(self):
        return self._stack.currentWidget() is self.gauges

    def _set_tab_order(self):
        """Walk Tab the way the tab reads, not the way it was built.

        Qt's default is construction order, which is right almost
        everywhere in this app - the forms are built top to bottom. This
        panel is the exception, because its two bars and its two body
        columns are built in an order that has nothing to do with where
        they end up: measured, Tab went Run (left) -> Name (middle) ->
        Initialise (left) -> Refresh (far right) -> the log (left) ->
        the view controls (middle), bouncing across the window six
        times.

        The log stays in the chain rather than being taken out of it: it
        is read-only, but a keyboard user still needs to reach it to
        scroll and copy. It just goes last, after every control.
        """
        chain = [self.run_btn, self.stop_btn, self.view3d_btn,
                 self.run_name, self.init_btn, *self._exec_btns,
                 self.refresh_val, self.refresh_mode,
                 self._view_seg, self.show_mesh, self.auto_clim,
                 self.clim_min, self.clim_max, self.log]
        for first, second in zip(chain, chain[1:]):
            QWidget.setTabOrder(first, second)

    def current_view(self):
        return '3D view' if self._stack.currentWidget() is self.view3d \
            else 'Live slice'

    # ── event handlers (called from the controller) ──────────────────────
    def set_running(self, running):
        self._running = bool(running)
        if running:
            # the cadence belongs to the run: a native run after a foam
            # one must not inherit "frames every ~0.05 ms" (G7)
            self._cadence = 0.0
            self._cadence_steps = 0
            self._last_dt = 0.0
            self._last_field = None
        start_ok = (not running) and (not self._busy) and self._case_ok
        self.run_btn.setEnabled(start_ok)
        self.init_btn.setEnabled(start_ok)
        # a disabled Stop used to stay danger-red, reading as armed
        self.stop_btn.setEnabled(bool(running))
        set_button_kind(self.stop_btn, 'danger' if running else 'default')
        for b in self._exec_btns:
            b.setEnabled(bool(running))
        self.set_paused(False)
        if running:
            self.progress.setValue(0)
            self._clear_log()
            # Everything below belongs to the PREVIOUS run: the chips and
            # the live plot used to keep its step/time/field until the new
            # run's first frame, which on a blastFoam cold start is minutes
            # of a stale picture (and, after Initialise Model, a t = 0 plot
            # beside the last run's step count).
            self._reset_readouts()
        else:
            # live attach only during a run; Results tab covers afterwards
            self.view3d_btn.setEnabled(False)

    def _reset_readouts(self):
        """Chips back to '-', live plot to a waiting placeholder, 3D view
        dropped: nothing on the Run tab may still describe the last run."""
        self._last_step = None
        self._chip_cells.hide()
        for chip in (self._chip_step, self._chip_t, self._chip_dt,
                     self._chip_pmax, self._chip_cells):
            chip.set('—')
        self._solid = None
        self._mesh_geom = None
        self._mesh_levels = None
        self._shape = None
        self.pane.show_placeholder()
        self.gauges.reset()
        try:
            self.view3d.reset()
        except Exception:
            pass

    def set_gauge_payload(self, payload):
        self.gauges.set_payload(payload)

    def say_no_gauges(self):
        """The case has no gauges, so the view has nothing to wait for."""
        self.gauges.reset(NO_GAUGES)

    def set_validation(self, ok, n_errors=0, text=None):
        """Mirror the Setup validation strip on the Run tab and gate the
        start buttons, so an invalid case is visible here instead of only
        as a modal after pressing Run. `text` overrides the wording."""
        self._case_ok = bool(ok)
        if ok:
            self._valid_lbl.setText(text or 'Case OK')
            self._valid_lbl.setStyleSheet(f'color: {theme.cur("ok")};')
        else:
            n = max(int(n_errors), 1)
            self._valid_lbl.setText(
                text or f'{n} error{"s" if n != 1 else ""} - see Setup')
            self._valid_lbl.setStyleSheet(f'color: {theme.cur("error")};')
        if not (self._running or self._busy):
            self.run_btn.setEnabled(bool(ok))
            self.init_btn.setEnabled(bool(ok))

    def set_busy(self, busy):
        """A job that is not a solve - the HD 1.3 assessment - is working
        on a thread: Run and Initialise Model off, the bar indeterminate.
        Nothing else changes; the log, chips and live view still describe
        the last solve, and the bar gets its old value back afterwards."""
        busy = bool(busy)
        if busy and not self._busy:
            self._bar_value = self.progress.value()
        self._busy = busy
        if busy:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1000)
            self.progress.setValue(self._bar_value)
        start_ok = not (self._running or busy) and self._case_ok
        self.run_btn.setEnabled(start_ok)
        self.init_btn.setEnabled(start_ok)

    def mark_refresh(self, ok):
        """Red-border the 'Refresh every' box when its value is unusable
        (it used to fall back to automatic in silence)."""
        self.refresh_val.setProperty('error', 'false' if ok else 'true')
        theme.repolish(self.refresh_val)

    def refresh_policy_text(self):
        return self.refresh_val.text(), self.refresh_mode.currentText()

    def set_refresh_policy_text(self, value, mode):
        self.refresh_val.setText(str(value or ''))
        if mode in ('seconds', 'steps'):
            self.refresh_mode.setCurrentText(mode)

    def set_paused(self, paused):
        self._paused_lbl.setText(
            ('PAUSED at step '
             f'{self._last_step}' if self._last_step is not None
             else 'PAUSED') if paused else '')

    def enable_view3d(self, enabled):
        self.view3d_btn.setEnabled(bool(enabled))

    def on_log(self, text):
        line = str(text)
        if self._AMR_MARK in line and self._amr_run:
            # replace the previous (also collapsed) AMR line in place
            cur = self.log.textCursor()
            cur.movePosition(QTextCursor.End)
            cur.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
            cur.removeSelectedText()
            cur.deletePreviousChar()
            self._amr_run += 1
            line = f'{line}   [{self._amr_run} AMR writes so far]'
        elif self._AMR_MARK in line:
            self._amr_run = 1
        else:
            self._amr_run = 0
        self.log.appendPlainText(line)
        self.log.verticalScrollBar().setValue(
            self.log.verticalScrollBar().maximum())

    def log_text(self):
        return self.log.toPlainText()

    def _clear_log(self):
        self._amr_run = 0
        self.log.clear()

    def mark_complete(self):
        """Run reached its own end: fill the bar. The worker throttles
        progress messages to ~10 Hz, so the final one is usually dropped
        and the last frac this panel ever saw is short of 1.0."""
        self.progress.setValue(1000)

    def on_progress(self, p):
        self.progress.setValue(int(round(1000 * max(0.0, min(1.0, p.frac)))))
        self._last_step = p.step
        self._chip_step.set(str(p.step))
        self._chip_t.set(f'{p.t*1e3:.3f}')
        self._chip_dt.set(f'{p.dt:.2e}')
        self._last_dt = float(p.dt)     # turns a step cadence into a time
        self._chip_pmax.set(f'{p.p_max / 1e3:,.4g}')

    def on_run_started(self, info):
        self._last_field = None
        self._mesh_geom = None
        self._mesh_levels = None
        if info['dim'] == 1:
            self._solid = None
            self._shape = None
            self.pane.start_1d(info)
        else:
            self._solid = np.asarray(info['solid'], dtype=bool)
            self._shape = self._solid.shape
            self.pane.start_2d(info)
            # mesh_src: the plane's source-cell ids for a refined foam
            # run (absent/None = uniform: every face)
            self._mesh_geom = (info['x_face'], info['y_face'],
                               info.get('mesh_src'))
            # dynamic AMR: frames carry their level map; display_level
            # sizes the blocks (the display grid sits at that level)
            self._disp_level = info.get('display_level')
            self._rebuild_overlay()

    # ── live colour range (2D pane) ──────────────────────────────────────
    def _sync_clim_state(self):
        for ent in self._clim_entries:
            ent.setEnabled(not self.auto_clim.isChecked())

    def live_clim(self):
        """(vmin, vmax) in kPa for the live pane, or None for autoscale.
        A blank or unparsable box falls back to autoscale rather than
        pinning the picture to a nonsense range."""
        if self.auto_clim.isChecked():
            return None
        try:
            lo = float(self.clim_min.text().strip() or 0.0)
            hi = float(self.clim_max.text().strip())
        except ValueError:
            return None
        if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
            return None
        return (lo, hi)

    def _clim_changed(self):
        self._sync_clim_state()
        if self.pane.image is not None and self._last_field is not None:
            self.pane.set_frame_2d(self._last_field, clim=self.live_clim())

    def set_cadence(self, dt=None, steps=None):
        """How often live frames arrive: `steps` solver steps (the live
        sample) or `dt` seconds (writeInterval, when there is no live
        sample). Either may be None for "unchanged" - the adaptive
        controller reports one, the refresh policy the other."""
        if dt is not None:
            try:
                self._cadence = max(0.0, float(dt))
            except (TypeError, ValueError):
                self._cadence = 0.0
        if steps is not None:
            try:
                self._cadence_steps = max(0, int(steps))
            except (TypeError, ValueError):
                self._cadence_steps = 0

    @staticmethod
    def _fmt_dt(seconds):
        ms = seconds * 1e3
        return f'{ms * 1e3:.3g} µs' if ms < 0.01 else f'{ms:.3g} ms'

    def cadence_text(self):
        """"frames every ~X" for the live-view title, or '' when the run
        emits whenever it likes (native)."""
        if self._cadence_steps > 0:
            if self._last_dt > 0.0:
                return ('frames every ~'
                        + self._fmt_dt(self._cadence_steps * self._last_dt))
            return f'frames every ~{self._cadence_steps} solver steps'
        if self._cadence > 0.0:
            return 'frames every ~' + self._fmt_dt(self._cadence)
        return ''

    def _rebuild_overlay(self):
        """Add/remove the cell-edge overlay per the checkbox."""
        if self.pane.image is None or self._mesh_geom is None:
            return
        if not self.show_mesh.isChecked():
            self.pane.clear_mesh()
            return
        xf, yf, src = self._mesh_geom
        lv = self._mesh_levels
        if lv is not None:
            lv = np.asarray(lv)
            src = refine.fine_src(
                np.maximum(lv, 0),
                int(self._disp_level or lv.max()),
                solid_fine=(lv < 0) if (lv < 0).any() else None)
        self.pane.set_mesh_segments(
            refine.mesh_segments_2d(src, xf, yf, max_lines=MESH_MAX_LINES))

    def _show_cells(self, levels):
        """Live cell count of a dynamic-AMR mesh (QA-32).

        `levels` is a level map on the DISPLAY grid (the finest displayed
        level), so a cell at level l stands for 2**((disp - l) * ndim)
        display cells - count each of them once. A 3D run hands over the
        live plane, not the whole mesh; the tooltip says so.
        """
        try:
            lv = np.asarray(levels)
            disp = float(lv.max())
            n = int(round(float(np.power(
                2.0, -(disp - lv.astype(np.float64)) * lv.ndim).sum())))
        except (ValueError, TypeError, AttributeError):
            return
        self._chip_cells.show()
        self._chip_cells.set(f'{n:,}')

    def on_frame(self, field, t, levels=None):
        # Frames are coalesced in a single slot shared across chain stages,
        # so a frame may briefly belong to the NEXT stage while this panel
        # is still configured for the previous one - guard by shape.
        field = np.asarray(field)
        if self.pane.image is not None:
            if self._shape is None or field.shape != self._shape:
                return
            self._last_field = field
            self.pane.set_frame_2d(field, clim=self.live_clim())
            if levels is not None and np.shape(levels) == field.shape:
                self._mesh_levels = levels
                self._show_cells(levels)
                if self.show_mesh.isChecked():
                    self._rebuild_overlay()
        elif self.pane.line is not None:
            if field.ndim != 2 or field.shape[0] != 2:
                return
            r, p = field
            self.pane.set_frame_1d(r, p)
        else:
            return
        self.pane.set_time(t, self.cadence_text())


class _NoViewer(QLabel):
    """Stand-in when no 3D host is wired (tests): keeps the panel API."""

    def __init__(self):
        super().__init__('3D view unavailable')
        self.setObjectName('view')
        self.setAlignment(Qt.AlignCenter)

    def reset(self):
        pass

    def on_done(self, reason):
        pass
