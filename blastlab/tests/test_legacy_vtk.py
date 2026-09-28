"""OUT-2: output/legacy_vtk.py and the Viper-style file content (no WSL,
no GUI).

Owner spec docs/batches/2026-09-27-out-2-surface-layout.md, decisions 1
and 4-6:

  * a round trip: synthetic per-field files as blastFoam's vtkTimeSeries
    surface writer emits them (legacy 2.0 ASCII POLYDATA, one `FIELD
    attributes 1` array each - the layout read from a real run on
    2026-09-27) are parsed, merged into one file, renamed, given the
    TIME field, written BINARY and read back identical by the strict
    parser; pMax comes back as Peak_Overpressure = pMax - P_AIR;
  * point data stays point data (nothing is interpolated);
  * per-field files whose geometry differs are refused;
  * the strict parser refuses truncated, over-long, mis-counted and
    unknown content, and binary data is big-endian;
  * a foamToVTK-style binary UNSTRUCTURED_GRID volume is rewritten with
    readable names and TIME, cellID kept;
  * the reference: when the owner's Viper samples are present
    (docs/references/viper_vtk_sample/, not in git) their keyword
    structure is walked without loading the data, and a written file
    follows the same order (FIELD FieldData 1 / TIME 1 1 float before
    CELL_DATA, SCALARS <name> float 1 + LOOKUP_TABLE default). Skipped
    when the samples are absent.

Run:  cd blastlab/tests && python test_legacy_vtk.py   (or pytest)
"""
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                            # noqa: E402

from blastlab.core.constants import P_AIR                      # noqa: E402
from blastlab.output import legacy_vtk as lv                   # noqa: E402

VIPER = os.path.join(HERE, '..', '..', 'docs', 'references',
                     'viper_vtk_sample')


# ── synthetic sources, shared with test_vtk_export_plan ──────────────────
def _wrap(tokens, per=10):
    return [' '.join(tokens[i:i + per]) for i in range(0, len(tokens), per)]


def surface_geometry(shift=0.0, n=3):
    """An n x n quad patch in the plane z = 0.3 (+shift): (points, polys)."""
    pts = [(0.1 * i + shift, 0.1 * j, 0.3) for j in range(n + 1)
           for i in range(n + 1)]
    polys = [(j * (n + 1) + i, j * (n + 1) + i + 1,
              (j + 1) * (n + 1) + i + 1, (j + 1) * (n + 1) + i)
             for j in range(n) for i in range(n)]
    return pts, polys


def foam_surface_ascii(field, values, points, polys, point_data=False):
    """One per-field surface file as blastFoam's vtkTimeSeries writer
    writes it: legacy 2.0 ASCII POLYDATA, `FIELD attributes 1`."""
    vals = np.asarray(values, dtype=float)
    ncomp = 1 if vals.ndim == 1 else vals.shape[1]
    lines = ['# vtk DataFile Version 2.0', 'sampleSurface', 'ASCII',
             'DATASET POLYDATA', f'POINTS {len(points)} float']
    lines += _wrap([f'{v:g}' for p in points for v in p])
    size = sum(len(p) + 1 for p in polys)
    lines.append(f'POLYGONS {len(polys)} {size}')
    lines += _wrap([str(x) for p in polys for x in (len(p),) + tuple(p)])
    n = len(points) if point_data else len(polys)
    lines += [f'{"POINT_DATA" if point_data else "CELL_DATA"} {n}',
              'FIELD attributes 1', f'{field} {ncomp} {n} float']
    lines += _wrap([f'{v:g}' for v in vals.ravel()])
    return ('\n'.join(lines) + '\n').encode('ascii')


