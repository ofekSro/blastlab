"""The interactive 3D viewer scene (pyvista) and its standalone window.

This is the only blastlab module that imports pyvista. `viewer_main`
is the multiprocessing spawn target: it builds the scene from the
'init' message, then drains ('frame', t, payload, final) messages on a
render timer - `final` marks the run's last frame so FrameStore.append
is told to keep it even mid-thinning-stride, never inferred from the
viewer's own 'done' state. While the run is live the view follows the
newest frame; after ('done', reason) the time slider scrubs the
retained history.

Scene layers (each toggled by an on-screen control):
  plane1..planeN    : cross-section planes coloured by the active field
  Isosurface        : shock front at a fraction of the frame's peak
  Surface loads     : adjacent-fluid pressure on box faces + ground
  Volume            : semi-transparent cloud of the active field

`GeometryScene` renders just the static scenery (domain, obstacles,
charge, gauges) for the GUI's live setup preview - no fields needed.
"""

import os
import time

import numpy as np

from ..core import refine
from ..core.refine import LEVEL_COLORS
from ..core.bc import normalize_bc as _normalize_bc
from ..core.constants import P_AIR
from .sampling import FRAME_MEM_CAP, FrameStore

CMAP = 'turbo'
BG_BOTTOM, BG_TOP = '#10131a', '#2a2f3a'
CHECK_ON, CHECK_OFF = '#4fc3f7', '#37474f'
OVP_TITLE = 'Overpressure [kPa]'
RHO_TITLE = 'Density [kg/m3]'

#: Selectable display fields: payload key -> scalar-bar title and
#: How many decades a logarithmic colour scale spans below the peak.
#:
#: Four was not enough, measured on a real live 3D run. A 2 kg charge
#: puts 2.8e6 kPa of overpressure in the products while the air around
#: them is at tens of kPa - a dynamic range of 27,608 - so a four-decade
#: floor (peak/1e4 = 278 kPa) still buried the entire shocked field at
#: the bottom of the bar. At six the shock front lands at 81-93 % of the
#: bar across every frame of that run, 10 kPa gets 15 % and 100 kPa 31 %.
#:
#: This is what a logarithmic scale is for, and it is why the live view
#: uses one for pressure by default: every rule that tries to pick a
#: LINEAR cap was measured and rejected. A percentile over the whole
#: domain is ambient (99.9 % of the cells are undisturbed air); a
#: percentile over only the disturbed cells is still products (the ratio
#: peak/p99.5 came out 1.0-1.4, so the clip never engaged, and lower
#: percentiles saturated the shock front itself at up to 1237 % of the
#: bar); and splitting products from air by a multiple of the median
#: moved the answer by 100x when that multiple went from 10 to 1000.
LOG_DECADES = 6.0

#: whether the stored display values are overpressure in kPa.
FIELDS = {
    'p':      dict(title=OVP_TITLE,                  ovp=True,
                   label='Pressure'),
    'rho':    dict(title=RHO_TITLE,                  ovp=False,
                   label='Density'),
    # P2-2: blastFoam does not hand back internal energy, so the foam
    # backend derives one as the ideal-gas p/((gamma-1) rho) - which is
    # simply wrong inside the products, where the EOS is JWL. The number
    # is still useful as a picture of where the hot gas is, so it stays,
    # but a run that computed it that way says so (see `approx_title`).
    # The native solvers carry the real solved e and keep the plain title.
    'e':      dict(title='Energy [J/kg]',            ovp=False,
                   label='Energy',
                   approx_title='Energy [J/kg] (approx)'),
    'p_peak': dict(title='Peak overpressure [kPa]',  ovp=True,
                   label='Peak overpressure'),
    #: net (not positive-phase) overpressure impulse - see README.md
    'imp':    dict(title='Net overpressure impulse [Pa·s]', ovp=False,
                   label='Net ovp impulse'),
}

#: Camera presets: view direction (towards the domain) and up vector.
VIEW_PRESETS = {
    'top':    ((0, 0, 1),  (0, 1, 0)),
    'bottom': ((0, 0, -1), (0, 1, 0)),
    'front':  ((0, -1, 0), (0, 0, 1)),
    'back':   ((0, 1, 0),  (0, 0, 1)),
    'left':   ((-1, 0, 0), (0, 0, 1)),
    'right':  ((1, 0, 0),  (0, 0, 1)),
}


def _ovp_kpa(p):
    return (np.asarray(p, np.float32) - np.float32(P_AIR)) / np.float32(1e3)


def _set_text(actor, s):
    try:
        actor.input = s
    except AttributeError:
        actor.SetInput(s)


def mesh_edges_polydata(segments, axis, pos):
    """pyvista PolyData of cell-edge segments ((N, 2, 2) in-plane
    coordinates) lying on the plane normal to `axis` at `pos`."""
    import pyvista as pv
    seg = np.asarray(segments, dtype=float).reshape(-1, 2, 2)
    n = len(seg)
    pts = np.zeros((2 * n, 3))
    uv = [a for a in range(3) if a != axis]
    pts[:, uv[0]] = seg[:, :, 0].ravel()
    pts[:, uv[1]] = seg[:, :, 1].ravel()
    pts[:, axis] = pos
    lines = np.column_stack([np.full(n, 2), np.arange(0, 2 * n, 2),
                             np.arange(1, 2 * n, 2)]).ravel()
    poly = pv.PolyData(pts)
    poly.lines = lines
    return poly


#: cell-edge overlay style: muted and translucent, so a fine grid reads
#: as a mesh instead of a white sheet
MESH_COLOR = '#8b95a3'
MESH_OPACITY = 0.45
#: full-span grid lines drawn per direction on one face (see
#: core.refine.mesh_segments_2d) - refinement boundaries are always kept
MESH_MAX_LINES = 40


def mesh_polydata(axes_c, dx, refine_rec=None, planes=(), boundary=True,
                  max_lines=MESH_MAX_LINES):
    """Cell edges over the WHOLE domain: the grid on each of the six
    boundary faces plus one grid per requested cut plane, merged into a
    single PolyData.

    `axes_c`: full-resolution (x_c, y_c, z_c); `dx`: their spacing;
    `refine_rec`: a Result/scene `refine` record (levels/lmax) for the
    true cells of a locally refined run, or None for a uniform mesh;
    `planes`: [(axis, fine index, position)]."""
    import pyvista as pv
    from ..core import refine
    axes = [np.asarray(a, dtype=float) for a in axes_c]
    faces = [np.concatenate(([a[0] - dx / 2], a + dx / 2)) for a in axes]
    want = list(planes)
    if boundary:
        for ax in range(3):
            for k in (0, len(axes[ax]) - 1):
                want.append((ax, k, float(faces[ax][k + (k > 0)])))
    parts = []
    for ax, k, pos in want:
        src = None
        if refine_rec is not None:
            src = refine.slice_src(refine_rec['levels'], refine_rec['lmax'],
                                   ax, int(k))
        uv = [a for a in range(3) if a != ax]
        segs = refine.mesh_segments_2d(src, faces[uv[0]], faces[uv[1]],
                                       max_lines=max_lines)
        if len(segs):
            parts.append(mesh_edges_polydata(segs, ax, float(pos)))
    if not parts:
        return None
    return parts[0].merge(parts[1:]) if len(parts) > 1 else parts[0]


