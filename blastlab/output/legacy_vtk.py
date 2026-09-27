"""OUT-2: a strict, pure-NumPy reader and writer for legacy VTK files.

Owner spec docs/batches/2026-09-27-out-2-surface-layout.md: one file per
surface per sample time holding every chosen field, with the sample time
inside the file (`FIELD FieldData 1` / `TIME 1 1 float`), as Viper::Blast
writes its section and obstacle files (the two samples the owner supplied,
docs/references/viper_vtk_sample/, legacy VTK 3.0 BINARY).

The format is the "Simple Legacy Formats" of the VTK User's Guide (File
Formats for VTK): a version line, a title line, ASCII or BINARY, a DATASET
with its geometry, then CELL_DATA / POINT_DATA attributes. Binary data is
big-endian. Read here:

* datasets POLYDATA (POINTS, VERTICES, LINES, POLYGONS, TRIANGLE_STRIPS),
  UNSTRUCTURED_GRID (POINTS, CELLS, CELL_TYPES), STRUCTURED_POINTS
  (DIMENSIONS, ORIGIN, SPACING / ASPECT_RATIO) and STRUCTURED_GRID;
* dataset-level FIELD data anywhere in the geometry section;
* attributes SCALARS (+ LOOKUP_TABLE), VECTORS and FIELD arrays.

Anything else (NORMALS, TENSORS, METADATA, the 5.x OFFSETS/CONNECTIVITY
cells, a count that does not add up, trailing bytes) is refused with a
ValueError that names the place - this is the strict parser the export
verifies every written file with.

The writer always writes BINARY, version 3.0, atomically (a temp file then
os.replace), so a ParaView session that has the series open never reads
half a file. No VTK import: the GUI process never imports VTK.
"""

import os
import re

import numpy as np

#: legacy data type -> big-endian dtype. `long` / `unsigned_long` are
#: platform-sized in VTK's own reader, so they are refused, not guessed.
TYPES = {'unsigned_char': '>u1', 'char': '>i1', 'unsigned_short': '>u2',
         'short': '>i2', 'unsigned_int': '>u4', 'int': '>i4',
         'vtktypeint64': '>i8', 'vtktypeuint64': '>u8',
         'float': '>f4', 'double': '>f8'}
_FLOAT_TYPES = ('float', 'double')
DATASETS = ('POLYDATA', 'UNSTRUCTURED_GRID', 'STRUCTURED_POINTS',
            'STRUCTURED_GRID')
#: POLYDATA's cell lists
POLY_CELLS = ('VERTICES', 'LINES', 'POLYGONS', 'TRIANGLE_STRIPS')
#: the VTK cell type of a polyhedron, whose CELLS entry is a face stream
_POLYHEDRON = 42
KINDS = ('scalars', 'vectors', 'field')
VERSION = '3.0'
_VERSION_LINE = re.compile(rb'# vtk DataFile Version (\d+)\.(\d+)')
_NON_BLANK = re.compile(rb'\S')


class Array:
    """One named data array: `values` is (n,) for one component and
    (n, ncomp) otherwise; `vtk_type` its legacy type name; `kind` how it
    is written (`scalars`, `vectors` or a `field` array)."""

    __slots__ = ('name', 'values', 'vtk_type', 'kind')

    def __init__(self, name, values, vtk_type='float', kind='scalars'):
        if vtk_type not in TYPES:
            raise ValueError(f'unsupported VTK data type {vtk_type!r}')
        if kind not in KINDS:
            raise ValueError(f'not an array kind: {kind!r}')
        name = str(name)
        if not name or any(c.isspace() for c in name):
            raise ValueError(f'a VTK array name has no blanks: {name!r}')
        self.name, self.vtk_type, self.kind = name, vtk_type, kind
        self.values = np.asarray(values)

    @property
    def ncomp(self):
        return 1 if self.values.ndim == 1 else int(self.values.shape[1])

    @property
    def ntuples(self):
        return int(self.values.shape[0])

    def __repr__(self):
        return (f'Array({self.name!r}, {self.ntuples}x{self.ncomp} '
                f'{self.vtk_type}, {self.kind})')


