"""RunController resilience (Qt port of test_gui_drain): a handler
exception must be logged and the loop must keep draining (the worker
keeps solving; 'result'/'done' must still arrive). Headless - offscreen
Qt, no window shown, no solver run: the controller is fed a synthetic
worker queue."""
import os, sys
import queue

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.ui.testing import ensure_qapp, pump          # noqa: E402

app = ensure_qapp()

from blastlab.solvers.hooks import Progress, Result        # noqa: E402
from blastlab.ui import dialogs                            # noqa: E402
from blastlab.ui.run_controller import (RunController,     # noqa: E402
                                        error_headline,
                                        parse_refresh)

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


class _StubHooks:
    feed3d = None
    ring = None
    scene3d = None
    auto3d = False
    refresh = ('seconds', 0.05)
    refresh3d = ('seconds', 0.2)

    def __init__(self, bad_frame=True):
        self._bad = bad_frame
        self.drained3d = 0
        self.exec_cmds = []

    def latest_frame(self):
        if self._bad:
            raise RuntimeError('synthetic frame handler failure')
        return None

    def latest_frame3d(self):
        self.drained3d += 1
        return None

    def set_exec(self, cmd):
        self.exec_cmds.append(cmd)


class _StubWorker:
    def __init__(self, bad_frame=True):
        self.q = queue.Queue()
        self.hooks = _StubHooks(bad_frame)
        self._alive = True

    def is_alive(self):
        return self._alive

    def stop(self):
        self._alive = False

    def join(self, timeout=None):
        self._alive = False


class _Handlers:
    """Records what the window would have been told; every other call is
    a no-op."""

    def __init__(self):
        self.lines = []
        self.results = []
        self.finished = []
        self.running = []
        self.started = []
        self.frames = []
        self.progress = []
        self.paused = []
        self.cadence = []
        self.view3d = []

    def on_log(self, text):
        self.lines.append(str(text))

    def on_run_started(self, info):
        self.started.append(info)

    def on_view3d_available(self, is3d):
        self.view3d.append(bool(is3d))

    def on_cadence(self, dt, steps):
        self.cadence.append((dt, steps))

    def on_progress(self, p):
        self.progress.append(p)

    def on_paused(self, paused):
        self.paused.append(bool(paused))

    def on_frame(self, field, t, levels=None):
        self.frames.append(t)

    def on_running(self, running):
        self.running.append(bool(running))

    def on_result(self, k, dim, label, res):
        self.results.append((k, dim, label, res))

    def on_finished(self, stopped, errored):
        self.finished.append((bool(stopped), bool(errored)))


def controller(bad_frame=True, dims=(2,)):
    h = _Handlers()
    c = RunController(handlers=h)
    c.worker = _StubWorker(bad_frame)
    c._stage_dims = list(dims)
    c._run_count = 1
    c._drain_pending = True
    return c, h


