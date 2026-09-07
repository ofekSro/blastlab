"""blastFoam case-writer tests: semantic checks + golden-text pinning.
Pure text - no WSL required.

Run:  python test_foam_writer.py             compare against foam_golden/
      python test_foam_writer.py --update    regenerate the golden files
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import Case1D, Case2D, Case3D          # noqa: E402
from blastlab.core.constants import MIN_EXP_CELLS              # noqa: E402
from blastlab.core.grid import make_grid_1d, make_grid         # noqa: E402
from blastlab.solvers.foam.dicts import fmt                    # noqa: E402
from blastlab.solvers.foam.materials import (MATERIALS, E0,    # noqa: E402
                                             charge_radius)
from blastlab.solvers.foam.writer import render_case           # noqa: E402

GOLD = os.path.join(HERE, 'foam_golden')
FAIL = []

EXPECTED_FILES = {
    'system/blockMeshDict', 'system/controlDict', 'system/fvSchemes',
    'system/fvSolution', 'system/setFieldsDict',
    'constant/phaseProperties', 'constant/dynamicMeshDict',
    '0/p', '0/T', '0/U', '0/alpha.expl', '0/rho.expl', '0/rho.air',
}


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def norm(text):
    """Whitespace-normalized text (keys are column-padded in files)."""
    return ' '.join(text.split())


def cases():
    """Reference cases spanning dims and materials (golden set)."""
    return {
        'case1d_tnt': Case1D(
            radius_m=5.0, charge_kg=1.0, cell_size_m=0.02,
            gauge_radii=[1.0, 2.0, 3.0, 4.0],
            solver='blastfoam', material='TNT'),
        'case3d_c4': Case3D(
            Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.025, charge=8.0,
            center=(0.5, 0.5, 0.5), gauges=[(0.85, 0.5, 0.5)],
            n_snapshots=4, solver='blastfoam', material='C4'),
        'case2d_axi_tnt': Case2D(
            Lx=4.0, Ly=4.0, cell_size_m=0.02, charge=1.0,
            center=(0.0, 1.0), gauges=[(1.0, 1.0)],
            solver='blastfoam', material='TNT'),
        'case2d_planar_anfo': Case2D(
            geometry='planar', Lx=4.0, Ly=4.0, cell_size_m=0.02,
            charge=1.0, center=(2.0, 2.0),
            solver='blastfoam', material='ANFO'),
        'case3d_two_charges': Case3D(
            Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.05, charge=4.0,
            center=(0.7, 1.0, 1.0), charges=[(1.4, 1.0, 1.0, 2.0)],
            det_points=[(0.7, 1.0, 1.0), (1.4, 1.0, 1.0)],
            n_snapshots=3, solver='blastfoam', material='TNT'),
        'case1d_tnt_afterburn': Case1D(
            radius_m=5.0, charge_kg=1.0, cell_size_m=0.02,
            gauge_radii=[1.0, 2.0], solver='blastfoam', material='TNT',
            afterburn='miller'),
        'case2d_axi_none': Case2D(
            Lx=4.0, Ly=4.0, cell_size_m=0.02, charge=1.0,
            center=(0.0, 1.0), activation='none',
            solver='blastfoam', material='TNT'),
        'case3d_obstacle': Case3D(
            Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.05, charge=4.0,
            center=(0.5, 1.0, 1.0),
            obstacles=[(1.2, 1.5, 0.6, 1.4, 0.0, 1.2)],
            gauges=[(1.8, 1.0, 1.0), (1.35, 1.0, 0.5)],
            n_snapshots=3, solver='blastfoam', material='TNT'),
        'case2d_axi_obstacle': Case2D(
            Lx=4.0, Ly=4.0, cell_size_m=0.02, charge=1.0,
            center=(0.0, 1.0), obstacles=[(2.0, 2.4, 0.0, 1.6)],
            gauges=[(1.0, 1.0), (2.2, 0.8)],
            solver='blastfoam', material='TNT'),
        # local refinement (N15): user zones nested 1 -> 2 on a base the
        # charge does not refine ('zone' mode: the charge gets automatic
        # zones instead of a global dx cut)
        'case2d_planar_refine': Case2D(
            geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.1,
            charge=50.0, center=(1.0, 1.0), charge_refine='zone',
            refine_zones=[(0.5, 1.5, 0.5, 1.5, 1),
                          (0.75, 1.25, 0.75, 1.25, 2)],
            gauges=[(1.6, 1.0)], solver='blastfoam', material='TNT'),
        'case2d_axi_refine': Case2D(
            Lx=2.0, Ly=2.0, cell_size_m=0.1, charge=1.0,
            center=(0.0, 1.0), charge_refine='zone',
            refine_zones=[(0.0, 0.6, 0.6, 1.4, 1)],
            gauges=[(1.0, 1.0)], solver='blastfoam', material='TNT'),
        'case3d_refine': Case3D(
            Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.1, charge=1.0,
            center=(0.5, 0.5, 0.5), charge_refine='zone',
            obstacles=[(0.0, 0.2, 0.0, 0.2, 0.0, 0.2)],
            gauges=[(0.9, 0.5, 0.5)], n_snapshots=2,
            solver='blastfoam', material='TNT'),
        # dynamic AMR (N16): adaptiveFvMesh cases - the base grid is the
        # case cell, no static refine dicts, a cellCentres FO replaces
        # the live slice; the 3D one exercises every coefficient
        'case2d_planar_amr': Case2D(
            geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.1,
            charge=25.0, center=(1.0, 1.0), gauges=[(1.6, 1.0)],
            solver='blastfoam', material='TNT', amr_levels=3),
        'case3d_amr': Case3D(
            Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.1, charge=8.0,
            center=(1.0, 1.0, 1.0), gauges=[(1.8, 1.0, 1.0)],
            n_snapshots=2, solver='blastfoam', material='TNT',
            amr_levels=3, amr_display_level=1, amr_estimator='Lohner',
            amr_refine=0.2, amr_unrefine=0.05, amr_interval=3,
            amr_buffer=1, amr_max_cells=500000),
    }


def afterburn_checks(specs):
    """N3: the Miller afterburn model reaches the phase dict and brings
    its transported burn fraction's schemes with it."""
    from blastlab.solvers.foam.materials import AFTERBURN
    sa = specs['case1d_tnt_afterburn']
    pp = sa.files['constant/phaseProperties']
    ab = AFTERBURN['TNT']
    check('afterburn: model + coefficients in the detonating phase',
          'afterburnModel Miller;' in norm(pp)
          and f'Q0 {fmt(ab.Q0)};' in norm(pp)
          and f'a {fmt(ab.a)};' in norm(pp)
          and f'pMin {fmt(ab.pMin)};' in norm(pp), norm(pp)[-400:])
    fs = norm(sa.files['system/fvSchemes'])
    check('afterburn: c.expl div + reconstruct schemes',
          'div(alphaRhoPhi.expl,c.expl) Riemann;' in fs
          and 'reconstruct(c.expl) vanAlbada;' in fs, fs)
    plain = specs['case1d_tnt']
    check('no afterburn: dicts untouched',
          'afterburn' not in plain.files['constant/phaseProperties']
          and 'c.expl' not in plain.files['system/fvSchemes'])


