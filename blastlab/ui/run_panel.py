"""02 Run (GUI-6, plan §6, boards Run / Run_Finished): three columns -
the run controls (280 px) · the centre (progress strip, view toolbar,
the live view, the dock) · the live gauges (340 px).

It began as a port of gui/run_panel.py and the controller still feeds it
through the same on_* methods; the public API of that one-column panel
(signals, attributes, methods) is kept with its meaning unchanged, only
where the widgets sit moved."""

import math
import os

import numpy as np
import shiboken6
from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QIcon, QTextCharFormat, QTextCursor,
                           QTextDocument)
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QProgressBar, QPushButton,
                               QSizePolicy, QStackedWidget, QVBoxLayout,
                               QWidget)

from ..core import refine
from ..services.model_folder import folder_for
from . import theme
from .components import Banner, Collapsible, StatTile, ToggleSwitch
from .live_gauges import (ALL_DROPPED, NO_GAUGES, WAITING,  # noqa: F401
                          LiveGaugePane)
from .pg_plots import MESH_MAX_LINES, LiveSlicePane
from .run_clock import RunClock, fmt_duration
from .run_dock import RunDock
from .run_gauges import GaugeColumn
from .setup_strip import fmt_count
from .setup_tree import _letter_space
from .theme import GAP
from .widgets import (ZWSP, ScrollColumn, Segmented, clean_copy,
                      set_button_kind)

#: the Runs folder's Browse button (the Tk folder icon says the same)
BROWSE_TIP = ('Choose the Runs folder: the folder that holds one '
              'sub-folder per model.')

#: the side columns (board Run lines 62 and 259). Each gives way down to
#: its *_MIN only when the window cannot hold all three columns - the
#: rule of the Setup tree (decision D19).
CTRL_W, CTRL_MIN = 280, 248
GAUGE_W, GAUGE_MIN = 340, 300
#: the dock under the view (board line 246: 142 px with its 38 px tab
#: strip). On a short window it gives way to DOCK_MIN (DOCK_FRACTION of
#: the panel's height), so the view keeps its room.
DOCK_H, DOCK_MIN, DOCK_FRACTION = 140, 110, 0.18
#: the resolved model-folder line is recomputed this long after the last
#: keystroke (it lists the Runs folder to match the model's spelling)
PATH_DEBOUNCE_MS = 200
#: shown in the path line while either box is blank
PATH_BLANK = '<Runs folder>' + os.sep + '<Model>' + os.sep
#: the progress strip goes onto two rows below this many px per tile
#: (Progress keeps PROGRESS_MIN): measured against the widest readouts
#: a run shows (`88,888 kPa`, `1,234,567` cells) in Space Grotesk 21 px
TILE_MIN = 112
PROGRESS_MIN = 220
#: Progress's one-row floor (D213 b): lower than PROGRESS_MIN because the
#: time line already elides (`QSizePolicy.Ignored`) - only its caps +
#: percent head must stay readable (measured ~158 px for `PROGRESS` +
#: `100 %` at 1280 x 840, offscreen; +2 px margin). Applied only while
#: `arrange()` picks one row; two-row mode keeps PROGRESS_MIN.
PROGRESS_MIN_1ROW = 160
#: the widest P MAX readout the one-row rule must hold at StatTile's
#: 14 px floor (GUI-11 T18, QA S3-1, D213); the readout string itself is
#: unchanged (U4, D52)
PMAX_WIDEST = '8.888e+05'
#: the live view never gets less than this; the dock gives way first,
#: down to its tab strip (GUI-11 T18, QA S3-7, D213)
VIEW_MIN = 200
#: the dock's tab strip: 40 px tabs, the 1 px rule and its 1 px margin
DOCK_FLOOR = 42

#: what a 0-D case shows where the view toolbar and the live view were
#: (GUI-11 T5, F12 owner-approved as GUI-11 d, D206)
HD13_NOTE = ('An HD 1.3 assessment has no field to show. When it ends, its '
             'report and load files are listed in the log below.')

#: Qt's QWIDGETSIZE_MAX (not exported by PySide6): "no maximum"
QWIDGETSIZE_MAX = (1 << 24) - 1

#: the chip keys the QA harness and the e2e suites read (chip_texts)
CHIP_KEYS = ('step', 't [ms]', 'dt [s]', 'p max [kPa]', 'cells')
#: the elapsed line refreshes this often while a run or an HD 1.3
#: assessment is live - a blastFoam cold start sends no progress for
#: minutes, and the time must still move (off while idle: B02 idle CPU)
TICK_MS = 1000


def unit_html(value, unit, colour):
    """A tile readout with its unit in a 13 px span (`5.818e+05 kPa`)."""
    if value == '—':
        return value
    return (f'{value} <span style="font-size: 13px; color: '
            f'{colour};">{unit}</span>')


def _two_state_icon(name, size, normal, disabled='muted'):
    """A glyph icon tinted `normal`, `disabled` when the button is off
    (theme.icon tints both states alike when a colour is forced)."""
    ic = QIcon()
    ic.addPixmap(theme.pixmap(name, size, color=normal), QIcon.Normal)
    ic.addPixmap(theme.pixmap(name, size, color=disabled), QIcon.Disabled)
    return ic


