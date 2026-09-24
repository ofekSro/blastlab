"""pytest configuration for blastlab/tests (docs/ARCHITECTURE_REVIEW.md,
Phase 0; finding F10).

Most suites here are plain scripts (`python test_x.py`) and stay that way.
This file makes a bare `python -m pytest` from this directory SAFE:

1. It points BLASTLAB_SETTINGS at a private file holding
   `"auto_cleanup": false` before any test module is imported. Anything
   that builds a window starts the run-corpus sweep against whatever
   settings it finds, and on this machine the real settings have the sweep
   ON (CLAUDE.md 8.2). `ui.testing` imports no Qt at module level.

2. It keeps out of collection every file that is unsafe or pointless to
   import under pytest: the six suites that run their whole body at import
   (`test_blast2d.py`, `test_blast3d.py` and four `test_viz3d_*.py`), the
   GUI and viewer suites, the WSL suites, the `_e2e_` real solves and the
   `_qa_` interactive harnesses. Those run as scripts only - see
   CLAUDE.md 6, "Tests - the gates".
"""

import os
import sys

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
