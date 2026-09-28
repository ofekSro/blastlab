"""OUT-4c C2: `vtk_export.decimate`, the volume subsampling post-pass.

docs/batches/2026-09-28-out-4-viper-matrix.md, OUT-4c C2; owner decision
Q4 (2026-09-27): subsample per axis, 3D volumes only - keep the cells in
every k-th BASE-cell layer on each axis, values untouched (a peak between
kept cells is not shown). Pure: a synthetic UNSTRUCTURED_GRID, no WSL.

The grid: 4 x 3 x 5 base cells of 0.1 m from origin (0.2, 0.0, -0.1),
points shared between neighbours; base cell (0, 0, 0) (kept at k = 2) and
(1, 0, 0) (dropped) are split into 8 fine hexahedra each, as AMR / static
refinement leaves them; base cells (2, 0, 2) (kept) and (3, 0, 0)
(dropped) are written as polyhedra (VTK type 42, a face stream), as
foamToVTK -poly writes split-hex cells. The expected kept set comes from
the generator's own record of each cell's base cell, not from centroids.

Checks: the cell count; kept values byte-equal (cell and point data, the
TIME field kept); a valid point re-index (each kept cell's point
coordinates, polyhedron face streams included, equal the source cell's,
no orphan point); a strict legacy_vtk.parse round trip; k = 1 changes
nothing; bad k and a non-UNSTRUCTURED_GRID refused.

Run:  cd blastlab/tests && python test_vtk_decimate.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                            # noqa: E402

from blastlab.output import legacy_vtk as lv                  # noqa: E402
from blastlab.solvers.foam import vtk_export as vx            # noqa: E402

FAIL = []
RAN = []

NX, NY, NZ = 4, 3, 5
H = 0.1                                   # base cell [m]
ORIGIN = (0.2, 0.0, -0.1)                 # [m]
SPLIT = ((0, 0, 0), (1, 0, 0))            # base cells refined into 8
POLY = ((2, 0, 2), (3, 0, 0))             # base cells written as type 42
_HEX = ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
        (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
_FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6),
          (1, 2, 6, 5), (0, 4, 7, 3))


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def synthetic():
    """(VtkData, base index of each cell)."""
    pts, index = [], {}

    def pid(x, y, z):
        key = (round(x, 9), round(y, 9), round(z, 9))
        if key not in index:
            index[key] = len(pts)
            pts.append((ORIGIN[0] + x, ORIGIN[1] + y, ORIGIN[2] + z))
        return index[key]

    conn, types, base = [], [], []
    for k in range(NZ):
        for j in range(NY):
            for i in range(NX):
                if (i, j, k) in SPLIT:
                    h = H / 2
                    for dk in (0, 1):
                        for dj in (0, 1):
                            for di in (0, 1):
                                x0, y0, z0 = (i * H + di * h, j * H + dj * h,
                                              k * H + dk * h)
                                ids = [pid(x0 + a * h, y0 + b * h, z0 + c * h)
                                       for a, b, c in _HEX]
                                conn += [8] + ids
                                types.append(12)
                                base.append((i, j, k))
                    continue
                ids = [pid((i + a) * H, (j + b) * H, (k + c) * H)
                       for a, b, c in _HEX]
                if (i, j, k) in POLY:
                    stream = [len(_FACES)]
                    for f in _FACES:
                        stream += [len(f)] + [ids[v] for v in f]
                    conn += [len(stream)] + stream
                    types.append(42)
                else:
                    conn += [8] + ids
                    types.append(12)
                base.append((i, j, k))
    n, npts = len(types), len(pts)
    geometry = [lv.Block('POINTS', (npts, 'float'),
                         np.asarray(pts, dtype=np.float32)),
                lv.Block('CELLS', (n, len(conn)), np.asarray(conn)),
                lv.Block('CELL_TYPES', (n,), np.asarray(types))]
    rng = np.random.default_rng(7)
    cell = [lv.Array('pressure', (1e5 + rng.random(n) * 1e6)
                     .astype(np.float32), 'float', 'scalars'),
            lv.Array('velocity', rng.random((n, 3)).astype(np.float32),
                     'float', 'vectors'),
            lv.Array('cellID', np.arange(n, dtype=np.int32), 'int', 'field')]
    point = [lv.Array('pointValue', np.arange(npts, dtype=np.float64) * 0.5,
                      'double', 'scalars')]
    vd = lv.VtkData('UNSTRUCTURED_GRID', geometry, cell_data=cell,
                    point_data=point, title='synthetic')
    vd = lv.with_time(vd, 0.00025)
    return vd, base


def cell_points(vd):
    """Per cell: (type, the point ids in stream order, the stream with the
    ids marked None) - the cell's structure without its numbering."""
    conn = np.asarray(vd.block('CELLS').values).tolist()
    types = np.asarray(vd.block('CELL_TYPES').values).tolist()
    out, pos = [], 0
    for t in types:
        m = conn[pos]
        entry = conn[pos + 1:pos + 1 + m]
        pos += 1 + m
        if t == 42:
            ids, shape, j = [], [entry[0]], 1
            for _ in range(entry[0]):
                c = entry[j]
                ids += entry[j + 1:j + 1 + c]
                shape.append(c)
                j += 1 + c
        else:
            ids, shape = entry, [m]
        out.append((t, ids, shape))
    return out


