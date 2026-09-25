"""Characterisation: what the Results-tab exports write (Phase 6).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 6 (finding F7). Pins, from
the code as it is before the export orchestration moves to
`services/exports.py`:

  * `can(kind, ent)` / `why_not(kind, ent)` for every kind in `KINDS`, on
    a real native 1D, 2D (axisymmetric) and 3D result, on a planar 2D
    result missing every optional piece (no gauges, snapshots or frames),
    on a blastFoam-shaped result whose case directory exists, and on no
    selection at all; `name_prefix` and `summary_rows`;
  * the Qt export path end to end (`ui.exports.export`, dialogs replaced
    by recorders, not threaded) for every kind on a native 1D and 2D run:
    the dialog each kind opens and the name it proposes, the log lines,
    what is handed to `os.startfile`, and every file written - text files
    (TSV/CSV/profile .txt) byte-exact through sha256, npz array-wise
    (dtype, shape, exact bytes), the HTML report byte-exact after its
    timestamp and its inlined PNGs are replaced by placeholders (the PNGs
    by their pixel size), PNG files by pixel size, the GIF by pixel size
    and frame count - rendering bytes are not pinned.

`test_gui_char_exports.py` pins the Tk `ResultsPanel._export` over the
same runs in the same format, so the two goldens can be compared.

No widget is built here: `ui.dialogs` is imported (it imports PySide6)
only so its two pickers can be replaced. The VTK export is pinned only on
its refusal path - it needs a blastFoam case directory in WSL.

Run:  cd blastlab/tests && python test_char_exports.py [--update]
"""
import base64
import dataclasses
import hashlib
import io
import os
import re
import shutil
import struct
import sys
import tempfile
from types import SimpleNamespace

import numpy as np

import char_common as cc
from blastlab.solvers import get_solver                     # noqa: E402
from blastlab.solvers.hooks import Result, RunHooks         # noqa: E402
from test_char_native_api import CASES                      # noqa: E402

#: the runs the exports are pinned on: the Phase 0 1D case, and the Phase
#: 0 2D axisymmetric case with a short replay record so `gif` has frames
EXPORT_CASES = {
    '1d': CASES['1d'],
    '2d': dataclasses.replace(CASES['2d'], record_frames=12),
}
#: what the GUI would name each run (a run name with characters the
#: file-name prefix must replace) and its picker label
NAMES = {'1d': ('char 1d/run', 'Run 1 - 1D'),
         '2d': ('char 2d: axisym', 'Run 2 - 2D')}
#: the kinds pinned a second time with the Title line and "Show mesh" on
TITLED_KINDS = ('report', 'pngs', 'gif')
TITLE = 'Char title'

_RESULTS = {}


def result(key):
    """The native Result for `key`, solved once per process."""
    if key not in _RESULTS:
        case = EXPORT_CASES[key] if key in EXPORT_CASES else CASES[key]
        res = get_solver(case.dim, 'native')(case, RunHooks())
        if key in NAMES:
            res.meta['name'] = NAMES[key][0]
        _RESULTS[key] = res
    return _RESULTS[key]


def entry(key):
    """A results-list entry as both GUIs hold one."""
    res = result(key)
    label = NAMES.get(key, (None, f'Run - {key.upper()}'))[1]
    return SimpleNamespace(label=label, display=label,
                           dim=int(key[0]), result=res)


def missing_entry():
    """A planar 2D result with no gauges, no snapshots and no frames."""
    meta = dict(geometry='planar', solver='native', Lx=1.0, Ly=1.0)
    res = Result({}, dict(times=np.array([]), points=[], pressures=[]),
                 meta, 'end time reached', False)
    return SimpleNamespace(label='empty', display='empty', dim=2, result=res)


def foam_entry(case_dir):
    """A blastFoam-shaped 3D result whose case directory exists."""
    meta = dict(solver='blastfoam', case_dir=case_dir)
    res = Result({}, dict(times=np.array([]), points=[], pressures=[]),
                 meta, 'end time reached', False)
    return SimpleNamespace(label='foam', display='foam', dim=3, result=res)


# ── describing what was written ──────────────────────────────────────────
def _sha(b):
    return hashlib.sha256(b).hexdigest()


def png_size(data):
    """(width, height) from a PNG's IHDR chunk."""
    assert data[:8] == b'\x89PNG\r\n\x1a\n', 'not a PNG'
    return list(struct.unpack('>II', data[16:24]))


_B64 = re.compile(r'data:image/png;base64,([A-Za-z0-9+/=]+)')
_STAMP = re.compile(r' &middot; \d{4}-\d{2}-\d{2} \d{2}:\d{2} &middot; ')


def normalise_html(text):
    """The report with its timestamp and inlined PNG bytes replaced by
    placeholders (the PNGs by their pixel size): everything else is
    pinned byte for byte."""
    text = _STAMP.sub(' &middot; <now> &middot; ', text)
    return _B64.sub(lambda m: 'data:image/png;<png %dx%d>'
                    % tuple(png_size(base64.b64decode(m.group(1)))), text)


