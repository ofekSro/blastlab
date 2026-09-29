"""The Setup tab's live model previews.

1D and 2D are matplotlib drawings (`output/preview_draw.py`, shared with
the Tk front-end) on an embedded canvas. 3D is the viewer child's
`setup` surface: `Preview3DBridge` keeps the leading-edge throttle and
the visual-dependency key the Tk panel had, so a burst of keystrokes
rebuilds the scene once instead of per character.
"""

import time

from PySide6.QtCore import QTimer
from matplotlib.figure import Figure

from ..output import preview_draw
from ..viz3d import pyvista_available
from ..viz3d.geometry import case_geometry
from . import theme
from .mpl_canvas import MplCanvas


def _pal():
    # the palette's `accent` is what preview_draw paints the gauges in;
    # the redesign draws gauges in `gauge` cyan everywhere (plan §2.1,
    # GUI-5b) - told apart from the orange charge by hue and lightness
    return preview_draw.palette(dark=theme.mode() == 'dark',
                                accent=theme.cur('gauge'),
                                muted=theme.cur('muted'))


class _MplPreview(MplCanvas):
    """One reused figure and axis; `show_case` redraws it in place."""

    def __init__(self, draw, parent=None):
        super().__init__(toolbar=False, parent=parent)
        self._draw = draw
        fig = Figure(figsize=(5, 5))
        self._ax = fig.add_subplot()
        self.set_figure(fig)
        # re-fit the margins when the canvas changes size, not only once
        # per case: the Setup centre (GUI-5b) resizes the canvas under a
        # drawn case, and the one-off tight_layout then cut the axis
        # labels off (measured at 1100 x 720: 'r [m]' half below it)
        fig.canvas.mpl_connect('resize_event', self._refit)
        self._last = None
        #: GUI-5b: `overlay(ax, case)` draws on top of the shared drawing
        #: after `preview_draw` returns (the Setup panel's Z rings and
        #: selection highlight); None draws nothing extra
        self.overlay = None

    @property
    def ax(self):
        return self._ax

    @property
    def last_case(self):
        return self._last[0] if self._last is not None else None

    def show_case(self, case, show_mesh=False):
        self._last = (case, bool(show_mesh))
        note = self._draw(self._ax, case, show_mesh=show_mesh, pal=_pal())
        if self.overlay is not None:
            self.overlay(self._ax, case)
        theme.style_figure(self.figure)
        try:
            self.figure.tight_layout()
        except Exception:
            pass                      # a degenerate case must not raise
        self.draw()
        return note

    def _refit(self, _event=None):
        if self._last is None:
            return
        try:
            self.figure.tight_layout()
        except Exception:
            pass                      # a degenerate case must not raise
        self.draw()

    def redraw_overlay(self):
        """Re-draw only the overlay (a new selection, the rings toggle):
        the case drawing stays, the overlay's own artists are swapped."""
        if self._last is None or self.overlay is None:
            return
        self.overlay(self._ax, self._last[0])
        self.draw()

    def fit(self):
        """Back to the whole domain: replay the drawing, whose limits are
        the domain plus a margin."""
        if self._last is not None:
            self.show_case(*self._last)

    def retheme(self):
        """A dark/light switch changes the boundary and mesh colours, so
        the drawing is replayed rather than just recoloured."""
        if self._last is not None:
            self.show_case(*self._last)
        else:
            super().retheme()


class Preview1D(_MplPreview):
    def __init__(self, parent=None):
        super().__init__(preview_draw.draw_1d, parent)


class Preview2D(_MplPreview):
    def __init__(self, parent=None):
        super().__init__(preview_draw.draw_2d, parent)


class Preview3DBridge:
    """Feeds the viewer child's `setup` surface from the edited case.

    Leading edge: the first edit of a burst renders at once, the rest of
    the burst collapses into one trailing rebuild. The key covers only
    what the picture depends on, so typing in `cfl` or a file name sends
    nothing at all.
    """

    THROTTLE_MS = 500

    def __init__(self, host, log_fn=print):
        self.host = host
        self._log = log_fn
        self._key = None
        self._pending = None
        self._last_build = -1e9
        self._timer = QTimer(host)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._flush)

    # ── the visual-dependency key ────────────────────────────────────────
    @staticmethod
    def scene_key(case, show_mesh):
        """Everything the 3D scenery depends on, and nothing else: cfl,
        gauge file names and snapshot counts must not rebuild it."""
        def rows(seq):
            return tuple(tuple(float(x) for x in row)
                         for row in (seq or []))

        return (
            float(case.Lx), float(case.Ly), float(getattr(case, 'Lz', 0.0)),
            float(case.cell_size_m),
            tuple(float(x) for x in case.center),
            None if case.charge is None else float(case.charge),
            getattr(case, 'charge_resolution', 'resolve'),
            case.init_mode, getattr(case, 'solver', 'native'),
            getattr(case, 'material', 'TNT'),
            getattr(case, 'charge_refine', 'global'),
            int(getattr(case, 'amr_levels', 0) or 0),
            getattr(case, 'slice_axis', 'y'),
            None if getattr(case, 'slice_pos', None) is None
            else float(case.slice_pos),
            tuple(sorted((case.bcs or {}).items())),
            rows(case.obstacles), rows(case.gauges),
            rows(getattr(case, 'refine_zones', None)),
            rows(getattr(case, 'charges', None)),
            rows(getattr(case, 'det_points', None)),
            bool(show_mesh),
        )

    # ── driving ──────────────────────────────────────────────────────────
    def show_case(self, case, show_mesh=False):
        if not pyvista_available():
            return False
        now = time.monotonic() * 1000.0
        if self._timer.isActive() or (now - self._last_build
                                      < self.THROTTLE_MS):
            self._pending = (case, bool(show_mesh))
            wait = max(1, int(self.THROTTLE_MS - (now - self._last_build)))
            self._timer.start(wait)
            return True
        return self._build(case, show_mesh)

    def _flush(self):
        pending, self._pending = self._pending, None
        if pending is not None:
            self._build(*pending)

    def _build(self, case, show_mesh):
        key = None
        try:
            key = self.scene_key(case, show_mesh)
        except Exception:
            pass                       # an odd case still gets rebuilt
        self._last_build = time.monotonic() * 1000.0
        if key is not None and key == self._key:
            return True                # nothing visible changed
        try:
            geo = case_geometry(case, show_mesh=show_mesh)
        except Exception as exc:
            self._key = None
            self._log(f'  [3D preview unavailable: {exc}]')
            return False
        self._key = key
        return self.host.show_geometry(geo)

    def clear(self):
        self._timer.stop()
        self._pending = None
        self._key = None
