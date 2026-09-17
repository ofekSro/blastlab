"""Real Qt window, real worker, real native 2D solver, all the way out
to the Results tab and a file on disk.

The other Qt e2e (`_e2e_ui_native_warn.py`) ends at the Run tab. This one
carries on: the finished run must arrive in the Results picker, every
sub-view must draw from it, the animation must replay the frames it
recorded with ONE colour range, and `PNGs` must write the full snapshot
grid - not the single panel the Fields view shows.

No WSL, no viewer child (a 2D run has no 3D scene). Offscreen by
default; `--window` shows the real thing.

Run:  cd blastlab/tests && python _e2e_ui_native.py
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS', os.path.join(
    tempfile.mkdtemp(prefix='blastlab_ui_e2e_'), 'settings.json'))

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def main():
    from blastlab.ui.testing import ensure_qapp, pump
    ensure_qapp(offscreen='--window' not in sys.argv)
    from blastlab.core.case import Case2D
    from blastlab.core.constants import ANIM_SCALE_LABELS
    from blastlab.ui import dialogs
    from blastlab.ui.app import MainWindow

    out = tempfile.mkdtemp(prefix='blastlab_ui_e2e_out_')
    case = Case2D(geometry='planar', Lx=2.0, Ly=1.2, cell_size_m=0.04,
                  charge=5.0, center=(0.4, 0.0),
                  obstacles=[(1.0, 1.3, 0.0, 0.5)],
                  bcs=dict(x_lo='reflect', x_hi='terminate',
                           y_lo='reflect', y_hi='terminate'),
                  gauges=[(0.9, 0.6), (1.8, 0.2)],
                  gauge_file=os.path.join(out, 'gauges.txt'),
                  n_snapshots=3, record_frames=12,
                  anim_file=None)

    win = MainWindow()
    win.show()
    pump(200)
    win.setup.set_case(case)
    win._schedule_validate()
    pump(400)
    check('the form adopted the case',
          abs(win.current_case().Lx - 2.0) < 1e-12)

    print('\nE1: run it with the accelerator, as a user would')
    t0 = time.time()
    win._run_single()                       # what F5 is bound to
    check('the Run tab came forward', win.current_tab() == 'run')
    for _ in range(3000):                   # <= 5 min
        pump(100)
        if not win.ctrl.running:
            break
    print(f'    run took {time.time() - t0:.1f} s')
    log = win.run_panel.log_text()
    check('the run finished', '[run finished]' in log)
    check('with no ui error while draining',
          '[ui error handling' not in log)

    print('\nE2: the result reached the Results tab on its own')
    res = win.results
    check('one entry in the picker', len(res.entries()) == 1,
          str([e.label for e in res.entries()]))
    ent = res.entries()[0]
    check('labelled as a 2D run', ent.dim == 2 and '2D' in ent.label,
          ent.label)
    check('and it is the selected one', res.current() is ent)
    win._show('results')
    pump(80)

    print('\nE3: Fields drew the real field')
    check('the image page is showing', res.fields.page() == 'image')
    check('it holds real overpressure, not a blank',
          res.fields.image is not None
          and res.fields.image.levels[1] > 1.0,
          str(None if res.fields.image is None
              else res.fields.image.levels))
    check('the obstacle mask came through',
          res.fields.image.mask is not None)
    check('the title names the snapshot',
          res.fields.snapshot() in res.fields.title(),
          res.fields.title())
    fields = [res.fields.field_sel.itemText(i)
              for i in range(res.fields.field_sel.count())]
    check('and the whole-run maps are offered',
          'peak overpressure' in fields, str(fields))
    for name in fields:
        res.fields.field_sel.setCurrentText(name)
        pump(30)
    check('every field drew without an error',
          res.fields.page() == 'image')

    print('\nE4: Gauges drew the traces and filled the table')
    res.show_view('Gauges')
    pump(60)
    check('the canvas has a figure', res.gauges.canvas.figure is not None)
    rows = res.gauges.rows()
    check('one row per gauge', len(rows) == 2, str(len(rows)))
    check('with a real peak overpressure in it',
          rows and rows[0][1] not in ('', '0.0'), str(rows[0][:3]))

    print('\nE5: the animation replays what the run recorded')
    res.show_view('Animation')
    pump(60)
    an = res.anim
    check('Play is enabled', an.play_btn.isEnabled())
    check('the slider spans the recorded frames',
          an.slider.maximum() > 0, str(an.slider.maximum()))
    check('and it defaults to ONE range for the whole video',
          an.scale() == 'run' and an.scale_used() == 'run',
          f'{an.scale()} / {an.scale_used()}')
    first = an.image.levels
    an.slider.setValue(an.slider.maximum())
    pump(30)
    check('so the last frame keeps the same colour range',
          an.image.levels == first, f'{first} -> {an.image.levels}')
    check('the range was clipped, as a recording from t = 0 needs',
          an.clipped())
    an.scale_sel.setCurrentText(ANIM_SCALE_LABELS['frame'])
    pump(30)
    check('and per-frame really does change it',
          an.image.levels != first, str(an.image.levels))
    # the property that matters: the t = 0 charge must not blacken the
    # rest. Unclipped this run spans 2.76e6 kPa against a last frame of
    # 7.7e3, i.e. 0.28 % of the colour bar.
    last_peak = an.image.levels[1]
    an.scale_sel.setCurrentText(ANIM_SCALE_LABELS['run'])
    pump(30)
    share = 100.0 * last_peak / an.image.levels[1]
    check('so the last frame still uses a usable part of the bar',
          share > 5.0, f'{share:.2f} % of {an.image.levels[1]:.3g} kPa')
    an.scale_sel.setCurrentText(ANIM_SCALE_LABELS['run'])
    pump(30)
    an.start_play()
    pump(200)
    check('playing advances the frame', an.frame() > 0, str(an.frame()))
    an.stop_play()
    check('and stopping stops the timer', not an.timer.isActive())

    print('\nE6: the exports write real files')
    real_dir, real_save = dialogs.pick_dir, dialogs.save_file
    dialogs.pick_dir = lambda *a, **k: out
    try:
        res.export('pngs', threaded=False)
        pump(60)
    finally:
        dialogs.pick_dir = real_dir
    pngs = sorted(f for f in os.listdir(out) if f.endswith('.png'))
    check('PNGs wrote the FULL grid, several files',
          len(pngs) > 2, str(pngs))
    check('and each one is a real image',
          all(os.path.getsize(os.path.join(out, f)) > 5000
              for f in pngs), str([(f, os.path.getsize(
                  os.path.join(out, f))) for f in pngs][:2]))
    gif = os.path.join(out, 'run.gif')
    dialogs.save_file = lambda *a, **k: gif
    try:
        res.export('gif', threaded=False)
        pump(60)
    finally:
        dialogs.save_file = real_save
    check('the Animation export wrote a video',
          os.path.exists(gif) and os.path.getsize(gif) > 2000,
          str(os.path.getsize(gif) if os.path.exists(gif) else 0))
    tsv = os.path.join(out, 'gauges_out.txt')
    dialogs.save_file = lambda *a, **k: tsv
    try:
        res.export('tsv', threaded=False)
        pump(30)
    finally:
        dialogs.save_file = real_save
    check('and the gauge TSV has a line per sample',
          os.path.exists(tsv)
          and len(open(tsv, encoding='utf-8').read().splitlines()) > 5)
    check('every export line reached the log',
          any('Saved' in s for s in win.run_panel.log_text().splitlines()),
          '')

    print('\nE7: still no VTK and no pyplot in this process')
    check('the viewer child was never spawned for a 2D session',
          not win.viewer_link.alive)
    check('no VTK in the GUI process',
          not [m for m in sys.modules
               if m.startswith(('vtk', 'pyvista'))])
    check('and no matplotlib.pyplot either',
          'matplotlib.pyplot' not in sys.modules)

    print('\nE8: Remove leaves nothing behind')
    res.remove_current()
    pump(60)
    check('the picker is empty', not res.entries())
    check('and every export is off again',
          all(not res.export_enabled(k) for k in res._export_btns))
    win.close()
    pump(200)

    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'E2E UI NATIVE: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
