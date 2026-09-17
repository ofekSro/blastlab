"""Off-screen smoke test of the 3D viewer scene (requires pyvista).

Builds a BlastScene on an off-screen plotter, feeds synthetic expanding-
blast frames through on_message, exercises every layer toggle, the
field/colour-scale controls, cross-section planes, view presets and the
playback path, and screenshots the result. No window is opened.
"""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

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
bcs = dict(x_lo='terminate', x_hi='terminate',
           y_lo='terminate', y_hi='terminate',
           z_lo='reflect', z_hi='terminate')
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
check("7 layers", set(scene.layers) == {'plane1', 'plane2', 'iso',
                                        'loads', 'volume', 'mesh',
                                        'sampled'})
# the sampled plane is the one layer that draws data the frame store
# does not have: a blastFoam run samples its burst plane far more often
# than it writes a full field, and this layer is where that lands
check("the sampled plane starts empty",
      scene.layers['sampled'].t is None)
check("hud placeholder", scene.frame is None)

print("\nS2: live frames")
for k, r in enumerate((0.3, 0.8, 1.4, 2.0)):
    scene.on_message(('frame', 1e-3 * (k + 1), synth_frame(1e-3, r), False))
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
    'p': decimate(np.full(solid.shape, P_AIR + 5e4, np.float64), stride)},
    False))
check("cmax came down with the field", scene.cmax < 0.3 * big,
      f"({big:.0f} -> {scene.cmax:.0f} kPa)")

print("\nS2c: slice data varies on every plane orientation")
X, Y, Z = np.meshgrid(x_c, y_c, z_c, indexing='ij')
scene.on_message(('frame', 6e-3,
                  dict(p=decimate(P_AIR + 1e5 * Z, stride)), False))
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
scene.on_message(('frame', 7e-3, synth_frame(7e-3, 1.4), True))
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
check("plane1 drawn", 'cut_plane1' in pl.actors)

print("\nS3-B19: colour range reaches every layer")
from blastlab.viz3d.viewer import (LOADS_TITLE, LOADS_BAR_KEY,
                                   LOADS_CAPTION)
# the bar lies flat along the bottom and is untitled: VTK printed a
# horizontal bar's title over its own tick labels, so the caption is a
# separate viewport text actor (QA-17)
check("loads carry their own scalar bar", LOADS_BAR_KEY in pl.scalar_bars,
      str(list(pl.scalar_bars.keys())))
check("loads bar is captioned", LOADS_CAPTION in pl.actors
      and LOADS_TITLE.startswith('Surface loads'))
load_actor = next(a for n, a in pl.actors.items() if n.startswith('load_'))
own = tuple(load_actor.mapper.scalar_range)
scene.set_field('rho')
check("switching the field drops the previous field's scalar bar",
      'Overpressure [kPa]' not in pl.scalar_bars and 'Density [kg/m3]' in pl.scalar_bars,
      str(list(pl.scalar_bars.keys())))
check("Density active: loads keep an overpressure range, not the density clim",
      tuple(load_actor.mapper.scalar_range) == own
      and own[1] < 1e4 and own[1] > 0.0, f"{load_actor.mapper.scalar_range} vs {own}")
scene.layers['volume'].set_visible(True)
scene.set_clim(1.0, 2.0)
vol = pl.actors['volume_f']
check("manual Min/Max reaches the volume", tuple(vol.mapper.scalar_range) == (1.0, 2.0),
      str(vol.mapper.scalar_range))
check("manual Min/Max on a density field leaves the loads alone",
      tuple(load_actor.mapper.scalar_range) == own, str(load_actor.mapper.scalar_range))
scene.set_field('p')
scene.set_clim(0.0, 250.0)
check("manual overpressure Min/Max reaches the loads",
      tuple(load_actor.mapper.scalar_range) == (0.0, 250.0), str(load_actor.mapper.scalar_range))
scene._set_auto_scale(True)
check("auto scale restores the loads' own range",
      abs(load_actor.mapper.scalar_range[1] - own[1]) < 1e-6 * max(own[1], 1),
      str(load_actor.mapper.scalar_range))
scene.layers['volume'].set_visible(False)
scene.layers['loads'].set_visible(False)
check("hiding loads removes their scalar bar", LOADS_TITLE not in pl.scalar_bars)
scene.layers['loads'].set_visible(True)
scene.layers['plane2'].set_visible(True)
check("plane2 actor", 'cut_plane2' in pl.actors)

