"""GUI-12 QA harness (Qt, real platform). Not committed to tests/."""
import os, sys, json, time, tempfile
REPO = r'c:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'blastlab', 'tests'))
OUT = os.path.join(REPO, 'docs', 'qa', '2026-10-04-gui-12-qa')
os.makedirs(OUT, exist_ok=True)
os.environ.pop('QT_QPA_PLATFORM', None)
os.environ['PYTHONIOENCODING'] = 'utf-8'

RES = []


def check(name, ok, detail=''):
    RES.append(dict(name=name, ok=bool(ok), detail=str(detail)))
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else '  -> ' + str(detail)))
    if ok and detail:
        print('      ' + str(detail)[:300])


def main():
    from blastlab.ui import testing
    testing.private_settings()
    app = testing.ensure_qapp(offscreen=False)
    pump = testing.pump
    from blastlab.ui import dialogs, run_controller
    run_controller.pyvista_available = lambda: False
    modal = []
    for n in ('show_error', 'warn', 'show_info'):
        setattr(dialogs, n, lambda title, text, parent=None, _n=n:
                modal.append((_n, title, str(text))))
    dialogs.ask_yes_no = lambda *a, **k: modal.append(('ask', a[:1])) or True
    from blastlab.core.case import Case1D, Case2D, Case3D
    from blastlab.ui.app import MainWindow

    win = MainWindow()
    win.set_solver('native')
    folder = testing.use_model(win, 'gui12qa')
    print('platform', app.platformName(), 'model folder', folder)

    def shoot(name, size):
        win.resize(*size)
        pump(250)
        win.raise_()
        path = os.path.join(OUT, f'{name}_{size[0]}x{size[1]}.png')
        win.grab().save(path)
        return path

    from PySide6.QtWidgets import QScrollArea

    def scroll_bottom(root):
        n = 0
        for sa in root.findChildren(QScrollArea):
            if sa.isVisible():
                bar = sa.verticalScrollBar()
                if bar.maximum() > 0:
                    bar.setValue(bar.maximum())
                    n += 1
        pump(200)
        return n

    win.resize(1100, 720)
    win.show()
    pump(400)
    check('startup: title', bool(win.windowTitle()), win.windowTitle())
    shoot('00_start', (1100, 720))

    # ---------------- 1. Setup Checks: Wall i wording ----------------
    two_wall = Case2D(
        solver='native', geometry='planar', Lx=2.4, Ly=1.6,
        cell_size_m=0.05, charge=20.0, center=(0.3, 0.8),
        obstacles=[(1.2, 1.6, 0.0, 0.6), (1.8, 2.0, 0.9, 1.3)],
        gauges=[(0.3, 0.8), (1.4, 0.3), (1.2, 0.3), (1.8, 0.8),
                (1.9, 1.1), (2.0, 1.2)],
        n_snapshots=2, record_frames=0, gauge_file=None)
    win.setup.set_dim(2)
    win.setup.set_case(two_wall)
    win._schedule_validate()
    pump(700)
    win._show('setup')
    win.setup.show_checks()
    pump(300)
    rows = win.setup.report_rows()
    print('SETUP REPORT', rows)
    msgs = [m for s, m in rows]
    drop = [m for m in msgs if 'will be dropped' in m]
    check('Setup: every drop warning names a wall (Wall i)',
          bool(drop) and all('Wall ' in m for m in drop), drop)
    check('Setup: has an "inside Wall 1" warning',
          any('inside Wall 1' in m for m in drop), drop)
    check('Setup: has an "inside Wall 2" warning (second obstacle index)',
          any('inside Wall 2' in m for m in drop), drop)
    check('Setup: has an "on the face of Wall" warning',
          any('on the face of Wall' in m for m in drop), drop)
    check('Setup: old wording "inside an obstacle" gone',
          not any('an obstacle' in m for m in msgs), msgs)
    for sz in ((1100, 720), (1600, 1000)):
        shoot('01_setup_checks', sz)
    win.resize(1100, 720)
    pump(300)
    sb = win.setup._status_scroll.verticalScrollBar()
    print('setup checks scroll max at 1100x720', sb.maximum())
    sb.setValue(sb.maximum())
    pump(200)
    shoot('01b_setup_checks_scrolled', (1100, 720))
    sb.setValue(0)
    # clipped check: each checktext label's sizeHint fits its height
    from PySide6.QtWidgets import QLabel
    clipped = []
    for lab in win.setup.findChildren(QLabel, 'checktext'):
        if lab.isVisible() and lab.heightForWidth(lab.width()) > lab.height() + 2:
            clipped.append((lab.text(), lab.height(), lab.heightForWidth(lab.width())))
    check('Setup: no check text clipped (heightForWidth <= height) at 1600x1000',
          not clipped, clipped)
    win.resize(1100, 720)
    pump(300)
    clipped = []
    for lab in win.setup.findChildren(QLabel, 'checktext'):
        if lab.isVisible() and lab.heightForWidth(lab.width()) > lab.height() + 2:
            clipped.append((lab.text(), lab.height(), lab.heightForWidth(lab.width())))
    check('Setup: no check text clipped at 1100x720', not clipped, clipped)

    # ---------------- 2. Chain stage 3 ----------------
    win._show('chain')
    ch = win.chain
    ch.set_route('123')
    pump(700)
    ch.focus_stage(3)
    ed3 = ch.editors[3]
    ed3.select_node('stage')
    pump(300)
    rows3 = ed3.check_rows()
    print('CHAIN3 rows', rows3)
    burst = [m for s, m in rows3 if 'burst is at' in m]
    check('Chain: default seed stage 3 shows the 2D->3D reach warning',
          len(burst) == 1 and 'z 2.0 m' in burst[0] and '1.5 m height' in burst[0],
          burst)
    check('Chain: card 3 reads 1 warning, Run chain enabled',
          ch.cards[3].state_text() == '● 1 warning' and ch.run_btn.isEnabled(),
          (ch.cards[3].state_text(), ch.run_btn.isEnabled()))
    print('seed Lz', ch.forms[3].v['Lz'].get(), 'center z 2D', ch.forms[2].v['cy'].get())
    for sz in ((1100, 720), (1600, 1000)):
        shoot('02_chain_stage3_lz1p5', sz)
    win.resize(1100, 720)
    pump(300)
    print('chain scroll areas scrolled', scroll_bottom(ed3))
    shoot('02b_chain_stage3_lz1p5_scrolled', (1100, 720))
    win.resize(1100, 720)
    pump(300)
    clipped = []
    for lab in ed3.findChildren(QLabel, 'checktext'):
        if lab.isVisible() and lab.heightForWidth(lab.width()) > lab.height() + 2:
            clipped.append((lab.text(), lab.height(), lab.heightForWidth(lab.width())))
    check('Chain: stage 3 check text not clipped at 1100x720', not clipped, clipped)
    ch.forms[3].v['Lz'].set('2.5')
    pump(700)
    rows3b = ed3.check_rows()
    check('Chain: silent at Lz 2.5',
          not any('burst is at' in m for s, m in rows3b)
          and ch.cards[3].state_text() == '● case OK', (rows3b, ch.cards[3].state_text()))
    for sz in ((1100, 720), (1600, 1000)):
        shoot('03_chain_stage3_lz2p5', sz)
    win.resize(1100, 720)
    pump(300)
    scroll_bottom(ed3)
    shoot('03b_chain_stage3_lz2p5_scrolled', (1100, 720))
    # boundary: Lz exactly equal to burst z (>= rule)
    ch.forms[3].v['Lz'].set('2.0')
    pump(700)
    check('Chain: Lz == burst z (2.0) still warns (at-or-above rule)',
          any('burst is at' in m for s, m in ed3.check_rows()), ed3.check_rows())
    ch.forms[3].v['Lz'].set('1.5')
    pump(500)

    # ---------------- 3/4. Run + Results: close gauges, earlier dropped ----------------
    dx = 2.4 / 43
    cx = lambda i: (i + 0.5) * dx
    G1 = (round(cx(19) - 0.45 * dx, 4), round(cx(12) + 0.45 * dx, 4))
    G3 = (round(20 * dx + 0.05 * dx, 4), round(cx(12), 4))
    G2 = (G3[0], round(cx(12) + 0.55 * dx, 4))
    wall = (round(20 * dx, 4), 1.5, round(13 * dx, 4), 1.0)
    print('G1', G1, 'G2', G2, 'G3', G3, 'wall', wall)
    run_case = Case2D(solver='native', geometry='planar', Lx=2.4, Ly=1.6,
                      cell_size_m=0.1, charge=400.0, center=(0.3, 0.8),
                      t_end=1.5e-3, n_snapshots=3, record_frames=0,
                      gauge_file=None, obstacles=[wall], gauges=[G1, G2, G3])
    win._show('setup')
    win.setup.set_case(run_case)
    win._schedule_validate()
    pump(700)
    print('RUN CASE setup report', win.setup.report_rows())
    drop = [m for s, m in win.setup.report_rows() if 'dropped' in m]
    check('run case: Setup warns G2 (inside Wall 1) only',
          len(drop) == 1 and 'inside Wall 1' in drop[0] and str(G2) in drop[0], drop)
    win._run_single()
    t0 = time.monotonic()
    col = win.run_panel.gauge_col
    mid_done = False
    while win.ctrl.running and time.monotonic() - t0 < 240:
        pump(30)
        if not mid_done and col.has_data():
            shoot('04_run_live_gauges_mid', (1100, 720))
            mid_done = True
            print('mid labels', col.row_labels(), col.caption_text())
    pump(800)
    check('run finished', not win.ctrl.running, f'{time.monotonic()-t0:.1f}s')
    labels = col.row_labels()
    cap = col.caption_text()
    print('final labels', labels, 'caption:', cap)
    for sz in ((1100, 720), (1600, 1000)):
        shoot('05_run_live_gauges_final', sz)
    res = win.results.current().result
    pts = res.gauges['points']
    print('solver points', pts, 'dx', res.meta.get('dx'))
    check('run: solver kept 2 gauges, dropped G2', len(pts) == 2, pts)
    from blastlab.output import gauge_summary as gs
    # greedy reference (pre-A2 rule)
    ent = res.meta.get('gauges')
    def greedy(points, w):
        used, out = set(), []
        for pt in points:
            j = min((j for j in range(len(w)) if j not in used),
                    key=lambda j: sum((a - b) ** 2 for a, b in zip(w[j], pt)))
            used.add(j); out.append(j)
        return out
    g_idx = greedy(pts, ent)
    print('greedy would pair', g_idx, ' order-preserving', gs.pair_in_order(pts, ent))
    check('real run discriminates greedy from order-preserving',
          g_idx != gs.pair_in_order(pts, ent), (g_idx, gs.pair_in_order(pts, ent)))
    check('Run live column labels are G1, G3 (sorted set)',
          sorted(labels) == ['G1', 'G3'], labels)
    check('Run live caption names G2 and Wall 1',
          'G2 dropped by the solver (inside Wall 1)' in cap, cap)
    exported = [s.split()[0] for s in gs.gauge_labels(res.gauges, ent)]
    check('exported gauge_labels == [G1, G3]', exported == ['G1', 'G3'], exported)

    # Results screen
    win._show('results')
    pump(300)
    p = win.results
    p.show_view('Gauges')
    pump(500)
    g = p.gauges
    cells = g.cells()
    print('results gauges cells', cells, 'caption', g.caption_text())
    check('Results Gauges rows labelled G1, G3',
          sorted(c[0] for c in cells) == ['G1', 'G3'], cells)
    for sz in ((1100, 720), (1600, 1000)):
        shoot('06_results_gauges', sz)
    # export figures
    from blastlab.services import exports as ex
    figs = ex.report_figures(res, 2)
    gfig = [(cap_, f) for cap_, f in figs if 'auge' in cap_]
    print('report figure captions', [c for c, f in figs])
    titles = []
    for cap_, f in gfig:
        for k, ax in enumerate(f.axes):
            titles.append(ax.get_title())
        f.savefig(os.path.join(OUT, '07_export_gauge_traces.png'), dpi=90)
    print('export titles', titles)
    check('export (report) gauge titles start Gauge 1 / Gauge 3, never Gauge 2',
          len(titles) >= 2 and titles[0].startswith('Gauge 1')
          and titles[1].startswith('Gauge 3') and not any(t.startswith('Gauge 2') for t in titles),
          titles)
    pngs = ex.png_figures(res, 2)
    ptitles = []
    for fn, f in pngs:
        if 'gauge' in fn.lower():
            ptitles += [ax.get_title() for ax in f.axes]
    check('export (PNG set) gauge titles agree', ptitles[:2] == titles[:2] if ptitles else False,
          ptitles)
    # on-screen gauge plot title / legend text: dump every pyqtgraph text item
    try:
        import pyqtgraph as pg
        texts = []
        for pw in g.findChildren(pg.PlotWidget):
            pi = pw.getPlotItem()
            texts.append(pi.titleLabel.text)
            leg = getattr(pi, 'legend', None)
            if leg is not None:
                texts += [l.text for _s, l in leg.items]
        print('on-screen pg texts', texts)
    except Exception as exc:
        print('pg dump failed', exc)
    # no-drop control for exports: bytes of titles equal literal
    json.dump(dict(labels=labels, caption=cap, titles=titles, pts=pts, ent=ent,
                   greedy=g_idx), open(os.path.join(OUT, 'run_values.json'), 'w'),
              indent=1, default=str)
    # keep the Summary and HTML via real exporters if cheap
    try:
        rep = ex.report_html if hasattr(ex, 'report_html') else None
        print('exports module has report_html', bool(rep))
    except Exception as exc:
        print(exc)
    # saved result for the Tk step
    import pickle
    with open(os.path.join(tempfile.gettempdir(), 'gui12_res.pkl'), 'wb') as f:
        pickle.dump(res, f)
    print('pickled result for Tk step')

    # ---------------- 4b. 1D Field tooltip ----------------
    win._show('setup')
    win.setup.set_dim(1)
    win.setup.set_case(Case1D(solver='native', radius_m=2.0, charge_kg=1.0,
                                cell_size_m=0.005, eos='idealGas'))
    pump(400)
    win._run_single()
    t0 = time.monotonic()
    while win.ctrl.running and time.monotonic() - t0 < 240:
        pump(30)
    pump(800)
    check('1D run finished', not win.ctrl.running, f'{time.monotonic()-t0:.1f}s')
    win._show('results')
    pump(300)
    p.show_view('Field')
    pump(800)
    fv = p.fields
    tip = fv.canvas.toolTip()
    print('1D tooltip:', tip)
    res1 = p.current().result
    from blastlab.output import plots
    from blastlab.services.exports import charge_label
    c = charge_label(res1.meta)
    full = plots.figure_results_1d(res1.snapshots, c.eos, c.charge_kg, c.radius_m)
    full_t = full.axes[0].get_title()
    check('1D Field tooltip = "Exports use the full title: <export suptitle>"',
          tip == f'Exports use the full title: {full_t}' and bool(full_t),
          (tip, full_t))
    for sz in ((1100, 720), (1600, 1000)):
        shoot('08_results_field_1d', sz)
    # hover tooltip rendering: real mouse move + QToolTip grab
    from PySide6.QtCore import QPoint, Qt, QEvent
    from PySide6.QtGui import QHelpEvent, QGuiApplication
    from PySide6.QtWidgets import QToolTip, QApplication
    win.resize(1100, 720)
    win.activateWindow()
    pump(400)
    cv = fv.canvas
    lp = QPoint(cv.width() // 2, cv.height() // 2)
    ev = QHelpEvent(QEvent.ToolTip, lp, cv.mapToGlobal(lp))
    QApplication.sendEvent(cv, ev)
    pump(600)
    for w in QApplication.topLevelWidgets():
        if w.metaObject().className() == 'QTipLabel' and w.isVisible():
            w.grab().save(os.path.join(OUT, '09_field_1d_tooltip.png'))
            print('tooltip widget grabbed', w.size())
    # window-only grab with the tooltip is not possible (tooltip is its own top-level)
    print('tooltip visible', QToolTip.isVisible(), repr(QToolTip.text()))
    check('QHelpEvent on the 1D canvas shows the tooltip (QToolTip visible)',
          QToolTip.isVisible() and QToolTip.text() == tip, repr(QToolTip.text()))

    # ---------------- close ----------------
    check('no modal dialogs except the model-folder overwrite question of the 3rd run in one folder (harness artefact)', all(m[0] == 'ask' and m[1] == ('Model folder',) for m in modal), modal)
    win.close()
    pump(300)
    json.dump(RES, open(os.path.join(OUT, 'results_qt.json'), 'w'), indent=1)
    n_ok = sum(r['ok'] for r in RES)
    print(f'\n{n_ok}/{len(RES)} checks passed')


if __name__ == '__main__':
    main()
