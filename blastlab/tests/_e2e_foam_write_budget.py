"""HD1-15, B3: one real run with a write budget, and one stopped and
resumed (WSL, ~5-10 min, one at a time).

THE CASE. test_foam_3d_smoke.py's --tiny case - 8 kg TNT in a 0.6 m box,
n_procs = 2, gauges on exact mirror cell centres - with an explicit end
time and write_budget = 10. Its boundaries are the Case3D default
(transmit, the ground reflects) instead of the smoke's terminating ones,
so the run reaches t_end and all ten budgeted writes happen.

RUN A, to the end:
  * the root has 10 writes after 0 - or 11 only if the end-time write
    lands within 0.1 x t_end/N of the last one - at the multiples of
    t_end/N;
  * each processorN holds {constant, 0, the final time};
  * the root copy of every purged time reads back (reader.read_scalar on
    its p);
  * the Result has snapshots and at least 2 frames;
  * the probe rows run contiguously to t_end: strictly increasing, from 0
    to t_end, no gap longer than t_end/N;
  * the run's du -sb is at most (writes + 2) x one write x 1.1, one write
    being the final root time dir.

RUN B, stop and resume: the same case, stopped through should_stop after
the 4th ingested write, then backend.resume_run(dir) to t_end.
  * each processorN holds {constant, 0, its newest write} after the stop
    and {constant, 0, final} at the end;
  * the root ends with every one of run A's writes, by name, plus at most
    ONE more, off the budget's multiples - the stop's own write. The plan
    said "the same write count as run A"; a graceful stop (should_stop ->
    `stopAt writeNow`, which the plan asks for) always writes where it
    stops, so that literal count is printed but cannot be the check.
    OpenFOAM-9 keeps `beginTime` in uniform/time (Time.C, writeTimeIndex_
    from beginTime_), so the writes after the restart stay on run A's
    multiples;
  * the probe rows are continuous across the restart (read_probes merges
    the chunks): strictly increasing, from 0 to t_end, no gap longer than
    3 x the longest one in run A's uninterrupted record.

Every criterion above was written before either run. Nothing is deleted
here, and no settings file, GUI or env.auto_cleanup is touched: the
batch removes its own runs afterwards, by exact name.

Run:  cd blastlab/tests && python -u _e2e_foam_write_budget.py
      (WSL; first confirm `wsl -d Ubuntu -- pgrep -a blastFoam` is empty)
"""

import os
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import refine                               # noqa: E402
from blastlab.core.case import (Case3D, material_rho0,         # noqa: E402
                                validate_case)
from blastlab.solvers.hooks import RunHooks                    # noqa: E402

L = 0.6
T_END = 5.0e-5
BUDGET = 10
STOP_AFTER = 4
FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def build_case():
    c = L / 2.0
    case = Case3D(Lx=L, Ly=L, Lz=L, cell_size_m=0.025, charge=8.0,
                  center=(c, c, c), n_snapshots=2, record_frames=150,
                  solver='blastfoam', material='TNT', n_procs=2,
                  t_end=T_END, write_budget=BUDGET)
    # the smoke's own gauge placement: exact mirror cell centres
    plan = refine.plan_levels(case, rho0=material_rho0(case))
    dxf = float(plan.fine['dx'])
    a = (round((L - 0.15) / dxf - 0.5) + 0.5) * dxf
    b = (round(c / dxf - 0.5) + 0.5) * dxf
    case.gauges = [(a, b, b), (b, a, b)]
    return case


class StopAfter(RunHooks):
    """A graceful stop once `n` written times have been ingested -
    step_gate() is called once per ingested write."""

    def __init__(self, n):
        self.n, self.writes = n, 0

    def step_gate(self):
        self.writes += 1

    def should_stop(self):
        return self.writes >= self.n


def root_times(unc):
    from blastlab.solvers.foam import reader
    return [(t, n) for t, n in reader.list_times(unc) if n != '0']


