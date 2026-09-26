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
are exported by `export_wall_loads` (Step 2b, owner answer Q1 of
2026-09-26), not with the chamber trace: their load definition and the
optional clearing of UFC 3-340-02 (2008), para. 2-15.3.2 (printed p. 65,
Eq. 2-8 / 2-9) need the wall's H and W, which the chamber trace does not.
Pre-registered interpretation (batch plan Step 2b; the owner may correct
it):
  * Source: the committed HD1-13 files in docs/hd13/ (no WSL, no solve),
    `vent3d_wall_load_G1.txt` (the G1 probe, 3395 rows: R, S, E per gamma)
    and `vent3d_wall_plane.txt` (749 writes: Emax per gamma, and G1cell_p,
    G1cell_rho, G1cell_U*). Each file's units line is checked against
    the one this parser was written for, and a mismatch is refused.
  * Traces: G1 x {1.24, 1.40} and plane-max x {1.24, 1.40}, four files per
    clearing setting: `{G1,planemax}_g{124,140}[_cleared].csv`.
  * Clearing off: the file's E = max(R, S) as HD1-13 computed it, in kPa
    (E / 1e3, bit for bit), "reflected + stagnation, no clearing, upper
    bound".
  * Clearing on (G1 ONLY): core/wallload.apply_clearing with the case's
    wall H and W. Ps = G1cell_p - P_AIR and q = rho un^2 / 2 with
    un = max(Ux, 0) (the wall at x = 10 m faces -x), from the 749 writes
    (not the probe), interpolated linearly onto the probe times. C_r from
    Rankine-Hugoniot at the trace's peak reflected state with the trace's
    gamma: ps_peak = the side-on overpressure whose normal reflection is
    max R (wallload.incident_from_reflected), then
    wallload.reflected_sound_speed. The Eq. 2-10 check is not applied,
    and the sidecar says so.
  * Plane-max is a maximum over different cells at different times, not a
    point on a wall, so clearing is not defined for it: it is always
    exported unrelieved, and its sidecar says why.
  * These traces come from ONE CFD run (HD1-3d); the case supplies only
    the wall (clearing, H, W). Every sidecar names the run.

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


def still_active(t_ms, p_kpa) -> str | None:
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


def net_impulse(t_ms, p_kpa) -> float:
    """Net impulse over the record [kPa*ms]: trapezoid of the columns."""
    return float(np.trapezoid(np.asarray(p_kpa, dtype=float),
                              np.asarray(t_ms, dtype=float)))


def write_trace(csv_path: str, t_ms, p_kpa, sidecar_lines) -> str | None:
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


def read_trace(csv_path: str) -> tuple[np.ndarray, np.ndarray]:
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
    """(1, -1, 0) -> '+1-1+0', the band file-name tag."""
    return ''.join(f'{int(s):+d}' for s in signs)


def _pa_to_kpa_over(p):
    """Absolute pressure [Pa] -> overpressure over P_AIR [kPa]."""
    return (np.asarray(p, dtype=float) - P_AIR) / 1e3


def _same_trace(a, b):
    """True if the (t, p) traces `a` and `b` are equal sample for sample."""
    t_a, p_a = a
    t_b, p_b = b
    return (np.array_equal(np.asarray(t_a, dtype=float),
                           np.asarray(t_b, dtype=float))
            and np.array_equal(np.asarray(p_a, dtype=float),
                               np.asarray(p_b, dtype=float)))


#: The files each export owns in its directory. They are removed before it
#: writes, so a re-run that writes fewer traces (band off, clearing off)
#: leaves no stale file beside the new ones (fix 95a62ce).
_HD13_PATTERNS = ('nominal.csv', 'nominal.txt', 'band_*.csv', 'band_*.txt')
_WALL_PATTERNS = ('G1_g*.csv', 'G1_g*.txt', 'planemax_g*.csv',
                  'planemax_g*.txt')


def _remove_old(d, patterns):
    """Delete the files a previous export left in `d` under `patterns`."""
    for pat in patterns:
        for old in glob.glob(os.path.join(d, pat)):
            os.remove(old)


def _write_and_record(d, name, t_ms, p_kpa, lines, files, messages):
    """`write_trace` into `d/name`; append the path to `files` and, if the
    still-active rule fired, (name, message) to `messages`."""
    path = os.path.join(d, name)
    msg = write_trace(path, t_ms, p_kpa, lines)
    files.append(path)
    if msg:
        messages.append((name, msg))


