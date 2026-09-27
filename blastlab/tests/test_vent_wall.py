"""HD1-13: `_e2e_vent_wall.py`, the wall load re-evaluated from a finished
run's files - pinned on a SYNTHETIC evidence copy (no WSL, no GUI).

A temporary directory stands in for the evidence copy: the script's own
CFD case saved as case.json, blastProbes p/U/rho files in the layout
blastFoam 6.2 writes, and a SHA256SUMS.source that vouches for them.
Pinned:
  * E is `core/wallload.wall_load` on the probes' own arrays, nothing
    else;
  * the example panel's T0 and T1 are built as the rule says (T1 holds
    max(p_open - P_AIR, max E) for 1.5 Tn at the record's last gap);
  * one changed byte in U is refused on sha256, and a changed case field
    is refused with the field named;
  * nothing under the evidence directory is created, changed or deleted;
  * P2 on a velocity rising linearly over 5 ms measures a 4.0 ms rise,
    and P3 gives the expected ratio on a synthetic 0-D record;
  * the outcome function maps every combination of the rule's four
    conditions to BOUND or NOT ESTABLISHED exactly as the rule's table
    says, first match winning, and takes nothing else;
  * the delivered trace names its units and reads back to the same R, S
    and E, bit for bit.

Run:  cd blastlab/tests && python test_vent_wall.py
"""
import contextlib
import hashlib
import inspect
import io
import itertools
import json
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)

import _e2e_vent_wall as ew                                    # noqa: E402
from blastlab.core import assessment as asm                    # noqa: E402
from blastlab.core import sdof, wallload as wl                 # noqa: E402
from blastlab.core.case import save_case                       # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402
from blastlab.solvers.foam import reader                       # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


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


