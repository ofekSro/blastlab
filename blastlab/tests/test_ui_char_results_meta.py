"""Characterisation: what the Qt Results views show, read from Result.meta.

docs/ARCHITECTURE_REVIEW.md section 5, Phase 8 (finding F3). Pinned
BEFORE the Qt panels' literal `meta[...]` reads moved behind the
accessors of `models/meta.py`, so the move is proven to change nothing
on screen. Golden: `char_golden/ui_results_meta.json`.

For every result of `char_meta_results.fixtures()` (native 1D/2D/3D, the
blastFoam-shaped ones, recorded colour scales, the other slice axes, no
or empty frames) through the REAL `ui.results_panel.ResultsPanel`:

  * Fields: for every field the selector offers and every snapshot,
    `results_fields.select_field` (arrays by exact-byte hash), the page
    the view shows, its title and hint, and the figure of the matplotlib
    page (1D profiles, 3D isosurface);
  * Gauges: the figure and the summary table;
  * Animation: `results_anim.plane_geometry`, the colour-scale widgets as
    set from the recorded scale, and title / scale used / clip / range at
    the first, middle and last frame;
  * missing keys: for the 1D/2D/3D native and blastFoam-shaped results,
    each meta key removed in turn - what `select_field` (every field, last
    snapshot), `plane_geometry`, `AnimView.set_result`, the 1D profile
    figure and the Gauges figure do (a description hash, or the exact
    exception).

Script only - it builds Qt widgets (conftest.py keeps `test_ui_*.py` out
of pytest). Headless: offscreen Qt, Agg, a private settings file.

Run:  cd blastlab/tests && python test_ui_char_results_meta.py [--update]
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import char_common as cc                                     # noqa: E402
import char_meta_results as cm                               # noqa: E402

from blastlab.ui.testing import ensure_qapp, pump            # noqa: E402

MISSING = ('native_1d', 'native_2d', 'native_3d', 'foam_1d', 'foam_2d',
           'foam_3d')


def fields_view(p, ent):
    from blastlab.ui import results_fields as RF
    f = p.fields
    out = {}
    snaps = list(ent.result.snapshots)
    for field in RF.field_options(ent.result, ent.dim):
        for snap in snaps:
            f.snap_sel.setCurrentText(snap)
            f.field_sel.setCurrentText(field)
            f.redraw()
            pump(2)
            page = f.page()
            out[f'{field} @ {snap}'] = dict(
                select=cm.outcome(RF.select_field, ent.result, ent.dim,
                                  snap, field, p.title_extra()),
                page=page, title=f.title() if page == 'image' else None,
                hint=f.hint.text() if page == 'empty' else None,
                figure=(cm.figure(f.canvas.figure) if page == 'figure'
                        else None))
    return out


def gauges_view(p):
    g = p.gauges
    g.redraw()
    return dict(figure=cm.figure(g.canvas.figure), rows=g.rows(),
                field=g.field())


def anim_view(p, ent):
    from blastlab.ui import results_anim as RA
    a = p.anim
    out = dict(geometry=(cm.outcome(RA.plane_geometry, ent.result.meta)
                         if ent.dim != 1 else None),
               hint=a.hint.text() if a.hint.isVisibleTo(a) else None,
               scale_label=a.scale_sel.currentText(),
               min_box=a.min_box.text(), max_box=a.max_box.text(),
               manual_visible=a.manual_visible(),
               slider_max=a.slider.maximum(),
               play_enabled=a.play_btn.isEnabled(), frames={})
    n = a.slider.maximum() + 1 if a.play_btn.isEnabled() else 0
    for k in sorted({0, n // 2, max(0, n - 1)}) if n else ():
        a.show_frame(k)
        out['frames'][str(k)] = dict(
            title=a.title(), scale_used=a.scale_used(),
            clipped=a.clipped(), clim=cm.value(a._clim))
    return out


def missing_keys(p, name, dim, res):
    """Every meta key removed in turn."""
    from blastlab.ui import results_anim as RA
    from blastlab.ui import results_fields as RF
    from blastlab.ui.results_panel import ResultEntry
    out = {}
    snap = list(res.snapshots)[-1]
    fields = RF.field_options(res, dim)
    for key in sorted(res.meta):
        r = cm.without(res, key)
        ent = ResultEntry(f'{name} -{key}', dim, r)
        row = {}
        for field in fields:
            row[f'select {field}'] = cm.short(cm.outcome(
                RF.select_field, r, dim, snap, field, None))
        if dim == 1:
            p.fields.set_result(ent)
            pump(2)
            row['fields page'] = p.fields.page()
            row['fields'] = cm.short({'ok': dict(
                hint=p.fields.hint.text(),
                figure=cm.figure(p.fields.canvas.figure))})
        else:
            row['plane_geometry'] = cm.short(cm.outcome(RA.plane_geometry,
                                                        r.meta))
        p.gauges.clear()
        p.gauges.set_result(ent)
        row['gauges'] = cm.short({'ok': dict(
            figure=cm.figure(p.gauges.canvas.figure), rows=p.gauges.rows())})
        p.anim.placeholder('')
        row['anim'] = cm.short(cm.outcome(p.anim.set_result, ent))
        row['anim shown'] = cm.short({'ok': dict(
            hint=p.anim.hint.text(), title=p.anim.title(),
            scale=p.anim.scale_sel.currentText(),
            slider=p.anim.slider.maximum())})
        out[key] = row
    p.fields.clear()
    p.gauges.clear()
    p.anim.placeholder('')
    return out


def collect():
    ensure_qapp()
    from test_ui_view3d_host import FakeLink
    from blastlab.ui.results_panel import ResultsPanel
    log = []
    p = ResultsPanel(viewer_link=FakeLink(), log_fn=log.append)
    p.resize(1280, 840)
    p.show()
    pump(20)
    got = {}
    try:
        fx = cm.fixtures()
        for name, dim, res in fx:
            ent = p.add_result(name, dim, res)
            pump(5)
            got[name] = dict(anim=anim_view(p, ent), gauges=gauges_view(p),
                             fields=fields_view(p, ent))
        for name, dim, res in fx:
            if name in MISSING:
                got[f'missing/{name}'] = missing_keys(p, name, dim, res)
    finally:
        p.close()
        p.deleteLater()
        pump(5)
    return got


def test_ui_results_meta():
    cc.check_json('ui_results_meta.json', collect())


def main():
    return cc.run_main('CHAR UI RESULTS META', [test_ui_results_meta])


if __name__ == '__main__':
    sys.exit(main())
