"""Live setup previews (VIPER-style), refreshed through the same
debounce as the validation strip so they follow the form as you type:

- Preview3DPanel: off-screen pyvista render of the Case3D being edited
  (domain box, ground, obstacles, charge ball, gauges);
- Preview2DPanel: matplotlib drawing of the Case2D domain (boundary
  types, obstacles, charge, gauges) - no pyvista needed."""

import time

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
    """The refinement plan for a parsed case, or None when it cannot be
    laid out (validation reports why in the status strip). A grid too
    large/fine to plan, a torn cell size or a nan extent all come back as
    ValueError now; catch the residual numeric blow-ups too so a preview
    can never take the app down."""
    try:
        return refine.plan_levels(case)
    except (ValueError, ZeroDivisionError, MemoryError, OverflowError,
            FloatingPointError):
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
    # extra blastFoam charges get their own radius from their own mass
    extras = []
    for ch in (getattr(case, 'charges', None) or []):
        try:
            ex, ey, ez, mass = (list(ch) + [0.0])[:4]
            r_i = refine.charge_radius(float(mass))
        except (TypeError, ValueError):
            continue
        extras.append((float(ex), float(ey), float(ez),
                       max(r_i, marker)))
    geo = dict(Lx=case.Lx, Ly=case.Ly, Lz=case.Lz,
               obstacles=[tuple(o) for o in case.obstacles],
               charge_center=tuple(case.center),
               r_draw=max(r_draw, marker), r_gauge=marker,
               bcs=dict(case.bcs),
               charges=extras,
               det_points=[tuple(float(v) for v in p)
                           for p in (getattr(case, 'det_points', None) or [])],
               gauges=[tuple(g) for g in case.gauges])
    plan = _plan(case)
    if plan is not None:
        geo['zones'] = [tuple(z) for z in plan.zones]
        if show_mesh:
            geo['mesh'] = _mesh_3d(case, plan)
    return geo


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

        # blastFoam detonation points (G8: the preview showed nothing of
        # them, so a multi-point case looked like a single centred burst)
        for k, dp in enumerate(getattr(case, 'det_points', None) or []):
            px, py = (list(dp) + [0.0, 0.0])[:2]
            if axisym:
                px = 0.0
            ax.plot([px], [py], marker='x', ms=7, mew=1.8,
                    color='#e5484d', zorder=4.5)
            ax.annotate(f'D{k + 1}', (px, py), textcoords='offset points',
                        xytext=(4, -10), fontsize=7, color='#e5484d')

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
        ax.set_title(f'2D {case.geometry} · wall: solid, open: dashed'
                     + mesh_note, fontsize=9)
        # grid(False, alpha=...) warns; set the properties only when on
        if show_mesh:
            ax.grid(False)
        else:
            ax.grid(True, alpha=0.25)
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
            # short enough to fit the preview pane at 1100 px (QA-27):
            # the cell count is already on the validation strip
            note = f' | base grid · AMR L{plan.amr} follows the shock'
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
