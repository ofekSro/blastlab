"""blastFoam case-writer tests: semantic checks + golden-text pinning.
Pure text - no WSL required.

Run:  python test_foam_writer.py             compare against foam_golden/
      python test_foam_writer.py --update    regenerate the golden files
"""

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import Case1D, Case2D, Case3D          # noqa: E402
from blastlab.core.constants import (FOAM_EXP_CELLS,          # noqa: E402
                                     GAMMA_AIR)
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


#: 1D profile committed under foam_fixtures/ so the profile-initialised
#: golden case (N7) renders from a fixed input on every machine
PROFILE_1D = os.path.join(HERE, 'foam_fixtures', 'profile1d_chain.txt')
#: the same, but exported by a blastFoam stage - so its products are
#: JWL, not ideal gas. Pins B1/B2: the hand-off has to be priced with
#: the EOS the SOURCE ran with (this header) and the case material's
#: own JWL constants, never with case.eos (forced to 'idealGas' for
#: every blastFoam case) or the TNT default.
PROFILE_1D_JWL = os.path.join(HERE, 'foam_fixtures',
                              'profile1d_chain_jwl.txt')


def cases():
    """Reference cases spanning dims and materials (golden set)."""
    return {
        # N7: a chain stage fed by a 1D profile - no charge sphere, the
        # remapped state is written straight into 0/
        'case2d_axi_profile': Case2D(
            Lx=1.0, Ly=2.0, cell_size_m=0.05, center=(0.0, 1.0),
            init_mode='profile1d', profile_file_in=PROFILE_1D,
            gauges=[(0.8, 1.0)], n_snapshots=1, eos='idealGas',
            solver='blastfoam', material='TNT'),
        # T70: the same stage with dynamic AMR - the state lands on the
        # BASE mesh (which is what blockMesh builds at t0) and the run
        # time refiner takes it from there
        'case2d_axi_profile_amr': Case2D(
            Lx=1.0, Ly=2.0, cell_size_m=0.05, center=(0.0, 1.0),
            init_mode='profile1d', profile_file_in=PROFILE_1D,
            gauges=[(0.8, 1.0)], n_snapshots=1, eos='idealGas',
            solver='blastfoam', material='TNT', amr_levels=2),
        # B1/B2: a foam->foam hand-off. Same geometry as
        # case2d_axi_profile, but the profile carries JWL products.
        'case2d_axi_profile_jwl': Case2D(
            Lx=1.0, Ly=2.0, cell_size_m=0.05, center=(0.0, 1.0),
            init_mode='profile1d', profile_file_in=PROFILE_1D_JWL,
            gauges=[(0.8, 1.0)], n_snapshots=1, eos='idealGas',
            solver='blastfoam', material='TNT'),
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
        # N5-8: this configuration is REFUSED by validate_case ("only
        # level 1 is possible on the axis, so the charge needs a base
        # cell of at most 0.0125 m"), so no user can run it. It stays a
        # golden on purpose: what it pins is the refinement PLANNER's
        # axis constraint (lmax 1, wedge normal never refined), which
        # has to be right regardless of whether this particular case
        # would also fail a later charge-resolution check.
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
    # lmax 4, not 3: the automatic charge zones target FOAM_EXP_CELLS = 8
    # cells across r_exp for blastFoam (T39), one level deeper than the
    # native 5-cell rule this case used to plan for.
    check('refine 2D: base kept at 0.1 m, zones + auto charge zones',
          abs(sp.dx_base - 0.1) < 1e-12 and sp.lmax == 4
          and sp.nb == (20, 20), f'{sp.dx_base} {sp.lmax} {sp.nb}')
    check('refine 2D: spec grid is the fine grid (nb * 2**lmax)',
          (sp.nx, sp.ny) == (320, 320) and abs(sp.dx - 0.00625) < 1e-12,
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
              and f'system/refineMeshDict.{l}' in sp.files for l in (1, 2, 3, 4))
          and 'system/refineMeshDict.5' not in sp.files)
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
    # P1-6 (2026-09-20): the DEFAULT estimator is Lohner now - the golden
    # tracks what an untouched case gets, so it carries field/epsilon.
    check('amr 2D: adaptiveFvMesh + the Lohner default with its keys',
          all(k in dm for k in (
              'dynamicFvMesh adaptiveFvMesh;', 'errorEstimator Lohner;',
              'field p;', 'epsilon 0.05;',
              # re-tuned 2026-09-10, see Case2D.amr_refine
              'refineInterval 2;', 'lowerRefineLevel 0.2;', 'unrefineLevel 0.1;',
              'nBufferLayers 2;', 'maxRefinement 3;', 'maxCells 8000000;',
              'dumpLevel yes;'))
          and 'loadBalance' not in dm, dm)
    # the other estimator stays reachable by explicit choice, and its
    # dict must NOT drag the Lohner-only keys along
    import dataclasses
    dg = render_case(dataclasses.replace(
        cases()['case2d_planar_amr'], amr_estimator='densityGradient'))
    dmg = norm(dg.files['constant/dynamicMeshDict'])
    check('amr 2D: explicit densityGradient honoured, no Lohner keys',
          'errorEstimator densityGradient;' in dmg
          and 'epsilon' not in dmg and 'field p;' not in dmg, dmg)
    # parallel AMR: balancing on, and it MUST be paired with the
    # addEmptyPatch stage or blastFoam refuses to start (fvMeshBalance.C:112)
    dmp = norm(specs['case2d_planar_amr_np4'].files[
        'constant/dynamicMeshDict'])
    # N5-13: the two loadBalance knobs and the unrefinement hold
    from blastlab.solvers.foam.writer import _unrefine_hold
    from blastlab.solvers.foam.materials import MATERIALS
    a3 = specs['case3d_amr']
    dm3 = norm(a3.files['constant/dynamicMeshDict'])
    hold = _unrefine_hold(a3)
    check('N5-13: a charge AMR case holds unrefinement past ignition',
          'beginUnrefine' in dm3 and hold > 0.0, f'{hold:g}')
    check('N5-13: the hold is delay + charge crossing at vDet',
          abs(hold - a3.r_exp / MATERIALS[a3.material].vDet) < 1e-12,
          f'{hold:g} vs {a3.r_exp / MATERIALS[a3.material].vDet:g}')
    pa = specs['case2d_axi_profile_amr']
    check('N5-13: a profile AMR stage does NOT hold (nothing to ignite)',
          'beginUnrefine' not in
          norm(pa.files['constant/dynamicMeshDict'])
          and _unrefine_hold(pa) == 0.0)
    dmp = norm(specs['case2d_planar_amr_np4']
               .files['constant/dynamicMeshDict'])
    check('N5-13: parallel AMR names both balance knobs',
          'balanceInterval 5;' in dmp
          and 'allowableImbalance 0.2;' in dmp, dmp[-200:])
    check('N5-13: serial AMR emits no loadBalance at all',
          'loadBalance' not in dm3, dm3[-120:])

    check('amr 2D np4: loadBalance is on for a parallel AMR run',
          'loadBalance' in dmp and 'balance yes;' in dmp, dmp)
    from blastlab.solvers.foam import backend as _be
    _stages = [c for _l, c in _be._mesh_stages(
        specs['case2d_planar_amr_np4'], None) if isinstance(c, str)]
    check('amr 2D np4: addEmptyPatch runs, and before decomposePar',
          any('addEmptyPatch' in c for c in _stages)
          and next(i for i, c in enumerate(_stages) if 'addEmptyPatch' in c)
          < next(i for i, c in enumerate(_stages) if 'decomposePar' in c),
          str(_stages))
    _ser = [c for _l, c in _be._mesh_stages(s2, None) if isinstance(c, str)]
    check('amr 2D serial: no addEmptyPatch (nothing to balance)',
          not any('addEmptyPatch' in c for c in _ser), str(_ser))
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
    # 0.02 is coarser than r_exp/8 -> refined to the largest spacing that
    # keeps FOAM_EXP_CELLS across the charge AND divides radius_m exactly
    # (the native divisor rule; blastFoam asks for 8 cells, not the
    # native 5, because setFields deposits only the staircase mass - T39)
    dx = 5.0 / math.ceil(5.0 / (r_exp / FOAM_EXP_CELLS))
    check('1d: dx refined to divisor-aware r_exp/FOAM_EXP_CELLS',
          abs(s1.dx - dx) < 1e-12 and s1.dx <= r_exp / FOAM_EXP_CELLS,
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
    # T62/writeTimeList: writeInterval is transit-sized, so endTime is
    # not a write multiple - this FO is the only guarantee the run
    # writes at the exact end time, which is the chain's hand-off
    # surface. Its one entry must equal controlDict's own endTime.
    from blastlab.solvers.foam.dicts import fmt as _fmt
    check('1d: writeTimeList pins the exact end time',
          'writeTimeList' in cd
          and f'times ({_fmt(s1.t_start + s1.end_time)});' in cd
          and f'endTime         {_fmt(s1.t_start + s1.end_time)};' in cd)
    cdp = specs['case2d_axi_profile'].files['system/controlDict']
    sp_ = specs['case2d_axi_profile']
    check('chain stage: writeTimeList pins t_start + end_time',
          f'times ({_fmt(sp_.t_start + sp_.end_time)});' in cdp
          and sp_.t_start > 0)
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
    dx_small = charge_radius(2.0, m_tnt) / FOAM_EXP_CELLS
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
    # the box is SNAPPED outward to base-cell faces (dx_base = 2/192 m):
    # 1.2/dx = 115.2 -> 115 (1.197916667), 0.6/dx = 57.6 -> 57 (0.59375),
    # 1.4/dx = 134.4 -> 135 (1.40625), 1.2/dx = 115.2 -> 116
    # (1.208333333); 1.5 and 0 are exact multiples and stay
    check('obstacle: topoSetDict box + invert',
          'source boxToCell; sourceInfo '
          '{ box (1.197916667 0.59375 0) (1.5 1.40625 1.208333333); }'
          in tsd
          and 'action invert;' in tsd
          and tsd.count('name fluid;') == 2)
    check('obstacle: snap recorded for the run log',
          [tuple(b) for b, _s in so.obstacles_moved]
          == [(1.2, 1.5, 0.6, 1.4, 0.0, 1.2)])
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
    # snapped outward to base faces (dx_base = 4/608 m): 2.4/dx = 364.8
    # -> 365 (2.401315789), 1.6/dx = 243.2 -> 244 (1.605263158); 2.0 and
    # 0 are exact multiples (304, 0) and stay put
    check('2d obstacle: z-unbounded carve box',
          f'box (2 0 -{zpad}) (2.401315789 1.605263158 {zpad});' in tsd2
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
    # N5-7: scotch. A planar split plus a detonation-point nudge was
    # tried and reverted - it fixed parallel consistency but moved
    # SERIAL impulse by 3.7 %, with nothing in the suite anchoring
    # impulse to say which answer is right. See TODO.md N5-7.
    check('np4: decomposeParDict scotch',
          'numberOfSubdomains 4;' in norm(dpd)
          and 'method scotch;' in norm(dpd))
    check('np4: only delta is decomposeParDict',
          {k: v for k, v in s3p.files.items()
           if k != 'system/decomposeParDict'} == s3.files)

    two = render_case(cases()['case1d_tnt'])
    check('deterministic render', two.files == s1.files)


def parallel_1d_checks(specs):
    """P1-25 (B1, D3): the 1D tree for 4 MPI ranks is the serial tree plus
    system/decomposeParDict and nothing else, byte for byte. Pinned here
    rather than as a foam_golden/ fixture, before 1D takes ranks at all."""
    s1 = specs['case1d_tnt']
    s1p = render_case(cases()['case1d_tnt'], n_procs=4)
    check('1D np4: file set is the serial set plus decomposeParDict',
          set(s1p.files) == set(s1.files) | {'system/decomposeParDict'},
          sorted(set(s1p.files) ^ set(s1.files)))
    dpd = norm(s1p.files.get('system/decomposeParDict', ''))
    check('1D np4: decomposeParDict scotch, 4 subdomains',
          'numberOfSubdomains 4;' in dpd and 'method scotch;' in dpd, dpd)
    check('1D np4: every other file equals the serial render byte for byte',
          {k: v for k, v in s1p.files.items()
           if k != 'system/decomposeParDict'} == s1.files)

    # B2: the mesh stages decompose last (after setRefinedFields), and the
    # banner names the ranks only when there is more than one (D2)
    from blastlab.solvers.foam import backend as _be
    cmds = [c for _l, c in _be._mesh_stages(s1p, None) if isinstance(c, str)]
    ser = [c for _l, c in _be._mesh_stages(s1, None) if isinstance(c, str)]
    check('1D np4: setRefinedFields, then decomposePar -force last',
          cmds[-1] == 'decomposePar -force'
          and any('setRefinedFields' in c for c in cmds[:-1])
          and cmds[:-1] == ser, str(cmds))

    class _Log:
        def __init__(self):
            self.lines = []

        def log(self, line):
            self.lines.append(line)

    case = cases()['case1d_tnt']
    b1, b4 = _Log(), _Log()
    _be._log_banner_1d(b1, case, s1)
    _be._log_banner_1d(b4, case, s1p)
    check('1D banner: serial names no ranks',
          not any('MPI' in ln for ln in b1.lines))
    check('1D banner: np4 adds one MPI-ranks line naming 4, nothing else',
          [ln for ln in b4.lines if ln not in b1.lines]
          == ['  MPI ranks       : 4'] and len(b4.lines) == len(b1.lines) + 1,
          str(b4.lines))


def chain_eos_checks(specs):
    """B0/B1/B2: what a profile-initialised stage hands blastFoam.

    B0 - lambda.<phase> must be written, or blastFoam blends the
    products back to the unreacted Murnaghan reactants and resets the
    whole fireball to pRef (measured: 4.43 MPa in, 101,298 Pa out).
    B1 - the pressure must be priced with the SOURCE profile's EOS.
    B2 - with the case material's JWL constants, not the TNT default.
    """
    from blastlab.core import profiles
    from blastlab.core.eos import material_jwl, jwl_pressure

    for name in ('case2d_axi_profile', 'case2d_axi_profile_jwl',
                 'case2d_axi_profile_amr'):
        sp = specs[name]
        rel = f'{sp.start_dir}/lambda.{sp.phase}'
        txt = sp.files.get(rel, '')
        check(f'B0: {name} writes {rel}', bool(txt), 'missing')
        check(f'B0: {name} lambda is fully reacted',
              'internalField uniform 1;' in norm(txt), norm(txt)[:120])
        check(f'B0: {name} lambda is dimensionless',
              'dimensions [0 0 0 0 0 0 0];' in norm(txt))
        check(f'B0: {name} defers lambda past the mesh stages',
              rel in sp.deferred)
        # activation stays `linear`: with lambda already at 1 it is a
        # no-op, while `none` re-injects E0 and multiplies p by 8.3
        pp = norm(sp.files['constant/phaseProperties'])
        check(f'B0: {name} keeps activationModel linear',
              'activationModel linear;' in pp)

    # B1/B2 as an ENERGY round trip, which is what the guide's 5.9
    # actually does with the field: blastFoam inverts the EOS to get e
    # back out of the p we wrote. The bug injected +33.3 % of e into
    # every product cell (the ratio (gamma_air - 1) / omega_TNT).
    for name, eos in (('case2d_axi_profile_jwl', 'JWL'),
                      ('case2d_axi_profile', 'idealGas')):
        sp = specs[name]
        st = sp.init_state
        check(f'B1: {name} init_state carries the source EOS',
              st.get('eos') == eos, str(st.get('eos')))
        _kind, p = _parse_internal(sp.files[f'{sp.start_dir}/p'])
        phase = st['phase'].ravel(order='F')
        rho = st['rho'].ravel(order='F')
        e_ref = st['e'].ravel(order='F')
        prod = phase > 0.5
        check(f'B1: {name} has product cells to judge', bool(prod.any()))
        if eos == 'JWL':
            j = material_jwl(sp.material)
            # jwl_pressure is linear in e: p = p_cold(rho) + omega rho e
            p_cold = jwl_pressure(rho[prod], np.zeros_like(rho[prod]), j)
            e_back = (p[prod] - p_cold) / (j['omega'] * rho[prod])
        else:
            e_back = p[prod] / ((GAMMA_AIR - 1.0) * rho[prod])
        d = float(np.max(np.abs(e_back / e_ref[prod] - 1.0)))
        check(f'B1: {name} product energy survives the hand-off',
              d < 1e-9, f'max rel {d:.3e}')
        # air cells were always ideal gas - a guard that the fix did
        # not over-reach into them
        air = ~prod
        if air.any():
            e_air = p[air] / ((GAMMA_AIR - 1.0) * rho[air])
            da = float(np.max(np.abs(e_air / e_ref[air] - 1.0)))
            check(f'B1: {name} air energy survives the hand-off',
                  da < 1e-9, f'max rel {da:.3e}')

    # N5-5: the energy the hand-off carries onto this mesh, which the
    # conservedQuantities FO is compared against at the first write.
    # Recomputed here through core.grid.make_geometry (a different route
    # to the cell volumes than writer._init_cell_volumes takes) so the
    # WEDGE CONVENTION is pinned by something independent: make_geometry
    # returns V per radian, the blockMesh wedge spans 2 degrees.
    from blastlab.core.grid import make_geometry
    for name in ('case2d_axi_profile', 'case2d_axi_profile_jwl'):
        sp = specs[name]
        st = sp.init_state
        g = make_geometry('axisymmetric', sp.grid['x_face'][-1],
                          sp.grid['y_face'][-1], sp.dx)
        V = np.broadcast_to(g['V'], (sp.nx, sp.ny)) * np.radians(2.0)
        ke = 0.5 * (st['u'] ** 2 + st['v'] ** 2)
        want = float(np.sum(st['rho'] * (st['e'] + ke) * V))
        got = st.get('E_total')
        check(f'N5-5: {name} carries its total energy',
              got is not None and abs(got / want - 1.0) < 1e-12,
              f'{got!r} vs {want:.6e}')
        # and it must be a real number, not an artefact: a domain of
        # ambient air alone is the floor it has to clear
        from blastlab.core.constants import RHO_AIR, E_AIR
        floor = float(np.sum(RHO_AIR * E_AIR * V))
        check(f'N5-5: {name} exceeds an ambient-air domain',
              got > floor, f'{got:.4e} vs ambient {floor:.4e}')

    # B2: TNT and C4 must not price the same state the same way - the
    # old call took pressure_soundspeed's TNT default for every
    # material, a silent 20 % on C4 (omega 0.30 vs 0.25)
    pr = profiles.load_profile(PROFILE_1D_JWL)
    prod = pr['phase'] > 0.5
    p_tnt = jwl_pressure(pr['rho'][prod], pr['e'][prod], material_jwl('TNT'))
    p_c4 = jwl_pressure(pr['rho'][prod], pr['e'][prod], material_jwl('C4'))
    spread = float(np.max(np.abs(p_c4 / p_tnt - 1.0)))
    check('B2: the material JWL set actually changes the pressure',
          spread > 0.1, f'max rel {spread:.3f}')


def charge_scale_checks(specs):
    """N5-2: setFields marks WHOLE cells, so what a charge source
    deposits is the staircase volume x rho0 - measured across the
    golden cases anywhere from 0.98 to 1.28 of the request, depending
    on where the centre falls between cell centres and how many cells
    span the radius. Every mass-based source now carries the `scale`
    that cancels what CAN be cancelled: massToCell.C multiplies the
    requested VOLUME by it before deriving the radius, so alpha stays 1
    and rho stays rho0.

    The staircase is a step function, so the contract is not "exact" -
    it is "the best plateau available", and never worse than the
    uncorrected source. A charge resolved by one cell (a refine-zone
    case) has a single plateau and nothing to choose from; a charge
    centred on a cell corner has coarse, highly symmetric steps.
    """
    import re
    from blastlab.core.refine import _charge_cells, _staircase
    from blastlab.solvers.foam.materials import MATERIALS
    from blastlab.solvers.foam.writer import charge_radius

    def geometry_of(sp, case, centre):
        if sp.dim == 1:
            return '', (0.0, 0.0), (float(sp.grid['r_face'][-1]),)
        if sp.dim == 2:
            geo = getattr(case, 'geometry', '')
            dims = tuple(float(sp.grid[q][-1]) for q in ('x_face', 'y_face'))
            cen = (0.0 if geo == 'axisymmetric' else float(centre[0]),
                   float(centre[1]))
            return geo, cen, dims
        dims = tuple(float(sp.grid[q][-1])
                     for q in ('x_face', 'y_face', 'z_face'))
        return '', tuple(float(v) for v in centre[:3]), dims

    def best_plateau(dim, geo, dx, r, cen, dims, target):
        """Smallest achievable |V/target - 1| over every plateau."""
        d, v = _charge_cells(dim, geo, dx, 1.5 * r, cen, dims)
        if d.size == 0:
            return None
        o = np.argsort(d, kind='stable')
        d, v = d[o], v[o]
        st = np.empty(d.size, dtype=bool)
        st[0] = True
        st[1:] = d[1:] > d[:-1] * (1.0 + 1e-9)
        ends = np.flatnonzero(st)
        ends = np.append(ends[1:] - 1, d.size - 1)
        return float(np.min(np.abs(np.cumsum(v)[ends] / target - 1.0)))

    tried = 0
    for name, sp in sorted(specs.items()):
        case = cases().get(name)
        if case is None or not sp.charges:
            continue
        sf = norm(sp.files['system/setFieldsDict'])
        if 'MassToCell' not in sf:
            continue           # plain geometric source (static planar)
        m = re.search(r'scale\s+([0-9.eE+-]+);', sf)
        check(f'N5-2: {name} sets scale on its charge source',
              m is not None, sf[:200])
        if m is None:
            continue
        tried += 1
        centre, mass = sp.charges[0]
        planar = sp.dim == 2 and getattr(case, 'geometry', '') == 'planar'
        r = charge_radius(mass, MATERIALS[sp.material], planar=planar)
        geo, cen, dims = geometry_of(sp, case, centre)
        k = float(m.group(1)) ** (1.0 / 3.0)
        target = _staircase(sp.dim, geo, sp.dx_charge, r, cen, dims)[2]
        if target <= 0:
            continue
        raw = _staircase(sp.dim, geo, sp.dx_charge, r, cen, dims)[1] / target
        got = _staircase(sp.dim, geo, sp.dx_charge,
                         k * r, cen, dims)[1] / target
        check(f'N5-2: {name} is never worse than the vendor default',
              abs(got - 1.0) <= abs(raw - 1.0) + 1e-12,
              f'corrected {got:.4f} vs raw {raw:.4f}')
        best = best_plateau(sp.dim, geo, sp.dx_charge, r, cen, dims, target)
        check(f'N5-2: {name} takes the best plateau on offer',
              best is None or abs(got - 1.0) <= best + 1e-9,
              f'got {abs(got - 1.0):.5f}, best available {best:.5f}')
        # the scale must survive the ten digits `fmt` writes: the search
        # returns the MIDDLE of a plateau, never its edge, so rounding
        # cannot tip a cell in or out
        check(f'N5-2: {name} scale is robust to the written precision',
              _staircase(sp.dim, geo, sp.dx_charge,
                         k * r * (1 + 1e-9), cen, dims)[1] / target == got
              and _staircase(sp.dim, geo, sp.dx_charge,
                             k * r * (1 - 1e-9), cen, dims)[1] / target == got,
              f'{name} sits on a step edge')

    check('N5-2: the charge cases were actually exercised', tried >= 4,
          f'only {tried}')

    # a profile stage marks no charge at all, so it carries no scale
    sf = norm(specs['case2d_axi_profile'].files['system/setFieldsDict'])
    check('N5-2: a profile stage still marks no charge region',
          'MassToCell' not in sf and 'scale ' not in sf, sf[-160:])


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


def _parse_internal(text):
    """(kind, values) of a nonuniform internalField."""
    _head, sep, rest = text.partition("internalField")
    assert sep and "nonuniform" in rest[:40], "not nonuniform"
    kind = "vector" if "List<vector>" in rest[:60] else "scalar"
    count, _, tail = rest.split("List<" + kind + ">", 1)[1].partition("(")
    n = int(count.strip())
    rows = [ln.strip() for ln in tail.rsplit(")", 1)[0].splitlines()
            if ln.strip()]
    if kind == "scalar":
        vals = np.array([float(x) for x in rows])
    else:
        vals = np.array([[float(c) for c in ln.strip("()").split()]
                         for ln in rows])
    assert len(vals) == n, (len(vals), n)
    return kind, vals


def profile_checks(specs):
    """N7: a profile-initialised stage writes the remapped state into
    0/ as nonuniform fields, sets no charge region, and conserves the
    profile's mass and energy on the case grid."""
    from blastlab.core.grid import make_geometry
    from blastlab.solvers.foam import writer as W
    from blastlab.solvers.foam.materials import MATERIALS
    sp = specs["case2d_axi_profile"]
    # no charge sphere, but r_exp keeps the SOURCE charge radius so
    # the next stage in the chain still knows the yield scale
    check("profile: no charge sphere planned", sp.charges == []
          and abs(sp.r_exp - 0.0527) < 1e-9,
          f"{sp.charges} {sp.r_exp}")
    sf = norm(sp.files["system/setFieldsDict"])
    check("profile: setFieldsDict marks no region",
          "sphericalMassToCell" not in sf and "cylinderToCell" not in sf,
          sf[-120:])
    st = sp.init_state
    check("profile: init_state carries the remap", st is not None
          and st["rho"].shape == (sp.nx, sp.ny)
          and abs(st["t0"] - 0.0005) < 1e-12,
          str(None if st is None else (st["rho"].shape, st["t0"])))
    d = sp.start_dir
    check("profile: fields live in a t0 time dir, not 0/",
          d != "0" and abs(float(d) - 0.0005) < 1e-9
          and f"{d}/p" in sp.files and "0/p" not in sp.files, d)
    cd = norm(sp.files["system/controlDict"])
    check("profile: the run starts from that dir (latestTime)",
          "startFrom latestTime;" in cd
          and f"startTime {d};" in cd, cd[:200])
    n_cells = sp.nx * sp.ny
    got = {}
    for name in ("p", "T", "U", "alpha.expl", "rho.expl", "rho.air"):
        rel = f"{d}/{name}"
        kind, vals = _parse_internal(sp.files[rel])
        got["0/" + name] = vals
        check(f"profile: {name} nonuniform over every cell",
              len(vals) == n_cells
              and kind == ("vector" if name == "U" else "scalar"),
              f"{len(vals)} vs {n_cells}, {kind}")
    alpha = got["0/alpha.expl"]
    phase = st["phase"].ravel(order="F")
    check("profile: alpha is the phase flag, in mesh (F) order",
          np.array_equal(alpha > 0.5, phase > 0.5)
          and set(np.unique(alpha)) <= {0.0, 1.0}, str(np.unique(alpha)))
    g = make_geometry("axisymmetric", sp.grid["x_face"][-1],
                      sp.grid["y_face"][-1], sp.dx)
    V = np.broadcast_to(g["V"], (sp.nx, sp.ny)).ravel(order="F")
    rho_mix = np.where(alpha > 0.5, got["0/rho.expl"], got["0/rho.air"])
    rho_ref = st["rho"].ravel(order="F")
    e_ref = st["e"].ravel(order="F")
    m = MATERIALS[sp.material]
    Cv = np.where(alpha > 0.5, m.Cv_products, W.CV_AIR)
    d_mass = abs((rho_mix * V).sum() - (rho_ref * V).sum()) / (rho_ref * V).sum()
    e_back = Cv * got["0/T"]
    ref_E = (rho_ref * e_ref * V).sum()
    d_energy = abs((rho_mix * e_back * V).sum() - ref_E) / ref_E
    check("profile: emitted mass equals the profile to 1e-6",
          d_mass < 1e-6, f"rel {d_mass:.2e}")
    check("profile: emitted internal energy equals the profile to 1e-6",
          d_energy < 1e-6, f"rel {d_energy:.2e}")
    ke_ref = (0.5 * (st["u"] ** 2 + st["v"] ** 2)).ravel(order="F")
    ke_got = 0.5 * (got["0/U"] ** 2).sum(axis=1)
    ref_K = (ke_ref * rho_ref * V).sum()
    d_ke = abs((ke_got * rho_mix * V).sum() - ref_K) / ref_K
    check("profile: emitted kinetic energy equals the profile to 1e-6",
          d_ke < 1e-6, f"rel {d_ke:.2e}")
    check("profile: U third component is zero in 2D",
          np.all(got["0/U"][:, 2] == 0.0))


def profile_amr_checks(specs):
    """T70: a profile stage may also run dynamic AMR. Its state is
    written on the base mesh - the mesh blockMesh builds and the only
    one whose cell order is known before the run starts - NOT on the
    display grid `spec.grid` sits on, which is 2**(dim*D) times bigger.
    """
    from blastlab.solvers.foam import backend
    sp = specs['case2d_axi_profile_amr']
    n_base = sp.nb[0] * sp.nb[1]
    check('profile+amr: display grid is 2 levels above the base mesh',
          sp.amr == 2 and sp.display_level == 2 and sp.nb == (20, 40)
          and (sp.nx, sp.ny) == (80, 160) and sp.n_cells == n_base,
          f'{sp.nb} {(sp.nx, sp.ny)} {sp.n_cells}')
    check('profile+amr: init_grid is the base grid, not the display grid',
          sp.init_grid is sp.grid_base
          and sp.init_state['rho'].shape == sp.nb,
          str(sp.init_state['rho'].shape))
    d = sp.start_dir
    for name in ('p', 'T', 'U', 'alpha.expl', 'rho.expl', 'rho.air'):
        kind, vals = _parse_internal(sp.files[f'{d}/{name}'])
        check(f'profile+amr: {name} sized for the base mesh',
              len(vals) == n_base, f'{len(vals)} vs {n_base}')
    check('profile+amr: blockMesh builds the base counts',
          '(20 40 1)' in norm(sp.files['system/blockMeshDict']))
    check('profile+amr: adaptiveFvMesh, no static refine dicts',
          'dynamicFvMesh adaptiveFvMesh;'
          in norm(sp.files['constant/dynamicMeshDict'])
          and not any('refineMeshDict' in k for k in sp.files))
    cmds = [c if isinstance(c, str) else '<python>'
            for _l, c in backend._mesh_stages(sp, None)]
    i_state = cmds.index('<python>')
    i_cc = next(i for i, c in enumerate(cmds) if 'writeCellCentres' in c)
    check('profile+amr: state written, THEN the cell centres of that mesh',
          i_state < i_cc and f'-time {d}' in cmds[i_cc]
          and not any('setRefinedFields' in c for c in cmds)
          and not any('refineMesh' in c for c in cmds), str(cmds))
    check('profile+amr: the source profile spacing rides along',
          abs(sp.init_state['dx_src'] - 0.01) < 1e-6,
          str(sp.init_state['dx_src']))


def burst_point_checks():
    """T62: a profile-initialised 3D stage has no charge list, so the
    shock-front metrics must fall back to the profile's own centre.
    They used to be fed the empty list straight from spec.charges,
    which crashed the run loop before the first frame."""
    from blastlab.core import geometry
    case = Case3D(Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.05,
                  center=(0.5, 0.5, 0.5), init_mode='profile1d',
                  profile_file_in=PROFILE_1D, n_snapshots=2,
                  solver='blastfoam', material='TNT')
    sp = render_case(case)
    check("3D profile: no charge sphere planned", sp.charges == [],
          str(sp.charges))
    check("3D profile: burst point is the profile centre",
          sp.burst_points == [(0.5, 0.5, 0.5)], str(sp.burst_points))
    # exactly what solve_3d_foam / postmortem do with them
    g = sp.grid
    d = geometry.d_charge_3d(g['x_c'], g['y_c'], g['z_c'], sp.burst_points)
    check("3D profile: d_charge spans the grid, zero at the centre",
          d.shape == (sp.nx, sp.ny, sp.nz) and d.min() < sp.dx,
          f"{d.shape} min {d.min():.4g}")
    dists = geometry.stop_dists_3d(case.Lx, case.Ly, case.Lz,
                                   sp.burst_points, case.bcs)
    check("3D profile: stop distances measured from it",
          dists and min(dists) > 0, str(dists))
    for name, fn in (('d_charge_3d',
                      lambda: geometry.d_charge_3d(g['x_c'], g['y_c'],
                                                   g['z_c'], [])),
                     ('stop_dists_3d',
                      lambda: geometry.stop_dists_3d(1.0, 1.0, 1.0, [],
                                                     case.bcs))):
        try:
            fn()
            ok, detail = False, 'no error'
        except ValueError as exc:
            ok, detail = True, str(exc)
        except Exception as exc:               # noqa: BLE001
            ok, detail = False, f'{type(exc).__name__}: {exc}'
        check(f"3D profile: {name} rejects an empty centre list", ok, detail)

    # P1-3: the last member of that family - phaseProperties' detonation
    # points. The empty list is CORRECT for a profile stage (its material
    # arrives already reacted; lighting the profile centre would detonate
    # it twice), so the emitted file must not change; what must not stay
    # silent is a CHARGE case that ends up with nothing to light.
    from blastlab.solvers.foam import writer as _w
    pp = _w._phaseproperties(sp, activation='linear', afterburn='none')
    check("profile stage still emits an empty detonation points list",
          'points ();' in pp,
          [ln for ln in pp.splitlines() if 'points' in ln])
    check("profile stage keeps its activation model",
          'activationModel linear;' in pp,
          [ln for ln in pp.splitlines() if 'activationModel' in ln])

    class _NoCentres(list):
        """A charge list that is truthy but yields no centres - the shape
        the guard exists for. Normal code cannot reach it today, which is
        the point: if a future edit drops the centres, the writer must
        refuse instead of emitting a case that never ignites."""

        def __iter__(self):
            return iter(())

    sp.charges = _NoCentres([((0.5, 0.5, 0.5), 1.0)])
    try:
        _w._phaseproperties(sp, activation='linear', afterburn='none')
        ok, detail = False, 'wrote a phaseProperties that never ignites'
    except ValueError as exc:
        ok, detail = 'never ignite' in str(exc), str(exc)
    check("a charge case with no detonation points is refused, loudly",
          ok, detail)


def time_name_checks():
    """T62: `startFrom latestTime` keeps the time VALUE it scanned and
    rebuilds the name from it at controlDict's timePrecision, so a time
    directory named with more digits than that is asked for back under a
    name nothing wrote - the run dies on a missing field file. Every
    emitted time dir must survive that value -> name round trip."""
    from blastlab.solvers.foam.dicts import TIME_PRECISION, tfmt
    # a remap t0 needing more digits than timePrecision - the profile
    # fixture's own t0 is short enough to have hidden this for a year
    for t0 in (0.0005, 0.0009331866336, 1.0 / 3.0, 0.1234567891234):
        d = tfmt(t0)
        check(f"time name {d} round-trips through its value",
              tfmt(float(d)) == d, f"{d} -> {tfmt(float(d))}")
    sp = specs_time_name()
    check("profile start dir is named at timePrecision",
          sp.start_dir == format(sp.t_start, f'.{TIME_PRECISION}g'),
          f"{sp.start_dir} vs t_start {sp.t_start!r}")
    check("profile fields live in the dir the run will ask for",
          f"{sp.start_dir}/p" in sp.files, sorted(sp.files)[:3])
    cd = norm(sp.files["system/controlDict"])
    check("controlDict startTime matches that dir",
          f"startTime {sp.start_dir};" in cd
          and f"timePrecision {TIME_PRECISION};" in cd,
          cd[:220])


def deferred_state_checks():
    """T62: a profile stage's fields are nonuniform over the FINAL
    cells, so they must not be on disk while subsetMesh/refineMesh are
    still reshaping the mesh - those read every field at the mesh they
    start from and abort on the count mismatch."""
    import shutil
    import tempfile
    from blastlab.solvers.foam import backend, writer as fw

    case = Case3D(Lx=10.0, Ly=10.0, Lz=10.0, cell_size_m=0.5,
                  center=(5.0, 5.0, 0.0), init_mode='profile1d',
                  profile_file_in=PROFILE_1D, charge=50.0,
                  obstacles=[(7.0, 10.0, 7.0, 10.0, 0.0, 5.0)],
                  n_snapshots=1, solver='blastfoam', material='TNT')
    tmp = tempfile.mkdtemp(prefix='blastlab_defer_')
    dest = os.path.join(tmp, 'case_3d')
    real_new = fw.env.new_case_dir
    try:
        fw.env.new_case_dir = lambda dim, stamp=None: ('/root/case_3d', dest)
        sp = fw.write_case(case, n_procs=4)
    finally:
        fw.env.new_case_dir = real_new
    try:
        d = sp.start_dir
        check("carved profile case defers its state",
              set(sp.deferred) == {f'{d}/{n}' for n in
                                   ('p', 'T', 'U', 'alpha.expl',
                                    'rho.expl', 'rho.air',
                                    'lambda.expl')},
              str(sp.deferred))
        check("state is absent while the mesh is still being carved",
              not os.path.isdir(os.path.join(dest, d))
              and os.path.isfile(os.path.join(dest, 'system',
                                              'controlDict')))
        fw.write_deferred(sp)
        check("write_deferred lands every field",
              all(os.path.isfile(os.path.join(dest, *r.split('/')))
                  for r in sp.deferred))
        # the fields describe the carved mesh, not the block mesh
        n_carved = sp.n_cells
        kind, vals = _parse_internal(sp.files[f'{d}/p'])
        check("state is sized for the carved mesh",
              len(vals) == n_carved < sp.nx * sp.ny * sp.nz,
              f"{len(vals)} vs {n_carved} of {sp.nx * sp.ny * sp.nz}")
        labels = [lbl for lbl, _cmd in backend._mesh_stages(sp, None)]
        cmds = [c if isinstance(c, str) else '<python>'
                for _l, c in backend._mesh_stages(sp, None)]
        i_state = next(i for i, c in enumerate(cmds) if c == '<python>')
        i_sub = max(i for i, c in enumerate(cmds) if 'subsetMesh' in c)
        i_dec = next(i for i, c in enumerate(cmds) if 'decomposePar' in c)
        check("state is written after carving and before decomposing",
              i_sub < i_state < i_dec, str(labels))
        check("no setRefinedFields on a profile stage",
              not any('setRefinedFields' in c for c in cmds), str(cmds))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def fo_block(text, name):
    """The text of function object `name` in a controlDict (its header
    line through its closing brace), or None."""
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line == f'    {name}':
            depth, out = 0, []
            for ln in lines[i:]:
                out.append(ln)
                depth += ln.count('{') - ln.count('}')
                if depth == 0 and '}' in ln:
                    return '\n'.join(out)
    return None


def fo_names(text):
    """The function-object names of a controlDict, in file order."""
    body = text.split('\nfunctions\n{\n', 1)[1]
    return [ln.strip() for ln in body.split('\n')
            if ln.startswith('    ') and not ln.startswith('     ')
            and ln.strip() not in ('{', '}', '')]


def top_entry(text, key):
    """A top-level controlDict entry's value (function objects carry
    their own, indented)."""
    import re
    m = re.search(rf'^{key}\s+([^;]+);', text, re.M)
    return m.group(1).strip() if m else None


def vtk_checks():
    """OUT-2 Step 3: the VTK output dictionaries, line by line against
    blastFoam User Guide v6.0 sec. 15.5 (p. 124) and the tutorial
    building3DWorkshop/system/controlDict."""
    from blastlab.solvers.foam import writer as W
    print('\n  OUT-2: VTK output')
    base = dict(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.05, charge=4.0,
                center=(0.5, 1.0, 1.0),
                obstacles=[(1.2, 1.5, 0.6, 1.4, 0.0, 1.2)],
                gauges=[(1.8, 1.0, 1.0)], n_snapshots=3,
                solver='blastfoam', material='TNT')
    # Time-mode values are in seconds (owner decision P22): the writer
    # writes them as they are
    surf = {'on': True, 'mode': 'time', 'value': 0.0005,
            'fields': ['p', 'pMax'], 'obstacle_fields': ['p', 'impulse'],
            'planes': [['y', 1.4], ['z', 0.5]]}
    vol = {'on': True, 'mode': 'step', 'value': 25,
           'fields': ['p', 'rho', 'U']}
    plain = render_case(Case3D(**base))
    both = render_case(Case3D(**base, vtk_surfaces=surf, vtk_volumes=vol))
    ctl, ctl0 = both.files['system/controlDict'], \
        plain.files['system/controlDict']
    names = fo_names(ctl)
    check('vtk: the two surface objects are the LAST functions entries, '
          'after the probes',
          names[-3:] == ['gauges', W.VTK_SECTIONS, W.VTK_OBSTACLES],
          str(names))
    check('vtk: writeTimes (T62) is still there',
          'writeTimes' in names and fo_block(ctl, 'writeTimes')
          == fo_block(ctl0, 'writeTimes'))
    sec = fo_block(ctl, W.VTK_SECTIONS)
    for want in ('type surfaces;',
                 'libs ("libsampling.so" "libblastFunctionObjects.so");',
                 'writeControl runTime;', 'writeInterval 0.0005;',
                 'surfaceFormat vtkTimeSeries;',
                 'interpolationScheme cell;', 'fields (p pMax);'):
        check(f'vtk sections: {want}', want in norm(sec), sec)
    check('vtk sections: Time mode never uses adjustableRunTime (D5)',
          'adjustableRunTime' not in sec)
    # the live slice (burst point y = 1.0) first, then the table rows
    y_live = W.snap_plane(both, 'y', 1.0)
    y_14, z_05 = W.snap_plane(both, 'y', 1.4), W.snap_plane(both, 'z', 0.5)
    yc, zc = both.grid['y_c'], both.grid['z_c']
    check('vtk sections: planes snap to the nearest cell-centre layer',
          y_14 == float(yc[np.argmin(abs(yc - 1.4))])
          and z_05 == float(zc[np.argmin(abs(zc - 0.5))])
          and y_14 != 1.4, f'{y_14} {z_05}')
    order = [ln.strip() for ln in sec.split('\n')
             if ln.startswith('            slice_')]
    check('vtk sections: the live slice first, then the rows, named by the '
          'position asked for (Q6)',
          order == ['slice_y_1.00', 'slice_y_1.40', 'slice_z_0.50'],
          str(order))
    for name, axis, pos in (('slice_y_1.00', 'y', y_live),
                            ('slice_y_1.40', 'y', y_14),
                            ('slice_z_0.50', 'z', z_05)):
        pt, nrm = W.plane_point_normal(axis, pos)
        blk = norm(sec.split(name, 1)[1].split('}\n            }', 1)[0])
        ok = all(w in blk for w in (
            'type plane;', 'planeType pointAndNormal;',
            f'point {fmt(pt)};', f'normal {fmt(nrm)};',
            'interpolate no;', 'triangulate no;'))
        check(f'vtk sections: {name} is an uncut plane through '
              f'{axis} = {pos:g}', ok, blk)
    check('vtk sections: the live slice itself is unchanged',
          fo_block(ctl, W.LIVE_SLICE) == fo_block(ctl0, W.LIVE_SLICE))
    obs = norm(fo_block(ctl, W.VTK_OBSTACLES))
    for want in ('type surfaces;', 'writeControl runTime;',
                 'writeInterval 0.0005;', 'surfaceFormat vtkTimeSeries;',
                 'fields (p impulse);', 'obstacles {', 'type patch;',
                 'patches (obstacles);', 'triangulate no;'):
        check(f'vtk obstacles: {want}', want in obs, obs)
    check('vtk volumes, Step mode: top-level writeControl timeStep, '
          'writeInterval 25',
          top_entry(ctl, 'writeControl') == 'timeStep'
          and top_entry(ctl, 'writeInterval') == '25',
          f"{top_entry(ctl, 'writeControl')} {top_entry(ctl, 'writeInterval')}")
    check('vtk volumes, Step mode: spec.write_steps 25, adaptive off',
          both.write_steps == 25 and both.adaptive_write is False
          and plain.write_steps == 0 and plain.adaptive_write is True)

    # surfaces only: the dictionary is the plain one plus the two blocks,
    # nothing else moves (the solve is untouched, D5)
    only = render_case(Case3D(**base, vtk_surfaces=surf))
    oc = only.files['system/controlDict']
    stripped = oc.replace(fo_block(oc, W.VTK_SECTIONS) + '\n', '').replace(
        fo_block(oc, W.VTK_OBSTACLES) + '\n', '')
    check('vtk surfaces only: remove the two blocks and the controlDict is '
          'the plain one, byte for byte', stripped == ctl0)
    check('   and every other file is byte-identical',
          {k: v for k, v in only.files.items() if k != 'system/controlDict'}
          == {k: v for k, v in plain.files.items()
              if k != 'system/controlDict'})
    check('   and the spec schedule is the plain one',
          only.adaptive_write is True and only.write_steps == 0
          and only.write_interval == plain.write_interval)

    step = render_case(Case3D(**base, vtk_surfaces=dict(
        surf, mode='step', value=10)))
    sb = norm(fo_block(step.files['system/controlDict'], W.VTK_SECTIONS))
    check('vtk surfaces, Step mode: writeControl timeStep; writeInterval 10',
          'writeControl timeStep;' in sb and 'writeInterval 10;' in sb, sb)

    tv = render_case(Case3D(**base, vtk_volumes=dict(vol, mode='time',
                                                     value=0.0002)))
    tc = tv.files['system/controlDict']
    # owner decision P14 (b): runTime, so the writes never clip dt
    check('vtk volumes, Time mode: runTime (never adjustableRunTime, '
          'P14 b), writeInterval = value = 0.0002 s (P22), pinned',
          top_entry(tc, 'writeControl') == 'runTime'
          and 'adjustableRunTime' not in tc
          and top_entry(tc, 'writeInterval') == '0.0002'
          and tv.write_interval == 0.0002 and tv.adaptive_write is False
          and tv.write_steps == 0)
    fx = render_case(Case3D(**base, fixed_dt=1e-6,
                            vtk_volumes=dict(vol, mode='time', value=0.0002)))
    fs = render_case(Case3D(**base, fixed_dt=1e-6, vtk_volumes=vol))
    check('vtk volumes with fixed_dt: Time mode runTime, Step mode stays '
          'timeStep',
          top_entry(fx.files['system/controlDict'], 'writeControl')
          == 'runTime'
          and top_entry(fs.files['system/controlDict'], 'writeControl')
          == 'timeStep')
    bud = render_case(Case3D(**base, t_end=0.003, write_budget=10,
                             vtk_volumes=vol))
    check('vtk volumes + a write budget (validation refuses it): volumes '
          'win, no budget, so no decomposed purge',
          bud.write_budget == 0 and bud.write_steps == 25)

    no_obs = dict(base, obstacles=[], gauges=[(1.8, 1.0, 1.0)])
    nob = render_case(Case3D(**no_obs, vtk_surfaces=surf))
    nn = fo_names(nob.files['system/controlDict'])
    check('vtk: no obstacles patch -> no obstacles object, sections still '
          'written', W.VTK_OBSTACLES not in nn and W.VTK_SECTIONS in nn,
          str(nn))
    nat_base = dict(base, solver='native')
    nat = render_case(Case3D(**nat_base, vtk_surfaces=surf,
                             vtk_volumes=vol))
    check('vtk: a native case carries nothing (solver != blastfoam)',
          nat.vtk_surfaces is None and nat.vtk_volumes is None
          and nat.files == render_case(Case3D(**nat_base)).files)
    off = render_case(Case3D(**base, vtk_surfaces=dict(surf, on=False),
                             vtk_volumes=dict(vol, on=False)))
    check('vtk: families switched off render the plain case',
          off.files == plain.files)

    # 2D: obstacles only, and the obstacles patch exists
    c2 = dict(Lx=4.0, Ly=4.0, cell_size_m=0.02, charge=1.0,
              center=(0.0, 1.0), obstacles=[(2.0, 2.4, 0.0, 1.6)],
              gauges=[(1.0, 1.0)], solver='blastfoam', material='TNT')
    s2 = render_case(Case2D(**c2, vtk_surfaces=dict(
        surf, fields=[], planes=[], obstacle_fields=['p', 'overpressure'])))
    n2 = fo_names(s2.files['system/controlDict'])
    check('vtk 2D: the obstacles object only, last',
          n2[-1] == W.VTK_OBSTACLES and W.VTK_SECTIONS not in n2, str(n2))

    # 1D volumes: the schedule only, no surfaces
    c1 = dict(radius_m=5.0, charge_kg=1.0, cell_size_m=0.02,
              gauge_radii=[1.0, 2.0], solver='blastfoam', material='TNT')
    p1 = render_case(Case1D(**c1))
    v1 = render_case(Case1D(**c1, vtk_volumes=dict(vol, value=40)))
    t1 = render_case(Case1D(**c1, vtk_volumes=dict(vol, mode='time',
                                                   value=0.00025)))
    v1c, t1c = v1.files['system/controlDict'], t1.files['system/controlDict']
    check('vtk 1D volumes, Step mode: timeStep every 40, pinned',
          top_entry(v1c, 'writeControl') == 'timeStep'
          and top_entry(v1c, 'writeInterval') == '40'
          and v1.write_steps == 40 and v1.adaptive_write is False)
    check('vtk 1D volumes, Time mode: runTime 0.00025 s (P14 b)',
          top_entry(t1c, 'writeControl') == 'runTime'
          and top_entry(t1c, 'writeInterval') == '0.00025')
    check('vtk 1D: no surface object, the rest of the functions unchanged',
          fo_names(v1c) == fo_names(p1.files['system/controlDict']))

    # the backend: the banner line, hooks.cadence and the adaptive flag
    from blastlab.solvers.foam import backend as B
    check('vtk banner, Step mode: "every 25 solver steps"',
          B._write_interval_line(both)
          == '  Write interval  : every 25 solver steps (pinned: VTK volumes)',
          B._write_interval_line(both))
    check('vtk banner, Time mode: the pinned ms interval',
          B._write_interval_line(tv)
          == '  Write interval  : 0.2000 ms (pinned: VTK volumes)',
          B._write_interval_line(tv))
    check('   and a case without VTK keeps its old line',
          B._write_interval_line(plain) == '  Write interval  : '
          f'{plain.write_interval * 1e3:.4f} ms (initial, adaptive)')

    class _Stop(Exception):
        pass

    class _Hooks:
        def __init__(self):
            self.seen = None

        def cadence(self, dt=None, steps=None):
            self.seen = (dt, steps)
            raise _Stop()                 # right after the expression

        def __getattr__(self, _name):
            return lambda *a, **k: None

    for solve, case, dt_want in (
            (B.solve_3d_foam, Case3D(**base, vtk_volumes=vol), None),
            (B.solve_3d_foam, Case3D(**base, vtk_volumes=dict(
                vol, mode='time', value=0.0002)), 0.0002),
            (B.solve_2d_foam, Case2D(**c2, vtk_volumes=vol), None),
            (B.solve_1d_foam, Case1D(**c1, vtk_volumes=vol), None)):
        spec, h = render_case(case), _Hooks()
        try:
            solve(case, hooks=h, adaptive_write=True, spec=spec)
        except _Stop:
            pass
        check(f'vtk volumes {case.dim}D {case.vtk_volumes["mode"]}: the '
              f'solve keeps adaptive_write off, cadence dt {dt_want}',
              spec.adaptive_write is False and h.seen is not None
              and h.seen[0] == dt_want, f'{spec.adaptive_write} {h.seen}')

    # P1-5: a resumed AMR leg has no pMax / impulse to sample (D4)
    case_fo = Case3D(**base, vtk_surfaces=dict(
        surf, fields=['p', 'pMax'], obstacle_fields=['impulse']))
    spec_fo = render_case(case_fo)
    spec_fo.fo_accumulators = False
    rc = W._controldict(spec_fo, case_fo)
    sb = norm(fo_block(rc, W.VTK_SECTIONS))
    check('vtk, fo_accumulators off: pMax dropped from the sections, and '
          'an obstacles list of impulse alone drops the object',
          'fields (p);' in sb and W.VTK_OBSTACLES not in fo_names(rc), sb)
    import tempfile
    amr_case = Case3D(**dict(base, amr_levels=1), vtk_surfaces=surf)
    amr_spec = render_case(amr_case)
    lines = []
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, 'system'))
        amr_spec.case_unc = d
        applied = B._disable_fo_accumulators(
            amr_spec, amr_case, type('H', (), {'log': lambda s, m:
                                               lines.append(m)})())
        with open(os.path.join(d, 'system', 'controlDict')) as f:
            written = f.read()
    said = [m for m in lines if 'VTK sections/obstacles' in m]
    check('vtk, resumed AMR leg: one log line naming impulse and pMax, and '
          'the rewritten controlDict samples neither',
          applied and len(said) == 1 and 'impulse and pMax' in said[0]
          and 'pMax' not in norm(fo_block(written, W.VTK_SECTIONS))
          and 'impulse' not in norm(fo_block(written, W.VTK_OBSTACLES)),
          str(lines))


