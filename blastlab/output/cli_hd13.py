"""HD1-11b: the HD 1.3 assessment from the command line.

The whole HD 1.3 track is 0-D and closed form, so unlike every other run
in this repo it needs no WSL, no solver and no GUI (the starter case takes
about 40 s with the sensitivity band off, about 20 min with it on). That makes a command-line entry point the cheapest way to make
the work usable, and it is deliberately the FIRST way rather than the
fallback: a Qt form can be built on top of exactly these calls later
without either of them owning the other.

    python -m blastlab --hd13-new magazine.json    # a starter case
    python -m blastlab --hd13 magazine.json        # run it, write the report
    python -m blastlab --hd13-wall-export magazine.json   # HD1-13 wall CSVs

The validation report is printed before anything is computed, errors and
warnings first, because for this model the warnings are the product. A
peak pressure from a burn law measured two decades away is not a result
until the reader knows that is what it is.

The assessment itself (validate, run, figures, report) is
`services/hd13.py` (docs/ARCHITECTURE_REVIEW.md section 5, Phase 7);
this module is the command-line wrapper around it: it prints, and it
turns a refused case into `SystemExit`.
"""

import os

from ..core import assessment
from ..services import hd13 as hd13_service


def write_starter_case(path: str) -> str:
    """A runnable, deliberately realistic starter case; returns `path`.

    Spread ignition rather than uniform, because uniform is a laboratory
    condition and a starter file that quietly used it would teach the
    wrong default on day one.
    """
    case = assessment.DeflagrationCase(
        name='magazine, 5 kg double-base, vented',
        propellant='double_base', charge_kg=5.0, volume_m3=1.0,
        vent_area_m2=0.02, confinement='both',
        # 20 cohorts, for the same reason the ignition is spread rather
        # than uniform: a starter file teaches whatever it does. With
        # entrainment ramped (scenario.windows) 20 is inside 1 % of
        # converged; with the old staircase even 160 was 1.2 % out. See
        # the measured table in ui/setup_spec.py.
        scenario_kind='flame_spread', n_cohorts=20, spread_time=30.0,
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


def _print_headline(out, out_path):
    """The headline numbers of an `assessment.run` output, then the
    report path."""
    c, u = out['confined'], out['unconfined']
    if c is not None:
        print(f"\n  confined   peak {c['p_max'] / 1e6:.3f} MPa"
              f"   ({c['stop_reason']})")
        if out['sensitivity_note']:
            print(f"             {out['sensitivity_note']}")
    if u is not None:
        print(f"  unconfined expansion Mach {u['mach_max']:.4f} (upper bound)"
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
        from ..core import qd as _qd      # lazy, as in core/assessment
        print(f"  siting     {_qd.summary_line(out['qd'])}")
    print(f'\n  report: {out_path}\n')


def run_and_report(case_path: str, out_path: str | None = None,
                   quiet: bool = False) -> str:
    """Load, validate, run and write the report. Returns its path.

    Prints the validation report and the headline numbers unless `quiet`;
    a refused case raises `SystemExit('refusing to run: ...')`.
    """
    case = assessment.load_case(case_path)
    rep = assessment.validate(case)
    if not quiet:
        print(f'\nHD 1.3 assessment: {case.name or case_path}')
        _print_report(rep)
    if not rep.ok:
        raise SystemExit('refusing to run: ' + '; '.join(rep.errors))

    bundle = hd13_service.assess(case, rep)
    if out_path is None:
        out_path = hd13_service.default_report_path(case_path)
    hd13_service.write_report(bundle, out_path)

    if not quiet:
        _print_headline(bundle['out'], out_path)
        _print_loads(bundle.get('loads'))
    return out_path


def wall_export(case_path: str, quiet: bool = False) -> dict:
    """HD1-16 step 1, item 2: write the HD1-13 wall-load traces as SBEDS
    CSVs into `<case>_wall_loads/` (output/load_csv.export_wall_loads).

    Only the case's loaded wall is read (clearing, wall_H_m, wall_W_m);
    clearing on with H or W missing raises `SystemExit` naming the field.
    """
    from . import load_csv
    case = assessment.load_case(case_path)
    errs = assessment.wall_errors(case)
    if errs:
        raise SystemExit('refusing to export: ' + '; '.join(errs))
    res = load_csv.export_wall_loads(case,
                                     load_csv.wall_loads_dir(case_path))
    if not quiet:
        print(f'\nHD 1.3 wall-load export: {case.name or case_path}')
        print('  clearing: ' + (
            f'on, H = {case.wall_H_m:g} m, W = {case.wall_W_m:g} m (G1 '
            f'only; plane-max is always unrelieved)' if case.clearing
            else 'off (E = max(R, S), no clearing, upper bound)'))
        for g, p in res['params'].items():
            print(f'  gamma {g}: C_r {p["c_r"]:.4g} m/s, t_c '
                  f'{p["t_c"] * 1e3:.4g} ms')
        _print_loads(res)
    return res


def _print_loads(loads):
    """HD1-16: where the SBEDS load CSVs went, and any trace whose record
    ends while the load is still active."""
    if not loads or not loads['files']:
        return
    print(f"  loads:  {loads['dir']}   ({len(loads['files'])} CSV, "
          f"t [ms], overpressure [kPa], each with a .txt sidecar)")
    for path in loads['files']:
        print(f'          {os.path.basename(path)}')
    for name, msg in loads['messages']:
        print(f'  {name}: {msg}')
    print()
