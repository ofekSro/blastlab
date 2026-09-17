"""Worker thread -> GUI thread hand-off.

`ThreadBridge.post(fn, *args)` may be called from any thread; `fn` runs
on the GUI thread on the next event-loop pass (a queued signal). This
replaces every `root.after(0, ...)` the Tk app issued from its export,
probe and load threads."""

import functools

from PySide6.QtCore import QObject, Qt, Signal


class ThreadBridge(QObject):
    call = Signal(object)
    log = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.call.connect(self._run, Qt.QueuedConnection)

    def post(self, fn, *args, **kw):
        self.call.emit(functools.partial(fn, *args, **kw))

    @staticmethod
    def _run(fn):
        try:
            fn()
        except Exception as exc:              # a bad callback must not
            print(f'[ui] bridged call failed: {exc!r}')  # kill the loop
