"""post-mortem load of a PARALLEL AMR run - no WSL.

A parallel AMR run is never reconstructed (reconstructPar cannot follow
a mesh that changes), so its written times stay in `processor*/` and
`spec.time_dirs(name)` returns one directory per rank - T42/N16-b.

`postmortem.load_run` honoured that in its readiness gate and in its
sanity walk-back, but its ingest loop built `os.path.join(unc, name)`
instead: the case root plus the time name, which on a decomposed run
does not exist. Every time was skipped and the loader reported "no
readable time directory" for a run that had 96 of them. Loading ANY
parallel AMR run failed that way.

The fake case here is the same 1 x 1 m / 0.5 m base / 2 AMR levels one
test_foam_amr_ingest uses, split over two ranks, with `_paths` pointed
at a local temp dir so the whole load runs off the local disk.

Run:  cd blastlab/tests && python test_foam_postmortem_decomposed.py
"""
import os
import shutil
import sys
import tempfile

import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core.case import Case2D, save_case                 # noqa: E402
from blastlab.core.constants import P_AIR                        # noqa: E402
from blastlab.solvers.foam import postmortem                     # noqa: E402
from test_foam_amr_ingest import (Log, block_centres,            # noqa: E402
                                  write_time)

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def build_case(root, n_procs):
    """A finished AMR run on disk: case.json, the t = 0 mesh, and three
    written times. With n_procs > 1 the times go to processor*/, exactly
    where a parallel AMR run leaves them."""
    case = Case2D(geometry='planar', Lx=1.0, Ly=1.0, cell_size_m=0.5,
                  charge=100.0, center=(0.5, 0.5), solver='blastfoam',
                  amr_levels=2, record_frames=10, n_snapshots=2,
                  n_procs=n_procs)
    save_case(case, os.path.join(root, 'case.json'))

    C0 = block_centres(0, 0, 0.5, 2)                     # 4 base cells
    write_time(root, '0', 0.0, C0, [0, 0, 0, 0],
               np.full(4, P_AIR), label_list=True)

    # the refined block grows, so the frames differ from each other
    C1 = np.vstack([C0[:3], block_centres(0.5, 0.5, 0.25, 2)])
    lv1 = [0, 0, 0, 1, 1, 1, 1]
    C2 = np.vstack([C1[:6], block_centres(0.75, 0.75, 0.125, 2)])
    lv2 = [0, 0, 0, 1, 1, 1, 2, 2, 2, 2]

    for name, t, C, lv in (('1e-05', 1e-5, C1, lv1),
                           ('2e-05', 2e-5, C2, lv2),
                           ('3e-05', 3e-5, C2, lv2)):
        p = P_AIR + 1000.0 * np.arange(len(C))
        if n_procs == 1:
            write_time(root, name, t, C, lv, p)
            continue
        cut = 3                                  # rank 0 keeps the base
        for i, sl in enumerate((slice(0, cut), slice(cut, len(C)))):
            pu = os.path.join(root, f'processor{i}')
            os.makedirs(pu, exist_ok=True)
            write_time(pu, name, t, C[sl], list(lv)[sl], p[sl])
    return case


def load(root):
    """load_run against a local directory (no WSL): _paths normally maps
    every name onto \\\\wsl.localhost\\..., so point it at the temp dir."""
    real = postmortem._paths
    postmortem._paths = lambda _d: (root, root)
    try:
        return postmortem.load_run(root, Log())
    finally:
        postmortem._paths = real


def main():
    print("\nparallel AMR run (times in processor*/)")
    root = tempfile.mkdtemp(prefix='blastlab_pm_np_')
    try:
        build_case(root, n_procs=2)
        check('the case root holds no time dirs of its own, only 0',
              sorted(d for d in os.listdir(root)
                     if d.startswith('processor')) == ['processor0',
                                                       'processor1'])
        try:
            res = load(root)
        except Exception as exc:                          # noqa: BLE001
            check('a decomposed run loads', False,
                  f'{type(exc).__name__}: {exc}')
            return
        check('a decomposed run loads', True)
        check('every written time was ingested, not skipped',
              '3 written frames' in res.stop_reason
              or res.stop_reason.endswith('(3 frames)'), res.stop_reason)
        check('the replay frames are on the display grid',
              res.meta['frames']['pressures'][0].shape == (8, 8),
              str(res.meta['frames']['pressures'][0].shape))
        check('...and carry a level map per frame (AMR overlay)',
              len(res.meta['frames']['levels'])
              == len(res.meta['frames']['pressures']))
        check('the level maps follow the refinement',
              res.meta['frames']['levels'][-1].max() == 2,
              str(res.meta['frames']['levels'][-1].max()))
        check('snapshots were picked', len(res.snapshots) >= 1,
              str(len(res.snapshots)))
        check('the final field is there for the 3D remap',
              res.meta['final_state']['p'].shape == (8, 8))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\nthe serial layout still loads (times at the case root)")
    root = tempfile.mkdtemp(prefix='blastlab_pm_1_')
    try:
        build_case(root, n_procs=1)
        try:
            res = load(root)
            ok, detail = True, ''
        except Exception as exc:                          # noqa: BLE001
            ok, detail = False, f'{type(exc).__name__}: {exc}'
        check('a serial run loads', ok, detail)
        if ok:
            check('same display grid as the decomposed one',
                  res.meta['frames']['pressures'][0].shape == (8, 8))
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    main()
    print()
    print('FOAM POSTMORTEM DECOMPOSED: '
          + ('PASS' if not FAILS
             else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
