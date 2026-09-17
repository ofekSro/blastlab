"""GUI side of local refinement + "show mesh" (T17): headless checks.

- CaseForm round-trips refine_zones (int level) and charge_refine, and
  disables/resets the charge-refinement combo for the native solver;
- Preview2DPanel draws zone rectangles and, with show_mesh, a
  LineCollection of the predicted cell edges (uniform and refined);
- SetupPanel's "Show mesh" checkbox re-renders the last case;
- RunPanel overlays cell edges on the live plot with/without mesh_src;
- ResultsPanel's checkbox renders every field with the overlay, for a
  uniform result and for one carrying meta['refine'];
- plots.figures_fields_2d/3d(show_mesh=True) keep the figure set and add
  the overlay; write_animation accepts show_mesh;
- the case's own `anim_mesh` flag round-trips through the form and
  the case file, and reaches write_animation on the run path.
Headless (Agg backend, hidden Tk root) - needs customtkinter, no WSL.

Run:  cd blastlab/tests && python test_gui_refine_preview.py
"""
import os
import sys

import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from matplotlib.collections import LineCollection                # noqa: E402

from blastlab.core import refine                                # noqa: E402
from blastlab.core.case import Case2D, Case3D                   # noqa: E402
from blastlab.output import plots                               # noqa: E402
from test_gui_results_fields import fake_2d, fake_3d            # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def n_linecolls(ax):
    return sum(isinstance(c, LineCollection) for c in ax.collections)


def refined_2d():
    """fake_2d() + a consistent meta['refine'] (2x2 base -> 4x4 fine)."""
    res = fake_2d()
    m = res.meta
    # rebuild the geometry on a 1 x 0.8 domain at base 0.5 -> fine 0.25
    from blastlab.core.grid import make_geometry
    g = make_geometry('planar', 1.0, 0.8, 0.25)
    nx, ny = g['Nx'], g['Ny']
    p = np.full((nx, ny), 1.0e5) + 1e3
    for s in res.snapshots.values():
        s['p'] = p
        s['rho'] = np.full_like(p, 1.2)
        s['speed'] = np.zeros_like(p)
    m.update(x_c=g['x_c'], y_c=g['y_c'], x_face=g['x_face'],
             y_face=g['y_face'], solid=np.zeros((nx, ny), dtype=bool),
             dx=0.25, p_peak=p + 5e3, impulse=np.full_like(p, 1.0))
    levels = np.zeros((nx, ny), dtype=np.int8)
    levels[:2, :2] = 1                       # the (0..0.5)^2 base cell
    m['refine'] = dict(levels=levels, lmax=1, dx_base=0.5,
                       zones=[(0.0, 0.5, 0.0, 0.5, 1)])
    return res


def refined_3d():
    res = fake_3d()
    m = res.meta
    nx, ny, nz = m['solid'].shape
    levels = np.zeros((nx, ny, nz), dtype=np.int8)
    levels[:2, :2, :2] = 1
    m['refine'] = dict(levels=levels, lmax=1, dx_base=0.4,
                       zones=[(0.0, 0.4, 0.0, 0.4, 0.0, 0.4, 1)])
    return res