def proc_listing(unc, n_procs=2):
    return {i: sorted(os.listdir(os.path.join(unc, f'processor{i}')))
            for i in range(n_procs)}


def du_sb(posix):
    res = subprocess.run(['wsl', '-d', 'Ubuntu', '-e', 'du', '-sb', posix],
                         capture_output=True, text=True, timeout=300)
    return int(res.stdout.split()[0])


def probe_times(unc):
    from blastlab.solvers.foam import reader
    pr = reader.read_probes(unc)
    return np.asarray(pr['times'], float) if pr else np.array([])


def on_budget(t, iv=T_END / BUDGET):
    """Is `t` one of the budget's multiples of t_end/N (to the 8-digit
    time-dir name)?"""
    k = round(t / iv)
    return k >= 1 and abs(t - k * iv) <= 1e-6 * k * iv


def run_a(case):
    from blastlab.solvers import get_solver
    from blastlab.solvers.foam import env, reader
    print('\nRUN A - to the end')
    t0 = time.time()
    res = get_solver(3, 'blastfoam')(case)
    posix, unc = env.case_paths(res.meta['case_dir'])
    print(f'  run      {posix} ({time.time() - t0:.0f} s, stop: '
          f'{res.stop_reason})')
    times = root_times(unc)
    names = [n for _t, n in times]
    iv = T_END / BUDGET
    close = (len(times) == 11
             and times[-1][0] - times[-2][0] < 0.1 * iv)
    print(f"  root     {len(names)} writes after 0: {' '.join(names)}")
    check(f'the root has {BUDGET} writes after 0 (or {BUDGET + 1} only if '
          f'the end-time write lands one step apart)',
          len(names) == BUDGET or close, f'{len(names)} writes')
    budget_t = [t for t, _n in (times[:-2] + times[-1:] if close
                                else times)]
    check('at the multiples of t_end/N',
          all(on_budget(t) for t in budget_t)
          and abs(times[-1][0] - T_END) <= 1e-6 * T_END,
          str([t for t in budget_t if not on_budget(t)]))
    proc = proc_listing(unc)
    final = names[-1]
    check('each processorN holds {constant, 0, the final time}',
          all(set(v) == {'constant', '0', final} for v in proc.values()),
          str(proc))
    purged = [n for n in names if n not in proc[0]]
    bad = []
    for n in purged:
        path = os.path.join(unc, n, 'p')
        try:
            k = reader.scalar_size(path)
            vals = reader.read_scalar(path, k)
            if k is None or len(vals) != k or not np.isfinite(vals).all():
                bad.append(n)
        except (OSError, ValueError) as exc:
            bad.append(f'{n}: {exc}')
    check(f'the root copy of every purged time reads back '
          f'({len(purged)} purged)', purged and not bad, str(bad))
    frames = (res.meta.get('frames') or {}).get('times')
    n_frames = 0 if frames is None else len(frames)
    check('the Result has snapshots and at least 2 frames',
          len(res.snapshots) >= 1 and n_frames >= 2,
          f'{len(res.snapshots)} snapshots, {n_frames} frames')
    pt = probe_times(unc)
    gaps = np.diff(pt)
    check('the probe rows run contiguously to t_end',
          len(pt) > 2 and pt[0] == 0.0 and (gaps > 0).all()
          and pt[-1] >= T_END * (1 - 1e-6) and gaps.max() <= iv,
          f'{len(pt)} rows, t = {pt[0]:g}..{pt[-1]:g} s, largest gap '
          f'{gaps.max():.3g} s' if len(pt) > 1 else f'{len(pt)} rows')
    du_run = du_sb(posix)
    du_one = du_sb(f'{posix}/{final}')
    cap = (len(names) + 2) * du_one * 1.1
    check('du -sb of the run <= (writes + 2) x one write x 1.1',
          du_run <= cap, f'{du_run:,} B against {cap:,.0f} B (one write '
          f'{du_one:,} B)')
    return dict(posix=posix, unc=unc, names=names, max_gap=float(gaps.max())
                if len(gaps) else np.nan, du=du_run, one=du_one)


