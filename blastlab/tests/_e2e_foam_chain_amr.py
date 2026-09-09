"""Manual e2e (WSL): a profile-initialised blastFoam stage with dynamic
AMR (T70, N7 + N16).

Until T70 a chain stage fed by a profile was refused if it also asked
for AMR. It need not be: under AMR the mesh at t0 IS the uniform base
grid blockMesh builds, which is exactly the mesh the remapped state is
written on - only `profile_state` was remapping onto the DISPLAY grid,
which is 2**(dim*D) times bigger.

What this proves, and cannot be proved by reading:
  * the case starts at all (no "size N is not equal to M" abort), which
    also means adaptiveFvMesh is happy starting WITHOUT a cellLevel
    field - a profile stage skips setRefinedFields entirely, so nothing
    writes one;
  * the run-time refiner then refines the profile's own shock: the last
    written mesh has cells above level 0 and more cells than it started
    with;
  * the gauges see a real wave, and the run reloads through
    postmortem.load_run (whose t0-vs-0 assumption T70 also fixed).

One 2D solve on a 25 x 50 base mesh - a couple of minutes.

Run:  cd blastlab/tests && python _e2e_foam_chain_amr.py
"""
import os
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core.case import Case1D, Case2D, validate_case      # noqa: E402
from blastlab.core.constants import P_AIR                         # noqa: E402
from blastlab.core import profiles                                # noqa: E402
from blastlab.solvers import get_solver                           # noqa: E402
from blastlab.solvers.foam import env, postmortem                 # noqa: E402
from blastlab.solvers.hooks import RunHooks                       # noqa: E402

ALL_TERM = dict(x_lo='terminate', x_hi='terminate',
                y_lo='terminate', y_hi='terminate')
GAUGES = [(0.3, 0.5), (0.4, 0.5)]
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       '_chain_study')

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAILS.append(name)


class Hooks(RunHooks):
    def __init__(self):
        super().__init__()
        self.lines = []

    def log(self, s):
        self.lines.append(s)
        print(s)


def arrival(times, p, thresh=0.05):
    ovp = np.asarray(p) - P_AIR
    idx = np.nonzero(ovp > thresh * P_AIR)[0]
    return float(times[idx[0]]) if len(idx) else float('nan')


def main():
    if env.status()[0] == 'fail':
        print('SKIP: no WSL blastFoam')
        return 0
    os.makedirs(OUT_DIR, exist_ok=True)
    prof = os.path.join(OUT_DIR, 'stage1_amr.txt')

    # stage 1: native 1D, stopped at 0.2 m - inside the 2D gauges, so
    # the 2D stage really continues a state rather than replaying an
    # answer. Its dx is far finer than the 2D base cell below, which is
    # what the T70 coarsening warning is about.
    c1 = Case1D(radius_m=0.2, charge_kg=0.2, cell_size_m=0.002,
                gauge_radii=[0.15], n_snapshots=1, solver='native')
    t0 = time.perf_counter()
    r1 = get_solver(1, 'native')(c1)
    profiles.save_profile(r1.meta['final_profile'], prof)
    fp = r1.meta['final_profile']
    print(f'  --- stage 1 (native 1D): {time.perf_counter() - t0:.0f} s, '
          f"front at {fp['r'][-1]:.2f} m, t = {fp['t'] * 1e3:.4f} ms")

    # stage 2: the same hand-off the chain panel wires, plus AMR
    case = Case2D(geometry='axisymmetric', Lx=0.5, Ly=1.0,
                  cell_size_m=0.02, center=(0.0, 0.5), gauges=list(GAUGES),
                  n_snapshots=1, eos='idealGas', solver='blastfoam',
                  material='TNT', init_mode='profile1d',
                  profile_file_in=prof, amr_levels=2, bcs=ALL_TERM)
    rep = validate_case(case)
    check('profile + AMR validates', not rep.errors, str(rep.errors))
    check('...and says where the state lands',
          any('base mesh and the AMR refines' in n for n in rep.notes),
          str(rep.notes))
    if rep.errors:
        return 1

    hooks = Hooks()
    t0 = time.perf_counter()
    res = get_solver(2, 'blastfoam')(case, hooks)
    wall = time.perf_counter() - t0
    print(f'  --- stage 2 (foam 2D axisym + AMR): {wall:.0f} s, '
          f'{res.stop_reason}')

    log = '\n'.join(hooks.lines)
    check('banner names the profile, not a charge',
          'Initialised from: stage1_amr.txt' in log
          and 'Charge          :' not in log, log[:400])
    check('banner says the state is written on the base mesh',
          'written on the 0.02 m base mesh' in log)
    check('banner warns the base cell coarsens the hand-off',
          'coarsens it' in log and 'lower the base cell size' in log,
          next((l for l in hooks.lines if '[warn]' in l), '(no warn line)'))

    ref = res.meta.get('refine') or {}
    counts = list(ref.get('counts') or [])
    n_base = case.Lx / 0.02 * case.Ly / 0.02
    check('the mesh refined below the base grid',
          len(counts) > 1 and sum(counts[1:]) > 0, str(counts))
    check('...and ended with more cells than it started with',
          ref.get('n_cells', 0) > n_base,
          f"{ref.get('n_cells')} vs {n_base:.0f} base cells")

    p = list(res.snapshots.values())[-1]['p']
    g = res.gauges
    peaks = [float(np.max(pr)) - P_AIR for pr in g['pressures']]
    arr = [arrival(g['times'], pr) for pr in g['pressures']]
    print(f'  gauge peaks [kPa]: {[round(v / 1e3) for v in peaks]}, '
          f'arrivals [ms]: {[round(a * 1e3, 4) for a in arr]}')
    check('the field is finite and above ambient',
          np.all(np.isfinite(p)) and float(p.max()) > 1.01 * P_AIR,
          f'max {float(p.max()) / 1e3:.0f} kPa')
    check('both gauges see the wave, the near one first',
          all(v > 0 for v in peaks) and np.isfinite(arr).all()
          and arr[0] < arr[1], f'{peaks} {arr}')

    pm = postmortem.load_run(res.meta['case_dir'])
    pp = list(pm.snapshots.values())[-1]['p']
    check('post-mortem reload finds the t0 mesh and the same field',
          pp.shape == p.shape and np.allclose(pp, p)
          and (pm.meta.get('refine') or {}).get('amr') == 2,
          f'{pp.shape} vs {p.shape}')

    left = subprocess.run(
        env.wsl_plain_argv('pgrep -a -f "[b]lastFoam" 2>/dev/null; true'),
        capture_output=True, text=True, timeout=60,
        stdin=subprocess.DEVNULL,
        creationflags=env.CREATE_NO_WINDOW).stdout.strip()
    check('no solver process left behind in WSL', not left, left)
    print(f"  case dir: {res.meta['case_dir']}")

    print()
    if FAILS:
        print(f'CHAIN AMR: FAIL ({len(FAILS)}): ' + ', '.join(FAILS))
        return 1
    print('CHAIN AMR: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
