"""Gauge time-history TSV writers, and the one reader of what they write.

Three small functions rather than one generic writer: the header formats
differ per dimension and the output files are pinned byte-for-byte by the
regression baseline. `read_gauges` (P2-25) reads any of the three back.
"""

import re

import numpy as np

#: OUT-4a: the gauge extras a blastFoam case may record (vtk_gauges), as
#: (gauge_out key, column prefix, unit), appended after every older column
#: and only when present - a run without them writes the same file as before
EXTRA_COLUMNS = (('overpressures', 'p_over', 'Pa'),
                 ('impulses', 'impulse', 'Pa s'),
                 ('temperatures', 'T', 'K'),
                 ('dyn_pressures', 'q', 'Pa'))


def _extras(gauge_out, n, label):
    """(header suffix, columns) of the OUT-4a extras for `n` gauges, each
    gauge's column named `<prefix>_<label(k)>[<unit>]`."""
    head, cols = '', []
    for key, prefix, unit in EXTRA_COLUMNS:
        extra = gauge_out.get(key)
        if extra and len(extra) == n:
            head += '\t' + '\t'.join(f'{prefix}_{label(k)}[{unit}]'
                                     for k in range(n))
            cols += list(extra)
    return head, cols


def save_gauges_1d(gauge_out, filename='gauges.txt'):
    """
    Write pressure-time history for all gauges to a tab-separated text file.

    Columns: time[s]  p_gauge1[Pa]  p_gauge2[Pa]  ...
    """
    times  = gauge_out['times']
    radii  = gauge_out['radii']
    pdata  = gauge_out['pressures']

    if len(times) == 0 or len(radii) == 0:
        print("  No gauge data to save.")
        return

    header = 'time[s]\t' + '\t'.join(f'p_r={r:.4f}m[Pa]' for r in radii)
    # OUT-4a: T and q, when the (blastFoam) run recorded them
    head, extra = _extras(gauge_out, len(radii),
                          lambda k: f'r={radii[k]:.4f}m')
    header += head
    matrix = np.column_stack([times] + list(pdata) + extra)
    np.savetxt(filename, matrix, delimiter='\t', header=header,
               comments='', fmt='%.6e')
    print(f"  Gauge data saved: {filename}  "
          f"({len(times)} rows x {len(radii)} gauges)")


def save_gauges_2d(gauge_out, filename='gauges_2d.txt'):
    """
    Write pressure-time history for all gauges to a tab-separated file.
    Columns: time[s]  p_(x,y)[Pa] ...
    """
    times  = gauge_out['times']
    points = gauge_out['points']
    pdata  = gauge_out['pressures']

    if len(times) == 0 or len(points) == 0:
        print("  No gauge data to save.")
        return

    header = 'time[s]\t' + '\t'.join(f'p_({x:.3f},{y:.3f})m[Pa]'
                                     for (x, y) in points)
    cols = list(pdata)
    # T44/N12: |U| and rho columns when the run recorded them (foam)
    for key, unit in (('speeds', 'U_mag'), ('rhos', 'rho')):
        extra = gauge_out.get(key)
        if extra and len(extra) == len(points):
            header += '\t' + '\t'.join(
                f'{unit}_({x:.3f},{y:.3f})m' for (x, y) in points)
            cols += list(extra)
    head, extra = _extras(gauge_out, len(points), lambda k: '({:.3f},{:.3f})m'
                          .format(*points[k]))
    header += head
    cols += extra
    matrix = np.column_stack([times] + cols)
    np.savetxt(filename, matrix, delimiter='\t', header=header,
               comments='', fmt='%.6e')
    print(f"  Gauge data saved: {filename}  "
          f"({len(times)} rows x {len(points)} gauges)")


