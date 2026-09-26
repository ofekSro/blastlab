"""HD1-16 step 1: the HD 1.3 chamber load as SBEDS-ready CSV files.

blastlab gives the LOAD, not the response (TODO.md HD1-16). The structural
response is SBEDS's job, and SBEDS applies a user-defined load exactly as
given, so what is written here has to be the load on the wall and has to
say so.

THE FORMAT (owner decision, 2026-09-26, which overrides the column spec
in TODO.md HD1-16 item 1)
    <stem>.csv  exactly two comma-separated columns, t [ms] and
                overpressure [kPa], one row per sample. No header, no
                comment line, nothing else - e.g. `0.0,100.0`. Negative
                values are written as computed: SBEDS accepts them (owner,
                2026-09-26), so suction is not clipped.
    <stem>.txt  the sidecar: everything that was to go in a header - the
                source case, which trace, the load type, gamma, the psi
                factor, the net impulse over the record and, when it
                fires, the "still active" line.

INTERPRETATIONS, registered here before any output is judged by them
(batch plan docs/batches/2026-09-26-hd1-16-load-export.md, Step 2):
  * Overpressure is p - P_AIR (101325 Pa, core/constants.P_AIR), the same
    p_ref the SDOF path used. Not absolute.
  * Numbers are written with repr(float), the shortest round-trip form,
    so reading a file back gives the writer's float64 values exactly:
    t_ms == 1e3 * t and p_kPa == (p - P_AIR) / 1e3, bit for bit.
  * Encoding: UTF-8 without BOM, LF line ends, written by Python `open`
    (never through PowerShell, CLAUDE.md 8.1). The CSV is pure ASCII by
    construction; the sidecar is kept ASCII too ("kPa*ms", "gamma"), so
    a tool that expects ASCII is not broken by it.
  * Impulse is not a column (owner, 2026-09-26). The sidecar gives the net
    impulse over the whole record, the cumulative trapezoid of the two
    columns as written, starting at 0 at the first sample.
  * psi is not a column either; the sidecar gives the factor,
    1 psi = 6.894757293168361 kPa.
  * NO TAIL (owner, 2026-09-25, HD1-16 2a): the trace ends at the run's
    last sample; core/wallload.extend_with_tail is not called. If the load
    has not returned to ambient by then - some |p_over| in the samples with
    t >= t_last - LOAD_ACTIVE_WINDOW_S (the last sample always included)
    exceeds LOAD_ACTIVE_FRACTION of the trace's max |p_over| - the sidecar
    and the returned message say exactly
    "record ends while the load is still active: p = <kPa> kPa at t = <ms> ms"
    with the last sample's values. The 0-D output is sparse (60 ms
    spacing at t_end = 60 s, n_out = 1000), so the window often holds the
    last sample alone.

WHICH TRACES (the HD 1.3 assessment, `export_hd13`)
  * nominal.csv  `out['confined']`, the assessment's own chamber run.
  * band_<signs>.csv  with the band on, one per run the band made: every
    corner and, when check_corners ran, every face centre. <signs> is the
    sign per axis of sensitivity.PARAMS (n, a, p_extinction, h_c, cd),
    two characters each, '+1', '-1' or '+0' (the axis at its nominal),
    e.g. band_+1-1+1+1+1. The band's own nominal sample (all '+0') is
    written as band_nominal.csv only if its (t, p) differ from
    out['confined']; when identical, nominal.txt says so and the file is
    not duplicated.
  * Load type: a 0-D chamber pressure is neither side-on nor reflected;
    every sidecar says so (LOAD_CHAMBER).
  * gamma: the products' prop.gamma, which the chamber model mass-weights
    with the room air (deflagration.mixture); the sidecar says both.
  * Files go to `<report stem>_loads/` beside the report. Files a previous
    export left there under the same naming (nominal.*, band_*.*) are
    removed first, so a band-off re-run does not leave stale band files
    beside a new nominal.

THE WALL-LOAD CFD TRACES (G1 and plane-max x gamma 1.24 / 1.40, HD1-13)
are exported by `export_wall_loads` below (Step 2b), not with the chamber
trace: their load definition and the optional clearing of UFC 3-340-02
(2008), para. 2-15.3.2 (printed p. 65, Eq. 2-8 / 2-9) need the wall's
H and W, which the chamber trace does not.

Pure: no Qt, no pyplot, no VTK (tests/test_layering.py).
"""

import glob
import os

import numpy as np

from ..core.constants import P_AIR

