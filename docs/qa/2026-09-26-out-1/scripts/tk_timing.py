"""OUT-1 QA, Tk: (a) where the event loop goes during a chain's stage 1 ->
stage 2 switch, (b) the same for a plain Run of the chain's 1D and 2D
cases, (c) Enter on the overwrite question, delivered to the dialog only
(posted WM_KEYDOWN/WM_KEYUP VK_RETURN to its focused button - never a
global keystroke; if it is not taken within 3 s, No is clicked and that
is recorded).

A sampler thread records the Tk main thread's Python stack every 100 ms
(sys._current_frames), so a long `root.update()` can be attributed to a
file and line.

Run:  python -u docs/qa/2026-09-26-out-1/scripts/tk_timing.py
"""
import collections
import os
import sys
import threading
import time
import traceback


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import qa_common as Q
    Q.private_env()
    Q.set_log('tk_timing')
    SHOTS = os.path.join(Q.OUT, 'shots')
    import customtkinter as ctk
    from blastlab.gui import app as gapp
    from blastlab.core.case import Case1D, Case2D, Case3D

    root = ctk.CTk()
    app = gapp.App(root)
    root.geometry('1280x840+60+40')
    main_id = threading.get_ident()
    SAMPLES = []
    stop_sampling = threading.Event()

    def sampler():
        while not stop_sampling.is_set():
            fr = sys._current_frames().get(main_id)
            if fr is not None:
                st = traceback.extract_stack(fr)[-16:]
                SAMPLES.append((time.time(), [
                    f'{os.path.basename(f.filename)}:{f.lineno}:{f.name}'
                    for f in st]))
            time.sleep(0.1)
    threading.Thread(target=sampler, daemon=True).start()

    def pump(seconds, until=None):
        end = time.time() + seconds
        while True:
            root.update()
            if until is not None and until():
                return True
            if time.time() >= end:
                return False
            time.sleep(0.01)

    def running():
        return app._running()

    def log_text():
        return app.run_panel.log.get('1.0', 'end')

    APP_FILES = ('app.py', 'run_panel.py', 'results_panel.py', 'mpl.py',
                 'preview_panel.py', 'forms.py', 'view3d_panel.py',
                 'chain_panel.py', 'worker.py', 'theme.py')

    def measure(tag, start, marks_wanted):
        t0 = time.time()
        start()
        t_ret = time.time()
        gaps, marks = [], {}
        while time.time() - t0 < 900:
            a = time.time()
            root.update()
            b = time.time()
            if b - a > 0.25:
                gaps.append((a, b))
            lt = log_text()
            for s in marks_wanted:
                if s in lt and s not in marks:
                    marks[s] = round(time.time() - t0, 2)
            if not running() and time.time() - t0 > 3:
                break
            time.sleep(0.01)
        pump(1.0)
        out = []
        for a, b in gaps:
            inside = [s for t, s in SAMPLES if a <= t <= b]
            cnt = collections.Counter(
                ' <- '.join(reversed([x for x in s
                                      if x.split(':')[0] in APP_FILES][-4:]))
                for s in inside)
            full = collections.Counter(' <- '.join(reversed(s[-7:]))
                                       for s in inside)
            out.append(dict(at_s=round(a - t0, 2),
                            gap_ms=round((b - a) * 1e3),
                            samples=len(inside),
                            top_app=cnt.most_common(3),
                            top_full=full.most_common(2)))
        Q.rec('gap_report', tag=tag, start_call_s=round(t_ret - t0, 2),
              marks=marks, total_s=round(time.time() - t0, 1), gaps=out)

    pump(2.0)
    rp = app.run_panel

    def chain_forms(model):
        ch = app.chain
        rp.set_runs_dir(Q.RUNS)
        rp.run_name.set(model)
        ch.set_stage_case(1, Case1D(radius_m=0.6, charge_kg=0.5,
                                    cell_size_m=0.004, n_snapshots=1,
                                    gauge_radii=[], gauge_file=None))
        ch.set_stage_case(2, Case2D(geometry='axisymmetric', Lx=1.0, Ly=1.6,
                                    cell_size_m=0.03, charge=0.5,
                                    center=(0.0, 0.8), n_snapshots=1,
                                    gauges=[(0.6, 0.8)], record_frames=0))
        ch.set_stage_case(3, Case3D(Lx=1.2, Ly=1.2, Lz=1.2,
                                    cell_size_m=0.08, charge=0.5,
                                    center=(0.6, 0.6, 0.6), n_snapshots=1,
                                    gauges=[], record_frames=0))
        for d in (1, 2, 3):
            ch.use[d].set(d < 3)
        pump(0.5)
        return ch

    for k in range(3):
        ch = chain_forms(f'TK_CHAIN_T{k}')
        app._show('chain')
        pump(0.3)
        measure(f'chain{k}', ch._run, ('=== Stage 1D ===',
                                       '=== Stage 2D ==='))
    app.setup.set_case(Case1D(radius_m=0.6, charge_kg=0.5,
                              cell_size_m=0.004, n_snapshots=1,
                              gauge_radii=[]))
    pump(0.8)
    rp.run_name.set('TK_RUN1D_T')
    measure('run1d', rp.run_btn.invoke, ())
    app.setup.set_case(Case2D(geometry='axisymmetric', Lx=1.0, Ly=1.6,
                              cell_size_m=0.03, charge=0.5,
                              center=(0.0, 0.8), n_snapshots=1,
                              gauges=[(0.6, 0.8)], record_frames=0))
    pump(0.8)
    rp.run_name.set('TK_RUN2D_T')
    measure('run2d', rp.run_btn.invoke, ())

    class EnterWatcher(Q.NativeDialogWatcher):
        def run(self):
            end = time.time() + self.timeout
            try:
                while time.time() < end:
                    for h, k, t in Q.top_windows():
                        if k == '#32770' and self.title_has in t:
                            time.sleep(1.0)
                            self.info = Q.dialog_info(h)
                            Q.grab_hwnd(h, self.shot_path)
                            self.info['shot'] = os.path.basename(
                                self.shot_path)
                            target = next((b['hwnd'] for b in
                                           self.info['buttons']
                                           if b['defpush']), h)
                            Q.user32.PostMessageW(target, 0x0100,
                                                  Q.VK_RETURN, 0x001C0001)
                            Q.user32.PostMessageW(target, 0x0101,
                                                  Q.VK_RETURN, 0xC01C0001)
                            self.info['action'] = ['posted VK_RETURN']
                            time.sleep(3.0)
                            still = any(hh == h for hh, _k, _t
                                        in Q.top_windows())
                            self.info['closed_by_enter'] = not still
                            if still:
                                for b in self.info['buttons']:
                                    if b['text'].replace('&', '') == 'No':
                                        Q.user32.PostMessageW(
                                            b['hwnd'], Q.BM_CLICK, 0, 0)
                                self.info['fallback'] = 'clicked No'
                            for b in self.info['buttons']:
                                b.pop('hwnd', None)
                            return
                    time.sleep(0.15)
            finally:
                self.done.set()

    folder = os.path.join(Q.RUNS, 'TK_RUN2D_T')
    snap = {p: os.stat(os.path.join(folder, p)).st_mtime_ns
            for p in os.listdir(folder)}
    w = EnterWatcher(os.path.join(SHOTS, 'tkt_01_dialog_enter.png'),
                     None, timeout=30, title_has='Model folder')
    w.start()
    rp.run_btn.invoke()
    pump(8, until=lambda: w.done.is_set())
    pump(1.0)
    after = {p: os.stat(os.path.join(folder, p)).st_mtime_ns
             for p in os.listdir(folder)}
    Q.rec('tk_enter', info=w.info, folder_untouched=(after == snap),
          run_started=running())
    if running():
        pump(300, until=lambda: not running())
    stop_sampling.set()
    t0 = time.time()
    app._on_close()        # the WM_DELETE_WINDOW handler; destroys root
    Q.rec('closed', seconds=round(time.time() - t0, 2))


if __name__ == '__main__':
    main()
    os._exit(0)