class Block:
    """One geometry entry: `keyword` (POINTS, POLYGONS, DIMENSIONS, ...),
    its header `args` as written, and its data (`values`, None for the
    one-line entries DIMENSIONS / ORIGIN / SPACING)."""

    __slots__ = ('keyword', 'args', 'values')

    def __init__(self, keyword, args, values=None):
        self.keyword, self.args = str(keyword), tuple(str(a) for a in args)
        self.values = None if values is None else np.asarray(values)

    def __repr__(self):
        return f'Block({self.keyword} {" ".join(self.args)})'


class VtkData:
    """A parsed legacy VTK file: the dataset type, its geometry blocks in
    file order, the dataset-level field data (TIME, ...) and the cell and
    point attributes."""

    def __init__(self, dataset, geometry, field_data=(), cell_data=(),
                 point_data=(), title='', version=VERSION, binary=True):
        if dataset not in DATASETS:
            raise ValueError(f'unsupported DATASET {dataset!r}')
        self.dataset = dataset
        self.geometry = list(geometry)
        self.field_data = list(field_data)
        self.cell_data = list(cell_data)
        self.point_data = list(point_data)
        self.title, self.version, self.binary = title, version, binary

    def block(self, keyword):
        for b in self.geometry:
            if b.keyword == keyword:
                return b
        return None

    @property
    def n_points(self):
        if self.dataset == 'STRUCTURED_POINTS':
            dims = self.block('DIMENSIONS')
            return int(np.prod([int(a) for a in dims.args])) if dims else 0
        pts = self.block('POINTS')
        return int(pts.args[0]) if pts is not None else 0

    @property
    def n_cells(self):
        if self.dataset in ('STRUCTURED_POINTS', 'STRUCTURED_GRID'):
            dims = self.block('DIMENSIONS')
            if dims is None:
                return 0
            return int(np.prod([max(int(a) - 1, 1) for a in dims.args]))
        if self.dataset == 'UNSTRUCTURED_GRID':
            cells = self.block('CELLS')
            return int(cells.args[0]) if cells is not None else 0
        return sum(int(b.args[0]) for b in self.geometry
                   if b.keyword in POLY_CELLS)

    def arrays(self):
        """Every attribute array name, cell data first."""
        return [a.name for a in self.cell_data + self.point_data]


# ── reading ──────────────────────────────────────────────────────────────
class _Cursor:
    """A position in the file's bytes; lines and payloads are taken in
    turn, and running short is a ValueError naming what was being read."""

    def __init__(self, data, binary):
        self.data, self.pos, self.binary = data, 0, binary

    def at_end(self):
        return _NON_BLANK.search(self.data, self.pos) is None

    def raw_line(self):
        end = self.data.find(b'\n', self.pos)
        if end < 0:
            end = len(self.data)
        line = self.data[self.pos:end]
        self.pos = min(end + 1, len(self.data))
        return line.rstrip(b'\r')

    def line(self, what='a keyword line'):
        """The next non-blank line, stripped, as str."""
        while self.pos < len(self.data):
            ln = self.raw_line().strip()
            if ln:
                try:
                    return ln.decode('ascii')
                except UnicodeDecodeError:
                    raise ValueError(f'binary bytes where {what} was '
                                     f'expected (at byte {self.pos})') \
                        from None
        raise ValueError(f'the file ends where {what} was expected')

    def peek(self):
        save = self.pos
        try:
            return None if self.at_end() else self.line()
        finally:
            self.pos = save

    def values(self, count, vtk_type, what):
        """`count` numbers of `vtk_type`: raw big-endian bytes in a binary
        file, whitespace-separated tokens (never sharing a line with a
        keyword) in an ASCII one. Native-order array."""
        if vtk_type not in TYPES:
            raise ValueError(f'{what}: unsupported data type {vtk_type!r}')
        dt = np.dtype(TYPES[vtk_type])
        if count < 0:
            raise ValueError(f'{what}: negative count {count}')
        if self.binary:
            n = count * dt.itemsize
            if self.pos + n > len(self.data):
                raise ValueError(f'{what}: the file ends inside its data '
                                 f'({len(self.data) - self.pos} of {n} '
                                 f'bytes)')
            arr = np.frombuffer(self.data, dtype=dt, count=count,
                                offset=self.pos)
            self.pos += n
            # the one newline a writer puts after a binary block
            if self.data[self.pos:self.pos + 1] == b'\n':
                self.pos += 1
            return arr.astype(dt.newbyteorder('='))
        tokens = []
        while len(tokens) < count:
            if self.pos >= len(self.data):
                raise ValueError(f'{what}: the file ends after '
                                 f'{len(tokens)} of {count} values')
            tokens.extend(self.raw_line().split())
        if len(tokens) != count:
            raise ValueError(f'{what}: {len(tokens)} values where {count} '
                             f'were declared')
        kind = np.float64 if vtk_type in _FLOAT_TYPES else np.int64
        try:
            arr = np.array(tokens, dtype=np.bytes_).astype(kind) \
                if tokens else np.zeros(0, kind)
        except ValueError as exc:
            raise ValueError(f'{what}: not a number ({exc})') from None
        return arr