def add_static_scenery(pl, geo):
    """Domain outline, obstacles, charge ball, ground tint and gauge
    markers. `geo`: Lx/Ly/Lz, obstacles, charge_center, r_draw, bcs and
    optionally gauges; a `cyl` entry (revolved axisymmetric domain)
    swaps the box outline/ground for a cylinder rim and disc, and
    `rings` ((r0, r1, z0, z1) rectangles of the source axisymmetric
    plane) render as revolved annular solids. Shared by BlastScene and
    the setup preview."""
    import pyvista as pv
    cyl = geo.get('cyl')
    if cyl is not None:
        cx, cy, R = float(cyl['cx']), float(cyl['cy']), float(cyl['R'])
        th = np.linspace(0.0, 2.0 * np.pi, 97)
        ring = np.column_stack([cx + R * np.cos(th),
                                cy + R * np.sin(th),
                                np.zeros_like(th)])
        parts = []
        for z in (0.0, float(geo['Lz'])):
            pts = ring.copy()
            pts[:, 2] = z
            parts.append(pv.lines_from_points(pts))
        for a in (0.0, 0.5 * np.pi, np.pi, 1.5 * np.pi):
            px, py = cx + R * np.cos(a), cy + R * np.sin(a)
            parts.append(pv.Line((px, py, 0.0),
                                 (px, py, float(geo['Lz']))))
        pl.add_mesh(parts[0].merge(parts[1:]), color='#6b7280',
                    line_width=1, opacity=0.5, name='domain')
        if _normalize_bc((geo.get('bcs') or {}).get('z_lo')) == 'reflect':
            pl.add_mesh(pv.Disc(center=(cx, cy, 0.0), inner=0.0,
                                outer=R, normal=(0, 0, 1), c_res=96),
                        color='#39424e', opacity=0.35, name='ground')
        # obstacle rectangles of the (r, z) plane, revolved: an
        # annular ring (r0 = 0 degenerates to a full cylinder)
        for k, (r0, r1, zlo, zhi) in enumerate(geo.get('rings') or []):
            disc = pv.Disc(center=(cx, cy, float(zlo)),
                           inner=float(r0), outer=float(r1),
                           normal=(0, 0, 1), c_res=96)
            pl.add_mesh(disc.extrude((0, 0, float(zhi) - float(zlo)),
                                     capping=True),
                        color='#8d99ae', opacity=1.0,
                        smooth_shading=False, name=f'ring{k}')
    else:
        bounds = (0.0, geo['Lx'], 0.0, geo['Ly'], 0.0, geo['Lz'])
        pl.add_mesh(pv.Box(bounds=bounds).extract_all_edges(),
                    color='#6b7280', line_width=1, opacity=0.5,
                    name='domain')
        if _normalize_bc((geo.get('bcs') or {}).get('z_lo')) == 'reflect':
            ground = pv.Plane(center=(geo['Lx'] / 2, geo['Ly'] / 2, 0.0),
                              direction=(0, 0, 1),
                              i_size=geo['Lx'], j_size=geo['Ly'])
            pl.add_mesh(ground, color='#39424e', opacity=0.35,
                        name='ground')
    for k, box in enumerate(geo.get('obstacles') or []):
        pl.add_mesh(pv.Box(bounds=box), color='#8d99ae',
                    opacity=1.0, smooth_shading=False,
                    name=f'obstacle{k}')
    # refinement zones: wireframe boxes coloured by level; the predicted
    # mesh on the live-slice plane when the preview asks for it
    for k, z in enumerate(geo.get('zones') or []):
        lv = int(round(float(z[-1])))
        col = LEVEL_COLORS[min(max(lv, 1), len(LEVEL_COLORS)) - 1]
        pl.add_mesh(pv.Box(bounds=tuple(float(v) for v in z[:6]))
                    .extract_all_edges(), color=col, line_width=1.5,
                    opacity=0.9, name=f'zone{k}')
    mesh = geo.get('mesh')
    if mesh:
        poly = mesh_polydata(mesh['axes'], mesh['dx'],
                             mesh.get('refine'), mesh.get('planes', ()))
        if poly is not None:
            pl.add_mesh(poly, color=MESH_COLOR, line_width=1,
                        opacity=MESH_OPACITY, name='mesh_preview')
    cx, cy, cz = geo['charge_center']
    pl.add_mesh(pv.Sphere(radius=geo['r_draw'], center=(cx, cy, cz)),
                color='#ff8f00', opacity=0.85, name='charge')
    # blastFoam multi-charge cases: the preview drew only the primary
    # charge, so a two-charge case looked single-charge (ROADMAP G8)
    for k, ch in enumerate(geo.get('charges') or []):
        ex, ey, ez, er = (list(ch) + [geo['r_draw']])[:4]
        pl.add_mesh(pv.Sphere(radius=max(float(er), geo['r_gauge']),
                              center=(float(ex), float(ey), float(ez))),
                    color='#ffb74d', opacity=0.85, name=f'xcharge{k}')
    for k, dp in enumerate(geo.get('det_points') or []):
        px, py, pz = (list(dp) + [0.0, 0.0, 0.0])[:3]
        r = 0.8 * geo['r_gauge']
        ctr = (float(px), float(py), float(pz))
        # a diamond, so a detonation point never reads as one more
        # (spherical) charge or gauge
        try:
            marker = pv.Octahedron(radius=r, center=ctr)
        except Exception:
            marker = pv.Sphere(radius=r, center=ctr,
                               theta_resolution=8, phi_resolution=8)
        pl.add_mesh(marker, color='#e5484d', name=f'det{k}')
    for k, g in enumerate(geo.get('gauges') or []):
        pl.add_mesh(pv.Sphere(radius=geo['r_gauge'], center=tuple(g)),
                    color='#4fc3f7', name=f'gauge{k}')


class _CameraOps:
    """Mouse-driven camera control shared by the scene classes; the
    embedded Tk hosts call these instead of VTK interaction."""

    def orbit(self, d_azimuth, d_elevation):
        cam = self.pl.camera
        cam.Azimuth(float(d_azimuth))
        cam.Elevation(float(d_elevation))
        cam.OrthogonalizeViewUp()
        self.pl.renderer.ResetCameraClippingRange()

    def pan(self, dx_frac, dy_frac):
        """Shift the view by fractions of the view height (mouse drag)."""
        cam = self.pl.camera
        pos = np.array(cam.position)
        fp = np.array(cam.focal_point)
        up = np.array(cam.up)
        fwd = fp - pos
        dist = np.linalg.norm(fwd)
        right = np.cross(fwd / max(dist, 1e-12), up)
        shift = (-dx_frac * right + dy_frac * up) * dist
        cam.position = tuple(pos + shift)
        cam.focal_point = tuple(fp + shift)
        self.pl.renderer.ResetCameraClippingRange()

    def zoom_view(self, factor):
        self.pl.camera.Dolly(float(factor))
        self.pl.renderer.ResetCameraClippingRange()

    def reset_view(self):
        self.pl.camera_position = 'iso'
        self.pl.reset_camera()

    def view_preset(self, name):
        """Axis-aligned view: 'top'/'bottom'/'front'/'back'/'left'/'right'."""
        direction, up = VIEW_PRESETS[name]
        c = np.array(self._domain_extent()) / 2.0
        dist = 2.4 * float(np.linalg.norm(c) or 1.0)
        self.pl.camera_position = [tuple(c + np.array(direction) * dist),
                                   tuple(c), up]
        self.pl.reset_camera()

    def set_parallel(self, on):
        self.pl.camera.SetParallelProjection(bool(on))
        self.pl.renderer.ResetCameraClippingRange()


