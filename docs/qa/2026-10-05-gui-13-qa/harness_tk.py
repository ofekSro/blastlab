"""GUI-13 QA harness (Tk --tk GUI, real run on the real desktop)."""
import os, sys, time, json
REPO = r'c:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
sys.path.insert(0, REPO)
OUT = os.path.join(REPO, 'docs', 'qa', '2026-10-05-gui-13-qa')
os.environ['PYTHONIOENCODING'] = 'utf-8'
RES = []


def check(name, ok, detail=''):
    RES.append(dict(name=name, ok=bool(ok), detail=str(detail)))
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else '  -> ' + str(detail)))
    if ok and detail:
        print('      ' + str(detail)[:400])


def main():
    from blastlab.ui import testing
    testing.private_settings()
    import tkinter as tk
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
    ctk.set_appearance_mode('dark')
    root = ctk.CTk()
    app = appmod.App(root)
    testing.use_model(app, 'gui13qa_tk')

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
        path = os.path.join(OUT, name)
        try:
            ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)
        except OSError:
            printwindow(root).save(path)      # screen grab refused (locked desktop)
        print('shot', path, (x, y, w, h))

    root.geometry('1100x720+0+0')
    root.deiconify()
    pump(1.5)
    # --- Setup warnings
    two_wall = Case2D(
        solver='native', geometry='planar', Lx=2.4, Ly=1.6,
        cell_size_m=0.05, charge=20.0, center=(0.3, 0.8),
        obstacles=[(1.2, 1.6, 0.0, 0.6), (1.8, 2.0, 0.9, 1.3)],
        gauges=[(0.3, 0.8), (1.4, 0.3), (1.2, 0.3), (1.8, 0.8),
                (1.9, 1.1), (2.0, 1.2), (3.0, 0.5)],
        n_snapshots=2, record_frames=0, gauge_file=None)
    app._show('setup')
    app.setup.set_case(two_wall)
    pump(1.5)
    texts = []
    for row in app.setup._status_rows:
        for c in row.winfo_children():
            t = c.cget('text') if hasattr(c, 'cget') else ''
            if t:
                texts.append(t)
    print('TK SETUP WARNINGS', texts)
    drop = [t for t in texts if 'dropped' in t]
    import re
    pat = re.compile(r'^G\d+ \(-?\d+\.\d\d, -?\d+\.\d\d\) m (inside Wall \d+|on the face of Wall \d+|outside the domain) - will be dropped$')
    check('Tk Setup warnings: G<n> (x, y) m wording',
          len(drop) == 5 and all(pat.match(t) for t in drop), drop)
    shoot('20_tk_setup_warnings_1100x720.png', '1100x720+0+0')
    shoot('20_tk_setup_warnings_1600x1000.png', '1600x1000+0+0')
    # --- run + results
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
    rp._view_seg.set('Gauges')
    rp._view_selected('Gauges')
    pump(0.5)
    try:
        rp._draw_gauges()
    except Exception as exc:
        print('draw gauges', exc)
    pump(1.0)
    tbl = rp.summary_table
    rows = [tbl.item(i, 'values') for i in tbl.get_children()]
    print('Tk summary rows', rows)
    shoot('21_tk_gauges_tab_1100x720.png', '1100x720+0+0')
    gw = int(tbl.column('gauge', 'width'))
    fnt = tkfont.Font(font=tbl.cget('style') and ttk_font(tbl) or None)
    widest = max(fnt.measure(str(r[0])) for r in rows)
    print('gauge column width', gw, 'widest text px', widest, 'font', fnt.actual())
    check('Tk Gauges: gauge column fits the widest cell text at 1100x720',
          gw >= widest + 8, (gw, widest, rows[0][0]))
    check('Tk Gauges: labels G1, G3', [str(r[0]).split()[0] for r in rows] == ['G1', 'G3'], rows)
    shoot('21_tk_gauges_tab_1600x1000.png', '1600x1000+0+0')
    check('Tk: no modal dialogs', not modal, modal)
    root.attributes('-topmost', False)
    root.destroy()
    json.dump(RES, open(os.path.join(OUT, 'results_tk.json'), 'w'), indent=1)
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


def ttk_font(tbl):
    from tkinter import ttk
    st = ttk.Style(tbl)
    f = st.lookup(tbl.cget('style') or 'Treeview', 'font') or 'TkDefaultFont'
    return f


if __name__ == '__main__':
    main()
