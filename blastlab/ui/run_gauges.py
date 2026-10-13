"""GUI-6b (plan §6, board Run lines 259-335): the Run screen's live-gauge
column - the selected gauge enlarged (its trace, the peak marked, a
dashed *now* line), then a compact list sorted by Z: gauge · Z · a 90 px
sparkline · the peak so far, or `waiting` before the wave arrives.

Data, never re-derived (plan §6: "Reuse live_gauges.py data"):

- the payload is the one `RunPanel.set_gauge_payload` already receives
  (`times`, `pressures` in absolute Pa, `points` or `radii`), or a
  finished Result's `gauges`, which has the same shape;
- rows are keyed G1…Gn in payload order (D61), and LABELLED with the
  entered gauge's number, so a gauge the solver dropped (inside a wall,
  outside the domain) does not renumber the later ones; the caption names
  the dropped gauge (D201, amends D61);
- overpressure is `(p - P_AIR) / 1e3` kPa, as `LiveGaugePane` draws it;
- arrival and the peak so far come from
  `output.gauge_summary.summarize_trace` on the series so far - the
  Results table's own rule (`ARRIVAL_FRAC`), so live and finished agree;
- Z is `scaled_distance.scaled_distance` (UFC 3-340-02, para. 2-13.1,
  the helper's citation) of the *entered* gauge each series belongs to,
  so the Run screen shows exactly Setup's Z, not the snapped cell
  centre's.

`rows(case, payload)` is plain numpy; the widgets below it only draw
what it returns. Sparklines are QPainter (no pyqtgraph per row); the
enlarged trace is one small pyqtgraph plot.
"""

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..core.constants import P_AIR
from ..output.gauge_summary import (pair_in_order, summarize_gauges,
                                    summarize_trace)
from ..services.validation import drop_rule, drop_wall, gauge_drop_reason
from . import scaled_distance as sd
from . import theme
from .components import _css
from .live_gauges import ALL_DROPPED, NO_GAUGES, _decimate
from .results_list import ElidedLabel
from .setup_tree import _letter_space

#: the row text before the wave arrives (board line 327, `faint`)
WAITING = 'waiting'
#: an HD 1.3 (0-D) case has no field and so no gauge to probe
NO_GAUGES_0D = 'An HD 1.3 assessment has no field, so there are no live ' \
               'gauges to show.'
#: board line 334
FOOTNOTE = ('When the run ends, its full traces, impulse and arrival times '
            'open in 03 Results → Gauges.')
#: the sparkline (board line 297) and the list row (line 293)
SPARK_W, SPARK_H = 90, 24
ROW_H = 40
#: the GAUGE column (the header's caps need 34 px at 10.5 px)
NUM_W = 38
#: the list's header row (board line 291)
LIST_HEAD_H = 28
#: points kept for drawing: a sparkline cannot show more than two per
#: pixel column, the enlarged trace not much more than its width
SPARK_POINTS = 2 * SPARK_W
TRACE_POINTS = 800
#: the list is re-summarised at most this often while a run streams
#: (2 Hz: the batch plan's fallback after T9's R-COST, decision D69);
#: the newest payload is always the one drawn (latest wins)
REFRESH_MS = 500


# ── the rows (toolkit-free) ──────────────────────────────────────────────
def fmt_peak(kpa):
    """`296 kPa` (whole kPa, as the board)."""
    return f'{kpa:,.0f} kPa'


def fmt_dist(value):
    """Z or R as the list shows it: two decimals (board `2.99`)."""
    return '—' if value is None else f'{value:.2f}'


def _arr(x):
    return np.asarray(x if x is not None else [], dtype=float)


def _positions(payload):
    """The payload's gauge positions as tuples: `radii` (a finished 1D
    Result) or `points` (every live payload, 1D included)."""
    radii = payload.get('radii')
    if radii is not None:
        return [(float(r),) for r in radii]
    pts = payload.get('points')
    if pts is None:
        return []
    return [tuple(float(v) for v in p) for p in pts]


def _entered(case):
    try:
        return sd.gauge_points(case) if case is not None else []
    except (AttributeError, TypeError, ValueError):
        return []


def _match_dist(g, pos):
    """`pair_in_order`'s distance for `_match`: Euclidean in the same
    dimension; x alone for a one-coordinate position against a
    multi-coordinate gauge; None otherwise."""
    if pos is None:
        return None
    if len(g) == len(pos):
        return math.dist(g, pos)
    if len(pos) == 1 and len(g) > 1:
        return abs(g[0] - pos[0])           # blastFoam live: x only
    return None


def _match(case, positions):
    """The entered gauge (0-based) each payload position belongs to, or
    None. The solver snaps a gauge to its cell centre, at most half a
    cell away per axis, and keeps the entered order, so the positions
    pair with the entered gauges in order, each within one cell
    (`output.gauge_summary.pair_in_order`, GUI-12 A2 - the labels'
    rule too); each entered gauge is taken once.

    blastFoam's live payload of a 3D run carries `radii` - the probes' x
    only (`solvers/foam/backend._gauges_from_probes`) - so a
    one-coordinate position against multi-coordinate gauges is matched
    on x, in entered order (the probes are written in that order), and
    ties go to the first gauge not yet taken."""
    try:
        tol = float(getattr(case, 'cell_size_m', 0.0) or 0.0)
    except (TypeError, ValueError):
        tol = 0.0
    return pair_in_order(list(positions), _entered(case),
                         dist=_match_dist, tol=tol)


