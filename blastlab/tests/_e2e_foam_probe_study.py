"""Manual e2e (WSL): where does a blastFoam gauge actually sample?

T40 / ROADMAP N16-a. The 3D AMR e2e records a gauge arrival ~18 % later
than the statically refined reference while the peak agrees to 2.7 %.
The suspect is `blastProbes { adjustLocations yes; }`, which moves every
probe onto the centre of the cell that holds it AT t = 0: on the AMR
case that cell is a coarse base cell, on the static reference a much
smaller one, so the two runs sample at different radii - and under AMR
the cell later refines underneath the sample point.

Runs the same small case four ways - {AMR, static reference} x
{adjustLocations yes, no} - with two gauges: one on a cell CORNER of
both meshes (the shape the AMR e2e uses) and one already at a base-cell
CENTRE, which adjustLocations should leave alone.

Each solve takes ~6 min, so one invocation runs ONE case and saves its
gauge traces under tests/_probe_study/; `--report` prints the table from
whatever has been saved.

Run:  cd blastlab/tests
      python _e2e_foam_probe_study.py --adjust yes --only AMR
      python _e2e_foam_probe_study.py --adjust yes --only static
      python _e2e_foam_probe_study.py --adjust no  --only AMR
      python _e2e_foam_probe_study.py --adjust no  --only static
      python _e2e_foam_probe_study.py --report
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core.case import Case3D, validate_case             # noqa: E402
from blastlab.core.constants import P_AIR                        # noqa: E402
from blastlab.solvers import get_solver                          # noqa: E402
from blastlab.solvers.foam import env                            # noqa: E402
from blastlab.solvers.hooks import RunHooks                      # noqa: E402

#: Small on purpose: this PC has 7.7 GB with 4 GB inside the WSL VM, and
#: the reference's display grid (whole domain at the finest level) is what
#: runs the host out of memory - 0.8 m keeps it at 64^3.
L = 0.8
CENTRE = (L / 2, L / 2, L / 2)
#: gauge 1 sits on a cell CORNER of both meshes (0.05 base and the 0.0125
#: finest level); gauge 2 is the CENTRE of a base (0.05 m) cell, which
#: adjustLocations should leave where it is
GAUGES = [(0.65, 0.40, 0.40), (0.625, 0.425, 0.425)]
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       '_probe_study')


class Hooks(RunHooks):
    def __init__(self):
        super().__init__()
        self.steps = 0

    def log(self, s):
        if not s.startswith('  [foam]'):
            print(s)

    def progress(self, p):
        self.steps = max(self.steps, p.step)


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
    for adjust in ('yes', 'no'):
        a = os.path.join(OUT_DIR, adjust + '_AMR.npz')
        u = os.path.join(OUT_DIR, adjust + '_static.npz')
        if not (os.path.exists(a) and os.path.exists(u)):
            print('=== adjustLocations ' + adjust + ': incomplete, skipped')
            continue
        za, zu = np.load(a), np.load(u)
        print('=== adjustLocations ' + adjust + ' ===')
        print('  gauge                      AMR arr    static arr    d%      '
              'AMR pk     static pk    d%')
        for k, g in enumerate(GAUGES):
            aa = arrival(za['times'], za['pressures'][k])
            au = arrival(zu['times'], zu['pressures'][k])
            pa = za['pressures'][k].max() - P_AIR
            pu = zu['pressures'][k].max() - P_AIR
            print(f'  {str(g):24s} {aa * 1e3:8.4f}  {au * 1e3:11.4f}  '
                  f'{(aa - au) / au * 100:+7.2f}  {pa / 1e3:9.0f}  '
                  f'{pu / 1e3:10.0f}  {(pa - pu) / pu * 100:+7.2f}')
    return 0


def main():
    if '--report' in sys.argv:
        return report()
    adjust = True
    if '--adjust' in sys.argv:
        adjust = sys.argv[sys.argv.index('--adjust') + 1] != 'no'
    only = (sys.argv[sys.argv.index('--only') + 1]
            if '--only' in sys.argv else None)
    if env.status()[0] == 'fail':
        print('SKIP: no WSL blastFoam')
        return 0
    base = dict(Lx=L, Ly=L, Lz=L, charge=8.0, center=CENTRE,
                gauges=list(GAUGES), n_snapshots=1, solver='blastfoam',
                material='TNT', probe_adjust=adjust)
    cases = {
        'AMR': Case3D(cell_size_m=0.05, amr_levels=2, amr_display_level=1,
                      amr_max_cells=150_000, **base),
        # same finest cell as the AMR case (0.05 / 2^2 = 0.0125 m)
        'static': Case3D(cell_size_m=0.05, charge_refine='zone',
                         n_procs=1, **base),
    }
    tag_adjust = 'yes' if adjust else 'no'
    print('=== adjustLocations ' + tag_adjust + ' ===')
    for label, case in cases.items():
        if only and label != only:
            continue
        vrep = validate_case(case)
        if vrep.errors:
            print('  ' + label + ': INVALID ' + str(vrep.errors))
            return 1
        t0 = time.perf_counter()
        h = Hooks()
        res = get_solver(3, 'blastfoam')(case, h)
        print(f'  --- {label}: {time.perf_counter() - t0:.0f} s, '
              f'{h.steps} steps, case {res.meta.get("case_dir")}')
        _save(tag_adjust + '_' + label, res)
    return report() if not only else 0


if __name__ == '__main__':
    sys.exit(main())
