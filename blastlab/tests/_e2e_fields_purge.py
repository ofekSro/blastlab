"""OUT-3 Step 7, real blastFoam: every run keeps only its newest writes in
WSL; the "Keep all fields in WSL" box turns it off.

docs/batches/2026-09-27-out-3-newest-fields.md Step 7. Every run is a
model-folder stage (`jobs.solve_stage(stage_dir=...)` on a SolverWorker),
so `model_folder.stage_solve` sets the hooks exactly as the GUI does.

The cases (tiny, serial unless said):
  R1  2D axisymmetric, 0.5 x 1.0 m, 1 cm base cell with a level-1 charge
      zone (~5,100 cells), 0.2 kg TNT on the axis, one obstacle, one gauge
      at 0.35 m, t_end = 0.6 ms, write budget 10 (~10 pinned writes, no
      adaptive interval), n_snapshots default, transmit sides (reflect on
      the axis). A = the box ticked, B = the default.
  R2  C = R1's default case stopped once the solver passed t = 0.3 ms,
      then resumed as a model-folder stage (`jobs.resume_stage`).
  R3  a 1D -> 2D chain (1D 0.4 m, 0.2 kg; 2D axisymmetric from the
      profile, 7,200 cells, t_end = 0.8 ms), default vs the box ticked on
      both stages (`model_folder.make_stages`).
  R4  R1 with dynamic AMR (2 levels) on 2 MPI ranks - a decomposed run,
      read per rank - default vs the box ticked.

PRE-REGISTERED RULES (CLAUDE.md sec. 6; written and committed before the
first run, never changed afterwards; a failure is recorded, not re-tuned):

 1. Serial 2D, A (box ticked) vs B (default):
    a. the gauge TSV (gauges\\), the snapshot arrays (Result.snapshots),
       the animation frames (Result.meta['frames']), the pin time (the
       run.log 'hand-off state pinned' lines, up to the '(') and
       final_state (Result.meta['final_state']) are byte-identical /
       exactly equal;
    b. during B, WSL is sampled every 2 s. With (D, P) = the ingested set
       and the protected set of the last export pass before the sample:
       every time dir on disk other than 0 is one of the two newest of D,
       in P, or newer than every time in D (ingested after that pass, or
       not yet); and at most ONE time dir on disk is not yet ingested at
       all (the loop's live `done`). At least 3 samples are taken;
    c. B's scratch is released (manifest wsl_scratch.deleted and
       `test -d`); A's is kept (deleted = false, kept_because = "Keep all
       fields in WSL was ticked", `test -d`) (E5);
    d. the root manifest's wsl_fields: A {mode keep_all, deleted 0}, B
       {mode newest, deleted >= 1} (E7).
 2. Stop and resume: C stopped at about half its end time.
    a. the kept scratch holds only time dirs in {0, start_dir} + the
       protected set + the two newest ingested writes of C's final export
       pass (E2);
    b. the resume's log line 'resuming <run> from t = X' names the newest
       written time on disk before the resume - or, when the log says
       that one cannot be restarted from (P1-5), the newest time the log
       does not refuse - and the resume finishes without an error;
    c. its gauges vs A's, per gauge, with output/gauge_summary.
       summarize_trace: |d peak| <= 1 %, |d positive-phase impulse| <=
       1 %, |d arrival| <= 0.5 %. All three, never peak alone.
 3. 1D -> 2D chain, default vs the box ticked: the hand-off profile at the
    model root is byte-identical (N2-13); the 1D stage deleted nothing
    (its manifest's wsl_fields.deleted == 0 in both, E3); both chains
    finish without an error.
 4. Decomposed AMR 2D on 2 ranks, default vs the box ticked:
    a. per gauge, peak / positive-phase impulse / arrival within 1 / 1 /
       0.5 %;
    b. the same snapshot labels;
    c. the default run deleted >= 1 written time; after its final export
       pass (before the release) no time the E6 plan - recomputed from
       that pass's ingested set, protected set, per-rank readiness and
       per-rank meshes - allows is still on any rank, and the two newest
       ingested times ready on every rank, and every protected time, are
       still on every rank.

The model folders stay under the printed runs folder, as evidence. The
scratches this script keeps (the ticked runs, E5) are deleted at the end.

Needs WSL with blastFoam and an idle VM (`wsl -d Ubuntu -- pgrep -a
blastFoam` empty - checked here, and the script refuses otherwise).
Run:  cd blastlab/tests && python -u _e2e_fields_purge.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')

import numpy as np                                            # noqa: E402

FAIL = []
RAN = []
#: the export passes of the run in progress (see spy_export)
PASSES = []
#: the live export and its `done` of the run in progress
LIVE = {}
LOCK = threading.Lock()

T_END = 6e-4
STOP_AT = 3e-4
#: rules 2c / 4a: relative tolerances (the OUT-2 Q7 thresholds)
TOL = dict(peak=0.01, impulse=0.01, arrival=0.005)
AXIS = dict(x_lo='reflect', x_hi='transmit', y_lo='transmit',
            y_hi='transmit')


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''), flush=True)
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def case2d(**kw):
    from blastlab.models.case import Case2D
    base = dict(geometry='axisymmetric', Lx=0.5, Ly=1.0, cell_size_m=0.01,
                charge=0.2, center=(0.0, 0.5), charge_refine='zone',
                gauges=[(0.35, 0.5)], obstacles=[(0.3, 0.33, 0.2, 0.8)],
                solver='blastfoam', material='TNT', n_procs=1,
                adaptive_write=False, write_budget=10, t_end=T_END,
                record_frames=20, bcs=dict(AXIS))
    base.update(kw)
    return Case2D(**base)


# ── observing the purge ──────────────────────────────────────────────────
def _times(path):
    from blastlab.solvers.foam.runloop import _is_time
    try:
        return sorted((n for n in os.listdir(path) if _is_time(n)),
                      key=float)
    except OSError:
        return None


def _ranks(ex):
    """{rank: (times, times holding polyMesh/)} of a decomposed run."""
    out = {}
    for i in range(int(ex.spec.n_procs)):
        pu = os.path.join(ex.spec.case_unc, f'processor{i}')
        names = _times(pu) or []
        out[i] = (names, {n for n in names
                          if os.path.isdir(os.path.join(pu, n, 'polyMesh'))})
    return out


def spy_export():
    """Record, after every export pass that ran, what it had ingested,
    protected and deleted, and the disk; on a decomposed run's final pass
    also the per-rank state and the E6 plan recomputed from it."""
    from blastlab.solvers.foam import runloop
    from blastlab.solvers.foam import vtk_export as vx
    real = vx.VtkExport.run

    def run(self, done, final=False):
        before = self._next
        real(self, done, final)
        with LOCK:
            LIVE['ex'], LIVE['done'] = self, done
        if not self.active or (not final and self._next == before):
            return
        names = sorted({str(n) for n in done}, key=float)
        rec = dict(final=final, done=names, protected=set(self.protected),
                   deleted=set(self.deleted),
                   start=str(self.spec.start_dir),
                   disk=_times(self.spec.case_unc))
        if final and getattr(self.spec, 'decomposed', False):
            ranks = _ranks(self)
            ready = runloop.common_ready_times(self.spec, self.fields) \
                or set()
            ordered = sorted(set().union(*(t for t, _m in ranks.values())),
                             key=float)
            rec.update(ranks=ranks, ready=set(ready), plan=vx.vtk_purge_plan(
                names, (), (), names, self.spec.start_dir, (),
                self.protected, self.spec.n_procs, ordered=ordered,
                require_copy=False, per_rank_ready=ready,
                rank_mesh={i: m for i, (_t, m) in ranks.items()}))
        with LOCK:
            PASSES.append(rec)
    vx.VtkExport.run = run


def newest_two(names):
    return set(sorted(names, key=float)[-2:])


def sampler(stop, out):
    """Rule 1b: every 2 s, the WSL listing against the last pass."""
    while not stop.wait(2.0):
        with LOCK:
            last = PASSES[-1] if PASSES else None
            ex, done = LIVE.get('ex'), LIVE.get('done')
        if last is None or ex is None or not last['done']:
            continue
        disk = [t for t in (_times(ex.spec.case_unc) or []) if t != '0']
        try:
            live = {str(n) for n in list(done)}
        except RuntimeError:             # the loop grew it mid-copy
            continue
        top = max(float(t) for t in last['done'])
        keep = newest_two(last['done']) | last['protected']
        bad = [t for t in disk if t not in keep and float(t) <= top]
        out.append(dict(disk=disk, bad=bad,
                        not_ingested=[t for t in disk if t not in live]))


# ── running one stage ────────────────────────────────────────────────────
def wsl_dir_exists(posix):
    from blastlab.solvers.foam import env
    p = subprocess.run(env.wsl_plain_argv(f"test -d '{posix}'"),
                       capture_output=True, stdin=subprocess.DEVNULL)
    return p.returncode == 0


def load_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def read_log(folder):
    try:
        with open(os.path.join(folder, 'run.log'), encoding='utf-8',
                  errors='replace') as f:
            return f.read().splitlines()
    except OSError:
        return []


def drive(w, stop_at=None, samples=None):
    """Run the worker to its end, pressing Stop at `stop_at` s; with
    `samples`, the rule 1b sampler runs meanwhile."""
    PASSES.clear()
    LIVE.clear()
    halt = threading.Event()
    th = None
    if samples is not None:
        th = threading.Thread(target=sampler, args=(halt, samples),
                              daemon=True)
        th.start()
    t0 = time.time()
    w.start()
    stopped = False
    try:
        while w.is_alive():
            while not w.q.empty():
                w.q.get_nowait()
            p = getattr(w.hooks, '_last_p', None)
            if stop_at and not stopped and p is not None and p.t >= stop_at:
                w.stop()
                stopped = True
            time.sleep(0.5)
    finally:
        halt.set()
        if th is not None:
            th.join(5)
    while not w.q.empty():
        w.q.get_nowait()
    return time.time() - t0


def run_stage(runs, model, c, stop_at=None, samples=None):
    """One model-folder stage to its end (or Stop at `stop_at` s).
    Returns dict(folder, res, error, m, passes, log)."""
    from blastlab.services import model_folder as mf
    from blastlab.services.validation import validate_case
    from blastlab.solvers import jobs
    from blastlab.solvers.worker import SolverWorker
    rep = validate_case(c)
    check(f'{model}: the case validates', rep.ok, str(rep.errors))
    target = mf.prepare_target(runs, model, confirm=lambda t: True)
    w = SolverWorker([jobs.solve_stage(c.dim, c, stage_dir=target.folder,
                                       run_info=mf.run_info(target, c,
                                                            rep))])
    dt = drive(w, stop_at, samples)
    res = w.results[0] if w.results else None
    m = load_json(os.path.join(target.folder, 'manifest.json'))
    print(f'    {model}: {dt:.0f} s, {m.get("n_steps")} steps, '
          f'{m.get("n_cells")} cells; error {(w.error or "")[-200:]!r}; '
          f'{len(PASSES)} export passes; wsl_fields {m.get("wsl_fields")}',
          flush=True)
    return dict(folder=target.folder, res=res, error=w.error, m=m,
                passes=list(PASSES), log=read_log(target.folder))


def resume_stage(runs, model, c, posix):
    from blastlab.services import model_folder as mf
    from blastlab.solvers import jobs
    from blastlab.solvers.worker import SolverWorker
    target = mf.prepare_target(runs, model, confirm=lambda t: True)
    w = SolverWorker([jobs.resume_stage(c.dim, posix, case=c,
                                        stage_dir=target.folder,
                                        run_info=mf.run_info(target, c))])
    dt = drive(w)
    res = w.results[0] if w.results else None
    m = load_json(os.path.join(target.folder, 'manifest.json'))
    print(f'    {model}: {dt:.0f} s; error {(w.error or "")[-200:]!r}',
          flush=True)
    return dict(folder=target.folder, res=res, error=w.error, m=m,
                log=read_log(target.folder))


def run_chain(runs, model, keep):
    from blastlab.models.case import Case1D, Case2D
    from blastlab.services import model_folder as mf
    from blastlab.services.validation import validate_case
    from blastlab.solvers.worker import SolverWorker
    target = mf.prepare_target(runs, model, confirm=lambda t: True)
    hand = mf.handoff_paths(target, [1, 2])[(1, 2)]
    c1 = Case1D(radius_m=0.4, charge_kg=0.2, cell_size_m=0.004,
                gauge_radii=[0.35], n_snapshots=1, solver='blastfoam',
                adaptive_write=False, profile_file=hand,
                keep_all_fields=keep)
    c2 = Case2D(geometry='axisymmetric', Lx=0.6, Ly=1.2, cell_size_m=0.01,
                center=(0.0, 0.6), gauges=[(0.5, 0.6)], n_snapshots=1,
                init_mode='profile1d', profile_file_in=hand,
                solver='blastfoam', material='TNT', eos='idealGas',
                n_procs=1, adaptive_write=False, t_end=8e-4,
                bcs=dict(AXIS), keep_all_fields=keep)
    reps = [validate_case(c1), validate_case(c2, pending_inputs=True)]
    check(f'{model}: both stages validate', all(r.ok for r in reps),
          str([r.errors for r in reps]))
    w = SolverWorker(mf.make_stages(target, [(1, c1), (2, c2)], reps))
    dt = drive(w)
    print(f'    {model}: {dt:.0f} s; error {(w.error or "")[-200:]!r}',
          flush=True)
    try:
        with open(hand, 'rb') as f:
            data = f.read()
    except OSError:
        data = None
    m1 = load_json(os.path.join(target.folder, '1d', 'manifest.json'))
    m2 = load_json(os.path.join(target.folder, '2d', 'manifest.json'))
    return dict(folder=target.folder, error=w.error, handoff=data, m1=m1,
                m2=m2)


# ── comparisons ──────────────────────────────────────────────────────────
def files(folder, sub):
    root = os.path.join(folder, sub)
    out = {}
    for base, _dirs, names in os.walk(root):
        for n in names:
            p = os.path.join(base, n)
            with open(p, 'rb') as f:
                out[os.path.relpath(p, root).replace('\\', '/')] = f.read()
    return out


def same(a, b):
    """Recursive equality: arrays exactly (NaN == NaN), dicts, lists."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        a, b = np.asarray(a), np.asarray(b)
        if a.shape != b.shape or a.dtype != b.dtype:
            return False
        if a.dtype.kind in 'fc':
            return bool(np.array_equal(a, b, equal_nan=True))
        return bool(np.array_equal(a, b))
    return a == b


