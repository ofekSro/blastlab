"""The Results tab (03 Results, board Results): browse the snapshots and
gauges of finished runs, replay recorded frames, drive the 3D viewer,
and export.

Three columns (docs/gui-redesign-plan.md section 7, batch
2026-09-29-gui-results): results + how it was computed (280 px) · the
centre (the view tabs over the sub-views) · export (320 px). The side
columns give way (to 248 and 288 px) only when the window cannot hold
the centre's minimum between them, as on the Run screen (D19).

Screen and file differ here by design. On screen the Fields view is ONE
large panel with selectors, because a persistent pyqtgraph image makes a
field change a single array upload. The `PNGs` and `Report` exports keep
writing the full multi-panel grid that `output/plots.py` builds, and
their tooltips say so.

The sub-views live in their own modules (`results_fields`,
`results_gauges`, `results_anim`), the list in `results_list`, the
method card's rows in `results_method` and the writing in `exports`, so
each is testable without building a window.
"""

import os
import threading

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QApplication, QBoxLayout, QDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from ..viz3d import MISSING_MSG, pyvista_available
from . import dialogs, exports, theme
from .bridge import ThreadBridge
from .export_column import DATA, FIGURES, ExportColumn, profile_suffix
from .results_anim import AnimView
from .results_fields import FieldsView
from .results_gauges import GaugesView
from .results_list import ElidedLabel, ResultsList
from .results_method import NO_CASE_TIP, case_source, method_rows
from .setup_tree import _letter_space
from .view3d_host import View3DHost
from .widgets import ScrollColumn, Segmented

#: longest label the picker shows in full; anything longer is elided
#: there and kept whole in the item's tooltip
PICKER_MAX = 34

#: the side columns (board Results lines 57 and 298) and how far they
#: give way on a narrow window (the Run screen's rule, D19)
LEFT_W, LEFT_MIN = 280, 248
RIGHT_W, RIGHT_MIN = 320, 288
#: the centre's padding (board line 96: 14 px top/bottom, 18 px sides)
CENTRE_PAD = (18, 14, 18, 14)
#: Qt's QWIDGETSIZE_MAX, to undo a setFixedHeight
QWIDGETSIZE_MAX = (1 << 24) - 1

#: (text, suffix, kind) for the export column, in the order they sit
#: (Data, then Figures). The kind stays 'gif' for the animation; the
#: writer follows whatever extension the dialog returns.
EXPORT_BUTTONS = tuple((text, suffix, kind)
                       for kind, text, suffix in DATA + FIGURES)

#: what each export writes, said once so the buttons are not a guess.
#: 'pngs' and 'report' are explicit that the file is NOT what is on
#: screen: the screen shows one field, the file the whole grid.
EXPORT_HELP = {
    'profile': 'Save the final state for a later stage to start from.',
    'gif': 'Write the recorded frames as a video, using the colour '
           'scale set in the Animation view.',
    'vtk': 'Convert the blastFoam case to VTK for ParaView.',
    'summary': 'Per-gauge peak, arrival, phase and impulse as CSV.',
    'tsv': 'The raw gauge time histories.',
    'fieldcsv': 'Every field map as a long-format CSV, one file per '
                'field.',
    'report': 'One self-contained HTML file: the FULL snapshot grid, '
              'the gauge table and the case, not just the panel on '
              'screen.',
    'pngs': 'The FULL multi-panel snapshot grid as PNGs, not just the '
            'single panel on screen.',
}

VIEWS = ('Fields', 'Gauges', 'Animation', '3D')


class ResultEntry:
    """One result in the list. `kind` is 'run', or 'chain' for a chain
    shown as one result with its `stages` (GUI-9 sets both)."""

    def __init__(self, label, dim, result, kind='run', stages=None):
        self.label = label
        self.display = label
        self.dim = dim
        self.result = result
        self.kind = kind
        self.stages = stages


