"""OUT-2: the VTK output case keys and their validation (no WSL, no GUI).

docs/batches/2026-09-27-out-2-vtk-output.md, Steps 1 and 2.

  A  (V1a) case keys, save / load
     * the three default cases save byte for byte as they did at c73d4fc
       (SHA-256 of save_case, taken from that commit's own tree);
     * an `on` family round-trips every key through save_case/load_case,
       with the planes, fields and value normalised;
     * `on: false` (and None) is not written;
     * a 1D file carrying `vtk_surfaces` is refused as an unknown key, and
       an unknown key inside a family is refused too.
  B  (V1b) validation - see test_validation below.

Run:  cd blastlab/tests && python test_vtk_case.py
"""
import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import (Case1D, Case2D, Case3D,        # noqa: E402
                                case_from_dict, case_to_dict, load_case,
                                save_case)
from blastlab.models import case as mcase                      # noqa: E402

FAILS = []

#: save_case(cls()) at c73d4fc (OUT-1 merged), measured on that commit's
#: own tree before OUT-2 touched models/case.py: (bytes, sha256)
DEFAULT_SAVES = {
    'Case1D': (537, 'ebeec40f5371e84fe3b67c9467fc1152'
                    'ae72610ab814e62f9fc1148dcf82aa40'),
    'Case2D': (1256, '7071cf98b62eeeef726f6a3e26da99ac'
                     '47d56d0a3f4f65311b819304d9f00bdf'),
    'Case3D': (1437, 'ff3e3925cc2cd12bd5af6c64993a1804'
                     '7eeedd6ce3ab3ff4f7a65bfd294f27d0'),
}


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def saved_bytes(case):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'case.json')
        save_case(case, path)
        with open(path, 'rb') as f:
            return f.read()


def roundtrip(case):
    """(the JSON dict save_case wrote, the case load_case read back)."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'case.json')
        save_case(case, path)
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
        return raw, load_case(path)


SURF = {'on': True, 'mode': 'time', 'value': 0.5,
        'fields': ['p', 'pMax'], 'obstacle_fields': ['p', 'impulse'],
        'planes': [['y', 1.4], ['z', 0.5]]}
VOL = {'on': True, 'mode': 'step', 'value': 25, 'fields': ['p', 'rho', 'U']}


def test_keys():
    print('\nA: case keys, save / load')
    for cls in (Case1D, Case2D, Case3D):
        b = saved_bytes(cls())
        n, sha = DEFAULT_SAVES[cls.__name__]
        check(f'{cls.__name__}(): save_case is byte-identical to c73d4fc',
              len(b) == n and hashlib.sha256(b).hexdigest() == sha,
              f'{len(b)} B {hashlib.sha256(b).hexdigest()}')
    check('Case1D has vtk_volumes and no vtk_surfaces',
          hasattr(Case1D(), 'vtk_volumes')
          and not hasattr(Case1D(), 'vtk_surfaces'))

    c3 = Case3D(solver='blastfoam', vtk_surfaces=dict(SURF),
                vtk_volumes=dict(VOL))
    raw, back = roundtrip(c3)
    check('3D, both families on: every key written, VERSION still 13',
          raw.get('vtk_surfaces') == SURF and raw.get('vtk_volumes') == VOL
          and raw.get('version') == 13, str(raw.get('vtk_surfaces')))
    check('   and read back unchanged',
          back.vtk_surfaces == SURF and back.vtk_volumes == VOL,
          f'{back.vtk_surfaces} {back.vtk_volumes}')
    check('   in the canonical key order',
          list(back.vtk_surfaces) == list(mcase.VTK_SURFACE_KEYS)
          and list(back.vtk_volumes) == list(mcase.VTK_VOLUME_KEYS))

    c2 = Case2D(solver='blastfoam',
                obstacles=[(2.0, 2.4, 0.0, 1.6)],
                vtk_surfaces={'on': True, 'mode': 'step', 'value': 10,
                              'obstacle_fields': ['p']},
                vtk_volumes={'on': True, 'mode': 'time', 'value': 1,
                             'fields': ['p']})
    raw2, back2 = roundtrip(c2)
    check('2D: a family written without some keys comes back complete',
          back2.vtk_surfaces == {'on': True, 'mode': 'step', 'value': 10,
                                 'fields': [], 'obstacle_fields': ['p'],
                                 'planes': []}, str(back2.vtk_surfaces))
    check('   Time-mode value is a float in ms, Step-mode value an int',
          isinstance(back2.vtk_volumes['value'], float)
          and back2.vtk_volumes['value'] == 1.0
          and type(back2.vtk_surfaces['value']) is int)

    d = case_to_dict(Case3D())
    d['vtk_surfaces'] = {'on': True, 'mode': 'step', 'value': 25.0,
                         'fields': ('p',), 'planes': [('x', '0.7')]}
    got = case_from_dict(json.loads(json.dumps(d))).vtk_surfaces
    check('case_from_dict normalises planes to [axis, float], fields to '
          'list of str, a whole Step value to int',
          got['planes'] == [['x', 0.7]] and got['fields'] == ['p']
          and got['value'] == 25 and type(got['value']) is int, str(got))
    d['vtk_surfaces'] = {'on': True, 'mode': 'step', 'value': 2.5,
                         'fields': ['p']}
    got = case_from_dict(json.loads(json.dumps(d))).vtk_surfaces
    check('   a fractional Step value is kept, for validation to refuse',
          got['value'] == 2.5)

    for off in ({'on': False, 'mode': 'time', 'value': 1.0,
                 'fields': ['p']}, None):
        for cls in (Case2D, Case3D):
            c = cls(vtk_surfaces=off, vtk_volumes=off)
            d = case_to_dict(c)
            check(f'{cls.__name__}: {off and "on: false" or "None"} is not '
                  f'written',
                  'vtk_surfaces' not in d and 'vtk_volumes' not in d)
        d1 = case_to_dict(Case1D(vtk_volumes=off))
        check(f'Case1D: {off and "on: false" or "None"} is not written',
              'vtk_volumes' not in d1)
    check('   and an on:false case saves byte-identical to the default',
          saved_bytes(Case3D(vtk_volumes={'on': False}))
          == saved_bytes(Case3D()))

    d1 = case_to_dict(Case1D())
    d1['vtk_surfaces'] = dict(SURF)
    try:
        case_from_dict(d1)
        check('Case1D refuses vtk_surfaces', False)
    except ValueError as exc:
        check('Case1D refuses vtk_surfaces ("Unknown case keys")',
              'Unknown case keys' in str(exc), str(exc))
    d1 = case_to_dict(Case1D())
    d1['vtk_volumes'] = dict(VOL)
    back1 = case_from_dict(json.loads(json.dumps(d1)))
    check('Case1D keeps vtk_volumes', back1.vtk_volumes == VOL)

    d = case_to_dict(Case3D())
    d['vtk_volumes'] = dict(VOL, planes=[['y', 1.0]])
    try:
        case_from_dict(d)
        check('vtk_volumes refuses a surfaces-only key (planes)', False)
    except ValueError as exc:
        check('vtk_volumes refuses a surfaces-only key (planes)',
              'Unknown vtk_volumes keys' in str(exc), str(exc))
    d['vtk_volumes'] = ['p']
    try:
        case_from_dict(d)
        check('a family that is not an object is refused', False)
    except ValueError as exc:
        check('a family that is not an object is refused',
              'must be an object' in str(exc), str(exc))


def main():
    test_keys()


if __name__ == '__main__':
    main()
    print()
    print('VTK CASE: ' + ('PASS' if not FAILS else
                          f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
