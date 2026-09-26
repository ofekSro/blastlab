"""OUT-1 QA, Tkinter GUI (python -m blastlab --tk), in a REAL window.

Tk messageboxes and file dialogs are native Win32 dialogs: a watcher
thread (qa_common.NativeDialogWatcher) finds them in this process, grabs
them with PrintWindow, reads their text / default button and answers.

Run:  python -u docs/qa/2026-09-26-out-1/scripts/tk_pass.py [--only a,b]
      [--resume <run name in /root/blastlab_runs>]
"""
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
RESUME = None
if '--resume' in sys.argv:
    RESUME = sys.argv[sys.argv.index('--resume') + 1]
LOGNAME = 'tk_resume' if RESUME else 'tk_pass'
Q.set_log(LOGNAME)
SHOTS = os.path.join(Q.OUT, 'shots')
PREFIX = 'tkr' if RESUME else 'tk'

import tkinter as tk  # noqa: E402
import customtkinter as ctk  # noqa: E402
from blastlab.gui import app as gapp  # noqa: E402
from blastlab.gui import results_panel as grp  # noqa: E402

N = [0]
ROOT = [None]
APP = [None]
DIALOGS = []


def _name(tag):
    N[0] += 1
    return f'{PREFIX}_{N[0]:02d}_{tag}.png'


def pump(seconds, until=None):
    end = time.time() + seconds
    root = ROOT[0]
    while True:
        try:
            root.update()
        except tk.TclError:
            return None
        if until is not None:
            r = until()
            if r:
                return r
        if time.time() >= end:
            return None if until is not None else True
        time.sleep(0.01)


def shot(tag):
    pump(0.4)
    root = ROOT[0]
    name = _name(tag)
    try:
        root.lift()
        Q.grab_hwnd(int(root.wm_frame(), 16), os.path.join(SHOTS, name))
    except Exception as exc:
        Q.rec('shot_error', name=name, error=str(exc))
    Q.rec('shot', path=name)
    return name


def expect_dialog(answer, title_has=None, timeout=30):
    """Start a watcher BEFORE the action that opens a native dialog."""
    tag = {'button': answer[1] if answer[0] == 'button' else ''}.get(
        answer[0], answer[0])
    w = Q.NativeDialogWatcher(os.path.join(SHOTS, _name(f'dialog_{tag}')),
                              lambda info: answer, timeout=timeout,
                              title_has=title_has)
    w.start()
    return w


def settle(w, secs=5):
    """Wait for the watcher, pumping Tk so the dialog closes cleanly."""
    pump(secs, until=lambda: w.done.is_set())
    pump(0.6)
    info = dict(w.info or {})
    DIALOGS.append(info)
    Q.rec('dialog', **info)
    return info


def build():
    root = ctk.CTk()
    t0 = time.time()
    app = gapp.App(root)
    ROOT[0], APP[0] = root, app
    root.geometry('1280x840+60+40')
    pump(2.0)
    Q.rec('window', title=root.title(), size=[root.winfo_width(),
                                               root.winfo_height()],
          built_s=round(time.time() - t0, 2), solver=app.solver_mode.get())
    return app


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
                   record_frames=60))


def running(app):
    return app._running()


def wait_run(app, timeout=900):
    t0 = time.time()
    pump(1.0)
    pump(timeout, until=lambda: not running(app))
    pump(1.0)
    return time.time() - t0


def log_text(app):
    try:
        return app.run_panel.log.get('1.0', 'end')
    except Exception:
        return ''


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
    Q.rec('folder', tag=tag, folder=folder, files=files,
          manifest_keys=sorted(m.keys()), manifest=m,
          outputs_match=(listed == on_disk),
          only_listed=sorted(set(listed) - set(on_disk)),
          only_disk=sorted(set(on_disk) - set(listed)),
          empty_files=[p for p, s in files if s == 0])
    return files, m