class _Layer:
    """A toggleable piece of the scene."""
    visible = False

    def set_visible(self, on):
        self.visible = bool(on)
        self.refresh()

    def refresh(self):
        """Rebuild/update the layer's actors for the current frame."""


def field_title(scene, key):
    """Scalar-bar title for `key` in this scene. P2-2: the energy field
    of a blastFoam run is an ideal-gas stand-in (the solver returns no
    internal energy), so it is labelled approximate; everything else, and
    every native run, keeps its plain title."""
    f = FIELDS[key]
    if getattr(scene, 'e_approx', False) and 'approx_title' in f:
        return f['approx_title']
    return f['title']


class BlastScene(_CameraOps):
    """The 3D scene. Two hosts use it:
    - the standalone window (CLI): VTK checkbox/slider/plane widgets,
      driven by `viewer_main` below (2 widget planes);
    - the embedded GUI panel (`gui/view3d_panel.py`): `embedded=True`
      skips all VTK widgets; Tk controls call the setter methods and the
      panel blits off-screen renders into the window (6 planes)."""

    def __init__(self, plotter, init, embedded=False, n_planes=2):
        import pyvista as pv
        self.pv = pv
        self.pl = plotter
        self.embedded = embedded
        self.init = init
        self.store = FrameStore(
            mem_cap=init.get('frame_mem_cap') or FRAME_MEM_CAP)
        self.frame = None            # current frame payload
        #: P2-2: this run's energy field is the foam backend's ideal-gas
        #: stand-in, not a solved one - the scalar bar says so
        self.e_approx = init.get('solver') == 'blastfoam'
        self.t = 0.0
        self.index = -1
        self.done = False
        self.stop_reason = ''
        #: extra HUD line while a caller streams frames in (playback of a
        #: finished result is fed one snapshot per Tk tick, so the window
        #: stays responsive and says how far it has got)
        self.loading = ''
        self.follow_live = True
        self.playing = False
        self._play_skip = 0
        self.field = 'p'             # active display field (FIELDS key)
        self.have = {k: False for k in FIELDS}
        self.auto_scale = True
        self.log_scale = False
        self.vmin = 0.0              # manual colour range (active field)
        self.cmax = 10.0
        self.iso_frac = 0.10

        dx = init['dx'] * init['stride']
        shape = init['solid_dec'].shape
        self.grid = pv.ImageData(
            dimensions=shape,
            spacing=(dx, dx, dx),
            origin=(float(init['x_c'][0]), float(init['y_c'][0]),
                    float(init['z_c'][0])))
        n = int(np.prod(shape))
        for key in FIELDS:
            self.grid.point_data[key] = np.zeros(n, np.float32)
        self._stale = set()          # frame fields not yet uploaded

        self._static_scene()
        use_widget = not embedded
        self.layers = {}
        defaults = {1: ('y', True), 2: ('z', False)}
        for k in range(1, max(2, n_planes) + 1):
            axis, on = defaults.get(k, ('x', False))
            self.layers[f'plane{k}'] = _CutPlane(
                self, f'plane{k}', axis, on=on,
                use_widget=use_widget and k <= 2)
        self.layers['iso'] = _Isosurface(self, on=True)
        self.layers['loads'] = _SurfaceLoads(self, on=True)
        self.layers['volume'] = _Volume(self, on=False)
        self.layers['mesh'] = _MeshEdges(self, on=False)
        if not embedded:
            self._widgets()

    def _domain_extent(self):
        return (self.init['Lx'], self.init['Ly'], self.init['Lz'])

    # ── static scenery ────────────────────────────────────────────────────
    def _static_scene(self):
        pl, init = self.pl, self.init
        pl.set_background(BG_BOTTOM, top=BG_TOP)
        try:
            pl.enable_depth_peeling()
        except Exception:
            pass
        geo = dict(init, r_draw=max(init['r_exp'], init['dx']),
                   r_gauge=1.5 * init['dx'], gauges=init.get('gauges'))
        add_static_scenery(pl, geo)
        pl.add_axes()
        hud_x = 0.02 if self.embedded else 0.28
        self.hud = pl.add_text('waiting for frames...', position=(hud_x, 0.93),
                               viewport=True, font_size=11, color='white',
                               name='hud')
        pl.camera_position = 'iso'
        pl.reset_camera()

    # ── widgets (standalone CLI window only) ──────────────────────────────
    def _widgets(self):
        pl = self.pl
        items = [
            ('Plane 1 (drag arrow)', True, lambda v: self.layers['plane1'].set_visible(v)),
            ('Plane 2 (drag arrow)', False, lambda v: self.layers['plane2'].set_visible(v)),
            ('Shock isosurface', True, lambda v: self.layers['iso'].set_visible(v)),
            ('Surface loads', True, lambda v: self.layers['loads'].set_visible(v)),
            ('Volume render', False, lambda v: self.layers['volume'].set_visible(v)),
            ('Auto colour scale', True, self._set_auto_scale),
            ('Follow live', True, self._set_follow),
        ]
        y = pl.window_size[1] - 46
        self._check_widgets = []
        for label, val, cb in items:
            w = pl.add_checkbox_button_widget(
                cb, value=val, position=(12, y), size=22, border_size=2,
                color_on=CHECK_ON, color_off=CHECK_OFF,
                background_color='#0d0f14')
            pl.add_text(label, position=(40, y + 3), font_size=8,
                        color='white', name=f'lbl_{label}')
            self._check_widgets.append(w)
            y -= 30

        self.slider_iso = pl.add_slider_widget(
            self._set_iso_frac, [0.02, 0.90], value=self.iso_frac,
            title='Iso level (frac of peak)',
            pointa=(0.03, 0.33), pointb=(0.22, 0.33),
            style='modern', title_height=0.016, fmt='%.2f')
        self.slider_cmax = pl.add_slider_widget(
            self._set_cmax, [1.0, 5000.0], value=self.cmax,
            title='Colour max [kPa]',
            pointa=(0.03, 0.24), pointb=(0.22, 0.24),
            style='modern', title_height=0.016, fmt='%.0f')
        self.slider_time = pl.add_slider_widget(
            self._scrub, [0.0, 1.0], value=1.0, title='Time',
            pointa=(0.28, 0.08), pointb=(0.86, 0.08),
            style='modern', title_height=0.016, fmt='%.2f')
        pl.add_key_event('space', self._toggle_play)

    # ── display state setters ─────────────────────────────────────────────
    def field_available(self, key):
        return self.have.get(key, False)

    def ensure_field(self, key):
        """Upload `key`'s data from the current frame if stale. Fields
        are uploaded lazily: each frame only pushes the arrays a layer
        actually displays into the VTK grid (~4 ms per 128-cubed array)."""
        if key in self._stale and self.frame is not None:
            arr = self.frame.get(key)
            if arr is not None:
                vals = _ovp_kpa(arr) if FIELDS[key]['ovp'] \
                    else np.asarray(arr, np.float32)
                self.grid.point_data[key] = vals.ravel(order='F')
            self._stale.discard(key)

    def set_field(self, key):
        """Switch the field the planes/volume are coloured by."""
        if key not in FIELDS or key == self.field:
            return
        self.field = key
        self.ensure_field(key)
        if self.auto_scale and self.frame is not None:
            self._auto_clim()
        self._refresh_field_layers()

    def set_clim(self, vmin, vmax):
        """Manual colour range for the active field (auto scale off)."""
        self.auto_scale = False
        self.vmin = float(vmin)
        self.cmax = max(float(vmax), self.vmin + 1e-9)
        self._broadcast_clim()

    def set_log_scale(self, on):
        self.log_scale = bool(on)
        self._broadcast_clim()

    def _broadcast_clim(self):
        """One colour-range change reaches EVERY layer (B19): the planes
        rebuild, the volume rescales/rebuilds, the loads re-range."""
        self._refresh_field_layers()
        for key, layer in self.layers.items():
            if key.startswith('plane'):
                continue                    # refreshed above
            if hasattr(layer, 'on_clim_changed'):
                layer.on_clim_changed()

    def _set_auto_scale(self, on):
        self.auto_scale = bool(on)
        if on:
            self._auto_clim()
            self._broadcast_clim()
        elif not self.embedded:
            self._apply_cmax(self.slider_cmax.GetRepresentation().GetValue())

    def _set_follow(self, on):
        self.follow_live = bool(on)
        if on and len(self.store):
            self._show_index(len(self.store) - 1)

    def _set_iso_frac(self, v):
        self.iso_frac = float(v)
        self.layers['iso'].refresh()

    def _set_cmax(self, v):
        if not self.auto_scale:
            self._apply_cmax(float(v))

    def _apply_cmax(self, v):
        v = max(1.0, float(v))
        if abs(v - self.cmax) / self.cmax < 0.02:
            return
        self.cmax = v
        self._broadcast_clim()

    def _refresh_field_layers(self):
        for key, layer in self.layers.items():
            if key.startswith('plane') or key == 'volume':
                layer.refresh()

    def _auto_clim(self):
        """Track the current frame's range of the active field (dead-band
        so tiny changes don't re-render every layer every frame)."""
        arr = self.grid.point_data[self.field]
        if arr.size == 0:
            return
        hi = float(np.nanmax(arr))
        lo = 0.0 if FIELDS[self.field]['ovp'] else float(np.nanmin(arr))
        hi = max(hi, lo + 1e-6)
        changed = (abs(hi - self.cmax) > 0.02 * max(abs(self.cmax), 1e-9)
                   or abs(lo - self.vmin) > 0.02 * max(abs(self.vmin), 1e-9))
        if changed:
            self.vmin, self.cmax = lo, hi
            for key, layer in self.layers.items():
                if not key.startswith('plane') and \
                        hasattr(layer, 'on_clim_changed'):
                    layer.on_clim_changed()    # planes refresh per frame

    def active_clim(self, field=None):
        """(vmin, vmax) for colouring `field` (default: active field);
        log scale clamps the lower bound positive."""
        lo, hi = self.vmin, self.cmax
        if field is not None and field != self.field:
            self.ensure_field(field)
            arr = self.grid.point_data[field]
            if arr.size:
                lo, hi = float(np.nanmin(arr)), float(np.nanmax(arr))
        hi = max(hi, lo + 1e-9)
        if self.log_scale:
            lo = max(lo, hi * 10.0 ** -LOG_DECADES, 1e-9)
        return lo, hi

    def _scrub(self, v):
        if not len(self.store):
            return
        k = int(round(float(v) * (len(self.store) - 1)))
        if k != self.index:
            if not self.done:
                self.follow_live = False
            self._show_index(k)

    def _toggle_play(self):
        self.playing = not self.playing

    # ── frame flow ────────────────────────────────────────────────────────
    def on_message(self, msg):
        tag = msg[0]
        if tag == 'frame':
            _, t, payload, final = msg
            stored = self.store.append(t, payload, force=final)
            if self.follow_live or self.index < 0:
                if stored:
                    self._show_index(len(self.store) - 1)
                else:
                    # history thinning rejected it - still show it live
                    self._display(t, payload)
            else:
                self._update_hud()
        elif tag == 'done':
            self.done = True
            self.stop_reason = msg[1]
            self.follow_live = False
            self._update_hud()
        elif tag == 'close':
            self.pl.close()

    def _show_index(self, k):
        if not len(self.store):
            return
        k = max(0, min(k, len(self.store) - 1))
        self.index = k
        t, frame = self.store[k]
        self._display(t, frame)
        # keep the time slider in sync without re-triggering _scrub
        if not self.embedded:
            rep = self.slider_time.GetRepresentation()
            frac = k / max(1, len(self.store) - 1)
            if abs(rep.GetValue() - frac) > 1e-6:
                rep.SetValue(frac)

    def _display(self, t, frame):
        """Make a frame payload current and refresh all layers. Only the
        displayed fields are uploaded (ensure_field); the rest stay
        marked stale until a control needs them."""
        self.t, self.frame = t, frame
        self._stale = {k for k in FIELDS if frame.get(k) is not None}
        for key in self._stale:
            self.have[key] = True
        self.ensure_field('p')        # iso + HUD peak always track pressure
        self.ensure_field(self.field)
        if self.auto_scale:
            self._auto_clim()
        for layer in self.layers.values():
            layer.refresh()
        self._update_hud()

    def _update_hud(self):
        peak = (float(np.nanmax(self.grid.point_data['p']))
                if self.frame is not None else 0.0)
        mode = ('PLAYBACK' if self.done else
                'LIVE' if self.follow_live else 'LIVE (paused view)')
        n = len(self.store)
        s = (f't = {self.t*1e3:8.3f} ms    peak = {peak:9.1f} kPa    '
             f'{mode}   [{self.index+1}/{n} frames]')
        if self.loading:
            s += f'\n{self.loading}'
        if self.done and self.stop_reason:
            s += f'\nrun ended: {self.stop_reason}   (space = play/pause)'
        _set_text(self.hud, s)
        self._scale_hud()

    def _scale_hud(self):
        """Size the HUD to the render window: an 11 pt overlay on a
        330 px embedded viewport ran off the right edge ("run ended: ..."
        clipped, QA-17/27). Re-applied per frame - the Tk host resizes
        the off-screen window whenever the pane moves."""
        try:
            w = int(self.pl.window_size[0])
        except Exception:
            return
        size = int(max(7, min(14, round(w / 64.0))))
        if size == getattr(self, '_hud_size', None):
            return
        self._hud_size = size
        try:
            self.hud.GetTextProperty().SetFontSize(size)
        except Exception:
            pass

    def tick(self, *_):
        """Render-timer callback: playback stepping."""
        if self.playing and len(self.store) > 1:
            self._play_skip = (self._play_skip + 1) % 2
            if self._play_skip == 0:
                self._show_index((self.index + 1) % len(self.store))

    # ── embedded-host API (Tk controls instead of VTK widgets) ────────────
    def show_frame(self, k):
        """Jump to stored frame k (playback scrub from the host UI)."""
        if len(self.store):
            if not self.done:
                self.follow_live = False
            self._show_index(int(k))

    def set_plane(self, key, axis, frac):
        """Position cut plane `key`: normal along `axis` ('x'/'y'/'z'),
        at fraction `frac` (0..1) of the domain extent."""
        layer = self.layers[key]
        ax = 'xyz'.index(axis)
        normal = [0.0, 0.0, 0.0]
        normal[ax] = 1.0
        extent = self._domain_extent()
        origin = [0.5 * e for e in extent]
        origin[ax] = float(frac) * extent[ax]
        layer._moved(tuple(normal), tuple(origin))

    def set_plane_opacity(self, key, opacity):
        layer = self.layers[key]
        layer.opacity = min(1.0, max(0.05, float(opacity)))
        layer.refresh()


