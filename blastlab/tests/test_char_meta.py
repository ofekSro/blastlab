"""The `Result.meta` contract (`models/meta.py`) and its accessors (Phase 8).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 8 (finding F3).

  * The documented key sets agree with what Phase 0 recorded
    (`char_golden/native_*_result.json`) and with the blastFoam backend's
    sets as documented. (`test_char_native_api.py` asserts the same on a
    fresh run.)
  * Every accessor returns what the panels' literal reads returned -
    the same objects, the same values - over the native Phase 0 runs'
    meta and over a hand-built blastFoam-shaped meta.
  * With any ONE key missing, an accessor fails exactly as the literal
    reads did (same exception type and message) or succeeds exactly as
    they did. The literal reads are copied below verbatim from the panels
    as they were before Phase 8 (`OLD_*`), so this stays a comparison
    against the old behaviour after the panels changed.

Runs under pytest and as a script.

Run:  cd blastlab/tests && python test_char_meta.py
"""
import sys

import numpy as np

import char_common as cc
from blastlab.core.constants import anim_scale_from_label       # noqa: E402
from blastlab.core.grid import make_geometry, make_grid          # noqa: E402
from blastlab.models import meta as M                            # noqa: E402

# ── the literal reads as the panels had them before Phase 8 ──────────────


def OLD_qt_fields_2d(meta):          # ui/results_fields.py select_field, dim 2
    solid, xf, yf = meta['solid'], meta['x_face'], meta['y_face']
    return xf, yf, solid, None


def OLD_qt_fields_3d(meta, xz):      # ui/results_fields.py select_field, dim 3
    j0, k0 = meta['j0'], meta['k0']
    if xz:
        sl = np.s_[:, j0, :]
        xf, yf = meta['x_face'], meta['z_face']
        pos = meta['y_c'][j0]
    else:
        sl = np.s_[:, :, k0]
        xf, yf = meta['x_face'], meta['y_face']
        pos = meta['z_c'][k0]
    solid = meta['solid'][sl]
    return xf, yf, solid, sl, pos


def OLD_tk_fields_3d(meta, xz):      # gui/results_panel.py _draw_field, dim 3
    j0, k0 = meta['j0'], meta['k0']
    if xz:
        sl = np.s_[:, j0, :]
        solid = meta['solid'][sl]
        xf, yf = meta['x_face'], meta['z_face']
        pos = meta['y_c'][j0]
    else:
        sl = np.s_[:, :, k0]
        solid = meta['solid'][sl]
        xf, yf = meta['x_face'], meta['y_face']
        pos = meta['z_c'][k0]
    return xf, yf, solid, sl, pos


def OLD_anim(meta):                  # ui/results_anim.py plane_geometry
    if 'z_face' in meta:
        s_ax = meta.get('slice_axis', 'y')
        s0 = meta.get('s0', meta['j0'])
        xf, yf = {'x': (meta['y_face'], meta['z_face']),
                  'y': (meta['x_face'], meta['z_face']),
                  'z': (meta['x_face'], meta['y_face'])}[s_ax]
        sl = tuple(s0 if a == 'xyz'.index(s_ax) else slice(None)
                   for a in range(3))
        return xf, yf, meta['solid'][sl], s_ax, s0, sl, \
            meta[f'{s_ax}_c'][s0]
    return meta['x_face'], meta['y_face'], meta['solid'], None, None, \
        None, None


def OLD_frames(meta):                # ui/results_anim.py AnimView._frames
    frames = meta.get('frames')
    if not frames or not len(frames['pressures']):
        return None
    return frames


def OLD_anim_scale(meta):            # ui/results_anim.py AnimView.set_result
    return (anim_scale_from_label(meta.get('anim_scale') or 'run'),
            meta.get('anim_clim'))


def OLD_charge_1d(meta):             # figure_results_1d(res.meta[...] x3)
    return meta['eos'], meta['charge_kg'], meta['radius_m']


def OLD_charge_gauges(meta):         # figure_gauges_1d(res.meta[...] x2)
    return meta['charge_kg'], meta['eos']


# ── the accessors, shaped like the old reads ─────────────────────────────
def NEW_qt_fields_2d(meta):
    g = M.slice_geometry(meta, 'grid')
    return g.xf, g.yf, g.solid, g.sl


def NEW_fields_3d(meta, xz):
    g = M.slice_geometry(meta, 'x-z' if xz else 'x-y')
    return g.xf, g.yf, g.solid, g.sl, g.coord


def NEW_anim(meta):
    return tuple(M.slice_geometry(meta, 'recorded'))


def NEW_frames(meta):
    return M.frames_of(meta)


def NEW_anim_scale(meta):
    return tuple(M.anim_scale_of(meta))


def NEW_charge_1d(meta):
    return tuple(M.charge_label(meta))


def NEW_charge_gauges(meta):
    c = M.charge_label(meta, radius=False)
    return c.charge_kg, c.eos


