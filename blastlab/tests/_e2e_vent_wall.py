"""HD1-13, route (b): the load a wall at x = 10 m takes from the HD1-3d
jet, re-evaluated from the finished run's files with NO new solve.

WHAT THIS PRODUCES, AND WHAT IT DOES NOT
`_e2e_vent_3d.py` judged a 200 mm panel 4 m from the opening on the
SIDE-ON trace of a gauge in free air: only the room is meshed, so
nothing at x = 10 m reflects. UFC 3-340-02 para 2-15.3.2 (printed p. 65)
loads a front wall with the reflected pressure and, after clearing,
with Ps + C_D q (Eq. 2-9). This script applies both, made compressible
(`core/wallload.py`), to the run's own records and delivers the result
as a LOAD: E(t) = max(R, S), with R(t) and S(t), in text files with
units, for the owner's SDOF on any wall. It gives no survival verdict -
every wall has its own criterion (owner, 2026-09-24). The 200 mm panel
of C10 is put through `core/sdof` as an example and REPORTED only.

THE RULE CAME FIRST. docs/hd13/vent3d_wall_rule.txt was committed
(bf8d89d) before this script existed and before any wall-load number
was computed on the evidence. The script prints that file's sha256 and
decides only what the rule decides: whether the delivered E(t) is an
upper bound on the wall load (BOUND) or is not claimed as one (NOT
ESTABLISHED). The outcome line is printed by `outcome_line`, whose only
inputs are the rule's four conditions - no SDOF result, peak or impulse
can reach it.

STEP 1 (this file's default): the three probes of the evidence copy,
every sample. The copy's case.json and gauges/0/{p,U,rho} must match
its SHA256SUMS.source and case.json must equal this script's CFD case in
every key, or nothing is computed. Then: the C10 control (G1's static
trace through the same `sdof.response` call must give mu 0.3027 and
theta 0.154 deg, or the script stops), E at G1/G2/G3 for gamma 1.24 and
1.40, the example panel under the rule's two tails T0 and T1, and the
premises P2 (quasi-steady stagnation at G1) and P3 (the chamber
pressure is a ceiling on the tail).

READ-ONLY. Nothing is written under the evidence dir or any run dir.
The record is stdout; the delivered G1 trace goes to --deliver (default
docs/hd13/), and --out DIR adds the G2/G3 traces, both refused if they
point into the evidence copy or into WSL.

Run:  cd blastlab/tests && python -u _e2e_vent_wall.py
          [--evidence DIR] [--deliver DIR] [--out DIR] [--record FILE]
"""

import argparse
import hashlib
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from _e2e_vent_3d import build                                # noqa: E402
from blastlab.core import assessment as asm                   # noqa: E402
from blastlab.core import sdof as _sdof                       # noqa: E402
from blastlab.core import wallload as wl                      # noqa: E402
from blastlab.core.case import case_to_dict                   # noqa: E402
from blastlab.core.constants import P_AIR                     # noqa: E402
from blastlab.output.gauge_summary import summarize_trace     # noqa: E402
from blastlab.solvers.foam import reader                      # noqa: E402

RUN_NAME = '20260923-195308_3d_p31468-00'
DEFAULT_EVIDENCE = os.path.join(
    os.environ.get('USERPROFILE') or os.path.expanduser('~'),
    'blastlab_evidence', RUN_NAME)
RULE = os.path.join(REPO, 'docs', 'hd13', 'vent3d_wall_rule.txt')
DELIVER = os.path.join(REPO, 'docs', 'hd13')
G1_FILE = 'vent3d_wall_load_G1.txt'

#: the rule's two ends: the double_base products (as written into the
#: run's constant/phaseProperties) and air. Both terms fall with gamma
#: (tests/test_wallload.py), so 1.24 is the severe end of any mixture.
GAMMAS = (1.24, 1.40)
#: the wall at x = 10 m faces -x: the flow that loads it runs along +x
NORMAL = (1.0, 0.0, 0.0)
#: what the evidence copy's SHA256SUMS.source must vouch for
EVIDENCE_FILES = ('case.json', 'postProcessing/gauges/0/p',
                  'postProcessing/gauges/0/U', 'postProcessing/gauges/0/rho')
