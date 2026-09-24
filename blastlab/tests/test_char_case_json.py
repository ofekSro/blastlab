"""Characterisation: the case JSON schemas (Phase 0).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 0. Pins, byte for byte after
`json.dumps(sort_keys=True)`, what `core.case.case_to_dict` writes for the
three default blast cases, what `core.assessment.case_to_dict` writes for
the HD 1.3 starter case (`output/cli_hd13.write_starter_case`), and what
the two committed case files in `tests/cases/` become after a load and a
re-save. Phase 2 moves these functions; the bytes must not move with them.

Each golden is also pushed back through `case_from_dict` to pin whether
the round trip reproduces it. Phase 5a adds the form round trip through
`models.fields` (no QApplication), which needs no golden.

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


#: Phase 5a: what one form round trip changes in a DEFAULT case, pinned as
#: found. The Case2D/3D dataclass AMR thresholds are 0.2/0.1 (re-tuned
#: 2026-09-10, models/case.py), but the form mapping substitutes 0.4/0.2
#: whenever AMR is off and falls back to them in fields_from_case, so a
#: default case read back through the form carries 0.4/0.2. Reported, not
#: fixed (a characterisation test documents behaviour, correct or not).
FORM_ROUNDTRIP_CHANGES = {
    1: {},
    2: {'amr_refine': ('0.2', '0.4'), 'amr_unrefine': ('0.1', '0.2')},
    3: {'amr_refine': ('0.2', '0.4'), 'amr_unrefine': ('0.1', '0.2')},
    0: {},
}


def test_fields_roundtrip_default_cases():
    """fields_from_case(case_from_fields(...)) on the three default blast
    cases and the default HD 1.3 case, both solver modes, no QApplication
    (Phase 5a): no errors, no bad fields, only the pinned changes, and a
    second round trip is a fixed point."""
    from blastlab.models import fields
    for case in (Case1D(), Case2D(), Case3D(),
                 assessment.DeflagrationCase()):
        dim = case.dim
        values = fields.fields_from_case(case)
        for mode in ('native', 'blastfoam'):
            got, errs, bad = fields.case_from_fields(dim, values, mode)
            assert (errs, bad) == ([], []), f'dim {dim} {mode}: {errs} {bad}'
            if dim:
                assert got.solver == mode, f'dim {dim} {mode}: {got.solver}'
            back = fields.fields_from_case(got)
            assert list(back) == list(values), \
                f'dim {dim} {mode}: field order changed'
            changed = {k: (values[k], back[k]) for k in values
                       if values[k] != back[k]}
            assert changed == FORM_ROUNDTRIP_CHANGES[dim], \
                f'dim {dim} {mode}: round trip changed {changed}'
            again, errs2, _ = fields.case_from_fields(dim, back, mode)
            assert not errs2 and fields.fields_from_case(again) == back, \
                f'dim {dim} {mode}: the second round trip is not a fixed point'


def main():
    return cc.run_main('CHAR CASE JSON', [
        test_default_cases, test_hd13_starter_case,
        test_committed_case_files, test_fields_roundtrip_default_cases])


if __name__ == '__main__':
    sys.exit(main())
