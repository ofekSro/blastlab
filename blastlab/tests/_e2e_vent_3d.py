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

Run:  cd blastlab/tests && python _e2e_vent_3d.py [--dry]
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


def main():
    dry = '--dry' in sys.argv
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

    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f'  [SKIP] blastFoam unavailable: {detail}')
        print('\nVENT 3D: SKIP')
        return 0
    from blastlab.solvers import get_solver

    print('\n  running')
    res = get_solver(3, 'blastfoam')(cfd)
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
