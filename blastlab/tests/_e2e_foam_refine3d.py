"""Manual e2e (WSL): 3D blastFoam runs with local refinement.

An 8 kg charge in a 1 m cube on a 10 cm base in 'zone' mode (automatic
nested zones to level 3, finest 1.25 cm) with one obstacle box in a
corner - serial, then with 2 MPI ranks (decomposePar after the cell
centres are written; reconstructPar restores serial order). Checks the
mesh matched the prediction, carved cells read back as ambient, live
slice frames and 3D frames arrived, the FO peak maps are on the fine
grid, the meta['refine'] record exists and both runs agree.

Run:  cd blastlab/tests && python _e2e_foam_refine3d.py   (~5-8 min, WSL)
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core import refine                                # noqa: E402
from blastlab.core.case import Case3D, validate_case            # noqa: E402
from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.solvers import get_solver                         # noqa: E402
from blastlab.solvers.hooks import RunHooks                     # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f' - {detail}' if detail else ''))
    if not ok:
        FAILS.append(name)


class Hooks(RunHooks):
    def __init__(self):
        super().__init__()
        self.lines, self.frames, self.frames3d = [], 0, 0

    def log(self, s):
        self.lines.append(s)
        print(s)

    def frame(self, payload, t):
        self.frames += 1

    def wants_frame3d(self):
        return True

    def frame3d(self, t, fields, force=False):
        self.frames3d += 1


def run(case, label):
    rep = validate_case(case)
    check(f'{label}: validates', rep.ok, '; '.join(rep.errors))
    h = Hooks()
    t0 = time.perf_counter()
    res = get_solver(3, 'blastfoam')(case, h)
    print(f'  --- {label}: {time.perf_counter() - t0:.0f} s, {h.frames} live / '
          f'{h.frames3d} 3D frames')
    return res, h


def main():
    base = dict(Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.1, charge=8.0,
                center=(0.5, 0.5, 0.5), charge_refine='zone',
                obstacles=[(0.0, 0.2, 0.0, 0.2, 0.0, 0.2)],
                # gauge inside the finest zone (a coarse-region gauge next to
                # the open boundary is still rising when the arrival stop lands)
                gauges=[(0.65, 0.5, 0.5)], n_snapshots=2, record_frames=20,
                solver='blastfoam', material='TNT')
    case = Case3D(**base)
    plan = refine.plan_levels(case, rho0=1630.0)
    print(f'plan: lmax {plan.lmax}, finest {plan.dx_fine:.4g} m, '
          f'{plan.n_pred:,} predicted cells, display {plan.fine["Nx"]}^3')
    check('plan: level 3 auto zones', plan.lmax == 3, str(plan.lmax))

    res, h = run(case, 'serial')
    m = res.meta
    check('mesh matched the prediction',
          any('matched the predicted structure' in l for l in h.lines))
    check("meta['refine'] with lmax 3",
          m.get('refine') is not None and m['refine']['lmax'] == 3)
    fin = list(res.snapshots.values())[-1]
    p = fin['p']
    check('final p on the fine display grid', p.shape == (80, 80, 80), str(p.shape))
    check('carved cells read back as ambient',
          np.allclose(p[m['solid']], P_AIR) and m['solid'].sum() == 8 * 8 ** 3,
          f"{m['solid'].sum()}")
    check('coarse corner (far from the charge) is one constant 8^3 block',
          p[72:, 72:, 72:].std() == 0.0, str(p[72:, 72:, 72:].std()))
    check('live slice frames + 3D frames arrived', h.frames >= 2 and h.frames3d >= 1,
          f'{h.frames} {h.frames3d}')
    check('peak maps on the fine grid, FO source',
          m['p_peak'].shape == p.shape and m.get('peak_source') == 'foam-fo',
          str(m.get('peak_source')))
    check('stopped via arrival', res.stop_reason.startswith('shock arrived'), res.stop_reason)
    check('recorded frames are slices of the fine grid',
          m['frames']['pressures'][0].shape == (80, 80))

    par = Case3D(n_procs=2, **base)
    res2, h2 = run(par, 'np=2')
    m2 = res2.meta
    check('np=2: mesh matched (centres written before decomposePar)',
          any('matched the predicted structure' in l for l in h2.lines))
    check('np=2: decomposed after the cell centres',
          [l for l in h2.lines if 'writing cell centres' in l or 'decomposing' in l][:2]
          and h2.lines.index(next(l for l in h2.lines if 'writing cell centres' in l))
          < h2.lines.index(next(l for l in h2.lines if 'decomposing' in l)))
    p2 = list(res2.snapshots.values())[-1]['p']
    check('np=2: same display grid and stop', p2.shape == p.shape
          and res2.stop_reason.startswith('shock arrived'))
    g1, g2 = res.gauges['pressures'][0], res2.gauges['pressures'][0]
    check('np=2: gauge peak within 10% of serial',
          abs(g2.max() - g1.max()) / (g1.max() - P_AIR) < 0.10,
          f'{(g1.max()-P_AIR)/1e3:.0f} vs {(g2.max()-P_AIR)/1e3:.0f} kPa')
    print(f"  serial case dir: {m['case_dir']}\n  np=2 case dir: {m2['case_dir']}")
    return m['case_dir']


if __name__ == '__main__':
    main()
    print()
    print('E2E FOAM REFINE 3D: ' + ('PASS' if not FAILS else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