def save_gauges_3d(gauge_out, filename='gauges_3d.txt'):
    """
    Write pressure-time history for all gauges to a tab-separated file.
    Columns: time[s]  p_(x,y,z)[Pa] ...
    """
    times  = gauge_out['times']
    points = gauge_out['points']
    pdata  = gauge_out['pressures']

    if len(times) == 0 or len(points) == 0:
        print("  No gauge data to save.")
        return

    header = 'time[s]\t' + '\t'.join(f'p_({x:.3f},{y:.3f},{z:.3f})m[Pa]'
                                     for (x, y, z) in points)
    cols = list(pdata)
    # T44/N12: |U| and rho columns when the run recorded them (foam)
    for key, unit in (('speeds', 'U_mag'), ('rhos', 'rho')):
        extra = gauge_out.get(key)
        if extra and len(extra) == len(points):
            header += '\t' + '\t'.join(
                f'{unit}_({x:.3f},{y:.3f},{z:.3f})m'
                for (x, y, z) in points)
            cols += list(extra)
    head, extra = _extras(gauge_out, len(points),
                          lambda k: '({:.3f},{:.3f},{:.3f})m'.format(*points[k]))
    header += head
    cols += extra
    matrix = np.column_stack([times] + cols)
    np.savetxt(filename, matrix, delimiter='\t', header=header,
               comments='', fmt='%.6e')
    print(f"  Gauge data saved: {filename}  "
          f"({len(times)} rows x {len(points)} gauges)")


# ── reading a gauge TSV back (P2-25) ─────────────────────────────────────────

#: column prefix -> gauge_out key: the pressure, the T44/N12 |U| and rho
#: columns and the OUT-4a extras, as the writers above name them
_READ_KEYS = {'p': 'pressures', 'U_mag': 'speeds', 'rho': 'rhos',
              **{prefix: key for key, prefix, _unit in EXTRA_COLUMNS}}

#: one column header: `<prefix>_<where>[<unit>]` with <where> either
#: `r=1.0000m` (1D) or `(0.300,0.800)m` (2D/3D); the unit is optional
#: (U_mag, rho). Non-greedy, so `p_over_r=...` is p_over, not p.
_COLUMN = re.compile(r'^(?P<prefix>.+?)_(?P<where>r=[^\[]*m|\([^)]*\)m)'
                     r'(?:\[[^\]]*\])?$')


def read_gauges(path):
    """The gauge_out dict a `save_gauges_1d/2d/3d` file was written from,
    to its written precision (values %.6e; radii 4 decimals, points 3):
    `times`, then `radii` (1D) or `points` (2D/3D, tuples), `pressures`
    and every other column the file holds under the key its writer read
    it from (`speeds`, `rhos`, `overpressures`, ...), one array per
    gauge. The inverse of the writers, for a model folder loaded back
    (services/model_folder.load_result). Raises ValueError for a file
    that is not a gauge TSV."""
    with open(path, encoding='utf-8') as f:
        header = f.readline().rstrip('\r\n').split('\t')
    if not header or header[0] != 'time[s]':
        raise ValueError(f'{path}: not a gauge TSV (no time[s] column)')
    cols = []
    for name in header[1:]:
        m = _COLUMN.match(name)
        if m is None or m.group('prefix') not in _READ_KEYS:
            raise ValueError(f'{path}: unknown gauge column {name!r}')
        cols.append((_READ_KEYS[m.group('prefix')], m.group('where')))
    data = np.loadtxt(path, delimiter='\t', skiprows=1, ndmin=2)
    if data.size and data.shape[1] != len(header):
        raise ValueError(f'{path}: {data.shape[1]} columns, header names '
                         f'{len(header)}')
    if not data.size:
        data = np.zeros((0, len(header)))
    wheres = [w for key, w in cols if key == 'pressures']
    out = dict(times=data[:, 0])
    if wheres and wheres[0].startswith('r='):
        out['radii'] = [float(w[2:-1]) for w in wheres]
    else:
        out['points'] = [tuple(float(v) for v in w[1:-2].split(','))
                         for w in wheres]
    for k, (key, _where) in enumerate(cols, start=1):
        out.setdefault(key, []).append(data[:, k])
    out.setdefault('pressures', [])
    return out
