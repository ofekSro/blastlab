"""QA re-run after the F2 fix (1b7817d, 50ad65b) - throwaway, docs/qa.

REAL window (QT_QPA_PLATFORM removed, CLAUDE.md 8.7), window built the way
ui/app.main builds it, at its own default size; private BLASTLAB_SETTINGS
with auto_cleanup false (8.2); env.auto_cleanup is never called; no WSL.
Win32 is the ground truth for the label rect and visibility. Screenshots
by ImageGrab, falling back to PrintWindow(PW_RENDERFULLCONTENT) on the
window's own HWND. Output: screenshots prefixed R_ in this folder, and case
and run output only under SCR.

Run:  python qa_hd1_16_rerun.py <scratch_dir>     (SCR must hold t.json)
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import threading
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, REPO)
OUT = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.abspath(sys.argv[1])
os.environ.pop('QT_QPA_PLATFORM', None)
os.environ['BLASTLAB_SETTINGS'] = os.path.join(SCR, 'settings.json')

from blastlab.ui.testing import disable_cleanup, pump        # noqa: E402
disable_cleanup(os.environ['BLASTLAB_SETTINGS'])
from blastlab.core import settings as _s                      # noqa: E402
assert _s.load()['auto_cleanup'] is False
print('settings', _s.config_path(), 'auto_cleanup', _s.load()['auto_cleanup'])

from PIL import Image, ImageGrab                              # noqa: E402
from PySide6.QtCore import QPoint, Qt                         # noqa: E402
from PySide6.QtGui import QColor                              # noqa: E402
from PySide6.QtTest import QTest                              # noqa: E402
from PySide6.QtWidgets import QApplication, QToolTip          # noqa: E402

user32 = ctypes.windll.user32
_wd = threading.Timer(900, lambda: os._exit(3))
_wd.daemon = True
_wd.start()
RESULTS = []
INFO = {}


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


def screen(name, h, settle=250):
    pump(settle)
    l, t, r, b = rect(h)
    try:
        img = ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)
        how = 'ImageGrab'
    except OSError:
        img, ok = printwindow(h)
        how = f'PrintWindow(ok={ok})'
    img.save(os.path.join(OUT, name))
    print('  screenshot', name, (l, t, r - l, b - t), how, flush=True)
    return img, (l, t)


def front(win):
    h = hwnd(win)
    user32.SetWindowPos(h, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
    user32.SetForegroundWindow(h)
    win.raise_()
    win.activateWindow()
    pump(200)


def measure_status(win, tag, img, origin):
    """Qt font metrics vs the label's Qt contents rect and Win32 rect; and
    the warn colour present in the label's pixels in the screenshot."""
    st = win._status
    text = st.text()
    fm = st.fontMetrics()
    tw = fm.horizontalAdvance(text)
    cw = st.contentsRect().width()
    dpr = st.devicePixelRatioF()
    r = rect(hwnd(st))
    rw = r[2] - r[0]
    wr = rect(hwnd(win))
    INFO[tag] = dict(text=text, text_px=tw, contents_px=cw, dpr=dpr, label_w32=r,
                     label_w32_w=rw, window_w32=wr, wordwrap=st.wordWrap(),
                     style=st.styleSheet())
    print('  ', tag, INFO[tag], flush=True)
    check(f'1 [{tag}] Qt: summary fits the label contents rect',
          tw <= cw, f'text {tw} px vs contents {cw} px')
    check(f'1 [{tag}] Win32: summary (device px) fits GetWindowRect of the label',
          tw * dpr <= rw and w32_visible(st),
          f'text {tw * dpr:.0f} dev px vs label rect {rw} dev px {r}, visible={w32_visible(st)}')
    check(f'1 [{tag}] Win32: label lies inside the main window horizontally',
          r[0] >= wr[0] and r[2] <= wr[2], f'label {r} window {wr}')
    # pixels: crop the label from the screenshot, count warn-coloured px
    warn = QColor(theme.cur('warn'))
    wrgb = (warn.red(), warn.green(), warn.blue())
    crop = img.crop((r[0] - origin[0], r[1] - origin[1], r[2] - origin[0], r[3] - origin[1]))
    crop.save(os.path.join(OUT, f'R_{tag}_status_crop.png'))
    px = list(crop.getdata())
    near = [i for i, p in enumerate(px)
            if sum(abs(a - b) for a, b in zip(p, wrgb)) <= 40]
    cols = sorted({i % crop.width for i in near})
    INFO[tag]['warn_px'] = len(near)
    INFO[tag]['warn_x_extent'] = (cols[0], cols[-1]) if cols else None
    check(f'1 [{tag}] warning colour: stylesheet is theme warn and warn pixels are drawn',
          st.styleSheet() == f'color: {theme.cur("warn")};' and len(near) > 50,
          f'style {st.styleSheet()!r}, warn {wrgb}, {len(near)} px, x extent '
          f'{INFO[tag]["warn_x_extent"]} of {crop.width}')
    # the last drawn glyph column must sit clear of the label's right edge
    check(f'1 [{tag}] pixels: the text ink ends before the label edge (not cut)',
          bool(cols) and cols[-1] < crop.width - 4,
          f'last ink col {cols[-1] if cols else None} / width {crop.width}')


