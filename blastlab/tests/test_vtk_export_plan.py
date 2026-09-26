"""OUT-2: the VTK export of a blastFoam run (no WSL, no GUI).

docs/batches/2026-09-27-out-2-vtk-output.md, Steps 4 and 6.

  A  (V3a) the pure pieces of solvers/foam/vtk_export.py
     * vtk_purge_plan: the full decision table - every exclusion alone
       and all of them together; a failed copy deletes nothing; the two
       newest writes, `0`, a resume's start dir and a protected name
       survive; a parallel time that is not reconstructed survives; the
       D9 AMR mesh chain;
     * time_dir_paths refuses the runs root, `..`, a nested path,
       `constant`, `-1` and `0`, and builds the root plus processor0..N-1;
       rm_scripts chunks 60 writes x 13 ranks under the command-line cap;
     * vtk_argv_script (D14), surface_sweep_plan, dest_name / series_name
       (D2, Q1) and split_surface_file.

Run:  cd blastlab/tests && python test_vtk_export_plan.py   (or pytest)
"""
import itertools
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.solvers.foam import env, runloop                  # noqa: E402
from blastlab.solvers.foam import vtk_export as vx              # noqa: E402

CASE = env.RUNS_ROOT + '/20260927-010203_3d_p1234-00'
T = ['0.0001', '0.0002', '0.0003', '0.0004', '0.0005', '0.0006']


def plan(**kw):
    """vtk_purge_plan with every gate open over T, overridable."""
    args = dict(done=T, converted=T, copied_ok=T, newest_complete=T,
                start_dir='0', reconstructed=T)
    args.update(kw)
    return vx.vtk_purge_plan(**args)


# ── A: vtk_purge_plan ────────────────────────────────────────────────────
def test_a_all_open_keeps_two_newest():
    got = plan()
    assert got == T[:-2], got
    assert got == sorted(got, key=float)


def test_a_each_exclusion_alone():
    x = '0.0002'
    rest = [t for t in T[:-2] if t != x]
    without = [t for t in T if t != x]
    cases = {
        'not ingested': dict(done=without),
        'not converted': dict(converted=without),
        'copy failed': dict(copied_ok=without),
        'start dir': dict(start_dir=x),
        'protected': dict(protected={x}),
        'not reconstructed (parallel)': dict(reconstructed=without,
                                             n_procs=4),
    }
    for why, kw in cases.items():
        got = plan(**kw)
        assert got == rest, (why, got)
    # serial ignores `reconstructed` altogether
    assert plan(reconstructed=()) == T[:-2]
    assert plan(reconstructed=(), n_procs=2) == []


def test_a_exclusions_together():
    names = ('done', 'converted', 'copied_ok', 'start', 'protected',
             'reconstructed')
    for flags in itertools.product((False, True), repeat=len(names)):
        on = dict(zip(names, flags))
        x = '0.0003'
        without = [t for t in T if t != x]
        kw = dict(n_procs=3)
        if on['done']:
            kw['done'] = without
        if on['converted']:
            kw['converted'] = without
        if on['copied_ok']:
            kw['copied_ok'] = without
        if on['start']:
            kw['start_dir'] = x
        if on['protected']:
            kw['protected'] = [x]
        if on['reconstructed']:
            kw['reconstructed'] = without
        got = plan(**kw)
        want = [t for t in T[:-2] if not (any(flags) and t == x)]
        assert got == want, (on, got)


def test_a_failed_copy_deletes_nothing():
    assert plan(copied_ok=()) == []
    assert plan(converted=()) == []
    assert plan(done=()) == []


def test_a_survivors():
    got = plan(start_dir='0.0001', protected=['0.0003'],
               done=['0'] + T, converted=['0'] + T, copied_ok=['0'] + T)
    assert got == ['0.0002', '0.0004'], got
    for keep in ('0', '0.0001', '0.0003', T[-1], T[-2]):
        assert keep not in got, keep


