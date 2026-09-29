"""Design system of the Qt front-end: the GUI redesign's own warm-black
palette (docs/gui-redesign-plan.md §2 - the Tk app keeps its own palette
in gui/theme.py, untouched), bundled fonts, spacing, a Fusion QPalette +
a small style sheet per mode, and the app's icons drawn with QPainter
(no asset files).

`apply(app, mode)` switches the whole application; widgets that hold
mode-dependent state (pyqtgraph panes, icon buttons) connect to
`signals.changed` and re-theme themselves.
"""

import os

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QIcon,
                           QPainter, QPainterPath, QPalette, QPen, QPixmap,
                           QPolygonF)

# ── palette (GUI-1: docs/gui-redesign-plan.md §2.1 / §2.2) ──────────────
# `error` / `danger_hover` have no §2.1 value: derived from the `danger`
# family (error = danger; hover one step lighter in dark, darker in
# light). `tile` is the same value as `card2`, both keys kept (§2.1).
DARK = dict(
    bg='#0b0b0c', panel='#0e0e10', card='#111113', card2='#141416',
    tile='#141416', view='#0d0d0f', hover='#1c1c1f', seg='#2a2a2f',
    border='#1f1f23', border2='#242428', entry='#0b0b0c',
    entry_border='#2c2c31', text='#f2efe9', text2='#cfcac2',
    muted='#a8a39b', faint='#8f8a82', num_dim='#6f6a63',
    accent='#ff6a2b', accent_hover='#ff7f47', on_accent='#1a0d06',
    accent_text='#ff8a55', accent_soft='#ffb896', accent_bg='#1d1511',
    accent_border='#5a3522', gauge='#4cc9f0', gauge_bg='#0f1a1f',
    ok='#7ddc9a', ok_bg='#121814', ok_border='#24302a', warn='#f5d061',
    danger='#ff5c7a', danger_hover='#ff7490', error='#ff5c7a',
    stop_bg='#26141a', stop_border='#6b2a37', stop_text='#ff9aac',
    title_bar='#202024',
)
# Light mode per plan §2.2, keys it omits derived with the same roles.
# Six of the §2.2 proposed values failed the 4.5:1 contrast gate the
# same section imposes and were darkened until they pass (measured by
# tests/test_ui_theme.py): faint #7a7e85->#696c72,
# accent_text #c7430f->#c5420f, gauge #0e7fa6->#0d7599,
# ok #2f9e44->#257d36, warn #b07d00->#926800, danger #d6336c->#cb3067.
LIGHT = dict(
    bg='#f4f3f0', panel='#faf9f7', card='#ffffff', card2='#f1efeb',
    tile='#f1efeb', view='#ecebe7', hover='#e9e6e1', seg='#dcd8d1',
    border='#e2ded7', border2='#d8d3cb', entry='#ffffff',
    entry_border='#cdc7be', text='#1f2430', text2='#3a3f4a',
    muted='#5f6368', faint='#696c72', num_dim='#9b958c',
    accent='#ff6a2b', accent_hover='#e85d20', on_accent='#1a0d06',
    accent_text='#c5420f', accent_soft='#b4461c', accent_bg='#fbe9df',
    accent_border='#e0b394', gauge='#0d7599', gauge_bg='#e3f1f7',
    ok='#257d36', ok_bg='#e7f3ea', ok_border='#c4dccb', warn='#926800',
    danger='#cb3067', danger_hover='#b52a5b', error='#cb3067',
    stop_bg='#fbe4e9', stop_border='#e3aab8', stop_text='#b02a48',
    title_bar='#dedad3',
)

# ── typography / spacing (plan §2.3: OFL fonts bundled under fonts/) ────
FONT = 'IBM Plex Sans'
MONO = 'IBM Plex Mono'
DISPLAY = 'Space Grotesk'
#: fallbacks when a bundled TTF is missing - the app must never crash
#: over a font (plan §2.3)
FONT_FALLBACK = 'Segoe UI'
MONO_FALLBACK = 'Consolas'
#: where the bundled TTFs live - the package directory, never
#: %WINDIR%\Fonts (plan §11: the Store-Python sandbox)
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'fonts')
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


def _body_font(size):
    f = QFont()
    f.setFamilies([FONT, FONT_FALLBACK])
    f.setPointSize(size)
    return f


