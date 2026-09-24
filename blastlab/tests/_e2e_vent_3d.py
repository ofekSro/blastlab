"""HD1-3d: the answer - what the jet out of the opening does to a wall.

This is what the whole HD1.3 track was for. Everything before it says
what happens INSIDE the room; this is the only thing that says what
leaves it and what that does to a structure standing outside.

WHAT IT PRODUCES
  * the pressure history on the face of a target structure,
  * the SDOF response of that face, from that trace,
  * the two validity metrics, next to the numbers rather than under
    them,
  * and the frames the 3-D viewer already knows how to show.

WHAT IT IS ALLOWED TO CLAIM, AND WHAT IT IS NOT
The opening here is a BURST PANEL, so the first front is the physics
and a peak may be read from it. An opening that was never closed would
not get that (`core/vent.py`): there was no diaphragm, so the first
front is an artefact of initialising a pressurised room against
ambient, and only steady-jet quantities after it has passed mean
anything. The mode is checked rather than assumed.

RESOLUTION, ENFORCED RATHER THAN HOPED FOR. The opening is at least
twelve base cells across, which `assessment.validate` now requires of
any run reporting a load - `_e2e_vent_verify.py` measured the discharge
coefficient moving 12.1 % between six cells and twelve. Even at twelve
the flow may be ~10 % below converged, in a known direction: less out,
so a slightly weak jet. `Cd` is a band axis for that reason and this
run does not pretend otherwise.

BOUNDARY REFLECTIONS ARE CHECKED, NOT ASSUMED. Every outer side is
`transmit`. In a 30 ms window sound covers ~10 m of ambient air, so a
wave reaching a boundary 5 m away can return inside the window and
would be indistinguishable from the jet. The target trace is examined
for a second arrival.

JUDGING A RUN THAT ALREADY EXISTS (HD1-3d, H2). `--load RUN` - a run
directory name under /root/blastlab_runs, a WSL path or a UNC path -
runs C1-C5 exactly as above, then reads the finished run's gauges and
puts the same C6-C13 to them. It is READ-ONLY on the run directory: it
opens the run's case.json (refusing a run that is not this script's
CFD case) and the blastProbes output under postProcessing/gauges, and
nothing else. No field is read, nothing is reconstructed, no solver and
no OpenFOAM utility is started. The gauges come from the same reader
call, packed into the same dict, as the live path's own
(`backend.finalize_3d`: `reader.read_probes(spec.case_unc)`), so C6-C13
see what the live run returned. `postmortem.load_run` is NOT used: it
reads every written time and may run reconstructPar INTO the run, and
the checks need neither.

Run:  cd blastlab/tests && python _e2e_vent_3d.py [--dry | --load RUN]
      (WSL; confirm `wsl -d Ubuntu -- pgrep -a blastFoam` is empty)
"""

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import assessment as asm                   # noqa: E402
from blastlab.core import sdof as _sdof                       # noqa: E402
from blastlab.core import vent as _vent                       # noqa: E402
from blastlab.core.case import validate_case                  # noqa: E402
from blastlab.core.constants import P_AIR                     # noqa: E402

