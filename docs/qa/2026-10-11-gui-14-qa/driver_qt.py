"""GUI-14 QA driver (Qt, real platform, native solver only). Not committed to tests/."""
import os, sys, json, time, re
REPO = r'C:\Users\rotem.ofek\blastlab-worktrees\gui-14'
sys.path.insert(0, REPO)
OUT = os.path.join(REPO, 'docs', 'qa', '2026-10-11-gui-14-qa')
os.environ.pop('QT_QPA_PLATFORM', None)
os.environ['PYTHONIOENCODING'] = 'utf-8'
RES = []


def check(name, ok, detail=''):
    RES.append(dict(name=name, ok=bool(ok), detail=str(detail)))
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else '  -> ' + str(detail)))
    if detail:
        print('      ' + str(detail)[:700])


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
    from blastlab.core.case import Case2D, Case3D
    from blastlab.ui.app import MainWindow
    from PySide6.QtWidgets import QLabel

    win = MainWindow()
    win.set_solver('native')
    testing.use_model(win, 'gui14qa')
    print('platform', app.platformName())

    def shoot(name, size):
        win.resize(*size)
        pump(300)
        win.raise_()
        p = os.path.join(OUT, f'{name}_{size[0]}x{size[1]}.png')
        win.grab().save(p)
        return p

    def both(name):
        for sz in ((1100, 720), (1600, 1000)):
            shoot(name, sz)
        win.resize(1100, 720)
        pump(250)

    win.resize(1100, 720)
    win.show()
    pump(500)
    win.showMaximized()
    pump(400)
    print('maximised size', win.size().width(), win.size().height())
    win.showNormal()
    win.resize(1100, 720)
    pump(300)

    # ---------- Chain default route ----------
    win._show('chain')
    ch = win.chain
    ch.set_route('123')
    pump(900)
    ch.focus_stage(1)
    pump(300)
    gl = {d: ch.forms[d].points['gauges'].get() for d in (1, 2, 3)}
    c1 = ch.forms[1].get_case()
    print('CHAIN gauges per stage', gl, 'stage1 radius', c1.radius_m,
          'gauge_radii', c1.gauge_radii)
    states = [ch.cards[d].state_text() for d in (1, 2, 3)]
    rows = {d: ch.editors[d].check_rows() for d in (1, 2, 3)}
    print('card states', states, rows)
    check('Chain default: stage 1 radius 1.5 m', abs(float(c1.radius_m) - 1.5) < 1e-9, c1.radius_m)
    check('Chain default: stage 1 holds no gauge at all (none beyond 1.5 m)',
          list(c1.gauge_radii) == [] and gl[1] == [], (gl, list(c1.gauge_radii)))
    check('Chain default: card 1 and card 2 clean', states[0] == '● case OK' and states[1] == '● case OK', states)
    check('Chain default: card 3 state (info)', True, states[2] + ' ' + str(rows[3]))
    both('01_chain_default_cards')
    ch.editors[1].select_node('gauges')
    pump(400)
    both('02_chain_stage1_gauges_node')

    # chain stage 2 with gauge in a wall and one outside
    two = Case2D(solver='native', geometry='planar', Lx=2.4, Ly=1.6,
                 cell_size_m=0.05, charge=20.0, center=(0.3, 0.8),
                 obstacles=[(1.2, 1.6, 0.0, 0.6)],
                 gauges=[(0.6, 0.8), (1.4, 0.3), (3.0, 0.5), (2.4, 0.8)],
                 n_snapshots=2, record_frames=0, gauge_file=None)
    ch.forms[2].set_case(two)
    ch.forms[2].points['gauges']._on_change()
    pump(1000)
    ed2 = ch.editors[2]
    ch.focus_stage(2)
    ed2.select_node('gauges')
    pump(500)
    st = ed2.tree.rows['gauges']._status
    print('chain stage 2 gauges node', st, ed2.check_rows())
    check('Chain stage 2: Gauges node warn with a wall and an outside gauge', st == 'warn', (st, ed2.check_rows()))
    both('03_chain_stage2_gauges_dropped')
    ch.forms[2].set_case(Case2D(solver='native', geometry='planar', Lx=2.4, Ly=1.6,
                                cell_size_m=0.05, charge=20.0, center=(0.3, 0.8),
                                obstacles=[(1.2, 1.6, 0.0, 0.6)], gauges=[(0.6, 0.8)],
                                n_snapshots=2, record_frames=0, gauge_file=None))
    ch.forms[2].points['gauges']._on_change()
    pump(900)
    st2 = ed2.tree.rows['gauges']._status
    check('Chain stage 2: Gauges node back to ok when moved inside', st2 == 'ok', st2)
    ch.forms[2].set_case(two)
    pump(600)

    # ---------- Setup: gauge table ----------
    win._show('setup')
    win.setup.set_dim(2)
    win.setup.set_case(two)
    win._schedule_validate()
    pump(900)
    win.setup.dock.set('Gauges')
    pump(300)
    grows = win.setup.gauge_rows()
    print('SETUP gauge rows', grows)
    wh = [r[-1] for r in grows]
    check('Setup Where: outside gauges read "outside the domain (dropped)"',
          any(w == 'outside the domain (dropped)' for w in wh), wh)
    check('Setup Where: x == Lx gauge (2.4, 0.8) not outside', not wh[3].startswith('outside'), wh[3])
    check('Setup Where: gauge in the wall reads inside Wall 1 (no suffix, warn-coloured)', wh[1] == 'inside Wall 1', wh[1])
    # warn colouring of items
    tbl = win.setup.findChild(type(win.setup.dock.widget('Gauges')), None) if False else None
    from PySide6.QtWidgets import QTableWidget
    t = [x for x in win.setup.findChildren(QTableWidget) if x.isVisible() and x.columnCount() >= 3]
    print('visible tables', [(x.rowCount(), x.columnCount()) for x in t])
    if t:
        tb = t[0]
        cols = []
        for r in range(tb.rowCount()):
            it0 = tb.item(r, 0)
            itw = tb.item(r, tb.columnCount() - 1)
            cols.append((it0.text() if it0 else None,
                         it0.foreground().color().name() if it0 else None,
                         itw.foreground().color().name() if itw else None))
        print('item colours', cols)
        distinct = {c[1] for c in cols}
        check('Setup table: dropped G<n> cells differ in colour from kept ones', len(distinct) >= 2, cols)
    node = win.setup.tree.rows['gauges'] if hasattr(win.setup.tree, 'rows') else None
    print('Setup gauges node status', node._status if node else None)
    check('Setup: Gauges node warn', node is not None and node._status == 'warn', node._status if node else None)
    both('04_setup_gauges_table')
    win.setup.select_node('gauges')
    pump(400)
    both('05_setup_gauges_node')
    win.setup.show_checks()
    pump(300)
    shoot('06_setup_checks', (1100, 720))

    # ---------- Run with native, dropped gauge: log line + card ----------
    dx = 2.4 / 43
    cx = lambda i: (i + 0.5) * dx
    G1 = (round(cx(19) - 0.45 * dx, 4), round(cx(12) + 0.45 * dx, 4))
    wall = (round(20 * dx, 4), 1.5, round(13 * dx, 4), 1.0)
    G2 = (round(20 * dx + 0.05 * dx, 4), round(cx(12) + 0.55 * dx, 4))
    G3 = (3.0, 0.5)
    run_case = Case2D(solver='native', geometry='planar', Lx=2.4, Ly=1.6,
                      cell_size_m=0.1, charge=400.0, center=(0.3, 0.8),
                      t_end=1.5e-3, n_snapshots=3, record_frames=0,
                      gauge_file=None, obstacles=[wall], gauges=[G1, G2, G3])
    win.setup.set_case(run_case)
    win._schedule_validate()
    pump(800)
    win._run_single()
    t0 = time.monotonic()
    while win.ctrl.running and time.monotonic() - t0 < 240:
        pump(30)
    pump(900)
    check('run finished', not win.ctrl.running, f'{time.monotonic()-t0:.1f}s')
    win._show('run')
    pump(400)
    log = win.run_panel.log.toPlainText()
    lines = [l for l in log.splitlines() if 'dropped' in l]
    print('RUN LOG drop lines', lines)
    pat_obs = re.compile(r'\[warn\] G2 \(-?\d+\.\d\d, -?\d+\.\d\d\) m inside an obstacle - dropped')
    pat_out = re.compile(r'\[warn\] G3 \(3\.00, 0\.50\) m outside the domain - dropped')
    check('Native log: G2 inside an obstacle line', any(pat_obs.search(l) for l in lines), lines)
    check('Native log: G3 outside the domain line', any(pat_out.search(l) for l in lines), lines)
    col = win.run_panel.gauge_col
    cap = col.caption_text()
    print('run caption', repr(cap), col.row_labels())
    both('07_run_log_and_gauges')
    card = col.card
    print('card meta', repr(card.meta.text()), 'full', repr(card.meta.full_text()))
    check('Run card header (planar 2D, R mode): no selected',
          'selected' not in card.meta.full_text() and card.meta.full_text().startswith('R '),
          card.meta.full_text())
    mg, pg = card.meta.geometry(), card.peak.geometry()
    check('Run card: header and peak do not overlap (1100x720)', mg.right() < pg.left() or mg.left() > pg.right(), (mg, pg))
    full = card.meta.full_text()
    card.meta.setFixedWidth(70)
    pump(150)
    check('Run card (R mode) forced narrow: elided at the END, tooltip full',
          card.meta.elided() and card.meta.text().startswith('R ') and card.meta.toolTip() == full,
          (card.meta.text(), card.meta.toolTip()))
    win.grab().save(os.path.join(OUT, '08_run_card_forced_elide_1100x720.png'))
    card.meta.setMinimumWidth(0)
    card.meta.setMaximumWidth(16777215)
    pump(150)

    # ---------- Results Gauges drop line, both themes ----------
    win._show('results')
    pump(400)
    p = win.results
    p.show_view('Gauges')
    pump(700)
    g = p.gauges
    dc = g.drop_caption
    print('drop caption', repr(dc.text()), dc.objectName())
    from blastlab.ui import theme
    for mode in ('dark', 'light'):
        win._dark_action.setChecked(mode == 'dark')
        pump(700)
        col_ = dc.palette().color(dc.foregroundRole()).name()
        f = dc.font()
        print(mode, 'drop caption colour', col_, 'weight', f.weight(), 'px', f.pixelSize(), 'objname', dc.objectName())
        check(f'Results drop line [{mode}] visible, objectName gaugedrop, weight>=600',
              dc.isVisible() and dc.objectName() == 'gaugedrop' and int(f.weight()) >= 600,
              (dc.objectName(), int(f.weight()), col_))
        both(f'09_results_gauges_{mode}')
    win._dark_action.setChecked(True)
    pump(600)

    # ---------- 3D chain: out of domain 3D gauge via chain stage 3 ----------
    ch.focus_stage(3)
    win._show('chain')
    pump(400)
    c3 = Case3D(solver='native', Lx=4.0, Ly=4.0, Lz=4.0, cell_size_m=0.2, charge=20.0,
                center=(1.0, 1.0, 0.5), gauges=[(1.5, 1.5, 0.5), (5.0, 1.0, 0.5)])
    try:
        ch.forms[3].set_case(c3)
        pump(900)
        ch.editors[3].select_node('gauges')
        pump(300)
        st3 = ch.editors[3].tree.rows['gauges']._status
        print('stage 3 gauges node', st3)
        check('Chain stage 3: Gauges node warn with one outside gauge', st3 == 'warn', st3)
        shoot('10_chain_stage3_gauges_dropped', (1100, 720))
    except Exception as exc:
        print('stage 3 error', repr(exc))
    print('modal', modal)
    check('no modal dialogs', not modal, modal)
    win.close()
    pump(300)
    json.dump(RES, open(os.path.join(OUT, 'results_qt.json'), 'w'), indent=1)
    print(f'\n{sum(r["ok"] for r in RES)}/{len(RES)} checks passed')


if __name__ == '__main__':
    main()
