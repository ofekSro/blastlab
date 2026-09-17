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
    return preview_draw.palette(dark=theme.mode() == 'dark',
                                accent=theme.cur('accent'),
                                muted=theme.cur('muted'))


class _MplPreview(MplCanvas):
    """One reused figure and axis; `show_case` redraws it in place."""

    def __init__(self, draw, parent=None):
        super().__init__(toolbar=False, parent=parent)
        self._draw = draw
        fig = Figure(figsize=(5, 5))
        self._ax = fig.add_subplot()
        self.set_figure(fig)
        self._last = None

    @property
    def ax(self):
        return self._ax

    def show_case(self, case, show_mesh=False):
        self._last = (case, bool(show_mesh))
        note = self._draw(self._ax, case, show_mesh=show_mesh, pal=_pal())
        theme.style_figure(self.figure)
        try:
            self.figure.tight_layout()
        except Exception:
            pass                      # a degenerate case must not raise
        self.draw()
        return note

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
