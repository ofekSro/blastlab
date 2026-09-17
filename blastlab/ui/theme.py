"""Design system of the Qt front-end: the palette shared with the Tk app,
fonts and spacing, a Fusion QPalette + a small style sheet per mode, and
the app's icons drawn with QPainter (no asset files).

`apply(app, mode)` switches the whole application; widgets that hold
mode-dependent state (pyqtgraph panes, icon buttons) connect to
`signals.changed` and re-theme themselves.
"""

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QPainter,
                           QPainterPath, QPalette, QPen, QPixmap, QPolygonF)

# ── palette (identical to gui/theme.py so both front-ends look alike) ───
DARK = dict(
    bg='#1a1a1a', card='#2b2b2b', card2='#333333', border='#3a3a3a',
    entry='#222222', accent='#4f9eff', accent_hover='#3f8ce6',
    text='#e8e8e8', muted='#9aa4b2', view='#141414',
    danger='#e5484d', danger_hover='#c93a3f',
    error='#ff6b6b', warn='#ffb86b', ok='#69db7c',
    seg='#3a3f46',
)
LIGHT = dict(
    bg='#f2f4f7', card='#ffffff', card2='#e9edf2', border='#dde2e9',
    entry='#f2f4f7', accent='#3b8bef', accent_hover='#2f7cdd',
    text='#1f2430', muted='#5f6b7a', view='#141414',
    danger='#d13438', danger_hover='#b02a2f',
    error='#d6336c', warn='#c77700', ok='#2f9e44',
    seg='#ced6e0',
)

# ── typography / spacing ─────────────────────────────────────────────────
FONT = 'Segoe UI'
MONO = 'Consolas'
PAD = 16          # outer padding between cards / panel edges
GAP = 8           # inner padding between rows/controls
RADIUS = 10       # buttons and inputs
CARD_RADIUS = 12

_mode = 'dark'


class _Signals(QObject):
    #: emitted with the new mode name after `apply()`
    changed = Signal(str)


signals = _Signals()


def mode():
    return _mode


def pal():
    """The current mode's palette dict."""
    return DARK if _mode == 'dark' else LIGHT


def cur(key):
    """Current-mode colour as a hex string."""
    return pal()[key]


def qcolor(key):
    return QColor(cur(key))


def font(kind='body'):
    """QFont for 'h1' | 'h2' | 'body' | 'small' | 'mono' | 'chip'."""
    if kind == 'h1':
        f = QFont(FONT, 20)
        f.setBold(True)
    elif kind == 'h2':
        f = QFont(FONT, 14)
        f.setBold(True)
    elif kind == 'small':
        f = QFont(FONT, 11)
    elif kind == 'small_bold':
        f = QFont(FONT, 11)
        f.setBold(True)
    elif kind == 'chip':
        f = QFont(FONT, 12)
        f.setBold(True)
    elif kind == 'mono':
        f = QFont(MONO, 12)
    else:
        f = QFont(FONT, 13)
    return f


# ── QPalette + style sheet ───────────────────────────────────────────────
def make_palette(mode_name):
    p = DARK if mode_name == 'dark' else LIGHT
    q = QPalette()
    roles = {
        QPalette.Window: p['bg'], QPalette.WindowText: p['text'],
        QPalette.Base: p['entry'], QPalette.AlternateBase: p['card2'],
        QPalette.Text: p['text'], QPalette.Button: p['card2'],
        QPalette.ButtonText: p['text'], QPalette.Highlight: p['accent'],
        QPalette.HighlightedText: '#ffffff', QPalette.ToolTipBase: p['card2'],
        QPalette.ToolTipText: p['text'], QPalette.PlaceholderText: p['muted'],
        QPalette.Link: p['accent'], QPalette.Mid: p['border'],
        QPalette.Dark: p['border'], QPalette.Light: p['card'],
        QPalette.Shadow: p['bg'],
    }
    for role, colour in roles.items():
        q.setColor(role, QColor(colour))
    # disabled text stays legible (the CTk app needed a workaround for this)
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        q.setColor(QPalette.Disabled, role, QColor(p['muted']))
    q.setColor(QPalette.Disabled, QPalette.Base, QColor(p['card']))
    q.setColor(QPalette.Disabled, QPalette.Button, QColor(p['card']))
    return q


