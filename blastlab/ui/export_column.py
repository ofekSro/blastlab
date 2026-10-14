"""The Results screen's export column (board Results lines 298-331).

EXPORT, then **Data** (Summary .csv · Gauge traces .txt · Field snapshot
.csv · Profile, for a Chain .txt|.npz · VTK for ParaView .vtk) and
**Figures** (All plots .png · Report .html · Animation .mp4|.gif), the
`Title on figures` box, and Open the 3D viewer at the foot. Each export
is an `ExportButton`: a 40 px button with its label and, at the right, the
file suffix in mono; while its export is being written the button gives
way to a busy strip (`writing…` over an indeterminate bar, UX-13).

Layout only: what each button does, and when it is enabled, is the
panel's (`ResultsPanel.export`, `_sync_export_buttons`). Batch
2026-09-29-gui-results T3.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QProgressBar, QPushButton, QVBoxLayout,
                               QWidget)

from ..output.animation import default_ext
from . import theme
from .setup_tree import _letter_space
from .widgets import ScrollColumn

#: (kind, label, suffix) of the Data group, in board order. The gauge
#: traces file is tab-separated text named `.txt` (its name is pinned by
#: the export golden), so the board's `.tsv` would misstate it.
DATA = (('summary', 'Summary', '.csv'),
        ('tsv', 'Gauge traces', '.txt'),
        ('fieldcsv', 'Field snapshot', '.csv'),
        # the suffix follows the result (profile_suffix)
        ('profile', 'Profile, for a Chain', '.txt|.npz'),
        ('vtk', 'VTK for ParaView', '.vtk'))
#: (kind, label, suffix) of the Figures group; the animation's suffix is
#: whatever this machine writes (`default_ext`: .mp4 with ffmpeg)
FIGURES = (('pngs', 'All plots', '.png'),
           ('report', 'Report', '.html'),
           ('gif', 'Animation', None))

#: the board's heights (D41: pinned in the QSS as well)
BUTTON_H = 40
VIEW3D_H = 42
#: the button's label and suffix insets (board line 306: padding 0 12,
#: gap 10)
PAD_X, GAP_X = 12, 10


def profile_suffix(dim):
    """`.txt` for a 1D result, `.npz` otherwise - `pick_target`'s rule;
    both when there is no result."""
    if dim is None:
        return '.txt|.npz'
    return '.txt' if int(dim) == 1 else '.npz'


class ExportButton(QWidget):
    """One export: `button` (the label as its text, the suffix a mono
    label at its right) and `strip`, the busy state that replaces it."""

    def __init__(self, kind, text, suffix, parent=None):
        super().__init__(parent)
        self.kind = kind
        self._busy = False
        self._mode_hidden = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.button = QPushButton(text)
        self.button.setObjectName('expbtn')
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setMinimumWidth(0)
        bl = QHBoxLayout(self.button)
        bl.setContentsMargins(0, 0, PAD_X, 0)
        bl.setSpacing(0)
        bl.addStretch(1)
        self.suffix = QLabel(suffix or '')
        self.suffix.setObjectName('expsuffix')
        self.suffix.setAttribute(Qt.WA_TransparentForMouseEvents)
        bl.addWidget(self.suffix)
        lay.addWidget(self.button)

        self.strip = QFrame()
        self.strip.setObjectName('expbusy')
        sl = QVBoxLayout(self.strip)
        sl.setContentsMargins(PAD_X, 9, PAD_X, 10)
        sl.setSpacing(6)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(GAP_X)
        self.busy_name = QLabel(text)
        self.busy_name.setObjectName('expbusyname')
        row.addWidget(self.busy_name, 1)
        self.busy_text = QLabel('writing…')
        self.busy_text.setObjectName('expbusytext')
        row.addWidget(self.busy_text)
        sl.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setObjectName('expbar')
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 0)             # indeterminate: no percent
        self.bar.setFixedHeight(4)
        sl.addWidget(self.bar)
        self.strip.hide()
        lay.addWidget(self.strip)

    def text(self):
        return self.button.text()

    def set_suffix(self, suffix):
        self.suffix.setText(suffix)

    def set_busy(self, on):
        self._busy = bool(on)
        self._apply()

    def busy(self):
        return self._busy

    def set_mode_hidden(self, hidden):
        """Hide the whole export for a solver mode (hide, never grey)."""
        self._mode_hidden = bool(hidden)
        self._apply()

    def _apply(self):
        self.button.setVisible(not self._mode_hidden and not self._busy)
        self.strip.setVisible(not self._mode_hidden and self._busy)
        self.setVisible(not self._mode_hidden)

    def label_fits(self):
        """The label's advance fits beside the suffix inside the button
        (nothing cut off)."""
        need = (PAD_X + self.button.fontMetrics().horizontalAdvance(
            self.button.text()) + GAP_X + self.suffix.sizeHint().width()
            + PAD_X)
        return need <= self.button.width()

    def minimumSizeHint(self):
        need = (PAD_X + self.button.fontMetrics().horizontalAdvance(
            self.button.text()) + GAP_X + self.suffix.sizeHint().width()
            + PAD_X)
        return QSize(need, super().minimumSizeHint().height())


class ExportColumn(QFrame):
    """The whole right column. `buttons` maps each kind to its
    QPushButton (the panel's `_export_btns`), `items` to its
    ExportButton; `title_box` and `view3d_btn` are the panel's."""

    def __init__(self, on_export, parent=None):
        super().__init__(parent)
        self.setObjectName('resright')
        fl = QVBoxLayout(self)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.setSpacing(0)
        col = ScrollColumn(spacing=16)
        col.layout_.setContentsMargins(18, 16, 14, 16)
        col.setFocusPolicy(Qt.NoFocus)
        self.scroll = col
        fl.addWidget(col)

        head = QWidget()
        hl = QVBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(4)
        caps = QLabel('EXPORT')
        caps.setObjectName('eyebrow')
        _letter_space(caps)
        hl.addWidget(caps)
        cap = QLabel('Into the model folder, or anywhere you choose.')
        cap.setObjectName('expcaption')
        cap.setWordWrap(True)
        hl.addWidget(cap)
        col.add(head)

        self.items, self.buttons, self.groups = {}, {}, {}
        for title, spec in (('Data', DATA), ('Figures', FIGURES)):
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(6)
            head = QLabel(title)
            head.setObjectName('expgroup')
            bl.addWidget(head)
            kinds = []
            for kind, text, suffix in spec:
                item = ExportButton(kind, text,
                                    suffix if suffix else default_ext())
                item.button.clicked.connect(
                    lambda *_, k=kind: on_export(k))
                bl.addWidget(item)
                self.items[kind] = item
                self.buttons[kind] = item.button
                kinds.append(kind)
            self.groups[title] = tuple(kinds)
            col.add(box)

        # G13U (D34): the 1D figure's export-title hint is a line of its
        # own under the buttons, not only their tooltip; hidden when empty
        self.hint = QLabel('')
        self.hint.setObjectName('expcaption')
        self.hint.setWordWrap(True)
        self.hint.setVisible(False)
        col.add(self.hint)

        tbox = QWidget()
        tl = QVBoxLayout(tbox)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)
        tcap = QLabel('Title on figures (optional)')
        tcap.setObjectName('expcaption')
        tl.addWidget(tcap)
        self.title_box = QLineEdit()
        self.title_box.setObjectName('restitle')
        self.title_box.setMinimumWidth(0)
        self.title_box.setPlaceholderText('added above the automatic title')
        tl.addWidget(self.title_box)
        col.add(tbox)
        col.add_stretch()

        self.view3d_btn = QPushButton('Open the 3D viewer')
        self.view3d_btn.setObjectName('res3d')
        self.view3d_btn.setCursor(Qt.PointingHandCursor)
        self.view3d_btn.setIcon(theme.icon('cube', 17))
        self.view3d_btn.setIconSize(QSize(17, 17))
        self.view3d_btn._blastlab_icon = ('cube', 17, None)
        col.add(self.view3d_btn)

    def set_hint(self, text):
        """The muted export-title hint under the buttons ('' hides it)."""
        text = str(text or '')
        self.hint.setText(text)
        self.hint.setToolTip(text)
        self.hint.setVisible(bool(text))

    def order(self):
        """{'Data': kinds, 'Figures': kinds} in the order they sit."""
        return dict(self.groups)
