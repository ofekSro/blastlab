"""Interactive prompt-based CLI: the historical blast1d/2d/3d setup
flows, deduplicated. `main('1d'|'2d'|'3d')` runs the same
prompt -> solve -> save -> plot pipeline the standalone scripts always had.
"""

import numpy as np
from matplotlib import animation

from .core.constants import CELLS_WARN, CELLS_REFUSE
from .core.profiles import load_profile, load_profile_2d



def _ask(question, default=None, cast=float, validator=None):
    """Prompt the user for a single value (same behaviour as blast1d/2d)."""
    hint = f" [{default}]" if default is not None else ""
    while True:
        try:
            raw = input(f"  {question}{hint}: ").strip()
        except EOFError:
            print()
            if default is None:
                raise
            return default
        if raw == '':
            if default is None:
                print("    A value is required.")
                continue
            return default
        try:
            val = cast(raw)
        except (ValueError, TypeError):
            print(f"    Invalid input - expected {cast.__name__}.")
            continue
        if validator is not None:
            err = validator(val)
            if err:
                print(f"    {err}")
                continue
        return val


def _positive(label):
    return lambda v: None if v > 0 else f"{label} must be > 0."


def _ask_eos(default='idealGas'):
    """Robust EOS prompt. Accepts JWL / jwl / j / idealGas / ideal / ig / i."""
    while True:
        try:
            raw = input(f"  Equation of state (JWL / idealGas) [{default}]: ").strip()
        except EOFError:
            print()
            return default
        if raw == '':
            return default
        s = raw.lower()
        if s in ('jwl', 'j'):
            return 'JWL'
        if s in ('idealgas', 'ideal', 'ig', 'i'):
            return 'idealGas'
        print(f"    Unknown EOS '{raw}'. Use 'JWL' or 'idealGas'.")


def _ask_choice(question, choices, default):
    """Prompt for one of `choices` (prefix matching, case-insensitive)."""
    lbl = " / ".join(choices)
    while True:
        try:
            raw = input(f"  {question} ({lbl}) [{default}]: ").strip().lower()
        except EOFError:
            print()
            return default
        if raw == '':
            return default
        hits = [ch for ch in choices if ch.lower().startswith(raw)]
        if len(hits) == 1:
            return hits[0]
        print(f"    Please answer one of: {lbl}")


def _ask_gauges(radius_m, default_step=1.0):
    """
    Space-separated list of gauge radii. Default: one gauge every `default_step`
    metres up to the domain radius (inclusive). All gauges must be in (0, radius].
    """
    eps = 1e-9
    default_gauges = [float(g) for g in
                      np.arange(default_step, radius_m + eps, default_step)]
    if not default_gauges:
        default_gauges = [radius_m / 2.0]

    if len(default_gauges) > 5:
        d_lbl = (f"{default_gauges[0]:g}, {default_gauges[1]:g}, ..., "
                 f"{default_gauges[-1]:g} m  (step {default_step:g} m, "
                 f"{len(default_gauges)} gauges)")
    else:
        d_lbl = ", ".join(f"{g:g}" for g in default_gauges) + " m"

    print(f"  Gauges [m] (space-separated, Enter for default = {d_lbl})")
    while True:
        try:
            raw = input("  Gauge radii     : ").strip()
        except EOFError:
            print()
            return default_gauges
        if raw == '':
            return default_gauges
        try:
            gauges = [float(t) for t in raw.split()]
        except ValueError as e:
            print(f"    Invalid number: {e}")
            continue
        if not gauges:
            print("    No values parsed - try again or press Enter for default.")
            continue
        bad = [g for g in gauges if g <= 0 or g > radius_m]
        if bad:
            print(f"    Out of range (must be in (0, {radius_m}] m): {bad}")
            continue
        return sorted(set(gauges))


