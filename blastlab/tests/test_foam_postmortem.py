"""postmortem.load_run round-trip: run a small 2D foam case live, then
reload the same finished case dir and require the exact same Result
shapes and values. Path mapping and run listing are checked without
WSL; the round-trip auto-SKIPs when blastFoam is unavailable."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def main():
    from blastlab.solvers.foam import postmortem as pm

    # ── path mapping (no WSL) ───────────────────────────────────────────
    p, _ = pm._paths('20260101-000000_2d')
    check('bare name maps under RUNS_ROOT',
          p == '/root/blastlab_runs/20260101-000000_2d', p)
    p, _ = pm._paths('\\\\wsl.localhost\\Ubuntu\\root\\blastlab_runs'
                     '\\x_3d')
    check('UNC maps to posix', p == '/root/blastlab_runs/x_3d', p)
    p, _ = pm._paths('/root/spike/s1')
    check('posix passes through', p == '/root/spike/s1', p)

    # ── live-vs-loaded round trip (WSL) ─────────────────────────────────
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM POSTMORTEM: "
              + ("FAIL" if FAIL else "PASS (offline checks only)"))
        return 1 if FAIL else 0

    from blastlab.core.case import Case2D
    from blastlab.solvers import get_solver
    case = Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                  cell_size_m=0.02, charge=4.0, center=(0.0, 1.0),
                  n_snapshots=3, gauges=[(0.6, 1.0)], record_frames=0,
                  solver='blastfoam', material='TNT')
    live = get_solver(2, 'blastfoam')(case)
    loaded = pm.load_run(live.meta['case_dir'])

    check('snapshot labels equal',
          list(live.snapshots) == list(loaded.snapshots),
          f"{list(live.snapshots)} vs {list(loaded.snapshots)}")
    lbl = list(live.snapshots)[-1]
    for key in ('p', 'rho', 'speed'):
        a = live.snapshots[lbl][key]
        b = loaded.snapshots[lbl][key]
        check(f'final snapshot {key} identical',
              a.shape == b.shape and np.array_equal(a, b))
    check('gauge times identical',
          np.array_equal(live.gauges['times'], loaded.gauges['times']))
    check('gauge pressures identical',
          all(np.array_equal(a, b) for a, b in
              zip(live.gauges['pressures'], loaded.gauges['pressures'])))
    check('meta keys superset',
          set(loaded.meta) >= set(live.meta) - {'frames'},
          str((set(live.meta) - {'frames'}) - set(loaded.meta)))
    fs_l, fs_p = live.meta['final_state'], loaded.meta['final_state']
    check('final_state identical',
          all(np.array_equal(np.asarray(fs_l[k]), np.asarray(fs_p[k]))
              for k in ('rho', 'u', 'v', 'e', 'p', 'phase'))
          and fs_l['t'] == fs_p['t'])
    check('FO maps survive reload',
          loaded.meta.get('peak_source') == live.meta.get('peak_source'))
    check('stop reason marks post-mortem',
          loaded.stop_reason.startswith('loaded post-mortem'))

    print()
    if FAIL:
        print(f"FOAM POSTMORTEM: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("FOAM POSTMORTEM: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
