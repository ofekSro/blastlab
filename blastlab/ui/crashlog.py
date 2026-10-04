"""A process-wide handler for exceptions nothing else caught.

WHY THIS FILE EXISTS, measured rather than imagined. On 2026-09-21 an
unhandled `ValueError` raised inside a Qt slot - `_run_single` on a
dim-0 case that validation refused - took the whole process down. The
log ended at the banner printed BEFORE the call, with no traceback, no
message box and no exit code worth reading. From the outside it looked
like a hang, and the bug it hid was a one-line validation mistake.

That is PySide6 behaving as documented: an exception propagating out of
a slot invoked from C++ has nowhere to go, so the binding calls
`sys.excepthook` and then `abort()`. Installing a handler does not
change the first half - it changes what the first half DOES, and the
process is still alive to show it.

WHAT IS AND IS NOT CAUGHT. This is a net under the trapeze, not a
reason to stop catching exceptions where they are raised: a handler
that swallows everything turns a crash into a wrong answer, which is
worse. The dialog says plainly that the application may now be in an
inconsistent state, because after an unhandled exception it may be.

THREADS TOO. `threading.excepthook` gets the same treatment: the run
worker is a thread, and an exception there used to vanish entirely -
the GUI simply stopped reporting progress. The log file and stderr are
written on the raising thread; the dialog is a widget with a nested
event loop, so it is only ever built on the GUI thread. A worker's
crash reaches it through a queued signal (GUI-11 T1, UXR-4, D203).

`KeyboardInterrupt` is passed through untouched, so Ctrl-C from a
terminal still stops the program rather than opening a dialog about
itself.
"""

import datetime
import os
import sys
import threading
import traceback

#: Where a crash is written, appended so a sequence of them survives.
#: Next to the settings rather than in the run corpus - CLAUDE.md 8.2:
#: anything under the runs root can be deleted by an automatic cleanup,
#: and the one file you want after a crash is the one describing it.
LOG_NAME = 'blastlab-crash.log'

#: Set by `install`; the tests read it rather than parsing the file.
last_crash = None

#: The GUI-thread relay for a crash raised on a worker thread, made by
#: `install` (UXR-4: a QMessageBox on a worker thread is undefined
#: behaviour in Qt and can take the window down).
_relay = None


def log_path():
    from ..core import settings as _settings
    try:
        base = os.path.dirname(os.path.abspath(_settings.config_path()))
    except Exception:
        base = os.path.expanduser('~')
    return os.path.join(base, LOG_NAME)


def _write(text):
    try:
        path = log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write(text)
        return path
    except Exception:
        # A crash handler that crashes is worse than none. The dialog
        # and the console still carry the traceback.
        return None


def _format(exc_type, exc, tb, where):
    return (f'\n{"=" * 70}\n{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  '
            f'{where}\n{"=" * 70}\n'
            + ''.join(traceback.format_exception(exc_type, exc, tb)))


def _report(exc_type, exc, tb, where='main thread'):
    global last_crash
    text = _format(exc_type, exc, tb, where)
    path = _write(text)
    last_crash = {'type': exc_type.__name__, 'message': str(exc),
                  'where': where, 'path': path, 'text': text}
    # The console first and always: a dialog can fail to open, and a
    # traceback that reached neither is the situation this file exists
    # to end.
    sys.stderr.write(text)
    sys.stderr.flush()
    if _on_gui_thread():
        _dialog(exc_type, exc, path, text)
    elif _relay is not None:
        # the box is the GUI thread's business: hand it over, queued
        try:
            _relay.show.emit((exc_type, exc, path, text))
        except Exception:
            pass


def _on_gui_thread():
    return threading.current_thread() is threading.main_thread()


def _suppressed():
    """No dialog without an application or on the offscreen platform
    (the tests): the log file and stderr carry the crash."""
    from PySide6.QtWidgets import QApplication
    return (QApplication.instance() is None
            or os.environ.get('QT_QPA_PLATFORM') == 'offscreen')


def _dialog(exc_type, exc, path, text=None):
    if not _on_gui_thread():
        return
    try:
        from PySide6.QtWidgets import QMessageBox
        if _suppressed():
            return
        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle('blastlab - unexpected error')
        box.setText(f'{exc_type.__name__}: {exc}')
        box.setInformativeText(
            'This was not handled anywhere, so the application may now be '
            'in an inconsistent state - save anything you care about and '
            'restart.'
            + (f'\n\nThe full traceback is in:\n{path}' if path else ''))
        if text is None:
            text = last_crash['text'] if last_crash else ''
        box.setDetailedText(text)
        box.exec()
    except Exception:
        pass


def _make_relay():
    """A QObject living on the GUI thread whose queued signal shows a
    worker's crash dialog there."""
    from PySide6.QtCore import QObject, Qt, Signal, Slot

    class _Relay(QObject):
        show = Signal(object)

        def __init__(self):
            super().__init__()
            self.show.connect(self._show, Qt.QueuedConnection)

        @Slot(object)
        def _show(self, args):
            _dialog(*args)

    return _Relay()


def install():
    """Install the handlers. Idempotent, and returns the log path.
    Call it on the GUI thread: the dialog relay lives there."""
    global _relay
    if _relay is None and _on_gui_thread():
        try:
            _relay = _make_relay()
        except Exception:
            _relay = None
    if getattr(sys.excepthook, '_blastlab', False):
        return log_path()

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        _report(exc_type, exc, tb)

    hook._blastlab = True
    sys.excepthook = hook

    def thread_hook(args):
        if issubclass(args.exc_type, KeyboardInterrupt):
            return
        _report(args.exc_type, args.exc_value, args.exc_traceback,
                where=f'thread {getattr(args.thread, "name", "?")}')

    thread_hook._blastlab = True
    threading.excepthook = thread_hook
    return log_path()
