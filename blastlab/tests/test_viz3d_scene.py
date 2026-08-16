"""Off-screen smoke test of the 3D viewer scene (requires pyvista).

Builds a BlastScene on an off-screen plotter, feeds synthetic expanding-
blast frames through on_message, exercises every layer toggle, the
field/colour-scale controls, cross-section planes, view presets and the
playback path, and screenshots the result. No window is opened.
"""
import os, sys
import numpy as np

sys.path.insert(0, r'c:\Users\rotem.ofek\Projects\BlastFoam')

from blastlab.core.constants import P_AIR
from blastlab.core.grid import make_grid
from blastlab.core.bc import solid_mask_3d
from blastlab.viz3d.sampling import (build_face_index, choose_stride,
                                     decimate, extract_loads)

FAIL = []

def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


import pyvista as pv
from blastlab.viz3d.viewer import BlastScene, GeometryScene, FIELDS

# ── synthetic scene: 4 m cube, one box, ground wall ─────────────────────────
grid = make_grid(4.0, 4.0, 4.0, 0.1)
x_c, y_c, z_c = grid['x_c'], grid['y_c'], grid['z_c']
obstacles = [(2.5, 3.0, 1.5, 2.5, 0.0, 1.0)]
solid = solid_mask_3d(x_c, y_c, z_c, obstacles)
bcs = dict(x_lo='open', x_hi='open', y_lo='open', y_hi='open',
           z_lo='wall', z_hi='open')
stride = choose_stride(solid.shape)
specs = build_face_index(obstacles, x_c, y_c, z_c, solid, bcs)
center = (1.5, 2.0, 1.0)

init = dict(stride=stride, x_c=x_c, y_c=y_c, z_c=z_c, dx=0.1,
            solid_dec=decimate(solid.astype(np.float32), stride) > 0.5,
            obstacles=obstacles, Lx=4.0, Ly=4.0, Lz=4.0,
            charge_center=center, r_exp=0.15, bcs=bcs, face_specs=specs)


def synth_frame(t, r_front):
    """Spherical shock: high pressure inside r_front, decaying shell."""
    X, Y, Z = np.meshgrid(x_c, y_c, z_c, indexing='ij')
    d = np.sqrt((X - center[0])**2 + (Y - center[1])**2 + (Z - center[2])**2)
    p = P_AIR + 4e5 * np.exp(-((d - r_front) / 0.3)**2) \
        + 2e5 * (d < r_front)
    p[solid] = P_AIR
    return dict(p=decimate(p, stride), loads=extract_loads(p, specs),
                rho=decimate(1.2 + p / 3e5, stride))


print("\nS1: build scene off-screen")
pl = pv.Plotter(off_screen=True, window_size=(800, 600))
scene = BlastScene(pl, init)
check("grid dims match decimated solid",
      tuple(scene.grid.dimensions) == init['solid_dec'].shape)
check("5 layers", set(scene.layers) == {'plane1', 'plane2', 'iso',
                                        'loads', 'volume'})
check("hud placeholder", scene.frame is None)

print("\nS2: live frames")
for k, r in enumerate((0.3, 0.8, 1.4, 2.0)):
    scene.on_message(('frame', 1e-3 * (k + 1), synth_frame(1e-3, r)))
check("4 frames stored", len(scene.store) == 4)
check("follow-live tracks latest", scene.index == 3)
check("time is latest", abs(scene.t - 4e-3) < 1e-12)
check("ovp positive somewhere",
      float(scene.grid.point_data['p'].max()) > 100.0)
check("auto scale tracks frame", scene.cmax > 100.0)
check("plane1 actor present", 'cut_plane1' in pl.actors)
check("iso actor present", 'iso_surface' in pl.actors)
load_actors = [a for a in pl.actors if a.startswith('load_')]
check("load actors present", len(load_actors) == len(specs),
      f"{len(load_actors)}/{len(specs)}")

print("\nS2b: per-frame auto scale follows a decaying field")
big = scene.cmax
scene.on_message(('frame', 5e-3, {
    **synth_frame(5e-3, 2.0),
    'p': decimate(np.full(solid.shape, P_AIR + 5e4, np.float64), stride)}))
check("cmax came down with the field", scene.cmax < 0.3 * big,
      f"({big:.0f} -> {scene.cmax:.0f} kPa)")

print("\nS2c: slice data varies on every plane orientation")
X, Y, Z = np.meshgrid(x_c, y_c, z_c, indexing='ij')
scene.on_message(('frame', 6e-3,
                  dict(p=decimate(P_AIR + 1e5 * Z, stride))))
for axis, expect_flat in (('x', False), ('y', False), ('z', True)):
    scene.set_plane('plane1', axis, 0.5)
    pl.render()
    # planes are live VTK pipelines: inspect the cutter's output
    cutter = scene.layers['plane1']._cutter
    cutter.Update()
    mesh = pv.wrap(cutter.GetOutput())
    vals = np.asarray(mesh.point_data['p'])
    rng = float(vals.max() - vals.min())
    ok = (rng < 1.0) if expect_flat else (rng > 100.0)
    check(f"z-field on normal-{axis} plane "
          f"{'flat' if expect_flat else 'varies'}", ok,
          f"(range {rng:.1f} kPa)")

