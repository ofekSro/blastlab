"""P1-25, batch 1d-mpi B5: a 1D blastFoam run on MPI, end to end through
the app path (WSL, ~15 min; nothing else may run on WSL meanwhile).

THE CASE. Case A of docs/verification/1d-mpi-probe.md cut to 1 ms:
1 kg TNT, R = 5 m, dx = 1 mm (5 000 cells), gauges 0.5 / 1 / 2 / 4 m,
t_end = 1e-3 s, run through backend.solve_1d_foam(adaptive_write=False)
at n_procs = 1, then at n_procs = 4 (scotch), one after the other. In
1 ms the shock reaches the 0.5 m and 1 m gauges only.

THE RUN MACHINERY (np 4; the serial run has no processor* dir):
  * exactly 4 processor* dirs;
  * every time written on the ranks is reconstructed at the root, and
    the root reaches t_end;
  * >= 1 live frame (emitted while the solver runs, t > 0) whose
    profile is full length (>= n_cells - 2 rows, the run loop's own
    "complete line" bar), in both runs;
  * the Result carries the four gauges, with samples;
  * the 1D banner names `MPI ranks       : 4` (D2) and the serial one
    names no ranks; both runs end at their end time, not early.

PRE-REGISTERED RULE - written 2026-10-14 10:53, before either run
(also in docs/verification/1d-mpi-probe.md, section B5):
  1. At the 0.5 m and 1.0 m gauges, from the Result's gauge traces with
     output.gauge_summary.summarize_trace (arrival = first sample above
     1.1 x ambient, ARRIVAL_FRAC = 0.10, P1-13): |peak4 - peak1| <=
     1 % of peak1, |I4 - I1| <= 1 % of I1 (positive impulse inside the
     1 ms window - at 1 m the window can cut it, identically in both
     runs), |ta4 - ta1| <= 1 % of ta1. All six must hold.
  2. ms/step np 1 / ms/step np 4 >= 2.0, ms/step being the median
     per-step ExecutionTime delta of each run's log.blastFoam over the
     same steps (the first N, N = the smaller step count; D6).
  Reported, not judged: the app-path wall time np 4 / np 1 (preflight,
  decomposePar and the per-write reconstructPar are in it). If it is
  > 0.6 while rule 2 passes, the ingest is the bottleneck: an owner
  question, no tuning in this batch.
A failed rule is reported with its numbers, never tuned.

The two runs land in /root/blastlab_runs like any app run; nothing is
deleted here (their names are printed). No settings file, GUI or
env.auto_cleanup is touched.

Run:  python -u blastlab/tests/_e2e_foam_1d_mpi.py
      (WSL; it refuses to start a run while `pgrep -a blastFoam` lists
      one - CLAUDE.md 8.6)
"""

import os
import re
import statistics
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import Case1D, validate_case           # noqa: E402
from blastlab.solvers.hooks import RunHooks                    # noqa: E402

T_END = 1.0e-3
GAUGES = [0.5, 1.0, 2.0, 4.0]
JUDGED = (0, 1)                 # the 0.5 m and 1.0 m gauges
TOL = 0.01                      # rule 1: 1 % of serial
SPEEDUP_MIN = 2.0               # rule 2
WALL_NOTE = 0.6                 # reported, not judged
FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def build_case(n_procs):
    return Case1D(solver='blastfoam', charge_kg=1.0, material='TNT',
                  radius_m=5.0, cell_size_m=0.001,
                  gauge_radii=list(GAUGES), t_end=T_END, n_procs=n_procs)


class Recorder(RunHooks):
    """Keeps the log lines and the shape of every frame; a frame counts
    as live when it arrives before finalize_1d's `Done.` line."""

    def __init__(self):
        self.lines, self.frames, self.done = [], [], False

    def log(self, msg):
        self.lines.append(msg)
        if 'Done. ' in msg:
            self.done = True

    def frame(self, field2d, t, levels=None):
        a = np.asarray(field2d)
        self.frames.append(dict(t=float(t), rows=a.shape[-1],
                                live=not self.done,
                                finite=bool(np.isfinite(a).all())))


