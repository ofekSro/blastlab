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
         RE-REGISTERED (owner, 2026-09-28, before the rerun): the two are
         compared as SAMPLE INDICES, not float times - run 2 picked the
         same sample on both sides, but gauge_summary's ms round trip
         made the times differ in the last bit.
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
         RE-REGISTERED (owner, 2026-09-28, before the rerun): the probe
         row is the one whose time equals the file's time printed at the
         probe file's precision (blastProbes writePrecision, 6 significant
         digits: `float(f'{t:.6g}')`); threshold unchanged (1e-4).

Both runs are also checked to finish without an error, and R0 to record
no extra gauge key.

OUT-4b B4 (the same batch plan, step B4): two more runs of the same case
with a SECOND obstacle box (0.03-0.12, 0.3-0.5, 0.3-0.5 m; the first stays
at 0.47-0.57, 0.1-0.3, 0.1-0.3 m, the Obstacles table order):

  R2a NO NEW TICKS  R0's families, two obstacles.
  R2  4b TICKS      R2a plus impulse + impulseMax in sections and volumes,
                    impulse + timeOfArrival + impulseMax + obstacleID on the
                    obstacles, and vtk_gauges = impulse.

PRE-REGISTERED RULES for B4 (committed before the first R2 run, never
changed afterwards; on any failure: stop and report):

 B-R1 the solve is untouched: for every gauge, R2's p trace against R2a's
      gives equal peak, positive-phase impulse (gauge_summary
      summarize_trace) and arrival, |d| = 0.
 B-R2 a. Peak_Impulse is an array of every sections, obstacles and volumes
         file of R2;
      b. per cell, along each series in time order, Peak_Impulse never
         decreases (tolerance 0);
      c. in every such file, Peak_Impulse >= Impulse, cell by cell
         (tolerance 0).
 B-R3 at each gauge's cell in the last volume file (the A-R6c cell rule:
      nearest centroid, any tied cell may match), Peak_Impulse is within
      1 % of the max over the whole run of that gauge's impulse trace.
 B-R4 in every obstacles file of R2: Obstacle_ID is an int array, every
      face has an ID in 1..2, and the face count of each ID equals the
      Python-predicted exposed faces of that snapped box - the faces
      between a solid cell of the planned mask (writer.plan_case(case)
      .solid, the box = the first snapped box holding the cell centre)
      and a fluid cell inside the domain, on the planned grid; the case
      must plan with no refinement (lmax = 0, amr = 0) for this count.

Also printed (information, not a rule): the distinct Time_Of_Peak values
in R2's last obstacles file (the B1 relabel; see the batch report).

OUT-4b F6 (owner approved the fix inside 4b, 2026-09-28): the writer emits
the timeOfArrival function object (`arrival`) BEFORE `pMax`, so its
`p > pMax` test sees the previous step's max (timeOfArrival.C execute()
shares the registered pMax with the fieldMinMax). Two runs of R2's case
with pMax and timeOfArrival added to the volumes (VOL3):

  R3pre PRE-FIX ORDER  the controlDict with `arrival` moved back after
                       pMax / impulseMax, just before `overpressure` - the
                       order of every writer golden before the fix (a spy on
                       writer._controldict_function_objects, test-only).
  R3    FIXED          the writer as committed.

PRE-REGISTERED RULES for F6 (committed before the first R3 run and before
the fix itself; never changed afterwards; on any failure: stop and
report):

 F-R1 the solve is untouched: R3 vs R3pre, for every gauge, peak,
      positive-phase impulse and arrival (gauge_summary) |d| = 0; the p
      arrays and the time columns identical (np.array_equal); the same
      solver step count (manifest n_steps).
 F-R2 in R3's last obstacles file and last volume file: Time_Of_Peak is
      not uniform (more than one distinct value); on the obstacle faces it
      is not 0 everywhere; every value lies in [0, t_file] (t_file the
      file's own sample time, tolerance 0 on the float32 values against
      float32(t_file)).
 F-R3 at each gauge's cell in R3's last volume file (the A-R6c cell rule),
      Time_Of_Peak equals the probe time of the maximum of that gauge's
      p trace up to that file's time, within 2e-5 relative (the probe
      file prints 6 significant digits, the VTK value is float32).
 F-R4 pMax is unchanged by the reorder: Peak_Overpressure in R3's and
      R3pre's last obstacles and last volume files identical (tolerance
      0), and Peak_Impulse and Impulse identical likewise.

