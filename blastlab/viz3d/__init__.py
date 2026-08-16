"""Interactive 3D blast viewer (optional, requires pyvista).

The viewer runs in a dedicated child process with its own VTK render
loop; the solver process feeds it decimated frames over a bounded
multiprocessing queue. Nothing in this package imports pyvista except
`viewer.py`, which only ever runs inside the child process, so the
solver/GUI work unchanged when pyvista is not installed.
"""

from importlib.util import find_spec

MISSING_MSG = ("3D viewer requires pyvista - install it with: "
               "pip install pyvista")


def pyvista_available():
    """True when pyvista can be imported (without importing it here)."""
    try:
        return find_spec('pyvista') is not None
    except (ImportError, ValueError):
        return False
