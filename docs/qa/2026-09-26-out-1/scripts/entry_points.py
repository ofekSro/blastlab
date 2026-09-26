"""Startup and close through the real entry points, as a user starts them:
`python -m blastlab` (PySide6) and `python -m blastlab --tk`, each in its
own process with the private settings file. The window is found by pid,
grabbed with PrintWindow, closed with WM_CLOSE (the title-bar X), and the
exit code and stderr are recorded.

Then the Tk Runs-folder memory across two processes: process A types a
folder into the box, presses Return and closes through WM_CLOSE; process
B (a fresh `--tk`) is grabbed so the box can be read on screen, and the
settings file is read.

Run:  python -u entry_points.py
"""
import json
import os
import subprocess
import sys
import time


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import qa_common as Q
    Q.private_env()
    Q.set_log('entry_points')
    SHOTS = os.path.join(Q.OUT, 'shots')
    env = dict(os.environ)
    env['BLASTLAB_SETTINGS'] = Q.SETTINGS
    env.pop('QT_QPA_PLATFORM', None)

    def window_of(pid, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            for h, k, t in Q.top_windows(pid):
                if t.startswith('blastlab'):
                    return h, k, t
            time.sleep(0.3)
        return None

    def launch(tag, args, settle=8.0, before_close=None):
        t0 = time.time()
        p = subprocess.Popen([sys.executable, '-m', 'blastlab'] + args,
                             cwd=Q.REPO, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True,
                             encoding='utf-8', errors='replace')
        w = window_of(p.pid)
        t_win = time.time() - t0
        info = dict(tag=tag, args=args, window=bool(w),
                    seconds_to_window=round(t_win, 1))
        if w:
            h, k, t = w
            time.sleep(settle)
            info.update(title=t, cls=k, rect=Q.rect(h))
            shot = f'entry_{tag}_start.png'
            try:
                Q.grab_hwnd(h, os.path.join(SHOTS, shot))
                info['shot'] = shot
            except Exception as exc:
                info['shot_error'] = str(exc)
            if before_close:
                before_close(h, info)
            t1 = time.time()
            Q.user32.PostMessageW(h, Q.WM_CLOSE, 0, 0)
            try:
                out, err = p.communicate(timeout=60)
                info['close_seconds'] = round(time.time() - t1, 1)
            except subprocess.TimeoutExpired:
                p.kill()
                out, err = p.communicate()
                info['close_seconds'] = 'TIMEOUT (killed)'
        else:
            p.kill()
            out, err = p.communicate()
        info.update(returncode=p.returncode, stdout_tail=out[-1500:],
                    stderr_tail=err[-3000:],
                    traceback=('Traceback' in err))
        Q.rec('entry', **info)
        return info

    launch('qt', [])
    launch('tk', ['--tk'])

    # Tk runs folder memory, across processes
    other = os.path.join(Q.RUNS, 'PERSIST_DIR')
    os.makedirs(other, exist_ok=True)
    code = r'''
import os, sys, time
sys.path.insert(0, %r)
import qa_common as Q
Q.private_env()
import customtkinter as ctk
from blastlab.gui import app as gapp
root = ctk.CTk(); app = gapp.App(root)
for _ in range(100): root.update(); time.sleep(0.01)
e = app.run_panel._runs_entry
e.delete(0, 'end'); e.insert(0, %r)
e._entry.focus_force(); root.update()
e._entry.event_generate('<Return>'); root.update()
app.run_panel.run_name.set('SHOULD_NOT_PERSIST')
root.update()
print('BOX', app.run_panel.runs_dir.get())
root.after(300, app._on_close)
root.mainloop()
print('CLOSED')
''' % (os.path.dirname(os.path.abspath(__file__)), other)
    r = subprocess.run([sys.executable, '-c', code], cwd=Q.REPO, env=env,
                       capture_output=True, text=True, timeout=120)
    with open(Q.SETTINGS, encoding='utf-8') as f:
        s = json.load(f)
    Q.rec('tk_persist_a', stdout=r.stdout[-500:], stderr=r.stderr[-800:],
          rc=r.returncode, settings_runs_dir=s.get('runs_dir'),
          auto_cleanup=s.get('auto_cleanup'))
    launch('tk_reopened', ['--tk'], settle=6.0)
    with open(Q.SETTINGS, encoding='utf-8') as f:
        s = json.load(f)
    # put the QA runs folder back for the other scripts
    s['runs_dir'] = Q.RUNS
    with open(Q.SETTINGS, 'w', encoding='utf-8') as f:
        json.dump(s, f, indent=2)


if __name__ == '__main__':
    main()
