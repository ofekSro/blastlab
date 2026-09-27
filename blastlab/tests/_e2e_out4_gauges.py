"""OUT-4a A7, real blastFoam: the gauge extras and dynamic pressure.

docs/batches/2026-09-28-out-4-viper-matrix.md, step A7. The tiny 3D case
of `_e2e_vtk_3d.py` (`case()`: 0.6 m cube, 20 kg TNT resolved, one
obstacle, one gauge at (0.3, 0.3, 0.5), t_end = 1 ms, serial, adaptive
write off, activation as that harness uses - the default), run twice as
model-folder stages:

  R0  NO NEW TICKS  that harness's C families: sections p + pMax (the live
                    slice and x = 0.2), obstacles p + pMax, Step every 25;
                    volumes p rho U, Time every 0.1 ms. No vtk_gauges.
  R1  ALL TICKS     R0 plus dynamicP in sections, obstacles and volumes,
                    and vtk_gauges = overpressure, impulse, T, dynamicP.

R0 carries the same VTK families as R1 on purpose: Time-mode volumes set
the solver's write schedule (writer._controldict_time, P14 b), so "no new
ticks" means the same families without the OUT-4a fields - the only
difference between R0 and R1 is what OUT-4a adds.

PRE-REGISTERED RULES (CLAUDE.md sec. 6; committed before the first run,
never changed afterwards; on any failure: stop and report):

 A-R1 the solve is untouched: for every gauge, R1's p trace against R0's
      gives equal peak, positive-phase impulse (output/gauge_summary
      summarize_trace) and arrival (10 % of ambient), |d| = 0.
 A-R2 the overpressure trace equals p - 101325 Pa within
      max(1 Pa, 1e-5 |p|), sample by sample.
 A-R3 the blastFoam impulse trace against the Python cumulative
      trapezoid integral of (p - 101325) dt on the same samples:
      a. the max of the trace within 2 %;
      b. the time of that max within 2 samples;
      c. the arrival read from the overpressure trace (first sample with
         p_over > 0.10 x 101325 Pa) equals the arrival read from p
         (gauge_summary, first p > 1.10 x 101325 Pa).
 A-R4 the q trace against 0.5 rho |U|^2 from the probed rho and U:
      a. relative error <= 1e-4 wherever q >= 1 % of its peak;
      b. the time of peak q identical (same sample).
 A-R5 T is finite and > 0 everywhere, and T at t = 0 is within 1 K of
      ambient (writer.T_AMB).
 A-R6 a. the per-series .vtk file counts (every folder under vtk\\) equal
         R0's +/- 1;
      b. Dynamic_Pressure is an array of every sections, obstacles and
         volumes file of R1;
      c. at each gauge's cell in the last volume file, Dynamic_Pressure
         matches the probe's q at that file's time within 1e-4 relative.
         The gauge's cell is the cell whose centroid is nearest the gauge
         point; on a tie (centroid distances equal to 1e-9 m) the rule
         passes if any tied cell matches. The probe row is the one whose
         time equals the file's time to 1e-9 relative.

Both runs are also checked to finish without an error, and R0 to record
no extra gauge key.

Needs WSL with blastFoam and an idle VM (`wsl -d Ubuntu -- pgrep -a
blastFoam` empty - checked here, the script refuses otherwise).
Run:  cd blastlab/tests && python -u _e2e_out4_gauges.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')

import numpy as np                                            # noqa: E402

import _e2e_vtk_3d as base                                    # noqa: E402

FAIL = []
RAN = []

EXTRAS = ['overpressure', 'impulse', 'T', 'dynamicP']
SURF0 = base.SURF
VOL0 = base.VOL
SURF1 = dict(SURF0, fields=SURF0['fields'] + ['dynamicP'],
             obstacle_fields=SURF0['obstacle_fields'] + ['dynamicP'])
VOL1 = dict(VOL0, fields=VOL0['fields'] + ['dynamicP'])


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''), flush=True)
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def first_above(t, x, level):
    idx = np.flatnonzero(np.asarray(x) > level)
    return float(t[idx[0]]) if idx.size else np.nan


def rule_a1(R0, R1):
    from blastlab.output.gauge_summary import summarize_trace
    print('\nA-R1: the solve is untouched (R1 vs R0, |d| = 0)', flush=True)
    g0, g1 = R0['res'].gauges, R1['res'].gauges
    check('A-R1 the same gauges', len(g0['pressures']) == len(g1['pressures'])
          > 0, f"{len(g0['pressures'])} vs {len(g1['pressures'])}")
    for k, (p0, p1) in enumerate(zip(g0['pressures'], g1['pressures'])):
        s0 = summarize_trace(g0['times'], p0)
        s1 = summarize_trace(g1['times'], p1)
        for key in ('peak_kpa', 'pos_impulse', 'arrival_ms'):
            check(f'A-R1 gauge {k + 1} {key}: |d| = 0', s0[key] == s1[key],
                  f'R0 {s0[key]!r}, R1 {s1[key]!r}')
        print(f'    (info) gauge {k + 1} p arrays identical: '
              f'{np.array_equal(p0, p1) and np.array_equal(g0["times"], g1["times"])}',
              flush=True)


def rule_a2_to_a5(R1):
    from blastlab.core.constants import P_AIR
    from blastlab.output.gauge_summary import ARRIVAL_FRAC, summarize_trace
    from blastlab.solvers.foam.writer import T_AMB
    g = R1['res'].gauges
    t = np.asarray(g['times'], float)
    for key in ('overpressures', 'impulses', 'temperatures', 'dyn_pressures',
                'rhos', 'speeds'):
        check(f'R1 records {key}', key in g and len(g[key])
              == len(g['pressures']), str(sorted(g)))
    if FAIL:
        return
    for k, p in enumerate(g['pressures']):
        p = np.asarray(p, float)
        tag = f'gauge {k + 1}'
        print(f'\nA-R2..A-R5, {tag}', flush=True)
        ovp = np.asarray(g['overpressures'][k], float)
        err = np.abs(ovp - (p - P_AIR))
        tol = np.maximum(1.0, 1e-5 * np.abs(p))
        check(f'A-R2 {tag}: p_over = p - 101325 within max(1 Pa, 1e-5|p|)',
              bool(np.all(err <= tol)),
              f'worst {err.max():.4g} Pa at sample {int(np.argmax(err - tol))}')
        imp = np.asarray(g['impulses'][k], float)
        f = p - P_AIR
        py = np.concatenate([[0.0], np.cumsum(0.5 * (f[1:] + f[:-1])
                                              * np.diff(t))])
        rel = abs(imp.max() - py.max()) / abs(py.max())
        check(f'A-R3a {tag}: max impulse within 2 % of the Python integral',
              rel <= 0.02, f'blastFoam {imp.max():.6g}, Python '
                           f'{py.max():.6g} Pa s, d {rel:.3%}')
        di = abs(int(np.argmax(imp)) - int(np.argmax(py)))
        check(f'A-R3b {tag}: time of that max within 2 samples', di <= 2,
              f'{di} samples (t {t[np.argmax(imp)]:.6g} vs '
              f'{t[np.argmax(py)]:.6g} s)')
        arr_p = summarize_trace(t, p)['arrival_ms'] * 1e-3
        arr_o = first_above(t, ovp, ARRIVAL_FRAC * P_AIR)
        check(f'A-R3c {tag}: arrival from p_over equals arrival from p',
              arr_p == arr_o, f'p {arr_p!r} s, p_over {arr_o!r} s')
        q = np.asarray(g['dyn_pressures'][k], float)
        rho = np.asarray(g['rhos'][k], float)
        spd = np.asarray(g['speeds'][k], float)
        q_py = 0.5 * rho * spd ** 2
        big = q >= 0.01 * q.max()
        relq = np.abs(q[big] - q_py[big]) / np.abs(q_py[big])
        check(f'A-R4a {tag}: q = 0.5 rho |U|^2 within 1e-4 where q >= 1 % '
              f'of peak', bool(big.any()) and bool(np.all(relq <= 1e-4)),
              f'{int(big.sum())} samples, worst {relq.max():.3g}'
              if big.any() else 'no sample')
        check(f'A-R4b {tag}: time of peak q identical',
              int(np.argmax(q)) == int(np.argmax(q_py)),
              f'{int(np.argmax(q))} vs {int(np.argmax(q_py))}')
        T = np.asarray(g['temperatures'][k], float)
        check(f'A-R5 {tag}: T finite and > 0, T(t=0) within 1 K of '
              f'ambient {T_AMB:.3f} K',
              bool(np.all(np.isfinite(T)) and np.all(T > 0))
              and t[0] == 0.0 and abs(T[0] - T_AMB) <= 1.0,
              f'T(0) = {T[0]!r} at t = {t[0]!r}, min {T.min():.4g}')


def series_counts(folder):
    vtk = os.path.join(folder, 'vtk')
    out = {}
    for name in sorted(os.listdir(vtk)):
        d = os.path.join(vtk, name)
        if os.path.isdir(d):
            out[name] = sorted(n for n in os.listdir(d) if n.endswith('.vtk'))
    return out


def centroids(vd):
    pts = np.asarray(vd.block('POINTS').values, float)
    conn = np.asarray(vd.block('CELLS').values, int)
    out, i = [], 0
    while i < len(conn):
        n = int(conn[i])
        out.append(pts[conn[i + 1:i + 1 + n]].mean(axis=0))
        i += 1 + n
    return np.array(out)


def rule_a6(R0, R1):
    from blastlab.output import legacy_vtk as lv
    print('\nA-R6: the VTK files', flush=True)
    c0, c1 = series_counts(R0['folder']), series_counts(R1['folder'])
    check('A-R6a the same series', sorted(c0) == sorted(c1) and bool(c1),
          f'{sorted(c0)} vs {sorted(c1)}')
    for s in sorted(set(c0) & set(c1)):
        check(f'A-R6a {s}: file count equals R0 +/- 1',
              abs(len(c0[s]) - len(c1[s])) <= 1,
              f'R0 {len(c0[s])}, R1 {len(c1[s])}')
    missing = []
    for s, names in c1.items():
        for n in names:
            vd = lv.read(os.path.join(R1['folder'], 'vtk', s, n))
            if 'Dynamic_Pressure' not in vd.arrays():
                missing.append(f'{s}/{n}')
    check('A-R6b Dynamic_Pressure in every sections, obstacles and volumes '
          'file', not missing and bool(c1),
          f'{sum(len(v) for v in c1.values())} files, missing {missing[:4]}')
    vols = c1.get('volumes') or []
    if not vols:
        check('A-R6c a last volume file exists', False)
        return
    last = sorted(vols, key=lambda n: float(n[2:-4]))[-1]
    t_file = float(last[2:-4])
    vd = lv.read(os.path.join(R1['folder'], 'vtk', 'volumes', last))
    q_arr = next(a for a in vd.cell_data if a.name == 'Dynamic_Pressure')
    cen = centroids(vd)
    g = R1['res'].gauges
    t = np.asarray(g['times'], float)
    rows = np.flatnonzero(np.abs(t - t_file) <= 1e-9 * max(abs(t_file), 1e-30))
    check(f'A-R6c a probe row at the last volume time {t_file!r} s',
          rows.size >= 1, f'nearest {t[np.argmin(np.abs(t - t_file))]!r}')
    if not rows.size:
        return
    j = int(rows[-1])
    for k, pt in enumerate(R1['c'].gauges):
        d = np.linalg.norm(cen - np.asarray(pt, float), axis=1)
        tied = np.flatnonzero(d <= d.min() + 1e-9)
        q_probe = float(g['dyn_pressures'][k][j])
        vals = [float(q_arr.values[c]) for c in tied]
        rels = [abs(v - q_probe) / abs(q_probe) if q_probe else abs(v)
                for v in vals]
        check(f'A-R6c gauge {k + 1}: Dynamic_Pressure at its cell = probe q '
              f'within 1e-4', min(rels) <= 1e-4,
              f'cells {tied.tolist()} values {vals}, probe {q_probe!r}, '
              f'rel {min(rels):.3g}')


def main():
    from blastlab.ui.testing import private_settings
    private_settings()                      # auto_cleanup off (CLAUDE.md 8.2)
    from blastlab.core import settings
    from blastlab.solvers.foam import env
    check('the private settings keep the startup sweep off',
          settings.load().get('auto_cleanup') is False)
    busy = subprocess.run(env.wsl_plain_argv('pgrep -a blastFoam || true'),
                          capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout.strip()
    if busy:
        print(f'  [SKIP] the WSL VM is not free (CLAUDE.md 8.6):\n{busy}')
        return 1
    ok, detail = env.check_available()
    if not ok:
        print(f'  [SKIP] blastFoam unavailable: {detail}')
        return 0
    env.hardware(probe=True)                # CLAUDE.md 4: headless
    runs = tempfile.mkdtemp(prefix='blastlab_e2e_out4_')
    print(f'runs folder (kept as evidence): {runs}', flush=True)
    c0 = base.case(vtk_surfaces=SURF0, vtk_volumes=VOL0)
    c1 = base.case(vtk_surfaces=SURF1, vtk_volumes=VOL1,
                   vtk_gauges={'fields': list(EXTRAS)})
    R0 = base.run_stage(runs, 'E2E_OUT4_R0', c0)
    R1 = base.run_stage(runs, 'E2E_OUT4_R1', c1)
    R0['c'], R1['c'] = c0, c1
    for tag, r in (('R0', R0), ('R1', R1)):
        check(f'{tag}: finished without an error, not stopped early',
              r['error'] is None and r['res'] is not None
              and not r['res'].stopped_early, (r['error'] or '')[-300:])
    if FAIL or base.FAIL:
        FAIL.extend(base.FAIL)
        print(f'FAILED before the rules: {FAIL}')
        return 1
    check('R0 records no extra gauge key',
          not ({'overpressures', 'impulses', 'temperatures',
                'dyn_pressures'} & set(R0['res'].gauges)),
          str(sorted(R0['res'].gauges)))
    print(f'    steps: R0 {R0["m"].get("n_steps")}, R1 {R1["m"].get("n_steps")}',
          flush=True)
    rule_a1(R0, R1)
    rule_a2_to_a5(R1)
    rule_a6(R0, R1)
    FAIL.extend(base.FAIL)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'E2E OUT-4a GAUGES: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
