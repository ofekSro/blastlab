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
    check('schema version is current (5: amr)', d['version'] == 5,
          str(d['version']))
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
    # charge needs level 4 (FOAM_EXP_CELLS = 8 across r_exp; it was
    # level 3 at the native 5-cell target), user zones (1, 2) nest
    f = Case2D(geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.1, charge=50.0,
               center=(1.0, 1.0), solver='blastfoam')
    f.charge_refine = 'zone'
    f.refine_zones = [(0.5, 1.5, 0.5, 1.5, 1), (0.75, 1.25, 0.75, 1.25, 2)]
    rep = validate_case(f)
    plan = refine.plan_levels(f, rho0=1630.0)
    zone_errs = [e for e in rep.errors if 'efine' in e or 'jumps' in e]
    check('foam + nested user zones + auto zones: no refinement errors',
          zone_errs == [], str(rep.errors))
    check('report matches the plan (lmax 4, fine 0.00625 m, 320x320)',
          rep.lmax == plan.lmax == 4 and abs(rep.dx_fine - 0.00625) < 1e-12
          and rep.n_fine == plan.n_fine == 320 ** 2,
          f'{rep.lmax} {rep.dx_fine} {rep.n_fine}')
    check('note describes the refinement',
          any('Local refinement: 4 level' in x for x in rep.notes), str(rep.notes))
    check('note predicts the set mass',
          any('Charge cells:' in x and 'set by blastFoam' in x
              for x in rep.notes), str(rep.notes))
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


def _block_centres(x0, y0, size, n):
    """n x n cell centres of spacing `size` tiling the unit square whose
    lower corner is (x0, y0); x slow, y fast."""
    cx = x0 + (np.arange(n) + 0.5) * size
    cy = y0 + (np.arange(n) + 0.5) * size
    X, Y = np.meshgrid(cx, cy, indexing='ij')
    return np.column_stack([X.ravel(), Y.ravel()])


def _expect_mean(C, vals, dxd, i, j):
    """Mean of `vals` over the cells whose centre falls in display cell
    (i, j) - valid when they all share one level."""
    m = ((np.floor(C[:, 0] / dxd) == i) & (np.floor(C[:, 1] / dxd) == j))
    return vals[m].mean()


