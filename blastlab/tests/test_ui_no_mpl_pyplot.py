"""The Qt GUI process must never import `matplotlib.pyplot`.

pyplot keeps a global figure manager with its own event handling. In a
Qt application it fights the real event loop, and every figure it tracks
is kept alive until someone closes it by number - which is why the Tk
app grew `output/pyplot_bridge.py` and why every builder in
`output/plots.py` returns a bare `Figure`.

The rule is easy to break by accident from a long way off. It was:
`pg.colormap.getFromMatplotlib('inferno')` imports pyplot just to read a
colour table, so merely drawing a field on screen pulled it in. The
colours now come from `matplotlib.colormaps` instead.

This has to run in a FRESH interpreter, because `sys.modules` is global
and any earlier test that touched pyplot would mask the result.

Run:  cd blastlab/tests && python test_ui_no_mpl_pyplot.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_np_'),
                                   'settings.json'))

import numpy as np                                            # noqa: E402

from blastlab.ui.testing import ensure_qapp, pump             # noqa: E402

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def clean():
    return 'matplotlib.pyplot' not in sys.modules


def main():
    check('a fresh interpreter has no pyplot', clean())
    ensure_qapp()
    check('nor does building the QApplication', clean())

    from blastlab.ui.app import MainWindow
    check('nor importing the window module', clean())
    win = MainWindow()
    win.show()
    pump(60)
    check('nor constructing and showing the window', clean())

    for tab in ('setup', 'run', 'results', 'chain'):
        win._show(tab)
        pump(40)
        check(f'nor showing the {tab} tab', clean())

    # the colour table is the one that used to reach for pyplot, so a
    # field actually drawn on screen is the case that matters
    from blastlab.ui import pg_plots
    cmap, lut = pg_plots.inferno()
    check('nor building the inferno colour map', clean())
    check('and it is a full 256-step table',
          lut.shape[0] == pg_plots._LUT_N, str(lut.shape))

    from test_gui_results_fields import fake_2d, fake_3d
    check('nor importing the fixtures', clean())
    r2 = fake_2d()
    nx, ny = r2.meta['solid'].shape
    r2.meta['frames'] = dict(
        times=[0.0, 1e-4],
        pressures=[np.full((nx, ny), 101325.0 + 5e4),
                   np.full((nx, ny), 101325.0 + 1e4)])
    win.on_result(1, 2, 'Run 1 - 2D', r2)
    win.on_result(2, 3, 'Run 2 - 3D', fake_3d())
    win._show('results')
    pump(40)
    # GUI-7 T6: Field replaces the Fields and Animation tabs
    for view in ('Field', 'Gauges', '3D'):
        win.results.show_view(view)
        pump(40)
        check(f'nor drawing Results / {view} with real data', clean())
    # the two views that fall back to a matplotlib canvas are the most
    # likely to reach for pyplot by habit
    win.results.show_view('Field')
    win.results.fields.field_sel.setCurrentText('isosurface')
    pump(60)
    check('nor the 3D isosurface page, which IS matplotlib',
          clean() and win.results.fields.page() == 'figure')
    win.results.sel.setCurrentIndex(0)             # the 2D, with frames
    pump(40)
    win.results.field_view.start_play()
    pump(40)
    win.results.field_view.stop_play()
    check('nor replaying the animation', clean())
    # the snapshots play on the Field view's own timer
    win.results.field_view.field_seg.changed.emit('Density')
    pump(20)
    win.results.field_view.start_play()
    pump(40)
    win.results.field_view.stop_play()
    check('nor stepping the snapshots', clean())
    # This frame .png builds and saves a matplotlib figure: OO only
    from blastlab.ui import dialogs
    out = os.path.join(tempfile.mkdtemp(prefix='blastlab_np_png_'), 'f.png')
    real = dialogs.save_file
    dialogs.save_file = lambda *a, **k: out
    try:
        win.results.field_view.save_frame_png(threaded=False)
    finally:
        dialogs.save_file = real
    check('nor This frame .png', clean() and os.path.exists(out))
    check('and VTK is still nowhere near the GUI process',
          not [m for m in sys.modules
               if m.startswith(('vtk', 'pyvista'))],
          str([m for m in sys.modules
               if m.startswith(('vtk', 'pyvista'))][:3]))
    win.close()
    pump(40)

    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI NO PYPLOT: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