def quietly(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = fn(*a, **kw)
    return out, buf.getvalue()


# ── a synthetic evidence copy ──────────────────────────────────────────

def scalar_text(points, t, cols):
    lines = [f'# Probe {i} ({x:g} {y:g} {z:g})'
             for i, (x, y, z) in enumerate(points)]
    lines.append('#' + ''.join(f'{h:>14}' for h in
                               ['Time'] + [str(i) for i in range(len(cols))]))
    for k, tk in enumerate(t):
        lines.append(f'{tk:14.6g}' + ''.join(f'{c[k]:14.6g}' for c in cols))
    return '\n'.join(lines) + '\n'


def vector_text(points, t, vecs):
    lines = [f'# Probe {i} ({x:g} {y:g} {z:g})'
             for i, (x, y, z) in enumerate(points)]
    lines.append('#' + ''.join(f'{h:>14}' for h in
                               ['Time'] + [str(i) for i in range(len(vecs))]))
    for k, tk in enumerate(t):
        lines.append(f'{tk:14.6g}' + ''.join(
            f'             ({v[k, 0]:.6g} {v[k, 1]:.6g} {v[k, 2]:.6g})'
            for v in vecs))
    return '\n'.join(lines) + '\n'


def synthetic_signals():
    """t, and per probe p, U (n, 3), rho: a front at 10 ms, then a jet
    along +x that rises over 4 ms and blows until the record ends."""
    t = np.linspace(0.0, 0.030, 3001)
    front = np.clip(1.0 - np.abs(t - 0.012) / 0.004, 0.0, None)
    jet = np.clip((t - 0.014) / 0.004, 0.0, 1.0)
    ps, Us, rhos = [], [], []
    for amp, u, side in ((30e3, 450.0, 20.0), (20e3, 150.0, -60.0),
                         (18e3, 200.0, 10.0)):
        p = P_AIR + amp * front - 15e3 * jet
        U = np.stack([u * jet - 40.0 * front, side * jet,
                      -5.0 * jet], axis=1)
        ps.append(p)
        Us.append(U)
        rhos.append(1.225 * (p / P_AIR) ** (1.0 / 1.4))
    return t, ps, Us, rhos


def write_sums(root):
    """A SHA256SUMS.source vouching for the evidence files as they are."""
    lines = []
    for rel in ew.EVIDENCE_FILES:
        with open(os.path.join(root, *rel.split('/')), 'rb') as f:
            lines.append(f'{hashlib.sha256(f.read()).hexdigest()}  {rel}')
    with open(os.path.join(root, 'SHA256SUMS.source'), 'w',
              encoding='ascii', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


def make_evidence(root, cfd):
    save_case(cfd, os.path.join(root, 'case.json'))
    gdir = os.path.join(root, 'postProcessing', 'gauges', '0')
    os.makedirs(gdir)
    pts = [tuple(g) for g in cfd.gauges]
    t, ps, Us, rhos = synthetic_signals()
    for name, text in (('p', scalar_text(pts, t, ps)),
                       ('rho', scalar_text(pts, t, rhos)),
                       ('U', vector_text(pts, t, Us))):
        with open(os.path.join(gdir, name), 'w', encoding='ascii',
                  newline='\n') as f:
            f.write(text)
    write_sums(root)


# ── the checks ─────────────────────────────────────────────────────────

def _check_evidence(case, cfd, info):
    print('\nthe evidence: sha256, identity, read-only')
    comp = ew.component(case)
    with tempfile.TemporaryDirectory() as ev:
        make_evidence(ev, cfd)
        before = tree(ev)
        probes, text = quietly(ew.load_evidence, ev, cfd)
        check('a matching evidence copy loads', probes is not None, text)
        if probes is None:
            return
        check('every file is vouched for by SHA256SUMS.source',
              text.count('matches SHA256SUMS.source') == 4, text)
        check('and case.json equals the CFD case key for key',
              'equals this CFD case' in text, text)
        raw = reader.read_probes(ev)
        t = raw['times']
        for g in ew.GAMMAS:
            for k in range(3):
                got = ew.gauge_load(probes, k, g)
                want = wl.wall_load(t, raw['pressures'][k],
                                    raw['velocities'][k], raw['rhos'][k], g,
                                    normal=(1.0, 0.0, 0.0))
                ok = all(np.array_equal(got[q], want[q])
                         for q in ('E', 'R', 'S', 'M', 'un'))
                check(f'E at probe {k + 1}, gamma {g}, is wall_load on the '
                      f'probe\'s own p, U, rho', ok)
        # the whole of Step 1 runs on it and leaves the copy untouched
        res1, text1 = quietly(ew.step1, info, probes, comp)
        check('Step 1 runs end to end and states both premises',
              'P2 (' in text1 and 'P3 (' in text1
              and "STEP 1's OUTCOME" in text1, text1[-600:])
        check('every trace is reported with both tails and both gammas',
              text1.count('T0: mu') == 6 and text1.count('T1 (E_tail') == 6,
              text1[:800])
        with tempfile.TemporaryDirectory() as dl, \
                tempfile.TemporaryDirectory() as out:
            paths, _t = quietly(ew.deliver_traces, res1, probes, 'f' * 64,
                                'test status', dl, out)
            check('the delivered G1 trace, and with --out the G1..G3 '
                  'traces, land where they were sent',
                  len(paths) == 4 and paths[0].startswith(dl)
                  and all(p.startswith(out) for p in paths[1:])
                  and all(os.path.isfile(p) for p in paths), str(paths))
            head, units, cols = ew.read_table(paths[0])
            L = res1['loads']['G1']
            check('the delivered trace names its units in a header line',
                  units is not None and 't [s]' in units
                  and 'un [m/s]' in units
                  and 'E_1.24 [Pa over P_AIR]' in units
                  and 'M_1.40 [-]' in units, str(units))
            check('and reads back to the same R, S, E (bit for bit), both '
                  'gammas',
                  all(np.array_equal(cols[f'{q}_{g:.2f}'], L[g][q])
                      for g in ew.GAMMAS for q in ('R', 'S', 'E', 'M'))
                  and np.array_equal(cols['t'], res1['t'])
                  and np.array_equal(cols['un'], L[1.24]['un']))
            check('the header states the T1 rule and the status',
                  any(h.startswith('T1 (a rule, not baked in') for h in head)
                  and 'status: test status' in head, str(head))
        check('nothing under the evidence copy was created, changed or '
              'deleted', tree(ev) == before)

        # one changed byte in U: refused on sha256
        upath = os.path.join(ev, 'postProcessing', 'gauges', '0', 'U')
        with open(upath, 'rb') as f:
            data = bytearray(f.read())
        i = data.index(b'(', data.index(b'Time'))    # the first vector
        data[i + 1] = ord('9') if data[i + 1] != ord('9') else ord('8')
        with open(upath, 'wb') as f:
            f.write(bytes(data))
        res, text = quietly(ew.load_evidence, ev, cfd)
        check('one changed byte in U is refused on sha256',
              res is None and 'DOES NOT MATCH' in text
              and 'gauges/0/U' in text.split('DOES NOT MATCH')[0]
              .splitlines()[-1], text)

        # a changed case field, re-vouched so only the identity can fail
        cpath = os.path.join(ev, 'case.json')
        with open(cpath, encoding='utf-8') as f:
            other = json.load(f)
        other['t_end'] = 0.031
        with open(cpath, 'w', encoding='utf-8') as f:
            json.dump(other, f, indent=2)
        write_sums(ev)
        res, text = quietly(ew.load_evidence, ev, cfd)
        check('a changed case field is refused, naming the field',
              res is None and 't_end' in text and 'not this script' in text,
              text)
    res, text = quietly(ew.load_evidence, ev, cfd)      # the dir is gone
    check('a missing evidence copy is refused, not raised',
          res is None and 'REFUSED' in text, text)


def _check_tails(case):
    print('\nthe example panel\'s two tails, as the rule builds them')
    comp = ew.component(case)
    t = np.concatenate([np.linspace(0.0, 0.008, 801),
                        0.008 + 8.265e-5 * np.arange(1, 267)])
    E = 60e3 * np.clip(1 - np.abs(t - 0.02) / 0.006, 0, None)
    for p_open, what in ((P_AIR + 205e3, 'the chamber pressure'),
                         (P_AIR + 20e3, 'the record\'s own maximum')):
        rs = ew.responses(t, E, comp, p_open)
        want = max(p_open - P_AIR, E.max())
        check(f'T1 holds max(p_open - P_AIR, max E) - here {what}',
              rs['level'] == want, f"{rs['level']} vs {want}")
        t1, E1 = wl.extend_with_tail(t, E, want, 1.5 * comp.Tn)
        check('T1 is the record plus that level for 1.5 Tn, at the last gap',
              np.array_equal(rs['t1'], t1) and np.array_equal(rs['E1'], E1))
        r0 = sdof.response(t, E, comp, p_ref=0.0)
        r1 = sdof.response(t1, E1, comp, p_ref=0.0)
        check('T0 is sdof.response on the record, p_ref = 0 (zero after)',
              rs['T0'].y_max == r0.y_max and rs['T0'].regime == r0.regime)
        check('T1 is sdof.response on the extended record, p_ref = 0',
              rs['T1'].y_max == r1.y_max)
        check('and both step at the same dt',
              rs['T0'].times[1] - rs['T0'].times[0]
              == rs['T1'].times[1] - rs['T1'].times[0])
    # the C10 control is exactly C10's call
    p = P_AIR + E
    ok, r = ew.c10_control(t, p, comp)
    r_ref = sdof.response(t, p, comp, p_ref=P_AIR)
    check('the C10 control is sdof.response(t, p, comp, p_ref=P_AIR)',
          r.y_max == r_ref.y_max)
    check('and it does not pass on a trace that is not C10\'s', not ok,
          f'mu {r.ductility:.4f}')
    ref = ew.ufc_reference(comp)
    check('the UFC reference rotations map to mu 3.93 / 11.82 / 23.91',
          [f'{mu:.2f}' for _th, mu in ref] == ['3.93', '11.82', '23.91'],
          str(ref))


def test_premises():
    print('\nthe premises')
    k = np.arange(101)
    t = 1e-4 * k
    u = np.minimum(100.0 * k, 5000.0)       # rises linearly over 5 ms
    p = np.full_like(t, P_AIR)
    rho = np.full_like(t, 1.225)
    r = ew.premise_p2(t, u, p, rho, 1.2)
    check('P2: a velocity rising linearly over 5 ms rises 10 %->90 % in '
          '4.0 ms', abs(r['rise'] - 4.0e-3) < 1e-12,
          f"{r['rise']!r}")
    a = np.sqrt(1.24 * P_AIR / 1.225)
    check('P2 compares it with D / sqrt(1.24 p / rho) at t90',
          abs(r['need'] - 1.2 / a) < 1e-15 and r['ok'] is True,
          f"{r['need']!r}")
    fast = np.minimum(250.0 * k, 5000.0)    # the same rise in 2 ms
    r2 = ew.premise_p2(t, fast, p, rho, 1.2)
    check('P2 fails on a rise shorter than D / a',
          r2['ok'] is False and abs(r2['rise'] - 1.6e-3) < 1e-12,
          f"{r2['rise']!r}")
    high = np.full_like(t, 3000.0)
    r3 = ew.premise_p2(t, high, p, rho, 1.2)
    check('P2 fails when the rise is never seen (no t10)',
          r3['ok'] is False and r3['i10'] is None)

    zd = {'t': [0.0, 1.0, 2.0, 3.0, 4.0],
          'p': [1.0e5, 1.1e5, 1.3e5, 1.6e5, 2.0e5]}
    r = ew.premise_p3(zd, 2.0, 3.0e5, 0.15)
    want = 3.0e4 / ((3.0e5 - P_AIR) / 0.15)
    check('P3: the larger one-sided rise rate at t_open over '
          '(p_open - P_AIR)/tau_drain', abs(r['ratio'] - want) < 1e-15
          and r['rate'] == 3.0e4 and r['back'] == 2.0e4 and r['ok'],
          f"{r['ratio']!r} vs {want!r}")
    r = ew.premise_p3(zd, 2.0, 3.0e5, 10.0)
    check('P3 fails when the chamber can rise faster than it drains',
          r['ok'] is False and r['ratio'] > 1.0, f"{r['ratio']!r}")


def test_outcome():
    print('\nthe outcome function')
    params = list(inspect.signature(ew.outcome).parameters)
    check('it takes the rule\'s four conditions and nothing else',
          params == ['p2_holds', 'p3_holds', 'step2_trusted',
                     'step2_read_only'], str(params))
    bad = []
    for combo in itertools.product((True, False), repeat=4):
        p2, p3, trusted, read_only = combo
        label, why = ew.outcome(*combo)
        line = ew.outcome_line(*combo)
        want = ew.BOUND if all(combo) else ew.NOT_ESTABLISHED
        named = {'P2 fails': not p2, 'P3 fails': not p3,
                 'Step 2 cannot be run read-only': not read_only,
                 'Step 2 is untrusted (mapping check)':
                     read_only and not trusted}
        ok = (label == want
              and line.startswith(f'HD1-13 ROUTE (b): {want} - ')
              and all((c in why) == v for c, v in named.items())
              and (label == ew.BOUND) == (why == [
                  'P2 and P3 hold and Step 2 is trusted']))
        if not ok:
            bad.append((combo, label, why))
    check('all 16 combinations map as the rule\'s table says', not bad,
          str(bad))
    check('a failed premise is NOT ESTABLISHED whatever Step 2 finds',
          ew.step1_status(False, True).startswith(ew.NOT_ESTABLISHED)
          and ew.step1_status(True, True).startswith('P2 and P3 hold'))


def test_refusals():
    print('\nthe outputs stay outside the evidence copy and WSL')
    ev = ew.DEFAULT_EVIDENCE
    check('a path inside the evidence copy is refused',
          not ew._outside(os.path.join(ev, 'x.txt'), ev))
    check('a WSL path is refused',
          not ew._outside(r'\\wsl.localhost\Ubuntu\root\x', ev))
    check('the repo docs/hd13 is allowed', ew._outside(ew.DELIVER, ev))
    rc, text = quietly(ew.main, ['--evidence', ev, '--deliver',
                                 os.path.join(ev, 'out')])
    check('main refuses before reading anything', rc == 2
          and 'refused' in text, text)


# ── Step 2 (A3): the plane, on synthetic arrays and a tiny fake run ─────

def test_plane_parts():
    print('\nStep 2: layers, the plane maximum, the panel means')
    xc = (np.arange(120) + 0.5) * 0.1            # the run's own x centres
    i_lo, i_hi = ew.bracket(xc, 10.0)
    check('the layers either side of x = 10 m come from x_c: 9.95, 10.05',
          (i_lo, i_hi) == (99, 100)
          and abs(xc[i_lo] - 9.95) < 1e-9 and abs(xc[i_hi] - 10.05) < 1e-9,
          f'{i_lo}, {i_hi}')
    check('and a y/z bracket the same way (6.0 -> 5.95 | 6.05)',
          ew.bracket(xc, 6.0) == (59, 60))
    for bad in (0.01, 12.5):
        try:
            ew.bracket(xc, bad)
            check(f'{bad} outside the centres is refused', False)
        except ValueError:
            check(f'{bad} outside the centres is refused', True)

    xs, ys, zs = np.array([9.95, 10.05]), np.arange(5.0), np.arange(3.0)
    E = np.zeros((2, 5, 3))
    E[1, 3, 2] = 7.0
    E[0, 1, 1] = np.nan                           # NaN cells are skipped
    v, where, ijk = ew.plane_max(E, xs, ys, zs)
    check('the plane maximum and where it sits',
          v == 7.0 and where == (10.05, 3.0, 2.0) and ijk == (1, 3, 2),
          f'{v}, {where}, {ijk}')

    ys = np.array([4.0, 5.0, 5.95, 6.05, 7.4, 8.0])
    zs = np.array([0.5, 2.5, 3.5])
    shape = (2, len(ys), len(zs))
    Eg = np.broadcast_to(1000.0 * ys[None, :, None], shape).copy()
    p = np.full(shape, P_AIR + 2000.0)
    rho = np.full(shape, 2.0)
    U = np.zeros(shape + (3,))
    U[..., 0] = np.array([10.0, -5.0, 10.0])[None, None, :]
    U[..., 1] = 300.0                             # along the wall: no load
    got = ew.panel_numbers(p, rho, U, {1.24: Eg, 1.4: 2 * Eg}, ys, zs,
                           (2, 3))
    check('panel area mean of E over y 4.5-7.5, z 0-3, both layers',
          abs(got[('E', 1.24)] - 6100.0) < 1e-9
          and abs(got[('E', 1.4)] - 12200.0) < 1e-9, str(got))
    check('strip mean of E at the two y columns around 6 m',
          abs(got[('strip', 1.24)] - 6000.0) < 1e-9, str(got))
    check('area mean of max(0, p - P_AIR + rho un^2), un = max(Ux, 0)',
          abs(got['momentum'] - 2100.0) < 1e-9, str(got))
    p2 = p.copy()
    p2[:, :, 1] = P_AIR - 3000.0                  # suction, un = 0 there
    got2 = ew.panel_numbers(p2, rho, U, {1.24: Eg}, ys, zs, (2, 3))
    check('suction contributes zero momentum flux, not a negative one',
          abs(got2['momentum'] - 1100.0) < 1e-9, str(got2))

    check('ps lines are matched by exact command name',
          ew.parse_ps('  12 blastFoam\n  13 bash\n  14 mpirun\n'
                      '  15 postProcessX\n') == ['12 blastFoam', '14 mpirun'])
    check('fingerprint lines are parsed, anything else ignored',
          ew.parse_fp('FP|du_sb|123\nnoise\nFP|sha256 case.json|ab|c\n')
          == {'du_sb': '123', 'sha256 case.json': 'ab|c'})


def test_mapping():
    print('\nStep 2: the mapping check')
    rng = np.random.default_rng(3)
    wt = np.array([0.005, 0.009, 0.010, 0.011])
    cells = np.empty((4, 8, 5))
    for c in range(8):
        cells[:, c, 0] = P_AIR + 1e3 * (c + 1) + 5e3 * rng.random(4)
        cells[:, c, 1] = 1.0 + 0.1 * c + 0.01 * rng.random(4)
        cells[:, c, 2:5] = 300.0 * rng.random((4, 3)) - 100.0
    elected = 5
    # the probe prints 6 significant digits and its times with 6 as well;
    # its rows are the solver steps, the writes a subset of them
    pt = np.sort(np.concatenate([wt, wt + 3e-6, wt - 4e-6]))
    six = np.vectorize(lambda v: float(f'{v:.6g}'))
    pt_printed = six(pt)
    P = np.full(len(pt), P_AIR)
    R = np.full(len(pt), 1.2)
    V = np.zeros((len(pt), 3))
    for w, tw in enumerate(wt):
        j = int(np.argmin(np.abs(pt - tw)))
        P[j], R[j] = six(cells[w, elected, 0]), six(cells[w, elected, 1])
        V[j] = six(cells[w, elected, 2:5])
    m = ew.mapping_check(wt, cells, pt_printed, P, R, V, t_min=0.008,
                         expected_n=3)
    check('the elected cell matches at every write after 8 ms, printed to '
          '6 digits', m['trusted'] and m['matched'] == elected
          and m['n'] == 3, str(m))
    check('and no other cell does',
          [d['ok'] for d in m['cells']] == [c == elected for c in range(8)])
    check('writes up to 8 ms are not compared', m['n'] == 3)
    m = ew.mapping_check(wt, cells, pt_printed, P, R, V, t_min=0.008,
                         expected_n=267)
    check('a count other than the rule\'s is not trusted, even matched',
          not m['trusted'] and m['matched'] == elected)
    for q, what in ((0, 'p'), (1, 'rho'), (2, 'U')):
        bad = cells.copy()
        scale = (np.sqrt((cells[2, elected, 2:5] ** 2).sum()) + 1.0
                 if q == 2 else abs(cells[2, elected, q]))
        bad[2, elected, q] += 2e-5 * scale
        m = ew.mapping_check(wt, bad, pt_printed, P, R, V, t_min=0.008,
                             expected_n=3)
        check(f'2e-5 off in {what} at one write fails the check',
              not m['trusted'] and m['matched'] is None, str(m['cells']))


def field_text(name, vals, vector=False):
    cls = 'volVectorField' if vector else 'volScalarField'
    kind = 'vector' if vector else 'scalar'
    rows = (['(' + ' '.join(repr(float(c)) for c in v) + ')' for v in vals]
            if vector else [repr(float(v)) for v in vals])
    return ('FoamFile { format ascii; class ' + cls + '; object ' + name
            + '; }\ndimensions [0 0 0 0 0 0 0];\n'
            'internalField   nonuniform List<' + kind + '>\n'
            + f'{len(vals)}\n(\n' + '\n'.join(rows) + '\n)\n;\n'
            'boundaryField { }\n')


def writer_start_files(values):
    """The start time's files exactly as blastlab's writer frames them
    (`writer._render_fields` over `writer._nonuniform`) - the list closed
    by ');' on one line. `values`: {name: (field kind, list, is_vector)}."""
    from types import SimpleNamespace
    from blastlab.solvers.foam import writer
    spec = SimpleNamespace(patches=[('x_lo', 'transmit')], l_inf=1.0)
    fields = {f'0/{name}': (name, kind,
                            writer._nonuniform(vals, vector=vec), vec)
              for name, (kind, vals, vec) in values.items()}
    return {rel[2:]: text for rel, text in
            writer._render_fields(fields, spec).items()}


def make_run(root, spec, times, field):
    """Time dirs holding p, U and rho in F order (x fastest), as the
    solver writes them; the start time holds p, U, alpha.expl, rho.expl
    and rho.air in the WRITER's framing and no rho, as the run's 0/ does."""
    nx, ny, nz = spec.nx, spec.ny, spec.nz
    order = [(i, j, k) for k in range(nz) for j in range(ny)
             for i in range(nx)]
    for tv, name in times:
        d = os.path.join(root, name)
        os.makedirs(d)
        p, rho, U = field(tv)
        if tv == 0.0:
            n = len(order)
            files = writer_start_files({
                'p': ('p', [p[c] for c in order], False),
                'U': ('U', [U[c] for c in order], True),
                'alpha.expl': ('alpha', [0.25] * n, False),
                'rho.expl': ('rho', [2.0] * n, False),
                'rho.air': ('rho', [1.2] * n, False)})
        else:
            files = {'p': field_text('p', [p[c] for c in order]),
                     'U': field_text('U', [U[c] for c in order],
                                     vector=True),
                     'rho': field_text('rho', [rho[c] for c in order])}
        for fname, text in files.items():
            with open(os.path.join(d, fname), 'w', encoding='ascii',
                      newline='\n') as f:
                f.write(text)


def test_start_reader():
    print("\nthe start time, as blastlab's writer frames it")
    files = writer_start_files({
        'p': ('p', [101325.0, 2.0e5, 3.5e5], False),
        'U': ('U', [(1.0, 2.0, 3.0), (0.0, 0.0, 0.0), (-4.0, 5.0, 6.5)],
              True)})
    check('the writer closes the list with ");" on one line',
          '\n);\n' in files['p'] and '\n);\n' in files['U'])
    with tempfile.TemporaryDirectory() as d:
        paths = {}
        for name, text in files.items():
            paths[name] = os.path.join(d, name)
            with open(paths[name], 'w', encoding='ascii', newline='\n') as f:
                f.write(text)
        # P1-7 (owner decision 2026-09-25): this check used to pin the
        # reader REFUSING the writer's ');' ("reader alone refuses it - the
        # mismatch Step 2 works around"). The decision fixes the reader, so
        # the expectation flips; every other check here is unchanged.
        try:
            got = reader.read_scalar(paths['p'], 3)
            err = ''
        except ValueError as exc:
            got, err = None, str(exc)
        check('reader reads the writer\'s ");" framing itself',
              got is not None
              and np.array_equal(got, [101325.0, 2.0e5, 3.5e5]), err)
        check('read_start reads the scalars',
              np.array_equal(ew.read_start(paths['p'], 3),
                             [101325.0, 2.0e5, 3.5e5]))
        check('and the vectors',
              np.array_equal(ew.read_start(paths['U'], 3, vector=True),
                             [[1.0, 2.0, 3.0], [0.0, 0.0, 0.0],
                              [-4.0, 5.0, 6.5]]))
        for what, n, mangle in (
                ('a count that is not the mesh\'s', 4, None),
                ('a torn file (no closing line)', 3,
                 lambda s: s[:s.index('\n);\n')])):
            path = paths['p']
            if mangle:
                path = os.path.join(d, 'torn')
                with open(path, 'w', encoding='ascii', newline='\n') as f:
                    f.write(mangle(files['p']))
            try:
                ew.read_start(path, n)
                check(f'{what} is still refused', False)
            except ValueError:
                check(f'{what} is still refused', True)
        of = os.path.join(d, 'of')
        with open(of, 'w', encoding='ascii', newline='\n') as f:
            f.write(field_text('p', [1.0, 2.0, 3.0]))
        check('an OpenFOAM-framed file goes through reader itself',
              np.array_equal(ew.read_start(of, 3),
                             reader.read_scalar(of, 3)))


def _check_step2_driver(case):
    print('\nStep 2 end to end on a tiny fake run (no WSL)')
    from types import SimpleNamespace
    from blastlab.solvers.foam import env
    xs = np.array([9.85, 9.95, 10.05, 10.15])
    ys = np.array([4.95, 5.95, 6.05, 7.05])
    zs = np.array([1.35, 1.45, 2.5])
    spec = SimpleNamespace(dim=3, nx=4, ny=4, nz=3, n_cells=48, solid=None,
                           remap=None, grid=dict(x_c=xs, y_c=ys, z_c=zs))
    times = [(0.0, '0'), (0.004, '0.004'), (0.009, '0.009'),
             (0.012, '0.012')]

    def field(tv):
        p, rho, U = {}, {}, {}
        for i in range(4):
            for j in range(4):
                for k in range(3):
                    if tv == 0.0:
                        p[i, j, k], U[i, j, k] = P_AIR, (0.0, 0.0, 0.0)
                        continue
                    p[i, j, k] = P_AIR + 1e3 * tv * 1e3 * (1 + i + 2 * j + k)
                    rho[i, j, k] = 1.2 + 0.01 * (i + j + k) + tv
                    U[i, j, k] = (40.0 * (i + 1) * tv * 1e3, 5.0 * j,
                                  -1.0 * k)
        return p, rho, U

    elected = (2, 1, 0)                     # x 10.05, y 5.95, z 1.35
    pt = np.array([tv for tv, _n in times])
    fields = [field(tv) for tv in pt]
    six = np.vectorize(lambda v: float(f'{v:.6g}'))
    probes = dict(times=pt,
                  pressures=[six(np.array([f[0][elected] for f in fields]))],
                  rhos=[six(np.array([f[1].get(elected, 1.4)
                                      for f in fields]))],
                  velocities=[six(np.array([f[2][elected] for f in fields]))])
    comp = ew.component(case)
    real_paths = env.case_paths
    env.case_paths = lambda d: (str(d), str(d))
    try:
        with tempfile.TemporaryDirectory() as run:
            make_run(run, spec, times, field)
            before = tree(run)
            fps = iter([{'tree_sha256': 'a'}, {'tree_sha256': 'a'}])
            res, text = quietly(ew.step2, None, probes, run, comp,
                                P_AIR + 205e3, spec=spec, scan=lambda: [],
                                fp=lambda _p: next(fps), expected_n=2)
            check('it completes, read-only and trusted',
                  res['completed'] and res['read_only'] and res['trusted'],
                  text[-1500:])
            check('the elected cell is the one the check names',
                  res['cand'][res['mapping']['matched']] == elected,
                  str(res['mapping']))
            check('t = 0 takes the mixture density (0.25 x 2.0 + 0.75 x '
                  '1.2)', np.allclose(res['cells'][0, :, 1], 1.4))
            want = []
            for w, (p, rho, U) in enumerate(fields):
                if w == 0:
                    want.append(0.0)
                    continue
                best = -np.inf
                for i in (1, 2):
                    for j in range(4):
                        for k in range(3):
                            L = wl.wall_load(0.0, p[i, j, k],
                                             np.array(U[i, j, k]),
                                             rho[i, j, k], 1.24)
                            best = max(best, float(L['E']))
                want.append(best)
            check('the plane maximum is the largest wall_load over the two '
                  'layers', np.allclose(res['Emax'][1.24], want, rtol=1e-12,
                                        atol=1e-9),
                  f"{res['Emax'][1.24]} vs {want}")
            check('the run dir is untouched', tree(run) == before)
            with tempfile.TemporaryDirectory() as dl:
                path, _t = quietly(ew.deliver_plane, res, 'f' * 64,
                                   'test status', dl)
                head, units, cols = ew.read_table(path)
                check('the plane file names its units and reads back bit '
                      'for bit',
                      'Emax_1.24 [Pa over P_AIR]' in units
                      and 'G1cell_rho [kg/m3]' in units
                      and np.array_equal(cols['Emax_1.24'],
                                         res['Emax'][1.24])
                      and np.array_equal(
                          cols['G1cell_p'],
                          res['cells'][:, res['mapping']['matched'], 0]),
                      str(units))

            # the read-only conditions
            fps = iter([{'tree_sha256': 'a'}, {'tree_sha256': 'b'}])
            res, _t = quietly(ew.step2, None, probes, run, comp, P_AIR,
                              spec=spec, scan=lambda: [],
                              fp=lambda _p: next(fps), expected_n=2)
            check('a fingerprint that changed means not read-only',
                  res['completed'] and not res['read_only'])
            res, text = quietly(ew.step2, None, probes, run, comp, P_AIR,
                                spec=spec, scan=lambda: ['9 blastFoam'],
                                fp=lambda _p: {}, expected_n=2)
            check('a foam process before the read refuses it',
                  not res['completed'] and not res['read_only']
                  and 'REFUSED' in text, text)
            seen = []

            def appears():                        # clean once, then a hit
                seen.append(1)
                return [] if len(seen) == 1 else ['9 mpirun']

            real_every = ew.SCAN_EVERY_S
            ew.SCAN_EVERY_S = 0.001               # the timer scans at once
            try:
                res, text = quietly(ew.step2, None, probes, run, comp,
                                    P_AIR, spec=spec, scan=appears,
                                    fp=lambda _p: {'x': '1'}, expected_n=2)
            finally:
                ew.SCAN_EVERY_S = real_every
            check('one appearing during the read means not read-only',
                  not res['read_only'] and '9 mpirun' in text
                  and len(seen) >= 2, text)

            def broken():                         # clean before the read, then
                seen.append(1)                    # fails at the timer's first scan
                if len(seen) > 1:                 # or the after-scan, whichever
                    raise RuntimeError('wsl.exe went away')   # comes first
                return []

            seen.clear()
            ew.SCAN_EVERY_S = 0.001
            try:
                res, text = quietly(ew.step2, None, probes, run, comp,
                                    P_AIR, spec=spec, scan=broken,
                                    fp=lambda _p: {'x': '1'}, expected_n=2)
            finally:
                ew.SCAN_EVERY_S = real_every
            check('a scan that fails means not read-only, and is said',
                  not res['read_only'] and 'wsl.exe went away' in text,
                  text)
            res, text = quietly(ew.step2, None, probes, run, comp, P_AIR,
                                spec=spec, scan=lambda: [],
                                fp=lambda _p: 1 / 0, expected_n=2)
            check('a fingerprint that cannot be taken means not read-only',
                  res['completed'] and not res['read_only']
                  and 'FAILED' in text, text)
            # a write that cannot be read aborts Step 2 - and the run is
            # still fingerprinted after it, so the record shows it intact
            with open(os.path.join(run, '0.009', 'p'), 'w',
                      encoding='ascii', newline='\n') as f:
                f.write('FoamFile { format ascii; }\ninternalField   '
                        'nonuniform List<scalar>\n48\n(\n1\n2\n')
            taken = []
            res, text = quietly(ew.step2, None, probes, run, comp, P_AIR,
                                spec=spec, scan=lambda: [],
                                fp=lambda _p: taken.append(1) or {'x': '1'},
                                expected_n=2)
            check('an unreadable write aborts Step 2 (not completed, not '
                  'read-only), and the after-fingerprint is still taken',
                  not res['completed'] and not res['read_only']
                  and 'ABORTED' in text and len(taken) == 2
                  and 'after    x 1' in text, text)
    finally:
        env.case_paths = real_paths


def test_built_case():
    """pytest's entry to the three checks that need the built case
    (P2-13 item 3: they take arguments, so pytest reported them as
    "fixture not found"). Builds it once, as `main()` does, and runs them
    in the same order. The script calls them directly from `main()`."""
    case = ew.build()
    cfd, info = asm.build_vent_case(case)
    _check_evidence(case, cfd, info)
    _check_tails(case)
    _check_step2_driver(case)


def main():
    case = ew.build()
    cfd, info = asm.build_vent_case(case)
    _check_evidence(case, cfd, info)
    _check_tails(case)
    test_premises()
    test_outcome()
    test_refusals()
    test_plane_parts()
    test_mapping()
    test_start_reader()
    _check_step2_driver(case)


if __name__ == '__main__':
    main()
    print()
    print('VENT WALL: ' + ('PASS' if not FAILS else
                           f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