def wsl_busy():
    res = subprocess.run(['wsl', '-d', 'Ubuntu', '--', 'pgrep', '-a',
                          'blastFoam'], capture_output=True, text=True,
                         timeout=60)
    return res.stdout.strip()


def exec_times(unc):
    """Every `ExecutionTime = x s` of the run's log.blastFoam, in order
    (one per solver step; the first belongs to the end of step 1)."""
    out = []
    with open(os.path.join(unc, 'log.blastFoam'), errors='replace') as f:
        for ln in f:
            m = re.match(r'ExecutionTime = ([0-9.eE+-]+) s', ln)
            if m:
                out.append(float(m.group(1)))
    return out


def ms_per_step(ets, n):
    d = [b - a for a, b in zip([0.0] + ets[:n - 1], ets[:n])]
    return 1e3 * statistics.median(d), 1e3 * ets[n - 1] / n


def run(n_procs):
    from blastlab.solvers.foam import backend, env
    print(f'\nRUN np {n_procs}')
    busy = wsl_busy()
    if busy:
        raise SystemExit(f'  [ABORT] blastFoam already running in WSL:\n'
                         f'{busy}')
    case = build_case(n_procs)
    rep = validate_case(case)
    plan = rep.run_plan
    print(f'  plan     ranks {getattr(plan, "ranks", None)}'
          f' ({getattr(plan, "reason", "")})')
    check(f'np {n_procs}: the case validates', rep.ok, '; '.join(rep.errors))
    hooks = Recorder()
    t0 = time.time()
    res = backend.solve_1d_foam(case, hooks, adaptive_write=False)
    wall = time.time() - t0
    posix, unc = env.case_paths(res.meta['case_dir'])
    print(f'  run      {posix} ({wall:.0f} s, stop: {res.stop_reason})')
    return dict(n=n_procs, res=res, hooks=hooks, wall=wall, posix=posix,
                unc=unc, ets=exec_times(unc))


def machinery(r):
    from blastlab.solvers.foam import backend, reader
    n, res, hooks, unc = r['n'], r['res'], r['hooks'], r['unc']
    n_cells = len(res.meta['r'])
    tag = f'np {n}'
    check(f'{tag}: ends at its end time, not early',
          res.stop_reason in backend._NATURAL_END and not res.stopped_early,
          res.stop_reason)
    procs = sorted(d for d in os.listdir(unc) if d.startswith('processor'))
    root = [nm for _t, nm in reader.list_times(unc)]
    if n > 1:
        check(f'{tag}: exactly {n} processor* dirs',
              procs == [f'processor{i}' for i in range(n)], str(procs))
        on_ranks = [nm for _t, nm in
                    reader.list_times(os.path.join(unc, 'processor0'))]
        missing = sorted(set(on_ranks) - set(root), key=float)
        check(f'{tag}: every rank time is reconstructed at the root '
              f'({len(on_ranks)} on processor0, {len(root)} at the root)',
              on_ranks and not missing, f'missing {missing}')
    else:
        check(f'{tag}: no processor* dir', not procs, str(procs))
    check(f'{tag}: the root reaches t_end',
          root and abs(float(root[-1]) - T_END) <= 1e-6 * T_END,
          root[-1] if root else 'no times')
    live = [f for f in hooks.frames if f['live'] and f['t'] > 0]
    full = [f for f in live if f['rows'] >= n_cells - 2 and f['finite']]
    check(f'{tag}: >= 1 live frame with a full-length profile',
          len(full) >= 1, f'{len(full)} of {len(live)} live frames full '
          f'({n_cells} cells)')
    g = res.gauges
    check(f'{tag}: the Result carries the 4 gauges, with samples',
          len(g['radii']) == len(GAUGES) and len(g['pressures']) == 4
          and len(g['times']) > 10
          and all(len(p) == len(g['times']) for p in g['pressures']),
          f"radii {[round(x, 4) for x in g['radii']]}, "
          f"{len(g['times'])} samples")
    ranks = [ln for ln in hooks.lines if 'MPI ranks       :' in ln]
    want = [f'  MPI ranks       : {n}'] if n > 1 else []
    check(f'{tag}: the banner names the ranks only when > 1 (D2)',
          [ln.rstrip() for ln in ranks] == want, str(ranks))


