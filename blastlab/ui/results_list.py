"""The Results screen's list of results (board Results lines 59-78).

`ResultsList` replaces the old picker QComboBox. It keeps the combo-box
surface every caller uses (`count`, `itemText`, `itemData`,
`setItemData`, `currentIndex`, `setCurrentIndex`, `currentData`,
`currentIndexChanged`, `addItem`, `clear`, `blockSignals`), so the QA
harness's `select_result`, `MainWindow._open_results` and the tests work
unchanged. Each entry is one row: its name (elided in the middle to the
column, the full label in the tooltip), a `latest` badge on the newest, a
`chain` badge when `entry.kind == 'chain'` (GUI-9), and the caption
`results_method.result_caption` (`2D axisym. · blastFoam · 5 min 31 s`).
Batch 2026-09-29-gui-results T2.
"""

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import theme
from .results_method import chain_caption, result_caption

#: the rows' minimum height (plan section 2.4, D41: pinned in the QSS)
ROW_MIN_H = 44


class ElidedLabel(QLabel):
    """A one-line label that elides its text to its own width (middle by
    default) and never holds its column wider; the whole text is the
    tooltip whenever it is cut."""

    def __init__(self, text='', mode=Qt.ElideMiddle, parent=None):
        super().__init__(parent)
        self._full = ''
        self._mode = mode
        self._tip = None            # a caller's own tooltip wins
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text):                         # noqa: N802 (Qt)
        self._full = str(text or '')
        self._render()

    def full_text(self):
        return self._full

    def set_tip(self, tip):
        """A tooltip that is shown whether or not the text is cut."""
        self._tip = tip
        self._render()

    def elided(self):
        """True when what is painted is not the whole text."""
        return super().text() != self._full

    def sizeHint(self):
        h = super().sizeHint().height()
        return QSize(self.fontMetrics().horizontalAdvance(self._full), h)

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def changeEvent(self, event):
        super().changeEvent(event)
        # a style sheet (font) change moves every advance
        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._render()

    def _render(self):
        w = self.width()
        shown = (self.fontMetrics().elidedText(self._full, self._mode, w)
                 if w > 0 else self._full)
        QLabel.setText(self, shown)
        tip = self._tip
        if tip is None:
            tip = self._full if shown != self._full else ''
        self.setToolTip(tip)


class ResultRow(QFrame):
    """One result: name + badges over the caption. `selected` fills it
    with `accent_bg` (QSS `QFrame#resrow[selected="true"]`)."""

    clicked = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('resrow')
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(ROW_MIN_H)
        self.setProperty('selected', 'false')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        self.name = ElidedLabel('')
        self.name.setObjectName('resname')
        top.addWidget(self.name, 1)
        self.latest = QLabel('latest')
        self.latest.setObjectName('reslatest')
        self.latest.hide()
        top.addWidget(self.latest)
        self.chain = QLabel('chain')
        self.chain.setObjectName('reschain')
        self.chain.hide()
        top.addWidget(self.chain)
        lay.addLayout(top)
        self.caption = ElidedLabel('', Qt.ElideRight)
        self.caption.setObjectName('rescaption')
        lay.addWidget(self.caption)
        for w in (self.name, self.latest, self.chain, self.caption):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_selected(self, on):
        self.setProperty('selected', 'true' if on else 'false')
        for w in (self, self.caption):
            theme.repolish(w)

    def selected(self):
        return self.property('selected') == 'true'

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton \
                and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self)
        super().mouseReleaseEvent(event)