def labels_under(w, mapped_only=False):
    out = []

    def walk(x):
        for ch in x.winfo_children():
            try:
                if isinstance(ch, ctk.CTkLabel):
                    t = ch.cget('text')
                    if t and (not mapped_only or ch.winfo_ismapped()):
                        out.append(str(t))
            except Exception:
                pass
            walk(ch)
    walk(w)
    return out


# ═══════════════════════════════════════════════════════════════════════
def item1(app):
    rp = app.run_panel
    app._show('run')
    pump(0.6)
    tips = {k: getattr(getattr(rp, k), '_blastlab_tip', None)
            for k in ('_runs_entry', '_runs_browse', '_name_entry')}
    Q.rec('item1', runs_dir_box=rp.runs_dir.get(),
          model_box=rp.run_name.get(),
          browse_text=rp._runs_browse.cget('text'),
          tooltips={k: (t.text if t else None) for k, t in tips.items()})
    shot('run_tab_start')
    # tab order from the Runs folder entry's inner tk.Entry
    w = rp._runs_entry._entry
    seq = []
    for _ in range(5):
        owner = ('runs_dir' if w is rp._runs_entry._entry else
                 'run_name' if w is rp._name_entry._entry else
                 f'{w.winfo_class()}:{str(w)[-40:]}')
        seq.append(owner)
        w = w.tk_focusNext()
        if w is None:
            break
    Q.rec('item1_focus_chain', chain=seq)
    for k, t in tips.items():
        if t is None:
            continue
        t._show()
        pump(0.6)
        try:
            h = int(t._tip.wm_frame(), 16)
            name = _name(f'tooltip{k}')
            Q.grab_hwnd(h, os.path.join(SHOTS, name))
            Q.rec('shot', path=name)
        except Exception as exc:
            Q.rec('tooltip_shot_error', key=k, error=str(exc))
        t._hide()
        pump(0.2)


def item2(app):
    C = cases()
    app.setup.set_case(C['N1D'])
    pump(0.8)
    app._show('run')
    rp = app.run_panel
    home = os.path.expanduser('~')
    foreign = os.path.join(Q.RUNS, 'TK_FOREIGN')
    os.makedirs(foreign, exist_ok=True)
    with open(os.path.join(foreign, 'notes.txt'), 'w') as f:
        f.write('not blastlab\n')
    before = sorted(os.listdir(Q.RUNS))
    trials = [('empty_runs_folder', '', 'TK_R2', ('button', 'OK')),
              ('missing_runs_folder', os.path.join(Q.RUNS, 'nope'), 'TK_R2',
               ('button', 'OK')),
              ('bad_name', Q.RUNS, 'a/b', ('button', 'OK')),
              ('runs_is_desktop', os.path.join(home, 'Desktop'), 'TK_R2',
               ('button', 'OK')),
              ('model_is_desktop', home, 'Desktop', ('button', 'OK')),
              ('foreign_folder', Q.RUNS, 'TK_FOREIGN', ('button', 'OK'))]
    for tag, runs, model, ans in trials:
        rp.set_runs_dir(runs)
        rp.run_name.set(model)
        pump(0.2)
        w = expect_dialog(ans)
        rp.run_btn.invoke()
        info = settle(w)
        Q.rec('item2', tag=tag, runs=runs, model=model,
              title=info.get('title'), texts=info.get('texts'),
              buttons=[b.get('text') for b in info.get('buttons', [])],
              shot=info.get('shot'), running=running(app))
    Q.rec('item2_after', runs_same=sorted(os.listdir(Q.RUNS)) == before,
          listing=sorted(os.listdir(Q.RUNS)),
          foreign_intact=os.listdir(foreign))
    rp.set_runs_dir(Q.RUNS)


