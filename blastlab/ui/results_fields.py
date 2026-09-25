"""The Results tab's Fields view: ONE large field panel plus selectors.

The Tk version built a whole matplotlib Figure per interaction - it
computed a single `(label, data)` pair and handed it to the multi-panel
grid builder with n=1. Here the panel is persistent, so the flow
inverts: changing snapshot or field is one array upload into a live
pyqtgraph image, not a figure rebuild. The exported PNGs and the HTML
report still get the full grid from `output/plots.py`; see `exports.py`.

Two of the "fields" are not maps at all - a 1D run's radial profiles and
a 3D run's isosurface view - so the panel is a stack whose second page
is a matplotlib canvas fed by the very same builders the exports use.
That is the only parity route that does not re-author two figure
builders.
"""

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QStackedWidget, QWidget
import pyqtgraph as pg

from ..core.constants import P_AIR
from ..models.meta import charge_label, slice_geometry
from ..output import plots
from . import pg_plots, theme
from .mpl_canvas import MplCanvas
from .widgets import hbox, label, vbox

#: the field selector's entries per dimension. 'profiles' and
#: 'isosurface' are the two that go to the matplotlib page.
MPL_FIELDS = ('profiles', 'isosurface')

#: shown before any run has finished, in place of empty axes
NO_RESULT = ('Run a case, or load a finished blastFoam run, and its '
             'fields appear here.')


def field_options(res, dim):
    """What the field selector offers for this result. The whole-run
    peak and impulse maps appear only when the run actually recorded
    them (older results, and some post-mortem loads, did not)."""
    if dim == 1:
        return ['profiles']
    peak = plots.has_peak_maps(res.meta)
    if dim == 2:
        out = ['overpressure', 'density', 'speed']
        if peak:
            out += ['peak overpressure', 'net ovp impulse']
        return out
    out = ['overpressure (x-z)', 'overpressure (x-y)',
           'density (x-z)', 'density (x-y)']
    if peak:
        out += ['peak overpressure (x-z)', 'peak overpressure (x-y)',
                'net ovp impulse (x-z)', 'net ovp impulse (x-y)']
    out.append('isosurface')
    return out


def select_field(res, dim, snap_label, field, title_extra=None):
    """Everything needed to paint one field panel, or None when this
    field is not a map (1D profiles, the 3D isosurface view).

    Pure: no widgets, so the whole selection matrix is testable. Keys:
    `z` the array, `unit` the colour-bar label, `xf`/`yf` the faces,
    `solid` the mask for THIS plane, `xlabel`/`ylabel`, `title`, `sl`
    the 3D plane selector (None in 2D) and `robust`.
    """
    if dim == 1 or field == 'isosurface':
        return None
    meta = res.meta
    snap = res.snapshots.get(snap_label)
    if snap is None:
        return None
    is_peak = field.startswith('peak overpressure')
    is_imp = field.startswith('net ovp impulse')
    # a whole-run map is not per snapshot, and says so instead of
    # carrying a time label it does not honour
    panel = 'whole run' if (is_peak or is_imp) else snap_label

    if dim == 2:
        g = slice_geometry(meta, 'grid')
        sl, solid, xf, yf = g.sl, g.solid, g.xf, g.yf
        axi = meta.get('geometry') == 'axisymmetric'
        xlabel = 'r [m]' if axi else 'x [m]'
        ylabel = 'z [m]' if axi else 'y [m]'
        if is_peak or is_imp:
            (_pl, pk), (_il, im) = plots.peak_items(meta)
            z = pk if is_peak else im
            unit = plots.PEAK_LABEL if is_peak else plots.IMPULSE_LABEL
        else:
            z = {'overpressure': (snap['p'] - P_AIR) / 1e3,
                 'density': snap['rho'],
                 'speed': snap['speed']}[field]
            unit = {'overpressure': 'Overpressure [kPa]',
                    'density': 'Density [kg/m³]',
                    'speed': 'Speed [m/s]'}[field]
    else:
        is_ovp = field.startswith('overpressure')
        plane = 'x-z' if '(x-z)' in field else 'x-y'
        g = slice_geometry(meta, plane)
        sl, solid, xf, yf = g.sl, g.solid, g.xf, g.yf
        pos = f"{g.axis} = {g.coord:.2f} m"
        if plane == 'x-z':
            xlabel, ylabel = 'x [m]', 'z [m]'
            raw = (snap['p'][sl] - np.float32(P_AIR) if is_ovp
                   else snap['rho_xz'])
        else:
            xlabel, ylabel = 'x [m]', 'y [m]'
            raw = (snap['p'][sl] - np.float32(P_AIR) if is_ovp
                   else snap['rho_xy'])
        if is_peak or is_imp:
            (_pl, pk), (_il, im) = plots.peak_items(meta, sl)
            z = pk if is_peak else im
            base = plots.PEAK_LABEL if is_peak else plots.IMPULSE_LABEL
            unit = f'{base} — {plane} slice at {pos}'
        elif is_ovp:
            z = raw / np.float32(1e3)
            unit = f'Overpressure [kPa] — {plane} slice at {pos}'
        else:
            z = raw
            unit = f'Density [kg/m³] — {plane} slice at {pos}'

    return dict(
        z=z, unit=unit, xf=xf, yf=yf, solid=solid, sl=sl,
        xlabel=xlabel, ylabel=ylabel, panel=panel,
        title=plots.titled(f'{field} - {plots.charge_label(meta)}',
                           title_extra),
        robust=bool(is_peak or is_imp))