def match_gauges(case, gauge_out):
    """The entered gauge (0-based) each position of `gauge_out` (a live
    payload or a finished Result's `gauges`) belongs to, or None - the
    D61 / D73 rules of `_match`. The Results screen's gauge table uses it
    too (GUI-7 T5), so both screens read a gauge's Z from the same
    entered position."""
    return _match(case, _positions(gauge_out or {}))


def _drop_reason(case, point, rule=None):
    """Why an entered gauge has no series: `inside Wall 1`, `within a
    cell of Wall 1`, `outside the domain`, or '' when the case does not
    say. The wall is the solver's own drop rule (`services.validation.
    drop_rule`), the one Setup's warning names, and inside / within a
    cell is the warning's open-box split, in the warning's words
    (`core.geometry.gauge_drop_reason`; GUI-13 (e), GUI-15 (d)). A case the rule cannot lay out (the Results screen's
    meta view, `scaled_distance.case_from_meta`) falls back to the first
    wall within a cell of the gauge, as before."""
    p = [float(v) for v in point]
    if sd.outside_domain(case, p):
        return gauge_drop_reason(0, False, outside=True)
    try:
        boxes = sd.obstacle_boxes(case)
    except (AttributeError, TypeError, ValueError):
        boxes = []
    inside = next((i for i, box in enumerate(boxes, start=1)
                   if len(box) == len(p)
                   and all(lo < v < hi for v, (lo, hi) in zip(p, box))), 0)
    if boxes:
        wall = rule(p) if rule is not None else drop_wall(case, p)
    else:
        wall = 0
    if not (inside or wall):
        try:
            tol = float(getattr(case, 'cell_size_m', 0.0) or 0.0)
        except (TypeError, ValueError):
            tol = 0.0
        wall = next((i for i, box in enumerate(boxes, start=1)
                     if len(box) == len(p)
                     and all(lo - tol <= v <= hi + tol
                             for v, (lo, hi) in zip(p, box))), 0)
    if inside or wall:
        return gauge_drop_reason(inside or wall, bool(inside))
    return ''


def _x_only_tie(case, entered, missing, positions):
    """True when an unmatched entered gauge was as good a candidate as
    the one `_match` took for some x-only position (blastFoam's live 3D
    payload, `radii`): with x alone the solver's drop cannot be told
    from its neighbour at the same x, so naming it would be a guess."""
    try:
        tol = float(getattr(case, 'cell_size_m', 0.0) or 0.0)
    except (TypeError, ValueError):
        tol = 0.0
    for pos in positions or []:
        if pos is None or len(pos) != 1:
            continue
        for j in missing:
            if len(entered[j]) > 1 and \
                    abs(entered[j][0] - pos[0]) <= tol + 1e-9:
                return True
    return False


def _numbering(case, match, n_series, positions=None, rule=None):
    """(labels, dropped) for `n_series` series matched to the entered
    gauges by `match` (D201, amends D61):

        labels      `G<n>` per series, n the ENTERED gauge's number when
                    the solver dropped a gauge, else the series' own
                    number (payload order, D61 - then the two agree)
        dropped     [(entered number, reason)] of the entered gauges
                    with no series

    A drop is named only when the count adds up: the series are short by
    exactly the unmatched entered gauges, so a matching miss is never
    called a drop. A series matching none keeps its payload number. Nor
    is one guessed when x-only `positions` (the blastFoam live 3D payload)
    tie a dropped gauge with a kept one (`_x_only_tie`): the labels then
    come from the rule (`pre_payload`, GUI-16 (d)) when the series are as
    many as the gauges it keeps - the entered numbers, the drops named -
    else they stay plain. `rule` is `drop_rule(case)`, None builds it."""
    entered = _entered(case)
    plain = [f'G{k + 1}' for k in range(n_series)]
    if n_series >= len(entered):
        return plain, []
    taken = {j for j in match[:n_series] if j is not None}
    missing = [j for j in range(len(entered)) if j not in taken]
    if len(missing) != len(entered) - n_series:
        return plain, []
    if _x_only_tie(case, entered, missing, positions):
        kept, dropped = pre_payload(case, rule)
        if n_series == len(kept):
            return [f'G{j + 1}' for j in kept], dropped
        return plain, []
    labels = [f'G{j + 1}' if j is not None else f'G{k + 1}'
              for k, j in enumerate(match[:n_series])]
    return labels, [(j + 1, _drop_reason(case, entered[j]))
                    for j in missing]