def _ask_obstacles(Lx, Ly):
    """Repeatedly ask for rectangles 'x0 x1 y0 y1'; empty line finishes."""
    obstacles = []
    print("  Obstacles: enter rectangles as 'x0 x1 y0 y1' [m], "
          "Enter to finish.")
    while True:
        try:
            raw = input(f"  Obstacle {len(obstacles)+1}: ").strip()
        except EOFError:
            print()
            break
        if raw == '':
            break
        try:
            vals = [float(tk) for tk in raw.split()]
        except ValueError as exc:
            print(f"    Invalid number: {exc}")
            continue
        if len(vals) != 4:
            print("    Need exactly 4 values: x0 x1 y0 y1")
            continue
        x0, x1, y0, y1 = vals
        if not (0 <= x0 < x1 <= Lx and 0 <= y0 < y1 <= Ly):
            print(f"    Rectangle must satisfy 0 <= x0 < x1 <= {Lx:g} and "
                  f"0 <= y0 < y1 <= {Ly:g}")
            continue
        obstacles.append((x0, x1, y0, y1))
    return obstacles


def _ask_gauges_2d(Lx, Ly, x0, y0):
    """
    Space-separated 'x,y' gauge locations. Default: 8 gauges on a
    horizontal line at the charge height, from the charge toward x = Lx.
    """
    xs = np.linspace(x0 + 0.1 * (Lx - x0), 0.9 * Lx, 8)
    default_gauges = [(float(x), float(y0)) for x in sorted(set(np.round(xs, 3)))]
    d_lbl = ", ".join(f"({x:g},{y:g})" for x, y in default_gauges[:3]) + ", ..."

    print(f"  Gauges: space-separated x,y pairs [m] "
          f"(Enter for default = {d_lbl} at charge height)")
    while True:
        try:
            raw = input("  Gauge locations : ").strip()
        except EOFError:
            print()
            return default_gauges
        if raw == '':
            return default_gauges
        try:
            gauges = []
            for tok in raw.split():
                sx, _, sy = tok.partition(',')
                gauges.append((float(sx), float(sy)))
        except ValueError:
            print("    Expected pairs like: 2,1.5 5,1.5 8,1.5")
            continue
        bad = [(x, y) for (x, y) in gauges
               if not (0 <= x <= Lx and 0 <= y <= Ly)]
        if bad:
            print(f"    Out of domain (0..{Lx:g} x 0..{Ly:g}): {bad}")
            continue
        return gauges


def _ask_obstacles_3d(Lx, Ly, Lz):
    """Repeatedly ask for boxes 'x0 x1 y0 y1 z0 z1'; empty line finishes."""
    obstacles = []
    print("  Obstacles: enter boxes as 'x0 x1 y0 y1 z0 z1' [m], "
          "Enter to finish.")
    while True:
        try:
            raw = input(f"  Obstacle {len(obstacles)+1}: ").strip()
        except EOFError:
            print()
            break
        if raw == '':
            break
        try:
            vals = [float(tk) for tk in raw.split()]
        except ValueError as exc:
            print(f"    Invalid number: {exc}")
            continue
        if len(vals) != 6:
            print("    Need exactly 6 values: x0 x1 y0 y1 z0 z1")
            continue
        x0, x1, y0, y1, z0, z1 = vals
        if not (0 <= x0 < x1 <= Lx and 0 <= y0 < y1 <= Ly
                and 0 <= z0 < z1 <= Lz):
            print(f"    Box must satisfy 0 <= a0 < a1 <= L for each axis "
                  f"({Lx:g} x {Ly:g} x {Lz:g})")
            continue
        obstacles.append((x0, x1, y0, y1, z0, z1))
    return obstacles


