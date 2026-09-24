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

STEP 2 (--plane): the plane x = 10 m. Every written time of the run -
the reconstructed ROOT time dirs, never processor* - is read over the
9p share with the live ingest's own reader (`backend.read_3d` on the
spec `writer.render_case` builds in memory), and E is taken over the
two cell layers either side of x = 10 m. Its maximum per write replaces
premise P1 (that G1 sits where the wall load is largest) with a
measurement. The mapping check decides whether that plane can be
trusted: one of the eight cells around (10, 6, 1.4) must reproduce G1's
probe p, rho and U to 1e-5 at all 267 writes after 8 ms. The run is
fingerprinted inside WSL before and after (sizes, counts, newest mtime,
a sha256 over every path + size + mtime), foam/MPI processes are scanned
for at least every 20 s while it is read, and any difference or hit
means Step 2 was not run read-only. No OpenFOAM utility is started,
`postmortem.load_run` is not used (it can reconstruct INTO the run), and
nothing is installed or written inside WSL. Then the rule's outcome
line, last.

READ-ONLY. Nothing is written under the evidence dir or any run dir.
The record is stdout (--record FILE keeps a copy); the delivered G1
trace and, with --plane, the plane file go to --deliver (default
docs/hd13/), and --out DIR adds the G2/G3 traces and the plane's raw
arrays. Each is refused if it points into the evidence copy or into
WSL.

Run:  cd blastlab/tests && python -u _e2e_vent_wall.py [--plane]
          [--evidence DIR] [--run NAME] [--deliver DIR] [--out DIR]
          [--record FILE]
      (--plane: WSL; ~26 GB read over 9p, 5-10 min)
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

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
        why = ('in free vibration once the load drops to zero'
               if tail == 'T0' else 'set by the T1 hold')
        say(f'      {tail}{extra}: mu {r.ductility:.4f}, theta '
            f'{r.support_rotation_deg:.3f} deg, {r.regime}, collapsed '
            f'{r.collapsed}; peak response at {r.t_ymax * 1e3:.2f} ms'
            + (f' - after the record ends, {why}' if late else ''))
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


# ── Step 2: the plane x = 10 m, read-only from the run ─────────────────

WALL_X = 10.0
G1_POINT = (10.0, 6.0, 1.4)
#: the rule names the two layers either side of the wall by their centres
LAYER_CENTRES = (9.95, 10.05)
#: report-only panel footprint (owner default, 2026-09-24): a 3 m span
#: from the ground, centred on the opening's axis
FOOT_Y = (4.5, 7.5)
FOOT_Z = (0.0, 3.0)
STRIP_Y = 6.0
#: the mapping check, as the rule states it
MAP_T_MIN = 0.008
MAP_N = 267
MAP_REL = 1e-5
MAP_U_FLOOR = 1.0
#: the process scan runs at least this often while the fields are read
SCAN_EVERY_S = 20.0
FOAM_PROCS = ('blastFoam', 'mpirun', 'orted', 'reconstructPar',
              'decomposePar', 'postProcess', 'foamToVTK')
PLANE_FILE = 'vent3d_wall_plane.txt'
#: READ-ONLY fingerprint of a run dir: sizes, newest mtime, counts, a
#: sha256 over every path + size + mtime, and the sha256 of the files
#: the evidence copy vouches for. Fed to `bash -s` on stdin as bytes
#: (LF endings, no quoting through any shell); prints to stdout only.
FINGERPRINT_SH = b'''R="$1"
echo "FP|du_sb|$(du -sb "$R" | cut -f1)"
echo "FP|newest_mtime|$(find "$R" -printf '%T@\\n' | sort -n | tail -1)"
echo "FP|n_files|$(find "$R" -type f | wc -l)"
echo "FP|n_dirs|$(find "$R" -type d | wc -l)"
echo "FP|tree_sha256|$(find "$R" -printf '%P %s %T@\\n' | LC_ALL=C sort | sha256sum | cut -d' ' -f1)"
for f in case.json postProcessing/gauges/0/p postProcessing/gauges/0/U postProcessing/gauges/0/rho; do
  echo "FP|sha256 $f|$(sha256sum "$R/$f" | cut -d' ' -f1)"
done
'''


def parse_ps(text):
    """`ps -eo pid=,comm=` output -> the foam/MPI lines. Matched on the
    exact command name, so the scan can never match itself."""
    hits = []
    for ln in (text or '').splitlines():
        parts = ln.split(None, 1)
        if len(parts) == 2 and parts[1].strip() in FOAM_PROCS:
            hits.append(ln.strip())
    return hits


