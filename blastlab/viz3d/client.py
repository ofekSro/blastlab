"""Parent-side handle for the interactive 3D viewer process.

Viewer3DClient spawns `viewer.viewer_main` in a child process (its own
VTK event loop) and streams it decimated frames through a bounded
multiprocessing queue. The queue drops frames when full, so a slow or
stalled viewer can never block the solver. This module never imports
pyvista - only the child does.
"""

import multiprocessing
import queue as _queue
import time

import numpy as np

from .sampling import build_payload, build_scene_init, decimate, extract_loads


class Viewer3DClient:
    """Feeds one viewer window. `scene_info` is the solver's `scene3d`
    run_started payload (also reconstructible from a Result's meta)."""

    def __init__(self, scene_info, max_dim=128, min_interval=0.3):
        self._min_interval = min_interval
        self._last_send = 0.0
        init, self._stride, self._face_specs = build_scene_init(
            scene_info, max_dim)

        ctx = multiprocessing.get_context('spawn')
        self._q = ctx.Queue(maxsize=2)
        # never let an unread frame in the pipe block interpreter exit
        self._q.cancel_join_thread()
        from .viewer import viewer_main
        # non-daemon: the viewer window outlives the run (and the CLI);
        # the interpreter waits for it unless close() is called
        self._proc = ctx.Process(target=viewer_main, args=(self._q,),
                                 daemon=False, name='blastlab-viewer3d')
        self._proc.start()
        self._q.put(('init', init))

    @property
    def alive(self):
        return self._proc.is_alive()

    def send_frame(self, t, fields, force=False):
        """Decimate and enqueue one frame; silently dropped when the
        viewer is behind (bounded queue) or the throttle interval has
        not elapsed. `fields` values are only read, never kept."""
        now = time.time()
        if not force and now - self._last_send < self._min_interval:
            return
        if not self.alive:
            return
        payload = build_payload(fields, self._stride, self._face_specs)
        try:
            if force:   # e.g. the final frame of a run - don't drop it
                self._q.put(('frame', float(t), payload), timeout=2.0)
            else:
                self._q.put_nowait(('frame', float(t), payload))
            self._last_send = now
        except _queue.Full:
            pass

    def finish(self, stop_reason=''):
        """Run ended: switch the viewer to playback mode (stays open)."""
        _send_blocking(self, ('done', str(stop_reason)), timeout=5.0)

    def close(self):
        """Ask the viewer window to close; terminate if unresponsive."""
        try:
            self._q.put_nowait(('close',))
        except _queue.Full:
            pass
        self._proc.join(timeout=2.0)
        if self._proc.is_alive():
            self._proc.terminate()


def scene_from_meta(meta):
    """Rebuild a scene_info dict from a 3D Result's meta."""
    return dict(x_c=meta['x_c'], y_c=meta['y_c'], z_c=meta['z_c'],
                dx=meta['dx'], solid=meta['solid'],
                obstacles=meta['obstacles'], Lx=meta['Lx'], Ly=meta['Ly'],
                Lz=meta['Lz'], charge_center=meta['charge_center'],
                r_exp=meta.get('r_src', meta.get('r_exp')), bcs=meta['bcs'])


def _send_blocking(client, msg, timeout=30.0):
    """Deliver a message even through the bounded queue (playback replay
    must not drop frames). Gives up if the viewer dies or stalls."""
    deadline = time.time() + timeout
    while time.time() < deadline and client.alive:
        try:
            client._q.put(msg, timeout=0.25)
            return True
        except _queue.Full:
            pass
    return False


def open_playback(result):
    """Open a viewer on a finished 3D Result: replay its snapshots
    (which carry `t` and decimated density) and enter playback mode."""
    client = Viewer3DClient(scene_from_meta(result.meta))
    for snap in result.snapshots.values():
        p = np.asarray(snap['p'])
        payload = dict(p=decimate(p, client._stride),
                       loads=extract_loads(p, client._face_specs))
        rho3 = snap.get('rho3')
        # snapshots decimate density with the same stride rule, so the
        # shapes match unless the snapshot predates the viewer
        if rho3 is not None and rho3.shape == payload['p'].shape:
            payload['rho'] = rho3
        if not _send_blocking(client, ('frame', float(snap.get('t', 0.0)),
                                       payload)):
            break
    client.finish(result.stop_reason)
    return client


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
