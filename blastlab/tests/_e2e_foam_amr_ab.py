"""Manual e2e (WSL): parallel AMR vs the serial run of the SAME case.

T42 / N16-b acceptance. Serial AMR is bit-deterministic and two parallel
runs agree with each other to 0.02 %, but serial and DECOMPOSED AMR are
two self-consistent, slightly different discretisations: the rank
boundaries change the refinement pattern and the difference feeds back
through the solve. Measured on this case: arrivals agree to 0.3-0.5 %,
point gauge peaks fluctuate 0.15-4 % along the domain, positive-phase
impulse drifts 4-9 % late in the run, and neither `loadBalance
{ balance yes; }` (the load was already balanced to 1.02-1.04) nor
maxCells headroom (the cap never bound) moves any of it.

The acceptance is therefore 1 % ON THE OBSERVABLES WHERE SERIAL-VS-
PARALLEL 1 % EXISTS (owner decision, 2026-09-07):

  * arrival time at every gauge        within 1 %   (measured 0.3-0.5 %)
  * peak-overpressure MAP, median
    over the loading region 0.15-0.8 m within 1 %   (measured 0.6 %)

Point peaks and impulse are printed as characterisation, not gated.

One invocation runs one case and saves its results under
tests/_amr_ab/; `--report` applies the gates to what has been saved.

Run:  cd blastlab/tests
      python _e2e_foam_amr_ab.py --only serial     (~6 min)
      python _e2e_foam_amr_ab.py --only np2        (~4 min)
      python _e2e_foam_amr_ab.py --report
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core.case import Case2D, validate_case            # noqa: E402
from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.solvers import get_solver                         # noqa: E402
from blastlab.solvers.foam import env                           # noqa: E402
from blastlab.solvers.hooks import RunHooks                     # noqa: E402

FAIL = []
GAUGES = [(0.5, 1.0), (0.7, 1.0)]
#: the domain (axisym r-z) and the loading-region band the map gate uses
LX, LY, CENTRE_Y = 1.0, 2.0, 1.0
R_BAND = (0.15, 0.8)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_amr_ab')


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


class H(RunHooks):
    def log(self, m):
        if not m.startswith('  [foam]'):
            print(m)


def case(np_):
    return Case2D(geometry='axisymmetric', Lx=LX, Ly=LY,
                  cell_size_m=0.02, charge=8.0, center=(0.0, CENTRE_Y),
                  gauges=list(GAUGES), n_snapshots=2, solver='blastfoam',
                  amr_levels=2, amr_display_level=1,
                  amr_max_cells=120_000, n_procs=np_)


def arrival(t, p, thr=0.05):
    idx = np.nonzero(np.asarray(p) - P_AIR > thr * P_AIR)[0]
    return float(t[idx[0]]) if len(idx) else float('nan')


def impulse(t, p, t_end):
    t = np.asarray(t)
    m = t <= t_end
    return float(np.trapezoid(
        np.clip(np.asarray(p)[m] - P_AIR, 0.0, None), t[m]))


def report():
    a, b = (os.path.join(OUT, f'{n}.npz') for n in ('serial', 'np2'))
    if not (os.path.exists(a) and os.path.exists(b)):
        print('  both runs must be done first')
        return 1
    za, zb = np.load(a), np.load(b)
    print(f"  wall: serial {float(za['wall']):.0f} s, "
          f"np2 {float(zb['wall']):.0f} s "
          f"({float(za['wall']) / float(zb['wall']):.2f}x); final mesh "
          f"{int(za['n_cells']):,} vs {int(zb['n_cells']):,} cells")
    t_common = min(za['times'][-1], zb['times'][-1])
    print('  gauge        serial arr    np2 arr    d%     serial pk'
          '    np2 pk    dpk%   impulse d%')
    for k, g in enumerate(GAUGES):
        aa = arrival(za['times'], za['pressures'][k])
        ab = arrival(zb['times'], zb['pressures'][k])
        pa = za['pressures'][k].max() - P_AIR
        pb = zb['pressures'][k].max() - P_AIR
        ia = impulse(za['times'], za['pressures'][k], t_common)
        ib = impulse(zb['times'], zb['pressures'][k], t_common)
        d_a = abs(ab - aa) / aa
        print(f'  {str(g):12s} {aa * 1e3:9.4f}  {ab * 1e3:9.4f}  '
              f'{d_a * 100:+6.2f}  {pa / 1e3:9.0f}  {pb / 1e3:8.0f}  '
              f'{(pb - pa) / pa * 100:+6.2f}  {(ib - ia) / ia * 100:+6.2f}')
        check(f'arrival at {g} within 1 %', d_a <= 0.01,
              f'{d_a * 100:.2f} %')
    pa, pb = za['p_peak'], zb['p_peak']
    nx, ny = pa.shape
    x = (np.arange(nx) + 0.5) * (LX / nx)
    y = (np.arange(ny) + 0.5) * (LY / ny)
    r = np.sqrt(x[:, None] ** 2 + (y[None, :] - CENTRE_Y) ** 2)
    band = (r >= R_BAND[0]) & (r <= R_BAND[1])
    rel = np.abs(pb - pa) / np.maximum(np.abs(pa), 1e3)
    med = float(np.median(rel[band]))
    check(f'peak map median over {R_BAND[0]:g}-{R_BAND[1]:g} m within 1 %',
          med <= 0.01, f'{med * 100:.3f} % over {int(band.sum())} cells')
    print()
    if FAIL:
        print(f'AMR PARALLEL A/B: FAIL ({len(FAIL)}): ' + ', '.join(FAIL))
        return 1
    print('AMR PARALLEL A/B: PASS')
    return 0


def main():
    if '--report' in sys.argv:
        return report()
    only = (sys.argv[sys.argv.index('--only') + 1]
            if '--only' in sys.argv else None)
    if env.status()[0] == 'fail':
        print('SKIP: no WSL blastFoam')
        return 0
    os.makedirs(OUT, exist_ok=True)
    for tag, np_ in (('serial', 1), ('np2', 2)):
        if only and tag != only:
            continue
        c = case(np_)
        vrep = validate_case(c)
        if vrep.errors:
            check(f'{tag} validates', False, str(vrep.errors))
            return 1
        t0 = time.perf_counter()
        res = get_solver(2, 'blastfoam')(c, H())
        wall = time.perf_counter() - t0
        g = res.gauges
        np.savez(os.path.join(OUT, tag + '.npz'),
                 times=np.asarray(g['times']),
                 pressures=np.asarray(g['pressures']), wall=wall,
                 p_peak=res.meta['p_peak'],
                 n_cells=res.meta['refine']['n_cells'])
        print(f'  --- {tag}: {wall:.0f} s')
    return report() if not only else 0


if __name__ == '__main__':
    sys.exit(main())