class _ListScroll(QScrollArea):
    """The list's scroll area. Its size hint is the height of all its
    rows (`_cap` sets it), so the column's layout gives it that height
    when there is room and shrinks it toward its two-row minimum only when
    there is not. A plain QScrollArea hints a fixed small height, which
    held the list at two rows with the column half empty and the newest
    (selected) result scrolled out of sight (GUI-7 verification)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._want = None

    def sizeHint(self):                              # noqa: N802 (Qt)
        s = super().sizeHint()
        return s if self._want is None else QSize(s.width(), self._want)


class ResultsList(QWidget):
    """The list of results, newest last, with the QComboBox surface of
    the picker it replaces. `currentIndexChanged(int)` fires as the
    combo's did: on a change of index, including the first item added and
    a clear."""

    currentIndexChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []            # [{'text', 'data', 'roles'}]
        self._rows = []
        self._index = -1
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        self.caps = QLabel('RESULTS')
        self.caps.setObjectName('eyebrow')
        self.caps.setContentsMargins(6, 0, 0, 2)
        root.addWidget(self.caps)
        self.scroll = _ListScroll()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.NoFocus)
        body = QWidget()
        self._lay = QVBoxLayout(body)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(4)
        self._lay.addStretch(1)
        self.scroll.setWidget(body)
        self.scroll.verticalScrollBar().rangeChanged.connect(
            lambda *_: self._reveal())
        root.addWidget(self.scroll, 1)
        self.empty = QLabel('No results yet. A finished run lands here.')
        self.empty.setObjectName('rescaption')
        self.empty.setWordWrap(True)
        self.empty.setContentsMargins(6, 0, 0, 0)
        root.addWidget(self.empty)
        self._sync_empty()

    # ── the QComboBox surface ────────────────────────────────────────────
    def count(self):
        return len(self._items)

    def itemText(self, i):                           # noqa: N802 (Qt)
        return self._items[i]['text'] if 0 <= i < len(self._items) else ''

    def itemData(self, i, role=Qt.UserRole):         # noqa: N802 (Qt)
        if not 0 <= i < len(self._items):
            return None
        it = self._items[i]
        if role == Qt.UserRole:
            return it['data']
        if role == Qt.DisplayRole:
            return it['text']
        return it['roles'].get(role)

    def setItemData(self, i, value, role=Qt.UserRole):  # noqa: N802 (Qt)
        if not 0 <= i < len(self._items):
            return
        if role == Qt.UserRole:
            self._items[i]['data'] = value
        else:
            self._items[i]['roles'][role] = value
        self._fill(i)

    def currentIndex(self):                          # noqa: N802 (Qt)
        return self._index

    def currentData(self, role=Qt.UserRole):         # noqa: N802 (Qt)
        return self.itemData(self._index, role)

    def currentText(self):                           # noqa: N802 (Qt)
        return self.itemText(self._index)

    def setCurrentIndex(self, i):                    # noqa: N802 (Qt)
        i = int(i)
        if not -1 <= i < len(self._items):
            return
        if i == self._index:
            return
        self._index = i
        self._paint_selection()
        self.currentIndexChanged.emit(i)

    def addItem(self, text, data=None):              # noqa: N802 (Qt)
        self._items.append(dict(text=str(text), data=data, roles={}))
        row = ResultRow()
        row.clicked.connect(self._row_clicked)
        self._lay.insertWidget(self._lay.count() - 1, row)
        self._rows.append(row)
        self._fill(len(self._items) - 1)
        self._badge_latest()
        self._sync_empty()
        if self._index < 0:
            self._index = 0
            self._paint_selection()
            self.currentIndexChanged.emit(0)

    def clear(self):
        for row in self._rows:
            self._lay.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows, self._items = [], []
        self._sync_empty()
        if self._index != -1:
            self._index = -1
            self.currentIndexChanged.emit(-1)

    # ── rows ─────────────────────────────────────────────────────────────
    def row(self, i):
        """The row widget of item `i` (tests)."""
        return self._rows[i]

    def rows(self):
        return list(self._rows)

    def refresh_captions(self):
        """Re-read every caption (a result's model folder may have been
        written after it was added)."""
        for i in range(len(self._items)):
            self._fill(i)

    def _fill(self, i):
        it, row = self._items[i], self._rows[i]
        row.name.setText(it['text'])
        tip = it['roles'].get(Qt.ToolTipRole)
        row.name.set_tip(tip)
        row.setToolTip(tip or '')
        data = it['data']
        chain = getattr(data, 'kind', None) == 'chain'
        row.chain.setVisible(chain)
        # GUI-9 T5: a chain's caption is its route, stages and duration
        row.caption.setText('' if data is None else chain_caption(data)
                            if chain else result_caption(data))

    def _badge_latest(self):
        last = len(self._rows) - 1
        for k, row in enumerate(self._rows):
            row.latest.setVisible(k == last)

    def _paint_selection(self):
        for k, row in enumerate(self._rows):
            if row.selected() != (k == self._index):
                row.set_selected(k == self._index)
        # the row may not be laid out yet (just added): once more after
        # this event-loop pass, and on every change of the scroll range
        self._reveal()
        QTimer.singleShot(0, self, self._reveal)

    def _row_clicked(self, row):
        if row in self._rows:
            self.setCurrentIndex(self._rows.index(row))

    def _sync_empty(self):
        self.empty.setVisible(not self._items)
        self.scroll.setVisible(bool(self._items))
        self._cap()
        # the rows' fonts reach them on their first polish
        QTimer.singleShot(0, self, self._cap)

    def _cap(self):
        """The list is as tall as its rows and no taller (the spare
        height of the column goes under the method card, board line 92);
        with more rows than fit it keeps two and scrolls."""
        n = len(self._rows)
        if not n:
            return
        sp = self._lay.spacing()
        heights = [max(r.sizeHint().height(), ROW_MIN_H) for r in self._rows]
        want = sum(heights) + sp * (n - 1) + 2 * self.scroll.frameWidth()
        two = sum(heights[:2]) + sp * (min(n, 2) - 1) \
            + 2 * self.scroll.frameWidth()
        self.scroll.setMaximumHeight(want)
        self.scroll.setMinimumHeight(min(want, two))
        if self.scroll._want != want:
            self.scroll._want = want
            self.scroll.updateGeometry()

    def _reveal(self):
        """Scroll the selected row into view (a new result is added last
        and selected; when the list scrolls it must not stay below the
        fold)."""
        if 0 <= self._index < len(self._rows):
            self.scroll.ensureWidgetVisible(self._rows[self._index], 0, 0)

    def showEvent(self, event):
        super().showEvent(event)
        self._cap()
        QTimer.singleShot(0, self, self._reveal)
