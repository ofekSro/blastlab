"""GUI-16 (C6-C9, C11): what the Qt screens SHOW at the two window sizes, on
the real platform. Batch docs/batches/2026-10-12-gui-final-2.md, Part C.

Real platform (`QT_QPA_PLATFORM` unset), the real MainWindow on throwaway
settings (CLAUDE.md sec. 8.2 / 8.7), 1100 x 720 and 1600 x 1000, dark and
light. Per check it prints the text the screen shows (a label's own text, or
`fontMetrics().elidedText` against the real width for a cell or a box that
elides) and PASS / FAIL.

  C6   Setup: the Gauges caption keeps `G2 dropped` and `trigger G3`; the
       trigger dropdown's current text is whole; Where shows `(dropped)`.
  C7   Chain: after selecting warned card 3 its first Checks row lies in the
       viewport; the card meta wraps, never elides.
  C8   Run: at a forced elide the card header keeps its number and unit
       whole (only `· Wall n` elides).
  C9   Results: a dropped trigger selects the first row; the plot caption
       is whole; every Summary header's text lies within its section; the
       1D export-title hint is a visible line.

Run:  cd blastlab/tests && python _e2e_ui_final_fit.py [--only C6] [--shots DIR]
Exit 0 when every check passes. No solve, no WSL, no viewer child.
"""
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS', os.path.join(
    tempfile.mkdtemp(prefix='blastlab_ui_finalfit_'), 'settings.json'))
os.environ.pop('QT_QPA_PLATFORM', None)        # the real platform

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

SIZES = ((1100, 720), (1600, 1000))
MODES = ('dark', 'light')
FAIL = []
RAN = []


def check(name, ok, detail=''):
    RAN.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def _arg(flag):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    return None


def elided(widget, text, width, mode=None):
    """The text a widget with `widget`'s font shows in `width` px."""
    from PySide6.QtCore import Qt
    return widget.fontMetrics().elidedText(
        text, mode if mode is not None else Qt.ElideRight, int(width))


# ── C6: Setup ────────────────────────────────────────────────────────────
def drop_case():
    """G1 kept, G2 inside Wall 1 (dropped), G3 kept and the trigger."""
    from blastlab.core.case import Case2D
    return Case2D(geometry='planar', Lx=2.4, Ly=1.6, cell_size_m=0.04,
                  charge=20.0, center=(0.6, 0.0), solver='native',
                  obstacles=[(1.2, 1.6, 0.0, 0.6)],
                  bcs=dict(x_lo='reflect', x_hi='terminate', y_lo='reflect',
                           y_hi='terminate'),
                  gauges=[(0.3, 0.8), (1.4, 0.3), (0.9, 1.0)],
                  trigger_gauge=3)


def c6_setup(win, tag, pump):
    from PySide6.QtCore import Qt
    from blastlab.ui import setup_nodes
    print(f'\nC6 {tag}: Setup captions, dropdown, Where')
    win.set_solver('native')
    win._show('setup')
    win.setup.set_case(drop_case())
    win._schedule_validate()
    pump(500)
    sp = win.setup
    cap = sp.tree.rows['gauges'].caption
    shown = cap.text()
    check(f'C6 (i) {tag}: the Gauges caption shows `G2 dropped` and '
          f'`trigger G3`', 'G2 dropped' in shown and 'trigger G3' in shown,
          f'{shown!r} in {cap.width()} px, full '
          f'{sp.tree.summary("gauges")!r}')
    node = setup_nodes.node_of_field(2, 'trigger_gauge')
    sp.select_node(node)
    pump(300)
    combo = sp.form.trigger_combo
    text = combo.currentText()
    avail = combo.width() - 22 - 14        # drop-down, QSS padding + border
    whole = combo.fontMetrics().horizontalAdvance(text)
    check(f'C6 (ii) {tag}: the trigger dropdown\'s current text is whole',
          combo.isVisibleTo(sp.form) and whole <= avail,
          f'{text!r} {whole} px in {avail} px')
    sp.set_dock_tab('Gauges')
    pump(300)
    t = sp.gauge_table
    rows = sp.gauge_rows()
    where = rows[1][-1]
    col = t.columnCount() - 1
    room = t.columnWidth(col) - 12
    seen = elided(t, where, room, Qt.ElideMiddle)
    check(f'C6 (iii) {tag}: Where shows `(dropped)` for G2',
          seen.endswith('(dropped)'),
          f'{seen!r} (full {where!r}) in {room} px')


