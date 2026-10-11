"""The Setup tab (GUI-5, plan §5, board BC_Combined): three columns -
the model tree (280 px), the centre (the live model preview over the
validation report) and the properties of the selected node (340 px).

The four case forms are `CaseForm(placement='nodes')`: one instance per
dimension, as before, so get_case / set_case are unchanged; only where
their cards are laid moved (plan §11). The dimension control lives in
the window's top bar (GUI-3)."""

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel,
                               QPlainTextEdit, QPushButton, QScrollArea,
                               QSizePolicy, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import mode as mode_mod
from ..services.validation import drop_rule
from ..viz3d import MISSING_MSG, pyvista_available
from . import scaled_distance, setup_nodes, theme
from .case_form import CaseForm
from .components import DockTabs
from .model_overlay import HOVER_TIP, ModelOverlay, hover_text, plane_caption
from .preview_panel import Preview1D, Preview2D, Preview3DBridge
from .setup_strip import LiveStrip
from .setup_tree import TREE_MIN, SetupTree, _letter_space
from .theme import GAP, PAD
from .widgets import Card, label

#: the dock under the model view (board line 217: 212 px, tabs 40 px +
#: a 1 px rule). On a short window it gives way down to DOCK_MIN
#: (DOCK_FRACTION of the panel's height) so the model keeps its room.
DOCK_H = 212
DOCK_MIN = 150
DOCK_FRACTION = 0.28
DOCK_TABS_H = 41

#: a long report (AMR + zones + foam notes can be eight lines) must not
#: grow over the model view, so the report area has a cap and scrolls.
#: Since GUI-5b the report is the dock's Checks tab and the cap is the
#: tab page: the dock minus its tab strip and its 1 px bottom border.
#: (Before: a 132 px card under the preview; 104, from the Tk widget,
#: had left a 54 px viewport for a 367 px report.)
STATUS_MAX_H = DOCK_H - DOCK_TABS_H - 1

#: the Checks tab lays its rows in two columns (board line 258) once its
#: viewport is this wide, else one
CHECKS_TWO_COL = 560

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

#: the gauge table's columns (board lines 228-235): name, up to three
#: coordinates (hidden per dimension), R, Z, Where
_GAUGE_COLS = ('gauge', 'c1', 'c2', 'c3', 'R', 'Z', 'where')

#: the dock tab a selected node brings up (board script: pickThreat ->
#: Checks, pickGauges -> Gauges); other nodes leave the dock alone
_DOCK_FOR_NODE = {'gauges': 'Gauges', 'threat': 'Checks'}


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

    def show_values(self, case, rep):
        """From the case the debounced validation parsed and its report;
        the rows keep their last values while the form does not parse.
        (Not named `update`: that would shadow QWidget.update(), which
        theme.repolish and Qt-side code call with no argument.)"""
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
        # UXR-15 (D221): the unit the compact `Z 2.99` leaves out
        self._vals['nearest'].setToolTip(
            scaled_distance.UNIT_TIP if near is not None
            and near[2] is not None else '')


def _tool_button(text, checkable=False, tip=None):
    """A 28 px toolbar button of the model view (board lines 164-166)."""
    b = QPushButton(text)
    b.setObjectName('viewtool')
    b.setCheckable(checkable)
    b.setFixedHeight(28)
    b.setCursor(Qt.PointingHandCursor)
    if tip:
        b.setToolTip(tip)
    return b


#: one wheel notch zooms the 1D/2D model view by this factor about the
#: pointer (Fit undoes it)
WHEEL_ZOOM = 0.8


def _dim_label(form):
    """The tree header's `MODEL · <dim>` text."""
    if form.dim == 0:
        return 'MODEL · 0D · HD 1.3'
    if form.dim == 1:
        return 'MODEL · 1D SPHERICAL'
    if form.dim == 2:
        return f'MODEL · 2D {form.v["geometry"].get().upper()}'
    return 'MODEL · 3D'


