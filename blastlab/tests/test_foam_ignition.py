"""P1-23 / P2-22: the ignition seed blastFoam is handed at t = 0.

blastFoam lights a detonation point by testing cell CENTRES,
`mag(C - pt) < radius` (guide 5.6.1, p. 71, `radii`; the installed
`activationModel.C:111-137`), and dies at start-up with "No cells will
be activated" when none passes. These checks pin what the writer seeds
today on the three cases that died at t = 0 on 2026-10-11:

  P1-23  axisymmetric 10 x 10 m, 0.04 m cell, 100 kg C4 at (0, 0), zones
         level 1 + level 2 (`/root/blastlab_runs/20261011-081913_2d_p61324-00`)
  F05    planar 4 x 4 m, 0.1 m cell, AMR 3, 100 kg/m TNT at (2, 2)
  F06    3D 1.5 m cube, 0.05 m cell, AMR 2, 20 kg TNT at the centre
         (the two GUI-14 QA cases, `_qa_ui_harness.py` F2D_AMR / F3D_AMR)

The golden `radii` lines are pinned byte for byte by test_foam_writer.py
and are not pinned twice here. Then (A2) the run-time fit on synthetic
t = 0 centres that reproduce what those three runs' 0/C hold, and the
backend hook on a temp case dir. No WSL.

Run:  cd blastlab/tests && python test_foam_ignition.py
"""

import os
import re
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import Case2D, Case3D                  # noqa: E402
from blastlab.solvers.foam import writer                       # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def p123_case(**kw):
    """The P1-23 case as its case.json has it (t_end aside)."""
    base = dict(
        geometry='axisymmetric', Lx=10.0, Ly=10.0, cell_size_m=0.04,
        charge=100.0, center=(0.0, 0.0),
        bcs=dict(x_lo='reflect', x_hi='terminate', y_lo='reflect',
                 y_hi='transmit'),
        obstacles=[(5.0, 5.5, 0.0, 4.0), (7.5, 10.0, 0.0, 10.0)],
        refine_zones=[(0.0, 7.5, 0.0, 6.0, 1), (3.5, 7.5, 0.1, 5.9, 2)],
        charge_refine='zone', n_snapshots=6,
        gauges=[(7.49, y) for y in (0.1, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0,
                                    6.0)],
        solver='blastfoam', material='C4')
    base.update(kw)
    return Case2D(**base)


def f05_case(**kw):
    """`_qa_ui_harness.py` F2D_AMR."""
    base = dict(
        geometry='planar', Lx=4.0, Ly=4.0, cell_size_m=0.1, charge=100.0,
        center=(2.0, 2.0), gauges=[(3.2, 2.0)], n_snapshots=2,
        record_frames=60, solver='blastfoam', material='TNT', amr_levels=3,
        bcs=dict(x_lo='terminate', x_hi='terminate', y_lo='terminate',
                 y_hi='terminate'))
    base.update(kw)
    return Case2D(**base)


def f06_case(**kw):
    """`_qa_ui_harness.py` F3D_AMR."""
    base = dict(
        Lx=1.5, Ly=1.5, Lz=1.5, cell_size_m=0.05, charge=20.0,
        center=(0.75, 0.75, 0.75), gauges=[(1.25, 0.75, 0.75)],
        amr_levels=2, amr_display_level=1, amr_max_cells=150_000,
        n_snapshots=2, record_frames=30, solver='blastfoam', material='TNT',
        bcs={s: 'terminate' for s in ('x_lo', 'x_hi', 'y_lo', 'y_hi',
                                      'z_lo', 'z_hi')})
    base.update(kw)
    return Case3D(**base)


def written_radii(spec):
    """The `radii` list of the rendered phaseProperties, in metres."""
    m = re.search(r'^\s*radii \(([^)]*)\);',
                  spec.files['constant/phaseProperties'], re.M)
    return [float(v) for v in m.group(1).split()] if m else None


