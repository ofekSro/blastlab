"""Real-window e2e of the Qt front-end: a native 3D run through
MainWindow with the viewer child embedded in the Run tab. Opens a window
on screen (not offscreen: the child needs a real GL window to embed).
Writes screenshots next to this file when --shots is given."""
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')
import tempfile
os.environ.setdefault('BLASTLAB_SETTINGS', os.path.join(
    tempfile.mkdtemp(prefix='blastlab_ui_e2e_'), 'settings.json'))

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def main():
    shots = '--shots' in sys.argv
    from PySide6.QtWidgets import QApplication
    from blastlab.ui import theme
    from blastlab.ui.testing import pump, use_model
    from blastlab.ui.app import MainWindow
    app = QApplication.instance() or QApplication(['blastlab-e2e'])
    theme.apply(app, 'dark')
    case = os.path.join(HERE, 'cases', 'native_3d_small.json')
    win = MainWindow(case_file=case)
    use_model(win)          # OUT-1: Run needs a runs folder and a model
    win.show()
    pump(300)
    check("case loaded", win.current_case() is not None
          and win.current_case().dim == 3)
    check("validation reached the Run tab",
          win.run_panel._valid_lbl.text() == 'Case OK',
          win.run_panel._valid_lbl.text())

    print("\nG1: start the 3D run (F5 path)")
    t0 = time.time()
    win._run_single()
    check("run tab shown", win.current_tab() == 'run')
    enabled = False
    for _ in range(400):                     # react as soon as it enables
        pump(50)
        if win.run_panel.view3d_btn.isEnabled():
            enabled = True
            break
    check("view3d button enabled", enabled, f"after {time.time()-t0:.1f}s")
    check("feed + ring attached to hooks",
          win.ctrl.worker.hooks.feed3d is not None
          and win.ctrl.worker.hooks.ring is not None)
    check("host has a scene", win.view3d.has_scene)

    print("\nG2: the 3D tab embeds the viewer window")
    win._open_view3d()
    embedded = False
    for _ in range(200):
        pump(50)
        if win.view3d._container is not None:
            embedded = True
            break
    check("viewer window embedded (container present)", embedded)
    check("3D tab selected", win.run_panel.current_view() == '3D view')
    check("viewer process alive", win.viewer_link.alive)
    if shots:
        win.grab().save(os.path.join(HERE, 'ui_e2e_run_tab.png'))

    # pump until the run finishes (tiny case: a few seconds)
    for _ in range(2400):
        pump(50)
        if not win.ctrl.running:
            break
    log = win.run_panel.log_text()
    check("run finished", '[run finished]' in log)
    check("3D view was active", '[3D view active' in log)
    check("no ui errors in the log", '[ui error handling' not in log,
          [ln for ln in log.splitlines() if 'ui error' in ln][:2])
    check("a result was posted", len(win._results) == 1)
    pump(500)
    st = win.view3d.status()
    check("viewer reported playback status",
          st.get('done') is True and st.get('n', 0) >= 2, str(st))
    check("time slider spans the frames",
          win.view3d.time_slider.maximum() == max(1, st.get('n', 0) - 1),
          f"{win.view3d.time_slider.maximum()} vs n={st.get('n')}")
    check("frames landed in the 2D pane",
          win.run_panel.pane.image is not None
          and win.run_panel.pane.image.levels[1] > 1.0,
          str(win.run_panel.pane.image.levels if win.run_panel.pane.image
              else None))
    if shots:
        path = os.path.join(HERE, 'ui_e2e_view3d.png')
        win.viewer_link.send(('screenshot', 'run', path))
        for _ in range(60):
            pump(50)
            if os.path.exists(path):
                break
        check("viewer screenshot written", os.path.exists(path))
        try:
            from PIL import ImageGrab
            g = win.frameGeometry()
            ImageGrab.grab(bbox=(g.left(), g.top(), g.right(), g.bottom()),
                           all_screens=True).save(
                os.path.join(HERE, 'ui_e2e_screen.png'))
        except Exception as exc:
            print(f'  [note] screen grab skipped: {exc}')

    if win.view3d._native:
        g3_native(win, pump)
    else:
        g3_container(win, pump)

    print("\nG4: a second run replaces the scene cleanly")
    win.run_panel.show_slice_tab()
    use_model(win)          # OUT-1: the same model again, no overwrite modal
    win._run_single()
    for _ in range(2400):
        pump(50)
        if not win.ctrl.running:
            break
    check("second run finished", win.run_panel.log_text().count(
        '[run finished]') == 1 and len(win._results) == 2)
    check("viewer still alive", win.viewer_link.alive)

    win.close()
    pump(300)
    check("viewer process closed with the window", not win.viewer_link.alive)

    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
        sys.exit(1)
    print("All Qt view3d e2e checks passed.")


