"""GUI-14 QA driver 2 (Qt, real platform): axisymmetric native run, Z-mode Run card header."""
import os, sys, json, time
REPO = r'C:\Users\rotem.ofek\blastlab-worktrees\gui-14'
sys.path.insert(0, REPO)
OUT = os.path.join(REPO, 'docs', 'qa', '2026-10-11-gui-14-qa')
os.environ.pop('QT_QPA_PLATFORM', None)
os.environ['PYTHONIOENCODING'] = 'utf-8'
RES = []


def check(name, ok, detail=''):
    RES.append(dict(name=name, ok=bool(ok), detail=str(detail)))
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else '  -> ' + str(detail)))
    if detail:
        print('      ' + str(detail)[:500])


def main():
    from blastlab.ui import testing
    testing.private_settings()
    app = testing.ensure_qapp(offscreen=False)
    pump = testing.pump
    from blastlab.ui import dialogs, run_controller
    run_controller.pyvista_available = lambda: False
    modal = []
    for n in ('show_error', 'warn', 'show_info'):
        setattr(dialogs, n, lambda title, text, parent=None, _n=n: modal.append((_n, title, str(text))))
    dialogs.ask_yes_no = lambda *a, **k: modal.append(('ask', a[:1])) or True
    from blastlab.core.case import Case2D
    from blastlab.ui.app import MainWindow
    win = MainWindow()
    win.set_solver('native')
    testing.use_model(win, 'gui14qa2')
    win.resize(1100, 720)
    win.show()
    pump(500)

    def shoot(name, size):
        win.resize(*size)
        pump(300)
        win.raise_()
        win.grab().save(os.path.join(OUT, f'{name}_{size[0]}x{size[1]}.png'))

    def both(name):
        for sz in ((1100, 720), (1600, 1000)):
            shoot(name, sz)
        win.resize(1100, 720)
        pump(250)

    ax = Case2D(solver='native', geometry='axisymmetric', Lx=3.0, Ly=3.0,
                cell_size_m=0.1, charge=50.0, center=(0.0, 1.5),
                t_end=2e-3, n_snapshots=3, record_frames=0, gauge_file=None,
                obstacles=[(2.0, 2.4, 0.0, 3.0)],
                gauges=[(1.0, 1.5), (1.5, 1.5), (2.2, 1.5), (4.0, 1.5)])
    win._show('setup')
    win.setup.set_dim(2)
    win.setup.set_case(ax)
    win._schedule_validate()
    pump(900)
    win.setup.dock.set('Gauges')
    pump(300)
    print('AXISYM gauge rows', win.setup.gauge_rows())
    print('AXISYM drops', [m for s, m in win.setup.report_rows() if 'dropped' in m])
    both('11_setup_gauges_axisym')
    win._run_single()
    t0 = time.monotonic()
    while win.ctrl.running and time.monotonic() - t0 < 240:
        pump(30)
    pump(900)
    check('axisym run finished', not win.ctrl.running, f'{time.monotonic()-t0:.1f}s')
    log = win.run_panel.log.toPlainText()
    print('LOG', [l for l in log.splitlines() if 'dropped' in l])
    win._show('run')
    pump(400)
    col = win.run_panel.gauge_col
    card = col.card
    full = card.meta.full_text()
    print('AXISYM card header', repr(full), '|', col.caption_text())
    check('Run card header (axisym, Z mode): "Z <v> m/kg^1/3", no "selected"',
          full.startswith('Z ') and 'm/kg^1/3' in full and 'selected' not in full, full)
    mg, pg = card.meta.geometry(), card.peak.geometry()
    check('Run card (Z): header and peak do not overlap at 1100x720',
          mg.right() < pg.left() or mg.left() > pg.right(), (mg, pg))
    both('12_run_card_Zmode')
    card.meta.setFixedWidth(70)
    pump(150)
    check('Run card (Z) forced narrow: elided at the END, starts "Z ", tooltip full',
          card.meta.elided() and card.meta.text().startswith('Z ') and card.meta.toolTip() == full,
          (card.meta.text(), card.meta.toolTip()))
    win.grab().save(os.path.join(OUT, '13_run_card_forced_elide_Z_1100x720.png'))
    card.meta.setMinimumWidth(0)
    card.meta.setMaximumWidth(16777215)
    pump(150)
    win.showMaximized()
    pump(500)
    win.grab().save(os.path.join(OUT, '14_run_Zmode_maximised.png'))
    print('maximised', win.size().width(), win.size().height())
    win.showNormal()
    win.resize(1100, 720)
    pump(300)
    check('no modal dialogs', not modal, modal)
    win.close()
    pump(300)
    json.dump(RES, open(os.path.join(OUT, 'results_qt2.json'), 'w'), indent=1)
    print(f'{sum(r["ok"] for r in RES)}/{len(RES)} checks passed')


if __name__ == '__main__':
    main()