def process_scan():
    """Foam/MPI processes running in WSL ([] = none)."""
    from blastlab.solvers.foam import env
    res = subprocess.run(['wsl', '-d', env.WSL_DISTRO, '-e', 'ps', '-eo',
                          'pid=,comm='], capture_output=True, timeout=120,
                         stdin=subprocess.DEVNULL,
                         creationflags=env.CREATE_NO_WINDOW)
    if res.returncode != 0:
        raise RuntimeError(f'the process scan failed (rc {res.returncode})')
    return parse_ps(res.stdout.decode('utf-8', 'replace'))


def parse_fp(text):
    """Fingerprint output -> {key: value}."""
    out = {}
    for ln in (text or '').splitlines():
        parts = ln.strip().split('|', 2)
        if len(parts) == 3 and parts[0] == 'FP':
            out[parts[1]] = parts[2]
    return out


def fingerprint(posix_run):
    """The READ-ONLY fingerprint of a run dir inside WSL (FINGERPRINT_SH)."""
    from blastlab.solvers.foam import env
    res = subprocess.run(['wsl', '-d', env.WSL_DISTRO, '-e', 'bash', '-s',
                          '--', posix_run], input=FINGERPRINT_SH,
                         capture_output=True, timeout=1800,
                         creationflags=env.CREATE_NO_WINDOW)
    return parse_fp(res.stdout.decode('utf-8', 'replace'))


def _checked(fn, say, *a, failed=('(the scan failed)',)):
    """fn(*a), or `failed` - printed - when it raises: a scan or a
    fingerprint that cannot be taken proves nothing, so it counts as a
    hit / as no fingerprint, never as a clean result."""
    try:
        return fn(*a)
    except Exception as exc:                # noqa: BLE001 - reported
        say(f'  [FAILED] {getattr(fn, "__name__", "check")}: {exc}')
        return list(failed) if isinstance(failed, tuple) else failed


class _Scanner:
    """Runs `scan` every `every` seconds on a daemon thread while the
    fields are read - so a stalled 9p read cannot stretch the cadence -
    and keeps the times of the scans and anything they saw."""

    def __init__(self, scan, every):
        import threading
        self.scan, self.every = scan, float(every)
        self.stamps, self.hits, self.error = [], [], None
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._run, daemon=True,
                                    name='hd13-foam-scan')

    def _run(self):
        while not self._stop.wait(self.every):
            try:
                h = self.scan()
            except Exception as exc:        # noqa: BLE001 - reported below
                self.error = exc
                return
            self.stamps.append(time.time())
            if h:
                self.hits.extend(h)

    def start(self):
        self._th.start()
        return self

    def stop(self):
        self._stop.set()
        self._th.join()

    @property
    def bad(self):
        return bool(self.hits) or self.error is not None


def bracket(centres, x):
    """(i_lo, i_hi): the cell centres either side of `x`,
    c[i_lo] <= x < c[i_hi]. Raises when `x` is not inside the centres."""
    c = np.asarray(centres, dtype=float)
    i_hi = int(np.searchsorted(c, float(x), side='right'))
    if i_hi <= 0 or i_hi >= len(c):
        raise ValueError(f'{x} is not between two cell centres')
    return i_hi - 1, i_hi


def plane_max(E, xs, ys, zs):
    """(max E, (x, y, z) of its cell, (i, j, k)) over a slab E[i, j, k]
    whose cells sit at xs[i], ys[j], zs[k]. NaN cells are skipped."""
    k = int(np.nanargmax(E))
    i, j, l = (int(v) for v in np.unravel_index(k, E.shape))
    return (float(E[i, j, l]), (float(xs[i]), float(ys[j]), float(zs[l])),
            (i, j, l))


def footprint_masks(ys, zs, foot_y=FOOT_Y, foot_z=FOOT_Z):
    """(y mask, z mask) of the cells whose centres lie on the panel."""
    ys, zs = np.asarray(ys, float), np.asarray(zs, float)
    return ((ys >= foot_y[0]) & (ys <= foot_y[1]),
            (zs >= foot_z[0]) & (zs <= foot_z[1]))