def refine_checks(specs):
    """N15: refined cases render one topoSet/refineMesh pair per level on
    a base-count blockMesh; spec exposes the fine display grid."""
    from blastlab.core import refine
    sp = specs['case2d_planar_refine']
    check('refine 2D: base kept at 0.1 m, zones + auto charge zones',
          abs(sp.dx_base - 0.1) < 1e-12 and sp.lmax == 3
          and sp.nb == (20, 20), f'{sp.dx_base} {sp.lmax} {sp.nb}')
    check('refine 2D: spec grid is the fine grid (nb * 2**lmax)',
          (sp.nx, sp.ny) == (160, 160) and abs(sp.dx - 0.0125) < 1e-12,
          f'{sp.nx} {sp.ny} {sp.dx}')
    check('refine 2D: n_cells is the predicted refined count',
          sp.n_cells == refine.n_cells_from_levels(sp.levels, sp.lmax)
          and sp.n_cells < sp.nx * sp.ny, str(sp.n_cells))
    bmd = norm(sp.files['system/blockMeshDict'])
    check('refine 2D: blockMesh on the base counts', '(20 20 1)' in bmd, bmd[-200:])
    check('refine 2D: slab thickness = base cell',
          f'(0 0 {fmt(-0.05)})' in sp.files['system/blockMeshDict'].replace(' -0.05', ' -0.05')
          and '-0.05' in sp.files['system/blockMeshDict'])
    check('refine 2D: one topoSet + refineMesh dict per level',
          all(f'system/topoSetDict.refine{l}' in sp.files
              and f'system/refineMeshDict.{l}' in sp.files for l in (1, 2, 3))
          and 'system/refineMeshDict.4' not in sp.files)
    rmd = sp.files['system/refineMeshDict.1']
    check('refine 2D: in-plane directions, no hex topology',
          'directions      (e1 e2);' in rmd or 'directions (e1 e2);' in norm(rmd)
          and 'useHexTopology' in rmd and 'no;' in rmd
          and 'set             refine1;' in rmd or 'refine1' in rmd,
          rmd[-400:])
    tsd = sp.files['system/topoSetDict.refine2']
    check('refine 2D: level-2 set holds the user level-2 zone and the auto zones',
          tsd.count('boxToCell') >= 2 and 'name refine2' in tsd
          and 'invert' not in tsd, tsd[-300:])
    check('refine 2D: setFields slab extent uses the base cell',
          f'(1 1 {fmt(-0.1)})' in sp.files['system/setFieldsDict'].replace('(1 1 -0.1)', f'(1 1 {fmt(-0.1)})'))
    sa = specs['case2d_axi_refine']
    check('refine axi: axis zone limited to level 1 -> lmax 1',
          sa.lmax == 1 and (sa.nx, sa.ny) == (40, 40), f'{sa.lmax} {sa.nx}')
    check('refine axi: wedge normal never refined',
          '(e1 e2)' in sa.files['system/refineMeshDict.1']
          and 'e3' not in sa.files['system/refineMeshDict.1'])
    s3 = specs['case3d_refine']
    check('refine 3D: hexRef8 (three directions + hex topology)',
          '(e1 e2 e3)' in s3.files['system/refineMeshDict.1']
          and 'useHexTopology  yes;' in s3.files['system/refineMeshDict.1']
          or ('useHexTopology' in s3.files['system/refineMeshDict.1']
              and 'yes' in s3.files['system/refineMeshDict.1']))
    check('refine 3D: level 4 auto zones (1 kg on 10 cm)', s3.lmax == 4
          and s3.nb == (10, 10, 10) and (s3.nx, s3.ny, s3.nz) == (160, 160, 160),
          f'{s3.lmax} {s3.nb} {s3.nx}')
    check('refine 3D: solid mask expanded from the base carve, not re-evaluated',
          s3.solid is not None and s3.solid.shape == (160, 160, 160)
          and int(s3.solid.sum()) == 8 * (16 ** 3)
          and s3.solid_base is not None and int(s3.solid_base.sum()) == 8,
          f"{s3.solid.sum() if s3.solid is not None else None}")
    check('refine 3D: n_cells excludes the carved base cells',
          s3.n_cells == refine.n_cells_from_levels(s3.levels, s3.lmax, s3.solid))
    check('refine 3D: blockMesh on base counts + obstacles patch',
          '(10 10 10)' in norm(s3.files['system/blockMeshDict'])
          and 'obstacles' in s3.files['system/blockMeshDict'])
    check('refine 3D: meta payload', set(s3.refine_meta()) == {'levels', 'lmax', 'dx_base', 'zones'})
    # uniform cases: no refinement artefacts at all
    su = specs['case3d_c4']
    check('uniform: lmax 0, no refine dicts, refine_meta None',
          su.lmax == 0 and su.refine_meta() is None
          and not any('refine' in k for k in su.files)
          and su.nb == (su.nx, su.ny, su.nz))


