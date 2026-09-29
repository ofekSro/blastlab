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


def main():
    s1_strip()
    pump(20)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI SETUP STRIP: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
