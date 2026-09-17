"""Live setup previews (VIPER-style), refreshed through the same
debounce as the validation strip so they follow the form as you type:

- Preview3DPanel: off-screen pyvista render of the Case3D being edited
  (domain box, ground, obstacles, charge ball, gauges);
- Preview2DPanel: matplotlib drawing of the Case2D domain (boundary
  types, obstacles, charge, gauges) - no pyvista needed."""

import time

import customtkinter as ctk
from matplotlib.figure import Figure

from ..core.case import material_rho0  # noqa: F401
from ..core.constants import MIN_EXP_CELLS  # noqa: F401
# the drawing itself moved to output/preview_draw.py (shared with the Qt
# front-end); this module is now just the Tk host for it
from ..output import preview_draw
from ..output.preview_draw import (MESH_MAX_LINES,  # noqa: F401
                                   MESH_PREVIEW_MAX)
from ..viz3d import MISSING_MSG, pyvista_available
# _plan / _mesh_3d / case_geometry moved to viz3d/geometry.py (shared
# with the Qt front-end); re-exported here for the Tk panel and its tests
from ..viz3d.geometry import _mesh_3d, _plan, case_geometry  # noqa: F401
from . import theme
from .mpl import EmbeddedFigure
from .vtk_host import VtkTkHost


def _pal():
    """The preview palette for the current CTk appearance mode."""
    return preview_draw.palette(dark=ctk.get_appearance_mode() == 'Dark',
                                accent=theme.cur('accent'),
                                muted=theme.cur('muted'))


class Preview3DPanel(VtkTkHost):
    PLACEHOLDER = 'Select 3D to preview the model here.'

    #: leading-edge throttle: the first edit of a burst renders at once,
    #: the rest of the burst collapses into one trailing rebuild
    THROTTLE_MS = 500

    def __init__(self, parent, log_fn=print):
        super().__init__(parent, log_fn=log_fn, view_size=(520, 480))
        self._geo_key = None
        self._build_job = None
        self._pending = None
        self._last_build = -1e9

    @staticmethod
    def _key(case, show_mesh):
        """Everything the rendered scene depends on. Rebuilding the VTK
        actors costs ~1.5 s, and the 300 ms validation debounce fired it
        on every keystroke - including edits (cfl, file names, gauges
        file) that cannot change the picture."""
        def rows(v):
            return tuple(tuple(float(x) for x in r) for r in (v or []))
        return (case.Lx, case.Ly, getattr(case, 'Lz', 0.0),
                case.cell_size_m, tuple(float(v) for v in case.center),
                case.charge, getattr(case, 'charge_resolution', ''),
                getattr(case, 'init_mode', ''), getattr(case, 'solver', ''),
                getattr(case, 'material', ''),
                getattr(case, 'charge_refine', ''),
                int(getattr(case, 'amr_levels', 0) or 0),
                getattr(case, 'slice_axis', ''), getattr(case, 'slice_pos', None),
                tuple(sorted((case.bcs or {}).items())),
                rows(case.obstacles), rows(case.gauges),
                rows(getattr(case, 'refine_zones', None)),
                rows(getattr(case, 'charges', None)),
                rows(getattr(case, 'det_points', None)),
                bool(show_mesh))

    def show_case(self, case, show_mesh=False):
        """Render (or update) the preview for a parsed Case3D.

        The 300 ms validation debounce calls this on every keystroke.
        The key cache below skips edits that cannot change the picture;
        for the ones that can, a burst of typing is collapsed into one
        rebuild at most every THROTTLE_MS (G4).
        """
        now = time.monotonic() * 1000.0
        if (self._build_job is not None
                or now - self._last_build < self.THROTTLE_MS):
            self._pending = (case, show_mesh)
            if self._build_job is None:
                wait = int(max(1, self.THROTTLE_MS - (now - self._last_build)))
                self._build_job = self.after(wait, self._flush_pending)
            return
        self._build(case, show_mesh)

    def _flush_pending(self):
        self._build_job = None
        pending, self._pending = self._pending, None
        if pending is not None:
            self._build(*pending)

    def _build(self, case, show_mesh=False):
        self._last_build = time.monotonic() * 1000.0
        if not pyvista_available():
            self.clear(MISSING_MSG)
            return
        try:
            key = self._key(case, show_mesh)
        except Exception:
            key = None
        if key is not None and key == self._geo_key and self._scene is not None:
            return                      # nothing visible changed
        if self._scene is None:
            from ..viz3d.viewer import GeometryScene
            self._scene = GeometryScene(self._make_plotter())
        try:
            self._scene.show(case_geometry(case, show_mesh=show_mesh))
        except Exception as exc:
            self._geo_key = None
            self.clear(f'preview unavailable: {exc}')
            self._log(f'3D preview error: {exc}')
            return
        self._geo_key = key
        self._dirty = True

    def clear(self, message=None):
        """Drop back to the text placeholder (non-3D case / parse error).
        The scene is dropped so the render tick stops blitting over the
        placeholder; the next show_case rebuilds it."""
        if self._build_job is not None:
            try:
                self.after_cancel(self._build_job)
            except Exception:
                pass
            self._build_job = None
        self._pending = None
        self._scene = None
        self._geo_key = None
        self._dirty = False
        self._photo = None
        self.view.configure(image='', text=message or self.PLACEHOLDER)