class _StopButton(QPushButton):
    """The board's Stop (Run line 85): a stop mark, `Stop` in the display
    face and a mono `Shift+Esc` key cap - three labels inside one
    QPushButton, so clicks, focus and the disabled state stay the
    button's. `set_button_kind(.., 'danger')` still names it `danger`
    (test_ui_run_panel U3); the `stop` property picks the board look."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty('stop', True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName('Stop')
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(9)
        self.mark = QLabel()
        self.text_lbl = QLabel('Stop')
        self.text_lbl.setObjectName('stoptext')
        self.key = QLabel('Shift+Esc')
        self.key.setObjectName('stopkey')
        lay.addStretch(1)
        for w in (self.mark, self.text_lbl, self.key):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            lay.addWidget(w, 0, Qt.AlignVCenter)
        lay.addStretch(1)
        self.retint()

    def retint(self, _mode=None):
        self.mark.setPixmap(theme.pixmap('stop', 13, color='stop_text'))

    def sizeHint(self):
        return QSize(self.layout().sizeHint().width(), 48)

    def minimumSizeHint(self):
        return QSize(self.layout().minimumSize().width(), 48)


class _SetupLink(QPushButton):
    """`✓ Setup: Case OK · 368 k cells` at the foot of the controls (board
    line 149): a flat button of labels; the verdict label is the panel's
    `_valid_lbl`, whose pinned texts are unchanged."""

    def __init__(self, valid_lbl, parent=None):
        super().__init__(parent)
        self.setObjectName('setuplink')
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName('Back to Setup')
        self.setToolTip('Back to 01 Setup')
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(6)
        self.icon_lbl = QLabel()
        self.prefix = QLabel('Setup:')
        self.valid = valid_lbl
        self.cells = QLabel('')
        for w in (self.icon_lbl, self.prefix, self.valid, self.cells):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            lay.addWidget(w, 0, Qt.AlignVCenter)
        lay.addSpacing(4)
        lay.insertSpacing(1, 4)
        lay.addStretch(1)

    def sizeHint(self):
        return QSize(self.layout().sizeHint().width(), 42)

    def minimumSizeHint(self):
        return QSize(self.layout().minimumSize().width(), 42)


class _RunStrip(QFrame):
    """The progress strip (board Run lines 157-181): the Progress tile
    (`accent_bg`) and the TIME · STEP · P MAX (· CELLS) stat tiles. One
    row when the centre holds it; otherwise Progress (and CELLS) on the
    first row and the three readouts on the second - the D29 pattern."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('runstrip')
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(GAP)
        self._row0 = QHBoxLayout()
        self._row1 = QHBoxLayout()
        for r in (self._row0, self._row1):
            r.setContentsMargins(0, 0, 0, 0)
            r.setSpacing(GAP)
            outer.addLayout(r)

        # ── the Progress tile ────────────────────────────────────────────
        self.progress_tile = QFrame()
        self.progress_tile.setObjectName('tile')
        self.progress_tile.setProperty('variant', 'accent')
        pl = QVBoxLayout(self.progress_tile)
        pl.setContentsMargins(14, 10, 14, 10)
        pl.setSpacing(6)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        self.caps = QLabel('PROGRESS')
        self.caps.setObjectName('progresscaps')
        _letter_space(self.caps)
        head.addWidget(self.caps, 0, Qt.AlignBaseline)
        # `78 %` in Space Grotesk 22 (board line 161); `—` while unknown
        self.pct_lbl = QLabel('—')
        self.pct_lbl.setObjectName('progresspct')
        head.addWidget(self.pct_lbl, 0, Qt.AlignBaseline)
        head.addStretch(1)
        self.paused_lbl = QLabel('')
        self.paused_lbl.setObjectName('pausedlbl')
        head.addWidget(self.paused_lbl, 0, Qt.AlignBaseline)
        pl.addLayout(head)
        self.progress = QProgressBar()
        self.progress.setObjectName('runbar')
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        pl.addWidget(self.progress)
        # `4 min 18 s elapsed · about 1 min 15 s left` (board line 164)
        self.time_lbl = QLabel('')
        self.time_lbl.setObjectName('progresstime')
        self.time_lbl.setMinimumWidth(0)
        self.time_lbl.setSizePolicy(QSizePolicy.Ignored,
                                    QSizePolicy.Preferred)
        pl.addWidget(self.time_lbl)
        self.progress_tile.setMinimumWidth(PROGRESS_MIN)

        # ── the stat tiles ───────────────────────────────────────────────
        self.tiles = {}
        for key, title, cap in (('time', 'Time', 'simulated'),
                                ('step', 'Step', 'dt — s'),
                                ('pmax', 'P max', 'in the field now'),
                                ('cells', 'Cells', 'AMR mesh, live plane')):
            # F34: a scientific p max (`2.799e+06 kPa`) keeps its unit
            t = StatTile(title, fit=True)
            t.caption.setText(cap)
            for lbl in (t.value, t.caption):
                # a long readout elides rather than hold the strip wide
                lbl.setMinimumWidth(0)
                lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            self.tiles[key] = t
        self._rows = None
        self.arrange(force=True)

    @staticmethod
    def _hidden(w):
        """Hidden on purpose (set_dim, the AMR cells rule). A parentless
        widget that was never shown also reports isHidden(); that is not
        a choice to keep, or the Progress tile would stay hidden for
        good once arrange() re-applied it."""
        return w.testAttribute(Qt.WA_WState_ExplicitShowHide) \
            and w.isHidden()

    def _shown_tiles(self):
        return [self.tiles[k] for k in ('time', 'step', 'pmax', 'cells')
                if not self._hidden(self.tiles[k])]

    def _pmax_need(self):
        """The P MAX tile width the widest readout (PMAX_WIDEST kPa) needs
        at StatTile's 14 px floor: font metrics of the rendered readout,
        as StatTile._fit_value measures it, never geometry (D164)."""
        t = self.tiles['pmax']
        t.value.ensurePolished()
        f = QFont(t.value.font())
        f.setPixelSize(StatTile.FIT_MIN_PX)
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(f)
        doc.setHtml(unit_html(PMAX_WIDEST, 'kPa', '#000'))
        m = t.layout().contentsMargins()
        return (math.ceil(doc.idealWidth()) + m.left() + m.right()
                + 2 * t.frameWidth())

    def _one_row_need(self, tiles):
        """The width one row needs (D213 b): P MAX its measured need,
        every other shown tile TILE_MIN, Progress its lower one-row
        floor - widths, not the old readout-stretch share."""
        pmax = self.tiles['pmax']
        need = sum(TILE_MIN for t in tiles if t is not pmax)
        if pmax in tiles:
            need += self._pmax_need()
        return need + PROGRESS_MIN_1ROW

    def _one_row_fits(self, width):
        tiles = self._shown_tiles()
        n = len(tiles)
        avail = width - GAP * n
        return avail >= self._one_row_need(tiles)

    def rows(self):
        """1 or 2 (tests, the viewer sampler)."""
        return self._rows

    def arrange(self, force=False):
        width = self.contentsRect().width() or 10 ** 6
        rows = 1 if self._one_row_fits(width) else 2
        if rows == self._rows and not force:
            return
        self._rows = rows
        hidden = {id(w): self._hidden(w) for w in
                  [self.progress_tile, *self.tiles.values()]}
        for lay in (self._row0, self._row1):
            while lay.count():
                lay.takeAt(0)
        t = self.tiles
        if rows == 1:
            # D213 b: each tile holds its own floor (TILE_MIN, or P MAX's
            # measured need) and Progress its lower one-row floor, so the
            # widths the fits check promised are the widths Qt gives -
            # stretch (unchanged) only shares space above those floors.
            self.progress_tile.setMinimumWidth(PROGRESS_MIN_1ROW)
            self._row0.addWidget(self.progress_tile, 23)
            for k in ('time', 'step', 'pmax', 'cells'):
                t[k].setMinimumWidth(self._pmax_need() if k == 'pmax'
                                      else TILE_MIN)
                self._row0.addWidget(t[k], 10)
        else:
            # Progress (and the AMR cells) on top, the readouts below -
            # the two-row layout, unchanged (D29): no per-tile floor,
            # Progress back at its wider two-row minimum
            self.progress_tile.setMinimumWidth(PROGRESS_MIN)
            for k in ('time', 'step', 'pmax', 'cells'):
                t[k].setMinimumWidth(0)
            self._row0.addWidget(self.progress_tile, 23)
            self._row0.addWidget(t['cells'], 10)
            for k in ('time', 'step', 'pmax'):
                self._row1.addWidget(t[k], 10)
        for w in [self.progress_tile, *self.tiles.values()]:
            w.setVisible(not hidden[id(w)])
        self.updateGeometry()

    def minimumSizeHint(self):
        # never hold the centre wide: arrange() wraps as the width drops
        hint = super().minimumSizeHint()
        return QSize(PROGRESS_MIN, hint.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange()

    def changeEvent(self, event):
        # QA S3-2 (D213): a theme or font change re-measures the tiles, so
        # the strip is laid out again at their new heights
        super().changeEvent(event)
        if event.type() in (QEvent.StyleChange, QEvent.FontChange):
            QTimer.singleShot(0, self._rearrange)

    def _rearrange(self):
        if shiboken6.isValid(self):
            self.arrange(force=True)


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
    #: the Runs folder box was edited or browsed (saved to settings)
    runs_dir_changed = Signal()
    #: the Setup link at the foot of the controls was clicked
    setup_requested = Signal()
    #: the finish banner's `Open in 03 Results →` was clicked
    results_requested = Signal()

    #: a dynamic-AMR run logs one of these per written time - 60+ lines
    #: for half a millisecond of simulation, which buried every other
    #: message. They are collapsed HERE rather than in the solver: the
    #: text itself is the e2e drivers' instrumentation (cells per write)
    #: and must keep reaching stdout and the transcript unchanged.
    _AMR_MARK = '[blastfoam] AMR t = '

    def __init__(self, view3d_host=None, clock=None, parent=None):
        super().__init__(parent)
        self.view3d = view3d_host
        #: run time with held time excluded (ui/run_clock.py); the window
        #: drives it and reads it for the Stop confirmation
        self.clock = clock if clock is not None else RunClock()
        self._pending_gauges = None  # a payload the hidden Gauges page owes
        body = QHBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(GAP)
        self._ctrl = self._build_controls()
        body.addWidget(self._ctrl)
        self._centre = self._build_centre()
        # a strip, banner or chain strip changing height re-fits the dock
        # (D213: the live view keeps VIEW_MIN)
        self._centre.installEventFilter(self)
        body.addWidget(self._centre, 1)
        self._gauge_col = self._build_gauge_column()
        body.addWidget(self._gauge_col)
        self._set_tab_order()

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
        self._n_cells = None        # cells of the latest validation report
        self._run_again = False     # a run has finished this session
        self._dim = 2
        self._shape = None
        self._frac = None           # the stage's progress fraction
        self._ended = None          # how the last run / assessment ended
        self._end_reason = ''       # the last result's stop_reason (T7)
        self._tick = QTimer(self)
        self._tick.setInterval(TICK_MS)
        self._tick.timeout.connect(self._render_time)
        self._readout = dict.fromkeys(CHIP_KEYS, '—')
        self._reset_readouts_text()
        self._sync_run_text()
        self._sync_clim_state()
        self._update_path()
        theme.signals.changed.connect(self._retheme)
        self._retheme()

    # ── the controls column (board lines 62-153) ─────────────────────────
    def _build_controls(self):
        frame = QFrame()
        frame.setObjectName('runctl')
        frame.setFixedWidth(CTRL_W)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.setSpacing(0)
        col = ScrollColumn(spacing=18)
        # 14 + 12: the Live view card's refresh row (label, box, unit)
        # needs 238 px, and the vertical scroll bar takes 10 of the
        # column's 278 once Step through is open (measured)
        col.layout_.setContentsMargins(14, 15, 12, 15)
        # no Tab stop of its own (it was one after the log): Tab through
        # its controls still scrolls it, QScrollArea.focusNextPrevChild
        col.setFocusPolicy(Qt.NoFocus)
        self._ctrl_scroll = col
        fl.addWidget(col)

        # ── where the files go (OUT-1: <Runs folder>\<Model>\ receives
        # every file of a run; both boxes are required before Run) ──────
        files = QWidget()
        wl = QVBoxLayout(files)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(5)
        caps = QLabel('WHERE THE FILES GO')
        caps.setObjectName('eyebrow')
        _letter_space(caps)
        wl.addWidget(caps)
        wl.addSpacing(5)
        wl.addWidget(self._field_label('Runs folder'))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.runs_dir = QLineEdit()
        self.runs_dir.setObjectName('runbox')
        self.runs_dir.setMinimumWidth(0)
        self.runs_dir.setPlaceholderText(r'e.g. C:\Users\me\BLASTLAB_RUNS')
        self.runs_dir.setToolTip(
            'Required. The folder that holds one sub-folder per model; a '
            'run writes every file it produces into <Runs folder>\\<Model>. '
            'Remembered between sessions.')
        self.runs_dir.editingFinished.connect(self.runs_dir_changed.emit)
        row.addWidget(self.runs_dir, 1)
        self.runs_browse = QPushButton('')
        self.runs_browse.setObjectName('squarebtn')
        self.runs_browse.setFixedSize(34, 34)
        self.runs_browse.setCursor(Qt.PointingHandCursor)
        self.runs_browse.setAccessibleName('Browse for the Runs folder')
        self.runs_browse.setToolTip(BROWSE_TIP)
        self.runs_browse.clicked.connect(lambda *_: self._browse_runs_dir())
        row.addWidget(self.runs_browse)
        wl.addLayout(row)
        wl.addSpacing(5)
        wl.addWidget(self._field_label('Model'))
        # results used to be labelled by dim + a counter only, so three
        # runs of different cases read "Run 1 - 2D", "Run 2 - 2D" ... (N9)
        self.run_name = QLineEdit()
        self.run_name.setObjectName('runbox')
        self.run_name.setMinimumWidth(0)
        self.run_name.setPlaceholderText('MODEL')
        self.run_name.setToolTip(
            'Required. The model folder <Runs folder>\\<Model> that '
            'receives every file of this run (a valid Windows folder name, '
            'at most 100 characters). It also names the run in the Results '
            'picker.')
        wl.addWidget(self.run_name)
        wl.addSpacing(5)
        # the resolved folder, display only (board line 77-80)
        prow = QHBoxLayout()
        prow.setContentsMargins(0, 0, 0, 0)
        prow.setSpacing(6)
        self._path_mark = QLabel()
        prow.addWidget(self._path_mark, 0, Qt.AlignTop)
        self._path_lbl = QLabel('')
        self._path_lbl.setObjectName('runpath')
        self._path_lbl.setWordWrap(True)
        self._path_lbl.setMinimumWidth(0)
        self._path_lbl.setSizePolicy(QSizePolicy.Ignored,
                                     QSizePolicy.Preferred)
        self._path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # the shown text wraps after each separator (ZWSP); a copy is the
        # path itself (GUI-10, F23)
        clean_copy(self._path_lbl)
        prow.addWidget(self._path_lbl, 1)
        wl.addLayout(prow)
        self._path_text = PATH_BLANK
        self._path_timer = QTimer(self)
        self._path_timer.setSingleShot(True)
        self._path_timer.setInterval(PATH_DEBOUNCE_MS)
        self._path_timer.timeout.connect(self._update_path)
        for box in (self.runs_dir, self.run_name):
            box.textChanged.connect(lambda _t: self._path_timer.start())
        col.add(files)

        # ── Stop / Run and the 3D square (board lines 83-98) ────────────
        act = QWidget()
        al = QHBoxLayout(act)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(8)
        self.stop_btn = _StopButton()
        self.stop_btn.setToolTip('Stop the run (Shift+Esc). After 30 s of '
                                 'run time it asks first; time spent held '
                                 'does not count.')
        self.stop_btn.clicked.connect(lambda *_: self.stop_requested.emit())
        self.stop_btn.setEnabled(False)
        self.stop_btn.setVisible(False)
        al.addWidget(self.stop_btn, 1)
        self.run_btn = QPushButton('Run')
        self.run_btn.setObjectName('runbig')
        self.run_btn.setProperty('runtab', True)
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.setIconSize(QSize(14, 14))
        self.run_btn.setToolTip('Run the case (F5)')
        self.run_btn.clicked.connect(lambda *_: self.run_requested.emit())
        al.addWidget(self.run_btn, 1)
        self.view3d_btn = QPushButton('')
        self.view3d_btn.setObjectName('run3d')
        self.view3d_btn.setFixedWidth(56)
        self.view3d_btn.setIconSize(QSize(19, 19))
        self.view3d_btn.setCursor(Qt.PointingHandCursor)
        self.view3d_btn.setAccessibleName('Open the 3D view')
        self.view3d_btn.setToolTip('Open the 3D view')
        self.view3d_btn.clicked.connect(
            lambda *_: self.view3d_requested.emit())
        self.view3d_btn.setEnabled(False)
        al.addWidget(self.view3d_btn)
        col.add(act)

        # ── Step through: today's Exec row, collapsed (board 100-122) ───
        self.step_card = Collapsible('Step through', 'Exec 1 … 1000')
        cap = QLabel('Initialise, then advance the solver a few steps at '
                     'a time.')
        cap.setObjectName('runhint')
        cap.setWordWrap(True)
        self.step_card.add(cap)
        self.init_btn = QPushButton('Initialise model')
        self.init_btn.setObjectName('runquiet')
        self.init_btn.setCursor(Qt.PointingHandCursor)
        self.init_btn.setToolTip('Start the run held at step 0, so the '
                                 'initial field is visible; the buttons '
                                 'below advance it')
        self.init_btn.clicked.connect(lambda *_: self.init_requested.emit())
        self.step_card.add(self.init_btn)
        self._exec_btns = []

        def exec_btn(text, cmd, mono):
            b = QPushButton(text)
            b.setObjectName('execbtn')
            b.setProperty('mono', bool(mono))
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumWidth(0)
            b.clicked.connect(lambda *_, c=cmd: self.exec_requested.emit(c))
            b.setEnabled(False)
            self._exec_btns.append(b)
            return b

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        for i, n in enumerate((1, 10, 100, 1000)):
            grid.addWidget(exec_btn(f'+{n}', n, True), 0, i)
            grid.setColumnStretch(i, 1)
        self.step_card.add_layout(grid)
        pair = QHBoxLayout()
        pair.setContentsMargins(0, 0, 0, 0)
        pair.setSpacing(6)
        pair.addWidget(exec_btn('To the end', 'run', False), 1)
        pair.addWidget(exec_btn('Pause', 'pause', False), 1)
        self.step_card.add_layout(pair)
        self._exec_btns[4].setToolTip('Run on to the end')
        self._exec_btns[5].setToolTip('Hold the run at the current step')
        col.add(self.step_card)

        # ── Live view (board lines 124-146) ─────────────────────────────
        self.live_card = QFrame()
        self.live_card.setObjectName('runcard')
        ll = QVBoxLayout(self.live_card)
        ll.setContentsMargins(12, 12, 12, 12)
        ll.setSpacing(12)
        title = QLabel('Live view')
        title.setObjectName('runcardtitle')
        ll.addWidget(title)
        rrow = QHBoxLayout()
        rrow.setContentsMargins(0, 0, 0, 0)
        rrow.setSpacing(6)
        rlbl = self._field_label('Refresh every', wrap=True)
        rrow.addWidget(rlbl, 1)
        # live-view refresh rate (2D slice + 3D view); blank = automatic
        self.refresh_val = QLineEdit()
        self.refresh_val.setObjectName('runsmall')
        self.refresh_val.setPlaceholderText('auto')
        self.refresh_val.setMinimumWidth(40)
        self.refresh_val.setMaximumWidth(60)
        self.refresh_val.setToolTip('How often the live view redraws; '
                                    'leave blank (or 0) for automatic.')
        self.refresh_val.editingFinished.connect(self.refresh_changed.emit)
        rrow.addWidget(self.refresh_val)
        self.refresh_mode = QComboBox()
        self.refresh_mode.setObjectName('runsmall')
        self.refresh_mode.addItems(['seconds', 'steps'])
        self.refresh_mode.setAccessibleName('Refresh unit')
        self.refresh_mode.currentTextChanged.connect(
            lambda _t: self.refresh_changed.emit())
        rrow.addWidget(self.refresh_mode)
        ll.addLayout(rrow)
        arow = QHBoxLayout()
        arow.setContentsMargins(0, 0, 0, 0)
        arow.setSpacing(10)
        arow.addWidget(self._field_label('Colour range: auto', wrap=True), 1)
        # manual colour range for the 2D live pane, mirroring the 3D
        # viewer's Min/Max: a late weak frame used to rescale the whole
        # picture, so nothing could be compared across a run (G7)
        self.auto_clim = ToggleSwitch()
        self.auto_clim.setAccessibleName('Automatic colour range')
        self.auto_clim.setChecked(True)
        self.auto_clim.toggled.connect(lambda _c: self._clim_changed())
        arow.addWidget(self.auto_clim)
        ll.addLayout(arow)
        # Min / Max [kPa] only while the switch is off (plan §6)
        self.clim_row = QWidget()
        cl = QHBoxLayout(self.clim_row)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        self.clim_min = QLineEdit('0')
        self.clim_max = QLineEdit('')
        self._clim_entries = [self.clim_min, self.clim_max]
        for text, ent in (('Min', self.clim_min), ('Max', self.clim_max)):
            ent.setObjectName('runsmall')
            ent.setMinimumWidth(44)
            ent.editingFinished.connect(self._clim_changed)
            lbl = QLabel(text)
            lbl.setObjectName('runhint')
            cl.addWidget(lbl)
            cl.addWidget(ent, 1)
        unit = QLabel('kPa')
        unit.setObjectName('rununit')
        cl.addWidget(unit)
        ll.addWidget(self.clim_row)
        col.add(self.live_card)

        col.add_stretch()
        # ── the way back to Setup (board line 149) ──────────────────────
        # the Setup strip is on another screen, so the Run screen used to
        # give no hint that the case was invalid until a modal appeared
        self._valid_lbl = QLabel('')
        self.setup_link = _SetupLink(self._valid_lbl)
        self.setup_link.clicked.connect(
            lambda *_: self.setup_requested.emit())
        col.add(self.setup_link)
        return frame

    @staticmethod
    def _field_label(text, wrap=False):
        lbl = QLabel(text)
        lbl.setObjectName('runfield')
        # a row caption may wrap rather than hold the column wide
        lbl.setWordWrap(wrap)
        return lbl

    # ── the centre column (board lines 155-257) ──────────────────────────
    def _build_centre(self):
        centre = QWidget()
        centre.setMinimumWidth(0)
        cl = QVBoxLayout(centre)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(GAP)
        # GUI-9 puts the chain's stage strip here (board Run_Chain lines
        # 60-70) through set_chain_strip; hidden, empty and zero-height
        # until then
        self.chain_slot = QWidget()
        self.chain_slot.setObjectName('chainslot')
        csl = QHBoxLayout(self.chain_slot)
        csl.setContentsMargins(0, 0, 0, 0)
        csl.setSpacing(0)
        self.chain_slot.setFixedHeight(0)
        self.chain_slot.setVisible(False)
        cl.addWidget(self.chain_slot)

        self.strip = _RunStrip()
        self.progress = self.strip.progress
        # stepped execution used to be visible only as a "[interrupted]"
        # line in the log; say it where the run state is read
        self._paused_lbl = self.strip.paused_lbl
        t = self.strip.tiles
        self._tile_time, self._tile_step = t['time'], t['step']
        self._tile_pmax, self._tile_cells = t['pmax'], t['cells']
        # dynamic AMR moves the cell count every write; it was only ever
        # visible as a log line (QA-32). Shown on the first frame that
        # carries a level map, so a static run keeps three readouts.
        self._tile_cells.setToolTip('Cells of the dynamic (AMR) mesh on the '
                                    'live plane - a 3D run counts the '
                                    'slice, not the whole mesh.')
        self._tile_cells.hide()
        self.strip.arrange(force=True)
        cl.addWidget(self.strip)

        # the finish banner (board Run_Finished lines 183-189), between
        # the strip and the view toolbar; shown by show_finish, hidden at
        # the next start
        self.banner = Banner('', 'Open in 03 Results →',
                             on_action=self.results_requested.emit)
        self.banner.setVisible(False)
        # two unwrapped, elided lines (_render_banner): never wider than
        # the centre column, never clipped
        msg = self.banner.message
        msg.setWordWrap(False)
        msg.setMinimumWidth(0)
        msg.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        msg.installEventFilter(self)
        self._banner_lines = ('', '')
        cl.addWidget(self.banner)

        # the view toolbar: a row ABOVE the view, not floated over it -
        # the native 3D child window paints over any Qt sibling laid on
        # top of it (CLAUDE.md 8.7). In a widget of its own, so a 0-D case
        # can hide the row (GUI-11 T5, F12)
        self._view_bar = QWidget()
        bar = QHBoxLayout(self._view_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(GAP)
        segframe = QFrame()
        segframe.setObjectName('runseg')
        sl = QHBoxLayout(segframe)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(0)
        self._view_seg = Segmented(['Live slice', 'Gauges', '3D view'],
                                   height=28, small=True)
        self._view_seg.changed.connect(self._view_selected)
        sl.addWidget(self._view_seg)
        bar.addWidget(segframe)
        bar.addStretch(1)
        # cell edges over the live slice (true cells of a refined run)
        self.show_mesh = QPushButton('Show mesh')
        self.show_mesh.setObjectName('viewtool')
        self.show_mesh.setCheckable(True)
        self.show_mesh.setCursor(Qt.PointingHandCursor)
        self.show_mesh.setToolTip('Draw the cell edges over the live slice')
        self.show_mesh.toggled.connect(lambda _c: self._rebuild_overlay())
        bar.addWidget(self.show_mesh, 0, Qt.AlignVCenter)
        cl.addWidget(self._view_bar)

        view = QFrame()
        view.setObjectName('runview')
        vl = QVBoxLayout(view)
        vl.setContentsMargins(8, 8, 8, 8)
        vl.setSpacing(0)
        self._stack = QStackedWidget()
        vl.addWidget(self._stack, 1)
        self.pane = LiveSlicePane()
        self._stack.addWidget(self.pane)
        self.gauges = LiveGaugePane()
        self._stack.addWidget(self.gauges)
        if self.view3d is None:
            self.view3d = _NoViewer()
        self._stack.addWidget(self.view3d)
        self._view_seg.set('Live slice')
        self._stack.setCurrentWidget(self.pane)
        self._view_frame = view
        # QA S3-7 (D213): never collapsed under the strips and the banner
        view.setMinimumHeight(VIEW_MIN)
        cl.addWidget(view, 1)
        # 0-D: an HD 1.3 assessment has no field, so the toolbar and the
        # view give their place to one note (GUI-11 T5, F12, D206)
        self.hd13_note = QLabel(HD13_NOTE)
        self.hd13_note.setObjectName('muted')
        self.hd13_note.setWordWrap(True)
        self.hd13_note.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.hd13_note.setContentsMargins(4, 8, 4, 8)
        self.hd13_note.setVisible(False)
        cl.addWidget(self.hd13_note, 1)

        # the dock Log · Messages · Earlier runs, Copy / Save log…
        # (ui/run_dock.py, UX-18); `log` is its Log page, as before
        self.dock = RunDock()
        self.dock_frame = self.dock
        self.dock.setFixedHeight(DOCK_H)
        self._dock_tucked = False       # stepped aside for the view (D213)
        self.log = self.dock.log
        cl.addWidget(self.dock)
        return centre

    # ── the live-gauge column (board lines 259-335, ui/run_gauges.py) ────
    def _build_gauge_column(self):
        frame = QFrame()
        frame.setObjectName('rungauges')
        frame.setFixedWidth(GAUGE_W)
        gl = QVBoxLayout(frame)
        gl.setContentsMargins(18, 16, 18, 16)
        gl.setSpacing(0)
        self.gauge_col = GaugeColumn()
        gl.addWidget(self.gauge_col, 1)
        # the column follows the Setup case until a run starts; from then
        # on it describes the run (its case, its series) until the next
        self._col_from_run = False
        return frame

    # ── layout: column widths and the dock height ────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        self._fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def _fit(self):
        self._fit_columns()
        self._fit_dock()

    def _fit_columns(self):
        """280 / centre / 340, the side columns giving way (controls to
        248, gauges to 300, in proportion) only when the window cannot
        hold the centre's minimum between them."""
        w = self.width()
        if w <= 1:
            return
        centre_min = self._centre.minimumSizeHint().width()
        short = CTRL_W + GAUGE_W + 2 * GAP + centre_min - w
        ctrl, gauge = CTRL_W, GAUGE_W
        if short > 0:
            room_c, room_g = CTRL_W - CTRL_MIN, GAUGE_W - GAUGE_MIN
            take_c = min(room_c, round(short * room_c / (room_c + room_g)))
            take_g = min(room_g, short - take_c)
            ctrl, gauge = CTRL_W - take_c, GAUGE_W - take_g
        if self._ctrl.width() != ctrl or self._ctrl.minimumWidth() != ctrl:
            self._ctrl.setFixedWidth(ctrl)
        if self._gauge_col.width() != gauge \
                or self._gauge_col.minimumWidth() != gauge:
            self._gauge_col.setFixedWidth(gauge)

    def _fit_dock(self):
        h = self.height()
        if h <= 1:
            return
        want = max(DOCK_MIN, min(DOCK_H, int(h * DOCK_FRACTION)))
        room = self._dock_room()
        # QA S3-7 (D213): the view keeps VIEW_MIN; the dock gives way
        # first, down to its tab strip, and steps aside when not even that
        # fits (1100 x 720 after a chain: chain strip, two-row strip and
        # banner). Decided with the dock counted as shown, so it cannot
        # flip-flop
        tuck = room is not None and room < DOCK_FLOOR
        if tuck != self._dock_tucked:
            self._dock_tucked = tuck
            self.dock_frame.setVisible(not tuck)
        if tuck:
            return
        if room is not None and room < want:
            want = room
        if self.dock_frame.height() != want \
                or self.dock_frame.minimumHeight() != want:
            self.dock_frame.setFixedHeight(want)

    def _dock_room(self):
        """The dock height that leaves the live view VIEW_MIN under the
        chain strip, the progress strip, the banner and the toolbar at
        their size hints; None when the view is hidden (0-D)."""
        view = self._view_frame
        if not view.isVisibleTo(self):
            return None
        lay = self._centre.layout()
        h = self._centre.height() if self._centre.height() > 1 \
            else self.height()
        above, n = 0, 0
        for i in range(lay.count()):
            it = lay.itemAt(i)
            w = it.widget()
            if w is None or (w is not self.dock_frame
                             and not w.isVisibleTo(self)):
                continue
            n += 1
            if w not in (view, self.dock_frame):
                above += it.sizeHint().height()
        return h - above - lay.spacing() * max(0, n - 1) - VIEW_MIN

    # ── the chain hook (T8; GUI-9 builds the strip) ──────────────────────
    def set_chain_strip(self, widget=None):
        """Put `widget` - GUI-9's stage strip - in `chain_slot`, above the
        progress strip, and show it; None empties the slot and hides it
        at zero height. A widget taken out is unparented (and so
        hidden). Anything appearing above the view moves the embedded
        3D viewer: GUI-9 re-measures it (CLAUDE.md 8.7)."""
        lay = self.chain_slot.layout()
        was_hidden = self.chain_slot.isHidden()
        while lay.count():
            w = lay.takeAt(0).widget()
            if w is not None and w is not widget:
                w.setParent(None)
        if widget is None:
            self.chain_slot.setFixedHeight(0)
            self.chain_slot.hide()
            return
        if was_hidden:
            # GUI-9 T4: the strip takes its height (and one GAP) from the
            # view; with the embedded 3D viewer on screen, shrink its
            # window first, so it never stands below its card while the
            # layout catches up (D93's pattern, results_panel's stage
            # slot)
            self._shrink_viewer(
                max(widget.sizeHint().height(),
                    widget.minimumSizeHint().height()) + GAP)
        lay.addWidget(widget)
        self.chain_slot.setMinimumHeight(0)
        self.chain_slot.setMaximumHeight(QWIDGETSIZE_MAX)
        self.chain_slot.show()

    def _shrink_viewer(self, dh):
        """Shrink the embedded viewer's window by `dh` px now, when it is
        on screen - ahead of a layout change above it (CLAUDE.md 8.7)."""
        host = self.view3d
        shrink = getattr(host, 'shrink_ahead', None)
        if shrink is None or self._stack.currentWidget() is not host \
                or not host.isVisible():
            return
        shrink(dh)

    def chain_strip(self):
        """The widget in `chain_slot`, or None."""
        lay = self.chain_slot.layout()
        return lay.itemAt(0).widget() if lay.count() else None

    def column_widths(self):
        """(controls, centre, gauges) in px, as laid out (tests)."""
        return (self._ctrl.width(), self._centre.width(),
                self._gauge_col.width())

    # ── theme ────────────────────────────────────────────────────────────
    def _retheme(self, _mode=None):
        self.runs_browse.setIcon(theme.icon('folder', 15, color='text2'))
        self.run_btn.setIcon(_two_state_icon('play', 14, 'on_accent'))
        self.view3d_btn.setIcon(_two_state_icon('cube', 19, 'text2'))
        self.stop_btn.retint()
        self._path_mark.setPixmap(theme.pixmap('chevron_right', 13,
                                               color='faint'))
        self._style_setup_link()

    # ── run name ─────────────────────────────────────────────────────────
    def set_run_name(self, name, replace=False):
        """Pre-fill the run name when the box is empty; `replace` sets it
        regardless (Open case: the opened model, GUI QA C1)."""
        if replace or not self.run_name.text().strip():
            self.run_name.setText(str(name or ''))

    def current_run_name(self):
        return self.run_name.text().strip()

    # ── the runs folder (OUT-1) ──────────────────────────────────────────
    def current_runs_dir(self):
        return self.runs_dir.text().strip()

    def set_runs_dir(self, path):
        self.runs_dir.setText(str(path or ''))

    def _browse_runs_dir(self):
        from . import dialogs
        path = dialogs.pick_dir('Runs folder', self, self.current_runs_dir())
        if path:
            self.runs_dir.setText(os.path.normpath(path))
            self.runs_dir_changed.emit()

    def _update_path(self):
        """The resolved model folder under the boxes (display only; the
        Run pre-flight `MainWindow._model_target` is what decides)."""
        runs, model = self.current_runs_dir(), self.current_run_name()
        if runs and model:
            text = folder_for(runs, model).rstrip('\\/') + os.sep
        else:
            text = PATH_BLANK
        self._path_text = text
        # break after the separators, so a long path wraps in the column
        self._path_lbl.setText(text.replace(os.sep, os.sep + ZWSP))
        self._path_lbl.setToolTip(text)

    def path_text(self):
        """The resolved-folder line as the user reads it (tests)."""
        return self._path_text

    # ── readouts, for the QA harness and the e2e suites ──────────────────
    def chip_texts(self):
        """The readouts as {key: value} - the same five keys and value
        strings the stat chips had ('1234', '1.500', '2.50e-07',
        '345.7', '14'), so a test reads what the user reads instead of
        walking widgets."""
        return dict(self._readout)

    def paused_text(self):
        """What the run state says about a stepped run being held."""
        return self._paused_lbl.text()

    def _render_readouts(self):
        """The tiles from `_readout`: the value with its unit after it in
        a smaller muted face (board lines 168, 178), dt in STEP's
        caption."""
        r = self._readout
        muted = theme.cur('muted')

        def with_unit(value, unit):
            return unit_html(value, unit, muted)

        self._tile_time.set(with_unit(r['t [ms]'], 'ms'))
        self._tile_step.set(r['step'], f'dt {r["dt [s]"]} s')
        self._tile_pmax.set(with_unit(r['p max [kPa]'], 'kPa'))
        self._tile_cells.set(r['cells'])

    def _reset_readouts_text(self):
        self._readout = dict.fromkeys(CHIP_KEYS, '—')
        self._render_readouts()

    # ── live-view sub-tab switching ──────────────────────────────────────
    #: which widget each segment shows
    def _view_widget(self, value):
        return {'3D view': self.view3d,
                'Gauges': self.gauges}.get(value, self.pane)

    def _view_selected(self, value):
        self._stack.setCurrentWidget(self._view_widget(value))
        if value == 'Gauges' and self._pending_gauges is not None:
            self.gauges.set_payload(self._pending_gauges)
            self._pending_gauges = None
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
        """Walk Tab the way the screen reads: the controls column top to
        bottom, then the view's toolbar, then the dock - the log last.

        Qt's default is construction order, which put the log before the
        view controls here once (measured on the old one-column panel:
        Tab bounced across the window six times). The log stays in the
        chain rather than being taken out of it: it is read-only, but a
        keyboard user still needs to reach it to scroll and copy.
        """
        chain = [self.runs_dir, self.runs_browse, self.run_name,
                 self.stop_btn, self.run_btn, self.view3d_btn,
                 self.step_card.header, self.init_btn, *self._exec_btns,
                 self.refresh_val, self.refresh_mode, self.auto_clim,
                 self.clim_min, self.clim_max, self.setup_link,
                 self._view_seg, self.show_mesh,
                 *self.dock.focus_widgets(), self.log]
        for first, second in zip(chain, chain[1:]):
            QWidget.setTabOrder(first, second)

    def current_view(self):
        return '3D view' if self._stack.currentWidget() is self.view3d \
            else 'Live slice'

    # ── 0-D (HD 1.3) ─────────────────────────────────────────────────────
    def set_dim(self, dim):
        """Hide, never grey (plan §9), what an HD 1.3 assessment does not
        have: Step through, the Live view card, the 3D button and the
        Time / Step / p max tiles; and (GUI-11 T5, F12) the view toolbar
        and the live view, which one 0-D note replaces. Runs folder,
        Model, Run and the log stay."""
        self._dim = int(dim)
        blast = self._dim != 0
        for w in (self.step_card, self.live_card, self.view3d_btn,
                  self._tile_time, self._tile_step, self._tile_pmax,
                  self._view_bar, self._view_frame):
            w.setVisible(blast)
        self.hd13_note.setVisible(not blast)
        if not blast:
            self._tile_cells.hide()
        self.strip.arrange(force=True)

    # ── event handlers (called from the controller) ──────────────────────
    def set_running(self, running, paused=False, model=None, folder=None):
        """A run started (`paused`: held at step 0 by Initialise) or
        ended. Stop and Run swap places by visibility AND enablement, so
        a disabled Stop never reads as armed. At a start the Log pane's
        text is kept as an earlier run (named `model`, in `folder`;
        default: the Run screen's boxes) and the pane cleared."""
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
        self.run_btn.setVisible(not running)
        self.stop_btn.setEnabled(bool(running))
        self.stop_btn.setVisible(bool(running))
        # a disabled Stop used to stay danger-red, reading as armed
        set_button_kind(self.stop_btn, 'danger' if running else 'default')
        for b in self._exec_btns:
            b.setEnabled(bool(running))
        self.set_paused(False)
        if running:
            self.progress.setValue(0)
            self._frac = None
            self._ended = None
            self._end_reason = ''
            self.banner.hide()
            self.strip.pct_lbl.setText('0 %')
            self._amr_run = 0
            self._start_record(model, folder)
            # the live-gauge column: no series yet, the now line on
            self._col_from_run = True
            self.gauge_col.start_run()
            # Everything below belongs to the PREVIOUS run: the readouts
            # and the live plot used to keep its step/time/field until the
            # new run's first frame, which on a blastFoam cold start is
            # minutes of a stale picture (and, after Initialise Model, a
            # t = 0 plot beside the last run's step count).
            self._reset_readouts()
            if paused:
                # Initialise: the Exec buttons are what comes next
                self.step_card.set_open(True)
        else:
            # live attach only during a run; Results tab covers afterwards
            self.view3d_btn.setEnabled(False)
            # how it ended arrives with on_finished (mark_ended)
            self._ended = 'ended'
            self.dock.record_end()
            # the finished column: the full traces, no now line
            self.gauge_col.set_live(False)
        self._sync_run_text()
        self._sync_tick()
        self._render_time()

    def show_finish(self, model, reason, folder=None):
        """The finish banner (plan §6): `Result ready: <model> · <how it
        ended>. Files in <folder>\\`. `reason` is the last result's
        stop_reason verbatim (decision D66); the time line appends it."""
        reason = str(reason or '').strip() or 'finished'
        head = f'Result ready: {model} · {reason}.'
        where = (f"Files in {str(folder).rstrip('/' + os.sep)}{os.sep}"
                 if folder else '')
        self._banner_lines = (head, where)
        full = f'{head} {where}' if where else head
        self.banner.message.setToolTip(full)
        self._render_banner()
        if self.banner.isHidden():
            self._shrink_viewer_for_banner()
        self.banner.show()
        self._end_reason = reason
        self._render_time()

    def _render_banner(self):
        """Two lines that never wrap: the result and how it ended (elided
        at the right), then the folder (elided in the middle), each to
        the label's width; the whole text is the tooltip. A word-wrapped
        label cannot break a path, so the path set the centre column's
        minimum width and was clipped at 1100 x 720 (T9 screenshots)."""
        msg = self.banner.message
        head, where = self._banner_lines
        msg.ensurePolished()
        fm, w = msg.fontMetrics(), max(1, msg.contentsRect().width())
        lines = [fm.elidedText(head, Qt.ElideRight, w)]
        if where:
            lines.append(fm.elidedText(where, Qt.ElideMiddle, w))
        text = '\n'.join(lines)
        if msg.text() != text:
            msg.setText(text)

    def eventFilter(self, obj, event):
        if obj is self.banner.message and event.type() == QEvent.Resize:
            self._render_banner()
        elif obj is getattr(self, '_centre', None) \
                and event.type() == QEvent.LayoutRequest:
            self._fit_dock()
        return super().eventFilter(obj, event)

    def _banner_dh(self):
        """The height the banner takes from the view when it shows: its
        own two lines and one layout GAP."""
        b = self.banner
        return max(b.sizeHint().height(), b.minimumSizeHint().height()) + GAP

    def _shrink_viewer_for_banner(self):
        """The banner takes its height from the view. With the embedded
        3D viewer on screen, shrink its window first, so it never stands
        out of its card while the layout catches up (CLAUDE.md 8.7; T9
        measured 30 ms and 70 px without this)."""
        host = self.view3d
        shrink = getattr(host, 'shrink_ahead', None)
        if shrink is None or self._stack.currentWidget() is not host \
                or not host.isVisible():
            return
        shrink(self._banner_dh())

    def banner_text(self):
        """The banner's whole message, or '' while it is hidden (the
        label may show it elided; the tooltip has it whole)."""
        if self.banner.isHidden():
            return ''
        head, where = self._banner_lines
        return f'{head} {where}' if where else head

    def set_run_again(self, on=True):
        """A run has finished this session: the idle button reads `Run
        again` from now on (board Run_Finished line 94; decision row)."""
        self._run_again = bool(on)
        self._sync_run_text()

    def _sync_run_text(self):
        self.run_btn.setText('Run again' if self._run_again else 'Run')
        self.run_btn.setAccessibleName(self.run_btn.text())

    def _reset_readouts(self):
        """Readouts back to '-', live plot to a waiting placeholder, 3D
        view dropped: nothing on the Run screen may still describe the
        last run."""
        self._last_step = None
        self._tile_cells.hide()
        self.strip.arrange(force=True)
        self._reset_readouts_text()
        self._solid = None
        self._mesh_geom = None
        self._mesh_levels = None
        self._shape = None
        self.pane.show_placeholder()
        self.gauges.reset()
        self._pending_gauges = None
        try:
            self.view3d.reset()
        except Exception:
            pass

    def set_gauge_payload(self, payload):
        """The series so far, for the live-gauge column and the view's
        Gauges page. The page is drawn only while it is on screen; the
        newest payload waits for it otherwise (it holds every earlier
        one), so a hidden pyqtgraph plot is not redrawn every frame now
        that the column keeps collection on (decision D60)."""
        self.gauge_col.set_payload(payload)
        if self.watching_gauges():
            self.gauges.set_payload(payload)
            self._pending_gauges = None
        else:
            self._pending_gauges = payload

    def set_gauge_case(self, case):
        """The case of the stage now running: the column's Z, wall names
        and trigger gauge (the app's `_run_cases`)."""
        self.gauge_col.set_case(case)

    def set_setup_case(self, case):
        """The Setup screen's case: shown by the column (all `waiting`)
        until the first run of the session starts."""
        if not self._col_from_run:
            self.gauge_col.set_case(case)

    def set_final_gauges(self, gauges):
        """The last stage's Result.gauges: the full traces."""
        self.gauge_col.set_payload(gauges, final=True)

    def say_no_gauges(self, text=NO_GAUGES):
        """The case has no gauges (or, `ALL_DROPPED`, the solver drops
        every one), so the view has nothing to wait for."""
        self.gauges.reset(text)

    def set_validation(self, ok, n_errors=0, text=None, n_cells=None):
        """Mirror the Setup validation on the Run screen's Setup link and
        gate the start buttons, so an invalid case is visible here
        instead of only as a modal after pressing Run. `text` overrides
        the wording; `n_cells` is the report's cell count (hidden when
        None)."""
        self._case_ok = bool(ok)
        if ok:
            self._valid_lbl.setText(text or 'Case OK')
        else:
            n = max(int(n_errors), 1)
            self._valid_lbl.setText(
                text or f'{n} error{"s" if n != 1 else ""} - see Setup')
        self._n_cells = int(n_cells) if n_cells else None
        self.setup_link.cells.setText(
            f'· {fmt_count(self._n_cells)} cells' if self._n_cells else '')
        self.setup_link.cells.setVisible(self._n_cells is not None)
        self._style_setup_link()
        if not (self._running or self._busy):
            self.run_btn.setEnabled(bool(ok))
            self.init_btn.setEnabled(bool(ok))

    def setup_link_text(self):
        """The link as read: `Setup: Case OK · 368 k cells` (tests)."""
        bits = [self.setup_link.prefix.text(), self._valid_lbl.text()]
        if not self.setup_link.cells.isHidden():
            bits.append(self.setup_link.cells.text())
        return ' '.join(b for b in bits if b)

    def _style_setup_link(self):
        """ok_bg / ok_border when the case is OK, stop_* when it has
        errors (board line 149); the text stays >= 4.5:1 (D23)."""
        link = self.setup_link
        link.setProperty('state', 'ok' if self._case_ok else 'error')
        theme.repolish(link)
        fg = theme.cur('text2' if self._case_ok else 'stop_text')
        for lbl in (link.prefix, self._valid_lbl, link.cells):
            lbl.setStyleSheet(f'color: {fg}; font-size: 13px;')
        icon, colour = (('check', 'ok') if self._case_ok
                        else ('error', 'danger'))
        link.icon_lbl.setPixmap(theme.pixmap(icon, 16, color=colour))

    def set_busy(self, busy):
        """Mark a non-solve job (the HD 1.3 assessment) as working or done.

        Busy: Run and Initialise Model off, the bar indeterminate, the
        last run's finish banner hidden. The log and the readouts still
        describe the last solve, and the bar gets its old value back
        afterwards; the percent tile reads `—` during and after (an
        assessment has no fraction; GUI-11 T5, D206).
        """
        busy = bool(busy)
        if busy and not self._busy:
            self._bar_value = self.progress.value()
        was = self._busy
        self._busy = busy
        if busy:
            self.progress.setRange(0, 0)        # (0, 0) = indeterminate
            # no fraction to show (plan §6, last bullet)
            self.strip.pct_lbl.setText('—')
            self._ended = None
            # an assessment is a run start (D166): the last run's finish
            # banner goes (GUI-11 T5, D206)
            self.banner.hide()
        else:
            self.progress.setRange(0, 1000)
            self.progress.setValue(self._bar_value)
            # the assessment had no fraction; the tile must not go back
            # to the last blast run's percent (GUI-11 T5, UXR-8, D206)
            self.strip.pct_lbl.setText('—')
            if was:
                self._ended = 'hd13'
        self._sync_tick()
        self._render_time()
        # same gate as set_running / set_validation
        start_ok = (not self._running) and (not busy) and self._case_ok
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
        # the badge has a fill, so an empty one must not show
        self._paused_lbl.setVisible(bool(paused))
        self._render_time()

    # ── the run clock's line (T2, plan §6, UX-19) ────────────────────────
    def _sync_tick(self):
        """The 1 s refresh runs only while a run or an assessment is
        live, and stops when idle."""
        if self._running or self._busy:
            if not self._tick.isActive():
                self._tick.start()
        else:
            self._tick.stop()

    def mark_ended(self, how):
        """How the run that just stopped ended: 'done' | 'stopped' |
        'failed' | 'ended' (no result and no Stop: say only that it
        ended)."""
        self._ended = how
        self.dock.record_end(how)
        self._render_time()

    def time_text(self):
        """The line under the bar: elapsed and the ETA while running,
        the held step, how the last run ended - all run time from the
        clock, held time excluded."""
        c = self.clock
        el = fmt_duration(c.run_s())
        if self._busy:
            return f'HD 1.3 assessment · {el} elapsed'
        if self._running:
            if c.held():
                where = ('held' if self._last_step is None
                         else f'held at step {self._last_step}')
                return f'{where} · {el} elapsed'
            eta = c.eta_s(self._frac) if self._frac is not None else None
            if eta is None:
                return f'{el} elapsed'
            return f'{el} elapsed · about {fmt_duration(eta)} left'
        line = {'done': f'Done in {el}',
                'stopped': f'Stopped after {el}',
                'failed': f'Failed after {el}',
                'ended': f'Ended after {el}',
                'hd13': f'HD 1.3 assessment · done in {el}'}.get(
                    self._ended, '')
        # T7: how the run ended, as the banner says it
        if line and self._end_reason and self._ended in ('done',
                                                         'stopped'):
            line += f' · {self._end_reason}'
        return line

    def _render_time(self):
        text = self.time_text()
        if self.strip.time_lbl.text() != text:
            self.strip.time_lbl.setText(text)
            self.strip.time_lbl.setToolTip(text)

    def pct_text(self):
        """The percent as shown: `78 %`, or `—` (tests)."""
        return self.strip.pct_lbl.text()

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
        self._colour_last_line(line)
        self.log.verticalScrollBar().setValue(
            self.log.verticalScrollBar().maximum())

    #: G14U-P2b (D30): the log's severity tags and the palette key each takes
    _LOG_TAGS = (('[error]', 'error'), ('[warn]', 'warn'))

    def _colour_last_line(self, line):
        """Give the line just appended its severity colour - `[warn]` the
        theme's warn, `[error]` its error - as a character format on that
        block only. The text, so `log_text()` and a copy, is unchanged."""
        key = next((k for tag, k in self._LOG_TAGS if tag in line), None)
        if key is None:
            return
        cur = QTextCursor(self.log.document().lastBlock())
        cur.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(theme.cur(key)))
        cur.mergeCharFormat(fmt)

    def log_line_colours(self):
        """[(line, foreground name or None)] per log line (tests)."""
        out = []
        block = self.log.document().firstBlock()
        while block.isValid():
            colour = None
            it = block.begin()
            while not it.atEnd():
                fmt = it.fragment().charFormat()
                if fmt.hasProperty(QTextCharFormat.ForegroundBrush):
                    colour = fmt.foreground().color().name()
                    break
                it += 1
            out.append((block.text(), colour))
            block = block.next()
        return out

    def log_text(self):
        """The current run's log (earlier runs are in log_history())."""
        return self.log.toPlainText()

    # ── the dock: earlier runs and messages (T4, UX-18) ──────────────────
    def _start_record(self, model, folder):
        model = model or self.current_run_name()
        if folder is None and model and self.current_runs_dir():
            folder = folder_for(self.current_runs_dir(), model)
        self.dock.record_start(model, folder)

    def log_history(self):
        """This session's earlier runs, newest first: [dict(model,
        started, ended, how, text, folder)]."""
        return self.dock.history()

    def show_earlier(self, i):
        self.dock.show_earlier(i)

    def messages_text(self):
        return self.dock.messages_text()

    def add_message(self, level, text):
        """One notify() line for the Messages page."""
        self.dock.add_message(level, text)

    def _clear_log(self):
        self._amr_run = 0
        self.log.clear()

    def mark_complete(self):
        """Run reached its own end: fill the bar. The worker throttles
        progress messages to ~10 Hz, so the final one is usually dropped
        and the last frac this panel ever saw is short of 1.0."""
        self.progress.setValue(1000)
        self.strip.pct_lbl.setText('100 %')

    def on_progress(self, p):
        frac = max(0.0, min(1.0, p.frac))
        self.progress.setValue(int(round(1000 * frac)))
        self._frac = frac
        self.strip.pct_lbl.setText(f'{int(round(100 * frac))} %')
        self._last_step = p.step
        self._readout.update({
            'step': str(p.step),
            't [ms]': f'{p.t*1e3:.3f}',
            'dt [s]': f'{p.dt:.2e}',
            # kPa like every plot and colorbar (the chip used to be the
            # one readout in Pa, a 1000x mismatch against the live view)
            'p max [kPa]': f'{p.p_max / 1e3:,.4g}'})
        self._last_dt = float(p.dt)     # turns a step cadence into a time
        self._render_readouts()
        self._render_time()

    def on_run_started(self, info):
        # a chain stage: the fraction (and so the ETA) restarts, and the
        # bar and the percent tile with it - the last stage's 100 % must
        # not stand until this stage's first progress (F25)
        self._frac = None
        self.progress.setValue(0)
        self.strip.pct_lbl.setText('0 %')
        # ... and STEP / TIME / dt / P MAX read `—` until this stage's own
        # first progress, which the worker queues after this message
        # (GUI-10, F27 / D182). Only the texts: the live plot restarts
        # below and the 3D view is kept (_reset_readouts would drop both).
        self._reset_readouts_text()
        # a stage held at its first gate: the PAUSED badge and the time
        # line name no step of the last stage (F28, GUI-11 T7)
        self._last_step = None
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
        manual = not self.auto_clim.isChecked()
        self.clim_row.setVisible(manual)
        for ent in self._clim_entries:
            ent.setEnabled(manual)

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
        """Add/remove the cell-edge overlay per the Show mesh button."""
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
        if self._tile_cells.isHidden():
            self._tile_cells.show()
            self.strip.arrange(force=True)
        self._readout['cells'] = f'{n:,}'
        self._render_readouts()

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
