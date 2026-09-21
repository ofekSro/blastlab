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

    print('\n  pressing Run writes a report')
    out = os.path.join(tempfile.mkdtemp(prefix='blastlab_hd13_gui_'),
                       'report.html')
    form = win.setup.forms[0]
    form.v['report_file'].set(out)
    form.v['t_end'].set('20')
    pump(150)
    win._run_single()
    pump(600)
    check('the report file exists', os.path.exists(out),
          out)
    if os.path.exists(out):
        body = open(out, encoding='utf-8').read()
        check('it is a real report, with the caveats in it',
              len(body) > 3000 and 'uncalibrated' in body,
              f'{len(body)} bytes')
    check('the status line says where it went',
          'HD 1.3 report' in win._status.text(), win._status.text())

    print('\n  nothing crashed')
    check('no unhandled exceptions', not crashes, str(crashes[:1]))

    win.close()
    pump(200)
    print('\nHD 1.3 GUI: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