# ── C7: Chain ────────────────────────────────────────────────────────────
def c7_chain(win, tag, pump):
    from PySide6.QtCore import QRect, Qt
    print(f'\nC7 {tag}: Chain, Checks in view, card meta')
    win.set_solver('native')
    win._show('chain')
    ch = win.chain
    ch.set_route('123')
    pump(300)
    ch.forms[3].v['Lz'].set('1.0')          # F45: the 2D burst is above it
    pump(600)
    ed = ch.editors[3]
    ch.focus_stage(1)
    ed.select_node('stage')                 # the node a stage switch keeps
    ch.focus_stage(3)
    pump(300)
    vp = ed.scroll_viewport()
    first = ed.check_row_widgets()[0]
    top = first.mapTo(vp, first.rect().topLeft()).y()
    check(f'C7 (v) {tag}: selecting warned card 3, its first Checks row lies '
          f'inside the viewport',
          ed.has_alerts() and 0 <= top and top + first.height() <= vp.height(),
          f'row y {top}..{top + first.height()} in a {vp.height()} px '
          f'viewport')
    for d in (1, 2, 3):
        key = ch.cards[d].key
        full = key.full_text()
        need = key.fontMetrics().boundingRect(
            QRect(0, 0, max(key.width(), 1), 10000),
            int(Qt.TextWordWrap | Qt.AlignLeft), full).height()
        check(f'C7 (vi) {tag}: card {d} meta is not elided (wraps)',
              need <= key.height() and key.height() <= 2 * key.fontMetrics()
              .lineSpacing() + 2,
              f'{full!r} needs {need} px of {key.height()} px, '
              f'{key.width()} px wide')


# ── C8: Run ──────────────────────────────────────────────────────────────
def c8_run(win, tag, pump):
    from blastlab.core.case import Case2D
    from blastlab.ui import scaled_distance as sd
    print(f'\nC8 {tag}: Run card header')
    win.set_solver('native')
    win._show('run')
    rp = win.run_panel
    # G1 stands 10 cm in front of Wall 1, so the header has a `· Wall 1`
    case = Case2D(geometry='axisymmetric', Lx=2.4, Ly=1.6, cell_size_m=0.04,
                  charge=20.0, center=(0.0, 0.8), solver='native',
                  obstacles=[(1.2, 1.6, 0.0, 0.6)], gauges=[(1.1, 0.3)])
    rp.set_gauge_case(case)
    for _ in range(10):                     # until the column is on screen
        pump(200)
        if rp.gauge_col.card.isVisible():
            break
    card = rp.gauge_col.card
    lead = card.lead.text()
    adv = card.lead.fontMetrics().horizontalAdvance(lead)
    check(f'C8 (iii) {tag}: the card header\'s number and unit are whole',
          lead.startswith('Z ') and lead.endswith(sd.unit())
          and card.lead.width() >= adv,
          f'{lead!r} {card.lead.width()} px of {adv} px; rest '
          f'{card.meta.text()!r}')
    card.meta.setFixedWidth(12)             # a forced elide
    pump(400)
    card.meta._render()     # a label not yet shown has seen no resize event
    check(f'C8 (iii) {tag}: at a forced elide only `· Wall n` is cut; the '
          f'lead keeps its whole text',
          card.lead.text() == lead and card.lead.width() >= adv
          and card.meta.elided(),
          f'{card.lead.text()!r} {card.lead.width()} >= {adv}; '
          f'{card.meta.text()!r} of {card.meta.full_text()!r} '
          f'({card.meta.width()} px)')
    card.meta.setMinimumWidth(0)
    card.meta.setMaximumWidth(16777215)


# ── C9: Results ──────────────────────────────────────────────────────────
_RESULTS = {}


def results_fixture():
    """A native 2D-like Result with three entered gauges, G2 inside Wall 1
    (dropped) and the trigger on it, and one 1D Result for the title hint."""
    import numpy as np
    from blastlab.core.constants import P_AIR
    from blastlab.solvers.hooks import Result
    from test_gui_results_fields import fake_2d
    res = fake_2d()
    t = np.linspace(0.0, 8e-3, 400)
    traces = []
    for t0, pk in ((4.7e-3, 184e3), (4.15e-3, 231e3)):
        s = np.clip((t - t0) / 1.3e-3, 0.0, None)
        traces.append(np.where(t >= t0, P_AIR + pk * (1 - s) * np.exp(-2 * s),
                               P_AIR))
    res.gauges = dict(times=t, points=[(2.975, 0.525), (2.975, 1.525)],
                      pressures=traces)
    res.meta.update(geometry='axisymmetric', charge=1.0,
                    charge_center=(0.0, 2.0), dx=0.05,
                    gauges=[(2.95, 0.50), (1.2, 0.6), (2.95, 1.50)],
                    obstacles=[(1.0, 1.4, 0.0, 1.2)], Lx=4.0, Ly=4.0,
                    from_profile=False, trigger_gauge=2)
    return Result(res.snapshots, res.gauges, res.meta, res.stop_reason,
                  False)


