"""FoamRunBrowser (N8): headless checks with injected data sources.

A synthetic run list (finished / running / unknown) fills the table with
name, dims (from a fake case.json), size and state; Load hands the
selected run's path to the callback; Delete refuses running/unknown
runs, asks for confirmation, calls the deleter for a finished run and
refreshes. No WSL, hidden Tk root.

Run:  cd blastlab/tests && python test_gui_run_browser.py
"""
import json
import os
import sys
import tempfile
import time

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def pump(root, seconds=1.5, until=None):
    t0 = time.time()
    while time.time() - t0 < seconds:
        root.update()
        if until is not None and until():
            return True
        time.sleep(0.02)
    return until() if until else True


def main():
    import customtkinter as ctk
    from blastlab.gui.run_browser import (FoamRunBrowser, human_size,
                                          started_from_name)

    check('human_size', human_size(1536) == '1.5 KB' and human_size(None) == '?'
          and human_size(3 * 1024 ** 3) == '3.0 GB')
    check('started_from_name', started_from_name('20260905-162157_2d_p1-00')
          == '2026-09-05 16:21:57' and started_from_name('weird') == '')

    tmp = tempfile.mkdtemp(prefix='blastlab_runs_')
    runs = []
    for name, dim, alive in (('20260905-120000_2d_p1-00', 2, False),
                             ('20260905-130000_3d_p2-00', 3, True),
                             ('20260905-140000_1d_p3-00', 1, None)):
        d = os.path.join(tmp, name)
        os.makedirs(d)
        with open(os.path.join(d, 'case.json'), 'w') as f:
            json.dump(dict(dim=dim), f)
        runs.append((name, d, alive))
    sizes = {f'/root/blastlab_runs/{n}': dict(bytes=(i + 1) * 1024 ** 2,
                                              mtime=1000)
             for i, (n, _d, _a) in enumerate(runs)}
    deleted, loaded, asked = [], [], []

    def lister():
        return [r for r in runs if r[0] not in deleted]

    def deleter(dirs):
        deleted.extend(d.rsplit('/', 1)[-1] for d in dirs)
        return True

    root = ctk.CTk()
    root.withdraw()
    win = FoamRunBrowser(root, on_load=loaded.append, log=lambda s: None,
                         lister=lister, sizer=lambda d: sizes,
                         deleter=deleter,
                         confirm=lambda t, m: asked.append(m) or True)
    win.withdraw()
    ok = pump(root, 3.0, until=lambda: not win._busy)
    check('listing + sizing finished off-thread', ok)
    items = win.table.get_children()
    check('one row per run', len(items) == 3, str(len(items)))
    vals = {win.table.item(i)['values'][0]: win.table.item(i)['values']
            for i in items}
    r2d = vals['20260905-120000_2d_p1-00']
    check('row shows dims from case.json, size and state',
          str(r2d[1]) == '2D' and str(r2d[2]) == '1.0 MB'
          and str(r2d[4]) == 'finished', str(r2d))
    check('running / unknown states shown',
          str(vals['20260905-130000_3d_p2-00'][4]) == 'running'
          and str(vals['20260905-140000_1d_p3-00'][4]) == 'unknown')
    check('status line has the total', '6.0 MB total' in win.status.cget('text'),
          win.status.cget('text'))

    print("\nactions")
    win.table.selection_set('20260905-130000_3d_p2-00')
    win.load_selected()
    check('Load hands the selected run path to the callback',
          loaded and loaded[-1].endswith('20260905-130000_3d_p2-00'), str(loaded))
    win.delete_selected()
    check('Delete refuses a running run', deleted == [] and not asked
          and 'not deleting' in win.status.cget('text'), win.status.cget('text'))
    win.table.selection_set('20260905-140000_1d_p3-00')
    win.delete_selected()
    check('Delete refuses an unknown-state run', deleted == [] and not asked)
    win.table.selection_set('20260905-120000_2d_p1-00')
    win.delete_selected()
    ok = pump(root, 3.0, until=lambda: not win._busy and deleted)
    check('Delete of a finished run asks, deletes and refreshes',
          asked and deleted == ['20260905-120000_2d_p1-00']
          and len(win.table.get_children()) == 2, f'{asked} {deleted}')
    win.table.selection_set(())
    win.load_selected()
    check('Load without a selection is a no-op with a hint',
          'select a run' in win.status.cget('text'))

    print("\nResults panel wiring")
    from blastlab.gui.results_panel import ResultsPanel
    panel = ResultsPanel(root)
    check('panel exposes load_foam_run_path', callable(panel.load_foam_run_path))
    texts = []

    def walk(w):
        for ch in w.winfo_children():
            try:
                texts.append(ch.cget('text'))
            except Exception:
                pass
            walk(ch)
    walk(panel)
    check("'Foam runs…' button present", any('Foam runs' in str(t) for t in texts))
    win.destroy()
    root.destroy()


if __name__ == '__main__':
    main()
    print()
    print('GUI RUN BROWSER: ' + ('PASS' if not FAILS
                                 else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
