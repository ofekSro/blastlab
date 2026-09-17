"""Animation export of recorded pressure-slice frames.

Builds its own Figure + Agg canvas (never pyplot), so it is safe to call
from a GUI worker thread. GIF via PillowWriter; .mp4 uses ffmpeg when
available and silently falls back to GIF otherwise.

The colour scale is fixed across the whole video by default (`scale
= 'run'`). It used to rescale on every frame, which made the colour bar
mean something different in each one: the shock never appeared to decay
and no two frames could be compared. 'frame' keeps that old behaviour
for a run whose late field would otherwise be a uniform blue, and
'manual' pins a range you choose - the only way to compare two videos
against each other.
"""

import numpy as np
from matplotlib import animation
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from ..core.constants import ANIM_SCALE_LABELS, ANIM_SCALES, P_AIR
from .plots import (add_gauge_markers, add_mesh_lines, gauge_points,
                    mesh_for, overpressure_panel, set_frame,
                    charge_label, titled)

#: how the colour range is chosen (see core.constants.ANIM_SCALES)
SCALES = ANIM_SCALES
SCALE_LABELS = ANIM_SCALE_LABELS


def frame_clim(pressures, solid=None):
    """One overpressure range [kPa] covering every recorded frame.

    Solid cells are excluded - a carved obstacle holds ambient pressure
    and would otherwise pin the minimum at zero. Returns None when the
    frames carry nothing finite."""
    lo, hi = np.inf, -np.inf
    for p in pressures:
        ovp = (np.asarray(p, dtype=np.float64) - P_AIR) / 1e3
        if solid is not None and np.shape(solid) == ovp.shape:
            ovp = np.where(solid, np.nan, ovp)
        if not np.isfinite(ovp).any():
            continue
        lo = min(lo, float(np.nanmin(ovp)))
        hi = max(hi, float(np.nanmax(ovp)))
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return None
    if hi <= lo:
        hi = lo + 1.0
    return lo, hi


def resolve_clim(meta, pressures, solid=None, scale=None, clim=None):
    """The (vmin, vmax) to pin the video to, and the scale actually used.

    `scale`/`clim` default to what the run recorded in its meta (the
    case's own choice), so a Result exported later keeps it; an explicit
    argument overrides. A 'manual' range that is missing or inverted
    falls back to 'run' rather than producing an unreadable video."""
    if scale is None:
        scale = meta.get('anim_scale') or 'run'
    scale = str(scale)
    if scale not in SCALES:
        scale = 'run'
    if clim is None:
        clim = meta.get('anim_clim')
    if scale == 'frame':
        return None, 'frame'
    if scale == 'manual' and clim is not None:
        try:
            lo, hi = float(clim[0]), float(clim[1])
        except (TypeError, ValueError, IndexError):
            lo = hi = 0.0
        if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
            return (lo, hi), 'manual'
        print('  [note] the animation colour range is unusable '
              f'({clim!r}) - using one range for the whole video')
    return frame_clim(pressures, solid), 'run'


