"""OUT-1 QA, PySide6 GUI, native flows, in a REAL window (no offscreen).

Items 1, 2, 3, 4, 6, 7, 8, 9, 11, 12 of the brief.
Run:  python -u docs/qa/2026-09-26-out-1/scripts/qt_pass.py [--only a,b]
"""
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_common as Q  # noqa: E402

Q.private_env()
ONLY = None
if '--only' in sys.argv:
    ONLY = set(sys.argv[sys.argv.index('--only') + 1].split(','))
PREFIX = 'qt'
if '--prefix' in sys.argv:
    PREFIX = sys.argv[sys.argv.index('--prefix') + 1]
Q.set_log(f'{PREFIX}_pass')
SHOTS = os.path.join(Q.OUT, 'shots')
os.makedirs(SHOTS, exist_ok=True)

from PySide6.QtCore import QPoint, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel, QLineEdit,  # noqa: E402
                               QMessageBox, QToolTip, QAbstractButton)

app = QApplication.instance() or QApplication(['blastlab-qa'])
from blastlab.core import settings as app_settings  # noqa: E402
from blastlab.ui import theme  # noqa: E402
theme.apply(app, app_settings.load().get('appearance', 'dark'))
from blastlab.ui import dialogs  # noqa: E402
from blastlab.ui.app import MainWindow  # noqa: E402

N = [0]
WIN = [None]
GAPS = []


def _name(tag):
    N[0] += 1
    return f'{PREFIX}_{N[0]:02d}_{tag}.png'


def shot(tag, widget=None):
    pump(0.3)
    name = _name(tag)
    (widget or WIN[0]).grab().save(os.path.join(SHOTS, name))
    Q.rec('shot', path=name)
    return name


def frame_shot(tag, widget):
    """PrintWindow of a top-level: the native frame and title too."""
    name = _name(tag)
    try:
        Q.grab_hwnd(int(widget.winId()), os.path.join(SHOTS, name))
    except Exception as exc:
        widget.grab().save(os.path.join(SHOTS, name))
        Q.rec('frame_shot_fallback', error=str(exc))
    Q.rec('shot', path=name)
    return name


def pump(seconds, until=None, tag=''):
    end = time.perf_counter() + seconds
    last = time.perf_counter()
    while True:
        app.processEvents()
        now = time.perf_counter()
        if now - last > 0.1:
            GAPS.append(dict(t=time.time(), gap_ms=round((now - last) * 1e3),
                             tag=tag))
        last = now
        if until is not None:
            r = until()
            if r:
                return r
        if now >= end:
            return None if until is not None else True
        time.sleep(0.01)


# ── the modal answering machine (QMessageBox is a Qt widget: a timer
#    that fires inside its nested loop reads it, grabs it and answers) ──
MODAL = dict(plan=[], seen=[])


def plan(*answers):
    MODAL['plan'] = list(answers)


def _modal_tick():
    w = QApplication.activeModalWidget()
    if not isinstance(w, QMessageBox) or getattr(w, '_qa_seen', False):
        return
    if not w.isVisible():
        return
    w._qa_seen = True
    QTimer.singleShot(600, lambda: _answer(w))


def _answer(w):
    ans = MODAL['plan'].pop(0) if MODAL['plan'] else None
    d = w.defaultButton()
    info = dict(title=w.windowTitle(), text=w.text(),
                buttons=[b.text() for b in w.buttons()],
                default=d.text() if d is not None else None,
                focus=(QApplication.focusWidget().text()
                       if isinstance(QApplication.focusWidget(),
                                     QAbstractButton) else None))
    info['shot'] = frame_shot(f'dialog_{ans or "auto"}', w)
    info['answer'] = ans or 'auto'
    MODAL['seen'].append(info)
    Q.rec('dialog', **info)
    if ans == 'enter':
        QTest.keyClick(w, Qt.Key_Return)
        return
    want = {'yes': QMessageBox.Yes, 'no': QMessageBox.No,
            'ok': QMessageBox.Ok}.get(ans)
    btn = w.button(want) if want is not None else None
    if btn is None:
        # unplanned: never Yes. No if there is one, else the escape button
        btn = w.button(QMessageBox.No) or w.escapeButton() or \
            w.button(QMessageBox.Ok)
    if btn is not None:
        btn.click()
    else:
        w.reject()