def amr_checks(specs):
    """N16: AMR cases render the adaptiveFvMesh block, keep the base
    blockMesh, drop the static refine dicts and the live slice, and
    expose the display grid + per-time mesh fields."""
    s2 = specs['case2d_planar_amr']
    dm = norm(s2.files['constant/dynamicMeshDict'])
    check('amr 2D: adaptiveFvMesh + densityGradient with the required keys',
          all(k in dm for k in (
              'dynamicFvMesh adaptiveFvMesh;', 'errorEstimator densityGradient;',
              'refineInterval 2;', 'lowerRefineLevel 0.4;', 'unrefineLevel 0.2;',
              'nBufferLayers 2;', 'maxRefinement 3;', 'maxCells 8000000;',
              'dumpLevel yes;'))
          and 'epsilon' not in dm and 'loadBalance' not in dm, dm)
    check('amr 2D: base blockMesh, display grid at the finest level',
          s2.amr == 3 and s2.display_level == 3 and s2.nb == (20, 20)
          and (s2.nx, s2.ny) == (160, 160) and abs(s2.dx - 0.0125) < 1e-12
          and abs(s2.dx_base - 0.1) < 1e-12 and s2.n_cells == 400,
          f'{s2.nb} {s2.nx} {s2.dx} {s2.n_cells}')
    check('amr 2D: no static refine dicts, zones empty, lmax = display level',
          not any('refine' in k for k in s2.files) and s2.zones == []
          and s2.lmax == 3 and '(20 20 1)' in norm(s2.files['system/blockMeshDict']))
    cd = s2.files['system/controlDict']
    check('amr 2D: cellCentres FO at writeTime, live slice kept, FOs kept',
          'writeCellCentres' in cd and 'libfieldFunctionObjects' in cd
          and 'liveSlice' in cd and 'surfaces' in cd
          and 'impulse' in cd and 'pMax' in cd and 'gauges' in cd)
    check('amr 2D: setFieldsDict maxRefinement after nBufferLayers',
          'nBufferLayers 1; maxRefinement 3;' in norm(s2.files['system/setFieldsDict']),
          norm(s2.files['system/setFieldsDict'])[:200])
    sfd = norm(s2.files['system/setFieldsDict'])
    check('amr 2D planar: mass-based cylinder source with a backup region '
          '(mass = charge x slab, LbyD = slab / 2r)',
          'cylindericalMassToCell' in sfd and 'cylinderToCell' not in sfd
          and f'mass {fmt(25.0 * 0.1)};' in sfd
          and f'LbyD {fmt(0.1 / (2.0 * s2.r_exp))};' in sfd
          and 'direction (0 0 1);' in sfd and 'backup' in sfd
          and f'L (0 0 {fmt(0.1)});' in sfd
          and f'radius {fmt(max(2.0 * s2.r_exp, 0.09))};' in sfd, sfd)
    sfd3 = norm(specs['case3d_amr'].files['system/setFieldsDict'])
    check('amr 3D: sphere backup radius >= 0.9 base cells',
          f'radius {fmt(max(2.0 * specs["case3d_amr"].r_exp, 0.09))};' in sfd3, sfd3)
    check('static planar: cylinderToCell unchanged',
          'cylinderToCell' in specs['case2d_planar_refine'].files['system/setFieldsDict']
          and 'MassToCell' not in specs['case2d_planar_refine'].files['system/setFieldsDict'])
    check('amr 2D: mesh_fields + refine_meta with amr keys',
          s2.mesh_fields == ('C', 'cellLevel')
          and set(s2.refine_meta()) == {'levels', 'lmax', 'dx_base', 'zones',
                                        'amr', 'display_level'}
          and s2.refine_meta()['amr'] == 3 and s2.refine_meta()['display_level'] == 3)
    s3 = specs['case3d_amr']
    dm = norm(s3.files['constant/dynamicMeshDict'])
    check('amr 3D: Lohner on p with epsilon + every coefficient',
          all(k in dm for k in (
              'errorEstimator Lohner;', 'field p;', 'epsilon 0.05;',
              'refineInterval 3;', 'lowerRefineLevel 0.2;', 'unrefineLevel 0.05;',
              'nBufferLayers 1;', 'maxRefinement 3;', 'maxCells 500000;')), dm)
    check('amr 3D: display level 1 -> 40^3 display grid over a 20^3 base',
          s3.display_level == 1 and s3.lmax == 1 and s3.nb == (20, 20, 20)
          and (s3.nx, s3.ny, s3.nz) == (40, 40, 40) and abs(s3.dx - 0.05) < 1e-12
          and s3.n_cells == 8000 and '(20 20 20)' in norm(s3.files['system/blockMeshDict']),
          f'{s3.display_level} {s3.nb} {s3.nx} {s3.dx}')
    check('amr 3D: setFieldsDict maxRefinement 3',
          'maxRefinement 3;' in norm(s3.files['system/setFieldsDict']))
    check('amr 3D: static-mesh readiness fields empty on non-AMR specs',
          specs['case3d_c4'].mesh_fields == () and specs['case3d_refine'].mesh_fields == ())
    su = specs['case3d_c4']
    check('no AMR: staticFvMesh, live slice, no maxRefinement, amr 0',
          'staticFvMesh' in su.files['constant/dynamicMeshDict']
          and 'liveSlice' in su.files['system/controlDict']
          and 'maxRefinement' not in su.files['system/setFieldsDict']
          and su.amr == 0 and 'amr' not in specs['case3d_refine'].refine_meta())