def write_animation(meta, filename='blast_animation.gif', fps=15,
                    progress_callback=None, show_mesh=False,
                    title=None, scale=None, clim=None):
    """
    Write the frames recorded by a run (meta['frames'] from
    record_frames > 0) to an animated .gif or .mp4.

    2D runs animate the full field; 3D runs animate the recorded live
    slice (user-selectable normal/position; default: the vertical x-z
    plane through the burst).

    `scale` is one of SCALES and `clim` is the (vmin, vmax) overpressure
    range in kPa for `scale='manual'`; both default to what the run
    recorded in its meta.
    """
    frames = meta.get('frames')
    if not frames or len(frames['pressures']) == 0:
        print("  No animation frames recorded (record_frames=0?).")
        return None
    times, pressures = frames['times'], frames['pressures']

    if filename.lower().endswith('.mp4'):
        if animation.FFMpegWriter.isAvailable():
            writer = animation.FFMpegWriter(fps=fps)
        else:
            filename = filename[:-4] + '.gif'
            print(f"  [note] ffmpeg not found - writing GIF instead: {filename}")
            writer = animation.PillowWriter(fps=fps)
    else:
        writer = animation.PillowWriter(fps=fps)

    # Plane geometry: 2D uses the full grid; 3D the recorded live slice
    if 'z_face' in meta:            # 3D
        s_ax = meta.get('slice_axis', 'y')
        s0 = meta.get('s0', meta['j0'])
        faces = {'x': (meta['y_face'], meta['z_face']),
                 'y': (meta['x_face'], meta['z_face']),
                 'z': (meta['x_face'], meta['y_face'])}[s_ax]
        labels = {'x': ('y [m]', 'z [m]'), 'y': ('x [m]', 'z [m]'),
                  'z': ('x [m]', 'y [m]')}[s_ax]
        sl = tuple(s0 if a == 'xyz'.index(s_ax) else slice(None)
                   for a in range(3))
        extents = {'x': (meta['Ly'], meta['Lz']),
                   'y': (meta['Lx'], meta['Lz']),
                   'z': (meta['Lx'], meta['Ly'])}[s_ax]
        xf, yf = faces
        xlabel, ylabel = labels
        solid_sl = meta['solid'][sl]
        coord = meta[f'{s_ax}_c'][s0]
        plane = f"{s_ax} = {coord:.2f} m  "
        h_over_w = extents[1] / extents[0]
    else:                            # 2D
        xf, yf = meta['x_face'], meta['y_face']
        solid_sl = meta['solid']
        sl = None
        plane = ''
        xlabel = 'x [m]'
        ylabel = ('z [m]' if meta.get('geometry') == 'axisymmetric'
                  else 'y [m]')
        h_over_w = meta['Ly'] / meta['Lx']

    fig = Figure(figsize=(7, 7 * h_over_w + 1))
    FigureCanvasAgg(fig)
    ax = fig.add_subplot()
    # dynamic AMR runs record a level map per frame: the overlay is then
    # rebuilt per frame instead of drawn once from the predicted mesh
    levels = frames.get('levels')
    per_frame = bool(show_mesh and levels is not None)
    mesh = overpressure_panel(
        ax, xf, yf, solid_sl.shape,
        mesh=mesh_for(meta, xf, yf, sl) if show_mesh and not per_frame
        else None)
    lines = [None]
    # gauges: fixed positions, so drawn once (3D keeps only the ones the
    # animated plane actually cuts)
    add_gauge_markers(ax, gauge_points(meta, sl),
                      trigger=meta.get('trigger_gauge'))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    title_art = ax.set_title('')
    # one range for the whole video unless asked otherwise, so the
    # colour bar means the same thing in every frame
    fixed, used = resolve_clim(meta, pressures, solid_sl, scale, clim)
    bar_label = 'Overpressure [kPa]'
    if fixed is not None:
        mesh.set_clim(*fixed)
        scale_note = (f'{SCALE_LABELS[used]} '
                      f'{fixed[0]:.3g} .. {fixed[1]:.3g} kPa')
    else:
        # the label and the log line read off the same fact, so they
        # cannot disagree: 'run' with no finite cell anywhere (a plane
        # cut entirely through an obstacle) does rescale per frame
        bar_label += '  (rescaled per frame)'
        scale_note = (SCALE_LABELS['frame'] if used == 'frame' else
                      f'{SCALE_LABELS[used]} unavailable, no finite cell '
                      '- rescaling per frame')
    fig.colorbar(mesh, ax=ax, label=bar_label, shrink=0.85)
    fig.tight_layout()

    def draw(k):
        set_frame(mesh, pressures[k], solid_sl, clim=fixed)
        if per_frame:
            if lines[0] is not None:
                lines[0].remove()
            lv = levels[min(k, len(levels) - 1)]
            lines[0] = add_mesh_lines(ax, mesh_for(meta, xf, yf, sl,
                                                   levels=lv))
        title_art.set_text(titled(
            f"{charge_label(meta)}  {plane}"
            f"t = {times[k]*1e3:.3f} ms", title))
        return (mesh, lines[0]) if per_frame else (mesh,)

    print(f"  Writing animation ({len(pressures)} frames, "
          f"{scale_note}) ... ", end='', flush=True)
    anim = animation.FuncAnimation(fig, draw, frames=len(pressures))
    anim.save(filename, writer=writer, dpi=100,
              progress_callback=progress_callback)
    print(f"done\n  Animation saved: {filename}")
    return filename
