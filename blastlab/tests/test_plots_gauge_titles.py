"""output.plots.figure_gauges_nd - the exported gauge-trace titles carry
the ENTERED gauge number (GUI-12 A3, F42's sibling; no GUI, no WSL).

A 2D result with G1-G5 entered and G2, G3 dropped titles its panels
`Gauge 1`, `Gauge 4`, `Gauge 5`; with no drop the titles are exactly
today's strings (the F42 owner rule: a run without a drop is
byte-identical). The Tk Gauges tab draws the same figure.

Run:  cd blastlab/tests && python test_plots_gauge_titles.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.output import plots                               # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


#: five gauges entered in a 2D case (dx 0.05); the cell centres the
#: solver snaps them to
ENTERED = [(0.83, 0.61), (1.21, 0.62), (1.53, 0.64), (2.01, 0.88),
           (2.52, 1.71)]
CELLS = [(0.825, 0.625), (1.225, 0.625), (1.525, 0.625), (2.025, 0.875),
         (2.525, 1.725)]


def titles(keep):
    """The panel titles of the gauge figure for the kept entered gauges
    (0-based), shown panels only."""
    t = np.linspace(0.0, 5e-3, 50)
    pts = [CELLS[j] for j in keep]
    g = dict(times=t, points=pts, pressures=[np.full(t.size, P_AIR)
                                             for _ in pts])
    meta = dict(charge=1.0, eos='JWL', geometry='axisymmetric',
                gauges=ENTERED)
    fig = plots.figure_gauges_nd(g, meta)
    return [ax.get_title() for ax in fig.axes if ax.get_visible()]


def main():
    print('\nfigure_gauges_nd titles')
    got = titles([0, 3, 4])
    check('G2 and G3 dropped: titles start Gauge 1, Gauge 4, Gauge 5',
          [s.split('  ')[0] for s in got] == ['Gauge 1', 'Gauge 4',
                                              'Gauge 5'], str(got))
    check('G2 and G3 dropped: the cell position is still shown',
          got == ['Gauge 1  (0.82, 0.62) m', 'Gauge 4  (2.02, 0.88) m',
                  'Gauge 5  (2.52, 1.73) m'], str(got))
    full = titles([0, 1, 2, 3, 4])
    check('no drop: titles as before (literal)',
          full == ['Gauge 1  (0.82, 0.62) m', 'Gauge 2  (1.23, 0.62) m',
                   'Gauge 3  (1.52, 0.62) m', 'Gauge 4  (2.02, 0.88) m',
                   'Gauge 5  (2.52, 1.73) m'], str(full))


if __name__ == '__main__':
    main()
    print()
    print('PLOTS GAUGE TITLES: ' + ('PASS' if not FAILS else
                                    f'FAIL ({len(FAILS)}): '
                                    + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
