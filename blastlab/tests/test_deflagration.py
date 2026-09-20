"""HD1-1: the 0-D deflagration (HD 1.3) gas-generation model.

The whole point of this model is that it has an EXACT answer to check
against. A closed vessel with all the propellant burnt must reach

    p_max = force * C / (V0 - b * C)
    T     = T_flame
    m     = C

straight from the Noble-Abel EOS and the definition of the force constant
(force = R * T_flame). Nothing here is calibrated against a real material -
see the module docstring - so an analytic limit plus conservation is the
only verification available, and it is worth a lot: it caught two real
integrator bugs while this file was being written.

  1. The step never grew past its seeded value, so a slow composite burn
     hit the step cap at t = 2 s of a 5 s burn and reported a peak 87 %
     low - with no error, just a wrong number.
  2. RK4 overshot Z = 1 and the overshoot was clipped, leaving m and E
     integrated against a dZ taken beyond burn-out: m_end came out at
     1.00066 * C, i.e. more gas than there was propellant.

Both are pinned below. No WSL, no solver, runs in about a second.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import deflagration as d                  # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def main():
    print('DEFLAGRATION (HD1-1)')

    # ── 1. thermodynamic identities ─────────────────────────────────────
    print('\n  the propellant relations')
    for name in d.PROPELLANT_NAMES:
        p = d.PROPELLANTS[name]
        check(f'{name}: R = force / T_flame',
              abs(p.R - p.force / p.T_flame) < 1e-9)
        check(f'{name}: cp - cv = R',
              abs((p.cp - p.cv) - p.R) < 1e-6 * p.R)
        check(f'{name}: force = (gamma - 1) * cv * T_flame',
              abs(p.force - (p.gamma - 1.0) * p.cv * p.T_flame)
              < 1e-6 * p.force)
    check('no row claims to be calibrated',
          not any(d.PROPELLANTS[n].calibrated for n in d.PROPELLANT_NAMES))

    # ── 2. the analytic closed-vessel limit ─────────────────────────────
    print('\n  the analytic limit')
    p = d.PROPELLANTS['double_base']
    check('p_max = force * C / (V - b C)',
          abs(d.closed_vessel_pmax(p, 5.0, 1.0)
              - p.force * 5.0 / (1.0 - p.covolume * 5.0)) < 1e-6)
    check('covolume RAISES the pressure over an ideal gas',
          d.closed_vessel_pmax(p, 5.0, 1.0) > p.force * 5.0 / 1.0)
    try:
        d.closed_vessel_pmax(p, 2000.0, 1.0)      # covolume fills the vessel
        check('a charge that cannot fit is refused', False, 'no raise')
    except ValueError as exc:
        check('a charge that cannot fit is refused', 'co-volume' in str(exc))

    # ── 3. the integrator against that limit ────────────────────────────
    print('\n  the closed vessel, integrated')
    for name in d.PROPELLANT_NAMES:
        prop = d.PROPELLANTS[name]
        t_end = 120.0 if name == 'composite' else 5.0
        for C, V in ((5.0, 1.0), (1.0, 2.0), (20.0, 10.0)):
            ana = d.closed_vessel_pmax(prop, C, V)
            r = d.simulate(prop, C, V, vent_area=0.0, t_end=t_end)
            pk, _t = d.peak(r)
            rel = abs(pk - ana) / ana
            check(f'{name} C={C:g} V={V:g}: peak within 0.1 % of analytic',
                  rel < 1e-3, f'{pk/1e5:.3f} vs {ana/1e5:.3f} bar '
                              f'({rel*100:.4f} %)')
            check(f'{name} C={C:g} V={V:g}: burnt out, not step-capped',
                  r['burnt_out'] and not r['hit_step_cap'],
                  f'Z={r["Z"][-1]:.6f} steps={r["steps"]}')
            # bug 2: more gas than propellant
            check(f'{name} C={C:g} V={V:g}: gas mass == charge mass',
                  abs(r['m'][-1] - C) < 1e-9 * C,
                  f'{r["m"][-1]:.9f} vs {C:g} kg')
            check(f'{name} C={C:g} V={V:g}: ends at the flame temperature',
                  abs(r['T'][-1] - prop.T_flame) < 1e-6 * prop.T_flame,
                  f'{r["T"][-1]:.1f} vs {prop.T_flame:g} K')

    # bug 1: a slow burn must not be silently truncated
    slow = d.PROPELLANTS['composite']
    short = d.simulate(slow, 5.0, 1.0, vent_area=0.0, t_end=2.0)
    check('a burn cut short reports burnt_out False rather than a low peak',
          short['burnt_out'] is False and short['p_max'] <
          d.closed_vessel_pmax(slow, 5.0, 1.0),
          f'Z={short["Z"][-1]:.4f}')

    # ── 4. the form function ────────────────────────────────────────────
    print('\n  the form function')
    neutral = d.Propellant(force=1e6, covolume=1e-3, rho=1600.0,
                           T_flame=3000.0, a=1e-7, n=0.9, form='neutral')
    degress = d.Propellant(force=1e6, covolume=1e-3, rho=1600.0,
                           T_flame=3000.0, a=1e-7, n=0.9, form='degressive')
    progr = d.Propellant(force=1e6, covolume=1e-3, rho=1600.0,
                         T_flame=3000.0, a=1e-7, n=0.9, form='progressive',
                         theta=2.0)
    check('neutral is flat', all(abs(d.form_factor(neutral, z) - 1.0) < 1e-12
                                 for z in (0.0, 0.3, 0.7, 1.0)))
    check('degressive starts at 1 and vanishes at burn-out',
          abs(d.form_factor(degress, 0.0) - 1.0) < 1e-12
          and abs(d.form_factor(degress, 1.0)) < 1e-12)
    check('degressive is monotonically decreasing',
          all(d.form_factor(degress, a) > d.form_factor(degress, b)
              for a, b in ((0.0, 0.3), (0.3, 0.7), (0.7, 0.99))))
    check('progressive grows to 1 + theta',
          abs(d.form_factor(progr, 1.0) - 3.0) < 1e-12)

    # ── 5. venting ──────────────────────────────────────────────────────
    print('\n  venting')
    peaks = []
    for area in (0.0, 0.001, 0.01, 0.1):
        r = d.simulate(p, 5.0, 1.0, vent_area=area, t_end=2.0)
        peaks.append((area, r['p_max'], r['p'][-1]))
    check('a bigger vent always gives a lower peak',
          all(peaks[i][1] > peaks[i + 1][1] for i in range(len(peaks) - 1)),
          ' > '.join(f'{v/1e5:.1f}' for _a, v, _e in peaks) + ' bar')
    check('a closed vessel does not decay',
          abs(peaks[0][2] - peaks[0][1]) < 1e-6 * peaks[0][1])
    # Tight on purpose, and tight on BOTH sides. The vent stops at ambient
    # because the model has no inflow, so a chamber that finishes well
    # below ambient has been stranded there by an over-long step - which
    # is exactly what a 5 % mass step did (0.58 bar against 1.01).
    check('a large vent decays back to ambient, without undershooting it',
          0.9 * d.P_AMB <= peaks[-1][2] <= 1.1 * d.P_AMB,
          f'{peaks[-1][2]/1e5:.3f} bar vs ambient {d.P_AMB/1e5:.3f}')
    check('venting removes mass',
          d.simulate(p, 5.0, 1.0, vent_area=0.01, t_end=2.0)['m'][-1] < 5.0)

    # ── 6. the burn is physical ─────────────────────────────────────────
    print('\n  monotonicity')
    r = d.simulate(p, 5.0, 1.0, vent_area=0.0, t_end=2.0)
    check('Z never decreases', all(b >= a - 1e-15 for a, b
                                   in zip(r['Z'], r['Z'][1:])))
    check('a closed vessel pressure never decreases',
          all(b >= a - 1e-6 * max(a, 1.0) for a, b in zip(r['p'], r['p'][1:])))
    check('Z stays in [0, 1]', all(0.0 <= z <= 1.0 for z in r['Z']))
    check('T stays positive', all(t > 0.0 for t in r['T']))
    check('the trace is sampled, not one point per step',
          10 < len(r['t']) <= 2000, f'{len(r["t"])} samples')
    check('p_max is taken over every step, not just the samples',
          r['p_max'] >= max(r['p']) - 1e-9)

    # ── 7. refusals ─────────────────────────────────────────────────────
    print('\n  refusals')
    for bad, label in (((0.0, 1.0), 'zero charge'),
                       ((5.0, 0.0), 'zero volume'),
                       ((-1.0, 1.0), 'negative charge')):
        try:
            d.simulate(p, bad[0], bad[1], t_end=0.01)
            check(f'{label} is refused', False, 'no raise')
        except ValueError:
            check(f'{label} is refused', True)

    print('\nDEFLAGRATION: '
          + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
