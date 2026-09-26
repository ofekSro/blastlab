"""Run jobs shared by the GUI front-ends: one stage = one case solved
plus the output files the CLI flow would write (gauges, animation,
profile). Toolkit-free; moved out of the Tk app.

A write that fails never throws the finished solve away (UX 2): it is
logged as `[warn] could not write <file>: <reason>` and the other writes
still happen. A failed gauge TSV or animation is only a warning - nothing
downstream reads them, and both can be exported again from Results. A
failed hand-off file (remap profile, trigger remap) raises
HandoffWriteError carrying the Result, so the worker posts the result
and then stops the chain: the next stage would otherwise start from a
stale or missing profile."""

from ..core.profiles import save_profile, save_profile_2d
# module level on purpose: these names are the seam the GUI tests patch
# to watch what a run stage writes (test_gui_refine_preview)
from ..output.animation import write_animation
from ..output.gauges import save_gauges_1d, save_gauges_2d, save_gauges_3d


class HandoffWriteError(Exception):
    """A finished stage could not write a hand-off file (its remap
    profile or trigger remap). `result` is the stage's complete Result;
    `failures` lists (path, reason), `path` / `reason` are the first."""

    def __init__(self, result, failures):
        self.result = result
        self.failures = list(failures)
        self.path, self.reason = self.failures[0]
        files = '; '.join(f'{p}: {r}' for p, r in self.failures)
        super().__init__(
            f'Could not write the hand-off file {files}\n'
            'The result of this stage is kept in Results. The run stopped '
            'here, so no later stage starts from a stale or missing '
            'profile.')


def _write(hooks, path, write, *args, **kwargs):
    """Run one output write. On failure log the warning through the
    stage's hooks and return (path, reason); None when it worked. With
    no hooks (a direct call, not a run stage) the error propagates."""
    try:
        write(*args, **kwargs)
    except Exception as exc:
        if hooks is None:
            raise
        reason = str(exc) or type(exc).__name__
        hooks.log(f'[warn] could not write {path}: {reason}')
        return (path, reason)
    return None


def write_trigger_remap(case, res, hooks=None):
    """T51: the remap file a trigger gauge asked for, written at the
    instant the wave reached it.

    Only the 'remap' (keep running) action needs this: the terminating
    actions stop the run there, so the state the normal profile write
    already saves IS the trigger state. The path is the case's trigger
    file, falling back to its profile output. 2D only - 3D has no remap
    format and 1D has no trigger gauge (T63).

    Returns (path, reason) when the write failed and was logged through
    `hooks` (see `_write`), else None."""
    path = getattr(case, 'trigger_file', None) or case.profile_file
    if not path:
        return None
    if case.dim == 2 and res.meta.get('trigger_state') is not None:
        return _write(hooks, path, save_profile_2d,
                      dict(res.meta, final_state=res.meta['trigger_state']),
                      path)
    return None


def _animate(case, res, hooks=None):
    """Write the run's own animation, and record the colour-scale choice
    in the Result's meta so a later export from the Results tab keeps
    it without needing the case. A failed write is logged (`_write`)."""
    res.meta.setdefault('anim_scale', getattr(case, 'anim_scale', 'run'))
    res.meta.setdefault('anim_clim', getattr(case, 'anim_clim', None))
    if case.anim_file and res.meta.get('frames'):
        _write(hooks, case.anim_file, write_animation,
               res.meta, case.anim_file,
               show_mesh=getattr(case, 'anim_mesh', False),
               scale=getattr(case, 'anim_scale', None),
               clim=getattr(case, 'anim_clim', None))


#: OUT-1: the model-folder stage wrapper, `services.model_folder.
#: stage_solve`, registered by that module when it is imported. solvers/
#: may not import services/ (test_layering), so the dependency is
#: inverted: every caller that passes a stage_dir has already imported
#: model_folder (it prepared the folder with it).
_stage_folder = None


def register_stage_folder(wrap):
    """Install `wrap(dim, case, stage_dir, run_info, make_solve) ->
    solve(hooks)` as the stage_dir path of `solve_stage`."""
    global _stage_folder
    _stage_folder = wrap


def solve_stage(dim, case, stage_dir=None, run_info=None):
    """Return (label, solve_callable(hooks) -> Result) for a case; the
    callable also writes the case's own output files (gauges, animation,
    profile) exactly like the CLI flow does.

    Every write is attempted even when an earlier one failed; a failed
    hand-off write (profile, trigger remap) raises HandoffWriteError
    carrying the Result once all writes are done (UX 2).

    OUT-1: with `stage_dir` (a prepared model folder) the stage binds the
    case's output files into it, keeps run.log there and writes every
    row of the model folder after the solve - also, as far as it can,
    after a failure or a stop, before re-raising
    (`services.model_folder.stage_solve`). `run_info` feeds the manifest.
    `stage_dir=None` is exactly the behaviour before OUT-1."""
    backend = getattr(case, 'solver', 'native')
    label = f'{dim}D' + (' blastFoam' if backend == 'blastfoam' else '')
    if stage_dir is None:
        return (label, _solver(dim, case))
    if _stage_folder is None:
        raise RuntimeError('solve_stage(stage_dir=...) needs '
                           'blastlab.services.model_folder imported - it '
                           'registers the model-folder writer')
    return (label, _stage_folder(dim, case, stage_dir, run_info,
                                 lambda bound: _solver(dim, bound)))


def _solver(dim, case):
    """The solve callable of `solve_stage`: solve, then write the case's
    own output files."""
    backend = getattr(case, 'solver', 'native')

    def solve(hooks):
        from . import get_solver
        res = get_solver(dim, backend)(case, hooks)
        handoff = []        # (path, reason) or None per hand-off write
        # Both halves of the guard matter: gauge POINTS say there is
        # something to write, gauge_file says the case asked for it.
        # Without the second, `gauge_file=None` wrote a file literally
        # named "None" into the working directory - np.savetxt stringifies
        # its path. The profile lines two below always had it right.
        if dim == 1:
            if case.gauge_radii and case.gauge_file:
                _write(hooks, case.gauge_file, save_gauges_1d,
                       res.gauges, case.gauge_file)
            if case.profile_file:
                handoff.append(_write(hooks, case.profile_file, save_profile,
                                      res.meta['final_profile'],
                                      case.profile_file))
        elif dim == 2:
            if case.gauges and case.gauge_file:
                _write(hooks, case.gauge_file, save_gauges_2d,
                       res.gauges, case.gauge_file)
            _animate(case, res, hooks)
            if case.profile_file:
                handoff.append(_write(hooks, case.profile_file,
                                      save_profile_2d, res.meta,
                                      case.profile_file))
            handoff.append(write_trigger_remap(case, res, hooks))
        else:
            if case.gauges and case.gauge_file:
                _write(hooks, case.gauge_file, save_gauges_3d,
                       res.gauges, case.gauge_file)
            _animate(case, res, hooks)
        failed = [f for f in handoff if f]
        if failed:
            raise HandoffWriteError(res, failed)
        return res
    return solve
