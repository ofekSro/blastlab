"""The burst plane at the solver's SAMPLE cadence (M6b).

A blastFoam run can only send a full 3D frame when it WRITES one.
Measured on a real 3D run through the Qt window: 38 frames in 328 s, one
every 8.6 s - while the very same case was decoding its burst plane for
the 2D live view about four times a second. The 3D view was 35 times
staler than the data already on the machine.

So the plane that was already decoded is handed to the 3D scene too.
What this pins:

- the plane really is drawn, at the right size and in the right place;
- it is PRESSURE and only shows while the scene is showing pressure,
  because that is the one field the sample carries;
- a full frame supersedes it, so the scene never keeps one plane ahead
  of a volume that has caught up;
- and the viewer SAYS the plane is ahead, rather than implying the whole
  volume is that fresh.

Needs pyvista. No WSL, no solver.

Run:  cd blastlab/tests && python test_viz3d_sampled_plane.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def main():
    from blastlab.viz3d import pyvista_available
    if not pyvista_available():
        print('  [SKIP] pyvista is not installed')
        return 0
    import numpy as np
    import pyvista as pv
    from blastlab.core.constants import P_AIR
    from blastlab.core.grid import make_grid
    from blastlab.core.bc import solid_mask_3d
    from blastlab.viz3d.sampling import build_face_index
    from blastlab.viz3d.viewer import BlastScene

    dx = 0.1
    grid = make_grid(1.2, 1.0, 0.8, dx)
    x_c, y_c, z_c = grid['x_c'], grid['y_c'], grid['z_c']
    nx, ny, nz = len(x_c), len(y_c), len(z_c)
    bcs = dict(x_lo='terminate', x_hi='terminate',
               y_lo='terminate', y_hi='terminate',
               z_lo='reflect', z_hi='terminate')
    solid = solid_mask_3d(x_c, y_c, z_c, [])
    init = dict(
        x_c=x_c, y_c=y_c, z_c=z_c, dx=dx, stride=1,
        solid_dec=solid, obstacles=[],
        Lx=1.2, Ly=1.0, Lz=0.8,
        charge_center=(0.6, 0.5, 0.4), r_exp=0.15, bcs=bcs,
        face_specs=build_face_index([], x_c, y_c, z_c, solid, bcs),
        slice_axis='y', slice_index=4)

    pl = pv.Plotter(off_screen=True, window_size=(400, 300))
    scene = BlastScene(pl, init)
    layer = scene.layers['sampled']

    print('P1: the layer knows where its plane is')
    check('it took the axis and index from the scene init',
          layer.axis == 'y' and layer.index == 4,
          f'{layer.axis} {layer.index}')
    check('and starts with nothing to draw', layer.t is None)

    print('\nP2: a sample is drawn, in the right place and size')
    arr = np.full((nx, nz), P_AIR, dtype=np.float32)
    arr[6, 3] = P_AIR + 250e3            # 250 kPa somewhere identifiable
    ok = scene.on_sampled_plane(1.5e-3, arr)
    check('the sample was accepted', ok)
    check('and the layer recorded its time', layer.t == 1.5e-3,
          str(layer.t))
    mesh = layer._mesh
    check('the mesh is one cell thick along the slice axis',
          tuple(mesh.dimensions) == (nx, 1, nz),
          str(tuple(mesh.dimensions)))
    check('and sits at the slice coordinate',
          abs(mesh.origin[1] - float(init['y_c'][4])) < 1e-12,
          f'{mesh.origin} vs y={init["y_c"][4]}')
    vals = np.asarray(mesh.point_data['p'])
    check('it carries overpressure in kPa, like every other plot',
          abs(float(vals.max()) - 250.0) < 1e-3, str(float(vals.max())))
    check('and ambient reads as zero overpressure',
          abs(float(vals.min())) < 1e-6, str(float(vals.min())))
    # the marked cell must land where it was put, not transposed
    flat = vals.reshape((nx, nz), order='F')
    check('the array is not transposed on the way in',
          abs(float(flat[6, 3]) - 250.0) < 1e-3,
          f'peak at {np.unravel_index(int(flat.argmax()), flat.shape)}')

    print('\nP3: it only shows while the scene shows pressure')
    check('an actor was added for pressure', layer._actor is not None)
    scene.have['rho'] = True
    scene.frame = {'p': np.full(nx * ny * nz, P_AIR, np.float32),
                   'rho': np.full(nx * ny * nz, 1.2, np.float32)}
    scene._stale = {'rho'}
    scene.set_field('rho')
    check('and it is hidden when the field is not pressure',
          layer._actor is None or not layer._actor.visibility)
    scene.set_field('p')
    check('and back when pressure returns',
          layer._actor is not None and layer._actor.visibility)

    print('\nP4: the HUD says the plane is ahead of the written frame')
    scene.t = 1.0e-3                       # the written frame is older
    scene._update_hud()
    text = _hud_text(scene)
    check('the HUD names the sampled time', 'sampled at' in text, text)
    check('and says it is ahead', 'ahead' in text, text)

    print('\nP5: a full frame supersedes it')
    scene.on_message(('frame', 2.0e-3,
                      {'p': np.full(nx * ny * nz, P_AIR, np.float32)},
                      False))
    check('the sampled plane was dropped once the volume caught up',
          layer.t is None, str(layer.t))
    check('and the HUD stops claiming anything is ahead',
          'ahead' not in _hud_text(scene), _hud_text(scene))

    print('\nP5b: the scene still renders and screenshots with it')
    # A degenerate (one-cell-thick) ImageData is an easy way to upset
    # VTK's pipeline, and a viewer that cannot render is worse than one
    # that is a little stale - so this is checked here rather than five
    # minutes into a foam run.
    scene.on_sampled_plane(2.5e-3, arr)
    shot = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '_sampled_plane_shot.png')
    err = None
    try:
        pl.render()
        pl.screenshot(shot)
    except Exception as exc:
        err = f'{type(exc).__name__}: {exc}'
    check('the plotter renders and screenshots with the plane on',
          err is None, str(err))
    check('and the file is a real image',
          os.path.exists(shot) and os.path.getsize(shot) > 1000,
          str(os.path.getsize(shot) if os.path.exists(shot) else 0))
    try:
        os.remove(shot)
    except OSError:
        pass
    scene.layers['sampled'].clear()

    print('\nP6: a sample that does not fit is refused, not drawn wrong')
    ok2 = scene.on_sampled_plane(3.0e-3,
                                 np.zeros((nx + 3, nz), np.float32))
    check('a wrong-shaped sample is refused', not ok2)
    check('and nothing stale is left claiming to be current',
          layer.t is None, str(layer.t))
    ok3 = scene.on_sampled_plane(3.0e-3, np.zeros(nx, np.float32))
    check('so is a 1D one', not ok3)

    pl.close()
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'VIZ3D SAMPLED PLANE: PASS ({len(RAN)} checks)')
    return 0


def _hud_text(scene):
    actor = scene.hud
    for attr in ('input', 'GetInput'):
        try:
            v = getattr(actor, attr)
            return str(v() if callable(v) else v)
        except Exception:
            continue
    return ''


if __name__ == '__main__':
    sys.exit(main())
