"""HD1-3d: two independent models of one opening, made to disagree.

THE CLAIM BEING TESTED
The 0-D model computes the flow through the vent from isentropic
orifice theory (`deflagration._vent_mdot`). blastFoam solves the same
opening from the equations, on a mesh, knowing nothing about orifices.
**They have to agree.** If they do not, one of them is wrong and the
venting stage has no standing.

PRE-REGISTERED, IN FULL, BEFORE THE RUN (CLAUDE.md 6). Both numbers,
not one - the plan registered only the mass flow, which left the
blowdown curve free to be judged after the fact:

  * **Cd_eff within 15 % of the nominal 0.8.** Deliberately wide,
    because Cd = 0.8 is an estimate and not a measurement - this
    comparison is one of the few things that could calibrate it.

  * **The blowdown SHAPE within 5 %,** after the lumped curve is
    time-scaled by the measured Cd_eff. This is the second check, and
    it had to be rewritten to become one.

    THE FIRST VERSION WAS NOT AN INDEPENDENT CHECK AND SAID IT WAS. It
    registered "t_half within 20 %" beside Cd_eff - but Cd_eff is
    DERIVED from t_half (tau goes as 1/(Cd A), so the ratio of
    half-times IS the ratio of flows). The two were algebraically one
    measurement, and the run duly reported 10.6 % on the half-time
    against 0.8/0.7238 = 10.5 % on Cd: the same number twice, presented
    as two thresholds passing.

    What is actually independent is the SHAPE. Scale the lumped model's
    clock by Cd_eff and the two curves have the same half-time BY
    CONSTRUCTION; whether they then lie on top of each other is a
    separate question, and it asks whether the lumped model is right
    about the FORM of a blowdown rather than about its coefficient.
    5 % of the initial overpressure, RMS over the window.

  * **Mesh convergence of Cd_eff.** A discharge coefficient from one
    mesh may be numerical dissipation in the opening rather than
    physics, so it is measured again at dx/2 and the SHIFT is reported.
    **`Cd` is not calibrated to any of this until the number stops
    moving with the mesh.**

`Cd_eff` IS A MEASUREMENT, NOT A KNOB. It is reported as
`mdot_CFD / mdot_isentropic`, which is the definition of a discharge
coefficient, and it is the OUTPUT of this file. Neither `Cd` in the
0-D model nor either threshold above may be adjusted after seeing it.
If the comparison fails, this file stops and says so, and the next step
is understanding why - not widening the band that caught it.

A DEVIATION FROM THE PLAN, AND THE REASON. The plan called for a 2-D
axisymmetric verification because it is cheap. `core/room.py` builds
rectangular boxes, so an axisymmetric room would need a second geometry
generator with no other user, and the verification would then be run
through a code path the answer never uses. This runs the same 3-D
chamber path the answer will use, on a deliberately small mesh.

Run:  cd blastlab/tests && python _e2e_vent_verify.py
      (WSL; confirm `wsl -d Ubuntu -- pgrep -a blastFoam` is empty)
"""

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import deflagration as d                   # noqa: E402
from blastlab.core import room as _room                       # noqa: E402
from blastlab.core import scenario as sc                      # noqa: E402
from blastlab.core import vent as _vent                       # noqa: E402
from blastlab.core.case import Case3D, validate_case          # noqa: E402
from blastlab.core.constants import P_AIR                     # noqa: E402

# ── PRE-REGISTERED. Do not edit these after reading a result. ───────────
CD_NOMINAL = 0.8
TOL_CD = 0.15           # on Cd_eff, against CD_NOMINAL
TOL_SHAPE = 0.05        # RMS of (p_0D - p_CFD) / (p0 - P_AIR), after
                        # the lumped clock is scaled by Cd_eff
TOL_MESH = 0.10         # how far Cd_eff may move between dx and dx/2
                        # before it is a property of the mesh and not
                        # of the opening
