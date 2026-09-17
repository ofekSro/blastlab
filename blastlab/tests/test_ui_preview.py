"""The setup previews: `output/preview_draw` puts the documented
artists on a bare matplotlib axis (boundary styles per BC kind,
obstacles, refinement zones, the charge, gauges, all three mesh
branches), and the Qt 3D bridge throttles rebuilds and ignores edits
the picture does not depend on.

The 1D/2D checks need no Qt at all; the bridge check uses a recording
stub in place of the viewer link."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')

from matplotlib.collections import LineCollection           # noqa: E402
from matplotlib.figure import Figure                        # noqa: E402
from matplotlib.patches import Circle, Rectangle             # noqa: E402

from blastlab.core import refine                             # noqa: E402
from blastlab.core.case import Case1D, Case2D, Case3D        # noqa: E402
from blastlab.output import preview_draw                     # noqa: E402

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def axis():
    return Figure(figsize=(5, 5)).add_subplot()


def rects(ax):
    return [p for p in ax.patches if isinstance(p, Rectangle)]


def circles(ax):
    return [p for p in ax.patches if isinstance(p, Circle)]


def texts(ax):
    return [t.get_text() for t in ax.texts]


def main():
    pal = preview_draw.palette(dark=True)

    print("\nP1: 2D boundary kinds each get their own line style")
    case = Case2D(geometry='planar', Lx=4.0, Ly=3.0, cell_size_m=0.1,
                  charge=1.0, center=(2.0, 0.5),
                  bcs=dict(x_lo='reflect', x_hi='terminate',
                           y_lo='transmit', y_hi='transmit'))
    ax = axis()
    preview_draw.draw_2d(ax, case, pal=pal)
    bnd = ax.lines[:4]
    check("four boundary lines", len(bnd) == 4, str(len(ax.lines)))
    wall = [ln for ln in bnd if ln.get_linewidth() == 2.5]
    check("reflect is one solid bold wall",
          len(wall) == 1 and wall[0].get_linestyle() == '-',
          str([(ln.get_linewidth(), ln.get_linestyle()) for ln in bnd]))
    check("reflect uses the wall colour",
          wall[0].get_color() == pal['wall'], wall[0].get_color())
    # get_linestyle() reports every dash tuple as '--', so compare the
    # patterns themselves
    dashes = {str(getattr(ln, '_unscaled_dash_pattern', None))
              for ln in bnd if ln.get_linewidth() != 2.5}
    check("terminate and transmit are dashed differently",
          len(dashes) == 2, str(dashes))
    check("the title spells out the key",
          'wall: solid, open: dashed' in ax.get_title(), ax.get_title())
    check("planar keeps x as x", ax.get_xlabel() == 'x [m]',
          ax.get_xlabel())
    # matplotlib reports 'equal' back as the ratio 1.0
    check("equal aspect", ax.get_aspect() in ('equal', 1.0),
          str(ax.get_aspect()))
    x0, x1 = ax.get_xlim()
    check("the domain is padded 4 % each side",
          abs(x0 + 0.04 * 4.0) < 1e-9 and abs(x1 - 4.0 * 1.04) < 1e-9,
          f'{x0:g}..{x1:g}')

    print("\nP2: axisymmetric labels r, and pins what it draws")
    ax = axis()
    preview_draw.draw_2d(ax, Case2D(geometry='axisymmetric', Lx=2.0,
                                    Ly=2.0, cell_size_m=0.1, charge=1.0,
                                    center=(1.0, 0.5)), pal=pal)
    check("axisym labels the radial axis", ax.get_xlabel() == 'r [m]',
          ax.get_xlabel())
    check("the charge is drawn on the axis",
          circles(ax) and abs(circles(ax)[0].center[0]) < 1e-12,
          str(circles(ax)[0].center if circles(ax) else None))

    print("\nP3: obstacles, the charge and the gauges")
    case = Case2D(geometry='planar', Lx=4.0, Ly=4.0, cell_size_m=0.1,
                  charge=2.0, center=(1.0, 1.0),
                  obstacles=[(2.0, 2.5, 0.0, 1.0), (3.0, 3.4, 0.0, 0.6)],
                  gauges=[(0.5, 0.5), (3.8, 2.0)])
    ax = axis()
    preview_draw.draw_2d(ax, case, pal=pal)
    filled = [r for r in rects(ax) if r.get_fill()]
    check("one filled rectangle per obstacle", len(filled) == 2,
          str(len(filled)))
    check("the charge is a circle at the burst point",
          circles(ax) and circles(ax)[0].center == (1.0, 1.0),
          str(circles(ax)[0].center if circles(ax) else None))
    check("the charge circle has a visible floor radius",
          circles(ax)[0].radius >= 0.004 * 4.0)
    check("each gauge is labelled",
          'G1' in texts(ax) and 'G2' in texts(ax), str(texts(ax)))
    ax = axis()
    preview_draw.draw_2d(ax, Case2D(init_mode='profile1d', charge=None,
                                    Lx=2.0, Ly=2.0, cell_size_m=0.1),
                         pal=pal)
    check("a remap case marks the origin instead of a charge circle",
          not circles(ax) and any(ln.get_marker() == 'x'
                                  for ln in ax.lines))

    print("\nP4: refinement zones are coloured by level, and labelled")
    # 'zone' charge refinement keeps the base cell, so this case can
    # actually be planned; with 'global' the 8-cell charge rule forces
    # 83 M cells, plan_levels refuses, and the preview correctly draws
    # no zones at all (the validation strip carries the reason)
    case = Case2D(geometry='planar', Lx=4.0, Ly=4.0, cell_size_m=0.05,
                  charge=1.0, center=(2.0, 1.0), solver='blastfoam',
                  charge_refine='zone',
                  refine_zones=[(1.0, 3.0, 0.0, 2.0, 2)])
    ax = axis()
    preview_draw.draw_2d(ax, case, pal=pal)
    hollow = [r for r in rects(ax) if not r.get_fill()]
    check("every planned zone is a hollow dashed box",
          len(hollow) == len(preview_draw._plan(case).zones)
          and all(r.get_linestyle() == '--' for r in hollow),
          str(len(hollow)))
    mine = [r for r in hollow if abs(r.get_x() - 1.0) < 1e-9]
    check("the requested zone is drawn where it was asked for",
          len(mine) == 1 and abs(mine[0].get_width() - 2.0) < 1e-9,
          str([(r.get_x(), r.get_width()) for r in hollow][:3]))
    check("in its level's colour",
          tuple(round(v, 6) for v in mine[0].get_edgecolor()[:3])
          == tuple(round(v, 6) for v in _rgb(refine.LEVEL_COLORS[1])),
          str(mine[0].get_edgecolor()))
    check("and carries its level label", 'L2' in texts(ax),
          str(texts(ax)[:4]))
    ax = axis()
    preview_draw.draw_2d(ax, Case2D(geometry='planar', Lx=4.0, Ly=4.0,
                                    cell_size_m=0.05, charge=1.0,
                                    center=(2.0, 1.0), solver='blastfoam',
                                    refine_zones=[(1.0, 3.0, 0.0, 2.0, 2)]),
                         pal=pal)
    check("an unplannable case draws no zones instead of raising",
          not [r for r in rects(ax) if not r.get_fill()])

    print("\nP5: detonation points are told apart from charges")
    case = Case2D(geometry='planar', Lx=4.0, Ly=4.0, cell_size_m=0.2,
                  charge=1.0, center=(2.0, 1.0), solver='blastfoam',
                  det_points=[(1.0, 0.5), (3.0, 0.5)])
    ax = axis()
    preview_draw.draw_2d(ax, case, pal=pal)
    check("one marker and one label per detonation point",
          'D1' in texts(ax) and 'D2' in texts(ax), str(texts(ax)))
    check("they are red, not the charge orange",
          any(ln.get_color() == preview_draw.DET_COLOR for ln in ax.lines))

    print("\nP6: all three mesh branches")
    base = dict(geometry='planar', Ly=4.0, charge=1.0, center=(2.0, 1.0),
                solver='blastfoam')
    # a case small enough that the predicted mesh is actually drawable
    # (a big charge in a small box needs no refinement to resolve it)
    ax = axis()
    note = preview_draw.draw_2d(
        ax, Case2D(geometry='planar', Lx=1.0, Ly=1.0, cell_size_m=0.02,
                   charge=50.0, center=(0.5, 0.25), solver='blastfoam'),
        show_mesh=True, pal=pal)
    lcs = [c for c in ax.collections if isinstance(c, LineCollection)]
    check("the mesh is one line collection", len(lcs) == 1, str(len(lcs)))
    check("drawn faint", lcs[0].get_linewidth()[0] == 0.35
          and abs(lcs[0].get_alpha() - 0.6) < 1e-9)
    check("the note counts the cells", 'cells' in note, note)
    ax = axis()
    note = preview_draw.draw_2d(ax, Case2D(Lx=4.0, cell_size_m=0.2,
                                           amr_levels=2, **base),
                                show_mesh=True, pal=pal)
    check("an AMR case says the mesh follows the shock",
          'AMR L2 follows the shock' in note, note)
    ax = axis()
    note = preview_draw.draw_2d(ax, Case2D(Lx=4.0, cell_size_m=0.004,
                                           **base),
                                show_mesh=True, pal=pal)
    check("too fine to draw falls back to the base grid",
          'too fine to draw' in note, note)
    ax = axis()
    preview_draw.draw_2d(ax, Case2D(Lx=4.0, cell_size_m=0.2, **base),
                         show_mesh=False, pal=pal)
    check("without Show mesh there is no mesh collection",
          not [c for c in ax.collections
               if isinstance(c, LineCollection)])

    print("\nP7: the 1D spherical sector")
    case = Case1D(radius_m=8.0, charge_kg=2.0, cell_size_m=0.01,
                  gauge_radii=[1.0, 4.0, 99.0], bc_outer='terminate')
    ax = axis()
    note = preview_draw.draw_1d(ax, case, pal=pal)
    polys = [p for p in ax.patches
             if type(p).__name__ == 'Polygon']
    check("the sector and the charge are filled polygons",
          len(polys) == 2, str([type(p).__name__ for p in ax.patches]))
    check("it says it is a sector and how big",
          'spherical sector' in ax.get_title() and 'R = 8 m'
          in ax.get_title(), ax.get_title())
    check("radial axis only", ax.get_xlabel() == 'r [m]'
          and list(ax.get_yticks()) == [], ax.get_ylabel())
    check("gauges inside the domain are labelled, the one outside is not",
          'G1' in texts(ax) and 'G2' in texts(ax)
          and 'G3' not in texts(ax), str(texts(ax)))
    check("the charge label carries the true radius",
          any('kg TNT' in t and 'r =' in t for t in texts(ax)),
          str(texts(ax)))
    ax = axis()
    note = preview_draw.draw_1d(ax, case, show_mesh=True, pal=pal)
    check("Show mesh thins the faces and says so",
          'cells' in note and 'drawn' in note, note)
    ax = axis()
    preview_draw.draw_1d(ax, Case1D(radius_m=0.0), pal=pal)
    check("a zero-radius case draws nothing rather than raising",
          not ax.axison)

    print("\nP8: the 3D bridge throttles, and ignores what does not show")
    from blastlab.ui.testing import ensure_qapp, pump
    ensure_qapp()
    from blastlab.ui.preview_panel import Preview3DBridge

    class FakeHost:
        def __init__(self):
            self.geos = []

        def show_geometry(self, geo):
            self.geos.append(geo)
            return True

    host = FakeHost()
    bridge = Preview3DBridge.__new__(Preview3DBridge)
    from PySide6.QtCore import QTimer
    bridge.host = host
    bridge._log = print
    bridge._key = None
    bridge._pending = None
    bridge._last_build = -1e9
    bridge._timer = QTimer()
    bridge._timer.setSingleShot(True)
    bridge._timer.timeout.connect(bridge._flush)

    c3 = Case3D(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.1, charge=5.0,
                center=(1.0, 1.0, 0.5))
    bridge.show_case(c3)
    check("the first edit renders at once", len(host.geos) == 1,
          str(len(host.geos)))
    key0 = bridge._key
    bridge._last_build = -1e9                    # pretend the wait passed
    bridge.show_case(Case3D(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.1,
                            charge=5.0, center=(1.0, 1.0, 0.5),
                            cfl=0.11, gauge_file='other.txt',
                            n_snapshots=9))
    check("cfl / file name / snapshot count do not rebuild the scene",
          len(host.geos) == 1 and bridge._key == key0, str(len(host.geos)))
    bridge._last_build = -1e9
    bridge.show_case(Case3D(Lx=3.0, Ly=2.0, Lz=2.0, cell_size_m=0.1,
                            charge=5.0, center=(1.0, 1.0, 0.5)))
    check("a geometry edit does", len(host.geos) == 2, str(len(host.geos)))
    n0 = len(host.geos)
    for lx in (3.1, 3.2, 3.3, 3.4, 3.5):         # a keystroke burst
        bridge.show_case(Case3D(Lx=lx, Ly=2.0, Lz=2.0, cell_size_m=0.1,
                                charge=5.0, center=(1.0, 1.0, 0.5)))
    check("a burst is collapsed while the throttle holds",
          len(host.geos) == n0, str(len(host.geos) - n0))
    pump(700)
    check("and lands once when it expires",
          len(host.geos) == n0 + 1, str(len(host.geos) - n0))
    check("the last value of the burst is the one drawn",
          abs(host.geos[-1]['Lx'] - 3.5) < 1e-12, str(host.geos[-1]['Lx']))

    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
        sys.exit(1)
    print("All preview checks passed.")


def _rgb(hex_colour):
    h = hex_colour.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


if __name__ == '__main__':
    main()
