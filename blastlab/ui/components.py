"""GUI-4: the shared components of the GUI redesign (plan §2.5, boards
BC_Combined / Run_Finished / Chain): ToggleSwitch, StatTile, TreeRow,
DockTabs, Banner and HandoffCard; GUI-6 added Collapsible (board Run,
Step through) and `DockTabs.add_corner`.

New module on purpose - nothing that imports `widgets` today is
disturbed, and nothing in the app consumes these yet (GUI-3/5/6/7
will). Colours come from `theme`; what QSS cannot draw (the switch
track, the tile bar) is painted in `paintEvent` - no shadows, no
gradients, no new dependency (plan §11). Every component re-tints
itself on `theme.signals.changed`.
"""

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QTransform
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QFrame,
                               QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QStackedWidget, QToolButton,
                               QVBoxLayout, QWidget)

from . import theme


def _px_font(px, weight=None, mono=False, display=False):
    """A theme-family QFont sized in pixels (the boards are specified
    in px; QSS cannot letter-space, so these are set in code)."""
    f = theme.font('mono' if mono else
                   'display' if display else 'body')
    f.setPixelSize(int(px))
    if weight is not None:
        f.setWeight(QFont.Weight(weight))
    return f


def _css(px, weight=None, colour=None, family=None):
    """Per-widget font/colour style string. Family and size must go
    through the style sheet: the app-wide QSS font rule overrides a
    plain setFont (measured; only weight and letter-spacing survive
    it)."""
    bits = [f'font-size: {int(px)}px;']
    if family:
        bits.append(f'font-family: "{family}";')
    if weight is not None:
        bits.append(f'font-weight: {int(weight)};')
    if colour is not None:
        bits.append(f'color: {theme.cur(colour)};')
    return ' '.join(bits)


def _on_theme(widget, fn):
    """Run the bound method `fn` now and on every theme switch. The
    direct bound-method connection lets Qt auto-disconnect it when
    `widget` (the receiver) is destroyed - a lambda would outlive it."""
    fn()
    theme.signals.changed.connect(fn)


