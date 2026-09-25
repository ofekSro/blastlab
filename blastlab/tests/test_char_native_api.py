"""Characterisation: the native solvers through the Case API (Phase 0).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 0. `test_regression.py` pins
the legacy `run_blast*` entry points byte for byte; this pins what it does
not see - the `Case` -> `solvers.get_solver(dim, 'native')` -> `Result`
path the GUI and the chain use: the gauge arrays exactly, `stop_reason`,
the key set of `Result.meta` with the dtype/shape of every array in it,
and the snapshot labels.

The three cases are the smallest baseline cases of `make_baseline.py`
(1D JWL charge; 2D axisymmetric charge + ground + obstacle; 3D box +
obstacle) re-expressed as Case1D/Case2D/Case3D. Everything not given here
is the dataclass default, so these runs also pin the defaults' effect.

Run:  cd blastlab/tests && python test_char_native_api.py [--update]
"""
import sys

import numpy as np

import char_common as cc
from blastlab.core.case import Case1D, Case2D, Case3D   # noqa: E402
from blastlab.solvers import get_solver                   # noqa: E402
from blastlab.solvers.hooks import RunHooks               # noqa: E402
from blastlab.models.meta import (META_KEYS_1D, META_KEYS_2D,  # noqa: E402
                                  META_KEYS_3D)

#: Phase 8 (docs/ARCHITECTURE_REVIEW.md): the documented Result.meta keys
META_KEYS = {'1d': META_KEYS_1D, '2d': META_KEYS_2D, '3d': META_KEYS_3D}

CASES = {
    '1d': Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.02, eos='JWL',
                 gauge_radii=[0.5, 1.0, 1.5]),
    '2d': Case2D(geometry='axisymmetric', Lx=1.2, Ly=1.6, cell_size_m=0.02,
                 charge=1.0, center=(0.0, 0.7),
                 bcs=dict(x_lo='reflect', x_hi='terminate',
                          y_lo='reflect', y_hi='terminate'),
                 obstacles=[(0.7, 0.9, 0.2, 0.5)], eos='idealGas',
                 n_snapshots=2, gauges=[(0.5, 0.7), (0.4, 0.2)]),
    '3d': Case3D(Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.025, charge=8.0,
                 center=(0.5, 0.5, 0.5),
                 obstacles=[(0.62, 0.72, 0.4, 0.6, 0.3, 0.7)],
                 eos='idealGas', n_snapshots=1,
                 bcs=dict(x_lo='terminate', x_hi='terminate',
                          y_lo='terminate', y_hi='terminate',
                          z_lo='reflect', z_hi='terminate'),
                 gauges=[(0.85, 0.5, 0.5), (0.5, 0.85, 0.5)]),
}


def describe(v):
    """Type/dtype/shape of a meta value; scalar values by repr."""
    if isinstance(v, np.ndarray):
        return {'ndarray': str(v.dtype), 'shape': list(v.shape)}
    if isinstance(v, dict):
        return {'dict': {str(k): describe(x) for k, x in v.items()}}
    if isinstance(v, (list, tuple)):
        if v and all(isinstance(x, np.ndarray) for x in v):
            return {'arrays': len(v),
                    'dtypes': sorted({str(x.dtype) for x in v}),
                    'shapes': sorted({str(tuple(x.shape)) for x in v})}
        return {type(v).__name__: [describe(x) for x in v]}
    if isinstance(v, np.generic):
        return {type(v).__name__: repr(v.item())}
    if v is None or isinstance(v, (bool, int, float, str)):
        return {type(v).__name__: repr(v)}
    return {'type': type(v).__name__}


def gauge_arrays(gauges):
    """The Result's gauge dict as flat npz arrays: list-of-array entries
    become `<key>_<i>`, everything else one array."""
    out = {}
    for k, v in gauges.items():
        if isinstance(v, (list, tuple)) and v \
                and all(isinstance(x, np.ndarray) for x in v):
            for i, x in enumerate(v):
                out[f'{k}_{i}'] = x
        else:
            out[k] = np.asarray(v)
    return out


def run(key):
    case = CASES[key]
    return get_solver(case.dim, 'native')(case, RunHooks())


def characterise(key):
    res = run(key)
    # Phase 8: the documented contract is exactly what the run returns
    want = META_KEYS[key]
    assert set(res.meta) == want, \
        f'{key}: meta keys differ from models.meta: {sorted(set(res.meta) ^ want)}'
    cc.check_npz(f'native_{key}_gauges.npz', gauge_arrays(res.gauges))
    cc.check_json(f'native_{key}_result.json', dict(
        stop_reason=res.stop_reason,
        stopped_early=res.stopped_early,
        gauge_keys=sorted(res.gauges),
        meta_keys=sorted(res.meta),
        meta={k: describe(res.meta[k]) for k in sorted(res.meta)},
        snapshot_labels=list(res.snapshots),
        snapshot_fields={lbl: describe(s) for lbl, s in
                         res.snapshots.items()},
    ))


def test_native_1d():
    characterise('1d')


def test_native_2d_axisym_obstacle():
    characterise('2d')


def test_native_3d_box_obstacle():
    characterise('3d')


def main():
    return cc.run_main('CHAR NATIVE API', [
        test_native_1d, test_native_2d_axisym_obstacle,
        test_native_3d_box_obstacle])


if __name__ == '__main__':
    sys.exit(main())
