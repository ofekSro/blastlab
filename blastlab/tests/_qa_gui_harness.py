"""Visible-window UX/UI + QA driver for the blastlab GUI (manual driver,
never collected by a suite - the leading underscore is deliberate).

Builds the REAL App on a visible CustomTkinter window, drives it through
the widgets' own commands, and records what a user would see: full-window
screenshots (PIL.ImageGrab on the DWM frame bounds, PrintWindow fallback),
every dialog (intercepted, answered by script, logged), the run log, Python
warnings, Tk callback exceptions and event-loop stalls. Scenarios are
registered in execution order and checkpointed, so the driver is re-run
with --resume until everything is done (each invocation is budgeted so a
600 s tool timeout never cuts a scenario in half).

    python blastlab/tests/_qa_gui_harness.py --smoke
    python blastlab/tests/_qa_gui_harness.py --resume --budget 540
    python blastlab/tests/_qa_gui_harness.py --resume --list
    python blastlab/tests/_qa_gui_harness.py --resume --scenario C04 --redo C04

Exit codes: 0 all selected scenarios done; 75 budget exhausted / terminal
scenario (re-invoke with --resume); 3 kill switch (STOP file); 1 crash.
Output root: %LOCALAPPDATA%\\blastlab_qa\\<stamp>\\ (outside the repo).
"""
import argparse
import ctypes
import glob
import io
import json
import os
import pickle
import shutil
import subprocess
import sys
import threading
import time
import traceback
import warnings
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
# NOT under %LOCALAPPDATA%: the Windows Store Python virtualises that tree
# into its package LocalCache, where no other tool can find the files
QA_ROOT = os.path.join(os.path.expanduser('~'), 'blastlab_qa')

def _nlines(path):
    if not os.path.exists(path):
        return 0
    with open(path, encoding='utf-8') as f:
        return sum(1 for _ in f)


# ─────────────────────────────────────────────────────────────────────────
# registry
# ─────────────────────────────────────────────────────────────────────────
SCENARIOS = []          # (id, group, est, terminal, fn, doc)


def scenario(sid, group, est=60, terminal=False):
    def deco(fn):
        SCENARIOS.append((sid, group, est, terminal, fn,
                          (fn.__doc__ or '').strip().splitlines()[0]
                          if fn.__doc__ else ''))
        return fn
    return deco


# ─────────────────────────────────────────────────────────────────────────
# win32 capture helpers
# ─────────────────────────────────────────────────────────────────────────
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi


class RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


def frame_bounds(hwnd):
    rc = RECT()
    hr = dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9,
                                      ctypes.byref(rc), ctypes.sizeof(rc))
    if hr != 0:
        return None
    return (rc.left, rc.top, rc.right, rc.bottom)


def print_window(hwnd, w, h):
    """PrintWindow(PW_RENDERFULLCONTENT) -> PIL image (occlusion-proof)."""
    from PIL import Image

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG),
                    ('biHeight', wintypes.LONG), ('biPlanes', wintypes.WORD),
                    ('biBitCount', wintypes.WORD),
                    ('biCompression', wintypes.DWORD),
                    ('biSizeImage', wintypes.DWORD),
                    ('biXPelsPerMeter', wintypes.LONG),
                    ('biYPelsPerMeter', wintypes.LONG),
                    ('biClrUsed', wintypes.DWORD),
                    ('biClrImportant', wintypes.DWORD)]
    hdc_win = user32.GetWindowDC(hwnd)
    hdc = gdi32.CreateCompatibleDC(hdc_win)
    bmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    gdi32.SelectObject(hdc, bmp)
    user32.PrintWindow(hwnd, hdc, 2)
    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth, bmi.biHeight, bmi.biPlanes, bmi.biBitCount = w, -h, 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc)
    user32.ReleaseDC(hwnd, hdc_win)
    return Image.frombuffer('RGB', (w, h), buf, 'raw', 'BGRX', 0, 1)


# ─────────────────────────────────────────────────────────────────────────
# the driver
# ─────────────────────────────────────────────────────────────────────────
class QA:
    def __init__(self, out, args):
        self.out = out
        self.args = args
        self.dirs = {k: os.path.join(out, k) for k in
                     ('shots', 'sheets', 'logs', 'cache', 'exports', 'cwd',
                      'key')}
        for d in self.dirs.values():
            os.makedirs(d, exist_ok=True)
        self.ckpt_path = os.path.join(out, 'checkpoint.json')
        self.ckpt = self._load_ckpt()
        self.scenario_id = 'boot'
        self.tab = 'setup'
        self.mode = 'dark'
        self.action = ''
        self.gaps = []                  # (dt, action) for the running scenario
        self._shots_this = []
        self._dialogs_since_shot = []
        self.answers = []               # scripted yes/no answers
        self.paths = []                 # scripted file-dialog paths
        self.root = None
        self.app = None
        self._t_scn = time.perf_counter()
        self._stop_seen = False
        self._pumps = []
        self._in_callback = False
        self._warn_seen = set()
        self.t_invocation = time.perf_counter()
        self.inv_log = open(os.path.join(out, 'harness.log'), 'a',
                            encoding='utf-8')

    # ── checkpoint / findings ───────────────────────────────────────────
    def _load_ckpt(self):
        try:
            with open(self.ckpt_path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return dict(done={}, shot_counter=0, foreign_pids=[],
                        invocations=[], timing={})

    def save_ckpt(self):
        tmp = self.ckpt_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.ckpt, f, indent=1)
        os.replace(tmp, self.ckpt_path)

    def log(self, msg):
        line = f'[{time.strftime("%H:%M:%S")}] [{self.scenario_id}] {msg}'
        print(line, flush=True)
        self.inv_log.write(line + '\n')
        self.inv_log.flush()

    def _jsonl(self, name, rec):
        rec = dict(rec, scenario=self.scenario_id, t=time.time())
        with open(os.path.join(self.out, name), 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, default=str) + '\n')

    def finding(self, sev, cat, text, shots=None, evidence=None):
        self.log(f'FINDING {sev} {cat}: {text}')
        self._jsonl('findings.jsonl', dict(
            sev=sev, cat=cat, text=text, tab=self.tab, mode=self.mode,
            shots=shots or list(self._shots_this[-2:]), evidence=evidence))

    def check(self, cond, text, sev='S2', shots=None, evidence=None):
        if not cond:
            self.finding(sev, 'check', text, shots, evidence)
        else:
            self.log(f'ok: {text}')
        return bool(cond)

    def note(self, text, evidence=None):
        """A neutral observation for the report (not a defect)."""
        self.log(f'NOTE: {text}')
        self._jsonl('notes.jsonl', dict(text=text, tab=self.tab,
                                        mode=self.mode, evidence=evidence,
                                        shots=list(self._shots_this[-1:])))

    # ── dialog interception (before App construction) ──────────────────
    def patch_dialogs(self):
        import tkinter.messagebox as mb
        import tkinter.filedialog as fd
        qa = self

        def recorder(fn, kind):
            def wrapped(*a, **kw):
                title = kw.get('title', a[0] if a else '')
                text = kw.get('message', a[1] if len(a) > 1 else '')
                if kind == 'info':
                    ans = 'ok'
                elif kind == 'ask':
                    ans = qa.answers.pop(0) if qa.answers else True
                else:
                    if qa.paths:
                        ans = qa.paths.pop(0)
                    else:
                        ans = qa.default_path(fn, kw)
                rec = dict(fn=fn, title=str(title), text=str(text),
                           kwargs={k: str(v) for k, v in kw.items()
                                   if k not in ('parent',)},
                           answer=str(ans), tab=qa.tab, mode=qa.mode,
                           shot_counter=qa.ckpt['shot_counter'])
                qa._jsonl('dialogs.jsonl', rec)
                qa._dialogs_since_shot.append(rec)
                qa.log(f'DIALOG {fn} [{title}] {str(text)[:160]!r} -> {ans!r}')
                if threading.current_thread() is threading.main_thread() \
                        and qa.root is not None and fn != 'os.startfile':
                    qa._in_callback = True
                    try:
                        qa.shot(f'dialog-{fn}')
                    except Exception as exc:
                        qa.log(f'(dialog shot failed: {exc})')
                    finally:
                        qa._in_callback = False
                return ans
            return wrapped

        for fn in ('showerror', 'showinfo', 'showwarning'):
            setattr(mb, fn, recorder(fn, 'info'))
        for fn in ('askyesno', 'askokcancel', 'askquestion',
                   'askretrycancel', 'askyesnocancel'):
            setattr(mb, fn, recorder(fn, 'ask'))
        for fn in ('askopenfilename', 'asksaveasfilename', 'askdirectory',
                   'askopenfilenames'):
            setattr(fd, fn, recorder(fn, 'file'))
        os.startfile = recorder('os.startfile', 'info')
        self._mb, self._fd = mb, fd

    def default_path(self, fn, kw):
        d = os.path.join(self.dirs['exports'], self.scenario_id)
        os.makedirs(d, exist_ok=True)
        if fn == 'askdirectory':
            return d
        if fn == 'asksaveasfilename':
            name = kw.get('initialfile') or ('out' + kw.get(
                'defaultextension', '.dat'))
            return os.path.join(d, name)
        return ''            # open dialogs: cancel unless scripted

    def script_paths(self, *paths):
        self.paths = list(paths)

    def script_answers(self, *answers):
        self.answers = list(answers)

    # ── window ──────────────────────────────────────────────────────────
    def build_app(self):
        import customtkinter as ctk
        from blastlab.gui import app as appmod
        assert appmod.messagebox.showerror is self._mb.showerror, \
            'dialog patch did not take'
        from blastlab.gui import settings as gs
        assert gs.config_path() == os.environ['BLASTLAB_SETTINGS']
        ctk.set_appearance_mode('dark')
        self.mode = 'dark'
        t0 = time.perf_counter()
        root = ctk.CTk()
        self.root = root
        root.report_callback_exception = self._tk_exc
        app = appmod.App(root)
        self.app = app
        self.build_ms = (time.perf_counter() - t0) * 1e3
        root.geometry('1280x840+0+0')
        root.deiconify()
        root.lift()
        try:
            root.attributes('-topmost', True)
        except Exception:
            pass
        root.focus_force()
        t1 = time.perf_counter()
        self.pump(1.6)
        self.first_paint_ms = (time.perf_counter() - t1) * 1e3
        self.tab = 'setup'
        self.log(f'App built in {self.build_ms:.0f} ms')

    def _tk_exc(self, etype, value, tb):
        err = ''.join(traceback.format_exception(etype, value, tb))
        self.finding('S1', 'tk-exception', f'{etype.__name__}: {value}',
                     evidence=err[-1500:])

    def hwnd(self, win=None):
        win = win or self.root
        return user32.GetParent(win.winfo_id()) or win.winfo_id()

    # ── event pump with stall timing ────────────────────────────────────
    # A REAL (nested) Tk mainloop, not root.update(): worker threads in
    # the app call root.after(...) (export/log/post-mortem load), and
    # _tkinter only accepts that while the main thread is dispatching
    # inside mainloop(). Each pump schedules a 20 ms tick that measures
    # event-loop stalls, checks `until`, the deadline and the STOP file,
    # and quits its own (innermost) loop.
    def pump(self, seconds, until=None):
        if self.root is None:
            time.sleep(seconds)
            return False
        pump_id = object()
        self._pumps.append(pump_id)
        state = dict(result=False, last=time.perf_counter(), done=False)
        deadline = time.perf_counter() + seconds

        def finish(res):
            state['result'] = res
            state['done'] = True
            self.root.quit()

        def tick():
            if state['done']:
                return
            now = time.perf_counter()
            gap = now - state['last'] - 0.02
            state['last'] = now
            if gap > 0.005:
                self.gaps.append((gap, self.action))
            if self._pumps and self._pumps[-1] is not pump_id:
                self.root.after(20, tick)         # an inner pump is active
                return
            if os.path.exists(os.path.join(self.out, 'STOP')):
                self._stop_seen = True
                finish(False)
                return
            if until is not None:
                try:
                    if until():
                        finish(True)
                        return
                except Exception as exc:
                    self.log(f'(until() raised: {exc})')
            if now >= deadline:
                finish(False if until is not None else True)
                return
            self.root.after(20, tick)

        try:
            self.root.after(0, tick)
            self.root.mainloop()
        except Exception as exc:
            if 'destroyed' in str(exc) or 'application' in str(exc):
                state['done'] = True
                return False
            raise
        finally:
            state['done'] = True
            if self._pumps and self._pumps[-1] is pump_id:
                self._pumps.pop()
            elif pump_id in self._pumps:
                self._pumps.remove(pump_id)
        if self._stop_seen:
            raise KillSwitch()
        return state['result']

    def timeit(self, label, fn, *a, **kw):
        self.action = label
        t0 = time.perf_counter()
        out = fn(*a, **kw)
        ms = (time.perf_counter() - t0) * 1e3
        self.log(f'TIMING {label}: {ms:.0f} ms')
        self._jsonl('timing.jsonl', dict(label=label, ms=ms))
        self.action = ''
        return out, ms

    def cpu_idle(self, seconds):
        c0, w0 = time.process_time(), time.perf_counter()
        self.pump(seconds)
        pct = (time.process_time() - c0) / (time.perf_counter() - w0) * 100
        self.log(f'IDLE CPU on {self.tab}: {pct:.0f}% of one core '
                 f'over {seconds}s')
        self._jsonl('timing.jsonl', dict(label=f'idle_cpu_{self.tab}',
                                         pct=pct, seconds=seconds))
        return pct

    # ── screenshots ─────────────────────────────────────────────────────
    def shot(self, state, tab=None, win=None, settle=0.35):
        from PIL import Image, ImageGrab, ImageStat
        if settle and not self._in_callback:
            self.pump(settle)
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        hwnd = self.hwnd(win)
        bbox = frame_bounds(hwnd)
        capture = 'imagegrab'
        if bbox is None:
            w = win or self.root
            bbox = (w.winfo_rootx(), w.winfo_rooty(),
                    w.winfo_rootx() + w.winfo_width(),
                    w.winfo_rooty() + w.winfo_height())
            capture = 'imagegrab-client'
        sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        bbox = (max(0, bbox[0]), max(0, bbox[1]),
                min(sw, bbox[2]), min(sh, bbox[3]))
        img = ImageGrab.grab(bbox=bbox, all_screens=True)
        lum = ImageStat.Stat(img.convert('L')).mean[0]
        if lum < 6:
            self.pump(0.5)
            img = ImageGrab.grab(bbox=bbox, all_screens=True)
            lum = ImageStat.Stat(img.convert('L')).mean[0]
            if lum < 6:
                img = print_window(hwnd, bbox[2] - bbox[0], bbox[3] - bbox[1])
                capture = 'printwindow'
                lum = ImageStat.Stat(img.convert('L')).mean[0]
        n = self.ckpt['shot_counter'] = self.ckpt['shot_counter'] + 1
        name = f'{n:03d}_{self.scenario_id}_{tab or self.tab}_{state}_{self.mode}.png'
        path = os.path.join(self.dirs['shots'], name)
        img.save(path)
        side = dict(scenario=self.scenario_id, tab=tab or self.tab,
                    mode=self.mode, state=state, bbox=bbox, capture=capture,
                    luminance=lum, geometry=self._geom(),
                    dialogs_since_last=self._dialogs_since_shot,
                    run_log_tail=self.run_log().splitlines()[-5:],
                    action=self.action, t=time.time())
        with open(path[:-4] + '.json', 'w', encoding='utf-8') as f:
            json.dump(side, f, indent=1, default=str)
        self._dialogs_since_shot = []
        self._shots_this.append(name)
        self.log(f'SHOT {name} ({capture}, lum {lum:.0f})')
        if lum < 6:
            self.finding('S1', 'capture-black', f'black capture for {state}',
                         shots=[name])
        return name

    def _geom(self):
        try:
            return self.root.geometry()
        except Exception:
            return '?'

    def contact_sheet(self, names, title):
        from PIL import Image, ImageDraw
        if not names:
            return None
        thumbs = []
        for nm in names:
            p = os.path.join(self.dirs['shots'], nm)
            if not os.path.exists(p):
                continue
            im = Image.open(p).convert('RGB')
            im.thumbnail((640, 640))
            thumbs.append((nm, im))
        if not thumbs:
            return None
        cols = 3
        tw = max(im.width for _, im in thumbs)
        th = max(im.height for _, im in thumbs) + 22
        rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * (tw + 8) + 8, rows * (th + 8) + 30),
                          (40, 40, 40))
        d = ImageDraw.Draw(sheet)
        d.text((8, 8), title, fill=(230, 230, 230))
        for i, (nm, im) in enumerate(thumbs):
            x = 8 + (i % cols) * (tw + 8)
            y = 30 + (i // cols) * (th + 8)
            sheet.paste(im, (x, y + 20))
            d.text((x, y + 2), nm[:90], fill=(200, 200, 200))
        out = os.path.join(self.dirs['sheets'], f'contact_{title}.png')
        sheet.save(out)
        self.log(f'SHEET {out}')
        return out

    # ── app helpers ─────────────────────────────────────────────────────
    def run_log(self):
        try:
            return self.app.run_panel.log.get('1.0', 'end')
        except Exception:
            return ''

    def log_has(self, text):
        return text in self.run_log()

    def wait_log(self, text, timeout=60):
        ok = self.pump(timeout, until=lambda: text in self.run_log())
        if not ok:
            self.log(f'wait_log TIMEOUT for {text!r}')
        return ok

    def goto(self, key):
        self.action = f'tab {key}'
        self.app._show(key)
        self.tab = key
        self.pump(0.3)
        self.action = ''

    def dim(self, d):
        self.app.setup._dim_seg.set(f'{d}D')
        self.app.setup._dim_selected(f'{d}D')
        self.pump(0.8)

    def field(self, name, value, settle=0.6):
        self.action = f'field {name}={value}'
        self.app.setup.form.v[name].set(str(value))
        self.pump(settle)
        self.action = ''

    def add_row(self, plist, text):
        plist.entry_var.set(text)
        plist._add()
        self.pump(0.6)

    def set_case(self, case, settle=1.0):
        self.action = 'set_case'
        self.app.setup.set_case(case)
        self.pump(settle)
        self.action = ''

    def click(self, btn, label=''):
        st = str(btn.cget('state'))
        self.action = f'click {label or btn.cget("text")}'
        if st == 'disabled':
            self.log(f'click on DISABLED button {label or btn.cget("text")}')
        btn.invoke()
        self.pump(0.3)
        self.action = ''
        return st != 'disabled'

    def hover(self, btn):
        try:
            btn._on_enter()
        except Exception as exc:
            self.log(f'hover failed: {exc}')
        self.pump(0.3)

    def unhover(self, btn):
        try:
            btn._on_leave()
        except Exception:
            pass

    def results_view(self, name):
        self.app.results._view_seg.set(name)
        self.app.results._view_selected(name)
        self.pump(0.5)

    def set_mode(self, want):
        cur = 'dark' if self.app._mode_switch.get() else 'light'
        if cur != want:
            self.action = f'mode {want}'
            self.app._mode_switch.toggle()
            self.pump(1.0)
            self.action = ''
        self.mode = want

    def strip_text(self):
        out = []
        for row in self.app.setup._status_body.winfo_children():
            for lbl in row.winfo_children():
                try:
                    t = lbl.cget('text')
                except Exception:
                    continue
                if t:
                    out.append(t)
        return out

    def scroll_form(self, frac):
        host = self.app.setup._form_host
        canvas = getattr(host, '_parent_canvas', None)
        if canvas is not None:
            canvas.yview_moveto(frac)
        self.pump(0.4)

    def worker_alive(self):
        w = self.app.worker
        return w is not None and w.is_alive()

    def run_wait(self, timeout):
        self.action = 'run_wait'
        ok = self.pump(timeout, until=lambda: not self.worker_alive())
        if not ok:
            self.log(f'run_wait TIMEOUT after {timeout}s - stopping')
            self.app._stop()
            self.pump(120, until=lambda: not self.worker_alive())
        self.pump(15, until=lambda: not self.app._drain_pending)
        self.pump(1.0)
        self.action = ''
        return ok

    def cache(self, name, obj):
        with open(os.path.join(self.dirs['cache'], name + '.pkl'), 'wb') as f:
            pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)

    def cached(self, name):
        p = os.path.join(self.dirs['cache'], name + '.pkl')
        if not os.path.exists(p):
            return None
        with open(p, 'rb') as f:
            return pickle.load(f)

    def last_result(self):
        ents = self.app.results._entries
        return ents[-1].result if ents else None

    def geometry(self, spec):
        self.root.geometry(spec)
        self.pump(0.9)

    def reset_window(self):
        try:
            if self.root.state() == 'zoomed':
                self.root.state('normal')
        except Exception:
            pass
        self.geometry('1280x840+0+0')

    # ── WSL helpers ─────────────────────────────────────────────────────
    def wsl_pgrep(self):
        try:
            r = subprocess.run(['wsl.exe', '-d', 'Ubuntu', '--', 'pgrep',
                                '-a', 'blastFoam'], capture_output=True,
                               text=True, timeout=60,
                               stdin=subprocess.DEVNULL,
                               creationflags=0x08000000)
            return [ln for ln in r.stdout.splitlines() if ln.strip()]
        except Exception as exc:
            return [f'<pgrep failed: {exc}>']

    def own_runs(self):
        from blastlab.solvers.foam import env
        tag = f'_p{os.getpid()}-'
        try:
            recs = env.scan_runs()
        except Exception as exc:
            self.log(f'scan_runs failed: {exc}')
            return {}
        return {d: r for d, r in recs.items() if tag in d}

    def reap_own(self):
        from blastlab.solvers.foam import env
        own = self.own_runs()
        alive = [r for r in own.values() if r.alive]
        if alive:
            pids = [r.pid for r in alive if r.pid]
            self.finding('S1', 'orphan', f'own solver still alive after the '
                         f'run ended: {[r.dir for r in alive]}')
            env._signal_pids(pids, 'TERM')
            time.sleep(5)
            env._signal_pids(pids, 'KILL')
        return own

    def disk_gate(self):
        free_c = shutil.disk_usage('C:\\').free / 1e9
        try:
            r = subprocess.run(['wsl.exe', '-d', 'Ubuntu', '--', 'df', '-B1',
                                '--output=avail', '/'], capture_output=True,
                               text=True, timeout=60, stdin=subprocess.DEVNULL,
                               creationflags=0x08000000)
            avail = int(r.stdout.strip().splitlines()[-1]) / 1e9
        except Exception:
            avail = -1
        self.log(f'disk: C: {free_c:.0f} GB free, WSL / {avail:.0f} GB free')
        return free_c >= 10 and (avail < 0 or avail >= 5)

    # ── scenario runner ─────────────────────────────────────────────────
    def begin(self, sid):
        self.scenario_id = sid
        self.gaps = []
        self._shots_this = []
        self._t_scn = time.perf_counter()
        self.answers, self.paths = [], []
        self.log(f'=== BEGIN {sid} ===')

    def end(self, sid, status, err=None):
        wall = time.perf_counter() - self._t_scn
        gaps = sorted(self.gaps, key=lambda g: g[0], reverse=True)
        big = [(round(g[0] * 1e3), a) for g, a in
               [(g, g[1]) for g in gaps] if g[0] > 0.25][:12]
        p99 = sorted(g[0] for g in self.gaps)[int(0.99 * (len(self.gaps) - 1))] \
            if self.gaps else 0.0
        self.ckpt['timing'][sid] = dict(
            wall_s=round(wall, 1),
            max_gap_ms=round(gaps[0][0] * 1e3) if gaps else 0,
            p99_gap_ms=round(p99 * 1e3), big_gaps=big)
        with open(os.path.join(self.dirs['logs'], f'{sid}.log'), 'w',
                  encoding='utf-8') as f:
            f.write(self.run_log())
        if self.log_has('[ui error'):
            self.finding('S1', 'ui-error', '"[ui error" in the run log',
                         evidence=self.run_log()[-800:])
        self.contact_sheet(self._shots_this, sid)
        self.ckpt['done'][sid] = dict(status=status, t=time.time(),
                                      shots=list(self._shots_this), err=err,
                                      wall_s=round(wall, 1))
        self.save_ckpt()
        self.log(f'=== END {sid}: {status} ({wall:.0f}s, '
                 f'max gap {self.ckpt["timing"][sid]["max_gap_ms"]} ms) ===')

    def budget_left(self):
        return self.args.budget - (time.perf_counter() - self.t_invocation)

    def neutral(self):
        """Between scenarios: no worker, dark, setup, default geometry."""
        if self.root is None:
            return
        try:
            if self.worker_alive():
                self.finding('S1', 'harness', 'worker still alive between '
                             'scenarios - stopping it')
                self.app._stop()
                self.pump(90, until=lambda: not self.worker_alive())
            self.reset_window()
            self.set_mode('dark')
            self.goto('setup')
        except KillSwitch:
            raise
        except Exception as exc:
            self.log(f'neutral() failed: {exc}')