PAIRS_2D = [('fields 2D', OLD_qt_fields_2d, NEW_qt_fields_2d),
            ('anim', OLD_anim, NEW_anim),
            ('frames', OLD_frames, NEW_frames),
            ('anim scale', OLD_anim_scale, NEW_anim_scale)]
PAIRS_3D = [('qt fields x-z', lambda m: OLD_qt_fields_3d(m, True),
             lambda m: NEW_fields_3d(m, True)),
            ('qt fields x-y', lambda m: OLD_qt_fields_3d(m, False),
             lambda m: NEW_fields_3d(m, False)),
            ('tk fields x-z', lambda m: OLD_tk_fields_3d(m, True),
             lambda m: NEW_fields_3d(m, True)),
            ('tk fields x-y', lambda m: OLD_tk_fields_3d(m, False),
             lambda m: NEW_fields_3d(m, False)),
            ('anim', OLD_anim, NEW_anim),
            ('frames', OLD_frames, NEW_frames),
            ('anim scale', OLD_anim_scale, NEW_anim_scale)]
PAIRS_1D = [('charge 1D', OLD_charge_1d, NEW_charge_1d),
            ('charge gauges', OLD_charge_gauges, NEW_charge_gauges)]


def _same(a, b):
    """Identical results: the same objects for arrays taken from meta,
    equal values for what was computed from them."""
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a is b
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return (type(a) is type(b) and a.dtype == b.dtype
                and a.shape == b.shape and np.array_equal(a, b))
    return type(a) is type(b) and a == b


def _call(fn, meta):
    try:
        return 'ok', fn(meta)
    except Exception as exc:                   # noqa: BLE001 - the point
        return 'raises', f'{type(exc).__name__}: {exc}'


def check_pairs(name, meta, pairs):
    """Old and new agree on the full meta and with each key removed."""
    bad = []
    variants = [('(full)', meta)] + [
        (f'-{k}', {x: v for x, v in meta.items() if x != k})
        for k in sorted(meta)]
    for vname, m in variants:
        for what, old, new in pairs:
            (ko, vo), (kn, vn) = _call(old, m), _call(new, m)
            same = ko == kn and (vo == vn if ko == 'raises'
                                 else _same(vo, vn))
            if not same:
                bad.append(f'{name} {vname} {what}: old {ko} {vo!r:.80} '
                           f'new {kn} {vn!r:.80}')
    assert not bad, '\n'.join(bad[:20])


# ── metas ────────────────────────────────────────────────────────────────
def native_meta(key):
    from test_char_native_api import run
    return run(key).meta


def foam_meta_2d():
    """A blastFoam-shaped 2D meta, hand-built with finalize_2d's keys."""
    g = make_geometry('axisymmetric', 0.6, 0.8, 0.1)
    nx, ny = g['Nx'], g['Ny']
    p = np.full((nx, ny), 101325.0)
    return dict(x_c=g['x_c'], y_c=g['y_c'], x_face=g['x_face'],
                y_face=g['y_face'], solid=np.zeros((nx, ny), bool),
                geometry='axisymmetric', Lx=0.6, Ly=0.8, dx=0.1, eos='JWL',
                bcs={}, obstacles=[], charge=1.0, charge_center=(0.0, 0.4),
                r_exp=0.05, from_profile=False, solver='blastfoam',
                material='TNT', conserved=None, gauges=[(0.3, 0.4)],
                case_dir='/root/blastlab_runs/x', refine=None,
                p_peak=p, impulse=p * 0, peak_source='foam',
                final_state=dict(t=1e-4, p=p), trigger_gauge=None,
                frames=dict(times=np.array([0.0, 1e-4]),
                            pressures=[p.astype(np.float32)] * 2,
                            levels=[np.zeros((nx, ny), int)] * 2))


