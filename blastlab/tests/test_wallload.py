"""HD1-13 A1: `core/wallload.py`, the load a wall takes at a point.

Every tolerance below is written here, with its reason, before the run
it judges (CLAUDE.md Sec. 6). The closed forms are derived in this file
by a second route rather than typed in from a table, and the only chart
numbers used are the ones UFC 3-340-02's own Appendix 2A prints.

WHAT IS PINNED
  * the two stagnation branches meet at M = 1 and the pitot one sits
    below the isentropic one everywhere above it;
  * the Rayleigh pitot value at M = 2 equals a normal-shock jump followed
    by the isentropic relation behind the shock - the textbook 5.6404;
  * the reflection's two limits (2 weak, (3g-1)/(g-1) = 8 strong);
  * the low-Mach limit is UFC Eq. 2-9 with C_D = 1 (para 2-15.3.2,
    printed p. 65, sidecar `=== page 141 ===`);
  * UFC Appendix 2A's own readings: Cr = 2.40 / 2.70 / 2.90 at Pso = 10 /
    12.8 / 20 psi (Fig. 2-193 at alpha = 0, pp. 410 and 425, sidecar
    `=== page 486 ===` and `=== page 501 ===`), q = 3.5 psi and
    Pso + C_D q = 16.3 psi at 12.8 psi (p. 411, `=== page 487 ===`);
  * both terms fall monotonically in gamma over [1.24, 1.40], which is
    what makes gamma 1.24 and 1.40 the two ends of any mixture;
  * `wall_load` and `extend_with_tail` behave as the HD1-13 rule needs.

WHY 6 % ON THE CHART ANCHORS. The appendix's own 12.8-psi reading, 2.70,
sits 6.3 % above its own 10-20 psi interpolation (2.54 at 12.8 psi), so
no closed form can be held tighter than that against the three readings
together. The Rankine-Hugoniot values are +5.5 %, -1.3 % and +2.7 %.
WHY 5 % ON q AND Pso + C_D q: a chart reading to two significant figures
(3.5 psi) carries +-1.5 % of reading error alone, and the appendix reads
q from Fig. 2-3 rather than computing it.

The Rayleigh pitot and normal-shock relations are not in a registered
reference (docs/references/INDEX.md); the M = 2 check derives the value
twice, independently, and cites neither.

Run:  cd blastlab/tests && python test_wallload.py
"""

import ast
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

from blastlab.core import sdof, wallload as wl                  # noqa: E402
from blastlab.core.constants import P_AIR, RHO_AIR              # noqa: E402

FAIL = []

# ── pre-registered tolerances ──────────────────────────────────────────
TOL_M1 = 1e-12            # the two branches at M = 1 (same number, twice)
TOL_TEXTBOOK = 1e-12      # pitot formula against the two-step derivation
TOL_TEXTBOOK_4DP = 1e-4   # both against the printed 5.6404
TOL_WEAK = 1e-6           # Pr/ps -> 2 at ps = 1e-6 p0 (the term is 8.6e-7)
TOL_STRONG = 1e-4         # Pr/ps -> 8 at ps = 1e6 p0 (the term is 4.2e-5)
TOL_LOW_MACH = 1e-4       # of q, at M = 0.01 (the M^2/4 term is 2.5e-5)
TOL_CR = 0.06             # see the module docstring
TOL_Q = 0.05              # see the module docstring
GAMMAS = np.linspace(1.24, 1.40, 17)

PSI = 6894.757293168361   # Pa per psi


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def pitot_by_parts(M, g):
    """p02/p1 by a second route: the normal-shock jump to M2 and p2/p1,
    then the isentropic stop from M2 behind the shock."""
    m2 = M * M
    M2sq = (1.0 + 0.5 * (g - 1.0) * m2) / (g * m2 - 0.5 * (g - 1.0))
    p2_p1 = 1.0 + 2.0 * g / (g + 1.0) * (m2 - 1.0)
    return p2_p1 * (1.0 + 0.5 * (g - 1.0) * M2sq) ** (g / (g - 1.0))


def post_shock(ps, g=1.4, p1=P_AIR, rho1=RHO_AIR):
    """(p2, rho2, u2) behind a front of overpressure ps running into
    still air (Rankine-Hugoniot, ideal gas)."""
    p2 = p1 + ps
    rho2 = rho1 * (((g + 1.0) * p2 + (g - 1.0) * p1)
                   / ((g - 1.0) * p2 + (g + 1.0) * p1))
    a1 = np.sqrt(g * p1 / rho1)
    Us = a1 * np.sqrt(1.0 + (g + 1.0) / (2.0 * g) * ps / p1)
    return p2, rho2, Us * (1.0 - rho1 / rho2)


