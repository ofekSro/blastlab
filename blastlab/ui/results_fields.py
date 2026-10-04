"""The Results tab's field maps: ONE large field panel plus selectors.
Since GUI-7 T6 it is an engine of the Field view (`results_field`), which
hides its selectors and drives them, and sets its colour scale.

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
from PySide6.QtWidgets import (QComboBox, QPushButton, QStackedWidget,
                               QWidget)
import pyqtgraph as pg

from ..core.constants import P_AIR
from ..models.meta import charge_label, slice_geometry
from ..output import animation as anim_mod
from ..output import plots
from . import pg_plots, theme
from .mpl_canvas import MplCanvas
from .widgets import WrapRow, hbox, label, vbox

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


def screen_unit(unit):
    """The colour-bar label as the screen shows it. UXR-15 (D221): the
    Impulse map reads kPa·ms, as the Gauges table beside it does; the
    number is the same, because 1 Pa·s = 1 kPa·ms. `select_field`'s `unit`
    (the exported PNG's label, `plots.IMPULSE_LABEL`) is unchanged."""
    return unit.replace('[Pa·s]', '[kPa·ms]')


def screen_title_1d(c):
    """The 1D profile figure's title on screen (F17, D214): `1D spherical
    · 1.0 kg TNT · JWL`, with the builder's own charge and EOS wording
    (`kg TNT` is E1's open question). `plots.figure_results_1d`'s
    `1D Spherical Blast - 1.0 kg TNT - EOS: JWL` stays in every export.

    Three title styles meet on Results (GUI-12 B3, UX quick win 5): this
    short 1D one on screen; the 2D map's `<field> - <charge_label>` and the
    3D plane's, which `select_field` builds and the exports reuse unchanged.
    The 1D canvas's tooltip names the full export title."""
    return f'1D spherical · {c.charge_kg} kg TNT · {c.eos}'


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


def whole_run_clim(res, dim, field, sel):
    """One colour range for every snapshot of `field` (GUI-7 T6, the
    snapshot maps' `whole run` scale), or None when there is nothing
    finite: overpressure through `output.animation.frame_clim` (the
    video's own rule, robust top included), density and speed through the
    finite min..max with solid cells excluded. Returns (lo, hi, clipped).
    """
    solid = sel['solid']
    if field.startswith('overpressure'):
        pressures = [(s['p'] if sel['sl'] is None else s['p'][sel['sl']])
                     for s in res.snapshots.values()]
        lo, hi, clipped = anim_mod.frame_clim(pressures, solid)
        return None if lo is None else (lo, hi, clipped)
    lo, hi = np.inf, -np.inf
    for label in res.snapshots:
        z = select_field(res, dim, label, field)['z']
        zm = np.asarray(z, dtype=np.float64)
        if solid is not None and np.shape(solid) == zm.shape:
            zm = np.where(solid, np.nan, zm)
        if not np.isfinite(zm).any():
            continue
        lo = min(lo, float(np.nanmin(zm)))
        hi = max(hi, float(np.nanmax(zm)))
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return None
    if hi <= lo:
        hi = lo + 1.0
    return lo, hi, False


class FieldsView(QWidget):
    """Snapshot / field selectors and Show mesh over one persistent
    image. `image` is rebuilt only when the grid it draws on changes -
    a new snapshot or a new field of the same plane reuses it.

    GUI-7 T6: the drawing engine behind the Field view. Its selectors
    (`controls`) are hidden there and driven by the visible controls of
    `results_field.FieldView`; `set_scale` gives the snapshot maps the
    Field view's colour scale."""

    def __init__(self, on_change=None, parent=None):
        super().__init__(parent)
        self._on_change = on_change or (lambda: None)
        self._ent = None
        self._title_extra = None
        self.image = None
        self.overlay = None
        self._key = None            # (label, xf.shape, yf.shape, sl repr)
        # 'frame' is the per-snapshot autoscale this view always had; the
        # Field view sets the result's recorded scale (set_scale)
        self._scale = 'frame'
        self._clim = None
        self._scale_used = 'frame'
        self._run_cache = {}        # field -> whole_run_clim(...)

        root = vbox(self)
        # the selectors wrap onto a second line rather than hold the
        # Results centre at 657 px between its two side columns (GUI-7:
        # placement only - the widgets and what they drive are unchanged)
        bar = WrapRow(spacing=theme.PAD)
        snap = QWidget()
        sl = hbox(snap)
        sl.addWidget(label('Snapshot', 'muted'))
        self.snap_sel = QComboBox()
        self.snap_sel.setMinimumWidth(180)
        self.snap_sel.currentIndexChanged.connect(lambda *_: self.redraw())
        sl.addWidget(self.snap_sel)
        bar.add(snap)
        fld = QWidget()
        fl = hbox(fld)
        fl.addWidget(label('Field', 'muted'))
        self.field_sel = QComboBox()
        self.field_sel.setMinimumWidth(190)
        self.field_sel.currentIndexChanged.connect(lambda *_: self.redraw())
        fl.addWidget(self.field_sel)
        bar.add(fld)
        # cell edges over the field: the true cells of a refined
        # blastFoam run, every face otherwise. A checkable button (board
        # line 217) with the tick box's setChecked / isChecked / toggled;
        # the Field view puts it in its own row
        self.show_mesh = QPushButton('Show mesh')
        self.show_mesh.setObjectName('fieldmesh')
        self.show_mesh.setCheckable(True)
        self.show_mesh.setCursor(Qt.PointingHandCursor)
        self.show_mesh.setToolTip('Draw the cell edges over the field (the '
                                  'true cells of a refined blastFoam run)')
        self.show_mesh.toggled.connect(lambda *_: self._mesh_toggled())
        bar.add(self.show_mesh)
        self._bar = bar
        #: the engine's own selector row: hidden under the Field view
        self.controls = bar
        root.addWidget(bar)

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
        self._run_cache = {}            # a different run, other ranges
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

    def take_show_mesh(self):
        """Hand Show mesh to the Field view's own row (GUI-7 T6). It is
        still this view's `show_mesh`, the state it and the exports read;
        only its place changes."""
        if self.show_mesh in self._bar._items:
            self._bar._items.remove(self.show_mesh)
        return self.show_mesh

    # ── the colour scale of the snapshot maps (GUI-7 T6) ─────────────────
    def set_scale(self, scale, clim=None, redraw=True):
        """`scale` 'run' (one range over every snapshot of the field),
        'frame' (each snapshot autoscaled, as this view always did) or
        'manual' with `clim` (lo, hi) in the field's own unit. The
        whole-run peak / impulse maps are single images: 'run' and
        'frame' both keep their robust autoscale there."""
        self._scale = scale if scale in ('run', 'frame', 'manual') else 'run'
        self._clim = clim
        if redraw:
            self.redraw()

    def scale(self):
        return self._scale

    def scale_used(self):
        """What the map on screen applied: a 'manual' range that is
        missing or inverted falls back to 'run', as the video does."""
        return self._scale_used

    def _levels_for(self, ent, sel):
        """(clim or None, clipped) for this map under the chosen scale;
        None means the autoscale of `set_data` (each frame, and the
        whole-run maps outside manual)."""
        if self._scale == 'manual':
            try:
                lo, hi = float(self._clim[0]), float(self._clim[1])
            except (TypeError, ValueError, IndexError):
                lo = hi = 0.0
            if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
                self._scale_used = 'manual'
                return (lo, hi), False
        if sel['robust'] or self._scale == 'frame':
            self._scale_used = 'frame'
            return None, False
        field = self.field()
        if field not in self._run_cache:
            try:
                self._run_cache[field] = whole_run_clim(
                    ent.result, ent.dim, field, sel)
            except (KeyError, IndexError, ValueError):
                self._run_cache[field] = None
        hit = self._run_cache[field]
        if hit is None:
            self._scale_used = 'frame'
            return None, False
        self._scale_used = 'run'
        return (hit[0], hit[1]), bool(hit[2])

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
                # on screen only: the builder's one-shot tight_layout is
                # for its own 10-inch page, and in the Results centre
                # (468 px at 1100 x 720) the tick labels and the title
                # fell outside the canvas. Laid out again at every draw,
                # at the canvas's size (GUI-7 verification)
                fig.set_layout_engine('tight')
                # F17 (GUI-11 T19, D214): on screen only, a title that
                # fits the canvas; the builder and every export keep
                # `1D Spherical Blast - … - EOS: …`
                # GUI-12 B3 (UX finding 2): say so - the tooltip carries
                # the builder's own title, read back, never retyped
                full = fig.axes[0].get_title()
                fig.axes[0].set_title(plots.titled(
                    screen_title_1d(c), self._title_extra))
                self.canvas.setToolTip(f'Exports use the full title: {full}')
            else:
                self.canvas.setToolTip('')
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
        self.canvas.setToolTip('')          # the 1D title hint is 1D only
        key = (str(ent.label), np.shape(sel['xf']), np.shape(sel['yf']),
               repr(sel['sl']))
        if key != self._key:
            self._drop_image()
            self.image = pg_plots.ScalarImage(
                self.plot, sel['xf'], sel['yf'], sel['solid'],
                label=screen_unit(sel['unit']))
            self.overlay = pg_plots.MeshOverlay(self.plot)
            self._key = key
        else:
            # the same grid, a different plane's mask can still differ
            self.image.rebuild_mask(sel['solid'])
        self.image.set_labels(sel['xlabel'], sel['ylabel'])
        clim, run_clipped = self._levels_for(ent, sel)
        _lo, _hi, clipped = self.image.set_data(sel['z'], clim=clim,
                                                robust=sel['robust'])
        # pyqtgraph has no equivalent of matplotlib's extend='max'
        # arrow, so the clip says so in words - in the same wording the
        # exported PNG uses. A whole-run range clipped by frame_clim says
        # so on the bar only, as the replay does.
        self.image.set_bar_label(
            screen_unit(sel['unit']) + (pg_plots.CLIP_BAR_SUFFIX
                           if clipped or run_clipped else ''))
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