# ── layers ────────────────────────────────────────────────────────────────
def _clip_to_cylinder(scene, alg):
    """Cylindrical-domain scenes (revolved axisymmetric runs): append a
    clip to a polydata-producing pipeline so slices and surfaces end at
    the true cylinder instead of the bounding box. Stays a live VTK
    pipeline - no per-frame Python cost. Returns `alg` unchanged for
    ordinary box domains."""
    cyl = scene.init.get('cyl')
    if not cyl:
        return alg
    import vtk
    fn = vtk.vtkCylinder()
    fn.SetCenter(float(cyl['cx']), float(cyl['cy']),
                 0.5 * float(scene.init['Lz']))
    fn.SetRadius(float(cyl['R']))
    try:
        fn.SetAxis(0.0, 0.0, 1.0)
    except AttributeError:          # old VTK: default axis is y
        tr = vtk.vtkTransform()
        tr.RotateX(90.0)
        fn.SetTransform(tr)
    clip = vtk.vtkClipPolyData()
    clip.SetInputConnection(alg.GetOutputPort())
    clip.SetClipFunction(fn)
    clip.InsideOutOn()              # keep the inside of the cylinder
    return clip


class _CutPlane(_Layer):
    """Cross-section plane, colour-mapped by the scene's active field
    (draggable VTK widget in the standalone window).

    The slice is a live VTK pipeline (vtkPlane -> vtkCutter bound to the
    scene grid): moving the plane or uploading new frame data re-executes
    in C++ at render time, so a frame costs no Python re-slicing. The
    actor is rebuilt only when the coloured-by array changes; colour
    range / log / opacity update the live mapper."""

    def __init__(self, scene, key, normal_axis, on, use_widget=True):
        import vtk
        self.s = scene
        self.name = f'cut_{key}'
        self.opacity = 1.0
        self.normal = {'x': (1.0, 0, 0), 'y': (0, 1.0, 0),
                       'z': (0, 0, 1.0)}[normal_axis]
        self.origin = tuple(scene.init['charge_center'])
        self._plane = vtk.vtkPlane()
        self._plane.SetNormal(*self.normal)
        self._plane.SetOrigin(*self.origin)
        self._cutter = vtk.vtkCutter()
        self._cutter.SetCutFunction(self._plane)
        self._cutter.SetInputData(scene.grid)
        self._tail = _clip_to_cylinder(scene, self._cutter)
        self._actor = None
        self._scalars = None            # array the actor is coloured by
        self.widget = None
        if use_widget:
            self.widget = scene.pl.add_plane_widget(
                self._moved, normal=self.normal, origin=self.origin,
                bounds=scene.grid.bounds, test_callback=False,
                normal_rotation=True, color='#e0e0e0', tubing=False,
                outline_translation=False, origin_translation=True)
        self.set_visible(on)

    def _moved(self, normal, origin):
        self.normal, self.origin = tuple(normal), tuple(origin)
        self._plane.SetNormal(*self.normal)
        self._plane.SetOrigin(*self.origin)
        self.refresh()
        self._sync_mesh()

    def set_visible(self, on):
        super().set_visible(on)
        self._sync_mesh()

    def _sync_mesh(self):
        """The mesh-edge layer follows this plane's position/visibility."""
        m = self.s.layers.get('mesh')
        if m is not None and m.visible:
            m.refresh()

    def on_clim_changed(self):
        self.refresh()

    def refresh(self):
        s = self.s
        if self.widget is not None:
            try:
                (self.widget.On if self.visible else self.widget.Off)()
            except Exception:
                pass
        if not self.visible or s.frame is None:
            if self._actor is not None:
                self._actor.visibility = False
            return
        scal = s.field
        s.ensure_field(scal)
        clim = s.active_clim()
        if self._actor is None or scal != self._scalars:
            s.pl.remove_actor(self.name)
            title = field_title(s, s.field)
            if self._scalars is not None and self._scalars != scal:
                # pyvista keeps a removed actor's scalar bar: drop the old
                # field's bar so it does not overprint the new one (B19)
                try:
                    s.pl.remove_scalar_bar(field_title(s, self._scalars),
                                           render=False)
                except Exception:
                    pass
            self._actor = s.pl.add_mesh(
                self._tail, scalars=scal, cmap=CMAP, clim=clim,
                log_scale=s.log_scale, opacity=self.opacity,
                name=self.name, show_scalar_bar=True,
                scalar_bar_args=dict(title=title, color='white',
                                     fmt='%.0f' if FIELDS[s.field]['ovp']
                                     else '%.3g', vertical=True,
                                     # far enough from the right edge that
                                     # the (centred) title still fits on a
                                     # narrow embedded viewport (QA-17)
                                     position_x=0.82, position_y=0.30,
                                     width=0.06, height=0.52,
                                     title_font_size=11, label_font_size=10),
                reset_camera=False, render=False)
            self._scalars = scal
        else:
            self._actor.visibility = True
            self._actor.mapper.scalar_range = clim
            self._actor.mapper.lookup_table.log_scale = s.log_scale
            self._actor.prop.opacity = self.opacity


