"""Everything the Results tab writes to disk, with no panel attached.

The toolkit-free half of the export orchestration, shared by both GUIs
(docs/ARCHITECTURE_REVIEW.md section 5, Phase 6; finding F7). Moved
verbatim from `ui/exports.py`, which keeps `pick_target` and `export`
(the Qt file dialogs) and re-exports the moved names; the Tk
`ResultsPanel._export` keeps its own dialogs and worker thread and calls
`run_export` for the writing.

`run_export` does the work and must NOT run on a GUI thread, because
building matplotlib figures for a 3D run takes seconds; it touches no
widget. Every file it writes goes through `output/` and
`core.profiles`. No GUI toolkit, no pyplot and no VTK is imported here.

Screen and file deliberately differ: the Results tab shows ONE large
field panel, while `pngs` and `report` keep writing the full snapshot
grid that `output/plots.py` builds. The button tooltips say so.
"""

import os
import re

from ..core.profiles import save_profile, save_profile_2d
from ..models.meta import charge_label
from ..output import gauge_summary, plots
from ..output.animation import write_animation
from ..output.gauges import save_gauges_1d, save_gauges_2d, save_gauges_3d

#: every export this module can run, in the order the buttons sit
KINDS = ('profile', 'gif', 'vtk', 'summary', 'tsv', 'fieldcsv', 'report',
         'pngs')

#: an export that writes a whole directory rather than one file
DIR_KINDS = ('pngs', 'fieldcsv')


def name_prefix(res):
    """'<run name>_' for the suggested file names, so three runs do not
    all propose gauges_2d.txt."""
    name = str(res.meta.get('name') or '').strip()
    slug = re.sub(r'[^0-9A-Za-z._-]+', '_', name).strip('_')
    return f'{slug[:40]}_' if slug else ''


def summary_rows(res, opts=None):
    """Per-gauge engineering rows. meta['gauges'] is what the user asked
    for; gauges['points'] is where the solver actually put them. `opts`
    may carry `gauge_numbers`, a 1D result's entered numbers (GUI-16 (b);
    `run_export`)."""
    return gauge_summary.summarize_gauges(
        res.gauges, requested=res.meta.get('gauges'),
        numbers=(opts or {}).get('gauge_numbers') or None)


def can(kind, ent):
    """Whether this export can run for this result at all."""
    if ent is None:
        return False
    from ..solvers.foam.export_vtk import can_export
    res, dim, meta = ent.result, ent.dim, ent.result.meta
    has_gauges = bool(res.gauges.get('pressures'))
    return dict(
        # a run that wrote <MODEL>\vtk\ opens it (F2) even without a case dir
        vtk=can_export(meta) or bool(run_vtk(ent)),
        gif=bool(meta.get('frames')),
        summary=has_gauges,
        tsv=has_gauges,
        pngs=bool(res.snapshots),
        profile=(dim == 1 or (dim == 2
                              and meta.get('geometry') == 'axisymmetric')),
    ).get(kind, True)


#: OUT-1: the VTK button of a run whose WSL case directory was deleted
#: after a verified copy (plan sec. 2.3)
SCRATCH_RELEASED = (
    "This run's WSL scratch was released after a verified copy into the "
    "model folder. Its foam\\ folder keeps the dictionaries, mesh, probes "
    "and logs, not the written fields, so there is nothing left to write "
    "as VTK.")


def model_dir(ent):
    """The result's model folder (OUT-1), when it has one that still
    exists: the start directory of the export dialogs (owner Q3)."""
    path = (getattr(getattr(ent, 'result', None), 'meta', None) or {}).get(
        'model_dir')
    return path if path and os.path.isdir(path) else ''


def run_vtk(ent):
    """(vtk dir, file count) when the run itself wrote VTK files into the
    result's model folder - `<MODEL>\\vtk\\` with its manifest.json
    (OUT-2) - else None. GUI QA 2026-09-27 F2: the Results tab used to say
    there was nothing to write while that folder held 258 files."""
    home = model_dir(ent)
    if not home:
        return None
    from ..output.vtk_series import MANIFEST_FILE
    from .model_folder import VTK_DIR
    vdir = os.path.join(home, VTK_DIR)
    if not os.path.isfile(os.path.join(vdir, MANIFEST_FILE)):
        return None
    return vdir, sum(len(files) for _r, _d, files in os.walk(vdir))


def run_vtk_text(found):
    """The VTK button's tooltip for a `run_vtk` folder."""
    vdir, n = found
    return (f'Written during the run: {vdir} - {n} files (see '
            f'vtk\\manifest.json). Click to open the folder; in ParaView, '
            f'File > Open a .vtk.series file.')


