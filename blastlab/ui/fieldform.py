"""The Setup form's engine: it turns `setup_spec` descriptors into
widgets and gives the case-building code the same variable surface the
Tk form had.

`form.v[name]` is a `Var` with exactly three methods - `get()` (always a
str), `set()` (which fires the change callbacks, as Tk's write trace
did) and `trace_add()`. That is deliberate: `get_case()`/`set_case()` and
the tests that poke a field carry over unchanged.

Fan-out contract (the same one `core/mode.py:SolverMode` implements): a
`set()` issued from inside a trace is applied immediately, but its own
fan-out waits until the current one finishes. The axisymmetric hook
writes `cx` from inside the `geometry` trace, and without this the write
either re-enters or is lost.
"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (QBoxLayout, QButtonGroup, QCheckBox,
                               QComboBox, QFormLayout, QGraphicsOpacityEffect,
                               QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QRadioButton,
                               QScrollArea, QSizePolicy, QStackedWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ..models import fields
from . import dialogs, theme
from .setup_spec import HIDDEN_ROWS, INPUT_MIN, LABEL_WRAP, SPAN, cards
from .theme import GAP
from .widgets import Card, button, label

#: the form's cards use the same 12 px padding as every other card on
#: the Setup and Chain panels. It used to be theme.PAD (16), which cost
#: 8 px per column - just enough to stop two columns fitting at the
#: DEFAULT 1280 px window, where the Tk form showed two.
CARD_PAD = 12

#: what one column of cards needs: a wrapped caption, an input, and the
#: card's padding on both sides. Two of these plus the gap is the width
#: at which the form stops trying to be two columns (see
#: FieldForm._fit_columns).
COL_MIN = LABEL_WRAP + INPUT_MIN + 2 * CARD_PAD


# ── variables ────────────────────────────────────────────────────────────
class Var:
    """A form field's value. `get()` returns a str, `set()` fires the
    traces, `trace_add('write', cb)` registers one."""

    def __init__(self, name, value=''):
        self.name = name
        self._value = self._coerce(value)
        self._traces = []
        self._push = None        # set(str) -> update the widget silently
        self._form = None        # the FieldForm, for the deferred fan-out

    @staticmethod
    def _coerce(value):
        return str(value)

    def get(self):
        return self._value

    def set(self, value):
        v = self._coerce(value)
        if v == self._value:
            return
        self._value = v
        if self._push is not None:
            self._push(v)
        self._fire()

    def trace_add(self, _mode, callback):
        """`_mode` is accepted and ignored - Tk's only mode here was
        'write'."""
        self._traces.append(callback)
        return callback

    # ── internals ────────────────────────────────────────────────────────
    def _adopt(self, raw):
        """The widget changed under the user's hands."""
        v = self._coerce(raw)
        if v == self._value:
            return
        self._value = v
        self._fire()

    def _fire(self):
        if self._form is not None:
            self._form._dispatch(self)
        else:
            for cb in list(self._traces):
                cb()

    def __repr__(self):
        return f'Var({self.name!r}, {self._value!r})'


class BoolVar(Var):
    """A checkbox's value: `get()` returns a real bool (the case builder
    does `150 if v['record'].get() else 0`)."""

    @staticmethod
    def _coerce(value):
        if isinstance(value, str):
            return value.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(value)


class MatrixVar(Var):
    """The VTK quantity matrix (OUT-2): `get()` returns
    {column: [field, ...]} in canonical order, for the destination
    columns of the form's dimension (models.fields.vtk_matrix)."""

    def __init__(self, name, dim, value=None):
        self._dim = int(dim)
        super().__init__(name, value)

    def _coerce(self, value):
        return fields.vtk_matrix(value, self._dim)

    def get(self):
        return {k: list(v) for k, v in self._value.items()}


