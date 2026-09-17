"""The embedded render window must stay over its card.

The owner reported this three times, and my first two explanations were
both wrong, so this suite is written around a measurement rather than a
theory: it reads the render window's real position with Win32 and
compares it with the card it is supposed to fill.

What is actually happening. `createWindowContainer` does NOT make the
foreign window a child of the container - measured with GetParent, it
re-parents it to the TOP-LEVEL window, and Qt then keeps its geometry in
step BY HAND. That bookkeeping breaks, and stays broken, under several
unrelated operations. Measured inside the real SetupPanel:

    hiding and showing the tab        258 px left,  48 px up
    resizing the window              258 px left,  48 px up
    switching the dimension away      878 px left, 121 px up
    switching to light mode           751 px left, 121 px up

Each one leaves the render window in the corner of the client area, over
the sidebar and the form.

**Correcting that is not enough, and this is the lesson of the whole
episode.** Once the position was re-asserted from state rather than from
events, the window always ended up over its card - and the owner still
watched it flick out and back, because a correction can only ever run
after the wrong frame. Measured on the Qt path: 18 ms on a tab switch,
68 ms on a theme change.

So the render window is now a real Windows CHILD of its card
(`View3DHost._embed_native`), which removes the failure instead of
repairing it: Windows clips it to the card, carries it when the card
moves, and makes its coordinates relative to the card - so the (0, 0)
that both processes fall back to is exactly right. Measured across
eleven actions with the real viewer child: never drawn out of place.

Hence three questions here, not one: the window ends up over its card
(E2), it is never DRAWN anywhere else (E3), and the backstop that
catches whatever is left stays cheap (E4).

  --qt-container   force Qt's window container: E2 passes, E3 fails,
                   which is the state the owner reported
  --break          also disable the geometry sync: E2 fails too

Two things this suite needs, and both are deliberate:

- A REAL platform. `QWindow.fromWinId` returns None offscreen, so there
  is nothing to embed and the suite skips.
- The real `SetupPanel`, not a flat stack. The first version of this
  test used one page holding the host directly and passed while the
  application was still broken: the hierarchy that matters is
  stack -> SetupPanel -> _prev_stack -> View3DHost -> container.

`_qa_foreign_window.py` stands in for the viewer child, because the bug
is about window parenting and not about rendering, and a pyvista scene
needs an OpenGL context.

Run:  cd blastlab/tests && python _e2e_ui_embed.py
      python _e2e_ui_embed.py --break     (without the fix: it fails)
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
_dir = tempfile.mkdtemp(prefix='blastlab_embed_')
_settings = os.path.join(_dir, 'settings.json')
with open(_settings, 'w', encoding='utf-8') as _f:
    _f.write('{"auto_cleanup": false}')
os.environ['BLASTLAB_SETTINGS'] = _settings

#: how far out of place counts as broken
TOL = 2
#: one frame at 60 Hz. A real child window measures 0.0 ms here; Qt's
#: window container measured 18 ms on a tab switch and 68 ms on a theme
#: change, and the owner saw both
VISIBLE_MS = 17

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
    return bool(ctypes.windll.user32.IsWindowVisible(ctypes.c_void_p(hwnd)))


class FakeLink:
    """Somewhere for the host to post its control messages."""

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
    qt_container = broken or '--qt-container' in sys.argv
    if qt_container:
        View3DHost._embed_native = lambda self: False
        print('*** the native child path is disabled: Qt window '
              'container only ***')
    if broken:
        View3DHost.sync_foreign_geometry = lambda self: None
        print('*** sync_foreign_geometry disabled ***')
    from blastlab.core.mode import SolverMode
    from blastlab.ui.setup_panel import SetupPanel

    # The REAL viewer child by preference. The stand-in cannot reproduce
    # the flash at all - it never repositions itself, while the child's
    # own Qt believes its render widget is a top-level window and
    # re-applies a stale position on every show() - so a suite built on
    # the stand-in reports a clean bill of health for a design the owner
    # can see failing. That is how the previous version of this file
    # stayed green through three bug reports.
    child = None
    link = None
    stand_in = '--stand-in' in sys.argv
    if not stand_in:
        from blastlab.ui.viewer_link import ViewerLink
        lines = []
        link = ViewerLink(log_fn=lines.append)

    win = QWidget()
    win.setWindowTitle('blastlab embed test')
    win.resize(1280, 840)
    root = QVBoxLayout(win)
    root.setContentsMargins(0, 0, 0, 0)
    stack = QStackedWidget()
    root.addWidget(stack)
    setup = SetupPanel(on_change=lambda: None,
                       mode=SolverMode('blastfoam'),
                       viewer_link=link or FakeLink(),
                       log_fn=lambda _s: None)
    stack.addWidget(setup)
    run_page = QWidget()
    QVBoxLayout(run_page).addWidget(QLabel('Run tab'))
    stack.addWidget(run_page)
    win.show()

    def settle(n=60):
        """Long enough for the 250 ms watchdog to get a tick in."""
        for _ in range(n):
            app.processEvents()
            time.sleep(0.01)

    settle()
    setup.set_dim(3)
    # set_dim alone leaves _prev_stack on its message page, so the host
    # would stay hidden and nothing would be embedded at all
    setup.update_preview(setup.get_case())
    settle()
    host = setup.view3d
    if host is None:
        print('SKIP: no 3D host (pyvista missing)')
        return 0
    check('the host is the current preview page',
          setup._prev_stack.currentWidget() is host and host.isVisible())

    if link is not None:
        for _ in range(2500):               # pyvista + VTK + a GL context
            app.processEvents()
            time.sleep(0.01)
            if host._hwnd and host._container is not None:
                break
        if not host._hwnd:
            print('  the real viewer child never reported a window '
                  f'({lines[-1].strip() if lines else "no reason given"});'
                  '\n  falling back to the stand-in, which CANNOT '
                  'reproduce the flash')
            link.close()
            link = None
        else:
            print(f'real viewer child, render window {host._hwnd}')
    if link is None:
        child = subprocess.Popen(
            [sys.executable, '-u',
             os.path.join(HERE, '_qa_foreign_window.py')],
            stdout=subprocess.PIPE, text=True)
        stand_hwnd = None
        for _ in range(300):
            line = child.stdout.readline()
            if not line:
                break
            if line.startswith('HWND'):
                stand_hwnd = int(line.split()[1])
                break
        if stand_hwnd is None:
            print('FAILED: the stand-in surface never reported a window')
            child.kill()
            return 1
        print(f'stand-in surface HWND: {stand_hwnd}')
        setup.view3d._has_scene = True
        host.on_window(stand_hwnd)
    settle()
    hwnd = host._hwnd

    def stop_surface():
        if child is not None:
            child.kill()
        if link is not None:
            link.close()

    print('\nE1: the embed itself')
    check('a card was built to hold it', host._container is not None)
    if host._container is None:
        stop_surface()
        return 1
    check(f'the expected path was taken (native={not qt_container})',
          host._native is not qt_container,
          f'native={host._native}')
    if host._native:
        check('the window is a child of the CARD, so Windows clips and '
              'carries it and its coordinates are relative to it',
              win32_parent(hwnd) == int(host._container.winId()),
              f'parent={win32_parent(hwnd)} '
              f'card={int(host._container.winId())} '
              f'toplevel={int(win.winId())}')
    else:
        check('Qt re-parented it to the TOP-LEVEL, not to the container '
              '- this is what makes that path fragile',
              win32_parent(hwnd) == int(win.winId()),
              f'parent={win32_parent(hwnd)} toplevel={int(win.winId())} '
              f'container={int(host._container.winId())}')
        check('and there is a foreign window wrapper',
              host._foreign is not None)

    def offset():
        c = host._container
        g = c.mapToGlobal(c.rect().topLeft())
        r = win32_rect(hwnd)
        return (r[0] - g.x(), r[1] - g.y())

    def ok_now(tag):
        d = offset()
        check(f'{tag}, offset {d}',
              abs(d[0]) <= TOL and abs(d[1]) <= TOL, str(d))
        return d

    ok_now('it starts over its card')

    print('\nE2: every operation that used to move it')
    stack.setCurrentIndex(1)
    settle()
    stack.setCurrentIndex(0)
    settle()
    ok_now('after Setup -> Run -> Setup')
    for _ in range(2):
        stack.setCurrentIndex(1)
        settle(30)
        stack.setCurrentIndex(0)
        settle(30)
    ok_now('after two more round trips')

    setup.set_dim(2)
    setup.update_preview(setup.get_case())
    settle()
    setup.set_dim(3)
    setup.update_preview(setup.get_case())
    settle()
    ok_now('after 3D -> 2D -> 3D')

    setup.show_mesh.setChecked(True)
    setup.update_preview(setup.get_case())
    settle()
    ok_now('after Show mesh')

    for _ in range(4):
        setup.update_preview(setup.get_case())
        settle(20)
    ok_now('after four edited cases')

    win.resize(1100, 720)
    settle()
    ok_now('after shrinking the window')
    win.resize(1440, 900)
    settle()
    ok_now('after growing it')

    theme.apply(app, 'light')
    settle()
    ok_now('after switching to light mode')
    theme.apply(app, 'dark')
    settle()
    ok_now('and back to dark')

    print('\nE3: and it is not merely corrected, it is never drawn wrong')
    # Ending up over the card is not the bar. A correction can only run
    # after the wrong frame, and the owner watched exactly that: the
    # window flicking right to left and back, "just for a moment".
    # What the eye sees is the longest UNBROKEN stretch during which a
    # VISIBLE window is not over its card, so that is what is measured.
    def longest_off(action, watch_ms=700):
        action()
        app.processEvents()
        t0 = time.perf_counter()
        run = best = 0.0
        prev = None
        while (time.perf_counter() - t0) * 1000 < watch_ms:
            app.processEvents()
            now = (time.perf_counter() - t0) * 1000
            d = offset()
            if (win32_visible(hwnd)
                    and max(abs(d[0]), abs(d[1])) > TOL):
                run += 0.0 if prev is None else now - prev
                best = max(best, run)
            else:
                run = 0.0
            prev = now
            time.sleep(0.002)
        return best

    def tab_trip():
        stack.setCurrentIndex(1)
        settle(25)
        stack.setCurrentIndex(0)

    def dim_trip():
        setup.set_dim(2)
        setup.update_preview(setup.get_case())
        settle(25)
        setup.set_dim(3)
        setup.update_preview(setup.get_case())

    def minimize_trip():
        win.showMinimized()
        settle(40)
        win.showNormal()

    for tag, action in (
            ('a tab round trip', tab_trip),
            ('a dimension round trip', dim_trip),
            ('a resize', lambda: win.resize(1180, 780)),
            ('minimizing and restoring', minimize_trip),
            ('switching to light mode',
             lambda: theme.apply(app, 'light')),
            ('and back to dark', lambda: theme.apply(app, 'dark'))):
        ms = longest_off(action)
        check(f'{tag} never draws it out of place for more than '
              f'{VISIBLE_MS} ms', ms <= VISIBLE_MS, f'{ms:.1f} ms')
        settle(20)

    print('\nE4: the watchdog is cheap when nothing is happening')
    check('it was running while embedded',
          host._sync_timer is not None and host._sync_timer.isActive())
    settle(int(View3DHost.SYNC_BURST_MS / 10) + 40)
    check('and drops back to its idle interval once things are quiet',
          host._sync_timer.interval() == View3DHost.SYNC_IDLE_MS,
          f'{host._sync_timer.interval()} ms')
    host.shutdown()
    settle(20)
    check('and stops with the host',
          host._sync_timer is None or not host._sync_timer.isActive())
    check('and the card handed the render window back, so the viewer '
          'keeps it when the card is destroyed',
          not host._native and host._container is None)
    win.close()
    settle(20)
    stop_surface()

    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'E2E UI EMBED: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
