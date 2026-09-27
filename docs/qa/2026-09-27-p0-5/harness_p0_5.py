"""Throwaway real-window QA harness for P0-5 / P1-18 (2026-09-27).

  python harness_p0_5.py qt      # Qt: HD 1.3 + 2D save/open, disk warning
  python harness_p0_5.py tk      # Tk: disk warning
  python harness_p0_5.py launch  # python -m blastlab [--tk]: open, shoot, close

Real platform (QT_QPA_PLATFORM unset), private settings with the sweep off
before any window (CLAUDE.md 8.2 / 8.7). WSL is stubbed for the disk
warning; delete_runs raises if called. No solve is started.

Screenshots: Win32 PrintWindow(PW_RENDERFULLCONTENT) of the app's own
top-level HWND - never a desktop grab, so nothing else on the owner's
screen is captured, and the window is never forced to the foreground.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

WT = r'C:\Users\rotem.ofek\blastlab-worktrees\todo'
OUT = os.path.join(WT, 'docs', 'qa', '2026-09-27-p0-5')
sys.path.insert(0, WT)
sys.path.insert(0, os.path.join(WT, 'blastlab', 'tests'))
os.environ.pop('QT_QPA_PLATFORM', None)
os.environ.setdefault('MPLBACKEND', 'Agg')

user32 = ctypes.windll.user32
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), str(detail)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f'  -- {detail}' if detail else ''),
          flush=True)


def private(tmp):
    os.environ['BLASTLAB_SETTINGS'] = os.path.join(tmp, 'settings.json')
    from blastlab.ui.testing import private_settings
    private_settings()
    from blastlab.core import settings as S
    from blastlab.solvers.foam import env
    assert S.load()['auto_cleanup'] is False
    assert env.auto_cleanup(S.load()) == (0, 0)
    return S


def printwindow(hwnd):
    """Win32 PrintWindow(PW_RENDERFULLCONTENT) of the real HWND."""
    from PIL import Image
    gdi32 = ctypes.windll.gdi32
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)

    class BIH(ctypes.Structure):
        _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG),
                    ('biPlanes', wt.WORD), ('biBitCount', wt.WORD),
                    ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD),
                    ('biXPelsPerMeter', wt.LONG), ('biYPelsPerMeter', wt.LONG),
                    ('biClrUsed', wt.DWORD), ('biClrImportant', wt.DWORD)]
    bi = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer('RGB', (w, h), buf, 'raw', 'BGRX', 0, 1)


def shoot(hwnd, name, pump=None):
    if pump:
        pump()
    else:
        time.sleep(0.6)
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    img = printwindow(hwnd)
    path = os.path.join(OUT, name + '.png')
    img.save(path)
    print(f'  shot {path} [PrintWindow] rect=({r.left},{r.top},{r.right},{r.bottom}) '
          f'visible={bool(user32.IsWindowVisible(hwnd))}', flush=True)
    return path


GB = 1024 ** 3
DAY = 86400.0


def runs_over_limit():
    """15 GB of fake runs, mtimes relative to now; two old finished ones."""
    now = time.time()
    root = '/root/blastlab_runs'
    return {
        f'{root}/old_a': (4 * GB, now - 30 * DAY, False),
        f'{root}/alive': (2 * GB, now - 25 * DAY, True),
        f'{root}/old_b': (3 * GB, now - 20 * DAY, False),
        f'{root}/unknown': (3 * GB, now - 18 * DAY, None),
        f'{root}/fresh_1': (1 * GB, now - 3 * DAY, False),
        f'{root}/fresh_2': (1 * GB, now - 2 * DAY, False),
        f'{root}/fresh_3': (1 * GB, now - 1 * DAY, False),
    }


def warn_settings(S):
    return dict(S.load(), auto_cleanup=False, cleanup_max_gb=10,
                cleanup_max_age_days=14)


# ── Qt ──────────────────────────────────────────────────────────────────────

def part_qt(tmp):
    S = private(tmp)
    from blastlab.ui.testing import ensure_qapp, pump
    app = ensure_qapp(offscreen=False)
    check('Qt platform is the real one', app.platformName() == 'windows',
          app.platformName())
    from PySide6.QtWidgets import QAbstractButton, QApplication, QDialog, QMessageBox
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    from blastlab.ui.app import MainWindow
    from blastlab.ui import dialogs
    from blastlab.models import hd13_case
    from blastlab.models.case import Case2D, save_case
    from blastlab.output.cli_hd13 import write_starter_case
    from blastlab.solvers.foam import env
    from test_settings_path import stub_wsl

    win = MainWindow()
    win.resize(1400, 900)
    win.show()
    pump(800)
    hwnd = int(win.winId())
    errors = []
    win.show_error = lambda t, m: errors.append((t, m))
    p = lambda: pump(600)                                      # noqa: E731

    def modals():
        out = []
        if QApplication.activeModalWidget() is not None:
            out.append(QApplication.activeModalWidget())
        out += [w for w in QApplication.topLevelWidgets()
                if w.isVisible() and isinstance(w, (QDialog, QMessageBox))]
        return out

    def button(text):
        for b in win.findChildren(QAbstractButton):
            if b.isVisible() and (b.text().strip() == text
                                  or b.toolTip().strip().startswith(text)):
                return b
        return None

    shoot(hwnd, 'q00_start', p)
    open_btn, save_btn = button('Open case…'), button('Save case…')
    check('Qt: sidebar has visible Open case… and Save case… buttons',
          open_btn is not None and save_btn is not None)

    open_target, save_target = [], []
    dialogs.open_file = lambda *a, **k: open_target[-1]
    dialogs.save_file = lambda *a, **k: save_target[-1]

    def do_open(path):
        open_target.append(path)
        QTest.mouseClick(open_btn, Qt.LeftButton)
        pump(400)

    def do_save(path):
        save_target.append(path)
        QTest.mouseClick(save_btn, Qt.LeftButton)
        pump(300)
        return path

    # 1. HD 1.3 starter: open -> save -> (form elsewhere) -> reopen
    starter = write_starter_case(os.path.join(tmp, 'starter.json'))
    want = hd13_case.case_to_dict(hd13_case.load_case(starter))
    blast_src = os.path.join(tmp, 'blast2d.json')
    save_case(Case2D(Lx=3.3), blast_src)

    do_open(starter)
    case = win.current_case()
    check('Qt HD13: starter opens into the 0-D form',
          not errors and win.setup.dim == 0
          and isinstance(case, hd13_case.DeflagrationCase)
          and hd13_case.case_to_dict(case) == want,
          f'errors={errors} dim={win.setup.dim}')
    shoot(hwnd, 'q01_hd13_starter_opened', p)

    saved = do_save(os.path.join(tmp, 'hd13_saved.json'))
    with open(saved, encoding='utf-8') as f:
        data = json.load(f)
    shutil.copy(saved, os.path.join(OUT, 'hd13_saved.json'))
    check('Qt HD13: Save case… writes schema "blastlab-hd13"',
          data.get('schema') == 'blastlab-hd13', data.get('schema'))

    do_open(blast_src)                       # move the form away first
    check('Qt HD13: form moved to 2D before reopening',
          win.setup.dim == 2, win.setup.dim)
    shoot(hwnd, 'q02_form_moved_to_2d', p)
    do_open(saved)
    case = win.current_case()
    got_d = hd13_case.case_to_dict(case) if case is not None else None
    diff = ({k: (want.get(k), got_d.get(k)) for k in set(want) | set(got_d)
             if want.get(k) != got_d.get(k)} if got_d else 'no case')
    check('Qt HD13: saved file reopens into the 0-D form, same values',
          not errors and win.setup.dim == 0
          and isinstance(case, hd13_case.DeflagrationCase) and got_d == want,
          f'errors={errors} dim={win.setup.dim} diff={diff}')
    check('Qt HD13: no modal dialog', not modals(), str(modals()))
    check('Qt HD13: Model box follows the file', win.run_panel.current_run_name(),
          win.run_panel.current_run_name())
    shoot(hwnd, 'q03_hd13_reopened', p)

    # 1b. 2D blast: open -> save -> reopen, unchanged behaviour
    do_open(blast_src)
    orig = win.current_case()
    got = do_save(os.path.join(tmp, 'blast_saved.json'))
    ref = os.path.join(tmp, 'blast_ref.json')
    save_case(orig, ref)
    with open(got, encoding='utf-8') as f:
        bschema = json.load(f).get('schema')
    same = open(got, 'rb').read() == open(ref, 'rb').read()
    check('Qt 2D: Save case… writes the blast schema, bytes == models.case.save_case',
          bschema == 'blastlab-case' and same, f'schema={bschema} same={same}')
    do_open(saved)                           # move away (0-D)
    do_open(got)
    back = win.current_case()
    ref2 = os.path.join(tmp, 'blast_ref2.json')
    save_case(back, ref2)
    check('Qt 2D: reopens as 2D with the same case',
          not errors and win.setup.dim == 2
          and open(ref2, 'rb').read() == open(ref, 'rb').read(),
          f'errors={errors} dim={win.setup.dim}')
    check('Qt 2D: no modal dialog', not modals(), str(modals()))
    shoot(hwnd, 'q04_blast2d_reopened', p)

    # 2. disk warning into the real window's sink
    win._show('setup')
    pump(200)
    notes = []
    real_notify = win.notify

    def notify(text, level='info'):
        notes.append((text, level))
        real_notify(text, level)
    win.notify = notify
    log0 = win.run_panel.log.toPlainText()
    st = warn_settings(S)
    with stub_wsl(runs_over_limit()) as (calls, _deleted):
        th = env.start_disk_warning(st, win._disk_warning, private_ok=True)
        check('Qt disk: private_ok starts the thread', th is not None)
        th.join(15)
        pump(600)
        calls = dict(calls)
    log1 = win.run_panel.log.toPlainText()
    new = log1[len(log0):] if log1.startswith(log0) else log1
    lines = [ln for ln in new.splitlines() if 'WSL runs folder' in ln]
    warns = [n for n in notes if n[1] == 'warn']
    status = win._status.text()
    print('  status:', status, flush=True)
    check('Qt disk: exactly one warn-level status notification',
          len(warns) == 1 and len(notes) == 1, str(len(notes)))
    check('Qt disk: status line shows the warning',
          status.startswith('WSL runs folder /root/blastlab_runs holds 15.0 GB'))
    check('Qt disk: exactly one Run-log line', len(lines) == 1, str(lines))
    check('Qt disk: nothing modal', not modals(), str(modals()))
    check('Qt disk: delete_runs never called', calls['delete_runs'] == 0, str(calls))
    shoot(hwnd, 'q05_disk_warning_status', p)
    win._show('run')
    pump(400)
    shoot(hwnd, 'q06_disk_warning_runlog', p)
    win.notify = real_notify

    # 3. close
    win.close()
    pump(500)
    check('Qt: window closed', not win.isVisible() and not user32.IsWindowVisible(hwnd))
    check('Qt: no error dialog recorded at any point', not errors, str(errors))


# ── Tk ──────────────────────────────────────────────────────────────────────

def part_tk(tmp):
    S = private(tmp)
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

    root = ctk.CTk()
    app = appmod.App(root)

    def pump(sec):
        end = time.monotonic() + sec
        while time.monotonic() < end:
            root.update()
            time.sleep(0.01)

    p = lambda: pump(0.8)                                      # noqa: E731
    pump(1.5)
    hwnd = int(root.wm_frame(), 16)
    shoot(hwnd, 't00_start', p)

    def toplevels():
        return [w for w in root.winfo_children()
                if isinstance(w, tk.Toplevel) and w.winfo_viewable()]

    notes = []
    real_notify = app.notify

    def notify(text, level='info'):
        notes.append((text, level))
        real_notify(text, level)
    app.notify = notify
    log0 = app.run_panel.log.get('1.0', 'end')
    st = warn_settings(S)
    with stub_wsl(runs_over_limit()) as (calls, _deleted):
        th = env.start_disk_warning(st, app._disk_warning, private_ok=True)
        check('Tk disk: private_ok starts the thread', th is not None)
        th.join(15)
        pump(0.8)
        calls = dict(calls)
    log1 = app.run_panel.log.get('1.0', 'end')
    new = log1[len(log0.rstrip('\n')):]
    lines = [ln for ln in new.splitlines() if 'WSL runs folder' in ln]
    warns = [n for n in notes if n[1] == 'warn']
    status = str(app._status.cget('text'))
    print('  status:', status, flush=True)
    check('Tk disk: exactly one warn-level status notification',
          len(warns) == 1 and len(notes) == 1, str(len(notes)))
    check('Tk disk: status line shows the warning',
          status.startswith('WSL runs folder /root/blastlab_runs holds 15.0 GB'))
    check('Tk disk: exactly one Run-log line', len(lines) == 1, str(lines))
    check('Tk disk: nothing modal (no messagebox, no Toplevel)',
          not modal_calls and not toplevels(), f'{modal_calls} {toplevels()}')
    check('Tk disk: delete_runs never called', calls['delete_runs'] == 0, str(calls))
    shoot(hwnd, 't01_disk_warning_status', p)
    app._show('run')
    pump(0.6)
    shoot(hwnd, 't02_disk_warning_runlog', p)
    app.notify = real_notify

    app._on_close()
    try:
        root.update()
    except tk.TclError:
        pass
    alive = True
    try:
        alive = bool(root.winfo_exists())
    except tk.TclError:
        alive = False
    check('Tk: window destroyed by _on_close',
          not alive and not user32.IsWindowVisible(hwnd))


# ── real launches ───────────────────────────────────────────────────────────

EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def top_windows():
    out = {}

    def cb(h, _l):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, buf, n + 1)
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            out[h] = (buf.value, pid.value)
        return True
    user32.EnumWindows(EnumProc(cb), 0)
    return out


def part_launch(tmp):
    private(tmp)
    envv = dict(os.environ)
    envv.pop('QT_QPA_PLATFORM', None)
    for tag, args in (('qt', []), ('tk', ['--tk'])):
        before = set(top_windows())
        errf = os.path.join(tmp, f'{tag}_stderr.txt')
        outf = os.path.join(tmp, f'{tag}_stdout.txt')
        with open(errf, 'w') as fe, open(outf, 'w') as fo:
            t0 = time.monotonic()
            proc = subprocess.Popen([sys.executable, '-u', '-m', 'blastlab', *args],
                                    cwd=WT, env=envv, stdout=fo, stderr=fe)
            hwnd = None
            while time.monotonic() - t0 < 40 and proc.poll() is None:
                for h, (title, _pid) in top_windows().items():
                    if h not in before and title.startswith('blastlab'):
                        hwnd = h
                        break
                if hwnd:
                    break
                time.sleep(0.3)
            startup = time.monotonic() - t0
            check(f'launch {tag}: window appeared ({startup:.1f} s)',
                  hwnd is not None, f'rc={proc.poll()}')
            if hwnd:
                time.sleep(3)
                title = top_windows().get(hwnd, ('?',))[0]
                r = wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                print(f'  {tag}: title={title!r} size={r.right - r.left}x{r.bottom - r.top}')
                shoot(hwnd, f'l_{tag}_window')
                user32.PostMessageW(hwnd, 0x0010, 0, 0)          # WM_CLOSE
            try:
                rc = proc.wait(30)
            except subprocess.TimeoutExpired:
                proc.kill()
                rc = 'HUNG (killed)'
        err = open(errf, encoding='utf-8', errors='replace').read()
        out = open(outf, encoding='utf-8', errors='replace').read()
        print(f'  {tag}: rc={rc}\n  stderr: {err[-1500:]!r}\n  stdout: {out[-800:]!r}')
        check(f'launch {tag}: WM_CLOSE ends the process with rc 0, no traceback',
              rc == 0 and 'Traceback' not in err, f'rc={rc}')
        leftovers = [h for h, (t, _p) in top_windows().items()
                     if h not in before and t.startswith('blastlab')]
        check(f'launch {tag}: no window left behind', not leftovers, str(leftovers))


if __name__ == '__main__':
    part = sys.argv[1]
    tmp = tempfile.mkdtemp(prefix=f'blastlab_qa_p05_{part}_')
    try:
        {'qt': part_qt, 'tk': part_tk, 'launch': part_launch}[part](tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [r for r in RESULTS if not r[1]]
    print(f'{part}: {len(RESULTS) - len(bad)}/{len(RESULTS)} PASS')
    sys.exit(1 if bad else 0)