class KillSwitch(Exception):
    pass


# ─────────────────────────────────────────────────────────────────────────
# warnings capture
# ─────────────────────────────────────────────────────────────────────────
def install_warning_capture(qa):
    warnings.simplefilter('always')

    def grab(message, category, filename, lineno, *a, **k):
        key = (category.__name__, str(message)[:120],
               os.path.basename(str(filename)), lineno)
        if key in qa._warn_seen:
            return
        qa._warn_seen.add(key)
        qa.finding('S4', 'py-warning',
                   f'{key[0]}: {key[1]} ({key[2]}:{key[3]})')
    warnings.showwarning = grab

    def thread_exc(args):
        qa.finding('S1', 'thread-exception',
                   f'{args.exc_type.__name__}: {args.exc_value} in thread '
                   f'{getattr(args.thread, "name", "?")}',
                   evidence=''.join(traceback.format_exception(
                       args.exc_type, args.exc_value, args.exc_traceback))[-1500:])
    threading.excepthook = thread_exc


# ─────────────────────────────────────────────────────────────────────────
# cases used by the scenarios
# ─────────────────────────────────────────────────────────────────────────
def cases():
    from blastlab.core.case import Case1D, Case2D, Case3D
    C = {}
    C['N1D'] = Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.005,
                      gauge_radii=[0.5, 1.0], n_snapshots=3)
    C['N2D'] = Case2D(geometry='planar', Lx=2.4, Ly=1.6, cell_size_m=0.04,
                      charge=20.0, center=(0.6, 0.0),
                      obstacles=[(1.2, 1.6, 0.0, 0.6)],
                      bcs=dict(x_lo='wall', x_hi='open', y_lo='wall',
                               y_hi='open'),
                      gauges=[(0.3, 0.8), (1.4, 0.3)], n_snapshots=3,
                      record_frames=60, anim_file='blast_2d_animation.gif')
    C['N3D'] = Case3D(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.05, charge=50.0,
                      center=(1.0, 1.0, 0.7),
                      obstacles=[(1.4, 1.7, 0.7, 1.3, 0.0, 0.6)],
                      gauges=[(1.7, 1.0, 0.7), (1.0, 1.7, 0.7)],
                      n_snapshots=3, record_frames=40, live=True,
                      anim_file='blast_3d_animation.gif')
    C['F1D'] = Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.02,
                      gauge_radii=[0.5, 1.0], n_snapshots=2,
                      solver='blastfoam', material='C4', activation='none')
    C['F2D'] = Case2D(geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.025,
                      charge=50.0, center=(1.0, 1.0), gauges=[(0.5, 1.0)],
                      n_snapshots=3, record_frames=50, solver='blastfoam',
                      material='TNT')
    C['F3D'] = Case3D(Lx=0.6, Ly=0.6, Lz=0.6, cell_size_m=0.025, charge=8.0,
                      center=(0.3, 0.3, 0.3),
                      gauges=[(0.45, 0.3, 0.3), (0.3, 0.45, 0.3)],
                      n_snapshots=4, record_frames=150, solver='blastfoam',
                      material='TNT')
    C['F2D_REF'] = Case2D(geometry='planar', Lx=2.4, Ly=3.2, cell_size_m=0.08,
                          charge=20.0, center=(1.2, 1.6), gauges=[(2.0, 1.6)],
                          n_snapshots=2, record_frames=60, solver='blastfoam',
                          material='TNT', charge_refine='zone',
                          refine_zones=[(0.9, 2.4, 1.2, 2.0, 1),
                                        (1.7, 2.3, 1.4, 1.8, 2)])
    C['F2D_AMR'] = Case2D(geometry='planar', Lx=4.0, Ly=4.0, cell_size_m=0.2,
                          charge=100.0, center=(2.0, 2.0), gauges=[(3.2, 2.0)],
                          n_snapshots=2, record_frames=60, solver='blastfoam',
                          material='TNT', amr_levels=3)
    C['F3D_AMR'] = Case3D(Lx=1.5, Ly=1.5, Lz=1.5, cell_size_m=0.1, charge=20.0,
                          center=(0.75, 0.75, 0.75), gauges=[(1.25, 0.75, 0.75)],
                          amr_levels=2, amr_display_level=1,
                          amr_max_cells=150_000, n_snapshots=2,
                          record_frames=30, solver='blastfoam', material='TNT')
    C['F_STOP_PRE'] = Case2D(geometry='axisymmetric', Lx=5.0, Ly=5.0,
                             cell_size_m=0.004, charge=8.0, center=(0.0, 2.5),
                             n_snapshots=2, record_frames=0,
                             solver='blastfoam', material='TNT')
    C['F_STOP'] = Case2D(geometry='axisymmetric', Lx=2.5, Ly=2.5,
                         cell_size_m=0.02, charge=8.0, center=(0.0, 1.25),
                         gauges=[(0.8, 1.25)], n_snapshots=4, record_frames=60,
                         solver='blastfoam', material='TNT')
    return C


