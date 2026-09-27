"""Compatibility shim: settings moved to `blastlab.core.settings` (PySide6
migration, M0) - the foam backend reads them too. The Tk GUI keeps
importing them here; that GUI is the permanent way back behind `--tk`
(CLAUDE.md section 9)."""

from ..core.settings import (DEFAULTS, config_path, default_path,  # noqa: F401
                             load, save, update)
