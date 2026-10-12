"""GUI-16 (b): the 1D exports keep the entered gauge numbers and name the
drop (no WSL; one offscreen Qt import, no window).

A 1D result whose solver dropped G2 of three entered radii has two
series, G1 and G3. With the numbers (`gauge_summary.numbers_1d`, fed by
Qt through `opts['gauge_numbers']`) the gauge figure titles its panels
`Gauge 1` / `Gauge 3` and names G2 in a footnote, the summary rows and
the HTML report's tables read G1 / G3; without them every builder gives
exactly today's titles and labels.

Run:  cd blastlab/tests && python test_export_numbers_1d.py
"""
import os
import sys
import tempfile
import types

import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.models.result import Result                       # noqa: E402
from blastlab.output import gauge_summary, plots, report        # noqa: E402
from blastlab.services import exports                           # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def result(drop=True):
    """Entered radii 0.5, 9.0 (beyond the 2 m domain: dropped), 1.5 m;
    the two series the solver kept. A short positive pulse each."""
    t = np.linspace(0.0, 2e-3, 80)
    pulse = [P_AIR + 5e4 * np.exp(-((t - c) / 2e-4) ** 2)
             for c in (4e-4, 1.2e-3)]
    meta = dict(radius_m=2.0, charge_kg=1.0, eos='JWL', r_exp=0.05)
    if drop:
        meta['gauges_dropped'] = [[2, 'outside the domain']]
    return Result({}, dict(times=t, radii=[0.5, 1.5], pressures=pulse),
                  meta, 'end time reached')


def titles(fig):
    return [ax.get_title() for ax in fig.axes if ax.get_visible()]


def footnote(fig):
    lab = getattr(fig, '_supxlabel', None)
    return None if lab is None else lab.get_text()


def main():
    res = result()
    nums = gauge_summary.numbers_1d(2, [2])
    check('numbers_1d(2 series, G2 dropped) is [1, 3]', nums == [1, 3],
          str(nums))

    print('\nthe gauge figure')
    fig = plots.figure_gauges_1d(res.gauges, 1.0, 'JWL', numbers=nums)
    got = titles(fig)
    check('panel titles Gauge 1, Gauge 3',
          [s.split('  ')[0] for s in got] == ['Gauge 1', 'Gauge 3'],
          str(got))
    check('the footnote names G2', 'G2' in (footnote(fig) or ''),
          str(footnote(fig)))
    fig = plots.figure_gauges_1d(res.gauges, 1.0, 'JWL', numbers=nums,
                                 drop_note='G2 dropped by the solver '
                                           '(outside the domain)')
    check('a passed note is the footnote',
          footnote(fig) == 'G2 dropped by the solver (outside the domain)')
    fig = plots.figure_gauges_1d(res.gauges, 1.0, 'JWL')
    check('numbers=None: today\'s titles exactly, no footnote',
          titles(fig) == ['Gauge 1  (r = 0.50 m)', 'Gauge 2  (r = 1.50 m)']
          and footnote(fig) is None and len(fig.texts) == 1,
          f'{titles(fig)} {footnote(fig)}')

    print('\nthe summary rows')
    rows = gauge_summary.summarize_gauges(res.gauges, numbers=nums)
    check('rows G1, G3', [r['gauge'] for r in rows]
          == ['G1  r = 0.500 m', 'G3  r = 1.500 m'],
          str([r['gauge'] for r in rows]))
    rows = gauge_summary.summarize_gauges(res.gauges)
    check('numbers=None: G1, G2 as today', [r['gauge'] for r in rows]
          == ['G1  r = 0.500 m', 'G2  r = 1.500 m'])
    check('services summary_rows takes the opts',
          [r['gauge'] for r in exports.summary_rows(
              res, dict(gauge_numbers=nums))][1].startswith('G3')
          and exports.summary_rows(res)[1]['gauge'].startswith('G2'))

    print('\nthe HTML report and the exports')
    with tempfile.TemporaryDirectory(prefix='blastlab_num1d_') as tmp:
        path = os.path.join(tmp, 'r.html')
        report.save_html_report(res, 1, path, numbers=nums)
        with open(path, encoding='utf-8') as f:
            html = f.read()
        check('the report\'s tables name G3, not G2',
              '<td>G3  r = 1.500 m</td>' in html
              and 'G2  r =' not in html, html[:200])
        kb = report.kb_rows(res, 1, nums)
        check('kb_rows label the KB comparison G1, G3',
              [r[0].split()[0] for r in kb] == ['G1', 'G3'], str(kb))
        ent = types.SimpleNamespace(label='x', display='x', dim=1,
                                    result=res)
        target = os.path.join(tmp, 's.csv')
        exports.run_export('summary', ent, target,
                           opts=dict(gauge_numbers=nums), log=lambda s: None)
        with open(target, encoding='utf-8') as f:
            csv_text = f.read()
        check('run_export summary: the CSV names G1 and G3',
              'G1  r = 0.500 m' in csv_text and 'G3  r = 1.500 m' in csv_text)
        figs = dict(exports.png_figures(res, 1, numbers=nums))
        check('png_figures: the 1D gauge figure carries the numbers',
              titles(figs['blast_1d_gauges.png'])[1].startswith('Gauge 3'))

    print('\nthe Qt side feeds them (ui/results_gauges, ui/exports)')
    from blastlab.ui import exports as ui_exports
    from blastlab.ui import results_gauges as RG
    check('export_numbers: [1, 3] for the stamped 1D result, None '
          'without a stamp or in 2D',
          RG.export_numbers(res, 1) == [1, 3]
          and RG.export_numbers(result(drop=False), 1) is None
          and RG.export_numbers(res, 2) is None)
    check('export_drop_note serves dim 1',
          RG.export_drop_note(res, 1)
          == 'G2 dropped by the solver (outside the domain)'
          and RG.export_drop_note(result(drop=False), 1) == '')
    seen = []
    real_pick, real_run = ui_exports.pick_target, ui_exports.run_export
    ui_exports.pick_target = lambda *a, **k: 'target'
    ui_exports.run_export = lambda *args: seen.append((args[0], args[3]))
    try:
        ent = types.SimpleNamespace(label='x', display='x', dim=1,
                                    result=res)
        for kind in ('summary', 'pngs', 'tsv'):
            ui_exports.export(kind, ent, threaded=False)
    finally:
        ui_exports.pick_target, ui_exports.run_export = real_pick, real_run
    opts = dict(seen)
    check('Qt export: summary and pngs get gauge_numbers, tsv nothing',
          opts['summary'] == dict(gauge_numbers=[1, 3])
          and opts['pngs']['gauge_numbers'] == [1, 3]
          and 'G2' in opts['pngs']['gauge_drop_note']
          and opts['tsv'] is None, str(opts))
    lab, dropped = RG.labels_and_dropped(res, 1)
    check('labels_and_dropped numbers the screen by the same rule',
          lab == {1: 'G1', 2: 'G3'} and dropped == [(2, 'outside the '
                                                       'domain')],
          f'{lab} {dropped}')


if __name__ == '__main__':
    main()
    print()
    print('EXPORT NUMBERS 1D: ' + ('PASS' if not FAILS else
                                   f'FAIL ({len(FAILS)}): '
                                   + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
