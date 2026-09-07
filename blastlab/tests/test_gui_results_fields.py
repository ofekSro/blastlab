"""ResultsPanel peak-overpressure / net-impulse fields (N1): headless
check. Synthetic 2D and 3D results carrying meta['p_peak'] /
meta['impulse'] must expose the new field-selector entries, render each
of them through _draw_field without error and export the extra PNG
figures; a result without the maps (older loaded run) must hide them.
Headless (Agg backend, hidden Tk root) - needs customtkinter, no WSL, no
solver run.

Run:  cd blastlab/tests && python test_gui_results_fields.py
"""
import os
import sys

import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.core.grid import make_geometry, make_grid          # noqa: E402
from blastlab.output import plots                               # noqa: E402
from blastlab.solvers.hooks import Result                       # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def fake_2d(with_maps=True):
    Lx, Ly, dx = 1.0, 0.8, 0.1
    g = make_geometry('planar', Lx, Ly, dx)
    nx, ny = g['Nx'], g['Ny']
    solid = np.zeros((nx, ny), dtype=bool)
    p = np.full((nx, ny), P_AIR) + 1e3
    snaps = {'t = 0.100 ms': dict(p=p, rho=np.full_like(p, 1.2),
                                  speed=np.zeros_like(p)),
             't = 0.200 ms (final)': dict(p=p, rho=np.full_like(p, 1.2),
                                          speed=np.zeros_like(p))}
    meta = dict(x_c=g['x_c'], y_c=g['y_c'], x_face=g['x_face'],
                y_face=g['y_face'], solid=solid, geometry='planar',
                Lx=Lx, Ly=Ly, dx=dx, eos='idealGas', bcs={}, obstacles=[],
                charge=1.0, charge_center=(0.5, 0.4), r_exp=0.05,
                from_profile=False)
    if with_maps:
        meta['p_peak'] = p + 5e3
        meta['impulse'] = np.full_like(p, 12.5)
    gauges = dict(times=np.array([]), points=[], pressures=[])
    return Result(snaps, gauges, meta, 'end time reached', False)


def fake_3d(with_maps=True):
    Lx, Ly, Lz, dx = 1.2, 1.0, 0.8, 0.2
    grid = make_grid(Lx, Ly, Lz, dx)
    x_c, y_c, z_c = grid['x_c'], grid['y_c'], grid['z_c']
    nx, ny, nz = len(x_c), len(y_c), len(z_c)
    solid = np.zeros((nx, ny, nz), dtype=bool)
    j0, k0 = ny // 2, nz // 2
    p = np.full((nx, ny, nz), P_AIR, dtype=np.float32) + 1e3
    snap = dict(p=p, rho_xz=np.full((nx, nz), 1.2, np.float32),
                rho_xy=np.full((nx, ny), 1.2, np.float32),
                speed_xz=np.zeros((nx, nz), np.float32),
                speed_xy=np.zeros((nx, ny), np.float32), t=1e-4,
                rho3=np.full((nx, ny, nz), 1.2, np.float32))
    snaps = {'t = 0.100 ms (final)': snap}
    meta = dict(x_c=x_c, y_c=y_c, z_c=z_c, x_face=grid['x_face'],
                y_face=grid['y_face'], z_face=grid['z_face'], j0=j0, k0=k0,
                slice_axis='y', s0=j0, solid=solid, Lx=Lx, Ly=Ly, Lz=Lz,
                dx=dx, eos='idealGas', bcs={}, obstacles=[], charge=1.0,
                charge_center=(Lx / 2, Ly / 2, Lz / 2), r_exp=0.1,
                r_src=0.1, from_profile=None)
    if with_maps:
        meta['p_peak'] = p + 5e3
        meta['impulse'] = np.full_like(p, 12.5)
    gauges = dict(times=np.array([]), points=[], pressures=[])
    return Result(snaps, gauges, meta, 'end time reached', False)


NEW_2D = ['peak overpressure', 'net ovp impulse']
NEW_3D = ['peak overpressure (x-z)', 'peak overpressure (x-y)',
          'net ovp impulse (x-z)', 'net ovp impulse (x-y)']