class FieldsView(QWidget):
    """Snapshot / field selectors and Show mesh over one persistent
    image. `image` is rebuilt only when the grid it draws on changes -
    a new snapshot or a new field of the same plane reuses it."""

    def __init__(self, on_change=None, parent=None):
        super().__init__(parent)
        self._on_change = on_change or (lambda: None)
        self._ent = None
        self._title_extra = None
        self.image = None
        self.overlay = None
        self._key = None            # (label, xf.shape, yf.shape, sl repr)

        root = vbox(self)
        bar = hbox()
        bar.addWidget(label('Snapshot', 'muted'))
        self.snap_sel = QComboBox()
        self.snap_sel.setMinimumWidth(180)
        self.snap_sel.currentIndexChanged.connect(lambda *_: self.redraw())
        bar.addWidget(self.snap_sel)
        bar.addSpacing(theme.PAD)
        bar.addWidget(label('Field', 'muted'))
        self.field_sel = QComboBox()
        self.field_sel.setMinimumWidth(190)
        self.field_sel.currentIndexChanged.connect(lambda *_: self.redraw())
        bar.addWidget(self.field_sel)
        bar.addSpacing(theme.PAD)
        # cell edges over the field: the true cells of a refined
        # blastFoam run, every face otherwise
        self.show_mesh = QCheckBox('Show mesh')
        self.show_mesh.toggled.connect(lambda *_: self._mesh_toggled())
        bar.addWidget(self.show_mesh)
        bar.addStretch(1)
        root.addLayout(bar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.glw = pg.GraphicsLayoutWidget()
        self.plot = self.glw.addPlot(row=0, col=0)
        self.plot.setMenuEnabled(False)
        self.plot.hideButtons()
        self.stack.addWidget(self.glw)                  # page 0: maps
        self.canvas = MplCanvas()
        self.stack.addWidget(self.canvas)               # page 1: the rest
        self.hint = label('', 'muted', wrap=True, align=Qt.AlignCenter)
        self.stack.addWidget(self.hint)                 # page 2: nothing
        pg_plots.apply_theme(self.glw, [self.plot])
        theme.signals.changed.connect(self._retheme)
        # start on the hint, not on an empty pair of axes. A blank plot
        # with 0..1 ticks reads as "a result that contains nothing",
        # which is exactly the wrong thing to say before a run exists.
        self.clear()

    # ── state ────────────────────────────────────────────────────────────
    def set_title_extra(self, text):
        self._title_extra = text or None

    def _unreadable(self, text):
        """Say so on the placeholder page, but KEEP the entry: the user
        can still pick another field or snapshot, which is the whole
        point of not having raised."""
        self._drop_image()
        self.hint.setText(text)
        self.stack.setCurrentIndex(2)

    def clear(self, text=None):
        self._ent = None
        self._drop_image()
        for combo in (self.snap_sel, self.field_sel):
            combo.blockSignals(True)
            combo.clear()
            combo.blockSignals(False)
        self.hint.setText(NO_RESULT if text is None else text)
        self.stack.setCurrentIndex(2)

    def set_result(self, ent):
        """Adopt a result: repopulate both selectors without firing a
        redraw per change, then draw once."""
        self._ent = ent
        if ent is None:
            self.clear()
            return
        res = ent.result
        for combo, values, pick in (
                (self.snap_sel, list(res.snapshots.keys()), -1),
                (self.field_sel, field_options(res, ent.dim), 0)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems([str(v) for v in values])
            if values:
                combo.setCurrentIndex(pick if pick >= 0
                                      else len(values) - 1)
            combo.blockSignals(False)
        self._drop_image()               # a new result is a new grid
        self.redraw()

    def field(self):
        return self.field_sel.currentText()

    def snapshot(self):
        return self.snap_sel.currentText()

    def page(self):
        """'image' | 'figure' | 'empty' - what the stack is showing."""
        return ('image', 'figure', 'empty')[self.stack.currentIndex()]

    # ── drawing ──────────────────────────────────────────────────────────
    def _mesh_toggled(self):
        self.redraw()
        self._on_change()

    def _drop_image(self):
        if self.overlay is not None:
            self.overlay.remove()
        if self.image is not None:
            self.image.remove()
        self.image = self.overlay = None
        self._key = None

    def redraw(self):
        ent = self._ent
        if ent is None or not ent.result.snapshots:
            self.clear()
            return
        try:
            sel = select_field(ent.result, ent.dim, self.snapshot(),
                               self.field(), self._title_extra)
        except (KeyError, IndexError, ValueError) as exc:
            # A result whose meta does not match the dimension it was
            # filed under - a 3D entry holding a 2D result, say - used to
            # raise straight out of a refresh and take the panel with it.
            # A result the panel cannot read is a blank panel that says
            # so, not a traceback.
            self._unreadable(f'{self.field()} cannot be read from this '
                             f'result ({type(exc).__name__}: {exc}).')
            return
        if sel is None:
            self._draw_figure(ent)
            return
        self._draw_map(ent, sel)

    def _draw_figure(self, ent):
        """The two non-map views, through the same matplotlib builders
        the file exports use."""
        res = ent.result
        try:
            if ent.dim == 1:
                c = charge_label(res.meta)
                fig = plots.figure_results_1d(
                    res.snapshots, c.eos, c.charge_kg, c.radius_m,
                    title_extra=self._title_extra)
            else:
                fig = plots.figure_isosurfaces_3d(
                    res.snapshots, res.meta,
                    title_extra=self._title_extra)
        except Exception as exc:
            self.hint.setText(f'Could not draw this view: {exc}')
            self.stack.setCurrentIndex(2)
            return
        self.canvas.set_figure(fig)
        self.stack.setCurrentIndex(1)

    def _draw_map(self, ent, sel):
        key = (str(ent.label), np.shape(sel['xf']), np.shape(sel['yf']),
               repr(sel['sl']))
        if key != self._key:
            self._drop_image()
            self.image = pg_plots.ScalarImage(
                self.plot, sel['xf'], sel['yf'], sel['solid'],
                label=sel['unit'])
            self.overlay = pg_plots.MeshOverlay(self.plot)
            self._key = key
        else:
            # the same grid, a different plane's mask can still differ
            self.image.rebuild_mask(sel['solid'])
        self.image.set_labels(sel['xlabel'], sel['ylabel'])
        _lo, _hi, clipped = self.image.set_data(sel['z'],
                                                robust=sel['robust'])
        # pyqtgraph has no equivalent of matplotlib's extend='max'
        # arrow, so the clip says so in words - in the same wording the
        # exported PNG uses
        self.image.set_bar_label(
            sel['unit'] + (pg_plots.CLIP_BAR_SUFFIX if clipped else ''))
        title = f"{sel['title']}  ·  {sel['panel']}"
        if clipped:
            title += pg_plots.CLIP_TITLE_SUFFIX
        self.plot.setTitle(title, color=theme.cur('text'), size='10pt')
        self._title = title
        if self.show_mesh.isChecked():
            try:
                self.overlay.set_segments(
                    plots.mesh_for(ent.result.meta, sel['xf'], sel['yf'],
                                   sel['sl']))
            except Exception:
                self.overlay.clear()
        else:
            self.overlay.clear()
        self.stack.setCurrentIndex(0)

    def title(self):
        return getattr(self, '_title', '')

    def _retheme(self, _mode=None):
        pg_plots.apply_theme(self.glw, [self.plot])
        if self.overlay is not None:
            self.overlay.retheme()
        self.canvas.retheme()