def panel_numbers(p, rho, U, E, ys, zs, strip_j):
    """Report-only means over the panel footprint, both layers: the area
    mean of E (per gamma, E maps gamma -> slab), the area mean of the
    momentum flux max(0, p - P_AIR + rho un^2), and the mean of E over
    the strip of z at the two y columns `strip_j`. Every cell of a
    uniform mesh has the same face area, so an area mean is a plain
    mean. Estimates, not bounds (see the module docstring)."""
    my, mz = footprint_masks(ys, zs)
    un = np.maximum(np.asarray(U, float)[..., 0], 0.0)
    mf = np.maximum(0.0, np.asarray(p, float) - P_AIR
                    + np.asarray(rho, float) * un * un)
    foot = np.ix_(np.arange(mf.shape[0]), np.flatnonzero(my),
                  np.flatnonzero(mz))
    strip = np.ix_(np.arange(mf.shape[0]), np.asarray(strip_j),
                   np.flatnonzero(mz))
    out = dict(momentum=float(np.mean(mf[foot])))
    for g, Eg in E.items():
        out[('E', g)] = float(np.mean(Eg[foot]))
        out[('strip', g)] = float(np.mean(Eg[strip]))
    return out


def mapping_check(write_t, cells, probe_t, probe_p, probe_rho, probe_U,
                  t_min=MAP_T_MIN, expected_n=MAP_N, rel=MAP_REL,
                  u_floor=MAP_U_FLOOR):
    """The rule's mapping check. `cells[w, c]` is [p, rho, Ux, Uy, Uz] of
    candidate cell c at write w. At every write after `t_min`, the probe
    row nearest in time is compared with each cell: p and rho to `rel`
    relative, U to `rel` of |U| + `u_floor` (the vector difference).
    Trusted when exactly `expected_n` writes were compared and one cell
    matched at all of them."""
    wt = np.asarray(write_t, float)
    cells = np.asarray(cells, float)
    pt = np.asarray(probe_t, float)
    sel = np.flatnonzero(wt > t_min)
    n = len(sel)
    res = dict(n=n, expected_n=expected_n, cells=[], matched=None,
               trusted=False, t_mismatch=np.nan)
    if not n:
        return res
    j = np.clip(np.searchsorted(pt, wt[sel]), 1, len(pt) - 1)
    j = np.where(np.abs(pt[j - 1] - wt[sel]) <= np.abs(pt[j] - wt[sel]),
                 j - 1, j)
    res['t_mismatch'] = float(np.max(np.abs(pt[j] - wt[sel])
                                     / np.abs(wt[sel])))
    P = np.asarray(probe_p, float)[j]
    R = np.asarray(probe_rho, float)[j]
    V = np.asarray(probe_U, float)[j]
    Vmag = np.sqrt((V * V).sum(axis=1))
    for c in range(cells.shape[1]):
        x = cells[sel, c]
        ep = np.abs(x[:, 0] - P) / np.abs(P)
        er = np.abs(x[:, 1] - R) / np.abs(R)
        eu = (np.sqrt(((x[:, 2:5] - V) ** 2).sum(axis=1))
              / (Vmag + u_floor))
        ok = bool((ep <= rel).all() and (er <= rel).all()
                  and (eu <= rel).all())
        res['cells'].append(dict(ok=ok, p=float(ep.max()),
                                 rho=float(er.max()), U=float(eu.max())))
    oks = [c for c, d in enumerate(res['cells']) if d['ok']]
    if oks:
        res['matched'] = oks[0]
    res['trusted'] = bool(oks) and n == expected_n
    return res


def start_density(tdir, spec):
    """The mixture density at a time blastFoam wrote no `rho` for (its
    start time): rho = alpha1 rho1 + (1 - alpha1) rho2 - blastFoam User
    Guide v6.0, sec. 2, Eqs. 2.9-2.10 (p. 15)."""
    from blastlab.core.constants import RHO_AIR
    from blastlab.solvers.foam import writer
    n = spec.n_cells
    a = reader.to_grid(reader.read_scalar(
        os.path.join(tdir, f'alpha.{writer.PHASE}'), n), spec, fill=0.0)
    r1 = reader.to_grid(reader.read_scalar(
        os.path.join(tdir, f'rho.{writer.PHASE}'), n), spec, fill=RHO_AIR)
    r2 = reader.to_grid(reader.read_scalar(
        os.path.join(tdir, 'rho.air'), n), spec, fill=RHO_AIR)
    return a * r1 + (1.0 - a) * r2


