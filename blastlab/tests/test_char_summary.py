"""Characterisation: the per-gauge engineering summary (Phase 0).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 0. Feeds the gauge records
`test_char_native_api.py` pinned (read back from its npz goldens, so no
solve runs here) through `output.gauge_summary.summarize_gauges` and pins
every row exactly - labels, peak, arrival, time of peak, positive-phase
duration and impulse, net impulse, completeness - plus the display
strings of `table_rows`. Phase 6 moves the export orchestration that
calls these; the rows must not change.

Run:  cd blastlab/tests && python test_char_summary.py [--update]
      (after test_char_native_api.py, whose goldens it reads)
"""
import sys

import char_common as cc
from blastlab.output import gauge_summary                 # noqa: E402
from test_char_native_api import CASES                    # noqa: E402


def gauges_from_golden(key):
    """The Result.gauges dict rebuilt from `native_<key>_gauges.npz`."""
    arrays = cc.load_npz(f'native_{key}_gauges.npz')
    n = sum(1 for k in arrays if k.startswith('pressures_'))
    out = dict(times=arrays['times'],
               pressures=[arrays[f'pressures_{i}'] for i in range(n)])
    if 'radii' in arrays:
        out['radii'] = list(arrays['radii'])
    else:
        out['points'] = [tuple(p) for p in arrays['points']]
    return out


def characterise(key):
    case = CASES[key]
    requested = getattr(case, 'gauges', None)
    rows = gauge_summary.summarize_gauges(gauges_from_golden(key),
                                          requested=requested)
    cc.check_json(f'summary_{key}.json', dict(
        rows=rows, table=gauge_summary.table_rows(rows)))


def test_summary_1d():
    characterise('1d')


def test_summary_2d():
    characterise('2d')


def test_summary_3d():
    characterise('3d')


def main():
    return cc.run_main('CHAR SUMMARY', [
        test_summary_1d, test_summary_2d, test_summary_3d])


if __name__ == '__main__':
    sys.exit(main())