def main():
    import customtkinter as ctk
    from blastlab.gui.forms import CaseForm, SetupPanel
    from blastlab.gui.preview_panel import Preview2DPanel, case_geometry
    from blastlab.gui.results_panel import ResultsPanel
    from blastlab.gui.run_panel import RunPanel

    root = ctk.CTk()
    root.withdraw()

    print("\nCaseForm round trip")
    form = CaseForm(root, 3)
    c3 = Case3D(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.5, charge=1.0,
                center=(1.0, 1.0, 1.0), solver='blastfoam')
    c3.refine_zones = [(0.5, 1.5, 0.5, 1.5, 0.5, 1.5, 1),
                       (0.75, 1.25, 0.75, 1.25, 0.75, 1.25, 2)]
    c3.charge_refine = 'zone'
    form.set_case(c3)
    got = form.get_case()
    check('refine_zones round-trip with int levels',
          got.refine_zones == c3.refine_zones
          and all(isinstance(z[-1], int) for z in got.refine_zones),
          str(got.refine_zones))
    check("charge_refine round-trip ('zone')", got.charge_refine == 'zone')
    check('charge-refinement row shown for blastfoam',
          form._cref_combo.winfo_manager() == 'grid',
          repr(form._cref_combo.winfo_manager()))
    form.set_mode('native')
    root.update()
    got_n = form.get_case()
    check("native mode keeps 'zone' in the form, hides the row and the "
          "zones card, and strips both from the case",
          form.v['charge_refine'].get() == 'zone'
          and form._cref_combo.winfo_manager() == ''
          and form._zones_card.winfo_manager() == ''
          and got_n.charge_refine == 'global' and got_n.refine_zones == []
          and got_n.solver == 'native',
          f"{form.v['charge_refine'].get()} {form._cref_combo.winfo_manager()!r} "
          f"{got_n.charge_refine} {got_n.refine_zones}")
    form.set_mode('blastfoam')
    root.update()
    check('back to blastfoam: the zones return',
          form.get_case().refine_zones == c3.refine_zones
          and form._zones_card.winfo_manager() == 'grid')
    form2 = CaseForm(root, 2)
    c2 = Case2D(geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.5,
                charge=1.0, center=(1.0, 1.0), solver='blastfoam')
    c2.refine_zones = [(0.5, 1.5, 0.5, 1.5, 1)]
    form2.set_case(c2)
    check('2D form round-trip', form2.get_case().refine_zones == c2.refine_zones,
          str(form2.get_case().refine_zones))

    print("\nPreview2DPanel")
    pv = Preview2DPanel(root)
    c2.charge = None
    c2.refine_zones = [(0.5, 1.5, 0.5, 1.5, 1), (0.75, 1.25, 0.75, 1.25, 2)]
    pv.show_case(c2, show_mesh=False)
    ax = pv._ax
    from matplotlib.patches import Rectangle
    rects = [p for p in ax.patches if isinstance(p, Rectangle)]
    check('zone rectangles drawn (2 zones, dashed)', len(rects) == 2
          and all(r.get_linestyle() != 'solid' for r in rects), str(len(rects)))
    check('no mesh lines without the checkbox', n_linecolls(ax) == 0)
    pv.show_case(c2, show_mesh=True)
    ax = pv._ax
    lcs = [c for c in ax.collections if isinstance(c, LineCollection)]
    plan = refine.plan_levels(c2)
    want = len(refine.mesh_segments_2d(
        refine.slice_src(plan.levels, plan.lmax), plan.fine['x_face'],
        plan.fine['y_face']))
    check('show_mesh draws the predicted edges (one LineCollection)',
          len(lcs) == 1 and len(lcs[0].get_segments()) == want,
          f'{len(lcs)} colls, {len(lcs[0].get_segments()) if lcs else 0} vs {want}')
    check('title reports the predicted cell count',
          f'{plan.n_pred:,} cells' in ax.get_title(), ax.get_title())
    c2.refine_zones = []
    pv.show_case(c2, show_mesh=True)
    lcs = [c for c in pv._ax.collections if isinstance(c, LineCollection)]
    check('uniform case: every base face drawn (4x4 -> 10 segments)',
          len(lcs) == 1 and len(lcs[0].get_segments()) == 10,
          str(len(lcs[0].get_segments()) if lcs else 0))

    # N2-07: the preview must plan with the MATERIAL's rho0. It used to
    # call plan_levels bare (TNT default), so on ANFO it drew one whole
    # extra refinement level than validate_case reported and the writer
    # built - and this file's only plan_levels call was ALSO bare, so
    # the test reproduced the bug instead of catching it. TNT is the one
    # material with no gap, which is why every TNT-only check passed.
    print("\nN2-07: preview plans with the material's rho0")
    from blastlab.gui.preview_panel import _plan
    from blastlab.core.case import material_rho0
    ca = Case2D(geometry='planar', Lx=4.0, Ly=3.0, cell_size_m=0.08,
                charge=20.0, center=(1.5, 1.6), solver='blastfoam',
                material='ANFO', charge_refine='zone',
                refine_zones=[(0.9, 2.4, 1.2, 2.0, 1),
                              (1.7, 2.3, 1.4, 1.8, 2)])
    pv_plan = _plan(ca)
    true_plan = refine.plan_levels(ca, rho0=material_rho0(ca))
    tnt_plan = refine.plan_levels(ca)        # the old, wrong default
    check('ANFO: preview plan matches the validated plan',
          pv_plan is not None
          and (pv_plan.lmax, pv_plan.n_pred, pv_plan.dx_fine)
          == (true_plan.lmax, true_plan.n_pred, true_plan.dx_fine),
          f'preview {pv_plan and (pv_plan.lmax, pv_plan.n_pred)} vs '
          f'validated {(true_plan.lmax, true_plan.n_pred)}')
    check('ANFO: and that differs from the bare-TNT plan it used to draw',
          (true_plan.lmax, true_plan.n_pred)
          != (tnt_plan.lmax, tnt_plan.n_pred),
          f'both {(tnt_plan.lmax, tnt_plan.n_pred)}')
    # native case with zones: preview still draws (validation reports the error)
    c2.solver = 'native'
    c2.refine_zones = [(0.5, 1.5, 0.5, 1.5, 1)]
    try:
        pv.show_case(c2, show_mesh=True)
        check('preview tolerates a native case with zones', True)
    except Exception as exc:
        check('preview tolerates a native case with zones', False, str(exc))

    print("\ncase_geometry (3D preview data)")
    c3.charge = None
    c3.charge_refine = 'global'
    c3.solver = 'blastfoam'
    geo = case_geometry(c3, show_mesh=True)
    check('zones exported for the 3D scene', len(geo.get('zones', [])) == 2
          and all(len(z) == 7 for z in geo['zones']), str(geo.get('zones')))
    mp = geo.get('mesh')
    check('mesh data carries the domain axes + the live-slice plane',
          mp is not None and len(mp['axes']) == 3 and mp['dx'] > 0
          and mp['planes'] and mp['planes'][0][0] == 1,
          str(mp and (mp['dx'], mp['planes'])))
    from blastlab.viz3d.viewer import mesh_polydata
    poly = mesh_polydata(mp['axes'], mp['dx'], mp.get('refine'), mp['planes'])
    check('mesh polydata spans the whole domain',
          poly is not None and poly.points[:, 0].max() > 1.9,
          str(None if poly is None else poly.points[:, 0].max()))
    check('no mesh without show_mesh',
          'mesh' not in case_geometry(c3, show_mesh=False))

    print("\nSetupPanel checkbox")
    sp = SetupPanel(root)
    c2.solver = 'blastfoam'
    sp.update_preview(c2)
    check('update_preview remembers the case', sp._last_case is c2)
    sp.show_mesh_var.set(True)
    sp._mesh_toggled()
    check('toggle re-renders with mesh',
          n_linecolls(sp.preview2d._ax) == 1)
    sp.show_mesh_var.set(False)
    sp._mesh_toggled()
    check('toggle off removes it', n_linecolls(sp.preview2d._ax) == 0)

    print("\nRunPanel live overlay")
    rp = RunPanel(root, on_run=lambda *a: None, on_stop=lambda *a: None)
    xf, yf = np.linspace(0, 1, 5), np.linspace(0, 1, 5)
    info = dict(dim=2, x_face=xf, y_face=yf, solid=np.zeros((4, 4), bool),
                xlabel='x', ylabel='y', title='')
    rp.on_run_started(info)
    check('no overlay by default', rp._mesh_lines is None)
    rp.show_mesh_var.set(True)
    rp._rebuild_overlay()
    check('uniform overlay: 10 face lines',
          rp._mesh_lines is not None and len(rp._mesh_lines.get_segments()) == 10,
          str(rp._mesh_lines and len(rp._mesh_lines.get_segments())))
    src = np.array([[0, 0, 4, 5], [0, 0, 6, 7], [1, 2, 8, 9], [1, 2, 10, 11]])
    info['mesh_src'] = src
    rp.on_run_started(info)
    want = len(refine.mesh_segments_2d(src, xf, yf))
    check('refined overlay uses mesh_src (checkbox still on)',
          rp._mesh_lines is not None
          and len(rp._mesh_lines.get_segments()) == want,
          str(rp._mesh_lines and len(rp._mesh_lines.get_segments())))
    rp.show_mesh_var.set(False)
    rp._rebuild_overlay()
    check('overlay removed', rp._mesh_lines is None)
    rp.on_frame(np.full((4, 4), 1.1e5), 1e-4)
    rp.on_run_started(dict(dim=1, radius_m=1.0))
    rp.show_mesh_var.set(True)
    rp._rebuild_overlay()
    check('1D run ignores the checkbox', rp._mesh_lines is None)

    print("\nResultsPanel checkbox")
    panel = ResultsPanel(root)
    for label, dim, res in (('2D uniform', 2, fake_2d()),
                            ('2D refined', 2, refined_2d()),
                            ('3D uniform', 3, fake_3d()),
                            ('3D refined', 3, refined_3d())):
        panel.add_result(label, dim, res)
        panel.show_mesh_var.set(True)
        values = list(panel.field_sel.cget('values'))
        bad = []
        for f in values:
            try:
                panel.field_sel.set(f)
                panel._draw_field()
                fig = panel.field_canvas._fig if hasattr(
                    panel.field_canvas, '_fig') else None
            except Exception as exc:
                bad.append(f'{f}: {type(exc).__name__}: {exc}')
        check(f'{label}: every field renders with the mesh overlay',
              not bad, '; '.join(bad))
        try:
            panel._mesh_toggled()
            ok = True
        except Exception as exc:
            ok, bad = False, str(exc)
        check(f'{label}: _mesh_toggled (field + replay) ok', ok, str(bad))
        panel.show_mesh_var.set(False)

    print("\nplots / animation")
    r2, r3 = refined_2d(), refined_3d()
    figs2 = plots.figures_fields_2d(r2.snapshots, r2.meta, include_peak=True,
                                    show_mesh=True)
    check('2D export: figure set unchanged with show_mesh', len(figs2) == 4)
    check('2D export: each panel carries a LineCollection',
          all(n_linecolls(ax) >= 1 for _n, f in figs2 for ax in f.axes
              if ax.get_label() != '<colorbar>' and ax.collections))
    figs3 = plots.figures_fields_3d(r3.snapshots, r3.meta, include_peak=True,
                                    show_mesh=True)
    check('3D export: figure set unchanged with show_mesh', len(figs3) == 8)
    segs = plots.mesh_for(r2.meta, r2.meta['x_face'], r2.meta['y_face'])
    want = len(refine.mesh_segments_2d(
        refine.slice_src(r2.meta['refine']['levels'], 1),
        r2.meta['x_face'], r2.meta['y_face']))
    check('mesh_for uses the refine record', len(segs) == want,
          f'{len(segs)} vs {want}')
    uni = plots.mesh_for(fake_2d().meta, r2.meta['x_face'], r2.meta['y_face'])
    check('mesh_for without refine: every face',
          len(uni) == len(r2.meta['x_face']) + len(r2.meta['y_face']))
    m3 = plots.mesh_for(r3.meta, r3.meta['x_face'], r3.meta['z_face'],
                        np.s_[:, r3.meta['j0'], :])
    check('mesh_for 3D slice', m3.ndim == 3 and len(m3) > 0)
    from blastlab.output.animation import write_animation
    import tempfile
    r2.meta['frames'] = dict(times=np.array([0.0, 1e-4]),
                             pressures=[s['p'].astype(np.float32)
                                        for s in r2.snapshots.values()])
    out = os.path.join(tempfile.mkdtemp(prefix='blastlab_anim_'), 'a.gif')
    try:
        write_animation(r2.meta, out, show_mesh=True)
        check('write_animation(show_mesh=True) writes', os.path.getsize(out) > 0)
    except Exception as exc:
        check('write_animation(show_mesh=True) writes', False, str(exc))

    print("\nanim_mesh (the run's own animation)")
    from blastlab.core.case import case_from_dict, case_to_dict
    check('default off',
          Case2D().anim_mesh is False and Case3D().anim_mesh is False)
    form3 = CaseForm(root, 2)
    form3.set_case(Case2D(anim_file='a.gif', anim_mesh=True))
    check('anim_mesh round-trips through the form',
          form3.get_case().anim_mesh is True)
    form3.v['anim_mesh'].set(False)
    check('unchecking it clears the case flag',
          form3.get_case().anim_mesh is False)
    check('anim_mesh round-trips through a case file',
          case_from_dict(case_to_dict(Case2D(anim_mesh=True))).anim_mesh
          is True)

    # the flag reaches write_animation on the GUI run path (the stage
    # builder moved to solvers/jobs.py, shared by both front-ends)
    import blastlab.solvers as solvers_mod
    import blastlab.solvers.jobs as app_mod

    class _Res:
        gauges = None
        meta = {'frames': dict(times=[0.0], pressures=[0.0])}

    seen = {}
    real_solver, real_write = solvers_mod.get_solver, app_mod.write_animation
    solvers_mod.get_solver = lambda dim, backend: (lambda case, hooks: _Res())
    app_mod.write_animation = lambda meta, fn, **kw: seen.update(kw)
    try:
        for dim, flag in ((2, True), (3, False)):
            cls = Case2D if dim == 2 else Case3D
            seen.clear()
            app_mod.solve_stage(dim, cls(anim_file='a.gif',
                                         anim_mesh=flag))[1](None)
            check(f'{dim}D run export passes show_mesh={flag}',
                  seen.get('show_mesh') is flag, str(seen))
    finally:
        solvers_mod.get_solver, app_mod.write_animation = (real_solver,
                                                           real_write)

    root.destroy()


if __name__ == '__main__':
    main()
    print()
    print('GUI REFINE PREVIEW: ' + ('PASS' if not FAILS
                                    else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