def _ask_gauges_3d(Lx, Ly, Lz, x0, y0, z0):
    """
    Space-separated 'x,y,z' gauge locations. Default: 8 gauges on a
    horizontal line from the burst toward x = Lx at the burst height.
    """
    xs = np.linspace(x0 + 0.1 * (Lx - x0), 0.9 * Lx, 8)
    default_gauges = [(float(x), float(y0), float(z0))
                      for x in sorted(set(np.round(xs, 3)))]
    d_lbl = ", ".join(f"({x:g},{y:g},{z:g})"
                      for x, y, z in default_gauges[:2]) + ", ..."

    print(f"  Gauges: space-separated x,y,z triples [m] "
          f"(Enter for default = {d_lbl} at burst height)")
    while True:
        try:
            raw = input("  Gauge locations : ").strip()
        except EOFError:
            print()
            return default_gauges
        if raw == '':
            return default_gauges
        try:
            gauges = []
            for tok in raw.split():
                parts = tok.split(',')
                if len(parts) != 3:
                    raise ValueError(tok)
                gauges.append(tuple(float(s) for s in parts))
        except ValueError:
            print("    Expected triples like: 2,5,1.5 4,5,1.5 6,5,1.5")
            continue
        bad = [g for g in gauges
               if not (0 <= g[0] <= Lx and 0 <= g[1] <= Ly and 0 <= g[2] <= Lz)]
        if bad:
            print(f"    Out of domain (0..{Lx:g} x 0..{Ly:g} x 0..{Lz:g}): {bad}")
            continue
        return gauges


def ask_user_1d():
    """Interactively collect all simulation parameters from the user."""
    print("\n" + "=" * 55)
    print("  1D Spherical Blast Wave Solver - Setup")
    print("=" * 55)
    print("  (press Enter to accept the default shown in [brackets])\n")

    charge_kg   = _ask("Charge weight [kg TNT]", default=1.0,
                       validator=_positive("Charge weight"))
    radius_m    = _ask("Domain radius [m]",      default=10.0,
                       validator=_positive("Domain radius"))
    cell_size_m = _ask("Cell size [m]",          default=0.001,
                       validator=lambda v: None if 0 < v < radius_m
                       else f"Cell size must be in (0, {radius_m}) m.")

    eos = _ask_eos(default='idealGas')

    n_snapshots = _ask("Number of field snapshots", default=5, cast=int,
                       validator=lambda v: None if v >= 1 else "Must be >= 1.")

    gauge_radii = _ask_gauges(radius_m, default_step=1.0)
    gauge_file  = _ask("Gauge output filename", default='gauges.txt', cast=str)

    profile_file = _ask("Save field profile for 2D remap? filename, or '-' to skip",
                        default='-', cast=str)
    profile_file = None if profile_file.strip() in ('-', '') else profile_file.strip()

    # ── Confirmation summary ───────────────────────────────────────────────
    if len(gauge_radii) <= 6:
        gauges_label = ", ".join(f"{g:g}" for g in gauge_radii) + " m"
    else:
        gauges_label = (f"{gauge_radii[0]:g}, {gauge_radii[1]:g}, ..., "
                        f"{gauge_radii[-1]:g} m  ({len(gauge_radii)} gauges)")

    print("\n" + "-" * 50)
    print("  Review your inputs:")
    print("-" * 50)
    print(f"  1. Charge weight  : {charge_kg} kg TNT")
    print(f"  2. Domain radius  : {radius_m} m")
    print(f"  3. Cell size      : {cell_size_m} m")
    print(f"  4. EOS            : {eos}")
    print(f"  5. Snapshots      : {n_snapshots}")
    print(f"  6. Gauges         : {gauges_label}")
    print(f"  7. Gauge file     : {gauge_file}")
    print(f"  8. Profile file   : {profile_file if profile_file else '(not saved)'}")
    print(f"     (run stops when shock reaches r = {radius_m} m)")
    print("-" * 50)
    try:
        confirm = input("  Press Enter to run, or 'r' to re-enter all "
                        "values: ").strip().lower()
    except EOFError:
        print()
        confirm = ''
    if confirm == 'r':
        return ask_user_1d()

    print("")
    return dict(
        charge_kg   = charge_kg,
        radius_m    = radius_m,
        cell_size_m = cell_size_m,
        eos         = eos,
        n_snapshots = n_snapshots,
        gauge_radii = gauge_radii,
        gauge_file  = gauge_file,
        profile_file= profile_file,
    )