def test_branches():
    print('\nthe two stagnation branches')
    for g in (1.24, 1.40):
        iso = float(wl.stagnation_ratio_isentropic(1.0, g))
        pit = float(wl.stagnation_ratio_pitot(1.0, g))
        check(f'pitot = isentropic at M = 1, gamma {g}',
              abs(pit - iso) <= TOL_M1, f'{pit!r} vs {iso!r}')
        M = np.linspace(1.0, 5.0, 4001)[1:]
        d = wl.stagnation_ratio_isentropic(M, g) \
            - wl.stagnation_ratio_pitot(M, g)
        check(f'pitot < isentropic at every M in (1, 5], gamma {g}',
              bool((d > 0).all()), f'min gap {d.min():.3e}')
        # stagnation_pressure itself switches at M = 1
        p, rho = 9.0e4, 1.0
        a = np.sqrt(g * p / rho)
        for Mk in (0.5, 1.0, 2.5):
            got = wl.stagnation_pressure(p, rho, Mk * a, g)
            want = p * float(wl.stagnation_ratio_isentropic(Mk, g)
                             if Mk < 1 else
                             wl.stagnation_ratio_pitot(Mk, g))
            check(f'stagnation_pressure picks the right branch at M = '
                  f'{Mk}, gamma {g}', abs(got / want - 1.0) < 1e-12,
                  f'{got:.6f} vs {want:.6f}')


def test_textbook():
    print('\nthe Rayleigh pitot value at M = 2, gamma 1.4')
    a = float(wl.stagnation_ratio_pitot(2.0, 1.4))
    b = pitot_by_parts(2.0, 1.4)
    check('formula = normal-shock jump + isentropic stop behind it',
          abs(a - b) <= TOL_TEXTBOOK * b, f'{a!r} vs {b!r}')
    check('both are the textbook 5.6404',
          abs(a - 5.6404) <= TOL_TEXTBOOK_4DP
          and abs(b - 5.6404) <= TOL_TEXTBOOK_4DP, f'{a:.6f}, {b:.6f}')
    # and the two routes agree over the whole supersonic range
    Ms = np.linspace(1.01, 5.0, 50)
    rel = np.abs(wl.stagnation_ratio_pitot(Ms, 1.24)
                 / pitot_by_parts(Ms, 1.24) - 1.0)
    check('the two routes agree on M in [1.01, 5], gamma 1.24',
          bool((rel <= TOL_TEXTBOOK).all()), f'max {rel.max():.2e}')


def test_reflection_limits():
    print('\nthe reflection limits')
    p0 = P_AIR
    r = wl.reflected_overpressure(1e-6 * p0, 1.4, p0) / (1e-6 * p0)
    check('Pr/ps -> 2 for a vanishing front', abs(r - 2.0) <= TOL_WEAK,
          f'{r!r}')
    r = wl.reflected_overpressure(1e6 * p0, 1.4, p0) / (1e6 * p0)
    check('Pr/ps -> (3g-1)/(g-1) = 8 for a strong front, gamma 1.4',
          abs(r - 8.0) <= TOL_STRONG, f'{r!r}')
    neg = np.array([-5e4, -1.0, 0.0])
    got = wl.reflected_overpressure(neg, 1.4, p0)
    check('ps <= 0 comes back unchanged', np.array_equal(got, neg),
          str(got))
    check('a scalar in gives a float out',
          isinstance(wl.reflected_overpressure(1e4), float))


def test_low_mach():
    print('\nthe low-Mach limit is UFC Eq. 2-9 with C_D = 1')
    for g in (1.24, 1.40):
        p, rho = 1.1 * P_AIR, 1.2
        u = 0.01 * np.sqrt(g * p / rho)
        q = 0.5 * rho * u * u
        S = wl.stagnation_pressure(p, rho, u, g) - P_AIR
        err = abs(S - (p - P_AIR + q)) / q
        check(f'S = ps + rho u^2/2 at M = 0.01, gamma {g}',
              err <= TOL_LOW_MACH, f'{err:.2e} of q')
    check('flow leaving the wall stagnates nothing (un < 0 is 0)',
          wl.stagnation_pressure(9e4, 1.0, -250.0, 1.4) == 9e4)


