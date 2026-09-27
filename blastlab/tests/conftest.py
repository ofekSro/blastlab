"""pytest configuration for blastlab/tests (docs/ARCHITECTURE_REVIEW.md,
Phase 0; finding F10).

Most suites here are plain scripts (`python test_x.py`) and stay that way.
This file makes a bare `python -m pytest` from this directory SAFE:

1. It points BLASTLAB_SETTINGS at a private file holding
   `"auto_cleanup": false` before any test module is imported. Anything
   that builds a window starts the run-corpus sweep against whatever
   settings it finds (off by default since 2026-09-27, but a settings
   file may switch it on - CLAUDE.md 8.2). `ui.testing` imports no Qt at
   module level.

2. It keeps out of collection every file that is unsafe or pointless to
   import under pytest: the six suites that run their whole body at import
   (`test_blast2d.py`, `test_blast3d.py` and four `test_viz3d_*.py`), the
   GUI and viewer suites, the WSL suites, the `_e2e_` real solves and the
   `_qa_` interactive harnesses. Those run as scripts only - see
   CLAUDE.md 6, "Tests - the gates".

3. It makes a failing `check()` fail the pytest test (P2-13 item 4, as
   amended by the owner 2026-09-27). The script suites' `check()` only
   appends the failing name to a module-level list (`FAIL` / `FAILS`)
   and the script's `main` exits 1 at the end; under pytest the test
   function returned normally whatever the list held, so it could not
   fail. A hook wrapper around each test's call phase records the
   length of every such list - in the test's own module and in every
   module loaded from this directory, so a check reached through an
   imported helper counts too - and fails the test afterwards if any
   grew, naming the new failing checks. No test file changes, and script
   mode is untouched.
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from blastlab.ui.testing import private_settings     # noqa: E402

# Session start: conftest.py is imported before any test module is.
private_settings()

collect_ignore_glob = [
    '_e2e_*.py',
    '_qa_*.py',
    'test_ui_*.py',
    'test_gui_*.py',
    'test_viz3d_*.py',
    'test_foam_*.py',
    'test_blast2d.py',
    'test_blast3d.py',
    'make_baseline.py',
]

@pytest.fixture(scope='module')
def tmp(tmp_path_factory):
    """The one temp directory a script suite's `main()` makes and passes
    to each of its `test_*(tmp)` functions (`test_load_csv`,
    `test_wall_clearing`). Module-scoped, as in `main()`, so a test that
    reads what an earlier one wrote still finds it (P2-13 item 5, owner
    2026-09-27)."""
    return str(tmp_path_factory.mktemp('suite'))


#: The module-level failure lists the suites' `check()` appends to
#: (grep `def check(` here: every one appends to FAIL or FAILS).
FAIL_LIST_NAMES = ('FAIL', 'FAILS', 'FAILED', 'FAILURES')


def _fail_lists(item):
    """{(module name, list name): list} for the test's own module and
    every loaded module whose file lives in this directory."""
    mods = {getattr(item, 'module', None)}
    for mod in list(sys.modules.values()):
        f = getattr(mod, '__file__', None)
        if f and os.path.dirname(os.path.abspath(f)) == HERE:
            mods.add(mod)
    out = {}
    for mod in mods:
        if mod is None:
            continue
        for name in FAIL_LIST_NAMES:
            val = vars(mod).get(name)
            if isinstance(val, list):
                out[(mod.__name__, name)] = val
    return out


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Fail the test when a `check()` inside it recorded a failure (see
    point 3 of the module docstring). A test that already raised keeps
    its own error."""
    before = {k: len(v) for k, v in _fail_lists(item).items()}
    result = yield
    new = []
    for key, lst in _fail_lists(item).items():
        start = before.get(key, 0)
        new += [f'{key[0]}.{key[1]}: {entry}' for entry in lst[start:]]
    if new:
        raise AssertionError(f'{len(new)} failing check(s): '
                             + '; '.join(new))
    return result
