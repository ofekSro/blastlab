"""The Phase 2 re-export shims hand out the SAME objects (Phase 2).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 2. The case dataclasses and
their JSON moved to `models/case.py`, `DeflagrationCase` and its JSON to
`models/hd13_case.py`, and `Progress`/`Result`/`StoppedBeforeStart`/
`ValidationReport` to `models/result.py`. The old modules re-export them.
An equal-looking copy would not do: `isinstance(x, Result)` in
`solvers/foam/backend.py` and `ui/run_controller.py` needs the one class,
and `case_from_dict` must build the class the GUI compares against.

Run:  cd blastlab/tests && python test_models_shims.py      (or under pytest)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from blastlab.core import assessment, case as core_case     # noqa: E402
from blastlab.models import case as m_case                  # noqa: E402
from blastlab.models import hd13_case as m_hd13             # noqa: E402
from blastlab.models import result as m_result              # noqa: E402
from blastlab.solvers import hooks                          # noqa: E402

CASE_NAMES = ('TRIGGER_ACTIONS', 'SCHEMA', 'VERSION', 'Case1D', 'Case2D',
              'Case3D', '_CASE_TYPES', 'case_to_dict', 'case_from_dict',
              'save_case', 'load_case', 'material_rho0', 'fmt_cells')
HD13_NAMES = ('SCHEMA', 'VERSION', 'DeflagrationCase', '_TUPLE_FIELDS',
              'case_to_dict', 'case_from_dict', 'save_case', 'load_case')
HOOKS_NAMES = ('Progress', 'Result', 'StoppedBeforeStart')


def _same(old, new, names):
    return [n for n in names if getattr(old, n) is not getattr(new, n)]


def test_core_case_reexports_models_case():
    assert not _same(core_case, m_case, CASE_NAMES)
    assert core_case.ValidationReport is m_result.ValidationReport
    assert core_case.VERSION == 13


def test_assessment_reexports_models_hd13_case():
    assert not _same(assessment, m_hd13, HD13_NAMES)
    assert assessment.ValidationReport is m_result.ValidationReport


def test_hooks_reexports_models_result():
    assert not _same(hooks, m_result, HOOKS_NAMES)


def test_objects_built_on_either_path_are_one_class():
    res = m_result.Result({}, {}, {})
    assert isinstance(res, hooks.Result)
    case = core_case.case_from_dict(m_case.case_to_dict(m_case.Case2D()))
    assert type(case) is core_case.Case2D is m_case.Case2D
    hd = assessment.case_from_dict(
        m_hd13.case_to_dict(m_hd13.DeflagrationCase()))
    assert type(hd) is assessment.DeflagrationCase


def main():
    fails = []
    for fn in (test_core_case_reexports_models_case,
               test_assessment_reexports_models_hd13_case,
               test_hooks_reexports_models_result,
               test_objects_built_on_either_path_are_one_class):
        try:
            fn()
        except AssertionError as exc:
            fails.append(fn.__name__)
            print(f'  [FAIL] {fn.__name__} - {exc}')
        else:
            print(f'  [PASS] {fn.__name__}')
    print()
    print('MODELS SHIMS: ' + ('PASS' if not fails else
                              f'FAIL ({len(fails)}): ' + ', '.join(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
