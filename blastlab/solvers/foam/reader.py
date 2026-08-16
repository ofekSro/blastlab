"""Parsers for blastFoam ascii output read over the WSL UNC share:
internalField values -> numpy, time directories, blastProbes files.

All reads go through `_retry` (9p transients); a truncated in-progress
write surfaces as ValueError so the caller re-polls instead of failing.

Grid mapping: a single-block blockMesh numbers cells x-fastest, so
`to_grid` is a plain order='F' reshape onto the native blastlab arrays
(the same convention viz3d uses).
"""

import os
import re
import time as _time
import warnings

import numpy as np

_RE_KIND = re.compile(r'internalField\s+(uniform|nonuniform)')
_RE_UNIFORM = re.compile(r'internalField\s+uniform\s+'
                         r'(?:\(([^)]*)\)|([^;\s]+))\s*;')
_RE_KEY_NUM = r'^\s*{key}\s+([0-9.eE+-]+);'


def _retry(fn, tries=3, delay=0.5):
    for i in range(tries):
        try:
            return fn()
        except OSError:
            if i == tries - 1:
                raise
            _time.sleep(delay)


def _read_text(path):
    def go():
        with open(path, encoding='ascii', errors='replace') as f:
            return f.read()
    return _retry(go)


def _floats(joined):
    """C-fast whitespace-separated float parse."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        return np.fromstring(joined, dtype=np.float64, sep=' ')


def _nonuniform_body(text, path):
    """Lines of the internalField nonuniform list (between the bare
    '(' and ')' lines)."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith('internalField'):
            for j in range(i + 1, min(i + 4, len(lines))):
                if lines[j].strip() == '(':
                    start = j + 1
                    break
            break
    if start is None:
        raise ValueError(f'no internalField list in {path}')
    for k in range(start, len(lines)):
        if lines[k].strip() == ')':
            return lines[start:k]
    raise ValueError(f'unterminated internalField list in {path}')


def _kind(text, path):
    m = _RE_KIND.search(text)
    if not m:
        raise ValueError(f'no internalField in {path}')
    return m.group(1)


def read_scalar(path, n_cells):
    """volScalarField internalField -> (n_cells,) float64."""
    text = _read_text(path)
    if _kind(text, path) == 'uniform':
        m = _RE_UNIFORM.search(text)
        return np.full(n_cells, float(m.group(2)))
    vals = _floats('\n'.join(_nonuniform_body(text, path)))
    if len(vals) != n_cells:
        raise ValueError(f'{path}: {len(vals)} values, '
                         f'expected {n_cells}')
    return vals


def read_vector(path, n_cells):
    """volVectorField internalField -> (n_cells, 3) float64."""
    text = _read_text(path)
    if _kind(text, path) == 'uniform':
        m = _RE_UNIFORM.search(text)
        v = [float(x) for x in m.group(1).split()]
        return np.tile(np.array(v), (n_cells, 1))
    body = '\n'.join(_nonuniform_body(text, path))
    vals = _floats(body.replace('(', ' ').replace(')', ' '))
    if len(vals) != 3 * n_cells:
        raise ValueError(f'{path}: {len(vals)} components, '
                         f'expected {3 * n_cells}')
    return vals.reshape(-1, 3)


def read_time(dir_path):
    """(t, deltaT) from <time>/uniform/time (exact values; the dir
    name is display precision only)."""
    text = _read_text(os.path.join(dir_path, 'uniform', 'time'))
    t = re.search(_RE_KEY_NUM.format(key='value'), text, re.M)
    dt = re.search(_RE_KEY_NUM.format(key='deltaT'), text, re.M)
    if not t:
        raise ValueError(f'no time value in {dir_path}/uniform/time')
    return float(t.group(1)), float(dt.group(1)) if dt else 0.0


def list_times(case_unc):
    """Sorted [(t_float, dirname)] of numeric time directories."""
    out = []
    for name in os.listdir(case_unc):
        try:
            t = float(name)
        except ValueError:
            continue
        if os.path.isdir(os.path.join(case_unc, name)):
            out.append((t, name))
    out.sort()
    return out


def time_ready(dir_path, fields):
    """All field files + uniform/time present (write completed)."""
    if not os.path.isfile(os.path.join(dir_path, 'uniform', 'time')):
        return False
    return all(os.path.isfile(os.path.join(dir_path, f))
               for f in fields)


def read_probes(case_unc, name='gauges', field='p'):
    """blastProbes output -> dict(points, times, pressures) or None.

    File layout: '# Probe <i> (<x> <y> <z>)' header lines (adjusted
    locations), a '# Time' style column header, then rows of
    `time v0 v1 ...`."""
    base = os.path.join(case_unc, 'postProcessing', name)
    if not os.path.isdir(base):
        return None
    tdirs = []
    for d in os.listdir(base):
        try:
            tdirs.append((float(d), d))
        except ValueError:
            continue
    if not tdirs:
        return None
    tdirs.sort()
    path = os.path.join(base, tdirs[0][1], field)
    if not os.path.isfile(path):
        return None
    text = _read_text(path)
    pts, rows = [], []
    for ln in text.splitlines():
        if ln.lstrip().startswith('#'):
            m = re.search(r'Probe\s+\d+\s+\(([^)]*)\)', ln)
            if m:
                pts.append(tuple(float(v) for v in m.group(1).split()))
        elif ln.strip():
            try:
                rows.append([float(v) for v in ln.split()])
            except ValueError:
                continue        # partial last line mid-write
    if not rows:
        return dict(points=pts, times=np.array([]),
                    pressures=[np.array([]) for _ in pts])
    ncol = min(len(r) for r in rows)
    a = np.array([r[:ncol] for r in rows])
    n_probes = ncol - 1
    if len(pts) != n_probes:            # header/columns mismatch
        pts = (pts + [(np.nan,) * 3] * n_probes)[:n_probes]
    return dict(points=pts, times=a[:, 0],
                pressures=[a[:, i + 1] for i in range(n_probes)])


def to_grid(vals, spec):
    """Flat internalField -> native blastlab array layout."""
    if spec.dim == 1:
        return vals
    if spec.dim == 2:
        return vals.reshape((spec.nx, spec.ny), order='F')
    return vals.reshape((spec.nx, spec.ny, spec.nz), order='F')
