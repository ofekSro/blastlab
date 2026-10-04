"""Characterisation: what the Qt Results panel exports, through its own path.

Batch 2026-09-29-gui-results, T0 (GUI-7). Recorded at base `c8a04d2`,
before any GUI-7 change, and committed alone: this is the "pre-batch
export" of docs/gui-redesign-plan.md section 10 ("exported CSV/TSV are
byte-identical to before for the same result"). Golden:
`char_golden/ui_results_exports.json`.

What it drives: the REAL `ui.results_panel.ResultsPanel` (offscreen), fed
the native 1D and 2D results of `test_char_exports.result('1d' / '2d')`
through `p.add_result(label, dim, res)`, every export through the panel's
own `p.export(kind, threaded=False)`. Dialogs are replaced exactly as
`test_char_exports.qt_export` does (`save_file` / `pick_dir` recorders, the
`gif_name` rule, `os.startfile` -> `Opened`), plus `show_error`.

Per case / kind / variant it records the dialog calls, the return value,
the log lines, the errors, what was opened, `p.export_opts()` (the dict
the animation export receives) and every written file through
`test_char_exports.describe_dir`.

Variants: `plain` for every kind in `exports.KINDS` (vtk on its refusal
path); `titled` (title `Char title`, Show mesh on) for report, pngs, gif;
and for gif also `frame` (scale = each frame) and `manual` (0, 50 kPa).

The panel state is set by ONE function, `drive()`, which is not edited
after T0. GUI-7 T6 adds `drive_visible()`, which must reproduce the same
golden through the new visible controls.

Run:  cd blastlab/tests && python test_ui_char_results_exports.py [--update]
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import char_common as cc                                     # noqa: E402
import test_char_exports as ce                               # noqa: E402

from blastlab.ui.testing import ensure_qapp, pump            # noqa: E402

GOLDEN = 'ui_results_exports.json'
#: the kinds whose written files must equal `exports_qt.json`'s
SAME_AS_QT = ('summary', 'tsv', 'fieldcsv', 'profile')
#: the extra variants of the Animation export: (scale, clim)
GIF_SCALES = {'frame': ('frame', None), 'manual': ('manual', (0.0, 50.0))}

_ERRORS = []


def _hook(etype, value, tb):
    """An exception raised in a Qt slot would otherwise print and be
    lost; record it, and let `main` fail on it."""
    import traceback
    _ERRORS.append(''.join(traceback.format_exception(etype, value, tb)))
    sys.__excepthook__(etype, value, tb)


def drive(p, title=None, mesh=False, scale=None, clim=None):
    """Set the panel state an export reads, through the base widgets:
    the title box, Fields' Show mesh, and Animation's colour scale and
    range. `scale=None` keeps the result's recorded scale."""
    from blastlab.core.constants import ANIM_SCALE_LABELS
    p.title_box.setText(title or '')
    p.fields.show_mesh.setChecked(bool(mesh))
    if clim is not None:
        p.anim.min_box.setText(f'{float(clim[0]):g}')
        p.anim.max_box.setText(f'{float(clim[1]):g}')
    if scale is not None:
        p.anim.scale_sel.setCurrentText(ANIM_SCALE_LABELS[scale])
    pump(5)


def drive_visible(p, title=None, mesh=False, scale=None, clim=None):
    """The same state as `drive()`, set through the Field view's VISIBLE
    controls (GUI-7 T6): the title box, a click on Show mesh, a click on
    the Colours control and the Min / Max boxes (typed, then Enter).
    `scale=None` keeps the result's recorded scale. A 1D result shows its
    profiles and no Field controls; the same clicks and edits are sent to
    them there (the range is then the overpressure one, the export's)."""
    from blastlab.ui.results_field import SCALE_LABEL
    fv = p.field_view
    p.title_box.setText(title or '')
    if fv.show_mesh.isChecked() != bool(mesh):
        fv.show_mesh.click()
    if scale is not None:
        fv.scale_seg._btns[SCALE_LABEL[scale]].click()
    if clim is not None:
        fv.min_edit.setText(f'{float(clim[0]):g}')
        fv.max_edit.setText(f'{float(clim[1]):g}')
        fv.max_edit.editingFinished.emit()
    pump(5)


