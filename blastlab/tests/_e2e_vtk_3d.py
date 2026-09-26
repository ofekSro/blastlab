"""OUT-2 Step 11 (V6), real blastFoam: VTK output on a tiny 3D run.

docs/batches/2026-09-27-out-2-vtk-output.md Step 11 and D6;
docs/model-folder-and-vtk-plan.md sec. 3.7 (V6). One tiny 3D case - a
0.6 m cube, 4 cm base cells refined to resolve 20 kg TNT (~36k cells,
the 8-cells-per-charge-radius rule makes "a few thousand" impossible for
a resolved charge), one obstacle box, one gauge, t_end = 1 ms, serial
(n_procs = 1), adaptive write interval off (adaptive_write = False, B23),
transmit on every side - run five times as model-folder stages
(`jobs.solve_stage(stage_dir=...)` on a SolverWorker):

  A  NONE     no VTK key
  B  SURF     vtk_surfaces only: Step mode, every 25 steps, sections p +
              pMax (the live slice y = 0.3 and x = 0.2), obstacles p + pMax
  C  BOTH     B's surfaces + vtk_volumes: Time mode, every 0.1 ms, p rho U
  D  NODEL    C with BLASTLAB_VTK_NO_DELETE=1 (nothing deleted in WSL)
  E  STOP     C, Stop pressed once the solver passed t = 0.35 ms

PRE-REGISTERED RULES (CLAUDE.md sec. 6; written and committed before the
first run, never changed afterwards):

 1. B vs A (surfaces only vs no export): every file under gauges\\ and
    fields\\ (the snapshot CSVs) byte-identical; the in-memory snapshot
    arrays (Result.snapshots) and the animation frames
    (Result.meta['frames']) identical; the animation file byte-identical.
 2. C vs D (deletion vs deletion disabled):
    a. gauges\\, fields\\ and the animation file byte-identical, file by
       file; snapshot arrays and frames identical;
    b. file count per family = expected +/- 1: volumes = t_end / 0.1 ms
       = 10; each section / obstacle series = n_steps // 25 + 1 (the t = 0
       sample, P6);
    c. every .vtk under vtk\\ is > 0 bytes, and every .vtk.series parses
       and names only files that exist;
    d. vtk\\manifest.json not_converted == [];
    e. during the run, after every export pass, each WSL time directory
       other than 0 is protected (the export's own `protected` set read
       at that pass), one of the two newest ingested writes, or not yet
       converted-and-copied (the conversion runs behind the ingest by
       design, D13); after the final sweep - before the release - the
       WSL time directories are within {0} + protected + the two newest;
       and C deleted at least one written time in WSL (D deleted none);
    f. after the release the scratch is gone (manifest and `test -d`)
       and foam\\SHA256SUMS verifies against the copied files.
 3. C vs A (volumes vs no export, Q7), per gauge, with
    output/gauge_summary.summarize_trace on gauges_3d.txt:
    |d peak| <= 1 %, |d positive-phase impulse| <= 1 %, |d arrival|
    <= 0.5 %. All three, never peak alone.
 4. E (stopped): the scratch is kept (manifest deleted = false and
    `test -d`), at least one volume file was converted, every file a
    series names exists with > 0 bytes, every series parses with its
    times ascending, and not_converted == [].

The model folders stay under the printed runs folder, as evidence. E's
kept scratch is this script's own run directory and is deleted at the end.

Needs WSL with blastFoam and an idle VM (`wsl -d Ubuntu -- pgrep -a
blastFoam` empty - checked here, and the script refuses otherwise).
Run:  cd blastlab/tests && python -u _e2e_vtk_3d.py
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')

import numpy as np                                            # noqa: E402

FAIL = []
RAN = []
#: the export passes of the run in progress (see spy_export)
PASSES = []

T_END = 1e-3
VOL_MS = 0.1
SURF_STEPS = 25
STOP_AT = 3.5e-4
SURF = dict(on=True, mode='step', value=SURF_STEPS, fields=['p', 'pMax'],
            obstacle_fields=['p', 'pMax'], planes=[['x', 0.2]])
VOL = dict(on=True, mode='time', value=VOL_MS, fields=['p', 'rho', 'U'])
#: rule 3 (Q7): relative tolerances
TOL = dict(peak=0.01, impulse=0.01, arrival=0.005)


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''), flush=True)
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def case(**vtk):
    from blastlab.models.case import Case3D
    return Case3D(Lx=0.6, Ly=0.6, Lz=0.6, cell_size_m=0.04, charge=20.0,
                  center=(0.3, 0.3, 0.3), gauges=[(0.3, 0.3, 0.5)],
                  obstacles=[(0.47, 0.57, 0.1, 0.3, 0.1, 0.3)],
                  n_snapshots=2, record_frames=20, solver='blastfoam',
                  material='TNT', n_procs=1, adaptive_write=False,
                  t_end=T_END,
                  bcs={s: 'transmit' for s in ('x_lo', 'x_hi', 'y_lo',
                                               'y_hi', 'z_lo', 'z_hi')},
                  **{k: json.loads(json.dumps(v)) for k, v in vtk.items()})


# ── observing the export ─────────────────────────────────────────────────
def spy_export():
    """Record, after every export pass that ran, the WSL time dirs, the
    export's own `protected` set and what it had ingested / copied."""
    from blastlab.solvers.foam import vtk_export as vx
    from blastlab.solvers.foam.runloop import _is_time
    real = vx.VtkExport.run

    def run(self, done, final=False):
        before = self._next
        real(self, done, final)
        if not self.active or (not final and self._next == before):
            return
        try:
            disk = sorted(n for n in os.listdir(self.spec.case_unc)
                          if _is_time(n))
        except OSError:
            disk = None
        PASSES.append(dict(
            final=final, disk=disk, protected=set(self.protected),
            done=sorted({str(n) for n in done}, key=float),
            copied=set(self.copied), deleted=set(self.deleted),
            not_conv={t for (_f, t) in self.not_converted}))
    vx.VtkExport.run = run


