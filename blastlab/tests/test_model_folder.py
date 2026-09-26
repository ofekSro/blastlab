"""The model folder (OUT-1): services/model_folder.py.

docs/model-folder-and-vtk-plan.md section 2; batch plan
docs/batches/2026-09-26-out-1-model-folder.md, Steps 1-4.

  A  the name rule, the folder check and `folder_for` (pure)
  B  prepare / bind_case / write_all / the manifest / run.log, on a
     native 1D and a native 2D axisymmetric result (a few hundred steps)
  C  jobs.solve_stage(..., stage_dir=...) on a SolverWorker run on this
     thread: the folder is complete before ('result', 0); a failed TSV, a
     failed hand-off, a raising solver and a stop before start

Everything runs in temp folders; the private settings file of
`char_common` keeps the real one untouched (CLAUDE.md 8.2).

Run:  cd blastlab/tests && python test_model_folder.py   (or under pytest)
"""
import json
import os
import queue
import shutil
import sys
import tempfile
import threading

import char_common as cc

from blastlab.models.case import (Case1D, Case2D, case_to_dict,  # noqa: E402
                                  load_case)
from blastlab.services import model_folder as mf            # noqa: E402
from blastlab.solvers import jobs                            # noqa: E402
from blastlab.solvers.worker import GuiHooks                 # noqa: E402

#: the keys of plan sec. 2.2, in order, plus the additive `failed`
MANIFEST_KEYS = ['model', 'runs_dir', 'created', 'finished', 'solver',
                 'dim', 'case_file', 'git_commit', 'stop_reason',
                 'n_cells', 'n_procs', 'n_steps', 'wsl_scratch', 'outputs',
                 'missing', 'vtk', 'failed']


# ── A: the name rule, check, folder_for ──────────────────────────────────
def test_a_empty_and_whitespace():
    assert mf.validate_name('') == 'the name is empty'
    assert mf.validate_name(None) == 'the name is empty'
    assert mf.validate_name('   \t ') == 'the name is empty'


def test_a_forbidden_chars():
    for c in '\\/:*?"<>|':
        why = mf.validate_name(f'A{c}B')
        assert why and c in why, (c, why)
    assert 'control' in mf.validate_name('A\x01B')
    assert 'control' in mf.validate_name('A\tB')


def test_a_reserved_names():
    for name in ('CON', 'con', 'con.txt', 'Con.tar.gz', 'NUL', 'PRN',
                 'AUX', 'COM1', 'com9', 'LPT1', 'LPT9', 'lpt9.log'):
        why = mf.validate_name(name)
        assert why and 'reserved' in why, (name, why)
    # not device names: a longer stem, or COM0/LPT10
    for name in ('CONSOLE', 'COM0', 'LPT10', 'NULL', 'model.con'):
        assert mf.validate_name(name) is None, name


def test_a_trailing_dot_and_space():
    assert 'dot' in mf.validate_name('MODEL.')
    assert 'dot' in mf.validate_name('MODEL. ')     # trimmed, then a dot
    assert 'dot' in mf.validate_name('..')
    assert 'dot' in mf.validate_name('.')
    # a trailing space alone is trimmed away: the folder is 'MODEL'
    assert mf.validate_name('MODEL ') is None
    assert mf.validate_name(' MODEL') is None


def test_a_length():
    assert mf.validate_name('M' * 100) is None
    why = mf.validate_name('M' * 101)
    assert why and '100' in why and '101' in why, why
    # the limit applies after trimming
    assert mf.validate_name(' ' + 'M' * 100 + ' ') is None


def test_a_check_messages():
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_a_')
    try:
        assert mf.check(tmp, 'MODEL') == []
        assert mf.check('', 'MODEL') == ['Runs folder is empty']
        assert mf.check('  ', 'MODEL') == ['Runs folder is empty']
        missing = os.path.join(tmp, 'nope')
        assert mf.check(missing, 'MODEL') == [
            f'Runs folder does not exist: {missing}']
        got = mf.check(tmp, 'A:B')
        assert len(got) == 1 and got[0].startswith('Model name: '), got
        # both boxes wrong: one message each, the folder first
        got = mf.check('', '')
        assert got == ['Runs folder is empty',
                       'Model name: the name is empty'], got
        desk = os.path.join(os.path.expanduser('~'), 'Desktop')
        if os.path.isdir(desk):
            got = mf.check(desk, 'MODEL')
            assert got and got[0].startswith(
                'Runs folder cannot be the Desktop'), got
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_folder_for_case_insensitive():
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_a_')
    try:
        assert mf.folder_for(tmp, ' MODEL ') == os.path.join(tmp, 'MODEL')
        os.mkdir(os.path.join(tmp, 'MODEL'))
        # 'model' is the same folder on Windows: its own spelling comes back
        assert mf.folder_for(tmp, 'model') == os.path.join(tmp, 'MODEL')
        assert mf.folder_for(tmp, 'other') == os.path.join(tmp, 'other')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── B: prepare, bind_case, write_all, manifest, run.log ──────────────────
