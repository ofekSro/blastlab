"""F14: a FieldForm must never call a deleted scroll viewport.

`FieldForm` watches the viewport of its nearest `QScrollArea` ancestor
for resizes (`_watch_viewport`, `eventFilter`). When that scroll area is
deleted while the form lives on under another one, the next showEvent
used to call `removeEventFilter` on the dead wrapper and raise
`RuntimeError: Internal C++ object ... already deleted`
(docs/gui-redesign-decisions.md F14; batch 2026-09-29-gui-results T1).

Deterministic: the form is moved from scroll area A to B, A is deleted
with `shiboken6.delete`, then the form is hidden and shown. No exception
may escape (a `sys.excepthook` recorder), and a resize of B's viewport
must reach `_fit_columns` exactly once through the filter.

Headless: offscreen Qt, no solver run.
Run:  cd blastlab/tests && python test_ui_fieldform_viewport.py
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.ui.testing import ensure_qapp, pump          # noqa: E402

app = ensure_qapp()

import shiboken6                                            # noqa: E402
from PySide6.QtCore import Qt                               # noqa: E402
from PySide6.QtWidgets import QScrollArea                   # noqa: E402

from blastlab.ui.case_form import CaseForm                  # noqa: E402

FAIL, RAN = [], []
CRASHES = []


def check(name, ok, detail=''):
    RAN.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def _hook(etype, value, tb):
    CRASHES.append(''.join(traceback.format_exception(etype, value, tb)))


def safely(fn, *args):
    """Call `fn`; an exception raised out of a Qt virtual (a showEvent
    reached from a Python show()) is recorded, not fatal."""
    try:
        fn(*args)
    except RuntimeError:
        CRASHES.append(traceback.format_exc())


def scroll():
    """A scroll area whose bars never come and go, so one resize of it
    is exactly one Resize event on its viewport."""
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
    s.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    s.resize(900, 600)
    return s


def filter_calls(form):
    """Count the `_fit_columns` calls that come from the event filter
    (a resize of the watched viewport), not from the form's own
    resizeEvent or showEvent."""
    calls = []
    real = form._fit_columns

    def counted():
        if sys._getframe(1).f_code.co_name == 'eventFilter':
            calls.append(1)
        return real()
    form._fit_columns = counted
    return calls


def s1_moved_between_scroll_areas():
    print('\nS1: the form moves from scroll area A to B, and A is deleted')
    for placement in ('nodes', 'columns'):
        del CRASHES[:]
        form = CaseForm(2, placement=placement)
        a = scroll()
        a.setWidget(form)
        a.show()
        pump(40)
        check(f'{placement}: the form watches A\'s viewport',
              form._watched is a.viewport())
        taken = a.takeWidget()
        b = scroll()
        b.setWidget(taken)          # B not shown yet: no showEvent here
        shiboken6.delete(a)
        pump(20)
        form.hide()
        safely(b.show)
        safely(form.show)
        pump(40)
        check(f'{placement}: no exception on show after A was deleted',
              not CRASHES, CRASHES[0].splitlines()[-1] if CRASHES else '')
        check(f'{placement}: the form now watches B\'s viewport',
              form._watched is b.viewport())
        calls = filter_calls(form)
        b.resize(b.width() - 60, b.height() - 40)
        pump(40)
        check(f'{placement}: a resize of B\'s viewport reaches _fit_columns '
              f'once through the filter', len(calls) == 1,
              f'{len(calls)} call(s)')
        b.hide()
        shiboken6.delete(b)
        pump(10)


def s2_dead_watched_is_dropped():
    print('\nS2: a dead watched viewport is dropped, never called')
    del CRASHES[:]
    form = CaseForm(2, placement='nodes')
    a = scroll()
    a.setWidget(form)
    a.show()
    pump(40)
    # a viewport destroyed without the form hearing of it (the hook
    # disconnected): the isValid guard alone must hold
    if hasattr(form, '_forget_viewport'):
        form._watched.destroyed.disconnect(form._forget_viewport)
    taken = a.takeWidget()
    b = scroll()
    b.setWidget(taken)
    shiboken6.delete(a)
    pump(20)
    check('the stale wrapper is invalid', not shiboken6.isValid(form._watched))
    safely(b.show)
    form.hide()
    safely(form.show)
    pump(40)
    check('show with a stale wrapper raises nothing', not CRASHES,
          CRASHES[0].splitlines()[-1] if CRASHES else '')
    check('and the filter moved to B', form._watched is b.viewport())
    b.hide()
    shiboken6.delete(b)
    pump(10)


def main():
    sys.excepthook = _hook
    try:
        s1_moved_between_scroll_areas()
        s2_dead_watched_is_dropped()
    finally:
        sys.excepthook = sys.__excepthook__
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'UI FIELDFORM VIEWPORT: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
