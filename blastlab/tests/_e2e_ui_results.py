"""GUI-7 end to end: the 03 Results screen on real native results
(batch docs/batches/2026-09-29-gui-results.md, T7; plan section 10 GUI-7).

What it does, through the real MainWindow on the real platform (CLAUDE.md
8.7), with throwaway settings and a private runs folder (`use_model`):

- runs three tiny native cases through Run: the Phase 0 1D case, the
  Phase 0 2D axisymmetric case with `record_frames = 12`, and the same 2D
  case planar (the Gauges view without Z);
- on the 1D and the 2D result walks the three views:
  - Field: every field, the time bar played for 1 s, a hover with the
    real pointer (`QTest.mouseMove` on the map's viewport), This frame
    .png (threaded, busy strip, the file written);
  - Gauges: a row click, Copy table - the REAL clipboard must hold the
    text built here from `table_rows` and Z;
  - 3D: the placeholder (no scene) for 1D and 2D;
  and asserts no uncaught exception and every page drawn;
- exports Summary, Gauge traces, Field snapshot and Profile of the real 1D
  and 2D results through the new buttons (threaded, as a click does) and,
  with `--base-worktree PATH` (a `git worktree` of the base `c8a04d2`),
  compares every file with `ui.exports.export(kind, ent, threaded=False)`
  run there on the SAME Result objects (pickled; this file copies itself
  into the worktree and runs with `--base-export`). Text files by
  sha256; an .npz by the bytes of every array (numpy stamps the zip
  members with the time of writing, so its own sha256 changes from run
  to run);
- with `--with-3d`, a tiny native 3D result (the Phase 0 3D case, 64 k
  cells) in the embedded viewer (check free memory first: the viewer
  child is about 0.4 GB);
- with `--shots DIR`, the screenshots of batch T7 in dark and light at
  1100 x 720 and 1600 x 1000, and `measure.json` with the geometry the
  report states.

Run:  cd blastlab/tests && python -u _e2e_ui_results.py
      [--shots DIR] [--with-3d] [--base-worktree PATH]
Base side (internal): --base-export PICKLE DIM LABEL OUTDIR
"""
import hashlib
import json
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

#: the four data exports compared byte for byte with the base
DATA_KINDS = ('summary', 'tsv', 'fieldcsv', 'profile')

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''), flush=True)
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def describe(out):
    """{relative path: sha256} of every file under `out`; an .npz as
    {array: [dtype, shape, sha256 of its bytes]}."""
    import numpy as np
    got = {}
    for base, _dirs, files in os.walk(out):
        for f in sorted(files):
            path = os.path.join(base, f)
            rel = os.path.relpath(path, out).replace(os.sep, '/')
            if f.endswith('.npz'):
                with np.load(path) as z:
                    got[rel] = {k: [str(z[k].dtype), list(z[k].shape),
                                    hashlib.sha256(np.ascontiguousarray(
                                        z[k]).tobytes()).hexdigest()]
                                for k in sorted(z.files)}
            else:
                with open(path, 'rb') as fh:
                    got[rel] = hashlib.sha256(fh.read()).hexdigest()
    return got


def to_front(win):
    """Put the window above the others (Win32 z-order, no focus needed),
    so the real pointer and a screen grab meet it, not what covers it."""
    import ctypes
    hwnd = ctypes.c_void_p(int(win.winId()))
    swp = 0x0001 | 0x0002 | 0x0010            # NOSIZE | NOMOVE | NOACTIVATE
    user32 = ctypes.windll.user32
    user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, swp)   # TOP
    user32.SetWindowPos(hwnd, ctypes.c_void_p(-2), 0, 0, 0, 0, swp)   # NOTOP
    win.raise_()


def pointer_to(glw, plot, x, y):
    """Move the real pointer onto the data point (x, y) of `plot` in the
    view `glw` (twice, from one cell away, so a move event happens)."""
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtTest import QTest
    from blastlab.ui.testing import pump
    for dx in (12, 0):
        vpt = glw.mapFromScene(plot.vb.mapViewToScene(QPointF(x, y)))
        QTest.mouseMove(glw.viewport(), QPoint(int(vpt.x()) + dx,
                                               int(vpt.y())))
        pump(150)


