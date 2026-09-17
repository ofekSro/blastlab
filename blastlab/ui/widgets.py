"""Shared widgets of the Qt front-end: cards, segmented switches, stat
chips, scroll columns and small factories, all styled through the
object names `theme.qss` knows about."""

from PySide6.QtCore import QSize, Qt, Signal    # noqa: F401
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from . import theme
from .theme import GAP, PAD


# ── labels / buttons ─────────────────────────────────────────────────────
def label(text='', kind='body', wrap=False, align=None):
    """QLabel with an object name the style sheet colours:
    'h1' | 'h2' | 'body' | 'muted' | 'small'."""
    lbl = QLabel(text)
    if kind in ('h1', 'h2', 'muted', 'small'):
        lbl.setObjectName(kind)
    if kind == 'h1':
        lbl.setFont(theme.font('h1'))
    elif kind == 'h2':
        lbl.setFont(theme.font('h2'))
    elif kind == 'small':
        lbl.setFont(theme.font('small'))
    if wrap:
        lbl.setWordWrap(True)
    if align is not None:
        lbl.setAlignment(align)
    return lbl


def button(text, icon=None, kind='default', width=None, height=None,
           tooltip=None, on_click=None, icon_size=15):
    """QPushButton styled as 'default' | 'primary' | 'danger' | 'nav' |
    'quiet' | 'link'. `icon` is a theme glyph name."""
    b = QPushButton(text)
    if kind != 'default':
        b.setObjectName(kind)
    if icon:
        colour = 'white' if kind in ('primary', 'danger') else None
        b.setIcon(theme.icon(icon, icon_size, color=colour))
        b.setIconSize(QSize(icon_size, icon_size))
        b._blastlab_icon = (icon, icon_size, colour)
    if width is not None:
        b.setFixedWidth(width)
    if height is not None:
        b.setFixedHeight(height)
    if tooltip:
        b.setToolTip(tooltip)
    if on_click is not None:
        b.clicked.connect(lambda *_: on_click())
    b.setCursor(Qt.PointingHandCursor)
    return b


def set_button_kind(b, kind):
    """Re-style a button (e.g. Stop: inert grey -> armed red)."""
    b.setObjectName('' if kind == 'default' else kind)
    ic = getattr(b, '_blastlab_icon', None)
    if ic is not None:
        name, size, _colour = ic
        colour = 'white' if kind in ('primary', 'danger') else None
        b.setIcon(theme.icon(name, size, color=colour))
        b._blastlab_icon = (name, size, colour)
    theme.repolish(b)


def refresh_icons(root):
    """Re-tint every `button()` icon under `root` for the current mode
    (icons are pixmaps, so a theme switch has to re-assign them)."""
    for b in root.findChildren(QPushButton):
        ic = getattr(b, '_blastlab_icon', None)
        if ic is not None:
            name, size, colour = ic
            b.setIcon(theme.icon(name, size, color=colour))


def hbox(parent=None, spacing=GAP, margins=(0, 0, 0, 0)):
    lay = QHBoxLayout(parent) if parent is not None else QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    return lay


def vbox(parent=None, spacing=GAP, margins=(0, 0, 0, 0)):
    lay = QVBoxLayout(parent) if parent is not None else QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    return lay


# ── Card ─────────────────────────────────────────────────────────────────
class Card(QFrame):
    """Rounded panel with a subtle border and optional title. Children go
    into `self.body` (its QVBoxLayout is `self.body_layout`)."""

    def __init__(self, title=None, pad=PAD, parent=None):
        super().__init__(parent)
        self.setObjectName('card')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(pad, 12 if title else 12, pad, 12)
        outer.setSpacing(4)
        self.title_label = None
        if title:
            lbl = label(title, 'h2', wrap=True)
            lbl.setToolTip(title)
            outer.addWidget(lbl)
            self.title_label = lbl
        self.body = QWidget(self)
        self.body.setObjectName('cardbody')
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(GAP)
        outer.addWidget(self.body, 1)

    def add(self, widget, stretch=0):
        self.body_layout.addWidget(widget, stretch)
        return widget

    def add_layout(self, lay, stretch=0):
        self.body_layout.addLayout(lay, stretch)
        return lay


