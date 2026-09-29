"""GUI-7 gate: the 03 Results screen (docs/gui-redesign-plan.md section 7,
board Results; batch docs/batches/2026-09-29-gui-results.md).

 S2  three columns 280 / centre / 320 at 1600 x 1000; nothing clipped at
     1100 x 720 (both modes, 12 results) nor on the 900 x 600 panel; the
     results list (duplicates numbered, the combo surface, `latest` on
     the newest only, a long label elided in the middle with the whole
     label as its tooltip); `method_rows` equal to rows built here from
     the same inputs (a native 2D result with a model folder, a
     blastFoam-shaped 2D result with a case.json, a native 1D result with
     none); Show case / Load into 01 Setup disabled with the why-not
     tooltip when there is no case file; Show case is non-modal and holds
     the file's text; Load into 01 Setup loads a new, unsaved case and
     never writes the model folder's MODEL.json, asking only when Setup is
     dirty; the stage hook.

Plain script, offscreen, throwaway settings, no window on screen:
    cd blastlab/tests && python test_ui_results_screen.py
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import traceback

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)

from blastlab.ui.testing import ensure_qapp, pump             # noqa: E402

app = ensure_qapp()

from PySide6.QtCore import Qt                                 # noqa: E402
from PySide6.QtWidgets import QLabel                          # noqa: E402

FAIL = []
RAN = []
TMP = tempfile.mkdtemp(prefix='blastlab_resscreen_')


def check(name, ok, detail=''):
    RAN.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def differ(got, want):
    """The detail of a failed comparison, '' when it holds."""
    return '' if got == want else f'{got} != {want}'


def t_part(res):
    """`t = … ms` of the final snapshot's label, found here on its own."""
    m = re.search(r't = [0-9.]+ ms', list(res.snapshots)[-1])
    return m.group(0) if m else None


# ── fixtures ─────────────────────────────────────────────────────────────
def model_case():
    """The Phase 0 2D case, with the two AMR thresholds at the Setup
    form's own values: with AMR off the form does not keep a file's
    `amr_refine` / `amr_unrefine` (Open case reads 0.2 / 0.1 back as
    0.4 / 0.2, before GUI-7 as after), so only this case round-trips."""
    import dataclasses
    from test_char_native_api import CASES
    return dataclasses.replace(CASES['2d'], amr_refine=0.4, amr_unrefine=0.2)


def model_folder_2d():
    """A native 2D result with a model folder built here: MODEL.json (the
    Phase 0 2D case) and a manifest.json."""
    import char_meta_results as cm
    from blastlab.models.case import save_case
    res = cm.native('2d')
    home = os.path.join(TMP, 'wall_A')
    os.makedirs(home, exist_ok=True)
    save_case(model_case(), os.path.join(home, 'MODEL.json'))
    with open(os.path.join(home, 'manifest.json'), 'w',
              encoding='utf-8') as f:
        json.dump(dict(solver='native', n_procs=1,
                       created='2026-09-29T10:00:00',
                       finished='2026-09-29T10:05:31'), f)
    res.meta['model_dir'] = home
    return res, home


def foam_2d():
    """A blastFoam-shaped 2D result whose (loaded) case directory holds a
    case.json with activation linear and afterburn none; meta['refine']
    carries lmax 2 over a 25 mm base cell."""
    import char_meta_results as cm
    res = cm.foam_shaped('2d')
    cd = os.path.join(TMP, 'foam_run')
    os.makedirs(cd, exist_ok=True)
    with open(os.path.join(cd, 'case.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(schema='blastlab-case', dim=2, solver='blastfoam',
                       material='TNT', activation='linear',
                       afterburn='none'), f)
    res.meta['case_dir'] = cd
    res.meta['refine'] = dict(lmax=2, dx_base=0.025)
    return res, cd


