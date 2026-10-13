"""The Run tab's live gauge traces (M6b).

The Tk app could only show gauges once a run had finished, which is the
wrong way round for what they are for: a gauge tells you whether the
shock has reached the point you care about, and that is a question you
ask WHILE the run is going.

What is actually checked, rather than assumed:

- the traces grow DURING the run, so the pane is live and not a
  post-mortem drawn early;
- nothing is collected while nobody is watching, because a native run
  copies the whole series on every live frame and a foam run re-reads
  blastProbes from the disk WSL is solving on;
- the decimation keeps the peak, which is the one sample that matters;
- a case with no gauges says so instead of waiting forever.

A real native 2D solve, no WSL. Offscreen.

Run:  cd blastlab/tests && python test_ui_live_gauges.py
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')
_dir = tempfile.mkdtemp(prefix='blastlab_live_gauges_')
_settings = os.path.join(_dir, 'settings.json')
with open(_settings, 'w', encoding='utf-8') as _f:
    _f.write('{"auto_cleanup": false}')
os.environ['BLASTLAB_SETTINGS'] = _settings

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def main():
    import numpy as np
    from blastlab.ui.testing import ensure_qapp, pump, use_model
    ensure_qapp()
    from blastlab.core.case import Case2D
    from blastlab.core.constants import P_AIR
    from blastlab.ui.app import MainWindow
    from blastlab.ui.live_gauges import (MAX_POINTS, NO_GAUGES, _decimate,
                                         _labels)

    print('G1: the decimation keeps what the trace is for')
    x = np.arange(20000, dtype=float)
    y = np.full(20000, 101.0)
    y[7777] = 4321.0                      # the shock, two samples wide
    y[7778] = 4000.0
    dx, dy = _decimate(x, y)
    check('a long trace is thinned for drawing',
          len(dx) <= MAX_POINTS + 1, f'{len(x)} -> {len(dx)}')
    check('and the peak survives it - a stride would have dropped it',
          abs(float(dy.max()) - 4321.0) < 1e-9, str(float(dy.max())))
    check('the newest sample is always kept',
          float(dx[-1]) == float(x[-1]), f'{dx[-1]} vs {x[-1]}')
    short_x, short_y = _decimate(x[:10], y[:10])
    check('a short trace is passed through untouched',
          len(short_x) == 10)

    print('\nG2: the labels name the gauge and where it ended up')
    check('2D points',
          _labels(dict(points=[(1.0, 2.0)]), 1)[0].startswith('G1'),
          _labels(dict(points=[(1.0, 2.0)]), 1)[0])
    check('and 1D radii read as radii',
          'r =' in _labels(dict(radii=[0.5]), 1)[0],
          _labels(dict(radii=[0.5]), 1)[0])

    print('\nG2b: GUI-16 round 2 (F-4): the enlarged card\'s peak label stays '
          'inside the plot')
    from blastlab.ui.run_gauges import _SelectedCard

    def card_row(peak_frac):
        t = np.linspace(0.0, 10.0, 400)
        k = int(round(peak_frac * 399))
        y = np.zeros_like(t)
        y[k] = 250.0
        return dict(label='G1', z=2.99, r=1.0, where='', waiting=False,
                    peak_kpa=250.0, t_ms=t, kpa=y, t_peak_ms=float(t[k]))

    card = _SelectedCard()
    card.resize(360, 200)
    card.show()
    pump(60)
    card.set_row(card_row(0.02), True, False)
    pump(60)
    box = card.plot.vb.sceneBoundingRect()
    lab = card.peak_lbl.sceneBoundingRect()
    check('an early peak (2 % of the range): the label lies inside the view',
          box.left() - 0.5 <= lab.left() and lab.right() <= box.right() + 0.5,
          f'label {lab.left():.1f}..{lab.right():.1f}, '
          f'view {box.left():.1f}..{box.right():.1f}')
    check('... and sits to the right of the peak (anchor -0.05)',
          card.peak_lbl.anchor[0] < 0, str(tuple(card.peak_lbl.anchor)))
    card.set_row(card_row(0.80), True, False)
    pump(60)
    check('a late peak (80 %): the anchor is today\'s, left of the peak',
          tuple(card.peak_lbl.anchor) == (1.05, 0.5),
          str(tuple(card.peak_lbl.anchor)))
    card.close()

    win = MainWindow()
    use_model(win)          # OUT-1: Run needs a runs folder and a model
    win.show()
    pump(150)
    rp = win.run_panel

    print('\nG3: nothing is collected while nobody is watching')
    check('the Run tab starts on the live slice, not on the gauges',
          not rp.watching_gauges(), rp.current_view())
    check('so the controller is not collecting',
          not getattr(win.ctrl, '_live_gauges', False))
    rp.show_gauges_tab()
    pump(30)
    check('opening the view turns collection on',
          win.ctrl._live_gauges and rp.watching_gauges())
    rp.show_slice_tab()
    pump(30)
    check('and leaving it turns collection off again',
          not win.ctrl._live_gauges)

    print('\nG4: a case with no gauges says so')
    win.setup.set_case(Case2D(geometry='planar', Lx=1.0, Ly=1.0,
                              cell_size_m=0.05, charge=1.0,
                              center=(0.3, 0.0), gauges=[],
                              gauge_file=None, n_snapshots=2,
                              record_frames=0, anim_file=None))
    win._schedule_validate()
    pump(200)
    rp.show_gauges_tab()
    pump(60)
    check('the placeholder explains it rather than waiting forever',
          rp.gauges._holder.text() == NO_GAUGES,
          repr(rp.gauges._holder.text()[:40]))
    rp.show_slice_tab()
    pump(20)

    print('\nG5: a real run, watched while it runs')
    case = Case2D(geometry='planar', Lx=2.0, Ly=1.2, cell_size_m=0.03,
                  charge=8.0, center=(0.4, 0.0),
                  bcs=dict(x_lo='reflect', x_hi='terminate',
                           y_lo='reflect', y_hi='terminate'),
                  gauges=[(1.0, 0.4), (1.6, 0.2)], gauge_file=None,
                  n_snapshots=2, record_frames=0, anim_file=None)
    win.setup.set_case(case)
    win._schedule_validate()
    pump(300)
    rp.show_gauges_tab()
    pump(30)
    win._run_single()
    seen = []
    t0 = time.time()
    while win.ctrl.running and time.time() - t0 < 420:
        pump(20)
        n = rp.gauges.n_points()
        if n and (not seen or n != seen[-1]):
            seen.append(n)
    pump(200)
    print(f'    the run took {time.time() - t0:.1f} s; '
          f'trace lengths seen: {seen[:3]} ... {seen[-3:]}')
    check('the run finished', not win.ctrl.running)
    check('the traces appeared DURING the run, not after it',
          len(seen) >= 3, f'{len(seen)} distinct lengths while running')
    check('and they grew as it went',
          len(seen) >= 2 and seen[-1] > seen[0],
          f'{seen[0] if seen else 0} -> {seen[-1] if seen else 0}')
    check('one curve per gauge', len(rp.gauges.curves) == 2,
          str(len(rp.gauges.curves)))
    check('the readout names the peak',
          'peak' in rp.gauges.peak_lbl.text(),
          rp.gauges.peak_lbl.text())

    print('\nG6: what is drawn is the overpressure the result reports')
    ent = win.results.entries()[-1] if win.results.entries() else None
    check('the run produced a result to compare against', ent is not None)
    if ent is not None:
        g = getattr(ent.result, 'gauges', None) or {}
        press = g.get('pressures')
        if press is not None and len(press):
            want = float(np.nanmax(
                (np.asarray(press[0], dtype=float) - P_AIR) / 1e3))
            drawn = float(np.nanmax(rp.gauges.curves[0].yData))
            check('the live peak matches the finished run\'s, in kPa',
                  abs(drawn - want) <= max(1e-6, 0.02 * abs(want)),
                  f'live {drawn:.3f} vs result {want:.3f} kPa')

    print('\nG7: a new run starts from a blank pane')
    rp._reset_readouts()
    pump(20)
    check('the traces were dropped', not rp.gauges.has_data())
    check('and the placeholder is back',
          rp.gauges._stack.currentIndex() == 0)

    win.close()
    pump(60)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'UI LIVE GAUGES: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
