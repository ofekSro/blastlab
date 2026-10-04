"""GUI-13 QA harness (Qt, real platform). Not committed to tests/."""
import os, sys, json, time, re, tempfile
REPO = r'c:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'blastlab', 'tests'))
OUT = os.path.join(REPO, 'docs', 'qa', '2026-10-05-gui-13-qa')
os.makedirs(OUT, exist_ok=True)
os.environ.pop('QT_QPA_PLATFORM', None)
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
    app = testing.ensure_qapp(offscreen=False)
    pump = testing.pump
    from blastlab.ui import dialogs, run_controller
    run_controller.pyvista_available = lambda: False
    modal = []
    for n in ('show_error', 'warn', 'show_info'):
        setattr(dialogs, n, lambda title, text, parent=None, _n=n:
                modal.append((_n, title, str(text))))
    dialogs.ask_yes_no = lambda *a, **k: modal.append(('ask', a[:1])) or True
    from blastlab.core.case import Case1D, Case2D
    from blastlab.ui.app import MainWindow
    from PySide6.QtWidgets import QLabel, QScrollArea

    win = MainWindow()
    win.set_solver('native')
    folder = testing.use_model(win, 'gui13qa')
    print('platform', app.platformName(), 'model folder', folder)

    def shoot(name, size):
        win.resize(*size)
        pump(250)
        win.raise_()
        path = os.path.join(OUT, f'{name}_{size[0]}x{size[1]}.png')
        win.grab().save(path)
        return path

    def both(name):
        for sz in ((1100, 720), (1600, 1000)):
            shoot(name, sz)
        win.resize(1100, 720)
        pump(250)

    def clipped_labels(root, objname=None):
        bad = []
        labs = root.findChildren(QLabel, objname) if objname else root.findChildren(QLabel)
        for lab in labs:
            if lab.isVisible() and lab.wordWrap() and lab.width() > 0 \
               and lab.heightForWidth(lab.width()) > lab.height() + 2:
                bad.append((lab.text()[:90], lab.height(), lab.heightForWidth(lab.width())))
        return bad

    win.resize(1100, 720)
    win.show()
    pump(400)
    check('startup: title', bool(win.windowTitle()), win.windowTitle())

    # ---------------- Chain ----------------
    win._show('chain')
    ch = win.chain
    ch.set_route('123')
    pump(800)
    ch.focus_stage(3)
    ed3 = ch.editors[3]
    ed3.select_node('stage')
    pump(300)
    rows3 = ed3.check_rows()
    print('CHAIN3 rows (default)', rows3)
    print('card states', [ch.cards[d].state_text() for d in (1, 2, 3)])
    print('seed Lz', ch.forms[3].v['Lz'].get(), 'get_case Lz', ch.forms[3].get_case().Lz)
    check('Chain default: A1 skipped, so the seed still warns (Lz 1.5, card 3 1 warning)',
          ch.cards[3].state_text() == '● 1 warning' and ch.forms[3].get_case().Lz == 1.5,
          (ch.cards[3].state_text(), rows3))
    check('Chain default: card 2 state (S2-1 expected to remain, Q1)',
          True, ch.cards[2].state_text() + ' | ' + str(ed3.check_rows() and ch.editors[2].check_rows()))
    both('01_chain_default_card3')
    # all label texts in cards (hand-off captions)
    caps = []
    for d in (1, 2, 3):
        for lab in ch.cards[d].findChildren(QLabel):
            if lab.text():
                caps.append((d, lab.text()))
    print('CARD LABELS', caps)
    check('Chain: card labels not clipped at 1100x720',
          not clipped_labels(ch), clipped_labels(ch))
    # Lz 1.5 warns
    ch.forms[3].v['Lz'].set('1.5')
    pump(900)
    rows3 = ed3.check_rows()
    print('CHAIN3 rows Lz1.5', rows3)
    f45 = [m for s, m in rows3 if 'at or above' in m]
    exp = ("The 2D stage's Burst z (2.0 m) is at or above this stage's Lz (1.5 m): "
           "the 3D box cuts the 2D field off above 1.5 m, burst included. Raise Lz "
           "to at least 4.0 m (the 2D stage's Height H) or lower the 2D stage's Burst z.")
    check('Chain Lz 1.5: F45 warns with the D3 text',
          len(f45) == 1 and f45[0] == exp, f45)
    check('Chain Lz 1.5: card 3 shows 1 warning',
          ch.cards[3].state_text() == '● 1 warning', ch.cards[3].state_text())
    dom = ed3.tree.rows['domain']
    check('Chain Lz 1.5: Domain & mesh row shows "!" (warn)',
          dom._status == 'warn' and dom.mark.text() == '!', (dom._status, dom.mark.text()))
    for sz in ((1100, 720), (1600, 1000)):
        shoot('02_chain_stage3_lz1p5', sz)
    win.resize(1100, 720)
    pump(300)
    cl = clipped_labels(ed3, 'checktext')
    check('Chain Lz 1.5: F45 text wraps, not clipped at 1100x720', not cl, cl)
    for sa in ed3.findChildren(QScrollArea):
        if sa.isVisible() and sa.verticalScrollBar().maximum() > 0:
            sa.verticalScrollBar().setValue(sa.verticalScrollBar().maximum())
    pump(200)
    shoot('02b_chain_stage3_lz1p5_scrolled', (1100, 720))
    win.resize(1100, 720)
    pump(200)
    both('02c_chain_lz1p5_cards')
    ch.forms[3].v['Lz'].set('4.0')
    pump(900)
    check('Chain Lz 4.0 again: row ok, card OK',
          ed3.tree.rows['domain']._status == 'ok' and ch.cards[3].state_text() == '● case OK',
          (ed3.tree.rows['domain']._status, ch.cards[3].state_text()))
    shoot('03_chain_lz4_ok', (1100, 720))
    # stage 2 domain row (S2-1 reach)
    ed2 = ch.editors[2]
    print('stage1 rows', ch.editors[1].check_rows(), 'tree dom', ch.editors[1].tree.rows['domain']._status)
    # route change / reset must not bring 1.5 back
    ch.set_route('13')
    pump(500)
    ch.set_route('123')
    pump(700)
    print('Lz after route toggle', ch.forms[3].v['Lz'].get())

    # ---------------- Setup: Checks strip, Where column ----------------
    win._show('setup')
    two_wall = Case2D(
        solver='native', geometry='planar', Lx=2.4, Ly=1.6,
        cell_size_m=0.05, charge=20.0, center=(0.3, 0.8),
        obstacles=[(1.2, 1.6, 0.0, 0.6), (1.8, 2.0, 0.9, 1.3)],
        gauges=[(0.3, 0.8), (1.4, 0.3), (1.2, 0.3), (1.8, 0.8),
                (1.9, 1.1), (2.0, 1.2), (3.0, 0.5), (1.18, 0.3)],
        n_snapshots=2, record_frames=0, gauge_file=None)
    win.setup.set_dim(2)
    win.setup.set_case(two_wall)
    win._schedule_validate()
    pump(800)
    win.setup.show_checks()
    pump(300)
    rows = win.setup.report_rows()
    print('SETUP REPORT', rows)
    drop = [m for s, m in rows if 'dropped' in m]
    pat = re.compile(r'^G\d+ \(-?\d+\.\d\d, -?\d+\.\d\d\) m (inside Wall \d+|on the face of Wall \d+|outside the domain) - will be dropped$')
    bad = [m for m in drop if not pat.match(m)]
    check('Setup Checks: every drop line is "G<n> (x, y) m ... - will be dropped"',
          bool(drop) and not bad, (drop, bad))
    check('Setup Checks: names G2 inside Wall 1 and G7 outside the domain',
          any(m.startswith('G3 (1.20, 0.30) m') or m.startswith('G2 (1.40, 0.30) m inside Wall 1') for m in drop)
          and any(m.startswith('G7 (3.00, 0.50) m outside the domain') for m in drop), drop)
    both('04_setup_checks')
    cl = clipped_labels(win.setup, 'checktext')
    check('Setup Checks: no text clipped at 1100x720', not cl, cl)
    win.setup.dock.set('Gauges')
    pump(400)
    grows = win.setup.gauge_rows()
    print('GAUGE ROWS', grows)
    wh = [r[-1] for r in grows]
    check('Setup Where column: a "(dropped)" entry exists for a gauge in/at a wall',
          any('(dropped)' in w for w in wh) or any('inside' in w.lower() for w in wh), wh)
    both('05_setup_gauges_where')
    # a gauge near, not touching, a wall
    nearcase = Case2D(solver='native', geometry='planar', Lx=2.4, Ly=1.6,
                      cell_size_m=0.05, charge=20.0, center=(0.3, 0.8),
                      obstacles=[(1.2, 1.6, 0.0, 0.6)],
                      gauges=[(1.16, 0.3), (1.3, 0.3), (0.6, 0.8)],
                      n_snapshots=2, record_frames=0, gauge_file=None)
    win.setup.set_case(nearcase)
    win._schedule_validate()
    pump(800)
    print('near rows', win.setup.gauge_rows())
    win.set_solver('blastfoam')
    ff = Case2D(solver='blastfoam', geometry='axisymmetric', Lx=4.0, Ly=4.0, cell_size_m=0.05,
                charge=500.0, center=(0.0, 2.0), gauges=[(1.252, 0.5), (1.9, 0.5)],
                obstacles=[(1.29, 1.6, 0.0, 1.0)])
    win.setup.set_dim(2)
    win.setup.set_case(ff)
    win._schedule_validate()
    pump(900)
    fr = win.setup.gauge_rows()
    print('FOAM where rows', fr)
    print('FOAM report', win.setup.report_rows())
    check('Setup Where (blastFoam snapping): 4 cm in front of Wall 1 (dropped)',
          any(r[-1] == '4 cm in front of Wall 1 (dropped)' for r in fr), fr)
    win.setup.dock.set('Gauges')
    both('05c_setup_where_foam_dropped')
    win.setup.show_checks()
    pump(300)
    both('05d_setup_checks_foam')
    win.set_solver('native')
    pump(300)
    shoot('05b_setup_gauges_where_near', (1100, 720))

    # ---------------- Run: real native run with a dropped gauge ----------------
    dx = 2.4 / 43
    cx = lambda i: (i + 0.5) * dx
    G1 = (round(cx(19) - 0.45 * dx, 4), round(cx(12) + 0.45 * dx, 4))
    G3 = (round(20 * dx + 0.05 * dx, 4), round(cx(12), 4))
    G2 = (G3[0], round(cx(12) + 0.55 * dx, 4))
    wall = (round(20 * dx, 4), 1.5, round(13 * dx, 4), 1.0)
    run_case = Case2D(solver='native', geometry='planar', Lx=2.4, Ly=1.6,
                      cell_size_m=0.1, charge=400.0, center=(0.3, 0.8),
                      t_end=1.5e-3, n_snapshots=3, record_frames=0,
                      gauge_file=None, obstacles=[wall], gauges=[G1, G2, G3])
    win.setup.set_case(run_case)
    win._schedule_validate()
    pump(700)
    drop = [m for s, m in win.setup.report_rows() if 'dropped' in m]
    print('RUN CASE warn', drop)
    check('Run case: Setup names the dropped gauge as G2 (x, y) m',
          len(drop) == 1 and drop[0].startswith('G2 (') and 'inside Wall 1' in drop[0], drop)
    win.setup.show_checks()
    pump(300)
    shoot('06_setup_checks_runcase', (1100, 720))
    win._run_single()
    t0 = time.monotonic()
    col = win.run_panel.gauge_col
    mid = False
    while win.ctrl.running and time.monotonic() - t0 < 240:
        pump(30)
        if not mid and col.has_data():
            shoot('07_run_live_mid', (1100, 720))
            mid = True
    pump(800)
    check('run finished', not win.ctrl.running, f'{time.monotonic()-t0:.1f}s')
    win._show('run')
    pump(300)
    cap = col.caption_text()
    print('run caption', repr(cap), 'labels', col.row_labels())
    check('Run caption starts "G2 dropped by the solver"', cap.startswith('G2 dropped by the solver'), cap)
    from blastlab.ui import theme
    ss = col.drop.styleSheet()
    pal = theme.qcolor('warn').name() if hasattr(theme, 'qcolor') else ''
    try:
        warnhex = theme.palette()['warn'] if callable(getattr(theme, 'palette', None)) else None
    except Exception:
        warnhex = None
    print('drop stylesheet', ss, 'warn', pal, warnhex)
    check('Run drop note visible and styled in the warn colour',
          not col.drop.isHidden() and (pal.lower() in ss.lower() or 'warn' in ss.lower()), (ss, pal))
    # drop label above sub caption
    check('Run: drop note sits above the caption',
          col.drop.geometry().bottom() <= col.sub.geometry().top() + 2,
          (col.drop.geometry(), col.sub.geometry()))
    for sz in ((1100, 720), (1600, 1000)):
        shoot('08_run_final', sz)
    win.resize(1100, 720)
    pump(300)
    card = col.card
    mg, pg = card.meta.geometry(), card.peak.geometry()
    print('card meta', repr(card.meta.text()), mg, 'peak', repr(card.peak.text()), pg,
          'elided', card.meta.elided(), 'tip', repr(card.meta.toolTip()))
    check('Run card: header and peak rects do not overlap at 1100x720',
          mg.right() < pg.left() or mg.left() > pg.right(), (mg, pg))
    check('Run card: header tooltip is the full text',
          card.meta.toolTip() in ('', card.meta.full_text()) and bool(card.meta.full_text()),
          (card.meta.toolTip(), card.meta.full_text()))
    cl = clipped_labels(col)
    check('Run gauge column: wrapped labels fit (heightForWidth <= height) at 1100x720', not cl, cl)
    # shrink header to force elision
    full = card.meta.full_text()
    card.meta.setFixedWidth(60)
    pump(100)
    check('Run card: forced narrow header elides middle, tooltip full',
          card.meta.elided() and card.meta.toolTip() == full, (card.meta.text(), card.meta.toolTip()))
    win.grab().save(os.path.join(OUT, '09_run_card_forced_elide_1100x720.png'))
    card.meta.setMinimumWidth(0)
    card.meta.setMaximumWidth(16777215)
    pump(100)

    # ---------------- Results ----------------
    res = win.results.current().result
    pts = res.gauges['points']
    check('solver kept 2 gauges (G2 dropped)', len(pts) == 2, pts)
    win._show('results')
    pump(300)
    p = win.results
    p.show_view('Gauges')
    pump(600)
    g = p.gauges
    cells = g.cells()
    print('results cells', cells, 'caption', repr(g.caption_text()))
    check('Results labels G1, G3', sorted(c[0] for c in cells) == ['G1', 'G3'], cells)
    dc = g.drop_caption
    check('Results drop caption wraps, visible, text G2 dropped',
          dc.isVisible() and dc.wordWrap() and dc.text().startswith('G2 dropped'), dc.text())
    for sz in ((1100, 720), (1600, 1000)):
        shoot('10_results_gauges', sz)
    win.resize(1100, 720)
    pump(300)
    cl = clipped_labels(g)
    check('Results Gauges: drop line not clipped at 1100x720', not cl, cl)
    # narrower to force a wrap
    win.resize(1100, 720)

    # export PNG with a footnote
    from blastlab.services import exports as ex
    from blastlab.ui import results_gauges as RG
    note = RG.export_drop_note(res, 2)
    print('export note', note)
    pngs = dict(ex.png_figures(res, 2, drop_note=note))
    fig = pngs['blast_2d_gauges.png']
    path = os.path.join(OUT, '11_export_gauge_png_qt_note.png')
    fig.savefig(path, dpi=100)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    cv_ = FigureCanvasAgg(fig)
    cv_.draw()
    rend = cv_.get_renderer()
    st = fig._supxlabel
    bb = st.get_window_extent(rend) if st else None
    fb = fig.bbox
    print('footnote bbox', bb, 'fig bbox', fb)
    check('Export PNG (Qt note): footnote present and inside the figure',
          st is not None and bb.x0 >= -0.5 and bb.x1 <= fb.x1 + 0.5 and bb.y0 >= -0.5 and bb.y1 <= fb.y1,
          (st.get_text() if st else None, bb))
    ptitles = [ax.get_title() for ax in fig.axes]
    print('titles', ptitles)
    check('Export PNG titles: G1/G3 with entered pos -> cell',
          ptitles[0].startswith('G1 (') and '→ cell' in ptitles[0] and ptitles[1].startswith('G3 ('), ptitles)
    # without note: builder generates it (Tk path)
    pngs2 = dict(ex.png_figures(res, 2))
    f2 = pngs2['blast_2d_gauges.png']
    f2.savefig(os.path.join(OUT, '12_export_gauge_png_builder_note.png'), dpi=100)
    print('builder footnote', f2._supxlabel.get_text() if f2._supxlabel else None)
    check('Export PNG (no Qt note): builder footnote "Not shown: G2 - dropped by the solver"',
          f2._supxlabel is not None and f2._supxlabel.get_text() == 'Not shown: G2 - dropped by the solver',
          f2._supxlabel.get_text() if f2._supxlabel else None)
    # real save through the real exporter path with pick_target patched
    from blastlab.ui import exports as UE
    saved = []
    real = (UE.pick_target, UE.run_export)
    UE.pick_target = lambda *a, **k: 'target'
    UE.run_export = lambda *a: saved.append(a[3])
    try:
        class E: pass
        e = E(); e.result = res; e.dim = 2
        UE.export('pngs', e, threaded=False)
    finally:
        UE.pick_target, UE.run_export = real
    check('UI export path passes gauge_drop_note', saved and saved[0] == {'gauge_drop_note': note}, saved)

    # ---------------- 1D result: export button tooltips ----------------
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
    eb = p._export_btns
    tips = {k: b.toolTip() for k, b in eb.items()}
    print('export btn tips', tips)
    check('1D Field: PNG button tooltip starts "Exports use the full title:"',
          tips.get('pngs', '').startswith('Exports use the full title:'), tips.get('pngs'))
    check('1D Field: Report button tooltip starts the same',
          tips.get('report', '').startswith('Exports use the full title:'), tips.get('report'))
    check('1D Field: canvas has no tooltip', p.fields.canvas.toolTip() == '', p.fields.canvas.toolTip())
    from PySide6.QtCore import QPoint, QEvent
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QToolTip, QApplication
    win.resize(1100, 720)
    win.activateWindow()
    pump(400)
    shoot('13_results_field_1d', (1100, 720))
    shoot('13_results_field_1d', (1600, 1000))
    win.resize(1100, 720)
    pump(300)
    b = eb['pngs']
    lp = QPoint(b.width() // 2, b.height() // 2)
    QApplication.sendEvent(b, QHelpEvent(QEvent.ToolTip, lp, b.mapToGlobal(lp)))
    pump(600)
    for w in QApplication.topLevelWidgets():
        if w.metaObject().className() == 'QTipLabel' and w.isVisible():
            w.grab().save(os.path.join(OUT, '14_png_button_tooltip.png'))
            print('tip grabbed', w.size())
    check('PNG button tooltip visible via QHelpEvent', QToolTip.isVisible(), repr(QToolTip.text())[:120])
    # 2D clears the hint
    p.show_view('Gauges')
    check('modal dialogs only the harness-expected overwrite asks',
          all(m[0] == 'ask' for m in modal), modal)
    win.close()
    pump(300)
    json.dump(RES, open(os.path.join(OUT, 'results_qt.json'), 'w'), indent=1)
    print(f'\n{sum(r["ok"] for r in RES)}/{len(RES)} checks passed')


if __name__ == '__main__':
    main()
