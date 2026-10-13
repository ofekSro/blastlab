"""GUI-16 round 2, U5: the unchecked-radii warning leads with the input,
not the exception (batch docs/batches/2026-10-13-gui-final-round2.md, B2).

The same two failures as test_case_validate.py's B11 checks: the uniform
base-cell layout raises (every radius unchecked), and one point's level
raises (that point unchecked). Each warning keeps its prefix and `not
checked`, names the domain size and the cell size before any exception
class, and carries the exception last as `(detail: <Type>: <msg>)`
(D-R10, owner Q4). No WSL.

Run:  cd blastlab/tests && python test_det_radii_text.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import grid, refine                           # noqa: E402
from blastlab.core.case import Case2D, validate_case             # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def unchecked(rep):
    return [w for w in rep.warnings if 'not checked' in w]


def reads_input_first(w, exc_name, domain):
    """The domain size and the cell size, with their values, come before
    the exception class, and the exception is the last clause."""
    at = w.find(exc_name)
    d = w.find(f'domain size ({domain})')
    c = re.search(r'cell size \([0-9.e+-]+ mm\)', w)
    return (0 <= d < at and c is not None and c.start() < at
            and w.rstrip().endswith(')')
            and w.rfind('(detail: ') == at - len('(detail: ')
            and 'could not be computed' in w[:at])


def base_cell_raises():
    print('\nthe base-cell layout raises: every radius unchecked')
    base = dict(geometry='axisymmetric', Lx=2.0, Ly=2.0, cell_size_m=0.02,
                charge=1.0, center=(0.0, 1.0), solver='blastfoam',
                material='TNT', gauges=[(1.0, 1.0)],
                det_points=[(0.0, 0.95), (0.0, 1.05)])
    real = grid._faces_shared

    def boom(*_a, **_k):
        raise ZeroDivisionError('float division by zero')
    grid._faces_shared = boom
    try:
        r = validate_case(Case2D(det_radii=[0.02, 0.001], **base))
    finally:
        grid._faces_shared = real
    un = unchecked(r)
    w = un[0] if len(un) == 1 else ''
    check('one warning, prefix `Ignition radii not checked`',
          w.startswith('Ignition radii not checked'), str(un))
    check('names the domain size (2 x 2 m) and the cell size before '
          'ZeroDivisionError, the exception last as (detail: ...)',
          reads_input_first(w, 'ZeroDivisionError', '2 x 2 m'), w)
    check('the exception text is still there (B11)',
          'float division by zero' in w, w)


def level_raises():
    print('\none point\'s level raises: that point unchecked')
    zoned = dict(geometry='planar', Lx=4.0, Ly=4.0, cell_size_m=0.1,
                 charge=100.0, center=(2.0, 2.0), gauges=[(3.2, 2.0)],
                 n_snapshots=2, record_frames=60, solver='blastfoam',
                 material='TNT', amr_levels=0,
                 refine_zones=[(1.5, 2.5, 1.5, 2.5, 1)],
                 det_points=[(2.0, 2.0), (2.0, 2.0)],
                 bcs=dict(x_lo='terminate', x_hi='terminate',
                          y_lo='terminate', y_hi='terminate'))
    real_level = refine.level_at
    calls = []

    def level_boom(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise ZeroDivisionError('no level')
        return real_level(*a, **k)
    refine.level_at = level_boom
    try:
        r = validate_case(Case2D(det_radii=[0.02, 0.001], **zoned))
    finally:
        refine.level_at = real_level
    un = unchecked(r)
    w = un[0] if len(un) == 1 else ''
    check('one warning, prefix `Detonation point 1: ignition radius not '
          'checked`',
          w.startswith('Detonation point 1: ignition radius not checked'),
          str(un))
    check('names the domain size (4 x 4 m) and the base cell size before '
          'ZeroDivisionError, the exception last as (detail: ...)',
          reads_input_first(w, 'ZeroDivisionError', '4 x 4 m'), w)
    check('point 2 is still checked and refused',
          any(e.startswith('Detonation point 2') for e in r.errors),
          str(r.errors))


def level_known():
    print('\nthe level is known when the layout fails: it is named')
    from blastlab.models.result import ValidationReport
    from blastlab.services import validation as V
    rep = ValidationReport()
    V._det_radii_unchecked(rep, ValueError('bad'), 2, dims=(4.0, 4.0),
                           dx=0.1, level=3, h=0.0125)
    w = rep.warnings[0] if rep.warnings else ''
    check('level 3 and its 12.5 mm cells come before the detail',
          'level 3' in w and '12.5 mm' in w
          and w.find('12.5 mm') < w.find('(detail: ValueError: bad)'), w)
    rep = ValidationReport()
    V._det_radii_unchecked(rep, TypeError('x'), dims=None, dx=None)
    w = rep.warnings[0] if rep.warnings else ''
    check('no values at hand: the plain words, still the detail last',
          w.startswith('Ignition radii not checked')
          and 'from the domain size and cell size' in w
          and w.rstrip().endswith('(detail: TypeError: x)'), w)


if __name__ == '__main__':
    base_cell_raises()
    level_raises()
    level_known()
    print()
    print('DET RADII TEXT: ' + ('PASS' if not FAIL else
                                f'FAIL ({len(FAIL)}): ' + ', '.join(FAIL)))
    sys.exit(1 if FAIL else 0)
