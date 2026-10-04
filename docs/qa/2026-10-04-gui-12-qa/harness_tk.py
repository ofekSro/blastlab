"""GUI-12 QA harness (Tk --tk GUI, real run on the real desktop)."""
import os, sys, time, json
REPO = r'c:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
sys.path.insert(0, REPO)
OUT = os.path.join(REPO, 'docs', 'qa', '2026-10-04-gui-12-qa')
os.environ['PYTHONIOENCODING'] = 'utf-8'
RES = []


def check(name, ok, detail=''):
    RES.append(dict(name=name, ok=bool(ok), detail=str(detail)))
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else '  -> ' + str(detail)))
    if ok and detail:
        print('      ' + str(detail)[:300])


def main():
    from blastlab.ui import testing
    testing.private_settings()
    import tkinter as tk
    from tkinter import messagebox
    modal = []
    for n in ('showerror', 'showinfo', 'showwarning'):
        setattr(messagebox, n, lambda title, msg, _n=n, **k: modal.append((_n, title, str(msg))))
    messagebox.askyesno = lambda *a, **k: modal.append(('askyesno', a[:1])) or True
    import customtkinter as ctk
    from PIL import ImageGrab
    from blastlab.core.case import Case2D
    from blastlab.gui import app as appmod
    ctk.set_appearance_mode('dark')
    root = ctk.CTk()
    app = appmod.App(root)
    testing.use_model(app, 'gui12qa_tk')

    def pump(seconds, until=None):
        st = dict(done=False, res=False)
        dl = time.perf_counter() + seconds

        def tick():
            if until is not None and until():
                st.update(done=True, res=True); root.quit(); return
            if time.perf_counter() >= dl:
                st.update(done=True); root.quit(); return
            root.after(25, tick)
        root.after(25, tick)
        root.mainloop()
        return st['res']

    def shoot(name, geom):
        root.geometry(geom)
        root.deiconify(); root.lift()
        root.attributes('-topmost', True)
        root.focus_force()
        pump(1.0)
        root.update_idletasks()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        w, h = root.winfo_width(), root.winfo_height()
        path = os.path.join(OUT, name)
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)
        print('shot', path, (x, y, w, h))
        return path

    root.geometry('1280x840+0+0')
    root.deiconify()
    pump(1.5)
    dx = 2.4 / 43
    cx = lambda i: (i + 0.5) * dx
    G1 = (round(cx(19) - 0.45 * dx, 4), round(cx(12) + 0.45 * dx, 4))
    G3 = (round(20 * dx + 0.05 * dx, 4), round(cx(12), 4))
    G2 = (G3[0], round(cx(12) + 0.55 * dx, 4))
    wall = (round(20 * dx, 4), 1.5, round(13 * dx, 4), 1.0)
    case = Case2D(solver='native', geometry='planar', Lx=2.4, Ly=1.6,
                  cell_size_m=0.1, charge=400.0, center=(0.3, 0.8),
                  t_end=1.5e-3, n_snapshots=3, record_frames=0,
                  gauge_file=None, obstacles=[wall], gauges=[G1, G2, G3])
    app.setup.set_case(case)
    pump(0.8)
    app._run_single()
    t0 = time.monotonic()
    pump(240, until=lambda: time.monotonic() - t0 > 1 and not app._running())
    pump(2.0)
    print('modal', modal)
    app._show('results')
    pump(0.8)
    rp = app.results
    ents = rp._entries
    check('Tk: a result exists after the run', len(ents) >= 1, len(ents))
    rp._view_seg.set('Gauges')
    rp._view_selected('Gauges')
    pump(0.5)
    try:
        rp._draw_gauges()
    except Exception as exc:
        print('draw gauges', exc)
    pump(1.0)
    fig = rp.gauge_canvas.figure
    titles = [ax.get_title() for ax in fig.axes]
    print('Tk gauge figure titles', titles)
    res = rp._current().result
    print('points', res.gauges['points'])
    check('Tk Gauges tab: 2 traces, titled Gauge 1 and Gauge 3 (no Gauge 2)',
          len(titles) == 2 and titles[0].startswith('Gauge 1')
          and titles[1].startswith('Gauge 3'), titles)
    rows = [rp.summary_table.item(i, 'values') for i in rp.summary_table.get_children()]
    print('Tk summary rows', rows)
    check('Tk summary table labels G1, G3',
          [str(r[0]).split()[0] for r in rows] == ['G1', 'G3'], rows)
    shoot('10_tk_gauges_tab_1280x840.png', '1280x840+0+0')
    shoot('10_tk_gauges_tab_1000x700.png', '1000x700+0+0')
    shoot('10_tk_gauges_tab_1600x1000.png', '1600x1000+0+0')
    check('Tk: no modal dialogs', not modal, modal)
    root.attributes('-topmost', False)
    root.destroy()
    json.dump(RES, open(os.path.join(OUT, 'results_tk.json'), 'w'), indent=1)
    print(sum(r['ok'] for r in RES), '/', len(RES))


if __name__ == '__main__':
    main()