# ── the Time / Step pair and the quantity matrix (OUT-2) ─────────────────
#: the opacity of the matrix's locked Gauges boxes (P20): low enough that
#: a locked box stands out from the card less than half as much as a live
#: one, in light and dark mode (test_ui_output_card C10)
LOCKED_OPACITY = 0.35


class RadioRow(QWidget):
    """One exclusive radio button per value, in a row. The Var holds the
    value ('time'); the button shows it capitalised ('Time')."""

    def __init__(self, var, values, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(GAP * 2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for val in values:
            b = QRadioButton(str(val).capitalize())
            b.clicked.connect(lambda *_a, v=var, val=val: v._adopt(val))
            self.group.addButton(b)
            self.buttons[val] = b
            lay.addWidget(b)
        lay.addStretch(1)
        var._push = self._push
        self._push(var.get())

    def _push(self, value):
        b = self.buttons.get(value)
        if b is not None:
            _silently(b.setChecked, b, True)


class MatrixGrid(QWidget):
    """Viper's "Output Quantities" grid: one row per quantity, one tick
    box per destination column (plan sec. 3.2). The Gauges column is
    display only - p, rho, U ticked and disabled (decision 4)."""

    def __init__(self, var, dim, rows, cols, parent=None):
        super().__init__(parent)
        self._var = var
        self.boxes = {}                          # (field, col) -> QCheckBox
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(GAP)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(0, 1)
        for j, col in enumerate(cols, start=1):
            head = label(fields.vtk_column_label(dim, col), 'small')
            head.setAlignment(Qt.AlignCenter)
            head.setToolTip(fields.vtk_column_tip(dim, col))
            grid.addWidget(head, 0, j)
        for i, f in enumerate(rows, start=1):
            name = label(fields.VTK_QUANTITY_LABELS.get(f, f), 'muted')
            name.setToolTip(fields.vtk_quantity_tip(f))
            grid.addWidget(name, i, 0)
            for j, col in enumerate(cols, start=1):
                box = QCheckBox()
                box.setToolTip(f'{fields.vtk_column_tip(dim, col)}: '
                               f'{fields.vtk_quantity_tip(f)}')
                if col == 'gauges':
                    box.setChecked(f in fields.VTK_GAUGE_FIELDS)
                    box.setEnabled(False)
                    # P20 (owner, 2026-09-27): Fusion draws a disabled box
                    # with the live one's outline and tick, on the card's
                    # white in light mode - so the locked column looked the
                    # MORE active. Fade it: display only, in both modes.
                    fade = QGraphicsOpacityEffect(box)
                    fade.setOpacity(LOCKED_OPACITY)
                    box.setGraphicsEffect(fade)
                else:
                    box.clicked.connect(lambda *_a: self._adopt())
                    self.boxes[(f, col)] = box
                grid.addWidget(box, i, j, Qt.AlignCenter)
        var._push = self._push
        self._push(var.get())

    def _adopt(self):
        value = {}
        for (f, col), box in self.boxes.items():
            if box.isChecked():
                value.setdefault(col, []).append(f)
        self._var._adopt(value)

    def _push(self, value):
        for (f, col), box in self.boxes.items():
            _silently(box.setChecked, box, f in value.get(col, ()))


# ── the fixed-arity point list (gauges, obstacles, zones) ────────────────
class PointList(QWidget):
    """A table of numeric tuples with an add/remove row.

    Everything typed must parse as `arity` numbers, separated by commas
    or spaces; a refusal turns the hint label red and says why rather
    than failing silently. `kinds` (OUT-2, batch plan D7) gives a column
    its own parser: 'axis' takes x / y / z, 'float' (the default) a
    number, so the VTK plane table reads `y, 1.4`."""

    def __init__(self, columns, on_change=None, rows=4, parent=None,
                 kinds=()):
        super().__init__(parent)
        self._columns = list(columns)
        self._arity = len(self._columns)
        self._kinds = tuple(kinds) or ('float',) * self._arity
        self._on_change = on_change or (lambda: None)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(GAP)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(self._arity)
        self.tree.setHeaderLabels(self._columns)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QTreeWidget.SingleSelection)
        head = self.tree.header()
        for i in range(self._arity):
            head.setSectionResizeMode(i, QHeaderView.Stretch)
        self.tree.setMinimumHeight(26 * max(2, rows))
        self.tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self.tree, 1)

        row = QHBoxLayout()
        row.setSpacing(GAP)
        self.entry = QLineEdit()
        self.entry.returnPressed.connect(self.add)
        row.addWidget(self.entry, 1)
        row.addWidget(button('', 'plus', width=34, height=30,
                             tooltip='Add this row', on_click=self.add,
                             icon_size=13))
        row.addWidget(button('', 'minus', width=34, height=30,
                             tooltip='Remove the selected row',
                             on_click=self.remove, icon_size=13))
        lay.addLayout(row)

        self.hint = label('', 'small', wrap=True)
        lay.addWidget(self.hint)
        self._accept()

    # ── hint / refusal ───────────────────────────────────────────────────
    def _idle_text(self):
        return 'add a row: ' + '  '.join(self._columns)

    def _accept(self):
        self.hint.setText(self._idle_text())
        self.hint.setStyleSheet(f'color: {theme.cur("muted")};')
        self.entry.setProperty('bad', 'false')
        theme.repolish(self.entry)

    def _reject(self, message):
        self.hint.setText(message)
        self.hint.setStyleSheet(f'color: {theme.cur("error")};')
        self.entry.setProperty('bad', 'true')
        theme.repolish(self.entry)

    # ── rows ─────────────────────────────────────────────────────────────
    def add(self):
        raw = self.entry.text().replace(',', ' ').split()
        if not raw:
            self._reject(self._idle_text())
            return False
        if any(k != 'float' for k in self._kinds):
            return self._add_typed(raw)
        try:
            vals = [float(x) for x in raw]
        except ValueError:
            bad = [x for x in raw if not _is_number(x)]
            self._reject('not numbers: ' + ', '.join(bad))
            return False
        if len(vals) != self._arity:
            self._reject(f'expected {self._arity} numbers '
                         f'({"  ".join(self._columns)})')
            return False
        self.tree.addTopLevelItem(
            QTreeWidgetItem([f'{v:g}' for v in vals]))
        self.entry.clear()
        self._accept()
        self._on_change()
        return True

    def _add_typed(self, raw):
        """`add` for a table with a non-numeric column (D7)."""
        if len(raw) != self._arity:
            self._reject(f'expected {self._arity} values '
                         f'({"  ".join(self._columns)})')
            return False
        try:
            vals = [_parse_cell(k, x) for k, x in zip(self._kinds, raw)]
        except ValueError as exc:
            self._reject(str(exc))
            return False
        self.tree.addTopLevelItem(QTreeWidgetItem(
            [_fmt_cell(k, v) for k, v in zip(self._kinds, vals)]))
        self.entry.clear()
        self._accept()
        self._on_change()
        return True

    def remove(self):
        item = self.tree.currentItem()
        if item is None:
            self._reject('select a row in the list first')
            return False
        self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
        self._accept()
        self._on_change()
        return True

    def get(self):
        out = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            try:
                out.append(tuple(_parse_cell(k, it.text(c))
                                 for c, k in enumerate(self._kinds)))
            except ValueError:
                continue
        return out

    def set(self, tuples):
        """Replace the rows. Does NOT fire on_change - `set_case` drives
        this, and the caller revalidates once at the end. The entry is
        cleared too: a refused row left in it survived Open case while
        the hint went back to idle (P21, GUI QA 2026-09-27 V3)."""
        self.tree.clear()
        for row in tuples or []:
            self.tree.addTopLevelItem(QTreeWidgetItem(
                [_fmt_cell(k, v) for k, v in zip(self._kinds, row)]))
        self.entry.clear()
        self._accept()

    def count(self):
        return self.tree.topLevelItemCount()


