"""The Results screen's Field view (GUI-7 T6, board Results lines 191-286):
Fields and Animation as ONE view (owner, plan section 7).

Placement, not engines (the GUI-5 rule "split its placement, not its
parsing"). `results_fields.FieldsView` (snapshot maps, the matplotlib page,
the hint) and `results_anim.AnimView` (the recorded replay, `resolve_clim`,
the play timer) still draw everything. Their own selectors - `snap_sel`,
`field_sel`, `scale_sel`, `min_box`, `max_box`, `slider`, `play_btn`,
`speed_sel` - stay alive and hidden, as the state the engines read (the
pinned characterisations, the R- and E-checks and the QA harness drive
them). This view puts the board's controls on top and keeps both in step,
both ways, with `blockSignals` against loops.

- **Field:** a Segmented of the base fields (+ Plane in 3D) composing
  exactly one string of `field_options(res, dim)`, written into
  `field_sel`. 1D shows its profiles and no controls.
- **Colours:** whole run · each frame · manual -> `scale_sel`, the
  Animation export's option as before, and `FieldsView.set_scale` for the
  snapshot maps. Min / Max only for manual, in the field's unit and
  remembered per field; `min_box` / `max_box` hold the overpressure range,
  the only one the export carries.
- **Time bar:** the recorded frames for Overpressure when the result has
  them, else the snapshots; Play, the time, a slider with a cyan tick at
  the selected gauge's arrival, `6.31 ms · 61 frames`, the speed, This
  frame .png. None for the whole-run maps, 1D profiles and the isosurface.
- **Hover:** the displayed cell under the pointer (`ScalarImage.value_at`).
"""

import math
import os
import re
import threading

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QDoubleValidator, QPainter
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QProgressBar, QPushButton,
                               QSlider, QStackedWidget, QStyle,
                               QStyleOptionSlider, QVBoxLayout, QWidget)

from ..core.constants import ANIM_SCALE_LABELS, P_AIR
from ..models.meta import anim_scale_of, frames_of
from ..output import plots
from . import dialogs, theme
from .results_anim import SPEED_LABELS, plane_geometry
from .results_fields import field_options, select_field
from .widgets import Segmented, WrapRow

#: (field_options key, the Segmented label), board line 195-197
BASES = (('overpressure', 'Overpressure'), ('density', 'Density'),
         ('speed', 'Speed'), ('peak overpressure', 'Peak'),
         ('net ovp impulse', 'Impulse'), ('isosurface', 'Isosurface'))
KEY_OF = {lbl: key for key, lbl in BASES}
LABEL_OF = {key: lbl for key, lbl in BASES}
PLANES = ('x-z', 'x-y')
#: (scale, the Segmented label), board lines 202-204
SCALES = (('run', 'whole run'), ('frame', 'each frame'),
          ('manual', 'manual'))
SCALE_OF = {lbl: key for key, lbl in SCALES}
SCALE_LABEL = dict(SCALES)
#: the unit of each base field's Min / Max and of the hover value
UNITS = {'Overpressure': 'kPa', 'Density': 'kg/m³', 'Speed': 'm/s',
         'Peak': 'kPa',
         'Impulse': re.search(r'\[(.*)\]', plots.IMPULSE_LABEL).group(1)}
#: the hover readout's name of each base field (board line 245)
HOVER_NAMES = {'Overpressure': 'overpressure', 'Density': 'density',
               'Speed': 'speed', 'Peak': 'peak overpressure',
               'Impulse': 'net ovp impulse'}
#: the speed box: SPEED_LABELS ('0.25x' ...) written with a real ×
SPEED_SHOWN = [s.replace('x', '×') for s in SPEED_LABELS]

COLOUR_NOTE = ('The colour choice here is also the one the animation export '
               'uses.')
NO_BAR = {
    'whole': 'A whole-run map is one picture of the run, so it has no time '
             'bar.',
    '1d': 'The profiles of every snapshot are drawn together, so there is '
          'no time bar.',
    'iso': 'The isosurfaces of every snapshot are drawn together, so there '
           'is no time bar.',
}
#: the board's time bar (lines 267-283) and control heights (D41: pinned
#: in the QSS too)
PLAY_D = 40
BAR_H = 32
TICK_W, TICK_H = 2, 8


def decompose(field):
    """(base label, plane or None) of a `field_options` string."""
    m = re.match(r'(.*) \((x-z|x-y)\)$', field or '')
    key, plane = (m.group(1), m.group(2)) if m else (field, None)
    return LABEL_OF.get(key), plane


def compose(base, plane, dim):
    """The `field_options` string of a base label and a plane."""
    key = KEY_OF[base]
    if dim == 3 and base != 'Isosurface':
        return f'{key} ({plane or PLANES[0]})'
    return key


def snapshot_ms(label):
    """The time [ms] of a snapshot label (`t = 0.200 ms (final)`), or
    None when it does not parse."""
    m = re.search(r't\s*=\s*([-+0-9.eE]+)\s*ms', str(label))
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None


def nearest(times, t):
    """Index of the finite entry of `times` nearest `t`, or None."""
    best = None
    for k, v in enumerate(times):
        if v is None or t is None or not math.isfinite(v):
            continue
        if best is None or abs(v - t) < abs(times[best] - t):
            best = k
    return best


def frames_plane(meta):
    """The Field view's plane of a 3D result's recorded frames: 'x-z'
    (slice across y), 'x-y' (across z), or None for a y-z recording (no
    Field plane matches it, so the replay shows under either)."""
    try:
        axis = plane_geometry(meta).get('plane', '')[:1] if meta else ''
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return {'y': 'x-z', 'z': 'x-y'}.get(axis)