def _int(tok, what):
    try:
        v = int(tok)
    except (TypeError, ValueError):
        raise ValueError(f'{what}: {tok!r} is not a whole number') from None
    if v < 0:
        raise ValueError(f'{what}: negative count {v}')
    return v


def _words(line, n, what, most=None):
    w = line.split()
    if len(w) < n or len(w) > (most or n):
        raise ValueError(f'malformed {what} line: {line!r}')
    return w


def _walk(conn, n, what, n_points=None):
    """Check a cell list `conn` (count, ids..., count, ids...) holds exactly
    `n` entries and, given `n_points`, that every id is a point."""
    size = conn.size
    c = conn.tolist()
    pos, starts = 0, []
    for _ in range(n):
        if pos >= size:
            raise ValueError(f'{what}: {n} cells declared, the list ends '
                             f'after {len(starts)}')
        m = c[pos]
        if m < 0 or pos + 1 + m > size:
            raise ValueError(f'{what}: a bad cell size {m} at entry '
                             f'{len(starts)}')
        starts.append(pos)
        pos += 1 + m
    if pos != size:
        raise ValueError(f'{what}: {size - pos} values after the last cell')
    if n_points is not None and size:
        mask = np.ones(size, dtype=bool)
        mask[starts] = False
        ids = conn[mask]
        if ids.size and (ids.min() < 0 or ids.max() >= n_points):
            raise ValueError(f'{what}: a point id outside 0..{n_points - 1}')


def _read_field(cur, line, n_expected, what):
    """A FIELD block: `FIELD <name> <n>` then n arrays `<name> <ncomp>
    <ntuples> <type>` + data. `n_expected` is the tuple count each array
    must have (None at dataset level)."""
    w = _words(line, 3, 'FIELD')
    n_arr = _int(w[2], 'FIELD')
    out = []
    for _ in range(n_arr):
        hdr = cur.line(f'a {what} FIELD array header')
        h = _words(hdr, 4, 'FIELD array')
        name, ncomp = h[0], _int(h[1], f'FIELD array {h[0]}')
        ntup, vtype = _int(h[2], f'FIELD array {h[0]}'), h[3].lower()
        if ncomp < 1:
            raise ValueError(f'FIELD array {name}: {ncomp} components')
        if n_expected is not None and ntup != n_expected:
            raise ValueError(f'{what} array {name}: {ntup} tuples, the '
                             f'dataset has {n_expected}')
        vals = cur.values(ncomp * ntup, vtype, f'{what} array {name}')
        if ncomp > 1:
            vals = vals.reshape(ntup, ncomp)
        out.append(Array(name, vals, vtype, 'field'))
    return out


