"""Characterisation: the case JSON schemas (Phase 0).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 0. Pins, byte for byte after
`json.dumps(sort_keys=True)`, what `core.case.case_to_dict` writes for the
three default blast cases, what `core.assessment.case_to_dict` writes for
the HD 1.3 starter case (`output/cli_hd13.write_starter_case`), and what
the two committed case files in `tests/cases/` become after a load and a
re-save. Phase 2 moves these functions; the bytes must not move with them.

Each golden is also pushed back through `case_from_dict` to pin whether
the round trip reproduces it.

Run:  cd blastlab/tests && python test_char_case_json.py [--update]
"""
import json
import os
import sys

import char_common as cc
from blastlab.core import assessment                      # noqa: E402
from blastlab.core.case import (Case1D, Case2D, Case3D,   # noqa: E402
                                case_from_dict, case_to_dict, load_case)

CASES_DIR = os.path.join(cc.HERE, 'cases')


def canonical(d):
    return json.dumps(d, sort_keys=True, indent=2) + '\n'


def blast_roundtrip(text):
    """The canonical text after one more case_from_dict/case_to_dict."""
    return canonical(case_to_dict(case_from_dict(json.loads(text))))


def test_default_cases():
    for name, cls in (('case1d', Case1D), ('case2d', Case2D),
                      ('case3d', Case3D)):
        text = canonical(case_to_dict(cls()))
        cc.check_text(f'json_{name}_default.json', text)
        assert blast_roundtrip(text) == text, \
            f'{name}: the default case does not round-trip'


def test_hd13_starter_case():
    case = cc.hd13_starter_case()
    text = canonical(assessment.case_to_dict(case))
    cc.check_text('json_hd13_starter.json', text)
    again = canonical(assessment.case_to_dict(
        assessment.case_from_dict(json.loads(text))))
    assert again == text, 'the HD 1.3 starter case does not round-trip'


def test_committed_case_files():
    for fname in ('native_2d_small.json', 'native_3d_small.json'):
        case = load_case(os.path.join(CASES_DIR, fname))
        text = canonical(case_to_dict(case))
        cc.check_text('json_loaded_' + fname, text)
        assert blast_roundtrip(text) == text, \
            f'{fname}: the loaded case does not round-trip'


def main():
    return cc.run_main('CHAR CASE JSON', [
        test_default_cases, test_hd13_starter_case,
        test_committed_case_files])


if __name__ == '__main__':
    sys.exit(main())