def describe_file(path):
    with open(path, 'rb') as f:
        data = f.read()
    ext = os.path.splitext(path)[1].lower()
    if ext == '.png':
        return {'png': png_size(data)}
    if ext == '.gif':
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            return {'gif': list(im.size),
                    'frames': int(getattr(im, 'n_frames', 1))}
    if ext == '.npz':
        with np.load(io.BytesIO(data)) as z:
            return {'npz': {k: {'dtype': str(z[k].dtype),
                                'shape': list(z[k].shape),
                                'sha256': _sha(np.ascontiguousarray(
                                    z[k]).tobytes())}
                            for k in sorted(z.files)}}
    if ext == '.html':
        return {'html': normalise_html(data.decode('utf-8'))}
    return {'bytes': len(data), 'sha256': _sha(data),
            'head': data.decode('utf-8', 'replace').splitlines()[:2]}


def describe_dir(out):
    files = {}
    for root, _dirs, names in os.walk(out):
        for n in sorted(names):
            p = os.path.join(root, n)
            files[os.path.relpath(p, out).replace(os.sep, '/')] = \
                describe_file(p)
    return files


def scrub(obj, out):
    """`obj` with the temp directory replaced by '<out>'."""
    if isinstance(obj, str):
        for form in (out, out.replace('\\', '/')):
            obj = obj.replace(form, '<out>')
        return obj.replace('\\', '/')
    if isinstance(obj, (list, tuple)):
        return [scrub(x, out) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub(v, out) for k, v in obj.items()}
    return obj


class Opened:
    """`os.startfile` replaced by a recorder for the duration: the report
    and VTK exports open what they wrote."""

    def __enter__(self):
        self.paths = []
        self._real = getattr(os, 'startfile', None)
        os.startfile = self.paths.append
        return self

    def __exit__(self, *exc):
        if self._real is None:
            del os.startfile
        else:
            os.startfile = self._real


def gif_name(default):
    """The GIF the user picks from the Animation dialog: the proposed name
    with a .gif extension (the proposal is .mp4 when ffmpeg is on PATH)."""
    return os.path.splitext(default)[0] + '.gif'


def plan():
    """(case key, kind, variant) for every export pinned, in order."""
    from blastlab.ui.exports import KINDS
    out = []
    for key in ('1d', '2d'):
        for kind in KINDS:
            out.append((key, kind, 'plain'))
        for kind in TITLED_KINDS:
            out.append((key, kind, 'titled'))
    return out


# ── the Qt path ──────────────────────────────────────────────────────────
def qt_export(key, kind, variant):
    from blastlab.ui import dialogs, exports
    ent = entry(key)
    opts = ({'title_extra': TITLE, 'show_mesh': True}
            if variant == 'titled' else {})
    out = tempfile.mkdtemp(prefix='blastlab_char_qt_')
    calls, log, errors = [], [], []

    def save_file(title, filters='All files (*.*)', parent=None, start='',
                  default_suffix=None):
        calls.append(['save_file', title, filters, start, default_suffix])
        name = gif_name(start) if kind == 'gif' else start
        return os.path.join(out, name)

    def pick_dir(title, parent=None, start=''):
        calls.append(['pick_dir', title, start])
        return out

    real = dialogs.save_file, dialogs.pick_dir
    dialogs.save_file, dialogs.pick_dir = save_file, pick_dir
    try:
        with Opened() as opened:
            ret = exports.export(kind, ent, opts, log=log.append,
                                 on_error=lambda *a: errors.append(list(a)),
                                 threaded=False)
        got = dict(dialogs=calls, returned=ret, log=log, errors=errors,
                   opened=opened.paths, files=describe_dir(out))
        return scrub(got, out)
    finally:
        dialogs.save_file, dialogs.pick_dir = real
        shutil.rmtree(out, ignore_errors=True)


def test_qt_exports():
    got = {f'{key}/{kind}/{variant}': qt_export(key, kind, variant)
           for key, kind, variant in plan()}
    cc.check_json('exports_qt.json', got)


# ── can / why_not / name_prefix / summary_rows ───────────────────────────
def test_can_why_not():
    from blastlab.ui import exports
    with tempfile.TemporaryDirectory(prefix='blastlab_char_foam_') as cd:
        ents = {'1d': entry('1d'), '2d': entry('2d'), '3d': entry('3d'),
                'missing': missing_entry(), 'foam': foam_entry(cd),
                'none': None}
        got = {}
        for name, ent in ents.items():
            got[name] = {kind: {'can': exports.can(kind, ent),
                                'why_not': exports.why_not(kind, ent)}
                         for kind in exports.KINDS}
            if ent is not None:
                got[name]['name_prefix'] = exports.name_prefix(ent.result)
        got['summary_rows'] = {k: exports.summary_rows(result(k))
                               for k in ('1d', '2d', '3d')}
        got['KINDS'] = list(exports.KINDS)
        got['DIR_KINDS'] = list(exports.DIR_KINDS)
        cc.check_json('exports_can.json', got)


def main():
    return cc.run_main('CHAR EXPORTS', [test_can_why_not, test_qt_exports])


if __name__ == '__main__':
    sys.exit(main())