def case1d(**kw):
    """test_char_write_failure.case1d: a 1 m sphere, 1 cm cells."""
    return Case1D(radius_m=1.0, charge_kg=0.5, cell_size_m=0.01,
                  n_snapshots=1, t_end=3e-4, gauge_radii=[0.5], **kw)


def case2d(**kw):
    """test_char_write_failure.case2d: 0.6 x 1.2 m axisymmetric, 3 cm."""
    kw.setdefault('bcs', dict(x_lo='reflect', x_hi='transmit',
                              y_lo='reflect', y_hi='transmit'))
    kw.setdefault('t_end', 2e-4)
    kw.setdefault('record_frames', 3)
    kw.setdefault('center', (0.0, 0.6))
    return Case2D(Lx=0.6, Ly=1.2, cell_size_m=0.03, charge=0.5,
                  n_snapshots=1,
                  gauges=[(0.25, 0.6), (0.5, 0.6)], **kw)


def files_on_disk(folder):
    """{relative path: bytes} of every file but manifest.json."""
    out = {}
    for root, _dirs, files in os.walk(folder):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, folder).replace('\\', '/')
            if rel != 'manifest.json':
                out[rel] = os.path.getsize(full)
    return out


def run_into(case, runs, model='MODEL'):
    """prepare + bind_case + the run stage (stage_dir=None, on the bound
    case) + write_all, with run.log fed by GuiHooks. Returns (folder,
    manifest, bound case, logged lines)."""
    folder = mf.prepare(runs, model, confirm=lambda text: True)
    bound = mf.bind_case(case, folder)
    hooks = GuiHooks(queue.Queue(), threading.Event())
    hooks.log_file = os.path.join(folder, mf.LOG_FILE)
    _label, solve = jobs.solve_stage(case.dim, bound)
    res = solve(hooks)
    info = dict(model=model, runs_dir=runs, n_cells=123, n_procs=1)
    manifest = mf.write_all(res, bound, case.dim, folder, info,
                            log=hooks.log)
    hooks.log_file = None
    lines = []
    while not hooks.q.empty():
        msg = hooks.q.get_nowait()
        if msg[0] == 'log':
            lines.append(msg[1])
    return folder, manifest, bound, lines


def _check_folder(folder, manifest, expect, lines):
    on_disk = files_on_disk(folder)
    for rel in expect:
        if rel.endswith('/*'):
            hits = [p for p in on_disk if p.startswith(rel[:-1])]
            assert hits, f'nothing in {rel}: {sorted(on_disk)}'
            assert all(on_disk[p] > 0 for p in hits), hits
        else:
            assert on_disk.get(rel, 0) > 0, f'{rel} missing or empty: ' \
                                            f'{sorted(on_disk)}'
    assert os.path.getsize(os.path.join(folder, 'manifest.json')) > 0
    # manifest.json parses, has the sec. 2.2 keys, and lists the disk
    with open(os.path.join(folder, 'manifest.json'), encoding='utf-8') as f:
        disk_manifest = json.load(f)
    assert disk_manifest == manifest, (disk_manifest, manifest)
    assert list(manifest) == MANIFEST_KEYS, list(manifest)
    assert {o['path']: o['bytes'] for o in manifest['outputs']} == on_disk
    assert manifest['failed'] == [], manifest['failed']
    assert manifest['case_file'] == 'MODEL.json'
    assert manifest['model'] == 'MODEL' and manifest['solver'] == 'native'
    assert manifest['n_cells'] == 123 and manifest['n_procs'] == 1
    assert manifest['created'] <= manifest['finished']
    assert manifest['vtk'] is None and manifest['wsl_scratch'] is None
    assert manifest['stop_reason'], manifest['stop_reason']
    # run.log holds exactly the lines the hooks logged
    with open(os.path.join(folder, 'run.log'), encoding='utf-8',
              newline='') as f:
        text = f.read()
    assert '\r' not in text
    assert text == ''.join(f'{ln}\n' for ln in lines), (text, lines)
    assert 'Stopped:' in text


