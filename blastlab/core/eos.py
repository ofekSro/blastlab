"""Equations of state: ideal-gas air and JWL detonation products."""

import numpy as np

from .constants import GAMMA_AIR, JWL_TNT


def air_pressure(rho, e):
    return (GAMMA_AIR - 1.0) * rho * e


def air_soundspeed(rho, p):
    return np.sqrt(GAMMA_AIR * np.maximum(p, 1.0) / np.maximum(rho, 1e-10))


def jwl_pressure(rho, e, j=JWL_TNT):
    rho = np.maximum(rho, 1e-10)
    V   = j['rho0'] / rho   # relative specific volume rho0/rho
    return (j['A'] * (1.0 - j['omega'] / (j['R1'] * V)) * np.exp(-j['R1'] * V)
          + j['B'] * (1.0 - j['omega'] / (j['R2'] * V)) * np.exp(-j['R2'] * V)
          + j['omega'] * rho * e)


def jwl_soundspeed(rho, e, p, j=JWL_TNT):
    """
    c^2 = (dp/drho)_e + omega * p / rho
    (dp/drho)_e evaluated numerically for generality.
    """
    rho  = np.maximum(rho, 1e-10)
    eps  = rho * 1e-5
    dp   = (jwl_pressure(rho + eps, e, j) - jwl_pressure(rho - eps, e, j)) / (2.0 * eps)
    c2   = dp + j['omega'] * np.maximum(p, 1.0) / rho
    return np.sqrt(np.maximum(c2, 1.0))  # floor at 1 m/s


def material_jwl(name):
    """JWL parameter dict for a charge material (N11/T46). 'TNT' returns
    the byte-pinned constants.JWL_TNT OBJECT itself, so every default
    run stays bit-identical; other names come from the shared
    solvers/foam/materials table (pure data, no foam dependency)."""
    if not name or name == 'TNT':
        return JWL_TNT
    from ..solvers.foam.materials import MATERIALS
    m = MATERIALS[name]
    return dict(A=m.A, B=m.B, R1=m.R1, R2=m.R2, omega=m.omega,
                rho0=m.rho0, e0=m.e0)


def pressure_soundspeed(rho, e, phase, eos, jwl=JWL_TNT):
    """
    Per-cell pressure and sound speed dispatched by phase mask
    (0 = air, 1 = detonation products). The JWL numerical soundspeed is
    evaluated on the product mask only - never on the full grid.
    `jwl` is the material's parameter set (material_jwl); the default
    keeps every existing caller byte-identical.
    """
    air  = phase == 0
    prod = ~air
    p    = np.empty_like(rho)
    c    = np.empty_like(rho)

    if air.any():
        p[air] = air_pressure(rho[air], e[air])
        c[air] = air_soundspeed(rho[air], p[air])

    if prod.any():
        if eos == 'JWL':
            p[prod] = np.maximum(jwl_pressure(rho[prod], e[prod], jwl),
                                 1.0)
            c[prod] = jwl_soundspeed(rho[prod], e[prod], p[prod], jwl)
        else:
            p[prod] = air_pressure(rho[prod], e[prod])
            c[prod] = air_soundspeed(rho[prod], p[prod])

    return p, c