# ── S2 ───────────────────────────────────────────────────────────────────
def s2_layout(win):
    from test_gui_results_fields import fake_2d
    from test_ui_parity import clipped
    print('\nS2a: three columns, nothing clipped')
    rs = win.results
    win._show('results')
    for i in range(12):
        rs.add_result(f'result number {i} with a longish name (2D)', 2,
                      fake_2d())
    win.resize(1600, 1000)
    pump(200)
    left, centre, right = rs.column_widths()
    check('1600 x 1000: 280 / centre / 320',
          abs(left - 280) <= 1 and abs(right - 320) <= 1 and centre > 400,
          str(rs.column_widths()))
    for mode in ('native', 'blastfoam'):
        win.set_solver(mode)
        win.resize(1100, 720)
        pump(200)
        bad = clipped(win)
        check(f'1100 x 720, {mode}, 12 results: nothing clipped',
              not bad, f'{bad[:4]} widths {rs.column_widths()}')
    check('1100 x 720: the side columns keep 280 / 320',
          rs.column_widths()[0] == 280 and rs.column_widths()[2] == 320,
          str(rs.column_widths()))
    rows = rs.sel.rows()
    check('the list scrolls inside its column when rows do not fit',
          rs.sel.scroll.verticalScrollBar().maximum() > 0
          and all(r.height() >= 44 for r in rows),
          f'bar {rs.sel.scroll.verticalScrollBar().maximum()} '
          f'rows {min(r.height() for r in rows)}')
    while rs.entries():
        rs.sel.setCurrentIndex(0)
        rs.remove_current()
    pump(30)


def s2_panel_900(link):
    from test_gui_results_fields import fake_2d
    from test_ui_parity import clipped
    from blastlab.ui.results_panel import ResultsPanel
    p = ResultsPanel(viewer_link=link, log_fn=lambda *_: None)
    p.resize(900, 600)
    p.show()
    for i in range(12):
        p.add_result(f'result number {i} with a longish name (2D)', 2,
                     fake_2d())
    for mode in ('native', 'blastfoam'):
        p.set_solver_mode(mode)
        pump(150)
        bad = clipped(p)
        check(f'the panel at 900 x 600, {mode}, 12 results: nothing '
              f'clipped', not bad, str(bad[:4]))
    p.shutdown()
    p.deleteLater()
    pump(20)


def s2_list(p):
    from test_gui_results_fields import fake_2d
    from blastlab.ui.results_panel import PICKER_MAX
    print('\nS2b: the results list')
    a = p.add_result('run', 2, fake_2d())
    b = p.add_result('run', 2, fake_2d())
    pump(30)
    check('two results with the same label -> run, run #2',
          [e.label for e in p.entries()] == ['run', 'run #2'],
          str([e.label for e in p.entries()]))
    check('sel.currentData() is the second', p.sel.currentData() is b)
    p.sel.setCurrentIndex(0)
    pump(20)
    check('sel.setCurrentIndex(0) reaches the first', p.current() is a)
    long = 'a-very-long-run-name-that-will-not-fit-in-the-picker (2D)'
    c = p.add_result(long, 2, fake_2d())
    pump(30)
    rows = p.sel.rows()
    check('newest last: the rows are in the order added',
          [p.sel.itemData(i) for i in range(p.sel.count())] == [a, b, c])
    check('the newest row, and only it, carries latest',
          [not r.latest.isHidden() for r in rows] == [False, False, True])
    check('a long label is elided in the middle',
          len(c.display) == PICKER_MAX and '…' in c.display
          and c.display.endswith('(2D)')
          and p.sel.itemText(2) == c.display, c.display)
    check('and itemData(i, ToolTipRole) is the whole label',
          p.sel.itemData(2, Qt.ToolTipRole) == long
          and rows[2].toolTip() == long)
    check('the selected row has the accent fill (selected property)',
          [r.selected() for r in rows] == [False, False, True])
    check('each row carries its caption',
          rows[0].caption.full_text() == '2D planar', rows[0].caption.full_text())
    check('no chain badge on a single run',
          all(r.chain.isHidden() for r in rows))
    rows[0].clicked.emit(rows[0])
    pump(20)
    check('a click on a row selects it', p.current() is a
          and rows[0].selected())
    while p.entries():
        p.sel.setCurrentIndex(0)
        p.remove_current()
    pump(20)


