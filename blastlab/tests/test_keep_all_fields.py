"""OUT-3: the "Keep all fields in WSL" case key and its validation notes
(no WSL, no GUI).

docs/batches/2026-09-27-out-3-newest-fields.md, Step 1.

  * the three default cases save byte for byte as before (the pinned
    hashes of test_vtk_case.DEFAULT_SAVES), with no `keep_all_fields` key;
  * `keep_all_fields = True` round-trips through save_case / load_case;
  * validation: nothing when the box is off; a native-mode note, a 1D
    note (P9) and a 2D/3D disk-estimate note when it is ticked.

Run:  cd blastlab/tests && python test_keep_all_fields.py
"""
import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import (Case1D, Case2D, Case3D,        # noqa: E402
                                load_case, save_case, validate_case)
from test_vtk_case import DEFAULT_SAVES                        # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def saved(case):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'case.json')
        save_case(case, path)
        with open(path, 'rb') as f:
            data = f.read()
        return data, load_case(path)


def test_keys():
    print('A: case key')
    for cls in (Case1D, Case2D, Case3D):
        data, _ = saved(cls())
        size, sha = DEFAULT_SAVES[cls.__name__]
        check(f'{cls.__name__} default save byte-identical',
              (len(data), hashlib.sha256(data).hexdigest()) == (size, sha))
        check(f'{cls.__name__} default has no keep_all_fields key',
              'keep_all_fields' not in json.loads(data))
        data, back = saved(cls(solver='blastfoam', keep_all_fields=True))
        check(f'{cls.__name__} True is written',
              json.loads(data).get('keep_all_fields') is True)
        check(f'{cls.__name__} True round-trips',
              back.keep_all_fields is True)


def notes(case):
    return [m for m in validate_case(case).notes if 'Keep all fields' in m]


def test_validation():
    print('\nB: validation')
    base3 = dict(solver='blastfoam', t_end=0.002)
    base2 = dict(solver='blastfoam', t_end=0.002,
                 obstacles=[(2.0, 2.4, 0.0, 1.6)])
    base1 = dict(solver='blastfoam', radius_m=5.0, cell_size_m=0.02)
    for name, cls, base in (('1D', Case1D, base1), ('2D', Case2D, base2),
                            ('3D', Case3D, base3)):
        off = validate_case(cls(**base))
        on = validate_case(cls(**base, keep_all_fields=True))
        check(f'{name} off: no note', not notes(cls(**base)))
        check(f'{name} on: same errors and warnings as off',
              on.errors == off.errors and on.warnings == off.warnings,
              f'{on.errors} {on.warnings}')
        got = notes(cls(**base, keep_all_fields=True))
        want = 'P9' if name == '1D' else 'disk estimate'
        check(f'{name} on: one note ({want})',
              len(got) == 1 and want in got[0], str(got))
        nat = dict(base, solver='native')
        got = notes(cls(**nat, keep_all_fields=True))
        check(f'{name} native: blastFoam-only note',
              len(got) == 1 and 'blastFoam setting' in got[0], str(got))
    got = notes(Case2D(**base2, keep_all_fields=True, write_budget=10))
    check('budget: the estimate counts its writes',
          len(got) == 1 and '(10 writes' in got[0], str(got))


def main():
    test_keys()
    test_validation()
    print(f"\n{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILED'}")
    return 0 if not FAILS else 1


if __name__ == '__main__':
    sys.exit(main())