def numbering(case, gauge_out, rule=None):
    """`_numbering` of a live payload or a finished Result's `gauges`."""
    gauge_out = gauge_out or {}
    series = gauge_out.get('pressures')
    n = 0 if series is None else len(series)
    pos = _positions(gauge_out)
    pos = (pos + [None] * max(0, n - len(pos)))[:n]
    return _numbering(case, _match(case, pos), n, pos, rule)


def dropped_text(dropped):
    """`G2 dropped by the solver (inside Wall 1)`, one per dropped gauge,
    joined by ` · `; '' when none."""
    return ' · '.join(
        f'G{n} dropped by the solver' + (f' ({why})' if why else '')
        for n, why in dropped)


def z_mode(case):
    """True when the column shows and sorts by Z; False for R (planar
    2D, a profile start: `scaled_distance.z_shown`)."""
    try:
        return case is not None and sd.z_shown(case)
    except (AttributeError, TypeError, ValueError):
        return False


def pre_payload(case, rule=None):
    """(kept, dropped) before any series exists (GUI-15 (a), D1): `kept`
    the 0-based entered gauges the solver keeps, `dropped` [(entered
    number, reason)] for the ones it drops - the same rule
    (`sd.is_dropped`, `services.validation.drop_rule`) Setup's warning
    and the first payload's `_numbering` use, so Run names the drop from
    Start. `rule` is `drop_rule(case)`, built once by the caller."""
    entered = _entered(case)
    if rule is None:
        rule = drop_rule(case)
    kept, dropped = [], []
    for j, g in enumerate(entered):
        if sd.is_dropped(case, g, rule):
            dropped.append((j + 1, _drop_reason(case, g, rule)))
        else:
            kept.append(j)
    return kept, dropped


def drops(case):
    """`[[entered number, reason], ...]` of the gauges the solver drops in
    `case`, as Run words them (GUI-15 (c), D3). `RunController` stamps it
    into the finished Result's `meta['gauges_dropped']` (memory only), so
    Results gives the reason Run gave - its own meta holds the
    face-snapped walls of a blastFoam run, which would read `inside`."""
    try:
        return [[n, why] for n, why in pre_payload(case)[1]]
    except (AttributeError, TypeError, ValueError):
        return []


def _geometry(case, point, rule=None):
    """(R, Z or None, short wall name or '') of `point` in the case. With
    the drop `rule` a dropped gauge is measured against the wall the rule
    drops it for, as Setup's Where column does (`sd.where_text`)."""
    if case is None or point is None:
        return None, None, ''
    try:
        if len(sd.burst_point(case)) != len(point):
            # an unmatched blastFoam live position (x only) in a 2D/3D
            # case: no R or Z rather than one computed from x alone
            return None, None, ''
        r = sd.distance(case, point)
        z = sd.scaled_distance(case, point)
        w = sd.where(case, point)
        wall = rule(point) if (rule is not None and w) else 0
        if wall and wall != w[0]:
            w = sd.where(case, point, wall=wall) or w
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        return None, None, ''
    return r, z, (f'Wall {w[0]}' if w else '')


def rows(case, payload=None, rule=None):
    """One dict per gauge, sorted by Z (ties: R, then the number) - by R
    when Z is hidden. `rule` is `drop_rule(case)` (built here when None);
    before any payload the gauges the solver drops are left out (GUI-15
    (a), `pre_payload`):

        number      G number, payload order (entered order before any
                    payload, the kept gauges counted 1..k) - the row's key
        label       `G<n>` as shown: the entered number when the solver
                    dropped a gauge (`_numbering`, D201), else `number`
        entered     the matched entered gauge, 1-based, or None
        r, z        R [m], Z [m per cube root of kg] (None when hidden or
                    unknown)
        where       `Wall 1` within 0.5 m (scaled_distance.where), or ''
        t_ms, kpa   the series so far: time [ms], overpressure [kPa]
        peak_kpa, t_peak_ms, arrival_ms   summarize_trace's numbers
        waiting     no arrival yet (arrival_ms NaN)
        peak_text   `296 kPa` or `waiting`
    """
    out = []
    if rule is None:
        rule = drop_rule(case) if case is not None else None
    if payload:
        times = _arr(payload.get('times'))
        series = payload.get('pressures')
        series = [] if series is None else list(series)
        pos = _positions(payload)
        pos = pos + [None] * max(0, len(series) - len(pos))
        match = _match(case, pos[:len(series)])
        entered = _entered(case)
        labels, _dropped = _numbering(case, match, len(series),
                                      pos[:len(series)], rule)
        for k, raw in enumerate(series):
            j = match[k]
            if j is not None and labels[k] != f'G{j + 1}':
                # an x-only tie resolved by the rule (GUI-16 (d)): the
                # series is the kept gauge the label names, not the
                # neighbour at the same x that `_match` took
                j = int(labels[k][1:]) - 1
            point = entered[j] if j is not None else pos[k]
            p = _arr(raw)
            n = min(p.size, times.size)
            s = summarize_trace(times[:n], p[:n])
            out.append(_row(case, k + 1, None if j is None else j + 1,
                            point, times[:n] * 1e3,
                            (p[:n] - P_AIR) / 1e3, s, labels[k], rule))
    else:
        entered = _entered(case)
        kept = pre_payload(case, rule)[0] if rule is not None \
            else range(len(entered))
        for k, j in enumerate(kept):
            out.append(_row(case, k + 1, j + 1, entered[j], np.zeros(0),
                            np.zeros(0), None, f'G{j + 1}', rule))
    by_z = z_mode(case)
    inf = float('inf')

    def key(row):
        lead = row['z'] if by_z else row['r']
        return (inf if lead is None else lead,
                inf if row['r'] is None else row['r'], row['number'])

    return sorted(out, key=key)


