"""The model folder (OUT-1): services/model_folder.py.

docs/model-folder-and-vtk-plan.md section 2; batch plan
docs/batches/2026-09-26-out-1-model-folder.md, Steps 1-4.

  A  the name rule, the folder check and `folder_for` (pure)
  B  prepare / bind_case / write_all / the manifest / run.log, on a
     native 1D and a native 2D axisymmetric result (a few hundred steps)
  C  jobs.solve_stage(..., stage_dir=...) on a SolverWorker run on this
     thread: the folder is complete before ('result', 0); a failed TSV, a
     failed hand-off, a raising solver and a stop before start
  D  blastFoam: the foam\\ skeleton copy with SHA256SUMS and the scratch
     release, on a fake scratch tree with `run` / `delete` injected - no
     WSL is touched

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

#: the keys of plan sec. 2.2, in order, plus the additive `vtk` (OUT-2),
#: `wsl_fields` (OUT-3) and `failed`
MANIFEST_KEYS = ['model', 'runs_dir', 'created', 'finished', 'solver',
                 'dim', 'case_file', 'git_commit', 'stop_reason',
                 'n_cells', 'n_procs', 'n_steps', 'wsl_scratch', 'outputs',
                 'missing', 'vtk', 'wsl_fields', 'failed']


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


def test_a_desktop_as_model_folder_refused():
    """verify: a model folder that IS, or holds, a Desktop is refused -
    home as runs folder + model 'Desktop' would rmtree the thesis data on
    an overwrite. A folder inside the Desktop stays a valid runs folder."""
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_a_')
    real = mf._desktop_roots
    try:
        home = os.path.join(tmp, 'Home')
        desk = os.path.join(home, 'Desktop')
        sub = os.path.join(desk, 'runs')
        os.makedirs(sub)
        mf._desktop_roots = lambda: {mf._norm(desk)}
        for runs, model in ((home, 'Desktop'), (home, 'desktop'),
                            (tmp, 'Home')):
            got = mf.check(runs, model)
            assert len(got) == 1 and got[0].startswith('Model name: ') \
                and 'Desktop' in got[0], (runs, model, got)
            asked = []
            try:
                mf.prepare(runs, model, confirm=lambda t: asked.append(t))
            except mf.ModelFolderError:
                pass
            else:
                raise AssertionError((runs, model))
            assert asked == [], asked                # never even asked
        assert mf.check(desk, 'MODEL')[0].startswith(
            'Runs folder cannot be the Desktop')
        assert mf.check(sub, 'MODEL') == []          # a sub-folder is fine
        assert mf.check(home, 'Other') == []
        assert os.listdir(desk) == ['runs']          # nothing touched
    finally:
        mf._desktop_roots = real
        shutil.rmtree(tmp, ignore_errors=True)
    # the real machine: home + 'Desktop' refused before any dialog
    home = os.path.expanduser('~')
    if os.path.isdir(os.path.join(home, 'Desktop')):
        got = mf.check(home, 'Desktop')
        assert got and 'Desktop' in got[-1], got


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
    """{relative path: bytes} of every file but manifest.json and the
    `.blastlab-model` marker (Q4)."""
    out = {}
    for root, _dirs, files in os.walk(folder):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, folder).replace('\\', '/')
            if rel not in ('manifest.json', '.blastlab-model'):
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
        assert os.listdir(folder) == ['.blastlab-model']   # only the marker
        assert os.listdir(runs) == ['MODEL']        # the runs folder stays
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_b_marker_written_at_creation():
    """Q4: `prepare` writes `.blastlab-model` (model name + creation time)
    the moment it creates the folder."""
    runs = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    try:
        folder = mf.prepare(runs, ' MODEL ', confirm=lambda t: True)
        with open(os.path.join(folder, '.blastlab-model'),
                  encoding='utf-8') as f:
            marker = json.load(f)
        assert marker['model'] == 'MODEL' and marker['created'], marker
        assert mf.list_outputs(folder) == []        # not an output
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_b_overwrite_marker_folder_is_asked():
    """Q4 case 1: a folder holding the marker (even an aborted run's)."""
    runs = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    try:
        folder = mf.prepare(runs, 'MODEL', confirm=lambda t: True)
        with open(os.path.join(folder, 'run.log'), 'w') as f:
            f.write('aborted\n')
        asked = []
        assert mf.prepare(runs, 'MODEL', confirm=lambda t: asked.append(t)
                          or True) == folder
        assert len(asked) == 1
        assert os.listdir(folder) == ['.blastlab-model']
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_b_overwrite_empty_folder_is_asked():
    """Q4 case 2: an empty folder with no marker is asked about too."""
    runs = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    try:
        os.mkdir(os.path.join(runs, 'MODEL'))
        asked = []
        assert mf.prepare(runs, 'MODEL', confirm=lambda t: asked.append(t)
                          or False) is None
        assert len(asked) == 1 and os.listdir(os.path.join(runs, 'MODEL')) \
            == []                                   # No: untouched
        folder = mf.prepare(runs, 'MODEL', confirm=lambda t: True)
        assert os.listdir(folder) == ['.blastlab-model']
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_b_foreign_folder_refused_before_any_dialog():
    """Q4 case 3: a non-empty folder without the marker is refused before
    any question, and nothing in it is deleted."""
    runs = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    try:
        foreign = os.path.join(runs, 'Thesis')
        os.makedirs(os.path.join(foreign, 'chapter1'))
        with open(os.path.join(foreign, 'notes.txt'), 'w') as f:
            f.write('not a blastlab run\n')
        before = _snapshot(foreign)
        asked = []
        try:
            mf.prepare(runs, 'thesis', confirm=lambda t: asked.append(t)
                       or True)
        except mf.ModelFolderError as exc:
            assert str(exc) == (f'{foreign} was not created by blastlab - '
                                f'choose another model name'), str(exc)
        else:
            raise AssertionError('a foreign folder was not refused')
        assert asked == []
        assert _snapshot(foreign) == before
        assert os.path.isdir(os.path.join(foreign, 'chapter1'))
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


def test_b_log_file_never_raises():
    """verify: a line the file cannot encode (a lone surrogate) or a log
    path that cannot be opened never disturbs the run (ux(2))."""
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    try:
        hooks = GuiHooks(queue.Queue(), threading.Event())
        hooks.log_file = os.path.join(tmp, 'run.log')
        hooks.log('before')
        hooks.log('bad \udcff byte')
        hooks.log('after')
        with open(hooks.log_file, encoding='utf-8') as f:
            assert f.read() == 'before\nbad ? byte\nafter\n'
        assert hooks.q.qsize() == 3                  # the Run tab got all
        hooks.log_file = tmp                         # a folder: cannot open
        hooks.log('into a folder')
        mf._append(tmp, 'into a folder \udcff')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_b_manifest_write_failure_is_a_failed_row():
    runs = tempfile.mkdtemp(prefix='blastlab_mf_b_')
    real = mf.write_manifest
    try:
        folder = mf.prepare(runs, 'MODEL', confirm=lambda t: True)
        mf.write_manifest = lambda m, d: 'disk full'
        m = mf.write_all(None, mf.bind_case(case1d(), folder), 1, folder,
                         log=lambda s: None)
        assert dict(name='manifest', path='manifest.json',
                    why='disk full') in m['failed'], m['failed']
    finally:
        mf.write_manifest = real
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
        assert sorted(os.listdir(folder)) == ['.blastlab-model', 'MODEL.json',
                                              'manifest.json',
                                              'run.log']   # no empty dirs
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


def test_c_folder_message_before_result():
    """verify (Steps 5-11): the stage's manifest and notice travel in a
    ('folder', stage_dir, manifest, notice) message posted before the
    stage's 'result', because a chain's next stage overwrites
    hooks.stage_manifest. The result knows its model folder."""
    runs = tempfile.mkdtemp(prefix='blastlab_mf_c_')
    try:
        w, folder, seen = run_worker(case1d(), runs)
        msgs = []
        while not w.q.empty():
            msgs.append(w.q.get_nowait())
        tags = [m[0] for m in msgs]
        assert tags.index('folder') < tags.index('result'), tags
        folder_msg = msgs[tags.index('folder')]
        assert folder_msg[1] == folder and folder_msg[3] is None
        assert folder_msg[2] == _manifest(folder)
        res = w.results[0]
        assert res.meta['model_dir'] == folder
        assert res.meta['scratch_released'] is False
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_c_resume_stage_writes_the_folder():
    """verify (Steps 5-11): a resume with a model folder is a run stage -
    the jobs files, every row, and the scratch release. stage_dir=None
    stays the bare resume that writes nothing."""
    import blastlab.solvers as solvers_pkg
    from blastlab.solvers.foam import backend
    from blastlab.solvers.worker import SolverWorker
    runs = tempfile.mkdtemp(prefix='blastlab_mf_c_')
    real_resume, real_release = backend.resume_run, \
        mf.verify_and_release_scratch
    calls = []

    def fake_resume(path, hooks):
        calls.append(('resume', path))
        hooks.scratch_posix = POSIX
        return solvers_pkg.get_solver(2, 'native')(case2d(), hooks)

    def recorder(manifest, stage_dir, posix, errored, stopped_early,
                 log=print, **kw):
        calls.append(('release', posix, errored, stopped_early))
        return manifest, None
    backend.resume_run = fake_resume
    mf.verify_and_release_scratch = recorder
    try:
        label, bare = jobs.resume_stage(2, POSIX)
        assert label == 'Resume 2D (blastfoam)'
        assert bare.__qualname__.endswith('resume')
        folder = mf.prepare(runs, 'RESUMED', confirm=lambda t: True)
        w = SolverWorker([jobs.resume_stage(
            2, POSIX, case2d(solver='blastfoam'), stage_dir=folder,
            run_info=dict(model='RESUMED'))])
        w.run()
        assert w.error is None, w.error
        assert calls == [('resume', POSIX),
                         ('release', POSIX, False, False)], calls
        on_disk = files_on_disk(folder)
        for rel in ('MODEL.json', 'run.log', 'report.html',
                    'gauges/gauges_2d.txt', 'profile_2d.npz'):
            assert on_disk.get(rel, 0) > 0, (rel, sorted(on_disk))
        m = _manifest(folder)
        assert m['solver'] == 'blastfoam' and m['failed'] == [], m
    finally:
        backend.resume_run = real_resume
        mf.verify_and_release_scratch = real_release
        shutil.rmtree(runs, ignore_errors=True)


def test_c_run_info_and_layout():
    from types import SimpleNamespace
    t = mf.Target(runs_dir='R', model='M', folder=os.path.join('R', 'M'))
    assert mf.stage_dirs(t, [2]) == [t.folder]
    assert mf.stage_dirs(t, [1, 2, 3]) == [os.path.join(t.folder, d)
                                           for d in ('1d', '2d', '3d')]
    rep = SimpleNamespace(n_cells=864000,
                          run_plan=SimpleNamespace(ranks=13))
    info = mf.run_info(t, case2d(solver='blastfoam'), rep)
    assert info == dict(model='M', runs_dir='R', model_dir=t.folder,
                        n_cells=864000, n_procs=13), info
    assert mf.run_info(t, case2d(), rep)['n_procs'] == 1
    assert mf.run_info(t, case1d(solver='blastfoam'), rep)['n_procs'] == 1
    assert 'n_cells' not in mf.run_info(t)
    h = mf.handoff_paths(t, [1, 2, 3])
    assert h == {(1, 2): os.path.join(t.folder, 'handoff_1d_to_2d.txt'),
                 (2, 3): os.path.join(t.folder, 'handoff_2d_to_3d.npz')}
    # GUI-8 (plan sec. 8.3): the 1D -> 3D route's hand-off, a .txt
    # because the source is 1D
    h13 = mf.handoff_paths(t, [1, 3])
    assert h13 == {(1, 3): os.path.join(t.folder, 'handoff_1d_to_3d.txt')}


def test_c_unfinished_stage_says_so():
    """A stage whose run never ends (the window closed mid-run: the worker
    is a daemon thread) already has MODEL.json and a manifest saying it
    did not finish, written before the solver started; the end of the
    stage replaces the provisional manifest (OUT-1 verifier, item 3a)."""
    import blastlab.solvers as solvers_pkg
    runs = tempfile.mkdtemp(prefix='blastlab_mf_c_')
    real = solvers_pkg.get_solver
    during = {}

    def peek(case, hooks):
        folder = os.path.dirname(os.path.dirname(case.gauge_file))
        during['files'] = sorted(files_on_disk(folder))
        during['manifest'] = _manifest(folder)
        raise RuntimeError('peeked')
    solvers_pkg.get_solver = lambda dim, backend: peek
    try:
        _w, folder, _seen = run_worker(case2d(), runs)
    finally:
        solvers_pkg.get_solver = real
    try:
        assert 'MODEL.json' in during['files'], during['files']
        m = during['manifest']
        assert m['stop_reason'] == mf.UNFINISHED and m['finished'] is None, m
        assert m['model'] == 'MODEL' and m['dim'] == 2, m
        assert _manifest(folder)['stop_reason'] == 'RuntimeError: peeked'
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_c_no_stage_dir_is_unchanged():
    """stage_dir=None returns the plain solve (test_char_write_failure
    pins what it does); nothing is bound or logged to a file."""
    label, solve = jobs.solve_stage(1, case1d(gauge_file=None))
    assert label == '1D' and solve.__qualname__ == '_solver.<locals>.solve'
    assert jobs.solve_stage(2, case2d(solver='blastfoam'))[0] == \
        '2D blastFoam'


# ── D: blastFoam foam\ skeleton and scratch release, no WSL ──────────────
POSIX = '/root/blastlab_runs/20260926-120000_3d_p1234-00'

#: the fake scratch: skeleton files, and what must never be copied
SKELETON = {
    'system/controlDict': b'FoamFile {}\nendTime 0.001;\n',
    'system/fvSchemes': b'ddtSchemes { default Euler; }\n',
    'constant/polyMesh/points': b'(0 0 0)\n(1 0 0)\n' * 50,
    'constant/phaseProperties': b'phases (tnt air);\n',
    '0/p': b'internalField uniform 101298;\n',
    '0/U': b'internalField uniform (0 0 0);\n',
    'postProcessing/probes/0/p': b'# Time p\n0 101298\n',
    'log.blastFoam': b'Time = 1e-06\nExecutionTime = 0.1 s\n',
    'log.blockMesh': b'End\n',
}
NEVER = {
    'processor0/0/p': b'decomposed\n',
    'processor0/constant/polyMesh/points': b'decomposed mesh\n',
    '0.001/p': b'a written time\n',
    '0.001/U': b'a written time\n',
    'case.json': b'{}\n',
}


def make_scratch(tmp):
    root = os.path.join(tmp, 'scratch')
    for rel, data in {**SKELETON, **NEVER}.items():
        path = os.path.join(root, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
    return root


class FakeWsl:
    """The injected `run`: hashes the fake scratch the way the WSL script
    does, and adds stray lines for processor0/ and 0.001/ so the filter
    on the Windows side is what keeps them out. `flip` changes one byte
    of a file AFTER hashing; `extra` lists a file that does not exist
    (a partial copy); `code` is the exit status."""

    def __init__(self, root, flip=None, extra=None, code=0, extra_line=None):
        self.root, self.flip, self.extra, self.code = root, flip, extra, code
        self.extra_line = extra_line          # a raw line, added as is
        self.calls = []

    def __call__(self, argv, **kw):
        import hashlib
        from types import SimpleNamespace
        self.calls.append(argv)
        script = argv[-1]
        assert argv[:3] == ['wsl.exe', '-d', 'Ubuntu'], argv
        assert 'source ' not in script          # wsl_plain_argv, no env
        assert script == mf.skeleton_script(POSIX), script
        if self.code:
            return SimpleNamespace(returncode=self.code, stdout='',
                                   stderr='sha256sum: boom\n')
        lines = []
        for rel in sorted({**SKELETON, **NEVER}):
            with open(os.path.join(self.root, *rel.split('/')), 'rb') as f:
                lines.append(f'{hashlib.sha256(f.read()).hexdigest()}  {rel}')
        if self.extra:
            lines.append('0' * 64 + '  ' + self.extra)
        if self.extra_line:
            lines.append(self.extra_line)
        with open(os.path.join(self.root, 'SHA256SUMS'), 'w',
                  newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        if self.flip:
            path = os.path.join(self.root, *self.flip.split('/'))
            with open(path, 'r+b') as f:
                b = f.read(1)
                f.seek(0)
                f.write(bytes([b[0] ^ 0xFF]))
        return SimpleNamespace(returncode=0, stdout='', stderr='')


class FakeDelete:
    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    def __call__(self, dirs):
        self.calls.append(list(dirs))
        return self.ok


def release(tmp, errored=False, stopped=False, failed=None, posix=POSIX,
            keep_all=False, **fake):
    """verify_and_release_scratch on a fake scratch and a model folder
    holding one finished row. Returns (manifest, notice, run, delete,
    folder, log lines)."""
    root = make_scratch(tmp)
    folder = os.path.join(tmp, 'MODEL')
    os.makedirs(folder)
    with open(os.path.join(folder, 'report.html'), 'w') as f:
        f.write('<html></html>\n')
    manifest = dict(model='MODEL', failed=list(failed or []), outputs=[],
                    wsl_scratch=None)
    run, delete, lines = FakeWsl(root, **fake), FakeDelete(), []
    manifest, notice = mf.verify_and_release_scratch(
        manifest, folder, posix, errored, stopped, log=lines.append,
        run=run, delete=delete, unc=lambda p: root, keep_all=keep_all)
    return manifest, notice, run, delete, folder, lines


def test_d_clean_run_releases_once():
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    try:
        m, notice, run, delete, folder, _l = release(tmp)
        assert delete.calls == [[POSIX]], delete.calls
        assert notice is None
        assert m['wsl_scratch']['deleted'] is True
        assert m['wsl_scratch']['posix'] == POSIX
        assert m['wsl_scratch']['deleted_at']
        assert m['failed'] == []
        copied = files_on_disk(os.path.join(folder, 'foam'))
        assert sorted(copied) == sorted(list(SKELETON) + ['SHA256SUMS'])
        for rel, data in SKELETON.items():
            with open(os.path.join(folder, 'foam', *rel.split('/')),
                      'rb') as f:
                assert f.read() == data, rel
        # processor0/ and 0.001/ (and anything else) never copied
        assert not [p for p in copied if p.startswith(('processor', '0.0',
                                                       'case.json'))]
        paths = [o['path'] for o in m['outputs']]
        assert 'foam/system/controlDict' in paths and 'report.html' in paths
        with open(os.path.join(folder, 'manifest.json'),
                  encoding='utf-8') as f:
            assert json.load(f) == m
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_d_flipped_byte_keeps_scratch():
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    try:
        m, notice, _r, delete, _f, lines = release(
            tmp, flip='system/controlDict')
        assert delete.calls == []
        assert m['wsl_scratch']['deleted'] is False
        assert 'system/controlDict' in notice, notice
        assert 'system/controlDict' in m['wsl_scratch']['kept_because']
        assert dict(name='foam', path='foam/system/controlDict',
                    why='hash mismatch') in m['failed']
        assert any('kept' in ln and POSIX in ln for ln in lines), lines
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_d_partial_copy_keeps_scratch():
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    try:
        m, notice, _r, delete, _f, _l = release(
            tmp, extra='postProcessing/probes/0/U')
        assert delete.calls == [] and not m['wsl_scratch']['deleted']
        assert 'postProcessing/probes/0/U' in notice, notice
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_d_unreadable_sums_line_keeps_scratch():
    """verify: sha256sum escapes a name with a backslash or newline as
    `\\<hex>  <name>`; such a line is a file that is not copied, so the
    copy is incomplete and the scratch stays."""
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    try:
        m, notice, _r, delete, _f, _l = release(
            tmp, extra_line='\\' + 'a' * 64 + '  system/odd\\\\name')
        assert delete.calls == [] and not m['wsl_scratch']['deleted']
        assert 'not understood' in notice, notice
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_d_wsl_hash_failure_keeps_scratch():
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    try:
        m, notice, _r, delete, _f, _l = release(tmp, code=1)
        assert delete.calls == [] and not m['wsl_scratch']['deleted']
        assert 'hashing in WSL failed' in notice, notice
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_d_stopped_keeps_scratch():
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    try:
        m, notice, run, delete, folder, lines = release(tmp, stopped=True)
        assert delete.calls == [] and not m['wsl_scratch']['deleted']
        assert notice is None                     # the user stopped it
        assert len(run.calls) == 1                # but foam\ is copied
        assert os.path.isfile(os.path.join(folder, 'foam', 'SHA256SUMS'))
        assert m['wsl_scratch']['kept_because'] == \
            'the run ended before its end time'
        assert any('[note]' in ln for ln in lines), lines
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_d_raised_keeps_scratch():
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    try:
        m, notice, run, delete, folder, _l = release(tmp, errored=True)
        assert delete.calls == [] and run.calls == []
        assert not m['wsl_scratch']['deleted'] and notice is None
        assert not os.path.exists(os.path.join(folder, 'foam'))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_d_failed_row_keeps_scratch():
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    try:
        row = dict(name='report', path='report.html', why='empty file')
        m, notice, _r, delete, _f, _l = release(tmp, failed=[row])
        assert delete.calls == [] and not m['wsl_scratch']['deleted']
        assert 'report.html' in notice, notice
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_d_only_run_dirs_are_deleted():
    for bad in ('/root/blastlab_runs', '/root/blastlab_runs/',
                '/root/blastlab_runs/a/b', '/root/other/run',
                '/root/blastlab_runs/..', '/', ''):
        assert not mf.is_run_dir(bad), bad
    assert mf.is_run_dir(POSIX)
    # a finished, verified run outside the runs root is still kept (the
    # fake WSL pins its script to POSIX, so the script is pinned too)
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    real = mf.skeleton_script
    try:
        mf.skeleton_script = lambda p: real(POSIX)
        m, notice, _r, delete, _f, _l = release(tmp, posix='/root/x')
        assert delete.calls == [] and not m['wsl_scratch']['deleted']
        assert 'not a run directory' in notice, notice
    finally:
        mf.skeleton_script = real
        shutil.rmtree(tmp, ignore_errors=True)


def test_d_release_decision_table():
    import itertools
    for errored, stopped, rows_ok, hashes_ok in itertools.product(
            (False, True), repeat=4):
        ok, why = mf.release_decision(
            errored, stopped, dict(rows_ok=rows_ok, hashes_ok=hashes_ok,
                                   rows_detail='report.html',
                                   hash_detail='hash mismatch: 0/p'))
        want = not errored and not stopped and rows_ok and hashes_ok
        assert ok is want, (errored, stopped, rows_ok, hashes_ok, ok, why)
        if errored:
            assert why == 'the run did not finish (it raised)'
        elif stopped:
            assert why == 'the run ended before its end time'
        elif not rows_ok:
            assert why.endswith('report.html'), why
        elif not hashes_ok:
            assert why.endswith('0/p'), why


def test_d_skeleton_filter_and_script():
    s = mf.skeleton_script(POSIX)
    assert s.startswith(f"cd '{POSIX}' && find system constant 0 "
                        'postProcessing log.* -type f'), s
    assert 'sha256sum > SHA256SUMS' in s and 'processor' not in s
    for rel in SKELETON:
        assert mf.in_skeleton(rel), rel
    for rel in list(NEVER) + ['../etc/passwd', '/etc/passwd', 'system/../x',
                              'logs/x', '']:
        assert not mf.in_skeleton(rel), rel


def test_d_stage_calls_release_for_foam():
    """stage_solve: a blastFoam stage whose backend set scratch_posix goes
    through verify_and_release_scratch with the run's own facts."""
    import blastlab.solvers as solvers_pkg
    from blastlab.solvers.worker import SolverWorker
    runs = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    real_solver, real_release = solvers_pkg.get_solver, \
        mf.verify_and_release_scratch
    calls = []

    def foam_like(case, hooks):
        hooks.scratch_posix = POSIX              # as backend._preflight
        return real_solver(case.dim, 'native')(case, hooks)

    def recorder(manifest, stage_dir, posix, errored, stopped_early,
                 log=print, **kw):
        calls.append((posix, errored, stopped_early))
        return manifest, 'kept for a test'
    solvers_pkg.get_solver = lambda dim, backend: foam_like
    mf.verify_and_release_scratch = recorder
    try:
        folder = mf.prepare(runs, 'FOAM', confirm=lambda t: True)
        w = SolverWorker([jobs.solve_stage(2, case2d(solver='blastfoam'),
                                           stage_dir=folder)])
        w.run()
        assert calls == [(POSIX, False, False)], calls
        assert w.hooks.folder_notice == 'kept for a test'
        # a native stage on the same hooks never releases anything
        calls.clear()
        folder = mf.prepare(runs, 'NATIVE', confirm=lambda t: True)
        solvers_pkg.get_solver = real_solver
        w2 = SolverWorker([jobs.solve_stage(2, case2d(), stage_dir=folder)])
        w2.hooks.scratch_posix = POSIX
        w2.run()
        assert calls == [] and w2.hooks.folder_notice is None
    finally:
        solvers_pkg.get_solver = real_solver
        mf.verify_and_release_scratch = real_release
        shutil.rmtree(runs, ignore_errors=True)


def test_d_vtk_not_converted_keeps_scratch():
    """OUT-2 (Q4): a time the VTK export could not convert is a failed
    row of the root manifest, so the scratch that still holds it stays."""
    from blastlab.output import vtk_series
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    try:
        root = make_scratch(tmp)
        folder = os.path.join(tmp, 'MODEL')
        os.makedirs(folder)
        vtk_series.write_vtk_manifest(os.path.join(folder, 'vtk'), dict(
            families={'volumes': dict(count=1, times=['0.0005'],
                                      series=[])},
            not_converted=[dict(time='0.001', family='volumes',
                                why='foamToVTK: exit 1',
                                path='vtk/volumes/t_0.001.vtk')]))
        m = mf.write_all(None, case1d(solver='blastfoam'), 1, folder,
                         log=lambda *_a: None)
        # P4: plus files / bytes under vtk\ (here the manifest alone)
        size = os.path.getsize(os.path.join(folder, 'vtk', 'manifest.json'))
        assert m['vtk'] == dict(dir='vtk', counts={'volumes': 1}, files=1,
                                bytes=size, not_converted=[dict(
                                    time='0.001', family='volumes',
                                    why='foamToVTK: exit 1',
                                    path='vtk/volumes/t_0.001.vtk')])
        assert dict(name='vtk', path='vtk/volumes/t_0.001.vtk',
                    why='t = 0.001: foamToVTK: exit 1') in m['failed']
        delete = FakeDelete()
        m, notice = mf.verify_and_release_scratch(
            m, folder, POSIX, False, False, log=lambda *_a: None,
            run=FakeWsl(root), delete=delete, unc=lambda p: root)
        assert delete.calls == [] and not m['wsl_scratch']['deleted']
        assert 'vtk/volumes/t_0.001.vtk' in notice, notice
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_d_skeleton_omits_vtk_surfaces():
    """OUT-2 (D11): the VTK surface output under postProcessing/ is the
    export's, never part of foam\\ - pruned from the WSL listing and
    refused by the filter; the names are the writer's own."""
    from blastlab.solvers.foam import writer
    assert mf.VTK_POST_DIRS == (f'postProcessing/{writer.VTK_SECTIONS}',
                                f'postProcessing/{writer.VTK_OBSTACLES}')
    s = mf.skeleton_script(POSIX)
    for d in mf.VTK_POST_DIRS:
        assert f"-not -path '{d}/*'" in s, s
    for rel in ('postProcessing/vtkSections/0.001/p_slice_y_0.30.vtk',
                'postProcessing/vtkSections/p_slice_y_0.30.vtk.series',
                'postProcessing/vtkObstacles/0/p_obstacles.vtk'):
        assert not mf.in_skeleton(rel), rel
    assert mf.in_skeleton('postProcessing/probes/0/p')
    assert mf.in_skeleton('postProcessing/vtkSectionsOther/x')
    # a stray line in the listing is filtered on the Windows side too
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    try:
        m, notice, _r, delete, folder, _l = release(
            tmp, extra_line='0' * 64 + '  postProcessing/vtkSections/'
                                       '0.001/p_slice_y_0.30.vtk')
        assert notice is None and m['wsl_scratch']['deleted'], notice
        assert not os.path.exists(os.path.join(folder, 'foam',
                                               'postProcessing',
                                               'vtkSections'))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_d_stage_sets_vtk_dir():
    """OUT-2 (D12): a blastFoam stage with a VTK family runs with
    hooks.vtk_dir = <stage>\\vtk, restored afterwards; without a family,
    or native, it stays None."""
    import blastlab.solvers as solvers_pkg
    from blastlab.solvers.worker import SolverWorker
    runs = tempfile.mkdtemp(prefix='blastlab_mf_d_')
    real_solver, real_release = solvers_pkg.get_solver, \
        mf.verify_and_release_scratch
    seen = []

    def foam_like(case, hooks):
        seen.append(hooks.vtk_dir)
        return real_solver(case.dim, 'native')(case, hooks)
    solvers_pkg.get_solver = lambda dim, backend: foam_like
    mf.verify_and_release_scratch = lambda m, *a, **k: (m, None)
    vol = dict(on=True, mode='time', value=0.00005, fields=['p'])   # [s]
    try:
        folder = mf.prepare(runs, 'VTK', confirm=lambda t: True)
        w = SolverWorker([jobs.solve_stage(
            2, case2d(solver='blastfoam', vtk_volumes=vol),
            stage_dir=folder)])
        w.run()
        assert seen == [os.path.join(folder, 'vtk')], seen
        assert w.hooks.vtk_dir is None
        seen.clear()
        folder = mf.prepare(runs, 'NOVTK', confirm=lambda t: True)
        w = SolverWorker([jobs.solve_stage(
            2, case2d(solver='blastfoam',
                      vtk_volumes=dict(vol, on=False)), stage_dir=folder)])
        w.run()
        assert seen == [None], seen
    finally:
        solvers_pkg.get_solver = real_solver
        mf.verify_and_release_scratch = real_release
        shutil.rmtree(runs, ignore_errors=True)


def test_e_stage_sets_purge_fields():
    """OUT-3 (E4): a blastFoam stage runs with hooks.purge_fields (no VTK
    family needed), a ticked box gives keep_all_fields instead, a native
    stage gets neither; all three are restored afterwards."""
    import blastlab.solvers as solvers_pkg
    from blastlab.solvers.worker import SolverWorker
    runs = tempfile.mkdtemp(prefix='blastlab_mf_e_')
    real_solver, real_release = solvers_pkg.get_solver, \
        mf.verify_and_release_scratch
    seen = []

    def foam_like(case, hooks):
        seen.append((hooks.purge_fields, hooks.keep_all_fields,
                     hooks.fields_deleted))
        return real_solver(case.dim, 'native')(case, hooks)
    solvers_pkg.get_solver = lambda dim, backend: foam_like
    mf.verify_and_release_scratch = lambda m, *a, **k: (m, None)
    try:
        for name, case, want in (
                ('DEF', case2d(solver='blastfoam'), (True, False, set())),
                ('KEEP', case2d(solver='blastfoam', keep_all_fields=True),
                 (False, True, set())),
                ('NAT', case2d(), (False, False, set()))):
            seen.clear()
            folder = mf.prepare(runs, name, confirm=lambda t: True)
            w = SolverWorker([jobs.solve_stage(2, case, stage_dir=folder)])
            w.run()
            assert seen == [want], (name, seen)
            assert (w.hooks.purge_fields, w.hooks.keep_all_fields,
                    w.hooks.fields_deleted) == (False, False, None), name
            mode = _manifest(folder)['wsl_fields']
            assert (mode or {}).get('mode') == dict(
                DEF='newest', KEEP='keep_all', NAT=None)[name], (name, mode)
    finally:
        solvers_pkg.get_solver = real_solver
        mf.verify_and_release_scratch = real_release
        shutil.rmtree(runs, ignore_errors=True)


def test_e_wsl_fields_record():
    """OUT-3 (E7): the root manifest's `wsl_fields` for each mode."""
    rec = mf.wsl_fields_record
    assert rec(False, False, 2, {'0.1'}) is None               # native
    assert rec(True, False, 1, set()) == dict(mode='off', deleted=0,
                                              first=None, last=None)
    assert rec(True, True, 3, set()) == dict(mode='keep_all', deleted=0,
                                             first=None, last=None)
    assert rec(True, False, 2, {'0.0002', '1e-05', '0.0001'}) == dict(
        mode='newest', deleted=3, first='1e-05', last='0.0002')
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_e_')
    try:
        folder = os.path.join(tmp, 'MODEL')
        os.makedirs(folder)
        want = rec(True, False, 2, {'0.0001'})
        m = mf.write_all(None, case2d(solver='blastfoam'), 2, folder,
                         dict(wsl_fields=want), log=lambda *_a: None)
        assert m['wsl_fields'] == want
        with open(os.path.join(folder, 'manifest.json'),
                  encoding='utf-8') as f:
            assert json.load(f)['wsl_fields'] == want
        m = mf.write_all(None, case2d(), 2, folder, log=lambda *_a: None)
        assert m['wsl_fields'] is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_e_keep_all_keeps_the_scratch():
    """OUT-3 (E5): a finished run with the box ticked keeps its scratch,
    says why, and the default is released as before."""
    assert mf.release_decision(False, False, dict(rows_ok=True,
                                                  hashes_ok=True),
                               keep_all=True) == (False, mf.KEEP_ALL_WHY)
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_e_')
    try:
        m, notice, _r, delete, _f, lines = release(tmp, keep_all=True)
        assert delete.calls == [] and m['wsl_scratch']['deleted'] is False
        assert m['wsl_scratch']['kept_because'] == mf.KEEP_ALL_WHY
        assert mf.KEEP_ALL_WHY in notice, notice
        assert any('[note] WSL scratch kept' in ln for ln in lines), lines
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_e_')
    try:
        m, notice, _r, delete, _f, _l = release(tmp)
        assert delete.calls == [[POSIX]] and notice is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


TESTS = [test_a_empty_and_whitespace, test_a_forbidden_chars,
         test_a_reserved_names, test_a_trailing_dot_and_space,
         test_a_length, test_a_check_messages,
         test_a_desktop_as_model_folder_refused,
         test_a_folder_for_case_insensitive,
         test_b_native_1d, test_b_native_2d_axisym,
         test_b_missing_animation_and_planar_profile,
         test_b_bind_case_names, test_b_prepare_overwrite_no_and_yes,
         test_b_marker_written_at_creation,
         test_b_overwrite_marker_folder_is_asked,
         test_b_overwrite_empty_folder_is_asked,
         test_b_foreign_folder_refused_before_any_dialog,
         test_b_prepare_locked_file, test_b_prepare_refusals,
         test_b_log_file_never_raises,
         test_b_manifest_write_failure_is_a_failed_row,
         test_b_git_commit,
         test_c_worker_folder_complete_before_result,
         test_c_failed_gauge_tsv, test_c_solver_raises,
         test_c_stopped_before_start, test_c_handoff_failure_keeps_rows,
         test_c_folder_message_before_result,
         test_c_resume_stage_writes_the_folder, test_c_run_info_and_layout,
         test_c_unfinished_stage_says_so,
         test_c_no_stage_dir_is_unchanged,
         test_d_clean_run_releases_once, test_d_flipped_byte_keeps_scratch,
         test_d_partial_copy_keeps_scratch,
         test_d_unreadable_sums_line_keeps_scratch,
         test_d_wsl_hash_failure_keeps_scratch,
         test_d_stopped_keeps_scratch, test_d_raised_keeps_scratch,
         test_d_failed_row_keeps_scratch, test_d_only_run_dirs_are_deleted,
         test_d_release_decision_table, test_d_skeleton_filter_and_script,
         test_d_stage_calls_release_for_foam,
         test_d_vtk_not_converted_keeps_scratch,
         test_d_skeleton_omits_vtk_surfaces, test_d_stage_sets_vtk_dir,
         test_e_stage_sets_purge_fields, test_e_wsl_fields_record,
         test_e_keep_all_keeps_the_scratch]


if __name__ == '__main__':
    sys.exit(cc.run_main('MODEL FOLDER', TESTS))
