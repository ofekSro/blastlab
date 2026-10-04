"""The Qt Run tab: control states, stat chips, the pyqtgraph live pane
(orientation, obstacle mask, colour range, mesh overlay), the collapsed
AMR log and the cadence line. Headless: offscreen Qt, no solver run.

GUI-6 (plan §9, batch 2026-09-29-gui-run): the chips became the progress
strip's stat tiles, so U4 reads them through `chip_texts()` with the same
expected strings, U1/U8/U14 look at the Cells tile under its new name
(`_tile_cells`), and U15 (the log | view sash) became "the view spans the
centre and is >= 240 px tall at the 1100 x 720 window" - the splitter is
gone and the log sits in the dock under the view."""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.ui.testing import ensure_qapp, pump          # noqa: E402

app = ensure_qapp()

from PySide6.QtCore import QPointF                         # noqa: E402
from blastlab.core.constants import P_AIR                  # noqa: E402
from blastlab.solvers.hooks import Progress                # noqa: E402
from blastlab.ui.run_panel import RunPanel                 # noqa: E402

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


# a deliberately non-square grid with a carved cell, so an orientation
# or transpose slip cannot pass
X_FACE = np.linspace(0.0, 1.0, 5)          # 4 cells in x
Y_FACE = np.linspace(0.0, 2.0, 9)          # 8 cells in y
SOLID = np.zeros((4, 8), bool)
SOLID[1, 2] = True
INFO_2D = dict(dim=2, x_face=X_FACE, y_face=Y_FACE, solid=SOLID,
               xlabel='x [m]', ylabel='y [m]', title='y = 1.25 m',
               gauges=[(1, 0.5, 1.0), (2, 0.9, 0.2)], trigger_gauge=1)
RAMP = P_AIR + 1e3 * np.arange(32, dtype=float).reshape(4, 8)


