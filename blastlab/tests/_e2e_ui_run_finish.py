"""GUI-6b end to end: a real short native run on the 02 Run screen, from
the live-gauge column to the finish banner, the Windows notification and
the next run (batch docs/batches/2026-09-29-gui-run.md, T9; plan §10
GUI-6: "the finish banner and the notification appear on a real short
native run").

What it asserts, on the real window and the real worker:

- during the run the live-gauge column is sorted by Z at every look, at
  least one row reads `waiting`, and that same row later shows a peak;
- at the end: the banner text (the result's stop_reason verbatim, the
  model folder), one `notify_desktop` call - through a recorder that
  also forwards to the real function, so the toast really appears - the
  title `✓ Done · …`, and `Run again`;
- the notification's tray icon is removed on its timer;
- a second run keeps the first run's full log in Earlier runs, and
  clears the banner and `✓ Done`.

Real platform by default (CLAUDE.md 8.7: screenshots and the toast need
it); `--offscreen` for CI-style runs (no system tray there, so the real
notify_desktop returns False and only the recorder sees the call).
`--shots DIR` saves the screenshots there (default: a temp folder):
running at about 60 % with far gauges still `waiting`, finished with the
banner, and a whole-screen grab while the toast is up.

Throwaway settings (ui.testing.ensure_qapp -> private_settings, a
private runs folder). No WSL.

The case is the boards' sample at a 50 mm cell, but the native solvers
refine any cell to MIN_EXP_CELLS across the charge radius
(core/refine.effective_dx), so 1 kg runs at 10.5 mm: 380 x 380 cells.
An axisymmetric run would also start the viewer child for its revolved
3D view; on the 8 GB PC this was written on, that child and the solve
together ran out of memory. The revolved view has nothing to do with
what is checked here (the embedded viewer is measured separately), so it
is off unless `--with-3d` is given; then the child is closed with the
window.

Run:  cd blastlab/tests && python _e2e_ui_run_finish.py [--offscreen]
      [--shots DIR] [--with-3d]
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
OFFSCREEN = '--offscreen' in sys.argv
if not OFFSCREEN:
    os.environ.pop('QT_QPA_PLATFORM', None)     # a real platform, on purpose
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS', os.path.join(
    tempfile.mkdtemp(prefix='blastlab_run_finish_'), 'settings.json'))

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def sample_case():
    """The boards' sample case at a 50 mm cell, so the run is short: 2D
    axisymmetric native, 1 kg TNT at z 2, 4 x 4 m, Wall 1 r 3.0-3.2 z
    0-1.5, six gauges - G4 behind the wall, G5 and G6 far out."""
    from blastlab.core.case import Case2D
    from blastlab.ui import setup_spec
    return Case2D(solver='native', geometry='axisymmetric', Lx=4.0, Ly=4.0,
                  cell_size_m=0.05, charge=1.0, center=(0.0, 2.0),
                  bcs=dict(setup_spec.BC_DEFAULTS[2]),
                  obstacles=[(3.0, 3.2, 0.0, 1.5)],
                  gauges=[(2.95, 0.5), (2.95, 1.5), (1.5, 0.5), (3.3, 0.5),
                          (1.0, 3.0), (3.8, 3.8)],
                  gauge_file=None, n_snapshots=2, record_frames=0,
                  anim_file=None)


def main():
    from blastlab.ui.testing import ensure_qapp, pump, use_model
    app = ensure_qapp(offscreen=OFFSCREEN)
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QSystemTrayIcon
    from blastlab.ui import dialogs, run_controller
    from blastlab.ui.app import MainWindow

    with_3d = '--with-3d' in sys.argv
    if not with_3d:
        # no revolved 3D view, so no viewer child (see the docstring)
        run_controller.pyvista_available = lambda: False
    shots =_arg('--shots') or tempfile.mkdtemp(prefix='blastlab_6b_shots_')
    os.makedirs(shots, exist_ok=True)
    mode = 'offscreen' if OFFSCREEN else 'real'
    print(f'platform: {app.platformName()} ({mode}); shots -> {shots}')

    # every modal becomes a recorder; notify_desktop forwards as well
    modal = []
    for name in ('show_error', 'warn', 'show_info'):
        setattr(dialogs, name,
                lambda title, text, parent=None, _n=name:
                modal.append((_n, title, str(text))))
    dialogs.ask_yes_no = lambda *a, **k: modal.append(('ask', a[:1])) or True
    real_notify = dialogs.notify_desktop
    notes = []

    def notify(title, text, on_click=None, parent=None):
        shown = real_notify(title, text, on_click=on_click, parent=parent)
        notes.append(dict(title=title, text=text, shown=shown,
                          at=time.monotonic()))
        return shown

    dialogs.notify_desktop = notify
    dialogs.TRAY_LIFE_MS = 15_000       # the 60 s removal, shortened

    def grab(name):
        path = os.path.join(shots, name)
        win.grab().save(path)
        return path

    win = MainWindow()
    win.set_solver('native')
    use_model(win, 'run_finish')
    win.resize(1600, 1000)
    win.show()
    pump(300)
    case = sample_case()
    win.setup.set_case(case)
    win._schedule_validate()
    pump(500)
    rp = win.run_panel
    col = rp.gauge_col

    print('\nF1: during the run - sorted by Z, waiting, then a peak')
    t0 = time.monotonic()
    win._run_single()
    check('the run started on the Run screen',
          win.ctrl.running and win.current_tab() == 'run')
    unsorted, waited, peaked, shot60 = [], set(), set(), None
    looks = 0
    while win.ctrl.running and time.monotonic() - t0 < 300:
        pump(20)
        table = col.table()
        if not table or not col.has_data():
            continue
        looks += 1
        zs = [r['z'] for r in table]
        if zs != sorted(zs):
            unsorted.append(zs)
        for r in table:
            if r['waiting']:
                waited.add(r['number'])
            elif r['number'] in waited:
                peaked.add(r['number'])
        frac = rp.progress.value() / 1000.0
        if shot60 is None and frac >= 0.6:
            shot60 = grab('gui6b-e2e-running-60pct-1600x1000-dark.png')
            far = [r['number'] for r in table if r['waiting']]
            print(f'    at {100 * frac:.0f} %: waiting {far}, '
                  f'{rp.time_text()!r}')
    wall = time.monotonic() - t0
    pump(500)
    print(f'    run took {wall:.1f} s; {looks} looks at the column')
    check('the run finished on its own',
          not win.ctrl.running and '[run finished]' in rp.log_text())
    check('the column was sorted by Z at every look',
          looks > 0 and not unsorted, f'{looks} looks, {len(unsorted)} not')
    check('at least one row read `waiting` during the run', bool(waited),
          str(sorted(waited)))
    check('and that same row later showed a peak', bool(peaked),
          f'waited {sorted(waited)}, then peaked {sorted(peaked)}')
    check('a screenshot at about 60 %', shot60 is not None, str(shot60))

    print('\nF2: the end - banner, notification, Done, Run again')
    ent = win.results.entries()[-1] if win.results.entries() else None
    res = ent.result if ent is not None else None
    folder = win.ctrl._model.folder
    want = (f'Result ready: run_finish · {getattr(res, "stop_reason", "")}. '
            f'Files in {folder.rstrip(os.sep)}{os.sep}')
    check('the banner reads the stop reason verbatim and the folder',
          rp.banner.isVisible() and rp.banner_text() == want,
          repr(rp.banner_text()))
    check('one notify_desktop call, forwarded to the real one',
          len(notes) == 1 and notes[0]['title'] == 'BlastLab'
          and notes[0]['text'].startswith('run_finish finished in '),
          repr(notes))
    tray = QSystemTrayIcon.isSystemTrayAvailable()
    check('the real notification went out (tray available) or, '
          'offscreen, returned False',
          (notes and notes[0]['shown'] is True and dialogs._tray is not None)
          if tray else (notes and notes[0]['shown'] is False),
          f'tray {tray}, shown {notes[0]["shown"] if notes else None}')
    check('the title starts with ✓ Done · ',
          win.windowTitle().startswith('✓ Done · '), win.windowTitle())
    check('the idle button reads Run again',
          rp.run_btn.text() == 'Run again' and rp.run_btn.isVisible())
    print(f'    notification: {notes[0]["text"] if notes else None!r}')
    print(f'    time line: {rp.time_text()!r}')
    grab('gui6b-e2e-finished-banner-1600x1000-dark.png')
    if tray and not OFFSCREEN:
        pump(1500)                  # let Windows draw the toast
        screen = QGuiApplication.primaryScreen().grabWindow(0)
        path = os.path.join(shots, 'gui6b-e2e-toast-screen.png')
        ok = screen.save(path)
        if not ok:
            try:
                from PIL import ImageGrab
                ImageGrab.grab().save(path)
                ok = True
            except Exception as exc:
                print(f'    (screen grab failed: {exc})')
        check('a whole-screen grab while the toast is up', ok, path)
        pump(max(0, dialogs.TRAY_LIFE_MS + 1500
                 - int(1000 * (time.monotonic() - notes[0]['at']))))
        check('the tray icon is gone after its timer', dialogs._tray is None)

    print('\nF3: the next run - the first run\'s log is an earlier run')
    log1 = rp.log_text()
    rp.run_name.setText('run_finish_2')
    win._run_single()
    for _ in range(100):
        pump(20)
        if win.ctrl.running:
            break
    hist = rp.log_history()
    check('Earlier runs holds the first run with its full text',
          bool(hist) and hist[0]['model'] == 'run_finish'
          and hist[0]['text'] == log1 and len(log1) > 0,
          f'{hist[0]["model"] if hist else None} '
          f'{len(hist[0]["text"]) if hist else 0} vs {len(log1)} chars')
    check('the next start hides the banner and clears ✓ Done',
          rp.banner.isHidden() and not win.windowTitle().startswith('✓'),
          win.windowTitle())
    win._stop()
    for _ in range(1500):
        pump(20)
        if not win.ctrl.running:
            break
    check('the second run stopped', not win.ctrl.running)
    if not with_3d:
        check('no viewer child was started', not win.viewer_link.alive)
    check('no failure dialog on the way', not [m for m in modal
                                               if m[0] != 'ask'],
          str(modal[:2]))
    win.close()
    pump(200)
    check('close leaves no tray icon', dialogs._tray is None)

    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'E2E UI RUN FINISH: PASS ({len(RAN)} checks, {mode})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
