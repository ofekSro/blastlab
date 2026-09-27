"""Throwaway QA harness, the one real run: the _e2e_vtk_3d.py case C
(0.6 m cube, 4 cm cells, one obstacle box, one gauge, t_end 1 ms, serial,
adaptive write off; sections + obstacles p/pMax every 25 steps with an
extra plane x = 0.2; volumes p/rho/U every 0.1 ms) opened from a case file
in the REAL Qt window, run with the Run button, into a private runs folder.
Run:  python -u qa_qt_run.py <shots dir> <work dir> <runs dir>
"""
import json
import os
import sys
import time
import traceback

REPO = r'C:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
sys.path.insert(0, REPO)
os.environ.pop('QT_QPA_PLATFORM', None)
assert os.environ.get('BLASTLAB_SETTINGS')
SHOTS, WORK, RUNS = sys.argv[1], sys.argv[2], sys.argv[3]
MODEL = 'QA_OUT2_VTK'
RES = dict(dialogs=[], log='', notes=[])


def main():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(['blastlab'])
    from blastlab.core import settings
    assert settings.load().get('auto_cleanup') is False
    from blastlab.ui import dialogs, theme
    theme.apply(app, 'dark')
    for fn in ('show_error', 'show_info', 'warn'):
        setattr(dialogs, fn, lambda t, m, p=None, _fn=fn:
                RES['dialogs'].append((_fn, t, m)))
    dialogs.ask_yes_no = lambda t, m, p=None: RES['dialogs'].append(
        ('ask_yes_no', t, m)) or True
    from blastlab.core.case import Case3D, save_case
    from blastlab.ui.app import MainWindow
    from blastlab.ui.testing import use_model

    def pump(s=0.3):
        end = time.monotonic() + s
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    case = Case3D(Lx=0.6, Ly=0.6, Lz=0.6, cell_size_m=0.04, charge=20.0,
                  center=(0.3, 0.3, 0.3), gauges=[(0.3, 0.3, 0.5)],
                  obstacles=[(0.47, 0.57, 0.1, 0.3, 0.1, 0.3)],
                  n_snapshots=2, record_frames=20, solver='blastfoam',
                  material='TNT', n_procs=1, adaptive_write=False, t_end=1e-3,
                  bcs={s: 'transmit' for s in ('x_lo', 'x_hi', 'y_lo', 'y_hi',
                                               'z_lo', 'z_hi')},
                  vtk_surfaces=dict(on=True, mode='step', value=25,
                                    fields=['p', 'pMax'],
                                    obstacle_fields=['p', 'pMax'],
                                    planes=[['x', 0.2]]),
                  vtk_volumes=dict(on=True, mode='time', value=0.1,
                                   fields=['p', 'rho', 'U']))
    path = os.path.join(WORK, 'qa_run_case.json')
    save_case(case, path)
    win = MainWindow()
    win.resize(1280, 840)
    win.show()
    pump(3.0)
    win._open_case(path)
    pump(2.0)
    folder = use_model(win, MODEL, runs_dir=RUNS)
    RES['folder'] = folder
    win._schedule_validate()
    pump(2.0)
    RES['strip'] = [f'{s}: {t}' for s, t in win.setup.report_rows()]
    win.setup.scroll_form(0.0)
    f = win.setup.form
    try:
        win.setup._scroll.ensureWidgetVisible(f.cards['VTK output (ParaView)'], 0, 0)
    except Exception:
        pass
    pump(0.6)
    win.grab().save(os.path.join(SHOTS, 'qt_run_00_setup_loaded.png'))
    f.cards['VTK output (ParaView)'].grab().save(
        os.path.join(SHOTS, 'qt_run_00_setup_card.png'))
    win._show('run')
    pump(0.6)
    rp = win.run_panel
    btn = rp.run_btn
    RES['run_btn_enabled_before'] = btn.isEnabled()
    QTest.mouseClick(btn, Qt.LeftButton)
    t0 = time.time()
    pump(3.0)
    RES['run_btn_enabled_during'] = btn.isEnabled()
    RES['stop_btn_enabled_during'] = rp.stop_btn.isEnabled()
    shots = 0
    last = 0
    while time.time() - t0 < 40 * 60:
        pump(1.0)
        if time.time() - last > 60 and shots < 4:
            win.grab().save(os.path.join(SHOTS, f'qt_run_0{shots + 1}_running.png'))
            shots += 1
            last = time.time()
        if not win.ctrl.running and time.time() - t0 > 10:
            break
    RES['elapsed_s'] = round(time.time() - t0)
    pump(8.0)
    RES['log'] = rp.log_text()
    win.grab().save(os.path.join(SHOTS, 'qt_run_10_done_runtab.png'))
    win._show('results')
    pump(3.0)
    win.grab().save(os.path.join(SHOTS, 'qt_run_11_results.png'))
    RES['results_texts'] = []
    from PySide6.QtWidgets import QLabel, QAbstractButton
    for w in win.results.findChildren(QLabel) + win.results.findChildren(QAbstractButton):
        try:
            if w.isVisible() and w.text():
                RES['results_texts'].append(w.text())
        except Exception:
            pass
    win.close()
    pump(1.5)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        RES['error'] = traceback.format_exc()
        traceback.print_exc()
    with open(os.path.join(SHOTS, 'qt_run_results.json'), 'w', encoding='utf-8') as fh:
        json.dump(RES, fh, indent=1, default=str)
    print('run harness done', RES.get('elapsed_s'), flush=True)
