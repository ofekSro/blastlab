"""Editing the Tk 2D form updates the status strip's cell count.

The Tk twin of `test_ui_status_cells.py` (docs/ARCHITECTURE_REVIEW.md
section 5, Phase 3): validation moved out of `core/case.py` into
`services/validation.py`, and the way back must still show the same
numbers. Loads `cases/native_2d_small.json` into a withdrawn App, then
sets the cell-size field's variable - the write trace an Entry keystroke
fires - and lets the 300 ms `after()` debounce run. The strip's rows are
read from the `show_report` call. Literals from the code before the move.

Withdrawn Tk root, private settings (auto_cleanup off), native case: no
WSL. Run:  cd blastlab/tests && python test_gui_status_cells.py
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')
if not os.environ.get('BLASTLAB_SETTINGS'):
    os.environ['BLASTLAB_SETTINGS'] = os.path.join(
        tempfile.mkdtemp(prefix='blastlab_status_cells_'), 'settings.json')

CASE = os.path.join(HERE, 'cases', 'native_2d_small.json')
LINE_LOADED = '~24,576 cells at dx = 0.012499 m'
LINE_TYPED = '~38,400 cells at dx = 0.01 m'

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def pump(root, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.01)


def main():
    from blastlab.ui.testing import disable_cleanup
    disable_cleanup()
    import customtkinter as ctk
    from blastlab.core.case import load_case
    from blastlab.gui import app as appmod

    root = ctk.CTk()
    root.withdraw()
    app = appmod.App(root)
    root.update_idletasks()

    shown = []
    real_show = app.setup.show_report

    def spy(errors=(), warnings=(), notes=()):
        shown.append((list(errors), list(warnings), list(notes)))
        return real_show(errors, warnings, notes)
    app.setup.show_report = spy

    def cell_lines():
        if not shown:
            return []
        return [m for m in shown[-1][2] if ' cells at dx = ' in m]

    print('S1: the loaded 2D case')
    app.setup.set_case(load_case(CASE))
    app._schedule_validate()
    pump(root, 1.0)
    check('the strip shows the cell count', cell_lines() == [LINE_LOADED],
          str(cell_lines()))

    print('S2: editing the cell size')
    app.setup.form.v['cell'].set('0.01')
    pump(root, 1.0)
    check('the strip follows the edit', cell_lines() == [LINE_TYPED],
          str(cell_lines()))
    check('and the case is runnable', bool(shown) and not shown[-1][0],
          str(shown[-1][0] if shown else None))
    root.destroy()

    print()
    print('GUI STATUS CELLS: ' + ('PASS' if not FAIL else
                                  f'FAIL ({len(FAIL)}): ' + ', '.join(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
