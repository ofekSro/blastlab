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
    return {'1': _run_1d, '2': _run_2d, '3': _run_3d}[dim]()


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


def clean_runs(assume_yes=False):
    """List and (after confirmation) delete the WSL-side blastFoam run
    directories (`--clean-foam-runs`). Big 3D runs are kept on disk for
    post-mortem inspection, so they accumulate."""
    import subprocess
    print(f"blastFoam run directories in WSL ({env.RUNS_ROOT}):")
    res = subprocess.run(
        env.wsl_argv(f'du -sh {env.RUNS_ROOT}/*/ 2>/dev/null'),
        capture_output=True, text=True, timeout=120,
        stdin=subprocess.DEVNULL, creationflags=env.CREATE_NO_WINDOW)
    listing = (res.stdout or '').strip()
    if res.returncode != 0 or not listing:
        print("  (none)")
        return
    print('\n'.join(f'  {ln}' for ln in listing.splitlines()))
    if not assume_yes:
        try:
            raw = input("Delete ALL of these? [y/N]: ").strip().lower()
        except EOFError:
            raw = ''
        if raw not in ('y', 'yes'):
            print("  Nothing deleted.")
            return
    subprocess.run(
        env.wsl_argv(f'rm -rf {env.RUNS_ROOT}/*/'),
        capture_output=True, timeout=300,
        stdin=subprocess.DEVNULL, creationflags=env.CREATE_NO_WINDOW)
    print("  Deleted.")


def _validate_or_exit(case):
    from ...core.case import validate_case
    rep = validate_case(case)
    for msg in rep.notes:
        print(f"  [note] {msg}")
    for msg in rep.warnings:
        print(f"  [warn] {msg}")
    if not rep.ok:
        raise SystemExit("  Invalid case:\n    "
                         + "\n    ".join(rep.errors))


def _run_2d():
    from ...cli import (_ask, _ask_choice, _ask_gauges_2d, _positive)
    from ...core.case import Case2D
    from ...output.gauges import save_gauges_2d
    from ...output.animation import write_animation
    from ...core.profiles import save_profile_2d
    from ..hooks import ConsoleHooks

    print()
    geometry = _ask_choice("Geometry", ['axisymmetric', 'planar'],
                           'axisymmetric')
    axisym = geometry == 'axisymmetric'
    Lx = _ask("Domain Lx [m]", default=10.0, validator=_positive("Lx"))
    Ly = _ask("Domain Ly [m]", default=10.0, validator=_positive("Ly"))
    charge = _ask("Charge [kg]" if axisym else "Charge [kg per metre]",
                  default=1.0, validator=_positive("Charge"))
    material = _ask_choice("Charge material", list(MATERIAL_NAMES), 'TNT')
    cell = _ask("Cell size [m]", default=0.025,
                validator=_positive("Cell size"))
    x0 = 0.0 if axisym else _ask("Burst x [m]", default=Lx / 2.0)
    y0 = _ask("Burst height y [m]", default=Ly / 2.0)
    n_snap = int(_ask("Snapshots", default=6, cast=int,
                      validator=_positive("Snapshots")))
    gauges = _ask_gauges_2d(Lx, Ly, x0, y0)
    gauge_file = _ask("Gauge TSV file", default='gauges_2d.txt', cast=str)
    anim = _ask("Animation gif ('-' = skip)",
                default='blast_2d_animation.gif', cast=str)
    anim = None if anim.strip() in ('-', '') else anim
    profile_out = None
    if axisym:
        profile_out = _ask("Profile out (.npz, '-' = skip)", default='-',
                           cast=str)
        profile_out = (None if profile_out.strip() in ('-', '')
                       else profile_out)

    case = Case2D(geometry=geometry, Lx=Lx, Ly=Ly, cell_size_m=cell,
                  charge=charge, center=(x0, y0), gauges=gauges,
                  n_snapshots=n_snap, gauge_file=gauge_file,
                  anim_file=anim, record_frames=150 if anim else 0,
                  profile_file=profile_out,
                  solver='blastfoam', material=material)
    _validate_or_exit(case)

    from .backend import solve_2d_foam
    res = solve_2d_foam(case, ConsoleHooks(2))

    if gauges:
        save_gauges_2d(res.gauges, gauge_file)
    if anim and res.meta.get('frames'):
        write_animation(res.meta, anim)
    if profile_out:
        save_profile_2d(res.meta, profile_out)
    return res


def _run_3d():
    from ...cli import (_ask, _ask_choice, _ask_gauges_3d, _positive)
    from ...core.case import Case3D
    from ...output.gauges import save_gauges_3d
    from ...output.animation import write_animation
    from ..hooks import ConsoleHooks

    print()
    Lx = _ask("Domain Lx [m]", default=10.0, validator=_positive("Lx"))
    Ly = _ask("Domain Ly [m]", default=10.0, validator=_positive("Ly"))
    Lz = _ask("Domain Lz [m]", default=10.0, validator=_positive("Lz"))
    charge = _ask("Charge [kg]", default=1.0,
                  validator=_positive("Charge"))
    material = _ask_choice("Charge material", list(MATERIAL_NAMES), 'TNT')
    cell = _ask("Cell size [m]", default=0.1,
                validator=_positive("Cell size"))
    x0 = _ask("Burst x [m]", default=Lx / 2.0)
    y0 = _ask("Burst y [m]", default=Ly / 2.0)
    z0 = _ask("Burst z [m]", default=Lz / 2.0)
    t_end = _ask("End time [s] (0 = auto)", default=0.0)
    n_snap = int(_ask("Snapshots", default=6, cast=int,
                      validator=_positive("Snapshots")))
    gauges = _ask_gauges_3d(Lx, Ly, Lz, x0, y0, z0)
    gauge_file = _ask("Gauge TSV file", default='gauges_3d.txt', cast=str)
    anim = _ask("Animation gif ('-' = skip)",
                default='blast_3d_animation.gif', cast=str)
    anim = None if anim.strip() in ('-', '') else anim

    case = Case3D(Lx=Lx, Ly=Ly, Lz=Lz, cell_size_m=cell, charge=charge,
                  center=(x0, y0, z0), t_end=t_end, gauges=gauges,
                  n_snapshots=n_snap, gauge_file=gauge_file,
                  anim_file=anim, record_frames=150 if anim else 0,
                  solver='blastfoam', material=material)
    _validate_or_exit(case)

    from .backend import solve_3d_foam
    res = solve_3d_foam(case, ConsoleHooks(3))

    if gauges:
        save_gauges_3d(res.gauges, gauge_file)
    if anim and res.meta.get('frames'):
        write_animation(res.meta, anim)
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
