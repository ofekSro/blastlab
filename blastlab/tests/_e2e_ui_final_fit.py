"""GUI-16 (C6-C9, C11): what the Qt screens SHOW at the two window sizes, on
the real platform. Batch docs/batches/2026-10-12-gui-final-2.md, Part C.

Real platform (`QT_QPA_PLATFORM` unset), the real MainWindow on throwaway
settings (CLAUDE.md sec. 8.2 / 8.7), 1100 x 720 and 1600 x 1000, dark and
light. Per check it prints the text the screen shows (a label's own text, or
`fontMetrics().elidedText` against the real width for a cell or a box that
elides) and PASS / FAIL.

  C6   Setup: the Gauges caption keeps `G2 dropped` and `trigger G3`; the
       trigger dropdown's current text is whole; Where shows `(dropped)`.

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


def run_size(win, app, size, mode, pump, only):
    from blastlab.ui import theme
    theme.apply(app, mode)
    win.resize(*size)
    pump(400)
    tag = f'{size[0]}x{size[1]} {mode}'
    if not only or 'C6' in only:
        c6_setup(win, tag, pump)


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
