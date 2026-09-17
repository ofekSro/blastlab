"""Compatibility shim: settings moved to `blastlab.core.settings` (PySide6
migration, M0) - the foam backend reads them too. Remove with the Tk
package."""

from ..core.settings import DEFAULTS, config_path, load, save, update  # noqa: F401