def gauge_checks():
    """OUT-4a A3: the dynamicPressure function object and the gauge probe
    fields, line by line against blastFoam User Guide v6.0 sec. 15.1
    (blastProbes, pp. 122-123) and sec. 15.9 (dynamicPressure, p. 125)."""
    from blastlab.solvers.foam import writer as W
    from blastlab.solvers.foam import backend as B
    print('\n  OUT-4a: gauge extras + dynamicPressure')
    base = dict(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.05, charge=4.0,
                center=(0.5, 1.0, 1.0),
                obstacles=[(1.2, 1.5, 0.6, 1.4, 0.0, 1.2)],
                gauges=[(1.8, 1.0, 1.0)], n_snapshots=3,
                solver='blastfoam', material='TNT')
    extras = {'fields': ['overpressure', 'impulse', 'T', 'dynamicP']}
    plain = render_case(Case3D(**base))
    allx = render_case(Case3D(**base, vtk_gauges=extras))
    ctl, ctl0 = allx.files['system/controlDict'], \
        plain.files['system/controlDict']
    check('gauges: an empty vtk_gauges renders the plain case, byte for '
          'byte', render_case(Case3D(**base, vtk_gauges={'fields': []}))
          .files == plain.files)
    check('gauges: no dynamicPressure object in the plain case',
          'dynamicPressure' not in fo_names(ctl0))
    names = fo_names(ctl)
    check('gauges: dynamicPressure comes before the probes (A3 FO order)',
          'dynamicPressure' in names and 'gauges' in names
          and names.index('dynamicPressure') < names.index('gauges'),
          str(names))
    check('   and after every accumulating function object',
          all(names.index(n) < names.index('dynamicPressure')
              for n in ('impulse', 'pMax', 'arrival', 'overpressure')),
          str(names))
    dp = norm(fo_block(ctl, 'dynamicPressure'))
    for want in ('type dynamicPressure;',
                 'libs ("libblastFunctionObjects.so");',
                 'writeControl writeTime;',
                 # OF-9 fieldExpression names the result `dynamicPressure`
                 # unless told (first OUT-4a e2e run, 2026-09-27)
                 'result dynamicP;'):
        check(f'dynamicPressure: {want}', want in dp, dp)
    check('dynamicPressure: rhoName / UName left at the guide defaults',
          'rhoName' not in dp and 'UName' not in dp, dp)
    pr = norm(fo_block(ctl, 'gauges'))
    check('probes: fields (p U rho overpressure impulse T dynamicP)',
          'fields (p U rho overpressure impulse T dynamicP);' in pr, pr)
    check('probes: the plain case keeps fields (p U rho)',
          'fields (p U rho);' in norm(fo_block(ctl0, 'gauges')))
    stripped = norm(ctl.replace(fo_block(ctl, 'dynamicPressure') + '\n',
                                '')).replace(
        'fields (p U rho overpressure impulse T dynamicP);',
        'fields (p U rho);')
    check('gauges: remove the object and the extras and the controlDict is '
          'the plain one', stripped == norm(ctl0))
    check('   and every other file is byte-identical',
          {k: v for k, v in allx.files.items() if k != 'system/controlDict'}
          == {k: v for k, v in plain.files.items()
              if k != 'system/controlDict'})
    # only T at the gauges: no dynamicPressure object
    t_only = render_case(Case3D(**base, vtk_gauges={'fields': ['T']}))
    check('gauges: T only -> no dynamicPressure object',
          'dynamicPressure' not in fo_names(t_only.files['system/controlDict']))
    # dynamicP ticked in a VTK family only
    vol = {'on': True, 'mode': 'step', 'value': 25, 'fields': ['p', 'dynamicP']}
    vv = render_case(Case3D(**base, vtk_volumes=vol))
    check('volumes with dynamicP: the object is emitted',
          'dynamicPressure' in fo_names(vv.files['system/controlDict']))
    surf = {'on': True, 'mode': 'time', 'value': 0.0005, 'fields': [],
            'obstacle_fields': ['dynamicP'], 'planes': []}
    ss = render_case(Case3D(**base, vtk_surfaces=surf))
    sn = fo_names(ss.files['system/controlDict'])
    check('obstacles with dynamicP: the object precedes vtkObstacles',
          sn.index('dynamicPressure') < sn.index(W.VTK_OBSTACLES), str(sn))
    no_g = render_case(Case3D(**dict(base, gauges=[]), vtk_gauges=extras))
    check('dynamicP at gauges without gauges: no object, no probes',
          'dynamicPressure' not in fo_names(no_g.files['system/controlDict'])
          and 'gauges' not in fo_names(no_g.files['system/controlDict']))
    nat = render_case(Case3D(**dict(base, solver='native'),
                             vtk_gauges=extras))
    check('native: vtk_gauges changes nothing',
          nat.gauge_fields == ()
          and nat.files == render_case(Case3D(**dict(
              base, solver='native'))).files)
    # 1D: T and dynamicP only (overpressure / impulse are 2D/3D, D4)
    c1 = dict(radius_m=5.0, charge_kg=1.0, cell_size_m=0.02,
              gauge_radii=[1.0, 2.0], solver='blastfoam', material='TNT')
    one = render_case(Case1D(**c1, vtk_gauges=extras))
    c1t = one.files['system/controlDict']
    check('1D: overpressure / impulse dropped, T and dynamicP probed',
          one.gauge_fields == ('T', 'dynamicP')
          and 'fields (p U rho T dynamicP);' in norm(fo_block(c1t, 'gauges'))
          and fo_names(c1t).index('dynamicPressure')
          < fo_names(c1t).index('gauges'), norm(fo_block(c1t, 'gauges')))
    # resumed AMR leg: impulse dropped from the probes, with one log line
    import tempfile
    amr_case = Case3D(**dict(base, amr_levels=1), vtk_gauges=extras)
    amr_spec = render_case(amr_case)
    lines = []
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, 'system'))
        amr_spec.case_unc = d
        B._disable_fo_accumulators(
            amr_spec, amr_case, type('H', (), {'log': lambda s, m:
                                               lines.append(m)})())
        with open(os.path.join(d, 'system', 'controlDict')) as f:
            written = f.read()
    said = [m for m in lines if 'VTK gauges' in m]
    check('resumed AMR leg: impulse dropped from the probes, one log line',
          len(said) == 1 and 'impulse' in said[0]
          and 'fields (p U rho overpressure T dynamicP);'
          in norm(fo_block(written, 'gauges')), str(lines))