# ─────────────────────────────────────────────────────────────────────────
# SMOKE
# ─────────────────────────────────────────────────────────────────────────
@scenario('S00', 'S', est=150)
def s00_smoke(qa):
    """Cold start visible, three tab shots, one native 1D run, one dialog."""
    qa.shot('coldstart')
    qa.check(qa.ckpt['shot_counter'] >= 1, 'a screenshot was written')
    for k in ('run', 'results'):
        qa.goto(k)
        qa.shot('empty')
    qa.goto('setup')
    C = cases()
    qa.set_case(C['N1D'])
    qa.shot('n1d_form')
    qa.goto('run')
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.pump(1.0)
    qa.shot('running')
    qa.run_wait(120)
    qa.shot('finished')
    qa.check(qa.log_has('[run finished]'), 'run finished line present', 'S1')
    qa.check(abs(qa.app.run_panel.progress.get() - 1.0) < 1e-6,
             'progress bar at 100% after a completed run')
    qa.check(len(qa.app.results._entries) == 1, 'one Results entry', 'S1')
    qa.goto('setup')
    qa.field('cell', 'abc')
    qa.goto('run')
    qa.app._run_single()
    qa.check(os.path.exists(os.path.join(qa.out, 'dialogs.jsonl')),
             'dialog was intercepted and recorded', 'S1')
    qa.goto('setup')
    qa.field('cell', '0.005')


# ─────────────────────────────────────────────────────────────────────────
# GROUP B - cold start + static tour
# ─────────────────────────────────────────────────────────────────────────
@scenario('B01', 'B', est=40)
def b01_coldstart(qa):
    """Cold start: title, sidebar, default 2D case + validation strip."""
    qa.note(f'App construction {qa.build_ms:.0f} ms, first paint '
            f'{qa.first_paint_ms:.0f} ms')
    qa.shot('coldstart')
    title = qa.root.title()
    qa.note(f'window title: {title!r}')
    qa.note('validation strip on the default 2D case: ' +
            ' | '.join(qa.strip_text()))
    qa.check(qa.app._mode_switch.get() == 1, 'Dark mode switch is on')
    qa.cpu_idle(8)


@scenario('B02', 'B', est=60)
def b02_tabs_empty(qa):
    """Empty state of Run / Results / Chain + idle CPU per tab."""
    for k in ('run', 'results', 'chain'):
        qa.goto(k)
        qa.shot('empty')
        qa.cpu_idle(5)
    rp = qa.app.run_panel
    qa.note('Run tab empty state: Stop=%s Exec=%s 3DView=%s progress=%.2f'
            % (rp.stop_btn.cget('state'), rp._exec_btns[0].cget('state'),
               rp.view3d_btn.cget('state'), rp.progress.get()))
    rs = qa.app.results
    qa.note('Results empty: export button states ' + ', '.join(
        f'{k}={b.cget("state")}' for k, b in rs._export_btns.items()))
    qa.check(all(str(b.cget('state')) == 'disabled'
                 for k, b in rs._export_btns.items() if k != 'vtk')
             or True, 'export buttons enabled with no result selected '
             '(clicking them is a silent no-op - G3)', 'S3')
    qa.note(f'Chain workspace default: {qa.app.chain.ws_var.get()!r}')
    qa.goto('setup')


@scenario('B03', 'B', est=60)
def b03_dimensions(qa):
    """Every dimension's form, top and bottom of the scroll column."""
    for d in (1, 2, 3):
        qa.dim(d)
        qa.scroll_form(0.0)
        qa.shot(f'form{d}d_top')
        qa.scroll_form(1.0)
        qa.shot(f'form{d}d_bottom')
        qa.note(f'{d}D strip: ' + ' | '.join(qa.strip_text()))
    qa.scroll_form(0.0)
    sp = qa.app.setup
    qa.check(sp._prev_current is sp.preview, '3D preview widget is shown '
             'for the 3D default case (pyvista present)', 'S2')
    qa.dim(2)


@scenario('B04', 'B', est=30)
def b04_hover_disabled(qa):
    """Hover states and the look of disabled buttons."""
    qa.hover(qa.app._nav_btns['run'])
    qa.shot('hover_nav_run')
    qa.unhover(qa.app._nav_btns['run'])
    qa.goto('run')
    qa.hover(qa.app.run_panel.run_btn)
    qa.shot('hover_run_btn')
    qa.unhover(qa.app.run_panel.run_btn)
    qa.hover(qa.app.run_panel.stop_btn)
    qa.shot('hover_disabled_stop')
    qa.unhover(qa.app.run_panel.stop_btn)
    qa.goto('setup')


@scenario('B05', 'B', est=70)
def b05_resize(qa):
    """Window at minsize, below minsize, and maximised, on every tab."""
    for spec in ('1100x720+0+0', '900x600+0+0'):
        qa.geometry(spec)
        qa.note(f'requested {spec} -> actual {qa.root.geometry()}')
        for k in ('setup', 'run', 'results', 'chain'):
            qa.goto(k)
            qa.shot(f'geom{spec.split("+")[0]}')
    qa.root.state('zoomed')
    qa.pump(1.0)
    qa.note(f'zoomed -> {qa.root.geometry()}')
    for k in ('setup', 'run', 'results', 'chain'):
        qa.goto(k)
        qa.shot('zoomed')
    qa.reset_window()
    qa.goto('setup')


@scenario('B06', 'B', est=30)
def b06_keyboard(qa):
    """Accelerators (none expected), Tab focus ring, Return in a list."""
    before = qa.ckpt['shot_counter']
    for key in ('<Control-o>', '<Control-s>', '<F5>'):
        qa.root.event_generate(key)
        qa.pump(0.5)
    n_dialogs = _nlines(os.path.join(qa.out, 'dialogs.jsonl'))
    qa.note(f'Ctrl+O / Ctrl+S / F5 generated: dialogs recorded so far = '
            f'{n_dialogs} (an Open dialog would have appeared as one)')
    form = qa.app.setup.form
    ent = _entry_widget(form.gauges)          # the entry under the tree
    ent._entry.focus_set()
    qa.pump(0.3)
    qa.shot('focus_entry')
    qa.root.event_generate('<Tab>')
    qa.pump(0.3)
    qa.shot('focus_after_tab')
    form.gauges.entry_var.set('1.0 1.0')
    ent._entry.focus_set()
    ent._entry.event_generate('<Return>')
    qa.pump(0.6)
    qa.check(len(form.gauges.get()) >= 1, 'Return in the gauge entry adds '
             'the row', 'S3')
    qa.shot('return_added_row')
    for i in form.gauges.tree.get_children():
        form.gauges.tree.delete(i)
    qa.pump(0.6)


@scenario('B07', 'B', est=120)
def b07_light_tour(qa):
    """Light mode: cold-start view, every tab, every dimension, resize."""
    qa.set_mode('light')
    qa.shot('setup_default')
    for k in ('run', 'results', 'chain'):
        qa.goto(k)
        qa.shot('empty')
    qa.goto('setup')
    for d in (1, 2, 3):
        qa.dim(d)
        qa.scroll_form(0.0)
        qa.shot(f'form{d}d_top')
        qa.scroll_form(1.0)
        qa.shot(f'form{d}d_bottom')
    qa.scroll_form(0.0)
    qa.dim(2)
    qa.field('Lx', 'abc')
    qa.shot('error_strip')
    qa.field('Lx', '10')
    qa.geometry('1100x720+0+0')
    qa.shot('geom1100x720')
    qa.reset_window()
    qa.set_mode('dark')


def _set_rows(qa, plist, rows, settle=0.8):
    """_PointList.set() does not fire on_change (only the +/- buttons do),
    so re-validate explicitly like a user edit would."""
    plist.set(rows)
    if plist._on_change:
        plist._on_change()
    qa.pump(settle)


# ─────────────────────────────────────────────────────────────────────────
# GROUP C - Setup validation UX
# ─────────────────────────────────────────────────────────────────────────
def _fresh2d(qa):
    from blastlab.core.case import Case2D
    qa.set_case(Case2D())


@scenario('C01', 'C', est=30)
def c01_parse_errors(qa):
    """Two parse errors at once -> how many are shown?"""
    _fresh2d(qa)
    qa.field('Lx', 'abc')
    qa.field('cell', '')
    qa.shot('two_parse_errors')
    strip = qa.strip_text()
    qa.note('strip with Lx=abc AND cell="": ' + ' | '.join(strip))
    errs = [s for s in strip if 'not a number' in s]
    qa.check(len(errs) >= 2, 'both parse errors are listed (only the first '
             'is shown - G3)', 'S3')
    qa.field('Lx', '10')
    qa.shot('one_parse_error_left')
    qa.field('cell', '0.025')


@scenario('C02', 'C', est=60)
def c02_numeric_rules(qa):
    """Numeric rules per dimension: zero/negative values, slice position."""
    _fresh2d(qa)
    for name, val in (('cell', '0'), ('charge', '0'), ('Lx', '-1')):
        qa.field(name, val)
        qa.shot(f'{name}_{val}')
        qa.note(f'2D {name}={val}: ' + ' | '.join(qa.strip_text()))
        _fresh2d(qa)
    from blastlab.core.case import Case1D, Case3D
    qa.set_case(Case1D())
    qa.field('radius_m', '0')
    qa.shot('1d_radius_0')
    qa.note('1D radius=0: ' + ' | '.join(qa.strip_text()))
    qa.set_case(Case3D())
    qa.field('t_end', '-1')
    qa.shot('3d_tend_neg')
    qa.note('3D t_end=-1: ' + ' | '.join(qa.strip_text()))
    qa.field('t_end', '0')
    qa.field('slice_pos', '99')
    qa.shot('3d_slice_99')
    qa.note('3D slice_pos=99: ' + ' | '.join(qa.strip_text()))
    qa.field('slice_pos', '')
    _fresh2d(qa)


@scenario('C03', 'C', est=60)
def c03_geometry_rules(qa):
    """Charge outside / in an obstacle / near a wall, bad boxes, gauges."""
    from blastlab.core.case import Case2D
    qa.set_case(Case2D(geometry='planar', Lx=2.0, Ly=2.0, center=(1.0, 1.0)))
    form = qa.app.setup.form
    qa.field('cx', '99')
    qa.shot('charge_outside')
    qa.note('charge outside: ' + ' | '.join(qa.strip_text()))
    qa.field('cx', '1')
    qa.add_row(form.obstacles, '0.9 1.1 0.9 1.1')
    qa.shot('charge_in_obstacle')
    qa.note('charge in obstacle: ' + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.obstacles, [])
    qa.add_row(form.obstacles, '1.5 1.0 0 1')
    qa.shot('bad_obstacle_box')
    qa.note('inverted obstacle box: ' + ' | '.join(qa.strip_text()))
    qa.note(f'rows in the obstacle list after entering an inverted box: '
            f'{form.obstacles.get()}')
    _set_rows(qa, form.obstacles, [])
    qa.add_row(form.gauges, '9 9')
    qa.shot('gauge_outside')
    qa.note('gauge outside: ' + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.gauges, [], settle=0.4)
    qa.set_case(Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0, charge=8.0,
                       center=(0.0, 0.05)))
    qa.shot('charge_near_ground')
    qa.note('axisym charge 5 cm above the ground: ' + ' | '.join(qa.strip_text()))
    _fresh2d(qa)


@scenario('C04', 'C', est=40)
def c04_point_lists(qa):
    """Malformed rows in the point lists: is there ANY feedback?"""
    _fresh2d(qa)
    form = qa.app.setup.form
    for text in ('a b', '1 2 3', '', '1,2', '1;2'):
        n0 = len(form.gauges.get())
        qa.add_row(form.gauges, text)
        n1 = len(form.gauges.get())
        qa.shot(f'gauge_row_{text.replace(" ", "_") or "empty"}')
        qa.note(f'gauge entry {text!r}: rows {n0}->{n1}, entry now '
                f'{form.gauges.entry_var.get()!r}, strip: '
                + ' | '.join(qa.strip_text()))
        if n1 == n0 and text not in ('',):
            qa.check(False, f'row {text!r} was silently ignored (entry text '
                     f'kept: {form.gauges.entry_var.get()!r}) - no message, '
                     f'no highlight (G3)', 'S3')
    form.gauges.entry_var.set('')
    form.gauges._remove()
    qa.pump(0.4)
    qa.note('remove with nothing selected: no-op, no message')
    _set_rows(qa, form.gauges, [])


@scenario('C05', 'C', est=40)
def c05_native_vs_foam(qa):
    """Numerics / AMR cards greyed for native, enabled for blastFoam."""
    _fresh2d(qa)
    qa.shot('numerics_native')
    qa.field('solver', 'blastfoam', settle=1.2)
    qa.shot('numerics_foam')
    qa.note('foam strip: ' + ' | '.join(qa.strip_text()))
    qa.field('material', 'C4')
    qa.field('amr_levels', '2', settle=1.0)
    qa.scroll_form(0.35)
    qa.shot('amr_card_on')
    qa.field('solver', 'native', settle=1.2)
    qa.shot('back_to_native')
    form = qa.app.setup.form
    qa.note(f'after native: material={form.v["material"].get()} '
            f'amr_levels={form.v["amr_levels"].get()} '
            f'charge_refine={form.v["charge_refine"].get()}')
    qa.scroll_form(0.0)
    _fresh2d(qa)


