"""QA harness for batch 2026-09-26-hd1-16-load-export (throwaway, docs/qa).

REAL window (QT_QPA_PLATFORM removed, CLAUDE.md 8.7), private settings file
with auto_cleanup false (8.2), Win32 as ground truth for visibility.
Screenshots: this RDP session's desktop cannot be BitBlt-ed (PIL ImageGrab
raises 'screen grab failed'), so windows are captured with Win32
PrintWindow(PW_RENDERFULLCONTENT). Case/report files go only under SCR.
Never edits application code.

Run:  python qa_hd1_16_harness.py <scratch_dir>
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import threading
import time
from dataclasses import replace

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, REPO)
OUT = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.abspath(sys.argv[1])
os.environ.pop('QT_QPA_PLATFORM', None)
os.environ['BLASTLAB_SETTINGS'] = os.path.join(SCR, 'settings.json')

from blastlab.ui.testing import disable_cleanup, pump        # noqa: E402
disable_cleanup(os.environ['BLASTLAB_SETTINGS'])
from blastlab.core import settings as _s                      # noqa: E402
assert _s.load()['auto_cleanup'] is False, 'settings: auto_cleanup not False'
print('settings file', _s.config_path(), 'auto_cleanup', _s.load()['auto_cleanup'])

from PIL import Image, ImageGrab                              # noqa: E402
from PySide6.QtCore import QPoint, Qt, QTimer                 # noqa: E402
from PySide6.QtTest import QTest                              # noqa: E402
from PySide6.QtWidgets import QApplication                    # noqa: E402

user32 = ctypes.windll.user32
_wd = threading.Timer(1200, lambda: os._exit(3))    # never outlive 20 min
_wd.daemon = True
_wd.start()
RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), str(detail)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f' - {detail}' if detail else ''),
          flush=True)


def hwnd(w):
    return int(w.winId())


def rect(h):
    r = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def w32_visible(w):
    return bool(user32.IsWindowVisible(hwnd(w)))


def printwindow(h):
    gdi32 = ctypes.windll.gdi32
    l, t, r, b = rect(h)
    w, hh = r - l, b - t
    hdc = user32.GetWindowDC(h)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, hh)
    gdi32.SelectObject(mdc, bmp)
    ok = user32.PrintWindow(h, mdc, 2)

    class BIH(ctypes.Structure):
        _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG),
                    ('biPlanes', wt.WORD), ('biBitCount', wt.WORD),
                    ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD),
                    ('biXPelsPerMeter', wt.LONG), ('biYPelsPerMeter', wt.LONG),
                    ('biClrUsed', wt.DWORD), ('biClrImportant', wt.DWORD)]
    bih = BIH(ctypes.sizeof(BIH), w, -hh, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * hh * 4)
    gdi32.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.byref(bih), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(h, hdc)
    return Image.frombuffer('RGBA', (w, hh), buf.raw, 'raw', 'BGRA', 0, 1).convert('RGB'), bool(ok)


def screen(name, h):
    pump(300)
    l, t, r, b = rect(h)
    try:
        img = ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)
        how = 'ImageGrab'
    except OSError:
        img, ok = printwindow(h)
        how = f'PrintWindow(ok={ok})'
    img.save(os.path.join(OUT, name))
    print('  screenshot', name, (l, t, r - l, b - t), how, flush=True)
    return img


def front(win):
    h = hwnd(win)
    user32.SetWindowPos(h, -1, 0, 0, 0, 0, 0x0001 | 0x0002)     # topmost
    user32.SetForegroundWindow(h)
    win.raise_()
    win.activateWindow()
    pump(250)


def box_pixels(win, widget, img):
    """Mean RGB of `widget`'s area in the window screenshot `img`."""
    top = widget.mapTo(win, QPoint(0, 0))
    wl, wt_, _, _ = rect(hwnd(win))
    # client origin of the frame in screen coords
    cp = win.mapToGlobal(QPoint(0, 0))
    ratio = win.devicePixelRatioF()
    x0 = int((cp.x() * ratio if False else 0))
    gx = win.mapToGlobal(top)
    # Qt global coords are device-independent; Win32 rect is physical
    x = int(gx.x() * ratio) - wl + 4
    y = int(gx.y() * ratio) - wt_ + 4
    w = int(widget.width() * ratio) - 8
    h = int(widget.height() * ratio) - 8
    crop = img.crop((x, y, x + w, y + h))
    px = list(crop.getdata())
    n = max(len(px), 1)
    return tuple(round(sum(p[i] for p in px) / n, 1) for i in range(3)), (x, y, w, h), x0


