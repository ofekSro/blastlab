"""Characterisation: the Tk Setup form's form <-> Case mapping (Phase 5b).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 5b (finding F4). The Tk
twin of `test_ui_char_case_form.py`: drives the REAL `gui.forms.CaseForm`
(customtkinter, withdrawn root) across dims 1-3 and both solver modes,
over the same scenarios, and pins in one golden
(`char_golden/gui_case_form.json`):

  * `get_case()` on the fresh form, on representative inputs and on
    invalid ones: the resulting `case_to_dict` JSON, or the exception
    type, its exact text and the set of fields marked bad;
  * which fields each solver mode reads, the gauge-file rule, the order
    box parsing, float/int parsing and the native-mode material rule;
  * `set_case()`: every field value, every point list, which fields end
    up hidden (the widget or a card above it not grid-managed) or
    disabled, the exact SEQUENCE of variable writes and point-list sets
    it performs (the Tk trace hooks - the axisymmetric pin, the AMR and
    video-range rows - fire in that order), then the case read back;
  * a native <-> blastFoam switch with typed values.

The Tk GUI is the permanent way back (CLAUDE.md section 9); this golden
is what proves the switch to `models/fields.py` changed only what the
owner accepted for Q1.

Script only - it builds Tk widgets, so conftest.py keeps it out of
pytest collection (`test_gui_*.py`).

Run:  cd blastlab/tests && python test_gui_char_case_form.py [--update]
"""
import sys

import char_common as cc

import customtkinter as ctk                                  # noqa: E402

from blastlab.core.case import (Case1D, Case2D, Case3D,     # noqa: E402
                                case_to_dict)
from blastlab.gui.forms import CaseForm                      # noqa: E402

MODES = ('native', 'blastfoam')
POINT_LISTS = ('gauges', 'obstacles', 'zones', 'det_pts', 'extra_charges')

ROOT = None


def _root():
    global ROOT
    if ROOT is None:
        ROOT = ctk.CTk()
        ROOT.withdraw()
    return ROOT


def make(dim, mode):
    return CaseForm(_root(), dim, mode=mode)


def points(form):
    return {k: getattr(form, k) for k in POINT_LISTS if hasattr(form, k)}


def read(form):
    """get_case() as data: the case dict, or the exception and the bad
    set. Any exception type is recorded - the Tk form let an IndexError
    out of a blank order box."""
    try:
        case = form.get_case()
    except Exception as exc:                          # noqa: BLE001
        return {'exception': type(exc).__name__, 'error': str(exc),
                'bad': sorted(form._bad)}
    return {'case': case_to_dict(case), 'bad': sorted(form._bad)}


def _hidden(form, w):
    """True when `w` or any container between it and the form has been
    taken out of the grid (grid_remove) or never placed."""
    while w is not None and w is not form:
        if w.winfo_manager() == '':
            return True
        w = w.master
    return False


def _disabled(w):
    try:
        return str(w.cget('state')) == 'disabled'
    except Exception:                                 # noqa: BLE001
        return False


def dump(form):
    """Everything set_case() leaves behind in the form."""
    widgets = {n: form._widget_for(n) for n in form.v}
    widgets = {n: w for n, w in widgets.items() if w is not None}
    widgets.update(points(form))
    return {
        'values': {k: v.get() for k, v in form.v.items()},
        'points': {k: p.get() for k, p in points(form).items()},
        'hidden': sorted(n for n, w in widgets.items() if _hidden(form, w)),
        'disabled': sorted(n for n, w in widgets.items() if _disabled(w)),
    }


def record_writes(form):
    """A list that fills with the name of every variable written and
    every point list set, in order, from now on."""
    log = []
    for name, var in form.v.items():
        var.trace_add('write', lambda *a, n=name: log.append(n))
    for name, pl in points(form).items():
        orig = pl.set

        def _set(rows, _orig=orig, _n=name):
            log.append(_n)
            return _orig(rows)
        pl.set = _set
    return log


def fill(form, values=None, pts=None):
    for k, val in (values or {}).items():
        form.v[k].set(val)
    for k, rows in (pts or {}).items():
        getattr(form, k).set(rows)


