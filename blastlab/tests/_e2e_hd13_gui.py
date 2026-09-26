"""HD1-11c: the HD 1.3 tab in a REAL window, measured with Win32.

CLAUDE.md Sec. 8.7 exists because of this exact situation. Offscreen Qt
tests and reasoning from the API have been wrong every single time a GUI
bug was investigated here; the rule is to measure the real component on
the real platform, and Win32 through ctypes is the ground truth rather
than Qt's own geometry().

So this file opens an actual window - `QT_QPA_PLATFORM` is explicitly
REMOVED, not set to offscreen - switches to the 0-D dimension and asks
Windows, not Qt, what is on screen:

  * the window is really visible and really has the size it claims;
  * the solver segment is really hidden at 0-D and really back at 2-D,
    checked through IsWindowVisible on its own HWND rather than through
    isVisible();
  * the validation card really fills with the HD 1.3 warnings;
  * pressing Run really writes a report file.

This is an `_e2e_` file by the repo's naming convention: it opens a real
window, so it is not part of the fast suite and is run deliberately.

Run:  cd blastlab/tests && python _e2e_hd13_gui.py
"""

import ctypes
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

# Sec. 8.7: a real platform, not offscreen. Removed rather than left
# alone, because a parent process may have exported it.
os.environ.pop('QT_QPA_PLATFORM', None)
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_e2e_'),
                                   'settings.json'))

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def hwnd_of(widget):
    wid = int(widget.winId())
    return wid or 0


def win32_visible(widget):
    """IsWindowVisible on the widget's own HWND. Only a top level or a
    widget forced to be native has one, so the caller makes it native
    first; for a child without one this falls back to walking up to the
    nearest native ancestor, which is what Qt actually paints into."""
    if not sys.platform.startswith('win'):
        return None
    h = hwnd_of(widget)
    if not h:
        return None
    return bool(ctypes.windll.user32.IsWindowVisible(h))


def win32_rect(widget):
    if not sys.platform.startswith('win'):
        return None
    rect = ctypes.wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd_of(widget),
                                              ctypes.byref(rect)):
        return None
    return (rect.left, rect.top, rect.right - rect.left,
            rect.bottom - rect.top)


