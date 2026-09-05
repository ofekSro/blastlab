"""ResultsPanel per-gauge summary table + CSV export (N2): headless.

Synthetic 1D, 2D and 3D results with Friedlander-like gauge traces must
fill the Gauges-tab table with one row per gauge (peak/arrival numbers
matching output.gauge_summary), a result without gauges leaves it empty,
and the export writer produces the CSV the panel would save.
Headless (Agg backend, hidden Tk root) - needs customtkinter, no WSL.

Run:  cd blastlab/tests && python test_gui_gauge_summary.py
"""
import csv
import os
import sys
import tempfile

import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.output import gauge_summary as gs                 # noqa: E402
from blastlab.solvers.hooks import Result                       # noqa: E402
from test_gui_results_fields import fake_2d, fake_3d            # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def pulse(t, ta, ps, td=3e-3, b=1.2):
    tau = np.clip((t - ta) / td, 0.0, None)
    return P_AIR + np.where(t >= ta, ps * (1 - tau) * np.exp(-b * tau), 0.0)


def with_gauges(res, points=None, radii=None):
    t = np.linspace(0.0, 10e-3, 2001)
    n = len(points) if points is not None else len(radii)
    press = [pulse(t, 1e-3 * (k + 1), 200e3 / (k + 1)) for k in range(n)]
    if radii is not None:
        res.gauges = dict(times=t, radii=list(radii), pressures=press)
    else:
        res.gauges = dict(times=t, points=list(points), pressures=press)
    return res


def fake_1d():
    r = np.linspace(0.05, 4.95, 50)
    p = np.full_like(r, P_AIR)
    snaps = {'t = 1.000 ms (final)': dict(r=r, p=p, rho=np.full_like(r, 1.2),
                                          u=np.zeros_like(r))}
    meta = dict(eos='idealGas', charge_kg=1.0, radius_m=5.0)
    return Result(snaps, dict(times=np.array([]), radii=[], pressures=[]),
                  meta, 'end time reached', False)


def main():
    import customtkinter as ctk
    from blastlab.gui.results_panel import ResultsPanel

    root = ctk.CTk()
    root.withdraw()
    panel = ResultsPanel(root)

    print("\nsummary table follows the selected result")
    cases = (('1D', 1, with_gauges(fake_1d(), radii=[1.0, 2.0, 3.0])),
             ('2D', 2, with_gauges(fake_2d(), points=[(0.6, 0.4), (0.9, 0.4)])),
             ('3D', 3, with_gauges(fake_3d(), points=[(0.9, 0.5, 0.4)])))
    for label, dim, res in cases:
        panel.add_result(label, dim, res)
        items = panel.summary_table.get_children()
        rows = gs.summarize_gauges(res.gauges)
        check(f'{label}: one table row per gauge', len(items) == len(rows),
              f'{len(items)} vs {len(rows)}')
        if items:
            v = panel.summary_table.item(items[0])['values']
            check(f'{label}: first row shows label, peak and arrival',
                  str(v[0]) == rows[0]['gauge']
                  and abs(float(v[1]) - rows[0]['peak_kpa']) < 0.06
                  and abs(float(v[2]) - rows[0]['arrival_ms']) < 0.01,
                  str(v))
    panel.add_result('no gauges', 2, fake_2d())
    check('result without gauges -> empty table',
          panel.summary_table.get_children() == ())

    print("\nexport")
    res = cases[1][2]
    out = os.path.join(tempfile.mkdtemp(prefix='blastlab_gsum_'),
                       'gauges_2d_summary.csv')
    gs.save_gauge_summary(panel.summary_rows(res), out)
    with open(out, newline='') as f:
        lines = list(csv.reader(f))
    check('CSV: header + one line per gauge', len(lines) == 3
          and tuple(lines[0]) == gs.COLUMNS, str(lines[:1]))
    texts = []

    def walk(w):
        for ch in w.winfo_children():
            try:
                texts.append(ch.cget('text'))
            except Exception:
                pass
            walk(ch)
    walk(panel)
    check("'Summary CSV' export button present", 'Summary CSV' in texts, str(texts))
    root.destroy()


if __name__ == '__main__':
    main()
    print()
    print('GUI GAUGE SUMMARY: ' + ('PASS' if not FAILS
                                   else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
