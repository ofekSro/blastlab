"""Characterisation: what the Tk Results panel shows, read from Result.meta.

docs/ARCHITECTURE_REVIEW.md section 5, Phase 8 (finding F3). The Tk twin
of `test_ui_char_results_meta.py`, pinned BEFORE `gui/results_panel.py`'s
literal `meta[...]` reads moved behind the accessors of `models/meta.py`.
Golden: `char_golden/gui_results_meta.json`. The Tk GUI is the permanent
way back (CLAUDE.md section 9); this golden is what proves Phase 8 left
its screens as they were.

For every result of `char_meta_results.fixtures()` through the REAL
`gui.results_panel.ResultsPanel` (customtkinter, withdrawn root):

  * Fields: `_draw_field` for every field the selector offers and every
    snapshot - the figure on the canvas (titles, labels, the exact bytes
    of every image/mesh array);
  * Gauges: `_draw_gauges` - the figure and the summary table rows;
  * Animation: `_setup_anim` - the plane caption, the mask, the slider,
    and `_show_frame` at the first, middle and last frame (title, the
    mesh's array);
  * missing keys: for the 1D/2D/3D native and blastFoam-shaped results,
    each meta key removed in turn - what `_draw_field` (every field but
    the slow isosurface, last snapshot), `_draw_gauges` and `_setup_anim`
    do (a description hash, or the exact exception).

Script only - it builds Tk widgets (conftest.py keeps `test_gui_*.py` out
of pytest).

Run:  cd blastlab/tests && python test_gui_char_results_meta.py [--update]
"""
import sys

import char_common as cc
import char_meta_results as cm

import customtkinter as ctk                                  # noqa: E402

from blastlab.gui import results_panel as rp                 # noqa: E402

MISSING = ('native_1d', 'native_2d', 'native_3d', 'foam_1d', 'foam_2d',
           'foam_3d')


def _fields(panel):
    return list(panel.field_sel.cget('values'))


def _tree(panel):
    tbl = panel.summary_table
    return [list(tbl.item(i, 'values')) for i in tbl.get_children()]


def anim_state(panel):
    out = dict(plane=getattr(panel, '_anim_plane', None),
               solid=cm.value(getattr(panel, '_anim_solid', None)),
               ready=panel._anim_mesh is not None,
               slider_to=cm.value(panel.frame_slider.cget('to')),
               figure=cm.figure(panel.anim_canvas.figure), frames={})
    if panel._anim_mesh is None:
        out['solid'] = None
        return out
    n = int(round(float(panel.frame_slider.cget('to')))) + 1
    for k in sorted({0, n // 2, n - 1}):
        panel._show_frame(k)
        out['frames'][str(k)] = dict(
            title=panel._anim_title.get_text(),
            mesh=cm.value(panel._anim_mesh.get_array()))
    return out


def fields_state(panel, res):
    out = {}
    for field in _fields(panel):
        for snap in res.snapshots:
            panel.snap_sel.set(snap)
            panel.field_sel.set(field)
            out[f'{field} @ {snap}'] = cm.outcome(
                lambda: (panel._draw_field(),
                         cm.figure(panel.field_canvas.figure))[1])
    return out


def missing_keys(panel, name, dim, res):
    out = {}
    snap = list(res.snapshots)[-1]
    for key in sorted(res.meta):
        r = cm.without(res, key)
        label = f'{name} -{key}'
        row = {'add_result': cm.short(cm.outcome(panel.add_result, label,
                                                 dim, r))}
        panel.snap_sel.set(snap)
        for field in _fields(panel):
            if field == 'isosurface':
                continue
            panel.field_sel.set(field)
            row[f'field {field}'] = cm.short(cm.outcome(
                lambda: (panel._draw_field(),
                         cm.figure(panel.field_canvas.figure))[1]))
        row['gauges'] = cm.short(cm.outcome(
            lambda: (panel._draw_gauges(),
                     dict(figure=cm.figure(panel.gauge_canvas.figure),
                          rows=_tree(panel)))[1]))
        row['anim'] = cm.short(cm.outcome(panel._setup_anim))
        row['anim shown'] = cm.short({'ok': dict(
            plane=getattr(panel, '_anim_plane', None),
            ready=panel._anim_mesh is not None,
            title=(panel._anim_title.get_text()
                   if panel._anim_title is not None else None),
            figure=cm.figure(panel.anim_canvas.figure))})
        out[key] = row
        panel._remove_current()
    return out


def collect():
    root = ctk.CTk()
    root.withdraw()
    log = []
    got = {}
    try:
        panel = rp.ResultsPanel(root, log_fn=log.append)
        fx = cm.fixtures()
        for name, dim, res in fx:
            panel.add_result(name, dim, res)
            panel.update_idletasks()
            got[name] = dict(
                fields_offered=_fields(panel),
                anim=anim_state(panel),
                gauges=dict(figure=cm.value(
                    cm.outcome(lambda: (panel._draw_gauges(), cm.figure(
                        panel.gauge_canvas.figure))[1])),
                    rows=_tree(panel)),
                fields=fields_state(panel, res))
        for name, dim, res in fx:
            if name in MISSING:
                got[f'missing/{name}'] = missing_keys(panel, name, dim, res)
        panel.destroy()
        return got
    finally:
        root.destroy()


def test_gui_results_meta():
    cc.check_json('gui_results_meta.json', collect())


def main():
    return cc.run_main('CHAR GUI RESULTS META', [test_gui_results_meta])


if __name__ == '__main__':
    sys.exit(main())