timer = QTimer()
timer.timeout.connect(_modal_tick)
timer.start(100)


def last_dialog():
    return MODAL['seen'][-1] if MODAL['seen'] else {}


def build():
    t0 = time.perf_counter()
    win = MainWindow()
    win.resize(1280, 840)
    win.show()
    win.raise_()
    win.activateWindow()
    WIN[0] = win
    pump(1.5)
    Q.rec('window', title=win.windowTitle(),
          size=[win.width(), win.height()],
          built_ms=round((time.perf_counter() - t0) * 1e3),
          solver=win.solver_mode.get())
    return win


def click(btn):
    QTest.mouseClick(btn, Qt.LeftButton)
    pump(0.2)


def cases():
    from blastlab.core.case import Case1D, Case2D
    return dict(
        N1D=Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.005,
                   gauge_radii=[0.5, 1.0], n_snapshots=3),
        N2D=Case2D(geometry='planar', Lx=2.4, Ly=1.6, cell_size_m=0.04,
                   charge=20.0, center=(0.6, 0.0),
                   obstacles=[(1.2, 1.6, 0.0, 0.6)],
                   bcs=dict(x_lo='reflect', x_hi='terminate',
                            y_lo='reflect', y_hi='terminate'),
                   gauges=[(0.3, 0.8), (1.4, 0.3)], n_snapshots=3,
                   record_frames=60),
        N2DAX=Case2D(geometry='axisymmetric', Lx=1.5, Ly=1.5,
                     cell_size_m=0.025, charge=2.0, center=(0.0, 0.75),
                     gauges=[(0.6, 0.75), (1.0, 0.75)], n_snapshots=3,
                     record_frames=0),
    )


def wait_run(win, timeout=600):
    t0 = time.time()
    pump(1.0)
    pump(timeout, until=lambda: not win.ctrl.running)
    pump(1.0)
    return time.time() - t0