def qss(mode_name):
    p = DARK if mode_name == 'dark' else LIGHT
    return f"""
    QWidget {{ font-family: "{FONT}"; font-size: 13pt; }}
    QToolTip {{ background: {p['card2']}; color: {p['text']};
                border: 1px solid {p['border']}; padding: 4px 6px; }}
    QFrame#card {{ background: {p['card']}; border: 1px solid {p['border']};
                   border-radius: {CARD_RADIUS}px; }}
    QFrame#chip {{ background: {p['card2']}; border-radius: 8px; }}
    QFrame#sidebar {{ background: {p['bg']}; }}
    QLabel {{ background: transparent; }}
    QLabel#h1 {{ font-size: 20pt; font-weight: bold; color: {p['text']}; }}
    QLabel#h2 {{ font-size: 14pt; font-weight: bold; color: {p['text']}; }}
    QLabel#muted {{ color: {p['muted']}; }}
    QLabel#small {{ color: {p['muted']}; font-size: 11pt; }}
    QLabel#view {{ background: {DARK['view']}; color: {DARK['muted']};
                   border-radius: 6px; }}
    QPushButton {{ background: {p['card2']}; color: {p['text']};
                   border: none; border-radius: {RADIUS}px;
                   padding: 6px 14px; min-height: 24px; }}
    QPushButton:hover {{ background: {p['border']}; }}
    QPushButton:disabled {{ color: {p['muted']}; background: {p['card2']}; }}
    QPushButton#primary {{ background: {p['accent']}; color: white; }}
    QPushButton#primary:hover {{ background: {p['accent_hover']}; }}
    QPushButton#primary:disabled {{ background: {p['card2']};
                                    color: {p['muted']}; }}
    QPushButton#danger {{ background: {p['danger']}; color: white; }}
    QPushButton#danger:hover {{ background: {p['danger_hover']}; }}
    QPushButton#danger:disabled {{ background: {p['card2']};
                                   color: {p['muted']}; }}
    QPushButton#nav {{ background: transparent; color: {p['text']};
                       text-align: left; padding: 8px 12px; }}
    QPushButton#nav:hover {{ background: {p['card']}; }}
    QPushButton#nav[active="true"] {{ background: {p['card']};
                                      color: {p['accent']}; }}
    QPushButton#quiet {{ background: transparent; color: {p['muted']};
                         text-align: left; padding: 6px 12px; }}
    QPushButton#quiet:hover {{ background: {p['card']}; }}
    QPushButton#link {{ background: transparent; color: {p['accent']};
                        padding: 0px 4px; min-height: 16px; }}
    QPushButton#link:hover {{ background: {p['card']}; }}
    QToolButton#seg {{ background: {p['seg']}; color: {p['text']};
                       border: none; padding: 4px 12px; }}
    QToolButton#seg:hover {{ background: {p['border']}; }}
    QToolButton#seg:checked {{ background: {p['accent']}; color: white; }}
    QToolButton#seg[pos="first"] {{ border-top-left-radius: {RADIUS}px;
                                    border-bottom-left-radius: {RADIUS}px; }}
    QToolButton#seg[pos="last"] {{ border-top-right-radius: {RADIUS}px;
                                   border-bottom-right-radius: {RADIUS}px; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit,
    QTextEdit {{ background: {p['entry']}; color: {p['text']};
                 border: 1px solid {p['border']}; border-radius: 8px;
                 padding: 3px 6px; selection-background-color: {p['accent']}; }}
    QLineEdit:disabled {{ color: {p['muted']}; }}
    /* a field the validator refused: `error` is the Run tab's refresh box,
       `bad` is what the Setup form's mark_fields() sets */
    QLineEdit[error="true"], QLineEdit[bad="true"],
    QComboBox[bad="true"] {{ border: 1px solid {p['error']}; }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {p['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{ background: {p['card2']}; color: {p['text']};
                                   selection-background-color: {p['accent']}; }}
    QPlainTextEdit#log {{ font-family: "{MONO}"; font-size: 12pt;
                          border: none; }}
    QCheckBox, QRadioButton {{ color: {p['text']}; spacing: 6px; }}
    QCheckBox:disabled, QRadioButton:disabled {{ color: {p['muted']}; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 17px; height: 17px; }}
    QProgressBar {{ background: {p['card2']}; border: none;
                    border-radius: 4px; max-height: 8px; }}
    QProgressBar::chunk {{ background: {p['accent']}; border-radius: 4px; }}
    QSlider::groove:horizontal {{ background: {p['card2']}; height: 6px;
                                  border-radius: 3px; }}
    QSlider::sub-page:horizontal {{ background: {p['accent']};
                                    border-radius: 3px; }}
    QSlider::handle:horizontal {{ background: {p['accent']}; width: 14px;
                                  margin: -5px 0; border-radius: 7px; }}
    QSlider::handle:horizontal:hover {{ background: {p['accent_hover']}; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {p['card2']}; min-height: 24px;
                                   border-radius: 5px; }}
    QScrollBar::handle:vertical:hover {{ background: {p['border']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {p['card2']}; min-width: 24px;
                                     border-radius: 5px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QSplitter::handle {{ background: transparent; }}
    QSplitter::handle:horizontal {{ width: 8px; }}
    QTableWidget, QTableView, QTreeView {{ background: {p['entry']};
        color: {p['text']}; border: none; gridline-color: {p['border']};
        selection-background-color: {p['accent']}; selection-color: white; }}
    QHeaderView::section {{ background: {p['card2']}; color: {p['muted']};
        border: none; padding: 4px 6px; font-weight: bold; font-size: 11pt; }}
    QStatusBar {{ color: {p['muted']}; }}
    QMenu {{ background: {p['card2']}; color: {p['text']};
             border: 1px solid {p['border']}; }}
    QMenu::item:selected {{ background: {p['accent']}; color: white; }}
    """