def c9_results(win, tag, pump):
    from PySide6.QtCore import Qt
    from blastlab.ui import results_gauges as RG
    print(f'\nC9 {tag}: Results gauges page, export hint')
    rp = win.results
    if 'two' not in _RESULTS:
        _RESULTS['two'] = results_fixture()
        win._show('results')
        rp.add_result('fit - 2D', 2, _RESULTS['two'])
        pump(500)
    win._show('results')
    rp.sel.setCurrentIndex(0)                # the 2D fixture
    rp.show_view('Gauges')
    pump(500)
    g = rp.gauges
    check(f'C9 (i) {tag}: trigger G2 was dropped, the default row is row 1 '
          f'(the first listed)',
          g.selected() == g.order()[0] and g.label(g.selected()) == 'G3'
          if g.order() else False,
          f'selected {g.selected()}, order {g.order()}, labels '
          f'{[c[0] for c in g.cells()]}')
    cap = g.head_caption
    check(f'C9 (ii) {tag}: the plot caption shows whole - its full text, '
          f'or its short form where that does not fit; never cut',
          cap.isVisible() and cap.text() in (RG.PLOT_CAPTION,
                                             RG.PLOT_CAPTION_SHORT)
          and cap.fontMetrics().horizontalAdvance(cap.text()) <= cap.width(),
          f'{cap.text()!r} in {cap.width()} px')
    hdr = g.table.horizontalHeader()
    bad = []
    for c in g.visible_columns():
        text = g.table.horizontalHeaderItem(c).text()
        lines = text.split('\n')
        need_w = max(hdr.fontMetrics().horizontalAdvance(ln) for ln in lines)
        need_h = len(lines) * hdr.fontMetrics().lineSpacing()
        if need_w + 8 > hdr.sectionSize(c) or need_h > hdr.height():
            bad.append((text, need_w, hdr.sectionSize(c), need_h,
                        hdr.height()))
    check(f'C9 (iii) {tag}: every Summary header\'s text is within its '
          f'section (width and height)', not bad,
          f'{bad}; table {g.table.viewport().width()} px, columns '
          f'{hdr.length()} px (it scrolls sideways when narrower), '
          f'wrapped {g.headers_wrapped()}')
    # the export-title hint is a line, not only a tooltip (a 1D result)
    if 'one' not in _RESULTS:
        import numpy as np
        from blastlab.core.constants import P_AIR
        from blastlab.solvers.hooks import Result
        r = np.linspace(0.01, 2.0, 60)
        snap = dict(r=r, p=P_AIR + 200e3 * np.exp(-r),
                    rho=np.full_like(r, 1.2), u=np.zeros_like(r))
        _RESULTS['one'] = Result(
            {'t = 0.100 ms (final)': snap},
            dict(times=np.linspace(0, 2e-3, 30), radii=[0.5, 1.0],
                 pressures=[P_AIR + 100e3 * np.ones(30),
                            P_AIR + 50e3 * np.ones(30)]),
            dict(eos='JWL', charge_kg=1.0, radius_m=2.0,
                 final_profile=np.column_stack(
                     [r, snap['p'], snap['rho'], snap['u']])),
            'end time reached', False)
        rp.add_result('fit - 1D', 1, _RESULTS['one'])
        pump(500)
    rp.sel.setCurrentIndex(1)                # the 1D fixture
    rp.show_view('Field')
    pump(500)
    hint = rp.export_col.hint
    check(f'C9 (iv) {tag}: the export-title hint is a visible muted line',
          hint.isVisible() and hint.text().startswith('Exports use the full '
                                                      'title'),
          f'{hint.text()!r} visible {hint.isVisible()}')


def run_size(win, app, size, mode, pump, only):
    from blastlab.ui import theme
    theme.apply(app, mode)
    win.resize(*size)
    pump(400)
    tag = f'{size[0]}x{size[1]} {mode}'
    if not only or 'C6' in only:
        c6_setup(win, tag, pump)
    if not only or 'C7' in only:
        c7_chain(win, tag, pump)
    if not only or 'C8' in only:
        c8_run(win, tag, pump)
    if not only or 'C9' in only:
        c9_results(win, tag, pump)


def main():
    from blastlab.ui.testing import ensure_qapp, pump, use_model
    app = ensure_qapp(offscreen=False)
    from blastlab.ui import dialogs
    from blastlab.ui.app import MainWindow

    only = [a for a in (_arg('--only') or '').split(',') if a]
    crashes = []
    sys.excepthook = lambda *a: crashes.append(
        ''.join(traceback.format_exception(*a)))
    dialogs.show_error = lambda t, m, p=None: print(f'  (dialog) {t}: {m}')
    dialogs.ask_yes_no = lambda *a, **k: True
    dialogs.notify_desktop = lambda *a, **k: None
    win = MainWindow()
    use_model(win, 'FIT')
    win.show()
    pump(400)
    try:
        for size in SIZES:
            for mode in MODES:
                run_size(win, app, size, mode, pump, only)
    finally:
        win.close()
        pump(100)
    check('no uncaught exception', not crashes, '\n'.join(crashes)[:400])
    print(f'\n{len(RAN) - len(FAIL)} of {len(RAN)} passed')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
