"""Parent-side handle for the 3D viewer child process.

`ViewerProcess` spawns `viewer.viewer_main` (a small Qt application
hosting pyvista render windows) and talks to it over a duplex Pipe of
small control tuples. Frames do NOT go through here - see
`protocol.SharedFrameRing`. This module never imports pyvista or Qt, so
the GUI/CLI process stays VTK-free.

Control messages, parent -> child (all carry the surface name second):
    ('scene', surface, spec)        build a BlastScene: spec = dict(init,
                                    shm, layout, n_planes, embedded, title)
    ('geo', surface, geo)           GeometryScene.show(geo) (setup preview)
    ('done', surface, reason)       run ended: playback mode
    ('claim', surface, hwnd|None)   show the window (embed into hwnd)
    ('release', surface)            hide the window
    ('detach', surface, bool)       float / re-embed
    ('resize', surface, w, h)       host container size
    ('screenshot', surface, path)   write a PNG
    ('hud', surface, text)          extra HUD line ('' clears)
    ('ctrl', surface, name, *args)  a BlastScene setter (see viewer._CTRL)
    ('close',)                      quit the child
Child -> parent:
    ('ready', pid)                  Qt loop running
    ('window', surface, hwnd)       native handle of a surface window
    ('scene_ready', surface)        scene built and attached to its ring
    ('status', surface, dict)       n/index/t/done/playing/follow/field/
                                    vmin/vmax/have, at most ~10 Hz
    ('closed', surface)             the user closed a floating window
    ('screenshot_done', surface, path)
    ('error', surface, text)        a message handler raised (logged too)
"""

import multiprocessing


class ViewerProcess:
    """One viewer child. `daemon=True` (GUI) dies with the parent;
    `daemon=False` (CLI) keeps its window open after the run and the
    interpreter waits for it unless `close()` is called."""

    def __init__(self, daemon=True, name='blastlab-viewer3d'):
        self._daemon = daemon
        self._name = name
        self._proc = None
        self._conn = None
        self._dead = False

    def start(self, opts=None):
        ctx = multiprocessing.get_context('spawn')
        parent, child = ctx.Pipe(duplex=True)
        from .viewer import viewer_main
        self._proc = ctx.Process(target=viewer_main,
                                 args=(child, dict(opts or {})),
                                 daemon=self._daemon, name=self._name)
        self._proc.start()
        child.close()
        self._conn = parent
        return self

    @property
    def pid(self):
        return self._proc.pid if self._proc is not None else None

    @property
    def alive(self):
        return (not self._dead and self._proc is not None
                and self._proc.is_alive())

    def send(self, msg):
        """Post one control tuple; False when the child is gone."""
        if not self.alive or self._conn is None:
            return False
        try:
            self._conn.send(msg)
            return True
        except (BrokenPipeError, EOFError, OSError, ValueError):
            self._dead = True
            return False

    def poll(self, limit=64):
        """Drain pending replies (non-blocking) as a list."""
        out = []
        if self._conn is None or self._dead:
            return out
        try:
            while len(out) < limit and self._conn.poll():
                out.append(self._conn.recv())
        except (BrokenPipeError, EOFError, OSError):
            self._dead = True
        return out

    def close(self, timeout=2.0):
        """Ask the child to quit; terminate if it does not."""
        if self._proc is None:
            return
        self.send(('close',))
        try:
            self._proc.join(timeout=timeout)
        except Exception:
            pass
        if self._proc.is_alive():
            try:
                self._proc.terminate()
                self._proc.join(timeout=1.0)
            except Exception:
                pass
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        self._conn = None
        self._dead = True
