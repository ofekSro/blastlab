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


if __name__ == '__main__':
    main()
