"""Static-scenery geometry of a Case3D for the setup preview
(`viewer.add_static_scenery` / `GeometryScene.show`). Toolkit-free and
pyvista-free; moved out of the Tk preview panel."""

from ..core import refine
from ..core.case import _charge_radius, material_rho0
from ..core.constants import MIN_EXP_CELLS


def _plan(case):
    """The refinement plan for a parsed case, or None when it cannot be
    laid out (validation reports why in the status strip). A grid too
    large/fine to plan, a torn cell size or a nan extent all come back as
    ValueError now; catch the residual numeric blow-ups too so a preview
    can never take the app down."""
    try:
        # N2-07: plan with the MATERIAL's rho0, exactly as validate_case
        # and the writer do. Calling plan_levels bare defaults rho0 to
        # TNT's 1630, so for any other material this panel drew a mesh
        # that disagreed with the numbers on the validation strip and
        # with the mesh blastFoam then built (ANFO: one whole extra
        # refinement level, finest cell 2x too small).
        return refine.plan_levels(case, rho0=material_rho0(case))
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
