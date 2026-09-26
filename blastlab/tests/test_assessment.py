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
from blastlab.core.case import (ValidationReport,             # noqa: E402
                                validate_case)

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
    # HD1-16: no structural response is computed, so none is promised
    check('no validation message promises a structural response',
          not has(rep, 'structural response will be computed'))

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
    for k in ('confined', 'unconfined', 'thermal', 'radiation'):
        check(f'{k} was produced', out[k] is not None and out[k] != ())
    check('the confined and unconfined halves used the SAME fire',
          out['confined']['scenario_kind']
          == out['unconfined']['scenario_kind'] == 'flame_spread')
    # HD1-16 step 1, item 3: the keys stay, always None, until step 2
    check('no structural response, even with an element in the case: '
          'sdof, component and verdict are None',
          good.has_component and out['sdof'] is None
          and out['component'] is None and out['verdict'] is None)
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
    check('every section rendered from one run() call, and no structural '
          'one', {'confined', 'unconfined', 'thermal', 'radiation'}
          <= set(sections) and 'sdof' not in sections, str(sections))

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

    # HD1-16 step 1, item 3: NO MU, NO ROTATION, NO VERDICT IN ANY OUTPUT.
    # The grep check the batch plan registered: the starter case (which
    # carries an element) with the band on at a tiny setting, through the
    # report HTML, the CLI stdout and the validation messages - none of
    # these strings may appear anywhere in them.
    print('\n  no output carries a mu, a rotation or a verdict (HD1-16)')
    import contextlib
    import io
    from blastlab.output import cli_hd13
    forbidden = ('Ductility', 'ductility', 'mu ', 'Support rotation',
                 'survives_across_band', 'fails_across_band',
                 'undetermined_within_band', 'COLLAPSE')
    gdir = tempfile.mkdtemp(prefix='blastlab_asm_grep_')
    starter = cli_hd13.write_starter_case(os.path.join(gdir, 's.json'))
    # tiny: adiabatic (so 25 band runs, not 43), short, few cohorts. No
    # standoffs: with h_c = 0 AND standoffs, services/hd13.assess feeds
    # figure_thermal an empty q (a pre-existing bug, reported, not fixed
    # in this batch).
    tiny = replace(asm.load_case(starter), sensitivity=True, t_end=5.0,
                   n_cohorts=4, spread_time=4.0, h_c=0.0, standoffs_m=[])
    check('the grep case carries an element, so a response WOULD have '
          'been computed before HD1-16', tiny.has_component)
    tiny_path = asm.save_case(tiny, os.path.join(gdir, 'tiny.json'))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        # OUT-1: into the model folder <gdir>\grep\ (hd13_report.html,
        # hd13_loads\)
        rpath = cli_hd13.run_and_report(tiny_path, gdir, 'grep')
    stdout = buf.getvalue()
    with open(rpath, encoding='utf-8') as fh:
        rpage = fh.read()
    out4 = asm.run(tiny)
    msgs = '\n'.join(out4['report'].errors + out4['report'].warnings
                     + out4['report'].notes)
    for label, text in (('report HTML', rpage), ('CLI stdout', stdout),
                        ('validation messages', msgs)):
        hits = [w for w in forbidden if w in text]
        check(f'the {label} carries none of {len(forbidden)} forbidden '
              f'strings', not hits, str(hits))
    check('the band did run (so the verdict path was reachable)',
          out4['band'] is not None and out4['verdict'] is None
          and 'band_' in ''.join(os.listdir(
              os.path.join(os.path.dirname(rpath), 'hd13_loads'))))
    check('and the report has no Structural response section or figure',
          'Structural response' not in rpage
          and 'survive the band' not in rpage)
    vpath = os.path.join(os.path.dirname(path), 'verdict.html')
    fake = {'verdict': 'fails_across_band', 'note': 'x',
            'low': {'ductility': 9.0}, 'high': {'ductility': 9.0}}
    hd13.save_hd13_report(vpath, prop=out4['prop'],
                          confined=out4['confined'], verdict=fake)
    with open(vpath, encoding='utf-8') as fh:
        vpage = fh.read()
    check('save_hd13_report ignores a verdict= it is still handed',
          'fails across band' not in vpage and 'survive the band'
          not in vpage)

    # THE BAND MUST RUN ON THE CASE'S OWN SCENARIO. Every band test in
    # test_sensitivity.py lights uniformly because that is fast, so the
    # SPREAD path - the one the ramped entrainment changed - is only
    # exercised through here. A band that quietly reverted to uniform
    # would be qualifying a different fire from the one being reported.
    print('\n  and the band runs on the case s own fire')
    sp = replace(banded, scenario_kind='flame_spread', n_cohorts=20,
                 spread_time=8.0, spread_geometry='area', t_end=20.0)
    out_sp = asm.run(sp)
    check('a spread case gets a band taken on a spread fire',
          out_sp['band'] is not None
          and out_sp['band']['nominal']['p_max'] > 0.0,
          f"x{out_sp['band']['spread']:.2f}")
    check('and the band brackets the SAME peak the report quotes - '
          'which it could not if it had reverted to uniform ignition',
          out_sp['band']['low']['p_max'] <= out_sp['confined']['p_max']
          <= out_sp['band']['high']['p_max'],
          f"{out_sp['band']['low']['p_max']/1e6:.4f} <= "
          f"{out_sp['confined']['p_max']/1e6:.4f} <= "
          f"{out_sp['band']['high']['p_max']/1e6:.4f} MPa")
    check('a uniform case would have given a different peak entirely, '
          'which is how we know the scenario really travelled',
          abs(asm.run(replace(sp, scenario_kind='uniform', n_cohorts=1,
                              spread_time=0.0, sensitivity=False)
                      )['confined']['p_max']
              / out_sp['confined']['p_max'] - 1.0) > 0.5)

    # ── QUANTITY-DISTANCE, wired and EMPTY ──────────────────────────────
    #
    # The comparison is evaluated whenever standoffs were given, even
    # with nothing entered - a siting report that simply OMITS it reads
    # as though it was not needed, while one that prints the sentence
    # says it was not done. Only the second is true.
    print('\n  quantity-distance: present, and empty')
    sited = asm.run(replace(good, sensitivity=False, standoffs_m=[25.0]))
    check('standoffs alone produce the comparison, not silence',
          sited['qd'] is not None and not sited['qd']['have_criteria'])
    check('and the report says no coefficients were entered rather than '
          'leaving the section out',
          any('no coefficients' in n for n in sited['report'].notes))
    entered = replace(good, sensitivity=False, standoffs_m=[25.0],
                      qd_criteria=[dict(name='inhabited building',
                                        k_factor=22.2, basis='mass',
                                        source='<owner standard>',
                                        protects='inhabited building')])
    out5 = asm.run(entered)
    check('a criterion the USER entered is computed, and carries its '
          'source with it',
          out5['qd']['have_criteria']
          and out5['qd']['rows'][0]['source'] == '<owner standard>',
          f"{out5['qd']['governing']} at "
          f"{out5['qd']['governing_distance_m']:.1f} m")
    bad_qd = replace(entered,
                     qd_criteria=[dict(name='x', k_factor=1.0)])
    vrep = asm.validate(bad_qd)
    check('a criterion entered WITHOUT a source is refused up front, '
          'rather than printing a distance with no provenance',
          not vrep.ok and any('QD criterion' in e for e in vrep.errors),
          str(vrep.errors[:1]))
    check('and the case will not run at all in that state - a siting '
          'number from a remembered factor is worse than none',
          _raises(lambda: asm.run(bad_qd)))
    qpath = os.path.join(os.path.dirname(path), 'qd.html')
    qs = hd13.save_hd13_report(qpath, prop=out5['prop'],
                               confined=out5['confined'], qd=out5['qd'])
    check('the report renders the QD section', 'qd' in qs, str(qs))
    with open(qpath, encoding='utf-8') as fh:
        qpage = fh.read()
    check('and prints the source beside the distance it produced, so a '
          'number can never appear without its provenance',
          '&lt;owner standard&gt;' in qpage
          and f"{out5['qd']['governing_distance_m']:.1f}" in qpage,
          f"{out5['qd']['governing_distance_m']:.1f} m with its source")
    epath = os.path.join(os.path.dirname(path), 'qd_empty.html')
    hd13.save_hd13_report(epath, prop=sited['prop'],
                          confined=sited['confined'], qd=sited['qd'])
    with open(epath, encoding='utf-8') as fh:
        epage = fh.read()
    check('an empty table renders the SECTION and a sentence - not a '
          'zero a reader could take for a clearance, and not silence, '
          'which would read as though the comparison was not needed',
          'Quantity-distance' in epage and 'No QD comparison' in epage
          and 'this tool ships none' in epage)

    # ── HD1-3f · THE VENTING STAGE, BUILT FROM THE 0-D CASE ─────────────
    #
    # The order here is the part worth pinning and it is not the obvious
    # one: the room is ALIGNED TO THE MESH FIRST, and only then is the
    # 0-D model run - at the aligned cavity, not at the volume typed
    # into the case. The other way round hands the mesh a state computed
    # for a room up to 10 % larger than the one about to be built, and
    # `validate_case` would rightly refuse it.
    print('\n  the venting stage, built from the 0-D case')
    vcase = replace(good, sensitivity=False, standoffs_m=[], span_m=0.0,
                    charge_kg=20.0, volume_m3=12.168, t_end=40.0,
                    scenario_kind='flame_spread', n_cohorts=40,
                    spread_time=20.0, h_c=200.0, wall_area_m2=6.0,
                    room_origin=(0.0, 0.0, 0.0), room_size=(3.0, 3.0, 2.0),
                    room_wall_m=0.2, vent_face='x_lo',
                    # 1.2 x 1.2 m at dx = 0.1 is 12 cells across, which
                    # is the floor a run that reports a LOAD has to
                    # meet: Cd_eff was measured moving 12.1 % between
                    # six cells and twelve. See room.MIN_VENT_CELLS_LOAD.
                    vent_rect=(0.8, 2.0, 0.3, 1.5),
                    open_mode='burst', p_burst=3.0 * 101325.0,
                    domain_size=(8.0, 6.0, 5.0), cfd_dx_m=0.1,
                    cfd_window_s=0.02,
                    vent_gauges=[(6.0, 3.0, 1.0)])
    vrep2 = asm.validate(vcase)
    check('a complete venting stage validates', vrep2.ok,
          str(vrep2.errors[:2]))
    check('and the cell budget is stated BEFORE anything is built',
          any('base cells' in n for n in vrep2.notes),
          str([n for n in vrep2.notes if 'base cells' in n][:1]))
    cfd, info = asm.build_vent_case(vcase)
    check('the CFD case is a chamber case carrying the room as ordinary '
          'obstacles', cfd.init_mode == 'chamber' and cfd.obstacles
          and cfd.solver == 'blastfoam')
    check('THE 0-D MODEL WAS RE-RUN AT THE ALIGNED CAVITY, not at the '
          'volume typed into the case - so the mesh and the state '
          'describe the same room',
          abs(info['state'].volume / info['room']['volume'] - 1.0) < 1e-12,
          f"state {info['state'].volume:.4f} m3, "
          f"mesh {info['room']['volume']:.4f} m3")
    check('and the case it produced validates against the writer s own '
          'rules', validate_case(cfd).ok,
          str(validate_case(cfd).errors[:2]))
    check('the caveats travel WITH it rather than being consumed here - '
          'the hand-off s, the window s and the room s',
          info['warnings'] and any('window' in w or 'artefact' in w
                                   or 'ADIABATIC' in w
                                   for w in info['warnings']),
          f"{len(info['warnings'])} warnings carried")
    check('the ground reflects and every other side lets the wave out, '
          'because a reflection arriving back inside the window is '
          'indistinguishable from the jet',
          cfd.bcs['z_lo'] == 'reflect'
          and all(cfd.bcs[s] == 'transmit' for s in
                  ('x_lo', 'x_hi', 'y_lo', 'y_hi', 'z_hi')))
    check('a burst panel with no burst pressure is refused - taking the '
          'peak instead would silently become the other case, whose '
          'first front is an artefact',
          not asm.validate(replace(vcase, p_burst=0.0)).ok)
    # TWO BRANCHES, AND THE SPLIT IS THE BUG THIS CAUGHT. Intent comes
    # from the GEOMETRY, not from any-field-set: the form pre-fills a
    # wall thickness, a base cell and a window, so keying on those made
    # a BRAND NEW dim-0 case refuse itself as half filled in - which
    # `_e2e_hd13_gui.py` found by pressing Run on a real window and
    # losing the process.
    half_geom = asm.validate(replace(vcase, vent_rect=()))
    check('half a GEOMETRY is refused - a room and a domain with no '
          'opening is not a smaller case',
          not half_geom.ok
          and any('half filled' in e for e in half_geom.errors),
          str(half_geom.errors[:1]))
    no_nums = asm.validate(replace(vcase, cfd_dx_m=0.0))
    check('and a complete geometry missing its numbers is refused too, '
          'with a different message that says which',
          not no_nums.ok
          and any('not its numbers' in e for e in no_nums.errors),
          str(no_nums.errors[:1]))
    check('while an UNTOUCHED case - geometry blank, scalars pre-filled '
          'by the form - is not a venting stage at all and validates',
          asm.validate(replace(good, room_wall_m=0.2, cfd_dx_m=0.1,
                               cfd_window_s=0.02, p_burst=3e5)).ok)
    check('a room that sticks out of the domain is refused',
          not asm.validate(replace(vcase, domain_size=(2.0, 2.0, 1.0))).ok)
    # SIX CELLS ACROSS THE OPENING IS ENOUGH FOR THE MASS FLOW AND NOT
    # FOR A LOAD, and that is a measurement rather than a judgement:
    # Cd_eff moved 12.1 % between six cells and twelve, with the coarse
    # mesh passing LESS. Blocking, because the symptom is a quietly weak
    # jet and not a run that fails.
    coarse_vent = asm.validate(replace(vcase, cfd_dx_m=0.2))
    check('an opening under twelve cells across is REFUSED for a run '
          'that reports a load - six buys the flow rate, not the '
          'discharge coefficient',
          not coarse_vent.ok
          and any('discharge coefficient' in e for e in coarse_vent.errors),
          str(coarse_vent.errors[:1])[:120])
    check('and at twelve the run is allowed but told the flow may still '
          'be ~10 % low, with the direction named',
          any('slightly weak' in n for n in vrep2.notes),
          str([n for n in vrep2.notes if 'weak' in n])[:100])
    check('and a 0-D case with no venting fields does not try to build '
          'one', not good.wants_vent
          and _raises(lambda: asm.build_vent_case(good)))
    check('opened-from-the-start warns about its artefact at VALIDATION, '
          'before a run, not only afterwards',
          any('ARTEFACT' in w for w in
              asm.validate(replace(vcase, open_mode='open',
                                   p_burst=0.0)).warnings))

    print('\nASSESSMENT: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
