"""Explosive material table for the blastFoam backend.

JWL parameters from the LLNL Explosives Handbook (Dobratz & Crawford,
1985) via BlastFoam_Basic_Info/blastfoam_toolkit/docs/jwl_parameters.md.
The TNT row matches core.constants.JWL_TNT exactly; thermo defaults
(Cv, Murnaghan reactants) follow the shipped freeField tutorial.

Pure data - safe to import from the GUI at startup.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    A: float            # Pa
    B: float            # Pa
    R1: float
    R2: float
    omega: float
    rho0: float         # kg/m^3  unreacted density
    e0: float           # J/kg    specific detonation energy
    vDet: float         # m/s     detonation velocity
    Cv_products: float = 1400.0     # J/(kg K)  (freeField tutorial)
    Cv_reactants: float = 815.0
    Gamma_reactants: float = 0.25   # Murnaghan
    molWeight: float = 55.0         # g/mol


MATERIALS = {
    'TNT':  Material(3.712e11,  3.23e9,   4.15,  0.95,  0.30, 1630.0,
                     4.29e6, 6930.0),
    'C4':   Material(6.0977e11, 1.295e10, 4.50,  1.40,  0.25, 1601.0,
                     5.56e6, 8193.0),
    'RDX':  Material(7.78e11,   7.07e9,   4.485, 1.068, 0.30, 1770.0,
                     5.15e6, 8750.0),
    'HMX':  Material(7.783e11,  7.071e9,  4.20,  1.00,  0.30, 1890.0,
                     5.50e6, 9100.0),
    'PETN': Material(6.17e11,   1.69e10,  4.40,  1.20,  0.25, 1770.0,
                     5.81e6, 8400.0),
    'ANFO': Material(4.95e10,   1.89e9,   3.90,  1.10,  0.35,  850.0,
                     3.80e6, 4500.0),
}

MATERIAL_NAMES = tuple(MATERIALS)   # combo/prompt order


def E0(m):
    """blastFoam initiation energy [J/m^3] (verified convention:
    freeField C4 uses E0 = 9.0e9 = 1601 * 5.56e6)."""
    return m.rho0 * m.e0


def charge_radius(mass, m, planar=False):
    """Initial charge radius [m]: sphere from a mass in kg, or (2D
    planar) a cylinder per unit depth from kg/m."""
    if planar:
        return math.sqrt(mass / (math.pi * m.rho0))
    return (3.0 * mass / (4.0 * math.pi * m.rho0)) ** (1.0 / 3.0)
