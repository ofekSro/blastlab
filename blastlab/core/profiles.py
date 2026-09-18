"""Field-profile files and cross-dimension remapping.

1D radial profiles are human-readable TSV (written by the 1D solver,
consumed as an axisymmetric IC in 2D or a spherical IC in 3D).
2D axisymmetric profiles are compressed .npz (written by the 2D solver,
rotated around a vertical axis as a 3D IC).
"""

import os

import numpy as np

from .constants import RHO_AIR, E_AIR


# ── 1D radial profile (TSV) ───────────────────────────────────────────────────

def save_profile(final_profile, filename='blast_profile.txt'):
    """
    Write the final radial field state to a tab-separated text file that
    the 2D/3D solvers can load as an initial condition.

    Metadata lines start with '#'; columns:
      r[m]  rho[kg/m3]  u[m/s]  e[J/kg]  p[Pa]  phase
    """
    fp = final_profile
    header = (f"# blast1d radial field profile\n"
              f"# time_s   = {fp['t']:.9e}\n"
              f"# charge_kg= {fp['charge_kg']}\n"
              f"# eos      = {fp['eos']}\n"
              f"# solver   = {fp.get('source_solver', 'unknown')}\n"
              f"# r_exp_m  = {fp['r_exp']:.6e}\n"
              f"# radius_m = {fp['radius_m']}\n"
              f"# r[m]\trho[kg/m3]\tu[m/s]\te[J/kg]\tp[Pa]\tphase")
    matrix = np.column_stack([fp['r'], fp['rho'], fp['u'],
                              fp['e'], fp['p'], fp['phase']])
    np.savetxt(filename, matrix, delimiter='\t', header=header,
               comments='', fmt='%.9e')
    print(f"  Field profile saved: {filename}  ({len(fp['r'])} cells, "
          f"t = {fp['t']*1e3:.3f} ms)")


#: bounded memo for profile_source, keyed on (path, mtime_ns, size) so a
#: rewritten profile is re-read but a keystroke is not
_SRC_MEMO = {}
_SRC_MEMO_MAX = 8


def profile_source(filename):
    """Which solver wrote this profile: 'native' | 'blastfoam' | 'unknown'.

    Reads the HEADER ONLY - validate_case calls this on a 300 ms
    keystroke debounce, so the cost has to be one os.stat in the common
    case. Profiles written before N5-4 carry no stamp and come back
    'unknown', which is never treated as an error anywhere: refusing
    them would break every profile already on disk in exchange for a
    guess.

    Never raises. A caller on the validation path cannot afford to care
    why a file was unreadable, only that it could not be identified.
    """
    try:
        st = os.stat(filename)
        key = (os.path.abspath(filename), st.st_mtime_ns, st.st_size)
    except OSError:
        return 'unknown'
    hit = _SRC_MEMO.get(key)
    if hit is not None:
        return hit
    try:
        if filename.lower().endswith('.npz'):
            with np.load(filename) as z:
                src = (str(z['source_solver'])
                       if 'source_solver' in z.files else 'unknown')
        else:
            src = 'unknown'
            with open(filename, encoding='utf-8', errors='replace') as fh:
                for _ in range(20):          # the header is 6 lines today
                    line = fh.readline()
                    if not line or not line.startswith('#'):
                        break
                    if '=' in line:
                        k, _, v = line[1:].partition('=')
                        if k.strip() == 'solver':
                            src = v.strip() or 'unknown'
                            break
    except Exception:            # noqa: BLE001 - see the docstring
        src = 'unknown'
    if len(_SRC_MEMO) >= _SRC_MEMO_MAX:
        _SRC_MEMO.clear()
    _SRC_MEMO[key] = src
    return src


def load_profile(filename):
    """
    Load a radial field profile written by save_profile.

    Returns dict with metadata (t, charge_kg, eos, r_exp, radius_m) and
    arrays r, rho, u, e, p, phase.
    """
    meta = {}
    with open(filename) as f:
        for line in f:
            if not line.startswith('#'):
                break
            if '=' in line:
                key, _, val = line.lstrip('#').partition('=')
                meta[key.strip()] = val.strip()

    data = np.loadtxt(filename, comments='#')
    if data.ndim != 2 or data.shape[1] != 6:
        raise ValueError(f"{filename}: expected 6 columns "
                         f"(r rho u e p phase), got shape {data.shape}")
    return dict(
        t         = float(meta.get('time_s', 0.0)),
        charge_kg = float(meta.get('charge_kg', 0.0)),
        eos       = meta.get('eos', 'unknown'),
        source_solver = meta.get('solver', 'unknown'),
        r_exp     = float(meta.get('r_exp_m', 0.0)),
        radius_m  = float(meta.get('radius_m', 0.0)),
        r     = data[:, 0], rho = data[:, 1], u = data[:, 2],
        e     = data[:, 3], p   = data[:, 4], phase = data[:, 5],
    )


