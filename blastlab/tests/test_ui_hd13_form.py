"""HD1-11c: the dim-0 Setup form for an HD 1.3 case.

Two halves, and only one of them is a real Qt test.

The CARD SPEC is plain data and is checked without a QApplication at all,
which is the reason setup_spec is toolkit-free: what a field is called,
what it defaults to and which card it sits on can be read by a test that
never opens a window.

The FORM ROUND TRIP does need widgets, and runs offscreen the way the
rest of the Qt suite does. What it proves is narrow and worth stating:
that a case survives set_case -> get_case unchanged, including every unit
conversion. It does NOT prove anything about layout, sizing or the main
window - CLAUDE.md Sec. 8.7 is explicit that those have to be measured on
a real window, and this file does not pretend otherwise.

The unit conversions are the reason this test exists. The form speaks
kPa, MPa, mm and mm/s because that is what an engineer writes down, and
the case is SI throughout. A factor of 1000 in the wrong direction is
invisible on screen and fatal in the answer.

Run:  cd blastlab/tests && python test_ui_hd13_form.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from blastlab.core import assessment as asm                    # noqa: E402
from blastlab.ui import setup_spec                             # noqa: E402

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


def main():
    print('HD1.3 SETUP FORM (HD1-11c)')

    # ── 1. the spec, with no QApplication in sight ──────────────────────
    print('\n  the card spec (no widgets)')
    cards = setup_spec.cards(0)
    fields = setup_spec.fields(0)
    names = {f.name for f in fields}
    check('dim 0 builds a card set', len(cards) >= 6, f'{len(cards)} cards')
    check('field names are unique', len(names) == len(fields))
    check('both columns are used',
          {c.col for c in cards} == {0, 1})
    check('dims 1-3 are untouched',
          all(len(setup_spec.cards(d)) > 0 for d in (1, 2, 3)))
    check('an unknown dimension is still refused',
          _raises(lambda: setup_spec.cards(4)))
    check('no row carries a solver scope - a 0-D case has no backend',
          all(f.scope is None for f in fields))
    check('the material, chamber, ignition, structure and heat cards are '
          'all there',
          {'Material', 'Charge and chamber', 'Ignition', 'Structure',
           'Heat'} <= {c.title for c in cards})
    check('override rows default to blank, meaning "use the table"',
          all(setup_spec.by_name(0)[k].default == ''
              for k in ('ov_n', 'ov_a', 'ov_r_atm', 'ov_web', 'ov_p_ext',
                        'ov_secondary')))
    check('the propellant choice comes from the real table',
          set(setup_spec.by_name(0)['propellant'].values)
          == set(__import__('blastlab.core.fuels', fromlist=['x'])
                 .PROPELLANT_NAMES))

    # ── 2. the form itself, offscreen ───────────────────────────────────
    print('\n  the form round trip (offscreen)')
    from blastlab.ui.testing import ensure_qapp
    ensure_qapp()
    from blastlab.ui.case_form import CaseForm

    form = CaseForm(0)
    check('a dim-0 form builds', form.dim == 0)

    case = asm.DeflagrationCase(
        name='round trip', propellant='single_base', charge_kg=3.25,
        volume_m3=2.5, vent_area_m2=0.035, discharge_coeff=0.72,
        p_ign=1.5e6, confinement='both', scenario_kind='flame_spread',
        n_cohorts=7, spread_time=12.5, spread_geometry='volume',
        t_end=44.0, n_out=800, h_c=150.0, wall_area_m2=9.5, T_wall=295.0,
        standoffs_m=[12.0, 40.0], span_m=4.0, mass_per_area=333.0,
        Ru_pa=275e3, kE_pa_m=21e6, support='fixed',
        rotation_limit_deg=8.0,
        overrides={'n': 0.77, 'r_atm': 2.5e-4, 'web': 1.4e-3,
                   'p_extinction': 0.8e6, 'secondary_heat': 2.8e6},
        measured=['n', 'r_atm', 'web', 'p_extinction', 'secondary_heat'])

    form.set_case(case)
    back = form.get_case()

    for f in ('name', 'propellant', 'confinement', 'scenario_kind',
              'spread_geometry', 'support', 'n_cohorts', 'n_out'):
        check(f'{f} survives', getattr(back, f) == getattr(case, f),
              f'{getattr(back, f)!r} vs {getattr(case, f)!r}')
    for f, tol in (('charge_kg', 1e-9), ('volume_m3', 1e-9),
                   ('vent_area_m2', 1e-9), ('discharge_coeff', 1e-9),
                   ('p_ign', 1.0), ('spread_time', 1e-9), ('t_end', 1e-9),
                   ('h_c', 1e-9), ('wall_area_m2', 1e-9), ('T_wall', 1e-9),
                   ('span_m', 1e-9), ('mass_per_area', 1e-9),
                   ('Ru_pa', 1.0), ('kE_pa_m', 1.0),
                   ('rotation_limit_deg', 1e-9)):
        a, b = getattr(back, f), getattr(case, f)
        check(f'{f} survives its unit conversion', abs(a - b) <= tol,
              f'{a!r} vs {b!r}')
    check('the standoffs survive',
          [round(x, 6) for x in back.standoffs_m] == case.standoffs_m,
          str(back.standoffs_m))

    print('\n  the overrides, which is where a factor of 1000 hides')
    for k, want in case.overrides.items():
        got = back.overrides.get(k)
        check(f'override {k} survives',
              got is not None and abs(got - want) <= abs(want) * 1e-9,
              f'{got!r} vs {want!r}')
    check('and they are still flagged as measured',
          set(back.measured) == set(case.measured))
    check('the round-tripped case still validates',
          asm.validate(back).ok, str(asm.validate(back).errors))

    print('\n  blank overrides mean "use the table", not zero')
    blank = asm.DeflagrationCase()
    form.set_case(blank)
    b2 = form.get_case()
    check('no overrides in, no overrides out', b2.overrides == {},
          str(b2.overrides))
    check('and the material is untouched',
          b2.build_propellant() is
          __import__('blastlab.core.fuels', fromlist=['x'])
          .PROPELLANTS[blank.propellant])

    print('\n  an override with the measured box off stays an estimate')
    form.set_case(case)
    form.v['measured'].set(False)
    check('overrides survive but measured is empty',
          form.get_case().overrides and not form.get_case().measured)

    print('\n  uniform ignition disables the spread rows')
    form.v['scenario_kind'].set('uniform')
    form._sync_scenario()
    u = form.get_case()
    check('and the case it builds is a consistent uniform one',
          u.scenario_kind == 'uniform' and u.spread_time == 0.0
          and u.n_cohorts == 1)
    check('which its own validator accepts', asm.validate(u).ok,
          str(asm.validate(u).errors))

    print('\n  a bad number is reported, not swallowed')
    form.v['charge_kg'].set('not a number')
    check('get_case raises with the field named',
          _raises(form.get_case))

    print('\nHD1.3 SETUP FORM: '
          + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