def foam_volume_binary(t=0.0005, name='case'):
    """A foamToVTK-style volume (legacy 2.0 BINARY UNSTRUCTURED_GRID, two
    hexahedra, `FIELD attributes 4`: cellID p rho U), and its arrays."""
    pts = np.array([(x, y, z) for z in (0, 1) for y in (0, 1)
                    for x in (0, 1, 2)], dtype='>f4')
    hexes = [(0, 1, 4, 3, 6, 7, 10, 9), (1, 2, 5, 4, 7, 8, 11, 10)]
    cells = np.array([v for h in hexes for v in (8,) + h], dtype='>i4')
    arrays = dict(cellID=np.array([0, 1]),
                  p=np.array([101325.0 + 1e5 * t, 2.5e5], dtype=np.float32),
                  rho=np.array([1.2, 2.4], dtype=np.float32),
                  U=np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32))
    out = [b'# vtk DataFile Version 2.0\n', name.encode(), b'\nBINARY\n',
           b'DATASET UNSTRUCTURED_GRID\n', b'POINTS 12 float\n',
           pts.tobytes(), b'\n', b'CELLS 2 18\n', cells.tobytes(), b'\n',
           b'CELL_TYPES 2\n', np.array([12, 12], '>i4').tobytes(), b'\n',
           b'CELL_DATA 2\n', b'FIELD attributes 4\n',
           b'cellID 1 2 int\n', arrays['cellID'].astype('>i4').tobytes(),
           b'\n']
    for k in ('p', 'rho', 'U'):
        nc = 1 if arrays[k].ndim == 1 else 3
        out += [f'{k} {nc} 2 float\n'.encode(),
                arrays[k].astype('>f4').tobytes(), b'\n']
    return b''.join(out), arrays


def _tmp(data, name='f.vtk'):
    d = tempfile.mkdtemp(prefix='blastlab_legacy_vtk_')
    path = os.path.join(d, name)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def _merged(point_data=False):
    """p and pMax on one quad patch, merged, renamed, t = 2e-05 s."""
    from blastlab.solvers.foam import vtk_export as vx
    pts, polys = surface_geometry()
    n = len(pts) if point_data else len(polys)
    p = 101325.0 + np.arange(n) * 1234.5
    pmax = 1.07829e+07 - np.arange(n) * 1000.0
    parts = [(f, lv.parse(foam_surface_ascii(f, v, pts, polys, point_data)))
             for f, v in (('p', p), ('pMax', pmax))]
    vd = vx.export_file(lv.merge(parts), '2e-05')
    return vd, p, pmax, pts, polys


# ── the round trip ───────────────────────────────────────────────────────
def test_round_trip_merge():
    vd, p, pmax, pts, polys = _merged()
    path = _tmp(b'')
    lv.write(path, vd)
    got = lv.verify(path, vd)
    assert got.dataset == 'POLYDATA' and got.binary and got.version == '3.0'
    assert got.n_cells == len(polys) and got.n_points == len(pts)
    assert [a.name for a in got.cell_data] == ['pressure',
                                               'Peak_Overpressure']
    assert all(a.kind == 'scalars' and a.vtk_type == 'float'
               for a in got.cell_data)
    assert got.point_data == []
    # values: float32 of the ASCII text (6 digits, as blastFoam writes);
    # Peak_Overpressure = pMax - P_AIR
    text = np.array([float(f'{v:g}') for v in p])
    assert np.array_equal(got.cell_data[0].values, text.astype(np.float32))
    pmax = np.array([float(f'{v:g}') for v in pmax])
    want = (pmax - P_AIR).astype(np.float32)
    assert np.array_equal(got.cell_data[1].values, want)
    assert abs(float(got.cell_data[1].values[0]) - (1.07829e+07 - 101325.0)) \
        < 1.0
    # the sample time inside the file, in seconds, as float
    assert [(a.name, a.vtk_type, a.ntuples) for a in got.field_data] == [
        ('TIME', 'float', 1)]
    assert float(got.field_data[0].values[0]) == np.float32(2e-05)
    # the geometry unchanged
    assert np.array_equal(got.block('POINTS').values,
                          np.array(pts, dtype=np.float32))
    conn = [x for q in polys for x in (4,) + q]
    assert got.block('POLYGONS').values.tolist() == conn


def test_point_data_stays_point_data():
    vd, p, _pmax, pts, _polys = _merged(point_data=True)
    path = _tmp(b'')
    lv.write(path, vd)
    got = lv.verify(path, vd)
    assert got.cell_data == []
    assert [a.name for a in got.point_data] == ['pressure',
                                                'Peak_Overpressure']
    assert got.point_data[0].ntuples == len(pts)


