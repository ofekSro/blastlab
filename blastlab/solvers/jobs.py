"""Run jobs shared by the GUI front-ends: one stage = one case solved
plus the output files the CLI flow would write (gauges, animation,
profile). Toolkit-free; moved out of the Tk app."""

from ..core.profiles import save_profile, save_profile_2d
# module level on purpose: these names are the seam the GUI tests patch
# to watch what a run stage writes (test_gui_refine_preview)
from ..output.animation import write_animation
from ..output.gauges import save_gauges_1d, save_gauges_2d, save_gauges_3d


def write_trigger_remap(case, res):
    """T51: the remap file a trigger gauge asked for, written at the
    instant the wave reached it.

    Only the 'remap' (keep running) action needs this: the terminating
    actions stop the run there, so the state the normal profile write
    already saves IS the trigger state. The path is the case's trigger
    file, falling back to its profile output. 2D only - 3D has no remap
    format and 1D has no trigger gauge (T63)."""
    path = getattr(case, 'trigger_file', None) or case.profile_file
    if not path:
        return
    if case.dim == 2 and res.meta.get('trigger_state') is not None:
        save_profile_2d(dict(res.meta,
                             final_state=res.meta['trigger_state']), path)


def solve_stage(dim, case):
    """Return (label, solve_callable(hooks) -> Result) for a case; the
    callable also writes the case's own output files (gauges, animation,
    profile) exactly like the CLI flow does."""
    backend = getattr(case, 'solver', 'native')

    def solve(hooks):
        from . import get_solver
        res = get_solver(dim, backend)(case, hooks)
        if dim == 1:
            if case.gauge_radii:
                save_gauges_1d(res.gauges, case.gauge_file)
            if case.profile_file:
                save_profile(res.meta['final_profile'], case.profile_file)
        elif dim == 2:
            if case.gauges:
                save_gauges_2d(res.gauges, case.gauge_file)
            if case.anim_file and res.meta.get('frames'):
                write_animation(res.meta, case.anim_file,
                                show_mesh=getattr(case, 'anim_mesh',
                                                  False))
            if case.profile_file:
                save_profile_2d(res.meta, case.profile_file)
            write_trigger_remap(case, res)
        else:
            if case.gauges:
                save_gauges_3d(res.gauges, case.gauge_file)
            if case.anim_file and res.meta.get('frames'):
                write_animation(res.meta, case.anim_file,
                                show_mesh=getattr(case, 'anim_mesh',
                                                  False))
        return res
    label = f'{dim}D' + (' blastFoam' if backend == 'blastfoam' else '')
    return (label, solve)