def test_amr():
    print("\ndynamic AMR: remap_from_centres, plan, validation (N16)")
    from blastlab.core.grid import make_geometry, make_grid
    # a 2 x 2 m planar domain of four 1 m base cells: one unrefined, one
    # at level 1 (4 cells), one at level 2 (16), one at level 3 (64)
    C = np.vstack([_block_centres(0, 0, 1.0, 1), _block_centres(1, 0, 0.5, 2),
                   _block_centres(0, 1, 0.25, 4), _block_centres(1, 1, 0.125, 8)])
    lv = np.r_[[0], [1] * 4, [2] * 16, [3] * 64]
    vals = np.arange(len(C), dtype=float)
    disp = make_geometry('planar', 2.0, 2.0, 0.25)       # display level 2
    mm = refine.remap_from_centres(C, lv, disp, 2)
    check('counts per level + n_cells', mm.counts == (1, 4, 16, 64) and mm.n_cells == 85,
          f'{mm.counts} {mm.n_cells}')
    check('level-0 cell covers a 4x4 display block at level 0',
          (mm.remap[0:4, 0:4] == 0).all() and (mm.levels[0:4, 0:4] == 0).all())
    check('level-1 cells cover 2x2 blocks (x slow, y fast order)',
          (mm.remap[4:6, 0:2] == 1).all() and (mm.remap[4:6, 2:4] == 2).all()
          and (mm.remap[6:8, 0:2] == 3).all() and (mm.remap[6:8, 2:4] == 4).all()
          and (mm.levels[4:8, 0:4] == 1).all(), str(mm.remap[4:8, 0:4]))
    check('level-2 cells map one-to-one',
          sorted(np.unique(mm.remap[0:4, 4:8]).tolist()) == list(range(5, 21))
          and (mm.levels[0:4, 4:8] == 2).all())
    check('cells finer than the display grid: remap -2, level capped at D',
          (mm.remap[4:8, 4:8] == -2).all() and (mm.levels[4:8, 4:8] == 2).all())
    g = mm.gather(vals)
    check('gather: direct cells', g[0, 0] == 0 and g[5, 1] == 1 and g[7, 3] == 4
          and g[0, 4] == vals[mm.remap[0, 4]])
    exp = np.array([[_expect_mean(C[21:], vals[21:], 0.25, i, j)
                     for j in range(4, 8)] for i in range(4, 8)])
    check('gather: sub-display cells are box-averaged', np.allclose(g[4:8, 4:8], exp),
          f'{g[4:8, 4:8][0]} vs {exp[0]}')
    w = np.bincount(mm.sub_idx, weights=mm.sub_w, minlength=64)
    check('sub-cell weights sum to 1 per display cell',
          np.allclose(w[mm.remap.reshape(-1) == -2], 1.0) and len(mm.sub_cells) == 64)
    try:
        refine.remap_from_centres(C[1:], lv[1:], disp, 2)
        bad = 'no error'
    except RuntimeError as exc:
        bad = str(exc)
    check('a missing cell -> RuntimeError naming the gap', 'covered 0 times' in bad, bad)
    try:
        refine.remap_from_centres(np.vstack([C, C[1:2]]), np.r_[lv, 1], disp, 2)
        bad = 'no error'
    except RuntimeError as exc:
        bad = str(exc)
    check('a duplicate cell -> RuntimeError', 'covered 2 times' in bad, bad)
    try:
        refine.remap_from_centres(C, np.r_[lv[1:], 9], disp, 2)
        bad = 'no error'
    except RuntimeError as exc:
        bad = str(exc)
    check('a wrong level -> RuntimeError', 'RuntimeError' or bad != 'no error', bad)
    solid = np.zeros((8, 8), dtype=bool)
    solid[0:4, 0:4] = True
    mm2 = refine.remap_from_centres(C[1:], lv[1:], disp, 2, solid_disp=solid)
    check('carved block: remap -1 and the fill value',
          (mm2.remap[0:4, 0:4] == -1).all()
          and (mm2.gather(np.ones(84), fill=-9.0)[0:4, 0:4] == -9.0).all()
          and mm2.gather(np.ones(84))[4:, :].min() == 1.0)
    try:
        refine.remap_from_centres(C, lv, disp, 2, solid_disp=solid)
        bad = 'no error'
    except RuntimeError as exc:
        bad = str(exc)
    check('a cell inside a carved region -> RuntimeError', 'carved' in bad, bad)
    # display level 1 (0.5 m): level 0 -> 2x2 block, level 1 one-to-one,
    # levels 2 and 3 averaged
    disp1 = make_geometry('planar', 2.0, 2.0, 0.5)
    m1 = refine.remap_from_centres(C, lv, disp1, 1)
    g1 = m1.gather(vals)
    exp1 = np.array([[_expect_mean(C[5:21], vals[5:21], 0.5, i, j) for j in (2, 3)]
                     for i in (0, 1)])
    exp3 = np.array([[_expect_mean(C[21:], vals[21:], 0.5, i, j) for j in (2, 3)]
                     for i in (2, 3)])
    check('display level 1: blocks, identity and two averaged levels',
          (m1.remap[0:2, 0:2] == 0).all()
          and m1.remap[2:4, 0:2].ravel().tolist() == [1, 2, 3, 4]
          and (m1.remap[:, 2:4] == -2).all()
          and np.allclose(g1[0:2, 2:4], exp1) and np.allclose(g1[2:4, 2:4], exp3)
          and (m1.levels[:, 2:4] == 1).all(), str(m1.remap))
    # static wrap: a match_cells-style remap becomes a MeshMap
    st = refine.MeshMap.from_remap(mm.remap[0:4, 0:4] * 0, mm.levels[0:4, 0:4], 1)
    check('MeshMap.from_remap gathers like to_grid', (st.gather(np.array([7.0])) == 7.0).all()
          and st.sub_cells is None)
    # 3D: one base cell refined to level 1 (8 cells) and to level 2 (64)
    disp3 = make_grid(1.0, 1.0, 1.0, 0.5)
    c8 = np.stack(np.meshgrid(*[(np.arange(2) + 0.5) * 0.5] * 3, indexing='ij'), -1).reshape(-1, 3)
    m8 = refine.remap_from_centres(c8, np.ones(8), disp3, 1)
    check('3D level-1 cells map one-to-one onto a 2^3 display grid',
          sorted(m8.remap.ravel().tolist()) == list(range(8)) and m8.counts == (0, 8))
    c64 = np.stack(np.meshgrid(*[(np.arange(4) + 0.5) * 0.25] * 3, indexing='ij'), -1).reshape(-1, 3)
    m64 = refine.remap_from_centres(c64, np.full(64, 2), disp3, 1)
    check('3D finer-than-display cells averaged with weight 1/8',
          (m64.remap == -2).all() and np.allclose(m64.sub_w, 0.125)
          and np.allclose(m64.gather(np.ones(64)), 1.0))
    m0 = refine.remap_from_centres(np.array([[0.5, 0.5, 0.5]]), [0], disp3, 1)
    check('3D base cell covers the whole 2^3 display block', (m0.remap == 0).all())

    # ── plan_levels / display_level_for / validate_case ──
    a = Case2D(geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.1, charge=25.0,
               center=(1.0, 1.0), solver='blastfoam', amr_levels=3)
    plan = refine.plan_levels(a)
    check('AMR plan: base dx kept, display = finest (25.6k < cap), zero level map, no zones',
          abs(plan.dx_base - 0.1) < 1e-12 and plan.amr == 3 and plan.display_level == 3
          and plan.lmax == 3 and plan.levels.shape == (160, 160) and not plan.levels.any()
          and plan.zones == [] and plan.n_pred == 400 and plan.n_fine == 160 ** 2,
          f'{plan.dx_base} {plan.display_level} {plan.levels.shape} {plan.n_pred}')
    check('plan.meta carries the amr keys', plan.meta()['amr'] == 3
          and plan.meta()['display_level'] == 3)
    a.amr_display_level = 1
    plan = refine.plan_levels(a)
    check('explicit display level 1 -> 40x40 display grid', plan.display_level == 1
          and plan.lmax == 1 and plan.levels.shape == (40, 40) and abs(plan.dx_fine - 0.05) < 1e-12)
    check('display_level_for picks the deepest level under the cap',
          refine.display_level_for((2.0, 2.0), 0.1, 4, 50_000) == 3
          and refine.display_level_for((2.0, 2.0), 0.1, 4, 10 ** 9) == 4
          and refine.display_level_for((2.0, 2.0), 0.1, 4, 100) == 0)
    # 4 AMR levels: the 8-cell foam charge target (T39) needs one more
    # level than the native 5-cell one for this 25 kg/m charge
    a.amr_levels = 4
    rep = validate_case(a)
    check('valid AMR case: no errors, AMR notes, report fields',
          not rep.errors and any('AMR (densityGradient)' in n for n in rep.notes)
          and any('displayed at level 1' in n for n in rep.notes)
          and any('may grow to 8,000,000' in n for n in rep.notes)
          and rep.amr_levels == 4 and rep.display_level == 1
          and abs(rep.dx_fine - 0.00625) < 1e-12 and rep.n_fine == 1600
          and rep.n_cells == 400 and abs(rep.effective_dx - 0.1) < 1e-12,
          f'{rep.errors} {rep.notes}')
    check('no global charge-cut note under AMR',
          not any('will be refined' in n for n in rep.notes), str(rep.notes))
    d = case_to_dict(a)
    d['amr_levels'], d['amr_display_level'] = 3.0, 1.0
    back = case_from_dict(d)
    check('v5 round trip coerces the amr ints', back.amr_levels == 3
          and isinstance(back.amr_levels, int) and back.amr_display_level == 1
          and back.amr_estimator == 'densityGradient' and d['version'] == 5)
    n = Case2D(geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.1, charge=25.0,
               center=(1.0, 1.0), solver='native', amr_levels=2)
    check('native + AMR -> error naming blastFoam',
          any('AMR' in e and 'blastFoam' in e for e in validate_case(n).errors),
          str(validate_case(n).errors))
    z = Case2D(geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.1, charge=25.0,
               center=(1.0, 1.0), solver='blastfoam', amr_levels=3,
               refine_zones=[(0.5, 1.5, 0.5, 1.5, 1)])
    check('AMR + zones -> mutually exclusive error',
          any('mutually exclusive' in e for e in validate_case(z).errors))
    z.refine_zones, z.charge_refine = [], 'zone'
    check("AMR + charge_refine='zone' -> same error",
          any('mutually exclusive' in e for e in validate_case(z).errors))
    u = Case2D(geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.1, charge=25.0,
               center=(1.0, 1.0), solver='blastfoam', amr_levels=2)
    rep = validate_case(u)
    check('too few levels for the charge -> error naming the level needed',
          any('needs AMR level 4' in e for e in rep.errors), str(rep.errors))
    for kw, frag in ((dict(amr_estimator='gradient'), 'Unknown AMR error estimator'),
                     (dict(amr_unrefine=0.5), 'unrefine threshold must not exceed'),
                     (dict(amr_refine=0.0), 'must be > 0'),
                     (dict(amr_interval=0), 'interval must be >= 1'),
                     (dict(amr_buffer=0), 'buffer layers must be >= 1'),
                     (dict(amr_display_level=5), 'display level must be 0..3'),
                     (dict(amr_levels=6), 'levels must be 1..5')):
        c = Case2D(geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.1, charge=25.0,
                   center=(1.0, 1.0), solver='blastfoam', amr_levels=3)
        for k, v in kw.items():
            setattr(c, k, v)
        rep = validate_case(c)
        check(f'{kw} -> error', any(frag in e for e in rep.errors), str(rep.errors))
    ax = Case2D(Lx=2.0, Ly=2.0, cell_size_m=0.1, charge=1.0, center=(0.0, 1.0),
                solver='blastfoam', amr_levels=4)
    rep = validate_case(ax)
    check('axisymmetric AMR -> axis warning, no error',
          not rep.errors and any('Axisymmetric AMR' in w for w in rep.warnings),
          f'{rep.errors} {rep.warnings}')
    g = Case3D(Lx=4.0, Ly=4.0, Lz=4.0, cell_size_m=0.1, charge=8.0, center=(2.0, 2.0, 2.0),
               solver='blastfoam', amr_levels=4)
    rep = validate_case(g)
    check('3D: auto display level stops under the cap (level 2 = 4.1M, warned)',
          not rep.errors and rep.display_level == 2
          and any('display grid' in w for w in rep.warnings), f'{rep.errors} {rep.warnings}')
    g.amr_display_level = 3
    rep = validate_case(g)
    check('3D: forcing display level 3 (32.8M) -> cap error with the AMR hint',
          any('lower the AMR display level' in e for e in rep.errors), str(rep.errors))
    g.amr_display_level = None
    g.amr_max_cells = 200_000_000
    check('maxCells over the blastFoam cap -> error',
          any('AMR max cells' in e for e in validate_case(g).errors))
    g.amr_max_cells = 0
    g.n_procs = 4
    # T42/N16-b: AMR runs in parallel now - the ingest reads
    # processor*/ directly instead of reconstructing
    check('AMR + MPI ranks -> the requested ranks, not a serial note',
          any('4 MPI ranks' in n for n in validate_case(g).notes)
          and not any('serially' in n for n in validate_case(g).notes),
          str(validate_case(g).notes))


