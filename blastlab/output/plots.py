"""Figure builders for all solvers.

Every function builds and RETURNS a matplotlib Figure (OO API - no pyplot,
no savefig, no show), so the same figures can be saved from the CLI,
embedded in the Tkinter GUI, or rendered on a worker thread. The legacy
plot_* wrappers add the historical filenames/printing/plt.show().
"""

import warnings

import matplotlib as mpl
import numpy as np
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # registers 3d proj

# N2-11 follow-up (N3 round, I06): the gauge figures use constrained
# layout so their margins survive canvas resizes - but when the window is
# squeezed BELOW its minimum the axes collapse to zero and matplotlib
# emits "constrained_layout not applied because axes sizes collapsed to
# zero" on every draw. tight_layout was simply silent there. The warning
# is pure noise at degenerate sizes (there is no layout to apply), and
# the QA harness rightly flags stray warnings, so this one specific
# message is filtered; every other layout warning still surfaces.
warnings.filterwarnings(
    'ignore',
    message='constrained_layout not applied because axes sizes collapsed')

try:
    from skimage import measure as _sk_measure
    HAVE_SKIMAGE = True
except ImportError:
    HAVE_SKIMAGE = False

from ..core.constants import P_AIR


def titled(base, extra=None):
    """A figure title with the user's own line above the automatic one.

    The automatic title carries what the picture IS (charge, field, and
    on an animation the running time), so `extra` is added ABOVE it
    rather than replacing it - a titled video still shows t. Empty or
    None gives the automatic title unchanged.
    """
    extra = (extra or '').strip()
    return f'{extra}\n{base}' if extra else base


def charge_label(meta):
    fp = meta.get('from_profile')
    if fp in (True, '1d'):
        return '1D remap'
    if fp == '2d':
        return '2D remap'
    if meta.get('geometry') == 'planar':
        return f"{meta['charge']:g} kg/m TNT"
    return f"{meta['charge']:g} kg TNT"


def _inferno_bad_gray():
    cmap = mpl.colormaps['inferno'].copy()
    cmap.set_bad('0.5')   # obstacles in gray
    return cmap


# ── Shared quadmesh helpers (live view, animation, GUI) ──────────────────────

def overpressure_panel(ax, x_face, y_face, shape2d, mesh=None):
    """Create an empty overpressure pcolormesh panel; returns the QuadMesh.
    `mesh`: cell-edge segments (see mesh_for) drawn on top."""
    Nx, Ny = shape2d
    qm = ax.pcolormesh(x_face, y_face, np.zeros((Ny, Nx)),
                       cmap=_inferno_bad_gray(), shading='flat')
    ax.set_aspect('equal')
    if mesh is not None:
        add_mesh_lines(ax, mesh)
    return qm


def add_mesh_lines(ax, segments, color='0.6'):
    """Overlay cell edges ((N, 2, 2) segments) on a field axis."""
    from matplotlib.collections import LineCollection
    lc = LineCollection(np.asarray(segments).reshape(-1, 2, 2),
                        colors=color, linewidths=0.35, alpha=0.6,
                        zorder=2.5)
    ax.add_collection(lc)
    return lc


#: full-span grid lines per direction on a field plot (refinement
#: boundaries are always kept - see core.refine.mesh_segments_2d)
MESH_MAX_LINES = 60

#: The robust colour clip, defined once here because three layers need
#: the SAME rule: the panel grid below, the animation's whole-video
#: range (output/animation.frame_clim) and the Qt Fields panel
#: (ui/pg_plots.ScalarImage.set_data).
#:
#: Blast fields are dominated by a handful of cells: a peak-overpressure
#: map has 1e7 kPa in the charge against a field of 1e2, and a recording
#: that starts at t = 0 has the unexpanded charge at ~2.8e6 kPa against a
#: shock of ~4.5e4 (measured, 5 kg planar 2D: a 61x ratio, which left the
#: last frame occupying 0.28 % of the colour bar). So the top is clipped
#: to this percentile - but ONLY when the peak really is that far above
#: the bulk, so an ordinary field is never touched.
CLIP_PERCENTILE = 99.5
CLIP_RATIO = 4.0
CLIP_NOTE = '  (top 0.5 % clipped)'


def gauge_points(meta, sl=None, tol=None):
    """The gauge positions to draw on one field plot, as (x, y) pairs in
    plot coordinates, with their 1-based numbers: [(n, x, y), ...].

    2D: every gauge. 3D: the ones the plotted plane actually cuts - a
    gauge a metre off the slice would otherwise be drawn as if it sat on
    it. `sl` is the plane selector write_animation/plots build (a tuple
    with one integer index); `tol` defaults to one cell.
    """
    pts = [tuple(float(v) for v in g) for g in (meta.get('gauges') or [])]
    if not pts:
        return []
    if sl is None or len(pts[0]) < 3:
        return [(i + 1, p[0], p[1]) for i, p in enumerate(pts)]
    axis = next(a for a, x in enumerate(sl) if not isinstance(x, slice))
    coord = meta['xyz'[axis] + '_c'][int(sl[axis])]
    if tol is None:
        tol = float(meta.get('dx') or 0.0) or None
    keep = [a for a in range(3) if a != axis]
    out = []
    for i, p in enumerate(pts):
        if tol is not None and abs(p[axis] - coord) > tol:
            continue
        out.append((i + 1, p[keep[0]], p[keep[1]]))
    return out