def vtk_opens_folder(ent):
    """The `run_vtk` folder when the VTK button opens it instead of
    converting: the run wrote VTK files and the case directory the
    converter needs is gone (usually the released WSL scratch)."""
    if ent is None:
        return None
    from ..solvers.foam.export_vtk import can_export
    if can_export(ent.result.meta):
        return None
    return run_vtk(ent)


def vtk_tip(ent):
    """The VTK button's tooltip when it opens the run's vtk\\ folder, else
    '' (the caller keeps its own text)."""
    found = vtk_opens_folder(ent)
    return run_vtk_text(found) if found else ''


def open_run_vtk(ent, log=print):
    """Open the run's vtk\\ folder (the VTK button of a run that wrote
    one). Returns the folder, or '' when there is none."""
    found = vtk_opens_folder(ent)
    if not found:
        return ''
    log(f'VTK files written during the run: {found[0]} ({found[1]} files)')
    _open(found[0], log)
    return found[0]


def why_not(kind, ent):
    """Why a disabled button is disabled. A greyed control that says
    nothing is worse than no control: 'Profile' in particular is off for
    every 3D and every planar 2D result."""
    if ent is None:
        return 'Select a result first.'
    dim = ent.dim
    return dict(
        vtk=(SCRATCH_RELEASED if ent.result.meta.get('scratch_released')
             else 'Only a blastFoam run whose case directory still exists '
                  'can be written as VTK.'),
        gif='This result has no recorded frames - tick "Record replay '
            'frames" before the run.',
        summary='This result has no gauges.',
        tsv='This result has no gauges.',
        pngs='This result has no field snapshots.',
        profile=('3D results have no profile export.' if dim == 3 else
                 'Only axisymmetric 2D fields can be remapped into 3D.'),
    ).get(kind, '')


# ── the figure lists the file exports use ────────────────────────────────
def _report_caption(fname, dim):
    """A section heading from the field name, not the file name:
    'blast_2d_pressure.png' used to become the heading
    'blast 2d pressure'."""
    stem = fname.rsplit('.', 1)[0]
    head = f'blast_{dim}d_'
    if stem.startswith(head):
        stem = stem[len(head):]
    stem = stem.replace('_', ' ')
    return stem[:1].upper() + stem[1:]


def png_figures(res, dim, show_mesh=False, title_extra=None,
                drop_note=None, numbers=None):
    """(filename, Figure) for the `pngs` export: the FULL snapshot grid
    that output/plots.py builds, not the single panel on screen.
    `drop_note` is the gauge grid's dropped-gauge footnote (GUI-13 (d);
    None: the figure's own); `numbers` a 1D result's entered gauge
    numbers (GUI-16 (b))."""
    if dim == 1:
        c = charge_label(res.meta)
        return [('blast_1d_results.png',
                 plots.figure_results_1d(
                     res.snapshots, c.eos, c.charge_kg, c.radius_m,
                     title_extra=title_extra)),
                ('blast_1d_gauges.png',
                 plots.figure_gauges_1d(
                     res.gauges, c.charge_kg, c.eos,
                     title_extra=title_extra, numbers=numbers,
                     drop_note=drop_note))]
    builder = plots.figures_fields_2d if dim == 2 else plots.figures_fields_3d
    figs = builder(res.snapshots, res.meta, include_peak=True,
                   show_mesh=show_mesh, title_extra=title_extra)
    figs.append((f'blast_{dim}d_gauges.png',
                 plots.figure_gauges_nd(res.gauges, res.meta,
                                        title_extra=title_extra,
                                        drop_note=drop_note)))
    if dim == 3:
        figs.append(('blast_3d_isosurface.png',
                     plots.figure_isosurfaces_3d(res.snapshots, res.meta,
                                                 title_extra=title_extra)))
    return figs