def _is_number(text):
    try:
        float(text)
        return True
    except ValueError:
        return False


def _parse_cell(kind, text):
    """One table cell by its column kind: 'axis' -> 'x' | 'y' | 'z',
    anything else -> float. Raises ValueError with the reason."""
    if kind == 'axis':
        return fields.parse_plane_axis(text)
    try:
        return float(text)
    except ValueError:
        raise ValueError(f'not a number: {text}')


def _fmt_cell(kind, value):
    return str(value) if kind == 'axis' else f'{float(value):g}'


# ── file picker ──────────────────────────────────────────────────────────
class FilePicker(QWidget):
    """An entry bound to a Var plus a browse button. The dialog title is
    always specific (QA-16)."""

    def __init__(self, var, spec=None, parent=None):
        super().__init__(parent)
        spec = spec or {}
        self._var = var
        self._title = spec.get('title') or 'Open file'
        self._filter = spec.get('filter') or 'All files (*.*)'
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(GAP)
        self.entry = QLineEdit(var.get())
        self.entry.textEdited.connect(var._adopt)
        var._push = self._push
        lay.addWidget(self.entry, 1)
        lay.addWidget(button('', 'folder', width=34, height=30,
                             tooltip=self._title, on_click=self._pick,
                             icon_size=14))

    def _push(self, text):
        self.entry.blockSignals(True)
        try:
            self.entry.setText(text)
        finally:
            self.entry.blockSignals(False)

    def _pick(self):
        path = dialogs.open_file(self._title, self._filter, self)
        if path:                      # an empty result must not clear it
            self._var.set(path)


