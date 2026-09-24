"""HD1-3d, H2: `_e2e_vent_3d.py --load` - a finished run's gauges, read
READ-ONLY (no WSL, no GUI).

A synthetic run directory stands in for the WSL run: the script's own
CFD case saved as case.json, plus a blastProbes `p` file in the layout
blastFoam 6.2 writes (postProcessing/gauges/0/p). Pinned:
  * the gauges are exactly what reader.read_probes parses - the call the
    live path's backend.finalize_3d makes - packed the way it packs them;
  * nothing under the run directory is created, modified or deleted;
  * a run whose case.json is not this script's case is refused, and so
    is a directory that cannot be read;
  * evaluate() runs on those gauges and reports every gauge, writing an
    impulse whose positive phase is still open as a LOWER BOUND.

Run:  cd blastlab/tests && python test_vent3d_load.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)

import _e2e_vent_3d as ev                                     # noqa: E402
from blastlab.core import assessment as asm                   # noqa: E402
from blastlab.core.case import save_case                      # noqa: E402
from blastlab.core.constants import P_AIR                     # noqa: E402
from blastlab.solvers.foam import env, reader                 # noqa: E402
from blastlab.solvers.hooks import Result                     # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def probes_text(points, t, cols):
    """A blastProbes scalar file as blastFoam 6.2 writes it: one
    `# Probe i (x y z)` line per probe, a `# Time` header, then rows."""
    lines = [f'# Probe {i} ({x:g} {y:g} {z:g})'
             for i, (x, y, z) in enumerate(points)]
    lines.append('#' + ''.join(f'{h:>14}' for h in
                               ['Time'] + [str(i) for i in range(len(cols))]))
    for k, tk in enumerate(t):
        lines.append(f'{tk:14.6g}' + ''.join(f'{c[k]:14.6g}' for c in cols))
    return '\n'.join(lines) + '\n'


def tree(root):
    """{relpath: (is_dir, size, mtime_ns)} of everything under root."""
    out = {}
    for dp, dn, fn in os.walk(root):
        for name in dn + fn:
            p = os.path.join(dp, name)
            st = os.stat(p)
            out[os.path.relpath(p, root)] = (os.path.isdir(p), st.st_size,
                                             st.st_mtime_ns)
    return out


def quietly(fn, *a):
    """(fn(*a), printed text) with the WSL path mapping pointed at the
    local directory - the test_foam_postmortem_decomposed idiom."""
    real = env.case_paths
    env.case_paths = lambda d: (str(d), str(d))
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            out = fn(*a)
    finally:
        env.case_paths = real
    return out, buf.getvalue()


def evaluate_quietly(case, m, res):
    """`quietly(ev.evaluate, ...)` with the script's FAIL list emptied
    before and after: evaluate() records failed checks in that module-wide
    list, and this test reads the report it prints, not its verdict."""
    del ev.FAIL[:]
    try:
        return quietly(ev.evaluate, case, m, res)
    finally:
        del ev.FAIL[:]


def main():
    case = ev.build()
    cfd, info = asm.build_vent_case(case)
    points = [tuple(g) for g in cfd.gauges]
    # gauge 1: a 20 kPa triangle peaking at 10 ms; gauge 2: 15 kPa at
    # 12 ms; gauge 3: still 12 kPa over ambient when the record ends.
    # All above gauge_summary's arrival rule (1.1 x ambient, 10.1 kPa).
    t = np.linspace(0.0, ev.WINDOW, 3001)
    cols = [P_AIR + 20e3 * np.clip(1 - np.abs(t - 0.010) / 0.004, 0, None),
            P_AIR + 15e3 * np.clip(1 - np.abs(t - 0.012) / 0.004, 0, None),
            P_AIR + np.where(t > 0.020, 12e3, 0.0)]

    with tempfile.TemporaryDirectory() as run:
        save_case(cfd, os.path.join(run, 'case.json'))
        gdir = os.path.join(run, 'postProcessing', 'gauges', '0')
        os.makedirs(gdir)
        with open(os.path.join(gdir, 'p'), 'w', encoding='ascii',
                  newline='\n') as f:
            f.write(probes_text(points, t, cols))
        before = tree(run)

        print('\nthe gauges are the live path\'s')
        res, text = quietly(ev.load_gauges, run, cfd)
        check('a run of this case loads', res is not None, text)
        if res is None:
            return
        probes = reader.read_probes(run)
        g = res.gauges
        check('the gauge dict has the live shape (p only: no U/rho files)',
              sorted(g) == ['points', 'pressures', 'times'], sorted(g))
        check('times are read_probes\' own',
              np.array_equal(g['times'], probes['times']))
        check('every pressure trace is read_probes\' own',
              len(g['pressures']) == 3
              and all(np.array_equal(a, b) for a, b in
                      zip(g['pressures'], probes['pressures'])))
        check('points are the probe header\'s, as tuples',
              g['points'] == [tuple(p) for p in probes['points']]
              == points, g['points'])
        # 6 significant digits in the file: up to 5e-6 relative
        check('and the trace is the one written, to file precision',
              np.allclose(g['pressures'][0], cols[0], rtol=1e-5))
        check('the load says it is read-only',
              'read-only' in text and 'no reconstruct' in text, text)

        print('\nevaluate() on them reports every gauge')
        rc, report = evaluate_quietly(case, info['room'], res)
        check('evaluate runs on loaded gauges', rc in (0, 1), rc)
        check('all three gauges are reported',
              all(f'G{k}' in report for k in (1, 2, 3))
              and 'reported, not judged' in report, report)
        check('a closed positive phase says so',
              report.count('positive_phase_complete True') == 2, report)
        check('an open one is written as a LOWER BOUND',
              'LOWER BOUND' in report
              and 'positive_phase_complete False' in report, report)
        # a gauge that never crosses the arrival rule gets no positive
        # phase at all - said, not printed as NaN numbers
        weak = Result({}, dict(g, pressures=[
            g['pressures'][0], g['pressures'][1],
            np.full_like(g['times'], P_AIR + 5e3)]), {})
        _rc, report2 = evaluate_quietly(case, info['room'], weak)
        check('a gauge below the arrival rule says "no arrival"',
              'no arrival' in report2
              and report2.count('positive_phase_complete') == 2, report2)

        check('nothing under the run directory was created, changed or '
              'deleted', tree(run) == before)

        print('\nrefusals')
        with open(os.path.join(run, 'case.json'), encoding='utf-8') as f:
            other = json.load(f)
        other['t_end'] = 0.031
        with open(os.path.join(run, 'case.json'), 'w',
                  encoding='utf-8') as f:
            json.dump(other, f, indent=2)
        res2, text2 = quietly(ev.load_gauges, run, cfd)
        check('a run that is not this case is refused, naming the field',
              res2 is None and 't_end' in text2, text2)
    res3, text3 = quietly(ev.load_gauges, run, cfd)     # dir now gone
    check('an unreadable run is refused, not raised',
          res3 is None and 'cannot read' in text3, text3)


if __name__ == '__main__':
    main()
    print()
    print('VENT 3D LOAD: ' + ('PASS' if not FAILS else
                              f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
