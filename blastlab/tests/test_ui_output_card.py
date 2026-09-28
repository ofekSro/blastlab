"""OUT-2 Step 8 (V5a): the Qt Setup card "VTK output (ParaView)".

docs/batches/2026-09-27-out-2-vtk-output.md Step 8 and
docs/model-folder-and-vtk-plan.md sec. 3.1-3.3 (owner Q2: separate
Sections and Obstacles columns). Drives the REAL `ui.case_form.CaseForm`
offscreen and checks:

  C1  the families and the matrix cells of each dimension;
  C2  native mode hides the whole card, and the case carries no key;
  C3  Time / Step greys the other interval box, and keeps its value;
  C4  the first tick of a family fills its defaults; unticking keeps them;
  C5  the plane table refuses `q, 1` and accepts `y, 1.4`;
  C6  form -> case -> JSON -> form is identical;
  C7  a bad value in the inactive box never blocks a run, one in the
      active box is reported and marked;
  C8  validation of what the card builds (2D without obstacles: "nothing
      to sample").

Headless: offscreen Qt, no window shown, no solver run.
Run:  cd blastlab/tests && python test_ui_output_card.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.ui.testing import ensure_qapp, pump          # noqa: E402

app = ensure_qapp()

from blastlab.core.case import (case_from_dict, case_to_dict,  # noqa: E402
                                validate_case)
from blastlab.models import fields as F                     # noqa: E402
from blastlab.models.case import vtk_fields_for             # noqa: E402
from blastlab.ui.case_form import CaseForm                  # noqa: E402
from blastlab.ui.setup_spec import SPAN                     # noqa: E402

FAIL = []
TITLE = 'VTK output (ParaView)'


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def form(dim, mode='blastfoam'):
    f = CaseForm(dim, mode=mode)
    f.resize(900, 700)
    f.show()
    pump(30)
    return f


def card_names(f):
    return sorted(n for n, t in f._card_of.items() if t == TITLE)


def _box_contrast(card, box, bg):
    """Mean |rgb - bg| over the tick box's indicator square, as drawn on
    the card (grab the opaque card: the matrix's own background is
    transparent, and a faded box grabbed alone is composed over black)."""
    img = card.grab().toImage()
    r = box.geometry()
    r.moveTopLeft(box.parentWidget().mapTo(card, r.topLeft()))
    side = min(r.height(), 20)
    x0 = r.x() + max(0, (r.width() - side) // 2)
    y0 = r.y() + (r.height() - side) // 2
    tot, n = 0.0, 0
    for x in range(x0, x0 + side):
        for y in range(y0, y0 + side):
            c = img.pixelColor(x, y)
            tot += (abs(c.red() - bg.red()) + abs(c.green() - bg.green())
                    + abs(c.blue() - bg.blue())) / 3.0
            n += 1
    return tot / max(n, 1)


def locked_column_is_muted():
    """P20 (owner, fix now): the locked Gauges column must read as muted,
    in light and dark mode - it was drawn white in light mode while the
    live boxes were grey, so the locked column looked the more active.
    Measured on the rendered grid: a locked box must stand out from the
    card less than half as much as a live one, ticked and unticked.
    Unfaded (LOCKED_OPACITY = 1): light 10.3 vs 17.5 and 32.5 vs 46.1,
    dark 3.6 vs 9.6 and 16.3 vs 27.3 - three of the four fail. Faded to
    0.35: light 3.5 / 11.2, dark 1.3 / 5.6."""
    print('\nC10: the locked Gauges column is visibly muted (P20)')
    from PySide6.QtWidgets import QApplication, QCheckBox
    from blastlab.ui import theme
    app_ = QApplication.instance()
    try:
        for mode in ('light', 'dark'):
            theme.apply(app_, mode)
            f = form(3)
            grid = f.widgets['vtk_fields']
            pump(30)
            locked = [b for b in grid.findChildren(QCheckBox)
                      if not b.isEnabled()]
            # OUT-4a: the only locked boxes left are p / rho / U, all
            # ticked - an unticked gauge cell is a live one now
            check(f'{mode}: no unticked locked box is left (OUT-4a)',
                  len(locked) == 3 and all(b.isChecked() for b in locked),
                  f'{len(locked)} locked')
            bg = theme.qcolor('card')
            card = f.cards[TITLE]
            tk_ = locked[0]
            tl = grid.boxes[('p', 'volumes')]
            tl.click()
            pump(10)
            c_tk, c_tl = (_box_contrast(card, tk_, bg),
                          _box_contrast(card, tl, bg))
            check(f'{mode}: and a ticked locked box is fainter than a ticked '
                  f'live one', tk_.isChecked() and tl.isChecked()
                  and c_tk < 0.5 * c_tl,
                  f'locked {c_tk:.1f}, live {c_tl:.1f}')
    finally:
        theme.apply(app_, 'dark')


def keep_all_box():
    """OUT-3 Step 6: the "Keep all fields in WSL" box on the card."""
    print('\nC11: the Keep all fields in WSL box (OUT-3)')
    from PySide6.QtWidgets import QCheckBox
    for d in (1, 2, 3):
        f = form(d)
        w = f.widgets.get('keep_all_fields')
        check(f'{d}D: the box is on the card, unticked, with its tooltip',
              isinstance(w, QCheckBox) and 'keep_all_fields' in card_names(f)
              and w.text() == F.KEEP_ALL_CAPTION and not w.isChecked()
              and w.toolTip() == F.KEEP_ALL_TIP and w.isVisible())
        check(f'{d}D: default case has keep_all_fields False, not written',
              f.get_case().keep_all_fields is False
              and 'keep_all_fields' not in case_to_dict(f.get_case()))
        w.click()
        pump(5)
        text = json.dumps(case_to_dict(f.get_case()), sort_keys=True)
        check(f'{d}D: ticked -> the case and its JSON carry it',
              json.loads(text).get('keep_all_fields') is True)
        g = form(d)
        g.set_case(case_from_dict(json.loads(text)))
        pump(5)
        check(f'{d}D: form -> case -> JSON -> form keeps the tick',
              g.v['keep_all_fields'].get() is True
              and g.widgets['keep_all_fields'].isChecked()
              and json.dumps(case_to_dict(g.get_case()),
                             sort_keys=True) == text)
        f.set_mode('native')
        pump(10)
        check(f'{d}D native: hidden with the card, and not in the case',
              not f.card_visible(TITLE) and not w.isVisible()
              and 'keep_all_fields' not in case_to_dict(f.get_case()))


def gauge_extras():
    """OUT-4a A5: a ticked gauge extra reaches `vtk_gauges`, survives a
    save/reload, and native mode hides the card and writes no key."""
    print('\nC12: the Gauges column extras (OUT-4a)')
    for d in (1, 2, 3):
        f = form(d)
        grid = f.widgets['vtk_fields']
        grid.boxes[('T', 'gauges')].click()
        pump(5)
        case = f.get_case()
        check(f'{d}D: a ticked T at the gauges is in vtk_gauges',
              case.vtk_gauges == {'fields': ['T']}
              and case_to_dict(case).get('vtk_gauges') == {'fields': ['T']},
              str(case.vtk_gauges))
        check(f'{d}D: ticking a gauge extra does not switch a family on',
              not f.v['vtk_s_on'].get() if d > 1 else True)
        text = json.dumps(case_to_dict(case), sort_keys=True)
        g = form(d)
        g.set_case(case_from_dict(json.loads(text)))
        pump(5)
        check(f'{d}D: save / reload restores the tick',
              g.widgets['vtk_fields'].boxes[('T', 'gauges')].isChecked()
              and json.dumps(case_to_dict(g.get_case()),
                             sort_keys=True) == text)
        f.set_mode('native')
        pump(10)
        check(f'{d}D native: the card is hidden and no vtk_gauges key',
              not f.card_visible(TITLE)
              and 'vtk_gauges' not in case_to_dict(f.get_case()))
    f = form(3)
    for fld in ('overpressure', 'impulse', 'dynamicP'):
        f.widgets['vtk_fields'].boxes[(fld, 'gauges')].click()
    pump(5)
    rep = validate_case(f.get_case())
    check('3D: overpressure, impulse, q at the gauges validate clean',
          f.get_case().vtk_gauges == {'fields': ['overpressure', 'impulse',
                                                 'dynamicP']}
          and not rep.errors, str(rep.errors))


def decimation():
    """OUT-4c C1 (owner Q4): the Volumes decimation spin box, 3D only,
    with the owner's warning line under it."""
    print('\nC13: the Volumes decimation box (OUT-4c)')
    from PySide6.QtWidgets import QSpinBox
    for d in (1, 2):
        f = form(d)
        check(f'{d}D: no decimation box (3D only)',
              'vtk_v_decimate' not in f.v and not f.row_notes)
    f = form(3)
    w = f.widgets.get('vtk_v_decimate')
    note = f.row_notes.get('vtk_v_decimate')
    check('3D: a spin box 1..16 holding 1, on the card, with its tip',
          isinstance(w, QSpinBox) and w.minimum() == 1
          and w.maximum() == F.VTK_DECIMATE_MAX and w.value() == 1
          and f.v['vtk_v_decimate'].get() == '1'
          and 'vtk_v_decimate' in card_names(f) and w.isVisible()
          and w.toolTip() == F.VTK_DECIMATE_TIP)
    check('   the owner\'s warning line under it, visible',
          note is not None and note.text() == F.VTK_DECIMATE_NOTE
          and 'viewing only; peaks may be missed' in note.text()
          and note.isVisible() and note.y() > w.y())
    f.widgets['vtk_v_on'].click()
    pump(5)
    check('k = 1: no decimate key in the case or its JSON',
          'decimate' not in f.get_case().vtk_volumes
          and 'decimate' not in case_to_dict(f.get_case())['vtk_volumes'])
    w.setValue(2)
    pump(5)
    case = f.get_case()
    text = json.dumps(case_to_dict(case), sort_keys=True)
    check('k = 2 (spin box): the case carries decimate 2, validates clean '
          'with the warning in its note',
          f.v['vtk_v_decimate'].get() == '2'
          and case.vtk_volumes.get('decimate') == 2
          and json.loads(text)['vtk_volumes']['decimate'] == 2
          and not validate_case(case).errors
          and any(F.VTK_DECIMATE_WARNING in n
                  for n in validate_case(case).notes), str(case.vtk_volumes))
    g = form(3)
    g.set_case(case_from_dict(json.loads(text)))
    pump(5)
    check('save / reload restores k = 2 in the box',
          g.widgets['vtk_v_decimate'].value() == 2
          and json.dumps(case_to_dict(g.get_case()), sort_keys=True) == text)
    w.setValue(0)                    # below the range: clamped by the box
    w.setValue(99)                   # above it: clamped too
    pump(5)
    check('the box clamps to 1..16', w.value() == F.VTK_DECIMATE_MAX
          and f.v['vtk_v_decimate'].get() == str(F.VTK_DECIMATE_MAX))
    f.set_mode('native')
    pump(10)
    check('native: hidden with the card, no vtk_volumes key',
          not f.card_visible(TITLE) and not w.isVisible()
          and 'vtk_volumes' not in case_to_dict(f.get_case()))