def apply(app, mode_name='dark'):
    """Switch the application to `mode_name` ('dark' | 'light')."""
    global _mode
    _mode = 'light' if str(mode_name).lower() == 'light' else 'dark'
    app.setStyle('Fusion')
    app.setPalette(make_palette(_mode))
    app.setStyleSheet(qss(_mode))
    _ICON_CACHE.clear()
    signals.changed.emit(_mode)


def repolish(widget):
    """Re-evaluate the style sheet after a dynamic property changed
    (e.g. `error` on a QLineEdit, `active` on a nav button)."""
    st = widget.style()
    st.unpolish(widget)
    st.polish(widget)
    widget.update()


# ── icons (drawn with QPainter, no asset files) ──────────────────────────
_ICON_CACHE = {}


def _shape(name, p, S, lw):
    """Draw glyph `name` in white on the S x S canvas (coords 0-100)."""
    u = S / 100.0
    white = QColor('white')
    pen = QPen(white, lw)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(QBrush(white))

    def pt(x, y):
        return QPointF(x * u, y * u)

    def poly(*pts, fill=True, w=lw):
        pg = QPolygonF([pt(x, y) for x, y in pts])
        if fill:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(white))
        else:
            pn = QPen(white, w)
            pn.setJoinStyle(Qt.RoundJoin)
            p.setPen(pn)
            p.setBrush(Qt.NoBrush)
        p.drawPolygon(pg)
        p.setPen(pen)
        p.setBrush(QBrush(white))

    def line(*pts, w=lw):
        pn = QPen(white, w)
        pn.setCapStyle(Qt.RoundCap)
        pn.setJoinStyle(Qt.RoundJoin)
        p.setPen(pn)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(pt(*pts[0]))
        for x, y in pts[1:]:
            path.lineTo(pt(x, y))
        p.drawPath(path)
        p.setPen(pen)
        p.setBrush(QBrush(white))

    def dot(x, y, r):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(white))
        p.drawEllipse(pt(x, y), r * u, r * u)
        p.setPen(pen)

    def ring(x, y, r, w=lw):
        pn = QPen(white, w)
        p.setPen(pn)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(pt(x, y), r * u, r * u)
        p.setPen(pen)
        p.setBrush(QBrush(white))

    def rrect(x0, y0, x1, y1, r, fill=True, w=lw):
        rect = QRectF(x0 * u, y0 * u, (x1 - x0) * u, (y1 - y0) * u)
        if fill:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(white))
        else:
            p.setPen(QPen(white, w))
            p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, r * u, r * u)
        p.setPen(pen)
        p.setBrush(QBrush(white))

    def rect(x0, y0, x1, y1, fill=True, w=lw):
        rrect(x0, y0, x1, y1, 0, fill=fill, w=w)

    if name == 'play':
        poly((32, 18), (32, 82), (86, 50))
    elif name == 'stop':
        rrect(26, 26, 74, 74, 8)
    elif name == 'pause':
        for x0 in (30, 56):
            rrect(x0, 20, x0 + 14, 80, 5)
    elif name == 'end':                      # fast-forward to end
        poly((16, 24), (16, 76), (48, 50))
        poly((46, 24), (46, 76), (78, 50))
        rrect(78, 24, 88, 76, 4)
    elif name == 'flag':                     # initialise model
        line((30, 14), (30, 86), w=lw * 1.1)
        poly((30, 18), (76, 28), (30, 46))
    elif name == 'sliders':                  # setup
        for y, kx in ((26, 62), (50, 36), (74, 66)):
            line((12, y), (88, y))
            dot(kx, y, 9)
    elif name == 'chart':                    # results
        for x0, y0 in ((14, 52), (41, 32), (68, 14)):
            rrect(x0, y0, x0 + 18, 86, 4)
    elif name == 'chain':
        ring(35, 50, 21)
        ring(65, 50, 21)
    elif name == 'folder':
        poly((10, 26), (38, 26), (46, 36), (90, 36), (90, 78), (10, 78))
    elif name == 'save':
        poly((16, 16), (70, 16), (84, 30), (84, 84), (16, 84), fill=False)
        rect(32, 18, 62, 38, fill=False, w=lw * 0.8)
        rect(30, 54, 70, 82, fill=False, w=lw * 0.8)
    elif name == 'cube':
        hexpts = ((50, 8), (86, 29), (86, 71), (50, 92), (14, 71), (14, 29))
        poly(*hexpts, fill=False)
        for x, y in ((14, 29), (86, 29), (50, 92)):
            line((50, 50), (x, y), w=lw * 0.9)
    elif name == 'image':
        rrect(10, 18, 90, 82, 8, fill=False)
        dot(33, 38, 7)
        line((18, 74), (42, 50), (58, 64), (73, 44), (87, 60), w=lw * 0.9)
    elif name == 'table':
        rrect(12, 20, 88, 80, 6, fill=False)
        line((12, 42), (88, 42), w=lw * 0.8)
        line((42, 42), (42, 80), w=lw * 0.8)
        line((66, 42), (66, 80), w=lw * 0.8)
    elif name == 'film':
        rrect(14, 22, 86, 78, 6, fill=False)
        line((30, 22), (30, 78), w=lw * 0.8)
        line((70, 22), (70, 78), w=lw * 0.8)
        for y in (30, 46, 62):
            rect(19, y, 25, y + 8)
            rect(75, y, 81, y + 8)
    elif name == 'curve':
        line((10, 80), (26, 80), (34, 18), (44, 62), (56, 40),
             (70, 68), (90, 70), w=lw * 1.05)
    elif name == 'export':
        line((22, 58), (22, 84), (78, 84), (78, 58))
        line((50, 64), (50, 20), w=lw * 1.05)
        line((34, 34), (50, 18), (66, 34), w=lw * 1.05)
    elif name == 'sun':
        ring(50, 50, 17)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (.7, .7), (-.7, .7), (.7, -.7), (-.7, -.7)):
            line((50 + 26 * dx, 50 + 26 * dy), (50 + 38 * dx, 50 + 38 * dy),
                 w=lw * 0.95)
    elif name == 'moon':
        full = QPainterPath()
        full.addEllipse(QRectF(0.18 * S, 0.16 * S, 0.64 * S, 0.64 * S))
        bite = QPainterPath()
        bite.addEllipse(QRectF(0.34 * S, 0.04 * S, 0.60 * S, 0.60 * S))
        p.setPen(Qt.NoPen)
        p.drawPath(full.subtracted(bite))
        p.setPen(pen)
    elif name == 'plus':
        line((50, 24), (50, 76), w=lw * 1.15)
        line((24, 50), (76, 50), w=lw * 1.15)
    elif name == 'minus':
        line((24, 50), (76, 50), w=lw * 1.15)
    elif name == 'check':
        line((20, 54), (42, 74), (80, 28), w=lw * 1.3)
    elif name == 'error':
        ring(50, 50, 36)
        line((38, 38), (62, 62), w=lw * 1.05)
        line((62, 38), (38, 62), w=lw * 1.05)
    elif name == 'warning':
        poly((50, 12), (92, 84), (8, 84), fill=False)
        line((50, 36), (50, 60), w=lw * 1.05)
        dot(50, 72, 4.5)
    elif name == 'info':
        ring(50, 50, 36)
        dot(50, 32, 5)
        line((50, 45), (50, 70), w=lw * 1.05)
    elif name == 'eye':
        pn = QPen(white, lw)
        pn.setCapStyle(Qt.RoundCap)
        p.setPen(pn)
        p.setBrush(Qt.NoBrush)
        box = QRectF(14 * u, 22 * u, 72 * u, 56 * u)
        p.drawArc(box, 20 * 16, 140 * 16)
        p.drawArc(box, 200 * 16, 140 * 16)
        p.setPen(pen)
        dot(50, 50, 11)
    elif name == 'detach':                   # window with an arrow out
        rrect(12, 24, 64, 80, 6, fill=False)
        line((52, 20), (88, 20), (88, 56), w=lw * 0.9)
        line((60, 48), (88, 20), w=lw * 0.9)
    elif name == 'chevron_left':
        line((62, 22), (36, 50), (62, 78), w=lw * 1.2)
    elif name == 'chevron_right':
        line((38, 22), (64, 50), (38, 78), w=lw * 1.2)
    elif name == 'step_back':
        rrect(18, 26, 28, 74, 3)
        poly((80, 26), (80, 74), (36, 50))
    elif name == 'step_fwd':
        rrect(72, 26, 82, 74, 3)
        poly((20, 26), (20, 74), (64, 50))
    elif name == 'loop':
        pn = QPen(white, lw)
        pn.setCapStyle(Qt.RoundCap)
        p.setPen(pn)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(18 * u, 22 * u, 64 * u, 56 * u), 30 * 16, 280 * 16)
        p.setPen(pen)
        poly((74, 18), (90, 34), (68, 40))
    else:
        raise KeyError(name)


