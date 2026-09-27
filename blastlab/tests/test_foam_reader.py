"""foam.reader tests against committed REAL blastFoam output
(foam_fixtures/, harvested from a 1 kg TNT / R=2 m sector run on
blastFoam v6.2.0), plus synthetic F-order reshape checks. No WSL
needed."""

import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.solvers.foam import reader                       # noqa: E402

FIX = os.path.join(HERE, 'foam_fixtures')
N = 190                     # cells in the fixture run
FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def main():
    # nonuniform scalar (final-time p of the fixture run)
    p = reader.read_scalar(os.path.join(FIX, 'p_nonuniform'), N)
    check('scalar nonuniform', len(p) == N
          and abs(p[0] - 158944.0) < 1e-6 and abs(p[-1] - 129465.0) < 1e-6
          and np.isfinite(p).all() and (p > 0).all())
    try:
        reader.read_scalar(os.path.join(FIX, 'p_nonuniform'), N + 1)
        check('scalar length mismatch raises', False)
    except ValueError:
        check('scalar length mismatch raises', True)

    # uniform scalar (initial p written by the blastlab writer)
    p0 = reader.read_scalar(os.path.join(FIX, 'p_uniform'), N)
    check('scalar uniform', len(p0) == N and (p0 == 101325.0).all())

    # torn mid-write uniform field (cut before the ';'): ValueError, not
    # the AttributeError that used to escape the ingest retry guards
    try:
        reader.read_scalar(os.path.join(FIX, 'p_uniform_truncated'), N)
        check('uniform truncated raises', False)
    except ValueError:
        check('uniform truncated raises', True)
    except Exception as exc:                # noqa: BLE001 - diagnostic
        check('uniform truncated raises', False, type(exc).__name__)
    try:
        reader.read_vector(os.path.join(FIX, 'p_uniform_truncated'), N)
        check('uniform truncated vector raises', False)
    except ValueError:
        check('uniform truncated vector raises', True)
    except Exception as exc:                # noqa: BLE001 - diagnostic
        check('uniform truncated vector raises', False,
              type(exc).__name__)

    # nonuniform vector
    U = reader.read_vector(os.path.join(FIX, 'U_nonuniform'), N)
    check('vector nonuniform', U.shape == (N, 3)
          and abs(U[0, 0] - 1.75732) < 1e-6
          and (U[:, 1] == 0).all() and (U[:, 2] == 0).all()
          and abs(U[:, 0].max() - 144.325) < 1e-3)

    # uniform/time: exact t and deltaT (dir names are display-precision).
    # read_time expects <dir>/uniform/time; the fixture stores the file
    # flat, so exercise the parser through a temp layout.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, 'uniform'))
        with open(os.path.join(FIX, 'time_uniform'), 'rb') as f:
            data = f.read()
        with open(os.path.join(td, 'uniform', 'time'), 'wb') as f:
            f.write(data)
        t, dt = reader.read_time(td)
    check('uniform/time exact values',
          abs(t - 0.0027290703852363637) < 1e-18
          and abs(dt - 4.01334e-06) < 1e-12)

    # blastProbes file: header points + columns
    with tempfile.TemporaryDirectory() as td:
        pdir = os.path.join(td, 'postProcessing', 'gauges', '0')
        os.makedirs(pdir)
        with open(os.path.join(FIX, 'probes_p'), 'rb') as f:
            data = f.read()
        with open(os.path.join(pdir, 'p'), 'wb') as f:
            f.write(data)
        pr = reader.read_probes(td)
    check('probes points', pr['points']
          == [(0.5, 0.0, 0.0), (1.0, 0.0, 0.0), (1.5, 0.0, 0.0)])
    check('probes columns', len(pr['pressures']) == 3
          and len(pr['times']) == 852
          and all(len(x) == 852 for x in pr['pressures'])
          and (np.diff(pr['times']) > 0).all())
    check('probes physics sane',
          pr['pressures'][0].max() > pr['pressures'][1].max()
          > pr['pressures'][2].max() > 1.5 * 101325.0)
    check('p-only run: no speeds/rhos keys (T44 degrades cleanly)',
          'speeds' not in pr and 'rhos' not in pr)

    # T44/N12: U (vector file format!) and rho ride along when their
    # rows align with p's; a torn/missing extra degrades to p-only
    with tempfile.TemporaryDirectory() as td:
        pdir = os.path.join(td, 'postProcessing', 'gauges', '0')
        os.makedirs(pdir)
        for fx, name in (('probes_p2', 'p'), ('probes_U', 'U'),
                         ('probes_rho', 'rho')):
            src = os.path.join(FIX, fx if fx != 'probes_p2'
                               else 'probes_U')
            pass
        # build a 3-row p file matching the U/rho fixtures
        with open(os.path.join(pdir, 'p'), 'w') as f:
            f.write('# Probe 0 (0.5 0 0)\n'
                    '# Probe 1 (1 0 0)\n'
                    '#         Time             0             1\n'
                    '            0        101325        101325\n'
                    '  1.19964e-07        201325        101325\n'
                    '  2.63446e-07        301325        111325\n')
        import shutil as _sh
        _sh.copy(os.path.join(FIX, 'probes_U'),
                 os.path.join(pdir, 'U'))
        _sh.copy(os.path.join(FIX, 'probes_rho'),
                 os.path.join(pdir, 'rho'))
        pr2 = reader.read_probes(td)
        check('U probes parsed as |U| per gauge (3-4-0 -> 5)',
              'speeds' in pr2 and len(pr2['speeds']) == 2
              and np.allclose(pr2['speeds'][0], [0.0, 5.0, 10.0])
              and np.allclose(pr2['speeds'][1], [0.0, 0.0, 3.0]),
              str(pr2.get('speeds')))
        check('rho probes ride along',
              'rhos' in pr2
              and np.allclose(pr2['rhos'][0], [1.225, 2.45, 4.9]),
              str(pr2.get('rhos')))
        check('pressures unchanged by the extras',
              np.allclose(pr2['pressures'][0],
                          [101325, 201325, 301325]))
        # HD1-13: the vectors themselves ride along too - a wall load
        # needs the component INTO the wall, which |U| has thrown away
        vel = pr2.get('velocities')
        check('U vectors per probe, aligned with p row for row',
              vel is not None and len(vel) == 2
              and all(v.shape == (3, 3) for v in vel)
              and np.array_equal(vel[0], [[0, 0, 0], [3, 4, 0], [6, 8, 0]])
              and np.array_equal(vel[1], [[0, 0, 0], [0, 0, 0], [1, 2, 2]]),
              str(vel))
        check('speeds == |velocities|, bit for bit',
              vel is not None
              and all(np.array_equal(s, np.sqrt((v ** 2).sum(axis=1)))
                      for s, v in zip(pr2['speeds'], vel)))
        check('p-only run: no velocities key either',
              'velocities' not in pr)
        # P2-14 item 7: identical times -> rho/U attached exactly as
        # before, and the key set is today's (no `warnings` key), so the
        # gauge TSVs written from this dict stay byte-identical
        check('identical times: the key set is exactly today\'s',
              set(pr2) == {'points', 'times', 'pressures', 'rhos',
                           'speeds', 'velocities'}, str(sorted(pr2)))
        check('identical times: rho/U arrays exactly as written',
              np.array_equal(pr2['rhos'][0], np.array([1.225, 2.45, 4.9]))
              and np.array_equal(pr2['rhos'][1],
                                 np.array([1.225, 1.225, 1.3]))
              and np.array_equal(pr2['speeds'][0],
                                 np.sqrt(np.array([0.0, 25.0, 100.0])))
              and np.array_equal(pr2['speeds'][1],
                                 np.sqrt(np.array([0.0, 0.0, 9.0])))
              and all(r.dtype == np.float64 for r in pr2['rhos']),
              str((pr2.get('rhos'), pr2.get('speeds'))))
        # a torn U file (fewer rows) must NOT misalign - drop it
        with open(os.path.join(pdir, 'U'), 'w') as f:
            f.write('# Probe 0 (0.5 0 0)\n'
                    '#         Time             0\n'
                    '            0    (0 0 0)\n')
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            pr3 = reader.read_probes(td)
        check('torn U file degrades to p-only, never misaligns',
              'speeds' not in pr3 and 'rhos' in pr3)
        check('and drops the vectors with it',
              'velocities' not in pr3)
        check('torn U: one warning naming U, in the dict and on stderr',
              len(pr3.get('warnings', [])) == 1
              and pr3['warnings'][0].startswith('U: times do not match p')
              and err.getvalue().count('\n') == 1
              and err.getvalue().startswith(
                  '[blastlab] probes: U times do not match p - using p '
                  'only ('), repr((pr3.get('warnings'), err.getvalue())))
        # equal row count but shifted times: never misaligned by count -
        # p-only for that field, a warning, no raise
        with open(os.path.join(pdir, 'U'), 'w') as f:
            f.write('# Probe 0 (0.5 0 0)\n'
                    '# Probe 1 (1 0 0)\n'
                    '#         Time             0             1\n'
                    '  1.19964e-07    (0 0 0)    (0 0 0)\n'
                    '  2.63446e-07    (3 4 0)    (0 0 0)\n'
                    '  3.91000e-07    (6 8 0)    (1 2 2)\n')
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                pr4 = reader.read_probes(td)
            raised = None
        except Exception as exc:            # noqa: BLE001 - diagnostic
            pr4, raised = None, exc
        check('shifted U times (same row count): no raise', raised is None,
              repr(raised))
        check('shifted U times: p kept, U dropped, rho still attached',
              pr4 is not None and 'speeds' not in pr4
              and 'velocities' not in pr4 and 'rhos' in pr4
              and np.array_equal(pr4['pressures'][0],
                                 np.array([101325.0, 201325.0, 301325.0])),
              str(None if pr4 is None else sorted(pr4)))
        check('shifted U times: one warning, dict and stderr',
              pr4 is not None and len(pr4.get('warnings', [])) == 1
              and 'row 0' in pr4['warnings'][0]
              and err.getvalue().startswith(
                  '[blastlab] probes: U times do not match p - using p '
                  'only (row 0: t = 1.19964e-07 vs 0 in p)'),
              repr((None if pr4 is None else pr4.get('warnings'),
                    err.getvalue())))

    # ── binary format (fixtures from a writeFormat-binary sector run) ──
    NB = 190                    # cells in the binary fixture run
    pb = reader.read_scalar(os.path.join(FIX, 'p_binary'), NB)
    check('binary scalar', len(pb) == NB and np.isfinite(pb).all()
          and abs(pb[0] - 88220.07645915999) < 1e-6
          and (pb > 5e4).all() and (pb < 2e5).all())
    try:
        reader.read_scalar(os.path.join(FIX, 'p_binary'), NB + 1)
        check('binary scalar count mismatch raises', False)
    except ValueError:
        check('binary scalar count mismatch raises', True)

    Ub = reader.read_vector(os.path.join(FIX, 'U_binary'), NB)
    check('binary vector', Ub.shape == (NB, 3)
          and abs(Ub[0, 0] - 0.00040734364585767713) < 1e-15
          and (Ub[:, 1] == 0).all() and (Ub[:, 2] == 0).all())

    # truncated mid-write binary file -> ValueError (caller re-polls)
    try:
        reader.read_scalar(os.path.join(FIX, 'p_binary_truncated'), NB)
        check('binary truncated raises', False)
    except ValueError:
        check('binary truncated raises', True)

    # uniform internalField inside a format-binary file stays text
    pu = reader.read_scalar(os.path.join(FIX, 'p_uniform_binaryheader'),
                            NB)
    check('uniform in binary file', len(pu) == NB
          and (pu == 101325.0).all())

    # restart merge: two time subdirs; the later dir starts at a time
    # the earlier one extends past - earlier rows must be clipped to
    # t < first_t(later) and the later dir's rows win from there on.
    hdr = ('# Probe 0 (0.5 0 0)\n# Probe 1 (1 0 0)\n'
           '#         Time             0             1\n')
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, 'postProcessing', 'gauges')
        os.makedirs(os.path.join(base, '0'))
        os.makedirs(os.path.join(base, '0.002'))
        with open(os.path.join(base, '0', 'p'), 'w') as f:
            f.write(hdr + '0.000 100 200\n0.001 101 201\n'
                          '0.002 999 999\n0.003 999 999\n')
        with open(os.path.join(base, '0.002', 'p'), 'w') as f:
            f.write(hdr + '0.002 102 202\n0.003 103 203\n')
        pr = reader.read_probes(td)
    check('restart merge times',
          np.allclose(pr['times'], [0.000, 0.001, 0.002, 0.003]))
    check('restart merge later dir wins',
          np.allclose(pr['pressures'][0], [100, 101, 102, 103])
          and np.allclose(pr['pressures'][1], [200, 201, 202, 203]))
    check('restart merge points kept',
          pr['points'] == [(0.5, 0.0, 0.0), (1.0, 0.0, 0.0)])

    # sets line sample (raw .xy): coords + values; a partial mid-write
    # last line is skipped, not fatal
    with tempfile.TemporaryDirectory() as td:
        sdir = os.path.join(td, 'postProcessing', 'liveLine', '0.00123')
        os.makedirs(sdir)
        with open(os.path.join(sdir, 'line_p.xy'), 'w') as f:
            f.write('0.0005 101325\n0.0015 150000\n0.0025 2.5e')
        ts = reader.list_sample_times(td, 'liveLine')
        rp = reader.read_line_sample(td, 'liveLine', '0.00123')
        missing = reader.read_line_sample(td, 'liveLine', '0.002')
    check('sample times listed', ts == [(0.00123, '0.00123')])
    check('line sample parsed', rp is not None
          and np.allclose(rp[0], [0.0005, 0.0015])
          and np.allclose(rp[1], [101325.0, 150000.0]))
    check('missing sample dir -> None', missing is None)
    check('no samples yet -> empty list',
          reader.list_sample_times(FIX, 'liveLine') == [])

    # surfaces slice sample (raw x y z v rows): header skipped, partial
    # mid-write tail row dropped
    with tempfile.TemporaryDirectory() as td:
        sdir = os.path.join(td, 'postProcessing', 'liveSlice', '0.001')
        os.makedirs(sdir)
        with open(os.path.join(sdir, 'p_slice.raw'), 'w') as f:
            f.write('# x y z p\n'
                    '0.5 0.5 0 101325\n1.5 0.5 0 150000\n'
                    '0.5 1.5 0 120000\n1.5 1.5 0\n')
        sp = reader.read_surface_sample(td, 'liveSlice', '0.001')
    check('surface sample parsed', sp is not None
          and sp[0].shape == (3, 3) and len(sp[1]) == 3
          and np.allclose(sp[1], [101325.0, 150000.0, 120000.0])
          and np.allclose(sp[0][1], [1.5, 0.5, 0.0]))

    # F-order reshape onto the native grid layout (x-fastest cell order)
    nx, ny, nz = 4, 3, 2
    flat = np.arange(nx * ny * nz, dtype=float)
    spec3 = SimpleNamespace(dim=3, nx=nx, ny=ny, nz=nz)
    a = reader.to_grid(flat, spec3)
    ok = all(a[i, j, k] == i + nx * j + nx * ny * k
             for i in range(nx) for j in range(ny) for k in range(nz))
    check('3d F-order reshape', ok)
    spec2 = SimpleNamespace(dim=2, nx=nx, ny=ny)
    b = reader.to_grid(np.arange(nx * ny, dtype=float), spec2)
    check('2d F-order reshape',
          all(b[i, j] == i + nx * j
              for i in range(nx) for j in range(ny)))
    spec1 = SimpleNamespace(dim=1)
    check('1d passthrough',
          (reader.to_grid(flat, spec1) == flat).all())

    # obstacle-carved mesh: fluid values scatter around the solid mask
    # (subsetMesh keeps cells in ascending x-fastest order), carved
    # cells take the fill value
    solid = np.zeros((nx, ny, nz), dtype=bool)
    solid[1, 2, 0] = solid[3, 0, 1] = True
    fluid_flat = ~solid.flatten(order='F')
    spec3s = SimpleNamespace(dim=3, nx=nx, ny=ny, nz=nz, solid=solid)
    vals = flat[fluid_flat]             # what the foam field would hold
    c = reader.to_grid(vals, spec3s, fill=-1.0)
    ok = all(c[i, j, k] == (-1.0 if solid[i, j, k]
                            else i + nx * j + nx * ny * k)
             for i in range(nx) for j in range(ny) for k in range(nz))
    check('3d obstacle scatter + fill', ok)

    # refined-mesh remap (N15): to_grid gathers per fine cell, -1 = carved
    remap = np.array([[0, 0, 1, 2],
                      [0, 0, 3, 4],
                      [5, 6, -1, -1],
                      [7, 8, -1, -1]], dtype=np.int32)
    rspec = SimpleNamespace(dim=2, nx=4, ny=4, remap=remap)
    vals = np.arange(9, dtype=float) * 10.0
    g = reader.to_grid(vals, rspec, fill=-1.0)
    check('remap to_grid: coarse cell fills its 2x2 block',
          (g[:2, :2] == 0.0).all() and g[0, 2] == 10.0 and g[1, 3] == 40.0)
    check('remap to_grid: carved fine cells take fill',
          (g[2:, 2:] == -1.0).all() and g[3, 1] == 80.0)
    # count-free vector read (cell centres of a refined mesh)
    ctxt = ('FoamFile { format ascii; class volVectorField; object C; }\n'
            'dimensions [0 1 0 0 0 0 0];\n'
            'internalField   nonuniform List<vector> \n3\n(\n'
            '(0.1 0.2 0)\n(0.3 0.4 0)\n(0.5 0.6 0)\n)\n;\n'
            'boundaryField { }\n')
    import tempfile as _tf
    cpath = os.path.join(_tf.mkdtemp(prefix='blastlab_c_'), 'C')
    with open(cpath, 'w') as f:
        f.write(ctxt)
    C = reader.read_vector(cpath, None)
    check('read_vector(n_cells=None) accepts any count', C.shape == (3, 3)
          and abs(C[2, 1] - 0.6) < 1e-12, str(C.shape))
    try:
        reader.read_vector(cpath, 4)
        check('read_vector strict count still enforced', False)
    except ValueError:
        check('read_vector strict count still enforced', True)

    # obstacle-aware live-slice decode (backend._decode_surface with a
    # slice mask): fluid rows land on their cells, carved cells read
    # ambient, and a short mid-write sample returns None
    import tempfile
    from blastlab.core.constants import P_AIR
    from blastlab.solvers.foam import backend, writer as fwriter
    sx, sy = 4, 3
    smask = np.zeros((sx, sy), dtype=bool)
    smask[2, 1] = smask[3, 1] = True
    xs = (np.arange(sx) + 0.5) * 0.1
    ys = (np.arange(sy) + 0.5) * 0.1
    rows, want = [], {}
    v = 100.0
    for i in range(sx):
        for j in range(sy):
            if smask[i, j]:
                continue
            v += 1.0
            want[(i, j)] = v
            rows.append(f'{xs[i]} {ys[j]} 0.0 {v}')
    rows = [rows[k] for k in (5, 0, 9, 3, 7, 1, 8, 2, 6, 4)]
    tmp = tempfile.mkdtemp()
    sdir = os.path.join(tmp, 'postProcessing', fwriter.LIVE_SLICE,
                        '0.001')
    os.makedirs(sdir)
    with open(os.path.join(sdir, 'p_slice.raw'), 'w') as f:
        f.write('\n'.join(rows) + '\n')
    sspec = SimpleNamespace(dim=2, nx=sx, ny=sy, case_unc=tmp,
                            solid=smask)
    out = backend._decode_surface(sspec, '0.001', (sx, sy), 0, 1, smask)
    check('slice decode scatters around carve',
          out is not None
          and all(out[i, j] == (P_AIR if smask[i, j] else want[(i, j)])
                  for i in range(sx) for j in range(sy)))
    with open(os.path.join(sdir, 'p_slice.raw'), 'w') as f:
        f.write('\n'.join(rows[:-2]) + '\n')
    check('short carved sample -> None',
          backend._decode_surface(sspec, '0.001', (sx, sy), 0, 1,
                                  smask) is None)

    # N2-16: a count within 1% of expected is a python-carve vs
    # boxToCell centre-line tie, not a torn write - the rows are placed
    # by their coordinates instead of refused (R2's 171,604-row samples
    # against a 171,580-cell mask killed the whole live path). On a
    # large enough grid, one extra row must be accepted and land in the
    # right cell; the tiny 3x3 fixture above stays strict because 1%
    # of 9 rounds to zero.
    bx, by = 20, 10
    bmask = np.zeros((bx, by), dtype=bool)
    brows = ['# x y z p']
    bwant = {}
    for i in range(bx):
        for j in range(by):
            v = 1000.0 + i * by + j
            bwant[(i, j)] = v
            brows.append(f'{(i + 0.5):.3f} {(j + 0.5):.3f} 0 {v}')
    # the "tie row": one extra sampled row, as boxToCell keeping a row
    # the python mask carved - its coordinates land it in cell (5, 5)
    brows.append(f'{5.5:.3f} {5.5:.3f} 0 {7777.0}')
    # time dir 0.004: the AMR checks further down own 0.003 in the same
    # tmp tree, and read_surface_sample reads whatever .raw sits in the
    # dir - sharing it made those checks read THIS fixture's rows
    bdir = os.path.join(tmp, 'postProcessing', 'liveSlice', '0.004')
    os.makedirs(bdir, exist_ok=True)
    with open(os.path.join(bdir, 'p_big.raw'), 'w') as f:
        f.write('\n'.join(brows) + '\n')
    bspec = SimpleNamespace(dim=2, nx=bx, ny=by, case_unc=tmp,
                            solid=bmask, dx=1.0)
    bout = backend._decode_surface(bspec, '0.004', (bx, by), 0, 1, bmask)
    check('tie-sized surplus decodes by coordinates (N2-16)',
          bout is not None and bout[5, 5] == 7777.0
          and bout[0, 0] == bwant[(0, 0)]
          and bout[bx - 1, by - 1] == bwant[(bx - 1, by - 1)])

    # remap branch: rows are cut-polygon centroids (= in-plane centres);
    # a 2x2 fine plane where the left column is one coarse cell
    rmap = np.array([[0, 0], [1, 2]], dtype=np.int32)
    rdir = os.path.join(tmp, 'postProcessing', 'liveSlice', '0.002')
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, 'p_plane.raw'), 'w') as f:
        f.write('# x y z p\n0.5 1.0 0 100\n1.5 0.5 0 200\n1.5 1.5 0 300\n')
    rspec2 = SimpleNamespace(dim=2, nx=2, ny=2, case_unc=tmp, dx=1.0,
                             n_cells=3, remap=rmap)
    got = backend._decode_surface(rspec2, '0.002', (2, 2), 0, 1,
                                  remap_sl=rmap)
    check('remap decode: coarse cell value fills both fine cells',
          got is not None and got[0, 0] == 100 and got[0, 1] == 100
          and got[1, 0] == 200 and got[1, 1] == 300,
          str(None if got is None else got.tolist()))
    with open(os.path.join(rdir, 'p_plane.raw'), 'w') as f:
        f.write('# x y z p\n0.5 1.0 0 100\n1.5 0.5 0 200\n')
    check('remap decode: incomplete sample -> None (retry)',
          backend._decode_surface(rspec2, '0.002', (2, 2), 0, 1,
                                  remap_sl=rmap) is None)

    # dynamic-AMR live-slice decode (backend._decode_surface_amr): the
    # rows carry no cell size - each centre pins its level and the
    # sample tiles the display plane like a written mesh. 2 x 2 m, base
    # 1 m, display level 1 (4 x 4 at 0.5 m): a level-0 cell, ten
    # level-1 cells and one display cell holding four level-2 cells
    # (finer than the display -> box-averaged, level capped at 1)
    adir = os.path.join(tmp, 'postProcessing', 'liveSlice', '0.003')
    os.makedirs(adir, exist_ok=True)
    arows = ['0.5 0.5 0 100',
             '1.25 0.25 0 200', '1.75 0.25 0 300', '1.25 0.75 0 400',
             '1.75 0.75 0 500',
             '0.25 1.25 0 600', '0.75 1.25 0 700', '0.25 1.75 0 800',
             '0.75 1.75 0 900',
             '1.75 1.25 0 1100', '1.25 1.75 0 1200', '1.75 1.75 0 1300',
             '1.125 1.125 0 10', '1.375 1.125 0 20', '1.125 1.375 0 30',
             '1.375 1.375 0 40']
    arows = [arows[k] for k in (9, 3, 14, 0, 12, 7, 1, 15, 5, 11, 2, 13,
                                8, 6, 10, 4)]
    with open(os.path.join(adir, 'p_slice.raw'), 'w') as f:
        f.write('# x y z p\n' + '\n'.join(arows) + '\n')
    aspec = SimpleNamespace(case_unc=tmp, dx_base=1.0, amr=2,
                            display_level=1)
    fuv = (np.arange(5) * 0.5, np.arange(5) * 0.5)
    got = backend._decode_surface_amr(aspec, '0.003', 0, 1, fuv)
    want = np.array([[100, 100, 600, 800], [100, 100, 700, 900],
                     [200, 400, 25, 1200], [300, 500, 1100, 1300]], float)
    want_lv = np.ones((4, 4), dtype=int)
    want_lv[0:2, 0:2] = 0
    check('AMR slice decode: levels off the centres, exact tiling, '
          'sub-display cells averaged',
          got is not None and np.allclose(got[0], want)
          and (got[1] == want_lv).all(),
          'None' if got is None else str(got[0].tolist()))
    with open(os.path.join(adir, 'p_slice.raw'), 'w') as f:
        f.write('# x y z p\n' + '\n'.join(arows[:-3]) + '\n')
    check('AMR slice decode: incomplete sample -> None (retry)',
          backend._decode_surface_amr(aspec, '0.003', 0, 1, fuv) is None)
    with open(os.path.join(adir, 'p_slice.raw'), 'w') as f:
        f.write('# x y z p\n' + '\n'.join(arows) + '\n1.7')
    check('AMR slice decode: partial trailing row is dropped, not fatal',
          backend._decode_surface_amr(aspec, '0.003', 0, 1, fuv)
          is not None)

    print()
    if FAIL:
        print(f"FOAM READER: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM READER: PASS")


if __name__ == '__main__':
    main()