def test_a_needs_two_complete_writes():
    assert plan(newest_complete=['0.0006']) == []
    assert plan(newest_complete=[]) == []
    # only the ingested-and-complete floor counts: two complete older
    # writes keep everything newer than their second-newest too
    assert plan(newest_complete=['0.0003', '0.0004']) == ['0.0001', '0.0002']


def test_a_non_times_ignored():
    got = plan(done=T + ['constant', '-1', 'x'],
               converted=T + ['constant', '-1', 'x'],
               copied_ok=T + ['constant', '-1', 'x'])
    assert got == T[:-2], got


def test_a_d9_amr_mesh_chain():
    # 1, 3 and 5 hold polyMesh/; 6 is the newest
    mesh = {'0.0001', '0.0003', '0.0005'}
    # 5 is kept (two newest: 5, 6); 4 goes; 3 goes only if the next kept
    # newer one (5) is a mesh time - it is; 2 goes; 1: next kept is 5 ->
    # mesh -> goes
    assert plan(mesh_dirs=mesh, ordered=T) == ['0.0001', '0.0002',
                                               '0.0003', '0.0004']
    # protect 4 (no mesh): 3 must stay, since 4 would resolve to it; then
    # 2 goes, and 1 stays because the next kept newer time is 3 (a mesh
    # time) -> 1 goes
    got = plan(mesh_dirs=mesh, ordered=T, protected=['0.0004'])
    assert got == ['0.0001', '0.0002'], got
    # protect 2 (no mesh): 1 must stay
    got = plan(mesh_dirs=mesh, ordered=T, protected=['0.0002'])
    assert got == ['0.0003', '0.0004'], got
    # a mesh time whose next newer one on disk is not converted (kept)
    got = plan(mesh_dirs=mesh, ordered=T,
               converted=[t for t in T if t != '0.0002'])
    assert got == ['0.0003', '0.0004'], got
    # no mesh dirs: the plain rule
    assert plan(ordered=T) == T[:-2]


# ── A: time_dir_paths, rm_scripts ────────────────────────────────────────
def test_a_time_dir_paths_guards():
    for bad_case in (env.RUNS_ROOT, env.RUNS_ROOT + '/', '/root/other/run',
                     env.RUNS_ROOT + '/a/b', env.RUNS_ROOT + '/..', '/', '',
                     env.RUNS_ROOT + "/x'; rm -rf /"):
        try:
            vx.time_dir_paths(bad_case, 1, ['0.001'])
        except ValueError:
            continue
        raise AssertionError(f'accepted case {bad_case!r}')
    for bad in ('constant', '-1', '0', '../0.001', '0.001/../x', 'system',
                '', 'nan', 'inf', '0.001 /'):
        try:
            vx.time_dir_paths(CASE, 1, [bad])
        except ValueError:
            continue
        raise AssertionError(f'accepted name {bad!r}')


def test_a_time_dir_paths_layout():
    assert vx.time_dir_paths(CASE, 1, ['0.0005']) == [f'{CASE}/0.0005']
    got = vx.time_dir_paths(CASE, 3, ['0.0005', '1e-05'])
    assert got == [f'{CASE}/0.0005', f'{CASE}/processor0/0.0005',
                   f'{CASE}/processor1/0.0005', f'{CASE}/processor2/0.0005',
                   f'{CASE}/1e-05', f'{CASE}/processor0/1e-05',
                   f'{CASE}/processor1/1e-05',
                   f'{CASE}/processor2/1e-05'], got


def test_a_rm_chunking_60_by_13():
    names = [f'{0.0005 * (k + 1):.6g}' for k in range(60)]
    paths = vx.time_dir_paths(CASE, 13, names)
    assert len(paths) == 60 * 14
    scripts = runloop.rm_scripts(paths)
    assert len(scripts) > 1
    assert all(len(s) <= runloop.RM_CHUNK_CHARS for s in scripts)
    back = [p.strip("'") for s in scripts for p in s.split(' ')[3:]]
    assert back == paths