def _glyph(name, size, colour):
    """Render glyph `name` at 4x resolution tinted with `colour`."""
    S = size * 4
    pm = QPixmap(S, S)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    try:
        _shape(name, p, S, lw=S * 0.075)
    finally:
        p.end()
    # tint: keep the alpha, replace the colour
    tinted = QPixmap(S, S)
    tinted.fill(Qt.transparent)
    q = QPainter(tinted)
    q.setCompositionMode(QPainter.CompositionMode_Source)
    q.drawPixmap(0, 0, pm)
    q.setCompositionMode(QPainter.CompositionMode_SourceIn)
    q.fillRect(tinted.rect(), QColor(colour))
    q.end()
    tinted.setDevicePixelRatio(4.0)
    return tinted


def icon(name, size=16, color=None):
    """A cached QIcon of the named glyph. Default colouring follows the
    text colour of the current mode (muted when disabled); pass `color`
    to force one (e.g. 'white' for icons sitting on accent buttons)."""
    key = (name, size, color, _mode)
    ic = _ICON_CACHE.get(key)
    if ic is None:
        ic = QIcon()
        normal = _glyph(name, size, color or cur('text'))
        ic.addPixmap(normal, QIcon.Normal)
        ic.addPixmap(normal, QIcon.Active)
        ic.addPixmap(_glyph(name, size, color or cur('muted')),
                     QIcon.Disabled)
        _ICON_CACHE[key] = ic
    return ic