# ── Segmented switch ─────────────────────────────────────────────────────
class Segmented(QWidget):
    """A row of exclusive toggle buttons. `changed(str)` fires only on a
    user click; `set()` is silent (as the Tk segmented button was)."""

    changed = Signal(str)

    def __init__(self, values, height=32, small=False, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._btns = {}
        values = list(values)
        for i, v in enumerate(values):
            b = QToolButton()
            b.setObjectName('seg')
            b.setText(str(v))
            b.setCheckable(True)
            b.setFixedHeight(height)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setFont(theme.font('small' if small else 'body'))
            b.setCursor(Qt.PointingHandCursor)
            if i == 0:
                b.setProperty('pos', 'first')
            if i == len(values) - 1:
                b.setProperty('pos', 'last' if i else 'both')
            if len(values) == 1:
                b.setProperty('pos', 'first')
            self._group.addButton(b)
            lay.addWidget(b)
            self._btns[str(v)] = b
            b.clicked.connect(lambda _c=False, v=str(v): self.changed.emit(v))
        if values:
            self._btns[str(values[0])].setChecked(True)

    def set(self, value):
        b = self._btns.get(str(value))
        if b is not None:
            b.setChecked(True)

    def get(self):
        for v, b in self._btns.items():
            if b.isChecked():
                return v
        return None

    def values(self):
        return list(self._btns)

    def set_enabled(self, value, enabled):
        b = self._btns.get(str(value))
        if b is not None:
            b.setEnabled(bool(enabled))


# ── Stat chip ────────────────────────────────────────────────────────────
class Chip(QFrame):
    """Small stat chip: muted caption over a bold value."""

    def __init__(self, caption, parent=None):
        super().__init__(parent)
        self.setObjectName('chip')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(0)
        cap = label(caption, 'small')
        self.value = QLabel('—')
        self.value.setFont(theme.font('chip'))
        lay.addWidget(cap)
        lay.addWidget(self.value)

    def set(self, text):
        self.value.setText(str(text))


# ── Scroll column ────────────────────────────────────────────────────────
class ScrollColumn(QScrollArea):
    """Vertical scroll area over a transparent column; add widgets to
    `self.layout_` and finish with `add_stretch()`."""

    def __init__(self, parent=None, spacing=GAP):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.layout_ = QVBoxLayout(self.content)
        self.layout_.setContentsMargins(0, 0, 4, 0)
        self.layout_.setSpacing(spacing)
        self.setWidget(self.content)

    def add(self, widget, stretch=0):
        self.layout_.addWidget(widget, stretch)
        return widget

    def add_layout(self, lay):
        self.layout_.addLayout(lay)
        return lay

    def add_stretch(self):
        self.layout_.addStretch(1)


class WrapRow(QWidget):
    """A row of widgets that WRAPS to a second line instead of letting
    Qt shrink them until their labels are clipped.

    Qt has no flow layout, and an ordinary QHBoxLayout compresses its
    children when short of room - which for a push button means the text
    is silently cut. Measured on the Results export row: four of the
    eight buttons showed 'Animatio', 'Summary C', 'Gauges TS' and
    'Field CSV' at EVERY window size, because they were pinned to 106 px
    while needing 116 to 155. The Tk row had the same defect once
    (N2-10) and was fixed by widening one button, which only moved the
    problem.

    Children keep their own sizeHint here, and the rows are filled
    greedily, so nothing is ever narrower than its text.
    """

    def __init__(self, spacing=GAP, parent=None):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self._plan = None
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(spacing)
        self._rows = []

    def add(self, widget, hidden=False):
        self._items.append(widget)
        widget.setParent(self)
        if hidden:
            widget.hide()
        self._relayout(force=True)
        if hidden:
            widget.hide()
        return widget

    def widgets(self):
        return list(self._items)

    def rows(self):
        """How many lines the row currently occupies."""
        return max(1, len(self._rows))

    def _plan_rows(self, avail):
        rows, cur, used = [], [], 0
        for w in self._items:
            need = w.sizeHint().width()
            if cur and used + self._spacing + need > avail:
                rows.append(cur)
                cur, used = [w], need
            else:
                used += (self._spacing if cur else 0) + need
                cur.append(w)
        if cur:
            rows.append(cur)
        return rows

    def _relayout(self, force=False):
        avail = max(1, self.width())
        plan = self._plan_rows(avail)
        key = [[id(w) for w in row] for row in plan]
        if key == self._plan and not force:
            return
        self._plan = key
        # adding a widget to a layout under a visible parent shows it,
        # so a child the caller had hidden must be put back afterwards.
        # The AMR cell chip is hidden until a level map arrives, and
        # every resize was bringing it back.
        hidden = {id(w): w.isHidden() for w in self._items}
        while self._outer.count():
            item = self._outer.takeAt(0)
            lay = item.layout()
            if lay is not None:
                while lay.count():
                    sub = lay.takeAt(0)
                    if sub.widget() is not None:
                        sub.widget().setParent(self)
                lay.deleteLater()
        self._rows = []
        for row in plan:
            lay = QHBoxLayout()
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(self._spacing)
            for w in row:
                lay.addWidget(w)
                w.setVisible(not hidden[id(w)])
            lay.addStretch(1)
            self._outer.addLayout(lay)
            self._rows.append(lay)
        # the row is taller now, and only we know it
        self.updateGeometry()

    def _row_height(self):
        return max((w.sizeHint().height() for w in self._items),
                   default=0)

    def _height_of(self, plan):
        n = max(1, len(plan))
        return n * self._row_height() + (n - 1) * self._spacing

    def minimumSizeHint(self):
        """The WIDEST single child, not the sum of them.

        This is the whole reason the wrap works. The nested layouts
        report the sum as their minimum, so the parent refused to squeeze
        the row below one line - measured: the row stayed 952 px wide
        inside a 500 px panel and simply overflowed, which is the
        clipping this class exists to avoid. Reporting one child's width
        lets the parent shrink us, which fires resizeEvent, which
        re-plans into more rows.
        """
        if not self._items:
            return super().minimumSizeHint()
        widest = max(w.sizeHint().width() for w in self._items)
        return QSize(widest,
                     self._height_of(self._plan_rows(max(1, self.width()))))

    def sizeHint(self):
        if not self._items:
            return super().sizeHint()
        total = (sum(w.sizeHint().width() for w in self._items)
                 + self._spacing * (len(self._items) - 1))
        return QSize(total,
                     self._height_of(self._plan_rows(max(1, self.width()))))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()


def hsep():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f'color: {theme.cur("border")};')
    return f


def spacer(w=0, h=0):
    s = QWidget()
    s.setFixedSize(max(0, w), max(0, h))
    return s
