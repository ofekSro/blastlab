"""GUI-1 gate: the design tokens and bundled fonts of the Qt front-end
(docs/gui-redesign-plan.md §2, batch 2026-09-28-gui-foundation).

Checks, in order:
 T1  font fallback - with the fonts dir pointed at an empty folder,
     `theme.apply()` still succeeds and `font('display')` falls back to
     Segoe UI (plan §2.3: never crash over a font);
 T2  the bundled families register (Space Grotesk / IBM Plex Sans /
     IBM Plex Mono) and `font('display'|'body'|'mono')` put them first;
 T3  the variable Space Grotesk really renders 600/700 heavier than 400
     (owner 2026-09-28: a variable TTF is acceptable only if it does);
 T4  DARK and LIGHT carry the same keys - every pre-redesign key plus
     the plan §2.1 additions - and every value is a full '#rrggbb';
 T5  the WCAG contrast gate: every text role of the plan §2.2 list
     reaches 4.5:1 on its backgrounds, in both modes, with the whole
     ratio table printed for the task report (GUI-10 added `num_dim` on
     bg / panel / card, F8);
 T6  (GUI-10, F8) the selected model-tree row: its fill is `chain_tint`
     and the number, title, caption and marks reach 4.5:1 on it.

Plain script, offscreen, no pytest: `python test_ui_theme.py`.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.ui import theme                              # noqa: E402

# T1 needs the fonts dir empty BEFORE the first `apply()` (fonts cannot
# be unregistered per-directory once loaded).
_REAL_FONT_DIR = theme.FONT_DIR
theme.FONT_DIR = tempfile.mkdtemp(prefix='blastlab_nofonts_')

from blastlab.ui.testing import ensure_qapp                # noqa: E402

app = ensure_qapp()

from PySide6.QtCore import Qt                              # noqa: E402
from PySide6.QtGui import (QColor, QFont, QFontDatabase,   # noqa: E402
                           QFontInfo, QImage, QPainter)

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


# ── WCAG relative luminance / contrast (plan §2.2) ──────────────────────
def _lum(hexs):
    r, g, b = (int(hexs[i:i + 2], 16) / 255.0 for i in (1, 3, 5))

    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(fg, bg):
    a, b = _lum(fg), _lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


#: (text role, background role) pairs of the batch-plan gate, all >= 4.5
GATE_PAIRS = ([(t, b) for t in ('text', 'text2', 'muted', 'faint')
               for b in ('bg', 'panel', 'card', 'tile')]
              + [('accent_text', b) for b in ('bg', 'card')]
              + [('accent_soft', b) for b in ('bg', 'card')]
              + [('on_accent', 'accent'), ('stop_text', 'stop_bg'),
                 ('gauge', 'gauge_bg'), ('gauge', 'bg'), ('ok', 'ok_bg'),
                 ('warn', 'bg'), ('danger', 'bg')]
              # GUI-10 (F8, D180): the tree's node numbers and the stage
              # card's number are text on these three
              + [('num_dim', b) for b in ('bg', 'panel', 'card')])

#: GUI-10 (F8, D180): the roles a SELECTED model-tree row draws on its
#: fill (number, title, caption, the ✓ / ! / ✗ marks), all >= 4.5
SELECTED_ROW_ROLES = ('accent_text', 'text', 'faint', 'ok', 'warn',
                      'danger')
#: num_dim before GUI-10, for the printed old -> new line
NUM_DIM_BEFORE = {'dark': '#6f6a63', 'light': '#9b958c'}

#: every key the palette must carry: the pre-redesign set plus §2.1
OLD_KEYS = {'bg', 'card', 'card2', 'border', 'entry', 'accent',
            'accent_hover', 'text', 'muted', 'view', 'danger',
            'danger_hover', 'error', 'warn', 'ok', 'seg'}
NEW_KEYS = {'panel', 'tile', 'hover', 'border2', 'entry_border', 'text2',
            'faint', 'num_dim', 'on_accent', 'accent_text', 'accent_soft',
            'accent_bg', 'accent_border', 'gauge', 'gauge_bg', 'ok_bg',
            'ok_border', 'stop_bg', 'stop_border', 'stop_text',
            'title_bar'}


def _ink(family, weight, text='BLASTLAB'):
    """Dark-pixel count of `text` rendered at `weight` - the ink test
    that proves a variable font's weights actually differ in Qt."""
    f = QFont()
    f.setFamilies([family])
    f.setPointSize(40)
    f.setWeight(QFont.Weight(weight))
    img = QImage(420, 90, QImage.Format_ARGB32)
    img.fill(Qt.white)
    p = QPainter(img)
    p.setFont(f)
    p.setPen(QColor('black'))
    p.drawText(img.rect(), Qt.AlignCenter, text)
    p.end()
    return sum(1 for y in range(img.height()) for x in range(img.width())
               if QColor(img.pixel(x, y)).lightness() < 128)


def t1_fallback():
    print('\nT1: apply() with no font files never crashes (plan §2.3)')
    theme.apply(app, 'dark')                    # FONT_DIR is empty here
    f = theme.font('display')
    fams = f.families()
    check('font("display") lists the Segoe UI fallback',
          'Segoe UI' in fams, str(fams))
    if 'Space Grotesk' not in QFontDatabase.families():
        real = QFontInfo(f).family()
        check('display resolves to Segoe UI when the TTF is missing',
              real == 'Segoe UI', real)
    else:                                       # system-installed copy
        print('  [note] Space Grotesk found system-wide; fallback '
              'resolution not observable on this machine')