def main():
    import customtkinter as ctk
    from blastlab.gui.results_panel import ResultsPanel

    root = ctk.CTk()
    root.withdraw()
    panel = ResultsPanel(root)

    print("\nfield selector + rendering")
    for label, dim, res, new in (('2D', 2, fake_2d(), NEW_2D),
                                 ('3D', 3, fake_3d(), NEW_3D)):
        panel.add_result(label, dim, res)
        values = list(panel.field_sel.cget('values'))
        check(f'{label}: new fields listed', all(f in values for f in new),
              str(values))
        if dim == 3:
            check('3D: isosurface stays last', values[-1] == 'isosurface',
                  str(values))
        for f in new:
            try:
                panel.field_sel.set(f)
                panel._draw_field()
                fig = panel.field_canvas.figure if hasattr(
                    panel.field_canvas, 'figure') else None
                ok, detail = True, ''
            except Exception as exc:
                ok, detail = False, f'{type(exc).__name__}: {exc}'
            check(f"{label}: '{f}' renders", ok, detail)
        # the plain fields still render after the new branches
        panel.field_sel.set(values[0])
        try:
            panel._draw_field()
            ok, detail = True, ''
        except Exception as exc:
            ok, detail = False, f'{type(exc).__name__}: {exc}'
        check(f"{label}: '{values[0]}' still renders", ok, detail)

    print("\nVTK export button state")
    check('VTK button disabled for a native result',
          panel._export_btns['vtk'].cget('state') == 'disabled',
          str(panel._export_btns['vtk'].cget('state')))
    foam = fake_2d()
    foam.meta['solver'] = 'blastfoam'
    foam.meta['case_dir'] = os.getcwd()
    panel.add_result('foam', 2, foam)
    check('VTK button enabled for a foam result with an existing case dir',
          panel._export_btns['vtk'].cget('state') == 'normal',
          str(panel._export_btns['vtk'].cget('state')))

    print("\nhidden without the maps (older loaded runs)")
    for label, dim, res, new in (('2D old', 2, fake_2d(False), NEW_2D),
                                 ('3D old', 3, fake_3d(False), NEW_3D)):
        panel.add_result(label, dim, res)
        values = list(panel.field_sel.cget('values'))
        check(f'{label}: new fields hidden',
              not any(f in values for f in new), str(values))

    print("\nPNG export figures")
    r2, r3 = fake_2d(), fake_3d()
    names2 = [n for n, _f in plots.figures_fields_2d(r2.snapshots, r2.meta,
                                                     include_peak=True)]
    check('2D export adds peak + impulse figures',
          names2[-2:] == ['blast_2d_peak_overpressure.png',
                          'blast_2d_impulse.png'], str(names2))
    names3 = [n for n, _f in plots.figures_fields_3d(r3.snapshots, r3.meta,
                                                     include_peak=True)]
    check('3D export adds 4 peak/impulse slice figures',
          names3[-4:] == ['blast_3d_peak_overpressure_vertical.png',
                          'blast_3d_impulse_vertical.png',
                          'blast_3d_peak_overpressure_horizontal.png',
                          'blast_3d_impulse_horizontal.png'], str(names3))
    check('default (CLI) figure set unchanged',
          len(plots.figures_fields_2d(r2.snapshots, r2.meta)) == 2
          and len(plots.figures_fields_3d(r3.snapshots, r3.meta)) == 4)
    old2 = fake_2d(False)
    check('no maps -> no extra figures even when asked',
          len(plots.figures_fields_2d(old2.snapshots, old2.meta,
                                      include_peak=True)) == 2)
    pk = dict(plots.peak_items(r2.meta))
    check('peak shown as overpressure in kPa',
          np.allclose(pk['peak overpressure'], 6.0), str(pk['peak overpressure'].ravel()[:2]))

    qa_s2_checks(panel)
    root.destroy()


