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
_RE_LIST_COUNT = re.compile(rb'\n(\d+)\s*\n\(')


def _retry(fn, tries=3, delay=0.5):
    for i in range(tries):
        try:
            return fn()
        except OSError:
            if i == tries - 1:
                raise
            _time.sleep(delay)


#: Read the 9p share in pieces this size. A ONE-SHOT `f.read()` of a
#: large file over `\\wsl.localhost\...` fails with OSError EINVAL
#: (errno 22) rather than short-reading - measured on the 864,000-cell
#: HD1-3d case, where a binary scalar field is ~7 MB and the first
#: written time threw on the first field it touched. `_retry` above did
#: not help, because the failure is deterministic in the SIZE rather
#: than transient, so every attempt failed identically.
#:
#: 4 MiB is comfortably under whatever the limit is and costs nothing:
#: the reads are sequential and the OS buffers them anyway.
_CHUNK = 4 << 20


def _read_text(path):
    # Same chunking as _read_bytes, for the same reason: an ascii field
    # file from a large case is just as big as a binary one.
    def go():
        parts = []
        with open(path, encoding='ascii', errors='replace') as f:
            while True:
                s = f.read(_CHUNK)
                if not s:
                    break
                parts.append(s)
        return ''.join(parts)
    return _retry(go)


def _read_bytes(path):
    """The whole file, read in chunks rather than in one call.

    See `_CHUNK` for why the obvious `f.read()` is not safe here. This
    also degrades gracefully if a future path short-reads: the loop
    ends on the first empty chunk either way.
    """
    def go():
        parts = []
        with open(path, 'rb') as f:
            while True:
                b = f.read(_CHUNK)
                if not b:
                    break
                parts.append(b)
        return b''.join(parts)
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
    if n_cells is not None and n != n_cells:
        raise ValueError(f'{path}: {n} values, expected {n_cells}')
    start, need = m.end(), n * ncomp * 8
    if len(buf) < start + need + 1 \
            or buf[start + need:start + need + 1] != b')':
        raise ValueError(f'{path}: truncated binary internalField')
    return np.frombuffer(buf, '<f8', count=n * ncomp,
                         offset=start).copy()


def scalar_size(path):
    """How many values a volScalarField's internalField actually holds,
    without being told what to expect - or None when it is `uniform`,
    which fits any mesh.

    P1-5: a time directory can be internally inconsistent. The per-step
    function objects (pMax, impulse) write at `writeTime` like everything
    else, but on a dynamic-AMR run a field that missed the mesh update is
    written at the PREVIOUS cell count, and blastFoam then refuses to
    restart from that directory ('size 5138 is not equal to the given
    value of 5189'). Comparing sizes here is what lets `resume_run` walk
    back to a directory that is whole. Raises for a missing or malformed
    file, like every other reader."""
    buf = _read_bytes(path)
    if _format_is_binary(buf):
        i = buf.find(b'internalField')
        if i < 0:
            raise ValueError(f'no internalField in {path}')
        m = _RE_BIN_COUNT.match(buf, i)
        if m is not None:
            return int(m.group(1))
        # uniform: still inline text, fall through to the ascii path
    text = buf.decode('ascii', 'replace')
    if _kind(text, path) == 'uniform':
        return None
    return len(_floats('\n'.join(_nonuniform_body(text, path))))


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
        if m is None or m.group(2) is None:
            raise ValueError(f'truncated uniform field: {path}')
        return np.full(n_cells, float(m.group(2)))
    vals = _floats('\n'.join(_nonuniform_body(text, path)))
    if len(vals) != n_cells:
        raise ValueError(f'{path}: {len(vals)} values, '
                         f'expected {n_cells}')
    return vals


def read_vector(path, n_cells):
    """volVectorField internalField -> (n_cells, 3) float64.
    `n_cells=None` accepts any nonuniform count (used for the cell
    centres of a refined mesh, whose count the reader learns here)."""
    buf = _read_bytes(path)
    if _format_is_binary(buf):
        vals = _binary_internal(buf, path, n_cells, 3)
        if vals is not None:
            return vals.reshape(-1, 3)
    text = buf.decode('ascii', 'replace')
    if _kind(text, path) == 'uniform':
        if n_cells is None:
            raise ValueError(f'{path}: uniform field needs a cell count')
        m = _RE_UNIFORM.search(text)
        if m is None or m.group(1) is None:
            raise ValueError(f'truncated uniform field: {path}')
        v = [float(x) for x in m.group(1).split()]
        return np.tile(np.array(v), (n_cells, 1))
    body = '\n'.join(_nonuniform_body(text, path))
    vals = _floats(body.replace('(', ' ').replace(')', ' '))
    if len(vals) % 3:
        raise ValueError(f'{path}: {len(vals)} components is not a '
                         f'whole number of vectors')
    if n_cells is not None and len(vals) != 3 * n_cells:
        raise ValueError(f'{path}: {len(vals)} components, '
                         f'expected {3 * n_cells}')
    return vals.reshape(-1, 3)