def _display_font(size, weight=QFont.DemiBold):
    """Space Grotesk (600-700), falling back to Segoe UI (plan §2.3)."""
    f = QFont()
    f.setFamilies([DISPLAY, FONT, FONT_FALLBACK])
    f.setPointSize(size)
    f.setWeight(weight)
    return f


def font(kind='body'):
    """QFont for 'h1' | 'h2' | 'display' | 'body' | 'small' |
    'small_bold' | 'chip' | 'mono' (plan §2.3: h1/h2/display are the
    Space Grotesk display family, body is IBM Plex Sans, mono is IBM
    Plex Mono, each with a system fallback)."""
    if kind == 'h1':
        f = _display_font(20, QFont.Bold)
    elif kind == 'h2':
        f = _display_font(14, QFont.Bold)
    elif kind == 'display':
        # stat-tile values, step titles: SG 600, 21-26 px (plan §2.5)
        f = _display_font(16, QFont.DemiBold)
    elif kind == 'small':
        f = _body_font(11)
    elif kind == 'small_bold':
        f = _body_font(11)
        f.setBold(True)
    elif kind == 'chip':
        f = _body_font(12)
        f.setBold(True)
    elif kind == 'mono':
        f = QFont()
        f.setFamilies([MONO, MONO_FALLBACK])
        f.setPointSize(12)
    else:
        f = _body_font(13)
    return f


# ── bundled fonts (plan §2.3) ────────────────────────────────────────────
_fonts_loaded = False