def elide_middle(text, width=PICKER_MAX):
    """Elide the MIDDLE of a long label: the tail carries the dimension,
    the '(stopped)' note and the ' #2' de-duplication marker, all of
    which a trailing ellipsis would eat."""
    if len(text) <= width:
        return text
    keep = width - 1
    head, tail = (keep + 1) // 2, keep // 2
    return text[:head] + '…' + text[len(text) - tail:]


class _ViewStack(QStackedWidget):
    """The views, sized by the page on screen (setup_panel._PreviewStack's
    rule, D25): a plain QStackedWidget takes its LARGEST page as its
    minimum, so the 3D host would hold the centre at 376 px under every
    other view and push the side columns narrower than they need be."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(lambda _i: self.updateGeometry())

    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        return (w.minimumSizeHint() if w is not None
                else super().minimumSizeHint())


class CaseViewer(QDialog):
    """`Case as run · <name>`: the case file's text, read-only, with its
    path and a Copy button. Not modal, so no unattended driver can hang
    on it (batch risk 9)."""

    def __init__(self, path, name, parent=None):
        super().__init__(parent)
        self.setModal(False)
        self.setWindowTitle(f'Case as run · {name}')
        self.resize(640, 560)
        with open(path, 'rb') as f:
            self._text = f.read().decode('utf-8', 'replace')
        self.path = path
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        where = ElidedLabel(path)
        where.setObjectName('runpath')
        lay.addWidget(where)
        self.view = QPlainTextEdit()
        self.view.setObjectName('caseview')
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.view.setPlainText(self._text)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        self.copy_btn = QPushButton('Copy')
        self.copy_btn.setObjectName('runquiet')
        self.copy_btn.setToolTip('Copy the whole case file')
        self.copy_btn.clicked.connect(lambda *_: self.copy())
        row.addWidget(self.copy_btn)
        close = QPushButton('Close')
        close.setObjectName('runquiet')
        close.clicked.connect(lambda *_: self.close())
        row.addWidget(close)
        lay.addLayout(row)

    def text(self):
        """The file's bytes decoded as UTF-8, exactly as copied."""
        return self._text

    def copy(self):
        QApplication.clipboard().setText(self._text)


