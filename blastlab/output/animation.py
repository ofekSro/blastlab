"""Animation export of recorded pressure-slice frames.

Builds its own Figure + Agg canvas (never pyplot), so it is safe to call
from a GUI worker thread. GIF via PillowWriter; .mp4 uses ffmpeg when
available and silently falls back to GIF otherwise.
"""

import numpy as np
from matplotlib import animation
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .plots import mesh_for, overpressure_panel, set_frame, charge_label


def write_animation(meta, filename='blast_animation.gif', fps=15,
                    progress_callback=None, show_mesh=False):
    """
    Write the frames recorded by a run (meta['frames'] from
    record_frames > 0) to an animated .gif or .mp4.

    2D runs animate the full field; 3D runs animate the recorded live
    slice (user-selectable normal/position; default: the vertical x-z
    plane through the burst).
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
    mesh = overpressure_panel(
        ax, xf, yf, solid_sl.shape,
        mesh=mesh_for(meta, xf, yf, sl) if show_mesh else None)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    title = ax.set_title('')
    fig.colorbar(mesh, ax=ax, label='Overpressure [kPa]', shrink=0.85)
    fig.tight_layout()

    def draw(k):
        set_frame(mesh, pressures[k], solid_sl)
        title.set_text(f"{charge_label(meta)}  {plane}"
                       f"t = {times[k]*1e3:.3f} ms")
        return mesh,

    print(f"  Writing animation ({len(pressures)} frames) ... ",
          end='', flush=True)
    anim = animation.FuncAnimation(fig, draw, frames=len(pressures))
    anim.save(filename, writer=writer, dpi=100,
              progress_callback=progress_callback)
    print(f"done\n  Animation saved: {filename}")
    return filename