DX = 0.10
WINDOW = 0.030

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def build():
    """The magazine, its opening, and a wall 4 m away."""
    return asm.DeflagrationCase(
        name='magazine, burst panel, wall at 4 m',
        propellant='double_base', charge_kg=40.0, volume_m3=52.272,
        vent_area_m2=0.0, confinement='confined',
        scenario_kind='flame_spread', n_cohorts=20, spread_time=20.0,
        spread_geometry='area', t_end=60.0,
        h_c=200.0, wall_area_m2=110.0,
        # the room: 5 x 5 x 3 m with 0.3 m walls, opening 1.2 x 1.2 in
        # the far x wall - twelve base cells across at dx = 0.1
        room_origin=(1.0, 3.5, 0.0), room_size=(5.0, 5.0, 3.0),
        room_wall_m=0.3, vent_face='x_hi',
        vent_rect=(5.4, 6.6, 0.8, 2.0),
        open_mode='burst', p_burst=3.0 * P_AIR,
        domain_size=(12.0, 12.0, 6.0), cfd_dx_m=DX,
        # SIX, not thirty. The first attempt asked for thirty on an
        # 864,000-cell mesh and wrote 193 GB, which filled the disk and
        # tripped the corpus sweep. A snapshot of this mesh costs ~6 GB
        # once the decomposed and reconstructed copies are counted, and
        # six is plenty to see the jet leave and load the wall.
        cfd_window_s=WINDOW, n_snapshots_vent=6,
        # gauges on the face of a wall 4 m beyond the opening, at the
        # height of the jet and one either side of it
        vent_gauges=[(10.0, 6.0, 1.4), (10.0, 5.0, 1.4),
                     (10.0, 6.0, 2.6)],
        # the wall itself, for the response
        span_m=3.0, mass_per_area=480.0, Ru_pa=400e3, kE_pa_m=3.0e7,
        support='simple')


def load_gauges(run, cfd):
    """The gauges of a FINISHED run, read back without touching it (H2).

    Opens only the run's case.json and its blastProbes output - see the
    module docstring for why this and not `postmortem.load_run`. Returns
    a Result with the live run's gauge dict, or None when the run cannot
    be read or is not this script's CFD case (every case.json field must
    match - a different run would be judged on the wrong gauges)."""
    import json

    from blastlab.core.case import case_to_dict
    from blastlab.solvers.foam import env, reader
    from blastlab.solvers.hooks import Result

    posix, unc = env.case_paths(run)
    print(f'\n  loading  {posix}')
    print('           read-only: case.json + postProcessing/gauges; no '
          'field, no reconstruct, no solver')
    try:
        with open(os.path.join(unc, 'case.json'), encoding='utf-8') as f:
            saved = json.load(f)
        probes = reader.read_probes(unc)
    except (OSError, ValueError) as exc:
        print(f'  [ERROR] cannot read the run: {exc}')
        return None
    want = json.loads(json.dumps(case_to_dict(cfd)))    # as save_case
    differ = sorted(k for k in set(saved) | set(want)
                    if saved.get(k) != want.get(k))
    if differ:
        print(f"  [ERROR] not this script's case: {', '.join(differ)} "
              f'differ')
        return None
    print(f'  case     case.json matches this CFD case, all {len(want)} '
          f'fields')
    # backend.finalize_3d's own gauge dict, from the same reader call
    if probes:
        gauges = dict(times=probes['times'],
                      points=[tuple(pt) for pt in probes['points']],
                      pressures=probes['pressures'],
                      **{k: probes[k] for k in ('speeds', 'rhos')
                         if k in probes})
    else:
        gauges = dict(times=np.array([]), points=[], pressures=[])
    n = len(gauges['times'])
    print(f"  gauges   {len(gauges['points'])} probes, {n} samples"
          + (f", t = {gauges['times'][0] * 1e3:.4f} to "
             f"{gauges['times'][-1] * 1e3:.4f} ms" if n else ''))
    return Result({}, gauges, dict(case_dir=unc, solver='blastfoam'),
                  'loaded post-mortem (gauges only)')


