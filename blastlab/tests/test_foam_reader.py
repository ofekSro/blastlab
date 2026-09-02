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

    print()
    if FAIL:
        print(f"FOAM READER: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM READER: PASS")


if __name__ == '__main__':
    main()
