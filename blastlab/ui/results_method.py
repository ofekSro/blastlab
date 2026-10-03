"""How a result was computed (UX-15): the rows of the Results screen's
method card, the caption of its list row, and the case file behind it.

Toolkit-free, so it is testable without a window. Batch
2026-09-29-gui-results T2 (plan section 7). The rule is "show only what
the result holds, never guess": every row comes from `res.meta`,
`res.stop_reason` or the result's own record files that `res.meta` names -
`meta['model_dir']` -> `MODEL.json` (the case exactly as run, OUT-1) and
`manifest.json`; for a loaded blastFoam run with no model folder,
`meta['case_dir']` -> its `case.json` (the file the resume path reads).
A missing or unreadable file drops its rows silently. Nothing is
defaulted: the case file is read as raw JSON, so a key the file does not
hold gives no row (`load_case` would fill in the dataclass default).
"""

import datetime
import json
import os
import re

from ..core import mode as mode_mod
from ..services.model_folder import CASE_FILE, MANIFEST_FILE
from .run_clock import fmt_duration

#: a loaded blastFoam run's own copy of its case (solvers/foam/writer.py)
RUN_CASE_FILE = 'case.json'

#: the tooltip of Show case / Load into 01 Setup when there is no file
NO_CASE_TIP = 'This result carries no saved case (no model folder).'

_T_LABEL = re.compile(r't\s*=\s*[-+0-9.eE]+\s*[mµu]?s')


def _meta(res):
    return (getattr(res, 'meta', None) or {}) if res is not None else {}


def _read_json(path):
    """The file's JSON object, or None when it is missing or unreadable."""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _model_dir(meta):
    path = meta.get('model_dir')
    return path if path and os.path.isdir(str(path)) else None


def case_path_of(res):
    """`<model_dir>\\MODEL.json` when it exists, else the loaded run's
    `<case_dir>\\case.json` when it exists, else None."""
    meta = _meta(res)
    home = _model_dir(meta)
    if home:
        p = os.path.join(home, CASE_FILE)
        if os.path.isfile(p):
            return p
    cd = meta.get('case_dir')
    if cd:
        p = os.path.join(str(cd), RUN_CASE_FILE)
        if os.path.isfile(p):
            return p
    return None


def case_source(entry):
    """The case file behind a results-list entry (`MODEL.json`, else the
    loaded run's `case.json`), or None."""
    return case_path_of(getattr(entry, 'result', None))


def records(res):
    """(case dict or None, manifest dict or None) for a result."""
    meta = _meta(res)
    path = case_path_of(res)
    case = _read_json(path) if path else None
    home = _model_dir(meta)
    manifest = (_read_json(os.path.join(home, MANIFEST_FILE)) if home
                else None)
    return case, manifest


def _num(v):
    """A finite float, or None (a missing, None or non-numeric value)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float('inf'), float('-inf')) else None


def _solver(meta, manifest):
    s = (manifest or {}).get('solver') or meta.get('solver')
    return mode_mod.LABELS.get(s, s) if s else None


def _is_foam(meta, manifest):
    return ((manifest or {}).get('solver') or meta.get('solver')) \
        == 'blastfoam'


def _position(meta, dim):
    """`· z 2 m` (2D axisymmetric), `· x 1, y 2 m` (planar), `· x, y, z`
    (3D); '' in 1D or when the meta does not say."""
    c = meta.get('charge_center')
    if dim == 1 or c is None:
        return ''
    try:
        vals = [_num(v) for v in c]
    except TypeError:
        return ''
    if dim == 2:
        geo = meta.get('geometry')
        if geo == 'axisymmetric' and len(vals) >= 2 and vals[1] is not None:
            return f' · z {vals[1]:g} m'
        if geo == 'planar' and len(vals) >= 2 and None not in vals[:2]:
            return f' · x {vals[0]:g}, y {vals[1]:g} m'
        return ''
    if dim == 3 and len(vals) >= 3 and None not in vals[:3]:
        return f' · x {vals[0]:g}, y {vals[1]:g}, z {vals[2]:g} m'
    return ''


def _charge(meta, case, dim):
    w = _num(meta.get('charge_kg') if dim == 1 else meta.get('charge'))
    if w is None:
        return None
    material = meta.get('material') or (case or {}).get('material')
    text = f'{w:g} kg' + (f' {material}' if material else '')
    return text + _position(meta, dim)


def _mesh(meta, case, dim):
    dx = _num(meta.get('dx'))
    if dx is None and dim == 1:
        dx = _num((case or {}).get('cell_size_m'))
    if dx is None:
        return None
    text = f'cell {dx * 1000:g} mm'
    ref = meta.get('refine')
    if isinstance(ref, dict):
        lmax, base = _num(ref.get('lmax')), _num(ref.get('dx_base'))
        if lmax is not None and lmax > 0 and base is not None:
            # D30's word: the finest cell of a refined mesh
            text += f' · finest {base / 2 ** int(lmax) * 1000:.3g} mm'
    return text


def _parallel(manifest):
    n = (manifest or {}).get('n_procs')
    if n is None or isinstance(n, bool):
        return None
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    return 'serial' if n == 1 else f'{n} MPI ranks'


def final_time_label(res):
    """`t = 4.90 ms` out of the final snapshot's label, or None."""
    snaps = getattr(res, 'snapshots', None) or {}
    if not snaps:
        return None
    m = _T_LABEL.search(str(list(snaps)[-1]))
    return m.group(0) if m else None


