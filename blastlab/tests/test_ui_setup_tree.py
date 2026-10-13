"""GUI-5a: the Setup model tree and its properties column.

T1 - the FieldForm 'nodes' placement and the node registry: every spec
field is reachable through exactly one node (plan §10), and the 'nodes'
placement changes where cards are laid, never what they parse or which
rows the solver scope shows.

T5 - (GUI-10, F21) the case pill and + buttons at the board heights;
real platform only (`--real`), skipped offscreen.

Headless: offscreen Qt, no window shown, no solver run.
Run:  cd blastlab/tests && python test_ui_setup_tree.py
      python test_ui_setup_tree.py --real     (T5 on the real platform)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.ui.testing import ensure_qapp, pump          # noqa: E402

# the check names carry '✓' / '✗' / '·', outside cp1252 - the encoding of
# a redirected stdout here; never let a print kill the suite over a glyph
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

#: GUI-10 (F21): `--real` runs only T5, the height check, on the real
#: platform (a window shows briefly); the default run is offscreen
REAL = '--real' in sys.argv[1:]
app = ensure_qapp(offscreen=not REAL)

from blastlab.core.case import Case1D, Case2D, Case3D      # noqa: E402
from blastlab.ui import setup_nodes, setup_spec            # noqa: E402
from blastlab.ui.case_form import CaseForm                 # noqa: E402

FAIL = []
RAN = []
MODES = ('native', 'blastfoam')


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def form(dim, mode='blastfoam', placement='columns'):
    f = CaseForm(dim, mode=mode, placement=placement)
    f.resize(340 if placement == 'nodes' else 900, 700)
    f.show()
    pump(30)
    return f


def same_case(a, b):
    """vars() equality with a float tolerance."""
    va, vb = vars(a), vars(b)
    if set(va) != set(vb):
        return False, str(set(va) ^ set(vb))
    diffs = []
    for k, x in va.items():
        y = vb[k]
        same = (abs(x - y) < 1e-12 if isinstance(x, float)
                and isinstance(y, float) else x == y)
        if not same:
            diffs.append(f'{k}: {x!r} vs {y!r}')
    return not diffs, '; '.join(diffs[:3])


def t1_registry():
    print('\nT1a: every spec field is reachable through exactly one node')
    for d in (1, 2, 3):
        table = setup_nodes.nodes(d)
        titles = [t for _n, ts in table for t in ts]
        check(f'{d}D: no card sits in two nodes',
              len(titles) == len(set(titles)), str(titles))
        check(f'{d}D: node numbers are 01-07, fixed',
              [n.number for n, _t in table]
              == ['01', '02', '03', '04', '05', '06', '07'])
        for mode in MODES:
            f = form(d, mode)
            check(f'{d}D {mode}: the node cards are exactly the form cards',
                  set(titles) == set(f.cards),
                  str(set(titles) ^ set(f.cards)))
            names = [x.name for x in setup_spec.fields(d)]
            owners = {n: [node.id for node, ts in table
                          if f._card_of.get(n) in ts] for n in names}
            multi = {n: o for n, o in owners.items() if len(o) != 1}
            check(f'{d}D {mode}: each of the {len(names)} spec fields '
                  f'maps to exactly one node', not multi, str(multi))
            wrong = [n for n in names if setup_nodes.node_of_field(d, n)
                     != owners[n][0]]
            check(f'{d}D {mode}: node_of_field agrees with '
                  f'FieldForm._card_of', not wrong, str(wrong))
            f.deleteLater()
    t1 = dict(setup_nodes.nodes(1))
    check('1D: 04 Structure holds no card (the tree hides it)',
          any(n.id == 'structure' and not ts
              for n, ts in setup_nodes.nodes(1)), str(t1))
    zero = setup_nodes.nodes(0)
    check('0D: one node per visible card, numbered in build order',
          [ts[0] for _n, ts in zero]
          == [c.title for c in setup_spec.cards(0)
              if c.title not in setup_spec.HIDDEN_CARDS_0]
          and [n.number for n, _t in zero]
          == [f'{i:02d}' for i in range(1, len(zero) + 1)])
    check('0D: the hidden Structure card has no node',
          all(setup_nodes.node_of_card(0, t) is None
              for t in setup_spec.HIDDEN_CARDS_0))
    check('0D: every field of a visible card maps to one node',
          all(setup_nodes.node_of_field(0, x.name) is not None
              for c in setup_spec.cards(0)
              if c.title not in setup_spec.HIDDEN_CARDS_0 for x in c.rows))


def t1_placement():
    print("\nT1b: 'nodes' placement lays cards, never parses them")
    for d in (0, 1, 2, 3):
        for mode in (MODES if d else ('blastfoam',)):
            a = form(d, mode, 'columns')
            b = form(d, mode, 'nodes')
            check(f'{d}D {mode}: same registries',
                  list(a.v) == list(b.v) and list(a.points) == list(b.points)
                  and a._card_of == b._card_of
                  and {k: v.get() for k, v in a.v.items()}
                  == {k: v.get() for k, v in b.v.items()})
            # the three rows the Setup screen's dependent rules own (T3:
            # the trigger switch, Profile file only in profile mode)
            own = {'profile_in', 'trigger_gauge', 'trigger_action'}
            check(f'{d}D {mode}: same scope visibility, row by row',
                  {n: a.row_visible(n) for n in a.widgets if n not in own}
                  == {n: b.row_visible(n) for n in b.widgets
                      if n not in own}
                  and {t: a.card_visible(t) for t in a.cards}
                  == {t: b.card_visible(t) for t in b.cards},
                  str([n for n in a.widgets if n not in own
                       and a.row_visible(n) != b.row_visible(n)]))
            if d:
                ok, why = same_case(a.get_case(), b.get_case())
                check(f'{d}D {mode}: the fresh forms build the same Case',
                      ok, why)
            a.deleteLater()
            b.deleteLater()
    for d, cls in ((1, Case1D), (2, Case2D), (3, Case3D)):
        for mode in MODES:
            a = form(d, mode, 'columns')
            b = form(d, mode, 'nodes')
            src = cls(solver=mode)
            a.set_case(src)
            b.set_case(src)
            pump(10)
            ok, why = same_case(a.get_case(), b.get_case())
            check(f'{d}D {mode}: set_case -> get_case identical in both '
                  f'placements', ok, why)
            a.deleteLater()
            b.deleteLater()

    print('\nT1c: the registries still drive the widgets in nodes placement')
    f = form(2, 'native', 'nodes')
    f.v['Lx'].set('6.25')
    f.v['n_procs'].set('7')
    check('native hides the blastFoam cards',
          not f.card_visible('Dynamic refinement (AMR)'))
    f.set_mode('blastfoam')
    check('blastFoam shows them again',
          f.card_visible('Dynamic refinement (AMR)')
          and f.row_visible('activation'))
    f.set_mode('native')
    check('values kept across the switches (S6 in nodes placement)',
          f.v['Lx'].get() == '6.25' and f.v['n_procs'].get() == '7')
    f.mark_fields(['cell'])
    check('mark_fields reaches the widget',
          f.widgets['cell'].property('bad') == 'true' and f.bad == {'cell'})
    f.mark_fields([])
    f.set_label('Lx', 'Lx [m]')
    check('set_label reaches the caption', f.label_text('Lx') == 'Lx [m]')
    f.v['geometry'].set('planar')
    check('the axisymmetric hook still relabels (planar charge caption)',
          f.label_text('charge') == 'Charge [kg TNT/m]'
          and f.is_enabled('cx'))
    f.v['geometry'].set('axisymmetric')
    check('and pins the burst to the axis',
          f.v['cx'].get() == '0' and not f.is_enabled('cx'))
    check('nodes placement is one column; the VTK card is stacked',
          f.single_column() and not f.span_side_by_side(
              'VTK output (ParaView)'))
    grid, _r = f.rows['bc_x_lo']
    check('the boundary grid is one pair per line in the column',
          grid.columnCount() == 2, str(grid.columnCount()))

    print('\nT1d: show_node shows exactly one page')
    f = form(3, 'blastfoam', 'nodes')
    for node, titles in setup_nodes.nodes(3):
        f.show_node(node.id)
        pump(5)
        shown = {t for t, c in f.cards.items() if c.isVisibleTo(f)}
        want = {t for t in titles if f.card_visible(t)}
        check(f'3D {node.number} {node.title}: only its cards',
              shown == want, f'{sorted(shown)} vs {sorted(want)}')
    check('an unknown node is refused', f.show_node('nope') is False)
    c = form(2)
    check("'columns' has no pages and show_node is a no-op",
          not c.pages and c.show_node('threat') is False)


def sample_case():
    """The boards' sample case (plan §1): 2D axisymmetric, blastFoam,
    1 kg TNT at z = 2 m, 4 x 4 m, cell 0.025 m, Wall 1 at r 3.0-3.2 m,
    gauges G1 (2.95, 0.50) and G2 (2.95, 1.50); the form's boundaries."""
    return Case2D(solver='blastfoam', geometry='axisymmetric', Lx=4.0,
                  Ly=4.0, cell_size_m=0.025, charge=1.0, center=(0.0, 2.0),
                  bcs=dict(setup_spec.BC_DEFAULTS[2]),
                  obstacles=[(3.0, 3.2, 0.0, 2.5)],
                  gauges=[(2.95, 0.5), (2.95, 1.5)])


