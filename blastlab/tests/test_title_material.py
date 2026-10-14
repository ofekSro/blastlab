"""GUI-16 round 2, F-1: every figure title names the charge's material
(batch docs/batches/2026-10-13-gui-final-round2.md, B1; P1-9 decision 1).

A blastFoam C4 result titles its figures `kg C4` - the 1D screen title,
both 1D export figures (`png_figures`, `report_figures`), the 2D and 3D
field and gauge figures and the 2D map on screen; a planar 2D C4 reads
`kg/m C4`. A meta with no material (native) and a TNT meta give exactly
today's strings, and each dimension keeps its own number format (D-R5:
1D `1.0`, 2D/3D `1`). Nothing is written to a meta (D-R9).

No WSL, no solve: synthetic results; one offscreen FieldsView, no window.

Run:  cd blastlab/tests && python test_title_material.py
"""
import copy
import os
import sys
from types import SimpleNamespace

import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.core.grid import make_geometry, make_grid          # noqa: E402
from blastlab.models.meta import charge_label as m_charge       # noqa: E402
from blastlab.output import plots                               # noqa: E402
from blastlab.services import exports                           # noqa: E402
from blastlab.solvers.hooks import Result                       # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def titles(fig):
    """Every title text of a figure: the suptitle and each axis title."""
    out = [ax.get_title() for ax in fig.axes]
    sup = getattr(fig, '_suptitle', None)
    if sup is not None:
        out.append(sup.get_text())
    return [t for t in out if t]


def result_1d(**extra):
    t = np.linspace(0.0, 2e-3, 40)
    r = np.linspace(0.0, 2.0, 20)
    snaps = {'t = 1.000 ms': dict(r=r, p=np.full_like(r, P_AIR) + 1e3,
                                  rho=np.full_like(r, 1.2),
                                  u=np.zeros_like(r))}
    gauges = dict(times=t, radii=[0.5],
                  pressures=[P_AIR + 5e4 * np.exp(-((t - 4e-4) / 2e-4) ** 2)])
    meta = dict(radius_m=2.0, charge_kg=1.0, eos='JWL', r_exp=0.05, **extra)
    return Result(snaps, gauges, meta, 'end time reached', False)


def gauges_nd(dim):
    t = np.linspace(0.0, 2e-3, 40)
    pt = (0.6, 0.4) if dim == 2 else (0.6, 0.5, 0.4)
    return dict(times=t, points=[pt],
                pressures=[P_AIR + 5e4 * np.exp(-((t - 4e-4) / 2e-4) ** 2)])


def result_2d(geometry='axisymmetric', **extra):
    Lx, Ly, dx = 1.0, 0.8, 0.1
    g = make_geometry(geometry, Lx, Ly, dx)
    nx, ny = g['Nx'], g['Ny']
    p = np.full((nx, ny), P_AIR) + 1e3
    snaps = {'t = 0.100 ms (final)': dict(p=p, rho=np.full_like(p, 1.2),
                                          speed=np.zeros_like(p))}
    meta = dict(x_c=g['x_c'], y_c=g['y_c'], x_face=g['x_face'],
                y_face=g['y_face'], solid=np.zeros((nx, ny), dtype=bool),
                geometry=geometry, Lx=Lx, Ly=Ly, dx=dx, eos='JWL', bcs={},
                obstacles=[], charge=1.0, charge_center=(0.5, 0.4),
                r_exp=0.05, from_profile=False, p_peak=p + 5e3,
                impulse=np.full_like(p, 12.5), **extra)
    return Result(snaps, gauges_nd(2), meta, 'end time reached', False)


