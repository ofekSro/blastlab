"""Shared helpers for the OUT-1 QA pass (2026-09-26).

Private settings (CLAUDE.md 8.2), Win32 window helpers (ctypes, the ground
truth for native dialogs - CLAUDE.md 8.7), screenshots and a JSON log.
Nothing here edits application code.

Screenshots of native windows use PrintWindow(PW_RENDERFULLCONTENT): the
window renders itself into our bitmap, so another application lying on
top of it on the owner's desktop cannot end up in the picture (ImageGrab
of the screen rectangle did exactly that on the first try).
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import threading
import time

REPO = r'C:\Users\rotem.ofek\blastlab-worktrees\out-track'
OUT = os.path.join(REPO, 'docs', 'qa', '2026-09-26-out-1')
QA_ROOT = r'C:\Users\rotem.ofek\blastlab_qa\out1_20260926_191440'
RUNS = os.path.join(QA_ROOT, 'runs')
SETTINGS = os.path.join(QA_ROOT, 'settings.json')

if REPO not in sys.path:
    sys.path.insert(0, REPO)


def private_env():
    """BLASTLAB_SETTINGS -> the QA root's own file, auto_cleanup False
    verified BEFORE any GUI is built. Real windows: QT_QPA_PLATFORM unset."""
    os.environ['BLASTLAB_SETTINGS'] = SETTINGS
    os.environ.pop('QT_QPA_PLATFORM', None)
    os.environ.setdefault('MPLBACKEND', 'Agg')
    os.makedirs(RUNS, exist_ok=True)
    from blastlab.ui.testing import disable_cleanup
    disable_cleanup(SETTINGS)
    from blastlab.core import settings as s
    d = s.load()
    assert os.path.normcase(s.config_path()) == os.path.normcase(SETTINGS), \
        s.config_path()
    assert d['auto_cleanup'] is False, d
    return d


LOG_PATH = None


def set_log(name, append=False):
    global LOG_PATH
    LOG_PATH = os.path.join(OUT, f'{name}.jsonl')
    if not append:
        open(LOG_PATH, 'w', encoding='utf-8').close()


def rec(kind, **kw):
    kw = dict(kind=kind, t=time.strftime('%H:%M:%S'), **kw)
    line = json.dumps(kw, default=str, ensure_ascii=False)
    print(line[:1500], flush=True)
    if LOG_PATH:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def tree(folder):
    out = []
    for root, _d, files in os.walk(folder):
        for n in files:
            p = os.path.join(root, n)
            out.append((os.path.relpath(p, folder).replace('\\', '/'),
                        os.path.getsize(p)))
    return sorted(out)


# ── Win32 ────────────────────────────────────────────────────────────────
user32 = ctypes.WinDLL('user32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wt.LPARAM]
user32.EnumChildWindows.argtypes = [wt.HWND, EnumWindowsProc, wt.LPARAM]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND,
                                            ctypes.POINTER(wt.DWORD)]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetDlgCtrlID.argtypes = [wt.HWND]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.GetWindowDC.argtypes = [wt.HWND]
user32.GetWindowDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT,
                            ctypes.c_void_p, ctypes.c_void_p, wt.UINT]

WM_CLOSE = 0x0010
BM_CLICK = 0x00F5
DM_GETDEFID = 0x0400
VK_RETURN = 0x0D
WM_GETTEXT, WM_GETTEXTLENGTH = 0x000D, 0x000E


def _text(h):
    buf = ctypes.create_unicode_buffer(1024)
    user32.GetWindowTextW(h, buf, 1024)
    return buf.value


def _long_text(h):
    n = int(user32.SendMessageW(h, WM_GETTEXTLENGTH, 0, 0))
    buf = ctypes.create_unicode_buffer(n + 2)
    user32.SendMessageW(h, WM_GETTEXT, n + 1,
                        ctypes.cast(buf, ctypes.c_void_p).value)
    return buf.value


def _cls(h):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, buf, 256)
    return buf.value


def _pid(h):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def top_windows(pid=None):
    pid = pid or os.getpid()
    out = []

    def cb(h, _l):
        if _pid(h) == pid and user32.IsWindowVisible(h):
            out.append((h, _cls(h), _text(h)))
        return True
    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return out


def children(h):
    out = []

    def cb(c, _l):
        out.append(c)
        return True
    user32.EnumChildWindows(h, EnumWindowsProc(cb), 0)
    return out


def rect(h):
    r = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG),
                ('biHeight', wt.LONG), ('biPlanes', wt.WORD),
                ('biBitCount', wt.WORD), ('biCompression', wt.DWORD),
                ('biSizeImage', wt.DWORD), ('biXPelsPerMeter', wt.LONG),
                ('biYPelsPerMeter', wt.LONG), ('biClrUsed', wt.DWORD),
                ('biClrImportant', wt.DWORD)]


def grab_hwnd(h, path):
    """PrintWindow the top-level `h` (frame included) into `path`."""
    from PIL import Image
    l, t, r, b = rect(h)
    w, hgt = r - l, b - t
    hdc = user32.GetWindowDC(h)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, hgt)
    old = gdi32.SelectObject(mdc, bmp)
    ok = user32.PrintWindow(h, mdc, 2)          # PW_RENDERFULLCONTENT
    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight = w, -hgt           # top-down
    bi.biPlanes, bi.biBitCount = 1, 32
    buf = ctypes.create_string_buffer(w * hgt * 4)
    gdi32.GetDIBits(mdc, bmp, 0, hgt, buf, ctypes.byref(bi), 0)
    gdi32.SelectObject(mdc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(h, hdc)
    Image.frombuffer('RGB', (w, hgt), buf, 'raw', 'BGRX', 0, 1).save(path)
    if not ok:
        raise OSError('PrintWindow failed')
    return path


def dialog_info(h):
    """Title, the static texts, the buttons (text, id, is-default)."""
    kids = children(h)
    texts, buttons, edits = [], [], []
    defid = int(user32.SendMessageW(h, DM_GETDEFID, 0, 0))
    def_id = (defid & 0xFFFF) if ((defid >> 16) & 0xFFFF) == 0x534B else None
    for c in kids:
        k = _cls(c)
        if k == 'Static':
            t = _long_text(c)
            if t.strip():
                texts.append(t)
        elif k == 'Edit':
            t = _long_text(c)
            if t.strip():
                edits.append(t)
        elif k == 'Button':
            style = user32.GetWindowLongW(c, -16)
            buttons.append(dict(text=_text(c), id=user32.GetDlgCtrlID(c),
                                defpush=bool((style & 0xF) == 1), hwnd=c))
    return dict(title=_text(h), cls=_cls(h), texts=texts, edits=edits,
                buttons=buttons, def_id=def_id)


class NativeDialogWatcher(threading.Thread):
    """Watch this process for a native #32770 dialog (a Tk messagebox, a
    Windows file dialog), screenshot it, record what it says and answer
    it with `answer(info) -> ('button', text) | ('enter',) | ('close',)`.
    One dialog per watcher."""

    def __init__(self, shot_path, answer, timeout=60, title_has=None):
        super().__init__(daemon=True)
        self.shot_path, self.answer = shot_path, answer
        self.timeout, self.title_has = timeout, title_has
        self.info = None
        self.done = threading.Event()

    def run(self):
        end = time.time() + self.timeout
        try:
            while time.time() < end:
                for h, k, t in top_windows():
                    if k == '#32770' and (self.title_has is None
                                          or self.title_has in t):
                        time.sleep(1.2)       # let it paint
                        self.info = dialog_info(h)
                        try:
                            grab_hwnd(h, self.shot_path)
                            self.info['shot'] = os.path.basename(
                                self.shot_path)
                        except Exception as exc:
                            self.info['shot_error'] = str(exc)
                        act = self.answer(self.info)
                        self.info['action'] = act
                        if act[0] == 'button':
                            for b in self.info['buttons']:
                                if b['text'].replace('&', '') == act[1]:
                                    user32.PostMessageW(b['hwnd'], BM_CLICK,
                                                        0, 0)
                                    break
                        elif act[0] == 'enter':
                            # a real keypress: the dialog is foreground
                            user32.SetForegroundWindow(h)
                            time.sleep(0.3)
                            self.info['fg_ok'] = (
                                user32.GetForegroundWindow() == h)
                            press_enter()
                        else:
                            user32.PostMessageW(h, WM_CLOSE, 0, 0)
                        for b in self.info['buttons']:
                            b.pop('hwnd', None)
                        return
                time.sleep(0.15)
        finally:
            self.done.set()


user32.GetForegroundWindow.restype = wt.HWND


class INPUT_KI(ctypes.Structure):
    _fields_ = [('wVk', wt.WORD), ('wScan', wt.WORD), ('dwFlags', wt.DWORD),
                ('time', wt.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class _INPUT_U(ctypes.Union):
    _fields_ = [('ki', INPUT_KI), ('pad', ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _anonymous_ = ('u',)
    _fields_ = [('type', wt.DWORD), ('u', _INPUT_U)]


def press_enter():
    down = INPUT(type=1)
    down.ki = INPUT_KI(VK_RETURN, 0, 0, 0, 0)
    up = INPUT(type=1)
    up.ki = INPUT_KI(VK_RETURN, 0, 2, 0, 0)
    arr = (INPUT * 2)(down, up)
    return user32.SendInput(2, arr, ctypes.sizeof(INPUT))
