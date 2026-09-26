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
TESTS = TESTS_A


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
