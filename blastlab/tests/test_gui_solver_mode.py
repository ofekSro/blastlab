"""Sidebar solver mode (T34) - headless Tk, no WSL.

The solver (native | blastFoam) is an app-level mode chosen in the
sidebar: every form hides the other solver's rows and cards (never
greys them), the hidden values survive a switch and are stripped from
the Case, Open case adopts the case's solver, the Chain tab presets its
stages from the mode and lets each stage override it, the Results tab
hides the blastFoam-only launchers in native mode, and the mode is
persisted in settings.json.

Run:  cd blastlab/tests && python test_gui_solver_mode.py
"""
import os
import sys
import tempfile

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

# a private settings file: the test must never read or write the user's
_TMP = tempfile.mkdtemp(prefix='blastlab_solver_mode_')
os.environ['BLASTLAB_SETTINGS'] = os.path.join(_TMP, 'settings.json')

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def widget_texts(w):
    """Every non-empty `text` option under a widget."""
    out, stack = [], [w]
    while stack:
        x = stack.pop()
        stack.extend(x.winfo_children())
        try:
            t = x.cget('text')
        except Exception:
            t = None
        if isinstance(t, str) and t:
            out.append(t)
    return out


def build():
    import customtkinter as ctk
    from blastlab.gui import app as appmod
    root = ctk.CTk()
    root.withdraw()
    app = appmod.App(root)
    root.update()
    return root, app


def teardown(root, app):
    app._on_close()                  # cancels the pending after() jobs
    # the icon cache holds PhotoImages of the interpreter that just died;
    # a second root in the same process (only tests do this) must not
    # reuse them ("image pyimageN doesn't exist")
    from blastlab.gui import theme
    theme._ICON_CACHE.clear()


# _mat_combo left this list with T46/N11: the native solvers share the
# JWL material table, so Material shows in BOTH modes now
FOAM_ONLY = {1: ['_act_combo', '_ab_combo'],
             2: ['_act_combo', '_ab_combo', '_cref_combo',
                 '_nproc_entry', '_amr_card', '_zones_card', '_det_card'],
             3: ['_act_combo', '_ab_combo', '_cref_combo',
                 '_nproc_entry', '_amr_card', '_zones_card', '_det_card',
                 '_xc_card']}
# _order_combo: T47/N10 - the MUSCL order knob is native-only
NATIVE_ONLY = {1: ['_eos_combo', '_order_combo'],
               2: ['_eos_combo', '_order_combo'],
               3: ['_eos_combo', '_order_combo', '_cres_combo']}


