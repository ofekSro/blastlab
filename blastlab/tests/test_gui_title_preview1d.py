"""The Results title line (T58) and the 1D model preview (T59, T60).

T58: a line of the user's own is added ABOVE the automatic title (which
     carries the charge, the field and, on an animation, the running
     time) - never replacing it - on the field maps, the gauge plots,
     the replay, the exported animation and the HTML report. It lives on
     the Results panel, not on the case.
T59: 1D gets a model preview: the spherical sector blastFoam meshes,
     with the charge radius inside it, the gauge radii marked and an
     optional cell-face overlay. Drawn from the axis (0 deg) to 30 deg.
T60: the far end of that sector takes the same three boundary kinds the
     2D/3D sides do, and the preview draws it in the same language.

Headless (Agg, hidden Tk root). Needs customtkinter, no WSL.
Run:  cd blastlab/tests && python test_gui_title_preview1d.py
"""
import math
import os
import sys

import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import Case1D                           # noqa: E402
from blastlab.output import plots                               # noqa: E402
from test_gui_results_fields import fake_2d, fake_3d            # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def suptitle_of(fig):
    return fig._suptitle.get_text() if fig._suptitle is not None else ''


def main():
    import customtkinter as ctk
    from blastlab.gui.preview_panel import Preview1DPanel
    from blastlab.gui.results_panel import ResultsPanel

    root = ctk.CTk()
    root.withdraw()

    print("\nT58 titled()")
    check('no extra -> the automatic title, untouched',
          plots.titled('auto') == 'auto'
          and plots.titled('auto', None) == 'auto'
          and plots.titled('auto', '   ') == 'auto')
    check('the extra line goes ABOVE, keeping the automatic one',
          plots.titled('auto', 'Mine') == 'Mine\nauto')

    print("\nT58 the figure builders take it")
    r2, r3 = fake_2d(), fake_3d()
    figs = plots.figures_fields_2d(r2.snapshots, r2.meta,
                                   title_extra='Case A')
    check('2D field set: every figure carries the line',
          figs and all(suptitle_of(f).startswith('Case A\n')
                       for _n, f in figs),
          str([suptitle_of(f).split(chr(10))[0] for _n, f in figs]))
    check('...and still carries the automatic one under it',
          all('2D Blast' in suptitle_of(f) for _n, f in figs))
    figs3 = plots.figures_fields_3d(r3.snapshots, r3.meta,
                                    title_extra='Case A')
    check('3D field set: every figure carries the line',
          figs3 and all(suptitle_of(f).startswith('Case A\n')
                        for _n, f in figs3))
    check('no extra -> no blank first line',
          not suptitle_of(plots.figures_fields_2d(
              r2.snapshots, r2.meta)[0][1]).startswith('\n'))
    g2 = plots.figure_gauges_nd(r2.gauges, r2.meta, title_extra='Case A')
    check('2D/3D gauge figure', g2 is None
          or suptitle_of(g2).startswith('Case A\n'))

    print("\nT58 the Results panel")
    panel = ResultsPanel(root)
    check('the panel has a title box', hasattr(panel, 'title_var'))
    check('empty box -> None (nothing is added)',
          panel.title_extra() is None)
    panel.title_var.set('  Blast study 3  ')
    check('the box is trimmed', panel.title_extra() == 'Blast study 3')
    panel.title_var.set('')
    check('back to nothing', panel.title_extra() is None)
    import inspect
    # Phase 6: _export hands the writing to services.exports.run_export,
    # so the export figure calls live there now (test_gui_char_exports.py
    # pins the titled files the Tk panel writes)
    from blastlab.services import exports as svc_exports
    src = inspect.getsource(ResultsPanel) + inspect.getsource(svc_exports)
    for what in ('figure_results_1d', 'figure_gauges_1d',
                 'figure_gauges_nd', 'figures_fields_2d',
                 'figures_fields_3d', 'figure_isosurfaces_3d'):
        check(f'{what} is called with the title',
              f'plots.{what}' in src and 'title_extra' in src)
    check('the exported animation gets it',
          'title=title_extra' in src)
    check('the report heading gets it',
          'title=title_extra or ent.label' in src)
    exp_src = inspect.getsource(ResultsPanel._export)
    check('the title is read on the Tk thread, not in the worker',
          exp_src.index('title_extra = self.title_extra()')
          < exp_src.index('def work()'))

    print("\nT58 write_animation takes a title")
    sig = inspect.signature(
        __import__('blastlab.output.animation', fromlist=['x'])
        .write_animation)
    check('write_animation(title=...)', 'title' in sig.parameters
          and sig.parameters['title'].default is None)

    print("\nT59 the 1D preview")
    p1 = Preview1DPanel(root)
    case = Case1D(radius_m=4.0, charge_kg=8.0, cell_size_m=0.004,
                  gauge_radii=[1.5, 2.5, 3.5])
    p1.show_case(case)
    ax = p1._ax
    n_plain = len(ax.lines)
    check('the sector is drawn (two lateral faces + the outlet arc)',
          n_plain >= 3, f'{n_plain} lines')
    check('the charge is a filled patch inside it',
          len(ax.patches) + len(ax.collections) >= 1)
    ttl = ax.get_title()
    check('the title is just the sector and its radius (T60)',
          ttl.startswith('1D spherical sector') and 'R = 4 m' in ttl
          and 'drawn at' not in ttl, ttl)
    ys = [y for ln in ax.lines for y in ln.get_ydata()]
    check('the sector sits on the axis: nothing below y = 0 (T60)',
          min(ys) >= -1e-9, f'min y = {min(ys):.3g}')
    check('...and opens to 30 degrees',
          abs(max(ys) - 4.0 * math.sin(math.radians(30.0))) < 1e-6,
          f'max y = {max(ys):.4g}')
    from blastlab.core.case import validate_case as _vc
    check('the charge label carries the true radius',
          any(f'{_vc(case).r_exp:.4g}' in t.get_text() for t in ax.texts),
          str([t.get_text() for t in ax.texts]))

    p1.show_case(case, show_mesh=True)
    n_mesh = len(p1._ax.lines)
    check('show mesh adds the radial cell faces', n_mesh > n_plain,
          f'{n_mesh} vs {n_plain}')
    check('...thinned, not one arc per cell (1,000 cells here)',
          n_mesh < 200, f'{n_mesh} lines')
    check('the mesh note names the cell size and the count',
          '0.004' in p1._ax.get_title()
          and '1,000' in p1._ax.get_title(), p1._ax.get_title())

    # a small charge on a big domain must not vanish into the apex
    small = Case1D(radius_m=10.0, charge_kg=0.25, cell_size_m=0.001)
    p1.show_case(small, show_mesh=True)
    check('a tiny charge is drawn at a visible floor, and says so',
          any('drawn enlarged' in t.get_text() for t in p1._ax.texts),
          str([t.get_text() for t in p1._ax.texts]))
    from blastlab.core.case import validate_case
    r_true = f'{validate_case(small).r_exp:.4g}'
    check('the true radius is still the one printed',
          any(r_true in t.get_text() for t in p1._ax.texts),
          f'{r_true} not in '
          + str([t.get_text() for t in p1._ax.texts]))

    # a case that cannot be drawn must not raise
    p1.show_case(Case1D(radius_m=0.0, charge_kg=1.0))
    check('a zero radius is handled, not raised', True)

    print("\nT60 the outer boundary kind")
    from blastlab.core.bc import BC_KINDS
    from blastlab.core.case import case_from_dict, case_to_dict
    check('the default is what 1D always did',
          Case1D().bc_outer == 'terminate')
    check('it round-trips through a case file',
          case_from_dict(case_to_dict(
              Case1D(bc_outer='reflect'))).bc_outer == 'reflect')
    styles = {}
    for kind in BC_KINDS:
        p1.show_case(Case1D(radius_m=4.0, charge_kg=8.0,
                            cell_size_m=0.05, bc_outer=kind))
        # the outlet arc is the last of the three boundary lines drawn.
        # get_linestyle() normalises every custom dash to '--', so the
        # dash pattern itself is what tells transmit from terminate
        arc = p1._ax.lines[2]
        styles[kind] = (arc.get_linestyle(),
                        arc._unscaled_dash_pattern,
                        round(arc.get_linewidth(), 2))
    check('each kind draws the outer arc differently',
          len(set(styles.values())) == 3, str(styles))
    check('a reflecting end is the bold solid one, as in 2D',
          styles['reflect'][2] > styles['transmit'][2]
          and styles['reflect'][0] == '-', str(styles))
    check('terminate and transmit are both dashed but not alike',
          styles['terminate'][0] == styles['transmit'][0] == '--'
          and styles['terminate'][1] != styles['transmit'][1],
          str(styles))

    from blastlab.gui.forms import CaseForm
    f1 = CaseForm(root, 1)
    check('the 1D form defaults to terminate',
          f1.get_case().bc_outer == 'terminate')
    f1.set_case(Case1D(bc_outer='transmit'))
    check('the form round-trips it', f1.get_case().bc_outer == 'transmit')

    print("\nT59 the Setup panel routes 1D to it")
    from blastlab.gui.forms import SetupPanel
    sp = SetupPanel(root)
    check('SetupPanel builds the 1D preview', hasattr(sp, 'preview1d'))
    sp.dim_var.set(1)
    sp.update_preview(case)
    check('a 1D case selects the 1D preview widget',
          sp._prev_current is sp.preview1d)
    sp.show_mesh_var.set(True)
    sp._mesh_toggled()
    check('Show mesh reaches it', sp._prev_current is sp.preview1d
          and len(sp.preview1d._ax.lines) > n_plain)

    root.destroy()


if __name__ == '__main__':
    main()
    print()
    print('GUI TITLE / 1D PREVIEW: '
          + ('PASS' if not FAILS
             else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