def s2_method(p):
    import char_meta_results as cm
    from blastlab.core.constants import P_AIR          # noqa: F401
    from blastlab.ui import results_method as RM
    from test_char_native_api import CASES
    print('\nS2c: how it was computed')

    # a native 2D result with a model folder
    res, home = model_folder_2d()
    m = res.meta
    want = [('Solver', 'native'),
            ('Charge', f"{m['charge']:g} kg {CASES['2d'].material}"
                       f" · z {m['charge_center'][1]:g} m"),
            ('Mesh', f"cell {m['dx'] * 1000:g} mm"),
            ('Parallel', 'serial'),
            ('Ended', f'{res.stop_reason} · {t_part(res)} · finished 10:05')]
    got = RM.method_rows(res, 2)
    check('native 2D + model folder: the rows built here', got == want,
          differ(got, want))
    check('native 2D: no Detonation / Afterburn row',
          not {'Detonation', 'Afterburn'} & {k for k, _v in got})
    ent2 = p.add_result('wall_A', 2, res)
    pump(30)
    check('the panel shows the same rows', p.method_rows() == want)
    check('the list caption: 2D axisym. · native · 5 min 31 s',
          p.sel.rows()[-1].caption.full_text()
          == '2D axisym. · native · 5 min 31 s',
          p.sel.rows()[-1].caption.full_text())
    check('the path line shows the model folder',
          p._path_lbl.full_text() == home
          and not p._path_lbl.isHidden())
    check('Show case and Load into 01 Setup enabled',
          p.method.show_btn.isEnabled() and p.method.load_btn.isEnabled())
    v = p.show_case()
    pump(30)
    with open(os.path.join(home, 'MODEL.json'), 'rb') as f:
        text = f.read().decode('utf-8')
    check('Show case: a non-modal viewer holding the file\'s text',
          v is not None and not v.isModal() and v.isVisible()
          and v.text() == text
          and v.view.toPlainText() == text.replace('\r\n', '\n')
          and v.windowTitle() == 'Case as run · wall_A',
          v.windowTitle() if v else 'None')
    v.copy()
    from PySide6.QtWidgets import QApplication
    check('Copy puts the whole file on the clipboard',
          QApplication.clipboard().text().replace('\r\n', '\n')
          == text.replace('\r\n', '\n'))
    v.close()

    # a blastFoam-shaped 2D result with a loaded run's case.json
    fres, _cd = foam_2d()
    fm = fres.meta
    want = [('Solver', 'blastFoam'),
            ('Charge', f"{fm['charge']:g} kg TNT"
                       f" · z {fm['charge_center'][1]:g} m"),
            ('Detonation', 'linear'),
            ('Afterburn', 'none'),
            ('Mesh', f"cell {fm['dx'] * 1000:g} mm · finest "
                     f"{0.025 / 2 ** 2 * 1000:.3g} mm"),
            ('Ended', f'{fres.stop_reason} · {t_part(fres)}')]
    got = RM.method_rows(fres, 2)
    check('blastFoam-shaped 2D + case.json: the rows built here',
          got == want, differ(got, want))
    check('its case source is the run\'s case.json',
          RM.case_source(p.add_result('foam', 2, fres))
          == os.path.join(_cd, 'case.json'))

    # a native 1D result with no model folder
    r1 = cm.native('1d')
    want = [('Charge', f"{r1.meta['charge_kg']:g} kg"),
            ('Ended', f'{r1.stop_reason} · {t_part(r1)}')]
    got = RM.method_rows(r1, 1)
    check('native 1D, no model folder: the rows built here', got == want,
          differ(got, want))
    keys = {k for k, _v in got}
    check('1D: no Solver, Detonation, Afterburn or Parallel row',
          not {'Solver', 'Detonation', 'Afterburn', 'Parallel'} & keys)
    check('1D: the Ended row begins with its stop_reason, verbatim',
          dict(got)['Ended'].startswith(r1.stop_reason))
    everything = [v for r in (res, fres, r1)
                  for _k, v in RM.method_rows(r, 2 if r is not r1 else 1)]
    check('no row reads None, nan or ?',
          not any(re.search(r'\bNone\b|\bnan\b|\?', v)
                  for v in everything), str(everything))
    e1 = p.add_result('free_field_1D', 1, r1)
    pump(30)
    tip = RM.NO_CASE_TIP
    check('no case file: Show case / Load disabled with the why-not tip',
          not p.method.show_btn.isEnabled()
          and not p.method.load_btn.isEnabled()
          and p.method.show_btn.toolTip() == tip
          and p.method.load_btn.toolTip() == tip
          and tip == 'This result carries no saved case (no model '
                     'folder).')
    check('and Show case opens nothing', p.show_case() is None)
    check('the path line is hidden without a model folder',
          p._path_lbl.isHidden())
    check('Remove says which result it removes',
          p._remove_btn.toolTip() == 'Remove free_field_1D from the list',
          p._remove_btn.toolTip())
    for ent in (e1, ent2):
        p.sel.setCurrentIndex(p.entries().index(ent))
        p.remove_current()
    while p.entries():
        p.sel.setCurrentIndex(0)
        p.remove_current()
    pump(20)
    return res, home


