"""blastFoam case-writer tests: semantic checks + golden-text pinning.
Pure text - no WSL required.

Run:  python test_foam_writer.py             compare against foam_golden/
      python test_foam_writer.py --update    regenerate the golden files
"""

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
    }


def semantic_checks(specs):
    s1 = specs['case1d_tnt']
    m_tnt = MATERIALS['TNT']
    r_exp = charge_radius(1.0, m_tnt)
    dx = r_exp / MIN_EXP_CELLS          # 0.02 is coarser -> refined
    check('1d: dx refined to r_exp/MIN_EXP_CELLS',
          abs(s1.dx - dx) < 1e-12, f'{s1.dx} vs {dx}')
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
    check('two charges: dx resolves the smaller charge',
          abs(s3t.dx - charge_radius(2.0, m_tnt) / MIN_EXP_CELLS) < 1e-12)
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


def main():
    update = '--update' in sys.argv
    specs = {name: render_case(case) for name, case in cases().items()}
    # parallel golden variant: same 3D case rendered for 4 MPI ranks
    specs['case3d_c4_np4'] = render_case(cases()['case3d_c4'], n_procs=4)
    semantic_checks(specs)
    golden(specs, update)
    print()
    if FAIL:
        print(f"FOAM WRITER: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM WRITER: PASS")


if __name__ == '__main__':
    main()
