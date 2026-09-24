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
    lines = []
    for rel in ew.EVIDENCE_FILES:
        with open(os.path.join(root, *rel.split('/')), 'rb') as f:
            lines.append(f'{hashlib.sha256(f.read()).hexdigest()}  {rel}')
    with open(os.path.join(root, 'SHA256SUMS.source'), 'w',
              encoding='ascii', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


# ── the checks ─────────────────────────────────────────────────────────

def test_evidence(case, cfd, info):
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
        lines = []
        for rel in ew.EVIDENCE_FILES:
            with open(os.path.join(ev, *rel.split('/')), 'rb') as f:
                lines.append(f'{hashlib.sha256(f.read()).hexdigest()}  '
                             f'{rel}')
        with open(os.path.join(ev, 'SHA256SUMS.source'), 'w',
                  encoding='ascii', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        res, text = quietly(ew.load_evidence, ev, cfd)
        check('a changed case field is refused, naming the field',
              res is None and 't_end' in text and 'not this script' in text,
              text)
    res, text = quietly(ew.load_evidence, ev, cfd)      # the dir is gone
    check('a missing evidence copy is refused, not raised',
          res is None and 'REFUSED' in text, text)


def test_tails(case):
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


def main():
    case = ew.build()
    cfd, info = asm.build_vent_case(case)
    test_evidence(case, cfd, info)
    test_tails(case)
    test_premises()
    test_outcome()
    test_refusals()


if __name__ == '__main__':
    main()
    print()
    print('VENT WALL: ' + ('PASS' if not FAILS else
                           f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