def run_b(case, a):
    from blastlab.solvers import get_solver
    from blastlab.solvers.foam import backend, env
    print('\nRUN B - stopped after the 4th write, then resumed')
    t0 = time.time()
    hooks = StopAfter(STOP_AFTER)
    part = get_solver(3, 'blastfoam')(case, hooks)
    posix, unc = env.case_paths(part.meta['case_dir'])
    names = [n for _t, n in root_times(unc)]
    print(f'  run      {posix} ({time.time() - t0:.0f} s, stop: '
          f'{part.stop_reason}; {hooks.writes} writes ingested)')
    print(f"  root     after the stop: {' '.join(names)}")
    check('it stopped early, through should_stop, after the 4th write',
          part.stopped_early and hooks.writes >= STOP_AFTER
          and len(names) < len(a['names']), part.stop_reason)
    proc = proc_listing(unc)
    check('after the stop each processorN holds {constant, 0, its newest '
          'write}',
          all(set(v) == {'constant', '0', names[-1]} for v in proc.values()),
          str(proc))
    t1 = time.time()
    res = backend.resume_run(posix)
    names = [n for _t, n in root_times(unc)]
    print(f'  resume   {time.time() - t1:.0f} s, stop: {res.stop_reason}')
    print(f"  root     at the end: {' '.join(names)}")
    check('the resume runs to t_end',
          not res.stopped_early
          and abs(float(names[-1]) - T_END) <= 1e-6 * T_END, res.stop_reason)
    extra = sorted(set(names) - set(a['names']), key=float)
    missing = sorted(set(a['names']) - set(names), key=float)
    print(f"  [note] the plan's literal check, the same write count as run "
          f"A: {len(names)} against {len(a['names'])}")
    check("the root ends with every one of run A's writes, plus at most "
          "the stop's own, off the budget's multiples",
          not missing and len(extra) <= 1
          and not any(on_budget(float(t)) for t in extra),
          f'missing {missing}, extra {extra}')
    proc = proc_listing(unc)
    check('each processorN ends with {constant, 0, final}',
          all(set(v) == {'constant', '0', names[-1]} for v in proc.values()),
          str(proc))
    pt = probe_times(unc)
    gaps = np.diff(pt)
    bound = 3.0 * a['max_gap']
    check('the probe rows are continuous across the restart',
          len(pt) > 2 and pt[0] == 0.0 and (gaps > 0).all()
          and pt[-1] >= T_END * (1 - 1e-6) and gaps.max() <= bound,
          f'{len(pt)} rows, t = {pt[0]:g}..{pt[-1]:g} s, largest gap '
          f'{gaps.max():.3g} s against {bound:.3g} s' if len(pt) > 1
          else f'{len(pt)} rows')
    return dict(posix=posix, names=names)


def main():
    from blastlab.solvers.foam import env
    print('HD1-15 B3 - a write budget on a real run')
    ok, detail = env.check_available()
    if not ok:
        print(f'  [SKIP] blastFoam unavailable: {detail}')
        print('\nWRITE BUDGET E2E: SKIP')
        return 0
    env.hardware(probe=True)
    case = build_case()
    rep = validate_case(case)
    for e in rep.errors:
        print(f'  [ERROR] {e}')
    for w in rep.warnings:
        print(f'  [warn] {w[:160]}')
    for n in rep.notes:
        if 'budget' in n.lower():
            print(f'  [note] {n[:200]}')
    check('the case validates', rep.ok, f'{len(rep.errors)} errors')
    if not rep.ok:
        print('\nWRITE BUDGET E2E: FAIL - the case does not validate')
        return 1
    a = run_a(case)
    b = run_b(case, a)
    print(f"\n  runs     A {a['posix']}\n           B {b['posix']}")
    print('\nWRITE BUDGET E2E: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL
                                    else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