def main():
    dry = '--dry' in sys.argv
    load = None
    if '--load' in sys.argv:
        i = sys.argv.index('--load')
        load = sys.argv[i + 1] if i + 1 < len(sys.argv) else ''
        if not load:
            print('usage: _e2e_vent_3d.py [--dry | --load RUN]')
            return 2
    case = build()

    print('VENT 3D (HD1-3d): the answer')
    rep = asm.validate(case)
    for e in rep.errors:
        print(f'  [ERROR] {e}')
    check('the case validates', rep.ok, f'{len(rep.errors)} errors')
    if not rep.ok:
        print('\nVENT 3D: FAIL - the case does not validate')
        return 1

    cfd, info = asm.build_vent_case(case)
    st, val, m = info['state'], info['validity'], info['room']
    vrep = validate_case(cfd)
    for e in vrep.errors:
        print(f'  [ERROR] {e}')
    check('and the CFD case it builds validates too', vrep.ok)
    check(f'the opening is at least twelve base cells across, which is '
          f'what a run reporting a LOAD now has to be',
          min(m['vent_cells']) >= 12, f"{m['vent_cells']} cells")
    check('the state and the mesh describe the same room',
          abs(st.volume / m['volume'] - 1.0) < 1e-12,
          f"{st.volume:.3f} m3")
    print(f"\n  room    cavity {m['volume']:.3f} m3, opening "
          f"{m['vent_area']:.3f} m2")
    print(f'  state   {st.p / 1e6:.4f} MPa, {st.T:.0f} K, alpha_expl '
          f'{st.alpha_expl:.4f}, burst at t = {st.t_open:.3f} s')
    print(f'  mesh    {vrep.n_cells:,} cells, {WINDOW * 1e3:.0f} ms')
    print(f"  window  tau_drain {val['tau_drain']:.4f} s, "
          f"window/drain {val['window_over_drain']:.3f}")
    for w in info['warnings']:
        print(f'  [caveat] {w[:150]}')

    # THE MODE DECIDES WHAT MAY BE READ, and it is checked rather than
    # assumed. A burst panel really does let go suddenly, so its first
    # front is the physics.
    check('this is a BURST panel, so a peak may be read from the first '
          'front - an opening that was never closed would not get that',
          st.mode == 'burst' and not st.first_front_is_artefact)

    if dry:
        print('\nVENT 3D: DRY - validated and sized, nothing run')
        return 1 if FAIL else 0

    if load:
        # a finished run, judged post-mortem - no WSL solve, no write
        res = load_gauges(load, cfd)
        if res is None:
            print('\nVENT 3D: NOT JUDGED - the run could not be read as '
                  'this case')
            return 1
        return evaluate(case, m, res)

    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f'  [SKIP] blastFoam unavailable: {detail}')
        print('\nVENT 3D: SKIP')
        return 0
    from blastlab.solvers import get_solver

    print('\n  running')
    return evaluate(case, m, get_solver(3, 'blastfoam')(cfd))


