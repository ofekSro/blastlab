"""3D blastFoam backend smoke test: 8 kg TNT centred in a 1 m box
(~104k cells, ~1.5-3 min wall). Asserts the full native Result
contract (snapshot keys/dtypes/shapes incl. rho3, gauges, meta incl.
j0/k0/s0, frames) plus x/y gauge symmetry and the arrival-watcher
stop. Auto-SKIPs when WSL/blastFoam is unavailable.

Pass --tiny for a 0.6 m box (~30-60 s) while iterating.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.case import Case3D                          # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402

FAIL = []
SNAP_KEYS = {'p', 'rho_xz', 'rho_xy', 'speed_xz', 'speed_xy', 't', 'rho3'}
META_KEYS = {'x_c', 'y_c', 'z_c', 'x_face', 'y_face', 'z_face',
             'j0', 'k0', 'slice_axis', 's0', 'solid', 'Lx', 'Ly', 'Lz',
             'dx', 'eos', 'bcs', 'obstacles', 'charge', 'charge_center',
             'r_exp', 'r_src', 'from_profile', 'frames'}


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM 3D SMOKE: SKIP")
        return

    L = 0.6 if '--tiny' in sys.argv else 1.0
    c = L / 2.0
    case = Case3D(Lx=L, Ly=L, Lz=L, cell_size_m=0.025,
                  charge=8.0, center=(c, c, c),
                  gauges=[(L - 0.15, c, c), (c, L - 0.15, c)],
                  n_snapshots=4, record_frames=150,
                  solver='blastfoam', material='TNT')
    from blastlab.solvers import get_solver
    res = get_solver(3, 'blastfoam')(case)

    check('arrival-watcher stop',
          res.stop_reason.startswith('shock arrived'), res.stop_reason)
    check('stopped_early False', res.stopped_early is False)

    labels = list(res.snapshots)
    check('snapshot labels', len(labels) >= 2
          and labels[-1].endswith('(final)')
          and all(k.startswith('t = ') for k in labels))
    N = None
    for label, snap in res.snapshots.items():
        if set(snap) != SNAP_KEYS:
            check(f'snapshot keys ({label})', False,
                  str(set(snap) ^ SNAP_KEYS))
            break
        N = snap['p'].shape
    else:
        check('snapshot keys', True)
    snap = res.snapshots[labels[-1]]
    check('snapshot dtypes/shapes',
          snap['p'].dtype == np.float32 and snap['p'].ndim == 3
          and snap['rho_xz'].shape == (N[0], N[2])
          and snap['rho_xy'].shape == (N[0], N[1])
          and snap['speed_xz'].dtype == np.float32
          and isinstance(snap['t'], float)
          and snap['rho3'].ndim == 3)

    m = res.meta
    check('meta keys', set(m) >= META_KEYS,
          str(META_KEYS - set(m)))
    check('meta grid consistency',
          (len(m['x_c']), len(m['y_c']), len(m['z_c'])) == N
          and len(m['x_face']) == N[0] + 1
          and m['solid'].shape == N and not m['solid'].any()
          and 0 <= m['j0'] < N[1] and 0 <= m['k0'] < N[2]
          and m['slice_axis'] == 'y' and 0 <= m['s0'] < N[1])
    fr = m['frames']
    check('frames record',
          len(fr['times']) == len(fr['pressures']) >= 3
          and fr['pressures'][0].shape == (N[0], N[2])
          and fr['pressures'][0].dtype == np.float32
          and (np.diff(fr['times']) > 0).all())

    check('gauge points snapped',
          len(res.gauges['points']) == 2
          and len(res.gauges['pressures']) == 2
          and (np.diff(res.gauges['times']) > 0).all())
    px = res.gauges['pressures'][0].max() - P_AIR
    py = res.gauges['pressures'][1].max() - P_AIR
    check('gauges shocked', px > 2 * P_AIR and py > 2 * P_AIR,
          f'{px/1e3:.0f} / {py/1e3:.0f} kPa')
    # --tiny gauges land on cell faces (0.45/0.025 = 18): the two probes
    # snap to non-mirror cells, so the extreme near field reads ~8%
    # apart; the full-size case stays within 5%.
    sym_tol = 0.10 if '--tiny' in sys.argv else 0.05
    check('x/y symmetry', abs(px - py) <= sym_tol * max(px, py),
          f'{px/1e3:.0f} vs {py/1e3:.0f} kPa')

    # per-step peak/impulse maps from the function objects. Snapshot p
    # is float32 (quantum ~8 Pa at 1e8 Pa), p_peak float64 - compare
    # with a relative margin.
    check('peak source is foam FO', m.get('peak_source') == 'foam-fo',
          str(m.get('peak_source')))
    fin_p = res.snapshots[labels[-1]]['p'].astype(np.float64)
    check('p_peak dominates final p',
          m['p_peak'].shape == N
          and (m['p_peak'] >= fin_p * (1.0 - 1e-6)).all()
          and m['p_peak'].max() > 2 * P_AIR)
    check('impulse map sane',
          m['impulse'].shape == N and np.isfinite(m['impulse']).all()
          and m['impulse'].max() > 0)

    print()
    if FAIL:
        print(f"FOAM 3D SMOKE: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM 3D SMOKE: PASS")


if __name__ == '__main__':
    main()