#: C10 as recorded (docs/hd13/vent3d_postmortem.txt), to the printed digits
C10_MU, C10_THETA, C10_REGIME = '0.3027', '0.154', 'dynamic'
#: T1 holds E_tail for this many natural periods of the wall
TAIL_TN = 1.5
#: UFC 3-340-02 support rotations listed beside the example panel's
#: response as REFERENCE ONLY (2 deg: para 4-9.1; 6 deg: 4-9.2; 12 deg:
#: 4-9.3) - the owner set no criterion and none is applied
UFC_LIMITS_DEG = (2.0, 6.0, 12.0)
#: P2's sound speed is taken at the products' gamma, as the rule writes it
P2_GAMMA = 1.24

BOUND = 'BOUND'
NOT_ESTABLISHED = 'NOT ESTABLISHED'


# ── the evidence ───────────────────────────────────────────────────────

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read_sums(path):
    """A `sha256sum` listing -> {relative path: hex digest}."""
    out = {}
    with open(path, encoding='utf-8') as f:
        for ln in f:
            parts = ln.split(None, 1)
            if len(parts) == 2:
                out[parts[1].strip()] = parts[0]
    return out


def verify_evidence(evidence, say=print):
    """True when every EVIDENCE_FILES entry matches SHA256SUMS.source."""
    try:
        sums = read_sums(os.path.join(evidence, 'SHA256SUMS.source'))
    except OSError as exc:
        say(f'  [REFUSED] cannot read SHA256SUMS.source: {exc}')
        return False
    ok = True
    for rel in EVIDENCE_FILES:
        want = sums.get(rel)
        try:
            got = sha256_file(os.path.join(evidence, *rel.split('/')))
        except OSError as exc:
            got = f'(unreadable: {exc})'
        match = want is not None and got == want
        ok = ok and match
        say(f'  sha256 {got}  {rel}  '
            + ('matches SHA256SUMS.source' if match else
               f'DOES NOT MATCH SHA256SUMS.source ({want})'))
    return ok


def case_differs(evidence, cfd):
    """(keys that differ, number of keys): case.json against this
    script's CFD case as save_case writes it and JSON reads it back."""
    with open(os.path.join(evidence, 'case.json'), encoding='utf-8') as f:
        saved = json.load(f)
    want = json.loads(json.dumps(case_to_dict(cfd)))
    return (sorted(k for k in set(saved) | set(want)
                   if saved.get(k) != want.get(k)), len(want))


def load_evidence(evidence, cfd, say=print):
    """The evidence copy's probes, or None with the refusal printed.
    Reads only case.json, SHA256SUMS.source and gauges/0/{p,U,rho}."""
    say(f'  evidence {evidence}')
    if not verify_evidence(evidence, say):
        say('  [REFUSED] the evidence copy does not match its '
            'SHA256SUMS.source - nothing is computed')
        return None
    try:
        differ, n = case_differs(evidence, cfd)
    except (OSError, ValueError) as exc:
        say(f'  [REFUSED] cannot read case.json: {exc}')
        return None
    if differ:
        say(f"  [REFUSED] not this script's case: {', '.join(differ)} "
            f'differ')
        return None
    say(f'  case     case.json equals this CFD case, all {n} keys')
    try:
        probes = reader.read_probes(evidence)
    except (OSError, ValueError) as exc:
        say(f'  [REFUSED] cannot read the probes: {exc}')
        return None
    if not probes or 'velocities' not in probes or 'rhos' not in probes:
        say('  [REFUSED] the probes carry no U vectors and rho aligned '
            'with p')
        return None
    return probes


# ── the load and the example panel ─────────────────────────────────────

def component(case):
    """C10's component, unchanged (`_e2e_vent_3d.evaluate`)."""
    return _sdof.Component(span=case.span_m, mass_per_area=case.mass_per_area,
                           Ru=case.Ru_pa, kE=case.kE_pa_m,
                           support=case.support)


def c10_control(t, p, comp):
    """(reproduced, SdofResult): G1's static trace through C10's own
    call - `sdof.response(t, p, comp, p_ref=P_AIR)` on the finite
    samples - against the recorded mu, theta and regime."""
    t, p = np.asarray(t, float), np.asarray(p, float)
    ok = np.isfinite(p)
    r = _sdof.response(t[ok], p[ok], comp, p_ref=P_AIR)
    return (f'{r.ductility:.4f}' == C10_MU
            and f'{r.support_rotation_deg:.3f}' == C10_THETA
            and r.regime == C10_REGIME), r


