"""GUI-15 QA: Setup Checks wording in blastFoam mode (no solve is started)."""
import os, sys
REPO = r'C:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
sys.path.insert(0, REPO)
OUT = os.path.join(REPO, 'docs', 'qa', '2026-10-11-gui-15-qa')
os.environ.pop('QT_QPA_PLATFORM', None)


def main():
    from blastlab.ui import testing
    testing.private_settings()
    app = testing.ensure_qapp(offscreen=False)
    pump = testing.pump
    from blastlab.ui import dialogs
    for n in ('show_error', 'warn', 'show_info'):
        setattr(dialogs, n, lambda *a, **k: None)
    from blastlab.core.case import Case1D, Case2D
    from blastlab.ui.app import MainWindow
    win = MainWindow()
    win.set_solver('blastfoam')
    testing.use_model(win, 'gui15foam')
    win.resize(1100, 720)
    win.show()
    pump(500)
    win._show('setup')
    win.setup.set_dim(2)
    W = (1.2, 1.6, 0.0, 0.6)
    for tag, g2, trig in (('near', (1.195, 0.3), 3), ('inside', (1.4, 0.3), 3), ('trigdrop', (1.4, 0.3), 2)):
        c = Case2D(solver='blastfoam', geometry='planar', Lx=2.4, Ly=1.6, cell_size_m=0.05,
                   charge=20.0, center=(0.6, 0.0), obstacles=[W],
                   gauges=[(0.3, 0.8), g2, (0.6, 0.5), (1.0, 1.0)],
                   trigger_gauge=trig, trigger_action='terminate')
        win.setup.set_case(c)
        win._schedule_validate()
        pump(900)
        print(tag, [m for s, m in win.setup.report_rows() if s == 'warn'])
        win.setup.show_checks()
        pump(300)
        win.raise_()
        win.grab().save(os.path.join(OUT, f'17_foam_setup_checks_{tag}_1100x720.png'))
    win.setup.set_dim(1)
    win.setup.set_case(Case1D(solver='blastfoam', radius_m=1.5, gauge_radii=[1.0, 2.0, 1.2], charge_kg=1.0))
    win._schedule_validate()
    pump(900)
    print('1D foam', [m for s, m in win.setup.report_rows() if s == 'warn'])
    win.setup.show_checks()
    pump(300)
    win.grab().save(os.path.join(OUT, '17_foam_setup_checks_1d_1100x720.png'))
    win.close()
    pump(300)


if __name__ == '__main__':
    main()
