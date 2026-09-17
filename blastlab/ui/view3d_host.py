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

import sys
import time

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
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

# ── making the render window a real child of its card ────────────────────
# Windows only; everywhere else the Qt window container is the only route.
_GWL_STYLE, _GWL_EXSTYLE = -16, -20
_WS_CHILD, _WS_POPUP = 0x40000000, 0x80000000
#: caption, sizing border, system menu and the two buttons
_WS_FRAME = 0x00C00000 | 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000
#: modal frame, window edge, client edge, app window, static edge
_WS_EX_FRAME = 0x00000001 | 0x00000100 | 0x00000200 | 0x00040000 | 0x00020000
_SW_HIDE, _SW_SHOWNA = 0, 8
#: SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER
_SWP_PIN = 0x0004 | 0x0010 | 0x0200
_SWP_FRAMECHANGED = 0x0020


def _user32():
    """The user32 handle, or None off Windows."""
    if not sys.platform.startswith('win'):
        return None
    try:
        import ctypes
        return ctypes.windll.user32
    except Exception:
        return None


def _get_style(hwnd, which):
    import ctypes
    u32 = ctypes.windll.user32
    fn = getattr(u32, 'GetWindowLongPtrW', None) or u32.GetWindowLongW
    fn.restype = ctypes.c_ssize_t
    fn.argtypes = [ctypes.c_void_p, ctypes.c_int]
    return int(fn(ctypes.c_void_p(int(hwnd)), which))