def loads_dir(report_path: str) -> str:
    """`<report stem>_loads`, beside the report."""
    return os.path.splitext(report_path)[0] + '_loads'


def export_hd13(out: dict, report_path: str, case_name: str = '') -> dict:
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
    _remove_old(d, _HD13_PATTERNS)
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
        p_k = _pa_to_kpa_over(p)
        lines = common + [trace_line] + list(extra)
        if len(p_k) and float(np.min(p_k)) < 0.0:
            lines.append(NO_INFLOW)
        _write_and_record(d, name, 1e3 * np.asarray(t, dtype=float), p_k,
                          lines, files, messages)

    b = out.get('band')
    has_band = b is not None and 'traces' in b
    extra = []
    # True unless the band's own nominal sample exists and differs from
    # out['confined']; only then is it written as band_nominal.csv
    same = True
    if has_band:
        band_nominal = None
        for signs, t, p in b['traces']:
            if not any(signs):
                band_nominal = (t, p)
        if band_nominal is not None:
            same = _same_trace(band_nominal, (conf['t'], conf['p']))
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

    if has_band:
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


# ── the HD1-13 wall-load traces (Step 2b) ────────────────────────────────

#: Where the committed HD1-13 traces live.
WALL_LOAD_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'docs', 'hd13'))
G1_FILE = 'vent3d_wall_load_G1.txt'
PLANE_FILE = 'vent3d_wall_plane.txt'

#: The units lines the parser was written for, verbatim. A file whose
#: units line differs is refused rather than read under a guess.
G1_UNITS = ('# units: t [s]; un [m/s]; R_1.24 [Pa over P_AIR]; '
            'S_1.24 [Pa over P_AIR]; E_1.24 [Pa over P_AIR]; M_1.24 [-]; '
            'R_1.40 [Pa over P_AIR]; S_1.40 [Pa over P_AIR]; '
            'E_1.40 [Pa over P_AIR]; M_1.40 [-]')
PLANE_UNITS = ('# units: t [s]; Emax_1.24 [Pa over P_AIR]; x_1.24 [m]; '
               'y_1.24 [m]; z_1.24 [m]; Emax_1.40 [Pa over P_AIR]; '
               'x_1.40 [m]; y_1.40 [m]; z_1.40 [m]; G1cell_p [Pa]; '
               'G1cell_rho [kg/m3]; G1cell_Ux [m/s]; G1cell_Uy [m/s]; '
               'G1cell_Uz [m/s]; G1cell_E_1.24 [Pa over P_AIR]; '
               'G1cell_E_1.40 [Pa over P_AIR]; panel_momentum [Pa]; '
               'panel_E_1.24 [Pa over P_AIR]; strip_E_1.24 [Pa over P_AIR]; '
               'panel_E_1.40 [Pa over P_AIR]; strip_E_1.40 [Pa over P_AIR]')

GAMMAS = ('1.24', '1.40')

#: 1 ft/ms in m/s, to quote C_r in the units of UFC 3-340-02 Fig. 2-192.
M_S_PER_FT_MS = 304.8

LOAD_G1_UNRELIEVED = (
    'load: reflected + stagnation, no clearing, upper bound - '
    'E = max(R, S) at G1 as HD1-13 computed it (R the Rankine-Hugoniot '
    'normal reflection, S the compressible stagnation of un = max(Ux, 0)), '
    'unrelieved by clearing and taken as uniform over the wall')
LOAD_PLANEMAX = (
    'load: reflected + stagnation, no clearing, upper bound - the maximum '
    'of E = max(R, S) over the wall plane x = 10 m at each write. It is a '
    'maximum over different cells at different times, not a point on a '
    'wall, so clearing is not defined for it and it is always exported '
    'unrelieved, whatever the clearing setting')