def test_a_volume_and_surface_paths():
    base = CASE.rsplit('/', 1)[1]
    assert vx.volume_file_name(CASE, '0.0005') == f'VTK/{base}_0.0005.vtk'
    assert vx.volume_file_paths(CASE, ['1e-05']) == [
        f'{CASE}/VTK/{base}_1e-05.vtk']
    assert vx.surface_dir_paths(CASE, 'vtkSections', ['0.0002']) == [
        f'{CASE}/postProcessing/vtkSections/0.0002']
    for bad_fo in ('probes', 'liveSlice', '../vtkSections', ''):
        try:
            vx.surface_dir_paths(CASE, bad_fo, ['0.0002'])
        except ValueError:
            continue
        raise AssertionError(bad_fo)


# ── A: the foamToVTK line, the sweep, the layout ─────────────────────────
def test_a_argv_script():
    s = vx.vtk_argv_script(['0.0001', '0.0002'], ['p', 'rho', 'U',
                                                   'alpha.expl'])
    assert s == ("foamToVTK -time '0.0001,0.0002' -fields "
                 "'(p rho U alpha.expl)' -poly -useTimeName "
                 "-noFunctionObjects -noFaceZones -noPointValues "
                 "-excludePatches '(\".*\")'"), s
    for bad in (([], ['p']), (['0.0001'], []), (['0'], ['p']),
                (['0.0001'], ['p; rm']), (['0.0001'], ["p'"])):
        try:
            vx.vtk_argv_script(*bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_a_surface_sweep_plan():
    listing = ['0.0003', '1e-05', '0.0001', 'p_slice_y_0.30.vtk.series',
               'pMax_obstacles.vtk.series']
    assert vx.surface_sweep_plan(listing, final=False) == ['1e-05', '0.0001']
    assert vx.surface_sweep_plan(listing, final=True) == ['1e-05', '0.0001',
                                                          '0.0003']
    assert vx.surface_sweep_plan(['0.0001'], final=False) == []
    assert vx.surface_sweep_plan([], final=True) == []


def test_a_dest_and_series_names():
    assert vx.dest_name('volumes', None, None, '0.0005') == \
        'volumes/t_0.0005.vtk'
    assert vx.dest_name('sections', 'slice_y_1.40', 'p', '1e-05') == \
        'sections/slice_y_1.40/p/t_1e-05.vtk'
    assert vx.dest_name('obstacles', 'obstacles', 'alpha.expl', '0.0005') == \
        'obstacles/alpha.expl/t_0.0005.vtk'
    assert vx.series_name('volumes', None, None) == \
        'volumes/volumes.vtk.series'
    assert vx.series_name('sections', 'slice_z_0.50', 'pMax') == \
        'sections/slice_z_0.50/pMax.vtk.series'
    assert vx.series_name('obstacles', 'obstacles', 'p') == \
        'obstacles/p.vtk.series'
    for bad in (('sections', '..', 'p', '0.1'), ('sections', 'a/b', 'p',
                                                   '0.1'),
                ('obstacles', 'o', '..', '0.1'), ('volumes', 0, 0, 'x'),
                ('other', 'o', 'p', '0.1')):
        try:
            vx.dest_name(*bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_a_split_surface_file():
    f = ['p', 'pMax', 'alpha.expl', 'overpressure']
    assert vx.split_surface_file('p_slice_y_0.30.vtk', f) == \
        ('p', 'slice_y_0.30')
    assert vx.split_surface_file('pMax_obstacles.vtk', f) == \
        ('pMax', 'obstacles')
    assert vx.split_surface_file('alpha.expl_slice_x_0.10.vtk', f) == \
        ('alpha.expl', 'slice_x_0.10')
    assert vx.split_surface_file('rho_obstacles.vtk') == ('rho', 'obstacles')
    for bad in ('p_slice.vtk.series', 'obstacles.vtk', 'p_.vtk', 'x.txt'):
        assert vx.split_surface_file(bad, f) is None, bad


TESTS_A = [test_a_all_open_keeps_two_newest, test_a_each_exclusion_alone,
           test_a_exclusions_together, test_a_failed_copy_deletes_nothing,
           test_a_survivors, test_a_needs_two_complete_writes,
           test_a_non_times_ignored, test_a_d9_amr_mesh_chain,
           test_a_time_dir_paths_guards, test_a_time_dir_paths_layout,
           test_a_rm_chunking_60_by_13, test_a_volume_and_surface_paths,
           test_a_argv_script, test_a_surface_sweep_plan,
           test_a_dest_and_series_names, test_a_split_surface_file]


# ── B: the executor on a fake scratch tree ───────────────────────────────
RUN = '20260927-010203_3d_p1234-00'
POSIX = env.RUNS_ROOT + '/' + RUN
SAMPLES = ['0', '2e-05', '6e-05', '0.00011', '0.00017']


class Tree:
    """A fake scratch (time dirs + the two surface function objects'
    output) and a model folder, in a temp dir. The injected runner,
    copy and delete work on it; nothing touches WSL."""

    def __init__(self, n_procs=1, surfaces=True, volumes=True,
                 vtk_dir=True):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix='blastlab_vtk_export_')
        self.unc = os.path.join(self.tmp, 'scratch', RUN)
        self.vtk = os.path.join(self.tmp, 'MODEL', 'vtk') if vtk_dir \
            else None
        for t in ['0'] + T:
            self.write(f'{t}/p', b'p field\n')
            for i in range(n_procs if n_procs > 1 else 0):
                self.write(f'processor{i}/{t}/p', b'rank\n')
        for fo, files in (('vtkSections', ('p_slice_y_0.30.vtk',
                                           'pMax_slice_y_0.30.vtk',
                                           'p_slice_z_0.35.vtk',
                                           'pMax_slice_z_0.35.vtk')),
                          ('vtkObstacles', ('p_obstacles.vtk',))):
            for t in SAMPLES:
                for f in files:
                    self.write(f'postProcessing/{fo}/{t}/{f}',
                               f'{fo} {t} {f}\n'.encode() * 10)
            self.write(f'postProcessing/{fo}/p_x.vtk.series', b'{}\n')
        self.spec = SimpleNamespace(
            dim=3, case_posix=POSIX, case_unc=self.unc, start_dir='0',
            n_procs=n_procs, amr=0, decomposed=False, n_cells=1000,
            vtk_volumes=(dict(on=True, mode='step', value=10,
                              fields=['p', 'rho', 'U']) if volumes
                         else None),
            vtk_surfaces=(dict(on=True, mode='time', value=0.02,
                               fields=['p', 'pMax'],
                               obstacle_fields=['p'], planes=[['z', 0.35]])
                          if surfaces else None))
        self.lines = []
        self.hooks = SimpleNamespace(vtk_dir=self.vtk, log=self.lines.append)
        self.runs, self.deletes = [], []
        self.fail_convert, self.empty_copy = set(), set()
        self.clock = itertools.count(0, 10)

    def write(self, rel, data):
        path = os.path.join(self.unc, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)

    def exists(self, rel):
        return os.path.exists(os.path.join(self.unc, *rel.split('/')))

    def runner(self, spec, names, fields):
        self.runs.append(list(names))
        tree = self

        class Job:
            def __init__(self):
                self.names = list(names)

            def poll(self):
                bad = [n for n in self.names if n in tree.fail_convert]
                for n in self.names:
                    if n not in bad:
                        tree.write(f'VTK/{RUN}_{n}.vtk', b'# vtk\n' * 100)
                return (not bad, 'boom' if bad else '')
        return Job()

    def copy(self, src, dst):
        import shutil as sh
        name = os.path.basename(dst)
        if any(name == f't_{n}.vtk' for n in self.empty_copy):
            open(dst, 'wb').close()
            return
        sh.copyfile(src, dst)

    def delete(self, paths):
        import shutil as sh
        self.deletes.append(list(paths))
        for p in paths:
            assert p.startswith(POSIX + '/'), p
            local = os.path.join(self.unc, *p[len(POSIX) + 1:].split('/'))
            if os.path.isdir(local):
                sh.rmtree(local)
            elif os.path.exists(local):
                os.remove(local)
        return True

    def export(self):
        return vx.VtkExport(self.spec, self.hooks, ('p',),
                            delete=self.delete, runner=self.runner,
                            copy=self.copy, sleep=lambda s: None,
                            clock=lambda: next(self.clock))

    def deleted_times(self):
        return [t for t in T if not self.exists(t)]

    def model(self, rel):
        return os.path.join(self.vtk, *rel.split('/'))

    def close(self):
        import shutil as sh
        sh.rmtree(self.tmp, ignore_errors=True)


def _series(path):
    import json
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _manifest(tree):
    from blastlab.output import vtk_series as vs
    return vs.load_vtk_manifest(tree.vtk)


def test_b_happy_path():
    tree = Tree()
    try:
        ex = tree.export()
        ex.run({t: 0 for t in T[:3]})          # starts a conversion
        assert tree.runs == [T[:3]] and tree.deleted_times() == []
        ex.run({t: 0 for t in T[:4]})          # polls it, copies, plans
        assert tree.deleted_times() == T[:2], tree.deleted_times()
        ex.run({t: 0 for t in T}, final=True)
        # every ingested write converted, copied, and in the series
        for t in T:
            assert os.path.getsize(tree.model(f'volumes/t_{t}.vtk')) > 0, t
        vol = _series(tree.model('volumes/volumes.vtk.series'))
        assert [f['name'] for f in vol['files']] == [f't_{t}.vtk' for t in T]
        assert vol['file-series-version'] == '1.0'
        # exactly the planned dirs: all but the two newest; 0 stays
        assert tree.deleted_times() == T[:-2], tree.deleted_times()
        assert tree.exists('0') and tree.exists(T[-1]) and tree.exists(T[-2])
        assert not os.path.isdir(os.path.join(tree.unc, 'VTK')) or not \
            os.listdir(os.path.join(tree.unc, 'VTK'))
        # the surfaces: every sample copied, one series per field and
        # plane, and the WSL sample dirs gone (blastFoam's series stays)
        for plane in ('slice_y_0.30', 'slice_z_0.35'):
            for fld in ('p', 'pMax'):
                s = _series(tree.model(f'sections/{plane}/{fld}.vtk.series'))
                assert [f['name'] for f in s['files']] == [
                    f'{fld}/t_{t}.vtk' for t in SAMPLES], s
                for t in SAMPLES:
                    assert os.path.isfile(tree.model(
                        f'sections/{plane}/{fld}/t_{t}.vtk'))
        s = _series(tree.model('obstacles/p.vtk.series'))
        assert [f['time'] for f in s['files']] == [float(t) for t in SAMPLES]
        for fo in ('vtkSections', 'vtkObstacles'):
            left = os.listdir(os.path.join(tree.unc, 'postProcessing', fo))
            assert left == ['p_x.vtk.series'], left
        m = _manifest(tree)
        assert m['families']['volumes']['count'] == len(T)
        assert m['families']['volumes']['times'] == T
        assert m['families']['sections']['count'] == 4 * len(SAMPLES)
        assert m['families']['obstacles']['count'] == len(SAMPLES)
        assert m['deleted_in_wsl'] == T[:-2]
        assert m['not_converted'] == [] and m['replay_incomplete'] is False
        assert m['cadence'] == {'volumes': dict(mode='step', value=10,
                                                unit='steps'),
                                'surfaces': dict(mode='time', value=0.02,
                                                 unit='ms')}
        assert any('VTK output (volumes, sections, obstacles)' in ln
                   for ln in tree.lines), tree.lines
        assert any('written time(s) deleted in WSL' in ln
                   for ln in tree.lines), tree.lines
    finally:
        tree.close()


def test_b_protected_and_start_dir_survive():
    tree = Tree(surfaces=False)
    try:
        tree.spec.start_dir = T[0]
        ex = tree.export()
        ex.protect(T[2])
        ex.protect(None)
        ex.run({t: 0 for t in T}, final=True)
        assert tree.deleted_times() == [T[1], T[3]], tree.deleted_times()
        ex.unprotect(T[2])
        ex.run({t: 0 for t in T}, final=True)
        assert tree.deleted_times() == [T[1], T[2], T[3]]
    finally:
        tree.close()


def test_b_converter_failure_deletes_nothing():
    tree = Tree(surfaces=False)
    try:
        tree.fail_convert = {T[1]}
        ex = tree.export()
        ex.run({t: 0 for t in T}, final=True)
        assert T[1] not in tree.deleted_times()
        assert tree.exists(T[1])
        m = _manifest(tree)
        nc = m['not_converted']
        assert [e['time'] for e in nc] == [T[1]], nc
        assert 'foamToVTK' in nc[0]['why'] and nc[0]['family'] == 'volumes'
        # the failed batch is split, then the bad write is tried twice on
        # its own and given up (one retry line, one give-up line)
        assert tree.runs[0] == T, tree.runs
        assert [r for r in tree.runs[1:] if T[1] in r] == [[T[1]], [T[1]]]
        assert all(len(r) == 1 for r in tree.runs[1:]), tree.runs
        assert sum('tried once more' in ln for ln in tree.lines) == 1
        assert sum('failed twice' in ln for ln in tree.lines) == 1
        assert not os.path.exists(tree.model(f'volumes/t_{T[1]}.vtk'))
    finally:
        tree.close()


def test_b_empty_copy_deletes_nothing():
    tree = Tree(surfaces=False)
    try:
        tree.empty_copy = {T[0]}
        ex = tree.export()
        ex.run({t: 0 for t in T}, final=True)
        ex.run({t: 0 for t in T}, final=True)
        assert T[0] not in tree.deleted_times()
        assert tree.exists(f'VTK/{RUN}_{T[0]}.vtk')   # its source kept
        assert not os.path.exists(tree.model(f'volumes/t_{T[0]}.vtk'))
        nc = _manifest(tree)['not_converted']
        assert [(e['time'], e['path']) for e in nc] == [
            (T[0], f'vtk/volumes/t_{T[0]}.vtk')], nc
        assert 'empty' in nc[0]['why'], nc
    finally:
        tree.close()


def test_b_inactive_without_vtk_dir():
    tree = Tree(vtk_dir=False)
    try:
        ex = tree.export()
        assert not ex.active
        ex.run({t: 0 for t in T})
        ex.run({t: 0 for t in T}, final=True)
        assert tree.runs == [] and tree.deletes == []
        assert tree.deleted_times() == []
        assert len(tree.lines) == 1 and 'no model folder' in tree.lines[0]
        # and nothing at all without a family
        tree2 = Tree(surfaces=False, volumes=False)
        try:
            ex2 = tree2.export()
            ex2.run({t: 0 for t in T}, final=True)
            assert not ex2.active and tree2.lines == [] and not tree2.runs
        finally:
            tree2.close()
    finally:
        tree.close()


def test_b_second_export_does_not_convert_twice():
    tree = Tree(surfaces=False)
    try:
        ex = tree.export()
        ex.run({t: 0 for t in T[:4]})
        ex.run({t: 0 for t in T[:4]})
        assert tree.runs == [T[:4]]
        # a W3 auto-resume: a new loop, the same hooks and folder
        tree.runs.clear()
        ex2 = tree.export()
        assert ex2.copied == set(T[:4]), ex2.copied
        on_disk = {t: 0 for t in T if tree.exists(t)}
        ex2.run(on_disk, final=True)
        assert tree.runs == [T[4:]], tree.runs
        vol = _series(tree.model('volumes/volumes.vtk.series'))
        assert [f['name'] for f in vol['files']] == [f't_{t}.vtk' for t in T]
        assert _manifest(tree)['families']['volumes']['count'] == len(T)
    finally:
        tree.close()


def test_b_newest_sample_waits_for_final():
    tree = Tree(volumes=False)
    try:
        ex = tree.export()
        ex.run({})
        newest = SAMPLES[-1]
        for fo in ('vtkSections', 'vtkObstacles'):
            assert tree.exists(f'postProcessing/{fo}/{newest}'), fo
            for t in SAMPLES[:-1]:
                assert not tree.exists(f'postProcessing/{fo}/{t}'), (fo, t)
        assert not os.path.exists(tree.model(f'obstacles/p/t_{newest}.vtk'))
        ex.run({}, final=True)
        for fo in ('vtkSections', 'vtkObstacles'):
            assert not tree.exists(f'postProcessing/{fo}/{newest}'), fo
        assert os.path.isfile(tree.model(f'obstacles/p/t_{newest}.vtk'))
        assert 'volumes' not in _manifest(tree)['families']
    finally:
        tree.close()


def test_b_parallel_needs_reconstruct():
    tree = Tree(surfaces=False, n_procs=2)
    try:
        ex = tree.export()
        ex.run({t: 0 for t in T}, final=True)
        assert tree.deleted_times() == []            # nothing covered yet
        ex.covered(T[:3])
        ex.run({t: 0 for t in T}, final=True)
        assert tree.deleted_times() == T[:3]
        for t in T[:3]:
            assert not tree.exists(f'processor0/{t}')
            assert not tree.exists(f'processor1/{t}')
        assert tree.exists(f'processor0/{T[3]}')
    finally:
        tree.close()


def test_b_no_delete_switch():
    tree = Tree()
    os.environ[vx.NO_DELETE_ENV] = '1'
    try:
        ex = tree.export()
        ex.run({t: 0 for t in T}, final=True)
        assert tree.deletes == [] and tree.deleted_times() == []
        assert os.path.isfile(tree.model(f'volumes/t_{T[0]}.vtk'))
        assert any(vx.NO_DELETE_ENV in ln for ln in tree.lines)
    finally:
        del os.environ[vx.NO_DELETE_ENV]
        tree.close()


def test_b_failing_delete_never_raises():
    tree = Tree(surfaces=False)
    try:
        ex = tree.export()
        ex.delete = lambda paths: (_ for _ in ()).throw(OSError('wsl gone'))
        ex.run({t: 0 for t in T}, final=True)
        ex.run({t: 0 for t in T}, final=True)
        assert tree.deleted_times() == []
        assert sum('did not go through' in ln for ln in tree.lines) == 1
        assert _manifest(tree)['deleted_in_wsl'] == []
    finally:
        tree.close()


def test_b_runloop_wiring():
    """FoamRunLoop builds the export and calls it after every ingest pass
    and on the final sweep; a loop assembled with __new__ has none."""
    loop = runloop.FoamRunLoop.__new__(runloop.FoamRunLoop)
    assert loop.vtk is None
    loop.protect('0.1')                  # no-ops without an export
    loop.unprotect('0.1')
    loop._export_vtk(final=True)
    calls = []
    loop.vtk = SimpleNamespace(
        run=lambda done, final: calls.append(('run', final)),
        covered=lambda names: calls.append(('covered', list(names))),
        protect=lambda n: calls.append(('protect', n)),
        unprotect=lambda n: calls.append(('unprotect', n)))
    loop.done = {}
    loop.purge = None
    loop._covered(['0.1'])
    loop._export_vtk(final=False)
    loop.protect('0.2')
    loop.unprotect('0.2')
    assert calls == [('covered', ['0.1']), ('run', False),
                     ('protect', '0.2'), ('unprotect', '0.2')], calls


TESTS_B = [test_b_happy_path, test_b_protected_and_start_dir_survive,
           test_b_converter_failure_deletes_nothing,
           test_b_empty_copy_deletes_nothing, test_b_inactive_without_vtk_dir,
           test_b_second_export_does_not_convert_twice,
           test_b_newest_sample_waits_for_final,
           test_b_parallel_needs_reconstruct, test_b_no_delete_switch,
           test_b_failing_delete_never_raises, test_b_runloop_wiring]
TESTS = TESTS_A + TESTS_B


def main():
    fails = []
    for t in TESTS:
        try:
            t()
            print(f'  [PASS] {t.__name__}')
        except Exception as exc:                    # noqa: BLE001
            print(f'  [FAIL] {t.__name__}: {exc!r}')
            fails.append(t.__name__)
    print(f'\nVTK EXPORT PLAN: {"PASS" if not fails else "FAIL"} '
          f'({len(TESTS) - len(fails)}/{len(TESTS)})')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
