"""Design system for the blastlab GUI (CustomTkinter).

Single source of truth for the palette, fonts, spacing, icons, the Card
container, ttk styling (for the few widgets with no CTk equivalent) and
dark/light theming of embedded matplotlib figures. Every color handed
to a CTk widget is a ("light", "dark") tuple, so switching the
appearance mode restyles the whole app; ttk widgets and matplotlib
figures are re-themed via apply_ttk_style / refresh_embedded.
"""

import weakref
from tkinter import ttk

import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw

# ── palette ──────────────────────────────────────────────────────────────
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


def c(key):
    """("light", "dark") tuple for CTk widget color options."""
    return (LIGHT[key], DARK[key])


def cur(key):
    """The current-mode color as a plain hex string (tk / matplotlib)."""
    pal = DARK if ctk.get_appearance_mode() == 'Dark' else LIGHT
    return pal[key]


# ── typography / spacing ─────────────────────────────────────────────────
FONT = 'Segoe UI'
F_H1 = (FONT, 20, 'bold')
F_H2 = (FONT, 14, 'bold')
F_BODY = (FONT, 13)
F_SMALL = (FONT, 11)
F_MONO = ('Consolas', 12)

PAD = 16          # outer padding between cards / panel edges
GAP = 8           # inner padding between rows/controls
RADIUS = 10       # buttons and inputs
CARD_RADIUS = 12


# ── tkinter-style item access for CTk widgets ────────────────────────────
class _Compat:
    """`widget['state']` / `slider['to']` support (the test suite and a
    few call sites use tkinter item access, which CTk doesn't provide)."""

    def __getitem__(self, key):
        return self.cget(key)


class Button(_Compat, ctk.CTkButton):
    """CTkButton whose DISABLED text stays legible. The default disabled
    tint was nearly invisible in light mode, so Exec / Interrupt / 3D View
    read as blank slabs."""

    def __init__(self, *a, **kw):
        kw.setdefault('text_color_disabled', c('muted'))
        super().__init__(*a, **kw)


class RadioButton(_Compat, ctk.CTkRadioButton):
    pass


class Slider(_Compat, ctk.CTkSlider):
    pass


# ── Card container ───────────────────────────────────────────────────────
class Card(ctk.CTkFrame):
    """Rounded panel with a subtle border and optional title. Children
    go into `self.body` (a transparent inner frame with padding)."""

    def __init__(self, parent, title=None, pad=PAD, **kw):
        kw.setdefault('fg_color', c('card'))
        kw.setdefault('corner_radius', CARD_RADIUS)
        kw.setdefault('border_width', 1)
        kw.setdefault('border_color', c('border'))
        super().__init__(parent, **kw)
        if title:
            ctk.CTkLabel(self, text=title, font=F_H2, anchor='w',
                         text_color=c('text')).pack(
                fill='x', padx=pad, pady=(12, 2))
        self.body = ctk.CTkFrame(self, fg_color='transparent')
        self.body.pack(fill='both', expand=True, padx=pad,
                       pady=((4 if title else 12), 12))


# ── icons (drawn with PIL, no asset files) ───────────────────────────────
_ICON_CACHE = {}


