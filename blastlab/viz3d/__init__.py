"""Interactive 3D blast viewer (optional, requires pyvista + pyvistaqt).

The viewer runs in a dedicated child process - a small Qt application
hosting one pyvista render window per surface - fed decimated frames
through a shared-memory ring (`protocol.py`) and controlled over a pipe
(`process.py`). Nothing in this package imports pyvista or Qt except
`viewer.py`, which only ever runs inside the child process, so the
solver/GUI work unchanged when pyvista is not installed.
"""

from importlib.util import find_spec

MISSING_MSG = ("3D viewer requires pyvista - install it with: "
               "pip install pyvista pyvistaqt")


def pyvista_available():
    """True when pyvista can be imported (without importing it here)."""
    try:
        return find_spec('pyvista') is not None
    except (ImportError, ValueError):
        return False