def _stamp(text):
    try:
        return datetime.datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None


def _ended(res, manifest):
    parts = []
    reason = str(getattr(res, 'stop_reason', '') or '')
    if reason:
        parts.append(reason)                    # verbatim (D66)
    t = final_time_label(res)
    if t:
        parts.append(t)
    fin = _stamp((manifest or {}).get('finished'))
    if fin is not None:
        parts.append(f'finished {fin:%H:%M}')
    return ' · '.join(parts) or None


def method_rows(res, dim):
    """[(label, value)] for the method card, in board order. A row is
    there only when its source holds the value (plan section 7)."""
    meta = _meta(res)
    case, manifest = records(res)
    rows = []
    solver = _solver(meta, manifest)
    if solver:
        rows.append(('Solver', solver))
    charge = _charge(meta, case, dim)
    if charge:
        rows.append(('Charge', charge))
    # the native solvers detonate the whole charge at t = 0 (CLAUDE.md
    # section 7): these two rows describe blastFoam results only
    if _is_foam(meta, manifest) and case:
        for label, key in (('Detonation', 'activation'),
                           ('Afterburn', 'afterburn')):
            if case.get(key):
                rows.append((label, str(case[key])))
    mesh = _mesh(meta, case, dim)
    if mesh:
        rows.append(('Mesh', mesh))
    par = _parallel(manifest)
    if par:
        rows.append(('Parallel', par))
    ended = _ended(res, manifest)
    if ended:
        rows.append(('Ended', ended))
    return rows


def _kind(meta, dim):
    if dim == 1:
        return '1D spherical'
    if dim == 2:
        geo = meta.get('geometry')
        return {'axisymmetric': '2D axisym.',
                'planar': '2D planar'}.get(geo, '2D')
    return f'{dim}D'


def run_duration(manifest):
    """manifest.finished - manifest.created in seconds, or None. It
    includes the model-folder writes (cf. D59)."""
    a = _stamp((manifest or {}).get('created'))
    b = _stamp((manifest or {}).get('finished'))
    if a is None or b is None or b < a:
        return None
    return (b - a).total_seconds()


def result_caption(entry):
    """`2D axisym. · blastFoam · 5 min 31 s`; the parts a result does not
    hold are left out."""
    res = getattr(entry, 'result', None)
    meta = _meta(res)
    _case, manifest = records(res)
    parts = [_kind(meta, int(getattr(entry, 'dim', 0) or 0))]
    solver = _solver(meta, manifest)
    if solver:
        parts.append(solver)
    s = run_duration(manifest)
    if s is not None:
        parts.append(fmt_duration(s))
    return ' · '.join(parts)


def chain_caption(entry):
    """A chain's list caption (GUI-9 T5, board Results_Chain line 62):
    `1D → 2D → 3D · 3 stages · 41 min 0 s`; `2 of 3 stages` while fewer
    landed (a stopped chain, or one still running). The duration is the
    last landed stage manifest's `finished` - the first stage manifest's
    `created` (both from the stages' own `records()`), left out without
    both."""
    route = [int(d) for d in (getattr(entry, 'route', None) or ())]
    stages = list(getattr(entry, 'stages', None) or [])
    parts = [' → '.join(f'{d}D' for d in route)] if route else []
    n, total = len(stages), len(route) or len(stages)
    parts.append(f'{n} stages' if n == total else f'{n} of {total} stages')
    if stages:
        _c, first = records(getattr(stages[0], 'result', None))
        _c, last = records(getattr(stages[-1], 'result', None))
        a = _stamp((first or {}).get('created'))
        b = _stamp((last or {}).get('finished'))
        if a is not None and b is not None and b >= a:
            parts.append(fmt_duration((b - a).total_seconds()))
    return ' · '.join(parts)
