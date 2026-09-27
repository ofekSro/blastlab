"""ParaView export of a finished blastFoam run (N4): `foamToVTK` on the
kept case directory, one file per written time in `<case>/VTK/`.

`-useTimeName` names the files by simulation time instead of index;
`-poly` keeps the polyhedral cells of locally refined meshes (hanging
nodes) instead of tet/pyramid decomposition. Parallel runs are already
reconstructed by the run loop, so the serial form applies. Results are
identified by `meta['case_dir']` (the UNC path the backend records).
"""

import os

from . import env, runner

VTK_CMD = 'foamToVTK -useTimeName -poly'


def can_export(meta):
    """True for a blastFoam result whose case directory still exists."""
    if not isinstance(meta, dict) or meta.get('solver') != 'blastfoam':
        return False
    cd = meta.get('case_dir')
    return bool(cd) and os.path.isdir(str(cd))


def export_vtk(case_dir, log=None, timeout=1800, vtk_dir=None):
    """Run foamToVTK on `case_dir` (UNC / posix / run name). Returns the
    UNC path of the VTK folder; raises RuntimeError (with the solver's
    tail) when the conversion fails. `vtk_dir` is the model's vtk\\ when
    the caller knows it (OUT-2: the warning of P11, below)."""
    log = log or (lambda s: None)
    posix, unc = env.case_paths(case_dir)
    if not os.path.isdir(unc):
        raise RuntimeError(f'case directory not found: {unc}')
    n_times = len([n for n in os.listdir(unc)
                   if os.path.isdir(os.path.join(unc, n))
                   and _is_time(n)])
    log(f'  [vtk] {VTK_CMD} in {posix} ({n_times} time dirs) ...')
    # owner decision P11: the run's own VTK export may have deleted
    # written times after converting them - this converts only the rest
    from .vtk_export import deleted_note
    note = deleted_note(posix, vtk_dir)
    if note:
        log(note)
    try:
        runner.run_stage(posix, [VTK_CMD], timeout=timeout)
    except runner.FoamStageError as exc:
        raise RuntimeError(f'foamToVTK failed: {exc}') from exc
    out = os.path.join(unc, 'VTK')
    n_files = len([f for f in os.listdir(out)
                   if os.path.isfile(os.path.join(out, f))]) \
        if os.path.isdir(out) else 0
    log(f'  [vtk] wrote {n_files} file(s) to {out}')
    return out


def _is_time(name):
    try:
        float(name)
        return True
    except ValueError:
        return False
