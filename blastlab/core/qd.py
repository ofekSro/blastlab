"""HD1-3e: quantity-distance, as a mechanism with no numbers in it.

THE TABLE IS EMPTY, AND THAT IS THE DESIGN
------------------------------------------
`CRITERIA` ships with nothing in it. Quantity-distance factors are
safety-siting numbers out of DoD 6055.09-M, AASTP-1 and their national
equivalents - they decide how far a magazine must sit from an occupied
building - and a wrong one is invisible: it produces a plausible
distance in metres with no symptom at all. Nothing in this file will
type one from memory, and nothing here guesses a default.

So a report with no criteria entered says **"no QD comparison - no
coefficients entered"**. It does not fall back, it does not interpolate,
and it does not print a zero that a reader could mistake for a
clearance. The owner enters the rows from the standard that applies to
them, and every row carries the `source` it came from, which is printed
beside the distance it produced.

This is the same standing `PROPELLANTS` has: the mechanism is here, the
data is not, and the code says which is which rather than shipping
something plausible.

WHY A SOURCE IS REQUIRED AND NOT ENCOURAGED
--------------------------------------------
`QDCriterion` REFUSES a row with an empty `source`. A factor without a
provenance is the failure mode this module exists to prevent - someone
remembering a number, or copying one out of a slide - and a field that
can be left blank will be left blank. Making it an error costs one
string at entry and removes the whole class.

THE TWO BASES, AND WHY 1.3 USUALLY NEEDS THE SECOND
---------------------------------------------------
'mass'      D = K * W**(1/3), the cube-root scaling every blast-siting
            table is built on. W is the net explosive weight.
'fireball'  D = K * R_fireball. For HD 1.3 the governing harm is usually
            the FIREBALL rather than the blast (see TODO.md HD1 and
            `core/thermal.py`), so most 1.3 criteria are written against
            its radius, and a cube-root rule applied to a deflagrating
            material answers a question about a detonation.

A 'fireball' criterion evaluated without a fireball radius raises rather
than falling back to the mass rule. The two are different physics and
silently swapping them would be the same mistake as entering an HD 1.3
charge as a TNT equivalent.
"""

from dataclasses import dataclass

BASES = ('mass', 'fireball')

#: DELIBERATELY EMPTY. See the module docstring. Populate it from the
#: standard that applies, or pass criteria to `compare` directly.
CRITERIA = {}

#: What a report prints when nothing has been entered. A sentence, not a
#: blank table and never a zero.
NO_CRITERIA = ('No QD comparison: no coefficients have been entered. '
               'Quantity-distance factors are safety-siting numbers from '
               'a standard, and this tool ships none - enter the rows '
               'that apply, each with its source.')


@dataclass(frozen=True)
class QDCriterion:
    """One quantity-distance rule, with where it came from.

    `k_factor`  the K in D = K W**(1/3) [m/kg^(1/3)], or the multiple of
                the fireball radius for a 'fireball' basis [-]
    `basis`     'mass' | 'fireball'
    `source`    REQUIRED. The standard, table and edition this came
                from. See the module docstring on why it cannot be
                blank.
    `protects`  free text - what the distance is protecting, e.g. an
                inhabited building or a public traffic route. Two rows
                from the same standard usually differ only in this, and
                a distance quoted without it is not an answer.
    """
    name: str
    k_factor: float
    basis: str = 'mass'
    source: str = ''
    protects: str = ''

    def __post_init__(self):
        if not str(self.name).strip():
            raise ValueError('a QD criterion needs a name')
        if self.basis not in BASES:
            raise ValueError(f'basis must be one of {BASES}, '
                             f'not {self.basis!r}')
        if self.k_factor <= 0:
            raise ValueError('the K factor must be positive')
        if not str(self.source).strip():
            raise ValueError(
                f"QD criterion '{self.name}' has no source. These are "
                f"safety-siting factors out of a standard and a wrong one "
                f"is invisible - it produces a plausible distance in "
                f"metres with no symptom. Name the standard, the table "
                f"and the edition.")


def qd_distance(crit, charge_kg=None, fireball_radius=None):
    """The distance `crit` requires, in metres.

    A 'fireball' criterion with no radius RAISES rather than falling
    back to the cube-root rule: the two are different physics, and for
    HD 1.3 the cube-root rule is the one that answers a question about
    a detonation.
    """
    if crit.basis == 'mass':
        if not charge_kg or charge_kg <= 0:
            raise ValueError(f"'{crit.name}' is a mass-based criterion and "
                             f"needs a positive net explosive weight")
        return crit.k_factor * float(charge_kg) ** (1.0 / 3.0)
    if not fireball_radius or fireball_radius <= 0:
        raise ValueError(
            f"'{crit.name}' is written against the FIREBALL radius and no "
            f"radius was given. It will not fall back to K W^(1/3): for "
            f"an HD 1.3 material the cube-root rule answers a question "
            f"about a detonation. Compute the fireball first - see "
            f"core/thermal.py.")
    return crit.k_factor * float(fireball_radius)


def compare(criteria, standoffs, charge_kg=None, fireball_radius=None):
    """Every criterion against every standoff.

    Returns a dict with `rows` - one per criterion, carrying the
    required distance, its source, and which of the given standoffs meet
    it - plus `note`, which is `NO_CRITERIA` when nothing was entered.

    `meets` is reported per standoff rather than as a single verdict,
    because a site usually has several distances that matter and they do
    not pass or fail together.
    """
    criteria = list(criteria or ())
    standoffs = [float(s) for s in (standoffs or ())]
    if not criteria:
        return {'rows': [], 'standoffs': standoffs, 'note': NO_CRITERIA,
                'have_criteria': False, 'governing': None}
    rows = []
    for c in criteria:
        d = qd_distance(c, charge_kg=charge_kg,
                        fireball_radius=fireball_radius)
        rows.append({
            'name': c.name,
            'basis': c.basis,
            'k_factor': c.k_factor,
            'source': c.source,
            'protects': c.protects,
            'distance_m': d,
            'meets': [s >= d for s in standoffs],
            'shortfall_m': [max(0.0, d - s) for s in standoffs],
        })
    gov = max(rows, key=lambda r: r['distance_m'])
    return {
        'rows': rows,
        'standoffs': standoffs,
        'note': '',
        'have_criteria': True,
        # The binding one, which is simply the largest - but naming it
        # saves a reader scanning a table for the row that decides the
        # site.
        'governing': gov['name'],
        'governing_distance_m': gov['distance_m'],
    }


def summary_line(res):
    """One line for a report. Says nothing rather than saying zero."""
    if not res['have_criteria']:
        return NO_CRITERIA
    g = res['governing_distance_m']
    short = [(s, r) for r in res['rows']
             for s, ok in zip(res['standoffs'], r['meets']) if not ok]
    txt = (f"{len(res['rows'])} criteria, governing "
           f"'{res['governing']}' at {g:.1f} m")
    if short:
        worst = min(s for s, _r in short)
        txt += (f' - {len(short)} standoff/criterion pairs fall short, '
                f'the nearest at {worst:.1f} m')
    elif res['standoffs']:
        txt += ' - every standoff given meets every criterion'
    return txt