def add_gauge_markers(ax, points, trigger=None, color='#00e5ff'):
    """Draw gauge positions on a field axis: a ringed dot per gauge with
    its number. `points` comes from gauge_points; `trigger` is the
    1-based number of the trigger gauge (T51), drawn heavier.

    Returns the artists so a live pane can remove them again."""
    arts = []
    for n, x, y in points:
        is_trig = (trigger is not None and n == trigger)
        arts.append(ax.plot(
            [x], [y], marker='o', markersize=6 if is_trig else 5,
            markerfacecolor='none', markeredgecolor=color,
            markeredgewidth=1.8 if is_trig else 1.1,
            linestyle='none', zorder=3.5)[0])
        arts.append(ax.annotate(
            f'G{n}' + ('*' if is_trig else ''), (x, y),
            textcoords='offset points', xytext=(6, 4), color=color,
            fontsize=7.5, fontweight='bold' if is_trig else 'normal',
            zorder=3.5))
    return arts


def _levels_depth(ref, levels=None):
    """How deep the grid a level map lives on is - the `lmax` fine_src /
    slice_src need.

    For STATIC refinement that is `ref['lmax']`. For a dynamic-AMR record
    it is NOT: those level maps (both meta['refine']['levels'] and the
    per-frame ones) live on the DISPLAY grid, whose depth is
    `display_level`, while `lmax` counts only the static refinement - 0
    on a run with no refine zones. Using it there made fine_src shift by
    a NEGATIVE count, which merged the refined block into one huge cell
    and left the coarse field split per cell: the overlay stopped looking
    like the AMR mesh at all (the live pane never had the bug - it sizes
    the blocks from display_level itself).

    The final max() is a guard: a level deeper than the recorded depth
    can only come from a mismatched record, and a negative shift there
    would be nonsense rather than a wrong-looking picture."""
    lmax = int(ref.get('lmax') or 0)
    if ref.get('amr'):
        lmax = int(ref.get('display_level') or 0) or lmax
    for lv in (levels, ref.get('levels')):
        if lv is not None:
            lmax = max(lmax, int(np.asarray(lv).max()))
            break
    return lmax


#: display cells above which a mesh overlay is COARSENED (the level map
#: is max-pooled 2x2 and the faces halved with it). Measured on a real
#: 640^2 level-4 AMR frame: fine_src + mesh_segments_2d cost ~45 ms
#: there, which the live pane already pays every frame, so the cap sits
#: well above it. What used to happen instead was worse than slow: over
#: 400_000 cells the overlay was REPLACED by a uniform base-grid mesh,
#: so a 640^2 AMR run (409,600 cells - just over the old cap) showed no
#: refinement at all in the exported video or the Results fields, while
#: the live pane, which never had that fallback, showed it correctly.
MESH_MAX_CELLS = 1_200_000


