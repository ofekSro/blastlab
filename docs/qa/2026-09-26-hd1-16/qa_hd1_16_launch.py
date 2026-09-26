"""QA part 3: the real entry point `python -m blastlab --case <hd13 json>`
in its own process (startup, what the window shows, WM_CLOSE shutdown),
plus a status-line width measurement for the DEFAULT report path.
Throwaway, docs/qa. Run:  python qa_hd1_16_launch.py <scratch_dir>
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
OUT = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.abspath(sys.argv[1])
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
u = ctypes.windll.user32
ctypes.windll.shcore.SetProcessDpiAwareness(2)


def windows_of(pid):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _l):
        p = wt.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(h, b, 256)
            r = wt.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            out.append((h, b.value, (r.left, r.top, r.right - r.left, r.bottom - r.top)))
        return True
    u.EnumWindows(cb, 0)
    return out


def pw(h, path):
    from PIL import Image
    g = ctypes.windll.gdi32
    r = wt.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    w, hh = r.right - r.left, r.bottom - r.top
    hdc = u.GetWindowDC(h)
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, hh)
    g.SelectObject(mdc, bmp)
    u.PrintWindow(h, mdc, 2)

    class BIH(ctypes.Structure):
        _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG),
                    ('biPlanes', wt.WORD), ('biBitCount', wt.WORD),
                    ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD),
                    ('biXPelsPerMeter', wt.LONG), ('biYPelsPerMeter', wt.LONG),
                    ('biClrUsed', wt.DWORD), ('biClrImportant', wt.DWORD)]
    bih = BIH(ctypes.sizeof(BIH), w, -hh, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * hh * 4)
    g.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.byref(bih), 0)
    Image.frombuffer('RGBA', (w, hh), buf.raw, 'raw', 'BGRA', 0, 1).convert('RGB').save(path)


env = dict(os.environ)
env.pop('QT_QPA_PLATFORM', None)
env['PYTHONPATH'] = REPO
env['BLASTLAB_SETTINGS'] = os.path.join(SCR, 'settings.json')     # auto_cleanup false
proc = subprocess.Popen([sys.executable, '-m', 'blastlab', '--case', os.path.join(SCR, 'tc.json')],
                        cwd=SCR, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
seen = []
t0 = time.monotonic()
while time.monotonic() - t0 < 25:
    ws = windows_of(proc.pid)
    if any(t == 'Open case' for _h, t, _r in ws) and any(t.startswith('blastlab') for _h, t, _r in ws):
        break
    if proc.poll() is not None:
        break
    time.sleep(0.5)
time.sleep(1.5)
ws = windows_of(proc.pid)
print('startup took %.1f s; windows:' % (time.monotonic() - t0), ws)
for h, title, _r in ws:
    name = '13_launch_case_' + ('dialog' if title == 'Open case' else 'main') + '.png'
    pw(h, os.path.join(OUT, name))
    print('  shot', name, title)
# close the dialog (WM_CLOSE), wait for the main window, shoot it, close it
for h, title, _r in ws:
    if title == 'Open case':
        u.PostMessageW(h, 0x0010, 0, 0)
t1 = time.monotonic()
main = None
while time.monotonic() - t1 < 20 and main is None:
    time.sleep(0.5)
    for h, title, _r in windows_of(proc.pid):
        if title.startswith('blastlab'):
            main = h
time.sleep(2)
print('after the dialog:', windows_of(proc.pid))
if main:
    pw(main, os.path.join(OUT, '13_launch_case_main.png'))
    print('  shot 13_launch_case_main.png')
    u.PostMessageW(main, 0x0010, 0, 0)          # WM_CLOSE = the title-bar X
try:
    out, err = proc.communicate(timeout=20)
    print('exit code', proc.returncode)
except subprocess.TimeoutExpired:
    proc.kill()
    out, err = proc.communicate()
    print('did not exit on WM_CLOSE; killed')
print('stdout tail:', out[-800:])
print('stderr tail:', err[-1500:])
