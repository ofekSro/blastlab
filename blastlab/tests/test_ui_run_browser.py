"""The Qt blastFoam run browser, driven without WSL.

Every data source is injectable (`lister`, `sizer`, `deleter`, `confirm`,
`warner`), so this drives the real widget with fabricated runs.

The rules under test are the ones that protect a live solver and an
unattended driver:

- Resume and Delete act only when `alive is False`. `None` means WSL did
  not report, and acting blind would race the solver, so it is refused
  exactly like a running run.
- Every refusal reaches the status line and the log BEFORE any dialog is
  attempted. The P2-8 check patches the warner to RAISE, and the refusal
  must still be fully recorded - that is what makes "the dialog is last"
  a property rather than a comment.
- The two-phase fill keeps the selection by name, because the row order
  can change between the names pass and the sizes pass.

Run:  cd blastlab/tests && python test_ui_run_browser.py
"""
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_rb_'),
                                   'settings.json'))

from blastlab.solvers.foam import runs as runs_mod              # noqa: E402
from blastlab.ui.testing import ensure_qapp, pump               # noqa: E402

FAIL = []
RAN = []

#: name -> alive. One of each state the lister can report.
FAKE = (('20260905-162157_2d_p26412-00', False),
        ('20260906-090000_3d_p1-00', True),
        ('20260907-235959_1d_p2-00', None))


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def until(pred, limit=300):
    """Pump the loop until `pred()`, or give up. The browser's two
    passes arrive from a worker thread through ThreadBridge."""
    for _ in range(limit):
        if pred():
            return True
        pump(10)
    return pred()


