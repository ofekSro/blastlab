"""OUT-2 Step 9 (V5b): the Tk Setup card "VTK output (ParaView)".

The Tk GUI is the permanent way back (CLAUDE.md section 9), so its card
is a full equivalent of the Qt one (test_ui_output_card.py). Drives the
REAL `gui.forms.CaseForm` (customtkinter, withdrawn root) and checks:

  K1  the same field names as the Qt spec (ui/setup_spec.fields), per
      dimension - the parity of the two toolkits;
  K2  the families, the matrix cells and the locked Gauges column;
  K3  native mode hides the card, and the case carries no key;
  K4  Time / Step disables the other interval box, keeping its value;
  K5  the first tick fills the defaults; unticking keeps them;
  K6  the plane table refuses `q, 1` and accepts `y, 1.4`;
  K7  form -> case -> JSON -> form is identical, and a Qt form loads
      the same case to the same values;
  K8  a bad value in the inactive box never blocks a run.

Script only - it builds Tk widgets (conftest keeps test_gui_* out of
pytest). Run:  cd blastlab/tests && python test_gui_output_card.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_go_'),
                                   'settings.json'))
os.environ.setdefault('MPLBACKEND', 'Agg')

import customtkinter as ctk                                  # noqa: E402

from blastlab.core.case import (case_from_dict, case_to_dict,  # noqa: E402
                                validate_case)
from blastlab.gui.forms import CaseForm                      # noqa: E402
from blastlab.models import fields as F                      # noqa: E402
from blastlab.models.case import vtk_fields_for              # noqa: E402
from blastlab.ui import setup_spec                           # noqa: E402

FAIL = []
ROOT = ctk.CTk()
ROOT.withdraw()


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def form(dim, mode='blastfoam'):
    f = CaseForm(ROOT, dim, mode=mode)
    ROOT.update_idletasks()
    return f


def names(f):
    return set(f.v) | set(f._point_lists())


def card_shown(f):
    """The VTK card is grid-managed (not grid_remove'd)."""
    return f._vtk_card.winfo_manager() == 'grid'


def entry_on(f, name):
    return str(f._vtk_entries[name].cget('state')) == 'normal'


def main():
    print('\nK1: the same field names as the Qt form')
    for d in (1, 2, 3):
        f = form(d)
        qt = {x.name for x in setup_spec.fields(d) if x.name.startswith('vtk_')}
        tk_ = {n for n in names(f) if n.startswith('vtk_')}
        check(f'{d}D: the VTK fields match the Qt spec', qt == tk_,
              str(sorted(qt ^ tk_)))
        f.destroy()

    print('\nK2: families, matrix and the locked Gauges column')
    want = {1: ['v'], 2: ['v', 's'], 3: ['s', 'v']}
    for d in (1, 2, 3):
        f = form(d)
        fams = [fam for fam, _c in F.VTK_FAMILIES[d]]
        check(f'{d}D: families {want[d]}', fams == want[d]
              and all(f'vtk_{x}_on' in f.v for x in fams))
        rows = vtk_fields_for(d)
        cells = f.v['vtk_fields'].cells
        dest = [c for c in F.VTK_COLUMNS[d] if c != 'gauges']
        # OUT-4a: plus a live gauge cell per extra (VTK_CELLS)
        extras = F.vtk_gauge_extras_for(d)
        check(f'{d}D: a box per quantity and destination column, plus the '
              f'gauge extras {extras}',
              # OUT-4b: a cell only where VTK_CELLS has one (obstacleID:
              # the obstacles column alone)
              set(cells) == {(r, c) for r in rows for c in dest
                             if c in F.VTK_CELLS[r]}
              | {(x, 'gauges') for x in extras}
              and set(extras) == ({'T', 'dynamicP'} if d == 1 else
                                  {'T', 'dynamicP', 'overpressure',
                                   'impulse'}),
              f'{len(cells)} cells')
        locked = f._vtk_grid.locked
        check(f'{d}D: p / rho / U locked and ticked at the Gauges',
              len(locked) == 3
              and all(str(b.cget('state')) == 'disabled' for _v, b in locked)
              and sum(v.get() for v, _b in locked) == 3)
        check(f'{d}D: a fresh form writes no VTK key',
              not any(k.startswith('vtk_')
                      for k in case_to_dict(f.get_case())))
        check(f'{d}D: the card is shown in blastFoam mode', card_shown(f))
        f.destroy()

    print('\nK3: native mode hides the card')
    for d in (1, 2, 3):
        f = form(d)
        fam = want[d][0]
        f.v[f'vtk_{fam}_on'].set(True)
        f.set_mode('native')
        ROOT.update_idletasks()
        check(f'{d}D native: hidden', not card_shown(f))
        check(f'{d}D native: no VTK key although a family is ticked',
              not any(k.startswith('vtk_')
                      for k in case_to_dict(f.get_case())))
        f.set_mode('blastfoam')
        check(f'{d}D back: shown, still ticked',
              card_shown(f) and f.v[f'vtk_{fam}_on'].get())
        f.destroy()

    print('\nK4: Time / Step disables the other box')
    f = form(3)
    for fam in ('s', 'v'):
        check(f'{fam}: Time, the steps box disabled',
              entry_on(f, f'vtk_{fam}_time')
              and not entry_on(f, f'vtk_{fam}_steps'))
        f.v[f'vtk_{fam}_time'].set('0.00075')
        f._vtk_radios[fam][1].invoke()          # Step
        check(f'{fam}: Step disables the seconds box instead',
              f.v[f'vtk_{fam}_mode'].get() == 'step'
              and not entry_on(f, f'vtk_{fam}_time')
              and entry_on(f, f'vtk_{fam}_steps'))
        check(f'{fam}: which keeps its value',
              f.v[f'vtk_{fam}_time'].get() == '0.00075')
    f.destroy()

    print('\nK5: the first tick fills the defaults')
    f = form(3)
    f.v['vtk_s_on'].set(True)
    check('3D surfaces: p, pMax on sections and obstacles',
          f.v['vtk_fields'].get() == {'gauges': [],     # OUT-4a column
                                      'sections': ['p', 'pMax'],
                                      'obstacles': ['p', 'pMax'],
                                      'volumes': []},
          str(f.v['vtk_fields'].get()))
    f.v['vtk_v_on'].set(True)
    check('3D volumes: p, rho, U',
          f.v['vtk_fields'].get()['volumes'] == ['p', 'rho', 'U'])
    f.v['vtk_fields'].cells[('T', 'obstacles')].set(True)
    f.v['vtk_s_on'].set(False)
    f.v['vtk_s_on'].set(True)
    check('unticking and ticking again keeps the edited column',
          f.v['vtk_fields'].get()['obstacles'] == ['p', 'pMax', 'T'])
    # OUT-4b B3 (owner Q3): Obstacle ID is an Obstacles cell alone, and
    # its tick lands in obstacle_fields
    cells = f.v['vtk_fields'].cells
    check('B3: Obstacle ID has an Obstacles cell and no other',
          {c for r, c in cells if r == 'obstacleID'} == {'obstacles'})
    cells[('obstacleID', 'obstacles')].set(True)
    check('B3: its tick is saved in obstacle_fields, last',
          case_to_dict(f.get_case())['vtk_surfaces']['obstacle_fields']
          == ['p', 'pMax', 'T', 'obstacleID'])
    cells[('obstacleID', 'obstacles')].set(False)
    # owner decision P15: an off family keeps its ticks through a save
    f.v['vtk_s_on'].set(False)
    text = json.dumps(case_to_dict(f.get_case()), sort_keys=True)
    saved = json.loads(text)
    check('P15: the off family is written, on: false, with its ticks',
          saved.get('vtk_surfaces', {}).get('on') is False
          and saved['vtk_surfaces']['obstacle_fields'] == ['p', 'pMax', 'T'],
          str(saved.get('vtk_surfaces')))
    g = form(3)
    g.set_case(case_from_dict(saved))
    check('P15: reloaded, the box is unticked and the ticks are back',
          not g.v['vtk_s_on'].get()
          and g.v['vtk_fields'].get()['obstacles'] == ['p', 'pMax', 'T'],
          str(g.v['vtk_fields'].get()))
    check('P15: and the case written again is the same JSON',
          json.dumps(case_to_dict(g.get_case()), sort_keys=True) == text)
    g.destroy()
    f.destroy()
    f = form(2)
    f.v['vtk_s_on'].set(True)
    check('2D obstacles: p, pMax',
          f.v['vtk_fields'].get() == {'gauges': [],     # OUT-4a column
                                      'obstacles': ['p', 'pMax'],
                                      'volumes': []})
    f.destroy()

    print('\nK6: the plane table (D7)')
    f = form(3)
    pl = f.vtk_planes
    pl.entry_var.set('q, 1')
    pl._add()
    check('`q, 1` is refused, and the hint says why',
          pl.get() == [] and 'x, y or z' in pl._hint.cget('text'),
          pl._hint.cget('text'))
    pl.entry_var.set('y, 1.4')
    pl._add()
    check('`y, 1.4` is accepted', pl.get() == [('y', 1.4)], str(pl.get()))
    # P21: a refused row does not survive a load
    pl.entry_var.set('q, 1')
    pl._add()
    f.set_case(case_from_dict(case_to_dict(f.get_case())))
    check('P21: a load clears a refused row and the hint',
          pl.entry_var.get() == ''
          and pl._hint.cget('text').startswith('add a row'),
          f'{pl.entry_var.get()!r} {pl._hint.cget("text")!r}')
    f.destroy()

    print('\nK7: form -> case -> JSON -> form, and the Qt twin agrees')
    for d in (1, 2, 3):
        f = form(d)
        if d > 1:
            f.obstacles.set([(0.1, 0.2, 0.3, 0.4)] if d == 2
                            else [(0.1, 0.2, 0.3, 0.4, 0.5, 0.6)])
        for fam in want[d]:
            f.v[f'vtk_{fam}_on'].set(True)
        if d == 3:
            f.v['vtk_s_mode'].set('step')
            f.v['vtk_s_steps'].set('40')
            f.v['vtk_v_time'].set('0.00025')
            f.vtk_planes.set([('x', 0.3), ('z', 1.1)])
            f.v['vtk_fields'].cells[('rhoE', 'volumes')].set(True)
        case = f.get_case()
        text = json.dumps(case_to_dict(case), sort_keys=True)
        g = form(d)
        g.set_case(case_from_dict(json.loads(text)))
        diff = [k for k in f.v if k.startswith('vtk_')
                and f.v[k].get() != g.v[k].get()]
        if d == 3 and f.vtk_planes.get() != g.vtk_planes.get():
            diff.append('vtk_planes')
        check(f'{d}D: every card value survives', not diff, str(diff))
        check(f'{d}D: the case written again is the same JSON',
              json.dumps(case_to_dict(g.get_case()), sort_keys=True) == text)
        check(f'{d}D: the loaded mode sets the disabled box',
              all(entry_on(g, f'vtk_{fam}_time')
                  == (g.v[f'vtk_{fam}_mode'].get() == 'time')
                  for fam in want[d]))
        if d == 3:
            got = case_to_dict(case)
            check('3D: the JSON of sec. 3.3',
                  got['vtk_surfaces']['planes'] == [['x', 0.3], ['z', 1.1]]
                  and got['vtk_surfaces']['value'] == 40
                  and got['vtk_volumes']['value'] == 0.00025      # [s]
                  and got['vtk_volumes']['fields']
                  == ['p', 'rho', 'U', 'rhoE'], str(got['vtk_surfaces']))
            # the Qt form builds the same case from the same file
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
            from blastlab.ui.testing import ensure_qapp
            ensure_qapp()
            from blastlab.ui.case_form import CaseForm as QtForm
            q = QtForm(3, mode='blastfoam')
            q.set_case(case_from_dict(json.loads(text)))
            check('3D: the Qt form loads it to the same case',
                  json.dumps(case_to_dict(q.get_case()), sort_keys=True)
                  == text)
            q.deleteLater()
        f.destroy()
        g.destroy()

    print('\nK8: a bad value in the inactive box never blocks a run')
    f = form(3)
    f.v['vtk_v_on'].set(True)
    f.v['vtk_v_steps'].set('lots')
    try:
        ok = f.get_case().vtk_volumes['value'] == 0.001 and not f._bad
    except ValueError:
        ok = False
    check('Time mode: a bad steps box is not read', ok)
    f.v['vtk_v_mode'].set('step')
    try:
        f.get_case()
        raised = ''
    except ValueError as exc:
        raised = str(exc)
    check('Step mode: it is reported and marked',
          'VTK Volumes every [steps]' in raised
          and f._bad == {'vtk_v_steps'}, raised)
    f.destroy()
    f = form(2)
    f.v['vtk_s_on'].set(True)
    rep = validate_case(f.get_case())
    check('2D obstacles without obstacles: "nothing to sample"',
          any('nothing to sample' in e for e in rep.errors), str(rep.errors))
    f.destroy()

    print('\nK9: what the matrix labels say (GUI QA 2026-09-27)')
    f = form(3)
    labels = {str(w.cget('text')): w for w in
              f._vtk_grid.winfo_children() if isinstance(w, ctk.CTkLabel)}
    pk = labels.get('Peak overpressure')
    tip = getattr(getattr(pk, '_blastlab_tip', None), 'text', '')
    # owner decision 4 (2026-09-27, out-2-surface-layout.md), replacing
    # F1: the export writes pMax - ambient
    check('decision 4: the pMax row reads "Peak overpressure"',
          pk is not None and 'Peak pressure' not in labels,
          str(sorted(labels)))
    check('decision 4: its tooltip says minus ambient, the array name and '
          'pMax', all(s in tip for s in ('minus ambient', '101.325 kPa',
                                          'Peak_Overpressure', 'pMax')), tip)

    def tip_of(text):
        return getattr(getattr(labels.get(text), '_blastlab_tip', None),
                       'text', '')
    # OUT-4b B1 (owner Q1): timeOfArrival is the time of PEAK pressure
    # (blastFoam User Guide v6.0, sec. 15.12), so the row says so
    check('B1: the timeOfArrival row reads "Time of peak", no "Arrival time"',
          'Time of peak' in labels and 'Arrival time' not in labels,
          str(sorted(labels)))
    check('B1: its tooltip says maximum, not the first arrival, and names '
          'Time_Of_Peak and timeOfArrival',
          all(s in tip_of('Time of peak') for s in (
              'maximum', 'not the first arrival', 'Time_Of_Peak',
              'timeOfArrival')), tip_of('Time of peak'))
    def walk(w):
        yield w
        for ch in w.winfo_children():
            yield from walk(ch)
    card = [str(w.cget('text')) for w in walk(f._vtk_card)
            if isinstance(w, ctk.CTkLabel)]
    check('the Tk card shows the shared captions (Qt parity)',
          F.VTK_PLANES_CAPTION in card and F.VTK_MATRIX_CAPTION in card,
          str([t for t in card if 'Quantities' in t or 'planes' in t]))
    check('P22: "Every [s]" and the line that the files use seconds',
          any(t.startswith('Every [s]') for t in card)
          and F.VTK_SECONDS_NOTE in card
          and not any('[ms]' in t for t in card), str(card))
    check('no user-facing "OUT-4" on the card or its header tooltips',
          not any('OUT-' in t for t in card + [tip_of(t) for t in labels]))
    for row, want in (('Energy', 'total energy per unit volume'),
                      ('Products', 'volume fraction of detonation products')):
        check(f'the "{row}" tooltip explains it', want in tip_of(row),
              tip_of(row))
    check('the "Volumes" header tooltip says whole-domain output',
          'whole-domain output' in tip_of('Volumes'), tip_of('Volumes'))
    # P13 / P24: full-word headers, in the order of the family boxes
    for d, want in ((1, ['Gauges', 'Whole domain']),
                    (2, ['Gauges', 'Whole domain', 'Obstacles']),
                    (3, ['Gauges', 'Sections', 'Obstacles', 'Volumes'])):
        g = form(d)
        heads = [str(w.cget('text')) for w in g._vtk_grid.winfo_children()
                 if isinstance(w, ctk.CTkLabel)][:len(want)]
        check(f'{d}D: full-word headers {want}', heads == want, str(heads))
        info = g._vtk_card.grid_info()
        check(f'{d}D: the card spans both columns, below every other card',
              int(info.get('columnspan', 1)) == 2
              and int(info.get('row', -1)) == max(
                  int(w.grid_info().get('row', 0))
                  for w in g.winfo_children() if w.winfo_manager() == 'grid'),
              str(info))
        g._vtk_fit(300)
        side_narrow = g._vtk_side
        g._vtk_fit(2000)
        check(f'{d}D: stacked when narrow, side by side when wide',
              side_narrow is False and g._vtk_side is True)
        g.destroy()
    f.destroy()

    print('\nK12: the Gauges column extras (OUT-4a)')
    for d in (1, 2, 3):
        f = form(d)
        f.v['vtk_fields'].cells[('T', 'gauges')].set(True)
        f.v['vtk_fields'].fire()
        case = f.get_case()
        check(f'{d}D: a ticked T at the gauges is in vtk_gauges',
              case.vtk_gauges == {'fields': ['T']}
              and case_to_dict(case).get('vtk_gauges') == {'fields': ['T']},
              str(case.vtk_gauges))
        text = json.dumps(case_to_dict(case), sort_keys=True)
        g = form(d)
        g.set_case(case_from_dict(json.loads(text)))
        check(f'{d}D: save / reload restores the tick',
              g.v['vtk_fields'].cells[('T', 'gauges')].get() is True
              and json.dumps(case_to_dict(g.get_case()),
                             sort_keys=True) == text)
        g.destroy()
        f.set_mode('native')
        ROOT.update_idletasks()
        check(f'{d}D native: hidden, and no vtk_gauges key',
              not card_shown(f)
              and 'vtk_gauges' not in case_to_dict(f.get_case()))
        f.destroy()
    f = form(3)
    check('the Tk caption says the gauges always record p, rho, U',
          'always recorded' in F.VTK_MATRIX_CAPTION
          and 'fixed' not in F.VTK_MATRIX_CAPTION)
    f.destroy()

    print('\nK11: the Keep all fields in WSL box (OUT-3)')
    for d in (1, 2, 3):
        f = form(d)
        box = f._keep_all_box
        check(f'{d}D: the box is on the card, unticked, blastFoam-scoped',
              str(box.cget('text')) == F.KEEP_ALL_CAPTION
              and f.v['keep_all_fields'].get() is False
              and box in f._scoped['blastfoam']
              and box.winfo_manager() == 'grid')
        check(f'{d}D: default case: False, not written',
              f.get_case().keep_all_fields is False
              and 'keep_all_fields' not in case_to_dict(f.get_case()))
        box.select()
        text = json.dumps(case_to_dict(f.get_case()), sort_keys=True)
        check(f'{d}D: ticked -> the JSON carries it',
              json.loads(text).get('keep_all_fields') is True)
        g = form(d)
        g.set_case(case_from_dict(json.loads(text)))
        check(f'{d}D: form -> case -> JSON -> form keeps the tick',
              g.v['keep_all_fields'].get() is True
              and json.dumps(case_to_dict(g.get_case()),
                             sort_keys=True) == text)
        g.destroy()
        f.set_mode('native')
        ROOT.update_idletasks()
        check(f'{d}D native: hidden, not in the case',
              not card_shown(f) and box.winfo_manager() == ''
              and 'keep_all_fields' not in case_to_dict(f.get_case()))
        f.destroy()

    ROOT.destroy()
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} check(s): {FAIL}')
        sys.exit(1)
    print('GUI OUTPUT CARD: PASS')


if __name__ == '__main__':
    main()