def test_vectors_and_keyword_order():
    """velocity is written as VECTORS; the keyword order is the Viper
    one: geometry, FIELD FieldData 1 / TIME 1 1 float, CELL_DATA, then
    SCALARS <name> float 1 + LOOKUP_TABLE default per array."""
    from blastlab.solvers.foam import vtk_export as vx
    pts, polys = surface_geometry(n=2)
    u = np.arange(3 * len(polys), dtype=float).reshape(-1, 3)
    parts = [('p', lv.parse(foam_surface_ascii('p', np.ones(len(polys)),
                                               pts, polys))),
             ('U', lv.parse(foam_surface_ascii('U', u, pts, polys)))]
    vd = vx.export_file(lv.merge(parts), '0.001')
    path = _tmp(b'')
    lv.write(path, vd)
    got = lv.verify(path, vd)
    assert [(a.name, a.kind) for a in got.cell_data] == [
        ('pressure', 'scalars'), ('velocity', 'vectors')]
    assert np.array_equal(got.cell_data[1].values, u.astype(np.float32))
    keys = [ln for _off, ln in lv.scan(path)]
    assert keys[0] == '# vtk DataFile Version 3.0' and keys[2] == 'BINARY'
    rest = keys[3:]
    assert rest == ['DATASET POLYDATA', f'POINTS {len(pts)} float',
                    f'POLYGONS {len(polys)} {5 * len(polys)}',
                    'FIELD FieldData 1', 'TIME 1 1 float',
                    f'CELL_DATA {len(polys)}', 'SCALARS pressure float 1',
                    'LOOKUP_TABLE default', 'VECTORS velocity float'], rest


def test_binary_is_big_endian():
    vd, *_ = _merged()
    data = lv.to_bytes(vd)
    i = data.index(b'TIME 1 1 float\n') + len(b'TIME 1 1 float\n')
    assert data[i:i + 4] == struct.pack('>f', 2e-05)
    j = data.index(b'LOOKUP_TABLE default\n') + len(b'LOOKUP_TABLE default\n')
    assert data[j:j + 4] == struct.pack('>f', 101325.0)


def test_volume_rewrite():
    from blastlab.solvers.foam import vtk_export as vx
    raw, arrays = foam_volume_binary(t=0.0005)
    src = lv.parse(raw)
    assert src.version == '2.0' and src.field_data == []   # no TIME
    vd = vx.export_file(src, '0.0005', title='blastlab volumes')
    path = _tmp(b'')
    lv.write(path, vd)
    got = lv.verify(path, vd)
    assert got.dataset == 'UNSTRUCTURED_GRID' and got.n_cells == 2
    assert [(a.name, a.kind, a.vtk_type) for a in got.cell_data] == [
        ('cellID', 'scalars', 'int'), ('pressure', 'scalars', 'float'),
        ('density', 'scalars', 'float'), ('velocity', 'vectors', 'float')]
    assert np.array_equal(got.cell_data[1].values, arrays['p'])
    assert np.array_equal(got.cell_data[3].values, arrays['U'])
    assert np.array_equal(got.block('CELL_TYPES').values, [12, 12])
    assert float(got.field_data[0].values[0]) == np.float32(0.0005)
    assert got.title == 'blastlab volumes'


