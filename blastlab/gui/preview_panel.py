"""Live setup previews (VIPER-style), refreshed through the same
debounce as the validation strip so they follow the form as you type:

- Preview3DPanel: off-screen pyvista render of the Case3D being edited
  (domain box, ground, obstacles, charge ball, gauges);
- Preview2DPanel: matplotlib drawing of the Case2D domain (boundary
  types, obstacles, charge, gauges) - no pyvista needed."""

import customtkinter as ctk
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Rectangle

from ..core.case import _charge_radius
from ..core.constants import MIN_EXP_CELLS
from ..viz3d import MISSING_MSG, pyvista_available
from . import theme
from .mpl import EmbeddedFigure
from .vtk_host import VtkTkHost


def case_geometry(case):
    """Static-scenery geo dict for a Case3D (see viewer.add_static_scenery).
    The charge ball radius matches what the solver will actually use
    (including the 'smear' source-ball enlargement)."""
    r_draw = 0.0
    if case.init_mode == 'charge' and case.charge and case.charge > 0:
        r_draw = _charge_radius(case)
        if getattr(case, 'charge_resolution', 'resolve') == 'smear' \
                and case.cell_size_m > r_draw / MIN_EXP_CELLS:
            r_draw = max(r_draw, 2.0 * case.cell_size_m)
    marker = 0.008 * max(case.Lx, case.Ly, case.Lz)
    return dict(Lx=case.Lx, Ly=case.Ly, Lz=case.Lz,
                obstacles=[tuple(o) for o in case.obstacles],
                charge_center=tuple(case.center),
                r_draw=max(r_draw, marker), r_gauge=marker,
                bcs=dict(case.bcs),
                gauges=[tuple(g) for g in case.gauges])


class Preview3DPanel(VtkTkHost):
    PLACEHOLDER = 'Select 3D to preview the model here.'

    def __init__(self, parent, log_fn=print):
        super().__init__(parent, log_fn=log_fn, view_size=(520, 480))

    def show_case(self, case):
        """Render (or update) the preview for a parsed Case3D."""
        if not pyvista_available():
            self.clear(MISSING_MSG)
            return
        if self._scene is None:
            from ..viz3d.viewer import GeometryScene
            self._scene = GeometryScene(self._make_plotter())
        try:
            self._scene.show(case_geometry(case))
        except Exception as exc:
            self._log(f'3D preview error: {exc}')
            return
        self._dirty = True

    def clear(self, message=None):
        """Drop back to the text placeholder (non-3D case / parse error).
        The scene is dropped so the render tick stops blitting over the
        placeholder; the next show_case rebuilds it."""
        self._scene = None
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

    def show_case(self, case):
        dark = ctk.get_appearance_mode() == 'Dark'
        wall = '#e8e8e8' if dark else '#37474f'
        open_ = '#5c6672' if dark else '#b0bec5'
        obst_face = '#5d6b7a' if dark else '#8d99ae'
        obst_edge = '#8d99ae' if dark else '#5d6b7a'

        ax = self._ax
        ax.clear()
        Lx, Ly = case.Lx, case.Ly
        axisym = case.geometry == 'axisymmetric'

        # boundary sides: wall = solid bold, open = dashed light
        for side, seg in (('x_lo', ((0, 0), (0, Ly))),
                          ('x_hi', ((Lx, Lx), (0, Ly))),
                          ('y_lo', ((0, Lx), (0, 0))),
                          ('y_hi', ((0, Lx), (Ly, Ly)))):
            is_wall = case.bcs.get(side) == 'wall'
            ax.plot(*seg, color=wall if is_wall else open_,
                    lw=2.5 if is_wall else 1.2,
                    ls='-' if is_wall else (0, (4, 3)), zorder=2)

        for (x0, x1, y0, y1) in case.obstacles:
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0,
                                   facecolor=obst_face,
                                   edgecolor=obst_edge, zorder=3))

        cx = 0.0 if axisym else case.center[0]
        cy = case.center[1]
        if case.init_mode == 'charge' and case.charge and case.charge > 0:
            r = _charge_radius(case)
            ax.add_patch(Circle((cx, cy), max(r, 0.004 * max(Lx, Ly)),
                                facecolor='#ff8f00', edgecolor='#e65100',
                                zorder=4))
        else:
            ax.plot([cx], [cy], marker='x', ms=9, mew=2,
                    color='#ff8f00', zorder=4)

        gauge_c = theme.cur('accent')
        for k, (gx, gy) in enumerate(case.gauges):
            ax.plot([gx], [gy], marker='o', ms=5, color=gauge_c, zorder=5)
            ax.annotate(f'G{k + 1}', (gx, gy), textcoords='offset points',
                        xytext=(4, 4), fontsize=7, color=gauge_c)

        pad_x, pad_y = 0.04 * Lx, 0.04 * Ly
        ax.set_xlim(-pad_x, Lx + pad_x)
        ax.set_ylim(-pad_y, Ly + pad_y)
        ax.set_aspect('equal')
        ax.set_xlabel('r [m]' if axisym else 'x [m]')
        ax.set_ylabel('y [m]')
        ax.set_title(f'2D {case.geometry} - solid: wall, dashed: open',
                     fontsize=9)
        ax.grid(True, alpha=0.25)
        theme.style_figure(self._fig)
        self._fig.tight_layout()
        self.canvas.draw()
