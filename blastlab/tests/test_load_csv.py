"""HD1-16 step 1: the SBEDS load CSVs (output/load_csv.py).

What is pinned, as the batch plan registered it
(docs/batches/2026-09-26-hd1-16-load-export.md, Step 2; owner format
decision 2026-09-26):
  (a) round trip: the CSV read back gives t_ms == 1e3 * t and
      p_kPa == (p - P_AIR) / 1e3 bit for bit (==, not isclose), and every
      line is exactly two floats - no header, no comment line;
  (b) the sidecar's net impulse equals numpy.trapezoid over the two
      columns read back, to 1e-12 relative;
  (c) a trace still at 5 % of its peak over its last 1 ms gets the exact
      "record ends while the load is still active: p = ... kPa at t = ...
      ms" line in its sidecar and as the returned message; one back below
      1 % gets neither;
  (d) the sidecar names the case, the trace, the load-type line and gamma;
  (e) the band path on a tiny band: `sensitivity.band` gains a 'traces'
      key with n_runs entries, low_trace / high_trace unchanged, and the
      export writes nominal.csv plus one band_<signs>.csv per non-nominal
      run.

Run:  cd blastlab/tests && python test_load_csv.py
"""

import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import deflagration as d                   # noqa: E402
from blastlab.core import sensitivity as sens                 # noqa: E402
from blastlab.core.constants import P_AIR                     # noqa: E402
from blastlab.output import load_csv as lc                    # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


def _two_floats_per_line(path):
    raw = _read(path)
    if raw.startswith(b'\xef\xbb\xbf') or b'\r' in raw:
        return False
    for line in raw.decode('ascii').split('\n')[:-1]:
        parts = line.split(',')
        if len(parts) != 2:
            return False
        try:
            float(parts[0]), float(parts[1])
        except ValueError:
            return False
    return raw.endswith(b'\n')


def _sidecar(csv_path):
    with open(os.path.splitext(csv_path)[0] + '.txt', encoding='utf-8') as f:
        return f.read().split('\n')


def test_round_trip_and_impulse(tmp):
    print('\n  (a) round trip, (b) impulse')
    prop = d.PROPELLANTS['double_base']
    r = d.simulate(prop, 5.0, 1.0, vent_area=0.02, t_end=5.0, n_out=300,
                   p0_chamber=d.P_AMB, refine_cohorts=False)
    out = dict(confined=r, prop=prop, band=None)
    res = lc.export_hd13(out, os.path.join(tmp, 'a_hd13.html'),
                         case_name='round trip')
    path = os.path.join(tmp, 'a_hd13_loads', 'nominal.csv')
    check('one CSV, nominal.csv, in <report stem>_loads/',
          res['files'] == [path] and os.path.isfile(path), str(res['files']))
    check('every line is exactly two floats, no BOM, LF only',
          _two_floats_per_line(path))
    t_ms, p_kpa = lc.read_trace(path)
    t = np.asarray(r['t'], dtype=float)
    p = np.asarray(r['p'], dtype=float)
    check('t_ms == 1e3 * t, bit for bit, every row',
          len(t_ms) == len(t) and bool(np.all(t_ms == 1e3 * t)))
    check('p_kPa == (p - P_AIR) / 1e3, bit for bit, every row',
          len(p_kpa) == len(p) and bool(np.all(p_kpa == (p - P_AIR) / 1e3)))
    side = _sidecar(path)
    line = [s for s in side if s.startswith('net impulse over the record')]
    got = float(line[0].split(': ')[1].split(' ')[0]) if line else None
    ref = float(np.trapezoid(p_kpa, t_ms))
    cum = np.concatenate([[0.0], np.cumsum(0.5 * (p_kpa[1:] + p_kpa[:-1])
                                           * np.diff(t_ms))])
    check('the sidecar net impulse equals the trapezoid of the columns read '
          'back, to 1e-12 relative',
          got is not None and abs(got - ref) <= 1e-12 * abs(ref),
          f'{got!r} vs {ref!r} kPa*ms')
    check('and the cumulative trapezoid, starting at 0, ends on it',
          cum[0] == 0.0 and abs(cum[-1] - ref) <= 1e-12 * abs(ref))


def test_still_active(tmp):
    print('\n  (c) the "still active" rule, HD1-16 2a')
    t = np.linspace(0.0, 0.1, 101)                  # 1 ms spacing
    # linear decay from 100 kPa to 5 kPa: still at 5 % of peak at the end
    p_hot = P_AIR + 1e3 * (100.0 - 95.0 * t / 0.1)
    path = os.path.join(tmp, 'hot.csv')
    t_ms, p_k = 1e3 * t, (p_hot - P_AIR) / 1e3
    msg = lc.write_trace(path, t_ms, p_k, ['case: synthetic'])
    want = (f'record ends while the load is still active: '
            f'p = {p_k[-1]:.6g} kPa at t = {t_ms[-1]:.6g} ms')
    check('a trace at 5 % of peak over its last 1 ms: the exact message',
          msg == want, repr(msg))
    check('and the exact sidecar line', want in _sidecar(path))
    check('which reads p = 5 kPa at t = 100 ms',
          want.endswith('p = 5 kPa at t = 100 ms'), want)
    # exponential decay, 10 ms: 0.005 % of peak over the last 1 ms
    p_cold = P_AIR + 1e5 * np.exp(-t / 0.01)
    path = os.path.join(tmp, 'cold.csv')
    msg = lc.write_trace(path, 1e3 * t, (p_cold - P_AIR) / 1e3, [])
    check('one back below 1 % gets no message', msg is None, repr(msg))
    check('and no sidecar line',
          not any(s.startswith('record ends while') for s in _sidecar(path)))
    # the threshold is the owner's, as named constants
    check('the rule is 1 % over 1 ms, as named constants',
          lc.LOAD_ACTIVE_FRACTION == 0.01
          and lc.LOAD_ACTIVE_WINDOW_S == 1.0e-3)


