"""HD1-6: how an HD 1.3 charge catches fire.

WHY THIS IS NOT A DETAIL
------------------------
The 0-D model lit the whole charge at once. That is exactly right for the
experiment it was verified against - a closed-vessel sample IS ignited
uniformly - and exactly wrong for the event it is meant to describe. A
magazine does not light all at once. A flame spreads through a stack, or
packages fail one after another, and the charge is entrained over a time
that is usually far longer than any one item takes to burn.

It changes the answer by more than anything else in the model. Measured
here on 5 kg of double-base in a 1 m^3 chamber vented through 0.02 m^2,
with everything else held fixed, and REFINED in the cohort count until
the numbers stopped moving (see `cohorts` for why that qualifier is not
decoration - the earlier version of this table was not refined):

    uniform                       3.87 MPa
    flame spread over 0.5 s       2.20 MPa
    flame spread over 2 s         0.67 MPa
    flame spread over 10 s        0.14 MPa

a factor of 28 across a range of spread times that a real magazine could
easily span.

Note WHICH WAY it errs, because it is not the simple way. Uniform
ignition over-predicts the peak pressure, so for a pressure check it
looks conservative. But it also under-predicts the DURATION, and
`core/sdof.py` is about exactly that: duration decides whether a wall is
in the impulsive regime or the quasi-static one, and which regime it is
in decides which check applies at all. An assumption that is
conservative on the number while wrong about the regime is not
conservative - it is answering a different question.

WHY THE COHORTS CANNOT BE CONVOLVED
-----------------------------------
The obvious shortcut - solve one cohort, then superpose shifted copies -
does not work here, and the reason is the whole physics of HD 1.3.
Every cohort burns at a rate set by the pressure in the chamber, and
they all share one chamber. A cohort that lights late burns FASTER than
the first one did at the same age, because the earlier cohorts have
already raised the pressure. The cohorts are coupled through `p`, so they
have to be integrated together as one system. That is why
`deflagration.simulate` carries a burnt fraction per cohort rather than a
single number.

WHAT IS AND IS NOT MODELLED
---------------------------
This module says WHEN each part of the charge is lit, and nothing else.
It does not model flame spread itself: `spread_time` is an input, not a
prediction, because predicting it needs the stack geometry, the packaging
and the radiant field, none of which this code has. Treat it as the knob
it is, and sweep it.
"""

from dataclasses import dataclass

KINDS = ('uniform', 'flame_spread', 'progressive_package')

#: How the burning front grows through the stack, for 'flame_spread'.
#: The mass lit by time t goes as (t/T)**d with d = 1, 2, 3: a line of
#: items lit end to end, a layer burning outward from a point, or a pile
#: engulfed in all three directions. The exponent, not the spread time,
#: is what decides whether the release is front-loaded or back-loaded.
GEOMETRIES = {'line': 1, 'area': 2, 'volume': 3}


@dataclass(frozen=True)
class IgnitionScenario:
    """When each part of the charge is lit.

    kind          'uniform'             everything at t = 0
                  'flame_spread'        a front crossing a stack
                  'progressive_package' packages failing in turn
    n_cohorts     how many equal-mass groups the charge is split into.
                  One is the old behaviour. More resolves the entrainment
                  better and costs almost nothing, since the cost is in
                  the shared pressure solve rather than per cohort.
    spread_time   [s] from the first item lighting to the last. This is
                  an INPUT, not a prediction - see the module docstring.
    geometry      'line' | 'area' | 'volume', for 'flame_spread'
    source        where spread_time came from, if anywhere
    """
    kind: str = 'uniform'
    n_cohorts: int = 1
    spread_time: float = 0.0
    geometry: str = 'line'
    source: str = ''

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f'kind must be one of {KINDS}, not {self.kind!r}')
        if self.n_cohorts < 1:
            raise ValueError('n_cohorts must be at least 1')
        if self.spread_time < 0.0:
            raise ValueError('spread_time cannot be negative')
        if self.geometry not in GEOMETRIES:
            raise ValueError(f'geometry must be one of '
                             f'{tuple(GEOMETRIES)}, not {self.geometry!r}')
        if self.kind == 'uniform' and self.spread_time:
            raise ValueError("kind 'uniform' lights everything at t = 0; it "
                             'cannot also have a spread_time')
        if self.kind != 'uniform' and self.n_cohorts < 2:
            raise ValueError(f'{self.kind!r} needs at least 2 cohorts to '
                             f'mean anything - with one it IS uniform, and '
                             f'saying so is better than pretending')

    @property
    def calibration_only(self):
        """Uniform ignition is a laboratory condition. True here is a
        flag for the report, not a judgement on the run."""
        return self.kind == 'uniform'

    def cohorts(self):
        """[(mass_fraction, t_ignite)] - equal masses, unequal times.

        Splitting by MASS rather than by time is what makes refining `n`
        CONVERGE rather than drift: each group carries 1/n of the charge
        whatever the spread law, so refining n refines the timing only.

        THAT IS NOT THE SAME AS "n DOES NOT CHANGE THE ANSWER", which is
        what this docstring used to say, and the gap between the two is
        large enough to matter. `n` is a discretisation of a continuous
        flame spread into n instantaneous ignitions of C/n each, and the
        convergence is first order. In a chamber that has settled between
        ignitions - a slow magazine fire - a single such step is the
        whole pressure signal, and the peak reported is the size of the
        step. Measured at a 60 s spread, n = 20 comes out 62 % high.

        So `n` has to be refined until the answer stops moving, exactly
        like a mesh. `deflagration.simulate` does that by default and
        reports `cohort_converged`; see `deflagration._COHORT_TOL`.
        """
        n = self.n_cohorts
        frac = 1.0 / n
        if self.kind == 'uniform':
            return [(frac, 0.0)] * n
        if self.kind == 'flame_spread':
            d = GEOMETRIES[self.geometry]
            # cohort i is lit when the front has covered the middle of
            # its share of the mass: F(t) = (t/T)**d = (i + 0.5)/n
            return [(frac, self.spread_time * ((i + 0.5) / n) ** (1.0 / d))
                    for i in range(n)]
        # progressive_package: each package fails after the one before,
        # evenly through the window, the first at t = 0
        span = max(n - 1, 1)
        return [(frac, self.spread_time * i / span) for i in range(n)]

    def mass_entrainment(self, t):
        """Fraction of the charge LIT by time t (not burnt by time t)."""
        return sum(f for f, ti in self.cohorts() if ti <= t)

    @property
    def last_ignition(self):
        return max(ti for _f, ti in self.cohorts())


def uniform():
    """The closed-vessel condition: everything lit at t = 0.

    Physically correct for a calibration sample and for nothing else -
    see the module docstring.
    """
    return IgnitionScenario(kind='uniform', n_cohorts=1)
