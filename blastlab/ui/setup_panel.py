"""The Setup tab (GUI-5, plan §5, board BC_Combined): three columns -
the model tree (280 px), the centre (the live model preview over the
validation report) and the properties of the selected node (340 px).

The four case forms are `CaseForm(placement='nodes')`: one instance per
dimension, as before, so get_case / set_case are unchanged; only where
their cards are laid moved (plan §11). The dimension control lives in
the window's top bar (GUI-3)."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel,
                               QScrollArea, QSizePolicy, QStackedWidget,
                               QVBoxLayout, QWidget)

from ..core import mode as mode_mod
from ..viz3d import MISSING_MSG, pyvista_available
from . import scaled_distance, setup_nodes, theme
from .case_form import CaseForm
from .preview_panel import Preview1D, Preview2D, Preview3DBridge
from .setup_tree import SetupTree, _letter_space
from .theme import GAP, PAD
from .widgets import Card, label

#: a long report (AMR + zones + foam notes can be eight lines) used to
#: grow the card until the form above it had a third of its height, so
#: the report area is a fixed height and scrolls.
#:
#: 104 came from the Tk widget's metrics and was too small here: it left
#: a 54 px viewport, about two wrapped lines, while a plain blastFoam 2D
#: case already reports six rows needing 367 px. 132 shows five or six
#: lines, which covers the ordinary case without eating the form.
STATUS_MAX_H = 132

#: the properties column (plan §5). It is a minimum: a node whose cards
#: cannot fit (the 3D VTK matrix with its full-word headers, P13; the 0-D
#: Loaded wall caption) widens it to their minimum rather than clip them
#: (decision D19).
PROPS_W = 340
#: the column's inner padding: left, top, right, bottom. The right pad is
#: small because the scroll bar sits there: 340 - 2 (border) - 12 - 4 -
#: 10 (scroll bar) leaves exactly the 312 px the label+input cards need
#: (measured).
PROPS_PAD = (12, 14, 4, 8)

#: icon + palette key per report severity
_ROW_STYLE = {'error': ('error', 'error'), 'warn': ('warning', 'warn'),
              'note': ('info', 'muted'), 'ok': ('check', 'ok')}

#: the point list a tree child row and the + buttons lead to
_CHILD_LIST = {'gauges': 'gauges', 'structure': 'obstacles'}


class _PreviewStack(QStackedWidget):
    """The preview pages, sized by the page on screen. A plain
    QStackedWidget takes its LARGEST page as its minimum, so the 3D host
    held the centre at 368 px even under a 2D preview (measured), and a
    wide properties page then pushed the window past 1100 px."""

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


class DerivedCard(Card):
    """The read-only Derived card on 01 Threat (plan §5.2, board lines
    326-331): charge radius, height of burst, nearest gauge with its Z.
    Display only. The radius is the validation report's own `r_exp` -
    never a second formula here; Z comes from `scaled_distance`."""

    ROWS = (('radius', 'Charge radius'), ('hob', 'Height of burst'),
            ('nearest', 'Nearest gauge'))

    def __init__(self, dim, parent=None):
        super().__init__(pad=14, parent=parent)
        self.dim = int(dim)
        lay = self.body_layout
        lay.setSpacing(9)
        eyebrow = QLabel('DERIVED')
        eyebrow.setObjectName('eyebrow')
        _letter_space(eyebrow)
        lay.addWidget(eyebrow)
        self._vals, self._rows = {}, {}
        for key, text in self.ROWS:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(GAP)
            k = QLabel(text)
            k.setObjectName('derivedkey')
            v = QLabel('')
            v.setObjectName('derivedval')
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            rl.addWidget(k)
            rl.addStretch(1)
            rl.addWidget(v)
            lay.addWidget(row)
            self._vals[key], self._rows[key] = v, row
        # a 1D charge is a free-air sphere: there is no ground to be above
        self._rows['hob'].setVisible(self.dim != 1)

    def value(self, key):
        return self._vals[key].text()

    def update(self, case, rep):
        """From the case the debounced validation parsed and its report;
        the rows keep their last values while the form does not parse."""
        if case is None or getattr(case, 'dim', None) != self.dim:
            return
        r_exp = getattr(rep, 'r_exp', None) if rep is not None else None
        # blank until validation has sized the charge (and in profile
        # mode, where it places none: r_exp = 0)
        self._vals['radius'].setText(f'{r_exp * 1e3:.1f} mm' if r_exp
                                     else '')
        if self.dim > 1:
            up = case.center[1] if self.dim == 2 else case.center[2]
            self._vals['hob'].setText(f'{float(up):.2f} m')
        near = scaled_distance.nearest_gauge(case)
        if near is None:
            text = ''
        elif near[2] is not None:
            text = f'G{near[0]} · Z {near[2]:.2f}'
        else:
            text = f'G{near[0]} · R {near[1]:.2f} m'
        self._vals['nearest'].setText(text)


def _dim_label(form):
    """The tree header's `MODEL · <dim>` text."""
    if form.dim == 0:
        return 'MODEL · 0D · HD 1.3'
    if form.dim == 1:
        return 'MODEL · 1D SPHERICAL'
    if form.dim == 2:
        return f'MODEL · 2D {form.v["geometry"].get().upper()}'
    return 'MODEL · 3D'