Printed (information): the distinct Time_Of_Peak count in R3pre's files
(expected 1 - the F6 symptom).

OUT-4c C3 (the same batch plan, step C3; owner Q4: subsample per axis,
3D volumes only): two runs of the base case (one obstacle, one gauge)
with volumes p rho U pMax, Time every 0.1 ms, no surfaces:

  R4  k = 1   vtk_volumes without `decimate` (every cell).
  R5  k = 2   the same with `decimate: 2`.

PRE-REGISTERED RULES for 4c (committed before the first R4/R5 run, never
changed afterwards; on any failure: stop and report):

 C-R0 the base grid of the prediction: the case's plan
      (core.refine.plan_levels, the call writer.plan_case makes) gives
      dx_base > 0 - the blockMesh cell, 0.0176 m here, because the charge
      refinement is global - and a base grid starting at 0 on x, y and z.
 C-R1 the solve is untouched: R5 vs R4, for every gauge, peak,
      positive-phase impulse and arrival (gauge_summary summarize_trace)
      |d| = 0, and the same solver step count (manifest n_steps).
 C-R2 every file under gauges\\ (the gauge TSV) byte-identical, R5 vs R4.
 C-R3 the same volume files: the list of names under vtk\\volumes\\ is
      identical (same write times, same count; tolerance 0).
 C-R4 per volume file, R5's cell and point counts equal the prediction
      made here from R4's file of the same time, independently of
      vtk_export.decimate: a cell is kept iff floor(c / dx_base) (C-R0's
      dx_base) is even on x, y and z, c = the mean of the cell's distinct
      points (a
      polyhedron's from its face stream); points = the distinct points of
      the kept cells.
 C-R5 per volume file, R5's values equal R4's at the kept cells, in R4's
      order: every cell-data array (same names, types, order), tolerance
      0 (bytes); each kept cell's point coordinates equal R4's; the TIME
      field equal.
 C-R6 vtk\\manifest.json records the decimation: `decimate` ==
      {"volumes": 2} for R5 and {"volumes": 1} for R4.

Printed (information): R5 / R4 cell and byte ratios.

Needs WSL with blastFoam and an idle VM (`wsl -d Ubuntu -- pgrep -a
blastFoam` empty - checked here, the script refuses otherwise).
Run:  cd blastlab/tests && python -u _e2e_out4_gauges.py [--only 4a|4b|f6|4c]
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
#: OUT-4b B4: the second obstacle box, after the base case's own
OBST2 = (0.03, 0.12, 0.3, 0.5, 0.3, 0.5)
SURF2 = dict(SURF0, fields=SURF0['fields'] + ['impulse', 'impulseMax'],
             obstacle_fields=SURF0['obstacle_fields'] + [
                 'impulse', 'timeOfArrival', 'impulseMax', 'obstacleID'])
VOL2 = dict(VOL0, fields=VOL0['fields'] + ['impulse', 'impulseMax'])
#: OUT-4c C3: R4 (k = 1) and R5 (k = 2); C-R4's base cell [m], set by
#: rule_c0 from the case's plan
VOL4 = dict(VOL0, fields=VOL0['fields'] + ['pMax'])
VOL5 = dict(VOL4, decimate=2)
DX_BASE = []


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
        # re-registered 2026-09-28 (owner): sample indices, not float times
        hit_p = np.flatnonzero(p > (1.0 + ARRIVAL_FRAC) * P_AIR)
        hit_o = np.flatnonzero(ovp > ARRIVAL_FRAC * P_AIR)
        i_p = int(hit_p[0]) if hit_p.size else -1
        i_o = int(hit_o[0]) if hit_o.size else -2
        arr_ms = summarize_trace(t, p)['arrival_ms']
        check(f'A-R3c {tag}: arrival sample from p_over equals the one from '
              f'p (gauge_summary)',
              i_p == i_o and i_p >= 0 and t[i_p] * 1e3 == arr_ms,
              f'p sample {i_p}, p_over sample {i_o}, gauge_summary '
              f'{arr_ms!r} ms')
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
    # re-registered 2026-09-28 (owner): the probe file's printed precision
    rows = np.flatnonzero(t == float(f'{t_file:.6g}'))
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


# ── OUT-4b B4 ────────────────────────────────────────────────────────────
def case2(**vtk):
    """The base case with the second obstacle box (B4)."""
    c = base.case(**vtk)
    c.obstacles = list(c.obstacles) + [OBST2]
    return c


def rule_b1(R2a, R2):
    from blastlab.output.gauge_summary import summarize_trace
    print('\nB-R1: the solve is untouched (R2 vs R2a, |d| = 0)', flush=True)
    g0, g1 = R2a['res'].gauges, R2['res'].gauges
    check('B-R1 the same gauges', len(g0['pressures']) == len(g1['pressures'])
          > 0, f"{len(g0['pressures'])} vs {len(g1['pressures'])}")
    for k, (p0, p1) in enumerate(zip(g0['pressures'], g1['pressures'])):
        s0 = summarize_trace(g0['times'], p0)
        s1 = summarize_trace(g1['times'], p1)
        for key in ('peak_kpa', 'pos_impulse', 'arrival_ms'):
            check(f'B-R1 gauge {k + 1} {key}: |d| = 0', s0[key] == s1[key],
                  f'R2a {s0[key]!r}, R2 {s1[key]!r}')
        print(f'    (info) gauge {k + 1} p arrays identical: '
              f'{np.array_equal(p0, p1) and np.array_equal(g0["times"], g1["times"])}',
              flush=True)


def _array(vd, name):
    return next((a for a in vd.cell_data if a.name == name), None)


def rule_b2(R2):
    from blastlab.output import legacy_vtk as lv
    print('\nB-R2: Peak_Impulse in every file, never decreasing, >= Impulse',
          flush=True)
    series = series_counts(R2['folder'])
    missing, down, below, n_files = [], [], [], 0
    for s, names in sorted(series.items()):
        prev = None
        for n in sorted(names, key=lambda x: float(x[2:-4])):
            vd = lv.read(os.path.join(R2['folder'], 'vtk', s, n))
            n_files += 1
            pk, imp = _array(vd, 'Peak_Impulse'), _array(vd, 'Impulse')
            if pk is None or imp is None:
                missing.append(f'{s}/{n}')
                prev = None
                continue
            v = np.asarray(pk.values, float)
            if np.any(v < np.asarray(imp.values, float)):
                below.append(f'{s}/{n}')
            if prev is not None and (prev.shape != v.shape
                                     or np.any(v < prev)):
                down.append(f'{s}/{n}')
            prev = v
    check('B-R2a Peak_Impulse (and Impulse) in every sections, obstacles '
          'and volumes file', n_files > 0 and not missing,
          f'{n_files} files in {sorted(series)}, missing {missing[:4]}')
    check('B-R2b per cell, Peak_Impulse never decreases along each series',
          n_files > 0 and not down, f'decreases in {down[:4]}')
    check('B-R2c Peak_Impulse >= Impulse in every file, cell by cell',
          n_files > 0 and not below, f'below in {below[:4]}')


def rule_b3(R2):
    from blastlab.output import legacy_vtk as lv
    print('\nB-R3: Peak_Impulse at the gauge cells vs the impulse traces',
          flush=True)
    vols = series_counts(R2['folder']).get('volumes') or []
    if not vols:
        check('B-R3 a last volume file exists', False)
        return
    last = sorted(vols, key=lambda n: float(n[2:-4]))[-1]
    vd = lv.read(os.path.join(R2['folder'], 'vtk', 'volumes', last))
    pk = _array(vd, 'Peak_Impulse')
    if pk is None:
        check(f'B-R3 Peak_Impulse in {last}', False)
        return
    cen = centroids(vd)
    g = R2['res'].gauges
    if 'impulses' not in g:
        check('B-R3 R2 records the gauge impulse traces', False,
              str(sorted(g)))
        return
    for k, pt in enumerate(R2['c'].gauges):
        d = np.linalg.norm(cen - np.asarray(pt, float), axis=1)
        tied = np.flatnonzero(d <= d.min() + 1e-9)
        want = float(np.max(np.asarray(g['impulses'][k], float)))
        vals = [float(pk.values[c]) for c in tied]
        rels = [abs(v - want) / abs(want) for v in vals]
        check(f'B-R3 gauge {k + 1}: Peak_Impulse at its cell ({last}) within '
              f'1 % of the max of its impulse trace', min(rels) <= 0.01,
              f'cells {tied.tolist()} values {vals}, trace max {want!r}, '
              f'rel {min(rels):.3g}')


def predicted_faces(c):
    """B-R4: {box id: exposed faces} from the planned solid mask."""
    from blastlab.solvers.foam import writer
    spec = writer.plan_case(c)
    check('B-R4 precondition: the case plans with no refinement',
          spec.lmax == 0 and spec.amr == 0, f'lmax {spec.lmax} amr {spec.amr}')
    solid = np.asarray(spec.solid, bool)
    cx, cy, cz = (np.asarray(spec.grid[k]) for k in ('x_c', 'y_c', 'z_c'))
    owner = np.zeros(solid.shape, int)
    X, Y, Z = np.meshgrid(cx, cy, cz, indexing='ij')
    for i, (x0, x1, y0, y1, z0, z1) in reversed(list(
            enumerate(spec.obstacles, start=1))):
        inside = ((X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
                  & (Z >= z0) & (Z <= z1))
        owner[inside & solid] = i            # lowest index wins (reversed)
    counts = {i: 0 for i in range(1, len(spec.obstacles) + 1)}
    n = solid.shape
    for idx in zip(*np.nonzero(solid)):
        for ax in range(3):
            for step in (-1, 1):
                nb = list(idx)
                nb[ax] += step
                if not 0 <= nb[ax] < n[ax] or solid[tuple(nb)]:
                    continue
                counts[int(owner[idx])] = counts.get(int(owner[idx]), 0) + 1
    return counts, spec.obstacles


def rule_b4(R2):
    from blastlab.output import legacy_vtk as lv
    print('\nB-R4: Obstacle_ID on every obstacles face', flush=True)
    want, boxes = predicted_faces(R2['c'])
    print(f'    (info) snapped boxes {boxes}; predicted faces {want}',
          flush=True)
    names = series_counts(R2['folder']).get('obstacles') or []
    check('B-R4 obstacles files exist', bool(names))
    bad = []
    for n in sorted(names, key=lambda x: float(x[2:-4])):
        vd = lv.read(os.path.join(R2['folder'], 'vtk', 'obstacles', n))
        ids = _array(vd, 'Obstacle_ID')
        if ids is None or ids.vtk_type != 'int':
            bad.append(f'{n}: no int Obstacle_ID')
            continue
        v = np.asarray(ids.values).astype(int)
        got = {i: int(np.sum(v == i)) for i in want}
        if v.size != vd.n_cells or v.min() < 1 or v.max() > len(want) \
                or got != want:
            bad.append(f'{n}: {got} of {vd.n_cells} faces')
    check('B-R4 every face has an ID in 1..2, and each count equals the '
          'predicted exposed faces, in every obstacles file',
          bool(names) and not bad, f'{len(names)} files; {bad[:3]}')
    if names:
        last = sorted(names, key=lambda x: float(x[2:-4]))[-1]
        vd = lv.read(os.path.join(R2['folder'], 'vtk', 'obstacles', last))
        tp = _array(vd, 'Time_Of_Peak')
        if tp is not None:
            u = np.unique(np.asarray(tp.values, float))
            print(f'    (info) Time_Of_Peak in {last}: {u.size} distinct '
                  f'value(s), min {u.min()!r}, max {u.max()!r}', flush=True)


# ── OUT-4b F6: timeOfArrival before pMax ─────────────────────────────────
VOL3 = dict(VOL0, fields=VOL0['fields'] + ['impulse', 'pMax',
                                           'timeOfArrival', 'impulseMax'])
#: set while R3pre runs: the pre-fix function-object order
PREFIX = []


def spy_prefix_order():
    """R3pre: `arrival` moved back just before `overpressure` - after
    pMax / impulseMax, the order every writer golden had before F6."""
    from blastlab.solvers.foam import writer
    real = writer._controldict_function_objects

    def fos(spec):
        d = real(spec)
        if not PREFIX or 'arrival' not in d:
            return d
        arr = d.pop('arrival')
        out = {}
        for k, v in d.items():
            if k == 'overpressure':
                out['arrival'] = arr
            out[k] = v
        out.setdefault('arrival', arr)
        return out
    writer._controldict_function_objects = fos


def _last(folder, series):
    names = series_counts(folder).get(series) or []
    return sorted(names, key=lambda n: float(n[2:-4]))[-1] if names else None


def rule_f1(R3pre, R3):
    from blastlab.output.gauge_summary import summarize_trace
    print('\nF-R1: the solve is untouched (R3 vs R3pre)', flush=True)
    g0, g1 = R3pre['res'].gauges, R3['res'].gauges
    check('F-R1 the same gauges', len(g0['pressures']) == len(g1['pressures'])
          > 0)
    for k, (p0, p1) in enumerate(zip(g0['pressures'], g1['pressures'])):
        s0 = summarize_trace(g0['times'], p0)
        s1 = summarize_trace(g1['times'], p1)
        for key in ('peak_kpa', 'pos_impulse', 'arrival_ms'):
            check(f'F-R1 gauge {k + 1} {key}: |d| = 0', s0[key] == s1[key],
                  f'R3pre {s0[key]!r}, R3 {s1[key]!r}')
        check(f'F-R1 gauge {k + 1}: p arrays and times identical',
              np.array_equal(p0, p1)
              and np.array_equal(g0['times'], g1['times']))
    n0, n1 = R3pre['m'].get('n_steps'), R3['m'].get('n_steps')
    check('F-R1 the same step count', n0 is not None and n0 == n1,
          f'R3pre {n0}, R3 {n1}')


def rule_f2(R3):
    from blastlab.output import legacy_vtk as lv
    print('\nF-R2: Time_Of_Peak is a real field in R3', flush=True)
    for series in ('obstacles', 'volumes'):
        last = _last(R3['folder'], series)
        if last is None:
            check(f'F-R2 a last {series} file', False)
            continue
        vd = lv.read(os.path.join(R3['folder'], 'vtk', series, last))
        tp = _array(vd, 'Time_Of_Peak')
        if tp is None:
            check(f'F-R2 Time_Of_Peak in {series}/{last}', False)
            continue
        v = np.asarray(tp.values)
        t32 = np.float32(float(last[2:-4]))
        u = np.unique(v)
        check(f'F-R2 {series}/{last}: not uniform', u.size > 1,
              f'{u.size} distinct, min {u.min()!r} max {u.max()!r}')
        if series == 'obstacles':
            check(f'F-R2 {series}/{last}: not 0 on every face',
                  bool(np.any(v != 0)))
        check(f'F-R2 {series}/{last}: every value in [0, t_file = {t32!r}]',
              bool(np.all(v >= 0) and np.all(v <= t32)),
              f'min {v.min()!r} max {v.max()!r}')


def rule_f3(R3):
    from blastlab.output import legacy_vtk as lv
    print('\nF-R3: Time_Of_Peak at the gauge cells vs the p traces',
          flush=True)
    last = _last(R3['folder'], 'volumes')
    if last is None:
        check('F-R3 a last volume file', False)
        return
    t_file = float(last[2:-4])
    vd = lv.read(os.path.join(R3['folder'], 'vtk', 'volumes', last))
    tp = _array(vd, 'Time_Of_Peak')
    if tp is None:
        check(f'F-R3 Time_Of_Peak in volumes/{last}', False)
        return
    cen = centroids(vd)
    g = R3['res'].gauges
    t = np.asarray(g['times'], float)
    upto = t <= float(f'{t_file:.6g}')
    for k, pt in enumerate(R3['c'].gauges):
        p = np.asarray(g['pressures'][k], float)
        want = float(t[upto][int(np.argmax(p[upto]))])
        d = np.linalg.norm(cen - np.asarray(pt, float), axis=1)
        tied = np.flatnonzero(d <= d.min() + 1e-9)
        vals = [float(tp.values[c]) for c in tied]
        rels = [abs(v - want) / want for v in vals]
        check(f'F-R3 gauge {k + 1}: Time_Of_Peak at its cell = the probe '
              f'time of peak p within 2e-5', min(rels) <= 2e-5,
              f'cells {tied.tolist()} values {vals}, probe {want!r}, '
              f'rel {min(rels):.3g}')


def rule_f4(R3pre, R3):
    from blastlab.output import legacy_vtk as lv
    print('\nF-R4: pMax / impulse unchanged by the reorder', flush=True)
    for series in ('obstacles', 'volumes'):
        a, b = _last(R3pre['folder'], series), _last(R3['folder'], series)
        if a is None or a != b:
            check(f'F-R4 {series}: the same last file', False, f'{a} vs {b}')
            continue
        va = lv.read(os.path.join(R3pre['folder'], 'vtk', series, a))
        vb = lv.read(os.path.join(R3['folder'], 'vtk', series, b))
        for name in ('Peak_Overpressure', 'Peak_Impulse', 'Impulse'):
            x, y = _array(va, name), _array(vb, name)
            check(f'F-R4 {series}/{a}: {name} identical',
                  x is not None and y is not None
                  and np.array_equal(x.values, y.values))
        tp = _array(va, 'Time_Of_Peak')
        if tp is not None:
            print(f'    (info) R3pre {series}/{a}: Time_Of_Peak '
                  f'{np.unique(tp.values).size} distinct value(s)',
                  flush=True)


def main_f6(runs):
    spy_prefix_order()
    c3 = case2(vtk_surfaces=SURF2, vtk_volumes=VOL3,
               vtk_gauges={'fields': ['impulse']})
    PREFIX.append(True)
    try:
        R3pre = base.run_stage(runs, 'E2E_OUT4_R3pre', c3)
    finally:
        PREFIX.clear()
    R3 = base.run_stage(runs, 'E2E_OUT4_R3', c3)
    R3pre['c'] = R3['c'] = c3
    for tag, r in (('R3pre', R3pre), ('R3', R3)):
        check(f'{tag}: finished without an error, not stopped early',
              r['error'] is None and r['res'] is not None
              and not r['res'].stopped_early, (r['error'] or '')[-300:])
    if FAIL or base.FAIL:
        FAIL.extend(base.FAIL)
        print(f'FAILED before the rules: {FAIL}')
        return 1
    rule_f1(R3pre, R3)
    rule_f2(R3)
    rule_f3(R3)
    rule_f4(R3pre, R3)
    FAIL.extend(base.FAIL)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'E2E OUT-4b F6 TIME OF PEAK: PASS ({len(RAN)} checks)')
    return 0


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
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv \
        else None
    if only == 'f6':
        return main_f6(runs)
    if only == '4c':
        return main_4c(runs)
    if only != '4b':
        rc = main_4a(runs)
        if rc or only == '4a':
            return rc
    return main_4b(runs)


def cell_streams(vd):
    """Per cell: (point ids in stream order, the stream with sizes only) -
    a plain walk of CELLS, polyhedra (type 42) by their face stream."""
    conn = np.asarray(vd.block('CELLS').values).tolist()
    types = np.asarray(vd.block('CELL_TYPES').values).tolist()
    out, pos = [], 0
    for t in types:
        m = conn[pos]
        e = conn[pos + 1:pos + 1 + m]
        pos += 1 + m
        if t == 42:
            ids, shape, j = [], [e[0]], 1
            for _ in range(e[0]):
                ids += e[j + 1:j + 1 + e[j]]
                shape.append(e[j])
                j += 1 + e[j]
        else:
            ids, shape = e, [m]
        out.append((ids, shape))
    return out


def rule_c0(c):
    from blastlab.core.refine import plan_levels
    from blastlab.solvers.foam.materials import MATERIALS
    print('\nC-R0: the base grid the prediction assumes', flush=True)
    plan = plan_levels(c, rho0=MATERIALS[c.material].rho0)
    starts = [float(plan.base[f'{a}_face'][0]) for a in 'xyz']
    dx = float(plan.dx_base)
    check('C-R0 plan dx_base > 0 and the base grid starts at 0',
          dx > 0 and starts == [0.0] * 3,
          f'dx_base {dx!r} m, starts {starts}, base cells '
          f'{[len(plan.base[f"{a}_face"]) - 1 for a in "xyz"]}')
    DX_BASE[:] = [dx]


def rule_c1_c2(R4, R5):
    from blastlab.output.gauge_summary import summarize_trace
    print('\nC-R1 / C-R2: the solve is untouched (R5 vs R4)', flush=True)
    g4, g5 = R4['res'].gauges, R5['res'].gauges
    check('C-R1 the same gauges', len(g4['pressures']) == len(g5['pressures'])
          > 0, f"{len(g4['pressures'])} vs {len(g5['pressures'])}")
    for k, (p4, p5) in enumerate(zip(g4['pressures'], g5['pressures'])):
        s4 = summarize_trace(g4['times'], p4)
        s5 = summarize_trace(g5['times'], p5)
        for key in ('peak_kpa', 'pos_impulse', 'arrival_ms'):
            check(f'C-R1 gauge {k + 1} {key}: |d| = 0', s4[key] == s5[key],
                  f'R4 {s4[key]!r}, R5 {s5[key]!r}')
    n4, n5 = R4['m'].get('n_steps'), R5['m'].get('n_steps')
    check('C-R1 the same solver step count', bool(n4) and n4 == n5,
          f'R4 {n4}, R5 {n5}')
    f4, f5 = base.files(R4['folder'], 'gauges'), base.files(R5['folder'],
                                                            'gauges')
    diff = sorted(k for k in set(f4) | set(f5) if f4.get(k) != f5.get(k))
    check('C-R2 every file under gauges\\ byte-identical', bool(f4)
          and not diff, f'{sorted(f4)}, differ {diff}')


def rule_c3_to_c6(R4, R5):
    from blastlab.output import legacy_vtk as lv
    print('\nC-R3..C-R6: the volume files', flush=True)
    d4 = os.path.join(R4['folder'], 'vtk', 'volumes')
    d5 = os.path.join(R5['folder'], 'vtk', 'volumes')
    n4 = sorted(n for n in os.listdir(d4) if n.endswith('.vtk'))
    n5 = sorted(n for n in os.listdir(d5) if n.endswith('.vtk'))
    check('C-R3 the same volume file names', bool(n4) and n4 == n5,
          f'R4 {len(n4)}, R5 {len(n5)}')
    bad4, bad5, tot = [], [], [0, 0, 0, 0]
    for name in sorted(set(n4) & set(n5)):
        a = lv.read(os.path.join(d4, name))
        b = lv.read(os.path.join(d5, name))
        pa = np.asarray(a.block('POINTS').values)
        cells = cell_streams(a)
        keep = []
        for i, (ids, _shape) in enumerate(cells):
            cen = pa[sorted(set(ids))].astype(np.float64).mean(axis=0)
            if all(int(np.floor(v / DX_BASE[0])) % 2 == 0 for v in cen):
                keep.append(i)
        want_pts = len({p for i in keep for p in cells[i][0]})
        if b.n_cells != len(keep) or b.n_points != want_pts:
            bad4.append(f'{name}: cells {b.n_cells}/{len(keep)}, points '
                        f'{b.n_points}/{want_pts}')
        tot[0] += a.n_cells
        tot[1] += b.n_cells
        tot[2] += os.path.getsize(os.path.join(d4, name))
        tot[3] += os.path.getsize(os.path.join(d5, name))
        why = []
        if [(x.name, x.vtk_type, x.kind) for x in a.cell_data] != \
                [(x.name, x.vtk_type, x.kind) for x in b.cell_data]:
            why.append('array list')
        else:
            for x, y in zip(a.cell_data, b.cell_data):
                if b.n_cells != len(keep) or np.asarray(x.values)[keep] \
                        .tobytes() != np.asarray(y.values).tobytes():
                    why.append(x.name)
        pb = np.asarray(b.block('POINTS').values)
        bc = cell_streams(b)
        if len(bc) != len(keep) or not all(
                cells[i][1] == s[1] and np.asarray(pa[cells[i][0]]).tobytes()
                == np.asarray(pb[s[0]]).tobytes()
                for i, s in zip(keep, bc)):
            why.append('geometry')
        ta = [x.values.tobytes() for x in a.field_data if x.name == 'TIME']
        tb = [x.values.tobytes() for x in b.field_data if x.name == 'TIME']
        if not ta or ta != tb:
            why.append('TIME')
        if why:
            bad5.append(f'{name}: {why}')
    check('C-R4 every R5 file: cell and point counts equal the prediction',
          bool(n5) and not bad4, str(bad4[:3]))
    check('C-R5 every R5 file: values, point coordinates and TIME equal '
          'R4\'s at the kept cells (tolerance 0)', bool(n5) and not bad5,
          str(bad5[:3]))
    if tot[0] and tot[2]:
        print(f'    (info) cells R5/R4 {tot[1]}/{tot[0]} = '
              f'{tot[1] / tot[0]:.4f}; bytes {tot[3] / tot[2]:.4f}',
              flush=True)
    for tag, R, k in (('R4', R4, 1), ('R5', R5, 2)):
        vm = base.load_json(os.path.join(R['folder'], 'vtk',
                                         'manifest.json'))
        check(f'C-R6 {tag}: manifest decimate == {{"volumes": {k}}}',
              vm.get('decimate') == {'volumes': k}, str(vm.get('decimate')))


def main_4c(runs):
    c4 = base.case(vtk_volumes=VOL4)
    c5 = base.case(vtk_volumes=VOL5)
    rule_c0(c5)
    if FAIL:
        print(f'FAILED before the runs: {FAIL}')
        return 1
    R4 = base.run_stage(runs, 'E2E_OUT4_R4', c4)
    R5 = base.run_stage(runs, 'E2E_OUT4_R5', c5)
    for tag, r in (('R4', R4), ('R5', R5)):
        check(f'{tag}: finished without an error, not stopped early',
              r['error'] is None and r['res'] is not None
              and not r['res'].stopped_early, (r['error'] or '')[-300:])
    if FAIL or base.FAIL:
        FAIL.extend(base.FAIL)
        print(f'FAILED before the rules: {FAIL}')
        return 1
    print(f'    steps: R4 {R4["m"].get("n_steps")}, R5 '
          f'{R5["m"].get("n_steps")}', flush=True)
    rule_c1_c2(R4, R5)
    rule_c3_to_c6(R4, R5)
    FAIL.extend(base.FAIL)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'E2E OUT-4c DECIMATION: PASS ({len(RAN)} checks)')
    return 0


