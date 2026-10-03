"""The 64 px top bar of the window frame (GUI-3, plan §4; board
BC_Combined lines 20-54).

Left to right: the 30 px mark + BLASTLAB wordmark · the workflow pills
01 Setup → 02 Run → 03 Results (selected = `text`-coloured pill with
`bg` text; a ✓ after a done step) · a 1 px divider · Chain 1D → 2D → 3D
· stretch · the case-name button with `● unsaved` · the solver chip ·
the dimension segmented control 0D · HD 1.3 | 1D | 2D | 3D.

The bar is layout and signals only: `MainWindow` owns the behaviour
(navigation, menus, dirty state) and wires it. All text styling goes
through QSS object-name rules (`#pill`, `#chainlink`, `#casebtn`,
`#chipbtn`) or per-widget style sheets - the app-wide QWidget font rule
overrides programmatic QFont family/size (foundation report, D6).
"""

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QStyle, QStyleOptionButton,
                               QWidget)

from . import theme
from .widgets import Segmented

#: the workflow pills, in order; Chain is the link after the divider
PILLS = (('setup', '01', 'Setup'), ('run', '02', 'Run'),
         ('results', '03', 'Results'))

#: dimension segmented labels; `int(label[0])` is the dimension
DIM_LABELS = ('0D · HD 1.3', '1D', '2D', '3D')

BAR_H = 64


def dot_pixmap(colour_key, d=7):
    """A small round status dot tinted with palette key `colour_key`."""
    pm = QPixmap(d, d)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(theme.cur(colour_key)))
    p.drawEllipse(0, 0, d, d)
    p.end()
    return pm


class ElidedButton(QPushButton):
    """A push button whose text elides at the right when the layout gives
    it less than the whole text needs; the whole text is then its tooltip
    (GUI-10, F29: the case name at 1100 px in blastFoam mode). The size
    hint is always the whole text's, so the layout gives it all it can."""

    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self._full = str(text)

    def full_text(self):
        return self._full

    def set_full_text(self, text):
        self._full = str(text)
        self._elide()
        self.updateGeometry()

    def sizeHint(self):
        # QPushButton::sizeHint for a text-only button, on the whole text
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        opt.text = self._full
        sz = self.fontMetrics().size(Qt.TextShowMnemonic, self._full)
        return self.style().sizeFromContents(
            QStyle.CT_PushButton, opt,
            QSize(sz.width(), max(sz.height(), 14)), self)

    def _elide(self):
        fm = self.fontMetrics()
        pad = self.sizeHint().width() - fm.horizontalAdvance(self._full)
        shown = fm.elidedText(self._full, Qt.ElideRight,
                              max(0, self.width() - pad))
        if shown != self.text():
            self.setText(shown)
        self.setToolTip('' if shown == self._full else self._full)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._elide()

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._elide()


