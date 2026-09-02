"""Parsers for blastFoam output read over the WSL UNC share:
internalField values -> numpy, time directories, blastProbes files.

Both write formats are handled: `ascii` (line-parsed) and `binary`
(FoamFile header + `nonuniform List<...>` + ascii count + `(` + raw
little-endian float64 + `);` - uniform internalFields stay inline
text in binary files too). The format is sniffed per file from the
FoamFile header, so mixed-format case dirs read fine.

All reads go through `_retry` (9p transients); a truncated in-progress
write surfaces as ValueError so the caller re-polls instead of failing.

Grid mapping: a single-block blockMesh numbers cells x-fastest, so
`to_grid` is a plain order='F' reshape onto the native blastlab arrays
(the same convention viz3d uses).
"""

import os
import re
import time as _time

import numpy as np

_RE_KIND = re.compile(r'internalField\s+(uniform|nonuniform)')
_RE_UNIFORM = re.compile(r'internalField\s+uniform\s+'
                         r'(?:\(([^)]*)\)|([^;\s]+))\s*;')
_RE_KEY_NUM = r'^\s*{key}\s+([0-9.eE+-]+);'
_RE_FORMAT = re.compile(rb'format\s+(ascii|binary)\s*;')
_RE_BIN_COUNT = re.compile(rb'internalField\s+nonuniform\s+'
                           rb'List<\w+>\s*(\d+)\s*\(')


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


def _read_bytes(path):
    def go():
        with open(path, 'rb') as f:
            return f.read()
    return _retry(go)


def _floats(joined):
    """Whitespace-separated float parse (ascii fallback path)."""
    return np.array(joined.split(), dtype=np.float64)


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


def _format_is_binary(buf):
    m = _RE_FORMAT.search(buf[:4096])
    return m is not None and m.group(1) == b'binary'


def _binary_internal(buf, path, n_cells, ncomp):
    """Binary nonuniform internalField -> flat float64 array (n*ncomp,),
    or None when the internalField is uniform (inline text - the ascii
    path handles it). Truncated/malformed data raises ValueError so a
    mid-write poll retries."""
    i = buf.find(b'internalField')
    if i < 0:
        raise ValueError(f'no internalField in {path}')
    m = _RE_BIN_COUNT.match(buf, i)
    if m is None:
        return None                     # uniform - still inline text
    n = int(m.group(1))
    if n != n_cells:
        raise ValueError(f'{path}: {n} values, expected {n_cells}')
    start, need = m.end(), n * ncomp * 8
    if len(buf) < start + need + 1 \
            or buf[start + need:start + need + 1] != b')':
        raise ValueError(f'{path}: truncated binary internalField')
    return np.frombuffer(buf, '<f8', count=n * ncomp,
                         offset=start).copy()


def read_scalar(path, n_cells):
    """volScalarField internalField -> (n_cells,) float64."""
    buf = _read_bytes(path)
    if _format_is_binary(buf):
        vals = _binary_internal(buf, path, n_cells, 1)
        if vals is not None:
            return vals
    text = buf.decode('ascii', 'replace')
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
    buf = _read_bytes(path)
    if _format_is_binary(buf):
        vals = _binary_internal(buf, path, n_cells, 3)
        if vals is not None:
            return vals.reshape(-1, 3)
    text = buf.decode('ascii', 'replace')
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


def list_sample_times(case_unc, name):
    """Sorted [(t_float, dirname)] of numeric time subdirectories of
    postProcessing/<name> (the layout functionObjects write one output
    time each). [] when the functionObject has not written yet."""
    base = os.path.join(case_unc, 'postProcessing', name)
    try:
        names = os.listdir(base)
    except OSError:
        return []
    out = []
    for d in names:
        try:
            out.append((float(d), d))
        except ValueError:
            continue
    out.sort()
    return out