def _slug(text):
    return re.sub(r'[^0-9A-Za-z.-]+', '_', str(text)).strip('_')


class _Row(WrapRow):
    """A WrapRow that plans only the widgets on show: a hidden group
    (Plane, the manual range) takes no room and makes no empty line."""

    def _visible(self):
        return [w for w in self._items if not w.isHidden()]

    def _plan_rows(self, avail):
        keep = self._items
        self._items = self._visible()
        try:
            return super()._plan_rows(avail)
        finally:
            self._items = keep

    def _row_height(self):
        return max((w.sizeHint().height() for w in self._visible()),
                   default=0)

    def minimumSizeHint(self):
        vis = self._visible()
        if not vis:
            return QSize(0, 0)
        widest = max(w.sizeHint().width() for w in vis)
        return QSize(widest,
                     self._height_of(self._plan_rows(max(1, self.width()))))

    def sizeHint(self):
        vis = self._visible()
        if not vis:
            return QSize(0, 0)
        total = (sum(w.sizeHint().width() for w in vis)
                 + self._spacing * (len(vis) - 1))
        return QSize(total,
                     self._height_of(self._plan_rows(max(1, self.width()))))

    def refresh(self):
        """Re-plan after a group was shown or hidden."""
        self._relayout(force=True)

    def event(self, e):
        # a child's size hint changes without a resize of the row (the
        # segment buttons grow once their style sheet is applied): the
        # lines are planned again, or a stale plan squeezes them
        if e.type() == QEvent.LayoutRequest:
            self._relayout()
        return super().event(e)


def _group(*widgets, name=None):
    """Widgets side by side in one QWidget (one unit of the wrap)."""
    w = QFrame() if name else QWidget()
    if name:
        w.setObjectName(name)
    lay = QHBoxLayout(w)
    lay.setContentsMargins(*((3, 3, 3, 3) if name else (0, 0, 0, 0)))
    lay.setSpacing(8 if not name else 0)
    for x in widgets:
        lay.addWidget(x)
    return w


class TickSlider(QSlider):
    """The time bar's slider with cyan ticks under the groove at given
    positions (the selected gauge's arrival, board lines 277-278)."""

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setObjectName('timeslider')
        self.setFixedHeight(26)
        self.setMinimumWidth(80)
        self._ticks = []

    def set_ticks(self, positions):
        self._ticks = [int(k) for k in positions]
        self.update()

    def ticks(self):
        return list(self._ticks)

    def tick_x(self, k):
        """The x [px] of a tick at value `k`: under the handle's centre
        when the handle sits at `k`."""
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        handle = self.style().subControlRect(QStyle.CC_Slider, opt,
                                             QStyle.SC_SliderHandle, self)
        span = max(1, self.width() - handle.width())
        return (QStyle.sliderPositionFromValue(
            self.minimum(), self.maximum(), int(k), span)
            + handle.width() / 2.0)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._ticks or self.maximum() <= self.minimum():
            return
        p = QPainter(self)
        colour = QColor(theme.cur('gauge'))
        for k in self._ticks:
            x = self.tick_x(k)
            p.fillRect(QRectF(x - TICK_W / 2.0, self.height() - TICK_H,
                              TICK_W, TICK_H), colour)
        p.end()


