"""OUT-2: output/vtk_series.py - the `.vtk.series` index and the vtk\\
manifest (no WSL, no GUI).

docs/batches/2026-09-27-out-2-vtk-output.md, Step 5 (V4).

  * a series round-trips through json.load in ParaView's layout;
  * entries are ordered by time as a float (1e-05 before 0.0001);
  * a rewrite after one more time keeps the earlier entries;
  * UTF-8, no BOM, LF only;
  * an interrupted write leaves the old file whole and no temp file;
  * the vtk\\ manifest keeps its key order and round-trips; the model
    folder's `vtk` summary comes from it, and write_all puts it in the
    root manifest (None without an export, as test_model_folder pins).

Run:  cd blastlab/tests && python test_vtk_series.py   (or pytest)
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.output import vtk_series as vs                    # noqa: E402


def _tmp():
    return tempfile.mkdtemp(prefix='blastlab_vtk_series_')


def _raw(path):
    with open(path, 'rb') as f:
        return f.read()


def test_round_trip():
    tmp = _tmp()
    try:
        path = vs.write_series(tmp, 'p', [('p/t_0.0005.vtk', 0.0005),
                                          {'name': 'p/t_0.001.vtk',
                                           'time': '0.001'}])
        assert path == os.path.join(tmp, 'p.vtk.series')
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        assert data == {'file-series-version': '1.0',
                        'files': [{'name': 'p/t_0.0005.vtk', 'time': 0.0005},
                                  {'name': 'p/t_0.001.vtk', 'time': 0.001}]}
        assert vs.read_series(path) == [('p/t_0.0005.vtk', 0.0005),
                                        ('p/t_0.001.vtk', 0.001)]
        # the suffix is not doubled
        assert vs.series_path(tmp, 'p.vtk.series') == path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_float_order():
    tmp = _tmp()
    try:
        path = vs.write_series(tmp, 'volumes', [
            ('t_0.0001.vtk', '0.0001'), ('t_1e-05.vtk', '1e-05'),
            ('t_0.00015.vtk', '0.00015'), ('t_2e-05.vtk', '2e-05')])
        names = [n for n, _t in vs.read_series(path)]
        assert names == ['t_1e-05.vtk', 't_2e-05.vtk', 't_0.0001.vtk',
                         't_0.00015.vtk'], names
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rewrite_keeps_earlier():
    tmp = _tmp()
    try:
        vs.write_series(tmp, 'p', [('p/t_1e-05.vtk', 1e-05)])
        vs.write_series(tmp, 'p', [('p/t_2e-05.vtk', 2e-05)])
        path = vs.write_series(tmp, 'p', [('p/t_2e-05.vtk', 2e-05),
                                          ('p/t_3e-05.vtk', 3e-05)])
        assert [n for n, _t in vs.read_series(path)] == [
            'p/t_1e-05.vtk', 'p/t_2e-05.vtk', 'p/t_3e-05.vtk']
        # merge=False writes exactly what it is given
        path = vs.write_series(tmp, 'p', [('p/t_3e-05.vtk', 3e-05)],
                               merge=False)
        assert vs.read_series(path) == [('p/t_3e-05.vtk', 3e-05)]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_no_bom_lf():
    tmp = _tmp()
    try:
        path = vs.write_series(tmp, 'alpha.expl',
                               [('alpha.expl/t_1e-05.vtk', 1e-05)])
        raw = _raw(path)
        assert not raw.startswith(b'\xef\xbb\xbf')
        assert b'\r' not in raw and raw.endswith(b'\n')
        mpath = vs.write_vtk_manifest(tmp, {'fields': {'volumes': ['p']}})
        raw = _raw(mpath)
        assert not raw.startswith(b'\xef\xbb\xbf') and b'\r' not in raw
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_interrupted_write_keeps_old():
    tmp = _tmp()
    real = vs.os.replace
    try:
        path = vs.write_series(tmp, 'p', [('p/t_1e-05.vtk', 1e-05)])
        before = _raw(path)

        def boom(src, dst):
            raise OSError('disk full')
        vs.os.replace = boom
        try:
            vs.write_series(tmp, 'p', [('p/t_2e-05.vtk', 2e-05)])
        except OSError:
            pass
        else:
            raise AssertionError('the failed write did not raise')
        vs.os.replace = real
        assert _raw(path) == before
        assert sorted(os.listdir(tmp)) == ['p.vtk.series'], os.listdir(tmp)
        # a bad entry fails before anything is written
        for bad in (('/abs/t.vtk', 1.0), ('../t.vtk', 1.0), ('c:x', 1.0),
                    ('t.vtk', 'soon')):
            try:
                vs.write_series(tmp, 'p', [bad])
            except ValueError:
                continue
            raise AssertionError(bad)
        assert _raw(path) == before
    finally:
        vs.os.replace = real
        shutil.rmtree(tmp, ignore_errors=True)


def test_vtk_manifest_and_summary():
    tmp = _tmp()
    try:
        assert vs.load_vtk_manifest(tmp) is None
        assert vs.vtk_summary(tmp) is None
        state = dict(
            replay_incomplete=True,
            families={'volumes': dict(count=2, times=['1e-05', '2e-05'],
                                      series=['volumes/volumes.vtk.series']),
                      'sections': dict(count=4, times=['1e-05'],
                                       series=['sections/s/p.vtk.series'])},
            not_converted=[dict(time='3e-05', why='foamToVTK failed')])
        vs.write_vtk_manifest(tmp, state)
        with open(os.path.join(tmp, 'manifest.json'), encoding='utf-8') as f:
            text = f.read()
        data = json.loads(text)
        assert list(data) == list(vs.MANIFEST_KEYS), list(data)
        assert data['replay_incomplete'] is True
        assert data['deleted_in_wsl'] == [] and data['fields'] == {}
        assert vs.load_vtk_manifest(tmp) == data
        # P4: numbers only - files and bytes under vtk\ (the manifest is
        # the one file here so far)
        size = os.path.getsize(os.path.join(tmp, 'manifest.json'))
        assert vs.vtk_summary(tmp) == dict(
            dir='vtk', counts={'volumes': 2, 'sections': 4}, files=1,
            bytes=size,
            not_converted=[dict(time='3e-05', why='foamToVTK failed')])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_write_all_carries_the_summary():
    """model_folder.write_all fills the root manifest's `vtk` key from
    vtk\\manifest.json, and leaves it None without one."""
    from blastlab.services import model_folder as mf
    from blastlab.models.case import Case1D
    tmp = _tmp()
    try:
        case = Case1D(solver='blastfoam')
        m = mf.write_all(None, case, 1, tmp, log=lambda *_a: None)
        assert m['vtk'] is None
        vdir = os.path.join(tmp, 'vtk')
        rels = [f'volumes/t_{t}.vtk' for t in ('0.0001', '0.0002', '0.0003')]
        for rel in rels:
            os.makedirs(os.path.join(vdir, 'volumes'), exist_ok=True)
            with open(os.path.join(vdir, *rel.split('/')), 'wb') as f:
                f.write(b'# vtk\n' * 10)
        vs.write_series(os.path.join(vdir, 'volumes'), 'volumes',
                        [(r.split('/')[1], float(r[len('volumes/t_'):-4]))
                         for r in rels])
        vs.write_vtk_manifest(vdir, dict(
            families={'volumes': dict(count=3, times=[], series=[],
                                      files=rels)}))
        m = mf.write_all(None, case, 1, tmp, log=lambda *_a: None)
        n, size = 0, 0
        for base, _d, names in os.walk(vdir):
            for name in names:
                n += 1
                size += os.path.getsize(os.path.join(base, name))
        assert m['vtk'] == dict(dir='vtk', counts={'volumes': 3}, files=5,
                                bytes=size, not_converted=[]), m['vtk']
        assert n == 5
        # P4: the root manifest's outputs leave vtk\ out; its full list
        # is vtk\manifest.json's
        paths = [o['path'] for o in m['outputs']]
        assert paths and not any(p.startswith('vtk/') for p in paths), paths
        assert vs.load_vtk_manifest(vdir)['families']['volumes']['files'] \
            == rels
        with open(os.path.join(tmp, 'manifest.json'), encoding='utf-8') as f:
            assert 'volumes/t_0.0001.vtk' not in f.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


TESTS = [test_round_trip, test_float_order, test_rewrite_keeps_earlier,
         test_no_bom_lf, test_interrupted_write_keeps_old,
         test_vtk_manifest_and_summary, test_write_all_carries_the_summary]


def main():
    fails = []
    for t in TESTS:
        try:
            t()
            print(f'  [PASS] {t.__name__}')
        except Exception as exc:                    # noqa: BLE001
            print(f'  [FAIL] {t.__name__}: {exc!r}')
            fails.append(t.__name__)
    print(f'\nVTK SERIES: {"PASS" if not fails else "FAIL"} '
          f'({len(TESTS) - len(fails)}/{len(TESTS)})')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