def main_4b(runs):
    c2a = case2(vtk_surfaces=SURF0, vtk_volumes=VOL0)
    c2 = case2(vtk_surfaces=SURF2, vtk_volumes=VOL2,
               vtk_gauges={'fields': ['impulse']})
    R2a = base.run_stage(runs, 'E2E_OUT4_R2a', c2a)
    R2 = base.run_stage(runs, 'E2E_OUT4_R2', c2)
    R2a['c'], R2['c'] = c2a, c2
    for tag, r in (('R2a', R2a), ('R2', R2)):
        check(f'{tag}: finished without an error, not stopped early',
              r['error'] is None and r['res'] is not None
              and not r['res'].stopped_early, (r['error'] or '')[-300:])
    if FAIL or base.FAIL:
        FAIL.extend(base.FAIL)
        print(f'FAILED before the rules: {FAIL}')
        return 1
    print(f'    steps: R2a {R2a["m"].get("n_steps")}, R2 '
          f'{R2["m"].get("n_steps")}', flush=True)
    rule_b1(R2a, R2)
    rule_b2(R2)
    rule_b3(R2)
    rule_b4(R2)
    FAIL.extend(base.FAIL)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'E2E OUT-4b PEAKS + IDS: PASS ({len(RAN)} checks)')
    return 0


def main_4a(runs):
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