#: HD1-16 2a (owner, 2026-09-25): the load is still active at the end of
#: the record if any |p_over| in the last LOAD_ACTIVE_WINDOW_S exceeds
#: this fraction of the trace's max |p_over|.
LOAD_ACTIVE_FRACTION = 0.01
#: HD1-16 2a (owner, 2026-09-25): the end-of-record window [s].
LOAD_ACTIVE_WINDOW_S = 1.0e-3

#: kPa per psi (1 psi = 6894.757293168361 Pa, exact by definition of the
#: pound-force and the inch).
KPA_PER_PSI = 6.894757293168361

#: The fixed load-type line of a 0-D chamber trace (batch plan, Step 2).
LOAD_CHAMBER = ('load: chamber pressure, quasi-static and uniform (not '
                'side-on, not reflected); acts on the inner face of the '
                'chamber wall as given')

#: Said in a chamber sidecar whenever the trace goes below ambient: the
#: 0-D vent passes no flow while the chamber is below ambient
#: (core/deflagration.py, the vent mass-flow function), so suction after
#: venting and wall cooling is not relieved by air flowing back in.
NO_INFLOW = ('note: this trace goes below ambient. The 0-D chamber model '
             'has no inflow through the vent (core/deflagration.py), so a '
             'sub-ambient pressure after venting and wall cooling is not '
             'relieved by air flowing back in; the negative values are as '
             'that model computed them')

STILL_ACTIVE = ('record ends while the load is still active: '
                'p = {p:.6g} kPa at t = {t:.6g} ms')


def _f(x):
    """Shortest round-trip text of a float (never numpy's repr)."""
    return repr(float(x))


def still_active(t_ms, p_kpa):
    """The HD1-16 2a message, or None if the load is back near ambient.

    `t_ms`, `p_kpa`: the columns as written. The window is the samples
    with t >= t_last - LOAD_ACTIVE_WINDOW_S (in ms), last sample always
    included."""
    t = np.asarray(t_ms, dtype=float)
    p = np.asarray(p_kpa, dtype=float)
    peak = float(np.max(np.abs(p))) if len(p) else 0.0
    if not peak > 0.0:
        return None
    win = t >= t[-1] - LOAD_ACTIVE_WINDOW_S * 1e3
    win[-1] = True
    if np.any(np.abs(p[win]) > LOAD_ACTIVE_FRACTION * peak):
        return STILL_ACTIVE.format(p=float(p[-1]), t=float(t[-1]))
    return None


def net_impulse(t_ms, p_kpa):
    """Net impulse over the record [kPa*ms]: trapezoid of the columns."""
    return float(np.trapezoid(np.asarray(p_kpa, dtype=float),
                              np.asarray(t_ms, dtype=float)))


