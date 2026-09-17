"""The Setup tab's 1D and 2D model previews, drawn onto a matplotlib
axis.

Extracted from the Tk preview panels so both front-ends draw the same
picture: the caller owns the figure and the canvas, passes the theme
colours in (`palette`) and does its own `tight_layout`/`draw`. Nothing
here imports a GUI toolkit.

A preview is not a plot of results - it is a drawing of the case that is
about to run: which boundary is a wall, where the obstacles and the
charge sit, which cells the mesh will have.
"""

import math

import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle, Rectangle

from ..core import refine
from ..core.bc import normalize_bc
from ..core.case import _charge_radius, validate_case

#: above this many fine display cells the 2D preview draws only the base
#: grid (the fine lines would be sub-pixel anyway)
MESH_PREVIEW_MAX = 250_000
#: full-span grid lines per direction (refinement boundaries always show)
MESH_MAX_LINES = 60

#: drawn opening angle of the 1D sector - legibility only; the mesh uses
#: writer.HALF_ANGLE_DEG (1 degree), which would draw as a bare line
DRAW_DEG = 30.0

CHARGE_FACE, CHARGE_EDGE = '#ff8f00', '#e65100'
DET_COLOR = '#e5484d'


def palette(dark=True, accent='#4f9eff', muted='#9aa4b2'):
    """The colours a preview needs from the host's theme."""
    return dict(
        dark=bool(dark), accent=accent, muted=muted,
        wall='#e8e8e8' if dark else '#37474f',
        open='#5c6672' if dark else '#b0bec5',
        obst_face='#5d6b7a' if dark else '#8d99ae',
        obst_edge='#8d99ae' if dark else '#5d6b7a',
    )


def _bc_style(kind, pal, wall_lw=2.5, open_lw=1.2):
    """reflect = solid bold wall; terminate = tight dots; transmit and
    anything else = long dashes. The 2D title spells the key out."""
    is_wall = kind == 'reflect'
    return dict(
        color=pal['wall'] if is_wall else pal['open'],
        lw=wall_lw if is_wall else open_lw,
        ls=('-' if is_wall else
            (0, (1, 2)) if kind == 'terminate' else (0, (4, 3))))


def _plan(case):
    """The refinement plan for a parsed case, or None when it cannot be
    laid out (validation reports why in the status strip)."""
    from ..core.case import material_rho0
    try:
        # N2-07: plan with the MATERIAL's rho0, exactly as validate_case
        # and the writer do - calling plan_levels bare defaults rho0 to
        # TNT's, so any other material drew a mesh that disagreed with
        # the validation strip and with what blastFoam then built
        return refine.plan_levels(case, rho0=material_rho0(case))
    except (ValueError, ZeroDivisionError, MemoryError, OverflowError,
            FloatingPointError):
        return None