DLG = []


def arm_modal_catcher(tag, delay=900):
    """Capture (screenshot, title, text) of the next modal and close it, so
    a dialog never blocks the harness."""
    def grab():
        w = QApplication.activeModalWidget()
        if w is None:
            QTimer.singleShot(300, grab) if time.monotonic() < deadline else None
            return
        rec = dict(tag=tag, title=w.windowTitle(),
                   text=w.text() if hasattr(w, 'text') else '')
        h = hwnd(w)
        user32.SetWindowPos(h, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
        pump(250)
        rec['visible'] = bool(user32.IsWindowVisible(h))
        rec['rect'] = rect(h)
        screen(f'{tag}.png', h)
        DLG.append(rec)
        print('  modal:', rec, flush=True)
        w.accept() if hasattr(w, 'accept') else w.close()
    deadline = time.monotonic() + 6
    QTimer.singleShot(delay, grab)


def last_dialog(tag):
    for r in reversed(DLG):
        if r['tag'] == tag:
            return r
    return None


# ── the app, built exactly as ui/app.main builds it ─────────────────────
from blastlab.ui import crashlog, theme                       # noqa: E402
crashlog.install()
_prev_hook = sys.excepthook
CRASHES = []


def _hook(*a):
    CRASHES.append(a)
    _prev_hook(*a)


sys.excepthook = _hook
app = QApplication.instance() or QApplication(['blastlab'])
app.setApplicationName('blastlab')
theme.apply(app, 'dark')
from blastlab.ui.app import MainWindow                        # noqa: E402
from blastlab.ui import dialogs                               # noqa: E402
from blastlab.core import assessment                          # noqa: E402

T = os.path.join(SCR, 't.json')                   # --hd13-new output
TC = os.path.join(SCR, 'tc.json')                 # clearing on, H=3, W=4
base = assessment.load_case(T)
assessment.save_case(replace(base, clearing=True, wall_H_m=3.0, wall_W_m=4.0), TC)


def open_case(path, tag):
    """The app's own Open case (win._open_case(path)); a dialog it raises is
    captured and closed. Returns the dialog record or None."""
    n = len(DLG)
    arm_modal_catcher(tag)
    win._open_case(path)
    pump(1200)
    return DLG[-1] if len(DLG) > n else None


def load_into_form(path):
    """Fallback when Open case refuses: what the Open would do for an HD 1.3
    file, through the HD 1.3 reader and the panel's set_case."""
    win.setup.set_case(assessment.load_case(path))
    win._schedule_validate()
    pump(1200)


win = MainWindow()
win.resize(1400, 950)
win.show()
pump(800)
front(win)
check('window visible per Win32', w32_visible(win), str(rect(hwnd(win))))
check('window title set', bool(win.windowTitle()), win.windowTitle())

# ── 1. Setup -> 0D (HD 1.3) form ─────────────────────────────────────────
print('\n1. Setup -> 0-D form')
win._show('setup')
pump(200)
QTest.mouseClick(win.setup.dim_seg._btns['0D'], Qt.LeftButton)
pump(600)
form = win.setup.form
check('0-D form is the active one', win.setup.dim == 0 and form is win.setup.forms[0])
wall_card = form.cards['Loaded wall']
struct_card = form.cards['Structure']
heat_card = form.cards['Heat']
Hw, Ww, cb = form.widgets['wall_H_m'], form.widgets['wall_W_m'], form.widgets['clearing']
win.setup._scroll.ensureWidgetVisible(wall_card, 50, 50)
pump(300)
front(win)
img_off = screen('01_0d_form_default.png', hwnd(win))
px_off = box_pixels(win, Hw, img_off)[0]

for w in (struct_card, heat_card, wall_card):
    w.setAttribute(Qt.WA_NativeWindow, True)
pump(300)
check('1a Structure card NOT on screen (Win32 IsWindowVisible on its HWND)',
      not w32_visible(struct_card) and struct_card.isHidden(),
      f'w32={w32_visible(struct_card)} qtHidden={struct_card.isHidden()}')
check('1a probe sanity: Heat card IS visible per Win32', w32_visible(heat_card))
check('1b Loaded wall card visible per Win32', w32_visible(wall_card))
titles_on_screen = [t for t, c in form.cards.items() if not c.isHidden()]
check('1a no visible card titled Structure', 'Structure' not in titles_on_screen,
      ', '.join(titles_on_screen))
lbl = {k: form.label_text(k) for k in ('wall_H_m', 'wall_W_m')}
check('1b labels Wall height H [m] / Wall width W [m] + clearing checkbox',
      lbl['wall_H_m'].replace('\n', ' ') == 'Wall height H [m]'
      and lbl['wall_W_m'] == 'Wall width W [m]' and cb.__class__.__name__ == 'QCheckBox',
      f'{lbl} checkbox={cb.text()!r}')
check('1b clearing unticked by default', not cb.isChecked())
check('1b H,W disabled while clearing off (Qt isEnabled)',
      not Hw.isEnabled() and not Ww.isEnabled(), f'H={Hw.isEnabled()} W={Ww.isEnabled()}')

# a real mouse click on the checkbox indicator
QTest.mouseClick(cb, Qt.LeftButton, Qt.NoModifier, QPoint(8, cb.height() // 2))
pump(500)
check('1b clicking ticks clearing', cb.isChecked() and form.v['clearing'].get() is True)
check('1b H,W enabled once ticked (Qt isEnabled)', Hw.isEnabled() and Ww.isEnabled())
front(win)
img_on = screen('02_0d_clearing_ticked.png', hwnd(win))
px_on = box_pixels(win, Hw, img_on)[0]
print('  H box mean RGB: disabled', px_off, 'enabled', px_on)
check('1b (visual) the disabled H box looks different from the enabled one',
      max(abs(a - b) for a, b in zip(px_off, px_on)) >= 6,
      f'mean RGB disabled {px_off} vs enabled {px_on}')
# type into H while enabled: accepted
QTest.mouseClick(Hw, Qt.LeftButton)
QTest.keyClicks(Hw, '3')
pump(200)
check('1b typing into the enabled H box works', Hw.text() == '3', repr(Hw.text()))
Hw.setText('')
form.v['wall_H_m'].set('')
QTest.mouseClick(cb, Qt.LeftButton, Qt.NoModifier, QPoint(8, cb.height() // 2))
pump(500)
check('1b unticking disables H,W again (Qt isEnabled)',
      not cb.isChecked() and not Hw.isEnabled() and not Ww.isEnabled())
# a click on the disabled box does not give it focus / accept keys
QTest.mouseClick(Hw, Qt.LeftButton)
QTest.keyClicks(Hw, '9')
pump(200)
check('1b the disabled H box ignores typing', Hw.text() == '', repr(Hw.text()))

# a 2D solver-mode switch must not bring the Structure card back at 0D
QTest.mouseClick(win.setup.dim_seg._btns['2D'], Qt.LeftButton)
pump(400)
print('  solver before switch:', win._solver_seg.get())
QTest.mouseClick(win._solver_seg._btns['native'], Qt.LeftButton)   # towards native only: no WSL probe
pump(400)
QTest.mouseClick(win.setup.dim_seg._btns['0D'], Qt.LeftButton)
pump(500)
check('1a Structure card still hidden after 2D + solver switch and back (Win32)',
      not w32_visible(struct_card) and struct_card.isHidden())

# ── 1c. the app's Open case / Save case with HD 1.3 files ────────────────
print('\n1c. Open case / Save case')
d = open_case(TC, 'F1_open_tc_json_refused')
check('1c the app\'s Open case opens tc.json (clearing on, H=3, W=4)', d is None,
      f"dialog {d['title']!r}: {d['text']!r}" if d else '')
d = open_case(T, 'F1b_open_starter_refused')
check('1c the app\'s Open case opens the --hd13-new starter t.json', d is None,
      f"dialog {d['title']!r}: {d['text']!r}" if d else '')
# form-level load (the HD 1.3 reader + the panel's set_case)
load_into_form(TC)
form = win.setup.form
check('1c [form level] tc.json loads: 0-D, clearing ticked, H=3, W=4, H/W enabled',
      win.setup.dim == 0 and cb.isChecked() and Hw.text() == '3' and Ww.text() == '4'
      and Hw.isEnabled() and Ww.isEnabled(),
      f'dim={win.setup.dim} cb={cb.isChecked()} H={Hw.text()!r} W={Ww.text()!r}')
check('1c Structure card still hidden after load (Win32)', not w32_visible(struct_card))
win.setup._scroll.ensureWidgetVisible(wall_card, 50, 50)
front(win)
screen('03_loaded_tc_json.png', hwnd(win))

# the app's Save case (only the path dialog is stood in for)
app_saved = os.path.join(SCR, 'tc_app_saved.json')
if os.path.exists(app_saved):
    os.remove(app_saved)
orig = dialogs.save_file
dialogs.save_file = lambda *a, **k: app_saved
arm_modal_catcher('F2_save_dialog')
try:
    win._save_case()
finally:
    dialogs.save_file = orig
pump(1200)
a = open(TC, 'rb').read()
b = open(app_saved, 'rb').read() if os.path.exists(app_saved) else b''
ja, jb = json.loads(a), (json.loads(b) if b else {})
diff = sorted(k for k in set(ja) | set(jb) if ja.get(k) != jb.get(k))
check('1c the app\'s Save case writes tc.json back byte-identical', a == b,
      f'bytes_equal={a == b}; keys that differ: ' + ', '.join(
          f'{k}: {ja.get(k)!r} -> {jb.get(k)!r}' for k in diff))
check('1c [values] clearing/H/W and the six Structure keys survive the app save',
      all(ja.get(k) == jb.get(k) for k in ('clearing', 'wall_H_m', 'wall_W_m', 'span_m',
                                           'mass_per_area', 'Ru_pa', 'kE_pa_m', 'support',
                                           'rotation_limit_deg')))
d = open_case(app_saved, 'F2b_reopen_app_saved_refused')
check('1c the app reopens the file its own Save case wrote', d is None,
      f"dialog {d['title']!r}: {d['text']!r}" if d else '')
# the form -> HD 1.3 writer (what test_ui_hd13_form pins)
load_into_form(TC)
form_saved = os.path.join(SCR, 'tc_form_saved.json')
assessment.save_case(win.setup.get_case(), form_saved)
check('1c [form level] form -> HD 1.3 writer gives tc.json back byte-identical',
      open(form_saved, 'rb').read() == a)
load_into_form(T)
form_saved_t = os.path.join(SCR, 't_form_saved.json')
assessment.save_case(win.setup.get_case(), form_saved_t)
check('1c [form level] starter t.json (clearing off) round-trips byte-identical, no wall keys',
      open(form_saved_t, 'rb').read() == open(T, 'rb').read())
check('1c starter loads with clearing off and H,W disabled', not cb.isChecked()
      and not Hw.isEnabled())

# ── 1d. clearing ticked with H blank: Run refused naming wall_H_m ────────
print('\n1d. H blank')
load_into_form(TC)
win.setup._scroll.ensureWidgetVisible(Hw, 50, 50)
pump(200)
front(win)
QTest.mouseClick(Hw, Qt.LeftButton)
QTest.keyClick(Hw, Qt.Key_A, Qt.ControlModifier)
QTest.keyClick(Hw, Qt.Key_Backspace)
pump(1500)                # the validate debounce
rows = win.setup.report_rows()
check('1d H is blank in the widget', Hw.text() == '', repr(Hw.text()))
check('1d Setup validation shows an error naming wall_H_m',
      any(sev == 'error' and 'wall_H_m' in m for sev, m in rows),
      ' | '.join(m for _s2, m in rows if 'wall' in m))
front(win)
screen('04_h_blank_validation.png', hwnd(win))
rb = win.run_panel.run_btn
win._show('run')
pump(400)
check('1d Run button disabled while H is blank (Qt)', not rb.isEnabled())
front(win)
screen('04b_h_blank_run_tab.png', hwnd(win))
win._show('setup')
pump(300)
arm_modal_catcher('05_run_refused_dialog')
QTest.keyClick(win, Qt.Key_F5)       # the keyboard path to Run
pump(1500)
d = last_dialog('05_run_refused_dialog')
if d is None:                        # the shortcut did not reach: call the slot
    arm_modal_catcher('05_run_refused_dialog')
    win._run_single()
    pump(1500)
    d = last_dialog('05_run_refused_dialog')
check('1d Run (F5) refused with a dialog naming wall_H_m',
      d is not None and 'wall_H_m' in d['text'],
      f"{d}" if d else 'no dialog')
check('1d no run started', not getattr(win, '_hd13_busy', False))
check('1d other inputs kept (clearing ticked, W=4, charge 5)',
      cb.isChecked() and Ww.text() == '4' and form.widgets['charge_kg'].text() == '5')

# ── resize ───────────────────────────────────────────────────────────────
print('\nresize')
for (w_, h_), name in (((900, 600), '06_resize_900x600.png'),
                       ((1600, 1000), '07_resize_1600x1000.png')):
    win.resize(w_, h_)
    pump(600)
    win.setup._scroll.ensureWidgetVisible(wall_card, 50, 50)
    front(win)
    screen(name, hwnd(win))
    check(f'resize {w_}x{h_}: Loaded wall still visible (Win32), Structure not',
          w32_visible(wall_card) and not w32_visible(struct_card))
win.resize(1400, 950)
pump(300)

# ── 2. run the starter case ──────────────────────────────────────────────
print('\n2. run the starter case')
load_into_form(T)
run_dir = os.path.join(SCR, 'run')
os.makedirs(run_dir, exist_ok=True)
report = os.path.join(run_dir, 't_hd13.html')
for f in os.listdir(run_dir):
    pass
form.v['report_file'].set(report)
pump(1500)
win._show('run')
pump(400)
check('2 Run button enabled for the starter case', rb.isEnabled())
front(win)
t0 = time.monotonic()
QTest.mouseClick(rb, Qt.LeftButton)
pump(1500)
check('2 busy after the click: Run greyed', not rb.isEnabled(), win._status.text())
front(win)
screen('08_run_busy.png', hwnd(win))
end = time.monotonic() + 900
mid = False
while getattr(win, '_hd13_busy', False) and time.monotonic() < end:
    pump(50)
    if not mid and time.monotonic() - t0 > 15:
        mid = True
        screen('08b_run_busy_15s.png', hwnd(win))   # repaints while running
dt = time.monotonic() - t0
pump(200)
status = win._status.text()
print('  run took %.1f s' % dt)
print('  STATUS:', status)
front(win)
screen('09_run_done_status.png', hwnd(win))
win._show('setup')
pump(300)
front(win)
screen('10_run_done_status_setup_tab.png', hwnd(win))
check('2 status names the CSV folder (<report>_loads)',
      't_hd13_loads' in status and 'CSV' in status, status)
check('2 status carries "record ends while the load is still active: p = ... kPa at t = ... ms"',
      'record ends while the load is still active: p = ' in status
      and ' kPa at t = ' in status and status.rstrip().endswith('ms'), status)
st = win._status
fm = st.fontMetrics()
check('2 (visual) status label wide enough to show the whole message',
      fm.horizontalAdvance(st.text()) <= st.width() or st.wordWrap(),
      f'text {fm.horizontalAdvance(st.text())} px, label {st.width()} px, wrap={st.wordWrap()}')
json.dump({'status': status, 'seconds': dt, 'report': report,
           'loads': os.path.join(run_dir, 't_hd13_loads')},
          open(os.path.join(SCR, 'run_result.json'), 'w'), indent=1)
print('  waiting 13 s for the status timer')
pump(13000)
check('(info) status line cleared after its 12 s timer', win._status.text() == '',
      repr(win._status.text()[:60]))
screen('11_status_after_12s.png', hwnd(win))

print('\nclose')
check('no unhandled exceptions in the GUI', not CRASHES, str(CRASHES[:1]))
json.dump(DLG, open(os.path.join(SCR, 'dialogs.json'), 'w'), indent=1)
user32.SetWindowPos(hwnd(win), -2, 0, 0, 0, 0, 0x0001 | 0x0002)
win.close()
pump(400)
app.quit()
json.dump(RESULTS, open(os.path.join(SCR, 'gui_results.json'), 'w'), indent=1)
n_fail = sum(1 for r in RESULTS if not r[1])
print(f'\nGUI harness: {len(RESULTS) - n_fail} pass, {n_fail} fail', flush=True)
os._exit(1 if n_fail else 0)