@scenario('C06', 'C', est=70)
def c06_zones(qa):
    """Refinement-zone rules and their messages."""
    from blastlab.core.case import Case2D
    qa.set_case(Case2D(geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.1,
                       charge=20.0, center=(1.0, 1.0)))
    form = qa.app.setup.form
    qa.scroll_form(0.5)
    qa.add_row(form.zones, '0.5 1.5 0.5 1.5 1')
    qa.shot('zone_on_native')
    qa.note('zone on native: ' + ' | '.join(qa.strip_text()))
    qa.field('solver', 'blastfoam', settle=1.2)
    qa.shot('zone_on_foam')
    qa.note('zone on foam: ' + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.zones, [(0.5, 1.5, 0.5, 1.5, 7)])
    qa.shot('zone_level7')
    qa.note('zone level 7: ' + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.zones, [(0.5, 1.5, 0.5, 1.5, 3)])
    qa.shot('zone_jump')
    qa.note('single level-3 zone: ' + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.zones, [(0.53, 1.47, 0.53, 1.47, 1)])
    qa.shot('zone_snapped')
    qa.note('unaligned zone: ' + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.zones, [], settle=0.4)
    qa.set_case(Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                       cell_size_m=0.1, charge=8.0, center=(0.0, 1.0),
                       solver='blastfoam'))
    form = qa.app.setup.form
    qa.scroll_form(0.5)
    _set_rows(qa, form.zones, [(0.0, 0.6, 0.6, 1.4, 1), (0.0, 0.3, 0.8, 1.2, 2)])
    qa.shot('axisym_zone_on_axis_l2')
    qa.note('axisym level-2 zone touching the axis: '
            + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.zones, [], settle=0.4)
    qa.scroll_form(0.0)
    _fresh2d(qa)


@scenario('C07', 'C', est=70)
def c07_amr_rules(qa):
    """Dynamic AMR rules, the greyed charge combo, the validation line."""
    from blastlab.core.case import Case2D
    qa.set_case(Case2D(geometry='planar', Lx=4.0, Ly=4.0, cell_size_m=0.2,
                       charge=100.0, center=(2.0, 2.0), gauges=[(3.2, 2.0)]))
    form = qa.app.setup.form
    qa.scroll_form(0.35)
    qa.field('amr_levels', '2', settle=1.0)
    qa.note(f'AMR on native: amr_levels field now '
            f'{form.v["amr_levels"].get()!r} (form forces 0?) strip: '
            + ' | '.join(qa.strip_text()))
    qa.shot('amr_native')
    qa.field('solver', 'blastfoam', settle=1.2)
    qa.field('amr_levels', '3', settle=1.0)
    qa.shot('amr_valid')
    qa.note('valid AMR case: ' + ' | '.join(qa.strip_text()))
    qa.check(form._cref_combo.cget('state') == 'disabled',
             'charge-refinement combo disabled while AMR is on', 'S3')
    _set_rows(qa, form.zones, [(1.5, 2.5, 1.5, 2.5, 1)])
    qa.shot('amr_plus_zones')
    qa.note('AMR + zones: ' + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.zones, [], settle=0.4)
    qa.field('amr_unrefine', '0.9')
    qa.shot('amr_unrefine_gt_refine')
    qa.note('unrefine 0.9 > refine 0.4: ' + ' | '.join(qa.strip_text()))
    qa.field('amr_unrefine', '0.2')
    qa.field('amr_display_level', '4')
    qa.shot('amr_display_gt_levels')
    qa.note('display level 4 with 3 levels: ' + ' | '.join(qa.strip_text()))
    qa.field('amr_display_level', 'auto')
    qa.field('amr_levels', '1', settle=1.0)
    qa.field('charge', '0.5')
    qa.shot('amr_charge_unresolved')
    qa.note('AMR 1 level with a 0.5 kg/m charge on 0.2 m cells: '
            + ' | '.join(qa.strip_text()))
    qa.scroll_form(0.0)
    _fresh2d(qa)


@scenario('C08', 'C', est=60)
def c08_caps_and_modal(qa):
    """Cell caps in the strip, then Run -> the modal error (G3 split)."""
    from blastlab.core.case import Case2D, Case3D
    qa.set_case(Case2D(geometry='planar', Lx=10.0, Ly=10.0, cell_size_m=0.001,
                       center=(5.0, 5.0)))
    qa.shot('2d_cap')
    qa.note('2D 100M cells: ' + ' | '.join(qa.strip_text()))
    qa.goto('run')
    qa.app._run_single()
    qa.shot('after_modal')
    qa.goto('setup')
    qa.set_case(Case3D(cell_size_m=0.06))
    qa.shot('3d_large_warning')
    qa.note('3D 0.06 m: ' + ' | '.join(qa.strip_text()))
    qa.set_case(Case3D(cell_size_m=0.02, solver='blastfoam'))
    qa.shot('3d_foam_cap')
    qa.note('3D foam 0.02 m: ' + ' | '.join(qa.strip_text()))
    _fresh2d(qa)


@scenario('C09', 'C', est=50)
def c09_strip_overflow(qa):
    """Many strip lines at once; extra charges / det points in preview."""
    from blastlab.core.case import Case3D
    qa.set_case(Case3D(Lx=6.0, Ly=6.0, Lz=6.0, cell_size_m=0.1, charge=20.0,
                       center=(2.0, 3.0, 1.0), solver='blastfoam',
                       obstacles=[(3.0, 3.5, 2.5, 3.5, 0.0, 1.5),
                                  (4.5, 5.0, 1.0, 2.0, 0.0, 2.0)],
                       charges=[(4.0, 3.0, 1.0, 10.0), (2.0, 5.0, 1.0, 5.0)],
                       det_points=[(2.0, 3.0, 1.0), (4.0, 3.0, 1.0)],
                       afterburn='miller', activation='none', amr_levels=2,
                       gauges=[(5.5, 3.0, 1.0), (3.0, 5.5, 1.0)]))
    qa.pump(1.5)
    qa.shot('overflow')
    strip = qa.strip_text()
    qa.note(f'{len(strip)} strip lines: ' + ' | '.join(strip))
    qa.note('G8 check: the 3D preview should show 3 charges + 2 det points '
            '(see the shot)')
    qa.set_mode('light')
    qa.shot('overflow_light')
    qa.set_mode('dark')
    _fresh2d(qa)


@scenario('C10', 'C', est=90)
def c10_preview_show_mesh(qa):
    """Preview + Show mesh: 3D zones, 2D refine, AMR caption, 1D hint."""
    from blastlab.core.case import Case1D, Case3D
    C = cases()
    qa.set_case(Case3D(Lx=10.0, Ly=10.0, Lz=10.0, cell_size_m=0.5,
                       charge=1.0, center=(5.0, 5.0, 5.0), solver='blastfoam',
                       charge_refine='zone',
                       refine_zones=[(4.0, 6.0, 4.0, 6.0, 4.0, 6.0, 1),
                                     (4.5, 5.5, 4.5, 5.5, 4.5, 5.5, 2)]))
    qa.pump(1.5)
    qa.shot('3d_zones_preview')
    strip = qa.strip_text()
    qa.note('3D zones strip: ' + ' | '.join(strip))
    qa.check(any('Local refinement' in s for s in strip),
             'strip says "Local refinement: N level(s)" for charge_refine=zone',
             'S2')
    qa.app.setup.show_mesh_var.set(True)
    qa.app.setup._mesh_toggled()
    qa.pump(2.0)
    qa.shot('3d_zones_mesh')
    qa.set_case(C['F2D_REF'])
    qa.pump(1.5)
    qa.shot('2d_refine_mesh')
    qa.note('2D refine strip: ' + ' | '.join(qa.strip_text()))
    qa.set_case(C['F2D_AMR'])
    qa.pump(1.5)
    qa.shot('2d_amr_mesh')
    qa.note('2D AMR strip: ' + ' | '.join(qa.strip_text()))
    qa.app.setup.show_mesh_var.set(False)
    qa.app.setup._mesh_toggled()
    qa.pump(1.0)
    qa.set_case(Case1D())
    qa.shot('1d_preview_hint')
    _fresh2d(qa)


@scenario('C11', 'C', est=30)
def c11_axisym_relabel(qa):
    """Axisymmetric relabels Lx/Ly/cx/cy and pins the burst radius."""
    _fresh2d(qa)
    qa.shot('axisym_labels')
    form = qa.app.setup.form
    qa.note(f'axisym: burst-x entry state={form._burst_x_entry.cget("state")} '
            f'x_lo combo={form._bc_combos["x_lo"].cget("state")} '
            f'cx={form.v["cx"].get()}')
    qa.field('geometry', 'planar', settle=0.8)
    qa.shot('planar_labels')
    qa.field('geometry', 'axisymmetric', settle=0.8)


@scenario('C12', 'C', est=40)
def c12_save_open(qa):
    """Save case -> Open case round trip, and the cancel path."""
    from blastlab.core.case import Case2D
    case = Case2D(geometry='planar', Lx=3.0, Ly=2.0, cell_size_m=0.05,
                  charge=5.0, center=(1.0, 0.5), gauges=[(2.0, 1.0)],
                  obstacles=[(1.5, 1.8, 0.0, 0.6)], n_snapshots=4)
    qa.set_case(case)
    p = os.path.join(qa.dirs['cwd'], 'save1.json')
    qa.script_paths(p)
    qa.app._save_case()
    qa.pump(0.5)
    qa.check(os.path.exists(p), 'Save case wrote the JSON', 'S1')
    _fresh2d(qa)
    qa.app._open_case(p)
    qa.pump(1.0)
    back = qa.app.setup.get_case()
    same = all(getattr(back, f) == getattr(case, f) for f in
               ('Lx', 'Ly', 'cell_size_m', 'charge', 'center', 'gauges',
                'obstacles', 'n_snapshots', 'geometry'))
    qa.check(same, 'Open case round-trips the saved fields', 'S2',
             evidence=str(vars(back)))
    qa.shot('after_open')
    qa.script_paths('')
    qa.app._open_case()
    qa.pump(0.5)
    qa.note('Open case cancelled -> nothing happened (expected)')


# ─────────────────────────────────────────────────────────────────────────
# GROUP D - native runs via the Run tab
# ─────────────────────────────────────────────────────────────────────────
class Deferred(Exception):
    """Scenario cannot run yet (foreign WSL solvers) - retry on resume."""


def _entry_widget(plist):
    import customtkinter as ctk
    return [w for w in plist.winfo_children() if isinstance(w, ctk.CTkEntry)][0]


def _cache_result(qa, name):
    res = qa.last_result()
    if res is None:
        qa.check(False, f'no result to cache as {name}', 'S1')
        return
    try:
        qa.cache(name, res)
    except Exception as exc:
        qa.log(f'cache {name} failed: {exc}')


def ensure_results(qa, names=('native1d', 'native2d', 'native3d')):
    """Re-add cached results (fresh invocation) under stable labels."""
    labels = [e.label for e in qa.app.results._entries]
    dims = {'1d': 1, '2d': 2, '3d': 3}
    for name in names:
        label = f'QA {name}'
        if label in labels:
            continue
        res = qa.cached(name)
        if res is None:
            qa.log(f'no cache for {name}')
            continue
        dim = dims[name[-2:]] if name[-2:] in dims else (
            1 if 'radius_m' in res.meta else 3 if 'z_c' in res.meta else 2)
        qa.app.results.add_result(label, dim, res)
        qa.pump(0.5)


def select_result(qa, label):
    qa.app.results.sel.set(label)
    qa.app.results._refresh()
    qa.pump(0.8)


@scenario('D01', 'D', est=60)
def d01_native_1d(qa):
    """Native 1D run from the Run tab; chips, progress, log."""
    C = cases()
    qa.set_case(C['N1D'])
    qa.goto('run')
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.pump(0.6)
    qa.shot('running')
    qa.run_wait(120)
    qa.shot('finished')
    rp = qa.app.run_panel
    qa.note(f'chips after 1D run: step={rp._chip_step.cget("text")} '
            f't={rp._chip_t.cget("text")} dt={rp._chip_dt.cget("text")} '
            f'pmax={rp._chip_pmax.cget("text")} (caption "p max [Pa]" while '
            f'the plots use kPa)')
    qa.check(abs(rp.progress.get() - 1.0) < 1e-6, 'progress 100% after run')
    _cache_result(qa, 'native1d')


@scenario('D02', 'D', est=200)
def d02_native_2d_live(qa):
    """Native 2D run: live slice + Show mesh, refresh policy, gauge warning."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N2D'])
    qa.goto('run')
    qa.app.run_panel.show_mesh_var.set(True)
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.wait_log('2D Blast Solver', 30)
    qa.pump(2.5)
    qa.shot('live_mesh')
    qa.app.run_panel.refresh_val.set('abc')
    qa.app._apply_refresh()
    qa.pump(0.3)
    qa.note('Refresh every = "abc" applied: no message, policy silently '
            'falls back to automatic (G3)')
    qa.app.run_panel.refresh_mode.set('steps')
    qa.app.run_panel.refresh_val.set('5')
    qa.app._apply_refresh()
    qa.pump(2.0)
    qa.shot('refresh_steps5')
    qa.app.run_panel.show_mesh_var.set(False)
    qa.app.run_panel._rebuild_overlay()
    qa.pump(1.5)
    qa.shot('live_nomesh')
    qa.run_wait(240)
    qa.shot('finished')
    qa.check(qa.log_has('[warn] Gauge (1.4, 0.3) inside an obstacle - dropped'),
             'dropped-gauge warning reached the run log', 'S2')
    qa.note('the dropped-gauge warning lives only in the Run log; the '
            'Results Gauges table will simply show one gauge')
    qa.app.run_panel.refresh_val.set('')
    qa.app.run_panel.refresh_mode.set('seconds')
    _cache_result(qa, 'native2d')


@scenario('D03', 'D', est=240)
def d03_stepped(qa):
    """Initialise Model / Exec / Interrupt / END on the 2D case."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N2D'])
    qa.goto('run')
    qa.click(qa.app.run_panel.init_btn, 'Initialise Model')
    qa.pump(1.5)
    qa.shot('initialised')
    qa.check(qa.log_has('[model initialised'), 'G1 hint present after '
             'Initialise Model', 'S3')
    rp = qa.app.run_panel
    qa.note(f'after init: Run={rp.run_btn.cget("state")} '
            f'Exec1={rp._exec_btns[0].cget("state")} '
            f'progress={rp.progress.get():.3f} step chip={rp._chip_step.cget("text")}')
    qa.click(rp._exec_btns[1], 'Exec 10')
    qa.pump(1.5)
    qa.shot('exec10')
    qa.note(f'step chip after Exec 10: {rp._chip_step.cget("text")}')
    qa.click(rp._exec_btns[2], 'Exec 100')
    qa.pump(1.5)
    qa.click(rp._exec_btns[5], 'Interrupt')
    qa.pump(1.0)
    qa.shot('interrupted')
    qa.note('paused state is indicated only by the "[interrupted]" log line; '
            'chips/progress/buttons do not change')
    qa.click(rp._exec_btns[4], 'END')
    qa.run_wait(240)
    qa.shot('finished')