# ── 2D ───────────────────────────────────────────────────────────────────
def draw_2d(ax, case, show_mesh=False, pal=None):
    """The Case2D domain: boundary kinds, obstacles, refinement zones,
    the charge, detonation points and gauges. Returns the mesh note that
    was appended to the title."""
    pal = pal or palette()
    ax.clear()
    Lx, Ly = case.Lx, case.Ly
    axisym = case.geometry == 'axisymmetric'

    for side, seg in (('x_lo', ((0, 0), (0, Ly))),
                      ('x_hi', ((Lx, Lx), (0, Ly))),
                      ('y_lo', ((0, Lx), (0, 0))),
                      ('y_hi', ((0, Lx), (Ly, Ly)))):
        ax.plot(*seg, zorder=2,
                **_bc_style(normalize_bc(case.bcs.get(side)), pal))

    for (x0, x1, y0, y1) in case.obstacles:
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0,
                               facecolor=pal['obst_face'],
                               edgecolor=pal['obst_edge'], zorder=3))

    # refinement zones (snapped boxes, colour per level) + the predicted
    # mesh when asked: the same structure the run will use
    plan = _plan(case)
    mesh_note = ''
    if plan is not None:
        for z in plan.zones:
            lv = refine.zone_level(z)
            col = refine.LEVEL_COLORS[min(max(lv, 1), refine.MAX_LEVEL) - 1]
            ax.add_patch(Rectangle((z[0], z[2]), z[1] - z[0], z[3] - z[2],
                                   fill=False, edgecolor=col, lw=1.3,
                                   ls='--', zorder=3.5))
            ax.annotate(f'L{lv}', (z[0], z[3]),
                        textcoords='offset points', xytext=(2, -9),
                        fontsize=7, color=col)
        if show_mesh:
            mesh_note = _mesh_2d(ax, plan, pal)

    cx = 0.0 if axisym else case.center[0]
    cy = case.center[1]
    if case.init_mode == 'charge' and case.charge and case.charge > 0:
        r = _charge_radius(case)
        ax.add_patch(Circle((cx, cy), max(r, 0.004 * max(Lx, Ly)),
                            facecolor=CHARGE_FACE, edgecolor=CHARGE_EDGE,
                            zorder=4))
    else:
        ax.plot([cx], [cy], marker='x', ms=9, mew=2, color=CHARGE_FACE,
                zorder=4)

    # blastFoam detonation points (G8: the preview showed nothing of them,
    # so a multi-point case looked like a single centred burst)
    for k, dp in enumerate(getattr(case, 'det_points', None) or []):
        px, py = (list(dp) + [0.0, 0.0])[:2]
        if axisym:
            px = 0.0
        ax.plot([px], [py], marker='x', ms=7, mew=1.8, color=DET_COLOR,
                zorder=4.5)
        ax.annotate(f'D{k + 1}', (px, py), textcoords='offset points',
                    xytext=(4, -10), fontsize=7, color=DET_COLOR)

    for k, (gx, gy) in enumerate(case.gauges):
        ax.plot([gx], [gy], marker='o', ms=5, color=pal['accent'], zorder=5)
        ax.annotate(f'G{k + 1}', (gx, gy), textcoords='offset points',
                    xytext=(4, 4), fontsize=7, color=pal['accent'])

    pad_x, pad_y = 0.04 * Lx, 0.04 * Ly
    ax.set_xlim(-pad_x, Lx + pad_x)
    ax.set_ylim(-pad_y, Ly + pad_y)
    ax.set_aspect('equal')
    ax.set_xlabel('r [m]' if axisym else 'x [m]')
    ax.set_ylabel('y [m]')
    ax.set_title(f'2D {case.geometry} · wall: solid, open: dashed'
                 + mesh_note, fontsize=9)
    _grid(ax, show_mesh)
    return mesh_note


def _mesh_2d(ax, plan, pal):
    """Cell edges of the predicted mesh (uniform: every base face).
    Returns a title suffix."""
    if plan.amr:
        segs = refine.mesh_segments_2d(None, plan.base['x_face'],
                                       plan.base['y_face'],
                                       max_lines=MESH_MAX_LINES)
        # short enough to fit the preview pane at 1100 px (QA-27): the
        # cell count is already on the validation strip
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
        note = (f' | mesh: {plan.n_pred:,} cells' if plan.refined
                else f' | mesh: {plan.n_fine:,} cells')
    ax.add_collection(LineCollection(segs, colors=pal['muted'],
                                     linewidths=0.35, alpha=0.6,
                                     zorder=1.5))
    return note


# ── 1D ───────────────────────────────────────────────────────────────────
def _arc(r, ang, n=64):
    """(x, y) of the arc of radius `r` from 0 to `ang` radians."""
    th = np.linspace(0.0, ang, n)
    return r * np.cos(th), r * np.sin(th)


def _sector_xy(r, ang):
    """Closed polygon of the sector from the apex out to `r`."""
    x, y = _arc(r, ang)
    return (np.concatenate([[0.0], x, [0.0]]),
            np.concatenate([[0.0], y, [0.0]]))


