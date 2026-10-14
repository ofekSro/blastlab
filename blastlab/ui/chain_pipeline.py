"""GUI-9 (plan §8.1, board Chain lines 53-94): the Chain screen's top
section - the route buttons and the pipeline of stage cards joined by
hand-off arrows.

Display only: `ChainPanel` decides what each card says (from
`chain_route` and the live checks) and what a click does. Colours come
from `theme` through object-name QSS rules (D6); the arrow is painted in
`paintEvent` (plan §11).
"""

from PySide6.QtCore import QEvent, QPointF, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from . import chain_route, theme
from .results_list import ElidedLabel

#: the board's card width (line 65) and the narrowest it gives way to
CARD_W = 308
CARD_MIN = 200
#: the link between two cards: 118 px with three stages, 200 with two
#: (board script `linkWidth`); it gives way to LINK_MIN
LINK_W3 = 118
LINK_W2 = 200
LINK_MIN = 64

#: the card's state line per `state`: (palette key of the dot and text)
STATE_COLOUR = {'ok': 'ok', 'warn': 'warn', 'error': 'danger'}


# ── the route buttons (board lines 55-59) ────────────────────────────────
class RouteBar(QFrame):
    """Four checkable, exclusive buttons in a 38 px group, one per
    `chain_route.ROUTES` entry. `picked(key)` fires on a click only;
    `set(key)` is silent."""

    picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('chainroutes')
        self.setFixedHeight(38)
        lay = QHBoxLayout(self)
        # 1 px border + 2 px + 32 px button + 2 px + 1 px = 38 (the plan's
        # group height; the board's padding 3 would make it 40)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)
        self.btns = {}
        for key, text, _dims in chain_route.ROUTES:
            b = QPushButton(text)
            b.setObjectName('chainroute')
            b.setCheckable(True)
            b.setFixedHeight(32)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self.picked.emit(k))
            self._grp.addButton(b)
            lay.addWidget(b)
            self.btns[key] = b

    def set(self, key):
        for k, b in self.btns.items():
            if b.isChecked() != (k == key):
                b.setChecked(k == key)