def t2_panel():
    from PySide6.QtWidgets import QApplication
    from blastlab.core import mode as mode_mod
    from blastlab.ui.setup_panel import PROPS_W, SetupPanel
    from blastlab.ui.setup_tree import TREE_W

    print('\nT2a: selecting a node shows only its cards')
    mode = mode_mod.SolverMode()
    sp = SetupPanel(mode=mode)
    sp.resize(1400, 860)
    sp.show()
    pump(80)
    check('the three columns: tree 280, properties 340',
          sp.tree.width() == TREE_W and sp.props_width() == PROPS_W,
          f'{sp.tree.width()} / {sp.props_width()}')
    for m in MODES:
        mode.set(m)
        pump(30)
        for d in (0, 1, 2, 3):
            sp.set_dim(d)
            pump(30)
            f = sp.form
            for node, titles in setup_nodes.nodes(d):
                want = [t for t in titles if f.card_visible(t)]
                in_tree = node.id in sp.visible_nodes()
                if not want:
                    check(f'{m} {d}D {node.number}: a node with no card '
                          f'is hidden, never greyed', not in_tree)
                    continue
                ok = sp.select_node(node.id)
                pump(10)
                check(f'{m} {d}D {node.number} {node.title}: only its '
                      f'cards', ok and in_tree
                      and sp.shown_cards() == want
                      and sp.selected_node() == node.id,
                      f'{sp.shown_cards()} vs {want}')
    mode.set('blastfoam')
    sp.set_dim(1)
    check('1D: no 04 Structure in the tree',
          'structure' not in sp.visible_nodes(), str(sp.visible_nodes()))
    mode.set('native')
    pump(20)
    check('native 1D: 07 Output is hidden (its only card is VTK)',
          'output' not in sp.visible_nodes(), str(sp.visible_nodes()))
    mode.set('blastfoam')
    sp.set_dim(2)
    sp.select_node('gauges')
    sp.set_dim(3)
    check('05 Gauges stays selected from 2D to 3D',
          sp.selected_node() == 'gauges')
    sp.set_dim(0)
    check('0D starts on its first card node, 01',
          sp.selected_node() == setup_nodes.nodes(0)[0][0].id)
    sp.set_dim(2)

    print('\nT2b: the pill tracks show_report; the report order stays')
    sp.show_report([], [], ['n1', 'n2', 'n3', 'n4'])
    check("0 errors / 0 warnings / 4 notes -> 'Case OK · 4 notes'",
          sp.pill() == ('ok', 'Case OK · 4 notes'), str(sp.pill()))
    sp.show_report(['e1', 'e2'])
    check("2 errors -> '2 errors' in danger",
          sp.pill() == ('error', '2 errors'), str(sp.pill()))
    sp.show_report(['e1'], ['w1', 'w2'], ['n1'])
    check('report_rows keeps error, warn, note order',
          [r[0] for r in sp.report_rows()] == ['error', 'warn', 'warn',
                                               'note'])
    sp.show_report()
    check("an empty report: 'Case OK' row and pill",
          sp.report_rows() == [('ok', 'Case OK')]
          and sp.pill() == ('ok', 'Case OK'))
    sp.show_report([], ['w'], [])
    check('a warning keeps Case OK and says so',
          sp.pill() == ('warn', 'Case OK · 1 warning'), str(sp.pill()))
    from blastlab.ui import theme

    def ratio(a, b):
        def lum(h):
            c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
                 for x in c]
            return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)
    worst = min(ratio(p['text2'], p['ok_bg']) for p in (theme.DARK,
                                                        theme.LIGHT))
    worst_e = min(ratio(p['stop_text'], p['stop_bg'])
                  for p in (theme.DARK, theme.LIGHT))
    check('the pill text reaches 4.5:1 in both modes (plan §2.2)',
          worst >= 4.5 and worst_e >= 4.5, f'{worst:.2f} / {worst_e:.2f}')
    check('the state colour rides on the pill icon',
          not sp.tree.pill.icon().isNull())

    print('\nT2c: children, + Gauge / + Obstacle, summaries, marks')
    sp.set_case(sample_case())
    case = sp.get_case()
    from blastlab.core.case import validate_case
    rep = validate_case(case)
    sp.refresh(case, rep)
    pump(30)
    t = sp.tree
    check('one child row per gauge (G1 · 2.95, 0.50)',
          t.children('gauges') == [('G1', '2.95, 0.50'),
                                   ('G2', '2.95, 1.50')],
          str(t.children('gauges')))
    check('one child row per obstacle (Wall 1 · r 3.0–3.2)',
          t.children('structure') == [('Wall 1', 'r 3.0–3.2')],
          str(t.children('structure')))
    sp.select_node('threat')
    t.child_row('gauges', 1).clicked.emit()
    pump(30)
    pl = sp.form.points['gauges']
    check('clicking G2 selects 05 Gauges and its row in the list',
          sp.selected_node() == 'gauges'
          and pl.tree.indexOfTopLevelItem(pl.tree.currentItem()) == 1)
    t.child_row('structure', 0).clicked.emit()
    pump(30)
    check('clicking Wall 1 selects 04 Structure',
          sp.selected_node() == 'structure')
    sp.activateWindow()
    sp.select_node('threat')
    t.add_gauge_btn.click()
    pump(40)
    check('+ Gauge selects 05 and focuses the gauge entry',
          sp.selected_node() == 'gauges'
          and QApplication.focusWidget() is sp.form.points['gauges'].entry,
          type(QApplication.focusWidget()).__name__)
    t.add_obstacle_btn.click()
    pump(40)
    check('+ Obstacle selects 04 and focuses the obstacle entry',
          sp.selected_node() == 'structure'
          and QApplication.focusWidget()
          is sp.form.points['obstacles'].entry)
    from blastlab.output.animation import default_ext
    want = {'threat': '1.0 kg TNT · z 2.0 m',
            'domain': '4 × 4 m · 25 mm',
            'bounds': 'the run ends at Outer',
            'structure': '1 obstacle',
            # GUI-5b: the board's wording (line 89) now that the Where
            # helper exists; 5a pinned the interim '2 gauges' (D26)
            'gauges': '2 · in front of Wall 1',
            'solver': 'linear · no afterburn · CFL 0.4',
            'output': f'{default_ext()} · VTK off'}
    got = {k: t.summary(k) for k in want}
    check('the board summaries, from the parsed case', got == want,
          str({k: v for k, v in got.items() if v != want[k]}))
    check('every node ✓ on a clean case',
          all(t.rows[k].mark.text() == '✓' for k in want))
    sp.form.v['cell'].set('abc')
    try:
        sp.get_case()
    except ValueError:
        pass
    sp.refresh(None, None)
    check('a bad field puts ✗ on its node only',
          t.rows['domain'].mark.text() == '✗'
          and t.rows['threat'].mark.text() == '✓')
    check('and the summary is kept from the last good case',
          t.summary('domain') == '4 × 4 m · 25 mm')
    sp.form.v['cell'].set('0.025')
    sp.get_case()
    sp.refresh(sp.get_case(), None)
    check('fixed: ✓ again', t.rows['domain'].mark.text() == '✓')
    check('scroll_form scrolls the properties column',
          isinstance(sp.scroll_form(1.0), int)
          and sp._scroll.isAncestorOf(sp.form))
    sp.close()