def peak_impulse_checks():
    """OUT-4b B2 (owner Q2): the Peak_Impulse fieldMinMax on `impulse`,
    line by line against blastFoam User Guide v6.0 sec. 15.2 (p. 123):
    `fields`, `minMax`; emitted only when a family asks for impulseMax,
    after `impulse`, before the samplers; the pMax entry untouched."""
    from blastlab.solvers.foam import writer as W
    from blastlab.solvers.foam import backend as B
    print('\n  OUT-4b: peak impulse (impulseMax)')
    base = dict(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.05, charge=4.0,
                center=(0.5, 1.0, 1.0),
                obstacles=[(1.2, 1.5, 0.6, 1.4, 0.0, 1.2)],
                gauges=[(1.8, 1.0, 1.0)], n_snapshots=3,
                solver='blastfoam', material='TNT')
    surf = {'on': True, 'mode': 'time', 'value': 0.0005,
            'fields': ['p', 'impulseMax'],
            'obstacle_fields': ['p', 'impulseMax'], 'planes': []}
    vol = {'on': True, 'mode': 'step', 'value': 25,
           'fields': ['p', 'impulseMax']}
    plain = render_case(Case3D(**base))
    ctl0 = plain.files['system/controlDict']
    check('impulseMax: no object in the plain case',
          'impulseMax' not in fo_names(ctl0))
    for label, kw in (('sections + obstacles', dict(vtk_surfaces=surf)),
                      ('volumes', dict(vtk_volumes=vol)),
                      ('obstacles only', dict(vtk_surfaces=dict(
                          surf, fields=['p'])))):
        sp = render_case(Case3D(**base, **kw))
        ctl = sp.files['system/controlDict']
        names = fo_names(ctl)
        blk = norm(fo_block(ctl, 'impulseMax')) if 'impulseMax' in names \
            else ''
        check(f'impulseMax ({label}): emitted after impulse and pMax, '
              f'before the samplers',
              'impulseMax' in names
              and names.index('impulse') < names.index('impulseMax')
              and names.index('pMax') < names.index('impulseMax')
              and all(names.index('impulseMax') < names.index(n)
                      for n in ('gauges', W.VTK_SECTIONS, W.VTK_OBSTACLES)
                      if n in names), str(names))
        for want in ('type fieldMinMax;',
                     'libs ("libblastFunctionObjects.so");',
                     'writeControl writeTime;', 'executeAtStart yes;',
                     'fields (impulse);', 'minMax max;'):
            check(f'impulseMax ({label}): {want}', want in blk, blk)
        check(f'impulseMax ({label}): the pMax entry is untouched',
              fo_block(ctl, 'pMax') == fo_block(ctl0, 'pMax'))
        # the same case without impulseMax, minus this one block
        without = {k: (dict(v, fields=[f for f in v['fields']
                                       if f != 'impulseMax'],
                            obstacle_fields=[f for f in v['obstacle_fields']
                                             if f != 'impulseMax'])
                       if k == 'vtk_surfaces' else
                       dict(v, fields=[f for f in v['fields']
                                       if f != 'impulseMax']))
                   for k, v in kw.items()}
        ref = render_case(Case3D(**base, **without)).files[
            'system/controlDict']
        stripped = ctl.replace(fo_block(ctl, 'impulseMax') + '\n', '')
        for fam in (W.VTK_SECTIONS, W.VTK_OBSTACLES):
            if fam in names:
                stripped = stripped.replace(
                    fo_block(ctl, fam), fo_block(ref, fam))
        check(f'impulseMax ({label}): remove it and its field and the '
              f'controlDict is the one without impulseMax', stripped == ref)
    ss = render_case(Case3D(**base, vtk_surfaces=surf))
    for fam, want in ((W.VTK_SECTIONS, 'fields (p impulseMax);'),
                      (W.VTK_OBSTACLES, 'fields (p impulseMax);')):
        check(f'impulseMax: {fam} samples it',
              want in norm(fo_block(ss.files['system/controlDict'], fam)))
    # 2D obstacles
    c2 = dict(Lx=4.0, Ly=4.0, cell_size_m=0.02, charge=1.0,
              center=(0.0, 1.0), obstacles=[(2.0, 2.4, 0.0, 1.6)],
              gauges=[(1.0, 1.0)], solver='blastfoam', material='TNT')
    s2 = render_case(Case2D(**c2, vtk_surfaces=dict(
        surf, fields=[], obstacle_fields=['impulseMax'])))
    check('impulseMax 2D obstacles: emitted',
          'impulseMax' in fo_names(s2.files['system/controlDict']))
    # no obstacles patch and no other family: nothing asks for it
    no_obs = render_case(Case3D(**dict(base, obstacles=[]),
                                vtk_surfaces=dict(surf, fields=['p'])))
    check('impulseMax on obstacles without obstacles: no object',
          'impulseMax' not in fo_names(no_obs.files['system/controlDict']))
    # a resumed AMR leg: dropped like pMax / impulse (_FO_ACCUMULATED)
    check('impulseMax is an accumulator (writer and backend lists)',
          'impulseMax' in W._FO_ACCUMULATED and 'impulseMax' in B._FO_FIELDS)
    case_fo = Case3D(**base, vtk_surfaces=surf, vtk_volumes=vol)
    spec_fo = render_case(case_fo)
    spec_fo.fo_accumulators = False
    rc = W._controldict(spec_fo, case_fo)
    check('impulseMax, fo_accumulators off: no object, and the sections '
          'and obstacles sample p only',
          'impulseMax' not in fo_names(rc)
          and 'fields (p);' in norm(fo_block(rc, W.VTK_SECTIONS))
          and 'fields (p);' in norm(fo_block(rc, W.VTK_OBSTACLES)))


