"""Entry point: `python -m blastlab` starts the GUI;
`python -m blastlab --cli 1d|2d|3d --runs-dir DIR --model NAME` runs the
prompt-based CLI into the model folder DIR\\NAME\\ (OUT-1).

The GUI is the PySide6 one (`blastlab.ui`), and `--qt` is accepted as a
no-op so the shortcuts written during the port keep working.

`--tk` opens the Tkinter original (`blastlab.gui`), which is **kept
indefinitely by owner decision (2026-09-18)**: Qt is the main GUI, and
Tk stays as the way back if it is ever needed. It is not deprecated and
it has no removal date - do not delete it, and do not describe it as
being retired, without the owner saying so."""

import argparse


def main():
    ap = argparse.ArgumentParser(
        prog='blastlab',
        description='Blast wave solvers (1D/2D/3D) with GUI and CLI.')
    ap.add_argument('--cli', metavar='DIM', choices=['1d', '2d', '3d'],
                    help='run the interactive prompt workflow instead of '
                         'the GUI (1d, 2d or 3d)')
    ap.add_argument('--solver', choices=['native', 'blastfoam'],
                    default='native',
                    help='CLI solver backend: the built-in numpy solvers '
                         'or blastFoam via WSL (default: native)')
    ap.add_argument('--case', metavar='FILE',
                    help='case JSON to open in the GUI at startup')
    ap.add_argument('--tk', action='store_true',
                    help='launch the Tkinter GUI (blastlab.gui) instead '
                         'of the default PySide6 one; kept as the way '
                         'back, with no removal planned')
    ap.add_argument('--qt', action='store_true',
                    help=argparse.SUPPRESS)   # now the default; accepted
                                              # so old shortcuts keep working
    ap.add_argument('--clean-foam-runs', action='store_true',
                    help='list and delete the WSL-side blastFoam run '
                         'directories, then exit (runs still solving '
                         'are skipped unless --force)')
    ap.add_argument('--force', action='store_true',
                    help='with --clean-foam-runs: delete run '
                         'directories even while their solver is alive')
    ap.add_argument('--older-than', metavar='DAYS', type=float,
                    help='with --clean-foam-runs: only runs untouched '
                         'for more than DAYS')
    ap.add_argument('--keep-gb', metavar='N', type=float,
                    help='with --clean-foam-runs: delete oldest runs '
                         'until the runs root fits under N GB')
    ap.add_argument('--reap-foam-runs', action='store_true',
                    help='kill WSL-side blastFoam solvers whose owning '
                         'blastlab process is gone (keeps the run '
                         'directories), then exit')
    ap.add_argument('--load-foam-run', metavar='DIR',
                    help='load a finished blastFoam run directory '
                         '(name under /root/blastlab_runs, or a full '
                         'path) and report its contents, then exit')
    ap.add_argument('--hd13', metavar='CASE',
                    help='run an HD 1.3 deflagration assessment from a '
                         'case file and write its HTML report and SBEDS '
                         'loads into the model folder, then exit. No WSL '
                         'and no GUI: the whole HD1.3 track is 0-D plus '
                         'closed-form models')
    ap.add_argument('--hd13-new', metavar='CASE',
                    help='write a starter HD 1.3 case file and exit')
    ap.add_argument('--hd13-wall-export', metavar='CASE',
                    help='write the HD1-13 wall-load traces (G1, plane-max '
                         'x gamma 1.24/1.40) as two-column SBEDS CSVs '
                         'into <MODEL>\\wall_loads\\, with clearing if the '
                         'case asks for it, then exit')
    # OUT-1: every entry that produces output writes <runs-dir>\<model>\
    ap.add_argument('--runs-dir', metavar='DIR',
                    help='the runs folder; required by --cli, --hd13 and '
                         '--hd13-wall-export')
    ap.add_argument('--model', metavar='NAME',
                    help='the model name: everything the run produces '
                         'goes into <runs-dir>\\<NAME>\\ (asked before an '
                         'existing model is overwritten); required with '
                         '--runs-dir')
    args = ap.parse_args()
    for flag, value in (('--cli', args.cli), ('--hd13', args.hd13),
                        ('--hd13-wall-export', args.hd13_wall_export)):
        if value and not (args.runs_dir and args.model):
            ap.error(f'{flag} needs --runs-dir DIR and --model NAME '
                     f'(OUT-1: every run writes <runs-dir>\\<model>\\)')

    # These two need neither the WSL probe below nor any Qt import.
    if args.hd13_new:
        from .output.cli_hd13 import write_starter_case
        print(write_starter_case(args.hd13_new))
        return
    if args.hd13:
        from .output.cli_hd13 import run_and_report
        run_and_report(args.hd13, args.runs_dir, args.model)
        return
    if args.hd13_wall_export:
        from .output.cli_hd13 import wall_export
        wall_export(args.hd13_wall_export, args.runs_dir, args.model)
        return

    # N21 follow-up: the hardware probe is process-local, and until this
    # call existed only the GUI restored it. Every other entry point
    # sized its cases against FOAM_VM_GB_ASSUMED (4 GB) and refused
    # perfectly runnable cases on a big machine. Idempotent gap-fill.
    from .solvers.foam.env import prime_from_settings
    prime_from_settings()

    if args.clean_foam_runs:
        from .solvers.foam.cli_run import clean_runs
        clean_runs(force=args.force, older_than_days=args.older_than,
                   keep_gb=args.keep_gb)
        return
    if args.reap_foam_runs:
        from .solvers.foam.cli_run import reap_foam_runs
        reap_foam_runs()
        return
    if args.load_foam_run:
        from .solvers.foam.cli_run import load_and_report
        load_and_report(args.load_foam_run)
        return
    if args.cli:
        from .cli import main as cli_main
        cli_main(args.cli, solver=args.solver, runs_dir=args.runs_dir,
                 model=args.model)
    elif args.tk:
        from .gui.app import main as gui_main
        gui_main(case_file=args.case)
    else:
        from .ui.app import main as qt_main
        qt_main(case_file=args.case)


if __name__ == '__main__':
    main()