def _fit_overlay(lv, xf, yf, lmax):
    """Halve a plane's level map (and its faces) until it is under
    MESH_MAX_CELLS. Levels are max-pooled so the refined REGIONS survive
    the coarsening; carved cells (-1) survive only where a whole block is
    carved. Returns (levels, u_face, v_face, lmax)."""
    lv = np.asarray(lv)
    xf, yf = np.asarray(xf), np.asarray(yf)
    while lv.size > MESH_MAX_CELLS and lmax > 0 and min(lv.shape) > 1:
        nu, nv = (lv.shape[0] // 2) * 2, (lv.shape[1] // 2) * 2
        block = lv[:nu, :nv].reshape(nu // 2, 2, nv // 2, 2)
        carved = (block < 0).all(axis=(1, 3))
        lv = np.where(carved, -1, np.maximum(block, 0).max(axis=(1, 3)))
        xf, yf = xf[:nu + 1:2], yf[:nv + 1:2]
        lmax -= 1
    return lv, xf, yf, lmax


def mesh_for(meta, xf, yf, sl=None, levels=None):
    """Cell-edge segments for a field plot with faces xf/yf: the TRUE
    cells of a refined blastFoam run (meta['refine'], coarse cells drawn
    as merged blocks), every face for a uniform run. `sl` selects the
    3D plane (a tuple with one integer index); very fine refined slices
    fall back to the base grid. `levels` (dynamic AMR: one frame's level
    map, already on the plotted plane, -1 = carved) replaces the
    meta['refine'] map so the overlay follows the replay."""
    from ..core import refine
    ref = meta.get('refine') if isinstance(meta, dict) else None
    if ref is None:
        return refine.mesh_segments_2d(None, xf, yf,
                                       max_lines=MESH_MAX_LINES)
    lmax = _levels_depth(ref, levels)
    if levels is not None:
        lv = np.asarray(levels)
    elif sl is None:
        lv = np.asarray(ref['levels'])
    else:
        axis = next(a for a, s in enumerate(sl) if not isinstance(s, slice))
        lv = np.asarray(ref['levels'])[
            tuple(int(sl[axis]) if a == axis else slice(None)
                  for a in range(3))]
    lv, xf, yf, lmax = _fit_overlay(lv, xf, yf, lmax)
    src = refine.fine_src(np.maximum(lv, 0), lmax,
                          solid_fine=(lv < 0) if (lv < 0).any() else None)
    return refine.mesh_segments_2d(src, xf, yf, max_lines=MESH_MAX_LINES)


def set_frame(mesh, p, solid, clim=None):
    """Push a pressure field into a QuadMesh. Autoscales per frame
    unless a fixed (vmin, vmax) overpressure range [kPa] is given."""
    ovp = np.where(solid, np.nan, (p.astype(np.float64) - P_AIR) / 1e3)
    mesh.set_array(ovp.T)
    if clim is None:
        # a plane cut entirely through an obstacle has no finite cell:
        # nanmax would warn and hand matplotlib a NaN range (NaN fails
        # the hi <= lo guard below, so it would get through)
        if np.isfinite(ovp).any():
            lo, hi = float(np.nanmin(ovp)), float(np.nanmax(ovp))
        else:
            lo = hi = 0.0
        if hi <= lo:
            hi = lo + 1.0
        mesh.set_clim(lo, hi)
    else:
        mesh.set_clim(*clim)
    return ovp


# ── 1D figures ────────────────────────────────────────────────────────────────

def figure_results_1d(snapshots, eos, charge_kg, radius_m,
                      title_extra=None):
    fig = Figure(figsize=(10, 10))
    axes = fig.subplots(3, 1, sharex=True)

    colors = mpl.colormaps['plasma'](np.linspace(0.1, 0.9, len(snapshots)))
    for (label, data), color in zip(snapshots.items(), colors):
        kw = dict(label=label, color=color, lw=1.5)
        axes[0].plot(data['r'], data['p'] / 1e3,   **kw)
        axes[1].plot(data['r'], data['rho'],        **kw)
        axes[2].plot(data['r'], data['u'],          **kw)

    axes[0].set_ylabel('Pressure [kPa]')
    axes[1].set_ylabel('Density [kg/m³]')
    axes[2].set_ylabel('Particle velocity [m/s]')
    axes[2].set_xlabel('Radius [m]')

    axes[0].set_title(titled(
        f'1D Spherical Blast - {charge_kg} kg TNT - EOS: {eos}',
        title_extra))
    axes[0].axhline(P_AIR / 1e3, color='k', lw=0.8, ls='--', alpha=0.4,
                    label='Ambient')
    axes[0].legend(loc='upper right', fontsize=8)

    for ax in axes:
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, radius_m)

    fig.tight_layout()
    return fig


def figure_gauges_1d(gauge_out, charge_kg, eos, title_extra=None):
    times  = gauge_out['times']
    radii  = gauge_out['radii']
    pdata  = gauge_out['pressures']

    if len(radii) == 0:
        return None

    n      = len(radii)
    ncols  = min(n, 2)
    nrows  = (n + ncols - 1) // ncols
    colors = mpl.colormaps['tab10'](np.linspace(0, 0.9, n))

    # N2-11: constrained layout, not the one-shot tight_layout() this used
    # to call at the bottom. The embedded canvas RESIZES the figure after
    # creation, and a tight_layout computed at 14x4 in leaves the panels
    # colliding at the ~10x3 in the widget actually gives them - the left
    # panel's y-label sat on its own tick labels and the right panel's
    # label landed between the panels. Constrained layout is recomputed
    # on every draw, so it survives any resize. (figure_gauges_nd below
    # had the identical latent pattern and gets the identical fix.)
    fig = Figure(figsize=(7 * ncols, 4 * nrows), layout='constrained')
    axes = fig.subplots(nrows, ncols, squeeze=False)
    fig.suptitle(titled(
        f'Gauge Time Histories - {charge_kg} kg TNT - EOS: {eos}',
        title_extra),
                 fontsize=12)

    for k, (p_arr, r_val, color) in enumerate(zip(pdata, radii, colors)):
        ax  = axes[k // ncols][k % ncols]
        ovp = (p_arr - P_AIR) / 1e3   # overpressure [kPa]
        ax.plot(times * 1e3, ovp, color=color, lw=1.2)
        ax.axhline(0, color='k', lw=0.7, ls='--', alpha=0.5)
        ax.set_title(f'Gauge {k+1}  (r = {r_val:.2f} m)', fontsize=10)
        ax.set_xlabel('Time [ms]')
        ax.set_ylabel('Overpressure [kPa]')
        ax.grid(True, alpha=0.3)

    for k in range(n, nrows * ncols):
        axes[k // ncols][k % ncols].set_visible(False)

    return fig


# ── 2D/3D gauge figure ───────────────────────────────────────────────────────

#: T44/N12: trace field -> (gauges key, y-label, transform)
GAUGE_FIELDS = {
    'p':   ('pressures', 'Overpressure [kPa]',
            lambda a: (a - P_AIR) / 1e3),
    '|U|': ('speeds', 'Speed [m/s]', lambda a: a),
    'rho': ('rhos', 'Density [kg/m3]', lambda a: a),
    # OUT-4a: the blastFoam gauge extras (vtk_gauges), when recorded.
    # 1 Pa s = 1 kPa ms; q is the magnitude of blastFoam's dynamicP
    # (blastFoam User Guide v6.0, sec. 15.9, eq. 15.1)
    'overpressure': ('overpressures', 'Overpressure (blastFoam) [kPa]',
                     lambda a: a / 1e3),
    'impulse': ('impulses', 'Impulse [kPa ms]', lambda a: a),
    'T': ('temperatures', 'Temperature [K]', lambda a: a),
    'q': ('dyn_pressures', 'Dynamic pressure [kPa]', lambda a: a / 1e3),
}


def gauge_fields_available(gauge_out):
    """Which of GAUGE_FIELDS this result actually recorded (native runs
    and pre-T44 foam runs are p-only)."""
    return [f for f, (key, _l, _t) in GAUGE_FIELDS.items()
            if gauge_out.get(key)]


def figure_gauges_nd(gauge_out, meta, field='p', title_extra=None):
    """Gauge grid for 2D (x,y points) and 3D (x,y,z points). `field`
    picks the trace: 'p' (default, always there), '|U|' or 'rho' when
    the run recorded them (blastFoam since T44)."""
    key, ylabel, tr = GAUGE_FIELDS[field]
    times  = gauge_out['times']
    points = gauge_out['points']
    pdata  = gauge_out.get(key) or gauge_out['pressures']

    if len(points) == 0:
        return None

    n      = len(points)
    ncols  = min(n, 2)
    nrows  = (n + ncols - 1) // ncols
    colors = mpl.colormaps['tab10'](np.linspace(0, 0.9, n))

    fig = Figure(figsize=(7 * ncols, 4 * nrows), layout='constrained')
    axes = fig.subplots(nrows, ncols, squeeze=False)
    fig.suptitle(titled(f"Gauge Time Histories - {charge_label(meta)} - "
                        f"EOS: {meta['eos']}", title_extra), fontsize=12)

    for k, (p_arr, pt, color) in enumerate(zip(pdata, points, colors)):
        ax  = axes[k // ncols][k % ncols]
        ovp = tr(p_arr)
        ax.plot(times * 1e3, ovp, color=color, lw=1.2)
        ax.axhline(0, color='k', lw=0.7, ls='--', alpha=0.5)
        loc = ", ".join(f"{v:.2f}" for v in pt)
        ax.set_title(f'Gauge {k+1}  ({loc}) m', fontsize=10)
        ax.set_xlabel('Time [ms]')
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)

    for k in range(n, nrows * ncols):
        axes[k // ncols][k % ncols].set_visible(False)

    return fig


# ── 2D field figures ─────────────────────────────────────────────────────────

def _panel_grid_figure(items, solid_sl, xf, yf, xlabel, ylabel, title,
                       cbar_label, aspect_wh, mesh=None, robust=False):
    """
    Grid of pcolormesh panels with per-panel autoscale.
    items: list of (label, 2D array (Na,Nb)) plotted with faces xf/yf.
    mesh: optional cell-edge segments (mesh_for) overlaid on each panel.
    robust: clip the top of the colour range to the 99.5th percentile.
      Whole-run peak/impulse maps are dominated by the few charge cells
      (1e7 kPa against a field of 1e2), which painted everything else
      black - the map read as a single dot.
    """
    n     = len(items)
    ncols = min(n, 3)
    nrows = (n + ncols - 1) // ncols
    panel_w = 5.0
    panel_h = panel_w / aspect_wh + 1.0

    # constrained layout: tight_layout let the run title and the per-panel
    # label overlap, and clipped the x axis of tall 3D slice panels
    fig = Figure(figsize=(panel_w * ncols, panel_h * nrows),
                 layout='constrained')
    axes = fig.subplots(nrows, ncols, squeeze=False)
    fig.suptitle(title, fontsize=12)

    cmap = _inferno_bad_gray()
    for k, (label, z) in enumerate(items):
        ax = axes[k // ncols][k % ncols]
        zm = np.where(solid_sl, np.nan, z.astype(np.float64))
        vmax = None
        if robust and np.isfinite(zm).any():
            hi = float(np.nanpercentile(zm, CLIP_PERCENTILE))
            top = float(np.nanmax(zm))
            # only clip when the tail really is a small hot spot
            if np.isfinite(hi) and hi > 0 and top > CLIP_RATIO * hi:
                vmax = hi
        im = ax.pcolormesh(xf, yf, zm.T, cmap=cmap, shading='flat',
                           vmax=vmax)
        if mesh is not None:
            add_mesh_lines(ax, mesh)
        ax.set_title(label + (CLIP_NOTE if vmax else ''), fontsize=10)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_aspect('equal')
        fig.colorbar(im, ax=ax, label=cbar_label, shrink=0.85,
                     extend='max' if vmax else 'neither')

    for k in range(n, nrows * ncols):
        axes[k // ncols][k % ncols].set_visible(False)

    return fig


PEAK_LABEL = 'Peak overpressure [kPa]'
IMPULSE_LABEL = 'Net overpressure impulse [Pa·s]'


def has_peak_maps(meta):
    """True when the run carries whole-run p_peak / impulse maps (native
    2D/3D and foam 2D/3D do; runs loaded from older results may not)."""
    return (meta.get('p_peak') is not None
            and meta.get('impulse') is not None)


def peak_items(meta, sl=None):
    """[(label, data)] for the two whole-run maps, optionally sliced.
    p_peak is absolute pressure - shown as overpressure in kPa."""
    pk, imp = meta['p_peak'], meta['impulse']
    if sl is not None:
        pk, imp = pk[sl], imp[sl]
    return [('peak overpressure', (pk - P_AIR) / 1e3),
            ('net ovp impulse', imp)]


def figures_fields_2d(snapshots, meta, include_peak=False,
                      show_mesh=False, title_extra=None):
    """The two 2D field figures: [(filename, Figure), ...]; with
    `include_peak` (and maps present) also the whole-run peak
    overpressure and net impulse figures; `show_mesh` overlays the cell
    edges (see mesh_for)."""
    base = (f"2D Blast ({meta['geometry']}) - {charge_label(meta)} - "
            f"EOS: {meta['eos']}")
    # titled() wraps each panel title, so the user's line sits above
    # every figure of the set (see figures_fields_3d)
    def _t(label):
        return titled(f'{label} - {base}', title_extra)
    xlabel = 'r [m]' if meta['geometry'] == 'axisymmetric' else 'x [m]'
    ylabel = 'z [m]' if meta['geometry'] == 'axisymmetric' else 'y [m]'
    common = dict(solid_sl=meta['solid'], xf=meta['x_face'],
                  yf=meta['y_face'], xlabel=xlabel, ylabel=ylabel,
                  aspect_wh=meta['Lx'] / meta['Ly'],
                  mesh=(mesh_for(meta, meta['x_face'], meta['y_face'])
                        if show_mesh else None))

    out = []
    out.append(('blast_2d_pressure.png', _panel_grid_figure(
        [(lbl, (d['p'] - P_AIR) / 1e3) for lbl, d in snapshots.items()],
        title=_t('Overpressure'), cbar_label='Overpressure [kPa]',
        **common)))
    out.append(('blast_2d_density.png', _panel_grid_figure(
        [(lbl, d['rho']) for lbl, d in snapshots.items()],
        title=_t('Density'), cbar_label='Density [kg/m³]',
        **common)))
    if include_peak and has_peak_maps(meta):
        (pk_lbl, pk), (im_lbl, im) = peak_items(meta)
        out.append(('blast_2d_peak_overpressure.png', _panel_grid_figure(
            [('whole run', pk)], title=_t('Peak overpressure'),
            cbar_label=PEAK_LABEL, robust=True, **common)))
        out.append(('blast_2d_impulse.png', _panel_grid_figure(
            [('whole run', im)], title=_t('Net overpressure impulse'),
            cbar_label=IMPULSE_LABEL, robust=True, **common)))
    return out


# ── 3D slice figures ─────────────────────────────────────────────────────────

def figures_fields_3d(snapshots, meta, include_peak=False,
                      show_mesh=False, title_extra=None):
    """The four 3D slice figures: [(filename, Figure), ...]; with
    `include_peak` (and maps present) also the whole-run peak
    overpressure and net impulse maps on the same two planes;
    `show_mesh` overlays the cell edges of each plane."""
    j0, k0 = meta['j0'], meta['k0']
    mesh_v = mesh_h = None
    if show_mesh:
        mesh_v = mesh_for(meta, meta['x_face'], meta['z_face'],
                          np.s_[:, j0, :])
        mesh_h = mesh_for(meta, meta['x_face'], meta['y_face'],
                          np.s_[:, :, k0])
    y0 = meta['y_c'][j0]
    z0 = meta['z_c'][k0]
    base = f"3D Blast - {charge_label(meta)} - EOS: {meta['eos']}"

    specs = [
        ('blast_3d_pressure_vertical.png',
         [(lbl, (s['p'][:, j0, :] - np.float32(P_AIR)) / np.float32(1e3))
          for lbl, s in snapshots.items()],
         meta['solid'][:, j0, :], meta['x_face'], meta['z_face'],
         'x [m]', 'z [m]',
         f'Overpressure, vertical plane y = {y0:.2f} m - {base}',
         'Overpressure [kPa]', meta['Lx'] / meta['Lz']),
        ('blast_3d_pressure_horizontal.png',
         [(lbl, (s['p'][:, :, k0] - np.float32(P_AIR)) / np.float32(1e3))
          for lbl, s in snapshots.items()],
         meta['solid'][:, :, k0], meta['x_face'], meta['y_face'],
         'x [m]', 'y [m]',
         f'Overpressure, horizontal plane z = {z0:.2f} m - {base}',
         'Overpressure [kPa]', meta['Lx'] / meta['Ly']),
        ('blast_3d_density_vertical.png',
         [(lbl, s['rho_xz']) for lbl, s in snapshots.items()],
         meta['solid'][:, j0, :], meta['x_face'], meta['z_face'],
         'x [m]', 'z [m]',
         f'Density, vertical plane y = {y0:.2f} m - {base}',
         'Density [kg/m³]', meta['Lx'] / meta['Lz']),
        ('blast_3d_density_horizontal.png',
         [(lbl, s['rho_xy']) for lbl, s in snapshots.items()],
         meta['solid'][:, :, k0], meta['x_face'], meta['y_face'],
         'x [m]', 'y [m]',
         f'Density, horizontal plane z = {z0:.2f} m - {base}',
         'Density [kg/m³]', meta['Lx'] / meta['Ly']),
    ]
    if include_peak and has_peak_maps(meta):
        for plane, sl, solid_sl, xf, yf, xl, yl, pos, ar in (
                ('vertical', np.s_[:, j0, :], meta['solid'][:, j0, :],
                 meta['x_face'], meta['z_face'], 'x [m]', 'z [m]',
                 f'y = {y0:.2f} m', meta['Lx'] / meta['Lz']),
                ('horizontal', np.s_[:, :, k0], meta['solid'][:, :, k0],
                 meta['x_face'], meta['y_face'], 'x [m]', 'y [m]',
                 f'z = {z0:.2f} m', meta['Lx'] / meta['Ly'])):
            (pk_lbl, pk), (im_lbl, im) = peak_items(meta, sl)
            specs.append((f'blast_3d_peak_overpressure_{plane}.png',
                          [('whole run', pk)], solid_sl, xf, yf, xl, yl,
                          f'Peak overpressure, {plane} plane {pos} - {base}',
                          PEAK_LABEL, ar))
            specs.append((f'blast_3d_impulse_{plane}.png',
                          [('whole run', im)], solid_sl, xf, yf, xl, yl,
                          f'Net overpressure impulse, {plane} plane {pos} '
                          f'- {base}', IMPULSE_LABEL, ar))
    # one wrap covers all six figures of the set
    return [(fn, _panel_grid_figure(items, solid_sl, xf, yf, xl, yl,
                                    titled(title, title_extra), cl, ar,
                                    mesh=mesh_v if 'vertical' in fn
                                    else mesh_h,
                                    robust=('peak' in fn or 'impulse' in fn)))
            for fn, items, solid_sl, xf, yf, xl, yl, title, cl, ar in specs]


# ── 3D shock-front isosurfaces ───────────────────────────────────────────────

def _obstacle_wireframe(ax, box):
    """Draw the 12 edges of an obstacle box on a 3D axis."""
    x0, x1, y0, y1, z0, z1 = box
    for (a, b) in (((x0, y0, z0), (x1, y0, z0)), ((x0, y1, z0), (x1, y1, z0)),
                   ((x0, y0, z1), (x1, y0, z1)), ((x0, y1, z1), (x1, y1, z1)),
                   ((x0, y0, z0), (x0, y1, z0)), ((x1, y0, z0), (x1, y1, z0)),
                   ((x0, y0, z1), (x0, y1, z1)), ((x1, y0, z1), (x1, y1, z1)),
                   ((x0, y0, z0), (x0, y0, z1)), ((x1, y0, z0), (x1, y0, z1)),
                   ((x0, y1, z0), (x0, y1, z1)), ((x1, y1, z0), (x1, y1, z1))):
        ax.plot(*zip(a, b), color='0.4', lw=1.0)


def figure_isosurfaces_3d(snapshots, meta, title_extra=None):
    """
    One 3D panel per snapshot showing the shock front: a pressure
    isosurface at 10% of the current peak overpressure. Uses
    skimage.measure.marching_cubes when installed; otherwise renders a
    subsampled point cloud of cells near the isovalue.
    """
    n     = len(snapshots)
    ncols = min(n, 3)
    nrows = (n + ncols - 1) // ncols
    fig = Figure(figsize=(5.5 * ncols, 5.0 * nrows))
    fig.suptitle(titled(
        f"Shock front - {charge_label(meta)} - EOS: {meta['eos']}",
        title_extra),
                 fontsize=12)
    x_c, y_c, z_c = meta['x_c'], meta['y_c'], meta['z_c']
    dx = meta['dx']
    x0, y0, z0 = meta['charge_center']
    rng = np.random.default_rng(0)

    for k, (label, snap) in enumerate(snapshots.items()):
        ax = fig.add_subplot(nrows, ncols, k + 1, projection='3d')
        ovp = snap['p'].astype(np.float64) - P_AIR
        iso = max(0.1 * ovp.max(), 1e3)
        drawn = False
        if iso < ovp.max() and iso > ovp.min():
            if HAVE_SKIMAGE:
                verts, faces, _, _ = _sk_measure.marching_cubes(
                    ovp, level=iso, spacing=(dx, dx, dx))
                verts += np.array([x_c[0], y_c[0], z_c[0]])
                ax.add_collection3d(Poly3DCollection(
                    verts[faces], alpha=0.5, facecolor='orangered',
                    edgecolor='none'))
                drawn = True
            else:
                band = (ovp > 0.8 * iso) & (ovp < 1.25 * iso) & ~meta['solid']
                pts = np.argwhere(band)
                if len(pts) > 0:
                    if len(pts) > 20000:
                        pts = pts[rng.choice(len(pts), 20000, replace=False)]
                    ax.scatter(x_c[pts[:, 0]], y_c[pts[:, 1]], z_c[pts[:, 2]],
                               c=z_c[pts[:, 2]], cmap='inferno', s=2, alpha=0.4)
                    drawn = True
        if not drawn:
            ax.text2D(0.5, 0.5, 'no front', transform=ax.transAxes,
                      ha='center')
        ax.scatter([x0], [y0], [z0], color='red', marker='*', s=60)
        for box in meta['obstacles']:
            _obstacle_wireframe(ax, box)
        ax.set_xlim(0, meta['Lx']); ax.set_ylim(0, meta['Ly'])
        ax.set_zlim(0, meta['Lz'])
        ax.set_box_aspect((meta['Lx'], meta['Ly'], meta['Lz']))
        ax.set_title(f"{label}  (iso = {iso/1e3:.1f} kPa)", fontsize=9)
        ax.set_xlabel('x [m]'); ax.set_ylabel('y [m]'); ax.set_zlabel('z [m]')

    fig.tight_layout()
    return fig


# ── HD 1.3: deflagration, structural response and heat (HD1-10) ─────────────
# Same OO convention as everything above: build and return a Figure, never
# touch pyplot. These are the exported figures for the HD1.3 track, whose
# models live in core/deflagration, core/unconfined, core/sdof and
# core/thermal.

def figure_deflagration(res, title=None):
    """The confined chamber: pressure, temperature, burnt fraction and
    vent flow against time, plus how much of the charge is even lit."""
    fig = Figure(figsize=(9, 6))
    t = np.asarray(res['t'])
    ax = fig.add_subplot(2, 2, 1)
    ax.plot(t, np.asarray(res['p']) / 1e6, color='#c1121f')
    ax.set_ylabel('p [MPa]')
    ax.set_title(title or 'Chamber pressure', fontsize=10)
    ax = fig.add_subplot(2, 2, 2)
    ax.plot(t, res['T'], color='#e07a5f')
    ax.set_ylabel('T [K]')
    ax.set_title('Gas temperature', fontsize=10)
    ax = fig.add_subplot(2, 2, 3)
    ax.plot(t, res['Z'], label='burnt')
    if 'lit' in res:
        ax.plot(t, res['lit'], '--', color='0.5', label='lit')
    ax.set_ylabel('fraction of charge')
    ax.set_xlabel('t [s]')
    ax.set_ylim(0, 1.02)
    ax.legend(fontsize=8)
    ax.set_title('Entrainment and burn', fontsize=10)
    ax = fig.add_subplot(2, 2, 4)
    ax.plot(t, res['mdot_out'], color='#3d5a80')
    ax.set_ylabel('vent flow [kg/s]')
    ax.set_xlabel('t [s]')
    ax.set_title('Venting', fontsize=10)
    for a in fig.axes:
        a.grid(alpha=0.3)
    fig.suptitle(f"stop: {res.get('stop_reason', '-')}"
                 f"   |   extrapolated {res.get('extrapolated_fraction', 0):.0%}"
                 f" of the burn", fontsize=9, color='#666')
    fig.tight_layout()
    return fig


def figure_unconfined(res, title=None):
    """The open-air burn: gas rate, burnt fraction, and the expansion
    Mach number that is the whole no-blast argument."""
    fig = Figure(figsize=(9, 3.2))
    t = np.asarray(res['t'])
    ax = fig.add_subplot(1, 3, 1)
    ax.plot(t, res['mdot'], color='#3d5a80')
    ax.set_ylabel('gas rate [kg/s]'); ax.set_xlabel('t [s]')
    ax.set_title(title or 'Gas generation', fontsize=10)
    ax = fig.add_subplot(1, 3, 2)
    ax.plot(t, res['z'], label='burnt')
    ax.plot(t, res['lit'], '--', color='0.5', label='lit')
    ax.set_xlabel('t [s]'); ax.set_ylim(0, 1.02); ax.legend(fontsize=8)
    ax.set_title('Entrainment and burn', fontsize=10)
    ax = fig.add_subplot(1, 3, 3)
    ax.plot(t, res['mach'], color='#c1121f')
    ax.axhline(0.05, ls=':', color='0.4')
    ax.text(t[-1], 0.05, ' quasi-static limit', fontsize=7, va='bottom',
            ha='right', color='0.4')
    ax.set_ylabel('expansion Mach'); ax.set_xlabel('t [s]')
    ax.set_title('Why there is no blast', fontsize=10)
    for a in fig.axes:
        a.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def figure_sdof_response(sres, comp, title=None):
    """Displacement and resistance against time, with the yield
    deflection marked - the picture of whether the element went plastic."""
    fig = Figure(figsize=(9, 3.4))
    t = np.asarray(sres.times) * 1e3
    ax = fig.add_subplot(1, 2, 1)
    ax.plot(t, np.asarray(sres.y) * 1e3, color='#3d5a80')
    ax.axhline(comp.y_el * 1e3, ls='--', color='#c1121f', lw=1)
    ax.text(t[-1], comp.y_el * 1e3, ' yield', fontsize=7, ha='right',
            va='bottom', color='#c1121f')
    ax.set_xlabel('t [ms]'); ax.set_ylabel('deflection [mm]')
    ax.set_title(title or f'Response ({sres.regime})', fontsize=10)
    ax = fig.add_subplot(1, 2, 2)
    ax.plot(t, np.asarray(sres.load) / 1e3, color='0.5', label='load')
    ax.plot(t, np.asarray(sres.R) / 1e3, color='#c1121f', label='resistance')
    ax.set_xlabel('t [ms]'); ax.set_ylabel('[kPa]')
    ax.legend(fontsize=8)
    ax.set_title('Load against resistance', fontsize=10)
    for a in fig.axes:
        a.grid(alpha=0.3)
    fig.suptitle(f'mu = {sres.ductility:.2f}   theta = '
                 f'{sres.support_rotation_deg:.2f} deg   '
                 f'td/Tn = {sres.td_over_Tn:.3g}', fontsize=9, color='#666')
    fig.tight_layout()
    return fig


def figure_pi_diagram(curves, points=(), title=None):
    """Pressure-impulse diagram: iso-damage curves and where the loads
    actually landed.

    `curves` is [(label, I_bar, P_bar)] and `points` is
    [(label, I_bar, P_bar)]. Log-log, because the two asymptotes are the
    entire content and they are decades apart - which is exactly the
    HD1.1 / HD1.3 distinction.
    """
    fig = Figure(figsize=(5.6, 4.6))
    ax = fig.add_subplot(1, 1, 1)
    for label, ib, pb in curves:
        ax.loglog(ib, pb, label=label)
    for label, ib, pb in points:
        ax.loglog([ib], [pb], 'o', ms=7, label=label)
    ax.set_xlabel(r'$\bar{I}$  (impulsive)')
    ax.set_ylabel(r'$\bar{P}$  (quasi-static)')
    ax.set_title(title or 'Pressure-impulse diagram', fontsize=10)
    ax.grid(alpha=0.3, which='both')
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def figure_thermal(t, q, T_surface=None, radiation=(), title=None):
    """Wall flux and surface temperature for the confined case, and
    received flux against standoff for the fireball."""
    n = 2 if T_surface is not None else 1
    n += 1 if radiation else 0
    fig = Figure(figsize=(4.4 * n, 3.2))
    k = 1
    ax = fig.add_subplot(1, n, k); k += 1
    ax.plot(np.asarray(t), np.asarray(q) / 1e3, color='#e07a5f')
    ax.set_xlabel('t [s]'); ax.set_ylabel('wall flux [kW/m2]')
    ax.set_title(title or 'Flux to the wall', fontsize=10)
    if T_surface is not None:
        ax = fig.add_subplot(1, n, k); k += 1
        ax.plot(np.asarray(t), np.asarray(T_surface) - 273.15,
                color='#c1121f')
        ax.set_xlabel('t [s]'); ax.set_ylabel('surface [C]')
        ax.set_title('Inner face temperature', fontsize=10)
    if radiation:
        ax = fig.add_subplot(1, n, k)
        d = [r['distance'] for r in radiation]
        ax.loglog(d, [r['flux'] / 1e3 for r in radiation], 'o-',
                  color='#3d5a80')
        ax.set_xlabel('standoff [m]'); ax.set_ylabel('incident [kW/m2]')
        ax.set_title('Fireball radiation', fontsize=10)
    for a in fig.axes:
        a.grid(alpha=0.3)
    fig.tight_layout()
    return fig