def test_every_readable_name():
    """Owner decision 5: the same readable name for every field, in
    every family."""
    from blastlab.models.case import VTK_ARRAY_NAMES, VTK_FIELDS
    from blastlab.solvers.foam import vtk_export as vx
    assert set(VTK_ARRAY_NAMES) == set(VTK_FIELDS)
    assert VTK_ARRAY_NAMES == {
        'p': 'pressure', 'pMax': 'Peak_Overpressure', 'impulse': 'Impulse',
        # OUT-4b B1: owner decision Q1 (2026-09-27) renames Arrival_Time -
        # blastFoam's timeOfArrival is the time of peak (guide sec. 15.12)
        'overpressure': 'Overpressure', 'timeOfArrival': 'Time_Of_Peak',
        'rho': 'density', 'U': 'velocity', 'T': 'temperature',
        'alpha.expl': 'Products_Fraction', 'rhoE': 'Energy',
        # OUT-4a A2: a spec addition (batch plan), not a change to pass
        'dynamicP': 'Dynamic_Pressure',
        # OUT-4b B2 (owner Q2): a spec addition, not a change to pass
        'impulseMax': 'Peak_Impulse',
        # OUT-4b B3 (owner Q3): a spec addition, not a change to pass
        'obstacleID': 'Obstacle_ID'}
    arrs = [lv.Array(f, np.ones(2), 'float', 'field') for f in VTK_FIELDS]
    out = vx.readable_arrays(arrs)
    assert [a.name for a in out] == [VTK_ARRAY_NAMES[f] for f in VTK_FIELDS]
    # only pMax changes value
    for f, a in zip(VTK_FIELDS, out):
        want = 1.0 - P_AIR if f == 'pMax' else 1.0
        assert np.allclose(a.values, want), f
    try:
        vx.readable_arrays([lv.Array('p', np.ones(2)),
                            lv.Array('pressure', np.ones(2))])
    except ValueError:
        pass
    else:
        raise AssertionError('two arrays named pressure accepted')


def test_dynamic_pressure_magnitude():
    """OUT-4a (owner Q5): blastFoam's dynamicP vector 0.5 rho U |U| is
    written as its magnitude q = 0.5 rho |U|^2, one scalar
    (blastFoam User Guide v6.0, sec. 15.9, eq. 15.1)."""
    from blastlab.solvers.foam import vtk_export as vx
    rho = np.array([1.2, 2.0])
    U = np.array([[3.0, 4.0, 0.0], [0.0, -10.0, 0.0]])
    mag = np.sqrt((U * U).sum(axis=1))
    vec = 0.5 * rho[:, None] * U * mag[:, None]
    out = vx.readable_arrays([lv.Array('dynamicP', vec, 'float', 'vectors')])
    assert out[0].name == 'Dynamic_Pressure' and out[0].ncomp == 1
    assert out[0].kind == 'scalars'
    assert np.allclose(out[0].values, 0.5 * rho * mag ** 2, rtol=1e-12)


def test_peak_overpressure_at_t0():
    """Owner decision 2026-09-27: blastFoam's pMax starts at 0, so the
    running max includes the current pressure p when it is in the file,
    and is floored at 0 overpressure when it is not."""
    from blastlab.solvers.foam import vtk_export as vx
    pmax0 = np.zeros(3)
    p = np.array([P_AIR, P_AIR + 50.0, P_AIR - 10.0])
    out = vx.readable_arrays([lv.Array('pMax', pmax0), lv.Array('p', p)])
    assert np.allclose(out[0].values, [0.0, 50.0, -10.0])
    assert np.allclose(out[1].values, p)            # p itself untouched
    # later times: pMax >= p, so the value is pMax - P_AIR as before
    pmax = np.array([P_AIR + 900.0, P_AIR + 50.0, P_AIR])
    out = vx.readable_arrays([lv.Array('pMax', pmax), lv.Array('p', p)])
    assert np.allclose(out[0].values, [900.0, 50.0, 0.0])
    # no p in the file: floored at 0
    out = vx.readable_arrays([lv.Array('pMax', pmax0)])
    assert np.allclose(out[0].values, 0.0)
    out = vx.readable_arrays([lv.Array('pMax', pmax)])
    assert np.allclose(out[0].values, [900.0, 50.0, 0.0])


