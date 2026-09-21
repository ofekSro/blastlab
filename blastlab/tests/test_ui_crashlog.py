"""A Qt slot that raises must not take the process with it.

THE RUN THAT MADE THIS NECESSARY. On 2026-09-21 an unhandled ValueError
inside `_run_single` - a dim-0 case its own validation refused - killed
the whole process. The log ended at the banner printed BEFORE the call:
no traceback, no dialog, no usable exit code. From the outside it looked
like a hang, and what it hid was a one-line validation mistake.

That is PySide6 behaving as documented: an exception leaving a slot
invoked from C++ has nowhere to propagate, so the binding calls
`sys.excepthook` and then aborts. The fix is not to catch everything -
a handler that swallows exceptions turns a crash into a wrong answer -
but to make sure the one that escapes is RECORDED and the process is
still there to say so.

So the check is the blunt one: connect a slot that raises on purpose,
fire it, and require that the interpreter is still running afterwards
with the traceback written down.

Run:  cd blastlab/tests && python test_ui_crashlog.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def main():
    print('UI CRASHLOG')
    from blastlab.ui.testing import ensure_qapp
    ensure_qapp()
    from PySide6.QtCore import QObject, QTimer, Signal
    from PySide6.QtWidgets import QApplication
    from blastlab.ui import crashlog

    path = crashlog.install()
    check('installing returns the log path', bool(path), str(path))
    check('and it is idempotent - a second install does not stack '
          'handlers', crashlog.install() == path)
    check('the hook is ours, which is what stops PySide6 aborting',
          getattr(sys.excepthook, '_blastlab', False))

    before = os.path.getsize(path) if os.path.exists(path) else 0
    crashlog.last_crash = None

    class Boom(QObject):
        fire = Signal()

        def __init__(self):
            super().__init__()
            self.fire.connect(self._slot)
            self.ran = False

        def _slot(self):
            self.ran = True
            raise ValueError('deliberate: a slot that raises')

    print('\n  a slot that raises on purpose')
    b = Boom()
    b.fire.emit()
    app = QApplication.instance()
    for _ in range(20):
        app.processEvents()

    # THE WHOLE POINT. If this line runs at all, the process survived.
    check('the interpreter is still alive after the slot raised',
          True, 'reached the line after the emit')
    check('the slot really ran and really raised', b.ran)
    check('the crash was recorded rather than lost',
          crashlog.last_crash is not None
          and crashlog.last_crash['type'] == 'ValueError'
          and 'deliberate' in crashlog.last_crash['message'],
          str(crashlog.last_crash and crashlog.last_crash['message']))
    check('with a traceback, not just a message',
          crashlog.last_crash
          and 'Traceback' in crashlog.last_crash['text']
          and '_slot' in crashlog.last_crash['text'])
    check('and it was appended to the log rather than overwriting it',
          os.path.exists(path) and os.path.getsize(path) > before,
          f'{before} -> {os.path.getsize(path)} bytes')

    print('\n  a worker thread is covered too')
    import threading
    crashlog.last_crash = None

    def explode():
        raise RuntimeError('deliberate: a thread that raises')

    th = threading.Thread(target=explode, name='deliberate-worker')
    th.start()
    th.join(5.0)
    check('an exception in a thread is recorded, not swallowed - the run '
          'worker is a thread, and one used to vanish leaving the GUI '
          'simply not reporting progress',
          crashlog.last_crash is not None
          and crashlog.last_crash['type'] == 'RuntimeError'
          and 'thread' in crashlog.last_crash['where'],
          str(crashlog.last_crash and crashlog.last_crash['where']))

    print('\n  what is deliberately NOT caught')
    check('KeyboardInterrupt goes to the default hook, so Ctrl-C from a '
          'terminal still stops the program rather than opening a dialog '
          'about itself',
          _ctrl_c_passes_through())

    print('\nUI CRASHLOG: '
          + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


def _ctrl_c_passes_through():
    """The hook must delegate KeyboardInterrupt to sys.__excepthook__."""
    from blastlab.ui import crashlog
    seen = []
    real = sys.__excepthook__
    try:
        sys.__excepthook__ = lambda *a: seen.append(a[0])
        crashlog.last_crash = None
        sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    finally:
        sys.__excepthook__ = real
    return seen == [KeyboardInterrupt] and crashlog.last_crash is None


if __name__ == '__main__':
    sys.exit(main())