def pins(log):
    return [ln.split('(')[0].strip() for ln in log
            if 'hand-off state pinned' in ln]


def gauge_metrics(folder):
    from blastlab.output.gauge_summary import summarize_trace
    path = os.path.join(folder, 'gauges', 'gauges_2d.txt')
    with open(path, encoding='utf-8') as f:
        head = f.readline().rstrip('\n').split('\t')
    data = np.loadtxt(path, skiprows=1, ndmin=2)
    out = []
    for j, col in enumerate(head):
        if col.startswith('p_'):
            s = summarize_trace(data[:, 0], data[:, j])
            out.append(dict(gauge=col, peak=s['peak_kpa'],
                            impulse=s['pos_impulse'],
                            arrival=s['arrival_ms']))
    return out


def gauge_rule(tag, ref, got):
    try:
        ma, mb = gauge_metrics(ref['folder']), gauge_metrics(got['folder'])
    except (OSError, ValueError) as exc:
        check(f'{tag}: the gauge TSVs read', False, str(exc))
        return
    check(f'{tag}: the same gauges', bool(ma) and [g['gauge'] for g in ma]
          == [g['gauge'] for g in mb], str(ma))
    for a, b in zip(ma, mb):
        for key in ('peak', 'impulse', 'arrival'):
            rel = (abs(b[key] - a[key]) / abs(a[key])
                   if a[key] and np.isfinite(a[key]) else np.inf)
            check(f'{tag} {a["gauge"]} {key}: |d| <= {TOL[key]:.1%}',
                  rel <= TOL[key],
                  f'ref {a[key]:.6g}, got {b[key]:.6g}, d {rel:.4%}')


