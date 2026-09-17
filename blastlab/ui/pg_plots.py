"""On-screen plotting for the Qt front-end, on pyqtgraph.

Mirrors the matplotlib builders of `output/plots.py` (which stay in
charge of every file export): the overpressure image with the obstacle
mask, cell-edge overlays, gauge markers and the Run tab's live pane.

Conventions: pyqtgraph's default `imageAxisOrder='col-major'` matches
our `(Nx, Ny)` x-first fields, so `ImageItem.setImage(field)` needs no
transpose, and `setRect` places pixel (i, j) exactly where
`pcolormesh(x_face, y_face, field.T)` put it (y up).
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from ..core.constants import P_AIR
from . import theme

pg.setConfigOptions(imageAxisOrder='col-major', antialias=False,
                    foreground=theme.DARK['muted'])

#: full-span grid lines per direction on a field plot (as plots.py)
MESH_MAX_LINES = 60
GAUGE_COLOR = '#00e5ff'

_CMAP = None
_LUT = None


def inferno():
    global _CMAP, _LUT
    if _CMAP is None:
        _CMAP = pg.colormap.getFromMatplotlib('inferno')
        _LUT = _CMAP.getLookupTable(0.0, 1.0, 256)
    return _CMAP, _LUT


def apply_theme(glw, plots=()):
    """Colour a GraphicsLayoutWidget and its PlotItems for the current
    mode (card background, muted axes, text-coloured titles)."""
    p = theme.pal()
    try:
        glw.setBackground(p['card'])
    except Exception:
        pass
    for plot in plots:
        try:
            for name in ('bottom', 'left', 'right', 'top'):
                ax = plot.getAxis(name)
                ax.setPen(pg.mkPen(p['muted']))
                ax.setTextPen(pg.mkPen(p['muted']))
            plot.titleLabel.setAttr('color', p['text'].lstrip('#'))
            plot.setTitle(plot.titleLabel.text)
        except Exception:
            pass


def overpressure_kpa(p, solid=None):
    """Overpressure [kPa] with NaN where solid (as plots.set_frame)."""
    ovp = (np.asarray(p).astype(np.float64) - P_AIR) / 1e3
    if solid is not None:
        ovp = np.where(solid, np.nan, ovp)
    return ovp


class ScalarImage:
    """An overpressure image on a PlotItem over uniform faces x_face /
    y_face (kPa, inferno), grey where the mask says solid, with a colour
    bar. `set_field(p, clim)` autoscales per frame unless a fixed
    (vmin, vmax) range is given; returns the (lo, hi) applied."""

    def __init__(self, plot, x_face, y_face, solid=None, colorbar=True,
                 label='Overpressure [kPa]'):
        self.plot = plot
        xf = np.asarray(x_face, dtype=float)
        yf = np.asarray(y_face, dtype=float)
        self.shape = (len(xf) - 1, len(yf) - 1)
        self.rect = QRectF(xf[0], yf[0], xf[-1] - xf[0], yf[-1] - yf[0])
        cmap, lut = inferno()
        # the item needs its pixel size before setRect can map it onto
        # the faces: a blank frame first, the rect second
        self.img = pg.ImageItem(np.zeros(self.shape, np.float32),
                                autoLevels=False, levels=(0.0, 1.0))
        self.img.setLookupTable(lut)
        self.img.setRect(self.rect)
        self.img.setZValue(0)
        plot.addItem(self.img)
        self.solid = None
        self.mask = None
        if solid is not None:
            solid = np.asarray(solid, dtype=bool)
            if solid.shape == self.shape and solid.any():
                self.solid = solid
                rgba = np.zeros(self.shape + (4,), dtype=np.uint8)
                rgba[..., :3] = 128
                rgba[..., 3] = np.where(solid, 255, 0)
                self.mask = pg.ImageItem(rgba)
                self.mask.setRect(self.rect)
                self.mask.setZValue(1)
                plot.addItem(self.mask)
        plot.setAspectLocked(True)
        plot.setRange(xRange=(float(xf[0]), float(xf[-1])),
                      yRange=(float(yf[0]), float(yf[-1])), padding=0.02)
        self.bar = None
        if colorbar:
            self.bar = pg.ColorBarItem(values=(0.0, 1.0), colorMap=cmap,
                                       interactive=False, label=label,
                                       width=14)
            self.bar.setImageItem(self.img, insert_in=plot)
        self.levels = (0.0, 1.0)

    def set_field(self, p, clim=None):
        ovp = overpressure_kpa(p, self.solid)
        if clim is None:
            with np.errstate(all='ignore'):
                hi = float(np.nanmax(ovp)) if np.isfinite(ovp).any() else 0.0
                lo = float(np.nanmin(ovp)) if np.isfinite(ovp).any() else 0.0
            if hi <= lo:
                hi = lo + 1.0
        else:
            lo, hi = float(clim[0]), float(clim[1])
        data = np.nan_to_num(ovp, nan=lo).astype(np.float32)
        self.img.setImage(data, autoLevels=False, levels=(lo, hi))
        if self.bar is not None:
            self.bar.setLevels((lo, hi))
        self.levels = (lo, hi)
        return lo, hi

    def remove(self):
        for item in (self.img, self.mask, self.bar):
            if item is None:
                continue
            try:
                if item is self.bar:
                    self.plot.layout.removeItem(item)
                else:
                    self.plot.removeItem(item)
            except Exception:
                pass


class MeshOverlay:
    """Cell edges ((N, 2, 2) segments) drawn as one polyline item."""

    def __init__(self, plot, color=None, z=2.5):
        self.plot = plot
        self.item = pg.PlotCurveItem(
            pen=pg.mkPen(color or theme.cur('muted'), width=1),
            connect='pairs')
        self.item.setZValue(z)
        self.item.setOpacity(0.6)
        plot.addItem(self.item)

    def set_segments(self, segments):
        segs = np.asarray(segments, dtype=float).reshape(-1, 2, 2)
        if len(segs) == 0:
            self.clear()
            return
        self.item.setData(segs[:, :, 0].ravel(), segs[:, :, 1].ravel(),
                          connect='pairs')

    def clear(self):
        self.item.setData(np.zeros(0), np.zeros(0))

    def set_visible(self, on):
        self.item.setVisible(bool(on))

    def retheme(self):
        self.item.setPen(pg.mkPen(theme.cur('muted'), width=1))

    def remove(self):
        try:
            self.plot.removeItem(self.item)
        except Exception:
            pass


def add_gauge_markers(plot, points, trigger=None, color=GAUGE_COLOR):
    """Gauge positions on a field plot: a ringed dot per gauge with its
    number (the trigger gauge heavier, starred). `points` is
    [(n, x, y), ...] as plots.gauge_points builds. Returns the items."""
    items = []
    for n, x, y in points:
        is_trig = (trigger is not None and n == trigger)
        dot = pg.ScatterPlotItem(
            [float(x)], [float(y)], size=11 if is_trig else 9,
            pen=pg.mkPen(color, width=2.0 if is_trig else 1.2),
            brush=pg.mkBrush(None), pxMode=True)
        dot.setZValue(3.5)
        plot.addItem(dot)
        txt = pg.TextItem(f'G{n}' + ('*' if is_trig else ''), color=color,
                          anchor=(-0.2, 1.25))
        txt.setPos(float(x), float(y))
        txt.setZValue(3.5)
        plot.addItem(txt)
        items += [dot, txt]
    return items


class LiveSlicePane(QWidget):
    """The Run tab's live pane: a placeholder until a run starts, then
    either the 2D overpressure image (with mesh overlay, gauge markers
    and title) or the 1D radial profile line."""

    PLACEHOLDER = 'waiting for the solver…'

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stack = QStackedWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._stack)
        self._holder = QLabel(self.PLACEHOLDER)
        self._holder.setObjectName('muted')
        self._holder.setAlignment(Qt.AlignCenter)
        self._stack.addWidget(self._holder)
        self.glw = pg.GraphicsLayoutWidget()
        self._stack.addWidget(self.glw)
        self.plot = None
        self.image = None
        self.line = None
        self.overlay = None
        self._markers = []
        self._title_base = ''
        self.dim = 0
        theme.signals.changed.connect(self._retheme)

    # ── lifecycle ────────────────────────────────────────────────────────
    def show_placeholder(self, text=None):
        self._holder.setText(text or self.PLACEHOLDER)
        self._stack.setCurrentIndex(0)
        self._clear()

    def _clear(self):
        if self.image is not None:
            self.image.remove()
        if self.overlay is not None:
            self.overlay.remove()
        self.image = self.line = self.overlay = None
        self._markers = []
        self.glw.clear()
        self.plot = None
        self.dim = 0

    def _new_plot(self):
        self._clear()
        self.plot = self.glw.addPlot(row=0, col=0)
        self.plot.setMenuEnabled(False)
        self.plot.hideButtons()
        apply_theme(self.glw, [self.plot])
        self._stack.setCurrentIndex(1)
        return self.plot

    def start_2d(self, info):
        """Axes for a 2D run (or a 3D run's live plane) from the
        run_started info: faces, solid mask, labels, gauges."""
        plot = self._new_plot()
        self.dim = 2
        self.image = ScalarImage(plot, info['x_face'], info['y_face'],
                                 info.get('solid'))
        self.overlay = MeshOverlay(plot)
        plot.setLabel('bottom', info.get('xlabel', 'x [m]'))
        plot.setLabel('left', info.get('ylabel', 'y [m]'))
        self._title_base = str(info.get('title', '') or '')
        self._set_title(self._title_base)
        self._markers = add_gauge_markers(plot, info.get('gauges') or [],
                                          trigger=info.get('trigger_gauge'))

    def start_1d(self, info):
        plot = self._new_plot()
        self.dim = 1
        self.line = plot.plot([], [], pen=pg.mkPen(theme.cur('accent'),
                                                   width=1.4))
        plot.setXRange(0.0, float(info['radius_m']), padding=0.0)
        plot.setYRange(0.0, 10.0)
        plot.enableAutoRange(axis='y', enable=True)
        plot.setLabel('bottom', 'r [m]')
        plot.setLabel('left', 'Overpressure [kPa]')
        plot.showGrid(x=True, y=True, alpha=0.3)
        for n, gr, _ in info.get('gauges') or []:
            ln = pg.InfiniteLine(pos=float(gr), angle=90,
                                 pen=pg.mkPen(theme.cur('muted'), width=1,
                                              style=Qt.DashLine),
                                 label=f'G{n}',
                                 labelOpts=dict(position=0.95,
                                                color=theme.cur('muted')))
            plot.addItem(ln)
        self._title_base = ''
        self._set_title('t = 0.000 ms')

    # ── frames ───────────────────────────────────────────────────────────
    def set_frame_2d(self, field, clim=None):
        if self.image is None:
            return None
        return self.image.set_field(field, clim=clim)

    def set_frame_1d(self, r, p):
        if self.line is None:
            return
        ovp = (np.asarray(p).astype(np.float64) - P_AIR) / 1e3
        self.line.setData(np.asarray(r, dtype=float), ovp)

    def set_time(self, t, hint=''):
        txt = f'{self._title_base}  t = {t*1e3:.3f} ms'.strip()
        if hint:
            txt += f'  ·  {hint}'
        self._set_title(txt)

    def _set_title(self, text):
        if self.plot is not None:
            self.plot.setTitle(text, color=theme.cur('text'), size='10pt')
            self._title = text

    def title(self):
        return getattr(self, '_title', '')

    def set_mesh_segments(self, segments):
        if self.overlay is not None:
            self.overlay.set_segments(segments)

    def clear_mesh(self):
        if self.overlay is not None:
            self.overlay.clear()

    def _retheme(self, _mode=None):
        if self.plot is not None:
            apply_theme(self.glw, [self.plot])
            if self.overlay is not None:
                self.overlay.retheme()
            if self.line is not None:
                self.line.setPen(pg.mkPen(theme.cur('accent'), width=1.4))
        self.glw.setBackground(theme.cur('card'))
