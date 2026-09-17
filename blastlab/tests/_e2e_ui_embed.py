"""The embedded render window must stay over its card.

The owner reported this twice: set Setup to 3D, go to Run, come back,
and the 3D preview is at the top-left of the application, over the
sidebar and the form. My first explanation - that the release/claim
messages were handing the window back to the child - was wrong, and the
fix built on it did nothing. So this suite measures the actual position
through Win32, which is the only account that cannot be argued with.

What is really happening: `createWindowContainer` does NOT make the
foreign window a child of the container. Measured with GetParent, it
re-parents it to the TOP-LEVEL window, and Qt then keeps its geometry in
step by hand. Hide the container and show it again - which is what a tab
switch does - and Qt stops. Measured without the fix: the window sits at
(8, 31) while its container is at (266, 79), i.e. 258 px left and 48 px
up, in the corner of the client area. It takes TWO cycles to appear,
which is why it looked intermittent.

Of the obvious remedies only one works, also measured: a resize nudge,
`updateGeometry()` and hiding/showing the container all leave it
misaligned. Setting the QWindow's geometry explicitly is what puts it
back, and that is `View3DHost.sync_foreign_geometry`.

Needs a REAL platform: `QWindow.fromWinId` returns None offscreen, so
there is nothing to embed. Uses `_qa_foreign_window.py` as the child
instead of the viewer, because the bug is about window parenting and not
about rendering.

Run:  cd blastlab/tests && python _e2e_ui_embed.py
      python _e2e_ui_embed.py --break     (watch it fail without the fix)
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.pop('QT_QPA_PLATFORM', None)     # a real platform, on purpose
os.environ.setdefault('MPLBACKEND', 'Agg')
_settings = os.path.join(tempfile.mkdtemp(prefix='blastlab_embed_'),
                         'settings.json')
with open(_settings, 'w', encoding='utf-8') as _f:
    _f.write('{"auto_cleanup": false}')
os.environ['BLASTLAB_SETTINGS'] = _settings

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


class _RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


def win32_rect(hwnd):
    r = _RECT()
    ctypes.windll.user32.GetWindowRect(ctypes.c_void_p(hwnd),
                                       ctypes.byref(r))
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def win32_parent(hwnd):
    return ctypes.windll.user32.GetParent(ctypes.c_void_p(hwnd))


def win32_visible(hwnd):
    return bool(ctypes.windll.user32.IsWindowVisible(
        ctypes.c_void_p(hwnd)))


class FakeLink:
    """The host only needs somewhere to post its control messages."""

    def __init__(self):
        self.sent = []

    def register(self, surface, host):
        pass

    def ensure_started(self):
        return True

    @property
    def alive(self):
        return True

    def send(self, msg):
        self.sent.append(msg)
        return True


def main():
    broken = '--break' in sys.argv
    from PySide6.QtWidgets import (QApplication, QLabel, QStackedWidget,
                                   QVBoxLayout, QWidget)
    app = QApplication(['blastlab-embed'])
    if app.platformName() == 'offscreen':
        print('SKIP: the offscreen platform cannot wrap a foreign '
              'window (fromWinId returns None)')
        return 0
    from blastlab.ui import theme
    theme.apply(app, 'dark')
    from blastlab.ui.view3d_host import View3DHost
    if broken:
        View3DHost.sync_foreign_geometry = lambda self: None
        print('*** sync_foreign_geometry disabled ***')

    child = subprocess.Popen(
        [sys.executable, '-u',
         os.path.join(HERE, '_qa_foreign_window.py')],
        stdout=subprocess.PIPE, text=True)
    hwnd = None
    for _ in range(300):
        line = child.stdout.readline()
        if not line:
            break
        if line.startswith('HWND'):
            hwnd = int(line.split()[1])
            break
    if hwnd is None:
        print('FAILED: the stand-in surface never reported a window')
        child.kill()
        return 1
    print(f'stand-in surface HWND: {hwnd}')

    # a tab stack, as the main window has: the host lives on one page
    win = QWidget()
    win.setWindowTitle('blastlab embed test')
    win.resize(1280, 840)
    root = QVBoxLayout(win)
    stack = QStackedWidget()
    root.addWidget(stack)
    page0 = QWidget()
    p0 = QVBoxLayout(page0)
    p0.addWidget(QLabel('Setup - the Model Preview card'))
    host = View3DHost(FakeLink(), 'setup', log_fn=lambda _s: None)
    host.set_controls_collapsed(True)
    p0.addWidget(host, 1)
    stack.addWidget(page0)
    page1 = QWidget()
    QVBoxLayout(page1).addWidget(QLabel('Run'))
    stack.addWidget(page1)
    win.show()

    def settle(n=40):
        for _ in range(n):
            app.processEvents()
            time.sleep(0.01)

    settle(60)
    # the production path: a scene attaches, then the child reports its
    # native handle and the host embeds it
    host._has_scene = True
    host.on_window(hwnd)
    settle(80)

    print('\nE1: the embed itself')
    check('a container was built', host._container is not None)
    check('and a foreign window wrapper with it',
          host._foreign is not None)
    if host._container is None:
        child.kill()
        return 1
    check('the window is a child of the TOP-LEVEL, not of the '
          'container - this is what makes it fragile',
          win32_parent(hwnd) == int(win.winId()),
          f'parent={win32_parent(hwnd)} toplevel={int(win.winId())} '
          f'container={int(host._container.winId())}')

    def offset():
        c = host._container
        g = c.mapToGlobal(c.rect().topLeft())
        r = win32_rect(hwnd)
        return (r[0] - g.x(), r[1] - g.y())

    check('it starts exactly over its container', offset() == (0, 0),
          str(offset()))

    print('\nE2: Setup -> Run -> Setup, three times')
    drift = []
    for i in range(3):
        stack.setCurrentIndex(1)
        settle()
        hidden = win32_visible(hwnd)
        stack.setCurrentIndex(0)
        settle()
        off = offset()
        drift.append(off)
        check(f'round {i + 1}: still over the card, offset {off}',
              abs(off[0]) <= 1 and abs(off[1]) <= 1, str(off))
        check(f'round {i + 1}: and it was hidden while away - a '
              f'container hides its contents', not hidden)
    check('no drift accumulated over three round trips',
          all(abs(x) <= 1 and abs(y) <= 1 for x, y in drift),
          str(drift))

    print('\nE3: and it follows a resize')
    win.resize(1100, 720)
    settle()
    check('after shrinking the window', abs(offset()[0]) <= 1
          and abs(offset()[1]) <= 1, str(offset()))
    win.resize(1440, 900)
    settle()
    check('and after growing it', abs(offset()[0]) <= 1
          and abs(offset()[1]) <= 1, str(offset()))

    host.shutdown()
    settle(20)
    win.close()
    settle(20)
    child.kill()

    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'E2E UI EMBED: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
