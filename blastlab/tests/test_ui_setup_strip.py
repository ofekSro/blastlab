"""GUI-5b: the Setup centre - live-number strip, model-view overlays and
the dock Gauges · Checks · Log (plan §5.3, board BC_Combined).

S1 - the strip: every tile's text equals the validation report's own
field, formatted HERE from the report (plan §10: "strip numbers equal the
validation report's numbers for the same case - asserted, not
eyeballed"); tiles hide, never grey, when their number is not available;
Run F5 / Initialise reach the MainWindow's own actions.

Headless: offscreen Qt, throwaway settings, no solver run.
Run:  cd blastlab/tests && python test_ui_setup_strip.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_ss_'),
                                   'settings.json'))

from blastlab.ui.testing import ensure_qapp, pump          # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

app = ensure_qapp()

from blastlab.core.case import (Case1D, Case2D, Case3D,     # noqa: E402
                                validate_case)
from blastlab.core.constants import BYTES_PER_CELL          # noqa: E402
from blastlab.solvers.foam import env                       # noqa: E402
from blastlab.ui import scaled_distance as sd               # noqa: E402
from blastlab.ui import setup_spec                          # noqa: E402

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def sample_case(**kw):
    """The boards' sample case (plan §1): 2D axisymmetric, blastFoam,
    1 kg TNT at z = 2 m, 4 x 4 m, cell 0.025 m, Wall 1 at r 3.0-3.2 m,
    gauges G1 (2.95, 0.50) and G2 (2.95, 1.50)."""
    args = dict(solver='blastfoam', geometry='axisymmetric', Lx=4.0,
                Ly=4.0, cell_size_m=0.025, charge=1.0, center=(0.0, 2.0),
                bcs=dict(setup_spec.BC_DEFAULTS[2]),
                obstacles=[(3.0, 3.2, 0.0, 2.5)],
                gauges=[(2.95, 0.5), (2.95, 1.5)])
    args.update(kw)
    return Case2D(**args)


def panel():
    from blastlab.core import mode as mode_mod
    from blastlab.ui.setup_panel import SetupPanel
    sp = SetupPanel(mode=mode_mod.SolverMode())
    sp.resize(1600, 960)
    sp.show()
    pump(60)
    return sp


def load(sp, case):
    """set_case, then the app's _validate path: refresh with the parsed
    case and ITS report. Returns (parsed case, report)."""
    sp.set_case(case)
    got = sp.get_case()
    rep = validate_case(got)
    sp.show_report(rep.errors, rep.warnings, rep.notes)
    sp.refresh(got, rep)
    pump(30)
    return got, rep


def s1_strip():
    s = None
    print('\nS1a: the sample case (2D axisym, blastFoam) - tile == report')
    env.forget_hardware()
    sp = panel()
    s = sp.strip
    case, rep = load(sp, sample_case())
    plan = rep.run_plan
    check('the report has what the strip reads',
          rep.r_exp and rep.n_cells and rep.effective_dx and plan is not None,
          f'{rep.r_exp} {rep.n_cells} {rep.effective_dx} {plan}')
    check('Charge: the mass as entered, radius = the report r_exp',
          s.shown('charge') == (f'{case.charge:.1f} kg {case.material}',
                                f'radius {rep.r_exp * 1e3:.1f} mm'),
          str(s.shown('charge')))
    check('Charge radius is the Derived card\'s own text',
          s.shown('charge')[1] == 'radius ' + sp.derived().value('radius'))
    check('Cells: rep.n_cells (368 k) and the cell rep.effective_dx',
          s.shown('cells') == (f'{rep.n_cells / 1e3:.0f} k',
                               f'cell {rep.effective_dx * 1e3:.3g} mm')
          and s.shown('cells')[0] == '368 k',
          str(s.shown('cells')))
    check('Cells tooltip carries the exact count',
          f'{rep.n_cells:,} cells' in s.tiles['cells'].toolTip(),
          s.tiles['cells'].toolTip())
    check('MPI ranks: rep.run_plan.ranks, auto, cells per rank',
          s.shown('ranks') == (str(plan.ranks),
                               f'auto · {rep.n_cells // plan.ranks / 1e3:.0f}'
                               f' k cells each'),
          str(s.shown('ranks')))
    check('MPI tooltip is the plan\'s own reason',
          plan.reason in s.tiles['ranks'].toolTip())
    gb = rep.n_cells * BYTES_PER_CELL / 2 ** 30
    check('Memory: rep.n_cells x BYTES_PER_CELL in GB (2^30)',
          s.shown('memory') == (f'{gb:.1f} GB',
                                'VM size not measured yet'),
          str(s.shown('memory')))
    check('no VM size: no bar', s.tile('memory').frac is None
          and not s.tiles['memory'].bar.isVisibleTo(s))
    zs = [z for _n, _r, z in sd.gauges(case)]
    check('Z at gauges: min-max of the Z helper (2.99-3.31)',
          s.shown('z') == (f'{min(zs):.2f}–{max(zs):.2f}', 'm/kg^1/3')
          and s.shown('z')[0] == '2.99–3.31', str(s.shown('z')))
    check('the Z tile is the accent variant',
          s.tiles['z'].property('variant') == 'accent')

    print('\nS1b: a measured VM - the memory bar is over run_plan.ram_gb')
    env.prime_hardware(cores=20, ram_gb=62)
    case, rep = load(sp, sample_case())
    plan = rep.run_plan
    b = rep.n_cells * BYTES_PER_CELL
    check('run_plan now carries the VM size',
          plan.ram_gb == 62, str(plan.ram_gb))
    check('Memory caption: of <ram_gb> GB VM',
          s.shown('memory')[1] == f'of {plan.ram_gb} GB VM',
          str(s.shown('memory')))
    check('bar fraction = bytes / (ram_gb x 2^30)',
          abs(s.tiles['memory'].bar.frac() - b / (plan.ram_gb * 2 ** 30))
          < 1e-12 and s.tiles['memory'].bar.isVisibleTo(s),
          f'{s.tiles["memory"].bar.frac()}')
    check('MPI ranks follow the new plan',
          s.shown('ranks')[0] == str(plan.ranks), str(s.shown('ranks')))
    case, rep = load(sp, sample_case(n_procs=64))
    plan = rep.run_plan
    check('an explicit request past the machine reads "clamped from 64"',
          plan.clamped and s.shown('ranks')[1].startswith(
              f'clamped from {plan.clamped_from} · ')
          and s.shown('ranks')[0] == str(plan.ranks),
          str(s.shown('ranks')))
    case, rep = load(sp, sample_case(n_procs=2))
    check('an explicit request that fits reads "requested"',
          s.shown('ranks')[1].startswith('requested · ')
          and s.shown('ranks')[0] == str(rep.run_plan.ranks),
          str(s.shown('ranks')))
    env.forget_hardware()

    print('\nS1c: what each case hides (hide, never grey)')
    case, rep = load(sp, sample_case(solver='native'))
    check('native: no run plan -> MPI and Memory hidden',
          rep.run_plan is None and s.shown('ranks') is None
          and s.shown('memory') is None)
    check('native: Charge, Cells, Z still read off the report',
          s.shown('cells')[0] == f'{rep.n_cells / 1e3:.0f} k'
          and s.shown('charge')[1] == f'radius {rep.r_exp * 1e3:.1f} mm'
          and s.shown('z') is not None, str(s.shown('cells')))
    case, rep = load(sp, sample_case(geometry='planar',
                                     center=(1.0, 2.0)))
    check('planar: Z hidden, the charge is per metre',
          s.shown('z') is None and s.shown('charge')[0] == '1.0 kg/m TNT',
          str(s.shown('charge')))
    case, rep = load(sp, sample_case(init_mode='profile1d',
                                     profile_file_in='x.txt'))
    check('profile start: no Charge tile, no Z',
          s.shown('charge') is None and s.shown('z') is None)
    case, rep = load(sp, sample_case(gauges=[]))
    check('no gauges: no Z tile', s.shown('z') is None)
    case, rep = load(sp, sample_case(amr_levels=2))
    check('AMR: finest cell rep.dx_fine, counted at t = 0',
          rep.dx_fine and s.shown('cells')[1]
          == f'finest {rep.dx_fine * 1e3:.3g} mm · at t = 0'
          and s.shown('memory')[1].endswith('· at t = 0'),
          f'{s.shown("cells")} {s.shown("memory")}')
    c1 = Case1D(solver='blastfoam', charge_kg=1.0, gauge_radii=[2.0, 3.0])
    case, rep = load(sp, c1)
    check('1D blastFoam: no run plan -> MPI and Memory hidden',
          rep.run_plan is None and s.shown('ranks') is None
          and s.shown('memory') is None)
    check('1D: cells, radius and Z 2.00-3.00 from the report / helper',
          s.shown('cells')[0] == f'{rep.n_cells / 1e3:.0f} k'
          and s.shown('charge') == ('1.0 kg TNT',
                                    f'radius {rep.r_exp * 1e3:.1f} mm')
          and s.shown('z')[0] == '2.00–3.00',
          f'{s.shown("cells")} {s.shown("charge")} {s.shown("z")}')
    c3 = Case3D(solver='blastfoam', charge=8.0, center=(1.0, 1.0, 1.0),
                gauges=[(3.0, 1.0, 1.0)])
    case, rep = load(sp, c3)
    check('3D blastFoam: all five tiles, a single Z',
          all(s.shown(n) is not None for n in
              ('charge', 'cells', 'ranks', 'memory', 'z'))
          and s.shown('z')[0] == f'{sd.gauges(case)[0][2]:.2f}'
          and s.shown('ranks')[0] == str(rep.run_plan.ranks),
          str(s.shown('z')))
    from blastlab.models.hd13_case import DeflagrationCase
    sp.set_dim(0)
    check('a dimension switch clears the numbers before its report',
          all(s.shown(n) is None for n in
              ('charge', 'cells', 'ranks', 'memory', 'z')))
    from blastlab.core.assessment import validate as validate_hd13
    d0 = sp.get_case()
    sp.refresh(d0, validate_hd13(d0))
    pump(20)
    check('0-D: no tile at all, Run shown, Initialise hidden',
          isinstance(d0, DeflagrationCase)
          and all(s.shown(n) is None for n in
                  ('charge', 'cells', 'ranks', 'memory', 'z'))
          and s.run_btn.isVisibleTo(s) and not s.init_btn.isVisibleTo(s))

    print('\nS1d: Run is gated like the Run tab, and emits')
    sp.set_dim(2)
    sp.show_report(['e1'])
    check('an error greys Run and Initialise',
          not s.run_btn.isEnabled() and not s.init_btn.isEnabled())
    sp.show_report([], ['w'], ['n'])
    check('warnings and notes do not', s.run_btn.isEnabled()
          and s.init_btn.isEnabled())
    got = []
    sp.run_requested.connect(lambda: got.append('run'))
    sp.init_requested.connect(lambda: got.append('init'))
    s.run_btn.click()
    s.init_btn.click()
    check('Run and Initialise emit the panel signals',
          got == ['run', 'init'], str(got))
    sp.close()

    print('\nS1e: the MainWindow wires them to its own actions')
    from blastlab.ui.app import MainWindow
    win = MainWindow()
    win.resize(1600, 1000)
    win.show()
    pump(150)
    calls = []
    win._run_single = lambda paused=False: calls.append(('run', paused))
    win._init_model = lambda: calls.append(('init',))
    win.setup.set_case(sample_case())
    win._validate()
    pump(60)
    win.setup.strip.run_btn.click()
    win.setup.strip.init_btn.click()
    check('Run F5 -> _run_single, Initialise -> _init_model',
          calls == [('run', False), ('init',)], str(calls))
    s = win.setup.strip
    rep = validate_case(win.setup.get_case())
    check('after the real _validate the tiles hold that report',
          s.shown('cells')[0] == f'{rep.n_cells / 1e3:.0f} k'
          and s.shown('ranks')[0] == str(rep.run_plan.ranks))
    check('1600 px: one row, the board\'s 148 px Run column',
          s.rows() == 1 and s.run_col.width() == 148,
          f'{s.rows()} rows, run {s.run_col.width()}')
    win.resize(1100, 720)
    pump(150)
    check('1100 x 720: the strip wraps instead of clipping',
          s.rows() == 2 and s.width() <= win.setup.width()
          and all(t.width() >= t.minimumSizeHint().width()
                  for t in s.tiles.values() if t.isVisible()),
          f'{s.rows()} rows, {s.width()} px')
    check('wrapped: captions move to the tooltips',
          not s.tiles['cells'].caption.isVisible()
          and 'cell ' in s.tiles['cells'].toolTip())
    win.close()
    pump(40)


def _mouse(canvas, ax, name, x, y, button=None):
    """Feed matplotlib a synthetic event at data point (x, y)."""
    from matplotlib.backend_bases import MouseEvent
    px, py = ax.transData.transform((x, y))
    ev = MouseEvent(name, canvas, px, py, button=button)
    canvas.callbacks.process(name, ev)


def _ring_radius(line, centre):
    import numpy as np
    x, y = line.get_data()
    r = np.hypot(np.asarray(x) - centre[0], np.asarray(y) - centre[1])
    return float(r.min()), float(r.max())


def s2_model_view():
    from blastlab.ui import theme
    from blastlab.ui.model_overlay import ModelOverlay
    print('\nS2a: Z rings at Z = 1, 2, 3 (radius Z W^1/3)')
    sp = panel()

    def show(case):
        got, rep = load(sp, case)
        sp.update_preview(got)
        pump(20)
        return got

    case = show(sample_case())
    ax = sp.preview2d.ax
    rings = sorted(ModelOverlay.found(ax, 'zring'),
                   key=lambda a: a.get_gid())
    radii = [_ring_radius(r, (0.0, 2.0)) for r in rings]
    want = [sd.ring_radius(case, z) for z in (1, 2, 3)]
    check('three dashed rings around the burst (0, 2)',
          len(rings) == 3 and all(abs(lo - w) < 1e-9 and abs(hi - w) < 1e-9
                                  for (lo, hi), w in zip(radii, want)),
          str(radii))
    check('1 kg: the rings sit at R = 1.00, 2.00, 3.00 m',
          [round(w, 2) for w in want] == [1.0, 2.0, 3.0], str(want))
    check('labelled Z 1 / Z 2 / Z 3',
          sorted(t.get_text().strip() for t in
                 ModelOverlay.found(ax, 'zlabel'))
          == ['Z 1', 'Z 2', 'Z 3'])
    check('dashed, in the accent colour',
          all(r.get_linestyle() == '--' and r.get_color()
              == theme.cur('accent') for r in rings))
    check('the toolbar: Z rings on by default, Mesh, Fit',
          sp.z_rings.isChecked() and sp.z_rings.isVisibleTo(sp)
          and sp.show_mesh.isVisibleTo(sp) and sp.fit_btn.isVisibleTo(sp))
    check('the plane caption (board line 162)',
          sp.view_caption() == 'r–z plane · charge on the axis',
          sp.view_caption())
    sp.z_rings.setChecked(False)
    pump(5)
    check('Z rings off: no ring', not ModelOverlay.found(ax, 'zring'))
    sp.z_rings.setChecked(True)
    pump(5)
    check('on again: three', len(ModelOverlay.found(ax, 'zring')) == 3)
    n0 = len(ModelOverlay.found(ax))
    for _ in range(3):
        sp.update_preview(sp.get_case())
    theme.apply(app, 'light')
    pump(20)
    theme.apply(app, 'dark')
    pump(20)
    check('replays and theme switches never leak overlay artists',
          len(ModelOverlay.found(ax)) == n0,
          f'{n0} -> {len(ModelOverlay.found(ax))}')
    heavy = show(sample_case(charge=8.0))
    radii = sorted(_ring_radius(r, (0.0, 2.0))[0]
                   for r in ModelOverlay.found(ax, 'zring'))
    check('8 kg doubles them (2, 4, 6 m)',
          [round(r, 6) for r in radii] == [2.0, 4.0, 6.0], str(radii))
    show(sample_case(geometry='planar', center=(1.0, 2.0)))
    check('planar: no ring, and the Z rings button is hidden',
          not ModelOverlay.found(ax, 'zring')
          and not sp.z_rings.isVisibleTo(sp))
    show(sample_case(init_mode='profile1d', profile_file_in='x.txt'))
    check('profile start: no ring', not ModelOverlay.found(ax, 'zring'))
    c1 = show(Case1D(solver='blastfoam', charge_kg=8.0,
                     gauge_radii=[2.0, 3.0]))
    ax1 = sp.preview1d.ax
    radii = sorted(_ring_radius(r, (0.0, 0.0))[1]
                   for r in ModelOverlay.found(ax1, 'zring'))
    check('1D: arcs in the sector at Z W^1/3 (8 kg: 2, 4, 6 m)',
          sp.preview_kind() == '1d'
          and [round(r, 6) for r in radii]
          == [round(sd.ring_radius(c1, z), 6) for z in (1, 2, 3)],
          str(radii))

    print('\nS2b: the selected node is highlighted (chargeHi / gaugeHi)')
    case = show(sample_case())
    sp.select_node('threat')
    pump(10)
    tags = [t.get_text() for t in ModelOverlay.found(ax, 'chargetag')]
    check('01 Threat: two rings and the charge tag',
          len([a for a in ModelOverlay.found(ax, 'charge')
                   if a.get_gid() == 'overlay:charge']) == 2
          and tags == ['Charge · 1 kg TNT'], str(tags))
    check('and no gauge highlight', not ModelOverlay.found(ax, 'halo'))
    sp.select_node('gauges')
    pump(10)
    rl = [t.get_text() for t in sorted(ModelOverlay.found(ax, 'rlabel'),
                                       key=lambda a: a.get_gid())]
    check('05 Gauges: one halo and one dashed line per gauge',
          len(ModelOverlay.found(ax, 'halo')) == 2
          and len(ModelOverlay.found(ax, 'gline')) == 2
          and all(h.get_color() == theme.cur('gauge')
                  for h in ModelOverlay.found(ax, 'halo')))
    check('R labels equal the helper: R 3.31, R 2.99',
          rl == [f'R {r:.2f}' for _n, r, _z in sd.gauges(case)]
          and rl == ['R 3.31', 'R 2.99'], str(rl))
    check('and no charge highlight',
          not ModelOverlay.found(ax, 'chargetag'))
    sp.select_node('domain')
    pump(10)
    check('another node: rings only',
          {a.get_gid().split(':')[1] for a in ModelOverlay.found(ax)}
          == {'zring', 'zlabel'})
    marks = [ln for ln in ax.lines if ln.get_marker() == 'o'
             and not (ln.get_gid() or '')]
    check('the preview draws the gauges in gauge cyan (plan §2.1)',
          marks and all(ln.get_color() == theme.cur('gauge')
                        for ln in marks), str([m.get_color()
                                              for m in marks]))

    print('\nS2c: the hover readout r · z · R · Z')
    canvas = sp.preview2d.figure.canvas
    _mouse(canvas, ax, 'motion_notify_event', 2.95, 0.5)
    check("over G1: 'r 2.95 · z 0.50 · R 3.31 · Z 3.31'",
          sp.view_caption() == 'r 2.95 · z 0.50 · R 3.31 · Z 3.31',
          sp.view_caption())
    from matplotlib.backend_bases import LocationEvent
    canvas.callbacks.process('figure_leave_event',
                             LocationEvent('figure_leave_event', canvas,
                                           0, 0))
    check('leaving the model restores the plane caption',
          sp.view_caption() == 'r–z plane · charge on the axis',
          sp.view_caption())
    show(sample_case(geometry='planar', center=(1.0, 2.0)))
    _mouse(canvas, ax, 'motion_notify_event', 2.0, 2.0)
    check("planar: 'x · y · R', no Z",
          sp.view_caption() == 'x 2.00 · y 2.00 · R 1.00',
          sp.view_caption())
    show(Case1D(solver='blastfoam', charge_kg=1.0, gauge_radii=[2.0]))
    _mouse(sp.preview1d.figure.canvas, sp.preview1d.ax,
           'motion_notify_event', 3.0, 0.0)
    check("1D: 'r · R · Z'",
          sp.view_caption() == 'r 3.00 · R 3.00 · Z 3.00',
          sp.view_caption())

    print('\nS2d: Mesh and Fit')
    show(sample_case())
    check('Mesh is the old show_mesh, now a checkable toolbar button',
          sp.show_mesh.isCheckable() and sp.show_mesh.text() == 'Mesh')
    sp.show_mesh.setChecked(True)
    pump(10)
    check('Mesh on replays the preview with the mesh',
          sp.preview2d._last[1] is True)
    sp.show_mesh.setChecked(False)
    pump(10)
    check('and off without', sp.preview2d._last[1] is False)
    lim = ax.get_xlim()
    _mouse(canvas, ax, 'scroll_event', 2.0, 2.0, button='up')
    zoomed = ax.get_xlim()
    check('a wheel notch zooms about the pointer',
          zoomed[1] - zoomed[0] < lim[1] - lim[0], f'{lim} -> {zoomed}')
    sp.fit_btn.click()
    pump(10)
    check('Fit goes back to the whole domain',
          all(abs(a - b) < 1e-9 for a, b in zip(ax.get_xlim(), lim)),
          f'{ax.get_xlim()} vs {lim}')
    check('Fit keeps the overlay', len(ModelOverlay.found(ax, 'zring'))
          == 3)
    sp.set_case(Case3D(solver='blastfoam', gauges=[(1.0, 1.0, 1.0)]))
    sp.update_preview(sp.get_case())
    pump(10)
    check('3D: no Z rings button (the child viewer is out of scope)',
          not sp.z_rings.isVisibleTo(sp))
    sp.set_dim(0)
    sp.update_preview(sp.get_case())
    pump(10)
    check('0-D: no model-view tool at all',
          not any(b.isVisibleTo(sp) for b in
                  (sp.z_rings, sp.show_mesh, sp.fit_btn))
          and sp.view_caption() == '')
    sp.close()


def main():
    s1_strip()
    s2_model_view()
    pump(20)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI SETUP STRIP: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