def _geometry(cur, dataset):
    """The geometry section up to CELL_DATA / POINT_DATA / the end:
    (blocks, dataset field data)."""
    blocks, fdata, seen = [], [], set()
    allowed = {'POLYDATA': ('POINTS',) + POLY_CELLS,
               'UNSTRUCTURED_GRID': ('POINTS', 'CELLS', 'CELL_TYPES'),
               'STRUCTURED_POINTS': ('DIMENSIONS', 'ORIGIN', 'SPACING',
                                     'ASPECT_RATIO'),
               'STRUCTURED_GRID': ('DIMENSIONS', 'POINTS')}[dataset]
    n_points = None
    while True:
        nxt = cur.peek()
        if nxt is None or nxt.split()[0].upper() in ('CELL_DATA',
                                                      'POINT_DATA'):
            break
        line = cur.line()
        kw = line.split()[0].upper()
        if kw == 'FIELD':
            fdata += _read_field(cur, line, None, 'dataset')
            continue
        if kw not in allowed:
            raise ValueError(f'{dataset}: unexpected keyword {kw!r}')
        if kw in seen:
            raise ValueError(f'{dataset}: {kw} given twice')
        seen.add(kw)
        if kw == 'POINTS':
            w = _words(line, 3, 'POINTS')
            n_points = _int(w[1], 'POINTS')
            vals = cur.values(3 * n_points, w[2].lower(), 'POINTS')
            blocks.append(Block('POINTS', (n_points, w[2].lower()),
                                vals.reshape(n_points, 3)))
        elif kw in POLY_CELLS or kw == 'CELLS':
            w = _words(line, 3, kw)
            n, size = _int(w[1], kw), _int(w[2], kw)
            vals = cur.values(size, 'int', kw)
            _walk(vals, n, kw, n_points if kw != 'CELLS' else None)
            blocks.append(Block(kw, (n, size), vals))
        elif kw == 'CELL_TYPES':
            w = _words(line, 2, 'CELL_TYPES')
            n = _int(w[1], 'CELL_TYPES')
            cells = [b for b in blocks if b.keyword == 'CELLS']
            if cells and n != int(cells[0].args[0]):
                raise ValueError(f'CELL_TYPES {n} for CELLS '
                                 f'{cells[0].args[0]}')
            vals = cur.values(n, 'int', 'CELL_TYPES')
            blocks.append(Block(kw, (n,), vals))
        elif kw == 'DIMENSIONS':
            w = _words(line, 4, 'DIMENSIONS')
            dims = [_int(x, 'DIMENSIONS') for x in w[1:]]
            if min(dims) < 1:
                raise ValueError(f'DIMENSIONS {dims}')
            blocks.append(Block(kw, dims))
        else:                                   # ORIGIN, SPACING, ASPECT_RATIO
            w = _words(line, 4, kw)
            try:
                [float(x) for x in w[1:]]
            except ValueError:
                raise ValueError(f'malformed {kw} line: {line!r}') from None
            blocks.append(Block('SPACING' if kw == 'ASPECT_RATIO' else kw,
                                w[1:]))
    vd = VtkData(dataset, blocks, fdata)
    if dataset == 'UNSTRUCTURED_GRID':
        cells, types = vd.block('CELLS'), vd.block('CELL_TYPES')
        if (cells is None) != (types is None):
            raise ValueError('UNSTRUCTURED_GRID: CELLS and CELL_TYPES go '
                             'together')
        if cells is not None:
            if int(types.args[0]) != int(cells.args[0]):
                raise ValueError(f'CELL_TYPES {types.args[0]} for CELLS '
                                 f'{cells.args[0]}')
            if not (types.values == _POLYHEDRON).any():
                _walk(cells.values, int(cells.args[0]), 'CELLS', n_points)
    if dataset == 'STRUCTURED_GRID' and vd.block('POINTS') is not None \
            and vd.n_points != int(np.prod([int(a) for a in
                                            vd.block('DIMENSIONS').args])):
        raise ValueError('STRUCTURED_GRID: POINTS does not match DIMENSIONS')
    return vd


def _attributes(cur, vd):
    target, count = None, None
    while not cur.at_end():
        line = cur.line()
        kw = line.split()[0].upper()
        if kw in ('CELL_DATA', 'POINT_DATA'):
            n = _int(_words(line, 2, kw)[1], kw)
            want = vd.n_cells if kw == 'CELL_DATA' else vd.n_points
            if n != want:
                raise ValueError(f'{kw} {n}, the dataset has {want}')
            target = vd.cell_data if kw == 'CELL_DATA' else vd.point_data
            count = n
            continue
        if target is None:
            raise ValueError(f'{kw} before CELL_DATA / POINT_DATA')
        if kw == 'SCALARS':
            w = _words(line, 3, 'SCALARS', most=4)
            ncomp = _int(w[3], 'SCALARS') if len(w) == 4 else 1
            if not 1 <= ncomp <= 4:
                raise ValueError(f'SCALARS {w[1]}: {ncomp} components')
            lut = cur.line('LOOKUP_TABLE')
            if lut.split()[0].upper() != 'LOOKUP_TABLE' or \
                    len(lut.split()) != 2:
                raise ValueError(f'SCALARS {w[1]}: no LOOKUP_TABLE line')
            vals = cur.values(ncomp * count, w[2].lower(), f'SCALARS {w[1]}')
            if ncomp > 1:
                vals = vals.reshape(count, ncomp)
            target.append(Array(w[1], vals, w[2].lower(), 'scalars'))
        elif kw == 'VECTORS':
            w = _words(line, 3, 'VECTORS')
            vals = cur.values(3 * count, w[2].lower(), f'VECTORS {w[1]}')
            target.append(Array(w[1], vals.reshape(count, 3), w[2].lower(),
                                'vectors'))
        elif kw == 'FIELD':
            target += _read_field(cur, line, count, kw.lower())
        else:
            raise ValueError(f'unsupported attribute keyword {kw!r}')
    names = vd.arrays()
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise ValueError(f'array name(s) given twice: {dup}')


