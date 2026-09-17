"""The Qt Results tab: picker, export gating, the four sub-views.

The port inverts the Tk flow. There, every interaction built a whole
matplotlib Figure and handed it to the multi-panel grid builder with
n=1. Here one persistent pyqtgraph image is reused and only the array is
uploaded, so the things worth pinning are: which selections reuse the
image and which rebuild it, that a robust-clipped map says so in words
(pyqtgraph has no `extend='max'` arrow), and that the FILE exports still
write the full grid even though the screen shows one panel.

Headless: QT_QPA_PLATFORM=offscreen, Agg, a private settings file, a
fake viewer link. No WSL, no solver, no window on screen.

Run:  cd blastlab/tests && python test_ui_results.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_ur_'),
                                   'settings.json'))

import numpy as np                                             # noqa: E402
from PySide6.QtCore import Qt                                   # noqa: E402

from blastlab.core.constants import ANIM_SCALE_LABELS, P_AIR    # noqa: E402
from blastlab.output import gauge_summary                       # noqa: E402
from blastlab.solvers.hooks import Result                       # noqa: E402
from blastlab.ui.testing import ensure_qapp, pump               # noqa: E402

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


# ── fixtures ─────────────────────────────────────────────────────────────
def with_gauges(res, n=3, fields=('p',)):
    """Give a Result gauge traces, optionally beyond pressure, so the
    summary table and the trace selector have something to show."""
    t = np.linspace(0.0, 2e-3, 40)
    traces = []
    for k in range(n):
        p = P_AIR + 300e3 * np.exp(-((t - 3e-4 * (k + 1)) / 2e-4) ** 2)
        traces.append(p)
    res.gauges = dict(times=t, points=[(0.2 * (k + 1), 0.3)
                                       for k in range(n)],
                      pressures=traces)
    if '|U|' in fields:
        res.gauges['speeds'] = [np.abs(p - P_AIR) / 400.0 for p in traces]
    if 'rho' in fields:
        res.gauges['rhos'] = [np.full_like(t, 1.2) for _ in traces]
    return res


def fake_1d():
    r = np.linspace(0.01, 2.0, 60)
    snap = dict(r=r, p=P_AIR + 200e3 * np.exp(-r), rho=np.full_like(r, 1.2),
                u=np.zeros_like(r))
    res = Result({'t = 0.100 ms (final)': snap},
                 dict(times=np.linspace(0, 2e-3, 30),
                      radii=[0.5, 1.0],
                      pressures=[P_AIR + 100e3 * np.ones(30),
                                 P_AIR + 50e3 * np.ones(30)]),
                 dict(eos='JWL', charge_kg=1.0, radius_m=2.0,
                      final_profile=np.column_stack(
                          [r, snap['p'], snap['rho'], snap['u']])),
                 'end time reached', False)
    return res


def peaky_2d():
    """A 2D result whose peak map really is a small hot spot.

    It needs its own, finer grid: the robust rule clips the top 0.5 %,
    so on the 10x8 grid of the shared fixture a single hot cell is 1.25 %
    of the field and correctly does NOT count as a tail.
    """
    from blastlab.core.grid import make_geometry
    Lx, Ly, dx = 1.0, 0.8, 0.02
    g = make_geometry('planar', Lx, Ly, dx)
    nx, ny = g['Nx'], g['Ny']
    p = np.full((nx, ny), P_AIR) + 1e3
    pk = np.full((nx, ny), P_AIR) + 1e3
    pk[0, 0] = P_AIR + 900e3          # 1 cell in 2000: a real tail
    meta = dict(x_c=g['x_c'], y_c=g['y_c'], x_face=g['x_face'],
                y_face=g['y_face'], solid=np.zeros((nx, ny), bool),
                geometry='planar', Lx=Lx, Ly=Ly, dx=dx, eos='idealGas',
                bcs={}, obstacles=[], charge=1.0,
                charge_center=(0.5, 0.4), r_exp=0.05, from_profile=False,
                p_peak=pk, impulse=np.full((nx, ny), 12.5))
    snaps = {'t = 0.100 ms (final)': dict(p=p, rho=np.full_like(p, 1.2),
                                          speed=np.zeros_like(p))}
    return Result(snaps, dict(times=np.array([]), points=[],
                              pressures=[]), meta,
                  'end time reached', False)


def frames_on(res, n=6, scale=None, clim=None):
    nx, ny = res.meta['solid'].shape
    res.meta['frames'] = dict(
        times=[1e-4 * k for k in range(n)],
        pressures=[np.full((nx, ny), P_AIR) + 400e3 / (k + 1)
                   for k in range(n)])
    if scale is not None:
        res.meta['anim_scale'] = scale
    if clim is not None:
        res.meta['anim_clim'] = clim
    return res


def main():
    ensure_qapp()
    from test_gui_results_fields import fake_2d, fake_3d
    from test_ui_view3d_host import FakeLink
    from blastlab.ui import dialogs, exports, pg_plots
    from blastlab.ui.results_panel import (PICKER_MAX, ResultsPanel,
                                           elide_middle)
    from blastlab.ui import results_gauges as RG

    log = []
    link = FakeLink()
    p = ResultsPanel(viewer_link=link, log_fn=log.append)
    p.resize(1280, 840)
    p.show()
    pump(50)

    print('\nR1: the picker')
    check('nothing selected -> nothing to export',
          all(not p.export_enabled(k) for k in p._export_btns))
    check('and every button says why',
          all(p._export_btns[k].toolTip() == 'Select a result first.'
              for k in p._export_btns))
    # four of these labels need 116-155 px and were pinned to 106, so
    # they read 'Animatio', 'Summary C', 'Gauges TS', 'Field CSV'
    cut = [b.text() for b in p._export_btns.values()
           if b.fontMetrics().horizontalAdvance(b.text())
           > b.width() - 15 - 6 - 24]
    check('no export label is cut off by its own button', not cut,
          str(cut))
    p.resize(900, 600)
    pump(60)
    cut = [b.text() for b in p._export_btns.values()
           if b.fontMetrics().horizontalAdvance(b.text())
           > b.width() - 15 - 6 - 24]
    check('nor at 900x600, where the row wraps instead of shrinking',
          not cut and p._export_row.rows() > 1,
          f'{cut} in {p._export_row.rows()} row(s)')
    p.resize(1280, 840)
    pump(60)
    a = p.add_result('run', 2, fake_2d())
    b = p.add_result('run', 2, fake_2d())
    pump(30)
    check('a duplicate label is numbered, not shadowed',
          [e.label for e in p.entries()] == ['run', 'run #2'],
          str([e.label for e in p.entries()]))
    check('the picker holds the entry itself, not its text',
          p.current() is b)
    p.sel.setCurrentIndex(0)
    pump(30)
    check('so selecting the first one reaches the first entry',
          p.current() is a)
    long = 'a-very-long-run-name-that-will-not-fit-in-the-picker (2D)'
    c = p.add_result(long, 2, fake_2d())
    pump(30)
    check('a long label is elided in the middle',
          len(c.display) == PICKER_MAX and '…' in c.display
          and c.display.endswith('(2D)'), c.display)
    check('and kept whole in the tooltip',
          p.sel.itemData(p.sel.currentIndex(), Qt.ToolTipRole) == long)
    check('elide_middle leaves a short label alone',
          elide_middle('short') == 'short')
    for ent in list(p.entries()):
        p.sel.setCurrentIndex(p.entries().index(ent))
        p.remove_current()
    pump(30)

    print('\nR2: an export is offered only when it can run')
    cases = [
        ('2D planar, no gauges, no frames', 2, fake_2d(),
         dict(profile=False, gif=False, vtk=False, summary=False,
              tsv=False, fieldcsv=True, report=True, pngs=True)),
        ('2D planar with gauges', 2, with_gauges(fake_2d()),
         dict(profile=False, gif=False, summary=True, tsv=True,
              pngs=True)),
        ('2D axisymmetric', 2, axi(fake_2d()),
         dict(profile=True)),
        ('2D with frames', 2, frames_on(fake_2d()),
         dict(gif=True)),
        ('3D', 3, fake_3d(), dict(profile=False, gif=False, pngs=True)),
        ('1D', 1, fake_1d(), dict(profile=True, gif=False, tsv=True,
                                  summary=True, pngs=True)),
    ]
    for name, dim, res, want in cases:
        ent = p.add_result(name, dim, res)
        pump(30)
        bad = {k: (p.export_enabled(k), v) for k, v in want.items()
               if p.export_enabled(k) != v}
        check(f'{name}', not bad, str(bad))
        off = [k for k in p._export_btns if not p.export_enabled(k)]
        check(f'{name}: every disabled button explains itself',
              all(p._export_btns[k].toolTip() for k in off),
              str([k for k in off if not p._export_btns[k].toolTip()]))
    check('vtk needs a live case dir, so it is off for all of these',
          not p.export_enabled('vtk'))
    # T34: in native mode the blastFoam-only launchers are not greyed,
    # they are gone - Qt keeps their place, so the Tk re-insert dance is
    # unnecessary here
    p.set_solver_mode('native')
    pump(20)
    check('native mode hides the foam launcher and the VTK export',
          p._foam_runs_btn.isHidden()
          and p._export_btns['vtk'].isHidden())
    p.set_solver_mode('blastfoam')
    pump(20)
    check('and blastFoam mode brings both back',
          not p._foam_runs_btn.isHidden()
          and not p._export_btns['vtk'].isHidden())
    # the browser's data sources are injectable precisely so this does
    # not reach WSL
    from blastlab.ui import run_browser as rb
    real_list, real_size = rb.default_lister, rb.default_sizer
    rb.default_lister = lambda: []
    rb.default_sizer = lambda dirs: {}
    try:
        win = p.open_run_browser()
        pump(40)
        check('the Foam runs button opens the browser', win is not None
              and win.isVisible())
        check('and asking again raises the same one, it does not stack',
              p.open_run_browser() is win)
        win.close()
        pump(20)
    finally:
        rb.default_lister, rb.default_sizer = real_list, real_size

    print('\nR3: Fields - one panel, reused where it can be')
    p.sel.setCurrentIndex(0)                      # the plain 2D result
    pump(30)
    f = p.fields
    check('2D offers the three fields plus the whole-run maps',
          [f.field_sel.itemText(i) for i in range(f.field_sel.count())]
          == ['overpressure', 'density', 'speed', 'peak overpressure',
              'net ovp impulse'])
    check('the newest snapshot is selected', f.snapshot().endswith('final)'))
    check('a map goes to the image page', f.page() == 'image')
    key = f._key
    f.field_sel.setCurrentText('density')
    pump(20)
    check('another field of the same grid reuses the image',
          f._key == key and f.image.levels == (1.2, 2.2),
          f'{f._key == key} {f.image.levels}')
    f.snap_sel.setCurrentIndex(0)
    pump(20)
    check('and so does another snapshot', f._key == key)
    check('the panel names the snapshot it is showing',
          f.snapshot() in f.title(), f.title())
    f.field_sel.setCurrentText('peak overpressure')
    pump(20)
    check('a whole-run map says so instead of a time',
          'whole run' in f.title(), f.title())

    pk = p.add_result('hot spot', 2, peaky_2d())
    pump(40)
    p.fields.field_sel.setCurrentText('peak overpressure')
    pump(20)
    check('a hot spot is clipped, as the exported PNG clips it',
          f.image.levels[1] < 100.0, str(f.image.levels))
    check('and the title says so in the exported wording',
          f.title().endswith(pg_plots.CLIP_TITLE_SUFFIX), f.title())
    f.field_sel.setCurrentText('overpressure')
    pump(20)
    check('a field with no hot spot is not clipped',
          not f.title().endswith(pg_plots.CLIP_TITLE_SUFFIX), f.title())
    check('the two clip strings are distinct and non-empty',
          pg_plots.CLIP_TITLE_SUFFIX.strip()
          and pg_plots.CLIP_BAR_SUFFIX.strip()
          and pg_plots.CLIP_TITLE_SUFFIX != pg_plots.CLIP_BAR_SUFFIX)
    # the Tk rule stands: gauges are marked on the live view and in the
    # exported video, never on a Fields map
    from blastlab.ui.pg_plots import GAUGE_COLOR
    items = f.plot.items
    check('Fields draws no gauge markers',
          not any(GAUGE_COLOR in repr(getattr(it, 'opts', ''))
                  for it in items)
          and len(items) <= 3, f'{len(items)} items')
    def segs():
        xs = f.overlay.item.getData()[0]
        return 0 if xs is None else len(xs)
    f.show_mesh.setChecked(True)
    pump(30)
    check('Show mesh draws the cell edges', segs() > 0, str(segs()))
    f.show_mesh.setChecked(False)
    pump(30)
    check('and unticking it clears them', segs() == 0, str(segs()))

    e3 = p.add_result('3d', 3, fake_3d())
    pump(40)
    check('3D offers both planes and the isosurface',
          f.field_sel.count() == 9
          and f.field_sel.itemText(8) == 'isosurface',
          str(f.field_sel.count()))
    kxz = f._key
    f.field_sel.setCurrentText('overpressure (x-y)')
    pump(20)
    check('a different plane rebuilds - different faces and mask',
          f._key != kxz)
    f.field_sel.setCurrentText('isosurface')
    pump(60)
    check('the isosurface is not a map, so it goes to matplotlib',
          f.page() == 'figure' and f.canvas.figure is not None)
    e1 = p.add_result('1d', 1, fake_1d())
    pump(60)
    check('and so are the 1D profiles',
          f.page() == 'figure' and f.canvas.figure is not None)
    check('1D offers exactly one entry',
          [f.field_sel.itemText(i) for i in range(f.field_sel.count())]
          == ['profiles'])

    print('\nR4: Gauges - the traces and the table')
    g = p.gauges
    check('1D: no trace selector (there is nothing to choose)',
          not g.selector_visible())
    check('the table has one column per summary field',
          len(RG.COLUMNS) == len(RG.HEADERS) == 8
          == g.table.columnCount() == len(gauge_summary.COLUMNS),
          f'{len(RG.COLUMNS)} {g.table.columnCount()} '
          f'{len(gauge_summary.COLUMNS)}')
    check('every header carries a tooltip',
          all(g.table.horizontalHeaderItem(i).toolTip()
              for i in range(g.table.columnCount())))
    check('the headers are the abbreviated set the report uses',
          RG.HEADERS[1] == 'Peak ovp [kPa]'
          and RG.HEADERS[-1] == 'Phase ended')
    gg = p.add_result('p only', 2, with_gauges(fake_2d()))
    pump(40)
    check('a p-only result still hides the selector',
          not g.selector_visible())
    check('but fills the table, one row per gauge',
          len(g.rows()) == 3, str(len(g.rows())))
    check('the rows are the shared summary formatting',
          g.rows() == [tuple(r) for r in
                       gauge_summary.table_rows(g.summary_rows(gg.result))])
    gm = p.add_result('three traces', 2,
                      with_gauges(fake_2d(), fields=('p', '|U|', 'rho')))
    pump(40)
    check('a result with more than p shows the selector',
          g.selector_visible())
    check('offering exactly what it recorded',
          g.field_seg.values() == ['p', '|U|', 'rho'],
          str(g.field_seg.values()))
    g.field_seg.changed.emit('|U|')
    pump(30)
    check('and switching it redraws that trace', g.field() == '|U|')
    p.sel.setCurrentIndex(p.entries().index(gg))
    pump(40)
    check('going back to a p-only result resets and hides it',
          g.field() == 'p' and not g.selector_visible())
    p.show_view('Gauges')
    # 1100x720 is the window's declared minimum, so every row must be
    # on screen there: this table is the only place the peak, arrival
    # and impulse numbers appear at all
    p.resize(1100, 720)
    pump(200)
    check('at the supported minimum every gauge row is on screen',
          g.table.verticalScrollBar().maximum() == 0
          and g.table.rowCount() == 3,
          f'scroll {g.table.verticalScrollBar().maximum()} '
          f'rows {g.table.rowCount()} h {g.table.height()}')
    check('and the table does not eat the traces',
          g.canvas.height() > g.table.height(),
          f'canvas {g.canvas.height()} vs table {g.table.height()}')
    # below the minimum the table scrolls rather than crowding the
    # traces out - that trade-off is the point of TABLE_MAX_SHARE
    p.resize(900, 600)
    pump(200)
    check('below the minimum the traces still win',
          g.canvas.height() > g.table.height()
          and g.table.height() <= int(g.height() * RG.TABLE_MAX_SHARE) + 2,
          f'canvas {g.canvas.height()} table {g.table.height()} '
          f'share {int(g.height() * RG.TABLE_MAX_SHARE)}')
    many = with_gauges(fake_2d(), n=12)
    p.add_result('twelve gauges', 2, many)
    # the export row may re-wrap and the table re-cap, and both change
    # the height the canvas gets; give the layout a full pass
    pump(200)
    check('twelve gauges scroll instead of squeezing the traces out',
          g.table.rowCount() == 12
          and g.table.maximumHeight() < 6 * g.table.rowHeight(0)
          and g.canvas.height() > g.table.height(),
          f'max {g.table.maximumHeight()} row {g.table.rowHeight(0)} '
          f'canvas {g.canvas.height()} table {g.table.height()}')
    p.sel.setCurrentIndex(p.entries().index(gg))
    pump(40)
    p.resize(1280, 840)
    pump(20)

    print('\nR5: Animation - replay, timer, slider')
    a2 = p.add_result('no frames', 2, fake_2d())
    pump(40)
    p.show_view('Animation')
    pump(20)
    an = p.anim
    check('a result with no frames says what to tick',
          'Record replay frames' in an.hint.text()
          and not an.play_btn.isEnabled())
    p.sel.setCurrentIndex(p.entries().index(e1))
    pump(40)
    check('a 1D result says it has no animation at all',
          '1D' in an.hint.text() and not an.play_btn.isEnabled(),
          an.hint.text())
    fr = p.add_result('frames', 2, frames_on(fake_2d()))
    pump(40)
    check('frames enable Play and size the slider',
          an.play_btn.isEnabled() and an.slider.maximum() == 5)
    check('and the first frame is drawn', an.frame() == 0
          and 't = 0.000 ms' in an.title(), an.title())
    calls = []
    real = an.show_frame
    an.show_frame = lambda k: (calls.append(k), real(k))[1]
    try:
        an.slider.setValue(3)
        pump(20)
        check('one slider move redraws exactly once',
              calls == [3], str(calls))
        check('and lands on that frame', an.frame() == 3
              and 't = 0.300 ms' in an.title(), an.title())
        calls.clear()
        an.start_play()
        an._tick()
        an._tick()
        check('a tick redraws once per frame, not twice',
              calls == [4, 5], str(calls))
        check('play swaps the button to Pause',
              an.play_btn.text() == 'Pause' and an.playing())
        calls.clear()
        p.title_box.setText('for the report')
        pump(20)
        check('a title edit redraws the CURRENT frame, not frame 0',
              calls and calls[-1] == 5, str(calls))
        check('and the typed line is on it',
              'for the report' in an.title(), an.title())
        p.title_box.setText('')
        pump(20)
    finally:
        an.show_frame = real
    an.start_play()
    p.sel.setCurrentIndex(p.entries().index(a2))
    pump(40)
    check('switching result stops the timer',
          not an.playing() and not an.timer.isActive())
    p.sel.setCurrentIndex(p.entries().index(fr))
    pump(40)

    print('\nR5b: playback speed')
    from blastlab.ui.results_anim import (MIN_INTERVAL_MS, SPEED_DEFAULT,
                                          SPEED_FACTORS, TICK_MS)
    check('it starts at 1x, the rate the Tk app had and could not change',
          an.speed_sel.currentText() == SPEED_DEFAULT
          and an.speed() == 1.0 and an.timer.interval() == TICK_MS,
          f'{an.speed_sel.currentText()} {an.timer.interval()} ms')
    rates = {}
    for lbl in SPEED_FACTORS:
        an.speed_sel.setCurrentText(lbl)
        pump(10)
        rates[lbl] = 1000.0 / an.timer.interval() * an.frame_step()
        check(f'{lbl} never asks the timer for less than the '
              f'{MIN_INTERVAL_MS} ms it can deliver',
              an.timer.interval() >= MIN_INTERVAL_MS,
              f'{an.timer.interval()} ms')
    ordered = [rates[k] for k in SPEED_FACTORS]
    check('and the frame rate rises monotonically with the setting',
          all(b > a for a, b in zip(ordered, ordered[1:])),
          str({k: round(v, 1) for k, v in rates.items()}))
    check('a 4x replay really is about four times a 1x one',
          abs(rates['4x'] / rates['1x'] - 4.0) < 0.3,
          f"{rates['1x']:.1f} -> {rates['4x']:.1f} frames/s")
    an.speed_sel.setCurrentText(SPEED_DEFAULT)
    pump(10)
    # the speed is a playback control and must not reach the export
    check('and it stays out of the export options',
          'speed' not in str(an.export_opts()).lower(),
          str(an.export_opts()))

    print('\nR6: the animation colour scale, here as well as in Setup')
    check('the replay pins one range for the whole video by default',
          an.scale() == 'run' and an.scale_used() == 'run',
          f'{an.scale()} / {an.scale_used()}')
    lv_run = an.image.levels
    check('that range spans the whole run, not the frame on screen',
          abs(lv_run[1] - 400.0) < 1e-6
          and abs(lv_run[0] - 400.0 / 6) < 1e-3, str(lv_run))
    an.slider.setValue(5)
    pump(20)
    check('so the decayed frame keeps the same range',
          an.image.levels == lv_run, f'{lv_run} -> {an.image.levels}')
    an.scale_sel.setCurrentText(ANIM_SCALE_LABELS['frame'])
    pump(20)
    check('per frame rescales it', an.image.levels != lv_run
          and an.scale_used() == 'frame', str(an.image.levels))
    check('and the bar says it is rescaling',
          'rescaled per frame' in bar_label(an.image))
    an.scale_sel.setCurrentText(ANIM_SCALE_LABELS['manual'])
    an.min_box.setText('0')
    an.max_box.setText('900')
    an.max_box.editingFinished.emit()
    pump(20)
    check('a manual range is honoured', an.image.levels == (0.0, 900.0)
          and an.scale_used() == 'manual', str(an.image.levels))
    check('the boxes show only in manual mode', an.manual_visible())
    an.max_box.setText('')
    an.max_box.editingFinished.emit()
    pump(20)
    check('an unusable range falls back, it does not break the replay',
          an.scale_used() == 'run' and an.image.levels == lv_run,
          f'{an.scale_used()} {an.image.levels}')
    check('the export carries the same choice',
          p.export_opts()['anim_scale'] == 'manual'
          and p.export_opts()['anim_clim'] is None,
          str(p.export_opts()))
    # the whole-video range costs a pass over every recorded frame
    # (measured: 2.6 s for 150 frames of 1000x1000), so toggling the
    # selector back and forth must not pay for it again
    from blastlab.output import animation as anim_mod
    calls = []
    real_resolve = anim_mod.resolve_clim
    anim_mod.resolve_clim = lambda *a, **k: (calls.append(1)
                                             or real_resolve(*a, **k))
    try:
        an.scale_sel.setCurrentText(ANIM_SCALE_LABELS['run'])
        pump(20)
        an._clim_cache.clear()                # measure from cold
        calls.clear()
        for scale in ('frame', 'run', 'frame', 'run'):
            an.scale_sel.setCurrentText(ANIM_SCALE_LABELS[scale])
            pump(20)
        check('four switches over two scales cost two computations',
              len(calls) == 2, f'{len(calls)} calls')
    finally:
        anim_mod.resolve_clim = real_resolve
    prev = dict(an._clim_cache)
    an.set_result(fr)
    pump(20)
    check('but a different result starts from scratch',
          an._clim_cache != prev or not prev, str(len(an._clim_cache)))
    an.scale_sel.setCurrentText(ANIM_SCALE_LABELS['run'])
    pump(20)
    mres = frames_on(fake_2d(), scale='manual', clim=(10.0, 40.0))
    p.add_result('run chose manual', 2, mres)
    pump(40)
    check("a result adopts the scale ITS run recorded",
          an.scale() == 'manual' and an.clim() == (10.0, 40.0)
          and an.image.levels == (10.0, 40.0), str(an.image.levels))

    print('\nR7: what the exports actually write')
    out = tempfile.mkdtemp(prefix='blastlab_rx_')
    # a run name means the files are prefixed, so three runs do not all
    # propose the same names
    gg.result.meta['name'] = 'my run/2'
    p.sel.setCurrentIndex(p.entries().index(gg))     # 2D + gauges
    pump(40)
    check('a run name becomes a filename-safe prefix',
          exports.name_prefix(gg.result) == 'my_run_2_',
          exports.name_prefix(gg.result))
    check('and no name means no prefix',
          exports.name_prefix(fr.result) == '')
    real_dir, real_save = dialogs.pick_dir, dialogs.save_file
    dialogs.pick_dir = lambda *a, **k: out
    try:
        p.export('pngs', threaded=False)
        pump(20)
    finally:
        dialogs.pick_dir = real_dir
    pngs = sorted(f for f in os.listdir(out) if f.endswith('.png'))
    check('PNGs writes the FULL grid, not the one panel on screen',
          len(pngs) > 1, str(pngs))
    figs = exports.png_figures(gg.result, 2)
    check('and at least one of those figures has several axes',
          any(f is not None and len(f.axes) > 1 for _n, f in figs),
          str([0 if f is None else len(f.axes) for _n, f in figs]))
    check('every file is prefixed with the run name',
          all(f.startswith('my_run_2_') for f in pngs), str(pngs))

    gif = os.path.join(out, 'x.gif')
    p.sel.setCurrentIndex(p.entries().index(fr))
    pump(40)
    an.scale_sel.setCurrentText(ANIM_SCALE_LABELS['manual'])
    an.min_box.setText('0')
    an.max_box.setText('700')
    an.max_box.editingFinished.emit()
    pump(20)
    seen = {}
    real_write = exports.write_animation
    exports.write_animation = lambda m, fn, **kw: seen.update(
        dict(kw, target=fn))
    dialogs.save_file = lambda *a, **k: gif
    try:
        p.export('gif', threaded=False)
        pump(20)
    finally:
        exports.write_animation = real_write
        dialogs.save_file = real_save
    check("the Animation export uses the view's colour scale",
          seen.get('scale') == 'manual'
          and seen.get('clim') == (0.0, 700.0)
          and seen.get('target') == gif, str(seen))

    dialogs.save_file = lambda *a, **k: ''
    try:
        check('cancelling a dialog writes nothing',
              p.export('report', threaded=False) == '')
    finally:
        dialogs.save_file = real_save
    errs = []
    n_log = len(log)
    exports.run_export('report', gg, os.path.join(out, 'no', 'x.html'),
                       log=log.append)
    check('a failed export lands in the log, it does not raise',
          any('Export failed' in s for s in log[n_log:]),
          str(log[n_log:]))
    check('an unknown kind is refused, not guessed',
          exports.pick_target('nonsense', gg, log=errs.append) == ''
          and errs)

    print('\nR7b: a post-mortem load crosses back to the GUI thread')
    import threading as _th
    from blastlab.solvers.foam import postmortem as pm
    loaded = fake_2d()
    loaded.meta['name'] = 'stopped run'
    where = {}
    real_load = pm.load_run

    def fake_load(path):
        where['thread'] = _th.current_thread().name
        return loaded
    pm.load_run = fake_load
    try:
        n_before = len(p.entries())
        p.load_foam_run_path('/root/blastlab_runs/whatever')
        for _ in range(200):                      # the loader is a thread
            pump(10)
            if len(p.entries()) > n_before:
                break
        check('the run was read off the GUI thread',
              where.get('thread', 'MainThread') != 'MainThread',
              str(where))
        check('and the entry arrived anyway, named and labelled',
              len(p.entries()) == n_before + 1
              and p.entries()[-1].label == 'stopped run (loaded, 2D)',
              str([e.label for e in p.entries()[-2:]]))
        check('an empty path is a no-op, not a crash',
              p.load_foam_run_path('') is None
              and len(p.entries()) == n_before + 1)
        n_log = len(log)
        pm.load_run = lambda path: (_ for _ in ()).throw(
            RuntimeError('no such run'))
        p.load_foam_run_path('/root/blastlab_runs/gone')
        for _ in range(100):
            pump(10)
            if any('Load failed' in s for s in log[n_log:]):
                break
        check('a failed load lands in the log, not in a dialog',
              any('Load failed' in s for s in log[n_log:]),
              str(log[n_log:]))
    finally:
        pm.load_run = real_load

    print('\nR8: Remove clears every sub-view')
    while p.entries():
        p.sel.setCurrentIndex(0)
        p.remove_current()
    pump(40)
    check('no entries left', not p.entries() and p.current() is None)
    check('every export is off again',
          all(not p.export_enabled(k) for k in p._export_btns))
    check('Fields is blank', p.fields.page() == 'empty'
          and p.fields.image is None)
    check('the gauge table is empty', p.gauges.rows() == [])
    # not blank-blank: an empty panel said nothing at all, so each
    # sub-view now names what would put something in it
    check('the replay says what would fill it, and holds no image',
          'Record replay frames' in p.anim.hint.text()
          and p.anim.image is None, repr(p.anim.hint.text()[:40]))
    check('and so do Fields and Gauges',
          'appear here' in p.fields.hint.text()
          and p.gauges.canvas.figure is not None,
          repr(p.fields.hint.text()[:40]))
    check('Remove with nothing selected says so, it does not raise',
          (p.remove_current() or True)
          and any('select a result first' in s.lower() for s in log))

    print('\nR9: the 3D surface replays a finished result')
    # three snapshots, so the HUD really has something to count in
    r3 = fake_3d()
    snap = r3.snapshots['t = 0.100 ms (final)']
    r3.snapshots = {f't = {0.1 * (k + 1):.3f} ms': dict(snap, t=1e-4 * k)
                    for k in range(3)}
    p.add_result('3d run', 3, r3)
    pump(40)
    n0 = len(link.sent)
    p.open_3d()
    # the feed runs on a 1 ms timer; drive it by hand so the count is
    # not a race against the event loop
    p.view3d._feed_timer.stop()
    scenes = [m for m in link.sent[n0:] if m[0] == 'scene']
    check('opening it builds a scene on the results surface',
          len(scenes) == 1 and scenes[0][1] == 'results',
          str([m[0] for m in link.sent[n0:]]))
    check('and switches to the 3D view', p.view() == '3D')
    check('with a feed armed but not yet finished',
          p.view3d.feeding())
    n1 = len(link.sent)
    for _ in range(len(r3.snapshots) + 2):
        p.view3d._feed_step()
    huds = [m for m in link.sent[n1:] if m[0] == 'hud']
    check('one snapshot per tick, counted in the HUD',
          len(huds) == 3 and 'loading 1/3' in huds[0][2], str(huds))
    check('the last tick clears the counter', huds[-1][2] == '')
    check('and the feed reports done',
          any(m[0] == 'done' for m in link.sent[n1:]))
    check('extra ticks are harmless once it is finished',
          not p.view3d.feeding())
    p.view3d.feed_result(r3)
    p.view3d._feed_timer.stop()
    check('a new feed re-arms', p.view3d.feeding())
    state = p.view3d._feed_state
    p.view3d.feed_result(r3)
    p.view3d._feed_timer.stop()
    check('a second feed replaces the first, it does not run beside it',
          p.view3d.feeding() and p.view3d._feed_state is not state)
    p.view3d.cancel_feed()
    check('and it can be cancelled', not p.view3d.feeding()
          and not p.view3d._feed_timer.isActive())
    p.view3d.feed_result(r3)
    p.shutdown()
    check('shutdown stops the feed', not p.view3d.feeding())

    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI RESULTS: PASS ({len(RAN)} checks)')


def axi(res):
    """Make a 2D result axisymmetric, so the profile export applies."""
    res.meta['geometry'] = 'axisymmetric'
    return res


def bar_label(image):
    """Whatever the colour bar's axis is currently labelled."""
    for axis in ('right', 'left'):
        try:
            text = image.bar.getAxis(axis).labelText
            if text:
                return text
        except Exception:
            pass
    return ''


if __name__ == '__main__':
    main()