class Preview2DPanel(ctk.CTkFrame):
    """Matplotlib preview of a Case2D: domain with boundary types,
    obstacles, the charge (or remap origin) and gauges. Boundary /
    obstacle colors are picked from the current theme at draw time
    (the preview redraws on every form edit)."""

    def __init__(self, parent):
        super().__init__(parent, fg_color='transparent', corner_radius=0)
        self.canvas = EmbeddedFigure(self, figsize=(5, 5), toolbar=False)
        self.canvas.pack(fill='both', expand=True)
        self._fig = Figure(figsize=(5, 5))
        self._ax = self._fig.add_subplot()
        self.canvas.set_figure(self._fig)

    def show_case(self, case, show_mesh=False):
        note = preview_draw.draw_2d(self._ax, case, show_mesh=show_mesh,
                                    pal=_pal())
        theme.style_figure(self._fig)
        self._fig.tight_layout()
        self.canvas.draw()
        return note


class Preview1DPanel(ctk.CTkFrame):
    """Matplotlib preview of a Case1D (T59).

    A 1D run is not a line: blastFoam solves it on the spherical SECTOR
    `_blockmesh_1d` builds - a collapsed hex with its apex at the origin,
    four wedge lateral faces and the outlet arc at `radius_m`. This draws
    that sector in the plane through its axis, with the charge sphere
    filled at its own radius inside it, the gauge radii marked, and (with
    Show mesh) the radial cell faces as arcs.

    The real opening is `writer.HALF_ANGLE_DEG` = 1 degree, which would
    draw as a bare line, so the wedge is opened up for legibility. It is
    drawn from 0 to DRAW_DEG rather than symmetrically about the axis:
    the lower edge IS the axis, which is how a sector is usually read.
    """

    #: drawn opening angle - legibility only; the mesh uses HALF_ANGLE_DEG
    DRAW_DEG = preview_draw.DRAW_DEG

    def __init__(self, parent):
        super().__init__(parent, fg_color='transparent', corner_radius=0)
        self.canvas = EmbeddedFigure(self, figsize=(5, 5), toolbar=False)
        self.canvas.pack(fill='both', expand=True)
        self._fig = Figure(figsize=(5, 5))
        self._ax = self._fig.add_subplot()
        self.canvas.set_figure(self._fig)

    _arc = staticmethod(preview_draw._arc)

    def show_case(self, case, show_mesh=False):
        note = preview_draw.draw_1d(self._ax, case, show_mesh=show_mesh,
                                    pal=_pal())
        theme.style_figure(self._fig)
        self._fig.tight_layout()
        self.canvas.draw()
        return note

