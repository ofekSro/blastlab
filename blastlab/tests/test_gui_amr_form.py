"""Dynamic AMR in the GUI (ROADMAP N16, T22) - headless Tk, no WSL.

The "Dynamic refinement (AMR)" card round-trips every amr_* case
field, is hidden for the native solver mode (T34: hidden, not greyed;
the values stay in the form), and hides the static charge 'zone' row
while AMR is on; the validation cell line reports the AMR
levels; the run-panel live overlay and the Results replay / animation
export follow the per-frame level maps an AMR run records;
plots.mesh_for(levels=) draws one frame's mesh.

Run:  cd blastlab/tests && python test_gui_amr_form.py
"""
import os
import sys
import tempfile

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                              # noqa: E402

from blastlab.core import refine                                # noqa: E402
from blastlab.core.case import Case2D, Case3D, validate_case    # noqa: E402
from blastlab.core.grid import make_geometry                    # noqa: E402
from blastlab.output import plots                               # noqa: E402
from blastlab.solvers.hooks import Result                       # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def n_linecolls(ax):
    from matplotlib.collections import LineCollection
    return sum(isinstance(c, LineCollection) for c in ax.collections)


def fake_amr_2d(n_frames=3):
    """A planar 2D AMR Result: 2 x 2 m, base 0.5 m, display level 2
    (8 x 8 at 0.25 m), a different level map per frame."""
    g = make_geometry('planar', 2.0, 2.0, 0.25)
    shape = (8, 8)
    levels = []
    for k in range(n_frames):
        lv = np.zeros(shape, dtype=np.int8)
        lv[:4 + 2 * k, :4] = 1            # a growing level-1 band
        lv[4:6, 4:6] = 2 if k else 0      # level-2 patch from frame 1
        levels.append(lv)
    pressures = [np.full(shape, 1e5 + 1e3 * k, dtype=np.float32)
                 for k in range(n_frames)]
    meta = dict(x_c=g['x_c'], y_c=g['y_c'], x_face=g['x_face'],
                y_face=g['y_face'], solid=np.zeros(shape, dtype=bool),
                geometry='planar', Lx=2.0, Ly=2.0, dx=0.25, eos='JWL',
                bcs={}, obstacles=[], charge=10.0, charge_center=(1.0, 1.0),
                r_exp=0.05, from_profile=False, solver='blastfoam',
                material='TNT', case_dir='',
                refine=dict(levels=levels[-1], lmax=2, dx_base=0.5, zones=[],
                            amr=2, display_level=2, n_cells=40,
                            counts=(1, 2, 4)),
                frames=dict(times=np.linspace(0, 1e-3, n_frames),
                            pressures=pressures, levels=levels))
    gauges = dict(times=np.array([]), points=[], pressures=[])
    return Result({}, gauges, meta, 'end time reached', False), g