# ───────────────────────────────────────────────────────────────────────

DX = 0.05
#: Long enough to pass the half-time (~4.4 ms measured) with room to
#: spare, and short enough that dx/2 is affordable: the fine run costs
#: 8x the cells and 2x the steps, so the window is what keeps it to
#: hours rather than half a day.
WINDOW = 0.012

FAIL = []
STOP = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def lumped_blowdown(prop, state, area, cd, t_end, n=4000):
    """The 0-D model's own answer for this opening, and nothing else.

    A pure blowdown: the charge is already burnt, so there is no
    generation term and this is the vent law alone. Deliberately a
    separate integration from `simulate` - the question is whether the
    ORIFICE law agrees with the mesh, and wrapping it in the burn model
    would put a second difference in the way.
    """
    m_p, m_a = state.m_p, state.m_a
    _R, cv, _cp, _g = d.mixture(prop, m_p, m_a)
    E = (m_p + m_a) * cv * state.T
    V = state.volume
    dt = t_end / n
    ts, ps = [0.0], []
    p = state.p
    ps.append(p)
    ts = [0.0]
    for _ in range(n):
        tot = m_p + m_a
        if tot <= 1e-12:
            break
        _R, cv, cp, _g = d.mixture(prop, m_p, m_a)
        T = E / (tot * cv)
        p = (m_p * prop.R + m_a * d.AIR_R) * T / V
        if p <= P_AIR:
            break
        mdot = d._vent_mdot(p, T, prop, area, cd, P_AIR, m_p=m_p, m_a=m_a)
        yp = m_p / tot
        m_p -= mdot * yp * dt
        m_a -= mdot * (1.0 - yp) * dt
        E -= mdot * cp * T * dt
        ts.append(ts[-1] + dt)
        ps.append(p)
    return np.asarray(ts), np.asarray(ps[:len(ts)])


def half_time(t, p, p0):
    """When the overpressure first falls to half. Interpolated, because
    the answer must not depend on the sampling interval."""
    t = np.asarray(t, dtype=float)
    p = np.asarray(p, dtype=float)
    target = P_AIR + 0.5 * (p0 - P_AIR)
    below = np.nonzero(p <= target)[0]
    if not len(below):
        return math.inf
    i = below[0]
    if i == 0:
        return float(t[0])
    p1, p2 = p[i - 1], p[i]
    if p1 == p2:
        return float(t[i])
    f = (p1 - target) / (p1 - p2)
    return float(t[i - 1] + f * (t[i] - t[i - 1]))


def shape_rms(t_cfd, p_cfd, t_0d, p_0d, cd_eff, p0):
    """RMS gap between the two blowdowns once the lumped clock is scaled
    by `cd_eff`, as a fraction of the initial overpressure.

    The scaling makes the two half-times agree BY CONSTRUCTION, so what
    is left is entirely about the FORM of the curve - which is the part
    `Cd_eff` cannot explain and therefore the only independent thing
    here. Compared over the window the CFD actually covers.
    """
    scale = CD_NOMINAL / cd_eff          # tau goes as 1/Cd
    t_s = np.asarray(t_0d, dtype=float) * scale
    hi = min(t_s[-1], t_cfd[-1])
    grid = np.linspace(0.0, hi, 200)
    a = np.interp(grid, t_cfd, p_cfd)
    b = np.interp(grid, t_s, p_0d)
    return float(np.sqrt(np.mean(((a - b) / (p0 - P_AIR)) ** 2)))


