"""Tk probe: the 1D form after a 3D case scrolled down - what does the form
column show? (the qa_tk.py 1D shots came out blank). Real window,
PrintWindow captures. QA_REPO selects the source tree (the branch, or a
`git archive master` copy for the before/after comparison).
Run:  python -u qa_tk_1d.py <shots dir> <tag>
"""
import os
import sys

REPO = os.environ.get('QA_REPO', r'C:\Users\rotem.ofek\OneDrive - Technion\BlastFoam')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)
assert os.environ.get('BLASTLAB_SETTINGS')
SHOTS, TAG = sys.argv[1], sys.argv[2]


def main():
    import ctypes
    from tkinter import messagebox
    import customtkinter as ctk
    from printwindow import capture
    for fn in ('showerror', 'showwarning', 'showinfo'):
        setattr(messagebox, fn, lambda *a, **k: None)
    from blastlab.gui import app as appmod
    print('blastlab from', appmod.__file__, flush=True)
    from blastlab.core.case import Case1D, Case3D
    user32 = ctypes.windll.user32
    ctk.set_appearance_mode('dark')
    root = ctk.CTk()
    app = appmod.App(root)
    root.geometry('1280x840+10+10')

    def pump(s=0.3):
        root.after(int(s * 1000), root.quit)
        root.mainloop()

    pump(2.0)
    hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()

    def shot(name):
        pump(0.5)
        img, ok, rect = capture(hwnd)
        img.save(os.path.join(SHOTS, f'tk_{TAG}_{name}.png'))

    def state(tag):
        root.update_idletasks()
        f = app.setup.form
        c = app.setup._form_host._parent_canvas
        print(tag, dict(dim=f.dim, form_mapped=f.winfo_ismapped(),
                        form_req=f.winfo_reqheight(),
                        scrollregion=c.cget('scrollregion'), yview=c.yview()),
              flush=True)

    app.setup.set_case(Case3D(solver='blastfoam'))
    pump(1.2)
    state('3D')
    c = app.setup._form_host._parent_canvas
    c.yview_moveto(0.7)
    pump(0.5)
    app.setup._dim_seg.set('1D'); app.setup._dim_selected('1D'); pump(1.2)
    state('1D via the 1D button after 3D scrolled to 0.7')
    shot('1d_via_button_after_3d_scrolled')
    app._on_close()


if __name__ == '__main__':
    main()
