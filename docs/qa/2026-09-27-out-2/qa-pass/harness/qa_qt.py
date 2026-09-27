"""Throwaway QA harness (gui-qa-tester, 2026-09-27): the OUT-2 "VTK output
(ParaView)" card in the REAL Qt window (QT_QPA_PLATFORM unset).

Run:  python -u qa_qt.py <shots dir> <work dir>
Needs BLASTLAB_SETTINGS pointing at a private file with auto_cleanup false.
Writes shots to <shots dir> (prefix qt_), and qt_results.json beside them.
"""
import ctypes
import json
import os
import sys
import time
import traceback

REPO = r'C:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
sys.path.insert(0, REPO)
os.environ.pop('QT_QPA_PLATFORM', None)
assert os.environ.get('BLASTLAB_SETTINGS'), 'private settings first'

SHOTS = sys.argv[1]
WORK = sys.argv[2]
os.makedirs(SHOTS, exist_ok=True)
os.makedirs(WORK, exist_ok=True)
VTK = 'VTK output (ParaView)'
RES = dict(checks=[], notes=[], errors=[], fit={}, colours={}, strips={},
           tips={}, labels={})
user32 = ctypes.windll.user32


def log(*a):
    print(*a, flush=True)


def check(name, ok, detail=''):
    RES['checks'].append(dict(name=name, ok=bool(ok), detail=str(detail)))
    log(f"[{'PASS' if ok else 'FAIL'}] {name} {('- ' + str(detail)) if detail else ''}")


def note(k, v):
    RES['notes'].append(f'{k}: {v}')
    log(f'  note {k}: {v}')