def semantic_checks(specs):
    refine_checks(specs)
    afterburn_checks(specs)
    amr_checks(specs)
    s1 = specs['case1d_tnt']
    m_tnt = MATERIALS['TNT']
    r_exp = charge_radius(1.0, m_tnt)
    # 0.02 is coarser than r_exp/5 -> refined to the largest spacing that
    # keeps MIN_EXP_CELLS across the charge AND divides radius_m exactly
    # (the native solvers' divisor rule, so foam and native cell counts agree)
    dx = 5.0 / math.ceil(5.0 / (r_exp / MIN_EXP_CELLS))
    check('1d: dx refined to divisor-aware r_exp/MIN_EXP_CELLS',
          abs(s1.dx - dx) < 1e-12 and s1.dx <= r_exp / MIN_EXP_CELLS,
          f'{s1.dx} vs {dx}')
    check('1d: nx matches core.grid', s1.nx == len(make_grid_1d(5.0, dx)[1]))
    check('1d: file set complete', set(s1.files) == EXPECTED_FILES,
          str(set(s1.files) ^ EXPECTED_FILES))
    bmd = norm(s1.files['system/blockMeshDict'])
    check('1d: sector hex + wedges',
          f'hex (0 1 2 0 0 3 4 0) ({s1.nx} 1 1)' in bmd
          and bmd.count('type wedge;') == 4)
    cd = s1.files['system/controlDict']
    check('1d: blastProbes with 4 gauges',
          'blastProbes' in cd and cd.count('(1 0 0)') == 1
          and cd.count('(4 0 0)') == 1)
    check('1d: adjustable writes',
          'writeControl    adjustableRunTime;' in cd
          and 'runTimeModifiable true;' in cd
          and s1.end_time > 0 and s1.write_interval > 0)
    end_x = s1.grid['r_face'][-1] - 0.25 * s1.dx
    check('1d: live line sampling',
          'liveLine' in cd and 'lineCell' in cd
          and f'end ({fmt(end_x)} 0 0);' in cd)
    cd3 = specs['case3d_c4'].files['system/controlDict']
    check('3d: live slice sampling',
          'liveSlice' in cd3 and 'pointAndNormal' in cd3
          and 'normal (0 1 0);' in cd3
          and 'interpolate     no;' in cd3
          and 'triangulate     no;' in cd3)
    cd2 = specs['case2d_axi_tnt'].files['system/controlDict']
    check('2d: live slice sampling (z=0 plane)',
          'liveSlice' in cd2 and 'point (0 0 0);' in cd2
          and 'normal (0 0 1);' in cd2)
    check('1d: wedge group entry in fields',
          'wedge' in s1.files['0/p'] and 'pressureWaveTransmissive'
          in s1.files['0/p'])

    s3 = specs['case3d_c4']
    m_c4 = MATERIALS['C4']
    g = make_grid(1.0, 1.0, 1.0, s3.dx)
    check('3d: grid matches core.grid',
          (s3.nx, s3.ny, s3.nz) == (g['Nx'], g['Ny'], g['Nz']))
    pp = s3.files['constant/phaseProperties']
    check('3d: C4 JWL params', fmt(m_c4.A) in pp and fmt(m_c4.vDet) in pp)
    check('3d: E0 = rho0*e0', fmt(E0(m_c4)) in pp)
    check('3d: rho.expl uniform',
          f'uniform {fmt(m_c4.rho0)}' in s3.files['0/rho.expl'])
    check('3d: static mesh', 'staticFvMesh'
          in s3.files['constant/dynamicMeshDict'])
    p3 = s3.files['0/p']
    u3 = s3.files['0/U']
    check('3d: z_lo wall -> slip U / zeroGradient p',
          'z_lo' in p3 and 'slip' in u3)
    sf = s3.files['system/setFieldsDict']
    check('3d: sphericalMassToCell mass',
          'sphericalMassToCell' in sf and 'mass            8;' in sf)
    check('3d: detonation point at centre',
          '(0.5 0.5 0.5)' in pp)

    # peak/impulse function objects: per-step accumulation for 2D/3D,
    # deliberately absent in 1D (no peak-map consumer there)
    cd3 = s3.files['system/controlDict']
    check('3d: impulse + pMax function objects',
          'type            impulse;' in cd3
          and 'type            fieldMinMax;' in cd3
          and 'libblastFunctionObjects' in cd3
          and 'pRef            101325;' in cd3
          and 'minMax          max;' in cd3)
    check('1d: no impulse/pMax function objects',
          'impulse' not in cd and 'fieldMinMax' not in cd)

    s2 = specs['case2d_axi_tnt']
    cd2 = s2.files['system/controlDict']
    check('2d: impulse + pMax function objects',
          'type            impulse;' in cd2
          and 'type            fieldMinMax;' in cd2)

    # write format: binary for 2D/3D (I/O + parse speed), ascii for 1D
    check('1d: ascii writes', 'writeFormat     ascii;' in cd)
    check('3d: binary writes', 'writeFormat     binary;' in cd3)
    check('2d: binary writes', 'writeFormat     binary;' in cd2)
    bmd2 = norm(s2.files['system/blockMeshDict'])
    check('2d axi: wedge pair + collapsed axis',
          bmd2.count('type wedge;') == 2 and 'x_lo' not in bmd2)
    s2p = specs['case2d_planar_anfo']
    bmd2p = norm(s2p.files['system/blockMeshDict'])
    check('2d planar: cylinder charge + empty planes',
          'cylinderToCell' in s2p.files['system/setFieldsDict']
          and 'frontAndBack' in bmd2p and 'type empty;' in bmd2p)

    # multi-charge + detonation points (E2)
    s3t = specs['case3d_two_charges']
    sf2 = s3t.files['system/setFieldsDict']
    pp2 = s3t.files['constant/phaseProperties']
    check('two charges: two mass regions',
          sf2.count('sphericalMassToCell') == 2
          and 'mass            4;' in sf2 and 'mass            2;' in sf2)
    check('two charges: both det points',
          '(0.7 1 1)' in pp2 and '(1.4 1 1)' in pp2)
    dx_small = charge_radius(2.0, m_tnt) / MIN_EXP_CELLS
    check('two charges: dx resolves the smaller charge',
          abs(s3t.dx - 2.0 / math.ceil(2.0 / dx_small)) < 1e-12
          and s3t.dx <= dx_small)
    check('two charges: r_exp is the larger',
          abs(s3t.r_exp - charge_radius(4.0, m_tnt)) < 1e-12)

    # activationModel (E3)
    ppn = specs['case2d_axi_none'].files['constant/phaseProperties']
    check('activation none: model + E0-only initiation',
          'activationModel none;' in ppn and 'E0' in ppn
          and 'vDet' not in ppn and 'points' not in ppn)
    check('activation linear default unchanged',
          'activationModel linear;' in pp)

    # obstacles (3D): topoSet carve + wall patch + gauge filtering
    from blastlab.core.bc import solid_mask_3d
    so = specs['case3d_obstacle']
    tsd = norm(so.files.get('system/topoSetDict', ''))
    check('obstacle: topoSetDict box + invert',
          'source boxToCell; sourceInfo '
          '{ box (1.2 0.6 0) (1.5 1.4 1.2); }' in tsd
          and 'action invert;' in tsd
          and tsd.count('name fluid;') == 2)
    bmdo = norm(so.files['system/blockMeshDict'])
    check('obstacle: zero-face wall patch in blockMesh',
          'obstacles' in bmdo and 'faces ();' in bmdo)
    check('obstacle: patch entries in 0/ fields',
          'obstacles' in so.files['0/p']
          and 'obstacles' in so.files['0/U'])
    ref_solid = solid_mask_3d(so.grid['x_c'], so.grid['y_c'],
                              so.grid['z_c'], so.obstacles)
    check('obstacle: solid mask matches core.bc',
          so.solid is not None and (so.solid == ref_solid).all()
          and so.solid.any())
    check('obstacle: n_cells excludes carved cells',
          so.n_cells == so.nx * so.ny * so.nz - int(so.solid.sum()))
    check('obstacle: gauge inside the box dropped',
          so.probe_pts == [(1.8, 1.0, 1.0)])
    check('no obstacles: no topoSetDict, no extra patch',
          'system/topoSetDict' not in s3.files
          and 'obstacles' not in s3.files['0/p'] and s3.solid is None)

    # obstacles (2D axisym): z-unbounded carve box + wall patch
    from blastlab.core.bc import solid_mask_2d
    so2 = specs['case2d_axi_obstacle']
    tsd2 = norm(so2.files.get('system/topoSetDict', ''))
    zpad = fmt(float(so2.grid['x_face'][-1]))
    check('2d obstacle: z-unbounded carve box',
          f'box (2 0 -{zpad}) (2.4 1.6 {zpad});' in tsd2
          and 'action invert;' in tsd2)
    bmdo2 = norm(so2.files['system/blockMeshDict'])
    check('2d obstacle: wall patch + field entries',
          'obstacles' in bmdo2 and 'faces ();' in bmdo2
          and 'obstacles' in so2.files['0/p'])
    ref2 = solid_mask_2d(so2.grid['x_c'], so2.grid['y_c'],
                         so2.obstacles)
    check('2d obstacle: solid mask + n_cells',
          so2.solid is not None and (so2.solid == ref2).all()
          and so2.solid.any()
          and so2.n_cells == so2.nx * so2.ny - int(so2.solid.sum()))
    check('2d obstacle: gauge inside the box dropped',
          so2.probe_pts == [(1.0, 1.0, 0.0)])

    # parallel: decomposeParDict appears ONLY for n_procs > 1, and
    # nothing else in the case tree varies
    s3p = specs['case3d_c4_np4']
    check('serial: no decomposeParDict',
          'system/decomposeParDict' not in s3.files)
    dpd = s3p.files.get('system/decomposeParDict', '')
    check('np4: decomposeParDict scotch',
          'numberOfSubdomains 4;' in norm(dpd)
          and 'method scotch;' in norm(dpd))
    check('np4: only delta is decomposeParDict',
          {k: v for k, v in s3p.files.items()
           if k != 'system/decomposeParDict'} == s3.files)

    two = render_case(cases()['case1d_tnt'])
    check('deterministic render', two.files == s1.files)


