"""GUI-14 QA driver (Tk --tk GUI, real desktop): Results Gauges table at ctk scaling 1.0 / 1.5.
usage: python driver_tk.py <scaling>"""
import os, sys, time, json
REPO = r'C:\Users\rotem.ofek\blastlab-worktrees\gui-14'
sys.path.insert(0, REPO)
OUT = os.path.join(REPO, 'docs', 'qa', '2026-10-11-gui-14-qa')
os.environ['PYTHONIOENCODING'] = 'utf-8'
SC = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
TAG = str(SC).replace('.', 'p')
RES = []


def check(name, ok, detail=''):
    RES.append(dict(name=name, ok=bool(ok), detail=str(detail)))
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else '  -> ' + str(detail)))
    if detail:
        print('      ' + str(detail)[:500])


def main():
    from blastlab.ui import testing
    testing.private_settings()
    import tkinter.font as tkfont
    from tkinter import messagebox
    modal = []
    for n in ('showerror', 'showinfo', 'showwarning'):
        setattr(messagebox, n, lambda title, msg, _n=n, **k: modal.append((_n, title, str(msg))))
    messagebox.askyesno = lambda *a, **k: modal.append(('askyesno', a[:1])) or True
    import customtkinter as ctk
    from PIL import ImageGrab
    from blastlab.core.case import Case2D
    from blastlab.gui import app as appmod
    ctk.set_widget_scaling(SC)
    ctk.set_window_scaling(SC)
    ctk.set_appearance_mode('dark')
    root = ctk.CTk()
    app = appmod.App(root)
    testing.use_model(app, 'gui14tk')

    def pump(seconds, until=None):
        st = dict(res=False)
        dl = time.perf_counter() + seconds

        def tick():
            if until is not None and until():
                st['res'] = True; root.quit(); return
            if time.perf_counter() >= dl:
                root.quit(); return
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
        try:
            ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(os.path.join(OUT, name))
        except OSError:
            printwindow(root).save(os.path.join(OUT, name))
        print('shot', name, (x, y, w, h))
        return w, h

    root.geometry('1100x720+0+0')
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
    app._show('setup')
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
    rp._view_seg.set('Gauges')
    rp._view_selected('Gauges')
    pump(0.6)
    try:
        rp._draw_gauges()
    except Exception as exc:
        print('draw gauges', exc)
    pump(1.0)
    tbl = rp.summary_table
    rows = [tbl.item(i, 'values') for i in tbl.get_children()]
    print('Tk summary rows', rows)
    w, h = shoot(f'tk_results_gauges_s{TAG}_1100x720.png', '1100x720+0+0')
    from tkinter import ttk
    st = ttk.Style(tbl)
    fname = st.lookup(tbl.cget('style') or 'Treeview', 'font') or 'TkDefaultFont'
    fnt = tkfont.Font(font=fname)
    cols = tbl['columns']
    info = {c: (int(tbl.column(c, 'width')), int(tbl.column(c, 'minwidth'))) for c in cols}
    print('columns (width, minwidth)', info, 'table width', tbl.winfo_width(), 'font', fnt.actual())
    ok_fit = True
    for iid in tbl.get_children():
        v = tbl.item(iid, 'values')
        gw = int(tbl.column('gauge', 'width'))
        need = fnt.measure(str(v[0]))
        if need > gw:
            ok_fit = False
    widest = max(fnt.measure(str(r[0])) for r in rows)
    check(f'[{SC}] gauge cell text fits the gauge column', ok_fit, (info['gauge'], widest))
    # complete column bbox inside the table
    last = tbl.get_children()[0]
    bb = tbl.bbox(last, cols[-1]) if cols else None
    comp = 'complete' if 'complete' in cols else cols[-1]
    bb = tbl.bbox(last, comp)
    print('complete cell bbox', bb, 'table width', tbl.winfo_width())
    check(f'[{SC}] right edge of the {comp} cell inside the table',
          bool(bb) and bb[0] + bb[2] <= tbl.winfo_width() + 1, (bb, tbl.winfo_width()))
    check(f'[{SC}] every result column visible (bbox non-empty)',
          all(tbl.bbox(last, c) for c in cols), {c: tbl.bbox(last, c) for c in cols})
    shoot(f'tk_results_gauges_s{TAG}_1600x1000.png', '1600x1000+0+0')
    check(f'[{SC}] no modal dialogs', not modal, modal)
    root.attributes('-topmost', False)
    root.destroy()
    json.dump(RES, open(os.path.join(OUT, f'results_tk_s{TAG}.json'), 'w'), indent=1)
    print(sum(r['ok'] for r in RES), '/', len(RES))


def printwindow(root):
    """Render the toplevel through Win32 PrintWindow into a PIL image."""
    import ctypes
    from ctypes import wintypes
    from PIL import Image
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = u.GetParent(root.winfo_id()) or root.winfo_id()
    rc = wintypes.RECT()
    u.GetClientRect(hwnd, ctypes.byref(rc))
    w, h = rc.right, rc.bottom
    hdc = u.GetDC(hwnd)
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, h)
    g.SelectObject(mdc, bmp)
    u.PrintWindow(hwnd, mdc, 3)       # PW_CLIENTONLY | PW_RENDERFULLCONTENT

    class BMI(ctypes.Structure):
        _fields_ = [('biSize', wintypes.DWORD), ('biWidth', ctypes.c_long),
                    ('biHeight', ctypes.c_long), ('biPlanes', wintypes.WORD),
                    ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                    ('biSizeImage', wintypes.DWORD), ('x', ctypes.c_long),
                    ('y', ctypes.c_long), ('cu', wintypes.DWORD), ('ci', wintypes.DWORD)]
    bi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1).convert('RGB')
    g.DeleteObject(bmp); g.DeleteDC(mdc); u.ReleaseDC(hwnd, hdc)
    return img




if __name__ == '__main__':
    main()
