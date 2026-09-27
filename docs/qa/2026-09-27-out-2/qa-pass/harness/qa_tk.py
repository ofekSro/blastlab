"""Throwaway QA harness (gui-qa-tester, 2026-09-27): the OUT-2 card in the
REAL Tk window (`python -m blastlab --tk`'s App on a ctk.CTk root).

The session is locked during this pass, so ImageGrab cannot read the
desktop; the window is captured through Win32 PrintWindow instead, and a
tooltip is raised with the <Enter> event its binding listens to (a real
cursor cannot hover a locked desktop).
Run:  python -u qa_tk.py <shots dir> <work dir>
"""
import json
import os
import sys
import time
import traceback

REPO = r'C:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)
assert os.environ.get('BLASTLAB_SETTINGS')
SHOTS, WORK = sys.argv[1], sys.argv[2]
os.makedirs(WORK, exist_ok=True)
RES = dict(checks=[], notes=[], errors=[], strips={}, geo={}, colours={},
           tips={}, dialogs=[])


def log(*a):
    print(*a, flush=True)


def check(name, ok, detail=''):
    RES['checks'].append(dict(name=name, ok=bool(ok), detail=str(detail)))
    log(f"[{'PASS' if ok else 'FAIL'}] {name} {('- ' + str(detail)) if detail else ''}")