class MethodCard(QFrame):
    """HOW IT WAS COMPUTED (UX-15, board lines 78-91): the rows of
    `results_method.method_rows`, then Show case / Load into 01 Setup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('runcard')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(9)
        caps = QLabel('HOW IT WAS COMPUTED')
        caps.setObjectName('eyebrow')
        _letter_space(caps)
        self._caps = caps
        lay.addWidget(caps)
        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(7)
        self._grid.setColumnStretch(1, 1)
        lay.addLayout(self._grid)
        self._row_widgets = []
        self.none = QLabel('Select a result to see how it was computed.')
        self.none.setObjectName('methodkey')
        self.none.setWordWrap(True)
        lay.addWidget(self.none)
        # side by side (board line 87), one above the other when the
        # column has given way and the two no longer fit in a row
        btns = QBoxLayout(QBoxLayout.LeftToRight)
        btns.setContentsMargins(0, 4, 0, 0)
        btns.setSpacing(6)
        self.show_btn = QPushButton('Show case')
        self.show_btn.setObjectName('resquiet')
        self.show_btn.setCursor(Qt.PointingHandCursor)
        btns.addWidget(self.show_btn, 10)
        self.load_btn = QPushButton('Load into 01 Setup')
        self.load_btn.setObjectName('resquiet')
        self.load_btn.setCursor(Qt.PointingHandCursor)
        btns.addWidget(self.load_btn, 14)
        self._btns = btns
        lay.addLayout(btns)
        self._rows = []

    def _pair_need(self):
        return (self.show_btn.sizeHint().width()
                + self.load_btn.sizeHint().width() + self._btns.spacing())

    def minimumSizeHint(self):
        """The widest single button (or the caps), not the pair: the
        buttons stack when the pair does not fit."""
        s = super().minimumSizeHint()
        m = self.layout().contentsMargins()
        w = max(self.show_btn.sizeHint().width(),
                self.load_btn.sizeHint().width(),
                self._caps.sizeHint().width())
        return QSize(w + m.left() + m.right(), s.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange()

    def _arrange(self):
        m = self.layout().contentsMargins()
        room = self.width() - m.left() - m.right()
        d = (QBoxLayout.LeftToRight if room >= self._pair_need()
             else QBoxLayout.TopToBottom)
        if self._btns.direction() != d:
            self._btns.setDirection(d)
            self.updateGeometry()

    def buttons_stacked(self):
        return self._btns.direction() == QBoxLayout.TopToBottom

    def set_rows(self, rows):
        """[(label, value)] as `method_rows` gives them."""
        for w in self._row_widgets:
            self._grid.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._row_widgets = []
        self._rows = list(rows)
        for k, (key, val) in enumerate(self._rows):
            kl = QLabel(key)
            kl.setObjectName('methodkey')
            vl = ElidedLabel(val, Qt.ElideRight)
            vl.setObjectName('methodval')
            vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._grid.addWidget(kl, k, 0)
            self._grid.addWidget(vl, k, 1)
            self._row_widgets += [kl, vl]
        self.none.setVisible(not self._rows)

    def rows(self):
        return list(self._rows)

    def value_label(self, key):
        """The value widget of row `key`, or None (tests)."""
        for k, (name, _v) in enumerate(self._rows):
            if name == key:
                return self._row_widgets[2 * k + 1]
        return None


class ResultsPanel(QWidget):
    #: Load into 01 Setup: the case file's path (MainWindow loads it)
    load_case_requested = Signal(str)

    def __init__(self, viewer_link=None, log_fn=print, mode=None,
                 on_resume=None, bridge=None, parent=None):
        super().__init__(parent)
        self._entries = []
        self._log = log_fn
        self._on_resume = on_resume
        # the post-mortem loader runs on a worker thread and must not
        # touch a widget from there; without a bridge it falls back to
        # calling straight through, which is only safe in tests
        self._bridge = bridge if bridge is not None else ThreadBridge(self)
        self._run_browser = None
        self._case_viewer = None
        # a standalone panel (tests) shows everything; the app narrows
        # this the moment the solver mode arrives
        self._solver_mode = 'blastfoam'

        body = QHBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self._left = self._build_left()
        body.addWidget(self._left)
        self._centre = self._build_centre(viewer_link, log_fn)
        body.addWidget(self._centre, 1)
        self._right = self._build_right()
        body.addWidget(self._right)

        # every sub-view starts on its own "nothing yet" message rather
        # than on empty axes, which read as a result containing nothing
        self.clear_views()
        self._render_method(None)
        self._sync_export_buttons(None)
        if mode is not None:
            mode.subscribe(self.set_solver_mode)
            self.set_solver_mode(mode.get())

    # ── the left column: results + how it was computed (board 57-94) ─────
    def _build_left(self):
        frame = QFrame()
        frame.setObjectName('resleft')
        frame.setFixedWidth(LEFT_W)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.setSpacing(0)
        col = ScrollColumn(spacing=16)
        col.layout_.setContentsMargins(14, 16, 12, 16)
        col.setFocusPolicy(Qt.NoFocus)
        self._left_scroll = col
        fl.addWidget(col)

        self.sel = ResultsList()
        self.sel.currentIndexChanged.connect(lambda *_: self.refresh())
        col.add(self.sel)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._foam_runs_btn = QPushButton('Load a run…')
        self._foam_runs_btn.setObjectName('resbtn')
        self._foam_runs_btn.setIcon(theme.icon('folder', 14))
        self._foam_runs_btn.setIconSize(QSize(14, 14))
        self._foam_runs_btn._blastlab_icon = ('folder', 14, None)
        self._foam_runs_btn.setCursor(Qt.PointingHandCursor)
        self._foam_runs_btn.setMinimumWidth(0)
        self._foam_runs_btn.setToolTip(
            'Load a finished blastFoam run from the runs folder in WSL '
            '(the run browser)')
        self._foam_runs_btn.clicked.connect(
            lambda *_: self.open_run_browser())
        row.addWidget(self._foam_runs_btn, 1)
        self._remove_btn = QPushButton('✕')
        self._remove_btn.setObjectName('ressquare')
        self._remove_btn.setFixedSize(34, 34)
        self._remove_btn.setCursor(Qt.PointingHandCursor)
        self._remove_btn.setAccessibleName('Remove the selected result')
        self._remove_btn.clicked.connect(lambda *_: self.remove_current())
        # at the right end, also when Load a run… is hidden (native mode)
        row.addWidget(self._remove_btn, 0, Qt.AlignRight)
        col.add_layout(row)

        self.method = MethodCard()
        self.method.show_btn.clicked.connect(lambda *_: self.show_case())
        self.method.load_btn.clicked.connect(lambda *_: self._load_case())
        col.add(self.method)
        # the spare height goes under the method card (board line 92); the
        # list takes only what its rows need (ResultsList caps itself)
        col.add_stretch()
        self._path_lbl = ElidedLabel('')
        self._path_lbl.setObjectName('runpath')
        self._path_lbl.hide()
        col.add(self._path_lbl)
        return frame

    # ── the centre: stage hook, view tabs, the views (board 96-296) ──────
    def _build_centre(self, viewer_link, log_fn):
        centre = QWidget()
        centre.setMinimumWidth(0)
        cl = QVBoxLayout(centre)
        cl.setContentsMargins(*CENTRE_PAD)
        cl.setSpacing(12)
        # GUI-9 puts a chain's STAGE 1D | 2D | 3D strip here (board
        # Results_Chain lines 98-103) through set_stage_strip; hidden,
        # empty and zero-height until then (RunPanel.chain_slot's rule)
        self.stage_slot = QWidget()
        self.stage_slot.setObjectName('stageslot')
        ssl = QHBoxLayout(self.stage_slot)
        ssl.setContentsMargins(0, 0, 0, 0)
        ssl.setSpacing(0)
        self.stage_slot.setFixedHeight(0)
        self.stage_slot.setVisible(False)
        cl.addWidget(self.stage_slot)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(12)
        segframe = QFrame()
        segframe.setObjectName('resseg')
        sl = QHBoxLayout(segframe)
        sl.setContentsMargins(3, 2, 3, 2)
        sl.setSpacing(0)
        self.view_seg = Segmented(list(VIEWS), height=32, small=True)
        self.view_seg.changed.connect(self._view_selected)
        sl.addWidget(self.view_seg)
        self._seg_frame = segframe
        bar.addWidget(segframe)
        bar.addStretch(1)
        cl.addLayout(bar)

        view = QFrame()
        view.setObjectName('resview')
        vl = QVBoxLayout(view)
        vl.setContentsMargins(10, 10, 10, 10)
        vl.setSpacing(0)
        self.stack = _ViewStack()
        vl.addWidget(self.stack, 1)
        self.fields = FieldsView(on_change=self._mesh_changed)
        self.gauges = GaugesView()
        self.anim = AnimView()
        self.view3d = (View3DHost(viewer_link, 'results', log_fn=log_fn)
                       if viewer_link is not None else QWidget())
        self._views = {'Fields': self.fields, 'Gauges': self.gauges,
                       'Animation': self.anim, '3D': self.view3d}
        for w in self._views.values():
            self.stack.addWidget(w)
        self.view_seg.set('Fields')
        self.stack.setCurrentWidget(self.fields)
        self._view_frame = view
        cl.addWidget(view, 1)
        return centre

    # ── the right column: export (board 298-331, ui/export_column.py) ────
    def _build_right(self):
        col = ExportColumn(on_export=lambda k: self.export(k))
        col.setFixedWidth(RIGHT_W)
        self.export_col = col
        self._right_scroll = col.scroll
        self._export_btns = col.buttons
        # A line of the user's own ABOVE the automatic title, on every
        # figure this tab shows or exports. It belongs to this
        # presentation of a result, not to the case.
        self.title_box = col.title_box
        self.title_box.textChanged.connect(lambda *_: self._title_changed())
        self._view3d_btn = col.view3d_btn
        self._view3d_btn.clicked.connect(lambda *_: self.open_3d())
        #: kinds being written now: their buttons are busy strips (UX-13)
        self._busy = set()
        return col

    # ── layout: the side columns give way on a narrow window ─────────────
    def showEvent(self, event):
        super().showEvent(event)
        self._fit_columns()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_columns()

    def _fit_columns(self):
        """280 / centre / 320, the side columns giving way (to 248 and
        288, in proportion) only when the window cannot hold the centre's
        minimum between them (RunPanel._fit_columns' rule)."""
        w = self.width()
        if w <= 1:
            return
        centre_min = self._centre.minimumSizeHint().width()
        short = LEFT_W + RIGHT_W + centre_min - w
        left, right = LEFT_W, RIGHT_W
        if short > 0:
            room_l, room_r = LEFT_W - LEFT_MIN, RIGHT_W - RIGHT_MIN
            take_l = min(room_l, round(short * room_l / (room_l + room_r)))
            take_r = min(room_r, short - take_l)
            left, right = LEFT_W - take_l, RIGHT_W - take_r
        if self._left.width() != left or self._left.minimumWidth() != left:
            self._left.setFixedWidth(left)
        if self._right.width() != right \
                or self._right.minimumWidth() != right:
            self._right.setFixedWidth(right)

    def column_widths(self):
        """(left, centre, right) in px, as laid out (tests)."""
        return (self._left.width(), self._centre.width(),
                self._right.width())

    # ── the stage hook (GUI-9 builds the strip) ──────────────────────────
    def set_stage_strip(self, widget=None):
        """Put `widget` - GUI-9's STAGE 1D | 2D | 3D strip - in
        `stage_slot`, above the view tabs, and show it; None empties the
        slot and hides it at zero height. A widget taken out is
        unparented (and so hidden). Anything appearing above the view
        moves the embedded 3D viewer: GUI-9 re-measures it (CLAUDE.md
        8.7)."""
        lay = self.stage_slot.layout()
        was_hidden = self.stage_slot.isHidden()
        while lay.count():
            w = lay.takeAt(0).widget()
            if w is not None and w is not widget:
                w.setParent(None)
        if widget is None:
            self.stage_slot.setFixedHeight(0)
            self.stage_slot.hide()
            return
        if was_hidden:
            # the strip takes its height from the view: with the embedded
            # 3D viewer on screen, shrink its window first (D70's
            # shrink_ahead), so it never stands below its card while the
            # layout catches up (T4 sampler: 29 ms and 44 px without it)
            self._shrink_viewer(
                max(widget.sizeHint().height(),
                    widget.minimumSizeHint().height())
                + self._centre.layout().spacing())
        lay.addWidget(widget)
        self.stage_slot.setMinimumHeight(0)
        self.stage_slot.setMaximumHeight(QWIDGETSIZE_MAX)
        self.stage_slot.show()

    def _shrink_viewer(self, dh):
        """Shrink the embedded viewer's window by `dh` px now, when it is
        on screen - ahead of a layout change above it (CLAUDE.md 8.7)."""
        host = self.view3d
        shrink = getattr(host, 'shrink_ahead', None)
        if shrink is None or self.stack.currentWidget() is not host \
                or not host.isVisible():
            return
        shrink(dh)

    def stage_strip(self):
        """The widget in `stage_slot`, or None."""
        lay = self.stage_slot.layout()
        return lay.itemAt(0).widget() if lay.count() else None

    # ── entries ──────────────────────────────────────────────────────────
    def _unique_label(self, text):
        """Number a duplicate. The picker matched entries by their text,
        so two identical labels made the second unreachable - selecting
        it always returned the first, which is exactly what loading the
        same foam run twice did."""
        taken = {e.label for e in self._entries}
        if text not in taken:
            return text
        n = 2
        while f'{text} #{n}' in taken:
            n += 1
        return f'{text} #{n}'

    def _repopulate(self, keep=None):
        """Rebuild the list, the entry itself in each item's data so
        `current()` never has to match on text."""
        taken = set()
        self.sel.blockSignals(True)
        self.sel.clear()
        for ent in self._entries:
            d, n = elide_middle(ent.label), 2
            base = d
            while d in taken:
                d = f'{base} ({n})'
                n += 1
            taken.add(d)
            ent.display = d
            self.sel.addItem(d, ent)
            if d != ent.label:
                self.sel.setItemData(self.sel.count() - 1, ent.label,
                                     Qt.ToolTipRole)
        if self._entries:
            idx = (self._entries.index(keep) if keep in self._entries
                   else len(self._entries) - 1)
            self.sel.setCurrentIndex(idx)
        self.sel.blockSignals(False)

    def add_result(self, text, dim, result):
        ent = ResultEntry(self._unique_label(text), dim, result)
        self._entries.append(ent)
        self._repopulate(keep=ent)
        self.refresh()
        return ent

    def entries(self):
        return list(self._entries)

    def current(self):
        return self.sel.currentData()

    def remove_current(self):
        """Drop the selected result. They used to accumulate for a whole
        session with no way to free their frames."""
        ent = self.current()
        if ent is None:
            self._log('Remove: select a result first.')
            return
        self.anim.stop_play()
        self._entries.remove(ent)
        self._repopulate()
        if self._entries:
            self.refresh()
        else:
            self.clear_views()
            self._render_method(None)
        self._log(f'Removed result: {ent.label}')

    def clear_views(self):
        self.fields.clear()
        self.gauges.clear()
        self.anim.placeholder(self.anim.NO_RESULT)
        if isinstance(self.view3d, View3DHost):
            self.view3d.cancel_feed()
        self._sync_export_buttons(None)

    # ── views ────────────────────────────────────────────────────────────
    def _view_selected(self, value):
        w = self._views.get(value)
        if w is not None:
            self.stack.setCurrentWidget(w)
            # the stack is sized by its page (_ViewStack)
            self._fit_columns()

    def show_view(self, name):
        """Switch sub-view programmatically (the QA harness uses this)."""
        self.view_seg.set(name)
        self._view_selected(name)

    def view(self):
        return self.view_seg.get()

    def title_extra(self):
        return self.title_box.text().strip() or None

    def _title_changed(self):
        extra = self.title_extra()
        for v in (self.fields, self.gauges, self.anim):
            v.set_title_extra(extra)
        # retitle only what is on screen; the animation stays on the
        # frame it is showing - retyping a title must not jump the
        # replay back to the start
        view = self.view()
        if view == 'Fields':
            self.fields.redraw()
        elif view == 'Gauges':
            self.gauges.redraw()
        elif view == 'Animation':
            self.anim.show_frame(self.anim.frame())

    def _mesh_changed(self):
        self.anim.set_show_mesh(self.fields.show_mesh.isChecked())

    def refresh(self):
        ent = self.current()
        self._render_method(ent)
        if ent is None:
            # a picker that matches nothing used to leave the export row
            # exactly as the previous result had left it, so every button
            # stayed enabled and did nothing when pressed
            self._sync_export_buttons(None)
            return
        self.anim.stop_play()
        self._sync_export_buttons(ent)
        extra = self.title_extra()
        for v in (self.fields, self.gauges, self.anim):
            v.set_title_extra(extra)
        self.fields.set_result(ent)
        self.gauges.set_result(ent)
        self.anim.set_result(
            ent, show_mesh=self.fields.show_mesh.isChecked())

    # ── how it was computed (UX-15) ──────────────────────────────────────
    def _render_method(self, ent):
        res = getattr(ent, 'result', None)
        self.method.set_rows(method_rows(res, ent.dim) if ent else [])
        src = case_source(ent) if ent is not None else None
        tip = (NO_CASE_TIP if ent is not None
               else 'Select a result first.')
        for b, good in ((self.method.show_btn,
                         'Show the case file this result was run from, '
                         'read-only'),
                        (self.method.load_btn,
                         'Load this case into 01 Setup as a new, unsaved '
                         'case (the model folder is never written)')):
            b.setEnabled(src is not None)
            b.setToolTip(good if src is not None else tip)
        home = ((getattr(res, 'meta', None) or {}).get('model_dir')
                if res is not None else None)
        self._path_lbl.setText(str(home or ''))
        self._path_lbl.set_tip(str(home) if home else None)
        self._path_lbl.setVisible(bool(home))
        self._remove_btn.setToolTip(
            f'Remove {ent.label} from the list' if ent is not None
            else 'Select a result first.')

    def method_rows(self):
        """The rows the method card shows (tests)."""
        return self.method.rows()

    def show_case(self):
        """Open the non-modal `Case as run` viewer for the selected
        result. Returns it, or None when there is no case file."""
        ent = self.current()
        path = case_source(ent) if ent is not None else None
        if not path:
            return None
        try:
            viewer = CaseViewer(path, ent.label, self)
        except OSError as exc:
            self._log(f'Show case: could not read {path}: {exc}')
            return None
        if self._case_viewer is not None:
            self._case_viewer.close()
            self._case_viewer.deleteLater()
        self._case_viewer = viewer
        viewer.show()
        return viewer

    def _load_case(self):
        ent = self.current()
        path = case_source(ent) if ent is not None else None
        if path:
            self.load_case_requested.emit(path)

    # ── solver mode and the export row ───────────────────────────────────
    def set_solver_mode(self, m):
        """Hide the blastFoam-only launchers in native mode. Per-result
        gating of the VTK button is unchanged - configuring a hidden
        button is harmless, and a post-mortem load still works in native
        mode; only the launcher is out of the way."""
        self._solver_mode = m
        foam = (m == 'blastfoam')
        self._foam_runs_btn.setVisible(foam)
        self.export_col.items['vtk'].set_mode_hidden(not foam)

    def _sync_export_buttons(self, ent):
        """Only offer an export that can actually run for this result.
        Every button used to stay enabled: with nothing selected they
        were silent no-ops, and Profile on a planar 2D result opened a
        file dialog and then failed in the log."""
        for kind, b in self._export_btns.items():
            good = exports.can(kind, ent)
            b.setEnabled(bool(good))
            # a greyed button has to say why; a VTK button that opens the
            # run's own vtk\ folder says where it is (GUI QA F2)
            tip = exports.vtk_tip(ent) if kind == 'vtk' else ''
            b.setToolTip(tip or (EXPORT_HELP.get(kind, '') if good
                                 else exports.why_not(kind, ent)))
        self.export_col.items['profile'].set_suffix(
            profile_suffix(ent.dim if ent is not None else None))
        good, tip = self._view3d_state(ent)
        self._view3d_btn.setEnabled(good)
        self._view3d_btn.setToolTip(tip)

    def _view3d_state(self, ent):
        """(enabled, tooltip) of Open the 3D viewer: a 3D result with
        snapshots, pyvista present and a viewer link; else why not."""
        if ent is None:
            return False, 'Select a result first.'
        if ent.dim != 3:
            return False, '3D results only.'
        if not pyvista_available():
            return False, MISSING_MSG
        if not ent.result.snapshots:
            return False, 'This result has no snapshots.'
        if not isinstance(self.view3d, View3DHost):
            return False, 'No viewer link in this panel.'
        return True, 'Show this result in the embedded 3D viewer'

    def export_enabled(self, kind):
        return self._export_btns[kind].isEnabled()

    # ── exports ──────────────────────────────────────────────────────────
    def export_opts(self):
        opts = dict(show_mesh=bool(self.fields.show_mesh.isChecked()),
                    title_extra=self.title_extra())
        opts.update(self.anim.export_opts())
        return opts

    def export(self, kind, threaded=True):
        """Write export `kind` of the selected result. Threaded (the
        buttons), its button becomes a busy strip once a target is chosen
        and until the writer is done; the same kind cannot start twice
        meanwhile, other kinds can, and Remove still works (the worker
        holds its own references). Returns the target, or ''."""
        if kind in self._busy:
            item = self.export_col.items.get(kind)
            self._log(f'{item.text() if item else kind} is already being '
                      f'written.')
            return ''
        done = ((lambda _ret, k=kind: self._bridge.post(self._export_done,
                                                        k))
                if threaded else None)
        target = exports.export(
            kind, self.current(), self.export_opts(), log=self._log,
            parent=self, on_error=self._post_error, threaded=threaded,
            on_done=done)
        # after pick_target returned a path: a cancelled dialog shows
        # nothing. The done call is queued to this thread, so it cannot
        # overtake this line.
        if target and threaded:
            self._set_busy(kind, True)
        return target

    def _set_busy(self, kind, on):
        item = self.export_col.items.get(kind)
        if on:
            self._busy.add(kind)
        else:
            self._busy.discard(kind)
        if item is not None:
            item.set_busy(on)

    def busy_kinds(self):
        return set(self._busy)

    def _export_done(self, kind):
        """On the GUI thread (posted by the worker): the button back, its
        enablement re-read for the result now selected."""
        self._set_busy(kind, False)
        self._sync_export_buttons(self.current())

    def _post_error(self, title, text):
        """`run_export`'s on_error, called on the worker (a VTK failure):
        the dialog is shown on the GUI thread."""
        self._bridge.post(self._show_error, title, text)

    def _show_error(self, title, text):
        dialogs.show_error(title, text, self)

    # ── the embedded 3D viewer ───────────────────────────────────────────
    def open_3d(self):
        ent = self.current()
        if ent is None:
            return
        if ent.dim != 3:
            self._log('3D Viewer: select a 3D result.')
            return
        if not pyvista_available():
            self._log(MISSING_MSG)
            return
        if not ent.result.snapshots:
            self._log('3D Viewer: this result has no snapshots.')
            return
        if not isinstance(self.view3d, View3DHost):
            self._log('3D Viewer: no viewer link in this panel.')
            return
        try:
            if self.view3d.feed_result(ent.result):
                self.show_view('3D')
                self._log(f'3D view loaded: {ent.label} '
                          f'({len(ent.result.snapshots)} snapshots)')
        except Exception as exc:
            self._log(f'3D view failed: {exc}')

    # ── post-mortem load of a finished blastFoam case dir ────────────────
    def open_run_browser(self):
        from .run_browser import FoamRunBrowser
        win = self._run_browser
        if win is not None and win.isVisible():
            win.raise_()
            win.activateWindow()
            win.refresh()
            return win
        self._run_browser = FoamRunBrowser(
            self, on_load=self.load_foam_run_path, log=self._log,
            on_resume=self._on_resume, bridge=self._bridge)
        self._run_browser.show()
        return self._run_browser

    def load_foam_run_path(self, path):
        """Post-mortem load of one run dir (UNC / posix / bare name) off
        the GUI thread, then add it to the results list."""
        if not path:
            return
        self._log(f'Loading foam run {path} ...')

        def work():
            try:
                from ..solvers.foam.postmortem import load_run
                res = load_run(path)
            except Exception as exc:
                self._log(f'Load failed: {exc}')
                return
            # OUT-2 P11: the run's VTK export deleted written times
            if res.meta.get('vtk_deleted_note'):
                self._log(res.meta['vtk_deleted_note'].strip())
            dim = 1 if 'radius_m' in res.meta else (
                3 if 'z_c' in res.meta else 2)
            name = (str(res.meta.get('name') or '').strip()
                    or os.path.basename(str(path).rstrip('/' + os.sep)))
            res.meta.setdefault('name', name)
            text = f'{name} (loaded, {dim}D)'
            # widgets only on the GUI thread
            self._bridge.post(self.add_result, text, dim, res)
            self._log(f'Loaded: {text} ({len(res.snapshots)} snapshots)')

        threading.Thread(target=work, daemon=True).start()

    def shutdown(self):
        self.anim.stop_play()
        if isinstance(self.view3d, View3DHost):
            self.view3d.shutdown()
        if self._case_viewer is not None:
            self._case_viewer.close()
