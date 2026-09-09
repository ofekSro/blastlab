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

from .sampling import build_payload, build_scene_init


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
        not elapsed. `fields` values are only read, never kept.
        `force` both bypasses the throttle/drop (e.g. the final frame of
        a run) and is carried in the message as `final`, so the viewer's
        FrameStore keeps it regardless of thinning stride."""
        now = time.time()
        if not force and now - self._last_send < self._min_interval:
            return
        if not self.alive:
            return
        payload = build_payload(fields, self._stride, self._face_specs)
        try:
            if force:   # e.g. the final frame of a run - don't drop it
                self._q.put(('frame', float(t), payload, True), timeout=2.0)
            else:
                self._q.put_nowait(('frame', float(t), payload, False))
            self._last_send = now
        except _queue.Full:
            pass

    def finish(self, stop_reason=''):
        """Run ended: switch the viewer to playback mode (stays open)."""
        _send_blocking(self, ('done', str(stop_reason)), timeout=5.0)

    def close(self):
        """Ask the viewer window to close; terminate if unresponsive.
        A full queue (stalled viewer) has one frame dropped so the
        'close' always lands (A8)."""
        _send_blocking(self, ('close',), timeout=2.0)
        self._proc.join(timeout=2.0)
        if self._proc.is_alive():
            self._proc.terminate()


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


def _send_blocking(client, msg, timeout=30.0):
    """Deliver a control message through the bounded queue. When the
    queue is full (the viewer is behind or stalled) one queued FRAME is
    dropped to make room - frames are expendable, 'done'/'close' are
    not; a non-frame message pulled out by mistake is put back. Gives up
    only when the viewer dies or the deadline passes (A8)."""
    deadline = time.time() + timeout
    while time.time() < deadline and client.alive:
        try:
            client._q.put(msg, timeout=0.25)
            return True
        except _queue.Full:
            pass
        try:
            item = client._q.get_nowait()
        except _queue.Empty:
            continue
        if item and item[0] != 'frame':
            try:
                client._q.put(item, timeout=0.25)
            except _queue.Full:
                pass
    return False


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
