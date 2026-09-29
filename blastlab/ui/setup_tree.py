"""GUI-5 (plan §5.1, board BC_Combined lines 58-121): the Setup screen's
model-tree column.

A `MODEL · <dim>` header, one `components.TreeRow` per node (number ·
title · mono summary · status mark), child rows under 04 Structure and
05 Gauges (one per obstacle / gauge), then + Gauge / + Obstacle and the
`Case OK · N notes` pill. The widget only displays: `SetupPanel` decides
what the rows say and what a click does.
"""

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

from . import theme
from .components import TreeRow

#: the column width of board BC_Combined (plan §5). It gives way down to
#: TREE_MIN only when the window is too narrow for the three columns
#: (a wide properties page on a small window); the summaries elide.
TREE_W = 280
TREE_MIN = 224

#: the case pill's icon per state: (theme glyph, palette key)
_PILL_ICON = {'ok': ('check', 'ok'), 'warn': ('warning', 'warn'),
              'error': ('error', 'danger')}


class _ChildRow(QFrame):
    """A gauge or obstacle under its node (board lines 83-99): a marker
    (cyan diamond for a gauge, a bar for an obstacle), the name and a
    mono position at the right. Emits `clicked()`."""

    clicked = Signal()

    def __init__(self, kind, name, value, parent=None):
        super().__init__(parent)
        self.setObjectName('treechild')
        self.kind = kind
        self.setFixedHeight(30)
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(44, 0, 10, 0)
        lay.setSpacing(10)
        self.marker = QLabel('◇' if kind == 'gauge' else '▮')
        self.marker.setObjectName('treemark_' + kind)
        self.name = QLabel(str(name))
        self.name.setObjectName('childname')
        self.value = QLabel(str(value))
        self.value.setObjectName('childval')
        lay.addWidget(self.marker)
        lay.addWidget(self.name)
        lay.addStretch(1)
        lay.addWidget(self.value)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton \
                and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class SetupTree(QFrame):
    """The tree column. Signals carry node ids (`setup_nodes.Node.id`)."""

    node_clicked = Signal(str)
    child_clicked = Signal(str, int)          # node id, row index
    add_gauge = Signal()
    add_obstacle = Signal()
    pill_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('setuptree')
        self.setMinimumWidth(TREE_MIN)
        self.setMaximumWidth(TREE_W)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 14, 12, 12)
        outer.setSpacing(8)
        self.header = QLabel('MODEL')
        self.header.setObjectName('eyebrow')
        _letter_space(self.header)
        outer.addWidget(self.header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        self._rows_lay = QVBoxLayout(body)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(2)
        self._rows_lay.addStretch(1)
        self._scroll.setWidget(body)
        outer.addWidget(self._scroll, 1)

        adds = QHBoxLayout()
        adds.setSpacing(8)
        self.add_gauge_btn = _add_button('Gauge', self.add_gauge.emit)
        self.add_obstacle_btn = _add_button('Obstacle',
                                            self.add_obstacle.emit)
        adds.addWidget(self.add_gauge_btn)
        adds.addWidget(self.add_obstacle_btn)
        outer.addLayout(adds)

        self.pill = QPushButton('Case OK')
        self.pill.setObjectName('casepill')
        self.pill.setProperty('state', 'ok')
        self.pill.setFixedHeight(42)
        self.pill.setCursor(Qt.PointingHandCursor)
        self.pill.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.pill.clicked.connect(lambda *_: self.pill_clicked.emit())
        outer.addWidget(self.pill)
        self._pill_icon()
        theme.signals.changed.connect(self._pill_icon)

        self.rows = {}              # node id -> TreeRow
        self._kids = {}             # node id -> (QWidget holder, [rows])
        self._selected = None

    def sizeHint(self):
        return QSize(TREE_W, super().sizeHint().height())

    # ── rows ─────────────────────────────────────────────────────────────
    def set_nodes(self, nodes):
        """Rebuild the rows: `nodes` = [(id, number, title)] in order."""
        lay = self._rows_lay
        while lay.count() > 1:                  # keep the trailing stretch
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.rows, self._kids = {}, {}
        for node_id, number, title in nodes:
            row = TreeRow(node_id, number, title)
            row.clicked.connect(self.node_clicked.emit)
            lay.insertWidget(lay.count() - 1, row)
            self.rows[node_id] = row
            holder = QWidget()
            hl = QVBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(0)
            holder.setVisible(False)
            lay.insertWidget(lay.count() - 1, holder)
            self._kids[node_id] = (holder, [])
        self._selected = None

    def set_selected(self, node_id):
        self._selected = node_id
        for nid, row in self.rows.items():
            row.set_selected(nid == node_id)

    def selected(self):
        return self._selected

    def set_node_visible(self, node_id, on):
        row = self.rows.get(node_id)
        if row is None:
            return
        row.setVisible(bool(on))
        holder, kids = self._kids[node_id]
        holder.setVisible(bool(on) and bool(kids))

    def node_visible(self, node_id):
        row = self.rows.get(node_id)
        return bool(row is not None and not row.isHidden())

    def set_summary(self, node_id, text):
        """The mono line under a row. It is elided to the row's width
        (full text in the tooltip): a label's minimum is its whole text,
        and 'linear · no afterburn · CFL 0.4' in mono is wider than the
        280 px column leaves it (measured 36 px over)."""
        row = self.rows.get(node_id)
        if row is None:
            return
        row.set_caption(text)
        cap = row.caption
        cap.setToolTip(str(text))
        if not hasattr(cap, '_full'):
            cap.setMinimumWidth(0)
            cap.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            cap.installEventFilter(self)
        cap._full = str(text)
        self._elide(cap)

    def summary(self, node_id):
        """The full summary text of a row (tests)."""
        row = self.rows.get(node_id)
        return getattr(row.caption, '_full', '') if row is not None else ''

    @staticmethod
    def _elide(cap):
        full = getattr(cap, '_full', cap.text())
        w = cap.width()
        text = (cap.fontMetrics().elidedText(full, Qt.ElideRight, w)
                if w > 0 else full)
        if text != cap.text():
            cap.setText(text)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Resize, QEvent.FontChange,
                            QEvent.StyleChange) and hasattr(obj, '_full'):
            self._elide(obj)
        return super().eventFilter(obj, event)

    def set_status(self, node_id, status):
        row = self.rows.get(node_id)
        if row is not None:
            row.set_status(status)

    def set_children(self, node_id, kind, items):
        """Replace the child rows of `node_id`: `items` = [(name, value)],
        `kind` 'gauge' | 'obstacle'."""
        if node_id not in self._kids:
            return
        holder, old = self._kids[node_id]
        if [(k.name.text(), k.value.text()) for k in old] == \
                [(str(n), str(v)) for n, v in items]:
            return                              # unchanged: no flicker
        lay = holder.layout()
        for k in old:
            lay.removeWidget(k)
            k.setParent(None)
            k.deleteLater()
        kids = []
        for i, (name, value) in enumerate(items):
            k = _ChildRow(kind, name, value)
            k.clicked.connect(lambda n=node_id, i=i:
                              self.child_clicked.emit(n, i))
            lay.addWidget(k)
            kids.append(k)
        self._kids[node_id] = (holder, kids)
        row = self.rows.get(node_id)
        holder.setVisible(bool(kids) and row is not None
                          and not row.isHidden())

    def children(self, node_id):
        """[(name, value)] as shown (tests)."""
        return [(k.name.text(), k.value.text())
                for k in self._kids.get(node_id, (None, []))[1]]

    def child_row(self, node_id, index):
        return self._kids[node_id][1][index]

    # ── the pill and the add buttons ─────────────────────────────────────
    def set_pill(self, state, text):
        """`state` 'ok' | 'warn' | 'error' (plan §5.1: ok_bg/ok_border,
        danger when invalid). The state colour is the icon's (board line
        117: a 16 px mark in `ok`); the text keeps 4.5:1."""
        self.pill.setText(text)
        self.pill.setProperty('state', state)
        self._pill_icon()
        theme.repolish(self.pill)

    def _pill_icon(self, _mode=None):
        state = self.pill.property('state') or 'ok'
        name, colour = _PILL_ICON.get(state, _PILL_ICON['ok'])
        self.pill.setIcon(theme.icon(name, 16, color=colour))
        self.pill.setIconSize(QSize(16, 16))

    def set_adds_visible(self, gauge, obstacle):
        self.add_gauge_btn.setVisible(bool(gauge))
        self.add_obstacle_btn.setVisible(bool(obstacle))


def _add_button(text, fn):
    b = QPushButton(f'+  {text}')
    b.setObjectName('treeadd')
    b.setFixedHeight(36)
    b.setCursor(Qt.PointingHandCursor)
    b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    b.clicked.connect(lambda *_: fn())
    return b


def _letter_space(lbl, pct=110):
    """Caps eyebrows are letter-spaced on the boards; QSS cannot do it,
    and the letter spacing survives the app-wide font rule (D6)."""
    f = lbl.font()
    f.setLetterSpacing(QFont.PercentageSpacing, pct)
    lbl.setFont(f)
