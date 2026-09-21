"""HD1-11b: the HD 1.3 assessment from the command line.

The whole HD 1.3 track is 0-D and closed form, so unlike every other run
in this repo it needs no WSL, no solver and no GUI - it finishes in under
a second. That makes a command-line entry point the cheapest way to make
the work usable, and it is deliberately the FIRST way rather than the
fallback: a Qt form can be built on top of exactly these calls later
without either of them owning the other.

    python -m blastlab --hd13-new magazine.json    # a starter case
    python -m blastlab --hd13 magazine.json        # run it, write the report

The validation report is printed before anything is computed, errors and
warnings first, because for this model the warnings are the product. A
peak pressure from a burn law measured two decades away is not a result
until the reader knows that is what it is.
"""

import os

from ..core import assessment
from . import hd13, plots


def write_starter_case(path):
    """A runnable, deliberately realistic starter case.

    Spread ignition rather than uniform, because uniform is a laboratory
    condition and a starter file that quietly used it would teach the
    wrong default on day one.
    """
    case = assessment.DeflagrationCase(
        name='magazine, 5 kg double-base, vented',
        propellant='double_base', charge_kg=5.0, volume_m3=1.0,
        vent_area_m2=0.02, confinement='both',
        # 40 cohorts, not the 10 this started with, for the same reason
        # the ignition is spread rather than uniform: a starter file
        # teaches whatever it does. Ten steps over 30 s is a coarse
        # ignition staircase and reports 2.84 x ambient where the
        # converged answer is 1.04. 40 is the knee of the cost curve and
        # still reports itself ~20 % high - see the measured table in
        # ui/setup_spec.py and deflagration._COHORT_TOL.
        scenario_kind='flame_spread', n_cohorts=40, spread_time=30.0,
        spread_geometry='area', t_end=60.0,
        h_c=200.0, wall_area_m2=6.0, standoffs_m=[10.0, 25.0, 50.0],
        # a 200 mm reinforced-concrete magazine wall rather than a light
        # panel: a starter case whose wall collapses on the first run
        # reads as a broken demo instead of an answer
        span_m=3.0, mass_per_area=480.0, Ru_pa=400e3, kE_pa_m=3.0e7)
    return assessment.save_case(case, path)


def _print_report(rep):
    for kind, items in (('ERROR', rep.errors), ('WARNING', rep.warnings),
                        ('note', rep.notes)):
        for m in items:
            print(f'  [{kind}] {m}')


def run_and_report(case_path, out_path=None, quiet=False):
    """Load, validate, run and write the report. Returns its path."""
    case = assessment.load_case(case_path)
    rep = assessment.validate(case)
    if not quiet:
        print(f'\nHD 1.3 assessment: {case.name or case_path}')
        _print_report(rep)
    if not rep.ok:
        raise SystemExit('refusing to run: ' + '; '.join(rep.errors))

    out = assessment.run(case)
    figures = []
    if out['confined'] is not None:
        figures.append(('Chamber', plots.figure_deflagration(out['confined'])))
    if out['unconfined'] is not None:
        figures.append(('In the open',
                        plots.figure_unconfined(out['unconfined'])))
    if out['sdof'] is not None:
        figures.append(('Structural response',
                        plots.figure_sdof_response(out['sdof'],
                                                   out['component'])))
    if out['thermal'] is not None or out['radiation']:
        t = out['confined']['t'] if out['confined'] else []
        q = out['thermal']['q'] if out['thermal'] else []
        Ts = out['thermal']['T_surface'] if out['thermal'] else None
        if len(t):
            figures.append(('Heat', plots.figure_thermal(
                t, q, Ts, out['radiation'])))

    if out_path is None:
        base = os.path.splitext(case_path)[0]
        out_path = base + '_hd13.html'
    hd13.save_hd13_report(
        out_path, prop=out['prop'], confined=out['confined'],
        unconfined=out['unconfined'], sdof=out['sdof'],
        component=out['component'], thermal=out['thermal'],
        radiation=out['radiation'], figures=figures,
        sensitivity=out['sensitivity'],
        sensitivity_note=out['sensitivity_note'],
        verdict=out['verdict'], qd=out['qd'],
        title=case.name or None)

    if not quiet:
        c, u = out['confined'], out['unconfined']
        if c is not None:
            print(f"\n  confined   peak {c['p_max'] / 1e6:.3f} MPa"
                  f"   ({c['stop_reason']})")
            if out['sensitivity_note']:
                print(f"             {out['sensitivity_note']}")
        if u is not None:
            print(f"  unconfined expansion Mach {u['mach_max']:.4f}"
                  f"   blast negligible: {u['blast_negligible']}")
        if out['sdof'] is not None:
            s = out['sdof']
            if s.collapsed:
                print(f'  structure  COLLAPSE at '
                      f'{s.t_collapse * 1e3:.1f} ms   {s.regime}'
                      f'   (rotation limit '
                      f'{out["component"].rotation_limit_deg:g} deg)')
            else:
                print(f"  structure  mu {s.ductility:.3f}   {s.regime}"
                      f"   theta {s.support_rotation_deg:.2f} deg")
        if out['verdict'] is not None:
            v = out['verdict']
            print(f"  verdict    {v['verdict'].replace('_', ' ').upper()}"
                  f"   (mu {v['low']['ductility']:.2f} at the low end of "
                  f"the band, {v['high']['ductility']:.2f} at the high)")
        if out['qd'] is not None:
            from ..core import qd as _qd
            print(f"  siting     {_qd.summary_line(out['qd'])}")
        print(f'\n  report: {out_path}\n')
    return out_path
