"""Per-gauge engineering summary from a pressure-time history (N2).

For each gauge trace (t, p): peak overpressure, arrival time, time of
peak, positive-phase duration, positive-phase impulse and net impulse.
The arrival rule is the one the foam-vs-native physics gates use
(`test_foam_1d_vs_native`): the first sample with p > (1 + ARRIVAL_FRAC)
* p_ambient. The positive phase runs from that sample to the first zero
crossing of the overpressure after the peak (linearly interpolated); its
impulse is the trapezoidal integral of max(p - p_ambient, 0) over that
window (ROADMAP B9: the blast-engineering "impulse"), while the net
impulse integrates the signed overpressure over the whole record (what
the field maps accumulate). Pure numpy; the CSV writer never touches the
byte-pinned gauge TSVs.
"""

import csv
import math

import numpy as np

from ..core.constants import P_AIR

#: arrival = first sample above (1 + ARRIVAL_FRAC) * ambient
ARRIVAL_FRAC = 0.10

_trapz = getattr(np, 'trapezoid', None) or np.trapz

COLUMNS = ('gauge', 'peak_overpressure_kPa', 'arrival_ms',
           'time_of_peak_ms', 'positive_phase_duration_ms',
           'positive_phase_impulse_Pa_s', 'net_impulse_Pa_s',
           'positive_phase_complete')


def summarize_trace(times, p, p_ambient=P_AIR, arrival_frac=ARRIVAL_FRAC):
    """Engineering numbers for one gauge. Returns a dict with keys
    peak_kpa, t_peak_ms, arrival_ms, pos_duration_ms, pos_impulse,
    net_impulse (Pa s), complete (False when the record ends inside the
    positive phase - duration and impulse are then lower bounds). Times
    are NaN when the gauge never sees the shock."""
    t = np.asarray(times, dtype=float)
    p = np.asarray(p, dtype=float)
    out = dict(peak_kpa=np.nan, t_peak_ms=np.nan, arrival_ms=np.nan,
               pos_duration_ms=np.nan, pos_impulse=np.nan,
               net_impulse=np.nan, complete=False)
    n = min(len(t), len(p))
    if n < 2:
        return out
    t, p = t[:n], p[:n]
    ovp = p - p_ambient
    i_pk = int(np.argmax(ovp))
    out['peak_kpa'] = float(ovp[i_pk]) / 1e3
    out['t_peak_ms'] = float(t[i_pk]) * 1e3
    out['net_impulse'] = float(_trapz(ovp, t))
    hit = np.flatnonzero(p > (1.0 + arrival_frac) * p_ambient)
    if not len(hit):
        return out
    i_arr = int(hit[0])
    out['arrival_ms'] = float(t[i_arr]) * 1e3
    # end of the first positive phase: first non-positive sample after the peak
    j = i_pk
    while j < n and ovp[j] > 0.0:
        j += 1
    pos = np.clip(ovp, 0.0, None)
    if j < n:                       # zero crossing between j-1 and j
        a, b = ovp[j - 1], ovp[j]
        frac = a / (a - b) if a != b else 0.0
        t_end = t[j - 1] + frac * (t[j] - t[j - 1])
        imp = float(_trapz(pos[i_arr:j], t[i_arr:j]))
        imp += 0.5 * a * (t_end - t[j - 1])      # triangle to the crossing
        out['complete'] = True
    else:                           # record ends inside the positive phase
        t_end = t[-1]
        imp = float(_trapz(pos[i_arr:], t[i_arr:]))
    out['pos_duration_ms'] = float(t_end - t[i_arr]) * 1e3
    out['pos_impulse'] = imp
    return out


def gauge_labels(gauge_out, requested=None):
    """One label per gauge.

    1D: 'G1  r = 1.000 m'. 2D/3D: 'G1 (0.300, 0.800)' when the gauge sits
    where it was asked for, and 'G1 (0.300, 0.800) -> cell (0.305, 0.802)'
    when the solver snapped it to a cell centre - the table used to show
    the snapped numbers alone, which read as a typo in the user's input
    (QA-33). `requested` is the case's gauge list (meta['gauges']).

    When the solver dropped a gauge (fewer points than entered gauges),
    the points are paired with the entered gauges in order
    (`pair_in_order`, GUI-12 A2) and each is labelled with
    that gauge's ENTERED number and position - `G3 (1.530, 1.710) -> cell
    (...)` - as the screens number it (F42, D201). Points >= entered keeps
    the index pairing, so a run without a drop is byte-identical.
    """
    def fmt(pt):
        return '(' + ', '.join(f'{float(v):.3f}' for v in pt) + ')'

    if 'radii' in gauge_out:
        return [f'G{k + 1}  r = {r:.3f} m'
                for k, r in enumerate(gauge_out['radii'])]
    pts = list(gauge_out.get('points', []))
    want = list(requested or [])
    if len(pts) >= len(want):
        pair = list(range(len(pts)))
    else:
        pair = _nearest_entered(pts, want)
        if any(j is None for j in pair):    # the count does not add up:
            pair = [None] * len(pts)        # plain labels for all (P1)
    out = []
    for k, pt in enumerate(pts):
        j = pair[k]
        num = k + 1 if j is None or len(pts) >= len(want) else j + 1
        label = f'G{num} {fmt(pt)} m'
        if j is not None and j < len(want) and len(want[j]) == len(pt):
            snapped = any(abs(float(a) - float(b)) > 1e-9
                          for a, b in zip(want[j], pt))
            if snapped:
                label = f'G{num} {fmt(want[j])} -> cell {fmt(pt)} m'
        out.append(label)
    return out


