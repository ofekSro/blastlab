"""The Setup tab: dimension selector, the three case forms, the
validation card and the live model preview."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QScrollArea,
                               QSizePolicy, QStackedWidget, QVBoxLayout,
                               QWidget)

from ..core import mode as mode_mod
from ..viz3d import MISSING_MSG, pyvista_available
from . import theme
from .case_form import CaseForm
from .preview_panel import Preview1D, Preview2D, Preview3DBridge
from .theme import GAP, PAD
from .widgets import Card, Segmented, label

#: a long report (AMR + zones + foam notes can be eight lines) used to
#: grow the card until the form above it had a third of its height, so
#: the report area is a fixed height and scrolls.
#:
#: 104 came from the Tk widget's metrics and was too small here: it left
#: a 54 px viewport, about two wrapped lines, while a plain blastFoam 2D
#: case already reports six rows needing 367 px. 132 shows five or six
#: lines, which covers the ordinary case without eating the form.
STATUS_MAX_H = 132

#: icon + palette key per report severity
_ROW_STYLE = {'error': ('error', 'error'), 'warn': ('warning', 'warn'),
              'note': ('info', 'muted'), 'ok': ('check', 'ok')}


class SetupPanel(QWidget):
    """Dimension selector + the three CaseForms + validation card, with
    a live model preview on the right."""

    PREV_HINT = 'Enter a valid case to preview the model here.'

    dim_changed = Signal(int)

    def __init__(self, on_change=None, mode=None, viewer_link=None,
                 log_fn=print, parent=None):
        super().__init__(parent)
        self._on_change = on_change or (lambda: None)
        # the app-level solver mode (T34); a private one when the panel is
        # built standalone (tests)
        self._mode = mode if mode is not None else mode_mod.SolverMode()
        self._log = log_fn
        self._last_case = None
        self._report = []            # (severity, message) as shown

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(PAD - 4)

        head = QHBoxLayout()
        head.addWidget(label('Case Setup', 'h1'))
        head.addStretch(1)
        self.dim_seg = Segmented(['1D', '2D', '3D'], height=34)
        self.dim_seg.setFixedWidth(180)
        self.dim_seg.changed.connect(self._dim_selected)
        head.addWidget(self.dim_seg)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(GAP)
        root.addLayout(body, 1)

        # left: the scrollable form column over the status card. The form
        # column carries two cards of label+input side by side and is the
        # one that runs out of room first, so it gets the wider share.
        left = QVBoxLayout()
        left.setSpacing(GAP)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._stack = QStackedWidget()
        self._scroll.setWidget(self._stack)
        left.addWidget(self._scroll, 1)

        self._status_card = Card(pad=12)
        self._status_card.setSizePolicy(QSizePolicy.Preferred,
                                        QSizePolicy.Fixed)
        self._status_scroll = QScrollArea()
        self._status_scroll.setWidgetResizable(True)
        self._status_scroll.setFrameShape(QScrollArea.NoFrame)
        # a MAXIMUM alone was not enough. The card is vertically Fixed,
        # so it took the scroll area's own small sizeHint instead of the
        # cap: measured 54 px of viewport against a 367 px report, i.e.
        # 85 % of what validation had to say was hidden behind a 175 px
        # scrollbar. Pin the height so the space is actually reserved.
        self._status_scroll.setMinimumHeight(STATUS_MAX_H)
        self._status_scroll.setMaximumHeight(STATUS_MAX_H)
        self._status_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff)
        self._status_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded)
        self._status_body = QWidget()
        self._status_lay = QVBoxLayout(self._status_body)
        self._status_lay.setContentsMargins(0, 0, 0, 0)
        self._status_lay.setSpacing(1)
        self._status_lay.addStretch(1)
        self._status_scroll.setWidget(self._status_body)
        self._status_card.add(self._status_scroll)
        left.addWidget(self._status_card)
        holder = QWidget()
        holder.setLayout(left)
        # The stretch barely matters: the preview card has its own
        # minimum (measured 366 px at every window size), so the form
        # gets whatever is left. Two columns fit at 1280 because
        # fieldform.CARD_PAD is 12, not 16 - see COL_MIN there.
        body.addWidget(holder, 13)

        # right: the preview card
        prev = Card('Model Preview', pad=12)
        pv = prev.body_layout
        self.show_mesh = QCheckBox('Show mesh')
        self.show_mesh.toggled.connect(self._mesh_toggled)
        pv.addWidget(self.show_mesh)
        self._prev_stack = QStackedWidget()
        pv.addWidget(self._prev_stack, 1)
        self._prev_msg = label(self.PREV_HINT, 'muted', wrap=True,
                               align=Qt.AlignCenter)
        self._prev_stack.addWidget(self._prev_msg)
        self.preview1d = Preview1D()
        self.preview2d = Preview2D()
        self._prev_stack.addWidget(self.preview1d)
        self._prev_stack.addWidget(self.preview2d)
        self.view3d = None
        self.preview3d = None
        if viewer_link is not None and pyvista_available():
            from .view3d_host import View3DHost
            self.view3d = View3DHost(viewer_link, 'setup', log_fn=log_fn)
            self.view3d.set_controls_collapsed(True)
            self._prev_stack.addWidget(self.view3d)
            self.preview3d = Preview3DBridge(self.view3d, log_fn=log_fn)
        self._prev_stack.setCurrentWidget(self._prev_msg)
        body.addWidget(prev, 7)

        self._forms = {d: CaseForm(d, on_change=self._changed,
                                   mode=self._mode.get())
                       for d in (1, 2, 3)}
        for f in self._forms.values():
            self._stack.addWidget(f)
        self._dim = 2
        self.dim_seg.set('2D')
        self._stack.setCurrentWidget(self._forms[2])
        self._mode.subscribe(self._mode_changed)
        self.show_report()

    # ── solver mode / dimension ──────────────────────────────────────────
    @property
    def solver(self):
        return self._mode.get()

    def _mode_changed(self, m):
        for f in self._forms.values():
            f.set_mode(m)
        # cards vanished: a viewport left past the new end would show
        # nothing, so go back to the top
        self._scroll.verticalScrollBar().setValue(0)
        self._changed()

    @property
    def dim(self):
        return self._dim

    def _dim_selected(self, value):
        self.set_dim(int(str(value)[0]))

    def set_dim(self, dim):
        dim = int(dim)
        if dim not in self._forms:
            return
        self._dim = dim
        self.dim_seg.set(f'{dim}D')
        self._stack.setCurrentWidget(self._forms[dim])
        self.dim_changed.emit(dim)
        self._changed()

    def _changed(self):
        self._on_change()

    # ── the active form ──────────────────────────────────────────────────
    @property
    def form(self):
        return self._forms[self._dim]

    @property
    def forms(self):
        return dict(self._forms)

    def get_case(self):
        return self.form.get_case()

    def set_case(self, case):
        # the case's solver becomes the app mode (sidebar, Chain presets,
        # Results) BEFORE the form is filled, so the amr_levels trace and
        # the hide/show logic see the right mode
        self._mode.set(getattr(case, 'solver', 'native'))
        self.set_dim(case.dim)
        self.form.set_case(case)

    # ── validation report ────────────────────────────────────────────────
    def show_report(self, errors=(), warnings=(), notes=()):
        rows = ([('error', m) for m in errors]
                + [('warn', m) for m in warnings]
                + [('note', m) for m in notes])
        if not rows:
            rows = [('ok', 'Case OK')]
        self._report = list(rows)
        lay = self._status_lay
        while lay.count() > 1:                  # keep the trailing stretch
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for i, (severity, message) in enumerate(rows):
            icon_name, colour = _ROW_STYLE[severity]
            row = QWidget()
            row.setProperty('severity', severity)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)
            pic = label('')
            pic.setFixedWidth(18)
            pic.setPixmap(theme.pixmap(icon_name, 13,
                                       color=theme.DARK[colour]))
            rl.addWidget(pic, 0, Qt.AlignTop)
            text = label(str(message), 'body', wrap=True)
            text.setStyleSheet(f'color: {theme.cur(colour)};')
            rl.addWidget(text, 1)
            lay.insertWidget(i, row)

    def report_rows(self):
        """(severity, message) per row, as shown - the QA harness reads
        the report through this instead of walking widgets."""
        return list(self._report)

    # ── preview ──────────────────────────────────────────────────────────
    def update_preview(self, case):
        """Refresh the model preview (a parsed Case, or None when the
        form does not parse - the last good preview is kept). Called
        through the window's debounce."""
        if case is None:
            # the form does not parse: keep the last good preview rather
            # than blanking the pane on every keystroke
            return
        self._last_case = case
        show_mesh = self.show_mesh.isChecked()
        if case.dim == 1:
            # T59: the spherical sector blastFoam actually meshes, with
            # the charge radius inside it
            self.preview1d.show_case(case, show_mesh=show_mesh)
            self._prev_stack.setCurrentWidget(self.preview1d)
        elif case.dim == 2:
            self.preview2d.show_case(case, show_mesh=show_mesh)
            self._prev_stack.setCurrentWidget(self.preview2d)
        elif case.dim == 3:
            if self.preview3d is None:
                self._prev_msg.setText(MISSING_MSG)
                self._prev_stack.setCurrentWidget(self._prev_msg)
                return
            self.preview3d.show_case(case, show_mesh=show_mesh)
            self._prev_stack.setCurrentWidget(self.view3d)
        else:
            self._prev_msg.setText(self.PREV_HINT)
            self._prev_stack.setCurrentWidget(self._prev_msg)

    def _mesh_toggled(self, _on=None):
        if self._last_case is not None:
            self.update_preview(self._last_case)

    def preview_kind(self):
        """'1d' | '2d' | '3d' | 'hint' - which preview is on screen."""
        w = self._prev_stack.currentWidget()
        if w is self.preview1d:
            return '1d'
        if w is self.preview2d:
            return '2d'
        if self.view3d is not None and w is self.view3d:
            return '3d'
        return 'hint'

    def scroll_form(self, frac):
        """Scroll the form column to a fraction of its range (the QA
        harness screenshots the bottom cards)."""
        bar = self._scroll.verticalScrollBar()
        bar.setValue(int(round(bar.maximum() * max(0.0, min(1.0, frac)))))
        return bar.value()

    def release_preview(self):
        """Give the viewer child's window back (leaving the tab)."""
        if self.preview3d is not None:
            self.preview3d.clear()
