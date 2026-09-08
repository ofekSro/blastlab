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


def reap_foam_runs():
    """`--reap-foam-runs`: kill WSL solvers whose owning Python process
    is gone (see env.reap_orphans), without deleting anything."""
    reaped = env.reap_orphans(log=print)
    print(f"  Reaped {len(reaped)} orphaned solver(s)."
          if reaped else "  No orphaned solvers found.")
    return reaped


def _human(n):
    if n is None:
        return '?'
    n = float(n)
    for unit in ('B', 'K', 'M', 'G', 'T'):
        if n < 1024 or unit == 'T':
            return f'{n:.0f}{unit}' if unit == 'B' else f'{n:.1f}{unit}'
        n /= 1024.0


def clean_runs(assume_yes=False, force=False, older_than_days=None,
               keep_gb=None):
    """List and (after confirmation) delete the WSL-side blastFoam run
    directories (`--clean-foam-runs`). Big 3D runs are kept on disk for
    post-mortem inspection, so they accumulate.

    Runs whose solver is still alive are listed but skipped - deleting a
    case dir out from under a running solve loses that whole result -
    unless `force`. Orphans (alive in WSL, owning process gone) are
    reaped first so their directories become collectable. With
    `older_than_days` / `keep_gb` only the runs the age/size policy picks
    (env.cleanup_policy, nothing kept for recency) are deleted."""
    import time
    print(f"blastFoam run directories in WSL ({env.RUNS_ROOT}):")
    env.reap_orphans(log=print)
    dirs = env.run_dirs()
    if not dirs:
        print("  (none)")
        return
    info = env.run_info(dirs)
    sizes = {d: _human(info.get(d, {}).get('bytes')) for d in dirs}
    alive = env.runs_alive(dirs)
    policy = older_than_days is not None or keep_gb is not None
    chosen = None
    if policy:
        records = [dict(dir=d, bytes=info.get(d, {}).get('bytes'),
                        mtime=info.get(d, {}).get('mtime'),
                        alive=alive.get(d)) for d in dirs]
        chosen = set(env.cleanup_policy(
            records, time.time(),
            max_bytes=None if keep_gb is None else keep_gb * 1024 ** 3,
            max_age_s=None if older_than_days is None
            else older_than_days * 86400.0,
            keep_recent=0))
    victims, skipped = [], []
    now = time.time()
    for d in dirs:
        live, note = alive.get(d), ''
        mt = info.get(d, {}).get('mtime')
        age = f'{(now - mt) / 86400:.1f} d' if mt else '?'
        if live and force:
            note = '  <- RUNNING, deleted anyway (--force)'
        elif live:
            note = '  <- RUNNING, skipped'
        elif live is None and not force:
            note = '  <- state unknown (WSL did not answer), skipped'
        elif policy and d not in chosen:
            note = '  <- kept by the age/size policy'
        take = force or (live is False and (not policy or d in chosen))
        (victims if take else skipped).append(d)
        print(f"  {sizes.get(d, '?'):>7}  {age:>7}  "
              f"{d.rsplit('/', 1)[-1]}{note}")
    if not victims:
        print(f"  Nothing to delete ({len(skipped)} run(s) skipped; "
              f"--force overrides).")
        return
    if not assume_yes:
        try:
            raw = input(f"Delete {len(victims)} of these? "
                        f"[y/N]: ").strip().lower()
        except EOFError:
            raw = ''
        if raw not in ('y', 'yes'):
            print("  Nothing deleted.")
            return
    env.delete_runs(victims)
    print(f"  Deleted {len(victims)} of {len(dirs)} run director"
          f"{'y' if len(victims) == 1 else 'ies'}."
          + (f"  {len(skipped)} skipped." if skipped else ''))


def load_and_report(case_dir):
    """`--load-foam-run`: post-mortem load + summary (no re-run)."""
    from ..hooks import ConsoleHooks
    from .postmortem import load_run, list_runs
    if case_dir in ('list', '-'):
        runs = list_runs(check_alive=True)
        print(f"blastFoam runs in {env.RUNS_ROOT}:")
        for name, _unc, alive in runs or []:
            print(f"  {name}" + ('  [running]' if alive else ''))
        if not runs:
            print("  (none)")
        return None
    res = load_run(case_dir, ConsoleHooks(1))
    dim = 1 if 'radius_m' in res.meta else (3 if 'z_c' in res.meta else 2)
    print(f"  Loaded {dim}D result from {res.meta['case_dir']}")
    print(f"  Snapshots : {len(res.snapshots)}"
          f"  ({', '.join(list(res.snapshots)[:3])}...)")
    n_g = len(res.gauges.get('points', res.gauges.get('radii', [])))
    print(f"  Gauges    : {n_g}")
    if res.meta.get('peak_source'):
        print(f"  Peak maps : {res.meta['peak_source']}")
    return res


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
    anim_mesh = bool(anim) and _ask_choice(
        "Draw the mesh on the animation?", ['no', 'yes'], 'no') == 'yes'
    profile_out = None
    if axisym:
        profile_out = _ask("Profile out (.npz, '-' = skip)", default='-',
                           cast=str)
        profile_out = (None if profile_out.strip() in ('-', '')
                       else profile_out)

    case = Case2D(geometry=geometry, Lx=Lx, Ly=Ly, cell_size_m=cell,
                  charge=charge, center=(x0, y0), gauges=gauges,
                  n_snapshots=n_snap, gauge_file=gauge_file,
                  anim_file=anim, anim_mesh=anim_mesh,
                  record_frames=150 if anim else 0,
                  profile_file=profile_out,
                  solver='blastfoam', material=material)
    _validate_or_exit(case)

    from .backend import solve_2d_foam
    res = solve_2d_foam(case, ConsoleHooks(2))

    if gauges:
        save_gauges_2d(res.gauges, gauge_file)
    if anim and res.meta.get('frames'):
        write_animation(res.meta, anim, show_mesh=anim_mesh)
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
    anim_mesh = bool(anim) and _ask_choice(
        "Draw the mesh on the animation?", ['no', 'yes'], 'no') == 'yes'

    case = Case3D(Lx=Lx, Ly=Ly, Lz=Lz, cell_size_m=cell, charge=charge,
                  center=(x0, y0, z0), t_end=t_end, gauges=gauges,
                  n_snapshots=n_snap, gauge_file=gauge_file,
                  anim_file=anim, anim_mesh=anim_mesh,
                  record_frames=150 if anim else 0,
                  solver='blastfoam', material=material)
    _validate_or_exit(case)

    from .backend import solve_3d_foam
    res = solve_3d_foam(case, ConsoleHooks(3))

    if gauges:
        save_gauges_3d(res.gauges, gauge_file)
    if anim and res.meta.get('frames'):
        write_animation(res.meta, anim, show_mesh=anim_mesh)
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