def _set_style(hwnd, which, value):
    import ctypes
    u32 = ctypes.windll.user32
    fn = getattr(u32, 'SetWindowLongPtrW', None) or u32.SetWindowLongW
    fn.restype = ctypes.c_ssize_t
    fn.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    return int(fn(ctypes.c_void_p(int(hwnd)), which, value))


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
        self._feed_timer = None       # results replay, one snapshot/tick
        self._feed_state = None
        # the container the child was last told to use, so a claim is
        # sent once per container and not once per edited case
        self._claimed = None
        self._claimed_ok = False
        self._sync_timer = None       # keeps the embedded window in place
        self._syncing = False
        self._burst_until = 0.0
        self._native = False          # the card adopted the window itself
        self._style = None            # the window's own frame, to restore
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
        # A palette change re-runs the whole layout, which moves the
        # container inside the top-level and breaks the embedded window's
        # alignment (measured: 751 px left, 121 px up). Nothing here has
        # to be redrawn - pyqtgraph and the icons are elsewhere - but the
        # geometry does have to be re-asserted once the layout settles.
        self._sync_soon()

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
        self._sync_soon()

    # ── keeping the embedded window where it belongs ─────────────────────
    #
    # `createWindowContainer` does NOT make the foreign window a child of
    # the container. Measured with Win32 GetParent: it re-parents it to
    # the TOP-LEVEL window, and Qt then keeps its geometry in step BY
    # HAND. That bookkeeping breaks, and stays broken, under several
    # unrelated operations - each measured on a stand-in foreign window
    # inside the real SetupPanel:
    #
    #   hiding and showing the tab      258 px left, 48 px up
    #   resizing the window             258 px left, 48 px up
    #   switching the dimension away    878 px left, 121 px up
    #   switching to light mode         751 px left, 121 px up
    #
    # Every one of them lands the render window in the corner of the
    # client area, over the sidebar and the form. Enumerating the
    # triggers failed three times, so the geometry is now asserted from
    # STATE rather than from events, in two layers:
    #
    # 1. The QWindow's own `xChanged`/`yChanged`/`widthChanged`/
    #    `heightChanged` signals. This is the move itself, not a guess at
    #    what caused it: the instant Qt puts the window somewhere else we
    #    put it back, inside the same frame. Measured, this is what keeps
    #    the correction invisible - the timer alone left the window
    #    visibly out of place for 53 to 157 ms.
    # 2. A timer as the backstop, for a break that arrives without any
    #    signal at all. Switching the theme is one: the window is not
    #    moved, the CONTAINER is, because the palette change re-runs the
    #    layout - and re-asserting the geometry in that same turn writes
    #    a rect the unfinished layout has not caught up with yet. So the
    #    timer runs fast for a short while after every disturbance, and
    #    idles the rest of the time.
    #
    # The event-driven calls stay too, since they cost nothing.
    SYNC_FAST_MS = 16      # one frame, while something is moving
    SYNC_IDLE_MS = 250     # a cheap heartbeat the rest of the time
    SYNC_BURST_MS = 600    # how long a disturbance keeps us fast

    def _sync_soon(self):
        """Now, again once Qt has had its turn, and at frame rate for a
        moment after.

        Synchronous alone is not enough: inside `resizeEvent` Qt
        re-applies its own wrong position AFTER us, and a sync there
        still left the window 258 px out. The deferred pass runs last,
        and the burst covers a layout that is still settling.
        """
        self.sync_foreign_geometry()
        QTimer.singleShot(0, self.sync_foreign_geometry)
        self._sync_burst()

    def _sync_burst(self):
        """Watch at frame rate for the next SYNC_BURST_MS."""
        self._burst_until = time.monotonic() + self.SYNC_BURST_MS / 1000.0
        if self._sync_timer is not None:
            self._sync_timer.setInterval(self.SYNC_FAST_MS)

    def _expected_rect(self):
        """Where the render window should be, in its Windows parent's own
        client coordinates.

        Which parent that is depends on how it was embedded, and the
        difference is the whole point of the native path: a real child of
        its card belongs at (0, 0) of the card, while Qt's container
        re-parents to the top-level and so has to be told where the card
        happens to sit inside it.
        """
        container = self._container
        if container is None or container.width() < 2:
            return None
        if self._native:
            return QRect(QPoint(0, 0), container.size())
        top = container.window()
        if top is None:
            return None
        return QRect(container.mapTo(top, QPoint(0, 0)),
                     container.size())

    def _real_offset(self):
        """How far the window REALLY is from its container, asked of the
        window manager rather than of Qt.

        This distinction is the whole difference between a fix and a
        near-miss. Comparing `fw.geometry()` with the container trusts
        Qt's bookkeeping - which is the thing that breaks. Minimising and
        restoring the window is the case that proves it: the window comes
        back 915 px left and 137 px up while Qt still believes it never
        moved, so an `!= want` test skips the correction and the window
        stays in the corner indefinitely.

        None on any platform without the call, or when the answer cannot
        be trusted; the caller then falls back to Qt's own view.
        """
        rect = self._real_rect()
        container = self._container
        if rect is None or container is None:
            return None
        here = container.mapToGlobal(QPoint(0, 0))
        return (rect[0] - here.x(), rect[1] - here.y())

    def _real_rect(self):
        """The window's screen rectangle as the window manager has it."""
        if not sys.platform.startswith('win') or not self._hwnd:
            return None
        try:
            import ctypes
            buf = ctypes.create_string_buffer(16)    # RECT: 4 x LONG
            if not ctypes.windll.user32.GetWindowRect(
                    ctypes.c_void_p(int(self._hwnd)), buf):
                return None
            left, top, right, bottom = ctypes.cast(
                buf, ctypes.POINTER(ctypes.c_long))[0:4]
            return (left, top, right - left, bottom - top)
        except Exception:
            return None

    def _real_size(self):
        rect = self._real_rect()
        return None if rect is None else (rect[2], rect[3])

    def sync_foreign_geometry(self):
        """Put the embedded render window back over its container.

        Qt sets the geometry, so its own bookkeeping stays in step and it
        has nothing stale to re-apply later; Win32 then puts the window
        there, because `setGeometry` to a rect Qt already believes in is
        a no-op inside Qt and would leave the window where it is.

        Re-entrant by construction: moving the window fires the very
        signals that call this, hence the guard.
        """
        if self._syncing:
            return
        fw = self._foreign
        want = self._expected_rect()
        if want is None or (fw is None and not self._native):
            return
        real = self._real_offset()
        if real is not None:
            if max(abs(real[0]), abs(real[1])) <= 1 \
                    and self._real_size() == (want.width(), want.height()):
                return
        elif fw is not None and fw.geometry() == want:
            return
        self._syncing = True
        try:
            if fw is not None:
                fw.setGeometry(want)
            self._pin_foreign(want)
        except Exception:
            pass
        finally:
            self._syncing = False

    #: SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER
    _SWP_FLAGS = 0x0004 | 0x0010 | 0x0200

    def _pin_foreign(self, want):
        """Move the window with the window manager itself.

        `want` is in the client coordinates of whichever window is the
        render window's Windows parent, which is what SetWindowPos wants
        for a child window - the card on the native path, the top-level
        under Qt's container.
        """
        if not sys.platform.startswith('win') or not self._hwnd:
            return
        try:
            import ctypes
            ctypes.windll.user32.SetWindowPos(
                ctypes.c_void_p(int(self._hwnd)), None,
                want.x(), want.y(), want.width(), want.height(),
                self._SWP_FLAGS)
        except Exception:
            pass

    def _watch_foreign_moves(self):
        """Correct the move itself, in the frame it happens."""
        fw = self._foreign
        if fw is None:
            return
        for sig in (fw.xChanged, fw.yChanged,
                    fw.widthChanged, fw.heightChanged):
            try:
                sig.connect(self._foreign_moved)
            except Exception:
                pass

    def _foreign_moved(self, _value):
        self.sync_foreign_geometry()

    def _sync_tick(self):
        """A mismatch means something is moving, so keep looking at frame
        rate; quiet means fall back to the heartbeat."""
        fw, want = self._foreign, self._expected_rect()
        if fw is not None and want is not None and fw.geometry() != want:
            self.sync_foreign_geometry()
            self._sync_burst()
            return
        if (self._sync_timer is not None
                and time.monotonic() > self._burst_until
                and self._sync_timer.interval() != self.SYNC_IDLE_MS):
            self._sync_timer.setInterval(self.SYNC_IDLE_MS)

    def _start_sync_watch(self):
        if self._sync_timer is None:
            self._sync_timer = QTimer(self)
            self._sync_timer.setInterval(self.SYNC_FAST_MS)
            self._sync_timer.timeout.connect(self._sync_tick)
        if not self._sync_timer.isActive():
            self._sync_timer.start()
        self._sync_burst()

    def _stop_sync_watch(self):
        if self._sync_timer is not None:
            self._sync_timer.stop()

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

    def _claim_if_visible(self, force=False):
        """Ask the child to show its window - but only when something
        actually changed.

        A `claim` makes the child call `show()` and `raise_()` on a
        widget it still believes is top-level (Qt.Window, no parent);
        only the SetParent that createWindowContainer did in this
        process makes it a child. So a redundant claim hands the window
        back to the child's own geometry and it reappears at the
        top-left of the application, over the sidebar and the form.
        `show_geometry` sent one on EVERY edited case, throttled to
        500 ms, which is how the Setup preview jumped away while simply
        typing in a 3D field.

        Claiming once per container is enough: the first handshake
        (before an HWND exists), again when `_embed` puts the window in
        a container, and after a detach. `force` covers that last one,
        where the container object is unchanged but the child has to be
        told anyway.
        """
        if not self._has_scene or self._floating:
            return
        if not self.isVisible():
            return
        target = self._container_id()
        if not force and self._claimed_ok and target == self._claimed:
            return
        self.link.send(('claim', self.surface, target))
        self._claimed, self._claimed_ok = target, True

    def _embed_native(self):
        """Make the render window a real child window of its card.

        This is the difference between correcting where the window is and
        it never being wrong. `createWindowContainer` re-parents the
        foreign window to the TOP-LEVEL and then tracks its position by
        hand - and it is not the only one doing so, because over in the
        viewer the same widget is a `Qt.Window` with no parent, so that
        process's Qt believes it is top-level too. Either side can
        re-apply a stale position at any moment, and the render window
        lands in the corner of the client area, over the sidebar and the
        form. Correcting it afterwards always costs a visible frame; the
        owner watched it happen.

        A real child window removes the failure rather than repairing
        it. Windows clips the window to the card and carries it when the
        card moves, and - the point - its coordinates become RELATIVE to
        the card, so the (0, 0) that both sides fall back to is exactly
        where it belongs.

        False if the platform has no such call, and the Qt window
        container is then used instead.
        """
        u32 = _user32()
        if u32 is None or not self._hwnd:
            return False
        mount = None
        try:
            import ctypes
            hwnd = int(self._hwnd)
            # into the stack BEFORE it gets a native handle: re-parenting
            # a native widget recreates its HWND, which would orphan the
            # render window we are about to hang off it
            mount = QWidget()
            mount.setFocusPolicy(Qt.NoFocus)
            mount.setMinimumSize(200, 150)
            self._view_stack.addWidget(mount)
            self._view_stack.setCurrentWidget(mount)
            mount.setAttribute(Qt.WA_NativeWindow, True)
            parent_id = int(mount.winId())
            if not parent_id:
                raise RuntimeError('the card has no native handle')

            self._style = (_get_style(hwnd, _GWL_STYLE),
                           _get_style(hwnd, _GWL_EXSTYLE))
            # hidden while it is re-parented and re-framed, so none of it
            # is ever on screen in the wrong place
            u32.ShowWindow(ctypes.c_void_p(hwnd), _SW_HIDE)
            _set_style(hwnd, _GWL_STYLE,
                       (self._style[0] & ~(_WS_POPUP | _WS_FRAME))
                       | _WS_CHILD)
            _set_style(hwnd, _GWL_EXSTYLE, self._style[1] & ~_WS_EX_FRAME)
            if not u32.SetParent(ctypes.c_void_p(hwnd),
                                 ctypes.c_void_p(parent_id)):
                raise ctypes.WinError(ctypes.get_last_error())
            self._container = mount
            self._native = True
            mount.installEventFilter(self)      # WinIdChange insurance
            u32.SetWindowPos(ctypes.c_void_p(hwnd), None, 0, 0,
                             max(1, mount.width()), max(1, mount.height()),
                             _SWP_PIN | _SWP_FRAMECHANGED)
            u32.ShowWindow(ctypes.c_void_p(hwnd), _SW_SHOWNA)
            self._start_sync_watch()
            return True
        except Exception as exc:
            self._log(f'  [3D view: the card could not adopt the render '
                      f'window ({exc}); falling back to Qt]')
            self._native = False
            self._container = None
            if mount is not None:
                try:
                    self._view_stack.removeWidget(mount)
                    mount.setParent(None)
                    mount.deleteLater()
                except Exception:
                    pass
            return False

    def _release_native(self):
        """Hand the window back to the viewer as a top-level again."""
        u32 = _user32()
        if u32 is None or not self._native or not self._hwnd:
            return
        try:
            import ctypes
            hwnd = int(self._hwnd)
            u32.ShowWindow(ctypes.c_void_p(hwnd), _SW_HIDE)
            u32.SetParent(ctypes.c_void_p(hwnd), None)
            if self._style is not None:
                _set_style(hwnd, _GWL_STYLE, self._style[0])
                _set_style(hwnd, _GWL_EXSTYLE, self._style[1])
                u32.SetWindowPos(ctypes.c_void_p(hwnd), None, 0, 0, 0, 0,
                                 _SWP_PIN | _SWP_FRAMECHANGED | 0x0001
                                 | 0x0002)      # SWP_NOSIZE | SWP_NOMOVE
        except Exception:
            pass
        self._native = False

    def eventFilter(self, obj, event):
        # Qt destroys and recreates a native widget's HWND when it is
        # re-parented or re-created; the render window hangs off that
        # handle, so it has to be re-adopted.
        if (self._native and obj is self._container
                and event.type() == QEvent.WinIdChange):
            u32 = _user32()
            if u32 is not None and self._hwnd:
                try:
                    import ctypes
                    u32.SetParent(ctypes.c_void_p(int(self._hwnd)),
                                  ctypes.c_void_p(int(obj.winId())))
                    self.sync_foreign_geometry()
                except Exception:
                    pass
        return super().eventFilter(obj, event)

    def _embed(self):
        """Give the child's HWND a home inside the host: a real child
        window of its card where the platform allows it, otherwise Qt's
        window container. On any failure the window is left to float on
        its own (the child still renders into it)."""
        if self._hwnd is None or self._container is not None:
            return self._container is not None
        if self._embed_native():
            self._sync_soon()
            return True
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
            self._watch_foreign_moves()
            self._start_sync_watch()
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
        if not self._native:
            self._view_stack.addWidget(self._container)
        # a native mount is never re-parented: its HWND is the render
        # window's parent, and Qt would destroy and recreate it
        self._view_stack.setCurrentWidget(self._container)
        self._sync_soon()

    def _drop_native_mount(self):
        """Hand the window back and take the card's mount down with it."""
        self._release_native()
        mount, self._container = self._container, None
        if mount is None:
            return
        try:
            mount.removeEventFilter(self)
            self._view_stack.removeWidget(mount)
            mount.setParent(None)
            mount.deleteLater()
        except Exception:
            pass

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
        if self._native:
            # No _FloatWindow here, and none wanted: detaching a real
            # child window means handing it back to the viewer, which
            # owns it as a proper framed top-level. Coming back, the
            # child re-reports its handle and `on_window` re-adopts it.
            self._floating = floating
            self._drop_native_mount()
            self._float_lbl.setText(self.FLOATING)
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
        # the container object is the same one, but the child still has
        # to be told after a detach, so this claim is forced
        self._claim_if_visible(force=True)

    # A tab switch must NOT ask the child to hide and show its window.
    #
    # The child's surface window is a QWidget with Qt.Window flags and no
    # parent, so over there Qt still believes it is top-level - the only
    # thing that made it a child is the SetParent that
    # createWindowContainer did in THIS process. `release` makes the
    # child call hide(), `claim` makes it call show() + raise_(), and
    # that pair hands the window back to the child's own top-level
    # geometry: leaving Setup for Run and returning put the 3D view at
    # the top-left of the application, over the sidebar and the form.
    #
    # An embedded window needs none of it. A window container's contents
    # follow the container's visibility, so hiding the tab hides the
    # render window with it. Only an UNembedded surface - the first
    # handshake before on_window arrives, or a failed embed - still has
    # to be told.
    def showEvent(self, event):
        super().showEvent(event)
        # a no-op once embedded: the target container has not changed
        self._claim_if_visible()
        # the container's final geometry is not known yet at show time
        self._sync_soon()

    def hideEvent(self, event):
        super().hideEvent(event)
        if not self._has_scene or self._floating:
            return
        if self._container is not None:
            return          # the container's contents hide with it
        self.link.send(('release', self.surface))
        self._claimed_ok = False    # so the next show claims again

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
        self._stop_sync_watch()
        self.cancel_feed()
        self.close_ring()
        if self._native:
            # the window goes back to the viewer BEFORE the card's mount
            # is destroyed: Windows destroys a parent's children with it,
            # and that would take the child process's render window
            self._drop_native_mount()
            return
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
        self._claim_if_visible()
        if self._container is None and self._hwnd is None \
                and not self._floating:
            self._holder.setText('starting the 3D view…')
        self.scene_changed.emit(True)
        return True

    def show_geometry(self, geo):
        """Static scenery only - the Setup tab's model preview. No ring
        and no frames: the child builds a GeometryScene and re-renders it
        for each edited case, keeping the camera while the domain extents
        are unchanged."""
        if not pyvista_available():
            self._log(MISSING_MSG)
            return False
        if not self.link.ensure_started():
            return False
        first = not self._has_scene
        self._has_scene = True
        self.link.send(('geo', self.surface, geo))
        # once per container, NOT once per edited case
        self._claim_if_visible()
        if first:
            if self._container is None and self._hwnd is None \
                    and not self._floating:
                self._holder.setText('starting the 3D preview…')
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
        self.cancel_feed()
        if self._has_scene:
            self.link.send(('release', self.surface))
        self._has_scene = False
        self._claimed_ok = False
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

    # ── replay of a finished result (the Results tab's surface) ──────────
    def feed_result(self, result):
        """Play a finished 3D Result's snapshots into the viewer.

        One snapshot per timer tick, not a loop: a 20-snapshot result
        rebuilt every layer inside a single callback and froze the window
        for seconds. The HUD counts them in while they stream, and
        starting a new result cancels a feed still in flight."""
        from ..viz3d.client import scene_from_meta
        self.cancel_feed()
        try:
            feed = Feed3D(scene_from_meta(result.meta))
            ring = make_ring(feed, None)
        except Exception as exc:
            self._log(f'  [3D view failed: {exc}]')
            return False
        if not self.adopt_feed(feed, ring):
            ring.close(unlink=True)
            return False
        # the whole-run maps live in meta, not per snapshot. Without them
        # the viewer greys out Peak overpressure / Net ovp impulse even
        # though the Fields list offers exactly those maps for the same
        # run; they are constant over the playback, as in Fields where
        # they are labelled "whole run".
        whole = {}
        for key, mkey in (('p_peak', 'p_peak'), ('imp', 'impulse')):
            arr = result.meta.get(mkey)
            if arr is not None:
                whole[key] = arr
        self._feed_state = dict(i=0, names=list(result.snapshots.keys()),
                                feed=feed, whole=whole, result=result)
        if self._feed_timer is None:
            self._feed_timer = QTimer(self)
            self._feed_timer.setInterval(1)
            self._feed_timer.timeout.connect(self._feed_step)
        self._feed_timer.start()
        return True

    def cancel_feed(self):
        if self._feed_timer is not None:
            self._feed_timer.stop()
        self._feed_state = None

    def feeding(self):
        return self._feed_state is not None

    def _feed_step(self):
        st = self._feed_state
        if st is None or self._ring is None or not st['names']:
            self.cancel_feed()
            return
        i, names = st['i'], st['names']
        snap = st['result'].snapshots[names[i]]
        payload = st['feed'].make_payload(dict(p=snap['p'], **st['whole']))
        rho3 = snap.get('rho3')       # stored pre-decimated, same stride
        if rho3 is not None and rho3.shape == payload['p'].shape:
            payload['rho'] = rho3
        last = i == len(names) - 1
        self.link.send(('hud', self.surface,
                        '' if last else
                        f'loading {i + 1}/{len(names)} snapshots'))
        try:
            self._ring.write(float(snap.get('t', 0.0)), payload, last)
        except Exception as exc:
            self._log(f'  [3D replay failed: {exc}]')
            self.cancel_feed()
            return
        self._n_frames = i + 1
        self._set_time_range(self._n_frames)
        st['i'] = i + 1
        if last:
            self.cancel_feed()
            self.on_done(getattr(st['result'], 'stop_reason', ''))

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