def main():
    print('HD 1.3 GUI, REAL WINDOW (HD1-11c)')
    import ctypes.wintypes                                     # noqa: F401
    from blastlab.ui.testing import ensure_qapp, pump
    ensure_qapp(offscreen=False)
    from blastlab.ui.app import MainWindow
    from blastlab.ui import theme

    crashes = []
    sys.excepthook = lambda *a: crashes.append(a)

    win = MainWindow()
    win.resize(1280, 840)
    win.show()
    pump(400)

    print('\n  the window is really on screen')
    check('Qt says it is visible', win.isVisible())
    if sys.platform.startswith('win'):
        check('and so does Win32', win32_visible(win) is True)
        r = win32_rect(win)
        check('Win32 reports a real rectangle', r and r[2] > 400 and r[3] > 300,
              str(r))

    print('\n  switching to 0D')
    win._show('setup')
    pump(200)
    win.setup.set_dim(0)
    pump(400)
    check('the panel reports dim 0', win.setup.dim == 0)
    check('the segment shows 0D', win.setup.dim_seg.get() == '0D',
          str(win.setup.dim_seg.get()))
    check('the 0-D form is the visible one',
          win.setup.form is win.setup.forms[0]
          and win.setup.forms[0].isVisible())

    print('\n  the solver switch is gone, per Win32')
    seg = win._solver_seg
    seg.setAttribute(__import__('PySide6.QtCore', fromlist=['Qt']).Qt
                     .WA_NativeWindow, True)
    pump(200)
    check('Qt hides the solver segment at 0D', not seg.isVisible())
    if sys.platform.startswith('win'):
        vis = win32_visible(seg)
        check('and Win32 agrees it is not on screen', vis in (False, None),
              str(vis))
    win.setup.set_dim(2)
    pump(400)
    check('and it comes back at 2D', seg.isVisible())
    win.setup.set_dim(0)
    pump(400)

    print('\n  validation fills the card with the HD 1.3 warnings')
    win._validate()
    pump(200)
    rows = win.setup.report_rows()
    text = ' '.join(m for _sev, m in rows)
    check('the card is not empty', bool(rows), f'{len(rows)} rows')
    check('it warns about the extrapolation', 'extrapolation' in text.lower())
    check('it names the uncalibrated fields',
          'not calibrated' in text.lower())
    check('it reports the closed-vessel limit',
          'closed-vessel limit' in text.lower())

    # HD1-16: the Structure card is built (its values pass through) but
    # must not be on screen - asked of Win32, not of isVisible()
    print('\n  the Structure card is not on screen (HD1-16), per Win32')
    form = win.setup.forms[0]
    QtNS = __import__('PySide6.QtCore', fromlist=['Qt']).Qt
    struct_card = form.cards['Structure']
    heat_card = form.cards['Heat']
    for c in (struct_card, heat_card):
        c.setAttribute(QtNS.WA_NativeWindow, True)
    pump(200)
    if sys.platform.startswith('win'):
        vis = win32_visible(struct_card)
        check('Win32: the Structure card is not visible', vis in (False, None)
              and not struct_card.isVisible(), str(vis))
        check('while a neighbouring card (Heat) is, so the probe works',
              win32_visible(heat_card) is True)

    print('\n  pressing Run writes a report and the SBEDS load CSVs')
    out = os.path.join(tempfile.mkdtemp(prefix='blastlab_hd13_gui_'),
                       'report.html')
    form.v['report_file'].set(out)
    # the form's own end time, not a shortened one: the record has to end
    # while the load is still active, so the "still active" path is shown
    # (QA 2026-09-26-hd1-16 F2); an end time of 20 never fires that rule
    pump(150)
    win._run_single()
    # the assessment runs on a worker thread (UX 1): wait it out with the
    # event loop running
    import time
    end = time.monotonic() + 900
    while getattr(win, '_hd13_busy', False) and time.monotonic() < end:
        pump(50)
    pump(300)
    check('the report file exists', os.path.exists(out),
          out)
    if os.path.exists(out):
        body = open(out, encoding='utf-8').read()
        check('it is a real report, with the caveats in it',
              len(body) > 3000 and 'uncalibrated' in body,
              f'{len(body)} bytes')
        check('and no Structural response section (HD1-16)',
              'Structural response' not in body)
    loads = os.path.splitext(out)[0] + '_loads'
    check('the _loads/ directory is written, with nominal.csv and its '
          'sidecar', os.path.isfile(os.path.join(loads, 'nominal.csv'))
          and os.path.isfile(os.path.join(loads, 'nominal.txt')),
          str(os.listdir(loads)) if os.path.isdir(loads) else 'missing')
    # QA 2026-09-26-hd1-16 F2: the status line used to hold the whole
    # ~3300 px text in a ~1170 px label, clipped and gone after 12 s. Now
    # it is a short summary that must FIT (measured against the label's
    # real width, per Win32), and the full text is in the tooltip and in
    # the Run log.
    status = win._status
    s_text = status.text()
    check('the status line is the short summary',
          s_text.startswith('HD 1.3 done') and 'SBEDS load CSV' in s_text
          and '(see Log)' in s_text, s_text)
    text_w = status.fontMetrics().horizontalAdvance(s_text)
    check('Qt: the summary fits inside the label',
          text_w <= status.contentsRect().width(),
          f'text {text_w} px, label {status.contentsRect().width()} px')
    if sys.platform.startswith('win'):
        status.setAttribute(QtNS.WA_NativeWindow, True)
        pump(200)
        r = win32_rect(status)
        dpr = status.devicePixelRatioF()
        check('Win32: the label is on screen', win32_visible(status) is True)
        check('Win32: the summary fits inside the label',
              r is not None and text_w * dpr <= r[2],
              f'text {text_w * dpr:.0f} px (device), label rect {r}')
    lines = win.run_panel.log_text().splitlines()
    loads_abs = os.path.abspath(loads)
    check('the Run log names the report',
          f'HD 1.3 report written: {os.path.abspath(out)}' in lines)
    check('the Run log names the load folder, absolute',
          any(loads_abs in ln and 'SBEDS loads' in ln for ln in lines))
    check('the Run log lists nominal.csv, absolute',
          f'  {os.path.join(loads_abs, "nominal.csv")}' in lines)
    active = [ln for ln in lines
              if 'record ends while the load is still active' in ln]
    check('the Run log carries the "still active" line', bool(active),
          active[0] if active else 'missing')
    check('so the status line is a warning',
          status.styleSheet() == f'color: {theme.cur("warn")};'
          and 'still active' in s_text, status.styleSheet())
    check('the tooltip holds the full text',
          all(ln in status.toolTip().splitlines() for ln in active)
          and loads_abs in status.toolTip(), status.toolTip()[:120])

    print('\n  nothing crashed')
    check('no unhandled exceptions', not crashes, str(crashes[:1]))

    win.close()
    pump(200)
    print('\nHD 1.3 GUI: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