def gauge_rule(r1, r4):
    from blastlab.output.gauge_summary import summarize_trace
    print('\nRULE 1 - gauges, np 4 against np 1 (1 % each)')
    print('  gauge | metric | np 1 | np 4 | delta %')
    rows = []
    for i in JUDGED:
        s = []
        for r in (r1, r4):
            g = r['res'].gauges
            s.append(summarize_trace(np.asarray(g['times'], float),
                                     np.asarray(g['pressures'][i], float)))
        x = r1['res'].gauges['radii'][i]
        for key, nm in (('peak_kpa', 'peak overpressure [kPa]'),
                        ('pos_impulse', 'positive impulse [Pa s]'),
                        ('arrival_ms', 'arrival [ms]')):
            v1, v4 = float(s[0][key]), float(s[1][key])
            rel = (v4 - v1) / v1 if v1 else np.inf
            print(f'  {x:.4f} m | {nm} | {v1:.6g} | {v4:.6g} | '
                  f'{100 * rel:+.4f}')
            rows.append((f'{GAUGES[i]:g} m {nm}', v1, v4, rel))
        print(f"  {x:.4f} m | impulse complete in the window | "
              f"{s[0]['complete']} | {s[1]['complete']}")
    for nm, v1, v4, rel in rows:
        check(f'{nm} within 1 % of serial', abs(rel) <= TOL,
              f'{v1:.6g} -> {v4:.6g} ({100 * rel:+.4f} %)')


def speed_rule(r1, r4):
    print('\nRULE 2 - ms/step, the same steps')
    n = min(len(r1['ets']), len(r4['ets']))
    if n < 2:
        check('ms/step np 1 / np 4 >= 2.0', False, f'only {n} steps logged')
        return
    med1, mean1 = ms_per_step(r1['ets'], n)
    med4, mean4 = ms_per_step(r4['ets'], n)
    print(f"  steps    np 1 {len(r1['ets'])}, np 4 {len(r4['ets'])}; "
          f"compared over the first {n}")
    print(f'  np 1     median {med1:.1f} ms/step (mean {mean1:.1f})')
    print(f'  np 4     median {med4:.1f} ms/step (mean {mean4:.1f})')
    check(f'ms/step np 1 / np 4 >= {SPEEDUP_MIN}', med1 / med4 >= SPEEDUP_MIN,
          f'{med1 / med4:.2f} (means {mean1 / mean4:.2f})')
    w = r4['wall'] / r1['wall']
    print(f"  [reported] app-path wall np 1 {r1['wall']:.0f} s, np 4 "
          f"{r4['wall']:.0f} s, np 4 / np 1 = {w:.2f}")
    if w > WALL_NOTE and med1 / med4 >= SPEEDUP_MIN:
        print(f'  [owner question] wall ratio {w:.2f} > {WALL_NOTE} while '
              f'the per-step rule passes: the ingest is the bottleneck')


def main():
    from blastlab.solvers.foam import env
    print('P1-25 B5 - 1D blastFoam serial vs np 4 through the app')
    ok, detail = env.check_available()
    if not ok:
        print(f'  [SKIP] blastFoam unavailable: {detail}')
        print('\nFOAM 1D MPI E2E: SKIP')
        return 0
    env.hardware(probe=True)
    r1 = run(1)
    r4 = run(4)
    print('\nMACHINERY')
    machinery(r1)
    machinery(r4)
    gauge_rule(r1, r4)
    speed_rule(r1, r4)
    print(f"\n  runs     np 1 {r1['posix']}\n           np 4 {r4['posix']}")
    print('\nFOAM 1D MPI E2E: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL
                                   else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