def foam_meta_3d(slice_axis='y'):
    """A blastFoam-shaped 3D meta, hand-built with finalize_3d's keys."""
    grid = make_grid(0.8, 0.6, 0.4, 0.1)
    x_c, y_c, z_c = grid['x_c'], grid['y_c'], grid['z_c']
    nx, ny, nz = len(x_c), len(y_c), len(z_c)
    solid = np.zeros((nx, ny, nz), bool)
    solid[2:4, 1:3, 0:2] = True
    j0, k0 = ny // 2, nz // 2
    s0 = {'x': nx // 2, 'y': j0, 'z': k0}[slice_axis]
    p = np.full((nx, ny, nz), 101325.0, np.float32)
    return dict(x_c=x_c, y_c=y_c, z_c=z_c, x_face=grid['x_face'],
                y_face=grid['y_face'], z_face=grid['z_face'], j0=j0, k0=k0,
                slice_axis=slice_axis, s0=s0, solid=solid, Lx=0.8, Ly=0.6,
                Lz=0.4, dx=0.1, eos='JWL', bcs={}, obstacles=[],
                charge=1.0, charge_center=(0.4, 0.3, 0.2), r_exp=0.05,
                r_src=0.05, from_profile=None, solver='blastfoam',
                material='TNT', conserved=None, gauges=[],
                case_dir='/root/blastlab_runs/x', refine=None, p_peak=p,
                impulse=p * 0, peak_source='foam', trigger_gauge=None,
                anim_scale='fixed (manual)', anim_clim=(0.0, 40.0),
                frames=dict(times=np.array([0.0]), pressures=[p[:, j0, :]]))


def foam_meta_1d():
    """finalize_1d's keys, hand-built."""
    return dict(final_profile={}, r=np.linspace(0, 1, 5), radius_m=1.0,
                charge_kg=2.0, eos='JWL', r_exp=0.06, solver='blastfoam',
                material='TNT', conserved=None, case_dir='/root/x')


# ── tests ────────────────────────────────────────────────────────────────
def test_key_sets_match_phase0_goldens():
    for key, want in (('1d', M.META_KEYS_1D), ('2d', M.META_KEYS_2D),
                      ('3d', M.META_KEYS_3D)):
        got = set(cc.load_json(f'native_{key}_result.json')['meta_keys'])
        assert got == set(want), f'{key}: {sorted(got ^ set(want))}'


def test_foam_key_sets_contain_native():
    for native, foam in ((M.META_KEYS_1D, M.META_FOAM_KEYS_1D),
                         (M.META_KEYS_2D, M.META_FOAM_KEYS_2D),
                         (M.META_KEYS_3D, M.META_FOAM_KEYS_3D)):
        assert native <= foam
    assert set(foam_meta_1d()) == M.META_FOAM_KEYS_1D
    assert set(foam_meta_2d()) == M.META_FOAM_KEYS_2D
    assert set(foam_meta_3d()) - M.META_HOST_KEYS == M.META_FOAM_KEYS_3D


def test_accessors_native_1d():
    meta = native_meta('1d')
    check_pairs('native 1D', meta, PAIRS_1D)
    c = M.charge_label(meta)
    assert (c.eos, c.charge_kg, c.radius_m) == ('JWL', 1.0, 2.0)
    assert M.charge_label(meta, radius=False).radius_m is None


def test_accessors_native_2d():
    meta = native_meta('2d')
    check_pairs('native 2D', meta, PAIRS_2D)
    g = M.slice_geometry(meta, 'grid')
    assert g.xf is meta['x_face'] and g.solid is meta['solid']
    assert M.slice_geometry(meta) == M.slice_geometry(meta, 'grid')
    assert M.frames_of(meta) is meta['frames']
    assert M.anim_scale_of(meta) == ('run', None)


def test_accessors_native_3d():
    meta = native_meta('3d')
    check_pairs('native 3D', meta, PAIRS_3D)
    g = M.slice_geometry(meta, 'x-z')
    assert (g.axis, g.index) == ('y', meta['j0'])
    assert g.sl == np.s_[:, meta['j0'], :]
    g = M.slice_geometry(meta)
    assert (g.axis, g.index) == ('y', meta['s0'])
    for ax, s0 in (('x', 3), ('z', 40)):
        m = dict(meta, slice_axis=ax, s0=s0)
        check_pairs(f'native 3D slice {ax}', m, PAIRS_3D)
    m = dict(meta, slice_axis='w')             # an unknown axis
    check_pairs('native 3D slice w', m, PAIRS_3D)


def test_accessors_foam_shaped():
    check_pairs('foam 1D', foam_meta_1d(), PAIRS_1D)
    check_pairs('foam 2D', foam_meta_2d(), PAIRS_2D)
    for ax in 'xyz':
        check_pairs(f'foam 3D {ax}', foam_meta_3d(ax), PAIRS_3D)
    m = foam_meta_3d()
    assert M.anim_scale_of(m) == ('manual', (0.0, 40.0))
    assert M.frames_of(m) is m['frames']


def test_frames_edge_cases():
    assert M.frames_of({}) is None
    assert M.frames_of({'frames': None}) is None
    assert M.frames_of({'frames': {}}) is None
    assert M.frames_of({'frames': {'times': [], 'pressures': []}}) is None
    for m in ({'frames': {'times': [0.0]}},):          # no 'pressures'
        assert _call(OLD_frames, m) == _call(NEW_frames, m)
    assert M.anim_scale_of({'anim_scale': 'nonsense'}).scale == 'run'
    assert M.anim_scale_of({'anim_scale': None}).scale == 'run'
    try:
        M.slice_geometry({}, 'diagonal')
    except ValueError:
        pass
    else:
        raise AssertionError('an unknown plane must raise ValueError')


def main():
    return cc.run_main('CHAR META', [
        test_key_sets_match_phase0_goldens, test_foam_key_sets_contain_native,
        test_accessors_native_1d, test_accessors_native_2d,
        test_accessors_native_3d, test_accessors_foam_shaped,
        test_frames_edge_cases])


if __name__ == '__main__':
    sys.exit(main())
