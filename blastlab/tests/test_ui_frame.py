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
    win._status.setText('')
    win._status_timer.stop()

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

    win.close()
    pump(80)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI FRAME: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
