"""Parallel blastFoam backend: np=1 vs np=2 equivalence on the small
2D axisymmetric case (8 kg TNT, 2.5 x 2.5 m, ~15.6k cells) plus the
parallel run-machinery contract (processor dirs, reconstructed times,
case-level probes). The fvSolution 'diagonal' solver has no global
sums, so the two runs should agree to near round-off. Auto-SKIPs
without WSL. Wall ~5 min (four runs: np1, np2, and a determinism pair
with the adaptive writeInterval controller switched off - see B23).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.case import Case2D                          # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402

#: T50: the pre-T50 solver default - every side lets the wave out
#: AND ends the run when it arrives (the plain 'transmit'
#: default would run this to the safety cap).
ALL_TERM = dict(x_lo='terminate', x_hi='terminate',
                y_lo='terminate', y_hi='terminate')

FAIL = []
GAUGES = [(0.6, 1.25), (1.0, 1.25)]
# np1 vs np2 is NOT bitwise: the decomposition changes FP evaluation
# order and the shock front amplifies the seed difference over ~10^3
# steps (observed ~1.5-3.5% at these extreme near-field gauges). The
# determinism check below pins our pipeline itself as race-free.
PEAK_RTOL = 0.05
ARRIVAL_RTOL = 0.03
IMPULSE_RTOL = 0.05


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def _case(n_procs):
    return Case2D(geometry='axisymmetric', Lx=2.5, Ly=2.5,
                  cell_size_m=0.02, charge=8.0, center=(0.0, 1.25),
                  n_snapshots=3, gauges=list(GAUGES), record_frames=0,
                  solver='blastfoam', material='TNT',
                  n_procs=n_procs, bcs=ALL_TERM)


def _arrival(times, p):
    ovp = p - P_AIR
    idx = np.argmax(ovp > 0.5 * ovp.max())
    return times[idx]


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM PARALLEL: SKIP")
        return

    # P2-7: since T68 an explicit rank count is clipped to what the
    # machine can take (env.rank_ceiling: cores minus headroom, and RAM
    # over RAM_GB_PER_RANK). On a VM of 3 GB or less that ceiling is 1,
    # so `_case(2)` would quietly run on ONE rank and this suite would
    # compare np1 against np1 and pass without testing anything. Say so
    # and skip instead.
    hw = env.hardware(probe=True) or {}
    ceiling, why = env.rank_ceiling(hw.get('cores'), hw.get('ram_gb'))
    if ceiling is not None and ceiling < 2:
        print(f"  [SKIP] this machine allows only {ceiling} MPI rank "
              f"({why}) - np=2 would silently run on one rank")
        print("\nFOAM PARALLEL: SKIP")
        return
    print(f"  rank ceiling here: {ceiling if ceiling else 'unknown'}"
          + (f" ({why})" if why else ""))

    from blastlab.solvers import get_solver
    solve = get_solver(2, 'blastfoam')

    print("--- serial run (np=1) ---")
    r1 = solve(_case(1))
    print("--- parallel run (np=2) ---")
    r2 = solve(_case(2))

    # Determinism pair: adaptive_write=False (B23). With the adaptive
    # controller on, `writeInterval` moves at a wall-clock-dependent
    # moment and `writeControl adjustableRunTime` clips the time step to
    # land on the new write times, so two identical runs diverge after
    # the first adaptation (observed: 525 vs 616 samples, max |dp| 470 Pa)
    # and this check failed at random. Pinning the interval makes the pair
    # bit-identical, which is what the check always claimed to test.
    print("--- determinism pair (np=2, writeInterval pinned) ---")
    d1 = solve(_case(2), adaptive_write=False)
    d2 = solve(_case(2), adaptive_write=False)

    n1 = [len(a) for a in d1.gauges['pressures']]
    n2 = [len(b) for b in d2.gauges['pressures']]
    n = min(len(d1.gauges['times']), len(d2.gauges['times']))
    # The solver itself is now deterministic: with writeInterval pinned,
    # every sample the two runs share is bit-identical. What is NOT
    # deterministic is WHERE the run ends - the arrival watcher reads a
    # written time on the Python side and then asks the solver to stop,
    # so the stop lands a step or two later depending on wall clock.
    check('determinism pair: identical sample times over the common record',
          np.array_equal(d1.gauges['times'][:n], d2.gauges['times'][:n]))
    check('determinism pair: identical gauge records over the common record',
          all(np.array_equal(a[:n], b[:n])
              for a, b in zip(d1.gauges['pressures'],
                              d2.gauges['pressures'])),
          f'{n} common samples')
    # ... and only the very tail can differ: the extra steps are the ones
    # the solver took between the watcher's request and the stop landing.
    longest = max(max(n1), max(n2))
    check('determinism pair: only the tail after the stop request differs',
          n >= 0.95 * longest,
          f'{n} common of {longest} ({n / max(longest, 1):.1%}); '
          f'{n1} vs {n2}')
    # a fixed writeInterval must still produce the same physics as the
    # adaptive default, or a regression in the pinned path would hide
    for k, gpt in enumerate(GAUGES):
        pa, pb = r2.gauges['pressures'][k], d1.gauges['pressures'][k]
        peak_a, peak_b = pa.max(), pb.max()
        check(f'pinned-interval peak matches the adaptive run at {gpt}',
              abs(peak_b - peak_a) <= 0.01 * peak_a,
              f'adaptive {peak_a/1e3:.1f} kPa, pinned {peak_b/1e3:.1f} kPa, '
              f'rel {(peak_b-peak_a)/peak_a:+.2e}')
        aa = _arrival(r2.gauges['times'], pa)
        ab = _arrival(d1.gauges['times'], pb)
        check(f'pinned-interval arrival matches the adaptive run at {gpt}',
              abs(ab - aa) <= 0.01 * max(aa, 1e-9),
              f'adaptive {aa*1e3:.4f} ms, pinned {ab*1e3:.4f} ms')

    # parallel machinery actually engaged
    cdir = r2.meta['case_dir']
    check('processor dirs created',
          os.path.isdir(os.path.join(cdir, 'processor0'))
          and os.path.isdir(os.path.join(cdir, 'processor1')))
    check('reconstructed time dirs ingested', len(r2.snapshots) >= 2)
    check('both stopped via arrival watcher',
          r1.stop_reason.startswith('shock arrived')
          and r2.stop_reason.startswith('shock arrived'),
          f'{r1.stop_reason!r} / {r2.stop_reason!r}')

    # gauge equivalence (peaks, arrivals, and the impulse integral
    # over the common time window - the two runs stop at slightly
    # different arrival-watcher times, so no final-field comparison)
    check('gauge counts equal',
          len(r1.gauges['pressures']) == len(r2.gauges['pressures'])
          == len(GAUGES))
    t_common = min(r1.gauges['times'][-1], r2.gauges['times'][-1])
    for k, gpt in enumerate(GAUGES):
        p1 = r1.gauges['pressures'][k]
        p2 = r2.gauges['pressures'][k]
        pk1, pk2 = p1.max(), p2.max()
        check(f'peak equivalence at {gpt}',
              abs(pk2 - pk1) <= PEAK_RTOL * pk1,
              f'np1 {pk1/1e3:.1f} kPa, np2 {pk2/1e3:.1f} kPa, '
              f'rel {(pk2-pk1)/pk1:+.2e}')
        a1 = _arrival(r1.gauges['times'], p1)
        a2 = _arrival(r2.gauges['times'], p2)
        check(f'arrival equivalence at {gpt}',
              abs(a2 - a1) <= ARRIVAL_RTOL * max(a1, 1e-9),
              f'np1 {a1*1e3:.4f} ms, np2 {a2*1e3:.4f} ms')
        m1 = r1.gauges['times'] <= t_common
        m2 = r2.gauges['times'] <= t_common
        i1 = np.trapezoid(p1[m1] - P_AIR, r1.gauges['times'][m1])
        i2 = np.trapezoid(p2[m2] - P_AIR, r2.gauges['times'][m2])
        check(f'impulse equivalence at {gpt}',
              abs(i2 - i1) <= IMPULSE_RTOL * max(abs(i1), 1e-9),
              f'np1 {i1:.1f} Pa s, np2 {i2:.1f} Pa s')

    # per-step FO maps survived the reconstruct
    check('np2 FO peak map present',
          r2.meta.get('peak_source') == 'foam-fo',
          str(r2.meta.get('peak_source')))

    print()
    if FAIL:
        print(f"FOAM PARALLEL: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM PARALLEL: PASS")


if __name__ == '__main__':
    main()
