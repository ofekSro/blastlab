"""P2-25 (D16), services half: a model folder loads back into a Result.

  A  output/gauges.read_gauges: the 1D / 2D / 3D gauge TSVs round-trip to
     their written precision (values %.6e, radii 4 decimals, points 3),
     extras included
  B  services/model_folder.load_result on a tiny native 2D run written by
     write_all into a temp folder: the same G numbers (G2 dropped inside
     Wall 1), peaks within the TSV precision, the end-state field from
     profile_2d.npz; a 1D run likewise from profile.txt
  C  a folder without MODEL.json is a ValueError naming it; a blastFoam
     folder reads its foam\\0\\p (no WSL)

Everything runs in temp folders; the private settings file of
`char_common` keeps the real one untouched (CLAUDE.md 8.2).

Run:  cd blastlab/tests && python test_model_load.py   (or under pytest)
"""
import os
import queue
import shutil
import sys
import tempfile
import threading

import numpy as np

import char_common as cc

from blastlab.models.case import Case1D, Case2D, save_case     # noqa: E402
from blastlab.output import gauge_summary                      # noqa: E402
from blastlab.output.gauges import (read_gauges, save_gauges_1d,  # noqa: E402
                                    save_gauges_2d, save_gauges_3d)
from blastlab.services import model_folder as mf               # noqa: E402
from blastlab.solvers import jobs                              # noqa: E402
from blastlab.solvers.worker import GuiHooks                   # noqa: E402

#: %.6e keeps 7 significant digits: half a unit in the last place
REL = 5e-7


def _series(n, k, seed):
    rng = np.random.default_rng(seed)
    return [1e5 + 1e4 * rng.random(n) for _ in range(k)]


def _same(a, b, rel=REL):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return a.shape == b.shape and np.allclose(a, b, rtol=rel, atol=0.0)