def finished(tag, r):
    check(f'{tag}: finished without an error, not stopped early',
          r['error'] is None and r['res'] is not None
          and not r['res'].stopped_early, (r['error'] or '')[-200:])


# ── the rules ────────────────────────────────────────────────────────────
def rule1(A, B, samples):
    from blastlab.services.model_folder import KEEP_ALL_WHY
    print('\nRule 1: A (box ticked) vs B (default), serial 2D', flush=True)
    finished('1 A', A)
    finished('1 B', B)
    ga, gb = files(A['folder'], 'gauges'), files(B['folder'], 'gauges')
    check('1a the gauge TSV byte-identical', bool(ga) and ga == gb,
          f'{sorted(ga)} vs {sorted(gb)}')
    ra, rb = A['res'], B['res']
    ok = ra is not None and rb is not None
    check('1a the snapshot arrays identical',
          ok and bool(ra.snapshots) and same(ra.snapshots, rb.snapshots),
          str(sorted(getattr(ra, 'snapshots', {}) or {})))
    check('1a the animation frames identical',
          ok and same(ra.meta.get('frames'), rb.meta.get('frames')))
    check('1a the pin time identical', pins(A['log']) == pins(B['log']),
          f'{pins(A["log"])} vs {pins(B["log"])}')
    check('1a final_state identical',
          ok and ra.meta.get('final_state') is not None
          and same(ra.meta.get('final_state'), rb.meta.get('final_state')))
    bad = [s for s in samples if s['bad'] or len(s['not_ingested']) > 1]
    check('1b every 2 s sample: two newest / protected / newer than the '
          'last pass, at most one not ingested',
          len(samples) >= 3 and not bad,
          f'{len(samples)} samples, bad {bad[:2]}')
    sa = A['m'].get('wsl_scratch') or {}
    sb = B['m'].get('wsl_scratch') or {}
    check('1c B: the scratch is released (manifest and test -d)',
          sb.get('deleted') is True and bool(sb.get('posix'))
          and not wsl_dir_exists(sb['posix']), str(sb))
    check('1c A: the scratch is kept, and says why (E5)',
          sa.get('deleted') is False and sa.get('kept_because')
          == KEEP_ALL_WHY and bool(sa.get('posix'))
          and wsl_dir_exists(sa['posix']), str(sa))
    fa, fb = A['m'].get('wsl_fields') or {}, B['m'].get('wsl_fields') or {}
    check('1d wsl_fields: A keep_all / 0, B newest / >= 1',
          fa.get('mode') == 'keep_all' and fa.get('deleted') == 0
          and fb.get('mode') == 'newest' and (fb.get('deleted') or 0) >= 1,
          f'A {fa}, B {fb}')
    return sa.get('posix')


