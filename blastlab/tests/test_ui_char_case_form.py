"""Characterisation: the Qt Setup form's form <-> Case mapping (Phase 5a).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 5a (finding F4). Drives the
REAL `ui.case_form.CaseForm` offscreen across dims 0-3 and both solver
modes, and pins, in one golden (`char_golden/ui_case_form.json`):

  * `get_case()` on the fresh form, on representative inputs and on
    invalid ones: the resulting `case_to_dict` JSON, or the exact error
    text (message order included) and the set of fields marked bad;
  * which fields each solver mode reads (a bad value in a field the mode
    hides must not block the case), the `gauge_file or None` rule, the
    guarded reconstruction order, float/int parsing (whitespace, empty,
    scientific notation, a decimal comma, nan/inf, fractional ints), and
    the native-mode material rule (UX-E2: native always sends 'TNT');
  * `set_case()`: every field value, every point list and the hidden /
    disabled rows after loading a case, then the case read back.

Phase 5a moves get_case/set_case into models/fields.py; this golden must
not move with them.

Script only - it builds Qt widgets, so conftest.py keeps it out of
pytest collection (`test_ui_*.py`).

Run:  cd blastlab/tests && python test_ui_char_case_form.py [--update]
"""
import sys

import char_common as cc
from blastlab.ui.testing import ensure_qapp                 # noqa: E402

app = ensure_qapp()

from blastlab.core import assessment                        # noqa: E402
from blastlab.core.case import (Case1D, Case2D, Case3D,     # noqa: E402
                                case_to_dict)
from blastlab.ui.case_form import CaseForm                  # noqa: E402

MODES = ('native', 'blastfoam')


def _to_dict(case):
    if getattr(case, 'dim', None) == 0:
        return assessment.case_to_dict(case)
    return case_to_dict(case)


def read(form):
    """get_case() as data: the case dict, or the error and the bad set."""
    try:
        case = form.get_case()
    except ValueError as exc:
        return {'error': str(exc), 'bad': sorted(form.bad)}
    return {'case': _to_dict(case), 'bad': sorted(form.bad)}


def dump(form):
    """Everything set_case() leaves behind in the form."""
    return {
        'values': {k: v.get() for k, v in form.v.items()},
        'points': {k: p.get() for k, p in form.points.items()},
        'hidden': sorted(n for n in form.widgets if form.widgets[n].isHidden()),
        'disabled': sorted(n for n in form.widgets
                           if not form.widgets[n].isEnabled()),
    }


def fill(form, values=None, points=None):
    for k, val in (values or {}).items():
        form.v[k].set(val)
    for k, rows in (points or {}).items():
        form.points[k].set(rows)


# ── scenarios: (label, values, points) per dimension ─────────────────────
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

S0 = [
    ('typed', {'name': ' run A ', 'propellant': 'double_base',
               'ov_n': '0.7', 'ov_a': '', 'ov_r_atm': '2.5', 'ov_web': '1',
               'ov_p_ext': '', 'ov_secondary': '4', 'measured': True,
               'charge_kg': '10', 'volume_m3': '2', 'vent_area': '0',
               'cd': '0', 'p_ign': '', 'p0_chamber': '', 'n_cohorts': '0',
               'spread_time': '12', 'n_out': '', 'h_c': '0',
               'rot_limit': '', 'room_size': '4,3; 2.5',
               'room_origin': '', 'vent_rect': '0,1,0,2', 'room_wall': '0.3',
               'domain_size': '1,2', 'n_snap_vent': '', 'p_burst': '0.2'},
     {'standoffs': [(5.0,), (10.0,)],
      'vent_gauges': [(1.0, 2.0, 3.0)]}),
    ('uniform', {'scenario_kind': 'uniform', 'n_cohorts': '7',
                 'spread_time': '9', 'measured': False, 'ov_n': '0.8'}, None),
    ('bad', {'ov_n': 'x', 'charge_kg': 'nan', 'n_cohorts': '2.5',
             'n_out': 'many', 'n_snap_vent': '1.5', 'cd': 'q',
             'p0_chamber': 'inf', 'vent_rect': '1,2,x,4'}, None),
    ('zero_p0', {'p0_chamber': '0', 'n_snap_vent': '0'}, None),
]

SCENARIOS = {1: S1, 2: S2, 3: S3, 0: S0}


def _set_case_sources():
    """Non-default cases for set_case, one per dimension (and 0)."""
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
    c3 = Case3D(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.05,
                center=(1.0, 1.0, 0.5), charge=5.0, charge_resolution='smear',
                slice_axis='x', slice_pos=0.25,
                charges=[(0.5, 0.5, 0.5, 1.0)], trigger_gauge=0,
                trigger_file='ignored.npz', gauges=[(1.0, 1.0, 1.0)],
                amr_display_level=None, anim_mesh=True)
    return {1: [('c1', c1)], 2: [('c2_axisym', c2), ('c2_planar', c2p)],
            3: [('c3', c3)], 0: [('starter', cc.hd13_starter_case())]}


def collect():
    out = {}
    for dim in (1, 2, 3, 0):
        modes = MODES if dim else ('native',)
        for mode in modes:
            key = f'dim{dim}_{mode}'
            f = CaseForm(dim, mode=mode)
            out[f'{key}/fresh'] = read(f)
            for label, values, points in SCENARIOS[dim]:
                f = CaseForm(dim, mode=mode)
                fill(f, values, points)
                out[f'{key}/{label}'] = read(f)
            for label, src in _set_case_sources()[dim]:
                f = CaseForm(dim, mode=mode)
                f.set_case(src)
                out[f'{key}/set_{label}'] = dump(f)
                out[f'{key}/set_{label}/get'] = read(f)
    # the switch: values typed in one mode are read after switching
    for dim in (2, 3):
        f = CaseForm(dim, mode='native')
        fill(f, *SCENARIOS[dim][0][1:])
        f.set_mode('blastfoam')
        out[f'dim{dim}_native_to_blastfoam/typed'] = read(f)
        f.set_mode('native')
        out[f'dim{dim}_back_to_native/typed'] = read(f)
    return out


def test_case_form_mapping():
    cc.check_json('ui_case_form.json', collect())


def main():
    return cc.run_main('CHAR UI CASE FORM', [test_case_form_mapping])


if __name__ == '__main__':
    sys.exit(main())
