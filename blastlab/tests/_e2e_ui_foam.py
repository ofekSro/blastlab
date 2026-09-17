"""A real blastFoam run, all the way through the Qt window.

blastFoam is the owner's default solver and, until now, the one path the
port had never exercised end to end: every Qt suite ran the native
solvers. `_e2e_gui_foam.py` does this for the Tk app; this is its Qt
counterpart, and it goes further where the port added something - the
export gating, the run browser against real WSL, and the foam-only
fields surviving a form round trip in all three dimensions.

Needs WSL with blastFoam; it SKIPs cleanly without them. The window is
created but never shown, and the run is a small 1D one so the whole
thing takes a couple of minutes.

The settings file is private and says `auto_cleanup: false`, which is
not a formality: building the app starts `foam_env.start_auto_cleanup`,
and on 2026-09-17 that deleted a 374 GB run corpus down to 21 GB
because a test let it read the real settings.

Run:  cd blastlab/tests && python _e2e_ui_foam.py
      python _e2e_ui_foam.py --window    (watch it)
"""
import os
import sys
import tempfile
import time
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')
_dir = tempfile.mkdtemp(prefix='blastlab_ui_foam_')
_settings = os.path.join(_dir, 'settings.json')
with open(_settings, 'w', encoding='utf-8') as _f:
    _f.write('{"auto_cleanup": false}')
os.environ['BLASTLAB_SETTINGS'] = _settings

