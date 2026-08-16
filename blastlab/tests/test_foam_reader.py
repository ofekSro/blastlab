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

    print()
    if FAIL:
        print(f"FOAM READER: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM READER: PASS")


if __name__ == '__main__':
    main()
