"""Entry point: `python -m blastlab` starts the GUI;
`python -m blastlab --cli 1d|2d|3d` runs the prompt-based CLI."""

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
    ap.add_argument('--clean-foam-runs', action='store_true',
                    help='list and delete the WSL-side blastFoam run '
                         'directories, then exit')
    ap.add_argument('--load-foam-run', metavar='DIR',
                    help='load a finished blastFoam run directory '
                         '(name under /root/blastlab_runs, or a full '
                         'path) and report its contents, then exit')
    args = ap.parse_args()

    if args.clean_foam_runs:
        from .solvers.foam.cli_run import clean_runs
        clean_runs()
        return
    if args.load_foam_run:
        from .solvers.foam.cli_run import load_and_report
        load_and_report(args.load_foam_run)
        return
    if args.cli:
        from .cli import main as cli_main
        cli_main(args.cli, solver=args.solver)
    else:
        from .gui.app import main as gui_main
        gui_main(case_file=args.case)


if __name__ == '__main__':
    main()