def read_hd13_table(path: str, units: str) -> tuple[list[str], dict]:
    """(header comment lines, {column: float64 array}) of one HD1-13
    trace file; ValueError unless its units line is exactly `units`."""
    comments, cols, rows = [], None, []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith('#'):
                comments.append(line)
            elif cols is None:
                cols = line.split()
            elif line.strip():
                rows.append([float(x) for x in line.split()])
    got = [c for c in comments if c.startswith('# units:')]
    if got != [units]:
        raise ValueError(f'{os.path.basename(path)}: the units line is not '
                         f'the one this parser expects; refusing to guess.\n'
                         f'  expected: {units}\n  found:    {got}')
    data = np.array(rows, dtype=float)
    if data.ndim != 2 or data.shape[1] != len(cols):
        raise ValueError(f'{os.path.basename(path)}: ragged table')
    return comments, {c: data[:, i] for i, c in enumerate(cols)}


def _source_lines(name, comments):
    """The provenance lines of an HD1-13 file, for a sidecar."""
    keep = [c[2:] for c in comments
            if c.startswith(('# HD1-13', '# run', '# status'))]
    return [f'source file: docs/hd13/{name}'] + [f'  {k}' for k in keep]


def _gamma_line(g):
    """The sidecar's gamma line for the HD1-13 column gamma `g`."""
    what = 'the double_base products' if g == '1.24' else 'air'
    return (f'gamma: {g} ({what}; HD1-13 computed E at both because '
            f'they bound any mixture)')


def _gamma_tag(g):
    """'1.24' -> 'g124', the file-name tag of a gamma."""
    return 'g' + g.replace('.', '')


def _cleared_lines(g, H, W, res, c_r, r_max, ps_peak):
    """The sidecar lines that describe a cleared G1 trace: what was done
    (UFC 3-340-02 (2008) para. 2-15.3.2), with which wall and C_r."""
    from ..core import wallload
    ta = ('never (the trace does not rise)' if res['t_a'] is None
          else f'{res["t_a"] * 1e3:.6g} ms')
    return [
        f'trace: G1, the probe at (10, 6, 1.4) m, column E_{g}, '
        f'after clearing',
        'load: front-wall load after clearing, UFC 3-340-02 (2008) '
        'para. 2-15.3.2, Eq. 2-8 / 2-9, Fig. 2-191a (printed pp. '
        '65, 266): L = E before arrival t_a, a linear blend '
        '(1 - tau/t_c) E + (tau/t_c)(Ps + C_D q) for 0 <= tau = '
        't - t_a <= t_c, then Ps + C_D q',
        f'wall: H = {H:g} m, W = {W:g} m; S = min(H, W/2) = '
        f'{res["S"]:g} m, G = max(H, W/2) = {res["G"]:g} m, R = S/G '
        f'= {res["R"]:.6g}',
        f'C_r = {c_r:.6g} m/s ({c_r / M_S_PER_FT_MS:.6g} ft/ms): '
        f'Rankine-Hugoniot at the peak reflected state, max R_{g} = '
        f'{r_max / 1e3:.6g} kPa -> side-on {ps_peak / 1e3:.6g} kPa, '
        f'gamma {g}, ambient {P_AIR:g} Pa / RHO_AIR (UFC 3-340-02 '
        f'Fig. 2-192 is for air, gamma 1.4)',
        f't_c = 4 S / ((1 + R) C_r) = {res["t_c"] * 1e3:.6g} ms '
        f'(Eq. 2-8); arrival t_a = {ta}, the first sample above '
        f'{wallload.CLEARING_ARRIVAL_FRACTION:g} of peak E; '
        f'C_D = {wallload.C_D_FRONT:g} (front wall, para. 2-15.3.2)',
        'Ps = G1cell_p - P_AIR and q = rho un^2 / 2, un = '
        'max(G1cell_Ux, 0), from docs/hd13/vent3d_wall_plane.txt '
        '(the 749 writes, cell (9.95, 5.95, 1.35) m, which matches '
        'the G1 probe at every write after 8 ms), NOT from the '
        'probe; interpolated linearly onto the probe times',
        'Eq. 2-10 check (fictitious duration t_rf = 2 i_r / P_r, '
        'keep the smaller impulse): NOT applied - it is meant for '
        'idealised triangles, not a computed trace']