def t3_trigger():
    from blastlab.core.case import validate_case
    from blastlab.ui.case_form import TRIGGER_CHOOSE
    print('\nT3a: the trigger switch writes what the old field wrote')
    pts = {2: [(2.95, 0.5), (2.95, 1.5)],
           3: [(1.0, 0.5, 0.5), (1.2, 0.75, 0.75)]}
    for d in (2, 3):
        for mode in MODES:
            new = form(d, mode, 'nodes')
            old = form(d, mode, 'columns')
            for f in (new, old):
                f.points['gauges'].set(pts[d])
            new.refresh_trigger_choices()
            sw, combo = new.trigger_switch, new.trigger_combo
            tag = f'{d}D {mode}'
            old.v['trigger_gauge'].set('')
            ok, why = same_case(new.get_case(), old.get_case())
            check(f'{tag}: off by default, rows hidden, the Case equals '
                  f'the old field blanked',
                  not sw.isChecked() and ok
                  and not new.row_visible('trigger_action')
                  and not new.row_visible('trigger_gauge')
                  and new.get_case().trigger_gauge is None, why)
            sw.click()
            pump(5)
            check(f'{tag}: on shows Gauge and On arrival, G1 chosen',
                  sw.isChecked() and new.row_visible('trigger_action')
                  and not combo.isHidden()
                  and new.v['trigger_gauge'].get() == '1'
                  and combo.currentData() == '1'
                  and combo.currentText().startswith('G1 ('),
                  combo.currentText())
            i = combo.findData('2')
            combo.setCurrentIndex(i)
            combo.activated.emit(i)
            old.v['trigger_gauge'].set('2')
            ok, why = same_case(new.get_case(), old.get_case())
            check(f'{tag}: picking G2 builds the Case typing 2 builds',
                  ok and new.get_case().trigger_gauge == 2, why)
            # C6 (D18): `G2 (2.95, 1.50)`, the axis names in the tooltip
            want = ('G2 (2.95, 1.50)' if d == 2
                    else 'G2 (1.20, 0.75, 0.75)')
            check(f'{tag}: the entry reads {want!r}',
                  combo.currentText() == want, combo.currentText())
            sw.click()
            old.v['trigger_gauge'].set('')
            ok, why = same_case(new.get_case(), old.get_case())
            check(f'{tag}: off again blanks it', ok
                  and new.v['trigger_gauge'].get() == ''
                  and not new.row_visible('trigger_action'), why)
            sw.click()
            check(f'{tag}: on again brings back G2',
                  new.v['trigger_gauge'].get() == '2')
            new.deleteLater()
            old.deleteLater()

    print('\nT3b: loading a case sets the switch')
    for d, cls in ((2, Case2D), (3, Case3D)):
        g = pts[d]
        f = form(d, 'blastfoam', 'nodes')
        f.set_case(cls(solver='blastfoam', gauges=g, trigger_gauge=1))
        pump(5)
        check(f'{d}D: trigger_gauge=1 -> on, dropdown on G1',
              f.trigger_switch.isChecked()
              and f.trigger_combo.currentData() == '1')
        f.set_case(cls(solver='blastfoam', gauges=g))
        pump(5)
        check(f'{d}D: blank -> off, rows hidden',
              not f.trigger_switch.isChecked()
              and not f.row_visible('trigger_action')
              and not f.trigger_combo.isVisibleTo(f))
        src = cls(solver='blastfoam', gauges=g, trigger_gauge=5)
        f.set_case(src)
        pump(5)
        c = form(d, 'blastfoam', 'columns')
        c.set_case(src)
        ok, why = same_case(f.get_case(), c.get_case())
        check(f'{d}D: G5 of 2 gauges is kept and shown as '
              f'"G5 (no such gauge)"',
              f.trigger_switch.isChecked()
              and f.trigger_combo.currentText() == 'G5 (no such gauge)'
              and f.get_case().trigger_gauge == 5 and ok,
              f.trigger_combo.currentText())
        errs = validate_case(f.get_case()).errors
        check(f'{d}D: and validation still names it',
              any('Trigger gauge G5' in e for e in errs), str(errs))
        f.set_case(cls(solver='blastfoam', gauges=[]))
        f.trigger_switch.click()
        check(f'{d}D: on with no gauges: blank, the dropdown says so',
              f.v['trigger_gauge'].get() == ''
              and f.trigger_combo.currentData() == ''
              and f.trigger_combo.currentText() != TRIGGER_CHOOSE)
        f.points['gauges'].set(g)
        f.refresh_trigger_choices()
        check(f'{d}D: a gauge added later is offered, nothing written',
              f.trigger_combo.count() == 3
              and f.trigger_combo.currentText() == TRIGGER_CHOOSE
              and f.v['trigger_gauge'].get() == '')
        # D27: on with nothing chosen means NO trigger in the case - the
        # dropdown says so in red rather than looking finished
        check(f'{d}D: on with nothing chosen: pending, dropdown red, '
              f'and the case has no trigger',
              f.trigger_pending()
              and f.trigger_combo.property('bad') == 'true'
              and f.get_case().trigger_gauge is None)
        i = f.trigger_combo.findData('2')
        f.trigger_combo.setCurrentIndex(i)
        f.trigger_combo.activated.emit(i)
        check(f'{d}D: picking G2 clears the red and writes 2',
              not f.trigger_pending()
              and f.trigger_combo.property('bad') == 'false'
              and f.get_case().trigger_gauge == 2)
        f.v['trigger_gauge'].set('')
        f.trigger_switch.click()
        f.trigger_switch.click()
        check(f'{d}D: off: never red',
              not f.trigger_switch.isChecked()
              and f.trigger_combo.property('bad') == 'false')
    f = form(2, 'blastfoam', 'nodes')
    check('the off line names the side that ends the run (board)',
          f._trig['off'].text()
          == 'Off: the run ends at the Outer side or at the end time.',
          f._trig['off'].text())
    check("1D has no switch (no trigger card, T63)",
          form(1, 'blastfoam', 'nodes').trigger_switch is None)
    check("3D's On arrival still drops remap (S1)",
          all('remap' not in a for a in
              setup_spec.by_name(3)['trigger_action'].values))
    check("a standalone 'columns' form has no switch (Chain, golden)",
          form(2, 'blastfoam', 'columns').trigger_switch is None)

    print('\nT3e: removing a gauge keeps the trigger on its gauge '
          '(UXR-9, D219)')
    four = {2: [(1.0, 0.5), (2.0, 0.5), (3.0, 0.5), (3.5, 1.0)],
            3: [(0.5, 0.5, 0.5), (0.6, 0.6, 0.6), (0.7, 0.7, 0.7),
                (0.8, 0.8, 0.8)]}

    def remove_row(f, i):
        pl = f.points['gauges']
        pl.tree.setCurrentItem(pl.tree.topLevelItem(i))
        return pl.remove()

    for d, cls in ((2, Case2D), (3, Case3D)):
        for placement in ('nodes', 'columns'):
            tag = f'{d}D {placement}'
            f = form(d, 'blastfoam', placement)
            f.set_case(cls(solver='blastfoam', gauges=four[d],
                           trigger_gauge=3))
            pump(5)
            g3 = four[d][2]
            remove_row(f, 0)
            pump(5)
            pts = f.points['gauges'].get()
            check(f'{tag}: trigger G3, remove G1 -> 2, the same point',
                  f.v['trigger_gauge'].get() == '2'
                  and pts[1] == g3 and f.get_case().trigger_gauge == 2,
                  f.v['trigger_gauge'].get())
            if f.trigger_combo is not None:
                check(f'{tag}: the dropdown shows the same coordinates',
                      f.trigger_combo.currentData() == '2'
                      and f.trigger_combo.currentText().endswith(
                          f'{g3[-1]:.2f})')
                      and f'{g3[0]:.2f}' in f.trigger_combo.currentText(),
                      f.trigger_combo.currentText())
            remove_row(f, 2)            # old G4, after the trigger
            pump(5)
            check(f'{tag}: a row after the trigger changes nothing',
                  f.v['trigger_gauge'].get() == '2')
            remove_row(f, 1)            # the trigger itself
            pump(5)
            check(f'{tag}: removing the trigger gauge blanks it',
                  f.v['trigger_gauge'].get() == ''
                  and f.get_case().trigger_gauge is None)
            if f.trigger_switch is not None:
                check(f'{tag}: the switch stays on, pending and red (D27)',
                      f.trigger_switch.isChecked() and f.trigger_pending()
                      and f.trigger_combo.property('bad') == 'true')
            f.deleteLater()
        f = form(d, 'blastfoam', 'nodes')
        f.set_case(cls(solver='blastfoam', gauges=four[d],
                       trigger_gauge=3))
        pump(5)
        remove_row(f, 3)
        check(f'{d}D: trigger G3, remove G4 -> still 3',
              f.v['trigger_gauge'].get() == '3')
        f.set_case(cls(solver='blastfoam', gauges=four[d][:3],
                       trigger_gauge=5))
        pump(5)
        remove_row(f, 0)
        check(f'{d}D: a loaded G5 (no such gauge) is untouched',
              f.v['trigger_gauge'].get() == '5'
              and f.trigger_combo.currentText() == 'G5 (no such gauge)',
              f.trigger_combo.currentText())
        f.set_case(cls(solver='blastfoam', gauges=four[d],
                       trigger_gauge=3))
        f.trigger_switch.click()            # off: 3 is remembered
        remove_row(f, 0)
        f.trigger_switch.click()            # on again
        check(f'{d}D: off, remove G1, on again -> the same gauge (2)',
              f.v['trigger_gauge'].get() == '2')
        f.deleteLater()

    print('\nT3c: Profile file only in profile mode')
    for d in (2, 3):
        f = form(d, 'blastfoam', 'nodes')
        check(f"{d}D: 'charge' hides Profile file",
              not f.row_visible('profile_in'))
        f.v['profile_in'].set(r'C:\data\blast_profile.txt')
        f.v['init_mode'].set('profile1d')
        check(f"{d}D: 'profile1d' shows it", f.row_visible('profile_in'))
        f.v['init_mode'].set('charge')
        check(f'{d}D: hidden again', not f.row_visible('profile_in'))
        f.v['init_mode'].set('profile1d')
        check(f'{d}D: the typed path survived the there-and-back',
              f.v['profile_in'].get() == r'C:\data\blast_profile.txt')
    c = form(2, 'blastfoam', 'columns')
    check("a 'columns' form keeps the row (unchanged; golden)",
          c.row_visible('profile_in'))

    print('\nT3d: restated rules still hold in nodes placement')
    f = form(2, 'blastfoam', 'nodes')
    check('AMR off: coefficients hidden, charge refinement shown',
          not f.row_visible('amr_refine') and f.row_visible('charge_refine'))
    f.v['amr_levels'].set('2')
    check('AMR on: coefficients shown, charge refinement hidden',
          f.row_visible('amr_refine') and not f.row_visible('charge_refine'))
    check('video min/max hidden unless manual',
          not f.row_visible('anim_clim_min'))
    f.v['vtk_v_on'].set(True)
    check('the first VTK tick fills its family defaults',
          bool(f.v['vtk_fields'].get().get('volumes')))


