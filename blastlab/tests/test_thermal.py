"""HD1-8: the thermal path - wall flux, fireball, and residual capacity.

Two kinds of check here, and they are not equally strong.

The CONDUCTION and GEOMETRY parts have exact answers and are held to
them: constant-flux heating of a semi-infinite solid, the view factor of
a sphere, and the fact that Duhamel superposition of a constant flux must
reproduce the closed form.

The FIREBALL correlations have no exact answer. They are hydrocarbon and
BLEVE work applied to a propellant stack because nothing better is
published, so what is tested is that they are self-consistent, that they
scale the way a cube-root law must, and above all that the module keeps
saying they are uncalibrated. A green run here does not make a fireball
diameter right.

The third section is the one with a trap in it, and the test exists to
keep the trap shut: `core/sdof.py` must not import this module, and
`residual_capacity` must be a separate answer rather than an input to the
dynamic response. See the thermal module docstring for why coupling them
would be unphysical.

Run:  cd blastlab/tests && python test_thermal.py
"""

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import deflagration as d                   # noqa: E402
from blastlab.core import thermal as th                       # noqa: E402

FAIL = []

TOL_CONDUCTION = 2e-3     # 0.2 % against the closed form
TOL_EXACT = 1e-12


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


def main():
    print('THERMAL (HD1-8)')

    # ── 1. conduction against its closed form ───────────────────────────
    print('\n  a semi-infinite wall under a constant flux')
    k, rho, cp, T0 = 45.0, 7850.0, 470.0, 300.0
    q0 = 50e3
    t = np.linspace(0.0, 60.0, 4001)
    q = np.full_like(t, q0)
    Ts = th.surface_temperature(t, q, k=k, rho=rho, cp=cp, T0=T0)
    alpha = k / (rho * cp)
    exact = T0 + 2.0 * q0 * np.sqrt(alpha * t / math.pi) / k
    err = np.max(np.abs(Ts[1:] - exact[1:]) / (exact[1:] - T0))
    check(f'Duhamel reproduces 2 q sqrt(alpha t / pi) / k to '
          f'{TOL_CONDUCTION:g}', err < TOL_CONDUCTION, f'{err:.2e}')
    check('a hotter wall at the end than at the start, monotonically',
          all(b >= a - 1e-9 for a, b in zip(Ts, Ts[1:])))
    check('zero flux leaves the wall at ambient',
          abs(th.surface_temperature(t, np.zeros_like(t), T0=T0)[-1] - T0)
          < TOL_EXACT)
    check('doubling the flux doubles the rise, since conduction is linear',
          abs(th.surface_temperature(t, 2 * q, k=k, rho=rho, cp=cp,
                                     T0=T0)[-1] - T0
              - 2.0 * (Ts[-1] - T0)) < 1e-6 * (Ts[-1] - T0))
    check('t and q of different lengths are refused',
          _raises(lambda: th.surface_temperature(t, q[:-1])))

    # ── 2. the confined wall, fed from a real 0-D run ───────────────────
    print('\n  the confined wall, from a chamber run')
    p = d.PROPELLANTS['double_base']
    r = d.simulate(p, 5.0, 1.0, vent_area=0.01, t_end=5.0)
    exp = th.wall_exposure(r['t'], r['T'], h_c=200.0, T_wall=300.0)
    check('the chamber heats its wall',
          exp['q_max'] > 0 and exp['T_surface_max'] > 300.0,
          f"q_max {exp['q_max']/1e3:.1f} kW/m2, "
          f"surface {exp['T_surface_max'] - 273.15:.0f} C")
    check('a cooler gas gives a smaller flux',
          th.wall_exposure(r['t'], r['T'], h_c=200.0,
                           T_wall=1000.0)['q_max'] < exp['q_max'])
    check('the flux never goes negative - this model has no wall cooling '
          'the gas back down',
          float(np.min(exp['q'])) >= 0.0)

    # ── 3. the fireball ─────────────────────────────────────────────────
    print('\n  the fireball')
    tot, ana, sec = th.fireball_energy(p, 5.0)
    check('secondary combustion is comparable to the propellant energy, '
          'not a correction to it',
          sec > 0.5 * ana,
          f'{sec/1e6:.1f} MJ secondary vs {ana/1e6:.1f} MJ anaerobic')
    check('and it can be switched off, for a like-for-like comparison',
          th.fireball_energy(p, 5.0, include_secondary=False)[0] == ana)
    fb = th.fireball(tot, mass_kg=5.0)
    tot8, _a8, _s8 = th.fireball_energy(p, 40.0)
    check('eight times the charge gives twice the diameter',
          abs(th.fireball(tot8)['diameter'] / fb['diameter'] - 2.0) < 1e-9)
    check('and twice the duration',
          abs(th.fireball(tot8)['duration'] / fb['duration'] - 2.0) < 1e-9)
    check('the geometry is driven by ENERGY, not by the mass label',
          th.fireball(tot, mass_kg=5.0)['diameter']
          == th.fireball(tot, mass_kg=500.0)['diameter'])
    check('the emissive power comes from the energy actually available, '
          'not a hydrocarbon table',
          abs(fb['sep'] - fb['f_rad'] * tot / (fb['area'] * fb['duration']))
          < 1e-6 * fb['sep'],
          f"{fb['sep']/1e3:.0f} kW/m2")
    # THE CONSISTENCY CHECK. Nothing forces this: the diameter comes from
    # a hydrocarbon correlation and the energy from the propellant table,
    # and the emissive power that falls out has to land where real
    # fireballs are measured. Driving the correlation by mass instead of
    # energy put it at 51 kW/m2, which is how the error was found.
    check('which lands in the range published for real fireballs - the '
          'only thing tying these correlations to a propellant',
          100e3 < fb['sep'] < 500e3, f"{fb['sep']/1e3:.0f} kW/m2")
    check('the fireball is flagged uncalibrated', not fb['calibrated'])
    check('a zero-energy fireball is refused',
          _raises(lambda: th.fireball(0.0)))

    print('\n  radiation at a standoff')
    near = th.radiation_at(fb, 10.0)
    far = th.radiation_at(fb, 100.0)
    check('flux falls with distance', near['flux'] > far['flux'],
          f"{near['flux']/1e3:.2f} vs {far['flux']/1e3:.4f} kW/m2")
    check('the view factor of a sphere falls as 1/L^2',
          abs(th.view_factor(fb, 100.0, height_m=0.0)
              / th.view_factor(fb, 200.0, height_m=0.0) - 4.0) < 1e-9)
    check('a receiver inside the fireball sees a view factor of 1',
          th.view_factor(fb, 0.0, height_m=0.0) == 1.0
          and th.radiation_at(fb, 0.5)['inside_fireball'])
    check('transmissivity is between 0 and 1 and falls with distance',
          0.0 < th.transmissivity(500.0) < th.transmissivity(10.0) <= 1.0,
          f'{th.transmissivity(10.0):.3f} -> {th.transmissivity(500.0):.3f}')
    check('dose carries a verdict against published thresholds',
          isinstance(near['verdict'], str) and near['verdict'],
          f"{near['dose']:.1f} -> {near['verdict']}")
    check('a big dose reads as a worse verdict than a small one',
          th.dose_verdict(5000.0) == '50 % fatality'
          and th.dose_verdict(1.0).startswith('below'))
    check('dose integrates the 4/3 power, in kW units',
          abs(th.thermal_dose([0.0, 2.0], [1e3, 1e3]) - 2.0) < 1e-9,
          str(th.thermal_dose([0.0, 2.0], [1e3, 1e3])))

    # ── 4. THE TRAP: thermal and dynamic stay separate ──────────────────
    print('\n  residual capacity is a SECOND question, not a coupling')
    import blastlab.core.sdof as sdof_mod
    src = open(sdof_mod.__file__, encoding='utf-8').read()
    check('core/sdof.py does not import the thermal module at all',
          'thermal' not in src,
          'sdof must not know heat exists')
    Ru = 50e3
    cold = th.residual_capacity(Ru, 293.15)
    hot = th.residual_capacity(Ru, 873.15)       # 600 C
    check('at ambient nothing is lost',
          abs(cold['Ru_degraded'] - Ru) < 1e-9)
    check('at 600 C steel keeps the Eurocode 0.47',
          abs(hot['factor'] - 0.47) < 1e-9, f"{hot['factor']}")
    check('concrete and steel degrade differently at the same temperature',
          abs(th.residual_capacity(Ru, 873.15, 'concrete')['factor'] - 0.45)
          < 1e-9)
    check('the result says out loud that it is for a later load case',
          'SUBSEQUENT' in hot['note'])
    check('an unknown material is refused',
          _raises(lambda: th.strength_factor(500.0, 'cheese')))

    # the two answers, side by side, never merged
    import numpy as _np
    comp = sdof_mod.Component(span=3.0, mass_per_area=200.0, Ru=Ru, kE=5e6)
    tt = _np.linspace(0.0, 6.0 * comp.Tn, 1201)
    pp = 101325.0 + 0.6 * Ru * _np.exp(-tt / (2.0 * comp.Tn))
    pulse = sdof_mod.response(tt, pp, comp)
    comp_hot = sdof_mod.Component(span=3.0, mass_per_area=200.0,
                                  Ru=hot['Ru_degraded'], kE=5e6)
    later = sdof_mod.response(tt, pp, comp_hot)
    check('the same load is survivable cold and not when the section has '
          'been cooked - two runs, two answers, no coupling',
          pulse.ductility < later.ductility,
          f'mu {pulse.ductility:.3f} cold vs {later.ductility:.3f} heated')

    print('\nTHERMAL: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