def rule2(runs, A, c):
    print('\nRule 2: C stopped at ~half its end time, then resumed',
          flush=True)
    C = run_stage(runs, 'E2E_OUT3_C_STOP', c, stop_at=STOP_AT)
    check('2 C was stopped early',
          C['res'] is not None and C['res'].stopped_early,
          getattr(C['res'], 'stop_reason', None))
    posix = (C['m'].get('wsl_scratch') or {}).get('posix')
    finals = [p for p in C['passes'] if p['final']]
    last = finals[-1] if finals else None
    from blastlab.solvers.foam import env
    disk = _times(env.unc(posix)) if posix else None
    allowed = (None if last is None else
               {'0', last['start']} | last['protected']
               | newest_two(last['done']))
    extra = None if disk is None or allowed is None else \
        [t for t in disk if t not in allowed]
    check('2a the kept scratch: only {0, start} + protected + the two '
          'newest', extra == [] and bool(disk),
          f'disk {disk}, protected {sorted(last["protected"]) if last else None}'
          f', extra {extra}')
    if not posix or not disk:
        check('2b the resume ran', False, 'no kept scratch')
        return
    R = resume_stage(runs, 'E2E_OUT3_C_RESUME', c, posix)
    refused = set()
    for ln in R['log']:
        m = re.search(r'cannot restart from t = (\S+):', ln)
        if m:
            refused.add(m.group(1))
    want = next((t for t in reversed(disk) if t not in refused), None)
    got = next((m.group(1) for ln in R['log']
                for m in [re.search(r'resuming \S+ from t = (\S+) \(', ln)]
                if m), None)
    check('2b the resume starts from the newest complete write',
          got is not None and got == want,
          f'from {got}, newest {disk[-1]}, refused {sorted(refused)}')
    check('2b the resume finishes without an error',
          R['error'] is None and R['res'] is not None,
          (R['error'] or '')[-300:])
    gauge_rule('2c resumed vs A', A, R)


