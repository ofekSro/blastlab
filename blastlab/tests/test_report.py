"""Headless checks for the field-map CSVs (N14) and the HTML report
(N13): row counts and headers per dim, KB block present for a free-air
case and absent otherwise, images inlined, self-contained file.

Run:  cd blastlab/tests && python test_report.py
"""
import os
import sys
import tempfile

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.constants import P_AIR                      # noqa: E402
from blastlab.output import report                             # noqa: E402
from blastlab.solvers.hooks import Result                      # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def fake_res_2d(obstacles=()):
    nx, ny = 6, 4
    x_c = (np.arange(nx) + 0.5) * 0.5
    y_c = (np.arange(ny) + 0.5) * 0.5
    t = np.linspace(0, 2e-3, 60)
    trace = P_AIR + 4e5 * np.exp(-((t - 6e-4) / 2e-4) ** 2) \
        * (t > 4e-4)
    gauges = dict(times=t, points=[(1.25, 1.0)], pressures=[trace])
    snap = {'t = 1.0 ms (final)': dict(p=np.full((nx, ny), P_AIR),
                                       rho=np.full((nx, ny), 1.225),
                                       speed=np.zeros((nx, ny)))}
    meta = dict(x_c=x_c, y_c=y_c, geometry='axisymmetric',
                charge=1.0, charge_center=(0.0, 1.0),
                obstacles=list(obstacles), gauges=[(1.25, 1.0)],
                p_peak=np.full((nx, ny), 2 * P_AIR),
                impulse=np.full((nx, ny), 50.0),
                solver='blastfoam', name='report test')
    return Result(snap, gauges, meta, 'done', False)


def main():
    res = fake_res_2d()

    # ── CSVs ────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        written = report.save_field_csvs(res, 2, td, prefix='x_')
        names = dict(written)
        check('CSV: p_peak + impulse + snapshot fields written',
              {'x_p_peak.csv', 'x_impulse.csv'} <= set(names)
              and any(n.endswith('_p.csv') for n in names)
              and any(n.endswith('_rho.csv') for n in names),
              str(sorted(names)))
        check('CSV: one row per cell', set(names.values()) == {24})
        with open(os.path.join(td, 'x_p_peak.csv')) as f:
            head = f.readline().strip()
            first = f.readline().split(',')
        check('CSV: long-format header with units',
              head == 'x[m],y[m],p_peak[Pa]', head)
        check('CSV: coordinates are cell centres',
              abs(float(first[0]) - 0.25) < 1e-9
              and abs(float(first[1]) - 0.25) < 1e-9)
        n_lines = sum(1 for _ in open(os.path.join(td, 'x_impulse.csv')))
        check('CSV: header + 24 rows', n_lines == 25, str(n_lines))

    # 1D: r,value
    r = np.linspace(0.1, 2.0, 10)
    res1 = Result({}, dict(times=np.array([0.0]), radii=[1.0],
                           pressures=[np.array([P_AIR])]),
                  dict(r=r, p_peak=2 * P_AIR * np.ones(10),
                       charge_kg=1.0, solver='native'), 'done', False)
    with tempfile.TemporaryDirectory() as td:
        written = report.save_field_csvs(res1, 1, td)
        with open(os.path.join(td, 'p_peak.csv')) as f:
            head = f.readline().strip()
        check('CSV 1D: r,value header', head == 'r[m],p_peak[Pa]', head)
        check('CSV 1D: 10 rows', dict(written)['p_peak.csv'] == 10)

    # ── KB rows ─────────────────────────────────────────────────────────
    kb = report.kb_rows(res, 2)
    check('KB: free-air axisym case gets rows', len(kb) == 1
          and abs(kb[0][2] - 1.25) < 1e-9, str(kb))
    check('KB: ratio is peak over the interpolated table value',
          0.2 < kb[0][5] < 2.0, str(kb[0]))
    check('KB: obstacles suppress the block',
          report.kb_rows(fake_res_2d(obstacles=[(1, 2, 0, 1)]), 2) == [])
    check('KB: log-log interpolation between table points',
          abs(report.kb_peak_kpa(1.0) - 904.0) < 1e-9
          and 186.0 < report.kb_peak_kpa(1.7) < 350.0
          and report.kb_peak_kpa(99.0) is None)

    # ── HTML ────────────────────────────────────────────────────────────
    from matplotlib.figure import Figure
    fig = Figure(figsize=(2, 1))
    fig.subplots().plot([0, 1], [0, 1])
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, 'r.html')
        sections = report.save_html_report(
            res, 2, path, figures=[('Test figure', fig)],
            case_json='{"dim": 2, "charge": 1.0}')
        text = open(path, encoding='utf-8').read()
        check('HTML: sections written',
              {'banner', 'gauges', 'kb', 'fig:Test figure', 'case'}
              <= set(sections), str(sections))
        check('HTML: self-contained (base64 image, no file refs)',
              'data:image/png;base64,' in text
              and 'src="file' not in text and 'http' not in
              text.split('</style>')[1])
        check('HTML: KB table + case JSON present',
              'Kingery-Bulmash' in text and '&quot;charge&quot;: 1.0' in text)
        # a non-free-air case drops the KB block
        path2 = os.path.join(td, 'r2.html')
        s2 = report.save_html_report(
            fake_res_2d(obstacles=[(1, 2, 0, 1)]), 2, path2)
        check('HTML: KB block absent with obstacles', 'kb' not in s2,
              str(s2))

    print()
    if FAIL:
        print(f"REPORT: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("REPORT: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