def ask_user_2d():
    """Interactively collect all simulation parameters from the user."""
    print("\n" + "=" * 60)
    print("  2D Blast Wave Solver - Setup")
    print("=" * 60)
    print("  (press Enter to accept the default shown in [brackets])\n")

    geometry = _ask_choice("Geometry", ['axisymmetric', 'planar'], 'axisymmetric')
    axisym   = geometry == 'axisymmetric'

    Lx = _ask("Radial extent Lx [m]" if axisym else "Domain width Lx [m]",
              default=10.0, validator=_positive("Lx"))
    Ly = _ask("Height Ly [m]", default=10.0, validator=_positive("Ly"))
    cell_size_m = _ask("Cell size [m]", default=0.025,
                       validator=lambda v: None if 0 < v < min(Lx, Ly)
                       else f"Cell size must be in (0, {min(Lx, Ly)}) m.")

    # ── Initialization: direct charge, or 1D profile remap (axisym only) ──
    profile      = None
    profile_file = None
    charge       = None
    if axisym:
        init = _ask_choice("Initialize from", ['charge', '1d-profile'], 'charge')
        if init == '1d-profile':
            def _readable(fn):
                try:
                    open(fn).close()
                    return None
                except OSError as exc:
                    return f"Cannot open '{fn}': {exc}"
            profile_file = _ask("1D profile file (from blast1d.py)",
                                default='blast_profile.txt', cast=str,
                                validator=_readable)
            profile = load_profile(profile_file)
            print(f"    Loaded: {profile['charge_kg']:g} kg TNT, "
                  f"EOS {profile['eos']}, t = {profile['t']*1e3:.3f} ms, "
                  f"{len(profile['r'])} cells")
        else:
            charge = _ask("Charge weight [kg TNT]", default=1.0,
                          validator=_positive("Charge weight"))
        x0 = 0.0
        y0 = _ask("Burst height above y=0 [m] (0 = ground burst)",
                  default=Ly / 2.0,
                  validator=lambda v: None if 0 <= v <= Ly
                  else f"Height must be in [0, {Ly}] m.")
    else:
        print("  Planar mode: the charge is an infinite cylinder - enter its")
        print("  line density in kg of TNT per metre of cylinder length.")
        charge = _ask("Charge line density [kg TNT / m]", default=1.0,
                      validator=_positive("Charge line density"))
        x0 = _ask("Charge centre x [m]", default=Lx / 2.0,
                  validator=lambda v: None if 0 < v < Lx else f"x in (0, {Lx}) m.")
        y0 = _ask("Charge centre y [m]", default=Ly / 2.0,
                  validator=lambda v: None if 0 < v < Ly else f"y in (0, {Ly}) m.")

    eos = _ask_eos(default=profile['eos'] if profile is not None
                   and profile['eos'] in ('JWL', 'idealGas') else 'idealGas')

    # ── Boundary conditions ────────────────────────────────────────────────
    bcs = {}
    if axisym:
        print("  Left boundary (r=0) is the symmetry axis.")
        bcs['x_lo'] = 'wall'
        bcs['y_lo'] = _ask_choice("Bottom boundary (ground?)",
                                  ['wall', 'open'], 'wall')
        bcs['y_hi'] = _ask_choice("Top boundary", ['open', 'wall'], 'open')
        bcs['x_hi'] = _ask_choice("Right boundary", ['open', 'wall'], 'open')
    else:
        for key, name in (('x_lo', 'Left'), ('x_hi', 'Right'),
                          ('y_lo', 'Bottom'), ('y_hi', 'Top')):
            bcs[key] = _ask_choice(f"{name} boundary", ['open', 'wall'], 'open')

    obstacles   = _ask_obstacles(Lx, Ly)
    n_snapshots = _ask("Number of field snapshots", default=6, cast=int,
                       validator=lambda v: None if v >= 1 else "Must be >= 1.")
    gauges      = _ask_gauges_2d(Lx, Ly, x0, y0)
    gauge_file  = _ask("Gauge output filename", default='gauges_2d.txt', cast=str)

    live = _ask_choice("Live view while running?", ['yes', 'no'], 'yes') == 'yes'
    default_anim = ('blast_2d_animation.mp4'
                    if animation.FFMpegWriter.isAvailable()
                    else 'blast_2d_animation.gif')
    anim_file = _ask("Animation file (.gif / .mp4), or '-' to skip",
                     default=default_anim, cast=str)
    anim_file = None if anim_file.strip() in ('-', '') else anim_file.strip()

    profile2d_file = None
    if axisym:
        profile2d_file = _ask("Save 2D profile for 3D remap? filename (.npz), "
                              "or '-' to skip", default='-', cast=str)
        profile2d_file = (None if profile2d_file.strip() in ('-', '')
                          else profile2d_file.strip())

    # ── Confirmation summary ───────────────────────────────────────────────
    if profile is not None:
        charge_lbl = f"1D profile '{profile_file}' ({profile['charge_kg']:g} kg TNT)"
    elif axisym:
        charge_lbl = f"{charge:g} kg TNT sphere"
    else:
        charge_lbl = f"{charge:g} kg/m TNT cylinder"
    obst_lbl = "; ".join(f"({a:g},{b:g},{c:g},{d:g})"
                         for a, b, c, d in obstacles) or "none"
    gaug_lbl = (", ".join(f"({x:g},{y:g})" for x, y in gauges[:4])
                + (", ..." if len(gauges) > 4 else ""))

    print("\n" + "-" * 55)
    print("  Review your inputs:")
    print("-" * 55)
    print(f"  1. Geometry       : {geometry}")
    print(f"  2. Domain         : {Lx:g} x {Ly:g} m, cell {cell_size_m:g} m")
    print(f"  3. Charge         : {charge_lbl} at ({x0:g}, {y0:g}) m")
    print(f"  4. EOS            : {eos}")
    print(f"  5. Boundaries     : " + ", ".join(f"{k}={v}" for k, v in bcs.items()))
    print(f"  6. Obstacles      : {obst_lbl}")
    print(f"  7. Snapshots      : {n_snapshots}")
    print(f"  8. Gauges         : {gaug_lbl}  ({len(gauges)} total)")
    print(f"  9. Gauge file     : {gauge_file}")
    print(f" 10. Live view      : {'yes' if live else 'no'}")
    print(f" 11. Animation      : {anim_file if anim_file else '(not saved)'}")
    if axisym:
        print(f" 12. 2D profile     : "
              f"{profile2d_file if profile2d_file else '(not saved)'}")
    print("-" * 55)
    try:
        confirm = input("  Press Enter to run, or 'r' to re-enter all "
                        "values: ").strip().lower()
    except EOFError:
        print()
        confirm = ''
    if confirm == 'r':
        return ask_user_2d()

    print("")
    return dict(
        geometry      = geometry,
        Lx            = Lx,
        Ly            = Ly,
        cell_size_m   = cell_size_m,
        charge        = charge,
        charge_center = (x0, y0),
        profile       = profile,
        eos           = eos,
        bcs           = bcs,
        obstacles     = obstacles,
        n_snapshots   = n_snapshots,
        gauges        = gauges,
        gauge_file    = gauge_file,
        live          = live,
        anim_file     = anim_file,
        profile2d_file= profile2d_file,
    )