def newest_two(done):
    return set(sorted(done, key=float)[-2:])


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


def run_stage(runs, model, c, stop_at=None, no_delete=False):
    """One model-folder stage to its end (or Stop at `stop_at` s).
    Returns dict(folder, res, error, m, passes)."""
    from blastlab.services import model_folder as mf
    from blastlab.services.validation import validate_case
    from blastlab.solvers import jobs
    from blastlab.solvers.foam.vtk_export import NO_DELETE_ENV
    from blastlab.solvers.worker import SolverWorker
    rep = validate_case(c)
    check(f'{model}: the case validates', rep.ok, str(rep.errors))
    target = mf.prepare_target(runs, model, confirm=lambda t: True)
    if no_delete:
        os.environ[NO_DELETE_ENV] = '1'
    else:
        os.environ.pop(NO_DELETE_ENV, None)
    PASSES.clear()
    t0 = time.time()
    w = SolverWorker([jobs.solve_stage(3, c, stage_dir=target.folder,
                                       run_info=mf.run_info(target, c,
                                                            rep))])
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
        os.environ.pop(NO_DELETE_ENV, None)
    while not w.q.empty():
        w.q.get_nowait()
    res = w.results[0] if w.results else None
    m = load_json(os.path.join(target.folder, 'manifest.json'))
    print(f'    {model}: {time.time() - t0:.0f} s, {m.get("n_steps")} steps, '
          f'{m.get("n_cells")} cells; error {(w.error or "")[-200:]!r}; '
          f'{len(PASSES)} export passes', flush=True)
    return dict(folder=target.folder, res=res, error=w.error, m=m,
                passes=list(PASSES))


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


def animation(folder):
    for n in sorted(os.listdir(folder)):
        if n.startswith('animation.'):
            with open(os.path.join(folder, n), 'rb') as f:
                return n, f.read()
    return None, None


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


def byte_rules(tag, x, y):
    """Rule 1 / 2a: gauges\\, fields\\, the animation, snapshots, frames."""
    for sub in ('gauges', 'fields'):
        fx, fy = files(x['folder'], sub), files(y['folder'], sub)
        diff = sorted(k for k in set(fx) | set(fy) if fx.get(k) != fy.get(k))
        check(f'{tag}: every file under {sub}\\ byte-identical',
              bool(fx) and not diff, f'{len(fx)} files, differ: {diff[:4]}')
    na, ba = animation(x['folder'])
    nb, bb = animation(y['folder'])
    check(f'{tag}: the animation file byte-identical',
          ba is not None and na == nb and ba == bb,
          f'{na} {len(ba or b"")} B vs {nb} {len(bb or b"")} B')
    rx, ry = x['res'], y['res']
    check(f'{tag}: the snapshot arrays identical',
          rx is not None and ry is not None
          and same(rx.snapshots, ry.snapshots),
          str(sorted(getattr(rx, 'snapshots', {}) or {})))
    check(f'{tag}: the animation frames identical',
          rx is not None and ry is not None
          and same(rx.meta.get('frames'), ry.meta.get('frames')))


