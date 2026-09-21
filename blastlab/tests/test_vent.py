"""HD1-3c: the hand-off from the 0-D chamber to the CFD mesh.

Two claims are pinned here and they are the ones that decide whether the
venting stage means anything.

THE FIRST is that a per-phase check is not the same as a total. The
existing `check_handoff_energy` compares the SUM of what was written
against what was meant, so a wrong split between products and air that
happens to sum correctly passes it in silence. The Dalton-to-volume-
fraction conversion is exactly where such a split goes wrong, so it is
checked phase by phase.

THE SECOND is that combustion products are not hot air. At the same p
and T the two differ by a factor of ~1.6 in internal energy and ~15 % in
choked mass flow, and 15 % is precisely the threshold the 2-D
verification is pre-registered at - so that error would have PASSED the
check meant to catch it and been absorbed into the discharge
coefficient. It is asserted here, without WSL, as a PRECONDITION of that
verification rather than a part of it.

Run:  cd blastlab/tests && python test_vent.py
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import deflagration as d                   # noqa: E402
from blastlab.core import scenario as sc                      # noqa: E402
from blastlab.core import vent                                # noqa: E402
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


def _room_case():
    """The meshed cavity of the magazine HD1-3b writes, so the heat-loss
    comparison below is taken on the same room the golden uses."""
    from blastlab.core import room as _room
    return _room.measure((0.0, 0.0, 0.0), (3.0, 3.0, 2.0), 0.2, 0.1,
                         vent=('x_lo', 1.0, 2.0, 0.6, 1.4))['volume']


def main():
    print('VENT (HD1-3c)')
    p = d.PROPELLANTS['double_base']
    V = 1.0
    s = sc.IgnitionScenario(kind='flame_spread', n_cohorts=40,
                            spread_time=20.0)

    # A magazine that really does pressurise, so there is something to
    # hand over: sealed while the panel holds.
    shut = d.simulate(p, 5.0, V, vent_area=0.0, t_end=40.0, scenario=s,
                      p0_chamber=P_AIR, refine_cohorts=False)
    vented = d.simulate(p, 5.0, V, vent_area=0.002, t_end=60.0, scenario=s,
                        p0_chamber=P_AIR, refine_cohorts=False)

    # ── 1. which instant, and why that one ──────────────────────────────
    print('\n  choosing the instant')
    p_burst = 3.0 * P_AIR
    t_b, i_b = vent.open_time(shut, mode='burst', p_burst=p_burst)
    check('a burst panel opens at the FIRST crossing of its own pressure, '
          'not at the peak',
          shut['p'][i_b] >= p_burst
          and all(q < p_burst for q in shut['p'][:i_b]),
          f"t = {t_b:.4f} s at {shut['p'][i_b]/1e6:.4f} MPa")
    t_o, i_o = vent.open_time(vented, mode='open')
    check('an opening that was never shut is taken at the peak of a run '
          'whose vent was already open',
          abs(vented['p'][i_o] - max(vented['p'])) < 1e-9,
          f"t = {t_o:.4f} s at {vented['p'][i_o]/1e6:.4f} MPa")
    check('a panel that never bursts is REFUSED, and the message says the '
          'magazine holds rather than reporting a venting stage',
          _raises(lambda: vent.open_time(shut, mode='burst',
                                         p_burst=1e12)))
    check('a burst mode with no burst pressure is refused rather than '
          'quietly falling back to the peak, which is a different case '
          'with a different standing',
          _raises(lambda: vent.open_time(shut, mode='burst')))
    check('an unknown mode is refused',
          _raises(lambda: vent.open_time(shut, mode='sometimes')))

    # ── 2. THE PER-PHASE CHECK, which the total cannot do ───────────────
    print('\n  Dalton to volume fractions, phase by phase')
    st = vent.handoff(shut, p, mode='burst', p_burst=p_burst, volume_cfd=V)
    mp, ma = st.mass_by_phase()
    check('the products written into the cells are the products the 0-D '
          'model had - alpha_expl * rho_expl * V, not m_p / V',
          abs(mp - st.m_p) < 1e-12 * max(st.m_p, 1.0),
          f'{mp:.9f} vs {st.m_p:.9f} kg')
    check('and so is the air, separately - this is the check the total '
          'energy comparison passes in silence when the split is wrong',
          abs(ma - st.m_a) < 1e-12 * max(st.m_a, 1.0),
          f'{ma:.9f} vs {st.m_a:.9f} kg')
    check('the two fractions are a partition',
          abs(st.alpha_expl + st.alpha_air - 1.0) < 1e-15
          and 0.0 < st.alpha_expl < 1.0,
          f'alpha_expl = {st.alpha_expl:.6f}')
    check('and alpha_expl is NOT 1: a magazine holds a mixture, because '
          'the air that was in the room is comparable to the gas made',
          st.alpha_expl < 0.99,
          f'{st.alpha_expl:.4f} with m_a/m_p = {st.m_a/st.m_p:.3f}')
    check('rho_expl is the density of the products at the FULL pressure, '
          'which is larger than the chamber average m_p/V',
          st.rho_expl > st.m_p / V,
          f'{st.rho_expl:.4f} vs {st.m_p / V:.4f} kg/m3')
    check('and the mixture density is the total mass over the volume, '
          'whatever the split',
          abs(st.rho_mix - (st.m_p + st.m_a) / V) < 1e-12)

    # ── 3. PRODUCTS ARE NOT HOT AIR ─────────────────────────────────────
    #
    # A precondition of the 2-D verification, not a part of it: the error
    # this catches is ~15 % on the choked flow, and that verification is
    # pre-registered at 15 %, so it would have passed there and been
    # calibrated into Cd.
    print('\n  products against air, at the same p and T')
    e_products = st.p * V / (p.gamma - 1.0)
    e_air = st.p * V / (1.4 - 1.0)
    check('at the same p and V the products hold ~1.6x the internal '
          'energy of air, because gamma is 1.25 and not 1.40',
          abs(e_products / e_air - (1.4 - 1.0) / (p.gamma - 1.0)) < 1e-12
          and e_products / e_air > 1.5,
          f'{e_products / e_air:.4f}x')
    check('the molecular weight handed to blastFoam is the propellant s, '
          'around 20-30 g/mol, and NOT air s 28.97 by accident',
          15.0 < st.mol_weight_p < 45.0
          and abs(st.mol_weight_p - 28.97) > 1.0,
          f'{st.mol_weight_p:.2f} g/mol against air 28.97')
    # the number that would have hidden inside Cd
    args = (st.p, st.T, 0.01, 0.8, P_AIR)
    md_products = d._vent_mdot(st.p, st.T, p, 0.01, 0.8, P_AIR,
                               m_p=1.0, m_a=0.0)
    md_air = d._vent_mdot(st.p, st.T, p, 0.01, 0.8, P_AIR,
                          m_p=0.0, m_a=1.0)
    check('and the choked flow of air through the same hole is ~15 % off '
          'the products - which is exactly the threshold the 2-D check '
          'is pre-registered at, so it would have passed and gone into Cd',
          0.05 < abs(md_air / md_products - 1.0) < 0.30,
          f'{md_air / md_products - 1.0:+.1%} '
          f'({md_air:.4f} vs {md_products:.4f} kg/s)')
    check('the gamma written for the phase is the propellant s',
          abs(st.gamma_p - p.gamma) < 1e-15)

    # ── 4. THE MESH HAS A DIFFERENT CAVITY, AND T IS WHAT SURVIVES ──────
    #
    # Obstacle snapping costs an off-grid 5 m room 10.5 % of its volume
    # (core/room.py). The hand-off carries mass and energy across and
    # lets pressure follow, so T does not move at all - which is why a
    # golden should pin T and a ratio, never p itself.
    print('\n  a mesh cavity 10 % smaller than the 0-D volume')
    tight = vent.handoff(shut, p, mode='burst', p_burst=p_burst,
                         volume_cfd=0.9 * V)
    check('mass crosses unchanged',
          abs(tight.m_p - st.m_p) < 1e-15 and abs(tight.m_a - st.m_a) < 1e-15)
    check('energy crosses unchanged',
          abs(tight.E - st.E) < 1e-9 * st.E,
          f'{tight.E/1e6:.6f} vs {st.E/1e6:.6f} MJ')
    check('T DOES NOT MOVE - preserving m and E preserves e = E/m, and '
          'for a calorically perfect gas that is constant T. This is the '
          'quantity a golden should pin.',
          abs(tight.T - st.T) < 1e-12,
          f'{tight.T:.9f} K both ways')
    check('and the pressure rises by exactly the volume ratio, which is '
          'what the physics requires of a smaller room',
          abs(tight.p / st.p - 1.0 / 0.9) < 1e-12,
          f'{tight.p / st.p:.6f} vs {1/0.9:.6f}')
    check('the shift is reported rather than absorbed',
          abs(tight.pressure_from_volume_shift) > 0.1,
          f'{tight.pressure_from_volume_shift:+.2%}')
    check('the per-phase masses still come back right on the new volume',
          all(abs(a - b) < 1e-12 * max(b, 1.0) for a, b in
              zip(tight.mass_by_phase(), (tight.m_p, tight.m_a))))

    # ── 5. E_total COMES FROM THE SOLVER, NOT FROM THE HAND-OFF ─────────
    print('\n  the energy check, and why it is not circular')
    i = min(range(len(shut['t'])), key=lambda k: abs(shut['t'][k] - st.t_open))
    _R, cv_mix, _cp, _g = d.mixture(p, shut['m'][i], shut['m_air'][i])
    e_solver = (shut['m'][i] + shut['m_air'][i]) * cv_mix * shut['T'][i]
    ec = vent.energy_check(st, e_solver)
    check('the state carries the energy the solver had, to well inside '
          'the 2 % the existing hand-off check runs at',
          ec['ok'] and ec['rel'] < 1e-9,
          f"{ec['rel']:.2e}")
    check('and comparing it against air at the same p and T would FAIL '
          'that check - which is what makes it worth running',
          not vent.energy_check(st, st.p * V / 0.4)['ok'],
          f"air would give {st.p * V / 0.4 / 1e6:.2f} MJ against "
          f"{st.E/1e6:.2f}")

    # ── 6. VALIDITY: two metrics for a panel, ONE for an open vent ──────
    print('\n  what a 100 ms window covers')
    vb = vent.validity(shut, st, 0.1, prop=p, vent_area=0.002)
    check('a burst panel gets two metrics, because how much more gas the '
          'fire makes and how far the room empties are separate questions',
          'burn_fraction' in vb and 'blowdown_fraction' in vb,
          f"burn {vb['burn_fraction']:.3%}, "
          f"blowdown {vb['blowdown_fraction']:.3%}")
    # THE BUG THIS METRIC SHIPPED WITH FOR ONE RUN. The first version
    # read the drain rate off the run that chose the instant - which for
    # a burst panel is the SEALED run - and returned a blowdown fraction
    # of MINUS 3.4 %, because a sealed chamber with a fire in it gains
    # mass. It looked computed and was not about the thing it named.
    check('the drain rate comes from the hole that will be OPEN, not from '
          'the sealed run that chose the instant',
          vb['drain_rate_from'] == 'the vent that will be open'
          and 0.0 <= vb['blowdown_fraction'] <= 1.0,
          f"tau_drain {vb['tau_drain']:.4f} s, "
          f"blowdown {vb['blowdown_fraction']:.1%}")
    check('and calling it without the vent says so rather than returning '
          'a number about the wrong hole',
          any('not about the blowdown' in w
              for w in vent.validity(shut, st, 0.1)['warnings']))
    check('both burst metrics are labelled for what they are - one an '
          'upper bound, one an estimate - rather than passed off as '
          'measurements',
          vb['burn_fraction_is_upper_bound'] and vb['blowdown_is_estimate'])
    st_o = vent.handoff(vented, p, mode='open', volume_cfd=V)
    vo = vent.validity(vented, st_o, 0.1, prop=p, vent_area=0.002)
    check('an opening that was never shut gets ONE - at the peak the fire '
          'and the vent balance by definition, so the two would be the '
          'same number twice',
          'burn_fraction' not in vo and 'blowdown_fraction' not in vo
          and 'window_over_drain' in vo
          and vo['single_metric_because'],
          f"window/tau_drain = {vo['window_over_drain']:.3f}")
    check('the drain time of a magazine is measured, not assumed',
          math.isfinite(vo['tau_drain']) and vo['tau_drain'] > 0,
          f"tau_drain = {vo['tau_drain']:.4f} s")

    # ── 7. THE ARTEFACT, FLAGGED IN CODE AND NOT IN SOMEONE'S HEAD ──────
    print('\n  the shock tube that only one of the two modes really is')
    check('a burst panel really does let go suddenly, so its first front '
          'is the physics and peak and impulse mean what they say',
          st.first_front_is_artefact is False)
    check('an opening that was never shut had no diaphragm and no wave, '
          'so its first front is an ARTEFACT of initialising a '
          'pressurised room against ambient',
          st_o.first_front_is_artefact is True)
    check('and the validity report says so in words, next to the numbers',
          any('ARTEFACT' in w for w in vo['warnings']),
          str([w[:60] for w in vo['warnings']]))
    check('while the burst report does not claim an artefact it does not '
          'have', not any('ARTEFACT' in w for w in vb['warnings']))
    line = vent.summary_line(st_o, vo)
    check('the one-line summary carries the caveat with the number',
          'ARTEFACT' in line and 'MPa' in line)

    # ── 8. WHERE THE STATE CAME FROM, not just what it is ───────────────
    #
    # `simulate` is ADIABATIC by default, which is the conservative
    # choice for a pressure check and the wrong one to write into a mesh
    # without saying so: T and therefore p are then upper bounds, and
    # HD1-3b is about to put them in a golden. The state answers this
    # itself rather than leaving it to whoever called simulate.
    print('\n  the provenance of the state, carried with it')
    check('a state from an adiabatic run says so',
          st.adiabatic_source and st.wall_loss_fraction == 0.0)
    check('and warns that its T and p are upper bounds, in words',
          any('ADIABATIC' in w for w in st.warnings),
          str([w[:50] for w in st.warnings]))
    cooled = d.simulate(p, 5.0, V, vent_area=0.0, t_end=40.0, scenario=s,
                        p0_chamber=P_AIR, refine_cohorts=False,
                        h_c=200.0, wall_area=6.0)
    st_c = vent.handoff(cooled, p, mode='burst', p_burst=p_burst,
                        volume_cfd=V)
    check('a state from a run that gave its walls heat does NOT claim to '
          'be adiabatic, and reports how much went',
          not st_c.adiabatic_source and st_c.wall_loss_fraction > 0.0,
          f'{st_c.wall_loss_fraction:.1%} of the energy released')

    # ── 8b. WHERE THE HEAT LOSS ACTUALLY SHOWS, and where it does not ───
    #
    # An earlier version of this file compared T between the two runs and
    # reported 2.2 %, which is the LEAST informative number in the set.
    # At a burst pressure the pressure is fixed BY THE TRIGGER, so T is
    # nearly determined by the composition and has almost nowhere to go.
    # The effect is in WHEN the panel bursts and HOW MUCH has burnt by
    # then: a cooled chamber climbs to p_burst more slowly, so it gets
    # there later and with more propellant consumed.
    #
    # Measured on a 20 kg magazine in 12.17 m3, adiabatic -> h_c = 200:
    #
    #     t_burst      +9.45 %
    #     mass burnt  +12.35 %
    #     alpha_expl  +10.79 %
    #     E           +3.58 %
    #     T           +1.38 %     <- the one that was being quoted
    #
    # AND T DOES NOT EVEN MOVE IN A FIXED DIRECTION. On that case it goes
    # UP with mild cooling, because the extra burnt propellant outweighs
    # the heat lost; at h_c = 500 it turns over and comes down. So the
    # old check was pinning an accident of one geometry as if it were a
    # law. These four are the quantities that carry the effect.
    print('\n  and where the heat loss shows: not in T')
    big = _room_case()
    ad = d.simulate(p, 20.0, big, vent_area=0.0, t_end=60.0, scenario=s,
                    p0_chamber=P_AIR, refine_cohorts=False)
    co = d.simulate(p, 20.0, big, vent_area=0.0, t_end=60.0, scenario=s,
                    p0_chamber=P_AIR, refine_cohorts=False,
                    h_c=200.0, wall_area=6.0)
    pb = 3.0 * P_AIR
    s_ad = vent.handoff(ad, p, mode='burst', p_burst=pb, volume_cfd=big)
    s_co = vent.handoff(co, p, mode='burst', p_burst=pb, volume_cfd=big)
    check('a cooled chamber reaches the burst pressure LATER',
          s_co.t_open > s_ad.t_open * 1.02,
          f'{s_ad.t_open:.4f} -> {s_co.t_open:.4f} s '
          f'({s_co.t_open/s_ad.t_open - 1.0:+.2%})')
    check('with MORE propellant burnt by then - the effect T cannot show',
          s_co.m_p > s_ad.m_p * 1.05,
          f'{s_ad.m_p:.5f} -> {s_co.m_p:.5f} kg '
          f'({s_co.m_p/s_ad.m_p - 1.0:+.2%})')
    check('so the mixture handed over is RICHER in products',
          s_co.alpha_expl > s_ad.alpha_expl * 1.05,
          f'{s_ad.alpha_expl:.5f} -> {s_co.alpha_expl:.5f} '
          f'({s_co.alpha_expl/s_ad.alpha_expl - 1.0:+.2%})')
    check('and it carries more energy, not less, despite having given '
          'the walls most of what was released',
          s_co.E > s_ad.E,
          f'{s_ad.E/1e6:.4f} -> {s_co.E/1e6:.4f} MJ '
          f'({s_co.E/s_ad.E - 1.0:+.2%}), with '
          f'{co["wall_loss_fraction"]:.0%} gone to the walls')
    check('while T moves by far the least of the four - which is why '
          'comparing T was the wrong comparison',
          abs(s_co.T/s_ad.T - 1.0) < 0.5 * abs(s_co.m_p/s_ad.m_p - 1.0),
          f'T {s_co.T/s_ad.T - 1.0:+.2%} against mass '
          f'{s_co.m_p/s_ad.m_p - 1.0:+.2%}')
    # AND ITS DIRECTION IS NOT FIXED, pinned so nobody re-derives a law
    # from one case. More cooling eventually turns it over.
    hot = vent.handoff(
        d.simulate(p, 20.0, big, vent_area=0.0, t_end=60.0, scenario=s,
                   p0_chamber=P_AIR, refine_cohorts=False,
                   h_c=500.0, wall_area=6.0),
        p, mode='burst', p_burst=pb, volume_cfd=big)
    check('T is not even MONOTONE in the wall coefficient: mild cooling '
          'raises it (more burnt) and harder cooling turns it over - so '
          'no direction may be asserted from one case',
          s_co.T > s_ad.T and hot.T < s_co.T,
          f'{s_ad.T:.2f} (adiabatic) -> {s_co.T:.2f} (h_c 200) -> '
          f'{hot.T:.2f} (h_c 500) K')
    check('a run that did not conserve is refused outright rather than '
          'handed to a mesh',
          _raises(lambda: vent.handoff(
              dict(shut, stop_reason='conservation_violation'), p,
              mode='burst', p_burst=p_burst, volume_cfd=V)))
    coarse = d.simulate(p, 5.0, V, vent_area=0.0, t_end=40.0,
                        p0_chamber=P_AIR,
                        scenario=sc.IgnitionScenario(kind='flame_spread',
                                                     n_cohorts=6,
                                                     spread_time=20.0))
    if not coarse['cohort_converged']:
        check('a state taken off an unconverged 0-D peak says the instant '
              'was set by the ignition staircase, not by the fire',
              any('staircase' in w for w in vent.handoff(
                  coarse, p, mode='burst', p_burst=p_burst,
                  volume_cfd=V).warnings))

    # ── 9. refusals ─────────────────────────────────────────────────────
    print('\n  refusals')
    check('a zero CFD window is refused',
          _raises(lambda: vent.validity(shut, st, 0.0)))
    check('a zero mesh volume is refused',
          _raises(lambda: vent.handoff(shut, p, mode='burst',
                                       p_burst=p_burst, volume_cfd=-1.0)))

    print('\nVENT: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