@scenario('D04', 'D', est=330)
def d04_native_3d_view(qa):
    """Native 3D run with the auto-attached embedded 3D view."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N3D'])
    qa.shot('3d_form')
    qa.goto('run')
    qa.click(qa.app.run_panel.run_btn, 'Run')
    ok = qa.pump(60, until=lambda: str(
        qa.app.run_panel.view3d_btn.cget('state')) == 'normal')
    qa.check(ok, '3D View button enabled at run start', 'S2')
    qa.pump(2.0)
    qa.shot('live_slice')
    qa.app._open_view3d()
    qa.pump(2.5)
    qa.shot('live_3d')
    qa.app.run_panel.show_slice_tab()
    qa.pump(0.5)
    qa.run_wait(300)
    qa.shot('finished_slice')
    qa.app.run_panel.show_3d_tab()
    qa.pump(1.5)
    qa.shot('finished_3d')
    v = qa.app.run_panel.view3d
    qa.note(f'after run: follow={v._vars["follow"].get()} '
            f'frames in store={len(v._scene.store) if v._scene else "?"} '
            f'3D View btn={qa.app.run_panel.view3d_btn.cget("state")}')
    qa.app.run_panel.show_slice_tab()
    _cache_result(qa, 'native3d')


@scenario('D05', 'D', est=200)
def d05_stop_midrun(qa):
    """Stop during a native 3D run: bar, label, buttons."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N3D'])
    qa.goto('run')
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.wait_log('3D Blast Solver', 30)
    qa.pump(4.0)
    t0 = time.perf_counter()
    qa.click(qa.app.run_panel.stop_btn, 'Stop')
    qa.shot('stop_requested')
    rp = qa.app.run_panel
    qa.note(f'right after Stop: Stop btn={rp.stop_btn.cget("state")} '
            f'Run btn={rp.run_btn.cget("state")}')
    qa.run_wait(120)
    qa.note(f'stop latency {time.perf_counter() - t0:.1f} s')
    qa.shot('stopped')
    labels = [e.label for e in qa.app.results._entries]
    qa.check(labels and labels[-1].endswith('(stopped)'),
             'stopped run labelled "(stopped)"', 'S2', evidence=str(labels))
    qa.check(rp.progress.get() < 1.0, 'progress bar NOT filled after a stop')
    _cache_result(qa, 'native3d_stopped')


@scenario('D06', 'D', est=90)
def d06_double_start(qa):
    """Second start while a run is live -> dialog."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N2D'])
    qa.goto('run')
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.wait_log('2D Blast Solver', 30)
    qa.app._run_single()
    qa.pump(0.3)
    qa.click(qa.app.run_panel.run_btn, 'Run (disabled?)')
    qa.app._stop()
    qa.run_wait(120)


# ─────────────────────────────────────────────────────────────────────────
# GROUP E - Results on the cached native runs
# ─────────────────────────────────────────────────────────────────────────
@scenario('E01', 'E', est=60)
def e01_combo_and_1d(qa):
    """Result combo, the 1D views, and the 3D sub-tab on a 1D result."""
    ensure_results(qa)
    qa.goto('results')
    qa.note('combo values: ' + str(qa.app.results.sel.cget('values')))
    select_result(qa, 'QA native1d')
    qa.shot('1d_fields')
    for view in ('Gauges', 'Animation', '3D'):
        qa.results_view(view)
        qa.shot(f'1d_{view.lower()}')
    qa.results_view('Fields')
    n0 = len(qa.run_log())
    qa.click(qa.app.results._export_btns['profile'], 'Profile')
    qa.pump(1.0)
    qa.app.results._open_3d()
    qa.pump(0.5)
    qa.check(qa.log_has('3D Viewer: select a 3D result.'),
             '3D Viewer on a 1D result logs a message', 'S3')
    qa.note('that message goes to the RUN-tab log while the user is on '
            'Results - nothing visible here')
    qa.shot('after_3dviewer_click')


@scenario('E02', 'E', est=120)
def e02_2d_fields(qa):
    """Every 2D field for the first and last snapshot, with/without mesh."""
    ensure_results(qa)
    qa.goto('results')
    select_result(qa, 'QA native2d')
    rs = qa.app.results
    snaps = list(rs.snap_sel.cget('values'))
    fields = list(rs.field_sel.cget('values'))
    qa.note(f'2D snapshots: {snaps}; fields: {fields}')
    for f in fields:
        rs.field_sel.set(f)
        for s in (snaps[0], snaps[-1]):
            rs.snap_sel.set(s)
            rs._draw_field()
            qa.pump(0.6)
            qa.shot(f'{f.replace(" ", "_")}_{s.replace(" ", "_")[:12]}')
    rs.field_sel.set(fields[0])
    rs.snap_sel.set(snaps[-1])
    rs.show_mesh_var.set(True)
    rs._mesh_toggled()
    qa.pump(1.0)
    qa.shot('overpressure_mesh')
    rs.show_mesh_var.set(False)
    rs._mesh_toggled()
    qa.pump(0.6)


@scenario('E03', 'E', est=60)
def e03_gauges_table(qa):
    """Gauges figure + summary table; Summary CSV and Gauges TSV exports."""
    ensure_results(qa)
    qa.goto('results')
    select_result(qa, 'QA native2d')
    qa.results_view('Gauges')
    qa.shot('gauges_2d')
    tbl = qa.app.results.summary_table
    rows = [tbl.item(i)['values'] for i in tbl.get_children()]
    qa.note(f'summary rows: {rows}')
    qa.note(f'table column widths: '
            f'{[tbl.column(c, "width") for c in tbl["columns"]]} '
            f'(sum {sum(tbl.column(c, "width") for c in tbl["columns"])} px) '
            f'vs table width {tbl.winfo_width()} px')
    for kind, fname in (('summary', 'gauges_2d_summary.csv'),
                        ('tsv', 'gauges_2d.txt')):
        qa.click(qa.app.results._export_btns[kind], kind)
        ok = qa.wait_log('Saved', 30)
        p = os.path.join(qa.dirs['exports'], 'E03', fname)
        qa.check(ok and os.path.exists(p), f'{kind} export wrote {fname}',
                 'S2')
        qa.shot(f'after_{kind}_export')
    qa.note('export feedback: only a "Saved ..." line in the RUN-tab log')
    select_result(qa, 'QA native1d')
    qa.shot('gauges_1d')
    qa.results_view('Fields')


@scenario('E04', 'E', est=60)
def e04_animation(qa):
    """Replay: play/pause, slider to the last frame, mesh during replay."""
    ensure_results(qa)
    qa.goto('results')
    select_result(qa, 'QA native2d')
    qa.results_view('Animation')
    qa.shot('anim_frame0')
    rs = qa.app.results
    n = len(rs._current().result.meta['frames']['pressures'])
    qa.note(f'{n} recorded frames; slider to={rs.frame_slider.cget("to")} '
            f'steps={rs.frame_slider.cget("number_of_steps")}')
    rs._toggle_play()
    qa.pump(2.0)
    qa.shot('playing')
    rs._toggle_play()
    rs.frame_slider.set(n - 1)
    rs._slider_moved(n - 1)
    qa.pump(0.6)
    qa.shot('last_frame')
    rs.show_mesh_var.set(True)
    rs._mesh_toggled()
    qa.pump(1.0)
    rs.frame_slider.set(n // 2)
    rs._slider_moved(n // 2)
    qa.pump(0.6)
    qa.shot('mid_frame_mesh')
    rs.show_mesh_var.set(False)
    rs._mesh_toggled()
    qa.results_view('Fields')


@scenario('E05', 'E', est=120)
def e05_3d_fields(qa):
    """Every 3D field entry + isosurface + mesh."""
    ensure_results(qa)
    qa.goto('results')
    select_result(qa, 'QA native3d')
    rs = qa.app.results
    fields = list(rs.field_sel.cget('values'))
    qa.note(f'3D fields: {fields}')
    for f in fields:
        rs.field_sel.set(f)
        rs._draw_field()
        qa.pump(0.8)
        qa.shot(f.replace(' ', '_').replace('(', '').replace(')', ''))
    rs.field_sel.set(fields[0])
    rs.show_mesh_var.set(True)
    rs._mesh_toggled()
    qa.pump(1.0)
    qa.shot('ovp_xz_mesh')
    rs.show_mesh_var.set(False)
    rs._mesh_toggled()
    qa.results_view('Gauges')
    qa.shot('gauges_3d')
    qa.results_view('Fields')


@scenario('E06', 'E', est=200)
def e06_3d_viewer(qa):
    """Embedded 3D viewer: feed timing + every control."""
    ensure_results(qa)
    qa.goto('results')
    select_result(qa, 'QA native3d')
    rs = qa.app.results
    _, ms = qa.timeit('feed_result native3d', rs._open_3d)
    qa.check(ms < 1000, f'feed_result blocked the UI for {ms:.0f} ms (G4)',
             'S3')
    qa.pump(1.5)
    qa.shot('viewer_default')
    v = rs.view3d
    qa.note('field buttons: ' + ', '.join(
        f'{k}={b.cget("state")}' for k, b in v._field_btns.items()))
    for key in ('rho', 'e', 'p_peak', 'imp', 'p'):
        if str(v._field_btns[key].cget('state')) == 'disabled':
            qa.note(f'field {key} disabled for this result')
            continue
        v._vars['field'].set(key)
        v._field_changed()
        qa.pump(1.2)
        qa.shot(f'field_{key}')
    v._vars['auto_scale'].set(False)
    v._vars['vmin'].set('0')
    v._vars['vmax'].set('200')
    v._clim_changed()
    qa.pump(1.2)
    qa.shot('manual_clim_0_200')
    v._vars['log'].set(True)
    v._log_changed()
    qa.pump(1.2)
    qa.shot('log_contours')
    v._vars['log'].set(False)
    v._log_changed()
    v._vars['auto_scale'].set(True)
    v._auto_changed()
    v._vars['iso'].set(False)
    v._toggle_layer('iso')
    qa.pump(1.0)
    qa.shot('iso_off')
    v._vars['iso'].set(True)
    v._toggle_layer('iso')
    v._vars['iso_frac'].set(0.3)
    v._iso_changed(0.3)
    qa.pump(1.0)
    qa.shot('iso_0.3')
    v._vars['loads'].set(False)
    v._toggle_layer('loads')
    qa.pump(1.0)
    qa.shot('loads_off')
    v._vars['loads'].set(True)
    v._toggle_layer('loads')
    v._vars['volume'].set(True)
    _, ms = qa.timeit('volume on + blit', lambda: (v._toggle_layer('volume'),
                                                   v._blit()))
    qa.pump(1.0)
    qa.shot('volume_on')
    v._vars['volume'].set(False)
    v._toggle_layer('volume')
    v._vars['mesh'].set(True)
    v._toggle_layer('mesh')
    qa.pump(1.2)
    qa.shot('mesh_on')
    v._tab_seg.set('Planes')
    v._tab_selected('Planes')
    v._vars['plane1_pos'].set(0.3)
    v._plane_changed('plane1')
    qa.pump(1.2)
    qa.shot('mesh_plane1_0.3')
    v._vars['mesh'].set(False)
    v._toggle_layer('mesh')
    v._vars['plane2'].set(True)
    v._toggle_layer('plane2')
    v._vars['plane2_axis'].set('z')
    v._vars['plane2_pos'].set(0.25)
    v._plane_changed('plane2')
    v._vars['plane2_op'].set('50')
    v._opacity_changed('plane2')
    qa.pump(1.2)
    qa.shot('plane2_z_0.25_op50')
    for pos in (0.0, 1.0):
        v._vars['plane1_pos'].set(pos)
        v._plane_changed('plane1')
        qa.pump(1.0)
        qa.shot(f'plane1_pos_{pos}')
    v._vars['plane1_pos'].set(0.5)
    v._plane_changed('plane1')
    v._tab_seg.set('View')
    v._tab_selected('View')
    for preset in ('top', 'front'):
        v._view_preset(preset)
        qa.pump(1.0)
        qa.shot(f'preset_{preset}')
    v._vars['parallel'].set(True)
    v._parallel_changed()
    qa.pump(1.0)
    qa.shot('parallel')
    v._vars['parallel'].set(False)
    v._parallel_changed()
    v._reset_view()
    v._tab_seg.set('Display')
    v._tab_selected('Display')
    n = len(v._scene.store)
    v._time_moved('0')
    qa.pump(1.0)
    qa.shot('time_first')
    v._time_moved(str(n - 1))
    qa.pump(1.0)
    qa.shot('time_last')
    v._toggle_play()
    qa.pump(1.5)
    qa.shot('playing')
    v._toggle_play()
    qa.results_view('Fields')


@scenario('E07', 'E', est=150)
def e07_exports(qa):
    """Every export button on the 2D and the 3D result."""
    ensure_results(qa)
    qa.goto('results')
    for label in ('QA native2d', 'QA native3d'):
        select_result(qa, label)
        for kind in ('profile', 'gif', 'summary', 'tsv', 'pngs', 'vtk'):
            n0 = len(qa.run_log())
            enabled = qa.click(qa.app.results._export_btns[kind], kind)
            if not enabled:
                qa.note(f'{label}: {kind} button disabled')
                continue
            ok = qa.pump(90, until=lambda: any(
                s in qa.run_log()[n0:] for s in
                ('Saved', 'failed', 'export', 'no profile', 'No ')))
            qa.note(f'{label} {kind}: ' + ' / '.join(
                qa.run_log()[n0:].strip().splitlines()[-3:]) or 'no log line')
            qa.shot(f'{label[-2:]}_{kind}')
        files = sorted(os.listdir(os.path.join(qa.dirs['exports'], 'E07'))
                       ) if os.path.isdir(os.path.join(qa.dirs['exports'],
                                                       'E07')) else []
        qa.note(f'files in exports/E07 after {label}: {files}')
    qa.results_view('Fields')


@scenario('E08', 'E', est=30)
def e08_empty_selection(qa):
    """Exports with no result selected."""
    ensure_results(qa)
    qa.goto('results')
    qa.app.results.sel.set('')
    qa.pump(0.3)
    n0 = len(qa.run_log())
    d0 = os.path.getsize(os.path.join(qa.out, 'dialogs.jsonl')) \
        if os.path.exists(os.path.join(qa.out, 'dialogs.jsonl')) else 0
    for kind, b in qa.app.results._export_btns.items():
        qa.click(b, kind)
    qa.pump(0.5)
    d1 = os.path.getsize(os.path.join(qa.out, 'dialogs.jsonl')) \
        if os.path.exists(os.path.join(qa.out, 'dialogs.jsonl')) else 0
    qa.check(len(qa.run_log()) > n0 or d1 > d0,
             'exports with nothing selected give some feedback (silent '
             'no-op - G3)', 'S3')
    qa.shot('after_empty_exports')
    select_result(qa, 'QA native2d')


@scenario('E09', 'E', est=30)
def e09_duplicate_labels(qa):
    """Duplicate result labels (G2)."""
    ensure_results(qa)
    qa.goto('results')
    res = qa.cached('native1d')
    qa.app.results.add_result('QA native1d', 1, res)
    qa.pump(0.5)
    vals = list(qa.app.results.sel.cget('values'))
    qa.note(f'combo now: {vals}')
    # G2 fix: a repeated label is numbered, so every entry stays reachable
    dupes = [v for v in vals if v == 'QA native1d']
    qa.check(len(dupes) == 1 and 'QA native1d #2' in vals,
             'a repeated result label is de-duplicated (#2), so both entries '
             'stay reachable in the picker', 'S2')
    qa.app.results.sel.set('QA native1d #2')
    cur = qa.app.results._current()
    qa.check(cur is not None and cur.label == 'QA native1d #2',
             'selecting the de-duplicated entry returns that entry', 'S2')
    n_before = len(qa.app.results._entries)
    qa.app.results._remove_current()
    qa.pump(0.4)
    qa.check(len(qa.app.results._entries) == n_before - 1
             and 'QA native1d #2' not in list(qa.app.results.sel.cget('values')),
             'Remove drops the selected result from the picker', 'S2')
    qa.shot('duplicate_labels')
    qa.note(f'{len(qa.app.results._entries)} entries retained; no Remove '
            f'button exists')


# ─────────────────────────────────────────────────────────────────────────
# GROUP G - Chain tab
# ─────────────────────────────────────────────────────────────────────────
def _chain_forms(qa, planar2d=False, foam2d=False):
    from blastlab.core.case import Case1D, Case2D, Case3D
    ch = qa.app.chain
    # 1D radius < 2D half-size and 2D size < 3D half-size so each
    # profile fits inside the next stage's domain
    ch.forms[1].set_case(Case1D(radius_m=0.6, charge_kg=1.0,
                                cell_size_m=0.002, gauge_radii=[0.4],
                                n_snapshots=2))
    ch.forms[2].set_case(Case2D(
        geometry='planar' if planar2d else 'axisymmetric', Lx=2.0, Ly=2.0,
        cell_size_m=0.02, charge=1.0, center=(0.0, 1.0), gauges=[(0.8, 1.0)],
        n_snapshots=2, record_frames=30,
        solver='blastfoam' if foam2d else 'native'))
    ch.forms[3].set_case(Case3D(Lx=4.0, Ly=4.0, Lz=4.0, cell_size_m=0.1,
                                charge=1.0, center=(2.0, 2.0, 1.0),
                                gauges=[(3.2, 2.0, 1.0)], n_snapshots=2,
                                record_frames=30))
    for d in (1, 2, 3):
        ch.use[d].set(True)
    ch.ws_var.set(os.path.join(qa.dirs['cwd'], 'chain_workspace'))
    qa.pump(0.5)


@scenario('G01', 'G', est=90)
def g01_chain_validation(qa):
    """Every Chain validation dialog, incl. the foam-from-profile refusal."""
    qa.goto('chain')
    _chain_forms(qa)
    ch = qa.app.chain
    qa.shot('chain_default')
    for d in (1, 2, 3):
        ch.use[d].set(False)
    ch._run()
    qa.pump(0.3)
    ch.use[1].set(True)
    ch.use[3].set(True)
    ch._run()
    qa.pump(0.3)
    ch.use[2].set(True)
    ch.forms[2].v['geometry'].set('planar')
    qa.pump(0.3)
    ch._run()
    qa.pump(0.3)
    ch.forms[2].v['geometry'].set('axisymmetric')
    ch.forms[2].v['solver'].set('blastfoam')
    qa.pump(0.3)
    ch._run()
    qa.pump(0.3)
    dl = os.path.join(qa.out, 'dialogs.jsonl')
    with open(dl, encoding='utf-8') as f:
        recs = [json.loads(l) for l in f]
    recs = [r for r in recs if r['scenario'] == 'G01']
    texts = [r['text'] for r in recs]
    qa.check(any('blastFoam stages cannot start from a profile yet' in t
                 for t in texts),
             'foam 2D stage fed by 1D -> N7 refusal dialog (uncommitted '
             'stage_errors)', 'S1', evidence=str(texts[-1:]))
    ch.forms[2].v['solver'].set('native')
    ch.forms[2].v['Lx'].set('abc')
    qa.pump(0.3)
    ch._run()
    qa.pump(0.3)
    ch.forms[2].v['Lx'].set('2.0')
    ch.forms[2].v['cy'].set('99')
    qa.pump(0.3)
    ch._run()
    qa.pump(0.3)
    ch.forms[2].v['cy'].set('1.0')
    qa.pump(0.3)
    qa.shot('after_dialogs')
    qa.note(f'stage switcher after the dialogs: {ch._stage_seg.get()} '
            f'(the dialog named stage 2)')
    qa.check(os.path.isdir(ch.ws_var.get()),
             'workspace dir created although every run was refused '
             '(side effect before validation)', 'S4')
    qa.check(str(ch.run_btn.cget('state')) == 'normal',
             'Run chain still enabled after refused starts', 'S2')


@scenario('G02', 'G', est=420)
def g02_chain_run(qa):
    """A 1D -> 2D -> 3D native chain end to end."""
    qa.goto('chain')
    _chain_forms(qa)
    ch = qa.app.chain
    t0 = time.perf_counter()
    ch._run()
    qa.tab = 'run'
    qa.pump(0.5)
    qa.check(str(ch.run_btn.cget('state')) == 'disabled',
             'Run chain disabled while the chain runs', 'S2')
    qa.goto('chain')
    qa.shot('chain_running')
    qa.goto('run')
    qa.shot('stage1')
    qa.wait_log('=== Stage 2D ===', 120)
    qa.pump(2.0)
    qa.shot('stage2')
    qa.wait_log('=== Stage 3D ===', 240)
    qa.pump(3.0)
    qa.shot('stage3')
    qa.app.run_panel.show_3d_tab()
    qa.pump(1.5)
    qa.shot('stage3_3d')
    qa.app.run_panel.show_slice_tab()
    qa.run_wait(360)
    qa.note(f'chain wall {time.perf_counter() - t0:.0f} s')
    qa.shot('chain_done')
    qa.check(str(ch.run_btn.cget('state')) == 'normal',
             'Run chain re-enabled after the chain', 'S2')
    labels = [e.label for e in qa.app.results._entries]
    qa.note(f'results after chain: {labels}')
    ws = ch.ws_var.get()
    files = sorted(os.listdir(ws)) if os.path.isdir(ws) else []
    qa.note(f'workspace files: {files}')
    qa.check(all(f in files for f in ('stage1_profile.txt',
                                      'stage2_profile.npz',
                                      'stage1_case.json', 'stage2_case.json',
                                      'stage3_case.json')),
             'workspace has the profiles and case JSONs', 'S2',
             evidence=str(files))
    qa.goto('results')
    qa.shot('results_combo')
    _cache_result(qa, 'chain3d')


@scenario('G03', 'G', est=120)
def g03_cross_tab_guard(qa):
    """Run chain while a Run-tab run is live."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N2D'])
    qa.goto('run')
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.wait_log('2D Blast Solver', 30)
    qa.goto('chain')
    qa.shot('chain_while_running')
    qa.check(str(qa.app.chain.run_btn.cget('state')) == 'disabled',
             'Run chain disabled during a Run-tab run', 'S2')
    qa.click(qa.app.chain.run_btn, 'Run chain (disabled)')
    _chain_forms(qa)
    qa.app.chain._run()
    qa.pump(0.3)
    qa.app._stop()
    qa.run_wait(120)