def s2_load_into_setup(win, res, home):
    from blastlab.models.case import load_case
    from blastlab.ui import dialogs
    print('\nS2d: Load into 01 Setup')
    model = os.path.join(home, 'MODEL.json')
    before = sha(model)
    rs = win.results
    win._set_dirty(False)
    rs.add_result('wall_A', 2, res)
    win._show('results')
    pump(50)
    real_ask, real_save = dialogs.ask_yes_no, dialogs.save_file
    asked, saved = [], []
    dialogs.ask_yes_no = lambda *a, **k: asked.append((a, k)) or False
    dialogs.save_file = lambda *a, **k: saved.append(a) or ''
    try:
        rs.method.load_btn.click()
        pump(100)
        check('Load into 01 Setup shows Setup',
              win.current_tab() == 'setup', str(win.current_tab()))
        loaded = win.setup.get_case()
        check('Setup holds the case of MODEL.json',
              loaded == load_case(model))
        check('as a new case: no path, and dirty',
              win._case_path is None and win._dirty)
        check('with Setup clean, nothing was asked', not asked)
        check('the run name is the model',
              win.run_panel.current_run_name() == 'wall_A',
              str(win.run_panel.current_run_name()))
        win._save_case_inplace()
        pump(20)
        check('Ctrl+S goes to Save as (cancelled here)', len(saved) == 1)
        check('MODEL.json is unchanged byte for byte', sha(model) == before)
        # the Phase 0 case as saved (AMR thresholds at the dataclass
        # defaults): Load gives exactly what Open case gives for it
        from blastlab.models.case import save_case
        from test_char_native_api import CASES
        plain = os.path.join(TMP, 'plain', 'MODEL.json')
        os.makedirs(os.path.dirname(plain), exist_ok=True)
        save_case(CASES['2d'], plain)
        win._set_dirty(False)
        win._load_case_from_result(plain)
        via_load = win.setup.get_case()
        win._open_case(plain)
        check('for any case file, Load into 01 Setup = Open case',
              via_load == win.setup.get_case())
        # a profile start: MODEL.json holds the hand-off relative to its
        # folder, and load_case resolves it there (models/case.py)
        import dataclasses
        prof_dir = os.path.join(TMP, 'chain_B', '2d')
        os.makedirs(prof_dir, exist_ok=True)
        with open(os.path.join(prof_dir, 'handoff.txt'), 'w') as f:
            f.write('# r p rho u\n')
        prof = os.path.join(prof_dir, 'MODEL.json')
        save_case(dataclasses.replace(model_case(), init_mode='profile1d',
                                      profile_file_in='handoff.txt'), prof)
        win._set_dirty(False)
        win._load_case_from_result(prof)
        got_prof = win.setup.get_case().profile_file_in
        check('a relative profile file resolves against the model folder',
              os.path.normcase(os.path.abspath(got_prof or ''))
              == os.path.normcase(os.path.join(prof_dir, 'handoff.txt')),
              str(got_prof))
        # Setup dirty beforehand: asked once, Keep editing changes nothing
        win._show('results')
        win.setup.set_case(load_case(model))
        win._case_path = os.path.join(TMP, 'mine.json')
        win._set_dirty(True)
        was = win.setup.get_case()
        rs.method.load_btn.click()
        pump(50)
        check('Setup dirty: asked once',
              len(asked) == 1 and asked[0][0][0] == 'Load into 01 Setup'
              and asked[0][1].get('yes') == 'Replace'
              and asked[0][1].get('no') == 'Keep editing'
              and asked[0][0][1] == 'Replace the unsaved changes in mine?',
              str(asked[:1]))
        check('Keep editing changes nothing',
              win.current_tab() == 'results'
              and win._case_path == os.path.join(TMP, 'mine.json')
              and win._dirty and win.setup.get_case() == was)
    finally:
        dialogs.ask_yes_no, dialogs.save_file = real_ask, real_save
    while rs.entries():
        rs.sel.setCurrentIndex(0)
        rs.remove_current()
    win._case_path = None
    win._set_dirty(False)
    pump(20)


