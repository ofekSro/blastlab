"""GUI-3 gate: the window frame (docs/gui-redesign-plan.md §4, board
BC_Combined lines 20-54 / 392-396).

 F1  no sidebar: no 216 px `#sidebar` frame; a 64 px top bar; the
     content stack starts at x ~ 0 under it; a 28 px status bar;
     nothing in the bar sticks out of the window at 1100x720 or 900x600
 F2  the pills (and the Chain link) navigate; `_show` re-marks them
 F3  the solver chip is the old sidebar switch: menu actions drive
     `solver_mode`, `set_solver` syncs the chip silently, `_poll_wsl`
     writes the chip dot + status-bar text, a 0-D case hides (never
     greys) the chip
 F4  Open / Save (in place, no dialog) / Save as / Recent; the 0-D case
     still routes through `hd13_case.save_case`; load -> save is
     byte-identical
 F5  the QShortcut set is exactly {Ctrl+O, Ctrl+S, Ctrl+Shift+S, F5,
     Shift+Esc}; plain Esc is NOT bound and does not stop
 F6  the title: `untitled · BlastLab`, the open stem, `78 % · ` during
     a run, `Chain 2/3 · ` during a chain, the dirty ●
 F7  the status bar: WSL text, the shortcuts + version line, notify()
     semantics unchanged
 F8  the dimension control syncs both ways; the dark-mode action works
 F9  at 1100 px in blastFoam mode the chip keeps its text and the case
     name elides, the whole name in its tooltip (GUI-10, F29)
 F10 the longest chip at 1100 px squeezes no control: the unsaved marker
     drops its word only then (verify10b, F37 / D198)
 F11 Save as reports a write failure (no crash dialog) and starts in the
     case folder / the newest Recent's / the Runs folder (GUI-11, D204)
 F12 F5 runs the chain on the Chain screen, 01 Setup's case elsewhere
     (GUI-11, D205)
 F13 the in-progress refusal is titled after the action; a message box
     keeps a path on one line; long tooltips wrap (GUI-11, D207 / D208)

Plain script, offscreen, no pytest: `python test_ui_frame.py`.
"""
import json
import os
import sys
import tempfile
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_fr_'),
                                   'settings.json'))

from blastlab.ui.testing import ensure_qapp, pump             # noqa: E402

FAIL = []
RAN = []

# titles carry '●', which a cp1252 console cannot encode - never let a
# print kill the suite over a glyph
try:
    sys.stdout.reconfigure(errors='replace')
