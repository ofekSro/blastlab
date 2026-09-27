"""Throwaway QA harness, Tk part 2: (a) the matrix tooltips, raised with
<Enter> on the CTkLabel's inner tk.Label (where CTkLabel.bind puts the
binding); (b) who makes the right column overflow at the 1100 px minimum
window: every card's requested width, blastFoam vs native, 1D/2D/3D.
Run:  python -u qa_tk2.py <shots dir>
"""
import json
import os
import sys
import traceback

REPO = r'C:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)
assert os.environ.get('BLASTLAB_SETTINGS')
SHOTS = sys.argv[1]
RES = dict(tips={}, widths={}, checks=[])


def main():
    import ctypes
    from tkinter import messagebox
    import customtkinter as ctk
    from printwindow import capture
    for fn in ('showerror', 'showwarning', 'showinfo'):
        setattr(messagebox, fn, lambda *a, **k: None)
    from blastlab.gui import app as appmod
    from blastlab.gui.theme import Card
    from blastlab.core.case import Case1D, Case2D, Case3D
    user32 = ctypes.windll.user32
    ctk.set_appearance_mode('dark')
    root = ctk.CTk()
    app = appmod.App(root)
    root.geometry('1100x720+10+10')

    def pump(s=0.3):
        root.after(int(s * 1000), root.quit)
        root.mainloop()

    pump(2.0)
    hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()

    def shot(name):
        pump(0.4)
        img, ok, rect = capture(hwnd)
        img.save(os.path.join(SHOTS, f'tk_{name}.png'))

    def find_label(parent, text):
        for w in parent.winfo_children():
            try:
                if isinstance(w, ctk.CTkLabel) and w.cget('text') == text:
                    return w
            except Exception:
                pass
            r = find_label(w, text)
            if r is not None:
                return r
        return None

    def cards(form):
        out = []
        for w in form.winfo_children():
            if isinstance(w, Card):
                title = None
                for ch in w.winfo_children():
                    if isinstance(ch, ctk.CTkLabel):
                        title = ch.cget('text'); break
                out.append((title, w))
        return out

    # (b) widths
    for mode in ('blastfoam', 'native'):
        for dim, C in ((1, Case1D), (2, Case2D), (3, Case3D)):
            app.setup.set_case(C(solver=mode))
            pump(1.0)
            f = app.setup.form
            root.update_idletasks()
            rows = []
            for title, w in cards(f):
                info = w.grid_info() if w.winfo_manager() == 'grid' else {}
                rows.append(dict(title=title, col=info.get('column'),
                                 shown=w.winfo_manager() == 'grid',
                                 req=w.winfo_reqwidth(), got=w.winfo_width()))
            canvas = app.setup._form_host._parent_canvas
            RES['widths'][f'{mode}_{dim}d'] = dict(
                canvas_w=canvas.winfo_width(), form_req=f.winfo_reqwidth(),
                form_w=f.winfo_width(), cards=rows)
            over = [r for r in rows if r['shown'] and r['got'] < r['req'] - 1]
            print(mode, dim, 'canvas', canvas.winfo_width(), 'form req',
                  f.winfo_reqwidth(), 'overflowing:',
                  [(r['title'], r['req'], r['got']) for r in over], flush=True)
            if dim == 3:
                app.setup._form_host._parent_canvas.yview_moveto(1.0)
                pump(0.4)
                shot(f'1100_{mode}_3d_bottom')

    # (a) tooltips, 1280 wide
    root.geometry('1280x840+10+10')
    pump(0.8)
    for mode_name in ('dark', 'light'):
        if mode_name == 'light':
            app._mode_switch.deselect(); app._toggle_mode(); pump(1.0)
        app.setup.set_case(Case3D(solver='blastfoam'))
        pump(1.0)
        f = app.setup.form
        f.v['vtk_s_on'].set(True)
        pump(0.4)
        root.update_idletasks()
        h = max(1, f.winfo_height())
        y = f._vtk_grid.winfo_rooty() - f.winfo_rooty()
        app.setup._form_host._parent_canvas.yview_moveto(max(0, (y - 40) / h))
        pump(0.5)
        for text in ('Gauge', 'Sect.', 'Obst.', 'Vol.', 'Peak overpr.',
                     'Products', 'Arrival time'):
            lbl = find_label(f._vtk_grid, text)
            inner = getattr(lbl, '_label', lbl)
            inner.event_generate('<Enter>', x=5, y=5)
            pump(0.9)
            tip = getattr(lbl, '_blastlab_tip', None)
            tw = getattr(tip, '_tip', None)
            txt = None
            if tw is not None:
                for ch in tw.winfo_children():
                    try:
                        txt = ch.cget('text')
                    except Exception:
                        pass
                th = user32.GetParent(tw.winfo_id()) or tw.winfo_id()
                img, ok, rect = capture(th)
                safe = text.replace('.', '').replace(' ', '_')
                img.save(os.path.join(SHOTS, f'tk_tip_{mode_name}_{safe}.png'))
                # the window with the tip: PrintWindow of the root does not
                # include another top-level, so record where it sits
                RES['tips'][f'{mode_name} {text}'] = dict(
                    text=txt, rect=rect,
                    label_at=(lbl.winfo_rootx(), lbl.winfo_rooty()))
            RES['checks'].append((f'{mode_name} {text}', tw is not None, txt))
            print(mode_name, text, '->', txt, flush=True)
            inner.event_generate('<Leave>', x=5, y=5)
            pump(0.3)
    app._mode_switch.select(); app._toggle_mode(); pump(0.5)
    app._on_close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
    with open(os.path.join(SHOTS, 'tk2_results.json'), 'w', encoding='utf-8') as fh:
        json.dump(RES, fh, indent=1, default=str)
