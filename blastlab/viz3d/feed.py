"""Solver-side feed for the embedded 3D view: turns full-resolution
fields into viewer payloads. Pure NumPy, no pyvista, no toolkit - safe to
build and call on the solver thread (moved out of the Tk view3d panel)."""

from .sampling import build_payload, build_scene_init

#: cut planes offered by the GUI-hosted viewer (the CLI window has 2)
N_PLANES = 6


class Feed3D:
    """Solver-thread side: turns full-resolution fields into viewer
    payloads. Read-only after construction, so thread-safe."""

    def __init__(self, scene_info):
        self.init, self._stride, self._specs = build_scene_init(scene_info)

    def make_payload(self, fields):
        return build_payload(fields, self._stride, self._specs)
