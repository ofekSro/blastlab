"""HD1-9: the same charge burning in the open, and the comparison.

The claim this file pins is TODO.md HD1's opening sentence made
numerical: the same material is negligible outside and dangerous in a
room. Both halves have to be COMPUTED for the comparison to be worth
anything - a table with one side asserted proves nothing.

It also pins the thing that makes the unconfined branch a separate model
rather than a parameter: it burns at a MEASURED atmospheric rate, and the
closed-vessel pair takes no part in it. Changing `a` and `n` by an order
of magnitude must not move an unconfined answer at all.

Run:  cd blastlab/tests && python test_unconfined.py
"""

import os
import sys
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import deflagration as d                   # noqa: E402
from blastlab.core import scenario as sc                      # noqa: E402
from blastlab.core import unconfined as u                     # noqa: E402
from blastlab.core.constants import P_AIR                     # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def _raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def spread(T, n=20):
    return sc.IgnitionScenario(kind='flame_spread', n_cohorts=n,
                               spread_time=T)


def main():
    print('UNCONFINED (HD1-9)')
    p = d.PROPELLANTS['double_base']

    # ── 1. it stands on its own datum ───────────────────────────────────
    print('\n  a separate model, not the confined one at p_amb')
    base = u.burn(p, 5.0, scenario=spread(60.0))
    # a and n are the closed-vessel pair. If they touched this branch at
    # all, the unconfined answer would be a three-decade extrapolation.
    wild = replace(p, a=p.a * 25.0, n=0.2)
    other = u.burn(wild, 5.0, scenario=spread(60.0))
    check('changing a by 25x and n by a factor of 4 does not move it',
          abs(other['mdot_max'] - base['mdot_max']) < 1e-12
          and abs(other['mach_max'] - base['mach_max']) < 1e-12,
          f"{other['mdot_max']:.9f} vs {base['mdot_max']:.9f} kg/s")
    # NOT "halving r_atm halves the peak rate": for a spread-limited fire
    # it does not, and assuming it did was wrong. Halving the rate
    # doubles how long each grain burns, so MORE cohorts overlap and the
    # peak barely moves. What it must do is stretch the event.
    slow = u.burn(replace(p, r_atm=p.r_atm / 2.0), 5.0,
                  scenario=spread(60.0))
    check('halving the atmospheric rate doubles how long a grain burns',
          abs(slow['grain_burn_time'] / base['grain_burn_time'] - 2.0) < 1e-9,
          f"{slow['grain_burn_time']:.2f} vs {base['grain_burn_time']:.2f} s")
    check('and stretches the whole event without raising the peak rate',
          slow['burn_time'] > base['burn_time']
          and slow['mdot_max'] <= base['mdot_max'] * 1.001,
          f"{slow['burn_time']:.1f} vs {base['burn_time']:.1f} s")
    check('nothing is extrapolated, and the run says so',
          base['extrapolated_fraction'] == 0.0)
    check('a propellant with no measured atmospheric rate is refused, '
          'rather than quietly using a p**n reach',
          _raises(lambda: u.burn(replace(p, r_atm=0.0), 5.0)))

    # ── 2. the burn itself ──────────────────────────────────────────────
    print('\n  the burn')
    # A degressive grain takes THREE times web/rate, not one: dz/dt goes
    # as (1-z)^(2/3), so the last of the web takes far longer than the
    # first. Using web/rate cut the burn off at a third of its length.
    check('a degressive grain takes 3 web/rate, not web/rate',
          abs(base['grain_burn_time'] - 3.0 * p.web / p.r_atm) < 1e-9,
          f"{base['grain_burn_time']:.3f} s")
    check('a neutral grain does take exactly web/rate',
          abs(u.burn(replace(p, form='neutral'), 5.0,
                     scenario=spread(60.0))['grain_burn_time']
              - p.web / p.r_atm) < 1e-9)
    check('everything burns',
          base['burnt_out'] and abs(base['z'][-1] - 1.0) < 1e-9)
    check('a slow fire is spread-limited, a fast one is not',
          u.burn(p, 5.0, scenario=spread(60.0))['spread_limited']
          and not u.burn(p, 5.0)['spread_limited'])
    check('total energy is the charge times its specific energy',
          abs(base['energy_total']
              - 5.0 * p.force / (p.gamma - 1.0)) < 1e-6 * base['energy_total'],
          f"{base['energy_total']/1e6:.3f} MJ")

    # ── 3. THE BLAST CLAIM, COMPUTED ────────────────────────────────────
    print('\n  why there is no blast - as a number, not a citation')
    machs = [u.burn(p, 5.0, scenario=spread(T))['mach_max']
             for T in (10.0, 30.0, 60.0, 300.0)]
    check('a slower fire expands more slowly, monotonically',
          all(a > b for a, b in zip(machs, machs[1:])),
          ' > '.join(f'{m:.4f}' for m in machs))
    check('a realistically slow magazine fire is far below the '
          'quasi-static threshold',
          machs[-1] < u.MACH_QUASI_STATIC / 2.0,
          f'Mach {machs[-1]:.4f} vs threshold {u.MACH_QUASI_STATIC}')
    check('and it is reported as negligible',
          u.burn(p, 5.0, scenario=spread(300.0))['blast_negligible'])
    check('the Mach number is an upper bound: a real stack has voids, so '
          'its surface is larger than the solid sphere used here',
          u.burn(p, 5.0, scenario=spread(60.0),
                 stack_area=base['stack_area'] * 3.0)['mach_max']
          < base['mach_max'])

    # The limit case, and why it is labelled rather than trusted.
    lim = u.burn(p, 5.0)
    check('lighting a whole pile at once is flagged as the impossible '
          'limit it is', lim['simultaneous_limit']
          and not u.burn(p, 5.0, scenario=spread(60.0))['simultaneous_limit'])
    check('and at that limit the expansion is NOT negligible - the '
          'no-blast claim rests on the fire being slow, not on the '
          'material alone',
          lim['mach_max'] > 10.0 * machs[-1],
          f"Mach {lim['mach_max']:.4f} simultaneous vs "
          f"{machs[-1]:.4f} over 300 s")

    # ── 4. THE COMPARISON - TODO.md HD1's opening claim ─────────────────
    #
    # THE MAIN CASE IS A REALISTIC VENT AND ITS ANSWER IS "NO", WHICH IS
    # THE FINDING.
    #
    # This section has been wrong twice and the corrections are worth
    # keeping, because both were the same mistake in different clothes:
    # a number quoted at a resolution nobody refined.
    #
    #   1. It ran at 0.02 m2 / 60 s and the old fixed-step integrator
    #      reported 3.75 x ambient. That was an integration error.
    #   2. The error-controlled integrator reported 1.06, and the test
    #      was then changed to a 0.002 m2 vent so that something above
    #      2 x would appear. That was choosing the input to get the
    #      output.
    #
    # So the main case is the realistic one and it is reported as a
    # RESULT: a 1 m3 magazine holding 5 kg, vented through 0.02 m2 - a
    # louvre of about a fifth of a square metre per cubic metre - with a
    # 60 s flame spread DOES NOT PRESSURISE. Converged, it reaches about
    # 1.03 x ambient, some 3 kPa. Nothing is being demonstrated by
    # shrinking the hole; the hole is the answer.
    #
    # The hand check that settles it, and it needs no model: a 60 s
    # spread of 5 kg generates at most 0.11 kg/s, while 0.02 m2 already
    # passes well over 1 kg/s at 1.2 x ambient - an order of magnitude
    # more than the source can supply. A chamber whose drain outruns its
    # tap cannot fill.
    print('\n  confined vs unconfined, both computed')
    # n = 80, not the 20 this test used to run at. The n-sequence for
    # this case is 3.04, 1.65, 1.20, 1.06, 1.03, 1.02 at n = 10 ... 320,
    # so 80 is the first count that supports the claim being made here -
    # "under 1.1, it does not pressurise" - and the tail only moves
    # further in that direction. Refining past 80 costs ~18 s a run and
    # buys a third decimal place of an answer that is already "no".
    s = spread(60.0, 80)
    conf, unconf, summ = u.compare(p, 5.0, 1.0, vent_area=0.02,
                                   scenario=s, t_end=120.0,
                                   p0_chamber=P_AIR, refine_cohorts=False)
    check('the same charge and the same fire, run through both models',
          conf['scenario_kind'] == unconf['scenario_kind'] == 'flame_spread')
    check('a realistic magazine vent does NOT pressurise, and that is the '
          'result rather than a failure to produce one',
          summ['confined_pressure_ratio'] < 1.1,
          f"{summ['confined_pressure_ratio']:.3f} x ambient, "
          f"{summ['confined_overpressure']/1e3:.1f} kPa")
    check('the vent outruns the fire by an order of magnitude, which is '
          'why - a hand check, not a model output',
          d._vent_mdot(1.2 * P_AIR, 1500.0, p, 0.02, 0.8, P_AIR,
                       m_p=0.05, m_a=0.5) > 10.0 * unconf['mdot_max'],
          f"vent {d._vent_mdot(1.2*P_AIR, 1500.0, p, 0.02, 0.8, P_AIR, m_p=0.05, m_a=0.5):.2f}"
          f" vs fire {unconf['mdot_max']:.3f} kg/s")
    check('and the run that produced it conserved to machine precision',
          conf['conservation_residual'] < 1e-9,
          f"{conf['conservation_residual']:.2e}")

    # THE COHORT COUNT IS A MESH. At 20 cohorts this same case reports
    # 1.65 x ambient, and the whole of that excess is the first cohort
    # lighting 0.25 kg in one instant. It is the reason the case above
    # is run at 320. A test that quoted 1.65 would be quoting its own
    # discretisation.
    print('\n  and the peak is refined, not quoted at whatever n was handy')
    coarse = d.simulate(p, 5.0, 1.0, vent_area=0.02, scenario=spread(60.0, 20),
                        t_end=120.0, p0_chamber=P_AIR)
    check('a coarse ignition staircase inflates the peak, and the run says '
          'so instead of reporting it flat',
          not coarse['cohort_converged']
          and coarse['cohort_refinement_error'] > 0.2,
          f"n=20 gives {coarse['p_max']/P_AIR:.3f} x against "
          f"{coarse['p_max_refined']/P_AIR:.3f} at 2n, "
          f"{coarse['cohort_refinement_error']:.0%} out")
    check('so the number this test used to report was half staircase',
          coarse['p_max'] > 1.5 * conf['p_max'],
          f"{coarse['p_max']/P_AIR:.3f} x at n=20 against "
          f"{conf['p_max']/P_AIR:.3f} at n=80")
    # A FAST FIRE IS CONVERGED AT THE SAME COHORT COUNT, which is the
    # whole reason this hid: the artefact grows with spread time, and
    # every case built while the module was being written was fast.
    check('the same 20 cohorts ARE converged on a 0.5 s spread - the '
          'artefact grows with spread time, so it hid in the fast cases',
          d.simulate(p, 5.0, 1.0, vent_area=0.02, scenario=spread(0.5, 20),
                     t_end=5.0, p0_chamber=P_AIR)['cohort_converged'])
    check('a uniform scenario is n-independent by construction, so it is '
          'converged without paying for a second run',
          d.simulate(p, 5.0, 1.0, vent_area=0.02, t_end=5.0)['cohort_converged'])

    # THE EDGE CASE, LABELLED AS ONE. 0.002 m2 is a tenth of the vent
    # above - a 45 mm slot in a room of this size, which is a blocked or
    # a deliberately sealed magazine and not a designed one. It is here
    # ONLY to show that the model does produce confined pressure when the
    # confinement is real, so that the "no" above is a measurement rather
    # than an inability.
    # It is still refining at n = 80 (1.92, against 1.79 at 160), so only
    # the claims that survive the rest of the sequence are asserted: it is
    # well above the realistic vent, it is a destructive pressure, and it
    # is under the 2 x label threshold. The exact ratio is not quoted.
    print('\n  the small-vent EDGE CASE - chosen to show trapped pressure')
    tight = u.compare(p, 5.0, 1.0, vent_area=0.002, scenario=spread(60.0, 80),
                      t_end=120.0, p0_chamber=P_AIR, refine_cohorts=False)[2]
    check('close the vent by 10x and the same fire does pressurise the room',
          tight['confined_pressure_ratio'] > 1.5,
          f"{tight['confined_pressure_ratio']:.2f} x ambient, "
          f"{tight['confined_overpressure']/1e3:.0f} kPa")
    check('so the realistic answer is a property of the VENT, not a limit '
          'of the model',
          tight['confined_pressure_ratio']
          > 1.5 * summ['confined_pressure_ratio'])

    print('\n  what governs, on each side')
    check('unconfined: no meaningful pressure at all',
          summ['unconfined_blast_negligible'])
    check('in the open the load is heat, which is why the thermal path is '
          'in scope',
          summ['governing_unconfined'] == 'thermal')
    # INSIDE, THE LABEL REFUSES RATHER THAN GUESSES.
    #
    # This check replaces one that pinned a 2 x ambient threshold. That
    # threshold was a round number wearing the clothes of a structural
    # criterion, and it failed in the direction that matters: the sealed
    # case below carries ~94 kPa of QUASI-STATIC overpressure, enough to
    # take an unreinforced masonry wall apart, and came back 'thermal'
    # because 94 < 101. Replacing it with a better round number would
    # mean typing a threshold out of a safety standard from memory,
    # which is the reason `core/qd.py` ships its table empty.
    check('with no element given, the label says undetermined instead of '
          'inventing a threshold - and hands back the pressure so a '
          'reader who HAS a wall in mind can decide',
          summ['governing_confined'] == 'undetermined'
          and summ['governing_confined_basis'].startswith('none')
          and summ['confined_overpressure'] > 0.0,
          f"{summ['confined_overpressure']/1e3:.1f} kPa, "
          f"{summ['governing_confined']}")
    check('and the sealed case is undetermined too, however large its '
          'pressure - the refusal is about having no element, not about '
          'the number being small',
          tight['governing_confined'] == 'undetermined',
          f"{tight['confined_overpressure']/1e3:.0f} kPa, still "
          f"'{tight['governing_confined']}'")

    # GIVEN AN ELEMENT IT IS DERIVED, and the two answers come from the
    # same pressure. A wall that yields under it is a pressure problem; a
    # wall that does not is not. That is a statement about a structure
    # rather than about a round number.
    print('\n  and given a wall, the label is computed from the wall')
    from blastlab.core import sdof as _sdof
    light = _sdof.Component(span=3.0, mass_per_area=100.0, Ru=20e3,
                            kE=2.0e6, support='simple')
    stout = _sdof.Component(span=3.0, mass_per_area=480.0, Ru=800e3,
                            kE=3.0e7, support='simple')
    s_light = u.compare(p, 5.0, 1.0, vent_area=0.002, scenario=spread(60.0, 80),
                        t_end=120.0, p0_chamber=P_AIR, refine_cohorts=False,
                        component=light)[2]
    s_stout = u.compare(p, 5.0, 1.0, vent_area=0.002, scenario=spread(60.0, 80),
                        t_end=120.0, p0_chamber=P_AIR, refine_cohorts=False,
                        component=stout)[2]
    check('the same 94 kPa yields a light panel, so for THAT wall pressure '
          'governs',
          s_light['governing_confined'] == 'pressure'
          and s_light['confined_yielded'],
          f"mu = {s_light['confined_ductility']:.2f}")
    check('and does not yield a 200 mm reinforced wall, so for THAT one it '
          'does not - one pressure, two answers, which is the point',
          s_stout['governing_confined'] == 'thermal'
          and not s_stout['confined_yielded'],
          f"mu = {s_stout['confined_ductility']:.3f}")
    check('and both say what the label was derived from',
          s_light['governing_confined_basis'] == 'sdof'
          and s_stout['governing_confined_basis'] == 'sdof')
    check('the confined side carries its extrapolation warning into the '
          'comparison, the unconfined side has none to carry',
          summ['confined_extrapolated_fraction'] > 0.99
          and unconf['extrapolated_fraction'] == 0.0)

    # ── 5. bookkeeping ──────────────────────────────────────────────────
    print('\n  bookkeeping')
    check('r_atm ships uncalibrated on every row',
          all(not d.PROPELLANTS[n].is_calibrated('r_atm')
              for n in d.PROPELLANT_NAMES))
    check('and a run reports whether the rate behind it was measured',
          base['r_atm_calibrated'] is False)
    check('a uniform run is still flagged as the laboratory condition',
          lim['calibration_only_scenario'] is True)
    check('a negative charge is refused', _raises(lambda: u.burn(p, -1.0)))

    print('\nUNCONFINED: '
          + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
