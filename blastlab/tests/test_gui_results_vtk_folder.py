"""GUI QA 2026-09-27 F2, the Tk twin of test_ui_results_vtk_folder.py.

The Tk GUI is the permanent way back (CLAUDE.md section 9), so its
Results tab gets the same fix: after an OUT-2 run that wrote
`<MODEL>\\vtk\\` and released its WSL scratch, the VTK button is live,
its tooltip says where the files are and how many, and pressing it opens
that folder instead of converting. A released run without vtk\\ keeps
the greyed SCRATCH_RELEASED text.

Script only - it builds Tk widgets (withdrawn root). No WSL, no solver.
Run:  cd blastlab/tests && python test_gui_results_vtk_folder.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_gv_'),
                                   'settings.json'))

import customtkinter as ctk                                  # noqa: E402

from test_gui_results_fields import fake_3d                  # noqa: E402
from test_ui_results_vtk_folder import model_folder, released  # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def tip_of(widget):
    return getattr(getattr(widget, '_blastlab_tip', None), 'text', '')


def main():
    from blastlab.gui import results_panel as rp
    from blastlab.services import exports as svc

    tmp = tempfile.mkdtemp(prefix='blastlab_gv_runs_')
    with_vtk = model_folder(tmp, 'WITH_VTK', True)
    without = model_folder(tmp, 'NO_VTK', False)
    root = ctk.CTk()
    root.withdraw()
    log = []
    panel = rp.ResultsPanel(root, log_fn=log.append)
    panel.set_solver_mode('blastfoam')
    btn = panel._export_btns['vtk']

    print('\nT1: the Tk button after an OUT-2 run')
    panel.add_result('with vtk', 3, released(fake_3d(), with_vtk))
    root.update_idletasks()
    check('the VTK button is enabled', str(btn.cget('state')) == 'normal')
    check('its tooltip points at the vtk\\ folder, not "nothing left"',
          tip_of(btn).startswith('Written during the run: ')
          and os.path.join(with_vtk, 'vtk') in tip_of(btn)
          and '4 files' in tip_of(btn), tip_of(btn))

    print('\nT2: pressing it opens the folder and writes nothing')
    opened, asked = [], []
    real_open, real_fd = svc._open, rp.filedialog

    class NoDialog:
        def __getattr__(self, name):
            return lambda *a, **k: asked.append(name) or ''
    svc._open = lambda path, log: opened.append(path)
    rp.filedialog = NoDialog()
    before = sorted(os.listdir(with_vtk))
    try:
        panel._export('vtk')
        root.update_idletasks()
    finally:
        svc._open, rp.filedialog = real_open, real_fd
    check('the folder is opened', opened == [os.path.join(with_vtk, 'vtk')],
          str(opened))
    check('no dialog, nothing written',
          not asked and sorted(os.listdir(with_vtk)) == before)
    check('the log says where the files are',
          any('written during the run' in s and '4 files' in s for s in log),
          str(log[-2:]))

    print('\nT3: a released run without vtk\\ keeps the old text')
    panel.add_result('no vtk', 3, released(fake_3d(), without))
    root.update_idletasks()
    check('greyed, SCRATCH_RELEASED',
          str(btn.cget('state')) == 'disabled'
          and tip_of(btn) == svc.SCRATCH_RELEASED, tip_of(btn))

    panel.destroy()
    root.destroy()
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} check(s): {FAIL}')
        sys.exit(1)
    print('GUI RESULTS VTK FOLDER: PASS')


if __name__ == '__main__':
    main()
