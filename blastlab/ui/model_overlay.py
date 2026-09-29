"""GUI-5b (plan §5.3, board BC_Combined lines 161-214): what the Setup
model view draws OVER the shared preview.

`output/preview_draw.py` draws the case (it is shared with the Tk app and
pinned by test_ui_preview); this module adds, Qt-side and after that
drawing returns, on the same matplotlib axis:

  * dashed **Z rings** at Z = 1, 2, 3 around the burst point, radius
    Z · W^(1/3) (`scaled_distance.ring_radius`) - only where Z is shown;
  * the **selected node** highlighted - two rings and a tag around the
    charge for 01 Threat (board `chargeHi`), gauge halos and dashed
    charge → gauge lines labelled with R for 05 Gauges (`gaugeHi`);
  * the **hover readout** text `r · z · R · Z` (`hover_text`).

Display only: every artist is tagged with a gid (`overlay:<kind>`), kept
out of `tight_layout`, and removed before the next set is drawn, so a
replay never leaks artists. Nothing here is exported or saved.
"""

import math

import numpy as np

from ..output import preview_draw
from . import scaled_distance, theme

#: the ring values (plan §5.3) and their opacity, nearest first (board
#: lines 171-173: 0.65 / 0.5 / 0.38)
RING_Z = (1, 2, 3)
RING_ALPHA = (0.65, 0.5, 0.38)
GID = 'overlay'


def plane_caption(case):
    """The muted line at the top left of the view (board line 162)."""
    dim = getattr(case, 'dim', None)
    if dim == 1:
        return 'spherical sector · r from the charge'
    if dim == 2:
        if case.geometry == 'axisymmetric':
            return 'r–z plane · charge on the axis'
        return 'x–y plane · per metre of depth'
    if dim == 3:
        return '3D model · drag to orbit, wheel to zoom'
    return ''


def _burst_xy(case):
    """The burst point in the preview's axis coordinates."""
    if case.dim == 1:
        return 0.0, 0.0
    b = scaled_distance.burst_point(case)
    return float(b[0]), float(b[1])


def _gauge_xy(case):
    """[(x, y, R)] per gauge, where the preview draws it: 2D at the
    gauge; 1D on its arc at the label's angle (preview_draw puts `Gn` at
    0.55 of the drawn sector)."""
    out = []
    if case.dim == 1:
        half = math.radians(preview_draw.DRAW_DEG) * 0.55
        for g in case.gauge_radii or []:
            g = float(g)
            out.append((g * math.cos(half), g * math.sin(half), abs(g)))
        return out
    for g in case.gauges or []:
        out.append((float(g[0]), float(g[1]),
                    scaled_distance.distance(case, g)))
    return out


def hover_text(case, x, y):
    """The readout for the axis point (x, y): `r 2.95 · z 0.50 · R 3.31 ·
    Z 3.31` in 2D axisymmetric, `x · y · R` planar, `r · R · Z` in the 1D
    sector; '' where there is nothing to read."""
    dim = getattr(case, 'dim', None)
    if dim not in (1, 2) or x is None or y is None:
        return ''
    if dim == 1:
        r = math.hypot(float(x), float(y))
        bits = [f'r {r:.2f}', f'R {r:.2f}']
        z = scaled_distance.scaled_distance(case, (r,))
    else:
        axisym = case.geometry == 'axisymmetric'
        a, b = ('r', 'z') if axisym else ('x', 'y')
        R = scaled_distance.distance(case, (x, y))
        bits = [f'{a} {x:.2f}', f'{b} {y:.2f}', f'R {R:.2f}']
        z = scaled_distance.scaled_distance(case, (x, y))
    if z is not None:
        bits.append(f'Z {z:.2f}')
    return ' · '.join(bits)