def patch_dialogs(out, record=None):
    """save_file / pick_dir answer inside `out` (the suggested file name
    kept); every other modal becomes a recorder. Returns the originals."""
    from blastlab.ui import dialogs
    real = {n: getattr(dialogs, n) for n in
            ('save_file', 'pick_dir', 'show_error', 'warn', 'show_info',
             'ask_yes_no') if hasattr(dialogs, n)}
    record = record if record is not None else []

    def save_file(*a, **k):
        start = a[3] if len(a) > 3 else k.get('start', '')
        record.append(('save_file', a[0] if a else k.get('title')))
        return os.path.join(out, os.path.basename(start) or 'x')

    def pick_dir(*a, **k):
        record.append(('pick_dir', a[0] if a else k.get('title')))
        return out
    dialogs.save_file = save_file
    dialogs.pick_dir = pick_dir
    for n in ('show_error', 'warn', 'show_info'):
        setattr(dialogs, n, lambda title, text, parent=None, _n=n:
                record.append((_n, title, str(text))))
    dialogs.ask_yes_no = lambda *a, **k: record.append(('ask', a[:1])) \
        or True
    return real


def restore_dialogs(real):
    from blastlab.ui import dialogs
    for n, fn in real.items():
        setattr(dialogs, n, fn)


# ── the base side: run inside a worktree of c8a04d2 ──────────────────────
def base_export(pickle_path, dim, label, outdir):
    """`ui.exports.export(kind, ent, threaded=False)` of the base code on
    the pickled Result, one folder per kind; prints describe() as JSON."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from blastlab.ui import exports
    from blastlab.ui.results_panel import ResultEntry
    with open(pickle_path, 'rb') as f:
        res = pickle.load(f)
    ent = ResultEntry(label, int(dim), res)
    out = {}
    for kind in DATA_KINDS:
        d = os.path.join(outdir, kind)
        os.makedirs(d, exist_ok=True)
        real = patch_dialogs(d)
        try:
            exports.export(kind, ent, threaded=False, log=lambda *_: None)
        finally:
            restore_dialogs(real)
        out[kind] = describe(d)
    print('JSON ' + json.dumps(out))
    return 0


# ── the cases ────────────────────────────────────────────────────────────
def cases():
    import dataclasses
    from test_char_native_api import CASES
    c1 = dataclasses.replace(CASES['1d'])
    c2 = dataclasses.replace(CASES['2d'], record_frames=12)
    # planar, the burst clear of Wall 1 (x 0.7-0.9, y 0.2-0.5) and near
    # both gauges, so the wave reaches them before a terminate side
    cp = dataclasses.replace(CASES['2d'], geometry='planar',
                             center=(0.25, 0.6))
    return [('e2e_1d', 1, c1), ('e2e_2d', 2, c2), ('e2e_planar', 2, cp)]


def main():
    shots = _arg('--shots')
    with_3d = '--with-3d' in sys.argv
    base_wt = _arg('--base-worktree')
    os.environ.pop('QT_QPA_PLATFORM', None)     # a real platform
    os.environ.setdefault('MPLBACKEND', 'Agg')
    os.environ.setdefault('BLASTLAB_SETTINGS', os.path.join(
        tempfile.mkdtemp(prefix='blastlab_e2e_results_'), 'settings.json'))
    from blastlab.ui.testing import ensure_qapp, pump, use_model
    app = ensure_qapp(offscreen=False)
    if app.platformName() == 'offscreen':
        print('SKIP: a real platform is needed')
        return 0
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from blastlab.output import gauge_summary
    from blastlab.ui import run_controller
    from blastlab.ui import scaled_distance as sd
    from blastlab.ui.app import MainWindow
    from blastlab.ui.exports import summary_rows
    from blastlab.ui.results_fields import field_options

    crashes = []

    def hook(*a):
        crashes.append(''.join(traceback.format_exception(*a)))
        sys.__excepthook__(*a)
    sys.excepthook = hook
    # no revolved 3D view during the 2D runs: no viewer child until the
    # 3D part asks for one (8 GB PC, see _e2e_ui_run_finish)
    run_controller.pyvista_available = lambda: False
    scratch = tempfile.mkdtemp(prefix='blastlab_e2e_results_work_')
    modal = []
    real_dialogs = patch_dialogs(os.path.join(scratch, 'dialog'), modal)
    os.makedirs(os.path.join(scratch, 'dialog'), exist_ok=True)

    win = MainWindow()
    win.set_solver('native')
    win.resize(1600, 1000)
    win.show()
    pump(400)
    rs = win.results
    fv = rs.field_view
    ents = {}

    print('\nR0: three tiny native runs through the Run screen', flush=True)
    for name, dim, case in cases():
        use_model(win, name)
        win.setup.set_case(case)
        win._schedule_validate()
        pump(400)
        n0 = len(rs.entries())
        t0 = time.monotonic()
        win._run_single()
        while (win.ctrl.running or len(rs.entries()) == n0) \
                and time.monotonic() - t0 < 600:
            pump(50)
        pump(300)
        ok = len(rs.entries()) == n0 + 1
        check(f'{name}: the run finished and landed in Results '
              f'({time.monotonic() - t0:.0f} s)', ok)
        if ok:
            ents[name] = rs.entries()[-1]
    if len(ents) < 3:
        print('FAILED: a run did not finish')
        return 1
    win._show('results')
    pump(300)

    def select(ent):
        rs.sel.setCurrentIndex(rs.entries().index(ent))
        pump(150)

    def fields_drawn():
        if fv.page() == 'replay':
            return rs.anim.image is not None
        return rs.fields.page() in ('image', 'figure')

    print('\nR1: the three views on the native 1D and 2D results',
          flush=True)
    for name in ('e2e_1d', 'e2e_2d'):
        ent = ents[name]
        res, dim = ent.result, ent.dim
        select(ent)
        rs.show_view('Field')
        pump(200)
        seen = []
        if dim == 1:
            seen.append(rs.fields.field())
            check(f'{name}: Field shows the profiles (a figure)',
                  rs.fields.page() == 'figure' and fields_drawn())
            # GUI-11 T19 (F17, D214): at 1100 x 720 the short on-screen
            # title lies inside the canvas (the screen grab is saved)
            win.resize(1100, 720)
            pump(600)
            cv = rs.fields.canvas._canvas
            cv.draw()
            ax0 = rs.fields.canvas.figure.axes[0]
            tb = ax0.title.get_window_extent(renderer=cv.get_renderer())
            cw, chh = cv.get_width_height()
            check(f'{name}: at 1100 x 720 the title '
                  f'{ax0.get_title()!r} lies inside the canvas',
                  ax0.get_title().startswith('1D spherical · ')
                  and tb.x0 >= -0.5 and tb.x1 <= cw + 0.5
                  and tb.y1 <= chh + 0.5,
                  f'x {tb.x0:.0f}..{tb.x1:.0f} in {cw}, top {tb.y1:.0f} '
                  f'of {chh}')
            to_front(win)
            pump(300)
            shot = os.path.join(scratch, 'gui11-1d-title-1100x720.png')
            app.primaryScreen().grabWindow(int(win.winId())).save(shot)
            print(f'    screen grab {shot}', flush=True)
            win.resize(1600, 1000)
            pump(400)
        else:
            for base in fv.field_seg.values():
                fv.field_seg._btns[base].click()
                pump(250)
                seen.append(rs.fields.field())
                check(f'{name}: Field / {base} drawn', fields_drawn(),
                      f'{fv.page()} {rs.fields.page()}')
            check(f'{name}: every field of field_options visited',
                  sorted(seen) == sorted(field_options(res, dim)),
                  str(seen))
            fv.field_seg._btns['Overpressure'].click()
            pump(200)
            k0 = rs.anim.frame()
            fv.start_play()
            pump(1000)
            fv.stop_play()
            check(f'{name}: the time bar played for 1 s (frames moved)',
                  fv.mode() == 'frames' and rs.anim.frame() != k0
                  and fv.timebar.slider.value() == rs.anim.frame(),
                  f'{k0} -> {rs.anim.frame()}')
            # the real pointer over the replay's map
            to_front(win)
            pump(300)
            img = rs.anim.image
            pointer_to(rs.anim.glw, rs.anim.plot,
                       (img.xf[5] + img.xf[6]) / 2,
                       (img.yf[5] + img.yf[6]) / 2)
            check(f'{name}: a hover with the real pointer shows the '
                  f'readout', fv.hover_visible('anim')
                  and 'overpressure' in fv.hover_text(),
                  repr(fv.hover_text()))
            before = set(os.listdir(os.path.join(scratch, 'dialog')))
            target = fv.save_frame_png()
            busy = fv.timebar.busy()
            for _ in range(300):
                pump(20)
                if not fv.timebar.busy():
                    break
            check(f'{name}: This frame .png (busy strip, then the file)',
                  busy and target and os.path.getsize(target) > 5000
                  and os.path.basename(target) not in before,
                  str(target))
        rs.show_view('Gauges')
        pump(300)
        g = rs.gauges
        rows = gauge_summary.table_rows(summary_rows(res))
        check(f'{name}: Gauges drawn, one row per gauge',
              g.page() == 'plot' and len(g.order()) == len(rows))
        if g.table.rowCount() > 1:
            rect = g.table.visualRect(g.table.model().index(1, 2))
            QTest.mouseClick(g.table.viewport(), Qt.LeftButton,
                             Qt.NoModifier, rect.center())
            pump(150)
            check(f'{name}: a row click selects that gauge',
                  g.selected() == g.order()[1]
                  and g.fill_span() is not None)
        # the text built here: headers, then table_rows + Z by row
        zs = None
        if g.z_shown():
            case = sd.case_from_meta(res.meta, dim, res.gauges)
            ent_pts = sd.gauge_points(case)
            zs = {n: sd.scaled_distance(case, ent_pts[n - 1])
                  for n in range(1, len(rows) + 1)}
        from blastlab.ui import results_gauges as RG
        heads = [h for i, h in enumerate(RG.HEADERS) if zs or i != 1]
        lines = ['\t'.join(heads)]
        for n in g.order():
            lines.append('\t'.join([f'G{n}'] + (
                [f'{zs[n]:.2f}'] if zs else []) + list(rows[n - 1][1:])))
        want = '\n'.join(lines)
        QApplication.clipboard().setText('sentinel')
        g.copy_btn.click()
        pump(100)
        got = QApplication.clipboard().text()
        check(f'{name}: Copy table puts exactly the text built here on the '
              f'real clipboard', got == want, repr(got[:100]))
        print('    clipboard: ' + repr(got), flush=True)
        rs.show_view('3D')
        pump(300)
        host = rs.view3d
        scene = getattr(host, 'has_scene', False)
        scene = scene() if callable(scene) else scene
        check(f'{name}: 3D shows its placeholder (no scene)',
              rs.stack.currentWidget() is host and not scene)
        rs.show_view('Field')
        pump(100)

    print('\nR2: the data exports through the new buttons', flush=True)
    head = {}
    for name in ('e2e_1d', 'e2e_2d'):
        ent = ents[name]
        select(ent)
        head[name] = {}
        for kind in DATA_KINDS:
            d = os.path.join(scratch, 'head', name, kind)
            os.makedirs(d, exist_ok=True)
            real = patch_dialogs(d, modal)
            try:
                rs._export_btns[kind].click()
                for _ in range(600):
                    pump(20)
                    if not rs.busy_kinds():
                        break
            finally:
                restore_dialogs(real)
            head[name][kind] = describe(d)
            check(f'{name}: {kind} written through its button',
                  bool(head[name][kind]), str(list(head[name][kind])))
        with open(os.path.join(scratch, f'{name}.pickle'), 'wb') as f:
            pickle.dump(ent.result, f)
    if base_wt:
        dst = os.path.join(base_wt, 'blastlab', 'tests',
                           os.path.basename(__file__))
        shutil.copy(__file__, dst)
        for name in ('e2e_1d', 'e2e_2d'):
            ent = ents[name]
            out = os.path.join(scratch, 'base', name)
            p = subprocess.run(
                [sys.executable, '-u', dst, '--base-export',
                 os.path.join(scratch, f'{name}.pickle'), str(ent.dim),
                 ent.label, out], capture_output=True, text=True,
                cwd=os.path.dirname(dst), timeout=600)
            line = [s for s in p.stdout.splitlines() if s.startswith('JSON ')]
            base = json.loads(line[-1][5:]) if line else None
            if base is None:
                print(p.stdout[-2000:], p.stderr[-2000:])
            for kind in DATA_KINDS:
                check(f'{name}: {kind} equals the base export of the same '
                      f'Result, byte for byte',
                      base is not None and base[kind] == head[name][kind]
                      and bool(base[kind]),
                      f'{sorted(base[kind]) if base else None}')
            print(f'    {name}: ' + json.dumps(head[name]), flush=True)
        os.remove(dst)
    else:
        print('    (no --base-worktree: the base comparison is skipped)')

    if with_3d:
        print('\nR3: a native 3D result in the embedded viewer', flush=True)
        from test_char_native_api import CASES
        from blastlab.solvers import get_solver
        from blastlab.solvers.hooks import RunHooks
        r3 = get_solver(3, 'native')(CASES['3d'], RunHooks())
        e3 = rs.add_result('e2e_3d (3D)', 3, r3)
        ents['e2e_3d'] = e3
        pump(200)
        rs.open_3d()
        host = rs.view3d
        for _ in range(9000):
            pump(10)
            if host._hwnd and host._container is not None:
                break
        check('3D: the viewer child reports a window',
              bool(host._hwnd), str(host._hwnd))
        pump(1500)

    if shots:
        take_shots(app, win, ents, shots, scratch)

    print('\nR9: nothing raised, no modal', flush=True)
    check('no uncaught exception', not crashes,
          crashes[0][-600:] if crashes else '')
    check('no error dialog', not [m for m in modal
                                  if m[0] in ('show_error', 'warn')],
          str(modal[:3]))
    restore_dialogs(real_dialogs)
    link = win.viewer_link
    child = getattr(link._proc, '_proc', None) if link._proc else None
    win.close()
    pump(500)
    if child is not None and child.is_alive():
        child.terminate()                     # ours, by its handle
        child.join(timeout=5)
        print('    stopped our viewer child')
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'E2E UI RESULTS: PASS ({len(RAN)} checks)')
    return 0


# ── the screenshots and the measurements (T7) ────────────────────────────
def take_shots(app, win, ents, shots, scratch):
    import copy
    from blastlab.ui.testing import pump
    os.makedirs(shots, exist_ok=True)
    rs = win.results
    fv = rs.field_view
    # a blastFoam-shaped copy of the 2D result for its method card: the
    # backend's extra keys and a loaded run's case.json (no model folder)
    foam = copy.copy(ents['e2e_2d'].result)
    foam.meta = dict(foam.meta)
    foam.meta.pop('model_dir', None)
    cd = os.path.join(scratch, 'foam_case')
    os.makedirs(cd, exist_ok=True)
    with open(os.path.join(cd, 'case.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(schema='blastlab-case', dim=2, solver='blastfoam',
                       material='TNT', activation='linear',
                       afterburn='none'), f)
    foam.meta.update(solver='blastfoam', material='TNT', case_dir=cd,
                     refine=dict(lmax=2, dx_base=foam.meta['dx']),
                     peak_source='foam', eos='JWL')
    ents['foam'] = rs.add_result('foam-shaped 2D (loaded, 2D)', 2, foam)
    pump(200)
    measure = {}

    def select(key):
        rs.sel.setCurrentIndex(rs.entries().index(ents[key]))
        pump(250)

    def grab(tag, screen=False):
        path = os.path.join(shots, f'gui7b-{tag}.png')
        if screen:
            # the embedded viewer is a native child window: only the
            # screen has its pixels
            to_front(win)
            pump(400)
            pix = app.primaryScreen().grabWindow(int(win.winId()))
        else:
            pix = win.grab()
        pix.save(path)
        return path

    def hover_2d():
        img = rs.anim.image if fv.page() == 'replay' else rs.fields.image
        plot = rs.anim.plot if fv.page() == 'replay' else rs.fields.plot
        glw = rs.anim.glw if fv.page() == 'replay' else rs.fields.glw
        i, j = img.shape[0] // 3, img.shape[1] // 2
        to_front(win)
        pump(200)
        pointer_to(glw, plot, (img.xf[i] + img.xf[i + 1]) / 2,
                   (img.yf[j] + img.yf[j + 1]) / 2)

    for mode in ('dark', 'light'):
        win._dark_action.setChecked(mode == 'dark')
        pump(400)
        for w, h in ((1600, 1000), (1100, 720)):
            win.resize(w, h)
            pump(500)
            sz = f'{mode}-{w}x{h}'
            m = measure.setdefault(sz, {})
            # Field: the 2D replay mid-way, with its tick
            select('e2e_2d')
            rs.show_view('Field')
            fv.field_seg._btns['Overpressure'].click()
            rs.set_colour_scale('run')
            pump(200)
            fv.timebar.slider.setValue(fv.timebar.slider.maximum() // 2)
            pump(300)
            grab(f'{sz}-field-replay')
            tb = fv.timebar
            m['columns'] = list(rs.column_widths())
            m['timebar'] = dict(one_line=tb.one_line(), height=tb.height(),
                                play=[tb.play_btn.width(),
                                      tb.play_btn.height()],
                                speed=tb.speed.height(),
                                frame_btn=tb.frame_btn.height(),
                                slider=tb.slider.width(),
                                ticks=tb.slider.ticks())
            m['controls_lines'] = fv.row.rows()
            m['view_tabs'] = rs.view_seg.height()
            m['export_buttons'] = sorted({it.button.height() for it in
                                          rs.export_col.items.values()
                                          if not it.isHidden()})
            m['open3d'] = rs._view3d_btn.height()
            # manual with Min / Max, and the pointer over the map
            rs.set_colour_scale('manual', (0.0, 50.0))
            pump(200)
            hover_2d()
            grab(f'{sz}-field-manual-hover')
            m['hover'] = fv.hover_text()
            rs.set_colour_scale('run')
            # Gauges, G2 selected
            rs.show_view('Gauges')
            pump(300)
            g = rs.gauges
            g.select(g.order()[-1])
            pump(200)
            grab(f'{sz}-gauges-2d')
            m['gauges'] = dict(
                plot=g.plot_w.height(), table=g.table.height(),
                table_width=g.table.width(),
                headers_wrapped=g.headers_wrapped(),
                hscroll=g.table.horizontalScrollBar().maximum(),
                vscroll=g.table.verticalScrollBar().maximum())
            select('e2e_planar')
            rs.show_view('Gauges')
            pump(300)
            grab(f'{sz}-gauges-planar')
            m['planar_z_hidden'] = rs.gauges.table.isColumnHidden(1)
            # 1D Field and Gauges
            select('e2e_1d')
            rs.show_view('Field')
            pump(400)
            grab(f'{sz}-field-1d')
            rs.show_view('Gauges')
            pump(300)
            grab(f'{sz}-gauges-1d')
            # the method card, native (with its model folder) and foam
            select('e2e_2d')
            rs.show_view('Field')
            pump(200)
            grab(f'{sz}-method-native')
            select('foam')
            pump(200)
            grab(f'{sz}-method-foam')
            m['method_foam_rows'] = rs.method_rows()
            # a real Animation export, busy
            select('e2e_2d')
            d = os.path.join(scratch, 'anim', sz)
            os.makedirs(d, exist_ok=True)
            real = patch_dialogs(d)
            try:
                rs._export_btns['gif'].click()
                pump(150)
                m['busy_strip'] = rs.export_col.items['gif'].strip.height()
                grab(f'{sz}-export-busy')
                for _ in range(1500):
                    pump(20)
                    if not rs.busy_kinds():
                        break
            finally:
                restore_dialogs(real)
            # 3D in the embedded viewer
            if 'e2e_3d' in ents:
                select('e2e_3d')
                rs.open_3d()
                pump(2000)
                grab(f'{sz}-view3d', screen=True)
            print(f'    shots {sz}: ' + json.dumps(m), flush=True)
    win._dark_action.setChecked(True)
    pump(300)
    with open(os.path.join(shots, 'measure-7b.json'), 'w',
              encoding='utf-8') as f:
        json.dump(measure, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    if len(sys.argv) >= 6 and sys.argv[1] == '--base-export':
        sys.exit(base_export(sys.argv[2], sys.argv[3], sys.argv[4],
                             sys.argv[5]))
    sys.exit(main())