print("\nS3a: mesh-edge layer (N15 show mesh)")
from blastlab.core import refine as _refine
from blastlab.viz3d.viewer import mesh_polydata
check("mesh layer off by default", 'mesh_edges' not in pl.actors)
scene.layers['plane1'].set_visible(True)      # known plane state for the
scene.layers['plane2'].set_visible(False)     # line-count comparisons below
scene.layers['mesh'].set_visible(True)
check("one merged mesh actor", 'mesh_edges' in pl.actors
      and not any(k.startswith('mesh_plane') for k in pl.actors),
      str([k for k in pl.actors if 'mesh' in k]))
poly = pl.actors['mesh_edges'].mapper.dataset
axes = (init['x_c'], init['y_c'], init['z_c'])
want = mesh_polydata(axes, init['dx'], None,
                     [scene.layers['mesh']._plane_geom(scene.layers['plane1'])])
check("edges cover the six boundary faces + the visible plane",
      poly.n_lines == want.n_lines and poly.n_lines > 12,
      f"{poly.n_lines} vs {want.n_lines}")
xs = poly.points[:, 0]
check("edges span the whole domain, not one plane",
      xs.min() < 0.01 and xs.max() > 3.99, f"x range {xs.min():.2f}..{xs.max():.2f}")
before = poly.n_lines
scene.layers['plane2'].set_visible(True)
check("a second visible plane adds its grid",
      pl.actors['mesh_edges'].mapper.dataset.n_lines > before)
scene.layers['plane2'].set_visible(False)
check("hiding it removes those lines again",
      pl.actors['mesh_edges'].mapper.dataset.n_lines == before)
scene.on_message(('frame', 5e-3, synth_frame(5e-3, 2.2), False))
check("frames keep the edges", 'mesh_edges' in pl.actors)
scene.layers['mesh'].set_visible(False)
check("mesh layer off removes the actor", 'mesh_edges' not in pl.actors)
many = _refine.mesh_segments_2d(None, np.linspace(0, 1, 401),
                                np.linspace(0, 1, 401), max_lines=40)
check("fine uniform grid thinned to the line budget", len(many) <= 84,
      str(len(many)))
lev = np.zeros((40, 40), dtype=np.int8)
lev[:10, :10] = 1
thin = _refine.mesh_segments_2d(_refine.fine_src(lev, 1),
                                np.linspace(0, 4, 41),
                                np.linspace(0, 4, 41), max_lines=8)
inner = [sg for sg in thin
         if abs(sg[0][0] - sg[1][0]) < 1e-9 and 0.05 < sg[0][0] < 0.95]
check("refinement-block boundaries survive thinning", len(inner) > 0,
      str(len(inner)))
lev3 = np.zeros((40, 40, 40), dtype=np.int8)
lev3[:10, :10, :10] = 1
init_r = dict(init, refine=dict(levels=lev3, lmax=1, dx_base=0.2, zones=[]))
pl_r = pv.Plotter(off_screen=True, window_size=(400, 300))
scene_r = BlastScene(pl_r, init_r)
scene_r.set_plane('plane1', 'z', 0.1)
scene_r.layers['mesh'].set_visible(True)
check("refined scene draws its mesh", 'mesh_edges' in pl_r.actors
      and pl_r.actors['mesh_edges'].mapper.dataset.n_lines > 0)
pl_r.close()

print("\nS3a2: dynamic AMR - the overlay follows each frame's level map (N16)")
init_a = dict(init, refine=dict(levels=np.zeros((40, 40, 40), dtype=np.int8),
                                lmax=1, dx_base=0.2, zones=[], amr=1,
                                display_level=1))
pl_a = pv.Plotter(off_screen=True, window_size=(400, 300))
scene_a = BlastScene(pl_a, init_a)
scene_a.set_plane('plane1', 'z', 0.1)
scene_a.layers['plane2'].set_visible(False)
scene_a.layers['mesh'].set_visible(True)
n_rec = pl_a.actors['mesh_edges'].mapper.dataset.n_lines
lvA = np.zeros((40, 40, 40), dtype=np.int8)
lvA[:10, :10, :10] = 1
scene_a.on_message(('frame', 1e-3, dict(synth_frame(1e-3, 0.5), levels=lvA), False))
n_a = pl_a.actors['mesh_edges'].mapper.dataset.n_lines
lvB = np.zeros((40, 40, 40), dtype=np.int8)
lvB[:24, :24, :4] = 1
scene_a.on_message(('frame', 2e-3, dict(synth_frame(2e-3, 0.7), levels=lvB), False))
n_b = pl_a.actors['mesh_edges'].mapper.dataset.n_lines
check("AMR frames rebuild the overlay from their own level maps",
      n_a != n_rec and n_b != n_a, f"{n_rec} {n_a} {n_b}")