def item3_and_1d(app):
    from blastlab.services import model_folder
    C = cases()
    app.setup.set_case(C['N1D'])
    pump(0.8)
    app._show('run')
    rp = app.run_panel
    rp.set_runs_dir(Q.RUNS)
    rp.run_name.set('TK_1D')
    folder = os.path.join(Q.RUNS, 'TK_1D')
    if not os.path.isdir(folder):
        model_folder.prepare(Q.RUNS, 'TK_1D', confirm=lambda t: True)
    old = os.path.join(folder, 'old_run.txt')
    with open(old, 'w', encoding='utf-8') as f:
        f.write('the previous run\n')
    snap = {p: os.stat(os.path.join(folder, p)).st_mtime_ns
            for p in os.listdir(folder)}
    # 1) a real Enter keypress on the dialog
    w = expect_dialog(('enter',), title_has='Model folder')
    rp.run_btn.invoke()
    info = settle(w)
    after = {p: os.stat(os.path.join(folder, p)).st_mtime_ns
             for p in os.listdir(folder)}
    Q.rec('item3_enter', info=info, folder_untouched=(after == snap),
          run_started=running(app))
    if running(app):
        wait_run(app)
    # 2) No
    w = expect_dialog(('button', 'No'), title_has='Model folder')
    rp.run_btn.invoke()
    info = settle(w)
    after = {p: os.stat(os.path.join(folder, p)).st_mtime_ns
             for p in os.listdir(folder)}
    Q.rec('item3_no', info=info, folder_untouched=(after == snap),
          run_started=running(app))
    # 3) Yes: overwrite, and the native 1D run
    w = expect_dialog(('button', 'Yes'), title_has='Model folder')
    t0 = time.time()
    rp.run_btn.invoke()
    info = settle(w)
    Q.rec('item3_yes', info=info, old_gone=not os.path.exists(old),
          run_started=running(app))
    shot('1d_running')
    wait_run(app)
    Q.rec('tk_1d_done', seconds=round(time.time() - t0, 1),
          log_tail=log_text(app)[-500:])
    shot('1d_done')
    check_folder(folder, 'TK_1D')


def item4_2d(app):
    C = cases()
    app.setup.set_case(C['N2D'])
    pump(0.8)
    rp = app.run_panel
    rp.set_runs_dir(Q.RUNS)
    rp.run_name.set('TK_2D')
    folder = os.path.join(Q.RUNS, 'TK_2D')
    rp.run_btn.invoke()
    pump(2)
    shot('2d_running')
    wait_run(app)
    shot('2d_done')
    check_folder(folder, 'TK_2D')
    # the Results tab's gauge table
    app._show('results')
    res = app.results
    try:
        res._view_seg.set('Gauges')
        res._view_selected('Gauges')
    except Exception as exc:
        Q.rec('tk_view_error', error=str(exc))
    pump(1.0)
    t = res.summary_table
    rows = [t.item(i)['values'] for i in t.get_children()]
    Q.rec('item11_tk', label=res.sel.get(), rows=rows)
    shot('results_gauges_2d')


def item9(app):
    """Results export dialogs: the initialdir each one is given."""
    real_save = grp.filedialog.asksaveasfilename
    real_dir = grp.filedialog.askdirectory
    calls = []

    def wrap(real, fn):
        def inner(**kw):
            calls.append(dict(fn=fn, **{k: str(v) for k, v in kw.items()}))
            w = Q.NativeDialogWatcher(
                os.path.join(SHOTS, _name(f'export_{fn}')),
                lambda info: ('close',), timeout=20,
                title_has=kw.get('title'))
            w.start()
            out = real(**kw)
            w.done.wait(5)
            calls[-1]['native'] = w.info
            calls[-1]['returned'] = out
            return out
        return inner
    grp.filedialog.asksaveasfilename = wrap(real_save, 'asksaveasfilename')
    grp.filedialog.askdirectory = wrap(real_dir, 'askdirectory')
    try:
        app._show('results')
        pump(0.5)
        for kind in ('summary', 'report', 'pngs'):
            app.results._export(kind)
            pump(0.8)
    finally:
        grp.filedialog.asksaveasfilename = real_save
        grp.filedialog.askdirectory = real_dir
    for c in calls:
        Q.rec('item9_tk', **c)