def plan():
    """(case key, kind, variant, drive kwargs) for every export pinned."""
    from blastlab.ui.exports import KINDS
    out = []
    for key in ('1d', '2d'):
        for kind in KINDS:
            out.append((key, kind, 'plain', {}))
        for kind in ce.TITLED_KINDS:
            out.append((key, kind, 'titled',
                        dict(title=ce.TITLE, mesh=True)))
        for variant, (scale, clim) in GIF_SCALES.items():
            out.append((key, 'gif', variant, dict(scale=scale, clim=clim)))
    return out


def panel_export(key, kind, variant, kw, driver=drive):
    """Build a fresh panel holding the result `key`, set its state with
    `driver`, export `kind` through `p.export(kind, threaded=False)` and
    describe everything that happened."""
    from blastlab.ui import dialogs
    from blastlab.ui.results_panel import ResultsPanel
    res = ce.result(key)
    label = ce.NAMES[key][1]
    out = tempfile.mkdtemp(prefix='blastlab_char_uires_')
    calls, log, errors = [], [], []

    def save_file(title, filters='All files (*.*)', parent=None, start='',
                  default_suffix=None):
        calls.append(['save_file', title, filters, start, default_suffix])
        name = ce.gif_name(start) if kind == 'gif' else start
        return os.path.join(out, name)

    def pick_dir(title, parent=None, start=''):
        calls.append(['pick_dir', title, start])
        return out

    def show_error(title, text, parent=None):
        errors.append([title, str(text)])

    real = dialogs.save_file, dialogs.pick_dir, dialogs.show_error
    dialogs.save_file, dialogs.pick_dir = save_file, pick_dir
    dialogs.show_error = show_error
    p = ResultsPanel(log_fn=log.append)
    try:
        p.resize(1200, 800)
        p.add_result(label, int(key[0]), res)
        pump(10)
        driver(p, **kw)
        opts = p.export_opts()
        del log[:]
        with ce.Opened() as opened:
            ret = p.export(kind, threaded=False)
            pump(20)
        got = dict(dialogs=calls, returned=ret, log=log, errors=errors,
                   opened=opened.paths, export_opts=opts,
                   files=ce.describe_dir(out))
        return ce.scrub(got, out)
    finally:
        dialogs.save_file, dialogs.pick_dir, dialogs.show_error = real
        p.shutdown()
        p.deleteLater()
        pump(5)
        shutil.rmtree(out, ignore_errors=True)


def collect(driver=drive):
    return {f'{key}/{kind}/{variant}': panel_export(key, kind, variant, kw,
                                                    driver)
            for key, kind, variant, kw in plan()}


_GOT = {}


def test_panel_exports():
    ensure_qapp()
    _GOT.update(collect(drive))
    assert not _ERRORS, 'uncaught exception(s):\n' + '\n'.join(_ERRORS)
    cc.check_json(GOLDEN, _GOT)


def test_panel_exports_visible():
    """GUI-7 T6: the same exports with the state set through the visible
    controls give the SAME golden, recorded at base (never rewritten
    from this driver)."""
    ensure_qapp()
    got = collect(drive_visible)
    assert not _ERRORS, 'uncaught exception(s):\n' + '\n'.join(_ERRORS)
    want = cc._read_text(GOLDEN)
    text = cc.dumps(got)
    if text != want:
        import difflib
        diff = ''.join(list(difflib.unified_diff(
            want.splitlines(True), text.splitlines(True),
            'golden/' + GOLDEN, 'drive_visible'))[:60])
        raise AssertionError(f'drive_visible differs from the golden:\n'
                             f'{diff}')


def test_same_bytes_as_exports_qt():
    """The data files written through the panel are the ones
    `test_char_exports` pins through `ui.exports.export` (so the two
    goldens cannot drift apart)."""
    qt = cc.load_json('exports_qt.json')
    mine = _GOT or cc.load_json(GOLDEN)
    bad = []
    for key in ('1d', '2d'):
        for kind in SAME_AS_QT:
            k = f'{key}/{kind}/plain'
            if cc.plain(mine[k]['files']) != qt[k]['files']:
                bad.append(k)
    assert not bad, f'files differ from exports_qt.json: {bad}'


def main():
    sys.excepthook = _hook
    tests = [test_panel_exports, test_same_bytes_as_exports_qt]
    if '--update' not in sys.argv[1:]:
        # never a writer: it must reproduce the golden `drive` wrote
        tests.insert(1, test_panel_exports_visible)
    return cc.run_main('CHAR UI RESULTS EXPORTS', tests)


if __name__ == '__main__':
    sys.exit(main())
