"""GUI-15 QA driver (Qt, real platform, native solver). Not committed to tests/."""
import os, sys, json, time, re
REPO = r'C:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
sys.path.insert(0, REPO)
OUT = os.path.join(REPO, 'docs', 'qa', '2026-10-11-gui-15-qa')
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
    from blastlab.core.case import Case1D, Case2D
    from blastlab.ui.app import MainWindow

    win = MainWindow()
    win.set_solver('native')
    testing.use_model(win, 'gui15qa')
    win.resize(1100, 720)
    win.show()
    pump(500)

    def shoot(name, size=(1100, 720)):
        win.resize(*size)
        pump(300)
        win.raise_()
        win.grab().save(os.path.join(OUT, f'{name}_{size[0]}x{size[1]}.png'))

    def both(name):
        for sz in ((1100, 720), (1600, 1000)):
            shoot(name, sz)
        win.resize(1100, 720)
        pump(250)

    WALL = (1.2, 1.6, 0.0, 0.6)

    def c2(gauges, trig=3, **kw):
        return Case2D(solver='native', geometry='planar', Lx=2.4, Ly=1.6,
                      cell_size_m=0.04, charge=20.0, center=(0.6, 0.0),
                      obstacles=[WALL],
                      bcs=dict(x_lo='reflect', x_hi='terminate', y_lo='reflect', y_hi='terminate'),
                      gauges=gauges, n_snapshots=3, record_frames=0, gauge_file=None,
                      trigger_gauge=trig, trigger_action='terminate', **kw)

    G = [(0.3, 0.8), (1.4, 0.3), (0.6, 0.5), (1.0, 1.0)]     # G2 strictly inside
    NEAR = [(0.3, 0.8), (1.195, 0.3), (0.6, 0.5), (1.0, 1.0)]  # G2 within a cell of Wall 1 face (x0=1.2)

    # ---------- Setup: Checks for 3 variants ----------
    win._show('setup')
    win.setup.set_dim(2)
    for tag, gs, trig in (('inside', G, 3), ('near', NEAR, 3), ('trigdrop', G, 2)):
        win.setup.set_case(c2(gs, trig))
        win._schedule_validate()
        pump(900)
        rows = win.setup.report_rows()
        print(tag, 'REPORT', rows)
        win.setup.show_checks()
        pump(300)
        shoot(f'01_setup_checks_{tag}')
        txt = ' | '.join(m for s, m in rows)
        if tag == 'inside':
            check('Checks (inside): "inside Wall 1" for G2', 'G2' in txt and 'inside Wall 1' in txt, txt)
        if tag == 'near':
            check('Checks (near): "within a cell of Wall 1", no "on the face of"',
                  'within a cell of Wall 1' in txt and 'on the face of' not in txt, txt)
        if tag == 'trigdrop':
            check('Checks (trigger on dropped G2): trigger-disabled warning names G2 and trigger',
                  re.search(r'(?i)trigger', txt) and 'G2' in txt and 'disabled' in txt.lower(), txt)

    # ---------- Setup gauges node + table ----------
    win.setup.set_case(c2(G, 3))
    win._schedule_validate()
    pump(900)
    node = win.setup.tree.rows['gauges']
    from PySide6.QtWidgets import QLabel
    def treeinfo(tree, nid):
        labs = [l.text() + ('  {TIP: ' + l.toolTip() + '}' if l.toolTip() else '') for l in tree.rows[nid].findChildren(QLabel)] + ['ROWTIP ' + tree.rows[nid].toolTip()]
        kids = [(k.name.text(), k.value.text(), k.warn) for k in tree._kids[nid][1]]
        return labs, kids
    labs, kids = treeinfo(win.setup.tree, 'gauges')
    print('Setup gauges node labels', labs, 'children', kids)
    check('Setup node caption names G2 dropped', any('G2 dropped' in l for l in labs) and any(l.endswith('…') or '…' in l for l in labs), labs)
    check('Setup G2 child warn, G1 not', len(kids) >= 2 and kids[1][2] and not kids[0][2], kids)
    win.setup.select_node('gauges')
    pump(400)
    both('02_setup_gauges_node')
    win.setup.dock.set('Gauges')
    pump(300)
    print('gauge rows', win.setup.gauge_rows())
    both('03_setup_gauges_table')

    # ---------- Chain stage 2 ----------
    win._show('chain')
    ch = win.chain
    ch.set_route('123')
    pump(900)
    ch.forms[2].set_case(c2(G, 3))
    ch.forms[2].points['gauges']._on_change()
    pump(900)
    ch.focus_stage(2)
    ch.editors[2].select_node('gauges')
    pump(500)
    st = ch.editors[2].tree.rows['gauges']._status
    check('Chain stage 2 Gauges node warn', st == 'warn', st)
    print('chain stage2 check rows', ch.editors[2].check_rows())
    print('chain stage2 node', treeinfo(ch.editors[2].tree, 'gauges'))
    both('04_chain_stage2_gauges_node')

    # ---------- 1D setup ----------
    win._show('setup')
    win.setup.set_dim(1)
    pump(300)
    c1 = Case1D(solver='native', radius_m=1.5, gauge_radii=[1.0, 2.0, 1.2], charge_kg=1.0, cell_size_m=0.005, gauge_file=None, n_snapshots=3)
    win.setup.set_case(c1)
    win._schedule_validate()
    pump(900)
    print('1D report', win.setup.report_rows())
    txt = ' | '.join(m for s, m in win.setup.report_rows())
    check('1D Checks: warns G2 outside the domain', 'G2' in txt and 'outside the domain' in txt, txt)
    win.setup.show_checks()
    pump(300)
    shoot('05_setup_checks_1d')
    n1 = win.setup.tree.rows['gauges']
    print('1D gauges node status', n1._status, treeinfo(win.setup.tree, 'gauges'))
    check('1D Gauges node warn', n1._status == 'warn', n1._status)
    win.setup.select_node('gauges')
    pump(400)
    both('06_setup_gauges_node_1d')
    win.setup.dock.set('Gauges')
    pump(300)
    print('1D gauge rows', win.setup.gauge_rows())
    shoot('07_setup_gauges_table_1d')

    # ---------- chain stage 1 1D ----------
    win._show('chain')
    ch.focus_stage(1)
    ch.forms[1].set_case(c1)
    pump(900)
    ch.editors[1].select_node('gauges')
    pump(500)
    s1 = ch.editors[1].tree.rows['gauges']._status
    print('chain stage1 gauges status', s1, ch.editors[1].check_rows())
    shoot('08_chain_stage1_gauges_1d')

    # ---------- Run 2D ----------
    win._show('setup')
    win.setup.set_dim(2)
    win.setup.set_case(c2(G, 3))
    win._schedule_validate()
    pump(800)
    win._run_single()
    win._show('run')
    got_pre = False
    shots = 0
    t0 = time.monotonic()
    while win.ctrl.running and time.monotonic() - t0 < 300:
        pump(40)
        col = win.run_panel.gauge_col
        if not got_pre:
            got_pre = True
            print('PRE rows', col.row_labels(), 'cap', repr(col.caption_text()))
            win.grab().save(os.path.join(OUT, '09_run_start_pre_payload_1100x720.png'))
            check('Run pre-payload: no G2 row, drop line names G2 and Wall 1',
                  'G2' not in ' '.join(col.row_labels()) and 'G2' in col.caption_text() and 'Wall 1' in col.caption_text(),
                  (col.row_labels(), col.caption_text()))
        elif shots < 3 and col.row_labels() and time.monotonic() - t0 > 1.0 + shots * 1.5:
            win.grab().save(os.path.join(OUT, f'10_run_live_{shots}_1100x720.png'))
            print('LIVE rows', col.row_labels(), repr(col.caption_text()))
            shots += 1
    pump(900)
    check('2D run finished', not win.ctrl.running, f'{time.monotonic()-t0:.1f}s')
    log = win.run_panel.log.toPlainText()
    lines = [l for l in log.splitlines() if 'dropped' in l or 'rigger' in l or 'stop' in l.lower()]
    print('LOG', lines)
    check('Log names the wall: "G2 ... inside Wall 1 - dropped"', any(re.search(r'\[warn\] G2 .*inside Wall 1 - dropped', l) for l in lines), lines)
    col = win.run_panel.gauge_col
    print('POST rows', col.row_labels(), repr(col.caption_text()))
    check('Run rows after run: G1 G3 G4', [x.split()[0] for x in col.row_labels()] == ['G1', 'G3', 'G4'] if col.row_labels() else False, col.row_labels())
    both('11_run_after')

    # ---------- Results ----------
    win._show('results')
    pump(400)
    p = win.results
    p.show_view('Gauges')
    pump(800)
    g = p.gauges
    print('RESULTS drop', repr(g.drop_caption.text()), 'labels', g._labels, 'order', g._order)
    print('RESULTS selected', getattr(g, '_sel', None))
    try:
        print('meta', {k: p.current_result().meta.get(k) for k in ('trigger_gauge', 'gauges_dropped', 'trigger')} if hasattr(p, 'current_result') else 'n/a')
    except Exception as e:
        print('meta err', e)
    both('12_results_gauges_2d')

    # ---------- 1D run ----------
    win._show('setup')
    win.setup.set_dim(1)
    win.setup.set_case(Case1D(solver='native', radius_m=1.5, gauge_radii=[1.0, 2.0, 1.2], charge_kg=1.0, cell_size_m=0.005, gauge_file=None, n_snapshots=3))
    win._schedule_validate()
    pump(800)
    win._run_single()
    win._show('run')
    pre1 = False
    t0 = time.monotonic()
    while win.ctrl.running and time.monotonic() - t0 < 200:
        pump(30)
        if not pre1:
            pre1 = True
            c = win.run_panel.gauge_col
            print('1D PRE rows', c.row_labels(), repr(c.caption_text()))
            win.grab().save(os.path.join(OUT, '13_run_1d_start_1100x720.png'))
    pump(900)
    log = win.run_panel.log.toPlainText()
    l1 = [l for l in log.splitlines() if 'dropped' in l]
    print('1D LOG', l1)
    check('1D log: G2 (r 2.00 m) outside the domain - dropped', any('G2' in l and 'outside the domain' in l for l in l1), l1)
    c = win.run_panel.gauge_col
    print('1D POST rows', c.row_labels(), repr(c.caption_text()))
    check('1D Run column: G1 and G3', [x.split()[0] for x in c.row_labels()] == ['G1', 'G3'] if c.row_labels() else False, c.row_labels())
    both('14_run_1d_after')
    win._show('results')
    pump(400)
    win.results.show_view('Gauges')
    pump(800)
    g = win.results.gauges
    print('1D RESULTS drop', repr(g.drop_caption.text()), g._labels, g._order)
    check('1D Results: labels G1 G3 and drop line names G2',
          list(g._labels.values()) == ['G1', 'G3'] and 'G2' in g.drop_caption.text(), (g._labels, g.drop_caption.text()))
    both('15_results_gauges_1d')

    print('modal', modal)
    check('no modal dialogs', not modal, modal)
    win.close()
    pump(300)
    json.dump(RES, open(os.path.join(OUT, 'results_qt.json'), 'w'), indent=1)
    print(f'\n{sum(r["ok"] for r in RES)}/{len(RES)} checks passed')


if __name__ == '__main__':
    main()
