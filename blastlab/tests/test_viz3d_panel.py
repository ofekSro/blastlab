"""Embedded 3D panel test: real Tk + View3DPanel + off-screen pyvista.
Feeds synthetic frames through the same Feed3D path the GUI uses,
exercises every control callback and verifies rendered blits."""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import tkinter as tk
from blastlab.core.constants import P_AIR
from blastlab.core.grid import make_grid
from blastlab.core.bc import solid_mask_3d
from blastlab.gui.view3d_panel import View3DPanel, Feed3D

FAIL = []

def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


# ── synthetic scene (same as the scene test) ────────────────────────────────
grid = make_grid(4.0, 4.0, 4.0, 0.1)
x_c, y_c, z_c = grid['x_c'], grid['y_c'], grid['z_c']
obstacles = [(2.5, 3.0, 1.5, 2.5, 0.0, 1.0)]
solid = solid_mask_3d(x_c, y_c, z_c, obstacles)
center = (1.5, 2.0, 1.0)
scene_info = dict(x_c=x_c, y_c=y_c, z_c=z_c, dx=0.1, solid=solid,
                  obstacles=obstacles, Lx=4.0, Ly=4.0, Lz=4.0,
                  charge_center=center, r_exp=0.15,
                  bcs=dict(x_lo='open', x_hi='open', y_lo='open',
                           y_hi='open', z_lo='wall', z_hi='open'))

X, Y, Z = np.meshgrid(x_c, y_c, z_c, indexing='ij')
D = np.sqrt((X - center[0])**2 + (Y - center[1])**2 + (Z - center[2])**2)

def fields(r_front):
    p = P_AIR + 4e5 * np.exp(-((D - r_front) / 0.3)**2) + 2e5 * (D < r_front)
    p[solid] = P_AIR
    return dict(p=p, rho=1.2 + p / 3e5)


print("\nP1: construct panel in a real Tk root")
root = tk.Tk()
root.withdraw()
panel = View3DPanel(root, log_fn=print)
panel.pack()
root.update()
check("panel built, no scene yet", panel._scene is None)

print("\nP2: prepare_live + frames through Feed3D")
feed = panel.prepare_live(scene_info)
check("feed returned", isinstance(feed, Feed3D))
check("scene created embedded", panel._scene is not None
      and panel._scene.embedded)
check("no VTK plane widgets", panel._scene.layers['plane1'].widget is None)
for k, r in enumerate((0.4, 1.0, 1.6, 2.2)):
    panel.on_frame(1e-3 * (k + 1), feed.make_payload(fields(r)))
check("4 frames stored", len(panel._scene.store) == 4)
check("follow-live on latest", panel._scene.index == 3)
check("time slider range", float(panel.time_slider['to']) == 3.0)

print("\nP3: blit")
panel._blit()
root.update()
check("photo image set", panel._photo is not None)
w, h = panel._photo.width(), panel._photo.height()
check("photo has size", w > 100 and h > 100, f"{w}x{h}")
# successive blits must show NEW content (pyvista screenshots only
# render on their first call - the host renders explicitly per blit)
img_a = panel._plotter.screenshot(return_img=True).copy()
panel.on_frame(6e-3, feed.make_payload(fields(3.4)))
panel._blit()
img_b = panel._plotter.screenshot(return_img=True).copy()
check("blit re-renders (frames not stale)",
      not np.array_equal(img_a, img_b))
cam_a = img_b
panel._scene.orbit(40, 15)
panel._blit()
cam_b = panel._plotter.screenshot(return_img=True).copy()
check("camera moves show up in the blit",
      not np.array_equal(cam_a, cam_b))

print("\nP4: controls drive the scene")
pl = panel._scene.pl
panel._vars['volume'].set(True); panel._toggle_layer('volume')
check("volume on", 'volume_f' in pl.actors)
panel._vars['volume'].set(False); panel._toggle_layer('volume')
check("volume off", 'volume_f' not in pl.actors)
panel._vars['iso'].set(False); panel._toggle_layer('iso')
check("iso off", not pl.actors['iso_surface'].visibility)
panel._vars['iso'].set(True); panel._toggle_layer('iso')
check("iso on", pl.actors['iso_surface'].visibility)
panel._vars['plane1_axis'].set('x')
panel._vars['plane1_pos'].set(0.25)
panel._plane_changed('plane1')
o = panel._scene.layers['plane1'].origin
n = panel._scene.layers['plane1'].normal
check("plane1 repositioned", abs(o[0] - 1.0) < 1e-9 and n == (1.0, 0.0, 0.0),
      f"origin={o} normal={n}")

panel._vars['mesh'].set(True); panel._toggle_layer('mesh')
check("show mesh on (plane1 edges)", 'mesh_plane1' in pl.actors)
panel._vars['mesh'].set(False); panel._toggle_layer('mesh')
check("show mesh off", 'mesh_plane1' not in pl.actors)

print("\nP4b: VIPER-style controls (fields / scale / planes / views)")
check("6 cross-section planes",
      all(f'plane{k}' in panel._scene.layers for k in range(1, 7)))
