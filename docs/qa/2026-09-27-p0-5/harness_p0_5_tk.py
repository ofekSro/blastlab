"""Tk disk-warning check driven INSIDE root.mainloop(), as the real app runs.

harness_p0_5.py tk pumps root.update() instead of mainloop; tkinter then
refuses root.after() from the warning thread ("main thread is not in main
loop", RuntimeError), which App._log_threadsafe/_disk_warning swallow, so
nothing arrives. This variant runs the scenario from after() callbacks
under a real mainloop and never blocks it.
"""
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness_p0_5 as H                                         # noqa: E402


def main(tmp, early):
    S = H.private(tmp)
    import tkinter as tk
    import customtkinter as ctk
    from blastlab.gui import app as appmod
    from blastlab.solvers.foam import env
    from test_settings_path import stub_wsl

    modal_calls = []
    mb = appmod.messagebox
    for n in ('showerror', 'showwarning', 'showinfo', 'askyesno',
              'askokcancel', 'askquestion', 'askyesnocancel', 'askretrycancel'):
        setattr(mb, n, (lambda n: lambda *a, **k: modal_calls.append((n, a)))(n))

    ctk.set_appearance_mode('dark')
    root = ctk.CTk()
    app = appmod.App(root)
    hwnd = [None]
    notes = []
    real_notify = app.notify

    def notify(text, level='info'):
        notes.append((text, level))
        real_notify(text, level)
    app.notify = notify
    log0 = [app.run_panel.log.get('1.0', 'end')]
    cm = stub_wsl(H.runs_over_limit())
    calls = cm.__enter__()[0]
    state = {}
    st = H.warn_settings(S)

    def start():
        state['th'] = env.start_disk_warning(st, app._disk_warning, private_ok=True)
        state['t0'] = time.monotonic()
        H.check(f'Tk disk ({"before" if early else "inside"} mainloop): '
                f'private_ok starts the thread', state['th'] is not None)
        root.after(100, wait)

    def wait():
        if state['th'].is_alive() and time.monotonic() - state['t0'] < 15:
            root.after(100, wait)
            return
        root.after(800, verify)

    def verify():
        cm.__exit__(None, None, None)
        log1 = app.run_panel.log.get('1.0', 'end')
        new = log1[len(log0[0].rstrip('\n')):]
        lines = [ln for ln in new.splitlines() if 'WSL runs folder' in ln]
        warns = [n for n in notes if n[1] == 'warn']
        status = str(app._status.cget('text'))
        print('  status:', status, flush=True)
        tag = 'before' if early else 'inside'
        H.check(f'Tk disk ({tag}): exactly one warn-level status notification',
                len(warns) == 1 and len(notes) == 1, str(len(notes)))
        H.check(f'Tk disk ({tag}): status line shows the warning',
                status.startswith('WSL runs folder /root/blastlab_runs holds 15.0 GB'))
        H.check(f'Tk disk ({tag}): exactly one Run-log line', len(lines) == 1,
                str(lines))
        tops = [w for w in root.winfo_children()
                if isinstance(w, tk.Toplevel) and w.winfo_viewable()]
        H.check(f'Tk disk ({tag}): nothing modal (no messagebox, no Toplevel)',
                not modal_calls and not tops, f'{modal_calls} {tops}')
        H.check(f'Tk disk ({tag}): delete_runs never called',
                calls['delete_runs'] == 0, str(calls))
        hwnd[0] = int(root.wm_frame(), 16)
        if not early:
            H.shoot(hwnd[0], 't01_disk_warning_status', lambda: None)
            app._show('run')
            root.after(700, shot_log)
        else:
            root.after(300, close)

    def shot_log():
        H.shoot(hwnd[0], 't02_disk_warning_runlog', lambda: None)
        root.after(200, close)

    def close():
        app.notify = real_notify
        app._on_close()                    # what WM_DELETE_WINDOW runs

    if early:
        # the real app's order: the thread starts in App.__init__, before
        # mainloop; with stubs it finishes in milliseconds (worst case)
        start()
    else:
        root.after(1500, start)
    root.mainloop()
    H.check(f'Tk ({"before" if early else "inside"}): mainloop returned after _on_close',
            True)


if __name__ == '__main__':
    early = len(sys.argv) > 1 and sys.argv[1] == 'early'
    tmp = tempfile.mkdtemp(prefix='blastlab_qa_p05_tk_')
    try:
        main(tmp, early)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [r for r in H.RESULTS if not r[1]]
    print(f'tk{"-early" if early else ""}: {len(H.RESULTS) - len(bad)}/{len(H.RESULTS)} PASS')
    sys.exit(1 if bad else 0)
