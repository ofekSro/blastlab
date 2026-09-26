"""Characterisation: what the Tk GUI shows when a run's output write
fails (UX 2).

docs/UX_REVIEW.md section 3, finding 2. The Tk twin of
test_ui_char_write_failure.py: drives the REAL `gui.app.App` (root
withdrawn) through `App._start` - the call both Run and the Chain tab
end in - with one writer of `solvers/jobs` raising PermissionError for
one path (`test_char_write_failure.failing_writes`), and pins the Results
entries the run adds, the error dialogs (`App.show_error`, stubbed to
record), the run-log lines carrying the warning or the error headline,
and that Stop is disabled and Run back in its idle state afterwards.

Scenarios: a 2D run whose animation write fails; a 1D -> 2D chain whose
stage-1 profile (the hand-off) write fails, launched with the wiring the
Chain tab builds.

Script only - it builds Tk widgets, so conftest.py keeps it out of
pytest collection (`test_gui_*.py`). BLASTLAB_SETTINGS points at a
private file with `auto_cleanup: false` (`char_common`), so building the
window can never sweep the run corpus (CLAUDE.md 8.2).

Run:  cd blastlab/tests && python test_gui_char_write_failure.py
"""
import os
import shutil
import sys
import tempfile
import time

import char_common  # noqa: F401  (private settings, auto_cleanup off)
import test_char_write_failure as tw                          # noqa: E402

interesting = tw.gui_log_line
EXPECTED = tw.EXPECTED_GUI


def press(root, app, dim_cases, fail_path, tmp):
    dialogs = []
    app.show_error = lambda title, msg: dialogs.append(
        [title, tw._norm(msg, tmp)])
    n0 = len(app.results._entries)
    app.run_panel.log.configure(state='normal')
    app.run_panel.log.delete('1.0', 'end')
    idle_run = str(app.run_panel.run_btn.cget('state'))
    with tw.failing_writes(fail_path):
        app._start(dim_cases)
        t0 = time.monotonic()
        while app._drain_pending and time.monotonic() - t0 < 120:
            root.update()
            time.sleep(0.02)
        for _ in range(5):
            root.update()
    log = app.run_panel.log.get('1.0', 'end').splitlines()
    return dict(
        results=[e.label for e in app.results._entries[n0:]],
        dialogs=dialogs,
        log=[tw._norm(ln, tmp).strip() for ln in log if interesting(ln)],
        running=bool(app._drain_pending),
        stop_enabled=str(app.run_panel.stop_btn.cget('state')) == 'normal',
        run_back_to_idle=str(app.run_panel.run_btn.cget('state'))
        == idle_run)


def collect():
    import customtkinter as ctk
    from blastlab.gui import app as appmod
    root = ctk.CTk()
    root.withdraw()
    app = appmod.App(root)
    root.update()
    got = {}
    try:
        tmp = tempfile.mkdtemp(prefix='blastlab_guichar_wfail_')
        p = lambda f: os.path.join(tmp, f)        # noqa: E731
        got['2d_anim'] = press(
            root, app, [(2, tw.case2d(tmp, anim_file=p('a.gif'),
                                      profile_file=p('p2.npz')))],
            p('a.gif'), tmp)
        shutil.rmtree(tmp, ignore_errors=True)

        tmp = tempfile.mkdtemp(prefix='blastlab_guichar_wfail_')
        p = lambda f: os.path.join(tmp, f)        # noqa: E731
        c1 = tw.case1d(tmp, profile_file=p('p1.txt'))
        c2 = tw.case2d(tmp, init_mode='profile1d',
                       profile_file_in=p('p1.txt'))
        got['chain_profile'] = press(root, app, [(1, c1), (2, c2)],
                                     p('p1.txt'), tmp)
        shutil.rmtree(tmp, ignore_errors=True)
    finally:
        app._on_close()
        from blastlab.gui import theme
        theme._ICON_CACHE.clear()
    return got


def main():
    got = collect()
    fails = []
    # the same expectations as the Qt GUI: the two must behave alike
    for name, exp in EXPECTED.items():
        g = dict(got.get(name) or {})
        ok = g == exp
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            print(f'      got      {g}\n      expected {exp}')
            fails.append(name)
    print()
    print('GUI WRITE FAILURE: ' + ('PASS' if not fails
                                   else f'FAIL ({len(fails)}): '
                                   + ', '.join(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
