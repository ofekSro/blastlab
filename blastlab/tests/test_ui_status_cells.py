"""Typing in the Qt 2D form updates the status strip's cell count.

docs/ARCHITECTURE_REVIEW.md section 5, Phase 3: the GUI check that
validation still reaches the window after it moved out of `core/case.py`
into `services/validation.py`. Loads `cases/native_2d_small.json`, reads
the strip, types a new cell size into the real QLineEdit (so the change
goes through `textEdited` and the window's 300 ms debounce, exactly as a
keystroke does), and reads the strip again. The two cell-count lines are
literals written from the code as it was before the move.

Offscreen, private settings (auto_cleanup off), a native case: no WSL.
Run:  cd blastlab/tests && python test_ui_status_cells.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')
if not os.environ.get('BLASTLAB_SETTINGS'):
    os.environ['BLASTLAB_SETTINGS'] = os.path.join(
        tempfile.mkdtemp(prefix='blastlab_status_cells_'), 'settings.json')

CASE = os.path.join(HERE, 'cases', 'native_2d_small.json')
#: the strip's cell line for the case as loaded (dx 0.04 is refined to
#: put MIN_EXP_CELLS across the 20 kg charge) and after typing 0.01
LINE_LOADED = '~24,576 cells at dx = 0.012499 m'
LINE_TYPED = '~38,400 cells at dx = 0.01 m'

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def cell_lines(win):
    return [m for sev, m in win.setup.report_rows()
            if sev == 'note' and ' cells at dx = ' in m]


def main():
    from blastlab.ui.testing import disable_cleanup, ensure_qapp, pump
    disable_cleanup()
    ensure_qapp()
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from blastlab.core.case import load_case
    from blastlab.ui.app import MainWindow

    def wait_for(pred, ms=5000):
        """Pump in 50 ms steps until `pred()` or `ms` ran out: the 300 ms
        debounce plus a validation pass is not a fixed 600 ms on a busy
        machine (GUI-14 h). The checks below still judge the result."""
        for _ in range(ms // 50):
            if pred():
                return
            pump(50)

    win = MainWindow()
    win.show()
    pump(150)
    print('S1: the loaded 2D case')
    win.setup.set_case(load_case(CASE))
    win._schedule_validate()
    wait_for(lambda: cell_lines(win) == [LINE_LOADED])
    check('the strip shows the cell count', cell_lines(win) == [LINE_LOADED],
          str(cell_lines(win)))

    print('S2: typing a cell size')
    edit = win.setup.form.widgets['cell']
    edit.setFocus()
    edit.selectAll()
    QTest.keyClick(edit, Qt.Key_Backspace)
    QTest.keyClicks(edit, '0.01')
    wait_for(lambda: cell_lines(win) == [LINE_TYPED])
    check('the field holds what was typed',
          win.setup.form.v['cell'].get() == '0.01',
          win.setup.form.v['cell'].get())
    check('the strip follows the keystrokes', cell_lines(win) == [LINE_TYPED],
          str(cell_lines(win)))
    check('and the case is runnable',
          not any(sev == 'error' for sev, _m in win.setup.report_rows()),
          str(win.setup.report_rows()))
    win.close()
    pump(50)

    print()
    print('UI STATUS CELLS: ' + ('PASS' if not FAIL else
                                 f'FAIL ({len(FAIL)}): ' + ', '.join(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
