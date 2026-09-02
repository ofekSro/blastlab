"""Full GUI-flow test of the embedded 3D view: real App, real worker
thread, real tiny 3D solve. Opens the 3D view mid-run exactly like the
'3D View' button, pumps the Tk event loop, and checks live frames,
playback hand-off and the Results-tab 3D sub-tab. Window stays hidden."""
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import tkinter as tk
from blastlab.core.case import Case3D
from blastlab.gui.app import App

FAIL = []

def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def pump(root, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def main():
    root = tk.Tk()
    root.withdraw()
    app = App(root)

    case = Case3D(Lx=3.0, Ly=3.0, Lz=3.0, cell_size_m=0.05, charge=900.0,
                  center=(1.5, 1.5, 1.0),
                  obstacles=[(2.2, 2.6, 1.1, 1.9, 0.0, 0.8)],
                  gauges=[], record_frames=0, live=False, anim_file=None)

    print("\nG1: start a 3D run through the worker")
    app._start([(3, case)])
    enabled = False
    for _ in range(200):                     # react as soon as it enables
        pump(root, 0.05)
        if str(app.run_panel.view3d_btn['state']) == 'normal':
            enabled = True
            break
    check("view3d button enabled", enabled)

    print("\nG2: open the embedded 3D view mid-run (the button's action)")
    app._open_view3d()
    pump(root, 0.3)
    panel = app.run_panel.view3d
    check("feed attached to hooks", app.worker.hooks.feed3d is not None)
    check("scene created", panel._scene is not None and panel._scene.embedded)

    # pump until the run finishes (tiny case: a few seconds)
    for _ in range(120):
        pump(root, 0.5)
        if app.worker is not None and not app.worker.is_alive():
            break
    pump(root, 0.5)

    print("\nG3: after the run")
    check("worker done", not app.worker.is_alive())
    check("frames arrived live", len(panel._scene.store) >= 1,
          f"n={len(panel._scene.store)}")
    check("panel in playback", panel._scene.done)
    check("feed detached", app.worker.hooks.feed3d is None)
    check("blit happened", panel._photo is not None)

    print("\nG4: Results tab 3D sub-tab")
    ent = app.results._entries[-1]
    check("result registered", ent.dim == 3)
    app.results._open_3d()
    pump(root, 0.5)
    rpanel = app.results.view3d
    check("results 3D scene loaded", rpanel._scene is not None
          and rpanel._scene.done)
    check("snapshots replayed",
          len(rpanel._scene.store) == len(ent.result.snapshots),
          f"{len(rpanel._scene.store)}/{len(ent.result.snapshots)}")
    rpanel._blit()
    check("results 3D renders", rpanel._photo is not None)

    app._on_close()
    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
        sys.exit(1)
    print("All GUI embedded-3D checks passed.")


if __name__ == '__main__':
    main()
