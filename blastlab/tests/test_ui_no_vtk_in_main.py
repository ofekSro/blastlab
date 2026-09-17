"""The Qt front-end must never import VTK/pyvista into its own process:
the 3D scenes live in the viewer child, and a VTK import here is the
11-13 s window freeze (N2-12) plus a second GL context in the GUI.

Builds the whole main window, loads a 3D case, starts a run far enough
for the auto-attach path to publish a scene, and asserts the module
table stays clean. Headless: offscreen Qt, no viewer child spawned."""
import os, sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.ui.testing import ensure_qapp, pump          # noqa: E402

app = ensure_qapp()

FAIL = []
BANNED = ('pyvista', 'vtk', 'vtkmodules', 'pyvistaqt')


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def loaded():
    return sorted({m.split('.')[0] for m in sys.modules
                   if m.split('.')[0] in BANNED})


def main():
    print("\nN1: importing the front-end pulls in no VTK")
    import blastlab.ui.app                                 # noqa: F401
    import blastlab.ui.run_controller                      # noqa: F401
    import blastlab.ui.view3d_host                         # noqa: F401
    import blastlab.ui.viewer_link                         # noqa: F401
    import blastlab.ui.pg_plots                            # noqa: F401
    import blastlab.viz3d.protocol                         # noqa: F401
    import blastlab.viz3d.process                          # noqa: F401
    check("clean after importing every ui module", loaded() == [],
          str(loaded()))

    print("\nN2: building the window and attaching a 3D scene")
    from blastlab.ui.app import MainWindow
    from blastlab.ui.view3d_host import make_ring
    from blastlab.viz3d.feed import Feed3D
    case = os.path.join(HERE, 'cases', 'native_3d_small.json')
    win = MainWindow(case_file=case)
    win.show()
    pump(200)
    check("the 3D case loaded", win.current_case() is not None
          and win.current_case().dim == 3)
    check("clean after the window is built", loaded() == [], str(loaded()))

    # the real auto-attach path, without spawning the child: the solver
    # thread's Feed3D + ring and the host's scene message
    from blastlab.solvers.foam import env as _env           # noqa: F401
    from blastlab.viz3d.geometry import case_geometry
    info = dict(x_c=[0.0, 0.1], y_c=[0.0, 0.1], z_c=[0.0, 0.1], dx=0.1,
                solid=[[[False, False], [False, False]],
                       [[False, False], [False, False]]],
                obstacles=[], Lx=0.2, Ly=0.2, Lz=0.2,
                charge_center=(0.1, 0.1, 0.1), r_exp=0.05,
                bcs=dict(z_lo='reflect'))
    feed = Feed3D(info)
    ring = make_ring(feed)
    sent = []
    win.viewer_link.send = lambda msg: sent.append(msg) or True
    win.viewer_link.ensure_started = lambda: True
    ok = win.view3d.adopt_feed(feed, ring)
    check("the host accepted the scene", ok and win.view3d.has_scene)
    check("a scene message was produced",
          any(m[0] == 'scene' for m in sent))
    check("clean after a scene is attached", loaded() == [], str(loaded()))

    # the setup preview's geometry payload is built here too
    geo = case_geometry(win.current_case(), show_mesh=True)
    check("the geometry preview payload is pure numpy",
          'mesh' in geo and loaded() == [], str(loaded()))

    ring.close(unlink=True)
    win.view3d._has_scene = False
    win.close()
    pump(100)
    check("still clean after shutdown", loaded() == [], str(loaded()))

    print("\nN3: the viewer child is what imports pyvista")
    from blastlab.viz3d import pyvista_available
    check("the availability gate does not import it either",
          pyvista_available() and loaded() == [], str(loaded()))

    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
        sys.exit(1)
    print("All 'no VTK in the GUI process' checks passed.")


if __name__ == '__main__':
    main()