def report_figures(res, dim, show_mesh=False, title_extra=None,
                   drop_note=None, numbers=None):
    """(caption, Figure) for the HTML report (`drop_note`, `numbers`: as
    `png_figures`)."""
    if dim == 1:
        c = charge_label(res.meta)
        return [('Results', plots.figure_results_1d(
                    res.snapshots, c.eos, c.charge_kg, c.radius_m,
                    title_extra=title_extra)),
                ('Gauge time histories', plots.figure_gauges_1d(
                    res.gauges, c.charge_kg, c.eos,
                    title_extra=title_extra, numbers=numbers,
                    drop_note=drop_note))]
    builder = plots.figures_fields_2d if dim == 2 else plots.figures_fields_3d
    figs = [(_report_caption(n, dim), f)
            for n, f in builder(res.snapshots, res.meta, include_peak=True,
                                show_mesh=show_mesh,
                                title_extra=title_extra)]
    # 'Gauge time histories', not a second 'Gauges' heading duplicating
    # the table section's
    figs.append(('Gauge time histories',
                 plots.figure_gauges_nd(res.gauges, res.meta,
                                        title_extra=title_extra,
                                        drop_note=drop_note)))
    return figs


# ── doing the work ───────────────────────────────────────────────────────
def run_export(kind, ent, target, opts=None, log=print, parent=None,
               on_error=None, open_after=True):
    """Write one export. Safe on a worker thread: it touches no widget,
    and every failure reaches `log`. Returns what was written, or None.

    `opts` may carry `show_mesh`, `title_extra`, `gauge_drop_note` (the
    gauge grid's dropped-gauge footnote, GUI-13 (d)), `gauge_numbers` (a
    1D result's entered gauge numbers for its figure, report and summary,
    GUI-16 (b)), and for `gif` an `anim_scale` / `anim_clim` override of
    the run's own colour range.
    `open_after=False` skips showing a written report / VTK folder
    (`os.startfile`): the model folder writes them unattended (OUT-1).
    """
    opts = opts or {}
    show_mesh = bool(opts.get('show_mesh'))
    title_extra = opts.get('title_extra') or None
    drop_note = opts.get('gauge_drop_note') or None
    numbers = opts.get('gauge_numbers') or None
    res, dim = ent.result, ent.dim
    pre = name_prefix(res)
    try:
        if kind == 'pngs':
            written = []
            for name, fig in png_figures(res, dim, show_mesh, title_extra,
                                         drop_note, numbers):
                if fig is None:            # figure_gauges_nd: no gauges
                    continue
                name = pre + name
                fig.savefig(os.path.join(target, name), dpi=150,
                            bbox_inches='tight')
                log(f'Saved {name}')
                written.append(name)
            return written
        if kind == 'tsv':
            {1: save_gauges_1d, 2: save_gauges_2d,
             3: save_gauges_3d}[dim](res.gauges, target)
            log(f'Saved {target}')
            return target
        if kind == 'fieldcsv':
            from ..output import report as report_mod
            written = report_mod.save_field_csvs(res, dim, target,
                                                 prefix=pre)
            if written:
                log(f'Saved {len(written)} field CSV(s) into {target}')
            else:
                log('No exportable field maps in this result.')
            return written
        if kind == 'report':
            from ..output import report as report_mod
            report_mod.save_html_report(
                res, dim, target,
                figures=report_figures(res, dim, show_mesh, title_extra,
                                       drop_note, numbers),
                # the user's own line wins over the run name for the
                # report's heading
                title=title_extra or ent.label, numbers=numbers)
            log(f'Saved {target}')
            if open_after:
                _open(target, log)
            return target
        if kind == 'summary':
            gauge_summary.save_gauge_summary(summary_rows(res, opts),
                                             target)
            log(f'Saved {target}')
            return target
        if kind == 'vtk':
            from ..solvers.foam.export_vtk import export_vtk
            found = run_vtk(ent)
            try:
                out = export_vtk(target, log=log,
                                 vtk_dir=found[0] if found else None)
            except RuntimeError as exc:
                log(f'VTK export failed: {exc}')
                if on_error is not None:
                    on_error('VTK export', str(exc)[:600])
                return None
            log(f'VTK export done: {out}')
            if open_after:
                _open(out, log)
            return out
        if kind == 'gif':
            write_animation(res.meta, target, show_mesh=show_mesh,
                            title=title_extra,
                            scale=opts.get('anim_scale'),
                            clim=opts.get('anim_clim'))
            log(f'Saved {target}')
            return target
        if kind == 'profile':
            if dim == 1:
                save_profile(res.meta['final_profile'], target)
            else:
                save_profile_2d(res.meta, target)
            log(f'Saved {target}')
            return target
        log(f'Unknown export: {kind}')
    except Exception as exc:                # surfaced to the log, never raised
        log(f'Export failed: {exc}')
    return None


def _open(path, log):
    """Show the user what was written. Absent off Windows, and a folder
    that will not open is a note, not a failure."""
    try:
        os.startfile(path)
    except (OSError, AttributeError) as exc:
        log(f'(could not open {path}: {exc})')