def _check_case_roundtrip(folder, bound, dim):
    path = os.path.join(folder, 'MODEL.json')
    with open(path, encoding='utf-8') as f:
        written = json.load(f)
    assert written['gauge_file'] == f'gauges/gauges_{dim}d.txt', written
    back = load_case(path)
    as_json = lambda c: json.loads(json.dumps(case_to_dict(c)))  # noqa
    assert as_json(back) == written, (as_json(back), written)
    # the same case as run, but for the folder-relative paths
    want = as_json(mf.relative_case(bound, folder))
    assert as_json(back) == want, (as_json(back), want)


def test_b_native_1d():
    runs = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    try:
        folder, manifest, bound, lines = run_into(case1d(), runs)
        assert folder == os.path.join(runs, 'MODEL')
        _check_folder(folder, manifest,
                      ['MODEL.json', 'run.log', 'gauges/gauges_1d.txt',
                       'gauges/gauges_1d_summary.csv', 'figures/*',
                       'fields/*', 'report.html', 'profile.txt'], lines)
        assert [m['name'] for m in manifest['missing']] == ['animation']
        assert manifest['missing'][0]['why'] == \
            'replay frames were not recorded'
        assert manifest['dim'] == 1
        _check_case_roundtrip(folder, bound, 1)
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_b_native_2d_axisym():
    runs = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    try:
        folder, manifest, bound, lines = run_into(case2d(), runs)
        anim = 'animation' + mf.anim_ext(None)
        _check_folder(folder, manifest,
                      ['MODEL.json', 'run.log', 'gauges/gauges_2d.txt',
                       'gauges/gauges_2d_summary.csv', 'figures/*',
                       'fields/*', 'report.html', anim, 'profile_2d.npz'],
                      lines)
        assert manifest['missing'] == [], manifest['missing']
        _check_case_roundtrip(folder, bound, 2)
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_b_missing_animation_and_planar_profile():
    runs = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    try:
        folder, manifest, _b, _l = run_into(case2d(record_frames=0), runs)
        assert not [p for p in files_on_disk(folder)
                    if p.startswith('animation')]
        assert manifest['missing'] == [
            dict(name='animation', why='replay frames were not recorded')]
        folder, manifest, _b, _l = run_into(
            case2d(geometry='planar', center=(0.3, 0.6)), runs, 'PLANAR')
        assert dict(name='profile',
                    why='3D / planar 2D has no profile export') \
            in manifest['missing'], manifest['missing']
        assert manifest['failed'] == []
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_b_bind_case_names():
    runs = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    try:
        c = case2d(anim_file='mine.gif', gauge_file='x.txt',
                   profile_file='p.npz', trigger_file='t.npz')
        b = mf.bind_case(c, runs)
        j = lambda *p: os.path.join(runs, *p)       # noqa: E731
        assert b.gauge_file == j('gauges', 'gauges_2d.txt')
        assert b.anim_file == j('animation.gif')    # the case's choice
        assert b.profile_file == j('profile_2d.npz')
        assert b.trigger_file == j('trigger_remap.npz')
        assert c.gauge_file == 'x.txt'              # the original is kept
        assert mf.bind_case(case2d(anim_file='v.mp4'), runs).anim_file \
            == j('animation.mp4')
        b1 = mf.bind_case(case1d(), runs)
        assert b1.profile_file == j('profile.txt')
        assert os.path.isdir(j('gauges'))
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def _snapshot(folder):
    out = {}
    for root, _d, files in os.walk(folder):
        for f in files:
            p = os.path.join(root, f)
            with open(p, 'rb') as fh:
                out[p] = (os.stat(p).st_mtime_ns, fh.read())
    return out