class _MeshEdges(_Layer):
    """Cell edges of the computational mesh over the WHOLE domain: the
    grid on the six boundary faces plus one grid per visible axis-
    aligned cut plane. The true cells of a locally refined run (coarse
    cells as merged blocks, from `init['refine']`), every face
    otherwise, thinned by core.refine so a fine grid does not merge into
    a solid sheet. Built from the FULL-resolution axes in `init` - not
    the stride-decimated display grid - and rebuilt only when a plane
    moves or toggles (frames refresh every layer, so the geometry is
    cached). Dynamic-AMR frames carry their own level map (`levels` in
    the payload): the overlay is then rebuilt per displayed frame so the
    mesh follows the shock in the replay. Off by default."""

    NAME = 'mesh_edges'

    def __init__(self, scene, on):
        self.s = scene
        self._built = None          # the plane set the actor was built for
        self.set_visible(on)

    def _remove(self):
        try:
            self.s.pl.remove_actor(self.NAME)
        except Exception:
            pass
        self._built = None

    def refresh(self):
        s = self.s
        if not self.visible:
            self._remove()
            return
        planes = []
        for key in sorted(s.layers):
            layer = s.layers[key]
            if key.startswith('plane') and layer.visible:
                geom = self._plane_geom(layer)
                if geom is not None:
                    planes.append(geom)
        init = s.init
        rec = init.get('refine')
        lv = s.frame.get('levels') if isinstance(s.frame, dict) else None
        key = (planes, None if lv is None else id(lv))
        if self._built == key:
            return
        self._remove()
        if lv is not None and rec is not None:
            # dynamic AMR: this frame's own level map on the display grid
            # (the record's lmax IS the display level; -1 = carved)
            rec = dict(rec, levels=np.maximum(np.asarray(lv), 0))
        poly = mesh_polydata((init['x_c'], init['y_c'], init['z_c']),
                             float(init['dx']), rec, planes)
        if poly is None:
            return
        s.pl.add_mesh(poly, color=MESH_COLOR, line_width=1,
                      opacity=MESH_OPACITY, name=self.NAME,
                      reset_camera=False, render=False)
        self._built = key

    def _plane_geom(self, layer):
        """(axis, fine layer index, position) of an axis-aligned plane,
        else None. The index selects the refinement structure; the edges
        are drawn at the plane's own position."""
        n = np.asarray(layer.normal, dtype=float)
        ax = int(np.argmax(np.abs(n)))
        if abs(n[ax]) < 0.99 * np.linalg.norm(n):
            return None
        init = self.s.init
        c = (init['x_c'], init['y_c'], init['z_c'])[ax]
        dxf = float(init['dx'])
        pos = float(layer.origin[ax])
        k = int(np.clip(np.floor((pos - (c[0] - dxf / 2)) / dxf), 0,
                        len(c) - 1))
        # a hair off the cut surface so the lines are not z-fought away
        return ax, k, round(pos + 1e-3 * dxf, 9)


