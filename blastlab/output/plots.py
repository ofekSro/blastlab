"""Figure builders for all solvers.

Every function builds and RETURNS a matplotlib Figure (OO API - no pyplot,
no savefig, no show), so the same figures can be saved from the CLI,
embedded in the Tkinter GUI, or rendered on a worker thread. The legacy
plot_* wrappers add the historical filenames/printing/plt.show().
"""

import matplotlib as mpl
import numpy as np
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # registers 3d proj

try:
    from skimage import measure as _sk_measure
    HAVE_SKIMAGE = True
except ImportError:
    HAVE_SKIMAGE = False

from ..core.constants import P_AIR


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

def overpressure_panel(ax, x_face, y_face, shape2d):
    """Create an empty overpressure pcolormesh panel; returns the QuadMesh."""
    Nx, Ny = shape2d
    mesh = ax.pcolormesh(x_face, y_face, np.zeros((Ny, Nx)),
                         cmap=_inferno_bad_gray(), shading='flat')
    ax.set_aspect('equal')
    return mesh


def set_frame(mesh, p, solid, clim=None):
    """Push a pressure field into a QuadMesh. Autoscales per frame
    unless a fixed (vmin, vmax) overpressure range [kPa] is given."""
    ovp = np.where(solid, np.nan, (p.astype(np.float64) - P_AIR) / 1e3)
    mesh.set_array(ovp.T)
    if clim is None:
        hi = np.nanmax(ovp)
        lo = np.nanmin(ovp)
        if hi <= lo:
            hi = lo + 1.0
        mesh.set_clim(lo, hi)
    else:
        mesh.set_clim(*clim)
    return ovp


# ── 1D figures ────────────────────────────────────────────────────────────────

def figure_results_1d(snapshots, eos, charge_kg, radius_m):
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

    axes[0].set_title(f'1D Spherical Blast - {charge_kg} kg TNT - EOS: {eos}')
    axes[0].axhline(P_AIR / 1e3, color='k', lw=0.8, ls='--', alpha=0.4,
                    label='Ambient')
    axes[0].legend(loc='upper right', fontsize=8)

    for ax in axes:
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, radius_m)

    fig.tight_layout()
    return fig


