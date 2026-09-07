"""Full GUI-flow check of the blastFoam backend: real App, real forms,
real worker thread and queue drainer - a 1D blastFoam run driven
through the Run button path with the window hidden. Captures every run
log line and every Python warning, verifies the Results panel got the
result and that the field/gauge figures draw. Needs WSL; a window is
created but never shown."""
import os, sys, time
import warnings

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import tkinter as tk

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def pump(root, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        return 0

    caught = []
    warnings.simplefilter('always')
    _orig = warnings.showwarning

    def grab(message, category, filename, lineno, *a, **k):
        caught.append(f'{category.__name__}: {message} '
                      f'({os.path.basename(str(filename))}:{lineno})')
    warnings.showwarning = grab

    import customtkinter as ctk
    from blastlab.gui.app import App
    root = ctk.CTk()
    root.withdraw()
    app = App(root)
    pump(root, 1.0)

    # ── forms round-trip incl. the new fields ──────────────────────────
    from blastlab.core.case import Case1D, Case2D, Case3D
    cases = {
        1: Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.02,
                  gauge_radii=[0.5, 1.0], n_snapshots=2,
                  solver='blastfoam', material='C4', activation='none'),
        2: Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                  cell_size_m=0.02, charge=4.0, center=(0.0, 1.0),
                  gauges=[(0.8, 1.0)], solver='blastfoam',
                  material='TNT', n_procs=2, det_points=[(0.0, 1.0)]),
        3: Case3D(Lx=1.4, Ly=1.0, Lz=1.0, cell_size_m=0.025,
                  charge=8.0, center=(0.35, 0.5, 0.5),
                  charges=[(1.05, 0.5, 0.5, 8.0)],
                  det_points=[(0.35, 0.5, 0.5), (1.05, 0.5, 0.5)],
                  solver='blastfoam', material='TNT', n_procs=4),
    }
    for dim, case in cases.items():
        app.setup.set_case(case)
        pump(root, 0.5)             # debounce -> validation strip
        back = app.setup.get_case()
        same = all(
            getattr(back, f, None) == getattr(case, f, None)
            for f in ('solver', 'material', 'activation', 'n_procs',
                      'charges', 'det_points') if hasattr(case, f))
        check(f'{dim}D form round-trips new fields', same,
              f'{vars(back)}')
    # T34: the case's solver became the app-level mode
    check('a blastFoam case switches the sidebar solver mode',
          app.solver == 'blastfoam' and app._solver_seg.get() == 'blastFoam',
          f'{app.solver} {app._solver_seg.get()}')

    # validation strip for the 3D foam case: no errors
    from blastlab.core.case import validate_case
    rep = validate_case(app.setup.get_case())
    check('3D foam case validates in form', rep.ok, str(rep.errors))

    # ── real 1D blastFoam run through the Run button path ──────────────
    app.setup.set_case(cases[1])
    pump(root, 0.5)
    app._run_single()
    t0 = time.time()
    while app.worker is not None and app.worker.is_alive() \
            and time.time() - t0 < 300:
        pump(root, 0.5)
    pump(root, 2.0)                 # let the drainer finish

    log = app.run_panel.log.get('1.0', 'end')
    check('run finished in the GUI', '[run finished]' in log)
    check('foam banner in log', '1D Spherical Blast - blastFoam' in log)
    check('no ui errors in drain', 'ui error' not in log, log[-400:])
    # warnings must arrive with their MESSAGE, never as the cryptic
    # bare '--> FOAM Warning :' marker; the benign sector-wedge ones
    # collapse into a single friendly note
    check('no cryptic warning markers',
          '--> FOAM Warning' not in log)
    foam_warns = [ln for ln in log.splitlines()
                  if '[foam]' in ln and 'Warning' in ln]
    check('surfaced warnings carry a message',
          all(ln.split('Warning:')[-1].strip() for ln in foam_warns),
          '; '.join(foam_warns[:3]))
    if foam_warns:
        print('    (surfaced:', '; '.join(foam_warns[:2]), ')')
    check('result registered', len(app.results._entries) == 1
          and app.results._entries[0].dim == 1)

    # the Results panel draws the 1D figures without raising
    app.results._refresh()
    pump(root, 1.0)
    check('results figures drawn',
          app.results.field_canvas.figure is not None
          and app.results.gauge_canvas.figure is not None)

    real = [w for w in caught if 'DeprecationWarning' in w
            or 'UserWarning' in w or 'RuntimeWarning' in w]
    check('no Python warnings during session', not real,
          ' | '.join(sorted(set(real))[:5]))

    warnings.showwarning = _orig
    root.destroy()
    print()
    if FAIL:
        print(f"GUI FOAM E2E: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("GUI FOAM E2E: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