def wall_load_traces(case, src_dir: str = WALL_LOAD_DIR) -> tuple[list, dict]:
    """The wall-load traces of the export, without writing anything.

    Returns [(csv name, t [s], load [Pa over ambient], sidecar lines)],
    G1 then plane-max, gamma 1.24 then 1.40, and the dict of clearing
    parameters per gamma (empty with clearing off)."""
    from ..core import wallload
    g1_c, g1 = read_hd13_table(os.path.join(src_dir, G1_FILE), G1_UNITS)
    pl_c, pl = read_hd13_table(os.path.join(src_dir, PLANE_FILE),
                               PLANE_UNITS)
    clearing = bool(getattr(case, 'clearing', False))
    common = [f'case: {getattr(case, "name", "") or "(unnamed)"} - the case '
              f'supplies only the loaded wall (clearing, H, W); the traces '
              f'are from the one HD1-13 CFD run named below',
              f'p_ref: {P_AIR!r} Pa (core.constants.P_AIR); overpressure '
              f'over ambient, not absolute',
              'the T1 tail of docs/hd13/vent3d_wall_rule.txt is NOT '
              'exported (TODO.md HD1-16 2a, owner 2026-09-25)']
    t = g1['t']
    if clearing:
        # The same for both gammas: the wall, and the G1 cell's Ps and q
        # (from the 749 plane writes) on the probe times. The wall at
        # x = 10 m faces -x, so only un = max(Ux, 0) loads it.
        H, W = float(case.wall_H_m), float(case.wall_W_m)
        ps = np.interp(t, pl['t'], pl['G1cell_p'] - P_AIR)
        un = np.maximum(pl['G1cell_Ux'], 0.0)
        q = np.interp(t, pl['t'], 0.5 * pl['G1cell_rho'] * un * un)

    out, params = [], {}
    for g in GAMMAS:
        tag, gam = _gamma_tag(g), _gamma_line(g)
        if not clearing:
            out.append((f'G1_{tag}.csv', t, g1[f'E_{g}'],
                        common + ['trace: G1, the probe at (10, 6, 1.4) m, '
                                  f'column E_{g}', LOAD_G1_UNRELIEVED, gam]
                        + _source_lines(G1_FILE, g1_c)))
            continue
        # C_r from Rankine-Hugoniot at the trace's peak reflected state
        r_max = float(np.max(g1[f'R_{g}']))
        ps_peak = float(wallload.incident_from_reflected(
            r_max, float(g), P_AIR))
        c_r = wallload.reflected_sound_speed(ps_peak, float(g), P_AIR)
        res = wallload.apply_clearing(t, g1[f'E_{g}'], ps, q, H, W, c_r)
        params[g] = dict(res, c_r=c_r, ps_peak=ps_peak, r_max=r_max)
        lines = (common
                 + _cleared_lines(g, H, W, res, c_r, r_max, ps_peak)
                 + [gam]
                 + _source_lines(G1_FILE, g1_c)
                 + _source_lines(PLANE_FILE, pl_c))
        out.append((f'G1_{tag}_cleared.csv', t, res['L'], lines))
    for g in GAMMAS:
        out.append((f'planemax_{_gamma_tag(g)}.csv', pl['t'],
                    pl[f'Emax_{g}'],
                    common + [f'trace: plane maximum, column Emax_{g}',
                              LOAD_PLANEMAX, _gamma_line(g)]
                    + _source_lines(PLANE_FILE, pl_c)))
    return out, params


def wall_loads_dir(case_path: str) -> str:
    """`<case stem>_wall_loads`, beside the case file."""
    return os.path.splitext(case_path)[0] + '_wall_loads'


def export_wall_loads(case, out_dir: str,
                      src_dir: str = WALL_LOAD_DIR) -> dict:
    """Write the four wall-load CSVs (+ sidecars) of `case` to `out_dir`.

    Returns dict(dir, files, messages, params) as `export_hd13` does, plus
    the clearing parameters per gamma. The caller validates the case
    first (core/assessment.wall_errors). Files a previous export left in
    `out_dir` under the same naming (G1_g*.*, planemax_g*.*) are removed
    first, as `export_hd13` does, so a clearing-off re-run does not leave
    stale `_cleared` files beside the new unrelieved ones."""
    traces, params = wall_load_traces(case, src_dir)
    os.makedirs(out_dir, exist_ok=True)
    _remove_old(out_dir, _WALL_PATTERNS)
    files, messages = [], []
    for name, t, load, lines in traces:
        # t [s] -> [ms], load [Pa over ambient] -> [kPa]
        _write_and_record(out_dir, name, 1e3 * np.asarray(t, dtype=float),
                          np.asarray(load, dtype=float) / 1e3, lines,
                          files, messages)
    return dict(dir=out_dir, files=files, messages=messages, params=params)