class TimeBar(QFrame):
    """Play/Pause · the time · the slider · `6.31 ms · 61 frames` · the
    speed · This frame .png (board lines 267-283). One line when it fits,
    else the slider keeps the first line and the rest go under it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('timebar')
        self.play_btn = QPushButton()
        self.play_btn.setObjectName('playround')
        self.play_btn.setFixedSize(PLAY_D, PLAY_D)
        self.play_btn.setIconSize(QSize(14, 14))
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.time_lbl = QLabel('')
        self.time_lbl.setObjectName('timenow')
        self.time_lbl.setMinimumWidth(76)
        self.slider = TickSlider()
        self.length_lbl = QLabel('')
        self.length_lbl.setObjectName('timelen')
        self.speed = QComboBox()
        self.speed.setObjectName('timespeed')
        self.speed.addItems(SPEED_SHOWN)
        self.speed.setCurrentIndex(SPEED_LABELS.index('1x'))
        self.speed.setToolTip('How fast the replay advances. It changes the '
                              'playback only - the exported video keeps its '
                              'own frame rate.')
        self.frame_btn = QPushButton('This frame .png')
        self.frame_btn.setObjectName('framebtn')
        self.frame_btn.setCursor(Qt.PointingHandCursor)
        self.frame_btn.setToolTip('Save the frame on screen as one PNG panel, '
                                  'with the colour range on screen')
        # the busy strip that replaces the button while it writes (T3's)
        self.frame_busy = QFrame()
        self.frame_busy.setObjectName('framebusy')
        bl = QVBoxLayout(self.frame_busy)
        bl.setContentsMargins(10, 3, 10, 4)
        bl.setSpacing(3)
        busy_row = QHBoxLayout()
        busy_row.setContentsMargins(0, 0, 0, 0)
        busy_row.setSpacing(8)
        name = QLabel('This frame')
        name.setObjectName('expbusyname')
        busy_row.addWidget(name)
        self.busy_text = QLabel('writing…')
        self.busy_text.setObjectName('expbusytext')
        busy_row.addWidget(self.busy_text)
        bl.addLayout(busy_row)
        self.busy_bar = QProgressBar()
        self.busy_bar.setObjectName('expbar')
        self.busy_bar.setTextVisible(False)
        self.busy_bar.setRange(0, 0)
        self.busy_bar.setFixedHeight(4)
        bl.addWidget(self.busy_bar)
        self.frame_busy.hide()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)
        self._row1 = QHBoxLayout()
        self._row1.setSpacing(14)
        self._row2 = QHBoxLayout()
        self._row2.setSpacing(14)
        lay.addLayout(self._row1)
        lay.addLayout(self._row2)
        self._tail = [self.length_lbl, self.speed, self.frame_btn,
                      self.frame_busy]
        self._one_line = None
        self._place(True)

    def _need(self):
        """Width of everything on one line with the slider at its
        minimum."""
        m = self.layout().contentsMargins()
        ws = [self.play_btn, self.time_lbl, self.length_lbl, self.speed,
              self.frame_btn]
        return (sum(w.sizeHint().width() for w in ws)
                + self.slider.minimumWidth() + 14 * len(ws)
                + m.left() + m.right())

    def _place(self, one_line):
        if one_line == self._one_line:
            return
        self._one_line = one_line
        for row in (self._row1, self._row2):
            while row.count():
                row.takeAt(0)
        self._row1.addWidget(self.play_btn)
        self._row1.addWidget(self.time_lbl)
        self._row1.addWidget(self.slider, 1)
        tail = self._row1 if one_line else self._row2
        tail.addWidget(self.length_lbl)
        if not one_line:
            tail.addStretch(1)
        for w in self._tail[1:]:
            tail.addWidget(w)
        self.updateGeometry()

    def one_line(self):
        return bool(self._one_line)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place(self.width() >= self._need())

    def minimumSizeHint(self):
        s = super().minimumSizeHint()
        m = self.layout().contentsMargins()
        row2 = (self.length_lbl.sizeHint().width()
                + self.speed.sizeHint().width()
                + self.frame_btn.sizeHint().width() + 2 * 14)
        row1 = PLAY_D + self.time_lbl.minimumWidth() \
            + self.slider.minimumWidth() + 2 * 14
        return QSize(max(row1, row2) + m.left() + m.right(), s.height())

    def set_busy(self, on):
        self.frame_btn.setVisible(not on)
        self.frame_busy.setVisible(bool(on))

    def busy(self):
        return not self.frame_busy.isHidden()


class FieldView(QWidget):
    """The Field view over the two engines (see the module docstring).
    `fields` and `anim` are the panel's FieldsView and AnimView; `bridge`
    posts a worker's end back to the GUI thread (This frame .png)."""

    def __init__(self, fields, anim, bridge=None, log=print, parent=None):
        super().__init__(parent)
        self.fields, self.anim = fields, anim
        self._bridge = bridge
        self._log = log
        self._ent = None
        self._mode = None           # 'frames' | 'snapshots' | None
        self._why = None            # the NO_BAR reason when mode is None
        self._times = []            # ms per timeline position (or None)
        self._ranges = {}           # base label -> (lo text, hi text)
        self._gauge = None          # the selected gauge (T5)
        self._gauge_label = None    # its `G<n>` as Gauges shows it
        self._arrival = float('nan')
        self._syncing = False
        self._keep_time = False
        self.last_frame_figure = None
        fields.controls.hide()
        anim.controls.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        card = QFrame()
        card.setObjectName('fieldcard')
        cl = QVBoxLayout(card)
        cl.setContentsMargins(1, 1, 1, 1)
        cl.setSpacing(0)

        # ── the controls row (board 193-218) ─────────────────────────────
        self.ctl = QWidget()
        self.ctl.setObjectName('fieldctl')
        ctl_lay = QVBoxLayout(self.ctl)
        ctl_lay.setContentsMargins(12, 10, 12, 10)
        self.row = _Row(spacing=14)
        self.field_seg = Segmented(['Overpressure'], height=28, small=True)
        self.field_seg.changed.connect(self._pick_base)
        self.field_grp = _group(self.field_seg, name='fieldseg')
        self.row.add(self.field_grp)
        self.plane_seg = Segmented(list(PLANES), height=28, small=True)
        self.plane_seg.changed.connect(self._pick_plane)
        plane_lbl = QLabel('Plane')
        plane_lbl.setObjectName('fieldkey')
        self.plane_grp = _group(plane_lbl, _group(self.plane_seg,
                                                  name='fieldseg'))
        self.row.add(self.plane_grp)
        colours = QLabel('Colours')
        colours.setObjectName('fieldkey')
        self.scale_seg = Segmented([lbl for _k, lbl in SCALES], height=28,
                                   small=True)
        self.scale_seg.changed.connect(self._pick_scale)
        self.scale_seg.setToolTip(
            'One range for the whole run keeps the colour bar meaningful '
            'from frame to frame; each frame rescales every picture; a '
            'manual range lets you compare two runs. The Animation export '
            'uses this choice.')
        self.scale_grp = _group(colours, _group(self.scale_seg,
                                                name='fieldseg'))
        self.row.add(self.scale_grp)
        self.min_edit, self.max_edit = QLineEdit(), QLineEdit()
        parts = []
        for cap, box in (('Min', self.min_edit), ('Max', self.max_edit)):
            lbl = QLabel(cap)
            lbl.setObjectName('fieldkey')
            box.setObjectName('fieldrange')
            box.setFixedWidth(64)
            box.setValidator(QDoubleValidator(-1e12, 1e12, 6, box))
            box.editingFinished.connect(self._pick_range)
            parts += [lbl, box]
        self.unit_lbl = QLabel('kPa')
        self.unit_lbl.setObjectName('fieldunit')
        self.manual_grp = _group(*parts, self.unit_lbl)
        self.row.add(self.manual_grp, hidden=True)
        self.show_mesh = fields.take_show_mesh()
        self.row.add(self.show_mesh)
        ctl_lay.addWidget(self.row)
        cl.addWidget(self.ctl)

        # ── the map: the engines' own pages (board 220-265) ──────────────
        self.map_stack = QStackedWidget()
        self.map_stack.addWidget(fields)                 # 0: snapshot maps
        self.map_stack.addWidget(anim)                   # 1: the replay
        cl.addWidget(self.map_stack, 1)

        # ── the time bar (board 267-283) ─────────────────────────────────
        self.timebar = TimeBar()
        self.timebar.slider.valueChanged.connect(self._slider_moved)
        self.timebar.play_btn.clicked.connect(lambda *_: self.toggle_play())
        self.timebar.speed.currentIndexChanged.connect(self._pick_speed)
        self.timebar.frame_btn.clicked.connect(
            lambda *_: self.save_frame_png())
        cl.addWidget(self.timebar)
        root.addWidget(card, 1)
        self.caption = QLabel(COLOUR_NOTE)
        self.caption.setObjectName('fieldcaption')
        self.caption.setWordWrap(True)
        root.addWidget(self.caption)

        # the snapshots play on their own timer, at the replay's rate
        self._snap_timer = QTimer(self)
        self._snap_timer.timeout.connect(self._snap_tick)

        # engines -> these controls
        fields.field_sel.currentIndexChanged.connect(
            lambda *_: self._engine_field_changed())
        fields.snap_sel.currentIndexChanged.connect(
            lambda *_: self._engine_snap_changed())
        anim.scale_sel.currentIndexChanged.connect(
            lambda *_: self._engine_scale_changed())
        for box in (anim.min_box, anim.max_box):
            box.editingFinished.connect(self._engine_range_changed)
        anim.frame_shown.connect(self._frame_shown)
        anim.playing_changed.connect(lambda *_: self._sync_play())
        anim.speed_sel.currentIndexChanged.connect(
            lambda *_: self._engine_speed_changed())

        # the hover readout, one per engine plot (board 243-245)
        self._hover = {}
        for name, plot in (('fields', fields.plot), ('anim', anim.plot)):
            item = pg.TextItem('', anchor=(0.0, 1.1))
            item.setZValue(20)
            item.hide()
            plot.vb.addItem(item, ignoreBounds=True)
            self._hover[name] = item
            plot.scene().sigMouseMoved.connect(
                lambda pos, n=name: self.hover_scene(pos, n))
        self._hover_text = ''

        theme.signals.changed.connect(self._retheme)
        self._retheme()
        self.set_result(None)

    # ── adopting a result ────────────────────────────────────────────────
    def adopt_scale(self, ent):
        """Before the engines take `ent`: its recorded colour scale (as
        AnimView does for a replay) on `scale_sel` and on the snapshot
        maps, so they draw once, in the right range."""
        if ent is None:
            return
        scale, clim = anim_scale_of(ent.result.meta)
        a = self.anim
        a.scale_sel.blockSignals(True)
        a.scale_sel.setCurrentText(ANIM_SCALE_LABELS[scale])
        a.scale_sel.blockSignals(False)
        if clim:
            a.min_box.setText(f'{float(clim[0]):g}')
            a.max_box.setText(f'{float(clim[1]):g}')
        a._set_manual_visible(scale == 'manual')
        self.fields.set_scale(scale, a.clim() if scale == 'manual' else None,
                              redraw=False)

    def set_result(self, ent):
        """After the engines took `ent`: rebuild the controls, then the
        timeline (frames or snapshots)."""
        self.stop_play()
        self._ent = ent
        has = ent is not None and ent.dim in (2, 3) \
            and bool(ent.result.snapshots)
        self.ctl.setVisible(has)
        if ent is None:
            self._set_mode(None, None)
            self._update_caption()
            return
        self._rebuild_field_seg(ent)
        self._syncing = True
        try:
            self._sync_field_controls()
            self._sync_scale_controls()
        finally:
            self._syncing = False
        self._apply_fields_scale()
        self._update_timeline(keep=False)

    def _rebuild_field_seg(self, ent):
        bases = []
        for f in field_options(ent.result, ent.dim):
            b, _p = decompose(f)
            if b and b not in bases:
                bases.append(b)
        if bases and self.field_seg.values() != bases:
            new = Segmented(bases, height=28, small=True)
            new.changed.connect(self._pick_base)
            lay = self.field_grp.layout()
            lay.replaceWidget(self.field_seg, new)
            # out of sight now: deleteLater waits for the event loop,
            # and the old row drew under the new one until then
            self.field_seg.hide()
            self.field_seg.setParent(None)
            self.field_seg.deleteLater()
            self.field_seg = new
            self.row.refresh()

    # ── reading the state ────────────────────────────────────────────────
    def base(self):
        """The base field on screen ('Overpressure', ...), or None (1D)."""
        return decompose(self.fields.field())[0]

    def _range_base(self):
        """Whose range Min / Max edit: the field on screen, or - with no
        map (1D) - the overpressure range, the one the export carries."""
        return self.base() or 'Overpressure'

    def plane(self):
        return decompose(self.fields.field())[1]

    def scale(self):
        return self.anim.scale()

    def composed(self):
        """The `field_options` string the controls compose."""
        if self._ent is None or self._ent.dim == 1:
            return None
        base = self.field_seg.get()
        plane = self.plane_seg.get() if self._ent.dim == 3 else None
        return compose(base, plane, self._ent.dim)

    def mode(self):
        """'frames' | 'snapshots' | None: what the time bar steps."""
        return self._mode

    def page(self):
        """'map' (a FieldsView page) or 'replay' (the AnimView)."""
        return ('map', 'replay')[self.map_stack.currentIndex()]

    # ── controls -> engines ──────────────────────────────────────────────
    def _pick_base(self, value):
        if value:
            self.field_seg.set(value)
        self._pick_field()

    def _pick_plane(self, value):
        if value:
            self.plane_seg.set(value)
        self._pick_field()

    def _pick_field(self, *_):
        if self._syncing or self._ent is None:
            return
        want = self.composed()
        if want is None or want == self.fields.field():
            return
        base, _plane = decompose(want)
        # the new field's range first, so the map draws once
        self.fields.set_scale(self.scale(), self._clim_for(base),
                              redraw=False)
        # a switch made here keeps the time on the bar (the nearest frame
        # or snapshot); one made on the engine's own selector (a test,
        # the harness) leaves the engine's snapshot as it set it
        self._keep_time = True
        try:
            self.fields.field_sel.setCurrentText(want)
        finally:
            self._keep_time = False

    def _pick_scale(self, label):
        if self._syncing:
            return
        key = SCALE_OF.get(label, 'run')
        self.anim.scale_sel.setCurrentText(ANIM_SCALE_LABELS[key])

    def _pick_range(self):
        if self._syncing:
            return
        lo, hi = self.min_edit.text().strip(), self.max_edit.text().strip()
        base = self._range_base()
        if base == 'Overpressure':
            # the export's range: the replay's boxes, as before
            self.anim.min_box.setText(lo)
            self.anim.max_box.setText(hi)
            self.anim.max_box.editingFinished.emit()
        else:
            self._ranges[base] = (lo, hi)
            self._apply_fields_scale()

    def set_scale(self, scale, clim=None):
        """What the Colours control and Min / Max do: `scale` 'run' |
        'frame' | 'manual', and `clim` (lo, hi) typed for the field on
        screen."""
        self.scale_seg.set(SCALE_LABEL[scale])
        self._pick_scale(SCALE_LABEL[scale])
        if clim is not None:
            self.min_edit.setText(f'{float(clim[0]):g}')
            self.max_edit.setText(f'{float(clim[1]):g}')
            self._pick_range()

    def _pick_speed(self, i):
        if self._syncing:
            return
        self.anim.speed_sel.setCurrentText(SPEED_LABELS[i])

    # ── engines -> controls ──────────────────────────────────────────────
    def _engine_field_changed(self):
        if self._ent is None:
            return
        self._syncing = True
        try:
            self._sync_field_controls()
            self._show_range_boxes()
        finally:
            self._syncing = False
        self._apply_fields_scale()
        self._update_timeline(keep=self._keep_time)

    def _sync_field_controls(self):
        base, plane = decompose(self.fields.field())
        if base:
            self.field_seg.set(base)
        if plane:
            self.plane_seg.set(plane)
        show_plane = (self._ent is not None and self._ent.dim == 3
                      and base not in (None, 'Isosurface'))
        colours = base not in (None, 'Isosurface')
        changed = (self.plane_grp.isHidden() == show_plane
                   or self.scale_grp.isHidden() == colours)
        self.plane_grp.setVisible(show_plane)
        self.scale_grp.setVisible(colours)
        self.show_mesh.setVisible(colours)
        manual = colours and self.scale() == 'manual'
        if self.manual_grp.isHidden() == manual:
            self.manual_grp.setVisible(manual)
            changed = True
        if changed:
            self.row.refresh()

    def _engine_scale_changed(self):
        self._syncing = True
        try:
            self._sync_scale_controls()
        finally:
            self._syncing = False
        self._apply_fields_scale()
        self._update_ticks()

    def _sync_scale_controls(self):
        key = self.scale()
        self.scale_seg.set(SCALE_LABEL[key])
        manual = key == 'manual' and not self.scale_grp.isHidden()
        if self.manual_grp.isHidden() == manual:
            self.manual_grp.setVisible(manual)
            self.row.refresh()
        self._show_range_boxes()

    def _engine_range_changed(self):
        if self._range_base() == 'Overpressure':
            self._syncing = True
            try:
                self._show_range_boxes()
            finally:
                self._syncing = False
            self._apply_fields_scale()

    def _engine_speed_changed(self):
        self._syncing = True
        try:
            i = SPEED_LABELS.index(self.anim.speed_sel.currentText()) \
                if self.anim.speed_sel.currentText() in SPEED_LABELS else 2
            self.timebar.speed.setCurrentIndex(i)
        finally:
            self._syncing = False
        self._snap_timer.setInterval(self.anim.timer.interval())

    def _show_range_boxes(self):
        base = self._range_base()
        if base == 'Overpressure':
            lo, hi = self.anim.min_box.text(), self.anim.max_box.text()
        else:
            lo, hi = self._ranges.get(base, ('', ''))
        for box, text in ((self.min_edit, lo), (self.max_edit, hi)):
            if box.text() != text:
                box.setText(text)
        self.unit_lbl.setText(UNITS.get(base, ''))

    def _clim_for(self, base):
        """The manual range of `base` [its unit], or None (unusable)."""
        if base == 'Overpressure':
            return self.anim.clim()
        try:
            lo, hi = self._ranges.get(base, ('', ''))
            return (float(lo), float(hi))
        except (TypeError, ValueError):
            return None

    def manual_range(self, base=None):
        """The typed range of `base` (default: the field on screen)."""
        return self._clim_for(base or self._range_base())

    def _apply_fields_scale(self):
        """The snapshot maps follow the colour control: the scale, and
        the typed range of the field on screen."""
        key = self.scale()
        clim = self._clim_for(self.base()) if key == 'manual' else None
        f = self.fields
        if (f.scale(), f._clim) != (key, clim):
            f.set_scale(key, clim, redraw=self._ent is not None)

    # ── the timeline ─────────────────────────────────────────────────────
    def _timeline_mode(self):
        """(mode, reason): 'frames' for Overpressure with recorded frames
        (in 3D, when the plane is the recorded one), 'snapshots' for the
        other time-dependent maps, None (with why) otherwise."""
        ent = self._ent
        if ent is None or not ent.result.snapshots:
            return None, None
        if ent.dim == 1:
            return None, '1d'
        base, plane = decompose(self.fields.field())
        if base == 'Isosurface':
            return None, 'iso'
        if base in ('Peak', 'Impulse'):
            return None, 'whole'
        if base is None:
            return None, None
        meta = ent.result.meta
        frames = frames_of(meta)
        if base == 'Overpressure' and frames is not None \
                and len(frames['pressures']):
            fp = frames_plane(meta) if ent.dim == 3 else None
            if ent.dim == 2 or fp is None or fp == plane:
                return 'frames', None
        return 'snapshots', None

    def current_time_ms(self):
        """The time on the time bar [ms], or None."""
        if self._mode == 'frames':
            frames = frames_of(self._ent.result.meta)
            k = min(self.anim.frame(), len(frames['times']) - 1)
            return float(frames['times'][k]) * 1e3
        if self._mode == 'snapshots':
            return snapshot_ms(self.fields.snapshot())
        return None

    def _update_timeline(self, keep=True):
        t_now = self.current_time_ms() if keep else None
        mode, why = self._timeline_mode()
        if mode != self._mode:
            self.stop_play()
        self._set_mode(mode, why)
        if mode == 'frames':
            frames = frames_of(self._ent.result.meta)
            self._times = [float(t) * 1e3 for t in frames['times']]
            k = nearest(self._times, t_now) if t_now is not None else None
            if k is None:
                k = self.anim.frame()
            if self.anim.slider.value() != k or self.anim.frame() != k:
                self.anim.slider.setValue(k)
                if self.anim.frame() != k:
                    self.anim.show_frame(k)
            n, unit = len(self._times), 'frames'
        elif mode == 'snapshots':
            labels = [self.fields.snap_sel.itemText(i)
                      for i in range(self.fields.snap_sel.count())]
            self._times = [snapshot_ms(s) for s in labels]
            k = nearest(self._times, t_now) if t_now is not None else None
            if k is None:
                k = self.fields.snap_sel.currentIndex()
            if k != self.fields.snap_sel.currentIndex():
                self.fields.snap_sel.setCurrentIndex(k)
            n, unit = len(labels), 'snapshots'
        else:
            self._times = []
            self._update_ticks()
            self._update_caption()
            return
        s = self.timebar.slider
        s.blockSignals(True)
        s.setRange(0, max(0, n - 1))
        s.setValue(max(0, k))
        s.blockSignals(False)
        last = next((t for t in reversed(self._times) if t is not None),
                    None)
        self.timebar.length_lbl.setText(
            f'{last:.2f} ms · {n} {unit}' if last is not None
            else f'{n} {unit}')
        self._show_time()
        self._update_ticks()
        self._update_caption()

    def _set_mode(self, mode, why):
        self._mode, self._why = mode, why
        self.timebar.setVisible(mode is not None)
        self.map_stack.setCurrentIndex(1 if mode == 'frames' else 0)
        for item in self._hover.values():
            item.hide()

    def _show_time(self):
        k = self.timebar.slider.value()
        t = self._times[k] if 0 <= k < len(self._times) else None
        muted = theme.cur('muted')
        if t is None:
            text = self.fields.snapshot() if self._mode == 'snapshots' \
                else ''
        else:
            text = (f'{t:.2f} <span style="font-size: 12px; color: '
                    f'{muted};">ms</span>')
        self.timebar.time_lbl.setText(text)

    def time_text(self):
        """The time as shown, without the markup (tests)."""
        return re.sub(r'<[^>]+>', '', self.timebar.time_lbl.text())

    def _slider_moved(self, value):
        if self._mode == 'frames':
            # the replay's own slider: one move, one frame drawn (R5)
            self.anim.slider.setValue(value)
        elif self._mode == 'snapshots':
            self.fields.snap_sel.setCurrentIndex(value)
        self._show_time()

    def _frame_shown(self, k):
        if self._mode != 'frames':
            return
        s = self.timebar.slider
        if s.value() != k:
            s.blockSignals(True)
            s.setValue(k)
            s.blockSignals(False)
        self._show_time()

    def _engine_snap_changed(self):
        if self._mode != 'snapshots':
            return
        k = self.fields.snap_sel.currentIndex()
        s = self.timebar.slider
        if s.value() != k:
            s.blockSignals(True)
            s.setValue(k)
            s.blockSignals(False)
        self._show_time()

    # ── play ─────────────────────────────────────────────────────────────
    def playing(self):
        return self.anim.playing() or self._snap_timer.isActive()

    def toggle_play(self):
        if self.playing():
            self.stop_play()
        else:
            self.start_play()

    def start_play(self):
        if self._mode == 'frames':
            self.anim.start_play()
        elif self._mode == 'snapshots' and len(self._times) > 1:
            self._snap_timer.setInterval(self.anim.timer.interval())
            self._snap_timer.start()
        self._sync_play()

    def stop_play(self):
        self._snap_timer.stop()
        self.anim.stop_play()
        self._sync_play()

    def _snap_tick(self):
        n = self.fields.snap_sel.count()
        if self._mode != 'snapshots' or n < 2:
            self.stop_play()
            return
        k = (self.fields.snap_sel.currentIndex()
             + self.anim.frame_step()) % n
        self.fields.snap_sel.setCurrentIndex(k)

    def _sync_play(self):
        on = self.playing()
        b = self.timebar.play_btn
        b.setIcon(theme.icon('pause' if on else 'play', 14,
                             color='on_accent'))
        b.setToolTip('Pause' if on else 'Play')
        b.setAccessibleName('Pause' if on else 'Play')

    # ── the arrival tick (the selected gauge, T5) ────────────────────────
    def set_arrival(self, number, arrival_ms, label=None):
        """The selected gauge and its arrival [ms] (NaN: none). `label`
        is its `G<n>` as the Gauges table shows it (the entered number
        after a dropped gauge, D201); None: `G<number>`."""
        self._gauge = number
        self._gauge_label = label or (None if number is None
                                      else f'G{number}')
        try:
            self._arrival = float(arrival_ms)
        except (TypeError, ValueError):
            self._arrival = float('nan')
        self._update_ticks()
        self._update_caption()

    def tick_index(self):
        """The timeline position of the tick, or None."""
        if self._mode is None or not math.isfinite(self._arrival):
            return None
        return nearest(self._times, self._arrival)

    def _update_ticks(self):
        k = self.tick_index()
        self.timebar.slider.set_ticks([] if k is None else [k])

    def _update_caption(self):
        bits = []
        if self._mode is None and self._why:
            bits.append(NO_BAR[self._why])
        if self.tick_index() is not None and self._gauge is not None:
            bits.append(f'Cyan tick on the time bar: arrival at '
                        f'{self._gauge_label}.')
        if self._ent is not None and self._ent.dim != 1:
            bits.append(COLOUR_NOTE)
        self.caption.setText(' '.join(bits))
        self.caption.setVisible(bool(bits))

    # ── the hover readout ────────────────────────────────────────────────
    def _page_image(self, which):
        if which == 'fields':
            if self.page() != 'map' or self.fields.page() != 'image':
                return None, None
            return self.fields.image, self.fields.plot
        if self.page() != 'replay':
            return None, None
        return self.anim.image, self.anim.plot

    def hover_scene(self, pos, which=None):
        """The readout at scene point `pos` over engine plot `which`
        ('fields' | 'anim'; default: the page on screen). Hidden outside
        the domain and on the matplotlib pages."""
        which = which or ('anim' if self.page() == 'replay' else 'fields')
        for name, item in self._hover.items():
            if name != which:
                item.hide()
        item = self._hover[which]
        image, plot = self._page_image(which)
        if image is None:
            item.hide()
            self._hover_text = ''
            return None
        pt = plot.vb.mapSceneToView(QPointF(pos))
        x, y = float(pt.x()), float(pt.y())
        v = image.value_at(x, y)
        if v is None:
            item.hide()
            self._hover_text = ''
            return None
        ax = [plot.getAxis(a).labelText.split(' ')[0] or '?'
              for a in ('bottom', 'left')]
        base = 'Overpressure' if which == 'anim' else self.base()
        line1 = f'{ax[0]} {x:.2f} · {ax[1]} {y:.2f} m'
        line2 = ('solid' if v == 'solid' else
                 f'{HOVER_NAMES.get(base, "")} {v:.4g} {UNITS.get(base, "")}')
        p = theme.pal()
        item.setHtml(f'<div style="font-family: \'{theme.MONO}\'; '
                     f'font-size: 11px;"><span style="color: {p["text"]};">'
                     f'{line1}</span><br><span style="color: '
                     f'{p["accent_soft"]};">{line2}</span></div>')
        # kept inside the map, so the plot never cuts it off (at 1100 x
        # 720 it read `overpressure 1944 kP`): right of and above the
        # pointer when that fits, else slid left / put below, as a
        # tooltip is. The text is in px; so is the scene
        sp = QPointF(pos)
        # 2 px in from the edges: the readout's frame is drawn outside
        # its text box
        box = plot.vb.sceneBoundingRect().adjusted(2, 2, -2, -2)
        text = item.textItem.boundingRect()
        w, h = max(text.width(), 1.0), max(text.height(), 1.0)
        left = min(sp.x(), box.right() - w)
        left = max(left, box.left())
        top = sp.y() - 1.1 * h
        if top < box.top():
            top = sp.y() + 0.1 * h
        top = max(min(top, box.bottom() - h), box.top())
        item.setAnchor(((sp.x() - left) / w, (sp.y() - top) / h))
        item.setPos(x, y)
        item.show()
        # a TextItem undoes the view's scaling only once it has painted,
        # and one that starts hidden is scaled with the data (metres) and
        # lands far off screen, so it never paints: set it now
        item.updateTransform(force=True)
        self._hover_text = f'{line1}\n{line2}'
        return v

    def hover_text(self):
        """The readout's two lines, '' while hidden."""
        return self._hover_text

    def hover_visible(self, which=None):
        which = which or ('anim' if self.page() == 'replay' else 'fields')
        return self._hover[which].isVisible()

    # ── This frame .png ──────────────────────────────────────────────────
    def frame_spec(self):
        """What the frame on screen is, for its one-panel PNG: dict with
        items, solid, faces, labels, title, unit, aspect, mesh, the
        on-screen clim (None = the builder's own) and the file name's
        field and time. None without a time bar."""
        ent = self._ent
        if ent is None or self._mode is None:
            return None
        res, meta = ent.result, ent.result.meta
        extra = self.fields._title_extra
        mesh_on = self.fields.show_mesh.isChecked()
        if self._mode == 'frames':
            frames = frames_of(meta)
            g = plane_geometry(meta)
            k = self.anim.frame()
            t = float(frames['times'][k])
            z = (np.asarray(frames['pressures'][k], dtype=np.float64)
                 - P_AIR) / 1e3
            lv = frames.get('levels')
            mesh = None
            if mesh_on:
                mesh = plots.mesh_for(
                    meta, g['xf'], g['yf'], g['sl'],
                    levels=None if lv is None else lv[min(k, len(lv) - 1)])
            clim = self.anim._clim
            return dict(
                items=[(f"{g['plane']}t = {t * 1e3:.3f} ms", z),
                       ], solid=g['solid'], xf=g['xf'], yf=g['yf'],
                xlabel=g['xlabel'], ylabel=g['ylabel'],
                title=plots.titled(
                    f'overpressure - {plots.charge_label(meta)}', extra),
                unit='Overpressure [kPa]', mesh=mesh,
                clim=None if clim is None else tuple(clim),
                field='overpressure', t_ms=t * 1e3)
        label = self.fields.snapshot()
        sel = select_field(res, ent.dim, label, self.fields.field(), extra)
        mesh = (plots.mesh_for(meta, sel['xf'], sel['yf'], sel['sl'])
                if mesh_on else None)
        on_screen = self.fields.scale_used() in ('run', 'manual')
        clim = (tuple(self.fields.image.levels)
                if on_screen and self.fields.image is not None else None)
        return dict(items=[(label, sel['z'])], solid=sel['solid'],
                    xf=sel['xf'], yf=sel['yf'], xlabel=sel['xlabel'],
                    ylabel=sel['ylabel'], title=sel['title'],
                    unit=sel['unit'], mesh=mesh, clim=clim,
                    field=self.fields.field(), t_ms=snapshot_ms(label))

    @staticmethod
    def frame_figure(spec):
        """The one-panel matplotlib figure of `frame_spec` - the Tk Fields
        view's single-panel call (`plots._panel_grid_figure` with one
        item), the on-screen range set on its QuadMesh when there is
        one."""
        from matplotlib.collections import QuadMesh
        xf, yf = np.asarray(spec['xf']), np.asarray(spec['yf'])
        aspect = float((xf[-1] - xf[0]) / (yf[-1] - yf[0]))
        fig = plots._panel_grid_figure(
            spec['items'], spec['solid'], xf, yf, spec['xlabel'],
            spec['ylabel'], spec['title'], spec['unit'], aspect,
            mesh=spec['mesh'], robust=False)
        if spec['clim'] is not None:
            # the panel's mesh only; its colour bar follows the mappable
            for ax in fig.axes:
                if ax.get_label() == '<colorbar>':
                    continue
                for c in ax.collections:
                    if isinstance(c, QuadMesh):
                        c.set_clim(*spec['clim'])
        return fig

    def frame_name(self, spec):
        from .exports import name_prefix
        t = spec['t_ms']
        when = f'{t:.3f}ms' if t is not None else _slug(self.fields.snapshot())
        return (f'{name_prefix(self._ent.result)}field_'
                f'{_slug(spec["field"])}_{when}.png')

    def save_frame_png(self, threaded=True):
        """Ask where (in the model folder), then write the frame on screen
        as one PNG panel: dpi 150, bbox tight (the PNG export's settings).
        Threaded, the button is a busy strip until it is written. Returns
        the target, or ''."""
        from .exports import model_dir
        if self.timebar.busy():
            self._log('This frame is already being written.')
            return ''
        try:
            spec = self.frame_spec()
        except Exception as exc:
            self._log(f'This frame: cannot read it ({exc}).')
            return ''
        if spec is None:
            return ''
        home = model_dir(self._ent)
        name = self.frame_name(spec)
        target = dialogs.save_file(
            'Save this frame', 'PNG image (*.png)', self,
            os.path.join(home, name) if home else name, '.png')
        if not target:
            return ''

        def work():
            try:
                fig = self.frame_figure(spec)
                fig.savefig(target, dpi=150, bbox_inches='tight')
                self.last_frame_figure = fig
                self._log(f'Saved {target}')
            except Exception as exc:
                self._log(f'This frame failed: {exc}')

        if threaded:
            self.timebar.set_busy(True)

            def run():
                try:
                    work()
                finally:
                    if self._bridge is not None:
                        self._bridge.post(self.timebar.set_busy, False)
            threading.Thread(target=run, daemon=True).start()
        else:
            work()
        return target

    # ── theme ────────────────────────────────────────────────────────────
    def _retheme(self, _mode=None):
        self._sync_play()
        self._show_time()
        self.timebar.slider.update()
        for item in self._hover.values():
            item.fill = pg.mkBrush(theme.cur('bg'))
            item.border = pg.mkPen(theme.cur('border2'))
            item.hide()