def result_3d(**extra):
    Lx, Ly, Lz, dx = 1.2, 1.0, 0.8, 0.2
    grid = make_grid(Lx, Ly, Lz, dx)
    x_c, y_c, z_c = grid['x_c'], grid['y_c'], grid['z_c']
    nx, ny, nz = len(x_c), len(y_c), len(z_c)
    p = np.full((nx, ny, nz), P_AIR, dtype=np.float32) + 1e3
    p[nx // 2, ny // 2, nz // 2] += 5e4
    snap = dict(p=p, rho_xz=np.full((nx, nz), 1.2, np.float32),
                rho_xy=np.full((nx, ny), 1.2, np.float32), t=1e-4)
    meta = dict(x_c=x_c, y_c=y_c, z_c=z_c, x_face=grid['x_face'],
                y_face=grid['y_face'], z_face=grid['z_face'],
                j0=ny // 2, k0=nz // 2, slice_axis='y', s0=ny // 2,
                solid=np.zeros((nx, ny, nz), dtype=bool), Lx=Lx, Ly=Ly,
                Lz=Lz, dx=dx, eos='JWL', bcs={}, obstacles=[], charge=1.0,
                charge_center=(Lx / 2, Ly / 2, Lz / 2), r_exp=0.1,
                r_src=0.1, from_profile=None, **extra)
    return Result({'t = 0.100 ms (final)': snap}, gauges_nd(3), meta,
                  'end time reached', False)


def all_titles(res, dim):
    out = []
    for _name, fig in exports.png_figures(res, dim):
        out += titles(fig)
    for _cap, fig in exports.report_figures(res, dim):
        out += titles(fig)
    return out


def check_1d():
    print('\n1D: the screen title and both export figures')
    c4 = result_1d(material='C4', solver='blastfoam')
    keep = copy.deepcopy(c4.meta)
    got = all_titles(c4, 1)
    want = ['1D Spherical Blast - 1.0 kg C4 - EOS: JWL',
            'Gauge Time Histories - 1.0 kg C4 - EOS: JWL']
    check('png_figures and report_figures: both figures say `1.0 kg C4`',
          all(sum(w in t for t in got) == 2 for w in want)
          and not any('TNT' in t for t in got), str(got))
    check('the meta is not written to (D-R9)', c4.meta.keys() == keep.keys()
          and c4.meta['material'] == 'C4', str(sorted(c4.meta)))

    from blastlab.ui import results_fields as RFS
    c = RFS.screen_label_1d(c4.meta)
    check('screen_title_1d names the material',
          RFS.screen_title_1d(c, 'C4') == '1D spherical · 1.0 kg C4 · JWL',
          RFS.screen_title_1d(c, 'C4'))
    check('screen_title_1d without a material is today\'s',
          RFS.screen_title_1d(c) == '1D spherical · 1.0 kg TNT · JWL',
          RFS.screen_title_1d(c))

    # the on-screen figure itself, through the Results engine
    from blastlab.ui.testing import ensure_qapp
    ensure_qapp()
    fv = RFS.FieldsView()
    hints = []
    fv.export_hint.connect(hints.append)
    fv.set_result(SimpleNamespace(result=c4, dim=1, label='c4',
                                  display='c4'))
    on_screen = fv.canvas.figure.axes[0].get_title()
    check('FieldsView: the 1D canvas title says `kg C4`',
          on_screen == '1D spherical · 1.0 kg C4 · JWL', on_screen)
    check('FieldsView: the export hint quotes the C4 export title',
          bool(hints) and hints[-1].endswith(want[0]), str(hints[-1:]))
    fv.set_result(SimpleNamespace(result=result_1d(), dim=1, label='n',
                                  display='n'))
    on_screen = fv.canvas.figure.axes[0].get_title()
    check('FieldsView: a native 1D result keeps `kg TNT`',
          on_screen == '1D spherical · 1.0 kg TNT · JWL', on_screen)
    fv.deleteLater()

    for name, res in (('no material', result_1d()),
                      ('TNT', result_1d(material='TNT',
                                        solver='blastfoam'))):
        got = all_titles(res, 1)
        check(f'1D, {name}: exactly today\'s titles',
              '1D Spherical Blast - 1.0 kg TNT - EOS: JWL' in got
              and 'Gauge Time Histories - 1.0 kg TNT - EOS: JWL' in got
              and not any('C4' in t for t in got), str(got))
    c = m_charge(result_1d().meta)
    built = plots.figure_results_1d(result_1d().snapshots, c.eos,
                                    c.charge_kg, c.radius_m)
    check('the builder without `material` keeps its title (the :1580 pin)',
          built.axes[0].get_title()
          == f'1D Spherical Blast - {c.charge_kg} kg TNT - EOS: {c.eos}')


def check_nd():
    print('\n2D / 3D: the field and gauge titles')
    for dim, res in ((2, result_2d(material='C4', solver='blastfoam')),
                     (3, result_3d(material='C4', solver='blastfoam'))):
        got = all_titles(res, dim)
        fields = [t for t in got if 'Gauge Time Histories' not in t
                  and t.count(' - ') >= 1 and 'Blast' in t]
        gauge = [t for t in got if t.startswith('Gauge Time Histories')]
        check(f'{dim}D C4: every field title says `1 kg C4`',
              bool(fields) and all('1 kg C4' in t for t in fields)
              and not any('TNT' in t for t in got), str(fields[:2]))
        check(f'{dim}D C4: the gauge figure says `1 kg C4`',
              len(gauge) == 2 and all('1 kg C4' in t for t in gauge),
              str(gauge))
    from blastlab.ui import results_fields as RFS
    res = result_2d(material='C4', solver='blastfoam')
    sel = RFS.select_field(res, 2, 't = 0.100 ms (final)', 'overpressure')
    check('2D C4: the map title on screen says `kg C4`',
          sel['title'] == 'overpressure - 1 kg C4', sel['title'])

    pl = result_2d('planar', material='C4', solver='blastfoam')
    got = all_titles(pl, 2)
    check('planar 2D C4: `1 kg/m C4`',
          plots.charge_label(pl.meta) == '1 kg/m C4'
          and any('1 kg/m C4' in t for t in got), str(got[:1]))

    for name, extra in (('no material', {}), ('TNT', dict(material='TNT'))):
        for dim, res in ((2, result_2d(**extra)), (3, result_3d(**extra))):
            got = all_titles(res, dim)
            check(f'{dim}D, {name}: `1 kg TNT` as today',
                  plots.charge_label(res.meta) == '1 kg TNT'
                  and not any('C4' in t for t in got)
                  and any('1 kg TNT' in t for t in got), str(got[:1]))
    check('planar 2D, no material: `1 kg/m TNT` as today',
          plots.charge_label(result_2d('planar').meta) == '1 kg/m TNT')
    check('a remapped start keeps its label whatever the material',
          plots.charge_label(dict(from_profile='1d', material='C4'))
          == '1D remap'
          and plots.charge_label(dict(from_profile='2d', material='C4'))
          == '2D remap')


def check_cli_1d():
    print('\nthe blastFoam CLI\'s 1D pop-up figures (cli_run._show_plots_1d)')
    import matplotlib
    import matplotlib.pyplot as plt
    from blastlab.output import pyplot_bridge
    from blastlab.solvers.foam import cli_run
    got = []
    saved = (matplotlib.get_backend, pyplot_bridge.adopt_figure, plt.show)
    matplotlib.get_backend = lambda: 'TkAgg'     # past its Agg early return
    pyplot_bridge.adopt_figure = got.append
    plt.show = lambda *a, **k: None
    try:
        case = SimpleNamespace(charge_kg=1.0, radius_m=2.0)
        for mat, word in (('C4', 'C4'), (None, 'TNT')):
            got.clear()
            extra = dict(material=mat) if mat else {}
            cli_run._show_plots_1d(result_1d(**extra), case)
            kg = [t for f in got for t in titles(f) if ' kg ' in t]
            check(f'CLI 1D, {mat or "no material"}: both pop-ups say '
                  f'`1.0 kg {word}`',
                  len(kg) == 2 and all(f'1.0 kg {word} ' in t for t in kg),
                  str(kg))
    finally:
        matplotlib.get_backend, pyplot_bridge.adopt_figure, plt.show = saved


def check_rule():
    print('\nthe rule: plots.charge_material')
    cm = plots.charge_material
    check('argument, else meta, else TNT',
          cm({'material': 'C4'}, 'PETN') == 'PETN'
          and cm({'material': 'C4'}) == 'C4'
          and cm({}) == 'TNT' and cm(None) == 'TNT'
          and cm({'material': ''}) == 'TNT'
          and cm({'material': None}) == 'TNT')


if __name__ == '__main__':
    check_rule()
    check_1d()
    check_nd()
    check_cli_1d()
    print()
    print('TITLE MATERIAL: ' + ('PASS' if not FAILS else
                                f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