print("\nS3: toggles")
scene.on_message(('frame', 7e-3, synth_frame(7e-3, 1.4)))
scene.layers['volume'].set_visible(True)
check("volume actor added", 'volume_f' in pl.actors)
scene.layers['volume'].set_visible(False)
check("volume actor removed", 'volume_f' not in pl.actors)
scene.layers['iso'].set_visible(False)
check("iso hidden", not pl.actors['iso_surface'].visibility)
scene.layers['iso'].set_visible(True)
check("iso back", pl.actors['iso_surface'].visibility)
scene.layers['loads'].set_visible(False)
check("loads removed", not any(a.startswith('load_') for a in pl.actors))
scene.layers['loads'].set_visible(True)
scene._set_density_planes(True)
check("density plane drawn", 'cut_plane1' in pl.actors)
scene._set_density_planes(False)
scene.layers['plane2'].set_visible(True)
check("plane2 actor", 'cut_plane2' in pl.actors)

print("\nS3b: field switching / colour scale / presets")
scene.set_field('rho')
check("plane mapper bound to density", scene.field == 'rho'
      and pl.actors['cut_plane1'].mapper.array_name == 'rho'
      and float(scene.grid.point_data['rho'].max()) > 1.0)
check("rho available flag", scene.field_available('rho'))
check("imp not available (never sent)", not scene.field_available('imp'))
scene.set_field('p')
scene.set_clim(10.0, 300.0)
check("manual clim applied", (not scene.auto_scale)
      and scene.active_clim() == (10.0, 300.0))
scene.set_log_scale(True)
lo, hi = scene.active_clim()
check("log clamps min positive", lo > 0)
scene.set_log_scale(False)
scene._set_auto_scale(True)
check("auto scale back on", scene.auto_scale)
scene.set_plane_opacity('plane1', 0.5)
check("plane opacity set", scene.layers['plane1'].opacity == 0.5)
cam = tuple(pl.camera.position)
scene.view_preset('top')
check("view preset moved camera", tuple(pl.camera.position) != cam)
scene.set_parallel(True)
check("parallel projection on", pl.camera.GetParallelProjection() == 1)
scene.set_parallel(False)
scene.reset_view()

print("\nS3c: live display continues when history thinning rejects")
scene2_pl = pv.Plotter(off_screen=True, window_size=(300, 200))
scene2 = BlastScene(scene2_pl, init, embedded=True)
scene2.store._mem_cap = 1     # every append triggers thinning/rejects
for k in range(8):
    scene2.on_message(('frame', 1e-3 * (k + 1), synth_frame(0, 0.5)))
check("store thinned", len(scene2.store) < 8,
      f"(stored {len(scene2.store)})")
check("displayed time is the newest frame", abs(scene2.t - 8e-3) < 1e-12,
      f"(t={scene2.t*1e3:.0f} ms)")
scene2_pl.close()

print("\nS4: done -> playback")
scene.on_message(('done', 'shock arrived at an open boundary'))
check("done flag", scene.done and not scene.follow_live)
scene._scrub(0.0)
check("scrub to first", scene.index == 0)
check("scrub time", abs(scene.t - 1e-3) < 1e-12)
scene._toggle_play()
for _ in range(4):
    scene.tick()
check("play advances", scene.index > 0, f"index={scene.index}")
scene._toggle_play()

print("\nS5: render & screenshot")
out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'viz3d_scene_test.png')
img = pl.screenshot(out)
check("screenshot written", os.path.exists(out) and img is not None)
check("image not blank", float(np.asarray(img).std()) > 1.0)
pl.close()

print("\nS6: geometry-only preview scene")
pl3 = pv.Plotter(off_screen=True, window_size=(400, 300))
geo = dict(Lx=4.0, Ly=4.0, Lz=4.0, obstacles=obstacles,
           charge_center=center, r_draw=0.3, r_gauge=0.05, bcs=bcs,
           gauges=[(3.0, 3.0, 1.0)])
gs = GeometryScene(pl3)
gs.show(geo)
check("preview has domain/charge/gauge actors",
      all(k in pl3.actors for k in ('domain', 'charge', 'gauge0',
                                    'obstacle0', 'ground')))
cam = pl3.camera_position
gs.show(dict(geo, r_draw=0.5))          # same domain: camera preserved
check("camera preserved on update",
      tuple(map(tuple, pl3.camera_position)) == tuple(map(tuple, cam)))
gs.show(dict(geo, Lx=8.0))              # new extents: camera reset
img3 = pl3.screenshot(None, return_img=True)
check("preview renders", float(np.asarray(img3).std()) > 1.0)
pl3.close()

print("\n" + "=" * 50)
if FAIL:
    print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
    sys.exit(1)
print("All viz3d scene checks passed.")
