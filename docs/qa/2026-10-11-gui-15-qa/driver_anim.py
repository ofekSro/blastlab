"""GUI-15 QA: 2D animation export with G2 dropped before the trigger (G3)."""
import os, sys, time, subprocess
REPO = r'C:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
sys.path.insert(0, REPO)
OUT = os.path.join(REPO, 'docs', 'qa', '2026-10-11-gui-15-qa')
os.environ.pop('QT_QPA_PLATFORM', None)


def main():
    from blastlab.ui import testing
    testing.private_settings()
    app = testing.ensure_qapp(offscreen=False)
    pump = testing.pump
    from blastlab.ui import dialogs, run_controller
    run_controller.pyvista_available = lambda: False
    target = os.path.join(OUT, '16_animation_export.mp4')
    dialogs.save_file = lambda *a, **k: target
    dialogs.ask_yes_no = lambda *a, **k: True
    from blastlab.core.case import Case2D
    from blastlab.ui.app import MainWindow
    win = MainWindow()
    win.set_solver('native')
    testing.use_model(win, 'gui15anim')
    win.resize(1100, 720)
    win.show()
    pump(400)
    case = Case2D(solver='native', geometry='planar', Lx=2.4, Ly=1.6, cell_size_m=0.04,
                  charge=20.0, center=(0.6, 0.0), obstacles=[(1.2, 1.6, 0.0, 0.6)],
                  bcs=dict(x_lo='reflect', x_hi='terminate', y_lo='reflect', y_hi='terminate'),
                  gauges=[(0.3, 0.8), (1.4, 0.3), (0.6, 0.5), (1.0, 1.0)],
                  n_snapshots=3, record_frames=8, gauge_file=None,
                  trigger_gauge=3, trigger_action='terminate')
    win._show('setup'); win.setup.set_dim(2); win.setup.set_case(case)
    pump(500)
    win._run_single()
    t0 = time.monotonic()
    while win.ctrl.running and time.monotonic() - t0 < 200:
        pump(30)
    pump(800)
    win._show('results'); pump(300)
    win.results.show_view('Field'); pump(800)
    win.grab().save(os.path.join(OUT, '16_results_field_before_export_1100x720.png'))
    r = win.results.export('gif', threaded=False)
    pump(1500)
    print('export target', r, os.path.exists(target), os.path.getsize(target) if os.path.exists(target) else None)
    win.close(); pump(300)
    meta = None
    for n in (1, 3, 5):
        png = os.path.join(OUT, f'16_animation_frame{n}.png')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', target, '-vf',
                        f'select=eq(n\\,{n})', '-vframes', '1', png])
        print(png, os.path.exists(png))


if __name__ == '__main__':
    main()