# ── the form ─────────────────────────────────────────────────────────────
class FieldForm(QWidget):
    """Two columns of titled cards built from `setup_spec.cards(dim)`."""

    def __init__(self, dim, on_change=None, mode='blastfoam', parent=None):
        super().__init__(parent)
        self.dim = int(dim)
        self._on_change = on_change or (lambda: None)
        self.v = {}                  # name -> Var / BoolVar
        self.points = {}             # name -> PointList
        self.rows = {}               # name -> (layout, index)
        self.widgets = {}            # name -> input widget
        self.labels = {}             # name -> QLabel (None for bool rows)
        self.cards = {}              # title -> Card
        self.notes = {}              # card title -> its note QLabel
        self._specs = {}             # name -> F
        self._card_of = {}           # name -> card title
        self._notifying = False
        self._pending = []
        self._bad = set()
        self._build()

    # ── construction ─────────────────────────────────────────────────────
    def _build(self):
        # the two columns side by side, and under them the cards that
        # span both (setup_spec.SPAN - the VTK card, owner decision P13)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(theme.PAD - 4)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(GAP)
        outer.addLayout(top, 1)
        self._cols, self._holders = [], []
        self._span_panes = []        # (QBoxLayout, left, right) per card
        for _ in (0, 1):
            box = QVBoxLayout()
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(theme.PAD - 4)
            holder = QWidget()
            holder.setLayout(box)
            # equal stretch alone lets the left column win, because its
            # label+input rows have the larger content minimum and the
            # right column's tables will shrink to nothing; the Tk form
            # used `uniform=` to force the two the same, so give both the
            # same floor (a 6-column obstacle table needs it)
            holder.setMinimumWidth(COL_MIN)
            top.addWidget(holder, 1)
            self._cols.append(box)
            self._holders.append(holder)
        wide = QVBoxLayout()
        wide.setContentsMargins(0, 0, 0, 0)
        wide.setSpacing(theme.PAD - 4)
        outer.addLayout(wide, 0)
        self._cols.append(wide)                 # index SPAN
        # (card, natural column, layout stretch) in spec order, which is
        # the reading order the single-column layout falls back to
        self._card_order = []
        for spec in cards(self.dim):
            card = Card(spec.title, pad=CARD_PAD, parent=self)
            self.cards[spec.title] = card
            card._blastlab_scope = spec.scope
            self._card_order.append(
                (card, spec.col, 1 if spec.field_rows else 0))
            self._cols[spec.col].addWidget(
                card, 1 if spec.field_rows else 0)
            self._fill_card(card, spec)
        for box in self._cols[:2]:
            box.addStretch(1)
        self._single = False
        self._watched = None

    # ── responsive columns ───────────────────────────────────────────────
    def _viewport(self):
        """The scroll viewport this form lives in, if any.

        Its width is the only honest measure of the room available. The
        form's OWN width is useless here: a scroll area with
        `setWidgetResizable(True)` sizes its child to
        `max(viewport, minimumSizeHint)`, so while the two columns
        demand 628 px the form reports 628 px however narrow the window
        gets, and its `resizeEvent` never fires."""
        p = self.parentWidget()
        while p is not None:
            if isinstance(p, QScrollArea):
                return p.viewport()
            p = p.parentWidget()
        return None

    def _avail_width(self):
        vp = self._viewport()
        return vp.width() if vp is not None else self.width()

    def _watch_viewport(self):
        vp = self._viewport()
        if vp is not None and vp is not self._watched:
            if self._watched is not None:
                self._watched.removeEventFilter(self)
            vp.installEventFilter(self)
            self._watched = vp

    def eventFilter(self, obj, event):
        if obj is self._watched and event.type() == QEvent.Resize:
            self._fit_columns()
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        self._watch_viewport()
        self._fit_columns()

    def _fit_columns(self):
        """Two columns need 2 x COL_MIN, and the Setup tab shares its
        width with the preview, so below about a 1290 px window they do
        not fit. The scroll column has no horizontal bar, so the excess
        was CLIPPED: measured 188 px of the right-hand cards unreachable
        at 1100x720, which is the window's own minimum size. Stack into
        one column instead, where everything stays reachable by the
        vertical scroll that is already there.

        The three dimension forms share a QStackedWidget, whose minimum
        is the LARGEST of its pages whether they are visible or not - so
        collapsing only the page on screen changed nothing, and all
        three have to move together."""
        avail = self._avail_width()
        single = avail < 2 * COL_MIN + GAP
        self._apply_single(single)
        self._fit_span(avail)
        stack = self.parentWidget()
        if isinstance(stack, QStackedWidget):
            for i in range(stack.count()):
                page = stack.widget(i)
                if isinstance(page, FieldForm) and page is not self:
                    page._apply_single(single)
                    page._fit_span(avail)

    def _fit_span(self, avail):
        """A spanning card (the VTK card) puts its two panes side by side
        when the width holds both minimums, else one above the other -
        so its full-word matrix headers (P13) are never clipped."""
        for box, left, right in self._span_panes:
            need = (left.minimumSizeHint().width()
                    + right.minimumSizeHint().width() + box.spacing()
                    + 2 * CARD_PAD)
            want = (QBoxLayout.LeftToRight if avail >= need
                    else QBoxLayout.TopToBottom)
            if box.direction() != want:
                box.setDirection(want)
                # a page the stack is not showing does not re-activate
                # its layouts, so the card and the page kept the side-by-
                # side minimum (measured 688 px at a 620 px viewport,
                # which clipped the whole stack): recompute up the chain
                w = left.parentWidget()
                while w is not None:
                    lay = w.layout()
                    if lay is not None:
                        lay.invalidate()
                        lay.activate()
                    w.updateGeometry()
                    if w is self:
                        break
                    w = w.parentWidget()

    def _relayout(self):
        """Recompute the form's layout minimum now, visible or not (see
        _apply_single)."""
        lay = self.layout()
        if lay is not None:
            lay.invalidate()
            lay.activate()

    def span_side_by_side(self, title):
        """True when the spanning card `title` shows its panes side by
        side (tests and the QA harness)."""
        card = self.cards.get(title)
        for box, left, _right in self._span_panes:
            if card is not None and card.isAncestorOf(left):
                return box.direction() == QBoxLayout.LeftToRight
        return False

    def _apply_single(self, single):
        if single == self._single:
            return
        self._single = single
        # a card hidden by the solver scope must stay hidden: adding a
        # widget to a layout under a visible parent shows it again
        hidden = {id(c): c.isHidden() for c, _col, _s in self._card_order}
        for box in self._cols:
            while box.count():
                item = box.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(self)
        for card, col, stretch in self._card_order:
            self._cols[0 if single else col].addWidget(card, stretch)
            card.setVisible(not hidden[id(card)])
        for box in self._cols[:2]:
            box.addStretch(1)
        # a hidden holder contributes nothing to the minimum, which is
        # what lets the form shrink to the viewport at all
        self._holders[1].setVisible(not single)
        # the columns sit in a nested layout (the spanning cards below
        # them), and a page the stack is not showing keeps its outer
        # layout's cached minimum - measured 612 px on a hidden 1D page
        # in one column, which widened the whole stack. Recompute now.
        self._relayout()
        # and the scroll area has to be told: it sized us before the
        # switch, so without this the width stays at the OLD minimum
        # (measured: minimumSizeHint drops 628 -> 310 while width stays
        # 628, i.e. still clipped) and only a later unrelated resize
        # would fix it
        self.updateGeometry()
        vp = self._viewport()
        if vp is not None:
            self.resize(max(vp.width(), self.minimumSizeHint().width()),
                        self.height())

    def single_column(self):
        return self._single

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_columns()

    def _fill_card(self, card, spec):
        if spec.rows and spec.rows[0].kind == 'points':
            f = spec.rows[0]
            pl = PointList(f.cols, self._on_change, rows=f.rows)
            self.points[f.name] = pl
            self.widgets[f.name] = pl
            self._specs[f.name] = f
            self._card_of[f.name] = spec.title
            card.add(pl, 1)
            return
        if spec.col == SPAN:
            # owner decision P13: a card across both columns - its rows on
            # the left, its matrix on the right, one above the other when
            # the width does not hold both (_fit_span)
            left, right = QWidget(), QWidget()
            panes = QBoxLayout(QBoxLayout.LeftToRight)
            panes.setContentsMargins(0, 0, 0, 0)
            panes.setSpacing(theme.PAD)
            panes.addWidget(left, 1, Qt.AlignTop)
            panes.addWidget(right, 1, Qt.AlignTop)
            card.add_layout(panes)
            self._span_panes.append((panes, left, right))
            self._fill_grid(_grid(left), spec,
                            [f for f in spec.rows if f.kind != 'matrix'])
            self._fill_grid(_grid(right), spec,
                            [f for f in spec.rows if f.kind == 'matrix'],
                            note=False)
            return
        grid = _grid()
        card.add_layout(grid)
        self._fill_grid(grid, spec, spec.rows)

    def _fill_grid(self, grid, spec, rows, note=True):
        """Lay `rows` of card `spec` into `grid`: caption + input pairs,
        wide rows (a table, the matrix) across both grid columns, and the
        card's note above the first wide row (or at the end)."""
        pairs = max(1, spec.grid)
        for c in range(pairs):
            grid.setColumnMinimumWidth(c * 2, LABEL_WRAP if pairs == 1
                                       else 0)
            grid.setColumnStretch(c * 2, 0)
            grid.setColumnStretch(c * 2 + 1, 1)
        line = 0                  # the next grid row of a one-pair card
        noted = not (note and spec.note)

        def add_note(row):
            # the card's note (P22: the VTK card's "seconds" line), under
            # the label+input rows and above any wide table
            lbl = label(spec.note, 'small', wrap=True)
            grid.addWidget(lbl, row, 0, 1, 2)
            self.notes[spec.title] = lbl

        for i, f in enumerate(rows):
            if not noted and f.kind in ('points', 'matrix') and pairs == 1:
                add_note(line)
                line, noted = line + 1, True
            r, c = ((i // pairs, (i % pairs) * 2) if pairs > 1
                    else (line, 0))
            line += 1
            if f.kind in ('points', 'matrix'):
                # a wide row (OUT-2): the caption above, the table across
                # both columns below
                lbl = label(f.label, 'muted', wrap=True)
                grid.addWidget(lbl, r, 0, 1, 2)
                grid.addWidget(self._make_widget(f), r + 1, 0, 1, 2)
                line += 1
                self.labels[f.name] = lbl
                self.rows[f.name] = (grid, r)
                self._card_of[f.name] = spec.title
                continue
            w = self._make_widget(f)
            if f.kind == 'bool':
                # the caption lives on the checkbox itself
                grid.addWidget(w, r, c, 1, 2)
                self.labels[f.name] = None
            else:
                lbl = label(f.label, 'muted', wrap=(pairs == 1))
                if pairs == 1:
                    lbl.setFixedWidth(LABEL_WRAP)
                lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                grid.addWidget(lbl, r, c)
                grid.addWidget(w, r, c + 1)
                self.labels[f.name] = lbl
            self.rows[f.name] = (grid, r)
            self._card_of[f.name] = spec.title
        if not noted:
            add_note(line)

    def _make_widget(self, f):
        self._specs[f.name] = f
        if f.kind == 'points':
            # a point list inside a mixed card (the VTK plane table)
            pl = PointList(f.cols, self._on_change, rows=f.rows,
                           kinds=f.kinds)
            self.points[f.name] = pl
            self.widgets[f.name] = pl
            return pl
        if f.kind == 'bool':
            var = BoolVar(f.name, f.default)
            w = QCheckBox(f.label)
            w.setChecked(var.get())
            # read the widget rather than trust the signal's argument:
            # `clicked` is declared `clicked(bool = false)`, and the
            # binding does not always deliver the bool
            w.clicked.connect(
                lambda *_a, v=var, w=w: v._adopt(w.isChecked()))
            var._push = lambda val, w=w: _silently(w.setChecked, w, val)
        elif f.kind == 'choice':
            var = Var(f.name, f.default)
            w = QComboBox()
            w.addItems([str(x) for x in f.values])
            w.setCurrentText(var.get())
            w.activated.connect(
                lambda _i, v=var, w=w: v._adopt(w.currentText()))
            var._push = lambda val, w=w: _silently(w.setCurrentText, w, val)
        elif f.kind == 'file':
            var = Var(f.name, f.default)
            w = FilePicker(var, f.file)
        elif f.kind == 'radio':
            var = Var(f.name, f.default)
            w = RadioRow(var, f.values)
        elif f.kind == 'matrix':
            var = MatrixVar(f.name, self.dim, f.default)
            w = MatrixGrid(var, self.dim, f.values, f.cols)
        else:                                   # text | float | int
            var = Var(f.name, _fmt(f.default))
            w = QLineEdit(var.get())
            w.textEdited.connect(var._adopt)
            var._push = lambda val, w=w: _silently(w.setText, w, val)
        var._form = self
        # every field restarts the caller's debounce, exactly as the Tk
        # write trace did
        var.trace_add('write', self._on_change)
        self.v[f.name] = var
        if f.kind not in ('bool', 'matrix'):
            w.setMinimumWidth(INPUT_MIN)
        self.widgets[f.name] = w
        return w

    # ── fan-out ──────────────────────────────────────────────────────────
    def _dispatch(self, var):
        """Run `var`'s traces. A `set()` from inside a trace queues here
        and runs after the current fan-out (see the module docstring)."""
        self._pending.append(var)
        if self._notifying:
            return
        self._notifying = True
        try:
            while self._pending:
                v = self._pending.pop(0)
                for cb in list(v._traces):
                    try:
                        cb()
                    except Exception as exc:    # one bad hook must not
                        print(f'[ui] field trace {v.name!r} '   # strand
                              f'failed: {exc!r}')               # the rest
        finally:
            self._notifying = False

    def on_field(self, name, callback):
        """Run `callback` whenever `name` changes (the imperative hooks)."""
        return self.v[name].trace_add('write', callback)

    # ── validation feedback ──────────────────────────────────────────────
    def mark_fields(self, names):
        """Red-border exactly `names` and clear whatever was marked
        before."""
        names = set(names or ())
        for name in self._bad | names:
            w = self.widgets.get(name)
            if w is None:
                continue
            w.setProperty('bad', 'true' if name in names else 'false')
            theme.repolish(w)
        self._bad = names

    @property
    def bad(self):
        return set(self._bad)

    # ── scope / sub-groups ───────────────────────────────────────────────
    def apply_scope(self, mode, groups=None):
        """Show a row iff it belongs to this solver AND its group is on;
        hide whole cards the same way. Values are never touched, so
        switching back restores what the user typed."""
        groups = groups or {}
        # OUT-1: a card whose every row is a hidden file-name row (the 1D
        # Outputs card) would be an empty frame
        emptied = set()
        for t in self.cards:
            names = [n for n, ct in self._card_of.items() if ct == t]
            if names and all(n in HIDDEN_ROWS for n in names):
                emptied.add(t)
        for title, card in self.cards.items():
            scope = getattr(card, '_blastlab_scope', None)
            card.setVisible(scope in (None, mode) and title not in emptied)
        for name, f in self._specs.items():
            on = f.scope in (None, mode) and name not in HIDDEN_ROWS
            if on and f.group is not None:
                on = bool(groups.get(f.group, True))
            self._set_row_visible(name, on)

    def _set_row_visible(self, name, on):
        entry = self.rows.get(name)
        if entry is None:                       # a points card: whole card
            return
        grid, row = entry
        on = bool(on)
        for w in (self.labels.get(name), self.widgets.get(name)):
            if w is not None:
                w.setVisible(on)
        # a hidden widget contributes no height, but the grid would keep
        # the row's spacing; zero it so the card really closes up
        try:
            grid.setRowMinimumHeight(row, 0)
        except Exception:
            pass

    def row_visible(self, name):
        w = self.widgets.get(name)
        return bool(w is not None and not w.isHidden())

    def card_visible(self, title):
        card = self.cards.get(title)
        return bool(card is not None and not card.isHidden())

    # ── labels ───────────────────────────────────────────────────────────
    def set_label(self, name, text):
        lbl = self.labels.get(name)
        if lbl is not None:
            lbl.setText(text)

    def label_text(self, name):
        lbl = self.labels.get(name)
        return lbl.text() if lbl is not None else ''

    def set_enabled(self, name, on):
        w = self.widgets.get(name)
        if w is not None:
            w.setEnabled(bool(on))

    def is_enabled(self, name):
        w = self.widgets.get(name)
        return bool(w is not None and w.isEnabled())


def _grid(parent=None):
    """A card's row grid. A grid, not a QFormLayout: QFormLayout
    over-constrained (a fixed caption column plus a field that wants to
    grow, inside a card narrower than their sum) lays the field ON TOP of
    the label - measured: label x=17 w=132, field x=21 w=272 on the same
    row - so a caption showed one character. A grid with an explicit
    caption column and a stretching input column cannot do that, and it
    is what the boundary card already used. `parent` - a pane widget of a
    spanning card - gets it as its layout."""
    grid = QGridLayout(parent) if parent is not None else QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(GAP)
    grid.setVerticalSpacing(4)
    return grid


def _silently(setter, widget, value):
    widget.blockSignals(True)
    try:
        setter(value)
    finally:
        widget.blockSignals(False)


def _fmt(value):
    """Defaults reach the form as the Tk form formatted them."""
    if isinstance(value, bool) or value is None:
        return '' if value is None else str(value)
    if isinstance(value, float):
        return f'{value:g}'
    return str(value)