def read_line_sample(case_unc, name, tdir):
    """One raw-format `sets` output dir -> (coords, values) float64
    arrays, or None when absent/unreadable. Malformed rows (partial
    mid-write line) are skipped - the caller judges completeness from
    the expected sample count."""
    base = os.path.join(case_unc, 'postProcessing', name, tdir)
    try:
        files = sorted(f for f in os.listdir(base) if f.endswith('.xy'))
    except OSError:
        return None
    if not files:
        return None
    try:
        text = _read_text(os.path.join(base, files[0]))
    except OSError:
        return None
    xs, vs = [], []
    for ln in text.splitlines():
        parts = ln.split()
        if len(parts) < 2:
            continue
        try:
            x, v = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        xs.append(x)
        vs.append(v)
    if not xs:
        return None
    return np.array(xs), np.array(vs)


def read_surface_sample(case_unc, name, tdir):
    """One raw-format `surfaces` output dir -> (points (n, 3), values
    (n,)) float64 arrays, or None when absent/unreadable. Comment
    lines are skipped and a partial mid-write tail row is dropped -
    the caller judges completeness from the expected sample count."""
    base = os.path.join(case_unc, 'postProcessing', name, tdir)
    try:
        files = sorted(f for f in os.listdir(base)
                       if f.endswith('.raw') or f.endswith('.xy'))
    except OSError:
        return None
    if not files:
        return None
    try:
        text = _read_text(os.path.join(base, files[0]))
    except OSError:
        return None
    rows = [ln for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith('#')]
    if not rows:
        return None
    try:
        vals = np.array(' '.join(rows).split(), dtype=np.float64)
    except ValueError:
        rows.pop()                  # partial mid-write tail row
        try:
            vals = np.array(' '.join(rows).split(), dtype=np.float64)
        except ValueError:
            return None
    n = (vals.size // 4) * 4        # x y z value rows
    if n == 0:
        return None
    a = vals[:n].reshape(-1, 4)
    return a[:, :3], a[:, 3]


def _parse_probes_file(path):
    """One blastProbes file -> (points, rows).

    File layout: '# Probe <i> (<x> <y> <z>)' header lines (adjusted
    locations), a '# Time' style column header, then rows of
    `time v0 v1 ...`."""
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
    return pts, rows


def read_probes(case_unc, name='gauges', field='p'):
    """blastProbes output -> dict(points, times, pressures) or None.

    Every time subdirectory of postProcessing/<name> is merged: a
    restarted run appends a new subdir starting at the restart time
    while the previous one may extend past it, so earlier chunks are
    clipped to t < first_t of the next chunk (the later dir wins)."""
    base = os.path.join(case_unc, 'postProcessing', name)
    tdirs = list_sample_times(case_unc, name)
    if not tdirs:
        return None

    pts, rows = [], []
    for _t0, d in tdirs:
        path = os.path.join(base, d, field)
        if not os.path.isfile(path):
            continue
        chunk_pts, chunk_rows = _parse_probes_file(path)
        if not pts:
            pts = chunk_pts
        if chunk_rows and rows:
            first_t = chunk_rows[0][0]
            rows = [r for r in rows if r[0] < first_t]
        rows.extend(chunk_rows)
    if not pts and not rows:
        return None
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


def to_grid(vals, spec, fill=0.0):
    """Flat internalField -> native blastlab array layout.

    On an obstacle-carved mesh (spec.solid mask set) the field holds
    only the fluid cells - subsetMesh keeps them in ascending original
    (x-fastest) order, so they scatter straight into the full grid;
    carved cells take `fill` (ambient value chosen by the caller)."""
    if spec.dim == 1:
        return vals
    shape = ((spec.nx, spec.ny) if spec.dim == 2
             else (spec.nx, spec.ny, spec.nz))
    solid = getattr(spec, 'solid', None)
    if solid is None:
        return vals.reshape(shape, order='F')
    full = np.full(solid.size, float(fill))
    full[~solid.flatten(order='F')] = vals
    return full.reshape(shape, order='F')
