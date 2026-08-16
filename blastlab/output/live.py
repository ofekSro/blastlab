"""Matplotlib live-view window for CLI runs (pyplot-based, interactive).

The GUI does NOT use this - it embeds its own canvas and receives frames
through GuiHooks. This window is created lazily by ConsoleHooks when a
CLI run asks for a live view on an interactive backend.
"""

import matplotlib.pyplot as plt
import numpy as np

from ..core.constants import P_AIR


class LiveView:
    """Live-updating overpressure window fed by RunHooks.frame.

    `info` comes from RunHooks.run_started: x_face, y_face (the two face
    coordinate arrays of the displayed plane), solid (2D mask on that
    plane), xlabel, ylabel, title.
    """

    def __init__(self, info):
        plt.ion()
        self.solid = info['solid']
        Nx, Ny = self.solid.shape
        self.fig, ax = plt.subplots(figsize=(7, 7 * Ny / Nx + 1))
        cmap = plt.cm.inferno.copy()
        cmap.set_bad('0.5')
        self.mesh = ax.pcolormesh(info['x_face'], info['y_face'],
                                  np.zeros((Ny, Nx)), cmap=cmap,
                                  shading='flat')
        ax.set_xlabel(info['xlabel'])
        ax.set_ylabel(info['ylabel'])
        ax.set_aspect('equal')
        self._prefix = info.get('title', '')
        self.title = ax.set_title(f'{self._prefix}  t = 0.000 ms'.strip())
        self.fig.colorbar(self.mesh, ax=ax, label='Overpressure [kPa]',
                          shrink=0.85)
        self.fig.canvas.manager.set_window_title('blastlab - live')
        self.fig.tight_layout()
        self.fig.show()

    def update(self, p, t):
        ovp = np.where(self.solid, np.nan,
                       (p.astype(np.float64) - P_AIR) / 1e3)
        self.mesh.set_array(ovp.T)
        hi = np.nanmax(ovp)
        lo = np.nanmin(ovp)
        if hi <= lo:
            hi = lo + 1.0
        self.mesh.set_clim(lo, hi)
        self.title.set_text(f'{self._prefix}  t = {t*1e3:.3f} ms'.strip())
        self.fig.canvas.draw_idle()
        plt.pause(0.001)   # let the GUI event loop breathe

    def close(self):
        plt.ioff()
        # leave the final frame on screen; plt.show() at the end blocks on it