def pixmap(name, size=16, color=None):
    return _glyph(name, size, color or cur('text'))


# ── matplotlib figure theming ────────────────────────────────────────────
def style_figure(fig):
    """Recolour a Figure's chrome in place to match the current mode.

    Only figures shown ON SCREEN pass through here (the Results previews
    and gauge traces); exports build their own figures and keep
    matplotlib's default light style, so a PNG is readable on paper
    whatever the app's appearance is."""
    p = pal()
    dark = _mode == 'dark'
    face = p['card']
    axface = p['entry'] if dark else p['card']
    fig.patch.set_facecolor(face)
    for txt in fig.texts:                                  # suptitles
        txt.set_color(p['text'])
    for ax in fig.axes:
        try:
            ax.set_facecolor(axface)
        except Exception:
            pass
        for sp in getattr(ax, 'spines', {}).values():
            sp.set_color(p['border'])
        ax.tick_params(colors=p['muted'], labelcolor=p['muted'],
                       which='both')
        for axis_name in ('xaxis', 'yaxis', 'zaxis'):
            axis = getattr(ax, axis_name, None)
            if axis is None:
                continue
            axis.label.set_color(p['text'])
            if hasattr(axis, 'pane'):                      # 3D axes
                axis.pane.set_facecolor(face)
                axis.pane.set_edgecolor(p['border'])
        ax.title.set_color(p['text'])
        leg = ax.get_legend()
        if leg is not None:
            leg.get_frame().set_facecolor(axface)
            leg.get_frame().set_edgecolor(p['border'])
            for t in leg.get_texts():
                t.set_color(p['text'])
    return fig