def _row(case, number, entered, point, t_ms, kpa, s, label=None, rule=None):
    r, z, where = _geometry(case, point, rule)
    nan = float('nan')
    s = s or dict(peak_kpa=nan, t_peak_ms=nan, arrival_ms=nan)
    waiting = not np.isfinite(s['arrival_ms'])
    return dict(number=number, label=label or f'G{number}',
                entered=entered, point=point, r=r, z=z,
                where=where, t_ms=t_ms, kpa=kpa, peak_kpa=s['peak_kpa'],
                t_peak_ms=s['t_peak_ms'], arrival_ms=s['arrival_ms'],
                waiting=waiting,
                peak_text=WAITING if waiting else fmt_peak(s['peak_kpa']))


def highest_peak(gauges):
    """(G number, peak_kpa, t_peak_ms) of the highest peak among the
    gauges with an arrival - `summarize_gauges` of a Result's `gauges`,
    numbered in their order - or None (no gauges, or no arrival)."""
    if not gauges:
        return None
    best = None
    for k, row in enumerate(summarize_gauges(gauges), start=1):
        if not np.isfinite(row['arrival_ms']):
            continue
        if best is None or row['peak_kpa'] > best[1]:
            best = (k, row['peak_kpa'], row['t_peak_ms'])
    return best


def default_row(case, table):
    """The gauge enlarged by default: the trigger gauge when the case has
    one, otherwise the first row (the lowest Z)."""
    if not table:
        return None
    trig = getattr(case, 'trigger_gauge', None)
    if trig is not None:
        for row in table:
            if row['entered'] == trig:
                return row
    return table[0]


def _mix(a, b, t):
    """`a` blended toward `b` by t (0..1), '#rrggbb'."""
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t),
                  round(ca.green() + (cb.green() - ca.green()) * t),
                  round(ca.blue() + (cb.blue() - ca.blue()) * t)).name()