class _MetaLabel(QLabel):
    """The card's mono key line (D26): it wraps to a second line when it
    is wider than the card instead of eliding, and never holds the card
    wider. The whole text stays the tooltip. The height follows the lines
    it needs (one or two), so a roomy card keeps its board height."""

    LINES = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full = ''
        self.setWordWrap(True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)

    def setText(self, text):                         # noqa: N802 (Qt)
        self._full = str(text or '')
        QLabel.setText(self, self._full)
        self._fit()

    def full_text(self):
        return self._full

    def set_tip(self, tip):
        self.setToolTip(str(tip or ''))

    def lines(self):
        """The lines the text needs at the current width (at most LINES)."""
        fm = self.fontMetrics()
        w = max(self.width(), 1)
        flags = Qt.TextWordWrap | Qt.AlignLeft
        h = fm.boundingRect(0, 0, w, 10000, int(flags), self._full).height()
        return max(1, min(self.LINES, -(-h // max(fm.lineSpacing(), 1))))

    def _fit(self):
        fm = self.fontMetrics()
        self.setFixedHeight(self.lines() * fm.lineSpacing() + 2)

    def resizeEvent(self, event):                    # noqa: N802 (Qt)
        super().resizeEvent(event)
        self._fit()

    def changeEvent(self, event):                    # noqa: N802 (Qt)
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._fit()


# ── a stage card (board lines 65-77) ─────────────────────────────────────
class StageCard(QFrame):
    """Number · title · solver chip / the mono key line / `● case OK`
    and the stage folder. Emits `clicked(dim)`."""

    clicked = Signal(int)

    def __init__(self, dim, parent=None):
        super().__init__(parent)
        self.setObjectName('stagecard')
        self.dim = int(dim)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(CARD_MIN)
        self.setMaximumWidth(CARD_W)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        self.num = QLabel('01')
        self.num.setObjectName('stagenum')
        self.title = ElidedLabel('', mode=Qt.ElideRight)
        self.title.setObjectName('stagetitle')
        self.chip = QLabel('')
        self.chip.setObjectName('stagechip')
        top.addWidget(self.num)
        top.addWidget(self.title, 1)
        top.addWidget(self.chip)
        lay.addLayout(top)
        self.key = _MetaLabel()
        self.key.setObjectName('stagekey')
        lay.addWidget(self.key)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(8)
        self.state = ElidedLabel('', mode=Qt.ElideRight)
        self.state.setObjectName('stagestate')
        self.folder = QLabel('\\' + f'{self.dim}d')
        self.folder.setObjectName('stagefolder')
        bottom.addWidget(self.state, 1)
        bottom.addWidget(self.folder)
        lay.addLayout(bottom)
        self._state = None
        self.set_selected(False)
        self.set_state('ok', '● case OK')

    def sizeHint(self):
        return QSize(CARD_W, super().sizeHint().height())

    def set_number(self, text):
        self.num.setText(str(text))

    def set_title(self, text):
        self.title.setText(text)

    def set_solver(self, text):
        self.chip.setText(str(text))

    def set_key(self, text):
        """The key line: wrapped onto a second line when it is wider than
        the card (D26), the whole of it in the tooltip."""
        self.key.setText(text)
        self.key.set_tip(text)

    def key_text(self):
        return self.key.full_text()

    def set_state(self, state, text):
        """`state` 'ok' | 'warn' | 'error'; `text` e.g. `● 1 error`."""
        self._state = state if state in STATE_COLOUR else 'ok'
        self.state.setText(text)
        self.state.setProperty('state', self._state)
        theme.repolish(self.state)

    def state_text(self):
        return self.state.full_text()

    def state_key(self):
        return self._state

    def set_selected(self, on):
        self.setProperty('selected', 'true' if on else 'false')
        self.num.setProperty('selected', 'true' if on else 'false')
        theme.repolish(self)
        theme.repolish(self.num)

    def selected(self):
        return self.property('selected') == 'true'

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton \
                and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.dim)
        super().mouseReleaseEvent(event)


# ── the hand-off arrow (board lines 78-84) ───────────────────────────────
class _Arrow(QWidget):
    """The orange 1.6 px arrow, painted (board: an SVG path)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(14)
        self.setMinimumWidth(10)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        theme.signals.changed.connect(self.update)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # the board's orange; in light mode `accent` is 2.58:1 on `bg`,
        # under the 3:1 a graphic needs, so the darker accent_text (4.55)
        pen = QPen(theme.qcolor('accent' if theme.mode() == 'dark'
                                else 'accent_text'), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        w, h = self.width(), self.height()
        y = h / 2.0
        p.drawLine(QPointF(2, y), QPointF(w - 3, y))
        p.drawPolyline([QPointF(w - 9, y - 5), QPointF(w - 2, y),
                        QPointF(w - 9, y + 5)])
        p.end()


def break_name(name, width, metrics):
    """`name` as lines that fit `width` px, broken only after an
    underscore (board: `word-break: break-all` on the file name); a part
    wider than `width` stays whole on its line."""
    parts, cur = [], ''
    for i, ch in enumerate(name):
        cur += ch
        if ch == '_' or i == len(name) - 1:
            parts.append(cur)
            cur = ''
    lines, line = [], ''
    for part in parts:
        if line and metrics.horizontalAdvance(line + part) > width:
            lines.append(line)
            line = part
        else:
            line += part
    if line:
        lines.append(line)
    return lines


class _NameLabel(QLabel):
    """The hand-off file name, centred, wrapped after an underscore when
    the link is narrow; it never widens the row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full = ''
        self.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def set_name(self, name):
        self._full = str(name)
        self.setToolTip(self._full)
        self._render()

    def full_text(self):
        return self._full

    def _render(self):
        w = self.width()
        text = ('\n'.join(break_name(self._full, w, self.fontMetrics()))
                if w > 0 else self._full)
        if text != self.text():
            self.setText(text)

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (event.Type.FontChange, event.Type.StyleChange):
            self._render()


class HandoffArrow(QWidget):
    """An arrow between two cards with the hand-off file under it."""

    def __init__(self, a, b, n_stages=3, parent=None):
        super().__init__(parent)
        self.setObjectName('handoffarrow')
        self.edge = (int(a), int(b))
        self._pref = LINK_W2 if n_stages == 2 else LINK_W3
        self.setMinimumWidth(LINK_MIN)
        self.setMaximumWidth(self._pref)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        lay = QVBoxLayout(self)
        # board: 6 px each side; 2 here, so `handoff_` (mono 10.5) still
        # fits a 64 px link without a cut glyph
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(6)
        lay.addStretch(1)
        self.arrow = _Arrow()
        lay.addWidget(self.arrow)
        self.label = _NameLabel()
        self.label.setObjectName('handofflabel')
        self.label.set_name(chain_route.handoff_name(a, b))
        lay.addWidget(self.label)
        lay.addStretch(1)

    def sizeHint(self):
        return QSize(self._pref, super().sizeHint().height())

    @property
    def pref(self):
        return self._pref

    def name(self):
        return self.label.full_text()


# ── the pipeline row ─────────────────────────────────────────────────────
def fit_widths(avail, n, link_pref):
    """(card width, link width) for `n` cards and `n - 1` links in
    `avail` px: the board's 308 / `link_pref` when they fit; else the
    links give way first (down to LINK_MIN), then the cards (down to
    CARD_MIN)."""
    m = max(0, n - 1)
    if n * CARD_W + m * link_pref <= avail:
        return CARD_W, link_pref
    link = (max(LINK_MIN, min(link_pref, (avail - n * CARD_W) // m))
            if m else 0)
    card = max(CARD_MIN, min(CARD_W, (avail - m * link) // max(1, n)))
    return int(card), int(link)


class Pipeline(QWidget):
    """The stage cards and the arrows between them, left-aligned. Their
    widths are set from the row's own width (`fit_widths`), so a narrow
    window narrows the links first, then the cards, and the row never
    holds the window wider than the route's minimum."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        # the fixed widths below must not become this row's minimum
        self._lay.setSizeConstraint(QHBoxLayout.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._cards, self._arrows = [], []

    def set_items(self, cards, arrows):
        """Lay `cards` (in route order) with `arrows` between them. The
        old arrows are deleted; the cards belong to the caller."""
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None and w not in cards and w in self._arrows:
                w.setParent(None)
                w.deleteLater()
        self._cards, self._arrows = list(cards), list(arrows)
        for i, card in enumerate(self._cards):
            self._lay.addWidget(card)
            if i < len(self._arrows):
                self._lay.addWidget(self._arrows[i])
        self._lay.addStretch(1)
        n = len(self._cards)
        self.setMinimumWidth(n * CARD_MIN + max(0, n - 1) * LINK_MIN)
        self._fit()

    def _link_pref(self):
        return self._arrows[0].pref if self._arrows else LINK_W3

    def sizeHint(self):
        n = len(self._cards)
        return QSize(n * CARD_W + max(0, n - 1) * self._link_pref(),
                     super().sizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def _fit(self):
        if not self._cards:
            return
        card, link = fit_widths(self.width(), len(self._cards),
                                self._link_pref())
        for c in self._cards:
            if c.width() != card or c.minimumWidth() != card:
                c.setFixedWidth(card)
        for a in self._arrows:
            if a.width() != link or a.minimumWidth() != link:
                a.setFixedWidth(link)
