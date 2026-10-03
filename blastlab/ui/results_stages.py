"""GUI-9 T5 (plan §7 "A chain is one result", board Results_Chain lines
98-103): the `STAGE 1D | 2D | 3D` tab strip of a chain's one 03 Results
entry.

`ResultsPanel` shows ONE instance in its `stage_slot` (above the view
tabs; the board has both in one row, D-row) while a chain is selected and
empties the slot for a plain result. One tab per LANDED stage; the
selected one is `accent` with `on_accent` text, the group sits on the
chain tint with an `accent_border` frame (theme.py, D6; heights pinned in
the QSS, D41). A click emits `picked(dim)`; `set_stages` is silent.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QWidget)

from .setup_tree import _letter_space

#: the strip's height (board: 32 px tabs in a 3 px padded, 1 px framed
#: group = 38)
TABS_H = 38


class StageTabs(QWidget):
    """`STAGE` + one checkable, exclusive tab per landed stage."""

    picked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(TABS_H)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.group = QFrame()
        self.group.setObjectName('stagetabs')
        self.group.setFixedHeight(TABS_H)
        self._lay = QHBoxLayout(self.group)
        # 1 px frame + 2 px + 32 px tab + 2 px + 1 px = 38 (resseg's rule)
        self._lay.setContentsMargins(3, 2, 3, 2)
        self._lay.setSpacing(2)
        self.eyebrow = QLabel('STAGE')
        self.eyebrow.setObjectName('stagetabeyebrow')
        # board: padding 0 8 0 6, letter-spacing 0.08em
        self.eyebrow.setContentsMargins(6, 0, 8, 0)
        _letter_space(self.eyebrow, 108)
        self._lay.addWidget(self.eyebrow, 0, Qt.AlignVCenter)
        outer.addWidget(self.group)
        outer.addStretch(1)
        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)
        self.btns = {}              # dim -> QPushButton, in stage order

    def set_stages(self, dims, selected):
        """Tabs for `dims` (the landed stages, in order), `selected`
        checked. Silent: no `picked`."""
        dims = [int(d) for d in dims]
        if dims != list(self.btns):
            for b in self.btns.values():
                self._grp.removeButton(b)
                self._lay.removeWidget(b)
                b.setParent(None)
                b.deleteLater()
            self.btns = {}
            for d in dims:
                b = QPushButton(f'{d}D')
                b.setObjectName('stagetab')
                b.setCheckable(True)
                b.setCursor(Qt.PointingHandCursor)
                b.setAccessibleName(f'Stage {d}D')
                b.clicked.connect(lambda _c=False, dd=d: self.picked.emit(dd))
                self._grp.addButton(b)
                self._lay.addWidget(b, 0, Qt.AlignVCenter)
                self.btns[d] = b
        # an exclusive group: checking one unchecks the other (`clicked`
        # is not emitted by setChecked)
        b = self.btns.get(selected)
        if b is not None and not b.isChecked():
            b.setChecked(True)

    def dims(self):
        return list(self.btns)

    def selected(self):
        """The checked tab's dimension, or None."""
        for d, b in self.btns.items():
            if b.isChecked():
                return d
        return None

    def button(self, dim):
        return self.btns.get(int(dim))

    def texts(self):
        """['1D', '2D', ...] - the tabs' texts, in order (tests)."""
        return [b.text() for b in self.btns.values()]