def _load_fonts():
    """Register every bundled TTF under `FONT_DIR` once per process.

    Called from `apply()`, so every entry path (the app, the tests, the
    QA harness) gets the families. A missing directory or a bad file is
    silently survived: the QFont fallbacks take over (plan §2.3 - never
    crash over a font)."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    _fonts_loaded = True
    try:
        for base, _dirs, files in os.walk(FONT_DIR):
            for name in files:
                if name.lower().endswith('.ttf'):
                    try:
                        QFontDatabase.addApplicationFont(
                            os.path.join(base, name))
                    except Exception:
                        pass
    except Exception:
        pass


# ── QPalette + style sheet ───────────────────────────────────────────────
def make_palette(mode_name):
    p = DARK if mode_name == 'dark' else LIGHT
    q = QPalette()
    roles = {
        QPalette.Window: p['bg'], QPalette.WindowText: p['text'],
        QPalette.Base: p['entry'], QPalette.AlternateBase: p['card2'],
        QPalette.Text: p['text'], QPalette.Button: p['card2'],
        QPalette.ButtonText: p['text'], QPalette.Highlight: p['accent'],
        # never white on the orange Highlight (plan §2.1: on_accent)
        QPalette.HighlightedText: p['on_accent'],
        QPalette.ToolTipBase: p['card2'],
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
    # Danger buttons: white fails 4.5:1 on the dark danger #ff5c7a
    # (2.97:1) and passes on the light #cb3067 (5.78:1) - measured by
    # tests/test_ui_theme.py, so the dark mode uses on_accent dark text.
    danger_fg = p['on_accent'] if mode_name == 'dark' else 'white'
    return f"""
    QWidget {{ font-family: "{FONT}"; font-size: 13pt; }}
    QToolTip {{ background: {p['card2']}; color: {p['text']};
                border: 1px solid {p['border']}; padding: 4px 6px; }}
    QFrame#card {{ background: {p['card']}; border: 1px solid {p['border2']};
                   border-radius: {CARD_RADIUS}px; }}
    QFrame#chip {{ background: {p['card2']}; border-radius: 8px; }}
    QLabel {{ background: transparent; }}
    /* the app-wide QWidget font rule overrides programmatic QFont
       family/size (measured), so the display family is set here too */
    QLabel#h1 {{ font-family: "{DISPLAY}"; font-size: 20pt;
                 font-weight: bold; color: {p['text']}; }}
    QLabel#h2 {{ font-family: "{DISPLAY}"; font-size: 14pt;
                 font-weight: bold; color: {p['text']}; }}
    QLabel#muted {{ color: {p['muted']}; }}
    QLabel#small {{ color: {p['muted']}; font-size: 11pt; }}
    QLabel#view {{ background: {p['view']}; color: {p['muted']};
                   border-radius: 6px; }}
    QPushButton {{ background: {p['card2']}; color: {p['text']};
                   border: none; border-radius: {RADIUS}px;
                   padding: 6px 14px; min-height: 24px; }}
    QPushButton:hover {{ background: {p['border']}; }}
    QPushButton:disabled {{ color: {p['muted']}; background: {p['card2']}; }}
    QPushButton#primary {{ background: {p['accent']};
                           color: {p['on_accent']}; }}
    QPushButton#primary:hover {{ background: {p['accent_hover']}; }}
    QPushButton#primary:disabled {{ background: {p['card2']};
                                    color: {p['muted']}; }}
    QPushButton#danger {{ background: {p['danger']}; color: {danger_fg}; }}
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
    QToolButton#seg {{ background: transparent; color: {p['muted']};
                       border: none; padding: 4px 12px; }}
    QToolButton#seg:hover {{ background: {p['hover']}; }}
    QToolButton#seg:checked {{ background: {p['seg']};
                               color: {p['text']}; }}
    QToolButton#seg[pos="first"] {{ border-top-left-radius: {RADIUS}px;
                                    border-bottom-left-radius: {RADIUS}px; }}
    QToolButton#seg[pos="last"] {{ border-top-right-radius: {RADIUS}px;
                                   border-bottom-right-radius: {RADIUS}px; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit,
    QTextEdit {{ background: {p['entry']}; color: {p['text']};
                 border: 1px solid {p['entry_border']}; border-radius: 8px;
                 padding: 3px 6px; selection-background-color: {p['accent']};
                 selection-color: {p['on_accent']}; }}
    QLineEdit:disabled {{ color: {p['muted']}; }}
    /* a field the validator refused: `error` is the Run tab's refresh box,
       `bad` is what the Setup form's mark_fields() sets */
    QLineEdit[error="true"], QLineEdit[bad="true"],
    QComboBox[bad="true"] {{ border: 1px solid {p['error']}; }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {p['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{ background: {p['card2']}; color: {p['text']};
                                   selection-background-color: {p['accent']};
                                   selection-color: {p['on_accent']}; }}
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
        selection-background-color: {p['accent']};
        selection-color: {p['on_accent']}; }}
    QHeaderView::section {{ background: {p['card2']}; color: {p['muted']};
        border: none; padding: 4px 6px; font-weight: bold; font-size: 11pt; }}
    QStatusBar {{ color: {p['muted']}; }}
    QMenu {{ background: {p['card2']}; color: {p['text']};
             border: 1px solid {p['border']}; }}
    /* GUI-4 shared components (ui/components.py, plan §2.5) */
    QFrame#tile {{ background: {p['tile']}; border: none;
                   border-radius: 10px; }}
    QFrame#tile[variant="accent"] {{ background: {p['accent_bg']}; }}
    QFrame#treerow {{ background: transparent; border: none;
                      border-radius: 9px; }}
    QFrame#treerow:hover {{ background: {p['hover']}; }}
    QFrame#treerow[selected="true"] {{ background: {p['accent_bg']}; }}
    QToolButton#docktab {{ background: transparent; border: none;
                           border-bottom: 2px solid transparent;
                           padding: 0px 14px; color: {p['muted']};
                           font-size: 13px; font-weight: 600; }}
    QToolButton#docktab:checked {{ color: {p['text']};
                                   border-bottom: 2px solid {p['accent']}; }}
    QFrame#banner {{ background: {p['ok_bg']};
                     border: 1px solid {p['ok_border']};
                     border-radius: 10px; }}
    QFrame#handoff {{ background: {p['accent_bg']};
                      border: 1px solid {p['accent_border']};
                      border-radius: 10px; }}
    QMenu::item:selected {{ background: {p['accent']};
                            color: {p['on_accent']}; }}
    QMenu::item:disabled {{ color: {p['muted']}; }}
    /* GUI-3 window frame (ui/topbar.py + the status bar, plan §4;
       board BC_Combined lines 20-54 / 392-396). Sizes in px because the
       board writes px; the app-wide QWidget font rule would otherwise
       override any programmatic QFont (D6). */
    QFrame#topbar {{ background: {p['bg']}; border: none;
                     border-bottom: 1px solid {p['border']}; }}
    QFrame#statusbar {{ background: {p['bg']}; border: none;
                        border-top: 1px solid {p['border']}; }}
    QPushButton#pill {{ background: transparent; color: {p['muted']};
                        border: none; border-radius: 20px;
                        padding: 0px 10px;
                        font-family: "{DISPLAY}"; font-size: 14px;
                        font-weight: 600; }}
    QPushButton#pill:hover {{ background: {p['hover']}; }}
    QPushButton#pill[active="true"] {{ background: {p['text']};
                                       color: {p['bg']}; }}
    QPushButton#chainlink {{ background: transparent; color: {p['muted']};
                             border: none; border-radius: 8px;
                             padding: 0px 8px; font-size: 13px; }}
    QPushButton#chainlink:hover {{ background: {p['hover']}; }}
    QPushButton#chainlink[active="true"] {{ color: {p['text']}; }}
    QPushButton#casebtn {{ background: transparent; color: {p['text']};
                           border: none; border-radius: 8px;
                           padding: 0px 6px;
                           font-family: "{DISPLAY}"; font-size: 17px;
                           font-weight: 600; }}
    QPushButton#casebtn:hover {{ background: {p['hover']}; }}
    QPushButton#chipbtn {{ background: transparent; color: {p['text2']};
                           border: 1px solid {p['seg']};
                           border-radius: 16px; padding: 0px 10px;
                           font-size: 12px; }}
    QPushButton#chipbtn:hover {{ background: {p['hover']}; }}
    /* the bar's dimension segments at the board's 12.5 px (the app-wide
       font rule would render them 13 pt and push the bar past 1100) */
    QFrame#topbar QToolButton#seg {{ font-size: 12px; }}
    /* GUI-5 Setup (board BC_Combined lines 58-121, 268-388): the tree
       and properties columns, px sizes as the board writes them (D6) */
    QFrame#setuptree, QFrame#setupprops {{ background: {p['panel']};
        border: 1px solid {p['border']}; border-radius: 10px; }}
    QLabel#eyebrow {{ font-size: 11px; font-weight: 600;
                      color: {p['faint']}; }}
    QLabel#propstitle {{ font-family: "{DISPLAY}"; font-size: 22px;
                         font-weight: 600; color: {p['text']}; }}
    QLabel#propscaption {{ font-size: 12px; color: {p['muted']}; }}
    QFrame#treechild {{ background: transparent; border: none;
                        border-radius: 7px; }}
    QFrame#treechild:hover {{ background: {p['hover']}; }}
    QLabel#childname {{ font-size: 13px; color: {p['text2']}; }}
    QLabel#childval {{ font-family: "{MONO}"; font-size: 11px;
                       color: {p['faint']}; }}
    QLabel#treemark_gauge {{ font-size: 12px; font-weight: 700;
                             color: {p['gauge']}; }}
    QLabel#treemark_obstacle {{ font-size: 12px; color: {p['text2']}; }}
    QPushButton#treeadd {{ background: transparent; color: {p['text2']};
                           border: 1px solid {p['entry_border']};
                           border-radius: 8px; padding: 0px 8px;
                           font-size: 13px; font-weight: 500; }}
    QPushButton#treeadd:hover {{ background: {p['hover']}; }}
    /* the case pill: the state colour is on its icon (setup_tree); the
       text stays >= 4.5:1 in both modes (ok/warn on ok_bg measured
       4.38 in light, danger on stop_bg 4.18 - too low for text) */
    QPushButton#casepill {{ text-align: left; padding: 0px 12px;
                            border-radius: 10px; font-size: 13px;
                            font-weight: 500; background: {p['ok_bg']};
                            border: 1px solid {p['ok_border']};
                            color: {p['text2']}; }}
    QPushButton#casepill[state="error"] {{ background: {p['stop_bg']};
                                          border: 1px solid {p['stop_border']};
                                          color: {p['stop_text']}; }}
    QLabel#trigtitle {{ font-size: 14px; font-weight: 600;
                        color: {p['text']}; }}
    QLabel#derivedkey {{ font-size: 13px; color: {p['muted']}; }}
    QLabel#derivedval {{ font-family: "{MONO}"; font-size: 13px;
                         color: {p['text']}; }}
    QFrame#card[flash="true"] {{ border: 1px solid {p['accent']}; }}
    /* GUI-5b Setup centre (board BC_Combined lines 125-265): the Run
       column of the live-number strip */
    QPushButton#runbig {{ background: {p['accent']}; border: none;
                          border-radius: 10px; padding: 0px;
                          min-height: 0px; }}
    QPushButton#runbig:hover {{ background: {p['accent_hover']}; }}
    QPushButton#runbig:disabled {{ background: {p['card2']}; }}
    QLabel#runbigtext {{ font-family: "{DISPLAY}"; font-size: 18px;
                         font-weight: 700; color: {p['on_accent']}; }}
    QLabel#runbigkey {{ font-family: "{MONO}"; font-size: 11px;
                        font-weight: 500; color: {p['on_accent']};
                        background: rgba(0, 0, 0, 40); border-radius: 4px;
                        padding: 1px 5px; }}
    QLabel#runbigtext:disabled, QLabel#runbigkey:disabled {{
        color: {p['muted']}; }}
    QPushButton#initbtn {{ background: transparent; color: {p['text2']};
                           border: 1px solid {p['entry_border']};
                           border-radius: 8px; padding: 0px 8px;
                           min-height: 0px; font-size: 12px;
                           font-weight: 500; }}
    QPushButton#initbtn:hover {{ background: {p['hover']}; }}
    QPushButton#initbtn:disabled {{ color: {p['muted']}; }}
    /* the model view's toolbar (board lines 163-167): Z rings, Mesh, Fit */
    QPushButton#viewtool {{ background: transparent; color: {p['muted']};
                            border: 1px solid {p['entry_border']};
                            border-radius: 6px; padding: 0px 10px;
                            min-height: 0px; font-size: 12px;
                            font-weight: 500; }}
    QPushButton#viewtool:hover {{ background: {p['hover']}; }}
    QPushButton#viewtool:checked {{ background: {p['accent_bg']};
                                    color: {p['accent_soft']};
                                    border: 1px solid {p['accent_border']}; }}
    QLabel#viewcaption {{ font-size: 12px; color: {p['faint']}; }}
    QLabel#viewcaption[hover="true"] {{ font-family: "{MONO}";
                                        font-size: 11px;
                                        color: {p['text2']}; }}
    """


def apply(app, mode_name='dark'):
    """Switch the application to `mode_name` ('dark' | 'light')."""
    global _mode
    _mode = 'light' if str(mode_name).lower() == 'light' else 'dark'
    _load_fonts()
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
    elif name == 'fit':                      # four corners (board line 166)
        for pts in (((16, 38), (16, 16), (38, 16)),
                    ((62, 16), (84, 16), (84, 38)),
                    ((16, 62), (16, 84), (38, 84)),
                    ((62, 84), (84, 84), (84, 62))):
            line(*pts, w=lw * 0.95)
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


def _resolve_colour(colour):
    """A palette key becomes the current mode's hex; anything else is
    passed to QColor as-is (so 'white' and '#rrggbb' still work)."""
    if colour is not None and colour in pal():
        return cur(colour)
    return colour


def icon(name, size=16, color=None):
    """A cached QIcon of the named glyph. Default colouring follows the
    text colour of the current mode (muted when disabled); pass `color`
    to force one - a palette key (e.g. 'on_accent' for icons sitting on
    accent buttons) or any QColor name."""
    key = (name, size, color, _mode)
    ic = _ICON_CACHE.get(key)
    if ic is None:
        ic = QIcon()
        normal = _glyph(name, size, _resolve_colour(color) or cur('text'))
        ic.addPixmap(normal, QIcon.Normal)
        ic.addPixmap(normal, QIcon.Active)
        ic.addPixmap(_glyph(name, size,
                            _resolve_colour(color) or cur('muted')),
                     QIcon.Disabled)
        _ICON_CACHE[key] = ic
    return ic


def pixmap(name, size=16, color=None):
    return _glyph(name, size, _resolve_colour(color) or cur('text'))


# ── the BlastLab mark and app icon (GUI-2, plan §3, board Logo_Final) ───
# A front stepping across a regular 8 x 8 grid, with a faint wake behind
# it. Drawn from the board's rectangle lists at three hand-tuned sizes
# (64 / 32 / 16); a design is never scaled below 24 px - below that the
# pixel-drawn 16 takes over. Multi-colour, so it does NOT go through
# `_glyph()` (that pipeline tints single-colour glyphs).

#: 64 design: 5x5 cells with a 0.5 inset, radius 1, at these origins
_MARK64_FRONT = [(8, 20), (14, 20), (20, 20), (20, 26), (26, 26),
                 (32, 26), (32, 32), (32, 38), (38, 38), (38, 44),
                 (38, 50)]
_MARK64_WAKE = [(8, 26), (14, 26), (20, 32), (26, 32), (26, 38),
                (32, 44), (32, 50)]
#: 32 design: 3x3 cells, no inset
_MARK32_FRONT = [(4, 10), (7, 10), (10, 10), (10, 13), (13, 13),
                 (16, 13), (16, 16), (16, 19), (19, 19), (19, 22),
                 (19, 25)]
_MARK32_WAKE = [(4, 13), (7, 13), (10, 16), (13, 16), (13, 19),
                (16, 22), (16, 25)]
#: 16 design: frame and five steps only (x, y, w, h)
_MARK16_STEPS = [(2, 4, 3, 2), (5, 5, 2, 3), (7, 7, 2, 2), (8, 9, 3, 2),
                 (10, 11, 2, 3)]


def _draw_mark(p, design, dark, grid=None):
    """Paint the mark in design coordinates (the painter is pre-scaled).
    Board Logo_Final: front #ff6a2b dark / #e0501a light, frame #e7eaee
    / #1f2430, wake at 35 % (30 % light) opacity."""
    front = QColor('#ff6a2b' if dark else '#e0501a')
    frame = QColor('#e7eaee' if dark else '#1f2430')
    wake_opacity = 0.35 if dark else 0.30
    p.setPen(Qt.NoPen)
    if design == 16:            # no grid, no wake - crisp edges
        p.setBrush(QBrush(front))
        for x, y, w, h in _MARK16_STEPS:
            p.drawRect(QRectF(x, y, w, h))
        pen = QPen(frame, 1)
        pen.setJoinStyle(Qt.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(1.5, 1.5, 13, 13))
        return
    if design == 32:
        grid_pen = QPen(QColor(grid or ('#2c3137' if dark else '#d3d8df')), 1)
        p.setPen(grid_pen)
        for k in range(7):
            v = 7.5 + 3 * k
            p.drawLine(QPointF(v, 4), QPointF(v, 28))
            p.drawLine(QPointF(4, v), QPointF(28, v))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(front))
        p.setOpacity(wake_opacity)
        for x, y in _MARK32_WAKE:
            p.drawRect(QRectF(x, y, 3, 3))
        p.setOpacity(1.0)
        for x, y in _MARK32_FRONT:
            p.drawRect(QRectF(x, y, 3, 3))
        pen = QPen(frame, 2)
        pen.setJoinStyle(Qt.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(3, 3, 26, 26))
        return
    # 64 (and larger, scaled up)
    grid_pen = QPen(QColor(grid or ('#353a41' if dark else '#d3d8df')), 0.75)
    p.setPen(grid_pen)
    for k in range(7):
        v = 14 + 6 * k
        p.drawLine(QPointF(v, 8), QPointF(v, 56))
        p.drawLine(QPointF(8, v), QPointF(56, v))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(front))
    p.setOpacity(wake_opacity)
    for x, y in _MARK64_WAKE:
        p.drawRoundedRect(QRectF(x + 0.5, y + 0.5, 5, 5), 1, 1)
    p.setOpacity(1.0)
    for x, y in _MARK64_FRONT:
        p.drawRoundedRect(QRectF(x + 0.5, y + 0.5, 5, 5), 1, 1)
    p.setPen(QPen(frame, 2.5))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(8, 8, 48, 48), 3, 3)