def pill_text(errors, warnings, notes):
    """(state, text) of the tree's case pill from report counts (plan
    §5.1): `N errors` when invalid, else `Case OK` plus the counts."""
    def n(k, word):
        return f'{k} {word}{"" if k == 1 else "s"}'
    if errors:
        return 'error', n(errors, 'error')
    bits = ['Case OK']
    if warnings:
        bits.append(n(warnings, 'warning'))
    if notes:
        bits.append(n(notes, 'note'))
    return ('warn' if warnings else 'ok'), ' · '.join(bits)


class SetupPanel(QWidget):
    """The model tree + the four CaseForms (in the properties column) +
    the live model preview and the validation card (in the centre)."""

    PREV_HINT = 'Enter a valid case to preview the model here.'

    dim_changed = Signal(int)
    node_selected = Signal(str)

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
        self._node = None            # the selected tree node

        body = QHBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(GAP)

        # ── left: the model tree ─────────────────────────────────────────
        self.tree = SetupTree()
        self.tree.node_clicked.connect(self._node_clicked)
        self.tree.child_clicked.connect(self._child_clicked)
        self.tree.add_gauge.connect(lambda: self.add_point('gauges'))
        self.tree.add_obstacle.connect(lambda: self.add_point('structure'))
        self.tree.pill_clicked.connect(self._flash_checks)
        body.addWidget(self.tree)

        # ── centre: the preview over the validation report ───────────────
        centre = QVBoxLayout()
        centre.setContentsMargins(0, 0, 0, 0)
        centre.setSpacing(GAP)
        prev = Card('Model Preview', pad=12)
        pv = prev.body_layout
        self.show_mesh = QCheckBox('Show mesh')
        self.show_mesh.toggled.connect(self._mesh_toggled)
        pv.addWidget(self.show_mesh)
        self._prev_stack = _PreviewStack()
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
        centre.addWidget(prev, 1)

        # the validation report stays visible at the bottom of the centre
        # (GUI-5b turns it into the dock's Checks tab)
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
        centre.addWidget(self._status_card)
        holder = QWidget()
        holder.setLayout(centre)
        body.addWidget(holder, 1)

        # ── right: the properties of the selected node ───────────────────
        self._props = QFrame()
        self._props.setObjectName('setupprops')
        self._props.setFixedWidth(PROPS_W)
        pl = QVBoxLayout(self._props)
        pl.setContentsMargins(*PROPS_PAD)
        pl.setSpacing(4)
        eyebrow = QLabel('PROPERTIES')
        eyebrow.setObjectName('eyebrow')
        _letter_space(eyebrow)
        self._props_title = QLabel('')
        self._props_title.setObjectName('propstitle')
        self._props_title.setTextFormat(Qt.RichText)
        self._props_caption = QLabel('')
        self._props_caption.setObjectName('propscaption')
        self._props_caption.setWordWrap(True)
        for w in (eyebrow, self._props_title, self._props_caption):
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
        cl.setSpacing(PAD - 4)
        self._scroll.setWidget(self._content)
        pl.addWidget(self._scroll, 1)
        body.addWidget(self._props)

        self._forms = {d: CaseForm(d, on_change=self._changed,
                                   mode=self._mode.get(),
                                   placement='nodes')
                       for d in (0, 1, 2, 3)}
        for d, f in self._forms.items():
            cl.addWidget(f)
            # only the active form is in the layout's minimum: a hidden
            # widget adds nothing (a QStackedWidget would add its largest)
            f.setVisible(d == 2)
        cl.addStretch(1)
        # the Derived card sits under the charge inputs on the 01 Threat
        # page of each blast form (board line 326), above the point lists
        self._derived = {d: self._forms[d].add_to_page(
            'threat', DerivedCard(d), index=1) for d in (1, 2, 3)}
        if 'geometry' in self._forms[2].v:
            self._forms[2].on_field('geometry', self._sync_header)
        self._dim = 2
        self._mode.subscribe(self._mode_changed)
        theme.signals.changed.connect(self._retheme)
        self._rebuild_tree()
        self.show_report()

    # ── solver mode / dimension ──────────────────────────────────────────
    @property
    def solver(self):
        return self._mode.get()

    def _mode_changed(self, m):
        for d, f in self._forms.items():
            if d:                       # a 0-D case has no solver backend
                f.set_mode(m)
        # cards vanished: a viewport left past the new end would show
        # nothing, so go back to the top
        self._scroll.verticalScrollBar().setValue(0)
        self._sync_tree()
        self._changed()

    @property
    def dim(self):
        return self._dim

    def set_dim(self, dim):
        dim = int(dim)
        if dim not in self._forms:
            return
        self._dim = dim
        for d, f in self._forms.items():
            f.setVisible(d == dim)
        self._rebuild_tree()
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
        # the case's solver becomes the app mode (top bar, Chain presets,
        # Results) BEFORE the form is filled, so the amr_levels trace and
        # the hide/show logic see the right mode. A 0-D case has no
        # solver and must not drag the app mode back to native.
        if case.dim:
            self._mode.set(getattr(case, 'solver', 'native'))
        self.set_dim(case.dim)
        self.form.set_case(case)
        self._sync_tree()

    # ── the model tree (plan §5.1) ───────────────────────────────────────
    def _rebuild_tree(self):
        """Rows for the active dimension; keep the selected node when the
        new dimension has it (05 Gauges stays 05 from 2D to 3D)."""
        nodes = setup_nodes.nodes(self._dim)
        self.tree.set_nodes([(n.id, n.number, n.title) for n, _t in nodes])
        self.tree.set_adds_visible('gauges' in self.form.points,
                                   'obstacles' in self.form.points)
        self._sync_header()
        self._sync_tree(prefer=self._node)

    def _sync_header(self):
        self.tree.header.setText(_dim_label(self.form))

    def _sync_tree(self, prefer=None):
        """Hide the nodes the solver scope empties (never grey them) and
        keep a visible node selected."""
        f = self.form
        for n, _t in setup_nodes.nodes(self._dim):
            self.tree.set_node_visible(n.id, f.node_visible(n.id))
        want = prefer or self._node
        if want is None or not self.tree.node_visible(want) \
                or want not in f.pages:
            want = next((n.id for n, _t in setup_nodes.nodes(self._dim)
                         if self.tree.node_visible(n.id)), None)
        if want is not None and (want != self._node
                                 or f.current_node() != want):
            self.select_node(want, emit=False)

    def visible_nodes(self):
        """The node ids the tree shows, in order (tests)."""
        return [n.id for n, _t in setup_nodes.nodes(self._dim)
                if self.tree.node_visible(n.id)]

    def select_node(self, node_id, emit=True):
        """Show node `node_id`'s cards, and only those, in the properties
        column. False when the active form has no such visible node."""
        f = self.form
        if node_id not in f.pages or not f.node_visible(node_id):
            return False
        f.show_node(node_id)
        self._node = node_id
        self.tree.set_selected(node_id)
        self._set_heading()
        self._scroll.verticalScrollBar().setValue(0)
        self._fit_props()
        if emit:
            self.node_selected.emit(node_id)
        return True

    def _set_heading(self):
        """`PROPERTIES` / `<number> <title>` (the number in accent_text,
        board line 274) / the node's one-line caption."""
        node = setup_nodes.node(self._dim, self._node)
        if node is None:
            return
        self._props_title.setText(
            f'<span style="color:{theme.cur("accent_text")}">'
            f'{node.number}</span> {node.title}')
        self._props_caption.setText(node.caption)
        self._props_caption.setVisible(bool(node.caption))

    def selected_node(self):
        return self._node

    def shown_cards(self):
        """The card titles the properties column shows now: the selected
        node's cards that the solver scope shows (tests)."""
        return [t for t, c in self.form.cards.items()
                if c.isVisibleTo(self._props)]

    def show_card(self, title):
        """Select the node holding card `title` and scroll to it (the QA
        harness reaches a card through this)."""
        node_id = setup_nodes.node_of_card(self._dim, title)
        if node_id is None or not self.select_node(node_id):
            return False
        self._ensure_visible(self.form.cards[title])
        return True

    def _node_clicked(self, node_id):
        self.select_node(node_id)

    def _child_clicked(self, node_id, index):
        """A gauge or obstacle row: select its parent node, scroll to its
        list and select the row there (plan §5.1)."""
        if not self.select_node(node_id):
            return
        pl = self.form.points.get(_CHILD_LIST.get(node_id, ''))
        if pl is None:
            return
        item = pl.tree.topLevelItem(index)
        if item is not None:
            pl.tree.setCurrentItem(item)
        self._ensure_visible(pl)

    def add_point(self, node_id):
        """+ Gauge / + Obstacle: select the node and put the cursor in its
        list's entry."""
        name = _CHILD_LIST.get(node_id)
        pl = self.form.points.get(name) if name else None
        if pl is None or not self.select_node(node_id):
            return False
        pl.entry.setFocus(Qt.OtherFocusReason)
        self._ensure_visible(pl.entry)
        return True

    def _ensure_visible(self, widget):
        """Scroll the properties column to `widget` once the newly shown
        page has its geometry (now, and again after the layout pass)."""
        self._content.layout().activate()
        self._scroll.ensureWidgetVisible(widget, 0, 0)
        QTimer.singleShot(0, self, lambda: self._scroll.ensureWidgetVisible(
            widget, 0, 0))

    def refresh(self, case=None, rep=None):
        """After a debounced validation (app._validate): the row
        summaries from the parsed case (kept when it does not parse),
        the gauge / obstacle children from the lists themselves, ✗ on a
        node with a field the form marked bad, the node visibility."""
        f = self.form
        if case is not None and getattr(case, 'dim', None) == self._dim:
            for node_id, text in setup_nodes.summaries(case).items():
                self.tree.set_summary(node_id, text)
            if self._dim in self._derived:
                self._derived[self._dim].update(case, rep)
        self._sync_children()
        # the trigger dropdown offers the gauges as they are now
        f.refresh_trigger_choices()
        bad = {setup_nodes.node_of_field(self._dim, n) for n in f.bad}
        for n, _t in setup_nodes.nodes(self._dim):
            self.tree.set_status(n.id, 'error' if n.id in bad else 'ok')
        self._sync_tree()

    def _sync_children(self):
        f = self.form
        if 'gauges' in f.points:
            rows = f.points['gauges'].get()
            self.tree.set_children('gauges', 'gauge', [
                (f'G{i}', ', '.join(f'{v:.2f}' for v in row))
                for i, row in enumerate(rows, start=1)])
        if 'obstacles' in f.points:
            axis = ('r' if self._dim == 2
                    and f.v['geometry'].get() == 'axisymmetric' else 'x')
            rows = f.points['obstacles'].get()
            self.tree.set_children('structure', 'obstacle', [
                (f'Wall {i}', f'{axis} {row[0]:.1f}–{row[1]:.1f}')
                for i, row in enumerate(rows, start=1)])

    def _fit_props(self):
        """Hold the properties column at PROPS_W unless the shown page
        needs more; then widen it to that page's minimum (D19)."""
        lay = self._content.layout()
        self.form._relayout()
        lay.invalidate()
        lay.activate()
        # + 2: the column's 1 px QSS border on each side (measured: the
        # viewport ran 2 px short of the page minimum without it)
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
        # the style sheet's fonts reach the widgets on their first show,
        # and they set the page minimum
        QTimer.singleShot(0, self, self._fit_props)

    def _retheme(self, _mode=None):
        # the heading's number colour is baked into its rich text
        self._set_heading()
        QTimer.singleShot(0, self, self._fit_props)

    # ── validation report ────────────────────────────────────────────────
    def show_report(self, errors=(), warnings=(), notes=()):
        rows = ([('error', m) for m in errors]
                + [('warn', m) for m in warnings]
                + [('note', m) for m in notes])
        # the tree's pill is fed from the same report (plan §5.1)
        self.tree.set_pill(*pill_text(len(errors), len(warnings),
                                      len(notes)))
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

    def derived(self, dim=None):
        """The Derived card of `dim` (default: the active one), or None
        (0-D has none)."""
        return self._derived.get(self._dim if dim is None else int(dim))

    def pill(self):
        """(state, text) of the tree's case pill (tests)."""
        return self.tree.pill.property('state'), self.tree.pill.text()

    def _flash_checks(self):
        """The pill until GUI-5b's dock exists: bring the report card to
        the eye - scroll it to the top and outline it for a moment."""
        self._status_scroll.verticalScrollBar().setValue(0)
        card = self._status_card
        card.setProperty('flash', 'true')
        theme.repolish(card)

        def unflash():
            card.setProperty('flash', 'false')
            theme.repolish(card)
        QTimer.singleShot(900, card, unflash)

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
        """Scroll the properties column to a fraction of its range (the
        QA harness screenshots the bottom cards)."""
        bar = self._scroll.verticalScrollBar()
        bar.setValue(int(round(bar.maximum() * max(0.0, min(1.0, frac)))))
        return bar.value()

    def release_preview(self):
        """Give the viewer child's window back (leaving the tab)."""
        if self.preview3d is not None:
            self.preview3d.clear()