def qa_s2_checks(panel):
    """QA S2 fixes: duplicate result labels are numbered so every entry
    stays reachable, Remove frees one, and a result with no replay frames
    blanks the animation canvas instead of leaving the previous result's
    frame on screen. Plus the stricter numeric field parsing."""
    import tkinter as tk
    from blastlab.gui import forms

    print("\nQA S2: results management")
    r2 = fake_2d()
    panel.add_result('dup', 2, r2)
    panel.add_result('dup', 2, r2)
    vals = list(panel.sel.cget('values'))
    check('a repeated label is numbered, not shadowed',
          vals.count('dup') == 1 and 'dup #2' in vals, str(vals))
    panel.sel.set('dup #2')
    ent = panel._current()
    check('the numbered entry is selectable',
          ent is not None and ent.label == 'dup #2')
    n = len(panel._entries)
    panel._remove_current()
    check('Remove drops it from the picker and the entry list',
          len(panel._entries) == n - 1
          and 'dup #2' not in list(panel.sel.cget('values')))

    print("\nQA S2: animation placeholder")
    # a result whose meta carries no frames must not keep the previous
    # result's replay picture (the 1D / post-mortem case)
    panel.add_result('noframes', 2, fake_2d())
    panel.sel.set('noframes')
    panel._refresh()
    check('no frames -> Play disabled',
          str(panel.play_btn.cget('state')) == 'disabled')
    check('no frames -> replay canvas carries an explanation',
          any('No recorded frames' in t.get_text()
              for ax in panel.anim_canvas.figure.axes for t in ax.texts))

    print("\nQA S2: numeric field parsing")
    var = tk.StringVar()
    for bad in ('nan', 'inf', '1e400'):
        var.set(bad)
        try:
            forms._f(var, 'charge')
            check(f'_f refuses {bad!r}', False)
        except ValueError as exc:
            check(f'_f refuses {bad!r}', 'finite' in str(exc))
    var.set('1.5')
    check('_f still accepts a normal float', forms._f(var, 'x') == 1.5)
    var.set('2.7')
    try:
        forms._i(var, 'snapshots')
        check('_i refuses a fractional count', False)
    except ValueError as exc:
        check('_i refuses a fractional count', 'whole number' in str(exc))
    for good, want in (('6', 6), ('6.0', 6), ('0', 0)):
        var.set(good)
        check(f'_i accepts {good!r}', forms._i(var, 'n') == want)

    print("\nQA S3: export gating + multi-error parsing + list feedback")
    r2 = fake_2d()
    panel.add_result('gating', 2, r2)
    panel.sel.set('gating')
    panel._refresh()
    st = {k: str(b.cget('state')) for k, b in panel._export_btns.items()}
    check('planar 2D -> Profile export disabled (it always failed)',
          st['profile'] == 'disabled', str(st))
    check('native run -> VTK disabled, PNGs enabled',
          st['vtk'] == 'disabled' and st['pngs'] == 'normal', str(st))
    panel.sel.set('')
    panel._clear_views()
    st = {k: str(b.cget('state')) for k, b in panel._export_btns.items()}
    check('nothing selected -> every export disabled (was a silent no-op)',
          set(st.values()) == {'disabled'}, str(st))

    form = forms.CaseForm(panel.winfo_toplevel(), 2)
    form.v['Lx'].set('abc')
    form.v['cell'].set('')
    form.v['cfl'].set('zzz')
    try:
        form.get_case()
        check('every bad field is reported at once', False)
    except ValueError as exc:
        lines = [ln for ln in str(exc).splitlines() if ln.strip()]
        check('every bad field is reported at once', len(lines) == 3,
              str(lines))
    check('the offending fields are marked',
          form._bad == {'Lx', 'cell', 'cfl'}, str(form._bad))
    form.v['Lx'].set('10')
    form.v['cell'].set('0.025')
    form.v['cfl'].set('0.4')
    form.get_case()
    check('marks clear once the fields parse', form._bad == set())

    form.gauges.entry_var.set('a b')
    form.gauges._add()
    check('a rejected list row explains itself',
          'not numbers' in form.gauges._hint.cget('text'))
    form.gauges.entry_var.set('1 2')
    form.gauges._add()
    check('a good row is accepted and clears the hint',
          len(form.gauges.get()) == 1
          and form.gauges._hint.cget('text') == '')
    form.destroy()

    print("\nQA S4: polish")
    from blastlab.gui.run_panel import RunPanel
    rp = RunPanel(panel.winfo_toplevel(), on_run=lambda: None,
                  on_stop=lambda: None)
    rp.on_log('  2D Blast Solver')
    for i in range(40):
        rp.on_log(f'  [blastfoam] AMR t = {i * 0.01:.3f} ms: '
                  f'{1000 + i:,} cells (+1), L0 {1000 + i:,}')
    rp.on_log('  Done. 400 steps')
    lines = rp.log.get('1.0', 'end').rstrip('\n').splitlines()
    check('40 AMR write lines collapse into one live line',
          len(lines) == 3, f'{len(lines)} lines')
    check('the collapsed line keeps the newest write and a count',
          '0.390 ms' in lines[1] and '40 AMR writes' in lines[1],
          lines[1] if len(lines) > 1 else '')
    check('a non-AMR line after them is not swallowed',
          lines[-1].strip() == 'Done. 400 steps')
    rp.destroy()

    # peak maps: the charge cells used to swallow the whole colour range
    # a charge is a tiny fraction of the domain (here 4 of 6400 cells)
    n = 80
    peak = np.linspace(1.0, 40.0, n * n).reshape(n, n)
    peak[39:41, 39:41] = 5e4                   # the charge, 3 decades up
    faces = np.linspace(0, 1, n + 1)
    solid = np.zeros((n, n), bool)
    args = (solid, faces, faces, 'x', 'y', 'peak', plots.PEAK_LABEL, 1.0)
    fig = plots._panel_grid_figure([('whole run', peak)], *args, robust=True)
    vmax = fig.axes[0].collections[0].get_clim()[1]
    check('robust peak scale clips the charge spike',
          vmax < 1e3, f'vmax={vmax}')
    plain = plots._panel_grid_figure([('whole run', peak)], *args)
    check('without robust the full range is kept',
          plain.axes[0].collections[0].get_clim()[1] >= 5e4)

    t29_checks(panel)
    t30_checks(panel)
    t32_checks(panel)


