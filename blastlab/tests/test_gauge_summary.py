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
          snapped == 'G1 (1.000, 2.000, 0.450) → cell '
                     '(1.000, 2.000, 0.500) m', snapped)
    check('an exact gauge is not cluttered with an arrow',
          '->' not in gs.summarize_gauges(
              g3, requested=[(1.0, 2.0, 0.5)])[0]['gauge'])
    # F42: the solver dropped the middle gauge (inside a wall); each point
    # keeps its own entered number and entered position, as the screens do
    want = [(0.83, 0.61), (1.2, 0.6), (1.53, 1.71)]
    g2 = dict(times=t, points=[(0.8263, 0.6053), (1.5316, 1.7106)],
              pressures=[p, p])
    lab = gs.gauge_labels(g2, want)
    check('a dropped gauge: labels keep the entered numbers G1, G3',
          lab[0].startswith('G1 ') and lab[1].startswith('G3 '), str(lab))
    check("a dropped gauge: G3's label carries G3's entered position",
          lab[1] == 'G3 (1.530, 1.710) → cell (1.532, 1.711) m', lab[1])
    check('a dropped gauge: G1 unchanged',
          lab[0] == 'G1 (0.830, 0.610) → cell (0.826, 0.605) m', lab[0])
    # points >= entered: the index pairing, exactly today's labels
    g4 = dict(times=t, points=[(0.8263, 0.6053), (1.2, 0.6),
                               (1.5316, 1.7106)], pressures=[p, p, p])
    check('no drop: labels as before (literal)',
          gs.gauge_labels(g4, want) == [
              'G1 (0.830, 0.610) → cell (0.826, 0.605) m',
              'G2 (1.200, 0.600) m',
              'G3 (1.530, 1.710) → cell (1.532, 1.711) m'],
          str(gs.gauge_labels(g4, want)))
    check('more points than entered: index pairing, plain extras',
          gs.gauge_labels(g4, want[:1]) == [
              'G1 (0.830, 0.610) → cell (0.826, 0.605) m',
              'G2 (1.200, 0.600) m', 'G3 (1.532, 1.711) m'],
          str(gs.gauge_labels(g4, want[:1])))
    # P1: a point no entered gauge can take -> plain labels for all
    mixed = [(0.83, 0.61, 0.0), (1.2, 0.6), (1.53, 1.71, 0.0)]
    check('pairing short of a point: plain labels for all (P1)',
          gs.gauge_labels(g2, mixed) == ['G1 (0.826, 0.605) m',
                                         'G2 (1.532, 1.711) m'],
          str(gs.gauge_labels(g2, mixed)))
    # GUI-12 A2 (verifyA Q1): G2 and G3 entered 0.4 cell apart (dx 0.1),
    # G2 dropped; G1's cell centre is nearer G3 than G1, so a greedy
    # nearest match gives the first point G3 and the survivor at G3's
    # cell G2. The solver keeps the entered order, so the pairing must be
    # an increasing subsequence: G1, G3.
    want5 = [(1.106, 0.694), (1.201, 0.69), (1.201, 0.65)]
    g5 = dict(times=t, points=[(1.15, 0.65), (1.25, 0.65)],
              pressures=[p, p])

    def greedy(pts, w):         # the pre-A2 rule, for the mutation check
        used, out = set(), []
        for pt in pts:
            j = min((j for j in range(len(w)) if j not in used),
                    key=lambda j: sum((a - b) ** 2
                                      for a, b in zip(w[j], pt)))
            used.add(j)
            out.append(j)
        return out
    check('A2 case discriminates: greedy nearest gives G3, G2',
          greedy(g5['points'], want5) == [2, 1],
          str(greedy(g5['points'], want5)))
    lab5 = gs.gauge_labels(g5, want5)
    check('A2: order-preserving pairing labels the survivor at G3\'s '
          'cell G3, not G2',
          lab5 == ['G1 (1.106, 0.694) → cell (1.150, 0.650) m',
                   'G3 (1.201, 0.650) → cell (1.250, 0.650) m'], str(lab5))
    check('A2: pair_in_order is an increasing subsequence',
          gs.pair_in_order(g5['points'], want5) == [0, 2])
    check('A2: a pair beyond tol cannot pair',
          gs.pair_in_order([(5.0, 5.0)], want5, tol=0.1) == [None])
    check('A2: ties go to the earlier entered gauge',
          gs.pair_in_order([(1.0,)], [(0.5,), (1.5,)]) == [0])
    check('empty gauges -> no rows',gs.summarize_gauges(dict(times=np.array([]), points=[], pressures=[])) == [])
    out = os.path.join(tempfile.mkdtemp(prefix='blastlab_gs_'), 'gauges_summary.csv')
    gs.save_gauge_summary(rows, out)
    with open(out, newline='') as f:
        lines = list(csv.reader(f))
    check('CSV header = COLUMNS', tuple(lines[0]) == gs.COLUMNS)
    check('CSV one line per gauge, peak in kPa with 1 decimal',
          len(lines) == 3 and lines[1][1] == '300.0' and lines[1][7] == 'yes', str(lines[1]))
    check('table rows are strings', all(isinstance(v, str) for v in gs.table_rows(rows)[0]))
    # owner Q4 (2026-10-12): `→` on screens, figures and reports; the CSV
    # keeps `->`, so its bytes stay pure ASCII
    out2 = os.path.join(os.path.dirname(out), 'snapped.csv')
    gs.save_gauge_summary(gs.summarize_gauges(g2, requested=want), out2)
    with open(out2, 'rb') as f:
        raw = f.read()
    check('Q4: the CSV writes the snapped label with -> and is ASCII',
          b'G3 (1.530, 1.710) -> cell (1.532, 1.711) m' in raw
          and raw.isascii(), raw[:160])


if __name__ == '__main__':
    main()
    print()
    print('GAUGE SUMMARY: ' + ('PASS' if not FAILS else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
