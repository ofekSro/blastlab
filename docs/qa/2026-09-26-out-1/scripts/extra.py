"""Two leftovers of item 1/2, both toolkits:
  * the Runs folder Browse (Qt) / folder icon (Tk): the real folder picker,
    where it opens, grabbed and cancelled;
  * Initialise Model with an empty Runs folder: refused like Run.

Run:  python -u extra.py qt|tk
"""
import os
import sys
import time


def main():
    kit = sys.argv[1]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import qa_common as Q
    Q.private_env()
    Q.set_log(f'extra_{kit}')
    SHOTS = os.path.join(Q.OUT, 'shots')
    from blastlab.core.case import Case1D
    case = Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.005,
                  gauge_radii=[0.5, 1.0], n_snapshots=3)
    if kit == 'qt':
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(['qa'])
        from blastlab.ui import theme
        theme.apply(app, 'dark')
        from blastlab.ui.app import MainWindow
        win = MainWindow()
        win.resize(1280, 840)
        win.show()

        def pump(s):
            end = time.time() + s
            while time.time() < end:
                app.processEvents()
                time.sleep(0.01)
        pump(2)
        win.setup.set_case(case)
        win._show('run')
        rp = win.run_panel
        rp.set_runs_dir(Q.RUNS)
        w = Q.NativeDialogWatcher(os.path.join(SHOTS, 'extra_qt_browse.png'),
                                  lambda i: ('close',), timeout=20,
                                  title_has='Runs folder')
        w.start()
        rp.runs_browse.click()
        pump(1)
        Q.rec('browse', native=w.info, box_after=rp.runs_dir.text())
        seen = []

        def tick():
            m = QApplication.activeModalWidget()
            if isinstance(m, QMessageBox) and not getattr(m, '_s', 0):
                m._s = 1
                Q.grab_hwnd(int(m.winId()),
                            os.path.join(SHOTS, 'extra_qt_init_refused.png'))
                seen.append(dict(title=m.windowTitle(), text=m.text()))
                m.button(QMessageBox.Ok).click()
        t = QTimer()
        t.timeout.connect(tick)
        t.start(150)
        rp.set_runs_dir('')
        rp.run_name.setText('INIT_TEST')
        rp.init_btn.click()
        pump(2)
        Q.rec('init_refusal', dialogs=seen, running=win.ctrl.running,
              folder=os.path.isdir(os.path.join(Q.RUNS, 'INIT_TEST')))
        rp.set_runs_dir(Q.RUNS)
        win.close()
        pump(0.5)
    else:
        import customtkinter as ctk
        import tkinter.filedialog as fd
        from blastlab.gui import app as gapp
        root = ctk.CTk()
        app = gapp.App(root)

        def pump(s):
            end = time.time() + s
            while time.time() < end:
                root.update()
                time.sleep(0.01)
        pump(2)
        app.setup.set_case(case)
        app._show('run')
        rp = app.run_panel
        rp.set_runs_dir(Q.RUNS)
        real = fd.askdirectory
        got = {}

        def askdirectory(**kw):
            got.update({k: str(v) for k, v in kw.items()})
            return real(**kw)
        fd.askdirectory = askdirectory
        w = Q.NativeDialogWatcher(os.path.join(SHOTS, 'extra_tk_browse.png'),
                                  lambda i: ('close',), timeout=20,
                                  title_has='Runs folder')
        w.start()
        rp._runs_browse.invoke()
        pump(1)
        fd.askdirectory = real
        Q.rec('browse', kwargs=got, native=w.info,
              box_after=rp.runs_dir.get())
        rp.set_runs_dir('')
        rp.run_name.set('INIT_TEST')
        w = Q.NativeDialogWatcher(
            os.path.join(SHOTS, 'extra_tk_init_refused.png'),
            lambda i: ('button', 'OK'), timeout=20, title_has='Run')
        w.start()
        rp.init_btn.invoke()
        pump(1)
        Q.rec('init_refusal', native=w.info, running=app._running(),
              folder=os.path.isdir(os.path.join(Q.RUNS, 'INIT_TEST')))
        rp.set_runs_dir(Q.RUNS)
        app._on_close()


if __name__ == '__main__':
    main()
    os._exit(0)
