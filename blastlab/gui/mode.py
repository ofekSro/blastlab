"""Compatibility shim: the solver-mode observable moved to
`blastlab.core.mode` (PySide6 migration, M0). The Tk GUI keeps importing
it here; that GUI is the permanent way back behind `--tk` (CLAUDE.md
section 9)."""

from ..core.mode import (DEFAULT, EXPLAIN, LABELS, MODES,  # noqa: F401
                         SolverMode, from_label, label, normalize)