def gauge_metrics(folder):
    from blastlab.output.gauge_summary import summarize_trace
    path = os.path.join(folder, 'gauges', 'gauges_3d.txt')
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


def series_ok(vtk_dir):
    """(ok, detail, counts): every series parses, its times ascend and
    every file it names exists with > 0 bytes; counts = entries per
    series (relative to vtk\\)."""
    counts, bad = {}, []
    for base, _dirs, names in os.walk(vtk_dir):
        for n in names:
            p = os.path.join(base, n)
            rel = os.path.relpath(p, vtk_dir).replace('\\', '/')
            if n.endswith('.vtk') and os.path.getsize(p) <= 0:
                bad.append(f'empty {rel}')
            if not n.endswith('.vtk.series'):
                continue
            try:
                with open(p, encoding='utf-8') as f:
                    data = json.load(f)
                entries = data['files']
                times = [float(e['time']) for e in entries]
            except (OSError, ValueError, KeyError, TypeError) as exc:
                bad.append(f'{rel}: {exc}')
                continue
            if data.get('file-series-version') != '1.0' \
                    or times != sorted(times):
                bad.append(f'{rel}: version or order')
            for e in entries:
                f = os.path.join(base, *str(e['name']).split('/'))
                if not os.path.isfile(f) or os.path.getsize(f) <= 0:
                    bad.append(f'{rel} -> {e["name"]} missing')
            counts[rel] = len(entries)
    return (bool(counts) and not bad), str(bad[:4]), counts


def verify_sums(folder):
    foam = os.path.join(folder, 'foam')
    try:
        with open(os.path.join(foam, 'SHA256SUMS'), encoding='utf-8') as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
    except OSError as exc:
        return False, str(exc)
    bad = []
    for ln in lines:
        digest, rel = ln[:64], ln[66:]
        try:
            with open(os.path.join(foam, *rel.split('/')), 'rb') as fh:
                got = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            got = None
        if got != digest:
            bad.append(rel)
    return bool(lines) and not bad, f'{len(lines)} files, bad {bad[:3]}'


# ── the rules ────────────────────────────────────────────────────────────
def rule2(C, D):
    print('\nRule 2: C (deletion) vs D (deletion disabled)', flush=True)
    byte_rules('2a C vs D', C, D)
    vtk = os.path.join(C['folder'], 'vtk')
    vm = load_json(os.path.join(vtk, 'manifest.json'))
    fams = vm.get('families') or {}
    n_vol = (fams.get('volumes') or {}).get('count', 0)
    want_vol = int(round(T_END / (VOL_MS / 1e3)))
    check('2b volumes: t_end / 0.1 ms files +/- 1',
          abs(n_vol - want_vol) <= 1, f'{n_vol} vs {want_vol}')
    ok, detail, counts = series_ok(vtk)
    n_steps = int(C['m'].get('n_steps') or 0)
    want_s = n_steps // SURF_STEPS + 1
    surf = {k: v for k, v in counts.items()
            if k.startswith(('sections/', 'obstacles/'))}
    check('2b each section / obstacle series: n_steps // 25 + 1 +/- 1',
          len(surf) == 6 and all(abs(v - want_s) <= 1
                                 for v in surf.values()),
          f'want {want_s} (n_steps {n_steps}): {surf}')
    check('2c every .vtk > 0 bytes; every series parses and names only '
          'files that exist', ok, detail)
    check('2d not_converted == []', vm.get('not_converted') == [],
          str(vm.get('not_converted'))[:300])
    during = [p for p in C['passes'] if not p['final']]
    finals = [p for p in C['passes'] if p['final']]
    bad = []
    for p in during:
        if p['disk'] is None:
            continue
        keep = p['protected'] | newest_two(p['done']) | {'0'}
        extra = [t for t in p['disk']
                 if t not in keep and t in p['copied']
                 and t not in p['not_conv']]
        if extra:
            bad.append((p['done'][-1:], extra))
    check('2e during the run: every WSL time dir is protected, one of the '
          'two newest, or not yet copied',
          bool(during) and not bad, f'{len(during)} passes, {bad[:2]}')
    last = finals[-1] if finals else None
    extra = (None if last is None or last['disk'] is None else
             [t for t in last['disk']
              if t not in last['protected'] | newest_two(last['done'])
              | {'0'}])
    check('2e after the final sweep: within {0} + protected + the two '
          'newest', extra == [],
          f'left {last and last["disk"]}, protected '
          f'{sorted(last["protected"], key=float) if last else None}, '
          f'extra {extra}')
    deleted_c = set().union(*(p['deleted'] for p in C['passes'])) \
        if C['passes'] else set()
    deleted_d = set().union(*(p['deleted'] for p in D['passes'])) \
        if D['passes'] else set()
    check('2e C deleted written times in WSL, D none',
          bool(deleted_c) and not deleted_d,
          f'C {sorted(deleted_c, key=float)}, D {sorted(deleted_d)}')
    scratch = C['m'].get('wsl_scratch') or {}
    posix = scratch.get('posix')
    check('2f the scratch is released (manifest and test -d)',
          scratch.get('deleted') is True and bool(posix)
          and not wsl_dir_exists(posix), str(scratch))
    ok, detail = verify_sums(C['folder'])
    check('2f foam\\SHA256SUMS verifies', ok, detail)


