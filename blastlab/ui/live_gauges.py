"""The Run tab's live gauge traces.

The Tk app could only show gauges once a run had finished, which is the
wrong way round for the thing they are for: a gauge is how you find out
whether the shock has reached the point you care about, and that is a
question you ask WHILE the run is going, not after it.

The solver hands over the whole series so far rather than a delta (see
`RunHooks.gauges`), so this only ever redraws - there is no accumulated
state here to fall out of step with the run.
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QLabel, QStackedWidget,
                               QVBoxLayout, QWidget)

from ..core.constants import P_AIR
from . import pg_plots, theme
from .widgets import hbox, label, vbox

WAITING = 'gauge traces appear here once the solver reaches them…'
NO_GAUGES = ('This case has no gauges.\n'
             'Add one on the Setup tab to watch a point during the run.')
#: GUI-16 (e), D22: the case has gauges, and the solver drops every one
ALL_DROPPED = 'Every gauge of this case is dropped by the solver.'

#: more than this many points per trace and the line is decimated for
#: drawing. A native 2D run samples every step, so a few seconds of
#: solving is already tens of thousands of points, and pyqtgraph redraws
#: all of them on every frame.
MAX_POINTS = 4000


def _decimate(x, y, cap=MAX_POINTS):
    """Thin a trace for drawing, keeping the peak.

    A plain stride would drop the shock: the peak is one or two samples
    wide, and the whole reason to watch a gauge is to see it arrive. So
    the series is bucketed and each bucket contributes its MAXIMUM.
    """
    n = len(x)
    if n <= cap:
        return x, y
    step = int(np.ceil(n / cap))
    keep = (n // step) * step
    xb = np.asarray(x[:keep]).reshape(-1, step)
    yb = np.asarray(y[:keep]).reshape(-1, step)
    idx = yb.argmax(axis=1)
    rows = np.arange(xb.shape[0])
    out_x, out_y = xb[rows, idx], yb[rows, idx]
    # The newest sample is the one the eye is on in a live view, and the
    # last bucket's maximum is usually NOT it - with a quiet tail the
    # bucket's argmax lands on its first entry, so the trace's right edge
    # would sit up to `step` samples behind the run.
    if out_x.size == 0 or float(out_x[-1]) != float(x[-1]):
        out_x = np.append(out_x, x[-1])
        out_y = np.append(out_y, y[-1])
    return out_x, out_y


class LiveGaugePane(QWidget):
    """Overpressure against time, one line per gauge, refreshed live."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = vbox(self)
        bar = hbox()
        self.follow = QCheckBox('Follow')
        self.follow.setChecked(True)
        self.follow.setToolTip(
            'Keep the view on the newest samples. Untick to zoom or pan '
            'into what has already been recorded without the run pulling '
            'the view back.')
        self.follow.toggled.connect(self._follow_changed)
        bar.addWidget(self.follow)
        self.peak_lbl = label('', 'small')
        bar.addWidget(self.peak_lbl, 1)
        root.addLayout(bar)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)
        self._holder = QLabel(WAITING)
        self._holder.setObjectName('muted')
        self._holder.setAlignment(Qt.AlignCenter)
        self._holder.setWordWrap(True)
        self._stack.addWidget(self._holder)
        self.glw = pg.GraphicsLayoutWidget()
        self._stack.addWidget(self.glw)
        self.plot = self.glw.addPlot(row=0, col=0)
        self.plot.setMenuEnabled(False)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.setLabel('bottom', 'time [ms]')
        self.plot.setLabel('left', 'Overpressure [kPa]')
        self.legend = self.plot.addLegend(offset=(-10, 10))
        self.curves = []
        self._n_points = 0
        pg_plots.apply_theme(self.glw, [self.plot])
        theme.signals.changed.connect(self._retheme)
        self.reset()

    # ── state ────────────────────────────────────────────────────────────
    def reset(self, text=WAITING):
        self._drop_curves()
        self._holder.setText(text)
        self._stack.setCurrentIndex(0)
        self.peak_lbl.setText('')
        self._n_points = 0

    def _drop_curves(self):
        for c in self.curves:
            self.plot.removeItem(c)
        self.curves = []
        try:
            self.legend.clear()
        except Exception:
            pass

    def has_data(self):
        return bool(self.curves) and self._n_points > 0

    def n_points(self):
        return self._n_points

    def _follow_changed(self, on):
        if on:
            self.plot.enableAutoRange()

    def _retheme(self, _mode=None):
        pg_plots.apply_theme(self.glw, [self.plot])
        for i, c in enumerate(self.curves):
            c.setPen(pg.mkPen(self._colour(i), width=2))

    @staticmethod
    def _colour(i):
        cols = pg_plots.series_colours()
        return cols[i % len(cols)]

    # ── the live update ──────────────────────────────────────────────────
    def set_payload(self, payload):
        """Draw the series the solver has so far.

        Overpressure in kPa, like every other plot and colour bar in the
        app - the raw series is absolute pressure in Pa.
        """
        if not payload:
            return
        # explicit None checks: a blastFoam payload carries ndarrays
        # (reader.read_probes), and `ndarray or []` raises (D6)
        times = payload.get('times')
        times = np.asarray([] if times is None else times, dtype=float)
        series = payload.get('pressures')
        if series is None:
            series = []
        if times.size == 0 or len(series) == 0:
            return
        names = _labels(payload, len(series))
        if len(self.curves) != len(series):
            self._drop_curves()
            for i, name in enumerate(names):
                self.curves.append(self.plot.plot(
                    [], [], pen=pg.mkPen(self._colour(i), width=2),
                    name=name))
        peak = 0.0
        for i, raw in enumerate(series):
            y = (np.asarray(raw, dtype=float) - P_AIR) / 1e3
            n = min(len(y), times.size)
            if n == 0:
                continue
            peak = max(peak, float(np.nanmax(y[:n])))
            xs, ys = _decimate(times[:n] * 1e3, y[:n])
            self.curves[i].setData(xs, ys)
        self._n_points = int(times.size)
        self._stack.setCurrentIndex(1)
        self.peak_lbl.setText(
            f'{len(series)} gauge{"s" if len(series) != 1 else ""}, '
            f'{times.size:,} samples, peak {peak:,.1f} kPa')
        if self.follow.isChecked():
            self.plot.enableAutoRange()


def _labels(payload, n):
    """G1..Gn, with the position the run actually snapped to."""
    pts = payload.get('points')
    radii = payload.get('radii')
    out = []
    for i in range(n):
        if radii is not None and i < len(radii):
            out.append(f'G{i + 1}  r = {float(radii[i]):.3f} m')
        elif pts is not None and i < len(pts):
            where = ', '.join(f'{float(v):.2f}' for v in pts[i])
            out.append(f'G{i + 1}  ({where})')
        else:
            out.append(f'G{i + 1}')
    return out
