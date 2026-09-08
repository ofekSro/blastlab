"""Revolver tests: 2D axisymmetric (r, z) frames revolved into the
Cartesian 3D block the embedded viewer consumes (pure NumPy).

Run:  python test_revolve3d.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.viz3d.sampling import Revolver, build_scene_init  # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def main():
    R, Lz, dr = 2.0, 4.0, 0.1
    r_c = (np.arange(int(R / dr)) + 0.5) * dr           # 20 cells
    z_c = (np.arange(int(Lz / dr)) + 0.5) * dr          # 40 cells
    from blastlab.core.bc import solid_mask_2d
    obstacles = [(1.0, 1.2, 0.0, 0.8)]
    info = dict(r_c=r_c, z_c=z_c,
                solid=solid_mask_2d(r_c, z_c, obstacles),
                bcs=dict(x_lo='reflect', x_hi='terminate',
                         y_lo='reflect', y_hi='terminate'),
                obstacles=obstacles,
                z0=1.0, r_exp=0.2, R=R, Lz=Lz)
    rev = Revolver(info, max_dim=64)
    s = rev.scene3d

    check('domain box 2R x 2R x Lz',
          s['Lx'] == 4.0 and s['Ly'] == 4.0 and s['Lz'] == 4.0)
    check('axis at domain centre, burst height kept',
          s['charge_center'] == (2.0, 2.0, 1.0))
    check('bcs mapped (ground from y_lo, sides from x_hi)',
          s['bcs']['z_lo'] == 'reflect' and s['bcs']['z_hi'] == 'terminate'
          and all(s['bcs'][k] == 'terminate'
                  for k in ('x_lo', 'x_hi', 'y_lo', 'y_hi')))
    check('uniform cubic spacing',
          np.allclose(np.diff(s['x_c']), s['dx'])
          and np.allclose(np.diff(s['z_c']), s['dx']))
    check('dims capped', max(len(s['x_c']), len(s['y_c']),
                             len(s['z_c'])) <= 64)
    check('solid revolved to 3D',
          s['solid'].shape == (len(s['x_c']), len(s['y_c']),
                               len(s['z_c']))
          and s['solid'].dtype == bool)
    n_mid = len(s['x_c']) // 2
    check('cylinder metadata for the viewer',
          s['cyl'] == dict(cx=R, cy=R, R=R))
    check('outside-radius corners marked no-data',
          s['solid'][0, 0, 0] and s['solid'][-1, -1, -1]
          and not s['solid'][n_mid, n_mid, 0])

    # radial mapping: f(r, z) = r -> axis cells read the innermost
    # ring, corners (r > R) clamp to the outermost ring
    f_r = np.repeat(r_c[:, None], len(z_c), axis=1)
    p3 = rev.revolve(f_r)
    n = len(s['x_c'])
    check('revolved shape', p3.shape == (n, n, len(s['z_c'])))
    check('axis reads innermost ring',
          p3[n // 2, n // 2, 0] == r_c[0])
    check('corner clamps to outermost ring', p3[0, 0, 0] == r_c[-1])
    check('rotationally symmetric',
          np.array_equal(p3, p3[::-1, :, :])
          and np.array_equal(p3, p3.transpose(1, 0, 2)))

    # axial mapping: f(r, z) = z -> each 3D layer reads its own height
    f_z = np.repeat(z_c[None, :], len(r_c), axis=0)
    p3z = rev.revolve(f_z)
    check('z layers preserved',
          all(np.all(p3z[:, :, k] == z_c[k])
              for k in range(0, len(s['z_c']), 7)))

    try:
        rev.revolve(np.zeros((len(r_c), len(z_c) + 1)))
        check('shape mismatch raises', False)
    except ValueError:
        check('shape mismatch raises', True)

    # obstacle rectangle -> viewer ring + revolved solid annulus
    check('rings carried for the viewer', s['rings'] == [obstacles[0]])
    xi = int(np.argmin(np.abs(s['x_c'] - (R + 1.1))))
    yi = int(np.argmin(np.abs(s['y_c'] - R)))
    zi = int(np.argmin(np.abs(s['z_c'] - 0.4)))
    check('obstacle annulus solid in 3D',
          s['solid'][xi, yi, zi]                     # on the ring
          and not s['solid'][n_mid, n_mid, zi])      # axis stays fluid

    # the scene3d dict must feed the normal viewer pipeline: stride 1
    # (already capped) and a ground plane from the mapped z_lo wall
    init, stride, specs = build_scene_init(s)
    check('viewer init stride 1', stride == 1)
    check('ground face present',
          any(sp.face_id == 'ground' for sp in specs))
    check('rings propagated to viewer init',
          init['rings'] == [obstacles[0]])

    print()
    if FAIL:
        print(f"REVOLVE 3D: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("REVOLVE 3D: PASS")


if __name__ == '__main__':
    main()