def test_amr_centres():
    print("\ndynamic AMR: wedge centroids tile the display grid, levels "
          "from centres")
    from blastlab.core.grid import make_geometry

    def r_cent(i, s):
        """Volume centroid (in r) of an axisymmetric wedge cell spanning
        [i s, (i+1) s]: (2/3)((i+1)^3 - i^3)/((i+1)^2 - i^2) s - 2/3 s
        for the axis cell, not the Cartesian midpoint."""
        return (2.0 / 3.0) * (((i + 1) ** 3 - i ** 3)
                              / ((i + 1) ** 2 - i ** 2)) * s

    # four 1 m base cells of a 2 x 2 m axisymmetric domain displayed at
    # level 3 (0.125 m): the axis cell's centroid sits 2/3 of the way
    # out, which used to land its block one display cell too far
    # (rint(rel - s/2)) and fail the exact-cover check at t = 0
    C = np.array([[r_cent(i, 1.0), j + 0.5] for i in range(2)
                  for j in range(2)])
    disp = make_geometry('planar', 2.0, 2.0, 0.125)
    try:
        mm = refine.remap_from_centres(C, np.zeros(4, dtype=int), disp, 3)
        ok = (mm.remap.shape == (16, 16) and (mm.remap[0:8, 0:8] == 0).all()
              and (mm.remap[8:16, 0:8] == 2).all()
              and (mm.remap[8:16, 8:16] == 3).all())
        detail = str(mm.remap[::8, ::8].tolist())
    except RuntimeError as exc:
        ok, detail = False, str(exc)
    check('wedge base-cell centroids tile a level-3 display grid', ok,
          detail)

    Cc = np.vstack([_block_centres(0, 0, 1.0, 1), _block_centres(1, 0, 0.5, 2),
                    _block_centres(0, 1, 0.25, 4),
                    _block_centres(1, 1, 0.125, 8)])
    lvc = np.r_[[0], [1] * 4, [2] * 16, [3] * 64]
    got = refine.levels_from_centres(Cc, (0.0, 0.0), 1.0, 3)
    check('levels_from_centres recovers every level', (got == lvc).all(),
          str(got))
    noisy = Cc + np.random.default_rng(0).uniform(-5e-6, 5e-6, Cc.shape)
    check('... under the 6-significant-digit write noise',
          (refine.levels_from_centres(noisy, (0.0, 0.0), 1.0, 3)
           == lvc).all())
    check('a row no level fits (torn line) -> -1',
          refine.levels_from_centres(np.array([[0.2, 0.03]]), (0.0, 0.0),
                                     1.0, 3)[0] == -1)
    check('finest-first: a level-5 centre near a coarse half-odd is level 5',
          refine.levels_from_centres(np.array([[7.5 / 32, 7.5 / 32]]),
                                     (0.0, 0.0), 1.0, 5)[0] == 5)
    check('a grid origin away from 0 is honoured',
          (refine.levels_from_centres(Cc + 3.0, (3.0, 3.0), 1.0, 3)
           == lvc).all())