def main():
    print('\nC1: the families and the matrix of each dimension')
    want_fams = {1: ['vtk_v_on'], 2: ['vtk_v_on', 'vtk_s_on'],
                 3: ['vtk_s_on', 'vtk_v_on']}
    # P24: the 2D matrix runs in the order of the family boxes
    want_cols = {1: ('gauges', 'volumes'),
                 2: ('gauges', 'volumes', 'obstacles'),
                 3: ('gauges', 'sections', 'obstacles', 'volumes')}
    # P13: full-word headers
    want_heads = {1: ['Gauges', 'Whole domain'],
                  2: ['Gauges', 'Whole domain', 'Obstacles'],
                  3: ['Gauges', 'Sections', 'Obstacles', 'Volumes']}
    for d in (1, 2, 3):
        f = form(d)
        names = card_names(f)
        fams = [n for n in f._card_of if n.endswith('_on')
                and n.startswith('vtk_')]
        check(f'{d}D: the card is there, in the right column',
              TITLE in f.cards and f.card_visible(TITLE))
        check(f'{d}D: its families, in order', fams == want_fams[d],
              str(fams))
        grid = f.widgets['vtk_fields']
        rows = vtk_fields_for(d)
        cols = sorted({c for _f, c in grid.boxes})
        check(f'{d}D: {len(rows)} quantity rows (D4)',
              sorted({f_ for f_, _c in grid.boxes}) == sorted(rows)
              # OUT-4a: + the Dynamic pressure row; OUT-4b: + Peak
              # impulse and Obstacle ID (2D/3D)
              and len(rows) == (7 if d == 1 else 13), str(rows))
        # OUT-4a: the Gauges column has live boxes too (the extras)
        check(f'{d}D: live columns {want_cols[d]}',
              cols == sorted(want_cols[d]), str(cols))
        extras = F.vtk_gauge_extras_for(d)
        check(f'{d}D: a tick box in every destination cell, plus the '
              f'gauge extras {extras}',
              len(grid.boxes) == sum(
                  len(set(F.VTK_CELLS[r]) & set(want_cols[d]) - {'gauges'})
                  for r in rows) + len(extras)
              and {f_ for f_, c in grid.boxes if c == 'gauges'}
              == set(extras), str(sorted(grid.boxes)))
        want_gauge = ({'T', 'dynamicP'} if d == 1 else
                      {'T', 'dynamicP', 'overpressure', 'impulse'})
        from PySide6.QtWidgets import QCheckBox as _QCB
        n_boxes = len(grid.findChildren(_QCB))
        check(f'{d}D: gauge cells exist only for p, rho, U and '
              f'{sorted(want_gauge)} (VTK_CELLS)',
              set(extras) == want_gauge
              and n_boxes == len(grid.boxes) + 3, f'{n_boxes} boxes')
        # P13 (owner, 2026-09-27): the card spans both columns, below
        # them, with full-word headers in the order of the families (P24)
        from PySide6.QtWidgets import QLabel
        heads = [lb.text() for lb in grid.findChildren(QLabel)][
            :len(want_cols[d])]
        check(f'{d}D: full-word headers in family order {want_heads[d]}',
              heads == want_heads[d], str(heads))
        card = f.cards[TITLE]
        col = next(c for w, c, _s in f._card_order if w is card)
        check(f'{d}D: the card spans both columns, below them',
              col == SPAN and not f.single_column()
              and f._cols[SPAN].indexOf(card) >= 0
              and card.width() > f._holders[0].width(),
              f'col {col}, card {card.width()} px, column '
              f'{f._holders[0].width()} px')
        # the first offscreen QA shots showed "Pressu" and "Obstacle":
        # nothing on the card may be cut, side by side or stacked
        # in a scroll area, as on the Setup tab: side by side when the
        # viewport holds both panes, stacked (and one column) when narrow
        from PySide6.QtWidgets import QScrollArea
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(f)
        sa.show()
        for width, side in ((1400, True), (460, False)):
            sa.resize(width, 700)
            pump(60)
            vp = sa.viewport().width()
            cut = [(lb.text(), lb.width()) for lb in card.findChildren(QLabel)
                   if lb.isVisible() and not lb.wordWrap() and lb.text()
                   and lb.width() + 1
                   < lb.fontMetrics().horizontalAdvance(lb.text())]
            check(f'{d}D at a {vp} px viewport: '
                  f'{"side by side" if side else "stacked"}, nothing cut, '
                  f'nothing wider than the viewport',
                  f.span_side_by_side(TITLE) == side and not cut
                  and f.width() <= vp and card.width() <= vp,
                  f'side {f.span_side_by_side(TITLE)} cut {cut} form '
                  f'{f.width()} card {card.width()} vp {vp}')
        check(f'{d}D: the plane table is 3D only',
              ('vtk_planes' in names) == (d == 3), str(names))
        # the locked Gauges column: p / rho / U ticked, all disabled
        from PySide6.QtWidgets import QCheckBox
        locked = [b for b in grid.findChildren(QCheckBox)
                  if not b.isEnabled()]
        ticked = [b for b in locked if b.isChecked()]
        check(f'{d}D: p, rho, U locked and ticked at the Gauges',
              len(locked) == 3 and len(ticked) == 3,
              f'{len(locked)} locked, {len(ticked)} ticked')
        # P22: the Time box is in seconds, and the card says the files are
        check(f'{d}D: the interval captions carry their units',
              all('[s]' in f.label_text(n) for n in names
                  if n.endswith('_time'))
              and any(n.endswith('_time') for n in names)
              and all('[steps]' in f.label_text(n) for n in names
                      if n.endswith('_steps')))
        note = f.notes.get(TITLE)
        check(f'{d}D: the card says the files and ParaView use seconds',
              note is not None
              and note.text() == 'Files and ParaView show time in seconds.',
              note.text() if note is not None else 'no note')
        check(f'{d}D: a fresh form writes no VTK key',
              'vtk_volumes' not in case_to_dict(f.get_case())
              and 'vtk_surfaces' not in case_to_dict(f.get_case()))
    f2 = form(2)
    check('2D: the surfaces family is called Obstacles',
          f2.widgets['vtk_s_on'].text() == 'Obstacles'
          and f2.widgets['vtk_v_on'].text() == 'Whole domain')

    print('\nC2: native mode hides the card; the case has no key')
    for d in (1, 2, 3):
        f = form(d)
        fam = 's' if d == 3 else 'v'
        f.v[f'vtk_{fam}_on'].set(True)
        f.set_mode('native')
        pump(10)
        check(f'{d}D native: the card is hidden', not f.card_visible(TITLE))
        dd = case_to_dict(f.get_case())
        check(f'{d}D native: no VTK key although a family is ticked',
              'vtk_volumes' not in dd and 'vtk_surfaces' not in dd)
        f.set_mode('blastfoam')
        pump(10)
        check(f'{d}D back to blastFoam: the card and the tick are back',
              f.card_visible(TITLE) and f.v[f'vtk_{fam}_on'].get())

    print('\nC3: Time / Step greys the other box')
    f = form(3)
    for fam in ('s', 'v'):
        check(f'{fam}: Time by default, the steps box greyed',
              f.v[f'vtk_{fam}_mode'].get() == 'time'
              and f.is_enabled(f'vtk_{fam}_time')
              and not f.is_enabled(f'vtk_{fam}_steps'))
        f.v[f'vtk_{fam}_time'].set('0.00075')
        f.widgets[f'vtk_{fam}_mode'].buttons['step'].click()
        pump(5)
        check(f'{fam}: a click on Step greys the seconds box instead',
              f.v[f'vtk_{fam}_mode'].get() == 'step'
              and not f.is_enabled(f'vtk_{fam}_time')
              and f.is_enabled(f'vtk_{fam}_steps'))
        check(f'{fam}: and the greyed box keeps its value',
              f.v[f'vtk_{fam}_time'].get() == '0.00075')
        f.v[f'vtk_{fam}_mode'].set('time')
        pump(5)
        check(f'{fam}: set() back to Time checks the Time radio',
              f.widgets[f'vtk_{fam}_mode'].buttons['time'].isChecked()
              and f.is_enabled(f'vtk_{fam}_time'))
    check('the rest of the form is never greyed by the card',
          f.is_enabled('cell') and f.is_enabled('t_end'))

    print('\nC4: the first tick fills the defaults')
    f = form(3)
    f.widgets['vtk_s_on'].click()
    pump(5)
    m = f.v['vtk_fields'].get()
    check('3D surfaces: p and pMax on sections and obstacles',
          m['sections'] == ['p', 'pMax'] and m['obstacles'] == ['p', 'pMax']
          and m['volumes'] == [], str(m))
    grid = f.widgets['vtk_fields']
    check('and the tick boxes show it',
          grid.boxes[('pMax', 'sections')].isChecked()
          and not grid.boxes[('rho', 'sections')].isChecked())
    f.widgets['vtk_v_on'].click()
    pump(5)
    check('3D volumes: p, rho, U',
          f.v['vtk_fields'].get()['volumes'] == ['p', 'rho', 'U'])
    grid.boxes[('T', 'obstacles')].click()
    grid.boxes[('p', 'sections')].click()
    pump(5)
    m = f.v['vtk_fields'].get()
    check('a click on a cell edits that column only',
          m['obstacles'] == ['p', 'pMax', 'T'] and m['sections'] == ['pMax'],
          str(m))
    # OUT-4b B3 (owner Q3): Obstacle ID is an Obstacles box alone, and
    # its tick lands in obstacle_fields
    check('B3: Obstacle ID has an Obstacles box and no other',
          {c for r, c in grid.boxes if r == 'obstacleID'} == {'obstacles'},
          str(sorted(c for r, c in grid.boxes if r == 'obstacleID')))
    grid.boxes[('obstacleID', 'obstacles')].click()
    pump(5)
    check('B3: its tick is saved in obstacle_fields, last',
          case_to_dict(f.get_case())['vtk_surfaces']['obstacle_fields']
          == ['p', 'pMax', 'T', 'obstacleID'])
    grid.boxes[('obstacleID', 'obstacles')].click()
    pump(5)
    f.widgets['vtk_s_on'].click()
    pump(5)
    check('unticking the family keeps its ticks',
          not f.v['vtk_s_on'].get()
          and f.v['vtk_fields'].get()['obstacles'] == ['p', 'pMax', 'T'])
    # owner decision P15: the ticks of a family that is off survive a
    # save and reload (written `on: false`), and the solver ignores it
    f.v['vtk_s_mode'].set('step')
    f.v['vtk_s_steps'].set('30')
    text = json.dumps(case_to_dict(f.get_case()), sort_keys=True)
    saved = json.loads(text)
    check('P15: the off family is written, on: false, with its ticks',
          saved.get('vtk_surfaces', {}).get('on') is False
          and saved['vtk_surfaces']['obstacle_fields'] == ['p', 'pMax', 'T']
          and saved['vtk_surfaces']['fields'] == ['pMax']
          and saved['vtk_surfaces']['mode'] == 'step'
          and saved['vtk_surfaces']['value'] == 30,
          str(saved.get('vtk_surfaces')))
    g = form(3)
    g.set_case(case_from_dict(saved))
    pump(5)
    check('P15: reloaded, the box is unticked and the ticks are back',
          not g.v['vtk_s_on'].get() and g.v['vtk_s_mode'].get() == 'step'
          and g.v['vtk_s_steps'].get() == '30'
          and g.v['vtk_fields'].get()['obstacles'] == ['p', 'pMax', 'T']
          and g.v['vtk_fields'].get()['sections'] == ['pMax'],
          str(g.v['vtk_fields'].get()))
    check('P15: and the case written again is the same JSON',
          json.dumps(case_to_dict(g.get_case()), sort_keys=True) == text)
    from blastlab.models.case import vtk_family
    check('P15: the solver side sees no surfaces family',
          vtk_family(g.get_case(), 'vtk_surfaces') is None)
    g.widgets['vtk_s_on'].click()
    pump(5)
    check('P15: ticking the reloaded family keeps its ticks (no defaults)',
          g.v['vtk_fields'].get()['obstacles'] == ['p', 'pMax', 'T'])
    f.v['vtk_s_mode'].set('time')
    f.widgets['vtk_s_on'].click()
    pump(5)
    check('and ticking it again does not overwrite them',
          f.v['vtk_fields'].get()['sections'] == ['pMax'])
    f1 = form(1)
    f1.widgets['vtk_v_on'].click()
    pump(5)
    check('1D whole domain: p, rho, U',
          f1.v['vtk_fields'].get() == {'gauges': [],   # OUT-4a column
                                       'volumes': ['p', 'rho', 'U']})
    f2 = form(2)
    f2.widgets['vtk_s_on'].click()
    pump(5)
    check('2D obstacles: p and pMax, no sections column',
          f2.v['vtk_fields'].get() == {'gauges': [],   # OUT-4a column
                                       'obstacles': ['p', 'pMax'],
                                       'volumes': []})

    print('\nC5: the plane table (D7)')
    f = form(3)
    pl = f.points['vtk_planes']
    pl.entry.setText('q, 1')
    check('`q, 1` is refused, and the hint says why',
          not pl.add() and 'x, y or z' in pl.hint.text() and pl.count() == 0,
          pl.hint.text())
    pl.entry.setText('y, abc')
    check('`y, abc` is refused', not pl.add() and pl.count() == 0,
          pl.hint.text())
    pl.entry.setText('y')
    check('a short row is refused', not pl.add() and pl.count() == 0)
    pl.entry.setText('y, 1.4')
    check('`y, 1.4` is accepted', pl.add() and pl.get() == [('y', 1.4)],
          str(pl.get()))
    pl.entry.setText('Z 0.5')
    check('`Z 0.5` is accepted as z', pl.add()
          and pl.get() == [('y', 1.4), ('z', 0.5)], str(pl.get()))
    check('the gauges table still takes numbers only',
          f.points['gauges']._kinds == ('float',) * 3)
    # P21: a refused row must not survive Open case / set_case
    pl.entry.setText('q, 1')
    pl.add()
    refused = pl.entry.text() == 'q, 1' and pl.entry.property('bad') == 'true'
    f.set_case(case_from_dict(case_to_dict(f.get_case())))
    pump(5)
    check('P21: a load clears a refused row and its red state',
          refused and pl.entry.text() == ''
          and pl.entry.property('bad') == 'false'
          and pl.hint.text().startswith('add a row'),
          f'{pl.entry.text()!r} {pl.entry.property("bad")} {pl.hint.text()!r}')

    print('\nC6: form -> case -> JSON -> form is identical')
    for d in (1, 2, 3):
        f = form(d)
        if d > 1:
            f.points['obstacles'].set(
                [(0.1, 0.2, 0.3, 0.4)] if d == 2
                else [(0.1, 0.2, 0.3, 0.4, 0.5, 0.6)])
        for fam, _c in F.VTK_FAMILIES[d]:
            f.widgets[f'vtk_{fam}_on'].click()
        pump(5)
        if d == 3:
            f.v['vtk_s_mode'].set('step')
            f.v['vtk_s_steps'].set('40')
            f.v['vtk_v_time'].set('0.00025')
            f.points['vtk_planes'].set([('x', 0.3), ('z', 1.1)])
            f.widgets['vtk_fields'].boxes[('rhoE', 'volumes')].click()
        elif d == 2:
            f.v['vtk_v_mode'].set('step')
            f.v['vtk_v_steps'].set('10')
            f.widgets['vtk_fields'].boxes[('timeOfArrival',
                                           'obstacles')].click()
        else:
            f.v['vtk_v_time'].set('0.0005')
        pump(5)
        case = f.get_case()
        text = json.dumps(case_to_dict(case), sort_keys=True)
        back = case_from_dict(json.loads(text))
        g = form(d)
        g.set_case(back)
        pump(5)
        keys = sorted(k for k in f.v if k.startswith('vtk_'))
        diff = [k for k in keys if f.v[k].get() != g.v[k].get()]
        if d == 3:
            diff += (['vtk_planes'] if f.points['vtk_planes'].get()
                     != g.points['vtk_planes'].get() else [])
        check(f'{d}D: every card value survives the round trip', not diff,
              str([(k, f.v[k].get(), g.v[k].get()) for k in diff
                   if k in f.v][:2]))
        again = json.dumps(case_to_dict(g.get_case()), sort_keys=True)
        check(f'{d}D: and the case written again is the same JSON',
              again == text)
        check(f'{d}D: the greying follows the loaded mode',
              all(g.is_enabled(f'vtk_{fam}_time')
                  == (g.v[f'vtk_{fam}_mode'].get() == 'time')
                  for fam, _c in F.VTK_FAMILIES[d]))
    dd = case_to_dict(f.get_case())
    check('3D: the JSON holds both families as sec. 3.3 says',
          dd['vtk_surfaces'] == {
              'on': True, 'mode': 'step', 'value': 40,
              'fields': ['p', 'pMax'], 'obstacle_fields': ['p', 'pMax'],
              'planes': [['x', 0.3], ['z', 1.1]]}
          and dd['vtk_volumes'] == {
              'on': True, 'mode': 'time', 'value': 0.00025,
              'fields': ['p', 'rho', 'U', 'rhoE']}, str(dd.get('vtk_volumes')))
    # loading a case without VTK keys resets the card
    g.set_case(case_from_dict(json.loads(json.dumps(
        {k: v for k, v in case_to_dict(case).items()
         if not k.startswith('vtk_')}))))
    pump(5)
    check('loading a case without VTK keys switches both families off',
          not g.v['vtk_s_on'].get() and not g.v['vtk_v_on'].get()
          and g.points['vtk_planes'].get() == []
          and g.v['vtk_fields'].get() == {'gauges': [],  # OUT-4a column
                                          'sections': [], 'obstacles': [],
                                          'volumes': []})

    print('\nC7: a bad value in the inactive box never blocks a run')
    f = form(3)
    f.widgets['vtk_v_on'].click()
    f.v['vtk_v_steps'].set('lots')            # inactive: Time mode
    pump(5)
    try:
        case = f.get_case()
        ok = case.vtk_volumes['value'] == 0.001 and not f.bad
    except ValueError as exc:
        ok, case = False, exc
    check('Time mode: a bad steps box is not read', ok, str(case)[:80])
    f.v['vtk_v_mode'].set('step')
    pump(5)
    try:
        f.get_case()
        raised = ''
    except ValueError as exc:
        raised = str(exc)
    check('Step mode: the same box is reported, and marked',
          "'VTK Volumes every [steps]' is not an integer" in raised
          and f.bad == {'vtk_v_steps'}, raised)
    f.v['vtk_v_steps'].set('2.5')
    try:
        f.get_case()
        raised = ''
    except ValueError as exc:
        raised = str(exc)
    check('a fractional step count is refused', 'whole number' in raised,
          raised)
    f.v['vtk_v_on'].set(False)
    pump(5)
    try:
        f.get_case()
        ok = not f.bad
    except ValueError:
        ok = False
    check('a family that is off is not read at all', ok)
    f.set_mode('native')
    f.v['vtk_v_on'].set(True)
    try:
        f.get_case()
        ok = True
    except ValueError:
        ok = False
    check('native mode never reads the card', ok)

    print('\nC8: validation of what the card builds')
    f = form(2)
    f.widgets['vtk_s_on'].click()
    pump(5)
    rep = validate_case(f.get_case())
    check('2D obstacles without obstacles: "nothing to sample"',
          any('nothing to sample' in e for e in rep.errors), str(rep.errors))
    f.points['obstacles'].set([(3.0, 3.2, 0.0, 0.5)])
    rep = validate_case(f.get_case())
    check('with an obstacle it validates', not rep.errors, str(rep.errors))
    f = form(1)
    f.widgets['vtk_v_on'].click()
    pump(5)
    rep = validate_case(f.get_case())
    check('1D whole domain validates, with the write-count note',
          not rep.errors and any('VTK volumes' in n for n in rep.notes),
          str(rep.errors))

    print('\nC9: what the matrix labels say (GUI QA 2026-09-27)')
    from PySide6.QtWidgets import QLabel
    f = form(3)
    labels = {w.text(): w for w in
              f.widgets['vtk_fields'].findChildren(QLabel)}
    pk = labels.get('Peak overpressure')
    tip = pk.toolTip() if pk is not None else ''
    # owner decision 4 (2026-09-27, out-2-surface-layout.md), replacing
    # F1: the export writes pMax - ambient, so the row says what is
    # exported
    check('decision 4: the pMax row reads "Peak overpressure"',
          pk is not None and 'Peak pressure' not in labels,
          str(sorted(labels)))
    check('decision 4: its tooltip says minus ambient, the array name and '
          'pMax', all(s in tip for s in ('minus ambient', '101.325 kPa',
                                          'Peak_Overpressure', 'pMax')), tip)
    # OUT-4b B1 (owner Q1): timeOfArrival is the time of PEAK pressure
    # (blastFoam User Guide v6.0, sec. 15.12), so the row says so
    tp = labels.get('Time of peak')
    tip = tp.toolTip() if tp is not None else ''
    check('B1: the timeOfArrival row reads "Time of peak", no "Arrival time"',
          tp is not None and 'Arrival time' not in labels, str(sorted(labels)))
    check('B1: its tooltip says maximum, not the first arrival, and names '
          'Time_Of_Peak and timeOfArrival',
          all(s in tip for s in ('maximum', 'not the first arrival',
                                 'Time_Of_Peak', 'timeOfArrival')), tip)
    # OUT-4b B3 (verify): obstacleID is made by the export, never sampled
    # - its tooltip must not send anyone looking for a blastFoam field
    oid = labels.get('Obstacle ID')
    tip = oid.toolTip() if oid is not None else ''
    check('B3: the Obstacle ID tooltip names Obstacle_ID and says it is '
          'not a blastFoam field',
          oid is not None and 'Obstacle_ID' in tip
          and 'not a blastFoam field' in tip
          and 'blastFoam field obstacleID' not in tip, tip)
    # the confusing-wording list: no internal ids, what the rows mean
    caps = [f.label_text('vtk_planes'), f.label_text('vtk_fields')]
    check('no user-facing "OUT-4" in the captions or header tooltips',
          not any('OUT-' in t for t in caps + [
              w.toolTip() for w in labels.values()]), str(caps))
    check('the live-slice note says "when Sections and obstacles is ticked"',
          'when "Sections and obstacles" is ticked' in caps[0], caps[0])
    # OUT-4a: the Gauges column is no longer fixed
    check('Gauges: pressure, density and velocity are always recorded',
          'pressure, density and velocity are always recorded' in caps[1]
          and 'fixed' not in caps[1], caps[1])
    for row, want in (('Energy', 'total energy per unit volume'),
                      ('Products', 'volume fraction of detonation products')):
        t = labels[row].toolTip() if row in labels else ''
        check(f'the "{row}" tooltip explains it', want in t, t)
    t = labels['Volumes'].toolTip() if 'Volumes' in labels else ''
    check('the "Volumes" header tooltip says whole-domain output',
          'whole-domain output' in t, t)
    f.widgets['vtk_v_on'].click()
    pump(5)
    rep = validate_case(f.get_case())
    n = next((x for x in rep.notes if x.startswith('VTK volumes')), '')
    # owner decision P14 (b): no "changes the solution" warning; the
    # writes are the first step past each interval
    check('Time-mode volumes note: the write schedule, first step past '
          'each interval, no "change the solution" warning',
          "solver's write schedule" in n
          and 'one write every 0.001 s' in n                  # P22
          and 'first solver step past its interval' in n
          and 'solution' not in n, n)
    f.v['vtk_v_mode'].set('step')
    pump(5)
    rep = validate_case(f.get_case())
    n = next((x for x in rep.notes if x.startswith('VTK volumes')), '')
    check('Step-mode volumes note: size per write, count depends on steps',
          'every 25 solver steps' in n and 'GB per write' in n
          and "depends on the run's step count" in n, n)

    locked_column_is_muted()
    keep_all_box()
    gauge_extras()
    decimation()

    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} check(s): {FAIL}')
        sys.exit(1)
    print('UI OUTPUT CARD: PASS')


if __name__ == '__main__':
    main()