def test_ufc_anchors():
    print('\nUFC 3-340-02 Appendix 2A')
    for pso, cr in ((10.0, 2.40), (12.8, 2.70), (20.0, 2.90)):
        C = wl.reflected_overpressure(pso * PSI, 1.4) / (pso * PSI)
        check(f'Cr at Pso = {pso} psi within 6 % of the chart {cr}',
              abs(C / cr - 1.0) <= TOL_CR, f'{C:.4f} ({C / cr - 1:+.2%})')
    p2, rho2, u2 = post_shock(12.8 * PSI)
    q = 0.5 * rho2 * u2 * u2
    check('q behind the 12.8-psi front within 5 % of 3.5 psi (Fig. 2-3)',
          abs(q / (3.5 * PSI) - 1.0) <= TOL_Q,
          f'{q / PSI:.3f} psi ({q / (3.5 * PSI) - 1:+.2%})')
    S = wl.stagnation_pressure(p2, rho2, u2, 1.4) - P_AIR
    check('S there within 5 % of Pso + C_D q = 16.3 psi',
          abs(S / (16.3 * PSI) - 1.0) <= TOL_Q,
          f'{S / PSI:.3f} psi ({S / (16.3 * PSI) - 1:+.2%})')


def test_gamma_monotone():
    print('\nboth terms fall with gamma, so 1.24 and 1.40 are the ends')
    worst = -np.inf
    for p, rho in ((P_AIR, RHO_AIR), (7.0e4, 0.5), (2.0e5, 2.0)):
        a14 = np.sqrt(1.4 * p / rho)
        # M = 0 is the one degenerate point: S = ps for every gamma
        flat = [wl.stagnation_pressure(p, rho, 0.0, g) for g in GAMMAS]
        check(f'at u = 0, S = ps for every gamma (p = {p:g})',
              all(v == p for v in flat))
        for M14 in np.linspace(0.05, 3.0, 60):
            s = np.array([wl.stagnation_pressure(p, rho, M14 * a14, g)
                          for g in GAMMAS])
            worst = max(worst, float(np.diff(s).max()))
    check('S falls strictly over the 17-point gamma grid, M(1.4) in '
          '[0.05, 3], three states', worst < 0.0,
          f'largest step {worst:.3e} Pa')
    worst = -np.inf
    for ps in (1e2, 1e3, 1e4, 1e5, 1e6, 1e7):
        r = np.array([wl.reflected_overpressure(ps, g) for g in GAMMAS])
        worst = max(worst, float(np.diff(r).max()))
    check('R falls strictly over the gamma grid at fixed ps',
          worst < 0.0, f'largest step {worst:.3e} Pa')


def test_wall_load():
    print('\nwall_load')
    t = np.linspace(0.0, 6e-4, 7)
    ps = np.array([-20e3, -5e3, 0.0, 10e3, 50e3, 200e3, 30e3])
    p = P_AIR + ps
    rho = np.array([0.9, 1.1, 1.225, 1.3, 1.6, 2.9, 1.5])
    U = np.array([[100.0, 5.0, -3.0], [-50.0, 0.0, 0.0],
                  [300.0, 10.0, 10.0], [0.0, 0.0, 0.0], [0.0, 50.0, 0.0],
                  [600.0, 0.0, 0.0], [-10.0, 0.0, 0.0]])
    for g in (1.24, 1.40):
        out = wl.wall_load(t, p, U, rho, g)
        check(f'returns t, E, R, S, M, un (gamma {g})',
              sorted(out) == ['E', 'M', 'R', 'S', 't', 'un'])
        check('an (n, 3) U gives un = max(U . n, 0)',
              np.array_equal(out['un'], np.maximum(U[:, 0], 0.0)))
        check('E >= ps at every sample', bool((out['E'] >= ps).all()))
        still = (out['un'] == 0.0) & (ps > 0.0)
        check('E = R where u = 0 and ps > 0 (three samples)',
              still.sum() == 3
              and np.array_equal(out['E'][still], out['R'][still]))
        low = ps <= 0.0
        check('E = S where ps <= 0 (three samples)',
              low.sum() == 3
              and np.array_equal(out['E'][low], out['S'][low]))
        check('R and S are the module\'s own functions',
              np.array_equal(out['R'],
                             wl.reflected_overpressure(ps, g))
              and np.array_equal(out['S'], wl.stagnation_pressure(
                  p, rho, out['un'], g) - P_AIR))
        speeds = wl.wall_load(t, p, U[:, 0], rho, g)
        check('normal speeds give the same load as the vectors',
              all(np.array_equal(speeds[k], out[k])
                  for k in ('E', 'R', 'S', 'M', 'un')))
    side = wl.wall_load(t, p, U, rho, 1.4, normal=(0.0, 2.0, 0.0))
    check('normal is normalised; un = max(U . n, 0) along it',
          np.array_equal(side['un'], np.maximum(U[:, 1], 0.0)))

    # the output shape follows the input
    p2 = p[:6].reshape(2, 3)
    out2 = wl.wall_load(t[:6], p2, U[:6].reshape(2, 3, 3),
                        rho[:6].reshape(2, 3), 1.4)
    check('a (2, 3) field gives (2, 3) outputs',
          all(out2[k].shape == (2, 3) for k in ('E', 'R', 'S', 'M', 'un')))
    flat = wl.wall_load(t, p, U, rho, 1.4)
    check('and the same numbers as the flat call',
          np.array_equal(out2['E'].ravel(), flat['E'][:6]))
    try:
        wl.wall_load(t, p, U[:, :2], rho, 1.4)
        check('a U of the wrong shape is refused', False)
    except ValueError:
        check('a U of the wrong shape is refused', True)

    # NaN in, NaN out - never 0
    for what in ('p', 'U', 'rho'):
        pp, UU, rr = p.copy(), U.copy(), rho.copy()
        {'p': pp, 'rho': rr}.get(what, UU)[3] = np.nan
        o = wl.wall_load(t, pp, UU, rr, 1.4)
        ok = np.isnan(o['E'][3]) and np.isfinite(np.delete(o['E'], 3)).all()
        check(f'a NaN in {what} gives NaN in E there and nowhere else',
              bool(ok), str(o['E']))