def test_plan_guards():
    """QA S1 fixes: plan_levels must refuse a degenerate or memory-blowing
    grid with a ValueError (never OOM / ZeroDivision / a nan int cast), and
    a fine grid whose axis does not divide evenly must still line its solid
    mask up with the level map (was an IndexError 641 vs 642)."""
    # a fine axis that does not divide evenly (Ly = 2 m -> 641, not 642)
    c = Case2D(geometry='planar', Lx=3.0, Ly=2.0, cell_size_m=0.05,
               charge=5.0, center=(1.0, 0.5),
               obstacles=[(1.5, 1.8, 0.0, 0.6)], solver='blastfoam',
               refine_zones=[(0.5, 1.5, 0.0, 1.0, 1)])
    plan = refine.plan_levels(c, rho0=1630.0)
    check('non-dividing fine axis: solid_fine matches the level map',
          plan.solid_fine.shape == plan.levels.shape)
    check('... and the full validate_case does not raise',
          validate_case(c).errors == [])

    def raises(case):
        try:
            refine.plan_levels(case)
            return False
        except ValueError:
            return True

    check('cell size 0 -> ValueError (not ZeroDivision)',
          raises(Case2D(cell_size_m=0.0)))
    check('cell size 1e-9 -> ValueError (not a billion-cell arange)',
          raises(Case2D(cell_size_m=1e-9)))
    check('non-finite charge -> ValueError (not a nan int cast)',
          raises(Case2D(charge=float('inf')))
          and raises(Case2D(charge=float('nan'))))
    check('default 3D case is too fine to plan -> ValueError (was 6 GB OOM)',
          raises(Case3D()))
    check('AMR display grid computed without an int64 blow-up',
          refine.plan_levels(
              Case3D(Lx=4.0, Ly=4.0, Lz=4.0, cell_size_m=0.1, charge=8.0,
                     center=(2.0, 2.0, 2.0), solver='blastfoam',
                     amr_levels=4, amr_display_level=4)).n_pred == 64_000)


def test_profile_centre_in_domain():
    """QA-06: a profile-initialised stage whose burst point is outside the
    domain must be rejected (it used to reach the backend and crash)."""
    bad = Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0, cell_size_m=0.02,
                 init_mode='profile1d', center=(0.0, 99.0),
                 profile_file_in='x.txt')
    ok_ = Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0, cell_size_m=0.02,
                 init_mode='profile1d', center=(0.0, 1.0),
                 profile_file_in='x.txt')
    check('profile burst outside domain -> error (even pending inputs)',
          any('outside the domain' in e
              for e in validate_case(bad, pending_inputs=True).errors))
    check('profile burst inside domain -> no error',
          validate_case(ok_, pending_inputs=True).errors == [])


if __name__ == '__main__':
    test_snap()
    test_plan_2d()
    test_axisym()
    test_auto_zones_3d()
    test_obstacles_and_segments()
    test_case_roundtrip_and_validation()
    test_amr()
    test_amr_centres()
    test_plan_guards()
    test_profile_centre_in_domain()
    print()
    print('REFINE: ' + ('PASS' if not FAILS else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
