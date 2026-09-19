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
    #: Pa - Chapman-Jouguet pressure, for `programmedIgnition` (guide
    #: 5.6.1.3, its beta burn). Values from jwl_parameters.md's table;
    #: self-consistency was spot-checked earlier as rho0*vDet^2/4, which
    #: lands within ~7 % of every row.
    Pcj: float = 0.0


MATERIALS = {
    'TNT':  Material(3.712e11,  3.23e9,   4.15,  0.95,  0.30, 1630.0,
                     4.29e6, 6930.0, Pcj=2.1e10),
    'C4':   Material(6.0977e11, 1.295e10, 4.50,  1.40,  0.25, 1601.0,
                     5.56e6, 8193.0, Pcj=2.8e10),
    'RDX':  Material(7.78e11,   7.07e9,   4.485, 1.068, 0.30, 1770.0,
                     5.15e6, 8750.0, Pcj=3.4e10),
    'HMX':  Material(7.783e11,  7.071e9,  4.20,  1.00,  0.30, 1890.0,
                     5.50e6, 9100.0, Pcj=3.9e10),
    'PETN': Material(6.17e11,   1.69e10,  4.40,  1.20,  0.25, 1770.0,
                     5.81e6, 8400.0, Pcj=3.1e10),
    'ANFO': Material(4.95e10,   1.89e9,   3.90,  1.10,  0.35,  850.0,
                     3.80e6, 4500.0, Pcj=5.0e9),
}

MATERIAL_NAMES = tuple(MATERIALS)   # combo/prompt order


@dataclass(frozen=True)
class Afterburn:
    """blastFoam `afterburnModel Miller` parameters.

    The model transports a burn fraction c with
        dc/dt = a (1 - c)^m p^n     (p in Pa, only where p > pMin)
    and releases Q0 * c J/kg on top of the JWL detonation energy - the
    products burning with atmospheric oxygen, which a pure detonation
    JWL run leaves out (that is the ~25 % Kingery-Bulmash gap
    test_foam_kb_anchor measures).

    Q0 scale: the fuel-rich explosives have an afterburn potential of
    (heat of combustion - heat of detonation); the oxygen-balanced ones
    have almost none. The values below are a FRACTION of that potential
    (mixing with air is incomplete in free field) and, together with the
    rate constants, were CALIBRATED in this repo against the
    Kingery-Bulmash free-air anchor (tests/test_foam_kb_anchor.py
    --afterburn) - they are not vendor- or paper-published constants.
    See ROADMAP N3 for the measured before/after ratios."""
    Q0: float           # J/kg   afterburn energy released at c = 1
    a: float            # 1/(s Pa^n)
    n: float = 1.0      # pressure exponent
    m: float = 0.5      # (1 - c) exponent
    pMin: float = 1.5e5   # Pa   no afterburn below this pressure


#: Per-material Miller parameters.
#:
#: TNT is CALIBRATED against the Kingery-Bulmash free-air anchor
#: (tests/test_foam_kb_anchor.py --afterburn), 1 kg TNT, gauges at
#: Z = 1 / 2 / 3 / 4 m/kg^(1/3). Current fit - Q0 = 2.0 MJ/kg,
#: a = 1.45e-5 - lands at 1.06 / 0.95 / 0.95 / 0.95, against
#: 0.89 / 0.85 / 0.86 / 0.87 with no afterburn at all.
#:
#: N5-3, why `a` and not Q0: the fit this replaced (a = 3.0e-4) was made
#: when the charge was resolved with 5 cells across its radius. T39
#: raised FOAM_EXP_CELLS to 8 and nobody refitted, which left the anchor
#: at 1.20 / 1.04 / 1.02 / 1.02 - a 20 % overshoot in the NEAR FIELD
#: only. Q0 scales all four gauges together, so pulling Z = 1 down to 1
#: with it would have dragged Z = 2..4 to ~0.88. The rate is the knob
#: that matches the symptom: releasing the afterburn energy more slowly
#: costs the Z = 1 peak (which is hit early, while the burn is still
#: going) far more than the later ones. Measured sweep, max |ratio - 1|
#: over the four gauges:
#:
#:     a = 3.0e-4  0.200      a = 1.7e-5  0.082
#:     a = 1.0e-4  0.134      a = 1.45e-5 0.055   <- fit
#:     a = 3.0e-5  0.088      a = 1.3e-5  0.058
#:     a = 1.0e-5  0.068      a = 3.0e-6  0.122
#:
#: The residual shape (Z = 1 high by 5 %, Z = 2..4 low by 5 %) is flat
#: against BOTH knobs - a Q0 trim in either direction makes the spread
#: worse - so 5 % is what this two-parameter Miller fit gives. Refit
#: after any change to what the charge deposits (N5-2 `scale`) or to
#: FOAM_EXP_CELLS, not before, or it gets calibrated twice.
#:
#: The others scale TNT's Q0 by OXYGEN BALANCE - how much oxygen the
#: molecule lacks to burn itself completely is what is left for the
#: atmosphere to supply: TNT -74 %, RDX/HMX -21.6 %, C4 ~-21 % (91 %
#: RDX), PETN -10.1 %, ANFO ~0 % (designed oxygen-balanced, so almost
#: no afterburn). Only the TNT row is anchored to data; treat the rest
#: as physically ordered estimates and calibrate before quoting.
AFTERBURN = {
    'TNT':  Afterburn(Q0=2.00e6, a=1.45e-5),
    'C4':   Afterburn(Q0=0.57e6, a=1.45e-5),
    'RDX':  Afterburn(Q0=0.58e6, a=1.45e-5),
    'HMX':  Afterburn(Q0=0.58e6, a=1.45e-5),
    'PETN': Afterburn(Q0=0.27e6, a=1.45e-5),
    'ANFO': Afterburn(Q0=0.10e6, a=1.45e-5),
}


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
