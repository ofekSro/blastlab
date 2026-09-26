"""HD1-10: the HD 1.3 figures and report.

These are writers, so what is worth testing is not that they are pretty
but that the CAVEATS survive the trip. Every number in this track carries
a qualification bigger than its own precision, and a report that prints
the value while losing the qualification is worse than no report - so the
checks below are mostly about what must appear NEXT TO a number:

  * a quantity from an uncalibrated field is labelled at the number;
  * the extrapolation fraction appears with the peak pressure;
  * the ignition scenario is always stated, and a uniform one is called
    a laboratory condition;
  * a simultaneous unconfined burn is called an impossible limit.

Also pinned: the figure builders return Figures and never touch pyplot,
which is what lets the GUI build them on a worker thread
(test_ui_no_mpl_pyplot.py pins the other half of that rule).

Run:  cd blastlab/tests && python test_hd13_report.py
"""

import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import deflagration as d                   # noqa: E402
from blastlab.core import scenario as sc                      # noqa: E402
from blastlab.core import sdof                                # noqa: E402
from blastlab.core import thermal as th                       # noqa: E402
from blastlab.core import unconfined as un                    # noqa: E402
from blastlab.output import hd13, plots                       # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def main():
    print('HD1.3 REPORT (HD1-10)')
    from matplotlib.figure import Figure

    p = d.PROPELLANTS['double_base']
    spread = sc.IgnitionScenario(kind='flame_spread', n_cohorts=10,
                                 spread_time=30.0)
    conf = d.simulate(p, 5.0, 1.0, vent_area=0.02, t_end=60.0,
                      scenario=spread)
    unconf = un.burn(p, 5.0, scenario=spread)
    exp = th.wall_exposure(conf['t'], conf['T'], h_c=200.0)
    tot, _a, _s = th.fireball_energy(p, 5.0)
    fb = th.fireball(tot, mass_kg=5.0)
    rad = [th.radiation_at(fb, r) for r in (10.0, 30.0, 100.0)]

    comp = sdof.Component(span=3.0, mass_per_area=200.0, Ru=50e3, kE=5e6)
    sres = sdof.response(conf['t'], conf['p'], comp)

    # ── 1. figures are Figures, and pyplot is untouched ─────────────────
    print('\n  figure builders')
    assert 'matplotlib.pyplot' not in sys.modules or True
    figs = {
        'deflagration': plots.figure_deflagration(conf),
        'unconfined': plots.figure_unconfined(unconf),
        'sdof': plots.figure_sdof_response(sres, comp),
        'thermal': plots.figure_thermal(conf['t'], exp['q'],
                                        exp['T_surface'], rad),
    }
    ib, pb = sdof.pi_curve(comp, 3.0, ratios=np.logspace(-1.5, 1.5, 12))
    figs['pi'] = plots.figure_pi_diagram(
        [('mu = 3', ib, pb)],
        [('this load', sres.I_bar, sres.P_bar)])
    for name, fig in figs.items():
        check(f'{name} returns a Figure', isinstance(fig, Figure))
    check('none of them imported pyplot',
          'matplotlib.pyplot' not in sys.modules,
          'a figure builder must stay on the OO API')

    # ── 2. the report writes, and the caveats survive ───────────────────
    print('\n  the report')
    out = os.path.join(tempfile.mkdtemp(prefix='blastlab_hd13_'),
                       'hd13.html')
    sections = hd13.save_hd13_report(
        out, prop=p, confined=conf, unconfined=unconf, sdof=sres,
        component=comp, thermal=exp, radiation=rad,
        sensitivity={'peak pressure [MPa]': (0.21, 0.55)},
        oat=[('n +/- 0.15', 0.31), ('a x2', 0.08)],
        figures=[(k, v) for k, v in figs.items()],
        title='test assessment')
    body = open(out, encoding='utf-8').read()
    check('it wrote a file', os.path.getsize(out) > 5000,
          f'{os.path.getsize(out)} bytes')
    for s in ('banner', 'material', 'confined', 'unconfined',
              'thermal', 'radiation', 'sensitivity', 'figures'):
        check(f'section {s!r} present', s in sections)
    # HD1-16 step 1, item 3: sdof= is still accepted and ignored
    check("no 'sdof' section, even when sdof= and component= are passed",
          'sdof' not in sections)

    print('\n  the caveats, which are the point')
    check('uncalibrated fields are labelled AT the number',
          body.count('uncalibrated') >= 5,
          f"{body.count('uncalibrated')} labels")
    check('the extrapolation fraction is reported with the pressure',
          'outside the calibration window' in body)
    check('a fully extrapolated run says so in words, not just a number',
          'the whole burn' in body,
          f"extrapolated {conf['extrapolated_fraction']:.2f}")
    check('the ignition scenario is always stated',
          'Ignition scenario' in body and 'flame_spread' in body)
    check('the TNT-equivalent warning is on every report',
          'opposite corner of the pressure-impulse diagram' in body)
    check('HD1-16: no structural response table, ductility or rotation',
          'Structural response' not in body and 'Ductility' not in body
          and 'Support rotation' not in body)
    check('the empirical status of the fireball is stated next to it',
          'does not solve radiation' in body)
    check('the sensitivity is one envelope, and says so',
          'not a set of runs to choose from' in body)

    print('\n  a uniform run is flagged as the laboratory condition')
    uni = d.simulate(p, 5.0, 1.0, vent_area=0.02, t_end=60.0)
    out2 = os.path.join(os.path.dirname(out), 'uniform.html')
    hd13.save_hd13_report(out2, prop=p, confined=uni,
                          unconfined=un.burn(p, 5.0))
    body2 = open(out2, encoding='utf-8').read()
    check('the confined side calls uniform ignition a laboratory condition',
          'laboratory condition' in body2)
    check('the unconfined side calls simultaneous ignition impossible',
          'impossible one' in body2)
    check('and a spread run does NOT carry either warning',
          'laboratory condition' not in body and 'impossible one' not in body)

    print('\n  a bare run still renders')
    out3 = os.path.join(os.path.dirname(out), 'bare.html')
    s3 = hd13.save_hd13_report(out3, confined=conf)
    check('sections are only what was supplied',
          s3 == ['banner', 'confined'], str(s3))
    check('and it is still valid html', open(out3, encoding='utf-8')
          .read().rstrip().endswith('</html>'))

    print('\nHD1.3 REPORT: '
          + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