def item6(app):
    app._show('setup')
    for d in ('1D', '2D', '3D'):
        app.setup._dim_selected(d)
        pump(0.8)
        form = app.setup.form
        texts = labels_under(form)
        Q.rec('item6_tk', dim=d,
              has_outputs_card='Outputs' in texts,
              has_trigger_card='Trigger gauge' in texts,
              file_rows=[t for t in texts if any(
                  s in t for s in ('Gauge TSV', 'Animation (', 'Profile out',
                                   'Remap file'))],
              anim_format='Animation format' in texts,
              right_column=[t for t in texts if t in (
                  'Outputs', 'Trigger gauge', 'Animation format',
                  'Video colours', 'Gauge number\n(blank = off)',
                  'On arrival')])
        try:
            app.setup._form_host._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass
        shot(f'setup_{d}_bottom')
    app.setup._dim_selected('2D')
    pump(0.4)


def _chain(app, model, three=False):
    from blastlab.core.case import Case1D, Case2D, Case3D
    ch = app.chain
    app.run_panel.set_runs_dir(Q.RUNS)
    app.run_panel.run_name.set(model)
    ch.set_stage_case(1, Case1D(radius_m=0.6, charge_kg=0.5,
                                cell_size_m=0.004, n_snapshots=1,
                                gauge_radii=[], gauge_file=None))
    ch.set_stage_case(2, Case2D(geometry='axisymmetric', Lx=1.0, Ly=1.6,
                                cell_size_m=0.03, charge=0.5,
                                center=(0.0, 0.8), n_snapshots=1,
                                gauges=[(0.6, 0.8)], record_frames=0))
    ch.set_stage_case(3, Case3D(Lx=1.2, Ly=1.2, Lz=1.2, cell_size_m=0.08,
                                charge=0.5, center=(0.6, 0.6, 0.6),
                                n_snapshots=1, gauges=[], record_frames=0))
    for d in (1, 2, 3):
        ch.use[d].set(True)
    if not three:
        ch.use[3].set(False)
    pump(0.5)
    return ch


def item7(app):
    ch = app.chain
    app._show('chain')
    pump(0.6)
    texts = labels_under(ch)
    Q.rec('item7_tk_panel', hint=[t for t in texts if 'model folder' in t],
          workspace=[t for t in texts if 'orkspace' in t])
    shot('chain_tab')
    _chain(app, 'TK_CHAIN')
    app.run_panel.run_name.set('')
    w = expect_dialog(('button', 'OK'), title_has='Chain')
    r = ch._run()
    info = settle(w)
    Q.rec('item7_tk_refusal', returned=r, texts=info.get('texts'),
          shot=info.get('shot'),
          folder=os.path.isdir(os.path.join(Q.RUNS, 'TK_CHAIN')))
    _chain(app, 'TK_CHAIN')
    app._show('chain')
    pump(0.3)
    t0 = time.time()
    r = ch._run()
    marks = {}
    gaps, last = [], time.time()
    while time.time() - t0 < 900:
        pump(0.05)
        now = time.time()
        if now - last > 0.25:
            gaps.append(dict(at_s=round(now - t0, 2),
                             gap_ms=round((now - last) * 1e3)))
        last = now
        lt = log_text(app)
        for s in ('=== Stage 1D ===', '=== Stage 2D ==='):
            if s in lt and s not in marks:
                marks[s] = round(time.time() - t0, 2)
        if not running(app) and time.time() - t0 > 3:
            break
    pump(1.0)
    folder = os.path.join(Q.RUNS, 'TK_CHAIN')
    Q.rec('item12_tk', returned=r, marks=marks, gaps_over_250ms=gaps,
          total_s=round(time.time() - t0, 1))
    shot('chain_done')
    Q.rec('item7_tk_folder', top=sorted(os.listdir(folder))
          if os.path.isdir(folder) else [], tree=Q.tree(folder),
          root_manifest=manifest(folder))