def read_label_list(path):
    """A polyMesh labelList file (e.g. `polyMesh/cellLevel`, the hexRef
    refinement level per cell that setRefinedFields / adaptiveFvMesh
    write) -> int64 array. Ascii or binary (32-bit labels, this build's
    Int32 flavour); a truncated file raises ValueError like the fields."""
    buf = _read_bytes(path)
    end_hdr = buf.find(b'}')                # end of the FoamFile header
    if end_hdr < 0:
        raise ValueError(f'no FoamFile header in {path}')
    m = _RE_LIST_COUNT.search(buf, end_hdr)
    if m is None:
        raise ValueError(f'no label list in {path}')
    n, start = int(m.group(1)), m.end()
    if _format_is_binary(buf):
        need = n * 4
        if len(buf) < start + need + 1 \
                or buf[start + need:start + need + 1] != b')':
            raise ValueError(f'{path}: truncated binary labelList')
        return np.frombuffer(buf, '<i4', count=n,
                             offset=start).astype(np.int64)
    text = buf[start:].decode('ascii', 'replace')
    k = text.find(')')
    if k < 0:
        raise ValueError(f'{path}: unterminated labelList')
    vals = np.array(text[:k].split(), dtype=np.int64)
    if len(vals) != n:
        raise ValueError(f'{path}: {len(vals)} labels, expected {n}')
    return vals


def read_cell_centres(case_unc, time='0'):
    """(n, 3) cell centres written by `postProcess -func
    writeCellCentres -time <time>` (<time>/C) - the refined mesh's own
    account of its cells, matched against core.refine's prediction.
    `time` is the run's start dir, which a profile stage names t0."""
    return read_vector(os.path.join(case_unc, time, 'C'), None)


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


def _parse_probes_vec(path):
    """One VECTOR blastProbes file -> (points, rows): vector rows look
    like `time (ux uy uz) (ux uy uz) ...`, so each row flattens to
    [t, u0x, u0y, u0z, u1x, ...]."""
    text = _read_text(path)
    pts, rows = [], []
    for ln in text.splitlines():
        if ln.lstrip().startswith('#'):
            m = re.search(r'Probe\s+\d+\s+\(([^)]*)\)', ln)
            if m:
                pts.append(tuple(float(v) for v in m.group(1).split()))
        elif ln.strip():
            try:
                rows.append([float(v) for v in
                             ln.replace('(', ' ').replace(')', ' ')
                             .split()])
            except ValueError:
                continue        # partial last line mid-write
    return pts, rows


def _merge_chunks(base, tdirs, field, parse):
    """Restart-chunk merge shared by every probe field: a restarted run
    appends a new subdir starting at the restart time while the previous
    one may extend past it, so earlier chunks are clipped to t < first_t
    of the next chunk (the later dir wins)."""
    pts, rows = [], []
    for _t0, d in tdirs:
        path = os.path.join(base, d, field)
        if not os.path.isfile(path):
            continue
        chunk_pts, chunk_rows = parse(path)
        if not pts:
            pts = chunk_pts
        if chunk_rows and rows:
            first_t = chunk_rows[0][0]
            rows = [r for r in rows if r[0] < first_t]
        rows.extend(chunk_rows)
    return pts, rows


def read_probes(case_unc, name='gauges', field='p'):
    """blastProbes output -> dict(points, times, pressures) or None.

    When the run also recorded U and rho (T44/N12) and their rows align
    row-for-row with p's, the dict gains `speeds` (|U| per probe) and
    `rhos`; consumers that only know `pressures` see exactly the shape
    they always did."""
    base = os.path.join(case_unc, 'postProcessing', name)
    tdirs = list_sample_times(case_unc, name)
    if not tdirs:
        return None

    pts, rows = _merge_chunks(base, tdirs, field, _parse_probes_file)
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
    out = dict(points=pts, times=a[:, 0],
               pressures=[a[:, i + 1] for i in range(n_probes)])

    # T44 extras, attached only when they align with p sample-for-sample
    # (they are written by the same FO in lockstep; a torn tail degrades
    # back to p-only rather than misaligning)
    _p2, rrows = _merge_chunks(base, tdirs, 'rho', _parse_probes_file)
    if rrows and len(rrows) == len(rows) \
            and min(len(r) for r in rrows) >= ncol:
        ra = np.array([r[:ncol] for r in rrows])
        out['rhos'] = [ra[:, i + 1] for i in range(n_probes)]
    _p3, urows = _merge_chunks(base, tdirs, 'U', _parse_probes_vec)
    if urows and len(urows) == len(rows) \
            and min(len(r) for r in urows) >= 1 + 3 * n_probes:
        ua = np.array([r[:1 + 3 * n_probes] for r in urows])
        out['speeds'] = [np.sqrt((ua[:, 1 + 3 * i:4 + 3 * i] ** 2)
                                 .sum(axis=1))
                         for i in range(n_probes)]
    return out


def to_grid(vals, spec, fill=0.0, mesh=None):
    """Flat internalField -> native blastlab array layout.

    On an obstacle-carved mesh (spec.solid mask set) the field holds
    only the fluid cells - subsetMesh keeps them in ascending original
    (x-fastest) order, so they scatter straight into the full grid;
    carved cells take `fill` (ambient value chosen by the caller).
    `mesh` (a core.refine.MeshMap - the per-time structure of a
    dynamic-AMR run) takes precedence over the per-run `spec.remap`."""
    if spec.dim == 1:
        return vals
    if mesh is not None:
        return mesh.gather(vals, fill)
    remap = getattr(spec, 'remap', None)
    if remap is not None:
        # refined mesh: every fine display cell gathers the value of the
        # foam cell covering it (-1 = carved)
        out = np.full(remap.shape, float(fill))
        m = remap >= 0
        out[m] = vals[remap[m]]
        return out
    shape = ((spec.nx, spec.ny) if spec.dim == 2
             else (spec.nx, spec.ny, spec.nz))
    solid = getattr(spec, 'solid', None)
    if solid is None:
        return vals.reshape(shape, order='F')
    full = np.full(solid.size, float(fill))
    full[~solid.flatten(order='F')] = vals
    return full.reshape(shape, order='F')