def main():
    import customtkinter as ctk
    from blastlab.gui.forms import CaseForm
    from blastlab.gui.results_panel import ResultsPanel
    from blastlab.gui.run_panel import RunPanel

    root = ctk.CTk()
    root.withdraw()

    print("\nCaseForm: AMR card round trip + enable rules")
    form = CaseForm(root, 2)
    # 320 kg/m: r_exp = 0.25 m, so 3 AMR levels still reach the 8 cells
    # across the radius blastFoam asks for (T39) - this case exercises
    # the form round trip, not the level rule
    c = Case2D(geometry='planar', Lx=4.0, Ly=4.0, cell_size_m=0.2,
               charge=320.0, center=(2.0, 2.0), solver='blastfoam',
               amr_levels=3, amr_estimator='Lohner', amr_refine=0.2,
               amr_unrefine=0.05, amr_interval=3, amr_buffer=1,
               amr_max_cells=500000, amr_display_level=2)
    form.set_case(c)
    root.update()
    got = form.get_case()
    check('every amr_* field round-trips',
          (got.amr_levels, got.amr_estimator, got.amr_refine, got.amr_unrefine,
           got.amr_interval, got.amr_buffer, got.amr_max_cells,
           got.amr_display_level)
          == (3, 'Lohner', 0.2, 0.05, 3, 1, 500000, 2)
          and isinstance(got.amr_levels, int) and isinstance(got.amr_display_level, int),
          str((got.amr_levels, got.amr_estimator, got.amr_refine, got.amr_unrefine,
               got.amr_interval, got.amr_buffer, got.amr_max_cells,
               got.amr_display_level)))
    check('the AMR case validates through the form',
          not validate_case(got).errors, str(validate_case(got).errors))
    check('AMR on: coefficient rows shown, charge-refinement row hidden',
          all(w.winfo_manager() == 'grid' for w in form._amr_entries)
          and form._amr_est_combo.winfo_manager() == 'grid'
          and form._cref_combo.winfo_manager() == '',
          f"{[w.winfo_manager() for w in form._amr_entries]} "
          f"{form._cref_combo.winfo_manager()!r}")
    c.amr_display_level = None
    form.set_case(c)
    root.update()
    check("display level None <-> 'auto'",
          form.v['amr_display_level'].get() == 'auto'
          and form.get_case().amr_display_level is None)
    form.v['charge_refine'].set('zone')
    root.update()
    check("AMR on: a 'zone' charge mode stays in the form but the case "
          "says 'global'",
          form.v['charge_refine'].get() == 'zone'
          and form.get_case().charge_refine == 'global',
          f"{form.v['charge_refine'].get()} {form.get_case().charge_refine}")
    form.v['amr_levels'].set('0')
    root.update()
    check('AMR off: coefficient rows hidden, charge-refinement row back '
          "with its 'zone' value",
          all(w.winfo_manager() == '' for w in form._amr_entries)
          and form._amr_disp_combo.winfo_manager() == ''
          and form._cref_combo.winfo_manager() == 'grid'
          and form.get_case().amr_levels == 0
          and form.get_case().charge_refine == 'zone')
    form.v['amr_levels'].set('2')
    form.set_mode('native')
    root.update()
    check('native mode: AMR card hidden, level kept in the form, case '
          'says 0',
          form.v['amr_levels'].get() == '2'
          and form._amr_card.winfo_manager() == ''
          and form.get_case().amr_levels == 0
          and form.get_case().solver == 'native',
          f"{form.v['amr_levels'].get()} {form._amr_card.winfo_manager()!r}")
    form.set_mode('blastfoam')
    root.update()
    check('back to blastFoam: the AMR card and its level return',
          form._amr_card.winfo_manager() == 'grid'
          and form.get_case().amr_levels == 2)
    form3 = CaseForm(root, 3)
    c3 = Case3D(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.1, charge=8.0,
                center=(1.0, 1.0, 1.0), solver='blastfoam', amr_levels=3,
                amr_display_level=1)
    form3.set_case(c3)
    root.update()
    g3 = form3.get_case()
    check('3D form round trip', g3.amr_levels == 3 and g3.amr_display_level == 1
          and g3.amr_estimator == 'densityGradient')
    plain = form3.get_case()
    plain.amr_levels = 0
    form3.set_case(plain)
    check('AMR switched off in a form round-trips as a static case',
          form3.get_case().amr_levels == 0
          and not validate_case(form3.get_case()).errors)

    print("\nplots.mesh_for(levels=)")
    res, g = fake_amr_2d()
    meta = res.meta
    xf, yf = g['x_face'], g['y_face']
    lv = meta['frames']['levels'][2]
    want = len(refine.mesh_segments_2d(refine.fine_src(lv, 2), xf, yf,
                                       max_lines=plots.MESH_MAX_LINES))
    segs = plots.mesh_for(meta, xf, yf, levels=lv)
    check('per-frame levels -> that frame\'s cell edges', len(segs) == want,
          f'{len(segs)} vs {want}')
    lv0 = meta['frames']['levels'][0]
    check('different frames give different overlays',
          len(plots.mesh_for(meta, xf, yf, levels=lv0)) != len(segs))
    check("without levels the final map (meta['refine']) is used",
          len(plots.mesh_for(meta, xf, yf)) == want)
    lvc = lv.copy()
    lvc[0:4, 0:4] = -1
    check('carved cells (-1) are left out',
          len(plots.mesh_for(meta, xf, yf, levels=lvc)) < want)

    print("\nplots.mesh_for on a REAL-SIZE AMR display grid")
    # the shape a 20 x 20 m axisym run at 0.5 m base with amr_levels=4
    # produces: a 640^2 display grid = 409,600 cells. That is just over
    # the old 400,000 guard, which REPLACED the overlay with a uniform
    # base grid - the AMR mesh vanished from the exported video and the
    # Results fields while the live pane still showed it.
    big = 640
    bxf = np.linspace(0.0, 20.0, big + 1)
    byf = np.linspace(0.0, 20.0, big + 1)
    jj, ii = np.meshgrid(np.arange(big), np.arange(big), indexing='ij')
    rad = np.hypot(ii, jj - big / 2)

    def band_map(bands):
        m = np.zeros((big, big), dtype=np.int8)
        for lvl, lo, hi in bands:
            m[(rad > lo) & (rad < hi)] = lvl
        return m

    big_lv = band_map(((1, 150, 300), (2, 185, 275),
                       (3, 205, 255), (4, 220, 243)))
    big_meta = dict(refine=dict(levels=big_lv, lmax=4, dx_base=0.5,
                                zones=[], amr=4, display_level=4))
    n_uni = len(plots.mesh_for(dict(refine=None), bxf, byf))
    n_amr = len(plots.mesh_for(big_meta, bxf, byf, levels=big_lv))
    check('a 640^2 AMR frame keeps its refinement (not a uniform grid)',
          n_amr > 10 * n_uni, f'{n_amr} segments vs {n_uni} uniform')
    check('the same holds without per-frame levels (Results fields)',
          len(plots.mesh_for(big_meta, bxf, byf)) == n_amr)
    shifted = band_map(((1, 190, 340), (2, 225, 315),
                        (3, 245, 295), (4, 260, 283)))
    check('and it still moves with the shock',
          len(plots.mesh_for(big_meta, bxf, byf, levels=shifted)) != n_amr)

    # far above the cap the map is COARSENED, never discarded
    huge = 2048
    hxf = np.linspace(0.0, 20.0, huge + 1)
    hyf = np.linspace(0.0, 20.0, huge + 1)
    huge_lv = np.zeros((huge, huge), dtype=np.int8)
    huge_lv[900:1150, 900:1150] = 3
    huge_meta = dict(refine=dict(levels=huge_lv, lmax=3, dx_base=0.5,
                                 zones=[], amr=3, display_level=3))
    n_huge = len(plots.mesh_for(huge_meta, hxf, hyf, levels=huge_lv))
    check('above the cap the level map is coarsened, not dropped',
          n_huge > len(plots.mesh_for(dict(refine=None), hxf, hyf)),
          str(n_huge))
    lv_fit, xf_fit, yf_fit, lmax_fit = plots._fit_overlay(
        huge_lv, hxf, hyf, 3)
    check('coarsening halves the map, the faces and the depth together',
          lv_fit.size <= plots.MESH_MAX_CELLS
          and len(xf_fit) == lv_fit.shape[0] + 1
          and len(yf_fit) == lv_fit.shape[1] + 1
          and lmax_fit < 3 and lv_fit.max() == 3,
          f'{lv_fit.shape} {lmax_fit}')

    print("\nRunPanel: live overlay follows the frame levels")
    rp = RunPanel(root, on_run=lambda *a: None, on_stop=lambda *a: None)
    info = dict(dim=2, x_face=xf, y_face=yf, solid=np.zeros((8, 8), bool),
                xlabel='x', ylabel='y', title='', mesh_src=None,
                display_level=2)
    rp.on_run_started(info)
    rp.show_mesh_var.set(True)
    rp._rebuild_overlay()
    n_uniform = len(rp._mesh_lines.get_segments())
    rp.on_frame(np.full((8, 8), 1e5, dtype=np.float32), 1e-4, levels=lv)
    check('frame with levels rebuilds the overlay from them',
          rp._mesh_lines is not None and len(rp._mesh_lines.get_segments()) == want
          and want != n_uniform,
          f'{len(rp._mesh_lines.get_segments())} vs {want} (uniform {n_uniform})')
    rp.on_frame(np.full((8, 8), 1e5, dtype=np.float32), 2e-4)
    check('a frame without levels keeps the last overlay',
          len(rp._mesh_lines.get_segments()) == want)
    rp.show_mesh_var.set(False)
    rp._rebuild_overlay()
    check('overlay removed', rp._mesh_lines is None)

    print("\nResultsPanel replay: per-frame overlay")
    panel = ResultsPanel(root)
    panel.add_result('AMR 2D', 2, res)
    panel.show_mesh_var.set(True)
    panel._setup_anim()
    panel._show_frame(0)
    ax = panel._anim_mesh.axes
    n0 = len(panel._anim_lines.get_segments()) if panel._anim_lines is not None else -1
    panel._show_frame(2)
    n2 = len(panel._anim_lines.get_segments()) if panel._anim_lines is not None else -1
    check('replay overlay exists and changes between frames',
          n0 > 0 and n2 == want and n0 != n2 and n_linecolls(ax) == 1,
          f'{n0} {n2} {n_linecolls(ax)}')
    panel.show_mesh_var.set(False)
    panel._setup_anim()
    panel._show_frame(2)
    check('overlay off: no line collection', n_linecolls(panel._anim_mesh.axes) == 0)

    print("\nanimation export with per-frame overlay")
    from blastlab.output.animation import write_animation
    out = os.path.join(tempfile.mkdtemp(prefix='blastlab_amr_anim_'), 'amr.gif')
    try:
        write_animation(meta, out, fps=5, show_mesh=True)
        ok = os.path.isfile(out) and os.path.getsize(out) > 0
        detail = str(os.path.getsize(out) if os.path.isfile(out) else 'missing')
    except Exception as exc:                          # noqa: BLE001
        ok, detail = False, f'{type(exc).__name__}: {exc}'
    check('write_animation(show_mesh=True) on an AMR record', ok, detail)

    root.destroy()
    print()
    print('GUI AMR FORM: ' + ('PASS' if not FAILS else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
