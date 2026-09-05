"""core.refine - the predicted refined-mesh structure (no GUI, no WSL).

Zone snapping, the fine-grid level map, the source-id bijection with the
predicted cell count, the 2:1 grading / axis / level rules, the automatic
charge zones, cell-edge segments and the foam-cell matching that T18's
backend relies on.

Run:  cd blastlab/tests && python test_refine.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core import refine                                # noqa: E402
from blastlab.core.case import (Case2D, Case3D, case_from_dict,  # noqa: E402
                                case_to_dict, validate_case)

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def planar(zones, dx=0.5, L=2.0, **kw):
    """A planar 2D foam case without a charge (no global auto-refine),
    so the zone logic is isolated."""
    c = Case2D(geometry='planar', Lx=L, Ly=L, cell_size_m=dx, charge=None,
               center=(L / 2, L / 2), solver='blastfoam', **kw)
    c.refine_zones = list(zones)
    return c


def centres_from_ids(ids, fine):
    """Synthetic foam cell centres = mean fine-centre per predicted id."""
    axes = [fine[k] for k in ('x_c', 'y_c', 'z_c')[:ids.ndim]]
    grids = np.meshgrid(*axes, indexing='ij')
    flat = ids.ravel()
    m = flat >= 0
    n = int(flat.max()) + 1
    cnt = np.bincount(flat[m], minlength=n)
    return np.column_stack([np.bincount(flat[m], weights=g.ravel()[m],
                                        minlength=n) / cnt for g in grids])


def test_snap():
    print("\nsnapping")
    z, moved = refine.snap_zone((0.37, 1.27, 0.5, 1.5, 1), 0.1, 2)
    check('level 1 snaps outward to base faces',
          np.allclose(z[:4], (0.3, 1.3, 0.5, 1.5)) and z[4] == 1 and moved,
          str(z))
    z, moved = refine.snap_zone((0.37, 1.27, 0.5, 1.5, 2), 0.1, 2)
    check('level 2 snaps to level-1 faces (dx/2)',
          np.allclose(z[:4], (0.35, 1.3, 0.5, 1.5)), str(z))
    z, moved = refine.snap_zone((0.5, 1.5, 0.5, 1.5, 1), 0.5, 2)
    check('aligned zone unchanged', not moved and np.allclose(z[:4], (0.5, 1.5, 0.5, 1.5)))


def test_plan_2d():
    print("\n2D plan: nested zones on a 4x4 base")
    c = planar([(0.5, 1.5, 0.5, 1.5, 1), (0.75, 1.25, 0.75, 1.25, 2)])
    p = refine.plan_levels(c)
    check('base dx kept (no charge)', p.dx_base == 0.5, str(p.dx_base))
    check('lmax = 2, fine grid 16x16', p.lmax == 2 and p.levels.shape == (16, 16),
          f'{p.lmax} {p.levels.shape}')
    check('predicted cells = 12 + 12 + 16 = 40', p.n_pred == 40, str(p.n_pred))
    check('n_fine = 256', p.n_fine == 256, str(p.n_fine))
    ids = refine.fine_src(p.levels, p.lmax)
    check('fine_src ids are a bijection onto the predicted cells',
          len(np.unique(ids)) == p.n_pred and ids.min() == 0 and ids.max() == p.n_pred - 1)
    blocks = np.bincount(ids.ravel())
    check('block sizes follow the levels (16 / 4 / 1 fine cells)',
          sorted(set(blocks.tolist())) == [1, 4, 16], str(sorted(set(blocks.tolist()))))
    check('level map: centre cell level 2, corner level 0',
          p.levels[8, 8] == 2 and p.levels[0, 0] == 0 and p.levels[4, 8] == 1,
          str((p.levels[8, 8], p.levels[0, 0], p.levels[4, 8])))
    e, w = refine.validate_zones(c, p)
    check('nested zones validate', e == [] and w == [], str(e + w))
    check('Plan.meta carries levels/lmax/dx_base/zones',
          set(p.meta()) == {'levels', 'lmax', 'dx_base', 'zones'})

    # level-2 zone directly inside level 0 -> grading error
    c2 = planar([(0.75, 1.25, 0.75, 1.25, 2)])
    e, _ = refine.validate_zones(c2, refine.plan_levels(c2))
    check('level jump of 2 is refused with a location',
          len(e) == 1 and 'jumps by 2' in e[0] and 'near (' in e[0], str(e))
    # margin: level-2 zone flush with the level-1 zone boundary -> refused
    c3 = planar([(0.5, 1.5, 0.5, 1.5, 1), (0.5, 1.0, 0.5, 1.0, 2)])
    e, _ = refine.validate_zones(c3, refine.plan_levels(c3))
    check('level-2 zone flush with its level-1 zone is refused',
          len(e) == 1 and 'jumps by 2' in e[0], str(e))
    # one level-1 cell of margin is enough
    c4 = planar([(0.5, 1.5, 0.5, 1.5, 1), (0.75, 1.0, 0.75, 1.0, 2)])
    e, _ = refine.validate_zones(c4, refine.plan_levels(c4))
    check('one level-1 cell of margin is enough', e == [], str(e))
    # bad boxes / levels
    c5 = planar([(0.5, 1.5, 0.5, 1.5, 5)])
    e, _ = refine.validate_zones(c5, refine.plan_levels(c5))
    check('level 5 refused', any('1..4' in x for x in e), str(e))
    c6 = planar([(1.5, 0.5, 0.5, 1.5, 1), (0.0, 3.0, 0.0, 1.0, 1)])
    e, _ = refine.validate_zones(c6, refine.plan_levels(c6))
    check('inverted / out-of-domain boxes refused', len(e) == 2, str(e))
    try:
        refine.plan_levels(planar([(0.5, 1.5, 0.5, 1.5, 1.5)]))
        check('non-integer level raises', False)
    except ValueError as exc:
        check('non-integer level raises', 'whole number' in str(exc))
    try:
        refine.plan_levels(planar([(0.5, 1.5, 0.5, 1)]))
        check('wrong arity raises', False)
    except ValueError as exc:
        check('wrong arity raises', 'box edges' in str(exc))
    # snapping warning
    c7 = planar([(0.6, 1.4, 0.5, 1.5, 1)])
    p7 = refine.plan_levels(c7)
    e, w = refine.validate_zones(c7, p7)
    check('unaligned zone snaps outward with a warning',
          e == [] and len(w) == 1 and 'snapped' in w[0]
          and np.allclose(p7.zones[0][:4], (0.5, 1.5, 0.5, 1.5)), str(w))


def test_axisym():
    print("\naxisymmetric axis rule")
    c = Case2D(geometry='axisymmetric', Lx=1.0, Ly=2.0, cell_size_m=0.1,
               charge=None, center=(0.0, 1.0), solver='blastfoam')
    c.refine_zones = [(0.0, 0.5, 0.5, 1.5, 1), (0.0, 0.3, 0.8, 1.2, 2)]
    e, _ = refine.validate_zones(c, refine.plan_levels(c))
    check('level 2 on the axis refused', len(e) == 1 and 'axis' in e[0], str(e))
    c.refine_zones = [(0.0, 0.5, 0.5, 1.5, 1), (0.2, 0.4, 0.8, 1.2, 2)]
    e, _ = refine.validate_zones(c, refine.plan_levels(c))
    check('level 2 off the axis is fine', e == [], str(e))
    c.refine_zones = [(0.0, 0.5, 0.5, 1.5, 1)]
    e, _ = refine.validate_zones(c, refine.plan_levels(c))
    check('level 1 on the axis is fine', e == [], str(e))


def test_auto_zones_3d():
    print("\n3D automatic charge zones (charge_refine='zone')")
    c = Case3D(Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.1, charge=1.0,
               center=(0.5, 0.5, 0.5), solver='blastfoam')
    c.charge_refine = 'zone'
    p = refine.plan_levels(c, rho0=1630.0)
    check('1 kg TNT on a 10 cm base needs level 4', p.auto_level == 4 and p.lmax == 4,
          f'{p.auto_level} {p.lmax}')
    check('base cell kept at 0.1 m', p.dx_base == 0.1, str(p.dx_base))
    check('four nested auto zones', len(p.auto_zones) == 4 and
          [refine.zone_level(z) for z in p.zones] == [1, 2, 3, 4], str(p.zones))
    e, w = refine.validate_zones(c, p)
    check('auto zones satisfy 2:1 grading', e == [], str(e))
    check('finest zone is compact (< 0.25 m wide)',
          p.zones[-1][1] - p.zones[-1][0] < 0.25, str(p.zones[-1]))
    check('cell count far below the fine grid',
          40_000 < p.n_pred < 60_000 and p.n_fine == 160 ** 3,
          f'{p.n_pred} {p.n_fine}')
    ids = refine.fine_src(p.levels, p.lmax)
    check('3D bijection', len(np.unique(ids)) == p.n_pred)
    # match_cells: shuffled synthetic centres reproduce the structure
    cent = centres_from_ids(ids, p.fine)
    perm = np.random.default_rng(0).permutation(len(cent))
    remap = refine.match_cells(cent[perm], p.fine, ids)
    check('match_cells: remap gives the foam cell covering each fine cell',
          np.all(perm[remap] == ids))
    try:
        refine.match_cells(cent[perm][:-1], p.fine, ids)
        check('missing cell raises', False)
    except RuntimeError as exc:
        check('missing cell raises', 'predicts' in str(exc), str(exc))
    dup = cent[perm].copy()
    dup[0] = dup[1]
    try:
        refine.match_cells(dup, p.fine, ids)
        check('mis-split cell raises', False)
    except RuntimeError as exc:
        check('mis-split cell raises', 'hit by' in str(exc), str(exc))
    # 'global' mode keeps today's rule: the whole grid refines
    c.charge_refine = 'global'
    pg = refine.plan_levels(c, rho0=1630.0)
    check("'global' refines the base dx instead", pg.dx_base < 0.011 and pg.lmax == 0,
          f'{pg.dx_base} {pg.lmax}')
    # too small a charge for MAX_LEVEL
    c.charge_refine = 'zone'
    c.charge = 0.01
    pz = refine.plan_levels(c, rho0=1630.0)
    e, _ = refine.validate_zones(c, pz)
    check('charge needing > MAX_LEVEL is refused with a base-cell hint',
          len(e) == 1 and 'lower the base cell' in e[0], str(e))


def test_obstacles_and_segments():
    print("\nobstacles + cell-edge segments")
    c = planar([(0.0, 0.5, 0.0, 0.5, 1)], dx=0.5, L=1.0)
    c.obstacles = [(0.5, 1.0, 0.5, 1.0)]
    p = refine.plan_levels(c)
    check('solid base cell excluded from the count (3 base - 1 solid + 4 fine = 6)',
          p.n_pred == 6, str(p.n_pred))
    ids = refine.fine_src(p.levels, p.lmax, p.solid_fine)
    check('solid fine cells are -1', (ids[2:, 2:] == -1).all() and (ids >= 0).sum() == 12)
    segs = refine.mesh_segments_2d(ids, p.fine['x_face'], p.fine['y_face'])
    # boundary 4 + x=0.5 (full) + y=0.5 (full) + x=0.25 (0..0.5) + y=0.25
    # (0..0.5) = 8; the solid block is one id (-1) so it has no inner edges
    check('segments: merged runs, refined cell edges, none inside the solid',
          len(segs) == 8, str(len(segs)))
    uni = refine.mesh_segments_2d(None, p.fine['x_face'], p.fine['y_face'])
    check('uniform: one segment per face line', len(uni) == 10, str(len(uni)))
    # 3D slice ids
    c3 = Case3D(Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.5, charge=None,
                center=(0.5, 0.5, 0.5), solver='blastfoam')
    c3.refine_zones = [(0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 1)]
    p3 = refine.plan_levels(c3)
    sl = refine.slice_src(p3.levels, p3.lmax, 2, 0)
    check('3D slice through the refined corner: 3 coarse + 4 fine ids',
          sl.shape == (4, 4) and len(np.unique(sl)) == 7, str(len(np.unique(sl))))
    sl_hi = refine.slice_src(p3.levels, p3.lmax, 2, 3)
    check('3D slice above it: 4 coarse ids', len(np.unique(sl_hi)) == 4)


def test_case_roundtrip_and_validation():
    print("\ncase schema + validate_case")
    c = planar([(0.5, 1.5, 0.5, 1.5, 1), (0.75, 1.25, 0.75, 1.25, 2)])
    c.charge = 100.0
    c.charge_refine = 'zone'
    d = case_to_dict(c)
    d['refine_zones'] = [list(map(float, z)) for z in d['refine_zones']]
    back = case_from_dict(d)
    check('v3 round trip keeps zones with int levels',
          back.refine_zones == c.refine_zones
          and all(isinstance(z[-1], int) for z in back.refine_zones)
          and back.charge_refine == 'zone', str(back.refine_zones))
    check('schema version is 3', d['version'] == 3)
    n = Case2D(geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.5, charge=100.0,
               center=(1.0, 1.0), solver='native')
    n.refine_zones = [(0.5, 1.5, 0.5, 1.5, 1)]
    rep = validate_case(n)
    check('native + zones -> error naming blastFoam',
          any('requires the blastFoam solver' in e for e in rep.errors), str(rep.errors))
    n.refine_zones = []
    n.charge_refine = 'zone'
    rep = validate_case(n)
    check("native + charge_refine='zone' -> same error",
          any('requires the blastFoam solver' in e for e in rep.errors), str(rep.errors))
    # foam, 50 kg/m planar charge on a 10 cm base in 'zone' mode: the
    # charge needs level 3, user zones (levels 1, 2) nest around it
    f = Case2D(geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.1, charge=50.0,
               center=(1.0, 1.0), solver='blastfoam')
    f.charge_refine = 'zone'
    f.refine_zones = [(0.5, 1.5, 0.5, 1.5, 1), (0.75, 1.25, 0.75, 1.25, 2)]
    rep = validate_case(f)
    plan = refine.plan_levels(f, rho0=1630.0)
    zone_errs = [e for e in rep.errors if 'efine' in e or 'jumps' in e]
    check('foam + nested user zones + auto zones: no refinement errors',
          zone_errs == [], str(rep.errors))
    check('report matches the plan (lmax 3, fine 0.0125 m, 160x160)',
          rep.lmax == plan.lmax == 3 and abs(rep.dx_fine - 0.0125) < 1e-12
          and rep.n_fine == plan.n_fine == 160 ** 2,
          f'{rep.lmax} {rep.dx_fine} {rep.n_fine}')
    check('note describes the refinement',
          any('Local refinement: 3 level' in x for x in rep.notes), str(rep.notes))
    check('n_cells is the predicted mesh count', rep.n_cells == plan.n_pred,
          f'{rep.n_cells} vs {plan.n_pred}')
    check("effective dx stays the base in 'zone' mode", abs(rep.effective_dx - 0.1) < 1e-12,
          str(rep.effective_dx))
    f.charge_refine = 'global'
    f.refine_zones = [(0.75, 1.25, 0.75, 1.25, 2)]
    rep = validate_case(f)
    check('grading error surfaces in validate_case',
          any('jumps by 2' in e for e in rep.errors), str(rep.errors))
    g = Case3D(Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.1, charge=1.0,
               center=(0.5, 0.5, 0.5), solver='blastfoam')
    g.charge_refine = 'zone'
    rep = validate_case(g)
    check("3D 'zone': no 'Cell size will be refined' note, auto-zone note instead",
          not any('will be refined' in x for x in rep.notes)
          and any('automatic level-4' in x for x in rep.notes), str(rep.notes))
    check("3D 'zone': effective dx stays the base", abs(rep.effective_dx - 0.1) < 1e-12,
          str(rep.effective_dx))
    check("3D 'zone': fine display grid warned about (4.1M cells)",
          any('display grid' in w for w in rep.warnings), str(rep.warnings))


if __name__ == '__main__':
    test_snap()
    test_plan_2d()
    test_axisym()
    test_auto_zones_3d()
    test_obstacles_and_segments()
    test_case_roundtrip_and_validation()
    print()
    print('REFINE: ' + ('PASS' if not FAILS else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