def main():
    rp = RunPanel()
    rp.resize(1200, 700)
    rp.show()
    pump(60)

    print("\nU1: idle state")
    check("Run and Initialise are armed, Stop and Exec are not",
          rp.run_btn.isEnabled() and rp.init_btn.isEnabled()
          and not rp.stop_btn.isEnabled()
          and not any(b.isEnabled() for b in rp._exec_btns))
    check("the live pane starts on its placeholder",
          rp.pane.image is None and rp.pane.line is None)
    check("the AMR cell chip is hidden until a level map arrives",
          not rp._tile_cells.isVisible())

    print("\nU2: an invalid case gates the start buttons")
    rp.set_validation(False, 3)
    check("the verdict is on the Run tab",
          rp._valid_lbl.text() == '3 errors - see Setup',
          rp._valid_lbl.text())
    check("Run and Initialise are refused",
          not rp.run_btn.isEnabled() and not rp.init_btn.isEnabled())
    rp.set_validation(True)
    check("a valid case arms them again",
          rp.run_btn.isEnabled() and rp._valid_lbl.text() == 'Case OK')

    print("\nU3: running state")
    rp.set_running(True)
    check("Stop is armed and reads as danger",
          rp.stop_btn.isEnabled() and rp.stop_btn.objectName() == 'danger')
    check("Run and Initialise are held",
          not rp.run_btn.isEnabled() and not rp.init_btn.isEnabled())
    check("every Exec button is live",
          all(b.isEnabled() for b in rp._exec_btns))

    print("\nU4: progress fills the chips")
    rp.on_progress(Progress(step=1234, t=1.5e-3, dt=2.5e-7, p_max=345678.0,
                            frac=0.37))
    chips = rp.chip_texts()
    check("step", chips['step'] == '1234', chips['step'])
    check("t in ms", chips['t [ms]'] == '1.500', chips['t [ms]'])
    check("dt in s", chips['dt [s]'] == '2.50e-07', chips['dt [s]'])
    check("p max in kPa, not Pa", chips['p max [kPa]'] == '345.7',
          chips['p max [kPa]'])
    check("the bar followed frac", rp.progress.value() == 370,
          rp.progress.value())
    rp.set_paused(True)
    check("a hold names the step it is on",
          rp._paused_lbl.text() == 'PAUSED at step 1234',
          rp._paused_lbl.text())
    rp.set_paused(False)
    check("released", rp._paused_lbl.text() == '')

    print("\nU5: the 2D live pane")
    rp.on_run_started(INFO_2D)
    check("an image pane was built", rp.pane.image is not None)
    check("the axes are labelled from the run info",
          rp.pane.plot.getAxis('bottom').labelText == 'x [m]'
          and rp.pane.plot.getAxis('left').labelText == 'y [m]')
    check("gauge markers are drawn (dot + label each)",
          len(rp.pane._markers) == 4, str(len(rp.pane._markers)))
    rp.on_frame(RAMP, 1.0e-3)
    img = rp.pane.image.img
    check("the image keeps the field's (Nx, Ny) shape - no transpose",
          img.image.shape == (4, 8), str(img.image.shape))
    check("overpressure in kPa autoscaled to the frame",
          rp.pane.image.levels == (0.0, 31.0), str(rp.pane.image.levels))
    # orientation: pixel (0, Ny) is the TOP-left corner of the domain,
    # exactly where pcolormesh(x_face, y_face, field.T) put it
    top_left = img.mapToView(QPointF(0.0, 8.0))
    bottom_right = img.mapToView(QPointF(4.0, 0.0))
    check("pixel (0, Ny) maps to (x_face[0], y_face[-1])",
          abs(top_left.x() - X_FACE[0]) < 1e-9
          and abs(top_left.y() - Y_FACE[-1]) < 1e-9,
          f'({top_left.x():g}, {top_left.y():g})')
    check("pixel (Nx, 0) maps to (x_face[-1], y_face[0])",
          abs(bottom_right.x() - X_FACE[-1]) < 1e-9
          and abs(bottom_right.y() - Y_FACE[0]) < 1e-9,
          f'({bottom_right.x():g}, {bottom_right.y():g})')
    check("the carved cell is painted by the obstacle mask, not the field",
          rp.pane.image.mask is not None
          and rp.pane.image.mask.image[1, 2, 3] == 255
          and rp.pane.image.mask.image[0, 0, 3] == 0)
    check("the title carries the time",
          rp.pane.title() == 'y = 1.25 m  t = 1.000 ms', rp.pane.title())

    print("\nU6: the colour range can be pinned for the run")
    rp.auto_clim.setChecked(False)
    rp.clim_min.setText('0')
    rp.clim_max.setText('50')
    rp._clim_changed()
    check("Min/Max are editable only with Auto off",
          rp.clim_min.isEnabled() and rp.clim_max.isEnabled())
    check("the pinned range is applied", rp.pane.image.levels == (0.0, 50.0),
          str(rp.pane.image.levels))
    rp.on_frame(RAMP * 2.0, 2.0e-3)
    check("a stronger frame does not rescale the picture",
          rp.pane.image.levels == (0.0, 50.0), str(rp.pane.image.levels))
    # an unparsable box falls back to autoscale rather than pinning the
    # picture to a nonsense range (as the Tk pane did)
    rp.clim_max.setText('nonsense')
    rp._clim_changed()
    check("an unparsable box falls back to autoscale",
          rp.pane.image.levels[1] > 50.0, str(rp.pane.image.levels))
    rp.auto_clim.setChecked(True)
    rp.on_frame(RAMP, 3.0e-3)
    check("Auto back on autoscales again",
          rp.pane.image.levels == (0.0, 31.0), str(rp.pane.image.levels))
    check("Min/Max are locked while Auto is on",
          not rp.clim_min.isEnabled() and not rp.clim_max.isEnabled())

    print("\nU7: the mesh overlay follows the checkbox")
    check("no overlay by default", len(rp.pane.overlay.item.getData()[0]) == 0)
    rp.show_mesh.setChecked(True)
    n_uniform = len(rp.pane.overlay.item.getData()[0])
    check("Show mesh draws the cell edges", n_uniform > 0, str(n_uniform))
    rp.show_mesh.setChecked(False)
    check("unchecking clears them",
          len(rp.pane.overlay.item.getData()[0]) == 0)

    print("\nU8: dynamic AMR - the cell chip and the per-frame mesh")
    levels = np.zeros((4, 8), np.int8)
    levels[2:, 4:] = 1
    rp.on_run_started(dict(INFO_2D, display_level=1))
    rp.show_mesh.setChecked(True)
    rp.on_frame(RAMP, 4.0e-3, levels=levels)
    check("the cells chip appears with a level map",
          rp._tile_cells.isVisible())
    # 8 level-1 cells count once each, the 24 level-0 cells stand for
    # 4 display cells each -> 8 + 24/4 = 14
    check("the chip counts true cells, not display cells",
          rp.chip_texts()['cells'] == '14', rp.chip_texts()['cells'])
    check("the overlay was rebuilt from the frame's own levels",
          len(rp.pane.overlay.item.getData()[0]) != n_uniform,
          f'{len(rp.pane.overlay.item.getData()[0])} vs {n_uniform}')

    print("\nU9: frames of the wrong shape are dropped, not fatal")
    before = rp.pane.image.levels
    rp.on_frame(np.full((9, 9), P_AIR + 1e6), 5.0e-3)
    check("a chain-boundary frame for another stage is ignored",
          rp.pane.image.levels == before, str(rp.pane.image.levels))

    print("\nU10: the cadence line says how fast the view can move")
    check("a native run claims no cadence", rp.cadence_text() == '',
          rp.cadence_text())
    rp.set_cadence(dt=5e-5)
    check("seconds cadence", rp.cadence_text() == 'frames every ~0.05 ms',
          rp.cadence_text())
    rp.set_cadence(steps=20)
    check("steps cadence uses the newest dt",
          rp.cadence_text() == 'frames every ~5 µs', rp.cadence_text())
    rp.on_frame(RAMP, 6.0e-3)
    check("and it is appended to the title",
          rp.pane.title().endswith('frames every ~5 µs'),
          rp.pane.title())

    print("\nU11: the log collapses an AMR burst")
    rp.on_log('plain line')
    for k in range(4):
        rp.on_log(f'  [blastfoam] AMR t = {k} s  cells = {1000 + k}')
    rp.on_log('after')
    lines = rp.log_text().splitlines()
    check("four AMR writes are one line", len(lines) == 3, str(lines))
    check("the surviving line counts them",
          lines[1].endswith('[4 AMR writes so far]'), lines[1])
    check("ordinary lines are untouched",
          lines[0] == 'plain line' and lines[2] == 'after')

    print("\nU12: the refresh box reports an unusable value")
    rp.mark_refresh(False)
    check("red border on", rp.refresh_val.property('error') == 'true')
    rp.mark_refresh(True)
    check("and off again", rp.refresh_val.property('error') == 'false')
    rp.set_refresh_policy_text('0.5', 'steps')
    check("the policy round-trips", rp.refresh_policy_text() == ('0.5',
                                                                 'steps'),
          str(rp.refresh_policy_text()))

    print("\nU13: the 1D pane is a radial line, autoscaled")
    rp.on_run_started(dict(dim=1, radius_m=3.0,
                           gauges=[(1, 1.0, None), (2, 2.0, None)]))
    check("a line pane was built",
          rp.pane.line is not None and rp.pane.image is None)
    r = np.linspace(0.0, 3.0, 64)
    rp.on_frame(np.vstack([r, P_AIR + 4e4 * np.exp(-r)]), 5.0e-4)
    pump(80)                      # pyqtgraph auto-ranges on the repaint
    ((x0, x1), (y0, y1)) = rp.pane.plot.viewRange()
    check("x is pinned to the domain radius",
          abs(x0) < 0.2 and abs(x1 - 3.0) < 0.2, f'{x0:g}..{x1:g}')
    check("y followed the data, not the 0..10 placeholder (T61)",
          y1 > 20.0, f'{y0:g}..{y1:g}')

    print("\nU14: a new run resets everything the last one left")
    rp.set_running(False)
    rp.set_running(True)
    check("chips are blank again",
          rp.chip_texts()['step'] == '—'
          and rp.chip_texts()['p max [kPa]'] == '—')
    check("the pane is back to its placeholder",
          rp.pane.image is None and rp.pane.line is None)
    check("the log was cleared", rp.log_text() == '')
    check("the cell chip is hidden again", not rp._tile_cells.isVisible())
    check("the cadence does not carry over", rp.cadence_text() == '')
    rp.set_running(False)
    check("the 3D button only lives during a run",
          not rp.view3d_btn.isEnabled())

    print("\nU15: the view spans the centre and keeps its height (QA-17)")
    # the panel's size inside the 1100 x 720 minimum window: 1100 - 2 x 16
    # of window padding, 720 - the 64 px top bar - the 28 px status bar -
    # 18 px of column margins (measured through MainWindow in R1)
    rp.resize(1068, 610)
    pump(80)
    view, centre = rp._view_frame, rp._centre
    check("the view spans the centre column's width",
          view.width() == centre.width(),
          f'{view.width()} vs {centre.width()}')
    check("and is at least 240 px tall at the 1100 x 720 window",
          view.height() >= 240, str(view.height()))

    pump(20)
    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
        sys.exit(1)
    print("All Qt run-panel checks passed.")


if __name__ == '__main__':
    main()