class TopBar(QFrame):
    """The frame's top bar. Signals only; the window wires behaviour."""

    #: a pill or the Chain link was clicked ('setup'|'run'|'results'|'chain')
    navigate = Signal(str)
    #: a dimension segment was clicked (0 | 1 | 2 | 3)
    dim_selected = Signal(int)
    #: the case-name button / the solver chip were clicked
    case_clicked = Signal()
    chip_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('topbar')
        self.setFixedHeight(BAR_H)
        # tighter than the 1440 px board (gap 26): the bar must fit the
        # 1100 px minimum window without clipping any button text. F29
        # (GUI-10): 6 -> 4 px gaps and 10 -> 6 px margins for blastFoam
        # mode's longer chip; the case name gives way last (ElidedButton)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(4)

        # mark + wordmark (GUI-2; moved here from the sidebar head)
        self._logo_mark = QLabel()
        self._logo_mark.setPixmap(theme.logo_pixmap(30))
        lay.addWidget(self._logo_mark)
        word = QHBoxLayout()
        word.setContentsMargins(0, 0, 0, 0)
        word.setSpacing(0)
        self._logo_blast = QLabel('BLAST')
        self._logo_lab = QLabel('LAB')
        wordmark_font = theme.font('h2')
        wordmark_font.setLetterSpacing(QFont.PercentageSpacing, 108)
        for w in (self._logo_blast, self._logo_lab):
            w.setFont(wordmark_font)
            word.addWidget(w)
        self._tint_wordmark()
        lay.addLayout(word)

        # workflow pills with the board's chevrons between them
        self.nav_btns = {}
        self._done = {}
        self._pill_text = {}
        self._chevrons = []
        for i, (key, num, text) in enumerate(PILLS):
            if i:
                ch = QLabel()
                ch.setPixmap(theme.pixmap('chevron_right', 12,
                                          color='num_dim'))
                ch.setFixedWidth(12)
                lay.addWidget(ch)
                self._chevrons.append(ch)
            b = QPushButton(f'{num} {text}')
            b.setObjectName('pill')
            b.setFixedHeight(40)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self.navigate.emit(k))
            lay.addWidget(b)
            self.nav_btns[key] = b
            self._pill_text[key] = f'{num} {text}'
            self._done[key] = False

        self._divider = QFrame()
        self._divider.setFixedSize(1, 22)
        lay.addWidget(self._divider)

        chain = QPushButton('Chain 1D → 2D → 3D')
        chain.setObjectName('chainlink')
        chain.setFixedHeight(40)
        chain.setCursor(Qt.PointingHandCursor)
        chain.clicked.connect(lambda _c=False: self.navigate.emit('chain'))
        lay.addWidget(chain)
        self.nav_btns['chain'] = chain

        lay.addStretch(1)

        # case name + unsaved marker
        self.case_btn = ElidedButton('untitled')
        self.case_btn.setObjectName('casebtn')
        self.case_btn.setFixedHeight(32)
        self.case_btn.setCursor(Qt.PointingHandCursor)
        self.case_btn.setMinimumWidth(40)
        self.case_btn.setMaximumWidth(200)
        self.case_btn.clicked.connect(lambda _c=False:
                                      self.case_clicked.emit())
        lay.addWidget(self.case_btn)
        self.dirty_lbl = QLabel('● unsaved')
        self.dirty_lbl.setVisible(False)
        lay.addWidget(self.dirty_lbl)

        # solver chip (dot + label; the menu is the window's)
        self.chip = QPushButton('')
        self.chip.setObjectName('chipbtn')
        self.chip.setFixedHeight(32)
        self.chip.setCursor(Qt.PointingHandCursor)
        # F29: the chip is never narrower than its text (the case name
        # gives way instead)
        self.chip.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.chip.setIconSize(QSize(7, 7))
        self.chip.clicked.connect(lambda _c=False: self.chip_clicked.emit())
        lay.addWidget(self.chip)
        self._chip_dot_key = None

        # dimension control; `int(label[0])` drives setup.set_dim
        self.dim_seg = Segmented(list(DIM_LABELS), height=30, small=True)
        self.dim_seg.changed.connect(
            lambda lbl: self.dim_selected.emit(int(str(lbl)[0])))
        # board: the 1D/2D/3D buttons are 40 px; without this the
        # Segmented's Expanding buttons push the bar past 1100 px
        for lbl in DIM_LABELS[1:]:
            b = self.dim_seg._btns.get(lbl)
            if b is not None:
                b.setFixedWidth(40)
        lay.addWidget(self.dim_seg)

        theme.signals.changed.connect(self.retheme)
        self.retheme()

    # ── pills ────────────────────────────────────────────────────────────
    def set_active(self, key):
        """Mark the pill (or the Chain link) of `key` as the current tab."""
        for k, b in self.nav_btns.items():
            b.setProperty('active', 'true' if k == key else 'false')
            theme.repolish(b)

    def set_done(self, key, done):
        """Show (or clear) the ✓ after a workflow step (plan §4)."""
        if key not in self._pill_text:
            return
        done = bool(done)
        if self._done.get(key) == done:
            return
        self._done[key] = done
        text = self._pill_text[key] + (' ✓' if done else '')
        self.nav_btns[key].setText(text)

    def is_done(self, key):
        return bool(self._done.get(key))

    def set_chain_label(self, text):
        """The Chain link's text: it follows the Chain screen's route
        (GUI-9, board Chain line 46: `Chain 1D → 2D → 3D`)."""
        self.nav_btns['chain'].setText(str(text))

    # ── case name ────────────────────────────────────────────────────────
    def set_case_name(self, name):
        self.case_btn.set_full_text(str(name or 'untitled'))

    def case_name(self):
        """The whole case name (the button may show it elided, F29)."""
        return self.case_btn.full_text()

    def set_dirty(self, dirty):
        self.dirty_lbl.setVisible(bool(dirty))

    # ── solver chip ──────────────────────────────────────────────────────
    def set_chip(self, text, dot=None):
        """Chip label and status-dot palette key (None = no dot)."""
        self.chip.setText(str(text))
        self._chip_dot_key = dot
        self.chip.setIcon(QIcon(dot_pixmap(dot)) if dot else QIcon())

    def set_chip_visible(self, visible):
        # hide, never grey (CLAUDE.md §4): a 0-D case has no solver
        self.chip.setVisible(bool(visible))

    # ── dimension ────────────────────────────────────────────────────────
    def set_dim(self, dim):
        """Silent sync from `SetupPanel.dim_changed` (the `Segmented`
        convention: `set()` fires nothing)."""
        for lbl in DIM_LABELS:
            if int(lbl[0]) == int(dim):
                self.dim_seg.set(lbl)
                return

    # ── theming ──────────────────────────────────────────────────────────
    def _tint_wordmark(self):
        """Board Logo_Final: Space Grotesk Bold caps, LAB in accent_text.
        Family/size through the style sheet (D6); the +8 % tracking stays
        on the QFont (QSS cannot letter-space)."""
        # board BC_Combined line 28: 700 16px in the top bar
        base = ('font-family: "Space Grotesk"; font-size: 16px; '
                'font-weight: 700;')
        self._logo_blast.setStyleSheet(
            base + f' color: {theme.cur("text")};')
        self._logo_lab.setStyleSheet(
            base + f' color: {theme.cur("accent_text")};')

    def retheme(self, _mode=None):
        self._logo_mark.setPixmap(theme.logo_pixmap(30))
        self._tint_wordmark()
        for ch in self._chevrons:
            ch.setPixmap(theme.pixmap('chevron_right', 12, color='num_dim'))
        self._divider.setStyleSheet(
            f'background: {theme.cur("seg")}; border: none;')
        self.dirty_lbl.setStyleSheet(
            f'color: {theme.cur("warn")}; font-size: 12px;')
        if self._chip_dot_key:
            self.chip.setIcon(QIcon(dot_pixmap(self._chip_dot_key)))
