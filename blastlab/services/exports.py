"""Everything the Results tab writes to disk, with no panel attached.

The toolkit-free half of the export orchestration, shared by both GUIs
(docs/ARCHITECTURE_REVIEW.md section 5, Phase 6; finding F7). Moved
verbatim from `ui/exports.py`, which keeps `pick_target` and `export`
(the Qt file dialogs) and re-exports every name here; the Tk
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


def summary_rows(res):
    """Per-gauge engineering rows. meta['gauges'] is what the user asked
    for; gauges['points'] is where the solver actually put them."""
    return gauge_summary.summarize_gauges(
        res.gauges, requested=res.meta.get('gauges'))


def can(kind, ent):
    """Whether this export can run for this result at all."""
    if ent is None:
        return False
    from ..solvers.foam.export_vtk import can_export
    res, dim, meta = ent.result, ent.dim, ent.result.meta
    has_gauges = bool(res.gauges.get('pressures'))
    return dict(
        vtk=can_export(meta),
        gif=bool(meta.get('frames')),
        summary=has_gauges,
        tsv=has_gauges,
        pngs=bool(res.snapshots),
        profile=(dim == 1 or (dim == 2
                              and meta.get('geometry') == 'axisymmetric')),
    ).get(kind, True)


def why_not(kind, ent):
    """Why a disabled button is disabled. A greyed control that says
    nothing is worse than no control: 'Profile' in particular is off for
    every 3D and every planar 2D result."""
    if ent is None:
        return 'Select a result first.'
    dim = ent.dim
    return dict(
        vtk='Only a blastFoam run whose case directory still exists can '
            'be written as VTK.',
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


def png_figures(res, dim, show_mesh=False, title_extra=None):
    """(filename, Figure) for the `pngs` export: the FULL snapshot grid
    that output/plots.py builds, not the single panel on screen."""
    if dim == 1:
        return [('blast_1d_results.png',
                 plots.figure_results_1d(
                     res.snapshots, res.meta['eos'], res.meta['charge_kg'],
                     res.meta['radius_m'], title_extra=title_extra)),
                ('blast_1d_gauges.png',
                 plots.figure_gauges_1d(
                     res.gauges, res.meta['charge_kg'], res.meta['eos'],
                     title_extra=title_extra))]
    builder = plots.figures_fields_2d if dim == 2 else plots.figures_fields_3d
    figs = builder(res.snapshots, res.meta, include_peak=True,
                   show_mesh=show_mesh, title_extra=title_extra)
    figs.append((f'blast_{dim}d_gauges.png',
                 plots.figure_gauges_nd(res.gauges, res.meta,
                                        title_extra=title_extra)))
    if dim == 3:
        figs.append(('blast_3d_isosurface.png',
                     plots.figure_isosurfaces_3d(res.snapshots, res.meta,
                                                 title_extra=title_extra)))
    return figs


def report_figures(res, dim, show_mesh=False, title_extra=None):
    """(caption, Figure) for the HTML report."""
    if dim == 1:
        return [('Results', plots.figure_results_1d(
                    res.snapshots, res.meta['eos'], res.meta['charge_kg'],
                    res.meta['radius_m'], title_extra=title_extra)),
                ('Gauge time histories', plots.figure_gauges_1d(
                    res.gauges, res.meta['charge_kg'], res.meta['eos'],
                    title_extra=title_extra))]
    builder = plots.figures_fields_2d if dim == 2 else plots.figures_fields_3d
    figs = [(_report_caption(n, dim), f)
            for n, f in builder(res.snapshots, res.meta, include_peak=True,
                                show_mesh=show_mesh,
                                title_extra=title_extra)]
    # 'Gauge time histories', not a second 'Gauges' heading duplicating
    # the table section's
    figs.append(('Gauge time histories',
                 plots.figure_gauges_nd(res.gauges, res.meta,
                                        title_extra=title_extra)))
    return figs


# ── doing the work ───────────────────────────────────────────────────────
def run_export(kind, ent, target, opts=None, log=print, parent=None,
               on_error=None):
    """Write one export. Safe on a worker thread: it touches no widget,
    and every failure reaches `log`. Returns what was written, or None.

    `opts` may carry `show_mesh`, `title_extra`, and for `gif` an
    `anim_scale` / `anim_clim` override of the run's own colour range.
    """
    opts = opts or {}
    show_mesh = bool(opts.get('show_mesh'))
    title_extra = opts.get('title_extra') or None
    res, dim = ent.result, ent.dim
    pre = name_prefix(res)
    try:
        if kind == 'pngs':
            written = []
            for name, fig in png_figures(res, dim, show_mesh, title_extra):
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
                figures=report_figures(res, dim, show_mesh, title_extra),
                # the user's own line wins over the run name for the
                # report's heading
                title=title_extra or ent.label)
            log(f'Saved {target}')
            _open(target, log)
            return target
        if kind == 'summary':
            gauge_summary.save_gauge_summary(summary_rows(res), target)
            log(f'Saved {target}')
            return target
        if kind == 'vtk':
            from ..solvers.foam.export_vtk import export_vtk
            try:
                out = export_vtk(target, log=log)
            except RuntimeError as exc:
                log(f'VTK export failed: {exc}')
                if on_error is not None:
                    on_error('VTK export', str(exc)[:600])
                return None
            log(f'VTK export done: {out}')
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
