"""Real Qt window + real worker thread + real native 2D solver: a
solver warning must reach the Run tab's log, the live pane must move,
and the run must finish through the controller. No WSL, no viewer child
(2D runs have no 3D scene). Offscreen by default; --window shows it."""
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
import tempfile
os.environ.setdefault('BLASTLAB_SETTINGS', os.path.join(
    tempfile.mkdtemp(prefix='blastlab_ui_warn_'), 'settings.json'))

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def main():
    from blastlab.ui.testing import ensure_qapp, pump, use_model
    app = ensure_qapp(offscreen='--window' not in sys.argv)
    from blastlab.core.case import Case2D
    from blastlab.ui.app import MainWindow

    box = (1.2, 1.6, 0.0, 0.6)                    # (x0, x1, y0, y1)
    case = Case2D(geometry='planar', Lx=2.4, Ly=1.6, cell_size_m=0.04,
                  charge=20.0, center=(0.6, 0.0), obstacles=[box],
                  bcs=dict(x_lo='reflect', x_hi='terminate', y_lo='reflect',
                           y_hi='terminate'),
                  gauges=[(0.3, 0.8), (1.4, 0.3)],   # 2nd is inside the box
                  gauge_file=os.path.join(tempfile.gettempdir(),
                                          'blastlab_ui_warn_gauges.txt'),
                  n_snapshots=1, record_frames=0)

    win = MainWindow()
    use_model(win)          # OUT-1: Run needs a runs folder and a model
    win.show()
    pump(200)
    notes = []
    real_notify = win.notify
    win.notify = lambda text, level='info': (notes.append((level, str(text)))
                                             or real_notify(text, level))
    win.setup.set_case(case)
    win._schedule_validate()
    pump(400)
    check("the form adopted the injected case",
          win.setup.dim == 2 and win.current_case() is not None
          and abs(win.current_case().Lx - 2.4) < 1e-12,
          str(win.setup.dim))
    check("validation ran on it", win.run_panel._valid_lbl.text() != '',
          win.run_panel._valid_lbl.text())

    print("\nW1: run it through the Run button's own path")
    t0 = time.time()
    win._run_single()
    check("the Run tab came forward", win.current_tab() == 'run')
    check("the controller is running", win.ctrl.running)
    for _ in range(3000):                         # <= 5 min
        pump(100)
        if not win.ctrl.running:
            break
    log = win.run_panel.log_text()
    print(f"    run took {time.time() - t0:.1f} s")

    check("run finished in the GUI", '[run finished]' in log)
    check("the native banner reached the log", '2D Blast Solver' in log)
    check("the solver's warning reached the log",
          any('[warn]' in ln for ln in log.splitlines()),
          [ln.strip() for ln in log.splitlines() if '[warn]' in ln][:2])
    check("the warning also surfaced on the status line",
          any(lvl == 'warn' and '[warn]' in text for lvl, text in notes),
          str([t[:60] for _l, t in notes][:3]))
    check("no ui error while draining", '[ui error handling' not in log,
          [ln for ln in log.splitlines() if 'ui error' in ln][:2])
    check("a result was posted", len(win._results) == 1,
          str(len(win._results)))
    check("the progress bar was filled at the end",
          win.run_panel.progress.value() == 1000,
          str(win.run_panel.progress.value()))

    print("\nW2: the live pane actually moved")
    pane = win.run_panel.pane
    check("a 2D image pane was built", pane.image is not None)
    check("it holds a real field (positive overpressure)",
          pane.image.levels[1] > 1.0, str(pane.image.levels))
    check("the title carries a simulation time",
          't =' in pane.title(), pane.title())
    check("the obstacle mask is present", pane.image.mask is not None)
    check("the chips show the final step",
          # GUI-6: the chips are the strip's tiles; read them as shown
          win.run_panel.chip_texts()['step'] not in ('', '—'),
          win.run_panel.chip_texts()['step'])

    print("\nW3: no 3D view - and no VTK process - for a 2D run")
    check("the 3D button stays disabled",
          not win.run_panel.view3d_btn.isEnabled())
    check("no scene was attached to the host", not win.view3d.has_scene)
    check("a 2D-only session never spawns the viewer child",
          not win.viewer_link.alive)

    win.close()
    pump(200)
    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
        sys.exit(1)
    print("All Qt native-run checks passed.")


if __name__ == '__main__':
    main()
