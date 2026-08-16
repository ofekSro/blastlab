"""Gauge time-history TSV writers.

Three small functions rather than one generic writer: the header formats
differ per dimension and the output files are pinned byte-for-byte by the
regression baseline.
"""

import numpy as np


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
    matrix = np.column_stack([times] + pdata)
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
    matrix = np.column_stack([times] + pdata)
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
    matrix = np.column_stack([times] + pdata)
    np.savetxt(filename, matrix, delimiter='\t', header=header,
               comments='', fmt='%.6e')
    print(f"  Gauge data saved: {filename}  "
          f"({len(times)} rows x {len(points)} gauges)")