def evaluate(case, m, res):
    """C6-C13 on a run's gauges - the live run's, or a finished run's
    read back by `load_gauges`. Only `res.gauges` is read."""
    t = np.asarray(res.gauges['times'], dtype=float)
    traces = [np.asarray(p, dtype=float) for p in res.gauges['pressures']]
    check('the target gauges recorded something',
          len(traces) == 3 and all(np.isfinite(p).any() for p in traces))

    face = traces[0]
    good = np.isfinite(face)
    tf, pf = t[good], face[good]
    peak = float(np.max(pf)) - P_AIR
    i_pk = int(np.argmax(pf))
    print(f'\n  target face  peak {peak / 1e3:.2f} kPa at '
          f't = {tf[i_pk] * 1e3:.2f} ms')
    check('the jet reached the wall and loaded it', peak > 1e3,
          f'{peak / 1e3:.2f} kPa over ambient')

    # A SECOND ARRIVAL would be a reflection off a domain boundary
    # coming back, and it would be indistinguishable from the jet.
    after = pf[i_pk:]
    t_after = tf[i_pk:]
    later = after[t_after > tf[i_pk] + 0.004]
    check('no boundary reflection returns to the wall inside the window '
          '- a second arrival would be indistinguishable from the jet',
          not len(later) or float(np.max(later)) - P_AIR < 0.5 * peak,
          f'later maximum '
          f'{(float(np.max(later)) - P_AIR) / 1e3 if len(later) else 0:.2f}'
          f' kPa against a peak of {peak / 1e3:.2f}')

    # EVERY GAUGE, REPORTED - NOT JUDGED (H2). The checks read gauge 1's
    # peak alone, and CLAUDE.md 6 says never measure peak alone: so
    # peak, arrival and positive-phase impulse are printed for all
    # three. No threshold on impulse or arrival was registered before
    # the run, so none is asserted - that would be judging after the
    # numbers. An impulse whose positive phase is still open when the
    # record ends is a LOWER BOUND and is printed as one.
    from blastlab.output.gauge_summary import gauge_labels, summarize_trace
    t_later = t_after[t_after > tf[i_pk] + 0.004]
    if len(later):
        j = int(np.argmax(later))
        print(f'  gauge 1 after t_peak + 4 ms: largest '
              f'{(later[j] - P_AIR) / 1e3:.2f} kPa at '
              f'{t_later[j] * 1e3:.3f} ms')
    print('\n  every gauge - reported, not judged (no threshold on impulse '
          'or arrival was set before the run)')
    for label, p in zip(gauge_labels(res.gauges, case.vent_gauges),
                        traces):
        ok = np.isfinite(p)
        s = summarize_trace(t[ok], p[ok])
        print(f'  {label}')
        print(f"     peak {s['peak_kpa']:.2f} kPa at "
              f"{s['t_peak_ms']:.3f} ms, arrival {s['arrival_ms']:.3f} ms, "
              f"net impulse {s['net_impulse']:.2f} Pa s")
        if np.isnan(s['arrival_ms']):
            print('     no arrival: never above 1.1 x ambient in the record')
            continue
        print(f"     positive phase {s['pos_duration_ms']:.3f} ms, impulse "
              f"{s['pos_impulse']:.2f} Pa s"
              + ('' if s['complete'] else
                 ' - a LOWER BOUND: still positive when the record ends')
              + f"; positive_phase_complete {s['complete']}")

    comp = _sdof.Component(span=case.span_m,
                           mass_per_area=case.mass_per_area,
                           Ru=case.Ru_pa, kE=case.kE_pa_m,
                           support=case.support)
    r = _sdof.response(tf, pf, comp, p_ref=P_AIR)
    print(f'  response     mu {r.ductility:.4f}, theta '
          f'{r.support_rotation_deg:.3f} deg, {r.regime}')
    check('the wall response is computed from the CFD trace, not from '
          'the 0-D chamber pressure - which is the whole point of '
          'running this',
          np.isfinite(r.ductility))
    check('and the wall survives this one, which a 200 mm reinforced '
          'panel at 4 m should', not r.collapsed,
          f'mu {r.ductility:.4f}')

    # ── THE CFD IS ONE POINT IN THE ENVELOPE, NOT THE ENVELOPE ──────────
    #
    # Every other uncertain parameter can be swept cheaply in the 0-D
    # model. `Cd` cannot, because the CFD does not TAKE a discharge
    # coefficient - it produces one, and the value depends on how well
    # the opening is resolved. So this run is a sample at Cd ~ 0.81, and
    # the load it reports is the load at that corner.
    print('\n  where this run sits in the envelope')
    across = min(m['vent_cells'])
    pt = _vent.cfd_point_in_band(None, across)
    print(f"  {pt['note']}")
    check('the run states where its own Cd sits in the band rather than '
          'presenting its load as the answer',
          0.0 <= pt['position'] <= 1.0
          and 'not the envelope' in pt['note'],
          f"Cd ~ {pt['cd_cfd']:.2f}, {pt['position']:.0%} up the axis")
    # AND A SINGLE SAMPLE CANNOT CLOSE AN UNDETERMINED VERDICT. Checked
    # against a verdict rather than by running a 43-solve band here: the
    # logic is what matters and the band is expensive.
    und = _vent.cfd_point_in_band(
        {'verdict': 'undetermined_within_band'}, across)
    check('and if the structural verdict is undetermined across the '
          'band, this run does NOT close it - one sample drawn from '
          'inside an interval cannot decide a question whose answer '
          'varies over it',
          und['closes_verdict'] is False
          and 'DOES NOT SETTLE' in und['note'])
    check('while a verdict that does not depend on the calibration is '
          'not undermined by the same argument',
          _vent.cfd_point_in_band(
              {'verdict': 'fails_across_band'}, across)['closes_verdict'])

    print('\nVENT 3D: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL
                           else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