def parse(data):
    """A VtkData from the bytes of a legacy VTK file. ValueError, naming
    the place, on anything this strict reader does not accept."""
    data = bytes(data)
    head = _Cursor(data, binary=False)
    m = _VERSION_LINE.fullmatch(head.raw_line().strip())
    if not m:
        raise ValueError('not a legacy VTK file (no "# vtk DataFile '
                         'Version" line)')
    version = f'{int(m.group(1))}.{int(m.group(2))}'
    if int(m.group(1)) >= 5:
        raise ValueError(f'legacy VTK {version}: the 5.x cell layout is '
                         f'not supported')
    title = head.raw_line().decode('ascii', 'replace')
    fmt = head.line('ASCII / BINARY').upper()
    if fmt not in ('ASCII', 'BINARY'):
        raise ValueError(f'the third line must be ASCII or BINARY: {fmt!r}')
    cur = _Cursor(data, binary=fmt == 'BINARY')
    cur.pos = head.pos
    w = cur.line('DATASET').split()
    if len(w) != 2 or w[0].upper() != 'DATASET':
        raise ValueError(f'expected "DATASET <type>": {" ".join(w)!r}')
    if w[1].upper() not in DATASETS:
        raise ValueError(f'unsupported DATASET {w[1]!r}')
    vd = _geometry(cur, w[1].upper())
    vd.title, vd.version, vd.binary = title, version, fmt == 'BINARY'
    _attributes(cur, vd)
    return vd


def read(path):
    """parse() of the file at `path`."""
    with open(path, 'rb') as f:
        return parse(f.read())


def scan(path):
    """The keyword lines of a BINARY legacy VTK file, [(offset, line)],
    read without loading its data: every payload is skipped by the size
    its header line gives, and the walk must end exactly at the end of
    the file. For a structure check of large reference files (the Viper
    samples); parse() is the strict reader. ValueError on a structure it
    cannot walk."""
    out = []
    with open(path, 'rb') as f:
        size = os.fstat(f.fileno()).st_size

        def line(what, raw=False):
            while True:
                off = f.tell()
                ln = f.readline()
                if not ln:
                    if raw:
                        return None
                    raise ValueError(f'the file ends where {what} was '
                                     f'expected')
                s = ln.strip()
                if not s and not raw:
                    continue
                try:
                    txt = s.decode('ascii')
                except UnicodeDecodeError:
                    raise ValueError(f'binary bytes where {what} was '
                                     f'expected (at byte {off})') from None
                out.append((off, txt))
                return txt

        def skip(count, vtype, what):
            if vtype not in TYPES:
                raise ValueError(f'{what}: unsupported type {vtype!r}')
            n = count * np.dtype(TYPES[vtype]).itemsize
            if f.tell() + n > size:
                raise ValueError(f'{what}: the file ends inside its data')
            f.seek(n, 1)
            if f.read(1) not in (b'\n', b''):
                f.seek(-1, 1)

        if not _VERSION_LINE.fullmatch(line('the version line').encode()):
            raise ValueError('not a legacy VTK file')
        line('the title', raw=True)
        if line('ASCII / BINARY').upper() != 'BINARY':
            raise ValueError('scan() reads BINARY files only')
        count = None
        while f.tell() < size:
            txt = line('a keyword line', raw=True)
            if txt is None:
                break
            w = txt.split()
            if not w:
                continue
            kw = w[0].upper()
            if kw == 'DATASET' or kw in ('DIMENSIONS', 'ORIGIN', 'SPACING',
                                         'ASPECT_RATIO'):
                continue
            if kw == 'POINTS':
                skip(3 * _int(w[1], kw), w[2].lower(), kw)
            elif kw in POLY_CELLS or kw == 'CELLS':
                skip(_int(w[2], kw), 'int', kw)
            elif kw == 'CELL_TYPES':
                skip(_int(w[1], kw), 'int', kw)
            elif kw in ('CELL_DATA', 'POINT_DATA'):
                count = _int(w[1], kw)
            elif kw == 'FIELD':
                for _ in range(_int(w[2], kw)):
                    h = line('a FIELD array header').split()
                    skip(_int(h[1], h[0]) * _int(h[2], h[0]), h[3].lower(),
                         h[0])
            elif kw == 'SCALARS' and count is not None:
                ncomp = _int(w[3], kw) if len(w) > 3 else 1
                if line('LOOKUP_TABLE').split()[0].upper() != 'LOOKUP_TABLE':
                    raise ValueError(f'SCALARS {w[1]}: no LOOKUP_TABLE')
                skip(count * ncomp, w[2].lower(), f'SCALARS {w[1]}')
            elif kw == 'VECTORS' and count is not None:
                skip(3 * count, w[2].lower(), f'VECTORS {w[1]}')
            else:
                raise ValueError(f'unexpected keyword {kw!r} at byte '
                                 f'{out[-1][0]}')
    return out