def seed_checks():
    """A1: today's written radius and charge spacing, before any change."""
    print("\nA1 - the seed as written today")
    for name, case, want in (('P1-23', p123_case(), 0.009),
                             ('F05', f05_case(), 0.01125),
                             ('F06', f06_case(), 0.01125)):
        spec = writer.render_case(case)
        r = written_radii(spec)
        check(f'{name}: one radius of {want * 1e3:g} mm is written',
              r is not None and len(r) == 1 and abs(r[0] - want) < 1e-12,
              f'{r}')
    sp = writer.render_case(p123_case())
    check('P1-23: the charge spacing is the global fine cell, 0.01 m',
          abs(sp.dx_charge - 0.01) < 1e-12, f'{sp.dx_charge}')


def p123_centres():
    """The t = 0 cells next to the P1-23 point (0, 0, 0), as measured in
    its 0/C: level-1 rows (0.02 m) whose axis cell refineMesh cut at the
    centroid, so the radial centres sit at 17.78 / 33.77 / 50.66 mm.
    Nearest (17.78, 10.0) mm = 20.39 mm, next (17.78, 30.0) = 34.87 mm."""
    xs = [0.01778, 0.03377, 0.05066, 0.07, 0.09]
    ys = [0.01, 0.03, 0.05, 0.07]
    return np.array([(x, y, 0.0) for x in xs for y in ys])


def f05_centres():
    """F05's t = 0 cells around (2, 2, 0): a 2 x 2 block of level-1 cells
    (0.05 m) on the point, ringed by level-2 cells (0.025 m) where the
    estimator flagged. 4 centres at 35.36 mm, next at 63.74 mm."""
    pts = [(2.0 + sx * 0.025, 2.0 + sy * 0.025, 0.0)
           for sx in (-1, 1) for sy in (-1, 1)]
    for a in (-0.0625, 0.0625):
        for b in (-0.0375, -0.0125, 0.0125, 0.0375):
            pts += [(2.0 + a, 2.0 + b, 0.0), (2.0 + b, 2.0 + a, 0.0)]
    return np.array(pts)


def f06_centres():
    """F06's level-0 cells (0.05 m) round the node (0.75, 0.75, 0.75):
    8 centres at 43.30 mm, the next shell at 82.92 mm."""
    off = (-0.075, -0.025, 0.025, 0.075)
    return np.array([(0.75 + a, 0.75 + b, 0.75 + c)
                     for a in off for b in off for c in off])


def fit_checks():
    """A2: a default radius that lights no centre is fitted to the
    nearest shell, one that lights a cell is left alone."""
    print("\nA2 - fitting the radius to the t = 0 mesh")
    for name, pt, r0, C, lo, hi, n_want in (
            ('P1-23', (0.0, 0.0, 0.0), 0.009, p123_centres(),
             0.02039, 0.03487, 1),
            ('F05', (2.0, 2.0, 0.0), 0.01125, f05_centres(),
             0.03536, 0.06374, 4),
            ('F06', (0.75, 0.75, 0.75), 0.01125, f06_centres(),
             0.04330, 0.08292, 8)):
        new, fits = writer.fit_det_radii([pt], [r0], C)
        d = np.linalg.norm(C - np.asarray(pt), axis=1)
        lit = int((d < new[0]).sum())
        check(f'{name}: {r0 * 1e3:g} mm lights nothing, so it is fitted',
              len(fits) == 1 and fits[0][0] == 0 and fits[0][1] == r0,
              f'{fits}')
        check(f'{name}: fitted radius {new[0] * 1e3:.2f} mm lies in '
              f'({lo * 1e3:.2f}, {hi * 1e3:.2f}) mm and lights {n_want}',
              lo < new[0] < hi and lit == n_want
              and fits and fits[0][3] == n_want, f'{new} lit {lit}')
        check(f'{name}: the fit reports the nearest centre',
              fits and abs(fits[0][4] - d.min()) < 1e-12, f'{fits}')
    # a radius that already lights a cell, and the findCell branch
    for r in (0.025, 0.0):
        new, fits = writer.fit_det_radii([(0.0, 0.0, 0.0)], [r],
                                         p123_centres())
        check(f'{r * 1e3:g} mm comes back unchanged, no fit',
              new == [r] and fits == [], f'{new} {fits}')
    # two points: only the one that lights nothing moves
    new, fits = writer.fit_det_radii(
        [(0.0, 0.0, 0.0), (0.05066, 0.05, 0.0)], [0.009, 0.009],
        p123_centres())
    check('two points: only the dark one is fitted',
          [f[0] for f in fits] == [0] and new[1] == 0.009, f'{fits}')
    # the rewritten text differs on the radii line only
    text = writer.render_case(p123_case()).files['constant/phaseProperties']
    out = writer.with_det_radii(text, [0.0275])
    diff = [(a, b) for a, b in zip(text.splitlines(), out.splitlines())
            if a != b]
    check('the rewrite changes the radii line and nothing else',
          len(text.splitlines()) == len(out.splitlines())
          and len(diff) == 1 and diff[0][0].strip() == 'radii (0.009);'
          and diff[0][1] == diff[0][0].replace('0.009', '0.0275'),
          f'{diff}')
    check('written_det_radii reads the rewritten value',
          writer.written_det_radii(out) == [0.0275])


