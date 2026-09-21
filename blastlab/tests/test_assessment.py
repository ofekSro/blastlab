"""HD1-11a: the HD 1.3 assessment case - save, validate, run.

Two things are being pinned.

THE CASE ROUND TRIP, so a result is reproducible from a file rather than
from a transcript of which function got called with what.

AND THE WARNINGS, which are the real product of `validate`. Up to here
every caveat lived in the module that knew about it, and a caller who did
not go looking never saw it. The checks below assert that the ones which
decide whether a number is quotable are raised BEFORE anything is
computed: the extrapolation below the calibrated window, the laboratory
ignition condition, a loading that cannot sustain its own burn, and the
uncalibrated fields.

A validation that passed everything silently would be worse than none,
so there are also checks that a clean case does NOT collect the warnings
belonging to a dirty one.

Run:  cd blastlab/tests && python test_assessment.py
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import assessment as asm                   # noqa: E402
from blastlab.core.case import ValidationReport               # noqa: E402

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


def has(rep, text):
    return any(text.lower() in m.lower()
               for m in rep.errors + rep.warnings + rep.notes)


def main():
    print('ASSESSMENT (HD1-11a)')

    # a realistic magazine case: spread ignition, vented, with a wall
    good = asm.DeflagrationCase(
        name='magazine', propellant='double_base', charge_kg=5.0,
        volume_m3=1.0, vent_area_m2=0.02, confinement='both',
        scenario_kind='flame_spread', n_cohorts=10, spread_time=30.0,
        t_end=60.0, h_c=200.0, wall_area_m2=6.0, standoffs_m=[10.0, 50.0],
        span_m=3.0, mass_per_area=200.0, Ru_pa=50e3, kE_pa_m=5e6)

    # ── 1. the case round trip ──────────────────────────────────────────
    print('\n  the case file')
    path = os.path.join(tempfile.mkdtemp(prefix='blastlab_asm_'),
                        'case.json')
    asm.save_case(good, path)
    back = asm.load_case(path)
    check('a saved case loads back identical',
          asm.case_to_dict(back) == asm.case_to_dict(good))
    check('it carries a schema and a version',
          asm.case_to_dict(good)['schema'] == asm.SCHEMA
          and asm.case_to_dict(good)['version'] == asm.VERSION)
    check('another schema is refused, so a blast case cannot be opened '
          'as an HD 1.3 one',
          _raises(lambda: asm.case_from_dict({'schema': 'blastlab-case'})))
    check('dim = 0, so a host can branch on it like any other case',
          good.dim == 0)
    check('unknown keys in a file are ignored rather than fatal',
          asm.case_from_dict({**asm.case_to_dict(good),
                              'from_the_future': 1}).charge_kg == 5.0)

    # ── 2. validation is the same object the blast cases use ────────────
    print('\n  validation')
    rep = asm.validate(good)
    check('it returns core.case.ValidationReport, so the existing Setup '
          'card and Run gating need no new plumbing',
          isinstance(rep, ValidationReport))
    check('a sound case validates', rep.ok, str(rep.errors))
    check('and still reports the closed-vessel limit and loading density',
          has(rep, 'closed-vessel limit') and has(rep, 'loading density'))
    check('a structural run states it uses the AMBIENT resistance',
          has(rep, 'ambient resistance'))

    print('\n  the warnings that decide whether a number is quotable')
    check('the extrapolation below the calibrated window is raised BEFORE '
          'anything is computed',
          has(rep, 'extrapolation below'), str(rep.warnings))
    check('the uncalibrated fields are named',
          has(rep, 'not calibrated for this material')
          and has(rep, 'p_extinction'))
    check('the fireball correlations are flagged as hydrocarbon work',
          has(rep, 'hydrocarbon'))
    check('a spread-ignition case does NOT collect the uniform warnings',
          not has(rep, 'laboratory condition')
          and not has(rep, 'impossible'))

    from dataclasses import replace
    uni = replace(good, scenario_kind='uniform', n_cohorts=1,
                  spread_time=0.0)
    rep_u = asm.validate(uni)
    check('a uniform case is told it is a laboratory condition',
          has(rep_u, 'laboratory condition'))
    check('and that in the open it is impossible, not conservative',
          has(rep_u, 'impossible'))

    # ── the generic-parametric path: the shipped rows are class-typical
    # literature, so a real assessment overrides them. It is also the
    # only way to switch the extinction limit on, which is why the
    # sustain check is unreachable without it.
    print('\n  material overrides - the generic-parametric case')
    tuned = replace(good, overrides={'n': 0.72, 'r_atm': 3.0e-4},
                    measured=['n', 'r_atm'])
    prop = tuned.build_propellant()
    check('an override reaches the material',
          prop.n == 0.72 and prop.r_atm == 3.0e-4)
    check('a field declared measured drops out of uncalibrated',
          'n' not in prop.uncalibrated and 'r_atm' not in prop.uncalibrated
          and 'a' in prop.uncalibrated, str(prop.uncalibrated))
    loose = replace(good, overrides={'n': 0.72})
    check('an override with no measurement behind it stays an estimate',
          'n' in loose.build_propellant().uncalibrated
          and has(asm.validate(loose), 'still carried as estimates'))
    check('overrides are listed in the report notes',
          has(asm.validate(tuned), 'material overrides'))
    check('a non-property override is refused',
          _raises(lambda: replace(good, overrides={'colour': 'red'})
                  .build_propellant()))
    check('uncalibrated itself cannot be overridden directly',
          _raises(lambda: replace(good, overrides={'uncalibrated': ()})
                  .build_propellant()))

    ext = replace(good, overrides={'p_extinction': 1.0e6})
    check('switching the extinction limit on is noted, with the reason '
          'to sweep it',
          has(asm.validate(ext), 'binary to the answer'))
    thin = replace(ext, charge_kg=0.2, volume_m3=50.0,
                   confinement='confined', standoffs_m=[])
    check('and only then can a loading be told it will light and go out',
          has(asm.validate(thin), 'light and go out'),
          str(asm.validate(thin).warnings))

    print('\n  refusals')
    for bad, label in (
            (dict(propellant='unobtainium'), 'an unknown propellant'),
            (dict(charge_kg=0.0), 'a zero charge'),
            (dict(t_end=-1.0), 'a negative end time'),
            (dict(confinement='partly'), 'an unknown confinement'),
            (dict(discharge_coeff=2.0), 'an impossible discharge '
                                        'coefficient'),
            (dict(volume_m3=0.0), 'a zero chamber volume'),
            (dict(scenario_kind='flame_spread', n_cohorts=1,
                  spread_time=5.0), 'a spread with one cohort')):
        r = asm.validate(replace(good, **bad))
        check(f'{label} is an error', not r.ok, str(r.errors))
    check('run() refuses an invalid case rather than producing numbers',
          _raises(lambda: asm.run(replace(good, charge_kg=-1.0))))

    # ── 3. one call, the whole assessment ───────────────────────────────
    print('\n  run()')
    out = asm.run(good)
    for k in ('confined', 'unconfined', 'thermal', 'radiation', 'sdof',
              'component'):
        check(f'{k} was produced', out[k] is not None and out[k] != ())
    check('the confined and unconfined halves used the SAME fire',
          out['confined']['scenario_kind']
          == out['unconfined']['scenario_kind'] == 'flame_spread')
    check('the structural response used the ambient resistance, not a '
          'heated one',
          out['component'].Ru == good.Ru_pa)
    check('residual capacity is reported separately, for a later case',
          'residual' in out
          and out['residual']['Ru_degraded'] <= good.Ru_pa
          and 'SUBSEQUENT' in out['residual']['note'])
    check('radiation was computed at each standoff asked for',
          len(out['radiation']) == 2
          and out['radiation'][0]['distance'] == 10.0)

    print('\n  the bundle feeds the report unchanged')
    from blastlab.output import hd13
    html_path = os.path.join(os.path.dirname(path), 'out.html')
    sections = hd13.save_hd13_report(
        html_path, prop=out['prop'], confined=out['confined'],
        unconfined=out['unconfined'], sdof=out['sdof'],
        component=out['component'], thermal=out['thermal'],
        radiation=out['radiation'], title=good.name)
    check('every section rendered from one run() call',
          {'confined', 'unconfined', 'sdof', 'thermal', 'radiation'}
          <= set(sections), str(sections))

    print('\n  a confined-only case skips what it did not ask for')
    lean = replace(good, confinement='confined', standoffs_m=[], h_c=0.0,
                   span_m=0.0)
    out2 = asm.run(lean)
    check('no unconfined branch, no thermal, no structure',
          out2['unconfined'] is None and out2['thermal'] is None
          and out2['sdof'] is None)
    check('but the chamber ran', out2['confined']['p_max'] > 101325.0)

    # ── THE BAND REACHES THE REPORT, not just the module ────────────────
    #
    # Nothing in PROPELLANTS is calibrated, so the peak above is a point
    # estimate from a burn law fitted two decades away from where it is
    # being evaluated. The band exists to say so, and it is only worth
    # anything if it travels with the number rather than living in a
    # function nobody calls.
    print('\n  the sensitivity band, wired through to the report')
    banded = replace(lean, sensitivity=True, t_end=10.0, n_cohorts=8,
                     sens_pext_factor=1.5)
    out3 = asm.run(banded)
    b = out3['band']
    check('a case that asks for a band gets one, and it brackets the '
          'number it qualifies',
          b is not None
          and b['low']['p_max'] <= out3['confined']['p_max']
          <= b['high']['p_max'],
          f"{b['low']['p_max']/1e6:.3f} <= "
          f"{out3['confined']['p_max']/1e6:.3f} <= "
          f"{b['high']['p_max']/1e6:.3f} MPa")
    check('every sample in it conserved',
          b['conserved'], f"{b['n_runs']} runs")
    check('the run reports how wide the uncertainty is AS A WARNING, '
          'beside the number and not in a footnote',
          has(out3['report'], 'uncertain by a factor of'),
          str(out3['report'].warnings))
    check('and that the width itself rests on a judgement, because no '
          'row here is calibrated',
          b['ranges_sourced'] is False
          and has(out3['report'], 'not citable either'))
    check('a case that did not ask for one is not charged for it',
          out2['band'] is None and out2['sensitivity'] is None)
    banded_path = os.path.join(os.path.dirname(path), 'banded.html')
    sect = hd13.save_hd13_report(
        banded_path, prop=out3['prop'],
        confined=out3['confined'], sensitivity=out3['sensitivity'],
        sensitivity_note=out3['sensitivity_note'])
    check('the report renders the envelope section from that same bundle',
          'sensitivity' in sect, str(sect))
    with open(banded_path, encoding='utf-8') as fh:
        page = fh.read()
    check('and the caveat is IN the page, not left to the reader',
          'UNSOURCED' in page)

    print('\nASSESSMENT: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