built = scene_a.layers['mesh']._built
scene_a.layers['plane1'].refresh()
check("same frame, same planes: cached (no rebuild)",
      scene_a.layers['mesh']._built == built)
scene_a.on_message(('frame', 3e-3, synth_frame(3e-3, 0.9), False))
check("a frame without levels falls back to the record's map",
      pl_a.actors['mesh_edges'].mapper.dataset.n_lines == n_rec)
scene_a.show_frame(1)
check("scrubbing back to an AMR frame restores its overlay",
      pl_a.actors['mesh_edges'].mapper.dataset.n_lines == n_b)
pl_a.close()
check("static scene: frames never change the built key",
      scene.layers['mesh']._built is None or scene.layers['mesh']._built[1] is None)

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
scene2.store._mem_cap = 1     # every append triggers thinning
for k in range(8):
    scene2.on_message(('frame', 1e-3 * (k + 1), synth_frame(0, 0.5), False))
check("store thinned", len(scene2.store) < 8,
      f"(stored {len(scene2.store)})")
check("displayed time is the newest frame", abs(scene2.t - 8e-3) < 1e-12,
      f"(t={scene2.t*1e3:.0f} ms)")

# B4/B20: the run's actual final frame is tagged `final=True` in the
# message (never inferred from `scene2.done`, which is still False here)
# and must survive being the newest frame under active thinning.
scene2.on_message(('frame', 9e-3, synth_frame(0, 0.5), True))
check("final-tagged frame stored despite aggressive thinning",
      abs(scene2.store.times[-1] - 9e-3) < 1e-12,
      f"(stored last t={scene2.store.times[-1]*1e3:.0f} ms)")
check("final frame did not itself flip scene2.done",
      not scene2.done)
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

print("\nA8: frames never block the sender (shared-memory ring)")
# The old bounded queue needed a frame dropped to let 'done' through;
# frames now go through a two-slot ring (latest wins) and control
# messages through a separate pipe, so a stalled viewer can never hold
# the solver: a burst of writes with nobody reading returns at once and
# the newest frame is the one a late reader gets.
import time as _time
from blastlab.viz3d.protocol import FrameLayout, SharedFrameRing
ring = SharedFrameRing(FrameLayout.from_init(init))
burst = [synth_frame(k * 1e-4, 0.3 + 0.03 * k) for k in range(5)]
t0 = _time.perf_counter()
for k in range(50):
    ring.write(k * 1e-4, burst[k % len(burst)])
dt_burst = _time.perf_counter() - t0
got = ring.read(0)
check("50 unread frames never block the sender", dt_burst < 2.0,
      f"{dt_burst*1e3:.0f} ms")
check("a late reader gets the newest frame", got is not None
      and got[0] == 50 and abs(got[1] - 49e-4) < 1e-12)
ring.close(unlink=True)

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

# G8/QA-21: a multi-charge blastFoam case must not look single-charge,
# and a detonation point must not look like one more charge
gs.show(dict(geo, charges=[(1.0, 1.0, 0.5, 0.2), (3.0, 1.0, 0.5, 0.1)],
             det_points=[(1.0, 1.0, 0.5), (3.0, 1.0, 0.5)]))
check("extra charges get their own actors",
      all(k in pl3.actors for k in ('xcharge0', 'xcharge1')),
      str([k for k in pl3.actors if k.startswith('xcharge')]))
check("detonation points get their own actors",
      all(k in pl3.actors for k in ('det0', 'det1')))
check("a detonation point is a diamond, not another ball",
      pl3.actors['det0'].mapper.dataset.n_points
      < pl3.actors['xcharge0'].mapper.dataset.n_points,
      f"{pl3.actors['det0'].mapper.dataset.n_points} vs "
      f"{pl3.actors['xcharge0'].mapper.dataset.n_points}")
gs.show(geo)                            # back to a plain case
check("they go away with the case that had them",
      not any(k.startswith(('xcharge', 'det')) for k in pl3.actors))
pl3.close()

print("\n" + "=" * 50)
if FAIL:
    print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
    sys.exit(1)
print("All viz3d scene checks passed.")
