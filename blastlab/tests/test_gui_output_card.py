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
        check(f'{d}D: a box per quantity and destination column',
              set(cells) == {(r, c) for r in rows for c in dest},
              f'{len(cells)} cells')
        locked = f._vtk_grid.locked
        check(f'{d}D: the Gauges column is locked, p / rho / U ticked',
              len(locked) == len(rows)
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
              entry_on(f, f'vtk_{fam}_ms')
              and not entry_on(f, f'vtk_{fam}_steps'))
        f.v[f'vtk_{fam}_ms'].set('0.75')
        f._vtk_radios[fam][1].invoke()          # Step
        check(f'{fam}: Step disables the ms box instead',
              f.v[f'vtk_{fam}_mode'].get() == 'step'
              and not entry_on(f, f'vtk_{fam}_ms')
              and entry_on(f, f'vtk_{fam}_steps'))
        check(f'{fam}: which keeps its value',
              f.v[f'vtk_{fam}_ms'].get() == '0.75')
    f.destroy()

    print('\nK5: the first tick fills the defaults')
    f = form(3)
    f.v['vtk_s_on'].set(True)
    check('3D surfaces: p, pMax on sections and obstacles',
          f.v['vtk_fields'].get() == {'sections': ['p', 'pMax'],
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
    f.destroy()
    f = form(2)
    f.v['vtk_s_on'].set(True)
    check('2D obstacles: p, pMax',
          f.v['vtk_fields'].get() == {'obstacles': ['p', 'pMax'],
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
            f.v['vtk_v_ms'].set('0.25')
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
              all(entry_on(g, f'vtk_{fam}_ms')
                  == (g.v[f'vtk_{fam}_mode'].get() == 'time')
                  for fam in want[d]))
        if d == 3:
            got = case_to_dict(case)
            check('3D: the JSON of sec. 3.3',
                  got['vtk_surfaces']['planes'] == [['x', 0.3], ['z', 1.1]]
                  and got['vtk_surfaces']['value'] == 40
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
        ok = f.get_case().vtk_volumes['value'] == 1.0 and not f._bad
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

    ROOT.destroy()
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} check(s): {FAIL}')
        sys.exit(1)
    print('GUI OUTPUT CARD: PASS')


if __name__ == '__main__':
    main()