# ── the app, built as ui/app.main builds it ─────────────────────────────
from blastlab.ui import crashlog, theme                       # noqa: E402
crashlog.install()
_prev = sys.excepthook
CRASHES = []
sys.excepthook = lambda *a: (CRASHES.append(a), _prev(*a))
app = QApplication.instance() or QApplication(['blastlab'])
app.setApplicationName('blastlab')
theme.apply(app, _s.load().get('appearance', 'dark'))
from blastlab.ui.app import MainWindow                        # noqa: E402
from blastlab.core import assessment                          # noqa: E402

T = os.path.join(SCR, 't.json')
win = MainWindow()
win.show()
pump(800)
front(win)
INFO['default_window_w32'] = rect(hwnd(win))
INFO['default_window_qt'] = (win.width(), win.height())
print('  default size (Qt client)', win.width(), win.height(), 'w32', rect(hwnd(win)))

# ── 0-D form with the starter case (Open case is F1: form-level load) ──
win._show('setup')
pump(200)
QTest.mouseClick(win.setup.dim_seg._btns['0D'], Qt.LeftButton)
pump(500)
win.setup.set_case(assessment.load_case(T))
win._schedule_validate()
pump(1200)
form = win.setup.form

# ── 5. regression spot-check ────────────────────────────────────────────
print('\n5. regression')
wall_card, struct_card, heat_card = (form.cards[k] for k in
                                     ('Loaded wall', 'Structure', 'Heat'))
Hw, Ww, cb = form.widgets['wall_H_m'], form.widgets['wall_W_m'], form.widgets['clearing']
for w in (struct_card, heat_card, wall_card):
    w.setAttribute(Qt.WA_NativeWindow, True)
win.setup._scroll.ensureWidgetVisible(wall_card, 50, 50)
pump(300)
check('5 Structure card hidden (Win32 IsWindowVisible False, Qt isHidden)',
      not w32_visible(struct_card) and struct_card.isHidden(),
      f'w32={w32_visible(struct_card)}')
check('5 probe sanity: Heat and Loaded wall cards visible (Win32)',
      w32_visible(heat_card) and w32_visible(wall_card))
check('5 clearing off: H/W disabled', not cb.isChecked() and not Hw.isEnabled()
      and not Ww.isEnabled())