def time_of_peak_order_checks(specs):
    """OUT-4b F6 (owner, 2026-09-28): timeOfArrival shares the registered
    pMax with the pMax fieldMinMax and sets the time only where p > pMax
    (timeOfArrival.C execute()), so `arrival` must come BEFORE `pMax`."""
    print('\n  OUT-4b F6: arrival before pMax')
    for name, spec in sorted(specs.items()):
        if spec.dim < 2:
            continue
        names = fo_names(spec.files['system/controlDict'])
        check(f'F6 {name}: arrival before pMax and impulse',
              'arrival' in names and all(
                  names.index('arrival') < names.index(n)
                  for n in ('pMax', 'impulse') if n in names), str(names))


def obstacle_id_checks():
    """OUT-4b B3 (owner Q3): obstacleID is made on Windows - blastFoam
    never samples it, and no mesh, BC or patch changes (plan F5)."""
    from blastlab.solvers.foam import writer as W
    print('\n  OUT-4b: obstacle IDs (obstacleID)')
    for dim, cls, base in (
            (3, Case3D, dict(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.05,
                             charge=4.0, center=(0.5, 1.0, 1.0),
                             obstacles=[(1.2, 1.5, 0.6, 1.4, 0.0, 1.2),
                                        (1.6, 1.8, 0.2, 0.5, 0.0, 0.4)],
                             gauges=[(1.8, 1.0, 1.0)], n_snapshots=3,
                             solver='blastfoam', material='TNT')),
            (2, Case2D, dict(Lx=4.0, Ly=4.0, cell_size_m=0.02, charge=1.0,
                             center=(0.0, 1.0),
                             obstacles=[(2.0, 2.4, 0.0, 1.6)],
                             gauges=[(1.0, 1.0)], solver='blastfoam',
                             material='TNT'))):
        surf = {'on': True, 'mode': 'time', 'value': 0.0005, 'fields': [],
                'obstacle_fields': ['p', 'obstacleID'], 'planes': []}
        tagged = render_case(cls(**base, vtk_surfaces=surf))
        plain = render_case(cls(**base, vtk_surfaces=dict(
            surf, obstacle_fields=['p'])))
        check(f'obstacleID {dim}D: not sampled - vtkObstacles fields (p)',
              'fields (p);' in norm(fo_block(
                  tagged.files['system/controlDict'], W.VTK_OBSTACLES)))
        check(f'obstacleID {dim}D: every file byte-identical to p alone '
              f'(no mesh, BC or patch change)',
              tagged.files == plain.files)