def test_sidecar_names(tmp):
    print('\n  (d) the sidecar names the case, the trace, the load, gamma')
    prop = d.PROPELLANTS['double_base']
    r = d.simulate(prop, 5.0, 1.0, vent_area=0.02, t_end=2.0, n_out=50,
                   p0_chamber=d.P_AMB, refine_cohorts=False)
    res = lc.export_hd13(dict(confined=r, prop=prop, band=None),
                         os.path.join(tmp, 'd.html'), case_name='my magazine')
    side = _sidecar(res['files'][0])
    check('case', 'case: my magazine' in side)
    check('trace', any(s.startswith('trace: nominal') for s in side))
    check('load type, neither side-on nor reflected',
          lc.LOAD_CHAMBER in side and 'not side-on, not reflected'
          in lc.LOAD_CHAMBER)
    check('gamma of the products, and that the model mixes it with air',
          any(s.startswith('gamma: 1.24 ') and 'deflagration.mixture' in s
              for s in side))
    check('the overpressure reference',
          any(s.startswith('p_ref: 101325.0 Pa') for s in side))
    check('no confined result: nothing written',
          lc.export_hd13(dict(confined=None, prop=prop, band=None),
                         os.path.join(tmp, 'none.html'))['files'] == []
          and not os.path.exists(os.path.join(tmp, 'none_loads')))


def test_band(tmp):
    print('\n  (e) the band path, on a tiny band')
    prop = d.PROPELLANTS['double_base']
    b = sens.band(prop, 5.0, 1.0, vent_area=0.02, t_end=2.0, n_out=60,
                  p0_chamber=d.P_AMB, check_corners=True)
    check("'traces' holds n_runs entries",
          len(b['traces']) == b['n_runs'], f"{len(b['traces'])} / "
          f"{b['n_runs']}")
    lo = [tr for tr in b['traces'] if tr[0] == b['low_signs']][0]
    hi = [tr for tr in b['traces'] if tr[0] == b['high_signs']][0]
    check('low_trace / high_trace are still the extreme runs, unchanged',
          b['low_trace'] == (lo[1], lo[2]) and b['high_trace']
          == (hi[1], hi[2]))
    check('exactly one nominal sample (all signs 0) in it',
          sum(1 for g, _t, _p in b['traces'] if not any(g)) == 1)
    nominal = d.simulate(prop, 5.0, 1.0, vent_area=0.02, t_end=2.0,
                         n_out=60, p0_chamber=d.P_AMB)
    out = dict(confined=nominal, prop=prop, band=b)
    report = os.path.join(tmp, 'b_hd13.html')
    # a stale band file from an earlier export must not survive
    os.makedirs(lc.loads_dir(report))
    with open(os.path.join(lc.loads_dir(report), 'band_stale.csv'), 'w'):
        pass
    res = lc.export_hd13(out, report, case_name='band')
    names = sorted(os.path.basename(f) for f in res['files'])
    band_names = [n for n in names if n.startswith('band_')]
    check('nominal.csv plus one band_<signs>.csv per non-nominal run',
          'nominal.csv' in names and len(band_names) == b['n_runs'] - 1
          and 'band_nominal.csv' not in names, str(names))
    on_disk = sorted(n for n in os.listdir(lc.loads_dir(report))
                     if n.endswith('.csv'))
    check('and nothing else on disk (the stale file is gone), each with a '
          '.txt sidecar',
          on_disk == names and all(os.path.isfile(os.path.join(
              lc.loads_dir(report), n[:-4] + '.txt')) for n in names))
    check('the band nominal equals the assessment run, so the sidecar says '
          'so and does not duplicate it',
          any('identical to this trace' in s for s in _sidecar(
              os.path.join(lc.loads_dir(report), 'nominal.csv'))))
    g = [tr for tr in b['traces'] if any(tr[0])][0]
    name = 'band_' + ''.join(f'{s:+d}' for s in g[0]) + '.csv'
    path = os.path.join(lc.loads_dir(report), name)
    t_ms, p_kpa = lc.read_trace(path)
    check(f'{name} round-trips its sample bit for bit',
          bool(np.all(t_ms == 1e3 * np.asarray(g[1], dtype=float)))
          and bool(np.all(p_kpa == (np.asarray(g[2], dtype=float) - P_AIR)
                          / 1e3)))
    check('and its sidecar names the signs',
          any(s.startswith('trace: sensitivity-band sample') and
              s.endswith(name[5:-4]) for s in _sidecar(path)))
    # a band whose nominal differs from the assessment run is written
    other = dict(nominal, p=list(np.asarray(nominal['p']) + 1.0))
    res = lc.export_hd13(dict(confined=other, prop=prop, band=b), report)
    check('a band nominal that differs is written as band_nominal.csv',
          any(f.endswith('band_nominal.csv') for f in res['files']))


def main():
    print('LOAD CSV (HD1-16)')
    tmp = tempfile.mkdtemp(prefix='blastlab_load_csv_')
    try:
        test_round_trip_and_impulse(tmp)
        test_still_active(tmp)
        test_sidecar_names(tmp)
        test_band(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nLOAD CSV: {'PASS' if not FAIL else f'FAIL ({len(FAIL)})'}")
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