def entered_numbers(points, requested=None):
    """The G number (1-based) of each 2D/3D point, as `gauge_labels`
    numbers it: the ENTERED gauge's number when the solver dropped one
    (F42), else - no drop, or a pairing short of a point (P1) - the
    point's own index + 1. The exported gauge-trace titles use it
    (GUI-12 A3)."""
    pts = list(points)
    want = list(requested or [])
    plain = list(range(1, len(pts) + 1))
    if len(pts) >= len(want):
        return plain
    pair = _nearest_entered(pts, want)
    if any(j is None for j in pair):
        return plain
    return [j + 1 for j in pair]


def dropped_numbers(points, requested=None):
    """The entered numbers (1-based) that have no point - the gauges the
    solver dropped - by `entered_numbers`' pairing; [] when none is
    dropped, and when the pairing is short of a point (P1: which gauges
    are missing is then not known). The exported gauge grid's footnote
    (GUI-13 (d))."""
    pts = list(points)
    want = list(requested or [])
    if len(pts) >= len(want):
        return []
    pair = _nearest_entered(pts, want)
    if any(j is None for j in pair):
        return []
    kept = set(pair)
    return [j + 1 for j in range(len(want)) if j not in kept]


def _same_dim_dist(w, pt):
    if pt is None or len(w) != len(pt):
        return None
    return math.dist([float(v) for v in w], [float(v) for v in pt])


def pair_in_order(pts, want, dist=None, tol=None):
    """The entered gauge (0-based) each point belongs to, or None - an
    ORDER-PRESERVING alignment (GUI-12 A2, verifyA Q1): the solvers keep
    the entered order and only leave gauges out, so the points pair with
    an increasing subsequence of `want`. Of those, the one pairing the
    most points, then with the least summed distance, wins; ties go to
    the earlier entered gauge. A greedy nearest match could hand a point
    a dropped neighbour's number when two gauges sit within a cell.

    `dist(entered, point)` is a distance, or None when the two cannot
    pair (default: Euclidean, same dimension only); a pair farther than
    `tol` (None: no limit) cannot pair either. Shared by the labels here
    and `ui/run_gauges._match` (D201), so screens and exports agree."""
    dist = dist or _same_dim_dist
    n, m = len(pts), len(want)

    def d(i, j):
        v = dist(want[j], pts[i])
        if v is None or (tol is not None and v > tol + 1e-9):
            return None
        return v

    # g[i][j]: (unpaired points, summed distance) of the best alignment
    # of pts[i:] with want[j:]
    g = [[(0, 0.0)] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        g[i][m] = (n - i, 0.0)
        for j in range(m - 1, -1, -1):
            u = g[i + 1][j]
            best = (u[0] + 1, u[1])                 # point i unpaired
            if g[i][j + 1] < best:
                best = g[i][j + 1]                  # want[j] left out
            v = d(i, j)
            if v is not None:
                w = g[i + 1][j + 1]
                if (w[0], w[1] + v) <= best:        # pair: wins ties
                    best = (w[0], w[1] + v)
            g[i][j] = best
    out, i, j = [], 0, 0
    while i < n:
        v = d(i, j) if j < m else None
        if v is not None and (g[i + 1][j + 1][0],
                              g[i + 1][j + 1][1] + v) == g[i][j]:
            out.append(j)
            i, j = i + 1, j + 1
        elif j < m and g[i][j + 1] == g[i][j]:
            j += 1
        else:
            out.append(None)
            i += 1
    return out


def _nearest_entered(pts, want):
    """The entered gauge (0-based) each point belongs to, or None:
    `pair_in_order` without the one-cell tolerance `ui/run_gauges._match`
    uses (F42; `output/` has no case)."""
    return pair_in_order(pts, want)


def summarize_gauges(gauge_out, p_ambient=P_AIR, requested=None):
    """[row dict per gauge] for a native or foam Result's `gauges`
    (1D: times/radii/pressures; 2D/3D: times/points/pressures)."""
    rows = []
    times = gauge_out.get('times', [])
    for label, p in zip(gauge_labels(gauge_out, requested),
                        gauge_out.get('pressures', [])):
        row = dict(gauge=label)
        row.update(summarize_trace(times, p, p_ambient))
        rows.append(row)
    return rows


def _fmt(v, nd=3):
    if isinstance(v, bool):
        return 'yes' if v else 'no'
    if isinstance(v, str):
        return v
    return '' if v is None or (isinstance(v, float) and np.isnan(v)) \
        else f'{v:.{nd}f}'


def table_rows(rows):
    """Display strings per row, in COLUMNS order (peak/times 3 decimals,
    impulses 2)."""
    out = []
    for r in rows:
        out.append((r['gauge'], _fmt(r['peak_kpa'], 1), _fmt(r['arrival_ms']),
                    _fmt(r['t_peak_ms']), _fmt(r['pos_duration_ms']),
                    _fmt(r['pos_impulse'], 2), _fmt(r['net_impulse'], 2),
                    _fmt(r['complete'])))
    return out


def save_gauge_summary(rows, filename):
    """CSV with COLUMNS as header; one line per gauge."""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in table_rows(rows):
            w.writerow(r)
    return filename
