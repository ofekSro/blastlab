"""Manual e2e (WSL): a full 1D -> 2D -> 3D chain driven through the GUI
against blastFoam (P2-6).

`_e2e_gui_foam.py` drives a single foam run through the real App; this
does the same for the Chain tab, which had no end-to-end driver at all -
its foam path was only ever exercised piecemeal. That gap is not
theoretical: T62 found that a chained 3D blastFoam stage had NEVER been
able to run (three stacked blockers on the profile-initialised path),
and nothing in the suite noticed, because the 2D stage looked healthy
and no test ran a chain through to a 3D foam stage.

What this drives, all through the panel's own widgets:
  * the three stage forms, each switched to blastFoam through the
    per-stage selector (T34);
  * the Chain Run button, so the profile hand-offs are wired by
    `ChainPanel._run` and not by the test - stage1_profile.txt and
    stage2_profile.npz come out of the panel's own workspace;
  * the real worker thread and queue drainer, so each stage's result
    lands in the Results panel the way a user sees it;
  * one physical clock across the stages (N7/T41): the 2D and 3D stages
    must start at the profile's t0, not at 0.

Small domains, ~10-20 minutes. Needs an idle WSL.

Run:  cd blastlab/tests && python _e2e_gui_chain_foam.py
"""
import os
import sys
import time
import warnings

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