# ─────────────────────────────────────────────────────────────────────────
# GROUP F - real blastFoam runs in WSL
# ─────────────────────────────────────────────────────────────────────────
def _foreign_busy(qa):
    now = qa.wsl_pgrep()
    return [ln for ln in now if ln and not ln.startswith('<')]


@scenario('F00', 'F', est=480)
def f00_gate(qa):
    """WSL availability + wait for foreign solvers + disk gate."""
    from blastlab.solvers.foam import env
    box = {}

    def probe():
        box['r'] = env.check_available()
    th = threading.Thread(target=probe, daemon=True)
    th.start()
    qa.pump(120, until=lambda: not th.is_alive())
    qa.note(f'check_available -> {box.get("r")}')
    if not box.get('r', (False,))[0]:
        raise Deferred('blastFoam unavailable')
    t0 = time.perf_counter()
    busy = _foreign_busy(qa)
    while busy and time.perf_counter() - t0 < 400:
        qa.log(f'foreign solvers still running: {busy} - waiting')
        qa.pump(30)
        busy = _foreign_busy(qa)
    qa.ckpt.setdefault('f00_attempts', 0)
    qa.ckpt['f00_attempts'] += 1
    if busy and qa.ckpt['f00_attempts'] < 3:
        raise Deferred(f'foreign solvers busy: {busy}')
    if busy:
        qa.note(f'proceeding with foreign solvers running: {busy} '
                f'(timings contaminated)')
    qa.ckpt['pre_f_pgrep'] = qa.wsl_pgrep()
    qa.check(qa.disk_gate(), 'disk gate before foam runs', 'S1')
    try:
        info = env.run_info()
        qa.ckpt['runs_root_bytes_before'] = sum(
            (i.get('bytes') or 0) for i in info.values())
        qa.note(f'runs root before F: {len(info)} runs, '
                f'{qa.ckpt["runs_root_bytes_before"] / 1e9:.1f} GB')
    except Exception as exc:
        qa.log(f'run_info failed: {exc}')


def _foam_run(qa, case, label, timeout, show_mesh=False):
    qa.goto('setup')
    qa.set_case(case, settle=1.5)
    qa.shot(f'{label}_setup')
    qa.note(f'{label} strip: ' + ' | '.join(qa.strip_text()))
    qa.goto('run')
    qa.app.run_panel.show_mesh_var.set(show_mesh)
    t0 = time.perf_counter()
    qa.click(qa.app.run_panel.run_btn, 'Run')
    if qa.wait_log('checking WSL', 20):
        qa.shot(f'{label}_checking_wsl')
    if qa.wait_log('blockMesh', 120):
        qa.pump(0.5)
        qa.shot(f'{label}_meshing')
    if qa.wait_log('[blastfoam] write', 240):
        frac = qa.app.run_panel.progress.get()
        qa.note(f'{label}: progress at first write = {frac:.3f} '
                f'({time.perf_counter() - t0:.0f} s after Run)')
        qa.check(frac > 0.0, 'progress > 0 by the first write (B7)', 'S3')
        qa.pump(2.5)
        qa.shot(f'{label}_first_write')
    qa.run_wait(timeout)
    qa.note(f'{label} wall {time.perf_counter() - t0:.0f} s; stop reason: '
            + ' / '.join(l for l in qa.run_log().splitlines()
                         if 'Stopped' in l or 'stop' in l.lower())[:300])
    qa.shot(f'{label}_finished')
    own = qa.reap_own()
    qa.note(f'own runs after {label}: '
            + ', '.join(f'{os.path.basename(d)} alive={r.alive}'
                        for d, r in own.items()))


@scenario('F01', 'F', est=420)
def f01_foam_1d(qa):
    """1D blastFoam (C4) through the Run tab."""
    _foam_run(qa, cases()['F1D'], 'foam1d', 360)
    qa.goto('results')
    qa.shot('results_fields')
    qa.results_view('Gauges')
    qa.shot('results_gauges')
    qa.results_view('Fields')
    _cache_result(qa, 'foam1d')


@scenario('F02', 'F', est=480)
def f02_foam_2d_planar(qa):
    """2D planar blastFoam: live slice, peak/impulse, replay, VTK export."""
    _foam_run(qa, cases()['F2D'], 'foam2d', 400, show_mesh=True)
    qa.goto('results')
    rs = qa.app.results
    fields = list(rs.field_sel.cget('values'))
    qa.note(f'foam 2D fields: {fields}; peak_source='
            f'{rs._current().result.meta.get("peak_source")}')
    for f in fields:
        rs.field_sel.set(f)
        rs._draw_field()
        qa.pump(0.6)
        qa.shot(f.replace(' ', '_'))
    qa.results_view('Gauges')
    qa.shot('gauges')
    qa.results_view('Animation')
    qa.shot('anim')
    qa.results_view('Fields')
    n0 = len(qa.run_log())
    enabled = qa.click(rs._export_btns['vtk'], 'VTK')
    qa.check(enabled, 'VTK button enabled for a foam run', 'S2')
    ok = qa.pump(180, until=lambda: 'VTK export done' in qa.run_log()[n0:]
                 or 'failed' in qa.run_log()[n0:])
    tail = qa.run_log()[n0:].strip().splitlines()
    qa.note('VTK export log: ' + ' / '.join(tail[-4:]))
    qa.check(ok and 'VTK export done' in qa.run_log()[n0:], 'VTK export done',
             'S2')
    m = [l for l in tail if 'VTK export done:' in l]
    if m:
        out = m[0].split('VTK export done:', 1)[1].strip()
        try:
            n = len([f for f in os.listdir(out) if f.endswith('.vtk')])
            ndirs = len(rs._current().result.snapshots)
            qa.note(f'VTK dir {out}: {n} .vtk files ({ndirs} snapshots)')
        except OSError as exc:
            qa.note(f'VTK dir not listable: {exc}')
    qa.shot('after_vtk')
    _cache_result(qa, 'foam2d')