def figure_gauges_1d(gauge_out, charge_kg, eos):
    times  = gauge_out['times']
    radii  = gauge_out['radii']
    pdata  = gauge_out['pressures']

    if len(radii) == 0:
        return None

    n      = len(radii)
    ncols  = min(n, 2)
    nrows  = (n + ncols - 1) // ncols
    colors = mpl.colormaps['tab10'](np.linspace(0, 0.9, n))

    fig = Figure(figsize=(7 * ncols, 4 * nrows))
    axes = fig.subplots(nrows, ncols, squeeze=False)
    fig.suptitle(f'Gauge Time Histories - {charge_kg} kg TNT - EOS: {eos}',
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

    fig.tight_layout()
    return fig


# ── 2D/3D gauge figure ───────────────────────────────────────────────────────

def figure_gauges_nd(gauge_out, meta):
    """Gauge grid for 2D (x,y points) and 3D (x,y,z points)."""
    times  = gauge_out['times']
    points = gauge_out['points']
    pdata  = gauge_out['pressures']

    if len(points) == 0:
        return None

    n      = len(points)
    ncols  = min(n, 2)
    nrows  = (n + ncols - 1) // ncols
    colors = mpl.colormaps['tab10'](np.linspace(0, 0.9, n))

    fig = Figure(figsize=(7 * ncols, 4 * nrows))
    axes = fig.subplots(nrows, ncols, squeeze=False)
    fig.suptitle(f"Gauge Time Histories - {charge_label(meta)} - "
                 f"EOS: {meta['eos']}", fontsize=12)

    for k, (p_arr, pt, color) in enumerate(zip(pdata, points, colors)):
        ax  = axes[k // ncols][k % ncols]
        ovp = (p_arr - P_AIR) / 1e3
        ax.plot(times * 1e3, ovp, color=color, lw=1.2)
        ax.axhline(0, color='k', lw=0.7, ls='--', alpha=0.5)
        loc = ", ".join(f"{v:.2f}" for v in pt)
        ax.set_title(f'Gauge {k+1}  ({loc}) m', fontsize=10)
        ax.set_xlabel('Time [ms]')
        ax.set_ylabel('Overpressure [kPa]')
        ax.grid(True, alpha=0.3)

    for k in range(n, nrows * ncols):
        axes[k // ncols][k % ncols].set_visible(False)

    fig.tight_layout()
    return fig


# ── 2D field figures ─────────────────────────────────────────────────────────

def _panel_grid_figure(items, solid_sl, xf, yf, xlabel, ylabel, title,
                       cbar_label, aspect_wh):
    """
    Grid of pcolormesh panels with per-panel autoscale.
    items: list of (label, 2D array (Na,Nb)) plotted with faces xf/yf.
    """
    n     = len(items)
    ncols = min(n, 3)
    nrows = (n + ncols - 1) // ncols
    panel_w = 5.0
    panel_h = panel_w / aspect_wh + 1.0

    fig = Figure(figsize=(panel_w * ncols, panel_h * nrows))
    axes = fig.subplots(nrows, ncols, squeeze=False)
    fig.suptitle(title, fontsize=12)

    cmap = _inferno_bad_gray()
    for k, (label, z) in enumerate(items):
        ax = axes[k // ncols][k % ncols]
        zm = np.where(solid_sl, np.nan, z.astype(np.float64))
        im = ax.pcolormesh(xf, yf, zm.T, cmap=cmap, shading='flat')
        ax.set_title(label, fontsize=10)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_aspect('equal')
        fig.colorbar(im, ax=ax, label=cbar_label, shrink=0.85)

    for k in range(n, nrows * ncols):
        axes[k // ncols][k % ncols].set_visible(False)

    fig.tight_layout()
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


def figures_fields_2d(snapshots, meta, include_peak=False):
    """The two 2D field figures: [(filename, Figure), ...]; with
    `include_peak` (and maps present) also the whole-run peak
    overpressure and net impulse figures."""
    base = (f"2D Blast ({meta['geometry']}) - {charge_label(meta)} - "
            f"EOS: {meta['eos']}")
    xlabel = 'r [m]' if meta['geometry'] == 'axisymmetric' else 'x [m]'
    ylabel = 'z [m]' if meta['geometry'] == 'axisymmetric' else 'y [m]'
    common = dict(solid_sl=meta['solid'], xf=meta['x_face'],
                  yf=meta['y_face'], xlabel=xlabel, ylabel=ylabel,
                  aspect_wh=meta['Lx'] / meta['Ly'])

    out = []
    out.append(('blast_2d_pressure.png', _panel_grid_figure(
        [(lbl, (d['p'] - P_AIR) / 1e3) for lbl, d in snapshots.items()],
        title=f'Overpressure - {base}', cbar_label='Overpressure [kPa]',
        **common)))
    out.append(('blast_2d_density.png', _panel_grid_figure(
        [(lbl, d['rho']) for lbl, d in snapshots.items()],
        title=f'Density - {base}', cbar_label='Density [kg/m³]',
        **common)))
    if include_peak and has_peak_maps(meta):
        (pk_lbl, pk), (im_lbl, im) = peak_items(meta)
        out.append(('blast_2d_peak_overpressure.png', _panel_grid_figure(
            [('whole run', pk)], title=f'Peak overpressure - {base}',
            cbar_label=PEAK_LABEL, **common)))
        out.append(('blast_2d_impulse.png', _panel_grid_figure(
            [('whole run', im)], title=f'Net overpressure impulse - {base}',
            cbar_label=IMPULSE_LABEL, **common)))
    return out


# ── 3D slice figures ─────────────────────────────────────────────────────────

def figures_fields_3d(snapshots, meta, include_peak=False):
    """The four 3D slice figures: [(filename, Figure), ...]; with
    `include_peak` (and maps present) also the whole-run peak
    overpressure and net impulse maps on the same two planes."""
    j0, k0 = meta['j0'], meta['k0']
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
    return [(fn, _panel_grid_figure(items, solid_sl, xf, yf, xl, yl,
                                    title, cl, ar))
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


def figure_isosurfaces_3d(snapshots, meta):
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
    fig.suptitle(f"Shock front - {charge_label(meta)} - EOS: {meta['eos']}",
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