WS = os.path.join(HERE, '_chain_study', 'gui_foam')
FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def pump(root, seconds, until=None):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        if until is not None and until():
            return True
        time.sleep(0.02)
    return until is None or bool(until and until())


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        return 0

    caught = []
    warnings.simplefilter('always')

    def grab(message, category, filename, lineno, *a, **k):
        caught.append(f'{category.__name__}: {message} '
                      f'({os.path.basename(str(filename))}:{lineno})')
    warnings.showwarning = grab

    import customtkinter as ctk
    from blastlab.core.case import Case1D, Case2D, Case3D
    from blastlab.gui.app import App

    os.makedirs(WS, exist_ok=True)
    root = ctk.CTk()
    root.withdraw()
    app = App(root)
    # messagebox.showerror is MODAL: unattended, a failed stage would
    # park this script on a dialog nobody can click. Record instead, and
    # print the traceback - a chain failure has to be readable, not a
    # window that never closes.
    errors = []
    app.show_error = lambda title, msg: errors.append((title, msg))
    pump(root, 1.0)

    chain = app.chain
    chain.ws_var.set(WS)

    # Deliberately small: the point is the hand-off, not the physics.
    # Stage 1 stops well inside stage 2's domain, and stage 2 inside
    # stage 3's, so each stage really continues a state.
    stages = {
        1: Case1D(radius_m=0.2, charge_kg=0.2, cell_size_m=0.002,
                  gauge_radii=[0.15], n_snapshots=1, solver='blastfoam'),
        2: Case2D(geometry='axisymmetric', Lx=0.5, Ly=1.0,
                  cell_size_m=0.02, center=(0.0, 0.5),
                  gauges=[(0.3, 0.5)], n_snapshots=1,
                  solver='blastfoam', material='TNT',
                  bcs=dict(x_lo='reflect', x_hi='terminate',
                           y_lo='terminate', y_hi='terminate')),
        3: Case3D(Lx=1.0, Ly=1.0, Lz=0.6, cell_size_m=0.04,
                  center=(0.5, 0.5, 0.3), gauges=[(0.8, 0.5, 0.3)],
                  n_snapshots=1, solver='blastfoam', material='TNT'),
    }
    for d, case in stages.items():
        chain.use[d].set(True)
        chain.set_stage_case(d, case)
        pump(root, 0.3)
        check(f'stage {d} form took the case on blastFoam',
              chain.stage_solver[d] == 'blastfoam',
              chain.stage_solver.get(d))

    n_before = len(app.results._entries)
    t0 = time.perf_counter()
    chain._run()                       # the Run button's own callback
    pump(root, 3.0)
    check('the chain started a worker', app.worker is not None)

    # let it run: three foam stages on tiny domains
    done = pump(root, 60 * 40,
                until=lambda: app.worker is None or not app.worker.is_alive())
    wall = time.perf_counter() - t0
    print(f'  --- chain finished in {wall:.0f} s ---')
    check('the chain ran to completion (worker exited)', done)

    # The worker queues the LAST stage's ('result'|'error', ...) and then
    # ('done',) microseconds before its thread dies, but App._drain is a
    # root.after(50) callback - so without this wait the final stage's
    # message is structurally unreachable and the run looks like it
    # produced one result fewer than it did. _e2e_gui_foam.py:100 and
    # _qa_gui_harness.py:599 already do this; this script did not.
    pump(root, 15, until=lambda: not app._drain_pending)
    pump(root, 1.0)

    # the panel's own workspace holds the hand-offs it wired
    p1 = os.path.join(WS, 'stage1_profile.txt')
    p2 = os.path.join(WS, 'stage2_profile.npz')
    check('stage 1 wrote the 1D profile the panel named', os.path.isfile(p1))
    check('stage 2 wrote the 2D profile the panel named', os.path.isfile(p2))
    for d in (1, 2, 3):
        check(f'stage {d} case.json saved in the workspace',
              os.path.isfile(os.path.join(WS, f'stage{d}_case.json')))

    # A stage that raised is the single most useful thing this script can
    # tell you, and it used to be thrown away entirely.
    if app.worker is not None and getattr(app.worker, 'error', None):
        print(f'\n  !! stage {app.worker.error_stage + 1} raised:\n')
        for ln in app.worker.error.rstrip().splitlines():
            print(f'     {ln}')
        print()
    for title, msg in errors:
        print(f'  !! {title}: {msg}')

    results = [e.result for e in app.results._entries[n_before:]]
    check('three results reached the Results panel', len(results) >= 3,
          f'{len(results)} results')
    labels = [e.label for e in app.results._entries[n_before:]]
    print(f'  results: {labels}')

    # N7/T41: one physical clock - a chained stage starts at the
    # profile's t0, so its gauge times do not restart from zero
    times = []
    for res in results[-3:]:
        # `gauges['times']` is a numpy array, so `x or []` raises
        # ValueError("truth value of an array ... is ambiguous") - test
        # against None instead (gauge_summary.py:107 does the same).
        g = getattr(res, 'gauges', None)
        g = {} if g is None else g
        _t = g.get('times')
        ts = [] if _t is None else list(_t)
        times.append((ts[0] if ts else None, ts[-1] if ts else None))
    print(f'  gauge time spans per stage: {times}')
    if len(times) == 3 and all(t[0] is not None for t in times):
        check('stage 2 starts where stage 1 ended, not at 0',
              times[1][0] > 0.9 * times[0][1],
              f'{times[1][0]:.3e} vs {times[0][1]:.3e}')
        check('stage 3 starts where stage 2 ended, not at 0',
              times[2][0] > 0.9 * times[1][1],
              f'{times[2][0]:.3e} vs {times[1][1]:.3e}')

    # A peak MAP is a 2D/3D thing: the 1D solvers (native and foam alike)
    # return a radial `final_profile`, and never set meta['p_peak'] -
    # asserting one for stage 1 was asking for something 1D has never
    # produced. Check each stage against its own contract.
    dims = [e.dim for e in app.results._entries[n_before:]][-3:]
    for lbl, dim, res in zip(labels[-3:], dims, results[-3:]):
        meta = getattr(res, 'meta', {})
        if dim == 1:
            # final_profile is a dict (t, r, rho, u, e, p, ...), not an
            # array - the 1D contract is a radial pressure profile.
            prof = meta.get('final_profile') or {}
            p = prof.get('p')
            check(f'{lbl}: a finite radial pressure profile',
                  p is not None and len(p) and float(max(p)) > 0,
                  str(None if p is None else max(p)))
        else:
            pk = meta.get('p_peak')
            check(f'{lbl}: a finite peak map',
                  pk is not None and float(pk.max()) > 0,
                  str(None if pk is None else pk.max()))

    check('no Python warnings during the chain', not caught, str(caught[:5]))

    root.destroy()

    print()
    if FAIL:
        print(f"GUI CHAIN FOAM: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("GUI CHAIN FOAM: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