class _Isosurface(_Layer):
    """Translucent shock-front surface at a fraction of the frame peak
    (always tracks pressure, whatever the display field). Live pipeline:
    vtkFlyingEdges3D on the scene grid, the level updated per frame."""

    def __init__(self, scene, on):
        import vtk
        self.s = scene
        self.name = 'iso_surface'
        self._fe = vtk.vtkFlyingEdges3D()
        self._fe.SetInputData(scene.grid)
        self._fe.SetInputArrayToProcess(
            0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, 'p')
        self._fe.SetNumberOfContours(1)
        self._tail = _clip_to_cylinder(scene, self._fe)
        self._actor = None
        self.set_visible(on)

    def on_clim_changed(self):
        pass

    def refresh(self):
        s = self.s
        if not self.visible or s.frame is None:
            if self._actor is not None:
                self._actor.visibility = False
            return
        s.ensure_field('p')
        peak = float(s.grid.point_data['p'].max())
        level = s.iso_frac * peak
        if peak <= 0 or level <= 0 or level >= peak:
            if self._actor is not None:
                self._actor.visibility = False
            return
        self._fe.SetValue(0, level)
        if self._actor is None:
            kw = dict(color='#ffb74d', opacity=0.45, name=self.name,
                      show_scalar_bar=False, reset_camera=False,
                      render=False)
            try:
                self._actor = s.pl.add_mesh(self._tail, smooth_shading=True,
                                            **kw)
            except TypeError:
                # pyvista >= 0.45 refuses to smooth-shade a piped
                # vtkAlgorithm. Flat shading keeps the live pipeline (no
                # per-frame Python re-slicing) instead of losing the layer.
                self._actor = s.pl.add_mesh(self._tail, **kw)
        else:
            self._actor.visibility = True


LOADS_TITLE = 'Surface loads [kPa]'
#: the loads bar lies flat along the bottom edge; VTK prints a horizontal
#: bar's title straight over its tick labels, so the bar itself is
#: untitled and the caption is drawn as its own viewport text (QA-17)
LOADS_BAR_KEY = ' '
LOADS_CAPTION = 'loads_caption'


class _SurfaceLoads(_Layer):
    """Obstacle faces + ground plane painted by adjacent-fluid pressure.

    Always painted in overpressure kPa with its OWN colour range (tracked
    per frame from the faces themselves, or the manual Min/Max when the
    active field is an overpressure field), so switching the planes to
    Density/Energy never saturates the loads; a second small scalar bar
    titles them separately from the active field's bar (B19)."""

    def __init__(self, scene, on):
        self.s = scene
        self.meshes = {}
        self._own = (0.0, 1.0)      # per-frame overpressure range [kPa]
        self._bar_actor = None      # the face carrying the loads bar
        init = scene.init
        coords = (init['x_c'], init['y_c'], init['z_c'])
        dx = init['dx']
        for spec in init['face_specs']:
            self.meshes[spec.face_id] = self._face_mesh(spec, coords, dx)
        self.set_visible(on)

    def _face_mesh(self, spec, coords, dx):
        pv = self.s.pv
        ta, tb = [a for a in range(3) if a != spec.axis]
        ca = np.asarray(coords[ta])[spec.lo[0]:spec.hi[0]]
        cb = np.asarray(coords[tb])[spec.lo[1]:spec.hi[1]]
        ea = np.append(ca - 0.5 * dx, ca[-1] + 0.5 * dx)
        eb = np.append(cb - 0.5 * dx, cb[-1] + 0.5 * dx)
        A, B = np.meshgrid(ea, eb, indexing='ij')
        P = np.empty(A.shape + (3,))
        # nudge off the box surface to avoid z-fighting with the grey box
        P[..., spec.axis] = spec.plane + spec.side * 0.05 * dx
        P[..., ta] = A
        P[..., tb] = B
        sg = pv.StructuredGrid()
        sg.dimensions = (A.shape[0], A.shape[1], 1)
        sg.points = np.column_stack(
            [P[..., k].ravel(order='F') for k in range(3)])
        sg.cell_data['load'] = np.zeros((len(ca)) * (len(cb)), np.float32)
        return sg

    def _load_clim(self):
        """Manual Min/Max applies only when it is an overpressure range;
        otherwise the faces keep their own per-frame overpressure range."""
        s = self.s
        if not s.auto_scale and FIELDS[s.field]['ovp']:
            return s.active_clim()
        lo, hi = self._own
        return (lo, max(hi, lo + 1e-6))

    def _track(self, loads):
        """Per-frame overpressure range of the faces (2 % dead-band)."""
        hi = 0.0
        for fid in self.meshes:
            arr = loads.get(fid)
            if arr is not None:
                v = _ovp_kpa(arr)
                if v.size:
                    hi = max(hi, float(np.nanmax(v)))
        if abs(hi - self._own[1]) > 0.02 * max(self._own[1], 1e-9):
            self._own = (0.0, max(hi, 1e-6))

    def on_clim_changed(self):
        clim = self._load_clim()
        for fid in self.meshes:
            actor = self.s.pl.actors.get(f'load_{fid}')
            if actor is not None:
                actor.mapper.scalar_range = clim

    def _remove_all(self):
        s = self.s
        for fid in self.meshes:
            s.pl.remove_actor(f'load_{fid}')
        try:
            s.pl.remove_scalar_bar(LOADS_BAR_KEY, render=False)
        except Exception:
            pass
        try:
            s.pl.remove_actor(LOADS_CAPTION, render=False)
        except Exception:
            pass
        self._bar_actor = None

    def refresh(self):
        s = self.s
        if not self.visible or s.frame is None:
            self._remove_all()
            return
        loads = s.frame.get('loads') or {}
        self._track(loads)
        clim = self._load_clim()
        for fid, mesh in self.meshes.items():
            arr = loads.get(fid)
            if arr is None:
                continue
            mesh.cell_data['load'] = _ovp_kpa(arr).ravel(order='F')
            name = f'load_{fid}'
            if name not in s.pl.actors:
                first_bar = self._bar_actor is None
                kw = dict(scalars='load', cmap=CMAP, clim=clim, name=name,
                          nan_color='#4a4f57', show_scalar_bar=first_bar,
                          reset_camera=False, render=False)
                if first_bar:
                    # horizontal, along the bottom: two vertical bars at
                    # the right edge crowded a narrow embedded viewport
                    # and the lower one lost its labels (QA-17)
                    kw['scalar_bar_args'] = dict(
                        title=LOADS_BAR_KEY, color='white', fmt='%.0f',
                        vertical=False, position_x=0.28, position_y=0.02,
                        width=0.44, height=0.10, n_labels=4,
                        title_font_size=1, label_font_size=9)
                if s.init.get('cyl'):
                    # cylindrical domain: cells beyond the outer radius
                    # are no-data - hide them so the ground is a disc
                    kw['nan_opacity'] = 0.0
                actor = s.pl.add_mesh(mesh, **kw)
                if first_bar:
                    self._bar_actor = actor
                    s.pl.add_text(LOADS_TITLE, position=(0.395, 0.10),
                                  viewport=True, font_size=6,
                                  color='white', name=LOADS_CAPTION)
            else:
                s.pl.actors[name].mapper.scalar_range = clim