def test_decimate():
    print('\nC2: decimate on a synthetic grid')
    vd, base = synthetic()
    src = lv.parse(lv.to_bytes(vd))           # as the export reads it
    k = 2
    keep = [c for c, b in enumerate(base) if all(v % k == 0 for v in b)]
    want_cells = (len({b for b in base if all(v % k == 0 for v in b)})
                  - 1 + 8)                    # (0,0,0) is split into 8
    check('the expected kept set: 12 base cells, one split into 8 -> 19',
          len(keep) == want_cells == 19, f'{len(keep)} vs {want_cells}')
    out = vx.decimate(src, k, ORIGIN, H)
    check('the cell count equals the prediction', out.n_cells == len(keep),
          f'{out.n_cells} vs {len(keep)}')
    s_cells, o_cells = cell_points(src), cell_points(out)
    s_pts = np.asarray(src.block('POINTS').values)
    o_pts = np.asarray(out.block('POINTS').values)
    ok_geom = len(o_cells) == len(keep) and all(
        so[0] == oo[0] and so[2] == oo[2]
        and np.array_equal(s_pts[so[1]], o_pts[oo[1]])
        for so, oo in zip((s_cells[c] for c in keep), o_cells))
    check('each kept cell: same type, same face-stream shape, and its point '
          'coordinates equal the source cell\'s (valid re-index)', ok_geom)
    check('   polyhedra handled: one kept, one dropped',
          sum(1 for c in o_cells if c[0] == 42) == 1)
    used = sorted({i for c in o_cells for i in c[1]})
    want_pts = len({i for c in keep for i in s_cells[c][1]})
    check('no orphan point: every point is used, and the count is the '
          'kept cells\' distinct points', used == list(range(len(o_pts)))
          and len(o_pts) == want_pts == out.n_points,
          f'{len(o_pts)} points, want {want_pts}')
    same = all(a.name == b.name and a.vtk_type == b.vtk_type
               and a.kind == b.kind
               and np.asarray(a.values)[keep].tobytes()
               == np.asarray(b.values).tobytes()
               for a, b in zip(src.cell_data, out.cell_data))
    check('cell data: every kept value byte-equal, names / types / kinds '
          'kept', same and len(out.cell_data) == len(src.cell_data))
    old_ids = [s_cells[c][1] for c in keep]
    new_ids = [c[1] for c in o_cells]
    m = {}
    for a, b in zip(old_ids, new_ids):
        m.update(zip(b, a))
    pv_s = np.asarray(src.point_data[0].values)
    pv_o = np.asarray(out.point_data[0].values)
    check('point data follows its points, byte-equal',
          pv_o.tobytes() == pv_s[[m[i] for i in range(len(pv_o))]].tobytes())
    check('the TIME field is kept', [a.name for a in out.field_data]
          == ['TIME'] and float(out.field_data[0].values[0])
          == float(src.field_data[0].values[0]))
    back = lv.parse(lv.to_bytes(out))
    check('a strict legacy_vtk.parse round trip holds it exactly',
          lv.compare(back, out) is None, str(lv.compare(back, out)))
    check('the source is not modified', lv.to_bytes(src) == lv.to_bytes(
        lv.parse(lv.to_bytes(vd))))
    check('k = 1 changes nothing (the same object back)',
          vx.decimate(src, 1, ORIGIN, H) is src)
    k3 = vx.decimate(src, 3, ORIGIN, H)
    want3 = [c for c, b in enumerate(base) if all(v % 3 == 0 for v in b)]
    check('k = 3: layers 0 and 3 on each axis',
          k3.n_cells == len(want3), f'{k3.n_cells} vs {len(want3)}')
    k9 = vx.decimate(src, 9, ORIGIN, H)
    want9 = [c for c, b in enumerate(base) if b == (0, 0, 0)]
    check('k beyond the grid keeps the first layer only (8 fine cells)',
          k9.n_cells == len(want9) == 8, str(k9.n_cells))
    for bad in (0, -2, 1.5, True, '2'):
        try:
            vx.decimate(src, bad, ORIGIN, H)
            check(f'k = {bad!r} refused', False)
        except ValueError:
            check(f'k = {bad!r} refused', True)
    for kw in (dict(dx_base=0.0), dict(origin=(0.0, 0.0))):
        args = dict(origin=ORIGIN, dx_base=H)
        args.update(kw)
        try:
            vx.decimate(src, 2, **args)
            check(f'bad {sorted(kw)} refused', False)
        except ValueError:
            check(f'bad {sorted(kw)} refused', True)
    poly = lv.VtkData('POLYDATA', [lv.Block('POINTS', (0, 'float'),
                                            np.zeros((0, 3)))])
    try:
        vx.decimate(poly, 2, ORIGIN, H)
        check('a POLYDATA surface refused', False)
    except ValueError:
        check('a POLYDATA surface refused', True)


def main():
    test_decimate()
    print()
    print(f'VTK DECIMATE: ' + ('PASS' if not FAIL else
                               f'FAIL ({len(FAIL)}): ' + ', '.join(FAIL))
          + f' ({len(RAN) - len(FAIL)}/{len(RAN)})')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