def main():
    from blastlab.core.case import Case2D, Case3D
    from blastlab.gui import mode, settings

    # never sweep the WSL run dirs from a test
    settings.save(dict(settings.DEFAULTS, auto_cleanup=False))

    print('\nSolverMode (no Tk)')
    seen = []
    sm = mode.SolverMode('native')
    sm.subscribe(lambda m: seen.append(('a', m)))
    sm.subscribe(lambda m: seen.append(('b', m)))
    check('set of the same value is a no-op', sm.set('native') is False
          and seen == [])
    check('set fans out in subscription order',
          sm.set('blastfoam') is True
          and seen == [('a', 'blastfoam'), ('b', 'blastfoam')], str(seen))
    check('normalize is forgiving', mode.normalize(' BlastFoam ') == 'blastfoam'
          and mode.normalize('bogus') == mode.DEFAULT
          and mode.from_label('blastFoam') == 'blastfoam')
    nested = []

    def re_enter(m):
        if m == 'native':
            sm.set('blastfoam')          # from inside a notification
        nested.append(m)
    sm.subscribe(re_enter)
    sm.set('native')
    check('a set() from inside a subscriber is applied after the fan-out',
          nested == ['native', 'blastfoam'] and sm.get() == 'blastfoam',
          str(nested))

    print('\nApp: fresh settings')
    root, app = build()
    check("fresh install starts in blastFoam mode",
          app.solver == 'blastfoam' and app._solver_seg.get() == 'blastFoam'
          and settings.DEFAULTS['solver'] == 'blastfoam',
          f'{app.solver} {app._solver_seg.get()}')
    check('the explainer is filled in', bool(app._solver_hint.cget('text')))

    print('\nSegmented switches are legible in both modes (P2-24)')

    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
             for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def ratio(a, b):
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    for label, seg in (('solver switch', app._solver_seg),
                       ('dimension switch', app.setup._dim_seg)):
        for i, mode_name in enumerate(('light', 'dark')):
            txt = seg.cget('text_color')[i]
            un = seg.cget('unselected_color')[i]
            r_un = ratio(txt, un)
            check(f'{label}, {mode_name}: unselected text >= 4.5:1',
                  r_un >= 4.5, f'{r_un:.2f}')
            if mode_name == 'light':
                r_sel = ratio(txt, seg.cget('selected_color')[i])
                check(f'{label}, light: selected text >= 4.5:1',
                      r_sel >= 4.5, f'{r_sel:.2f}')

    print('\nSetup forms: inventory per mode')
    for m in ('blastfoam', 'native'):
        app.set_solver(m)
        root.update()
        foam = (m == 'blastfoam')
        for d, f in app.setup._forms.items():
            state = {n: getattr(f, n).winfo_manager() != ''
                     for n in FOAM_ONLY[d] + NATIVE_ONLY[d]}
            ok = (all(state[n] == foam for n in FOAM_ONLY[d])
                  and all(state[n] == (not foam) for n in NATIVE_ONLY[d]))
            check(f'{d}D form inventory in {m} mode', ok, str(state))
    texts = [t for f in app.setup._forms.values() for t in widget_texts(f)]
    check('no "(blastFoam)" caption left in any form',
          not any('(blastFoam)' in t for t in texts),
          str([t for t in texts if 'blastFoam' in t]))
    check('the Solver combo is gone from the forms',
          all('solver' not in f.v for f in app.setup._forms.values()))

    print('\nHidden values survive a switch and are stripped from the case')
    app.set_solver('blastfoam')
    app.setup._dim_seg.set('2D')
    app.setup._dim_selected('2D')
    root.update()
    f2 = app.setup._forms[2]
    f2.v['material'].set('C4')
    f2.v['amr_levels'].set('2')
    f2.v['n_procs'].set('abc')
    f2.zones.set([(0.5, 1.5, 0.5, 1.5, 1)])
    f2.det_pts.set([(1.0, 1.0)])
    root.update()
    app.set_solver('native')
    root.update()
    try:
        cn, err = app.setup.get_case(), None
    except ValueError as exc:
        cn, err = None, exc
    check("native get_case() ignores a bad value in a hidden field",
          cn is not None, str(err))
    if cn is not None:
        got = (cn.solver, cn.material, cn.amr_levels, cn.n_procs,
               cn.refine_zones, cn.det_points)
        check('native case carries native defaults for the hidden fields',
              got == ('native', 'TNT', 0, 0, [], None), str(got))
    app.set_solver('blastfoam')
    root.update()
    check('the typed values are still in the form',
          f2.v['material'].get() == 'C4' and f2.v['amr_levels'].get() == '2'
          and f2.v['n_procs'].get() == 'abc'
          and f2.zones.get() == [(0.5, 1.5, 0.5, 1.5, 1.0)]
          and f2.det_pts.get() == [(1.0, 1.0)])
    f2.v['n_procs'].set('2')
    root.update()
    cf = app.setup.get_case()
    check('blastFoam case carries them again',
          (cf.material, cf.amr_levels, cf.n_procs, cf.refine_zones,
           cf.det_points)
          == ('C4', 2, 2, [(0.5, 1.5, 0.5, 1.5, 1)], [(1.0, 1.0)]),
          str((cf.material, cf.amr_levels, cf.n_procs, cf.refine_zones,
               cf.det_points)))

    print('\nAMR rows')
    f2.v['amr_levels'].set('0')
    root.update()
    check('AMR off: coefficient rows hidden, charge-refinement row shown',
          all(w.winfo_manager() == '' for w in f2._amr_entries)
          and f2._cref_combo.winfo_manager() == 'grid')
    f2.v['charge_refine'].set('zone')
    f2.v['amr_levels'].set('2')
    root.update()
    check("AMR on: charge-refinement row hidden, 'zone' kept in the form "
          "but 'global' in the case",
          f2._cref_combo.winfo_manager() == ''
          and all(w.winfo_manager() == 'grid' for w in f2._amr_entries)
          and f2.v['charge_refine'].get() == 'zone'
          and app.setup.get_case().charge_refine == 'global')
    f2.v['amr_levels'].set('0')
    f2.v['charge_refine'].set('global')
    f2.zones.set([])
    f2.det_pts.set([])

    print('\nOpen case adopts the solver')
    app.setup.set_case(Case2D())
    root.update()
    check('a native case flips the app to native',
          app.solver == 'native' and app._solver_seg.get() == 'native')
    c3 = Case3D(Lx=1.4, Ly=1.0, Lz=1.0, cell_size_m=0.025, charge=8.0,
                center=(0.35, 0.5, 0.5), charges=[(1.05, 0.5, 0.5, 8.0)],
                det_points=[(0.35, 0.5, 0.5), (1.05, 0.5, 0.5)],
                solver='blastfoam', material='TNT', n_procs=4)
    app.setup.set_case(c3)
    root.update()
    back = app.setup.get_case()
    check('a blastFoam case flips to blastFoam and round-trips its fields',
          app.solver == 'blastfoam' and back.solver == 'blastfoam'
          and back.charges == c3.charges and back.det_points == c3.det_points
          and back.n_procs == 4, str(vars(back)))

    print('\nChain: preset + per-stage override')
    app.set_solver('native')
    root.update()
    check('stages preset to the global mode',
          all(v == 'native' for v in app.chain.stage_solver.values()),
          str(app.chain.stage_solver))
    app.chain.set_stage_solver(2, 'blastfoam')
    root.update()
    check('one stage overridden',
          app.chain.forms[2].get_case().solver == 'blastfoam'
          and app.chain.forms[1].get_case().solver == 'native'
          and app.chain._stage_solver_seg[2].get() == 'blastFoam'
          # Material shows in BOTH modes since T46; the per-stage
          # override is still visible through a foam-only row
          and app.chain.forms[2]._ab_combo.winfo_manager() == 'grid'
          and app.chain.forms[1]._ab_combo.winfo_manager() == '')
    app.set_solver('blastfoam')
    root.update()
    check('a global change presets every stage again',
          all(v == 'blastfoam' for v in app.chain.stage_solver.values())
          and all(f.mode == 'blastfoam' for f in app.chain.forms.values()))

    print('\nResults: blastFoam-only launchers')
    r = app.results
    check('shown in blastFoam mode',
          r._foam_runs_btn.winfo_manager() == 'pack'
          and r._export_btns['vtk'].winfo_manager() == 'pack')
    app.set_solver('native')
    root.update()
    check('hidden in native mode',
          r._foam_runs_btn.winfo_manager() == ''
          and r._export_btns['vtk'].winfo_manager() == '')
    app.set_solver('blastfoam')
    root.update()
    order = []
    for w in r._export_btns['vtk'].master.pack_slaves():
        try:
            order.append(w.cget('text'))
        except Exception:
            pass
    check('export button order restored after re-show',
          # 'GIF' became 'Animation' when the export learned to write
          # .mp4 as well (T56); the kind key behind it is still 'gif'
          order == ['Export', 'Profile', 'Animation', 'VTK',
                    'Summary CSV', 'Gauges TSV', 'Field CSV', 'Report',
                    'PNGs'],
          str(order))

    print('\nPersistence')
    app.set_solver('native')
    app._save_ui_state()
    check('the mode is written to settings.json',
          settings.load()['solver'] == 'native')
    teardown(root, app)
    root, app = build()
    check('a new window starts in the persisted mode', app.solver == 'native')
    teardown(root, app)
    settings.update(solver='bogus')
    root, app = build()
    check('an unknown persisted value falls back to the default',
          app.solver == mode.DEFAULT, app.solver)
    teardown(root, app)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED:')
        for f in FAILS:
            print('  -', f)
        sys.exit(1)
    print('all solver-mode checks passed')


if __name__ == '__main__':
    main()