class _Volume(_Layer):
    """Semi-transparent cloud of the active field."""

    def __init__(self, scene, on):
        self.s = scene
        self.name = 'volume_f'
        self._added = None           # field key currently added, or None
        self.set_visible(on)

    def on_clim_changed(self):
        if not self._added:
            return
        actor = self.s.pl.actors.get(self.name)
        try:
            actor.mapper.scalar_range = self.s.active_clim()
        except Exception:       # mapper cannot rescale live: rebuild
            self._remove()
            self.refresh()

    def _remove(self):
        try:
            self.s.pl.remove_actor(self.name)
        except Exception:
            pass
        self._added = None

    def refresh(self):
        s = self.s
        if not self.visible or s.frame is None:
            self._remove()
            return
        s.ensure_field(s.field)
        if self._added != s.field:
            self._remove()
            s.pl.add_volume(s.grid, scalars=s.field, cmap=CMAP,
                            clim=s.active_clim(), opacity='linear',
                            opacity_unit_distance=4 * s.grid.spacing[0],
                            name=self.name, show_scalar_bar=False,
                            reset_camera=False, render=False)
            self._added = s.field
        else:
            s.grid.Modified()


class GeometryScene(_CameraOps):
    """Static scenery only - the GUI's live setup preview. `show(geo)`
    re-renders for a new/edited case; the camera is preserved while the
    domain extents stay the same."""

    def __init__(self, plotter):
        self.pl = plotter
        self._extent = None
        self._axes_added = False
        self.pl.set_background(BG_BOTTOM, top=BG_TOP)

    def _domain_extent(self):
        return self._extent or (1.0, 1.0, 1.0)

    def show(self, geo):
        extent = (geo['Lx'], geo['Ly'], geo['Lz'])
        keep_camera = self._extent == extent
        cam = self.pl.camera_position if keep_camera else None
        self.pl.clear()
        self.pl.set_background(BG_BOTTOM, top=BG_TOP)
        add_static_scenery(self.pl, geo)
        self.pl.show_bounds(color='#9aa4b2', grid='back', location='outer',
                            xtitle='x [m]', ytitle='y [m]', ztitle='z [m]',
                            font_size=10)
        if not self._axes_added:
            self.pl.add_axes()
            self._axes_added = True
        self._extent = extent
        if keep_camera:
            self.pl.camera_position = cam
        else:
            self.reset_view()


# ── entry point ───────────────────────────────────────────────────────────
#: ('ctrl', surface, name, *args) -> BlastScene setter (host controls)
_CTRL = {
    'layer': lambda sc, key, on: sc.layers[key].set_visible(bool(on)),
    'field': lambda sc, key: sc.set_field(key),
    'clim': lambda sc, lo, hi: sc.set_clim(lo, hi),
    'auto_scale': lambda sc, on: sc._set_auto_scale(bool(on)),
    'log': lambda sc, on: sc.set_log_scale(bool(on)),
    'iso_frac': lambda sc, f: sc._set_iso_frac(float(f)),
    'plane': lambda sc, key, axis, frac: sc.set_plane(key, axis, frac),
    'plane_opacity': lambda sc, key, op: sc.set_plane_opacity(key, op),
    'view': lambda sc, name: sc.view_preset(name),
    'parallel': lambda sc, on: sc.set_parallel(bool(on)),
    'reset_view': lambda sc: sc.reset_view(),
    'follow': lambda sc, on: sc._set_follow(bool(on)),
    'show_frame': lambda sc, k: sc.show_frame(int(k)),
    'play': lambda sc, on: setattr(sc, 'playing', bool(on)),
}

#: default window sizes: the CLI window, and a GUI surface before its
#: host tells it the container size
_STANDALONE_SIZE = (1400, 900)
_EMBED_SIZE = (640, 480)