def main():
    import ctypes
    import tkinter as tk
    from tkinter import filedialog, messagebox
    import customtkinter as ctk
    from printwindow import capture
    from blastlab.core import settings
    assert settings.load().get('auto_cleanup') is False
    # no modal dialog may block the pass: record them instead
    for fn in ('showerror', 'showwarning', 'showinfo'):
        setattr(messagebox, fn, lambda *a, _fn=fn, **k:
                RES['dialogs'].append((_fn, a)))
    for fn in ('askyesno', 'askokcancel'):
        setattr(messagebox, fn, lambda *a, _fn=fn, **k:
                RES['dialogs'].append((_fn, a)) or False)
    save_to = {'path': ''}
    filedialog.asksaveasfilename = lambda *a, **k: save_to['path']
    from blastlab.gui import app as appmod
    from blastlab.core.case import Case1D, Case2D, Case3D, save_case
    user32 = ctypes.windll.user32

    ctk.set_appearance_mode('dark')
    root = ctk.CTk()
    errs = []
    root.report_callback_exception = lambda et, ev, tb: errs.append(
        ''.join(traceback.format_exception(et, ev, tb)))
    app = appmod.App(root)
    root.geometry('1280x840+10+10')
    root.deiconify()

    def pump(s=0.3):
        root.after(int(s * 1000), root.quit)
        root.mainloop()

    pump(2.0)
    hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
    RES['notes'].append(f'title {root.title()!r}, geometry {root.geometry()}')

    def shot(name, crop_widget=None):
        pump(0.4)
        root.update_idletasks()
        img, ok, rect = capture(hwnd)
        if crop_widget is not None:
            x0 = crop_widget.winfo_rootx() - rect[0]
            y0 = crop_widget.winfo_rooty() - rect[1]
            img = img.crop((max(0, x0), max(0, y0),
                            x0 + crop_widget.winfo_width(),
                            y0 + crop_widget.winfo_height()))
        p = os.path.join(SHOTS, f'tk_{name}.png')
        img.save(p)
        log(f'  shot {p} (PrintWindow ok={ok})')
        return img

    setup = app.setup

    def form():
        return setup.form

    def canvas():
        return setup._form_host._parent_canvas

    def scroll(frac):
        canvas().yview_moveto(frac)
        pump(0.4)

    def see(widget):
        root.update_idletasks()
        f = form()
        h = max(1, f.winfo_height())
        y = widget.winfo_rooty() - f.winfo_rooty()
        scroll(max(0.0, (y - 10) / h))

    def strip():
        out = []
        for row in setup._status_body.winfo_children():
            for lbl in row.winfo_children():
                try:
                    t = lbl.cget('text')
                except Exception:
                    continue
                if t:
                    out.append(t)
        return out

    def set_case(c):
        setup.set_case(c)
        pump(1.2)

    def visible_in_viewport(widget):
        root.update_idletasks()
        c = canvas()
        top, bot = c.winfo_rooty(), c.winfo_rooty() + c.winfo_height()
        y0 = widget.winfo_rooty()
        y1 = y0 + widget.winfo_height()
        return y0 >= top - 2 and y1 <= bot + 2, (y0 - top, y1 - top,
                                                  c.winfo_height())

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

    def card_of(label_widget):
        w = label_widget
        from blastlab.gui.theme import Card
        while w is not None and not isinstance(w, Card):
            w = w.master
        return w

    def live(name):
        return str(form()._vtk_entries[name].cget('state')) == 'normal'

    # ── 3D card: layout, scrolling, Trigger + strip reachable ─────────
    for size in ('1280x840', '1100x720'):
        try:
            root.geometry(size + '+10+10')
            pump(1.0)
            set_case(Case3D(solver='blastfoam'))
            f = form()
            f.v['vtk_s_on'].set(True)
            f.v['vtk_v_on'].set(True)
            pump(0.8)
            card = f._vtk_card
            trig_lbl = find_label(f, 'Trigger gauge')
            trig = card_of(trig_lbl) if trig_lbl else None
            root.update_idletasks()
            # column heights
            col_h = {0: 0, 1: 0}
            for w in f.grid_slaves():
                info = w.grid_info()
                if w.winfo_manager() == 'grid' and w.winfo_ismapped():
                    col = int(info.get('column', 0))
                    col_h[col] = max(col_h[col], w.winfo_y() + w.winfo_height())
            RES['geo'][size] = dict(form_h=f.winfo_height(),
                                    canvas_h=canvas().winfo_height(),
                                    col0_bottom=col_h[0], col1_bottom=col_h[1],
                                    vtk_y=card.winfo_y(), vtk_h=card.winfo_height(),
                                    vtk_w=card.winfo_width(),
                                    trigger_y=trig.winfo_y() if trig else None)
            log('  geo', size, RES['geo'][size])
            see(card)
            shot(f'3d_card_top_{size}')
            shot(f'3d_card_top_{size}_crop', card)
            scroll(1.0)
            ok, pos = visible_in_viewport(trig) if trig else (False, None)
            check(f'{size}: scrolled to the end, the Trigger gauge card is '
                  'fully in view', ok, pos)
            s_ok = setup._status_card.winfo_ismapped() and \
                setup._status_card.winfo_rooty() + setup._status_card.winfo_height() \
                <= root.winfo_rooty() + root.winfo_height() + 2
            check(f'{size}: the validation strip is on screen', s_ok,
                  (setup._status_card.winfo_rooty() - root.winfo_rooty(),
                   setup._status_card.winfo_height(), root.winfo_height()))
            shot(f'3d_bottom_{size}')
            # the matrix itself
            see(f._vtk_grid)
            shot(f'3d_matrix_{size}_crop', f._vtk_grid)
            # headers clipped? label reqwidth vs actual width
            clipped = []
            for w in f._vtk_grid.winfo_children():
                if isinstance(w, ctk.CTkLabel):
                    if w.winfo_width() + 1 < w.winfo_reqwidth():
                        clipped.append((w.cget('text'), w.winfo_width(),
                                        w.winfo_reqwidth()))
            gx = f._vtk_grid.winfo_rootx() + f._vtk_grid.winfo_width()
            cx = card.winfo_rootx() + card.winfo_width()
            check(f'{size}: matrix labels not clipped and matrix inside '
                  'its card', not clipped and gx <= cx,
                  f'clipped {clipped}, grid right {gx} card right {cx}')
        except Exception:
            RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # ── greyed entries (muted) + tooltips ─────────────────────────────
    for mode_name in ('dark', 'light'):
        try:
            if mode_name == 'light':
                app._mode_switch.deselect()
                app._toggle_mode()
                pump(1.2)
            root.geometry('1280x840+10+10')
            pump(0.6)
            set_case(Case3D(solver='blastfoam'))
            f = form()
            f.v['vtk_s_on'].set(True)
            f.v['vtk_v_on'].set(True)
            f._vtk_radios['s'][1].invoke()
            pump(0.6)
            cols = {}
            for n in ('vtk_s_ms', 'vtk_s_steps', 'vtk_v_ms', 'vtk_v_steps'):
                e = f._vtk_entries[n]
                cols[n] = dict(state=str(e.cget('state')),
                               text_color=str(e.cget('text_color')),
                               fg=str(e.cget('fg_color')))
            RES['colours'][mode_name] = cols
            check(f'{mode_name}: Step greys the sections ms box (disabled, '
                  'muted text) and leaves steps live',
                  not live('vtk_s_ms') and live('vtk_s_steps') and live('vtk_v_ms')
                  and not live('vtk_v_steps'), cols)
            see(f._vtk_card)
            shot(f'3d_{mode_name}_card_crop', f._vtk_card)
            see(f._vtk_grid)
            shot(f'3d_{mode_name}_matrix_crop', f._vtk_grid)
            # tooltips: <Enter> on the header and a row label
            for text in ('Sect.', 'Obst.', 'Vol.', 'Gauge', 'Peak overpr.',
                         'Products'):
                lbl = find_label(f._vtk_grid, text)
                if lbl is None:
                    check(f'{mode_name}: matrix label {text!r} exists', False)
                    continue
                target = getattr(lbl, '_label', lbl)
                lbl.event_generate('<Enter>')
                pump(0.9)
                tip = getattr(lbl, '_blastlab_tip', None)
                tw = getattr(tip, '_tip', None)
                ok = tw is not None
                txt = None
                if ok:
                    for ch in tw.winfo_children():
                        try:
                            txt = ch.cget('text')
                        except Exception:
                            pass
                    thwnd = user32.GetParent(tw.winfo_id()) or tw.winfo_id()
                    img, pok, rect = capture(thwnd)
                    safe = text.replace('.', '').replace(' ', '_')
                    img.save(os.path.join(SHOTS, f'tk_tip_{mode_name}_{safe}.png'))
                    RES['tips'][f'{mode_name} {text}'] = dict(
                        text=txt, size=(rect[2] - rect[0], rect[3] - rect[1]),
                        pos_rel_root=(rect[0] - root.winfo_rootx(),
                                      rect[1] - root.winfo_rooty()))
                check(f'{mode_name}: <Enter> on {text!r} shows its tooltip',
                      ok and bool(txt), txt)
                lbl.event_generate('<Leave>')
                pump(0.3)
        except Exception:
            RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())
    # back to dark
    try:
        app._mode_switch.select()
        app._toggle_mode()
        pump(1.0)
    except Exception:
        RES['errors'].append(traceback.format_exc())

    # ── plane table ──────────────────────────────────────────────────
    try:
        set_case(Case3D(solver='blastfoam'))
        f = form()
        f.v['vtk_s_on'].set(True)
        pump(0.5)
        pl = f.vtk_planes
        pl.entry_var.set('q, 1'); pl._add(); pump(0.6)
        hint = pl._hint.cget('text')
        check('Tk plane "q, 1" refused with a reason',
              pl.get() == [] and 'x, y or z' in hint, hint)
        see(pl)
        shot('3d_plane_q1_refused_crop', f._vtk_card)
        pl.entry_var.set('y, 1.4'); pl._add(); pump(0.8)
        check('Tk plane "y, 1.4" accepted', pl.get() == [('y', 1.4)], pl.get())
        shot('3d_plane_y14_crop', f._vtk_card)
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # ── native: hidden, restore, saved case ──────────────────────────
    try:
        set_case(Case3D(solver='blastfoam'))
        f = form()
        f.v['vtk_s_on'].set(True); f.v['vtk_v_on'].set(True)
        f._vtk_radios['v'][1].invoke()
        pump(0.6)
        before = (f.v['vtk_fields'].get(), f.v['vtk_s_on'].get(),
                  f.v['vtk_v_on'].get(), f.v['vtk_v_mode'].get())
        save_to['path'] = os.path.join(WORK, 'tk_saved_foam_3d.json')
        app._save_case(); pump(0.3)
        foam = json.load(open(save_to['path'], encoding='utf-8'))
        check('Tk blastFoam save carries both vtk_ keys',
              'vtk_surfaces' in foam and 'vtk_volumes' in foam,
              {k: foam.get(k) for k in ('vtk_surfaces', 'vtk_volumes')})
        app.set_solver('native'); pump(1.2)
        check('Tk native: the card is not gridded (hidden, not greyed)',
              f._vtk_card.winfo_manager() == '', f._vtk_card.winfo_manager())
        scroll(1.0)
        shot('3d_native_bottom')
        scroll(0.55)
        shot('3d_native_mid')
        save_to['path'] = os.path.join(WORK, 'tk_saved_native_3d.json')
        app._save_case(); pump(0.3)
        nat = json.load(open(save_to['path'], encoding='utf-8'))
        check('Tk native save has no vtk_ key',
              not any(k.startswith('vtk_') for k in nat),
              [k for k in nat if k.startswith('vtk')])
        app.set_solver('blastfoam'); pump(1.2)
        after = (f.v['vtk_fields'].get(), f.v['vtk_s_on'].get(),
                 f.v['vtk_v_on'].get(), f.v['vtk_v_mode'].get())
        check('Tk back to blastFoam: card shown, ticks and mode restored',
              f._vtk_card.winfo_manager() == 'grid' and after == before,
              f'{before} -> {after}')
        see(f._vtk_card)
        shot('3d_foam_again_crop', f._vtk_card)
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # ── 2D obstacles family ──────────────────────────────────────────
    try:
        set_case(Case2D(solver='blastfoam'))
        f = form()
        f.v['vtk_s_on'].set(True)
        pump(1.2)
        s1 = strip()
        RES['strips']['2D none'] = s1
        check('Tk 2D Obstacles, none drawn: "nothing to sample"',
              any('nothing to sample' in s for s in s1), s1[:2])
        see(f._vtk_card)
        shot('2d_no_obstacles')
        f.obstacles.entry_var.set('3.0, 3.2, 0.0, 0.5'); f.obstacles._add()
        pump(1.2)
        s2 = strip()
        RES['strips']['2D one'] = s2
        check('Tk 2D: an obstacle added with + clears it',
              not any('nothing to sample' in s for s in s2), s2[:2])
        shot('2d_with_obstacle')
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # ── load with keys, then without ─────────────────────────────────
    try:
        p_with = os.path.join(WORK, 'case_with_vtk.json')
        p_without = os.path.join(WORK, 'case_without_vtk.json')
        if not os.path.exists(p_with):
            save_case(Case3D(solver='blastfoam', vtk_surfaces=dict(
                on=True, mode='step', value=10, fields=['p', 'impulse'],
                obstacle_fields=['pMax'], planes=[['x', 0.5], ['z', 0.3]]),
                vtk_volumes=dict(on=True, mode='time', value=0.5,
                                 fields=['p', 'T'])), p_with)
            save_case(Case3D(solver='blastfoam'), p_without)
        app._open_case(p_with); pump(1.5)
        f = form()
        got = dict(s_on=f.v['vtk_s_on'].get(), s_mode=f.v['vtk_s_mode'].get(),
                   s_steps=f.v['vtk_s_steps'].get(), v_on=f.v['vtk_v_on'].get(),
                   v_mode=f.v['vtk_v_mode'].get(), v_ms=f.v['vtk_v_ms'].get(),
                   planes=f.vtk_planes.get(), m=f.v['vtk_fields'].get(),
                   live={n: live(n) for n in f._vtk_entries})
        check('Tk load with keys: shown, greying follows each mode',
              got['s_on'] and got['s_mode'] == 'step' and got['s_steps'] == '10'
              and got['v_mode'] == 'time' and got['v_ms'] == '0.5'
              and got['planes'] == [('x', 0.5), ('z', 0.3)]
              and got['m'] == {'sections': ['p', 'impulse'],
                               'obstacles': ['pMax'], 'volumes': ['p', 'T']}
              and got['live'] == {'vtk_s_ms': False, 'vtk_s_steps': True,
                                  'vtk_v_ms': True, 'vtk_v_steps': False}, got)
        see(f._vtk_card)
        shot('3d_loaded_with_keys_crop', f._vtk_card)
        app._open_case(p_without); pump(1.5)
        got2 = dict(s_on=f.v['vtk_s_on'].get(), s_mode=f.v['vtk_s_mode'].get(),
                    s_steps=f.v['vtk_s_steps'].get(), s_ms=f.v['vtk_s_ms'].get(),
                    v_on=f.v['vtk_v_on'].get(), v_mode=f.v['vtk_v_mode'].get(),
                    v_ms=f.v['vtk_v_ms'].get(), v_steps=f.v['vtk_v_steps'].get(),
                    planes=f.vtk_planes.get(), m=f.v['vtk_fields'].get(),
                    live={n: live(n) for n in f._vtk_entries})
        check('Tk load without keys: P12 defaults, greying follows Time',
              not got2['s_on'] and not got2['v_on'] and got2['s_mode'] == 'time'
              and got2['v_mode'] == 'time' and got2['s_ms'] in ('1', '1.0')
              and got2['s_steps'] == '25' and got2['planes'] == []
              and not any(got2['m'].values())
              and got2['live'] == {'vtk_s_ms': True, 'vtk_s_steps': False,
                                   'vtk_v_ms': True, 'vtk_v_steps': False}, got2)
        see(f._vtk_card)
        shot('3d_loaded_without_keys_crop', f._vtk_card)
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # ── 1D / 2D cards, both themes ───────────────────────────────────
    try:
        for mode_name in ('dark', 'light'):
            if mode_name == 'light':
                app._mode_switch.deselect(); app._toggle_mode(); pump(1.0)
            for dim, C in ((1, Case1D), (2, Case2D)):
                kw = dict(solver='blastfoam')
                if dim == 2:
                    kw['obstacles'] = [(3.0, 3.2, 0.0, 0.5)]
                set_case(C(**kw))
                f = form()
                for fam, _c in __import__('blastlab.models.fields', fromlist=['x']).VTK_FAMILIES[dim]:
                    f.v[f'vtk_{fam}_on'].set(True)
                f._vtk_radios['v'][1].invoke()
                pump(0.6)
                see(f._vtk_card)
                shot(f'{dim}d_{mode_name}_card_crop', f._vtk_card)
                shot(f'{dim}d_{mode_name}_window')
        app._mode_switch.select(); app._toggle_mode(); pump(0.6)
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    RES['tk_callback_errors'] = errs
    # close through the app's own close handler
    try:
        app._on_close()
    except Exception:
        RES['errors'].append(traceback.format_exc())
    try:
        root.update()
    except Exception:
        pass


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        RES['errors'].append(traceback.format_exc())
    with open(os.path.join(SHOTS, 'tk_results.json'), 'w', encoding='utf-8') as fh:
        json.dump(RES, fh, indent=1, default=str)
    n_fail = sum(1 for c in RES['checks'] if not c['ok'])
    print(f'DONE: {len(RES["checks"])} checks, {n_fail} failed, '
          f'{len(RES["errors"])} harness errors, '
          f'{len(RES.get("tk_callback_errors", []))} Tk callback errors', flush=True)
