"""The Qt half of the Results-tab exports: where to write, and wiring.

The writing itself lives in `services/exports.py`, shared by both GUIs
(docs/ARCHITECTURE_REVIEW.md section 5, Phase 6). This module keeps the
two Qt-facing functions: `pick_target` asks the user where (it must run
on the GUI thread, because a file dialog spins an event loop) and
`export` picks a target, then runs `run_export` on a worker.

Every name moved to `services.exports` stays importable from here as the
same object (`ui/results_gauges.py` imports `summary_rows`,
`ui/results_panel.py` uses `can` and `why_not`, and the tests read the
rest - `write_animation` included, since a copy would let the two drift).
"""

import threading

from ..services.exports import (DIR_KINDS, KINDS,          # noqa: F401
                                _open, _report_caption, can, name_prefix,
                                png_figures, report_figures, run_export,
                                summary_rows, why_not, write_animation)
from . import dialogs


# ── where to write ───────────────────────────────────────────────────────
def pick_target(kind, ent, log=print, parent=None):
    """Ask the user where this export goes. Runs on the GUI thread.
    Returns '' when they cancelled or the export cannot run."""
    res, dim = ent.result, ent.dim
    pre = name_prefix(res)
    if kind == 'pngs':
        return dialogs.pick_dir('Save PNGs into', parent)
    if kind == 'fieldcsv':
        return dialogs.pick_dir('Save field CSVs into', parent)
    if kind == 'report':
        return dialogs.save_file(
            'Save HTML report', 'HTML (*.html)', parent,
            f'{pre}blast_{dim}d_report.html', '.html')
    if kind == 'tsv':
        return dialogs.save_file(
            'Save gauges TSV', 'Text (*.txt)', parent,
            f'{pre}gauges_{dim}d.txt', '.txt')
    if kind == 'summary':
        if not res.gauges.get('pressures'):
            log('No gauges in this result.')
            return ''
        return dialogs.save_file(
            'Save gauge summary CSV', 'CSV (*.csv)', parent,
            f'{pre}gauges_{dim}d_summary.csv', '.csv')
    if kind == 'vtk':
        from ..solvers.foam.export_vtk import can_export
        if not can_export(res.meta):
            log('VTK export needs a blastFoam run whose case directory '
                'still exists.')
            return ''
        return res.meta['case_dir']         # written in place, no dialog
    if kind == 'gif':
        if not res.meta.get('frames'):
            log('No recorded frames in this result.')
            return ''
        # .mp4 needs ffmpeg on PATH; write_animation falls back to .gif
        # with a note, so offer whichever this machine can write
        from matplotlib import animation as _mplanim
        ext = '.mp4' if _mplanim.FFMpegWriter.isAvailable() else '.gif'
        return dialogs.save_file(
            'Save animation', 'MP4 video (*.mp4);;Animated GIF (*.gif)',
            parent, f'{pre}blast_{dim}d_animation{ext}', ext)
    if kind == 'profile':
        if dim == 3:
            log('3D results have no profile export.')
            return ''
        return dialogs.save_file(
            'Save profile', 'All files (*.*)', parent,
            (f'{pre}blast_profile.txt' if dim == 1
             else f'{pre}blast_profile_2d.npz'),
            '.txt' if dim == 1 else '.npz')
    log(f'Unknown export: {kind}')
    return ''


def export(kind, ent, opts=None, log=print, parent=None, on_error=None,
           threaded=True):
    """Pick a target on the calling (GUI) thread, then write on a worker.
    Returns the target, or '' when nothing will be written."""
    if ent is None:
        log('Select a result before exporting.')
        return ''
    target = pick_target(kind, ent, log=log, parent=parent)
    if not target:
        return ''
    args = (kind, ent, target, opts, log, parent, on_error)
    if threaded:
        threading.Thread(target=run_export, args=args, daemon=True).start()
    else:
        run_export(*args)
    return target