def logo_pixmap(size, mode=None, _grid=None):
    """The BlastLab mark at `size` device pixels (DPR 1, so the pixel
    test reads device pixels). `mode` defaults to the current one."""
    dark = (mode or _mode) != 'light'
    size = int(size)
    design = 64 if size >= 48 else (32 if size >= 24 else 16)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    # the 16 design is drawn to the pixel (board: crispEdges)
    p.setRenderHint(QPainter.Antialiasing, size != 16)
    s = size / design
    p.scale(s, s)
    try:
        _draw_mark(p, design, dark, grid=_grid)
    finally:
        p.end()
    return pm


def app_icon():
    """The app icon: the mark on a #1f1c1b rounded square (radius
    ~20/88, mark ~68/88 of the tile - board Logo_Final, APP ICON).
    One QIcon with 16/24/32/48/64/128/256 pixmaps, to be set on the
    QApplication and the main window (plan §3)."""
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor('#1f1c1b')))
        r = s * 20.0 / 88.0
        p.drawRoundedRect(QRectF(0, 0, s, s), r, r)
        p.end()
        mark_size = max(1, round(s * 68.0 / 88.0))
        mark = logo_pixmap(mark_size, 'dark', _grid='#3a3634')
        q = QPainter(pm)
        off = (s - mark_size) / 2.0
        q.drawPixmap(QPointF(off, off), mark)
        q.end()
        ic.addPixmap(pm)
    return ic


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
