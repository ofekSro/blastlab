"""GUI-9 (plan §8.1, board Chain lines 98-217): one Chain stage's editor
in the 01 Setup layout - the stage tree, the centre (header numbers and
the model preview) and the properties column.

Built from the Setup's own parts: `SetupTree`, `CaseForm(placement=
'nodes')`, `DerivedCard`, `Preview1D` / `Preview2D` with a `ModelOverlay`,
`setup_strip.tiles` for the numbers, `HandoffCard` for the hand-offs.
`ChainPanel` owns the behaviour (routes, checks, seeding); this widget
lays a stage out and shows what the panel's live check found.

A `00 Stage` node comes first: the stage's solver, its hand-offs, its
checks and where the files go (decision D-row: the stage-level cards on
their own node, so a node's cards keep the column at 1100 x 720). A 3D
stage shows no preview here - the viewer child is not embedded a fourth
time (CLAUDE.md §8.7; decision D-row).
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

from ..core import mode as mode_mod
from . import chain_route, setup_nodes, setup_strip, theme
from .case_form import CaseForm
from .components import HandoffCard
from .model_overlay import ModelOverlay, hover_text, plane_caption
from .preview_panel import Preview1D, Preview2D
from .results_list import ElidedLabel
from .setup_panel import (PROPS_PAD, PROPS_W, WHEEL_ZOOM, DerivedCard,
                          _tool_button, pill_text)
from .setup_tree import TREE_MIN, SetupTree, _letter_space
from .theme import GAP
from .widgets import ZWSP, Card, Segmented, clean_copy, label

#: the stage tree's width (board Chain line 100)
TREE_W = 272

#: the 00 Stage node
STAGE_NODE = 'stage'
STAGE_TITLE = 'Stage'

#: a 3D stage's centre (decision D-row: no fourth viewer embedding)
HINT_3D = ('The 3D model view runs in its own window and is shown in 01 '
           'Setup. This stage\'s numbers are above; its checks are on 00 '
           'Stage.')

SOLVER_SUB = 'Preset from the solver switch; override per stage.'
COPY_TEXT = 'Copy from 01 Setup'
LOAD_TEXT = 'Load case…'

#: icon + palette key per check severity (the Setup's Checks rows)
_ROW_STYLE = {'error': ('error', 'error'), 'warn': ('warning', 'warn'),
              'note': ('info', 'muted'), 'ok': ('check', 'ok')}

#: the point list a tree child row leads to
_CHILD_LIST = {'gauges': 'gauges', 'structure': 'obstacles'}


def header_numbers(tiles):
    """`cells · ranks · GB` from `setup_strip.tiles` (the one source of
    those numbers): the tiles that are shown, in strip order."""
    bits = []
    t = tiles.get('cells')
    if t is not None:
        bits.append(f'{t.value} cells')
    t = tiles.get('ranks')
    if t is not None:
        bits.append(f'{t.value} rank{"" if t.value == "1" else "s"}')
    t = tiles.get('memory')
    if t is not None:
        bits.append(f'{t.value} {t.unit}')
    return ' · '.join(bits)


class StageEditor(QWidget):
    """Tree · centre · properties for Chain stage `dim`. Signals:
    `solver_picked(mode)` on a click of the stage's solver switch,
    `copy_clicked()`, `load_clicked()`."""

    solver_picked = Signal(str)
    copy_clicked = Signal()
    load_clicked = Signal()

    def __init__(self, dim, mode, on_change=None, parent=None):
        super().__init__(parent)
        self.dim = int(dim)
        self._node = None
        self._shown_once = False
        self._case = None            # the wired case last shown
        self._pending_preview = None
        self._number = '01'
        self._title = chain_route.stage_title(self.dim)

        body = QHBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(GAP)

        # ── left: the stage tree ─────────────────────────────────────────
        self.tree = SetupTree()
        self.tree.setMaximumWidth(TREE_W)
        self.tree.set_adds_visible(False, False)
        self.tree.node_clicked.connect(self.select_node)
        self.tree.child_clicked.connect(self._child_clicked)
        self.tree.pill_clicked.connect(
            lambda: self.select_node(STAGE_NODE))
        # the board's 40 px pill (theme: `#casepill[chain="true"]`)
        self.tree.pill.setProperty('chain', 'true')
        theme.repolish(self.tree.pill)
        foot = QWidget()
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        self.copy_btn = QPushButton(COPY_TEXT)
        self.load_btn = QPushButton(LOAD_TEXT)
        for b, stretch in ((self.copy_btn, 13), (self.load_btn, 10)):
            b.setObjectName('stagebtn')
            b.setFixedHeight(36)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumWidth(0)
            b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            fl.addWidget(b, stretch)
        self.copy_btn.clicked.connect(lambda *_: self.copy_clicked.emit())
        self.load_btn.clicked.connect(lambda *_: self.load_clicked.emit())
        self.load_btn.setToolTip('Fill this stage from a saved case file '
                                 'of the same dimension')
        self.tree.add_footer(foot)
        body.addWidget(self.tree)

        # ── centre: header numbers and the model preview ─────────────────
        self.view_card = Card(pad=12)
        pv = self.view_card.body_layout
        # two lines (decision D-row): the title and the numbers, then the
        # Setup's own toolbar line - the plane caption / hover readout and
        # Z rings · Mesh · Fit. On one line (the board) the 440 px centre
        # of a 1100 x 720 window left the caption no room at all.
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        self.view_title = QLabel(self._title)
        self.view_title.setObjectName('stageviewtitle')
        head.addWidget(self.view_title)
        head.addStretch(1)
        self.numbers = ElidedLabel('', mode=Qt.ElideRight)
        self.numbers.setObjectName('stagenumbers')
        self.numbers.setSizePolicy(QSizePolicy.Preferred,
                                   QSizePolicy.Preferred)
        head.addWidget(self.numbers)
        pv.addLayout(head)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)
        self._view_caption = ElidedLabel('', mode=Qt.ElideRight)
        self._view_caption.setObjectName('viewcaption')
        bar.addWidget(self._view_caption, 1)
        self.z_rings = _tool_button('Z rings', checkable=True,
                                    tip='Dashed rings at Z = 1, 2, 3 '
                                        'around the burst point '
                                        '(Z = R / W^1/3)')
        self.z_rings.setChecked(True)
        self.z_rings.toggled.connect(self._rings_toggled)
        self.show_mesh = _tool_button('Mesh', checkable=True,
                                      tip='Show the cells the run will use')
        self.show_mesh.toggled.connect(lambda _on: self._redraw())
        self.fit_btn = _tool_button('', tip='Fit the whole domain')
        self.fit_btn.setFixedWidth(28)
        self.fit_btn.setAccessibleName('Fit to view')
        self.fit_btn.setIcon(theme.icon('fit', 15, color='muted'))
        self.fit_btn.clicked.connect(lambda *_: self.fit_view())
        for b in (self.z_rings, self.show_mesh, self.fit_btn):
            bar.addWidget(b)
        pv.addLayout(bar)
        self._overlay = ModelOverlay()
        self.preview = None
        self.hint = None
        if self.dim == 3:
            self.hint = label(HINT_3D, 'muted', wrap=True,
                              align=Qt.AlignCenter)
            self.hint.setObjectName('stagehint')
            pv.addWidget(self.hint, 1)
            for b in (self.z_rings, self.show_mesh, self.fit_btn,
                      self._view_caption):
                b.setVisible(False)
        else:
            self.preview = Preview1D() if self.dim == 1 else Preview2D()
            self.preview.overlay = self._overlay.apply
            canvas = self.preview.figure.canvas
            canvas.mpl_connect('motion_notify_event', self._hover)
            canvas.mpl_connect('figure_leave_event', self._unhover)
            canvas.mpl_connect('scroll_event', self._wheel)
            pv.addWidget(self.preview, 1)
        body.addWidget(self.view_card, 1)

        # ── right: the properties (the Setup's column, D19) ──────────────
        self._props = QFrame()
        self._props.setObjectName('setupprops')
        self._props.setFixedWidth(PROPS_W)
        pl = QVBoxLayout(self._props)
        pl.setContentsMargins(*PROPS_PAD)
        pl.setSpacing(4)
        self._eyebrow = QLabel('PROPERTIES')
        self._eyebrow.setObjectName('eyebrow')
        _letter_space(self._eyebrow)
        self._props_title = QLabel('')
        self._props_title.setObjectName('propstitle')
        self._props_title.setTextFormat(Qt.RichText)
        self._props_title.setWordWrap(True)
        self._props_caption = QLabel('')
        self._props_caption.setObjectName('propscaption')
        self._props_caption.setWordWrap(True)
        for w in (self._eyebrow, self._props_title, self._props_caption):
            w.setContentsMargins(0, 0, 8, 0)
            pl.addWidget(w)
        pl.addSpacing(10)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(theme.PAD - 4)
        self._scroll.setWidget(self._content)
        pl.addWidget(self._scroll, 1)
        body.addWidget(self._props)

        self.stage_page = self._build_stage_page()
        cl.addWidget(self.stage_page)
        self.form = CaseForm(self.dim, on_change=on_change,
                             mode=mode, placement='nodes')
        cl.addWidget(self.form)
        cl.addStretch(1)
        self.derived = self.form.add_to_page('threat', DerivedCard(self.dim),
                                             index=1)
        self.tree.set_nodes([(STAGE_NODE, '00', STAGE_TITLE)]
                            + [(n.id, n.number, n.title)
                               for n, _t in setup_nodes.nodes(self.dim)])
        self.tree.set_summary(STAGE_NODE, '')
        theme.signals.changed.connect(self._retheme)
        self._sync_tree_nodes()
        self.select_node(STAGE_NODE)

    # ── the 00 Stage page ────────────────────────────────────────────────
    def _build_stage_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        solver = QVBoxLayout()
        solver.setSpacing(6)
        cap = QLabel('Solver for this stage')
        cap.setObjectName('stagefield')
        solver.addWidget(cap)
        self.solver_seg = Segmented([mode_mod.label(m)
                                     for m in mode_mod.MODES],
                                    height=32, small=True)
        self.solver_seg.changed.connect(
            lambda lbl: self.solver_picked.emit(mode_mod.from_label(lbl)))
        solver.addWidget(self.solver_seg)
        sub = QLabel(SOLVER_SUB)
        sub.setObjectName('stagesub')
        sub.setWordWrap(True)
        solver.addWidget(sub)
        lay.addLayout(solver)
        # N5-4: the hand-off refusal, said where the choice is made
        self.compat = label('', 'small', wrap=True)
        self.compat.setVisible(False)
        lay.addWidget(self.compat)
        self.hand_in = HandoffCard('Hand-off in', tinted=True)
        self.hand_out = HandoffCard('Hand-off out', tinted=False)
        lay.addWidget(self.hand_in)
        lay.addWidget(self.hand_out)
        checks = QLabel('CHECKS')
        checks.setObjectName('eyebrow')
        _letter_space(checks)
        lay.addWidget(checks)
        self._checks_box = QVBoxLayout()
        self._checks_box.setSpacing(8)
        lay.addLayout(self._checks_box)
        self._check_rows = []
        self._rows = [('ok', 'Stage OK')]
        self.note = QLabel('')
        self.note.setObjectName('stagenote')
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self._render_checks()
        return page

    def _render_checks(self):
        for w in self._check_rows:
            self._checks_box.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._check_rows = []
        for severity, message in self._rows:
            icon_name, colour = _ROW_STYLE[severity]
            row = QWidget()
            row.setProperty('severity', severity)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            pic = label('')
            pic.setFixedWidth(16)
            pic.setPixmap(theme.pixmap(icon_name, 14,
                                       color=theme.cur(colour)))
            rl.addWidget(pic, 0, Qt.AlignTop)
            # a path in a message may wrap after a separator: unbroken it
            # would set the page's minimum and widen the column (D19)
            shown = str(message).replace('\\', '\\' + ZWSP) \
                .replace('/', '/' + ZWSP)
            text = label(shown, 'body', wrap=True)
            text.setObjectName('checktext')
            text.setStyleSheet(f'color: {theme.cur(colour)};')
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            # a copied message carries no ZWSP (GUI-10, F23)
            clean_copy(text)
            rl.addWidget(text, 1)
            self._checks_box.addWidget(row)
            self._check_rows.append(row)

    def check_rows(self):
        """(severity, message) of the Checks list, as shown (tests)."""
        return list(self._rows)

    # ── position in the route ────────────────────────────────────────────
    def set_position(self, number, title):
        """`number` '01'-'03' (the stage's place in the route), `title`
        `2D axisymmetric` etc."""
        self._number, self._title = str(number), str(title)
        self.tree.header.setText(f'STAGE {self._number} · '
                                 f'{self._title.upper()}')
        self.view_title.setText(self._title)
        self._set_heading()

    # ── the tree ─────────────────────────────────────────────────────────
    def _sync_tree_nodes(self):
        """Hide the nodes the solver scope empties (never grey them)."""
        for n, _t in setup_nodes.nodes(self.dim):
            self.tree.set_node_visible(n.id, self.form.node_visible(n.id))
        if self._node not in (None, STAGE_NODE) \
                and not self.tree.node_visible(self._node):
            self.select_node(STAGE_NODE)

    def visible_nodes(self):
        """['stage'] + the form nodes the tree shows, in order."""
        return [STAGE_NODE] + [n.id for n, _t in setup_nodes.nodes(self.dim)
                               if self.tree.node_visible(n.id)]

    def has_node(self, node_id):
        return node_id in self.visible_nodes()

    def select_node(self, node_id):
        """Show node `node_id`: the 00 Stage page, or the form's own page
        for 01-07 (`CaseForm.show_node`, as Setup). False when the stage
        has no such visible node."""
        if node_id != STAGE_NODE and (node_id not in self.form.pages
                                      or not self.form.node_visible(
                                          node_id)):
            return False
        self._node = node_id
        stage = node_id == STAGE_NODE
        self.stage_page.setVisible(stage)
        self.form.setVisible(not stage)
        if not stage:
            self.form.show_node(node_id)
        self.tree.set_selected(node_id)
        if self._overlay.node != node_id:
            self._overlay.node = node_id
            if self.preview is not None and self.isVisible():
                self.preview.redraw_overlay()
        self._set_heading()
        self._scroll.verticalScrollBar().setValue(0)
        self.fit_props()
        return True

    def selected_node(self):
        return self._node

    def shown_cards(self):
        """The card titles the properties column shows now (Setup's
        `shown_cards` semantics); [] on 00 Stage."""
        if self._node == STAGE_NODE:
            return []
        return [t for t, c in self.form.cards.items()
                if c.isVisibleTo(self._props)]

    def _set_heading(self):
        if self._node == STAGE_NODE or self._node is None:
            self._eyebrow.setText(f'STAGE {self._number}')
            self._props_title.setText(self._title)
            self._props_caption.setVisible(False)
            return
        node = setup_nodes.node(self.dim, self._node)
        if node is None:
            return
        self._eyebrow.setText('PROPERTIES')
        self._props_title.setText(
            f'<span style="color:{theme.cur("accent_text")}">'
            f'{node.number}</span> {node.title}')
        self._props_caption.setText(node.caption)
        self._props_caption.setVisible(bool(node.caption))

    def _child_clicked(self, node_id, index):
        """A gauge or obstacle row: its node, and the row in its list."""
        if not self.select_node(node_id):
            return
        pl = self.form.points.get(_CHILD_LIST.get(node_id, ''))
        if pl is None:
            return
        item = pl.tree.topLevelItem(index)
        if item is not None:
            pl.tree.setCurrentItem(item)
        self._content.layout().activate()
        self._scroll.ensureWidgetVisible(pl, 0, 0)

    def _sync_children(self):
        f = self.form
        if 'gauges' in f.points:
            rows = f.points['gauges'].get()
            self.tree.set_children('gauges', 'gauge', [
                (f'G{i}', ', '.join(f'{v:.2f}' for v in row))
                for i, row in enumerate(rows, start=1)])
        if 'obstacles' in f.points:
            axis = ('r' if self.dim == 2
                    and f.v['geometry'].get() == 'axisymmetric' else 'x')
            rows = f.points['obstacles'].get()
            self.tree.set_children('structure', 'obstacle', [
                (f'Wall {i}', f'{axis} {row[0]:.1f}–{row[1]:.1f}')
                for i, row in enumerate(rows, start=1)])

    # ── what the live check found ────────────────────────────────────────
    def show_check(self, chk, solver, prev, nxt, note):
        """Fill the tree, the pill, the header numbers, the 00 Stage page
        and the preview from one `chain_route.StageCheck`."""
        f = self.form
        case = chk.case
        self._sync_tree_nodes()
        self.tree.set_summary(STAGE_NODE,
                              chain_route.stage_summary(solver, prev))
        if case is not None:
            self._case = case
            for node_id, text in setup_nodes.summaries(case).items():
                self.tree.set_summary(node_id, text)
            self.derived.show_values(case, chk.report)
            self.numbers.setText(header_numbers(
                setup_strip.tiles(case, chk.report)))
            self.numbers.set_tip(self.numbers.full_text())
            self.hand_in.set(chain_route.in_file(prev, self.dim),
                             chain_route.in_text(case, prev))
            self.hand_out.set(chain_route.out_file(self.dim, nxt),
                              chain_route.out_text(case, nxt))
            self.update_preview(case)
        else:
            # the form does not parse: the files still follow the route
            self.hand_in.set(chain_route.in_file(prev, self.dim))
            self.hand_out.set(chain_route.out_file(self.dim, nxt))
        self._sync_children()
        f.refresh_trigger_choices()
        bad = {setup_nodes.node_of_field(self.dim, n) for n in f.bad}
        stage_level = {chain_route.AXISYM_REFUSAL.split(': ', 1)[1],
                       _handoff_msg()}
        for n, _t in setup_nodes.nodes(self.dim):
            self.tree.set_status(n.id, 'error' if n.id in bad else 'ok')
        self.tree.set_status(STAGE_NODE, 'error' if any(
            e in stage_level for e in chk.errors) else 'ok')
        self.tree.set_pill(*pill_text(chk.n_errors, len(chk.warnings),
                                      len(chk.notes), ok_text='Stage OK'))
        self._rows = chk.rows() or [('ok', 'Stage OK')]
        self._render_checks()
        self.note.setText(note)

    def pill(self):
        return self.tree.pill.property('state'), self.tree.pill.text()

    # ── preview (1D / 2D only) ───────────────────────────────────────────
    def update_preview(self, case):
        """Draw `case` now when on screen, else when next shown."""
        if self.preview is None:
            self._sync_toolbar()
            return
        if not self.isVisible():
            self._pending_preview = case
            return
        self._pending_preview = None
        self.preview.show_case(case, show_mesh=self.show_mesh.isChecked())
        self._sync_toolbar()

    def _redraw(self):
        if self._case is not None:
            self.update_preview(self._case)

    def _sync_toolbar(self):
        case = self._case
        if self.preview is None:
            self._view_caption.setText('')
            return
        from . import scaled_distance
        self.z_rings.setVisible(case is not None
                                and scaled_distance.z_shown(case))
        if self._view_caption.property('hover') != 'true':
            self._view_caption.setText(plane_caption(case) if case
                                       else '')

    def _rings_toggled(self, on):
        self._overlay.rings = bool(on)
        if self.preview is not None:
            self.preview.redraw_overlay()

    def fit_view(self):
        if self.preview is not None:
            self.preview.fit()

    def _hover(self, event):
        p = self.preview
        if p is None or event.inaxes is None or p.last_case is None:
            self._unhover()
            return
        text = hover_text(p.last_case, event.xdata, event.ydata)
        if not text:
            self._unhover()
            return
        lbl = self._view_caption
        if lbl.property('hover') != 'true':
            lbl.setProperty('hover', 'true')
            theme.repolish(lbl)
        lbl.setText(text)

    def _unhover(self, _event=None):
        lbl = self._view_caption
        if lbl.property('hover') == 'true':
            lbl.setProperty('hover', 'false')
            theme.repolish(lbl)
        self._sync_toolbar()

    def _wheel(self, event):
        ax = event.inaxes
        if ax is None or event.xdata is None:
            return
        k = WHEEL_ZOOM if event.button == 'up' else 1.0 / WHEEL_ZOOM
        x, y = event.xdata, event.ydata
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        ax.set_xlim(x - (x - x0) * k, x + (x1 - x) * k)
        ax.set_ylim(y - (y - y0) * k, y + (y1 - y) * k)
        ax.figure.canvas.draw_idle()

    def view_caption(self):
        return self._view_caption.full_text()

    # ── the properties column (Setup's D19 rule) ─────────────────────────
    def fit_props(self):
        """PROPS_W unless the shown page needs more (D19)."""
        lay = self._content.layout()
        if self._node != STAGE_NODE:
            self.form._relayout()
        lay.invalidate()
        lay.activate()
        need = (self._content.minimumSizeHint().width()
                + PROPS_PAD[0] + PROPS_PAD[2]
                + self._scroll.verticalScrollBar().sizeHint().width() + 2)
        w = max(PROPS_W, need)
        if self._props.width() != w or self._props.minimumWidth() != w:
            self._props.setFixedWidth(w)

    def props_width(self):
        return self._props.width()

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_preview is not None:
            case, self._pending_preview = self._pending_preview, None
            QTimer.singleShot(0, self, lambda: self.update_preview(case))
        QTimer.singleShot(0, self, self.fit_props)

    def _retheme(self, _mode=None):
        self._set_heading()
        self.fit_btn.setIcon(theme.icon('fit', 15, color='muted'))
        self._render_checks()
        QTimer.singleShot(0, self, self.fit_props)


def _handoff_msg():
    from ..services.chain import HANDOFF_MSG
    return HANDOFF_MSG


# re-exported for the tests (the Setup's minimum tree width)
__all__ = ['StageEditor', 'header_numbers', 'TREE_W', 'TREE_MIN',
           'HINT_3D', 'STAGE_NODE']