def run_one(get_solver, prop, st, m, dx, window, tag):
    """One mesh: build, run, and return (t, p) from deep in the room."""
    deep = (0.75, 0.75, 0.4)
    case = Case3D(
        solver='blastfoam', Lx=3.0, Ly=1.5, Lz=1.5, cell_size_m=dx,
        init_mode='chamber', charge=0.0,
        room=m, chamber_state=st.as_dict(), obstacles=m['boxes'],
        bcs=dict(x_lo='transmit', x_hi='transmit', y_lo='transmit',
                 y_hi='transmit', z_lo='reflect', z_hi='transmit'),
        t_end=window, n_snapshots=20, gauges=[deep])
    rep = validate_case(case)
    if not rep.ok:
        raise RuntimeError(f'{tag}: ' + '; '.join(rep.errors))
    across = int(round(math.sqrt(m['vent_area']) / dx))
    print(f'  {tag}: dx {dx:g} m, {rep.n_cells:,} cells, '
          f'~{across} cells across the opening')
    res = get_solver(3, 'blastfoam')(case)
    t = np.asarray(res.gauges['times'], dtype=float)
    p = np.asarray(res.gauges['pressures'][0], dtype=float)
    good = np.isfinite(p)
    return t[good], p[good], across


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f'  [SKIP] blastFoam unavailable: {detail}')
        print('\nVENT VERIFY: SKIP')
        return 0
    from blastlab.solvers import get_solver

    prop = d.PROPELLANTS['double_base']
    print('VENT VERIFY (HD1-3d): two models of one opening')
    print(f'  PRE-REGISTERED: Cd_eff within {TOL_CD:.0%} of '
          f'{CD_NOMINAL:g}; blowdown SHAPE within {TOL_SHAPE:.0%} once '
          f'the coefficient is taken out; Cd_eff moving less than '
          f'{TOL_MESH:.0%} between dx and dx/2')

    # ── the room, ALIGNED - and the 0-D side uses the aligned numbers ───
    m = _room.measure((0.25, 0.25, 0.0), (1.0, 1.0, 1.0), 0.2, DX,
                      vent=('x_hi', 0.5, 0.8, 0.25, 0.55))
    if not m['ok']:
        raise RuntimeError('; '.join(m['errors']))
    print(f"\n  room: cavity {m['volume']:.4f} m3, opening "
          f"{m['vent_area']:.4f} m2, aligned so snapping moved nothing "
          f"({m['volume_shift']:+.1e})")
    check('the 0-D side will use the ALIGNED geometry, which is the '
          'pre-registered condition on this comparison',
          abs(m['volume_shift']) < 1e-12
          and abs(m['vent_area_shift']) < 1e-12)

    # ── the state, from a real burst ────────────────────────────────────
    s = sc.IgnitionScenario(kind='flame_spread', n_cohorts=20,
                            spread_time=8.0)
    shut = d.simulate(prop, 6.0, m['volume'], vent_area=0.0, t_end=30.0,
                      scenario=s, p0_chamber=P_AIR, refine_cohorts=False)
    st = _vent.handoff(shut, prop, mode='burst', p_burst=5.0 * P_AIR,
                       volume_cfd=m['volume'])
    print(f'  state: {st.p / 1e6:.4f} MPa, {st.T:.0f} K, '
          f'alpha_expl {st.alpha_expl:.4f}')

    # ── the lumped model's own answers, once ────────────────────────────
    t0, p0 = lumped_blowdown(prop, st, m['vent_area'], CD_NOMINAL, WINDOW)
    t1, p1 = lumped_blowdown(prop, st, m['vent_area'], 1.0, WINDOW)
    th_isen = half_time(t1, p1, st.p)
    th_0d = half_time(t0, p0, st.p)

    # ── TWO MESHES, because one Cd is not a measurement of an opening ───
    print(f'\n  two meshes, {WINDOW * 1e3:.0f} ms each')
    results = {}
    for tag, dx in (('coarse', DX), ('fine', DX / 2.0)):
        t_c, p_c, across = run_one(get_solver, prop, st, m, dx, WINDOW,
                                   tag)
        check(f'{tag}: the CFD produced a chamber trace', len(p_c) > 5,
              f'{len(p_c)} samples, {p_c[0] / 1e6:.4f} -> '
              f'{p_c[-1] / 1e6:.4f} MPa')
        th = half_time(t_c, p_c, st.p)
        if not math.isfinite(th):
            STOP.append(f'{tag}: the half-time never arrived inside the '
                        f'window - lengthen it and re-run, do NOT relax '
                        f'a threshold')
            check(f'{tag}: reached half the overpressure inside the '
                  f'window', False, 'window too short to judge anything')
            continue
        # Cd_eff IS THE OUTPUT. tau goes as 1/(Cd A), so the ratio of
        # half-times IS the ratio of mass flows: mdot_CFD over
        # mdot_isentropic, measured, which is the definition.
        results[tag] = dict(t=t_c, p=p_c, th=th, across=across,
                            cd=th_isen / th)
        print(f'    half-time {th * 1e3:.3f} ms   '
              f'Cd_eff = {results[tag]["cd"]:.4f}')

    if 'coarse' not in results or 'fine' not in results:
        check('both meshes produced a measurement', False)
    else:
        c, f = results['coarse'], results['fine']
        print(f'\n  MEASURED  Cd_eff  {c["cd"]:.4f} at dx = {DX:g} m  ->  '
              f'{f["cd"]:.4f} at dx/2')
        shift = abs(f['cd'] - c['cd']) / c['cd']
        check(f'Cd_eff moves less than the pre-registered {TOL_MESH:.0%} '
              f'between the two meshes - below that it is a property of '
              f'the opening, above it a property of the mesh',
              shift <= TOL_MESH, f'{shift:.1%} apart')
        check('and the fine mesh has at least as many cells across the '
              'opening as the coarse one - the constraint the 3-D answer '
              'has to meet too',
              f['across'] >= c['across'] >= 6,
              f"{c['across']} -> {f['across']} cells")
        # The finer mesh is the one to quote.
        cd_eff = f['cd']
        err = abs(cd_eff - CD_NOMINAL) / CD_NOMINAL
        check(f'Cd_eff is within the pre-registered {TOL_CD:.0%} of '
              f'{CD_NOMINAL:g}', err <= TOL_CD,
              f'Cd_eff = {cd_eff:.4f}, off by {err:.1%}')
        # THE SECOND CHECK, and independent this time. Scaling the
        # lumped clock by Cd_eff makes the half-times agree by
        # construction, so what is left is the SHAPE - whether the
        # lumped model is right about the form of a blowdown rather than
        # about its coefficient.
        rms = shape_rms(f['t'], f['p'], t0, p0, cd_eff, st.p)
        check(f'and the blowdown SHAPE agrees to the pre-registered '
              f'{TOL_SHAPE:.0%} once the coefficient is taken out - this '
              f'is the part Cd_eff cannot explain, and the previous '
              f'version of this file mistook a restatement of Cd for it',
              rms <= TOL_SHAPE, f'RMS {rms:.2%} of the initial '
                                f'overpressure')
        check('the chamber really emptied rather than the test reading '
              'noise', f['p'][0] > 2.0 * P_AIR and f['p'][-1] < f['p'][0],
              f"{f['p'][0] / 1e6:.4f} -> {f['p'][-1] / 1e6:.4f} MPa")
        print(f'\n  for the record: 0-D at Cd={CD_NOMINAL:g} halves in '
              f'{th_0d * 1e3:.3f} ms, isentropic in {th_isen * 1e3:.3f}')

    if FAIL:
        print('\nVENT VERIFY: FAIL - ' + ', '.join(FAIL))
        print('  STOP. Do NOT adjust Cd or any threshold to make this '
              'pass - they were registered before the run for exactly '
              'this moment. Report the number and find out why.')
        for s_ in STOP:
            print(f'  note: {s_}')
        return 1
    print('\nVENT VERIFY: PASS - the orifice law and the mesh agree on '
          'this opening, and Cd_eff is mesh-independent')
    return 0


if __name__ == '__main__':
    sys.exit(main())