def rule3(A, C):
    print('\nRule 3: C (volumes) vs A (no export), Q7', flush=True)
    ma, mc = gauge_metrics(A['folder']), gauge_metrics(C['folder'])
    check('3 the same gauges', [g['gauge'] for g in ma]
          == [g['gauge'] for g in mc] and ma, str(ma))
    for a, c in zip(ma, mc):
        for key in ('peak', 'impulse', 'arrival'):
            rel = (abs(c[key] - a[key]) / abs(a[key])
                   if a[key] and np.isfinite(a[key]) else np.inf)
            check(f'3 {a["gauge"]} {key}: |d| <= {TOL[key]:.1%}',
                  rel <= TOL[key],
                  f'A {a[key]:.6g}, C {c[key]:.6g}, d {rel:.4%}')


def rule4(E):
    print('\nRule 4: E (stopped)', flush=True)
    res = E['res']
    check('4 the run was stopped early',
          res is not None and res.stopped_early,
          getattr(res, 'stop_reason', None))
    scratch = E['m'].get('wsl_scratch') or {}
    posix = scratch.get('posix')
    check('4 the scratch is kept (manifest and test -d)',
          scratch.get('deleted') is False and bool(posix)
          and wsl_dir_exists(posix), str(scratch))
    vtk = os.path.join(E['folder'], 'vtk')
    vm = load_json(os.path.join(vtk, 'manifest.json'))
    n_vol = ((vm.get('families') or {}).get('volumes') or {}).get('count', 0)
    check('4 volume files were converted', n_vol >= 1, str(n_vol))
    ok, detail, counts = series_ok(vtk)
    check('4 every series parses, ascends and names files that exist',
          ok, f'{detail} {counts}')
    check('4 not_converted == []', vm.get('not_converted') == [],
          str(vm.get('not_converted'))[:300])
    return posix


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
    runs = tempfile.mkdtemp(prefix='blastlab_e2e_vtk_')
    print(f'runs folder (kept as evidence): {runs}', flush=True)
    kept = None
    try:
        print('\nA / B / C / D / E', flush=True)
        A = run_stage(runs, 'E2E_VTK_A_NONE', case())
        B = run_stage(runs, 'E2E_VTK_B_SURF', case(vtk_surfaces=SURF))
        C = run_stage(runs, 'E2E_VTK_C_BOTH',
                      case(vtk_surfaces=SURF, vtk_volumes=VOL))
        D = run_stage(runs, 'E2E_VTK_D_NODEL',
                      case(vtk_surfaces=SURF, vtk_volumes=VOL),
                      no_delete=True)
        E = run_stage(runs, 'E2E_VTK_E_STOP',
                      case(vtk_surfaces=SURF, vtk_volumes=VOL),
                      stop_at=STOP_AT)
        for tag, r in (('A', A), ('B', B), ('C', C), ('D', D)):
            check(f'{tag}: finished without an error, not stopped early',
                  r['error'] is None and r['res'] is not None
                  and not r['res'].stopped_early,
                  (r['error'] or '')[-200:])
        print('\nRule 1: B (surfaces only) vs A (no export)', flush=True)
        byte_rules('1 B vs A', B, A)
        rule2(C, D)
        rule3(A, C)
        kept = rule4(E)
    finally:
        if kept and model_folder.is_run_dir(kept):
            env.delete_runs([kept])
            print(f'    removed this script\'s kept scratch: {kept}')
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'E2E VTK 3D: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
