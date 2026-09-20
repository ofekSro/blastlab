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
product data. The Vieille pair (`a`, `n`) in particular varies lot to
lot, and `a` sets the whole timescale linearly - nothing here is quotable
without a closed-vessel test of the actual material. That is exactly the
standard `materials.py` holds its non-TNT afterburn rows to (see the long
comment there, and TODO.md P1-4).

`uncalibrated` names the fields THIS ROW has no measurement behind, one
entry per field rather than one flag per row, because they do not all
become known at the same time: a closed-vessel test fixes `a`, `n` and
the validity window it was measured over, and says nothing whatsoever
about the low-pressure extinction limit. `calibrated` is derived from it,
so the two cannot drift apart.

THE VALIDITY WINDOW IS THE MODEL'S BIGGEST RISK, AND IT IS WHY IT IS HERE
------------------------------------------------------------------------
A closed-vessel test measures the burn law where a closed vessel reaches
pressure: tens to hundreds of MPa. The quasi-static pressure inside a
vented magazine is 0.1-2 MPa. Using `r = a p^n` there is an
extrapolation of two to three DECADES below the data, and in an
extrapolation that long the dominant error is in the exponent, not the
coefficient - which is why the sensitivity band has to sweep `n`, and
why `p_valid_min`/`p_valid_max` travel with the row instead of living in
a comment. `deflagration.simulate` reports the fraction of the burn that
ran outside this window so the number cannot be quoted without it.

WHY p_extinction SHIPS AT ZERO
------------------------------
The solver supports a low-pressure extinction limit and `simulate` will
stop a burn that falls below it. Every row nevertheless ships with
`p_extinction = 0.0`, meaning "not modelled", because the number that is
easy to look up is the wrong number to use here.

The published low-pressure deflagration limit - around 0.5 MPa for a
double-base propellant - is measured on a SINGLE STRAND at ambient
temperature in a strand burner. A magazine fire is a hot stack with
radiant feedback between neighbouring items, and it sustains far below
the strand limit. That is precisely why HD 1.3 storage fires exist at
all. Applying the strand figure to bulk burning was tried here and gives
the obviously false answer that nothing burns: with a realistic igniter
converting 1 % of the charge, not one of the shipped loadings could
sustain combustion, and forcing them to sustain needs an "igniter" that
burns 95 % of the charge first, at which point the result is an artefact
of the seed rather than a burn.

So the honest default is to leave it off, and to make turning it on a
deliberate per-scenario act with a number the user can defend. It is
BINARY to the answer - the burn either continues or it does not - which
makes it the first thing a sensitivity band should sweep and the last
thing to set from a handbook without thinking.
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

    p_valid_min  the pressure window the Vieille pair was MEASURED over
    p_valid_max  [Pa]. Outside it `r = a p^n` is an extrapolation and
                 `deflagration.simulate` says how much of the burn spent
                 its time there. See the module docstring.
    p_extinction [Pa] the low-pressure deflagration limit: below it the
                 burn rate is taken as zero and the charge goes out.
                 **Ships as 0.0 - not modelled - and that is a physics
                 decision, not an oversight.** See below.

    uncalibrated names of the fields with no measurement behind them
    calibrated   derived: True only when `uncalibrated` is empty
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
    p_valid_min: float = 0.0
    p_valid_max: float = float('inf')
    p_extinction: float = 0.0
    uncalibrated: tuple = ()

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

    @property
    def calibrated(self):
        """True only when every field has a measurement behind it.

        Derived rather than stored so a row cannot claim calibration
        while still listing placeholder fields.
        """
        return not self.uncalibrated

    def is_calibrated(self, field):
        """Does THIS field rest on a measurement for this row?"""
        return field not in self.uncalibrated

    def in_validity_window(self, p):
        return self.p_valid_min <= p <= self.p_valid_max


#: Fields no shipped row has data behind. `web` is the geometry of one
#: specific grain lot and has no generic value at all; `a`/`n` are class
#: midpoints; `p_extinction` cannot come from closed-vessel data even in
#: principle. `p_valid_*` describe where each class is normally
#: characterised, which is knowledge about the METHOD rather than about
#: the material, so they are listed too until a real test defines them.
_PLACEHOLDER = ('a', 'n', 'web', 'p_extinction', 'p_valid_min',
                'p_valid_max')

#: Representative classes, NOT product data. See the module docstring.
#: force/T_flame/covolume are the usual textbook ranges for each class;
#: the Vieille pair is where lot-to-lot variation really lives.
#:
#: The two gun propellants carry a closed-vessel window (tens to hundreds
#: of MPa, where a closed vessel actually reaches pressure) and a
#: low-pressure deflagration limit of order half a MPa. The composite is
#: characterised in a strand burner at motor pressures instead, which is
#: an order of magnitude lower, and AP composites sustain a flame further
#: down - so for a magazine at 0.1-2 MPa the composite row is the ONLY
#: one whose burn law is anywhere near its measured window. That is a
#: real, load-bearing difference between the classes, not bookkeeping.
PROPELLANTS = {
    # nitrocellulose only - the lowest-energy, coolest of the three
    'single_base': Propellant(force=0.95e6, covolume=1.05e-3, rho=1600.0,
                              T_flame=2500.0, a=5.0e-8, n=0.85,
                              gamma=1.25, web=1.0e-3, form='degressive',
                              p_valid_min=50.0e6, p_valid_max=300.0e6,
                              p_extinction=0.0,
                              uncalibrated=_PLACEHOLDER),
    # NC + nitroglycerine - hotter and faster
    'double_base': Propellant(force=1.10e6, covolume=1.00e-3, rho=1650.0,
                              T_flame=3000.0, a=8.0e-8, n=0.90,
                              gamma=1.24, web=1.0e-3, form='degressive',
                              p_valid_min=50.0e6, p_valid_max=300.0e6,
                              p_extinction=0.0,
                              uncalibrated=_PLACEHOLDER),
    # AP/HTPB-like composite - lower pressure exponent, near-neutral burn
    'composite': Propellant(force=1.00e6, covolume=1.10e-3, rho=1750.0,
                            T_flame=3000.0, a=3.0e-6, n=0.35,
                            gamma=1.20, web=3.0e-3, form='neutral',
                            p_valid_min=1.0e6, p_valid_max=15.0e6,
                            p_extinction=0.0,
                            uncalibrated=_PLACEHOLDER),
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
