"""The old import path of the case model and of pre-flight validation.

The case dataclasses (`Case1D`, `Case2D`, `Case3D`) and their versioned
JSON form live in `models/case.py`, `ValidationReport` in
`models/result.py` (Phase 2 of docs/ARCHITECTURE_REVIEW.md), and
`validate_case` with its helpers in `services/validation.py` (Phase 3).
This module re-exports them, underscore names included, so every
existing import keeps returning the same objects - and `core/` no
longer imports `solvers.foam` for it.
"""

# `import *` skips underscore names, so each one the old module held is
# listed by hand
from ..models.case import *                     # noqa: F401,F403
from ..models.case import _CASE_TYPES           # noqa: F401
from ..models.result import ValidationReport    # noqa: F401
from ..services.validation import *             # noqa: F401,F403
from ..services.validation import (             # noqa: F401
    _charge_radius, _hardware, _validate_solver, _validate_write_budget,
    _warn_long_end_time)
