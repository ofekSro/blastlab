"""WSL smokes for the E2/E3 features: a two-charge 3D run must show
two distinct high-pressure foci in the per-step peak map, and an
activation='none' (instant detonation) 2D run must complete via the
arrival watcher with a shocked gauge. Auto-SKIPs without WSL.
Wall ~11 min (measured 2026-09-10 on a 20-core / 62 GiB-VM machine;
the old "~3 min" predates T39's 5 -> 8 cells across the charge)."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.case import Case2D, Case3D, validate_case   # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402

#: T50: the pre-T50 solver default - every side lets the wave out
#: AND ends the run when it arrives (the plain 'transmit'
#: default would run this to the safety cap).
ALL_TERM = dict(x_lo='terminate', x_hi='terminate',
                y_lo='terminate', y_hi='terminate')

#: T50: the pre-T50 3D solver default - terminating sides over a
#: reflecting ground.
ALL_TERM_3D = dict(x_lo='terminate', x_hi='terminate',
                   y_lo='terminate', y_hi='terminate',
                   z_lo='reflect', z_hi='terminate')

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM FEATURES: SKIP")
        return

    from blastlab.solvers import get_solver

    # ── E2: two charges, detonated at their own centres ────────────────
    case3 = Case3D(Lx=1.4, Ly=1.0, Lz=1.0, cell_size_m=0.025,
                   charge=8.0, center=(0.35, 0.5, 0.5),
                   charges=[(1.05, 0.5, 0.5, 8.0)],
                   n_snapshots=3, record_frames=0,
                   solver='blastfoam', material='TNT', bcs=ALL_TERM_3D)
    rep = validate_case(case3)
    check('two-charge case validates', rep.ok, str(rep.errors))
    print('--- two-charge 3D run ---')
    r3 = get_solver(3, 'blastfoam')(case3)
    check('two-charge run stops via arrival',
          r3.stop_reason.startswith('shock arrived'), r3.stop_reason)
    pk = r3.meta['p_peak']
    xc, yc, zc = r3.meta['x_c'], r3.meta['y_c'], r3.meta['z_c']
    j = int(np.argmin(np.abs(yc - 0.5)))
    k = int(np.argmin(np.abs(zc - 0.5)))
    i1 = int(np.argmin(np.abs(xc - 0.35)))
    i2 = int(np.argmin(np.abs(xc - 1.05)))
    imid = int(np.argmin(np.abs(xc - 0.70)))
    pk1, pk2, pkm = pk[i1, j, k], pk[i2, j, k], pk[imid, j, k]
    check('two pressure foci in peak map',
          pk1 > 50 * P_AIR and pk2 > 50 * P_AIR,
          f'{pk1/1e6:.1f} / {pk2/1e6:.1f} MPa')
    check('foci roughly symmetric (equal charges)',
          abs(pk1 - pk2) < 0.35 * max(pk1, pk2),
          f'{pk1/1e6:.1f} vs {pk2/1e6:.1f} MPa')
    check('midpoint below the foci', pkm < min(pk1, pk2),
          f'mid {pkm/1e6:.1f} MPa')

    # ── E3: instant detonation ('none') ────────────────────────────────
    case2 = Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                   cell_size_m=0.02, charge=4.0, center=(0.0, 1.0),
                   gauges=[(0.8, 1.0)], n_snapshots=2, record_frames=0,
                   activation='none', solver='blastfoam',
                   material='TNT', bcs=ALL_TERM)
    rep = validate_case(case2)
    check("activation 'none' validates", rep.ok, str(rep.errors))
    print("--- activation 'none' 2D run ---")
    r2 = get_solver(2, 'blastfoam')(case2)
    check("'none' run stops via arrival",
          r2.stop_reason.startswith('shock arrived'), r2.stop_reason)
    ovp = r2.gauges['pressures'][0].max() - P_AIR
    check("'none' gauge shocked", ovp > 2 * P_AIR,
          f'{ovp/1e3:.0f} kPa')

    print()
    if FAIL:
        print(f"FOAM FEATURES: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM FEATURES: PASS")


if __name__ == '__main__':
    main()