panel._vars['plane3'].set(True); panel._toggle_layer('plane3')
check("plane3 on", 'cut_plane3' in pl.actors)
panel._vars['plane3_op'].set(50); panel._opacity_changed('plane3')
check("plane3 opacity", panel._scene.layers['plane3'].opacity == 0.5)
panel._vars['plane3'].set(False); panel._toggle_layer('plane3')
panel._vars['field'].set('rho'); panel._field_changed()
check("field switched to density", panel._scene.field == 'rho')
check("density radio enabled",
      str(panel._field_btns['rho']['state']) != 'disabled')
check("impulse radio disabled (not in payload)",
      str(panel._field_btns['imp']['state']) == 'disabled')
panel._vars['field'].set('p'); panel._field_changed()
panel._vars['vmin'].set('5'); panel._vars['vmax'].set('250')
panel._clim_changed()
check("manual clim + auto off",
      panel._scene.active_clim() == (5.0, 250.0)
      and not panel._vars['auto_scale'].get())
panel._vars['log'].set(True); panel._log_changed()
check("log scale on, min clamped > 0",
      panel._scene.log_scale and panel._scene.active_clim()[0] > 0)
panel._vars['log'].set(False); panel._log_changed()
panel._vars['auto_scale'].set(True); panel._auto_changed()
cam0 = tuple(pl.camera.position)
panel._view_preset('top')
check("view preset applied", tuple(pl.camera.position) != cam0)
panel._vars['parallel'].set(True); panel._parallel_changed()
check("parallel projection", pl.camera.GetParallelProjection() == 1)
panel._vars['parallel'].set(False); panel._parallel_changed()

print("\nP5: camera ops change the view")
cam_before = tuple(pl.camera.position)
panel._scene.orbit(30, 10)
check("orbit moved camera", tuple(pl.camera.position) != cam_before)
cam_before = tuple(pl.camera.position)
panel._scene.pan(0.1, 0.05)
check("pan moved camera", tuple(pl.camera.position) != cam_before)
cam_before = tuple(pl.camera.position)
panel._scene.zoom_view(1.3)
check("zoom moved camera", tuple(pl.camera.position) != cam_before)
panel._reset_view()

print("\nP6: done -> scrub/play")
panel.on_done('shock arrived at an open boundary')
check("done + follow off", panel._scene.done
      and not panel._vars['follow'].get())
panel._time_moved('0')
check("scrub to first", panel._scene.index == 0)
panel._toggle_play()
check("playing", panel._playing)
root.update()
panel._play_tick()
check("play advanced", panel._scene.index > 0)
panel._toggle_play()

print("\nP7: reuse for a second result (fresh scene)")
feed2 = panel.prepare_live(scene_info)
check("scene rebuilt", len(panel._scene.store) == 0)
panel.on_frame(1e-3, feed2.make_payload(fields(0.8)))
panel._blit()
check("second scene renders", panel._photo is not None)

print("\nP8: adopt_feed (auto-attach path) + setup preview panel")
from blastlab.gui.view3d_panel import Feed3D as _F
feed3 = _F(scene_info)
check("adopt_feed builds scene", panel.adopt_feed(feed3)
      and len(panel._scene.store) == 0)
panel.on_frame(1e-3, feed3.make_payload(fields(0.6)))
check("adopted feed streams", len(panel._scene.store) == 1)

from blastlab.core.case import Case3D
from blastlab.gui.preview_panel import Preview3DPanel, case_geometry
case = Case3D(Lx=4.0, Ly=4.0, Lz=4.0, cell_size_m=0.1, charge=5.0,
              center=(2.0, 2.0, 1.0), obstacles=[(2.5, 3.0, 1.5,
                                                  2.5, 0.0, 1.0)],
              gauges=[(3.0, 3.0, 1.0)], charge_resolution='smear')
geo = case_geometry(case)
check("smear preview ball >= 2 cells",
      abs(geo['r_draw'] - 0.2) < 1e-12, f"r_draw={geo['r_draw']}")
prev = Preview3DPanel(root)
prev.pack()
root.update()
prev.show_case(case)
prev._blit()
check("preview blits", prev._photo is not None)
prev.show_case(Case3D(Lx=6.0))     # domain change re-renders
prev.clear()
check("preview cleared", prev._scene is None)

print("\nP9: 2D setup preview (matplotlib)")
from blastlab.core.case import Case2D
from blastlab.gui.preview_panel import Preview2DPanel
p2 = Preview2DPanel(root)
p2.pack()
root.update()
c2 = Case2D(Lx=4.0, Ly=6.0, charge=1.0, center=(0.0, 3.0),
            obstacles=[(1.0, 1.5, 0.5, 2.0)], gauges=[(2.0, 3.0)])
p2.show_case(c2)
root.update()
ax = p2._ax
check("axisym labels + extents", ax.get_xlabel() == 'r [m]'
      and ax.get_ylim()[1] > 6.0)
check("obstacle + charge patches drawn", len(ax.patches) == 2)
check("gauge marker drawn",
      any(len(l.get_xdata()) == 1 for l in ax.lines))
c2p = Case2D(geometry='planar', Lx=4.0, Ly=6.0, init_mode='profile1d',
             profile_file_in='x.txt', center=(2.0, 3.0))
p2.show_case(c2p)
check("planar remap: x label + origin marker",
      ax.get_xlabel() == 'x [m]' and len(ax.patches) == 0)

root.destroy()

print("\n" + "=" * 50)
if FAIL:
    print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
    sys.exit(1)
print("All viz3d panel checks passed.")