def _round_trip(save, gauge_out, name):
    tmp = tempfile.mkdtemp(prefix='blastlab_load_a_')
    try:
        path = os.path.join(tmp, name)
        save(gauge_out, path)
        return read_gauges(path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_round_trip_1d():
    t = np.linspace(0.0, 1e-3, 40)
    g = dict(times=t, radii=[0.5, 1.25, 2.0], pressures=_series(40, 3, 1),
             temperatures=_series(40, 3, 2))
    got = _round_trip(save_gauges_1d, g, 'gauges_1d.txt')
    assert _same(got['times'][1:], t[1:]) and got['times'][0] == 0.0
    assert got['radii'] == [0.5, 1.25, 2.0], got['radii']
    assert 'points' not in got
    for key in ('pressures', 'temperatures'):
        assert len(got[key]) == 3
        assert all(_same(a, b) for a, b in zip(got[key], g[key])), key


def test_a_round_trip_2d():
    t = np.linspace(0.0, 1e-3, 25)
    pts = [(0.25, 0.6), (0.5, 0.6), (1.4, 0.3)]
    g = dict(times=t, points=pts, pressures=_series(25, 3, 3),
             speeds=_series(25, 3, 4), rhos=_series(25, 3, 5),
             overpressures=_series(25, 3, 6), impulses=_series(25, 3, 7))
    got = _round_trip(save_gauges_2d, g, 'gauges_2d.txt')
    assert got['points'] == pts, got['points']
    for key in ('pressures', 'speeds', 'rhos', 'overpressures', 'impulses'):
        assert len(got[key]) == 3, key
        assert all(_same(a, b) for a, b in zip(got[key], g[key])), key
    # the written precision: points carry 3 decimals
    g2 = dict(times=t, points=[(0.1234, 0.5678)], pressures=_series(25, 1, 8))
    got = _round_trip(save_gauges_2d, g2, 'gauges_2d.txt')
    assert np.allclose(got['points'][0], (0.1234, 0.5678), atol=5e-4)


def test_a_round_trip_3d_and_one_row():
    t = np.linspace(0.0, 1e-3, 12)
    pts = [(0.3, 0.57, 0.9), (0.5, 0.57, 0.6)]
    g = dict(times=t, points=pts, pressures=_series(12, 2, 9),
             dyn_pressures=_series(12, 2, 10))
    got = _round_trip(save_gauges_3d, g, 'gauges_3d.txt')
    assert got['points'] == pts
    assert all(_same(a, b) for a, b in zip(got['pressures'], g['pressures']))
    assert all(_same(a, b) for a, b in zip(got['dyn_pressures'],
                                           g['dyn_pressures']))
    one = dict(times=np.array([1e-4]), points=pts,
               pressures=[np.array([1.1e5]), np.array([1.2e5])])
    got = _round_trip(save_gauges_3d, one, 'gauges_3d.txt')
    assert got['times'].shape == (1,) and _same(got['pressures'][1], [1.2e5])


def test_a_not_a_gauge_tsv():
    tmp = tempfile.mkdtemp(prefix='blastlab_load_a_')
    try:
        path = os.path.join(tmp, 'x.txt')
        with open(path, 'w') as f:
            f.write('a\tb\n1\t2\n')
        try:
            read_gauges(path)
        except ValueError as exc:
            assert 'not a gauge TSV' in str(exc)
        else:
            raise AssertionError('no ValueError')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def write_run(case, runs, model='MODEL'):
    """prepare + bind_case + the run stage + write_all (test_model_folder's
    run_into). Returns (folder, the run's Result)."""
    folder = mf.prepare(runs, model, confirm=lambda text: True)
    bound = mf.bind_case(case, folder)
    hooks = GuiHooks(queue.Queue(), threading.Event())
    _label, solve = jobs.solve_stage(case.dim, bound)
    res = solve(hooks)
    mf.write_all(res, bound, case.dim, folder, dict(model=model),
                 log=lambda s: None)
    return folder, res


def case2d():
    """test_model_folder.case2d with a wall that drops G2 (inside it)."""
    return Case2D(Lx=0.6, Ly=1.2, cell_size_m=0.03, charge=0.5,
                  n_snapshots=1, t_end=2e-4, center=(0.0, 0.6),
                  record_frames=0,
                  bcs=dict(x_lo='reflect', x_hi='transmit', y_lo='reflect',
                           y_hi='transmit'),
                  obstacles=[(0.35, 0.47, 0.0, 0.3)],
                  gauges=[(0.25, 0.6), (0.41, 0.15), (0.5, 0.6)])


def test_b_native_2d_loads_back():
    runs = tempfile.mkdtemp(prefix='blastlab_load_b_')
    try:
        folder, res = write_run(case2d(), runs)
        got = mf.load_result(folder)
        want_nums = gauge_summary.entered_numbers(res.gauges['points'],
                                                  res.meta['gauges'])
        nums = gauge_summary.entered_numbers(got.gauges['points'],
                                             got.meta['gauges'])
        assert want_nums == [1, 3] and nums == want_nums, (nums, want_nums)
        assert gauge_summary.dropped_numbers(got.gauges['points'],
                                             got.meta['gauges']) == [2]
        assert got.meta['gauges_dropped'] == [[2, 'inside Wall 1']], \
            got.meta['gauges_dropped']
        peaks = [float(np.max(p)) for p in got.gauges['pressures']]
        want = [float(np.max(p)) for p in res.gauges['pressures']]
        assert np.allclose(peaks, want, rtol=REL, atol=0.0), (peaks, want)
        assert _same(got.gauges['times'][1:], res.gauges['times'][1:])
        assert got.stop_reason == res.stop_reason and not got.stopped_early
        # the end state, from profile_2d.npz
        (label, field), = got.snapshots.items()
        assert label.endswith('(final)'), label
        assert field['p'].shape == res.meta['final_state']['p'].shape
        assert np.array_equal(field['p'], res.meta['final_state']['p'])
        assert got.meta['solid'].shape == field['p'].shape
        assert got.meta['solid'].any()                  # Wall 1
        assert got.meta['model_dir'] == folder
        assert got.meta['geometry'] == 'axisymmetric'
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_b_native_1d_loads_back():
    runs = tempfile.mkdtemp(prefix='blastlab_load_b_')
    try:
        case = Case1D(radius_m=1.0, charge_kg=0.5, cell_size_m=0.01,
                      n_snapshots=1, t_end=3e-4, gauge_radii=[0.5, 1.5])
        folder, res = write_run(case, runs)
        got = mf.load_result(folder)
        # the radius the solver snapped G1 to, to the TSV's 4 decimals
        assert np.allclose(got.gauges['radii'], res.gauges['radii'],
                           atol=5e-5) and len(got.gauges['radii']) == 1, \
            (got.gauges['radii'], res.gauges['radii'])
        assert got.meta['gauges_dropped'] == [[2, 'outside the domain']]
        assert np.allclose(np.max(got.gauges['pressures'][0]),
                           np.max(res.gauges['pressures'][0]), rtol=REL)
        (label, field), = got.snapshots.items()
        assert np.allclose(field['p'], res.meta['final_profile']['p'],
                           rtol=1e-9)
        assert got.meta['radius_m'] == 1.0 and got.meta['charge_kg'] == 0.5
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_c_no_model_json_is_a_value_error():
    tmp = tempfile.mkdtemp(prefix='blastlab_load_c_')
    try:
        try:
            mf.load_result(tmp)
        except ValueError as exc:
            assert tmp in str(exc) and 'MODEL.json' in str(exc), str(exc)
        else:
            raise AssertionError('no ValueError')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


UNIFORM_P = """FoamFile
{
    format      ascii;
    class       volScalarField;
    object      p;
}
dimensions      [1 -1 -2 0 0 0 0];
internalField   uniform 101298;
boundaryField
{
}
"""


def test_c_foam_copy_field():
    """A blastFoam planar 2D folder (no profile): the foam\\ copy's 0\\p
    on the display grid; the gauges still load without it."""
    tmp = tempfile.mkdtemp(prefix='blastlab_load_c_')
    try:
        case = Case2D(geometry='planar', Lx=1.0, Ly=0.8, cell_size_m=0.05,
                      charge=0.5, center=(0.5, 0.4), gauges=[(0.8, 0.4)],
                      solver='blastfoam', material='TNT')
        save_case(case, os.path.join(tmp, mf.CASE_FILE))
        got = mf.load_result(tmp)
        assert got.snapshots == {} and got.gauges['pressures'] == []
        os.makedirs(os.path.join(tmp, mf.FOAM_DIR, '0'))
        with open(os.path.join(tmp, mf.FOAM_DIR, '0', 'p'), 'w') as f:
            f.write(UNIFORM_P)
        got = mf.load_result(tmp)
        (label, field), = got.snapshots.items()
        from blastlab.solvers.foam import writer
        spec = writer.render_case(case)
        assert field['p'].shape == (spec.nx, spec.ny), field['p'].shape
        assert np.all(field['p'] == 101298.0) and 'initial' in label
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


TESTS = [test_a_round_trip_1d, test_a_round_trip_2d,
         test_a_round_trip_3d_and_one_row, test_a_not_a_gauge_tsv,
         test_b_native_2d_loads_back, test_b_native_1d_loads_back,
         test_c_no_model_json_is_a_value_error, test_c_foam_copy_field]


if __name__ == '__main__':
    sys.exit(cc.run_main('MODEL LOAD', TESTS))
