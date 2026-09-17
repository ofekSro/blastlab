"""Embedded 3D view of the Qt front-end (VIPER-style controls).

The rendering happens in the viewer child process; this widget owns one
of its surfaces: it embeds the child's render window through
`QWindow.fromWinId` + `createWindowContainer` (or lets it float), drives
the scene with `('ctrl', surface, name, ...)` messages and mirrors the
child's `status` replies into its controls. The control column is the
same three-tab stack the Tk panel had:

  Display : displayed field, auto or manual colour range, log contours,
            isosurface / surface loads / volume / mesh layers
  Planes  : six cross-section planes - enable, axis, position, opacity
  View    : axis-aligned camera presets + parallel projection

Frames reach the child through a shared-memory ring the solver thread
writes into (`viz3d.protocol`); the host only hands the child the
scene init and the ring's name.
"""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox,
                               QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QRadioButton, QSizePolicy,
                               QSlider, QStackedWidget, QVBoxLayout,
                               QWidget)

from ..viz3d import MISSING_MSG, pyvista_available
from ..viz3d.feed import Feed3D, N_PLANES
from ..viz3d.protocol import FrameLayout, SharedFrameRing
from ..viz3d.viewer import FIELDS
from . import theme
from .theme import GAP
from .widgets import ScrollColumn, Segmented, button, label

#: radio-button fields, straight from the viewer's FIELDS table
FIELD_LABELS = [(key, spec['label']) for key, spec in FIELDS.items()]
_PLANE_DEFAULTS = {1: ('y', True), 2: ('z', False)}


class _FloatWindow(QWidget):
    """The detached 3D window: it carries the host's window container, so
    the foreign render window is only ever re-parented inside this
    process. Closing it re-attaches instead of destroying anything."""

    def __init__(self, host):
        super().__init__(None)
        self._host = host
        self.setWindowTitle('blastlab - 3D view')
        self.resize(900, 700)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._closing = False

    def take(self, container):
        self._lay.addWidget(container)
        self.show()
        self.raise_()

    def release(self):
        """The host took its container back: hide (never destroy)."""
        self.hide()

    def forget(self):
        self._host = None

    def closeEvent(self, event):
        if self._host is not None and not self._closing:
            self._closing = True
            try:
                self._host.set_floating(False)
            finally:
                self._closing = False
            event.ignore()
            return
        event.accept()


def make_ring(feed, scene_info=None):
    """The shared-memory ring for a Feed3D's scene (levels block only
    for refined runs, whose frames may carry a level map)."""
    with_levels = feed.init.get('refine') is not None or bool(
        (scene_info or {}).get('refine') is not None)
    return SharedFrameRing(FrameLayout.from_init(feed.init,
                                                 with_levels=with_levels))