def read_slab(tdir, spec, i_lo, i_hi):
    """(p, rho, U) on the layers i_lo..i_hi of one written time, through
    the live ingest's own reader (`backend.read_3d`), so the grid mapping
    is the one the foam tests pin. Reads files; writes nothing."""
    from blastlab.solvers.foam import backend
    sl = slice(i_lo, i_hi + 1)
    if os.path.isfile(os.path.join(tdir, 'rho')):
        f = backend.read_3d(tdir, spec, what=('p', 'rho', 'U'))
        return f['p'][sl], f['rho'][sl], f['U'][sl]
    f = backend.read_3d(tdir, spec, what=('p', 'U'))
    return f['p'][sl], start_density(tdir, spec)[sl], f['U'][sl]


def step2(cfd, probes, run, comp, p_open, say=print, spec=None,
          scan=process_scan, fp=fingerprint, t_min=MAP_T_MIN,
          expected_n=MAP_N):
    """Step 2: E over the plane x = 10 m at every written time, read-only
    from the run's reconstructed root time dirs. Returns a dict whose
    `read_only` and `trusted` are the rule's two Step 2 conditions."""
    from blastlab.solvers.foam import env, writer
    posix, unc = env.case_paths(run)
    out = dict(read_only=False, trusted=False, completed=False)
    say('\nSTEP 2 - the plane x = 10 m, every written time, read-only from '
        'the run')
    say(f'  run      {posix}')
    hits = _checked(scan, say)
    say('  scan     before: ' + (', '.join(hits) if hits else
                                 'no foam/MPI process'))
    if hits:
        say('  [REFUSED] a foam/MPI process is running, or the scan failed '
            '- Step 2 cannot be run read-only')
        return out
    before = _checked(fp, say, posix, failed={})
    for k, v in before.items():
        say(f'  before   {k} {v}')
    if spec is None:
        spec = writer.render_case(cfd, n_procs=13)
    g = spec.grid
    xs, ys, zs = (np.asarray(g[k], float) for k in ('x_c', 'y_c', 'z_c'))
    i_lo, i_hi = bracket(xs, WALL_X)
    js, ks = bracket(ys, G1_POINT[1]), bracket(zs, G1_POINT[2])
    layers = (float(xs[i_lo]), float(xs[i_hi]))
    say(f'  layers   x = {layers[0]:.4f} and {layers[1]:.4f} m (cells '
        f'{i_lo}, {i_hi} of {len(xs)}), from spec.grid x_c; all '
        f'{len(ys)} x {len(zs)} y, z')
    as_stated = all(abs(a - b) < 1e-9 for a, b in zip(layers, LAYER_CENTRES))
    if not as_stated:
        say(f'  [REFUSED] the rule names the layers {LAYER_CENTRES}; this '
            f'grid does not have them')
        return out
    cand = [(i, j, k) for i in (i_lo, i_hi) for j in js for k in ks]
    say('  G1 cells ' + ', '.join(
        f'({xs[i]:.2f}, {ys[j]:.2f}, {zs[k]:.2f})' for i, j, k in cand))
    my, mz = footprint_masks(ys, zs)
    say(f'  panel    y {FOOT_Y[0]:g}-{FOOT_Y[1]:g} m, z {FOOT_Z[0]:g}-'
        f'{FOOT_Z[1]:g} m: {int(my.sum())} x {int(mz.sum())} cells per '
        f'layer (report only)')
    times = reader.list_times(unc)
    n = len(times)
    say(f'  times    {n} written times at the root, t = {times[0][0]:g} to '
        f'{times[-1][0]:g} s (processor* dirs are not read)')
    t = np.array([tv for tv, _name in times])
    Emax = {gm: np.full(n, np.nan) for gm in GAMMAS}
    where = {gm: np.full((n, 3), np.nan) for gm in GAMMAS}
    cells = np.full((n, len(cand), 5), np.nan)
    panel = {key: np.full(n, np.nan) for key in
             ['momentum'] + [('E', gm) for gm in GAMMAS]
             + [('strip', gm) for gm in GAMMAS]}
    nbytes = 0
    t0 = time.time()
    stamps = [t0]                           # the scan before
    scanner = _Scanner(scan, SCAN_EVERY_S).start()
    try:
        for w, (tv, name) in enumerate(times):
            tdir = os.path.join(unc, name)
            p, rho, U = read_slab(tdir, spec, i_lo, i_hi)
            nbytes += sum(os.path.getsize(os.path.join(tdir, f))
                          for f in ('p', 'U', 'rho')
                          if os.path.isfile(os.path.join(tdir, f)))
            E = {}
            for gm in GAMMAS:
                E[gm] = wl.wall_load(tv, p, U, rho, gm, normal=NORMAL)['E']
                Emax[gm][w], where[gm][w], _ijk = plane_max(
                    E[gm], xs[i_lo:i_hi + 1], ys, zs)
            for c, (i, j, k) in enumerate(cand):
                ii = i - i_lo
                cells[w, c] = (p[ii, j, k], rho[ii, j, k], *U[ii, j, k])
            for key, v in panel_numbers(p, rho, U, E, ys, zs, js).items():
                panel[key][w] = v
            if scanner.bad:
                say('  [ABORTED] while reading, the process scan '
                    + (f'saw {", ".join(scanner.hits)}' if scanner.hits
                       else f'failed: {scanner.error}'))
                return out
            if (w + 1) % 50 == 0 or w + 1 == n:
                say(f'  read     {w + 1}/{n} writes, t = {tv * 1e3:.3f} ms, '
                    f'{time.time() - t0:.0f} s')
    except (OSError, ValueError) as exc:
        say(f'  [ABORTED] reading failed: {exc}')
        return out
    finally:
        scanner.stop()
    wall = time.time() - t0
    hits = _checked(scan, say)
    stamps += scanner.stamps + [time.time()]
    gap = float(np.max(np.diff(sorted(stamps))))
    scanned_ok = not hits and not scanner.bad and gap <= 30.0
    say('  scan     after: ' + (', '.join(hits) if hits else
                                'no foam/MPI process')
        + f' ({len(stamps)} scans in all, every {SCAN_EVERY_S:g} s on a '
          f'timer while reading; the largest gap {gap:.1f} s)')
    after = _checked(fp, say, posix, failed={})
    for k, v in after.items():
        say(f'  after    {k} {v}')
    same = bool(before) and before == after
    say(f'  read     {n} writes, {nbytes:,} B of p/U/rho in {wall:.0f} s; '
        f'fingerprint before == after: {same}; scans clean and at most '
        f'30 s apart: {scanned_ok}')
    out['completed'] = True
    out['read_only'] = same and scanned_ok

    # the mapping check - P1 replaced by a measurement
    m = mapping_check(t, cells, probes['times'], probes['pressures'][0],
                      probes['rhos'][0], probes['velocities'][0],
                      t_min=t_min, expected_n=expected_n)
    say(f"\n  MAPPING CHECK - the eight cells around G1 against G1's probe, "
        f"at the {m['n']} writes after {t_min * 1e3:g} ms (the rule says "
        f"{expected_n}); nearest probe row, time mismatch at most "
        f"{m['t_mismatch']:.2e} relative")
    for c, (i, j, k) in enumerate(cand):
        d = m['cells'][c] if m['cells'] else None
        if d is None:
            continue
        say(f"    ({xs[i]:.2f}, {ys[j]:.2f}, {zs[k]:.2f}): max error p "
            f"{d['p']:.2e}, rho {d['rho']:.2e}, U {d['U']:.2e} -> "
            + ('MATCHES' if d['ok'] else 'no'))
    out['trusted'] = m['trusted']
    say('  Step 2 is ' + ('TRUSTED' if m['trusted'] else 'UNTRUSTED')
        + (f" - cell {cand[m['matched']]} is G1's" if m['matched'] is not None
           else ' - no cell matched at every write'))

    # the plane maximum through the example panel - reported only
    say('\n  THE PLANE MAXIMUM - E over both layers, every write')
    for gm in GAMMAS:
        i_pk = int(np.nanargmax(Emax[gm]))
        say(f'    gamma {gm:.2f}: at its peak the maximum sits at '
            f'({where[gm][i_pk][0]:.2f}, {where[gm][i_pk][1]:.2f}, '
            f'{where[gm][i_pk][2]:.2f}) m')
        s = summarize_trace(t, P_AIR + Emax[gm])
        say(f"      E peak {s['peak_kpa']:.2f} kPa at {s['t_peak_ms']:.3f} "
            f"ms; arrival {s['arrival_ms']:.3f} ms, positive phase "
            f"{s['pos_duration_ms']:.3f} ms, positive-phase impulse "
            f"{s['pos_impulse']:.2f} Pa s"
            + ('' if s['complete'] else
               ' - a LOWER BOUND: still positive when the record ends')
            + f"; net impulse {s['net_impulse']:.2f} Pa s")
        rs = responses(t, Emax[gm], comp, p_open)
        for tail in ('T0', 'T1'):
            r = rs[tail]
            late = r.t_ymax > rs['t_end']
            why = ('in free vibration once the load drops to zero'
                   if tail == 'T0' else 'set by the T1 hold')
            extra = (f" (E_tail {_kpa(rs['level'])} kPa held "
                     f"{TAIL_TN * comp.Tn * 1e3:.2f} ms)" if tail == 'T1'
                     else '')
            say(f'      {tail}{extra}: mu {r.ductility:.4f}, theta '
                f'{r.support_rotation_deg:.3f} deg, {r.regime}, collapsed '
                f'{r.collapsed}; peak response at {r.t_ymax * 1e3:.2f} ms'
                + (f' - after the record ends, {why}' if late else ''))
        out.setdefault('levels', {})[gm] = rs['level']
    say('\n  PANEL MEANS over the footprint - estimates, NOT bounds: a wall '
        'spreads the stagnation region wider than the free jet')
    for key in panel:
        v = panel[key]
        i_pk = int(np.nanargmax(v))
        lab = ('momentum flux max(0, p - P_AIR + rho un^2)'
               if key == 'momentum' else
               f"{'area mean of E' if key[0] == 'E' else 'strip mean of E at y = 6'}"
               f', gamma {key[1]:.2f}')
        say(f'    {lab}: peak {_kpa(v[i_pk])} kPa at {t[i_pk] * 1e3:.3f} ms')
    out.update(t=t, Emax=Emax, where=where, cells=cells, cand=cand,
               xs=xs, ys=ys, zs=zs, layers=layers, panel=panel, mapping=m,
               before=before, after=after, wall=wall, nbytes=nbytes)
    return out