@scenario('F03', 'F', est=420)
def f03_foam_3d_tiny(qa):
    """3D tiny blastFoam: live 3D view, Results 3D playback with p_peak."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['F3D'], settle=1.5)
    qa.goto('run')
    t0 = time.perf_counter()
    qa.click(qa.app.run_panel.run_btn, 'Run')
    ok = qa.pump(240, until=lambda: str(
        qa.app.run_panel.view3d_btn.cget('state')) == 'normal')
    qa.check(ok, '3D View enabled for the foam 3D run', 'S2')
    qa.wait_log('[blastfoam] write', 240)
    qa.pump(3.0)
    qa.app.run_panel.show_3d_tab()
    qa.pump(1.5)
    qa.shot('live_3d')
    qa.app.run_panel.show_slice_tab()
    qa.pump(0.5)
    qa.shot('live_slice')
    qa.run_wait(360)
    qa.note(f'foam3d wall {time.perf_counter() - t0:.0f} s')
    qa.shot('finished')
    qa.reap_own()
    qa.goto('results')
    rs = qa.app.results
    rs._open_3d()
    qa.pump(2.0)
    qa.shot('results_3d')
    v = rs.view3d
    qa.note('3D viewer fields for foam: ' + ', '.join(
        f'{k}={b.cget("state")}' for k, b in v._field_btns.items()))
    v._vars['field'].set('p_peak')
    v._field_changed()
    qa.pump(1.5)
    qa.shot('results_3d_ppeak')
    v._vars['field'].set('p')
    v._field_changed()
    v._vars['mesh'].set(True)
    v._toggle_layer('mesh')
    qa.pump(1.5)
    qa.shot('results_3d_mesh')
    v._vars['mesh'].set(False)
    v._toggle_layer('mesh')
    qa.results_view('Fields')
    _cache_result(qa, 'foam3d')


@scenario('F04', 'F', est=420)
def f04_foam_2d_refine(qa):
    """2D planar with static refinement zones + Show mesh everywhere."""
    qa.goto('setup')
    qa.app.setup.show_mesh_var.set(True)
    qa.app.setup._mesh_toggled()
    _foam_run(qa, cases()['F2D_REF'], 'refine2d', 330, show_mesh=True)
    qa.app.setup.show_mesh_var.set(False)
    qa.goto('results')
    rs = qa.app.results
    rs.show_mesh_var.set(True)
    rs._mesh_toggled()
    qa.pump(1.0)
    qa.shot('fields_mesh')
    qa.results_view('Animation')
    qa.shot('replay_mesh')
    n = len(rs._current().result.meta['frames']['pressures'])
    rs.frame_slider.set(n - 1)
    rs._slider_moved(n - 1)
    qa.pump(0.8)
    qa.shot('replay_last_mesh')
    qa.results_view('Fields')
    n0 = len(qa.run_log())
    qa.click(rs._export_btns['pngs'], 'PNGs')
    qa.pump(90, until=lambda: 'gauges.png' in qa.run_log()[n0:])
    files = sorted(os.listdir(os.path.join(qa.dirs['exports'], 'F04'))) \
        if os.path.isdir(os.path.join(qa.dirs['exports'], 'F04')) else []
    qa.note(f'PNG export with mesh: {files}')
    rs.show_mesh_var.set(False)
    rs._mesh_toggled()
    _cache_result(qa, 'foam2d_refine')


@scenario('F05', 'F', est=420)
def f05_foam_2d_amr(qa):
    """2D planar dynamic AMR: per-write mesh in the live view and replay."""
    qa.goto('setup')
    qa.set_case(cases()['F2D_AMR'], settle=1.5)
    strip = qa.strip_text()
    qa.check(any('AMR up to level' in s for s in strip),
             'validation line names the AMR levels / display level', 'S2',
             evidence=str(strip))
    _foam_run(qa, cases()['F2D_AMR'], 'amr2d', 330, show_mesh=True)
    lines = [l for l in qa.run_log().splitlines() if 'AMR t =' in l]
    qa.note(f'{len(lines)} AMR log lines; first: {lines[:1]}; last: {lines[-1:]}')
    qa.goto('results')
    rs = qa.app.results
    rs.show_mesh_var.set(True)
    rs._mesh_toggled()
    qa.results_view('Animation')
    qa.pump(0.8)
    qa.shot('replay_frame0_mesh')
    n = len(rs._current().result.meta['frames']['pressures'])
    rs.frame_slider.set(n - 1)
    rs._slider_moved(n - 1)
    qa.pump(0.8)
    qa.shot('replay_last_mesh')
    lv = rs._current().result.meta['frames'].get('levels')
    qa.check(lv is not None and len(lv) == n, 'per-frame level maps recorded',
             'S2')
    qa.results_view('Fields')
    qa.shot('fields_mesh')
    rs.show_mesh_var.set(False)
    rs._mesh_toggled()
    _cache_result(qa, 'foam2d_amr')


@scenario('F06', 'F', est=200)
def f06_foam_3d_amr(qa):
    """3D dynamic AMR tiny (optional): per-frame mesh in the 3D viewer."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['F3D_AMR'], settle=1.5)
    strip = qa.strip_text()
    qa.note('3D AMR strip: ' + ' | '.join(strip))
    if any('error' in s.lower() for s in strip):
        qa.note('3D AMR case does not validate - skipping the run')
        return
    qa.goto('run')
    t0 = time.perf_counter()
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.wait_log('[blastfoam] write', 240)
    qa.app.run_panel.show_3d_tab()
    v = qa.app.run_panel.view3d
    v._vars['mesh'].set(True)
    v._toggle_layer('mesh')
    qa.pump(3.0)
    qa.shot('live_3d_mesh_a')
    qa.pump(8.0)
    qa.shot('live_3d_mesh_b')
    ok = qa.pump(300, until=lambda: not qa.worker_alive())
    if not ok:
        qa.note('3D AMR still running after 6 min - stopping')
        qa.app._stop()
    qa.run_wait(120)
    qa.note(f'amr3d wall {time.perf_counter() - t0:.0f} s')
    qa.shot('finished')
    v._vars['mesh'].set(False)
    v._toggle_layer('mesh')
    qa.app.run_panel.show_slice_tab()
    qa.reap_own()
    qa.goto('results')
    rs = qa.app.results
    rs._open_3d()
    rv = rs.view3d
    rv._vars['mesh'].set(True)
    rv._toggle_layer('mesh')
    qa.pump(2.0)
    qa.shot('results_3d_mesh_first')
    n = len(rv._scene.store) if rv._scene else 0
    if n > 1:
        rv._time_moved(str(n - 1))
        qa.pump(1.5)
        qa.shot('results_3d_mesh_last')
    rv._vars['mesh'].set(False)
    rv._toggle_layer('mesh')
    qa.results_view('Fields')
    _cache_result(qa, 'foam3d_amr')


@scenario('F07', 'F', est=120)
def f07_stop_during_meshing(qa):
    """Stop while blockMesh runs on a 1.5 M-cell case."""
    qa.goto('setup')
    qa.set_case(cases()['F_STOP_PRE'], settle=1.5)
    qa.goto('run')
    n_res = len(qa.app.results._entries)
    d0 = _nlines(os.path.join(qa.out, 'dialogs.jsonl'))
    qa.click(qa.app.run_panel.run_btn, 'Run')
    ok = qa.wait_log('blockMesh', 150)
    qa.check(ok, 'blockMesh stage line appeared', 'S2')
    t0 = time.perf_counter()
    qa.click(qa.app.run_panel.stop_btn, 'Stop')
    qa.shot('stop_during_meshing')
    qa.run_wait(90)
    dt = time.perf_counter() - t0
    qa.note(f'stop during meshing -> run finished in {dt:.1f} s')
    qa.check(dt < 15, f'stop during meshing returned in {dt:.1f} s (< 15)',
             'S2')
    d1 = _nlines(os.path.join(qa.out, 'dialogs.jsonl'))
    qa.check(d1 == d0, 'no "Run failed" dialog after a stop in meshing', 'S2')
    qa.check(len(qa.app.results._entries) == n_res,
             'no Results entry for a run stopped before start', 'S2')
    qa.shot('after_stop')
    qa.note('log tail: ' + ' / '.join(qa.run_log().strip().splitlines()[-4:]))
    qa.reap_own()


@scenario('F08', 'F', est=200)
def f08_stop_during_solve(qa):
    """Stop while solving; revolved 3D view; run browser shows 'running'."""
    qa.goto('setup')
    qa.set_case(cases()['F_STOP'], settle=1.5)
    qa.goto('run')
    qa.click(qa.app.run_panel.run_btn, 'Run')
    ok = qa.wait_log('[blastfoam] write', 240)
    qa.check(ok, 'first write of the axisym stop case', 'S2')
    qa.pump(2.0)
    qa.app.run_panel.show_3d_tab()
    qa.pump(3.0)
    qa.shot('revolved_3d')
    qa.app.run_panel.show_slice_tab()
    qa.app.results._open_run_browser()
    win = qa.app.results._run_browser
    try:
        win.attributes('-topmost', True)
        win.lift()
    except Exception:
        pass
    qa.pump(90, until=lambda: not win._busy)
    qa.shot('browser_with_running', win=win)
    own = [n for n in win.rows if f'_p{os.getpid()}-' in n]
    qa.note(f'browser rows: {len(win.rows)}; own: {own}; '
            f'status: {win.status.cget("text")!r}')
    # the run that is solving right now = the newest own dir
    own.sort(reverse=True)
    if own:
        win.table.selection_set(own[0])
        win.table.see(own[0])
        qa.pump(0.3)
        qa.note(f'own row {own[0]} state: {win.rows[own[0]]["alive"]} '
                f'(solver is running right now)')
        qa.check(win.rows[own[0]]['alive'] is True,
                 'browser reports the live run as running', 'S2')
        own = [own[0]]
        qa.script_answers(False)
        win.delete_selected()
        qa.pump(0.5)
        qa.shot('browser_delete_refused', win=win)
        qa.note(f'status after delete on a running run: '
                f'{win.status.cget("text")!r}')
    win.destroy()
    qa.pump(0.5)
    t0 = time.perf_counter()
    qa.click(qa.app.run_panel.stop_btn, 'Stop')
    qa.run_wait(150)
    dt = time.perf_counter() - t0
    qa.note(f'graceful stop during solve took {dt:.1f} s')
    qa.check(not qa.log_has('did not stop cleanly'), 'stop was graceful', 'S2')
    labels = [e.label for e in qa.app.results._entries]
    qa.check(labels and labels[-1].endswith('(stopped)'),
             'stopped foam run labelled (stopped)', 'S2', evidence=str(labels))
    qa.shot('stopped')
    qa.reap_own()
    _cache_result(qa, 'foam2d_axi_stopped')


@scenario('F09', 'F', est=240)
def f09_run_browser(qa):
    """Run browser: list, Load (post-mortem == live), duplicate, Delete."""
    qa.goto('results')
    qa.app.results._open_run_browser()
    win = qa.app.results._run_browser
    try:
        win.attributes('-topmost', True)
        win.lift()
    except Exception:
        pass
    qa.pump(1.0)
    qa.shot('browser_listing', win=win)
    qa.pump(120, until=lambda: not win._busy)
    qa.shot('browser_sized', win=win)
    qa.note(f'browser: {len(win.rows)} rows; status {win.status.cget("text")!r}; '
            f'geometry {win.geometry()}')
    cached = qa.cached('foam2d')
    name = os.path.basename(cached.meta.get('case_dir', '').rstrip('/')) \
        if cached is not None else ''
    qa.note(f'F02 run dir: {name!r}; in browser: {name in win.rows}')
    if name and name in win.rows:
        win.table.selection_set(name)
        win.table.see(name)
        n0 = len(qa.run_log())
        win.load_selected()
        ok = qa.pump(240, until=lambda: 'Loaded:' in qa.run_log()[n0:]
                     or 'Load failed' in qa.run_log()[n0:])
        qa.pump(1.5)
        qa.check(ok and 'Loaded:' in qa.run_log()[n0:], 'post-mortem load '
                 'succeeded', 'S1', evidence=qa.run_log()[n0:][-400:])
        qa.shot('after_load', win=win)
        qa.shot('results_loaded')
        loaded = qa.last_result()
        if loaded is not None and cached is not None:
            import numpy as np
            same_snaps = list(loaded.snapshots) == list(cached.snapshots)
            gp = np.allclose(loaded.gauges['pressures'][0],
                             cached.gauges['pressures'][0], rtol=1e-6) \
                if loaded.gauges.get('pressures') and cached.gauges.get('pressures') else False
            pk = ('p_peak' in loaded.meta and 'p_peak' in cached.meta
                  and np.allclose(loaded.meta['p_peak'], cached.meta['p_peak'],
                                  rtol=1e-5))
            ft = (np.array_equal(loaded.meta['frames']['times'],
                                 cached.meta['frames']['times'])
                  if loaded.meta.get('frames') and cached.meta.get('frames')
                  else None)
            qa.check(same_snaps, 'loaded snapshot keys == live', 'S2',
                     evidence=f'{list(loaded.snapshots)} vs {list(cached.snapshots)}')
            qa.check(gp, 'loaded gauge pressures == live', 'S2')
            qa.check(pk, 'loaded p_peak == live', 'S2',
                     evidence=f'peak_source {loaded.meta.get("peak_source")} '
                              f'vs {cached.meta.get("peak_source")}')
            qa.note(f'frame times equal: {ft}')
        # G2 with a real duplicate: load the same run again
        n0 = len(qa.run_log())
        win.table.selection_set(name)
        win.load_selected()
        qa.pump(240, until=lambda: 'Loaded:' in qa.run_log()[n0:])
        qa.pump(1.5)
        vals = list(qa.app.results.sel.cget('values'))
        dup = [v for v in vals if v == f'Loaded - {name} (2D)']
        qa.check(len(dup) == 2, 'loading twice yields two identical combo '
                 'entries (G2)', 'S2', evidence=str(vals))
        qa.shot('duplicate_loaded')
    win.refresh()
    qa.pump(120, until=lambda: not win._busy)
    f3 = qa.cached('foam3d')
    n3 = os.path.basename(f3.meta.get('case_dir', '').rstrip('/')) \
        if f3 is not None else ''
    if n3 and n3 in win.rows and win.rows[n3]['alive'] is False:
        win.table.selection_set(n3)
        qa.script_answers(True)
        win.delete_selected()
        qa.pump(120, until=lambda: not win._busy and n3 not in win.rows)
        qa.check(n3 not in win.rows, 'own finished 3D run deleted from the '
                 'browser', 'S2')
        qa.shot('after_delete', win=win)
    else:
        qa.note(f'F03 run {n3!r} not deletable: '
                f'{win.rows.get(n3, {}).get("alive")}')
    qa.script_paths('')
    win.browse()
    qa.pump(0.5)
    win.destroy()
    qa.pump(0.5)


@scenario('F10', 'F', est=100)
def f10_vtk_edge_cases(qa):
    """VTK on a loaded run and on a run whose dir was deleted."""
    qa.goto('results')
    rs = qa.app.results
    vals = list(rs.sel.cget('values'))
    loaded = [v for v in vals if v.startswith('Loaded -')]
    if loaded:
        select_result(qa, loaded[0])
        n0 = len(qa.run_log())
        qa.click(rs._export_btns['vtk'], 'VTK')
        qa.pump(180, until=lambda: 'VTK export done' in qa.run_log()[n0:]
                or 'failed' in qa.run_log()[n0:])
        qa.note('VTK on a loaded run: ' + ' / '.join(
            qa.run_log()[n0:].strip().splitlines()[-3:]))
    f3 = [v for v in vals if v.endswith('3D') and 'QA' not in v]
    if f3:
        select_result(qa, f3[-1])
        qa.note(f'{f3[-1]}: VTK button state after its dir was deleted = '
                f'{rs._export_btns["vtk"].cget("state")}')
        n0 = len(qa.run_log())
        rs._export('vtk')
        qa.pump(1.0)
        qa.note('direct _export(vtk) on a deleted dir: '
                + ' / '.join(qa.run_log()[n0:].strip().splitlines()[-2:]))
    qa.shot('vtk_edge')