def manifest(folder):
    try:
        with open(os.path.join(folder, 'manifest.json'),
                  encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        return {'_error': str(exc)}


def check_folder(folder, tag):
    files = Q.tree(folder)
    m = manifest(folder)
    listed = sorted(o.get('path') for o in m.get('outputs', []))
    on_disk = sorted(p for p, _s in files
                     if p not in ('manifest.json', '.blastlab-model'))
    empty = [p for p, s in files if s == 0]
    Q.rec('folder', tag=tag, folder=folder, files=files,
          manifest_keys=sorted(m.keys()), manifest=m,
          outputs_match=(listed == on_disk),
          only_listed=sorted(set(listed) - set(on_disk)),
          only_disk=sorted(set(on_disk) - set(listed)), empty_files=empty)
    return files, m


def _tip_widget():
    for w in QApplication.topLevelWidgets():
        if type(w).__name__ == 'QTipLabel' or \
                w.metaObject().className() == 'QTipLabel':
            if w.isVisible():
                return w
    return None


# ═══════════════════════════════════════════════════════════════════════
def item1_run_tab(win):
    rp = win.run_panel
    win._show('run')
    pump(0.5)
    Q.rec('item1', runs_dir_box=rp.runs_dir.text(),
          runs_placeholder=rp.runs_dir.placeholderText(),
          runs_tooltip=rp.runs_dir.toolTip(),
          browse_text=rp.runs_browse.text(),
          browse_tooltip=rp.runs_browse.toolTip(),
          model_box=rp.run_name.text(),
          model_placeholder=rp.run_name.placeholderText(),
          model_tooltip=rp.run_name.toolTip())
    shot('run_tab_start')
    frame_shot('run_tab_start_frame', win)
    chain, w = [], rp.runs_dir
    for _ in range(6):
        chain.append('runs_dir' if w is rp.runs_dir else
                     'browse' if w is rp.runs_browse else
                     'run_name' if w is rp.run_name else
                     f'{type(w).__name__}:{getattr(w, "text", lambda: "")()}')
        w = w.nextInFocusChain()
        while not (w.focusPolicy() & Qt.TabFocus) or not w.isVisible():
            w = w.nextInFocusChain()
    Q.rec('item1_focus_chain', chain=chain)
    rp.runs_dir.setFocus(Qt.TabFocusReason)
    pump(0.2)
    seen = []
    for _ in range(4):
        fw = QApplication.focusWidget()
        seen.append(('runs_dir' if fw is rp.runs_dir else
                     'browse' if fw is rp.runs_browse else
                     'run_name' if fw is rp.run_name else
                     f'{type(fw).__name__}:{getattr(fw, "text", lambda: "")()}'
                     if fw is not None else None))
        QTest.keyClick(fw or win, Qt.Key_Tab)
        pump(0.15)
    Q.rec('item1_tab_keys', focus_sequence=seen,
          active=win.isActiveWindow())
    for name, w in (('runs_dir', rp.runs_dir), ('model', rp.run_name),
                    ('browse', rp.runs_browse)):
        pos = w.mapToGlobal(QPoint(w.width() // 2, w.height() // 2))
        QToolTip.showText(pos, w.toolTip(), w)
        pump(0.8)
        tip = _tip_widget()
        if tip is not None:
            shot(f'tooltip_{name}', tip)
        else:
            Q.rec('tooltip_missing', name=name, text=w.toolTip())
        QToolTip.hideText()
        pump(0.3)


def item2_refusals(win):
    C = cases()
    win.setup.set_case(C['N1D'])
    pump(0.8)
    win._show('run')
    rp = win.run_panel
    home = os.path.expanduser('~')
    foreign = os.path.join(Q.RUNS, 'FOREIGN')
    os.makedirs(foreign, exist_ok=True)
    with open(os.path.join(foreign, 'notes.txt'), 'w') as f:
        f.write('not blastlab\n')
    empty = os.path.join(Q.RUNS, 'EMPTYDIR')
    os.makedirs(empty, exist_ok=True)
    before = sorted(os.listdir(Q.RUNS))
    home_before = sorted(os.listdir(home))
    trials = [
        ('empty_runs_folder', '', 'R2_EMPTY', 'ok'),
        ('missing_runs_folder', os.path.join(Q.RUNS, 'no_such_dir'),
         'R2_MISSING', 'ok'),
        ('bad_name_colon', Q.RUNS, 'bad:name', 'ok'),
        ('bad_name_CON', Q.RUNS, 'CON', 'ok'),
        ('bad_name_trailing_dot', Q.RUNS, 'model.', 'ok'),
        ('bad_name_empty', Q.RUNS, '', 'ok'),
        ('bad_name_101', Q.RUNS, 'x' * 101, 'ok'),
        ('bad_name_dotdot', Q.RUNS, '..', 'ok'),
        ('runs_is_desktop', os.path.join(home, 'Desktop'), 'R2_DESK', 'ok'),
        ('model_is_desktop', home, 'Desktop', 'ok'),
        ('model_holds_desktop', os.path.dirname(home),
         os.path.basename(home), 'ok'),
        ('foreign_folder', Q.RUNS, 'FOREIGN', 'ok'),
        ('foreign_folder_case', Q.RUNS, 'foreign', 'ok'),
        # an empty existing folder is asked about; answer No
        ('empty_existing_folder', Q.RUNS, 'EMPTYDIR', 'no'),
    ]
    for tag, runs, model, ans in trials:
        rp.set_runs_dir(runs)
        rp.run_name.setText(model)
        pump(0.2)
        n0 = len(MODAL['seen'])
        plan(ans)
        click(rp.run_btn)
        pump(3, until=lambda: len(MODAL['seen']) > n0)
        pump(0.5)
        d = last_dialog() if len(MODAL['seen']) > n0 else {}
        Q.rec('item2', tag=tag, runs=runs, model=model[:40],
              dialog_title=d.get('title'), dialog_text=d.get('text'),
              buttons=d.get('buttons'), default=d.get('default'),
              shot=d.get('shot'), worker_running=win.ctrl.running)
        if win.ctrl.running:
            win.ctrl.stop()
            wait_run(win, 60)
    Q.rec('item2_after',
          runs_listing_same=sorted(os.listdir(Q.RUNS)) == before,
          runs_listing=sorted(os.listdir(Q.RUNS)),
          home_listing_same=sorted(os.listdir(home)) == home_before,
          foreign_intact=os.listdir(foreign),
          emptydir_intact=os.listdir(empty))
    rp.set_runs_dir(Q.RUNS)


def item3_overwrite_and_1d(win):
    from blastlab.services import model_folder
    C = cases()
    win.setup.set_case(C['N1D'])
    pump(0.8)
    win._show('run')
    rp = win.run_panel
    rp.set_runs_dir(Q.RUNS)
    rp.run_name.setText('QA_1D')
    folder = os.path.join(Q.RUNS, 'QA_1D')
    if not os.path.isdir(folder):
        model_folder.prepare(Q.RUNS, 'QA_1D', confirm=lambda t: True)
    old = os.path.join(folder, 'old_run.txt')
    with open(old, 'w', encoding='utf-8') as f:
        f.write('the previous run\n')
    snap = {p: os.stat(os.path.join(folder, p)).st_mtime_ns
            for p in os.listdir(folder)}
    # 1) Enter on the dialog = the default button
    n0 = len(MODAL['seen'])
    plan('enter')
    click(rp.run_btn)
    pump(3, until=lambda: len(MODAL['seen']) > n0)
    pump(0.8)
    after = {p: os.stat(os.path.join(folder, p)).st_mtime_ns
             for p in os.listdir(folder)}
    Q.rec('item3_enter', dialog=last_dialog(),
          folder_untouched=(after == snap), run_started=win.ctrl.running)
    if win.ctrl.running:
        wait_run(win)
    # 2) explicit No
    n0 = len(MODAL['seen'])
    plan('no')
    click(rp.run_btn)
    pump(3, until=lambda: len(MODAL['seen']) > n0)
    pump(0.5)
    after = {p: os.stat(os.path.join(folder, p)).st_mtime_ns
             for p in os.listdir(folder)}
    Q.rec('item3_no', dialog=last_dialog(), folder_untouched=(after == snap),
          run_started=win.ctrl.running)
    # 3) Yes - the old file goes, the native 1D run starts (item 4)
    n0 = len(MODAL['seen'])
    plan('yes')
    t0 = time.time()
    click(rp.run_btn)
    pump(3, until=lambda: len(MODAL['seen']) > n0)
    pump(0.5)
    Q.rec('item3_yes', dialog=last_dialog(),
          old_file_gone=not os.path.exists(old),
          run_started=win.ctrl.running)
    shot('1d_running')
    wait_run(win)
    Q.rec('item4_1d_done', seconds=round(time.time() - t0, 1),
          log_tail=rp.log_text()[-600:])
    shot('1d_done')
    check_folder(folder, '1D')


def item4_2d(win, name='QA_2D', key='N2D'):
    C = cases()
    win.setup.set_case(C[key])
    pump(0.8)
    win._show('run')
    rp = win.run_panel
    rp.set_runs_dir(Q.RUNS)
    rp.run_name.setText(name)
    folder = os.path.join(Q.RUNS, name)
    plan('yes')
    click(rp.run_btn)
    pump(2)
    shot(f'{name}_running')
    wait_run(win)
    shot(f'{name}_done')
    check_folder(folder, name)
    return folder


def item11_numbers(win, folder, dim=2):
    """Results tab gauge table vs gauges_<d>d_summary.csv vs the TSV."""
    import numpy as np
    win._show('results')
    res = win.results
    res.show_view('Gauges')
    pump(1.0)
    ent = res.current()
    rows = res.gauges.rows()
    headers = [res.gauges.table.horizontalHeaderItem(i).text()
               for i in range(res.gauges.table.columnCount())]
    shot(f'results_gauges_{os.path.basename(folder)}')
    csv_path = os.path.join(folder, 'gauges', f'gauges_{dim}d_summary.csv')
    with open(csv_path, encoding='utf-8') as f:
        csv_rows = list(csv.reader(f))
    tsv_path = os.path.join(folder, 'gauges', f'gauges_{dim}d.txt')
    with open(tsv_path, encoding='utf-8') as f:
        head = [next(f) for _ in range(12)]
    from blastlab.services.exports import summary_rows
    core = summary_rows(ent.result)
    Q.rec('item11', label=ent.label, headers=headers, table=rows,
          csv=csv_rows, tsv_head=head, core=core)
    try:
        data = np.genfromtxt(tsv_path, comments='#', invalid_raise=False)
        Q.rec('item11_tsv', shape=list(data.shape),
              col_max=[float(v) for v in np.nanmax(data, axis=0)],
              col_min=[float(v) for v in np.nanmin(data, axis=0)])
    except Exception as exc:
        Q.rec('item11_tsv', error=str(exc))


def item9_exports(win, folder):
    """Results-tab export dialogs open in the model folder."""
    real_save, real_pick = dialogs.save_file, dialogs.pick_dir
    calls = []

    def watch(title):
        w = Q.NativeDialogWatcher(
            os.path.join(SHOTS, _name(f'export_{title.replace(" ", "_")}')),
            lambda info: ('close',), timeout=20, title_has=title)
        w.start()
        return w

    def save_file(title, filters='All files (*.*)', parent=None, start='',
                  default_suffix=None):
        calls.append(dict(fn='save_file', title=title, start=start))
        w = watch(title)
        out = real_save(title, filters, parent, start, default_suffix)
        w.done.wait(5)
        calls[-1].update(native=w.info, returned=out)
        return out

    def pick_dir(title, parent=None, start=''):
        calls.append(dict(fn='pick_dir', title=title, start=start))
        w = watch(title)
        out = real_pick(title, parent, start)
        w.done.wait(5)
        calls[-1].update(native=w.info, returned=out)
        return out
    dialogs.save_file, dialogs.pick_dir = save_file, pick_dir
    try:
        win._show('results')
        pump(0.5)
        for kind in ('summary', 'report', 'pngs'):
            if win.results.export_enabled(kind):
                win.results.export(kind, threaded=False)
                pump(0.5)
    finally:
        dialogs.save_file, dialogs.pick_dir = real_save, real_pick
    for c in calls:
        Q.rec('item9', folder=folder, **c)


def item6_outputs(win):
    from blastlab.ui.setup_spec import HIDDEN_ROWS
    win._show('setup')
    pump(0.5)
    for dim in (1, 2, 3, 0):
        win.setup.set_dim(dim)
        pump(0.8)
        form = win.setup.forms[dim]
        info = dict(dim=dim, cards=list(form.cards.keys()),
                    outputs_card=form.card_visible('Outputs'))
        for n in HIDDEN_ROWS + ('anim_format', 'report_file', 'name'):
            if n in getattr(form, 'widgets', {}):
                info[n] = form.row_visible(n)
            else:
                info[n] = 'absent'
        info['trigger_card'] = form.card_visible('Trigger gauge')
        if 'Outputs' in form.cards and form.card_visible('Outputs'):
            card = form.cards['Outputs']
            info['outputs_labels'] = [
                lb.text() for lb in card.findChildren(QLabel)
                if lb.isVisible() and lb.text()]
            win.setup._scroll.ensureWidgetVisible(card)
            pump(0.4)
            info['shot'] = shot(f'setup_outputs_{dim}d')
            shot(f'setup_outputs_{dim}d_card', card)
        if 'Trigger gauge' in form.cards:
            card = form.cards['Trigger gauge']
            info['trigger_labels'] = [
                lb.text() for lb in card.findChildren(QLabel)
                if lb.isVisible() and lb.text()]
            shot(f'setup_trigger_{dim}d_card', card)
        if dim == 1:
            win.setup.scroll_form(1.0)
            info['shot'] = shot('setup_1d_bottom')
        Q.rec('item6', **info)
    win.setup.set_dim(2)
    pump(0.5)


def _chain_forms(win, model):
    from blastlab.core.case import Case1D, Case2D, Case3D
    ch = win.chain
    win.run_panel.set_runs_dir(Q.RUNS)
    win.run_panel.run_name.setText(model)
    ch.set_stage_case(1, Case1D(radius_m=0.6, charge_kg=0.5,
                                cell_size_m=0.004, n_snapshots=1,
                                gauge_radii=[], gauge_file=None))
    ch.set_stage_case(2, Case2D(geometry='axisymmetric', Lx=1.0, Ly=1.6,
                                cell_size_m=0.03, charge=0.5,
                                center=(0.0, 0.8), n_snapshots=1,
                                gauges=[(0.6, 0.8)], record_frames=0))
    ch.set_stage_case(3, Case3D(Lx=1.2, Ly=1.2, Lz=1.2, cell_size_m=0.08,
                                charge=0.5, center=(0.6, 0.6, 0.6),
                                n_snapshots=1, gauges=[],
                                gauge_file=None, anim_file=None,
                                record_frames=0))
    for d in (1, 2, 3):
        ch.use[d].setChecked(True)
    pump(0.5)
    return ch


def item7_chain(win, runs=1, three=False, tag='', stay_on_chain=False):
    ch = win.chain
    win._show('chain')
    pump(0.6)
    if not tag:
        hints = [lb.text() for lb in ch.findChildren(QLabel)
                 if 'model folder' in lb.text()]
        ws = [t for t in (lb.text() for lb in ch.findChildren(QLabel))
              if 'orkspace' in t]
        ws_boxes = [e.placeholderText() for e in ch.findChildren(QLineEdit)
                    if e.isVisible() and 'orkspace' in
                    (e.placeholderText() + e.toolTip())]
        Q.rec('item7_panel', hint=hints, workspace_labels=ws,
              workspace_boxes=ws_boxes)
        shot('chain_tab')
        _chain_forms(win, 'QA_CHAIN')
        win.run_panel.run_name.setText('')
        n0 = len(MODAL['seen'])
        plan('ok')
        click(ch.run_btn)
        pump(3, until=lambda: len(MODAL['seen']) > n0)
        pump(0.5)
        Q.rec('item7_refusal', dialog=last_dialog(),
              status=ch.status.text(),
              folder_created=os.path.isdir(os.path.join(Q.RUNS, 'QA_CHAIN')))
        shot('chain_refused')
        win.run_panel.run_name.setText('QA_CHAIN')
        win.run_panel.set_runs_dir('')
        n0 = len(MODAL['seen'])
        plan('ok')
        click(ch.run_btn)
        pump(3, until=lambda: len(MODAL['seen']) > n0)
        Q.rec('item7_refusal_runs', dialog=last_dialog())
        win.run_panel.set_runs_dir(Q.RUNS)
    for k in range(runs):
        model = f'QA_CHAIN{tag}{k}' if (tag or k) else 'QA_CHAIN'
        _chain_forms(win, model)
        if not three:
            ch.use[3].setChecked(False)
        pump(0.4)
        win._show('chain')
        pump(0.3)
        if k == 0 and not tag:
            shot('chain_ready')
        folder = os.path.join(Q.RUNS, model)
        GAPS.clear()
        plan('yes')
        t_click = time.time()
        click(ch.run_btn)
        switched = pump(10, until=lambda: win._stack.currentWidget()
                        is win.run_panel)
        t_run_tab = time.time()
        if stay_on_chain:
            win._show('chain')
        marks, tab_at_mark = {}, {}
        t_end = time.time() + 900
        while time.time() < t_end:
            pump(0.05, tag='chain')
            log = win.run_panel.log_text()
            for s in ('=== Stage 1D ===', '=== Stage 2D ===',
                      '=== Stage 3D ==='):
                if s in log and s not in marks:
                    marks[s] = time.time()
                    cur = win._stack.currentWidget()
                    tab_at_mark[s] = [kk for kk, v in win._panels.items()
                                      if v is cur]
                    if s != '=== Stage 1D ===' and k == 0:
                        shot(f'chain{tag}_{s[10:12]}_started')
            if not win.ctrl.running and time.time() - t_click > 3:
                break
        pump(1.0, tag='chain-after')
        big = [g for g in GAPS if g['gap_ms'] > 250]
        rel = [dict(at_s=round(g['t'] - t_click, 2), gap_ms=g['gap_ms'],
                    tag=g['tag']) for g in big]
        Q.rec('item12', model=model, three=three,
              stay_on_chain=stay_on_chain,
              click_to_run_tab_s=round(t_run_tab - t_click, 2),
              switched=bool(switched),
              stage_marks={k2: round(v - t_click, 2)
                           for k2, v in marks.items()},
              tab_at_mark=tab_at_mark,
              gaps_over_250ms=rel,
              max_gap_ms=max([g['gap_ms'] for g in GAPS] or [0]),
              total_s=round(time.time() - t_click, 1))
        if k == 0 and not tag:
            shot('chain_done_run_tab')
        top = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
        Q.rec('item7_folder', model=model, top=top, tree=Q.tree(folder),
              root_manifest=manifest(folder),
              stage2_case=_model_json(folder, '2d'),
              stage1_case=_model_json(folder, '1d'))


def _model_json(folder, stage):
    try:
        with open(os.path.join(folder, stage, 'MODEL.json'),
                  encoding='utf-8') as f:
            d = json.load(f)
        return {k: d.get(k) for k in ('init_mode', 'profile_file_in',
                                      'profile_file', 'gauge_file')}
    except (OSError, ValueError) as exc:
        return str(exc)


def item8_hd13(win):
    from blastlab.core import assessment
    win._show('setup')
    win.setup.set_dim(0)
    pump(0.6)
    win.setup.forms[0].set_case(assessment.DeflagrationCase(
        name='QA HD13', charge_kg=5.0, volume_m3=1.0, vent_area_m2=0.02,
        scenario_kind='flame_spread', n_cohorts=4, spread_time=4.0,
        t_end=5.0, n_out=200))
    pump(0.8)
    shot('hd13_setup')
    rp = win.run_panel
    rp.set_runs_dir(Q.RUNS)
    rp.run_name.setText('QA_HD13')
    folder = os.path.join(Q.RUNS, 'QA_HD13')
    win._show('run')
    plan('yes')
    t0 = time.time()
    click(rp.run_btn)
    pump(1.0)
    busy = win._hd13_busy
    shot('hd13_running')
    if busy:
        # the Chain tab during the assessment (its button is not greyed
        # by an HD 1.3 run - the controller is idle)
        _chain_forms(win, 'QA_CHAIN_DURING_HD13')
        win.chain.use[3].setChecked(False)
        win._show('chain')
        pump(0.3)
        n0 = len(MODAL['seen'])
        plan('ok')
        btn_enabled = win.chain.run_btn.isEnabled()
        click(win.chain.run_btn)
        pump(3, until=lambda: len(MODAL['seen']) > n0)
        Q.rec('item8_chain_during', run_btn_enabled=btn_enabled,
              dialog=last_dialog() if len(MODAL['seen']) > n0 else None,
              folder_created=os.path.isdir(
                  os.path.join(Q.RUNS, 'QA_CHAIN_DURING_HD13')),
              still_busy=win._hd13_busy)
        # a resume during the assessment: the run browser's callback with
        # a path that does not load stops earlier, so the check is on the
        # gate itself (item 8 in qt_foam.py does it with a real run)
        n0 = len(MODAL['seen'])
        plan('ok')
        tgt = win._model_target('Resume')
        pump(2, until=lambda: len(MODAL['seen']) > n0)
        Q.rec('item8_resume_gate_during', returned=str(tgt),
              dialog=last_dialog() if len(MODAL['seen']) > n0 else None)
        rp.run_name.setText('QA_HD13')
        win._show('run')
    pump(900, until=lambda: not win._hd13_busy)
    pump(1.0)
    Q.rec('item8_done', seconds=round(time.time() - t0, 1), busy_seen=busy,
          status=win._status.text(), log_tail=rp.log_text()[-900:])
    shot('hd13_done')
    check_folder(folder, 'HD13')
    try:
        Q.rec('item8_loads', loads=os.listdir(os.path.join(folder,
                                                           'hd13_loads')))
    except OSError as exc:
        Q.rec('item8_loads', error=str(exc))
    win.setup.set_dim(2)
    pump(0.4)


def item1_persist(win):
    rp = win.run_panel
    win._show('run')
    pump(0.3)
    rp.runs_dir.setFocus()
    rp.runs_dir.selectAll()
    QTest.keyClicks(rp.runs_dir, Q.RUNS)
    QTest.keyClick(rp.runs_dir, Qt.Key_Return)
    rp.run_name.setText('PERSIST_MODEL')
    pump(0.3)
    with open(Q.SETTINGS, encoding='utf-8') as f:
        on_disk = json.load(f).get('runs_dir')
    win.close()
    pump(1.0)
    with open(Q.SETTINGS, encoding='utf-8') as f:
        after_close = json.load(f)
    win2 = build()
    win2._show('run')
    pump(0.5)
    Q.rec('item1_persist', typed=Q.RUNS, settings_after_enter=on_disk,
          settings_after_close=after_close.get('runs_dir'),
          auto_cleanup=after_close.get('auto_cleanup'),
          reopened_runs_box=win2.run_panel.runs_dir.text(),
          reopened_model_box=win2.run_panel.run_name.text())
    shot('run_tab_reopened')
    return win2


def resize_shots(win):
    win._show('run')
    for w, h in ((900, 600), (1600, 1000)):
        win.resize(w, h)
        pump(0.8)
        Q.rec('resize', asked=[w, h], got=[win.width(), win.height()])
        shot(f'run_tab_{w}x{h}')
    win.resize(1280, 840)
    pump(0.5)


def main():
    win = build()
    steps = [('1', lambda: item1_run_tab(win)),
             ('2', lambda: item2_refusals(win)),
             ('3', lambda: item3_overwrite_and_1d(win)),
             ('4', lambda: item4_2d(win)),
             ('11', lambda: item11_numbers(win, os.path.join(Q.RUNS,
                                                             'QA_2D'))),
             ('9', lambda: item9_exports(win, os.path.join(Q.RUNS,
                                                           'QA_2D'))),
             ('4ax', lambda: item4_2d(win, 'QA_2DAX', 'N2DAX')),
             ('6', lambda: item6_outputs(win)),
             ('7', lambda: item7_chain(win)),
             ('12', lambda: item7_chain(win, runs=2, tag='T')),
             ('12c', lambda: item7_chain(win, runs=1, tag='C',
                                         stay_on_chain=True)),
             ('12b', lambda: item7_chain(win, runs=1, three=True, tag='3S')),
             ('8', lambda: item8_hd13(win)),
             ('R', lambda: resize_shots(win))]
    for key, fn in steps:
        if ONLY and key not in ONLY:
            continue
        Q.rec('step', key=key)
        try:
            fn()
        except Exception:
            import traceback
            Q.rec('step_error', key=key, tb=traceback.format_exc())
    win2 = item1_persist(win) if (not ONLY or 'P' in ONLY) else win
    t0 = time.time()
    win2.close()
    pump(1.0)
    Q.rec('closed', seconds=round(time.time() - t0, 2),
          dialogs_total=len(MODAL['seen']))
    app.quit()


if __name__ == '__main__':
    main()
    os._exit(0)
