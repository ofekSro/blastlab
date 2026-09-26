"""OUT-1 QA, PySide6 GUI, the blastFoam part, in a REAL window.

F1  a tiny blastFoam 1D run to the end: foam\\ skeleton + SHA256SUMS in
    the model folder, the scratch released, the Results-tab VTK button.
F2  a small 2D axisymmetric blastFoam run stopped partway: the scratch is
    kept, and the manifest says why (the run item 10 resumes from Tk).
F3  the HD 1.3 starter assessment; while it runs, Chain and a resume of
    F2's run are pressed ("A run is already in progress.").
F4  Open case... on the HD 1.3 MODEL.json.

Everything under `if __name__ == '__main__'`: the 3D viewer child is a
multiprocessing spawn that re-imports this file as __mp_main__.
Run (only after `wsl -d Ubuntu -- pgrep -a blastFoam` came back empty):
    python -u docs/qa/2026-09-26-out-1/scripts/qt_foam.py
"""
import json
import os
import sys
import time


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import qa_common as Q
    Q.private_env()
    Q.set_log('qt_foam')
    SHOTS = os.path.join(Q.OUT, 'shots')

    from PySide6.QtCore import QPoint, Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (QApplication, QMessageBox, QToolTip,
                                   QAbstractButton)
    app = QApplication.instance() or QApplication(['blastlab-qa'])
    from blastlab.core import settings as app_settings
    from blastlab.ui import theme
    theme.apply(app, app_settings.load().get('appearance', 'dark'))
    from blastlab.ui.app import MainWindow

    N = [0]
    MODAL = dict(plan=[], seen=[])

    def name_(tag):
        N[0] += 1
        return f'qtf_{N[0]:02d}_{tag}.png'

    def pump(seconds, until=None):
        end = time.perf_counter() + seconds
        while True:
            app.processEvents()
            if until is not None:
                r = until()
                if r:
                    return r
            if time.perf_counter() >= end:
                return None if until is not None else True
            time.sleep(0.01)

    def shot(tag, widget=None):
        pump(0.3)
        n = name_(tag)
        (widget or win).grab().save(os.path.join(SHOTS, n))
        Q.rec('shot', path=n)
        return n

    def frame_shot(tag, widget):
        n = name_(tag)
        try:
            Q.grab_hwnd(int(widget.winId()), os.path.join(SHOTS, n))
        except Exception as exc:
            widget.grab().save(os.path.join(SHOTS, n))
            Q.rec('frame_shot_fallback', error=str(exc))
        return n

    def tick():
        w = QApplication.activeModalWidget()
        if isinstance(w, QMessageBox) and w.isVisible() and \
                not getattr(w, '_qa_seen', False):
            w._qa_seen = True
            QTimer.singleShot(600, lambda: answer(w))

    def answer(w):
        ans = MODAL['plan'].pop(0) if MODAL['plan'] else None
        d = w.defaultButton()
        info = dict(title=w.windowTitle(), text=w.text(),
                    buttons=[b.text() for b in w.buttons()],
                    default=d.text() if d is not None else None)
        info['shot'] = frame_shot(f'dialog_{ans or "auto"}', w)
        info['answer'] = ans or 'auto'
        MODAL['seen'].append(info)
        Q.rec('dialog', **info)
        want = {'yes': QMessageBox.Yes, 'no': QMessageBox.No,
                'ok': QMessageBox.Ok}.get(ans)
        btn = w.button(want) if want is not None else None
        if btn is None:
            btn = w.button(QMessageBox.No) or w.escapeButton() or \
                w.button(QMessageBox.Ok)
        if btn is not None:
            btn.click()
        else:
            w.reject()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(100)

    def plan(*a):
        MODAL['plan'] = list(a)

    def manifest(folder):
        try:
            with open(os.path.join(folder, 'manifest.json'),
                      encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError) as exc:
            return {'_error': str(exc)}

    def wsl_exists(posix):
        import subprocess
        from blastlab.solvers.foam import env
        return subprocess.run(env.wsl_plain_argv(f"test -d '{posix}'"),
                              capture_output=True,
                              stdin=subprocess.DEVNULL).returncode == 0

    win = MainWindow()
    win.resize(1280, 840)
    win.show()
    pump(2.0)
    rp = win.run_panel
    rp.set_runs_dir(Q.RUNS)

    from blastlab.core.case import Case1D, Case2D
    # ── F1 ──────────────────────────────────────────────────────────────
    Q.rec('step', key='F1')
    f1 = Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.02,
                gauge_radii=[0.5, 1.0], n_snapshots=2,
                solver='blastfoam', material='C4', activation='none')
    win.setup.set_case(f1)
    win._schedule_validate()
    pump(3.0)
    Q.rec('F1_setup', solver=win.solver_mode.get(),
          report=win.setup.report_rows())
    rp.run_name.setText('QA_FOAM1D')
    folder1 = os.path.join(Q.RUNS, 'QA_FOAM1D')
    win._show('run')
    plan('yes')
    t0 = time.time()
    QTest.mouseClick(rp.run_btn, Qt.LeftButton)
    pump(15)
    shot('foam1d_running')
    pump(1800, until=lambda: not win.ctrl.running)
    pump(3.0)
    Q.rec('F1_done', seconds=round(time.time() - t0, 1),
          log_tail=rp.log_text()[-2500:])
    shot('foam1d_done')
    m1 = manifest(folder1)
    ws1 = m1.get('wsl_scratch') or {}
    Q.rec('F1_folder', tree=Q.tree(folder1), manifest=m1,
          scratch_exists_in_wsl=(wsl_exists(ws1['posix'])
                                 if ws1.get('posix') else None))
    try:
        with open(os.path.join(folder1, 'foam', 'SHA256SUMS'),
                  encoding='utf-8') as f:
            sums = f.read().splitlines()
        Q.rec('F1_sums', n=len(sums), head=sums[:8])
    except OSError as exc:
        Q.rec('F1_sums', error=str(exc))
    # the Results tab and its VTK button
    win._show('results')
    pump(1.0)
    ent = win.results.current()
    vb = win.results._export_btns['vtk']
    Q.rec('F1_vtk_button', label=ent.label if ent else None,
          visible=vb.isVisible(), enabled=vb.isEnabled(),
          text=vb.text(), tooltip=vb.toolTip(),
          meta_scratch_released=(ent.result.meta.get('scratch_released')
                                 if ent else None),
          meta_case_dir=(ent.result.meta.get('case_dir') if ent else None))
    shot('foam1d_results')
    QToolTip.showText(vb.mapToGlobal(QPoint(vb.width() // 2,
                                            vb.height() // 2)),
                      vb.toolTip(), vb)
    pump(0.8)
    for w in QApplication.topLevelWidgets():
        if w.metaObject().className() == 'QTipLabel' and w.isVisible():
            shot('foam1d_vtk_tooltip', w)
    QToolTip.hideText()
    if vb.isEnabled():
        win.results.export('vtk', threaded=False)
        pump(1.0)
        Q.rec('F1_vtk_click', status=win._status.text())
        shot('foam1d_vtk_clicked')

    # ── F2 ──────────────────────────────────────────────────────────────
    Q.rec('step', key='F2')
    f2 = Case2D(geometry='axisymmetric', Lx=0.6, Ly=1.2,
                cell_size_m=0.015, charge=1.0, center=(0.0, 0.6),
                gauges=[(0.35, 0.6)], n_snapshots=2, record_frames=0,
                bcs=dict(x_lo='reflect', x_hi='terminate',
                         y_lo='terminate', y_hi='terminate'),
                solver='blastfoam', material='TNT')
    win.setup.set_case(f2)
    win._schedule_validate()
    pump(3.0)
    rp.run_name.setText('QA_FOAM_STOP')
    folder2 = os.path.join(Q.RUNS, 'QA_FOAM_STOP')
    win._show('run')
    plan('yes')
    QTest.mouseClick(rp.run_btn, Qt.LeftButton)
    t0 = time.time()
    pump(60, until=lambda: not win.ctrl.running)
    was_running = win.ctrl.running
    shot('foamstop_running')
    # the unfinished-run manifest while it runs
    Q.rec('F2_while_running', manifest=manifest(folder2),
          top=sorted(os.listdir(folder2)) if os.path.isdir(folder2) else [])
    QTest.mouseClick(rp.stop_btn, Qt.LeftButton)
    pump(600, until=lambda: not win.ctrl.running)
    pump(3.0)
    m2 = manifest(folder2)
    ws2 = m2.get('wsl_scratch') or {}
    Q.rec('F2_done', was_running_at_stop=was_running,
          seconds=round(time.time() - t0, 1),
          log_tail=rp.log_text()[-1500:], tree=Q.tree(folder2), manifest=m2,
          scratch_exists_in_wsl=(wsl_exists(ws2['posix'])
                                 if ws2.get('posix') else None))
    shot('foamstop_done')
    win._show('results')
    pump(0.8)
    ent = win.results.current()
    vb = win.results._export_btns['vtk']
    Q.rec('F2_vtk_button', label=ent.label if ent else None,
          enabled=vb.isEnabled(), tooltip=vb.toolTip(),
          case_dir=(ent.result.meta.get('case_dir') if ent else None))
    shot('foamstop_results')
    stopped_path = ent.result.meta.get('case_dir') if ent else None

    # ── F3: HD 1.3 while Chain / resume are pressed ────────────────────
    Q.rec('step', key='F3')
    import tempfile
    from blastlab.output.cli_hd13 import write_starter_case
    from blastlab.models.hd13_case import load_case as load_hd13
    starter = write_starter_case(os.path.join(tempfile.mkdtemp(),
                                              'starter.json'))
    win._show('setup')
    win.setup.set_dim(0)
    pump(0.6)
    win.setup.forms[0].set_case(load_hd13(starter))
    pump(1.0)
    rp.run_name.setText('QA_HD13_BUSY')
    folder3 = os.path.join(Q.RUNS, 'QA_HD13_BUSY')
    win._show('run')
    plan('yes')
    t0 = time.time()
    QTest.mouseClick(rp.run_btn, Qt.LeftButton)
    pump(1.5)
    busy = win._hd13_busy
    Q.rec('F3_busy', busy=busy, run_btn_enabled=rp.run_btn.isEnabled(),
          status=win._status.text())
    shot('hd13_busy')
    if busy:
        from blastlab.core.case import Case1D as C1, Case2D as C2
        ch = win.chain
        ch.set_stage_case(1, C1(radius_m=0.6, charge_kg=0.5,
                                cell_size_m=0.004, n_snapshots=1,
                                gauge_radii=[]))
        ch.set_stage_case(2, C2(geometry='axisymmetric', Lx=1.0, Ly=1.6,
                                cell_size_m=0.03, charge=0.5,
                                center=(0.0, 0.8), n_snapshots=1,
                                gauges=[], record_frames=0))
        for d in (1, 2, 3):
            ch.use[d].setChecked(d < 3)
        rp.run_name.setText('QA_CHAIN_DURING_HD13')
        win._show('chain')
        pump(0.4)
        n0 = len(MODAL['seen'])
        plan('ok')
        en = ch.run_btn.isEnabled()
        QTest.mouseClick(ch.run_btn, Qt.LeftButton)
        pump(4, until=lambda: len(MODAL['seen']) > n0)
        Q.rec('F3_chain_during', run_chain_enabled=en,
              dialog=MODAL['seen'][-1] if len(MODAL['seen']) > n0 else None,
              folder=os.path.isdir(os.path.join(Q.RUNS,
                                                'QA_CHAIN_DURING_HD13')),
              still_busy=win._hd13_busy, chain_status=ch.status.text())
        shot('chain_during_hd13')
        if stopped_path:
            rp.run_name.setText('QA_RESUME_DURING_HD13')
            n0 = len(MODAL['seen'])
            plan('ok')
            r = win._resume_foam_run(stopped_path)
            pump(4, until=lambda: len(MODAL['seen']) > n0)
            Q.rec('F3_resume_during', returned=r,
                  dialog=MODAL['seen'][-1] if len(MODAL['seen']) > n0
                  else None, running=win.ctrl.running,
                  folder=os.path.isdir(os.path.join(
                      Q.RUNS, 'QA_RESUME_DURING_HD13')))
        rp.run_name.setText('QA_HD13_BUSY')
        win._show('run')
    pump(1800, until=lambda: not win._hd13_busy)
    pump(1.0)
    Q.rec('F3_done', seconds=round(time.time() - t0, 1),
          status=win._status.text(), status_tip=win._status.toolTip(),
          tree=Q.tree(folder3), manifest=manifest(folder3))
    shot('hd13_starter_done')

    # ── F4: Open case... on the HD 1.3 MODEL.json ──────────────────────
    Q.rec('step', key='F4')
    n0 = len(MODAL['seen'])
    plan('ok')
    win._open_case(os.path.join(folder3, 'MODEL.json'))
    pump(3, until=lambda: len(MODAL['seen']) > n0)
    Q.rec('F4_open_hd13_model_json',
          dialog=MODAL['seen'][-1] if len(MODAL['seen']) > n0 else None,
          dim=win.setup.dim)
    n0 = len(MODAL['seen'])
    plan('ok')
    win._open_case(os.path.join(folder1, 'MODEL.json'))
    pump(3, until=lambda: len(MODAL['seen']) > n0)
    Q.rec('F4_open_foam1d_model_json',
          dialog=MODAL['seen'][-1] if len(MODAL['seen']) > n0 else None,
          dim=win.setup.dim, model_box=rp.run_name.text())

    Q.rec('RESULT', stopped_run=(ws2.get('posix') or stopped_path))
    win.close()
    pump(1.0)
    Q.rec('closed')


if __name__ == '__main__':
    main()
    os._exit(0)