# ── writing ──────────────────────────────────────────────────────────────
def _be(values, vtk_type):
    return np.ascontiguousarray(values, dtype=TYPES[vtk_type]).tobytes()


def _array_chunks(a, count):
    if a.ntuples != count:
        raise ValueError(f'array {a.name}: {a.ntuples} tuples for {count}')
    if a.kind == 'scalars':
        if not 1 <= a.ncomp <= 4:
            raise ValueError(f'SCALARS {a.name}: {a.ncomp} components')
        yield (f'SCALARS {a.name} {a.vtk_type} {a.ncomp}\n'
               f'LOOKUP_TABLE default\n').encode('ascii')
    elif a.kind == 'vectors':
        if a.ncomp != 3:
            raise ValueError(f'VECTORS {a.name}: {a.ncomp} components')
        yield f'VECTORS {a.name} {a.vtk_type}\n'.encode('ascii')
    yield _be(a.values, a.vtk_type)
    yield b'\n'


def _field_chunks(label, arrays, count=None):
    yield f'FIELD {label} {len(arrays)}\n'.encode('ascii')
    for a in arrays:
        if count is not None and a.ntuples != count:
            raise ValueError(f'array {a.name}: {a.ntuples} tuples for '
                             f'{count}')
        yield (f'{a.name} {a.ncomp} {a.ntuples} {a.vtk_type}\n'
               .encode('ascii'))
        yield _be(a.values, a.vtk_type)
        yield b'\n'


def _attr_chunks(arrays, count):
    """SCALARS / VECTORS in order; each run of `field` arrays as one FIELD
    block."""
    run = []
    for a in list(arrays) + [None]:
        if a is not None and a.kind == 'field':
            run.append(a)
            continue
        if run:
            yield from _field_chunks('attributes', run, count)
            run = []
        if a is not None:
            yield from _array_chunks(a, count)


def chunks(vd):
    """The bytes of `vd` as legacy VTK 3.0 BINARY, in pieces. The dataset
    field data (TIME) follows the geometry, as the Viper samples place
    it."""
    title = str(vd.title or 'blastlab').replace('\n', ' ')[:255]
    yield (f'# vtk DataFile Version {VERSION}\n{title}\nBINARY\n'
           f'DATASET {vd.dataset}\n').encode('ascii')
    for b in vd.geometry:
        yield f'{b.keyword} {" ".join(b.args)}\n'.encode('ascii')
        if b.values is None:
            continue
        vtype = b.args[1] if b.keyword == 'POINTS' else 'int'
        yield _be(b.values, vtype)
        yield b'\n'
    if vd.field_data:
        yield from _field_chunks('FieldData', vd.field_data)
    if vd.cell_data:
        yield f'CELL_DATA {vd.n_cells}\n'.encode('ascii')
        yield from _attr_chunks(vd.cell_data, vd.n_cells)
    if vd.point_data:
        yield f'POINT_DATA {vd.n_points}\n'.encode('ascii')
        yield from _attr_chunks(vd.point_data, vd.n_points)


def to_bytes(vd):
    return b''.join(chunks(vd))


def write(path, vd):
    """Write `vd` to `path` (BINARY, big-endian) via `<path>.tmp` +
    os.replace; the old file stays whole when anything fails. Returns the
    byte count."""
    tmp = path + '.tmp'
    n = 0
    try:
        with open(tmp, 'wb') as f:
            for piece in chunks(vd):
                f.write(piece)
                n += len(piece)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return n