def draw_1d(ax, case, show_mesh=False, pal=None):
    """The Case1D spherical sector (T59).

    A 1D run is not a line: blastFoam solves it on the spherical sector
    `_blockmesh_1d` builds - a collapsed hex with its apex at the origin,
    four wedge lateral faces and the outlet arc at `radius_m`. The real
    opening is 1 degree, so the wedge is opened up for legibility, drawn
    from 0 to DRAW_DEG rather than symmetrically: the lower edge IS the
    axis, which is how a sector is usually read."""
    pal = pal or palette()
    edge = pal['wall']
    ax.clear()
    R = float(case.radius_m or 0.0)
    if R <= 0:
        ax.set_axis_off()
        return ''
    half = math.radians(DRAW_DEG)

    # the sector: the axis (0 deg), the second lateral face, and the
    # outlet arc - drawn in the language the 2D preview uses, so the
    # outer boundary kind is visible (T60)
    ax.fill(*_sector_xy(R, half), facecolor=pal['open'], alpha=0.12,
            edgecolor='none', zorder=0.5)
    ax.plot([0, R], [0, 0], color=edge, lw=2.0, zorder=2)
    ax.plot([0, R * math.cos(half)], [0, R * math.sin(half)], color=edge,
            lw=2.0, zorder=2)
    kind = normalize_bc(getattr(case, 'bc_outer', 'terminate'))
    ax.plot(*_arc(R, half), zorder=2,
            **_bc_style(kind, pal, wall_lw=2.5, open_lw=1.4))

    # the charge, at its own radius, inside the sector
    rep = validate_case(case)
    r_exp = rep.r_exp or 0.0
    if r_exp > 0:
        # a small charge on a big domain is a dot at the apex and reads
        # as "no charge at all", so it is drawn at a floor and the label
        # carries the true radius (as the 2D charge circle does)
        r_draw = min(max(r_exp, 0.015 * R), R)
        ax.fill(*_sector_xy(r_draw, half), facecolor=CHARGE_FACE,
                edgecolor=CHARGE_EDGE, lw=1.0, zorder=4)
        ax.text(0.02, 0.97,
                f'{case.charge_kg:g} kg '
                f'{getattr(case, "material", "TNT")}\n'
                f'r = {r_exp:.4g} m'
                + ('  (drawn enlarged)' if r_draw > r_exp * 1.01 else ''),
                transform=ax.transAxes, ha='left', va='top', fontsize=7.5,
                color=CHARGE_FACE, zorder=4.5)

    note = _mesh_1d(ax, case, rep, R, half, pal) if show_mesh else ''

    for k, g in enumerate(case.gauge_radii or []):
        g = float(g)
        if not 0 < g <= R:
            continue
        ax.plot(*_arc(g, half), color=pal['accent'], lw=1.0, alpha=0.9,
                zorder=5)
        ax.annotate(f'G{k + 1}', (g * math.cos(half * 0.55),
                                  g * math.sin(half * 0.55)),
                    textcoords='offset points', xytext=(3, 3), fontsize=7,
                    color=pal['accent'], zorder=5)

    pad = 0.06 * R
    ax.set_xlim(-pad, R + pad)
    ax.set_ylim(-pad, R * math.sin(half) + pad)
    ax.set_aspect('equal')
    ax.set_xlabel('r [m]')
    ax.set_ylabel('')
    ax.set_yticks([])
    ax.set_title(f'1D spherical sector · R = {R:g} m' + note,
                 fontsize=9)
    _grid(ax, show_mesh)
    return note


def _mesh_1d(ax, case, rep, R, half, pal):
    """The radial cell faces as arcs. Thinned to MESH_MAX_LINES: a
    default 1D case is 10,000 cells across, which would ink the whole
    sector solid. Returns a title suffix."""
    dx = rep.effective_dx or case.cell_size_m
    n = int(rep.n_cells or max(1, round(R / max(dx, 1e-12))))
    if n < 1:
        return ''
    step = max(1, math.ceil(n / MESH_MAX_LINES))
    for i in range(step, n, step):
        ax.plot(*_arc(i * (R / n), half), color=pal['muted'], lw=0.35,
                alpha=0.6, zorder=1.5)
    drawn = 'every face' if step == 1 else f'every {step}th face'
    return (f'\ncell {dx:.4g} m · {n:,} cells · {drawn} drawn'
            + (' · refined to resolve the charge'
               if rep.notes and any('refined' in t for t in rep.notes)
               else ''))


def _grid(ax, show_mesh):
    # grid(False, alpha=...) warns; set the properties only when on
    if show_mesh:
        ax.grid(False)
    else:
        ax.grid(True, alpha=0.25)
