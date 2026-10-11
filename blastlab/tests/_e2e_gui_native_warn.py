"""B11 GUI check: a native solver warning must reach the GUI log pane.
A tiny native planar 2D case with one gauge placed inside a wall is
started through the real App (hidden root, real worker thread and
drainer); the solver drops that gauge with a "[warn] G2 ... inside
Wall 1 - dropped" line, which used to go to stdout only and so never
showed in the GUI. No WSL needed."""
import os, sys, time

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import tkinter as tk
from blastlab.core.case import Case2D
from blastlab.gui.app import App

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
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
    pump(root, 0.5)

    import tempfile
    box = (1.2, 1.6, 0.0, 0.6)                    # (x0, x1, y0, y1)
    case = Case2D(geometry='planar', Lx=2.4, Ly=1.6, cell_size_m=0.04,
                  charge=20.0, center=(0.6, 0.0), obstacles=[box],
                  bcs=dict(x_lo='reflect', x_hi='terminate', y_lo='reflect',
                           y_hi='terminate'),
                  gauges=[(0.3, 0.8), (1.4, 0.3)],   # 2nd is inside the box
                  gauge_file=os.path.join(tempfile.gettempdir(),
                                          'blastlab_native_warn_gauges.txt'),
                  n_snapshots=1, record_frames=0)
    app._start([(2, case)])
    for _ in range(600):                          # <= 5 min
        pump(root, 0.5)
        if app.worker is None or not app.worker.is_alive():
            break
    pump(root, 2.0)                               # let the drainer finish
    log = app.run_panel.log.get('1.0', 'end')

    check('run finished in the GUI', '[run finished]' in log)
    check('native banner reached the GUI log', '2D Blast Solver' in log)
    check('"[warn] Gauge ... dropped" reached the GUI log',
          '[warn] G2 (1.40, 0.30) m inside Wall 1 - dropped' in log,
          '(not in log)')
    check('the kept gauge is not reported dropped',
          'Gauge (0.3, 0.8)' not in log)
    root.destroy()

    print()
    if FAIL:
        print(f"GUI NATIVE WARN: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("GUI NATIVE WARN: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