def test_tail():
    print('\nextend_with_tail (the rule\'s T1)')
    comp = sdof.Component(3.0, 480.0, 400e3, 3.0e7, support='simple')
    # uneven sampling, the last gap larger than the smallest, like a
    # probe record; and an evenly sampled one
    t_a = np.concatenate([np.linspace(0.0, 0.01, 101),
                          0.01 + 2e-4 * np.arange(1, 51)])
    t_b = np.linspace(0.0, 0.02, 201)
    for label, t in (('uneven', t_a), ('even', t_b)):
        y = 1e5 * np.sin(np.pi * t / t[-1])
        dur = 1.5 * comp.Tn
        te, ye = wl.extend_with_tail(t, y, 2.05e5, dur)
        gap = t[-1] - t[-2]
        add = np.diff(te[len(t) - 1:])
        check(f'{label}: every added step is the last gap',
              np.allclose(add, gap, rtol=1e-9, atol=0.0),
              f'{add.min():.6e}..{add.max():.6e} vs {gap:.6e}')
        check(f'{label}: the hold lasts at least the duration, by less '
              f'than one gap more',
              dur <= te[-1] - t[-1] < dur + gap,
              f'{te[-1] - t[-1]:.6e} vs {dur:.6e}')
        check(f'{label}: the record is kept and the tail is the level',
              np.array_equal(te[:len(t)], t)
              and np.array_equal(ye[:len(t)], y)
              and (ye[len(t):] == 2.05e5).all())
        r0 = sdof.response(t, y, comp, p_ref=0.0)
        r1 = sdof.response(te, ye, comp, p_ref=0.0)
        dt0 = r0.times[1] - r0.times[0]
        dt1 = r1.times[1] - r1.times[0]
        exact = label == 'uneven'
        check(f'{label}: sdof.response steps the extended trace at the '
              f'same dt' + (' (exactly)' if exact else ''),
              dt0 == dt1 if exact else abs(dt1 / dt0 - 1.0) < 1e-12,
              f'{dt0!r} vs {dt1!r}')
    same = wl.extend_with_tail(t_b, t_b, 1.0, 0.0)
    check('a zero duration adds nothing',
          np.array_equal(same[0], t_b) and np.array_equal(same[1], t_b))


def test_imports():
    print('\nimports')
    src = os.path.join(REPO, 'blastlab', 'core', 'wallload.py')
    with open(src, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add('.' * node.level + (node.module or ''))
    check('the module imports only numpy and core.constants',
          mods == {'numpy', '.constants'}, str(sorted(mods)))
    hits = []
    for sub in ('ui', 'gui', 'viz3d'):
        for dp, _dn, fn in os.walk(os.path.join(REPO, 'blastlab', sub)):
            for name in fn:
                if name.endswith('.py'):
                    with open(os.path.join(dp, name), encoding='utf-8',
                              errors='replace') as f:
                        if 'wallload' in f.read():
                            hits.append(os.path.join(sub, name))
    check('no GUI or viewer module imports it', not hits, str(hits))


def main():
    test_branches()
    test_textbook()
    test_reflection_limits()
    test_low_mach()
    test_ufc_anchors()
    test_gamma_monotone()
    test_wall_load()
    test_tail()
    test_imports()


if __name__ == '__main__':
    main()
    print()
    print('WALL LOAD: ' + ('PASS' if not FAIL else
                           f'FAIL ({len(FAIL)}): ' + ', '.join(FAIL)))
    sys.exit(1 if FAIL else 0)