class ModelOverlay:
    """The overlay state of one Setup panel: rings on/off and the
    selected node. `apply(ax, case)` (re)draws it on a preview axis."""

    def __init__(self):
        self.rings = True
        self.node = None
        self._artists = []

    # ── bookkeeping ──────────────────────────────────────────────────────
    def _keep(self, artist, kind):
        artist.set_gid(f'{GID}:{kind}')
        try:
            artist.set_in_layout(False)
        except Exception:
            pass
        self._artists.append(artist)
        return artist

    def clear(self):
        for a in self._artists:
            try:
                a.remove()
            except (ValueError, NotImplementedError, AttributeError):
                pass                    # already gone with an ax.clear()
        self._artists = []

    @staticmethod
    def found(ax, kind=None):
        """The overlay artists on `ax` (of one `kind`) - tests."""
        want = f'{GID}:{kind}' if kind else f'{GID}:'
        arts = list(ax.patches) + list(ax.lines) + list(ax.texts)
        return [a for a in arts if (a.get_gid() or '').startswith(want)]

    # ── drawing ──────────────────────────────────────────────────────────
    def apply(self, ax, case):
        """Draw the rings and the selection highlight for `case` on `ax`
        (called right after `preview_draw` has drawn the case)."""
        self.clear()
        if case is None or getattr(case, 'dim', None) not in (1, 2):
            return
        if self.rings and scaled_distance.z_shown(case):
            self._rings(ax, case)
        if self.node == 'threat':
            self._charge_hi(ax, case)
        elif self.node == 'gauges':
            self._gauge_hi(ax, case)

    def _rings(self, ax, case):
        x0, y0 = _burst_xy(case)
        accent, label = theme.cur('accent'), theme.cur('accent_text')
        half = math.radians(preview_draw.DRAW_DEG)
        for z, alpha in zip(RING_Z, RING_ALPHA):
            R = scaled_distance.ring_radius(case, z)
            if case.dim == 1:
                th = np.linspace(0.0, half, 64)
                (ln,) = ax.plot(R * np.cos(th), R * np.sin(th),
                                color=accent, lw=1.0, ls=(0, (3, 3)),
                                alpha=alpha, zorder=3.8)
                self._keep(ln, f'zring:{z}')
                at = half * 0.85
            else:
                th = np.linspace(0.0, 2 * math.pi, 181)
                (ln,) = ax.plot(x0 + R * np.cos(th), y0 + R * np.sin(th),
                                color=accent, lw=1.0, ls=(0, (3, 3)),
                                alpha=alpha, zorder=3.8)
                self._keep(ln, f'zring:{z}')
                at = math.radians(8.0)
            t = ax.text(x0 + R * math.cos(at), y0 + R * math.sin(at),
                        f' Z {z}', fontsize=7, family='monospace',
                        color=label, ha='left', va='bottom', zorder=3.9,
                        clip_on=True)
            self._keep(t, f'zlabel:{z}')

    def _charge_hi(self, ax, case):
        charged = case.dim == 1 or case.init_mode == 'charge'
        if not charged:
            return
        x0, y0 = _burst_xy(case)
        accent = theme.cur('accent')
        for ms, alpha, lw in ((22, 0.35, 1.0), (13, 0.7, 1.2)):
            (ln,) = ax.plot([x0], [y0], marker='o', ms=ms, mfc='none',
                            mec=accent, mew=lw, alpha=alpha, ls='none',
                            zorder=4.6)
            self._keep(ln, 'charge')
        w = scaled_distance.charge_mass(case)
        planar = case.dim == 2 and case.geometry == 'planar'
        tag = (f'Charge · {w:g} kg{"/m" if planar else ""} '
               f'{case.material}')
        t = ax.annotate(tag, (x0, y0), textcoords='offset points',
                        xytext=(14, 10), fontsize=7.5, fontweight='bold',
                        color=theme.cur('accent_soft'), zorder=4.7,
                        annotation_clip=False,
                        bbox=dict(boxstyle='round,pad=0.35',
                                  fc=theme.cur('accent_bg'),
                                  ec=theme.cur('accent_border'), lw=0.6))
        self._keep(t, 'chargetag')

    def _gauge_hi(self, ax, case):
        x0, y0 = _burst_xy(case)
        cyan = theme.cur('gauge')
        for k, (gx, gy, R) in enumerate(_gauge_xy(case), start=1):
            (halo,) = ax.plot([gx], [gy], marker='o', ms=18, color=cyan,
                              alpha=0.16, mew=0, ls='none', zorder=4.4)
            self._keep(halo, f'halo:{k}')
            if case.dim == 1:
                # in the sector every gauge lies on the one ray from the
                # charge and R is its radius: lines and labels would only
                # pile up at the apex (seen on the 1D screenshot)
                continue
            (ln,) = ax.plot([x0, gx], [y0, gy], color=cyan, lw=0.8,
                            ls=(0, (2, 3)), alpha=0.6, zorder=4.4)
            self._keep(ln, f'gline:{k}')
            t = ax.text((x0 + gx) / 2, (y0 + gy) / 2, f'R {R:.2f}',
                        fontsize=7, family='monospace', color=cyan,
                        ha='center', va='bottom', zorder=4.5, clip_on=True)
            self._keep(t, f'rlabel:{k}')
