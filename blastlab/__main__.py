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
    ap.add_argument('--case', metavar='FILE',
                    help='case JSON to open in the GUI at startup')
    args = ap.parse_args()

    if args.cli:
        from .cli import main as cli_main
        cli_main(args.cli)
    else:
        from .gui.app import main as gui_main
        gui_main(case_file=args.case)


if __name__ == '__main__':
    main()