def rule3(runs):
    print('\nRule 3: 1D -> 2D chain, default vs the box ticked', flush=True)
    D = run_chain(runs, 'E2E_OUT3_CHAIN_DEF', False)
    K = run_chain(runs, 'E2E_OUT3_CHAIN_KEEP', True)
    for tag, r in (('default', D), ('ticked', K)):
        check(f'3 the {tag} chain finished without an error',
              r['error'] is None, (r['error'] or '')[-300:])
    check('3 the hand-off profile at the model root is byte-identical',
          D['handoff'] is not None and D['handoff'] == K['handoff'],
          f'{len(D["handoff"] or b"")} vs {len(K["handoff"] or b"")} B')
    w1d, w1k = D['m1'].get('wsl_fields') or {}, K['m1'].get('wsl_fields') \
        or {}
    check('3 the 1D stage deleted nothing (E3)',
          w1d.get('deleted') == 0 and w1k.get('deleted') == 0,
          f'default {w1d}, ticked {w1k}')
    kept = [((K['m1'].get('wsl_scratch') or {}).get('posix')),
            ((K['m2'].get('wsl_scratch') or {}).get('posix'))]
    return [p for p in kept if p]


def rule4(runs):
    print('\nRule 4: decomposed AMR 2D on 2 ranks, default vs ticked',
          flush=True)
    c = case2d(charge_refine='global', amr_levels=2, n_procs=2)
    D = run_stage(runs, 'E2E_OUT3_AMR_DEF', c)
    K = run_stage(runs, 'E2E_OUT3_AMR_KEEP',
                  case2d(charge_refine='global', amr_levels=2, n_procs=2,
                         keep_all_fields=True))
    finished('4 default', D)
    finished('4 ticked', K)
    gauge_rule('4a default vs ticked', K, D)
    check('4b the same snapshot labels',
          D['res'] is not None and K['res'] is not None
          and sorted(D['res'].snapshots) == sorted(K['res'].snapshots),
          f'{sorted(getattr(D["res"], "snapshots", {}) or {})} vs '
          f'{sorted(getattr(K["res"], "snapshots", {}) or {})}')
    finals = [p for p in D['passes'] if p['final'] and 'ranks' in p]
    last = finals[-1] if finals else None
    deleted = set().union(*(p['deleted'] for p in D['passes'])) \
        if D['passes'] else set()
    check('4c the default run deleted written times', bool(deleted),
          str(sorted(deleted, key=float)))
    if last is None:
        check('4c the final pass saw the ranks', False, 'no final pass')
    else:
        left = {i: set(t) for i, (t, _m) in last['ranks'].items()}
        still = sorted({t for s in left.values() for t in s}
                       & set(last['plan']), key=float)
        check('4c no time the E6 plan allows is still on any rank',
              not still, f'still {still}; plan {last["plan"]}')
        anchors = newest_two([t for t in last['done']
                              if t in last['ready']]) | last['protected']
        gone = {i: sorted(anchors - s, key=float) for i, s in left.items()
                if anchors - s}
        check('4c the two newest ready times and every protected time '
              'are on every rank', not gone,
              f'missing {gone}; anchors {sorted(anchors, key=float)}')
    return (K['m'].get('wsl_scratch') or {}).get('posix')


def main():
    from blastlab.ui.testing import private_settings
    private_settings()                      # auto_cleanup off (CLAUDE.md 8.2)
    from blastlab.core import settings
    from blastlab.services import model_folder
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
    spy_export()
    runs = tempfile.mkdtemp(prefix='blastlab_e2e_out3_')
    print(f'runs folder (kept as evidence): {runs}', flush=True)
    kept = []
    try:
        print('\nA / B', flush=True)
        A = run_stage(runs, 'E2E_OUT3_A_KEEP', case2d(keep_all_fields=True))
        samples = []
        B = run_stage(runs, 'E2E_OUT3_B_DEFAULT', case2d(), samples=samples)
        kept.append(rule1(A, B, samples))
        rule2(runs, A, case2d())
        kept += rule3(runs)
        kept.append(rule4(runs))
    finally:
        for posix in kept:
            if posix and model_folder.is_run_dir(posix):
                env.delete_runs([posix])
                print(f'    removed this script\'s kept scratch: {posix}')
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'E2E FIELDS PURGE: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