def gauge_load(probes, k, gamma):
    """The rule's E at probe k: wall_load on the probe's own p, U, rho."""
    return wl.wall_load(probes['times'], probes['pressures'][k],
                        probes['velocities'][k], probes['rhos'][k], gamma,
                        normal=NORMAL)


def tail_level(E, p_open):
    """T1's E_tail = max(p_open - P_AIR, max E over the record) [Pa]."""
    return max(float(p_open) - P_AIR, float(np.nanmax(E)))


def responses(t, E, comp, p_open):
    """The example panel under the rule's two tails. T0: the record, and
    zero after it (`sdof.response`'s own convention - what C10 did). T1:
    E_tail held for TAIL_TN natural periods after the record, then the
    solver's free vibration. Non-finite samples are dropped (and counted)
    as C10 dropped them. Returns dict(T0, T1, level, t1, E1, dropped)."""
    t, E = np.asarray(t, float), np.asarray(E, float)
    ok = np.isfinite(E) & np.isfinite(t)
    t, E = t[ok], E[ok]
    level = tail_level(E, p_open)
    r0 = _sdof.response(t, E, comp, p_ref=0.0)
    t1, E1 = wl.extend_with_tail(t, E, level, TAIL_TN * comp.Tn)
    r1 = _sdof.response(t1, E1, comp, p_ref=0.0)
    return dict(T0=r0, T1=r1, level=level, t1=t1, E1=E1,
                dropped=int((~ok).sum()), t_end=float(t[-1]))


def ufc_reference(comp):
    """[(theta_deg, mu)] for the UFC reference rotations on `comp`."""
    arm = comp.span if comp.support == 'cantilever' else 0.5 * comp.span
    return [(th, arm * np.tan(np.radians(th)) / comp.y_el)
            for th in UFC_LIMITS_DEG]


# ── the premises ───────────────────────────────────────────────────────

def premise_p2(t, un, p, rho, D, gamma=P2_GAMMA):
    """P2, quasi-steady stagnation: t90 - t10 >= D / a, with t90 the first
    time un >= 0.9 max(un), t10 the last time before it with un <= 0.1
    max(un), and a = sqrt(gamma p / rho) at t90. No t10 (the flow never
    was slow before its rise) means the rise was not seen: P2 fails."""
    t, un = np.asarray(t, float), np.asarray(un, float)
    p, rho = np.asarray(p, float), np.asarray(rho, float)
    umax = float(np.nanmax(un))
    i90 = int(np.flatnonzero(un >= 0.9 * umax)[0])
    low = np.flatnonzero(un[:i90] <= 0.1 * umax)
    a = float(np.sqrt(gamma * p[i90] / rho[i90]))
    need = float(D) / a
    out = dict(umax=umax, i90=i90, t90=float(t[i90]), a=a, D=float(D),
               need=need, i10=None, t10=np.nan, rise=np.nan, ok=False)
    if len(low):
        i10 = int(low[-1])
        rise = float(t[i90] - t[i10])
        out.update(i10=i10, t10=float(t[i10]), rise=rise,
                   ok=bool(rise >= need))
    return out


def premise_p3(zero_d, t_open, p_open, tau_drain):
    """P3, the tail is a ceiling: the sealed 0-D run's pressure rise rate
    at t_open < (p_open - P_AIR) / tau_drain.

    The 0-D output is sampled, so the rate at t_open is estimated from
    the samples either side of it, and the LARGER of the two one-sided
    differences is judged: that bounds the central difference from
    above, so P3 can only be harder to pass than with any usual
    estimator. Chosen here, before any P3 number was computed."""
    t = np.asarray(zero_d['t'], float)
    p = np.asarray(zero_d['p'], float)
    i = int(np.argmin(np.abs(t - float(t_open))))
    back = (p[i] - p[i - 1]) / (t[i] - t[i - 1]) if i > 0 else np.nan
    fwd = ((p[i + 1] - p[i]) / (t[i + 1] - t[i]) if i + 1 < len(t)
           else np.nan)
    rate = float(np.nanmax([back, fwd]))
    ceiling = (float(p_open) - P_AIR) / float(tau_drain)
    return dict(i=i, t_i=float(t[i]), back=float(back), fwd=float(fwd),
                rate=rate, ceiling=ceiling, ratio=rate / ceiling,
                ok=bool(rate < ceiling))


