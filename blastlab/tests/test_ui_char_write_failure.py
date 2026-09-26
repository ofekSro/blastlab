"""Characterisation: what the Qt GUI shows when a run's output write
fails (UX 2).

docs/UX_REVIEW.md section 3, finding 2. Drives the REAL `ui.app.
MainWindow` offscreen through `RunController.start_stages` - the call
both Run and the Chain tab end in - with one writer of `solvers/jobs`
raising PermissionError for one path (`test_char_write_failure.
failing_writes`), and pins what reaches the user:

  * the Results entries added by the run;
  * the error dialogs (`RunController.show_error`, stubbed to record);
  * the run-log lines that carry the warning or the error headline, and
    whether the run ended ('[run finished]');
  * Stop disabled and Run back in its idle state afterwards.

Scenarios: a 2D run whose animation write fails; a 1D -> 2D chain whose
stage-1 profile (the hand-off) write fails. The chain is launched with
the stage wiring the Chain tab builds (profile_file / profile_file_in),
without the tab itself.

Script only - it builds Qt widgets, so conftest.py keeps it out of
pytest collection (`test_ui_*.py`). BLASTLAB_SETTINGS points at a
private file with `auto_cleanup: false` (`char_common`), so building the
window can never sweep the run corpus (CLAUDE.md 8.2).

Run:  cd blastlab/tests && python test_ui_char_write_failure.py
"""
import os
import shutil
import sys
import tempfile
import time

import char_common  # noqa: F401  (private settings, auto_cleanup off)
from blastlab.ui.testing import ensure_qapp, pump             # noqa: E402

app = ensure_qapp()

import test_char_write_failure as tw                          # noqa: E402

interesting = tw.gui_log_line
EXPECTED = tw.EXPECTED_GUI


def press(win, dim_cases, fail_path, tmp):
    dialogs = []
    win.ctrl.show_error = lambda title, msg: dialogs.append(
        [title, tw._norm(msg, tmp)])
    n0 = len(win.results.entries())
    win.run_panel.log.clear()
    idle_run = win.run_panel.run_btn.isEnabled()
    with tw.failing_writes(fail_path):
        assert win.ctrl.start_stages(dim_cases)
        t0 = time.monotonic()
        while win.ctrl.running and time.monotonic() - t0 < 120:
            pump(50)
        pump(100)
    log = win.run_panel.log.toPlainText().splitlines()
    return dict(
        results=[e.label for e in win.results.entries()[n0:]],
        dialogs=dialogs,
        log=[tw._norm(ln, tmp).strip() for ln in log if interesting(ln)],
        running=win.ctrl.running,
        stop_enabled=win.run_panel.stop_btn.isEnabled(),
        run_back_to_idle=win.run_panel.run_btn.isEnabled() == idle_run)


def collect():
    from blastlab.ui.app import MainWindow
    win = MainWindow()
    win.show()
    pump(150)
    got = {}
    try:
        tmp = tempfile.mkdtemp(prefix='blastlab_uichar_wfail_')
        p = lambda f: os.path.join(tmp, f)        # noqa: E731
        got['2d_anim'] = press(
            win, [(2, tw.case2d(tmp, anim_file=p('a.gif'),
                                profile_file=p('p2.npz')))],
            p('a.gif'), tmp)
        shutil.rmtree(tmp, ignore_errors=True)

        tmp = tempfile.mkdtemp(prefix='blastlab_uichar_wfail_')
        p = lambda f: os.path.join(tmp, f)        # noqa: E731
        c1 = tw.case1d(tmp, profile_file=p('p1.txt'))
        c2 = tw.case2d(tmp, init_mode='profile1d',
                       profile_file_in=p('p1.txt'))
        got['chain_profile'] = press(win, [(1, c1), (2, c2)],
                                     p('p1.txt'), tmp)
        shutil.rmtree(tmp, ignore_errors=True)
    finally:
        win.close()
        pump(100)
    return got


def main():
    got = collect()
    fails = []
    for name, exp in EXPECTED.items():
        ok = got.get(name) == exp
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            print(f'      got      {got.get(name)}\n      expected {exp}')
            fails.append(name)
    print()
    print('UI WRITE FAILURE: ' + ('PASS' if not fails
                                  else f'FAIL ({len(fails)}): '
                                  + ', '.join(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