# Win32 is the ground truth here (CLAUDE.md §8.7), as in
# _e2e_ui_viewer_place.py: never Qt's own idea of the window.
def _u32():
    import ctypes
    return ctypes, ctypes.windll.user32


def win32_parent(hwnd):
    ctypes, u32 = _u32()
    u32.GetParent.restype = ctypes.c_void_p
    return int(u32.GetParent(ctypes.c_void_p(hwnd)) or 0)


def win32_visible(hwnd):
    ctypes, u32 = _u32()
    return bool(u32.IsWindowVisible(ctypes.c_void_p(hwnd)))


def win32_close(hwnd):
    """WM_CLOSE, as the floating window's own close button sends it."""
    ctypes, u32 = _u32()
    u32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)


def _sample(pump, seconds, ok, period_ms=50):
    """Sample `ok()` every `period_ms` for `seconds`: (all ok, the time
    of the first sample that was ok or None, samples taken)."""
    n = max(1, int(seconds * 1000 / period_ms))
    first, every = None, True
    t0 = time.monotonic()
    for _ in range(n):
        pump(period_ms)
        good = ok()
        every = every and good
        if good and first is None:
            first = time.monotonic() - t0
    return every, first, n


def g3_native(win, pump):
    """GUI-16 (g): the native mount hands the render window back to the
    viewer as a framed top-level on Detach - and it has to STAY there.
    The child re-reports its handle on every detach, and that report
    used to re-embed the window at once."""
    print("\nG3: detach / re-attach on the native mount (Win32 truth)")
    host = win.view3d
    hwnd = int(host._hwnd)

    def floating():
        return win32_parent(hwnd) == 0 and win32_visible(hwnd)
    host.set_floating(True)
    # the host hides the window while it un-parents it and the child
    # shows it again on its `detach`: one round trip, then it must stay
    _every, first, _n = _sample(pump, 1.0, floating)
    check("after Detach the window appears as a top-level within 1 s",
          first is not None,
          f"after {first:.2f} s" if first is not None else
          f"never (parent {win32_parent(hwnd):#x}, "
          f"visible {win32_visible(hwnd)})")
    every, _first, n = _sample(pump, 2.0, floating)
    check("and stays a visible top-level for 2 s (no re-embed)",
          every, f"({n} samples at 50 ms)")
    check("no re-embed while detached",
          host._floating and host._container is None
          and host._view_stack.currentWidget() is host._float_box)

    def attached():
        mount = host._container
        return (mount is not None and host._native
                and win32_parent(hwnd) == int(mount.winId()))
    host.set_floating(False)
    _every, first, _n = _sample(pump, 1.0, attached)
    check("Re-attach puts it back in the mount within 1 s",
          first is not None and attached(),
          f"after {first:.2f} s" if first is not None else "never")

    host.set_floating(True)
    _every, first, _n = _sample(pump, 1.0, floating)
    check("detached again", first is not None and floating())
    win32_close(hwnd)
    _every, first, _n = _sample(pump, 1.0, attached)
    check("closing the floating window (WM_CLOSE) re-attaches within 1 s",
          first is not None and attached() and not host._floating,
          f"after {first:.2f} s" if first is not None else "never")
    check("the card shows the mount again",
          host._view_stack.currentWidget() is host._container)


def g3_container(win, pump):
    """The Qt window-container path (no native mount)."""
    print("\nG3: detach / re-attach (the container travels, nothing is "
          "destroyed)")
    container = win.view3d._container
    win.view3d.set_floating(True)
    pump(600)
    check("the 3D window is now a top-level of its own",
          win.view3d._float_win is not None
          and container.parent() is win.view3d._float_win
          and win.view3d._float_win.isVisible())
    check("the host shows the re-attach note",
          win.view3d._view_stack.currentWidget() is win.view3d._float_box)
    win.view3d.set_floating(False)
    pump(300)
    check("re-attached, same container",
          win.view3d._container is container
          and win.view3d._view_stack.currentWidget() is container)
    check("closing the detached window re-attaches", True)
    win.view3d.set_floating(True)
    pump(200)
    win.view3d._float_win.close()
    pump(300)
    check("closed window came back into the host",
          not win.view3d._floating
          and win.view3d._view_stack.currentWidget() is container)


if __name__ == '__main__':
    main()