def deliver_plane(res2, rule_sha, status, deliver, out=None, say=print):
    """The delivered plane file (and, with --out, the raw arrays)."""
    t, m, cand = res2['t'], res2['mapping'], res2['cand']
    xs, ys, zs = res2['xs'], res2['ys'], res2['zs']
    if m['matched'] is not None:
        best = m['matched']
        c_note = ("the cell that matches G1's probe at every write after "
                  "8 ms")
    else:
        errs = [max(d['p'], d['rho'], d['U']) for d in m['cells']]
        best = int(np.argmin(errs)) if errs else 0
        c_note = ("NO cell matched G1's probe at every write; these "
                  "columns hold the closest candidate")
    i, j, k = cand[best]
    cols, units, arrs = ['t'], ['s'], [t]
    for g in GAMMAS:
        cols += [f'Emax_{g:.2f}', f'x_{g:.2f}', f'y_{g:.2f}', f'z_{g:.2f}']
        units += ['Pa over P_AIR', 'm', 'm', 'm']
        arrs += [res2['Emax'][g], res2['where'][g][:, 0],
                 res2['where'][g][:, 1], res2['where'][g][:, 2]]
    cell = res2['cells'][:, best]
    cols += ['G1cell_p', 'G1cell_rho', 'G1cell_Ux', 'G1cell_Uy', 'G1cell_Uz']
    units += ['Pa', 'kg/m3', 'm/s', 'm/s', 'm/s']
    arrs += [cell[:, q] for q in range(5)]
    for g in GAMMAS:
        cols.append(f'G1cell_E_{g:.2f}')
        units.append('Pa over P_AIR')
        arrs.append(wl.wall_load(t, cell[:, 0], cell[:, 2:5], cell[:, 1], g,
                                 normal=NORMAL)['E'])
    cols.append('panel_momentum')
    units.append('Pa')
    arrs.append(res2['panel']['momentum'])
    for g in GAMMAS:
        cols += [f'panel_E_{g:.2f}', f'strip_E_{g:.2f}']
        units += ['Pa over P_AIR', 'Pa over P_AIR']
        arrs += [res2['panel'][('E', g)], res2['panel'][('strip', g)]]
    head = [
        f'HD1-13 route (b): the wall plane x = 10 m, every written time '
        f'({len(t)} rows, t = 0 included)',
        f'run {RUN_NAME} (HD1-3d), its reconstructed root time dirs, read '
        f'read-only (processor* not read); no solve',
        f'rule docs/hd13/vent3d_wall_rule.txt, sha256 {rule_sha}',
        f'Emax_g: the maximum of E = max(R, S) over the two cell layers '
        f'either side of x = 10 m (centres {res2["layers"][0]:.2f} and '
        f'{res2["layers"][1]:.2f} m), all y and z; x_g, y_g, z_g: the '
        f'centre of the cell it sits in. E is in Pa over P_AIR = 101325 Pa, '
        f'gamma 1.24 and 1.40, as in the G1 trace.',
        f'G1cell_*: cell ({xs[i]:.2f}, {ys[j]:.2f}, {zs[k]:.2f}) m - '
        + c_note + '.',
        'panel_*: report-only means over y 4.5-7.5 m, z 0-3 m, both '
        'layers (estimates, NOT bounds): panel_E_g the area mean of E, '
        'panel_momentum the area mean of max(0, p - P_AIR + rho un^2), '
        'strip_E_g the mean of E over z at the two y columns either side '
        'of y = 6 m.',
        't = 0: blastFoam writes no mixture rho at its start time; it is '
        'alpha.expl rho.expl + (1 - alpha.expl) rho.air (blastFoam User '
        'Guide v6.0, Eq. 2.10).',
        f'T1 (a rule, not baked in - its length belongs to the wall): '
        f'after the record ends at t = {t[-1]:.6g} s, hold E_tail = '
        f'max(p_open - P_AIR, max E) for 1.5 Tn of the wall being checked; '
        f'E_tail for Emax: '
        + ', '.join(f'gamma {g:.2f} {res2["levels"][g]:.1f} Pa'
                    for g in GAMMAS) + '.',
        f'status: {status}',
    ]
    path = write_table(os.path.join(deliver, PLANE_FILE), head, cols, units,
                       arrs)
    say(f'  delivered {path} ({len(t)} rows)')
    if out:
        raw = os.path.join(out, 'vent3d_wall_plane_raw.npz')
        np.savez(raw, t=t, cells=res2['cells'], cand=np.array(cand),
                 **{f'Emax_{g:.2f}': res2['Emax'][g] for g in GAMMAS})
        say(f'  delivered {raw}')
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--evidence', default=DEFAULT_EVIDENCE)
    ap.add_argument('--deliver', default=DELIVER)
    ap.add_argument('--out', default=None)
    ap.add_argument('--record', default=None)
    ap.add_argument('--plane', action='store_true',
                    help='also run Step 2 (reads the run, WSL)')
    ap.add_argument('--run', default=RUN_NAME)
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
    p2, p3 = res1['p2']['ok'], res1['p3']['ok']
    if not args.plane:
        status = ('Step 1 only - Step 2 (the plane) not run, so no bound is '
                  'claimed yet: ' + step1_status(p2, p3))
        print()
        deliver_traces(res1, probes, rule_sha, status, args.deliver,
                       args.out)
        return 0

    try:
        res2 = step2(cfd, probes, args.run, comp, st.p)
    except Exception as exc:                # noqa: BLE001 - it is the outcome
        print(f'  [ABORTED] Step 2 raised {type(exc).__name__}: {exc}')
        res2 = dict(read_only=False, trusted=False, completed=False)
    read_only, trusted = res2['read_only'], res2['trusted']
    label, why = outcome(p2, p3, trusted, read_only)
    if label == BOUND:
        status = ('BOUND - an upper bound on the load a wall at x = 10 m '
                  'takes during the record, unrelieved by clearing and '
                  'taken as uniform over the wall; beyond the record the '
                  'T1 rule applies (docs/hd13/vent3d_wall_rule.txt)')
    else:
        status = ('NOT ESTABLISHED - NOT a bound on the wall load: '
                  + '; '.join(why))
    print('\nTHE RULE\'S CONDITIONS')
    print(f"  P2 {'holds' if p2 else 'FAILS'}; P3 {'holds' if p3 else 'FAILS'}"
          f"; Step 2 run read-only: {'yes' if read_only else 'NO'}; Step 2 "
          f"trusted (mapping check): {'yes' if trusted else 'NO'}")
    print('\nDELIVERED')
    deliver_traces(res1, probes, rule_sha, status, args.deliver, args.out)
    if res2['completed']:
        deliver_plane(res2, rule_sha, status, args.deliver, args.out)
    print()
    print(outcome_line(p2, p3, trusted, read_only))
    return 0


if __name__ == '__main__':
    sys.exit(main())