def test_peak_impulse_max_rule():
    """OUT-4b B2 (owner Q2): impulseMax is written as Peak_Impulse, and
    the running max includes the current impulse when it is in the file
    (the pMax addendum); without it the value is written as is - no
    floor, the net impulse may be negative."""
    from blastlab.solvers.foam import vtk_export as vx
    imax0 = np.array([0.0, 0.0, -3.0])
    imp = np.array([5.0, -2.0, -4.0])
    out = vx.readable_arrays([lv.Array('impulseMax', imax0),
                              lv.Array('impulse', imp)])
    assert [a.name for a in out] == ['Peak_Impulse', 'Impulse']
    assert np.array_equal(out[0].values, [5.0, 0.0, -3.0])
    assert np.array_equal(out[1].values, imp)       # impulse untouched
    # later: impulseMax >= impulse, the value is impulseMax itself
    imax = np.array([7.0, 1.0, -1.0])
    out = vx.readable_arrays([lv.Array('impulse', imp),
                              lv.Array('impulseMax', imax)])
    assert np.array_equal(out[1].values, imax)
    # no impulse in the file (or another length): as written
    out = vx.readable_arrays([lv.Array('impulseMax', imax0)])
    assert np.array_equal(out[0].values, imax0)
    out = vx.readable_arrays([lv.Array('impulseMax', imax0),
                              lv.Array('impulse', np.ones(2))])
    assert np.array_equal(out[0].values, imax0)


# ── refusals ─────────────────────────────────────────────────────────────
def test_geometry_mismatch_refused():
    pts, polys = surface_geometry()
    n = len(polys)
    a = lv.parse(foam_surface_ascii('p', np.ones(n), pts, polys))
    moved = lv.parse(foam_surface_ascii('pMax', np.ones(n),
                                        *surface_geometry(shift=1e-4)))
    other = list(polys)
    other[0] = other[0][::-1]
    rewired = lv.parse(foam_surface_ascii('pMax', np.ones(n), pts, other))
    fewer_pts, fewer = surface_geometry(n=2)
    smaller = lv.parse(foam_surface_ascii('pMax', np.ones(len(fewer)),
                                          fewer_pts, fewer))
    for label, b in (('moved points', moved), ('rewired', rewired),
                     ('smaller', smaller)):
        try:
            lv.merge([('p', a), ('pMax', b)])
        except ValueError as exc:
            assert 'differ in geometry' in str(exc), exc
            continue
        raise AssertionError(label)
    try:
        lv.merge([('p', a), ('p2', a)])
    except ValueError as exc:
        assert 'more than one file' in str(exc), exc
    else:
        raise AssertionError('one array name twice merged')


def _refused(data, needle=''):
    try:
        lv.parse(data)
    except ValueError as exc:
        assert needle in str(exc), (needle, str(exc))
        return
    raise AssertionError(f'accepted: {data[:80]!r}')


def test_strict_parser():
    pts, polys = surface_geometry(n=1)
    good = foam_surface_ascii('p', [1.0], pts, polys)
    lv.parse(good)
    _refused(b'hello\n', 'not a legacy VTK')
    _refused(good.replace(b'Version 2.0', b'Version 5.1'), '5.x')
    _refused(good.replace(b'ASCII', b'TEXT'), 'ASCII or BINARY')
    _refused(good.replace(b'POLYDATA', b'RECTILINEAR_GRID'), 'DATASET')
    _refused(good.replace(b'CELL_DATA 1', b'CELL_DATA 2'), 'CELL_DATA 2')
    _refused(good.replace(b'p 1 1 float', b'p 1 2 float'), 'tuples')
    _refused(good.replace(b'POLYGONS 1 5', b'POLYGONS 1 6'), 'POLYGONS')
    _refused(good.replace(b'POLYGONS 1 5\n4 0 1 3 2',
                          b'POLYGONS 1 5\n4 0 1 3 9'), 'point id')
    _refused(good + b'1.0\n', 'unsupported attribute')
    _refused(good.replace(b'FIELD attributes 1\np 1 1 float\n1',
                          b'NORMALS n float\n1 0 0'), 'NORMALS')
    _refused(good.replace(b'FIELD attributes 1\np 1 1 float\n1',
                          b'SCALARS p float 1\n1'), 'LOOKUP_TABLE')
    _refused(good.replace(b'FIELD attributes 1\np 1 1 float\n1',
                          b'FIELD attributes 1\np 1 1 long\n1'), 'long')
    _refused(good[:good.rindex(b'1')], 'ends')
    # binary: a truncated payload, and bytes after the last block
    vd, *_ = _merged()
    data = lv.to_bytes(vd)
    lv.parse(data)
    _refused(data[:-10], 'ends inside')
    _refused(data + b'junk\n', 'unsupported attribute')
    _refused(data.replace(b'CELL_DATA 9', b'POINT_DATA 9'), 'POINT_DATA 9')
    raw, _ = foam_volume_binary()
    lv.parse(raw)
    _refused(raw.replace(b'CELL_TYPES 2', b'CELL_TYPES 3'), 'CELL_TYPES')


