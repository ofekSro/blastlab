"""Interactive CLI flow for `python -m blastlab --cli DIM --solver
blastfoam`. Kept separate from cli.py/legacy so the byte-pinned native
prompt flow stays untouched; the shared prompt helpers are reused."""

from . import env
from .materials import MATERIAL_NAMES


def _unavailable():
    raise SystemExit(
        "  The blastFoam backend is unavailable. Verify that WSL "
        f"distro '{env.WSL_DISTRO}' exists and that\n  "
        f"{env.FOAM_BASHRC} sources a build providing: "
        + ", ".join(env.NEEDED_TOOLS))


def run(dim):
    dim = str(dim).lower().lstrip('-')[0]
    print("blastlab - blastFoam (WSL) backend")
    print("  Checking WSL blastFoam availability...")
    ok, detail = env.check_available()
    print(f"  {detail}")
    if not ok:
        _unavailable()
    if dim == '1':
        return _run_1d()
    raise SystemExit(
        f"  The blastFoam CLI workflow for {dim}D cases is not "
        f"implemented yet.")


def _run_1d():
    from ...cli import _ask, _ask_choice, _ask_gauges, _positive
    from ...core.case import Case1D, validate_case
    from ...output.gauges import save_gauges_1d
    from ...core.profiles import save_profile
    from ..hooks import ConsoleHooks

    print()
    radius = _ask("Domain radius [m]", default=10.0,
                  validator=_positive("Radius"))
    charge = _ask("Charge weight [kg]", default=1.0,
                  validator=_positive("Charge"))
    material = _ask_choice("Charge material", list(MATERIAL_NAMES), 'TNT')
    cell = _ask("Cell size [m]", default=0.01,
                validator=_positive("Cell size"))
    n_snap = int(_ask("Snapshots", default=5, cast=int,
                      validator=_positive("Snapshots")))
    gauges = _ask_gauges(radius)
    gauge_file = _ask("Gauge TSV file", default='gauges.txt', cast=str)
    profile_out = _ask("Profile out (.txt, '-' = skip)",
                       default='blast_profile.txt', cast=str)
    profile_out = None if profile_out.strip() in ('-', '') else profile_out

    case = Case1D(radius_m=radius, charge_kg=charge, cell_size_m=cell,
                  n_snapshots=n_snap, gauge_radii=gauges,
                  gauge_file=gauge_file, profile_file=profile_out,
                  solver='blastfoam', material=material)
    rep = validate_case(case)
    for msg in rep.notes:
        print(f"  [note] {msg}")
    for msg in rep.warnings:
        print(f"  [warn] {msg}")
    if not rep.ok:
        raise SystemExit("  Invalid case:\n    "
                         + "\n    ".join(rep.errors))

    from .backend import solve_1d_foam
    res = solve_1d_foam(case, ConsoleHooks(1))

    if gauges:
        save_gauges_1d(res.gauges, gauge_file)
    if profile_out:
        save_profile(res.meta['final_profile'], profile_out)

    _show_plots_1d(res, case)
    return res


def _show_plots_1d(res, case):
    import matplotlib
    if matplotlib.get_backend().lower().startswith('agg'):
        return
    from ...output.plots import figure_results_1d, figure_gauges_1d
    from ...output.pyplot_bridge import adopt_figure
    import matplotlib.pyplot as plt
    adopt_figure(figure_results_1d(res.snapshots, 'JWL',
                                   case.charge_kg, case.radius_m))
    if res.gauges['radii']:
        adopt_figure(figure_gauges_1d(res.gauges, case.charge_kg, 'JWL'))
    plt.show()