# ── scenarios: (label, values, points) per dimension ─────────────────────
# the same as test_ui_char_case_form.py (dims 1-3; the Tk GUI has no 0-D
# form)
S1 = [
    ('typed', {'radius_m': ' 12.5 ', 'charge': '2e0', 'cell': '5e-3',
               'eos': 'JWL', 'order': '2 (MUSCL)', 'cfl': '0.45',
               'bc_outer': 'reflect', 'n_snapshots': '7.0', 't_end': '1e-2',
               'material': 'PETN', 'activation': 'programmedIgnition',
               'afterburn': 'miller', 'gauge_file': '',
               'profile_out': 'p.txt'},
     {'gauges': [(0.5,), (1.0,), (2.5,)]}),
    ('bad', {'radius_m': '', 'charge': 'abc', 'cell': 'nan',
             'cfl': '1,5', 'n_snapshots': '2.7', 't_end': 'inf',
             'order': 'garbage'}, None),
    ('bad2', {'radius_m': '1e400', 'n_snapshots': 'x', 'order': ''}, None),
    ('order_blank_word', {'order': ' 2'}, None),
]

S2 = [
    ('typed', {'geometry': 'planar', 'Lx': '6', 'Ly': ' 3.5', 'cell': '0.05',
               'init_mode': 'charge', 'charge': '1.5', 'material': 'PETN',
               'cx': '1.25', 'cy': '0.5', 'eos': 'JWL',
               'order': '2 (MUSCL)', 'activation': 'none',
               'afterburn': 'miller', 'charge_refine': 'zone',
               'n_snapshots': '4', 'cfl': '0.35', 'n_procs': '6',
               't_end': '0.02', 'bc_x_lo': 'transmit', 'bc_y_hi': 'reflect',
               'gauge_file': '', 'anim_file': '',
               'anim_scale': 'fixed (manual)', 'anim_clim_min': '1',
               'anim_clim_max': '2.5e2', 'record': False, 'anim_mesh': True,
               'profile_out': 'out.npz', 'profile_in': '',
               'trigger_gauge': '2.9', 'trigger_action': 'terminate',
               'trigger_file': ''},
     {'gauges': [(1.0, 0.5), (2.0, 0.5)],
      'obstacles': [(3.0, 3.5, 0.0, 1.0)],
      'zones': [(0.0, 2.0, 0.0, 1.0, 2.0)],
      'det_pts': [(1.25, 0.5)]}),
    ('amr', {'amr_levels': '2', 'amr_estimator': 'Lohner',
             'amr_refine': '0.3', 'amr_unrefine': '0.1',
             'amr_interval': '3', 'amr_buffer': '1', 'amr_max_cells': '5e5',
             'amr_display_level': '1', 'charge_refine': 'zone',
             'trigger_gauge': 'abc'}, None),
    ('amr_bad', {'amr_levels': '1', 'amr_refine': 'x', 'amr_interval': '1.5',
                 'amr_display_level': 'auto', 'n_procs': 'q'}, None),
    ('bad', {'Lx': 'x', 'Ly': '', 'cell': '0,025', 'charge': 'nan',
             'cx': 'a', 'cy': 'b', 'cfl': 'inf', 'n_snapshots': '1.5',
             't_end': '', 'order': 'zz', 'n_procs': 'bad',
             'amr_levels': '0', 'amr_refine': 'bad',
             'anim_scale': 'fixed (manual)', 'anim_clim_min': 'lo',
             'anim_clim_max': ''}, None),
    ('trigger0', {'trigger_gauge': '0', 'trigger_file': 'remap.npz',
                  'trigger_action': 'remap'}, None),
]

S3 = [
    ('typed', {'Lx': '2', 'Ly': '2.5', 'Lz': '3', 'cell': '0.04',
               'init_mode': 'charge', 'charge': '10', 'material': 'PETN',
               'charge_res': 'smear', 'cx': '1', 'cy': '1.25', 'cz': '0.5',
               'eos': 'JWL', 'order': '2 (MUSCL)', 'n_procs': '4',
               'slice_axis': 'z', 'slice_pos': ' 0.75 ', 't_end': '5e-3',
               'bc_z_lo': 'transmit', 'gauge_file': 'g3.txt',
               'anim_scale': 'fixed (manual)', 'anim_clim_min': '0',
               'anim_clim_max': '100', 'trigger_gauge': '1'},
     {'gauges': [(1.0, 1.0, 1.0)],
      'obstacles': [(0.1, 0.2, 0.3, 0.4, 0.5, 0.6)],
      'zones': [(0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 1.0)],
      'extra_charges': [(0.5, 0.5, 0.5, 2.0)],
      'det_pts': [(1.0, 1.25, 0.5)]}),
    ('bad', {'Lz': 'x', 'cz': '', 'slice_pos': 'mid', 'charge_res': 'smear',
             'order': 'no', 'amr_levels': '3', 'amr_max_cells': '1.5',
             'amr_display_level': ' '}, None),
    ('slice_blank', {'slice_pos': '   '}, None),
]