# ── the widgets ──────────────────────────────────────────────────────────
class Sparkline(QWidget):
    """A 90 x 24 trace in `gauge` cyan, drawn with QPainter - a pyqtgraph
    plot per row would cost a scene per gauge (board line 297)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(SPARK_W, SPARK_H)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._x = np.zeros(0)
        self._y = np.zeros(0)
        self._span = (0.0, 1.0, 0.0, 1.0)

    def set_data(self, x, y, span):
        """`x`, `y` already decimated; `span` = (x0, x1, y0, y1), shared by
        every row so the list compares peaks at a glance."""
        self._x, self._y = np.asarray(x, float), np.asarray(y, float)
        self._span = span
        self.update()

    def n_points(self):
        return int(self._x.size)

    def paintEvent(self, _event):
        if self._x.size < 2:
            return
        x0, x1, y0, y1 = self._span
        w, h = self.width() - 1.0, self.height() - 3.0
        sx = w / (x1 - x0) if x1 > x0 else 0.0
        sy = h / (y1 - y0) if y1 > y0 else 0.0
        ok = np.isfinite(self._x) & np.isfinite(self._y)
        poly = QPolygonF([QPointF((xv - x0) * sx, 1.5 + h - (yv - y0) * sy)
                          for xv, yv in zip(self._x[ok], self._y[ok])])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor(theme.cur('gauge')))
        pen.setWidthF(1.3)
        p.setPen(pen)
        p.drawPolyline(poly)
        p.end()


class _GaugeRow(QFrame):
    """One list row (board lines 293-330): GAUGE · Z · TRACE · PEAK, 40 px;
    the selected row has the `gauge_bg` fill. A click selects it."""

    clicked = Signal(int)

    def __init__(self, number, parent=None):
        super().__init__(parent)
        self.number = number
        self.setObjectName('gaugerow')
        self.setFixedHeight(ROW_H)
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(8)
        self.num = QLabel(f'G{number}')
        self.num.setFixedWidth(NUM_W)
        self.dist = QLabel('—')
        self.dist.setFixedWidth(40)
        self.spark = Sparkline()
        self.peak = QLabel(WAITING)
        self.peak.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.peak.setMinimumWidth(0)
        for w in (self.num, self.dist, self.spark, self.peak):
            lay.addWidget(w, 0, Qt.AlignVCenter)
        lay.setStretchFactor(self.peak, 1)
        self._selected = False
        self._waiting = True
        self._peak_kpa = None
        self._peak_text = WAITING
        self.recolour()

    def set_row(self, row, span):
        """Texts and the sparkline only; the style sheets are re-applied
        only when the waiting state changes (re-polishing every row on
        every refresh was most of the collection cost, T9 R-COST)."""
        if self.num.text() != row['label']:
            self.num.setText(row['label'])          # the entered number
        self.dist.setText(fmt_dist(row['z'] if row['z'] is not None
                                   else row['r']))
        changed = row['waiting'] != self._waiting
        self._waiting = row['waiting']
        self._peak_kpa = None if row['waiting'] else row['peak_kpa']
        self._peak_text = row['peak_text']
        self._set_peak_html()
        x, y = _decimate(row['t_ms'], row['kpa'], cap=SPARK_POINTS) \
            if row['t_ms'].size else (row['t_ms'], row['kpa'])
        self.spark.set_data(x, y, span)
        if changed:
            self.recolour()

    def _set_peak_html(self):
        if self._peak_kpa is None:
            text = WAITING
        else:
            text = (f'{self._peak_kpa:,.0f} <span style="color: '
                    f'{theme.cur("faint")};">kPa</span>')
        if self.peak.text() != text:
            self.peak.setText(text)

    def peak_text(self):
        """The PEAK cell as read: `296 kPa` or `waiting`."""
        return self._peak_text

    def set_selected(self, on):
        if bool(on) != self._selected:
            self._selected = bool(on)
            self.recolour()

    def recolour(self):
        p = theme.pal()
        bg = p['gauge_bg'] if self._selected else 'transparent'
        self.setStyleSheet(f'QFrame#gaugerow {{ background: {bg}; '
                           f'border: none; '
                           f'border-top: 1px solid {p["border"]}; }}')
        self.num.setStyleSheet(_css(12.5, 600, 'gauge', theme.MONO))
        self.dist.setStyleSheet(_css(12, None, 'accent_soft', theme.MONO))
        self.peak.setStyleSheet(_css(12.5, None,
                                     'faint' if self._waiting else 'text',
                                     theme.MONO))
        self._set_peak_html()           # the unit's colour is in the HTML
        self.spark.update()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton \
                and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.number)


class _SelectedCard(QFrame):
    """The enlarged gauge (board lines 265-288): `G2`, `Z 2.99 · Wall 1 ·
    selected`, `peak 231 kPa`; its trace in `gauge` cyan, the peak marked
    with a dot and its time, a dashed orange *now* line at the newest
    sample while the run goes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('gaugecard')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        self.num = QLabel('')
        # GUI-13 (g), QA #2: the whole text is the tooltip and it never
        # runs under the peak. GUI-14 (e) / G14U-P3 (D32): the number and its
        # unit (`Z 1.23 m/kg¹ᐟ³`) are a label of their own that never
        # shrinks; only the `· Wall n` after it elides
        self.lead = QLabel('')
        self.lead.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.meta = ElidedLabel('', Qt.ElideRight)
        self.peak = QLabel('')
        head.addWidget(self.num, 0, Qt.AlignBaseline)
        head.addWidget(self.lead, 0, Qt.AlignBaseline)
        head.addWidget(self.meta, 1, Qt.AlignBaseline)
        head.addWidget(self.peak, 0, Qt.AlignBaseline)
        lay.addLayout(head)
        self.plot_w = pg.PlotWidget()
        self.plot_w.setFixedHeight(116)
        self.plot_w.setMenuEnabled(False)
        self.plot_w.setMouseEnabled(False, False)
        self.plot_w.hideButtons()
        self.plot_w.setFocusPolicy(Qt.NoFocus)
        self.plot = self.plot_w.getPlotItem()
        self.plot.setLabel('bottom', '')
        for ax in ('left', 'bottom'):
            self.plot.getAxis(ax).setStyle(tickLength=-3)
        self.curve = self.plot.plot([], [])
        self.peak_dot = pg.ScatterPlotItem(size=6)
        self.plot.addItem(self.peak_dot)
        self.peak_lbl = pg.TextItem('', anchor=(1.05, 0.5))
        self.plot.addItem(self.peak_lbl)
        self.now_line = pg.InfiniteLine(angle=90, movable=False,
                                        label='now',
                                        labelOpts=dict(position=0.92))
        self.plot.addItem(self.now_line)
        self.now_line.setVisible(False)
        lay.addWidget(self.plot_w)
        self._row = None
        self._live = False

    def meta_text(self):
        """The whole header text, `Z 2.99 m/kg¹ᐟ³ · Wall 1` (tests)."""
        return ' '.join(t for t in (self.lead.text(),
                                    self.meta.full_text()) if t)

    def set_row(self, row, z_on, live):
        """Texts, the trace and its marks; the peak label is re-styled
        only when the waiting state changes (see _GaugeRow.set_row)."""
        was = self._row is None or self._row['waiting']
        self._row, self._live = row, bool(live)
        self.num.setText(row['label'])
        # GUI-14 (e), UX F4: Z carries its unit (from the column label),
        # and the header says nothing about being selected - the enlarged
        # card is the selection
        lead = (f'Z {fmt_dist(row["z"])} {sd.unit()}' if z_on
                else f'R {fmt_dist(row["r"])} m')
        self.lead.setText(lead)
        self.meta.setText(f'· {row["where"]}' if row['where'] else '')
        self.meta.setVisible(bool(row['where']))
        self.peak.setText(WAITING if row['waiting']
                          else f'peak {fmt_peak(row["peak_kpa"])}')
        t, y = row['t_ms'], row['kpa']
        if t.size:
            x, yy = _decimate(t, y, cap=TRACE_POINTS)
            self.curve.setData(x, yy)
            self.now_line.setValue(float(t[-1]))
        else:
            self.curve.setData([], [])
        self._set_range(t, y)
        if row['waiting'] or not t.size:
            self.peak_dot.setData([], [])
            self.peak_lbl.setText('')
        else:
            self.peak_dot.setData([row['t_peak_ms']], [row['peak_kpa']])
            self.peak_lbl.setText(f'{row["t_peak_ms"]:.2f} ms')
            self.peak_lbl.setPos(row['t_peak_ms'], row['peak_kpa'])
        self.now_line.setVisible(self._live and bool(t.size))
        if row['waiting'] != was:
            self._style_peak()

    def _style_peak(self):
        waiting = self._row is None or self._row['waiting']
        self.peak.setStyleSheet(_css(12, None, 'faint' if waiting else 'text',
                                     theme.MONO))

    def _set_range(self, t, y):
        """Time from 0 to the newest sample, overpressure from min(0, the
        lowest) to the highest. Set, not autoranged: a waiting gauge's
        flat trace autoranged to +-1e-305 kPa (T9 screenshot)."""
        ok = np.isfinite(y) if y.size else np.zeros(0, bool)
        t_end = float(t[-1]) if t.size else 0.0
        lo = min(0.0, float(y[ok].min())) if ok.any() else 0.0
        hi = float(y[ok].max()) if ok.any() else 0.0
        if not hi > lo + 1e-6:
            hi = lo + 1.0                       # flat: a 1 kPa window
        self.plot.disableAutoRange()
        self.plot.setXRange(0.0, t_end if t_end > 0.0 else 1.0,
                            padding=0.02)
        self.plot.setYRange(lo, hi, padding=0.1)

    def y_range(self):
        """(lo, hi) of the trace's vertical axis (tests)."""
        return tuple(self.plot.viewRange()[1])

    def set_live(self, live):
        self._live = bool(live)
        has = self._row is not None and self._row['t_ms'].size > 0
        self.now_line.setVisible(self._live and has)

    def recolour(self):
        p = theme.pal()
        border = _mix(p['gauge_bg'], p['gauge'], 0.28)
        self.setStyleSheet(f'QFrame#gaugecard {{ background: {p["gauge_bg"]};'
                           f' border: 1px solid {border}; '
                           f'border-radius: 10px; }}')
        self.num.setStyleSheet(_css(13, 600, 'gauge', theme.MONO))
        self.lead.setStyleSheet(_css(12, None, 'faint'))
        self.meta.setStyleSheet(_css(12, None, 'faint'))
        self._style_peak()
        self.plot_w.setBackground(p['gauge_bg'])
        for ax in ('left', 'bottom'):
            a = self.plot.getAxis(ax)
            a.setPen(pg.mkPen(p['border2']))
            a.setTextPen(pg.mkPen(p['faint']))
        gauge = p['gauge']
        self.curve.setPen(pg.mkPen(gauge, width=1.8))
        self.peak_dot.setBrush(pg.mkBrush(gauge))
        self.peak_dot.setPen(pg.mkPen(None))
        self.peak_lbl.setColor(gauge)
        self.now_line.setPen(pg.mkPen(p['accent'], width=1,
                                      style=Qt.DashLine))
        # the board's accent_text in dark (7.59:1 on gauge_bg); light
        # accent_text is 4.37:1 there, so accent_soft (4.75), as D38
        self.now_line.label.setColor(p['accent_text'] if theme.mode() ==
                                     'dark' else p['accent_soft'])