front(win)
screen('R_5a_wall_clearing_off.png', hwnd(win))
QTest.mouseClick(cb, Qt.LeftButton, Qt.NoModifier, QPoint(8, cb.height() // 2))
pump(500)
check('5 click ticks clearing: H/W enabled', cb.isChecked() and Hw.isEnabled()
      and Ww.isEnabled())
front(win)
screen('R_5b_wall_clearing_on.png', hwnd(win))
QTest.mouseClick(cb, Qt.LeftButton, Qt.NoModifier, QPoint(8, cb.height() // 2))
pump(500)
check('5 click unticks clearing: H/W disabled again', not cb.isChecked()
      and not Hw.isEnabled() and not Ww.isEnabled())
check('5 Structure still hidden after the toggles (Win32)', not w32_visible(struct_card))
# restore the starter case exactly (clearing off, H/W blank)
win.setup.set_case(assessment.load_case(T))
win._schedule_validate()
pump(1200)
form = win.setup.form

# ── run ─────────────────────────────────────────────────────────────────
print('\nrun')
run_dir = os.path.join(SCR, 'run')
os.makedirs(run_dir, exist_ok=True)
report = os.path.join(run_dir, 't_hd13.html')
form.v['report_file'].set(report)
pump(1500)
win._status.setAttribute(Qt.WA_NativeWindow, True)   # its own HWND for Win32
pump(200)
win._show('run')
pump(400)
rb = win.run_panel.run_btn
check('run: Run button enabled', rb.isEnabled())
log_before = win.run_panel.log_text()
front(win)
t0 = time.monotonic()
QTest.mouseClick(rb, Qt.LeftButton)
pump(500)
while getattr(win, '_hd13_busy', False) and time.monotonic() - t0 < 600:
    pump(50)
t_done = time.monotonic()
INFO['run_seconds'] = round(t_done - t0, 1)
print('  run took', INFO['run_seconds'], 's')
check('run finished with no dialog', QApplication.activeModalWidget() is None)

# ── 1. default size ─────────────────────────────────────────────────────
print('\n1. status at default size', win.width(), win.height())
st = win._status
check('1 status is the short summary',
      st.text().startswith('HD 1.3 done') and 'still active' in st.text()
      and '(see Log)' in st.text(), st.text())
front(win)
img, org = screen('R_1a_status_default_1280.png', hwnd(win), settle=100)
measure_status(win, 'default', img, org)

# ── 2. tooltip ──────────────────────────────────────────────────────────
tip = st.toolTip()
INFO['tooltip'] = tip
log_new = win.run_panel.log_text()[len(log_before):].lstrip('\n').splitlines()
INFO['log_added'] = log_new
print('  TOOLTIP:\n' + tip)
loads = os.path.join(run_dir, 't_hd13_loads')
csv = os.path.join(loads, 'nominal.csv')
tl = tip.splitlines()
active = [ln for ln in tl if 'record ends while the load is still active: p = ' in ln]
check('2 tooltip: report path (absolute)',
      f'HD 1.3 report written: {os.path.abspath(report)}' in tl, tl[:1])
check('2 tooltip: load folder (absolute)',
      any(os.path.abspath(loads) in ln and 'SBEDS loads' in ln for ln in tl))
check('2 tooltip: nominal.csv (absolute)', f'  {os.path.abspath(csv)}' in tl)
check('2 tooltip: "still active: p = ... kPa at t = ... ms" line',
      bool(active) and ' kPa at t = ' in active[0] and active[0].rstrip().endswith('ms'),
      active[0] if active else 'missing')
# show the tooltip for real and capture its window
gp = st.mapToGlobal(QPoint(20, st.height() // 2))
QToolTip.showText(gp, tip, st)
pump(600)
tw_ = [w for w in QApplication.topLevelWidgets()
       if w.isVisible() and w.metaObject().className() == 'QTipLabel']
if tw_:
    screen('R_2_status_tooltip.png', hwnd(tw_[0]), settle=150)
    INFO['tooltip_window_w32'] = rect(hwnd(tw_[0]))
    check('2 tooltip window on screen (Win32 visible)', w32_visible(tw_[0]),
          str(rect(hwnd(tw_[0]))))
else:
    check('2 tooltip window captured', False, 'no QTipLabel visible')
QToolTip.hideText()
pump(100)

# ── 1. minimum width ────────────────────────────────────────────────────
win.resize(1100, win.height())
pump(400)
INFO['min_window_qt'] = (win.width(), win.height())
print('\n1. status at min width', win.width(), win.height())
check('1 window at its minimum width', win.width() == win.minimumWidth(),
      f'{win.width()} (min {win.minimumWidth()})')
front(win)
img, org = screen('R_1b_status_min_1100.png', hwnd(win), settle=100)
measure_status(win, 'min1100', img, org)
check('1 still inside the 12 s window when measured', time.monotonic() - t_done < 11.5,
      f'{time.monotonic() - t_done:.1f} s after the run')
win.resize(1280, 840)
pump(300)

# ── 3. Run log ──────────────────────────────────────────────────────────
print('\n3. Run log')
for ln in log_new:
    print('   LOG|' + ln)
check('3 log: absolute report path',
      f'HD 1.3 report written: {os.path.abspath(report)}' in log_new)
check('3 log: load folder', any(os.path.abspath(loads) in ln and 'SBEDS loads' in ln
                                for ln in log_new))
check('3 log: nominal.csv', f'  {os.path.abspath(csv)}' in log_new)
check('3 log: the still-active line verbatim (same as the tooltip)',
      bool(active) and active[0] in log_new, active[0] if active else '')
sidecar = open(os.path.join(loads, 'nominal.txt'), encoding='utf-8').read()
msg = active[0].split(': ', 1)[1] if active else '???'
check('3 the still-active text matches the nominal.txt sidecar', msg in sidecar,
      msg)
front(win)
screen('R_3_run_log.png', hwnd(win))

# ── 4. after 12 s ───────────────────────────────────────────────────────
print('\n4. waiting for the 12 s timer')
while time.monotonic() - t_done < 13.5:
    pump(100)
check('4 status text cleared', st.text() == '', repr(st.text()))
check('4 tooltip cleared', st.toolTip() == '', repr(st.toolTip()[:60]))
log_after = win.run_panel.log_text()[len(log_before):].lstrip('\n').splitlines()
check('4 log still holds the lines', log_after[:len(log_new)] == log_new,
      f'{len(log_after)} lines')
front(win)
screen('R_4_after_12s.png', hwnd(win))

print('\nclose')
check('no unhandled exceptions', not CRASHES, str(CRASHES[:1]))
user32.SetWindowPos(hwnd(win), -2, 0, 0, 0, 0, 0x0001 | 0x0002)
win.close()
pump(400)
app.quit()
json.dump({'results': RESULTS, 'info': INFO},
          open(os.path.join(SCR, 'rerun_results.json'), 'w'), indent=1, default=str)
n_fail = sum(1 for r in RESULTS if not r[1])
print(f'\nRE-RUN: {len(RESULTS) - n_fail} pass, {n_fail} fail', flush=True)
os._exit(1 if n_fail else 0)
