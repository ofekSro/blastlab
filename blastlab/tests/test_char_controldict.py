"""Characterisation: the controlDict branches the foam goldens miss (Phase 10).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 10 splits
`solvers/foam/writer._controldict` into one function per section it
renders. `tests/foam_golden/` (test_foam_writer.py) pins the controlDict
of 21 reference cases, but none of them takes these branches:

- a fixed time step (`Case3D.fixed_dt` > 0: deltaT, adjustTimeStep no,
  writeControl runTime);
- the foam-side pMax/impulse accumulators switched off
  (`spec.fo_accumulators = False`, what backend._disable_fo_accumulators
  re-renders on a resume);
- a 3D live slice on another axis ('x', 'z') and at an explicit
  `slice_pos`, with and without the AMR sub-layer offset;
- an explicit live-sample cadence (`render_case(..., live_steps=N)`),
  1D and 2D;
- probes that may not be moved (`probe_adjust=False`), and a 1D case
  with no gauges at all.

Each variant's controlDict is pinned byte for byte under
`char_golden/controldict_<name>.txt`, written once from the code before
the split. A golden is never rewritten to make this pass.

Run:  cd blastlab/tests && python test_char_controldict.py [--update]
"""
import sys

import char_common as cc
from blastlab.core.case import Case1D, Case2D, Case3D     # noqa: E402
from blastlab.solvers.foam import writer                 # noqa: E402
from blastlab.solvers.foam.writer import render_case     # noqa: E402

CD = 'system/controlDict'


def _box3d(**kw):
    """The case3d_amr geometry of test_foam_writer (coarse, renders fast)."""
    base = dict(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.1, charge=8.0,
                center=(1.0, 1.0, 1.0), gauges=[(1.8, 1.0, 1.0)],
                n_snapshots=2, solver='blastfoam', material='TNT')
    base.update(kw)
    return Case3D(**base)


def _axi2d(**kw):
    """The case2d_axi_tnt geometry of test_foam_writer."""
    base = dict(Lx=4.0, Ly=4.0, cell_size_m=0.02, charge=1.0,
                center=(0.0, 1.0), gauges=[(1.0, 1.0)],
                solver='blastfoam', material='TNT')
    base.update(kw)
    return Case2D(**base)


def _sphere1d(**kw):
    """The case1d_tnt geometry of test_foam_writer."""
    base = dict(radius_m=5.0, charge_kg=1.0, cell_size_m=0.02,
                gauge_radii=[1.0, 2.0], solver='blastfoam', material='TNT')
    base.update(kw)
    return Case1D(**base)


def _check(name, text, must_contain):
    cc.check_text(f'controldict_{name}.txt', text)
    for frag in must_contain:
        assert frag in text, f'{name}: the variant no longer renders {frag!r}'


def test_fixed_dt_3d():
    text = render_case(_box3d(fixed_dt=2.0e-6)).files[CD]
    _check('fixed_dt_3d', text,
           ['adjustTimeStep  no;', 'writeControl    runTime;'])


def test_fo_accumulators_off_2d():
    case = _axi2d()
    spec = render_case(case)
    spec.fo_accumulators = False
    text = writer._controldict(spec, case)
    _check('fo_off_2d', text, ['timeOfArrival'])
    assert 'fieldMinMax' not in text, 'fo_off_2d: pMax still rendered'


def test_slice_x_at_pos_3d():
    text = render_case(_box3d(slice_axis='x', slice_pos=0.33)).files[CD]
    _check('slice_x_pos_3d', text, ['normal (1 0 0);'])


def test_slice_z_amr_3d():
    text = render_case(_box3d(slice_axis='z', slice_pos=1.4, amr_levels=2,
                              amr_display_level=0)).files[CD]
    _check('slice_z_amr_3d', text, ['normal (0 0 1);', 'cellCentres'])


def test_live_steps():
    _check('live_steps_1d', render_case(_sphere1d(), live_steps=7).files[CD],
           ['writeInterval   7;'])
    _check('live_steps_2d', render_case(_axi2d(), live_steps=3).files[CD],
           ['writeInterval   3;'])


def test_probes_fixed_and_absent_1d():
    _check('probe_fixed_1d',
           render_case(_sphere1d(probe_adjust=False)).files[CD],
           ['adjustLocations no;'])
    text = render_case(_sphere1d(gauge_radii=[])).files[CD]
    _check('no_gauges_1d', text, ['liveLine'])
    assert 'blastProbes' not in text, 'no_gauges_1d: probes rendered'


def main():
    return cc.run_main('CHAR CONTROLDICT', [
        test_fixed_dt_3d, test_fo_accumulators_off_2d,
        test_slice_x_at_pos_3d, test_slice_z_amr_3d, test_live_steps,
        test_probes_fixed_and_absent_1d])


if __name__ == '__main__':
    sys.exit(main())
