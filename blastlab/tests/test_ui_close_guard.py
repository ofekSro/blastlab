"""GUI-11 T2 (UXR-1 = QA S2-2, decision D202): Close, Open and Recent ask
before they drop a live run or unsaved edits.

 C1  a dirty window: Cancel keeps it open with the case unchanged;
     Discard closes it; Save with a path writes the file, then closes;
     Save on an untitled case whose Save as is cancelled keeps it open
 C2  a dirty window and Open: Cancel leaves the case and the path alone
     and opens no file dialog; the same for a Recent action
 C3  a clean window Opens and closes without a question
 C4  a live run: Keep running ignores the close and sends no stop; a
     busy HD 1.3 assessment asks `Quit anyway?`

Every question goes through `dialogs.ask_discard`; each check patches it
with the answer it needs. Plain script, offscreen, no pytest:
`python test_ui_close_guard.py`.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from blastlab.ui.testing import ensure_qapp, pump             # noqa: E402

FAIL = []

try:
    sys.stdout.reconfigure(errors='replace')
except Exception:
    pass


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


class Asked:
    """`dialogs.ask_discard` answering `answer`, recording each call."""

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, kind, text, parent=None, title='BlastLab'):
        self.calls.append((kind, str(text), title))
        return self.answer


def patched(answer):
    from blastlab.ui import dialogs
    rec = Asked(answer)
    dialogs.ask_discard = rec
    return rec


def new_window(path=None):
    from blastlab.ui.app import MainWindow
    win = MainWindow()
    win.resize(1280, 840)
    win.show()
    pump(150)
    if path:
        win._open_case(path)
        pump(400)
    return win


def lx_of(win):
    return win.setup.forms[2].v['Lx'].get()


def main():
    print('UI CLOSE GUARD (GUI-11 T2)')
    ensure_qapp()
    from PySide6.QtGui import QCloseEvent
    from blastlab.core.case import Case2D, save_case
    from blastlab.ui import dialogs, testing
    from blastlab.ui.run_controller import RunController

    hook = dialogs.ask_discard
    check('ensure_qapp answers the question for tests (a recorder)',
          getattr(hook, '_test_hook', False)
          and testing.REAL_ASK_DISCARD is not None
          and testing.REAL_ASK_DISCARD is not hook)
    tmp = tempfile.mkdtemp(prefix='blastlab_close_')
    pa = os.path.join(tmp, 'wall_A.json')
    pb = os.path.join(tmp, 'wall_B.json')
    save_case(Case2D(Lx=3.0, Ly=2.0, cell_size_m=0.05, charge=5.0,
                     center=(0.0, 0.5), gauges=[(1.0, 1.0)]), pa)
    save_case(Case2D(Lx=4.0, Ly=2.0, cell_size_m=0.05, charge=5.0,
                     center=(0.0, 0.5), gauges=[(1.0, 1.0)]), pb)
    try:
        print('\nC3: a clean window opens and closes without asking')
        dialogs.ask_discard = hook
        del testing.DISCARD_ASKED[:]
        win = new_window(pa)
        check('a window opened from a file is clean after the pumps',
              not win._dirty)
        win._open_case(pb)
        pump(400)
        check('Open on a clean window loads without a question',
              win._case_path == pb and testing.DISCARD_ASKED == [],
              str(testing.DISCARD_ASKED))
        closed = win.close()
        pump(50)
        check('and it closes without a question',
              closed and testing.DISCARD_ASKED == [],
              str(testing.DISCARD_ASKED))

        print('\nC1: a dirty window on Close')
        win = new_window(pa)
        win.setup.forms[2].v['Lx'].set('5.5')
        pump(60)
        check('the edit made it dirty', win._dirty)
        rec = patched('cancel')
        closed = win.close()
        pump(50)
        check('Cancel: the window stays, the case unchanged',
              not closed and win.isVisible() and win._dirty
              and lx_of(win) == '5.5' and win._case_path == pa,
              f'closed={closed} lx={lx_of(win)!r}')
        check('one question, Save / Discard / Cancel, naming the file',
              [c[0] for c in rec.calls] == ['dirty']
              and rec.calls[0][1] == 'Save the changes to wall_A.json?'
              and rec.calls[0][2] == 'Quit BlastLab', str(rec.calls))
        rec = patched('proceed')
        closed = win.close()
        pump(50)
        check('Discard: it closes, the file untouched',
              closed and not win.isVisible()
              and json.load(open(pa, encoding='utf-8'))['Lx'] == 3.0,
              f'closed={closed}')

        win = new_window(pa)
        win.setup.forms[2].v['Lx'].set('6.5')
        pump(60)
        rec = patched('save')
        closed = win.close()
        pump(50)
        check('Save with a path: the file is written, then it closes',
              closed and not win.isVisible()
              and json.load(open(pa, encoding='utf-8'))['Lx'] == 6.5,
              f'closed={closed} '
              f'Lx={json.load(open(pa, encoding="utf-8"))["Lx"]}')

        win = new_window()
        win.setup.forms[2].v['Lx'].set('7.5')
        pump(60)
        rec = patched('save')
        real_save_file = dialogs.save_file
        dialogs.save_file = lambda *a, **k: ''
        try:
            closed = win.close()
            pump(50)
        finally:
            dialogs.save_file = real_save_file
        check('Save on an untitled case, Save as cancelled: it stays',
              not closed and win.isVisible() and win._dirty,
              f'closed={closed}')

        print('\nC2: a dirty window and Open / Recent')
        patched('proceed')          # discard the untitled edits
        win._open_case(pa)
        pump(400)
        win.setup.forms[2].v['Lx'].set('8.5')
        pump(60)
        check('dirty again on wall_A', win._dirty and win._case_path == pa)
        rec = patched('cancel')
        opened = []
        real_open_file = dialogs.open_file
        dialogs.open_file = lambda *a, **k: opened.append(a) or pb
        try:
            win._open_case()
            pump(100)
            check('Open, Cancel: no file dialog, case and path unchanged',
                  opened == [] and win._case_path == pa
                  and lx_of(win) == '8.5' and win._dirty,
                  f'opened={len(opened)} path={win._case_path!r} '
                  f'lx={lx_of(win)!r}')
            check('asked about the edits only, titled Open case',
                  [c[0] for c in rec.calls] == ['dirty']
                  and rec.calls[0][2] == 'Open case', str(rec.calls))
            win._push_recent(pb)
            win._fill_recent_menu()
            acts = [a for a in win._recent_menu.actions()
                    if a.text() == 'wall_B.json']
            rec = patched('cancel')
            if acts:
                acts[0].trigger()
                pump(100)
            check('a Recent entry, Cancel: case and path unchanged',
                  acts and win._case_path == pa and lx_of(win) == '8.5'
                  and [c[0] for c in rec.calls] == ['dirty'],
                  f'acts={len(acts)} path={win._case_path!r}')
            rec = patched('proceed')
            acts[0].trigger()
            pump(400)
            check('the same Recent entry, Discard: wall_B opens',
                  win._case_path == pb and lx_of(win) == '4'
                  and not win._dirty, f'{win._case_path!r} {lx_of(win)!r}')
        finally:
            dialogs.open_file = real_open_file

        print('\nC4: a live run and a busy HD 1.3 assessment on Close')
        stops, shuts = [], []
        real_running = RunController.running
        win.ctrl.stop = lambda: stops.append(1)
        win.ctrl.shutdown = lambda *a, **k: shuts.append(1)
        RunController.running = property(lambda self: True)
        try:
            win.ctrl._run_name = 'QA_RUN'
            rec = patched('cancel')
            ev = QCloseEvent()
            win.closeEvent(ev)
            pump(20)
            check('Keep running: the close is ignored, no stop is sent',
                  not ev.isAccepted() and stops == [] and shuts == []
                  and win.isVisible(),
                  f'accepted={ev.isAccepted()} stops={stops} '
                  f'shutdowns={shuts}')
            check('the question is `Stop QA_RUN … and quit?`',
                  rec.calls and rec.calls[0][0] == 'run'
                  and rec.calls[0][1].startswith('Stop QA_RUN')
                  and ' and quit?' in rec.calls[0][1].split('\n')[0],
                  str(rec.calls[:1]))
        finally:
            RunController.running = real_running
        win._hd13_busy = True
        win._hd13_model = 'HD13'
        rec = patched('cancel')
        ev = QCloseEvent()
        win.closeEvent(ev)
        win._hd13_busy = False
        check('a busy HD 1.3 assessment: Keep running ignores the close',
              not ev.isAccepted() and rec.calls
              and rec.calls[0][0] == 'hd13'
              and rec.calls[0][1] == 'An HD 1.3 assessment is still '
                                     'writing HD13. Quit anyway?',
              str(rec.calls[:1]))
        del win.ctrl.stop
        del win.ctrl.shutdown
        patched('proceed')
        win.close()
        pump(50)
    finally:
        dialogs.ask_discard = hook
    print('\nUI CLOSE GUARD: '
          + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