# ── the outcome ────────────────────────────────────────────────────────

def outcome(p2_holds, p3_holds, step2_trusted, step2_read_only):
    """The rule's OUTCOME table, first match wins: (label, conditions).
    Only the rule's four conditions enter - no SDOF result, no peak, no
    impulse. When Step 2 could not be run read-only its mapping check
    means nothing, so only the first is named."""
    failed = []
    if not p2_holds:
        failed.append('P2 fails')
    if not p3_holds:
        failed.append('P3 fails')
    if not step2_read_only:
        failed.append('Step 2 cannot be run read-only')
    elif not step2_trusted:
        failed.append('Step 2 is untrusted (mapping check)')
    if failed:
        return NOT_ESTABLISHED, failed
    return BOUND, ['P2 and P3 hold and Step 2 is trusted']


def outcome_line(p2_holds, p3_holds, step2_trusted, step2_read_only):
    """The record's final line, printed by this function, never typed."""
    label, why = outcome(p2_holds, p3_holds, step2_trusted,
                         step2_read_only)
    return f"HD1-13 ROUTE (b): {label} - {'; '.join(why)}"


def step1_status(p2_holds, p3_holds):
    """What Step 1 alone settles: a failed premise is NOT ESTABLISHED
    whatever Step 2 finds (first match wins); otherwise Step 2 decides."""
    if not (p2_holds and p3_holds):
        label, why = outcome(p2_holds, p3_holds, True, True)
        return f"{label} whatever Step 2 finds - {'; '.join(why)}"
    return 'P2 and P3 hold - the outcome needs Step 2 (the plane)'


# ── the delivered text files ───────────────────────────────────────────

