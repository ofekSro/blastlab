"""OUT-1, real blastFoam: the model folder and the WSL scratch release.

docs/model-folder-and-vtk-plan.md sec. 2.3 and sec. 7; batch plan
docs/batches/2026-09-26-out-1-model-folder.md, Step 10. Three runs of the
same tiny 3D case (0.6 m cube, 2.5 cm cells, ~14k cells, terminate on all
sides - the F3D fixture of the QA harness), each a run stage writing a
model folder (`jobs.solve_stage(stage_dir=...)` on a SolverWorker):

  OK      runs to its end. Pass: every sec. 2.2 row a 3D run has is in the
          folder, manifest.failed is empty, foam\\SHA256SUMS verifies
          against the copied files (hashed again here, on Windows), the
          manifest says wsl_scratch.deleted = true, and WSL agrees - `test
          -d <scratch>` fails.
  KILLED  the solver is killed (SIGKILL on the pid in its .run.pid) once
          it has taken steps. Pass: the run fails, the scratch is kept
          (`test -d` succeeds) and the manifest says deleted = false with
          a reason.
  STOP    Stop is pressed once it has taken steps. Pass: the result is
          stopped early, foam\\ is copied, the scratch is kept and the
          manifest says deleted = false, "the run ended before its end
          time".

The pass rules above are fixed before the run (CLAUDE.md 6). The kept
scratches of KILLED and STOP are deleted at the end, after their checks
(they are this script's own run directories). The model folders stay,
under the printed runs folder, as evidence.

Needs WSL with blastFoam and an idle VM (`wsl -d Ubuntu -- pgrep -a
blastFoam` empty - checked here, and the script refuses otherwise).
Run:  cd blastlab/tests && python -u _e2e_model_folder.py
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

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''), flush=True)
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def case():
    from blastlab.models.case import Case3D
    return Case3D(Lx=0.6, Ly=0.6, Lz=0.6, cell_size_m=0.025, charge=8.0,
                  center=(0.3, 0.3, 0.3),
                  gauges=[(0.45, 0.3, 0.3), (0.3, 0.45, 0.3)],
                  n_snapshots=2, record_frames=20, solver='blastfoam',
                  material='TNT',
                  bcs=dict(x_lo='terminate', x_hi='terminate',
                           y_lo='terminate', y_hi='terminate',
                           z_lo='terminate', z_hi='terminate'))


def wsl_dir_exists(posix):
    from blastlab.solvers.foam import env
    p = subprocess.run(env.wsl_plain_argv(f"test -d '{posix}'"),
                       capture_output=True, stdin=subprocess.DEVNULL)
    return p.returncode == 0


def manifest(folder):
    try:
        with open(os.path.join(folder, 'manifest.json'),
                  encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def start(runs, model, rep):
    """prepare + a SolverWorker with one stage_dir stage, started on its
    own thread. Returns (worker, folder)."""
    from blastlab.services import model_folder as mf
    from blastlab.solvers import jobs
    from blastlab.solvers.worker import SolverWorker
    target = mf.prepare_target(runs, model, confirm=lambda t: True)
    c = case()
    w = SolverWorker([jobs.solve_stage(3, c, stage_dir=target.folder,
                                       run_info=mf.run_info(target, c,
                                                            rep))])
    w.start()
    return w, target.folder


def drain(w):
    """Empty the worker queue (nobody else reads it here); returns the
    ('folder', ...) messages seen."""
    out = []
    while not w.q.empty():
        msg = w.q.get_nowait()
        if msg[0] == 'folder':
            out.append(msg)
    return out


def wait_steps(w, n=20, timeout=900):
    """Until the solver has reported `n` steps (or the worker ended)."""
    t0 = time.time()
    while w.is_alive() and time.time() - t0 < timeout:
        p = getattr(w.hooks, '_last_p', None)
        if p is not None and p.step >= n:
            return True
        drain(w)
        time.sleep(0.5)
    return False


def verify_sums(folder):
    """(ok, detail): every line of foam\\SHA256SUMS matches the copy."""
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
    return (bool(lines) and not bad,
            f'{len(lines)} files, {len(bad)} mismatched {bad[:3]}')


def run_ok(runs, rep):
    print('\nOK: a run to its end', flush=True)
    t0 = time.time()
    w, folder = start(runs, 'E2E_OK', rep)
    while w.is_alive():
        drain(w)
        time.sleep(1.0)
    drain(w)
    print(f'    took {time.time() - t0:.0f} s; folder {folder}', flush=True)
    check('the run finished without an error', w.error is None,
          (w.error or '')[-300:])
    res = w.results[0]
    check('and ran to its end (not stopped early)',
          res is not None and not res.stopped_early,
          getattr(res, 'stop_reason', None))
    m = manifest(folder)
    top = sorted(os.listdir(folder))
    print(f'    folder: {top}', flush=True)
    for want in ('MODEL.json', 'run.log', 'manifest.json', 'report.html',
                 'gauges', 'figures', 'fields', 'foam'):
        check(f'the folder holds {want}', want in top, str(top))
    check('an animation (replay frames were recorded)',
          any(n.startswith('animation.') for n in top), str(top))
    check('manifest: nothing failed, 3D blastFoam, cells and ranks',
          m.get('failed') == [] and m.get('solver') == 'blastfoam'
          and m.get('dim') == 3 and m.get('n_cells')
          and m.get('n_procs'), str({k: m.get(k) for k in (
              'failed', 'solver', 'dim', 'n_cells', 'n_procs',
              'n_steps')}))
    ok, detail = verify_sums(folder)
    check('foam\\SHA256SUMS verifies against the copied files', ok, detail)
    scratch = m.get('wsl_scratch') or {}
    check('the manifest says the scratch was deleted',
          scratch.get('deleted') is True and scratch.get('deleted_at'),
          str(scratch))
    posix = scratch.get('posix')
    check('and WSL agrees: the scratch is gone',
          bool(posix) and not wsl_dir_exists(posix), str(posix))
    check('the result knows its model folder and the release',
          res is not None and res.meta.get('model_dir') == folder
          and res.meta.get('scratch_released') is True)


def run_killed(runs, rep):
    from blastlab.solvers.foam import env
    print('\nKILLED: the solver is killed mid-run', flush=True)
    w, folder = start(runs, 'E2E_KILLED', rep)
    stepped = wait_steps(w, 20)
    posix = getattr(w.hooks, 'scratch_posix', None)
    rec = env.scan_runs([posix]).get(posix) if posix else None
    check('the solver was running with a pid', stepped and rec is not None
          and rec.pid and rec.alive, str(rec))
    if rec is not None and rec.pid:
        subprocess.run(env.wsl_plain_argv(
            f'kill -9 {int(rec.pid)} 2>/dev/null; '
            f'pkill -9 -P {int(rec.pid)} 2>/dev/null; true'),
            capture_output=True, stdin=subprocess.DEVNULL)
    w.join(timeout=900)
    drain(w)
    m = manifest(folder)
    scratch = m.get('wsl_scratch') or {}
    print(f'    worker error: {(w.error or "").strip()[-200:]!r}')
    print(f'    stop_reason: {m.get("stop_reason")!r}; scratch: {scratch}')
    check('the run did not finish cleanly',
          w.error is not None or (w.results[0] is not None
                                  and w.results[0].stopped_early),
          str(m.get('stop_reason')))
    check('the manifest says deleted = false, with a reason',
          scratch.get('deleted') is False and scratch.get('kept_because'),
          str(scratch))
    check('and the scratch is really kept', bool(posix)
          and wsl_dir_exists(posix), str(posix))
    return posix


def run_stop(runs, rep):
    print('\nSTOP: Stop pressed mid-run', flush=True)
    w, folder = start(runs, 'E2E_STOP', rep)
    wait_steps(w, 20)
    w.stop()
    w.join(timeout=900)
    drain(w)
    m = manifest(folder)
    scratch = m.get('wsl_scratch') or {}
    res = w.results[0]
    print(f'    stop_reason: {m.get("stop_reason")!r}; scratch: {scratch}')
    check('the result is a stopped one', res is not None
          and res.stopped_early, getattr(res, 'stop_reason', None))
    check('foam\\ was still copied',
          os.path.isfile(os.path.join(folder, 'foam', 'SHA256SUMS')))
    check('the manifest says deleted = false, "ended before its end time"',
          scratch.get('deleted') is False
          and scratch.get('kept_because')
          == 'the run ended before its end time', str(scratch))
    posix = scratch.get('posix')
    check('and the scratch is really kept', bool(posix)
          and wsl_dir_exists(posix), str(posix))
    return posix


def main():
    from blastlab.ui.testing import private_settings
    private_settings()                      # auto_cleanup off (CLAUDE.md 8.2)
    from blastlab.core import settings
    from blastlab.services import model_folder  # noqa: F401 (registers)
    from blastlab.services.validation import validate_case
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
    rep = validate_case(case())
    check('the tiny 3D case validates', rep.ok, str(rep.errors))
    print(f'    {rep.n_cells} cells, ranks '
          f'{getattr(rep.run_plan, "ranks", None)}')
    runs = tempfile.mkdtemp(prefix='blastlab_e2e_mf_')
    print(f'runs folder (kept as evidence): {runs}', flush=True)
    kept = []
    try:
        run_ok(runs, rep)
        kept.append(run_killed(runs, rep))
        kept.append(run_stop(runs, rep))
    finally:
        own = [p for p in kept if p and model_folder.is_run_dir(p)]
        if own:
            env.delete_runs(own)
            print(f'    removed this script\'s kept scratches: {own}')
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'E2E MODEL FOLDER: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