#: a 1D run has to finish inside this, or something is wrong
RUN_TIMEOUT_S = 420

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f'  [SKIP] blastFoam unavailable: {detail}')
        return 0
    print(f'blastFoam: {detail}')

    caught = []
    warnings.simplefilter('always')
    _orig = warnings.showwarning

    def grab(message, category, filename, lineno, *a, **k):
        caught.append(f'{category.__name__}: {message} '
                      f'({os.path.basename(str(filename))}:{lineno})')
    warnings.showwarning = grab

    from blastlab.ui.testing import ensure_qapp, pump
    ensure_qapp(offscreen='--window' not in sys.argv)
    from blastlab.core.case import Case1D, Case2D, Case3D, validate_case
    from blastlab.ui import dialogs
    from blastlab.ui.app import MainWindow

    out = tempfile.mkdtemp(prefix='blastlab_ui_foam_out_')
    win = MainWindow()
    win.show()
    pump(200)

    print('\nF1: the foam-only fields survive a form round trip')
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
        win.setup.set_case(case)
        pump(300)                       # the debounce, then validation
        back = win.setup.get_case()
        fields = [f for f in ('solver', 'material', 'activation',
                              'n_procs', 'charges', 'det_points',
                              'adaptive_write')
                  if hasattr(case, f)]
        bad = [f for f in fields
               if getattr(back, f, None) != getattr(case, f, None)]
        check(f'{dim}D keeps every foam field', not bad,
              '; '.join(f'{f}: {getattr(case, f, None)!r} -> '
                        f'{getattr(back, f, None)!r}' for f in bad))
    check('and the sidebar followed the case into blastFoam mode',
          win.solver_mode.get() == 'blastfoam', win.solver_mode.get())
    rep = validate_case(win.setup.get_case())
    check('the 3D foam case validates with no errors', rep.ok,
          str(rep.errors))

    print('\nF2: a real 1D blastFoam run, started the way a user starts it')
    win.setup.set_case(cases[1])
    win._schedule_validate()
    pump(400)
    t0 = time.time()
    win._run_single()                   # what the Run button and F5 do
    check('the Run tab came forward', win.current_tab() == 'run')
    while win.ctrl.running and time.time() - t0 < RUN_TIMEOUT_S:
        pump(100)
    took = time.time() - t0
    pump(300)                           # let the drain finish
    print(f'    the run took {took:.1f} s')
    log = win.run_panel.log_text()
    check('it finished', '[run finished]' in log,
          log[-300:] if '[run finished]' not in log else '')
    check('and it really was blastFoam, not a native fallback',
          '1D Spherical Blast - blastFoam' in log,
          [ln for ln in log.splitlines() if 'Blast' in ln][:2])
    check('nothing broke while draining the queue',
          'ui error' not in log, log[-400:])

    print('\nF3: what the foam backend said reached the user intact')
    check('no cryptic warning markers', '--> FOAM Warning' not in log)
    foam_warns = [ln for ln in log.splitlines()
                  if '[foam]' in ln and 'Warning' in ln]
    check('every surfaced warning carries its message',
          all(ln.split('Warning:')[-1].strip() for ln in foam_warns),
          '; '.join(foam_warns[:3]))
    if foam_warns:
        print(f'    surfaced: {"; ".join(foam_warns[:2])}')

    print('\nF4: the result reached Results and drew')
    res = win.results
    check('one entry in the picker', len(res.entries()) == 1,
          str([e.label for e in res.entries()]))
    if not res.entries():
        warnings.showwarning = _orig
        print(f'\nUI FOAM E2E: FAIL - no result to inspect')
        return 1
    ent = res.entries()[0]
    check('labelled as a 1D run', ent.dim == 1 and '1D' in ent.label,
          ent.label)
    win._show('results')
    pump(200)
    check('the 1D profiles page is showing, not the map',
          res.fields.page() == 'figure', res.fields.page())
    check('and it drew a figure',
          res.fields.canvas.figure is not None)
    res.show_view('Gauges')
    pump(150)
    check('the gauge canvas has a figure',
          res.gauges.canvas.figure is not None)
    rows = res.gauges.rows()
    check('one summary row per gauge', len(rows) == 2, str(len(rows)))
    check('carrying a real peak overpressure',
          rows and rows[0][1] not in ('', '0.0'),
          str(rows[0][:3]) if rows else '')

    print('\nF5: the blastFoam-only exports are offered, and work')
    vtk_btn = res._export_btns.get('vtk')
    check('the VTK button is visible for a foam run',
          vtk_btn is not None and vtk_btn.isVisible(),
          'missing' if vtk_btn is None else f'visible={vtk_btn.isVisible()}')
    check('and it is enabled', vtk_btn is not None and vtk_btn.isEnabled(),
          '' if vtk_btn is None else (vtk_btn.toolTip() or ''))
    real_dir = dialogs.pick_dir
    dialogs.pick_dir = lambda *a, **k: out
    try:
        res.export('pngs', threaded=False)
        pump(200)
    finally:
        dialogs.pick_dir = real_dir
    pngs = sorted(f for f in os.listdir(out) if f.endswith('.png'))
    check('PNGs wrote real files', len(pngs) >= 1, str(pngs))
    check('and each is a real image',
          all(os.path.getsize(os.path.join(out, f)) > 5000 for f in pngs),
          str([(f, os.path.getsize(os.path.join(out, f)))
               for f in pngs][:2]))

    print('\nF6: the run browser, against the real WSL run corpus')
    browser = res.open_run_browser()
    pump(400)
    check('it opened', browser is not None)
    if browser is not None:
        SIZE_COL = 2
        for _ in range(60):             # phase one: names, dims, dates
            pump(100)
            if browser.table.rowCount():
                break
        n = browser.table.rowCount()
        check('and listed the runs WSL actually has', n > 0, f'{n} rows')
        if n:
            names = [browser.table.item(r, 0).text() for r in range(n)]
            check('including the one this test just made',
                  any('1d' in s.lower() or 'blast' in s.lower()
                      for s in names), str(names[:4]))
            # phase two is a `du` over the whole corpus in WSL, so it
            # arrives well after the names; until it does the column
            # holds an ellipsis on purpose
            for _ in range(300):
                pump(100)
                if all(browser.table.item(r, SIZE_COL).text().strip()
                       != '…' for r in range(browser.table.rowCount())):
                    break
            rows = [[browser.table.item(r, c).text()
                     for c in range(browser.table.columnCount())]
                    for r in range(browser.table.rowCount())]
            unsized = [r[0] for r in rows if r[SIZE_COL].strip() == '…']
            check('and the sizes arrived for every row', not unsized,
                  f'{len(unsized)} still an ellipsis: {unsized[:3]}')
            check('with every other column filled in too',
                  all(all(s.strip() for s in r) for r in rows),
                  str(next((r for r in rows
                            if not all(s.strip() for s in r)), '')))
        browser.close()
        pump(100)

    real = [w for w in caught if 'DeprecationWarning' in w
            or 'UserWarning' in w or 'RuntimeWarning' in w]
    check('no Python warnings during the whole session', not real,
          ' | '.join(sorted(set(real))[:5]))

    warnings.showwarning = _orig
    win.close()
    pump(100)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'UI FOAM E2E: PASS ({len(RAN)} checks, run {took:.0f} s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