# ── Toggle switch ────────────────────────────────────────────────────────
class ToggleSwitch(QCheckBox):
    """A QCheckBox painted as a 46 x 26 track with a white knob -
    `accent` when on, #3a3a40 (dark) / a derived grey (light) when off
    (board BC_Combined, the trigger switch). Subclassing keeps the
    keyboard, focus and screen-reader behaviour of a checkbox
    (plan §2.5)."""

    _W, _H = 46, 26

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):
        return QSize(self._W, self._H)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self._H / 2.0
        track = QColor(theme.cur('accent') if self.isChecked() else
                       ('#3a3a40' if theme.mode() == 'dark'
                        else '#b9b3aa'))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(track))
        p.drawRoundedRect(QRectF(0, 0, self._W, self._H), r, r)
        if self.hasFocus():
            p.setPen(QPen(theme.qcolor('accent_text'), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(0.75, 0.75, self._W - 1.5,
                                     self._H - 1.5), r, r)
            p.setPen(Qt.NoPen)
        knob = self._H - 6
        x = self._W - knob - 3 if self.isChecked() else 3
        p.setBrush(QBrush(QColor('#ffffff')))
        p.drawEllipse(QRectF(x, 3, knob, knob))
        p.end()


# ── Stat tile ────────────────────────────────────────────────────────────
class _TileBar(QWidget):
    """The thin bar of the memory tile (4 px, `seg` track, `ok` fill)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frac = 0.0
        self.setFixedHeight(4)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_frac(self, frac):
        self._frac = min(1.0, max(0.0, float(frac)))
        self.update()

    def frac(self):
        return self._frac

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(theme.qcolor('seg')))
        p.drawRoundedRect(QRectF(0, 0, self.width(), 4), 2, 2)
        if self._frac > 0:
            p.setBrush(QBrush(theme.qcolor('ok')))
            p.drawRoundedRect(QRectF(0, 0, self.width() * self._frac, 4),
                              2, 2)
        p.end()


class StatTile(QFrame):
    """A live-number tile (board BC_Combined, the strip): caps label
    (10.5 px, letter-spaced), value in Space Grotesk 21 px via
    `theme.font('display')`, a caption line, and an optional thin bar
    (memory). `variant='accent'` is the tinted Z tile (`accent_bg`)."""

    def __init__(self, title, variant=None, bar=False, parent=None):
        super().__init__(parent)
        self.setObjectName('tile')
        self.variant = variant
        if variant:
            self.setProperty('variant', variant)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(3)
        self.caps = QLabel(str(title).upper())
        caps_font = _px_font(10.5, 600)
        caps_font.setLetterSpacing(QFont.PercentageSpacing, 110)
        self.caps.setFont(caps_font)
        self.value = QLabel('—')
        self.value.setFont(_px_font(21, 600, display=True))
        self.caption = QLabel('')
        self.caption.setFont(_px_font(11.5))
        self.bar = _TileBar(self) if bar else None
        lay.addWidget(self.caps)
        lay.addWidget(self.value)
        if self.bar is not None:
            lay.addWidget(self.bar)
        lay.addWidget(self.caption)
        _on_theme(self, self._recolour)

    def _recolour(self, _mode=None):
        caps = 'accent_text' if self.variant == 'accent' else 'faint'
        cap = 'accent_soft' if self.variant == 'accent' else 'muted'
        self.caps.setStyleSheet(_css(10, 600, caps))
        self.value.setStyleSheet(_css(21, 600, 'text',
                                      family=theme.DISPLAY))
        self.caption.setStyleSheet(_css(11, colour=cap))

    def set(self, value, caption=None, frac=None):
        self.value.setText(str(value))
        if caption is not None:
            self.caption.setText(str(caption))
        if frac is not None and self.bar is not None:
            self.bar.set_frac(frac)


# ── Tree row ─────────────────────────────────────────────────────────────
_STATUS = {'ok': ('✓', 'ok'), 'warn': ('!', 'warn'),
           'error': ('✗', 'danger')}


class TreeRow(QFrame):
    """A model-tree row (board BC_Combined): number (Space Grotesk
    12.5, `num_dim`, `accent_text` when selected) · title · mono
    caption · right-side status mark (✓ ok / ! warn / ✗ danger).
    Selected fill `accent_bg`; min height 44 px (§2.4); emits
    `clicked(row_id)`."""

    clicked = Signal(str)

    def __init__(self, row_id, number, title, caption='', parent=None):
        super().__init__(parent)
        self.setObjectName('treerow')
        self._id = str(row_id)
        self._selected = False
        self._status = None
        self.setMinimumHeight(44)
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(12)
        self.number = QLabel(str(number))
        self.number.setFont(_px_font(12.5, 600, display=True))
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        self.title = QLabel(str(title))
        self.title.setFont(_px_font(14, 500))
        self.caption = QLabel(str(caption))
        self.caption.setFont(_px_font(11.5, mono=True))
        col.addWidget(self.title)
        col.addWidget(self.caption)
        self.caption.setVisible(bool(caption))
        self.mark = QLabel('')
        self.mark.setFont(_px_font(14, 600))
        lay.addWidget(self.number)
        lay.addLayout(col, 1)
        lay.addWidget(self.mark)
        _on_theme(self, self._recolour)

    def _recolour(self, _mode=None):
        num = 'accent_text' if self._selected else 'num_dim'
        self.number.setStyleSheet(_css(12, 600, num,
                                       family=theme.DISPLAY))
        self.title.setStyleSheet(_css(14, 500, 'text'))
        self.caption.setStyleSheet(_css(11, colour='faint',
                                        family=theme.MONO))
        if self._status in _STATUS:
            self.mark.setStyleSheet(
                _css(14, 600, _STATUS[self._status][1]))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton \
                and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self._id)
        super().mouseReleaseEvent(event)

    def set_selected(self, selected):
        self._selected = bool(selected)
        self.setProperty('selected',
                         'true' if self._selected else 'false')
        theme.repolish(self)
        self._recolour()

    def selected(self):
        return self._selected

    def set_status(self, status):
        """'ok' | 'warn' | 'error' | None (no mark)."""
        self._status = status if status in _STATUS else None
        self.mark.setText(_STATUS[self._status][0] if self._status
                          else '')
        self._recolour()

    def set_caption(self, caption):
        self.caption.setText(str(caption))
        self.caption.setVisible(bool(caption))


# ── Dock tabs ────────────────────────────────────────────────────────────
class DockTabs(QWidget):
    """A tab strip whose active tab has a 2 px `accent` underline
    (board BC_Combined, the dock), over a QStackedWidget. The
    `Segmented` API convention holds: `changed(str)` fires only on a
    user click, `set()` is silent."""

    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._strip = QHBoxLayout()
        self._strip.setContentsMargins(8, 0, 8, 0)
        self._strip.setSpacing(0)
        self._strip.addStretch(1)
        outer.addLayout(self._strip)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._tabs = {}

    def add(self, name, widget):
        b = QToolButton()
        b.setObjectName('docktab')
        b.setText(str(name))
        b.setCheckable(True)
        b.setFixedHeight(40)
        b.setFont(_px_font(13, 600))
        b.setCursor(Qt.PointingHandCursor)
        self._group.addButton(b)
        self._strip.insertWidget(self._strip.count() - 1, b)
        self._tabs[str(name)] = (b, widget)
        self.stack.addWidget(widget)
        b.clicked.connect(lambda _c=False, n=str(name):
                          (self._activate(n), self.changed.emit(n)))
        if len(self._tabs) == 1:
            b.setChecked(True)
            self.stack.setCurrentWidget(widget)
        return widget

    def set_label(self, name, text, icon=None):
        """Re-label tab `name` (e.g. with a count) without changing its
        key; `icon` a QIcon shown beside the text, or None."""
        if str(name) not in self._tabs:
            return
        b, _w = self._tabs[str(name)]
        b.setText(str(text))
        if icon is not None:
            b.setIcon(icon)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

    def set_tooltip(self, name, text):
        if str(name) in self._tabs:
            self._tabs[str(name)][0].setToolTip(str(text))

    def label(self, name):
        """The tab's text as shown (tests)."""
        return self._tabs[str(name)][0].text()

    def set_tab_visible(self, name, on):
        """Hide (never grey) a tab that does not apply; a hidden current
        tab hands over to the first visible one."""
        if str(name) not in self._tabs:
            return
        b, _w = self._tabs[str(name)]
        b.setVisible(bool(on))
        if not on and b.isChecked():
            for other, (ob, _ow) in self._tabs.items():
                if not ob.isHidden():
                    self._activate(other)
                    break

    def tab_visible(self, name):
        return not self._tabs[str(name)][0].isHidden()

    def _activate(self, name):
        b, widget = self._tabs[name]
        b.setChecked(True)
        self.stack.setCurrentWidget(widget)

    def set(self, name):
        """Silent, as `Segmented.set` is."""
        if str(name) in self._tabs:
            self._activate(str(name))

    def get(self):
        for name, (b, _w) in self._tabs.items():
            if b.isChecked():
                return name
        return None

    def names(self):
        return list(self._tabs)

    def button(self, name):
        """The tab's own button (a focus chain, tests)."""
        return self._tabs[str(name)][0]

    def add_corner(self, widget, gap=0):
        """Put `widget` at the right end of the tab strip, after the
        stretch (board Run line 252: Copy / Save log… beside the tabs),
        `gap` px after the previous corner widget. Returns the widget."""
        if gap:
            self._strip.addSpacing(int(gap))
        self._strip.addWidget(widget, 0, Qt.AlignVCenter)
        return widget


# ── Collapsible section ──────────────────────────────────────────────────
class _CollapseHeader(QPushButton):
    """The header row of a `Collapsible`: chevron · title · hint, three
    labels inside one checkable QPushButton, so clicks, focus, Space and
    the checked state stay the button's."""

    def __init__(self, title, hint, parent=None):
        super().__init__(parent)
        self.setObjectName('collapsehead')
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(str(title))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.chevron = QLabel()
        self.title = QLabel(str(title))
        self.hint = QLabel(str(hint))
        for w in (self.chevron, self.title, self.hint):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(self.chevron)
        lay.addWidget(self.title, 1)
        lay.addWidget(self.hint)

    def sizeHint(self):
        return self.layout().sizeHint()

    def minimumSizeHint(self):
        return self.layout().minimumSize()


class Collapsible(QFrame):
    """A card whose body opens and closes under a header row (board Run
    lines 100-122, *Step through*): a chevron that turns 90° when open,
    the title, and a `hint` shown at the right while closed. Closed by
    default; `toggled(bool)` fires on every change, user or code."""

    toggled = Signal(bool)

    def __init__(self, title, hint='', parent=None):
        super().__init__(parent)
        self.setObjectName('collapsible')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        self.header = _CollapseHeader(title, hint)
        self.header.toggled.connect(self._apply)
        lay.addWidget(self.header)
        self.body = QWidget()
        self.body.setObjectName('collapsebody')
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        lay.addWidget(self.body)
        self.body.setVisible(False)
        self.header.hint.setVisible(bool(hint))
        _on_theme(self, self._recolour)

    def _recolour(self, _mode=None):
        h = self.header
        h.title.setStyleSheet(_css(14, 600, 'text'))
        h.hint.setStyleSheet(_css(12, 400, 'faint'))
        pm = theme.pixmap('chevron_right', 15, color='text')
        if self.is_open():
            dpr = pm.devicePixelRatio()
            pm = pm.transformed(QTransform().rotate(90))
            pm.setDevicePixelRatio(dpr)
        h.chevron.setPixmap(pm)

    def _apply(self, on):
        self.body.setVisible(bool(on))
        self.header.hint.setVisible(not on and bool(self.header.hint.text()))
        self._recolour()
        self.toggled.emit(bool(on))

    def add(self, widget, stretch=0):
        self.body_layout.addWidget(widget, stretch)
        return widget

    def add_layout(self, lay):
        self.body_layout.addLayout(lay)
        return lay

    def set_open(self, on):
        """Open or close the body (emits `toggled` when it changes)."""
        if bool(on) != self.header.isChecked():
            self.header.setChecked(bool(on))

    def is_open(self):
        return self.header.isChecked()

    def hint_text(self):
        """The hint as shown ('' while open), for tests."""
        h = self.header.hint
        return h.text() if not h.isHidden() else ''


# ── Banner and hand-off card ─────────────────────────────────────────────
class Banner(QFrame):
    """The finished-run banner (board Run_Finished): ✓ on `ok_bg` with
    an `ok_border`, a message, and an action button slot."""

    def __init__(self, message='', action_text=None, on_action=None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName('banner')
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)
        self.mark = QLabel('✓')
        self.mark.setFont(_px_font(16, 600))
        self.message = QLabel(str(message))
        self.message.setFont(_px_font(14))
        self.message.setWordWrap(True)
        lay.addWidget(self.mark)
        lay.addWidget(self.message, 1)
        self.action = None
        if action_text:
            self.action = QPushButton(str(action_text))
            self.action.setFont(_px_font(13.5, 600))
            self.action.setFixedHeight(36)
            self.action.setCursor(Qt.PointingHandCursor)
            if on_action is not None:
                self.action.clicked.connect(lambda *_: on_action())
            lay.addWidget(self.action)
        _on_theme(self, self._recolour)

    def _recolour(self, _mode=None):
        self.mark.setStyleSheet(_css(16, 600, 'ok'))
        self.message.setStyleSheet(_css(14, colour='text'))
        if self.action is not None:
            # dark text on the light-green dark-mode ok, white on the
            # darker light-mode ok (both >= 4.5:1, see test_ui_theme)
            fg = '#08140c' if theme.mode() == 'dark' else '#ffffff'
            self.action.setStyleSheet(
                f'QPushButton {{ background: {theme.cur("ok")}; '
                f'color: {fg}; border: none; border-radius: 8px; '
                f'padding: 0px 14px; font-size: 13px; '
                f'font-weight: 600; }}')

    def set(self, message):
        self.message.setText(str(message))


class HandoffCard(QFrame):
    """The chain hand-off card (board Chain): tinted `accent_bg`,
    `accent_border`, caps title + mono file line + caption. GUI-9:
    `tinted=False` is the board's neutral HAND-OFF OUT card (line 209:
    `card` with a `border2` frame, the title in `faint`)."""

    def __init__(self, title='HAND-OFF', parent=None, tinted=True):
        super().__init__(parent)
        self.tinted = bool(tinted)
        self.setObjectName('handoff' if self.tinted else 'handoffplain')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        self.title = QLabel(str(title).upper())
        caps_font = _px_font(11, 600)
        caps_font.setLetterSpacing(QFont.PercentageSpacing, 110)
        self.title.setFont(caps_font)
        self.file = QLabel('')
        self.file.setFont(_px_font(12.5, mono=True))
        self.caption = QLabel('')
        self.caption.setFont(_px_font(12.5))
        self.caption.setWordWrap(True)
        lay.addWidget(self.title)
        lay.addWidget(self.file)
        lay.addWidget(self.caption)
        self.caption.setVisible(False)
        _on_theme(self, self._recolour)

    def _recolour(self, _mode=None):
        self.title.setStyleSheet(_css(11, 600, 'accent_text'
                                      if self.tinted else 'faint'))
        self.file.setStyleSheet(_css(12, colour='text',
                                     family=theme.MONO))
        self.caption.setStyleSheet(_css(12, colour='text2'))

    def set(self, file, text=None):
        self.file.setText(str(file))
        if text is not None:
            self.caption.setText(str(text))
            self.caption.setVisible(bool(text))