def t4_derived():
    from blastlab.core.case import validate_case
    from blastlab.core import mode as mode_mod
    from blastlab.ui import scaled_distance as sd
    from blastlab.ui.setup_panel import SetupPanel

    print('\nT4a: the Z helper, pinned (UFC 3-340-02 para. 2-13.1)')
    case = sample_case()
    rows = sd.gauges(case)
    check('sample case: Z(G1) = 3.31, Z(G2) = 2.99 (R = Z for 1 kg)',
          [round(z, 2) for _n, _r, z in rows] == [3.31, 2.99]
          and all(abs(r - z) < 1e-12 for _n, r, z in rows),
          str(rows))
    c3 = Case3D(charge=8.0, center=(0.0, 0.0, 0.0), gauges=[(2.0, 0, 0)])
    check('3D, W = 8 kg at the origin, gauge (2, 0, 0): Z = 1.00',
          round(sd.gauges(c3)[0][2], 2) == 1.0, str(sd.gauges(c3)))
    c1 = Case1D(charge_kg=1.0, gauge_radii=[2.0, 3.0])
    check('1D: Z = r / W^(1/3)',
          [round(z, 6) for _n, _r, z in sd.gauges(c1)] == [2.0, 3.0])
    planar = sample_case()
    planar.geometry = 'planar'
    check('planar 2D: Z hidden (None)', not sd.z_shown(planar)
          and all(z is None for _n, _r, z in sd.gauges(planar)))
    prof = sample_case()
    prof.init_mode = 'profile1d'
    check("init_mode 'profile1d': Z hidden (None)",
          all(z is None for _n, _r, z in sd.gauges(prof)))
    zero = sample_case()
    zero.charge = 0.0
    check('W <= 0: Z hidden', not sd.z_shown(zero))
    anfo = sample_case()
    anfo.material = 'ANFO'
    check('ANFO: W is used as entered - Z changes with W, not material',
          sd.gauges(anfo) == sd.gauges(case))
    heavy = sample_case()
    heavy.charge = 8.0
    check('and it does change with W (8 kg halves Z)',
          abs(sd.gauges(heavy)[0][2] - sd.gauges(case)[0][2] / 2) < 1e-12)
    check("the label everywhere is 'Z [m/kg^1/3]'",
          sd.LABEL == 'Z [m/kg^1/3]')
    check('nearest gauge = the min-Z one (G2)',
          sd.nearest_gauge(case)[0] == 2)

    print('\nT4b: the Derived card on 01 Threat')
    sp = SetupPanel(mode=mode_mod.SolverMode())
    sp.resize(1400, 860)
    sp.show()
    pump(60)
    sp.set_case(case)
    got = sp.get_case()
    rep = validate_case(got)
    card = sp.derived()
    check('before any report: the radius row is blank',
          card.value('radius') == '')
    sp.refresh(got, rep)
    pump(20)
    want = f'{rep.r_exp * 1e3:.1f} mm'
    check("charge radius = the report's r_exp, formatted",
          card.value('radius') == want, f'{card.value("radius")} '
          f'vs report {want}')
    check("height of burst '2.00 m' (the burst z as entered)",
          card.value('hob') == '2.00 m', card.value('hob'))
    check("nearest gauge 'G2 · Z 2.99'",
          card.value('nearest') == 'G2 · Z 2.99', card.value('nearest'))
    sp.select_node('threat')
    pump(20)
    check('the card sits on the 01 Threat page',
          card.isVisibleTo(sp._props))
    try:
        from blastlab.ui import theme as _theme
        _theme.repolish(card)             # calls QWidget.update()
        repaint_ok = True
    except TypeError as exc:
        repaint_ok = str(exc)
    check('the card does not shadow QWidget.update (repolish works)',
          repaint_ok is True, str(repaint_ok))
    page = sp.form.pages['threat'].layout()
    check('right under the charge inputs (board line 326)',
          page.indexOf(card) == 1
          and page.itemAt(0).widget() is sp.form.cards['Initialization'],
          str(page.indexOf(card)))
    sp.select_node('domain')
    pump(20)
    check('and only there', not card.isVisibleTo(sp._props))
    check('the properties column stays 340 px with it',
          sp.props_width() == 340, str(sp.props_width()))
    sp.form.v['geometry'].set('planar')
    pl = sp.get_case()
    sp.refresh(pl, validate_case(pl))
    check("planar: Z hidden -> nearest by R ('G2 · R ...')",
          card.value('nearest').startswith('G2 · R '),
          card.value('nearest'))
    check('0D has no Derived card', sp.derived(0) is None)
    sp.close()


