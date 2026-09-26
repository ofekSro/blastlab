"""The HD 1.3 assessment as a service: validate, run, build the report's
figures, write the report. No printing, no dialogs.

docs/ARCHITECTURE_REVIEW.md section 5, Phase 7. Moved from
`output/cli_hd13.run_and_report`, which is now the command-line wrapper
around these calls (it prints the validation report and the headline
numbers, and turns a refusal into `SystemExit`); the Qt window's
`_run_hd13` calls them directly.

    bundle = assess(case)                 # ValueError if validate refuses
    write_report(bundle, out_path)        # -> out_path

No GUI toolkit, no pyplot and no VTK is imported here: the figures are
the OO-matplotlib ones of `output/plots.py`.
"""

import os

from ..core import assessment
from ..output import hd13, load_csv, plots


#: OUT-1 (plan sec. 2.2): the HD 1.3 rows of a model folder
REPORT_NAME = 'hd13_report.html'
LOADS_NAME = 'hd13_loads'
WALL_LOADS_NAME = 'wall_loads'


def assess(case, report=None) -> dict:
    """Validate `case`, run it and build the report's figures.

    `report` is the `ValidationReport` of `case` when the caller has
    already made one (the CLI prints it before anything is computed);
    otherwise `case` is validated here. Raises `ValueError`
    ('refusing to run: <errors joined by "; ">') if it is refused.

    Returns the bundle `write_report` takes: a dict with the `case`, the
    `assessment.run` output under `out`, and the (caption, Figure) list
    under `figures`.
    """
    if report is None:
        report = assessment.validate(case)
    if not report.ok:
        raise ValueError('refusing to run: ' + '; '.join(report.errors))

    out = assessment.run(case)
    confined, thermal = out['confined'], out['thermal']
    figures = []
    if confined is not None:
        figures.append(('Chamber', plots.figure_deflagration(confined)))
    if out['unconfined'] is not None:
        figures.append(('In the open',
                        plots.figure_unconfined(out['unconfined'])))
    # HD1-16: no structural-response figure; the load goes to SBEDS.
    # The heat figure is drawn on the chamber's time axis: with no
    # confined result there is no axis, so no heat figure.
    if thermal is not None or out['radiation']:
        t = confined['t'] if confined else []
        q = thermal['q'] if thermal else []
        T_surface = thermal['T_surface'] if thermal else None
        if len(t):
            figures.append(('Heat', plots.figure_thermal(
                t, q, T_surface, out['radiation'])))
    return dict(case=case, out=out, figures=figures)


def write_report(bundle: dict, out_path: str, loads_dir=None) -> str:
    """Write the HD 1.3 HTML report of an `assess` bundle to `out_path`;
    returns `out_path`.

    Then the chamber load as SBEDS CSVs into `loads_dir` (OUT-1: the
    model folder's `hd13_loads`), else `<report stem>_loads/` (HD1-16,
    `output/load_csv.export_hd13`); what was written, and any "record
    ends while the load is still active" message, is put in
    `bundle['loads']` for the caller to show."""
    case, out = bundle['case'], bundle['out']
    hd13.save_hd13_report(
        out_path, prop=out['prop'], confined=out['confined'],
        unconfined=out['unconfined'], thermal=out['thermal'],
        radiation=out['radiation'], figures=bundle['figures'],
        sensitivity=out['sensitivity'],
        sensitivity_note=out['sensitivity_note'], qd=out['qd'],
        title=case.name or None)
    bundle['loads'] = load_csv.export_hd13(out, out_path,
                                           case_name=case.name,
                                           out_dir=loads_dir)
    return out_path


def run_into_model_folder(case, target, report=None, log=print) -> dict:
    """OUT-1: one HD 1.3 assessment into a prepared model folder
    (`model_folder.Target`), the same for the Qt window and `--hd13`.

    The case is saved as `<MODEL>\\MODEL.json` and the assessment is made
    from the case read back from it; then `hd13_report.html`,
    `hd13_loads\\` and `manifest.json`. Returns the `assess` bundle, with
    the report path under `report`. A failure still leaves MODEL.json and
    a manifest whose `stop_reason` says why, and is re-raised."""
    from . import model_folder as mf
    info = mf.run_info(target)
    case_path = os.path.join(target.folder, mf.CASE_FILE)
    try:
        assessment.save_case(case, case_path)
        bundle = assess(assessment.load_case(case_path), report)
        write_to_model_folder(bundle, target.folder, case_path, info,
                              log=log)
        return bundle
    except Exception as exc:
        failed = hd13_manifest(target.folder, case_path, info)
        failed['stop_reason'] = mf.headline(exc)
        mf.write_manifest(failed, target.folder)
        raise


def write_to_model_folder(bundle: dict, folder: str, case_path: str,
                          info: dict, log=print) -> dict:
    """OUT-1: the HD 1.3 rows of a model folder, after `assess`:
    `hd13_report.html`, `hd13_loads\\`, then `manifest.json` (`solver`
    "hd13", `dim` 0, `wsl_scratch` null). `case_path` is the folder's
    MODEL.json, already written. Returns the manifest. Raises what the
    report writer raises (the caller shows it); the manifest itself goes
    through `model_folder.write_manifest`, which never raises."""
    from . import model_folder as mf
    report = write_report(bundle, os.path.join(folder, REPORT_NAME),
                          loads_dir=os.path.join(folder, LOADS_NAME))
    manifest = hd13_manifest(folder, case_path, info)
    manifest['stop_reason'] = (bundle['out'].get('confined') or {}).get(
        'stop_reason')
    err = mf.write_manifest(manifest, folder)
    if err:
        log(f'[warn] model folder: could not write '
            f'{mf.MANIFEST_FILE}: {err}')
    bundle['report'] = report
    return manifest


def hd13_manifest(folder: str, case_path: str, info: dict) -> dict:
    """The manifest of an HD 1.3 model folder (plan sec. 2.2 keys): no
    solver steps, no cells, no WSL scratch."""
    from . import model_folder as mf
    info = dict(info or {})
    manifest = mf.new_manifest(None, 0, folder, info)
    manifest.update(solver='hd13', dim=0,
                    case_file=os.path.basename(case_path),
                    finished=mf.now_iso())
    manifest['outputs'] = mf.list_outputs(folder)
    return manifest
