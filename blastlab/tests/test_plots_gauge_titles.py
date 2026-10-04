"""output.plots.figure_gauges_nd - the exported gauge-trace titles carry
the ENTERED gauge number (GUI-12 A3, F42's sibling; no GUI, no WSL).

A 2D result with G1-G5 entered and G2, G3 dropped titles its panels
`G1 (0.83, 0.61) m → cell (0.82, 0.62)`, `G4 ...`, `G5 ...` and carries
a footnote naming G2 and G3 (GUI-13 (d)); with no drop the titles are
exactly today's strings and there is no footnote (the F42 owner rule: a
run without a drop is byte-identical). The Tk Gauges tab draws the same
figure.

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


def figure(keep, **kw):
    """The gauge figure for the kept entered gauges (0-based)."""
    t = np.linspace(0.0, 5e-3, 50)
    pts = [CELLS[j] for j in keep]
    g = dict(times=t, points=pts, pressures=[np.full(t.size, P_AIR)
                                             for _ in pts])
    meta = dict(charge=1.0, eos='JWL', geometry='axisymmetric',
                gauges=ENTERED)
    return plots.figure_gauges_nd(g, meta, **kw)


def titles(keep, **kw):
    """The panel titles of the gauge figure, shown panels only."""
    fig = figure(keep, **kw)
    return [ax.get_title() for ax in fig.axes if ax.get_visible()]


def footnote(fig):
    """The figure's footnote (its supxlabel), or None when it has none."""
    lab = getattr(fig, '_supxlabel', None)
    return None if lab is None else lab.get_text()


def main():
    print('\nfigure_gauges_nd titles')
    got = titles([0, 3, 4])
    # GUI-13 (d), D6: with a drop the titles carry the entered number,
    # the entered position and the cell (a named edit of GUI-12 A3's
    # `Gauge 1  (0.82, 0.62) m` drop-case literals)
    check('G2 and G3 dropped: titles start G1, G4, G5',
          [s.split(' ')[0] for s in got] == ['G1', 'G4', 'G5'], str(got))
    check('G2 and G3 dropped: entered position -> cell position',
          got == ['G1 (0.83, 0.61) m → cell (0.82, 0.62)',
                  'G4 (2.01, 0.88) m → cell (2.02, 0.88)',
                  'G5 (2.52, 1.71) m → cell (2.52, 1.73)'], str(got))
    full = titles([0, 1, 2, 3, 4])
    check('no drop: titles as before (literal)',
          full == ['Gauge 1  (0.82, 0.62) m', 'Gauge 2  (1.23, 0.62) m',
                   'Gauge 3  (1.52, 0.62) m', 'Gauge 4  (2.02, 0.88) m',
                   'Gauge 5  (2.52, 1.73) m'], str(full))

    print('\nfigure_gauges_nd footnote (GUI-13 (d))')
    fig = figure([0, 3, 4])
    check('a drop: the footnote names the missing gauges',
          footnote(fig) == 'Not shown: G2, G3 - dropped by the solver',
          str(footnote(fig)))
    fig = figure([0, 3, 4], drop_note='G2 dropped by the solver (inside '
                                      'Wall 1) · G3 dropped by the solver')
    check('a drop with the Qt note: that note is the footnote',
          footnote(fig) == 'G2 dropped by the solver (inside Wall 1) · '
                           'G3 dropped by the solver', str(footnote(fig)))
    fig = figure([0, 1, 2, 3, 4])
    check('no drop: no footnote artist (the suptitle is the only text)',
          footnote(fig) is None and len(fig.texts) == 1,
          str([t.get_text() for t in fig.texts]))
    fig = figure([0, 1, 2, 3, 4], drop_note='')
    check('no drop, an empty Qt note: still no footnote',
          footnote(fig) is None and len(fig.texts) == 1)
    from blastlab.output.gauge_summary import dropped_numbers
    check('dropped_numbers: [2, 3]; none dropped: []; a pairing short of '
          'a point (P1): []',
          dropped_numbers([CELLS[j] for j in (0, 3, 4)], ENTERED) == [2, 3]
          and dropped_numbers(CELLS, ENTERED) == []
          and dropped_numbers([(9.0, 9.0, 9.0)], ENTERED) == [])


if __name__ == '__main__':
    main()
    print()
    print('PLOTS GAUGE TITLES: ' + ('PASS' if not FAILS else
                                    f'FAIL ({len(FAILS)}): '
                                    + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