def t30_checks(panel):
    """T30 / N9 / QA-24: a run can be named, the name reaches the label
    and the suggested export file names, and a long label stays
    reachable in the 250 px picker."""
    print("")
    print("T30: named runs + picker ellipsis")
    from blastlab.gui.run_panel import RunPanel
    from blastlab.gui.results_panel import ResultsPanel, PICKER_MAX
    root = panel.winfo_toplevel()
    rp = RunPanel(root, on_run=lambda: None, on_stop=lambda: None,
                  on_init=lambda: None, on_refresh=lambda: None)
    rp.run_name.set('  urban street  ')
    check('the Run tab hands back a trimmed run name',
          rp.current_run_name() == 'urban street')
    rp.set_run_name('from_file')
    check('Open case never overwrites a name the user typed',
          rp.current_run_name() == 'urban street')
    rp.run_name.set('')
    rp.set_run_name('kitchen_case')
    check('Open case pre-fills the name from the file stem',
          rp.current_run_name() == 'kitchen_case')
    rp.destroy()

    named = fake_2d()
    named.meta['name'] = 'urban street'
    check('export file names carry the run name',
          ResultsPanel._name_prefix(named) == 'urban_street_',
          ResultsPanel._name_prefix(named))
    check('an unnamed run keeps the old export names',
          ResultsPanel._name_prefix(fake_2d()) == '')

    long_label = 'a really long run name that will not fit the picker - 2D'
    panel.add_result(long_label, 2, named)
    ent = panel._entries[-1]
    check('a long label is elided in the picker, tail kept',
          '…' in ent.display and len(ent.display) <= PICKER_MAX
          and ent.display.endswith('- 2D'), ent.display)
    check('the picker still resolves the ellipsised entry',
          panel._current() is ent)
    check('the full label is one hover away',
          panel.sel._blastlab_tip.text == long_label)
    panel._remove_current()


