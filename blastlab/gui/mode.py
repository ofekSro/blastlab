"""Compatibility shim: the solver-mode observable moved to
`blastlab.core.mode` (PySide6 migration, M0). Remove with the Tk package."""

from ..core.mode import (DEFAULT, EXPLAIN, LABELS, MODES,  # noqa: F401
                         SolverMode, from_label, label, normalize)