def pill_text(errors, warnings, notes, ok_text='Case OK'):
    """(state, text) of the tree's case pill from report counts (plan
    §5.1): `N errors` when invalid, else `Case OK` plus the counts. The
    Chain's stage tree says `Stage OK` (GUI-9, board Chain line 116)."""
    def n(k, word):
        return f'{k} {word}{"" if k == 1 else "s"}'
    if errors:
        return 'error', n(errors, 'error')
    bits = [ok_text]
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
    #: the strip's Run F5 / Initialise (MainWindow wires them to the same
    #: actions as the Run tab and the F5 key)
    run_requested = Signal()
    init_requested = Signal()
    #: one line for the dock's Log tab; emitted from whatever thread
    #: logged it and delivered queued on the GUI thread
    _log_line = Signal(str)

    def __init__(self, on_change=None, mode=None, viewer_link=None,
                 log_fn=print, parent=None):
        super().__init__(parent)
        self._on_change = on_change or (lambda: None)
        # the app-level solver mode (T34); a private one when the panel is
        # built standalone (tests)
        self._mode = mode if mode is not None else mode_mod.SolverMode()
        # the window's sink still gets every line; the dock's Log tab a
        # copy (GUI-5b)
        self._log_sink = log_fn
        self._log = self._log_through
        self._last_case = None
        self._table_case = None      # the case the gauge table shows
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
        self.tree.pill_clicked.connect(self.show_checks)
        body.addWidget(self.tree)

        # ── centre: the live numbers, the preview, the report ────────────
        centre = QVBoxLayout()
        centre.setContentsMargins(0, 0, 0, 0)
        centre.setSpacing(GAP)
        # GUI-5b: the live-number strip (board lines 125-159), filled by
        # refresh() from the report the debounced validation produced
        self.strip = LiveStrip()
        self.strip.run_clicked.connect(self.run_requested.emit)
        self.strip.init_clicked.connect(self.init_requested.emit)
        centre.addWidget(self.strip)
        prev = Card(pad=12)
        self._view_card = prev
        pv = prev.body_layout
        # GUI-5b: the model view's toolbar (board lines 162-167) - the
        # plane caption (the hover readout while the pointer is over the
        # model), then Z rings / Mesh / Fit
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)
        self._view_caption = QLabel('')
        self._view_caption.setObjectName('viewcaption')
        self._view_caption.setMinimumWidth(10)
        self._view_caption.setSizePolicy(QSizePolicy.Ignored,
                                         QSizePolicy.Preferred)
        bar.addWidget(self._view_caption, 1)
        self.z_rings = _tool_button('Z rings', checkable=True,
                                    tip='Dashed rings at Z = 1, 2, 3 '
                                        'around the burst point '
                                        '(Z = R / W^1/3)')
        self.z_rings.setChecked(True)
        self.z_rings.toggled.connect(self._rings_toggled)
        #: kept under its old name: the harness, the embed e2e and the
        #: 3D preview call setChecked / isChecked / toggled on it
        self.show_mesh = _tool_button('Mesh', checkable=True,
                                      tip='Show the cells the run will use')
        self.show_mesh.toggled.connect(self._mesh_toggled)
        self.fit_btn = _tool_button('', tip='Fit the whole domain')
        self.fit_btn.setFixedWidth(28)
        self.fit_btn.setAccessibleName('Fit to view')
        self.fit_btn.setIcon(theme.icon('fit', 15, color='muted'))
        self.fit_btn.clicked.connect(lambda *_: self.fit_view())
        for b in (self.z_rings, self.show_mesh, self.fit_btn):
            bar.addWidget(b)
        pv.addLayout(bar)
        self._overlay = ModelOverlay()
        self._prev_stack = _PreviewStack()
        pv.addWidget(self._prev_stack, 1)
        self._prev_msg = label(self.PREV_HINT, 'muted', wrap=True,
                               align=Qt.AlignCenter)
        self._prev_stack.addWidget(self._prev_msg)
        self.preview1d = Preview1D()
        self.preview2d = Preview2D()
        for p in (self.preview1d, self.preview2d):
            self._prev_stack.addWidget(p)
            p.overlay = self._overlay.apply
            canvas = p.figure.canvas
            canvas.mpl_connect('motion_notify_event', self._hover)
            canvas.mpl_connect('figure_leave_event', self._unhover)
            canvas.mpl_connect('scroll_event', self._wheel)
        self.view3d = None
        self.preview3d = None
        if viewer_link is not None and pyvista_available():
            from .view3d_host import View3DHost
            self.view3d = View3DHost(viewer_link, 'setup',
                                     log_fn=self._log)
            self.view3d.set_controls_collapsed(True)
            self._prev_stack.addWidget(self.view3d)
            self.preview3d = Preview3DBridge(self.view3d, log_fn=self._log)
        self._prev_stack.setCurrentWidget(self._prev_msg)
        centre.addWidget(prev, 1)

        # GUI-5b: the dock Gauges · Checks · Log (board lines 217-265).
        # Checks is the validation report that sat in its own card here
        # until 5b; `show_report` / `report_rows` keep their semantics.
        self.dock_frame = QFrame()
        self.dock_frame.setObjectName('setupdock')
        self.dock_frame.setFixedHeight(DOCK_H)
        dl = QVBoxLayout(self.dock_frame)
        dl.setContentsMargins(1, 0, 1, 1)
        dl.setSpacing(0)
        self.dock = DockTabs()
        rule = QFrame()
        rule.setObjectName('dockrule')
        rule.setFixedHeight(1)
        self.dock.layout().insertWidget(1, rule)
        dl.addWidget(self.dock)
        self.dock.add('Gauges', self._build_gauge_table())
        self.dock.add('Checks', self._build_checks())
        self.dock.add('Log', self._build_log())
        self.dock.set('Checks')
        centre.addWidget(self.dock_frame)
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
        self._sync_toolbar()

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
        # the last dimension's numbers must not describe this one
        self.strip.clear(dim)
        # 0-D has no gauge table (hide, never grey)
        self.dock.set_tab_visible('Gauges', dim != 0)
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
        # the model view highlights the selected node (board chargeHi /
        # gaugeHi)
        if self._overlay.node != node_id:
            self._overlay.node = node_id
            self._redraw_overlay()
        # the dock follows a selection the user made (plan §5.3)
        if emit and node_id in _DOCK_FOR_NODE:
            self.dock.set(_DOCK_FOR_NODE[node_id])
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
                self._derived[self._dim].show_values(case, rep)
            # the live numbers: every one read off this report (GUI-5b)
            self.strip.show_values(case, rep)
            if self._dim:
                self._table_case = case
                self._fill_gauges(case)
        # GUI-14 (d), D3: the Gauges node is warn while a gauge is dropped
        # (the rule, not the warning text); GUI-15 (e): so is its child row
        gone = (scaled_distance.dropped_numbers(case)
                if case is not None and getattr(case, 'dim', None) == self._dim
                else [])
        self._sync_children(gone)
        # the trigger dropdown offers the gauges as they are now
        f.refresh_trigger_choices()
        bad = {setup_nodes.node_of_field(self._dim, n) for n in f.bad}
        drop = bool(gone)
        for n, _t in setup_nodes.nodes(self._dim):
            self.tree.set_status(n.id, 'error' if n.id in bad else
                                 'warn' if n.id == 'gauges' and drop
                                 else 'ok')
        self._sync_tree()

    def _sync_children(self, gone=()):
        """`gone`: the dropped gauges' numbers (GUI-15 (e) - warn rows)."""
        f = self.form
        if 'gauges' in f.points:
            rows = f.points['gauges'].get()
            self.tree.set_children('gauges', 'gauge', [
                (f'G{i}', ', '.join(f'{v:.2f}' for v in row), i in gone)
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
        # a wider properties page leaves the centre less room
        self._fit_dock_labels()

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
        self.fit_btn.setIcon(theme.icon('fit', 15, color='muted'))
        # the dock's colours are baked into its rows and items
        self._label_checks()
        self._render_checks()
        if self._table_case is not None:
            self._fill_gauges(self._table_case)
        QTimer.singleShot(0, self, self._fit_props)

    # ── validation report ────────────────────────────────────────────────
    def show_report(self, errors=(), warnings=(), notes=()):
        rows = ([('error', m) for m in errors]
                + [('warn', m) for m in warnings]
                + [('note', m) for m in notes])
        # the tree's pill is fed from the same report (plan §5.1)
        self.tree.set_pill(*pill_text(len(errors), len(warnings),
                                      len(notes)))
        # the Run tab's gate: an invalid case does not start
        self.strip.set_run_enabled(not errors)
        # the Checks tab carries the counts, errors · warnings · notes
        # (board line 222), and the state on its icon
        state = 'error' if errors else 'warn' if warnings else 'ok'
        self._checks_state = (state, len(errors), len(warnings), len(notes))
        self._label_checks()
        if not rows:
            rows = [('ok', 'Case OK')]
        self._report = list(rows)
        self._render_checks()

    def _label_checks(self):
        """Both dock tabs' labels: `Gauges   2` and `Checks   E · W · N`
        (board lines 219-222) with the state icon - or, when the centre
        is too narrow for them, `Gauges` / `Checks` with the counts in
        the tooltips, so the tab strip never holds the window wide."""
        state, ne, nw, nn = self._checks_state
        icon, colour = {'error': ('error', 'danger'),
                        'warn': ('warning', 'warn')}.get(state,
                                                         ('check', 'ok'))
        counts = f'{ne} · {nw} · {nn}'
        compact = self._dock_compact
        self.dock.set_label('Checks', 'Checks' if compact
                            else f'Checks   {counts}',
                            icon=theme.icon(icon, 14, color=colour))
        self.dock.set_label('Gauges', 'Gauges' if compact
                            else f'Gauges   {self._n_gauges}')
        self.dock.set_tooltip('Checks', f'{ne} errors · {nw} warnings · '
                                        f'{nn} notes')
        self.dock.set_tooltip('Gauges', f'{self._n_gauges} gauges')

    def _fit_dock_labels(self):
        """Long tab labels when the centre can hold them, else compact:
        judged against the width the centre would get with the tree at
        its minimum, never against the centre's own (circular) width."""
        if not self.isVisible():
            return
        room = (self.width() - TREE_MIN - self._props.width() - 2 * GAP
                - 4)                    # the dock frame's margins + border
        was = self._dock_compact
        self._dock_compact = False
        self._label_checks()
        if self.dock.minimumSizeHint().width() > room:
            self._dock_compact = True
        if self._dock_compact or was:
            self._label_checks()

    def _render_checks(self):
        """One row per report message, error -> warn -> note, laid by
        `_lay_checks` in one or two columns."""
        for w in self._check_rows:
            self._status_lay.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._check_rows = []
        for severity, message in self._report:
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
            text = label(str(message), 'body', wrap=True)
            text.setObjectName('checktext')
            text.setStyleSheet(f'color: {theme.cur(colour)};')
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            rl.addWidget(text, 1)
            self._check_rows.append(row)
        self._checks_cols = None
        self._lay_checks()

    def _lay_checks(self):
        """Two columns when the tab is wide (board line 258), else one;
        row-major, so the reading order stays error -> warn -> note."""
        cols = (2 if self._status_scroll.viewport().width() >= CHECKS_TWO_COL
                else 1)
        if cols == self._checks_cols:
            return
        self._checks_cols = cols
        g = self._status_lay
        for w in self._check_rows:
            g.removeWidget(w)
        for r in range(g.rowCount()):
            g.setRowStretch(r, 0)
        for k, w in enumerate(self._check_rows):
            # top-aligned: a one-line row beside a wrapped one must not
            # float to the middle of its cell (measured on the shots)
            g.addWidget(w, k // cols, k % cols, Qt.AlignTop)
        for c in range(2):
            g.setColumnStretch(c, 1 if c < cols else 0)
        g.setRowStretch((len(self._check_rows) + cols - 1) // cols, 1)

    def report_rows(self):
        """(severity, message) per row, as shown - the QA harness reads
        the report through this instead of walking widgets."""
        return list(self._report)

    def show_checks(self):
        """The case pill (plan §5.1): the dock's Checks tab, at the top."""
        self.dock.set('Checks')
        self._status_scroll.verticalScrollBar().setValue(0)

    # ── the dock (GUI-5b, board lines 217-265) ───────────────────────────
    def _build_gauge_table(self):
        """The Gauges tab: Gauge · r · z · R from charge · Z · Where."""
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        t = QTableWidget(0, len(_GAUGE_COLS))
        t.setObjectName('gaugetable')
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(34)
        t.setShowGrid(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        h = t.horizontalHeader()
        h.setHighlightSections(False)
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        # Where takes the slack; with Where hidden (1D) the numbers keep
        # their own widths instead of Z stretching across the tab
        h.setStretchLastSection(False)
        h.setSectionResizeMode(len(_GAUGE_COLS) - 1, QHeaderView.Stretch)
        h.setDefaultAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # clicking a row selects the gauge in 05 (plan §5.1's child rule)
        t.cellClicked.connect(lambda r, _c: self._child_clicked('gauges', r))
        t.viewport().installEventFilter(self)
        self._gauge_axes = 2
        self._fitting_gauges = False
        self.gauge_table = t
        # wrapped: an unwrapped hint set the dock's minimum at 280 px and
        # held a narrow window wide (measured, 3D 07 Output at 1000 px)
        self._gauge_empty = label('No gauges yet - add one with + Gauge.',
                                  'muted', wrap=True, align=Qt.AlignCenter)
        pl.addWidget(t, 1)
        pl.addWidget(self._gauge_empty, 1)
        self._gauge_empty.setVisible(False)
        return page

    def _fill_gauges(self, case):
        """The table from the parsed case: positions as entered, R and Z
        from `scaled_distance` (Z hidden where it is), Where from its
        nearest-face helper."""
        t = self.gauge_table
        dim = case.dim
        axes = (('r',) if dim == 1 else
                ('r', 'z') if case.geometry == 'axisymmetric' else
                ('x', 'y')) if dim < 3 else ('x', 'y', 'z')
        heads = ['Gauge'] + [f'{a} [m]' for a in axes] + [''] * (3 - len(axes))
        heads += ['R from charge [m]', scaled_distance.LABEL, 'Where']
        for c, text in enumerate(heads):
            item = QTableWidgetItem(text)
            item.setTextAlignment((Qt.AlignLeft if c in (0, 6)
                                   else Qt.AlignRight) | Qt.AlignVCenter)
            t.setHorizontalHeaderItem(c, item)
        z_on = scaled_distance.z_shown(case)
        self._gauge_axes = len(axes)
        for c in range(1, 4):
            t.setColumnHidden(c, c > len(axes))
        t.setColumnHidden(5, not z_on)
        t.setColumnHidden(6, dim == 1)          # 1D has no obstacles
        pts = scaled_distance.gauge_points(case)
        rows = scaled_distance.gauges(case)
        t.setRowCount(len(pts))
        mono = QFont(theme.MONO)
        mono.setPixelSize(13)
        # GUI-13 (e): the solver's drop rule, built once for the table
        dropped = drop_rule(case)
        for r, (p, (num, R, Z)) in enumerate(zip(pts, rows)):
            # GUI-14 (d): a dropped gauge's G<n> and Where cells are warn
            gone = scaled_distance.is_dropped(case, p, dropped)
            cells = ([(f'G{num}', 'warn' if gone else 'gauge')]
                     + [(f'{v:.2f}', 'text') for v in p]
                     + [('', 'text')] * (3 - len(p))
                     + [(f'{R:.2f}', 'text2'),
                        ('' if Z is None else f'{Z:.2f}', 'accent_soft'),
                        (scaled_distance.where_text(case, p, dropped),
                         'warn' if gone else 'muted')])
            for c, (text, colour) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setForeground(theme.qcolor(colour))
                if c != 6:
                    f = QFont(mono)
                    if c == 0:
                        f.setWeight(QFont.Weight.DemiBold)
                    item.setFont(f)
                item.setTextAlignment((Qt.AlignLeft if c in (0, 6)
                                       else Qt.AlignRight) | Qt.AlignVCenter)
                if c == 6 and text:
                    item.setToolTip(text)
                t.setItem(r, c, item)
        t.setVisible(bool(pts))
        self._gauge_empty.setVisible(not pts)
        self._n_gauges = len(pts)
        self._label_checks()
        self._fit_gauge_cols()

    def _fit_gauge_cols(self):
        """The board's table needs ~620 px; the centre is 432 at the
        1100 x 720 minimum. Give way in two steps rather than hide R, Z
        or Where behind a scroll: the R header shortens to `R [m]`, then
        the coordinate columns go (the tree's gauge rows show them) -
        decision D36."""
        t = self.gauge_table
        if self._table_case is None or self._fitting_gauges:
            return
        self._fitting_gauges = True
        try:
            h = t.horizontalHeader()
            avail = t.viewport().width()

            def need():
                return sum(max(t.sizeHintForColumn(c), h.sectionSizeHint(c))
                           for c in range(t.columnCount())
                           if not t.isColumnHidden(c))

            r_head = t.horizontalHeaderItem(4)
            r_head.setText('R from charge [m]')
            for c in range(1, 4):
                t.setColumnHidden(c, c > self._gauge_axes)
            if need() > avail:
                r_head.setText('R [m]')
            if need() > avail:
                for c in range(1, 4):
                    t.setColumnHidden(c, True)
            r_head.setToolTip('R from charge [m]: the distance from the '
                              'burst point to the gauge')
        finally:
            self._fitting_gauges = False

    def gauge_rows(self):
        """[[cell text per visible column]] of the gauge table (tests)."""
        t = self.gauge_table
        cols = [c for c in range(t.columnCount()) if not t.isColumnHidden(c)]
        return [[t.item(r, c).text() for c in cols]
                for r in range(t.rowCount())]

    def gauge_headers(self):
        t = self.gauge_table
        return [t.horizontalHeaderItem(c).text()
                for c in range(t.columnCount()) if not t.isColumnHidden(c)]

    def _build_checks(self):
        """The Checks tab: the validation report, capped and scrolling."""
        self._status_scroll = QScrollArea()
        self._status_scroll.setWidgetResizable(True)
        self._status_scroll.setFrameShape(QScrollArea.NoFrame)
        self._status_scroll.setMaximumHeight(STATUS_MAX_H)
        self._status_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff)
        self._status_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded)
        self._status_body = QWidget()
        self._status_lay = QGridLayout(self._status_body)
        self._status_lay.setContentsMargins(16, 12, 16, 12)
        self._status_lay.setHorizontalSpacing(24)
        self._status_lay.setVerticalSpacing(8)
        self._status_scroll.setWidget(self._status_body)
        self._check_rows = []
        self._checks_cols = None
        self._checks_state = ('ok', 0, 0, 0)
        self._n_gauges = 0
        self._dock_compact = False
        self._status_scroll.viewport().installEventFilter(self)
        return self._status_scroll

    def _build_log(self):
        """The Log tab: what the panel's log_fn was given (the 3D preview
        and viewer link messages), newest last."""
        self._log_view = QPlainTextEdit()
        self._log_view.setObjectName('log')
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(2000)
        self._log_view.setFrameShape(QFrame.NoFrame)
        self._log_line.connect(self._append_log)
        return self._log_view

    def _log_through(self, text):
        """The panel's log_fn: the window's sink first (unchanged), then a
        copy to the Log tab through a queued signal - the viewer link
        logs from its own thread."""
        try:
            self._log_sink(text)
        finally:
            try:
                self._log_line.emit(str(text))
            except RuntimeError:
                pass                     # the panel is already gone

    def _append_log(self, text):
        self._log_view.appendPlainText(str(text))

    def log_lines(self):
        """The Log tab's lines (tests)."""
        return self._log_view.toPlainText().splitlines()

    def set_dock_tab(self, name):
        self.dock.set(name)

    def dock_tab(self):
        return self.dock.get()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            checks = getattr(self, '_status_scroll', None)
            table = getattr(self, 'gauge_table', None)
            if checks is not None and obj is checks.viewport():
                self._lay_checks()
            elif table is not None and obj is table.viewport():
                self._fit_gauge_cols()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # the dock gives way on a short window (DOCK_MIN..DOCK_H)
        h = max(DOCK_MIN, min(DOCK_H, int(self.height() * DOCK_FRACTION)))
        if self.dock_frame.height() != h:
            self.dock_frame.setFixedHeight(h)
        self._fit_dock_labels()

    def derived(self, dim=None):
        """The Derived card of `dim` (default: the active one), or None
        (0-D has none)."""
        return self._derived.get(self._dim if dim is None else int(dim))

    def pill(self):
        """(state, text) of the tree's case pill (tests)."""
        return self.tree.pill.property('state'), self.tree.pill.text()

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
        before = self._prev_stack.currentWidget()
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
            else:
                self.preview3d.show_case(case, show_mesh=show_mesh)
                self._prev_stack.setCurrentWidget(self.view3d)
        else:
            self._prev_msg.setText(self.PREV_HINT)
            self._prev_stack.setCurrentWidget(self._prev_msg)
        if self._prev_stack.currentWidget() is not before:
            # a readout of the page that went away must not linger
            self._view_caption.setProperty('hover', 'false')
            theme.repolish(self._view_caption)
        self._sync_toolbar()

    def _mesh_toggled(self, _on=None):
        if self._last_case is not None:
            self.update_preview(self._last_case)

    # ── the model view's toolbar and overlay (GUI-5b) ────────────────────
    def _mpl_preview(self):
        """The 1D/2D matplotlib preview on screen, or None."""
        w = self._prev_stack.currentWidget()
        return w if w in (self.preview1d, self.preview2d) else None

    def _sync_toolbar(self):
        """Hide, never grey: Z rings only where rings can be drawn (a 1D
        or 2D preview whose case shows Z - the 3D child viewer's scene is
        out of scope, D32); Mesh and Fit wherever a preview is on screen;
        the plane caption for the case on screen."""
        kind = self.preview_kind()
        case = self._last_case
        self.z_rings.setVisible(kind in ('1d', '2d') and case is not None
                                and scaled_distance.z_shown(case))
        for b in (self.show_mesh, self.fit_btn):
            b.setVisible(kind != 'hint')
        if not self._view_caption.property('hover') == 'true':
            self._view_caption.setText(
                plane_caption(case) if kind != 'hint' else '')
            # UXR-15 (D221, D224): the readout's units stay on the caption
            # after the pointer leaves the model, so moving onto the
            # caption can show them (the hover itself clears the readout)
            self._view_caption.setToolTip(
                HOVER_TIP if kind in ('1d', '2d') and case is not None
                else '')

    def _redraw_overlay(self):
        p = self._mpl_preview()
        if p is not None:
            p.redraw_overlay()

    def _rings_toggled(self, on):
        self._overlay.rings = bool(on)
        self._redraw_overlay()

    def fit_view(self):
        """Fit: the whole domain again - the 1D/2D drawing replayed at its
        own limits, or the 3D viewer's camera reset."""
        p = self._mpl_preview()
        if p is not None:
            p.fit()
        elif self.preview_kind() == '3d':
            self.view3d._ctrl('reset_view')

    def overlay(self):
        """The model view's overlay state (tests)."""
        return self._overlay

    def view_caption(self):
        return self._view_caption.text()

    def _hover(self, event):
        """`r · z · R · Z` under the pointer (board: the hover readout),
        in the toolbar's caption slot while the pointer is on the model."""
        p = self._mpl_preview()
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
            lbl.setToolTip(HOVER_TIP)           # UXR-15: the units
        lbl.setText(text)

    def _unhover(self, _event=None):
        lbl = self._view_caption
        if lbl.property('hover') == 'true':
            lbl.setProperty('hover', 'false')
            theme.repolish(lbl)
        self._sync_toolbar()                    # the caption and its tip

    def _wheel(self, event):
        """A wheel notch zooms the 1D/2D view about the pointer; Fit
        goes back to the whole domain."""
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
