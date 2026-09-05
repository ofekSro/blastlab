"""Manual e2e (WSL): a planar 2D blastFoam run with local refinement.

A 20 kg/m charge on an 8 cm base in 'zone' mode (automatic nested zones
to level 3, finest 1 cm) plus user zones - level 1 (4 cm) over the path
to the gauge and level 2 (2 cm) around it - versus the same case refined
globally (today's rule, uniform 1.25 cm). The far corners stay at 8 cm. Checks the mesh stages ran, the refined mesh
matched core.refine's prediction, fields come back on the fine display
grid with coarse cells as constant blocks, live frames arrived, the
meta['refine'] record is present, and the gauge agrees with the uniform
reference within blast-engineering tolerances.

Run:  cd blastlab/tests && python _e2e_foam_refine2d.py   (~5 min, WSL)
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core import refine                                # noqa: E402
from blastlab.core.case import Case2D, validate_case            # noqa: E402
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
        self.lines, self.frames = [], 0

    def log(self, s):
        self.lines.append(s)
        print(s)

    def frame(self, payload, t):
        self.frames += 1


def arrival(times, p, thresh=0.05):
    ovp = p - P_AIR
    idx = np.argmax(ovp > thresh * P_AIR)
    return times[idx]


def run(case, label):
    rep = validate_case(case)
    check(f'{label}: validates', rep.ok, '; '.join(rep.errors))
    h = Hooks()
    t0 = time.perf_counter()
    res = get_solver(2, 'blastfoam')(case, h)
    print(f'  --- {label}: {time.perf_counter() - t0:.0f} s, {h.frames} live frames')
    return res, h


def main():
    # y extent 3.2 m: the nearest open boundary (x_hi, 1.2 m) is farther
    # than the gauge (0.8 m), so the arrival stop comes after the gauge peak
    base = dict(geometry='planar', Lx=2.4, Ly=3.2, cell_size_m=0.08,
                charge=20.0, center=(1.2, 1.6), gauges=[(2.0, 1.6)],
                n_snapshots=2, solver='blastfoam', material='TNT')
    refined = Case2D(charge_refine='zone',
                     refine_zones=[(0.9, 2.4, 1.2, 2.0, 1),
                                   (1.7, 2.3, 1.4, 1.8, 2)], **base)
    plan = refine.plan_levels(refined, rho0=1630.0)
    print(f'plan: lmax {plan.lmax}, finest {plan.dx_fine:.4g} m, '
          f'{plan.n_pred:,} predicted cells, display {plan.fine["Nx"]}x{plan.fine["Ny"]}')
    check('plan: level 3 auto zones + user zones validate', plan.lmax == 3
          and refine.validate_zones(refined, plan)[0] == [],
          f'{plan.lmax} {refine.validate_zones(refined, plan)[0]}')

    res, h = run(refined, 'refined')
    check('mesh stages: refine passes logged',
          sum('refining level' in l for l in h.lines) >= 2 * plan.lmax)
    check('mesh matched the prediction',
          any('matched the predicted structure' in l for l in h.lines))
    m = res.meta
    check("meta['refine'] present with lmax 3",
          m.get('refine') is not None and m['refine']['lmax'] == 3)
    check('display grid is the fine grid',
          len(m['x_face']) - 1 == plan.fine['Nx'] and abs(m['dx'] - plan.dx_fine) < 1e-12,
          f"{len(m['x_face']) - 1} {m['dx']}")
    snap = list(res.snapshots.values())[-1]
    p = snap['p']
    # level-0 corner: 8x8 fine blocks are one foam cell -> exactly constant
    blk = p[:8, :8]
    check('coarse corner cell is one constant 8x8 block', blk.std() == 0.0, str(blk.std()))
    # inside the finest zone every fine cell is its own cell: not all equal
    src = refine.slice_src(m['refine']['levels'], 3)
    cx, cy = np.searchsorted(m['x_face'], 1.2) - 1, np.searchsorted(m['y_face'], 1.6) - 1
    fine_ids = src[cx - 4:cx + 4, cy - 4:cy + 4]
    check('finest zone: 64 distinct cells in an 8x8 patch', len(np.unique(fine_ids)) == 64)
    check('live frames arrived', h.frames >= 3, str(h.frames))
    check('peak/impulse maps present on the fine grid',
          m.get('p_peak') is not None and m['p_peak'].shape == p.shape)
    check('stopped via arrival', res.stop_reason.startswith('shock arrived'), res.stop_reason)
    check('graceful stop honoured (no kill)',
          not any('did not stop cleanly' in l for l in h.lines))
    check("no spurious '0' dir stall message",
          not any('time dir 0 ' in l for l in h.lines))

    ref_case = Case2D(charge_refine='global', **base)
    ref, _ = run(ref_case, 'uniform reference')
    g_r, g_u = res.gauges, ref.gauges
    check('both runs recorded the gauge',
          len(g_r['pressures']) == 1 and len(g_u['pressures']) == 1)
    if g_r['pressures'] and g_u['pressures']:
        pk_r = g_r['pressures'][0].max() - P_AIR
        pk_u = g_u['pressures'][0].max() - P_AIR
        ta_r = arrival(g_r['times'], g_r['pressures'][0])
        ta_u = arrival(g_u['times'], g_u['pressures'][0])
        check('gauge peak within 15% of the uniform reference',
              abs(pk_r - pk_u) / pk_u < 0.15,
              f'refined {pk_r/1e3:.0f} kPa, uniform {pk_u/1e3:.0f} kPa')
        check('gauge arrival within 10% of the uniform reference',
              abs(ta_r - ta_u) / ta_u < 0.10,
              f'refined {ta_r*1e3:.3f} ms, uniform {ta_u*1e3:.3f} ms')
    # post-mortem reload rebuilds the remap from the kept 0/C
    from blastlab.solvers.foam import postmortem
    pm = postmortem.load_run(m['case_dir'])
    pp = list(pm.snapshots.values())[-1]['p']
    check('post-mortem reload: same fine grid, refine record and final field',
          pm.meta.get('refine') is not None and pm.meta['refine']['lmax'] == 3
          and pp.shape == p.shape and np.allclose(pp, p),
          f"{pp.shape} vs {p.shape}")
    print(f"  refined case dir: {m['case_dir']}")
    return m['case_dir']


if __name__ == '__main__':
    main()
    print()
    print('E2E FOAM REFINE 2D: ' + ('PASS' if not FAILS else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
