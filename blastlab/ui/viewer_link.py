"""The application's one viewer process, shared by the 3D hosts.

`ViewerLink` spawns `viz3d.process.ViewerProcess` lazily, buffers
messages until the child reports `ready` (its first `scene` carries
megabytes of init arrays, and a pipe send blocks until the reader is
up), polls replies on a QTimer and routes them to the host registered
for each surface. Nothing here imports pyvista or Qt's OpenGL."""

from PySide6.QtCore import QObject, QTimer, Signal

from ..viz3d import pyvista_available
from ..viz3d.process import ViewerProcess


class ViewerLink(QObject):
    ready = Signal()
    died = Signal()

    POLL_MS = 50

    def __init__(self, parent=None, log_fn=print):
        super().__init__(parent)
        self._log = log_fn
        self._proc = None
        self._ready = False
        self._pending = []
        self._hosts = {}
        self._windows = {}
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_MS)
        self._timer.timeout.connect(self._poll)

    # ── lifecycle ────────────────────────────────────────────────────────
    def register(self, surface, host):
        self._hosts[surface] = host
        hwnd = self._windows.get(surface)
        if hwnd is not None:
            host.on_window(hwnd)

    @property
    def alive(self):
        return self._proc is not None and self._proc.alive

    @property
    def is_ready(self):
        return self._ready and self.alive

    def ensure_started(self):
        """Spawn the child if it is not running; False when pyvista is
        missing (the hosts show MISSING_MSG themselves)."""
        if self.alive:
            return True
        if not pyvista_available():
            return False
        self._ready = False
        self._pending = []
        self._windows = {}
        try:
            self._proc = ViewerProcess(daemon=True).start(
                opts=dict(standalone=False))
        except Exception as exc:
            self._log(f'  [3D viewer failed to start: {exc}]')
            self._proc = None
            return False
        self._timer.start()
        return True

    def prewarm(self):
        """Start the child early so its pyvista import and GL context are
        paid while the user is still looking at the Setup tab."""
        self.ensure_started()

    def send(self, msg):
        """Queue a control message (delivered once the child is ready)."""
        if not self.ensure_started():
            return False
        if not self._ready:
            self._pending.append(msg)
            return True
        return self._proc.send(msg)

    def close(self):
        self._timer.stop()
        if self._proc is not None:
            self._proc.close()
        self._proc = None
        self._ready = False
        self._pending = []

    # ── replies ──────────────────────────────────────────────────────────
    def _poll(self):
        proc = self._proc
        if proc is None:
            return
        for msg in proc.poll():
            try:
                self._handle(msg)
            except Exception as exc:
                self._log(f'  [3D viewer reply {msg[0]!r} failed: {exc}]')
        if not proc.alive:
            self._timer.stop()
            self._ready = False
            self._log('  [3D viewer process ended]')
            for host in self._hosts.values():
                try:
                    host.on_viewer_died()
                except Exception:
                    pass
            self.died.emit()

    def _handle(self, msg):
        tag = msg[0]
        if tag == 'ready':
            self._ready = True
            pending, self._pending = self._pending, []
            for m in pending:
                self._proc.send(m)
            self.ready.emit()
            return
        surface = msg[1] if len(msg) > 1 else None
        host = self._hosts.get(surface)
        if tag == 'window':
            self._windows[surface] = int(msg[2])
            if host is not None:
                host.on_window(int(msg[2]))
        elif host is None:
            return
        elif tag == 'status':
            host.on_status(msg[2])
        elif tag == 'scene_ready':
            host.on_scene_ready()
        elif tag == 'closed':
            host.on_closed()
        elif tag == 'screenshot_done':
            host.on_screenshot(msg[2])
        elif tag == 'error':
            host.on_error(str(msg[2]))
