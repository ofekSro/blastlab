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
    each point is paired with its nearest entered gauge and labelled with
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


def _nearest_entered(pts, want):
    """The entered gauge (0-based) each point belongs to, or None: the
    nearest entered gauge of the same dimension, greedy in point order,
    each entered gauge taken once (F42; the match `ui/run_gauges._match`
    makes, without its one-cell tolerance - `output/` has no case)."""
    used, out = set(), []
    for pt in pts:
        best = None
        for j, w in enumerate(want):
            if j in used or len(w) != len(pt):
                continue
            d = sum((float(a) - float(b)) ** 2 for a, b in zip(w, pt))
            if best is None or d < best[1]:
                best = (j, d)
        if best is None:
            out.append(None)
        else:
            used.add(best[0])
            out.append(best[0])
    return out


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