def _shape(name, d, S, lw):
    """Draw glyph `name` in white on the S x S canvas (coords 0-100)."""
    u = S / 100.0

    def P(*pts):
        return [(x * u, y * u) for x, y in pts]

    def line(*pts, w=lw):
        d.line(P(*pts), fill='white', width=int(w), joint='curve')

    def dot(x, y, r):
        d.ellipse([(x - r) * u, (y - r) * u, (x + r) * u, (y + r) * u],
                  fill='white')

    def ring(x, y, r, w=lw):
        d.ellipse([(x - r) * u, (y - r) * u, (x + r) * u, (y + r) * u],
                  outline='white', width=int(w))

    if name == 'play':
        d.polygon(P((32, 18), (32, 82), (86, 50)), fill='white')
    elif name == 'stop':
        d.rounded_rectangle([26 * u, 26 * u, 74 * u, 74 * u],
                            radius=8 * u, fill='white')
    elif name == 'pause':
        for x0 in (30, 56):
            d.rounded_rectangle([x0 * u, 20 * u, (x0 + 14) * u, 80 * u],
                                radius=5 * u, fill='white')
    elif name == 'end':                      # fast-forward to end
        d.polygon(P((16, 24), (16, 76), (48, 50)), fill='white')
        d.polygon(P((46, 24), (46, 76), (78, 50)), fill='white')
        d.rounded_rectangle([78 * u, 24 * u, 88 * u, 76 * u],
                            radius=4 * u, fill='white')
    elif name == 'flag':                     # initialise model
        line((30, 14), (30, 86), w=lw * 1.1)
        d.polygon(P((30, 18), (76, 28), (30, 46)), fill='white')
    elif name == 'sliders':                  # setup
        for y, kx in ((26, 62), (50, 36), (74, 66)):
            line((12, y), (88, y))
            dot(kx, y, 9)
    elif name == 'chart':                    # results
        for x0, y0 in ((14, 52), (41, 32), (68, 14)):
            d.rounded_rectangle([x0 * u, y0 * u, (x0 + 18) * u, 86 * u],
                                radius=4 * u, fill='white')
    elif name == 'chain':
        ring(35, 50, 21)
        ring(65, 50, 21)
    elif name == 'folder':
        d.polygon(P((10, 26), (38, 26), (46, 36), (90, 36),
                    (90, 78), (10, 78)), fill='white')
    elif name == 'save':
        d.polygon(P((16, 16), (70, 16), (84, 30), (84, 84), (16, 84)),
                  outline='white', width=int(lw))
        d.rectangle([32 * u, 18 * u, 62 * u, 38 * u],
                    outline='white', width=int(lw * 0.8))
        d.rectangle([30 * u, 54 * u, 70 * u, 82 * u],
                    outline='white', width=int(lw * 0.8))
    elif name == 'cube':
        hexpts = ((50, 8), (86, 29), (86, 71), (50, 92), (14, 71), (14, 29))
        d.polygon(P(*hexpts), outline='white', width=int(lw))
        for x, y in ((14, 29), (86, 29), (50, 92)):
            line((50, 50), (x, y), w=lw * 0.9)
    elif name == 'image':
        d.rounded_rectangle([10 * u, 18 * u, 90 * u, 82 * u],
                            radius=8 * u, outline='white', width=int(lw))
        dot(33, 38, 7)
        line((18, 74), (42, 50), (58, 64), (73, 44), (87, 60), w=lw * 0.9)
    elif name == 'table':
        d.rounded_rectangle([12 * u, 20 * u, 88 * u, 80 * u],
                            radius=6 * u, outline='white', width=int(lw))
        line((12, 42), (88, 42), w=lw * 0.8)
        line((42, 42), (42, 80), w=lw * 0.8)
        line((66, 42), (66, 80), w=lw * 0.8)
    elif name == 'film':
        d.rounded_rectangle([14 * u, 22 * u, 86 * u, 78 * u],
                            radius=6 * u, outline='white', width=int(lw))
        line((30, 22), (30, 78), w=lw * 0.8)
        line((70, 22), (70, 78), w=lw * 0.8)
        for y in (30, 46, 62):
            d.rectangle([19 * u, y * u, 25 * u, (y + 8) * u], fill='white')
            d.rectangle([75 * u, y * u, 81 * u, (y + 8) * u], fill='white')
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
        d.polygon(P((50, 12), (92, 84), (8, 84)),
                  outline='white', width=int(lw))
        line((50, 36), (50, 60), w=lw * 1.05)
        dot(50, 72, 4.5)
    elif name == 'info':
        ring(50, 50, 36)
        dot(50, 32, 5)
        line((50, 45), (50, 70), w=lw * 1.05)
    elif name == 'eye':
        d.arc([14 * u, 22 * u, 86 * u, 78 * u], 20, 160,
              fill='white', width=int(lw))
        d.arc([14 * u, 22 * u, 86 * u, 78 * u], 200, 340,
              fill='white', width=int(lw))
        dot(50, 50, 11)
    else:
        raise KeyError(name)