def ask_user_3d():
    """Interactively collect all simulation parameters from the user."""
    print("\n" + "=" * 62)
    print("  3D Blast Wave Solver - Setup")
    print("=" * 62)
    print("  (press Enter to accept the default shown in [brackets])\n")

    Lx = _ask("Domain width Lx [m]",  default=10.0, validator=_positive("Lx"))
    Ly = _ask("Domain depth Ly [m]",  default=10.0, validator=_positive("Ly"))
    Lz = _ask("Domain height Lz [m]", default=10.0, validator=_positive("Lz"))

    def _cell_ok(v):
        if not 0 < v < min(Lx, Ly, Lz):
            return f"Cell size must be in (0, {min(Lx, Ly, Lz)}) m."
        n_est = int(Lx / v) * int(Ly / v) * int(Lz / v)
        if n_est > CELLS_REFUSE:
            return (f"{n_est:,} cells exceeds the {CELLS_REFUSE:,} cap - "
                    f"use a coarser cell or a smaller domain.")
        if n_est > CELLS_WARN:
            print(f"    [warn] {n_est:,} cells - this will be slow and "
                  f"RAM-hungry")
        return None
    cell_size_m = _ask("Cell size [m]", default=0.1, validator=_cell_ok)

    # ── Initialization ─────────────────────────────────────────────────────
    profile = profile2d = None
    profile_file = charge = None
    charge_resolution = 'resolve'
    init = _ask_choice("Initialize from", ['charge', '1d-profile', '2d-profile'],
                       'charge')

    def _readable(fn):
        try:
            open(fn, 'rb').close()
            return None
        except OSError as exc:
            return f"Cannot open '{fn}': {exc}"

    if init == '1d-profile':
        profile_file = _ask("1D profile file (from blast1d.py)",
                            default='blast_profile.txt', cast=str,
                            validator=_readable)
        profile = load_profile(profile_file)
        print(f"    Loaded: {profile['charge_kg']:g} kg TNT, "
              f"EOS {profile['eos']}, t = {profile['t']*1e3:.3f} ms")
    elif init == '2d-profile':
        profile_file = _ask("2D profile file (from blast2d.py, .npz)",
                            default='blast_profile_2d.npz', cast=str,
                            validator=_readable)
        profile2d = load_profile_2d(profile_file)
        print(f"    Loaded: {profile2d['charge_kg']:g} kg TNT, "
              f"EOS {profile2d['eos']}, t = {profile2d['t']*1e3:.3f} ms, "
              f"burst height {profile2d['y0']:g} m, "
              f"grid {profile2d['rho'].shape[0]} x {profile2d['rho'].shape[1]}")
    else:
        charge = _ask("Charge weight [kg TNT]", default=1.0,
                      validator=_positive("Charge weight"))
        print("    ('resolve' refines the grid to 5 cells across the "
              "charge radius - can\n     exceed the 3D cell cap for small "
              "charges; 'smear' keeps your cell size\n     and deposits "
              "the charge's mass & energy into a small source ball)")
        charge_resolution = _ask_choice("Charge resolution",
                                        ['resolve', 'smear'], 'resolve')

    x0 = _ask("Burst point x [m]", default=Lx / 2.0,
              validator=lambda v: None if 0 <= v <= Lx else f"x in [0, {Lx}] m.")
    y0 = _ask("Burst point y [m]", default=Ly / 2.0,
              validator=lambda v: None if 0 <= v <= Ly else f"y in [0, {Ly}] m.")
    if profile2d is not None:
        z0 = profile2d['y0']
        print(f"  Burst height z = {z0:g} m (from the 2D profile)")
    else:
        z0 = _ask("Burst height z [m] (0 = ground burst)", default=Lz / 2.0,
                  validator=lambda v: None if 0 <= v <= Lz
                  else f"z in [0, {Lz}] m.")

    prof_eos = (profile or profile2d or {}).get('eos')
    eos = _ask_eos(default=prof_eos if prof_eos in ('JWL', 'idealGas')
                   else 'idealGas')

    # ── Boundary conditions ────────────────────────────────────────────────
    bcs = {}
    bcs['z_lo'] = _ask_choice("Bottom boundary z=0 (ground?)",
                              ['wall', 'open'], 'wall')
    bcs['z_hi'] = _ask_choice("Top boundary", ['open', 'wall'], 'open')
    for key, name in (('x_lo', 'x=0'), ('x_hi', f'x={Lx:g}'),
                      ('y_lo', 'y=0'), ('y_hi', f'y={Ly:g}')):
        bcs[key] = _ask_choice(f"Boundary {name}", ['open', 'wall'], 'open')

    obstacles   = _ask_obstacles_3d(Lx, Ly, Lz)
    n_snapshots = _ask("Number of field snapshots", default=6, cast=int,
                       validator=lambda v: None if v >= 1 else "Must be >= 1.")
    gauges      = _ask_gauges_3d(Lx, Ly, Lz, x0, y0, z0)
    gauge_file  = _ask("Gauge output filename", default='gauges_3d.txt', cast=str)

    live = _ask_choice("Live view while running?", ['yes', 'no'], 'yes') == 'yes'
    from .viz3d import MISSING_MSG, pyvista_available
    if pyvista_available():
        view3d = _ask_choice("Interactive 3D viewer while running?",
                             ['yes', 'no'], 'yes') == 'yes'
    else:
        print(f"    [note] {MISSING_MSG}")
        view3d = False
    default_anim = ('blast_3d_animation.mp4'
                    if animation.FFMpegWriter.isAvailable()
                    else 'blast_3d_animation.gif')
    anim_file = _ask("Animation file (.gif / .mp4), or '-' to skip",
                     default=default_anim, cast=str)
    anim_file = None if anim_file.strip() in ('-', '') else anim_file.strip()

    # ── Confirmation summary ───────────────────────────────────────────────
    if profile is not None:
        charge_lbl = f"1D profile '{profile_file}' ({profile['charge_kg']:g} kg)"
    elif profile2d is not None:
        charge_lbl = f"2D profile '{profile_file}' ({profile2d['charge_kg']:g} kg)"
    else:
        charge_lbl = f"{charge:g} kg TNT sphere ({charge_resolution})"
    obst_lbl = "; ".join("(" + ",".join(f"{v:g}" for v in box) + ")"
                         for box in obstacles) or "none"
    gaug_lbl = (", ".join(f"({x:g},{y:g},{z:g})" for x, y, z in gauges[:3])
                + (", ..." if len(gauges) > 3 else ""))
    n_est = int(Lx / cell_size_m) * int(Ly / cell_size_m) * int(Lz / cell_size_m)

    print("\n" + "-" * 58)
    print("  Review your inputs:")
    print("-" * 58)
    print(f"  1. Domain         : {Lx:g} x {Ly:g} x {Lz:g} m, "
          f"cell {cell_size_m:g} m (~{n_est:,} cells)")
    print(f"  2. Init           : {charge_lbl} at ({x0:g}, {y0:g}, {z0:g}) m")
    print(f"  3. EOS            : {eos}")
    print(f"  4. Boundaries     : " + ", ".join(f"{k}={v}" for k, v in bcs.items()))
    print(f"  5. Obstacles      : {obst_lbl}")
    print(f"  6. Snapshots      : {n_snapshots}")
    print(f"  7. Gauges         : {gaug_lbl}  ({len(gauges)} total)")
    print(f"  8. Gauge file     : {gauge_file}")
    print(f"  9. Live view      : {'yes' if live else 'no'}")
    print(f" 10. 3D viewer      : {'yes' if view3d else 'no'}")
    print(f" 11. Animation      : {anim_file if anim_file else '(not saved)'}")
    print("-" * 58)
    try:
        confirm = input("  Press Enter to run, or 'r' to re-enter all "
                        "values: ").strip().lower()
    except EOFError:
        print()
        confirm = ''
    if confirm == 'r':
        return ask_user_3d()

    print("")
    return dict(
        Lx=Lx, Ly=Ly, Lz=Lz, cell_size_m=cell_size_m,
        charge=charge, charge_center=(x0, y0, z0),
        charge_resolution=charge_resolution,
        profile=profile, profile2d=profile2d,
        eos=eos, bcs=bcs, obstacles=obstacles,
        n_snapshots=n_snapshots, gauges=gauges, gauge_file=gauge_file,
        live=live, view3d=view3d, anim_file=anim_file,
    )


def main(dim, solver='native'):
    """Run the prompt workflow for '1d', '2d' or '3d'. The historical
    (native) flow lives in legacy/; the blastFoam backend has its own
    prompt flow so the byte-pinned legacy modules stay untouched."""
    dim = str(dim).lower().lstrip('-')
    if dim not in ('1', '1d', '2', '2d', '3', '3d'):
        raise SystemExit(f"Unknown dimension '{dim}' (use 1d, 2d or 3d)")
    if solver == 'blastfoam':
        from .solvers.foam.cli_run import run
        return run(dim)
    if dim in ('1', '1d'):
        from .legacy import blast1d as mod
    elif dim in ('2', '2d'):
        from .legacy import blast2d as mod
    else:
        from .legacy import blast3d as mod
    mod._main()