def main():
    from blastlab.core import settings
    assert settings.load().get('auto_cleanup') is False
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (QApplication, QCheckBox, QLabel,
                                   QLineEdit, QToolTip, QWidget)
    from PIL import ImageGrab
    app = QApplication.instance() or QApplication(['blastlab'])
    from blastlab.ui import theme
    theme.apply(app, 'dark')
    from blastlab.ui import dialogs
    from blastlab.ui.app import MainWindow
    from blastlab.core.case import Case1D, Case2D, Case3D, save_case

    def pump(s=0.3):
        end = time.monotonic() + s
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()

    win = MainWindow()
    win.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    win.resize(1280, 840)
    win.move(20, 20)
    win.show()
    win.raise_()
    win.activateWindow()
    pump(2.0)
    dpr = win.devicePixelRatioF()
    scr = win.screen().geometry()
    note('screen', f'{scr.width()}x{scr.height()} logical, dpr {dpr}')
    note('window', f'{win.width()}x{win.height()}, title {win.windowTitle()!r}, '
         f'minimum {win.minimumWidth()}x{win.minimumHeight()}')
    win._show('setup')
    pump(0.5)
    setup = win.setup

    def form():
        return setup.form

    def card():
        return form().cards[VTK]

    def see_card():
        try:
            setup._scroll.ensureWidgetVisible(card(), 0, 0)
        except Exception:
            pass
        pump(0.5)

    def shot(name, widget=None):
        pump(0.35)
        w = widget or win
        pm = w.grab()
        path = os.path.join(SHOTS, f'qt_{name}.png')
        pm.save(path)
        log(f'  shot {path}')
        return path

    def screen_shot(name, widget, margin=(40, 40, 420, 120)):
        """Screen pixels around `widget` (tooltips are their own window)."""
        g = widget.mapToGlobal(QPoint(0, 0))
        x0 = int((g.x() - margin[0]) * dpr)
        y0 = int((g.y() - margin[1]) * dpr)
        x1 = int((g.x() + widget.width() + margin[2]) * dpr)
        y1 = int((g.y() + widget.height() + margin[3]) * dpr)
        path = os.path.join(SHOTS, f'qt_{name}.png')
        ImageGrab.grab(bbox=(max(0, x0), max(0, y0), x1, y1),
                       all_screens=True).save(path)
        log(f'  screen shot {path}')
        return path

    def strip():
        return [f'{s}: {t}' for s, t in setup.report_rows()]

    def validate():
        win._schedule_validate()
        pump(1.0)

    def set_case(c):
        setup.set_case(c)
        win._schedule_validate()
        pump(1.2)

    def mean_rgb(widget, inset=None):
        img = widget.grab().toImage().convertToFormat(QImage.Format_RGB32)
        w, h = img.width(), img.height()
        if inset:
            cx, cy = w // 2, h // 2
            xs = range(max(0, cx - inset), min(w, cx + inset))
            ys = range(max(0, cy - inset), min(h, cy + inset))
        else:
            xs, ys = range(w), range(h)
        r = g = b = n = 0
        for y in ys:
            for x in xs:
                c = img.pixelColor(x, y)
                r += c.red(); g += c.green(); b += c.blue(); n += 1
        return (round(r / n), round(g / n), round(b / n)) if n else None

    def fit(tag):
        """Does the card (and its matrix) fit at this width?"""
        f = form()
        cd = card()
        out = dict(window=f'{win.width()}x{win.height()}',
                   card_w=cd.width(), issues=[])
        grid = f.widgets['vtk_fields']
        out['grid_w'] = grid.width()
        out['grid_min_w'] = grid.minimumSizeHint().width()
        for lbl in cd.findChildren(QLabel):
            if not lbl.isVisible() or not lbl.text():
                continue
            txt = lbl.text()
            fm = lbl.fontMetrics()
            if lbl.wordWrap():
                need_h = lbl.heightForWidth(lbl.width())
                if need_h > lbl.height() + 1:
                    out['issues'].append(f'label {txt!r} clipped vertically '
                                         f'(needs {need_h}, has {lbl.height()})')
                # a single word longer than the width is cut even when wrapped
                longest = max((fm.horizontalAdvance(wd) for wd in
                               txt.replace('\n', ' ').split()), default=0)
                if longest > lbl.width():
                    out['issues'].append(f'label {txt!r}: a word needs '
                                         f'{longest}px, label {lbl.width()}px')
            else:
                need = max(fm.horizontalAdvance(t) for t in txt.split('\n'))
                if need > lbl.width():
                    out['issues'].append(f'label {txt!r} needs {need}px, '
                                         f'has {lbl.width()}px')
        for box in grid.findChildren(QCheckBox):
            if not grid.rect().contains(box.geometry()):
                out['issues'].append(f'checkbox at {box.geometry()} outside '
                                     f'the grid {grid.rect()}')
        tl = grid.mapTo(cd, QPoint(0, 0))
        if tl.x() + grid.width() > cd.width():
            out['issues'].append('matrix wider than its card')
        # overlap with sibling cards
        mine = cd.geometry()
        for t, other in f.cards.items():
            if other is cd or other.isHidden() or other.parent() is not cd.parent():
                continue
            if mine.intersects(other.geometry()):
                out['issues'].append(f'card overlaps {t!r}')
        # every input of the card at least as wide as its minimum
        for n in ('vtk_s_ms', 'vtk_s_steps', 'vtk_v_ms', 'vtk_v_steps'):
            w = f.widgets.get(n)
            if w is not None and w.isVisible() and w.width() < w.minimumWidth():
                out['issues'].append(f'{n} narrower than its minimum')
        out['hscroll_max'] = setup._scroll.horizontalScrollBar().maximum()
        RES['fit'][tag] = out
        check(f'{tag}: the card and matrix fit ({out["window"]}, card '
              f'{out["card_w"]}px, matrix {out["grid_w"]}px)',
              not out['issues'], out['issues'])
        return out

    def tick_family(fam, on=True):
        box = form().widgets[f'vtk_{fam}_on']
        if box.isChecked() != on:
            QTest.mouseClick(box, Qt.LeftButton,
                             pos=QPoint(8, box.height() // 2))
            pump(0.5)

    def mode(fam, m):
        b = form().widgets[f'vtk_{fam}_mode'].buttons[m]
        QTest.mouseClick(b, Qt.LeftButton, pos=QPoint(8, b.height() // 2))
        pump(0.5)

    fams = {1: ['v'], 2: ['v', 's'], 3: ['s', 'v']}

    # ── 1. 1D/2D/3D x Time/Step x 1100/1280 ───────────────────────────
    for width in (1100, 1280):
        win.resize(width, 840 if width == 1280 else 720)
        pump(0.8)
        for dim, C in ((1, Case1D), (2, Case2D), (3, Case3D)):
            try:
                kw = dict(solver='blastfoam')
                if dim == 2:
                    kw['obstacles'] = [(3.0, 3.2, 0.0, 0.5)]
                set_case(C(**kw))
                for fm in fams[dim]:
                    tick_family(fm)
                see_card()
                check(f'{dim}D@{width}: first ticks fill the defaults',
                      bool(form().v['vtk_fields'].get()),
                      form().v['vtk_fields'].get())
                fit(f'{dim}D_time_{width}')
                ms_on = all(form().is_enabled(f'vtk_{fm}_ms') and
                            not form().is_enabled(f'vtk_{fm}_steps')
                            for fm in fams[dim])
                check(f'{dim}D@{width} Time: steps boxes disabled, ms live',
                      ms_on)
                shot(f'{dim}d_time_{width}_window')
                shot(f'{dim}d_time_{width}_card', card())
                for fm in fams[dim]:
                    mode(fm, 'step')
                st_on = all(not form().is_enabled(f'vtk_{fm}_ms') and
                            form().is_enabled(f'vtk_{fm}_steps')
                            for fm in fams[dim])
                check(f'{dim}D@{width} Step: ms boxes disabled, steps live',
                      st_on)
                fit(f'{dim}D_step_{width}')
                shot(f'{dim}d_step_{width}_card', card())
                RES['strips'][f'{dim}D_step_{width}'] = strip()
            except Exception:
                RES['errors'].append(traceback.format_exc())
                log(traceback.format_exc())

    # ── colours: locked Gauge vs live ticks; inactive cadence ─────────
    try:
        win.resize(1280, 840)
        pump(0.6)
        set_case(Case3D(solver='blastfoam'))
        tick_family('s'); tick_family('v'); mode('s', 'step')
        see_card()
        grid = form().widgets['vtk_fields']
        locked = [b for b in grid.findChildren(QCheckBox)
                  if not b.isEnabled()]
        locked_on = [b for b in locked if b.isChecked()]
        locked_off = [b for b in locked if not b.isChecked()]
        live_on = [b for b in grid.boxes.values() if b.isChecked()]
        live_off = [b for b in grid.boxes.values() if not b.isChecked()]
        col = dict(
            locked_ticked=mean_rgb(locked_on[0], 7),
            live_ticked=mean_rgb(live_on[0], 7),
            locked_unticked=mean_rgb(locked_off[0], 7) if locked_off else None,
            live_unticked=mean_rgb(live_off[0], 7),
            ms_live=mean_rgb(form().widgets['vtk_v_ms']),
            ms_greyed=mean_rgb(form().widgets['vtk_s_ms']),
            steps_live=mean_rgb(form().widgets['vtk_s_steps']),
            steps_greyed=mean_rgb(form().widgets['vtk_v_steps']))
        RES['colours']['dark'] = col
        note('dark colours', col)
        d = sum((a - b) ** 2 for a, b in zip(col['locked_ticked'],
                                             col['live_ticked'])) ** .5
        check('dark: locked Gauge tick differs from a live tick (RGB distance'
              ' > 40)', d > 40, f'distance {d:.0f}')
        pal_dis = form().widgets['vtk_s_ms'].palette()
        note('greyed ms box text', form().widgets['vtk_s_ms'].text())
        shot('3d_colours_dark_card', card())
        shot('3d_matrix_dark', grid)
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # ── tooltips by real hover (1100 px, 3D) ──────────────────────────
    try:
        win.resize(1100, 720)
        pump(0.8)
        see_card()
        grid = form().widgets['vtk_fields']
        labels = [l for l in grid.findChildren(QLabel) if l.toolTip()]
        RES['labels']['matrix'] = [(l.text(), l.toolTip()) for l in labels]
        # scroll so the matrix is on screen
        setup._scroll.ensureWidgetVisible(grid, 0, 0)
        pump(0.6)
        win.raise_(); win.activateWindow(); pump(0.4)
        picks = [l for l in labels if l.text() in ('Sect.', 'Obst.', 'Vol.',
                                                   'Gauge', 'Peak overpr.',
                                                   'Products')]
        for lbl in picks:
            g = lbl.mapToGlobal(QPoint(lbl.width() // 2, lbl.height() // 2))
            user32.SetCursorPos(int(g.x() * dpr) - 3, int(g.y() * dpr) - 3)
            pump(0.15)
            user32.SetCursorPos(int(g.x() * dpr), int(g.y() * dpr))
            pump(1.5)
            shown = QToolTip.isVisible()
            txt = QToolTip.text()
            RES['tips'][lbl.text()] = dict(visible=shown, text=txt,
                                           expected=lbl.toolTip())
            safe = lbl.text().replace('.', '').replace(' ', '_')
            screen_shot(f'tip_{safe}', lbl)
            check(f'hover {lbl.text()!r}: tooltip shows {lbl.toolTip()!r}',
                  shown and txt == lbl.toolTip(), f'visible={shown} text={txt!r}')
            user32.SetCursorPos(5, 5)
            pump(0.4)
        # a locked Gauge box: does it explain itself?
        locked = [b for b in grid.findChildren(QCheckBox) if not b.isEnabled()]
        RES['tips']['locked_box'] = locked[0].toolTip() if locked else None
        # the greyed cadence box: does it explain itself?
        RES['tips']['greyed_ms'] = form().widgets['vtk_s_ms'].toolTip()
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # ── plane table: q, 1 refused, y, 1.4 accepted (typed + Return) ───
    try:
        pl = form().points['vtk_planes']
        setup._scroll.ensureWidgetVisible(pl, 0, 0)
        pump(0.4)
        pl.entry.clear()
        QTest.keyClicks(pl.entry, 'q, 1')
        QTest.keyClick(pl.entry, Qt.Key_Return)
        pump(0.5)
        hint = pl.hint.text()
        check('plane "q, 1" refused with a reason', pl.count() == 0
              and 'x, y or z' in hint, f'rows {pl.get()}, hint {hint!r}')
        RES['labels']['plane_refusal'] = hint
        shot('3d_plane_q1_refused_1100_card', card())
        pl.entry.clear()
        QTest.keyClicks(pl.entry, 'y, 1.4')
        QTest.keyClick(pl.entry, Qt.Key_Return)
        pump(0.8)
        check('plane "y, 1.4" accepted', pl.get() == [('y', 1.4)],
              f'rows {pl.get()}, hint {pl.hint.text()!r}')
        validate()
        RES['strips']['3D_plane_y14'] = strip()
        shot('3d_plane_y14_1100_card', card())
        shot('3d_plane_y14_1100_window')
        # out of range and a word
        for text in ('z, 9', 'x, abc', 'x 0.5 1'):
            pl.entry.clear()
            QTest.keyClicks(pl.entry, text)
            QTest.keyClick(pl.entry, Qt.Key_Return)
            pump(0.6)
            validate()
            RES['labels'][f'plane {text!r}'] = dict(
                rows=pl.get(), hint=pl.hint.text(),
                strip=[s for s in strip() if 'plane' in s.lower() or 'VTK' in s])
        shot('3d_plane_z9_card', card())
        RES['strips']['3D_plane_z9'] = strip()
        shot('3d_plane_z9_window')
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # ── bad values in the active / inactive box ───────────────────────
    try:
        win.resize(1280, 840); pump(0.5)
        set_case(Case3D(solver='blastfoam'))
        tick_family('s'); tick_family('v')
        f = form()
        for name, text in (('vtk_v_ms', '-1'), ('vtk_v_ms', '0'),
                           ('vtk_v_ms', 'abc'), ('vtk_v_ms', ''),
                           ('vtk_s_steps', '2.5')):
            if name == 'vtk_s_steps':
                mode('s', 'step')
            w = f.widgets[name]
            w.setFocus()
            w.selectAll()
            QTest.keyClicks(w, text) if text else QTest.keyClick(w, Qt.Key_Delete)
            validate()
            RES['strips'][f'bad {name}={text!r}'] = strip()
            check(f'bad {name}={text!r}: the strip reports an error, others kept',
                  any(s.startswith('error') for s in strip())
                  and f.v['vtk_s_on'].get(), strip()[:3])
            safe = text.replace('.', 'p').replace('-', 'm') or 'empty'
            shot(f'bad_{name}_{safe}_window')
            w.selectAll()
            QTest.keyClicks(w, '1' if name.endswith('ms') else '25')
            validate()
        # a bad value in the INACTIVE box never blocks
        mode('s', 'time')
        w = f.widgets['vtk_s_steps']   # disabled now: set via the var
        f.v['vtk_s_steps'].set('abc')
        validate()
        RES['strips']['inactive steps=abc'] = strip()
        check('an "abc" in the greyed steps box does not block',
              not any(s.startswith('error') for s in strip()), strip()[:3])
        f.v['vtk_s_steps'].set('25')
        validate()
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # ── 3. native mode: hidden; back restores; saved case has no vtk_ ─
    saved = {}
    try:
        set_case(Case3D(solver='blastfoam'))
        tick_family('s'); tick_family('v'); mode('v', 'step')
        before = dict(m=form().v['vtk_fields'].get(),
                      s=form().v['vtk_s_on'].get(), v=form().v['vtk_v_on'].get(),
                      vmode=form().v['vtk_v_mode'].get())
        # save in blastFoam mode (the file for item 5)
        p_foam = os.path.join(WORK, 'qt_saved_foam_3d.json')
        dialogs.save_file = lambda *a, **k: p_foam
        win._save_case()
        pump(0.3)
        saved['foam'] = json.load(open(p_foam, encoding='utf-8'))
        check('blastFoam save carries vtk_surfaces and vtk_volumes',
              'vtk_surfaces' in saved['foam'] and 'vtk_volumes' in saved['foam'],
              {k: saved['foam'].get(k) for k in ('vtk_surfaces', 'vtk_volumes')})
        # sidebar segment click, the real control
        seg = win._solver_seg
        win.solver_mode.set('native')
        pump(1.0)
        check('native: the VTK card is hidden (isHidden)',
              card().isHidden(), f'hidden={card().isHidden()} '
              f'enabled={card().isEnabled()}')
        setup.scroll_form(1.0); pump(0.4)
        shot('3d_native_bottom_window')
        setup.scroll_form(0.0); pump(0.4)
        shot('3d_native_top_window')
        p_nat = os.path.join(WORK, 'qt_saved_native_3d.json')
        dialogs.save_file = lambda *a, **k: p_nat
        win._save_case()
        pump(0.3)
        saved['native'] = json.load(open(p_nat, encoding='utf-8'))
        check('native save has no vtk_ key',
              not any(k.startswith('vtk_') for k in saved['native']),
              sorted(k for k in saved['native'] if k.startswith('vtk')))
        win.solver_mode.set('blastfoam')
        pump(1.0)
        after = dict(m=form().v['vtk_fields'].get(),
                     s=form().v['vtk_s_on'].get(), v=form().v['vtk_v_on'].get(),
                     vmode=form().v['vtk_v_mode'].get())
        check('back to blastFoam: card visible and ticks/mode restored',
              (not card().isHidden()) and after == before,
              f'before {before} after {after}')
        see_card()
        shot('3d_foam_again_card', card())
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # ── 4. 2D obstacles family with no obstacles ─────────────────────
    try:
        set_case(Case2D(solver='blastfoam'))
        tick_family('s')
        validate()
        s1 = strip()
        RES['strips']['2D obstacles none'] = s1
        check('2D Obstacles, no obstacles: "nothing to sample" in the strip',
              any('nothing to sample' in s for s in s1), s1)
        see_card()
        shot('2d_no_obstacles_window')
        obs = form().obstacles
        setup._scroll.ensureWidgetVisible(obs, 0, 0)
        pump(0.4)
        obs.entry.clear()
        QTest.keyClicks(obs.entry, '3.0, 3.2, 0.0, 0.5')
        QTest.keyClick(obs.entry, Qt.Key_Return)
        pump(0.5)
        validate()
        s2 = strip()
        RES['strips']['2D obstacles one'] = s2
        check('2D: after typing an obstacle the refusal clears',
              not any('nothing to sample' in s for s in s2), s2)
        shot('2d_with_obstacle_window')
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # ── 5. load a case with VTK keys, then one without (P12) ─────────
    try:
        with_keys = Case3D(solver='blastfoam', vtk_surfaces=dict(
            on=True, mode='step', value=10, fields=['p', 'impulse'],
            obstacle_fields=['pMax'], planes=[['x', 0.5], ['z', 0.3]]),
            vtk_volumes=dict(on=True, mode='time', value=0.5,
                             fields=['p', 'T']))
        p_with = os.path.join(WORK, 'case_with_vtk.json')
        save_case(with_keys, p_with)
        p_without = os.path.join(WORK, 'case_without_vtk.json')
        save_case(Case3D(solver='blastfoam'), p_without)
        p_without_nat = os.path.join(WORK, 'case_without_vtk_native.json')
        save_case(Case3D(solver='native'), p_without_nat)
        # dirty the card first so a reset is visible
        set_case(Case3D(solver='blastfoam'))
        win._open_case(p_with)
        pump(1.2)
        f = form()
        got = dict(s_on=f.v['vtk_s_on'].get(), s_mode=f.v['vtk_s_mode'].get(),
                   s_steps=f.v['vtk_s_steps'].get(), s_ms=f.v['vtk_s_ms'].get(),
                   v_on=f.v['vtk_v_on'].get(), v_mode=f.v['vtk_v_mode'].get(),
                   v_ms=f.v['vtk_v_ms'].get(), v_steps=f.v['vtk_v_steps'].get(),
                   planes=f.points['vtk_planes'].get(),
                   m=f.v['vtk_fields'].get(),
                   s_ms_enabled=f.is_enabled('vtk_s_ms'),
                   s_steps_enabled=f.is_enabled('vtk_s_steps'),
                   v_ms_enabled=f.is_enabled('vtk_v_ms'),
                   v_steps_enabled=f.is_enabled('vtk_v_steps'))
        RES['labels']['loaded_with'] = got
        ok = (got['s_on'] and got['s_mode'] == 'step' and got['s_steps'] == '10'
              and got['v_on'] and got['v_mode'] == 'time'
              and got['v_ms'] == '0.5'
              and got['planes'] == [('x', 0.5), ('z', 0.3)]
              and got['m'] == {'sections': ['p', 'impulse'],
                               'obstacles': ['pMax'], 'volumes': ['p', 'T']}
              and not got['s_ms_enabled'] and got['s_steps_enabled']
              and got['v_ms_enabled'] and not got['v_steps_enabled'])
        check('load with keys: every key shown, greying follows each mode',
              ok, got)
        see_card()
        shot('3d_loaded_with_keys_card', card())
        win._open_case(p_without)
        pump(1.2)
        f = form()
        got2 = dict(s_on=f.v['vtk_s_on'].get(), s_mode=f.v['vtk_s_mode'].get(),
                    s_steps=f.v['vtk_s_steps'].get(), s_ms=f.v['vtk_s_ms'].get(),
                    v_on=f.v['vtk_v_on'].get(), v_mode=f.v['vtk_v_mode'].get(),
                    v_ms=f.v['vtk_v_ms'].get(), v_steps=f.v['vtk_v_steps'].get(),
                    planes=f.points['vtk_planes'].get(),
                    m=f.v['vtk_fields'].get(),
                    s_ms_enabled=f.is_enabled('vtk_s_ms'),
                    s_steps_enabled=f.is_enabled('vtk_s_steps'),
                    v_ms_enabled=f.is_enabled('vtk_v_ms'),
                    v_steps_enabled=f.is_enabled('vtk_v_steps'),
                    step_radio_checked=f.widgets['vtk_s_mode'].buttons['step'].isChecked(),
                    time_radio_checked=f.widgets['vtk_s_mode'].buttons['time'].isChecked())
        RES['labels']['loaded_without'] = got2
        ok2 = (not got2['s_on'] and not got2['v_on']
               and got2['s_mode'] == 'time' and got2['v_mode'] == 'time'
               and got2['s_ms'] == '1' and got2['v_ms'] == '1'
               and got2['s_steps'] == '25' and got2['v_steps'] == '25'
               and got2['planes'] == []
               and not any(got2['m'].values())
               and got2['s_ms_enabled'] and not got2['s_steps_enabled']
               and got2['v_ms_enabled'] and not got2['v_steps_enabled']
               and got2['time_radio_checked'] and not got2['step_radio_checked'])
        check('load without keys: P12 defaults, greying follows Time', ok2, got2)
        see_card()
        shot('3d_loaded_without_keys_card', card())
        win._open_case(p_without_nat)
        pump(1.2)
        check('load a native case: the card is hidden', card().isHidden(),
              f'mode {win.solver_mode.get()}')
        win.solver_mode.set('blastfoam'); pump(1.0)
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # ── 7. light mode ────────────────────────────────────────────────
    try:
        win._mode_switch.setChecked(False)
        pump(1.0)
        for dim, C in ((1, Case1D), (2, Case2D), (3, Case3D)):
            kw = dict(solver='blastfoam')
            if dim == 2:
                kw['obstacles'] = [(3.0, 3.2, 0.0, 0.5)]
            set_case(C(**kw))
            for fm in fams[dim]:
                tick_family(fm)
            mode(fams[dim][0], 'step')
            see_card()
            shot(f'{dim}d_light_card', card())
        shot('3d_light_window')
        grid = form().widgets['vtk_fields']
        locked = [b for b in grid.findChildren(QCheckBox)
                  if not b.isEnabled() and b.isChecked()]
        live_on = [b for b in grid.boxes.values() if b.isChecked()]
        live_off = [b for b in grid.boxes.values() if not b.isChecked()]
        col = dict(locked_ticked=mean_rgb(locked[0], 7),
                   live_ticked=mean_rgb(live_on[0], 7),
                   live_unticked=mean_rgb(live_off[0], 7),
                   ms_greyed=mean_rgb(form().widgets['vtk_s_ms']),
                   ms_live=mean_rgb(form().widgets['vtk_v_ms']))
        RES['colours']['light'] = col
        d = sum((a - b) ** 2 for a, b in zip(col['locked_ticked'],
                                             col['live_ticked'])) ** .5
        check('light: locked Gauge tick differs from a live tick (> 40)',
              d > 40, f'distance {d:.0f} {col}')
        shot('3d_matrix_light', grid)
        win._mode_switch.setChecked(True)
        pump(0.8)
    except Exception:
        RES['errors'].append(traceback.format_exc()); log(traceback.format_exc())

    # label texts for the confusion review
    try:
        f = form()
        RES['labels']['card_texts'] = [l.text() for l in card().findChildren(QLabel)
                                       if l.text()]
        RES['labels']['card_checkboxes'] = [b.text() for b in
                                            card().findChildren(QCheckBox)
                                            if b.text()]
        RES['labels']['t_end_label'] = f.label_text('t_end')
        RES['labels']['all_row_labels'] = {n: (l.text() if l else None)
                                           for n, l in f.labels.items()}
    except Exception:
        RES['errors'].append(traceback.format_exc())

    # close through the real close path
    win.close()
    pump(1.0)
    with open(os.path.join(SHOTS, 'qt_results.json'), 'w', encoding='utf-8') as fh:
        json.dump(RES, fh, indent=1, default=str)
    n_fail = sum(1 for c in RES['checks'] if not c['ok'])
    log(f'DONE: {len(RES["checks"])} checks, {n_fail} failed, '
        f'{len(RES["errors"])} harness errors')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        with open(os.path.join(SHOTS, 'qt_results.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(RES, fh, indent=1, default=str)
        sys.exit(1)
