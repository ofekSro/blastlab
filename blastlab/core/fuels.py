"""Deflagrating (HD 1.3) materials: the propellant table and its grain
geometry. Pure data - safe to import from the GUI at startup.

This is the HD1.3 counterpart of `solvers/foam/materials.py`, and the
split is for the same reason: a table with several consumers does not
belong inside any one of them. `core/deflagration.py` is only the first.
The venting stage needs `covolume` and the derived molecular weight to
write an `AbelNobel` phase; the thermal path needs `T_flame` and the
condensed-residue properties; the closed-vessel calibration WRITES rows
here; and a GUI that lists the material names must not have to import an
ODE integrator to do it.

A propellant is NOT a `Material`. It has no JWL expansion curve, no
detonation velocity and no Chapman-Jouguet pressure, because it does not
detonate - it burns at a pressure-dependent rate from its surface
inwards. The two tables have no field in common except a density, and
merging them would only invite one to be used where the other belongs.

STATUS OF THE NUMBERS
---------------------
Every row is REPRESENTATIVE LITERATURE RANGE for a CLASS of material, not
product data, and `calibrated=False` on all of them is deliberate and is
enforced by the test suite. The Vieille pair (`a`, `n`) in particular
varies lot to lot, and `a` sets the whole timescale linearly - nothing
here is quotable without a closed-vessel test of the actual material.
That is exactly the standard `materials.py` holds its non-TNT afterburn
rows to (see the long comment there, and TODO.md P1-4).
"""

from dataclasses import dataclass

FORMS = ('neutral', 'degressive', 'progressive')


@dataclass(frozen=True)
class Propellant:
    """A deflagrating (HD 1.3) material.

    force        lambda = R * T_flame [J/kg]. The "impetus" or "force
                 constant" of interior ballistics; sets the pressure a
                 given mass reaches in a given volume.
    covolume     b [m^3/kg]. The Noble-Abel co-volume - roughly the volume
                 the product molecules themselves occupy. ~1e-3 for most
                 propellant gases, i.e. 1 litre per kg, which is NOT
                 negligible against a chamber of a few litres.
    rho          solid density [kg/m^3]
    T_flame      isochoric flame temperature [K]
    a, n         Vieille burn law r = a * p**n, r in m/s with p in Pa
    gamma        ratio of specific heats of the product gas
    web          w0 [m]: the burning distance from the surface to
                 burn-out. For a slab burning on both faces this is the
                 half-thickness; dZ/dt = sigma(Z) * r / w0.
    form         'neutral' | 'degressive' | 'progressive'
    theta        progressivity, used only by form='progressive'
    calibrated   False everywhere on purpose - see the module docstring.
    """
    force: float
    covolume: float
    rho: float
    T_flame: float
    a: float
    n: float
    gamma: float = 1.25
    web: float = 1.0e-3
    form: str = 'degressive'
    theta: float = 1.0
    calibrated: bool = False

    @property
    def R(self):
        """Specific gas constant [J/(kg K)] - force / flame temperature."""
        return self.force / self.T_flame

    @property
    def cv(self):
        return self.R / (self.gamma - 1.0)

    @property
    def cp(self):
        return self.gamma * self.cv


#: Representative classes, NOT product data. See the module docstring.
#: force/T_flame/covolume are the usual textbook ranges for each class;
#: the Vieille pair is where lot-to-lot variation really lives.
PROPELLANTS = {
    # nitrocellulose only - the lowest-energy, coolest of the three
    'single_base': Propellant(force=0.95e6, covolume=1.05e-3, rho=1600.0,
                              T_flame=2500.0, a=5.0e-8, n=0.85,
                              gamma=1.25, web=1.0e-3, form='degressive'),
    # NC + nitroglycerine - hotter and faster
    'double_base': Propellant(force=1.10e6, covolume=1.00e-3, rho=1650.0,
                              T_flame=3000.0, a=8.0e-8, n=0.90,
                              gamma=1.24, web=1.0e-3, form='degressive'),
    # AP/HTPB-like composite - lower pressure exponent, near-neutral burn
    'composite': Propellant(force=1.00e6, covolume=1.10e-3, rho=1750.0,
                            T_flame=3000.0, a=3.0e-6, n=0.35,
                            gamma=1.20, web=3.0e-3, form='neutral'),
}

PROPELLANT_NAMES = tuple(PROPELLANTS)


def form_factor(prop, Z):
    """sigma(Z) = S(Z)/S0, the burning surface relative to its initial value.

    neutral      a slab or a tube burning inward and outward at once, the
                 area changes cancel -> 1
    degressive   a sphere or a cord: the surface shrinks as it burns, and
                 for a sphere S ~ r^2 while the burnt fraction goes as
                 r^3, hence (1 - Z)^(2/3)
    progressive  a multi-perforated grain, whose internal perforations
                 grow faster than the outside shrinks -> 1 + theta*Z

    Grain geometry, not solver state, which is why it lives beside the
    table rather than beside the integrator.
    """
    Z = min(max(Z, 0.0), 1.0)
    if prop.form == 'neutral':
        return 1.0
    if prop.form == 'progressive':
        return 1.0 + prop.theta * Z
    return (1.0 - Z) ** (2.0 / 3.0)