def test_atomic_write_keeps_old_file():
    vd, *_ = _merged()
    path = _tmp(b'old')
    bad = lv.VtkData('POLYDATA', vd.geometry,
                     cell_data=[lv.Array('x', np.ones(3))])   # 3 for 9 cells
    try:
        lv.write(path, bad)
    except ValueError:
        pass
    else:
        raise AssertionError('a wrong tuple count was written')
    with open(path, 'rb') as f:
        assert f.read() == b'old'
    assert os.listdir(os.path.dirname(path)) == ['f.vtk']


# ── the owner's Viper samples (reference; not in git) ────────────────────
def test_viper_reference_structure():
    """Walk the samples' keyword lines without loading their data, and
    check a file this module writes follows the same order."""
    have = [n for n in ('section_example.vtk', 'obs_example.vtk')
            if os.path.isfile(os.path.join(VIPER, n))]
    if not have:
        print('  [SKIP] the Viper samples are not here '
              '(docs/references/viper_vtk_sample/)')
        return
    datasets = {'section_example.vtk': 'STRUCTURED_POINTS',
                'obs_example.vtk': 'UNSTRUCTURED_GRID'}
    vd, *_ = _merged()
    path = _tmp(b'')
    lv.write(path, vd)
    ours = [ln for _o, ln in lv.scan(path)]
    for n in have:
        keys = [ln for _o, ln in lv.scan(os.path.join(VIPER, n))]
        assert keys[0] == '# vtk DataFile Version 3.0', keys[:3]
        assert keys[2] == 'BINARY', keys[:3]
        assert keys[3] == f'DATASET {datasets[n]}', keys[3]
        i = keys.index('FIELD FieldData 1')
        assert keys[i + 1] == 'TIME 1 1 float', keys[i:i + 2]
        assert keys[i + 2].startswith('CELL_DATA '), keys[i + 2]
        scal = keys[i + 3:]
        assert len(scal) % 2 == 0 and scal, scal
        for s, lut in zip(scal[::2], scal[1::2]):
            w = s.split()
            assert w[0] == 'SCALARS' and w[2:] == ['float', '1'], s
            assert lut == 'LOOKUP_TABLE default', lut
        # the same order in ours: FieldData/TIME right before CELL_DATA,
        # then SCALARS <name> float 1 + LOOKUP_TABLE default
        j = ours.index('FIELD FieldData 1')
        assert ours[j + 1] == 'TIME 1 1 float'
        assert ours[j + 2].startswith('CELL_DATA ')
        for s, lut in zip(ours[j + 3::2], ours[j + 4::2]):
            assert s.split()[0] == 'SCALARS' and s.split()[2:] == \
                ['float', '1'] and lut == 'LOOKUP_TABLE default', (s, lut)


TESTS = [test_round_trip_merge, test_point_data_stays_point_data,
         test_vectors_and_keyword_order, test_binary_is_big_endian,
         test_volume_rewrite, test_every_readable_name,
         test_dynamic_pressure_magnitude,
         test_peak_overpressure_at_t0, test_peak_impulse_max_rule,
         test_geometry_mismatch_refused, test_strict_parser,
         test_atomic_write_keeps_old_file, test_viper_reference_structure]


def main():
    fails = []
    for t in TESTS:
        try:
            t()
            print(f'  [PASS] {t.__name__}')
        except Exception as exc:                    # noqa: BLE001
            print(f'  [FAIL] {t.__name__}: {exc!r}')
            fails.append(t.__name__)
    print(f'\nLEGACY VTK: {"PASS" if not fails else "FAIL"} '
          f'({len(TESTS) - len(fails)}/{len(TESTS)})')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