def persist(app):
    rp = app.run_panel
    rp.set_runs_dir(Q.RUNS)
    rp._on_runs_dir()
    rp.run_name.set('TK_PERSIST')
    pump(0.3)
    with open(Q.SETTINGS, encoding='utf-8') as f:
        s1 = json.load(f).get('runs_dir')
    app._on_close()
    pump(0.5)
    with open(Q.SETTINGS, encoding='utf-8') as f:
        s2 = json.load(f)
    try:
        ROOT[0].destroy()
    except Exception:
        pass
    app2 = build()
    app2._show('run')
    pump(0.5)
    Q.rec('item1_tk_persist', settings_after_enter=s1,
          settings_after_close=s2.get('runs_dir'),
          auto_cleanup=s2.get('auto_cleanup'),
          reopened_runs=app2.run_panel.runs_dir.get(),
          reopened_model=app2.run_panel.run_name.get())
    shot('run_tab_reopened')
    return app2


def resume(app, run_name):
    """Item 10: Results -> Foam runs... -> select the stopped run ->
    Resume, into a model folder of its own."""
    rp = app.run_panel
    rp.set_runs_dir(Q.RUNS)
    rp.run_name.set('TK_RESUME')
    app._show('results')
    pump(0.5)
    app.results._open_run_browser()
    br = app.results._run_browser
    pump(120, until=lambda: not br._busy and br.rows)
    pump(0.5)
    Q.rec('item10_browser', n_rows=len(br.rows),
          mine=br.rows.get(run_name), status=br.status.cget('text'))
    try:
        br.table.see(run_name)
        br.table.selection_set(run_name)
    except Exception as exc:
        Q.rec('item10_select_error', error=str(exc))
    pump(0.4)
    name = _name('run_browser')
    try:
        Q.grab_hwnd(int(br.wm_frame(), 16), os.path.join(SHOTS, name))
        Q.rec('shot', path=name)
    except Exception as exc:
        Q.rec('shot_error', error=str(exc))
    t0 = time.time()
    br.btn_resume.invoke()
    started = pump(20, until=lambda: running(app))
    Q.rec('item10_started', started=bool(started),
          log_head=log_text(app)[:800])
    shot('resume_running')
    wait_run(app, timeout=1800)
    Q.rec('item10_done', seconds=round(time.time() - t0, 1),
          log_tail=log_text(app)[-1200:])
    shot('resume_done')
    folder = os.path.join(Q.RUNS, 'TK_RESUME')
    files, m = check_folder(folder, 'TK_RESUME')
    ws = (m.get('wsl_scratch') or {})
    if ws.get('posix'):
        import subprocess
        from blastlab.solvers.foam import env
        rc = subprocess.run(env.wsl_plain_argv(f"test -d '{ws['posix']}'"),
                            capture_output=True,
                            stdin=subprocess.DEVNULL).returncode
        Q.rec('item10_scratch', posix=ws['posix'], exists=(rc == 0),
              wsl_scratch=ws)
    app._show('results')
    pump(0.5)
    shot('resume_results')


def main():
    app = build()
    if RESUME:
        try:
            resume(app, RESUME)
        except Exception:
            import traceback
            Q.rec('step_error', key='resume', tb=traceback.format_exc())
    else:
        steps = [('1', item1), ('2', item2), ('3', item3_and_1d),
                 ('4', item4_2d), ('9', item9), ('6', item6), ('7', item7)]
        for key, fn in steps:
            if ONLY and key not in ONLY:
                continue
            Q.rec('step', key=key)
            try:
                fn(app)
            except Exception:
                import traceback
                Q.rec('step_error', key=key, tb=traceback.format_exc())
        if not ONLY or 'P' in ONLY:
            app = persist(app)
    t0 = time.time()
    try:
        APP[0]._on_close()
    except Exception:
        import traceback
        Q.rec('close_error', tb=traceback.format_exc())
    pump(0.5)
    try:
        ROOT[0].destroy()
    except Exception:
        pass
    Q.rec('closed', seconds=round(time.time() - t0, 2),
          dialogs=len(DIALOGS))


if __name__ == '__main__':
    main()
    os._exit(0)
