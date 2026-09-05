"""Live setup previews (VIPER-style), refreshed through the same
debounce as the validation strip so they follow the form as you type:

- Preview3DPanel: off-screen pyvista render of the Case3D being edited
  (domain box, ground, obstacles, charge ball, gauges);
- Preview2DPanel: matplotlib drawing of the Case2D domain (boundary
  types, obstacles, charge, gauges) - no pyvista needed."""

import customtkinter as ctk
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Rectangle

from ..core import refine
from ..core.case import _charge_radius
from ..core.constants import MIN_EXP_CELLS
from ..viz3d import MISSING_MSG, pyvista_available
from . import theme
from .mpl import EmbeddedFigure
from .vtk_host import VtkTkHost


#: above this many fine display cells the 2D preview draws only the
#: base grid (the fine lines would be sub-pixel anyway)
MESH_PREVIEW_MAX = 250_000
#: full-span grid lines per direction (refinement boundaries always show)
MESH_MAX_LINES = 60


def _plan(case):
    """The refinement plan for a parsed case, or None when the zones
    cannot be laid out (validation reports why)."""
    try:
        return refine.plan_levels(case)
    except ValueError:
        return None


def _mesh_3d(case, plan):
    """Whole-domain mesh data for viewer.mesh_polydata: the predicted
    grid (the viewer adds the six boundary faces) plus the live-slice
    plane of a Case3D."""
    axis = 'xyz'.index(getattr(case, 'slice_axis', 'y') or 'y')
    # dynamic AMR: the mesh follows the shock, so the preview can only
    # show the base grid it starts from
    g = plan.base if plan.amr else plan.fine
    c = g[('x_c', 'y_c', 'z_c')[axis]]
    pos = getattr(case, 'slice_pos', None)
    pos = float(case.center[axis]) if pos is None else float(pos)
    k = int(min(range(len(c)), key=lambda i: abs(float(c[i]) - pos)))
    return dict(axes=(g['x_c'], g['y_c'], g['z_c']), dx=float(g['dx']),
                refine=plan.meta() if plan.refined and not plan.amr else None,
                planes=[(axis, k, float(c[k]))])


def case_geometry(case, show_mesh=False):
    """Static-scenery geo dict for a Case3D (see viewer.add_static_scenery).
    The charge ball radius matches what the solver will actually use
    (including the 'smear' source-ball enlargement). Refinement zones
    ride along as `zones` (snapped boxes + level) and, with `show_mesh`,
    the predicted mesh as `mesh` (whole domain + live-slice plane)."""
    r_draw = 0.0
    if case.init_mode == 'charge' and case.charge and case.charge > 0:
        r_draw = _charge_radius(case)
        if getattr(case, 'charge_resolution', 'resolve') == 'smear' \
                and case.cell_size_m > r_draw / MIN_EXP_CELLS:
            r_draw = max(r_draw, 2.0 * case.cell_size_m)
    marker = 0.008 * max(case.Lx, case.Ly, case.Lz)
    geo = dict(Lx=case.Lx, Ly=case.Ly, Lz=case.Lz,
               obstacles=[tuple(o) for o in case.obstacles],
               charge_center=tuple(case.center),
               r_draw=max(r_draw, marker), r_gauge=marker,
               bcs=dict(case.bcs),
               gauges=[tuple(g) for g in case.gauges])
    plan = _plan(case)
    if plan is not None:
        geo['zones'] = [tuple(z) for z in plan.zones]
        if show_mesh:
            geo['mesh'] = _mesh_3d(case, plan)
    return geo


class Preview3DPanel(VtkTkHost):
    PLACEHOLDER = 'Select 3D to preview the model here.'

    def __init__(self, parent, log_fn=print):
        super().__init__(parent, log_fn=log_fn, view_size=(520, 480))

    def show_case(self, case, show_mesh=False):
        """Render (or update) the preview for a parsed Case3D."""
        if not pyvista_available():
            self.clear(MISSING_MSG)
            return
        if self._scene is None:
            from ..viz3d.viewer import GeometryScene
            self._scene = GeometryScene(self._make_plotter())
        try:
            self._scene.show(case_geometry(case, show_mesh=show_mesh))
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

    def show_case(self, case, show_mesh=False):
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

        # refinement zones (snapped boxes, colour per level) + the
        # predicted mesh when asked: the same structure the run will use
        plan = _plan(case)
        mesh_note = ''
        if plan is not None:
            for z in plan.zones:
                lv = refine.zone_level(z)
                col = refine.LEVEL_COLORS[
                    min(max(lv, 1), refine.MAX_LEVEL) - 1]
                ax.add_patch(Rectangle((z[0], z[2]), z[1] - z[0],
                                       z[3] - z[2], fill=False,
                                       edgecolor=col, lw=1.3, ls='--',
                                       zorder=3.5))
                ax.annotate(f'L{lv}', (z[0], z[3]),
                            textcoords='offset points', xytext=(2, -9),
                            fontsize=7, color=col)
            if show_mesh:
                mesh_note = self._draw_mesh(ax, plan)

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
        ax.set_title(f'2D {case.geometry} - solid: wall, dashed: open'
                     + mesh_note, fontsize=9)
        ax.grid(not show_mesh, alpha=0.25)
        theme.style_figure(self._fig)
        self._fig.tight_layout()
        self.canvas.draw()

    def _draw_mesh(self, ax, plan):
        """Cell edges of the predicted mesh (uniform: every base face).
        Returns a title suffix."""
        if plan.amr:
            segs = refine.mesh_segments_2d(None, plan.base['x_face'],
                                           plan.base['y_face'],
                                           max_lines=MESH_MAX_LINES)
            note = (f' | base grid ({plan.n_pred:,} cells) - AMR up to '
                    f'level {plan.amr} follows the shock')
        elif plan.n_fine > MESH_PREVIEW_MAX:
            segs = refine.mesh_segments_2d(None, plan.base['x_face'],
                                           plan.base['y_face'],
                                           max_lines=MESH_MAX_LINES)
            note = ' | base grid only (mesh too fine to draw)'
        else:
            src = refine.slice_src(plan.levels, plan.lmax,
                                   solid_fine=plan.solid_fine)
            segs = refine.mesh_segments_2d(src, plan.fine['x_face'],
                                           plan.fine['y_face'],
                                           max_lines=MESH_MAX_LINES)
            note = (f' | mesh: {plan.n_pred:,} cells'
                    if plan.refined else f' | mesh: {plan.n_fine:,} cells')
        ax.add_collection(LineCollection(segs, colors=theme.cur('muted'),
                                         linewidths=0.35, alpha=0.6,
                                         zorder=1.5))
        return note
