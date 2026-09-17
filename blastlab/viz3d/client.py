"""Parent-side handle for the interactive 3D viewer (CLI path).

Viewer3DClient spawns the viewer child (`process.ViewerProcess`) and
streams it decimated frames through a shared-memory ring
(`protocol.SharedFrameRing`): latest wins, so a slow or stalled viewer
can never block the solver. This module never imports pyvista - only
the child does.
"""

import atexit
import time

from .process import ViewerProcess
from .protocol import FrameLayout, SharedFrameRing
from .sampling import build_payload, build_scene_init


class Viewer3DClient:
    """Feeds one viewer window. `scene_info` is the solver's `scene3d`
    run_started payload (also reconstructible from a Result's meta)."""

    def __init__(self, scene_info, max_dim=128, min_interval=0.3,
                 daemon=False, n_planes=2, embedded=False,
                 title='blastlab - 3D blast viewer'):
        self._min_interval = min_interval
        self._last_send = 0.0
        init, self._stride, self._face_specs = build_scene_init(
            scene_info, max_dim)
        self._layout = FrameLayout.from_init(
            init, with_levels=scene_info.get('refine') is not None)
        self._ring = SharedFrameRing(self._layout)
        # non-daemon by default: the viewer window outlives the run (and
        # the CLI); the interpreter waits for it unless close() is called
        self._proc = ViewerProcess(daemon=daemon).start(
            opts=dict(standalone=True))
        self._proc.send(('scene', 'run', dict(
            init=init, shm=self._ring.name, layout=self._layout,
            n_planes=n_planes, embedded=embedded, title=title)))
        atexit.register(self._release_ring)

    @property
    def alive(self):
        return self._proc.alive

    def send_frame(self, t, fields, force=False):
        """Decimate and publish one frame; the viewer picks up the newest
        on its own timer (latest wins) so this never blocks. `fields`
        values are only read, never kept. `force` bypasses the throttle
        (e.g. the final frame of a run) and marks the frame `final`, so
        the viewer's FrameStore keeps it regardless of thinning stride."""
        now = time.time()
        if not force and now - self._last_send < self._min_interval:
            return
        if not self.alive:
            return
        payload = build_payload(fields, self._stride, self._face_specs)
        self._ring.write(t, payload, final=force)
        self._last_send = now

    def finish(self, stop_reason=''):
        """Run ended: switch the viewer to playback mode (stays open)."""
        self._proc.send(('done', 'run', str(stop_reason)))

    def close(self):
        """Ask the viewer window to close; terminate if unresponsive."""
        self._proc.close()
        self._release_ring()

    def _release_ring(self):
        ring = getattr(self, '_ring', None)
        if ring is not None:
            ring.close(unlink=True)


def scene_from_meta(meta):
    """Rebuild a scene_info dict from a 3D Result's meta."""
    return dict(x_c=meta['x_c'], y_c=meta['y_c'], z_c=meta['z_c'],
                dx=meta['dx'], solid=meta['solid'],
                obstacles=meta['obstacles'], Lx=meta['Lx'], Ly=meta['Ly'],
                Lz=meta['Lz'], charge_center=meta['charge_center'],
                r_exp=meta.get('r_src', meta.get('r_exp')), bcs=meta['bcs'],
                refine=meta.get('refine'),
                # P2-2: which backend produced the energy field
                solver=meta.get('solver'))


class _StartupAttach:
    """CLI helper: wraps hooks so the viewer opens as soon as the solver
    reports run_started (which carries the scene geometry)."""

    def __init__(self, hooks):
        self._hooks = hooks
        self._orig_run_started = hooks.run_started

    def __call__(self, info):
        self._orig_run_started(info)
        scene = info.get('scene3d')
        if scene is not None and self._hooks.viewer3d is None:
            self._hooks.viewer3d = Viewer3DClient(scene)


def attach_on_start(hooks):
    """Arrange for `hooks.viewer3d` to be created from the run_started
    scene payload (used by the CLI path where the scene is not known
    before the solver starts)."""
    hooks.run_started = _StartupAttach(hooks)
    return hooks