# ── 1D -> 2D axisymmetric remap ──────────────────────────────────────────────

def remap_profile_1d_to_2d(profile, x_c, y_c, y0):
    """
    Interpolate a 1D spherical profile onto the 2D axisymmetric grid
    around the burst point (r=0, z=y0).

    Returns U (4,Nx,Ny), phase (Nx,Ny) int, start time t0.
    """
    X = x_c[:, None]
    Y = y_c[None, :] - y0
    d = np.sqrt(X**2 + Y**2)

    r_p = profile['r']
    rho = np.interp(d, r_p, profile['rho'], right=RHO_AIR)
    u_r = np.interp(d, r_p, profile['u'],   right=0.0)
    e   = np.interp(d, r_p, profile['e'],   right=E_AIR)
    ph  = np.interp(d, r_p, profile['phase'], right=0.0)
    phase = (ph > 0.5).astype(int)

    # Radial unit vector; u_r -> 0 at the burst point anyway.
    d_safe = np.maximum(d, 1e-12)
    u = u_r * X / d_safe
    v = u_r * Y / d_safe

    U = np.array([rho,
                  rho * u,
                  rho * v,
                  rho * (e + 0.5 * (u**2 + v**2))])
    return U, phase, profile['t']


# ── 1D -> 3D remap ───────────────────────────────────────────────────────────

def remap_profile_1d_to_3d(profile, x_c, y_c, z_c, center):
    """
    Interpolate a 1D spherical profile onto the 3D grid around `center`.
    Returns U (5,Nx,Ny,Nz), phase, start time t0.
    """
    x0, y0, z0 = center
    X = x_c[:, None, None] - x0
    Y = y_c[None, :, None] - y0
    Z = z_c[None, None, :] - z0
    d = np.sqrt(X**2 + Y**2 + Z**2)

    r_p = profile['r']
    rho = np.interp(d, r_p, profile['rho'], right=RHO_AIR)
    u_r = np.interp(d, r_p, profile['u'],   right=0.0)
    e   = np.interp(d, r_p, profile['e'],   right=E_AIR)
    ph  = np.interp(d, r_p, profile['phase'], right=0.0)
    phase = (ph > 0.5).astype(int)

    d_safe = np.maximum(d, 1e-12)
    u = u_r * X / d_safe
    v = u_r * Y / d_safe
    w = u_r * Z / d_safe

    U = np.array([rho, rho * u, rho * v, rho * w,
                  rho * (e + 0.5 * (u**2 + v**2 + w**2))])
    return U, phase, profile['t']


# ── 2D axisymmetric profile (.npz) ───────────────────────────────────────────

def save_profile_2d(meta, filename='blast_profile_2d.npz'):
    """
    Write the final axisymmetric r-z field state to a compressed .npz that
    the 3D solver can load as an initial condition (rotated around a
    vertical axis through a chosen 3D burst point).

    Arrays: rho, u (=u_r), v (=u_z), e, p, phase (Nx,Ny) + r_c, z_c.
    Scalars: t, charge_kg (0.0 when the 2D run itself came from a 1D
    profile), r_exp, y0 (burst height). Strings: eos, geometry.
    """
    if meta['geometry'] != 'axisymmetric':
        raise ValueError("save_profile_2d: only axisymmetric fields can be "
                         "remapped into 3D")
    if meta['solid'].any():
        print("  [warn] 2D field contains obstacles - they would become "
              "rings in 3D and are NOT carried over")
    fs = meta['final_state']
    np.savez_compressed(
        filename,
        rho=fs['rho'], u=fs['u'], v=fs['v'], e=fs['e'], p=fs['p'],
        phase=fs['phase'], r_c=meta['x_c'], z_c=meta['y_c'],
        t=fs['t'],
        charge_kg=meta['charge'] if meta['charge'] is not None else 0.0,
        r_exp=meta['r_exp'], y0=meta['charge_center'][1],
        eos=meta['eos'], geometry=meta['geometry'],
        source_solver=str(meta.get('solver', 'unknown')))
    print(f"  2D field profile saved: {filename}  "
          f"({fs['rho'].shape[0]} x {fs['rho'].shape[1]} cells, "
          f"t = {fs['t']*1e3:.3f} ms)")