def test_b_prepare_overwrite_no_and_yes():
    runs = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    try:
        folder = mf.prepare(runs, 'MODEL', confirm=lambda t: True)
        os.makedirs(os.path.join(folder, 'gauges'))
        for rel in ('MODEL.json', 'gauges/g.txt', 'report.html'):
            with open(os.path.join(folder, rel), 'w') as f:
                f.write('old run\n')
        before = _snapshot(folder)
        asked = []
        got = mf.prepare(runs, 'model', confirm=lambda t: asked.append(t)
                         or False)
        assert got is None
        assert asked == [f"model already exists in {runs}. Overwrite? "
                         f"The previous run's files will be deleted."]
        assert _snapshot(folder) == before
        got = mf.prepare(runs, 'MODEL', confirm=lambda t: True)
        assert got == folder
        assert os.listdir(folder) == []
        assert os.listdir(runs) == ['MODEL']        # the runs folder stays
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_b_prepare_locked_file():
    if os.name != 'nt':
        return                     # an open handle blocks delete on Windows
    runs = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    try:
        folder = mf.prepare(runs, 'MODEL', confirm=lambda t: True)
        locked = os.path.join(folder, 'report.html')
        with open(locked, 'w') as held:
            held.write('open in another program\n')
            held.flush()
            try:
                mf.prepare(runs, 'MODEL', confirm=lambda t: True)
            except mf.ModelFolderError as exc:
                assert 'report.html' in str(exc), str(exc)
            else:
                raise AssertionError('a locked file did not refuse')
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_b_prepare_refusals():
    runs = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    try:
        for bad_runs, bad_model in ((runs, '..'), (runs, ''), (runs, 'C:'),
                                    ('', 'MODEL'),
                                    (os.path.join(runs, 'no'), 'MODEL')):
            try:
                mf.prepare(bad_runs, bad_model, confirm=lambda t: True)
            except mf.ModelFolderError:
                pass
            else:
                raise AssertionError((bad_runs, bad_model))
        # the target guard itself: never the runs folder, never outside
        real = mf.folder_for
        for fake in (lambda r, m: r,
                     lambda r, m: os.path.join(os.path.dirname(r), m)):
            mf.folder_for = fake
            try:
                mf.prepare(runs, 'MODEL', confirm=lambda t: True)
            except mf.ModelFolderError:
                pass
            else:
                raise AssertionError('guard did not refuse')
            finally:
                mf.folder_for = real
        assert os.path.isdir(runs) and os.listdir(runs) == []
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_b_git_commit():
    got = mf.git_commit()
    assert got is None or (len(got) == 7 and all(
        c in '0123456789abcdef' for c in got)), got
    assert mf.git_commit(tempfile.gettempdir()) is None


# ── C: the worker with a stage_dir ───────────────────────────────────────
class SnapQueue(queue.Queue):
    """A worker queue that records the folder listing at the moment each
    message is posted - to show the folder is complete BEFORE 'result'."""

    def __init__(self, folder):
        super().__init__()
        self.folder = folder
        self.seen = []

    def put(self, item, *a, **kw):
        self.seen.append((item[0], sorted(files_on_disk(self.folder))
                          if os.path.isdir(self.folder) else []))
        return super().put(item, *a, **kw)


def run_worker(case, runs, model='MODEL', **info):
    """prepare + a SolverWorker with one stage_dir stage, on this thread.
    Returns (worker, folder, [(tag, listing at post time)])."""
    from blastlab.solvers.worker import SolverWorker
    folder = mf.prepare(runs, model, confirm=lambda t: True)
    w = SolverWorker([jobs.solve_stage(case.dim, case, stage_dir=folder,
                                       run_info=dict(model=model, **info))])
    w.q = w.hooks.q = SnapQueue(folder)
    w.run()
    return w, folder, w.q.seen


def _manifest(folder):
    with open(os.path.join(folder, 'manifest.json'), encoding='utf-8') as f:
        return json.load(f)