class GaugeColumn(QWidget):
    """The right column of 02 Run (board lines 259-335)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        top = QVBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)
        self.caps = QLabel('LIVE GAUGES')
        self.caps.setObjectName('eyebrow')
        _letter_space(self.caps)
        top.addWidget(self.caps)
        # GUI-13 B3 (UX #11): the drop note comes first, in the warn colour
        self.drop = QLabel('')
        self.drop.setWordWrap(True)
        self.drop.setVisible(False)
        top.addWidget(self.drop)
        self.sub = QLabel('')
        self.sub.setWordWrap(True)
        top.addWidget(self.sub)
        lay.addLayout(top)
        self.card = _SelectedCard()
        # its content height, never more: the spare height of a tall
        # column goes to the spacer under the list (T9 screenshot: the
        # card grew to 225 px with its header floating)
        self.card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        lay.addWidget(self.card)
        # the list: a header, then one 40 px row per gauge, scrolling
        # when there are more than fit (board lines 290-331)
        self.list_frame = QFrame()
        self.list_frame.setObjectName('gaugelist')
        ll = QVBoxLayout(self.list_frame)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(10, 0, 10, 0)
        head.setSpacing(8)
        self.head_lbls = []
        for text, w in (('GAUGE', NUM_W), ('Z', 40), ('TRACE', SPARK_W),
                        ('PEAK', None)):
            lbl = QLabel(text)
            if w:
                lbl.setFixedWidth(w)
            else:
                lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            head.addWidget(lbl, 0 if w else 1)
            self.head_lbls.append(lbl)
        hw = QWidget()
        hw.setFixedHeight(LIST_HEAD_H)
        hw.setLayout(head)
        ll.addWidget(hw)
        self.list_head = hw
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # it grows to hold every row (its maximum is set per row count in
        # _rebuild) and gives way down to one row, then scrolls
        self.scroll.setSizePolicy(QSizePolicy.Preferred,
                                  QSizePolicy.Expanding)
        self.scroll.setMinimumHeight(ROW_H)
        # no Tab stop (the rows are mouse targets; D58's rule for the
        # controls column's scroll area)
        self.scroll.setFocusPolicy(Qt.NoFocus)
        self._rows_host = QWidget()
        self._rows_lay = QVBoxLayout(self._rows_host)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(0)
        self.scroll.setWidget(self._rows_host)
        ll.addWidget(self.scroll)
        lay.addWidget(self.list_frame, 1)
        self.empty = QLabel(NO_GAUGES)
        self.empty.setWordWrap(True)
        lay.addWidget(self.empty)
        lay.addStretch(0)
        self.foot = QLabel(FOOTNOTE)
        self.foot.setWordWrap(True)
        self.foot.setObjectName('gaugefoot')
        lay.addWidget(self.foot)

        self._case = None
        self._rule = None
        self._payload = None
        self._table = []
        self._widgets = {}          # G number -> _GaugeRow
        self._order = []
        self._selected = None       # ('e', entered) | ('n', number)
        self._live = False
        self._dirty = False
        self._cool = QTimer(self)
        self._cool.setSingleShot(True)
        self._cool.setInterval(REFRESH_MS)
        self._cool.timeout.connect(self._cooled)
        theme.signals.changed.connect(self._retheme)
        self._retheme()
        self._render()

    # ── feeding it ───────────────────────────────────────────────────────
    def set_case(self, case):
        """The case of the stage being shown (Z, the wall names, the
        trigger gauge). Its series so far are dropped: a new stage, or
        no run yet - the rows are the case's gauges, all `waiting`."""
        self._case = case
        self._rule = self._build_rule(case)
        self._payload = None
        self._render()

    @staticmethod
    def _build_rule(case):
        """The solver's drop rule, built once per case (GUI-15 (a), D1)."""
        return None if case is None else drop_rule(case)

    def case(self):
        return self._case

    def start_run(self):
        """A run starts: no series yet, the selection back to its
        default, the now line on."""
        self._payload = None
        self._selected = None
        self._live = True
        self._render()

    def set_live(self, live):
        """While a run goes the enlarged trace has a *now* line; a
        finished column shows the full traces without it."""
        self._live = bool(live)
        self.card.set_live(self._live)

    def set_payload(self, payload, final=False):
        """The series so far (latest wins). Drawn at once when the list
        has been quiet for REFRESH_MS, else when that interval ends -
        the summary of a long native series is not free, and a live
        frame arrives every drain. `final` (a finished Result's gauges)
        is always drawn at once."""
        if not payload:
            return
        self._payload = payload
        if final or not self._cool.isActive():
            self._render()
            self._cool.start()
        else:
            self._dirty = True

    def flush(self):
        """Draw a payload still waiting on the REFRESH_MS interval."""
        if self._dirty:
            self._render()

    def _cooled(self):
        if self._dirty:
            self._render()
            self._cool.start()

    def has_data(self):
        return self._payload is not None

    # ── reading it (tests, the e2e) ──────────────────────────────────────
    def table(self):
        """The rows as displayed, sorted (dicts of `rows()`)."""
        return list(self._table)

    def row_widget(self, number):
        return self._widgets.get(number)

    def row_widgets(self):
        """The row widgets in display order."""
        return [self._widgets[n] for n in self._order]

    def selected_number(self):
        row = self._selected_row()
        return None if row is None else row['number']

    def card_texts(self):
        return (self.card.num.text(), self.card.meta_text(),
                self.card.peak.text())

    def now_visible(self):
        return self.card.now_line.isVisible()

    def header_text(self):
        return ' · '.join(lbl.text() for lbl in self.head_lbls)

    def caption_text(self):
        """The line above the card: the count, the sort, and a dropped
        gauge's name first (D201, GUI-13 B3)."""
        if self.drop.isHidden():
            return self.sub.text()
        return f'{self.drop.text()} · {self.sub.text()}'

    def row_labels(self):
        """The GAUGE cells in display order (`G1`, `G3`, ...)."""
        return [w.num.text() for w in self.row_widgets()]

    def select(self, number):
        """Enlarge G`number` (a row click); it persists for the run."""
        for row in self._table:
            if row['number'] == number:
                self._selected = (('e', row['entered'])
                                  if row['entered'] is not None
                                  else ('n', number))
                break
        self._show_selected()

    # ── drawing ──────────────────────────────────────────────────────────
    def _selected_row(self):
        if not self._table:
            return None
        if self._selected is not None:
            kind, val = self._selected
            for row in self._table:
                if (row['entered'] if kind == 'e' else row['number']) == val:
                    return row
        return default_row(self._case, self._table)

    def _render(self):
        self._dirty = False
        self._table = rows(self._case, self._payload, self._rule)
        z_on = z_mode(self._case)
        n = len(self._table)
        has = n > 0
        dim0 = getattr(self._case, 'dim', None) == 0
        # GUI-16 (e), D22: a case whose gauges are all dropped is not a case
        # with none - the drop line below names them
        all_gone = not has and bool(_entered(self._case))
        self.empty.setText(NO_GAUGES_0D if dim0 else
                           ALL_DROPPED if all_gone else NO_GAUGES)
        for w in (self.card, self.list_frame):
            w.setVisible(has)
        self.empty.setVisible(not has)
        axis = 'Z' if z_on else 'R'
        self.head_lbls[1].setText(axis)
        # UXR-15 (D221): the unit the narrow header leaves out
        self.head_lbls[1].setToolTip(
            sd.unit_tip() if z_on else 'R: the distance from the burst, in m')
        # D201: a gauge the solver dropped is named, so the entered
        # numbers on the rows do not read as a gap
        # (before the first payload too: the same rule, GUI-15 (a))
        note = dropped_text(
            numbering(self._case, self._payload)[1] if self._payload
            else pre_payload(self._case, self._rule)[1]
            if self._rule is not None else [])
        self.sub.setText(f'{n} gauge{"" if n == 1 else "s"}, sorted by '
                         f'{axis}. Click a row to enlarge it.'
                         if has else '')
        self.sub.setVisible(has)
        # G14U-P2 (D29): no full stop, as Results' line ends
        self.drop.setText(note)
        self.drop.setVisible(bool(note))
        order = [row['number'] for row in self._table]
        if order != self._order:
            self._rebuild(order)
        span = self._span()
        for row in self._table:
            self._widgets[row['number']].set_row(row, span)
        self._show_selected()

    def _span(self):
        """(x0, x1, y0, y1) shared by every sparkline."""
        t1, lo, hi = 0.0, 0.0, 0.0
        for row in self._table:
            if row['t_ms'].size:
                t1 = max(t1, float(row['t_ms'][-1]))
                lo = min(lo, float(np.nanmin(row['kpa'])))
                hi = max(hi, float(np.nanmax(row['kpa'])))
        return (0.0, t1 if t1 > 0 else 1.0, lo, hi if hi > lo else lo + 1.0)

    def _rebuild(self, order):
        for w in self._widgets.values():
            w.setParent(None)
            w.deleteLater()
        self._widgets = {}
        while self._rows_lay.count():
            self._rows_lay.takeAt(0)
        for number in order:
            w = _GaugeRow(number)
            w.clicked.connect(self.select)
            self._rows_lay.addWidget(w)
            self._widgets[number] = w
        self._rows_lay.addStretch(1)
        self._order = order
        rows_h = len(order) * ROW_H + 2 * self.scroll.frameWidth()
        self.scroll.setMaximumHeight(rows_h)
        # the frame too, or it takes the column's stretch and its header
        # floats in the middle of empty space (T9 screenshot); the extra
        # height goes to the spacer under it instead
        m = self.list_frame.contentsMargins()
        self.list_frame.setMaximumHeight(
            LIST_HEAD_H + rows_h + m.top() + m.bottom()
            + 2 * self.list_frame.frameWidth())

    def _show_selected(self):
        row = self._selected_row()
        for number, w in self._widgets.items():
            w.set_selected(row is not None and number == row['number'])
        if row is not None:
            self.card.set_row(row, z_mode(self._case), self._live)

    def _retheme(self, _mode=None):
        p = theme.pal()
        self.sub.setStyleSheet(_css(12.5, None, 'muted'))
        self.drop.setStyleSheet(_css(12.5, 600, 'warn'))
        self.list_frame.setStyleSheet(
            f'QFrame#gaugelist {{ background: {p["card"]}; '
            f'border: 1px solid {p["border2"]}; border-radius: 10px; }}')
        self.scroll.setStyleSheet('QScrollArea { background: transparent; '
                                  'border: none; }')
        self._rows_host.setStyleSheet('background: transparent;')
        for lbl in self.head_lbls:
            lbl.setStyleSheet(_css(10.5, 600, 'faint'))
        self.empty.setStyleSheet(_css(12, None, 'muted'))
        self.foot.setStyleSheet(
            f'QLabel#gaugefoot {{ background: {p["card2"]}; '
            f'border-radius: 10px; padding: 12px 14px; font-size: 12px; '
            f'color: {p["muted"]}; }}')
        for w in self._widgets.values():
            w.recolour()
        self.card.recolour()

    def sizeHint(self):
        return QSize(300, super().sizeHint().height())
