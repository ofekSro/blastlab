"""GUI-5a: the Setup model tree and its properties column.

T1 - the FieldForm 'nodes' placement and the node registry: every spec
field is reachable through exactly one node (plan §10), and the 'nodes'
placement changes where cards are laid, never what they parse or which
rows the solver scope shows.

Headless: offscreen Qt, no window shown, no solver run.
Run:  cd blastlab/tests && python test_ui_setup_tree.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.ui.testing import ensure_qapp, pump          # noqa: E402

app = ensure_qapp()

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
            check(f'{d}D {mode}: same scope visibility, row by row',
                  {n: a.row_visible(n) for n in a.widgets}
                  == {n: b.row_visible(n) for n in b.widgets}
                  and {t: a.card_visible(t) for t in a.cards}
                  == {t: b.card_visible(t) for t in b.cards},
                  str([n for n in a.widgets
                       if a.row_visible(n) != b.row_visible(n)]))
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


def main():
    t1_registry()
    t1_placement()
    pump(20)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI SETUP TREE: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