def write_trace(csv_path, t_ms, p_kpa, sidecar_lines):
    """Write one two-column CSV and its sidecar `.txt` (same stem).

    `t_ms`, `p_kpa` are written as given with repr(float). The sidecar
    gets `sidecar_lines`, then the rows, peak and net impulse, then the
    "still active" line when the HD1-16 2a rule fires. Returns that
    message or None."""
    t = [float(x) for x in t_ms]
    p = [float(x) for x in p_kpa]
    if len(t) != len(p) or len(t) < 2:
        raise ValueError('a trace needs at least two samples, as many '
                         'pressures as times')
    with open(csv_path, 'w', encoding='utf-8', newline='\n') as f:
        for ti, pi in zip(t, p):
            f.write(f'{_f(ti)},{_f(pi)}\n')
    msg = still_active(t, p)
    k = int(np.argmax(p))
    lines = [f'file: {os.path.basename(csv_path)}',
             'format: two comma-separated columns, no header: t [ms], '
             'overpressure [kPa]']
    lines += list(sidecar_lines)
    lines += [f'rows: {len(t)}, t from {t[0]:.6g} to {t[-1]:.6g} ms',
              f'peak overpressure: {p[k]:.6g} kPa at t = {t[k]:.6g} ms',
              f'min overpressure: {min(p):.6g} kPa',
              f'net impulse over the record (trapezoid of the two columns, '
              f'negative phase included): {_f(net_impulse(t, p))} kPa*ms',
              f'psi: p [psi] = p [kPa] / {KPA_PER_PSI!r}',
              'negative values: written as computed (SBEDS accepts them, '
              'owner 2026-09-26)',
              'tail: none - the record ends at the run\'s last sample '
              '(TODO.md HD1-16 2a, owner 2026-09-25)']
    if msg:
        lines.append(msg)
    with open(os.path.splitext(csv_path)[0] + '.txt', 'w',
              encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    return msg


def read_trace(csv_path):
    """(t_ms, p_kpa) float64 arrays back from a two-column CSV; raises
    ValueError on any line that is not exactly two floats."""
    t, p = [], []
    with open(csv_path, encoding='utf-8') as f:
        for n, line in enumerate(f, 1):
            parts = line.rstrip('\n').split(',')
            if len(parts) != 2:
                raise ValueError(f'{csv_path}:{n}: not two columns')
            t.append(float(parts[0]))
            p.append(float(parts[1]))
    return np.array(t), np.array(p)


def _signs_tag(signs):
    return ''.join(f'{int(s):+d}' for s in signs)


def _pa_to_kpa_over(p):
    return (np.asarray(p, dtype=float) - P_AIR) / 1e3


def _clear_old(d):
    for pat in ('nominal.csv', 'nominal.txt', 'band_*.csv', 'band_*.txt'):
        for old in glob.glob(os.path.join(d, pat)):
            os.remove(old)


def loads_dir(report_path):
    """`<report stem>_loads`, beside the report."""
    return os.path.splitext(report_path)[0] + '_loads'


def export_hd13(out, report_path, case_name=''):
    """Write every chamber trace of an `assessment.run` output.

    Returns dict(dir, files, messages): the directory, the CSV paths
    written, and [(csv name, message)] for every trace the HD1-16 2a rule
    flagged. With no confined result nothing is written and `dir` is None.
    """
    conf = out.get('confined')
    if conf is None:
        return dict(dir=None, files=[], messages=[])
    d = loads_dir(report_path)
    os.makedirs(d, exist_ok=True)
    _clear_old(d)
    prop = out['prop']
    common = [
        f'case: {case_name or "(unnamed)"}',
        f'p_ref: {P_AIR!r} Pa (core.constants.P_AIR); overpressure over '
        f'ambient, not absolute',
        LOAD_CHAMBER,
        f'gamma: {prop.gamma:g} (the products, prop.gamma; the chamber '
        f'model mass-weights it with the room air, deflagration.mixture)',
        'source: blastlab HD 1.3 assessment, 0-D chamber model '
        '(core/deflagration.simulate); TODO.md HD1-16']
    files, messages = [], []

    def one(name, t, p, trace_line, extra=()):
        path = os.path.join(d, name)
        p_k = _pa_to_kpa_over(p)
        lines = common + [trace_line] + list(extra)
        if len(p_k) and float(np.min(p_k)) < 0.0:
            lines.append(NO_INFLOW)
        msg = write_trace(path, 1e3 * np.asarray(t, dtype=float), p_k,
                          lines)
        files.append(path)
        if msg:
            messages.append((name, msg))

    b = out.get('band')
    extra = []
    band_nominal, same = None, True
    if b is not None and 'traces' in b:
        for signs, t, p in b['traces']:
            if not any(signs):
                band_nominal = (t, p)
        if band_nominal is not None:
            same = (np.array_equal(np.asarray(band_nominal[0], dtype=float),
                                   np.asarray(conf['t'], dtype=float))
                    and np.array_equal(
                        np.asarray(band_nominal[1], dtype=float),
                        np.asarray(conf['p'], dtype=float)))
            if same:
                extra.append('the sensitivity band\'s own nominal sample '
                             '(all signs +0) is identical to this trace '
                             'and is not written again')
            else:
                extra.append('the sensitivity band\'s own nominal sample '
                             'differs from this trace and is written as '
                             'band_nominal.csv')
    one('nominal.csv', conf['t'], conf['p'],
        'trace: nominal (the assessment\'s own chamber run)', extra)

    if b is not None and 'traces' in b:
        axes = ', '.join(b.get('params', ()))
        hc = ('yes' if b.get('spans_heat_loss')
              else 'no (adiabatic, the h_c sign is inert)')
        cd = ('yes' if b.get('spans_cd')
              else 'no (closed vessel, the cd sign is inert)')
        spans = f'axes spanned: h_c {hc}, cd {cd}'
        for signs, t, p in b['traces']:
            if not any(signs):
                if not same:
                    one('band_nominal.csv', t, p,
                        'trace: sensitivity-band nominal sample '
                        f'(signs over ({axes}): {_signs_tag(signs)})',
                        [spans])
                continue
            one(f'band_{_signs_tag(signs)}.csv', t, p,
                f'trace: sensitivity-band sample, signs over ({axes}): '
                f'{_signs_tag(signs)}', [spans])
    return dict(dir=d, files=files, messages=messages)