def write_centres(case_dir, C, time='0'):
    """A 0/C file as writeCellCentres writes it (ascii)."""
    d = os.path.join(case_dir, time)
    os.makedirs(d, exist_ok=True)
    rows = '\n'.join(f'({x:.17g} {y:.17g} {z:.17g})' for x, y, z in C)
    with open(os.path.join(d, 'C'), 'w', newline='\n') as f:
        f.write('FoamFile { format ascii; class volVectorField; '
                'object C; }\ndimensions [0 1 0 0 0 0 0];\n'
                f'internalField   nonuniform List<vector> \n{len(C)}\n(\n'
                f'{rows}\n)\n;\nboundaryField {{ }}\n')


class _Hooks:
    def __init__(self):
        self.msgs = []

    def log(self, m):
        self.msgs.append(m)


def staged_spec(case, C):
    """`case` rendered and written into a temp dir with `C` as its 0/C,
    as the mesh stages leave it. Returns (spec, phaseProperties path)."""
    spec = writer.render_case(case)
    spec.case_unc = tempfile.mkdtemp(prefix='blastlab_ign_')
    writer._write_files(spec, list(spec.files))
    write_centres(spec.case_unc, C)
    return spec, os.path.join(spec.case_unc, 'constant', 'phaseProperties')


def read_text(path):
    with open(path, encoding='ascii', newline='') as f:
        return f.read()


def hook_checks():
    """A2: the run-time hook rewrites the file on disk and says so."""
    from blastlab.solvers.foam import backend
    print("\nA2 - the run-time hook (backend._fit_ignition)")
    spec, pp = staged_spec(p123_case(), p123_centres())
    before = read_text(pp)
    h = _Hooks()
    backend._fit_ignition(spec, h)
    after = read_text(pp)
    r = writer.written_det_radii(after)
    check('P1-23: the file on disk carries the fitted radius',
          r is not None and 0.02039 < r[0] < 0.03487
          and after == spec.files['constant/phaseProperties'], f'{r}')
    check('P1-23: on disk, only the radii line changed',
          sum(a != b for a, b in zip(before.splitlines(),
                                     after.splitlines())) == 1)
    notes = [m for m in h.msgs if '[note]' in m]
    check('P1-23: one note names point 1, both radii and 1 cell lit',
          len(notes) == 1 and 'detonation point 1' in notes[0]
          and '9 mm' in notes[0] and f'{r[0] * 1e3:.4g} mm' in notes[0]
          and '1 cell(s) lit' in notes[0], f'{h.msgs}')
    shutil.rmtree(spec.case_unc, ignore_errors=True)
    # a radius that lights a cell: the file stays byte-identical
    lit = p123_centres()
    lit[0] = (0.005, 0.005, 0.0)
    spec, pp = staged_spec(p123_case(), lit)
    before = read_text(pp)
    h = _Hooks()
    backend._fit_ignition(spec, h)
    check('a radius that lights a cell: file unchanged, no note',
          read_text(pp) == before and not h.msgs, f'{h.msgs}')
    shutil.rmtree(spec.case_unc, ignore_errors=True)


def main():
    seed_checks()
    fit_checks()
    hook_checks()
    print()
    if FAIL:
        print(f"FOAM IGNITION: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM IGNITION: PASS")


if __name__ == '__main__':
    main()
