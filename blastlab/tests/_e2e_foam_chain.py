"""Manual e2e (WSL): a blastFoam stage started from a 1D profile (N7).

T41. Runs a native 1D stage, hands its final profile to a blastFoam 2D
axisymmetric stage, and compares that against the SAME foam 2D domain
initialised directly from the charge. Both stages see the same gauges,
so the profile hand-off is judged on the numbers the user reads:

  gauge peaks within 10 %, arrival times within 5 %.

The 1D stage is stopped well before the gauges (its domain radius is
smaller than the first gauge), so the profile really is the state the
2D stage continues from rather than a finished answer.

Each 2D solve takes several minutes, so one invocation runs one of them
and saves its gauge traces under tests/_chain_study/; `--report` prints
the comparison from what has been saved.

Run:  cd blastlab/tests
      python _e2e_foam_chain.py --only chained
      python _e2e_foam_chain.py --only direct
      python _e2e_foam_chain.py --report
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core.case import Case1D, Case2D, validate_case      # noqa: E402
from blastlab.core.constants import P_AIR                         # noqa: E402
from blastlab.core import profiles                                # noqa: E402
from blastlab.solvers import get_solver                           # noqa: E402
from blastlab.solvers.foam import env                             # noqa: E402

FAIL = []
#: the 2D stages: 1 m radius, burst 1 m up, gauges out at 0.6/0.8 m
GAUGES = [(0.6, 1.0), (0.8, 1.0)]
PEAK_TOL = 0.10
ARRIVAL_TOL = 0.05
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       '_chain_study')


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def arrival(times, p, thresh=0.05):
    ovp = np.asarray(p) - P_AIR
    idx = np.nonzero(ovp > thresh * P_AIR)[0]
    return float(times[idx[0]]) if len(idx) else float('nan')


def _save(tag, res):
    os.makedirs(OUT_DIR, exist_ok=True)
    g = res.gauges
    np.savez(os.path.join(OUT_DIR, tag + '.npz'),
             times=np.asarray(g['times']),
             pressures=np.asarray(g['pressures']))
    print('  saved ' + tag + '.npz')


def report():
    a = os.path.join(OUT_DIR, 'chained.npz')
    b = os.path.join(OUT_DIR, 'direct.npz')
    if not (os.path.exists(a) and os.path.exists(b)):
        print('  both runs must be done first')
        return 1
    gc, gd = np.load(a), np.load(b)
    print('  gauge        chained arr   direct arr    d%     chained pk'
          '   direct pk     d%')
    for k, g in enumerate(GAUGES):
        ac = arrival(gc['times'], gc['pressures'][k])
        ad = arrival(gd['times'], gd['pressures'][k])
        pc = gc['pressures'][k].max() - P_AIR
        pd = gd['pressures'][k].max() - P_AIR
        d_a = abs(ac - ad) / ad
        d_p = abs(pc - pd) / pd
        print(f'  {str(g):12s} {ac * 1e3:9.4f} ms {ad * 1e3:10.4f}  '
              f'{d_a * 100:+6.2f}  {pc / 1e3:10.0f}  {pd / 1e3:10.0f}  '
              f'{(pc - pd) / pd * 100:+6.2f}')
        check(f'arrival at {g} within {ARRIVAL_TOL * 100:.0f} %',
              d_a <= ARRIVAL_TOL, f'{d_a * 100:.2f} %')
        check(f'peak at {g} within {PEAK_TOL * 100:.0f} %',
              d_p <= PEAK_TOL, f'{d_p * 100:.2f} %')
    print()
    if FAIL:
        print(f'FOAM CHAIN: FAIL ({len(FAIL)}): ' + ', '.join(FAIL))
        return 1
    print('FOAM CHAIN: PASS')
    return 0


def main():
    if '--report' in sys.argv:
        return report()
    only = (sys.argv[sys.argv.index('--only') + 1]
            if '--only' in sys.argv else None)
    if env.status()[0] == 'fail':
        print('SKIP: no WSL blastFoam')
        return 0
    os.makedirs(OUT_DIR, exist_ok=True)
    prof = os.path.join(OUT_DIR, 'stage1.txt')

    # stage 1: native 1D, stopped at 0.4 m (well inside the gauges)
    c1 = Case1D(radius_m=0.4, charge_kg=1.0, cell_size_m=0.004,
                gauge_radii=[0.35], n_snapshots=1, solver='native')
    t0 = time.perf_counter()
    r1 = get_solver(1, 'native')(c1)
    profiles.save_profile(r1.meta['final_profile'], prof)
    print(f'  --- stage 1 (native 1D): {time.perf_counter() - t0:.0f} s, '
          f"front reaches {r1.meta['final_profile']['r'][-1]:.2f} m, "
          f"t = {r1.meta['final_profile']['t'] * 1e3:.4f} ms")

    dom = dict(geometry='axisymmetric', Lx=1.0, Ly=2.0, cell_size_m=0.01,
               center=(0.0, 1.0), gauges=list(GAUGES), n_snapshots=1,
               eos='idealGas', solver='blastfoam', material='TNT')
    chained = Case2D(init_mode='profile1d', profile_file_in=prof, **dom)
    direct = Case2D(charge=1.0, **dom)

    for label, case in (('chained', chained), ('direct', direct)):
        if only and label != only:
            continue
        vrep = validate_case(case)
        if vrep.errors:
            check(f'{label} case validates', False, str(vrep.errors))
            return 1
        t0 = time.perf_counter()
        res = get_solver(2, 'blastfoam')(case)
        print(f'  --- {label}: {time.perf_counter() - t0:.0f} s')
        _save(label, res)
    return report() if not only else 0


if __name__ == '__main__':
    sys.exit(main())