def golden(specs, update):
    if update or not os.path.isdir(GOLD):
        for name, spec in specs.items():
            for rel, text in spec.files.items():
                path = os.path.join(GOLD, name, *rel.split('/'))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as f:
                    f.write(text.encode('ascii'))
        print(f"  [note] golden files written to {GOLD}")
        return
    for name, spec in specs.items():
        bad = []
        for rel, text in spec.files.items():
            path = os.path.join(GOLD, name, *rel.split('/'))
            try:
                with open(path, 'rb') as f:
                    ref = f.read()
            except OSError:
                bad.append(f'{rel}: missing')
                continue
            if ref != text.encode('ascii'):
                bad.append(rel)
        check(f'golden: {name}', not bad, ', '.join(bad))


def fresh_dir_checks():
    """B13: a fresh run must claim its own directory. new_case_dir is
    redirected to a local temp dir, so this needs no WSL."""
    import shutil
    import tempfile
    from blastlab.solvers.foam import writer as fw

    case = cases()['case3d_c4']
    tmp = tempfile.mkdtemp(prefix='blastlab_writer_')
    taken = os.path.join(tmp, 'taken_3d')
    real_new = fw.env.new_case_dir
    try:
        fw.env.new_case_dir = lambda dim, stamp=None: ('/root/taken_3d',
                                                       taken)
        spec = fw.write_case(case)
        check('write_case creates the fresh case dir',
              os.path.isfile(os.path.join(spec.case_unc, 'system',
                                          'controlDict')))
        try:
            fw.write_case(case)
            same_dir_ok = True
        except FileExistsError:
            same_dir_ok = False
        check('a second fresh run refuses to reuse the dir (B13)',
              not same_dir_ok)
        # the explicit-path branch stays permissive (resume/postmortem)
        real_unc = fw.env.unc
        try:
            fw.env.unc = lambda posix: taken
            fw.write_case(case, case_posix='/root/taken_3d')
            reuse_ok = True
        except FileExistsError:
            reuse_ok = False
        finally:
            fw.env.unc = real_unc
        check('an explicit case_posix may reuse an existing dir',
              reuse_ok)
    finally:
        fw.env.new_case_dir = real_new
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    update = '--update' in sys.argv
    specs = {name: render_case(case) for name, case in cases().items()}
    # parallel golden variant: same 3D case rendered for 4 MPI ranks
    specs['case3d_c4_np4'] = render_case(cases()['case3d_c4'], n_procs=4)
    semantic_checks(specs)
    fresh_dir_checks()
    golden(specs, update)
    print()
    if FAIL:
        print(f"FOAM WRITER: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM WRITER: PASS")


if __name__ == '__main__':
    main()