def specs_time_name():
    """A profile stage whose t0 needs more digits than timePrecision."""
    import numpy as np
    from blastlab.solvers.foam import writer as W
    case = Case2D(Lx=1.0, Ly=2.0, cell_size_m=0.05, center=(0.0, 1.0),
                  init_mode='profile1d', profile_file_in=PROFILE_1D,
                  n_snapshots=1, eos='idealGas',
                  solver='blastfoam', material='TNT')
    real = W.profile_state

    def long_t0(c, s):
        st = real(c, s)
        if st is not None:
            st = dict(st, t0=0.0009331866336)
        return st

    W.profile_state = long_t0
    try:
        return render_case(case)
    finally:
        W.profile_state = real


def main():
    update = '--update' in sys.argv
    specs = {name: render_case(case) for name, case in cases().items()}
    # parallel golden variant: same 3D case rendered for 4 MPI ranks
    specs['case3d_c4_np4'] = render_case(cases()['case3d_c4'], n_procs=4)
    # parallel AMR: the loadBalance branch in writer._dynamicmeshdict
    # fires ONLY for n_procs > 1 AND amr, and had no golden at all - so
    # nothing would have noticed it changing. It pairs with the
    # addEmptyPatch mesh stage; see backend._mesh_stages.
    specs['case2d_planar_amr_np4'] = render_case(
        cases()['case2d_planar_amr'], n_procs=4)
    semantic_checks(specs)
    parallel_1d_checks(specs)
    profile_checks(specs)
    profile_amr_checks(specs)
    chain_eos_checks(specs)
    charge_scale_checks(specs)
    burst_point_checks()
    time_name_checks()
    deferred_state_checks()
    fresh_dir_checks()
    vtk_checks()
    gauge_checks()
    peak_impulse_checks()
    obstacle_id_checks()
    time_of_peak_order_checks(specs)
    golden(specs, update)
    print()
    if FAIL:
        print(f"FOAM WRITER: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM WRITER: PASS")


if __name__ == '__main__':
    main()
