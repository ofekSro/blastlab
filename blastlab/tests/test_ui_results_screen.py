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
 S3  the export column: Data / Figures in board order, the suffixes
     (profile .txt / .npz by dimension, the animation's default_ext()),
     40 px buttons, Open the 3D viewer at 42 px; no label cut and nothing
     clipped at 1100 x 720 (both modes) and on the 900 x 600 panel; VTK
     hidden in native mode; the busy strip (a blocking run_export): up
     only once a target is chosen, no double start (logged), another
     kind still starts, Remove still works, both back when done,
     `_export_done` and the VTK error dialog on the GUI thread; Open the
     3D viewer disabled with its why-not for 1D, 2D, a 3D result with no
     snapshots and without pyvista, enabled for a 3D result with
     snapshots; the title box retitles the figures (E09).
 S5  the Gauges view: every curve is (times x 1e3, GAUGE_FIELDS' transform)
     exactly; Z = scaled_distance of the entered gauge (the sample
     geometry: G1 3.31, G2 2.99), rows by Z; every numeric cell is
     table_rows' string by gauge number; the selected curve in `gauge` at
     2.4 px, the others grey, the positive phase shaded over [arrival,
     arrival + duration] and moved by a row click, none for |U|; the
     readout; the default selection (trigger, else first row) and the
     panel API; Copy table and Ctrl+C (table-scoped) put the text built
     here on the clipboard, nine columns with Z, eight without; planar and
     a profile start hide Z; 1D Z = r / W^(1/3); the plot keeps the
     stretch at 1100 x 720 and 900 x 600, twelve gauges scroll.

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
    # GUI-7 verification: the list held two rows with the column half
    # empty, the newest (selected) one scrolled out of sight
    from PySide6.QtGui import QPalette
    from blastlab.ui import theme

    def in_view(row):
        vp = p.sel.scroll.viewport()
        return vp.rect().contains(row.mapTo(vp, row.rect().center()))
    check('three rows with room to spare: every row shown, no scrolling',
          p.sel.scroll.verticalScrollBar().maximum() == 0
          and all(in_view(r) for r in rows),
          f'vbar {p.sel.scroll.verticalScrollBar().maximum()}')
    check('the selected row\'s caption is muted (faint is 4.47:1 on '
          'accent_bg in light mode)',
          rows[2].caption.palette().color(QPalette.WindowText).name()
          == theme.cur('muted')
          and rows[0].caption.palette().color(QPalette.WindowText).name()
          == theme.cur('faint'))
    rows[0].clicked.emit(rows[0])
    pump(20)
    check('a click on a row selects it', p.current() is a
          and rows[0].selected())
    many = [p.add_result(f'more {k}', 2, fake_2d()) for k in range(14)]
    pump(60)
    newest = p.sel.rows()[-1]
    check('more rows than fit: the list scrolls, and the newest (selected) '
          'row is in view', p.sel.scroll.verticalScrollBar().maximum() > 0
          and p.current() is many[-1] and in_view(newest),
          f'vbar {p.sel.scroll.verticalScrollBar().maximum()}')
    p.sel.setCurrentIndex(0)
    pump(30)
    check('and selecting the first scrolls it back into view',
          in_view(p.sel.rows()[0]))
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
            ('Mesh', f"cell {m['dx'] * 1000:.3g} mm"),     # T20: .3g
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
            ('Mesh', f"cell {fm['dx'] * 1000:.3g} mm · finest "
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

    # GUI-11 T20 (UXR-10): unit, precision, caveat, the Ended wrap
    import copy
    pl = copy.copy(res)
    pl.meta = dict(res.meta, geometry='planar')
    ch = dict(RM.method_rows(pl, 2)).get('Charge', '')
    check('a planar charge reads kg/m (a line charge)',
          f"{m['charge']:g} kg/m " in ch and ' kg ' not in ch, ch)
    check('an axisymmetric charge still reads kg',
          dict(RM.method_rows(res, 2))['Charge'].startswith(
              f"{m['charge']:g} kg "), dict(RM.method_rows(res, 2))['Charge'])
    dxr = copy.copy(res)
    dxr.meta = dict(res.meta, dx=0.0124352)
    check('dx 0.0124352 reads cell 12.4 mm (amends D90)',
          dict(RM.method_rows(dxr, 2))['Mesh'] == 'cell 12.4 mm',
          dict(RM.method_rows(dxr, 2))['Mesh'])
    c4 = copy.copy(fres)
    c4.meta = dict(fres.meta, material='C4')
    c4d = os.path.join(TMP, 'foam_run_c4')
    os.makedirs(c4d, exist_ok=True)
    with open(os.path.join(c4d, 'case.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(schema='blastlab-case', dim=2, solver='blastfoam',
                       material='C4', activation='linear',
                       afterburn='miller'), f)
    c4.meta['case_dir'] = c4d
    ab = dict(RM.method_rows(c4, 2)).get('Afterburn')
    check('a C4 blastFoam result with miller: the TNT-only caveat',
          ab == 'miller (calibrated for TNT only)', repr(ab))
    tnt = copy.copy(c4)
    tnt.meta = dict(c4.meta, material='TNT')
    with open(os.path.join(c4d, 'case.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(schema='blastlab-case', dim=2, solver='blastfoam',
                       material='TNT', activation='linear',
                       afterburn='miller'), f)
    ab = dict(RM.method_rows(tnt, 2)).get('Afterburn')
    check('TNT with miller: no caveat', ab == 'miller', repr(ab))
    ent_e = p.add_result('ended_wrap', 2, res)
    pump(30)
    lbl = p.method.value_label('Ended')
    check('the Ended value word-wraps, onto at most two lines',
          lbl is not None and lbl.wordWrap()
          and lbl.full_text() == dict(
              want_e := RM.method_rows(res, 2))['Ended']
          and 1 <= len(lbl.text().split('\n')) <= 2,
          repr(lbl.text() if lbl else None))
    shown = lbl.text().replace('\n', ' ')
    check('its lines are the text (the second elided only when cut, the '
          'whole text then its tooltip)',
          shown == lbl.full_text() or (shown.endswith('…')
                                       and lbl.toolTip() == lbl.full_text()),
          repr(lbl.text()))
    others = [p.method.value_label(k) for k, _v in want_e if k != 'Ended']
    check('the other values stay one elided line',
          all(not hasattr(w, 'wordWrap') or not w.wordWrap()
              for w in others))
    p.sel.setCurrentIndex(p.entries().index(ent_e))
    p.remove_current()
    pump(20)
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
        win._done_mark = True               # a run ended on its own (D68)
        win._update_title()
        rs.method.load_btn.click()
        pump(100)
        check('Load into 01 Setup shows Setup',
              win.current_tab() == 'setup', str(win.current_tab()))
        check('a case was opened: the title drops the last run\'s ✓ Done '
              '(D68)', '✓ Done' not in win.windowTitle()
              and not win._done_mark, win.windowTitle())
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
    # T4 (sampler: 29 ms / 44 px without it): with the 3D view on screen
    # the viewer's window is shrunk by the strip's height first (D70)
    calls = []
    real = p.view3d.shrink_ahead
    p.view3d.shrink_ahead = calls.append
    try:
        p.set_stage_strip(QLabel('y'))          # Fields on screen
        pump(20)
        p.set_stage_strip(None)
        pump(20)
        check('the strip over Fields shrinks no viewer', calls == [])
        p.show_view('3D')
        pump(40)
        strip = QLabel('STAGE')
        strip.setFixedHeight(32)
        p.set_stage_strip(strip)
        pump(40)
        want = 32 + p._centre.layout().spacing()
        check('over the 3D view: shrink_ahead(strip + spacing) first, once',
              calls == [want] and p.stage_slot.height() == 32,
              f'{calls} want [{want}] slot {p.stage_slot.height()}')
        p.set_stage_strip(None)
        pump(20)
        check('and taking it away shrinks nothing', calls == [want])
    finally:
        p.view3d.shrink_ahead = real
        p.show_view('Fields')
    while p.entries():
        p.sel.setCurrentIndex(0)
        p.remove_current()
    pump(20)


# ── S3 ───────────────────────────────────────────────────────────────────
def s3_layout(win, link):
    from test_gui_results_fields import fake_2d
    from test_ui_parity import clipped
    from test_ui_results import fake_1d
    from blastlab.output.animation import default_ext
    from blastlab.ui.results_panel import ResultsPanel
    print('\nS3a: the export column')
    rs = win.results
    col = rs.export_col
    check('Data = summary, tsv, fieldcsv, profile, vtk; Figures = pngs, '
          'report, gif', col.order() == {
              'Data': ('summary', 'tsv', 'fieldcsv', 'profile', 'vtk'),
              'Figures': ('pngs', 'report', 'gif')}, str(col.order()))
    check('_export_btns maps the same 8 kinds to the new buttons',
          sorted(rs._export_btns) == sorted(
              ['summary', 'tsv', 'fieldcsv', 'profile', 'vtk', 'pngs',
               'report', 'gif'])
          and all(rs._export_btns[k] is col.items[k].button
                  for k in rs._export_btns))
    win.set_solver('blastfoam')
    win._show('results')
    win.resize(1600, 1000)
    pump(120)
    ys = [col.items[k].mapTo(col, col.items[k].rect().topLeft()).y()
          for k in col.order()['Data'] + col.order()['Figures']]
    check('and they sit in that order, top to bottom', ys == sorted(ys),
          str(ys))
    heights = {k: it.button.height() for k, it in col.items.items()}
    check('each export button is 40 px', set(heights.values()) == {40},
          str(heights))
    check('Open the 3D viewer is 42 px, at the foot',
          rs._view3d_btn.height() == 42
          and rs._view3d_btn.text() == 'Open the 3D viewer',
          str(rs._view3d_btn.height()))
    e1 = rs.add_result('one', 1, fake_1d())
    pump(30)
    check('Profile suffix .txt for a 1D result',
          col.items['profile'].suffix.text() == '.txt')
    e2 = rs.add_result('two', 2, fake_2d())
    pump(30)
    check('and .npz for a 2D result',
          col.items['profile'].suffix.text() == '.npz')
    check('the Animation suffix is default_ext()',
          col.items['gif'].suffix.text() == default_ext(),
          col.items['gif'].suffix.text())
    check('the title box: placeholder `added above the automatic title`',
          rs.title_box.placeholderText() == 'added above the automatic '
                                            'title')
    for mode in ('native', 'blastfoam'):
        win.set_solver(mode)
        win.resize(1100, 720)
        pump(150)
        cut = [it.text() for it in col.items.values()
               if not it.isHidden() and not it.label_fits()]
        bad = clipped(win)
        check(f'1100 x 720, {mode}: no export label cut, nothing clipped',
              not cut and not bad, f'{cut} {bad[:3]}')
    win.set_solver('native')
    pump(30)
    check('native: the VTK export and its button are hidden',
          col.items['vtk'].isHidden() and rs._export_btns['vtk'].isHidden())
    win.set_solver('blastfoam')
    pump(30)
    check('blastFoam: both back',
          not col.items['vtk'].isHidden()
          and not rs._export_btns['vtk'].isHidden())
    for ent in (e1, e2):
        rs.sel.setCurrentIndex(rs.entries().index(ent))
        rs.remove_current()
    pump(20)
    p = ResultsPanel(viewer_link=link, log_fn=lambda *_: None)
    p.resize(900, 600)
    p.show()
    p.add_result('two', 2, fake_2d())
    pump(120)
    cut = [it.text() for it in p.export_col.items.values()
           if not it.label_fits()]
    check('the panel at 900 x 600: no export label cut, nothing clipped',
          not cut and not clipped(p), f'{cut} {clipped(p)[:3]}')
    p.shutdown()
    p.deleteLater()
    pump(20)


def s3_busy(link):
    import threading
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication
    from test_gui_results_fields import fake_2d
    from test_ui_results import with_gauges
    from blastlab.ui import dialogs
    from blastlab.ui import exports as UE
    from blastlab.ui.results_panel import ResultsPanel
    print('\nS3b: busy, and no double start (UX-13)')
    log = []
    p = ResultsPanel(viewer_link=link, log_fn=log.append)
    p.resize(1280, 840)
    p.show()
    ent = p.add_result('gauged', 2, with_gauges(fake_2d()))
    pump(50)
    out = os.path.join(TMP, 'busy')
    os.makedirs(out, exist_ok=True)
    gate = threading.Event()
    started = []
    threads = []

    def blocking(kind, *_a, **_k):
        started.append(kind)
        gate.wait(20)
        return 'written'

    def save_file(title, filters='', parent=None, start='',
                  default_suffix=None):
        return os.path.join(out, os.path.basename(start) or 'x')

    real = (UE.run_export, dialogs.save_file, dialogs.pick_dir)
    real_done = p._export_done

    def done(kind):
        threads.append(QThread.currentThread() is app.thread())
        real_done(kind)
    p._export_done = done
    UE.run_export = blocking
    dialogs.save_file = save_file
    dialogs.pick_dir = lambda *a, **k: out
    items = p.export_col.items
    try:
        ret = p.export('summary')
        pump(80)
        check('export(summary) starts one writer and shows its busy strip',
              ret and started == ['summary']
              and not items['summary'].strip.isHidden()
              and items['summary'].button.isHidden()
              and p.busy_kinds() == {'summary'}, f'{ret!r} {started}')
        check('the strip: the name, writing…, an indeterminate bar',
              items['summary'].busy_name.text() == 'Summary'
              and items['summary'].busy_text.text() == 'writing…'
              and items['summary'].bar.maximum() == 0
              and items['summary'].strip.height() >= 40,
              str(items['summary'].strip.height()))
        del log[:]
        again = p.export('summary')
        pump(80)
        check('a second export(summary) returns \'\' and adds no writer',
              again == '' and started == ['summary'], str(started))
        check('and logs that it is already being written',
              log == ['Summary is already being written.'], str(log))
        ret2 = p.export('tsv')
        pump(80)
        check('export(tsv) still starts',
              ret2 and started == ['summary', 'tsv']
              and not items['tsv'].strip.isHidden(), str(started))
        p.remove_current()
        pump(30)
        check('Remove still works while writing', p.entries() == [])
        p.add_result('gauged', 2, ent.result)
        pump(30)
        gate.set()
        for _ in range(60):
            pump(20)
            if not p.busy_kinds():
                break
        check('after the writers finish both buttons are back and enabled',
              not p.busy_kinds()
              and not items['summary'].button.isHidden()
              and not items['tsv'].button.isHidden()
              and items['summary'].strip.isHidden()
              and p.export_enabled('summary') and p.export_enabled('tsv'))
        check('_export_done ran on the GUI thread',
              threads == [True, True], str(threads))
        # a cancelled dialog shows nothing
        dialogs.save_file = lambda *a, **k: ''
        started.clear()
        ret3 = p.export('summary')
        pump(40)
        check('a cancelled dialog shows no strip and starts nothing',
              ret3 == '' and not started and not p.busy_kinds()
              and items['summary'].strip.isHidden())
    finally:
        gate.set()
        UE.run_export, dialogs.save_file, dialogs.pick_dir = real
        p._export_done = real_done
    check('ui.exports.run_export restored',
          UE.run_export is real[0])
    # the VTK failure dialog is posted to the GUI thread (was shown from
    # the worker)
    shown = []
    real_err = dialogs.show_error
    dialogs.show_error = lambda *a, **k: shown.append(
        (a[:2], QThread.currentThread() is app.thread()))
    try:
        t = threading.Thread(target=p._post_error, args=('VTK export',
                                                          'boom'))
        t.start()
        t.join()
        pump(40)
    finally:
        dialogs.show_error = real_err
    check('on_error from a worker shows its dialog on the GUI thread',
          shown == [(('VTK export', 'boom'), True)], str(shown))
    QApplication.processEvents()
    p.shutdown()
    p.deleteLater()
    pump(20)


def s3_view3d_and_title(link):
    from test_gui_results_fields import fake_2d, fake_3d
    from test_ui_results import fake_1d
    from blastlab.ui import results_panel as RP
    from blastlab.viz3d import MISSING_MSG
    print('\nS3c: Open the 3D viewer, the title box')
    log = []
    p = RP.ResultsPanel(viewer_link=link, log_fn=log.append)
    p.resize(1280, 840)
    p.show()
    pump(30)
    b = p._view3d_btn
    check('no result: disabled, `Select a result first.`',
          not b.isEnabled() and b.toolTip() == 'Select a result first.')
    for name, dim, res in (('1D', 1, fake_1d()), ('2D', 2, fake_2d())):
        p.add_result(name, dim, res)
        pump(20)
        check(f'{name}: disabled, `3D results only.`',
              not b.isEnabled() and b.toolTip() == '3D results only.',
              b.toolTip())
    empty3 = fake_3d()
    empty3.snapshots = {}
    p.add_result('3D, no snapshots', 3, empty3)
    pump(20)
    check('3D with no snapshots: disabled, `This result has no snapshots.`',
          not b.isEnabled()
          and b.toolTip() == 'This result has no snapshots.', b.toolTip())
    real = RP.pyvista_available
    RP.pyvista_available = lambda: False
    try:
        p.add_result('3D, no pyvista', 3, fake_3d())
        pump(20)
        check('3D without pyvista: disabled with MISSING_MSG',
              not b.isEnabled() and b.toolTip() == MISSING_MSG)
    finally:
        RP.pyvista_available = real
    p.add_result('3D', 3, fake_3d())
    pump(20)
    check('3D with snapshots under the FakeLink: enabled',
          b.isEnabled() == real(), f'pyvista {real()}')
    p.sel.setCurrentIndex(0)
    pump(20)
    del log[:]
    p.open_3d()
    check('open_3d() keeps its log line for a 1D result',
          log == ['3D Viewer: select a 3D result.'], str(log))
    p.sel.setCurrentIndex(1)
    pump(20)
    p.title_box.setText('QA title')
    pump(60)
    check('the title box rides into the panel and the figure (E09)',
          'QA title' in (p.title_extra() or '')
          and 'QA title' in (p.fields.title() or ''),
          repr(p.fields.title()))
    p.title_box.setText('')
    pump(20)
    p.shutdown()
    p.deleteLater()
    pump(20)


# ── S5 ───────────────────────────────────────────────────────────────────
def sample_2d(trigger=None, from_profile=False):
    """The sample geometry (plan section 10, GUI-5): 1 kg at z 2 on the
    axis, gauges G1 (2.95, 0.50) and G2 (2.95, 1.50) as entered; the
    solver snapped them half a 5 cm cell away. Z: G1 3.31, G2 2.99."""
    import numpy as np
    from blastlab.core.constants import P_AIR
    from blastlab.solvers.hooks import Result
    from test_gui_results_fields import fake_2d
    res = fake_2d()
    t = np.linspace(0.0, 8e-3, 400)
    traces = []
    for k, (t0, pk) in enumerate(((4.7e-3, 184e3), (4.15e-3, 231e3))):
        s = np.clip((t - t0) / 1.3e-3, 0.0, None)
        p = np.where(t >= t0, P_AIR + pk * (1 - s) * np.exp(-2 * s), P_AIR)
        traces.append(p)
    res.gauges = dict(times=t, points=[(2.975, 0.525), (2.975, 1.525)],
                      pressures=traces)
    res.meta.update(geometry='axisymmetric', charge=1.0,
                    charge_center=(0.0, 2.0), dx=0.05,
                    gauges=[(2.95, 0.50), (2.95, 1.50)],
                    from_profile=from_profile, trigger_gauge=trigger)
    return Result(res.snapshots, res.gauges, res.meta, res.stop_reason,
                  False)


def sample_case():
    from blastlab.models.case import Case2D
    return Case2D(geometry='axisymmetric', Lx=4.0, Ly=4.0,
                  cell_size_m=0.05, charge=1.0, center=(0.0, 2.0),
                  gauges=[(2.95, 0.50), (2.95, 1.50)])


def want_text(g, strings, zs, order):
    """The clipboard text built here: the visible headers, then one line
    per row in on-screen order, `table_rows` strings and Z (.2f)."""
    from blastlab.ui import results_gauges as RG
    heads = [h for i, h in enumerate(RG.HEADERS) if zs or i != 1]
    lines = ['\t'.join(heads)]
    for n in order:
        row = strings[n - 1]
        cells = [f'G{n}'] + ([f'{zs[n]:.2f}'] if zs else []) + list(row[1:])
        lines.append('\t'.join(cells))
    return '\n'.join(lines)


def sample_dropped():
    """The sample result with THREE entered gauges, the second inside
    Wall 1 (r 1.0-1.4 m, z 0-1.2 m): the solver dropped it, so the
    payload holds two series - G1 and G3 as entered (UXR-2, D201)."""
    res = sample_2d()
    res.meta.update(gauges=[(2.95, 0.50), (1.2, 0.6), (2.95, 1.50)],
                    obstacles=[(1.0, 1.4, 0.0, 1.2)], Lx=4.0, Ly=4.0)
    return res


def s5g_dropped(link):
    """UXR-2 / D201 (GUI-11 T8): a dropped gauge keeps the later gauges'
    entered numbers on screen, and the caption names it; rows() (D98),
    the headers and every export are unchanged."""
    from blastlab.output import gauge_summary
    from blastlab.ui import results_gauges as RG
    from blastlab.ui.exports import summary_rows
    from blastlab.ui.results_panel import ResultsPanel
    print('\nS5g: a gauge the solver dropped (inside Wall 1)')
    p = ResultsPanel(viewer_link=link, log_fn=lambda *_: None)
    p.resize(1600, 1000)
    p.show()
    p.show_view('Gauges')
    g = p.gauges
    res = sample_dropped()
    p.add_result('dropped', 2, res)
    pump(60)
    labels = [c[0] for c in g.cells()]
    check('two rows, labelled G3 (Z 2.99) then G1 (Z 3.31): the entered '
          'numbers', labels == ['G3', 'G1']
          and [c[1] for c in g.cells()] == ['2.99', '3.31'],
          str(g.cells()))
    check('the caption names G2 first, then the usual caption',
          g.caption_text() == 'G2 dropped by the solver (inside Wall 1) · '
          + RG.TABLE_CAPTION, g.caption_text())
    # GUI-13 (g), QA #3: the note wraps on a line of its own, and the
    # static caption above it stays one elided line
    dc = g.drop_caption
    check('the drop note is its own wrapped line, whole; the caption '
          'above stays one line',
          dc.isVisibleTo(g) and dc.wordWrap()
          and dc.text() == 'G2 dropped by the solver (inside Wall 1)'
          and g.table_caption.full_text() == RG.TABLE_CAPTION,
          f'{dc.text()!r}')
    # GUI-13 (d), D6: the Qt PNG / report export hands that note to the
    # gauge figure as its footnote
    import types
    from blastlab.ui import exports as UE
    seen = []
    real = (UE.pick_target, UE.run_export)
    UE.pick_target = lambda *a, **k: 'target'
    UE.run_export = lambda *a: seen.append(a[3])
    try:
        ent = types.SimpleNamespace(result=res, dim=2)
        UE.export('pngs', ent, threaded=False)
        UE.export('tsv', ent, threaded=False)
    finally:
        UE.pick_target, UE.run_export = real
    note = 'G2 dropped by the solver (inside Wall 1)'
    fig = dict(UE.png_figures(res, 2, drop_note=note))['blast_2d_gauges.png']
    check('GUI-13 (d): export_drop_note is the caption\'s note; the PNG '
          'export passes it (a TSV does not), and it is the figure\'s '
          'footnote',
          RG.export_drop_note(res, 2) == note
          and seen == [{'gauge_drop_note': note}, None]
          and fig._supxlabel is not None
          and fig._supxlabel.get_text() == note, str(seen))
    check('rows() is table_rows(summary_rows(res)), unchanged (D98)',
          g.rows() == [tuple(r) for r in gauge_summary.table_rows(
              summary_rows(res))], str(g.rows()))
    check('the headers are unchanged', g.headers() == list(RG.HEADERS),
          str(g.headers()))
    # F42 (GUI-11e A1): the exported label numbers the gauge as the cell
    # does, so each Gauge cell's tooltip starts with the cell's own label
    tips = [g.table.item(r, 0).toolTip() for r in range(len(labels))]
    check("each Gauge cell's tooltip starts with its own label (F42)",
          all(tip.startswith(lab + ' (') for lab, tip in zip(labels, tips))
          and len(tips) == 2, str(list(zip(labels, tips))))
    check('the keys stay the payload numbers; the readout says G3',
          g.order() == [2, 1] and g.selected() == 2
          and g.readout_text()[0] == 'G3 · Z 2.99',
          f'{g.order()} {g.selected()} {g.readout_text()}')
    # verify 11b: the Field view's arrival tick names it as Gauges does
    fv = p.field_view
    check('the Field caption\'s arrival tick names G3, not G2',
          fv._gauge_label == 'G3'
          and 'arrival at G2.' not in fv.caption.text()
          and ('arrival at' not in fv.caption.text()
               or 'arrival at G3.' in fv.caption.text()),
          f'{fv._gauge_label!r} {fv.caption.text()!r}')
    p.add_result('sample', 2, sample_2d())
    pump(40)
    check('a result without a dropped gauge: the Field caption is '
          'G<number> again', fv._gauge_label == f'G{g.selected()}',
          f'{fv._gauge_label!r} {g.selected()}')
    check('a result without a dropped gauge: G2 / G1 and the plain '
          'caption again', [c[0] for c in g.cells()] == ['G2', 'G1']
          and g.caption_text() == RG.TABLE_CAPTION,
          f'{g.cells()} {g.caption_text()}')
    p.shutdown()
    p.deleteLater()
    pump(20)


def s5_gauges(win, link):
    import numpy as np
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    import test_char_exports as ce
    from test_gui_results_fields import fake_2d
    from test_ui_results import with_gauges
    from blastlab.output import gauge_summary, plots
    from blastlab.ui import results_gauges as RG
    from blastlab.ui import scaled_distance as sd
    from blastlab.ui import theme
    from blastlab.ui.exports import summary_rows
    from blastlab.ui.results_panel import ResultsPanel
    print('\nS5: Gauges - one plot, the selection, the table, Copy')
    p = ResultsPanel(viewer_link=link, log_fn=lambda *_: None)
    p.resize(1600, 1000)
    p.show()
    p.show_view('Gauges')
    g = p.gauges
    tr = plots.GAUGE_FIELDS['p'][2]

    for name, res, case in (('char 2D', ce.result('2d'), None),
                            ('sample', sample_2d(), sample_case())):
        p.add_result(name, 2, res)
        pump(60)
        t = res.gauges['times']
        curves = g.traces()
        check(f'{name}: one curve per gauge, each (times*1e3, '
              f'GAUGE_FIELDS[p](p_k)) exactly',
              sorted(curves) == list(range(1, len(res.gauges['pressures'])
                                           + 1))
              and all(np.array_equal(curves[k + 1][0], t * 1e3)
                      and np.array_equal(curves[k + 1][1], tr(pk))
                      for k, pk in enumerate(res.gauges['pressures'])))
        if case is None:
            from test_char_native_api import CASES
            case = CASES['2d']
        zs = {k: sd.scaled_distance(case, pt)
              for k, pt in enumerate(case.gauges, start=1)}
        strings = gauge_summary.table_rows(summary_rows(res))
        order = sorted(zs, key=lambda n: (zs[n], n))
        check(f'{name}: rows sorted by Z, ties by number',
              g.order() == order, f'{g.order()} vs {order}')
        shown = {int(r[0][1:]): r for r in g.cells()}
        check(f'{name}: Z = scaled_distance(case, entered gauge), .2f',
              all(shown[n][1] == f'{zs[n]:.2f}' for n in zs),
              str({n: (shown[n][1], round(zs[n], 4)) for n in zs}))
        check(f'{name}: every numeric cell is table_rows\' string, by '
              f'gauge number',
              all(shown[n][2:] == list(strings[n - 1][1:]) for n in zs))
        check(f'{name}: the Gauge cell is G<n>, its tooltip the old label',
              all(g.table.item(r, 0).text() == f'G{n}'
                  and g.table.item(r, 0).toolTip() == strings[n - 1][0]
                  for r, n in enumerate(g.order())))
    zs_txt = [c[1] for c in g.cells()]
    check('sample: G2 2.99 above G1 3.31 (plan section 10)',
          g.order() == [2, 1] and zs_txt == ['2.99', '3.31'], str(zs_txt))

    print('\nS5b: selection, positive phase, readout')
    grey = RG.GREY[theme.mode()]
    gauge = theme.cur('gauge')
    rows = summary_rows(p.current().result)
    strings = gauge_summary.table_rows(rows)
    check('the default is the first row (no trigger gauge)',
          g.selected() == 2 and p.selected_gauge() == 2)

    def selected_ok(n):
        other = 1 if n == 2 else 2
        a, d = rows[n - 1]['arrival_ms'], rows[n - 1]['pos_duration_ms']
        span = g.fill_span()
        return (g.pen_of(n) == (gauge, RG.SELECTED_W)
                and g.pen_of(other) == (grey, RG.OTHER_W)
                and span is not None and abs(span[0] - a) < 1e-9
                and abs(span[1] - (a + d)) < 1e-9)
    check('selected curve: gauge at 2.4 px, the other grey at 1.2; the '
          'fill spans [arrival, arrival + positive phase]', selected_ok(2),
          f'{g.pen_of(1)} {g.pen_of(2)} {g.fill_span()}')
    row = strings[1]
    check('the readout is the table\'s own strings',
          g.readout_text() == ['G2 · Z 2.99',
                               f'peak {row[1]} kPa at {row[3]} ms',
                               f'pos. impulse {row[5]} kPa·ms'],
          str(g.readout_text()))
    heard = []
    g.gauge_selected.connect(heard.append)
    rect = g.table.visualRect(g.table.model().index(1, 3))
    QTest.mouseClick(g.table.viewport(), Qt.LeftButton, Qt.NoModifier,
                     rect.center())
    pump(30)
    check('a click on the second row selects G1: pens, fill and readout '
          'move', g.selected() == 1 and selected_ok(1) and heard == [1]
          and g.readout_text()[0] == 'G1 · Z 3.31',
          f'{g.selected()} {heard} {g.readout_text()}')
    p.show_view('Field')
    pump(20)
    p.show_view('Gauges')
    pump(20)
    check('the selection persists across the view tabs',
          p.selected_gauge() == 1)
    p.select_gauge(2)
    check('select_gauge(n) is the API', g.selected() == 2
          and selected_ok(2))
    p.add_result('trigger', 2, sample_2d(trigger=1))
    pump(40)
    check('a result change resets it: the trigger gauge when set',
          p.selected_gauge() == 1 and selected_ok(1))

    print('\nS5c: Copy table, Ctrl+C')
    clip = QApplication.clipboard()
    # R = sqrt(2.95^2 + 1.5^2) and sqrt(2.95^2 + 0.5^2), W = 1 kg
    zmap = {1: 3.309456, 2: 2.992073}
    zs = {n: sd.scaled_distance(sample_case(), pt) for n, pt in
          enumerate(sample_case().gauges, start=1)}
    check('the test\'s Z: G1 3.31, G2 2.99',
          all(abs(zs[n] - zmap[n]) < 1e-5 for n in zs), str(zs))
    want = want_text(g, strings, zs, [2, 1])
    clip.setText('sentinel')
    g.copy_btn.click()
    pump(10)
    got = clip.text()
    check('Copy table: tab-separated, headers first, on-screen order, no '
          'trailing newline', got == want, repr(got[:120]))
    check('nine columns with Z',
          all(len(line.split('\t')) == 9 for line in got.split('\n')))
    clip.setText('sentinel')
    g.table.setFocus()
    QTest.keyClick(g.table, Qt.Key_C, Qt.ControlModifier)
    pump(10)
    check('Ctrl+C with the table focused copies the same text',
          clip.text() == want, repr(clip.text()[:60]))
    clip.setText('sentinel')
    p.title_box.setText('abc')
    p.title_box.setFocus()
    QTest.keyClick(p.title_box, Qt.Key_C, Qt.ControlModifier)
    pump(10)
    check('Ctrl+C in the title box leaves the table alone',
          clip.text() == 'sentinel', repr(clip.text()[:60]))
    p.title_box.setText('')
    from PySide6.QtGui import QKeySequence, QShortcut
    copy = QKeySequence(QKeySequence.Copy).toString()
    check('Ctrl+C is the focused table\'s own key: no QShortcut for it in '
          'the panel (never window-wide; test_ui_frame F5 pins the window)',
          not [s for s in p.findChildren(QShortcut)
               if s.key().toString() == copy])

    print('\nS5d: Z hidden - planar and a profile start')
    for name, res in (('planar 2D', with_gauges(fake_2d())),
                      ('profile start', sample_2d(from_profile='1d'))):
        p.add_result(name, 2, res)
        pump(40)
        strings = gauge_summary.table_rows(summary_rows(res))
        n = len(strings)
        check(f'{name}: the Z column is hidden, rows by number',
              g.table.isColumnHidden(1) and g.order() == list(
                  range(1, n + 1)) and not g.z_shown())
        clip.setText('sentinel')
        g.copy_table()
        got = clip.text()
        check(f'{name}: eight columns copied, built here',
              got == want_text(g, strings, None, list(range(1, n + 1)))
              and all(len(line.split('\t')) == 8
                      for line in got.split('\n')), repr(got[:80]))
        check(f'{name}: the readout has no Z',
              g.readout_text()[0] == f'G{g.selected()}')

    print('\nS5e: other traces, 1D')
    p.add_result('three traces', 2,
                 with_gauges(fake_2d(), fields=('p', '|U|', 'rho')))
    pump(40)
    check('p: the fill is on', g.fill_span() is not None)
    g.field_seg.changed.emit('|U|')
    pump(30)
    ok_u = all(np.array_equal(
        g.traces()[k + 1][1], plots.GAUGE_FIELDS['|U|'][2](s))
        for k, s in enumerate(p.current().result.gauges['speeds']))
    check('|U|: the curves are the speeds, the y-label the builder\'s, '
          'and there is no fill',
          ok_u and g.fill_span() is None
          and g.ylabel() == plots.GAUGE_FIELDS['|U|'][1]
          and g.head_lbl.text() == 'Speed at the gauges', g.ylabel())
    check('the header tooltip says the file is the grid',
          'grid' in g.head_lbl.toolTip())
    # verification: a failure to build the curves read "This result has
    # no gauges." - it now says it could not draw them, and why
    real_traces = RG.traces

    def boom(*_a, **_k):
        raise ValueError('boom')
    RG.traces = boom
    try:
        g.redraw()
    finally:
        RG.traces = real_traces
    check('a failure to draw the curves says so (not "no gauges")',
          g.page() == 'empty'
          and g.hint.text() == 'Could not draw the gauges: boom',
          g.hint.text())
    g.redraw()
    check('and the next draw is back', g.page() == 'plot')
    r1 = ce.result('1d')
    p.add_result('1d', 1, r1)
    pump(40)
    radii = r1.gauges['radii']
    w13 = r1.meta['charge_kg'] ** (1.0 / 3.0)
    shown = {int(r[0][1:]): r for r in g.cells()}
    check('1D: one plot, no selector, Z = r / W^(1/3)',
          not g.selector_visible() and g.page() == 'plot'
          and all(shown[k + 1][1] == f'{r / w13:.2f}'
                  for k, r in enumerate(radii)),
          str([r[1] for r in g.cells()]))
    p.shutdown()
    p.deleteLater()
    pump(20)

    print('\nS5f: the plot keeps the stretch')
    rs = win.results
    win._show('results')
    win.resize(1100, 720)
    rs.add_result('three', 2, with_gauges(fake_2d()))
    rs.show_view('Gauges')
    pump(150)
    gg = rs.gauges
    check('1100 x 720: every row on screen and the plot taller than the '
          'table', gg.table.verticalScrollBar().maximum() == 0
          and gg.plot_w.height() > gg.table.height(),
          f'plot {gg.plot_w.height()} table {gg.table.height()}')
    rs.add_result('twelve', 2, with_gauges(fake_2d(), n=12))
    pump(150)
    check('twelve gauges scroll and the plot still wins',
          gg.table.verticalScrollBar().maximum() > 0
          and gg.plot_w.height() > gg.table.height(),
          f'plot {gg.plot_w.height()} table {gg.table.height()}')
    from test_ui_parity import clipped
    bad = clipped(win)
    check('1100 x 720: nothing clipped on Gauges', not bad, str(bad[:4]))
    while rs.entries():
        rs.sel.setCurrentIndex(0)
        rs.remove_current()
    rs.show_view('Field')
    pump(30)
    p9 = ResultsPanel(viewer_link=link, log_fn=lambda *_: None)
    p9.resize(900, 600)
    p9.show()
    p9.add_result('twelve', 2, with_gauges(fake_2d(), n=12))
    p9.show_view('Gauges')
    pump(150)
    g9 = p9.gauges
    check('the panel at 900 x 600: the plot taller than the table, which '
          'scrolls', g9.plot_w.height() > g9.table.height()
          and g9.table.verticalScrollBar().maximum() > 0,
          f'plot {g9.plot_w.height()} table {g9.table.height()}')
    # (verification: this read `maximum() >= 0`, which is always true)
    check('the headers wrap onto two lines there, and the table scrolls '
          'sideways rather than clip', g9.headers_wrapped()
          and g9.table.horizontalScrollBar().maximum() > 0
          and not clipped(p9),
          f'hbar {g9.table.horizontalScrollBar().maximum()} '
          f'{clipped(p9)[:3]}')
    p9.shutdown()
    p9.deleteLater()
    pump(20)


# ── S6 ───────────────────────────────────────────────────────────────────
def s6_field(link):
    import numpy as np
    import pyqtgraph as pg
    from matplotlib.collections import QuadMesh
    from PySide6.QtCore import QPointF
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton
    import test_char_exports as ce
    from test_gui_results_fields import fake_2d, fake_3d
    from test_ui_results import frames_on, with_gauges
    from blastlab.core.constants import ANIM_SCALE_LABELS, P_AIR
    from blastlab.models.meta import frames_of
    from blastlab.ui import dialogs
    from blastlab.ui import results_field as RF
    from blastlab.ui import results_panel as RP
    from blastlab.ui.exports import name_prefix, summary_rows
    from blastlab.ui.results_fields import field_options
    print('\nS6a: Field replaces Fields and Animation')
    log = []
    p = RP.ResultsPanel(viewer_link=link, log_fn=log.append)
    p.resize(1600, 1000)
    p.show()
    pump(40)
    fv = p.field_view
    check('VIEWS == (Field, Gauges, 3D) and the tab strip has three tabs',
          RP.VIEWS == ('Field', 'Gauges', '3D')
          and p.view_seg.values() == ['Field', 'Gauges', '3D']
          and p.view() == 'Field', str(p.view_seg.values()))
    p.show_view('Gauges')
    p.show_view('Animation')
    ok_anim = p.view() == 'Field'
    p.show_view('Gauges')
    p.show_view('Fields')
    check('show_view(Animation) and show_view(Fields) select Field',
          ok_anim and p.view() == 'Field'
          and p.stack.currentWidget() is fv)
    check('the engines\' own control rows are hidden (legacy state)',
          p.fields.controls.isHidden() and p.anim.controls.isHidden())
    check('Show mesh is a checkable button in the Field row, the same '
          'widget the engine and the export read',
          isinstance(p.fields.show_mesh, QPushButton)
          and p.fields.show_mesh.isCheckable()
          and fv.show_mesh is p.fields.show_mesh
          and fv.show_mesh.parent() is not p.fields.controls)

    print('\nS6b: the composed Field / Plane choices = field_options')
    r2 = ce.result('2d')
    fixtures = (('2D with frames', 2, r2), ('2D, no frames', 2, fake_2d()),
                ('3D', 3, fake_3d()), ('1D', 1, ce.result('1d')))
    for name, dim, res in fixtures:
        p.add_result(name, dim, res)
        pump(60)
        opts = field_options(res, dim)
        if dim == 1:
            check('1D: profiles only, the controls row hidden',
                  opts == ['profiles'] and p.fields.field() == 'profiles'
                  and fv.ctl.isHidden() and p.fields.page() == 'figure')
            # verification: at 1100 px the builder's one-shot layout put
            # the tick labels outside the canvas
            p.resize(1100, 720)
            pump(80)
            cv = p.fields.canvas._canvas
            cv.draw()
            fig = p.fields.canvas.figure
            r = cv.get_renderer()
            out = [t.get_text() for a in fig.axes
                   for t in a.get_yticklabels() + [a.yaxis.label]
                   if t.get_text() and t.get_visible()
                   and t.get_window_extent(renderer=r).x0 < -0.5]
            check('1D at 1100 px: every tick label and y label inside the '
                  'canvas', not out, ascii(out[:4]))
            # GUI-11 T19 (F17, D214): the short title on screen only
            from blastlab.models.meta import charge_label as m_charge
            from blastlab.output import plots as P
            c = m_charge(res.meta)
            want = f'1D spherical · {c.charge_kg} kg TNT · {c.eos}'
            got_t = fig.axes[0].get_title()
            check('1D: the on-screen title is the short form (F17)',
                  got_t == want, ascii(got_t))
            tb = fig.axes[0].title.get_window_extent(renderer=r)
            cw, ch_ = cv.get_width_height()
            check('1D at 1100 px: the title lies inside the canvas',
                  tb.x0 >= -0.5 and tb.x1 <= cw + 0.5 and tb.y1 <= ch_ + 0.5,
                  f'{tb.x0:.0f}..{tb.x1:.0f} in {cw}, top {tb.y1:.0f}/{ch_}')
            built = P.figure_results_1d(res.snapshots, c.eos, c.charge_kg,
                                        c.radius_m)
            check('the builder (every export) keeps its long title',
                  built.axes[0].get_title()
                  == f'1D Spherical Blast - {c.charge_kg} kg TNT - EOS: '
                     f'{c.eos}', ascii(built.axes[0].get_title()))
            # GUI-12 B3 (UX finding 2): the canvas says the export keeps
            # the full title, built from the builder's own string
            # GUI-13 B4 (UX #10): the hint moved from the canvas to the
            # figure Export buttons (the same text, built from the builder's
            # own string); the canvas has no tooltip
            png = p._export_btns['pngs']
            tip = png.toolTip()
            check('GUI-13 B4: the 1D PNG button\'s tooltip carries the '
                  'exported suptitle, the canvas has none',
                  tip.startswith('Exports use the full title: '
                                 + built.axes[0].get_title())
                  and '1D Spherical Blast' in tip
                  and p.fields.canvas.toolTip() == ''
                  and p._export_btns['report'].toolTip().startswith(
                      'Exports use the full title:'), ascii(tip))
            p.title_box.setText('QA title')
            pump(120)
            check('GUI-13 B4: with a user title the tooltip carries the '
                  'exported (titled) form',
                  P.titled(built.axes[0].get_title(), 'QA title')
                  in png.toolTip(), ascii(png.toolTip()))
            got_t = p.fields.canvas.figure.axes[0].get_title()
            check('the user\'s title line stays above the short one',
                  got_t == 'QA title\n' + want, ascii(got_t))
            p.title_box.setText('')
            pump(60)
            p.resize(1600, 1000)
            pump(40)
            continue
        got = []
        for base in fv.field_seg.values():
            fv.field_seg._btns[base].click()
            pump(10)
            planes = (RF.PLANES if dim == 3 and base != 'Isosurface'
                      else (None,))
            for plane in planes:
                if plane:
                    fv.plane_seg._btns[plane].click()
                    pump(10)
                got.append(p.fields.field())
        check(f'{name}: the choices give exactly field_options (set and '
              f'bijection)', sorted(set(got)) == sorted(opts)
              and len(got) == len(set(got)) == len(opts), str(got))
        fv.field_seg._btns[fv.field_seg.values()[0]].click()
        pump(10)
        check(f'GUI-13 B4: {name}: no export-title hint on the figure '
              'buttons',
              not p._export_btns['pngs'].toolTip().startswith(
                  'Exports use the full title:'),
              ascii(p._export_btns['pngs'].toolTip()))

    print('\nS6c: the time bar')
    ent = p.add_result('frames', 2, r2)
    pump(60)
    frames = frames_of(r2.meta)
    n = len(frames['pressures'])
    fms = [float(t) * 1e3 for t in frames['times']]
    tb = fv.timebar
    check('overpressure with frames: the recorded frames, max n-1',
          fv.mode() == 'frames' and fv.page() == 'replay'
          and tb.slider.maximum() == n - 1
          and tb.length_lbl.text() == f'{fms[-1]:.2f} ms · {n} frames',
          tb.length_lbl.text())
    calls = []
    real = p.anim.show_frame
    p.anim.show_frame = lambda k: (calls.append(k), real(k))[1]
    try:
        tb.slider.setValue(3)
        pump(10)
        tb.slider.setValue(5)
        pump(10)
        check('each move of the time bar draws the frame once (R5\'s rule)',
              calls == [3, 5] and p.anim.frame() == 5, str(calls))
    finally:
        p.anim.show_frame = real
    check('the time is the frame\'s', fv.time_text() == f'{fms[5]:.2f} ms',
          fv.time_text())
    fv.field_seg._btns['Density'].click()
    pump(30)
    labels = list(r2.snapshots)
    st = [RF.snapshot_ms(s) for s in labels]
    k_s = int(np.argmin([abs(t - fms[5]) for t in st]))
    check('Density: the snapshots, `… · N snapshots`, the nearest one to '
          'the frame\'s time', fv.mode() == 'snapshots'
          and fv.page() == 'map'
          and tb.length_lbl.text().endswith(f'· {len(labels)} snapshots')
          and p.fields.snap_sel.currentIndex() == k_s,
          f'{tb.length_lbl.text()} {p.fields.snap_sel.currentIndex()} '
          f'want {k_s}')
    tb.slider.setValue(len(labels) - 1)
    pump(20)
    check('the time bar steps the snapshots',
          p.fields.snapshot() == labels[-1])
    fv.field_seg._btns['Overpressure'].click()
    pump(30)
    k_f = int(np.argmin([abs(t - st[-1]) for t in fms]))
    check('back on overpressure: the frame nearest the snapshot\'s time',
          fv.mode() == 'frames' and p.anim.frame() == k_f
          and tb.slider.value() == k_f, f'{p.anim.frame()} want {k_f}')
    fv.start_play()
    p.anim._tick()
    pump(10)
    check('Play runs the replay; the time bar follows its ticks',
          fv.playing() and p.anim.playing()
          and tb.slider.value() == p.anim.frame()
          and tb.play_btn.toolTip() == 'Pause')
    fv.stop_play()
    check('and stops', not fv.playing() and tb.play_btn.toolTip() == 'Play')
    tb.speed.setCurrentIndex(RF.SPEED_SHOWN.index('2×'))
    check('the speed box drives the replay\'s speed',
          p.anim.speed_sel.currentText() == '2x')
    p.anim.speed_sel.setCurrentText('4x')
    check('and follows it', tb.speed.currentText() == '4×')
    p.anim.speed_sel.setCurrentText('1x')
    fv.field_seg._btns['Density'].click()
    pump(20)
    fv.start_play()
    k0 = p.fields.snap_sel.currentIndex()
    fv._snap_tick()
    pump(10)
    check('the snapshots play on the same tick and speed rules',
          fv._snap_timer.isActive()
          and fv._snap_timer.interval() == p.anim.timer.interval()
          and p.fields.snap_sel.currentIndex()
          == (k0 + p.anim.frame_step()) % len(labels))
    fv.stop_play()
    for base, why in (('Peak', 'whole'), ('Impulse', 'whole')):
        fv.field_seg._btns[base].click()
        pump(20)
        check(f'{base}: no time bar, and the caption says why',
              tb.isHidden() and fv.mode() is None
              and RF.NO_BAR[why] in fv.caption.text())
    fv.field_seg._btns['Overpressure'].click()
    pump(20)
    check('the controls: Play 40 px round, speed and This frame 32 px',
          tb.play_btn.height() == 40 and tb.play_btn.width() == 40
          and tb.speed.height() == 32 and tb.frame_btn.height() == 32,
          f'{tb.play_btn.size()} {tb.speed.height()} '
          f'{tb.frame_btn.height()}')

    print('\nS6d: the colour scale drives the export')
    fv.scale_seg._btns['manual'].click()
    pump(20)
    check('manual shows Min / Max with the field\'s unit (kPa)',
          not fv.manual_grp.isHidden() and fv.unit_lbl.text() == 'kPa')
    for box, text in ((fv.min_edit, '0'), (fv.max_edit, '50')):
        box.clear()
        QTest.keyClicks(box, text)
        QTest.keyClick(box, Qt.Key_Return)
    pump(20)
    want = {'show_mesh': p.fields.show_mesh.isChecked(), 'title_extra': None,
            'anim_scale': 'manual', 'anim_clim': (0.0, 50.0)}
    check('manual (0, 50) through the visible control: export_opts',
          p.export_opts() == want, str(p.export_opts()))
    check('and the replay uses it', p.anim.image.levels == (0.0, 50.0),
          str(p.anim.image.levels))
    p.anim.scale_sel.setCurrentText(ANIM_SCALE_LABELS['frame'])
    pump(20)
    check('the engine\'s selector moves the visible control (both ways)',
          fv.scale_seg.get() == 'each frame' and fv.manual_grp.isHidden())
    p.set_colour_scale('manual')
    pump(20)
    check('back to manual keeps the typed overpressure range',
          fv.min_edit.text() == '0' and fv.max_edit.text() == '50'
          and p.export_opts()['anim_clim'] == (0.0, 50.0))

    print('\nS6e: the snapshot maps\' scale')
    fk = p.add_result('flat', 2, fake_2d())
    pump(40)
    fv.field_seg._btns['Density'].click()
    pump(20)
    p.set_colour_scale('frame')
    pump(20)
    check('each frame: today\'s set_data levels (R3\'s (1.2, 2.2))',
          p.fields.image.levels == (1.2, 2.2), str(p.fields.image.levels))
    p.sel.setCurrentIndex(p.entries().index(ent))
    pump(40)
    fv.field_seg._btns['Density'].click()
    pump(20)
    p.set_colour_scale('run')
    pump(20)
    solid = r2.meta['solid']
    vals = [np.where(solid, np.nan, np.asarray(s['rho'], dtype=np.float64))
            for s in r2.snapshots.values()]
    lo = min(float(np.nanmin(v)) for v in vals)
    hi = max(float(np.nanmax(v)) for v in vals)
    check('whole run on density: (min, max) over the snapshots, solid '
          'cells out', p.fields.image.levels == (lo, hi)
          and p.fields.scale_used() == 'run',
          f'{p.fields.image.levels} want {(lo, hi)}')
    # the overpressure range typed in S6d is the export's
    clim_before = p.anim.clim()
    p.set_colour_scale('manual', (1.0, 3.0))
    pump(20)
    check('a manual density range: on the map, not in the export',
          p.fields.image.levels == (1.0, 3.0)
          and fv.unit_lbl.text() == 'kg/m³'
          and clim_before == (0.0, 50.0)
          and p.export_opts()['anim_clim'] == clim_before
          and p.anim.min_box.text() != '1', str(p.export_opts()))
    fv.field_seg._btns['Speed'].click()
    pump(20)
    speed_boxes = (fv.min_edit.text(), fv.max_edit.text())
    fv.field_seg._btns['Density'].click()
    pump(20)
    check('ranges are remembered per field',
          speed_boxes == ('', '') and fv.min_edit.text() == '1'
          and fv.manual_range('Density') == (1.0, 3.0)
          and fv.manual_range('Overpressure') == clim_before)

    print('\nS6f: the hover readout')
    img = p.fields.image
    xf, yf = img.xf, img.yf

    def centre(i, j):
        return p.fields.plot.vb.mapViewToScene(QPointF(
            (xf[i] + xf[i + 1]) / 2, (yf[j] + yf[j + 1]) / 2))
    fluid = np.argwhere(~solid)[len(np.argwhere(~solid)) // 2]
    i, j = int(fluid[0]), int(fluid[1])
    v = fv.hover_scene(centre(i, j))
    shown = img.shown[i, j]
    check('over a cell centre: the displayed cell\'s value, formatted',
          v == shown and fv.hover_text().split('\n')[1]
          == f'density {shown:.4g} kg/m³' and fv.hover_visible(),
          fv.hover_text())
    check('the axis names follow the page\'s labels (r, z)',
          fv.hover_text().startswith('r ') and ' · z ' in fv.hover_text())
    si, sj = (int(x) for x in np.argwhere(solid)[0])
    check('a solid cell reads solid', fv.hover_scene(centre(si, sj))
          == 'solid' and fv.hover_text().endswith('\nsolid'))
    out_pos = p.fields.plot.vb.mapViewToScene(QPointF(xf[-1] + 1.0,
                                                      yf[-1] + 1.0))
    check('outside the domain it hides',
          fv.hover_scene(out_pos) is None and not fv.hover_visible()
          and fv.hover_text() == '')
    # verification: the readout opened to the right and above whatever
    # the pointer was, so near the right edge it was cut off
    vbr = p.fields.plot.vb.sceneBoundingRect()
    nx, ny = img.shape
    inside = []
    for ci, cj in ((0, 0), (nx - 1, 0), (0, ny - 1), (nx - 1, ny - 1)):
        fv.hover_scene(centre(ci, cj))
        box = fv._hover['fields'].sceneBoundingRect()
        inside.append(vbr.contains(box))
    check('at each corner cell the readout opens inward, inside the map',
          all(inside), str(inside))
    # and along the middle row, where a rule by the view's midpoint put
    # it past the right edge of a narrow map (the real-platform shot)
    def sweep():
        box = p.fields.plot.vb.sceneBoundingRect()
        out, text_w = [], 0.0
        for ci in range(0, nx, max(1, nx // 25)):
            fv.hover_scene(centre(ci, ny // 2))
            item = fv._hover['fields']
            text_w = item.sceneBoundingRect().width()
            if not box.contains(item.sceneBoundingRect()):
                out.append(ci)
        return out, box.width(), text_w
    cut, w, tw = sweep()
    check('along the middle row the readout is never cut off', not cut,
          str(cut[:6]))
    for size in ((1100, 720), (900, 600)):
        p.resize(*size)
        pump(80)
        cut, w, tw = sweep()
        check(f'nor on the narrow map at {size[0]} x {size[1]} (it slides '
              f'to stay inside)', not cut and w > tw,
              f'cut at {cut[:6]}; map {w:.0f} px, readout {tw:.0f} px')
    p.resize(1600, 1000)
    pump(80)
    p.fields.plot.scene().sigMouseMoved.emit(centre(i, j))
    check('the pointer (the scene signal) drives it',
          fv.hover_visible() and fv.hover_text().endswith('kg/m³'))
    fv.field_seg._btns['Overpressure'].click()
    pump(20)
    aim = p.anim.image
    v = fv.hover_scene(p.anim.plot.vb.mapViewToScene(QPointF(
        (aim.xf[i] + aim.xf[i + 1]) / 2, (aim.yf[j] + aim.yf[j + 1]) / 2)),
        'anim')
    check('on the replay too, in kPa', v == aim.shown[i, j]
          and fv.hover_text().endswith(f'overpressure {v:.4g} kPa'),
          fv.hover_text())
    # UXR-11 / QA S4-a (D220, amends D111): the axisymmetric replay reads
    # r · z like its snapshot maps; This frame .png keeps the video's
    # own labels (plane_geometry)
    bottom = p.anim.plot.getAxis('bottom').labelText
    check('the axisymmetric replay\'s axis and readout read r · z',
          r2.meta.get('geometry') == 'axisymmetric'
          and bottom.startswith('r ')
          and p.fields.plot.getAxis('bottom').labelText.startswith('r ')
          and fv.hover_text().startswith('r ')
          and ' · z ' in fv.hover_text(), f'{bottom!r} {fv.hover_text()!r}')
    p.anim.set_show_mesh(not p.anim._show_mesh)
    p.anim.set_show_mesh(not p.anim._show_mesh)
    check('and still after the mesh overlay is redrawn',
          p.anim.plot.getAxis('bottom').labelText.startswith('r '),
          p.anim.plot.getAxis('bottom').labelText)
    from blastlab.ui.results_anim import plane_geometry
    check('the replay geometry (This frame .png) keeps its own x label',
          plane_geometry(r2.meta)['xlabel'] == 'x [m]')

    # UXR-15 (D221): the Impulse map reads kPa·ms on screen, as the
    # Gauges table does; 1 Pa·s = 1 kPa·ms, so the numbers are the same
    from blastlab.output import plots
    from blastlab.ui.results_fields import screen_unit, select_field
    fv.field_seg._btns['Impulse'].click()
    pump(20)

    def bar_text(image):
        for axis in ('right', 'left'):
            try:
                text = image.bar.getAxis(axis).labelText
            except Exception:
                text = ''
            if text:
                return text
        return ''
    bar = bar_text(p.fields.image)
    sel = select_field(r2, 2, p.fields.snapshot(), p.fields.field())
    check('the Impulse colour bar reads kPa·ms, not Pa·s',
          p.fields.field().startswith('net ovp impulse')
          and 'kPa·ms' in bar and 'Pa·s' not in bar, bar)
    check('its Min / Max caption and the hover unit too',
          fv.unit_lbl.text() == 'kPa·ms', fv.unit_lbl.text())
    check('the export\'s label (select_field, This frame .png) keeps '
          'Pa·s', sel['unit'] == plots.IMPULSE_LABEL
          and screen_unit(plots.IMPULSE_LABEL)
          == 'Net overpressure impulse [kPa·ms]', sel['unit'])
    fv.field_seg._btns['Overpressure'].click()
    pump(20)

    print('\nS6g: the arrival tick')
    rows = summary_rows(r2)
    g1 = p.selected_gauge()
    k1 = int(np.argmin([abs(t - rows[g1 - 1]['arrival_ms']) for t in fms]))
    check('the tick sits at the frame nearest the selected gauge\'s '
          'arrival', tb.slider.ticks() == [k1]
          and f'arrival at G{g1}.' in fv.caption.text(),
          f'{tb.slider.ticks()} want {k1}; {fv.caption.text()}')
    g2 = 2 if g1 == 1 else 1
    p.select_gauge(g2)
    k2 = int(np.argmin([abs(t - rows[g2 - 1]['arrival_ms']) for t in fms]))
    check('selecting another gauge in Gauges moves it',
          tb.slider.ticks() == [k2]
          and f'arrival at G{g2}.' in fv.caption.text(), str(k2))
    fv.field_seg._btns['Density'].click()
    pump(20)
    k3 = RF.nearest(st, rows[g2 - 1]['arrival_ms'])
    check('on the snapshots, at the nearest snapshot',
          tb.slider.ticks() == [k3])
    fv.field_seg._btns['Overpressure'].click()
    pump(20)
    flat = frames_on(fake_2d())
    flat.gauges = dict(times=np.linspace(0, 1e-3, 20), points=[(0.3, 0.3)],
                       pressures=[np.full(20, P_AIR)])
    p.add_result('no arrival', 2, flat)
    pump(40)
    check('no arrival (NaN): no tick, and the caption says nothing of it',
          fv.timebar.slider.ticks() == []
          and 'Cyan tick' not in fv.caption.text())

    print('\nS6h: This frame .png')
    p.sel.setCurrentIndex(p.entries().index(ent))
    pump(40)
    out = os.path.join(TMP, 'frame')
    os.makedirs(out, exist_ok=True)
    asked = []

    def save_file(title, filters='', parent=None, start='',
                  default_suffix=None):
        asked.append((title, start, default_suffix))
        return os.path.join(out, os.path.basename(start))
    real_save = dialogs.save_file
    dialogs.save_file = save_file
    try:
        p.set_colour_scale('manual', (0.0, 50.0))
        tb.slider.setValue(4)
        pump(20)
        target = fv.save_frame_png(threaded=False)
        fig = fv.last_frame_figure
        # one panel; matplotlib's colour bar is an axis of its own
        panels = [a for a in fig.axes if a.get_label() != '<colorbar>'
                  and any(isinstance(c, QuadMesh) for c in a.collections)]
        qm = [c for c in panels[0].collections
              if isinstance(c, QuadMesh)][0]
        want_name = (f'{name_prefix(r2)}field_overpressure_'
                     f'{fms[4]:.3f}ms.png')
        check('a frame: one PNG > 5 kB, one panel, named after the field '
              'and the time', os.path.getsize(target) > 5000
              and len(panels) == 1
              and os.path.basename(target) == want_name
              and asked[-1][0] == 'Save this frame'
              and asked[-1][2] == '.png', f'{target} {len(panels)}')
        check('manual: the QuadMesh clim is the range on screen',
              tuple(qm.get_clim()) == (0.0, 50.0)
              == tuple(p.anim.image.levels), str(qm.get_clim()))
        fv.field_seg._btns['Density'].click()
        pump(20)
        p.set_colour_scale('run')
        pump(20)
        target = fv.save_frame_png(threaded=False)
        qm = [c for a in fv.last_frame_figure.axes for c in a.collections
              if isinstance(c, QuadMesh)
              and a.get_label() != '<colorbar>'][0]
        check('a snapshot map, whole run: its on-screen range',
              os.path.getsize(target) > 5000
              and tuple(qm.get_clim()) == tuple(p.fields.image.levels)
              and 'field_density_' in os.path.basename(target),
              str(qm.get_clim()))
        before = len(os.listdir(out))
        p.set_colour_scale('frame')
        tb.slider.setValue(tb.slider.maximum())      # a new file name
        pump(20)
        target = fv.save_frame_png()          # threaded, the busy strip
        busy = tb.busy() and tb.frame_btn.isHidden()
        for _ in range(200):
            pump(20)
            if not tb.busy():
                break
        check('threaded: the busy strip while it writes, then the button',
              busy and not tb.busy() and not tb.frame_btn.isHidden()
              and os.path.exists(target) and len(os.listdir(out)) > before)
        dialogs.save_file = lambda *a, **k: ''
        check('a cancelled dialog writes nothing and shows no strip',
              fv.save_frame_png() == '' and not tb.busy())
    finally:
        dialogs.save_file = real_save

    print('\nS6i: F15 - one colour bar after a second 2D result')
    fv.field_seg._btns['Overpressure'].click()
    p.add_result('another', 2, fake_2d())
    pump(30)
    p.add_result('and another', 2, fake_2d())
    pump(30)
    fv.field_seg._btns['Density'].click()
    pump(30)
    bars = [it for it in p.fields.glw.scene().items()
            if isinstance(it, pg.ColorBarItem)]
    check('the Field map\'s scene holds exactly one colour bar (F15)',
          len(bars) == 1, str(len(bars)))
    p.shutdown()
    p.deleteLater()
    pump(20)
    del fk


def s3_placeholder(win):
    """GUI-11 T21 (QA S3-6, the text half; D215): Results ▸ 3D says what
    to do, from a subclass in results_panel.py; the shared host text and
    the Results centre's minimum width are unchanged."""
    from blastlab.ui.results_panel import ResultsView3DHost
    from blastlab.ui.view3d_host import View3DHost
    print('\nS3e: the Results 3D placeholder (GUI-11 T21)')
    rs = win.results
    win._show('results')
    win.resize(1100, 720)
    pump(150)
    host = rs.view3d
    want = ('Select a 3D result, then press\nOpen the 3D viewer in the\n'
            'Export column.')
    check('results.view3d is still a View3DHost (the Results subclass)',
          isinstance(host, View3DHost) and isinstance(host,
                                                      ResultsView3DHost))
    check('its placeholder is the new text', host._holder.text() == want,
          repr(host._holder.text()))
    check('the shared host text is unchanged',
          View3DHost.PLACEHOLDER.startswith('Run a 3D case'))
    fm = host._holder.fontMetrics()
    longest = max(fm.horizontalAdvance(s)
                  for s in View3DHost.PLACEHOLDER.split('\n'))
    new = max(fm.horizontalAdvance(s) for s in want.split('\n'))
    check('no line longer than the shared text\'s longest',
          new <= longest, f'{new} <= {longest} px')
    now = rs._centre.minimumSizeHint().width()
    host._holder.setText(View3DHost.PLACEHOLDER)
    pump(30)
    old = rs._centre.minimumSizeHint().width()
    host._holder.setText(want)
    pump(30)
    check('1100 x 720: the Results centre minimum width is unchanged',
          now == old, f'{now} vs {old} with the old text')
    win.resize(1280, 840)
    pump(60)


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
        s3_layout(win, link)
        s3_busy(link)
        s3_view3d_and_title(link)
        s3_placeholder(win)
        s5_gauges(win, link)
        s5g_dropped(link)
        s6_field(link)
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
