"""Shim: the explosive material table moved to `core/materials.py`
(docs/ARCHITECTURE_REVIEW.md, Phase 1). Every name stays importable from
this path and is the very same object as in core.materials.
"""

from ...core.materials import *                               # noqa: F401,F403
from ...core.materials import (Material, MATERIALS, MATERIAL_NAMES,  # noqa: F401
                               Afterburn, AFTERBURN, E0, charge_radius)