def test_c_worker_folder_complete_before_result():
    runs = tempfile.mkdtemp(prefix='blastlab_mf_c_')
    try:
        w, folder, seen = run_worker(case2d(), runs, n_cells=1)
        tags = [t for t, _ls in seen]
        assert 'result' in tags and tags[-1] == 'done', tags
        assert tags.index('result') < tags.index('done')
        at_result = dict(seen)['result']
        for rel in ('MODEL.json', 'run.log', 'report.html',
                    'gauges/gauges_2d.txt', 'gauges/gauges_2d_summary.csv',
                    'profile_2d.npz'):
            assert rel in at_result, (rel, at_result)
        assert os.path.isfile(os.path.join(folder, 'manifest.json'))
        m = _manifest(folder)
        assert m['failed'] == [] and m['n_steps'] and m['n_steps'] > 0, m
        assert m['stop_reason'] == w.results[0].stop_reason
        assert w.error is None
        # the hooks are released: no later line lands in this run.log
        assert w.hooks.log_file is None
        assert w.hooks.stage_manifest == m
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_c_failed_gauge_tsv():
    runs = tempfile.mkdtemp(prefix='blastlab_mf_c_')
    real = jobs.save_gauges_2d

    def locked(obj, path, *a, **kw):
        raise PermissionError(13, 'Permission denied', str(path))
    jobs.save_gauges_2d = locked
    try:
        w, folder, _seen = run_worker(case2d(), runs)
    finally:
        jobs.save_gauges_2d = real
    try:
        assert w.error is None and w.results[0] is not None
        assert os.path.getsize(os.path.join(folder, 'report.html')) > 0
        m = _manifest(folder)
        assert [f['path'] for f in m['failed']] == ['gauges/gauges_2d.txt'], \
            m['failed']
        with open(os.path.join(folder, 'run.log'), encoding='utf-8') as f:
            log = f.read()
        assert '[warn] could not write' in log and 'gauges_2d.txt' in log
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_c_solver_raises():
    import blastlab.solvers as solvers_pkg
    runs = tempfile.mkdtemp(prefix='blastlab_mf_c_')
    real = solvers_pkg.get_solver

    def broken(case, hooks):
        hooks.log('  a line before the failure')
        raise RuntimeError('mesh exploded\nsecond line')
    solvers_pkg.get_solver = lambda dim, backend: broken
    try:
        w, folder, seen = run_worker(case2d(), runs)
    finally:
        solvers_pkg.get_solver = real
    try:
        assert w.error and 'mesh exploded' in w.error
        assert 'result' not in [t for t, _l in seen]
        for rel in ('MODEL.json', 'run.log', 'manifest.json'):
            assert os.path.getsize(os.path.join(folder, rel)) > 0, rel
        m = _manifest(folder)
        assert m['stop_reason'] == 'RuntimeError: mesh exploded', m
        assert m['failed'] == [] and m['missing'] == []
        assert [o['path'] for o in m['outputs']] == ['MODEL.json',
                                                     'run.log'], m
        with open(os.path.join(folder, 'run.log'), encoding='utf-8') as f:
            log = f.read()
        assert log == ('  a line before the failure\n'
                       '[stage ended: RuntimeError: mesh exploded]\n'), log
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_c_stopped_before_start():
    import blastlab.solvers as solvers_pkg
    from blastlab.solvers.hooks import StoppedBeforeStart
    runs = tempfile.mkdtemp(prefix='blastlab_mf_c_')
    real = solvers_pkg.get_solver

    def stopped(case, hooks):
        raise StoppedBeforeStart('stopped before start (meshing)')
    solvers_pkg.get_solver = lambda dim, backend: stopped
    try:
        w, folder, seen = run_worker(case1d(), runs)
    finally:
        solvers_pkg.get_solver = real
    try:
        assert w.error is None                     # not a failure
        m = _manifest(folder)
        assert m['stop_reason'] == 'stopped before start (meshing)'
        assert os.path.isfile(os.path.join(folder, 'MODEL.json'))
        assert os.path.isfile(os.path.join(folder, 'run.log'))
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_c_handoff_failure_keeps_rows():
    runs = tempfile.mkdtemp(prefix='blastlab_mf_c_')
    real = jobs.save_profile

    def locked(obj, path, *a, **kw):
        raise PermissionError(13, 'Permission denied', str(path))
    jobs.save_profile = locked
    try:
        w, folder, seen = run_worker(case1d(), runs)
    finally:
        jobs.save_profile = real
    try:
        tags = [t for t, _l in seen]
        # the worker's HandoffWriteError path: result, then error
        assert tags.index('result') < tags.index('error'), tags
        m = _manifest(folder)
        assert [f['path'] for f in m['failed']] == ['profile.txt'], m
        assert m['stop_reason'].startswith('Could not write the hand-off')
        assert os.path.getsize(os.path.join(folder, 'report.html')) > 0
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_c_no_stage_dir_is_unchanged():
    """stage_dir=None returns the plain solve (test_char_write_failure
    pins what it does); nothing is bound or logged to a file."""
    label, solve = jobs.solve_stage(1, case1d(gauge_file=None))
    assert label == '1D' and solve.__qualname__ == '_solver.<locals>.solve'
    assert jobs.solve_stage(2, case2d(solver='blastfoam'))[0] == \
        '2D blastFoam'


TESTS = [test_a_empty_and_whitespace, test_a_forbidden_chars,
         test_a_reserved_names, test_a_trailing_dot_and_space,
         test_a_length, test_a_check_messages,
         test_a_folder_for_case_insensitive,
         test_b_native_1d, test_b_native_2d_axisym,
         test_b_missing_animation_and_planar_profile,
         test_b_bind_case_names, test_b_prepare_overwrite_no_and_yes,
         test_b_prepare_locked_file, test_b_prepare_refusals,
         test_b_git_commit,
         test_c_worker_folder_complete_before_result,
         test_c_failed_gauge_tsv, test_c_solver_raises,
         test_c_stopped_before_start, test_c_handoff_failure_keeps_rows,
         test_c_no_stage_dir_is_unchanged]


if __name__ == '__main__':
    sys.exit(cc.run_main('MODEL FOLDER', TESTS))
