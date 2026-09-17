"""The Results tab's Animation view: replay the frames a run recorded.

The colour scale is a control here, not a hidden default. It applies to
the replay on screen AND to what the Animation export writes, and it
starts from the choice the run itself recorded (`meta['anim_scale']`),
so a video exported from this tab matches the one the run wrote unless
you say otherwise. See `output/animation.py` for the three modes.

The play timer and the slider would otherwise chase each other: the tick
moves the slider, whose signal would move the frame again. The
programmatic set is wrapped in blockSignals and guarded by `_playing`.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QComboBox, QLineEdit, QSlider, QWidget
import pyqtgraph as pg

from ..core.constants import ANIM_SCALE_LABELS, anim_scale_from_label
from ..output import animation as anim_mod
from ..output import plots
from . import pg_plots, theme
from .widgets import button, hbox, label, vbox

#: one frame every 66 ms (~15 fps), as the Tk replay ran
TICK_MS = 66

#: an empty string here left a blank panel that said nothing at all on a
#: fresh Results tab
NO_RESULT = ('Run a case with "Record replay frames" ticked, and the '
             'recorded frames replay here.')
NO_1D = '1D results have no animation frames.'

#: Replay speeds, as multiples of the base tick. Kept as labels rather
#: than a slider so two sessions can be compared: "it was slow at 1x" is
#: a statement, "it was slow with the handle about a third along" is not.
SPEED_FACTORS = {'0.25x': 0.25, '0.5x': 0.5, '1x': 1.0,
                 '2x': 2.0, '4x': 4.0}
SPEED_LABELS = list(SPEED_FACTORS)
SPEED_DEFAULT = '1x'
#: below this the timer is asked for more than Qt will deliver, so the
#: frames are stepped instead (see `_tick`)
MIN_INTERVAL_MS = 16
NO_FRAMES = ('No recorded frames for this result.\n'
             'Tick "Record replay frames" before the run; runs loaded '
             'from the foam run browser\ncarry snapshots but no replay '
             'frames.')


def plane_geometry(meta):
    """Faces, labels, mask and plane caption for the recorded frames.
    Mirrors `output/animation.py` so the replay and the exported video
    show the same plane."""
    if 'z_face' in meta:                       # 3D: the recorded slice
        s_ax = meta.get('slice_axis', 'y')
        s0 = meta.get('s0', meta['j0'])
        xf, yf = {'x': (meta['y_face'], meta['z_face']),
                  'y': (meta['x_face'], meta['z_face']),
                  'z': (meta['x_face'], meta['y_face'])}[s_ax]
        xlabel, ylabel = {'x': ('y [m]', 'z [m]'),
                          'y': ('x [m]', 'z [m]'),
                          'z': ('x [m]', 'y [m]')}[s_ax]
        sl = tuple(s0 if a == 'xyz'.index(s_ax) else slice(None)
                   for a in range(3))
        return dict(xf=xf, yf=yf, xlabel=xlabel, ylabel=ylabel, sl=sl,
                    solid=meta['solid'][sl],
                    plane=f"{s_ax} = {meta[f'{s_ax}_c'][s0]:.2f} m  ")
    return dict(xf=meta['x_face'], yf=meta['y_face'], xlabel='x [m]',
                ylabel=('z [m]' if meta.get('geometry') == 'axisymmetric'
                        else 'y [m]'),
                sl=None, solid=meta['solid'], plane='')


class AnimView(QWidget):
    NO_RESULT = NO_RESULT

    def __init__(self, on_change=None, parent=None):
        super().__init__(parent)
        self._on_change = on_change or (lambda: None)
        self._ent = None
        self._title_extra = None
        self._playing = False
        self._geom = None
        self._levels = None
        self._clim = None
        self._scale_used = 'run'
        self._clipped = False
        self._clim_cache = {}       # (result, scale, clim) -> resolved
        self.image = None
        self.overlay = None
        self._show_mesh = False

        root = vbox(self)
        bar = hbox()
        self.play_btn = button('Play', 'play', 'primary', width=92,
                               height=32, on_click=self.toggle_play)
        bar.addWidget(self.play_btn)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1)
        self.slider.valueChanged.connect(self._slider_moved)
        bar.addWidget(self.slider, 1)
        # Playback speed: a recording is 60 to 150 frames, so at one
        # fixed rate a long one crawls and a short one is over before it
        # reads. The Tk app had no control at all.
        bar.addWidget(label('Speed', 'muted'))
        self.speed_sel = QComboBox()
        self.speed_sel.addItems(SPEED_LABELS)
        self.speed_sel.setCurrentText(SPEED_DEFAULT)
        self.speed_sel.setFixedWidth(72)
        self.speed_sel.setToolTip(
            'How fast the replay advances. It changes the playback only '
            '- the exported video keeps its own frame rate.')
        self.speed_sel.currentIndexChanged.connect(
            lambda *_: self._speed_changed())
        bar.addWidget(self.speed_sel)
        root.addLayout(bar)

        # the colour scale, for the replay and for the export
        bar2 = hbox()
        bar2.addWidget(label('Colours', 'muted'))
        self.scale_sel = QComboBox()
        self.scale_sel.addItems(list(ANIM_SCALE_LABELS.values()))
        self.scale_sel.setToolTip(
            'One range for the whole video keeps the colour bar '
            'meaningful from frame to frame; per-frame rescaling is the '
            'old behaviour; a manual range lets you compare two videos.')
        self.scale_sel.currentIndexChanged.connect(
            lambda *_: self._scale_changed())
        bar2.addWidget(self.scale_sel)
        self.min_box, self.max_box = QLineEdit(), QLineEdit()
        for box, cap in ((self.min_box, 'min [kPa]'),
                         (self.max_box, 'max [kPa]')):
            box.setFixedWidth(88)
            box.setPlaceholderText(cap)
            box.editingFinished.connect(self._scale_changed)
            bar2.addWidget(box)
        bar2.addStretch(1)
        root.addLayout(bar2)

        self.glw = pg.GraphicsLayoutWidget()
        self.plot = self.glw.addPlot(row=0, col=0)
        self.plot.setMenuEnabled(False)
        self.plot.hideButtons()
        root.addWidget(self.glw, 1)
        self.hint = label('', 'muted', wrap=True, align=Qt.AlignCenter)
        root.addWidget(self.hint)

        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)
        self._step = 1
        self._speed_changed()
        pg_plots.apply_theme(self.glw, [self.plot])
        theme.signals.changed.connect(self._retheme)
        self._set_manual_visible(False)
        self.placeholder(NO_RESULT)

    # ── the colour scale ─────────────────────────────────────────────────
    def scale(self):
        return anim_scale_from_label(self.scale_sel.currentText())

    def clim(self):
        """The typed range, or None when it is not usable. An unusable
        manual range is not an error here - `resolve_clim` falls back to
        one range for the whole video and says so."""
        try:
            return (float(self.min_box.text()), float(self.max_box.text()))
        except (TypeError, ValueError):
            return None

    def export_opts(self):
        """What the Animation export should use for its colours. The
        typed range travels only in manual mode, as the Setup form does
        it, so a leftover value in a hidden box changes nothing."""
        scale = self.scale()
        return dict(anim_scale=scale,
                    anim_clim=self.clim() if scale == 'manual' else None)

    def _set_manual_visible(self, on):
        for box in (self.min_box, self.max_box):
            box.setVisible(bool(on))

    def manual_visible(self):
        """Whether the two range boxes are part of the layout. Not
        `isVisible()`, which is False for the whole page while another
        sub-view is on top."""
        return not self.min_box.isHidden()

    def _scale_changed(self):
        self._set_manual_visible(self.scale() == 'manual')
        if self._ent is not None:
            self._resolve_clim()
            self.show_frame(self.slider.value())
        self._on_change()

    def _resolve_clim(self):
        """Fix the range once per result and scale, not per frame - that
        is the whole point of the 'run' scale.

        The answer is memoised because the whole-video range costs a
        pass over every recorded frame (measured: 2.6 s for 150 frames
        of 1000x1000), and toggling the selector back and forth must not
        pay for it twice."""
        frames = self._frames()
        if frames is None:
            self._clim, self._scale_used, self._clipped = None, 'run', False
            return
        # keyed on the scale only: the cache is emptied whenever the
        # result changes, so an id() that Python later reuses for a
        # different entry cannot hand back a stale range
        key = (self.scale(), self.clim())
        hit = self._clim_cache.get(key)
        if hit is None:
            solid = self._geom['solid'] if self._geom else None
            hit = anim_mod.resolve_clim(
                self._ent.result.meta, frames['pressures'], solid,
                self.scale(), self.clim())
            self._clim_cache[key] = hit
        self._clim, self._scale_used, self._clipped = hit

    # ── state ────────────────────────────────────────────────────────────
    def set_title_extra(self, text):
        self._title_extra = text or None

    def set_show_mesh(self, on):
        """The Fields tick-box drives the replay's overlay too. Only
        redraws when the flag actually changed - `set_result` takes it as
        an argument, so adopting a result costs one draw, not two."""
        on = bool(on)
        if on == self._show_mesh:
            return
        self._show_mesh = on
        if self._ent is not None:
            self.set_result(self._ent)

    def _frames(self):
        if self._ent is None:
            return None
        frames = self._ent.result.meta.get('frames')
        if not frames or not len(frames['pressures']):
            return None
        return frames

    def placeholder(self, text):
        """Blank the replay. Without this the previous result's frame
        stays on screen under a result that has no animation at all."""
        self.stop_play()
        if self.overlay is not None:
            self.overlay.remove()
        if self.image is not None:
            self.image.remove()
        self.image = self.overlay = None
        self._geom = self._levels = self._clim = None
        self._clipped = False
        self._clim_cache = {}
        self.plot.setTitle('', color=theme.cur('text'))
        self._title = ''
        self.glw.setVisible(False)
        self.hint.setText(text)
        self.hint.setVisible(True)
        self.play_btn.setEnabled(False)
        self.slider.blockSignals(True)
        self.slider.setRange(0, 1)
        self.slider.setValue(0)
        self.slider.blockSignals(False)

    def set_result(self, ent, show_mesh=None):
        if show_mesh is not None:
            self._show_mesh = bool(show_mesh)
        self._ent = ent
        self._clim_cache = {}         # a different run, a different range
        self.stop_play()
        if ent is None:
            self.placeholder(NO_RESULT)
            return
        if ent.dim == 1:
            self.placeholder(NO_1D)
            return
        frames = self._frames()
        if frames is None:
            self.placeholder(NO_FRAMES)
            return
        meta = ent.result.meta
        self._geom = plane_geometry(meta)
        # the run's own choice is the starting point, so a video
        # exported here matches the one the run wrote
        recorded = anim_scale_from_label(meta.get('anim_scale') or 'run')
        self.scale_sel.blockSignals(True)
        self.scale_sel.setCurrentText(ANIM_SCALE_LABELS[recorded])
        self.scale_sel.blockSignals(False)
        rec_clim = meta.get('anim_clim')
        if rec_clim:
            self.min_box.setText(f'{float(rec_clim[0]):g}')
            self.max_box.setText(f'{float(rec_clim[1]):g}')
        self._set_manual_visible(recorded == 'manual')

        if self.image is not None:
            self.image.remove()
        if self.overlay is not None:
            self.overlay.remove()
        g = self._geom
        self.image = pg_plots.ScalarImage(self.plot, g['xf'], g['yf'],
                                          g['solid'])
        self.image.set_labels(g['xlabel'], g['ylabel'])
        self.overlay = pg_plots.MeshOverlay(self.plot)
        # a dynamic-AMR run recorded a level map per frame, so the
        # overlay is rebuilt per frame instead of drawn once
        self._levels = frames.get('levels')
        if self._show_mesh and self._levels is None:
            try:
                self.overlay.set_segments(
                    plots.mesh_for(meta, g['xf'], g['yf'], g['sl']))
            except Exception:
                self.overlay.clear()
        self._resolve_clim()
        n = len(frames['pressures'])
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(1, n - 1))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.play_btn.setEnabled(True)
        self.hint.setVisible(False)
        self.glw.setVisible(True)
        self.show_frame(0)

    # ── frames ───────────────────────────────────────────────────────────
    def show_frame(self, k):
        frames = self._frames()
        if frames is None or self.image is None:
            return
        n = len(frames['pressures'])
        k = max(0, min(int(k), n - 1))
        self.image.set_field(frames['pressures'][k], clim=self._clim)
        bar = 'Overpressure [kPa]'
        if self._clim is None:
            bar += '  (rescaled per frame)'
        elif self._clipped:
            bar += pg_plots.CLIP_BAR_SUFFIX
        self.image.set_bar_label(bar)
        if self._levels is not None and self._show_mesh:
            g = self._geom
            lv = self._levels[min(k, len(self._levels) - 1)]
            try:
                self.overlay.set_segments(
                    plots.mesh_for(self._ent.result.meta, g['xf'], g['yf'],
                                   g['sl'], levels=lv))
            except Exception:
                self.overlay.clear()
        plane = self._geom['plane'] if self._geom else ''
        title = plots.titled(
            f"{plane}t = {frames['times'][k]*1e3:.3f} ms",
            self._title_extra)
        self.plot.setTitle(title, color=theme.cur('text'), size='10pt')
        self._title = title
        self._frame = k

    def frame(self):
        return getattr(self, '_frame', 0)

    def title(self):
        return getattr(self, '_title', '')

    def scale_used(self):
        """Which scale the replay actually applied - 'manual' falls back
        to 'run' when the typed range is unusable."""
        return self._scale_used

    def clipped(self):
        """Whether the whole-video range had its top clipped, which a
        recording that starts at t = 0 nearly always needs."""
        return self._clipped

    def _slider_moved(self, value):
        if not self._playing:
            self.show_frame(value)

    # ── playback ─────────────────────────────────────────────────────────
    def toggle_play(self):
        if self._playing:
            self.stop_play()
        else:
            self.start_play()

    def start_play(self):
        if self._frames() is None or self.image is None:
            return
        self._playing = True
        self.play_btn.setText('Pause')
        self.play_btn.setIcon(theme.icon('pause', 13, color='white'))
        self.play_btn._blastlab_icon = ('pause', 13, 'white')
        self.timer.start()

    def stop_play(self):
        self._playing = False
        self.timer.stop()
        self.play_btn.setText('Play')
        self.play_btn.setIcon(theme.icon('play', 13, color='white'))
        self.play_btn._blastlab_icon = ('play', 13, 'white')

    def playing(self):
        return self._playing

    # ── playback speed ───────────────────────────────────────────────────
    def speed(self):
        """The chosen multiple of the base rate."""
        return SPEED_FACTORS.get(self.speed_sel.currentText(), 1.0)

    def _speed_changed(self):
        """Apply the speed, live, without interrupting a playback.

        Above 1x the interval would fall under what Qt actually
        delivers, so the tick advances by more than one frame instead of
        being asked to fire faster than the screen refreshes.
        """
        factor = self.speed()
        want = TICK_MS / factor
        self._step = max(1, int(round(MIN_INTERVAL_MS / want))) \
            if want < MIN_INTERVAL_MS else 1
        self.timer.setInterval(max(MIN_INTERVAL_MS, int(round(want))))

    def frame_step(self):
        """How many frames one tick advances - 1 unless the speed asks
        for a rate faster than the timer can deliver."""
        return getattr(self, '_step', 1)

    def _tick(self):
        frames = self._frames()
        if frames is None or self.image is None:
            self.stop_play()
            return
        n = len(frames['pressures'])
        k = (self.slider.value() + self.frame_step()) % n
        # the slider is being driven, not read: its signal would call
        # show_frame a second time for the same tick
        self.slider.blockSignals(True)
        self.slider.setValue(k)
        self.slider.blockSignals(False)
        self.show_frame(k)

    def _retheme(self, _mode=None):
        pg_plots.apply_theme(self.glw, [self.plot])
        if self.overlay is not None:
            self.overlay.retheme()
        if self._ent is not None and self.image is not None:
            self.show_frame(self.slider.value())
