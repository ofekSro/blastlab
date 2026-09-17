"""M6 parity sweep: light mode, three window sizes, four tabs.

This suite exists because of what it found. The Setup form asks for two
columns of 310 px, the Setup tab shares its width with the preview, and
the scroll column has no horizontal scrollbar - so below roughly a
1290 px window the right-hand cards were simply CUT OFF. Measured 188 px
unreachable at 1100x720, which is the window's own minimum size, and
8 px even at the default 1280x840. The three dimension forms share a
QStackedWidget whose minimum is the largest of its pages, so collapsing
only the visible one changed nothing.

The checks are therefore about content being REACHABLE, not about
pixels looking nice: nothing horizontally clipped inside a scroll area,
nothing past the window outside one, both appearance modes, and no
value lost when the columns collapse.

Headless. Run:  cd blastlab/tests && python test_ui_parity.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_pa_'),
                                   'settings.json'))

import numpy as np                                            # noqa: E402

from blastlab.ui.testing import ensure_qapp, pump             # noqa: E402

FAIL = []
RAN = []

#: the default, the window's declared minimum, and below it
SIZES = ((1280, 840), (1100, 720), (900, 600))
TABS = ('setup', 'run', 'results', 'chain')


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def clipped(root):
    """Content that is cut off, not merely scrollable.

    Vertical overflow inside a scroll area is what scrolling is for.
    Horizontal overflow there is a defect, because ScrollColumn turns
    that scrollbar off. Qt's own scrollbar furniture sits beside the
    viewport by design and is skipped."""
    from PySide6.QtWidgets import QScrollArea, QScrollBar, QWidget
    out = []
    for c in root.findChildren(QWidget):
        if not c.isVisible() or c.width() <= 0:
            continue
        if c.objectName().startswith('qt_') or isinstance(c, QScrollBar):
            continue
        if isinstance(c.parentWidget(), QScrollBar):
            continue
        sa, p = None, c.parentWidget()
        while p is not None:
            if isinstance(p, QScrollArea):
                sa = p
                break
            p = p.parentWidget()
        if sa is not None:
            tl = c.mapTo(sa.viewport(), c.rect().topLeft())
            over = tl.x() + c.width() - sa.viewport().width()
            if over > 1:
                out.append((type(c).__name__, 'H-clipped', over))
        else:
            tl = c.mapTo(root, c.rect().topLeft())
            for over, kind in ((tl.x() + c.width() - root.width(), 'H'),
                               (tl.y() + c.height() - root.height(), 'V')):
                if over > 1:
                    out.append((type(c).__name__,
                                f'{kind}-past-window', over))
    return out


def main():
    ensure_qapp()
    from PySide6.QtWidgets import QApplication
    from test_gui_results_fields import fake_2d, fake_3d
    from blastlab.ui import theme
    from blastlab.ui.app import MainWindow
    from blastlab.ui.case_form import CaseForm
    from blastlab.ui.fieldform import COL_MIN
    from blastlab.ui import results_gauges as RG

    crashes = []
    sys.excepthook = lambda *a: crashes.append(a)

    win = MainWindow()
    win.show()
    pump(150)
    res = fake_2d()
    nx, ny = res.meta['solid'].shape
    res.meta['frames'] = dict(
        times=[0.0, 1e-4, 2e-4],
        pressures=[np.full((nx, ny), 101325.0 + p)
                   for p in (4e5, 2e5, 5e4)])
    win.on_result(1, 2, 'Run 1 - 2D', res)
    win.on_result(2, 3, 'Run 2 - 3D', fake_3d())
    pump(150)

    print('\nP1: nothing is cut off, at any size, in either mode')
    for mode in ('dark', 'light'):
        theme.apply(QApplication.instance(), mode)
        pump(150)
        for size in SIZES:
            win.resize(*size)
            pump(100)
            worst = []
            for tab in TABS:
                win._show(tab)
                pump(150)
                bad = clipped(win)
                if bad:
                    bad.sort(key=lambda t: -t[2])
                    worst.append((tab, bad[0]))
            check(f'{mode} {size[0]}x{size[1]}', not worst, str(worst[:2]))

    print('\nP2: light mode really changes the palette')
    theme.apply(QApplication.instance(), 'dark')
    pump(120)
    dark = dict(theme.pal())
    theme.apply(QApplication.instance(), 'light')
    pump(120)
    light = dict(theme.pal())
    check('the background inverts',
          dark['bg'] != light['bg']
          and int(light['bg'][1:3], 16) > int(dark['bg'][1:3], 16),
          f"{dark['bg']} -> {light['bg']}")
    check('and so does the text', dark['text'] != light['text'],
          f"{dark['text']} -> {light['text']}")
    check('every palette colour is a full #rrggbb - LabelItem feeds it '
          'straight to mkColor, which rejects a bare hex',
          all(isinstance(v, str) and v.startswith('#') and len(v) == 7
              for v in light.values() if isinstance(v, str)
              and not v.startswith('rgb')),
          str([k for k, v in light.items()
               if isinstance(v, str) and not v.startswith('#')][:4]))
    check('switching modes raises nothing', not crashes, str(crashes[:1]))

    print('\nP3: the Setup form collapses to one column instead of '
          'clipping')
    win._show('setup')
    win.resize(1600, 900)
    pump(250)
    forms = [f for f in win.setup.findChildren(CaseForm)]
    vis = [f for f in forms if f.isVisible()]
    check('three dimension forms, one on screen',
          len(forms) == 3 and len(vis) == 1, f'{len(forms)}/{len(vis)}')
    check('wide: two columns', not vis[0].single_column(),
          f'avail {vis[0]._avail_width()}')
    check('and the form fills the viewport, not its minimum',
          vis[0].width() == vis[0]._avail_width(),
          f'{vis[0].width()} vs {vis[0]._avail_width()}')
    win.resize(1100, 720)
    pump(200)
    check('narrow: one column', vis[0].single_column(),
          f'avail {vis[0]._avail_width()}')
    check('ALL three forms collapsed, not just the visible one - the '
          'stack takes the largest page as its minimum',
          all(f.single_column() for f in forms),
          str([f.single_column() for f in forms]))
    check('the second holder is out of the layout, so it stops '
          'contributing to the minimum',
          vis[0]._holders[1].isHidden())
    check('and the form now fits the viewport',
          vis[0].width() <= vis[0]._avail_width(),
          f'{vis[0].width()} vs {vis[0]._avail_width()}')
    check('the threshold is two columns plus the gap',
          COL_MIN == 310 and 2 * COL_MIN + 8 == 628, str(COL_MIN))

    print('\nP4: collapsing must not lose anything')
    win.resize(1600, 900)
    pump(200)
    form = vis[0]
    form.v['Lx'].set('7.25')
    form.v['cell'].set('0.033')
    before_case = form.get_case()
    before_cards = sorted(form.cards)
    hidden_before = {t: form.cards[t].isHidden() for t in form.cards}
    win.resize(900, 600)
    pump(250)
    check('every card survived the move',
          sorted(form.cards) == before_cards,
          str(set(before_cards) ^ set(form.cards)))
    check('the typed values survived',
          form.v['Lx'].get() == '7.25'
          and form.v['cell'].get() == '0.033',
          f"{form.v['Lx'].get()} {form.v['cell'].get()}")
    check('and so does the case it builds',
          abs(form.get_case().Lx - before_case.Lx) < 1e-12
          and abs(form.get_case().cell_size_m
                  - before_case.cell_size_m) < 1e-12)
    check('a card the solver mode had hidden is still hidden',
          {t: form.cards[t].isHidden() for t in form.cards}
          == hidden_before,
          str([t for t in form.cards
               if form.cards[t].isHidden() != hidden_before[t]]))
    # the registry that maps a field name to its live widget and row is
    # what re-parenting could break. Exercise it AFTER the move rather
    # than before: the panel's debounced validation legitimately clears
    # stale marks whenever the form revalidates.
    form.mark_fields(['cell'])
    check('a field can still be marked bad after the move',
          form.bad == {'cell'}
          and form.widgets['cell'].property('bad') == 'true',
          f"{form.bad} {form.widgets['cell'].property('bad')!r}")
    form.mark_fields([])
    # the property is the string the QSS rule [bad="true"] matches, so
    # clearing it means 'false', not a falsy value
    check('and unmarked again',
          not form.bad
          and form.widgets['cell'].property('bad') == 'false',
          f"{form.bad} {form.widgets['cell'].property('bad')!r}")
    check('row visibility still answers after the move',
          form.row_visible('Lx') and form.row_visible('cell'))
    check('and set_label still reaches the right caption',
          (form.set_label('Lx', 'Lx [m]') or True)
          and form.labels['Lx'].text() == 'Lx [m]')
    win.resize(1600, 900)
    pump(250)
    check('going back to two columns restores them',
          not form.single_column()
          and not form._holders[1].isHidden())
    check('still with the values', form.v['Lx'].get() == '7.25')

    print('\nP5: tooltips on everything that is greyed or abbreviated')
    win._show('results')
    pump(150)
    heads = win.results.gauges.table
    check('all eight summary headers explain themselves',
          all(heads.horizontalHeaderItem(i).toolTip()
              for i in range(heads.columnCount()))
          and heads.columnCount() == len(RG.HEADERS))
    btns = win.results._export_btns
    check('all eight export buttons have a tooltip',
          len(btns) == 8 and all(b.toolTip() for b in btns.values()),
          str([k for k, b in btns.items() if not b.toolTip()]))
    win.results.sel.setCurrentIndex(0)
    pump(100)
    off = [k for k in btns if not win.results.export_enabled(k)]
    check('and a disabled one says WHY, not just what',
          off and all(btns[k].toolTip() for k in off), str(off))

    print('\nP6: the four accelerators are bound')
    from PySide6.QtGui import QShortcut
    keys = {sc.key().toString() for sc in win.findChildren(QShortcut)}
    for want in ('Ctrl+O', 'Ctrl+S', 'F5', 'Esc'):
        check(f'{want} is bound', want in keys, str(sorted(keys)))

    check('nothing raised during the whole sweep', not crashes,
          str(crashes[:1]))
    win.close()
    pump(100)

    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI PARITY: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
