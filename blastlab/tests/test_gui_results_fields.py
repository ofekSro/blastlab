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


if __name__ == '__main__':
    main()
    print()
    print('GUI RESULTS FIELDS: ' + ('PASS' if not FAILS
                                    else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