except Exception:
    pass


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def main():
    ensure_qapp()
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QShortcut
    from PySide6.QtWidgets import QFrame
    from blastlab import __version__
    from blastlab.core import mode as mode_mod
    from blastlab.core import settings as app_settings
    from blastlab.core.case import Case2D, save_case
    from blastlab.models import hd13_case
    from blastlab.solvers.foam import env as foam_env
    from blastlab.ui import dialogs, theme
    from blastlab.ui.app import MainWindow

    win = MainWindow()
    win.resize(1280, 840)
    win.show()
    pump(200)

    print('\nF1: no sidebar - a 64 px top bar and a 28 px status bar')
    check('the default title is untitled · BlastLab',
          win.windowTitle() == 'untitled · BlastLab', win.windowTitle())
    check('no #sidebar frame anywhere',
          win.findChildren(QFrame, 'sidebar') == [])
    check('and no _build_sidebar method',
          not hasattr(win, '_build_sidebar'))
    check('the top bar is 64 px and spans the window',
          win.topbar.height() == 64
          and abs(win.topbar.width() - win.width()) <= 2,
          f'{win.topbar.width()}x{win.topbar.height()}')
    pos = win._stack.mapTo(win, QPoint(0, 0))
    check('the content stack starts at x ~ 0 under the bar',
          pos.x() <= 24 and pos.y() >= 64, f'({pos.x()}, {pos.y()})')
    sbar = win.findChildren(QFrame, 'statusbar')
    check('a 28 px #statusbar exists',
          len(sbar) == 1 and sbar[0].height() == 28,
          str([s.height() for s in sbar]))
    for size in ((1100, 720), (900, 600)):
        win.resize(*size)
        pump(120)
        over = []
        from PySide6.QtWidgets import QWidget
        for bar in (win.topbar, sbar[0]):
            for c in bar.findChildren(QWidget):
                if not c.isVisible() or c.width() <= 0:
                    continue
                tl = c.mapTo(win, c.rect().topLeft())
                if tl.x() + c.width() - win.width() > 1:
                    over.append((type(c).__name__,
                                 tl.x() + c.width() - win.width()))
        check(f'nothing in the bars sticks out at {size[0]}x{size[1]}',
              not over, str(over[:3]))
    win.resize(1280, 840)
    pump(100)

    print('\nF2: the pills navigate, and _show re-marks them')
    for key in ('run', 'results', 'chain', 'setup'):
        win._nav_btns[key].click()
        pump(60)
        vis = [k for k, p in win._panels.items() if p.isVisible()]
        check(f'pill {key} -> current_tab() == {key!r}, one panel visible',
              win.current_tab() == key and vis == [key], str(vis))
    win._show('results')
    pump(40)
    marks = {k: win._nav_btns[k].property('active')
             for k in win._nav_btns}
    check('_show re-marks the pills',
          marks['results'] == 'true'
          and all(v == 'false' for k, v in marks.items()
                  if k != 'results'), str(marks))
    win._show('setup')
    pump(40)

    print('\nF3: the chip is the old solver switch')
    win.set_solver('blastfoam')
    pump(40)
    check('blastfoam: the chip text follows mode_mod.label',
          win.topbar.chip.text().startswith(mode_mod.label('blastfoam')),
          win.topbar.chip.text())
    check('and the menu has native / blastFoam / Re-detect',
          sorted(a.text() for a in win._chip_actions.values())
          == sorted(mode_mod.label(m) for m in mode_mod.MODES)
          and any(a.text() == 'Re-detect'
                  for a in win._chip_menu.actions()))
    win._chip_actions['native'].trigger()
    pump(40)
    check('the native action switches the app mode',
          win.solver == 'native'
          and win.topbar.chip.text() == mode_mod.label('native'),
          f'{win.solver} / {win.topbar.chip.text()}')
    win._chip_actions['blastfoam'].trigger()
    pump(40)
    check('and blastFoam back', win.solver == 'blastfoam',
          win.solver)
    win.set_solver('native')
    pump(40)
    check('set_solver updates the chip silently (no loop)',
          win.topbar.chip.text() == 'native'
          and win._chip_actions['native'].isChecked()
          and not win._chip_actions['blastfoam'].isChecked())
    win.set_solver('blastfoam')
    pump(40)
    real_status = foam_env.status
    try:
        foam_env.status = lambda: ('ok', '')
        win._poll_wsl()
        check("state 'ok': the status bar says ready and the chip "
              'mirrors it',
              win._wsl_hint.text().startswith('WSL: blastFoam ready')
              and win.topbar.chip.text() == 'blastFoam · WSL ready'
              and win.topbar._chip_dot_key in ('ok', 'warn'),
              f'{win._wsl_hint.text()!r} / {win.topbar.chip.text()!r} '
              f'/ {win.topbar._chip_dot_key}')
        foam_env.status = lambda: ('fail', 'nope')
        win._poll_wsl()
        check("state 'fail': danger dot, unavailable text, the detail "
              'in the tooltip',
              win.topbar.chip.text() == 'blastFoam · WSL unavailable'
              and win.topbar._chip_dot_key == 'danger'
              and win._wsl_hint.toolTip() == 'nope',
              f'{win.topbar.chip.text()!r} / {win.topbar._chip_dot_key}')
    finally:
        foam_env.status = real_status
        win._wsl_timer.stop()
    win.setup.set_dim(0)
    pump(60)
    check('a 0-D case hides the chip - hidden, not greyed',
          not win.topbar.chip.isVisible() and win.topbar.chip.isEnabled())
    win.setup.set_dim(2)
    pump(60)
    check('and set_dim(2) brings it back', win.topbar.chip.isVisible())

    print('\nF4: Open / Save in place / Save as / Recent')
    tmp = tempfile.mkdtemp(prefix='blastlab_frame_')
    p1 = os.path.join(tmp, 'wall_A.json')
    save_case(Case2D(Lx=3.0, Ly=2.0, cell_size_m=0.05, charge=5.0,
                     center=(0.0, 0.5), gauges=[(1.0, 1.0)]), p1)
    shown = []
    real_err = MainWindow.show_error
    win.show_error = lambda t, m: shown.append((t, m))
    win._open_case(p1)
    pump(400)
    check('Open loads it and the case button shows the stem',
          win.topbar.case_btn.text() == 'wall_A' and not shown,
          f'{win.topbar.case_btn.text()!r} {shown}')
    check('the title shows the stem',
          win.windowTitle() == 'wall_A · BlastLab', win.windowTitle())
    check('open does not mark dirty',
          not win._dirty and not win.topbar.dirty_lbl.isVisible())
    rec = app_settings.load().get('recent_cases') or []
    check('the file landed in recent_cases, most recent first',
          rec and os.path.normcase(rec[0]) == os.path.normcase(p1),
          str(rec))
    win.setup.forms[2].v['Lx'].set('5.5')
    pump(40)
    check('an edit sets the dirty state and the ● unsaved marker',
          win._dirty and win.topbar.dirty_lbl.isVisible()
          and win.windowTitle() == '● wall_A · BlastLab'
          and 'unsaved changes' in win._dirty_lbl.text(),
          f'{win.windowTitle()!r} / {win._dirty_lbl.text()!r}')
    dialog_calls = []
    real_save_file = dialogs.save_file
    dialogs.save_file = (lambda *a, **k:
                         dialog_calls.append(a) or '')
    try:
        before = open(p1, encoding='utf-8').read()
        win._save_case_inplace()
        pump(40)
        after = open(p1, encoding='utf-8').read()
        check('Ctrl+S writes THAT file in place, no dialog',
              not dialog_calls and after != before
              and json.loads(after)['Lx'] == 5.5,
              f'dialog={len(dialog_calls)} Lx='
              f'{json.loads(after).get("Lx")}')
        check('and clears the dirty state',
              not win._dirty and not win.topbar.dirty_lbl.isVisible()
              and win.windowTitle() == 'wall_A · BlastLab',
              win.windowTitle())
        # Save as goes through the dialog and updates path + recents
        p2 = os.path.join(tmp, 'wall_B.json')
        dialogs.save_file = lambda *a, **k: p2
        win._save_case()
        pump(40)
        rec = app_settings.load().get('recent_cases') or []
        check('Save as writes the dialog path and adopts it',
              os.path.exists(p2) and win._case_path == p2
              and win.topbar.case_btn.text() == 'wall_B'
              and os.path.normcase(rec[0]) == os.path.normcase(p2),
              f'{win._case_path!r} rec0={rec[:1]}')
        win._open_case(p1)
        pump(400)
        rec = app_settings.load().get('recent_cases') or []
        norm = [os.path.normcase(p) for p in rec]
        check('Recent: most recent first, no duplicates, len <= 8',
              norm[0] == os.path.normcase(p1)
              and norm.count(os.path.normcase(p1)) == 1
              and len(rec) <= 8, str(rec))
    finally:
        dialogs.save_file = real_save_file
    # load -> save byte-parity: open a fresh file and save it in place.
    # The two AMR coefficients are written at the form's defaults while
    # AMR is off (test_ui_setup_form S3, 'exactly as in Tk'), so the
    # parity case carries those values explicitly.
    p3 = os.path.join(tmp, 'parity.json')
    save_case(Case2D(amr_refine=0.4, amr_unrefine=0.2), p3)
    raw = open(p3, 'rb').read()
    win._open_case(p3)
    pump(400)
    win._save_case_inplace()
    pump(40)
    check('load -> save in place is byte-identical',
          open(p3, 'rb').read() == raw)
    # the 0-D case still routes through hd13_case.save_case
    routed = []
    real_hd13_save = hd13_case.save_case
    hd13_case.save_case = lambda case, path: routed.append(path)
    try:
        win.setup.set_dim(0)
        pump(60)
        win._case_path = os.path.join(tmp, 'hd13.json')
        win._save_case_inplace()
        pump(40)
        check('a 0-D case routes through hd13_case.save_case',
              routed == [win._case_path] and not shown,
              f'{routed} {shown}')
    finally:
        hd13_case.save_case = real_hd13_save
        win.setup.set_dim(2)
        pump(60)
    win.show_error = real_err
    win._case_path = p3
    win._set_dirty(False)
    win.topbar.set_case_name(win._case_stem())
    win._update_title()

    print('\nF5: the keyboard is exactly the five keys, and Esc is free')
    keys = sorted(sc.key().toString() for sc in win.findChildren(QShortcut))
    check('the QShortcut set is {Ctrl+O, Ctrl+S, Ctrl+Shift+S, F5, '
          'Shift+Esc}',
          keys == sorted(['Ctrl+O', 'Ctrl+S', 'Ctrl+Shift+S', 'F5',
                          'Shift+Esc']), str(keys))
    check("plain 'Esc' is NOT bound", 'Esc' not in keys, str(keys))
    stops = []
    real_stop = win.ctrl.stop
    win.ctrl.stop = lambda: stops.append(1)
    try:
        for sc in win.findChildren(QShortcut):
            if sc.key().toString() == 'Shift+Esc':
                sc.activated.emit()
        pump(20)
        check('Shift+Esc reaches ctrl.stop', stops == [1], str(stops))
    finally:
        win.ctrl.stop = real_stop

    print('\nF6: the title carries the run')
    stem = win._case_stem()
    win.ctrl._stage_dims = [2]
    win.on_running(True)
    win.on_progress(SimpleNamespace(frac=0.78, step=5, t=1e-3, dt=1e-6,
                                    p_max=2e5))
    pump(20)
    check('a fed on_progress(frac=0.78) shows 78 % ·',
          win.windowTitle() == f'78 % · {stem} · BlastLab',
          win.windowTitle())
    win.on_running(False)
    pump(20)
    check('and the title is restored when the run ends',
          win.windowTitle() == f'{stem} · BlastLab', win.windowTitle())
    win.ctrl._stage_dims = [1, 2, 3]
    win.on_running(True)
    info1d = dict(dim=1, radius_m=3.0, gauges=[])
    win.on_run_started(info1d)
    win.on_run_started(info1d)
    pump(20)
    check("a 3-stage chain's second stage shows Chain 2/3 ·",
          win.windowTitle().startswith('Chain 2/3 · '),
          win.windowTitle())
    win.on_running(False)
    win.ctrl._stage_dims = []
    pump(20)
    win.setup.forms[2].v['Lx'].set('6.5')
    pump(40)
    check('the dirty mark appears in the title too',
          win.windowTitle().startswith('● '), win.windowTitle())
    win._set_dirty(False)

    print('\nF7: the status bar')
    check('the shortcuts line ends with the version',
          win._keys_lbl.text()
          == f'Ctrl+S save · F5 run · Shift+Esc stop · v{__version__}',
          win._keys_lbl.text())
    win.notify('boom', 'warn')
    check("notify('boom', 'warn') lands in _status with the warn "
          'colour and the 12 s timer',
          win._status.text() == 'boom'
          and win._status.styleSheet() == f'color: {theme.cur("warn")};'
          and win._status_timer.isActive(),
          f'{win._status.text()!r} {win._status.styleSheet()!r}')
    check('the message outranks the shortcuts hint (decision D13): '
          'the keys label yields its width',
          not win._keys_lbl.isVisible())
    win._status_timer.stop()
    win._clear_status()
    pump(20)
    check('and the timer clear restores it',
          win._keys_lbl.isVisible() and win._status.text() == ''
          and win._status.toolTip() == '')

    print('\nF8: dimension control and dark mode')
    win.topbar.dim_seg.changed.emit('3D')
    pump(60)
    check('clicking 3D drives setup.set_dim(3)', win.setup.dim == 3)
    win.setup.set_dim(1)
    pump(40)
    check('setup.set_dim(1) syncs the bar back (silent)',
          win.topbar.dim_seg.get() == '1D', win.topbar.dim_seg.get())
    win.setup.set_dim(0)
    pump(40)
    check("the 0-D label is '0D · HD 1.3'",
          win.topbar.dim_seg.get() == '0D · HD 1.3',
          win.topbar.dim_seg.get())
    win.setup.set_dim(2)
    pump(40)
    was = theme.mode()
    check('the Dark-mode action mirrors the mode',
          win._dark_action.isChecked() == (was == 'dark'))
    win._dark_action.toggle()
    pump(120)
    check('toggling it switches the theme', theme.mode() != was,
          theme.mode())
    win._dark_action.toggle()
    pump(120)
    check('and back', theme.mode() == was, theme.mode())

    print('\nF9: at 1100 px the chip keeps its text and the case name '
          'elides (F29)')
    from PySide6.QtWidgets import QWidget
    tb = win.topbar
    long_name = 'wall_A_blastfoam'      # fits the button's 200 px max
    tb.set_chip('blastFoam · WSL ready', 'ok')
    tb.set_dirty(True)
    tb.set_done('setup', True)
    tb.set_done('run', True)
    tb.set_case_name(long_name)
    win.resize(1100, 720)
    pump(150)
    over = [type(c).__name__ for c in tb.findChildren(QWidget)
            if c.isVisible() and c.width() > 0
            and c.mapTo(win, c.rect().topLeft()).x() + c.width()
            - win.width() > 1]
    check('nothing in the bar sticks out', not over, str(over))
    check('the chip is never narrower than its text',
          tb.chip.width() >= tb.chip.sizeHint().width()
          and tb.chip.text() == 'blastFoam · WSL ready',
          f'{tb.chip.width()} / {tb.chip.sizeHint().width()}')
    cb = tb.case_btn
    check('the case name is elided, the whole name in its tooltip',
          cb.text().endswith('…') and cb.toolTip() == long_name
          and tb.case_name() == long_name
          and cb.fontMetrics().horizontalAdvance(cb.text())
          <= cb.width(), f'{cb.text()!r} {cb.toolTip()!r} {cb.width()}')
    win.resize(1600, 1000)
    pump(150)
    check('and whole, with no tooltip, when there is room',
          cb.text() == long_name and cb.toolTip() == '',
          f'{cb.text()!r} {cb.toolTip()!r}')
    check('a screen reader gets the whole name (verify10b)',
          cb.accessibleName() == long_name, repr(cb.accessibleName()))

    print('\nF10: the longest chip at 1100 px squeezes no control; the '
          'marker drops its word only then (verify10b, F37 / D198)')
    from blastlab.ui.topbar import DIRTY_LONG, DIRTY_SHORT, TopBar

    def squeezed(bar):
        return [b.text() for b in bar.dim_seg._btns.values()
                if b.minimumWidth() != b.maximumWidth()
                and b.width() < b.sizeHint().width()]

    tb.set_chip('blastFoam · WSL unavailable', 'danger')
    win.resize(1100, 720)
    pump(150)
    check('in the window: the dimension control keeps every label whole',
          not squeezed(tb), str(squeezed(tb)))
    check('and the chip keeps its text',
          tb.chip.width() >= tb.chip.sizeHint().width(),
          f'{tb.chip.width()} / {tb.chip.sizeHint().width()}')
    win.resize(1600, 1000)
    pump(150)
    check('at 1600 px the marker is ● unsaved',
          tb.dirty_lbl.text() == DIRTY_LONG, repr(tb.dirty_lbl.text()))
    # the offscreen glyphs are narrower than the real platform's, where
    # the window's bar was 22 px short; so a bar in a plain host is made
    # short here by half of what dropping the word saves
    host = QWidget()
    bar = TopBar(host)
    bar.set_chip('blastFoam · WSL unavailable', 'danger')
    bar.set_done('setup', True)
    bar.set_done('run', True)
    bar.set_case_name(long_name)
    bar.set_dirty(True)
    host.resize(1400, 64)
    bar.setGeometry(0, 0, 1400, 64)
    host.show()
    pump(150)
    lay = bar.layout()
    full = lay.minimumSize().width()
    fm = bar.dirty_lbl.fontMetrics()
    save = (fm.horizontalAdvance(DIRTY_LONG)
            - fm.horizontalAdvance(DIRTY_SHORT))
    bar.setGeometry(0, 0, full - save // 2, 64)
    pump(150)
    given = [f'{(lay.itemAt(i).widget() or lay.itemAt(i)).__class__.__name__}'
             f' {lay.itemAt(i).geometry().width()}'
             f'<{lay.itemAt(i).sizeHint().width()}'
             for i in range(lay.count())
             if lay.itemAt(i).spacerItem() is None
             and lay.itemAt(i).widget() is not bar.case_btn
             and lay.itemAt(i).geometry().width()
             < lay.itemAt(i).sizeHint().width()]
    check(f'a bar {save // 2} px short: only the case name gives way',
          not given and not squeezed(bar), f'{given} {squeezed(bar)}')
    check('its marker reads ●, the word in its tooltip',
          bar.dirty_lbl.text() == DIRTY_SHORT
          and bar.dirty_lbl.toolTip() == 'Unsaved changes',
          f'{bar.dirty_lbl.text()!r} {bar.dirty_lbl.toolTip()!r}')
    bar.setGeometry(0, 0, 1400, 64)
    pump(150)
    check('with room again it is ● unsaved, no tooltip',
          bar.dirty_lbl.text() == DIRTY_LONG
          and bar.dirty_lbl.toolTip() == '', repr(bar.dirty_lbl.text()))
    host.close()

    print('\nF11: Save as reports a write failure and starts in a useful '
          'folder (GUI-11 T3, UXR-5 / D204)')
    from blastlab.ui import crashlog
    crashlog.install()      # an escaping OSError would land here
    win.resize(1280, 840)
    pump(60)
    locked_dir = tempfile.mkdtemp(prefix='blastlab_ro_')
    locked = os.path.join(locked_dir, 'locked.json')
    with open(locked, 'w', encoding='utf-8') as f:
        f.write('{}')
    # Windows ignores a folder's read-only flag for new files, so the
    # target itself is read-only: the write raises PermissionError
    os.chmod(locked, 0o444)
    win._case_path = p3
    win.topbar.set_case_name(win._case_stem())
    win.setup.forms[2].v['Lx'].set('7.5')
    pump(40)
    rec_before = list(app_settings.load().get('recent_cases') or [])
    crash_before = crashlog.last_crash
    shown = []
    win.show_error = lambda t, m: shown.append((t, m))
    asked = []
    real_save_file = dialogs.save_file

    def fake_save_file(*a, **k):
        asked.append(k.get('start', a[3] if len(a) > 3 else None))
        return locked
    dialogs.save_file = fake_save_file
    try:
        for sc in win.findChildren(QShortcut):
            if sc.key().toString() == 'Ctrl+Shift+S':
                sc.activated.emit()
        pump(40)
    finally:
        dialogs.save_file = real_save_file
        os.chmod(locked, 0o666)
    check('a read-only target: one show_error titled Save case',
          len(shown) == 1 and shown[0][0] == 'Save case'
          and shown[0][1].startswith(f'Could not write {locked}: '),
          str(shown))
    check('no crashlog entry (the OSError did not escape)',
          crashlog.last_crash is crash_before,
          str(crashlog.last_crash and crashlog.last_crash['message']))
    check('the window is still dirty, its path and Recent unchanged',
          win._dirty and win._case_path == p3
          and (app_settings.load().get('recent_cases') or []) == rec_before,
          f'dirty={win._dirty} path={win._case_path!r}')
    check('the dialog starts in the case folder, named <stem>.json',
          asked == [os.path.join(os.path.dirname(os.path.abspath(p3)),
                                 'parity.json')], str(asked))
    win._case_path = None
    win.run_panel.set_run_name('QA_MODEL', replace=True)
    newest = (app_settings.load().get('recent_cases') or [None])[0]
    check('untitled: the newest Recent entry\'s folder, <Model>.json',
          newest and win._save_as_start() == os.path.join(
              os.path.dirname(os.path.abspath(newest)), 'QA_MODEL.json'),
          f'{win._save_as_start()!r} newest={newest!r}')
    app_settings.update(recent_cases=[])
    runs = win.run_panel.current_runs_dir()
    check('untitled, no Recent: the Runs folder',
          os.path.isdir(runs) and win._save_as_start()
          == os.path.join(runs, 'QA_MODEL.json'),
          f'{win._save_as_start()!r} runs={runs!r}')
    app_settings.update(recent_cases=rec_before)
    win.show_error = real_err
    win._case_path = p3
    win._set_dirty(False)
    win.topbar.set_case_name(win._case_stem())

    print('\nF12: F5 runs the chain on the Chain screen, the case '
          'elsewhere (GUI-11 T4, UXR-7 / D205)')
    calls = []
    win.chain.run = lambda: calls.append('chain')
    win._run_single = lambda *a, **k: calls.append('single')
    f5 = [sc for sc in win.findChildren(QShortcut)
          if sc.key().toString() == 'F5']
    try:
        win._show('chain')
        pump(40)
        f5[0].activated.emit()
        pump(20)
        check('on Chain: F5 calls chain.run once, _run_single never',
              calls == ['chain'], str(calls))
        del calls[:]
        win._show('setup')
        pump(40)
        f5[0].activated.emit()
        pump(20)
        check('on Setup: F5 calls _run_single once, chain.run never',
              calls == ['single'], str(calls))
    finally:
        del win.chain.run
        del win._run_single
    check('still exactly five shortcuts',
          len(win.findChildren(QShortcut)) == 5,
          str(len(win.findChildren(QShortcut))))
    check('the Run chain tooltip names F5',
          'F5' in win.chain.run_btn.toolTip(), win.chain.run_btn.toolTip())

    print('\nF13: refusal titles, paths kept whole, wrapped tooltips '
          '(GUI-11 T6, P2-18 / P2-24, D207 / D208)')
    infos = []
    real_info = dialogs.show_info
    dialogs.show_info = lambda t, m, p=None: infos.append((t, m))
    win._hd13_busy = True
    try:
        got = win._model_target('Run chain')
    finally:
        win._hd13_busy = False
        dialogs.show_info = real_info
    check("the in-progress refusal is titled after the action: 'Run chain'",
          got is None
          and infos == [('Run chain', 'A run is already in progress.')],
          str(infos))
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel, QMessageBox
    from blastlab.ui.widgets import TIP_WRAP_CHARS, tip_text, wrap_tip
    # short: the offscreen screen is 800 px wide, so the cap is 200 px
    # there (the 70-character path is measured on the real platform)
    runs = 'C:\\runs\\lab'
    text = (f'QA_MODEL already exists in {runs}. Overwrite? The previous '
            f"run's files will be deleted.")
    box = QMessageBox(QMessageBox.Question, 'Model folder', text,
                      QMessageBox.Yes | QMessageBox.No, win)
    dialogs._keep_paths(box)
    lbl = box.findChild(QLabel, 'qt_msgbox_label')
    adv = lbl.fontMetrics().horizontalAdvance(runs + '.')
    check('a message with a path: the label is at least the path wide',
          lbl.minimumWidth() >= adv, f'{lbl.minimumWidth()} >= {adv}')
    check('the path starts its own line, the words unchanged',
          box.text() == text.replace(' C:\\', '\nC:\\')
          and box.text().replace('\n', ' ') == text, repr(box.text()[:40]))
    check('and the text is selectable',
          bool(lbl.textInteractionFlags() & Qt.TextSelectableByMouse))
    huge = 'C:\\' + '\\'.join(['a_very_long_folder_name'] * 40)
    box2 = QMessageBox(QMessageBox.Critical, 'Run', f'Missing {huge}',
                       QMessageBox.Ok, win)
    dialogs._keep_paths(box2)
    lbl2 = box2.findChild(QLabel, 'qt_msgbox_label')
    check('a path past the cap is elided in the middle, the whole text '
          'in the tooltip',
          '…' in box2.text() and lbl2.toolTip() == f'Missing {huge}'
          and lbl2.minimumWidth() < lbl2.fontMetrics().horizontalAdvance(
              huge), f'{box2.text()[:30]!r} min {lbl2.minimumWidth()}')
    # verify11a: an OSError's text quotes its path; the quoted path starts
    # its own line with its quote (the real platform broke it mid-path)
    p = 'C:\\runs\\lab.json'
    err = f'Could not write {p}: [Errno 13] Permission denied: {p!r}'
    box3 = QMessageBox(QMessageBox.Critical, 'Save case', err,
                       QMessageBox.Ok, win)
    dialogs._keep_paths(box3)
    check('a quoted path starts its own line with its quote',
          box3.text() == (f'Could not write\n{p}: [Errno 13] Permission '
                          f'denied:\n{p!r}')
          and box3.text().replace('\n', ' ') == err, repr(box3.text()))
    box.deleteLater()
    box2.deleteLater()
    box3.deleteLater()
    short = 'x' * TIP_WRAP_CHARS
    long_tip = 'word & <tag> ' * 10 + '\nnext line'
    check('wrap_tip: a short tip is unchanged, a long one is rich text '
          'whose plain text is the tip',
          wrap_tip(short) == short and wrap_tip(long_tip).startswith('<')
          and tip_text(wrap_tip(long_tip)) == long_tip,
          repr(tip_text(wrap_tip(long_tip))[:30]))

    win.close()
    pump(80)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI FRAME: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