def t5_heights():
    """GUI-10 (F21, D179): the board heights at 1100 x 720 in both
    modes - Setup's case pill 42 (BC_Combined line 116), + Gauge /
    + Obstacle 36 (lines 113-114), the Chain stage pill still 40 (D153),
    all pinned in the QSS. Geometry is measured on the real platform only
    (CLAUDE.md §8.7), so offscreen this check is skipped, and says so:
    run `python test_ui_setup_tree.py --real` for it."""
    print('\nT5: Setup heights at 1100 x 720 (F21)')
    if app.platformName() == 'offscreen':
        print('  [SKIP] heights are measured on the real platform only: '
              'python test_ui_setup_tree.py --real')
        return
    from PySide6.QtWidgets import QPushButton
    from blastlab.ui import theme
    from blastlab.ui.app import MainWindow
    win = MainWindow()
    try:
        win.resize(1100, 720)
        win.show()
        pump(400)
        for mode in ('dark', 'light'):
            theme.apply(app, mode)
            win._show('setup')
            pump(400)
            t = win.setup.tree
            check(f'{mode}: Setup case pill 42 px', t.pill.height() == 42,
                  str(t.pill.height()))
            check(f'{mode}: + Gauge and + Obstacle 36 px',
                  t.add_gauge_btn.height() == 36
                  and t.add_obstacle_btn.height() == 36,
                  f'{t.add_gauge_btn.height()} / '
                  f'{t.add_obstacle_btn.height()}')
            win._show('chain')
            pump(500)
            pills = [b for b in win.chain.findChildren(QPushButton)
                     if b.objectName() == 'casepill' and b.isVisible()
                     and b.property('chain') == 'true']
            check(f'{mode}: the Chain stage pill still 40 px',
                  bool(pills) and all(b.height() == 40 for b in pills),
                  str([b.height() for b in pills]))
    finally:
        theme.apply(app, 'dark')
        win.close()
        pump(100)


def main():
    if REAL:
        t5_heights()
    else:
        t1_registry()
        t1_placement()
        t2_panel()
        t3_trigger()
        t4_derived()
        t5_heights()
    pump(20)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI SETUP TREE: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