def s2_stage_hook(p):
    from test_gui_results_fields import fake_2d
    print('\nS2e: the stage hook')
    p.add_result('single', 2, fake_2d())
    pump(30)
    check('stage_slot hidden at 0 px for a single result',
          p.stage_slot.isHidden() and p.stage_slot.height() == 0
          and p.stage_strip() is None)
    lbl = QLabel('x')
    p.set_stage_strip(lbl)
    pump(40)
    check('set_stage_strip shows it above the view tabs',
          not p.stage_slot.isHidden() and p.stage_strip() is lbl
          and p.stage_slot.height() > 0
          and p.stage_slot.geometry().bottom() < p._seg_frame.y(),
          f'slot {p.stage_slot.geometry()} tabs y {p._seg_frame.y()}')
    p.set_stage_strip(None)
    pump(40)
    check('None hides it again at 0 px',
          p.stage_slot.isHidden() and p.stage_slot.height() == 0
          and p.stage_strip() is None and lbl.parent() is None)
    while p.entries():
        p.sel.setCurrentIndex(0)
        p.remove_current()
    pump(20)


def main():
    from blastlab.ui.app import MainWindow
    from blastlab.ui.results_panel import ResultsPanel
    from test_ui_view3d_host import FakeLink
    crashes = []
    sys.excepthook = lambda *a: crashes.append(
        ''.join(traceback.format_exception(*a)))
    win = MainWindow()
    win.show()
    pump(200)
    link = FakeLink()
    p = ResultsPanel(viewer_link=link, log_fn=lambda *_: None)
    p.resize(1280, 840)
    p.show()
    pump(50)
    try:
        s2_layout(win)
        s2_panel_900(link)
        s2_list(p)
        res, home = s2_method(p)
        s2_load_into_setup(win, res, home)
        s2_stage_hook(p)
    finally:
        check('nothing raised', not crashes, crashes[0][-400:]
              if crashes else '')
        # the recorder is for Qt slots only: an exception out of a check
        # function still prints its traceback (61bfd56)
        sys.excepthook = sys.__excepthook__
        p.shutdown()
        win.close()
        pump(100)
        shutil.rmtree(TMP, ignore_errors=True)
    bad = [m for m in sys.modules
           if m.split('.')[0] in ('vtk', 'vtkmodules', 'pyvista', 'pyvistaqt')
           or m == 'matplotlib.pyplot']
    check('no VTK / pyplot in the GUI process', not bad, str(bad[:3]))
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'UI RESULTS SCREEN: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
