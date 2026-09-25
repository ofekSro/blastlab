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
from ..output import hd13, plots


def default_report_path(case_path):
    """Where `--hd13` writes the report when not told: beside the case
    file, `<case>_hd13.html`."""
    base = os.path.splitext(case_path)[0]
    return base + '_hd13.html'


def assess(case, report=None):
    """Validate `case`, run it and build the report's figures.

    `report` is the `ValidationReport` of `case` when the caller has
    already made one (the CLI prints it before anything is computed);
    otherwise `case` is validated here. Raises `ValueError`
    ('refusing to run: <errors joined by "; ">') if it is refused.

    Returns the bundle `write_report` takes: a dict with the `case`, the
    `assessment.run` output under `out`, and the (caption, Figure) list
    under `figures`.
    """
    rep = assessment.validate(case) if report is None else report
    if not rep.ok:
        raise ValueError('refusing to run: ' + '; '.join(rep.errors))

    out = assessment.run(case)
    figures = []
    if out['confined'] is not None:
        figures.append(('Chamber', plots.figure_deflagration(out['confined'])))
    if out['unconfined'] is not None:
        figures.append(('In the open',
                        plots.figure_unconfined(out['unconfined'])))
    if out['sdof'] is not None:
        figures.append(('Structural response',
                        plots.figure_sdof_response(out['sdof'],
                                                   out['component'])))
    if out['thermal'] is not None or out['radiation']:
        t = out['confined']['t'] if out['confined'] else []
        q = out['thermal']['q'] if out['thermal'] else []
        Ts = out['thermal']['T_surface'] if out['thermal'] else None
        if len(t):
            figures.append(('Heat', plots.figure_thermal(
                t, q, Ts, out['radiation'])))
    return dict(case=case, out=out, figures=figures)


def write_report(bundle, out_path):
    """Write the HD 1.3 HTML report of an `assess` bundle to `out_path`;
    returns `out_path`."""
    case, out = bundle['case'], bundle['out']
    hd13.save_hd13_report(
        out_path, prop=out['prop'], confined=out['confined'],
        unconfined=out['unconfined'], sdof=out['sdof'],
        component=out['component'], thermal=out['thermal'],
        radiation=out['radiation'], figures=bundle['figures'],
        sensitivity=out['sensitivity'],
        sensitivity_note=out['sensitivity_note'],
        verdict=out['verdict'], qd=out['qd'],
        title=case.name or None)
    return out_path
