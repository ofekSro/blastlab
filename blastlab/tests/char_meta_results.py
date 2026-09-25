"""Shared fixtures for the Phase 8 characterisation of the results panels.

docs/ARCHITECTURE_REVIEW.md section 5, Phase 8 (finding F3). The panel
tests `test_ui_char_results_meta.py` (Qt) and `test_gui_char_results_meta.py`
(Tk) pin what the Fields, Gauges and Animation views DISPLAY for a finished
native 1D/2D/3D run and for blastFoam-shaped results, and what each view
does when one `Result.meta` key is missing. This module builds those
results and turns what a view shows into plain JSON.

The native results are the three Phase 0 cases of `test_char_native_api`
(the same solves, so they are deterministic). There is no WSL here, so the
blastFoam-shaped results are the native ones with the extra keys
`solvers/foam/backend.py` `finalize_1d/2d/3d` add (`solver`, `material`,
`conserved`, `case_dir`, `refine`, `peak_source`) - the key sets the
backend writes, read from its code, not from a real run.

Not a test module (no `test_` prefix): imported by the two panel tests.
"""
import copy
import hashlib
import json

import numpy as np

import char_common as cc                                   # noqa: F401
from blastlab.solvers.hooks import Result                   # noqa: E402

_RUNS = {}


def native(key):
    """A fresh deep copy of the native '1d' / '2d' / '3d' Phase 0 result
    (solved once per process)."""
    if key not in _RUNS:
        from test_char_native_api import run
        _RUNS[key] = run(key)
    return copy.deepcopy(_RUNS[key])


#: the keys `finalize_*` in solvers/foam/backend.py add on top of the
#: native set (values made up; case_dir deliberately does not exist)
FOAM_EXTRA_1D = dict(solver='blastfoam', material='TNT', conserved=None,
                     case_dir='/root/blastlab_runs/p8_char_missing')
FOAM_EXTRA_ND = dict(FOAM_EXTRA_1D, refine=None, peak_source='foam')


def foam_shaped(key):
    """The native result with the blastFoam backend's extra meta keys."""
    res = native(key)
    res.meta.update(FOAM_EXTRA_1D if key == '1d' else FOAM_EXTRA_ND)
    res.meta['eos'] = 'JWL'            # the backend always writes JWL
    return res


def fixtures():
    """(name, dim, Result) for every result the panels are pinned on."""
    out = [('native_1d', 1, native('1d')),
           ('native_2d', 2, native('2d')),
           ('native_3d', 3, native('3d')),
           ('foam_1d', 1, foam_shaped('1d')),
           ('foam_2d', 2, foam_shaped('2d')),
           ('foam_3d', 3, foam_shaped('3d'))]
    # the recorded colour scale as solvers/jobs.py stores it after a run
    r = native('2d')
    r.meta.update(anim_scale='manual', anim_clim=(0.0, 50.0), name='manual')
    out.append(('native_2d_manual_scale', 2, r))
    r = native('3d')
    r.meta.update(anim_scale='frame', anim_clim=None)
    out.append(('native_3d_frame_scale', 3, r))
    # the other two recorded slice axes (the case is a cube, so the
    # recorded frames still fit the plane)
    for ax, s0 in (('x', 10), ('z', 30)):
        r = native('3d')
        r.meta.update(slice_axis=ax, s0=s0)
        out.append((f'native_3d_slice_{ax}', 3, r))
    # a 3D result whose slice was recorded before `s0` existed
    r = native('3d')
    del r.meta['s0'], r.meta['slice_axis']
    out.append(('native_3d_no_s0', 3, r))
    # no frames recorded, and frames recorded but empty
    r = native('2d')
    del r.meta['frames']
    out.append(('native_2d_no_frames', 2, r))
    r = native('2d')
    r.meta['frames'] = dict(times=np.array([]), pressures=[])
    out.append(('native_2d_empty_frames', 2, r))
    return out


def without(res, key):
    """A shallow copy of `res` whose meta lacks `key`."""
    meta = {k: v for k, v in res.meta.items() if k != key}
    return Result(res.snapshots, res.gauges, meta, res.stop_reason,
                  res.stopped_early)


# ── describing what is shown ─────────────────────────────────────────────
def digest(a):
    """dtype, shape and a hash of the exact bytes of an array (masked
    arrays: data and mask)."""
    if isinstance(a, np.ma.MaskedArray):
        return dict(masked=digest(np.ma.getdata(a)),
                    mask=digest(np.ma.getmaskarray(a)))
    a = np.asarray(a)
    return dict(dtype=str(a.dtype), shape=list(a.shape),
                sha1=hashlib.sha1(np.ascontiguousarray(a).tobytes())
                .hexdigest())


def value(v):
    """A plain-JSON description of any value a view reads or shows."""
    if isinstance(v, np.ndarray):
        return digest(v)
    if isinstance(v, dict):
        return {str(k): value(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        if v and all(isinstance(x, np.ndarray) for x in v):
            return dict(arrays=len(v), digests=[digest(x)['sha1']
                                                for x in v])
        return [value(x) for x in v]
    if isinstance(v, slice):
        return repr(v)
    if isinstance(v, np.generic):
        return repr(v.item())
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return repr(v)


def outcome(fn, *args, **kw):
    """What calling `fn` does: `{'ok': <description>}` or the exception's
    type and message."""
    try:
        return {'ok': value(fn(*args, **kw))}
    except Exception as exc:                  # noqa: BLE001 - the point
        return {'raises': f'{type(exc).__name__}: {exc}'}


def short(desc):
    """A missing-key outcome shortened: raises verbatim, ok as a hash."""
    if 'ok' in desc:
        text = json.dumps(cc.plain(desc['ok']), sort_keys=True)
        return 'ok ' + hashlib.sha1(text.encode()).hexdigest()[:16]
    return desc['raises']


def figure(fig):
    """Titles, labels and the data of every artist of a matplotlib
    figure, or None."""
    if fig is None:
        return None
    out = dict(texts=[t.get_text() for t in fig.texts],
               suptitle=(fig._suptitle.get_text()
                         if getattr(fig, '_suptitle', None) else None),
               axes=[])
    for ax in fig.axes:
        a = dict(title=ax.get_title(), xlabel=ax.get_xlabel(),
                 ylabel=ax.get_ylabel(),
                 lines=[digest(np.asarray(ln.get_xydata()))['sha1']
                        for ln in ax.get_lines()],
                 labels=[ln.get_label() for ln in ax.get_lines()],
                 images=[digest(im.get_array()) for im in ax.images],
                 collections=[digest(c.get_array())
                              if c.get_array() is not None else None
                              for c in ax.collections],
                 texts=[t.get_text() for t in ax.texts])
        out['axes'].append(a)
    return out