def write_table(path, header, columns, units, arrays):
    """A plain text table: '# ' header lines, one '# units:' line, the
    column names, then one row per sample. Floats are written with
    repr(), the shortest text that reads back to the same double."""
    lines = ['# ' + h for h in header]
    lines.append('# units: ' + '; '.join(f'{c} [{u}]'
                                         for c, u in zip(columns, units)))
    lines.append(' '.join(columns))
    cols = [np.asarray(a, float) for a in arrays]
    n = len(cols[0])
    if any(len(c) != n for c in cols):
        raise ValueError('every column needs the same length')
    for i in range(n):
        lines.append(' '.join(repr(float(c[i])) for c in cols))
    with open(path, 'w', encoding='ascii', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    return path


def read_table(path):
    """(header lines, units line, {column: array}) of a write_table file."""
    header, units, names, rows = [], None, None, []
    with open(path, encoding='ascii') as f:
        for ln in f:
            ln = ln.rstrip('\n')
            if ln.startswith('# units: '):
                units = ln[len('# units: '):]
            elif ln.startswith('#'):
                header.append(ln[2:])
            elif names is None:
                names = ln.split()
            elif ln.strip():
                rows.append([float(v) for v in ln.split()])
    a = np.array(rows, dtype=float).reshape(-1, len(names))
    return header, units, {c: a[:, j] for j, c in enumerate(names)}


def trace_columns(t, un, loads):
    """(columns, units, arrays) of one probe's delivered trace: t, un,
    then R, S, E, M per gamma. `loads` maps gamma -> wall_load dict."""
    cols, units, arrs = ['t', 'un'], ['s', 'm/s'], [t, un]
    for g in GAMMAS:
        L = loads[g]
        for q, u in (('R', 'Pa over P_AIR'), ('S', 'Pa over P_AIR'),
                     ('E', 'Pa over P_AIR'), ('M', '-')):
            cols.append(f'{q}_{g:.2f}')
            units.append(u)
            arrs.append(L[q])
    return cols, units, arrs


def trace_header(label, point, n, rule_sha, levels, p_open, t_end, status):
    """The header of a delivered probe trace: what it is, the rule, the
    T1 rule stated rather than baked in, and the rule's outcome."""
    return [
        f'HD1-13 route (b): the wall load at {label} = '
        f'({point[0]:g}, {point[1]:g}, {point[2]:g}) m, every probe '
        f'sample ({n} rows)',
        f'run {RUN_NAME} (HD1-3d), probes postProcessing/gauges/0/'
        f'{{p,U,rho}} of the sha256-checked evidence copy; no solve',
        f'rule docs/hd13/vent3d_wall_rule.txt, sha256 {rule_sha}',
        'E = max(R, S) over P_AIR = 101325 Pa. R: normal reflection of the '
        'front (Rankine-Hugoniot, no clearing). S: stagnation overpressure '
        'of un = max(Ux, 0), isentropic below M = 1, Rayleigh pitot at and '
        'above. The wall at x = 10 m faces -x.',
        'gamma 1.24 (the double_base products) and 1.40 (air) bound any '
        'mixture; 1.24 is the severe end of both terms.',
        f'T1 (a rule, not baked in - its length belongs to the wall): '
        f'after the record ends at t = {t_end:.6g} s, hold E_tail = '
        f'max(p_open - P_AIR, max E) for 1.5 Tn of the wall being checked. '
        f'p_open - P_AIR = {p_open - P_AIR:.1f} Pa; E_tail here: '
        + ', '.join(f'gamma {g:.2f} {levels[g]:.1f} Pa' for g in GAMMAS)
        + '.',
        f'status: {status}',
    ]


def _outside(path, evidence):
    """True when `path` is neither inside the evidence copy nor in WSL."""
    a = os.path.normcase(os.path.abspath(path))
    e = os.path.normcase(os.path.abspath(evidence))
    return not (a == e or a.startswith(e + os.sep)
                or a.startswith('\\\\wsl'))


class _Tee:
    """stdout, also written to a record file (UTF-8, LF)."""

    def __init__(self, path):
        self.f = open(path, 'w', encoding='utf-8', newline='\n')
        self.out = sys.stdout

    def write(self, s):
        self.out.write(s)
        self.f.write(s)

    def flush(self):
        self.out.flush()
        self.f.flush()


# ── Step 1 ─────────────────────────────────────────────────────────────

def _kpa(v):
    return f'{v / 1e3:.2f}'


def report_trace(t, E, parts, comp, p_open, say=print):
    """Peak, positive phase, arrival (summarize_trace on P_AIR + E) and
    the example panel under T0 and T1, for one E trace. Returns the two
    responses. Nothing here is judged."""
    s = summarize_trace(t, P_AIR + np.asarray(E, float))
    i_pk = int(np.nanargmax(E))
    which = ('R' if parts['R'][i_pk] >= parts['S'][i_pk] else 'S')
    say(f"      E peak {s['peak_kpa']:.2f} kPa at {s['t_peak_ms']:.3f} ms "
        f"(governed by {which}: R {_kpa(parts['R'][i_pk])}, "
        f"S {_kpa(parts['S'][i_pk])} kPa)")
    if np.isnan(s['arrival_ms']):
        say('      no arrival: E never above 0.1 x P_AIR in the record')
    else:
        say(f"      arrival {s['arrival_ms']:.3f} ms, positive phase "
            f"{s['pos_duration_ms']:.3f} ms, positive-phase impulse "
            f"{s['pos_impulse']:.2f} Pa s"
            + ('' if s['complete'] else
               ' - a LOWER BOUND: still positive when the record ends')
            + f"; net impulse {s['net_impulse']:.2f} Pa s")
    rs = responses(t, E, comp, p_open)
    for tail in ('T0', 'T1'):
        r = rs[tail]
        extra = ''
        if tail == 'T1':
            extra = (f" (E_tail {_kpa(rs['level'])} kPa held "
                     f"{TAIL_TN * comp.Tn * 1e3:.2f} ms)")
        late = r.t_ymax > rs['t_end']
        say(f'      {tail}{extra}: mu {r.ductility:.4f}, theta '
            f'{r.support_rotation_deg:.3f} deg, {r.regime}, collapsed '
            f'{r.collapsed}; peak response at {r.t_ymax * 1e3:.2f} ms'
            + (' - after the record ends: set by the tail' if late
               else ''))
    dt0 = rs['T0'].times[1] - rs['T0'].times[0]
    dt1 = rs['T1'].times[1] - rs['T1'].times[0]
    say(f'      sdof dt {dt0:.4e} s (T0) / {dt1:.4e} s (T1)'
        + (', the same' if dt0 == dt1 else ' - DIFFERENT')
        + (f"; {rs['dropped']} non-finite samples dropped"
           if rs['dropped'] else ''))
    return rs


def step1(info, probes, comp, say=print):
    """Step 1 on the evidence probes. Returns a dict with the loads per
    gauge and gamma, the premises and the levels, for the files."""
    t = np.asarray(probes['times'], float)
    st = info['state']
    p_open = float(st.p)
    labels = ('G1', 'G2', 'G3')
    loads = {}
    say('\nSTEP 1 - E at the three probes, every sample (G1 is the rule\'s '
        'Step 1 trace; G2, G3 are reported)')
    for k, lab in enumerate(labels):
        pt = probes['points'][k]
        U = np.asarray(probes['velocities'][k], float)
        mag = np.asarray(probes['speeds'][k], float)
        loads[lab] = {g: gauge_load(probes, k, g) for g in GAMMAS}
        un = loads[lab][GAMMAS[0]]['un']
        i_m, i_n = int(np.nanargmax(mag)), int(np.nanargmax(un))
        say(f'\n  {lab} ({pt[0]:g}, {pt[1]:g}, {pt[2]:g}) m')
        say(f'    |U| against un: max |U| {mag[i_m]:.1f} m/s at '
            f'{t[i_m] * 1e3:.3f} ms (Ux/|U| there {U[i_m, 0] / mag[i_m]:.4f}'
            f'); max un {un[i_n]:.1f} m/s at {t[i_n] * 1e3:.3f} ms')
        for g in GAMMAS:
            L = loads[lab][g]
            say(f'    gamma {g:.2f}')
            report_trace(t, L['E'], L, comp, p_open, say)

    # the premises
    say('\nPREMISES')
    g1 = loads['G1'][GAMMAS[0]]
    D = float(np.sqrt(info['room']['vent_area']))
    p2 = premise_p2(t, g1['un'], probes['pressures'][0], probes['rhos'][0],
                    D)
    if p2['i10'] is None:
        say(f"  P2 (quasi-steady stagnation, G1): un max {p2['umax']:.1f} m/s,"
            f" t90 {p2['t90'] * 1e3:.3f} ms, and un never <= 0.1 max before "
            f"it - the rise is not seen -> P2 FAILS")
    else:
        say(f"  P2 (quasi-steady stagnation, G1): un max {p2['umax']:.1f} "
            f"m/s; t10 {p2['t10'] * 1e3:.3f} ms, t90 {p2['t90'] * 1e3:.3f} "
            f"ms, rise {p2['rise'] * 1e3:.3f} ms; D = sqrt(vent area) = "
            f"{p2['D']:.3f} m, a = sqrt(1.24 p/rho) at t90 = {p2['a']:.1f} "
            f"m/s, D/a = {p2['need'] * 1e3:.3f} ms -> P2 "
            + ('HOLDS' if p2['ok'] else 'FAILS')
            + f" (rise/(D/a) = {p2['rise'] / p2['need']:.3f})")
    val = info['validity']
    p3 = premise_p3(info['zero_d'], st.t_open, p_open, val['tau_drain'])
    say(f"  P3 (the tail is a ceiling): the sealed 0-D run at t_open = "
        f"{st.t_open:.4f} s (sample {p3['t_i']:.4f} s) rises "
        f"{p3['rate']:.1f} Pa/s (the larger one-sided difference: back "
        f"{p3['back']:.1f}, forward {p3['fwd']:.1f}); (p_open - P_AIR)/"
        f"tau_drain = {_kpa(p_open - P_AIR)} kPa / {val['tau_drain']:.4f} s "
        f"= {p3['ceiling']:.1f} Pa/s; ratio {p3['ratio']:.4f} -> P3 "
        + ('HOLDS' if p3['ok'] else 'FAILS'))
    say(f"\nSTEP 1's OUTCOME: {step1_status(p2['ok'], p3['ok'])}")
    levels = {lab: {g: tail_level(loads[lab][g]['E'], p_open)
                    for g in GAMMAS} for lab in labels}
    return dict(t=t, loads=loads, p2=p2, p3=p3, levels=levels,
                p_open=p_open, labels=labels)


def deliver_traces(res1, probes, rule_sha, status, deliver, out, say=print):
    """The delivered G1 trace (and, with --out, G2 and G3 beside it)."""
    t = res1['t']
    paths = []
    targets = [('G1', 0, os.path.join(deliver, G1_FILE))]
    if out:
        targets += [(lab, k, os.path.join(out, f'vent3d_wall_load_{lab}.txt'))
                    for k, lab in enumerate(res1['labels'])]
    for lab, k, path in targets:
        loads = res1['loads'][lab]
        cols, units, arrs = trace_columns(t, loads[GAMMAS[0]]['un'], loads)
        head = trace_header(lab, probes['points'][k], len(t), rule_sha,
                            res1['levels'][lab], res1['p_open'],
                            float(t[-1]), status)
        write_table(path, head, cols, units, arrs)
        paths.append(path)
        say(f'  delivered {path} ({len(t)} rows)')
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--evidence', default=DEFAULT_EVIDENCE)
    ap.add_argument('--deliver', default=DELIVER)
    ap.add_argument('--out', default=None)
    ap.add_argument('--record', default=None)
    args = ap.parse_args(argv)
    for d in (args.deliver, args.out, args.record):
        if d and not _outside(d, args.evidence):
            print(f'refused: {d} is inside the evidence copy or in WSL')
            return 2
    if args.record:
        sys.stdout = _Tee(args.record)
    if args.out:
        os.makedirs(args.out, exist_ok=True)

    print('HD1-13 ROUTE (b) - the load a wall at x = 10 m takes, from the '
          'HD1-3d run\'s files (no solve)')
    case = build()
    cfd, info = asm.build_vent_case(case)
    probes = load_evidence(args.evidence, cfd)
    if probes is None:
        print('\nHD1-13 ROUTE (b): NOT RUN - the evidence was refused')
        return 1
    rule_sha = sha256_file(RULE)
    print(f'  rule     docs/hd13/vent3d_wall_rule.txt  sha256 {rule_sha}')
    t = np.asarray(probes['times'], float)
    print(f"  probes   {len(probes['points'])} probes, {len(t)} samples, "
          f"t = {t[0] * 1e3:.4f} to {t[-1] * 1e3:.4f} ms; U vectors and rho "
          f"aligned with p")

    comp = component(case)
    ok, r = c10_control(t, probes['pressures'][0], comp)
    print('\nC10 CONTROL - G1\'s static trace through the same call '
          '(sdof.response, p_ref = P_AIR)')
    print(f'  mu {r.ductility:.4f}, theta {r.support_rotation_deg:.3f} deg, '
          f'{r.regime} - ' + (f'reproduces C10 ({C10_MU}, {C10_THETA} deg, '
                               f'{C10_REGIME})' if ok else
                               f'DOES NOT reproduce C10 ({C10_MU}, '
                               f'{C10_THETA} deg, {C10_REGIME})'))
    if not ok:
        print('\nHD1-13 ROUTE (b): NOT RUN - the C10 control failed, so '
              'this is not the call C10 made')
        return 1
    st = info['state']
    print(f'\n  example panel (C10\'s component, unchanged): span '
          f'{comp.span:g} m, {comp.mass_per_area:g} kg/m2, Ru '
          f'{comp.Ru / 1e3:g} kPa, kE {comp.kE:.3g} Pa/m, {comp.support}, '
          f'damping {comp.damping:g}, K_LM {comp.KLM:.2f} '
          f'({comp.klm_mode}), Tn {comp.Tn * 1e3:.2f} ms, y_el '
          f'{comp.y_el * 1e3:.2f} mm, collapse at '
          f'{comp.rotation_limit_deg:g} deg')
    print('  UFC 3-340-02 support rotations, REFERENCE ONLY (no criterion '
          'is applied): ' + ', '.join(f'{th:g} deg = mu {mu:.2f}'
                                      for th, mu in ufc_reference(comp)))
    print(f'  chamber  p_open {st.p / 1e6:.5f} MPa, so p_open - P_AIR = '
          f'{_kpa(st.p - P_AIR)} kPa; T1 holds E_tail = max(that, max E) '
          f'for {TAIL_TN:g} Tn = {TAIL_TN * comp.Tn * 1e3:.2f} ms')

    res1 = step1(info, probes, comp)
    status = ('Step 1 only - Step 2 (the plane) not run, so no bound is '
              'claimed yet: ' + step1_status(res1['p2']['ok'],
                                             res1['p3']['ok']))
    print()
    deliver_traces(res1, probes, rule_sha, status, args.deliver, args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