def _glyph(name, size):
    """Render glyph `name` (white on transparent) at 4x resolution."""
    S = size * 8
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if name == 'moon':
        full = Image.new('L', (S, S), 0)
        ImageDraw.Draw(full).ellipse(
            [0.18 * S, 0.16 * S, 0.82 * S, 0.80 * S], fill=255)
        bite = Image.new('L', (S, S), 0)
        ImageDraw.Draw(bite).ellipse(
            [0.34 * S, 0.04 * S, 0.94 * S, 0.64 * S], fill=255)
        alpha = ImageChops.subtract(full, bite)
        img.paste((255, 255, 255, 255), (0, 0), alpha)
    else:
        _shape(name, d, S, lw=S * 0.075)
    return img.resize((size * 4, size * 4), Image.LANCZOS)


def _tint(img, color):
    out = Image.new('RGBA', img.size, (0, 0, 0, 0))
    solid = Image.new('RGBA', img.size, color)
    out.paste(solid, (0, 0), img)
    return out


def icon(name, size=16, color=None):
    """A cached CTkImage of the named glyph. Default coloring follows
    the text color of each appearance mode; pass `color` to force one
    (e.g. 'white' for icons sitting on accent buttons)."""
    key = (name, size, color)
    if key not in _ICON_CACHE:
        base = _glyph(name, size)
        if color:
            li = di = _tint(base, color)
        else:
            li, di = _tint(base, LIGHT['text']), _tint(base, DARK['text'])
        _ICON_CACHE[key] = ctk.CTkImage(light_image=li, dark_image=di,
                                        size=(size, size))
    return _ICON_CACHE[key]


# ── ttk styling (Treeview / Panedwindow have no CTk equivalent) ──────────
def apply_ttk_style(root=None):
    pal = DARK if ctk.get_appearance_mode() == 'Dark' else LIGHT
    st = ttk.Style(root)
    try:
        st.theme_use('clam')
    except Exception:
        pass
    st.configure('TFrame', background=pal['card'])
    st.configure('Treeview', background=pal['entry'],
                 fieldbackground=pal['entry'], foreground=pal['text'],
                 borderwidth=0, relief='flat', rowheight=26,
                 font=(FONT, 11))
    st.configure('Treeview.Heading', background=pal['card2'],
                 foreground=pal['muted'], borderwidth=0, relief='flat',
                 font=(FONT, 11, 'bold'), padding=(6, 4))
    st.map('Treeview',
           background=[('selected', pal['accent'])],
           foreground=[('selected', '#ffffff')])
    st.map('Treeview.Heading', background=[('active', pal['card2'])])
    st.configure('TPanedwindow', background=pal['bg'])
    st.configure('Sash', sashthickness=8, gripcount=0)


# ── matplotlib figure theming ────────────────────────────────────────────
def style_figure(fig):
    """Recolor a Figure's chrome in place to match the current mode
    (only display copies pass through here; exports build their own
    figures and keep matplotlib's default light style)."""
    dark = ctk.get_appearance_mode() == 'Dark'
    pal = DARK if dark else LIGHT
    face = pal['card']
    axface = pal['entry'] if dark else pal['card']
    fig.patch.set_facecolor(face)
    for txt in fig.texts:                                  # suptitles
        txt.set_color(pal['text'])
    for ax in fig.axes:
        try:
            ax.set_facecolor(axface)
        except Exception:
            pass
        for sp in getattr(ax, 'spines', {}).values():
            sp.set_color(pal['border'])
        ax.tick_params(colors=pal['muted'], labelcolor=pal['muted'],
                       which='both')
        for axis_name in ('xaxis', 'yaxis', 'zaxis'):
            axis = getattr(ax, axis_name, None)
            if axis is None:
                continue
            axis.label.set_color(pal['text'])
            if hasattr(axis, 'pane'):                      # 3D axes
                axis.pane.set_facecolor(face)
                axis.pane.set_edgecolor(pal['border'])
        ax.title.set_color(pal['text'])
        leg = ax.get_legend()
        if leg is not None:
            leg.get_frame().set_facecolor(axface)
            leg.get_frame().set_edgecolor(pal['border'])
            for t in leg.get_texts():
                t.set_color(pal['text'])
    return fig


# ── live re-theming of embedded figures on mode toggle ───────────────────
_embedded = weakref.WeakSet()


def register_embedded(widget):
    """EmbeddedFigure instances register here so a theme toggle can
    restyle the figures they currently display."""
    _embedded.add(widget)


def refresh_embedded():
    for w in list(_embedded):
        try:
            w.retheme()
        except Exception:
            pass