class View3DHost(QWidget):
    PLACEHOLDER = ('Run a 3D case - the live view attaches\n'
                   'automatically. Finished 3D results replay\n'
                   'here from the Results tab.')
    FLOATING = ('The 3D view is in its own window.\n'
                'Close it or click Re-attach to bring it back.')
    #: width of the control column, and the host width below which it
    #: folds away on its own
    CTL_W = 200
    COLLAPSE_W = 700

    scene_changed = Signal(bool)     # True: a scene is attached

    def __init__(self, link, surface='run', log_fn=print, parent=None):
        super().__init__(parent)
        self.link = link
        self.surface = surface
        self._log = log_fn
        self._has_scene = False
        self._feed = None
        self._ring = None
        self._hwnd = None
        self._foreign = None
        self._container = None
        self._float_win = None
        self._floating = False
        self._done = False
        self._n_frames = 0
        self._playing = False
        self._syncing = False
        self._ctl_collapsed = False
        self._ctl_user = False
        self._built = False
        self._status = {}
        self._build()
        self._built = True
        link.register(surface, self)
        theme.signals.changed.connect(self._retheme)

    # ── UI construction ──────────────────────────────────────────────────
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(GAP)

        ctl = QWidget()
        ctl.setFixedWidth(self.CTL_W)
        cl = QVBoxLayout(ctl)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(GAP)
        self._ctl = ctl
        root.addWidget(ctl)

        rail = QWidget()
        rail.setFixedWidth(22)
        rl = QVBoxLayout(rail)
        rl.setContentsMargins(0, 2, 0, 0)
        self._collapse_btn = button('', 'chevron_left', width=20, height=48,
                                    tooltip='Show / hide the 3D controls',
                                    on_click=self._collapse_clicked,
                                    icon_size=12)
        rl.addWidget(self._collapse_btn)
        rl.addStretch(1)
        root.addWidget(rail)

        # the view area: placeholder text | the embedded render window
        self._view_stack = QStackedWidget()
        self._view_stack.setSizePolicy(QSizePolicy.Expanding,
                                       QSizePolicy.Expanding)
        self._holder = QLabel(self.PLACEHOLDER)
        self._holder.setObjectName('view')
        self._holder.setAlignment(Qt.AlignCenter)
        self._holder.setWordWrap(True)
        self._view_stack.addWidget(self._holder)
        self._float_box = QWidget()
        fl = QVBoxLayout(self._float_box)
        fl.setAlignment(Qt.AlignCenter)
        self._float_lbl = QLabel(self.FLOATING)
        self._float_lbl.setObjectName('muted')
        self._float_lbl.setAlignment(Qt.AlignCenter)
        fl.addWidget(self._float_lbl)
        fl.addWidget(button('Re-attach', 'detach', width=120,
                            on_click=lambda: self.set_floating(False)),
                     alignment=Qt.AlignCenter)
        self._view_stack.addWidget(self._float_box)
        root.addWidget(self._view_stack, 1)

        # ── control tabs ───────────────────────────────────────────────
        self._tab_seg = Segmented(['Display', 'Planes', 'View'], height=28,
                                  small=True)
        self._tab_seg.changed.connect(self._tab_selected)
        cl.addWidget(self._tab_seg)
        self._tabs = QStackedWidget()
        cl.addWidget(self._tabs, 1)
        disp, planes, viewtab = ScrollColumn(), ScrollColumn(), ScrollColumn()
        for w in (disp, planes, viewtab):
            self._tabs.addWidget(w)
        self._tab_widgets = {'Display': disp, 'Planes': planes,
                             'View': viewtab}
        self._checks = {}

        def small_label(col, text):
            col.add(label(text, 'small'))

        def checkbox(col, text, key, default, fn):
            cb = QCheckBox(text)
            cb.setChecked(bool(default))
            cb.toggled.connect(lambda _c, k=key: fn(k))
            self._checks[key] = cb
            col.add(cb)
            return cb

        # Display tab
        small_label(disp, 'FIELD')
        self._field_group = QButtonGroup(self)
        self._field_btns = {}
        for key, text in FIELD_LABELS:
            rb = QRadioButton(text)
            self._field_group.addButton(rb)
            rb.toggled.connect(lambda on, k=key: on and self._field_changed(k))
            self._field_btns[key] = rb
            disp.add(rb)
        self._field_btns['p'].setChecked(True)
        self._field = 'p'
        small_label(disp, 'COLOUR SCALE')
        checkbox(disp, 'Auto colour scale', 'auto_scale', True,
                 lambda _k: self._auto_changed())
        self._vmin = QLineEdit('0')
        self._vmax = QLineEdit('500')
        for text, ent in (('Min', self._vmin), ('Max', self._vmax)):
            row = QHBoxLayout()
            row.setSpacing(4)
            lbl = label(text, 'small')
            lbl.setFixedWidth(28)
            row.addWidget(lbl)
            ent.setFont(theme.font('small'))
            ent.editingFinished.connect(self._clim_changed)
            row.addWidget(ent, 1)
            disp.add_layout(row)
        checkbox(disp, 'Log contours', 'log', False,
                 lambda _k: self._ctrl('log', self._checks['log'].isChecked()))
        small_label(disp, 'LAYERS')
        checkbox(disp, 'Shock isosurface', 'iso', True, self._toggle_layer)
        disp.add(label('Iso level (frac of peak)', 'small'))
        self._iso = QSlider(Qt.Horizontal)
        self._iso.setRange(2, 90)
        self._iso.setValue(10)
        self._iso.valueChanged.connect(
            lambda v: self._ctrl('iso_frac', v / 100.0))
        disp.add(self._iso)
        checkbox(disp, 'Surface loads', 'loads', True, self._toggle_layer)
        checkbox(disp, 'Volume render', 'volume', False, self._toggle_layer)
        checkbox(disp, 'Show mesh', 'mesh', False, self._toggle_layer)
        disp.add_stretch()

        # Planes tab (VIPER-style cross-sections)
        small_label(planes, 'CROSS-SECTION PLANES')
        self._planes = {}
        for k in range(1, N_PLANES + 1):
            key = f'plane{k}'
            axis0, on0 = _PLANE_DEFAULTS.get(k, ('x', False))
            row = QHBoxLayout()
            row.setSpacing(4)
            cb = QCheckBox('')
            cb.setChecked(on0)
            cb.toggled.connect(lambda _c, kk=key: self._toggle_layer(kk))
            self._checks[key] = cb
            axis = QComboBox()
            axis.addItems(['x', 'y', 'z'])
            axis.setCurrentText(axis0)
            axis.setFixedWidth(48)
            axis.setFont(theme.font('small'))
            axis.currentTextChanged.connect(
                lambda _t, kk=key: self._plane_changed(kk))
            pos = QSlider(Qt.Horizontal)
            pos.setRange(0, 1000)
            pos.setValue(500)
            pos.valueChanged.connect(lambda _v, kk=key: self._plane_changed(kk))
            op = QComboBox()
            op.addItems([str(x) for x in range(10, 101, 10)])
            op.setCurrentText('100')
            op.setFixedWidth(58)
            op.setFont(theme.font('small'))
            op.currentTextChanged.connect(
                lambda _t, kk=key: self._opacity_changed(kk))
            for w, stretch in ((cb, 0), (axis, 0), (pos, 1), (op, 0)):
                row.addWidget(w, stretch)
            planes.add_layout(row)
            self._planes[key] = (axis, pos, op)
        hint = label('Each row: on, axis, position, opacity %', 'small',
                     wrap=True)
        planes.add(hint)
        planes.add_stretch()

        # View tab
        small_label(viewtab, 'CAMERA PRESETS')
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, name in enumerate(('top', 'bottom', 'front',
                                  'back', 'left', 'right')):
            grid.addWidget(button(name.capitalize(), height=30,
                                  on_click=lambda n=name: self._ctrl('view', n)),
                           i // 2, i % 2)
        viewtab.add_layout(grid)
        checkbox(viewtab, 'Parallel projection', 'parallel', False,
                 lambda _k: self._ctrl('parallel',
                                       self._checks['parallel'].isChecked()))
        viewtab.add(button('Reset view', height=30,
                           on_click=lambda: self._ctrl('reset_view')))
        viewtab.add_stretch()
        self._tab_seg.set('Display')
        self._tabs.setCurrentWidget(disp)

        # ── always visible: follow / timeline / play / detach ──────────
        bottom = QVBoxLayout()
        bottom.setSpacing(4)
        self._follow = QCheckBox('Follow live')
        self._follow.setChecked(True)
        self._follow.toggled.connect(self._follow_changed)
        bottom.addWidget(self._follow)
        bottom.addWidget(label('Time', 'small'))
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 1)
        self.time_slider.setValue(0)
        self.time_slider.valueChanged.connect(self._time_moved)
        bottom.addWidget(self.time_slider)
        row = QHBoxLayout()
        self.play_btn = button('Play', 'play', 'primary', width=84, height=28,
                               on_click=self._toggle_play, icon_size=12)
        row.addWidget(self.play_btn)
        self.detach_btn = button('Detach', 'detach', width=90, height=28,
                                 tooltip='Pop the 3D view out into its own '
                                         'window (e.g. onto a second screen)',
                                 on_click=lambda: self.set_floating(True),
                                 icon_size=12)
        row.addWidget(self.detach_btn)
        row.addStretch(1)
        bottom.addLayout(row)
        bottom.addWidget(label('Drag: rotate   Right-drag: pan\n'
                               'Wheel: zoom', 'small'))
        cl.addLayout(bottom)

    def _tab_selected(self, value):
        self._tabs.setCurrentWidget(self._tab_widgets[value])

    def _retheme(self, _mode=None):
        pass

    # ── control-column collapse ──────────────────────────────────────────
    def _collapse_clicked(self):
        self._ctl_user = True       # a manual choice outranks the width
        self.set_controls_collapsed(not self._ctl_collapsed)

    def set_controls_collapsed(self, collapsed):
        collapsed = bool(collapsed)
        if collapsed == self._ctl_collapsed:
            return
        self._ctl_collapsed = collapsed
        self._ctl.setVisible(not collapsed)
        self._collapse_btn.setIcon(theme.icon(
            'chevron_right' if collapsed else 'chevron_left', 12))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._built and not self._ctl_user and event.size().width() > 1:
            self.set_controls_collapsed(event.size().width() < self.COLLAPSE_W)

    # ── window embedding ─────────────────────────────────────────────────
    # The container is built ONCE per native window and then only moved
    # between the host's stack and the detached window. Destroying a
    # window container that still holds a live foreign window crashes
    # (the wrapper re-parents a window Qt is told not to manipulate -
    # QWindow.fromWinId's own warning), so nothing here tears one down
    # while the viewer child is alive; `shutdown()` orders that.
    def on_window(self, hwnd):
        """The child reported its native window handle (once per window
        it creates)."""
        hwnd = int(hwnd)
        if hwnd == self._hwnd and self._container is not None:
            self._claim_if_visible()
            return
        self._hwnd = hwnd
        self._embed()
        self._claim_if_visible()

    def _container_id(self):
        return int(self._container.winId()) if self._container else None

    def _claim_if_visible(self):
        if self._container is None:
            return
        if self._floating or (self.isVisible() and self._has_scene):
            self.link.send(('claim', self.surface, self._container_id()))

    def _embed(self):
        """Wrap the child's HWND in a window container inside the host;
        on any failure the window is left to float on its own (the child
        still renders into it)."""
        if self._hwnd is None or self._container is not None:
            return self._container is not None
        try:
            win = QWindow.fromWinId(self._hwnd)
            if win is None:
                raise RuntimeError('fromWinId returned None')
            container = QWidget.createWindowContainer(win, self)
            container.setFocusPolicy(Qt.NoFocus)
            container.setMinimumSize(200, 150)
            self._foreign = win
            self._container = container
            self._host_container()
            return True
        except Exception as exc:
            self._log(f'  [3D view: embedding failed ({exc}); '
                      'the viewer window floats]')
            self._foreign = None
            self._container = None
            self._floating = True
            self._view_stack.setCurrentWidget(self._float_box)
            self.link.send(('detach', self.surface, True))
            return False

    def _host_container(self):
        """Move the container into the host's view stack."""
        if self._container is None:
            return
        self._view_stack.addWidget(self._container)
        self._view_stack.setCurrentWidget(self._container)

    def set_floating(self, floating):
        """Move the render window into its own top-level window, or bring
        it back into the host. The container travels with it, so the
        foreign window is only re-parented inside this process."""
        floating = bool(floating)
        if floating == self._floating:
            return
        if self._container is None:
            # nothing embedded (yet, or embedding failed): the child's
            # window is already on its own
            self._floating = floating
            self._view_stack.setCurrentWidget(
                self._float_box if floating else self._holder)
            self.link.send(('detach', self.surface, floating))
            self.detach_btn.setEnabled(not floating)
            return
        self._floating = floating
        if floating:
            if self._float_win is None:
                self._float_win = _FloatWindow(self)
            self._float_win.take(self._container)
            self._float_lbl.setText(self.FLOATING)
            self._view_stack.setCurrentWidget(self._float_box)
        else:
            self._host_container()
            if self._float_win is not None:
                self._float_win.release()
        self.detach_btn.setEnabled(not floating)
        self._claim_if_visible()

    def showEvent(self, event):
        super().showEvent(event)
        if self._has_scene and not self._floating:
            self._claim_if_visible()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._has_scene and not self._floating:
            self.link.send(('release', self.surface))

    def on_closed(self):
        """The child says its window was closed from the outside."""
        if self._floating:
            self._float_lbl.setText('The 3D window was closed.')

    def on_viewer_died(self):
        self._has_scene = False
        self._holder.setText('The 3D viewer process stopped.\n'
                             'Start a new run to restart it.')
        self._view_stack.setCurrentWidget(self._holder)
        self.scene_changed.emit(False)

    def shutdown(self):
        """Release the foreign window BEFORE the viewer child is asked to
        quit, and drop the container while its window is still alive but
        no longer ours: the reverse order leaves Qt holding a dangling
        HWND at teardown."""
        self._has_scene = False
        self.close_ring()
        if self._float_win is not None:
            # nothing may outlive the main window
            self._host_container()
            self._float_win.forget()
            self._float_win.close()
            self._float_win = None
            self._floating = False
        container, self._container = self._container, None
        self._foreign = None
        if container is not None:
            try:
                # ONE re-parent, and never of the foreign window itself:
                # dropping the container hands the child's window back
                # (fromWinId's wrapper supports exactly this). Orphaning
                # the wrapper first and then moving the container is an
                # access violation, and so is letting Qt do it at
                # teardown once the child process is gone.
                self._view_stack.removeWidget(container)
                container.setParent(None)
                container.deleteLater()
                app = QApplication.instance()
                if app is not None:
                    app.sendPostedEvents(None, QEvent.DeferredDelete)
            except Exception:
                pass

    def on_error(self, text):
        self._log(f'  [3D view: {text}]')

    def on_screenshot(self, path):
        self._log(f'  [3D view screenshot: {path}]')

    def on_scene_ready(self):
        pass

    # ── scene lifecycle ──────────────────────────────────────────────────
    @property
    def has_scene(self):
        return self._has_scene

    def prepare_live(self, scene_info):
        """New live 3D run from a scene_info dict: build the feed and its
        ring, attach; returns (feed, ring) or None."""
        try:
            feed = Feed3D(scene_info)
            ring = make_ring(feed, scene_info)
        except Exception as exc:
            self._log(f'  [3D view failed: {exc}]')
            return None
        if not self.adopt_feed(feed, ring):
            ring.close(unlink=True)
            return None
        return feed, ring

    def adopt_feed(self, feed, ring):
        """Attach to a Feed3D + ring built elsewhere (auto-attach at run
        start: the solver thread builds both before the first frame)."""
        return self._send_scene(feed.init, ring)

    def _send_scene(self, init, ring, title=None):
        if not pyvista_available():
            self._log(MISSING_MSG)
            return False
        if not self.link.ensure_started():
            self._log(f'  [{MISSING_MSG}]')
            return False
        if self._ring is not None and self._ring is not ring:
            self._ring.close(unlink=True)
        self._ring = ring
        self._done = False
        self._n_frames = 0
        self._status = {}
        self._set_playing(False)
        self._has_scene = True
        self.link.send(('scene', self.surface, dict(
            init=init, shm=ring.name, layout=ring.layout,
            n_planes=N_PLANES, embedded=True,
            title=title or 'blastlab - 3D view')))
        self._apply_all_controls()
        self._set_time_range(0)
        if self.isVisible() and not self._floating:
            self.link.send(('claim', self.surface, self._container_id()))
        if self._container is None and self._hwnd is None \
                and not self._floating:
            self._holder.setText('starting the 3D view…')
        self.scene_changed.emit(True)
        return True

    def on_done(self, reason):
        if not self._has_scene:
            return
        self._done = True
        self.link.send(('done', self.surface, str(reason)))
        self._follow.blockSignals(True)
        self._follow.setChecked(False)
        self._follow.blockSignals(False)

    def reset(self):
        """Drop the current scene and go back to the placeholder, so a new
        run does not start against the previous run's picture."""
        if self._has_scene:
            self.link.send(('release', self.surface))
        self._has_scene = False
        self._done = False
        self._set_playing(False)
        self._holder.setText(self.PLACEHOLDER)
        if not self._floating:
            self._view_stack.setCurrentWidget(self._holder)
        self._set_time_range(0)
        self.scene_changed.emit(False)

    def close_ring(self):
        if self._ring is not None:
            self._ring.close(unlink=True)
            self._ring = None

    # ── control callbacks ────────────────────────────────────────────────
    def _ctrl(self, name, *args):
        if self._has_scene:
            self.link.send(('ctrl', self.surface, name, *args))

    def _toggle_layer(self, key):
        self._ctrl('layer', key, self._checks[key].isChecked())

    def _field_changed(self, key):
        self._field = key
        self._ctrl('field', key)

    def _plane_changed(self, key):
        axis, pos, _op = self._planes[key]
        # 0.0 / 1.0 sit exactly on a domain face: the cut is empty and the
        # plane silently disappears, so keep it just inside
        frac = min(max(pos.value() / 1000.0, 0.001), 0.999)
        self._ctrl('plane', key, axis.currentText(), frac)

    def _opacity_changed(self, key):
        _axis, _pos, op = self._planes[key]
        try:
            self._ctrl('plane_opacity', key, float(op.currentText()) / 100.0)
        except ValueError:
            pass

    def _auto_changed(self):
        on = self._checks['auto_scale'].isChecked()
        self._ctrl('auto_scale', on)
        if not on:
            self._clim_changed()

    def _clim_changed(self):
        """Manual Min/Max entries applied (turns auto scale off)."""
        try:
            vmin = float(self._vmin.text())
            vmax = float(self._vmax.text())
        except ValueError:
            return
        if vmax <= vmin:
            return
        if self._checks['auto_scale'].isChecked():
            self._checks['auto_scale'].blockSignals(True)
            self._checks['auto_scale'].setChecked(False)
            self._checks['auto_scale'].blockSignals(False)
        self._ctrl('clim', vmin, vmax)

    def _follow_changed(self, on):
        if self._syncing:
            return
        self._ctrl('follow', bool(on))

    def _time_moved(self, v):
        if self._syncing or not self._has_scene:
            return
        if self._follow.isChecked():
            self._syncing = True
            self._follow.setChecked(False)
            self._syncing = False
            self._ctrl('follow', False)
        self._ctrl('show_frame', int(v))

    def _toggle_play(self):
        if not self._has_scene or self._n_frames < 2:
            return
        self._set_playing(not self._playing)
        if self._playing and self._follow.isChecked():
            self._syncing = True
            self._follow.setChecked(False)
            self._syncing = False
            self._ctrl('follow', False)
        self._ctrl('play', self._playing)

    def _set_playing(self, playing):
        self._playing = bool(playing)
        self.play_btn.setText('Pause' if self._playing else 'Play')
        self.play_btn.setIcon(theme.icon('pause' if self._playing else 'play',
                                         12, color='white'))

    def _apply_all_controls(self):
        """Replay the control state into a freshly built scene."""
        for key in (['iso', 'loads', 'volume', 'mesh']
                    + [f'plane{k}' for k in range(1, N_PLANES + 1)]):
            self._ctrl('layer', key, self._checks[key].isChecked())
        self._ctrl('field', self._field)
        self._ctrl('iso_frac', self._iso.value() / 100.0)
        self._ctrl('auto_scale', self._checks['auto_scale'].isChecked())
        self._ctrl('log', self._checks['log'].isChecked())
        if not self._checks['auto_scale'].isChecked():
            self._clim_changed()
        self._ctrl('follow', self._follow.isChecked())
        self._ctrl('parallel', self._checks['parallel'].isChecked())
        for k in range(1, N_PLANES + 1):
            self._plane_changed(f'plane{k}')
            self._opacity_changed(f'plane{k}')

    # ── control <-> scene sync (status replies) ──────────────────────────
    def _set_time_range(self, n):
        self._syncing = True
        try:
            self.time_slider.setRange(0, max(1, n - 1))
        finally:
            self._syncing = False

    def on_status(self, st):
        self._status = dict(st)
        n = int(st.get('n', 0))
        if n != self._n_frames:
            self._n_frames = n
            self._set_time_range(n)
        if not self.time_slider.isSliderDown():
            self._syncing = True
            try:
                self.time_slider.setValue(int(st.get('index', 0)))
            finally:
                self._syncing = False
        # offer exactly the fields this result carries: a greyed radio
        # read as a control the user had failed to unlock (QA-17)
        have = set(st.get('have') or []) | {'p'}
        for key, _text in FIELD_LABELS:
            self._field_btns[key].setVisible(key in have)
        if self._field not in have:
            self._field_btns['p'].setChecked(True)
        if self._checks['auto_scale'].isChecked():
            for ent, key in ((self._vmin, 'vmin'), (self._vmax, 'vmax')):
                if not ent.hasFocus() and key in st:
                    ent.setText(f'{float(st[key]):g}')
        playing = bool(st.get('playing', False))
        if playing != self._playing:
            self._set_playing(playing)
        follow = bool(st.get('follow', self._follow.isChecked()))
        if follow != self._follow.isChecked():
            self._syncing = True
            self._follow.setChecked(follow)
            self._syncing = False
        if st.get('done'):
            self._done = True

    def status(self):
        return dict(self._status)