def main():
    ensure_qapp()
    from blastlab.ui import dialogs                      # noqa: F401
    from blastlab.ui.run_browser import FoamRunBrowser

    print('\nB1: the three module helpers')
    check('human_size rounds and labels',
          [runs_mod.human_size(n) for n in (None, 0, 900, 2048,
                                            5 * 1024 ** 3)]
          == ['?', '0 B', '900 B', '2.0 KB', '5.0 GB'],
          str([runs_mod.human_size(n) for n in (None, 0, 900, 2048,
                                                5 * 1024 ** 3)]))
    check('a stamped run name becomes a readable date',
          runs_mod.started_from_name('20260905-162157_2d_p26412-00')
          == '2026-09-05 16:21:57',
          runs_mod.started_from_name('20260905-162157_2d_p26412-00'))
    check('and an unstamped one is blank, not a crash',
          runs_mod.started_from_name('my-run') == '')
    missing = tempfile.mkdtemp(prefix='blastlab_nocase_')
    check('a run dir with no case.json reports its dim as ?',
          runs_mod.dims_from_case_json(missing) == '?')
    with open(os.path.join(missing, 'case.json'), 'w',
              encoding='utf-8') as f:
        f.write('{"dim": 2}')
    check('and reads it when there is one',
          runs_mod.dims_from_case_json(missing) == '2D')
    with open(os.path.join(missing, 'case.json'), 'w',
              encoding='utf-8') as f:
        f.write('not json at all')
    check('a corrupt case.json is ? as well, not an exception',
          runs_mod.dims_from_case_json(missing) == '?')
    check('None is "unknown", NOT "finished" - that distinction is the '
          'whole guard',
          [runs_mod.state_text(a) for a in (True, False, None)]
          == ['running', 'finished', 'unknown'])

    print('\nB2: the two-phase fill')
    log = []
    gate = threading.Event()
    sized_calls = []

    def lister():
        return [(name, os.path.join(missing, name), alive)
                for name, alive in FAKE]

    def sizer(dirs):
        sized_calls.append(list(dirs))
        gate.wait(10)                     # held so phase 1 is observable
        return {d: dict(bytes=(i + 1) * 1024 ** 2)
                for i, d in enumerate(dirs)}
    loaded, resumed, deleted = [], [], []
    win = FoamRunBrowser(
        on_load=loaded.append, log=log.append, lister=lister,
        sizer=sizer, deleter=lambda dirs: (deleted.append(list(dirs))
                                           or True),
        confirm=lambda t, m: True, on_resume=resumed.append,
        warner=lambda t, m: None, runs_dir=lambda: 'RUNS',
        # P2-17: the first run is held by a chain's stage folder of MODEL_A
        modeler=lambda runs, posix: (
            os.path.join(runs, 'MODEL_A', '2d')
            if runs == 'RUNS' and posix.endswith(FAKE[0][0]) else None))
    win.resize(760, 420)
    win.show()
    until(lambda: len(win.names()) == 3)
    check('P2-17: the Model column is last, a placeholder until the second '
          'pass', win.table.horizontalHeaderItem(5).text() == 'Model'
          and win.row_text(FAKE[0][0])[5] == '…',
          str(win.row_text(FAKE[0][0])))
    check('the names are on screen before any size is known',
          win.names() == [n for n, _a in FAKE], str(win.names()))
    check('with the size column still a placeholder',
          win.row_text(FAKE[0][0])[2] == '…',
          str(win.row_text(FAKE[0][0])))
    check('and the states already readable',
          [win.row_text(n)[4] for n, _a in FAKE]
          == ['finished', 'running', 'unknown'],
          str([win.row_text(n)[4] for n, _a in FAKE]))
    check('the dims came from each case.json', win.row_text(FAKE[0][0])[1]
          in ('2D', '?'), str(win.row_text(FAKE[0][0])[1]))
    win.select(FAKE[1][0])                # pick the middle row
    gate.set()
    until(lambda: win.row_text(FAKE[0][0])[2] != '…')
    check('the sizes arrive in a second pass',
          win.row_text(FAKE[0][0])[2] == '1.0 MB',
          str(win.row_text(FAKE[0][0])))
    check('P2-17: the Model column names the model that holds each run (a '
          'chain\'s stage folder gives its model), `-` when none does',
          [win.row_text(n)[5] for n, _a in FAKE] == ['MODEL_A', '-', '-'],
          str([win.row_text(n)[5] for n, _a in FAKE]))
    check('and the selection survived it, by name',
          win.selected_name() == FAKE[1][0], str(win.selected_name()))
    check('the status line totals them',
          '3 runs' in win.status.text()
          and 'total' in win.status.text(), win.status.text())
    check('the sizer was asked for posix paths, not UNC ones',
          sized_calls and all('/' in d for d in sized_calls[0]),
          str(sized_calls[:1]))

    print('\nB3: Load')
    win.select(FAKE[0][0])
    check('Load hands the UNC path to the loader',
          win.load_selected() is True and len(loaded) == 1
          and FAKE[0][0] in loaded[0], str(loaded))
    check('and says so in the log',
          any('loading' in s for s in log), str(log[-1:]))
    win.table.clearSelection()
    win.table.setCurrentCell(-1, -1)
    n = len(loaded)
    check('with nothing selected it asks, it does not guess',
          win.load_selected() is False and len(loaded) == n
          and 'select a run first' in win.status.text())

    print('\nB4: Resume and Delete refuse anything not finished')
    for name, alive in FAKE[1:]:          # True and None
        state = 'running' if alive else 'unknown'
        win.select(name)
        n_log = len(log)
        win.status.setText('')
        check(f'{state}: Resume refused',
              win.resume_selected() is False and not resumed,
              str(resumed))
        check(f'{state}: with the reason on the status line',
              'not resuming' in win.status.text()
              and win.status.text().endswith(
                  'is still running' if alive
                  else 'did not report its state'), win.status.text())
        check(f'{state}: and in the log',
              any('refused to resume' in s for s in log[n_log:]),
              str(log[n_log:]))
        n_log = len(log)
        win.status.setText('')
        check(f'{state}: Delete refused',
              win.delete_selected() is False and not deleted,
              str(deleted))
        check(f'{state}: with the reason on the status line',
              'not deleting' in win.status.text(), win.status.text())
        check(f'{state}: and in the log',
              any('refused to delete' in s for s in log[n_log:]),
              str(log[n_log:]))

    print('\nB5: P2-8 - the dialog is provably last')
    warned = []

    def exploding(title, msg):
        warned.append((title, msg))
        raise RuntimeError('a modal would have blocked here')
    win._warn = exploding
    win.select(FAKE[1][0])                # the running one
    win.status.setText('')
    n_log = len(log)
    check('a refused Delete still returns False when the dialog raises',
          win.delete_selected() is False and not deleted)
    check('the status line was written BEFORE the dialog',
          'not deleting' in win.status.text(), win.status.text())
    check('and so was the log',
          any('refused to delete' in s for s in log[n_log:]),
          str(log[n_log:]))
    check('the dialog was attempted, and its failure noted',
          warned and any('dialog failed' in s for s in log[n_log:]),
          str(log[n_log:]))
    win._warn = lambda t, m: None

    print('\nB6: Delete on a finished run')
    win.select(FAKE[0][0])
    asked = []
    win._confirm = lambda t, m: (asked.append((t, m)) or True)
    gate.clear()
    check('it confirms first', win.delete_selected() is True
          and len(asked) == 1)
    check('naming the run and its size',
          FAKE[0][0] in asked[0][1] and '1.0 MB' in asked[0][1],
          asked[0][1])
    check('and warning that it cannot be undone',
          'cannot be undone' in asked[0][1])
    until(lambda: bool(deleted))
    check('the deleter got the POSIX path, not the UNC one',
          deleted and deleted[0] and '/' in deleted[0][0]
          and FAKE[0][0] in deleted[0][0], str(deleted))
    gate.set()
    until(lambda: not win._busy)
    check('and the table was refreshed afterwards',
          len(win.names()) == 3, str(win.names()))
    deleted.clear()
    win._confirm = lambda t, m: False
    win.select(FAKE[0][0])
    check('declining the confirmation deletes nothing',
          win.delete_selected() is False and not deleted)

    print('\nB7: Resume on a finished run')
    win._confirm = lambda t, m: True
    win.select(FAKE[0][0])
    check('it closes the dialog BEFORE handing over, so the Run tab '
          'is not behind a modal',
          win.resume_selected() is True and not win.isVisible()
          and len(resumed) == 1, f'{win.isVisible()} {resumed}')
    check('and the resume got the UNC path',
          FAKE[0][0] in resumed[0], str(resumed))

    print('\nB8: a listing that fails is reported, not a dead window')
    bad = FoamRunBrowser(
        log=log.append, lister=lambda: (_ for _ in ()).throw(
            OSError('wsl is down')), sizer=lambda d: {},
        warner=lambda t, m: None)
    until(lambda: 'failed' in bad.status.text())
    check('the status line says what happened',
          'listing failed' in bad.status.text()
          and 'wsl is down' in bad.status.text(), bad.status.text())
    check('and so does the log',
          any('listing failed' in s for s in log), str(log[-1:]))
    check('the window is still alive and refreshable',
          bad.refresh() is True)
    bad.close()

    print('\nB9: no Resume button when there is nothing to resume')
    plain = FoamRunBrowser(log=log.append, lister=lister,
                           sizer=lambda d: {}, autorefresh=False,
                           warner=lambda t, m: None)
    check('Resume is absent without an on_resume callback',
          plain.btn_resume is None)
    check('the other four are there',
          all(b is not None for b in (plain.btn_load, plain.btn_delete,
                                      plain.btn_refresh,
                                      plain.btn_close)))
    check('autorefresh=False lists nothing until asked',
          plain.names() == [])
    plain.close()
    win.close()

    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI RUN BROWSER: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