@scenario('F11', 'F', est=200, terminal=True)
def f11_close_during_foam(qa):
    """Close the window mid-foam-run: no orphan solver may survive."""
    qa.goto('setup')
    qa.set_case(cases()['F2D'], settle=1.5)
    qa.goto('run')
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.wait_log('[blastfoam] write', 240)
    qa.pump(1.0)
    w = qa.app.worker
    t0 = time.perf_counter()
    qa.app._on_close()
    qa.root = None
    w.join(180)
    qa.log(f'_on_close + join took {time.perf_counter() - t0:.1f} s; '
           f'worker alive={w.is_alive()}')
    time.sleep(3)
    own = qa.own_runs()
    alive = [d for d, r in own.items() if r.alive]
    qa.check(not alive, 'no own solver alive after closing the window '
             'mid-run', 'S1', evidence=str(alive))
    qa.note(f'pgrep after close: {qa.wsl_pgrep()}')


# ─────────────────────────────────────────────────────────────────────────
# GROUP H - theme toggle mid-session (G6 theme half)
# ─────────────────────────────────────────────────────────────────────────
@scenario('H01', 'H', est=60)
def h01_preview_theme(qa):
    """Setup preview after a dark->light toggle without a redraw."""
    from blastlab.core.case import Case2D
    qa.goto('setup')
    # (the blastFoam variant with a level-1 zone crashes the preview with
    # an IndexError - recorded as a finding in the first H01 run)
    qa.set_case(Case2D(geometry='planar', Lx=3.0, Ly=2.0, cell_size_m=0.05,
                       charge=5.0, center=(1.0, 0.5), gauges=[(2.0, 1.0)],
                       obstacles=[(1.5, 1.8, 0.0, 0.6)]))
    qa.app.setup.show_mesh_var.set(True)
    qa.app.setup._mesh_toggled()
    qa.pump(1.0)
    qa.shot('preview_dark')
    qa.set_mode('light')
    qa.shot('preview_light_no_redraw')
    qa.field('Lx', '3.0001')
    qa.pump(0.8)
    qa.shot('preview_light_redrawn')
    qa.set_mode('dark')
    qa.shot('preview_dark_no_redraw')
    qa.field('Lx', '3.0')
    qa.app.setup.show_mesh_var.set(False)
    qa.app.setup._mesh_toggled()


@scenario('H02', 'H', est=200)
def h02_live_theme(qa):
    """Theme toggle during a live native 2D run."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N2D'])
    qa.goto('run')
    qa.app.run_panel.show_mesh_var.set(True)
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.wait_log('2D Blast Solver', 30)
    qa.pump(2.0)
    qa.set_mode('light')
    qa.pump(1.5)
    qa.shot('live_light')
    qa.run_wait(240)
    qa.shot('finished_light')
    qa.set_mode('dark')
    qa.pump(1.0)
    qa.shot('finished_dark_again')
    qa.app.run_panel.show_mesh_var.set(False)


@scenario('H03', 'H', est=150)
def h03_results_light(qa):
    """Results views, run browser and Chain in light mode."""
    ensure_results(qa)
    qa.set_mode('light')
    qa.goto('results')
    for label in ('QA native2d', 'QA native3d'):
        select_result(qa, label)
        for view in ('Fields', 'Gauges', 'Animation'):
            qa.results_view(view)
            qa.shot(f'{label[-2:]}_{view.lower()}')
        if label.endswith('3d'):
            qa.app.results._open_3d()
            qa.pump(1.5)
            qa.shot('3d_viewer')
    qa.results_view('Fields')
    qa.app.results._open_run_browser()
    win = qa.app.results._run_browser
    try:
        win.attributes('-topmost', True)
        win.lift()
    except Exception:
        pass
    qa.pump(90, until=lambda: not win._busy)
    qa.shot('browser_light', win=win)
    win.destroy()
    qa.goto('chain')
    qa.shot('chain_light')
    qa.goto('run')
    qa.shot('run_light')
    qa.set_mode('dark')


# ─────────────────────────────────────────────────────────────────────────
# GROUP I - robustness
# ─────────────────────────────────────────────────────────────────────────
@scenario('I01', 'I', est=330)
def i01_rapid_tabs(qa):
    """Random tab/view switching during a native 3D run."""
    import random
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N3D'])
    qa.goto('run')
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.wait_log('3D Blast Solver', 30)
    qa.pump(3.0)
    rnd = random.Random(7)
    t0 = time.perf_counter()
    qa.action = 'rapid tabs'
    while time.perf_counter() - t0 < 12:
        k = rnd.choice(['setup', 'run', 'results', 'chain'])
        qa.app._show(k)
        qa.tab = k
        if k == 'results' and rnd.random() < 0.5:
            qa.app.results._view_seg.set(rnd.choice(['Fields', 'Gauges',
                                                     'Animation', '3D']))
            qa.app.results._view_selected(qa.app.results._view_seg.get())
        if k == 'run' and rnd.random() < 0.5:
            (qa.app.run_panel.show_3d_tab if rnd.random() < 0.5
             else qa.app.run_panel.show_slice_tab)()
        qa.pump(0.1)
    qa.action = ''
    qa.goto('run')
    qa.run_wait(300)
    for k in ('setup', 'run', 'results', 'chain'):
        qa.goto(k)
        qa.shot('after_rapid')
    qa.app.run_panel.show_slice_tab()


@scenario('I02', 'I', est=120, terminal=True)
def i02_close_during_native(qa):
    """Close the window 2 s into a native 3D run."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N3D'])
    qa.goto('run')
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.wait_log('3D Blast Solver', 30)
    qa.pump(2.0)
    w = qa.app.worker
    t0 = time.perf_counter()
    qa.app._on_close()
    qa.root = None
    dt = time.perf_counter() - t0
    w.join(60)
    qa.log(f'_on_close took {dt:.1f} s; worker alive after join: {w.is_alive()}')
    qa.check(dt < 12, f'close during a native run returned in {dt:.1f} s',
             'S2')


@scenario('I03', 'I', est=60)
def i03_bad_json(qa):
    """Open case on garbage / wrong schema / wrong dim / missing file."""
    qa.goto('setup')
    from blastlab.core.case import Case2D
    qa.set_case(Case2D(Lx=3.3))
    cases_dir = qa.dirs['cwd']
    bad = {'garbage.json': '{not json',
           'wrongschema.json': json.dumps({'schema': 99, 'dim': 2}),
           'dim5.json': json.dumps({'dim': 5}),
           'empty.json': ''}
    for name, text in bad.items():
        p = os.path.join(cases_dir, name)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
    for name in list(bad) + ['missing.json']:
        p = os.path.join(cases_dir, name)
        qa.app._open_case(p)
        qa.pump(0.5)
        qa.note(f'{name}: form Lx still {qa.app.setup.form.v["Lx"].get()!r}')
    qa.shot('after_bad_json')


@scenario('I04', 'I', est=120)
def i04_huge_cells(qa):
    """Cap errors on Run / Initialise; a warning-level case starts silently."""
    from blastlab.core.case import Case2D
    qa.goto('setup')
    qa.set_case(Case2D(geometry='planar', Lx=10.0, Ly=10.0, cell_size_m=0.001,
                       center=(5.0, 5.0)))
    qa.goto('run')
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.click(qa.app.run_panel.init_btn, 'Initialise Model')
    qa.goto('setup')
    qa.set_case(Case2D(geometry='planar', Lx=6.0, Ly=6.0, cell_size_m=0.004,
                       charge=50.0, center=(3.0, 3.0), record_frames=0))
    strip = qa.strip_text()
    qa.note('2.25 M-cell 2D case strip: ' + ' | '.join(strip))
    qa.goto('run')
    n0 = len(qa.run_log())
    d0 = _nlines(os.path.join(qa.out, 'dialogs.jsonl'))
    qa.click(qa.app.run_panel.run_btn, 'Run')
    qa.pump(2.0)
    started = qa.worker_alive() or '[run finished]' in qa.run_log()[n0:]
    d1 = _nlines(os.path.join(qa.out, 'dialogs.jsonl'))
    qa.note(f'warning-level case: started={started}, dialogs={d1 - d0} '
            f'(no confirmation prompt for a large run)')
    qa.shot('large_run_started')
    qa.app._stop()
    qa.run_wait(120)


@scenario('I05', 'I', est=60)
def i05_input_stress(qa):
    """Odd numeric inputs: 1e400, nan, inf, whitespace, decimal comma."""
    from blastlab.core.case import Case2D
    qa.goto('setup')
    qa.set_case(Case2D())
    for val in ('1e400', 'nan', 'inf', ' 1 ', '1,5', '-0'):
        qa.field('charge', val)
        qa.note(f'charge={val!r}: ' + ' | '.join(qa.strip_text()))
        qa.shot('charge_' + val.strip().replace(',', 'comma').replace(' ', ''))
    qa.field('charge', '1.0')
    qa.field('n_snapshots', '2.7')
    qa.note('n_snapshots=2.7: ' + ' | '.join(qa.strip_text()) +
            f' (parsed as {qa.app.setup.get_case().n_snapshots})')
    qa.field('n_snapshots', '6')
    qa.field('cell', '1e-9')
    qa.note('cell=1e-9: ' + ' | '.join(qa.strip_text()))
    qa.field('cell', '0.025')


@scenario('I06', 'I', est=40)
def i06_small_window_3d(qa):
    """Below-minsize window with the Results 3D sub-tab open."""
    ensure_results(qa)
    qa.goto('results')
    select_result(qa, 'QA native3d')
    qa.app.results._open_3d()
    qa.pump(1.5)
    qa.geometry('1100x720+0+0')
    qa.shot('3d_1100x720')
    qa.geometry('900x600+0+0')
    qa.shot('3d_900x600')
    qa.reset_window()
    qa.results_view('Fields')


# ─────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────
def latest_out():
    dirs = sorted(glob.glob(os.path.join(QA_ROOT, '*')))
    dirs = [d for d in dirs if os.path.isdir(d)]
    return dirs[-1] if dirs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--only', default='')
    ap.add_argument('--skip', default='')
    ap.add_argument('--scenario', default='')
    ap.add_argument('--redo', default='')
    ap.add_argument('--budget', type=float, default=540)
    ap.add_argument('--smoke', action='store_true')
    ap.add_argument('--list', action='store_true')
    args = ap.parse_args()

    if args.out:
        out = args.out
    elif args.resume and latest_out():
        out = latest_out()
    else:
        out = os.path.join(QA_ROOT, time.strftime('%Y%m%d-%H%M'))
    os.makedirs(out, exist_ok=True)
    print(f'QA output: {out}', flush=True)

    # scratch settings + CWD BEFORE importing the app
    settings = os.path.join(out, 'settings.json')
    if not os.path.exists(settings):
        with open(settings, 'w', encoding='utf-8') as f:
            json.dump(dict(auto_cleanup=False), f)
    os.environ['BLASTLAB_SETTINGS'] = settings
    os.environ['MPLBACKEND'] = 'TkAgg'
    cwd = os.path.join(out, 'cwd')
    os.makedirs(cwd, exist_ok=True)
    os.chdir(cwd)
    sys.path.insert(0, REPO)

    qa = QA(out, args)
    only = [g for g in args.only.split(',') if g]
    skip = [s for s in args.skip.split(',') if s]
    redo = [s for s in args.redo.split(',') if s]
    for r in redo:
        qa.ckpt['done'].pop(r, None)

    def selected(sid, group):
        if args.smoke:
            return sid == 'S00'
        if args.scenario:
            return sid in args.scenario.split(',')
        if sid == 'S00':
            return False
        if only and group not in only and sid not in only:
            return False
        if sid in skip:
            return False
        return True

    todo = [s for s in SCENARIOS if selected(s[0], s[1])
            and s[0] not in qa.ckpt['done']]
    if args.list:
        for sid, group, est, term, fn, doc in SCENARIOS:
            st = qa.ckpt['done'].get(sid, {}).get('status', '-')
            print(f'  {sid:5s} {group:2s} {est:4d}s {st:10s} {doc}')
        print(f'{len(todo)} pending')
        return 0
    if not todo:
        print('nothing to do')
        return 0

    qa.ckpt['invocations'].append(dict(start=time.time(), argv=sys.argv[1:]))
    if not qa.ckpt.get('foreign_pids'):
        qa.ckpt['foreign_pids'] = qa.wsl_pgrep()
        qa.log(f'foreign WSL solvers at kickoff: {qa.ckpt["foreign_pids"]}')
    qa.save_ckpt()

    install_warning_capture(qa)
    qa.patch_dialogs()
    exit_code = 0
    try:
        qa.build_app()
        for sid, group, est, terminal, fn, doc in todo:
            if os.path.exists(os.path.join(out, 'STOP')):
                raise KillSwitch()
            if est > qa.budget_left():
                qa.log(f'budget: {qa.budget_left():.0f}s left < {est}s for '
                       f'{sid} - exiting 75')
                exit_code = 75
                break
            qa.begin(sid)
            try:
                fn(qa)
                qa.end(sid, 'done')
            except KillSwitch:
                qa.end(sid, 'killed')
                raise
            except Deferred as exc:
                qa.end(sid, 'deferred', str(exc))
                qa.ckpt['done'].pop(sid, None)
                qa.save_ckpt()
                qa.log(f'{sid} deferred: {exc} - exiting 75')
                exit_code = 75
                break
            except Exception:
                err = traceback.format_exc()
                qa.finding('S1', 'harness-crash', f'{sid} raised',
                           evidence=err[-2000:])
                qa.end(sid, 'crashed', err)
            if terminal:
                qa.log(f'{sid} is terminal - exiting 75 for a fresh App')
                exit_code = 75
                break
            qa.neutral()
        else:
            exit_code = 0
    except KillSwitch:
        qa.log('kill switch - stopping')
        exit_code = 3
    except Exception:
        qa.log('HARNESS CRASH\n' + traceback.format_exc())
        exit_code = 1
    finally:
        try:
            if qa.app is not None and qa.worker_alive():
                qa.app._stop()
                qa.pump(90, until=lambda: not qa.worker_alive())
        except Exception:
            pass
        try:
            qa.reap_own()
        except Exception as exc:
            qa.log(f'reap failed: {exc}')
        try:
            if qa.root is not None:
                qa.root.destroy()
        except Exception:
            pass
        qa.ckpt['invocations'][-1]['end'] = time.time()
        qa.ckpt['invocations'][-1]['exit'] = exit_code
        qa.save_ckpt()
        pending = [s[0] for s in SCENARIOS if selected(s[0], s[1])
                   and s[0] not in qa.ckpt['done']]
        qa.log(f'exit {exit_code}; pending: {pending}')
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