def load_profile_2d(filename):
    """Load an axisymmetric r-z field saved by save_profile_2d."""
    z = np.load(filename)
    geometry = str(z['geometry'])
    if geometry != 'axisymmetric':
        raise ValueError(f"{filename}: geometry '{geometry}' cannot be "
                         f"remapped into 3D (axisymmetric only)")
    return dict(
        t         = float(z['t']),
        charge_kg = float(z['charge_kg']),
        eos       = str(z['eos']),
        source_solver = (str(z['source_solver'])
                         if 'source_solver' in z.files else 'unknown'),
        r_exp     = float(z['r_exp']),
        y0        = float(z['y0']),        # burst height above ground
        r_c   = z['r_c'], z_c = z['z_c'],
        rho   = z['rho'], u = z['u'], v = z['v'],
        e     = z['e'],   p = z['p'], phase = z['phase'].astype(float),
    )


# ── 2D -> 3D remap ───────────────────────────────────────────────────────────

def _bilinear(F, r_c, z_c, R, Z):
    """Bilinear interpolation of F(r,z) on a regular grid at points (R, Z)."""
    dr = r_c[1] - r_c[0]
    dz = z_c[1] - z_c[0]
    fr = (R - r_c[0]) / dr
    fz = (Z - z_c[0]) / dz
    i  = np.clip(np.floor(fr).astype(int), 0, len(r_c) - 2)
    j  = np.clip(np.floor(fz).astype(int), 0, len(z_c) - 2)
    wr = np.clip(fr - i, 0.0, 1.0)
    wz = np.clip(fz - j, 0.0, 1.0)
    return ((1 - wr) * (1 - wz) * F[i, j] + wr * (1 - wz) * F[i + 1, j]
            + (1 - wr) * wz * F[i, j + 1] + wr * wz * F[i + 1, j + 1])


def remap_profile_2d_to_3d(prof, x_c, y_c, z_c, x0b, y0b):
    """
    Rotate an axisymmetric r-z field around the vertical axis through
    (x0b, y0b). The 2D z coordinate maps directly onto the 3D z (both
    grounds at 0); cells outside the 2D extent get ambient air.

    Returns U (5,Nx,Ny,Nz), phase, start time t0.
    """
    X = x_c[:, None, None] - x0b        # (Nx,1,1)
    Y = y_c[None, :, None] - y0b        # (1,Ny,1)
    r_cyl = np.sqrt(X**2 + Y**2)        # (Nx,Ny,1)
    Z = z_c[None, None, :]              # (1,1,Nz)

    R = np.broadcast_to(r_cyl, (len(x_c), len(y_c), len(z_c)))
    Zb = np.broadcast_to(Z, R.shape)
    outside = ((R > prof['r_c'][-1])
               | (Zb > prof['z_c'][-1]) | (Zb < prof['z_c'][0]))

    rho = np.where(outside, RHO_AIR, _bilinear(prof['rho'], prof['r_c'], prof['z_c'], R, Zb))
    u_r = np.where(outside, 0.0,     _bilinear(prof['u'],   prof['r_c'], prof['z_c'], R, Zb))
    u_z = np.where(outside, 0.0,     _bilinear(prof['v'],   prof['r_c'], prof['z_c'], R, Zb))
    e   = np.where(outside, E_AIR,   _bilinear(prof['e'],   prof['r_c'], prof['z_c'], R, Zb))
    ph  = np.where(outside, 0.0,     _bilinear(prof['phase'], prof['r_c'], prof['z_c'], R, Zb))
    phase = (ph > 0.5).astype(int)

    d_safe = np.maximum(r_cyl, 1e-12)
    u = u_r * X / d_safe
    v = u_r * Y / d_safe
    w = u_z

    U = np.array([rho, rho * u, rho * v, rho * w,
                  rho * (e + 0.5 * (u**2 + v**2 + w**2))])
    return U, phase, prof['t']
