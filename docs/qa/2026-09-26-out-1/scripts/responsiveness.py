"""Item 12, measured the Windows way: is the window answering messages while
a native 1D -> 2D chain moves from stage 1 to stage 2?

Two independent probes, neither of which depends on how the harness pumps:
  * a thread sends WM_NULL to the top-level HWND with SendMessageTimeout
    (SMTO_ABORTIFHUNG, 100 ms) every 50 ms and records every stretch in
    which the window did not answer - the criterion Windows itself uses
    for "Not Responding" (5 s);
  * a self-rescheduling 20 ms timer on the GUI thread (Tk `after` / Qt
    QTimer) records the longest interval between two of its ticks.

Run:  python -u responsiveness.py tk|qt
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading
import time


def main():
    kit = sys.argv[1]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import qa_common as Q
    Q.private_env()
    Q.set_log(f'responsiveness_{kit}')
    from blastlab.core.case import Case1D, Case2D

    user32 = ctypes.WinDLL('user32')
    user32.SendMessageTimeoutW.argtypes = [
        wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
        ctypes.POINTER(ctypes.c_size_t)]
    user32.SendMessageTimeoutW.restype = ctypes.c_size_t

    probe = dict(hwnd=None, stop=False, bad=[], cur=None)

    def prober():
        while not probe['stop']:
            h = probe['hwnd']
            if h:
                res = ctypes.c_size_t()
                t = time.time()
                ok = user32.SendMessageTimeoutW(h, 0, 0, 0, 0x0002, 100,
                                                ctypes.byref(res))
                if not ok:
                    if probe['cur'] is None:
                        probe['cur'] = t
                elif probe['cur'] is not None:
                    probe['bad'].append((probe['cur'], time.time()))
                    probe['cur'] = None
            time.sleep(0.05)
    threading.Thread(target=prober, daemon=True).start()

    ticks = []

    def stages():
        s1 = Case1D(radius_m=0.6, charge_kg=0.5, cell_size_m=0.004,
                    n_snapshots=1, gauge_radii=[], gauge_file=None)
        s2 = Case2D(geometry='axisymmetric', Lx=1.0, Ly=1.6,
                    cell_size_m=0.03, charge=0.5, center=(0.0, 0.8),
                    n_snapshots=1, gauges=[(0.6, 0.8)], record_frames=0)
        return s1, s2

    def report(tag, t0, marks, loop_gaps):
        tick_gaps = [(round(a - t0, 2), round((b - a) * 1e3))
                     for a, b in zip(ticks, ticks[1:]) if b - a > 0.25]
        hung = [(round(a - t0, 2), round((b - a) * 1e3))
                for a, b in probe['bad'] if a >= t0]
        Q.rec('responsiveness', kit=kit, tag=tag, marks=marks,
              timer_gaps_over_250ms=tick_gaps,
              max_timer_gap_ms=max([g for _a, g in tick_gaps] or [0]),
              wm_null_unanswered=hung,
              max_unanswered_ms=max([g for _a, g in hung] or [0]),
              pump_gaps_over_250ms=loop_gaps)

    if kit == 'tk':
        import customtkinter as ctk
        from blastlab.gui import app as gapp
        root = ctk.CTk()
        app = gapp.App(root)
        root.geometry('1280x840+60+40')

        def tick():
            ticks.append(time.time())
            root.after(20, tick)
        root.after(20, tick)
        for _ in range(200):
            root.update()
            time.sleep(0.01)
        probe['hwnd'] = int(root.wm_frame(), 16)
        rp, ch = app.run_panel, app.chain
        for k in range(2):
            model = f'RESP_TK_{k}'
            rp.set_runs_dir(Q.RUNS)
            rp.run_name.set(model)
            s1, s2 = stages()
            ch.set_stage_case(1, s1)
            ch.set_stage_case(2, s2)
            ch.use[1].set(True)
            ch.use[2].set(True)
            ch.use[3].set(False)
            app._show('chain')
            for _ in range(30):
                root.update()
                time.sleep(0.01)
            del ticks[:]
            t0 = time.time()
            ch._run()
            marks, gaps = {}, []
            while time.time() - t0 < 600:
                a = time.time()
                root.update()
                b = time.time()
                if b - a > 0.25:
                    gaps.append((round(a - t0, 2), round((b - a) * 1e3)))
                lt = rp.log.get('1.0', 'end')
                for s in ('=== Stage 1D ===', '=== Stage 2D ==='):
                    if s in lt and s not in marks:
                        marks[s] = round(time.time() - t0, 2)
                if not app._running() and time.time() - t0 > 3:
                    break
                time.sleep(0.01)
            report(f'chain{k}', t0, marks, gaps)
        probe['stop'] = True
        app._on_close()
    else:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        qapp = QApplication.instance() or QApplication(['qa'])
        from blastlab.ui import theme
        theme.apply(qapp, 'dark')
        from blastlab.ui import dialogs
        from blastlab.ui.app import MainWindow
        dialogs.ask_yes_no = lambda *a, **k: False
        win = MainWindow()
        win.resize(1280, 840)
        win.show()
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(time.time()))
        timer.start(20)
        end = time.time() + 2
        while time.time() < end:
            qapp.processEvents()
            time.sleep(0.01)
        probe['hwnd'] = int(win.winId())
        rp, ch = win.run_panel, win.chain
        for k in range(2):
            model = f'RESP_QT_{k}'
            rp.set_runs_dir(Q.RUNS)
            rp.run_name.setText(model)
            s1, s2 = stages()
            ch.set_stage_case(1, s1)
            ch.set_stage_case(2, s2)
            for d in (1, 2, 3):
                ch.use[d].setChecked(d < 3)
            win._show('chain')
            end = time.time() + 0.5
            while time.time() < end:
                qapp.processEvents()
                time.sleep(0.01)
            del ticks[:]
            t0 = time.time()
            ch.run()
            marks, gaps = {}, []
            while time.time() - t0 < 600:
                a = time.time()
                qapp.processEvents()
                b = time.time()
                if b - a > 0.25:
                    gaps.append((round(a - t0, 2), round((b - a) * 1e3)))
                lt = rp.log_text()
                for s in ('=== Stage 1D ===', '=== Stage 2D ==='):
                    if s in lt and s not in marks:
                        marks[s] = round(time.time() - t0, 2)
                if not win.ctrl.running and time.time() - t0 > 3:
                    break
                time.sleep(0.01)
            report(f'chain{k}', t0, marks, gaps)
        probe['stop'] = True
        win.close()


if __name__ == '__main__':
    main()
    os._exit(0)