SCENARIOS = {1: S1, 2: S2, 3: S3}


def _set_case_sources():
    """Non-default cases for set_case, one or two per dimension (the
    ones test_ui_char_case_form.py loads)."""
    c1 = Case1D(radius_m=3.0, charge_kg=0.5, cell_size_m=0.002, eos='JWL',
                order=2, cfl=0.4, bc_outer='transmit', n_snapshots=3,
                t_end=0.004, gauge_radii=[0.5, 1.5], gauge_file=None,
                profile_file='prof.txt', material='PETN',
                activation='none', afterburn=None)
    c2 = Case2D(geometry='axisymmetric', Lx=5.0, Ly=4.0, cell_size_m=0.05,
                center=(1.0, 1.5), charge=2.0, eos='JWL', order=2,
                bcs=dict(x_lo='transmit', x_hi='wall', y_lo='reflect',
                         y_hi='transmit'),
                gauges=[(1.0, 2.0)], obstacles=[(2.0, 2.5, 0.0, 1.0)],
                refine_zones=[(0.0, 1.0, 0.0, 1.0, 2)],
                det_points=[(0.0, 1.5)], gauge_file='g.txt',
                anim_file=None, anim_scale='manual', anim_clim=(5.0, 50.0),
                record_frames=0, trigger_gauge=1, trigger_action='remap',
                trigger_file='r.npz', amr_levels=2, amr_estimator='Lohner',
                amr_refine=0.35, amr_display_level=1, n_procs=3,
                material='PETN', afterburn='miller', charge_refine='zone',
                profile_file='o.npz', t_end=0.01)
    c2p = Case2D(geometry='planar', center=(0.5, 0.75), charge=None,
                 init_mode='profile1d', profile_file_in='in.txt')
    c2n = Case2D(gauge_file=None)
    c3 = Case3D(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.05,
                center=(1.0, 1.0, 0.5), charge=5.0, charge_resolution='smear',
                slice_axis='x', slice_pos=0.25,
                charges=[(0.5, 0.5, 0.5, 1.0)], trigger_gauge=0,
                trigger_file='ignored.npz', gauges=[(1.0, 1.0, 1.0)],
                amr_display_level=None, anim_mesh=True)
    return {1: [('c1', c1)],
            2: [('c2_axisym', c2), ('c2_planar', c2p),
                ('c2_no_gauge_file', c2n)],
            3: [('c3', c3)]}


def collect():
    out = {}
    for dim in (1, 2, 3):
        for mode in MODES:
            key = f'dim{dim}_{mode}'
            f = make(dim, mode)
            out[f'{key}/fresh'] = read(f)
            out[f'{key}/fresh/dump'] = dump(f)
            f.destroy()
            for label, values, pts in SCENARIOS[dim]:
                f = make(dim, mode)
                fill(f, values, pts)
                out[f'{key}/{label}'] = read(f)
                f.destroy()
            for label, src in _set_case_sources()[dim]:
                f = make(dim, mode)
                log = record_writes(f)
                f.set_case(src)
                out[f'{key}/set_{label}'] = dump(f)
                out[f'{key}/set_{label}/writes'] = list(log)
                out[f'{key}/set_{label}/get'] = read(f)
                f.destroy()
    # the switch: values typed in one mode are read after switching
    for dim in (1, 2, 3):
        f = make(dim, 'native')
        fill(f, *SCENARIOS[dim][0][1:])
        f.set_mode('blastfoam')
        out[f'dim{dim}_native_to_blastfoam/typed'] = read(f)
        out[f'dim{dim}_native_to_blastfoam/dump'] = dump(f)
        f.set_mode('native')
        out[f'dim{dim}_back_to_native/typed'] = read(f)
        f.destroy()
    return out


def test_gui_case_form_mapping():
    try:
        cc.check_json('gui_case_form.json', collect())
    finally:
        global ROOT
        if ROOT is not None:
            ROOT.destroy()
            ROOT = None


def main():
    return cc.run_main('CHAR GUI CASE FORM', [test_gui_case_form_mapping])


if __name__ == '__main__':
    sys.exit(main())