def t32_checks(panel):
    """T32 / G9 / G13: affordance in both modes, accelerators, and UI
    state that survives a restart."""
    print("")
    print("T32: affordance, accelerators, persistence")
    import tkinter as tk
    import customtkinter as ctk
    from blastlab.gui import theme
    from blastlab.gui import settings as gui_settings
    from blastlab.gui.app import App
    from blastlab.gui.run_panel import RunPanel
    from blastlab.gui import forms as gforms
    root = panel.winfo_toplevel()

    plain = ctk.CTkButton(root, text='x', state='disabled')
    check('a plain CTkButton keeps legible disabled text',
          list(plain.cget('text_color_disabled'))
          == [theme.LIGHT['muted'], theme.DARK['muted']],
          str(plain.cget('text_color_disabled')))
    seg = ctk.CTkSegmentedButton(root, values=['a', 'b'])
    check('unselected segments are visible in both modes',
          list(seg.cget('unselected_color'))
          == [theme.LIGHT['seg'], theme.DARK['seg']],
          str(seg.cget('unselected_color')))

    rp = RunPanel(root, on_run=lambda: None, on_stop=lambda: None,
                  on_init=lambda: None, on_refresh=lambda: None)
    idle = rp.stop_btn.cget('fg_color')
    rp.set_running(True)
    live = rp.stop_btn.cget('fg_color')
    rp.set_running(False)
    check('Stop is danger-red only while a run is live',
          list(live) == list(theme.c('danger'))
          and list(idle) == list(theme.c('card2'))
          and list(rp.stop_btn.cget('fg_color')) == list(idle),
          f'{idle} -> {live}')
    rp.destroy()

    # a real focus change needs a mapped window: synthesised <FocusIn>
    # events never reach the inner tk Entry CTkEntry binds on
    was_hidden = not root.winfo_ismapped()
    root.deiconify()
    ent = gforms._entry(root, tk.StringVar())
    ent.pack()
    sink = ctk.CTkFrame(root)
    sink.pack()
    for _ in range(3):
        root.update()
    getattr(ent, '_entry', ent).focus_force()
    for _ in range(3):
        root.update()
    focused = ent.cget('border_color')
    sink.focus_force()
    for _ in range(3):
        root.update()
    check('an entry shows a focus ring',
          list(focused) == list(theme.c('accent'))
          and list(ent.cget('border_color')) == list(theme.c('border')),
          f'{focused} -> {ent.cget("border_color")}')
    ent.destroy()
    sink.destroy()
    if was_hidden:
        root.withdraw()

    stub = App.__new__(App)
    stub._open_case = lambda *a: None
    stub._save_case = lambda *a: None
    stub._run_single = lambda *a: None
    stub._stop = lambda *a: None
    stub._bind_accelerators(root)
    for seq in ('<Control-o>', '<Control-s>', '<F5>', '<Escape>'):
        check(f'{seq} is bound', bool(root.bind_all(seq)))

    import tempfile, shutil
    tmp = tempfile.mkdtemp(prefix='blastlab_settings_')
    cfg = os.path.join(tmp, 'settings.json')
    try:
        for key in ('geometry', 'appearance', 'refresh_value',
                    'refresh_mode'):
            check(f'{key} has a persisted default',
                  key in gui_settings.DEFAULTS)
        gui_settings.save(dict(gui_settings.DEFAULTS,
                               geometry='1400x900+10+10',
                               appearance='light', refresh_value='7',
                               refresh_mode='steps'), cfg)
        back = gui_settings.load(cfg)
        check('UI state round-trips through settings.json',
              (back['geometry'], back['appearance'], back['refresh_value'],
               back['refresh_mode'])
              == ('1400x900+10+10', 'light', '7', 'steps'), str(back))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t29_checks(panel):
    """T29: the Run tab gates its start buttons on validation, a greyed
    export says why it is greyed, and Open case explains a bad file."""
    print("")
    print("T29: run gating, export reasons, open-case messages")
    from blastlab.gui.run_panel import RunPanel
    root = panel.winfo_toplevel()
    rp = RunPanel(root, on_run=lambda: None, on_stop=lambda: None,
                  on_init=lambda: None, on_refresh=lambda: None)
    rp.set_validation(False, 3)
    check('errors gate Run and Initialise',
          str(rp.run_btn.cget('state')) == 'disabled'
          and str(rp.init_btn.cget('state')) == 'disabled')
    check('the Run tab says how many errors',
          '3 errors' in rp._valid_lbl.cget('text'),
          rp._valid_lbl.cget('text'))
    rp.set_validation(True)
    check('a clean case re-enables the start buttons',
          str(rp.run_btn.cget('state')) == 'normal'
          and rp._valid_lbl.cget('text') == 'Case OK')
    rp.destroy()

    panel.sel.set('gating')          # the planar 2D result from QA S3
    panel._refresh()
    prof = panel._export_btns['profile']
    check('a disabled export explains itself on hover',
          'axisymmetric' in getattr(prof, '_blastlab_tip').text,
          getattr(prof, '_blastlab_tip').text)

    import json, tempfile, os as _os
    from blastlab.gui import app as _app
    seen = []
    real = _app.messagebox.showerror
    _app.messagebox.showerror = lambda title, msg: seen.append((title, msg))
    stub = _app.App.__new__(_app.App)
    stub.setup = type('S', (), dict(set_case=lambda self, c: None))()
    stub._show = lambda *a: None
    tmp = tempfile.mkdtemp(prefix='blastlab_open_')
    try:
        bad = _os.path.join(tmp, 'bad.json')
        with open(bad, 'w', encoding='utf-8') as f:
            f.write('{not json')
        stub._open_case(bad)
        check('garbage JSON reads as a JSON error',
              'not valid JSON' in seen[-1][1], seen[-1][1])
        wrong = _os.path.join(tmp, 'wrong.json')
        with open(wrong, 'w', encoding='utf-8') as f:
            json.dump(dict(dim=5), f)
        stub._open_case(wrong)
        check('a wrong schema reads as a blastlab-case error',
              'case file' in seen[-1][1].lower(), seen[-1][1])
        missing = _os.path.join(tmp, 'nope.json')
        stub._open_case(missing)
        check('a missing file is named as a path, not a repr',
              seen[-1][1] == f'File not found: {missing}', seen[-1][1])
        check('every Open-case dialog is titled',
              all(t == 'Open case' for t, _ in seen[-3:]))
    finally:
        _app.messagebox.showerror = real
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
    print()
    print('GUI RESULTS FIELDS: ' + ('PASS' if not FAILS
                                    else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