def main():
    errors = []
    dialogs.show_error = lambda title, msg, parent=None: errors.append(msg)
    dialogs.show_info = lambda title, msg, parent=None: errors.append(msg)

    print("\nT1: a raising handler is logged and draining continues")
    c, h = controller()
    res = Result(snapshots={}, gauges={}, meta={}, stop_reason='done')
    for msg in (('log', 'first'), ('frame',), ('log', 'second'),
                ('result', 0, res), ('done',)):
        c.worker.q.put(msg)
    c._drain()
    check("the bad frame was reported, not fatal",
          any("[ui error handling 'frame']" in ln for ln in h.lines),
          [ln.splitlines()[0] for ln in h.lines])
    check("messages before AND after the failure arrived",
          'first' in h.lines and 'second' in h.lines)
    check("the result still arrived", len(h.results) == 1)
    check("'done' still finished the run",
          h.running == [False] and h.finished == [(False, False)]
          and '  [run finished]' in h.lines)
    check("the drain timer stopped", not c._timer.isActive())
    check("no longer running", not c.running)

    print("\nT2: every tag reaches its handler")
    c, h = controller(bad_frame=False)
    info = dict(dim=2, scene3d=None)
    p = Progress(step=7, t=1e-4, dt=1e-6, p_max=2e5, frac=0.25)
    for msg in (('run_started', info), ('cadence', 1e-5, 3),
                ('progress', p), ('paused', True), ('paused', False),
                ('frame',), ('frame3d',), ('stage', 0, '2D'),
                ('result', 0, res), ('done',)):
        c.worker.q.put(msg)
    c._drain()
    check("run_started", h.started == [info])
    check("cadence", h.cadence == [(1e-5, 3)])
    check("progress", h.progress == [p])
    check("paused both ways", h.paused == [True, False])
    check("a 2D-only run offers no 3D view", h.view3d == [False])
    check("stage logged", '=== Stage 2D ===' in h.lines)
    check("the frame3d slot is drained even with no viewer",
          c.worker.hooks.drained3d == 1)
    check("result labelled by run number and dim",
          h.results[0][2] == 'Run 1 - 2D', h.results[0][2])

    print("\nT3: a stopped stage and an errored stage are told apart")
    c, h = controller(bad_frame=False)
    stopped = Result(snapshots={}, gauges={}, meta={}, stop_reason='user',
                     stopped_early=True)
    c.worker.q.put(('result', 0, stopped))
    c.worker.q.put(('done',))
    c._drain()
    check("a stopped result is labelled", h.results[0][2].endswith('(stopped)'),
          h.results[0][2])
    check("a stopped run is not marked complete", h.finished == [(True, False)])

    c, h = controller(bad_frame=False)
    errors.clear()
    tb = ('Traceback (most recent call last):\n'
          '  File "x.py", line 1, in <module>\n'
          'RuntimeError: blastFoam failed (exit 1)\n  tail line\n')
    c.worker.q.put(('error', tb))
    c.worker.q.put(('done',))
    c._drain()
    check("the error reached the log", any('RuntimeError' in ln
                                           for ln in h.lines))
    check("the dialog shows the headline, not the tail",
          errors and errors[0].startswith('RuntimeError: blastFoam failed'),
          errors[0].splitlines()[0] if errors else '<none>')
    check("an errored run is not marked complete",
          h.finished == [(False, True)])

    print("\nT4: a named run labels its results")
    c, h = controller(bad_frame=False)
    c._run_name = 'tunnel'
    c.worker.q.put(('result', 0, res))
    c.worker.q.put(('done',))
    c._drain()
    check("name wins over the counter", h.results[0][2] == 'tunnel - 2D',
          h.results[0][2])
    check("the name rides in the result meta",
          res.meta.get('name') == 'tunnel')

    print("\nT5: one run at a time")
    c, h = controller(bad_frame=False)
    errors.clear()
    check("a second start is refused while one is pending",
          c.start_stages([(2, object())]) is False)
    check("the refusal is explained", errors
          and 'already in progress' in errors[0])
    c._drain_pending = False
    c.worker._alive = False

    print("\nT5b: GUI-15 (c) - a stage's result carries Run's drop reasons")
    import time
    from blastlab.core.case import Case2D
    from blastlab.ui import run_gauges
    ew = Case2D(geometry='planar', Lx=2.4, Ly=1.6, cell_size_m=0.04,
                charge=20.0, center=(0.6, 0.0), solver='native',
                obstacles=[(1.2, 1.6, 0.0, 0.6)], t_end=2e-4,
                bcs=dict(x_lo='reflect', x_hi='terminate', y_lo='reflect',
                         y_hi='terminate'),
                gauges=[(0.3, 0.8), (1.4, 0.3), (0.9, 1.0)],
                n_snapshots=1, record_frames=0, gauge_file=None)
    why = run_gauges.drops(ew)
    check("drops(): G2 only, the reason names Wall 1",
          len(why) == 1 and why[0][0] == 2 and 'Wall 1' in why[0][1],
          str(why))
    h = _Handlers()
    c = RunController(handlers=h)
    check("start_stages accepts a native 2D case",
          c.start_stages([(2, ew)]) is True)
    end = time.time() + 300
    while c.running and time.time() < end:
        pump(100)
    got = h.results[0][3] if h.results else None
    check("the finished Result's meta['gauges_dropped'] is [[2, reason]]",
          got is not None and got.meta.get('gauges_dropped') == why
          and 'Wall 1' in why[0][1], str(got and got.meta.get(
              'gauges_dropped')))

    print("\nT5c: GUI-15 (f) - a 1D gauge beyond the radius, through Run")
    from blastlab.core.case import Case1D
    from blastlab.ui import results_gauges
    one = Case1D(radius_m=1.5, charge_kg=0.5, cell_size_m=0.005,
                 n_snapshots=1, gauge_radii=[1.0, 2.0, 1.2], gauge_file=None)
    h = _Handlers()
    c = RunController(handlers=h)
    check("start_stages accepts a native 1D case",
          c.start_stages([(1, one)]) is True)
    end = time.time() + 300
    while c.running and time.time() < end:
        pump(100)
    got = h.results[0][3] if h.results else None
    labels, dropped = (results_gauges.labels_and_dropped(got, 1)
                       if got is not None else ({}, []))
    check("Results labels the two series G1 and G3; its drop line names G2 "
          "outside the domain",
          labels == {1: 'G1', 2: 'G3'}
          and results_gauges.dropped_text(dropped)
          == 'G2 dropped by the solver (outside the domain)',
          f'{labels} {dropped}')
    check("the run log names G2 beyond the radius",
          any('G2 (r 2.00 m) outside the domain - dropped' in ln
              for ln in h.lines), str([ln for ln in h.lines if 'G2' in ln]))

    print("\nT6: refresh policy parsing")
    cases = [(('', 'seconds'), None), (('0', 'seconds'), None),
             (('0.25', 'seconds'), ('seconds', 0.25)),
             (('5', 'steps'), ('steps', 5)),
             (('2.6', 'steps'), ('steps', 3))]
    for (text, mode), want in cases:
        check(f"'{text}' as {mode} -> {want}",
              parse_refresh(text, mode) == want,
              str(parse_refresh(text, mode)))
    for text in ('abc', '-1', ''):
        if text == '':
            continue
        try:
            parse_refresh(text, 'seconds')
            ok = False
        except ValueError:
            ok = True
        check(f"'{text}' is rejected", ok)

    c, h = controller(bad_frame=False)
    check("a usable box is accepted and pushed to the hooks",
          c.apply_refresh('0.5', 'seconds')
          and c.worker.hooks.refresh == ('seconds', 0.5)
          and c.worker.hooks.refresh3d == ('seconds', 0.5))
    check("an unusable box reports False and falls back to automatic",
          c.apply_refresh('abc', 'seconds') is False
          and c.worker.hooks.refresh == _StubHooks.refresh)

    print("\nT7: stepped execution")
    c, h = controller(bad_frame=False)
    for cmd in (10, 'pause', 'run'):
        c.exec_cmd(cmd)
    check("commands reach the hooks",
          c.worker.hooks.exec_cmds == [10, 'pause', 'run'])
    check("each one says what it did in the log",
          len([ln for ln in h.lines if ln.startswith('  [')]) == 3, h.lines)

    print("\nT8: error_headline skips the traceback chrome")
    chained = ('Traceback (most recent call last):\n'
               '  File "a.py", line 2, in f\n'
               'ValueError: inner\n\n'
               'The above exception was the direct cause of the following '
               'exception:\n\n'
               'Traceback (most recent call last):\n'
               '  File "b.py", line 9, in g\n'
               'RuntimeError: outer\n')
    check("the first real exception line is used",
          error_headline(chained) == 'ValueError: inner',
          error_headline(chained))
    check("a bare message survives", error_headline('boom') == 'boom')

    pump(20)
    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
        sys.exit(1)
    print("All Qt run-controller checks passed.")


if __name__ == '__main__':
    main()
