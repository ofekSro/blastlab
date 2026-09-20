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
    print('\n  confined vs unconfined, both computed')
    s = spread(60.0)
    conf, unconf, summ = u.compare(p, 5.0, 1.0, vent_area=0.02,
                                   scenario=s, t_end=120.0)
    check('the same charge and the same fire, run through both models',
          conf['scenario_kind'] == unconf['scenario_kind'] == 'flame_spread')
    check('confined: a real structural pressure load',
          summ['confined_pressure_ratio'] > 2.0,
          f"{summ['confined_pressure_ratio']:.2f} x ambient")
    check('unconfined: no meaningful pressure at all',
          summ['unconfined_blast_negligible'])
    check('so pressure governs inside and heat governs outside - which is '
          'why the thermal path is in scope',
          summ['governing_confined'] == 'pressure'
          and summ['governing_unconfined'] == 'thermal',
          f"{summ['governing_confined']} / {summ['governing_unconfined']}")
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