def t2_families():
    print('\nT2: the bundled families register')
    theme.FONT_DIR = _REAL_FONT_DIR
    theme._fonts_loaded = False
    theme.apply(app, 'dark')
    fams = QFontDatabase.families()
    for want in ('Space Grotesk', 'IBM Plex Sans', 'IBM Plex Mono'):
        check(f'{want} registered', want in fams)
    for kind, fam in (('display', 'Space Grotesk'),
                      ('body', 'IBM Plex Sans'),
                      ('mono', 'IBM Plex Mono')):
        first = theme.font(kind).families()[0]
        check(f'font("{kind}") -> {fam} first', first == fam, first)


def t3_weights():
    print('\nT3: Space Grotesk 600/700 render heavier than 400')
    n400 = _ink('Space Grotesk', 400)
    n600 = _ink('Space Grotesk', 600)
    n700 = _ink('Space Grotesk', 700)
    print(f'  ink 400/600/700: {n400}/{n600}/{n700}')
    check('600 heavier than 400', n600 > n400 * 1.05)
    check('700 heavier than 600', n700 > n600 * 1.02)


def t4_keys():
    print('\nT4: palette keys and #rrggbb form')
    want = OLD_KEYS | NEW_KEYS
    for name, pal in (('DARK', theme.DARK), ('LIGHT', theme.LIGHT)):
        missing = want - set(pal)
        check(f'{name} carries every key', not missing, str(missing))
        bad = [f'{k}={v}' for k, v in pal.items()
               if not (isinstance(v, str) and len(v) == 7
                       and v[0] == '#'
                       and all(c in '0123456789abcdefABCDEF'
                               for c in v[1:]))]
        check(f'{name} values are 7-char #rrggbb', not bad, str(bad))
    check('DARK and LIGHT have the same keys',
          set(theme.DARK) == set(theme.LIGHT),
          str(set(theme.DARK) ^ set(theme.LIGHT)))
    check('tile == card2 (both keys kept)',
          theme.DARK['tile'] == theme.DARK['card2']
          and theme.LIGHT['tile'] == theme.LIGHT['card2'])


def t5_contrast():
    print('\nT5: WCAG contrast gate (all listed pairs >= 4.5)')
    for name, pal in (('dark', theme.DARK), ('light', theme.LIGHT)):
        print(f'  -- {name} --')
        worst = None
        for fg, bg in GATE_PAIRS:
            r = contrast(pal[fg], pal[bg])
            print(f'    {fg:12s} on {bg:9s} {pal[fg]} / {pal[bg]}  '
                  f'{r:6.2f}')
            if worst is None or r < worst[0]:
                worst = (r, fg, bg)
        check(f'{name}: every pair >= 4.5', worst[0] >= 4.5,
              f'worst {worst[1]} on {worst[2]} = {worst[0]:.2f}')
        # danger buttons (GUI-1 sweep): text colour per qss()
        wd = contrast('#ffffff', pal['danger'])
        oa = contrast(pal['on_accent'], pal['danger'])
        print(f'    white on danger {wd:6.2f} · on_accent on danger '
              f'{oa:6.2f}')
        need = oa if name == 'dark' else wd
        check(f'{name}: danger-button text >= 4.5', need >= 4.5,
              f'{need:.2f}')
        old = NUM_DIM_BEFORE[name]
        print(f'    num_dim {old} -> {pal["num_dim"]}: '
              + ', '.join(f'{b} {contrast(old, pal[b]):.2f} -> '
                          f'{contrast(pal["num_dim"], pal[b]):.2f}'
                          for b in ('bg', 'panel', 'card')))


def t6_selected_row():
    """GUI-10 (F8, D180): the selected model-tree row's fill is the
    QSS rule's own (`treerow[selected="true"]`), and every role drawn on
    it reaches 4.5:1. Hover rows are printed for the report, not gated
    (D180: the global `hover` key is unchanged)."""
    import re
    print('\nT6: the selected tree row (every role >= 4.5)')
    for name, pal in (('dark', theme.DARK), ('light', theme.LIGHT)):
        m = re.search(r'QFrame#treerow\[selected="true"\]\s*\{\s*'
                      r'background:\s*(#[0-9a-fA-F]{6})', theme.qss(name))
        fill = m.group(1) if m else None
        check(f'{name}: the selected-row fill is chain_tint '
              f'({theme.chain_tint(name)})',
              fill == theme.chain_tint(name), str(fill))
        if fill is None:
            continue
        worst = None
        for role in SELECTED_ROW_ROLES:
            r = contrast(pal[role], fill)
            print(f'    {role:12s} on {fill}  {r:6.2f}')
            if worst is None or r < worst[0]:
                worst = (r, role)
        check(f'{name}: every role on the selected row >= 4.5',
              worst[0] >= 4.5, f'worst {worst[1]} = {worst[0]:.2f}')
        print(f'    (hover, not gated: '
              + ', '.join(f'{role} {contrast(pal[role], pal["hover"]):.2f}'
                          for role in ('num_dim', 'text', 'faint', 'ok',
                                       'warn', 'danger')) + ')')


def main():
    t1_fallback()
    t2_families()
    t3_weights()
    t4_keys()
    t5_contrast()
    t6_selected_row()
    print(f'\nTHEME: {"PASS" if not FAIL else "FAIL " + str(FAIL)}')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