def _window_class():
    """The per-surface top-level window (built lazily: Qt is imported
    only inside the viewer child)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    from pyvistaqt import QtInteractor

    class SurfaceWindow(QWidget):
        """A framed top-level window. The GUI host embeds it through
        QWindow.fromWinId + createWindowContainer, which strips the frame
        while embedded and restores it when the host detaches - so the
        child never touches window styles itself: it only shows, hides
        and reports its native handle."""

        def __init__(self, surface, host, standalone, title):
            super().__init__(None)
            self.surface = surface
            self._host = host
            self.standalone = standalone
            self.setWindowFlags(Qt.Window)
            self.setWindowTitle(title)
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            self.plotter = QtInteractor(self, auto_update=False)
            lay.addWidget(self.plotter)
            self.resize(*(_STANDALONE_SIZE if standalone else _EMBED_SIZE))

        def render(self):
            self.plotter.render()

        def closeEvent(self, event):
            # a floating window closed by the user: tell the host, and
            # keep the scene (the GUI can re-claim it); the CLI quits
            # once its last window is gone
            self._host.window_closed(self.surface)
            if self.standalone:
                event.accept()
            else:
                event.ignore()
                self.hide()

    return SurfaceWindow


class _ViewerHost:
    """Everything the child does between two timer ticks: pull frames
    out of the rings, step playback, apply control messages, render the
    windows that changed, report status."""

    STATUS_S = 0.1          # status replies at most this often per surface
    PLAY_S = 0.1            # playback stepping cadence (BlastScene.tick)

    def __init__(self, conn, opts, app):
        from .protocol import SharedFrameRing
        self._Ring = SharedFrameRing
        self._Window = _window_class()
        self.conn = conn
        self.opts = opts
        self.app = app
        self.standalone = bool(opts.get('standalone'))
        self.win = {}
        self.scene = {}
        self.ring = {}
        self.seq = {}
        self.dirty = set()
        self._lost = False
        self._status_sig = {}
        self._status_at = {}
        self._play_at = time.monotonic()
        self._send(('ready', os.getpid()))

    # ── plumbing ─────────────────────────────────────────────────────────
    def _send(self, msg):
        if self._lost:
            return
        try:
            self.conn.send(msg)
        except (BrokenPipeError, EOFError, OSError, ValueError):
            self._connection_lost()

    def _error(self, surface, exc):
        print(f'[viewer] {surface}: {exc!r}')
        self._send(('error', surface, repr(exc)))

    def _connection_lost(self):
        if self._lost:
            return
        self._lost = True
        for s, sc in self.scene.items():
            if isinstance(sc, BlastScene) and not sc.done:
                try:
                    sc.on_message(('done', 'connection to solver lost'))
                except Exception:
                    pass
                self.dirty.add(s)
        if not self.standalone:
            self.app.quit()

    def window_closed(self, surface):
        self._send(('closed', surface))
        if self.standalone and not any(
                w.isVisible() and w.surface != surface
                for w in self.win.values()):
            self.app.quit()

    def _window(self, surface, title=None):
        w = self.win.get(surface)
        if w is None:
            w = self._Window(surface, self, self.standalone,
                             title or 'blastlab - 3D blast viewer')
            self.win[surface] = w
            if self.standalone:
                w.show()
                self.app.processEvents()   # size the render window first
            self._send(('window', surface, int(w.winId())))
        return w

    def _drop_scene(self, surface):
        ring = self.ring.pop(surface, None)
        if ring is not None:
            ring.close()
        self.scene.pop(surface, None)
        self.seq.pop(surface, None)
        self._status_sig.pop(surface, None)
        w = self.win.get(surface)
        if w is not None:
            pl = w.plotter
            for fn in ('clear_button_widgets', 'clear_slider_widgets',
                       'clear_plane_widgets'):
                try:
                    getattr(pl, fn)()
                except Exception:
                    pass
            pl.clear()

    # ── the tick ─────────────────────────────────────────────────────────
    def tick(self):
        now = time.monotonic()
        for s, ring in list(self.ring.items()):
            self._pump_ring(s, ring)
        if now - self._play_at >= self.PLAY_S:
            self._play_at = now
            for s, sc in self.scene.items():
                if isinstance(sc, BlastScene):
                    before = sc.index
                    try:
                        sc.tick()
                    except Exception as exc:
                        self._error(s, exc)
                    if sc.index != before:
                        self.dirty.add(s)
        for _i in range(8):
            if self._lost:
                break
            try:
                if not self.conn.poll():
                    break
                msg = self.conn.recv()
            except (EOFError, OSError, BrokenPipeError):
                self._connection_lost()
                break
            self._handle(msg)
        for s in list(self.dirty):
            w = self.win.get(s)
            if w is not None and w.isVisible():
                try:
                    w.render()
                except Exception as exc:
                    self._error(s, exc)
        self.dirty.clear()
        self._report(now)

    def _pump_ring(self, surface, ring):
        got = ring.read(self.seq.get(surface, 0))
        if got is None:
            return
        seq, t, payload, final = got
        self.seq[surface] = seq
        sc = self.scene.get(surface)
        if isinstance(sc, BlastScene):
            try:
                sc.on_message(('frame', t, payload, final))
            except Exception as exc:            # keep the window alive
                print(f'[viewer] frame dropped: {exc!r}')
            self.dirty.add(surface)

    def _report(self, now):
        for s, sc in self.scene.items():
            if not isinstance(sc, BlastScene):
                continue
            have = tuple(sorted(k for k, v in sc.have.items() if v))
            sig = (len(sc.store), sc.index, sc.t, sc.done, sc.playing,
                   sc.follow_live, sc.field, sc.vmin, sc.cmax, have,
                   sc.stop_reason)
            if sig == self._status_sig.get(s):
                continue
            if now - self._status_at.get(s, 0.0) < self.STATUS_S:
                continue
            self._status_sig[s] = sig
            self._status_at[s] = now
            self._send(('status', s, dict(
                n=sig[0], index=sig[1], t=sig[2], done=sig[3],
                playing=sig[4], follow=sig[5], field=sig[6],
                vmin=sig[7], vmax=sig[8], have=list(have),
                stop_reason=sig[10])))

    # ── control messages ─────────────────────────────────────────────────
    def _handle(self, msg):
        tag = msg[0]
        if tag == 'close':
            self.app.quit()
            return
        surface = msg[1] if len(msg) > 1 else ''
        try:
            if tag == 'scene':
                self._build_scene(surface, msg[2])
            elif tag == 'geo':
                self._show_geo(surface, msg[2])
            elif tag == 'done':
                ring = self.ring.get(surface)
                if ring is not None:       # the final frame lands first
                    self._pump_ring(surface, ring)
                sc = self.scene.get(surface)
                if isinstance(sc, BlastScene):
                    sc.on_message(('done', str(msg[2])))
                    self.dirty.add(surface)
            elif tag == 'claim':
                self._claim(surface, msg[2] if len(msg) > 2 else None)
            elif tag == 'release':
                w = self.win.get(surface)
                if w is not None:
                    w.hide()
            elif tag == 'detach':
                self._detach(surface, bool(msg[2]))
            elif tag == 'resize':
                w = self.win.get(surface)
                if w is not None:
                    w.resize(max(1, int(msg[2])), max(1, int(msg[3])))
                    self.dirty.add(surface)
            elif tag == 'screenshot':
                w = self.win.get(surface)
                if w is not None:
                    w.render()
                    w.plotter.screenshot(msg[2])
                    self._send(('screenshot_done', surface, msg[2]))
            elif tag == 'hud':
                sc = self.scene.get(surface)
                if isinstance(sc, BlastScene):
                    sc.loading = str(msg[2])
                    sc._update_hud()
                    self.dirty.add(surface)
            elif tag == 'ctrl':
                sc = self.scene.get(surface)
                fn = _CTRL.get(msg[2])
                if isinstance(sc, BlastScene) and fn is not None:
                    fn(sc, *msg[3:])
                    self.dirty.add(surface)
        except Exception as exc:
            self._error(surface, exc)

    def _build_scene(self, surface, spec):
        w = self._window(surface, spec.get('title'))
        self._drop_scene(surface)
        sc = BlastScene(w.plotter, spec['init'],
                        embedded=bool(spec.get('embedded', True)),
                        n_planes=int(spec.get('n_planes', 2)))
        self.scene[surface] = sc
        if spec.get('shm'):
            self.ring[surface] = self._Ring(spec['layout'], name=spec['shm'],
                                            create=False)
            self.seq[surface] = 0
        self.dirty.add(surface)
        self._send(('scene_ready', surface))

    def _show_geo(self, surface, geo):
        w = self._window(surface, 'blastlab - model preview')
        sc = self.scene.get(surface)
        if not isinstance(sc, GeometryScene):
            self._drop_scene(surface)
            sc = GeometryScene(w.plotter)
            self.scene[surface] = sc
        sc.show(geo)
        self.dirty.add(surface)

    def _claim(self, surface, hwnd):
        """Show the surface window (the host has already re-parented it
        into its container when `hwnd` is given; a floating window just
        appears). `hwnd` is informational."""
        w = self._window(surface)
        w.show()
        w.raise_()
        self.dirty.add(surface)

    def _detach(self, surface, floating):
        """The host un-embedded (floating=True: show as a framed window)
        or wants the window back (False: hide until it re-embeds and
        claims it); either way the native handle is reported again."""
        w = self._window(surface)
        if floating:
            w.show()
            w.raise_()
            self.dirty.add(surface)
        else:
            w.hide()
        self._send(('window', surface, int(w.winId())))

    def shutdown(self):
        for s in list(self.scene):
            self._drop_scene(s)
        for w in self.win.values():
            try:
                w.plotter.close()
                w.close()
            except Exception:
                pass


def viewer_main(conn, opts=None):
    """Spawn target: a small Qt application hosting one pyvista render
    window per surface, fed from shared-memory rings and driven by the
    control pipe (see process.py for the message vocabulary)."""
    # a test parent's offscreen platform must not leak into the child:
    # VTK needs a real GL window here
    os.environ.pop('QT_QPA_PLATFORM', None)
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(['blastlab-viewer3d'])
    app.setQuitOnLastWindowClosed(False)
    host = _ViewerHost(conn, dict(opts or {}), app)
    timer = QTimer()
    timer.setInterval(33)
    timer.timeout.connect(host.tick)
    timer.start()
    try:
        app.exec()
    finally:
        host.shutdown()
