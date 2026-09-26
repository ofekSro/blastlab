"""HD1-16 step 1, item 2: the HD1-13 wall-load export, with optional
clearing (core/wallload.py clearing functions, output/load_csv.py
`export_wall_loads`, `python -m blastlab --hd13-wall-export`).

Reference: UFC 3-340-02 (2008), para. 2-15.3.2 (printed p. 65): Eq. 2-8
t_c = 4S / ((1 + R) C_r), S = min(H, W/2), G = max(H, W/2), R = S/G;
Eq. 2-9 P = Ps + C_D q, C_D = 1; Fig. 2-191a (p. 266); Fig. 2-192 (p. 267).

PRE-REGISTERED TOLERANCE for (d), written before the check was run:
C_r from Rankine-Hugoniot (air, gamma 1.4, P_AIR, RHO_AIR) must lie within
2 % of Fig. 2-192 at each point below. The points were read off the PDF
page (docs/references/ufc_3_340_02.pdf, PDF page 343), from the figure's
own vector path: the curve's polyline vertices mapped through the page's
grid lines (Pso 0-75 psi every 5, C_r 1.10-2.00 ft/ms every 0.05). The
page could not be rasterised here (no poppler), so the vertices were
plotted back from the page geometry and checked by eye against the grid.
One more point is the text of the manual's own worked example (printed
p. 411): Pso = 12.8 psi -> C_r = 1.325 ft/ms.

Run:  cd blastlab/tests && python test_wall_clearing.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

from blastlab.core import assessment, wallload as wl          # noqa: E402
from blastlab.core.constants import P_AIR                     # noqa: E402
from blastlab.output import load_csv as lc                    # noqa: E402

FAIL = []

#: Fig. 2-192 (Pso [psi], C_r [ft/ms]), vertices of the page's curve
FIG_2_192 = ((4.934, 1.1986), (9.890, 1.2841), (19.743, 1.4233),
             (39.802, 1.6500), (69.963, 1.9372))
#: the worked example, UFC 3-340-02 printed p. 411
UFC_EXAMPLE = (12.8, 1.325)
#: the pre-registered tolerance of (d)
CR_TOL = 0.02
PSI = 6894.757293168361        # Pa
FT_MS = 304.8                  # m/s


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def test_geometry():
    print('\n  (a) S, G, R and t_c, Eq. 2-8')
    S, G, R = wl.clearing_geometry(3.0, 4.0)
    check('H = 3, W = 4: S = 2, G = 3, R = 2/3',
          (S, G) == (2.0, 3.0) and R == 2.0 / 3.0, f'{S}, {G}, {R}')
    check('t_c by hand, C_r = 400 m/s: 4*2 / ((1 + 2/3) * 400) = 12 ms',
          abs(wl.clearing_time(3.0, 4.0, 400.0) - 0.012) < 1e-15,
          f'{wl.clearing_time(3.0, 4.0, 400.0)!r}')
    S, G, R = wl.clearing_geometry(2.0, 10.0)
    check('H = 2, W = 10: S = 2, G = 5, R = 0.4',
          (S, G) == (2.0, 5.0) and R == 0.4, f'{S}, {G}, {R}')
    check('t_c by hand, C_r = 400 m/s: 4*2 / (1.4 * 400) = 14.2857 ms',
          abs(wl.clearing_time(2.0, 10.0, 400.0) - 8.0 / 560.0) < 1e-15)
    for H, W in ((0.0, 4.0), (3.0, -1.0)):
        try:
            wl.clearing_geometry(H, W)
            ok = False
        except ValueError:
            ok = True
        check(f'H = {H}, W = {W} is refused', ok)


def test_step():
    print('\n  (b) a step trace: Pr at t_a, Ps + q at t_a + t_c, linear '
          'between')
    Pr, Ps, q = 300e3, 100e3, 20e3
    c_r, H, W = 400.0, 3.0, 4.0
    t_c = wl.clearing_time(H, W, c_r)                  # 12 ms
    t_a = 0.005
    t = np.concatenate([np.linspace(0.0, t_a, 11)[:-1],
                        t_a + np.linspace(0.0, t_c, 25),
                        t_a + t_c + np.linspace(0.001, 0.02, 5)])
    E = np.where(t >= t_a, Pr, 0.0)
    res = wl.apply_clearing(t, E, np.full_like(t, Ps), np.full_like(t, q),
                            H, W, c_r)
    L = res['L']
    i_a = int(np.argmax(t >= t_a))
    i_c = i_a + 24
    check('arrival is the first sample above 1 % of the peak',
          res['t_a'] == t_a, f"{res['t_a']!r}")
    check('L = Pr at t_a', L[i_a] == Pr, f'{L[i_a]!r}')
    check('L = Ps + q at t_a + t_c', abs(L[i_c] - (Ps + q)) < 1e-9,
          f'{L[i_c]!r}')
    between = L[i_a:i_c + 1]
    lin = Pr + (Ps + q - Pr) * (t[i_a:i_c + 1] - t_a) / t_c
    check('linear in between', np.max(np.abs(between - lin)) < 1e-6,
          f'max dev {np.max(np.abs(between - lin)):.2e} Pa')
    check('Ps + q after t_c, E (= 0) before t_a',
          np.allclose(L[i_c:], Ps + q, rtol=0, atol=1e-9)
          and np.all(L[:i_a] == 0.0))
    check('C_D on a front wall is 1 (para. 2-15.3.2)', wl.C_D_FRONT == 1.0)


def test_cr_against_figure():
    print(f'\n  (d) C_r against Fig. 2-192, gamma 1.4, tolerance '
          f'{CR_TOL:.0%} (pre-registered)')
    for pso, fig in FIG_2_192 + (UFC_EXAMPLE,):
        cr = wl.reflected_sound_speed(pso * PSI, 1.4, P_AIR) / FT_MS
        check(f'Pso {pso:g} psi: C_r {cr:.4f} ft/ms vs {fig} ft/ms',
              abs(cr / fig - 1.0) <= CR_TOL, f'{cr / fig - 1.0:+.2%}')
    for g in (1.24, 1.4):
        for ps in (5e3, 1e5, 1e6):
            r = wl.reflected_overpressure(ps, g)
            back = wl.incident_from_reflected(r, g)
            check(f'incident_from_reflected inverts R, gamma {g}, '
                  f'ps {ps:g} Pa', abs(back / ps - 1.0) < 1e-12,
                  f'{back!r}')


def _two_floats(path):
    with open(path, 'rb') as f:
        raw = f.read()
    if raw.startswith(b'\xef\xbb\xbf') or b'\r' in raw:
        return False
    for line in raw.decode('ascii').split('\n')[:-1]:
        parts = line.split(',')
        if len(parts) != 2:
            return False
        float(parts[0]), float(parts[1])
    return True


def _case(**kw):
    return assessment.DeflagrationCase(name='wall test', **kw)


def test_export_off(tmp):
    print('\n  (c) clearing off: E exported bit for bit, in kPa')
    _c, g1 = lc.read_hd13_table(os.path.join(lc.WALL_LOAD_DIR, lc.G1_FILE),
                                lc.G1_UNITS)
    _c, pl = lc.read_hd13_table(os.path.join(lc.WALL_LOAD_DIR,
                                             lc.PLANE_FILE), lc.PLANE_UNITS)
    res = lc.export_wall_loads(_case(), os.path.join(tmp, 'off'))
    names = sorted(os.path.basename(f) for f in res['files'])
    check('four CSVs', names == ['G1_g124.csv', 'G1_g140.csv',
                                 'planemax_g124.csv', 'planemax_g140.csv'],
          str(names))
    check('every line of each is exactly two floats',
          all(_two_floats(f) for f in res['files']))
    for g, tag in (('1.24', 'g124'), ('1.40', 'g140')):
        t_ms, p = lc.read_trace(os.path.join(tmp, 'off', f'G1_{tag}.csv'))
        check(f'G1 gamma {g}: t_ms == 1e3 t and p == E_{g} / 1e3, bit for '
              f'bit', np.all(t_ms == 1e3 * g1['t'])
              and np.all(p == g1[f'E_{g}'] / 1e3))
        check(f'G1 gamma {g}: peak = max E / 1e3',
              p.max() == g1[f'E_{g}'].max() / 1e3,
              f'{p.max():.6g} kPa')
        t_ms, p = lc.read_trace(os.path.join(tmp, 'off',
                                             f'planemax_{tag}.csv'))
        check(f'plane-max gamma {g}: Emax_{g} / 1e3 bit for bit',
              np.all(t_ms == 1e3 * pl['t'])
              and np.all(p == pl[f'Emax_{g}'] / 1e3))
    with open(os.path.join(tmp, 'off', 'G1_g124.txt'), encoding='utf-8') as f:
        side = f.read()
    check('the sidecar says reflected + stagnation, no clearing, upper '
          'bound', 'reflected + stagnation, no clearing, upper bound' in side)
    with open(os.path.join(tmp, 'off', 'planemax_g140.txt'),
              encoding='utf-8') as f:
        side = f.read()
    check('the plane-max sidecar says why it is never relieved',
          'clearing is not defined for it' in side)
    bad = os.path.join(tmp, 'bad_units.txt')
    with open(os.path.join(lc.WALL_LOAD_DIR, lc.G1_FILE),
              encoding='utf-8') as f:
        text = f.read().replace('R_1.24 [Pa over P_AIR]', 'R_1.24 [kPa]', 1)
    with open(bad, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    try:
        lc.read_hd13_table(bad, lc.G1_UNITS)
        ok = False
    except ValueError as exc:
        ok = 'units line' in str(exc)
    check('a file whose units line differs is refused', ok)


def test_export_on(tmp):
    print('\n  clearing on: G1 relieved, plane-max untouched')
    case = _case(clearing=True, wall_H_m=3.0, wall_W_m=4.0)
    res = lc.export_wall_loads(case, os.path.join(tmp, 'on'))
    names = sorted(os.path.basename(f) for f in res['files'])
    check('G1 _cleared x 2 and plane-max x 2',
          names == ['G1_g124_cleared.csv', 'G1_g140_cleared.csv',
                    'planemax_g124.csv', 'planemax_g140.csv'], str(names))
    _c, g1 = lc.read_hd13_table(os.path.join(lc.WALL_LOAD_DIR, lc.G1_FILE),
                                lc.G1_UNITS)
    _c, pl = lc.read_hd13_table(os.path.join(lc.WALL_LOAD_DIR,
                                             lc.PLANE_FILE), lc.PLANE_UNITS)
    for g, tag in (('1.24', 'g124'), ('1.40', 'g140')):
        p = res['params'][g]
        t_ms, L = lc.read_trace(os.path.join(tmp, 'on',
                                             f'G1_{tag}_cleared.csv'))
        E = g1[f'E_{g}'] / 1e3
        t = g1['t']
        pre = t < p['t_a']
        check(f'gamma {g}: L = E before arrival',
              np.all(L[pre] == E[pre]))
        check(f'gamma {g}: t_c = Eq. 2-8 with S = 2, R = 2/3 and C_r',
              p['t_c'] == wl.clearing_time(3.0, 4.0, p['c_r']),
              f"C_r {p['c_r']:.1f} m/s, t_c {p['t_c'] * 1e3:.3f} ms")
        ps = np.interp(t, pl['t'], pl['G1cell_p'] - P_AIR)
        un = np.maximum(pl['G1cell_Ux'], 0.0)
        q = np.interp(t, pl['t'], 0.5 * pl['G1cell_rho'] * un * un)
        post = t > p['t_a'] + p['t_c']
        check(f'gamma {g}: L = Ps + q (from the plane file) after t_a + t_c',
              post.any() and np.allclose(L[post], (ps + q)[post] / 1e3,
                                         rtol=1e-12, atol=1e-12))
        print(f'      peak E {E.max():.1f} kPa -> cleared peak '
              f'{L.max():.1f} kPa')
    with open(os.path.join(tmp, 'on', 'G1_g124_cleared.txt'),
              encoding='utf-8') as f:
        side = f.read()
    check('the sidecar says Eq. 2-10 is NOT applied',
          'Eq. 2-10' in side and 'NOT applied' in side)
    check('and that Ps and q come from the 749 writes, not the probe',
          '749 writes' in side and 'NOT from the probe' in side)
    # a clearing-off re-run into the same directory must not leave the
    # _cleared files of the earlier export beside the unrelieved ones
    lc.export_wall_loads(_case(), os.path.join(tmp, 'on'))
    left = sorted(n for n in os.listdir(os.path.join(tmp, 'on'))
                  if n.endswith('.csv'))
    check('a clearing-off re-run leaves no stale _cleared CSV behind',
          left == ['G1_g124.csv', 'G1_g140.csv', 'planemax_g124.csv',
                   'planemax_g140.csv'], str(left))


def test_refused(tmp):
    print('\n  (e) clearing on with no H is refused, naming wall_H_m')
    case = _case(clearing=True, wall_W_m=4.0)
    errs = assessment.wall_errors(case)
    check('wall_errors names wall_H_m, and only it',
          len(errs) == 1 and 'wall_H_m' in errs[0], str(errs))
    rep = assessment.validate(case)
    check('validate refuses the case with that error',
          not rep.ok and any('wall_H_m' in e for e in rep.errors))
    check('clearing off needs no wall', assessment.wall_errors(_case()) == [])
    path = os.path.join(tmp, 'noh.json')
    assessment.save_case(case, path)
    env = dict(os.environ, PYTHONIOENCODING='utf-8',
               PYTHONPATH=REPO + os.pathsep + os.environ.get('PYTHONPATH',
                                                              ''))
    # OUT-1: the export needs --runs-dir / --model; nothing may appear
    # in the model folder either
    os.makedirs(os.path.join(tmp, 'runs'), exist_ok=True)
    p = subprocess.run([sys.executable, '-m', 'blastlab',
                        '--hd13-wall-export', 'noh.json',
                        '--runs-dir', 'runs', '--model', 'NOH'], cwd=tmp,
                       env=env, capture_output=True, text=True)
    check('the CLI exits non-zero naming wall_H_m and writes nothing',
          p.returncode != 0 and 'wall_H_m' in p.stderr
          and not os.path.exists(os.path.join(tmp, 'noh_wall_loads'))
          and not os.path.exists(os.path.join(tmp, 'runs', 'NOH')),
          p.stderr.strip()[-120:])


def test_json(tmp):
    print('\n  the case JSON: optional keys only when set')
    path = os.path.join(tmp, 'plain.json')
    assessment.save_case(_case(), path)
    with open(path, encoding='utf-8') as f:
        text = f.read()
    check('a case without clearing writes none of the three keys',
          not any(k in text for k in ('clearing', 'wall_H_m', 'wall_W_m')))
    case = _case(clearing=True, wall_H_m=3.0, wall_W_m=4.0)
    path = os.path.join(tmp, 'wall.json')
    assessment.save_case(case, path)
    back = assessment.load_case(path)
    check('a case with them round-trips',
          (back.clearing, back.wall_H_m, back.wall_W_m) == (True, 3.0, 4.0))


def main():
    print('WALL CLEARING (HD1-16)')
    tmp = tempfile.mkdtemp(prefix='blastlab_wall_clearing_')
    try:
        test_geometry()
        test_step()
        test_cr_against_figure()
        test_export_off(tmp)
        test_export_on(tmp)
        test_refused(tmp)
        test_json(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nWALL CLEARING: {'PASS' if not FAIL else f'FAIL ({len(FAIL)})'}")
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
