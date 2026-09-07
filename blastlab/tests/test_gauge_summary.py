"""output.gauge_summary - per-gauge engineering numbers (no GUI, no WSL).

A synthetic Friedlander pulse with known peak, arrival, positive-phase
duration and analytic positive-phase impulse; a record cut inside the
positive phase; a gauge that never sees the shock; labels for 1D and
2D/3D gauge dicts; the CSV round trip.

Run:  cd blastlab/tests && python test_gauge_summary.py
"""
import csv
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.output import gauge_summary as gs                 # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def friedlander(t, ta, ps, td, b):
    tau = np.clip((t - ta) / td, 0.0, None)
    ovp = np.where(t >= ta, ps * (1.0 - tau) * np.exp(-b * tau), 0.0)
    return P_AIR + ovp


def analytic_pos_impulse(ps, td, b):
    """int_0^td ps (1 - x/td) e^{-b x/td} dx."""
    return ps * td * ((1 - np.exp(-b)) / b - (1 - (1 + b) * np.exp(-b)) / b ** 2)


def main():
    print("\nFriedlander pulse")
    ta, ps, td, b = 2e-3, 300e3, 4e-3, 1.5
    t = np.linspace(0.0, 12e-3, 12001)
    p = friedlander(t, ta, ps, td, b)
    r = gs.summarize_trace(t, p)
    check('peak overpressure = Ps (kPa)', abs(r['peak_kpa'] - ps / 1e3) < 1e-6, str(r['peak_kpa']))
    check('arrival at the first sample above 10% (= ta)',
          abs(r['arrival_ms'] - ta * 1e3) < 2e-3, str(r['arrival_ms']))
    check('time of peak = ta', abs(r['t_peak_ms'] - ta * 1e3) < 2e-3, str(r['t_peak_ms']))
    check('positive-phase duration = td', abs(r['pos_duration_ms'] - td * 1e3) < 2e-3,
          str(r['pos_duration_ms']))
    ana = analytic_pos_impulse(ps, td, b)
    check('positive-phase impulse within 0.1% of the analytic value',
          abs(r['pos_impulse'] - ana) / ana < 1e-3, f"{r['pos_impulse']:.3f} vs {ana:.3f}")
    check('net impulse smaller than positive-phase (negative phase counted)',
          r['net_impulse'] < r['pos_impulse'])
    check('phase complete', r['complete'] is True)

    print("\nrecord cut inside the positive phase")
    cut = t <= ta + 0.5 * td
    r2 = gs.summarize_trace(t[cut], p[cut])
    check('flagged incomplete', r2['complete'] is False)
    check('duration is a lower bound (half td)',
          abs(r2['pos_duration_ms'] - 0.5 * td * 1e3) < 2e-3, str(r2['pos_duration_ms']))
    check('impulse is a lower bound', 0 < r2['pos_impulse'] < ana)

    print("\nquiet gauge / short record")
    r3 = gs.summarize_trace(t, np.full_like(t, P_AIR))
    check('no arrival -> NaN times, zero peak',
          np.isnan(r3['arrival_ms']) and r3['peak_kpa'] == 0.0 and np.isnan(r3['pos_impulse']))
    r4 = gs.summarize_trace([0.0], [P_AIR])
    check('single sample -> all NaN', np.isnan(r4['peak_kpa']))

    print("\ngauge dicts + CSV")
    g1 = dict(times=t, radii=[1.0, 2.5], pressures=[p, friedlander(t, 2 * ta, ps / 3, td, b)])
    rows = gs.summarize_gauges(g1)
    # QA-33: every label starts with the gauge number the plots use
    check('1D labels',
          [r['gauge'] for r in rows] == ['G1  r = 1.000 m',
                                         'G2  r = 2.500 m'],
          str([r['gauge'] for r in rows]))
    check('second gauge later and weaker',
          rows[1]['arrival_ms'] > rows[0]['arrival_ms'] and rows[1]['peak_kpa'] < rows[0]['peak_kpa'])
    g3 = dict(times=t, points=[(1.0, 2.0, 0.5)], pressures=[p])
    check('3D label',
          gs.summarize_gauges(g3)[0]['gauge'] == 'G1 (1.000, 2.000, 0.500) m',
          gs.summarize_gauges(g3)[0]['gauge'])
    # a gauge the solver had to snap says both numbers, so the snapped
    # coordinates do not read as a typo in the user's input (QA-33)
    snapped = gs.summarize_gauges(g3, requested=[(1.0, 2.0, 0.45)])[0]['gauge']
    check('a snapped gauge shows requested -> cell',
          snapped == 'G1 (1.000, 2.000, 0.450) -> cell '
                     '(1.000, 2.000, 0.500) m', snapped)
    check('an exact gauge is not cluttered with an arrow',
          '->' not in gs.summarize_gauges(
              g3, requested=[(1.0, 2.0, 0.5)])[0]['gauge'])
    check('empty gauges -> no rows', gs.summarize_gauges(dict(times=np.array([]), points=[], pressures=[])) == [])
    out = os.path.join(tempfile.mkdtemp(prefix='blastlab_gs_'), 'gauges_summary.csv')
    gs.save_gauge_summary(rows, out)
    with open(out, newline='') as f:
        lines = list(csv.reader(f))
    check('CSV header = COLUMNS', tuple(lines[0]) == gs.COLUMNS)
    check('CSV one line per gauge, peak in kPa with 1 decimal',
          len(lines) == 3 and lines[1][1] == '300.0' and lines[1][7] == 'yes', str(lines[1]))
    check('table rows are strings', all(isinstance(v, str) for v in gs.table_rows(rows)[0]))


if __name__ == '__main__':
    main()
    print()
    print('GAUGE SUMMARY: ' + ('PASS' if not FAILS else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