# ── comparing, merging ───────────────────────────────────────────────────
def _same_values(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        return False
    if a.dtype.kind == 'f' or b.dtype.kind == 'f':
        return bool(np.array_equal(a, b, equal_nan=True))
    return bool(np.array_equal(a, b))


def same_geometry(a, b):
    """None when `a` and `b` have one geometry (dataset, blocks, header
    numbers and every point / cell value), else what differs."""
    if a.dataset != b.dataset:
        return f'DATASET {a.dataset} vs {b.dataset}'
    ka = [x.keyword for x in a.geometry]
    kb = [x.keyword for x in b.geometry]
    if ka != kb:
        return f'blocks {ka} vs {kb}'
    for x, y in zip(a.geometry, b.geometry):
        if x.keyword in ('ORIGIN', 'SPACING'):
            if [float(v) for v in x.args] != [float(v) for v in y.args]:
                return f'{x.keyword} {x.args} vs {y.args}'
            continue
        if x.args != y.args:
            return f'{x.keyword} {" ".join(x.args)} vs {" ".join(y.args)}'
        if (x.values is None) != (y.values is None) or (
                x.values is not None
                and not _same_values(x.values, y.values)):
            return f'{x.keyword} values differ'
    return None


def _cast(a):
    """`a`'s values as they are after a write (its legacy type)."""
    return np.asarray(a.values).astype(np.dtype(TYPES[a.vtk_type])
                                       .newbyteorder('='))


def compare(got, want):
    """None when the file read back (`got`) holds exactly what was written
    (`want`, values compared after the cast to their legacy type), else
    what differs."""
    why = same_geometry(got, _written(want))
    if why:
        return why
    for label, ga, wa in (('field data', got.field_data, want.field_data),
                          ('cell data', got.cell_data, want.cell_data),
                          ('point data', got.point_data, want.point_data)):
        gn = [(a.name, a.kind, a.vtk_type, a.ncomp) for a in ga]
        wn = [(a.name, a.kind, a.vtk_type, a.ncomp) for a in wa]
        if gn != wn:
            return f'{label}: {gn} vs {wn}'
        for x, y in zip(ga, wa):
            if not _same_values(x.values, _cast(y)):
                return f'{label} {x.name}: values differ'
    return None


def _written(vd):
    """`vd`'s geometry as a reader sees it after a write (point
    coordinates cast to their declared type)."""
    blocks = []
    for b in vd.geometry:
        v = b.values
        if v is not None:
            vtype = b.args[1] if b.keyword == 'POINTS' else 'int'
            v = np.asarray(v).astype(np.dtype(TYPES[vtype])
                                     .newbyteorder('='))
        blocks.append(Block(b.keyword, b.args, v))
    return VtkData(vd.dataset, blocks)


def verify(path, want):
    """Read `path` back with the strict parser and check it holds `want`;
    ValueError (what differs) otherwise."""
    got = read(path)
    why = compare(got, want)
    if why:
        raise ValueError(f'{os.path.basename(path)} read back wrong: {why}')
    return got


def merge(parts):
    """One VtkData from per-field files of one surface and one time:
    `parts` is [(label, VtkData)]. The first part's geometry, and every
    part's cell and point arrays in turn (kept as cell or point data, as
    the source holds them - nothing is interpolated). ValueError when the
    parts do not share one geometry or an array name repeats."""
    parts = list(parts)
    if not parts:
        raise ValueError('nothing to merge')
    label0, first = parts[0]
    out = VtkData(first.dataset, first.geometry, title=first.title)
    for label, vd in parts:
        why = same_geometry(first, vd)
        if why:
            raise ValueError(f'the per-field files differ in geometry '
                             f'({label} vs {label0}): {why}')
        out.cell_data += vd.cell_data
        out.point_data += vd.point_data
    names = out.arrays()
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise ValueError(f'array name(s) in more than one file: {dup}')
    return out


def with_time(vd, t):
    """`vd` with the sample time `t` [s] as its dataset field data
    `TIME 1 1 float`, as the Viper samples carry it (any earlier TIME
    replaced)."""
    rest = [a for a in vd.field_data if a.name != 'TIME']
    vd.field_data = [Array('TIME', np.array([float(t)], dtype=np.float32),
                           'float', 'field')] + rest
    return vd
