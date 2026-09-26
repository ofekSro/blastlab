"""App._drain resilience: a handler exception must be logged and the
loop must keep draining (worker keeps solving; 'result'/'done' must
still arrive). Headless - no real Tk window, no solver run: the App is
instantiated on a hidden root and fed a synthetic worker queue."""
import os, sys
import queue

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import tkinter as tk

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


class _StubHooks:
    feed3d = None

    def latest_frame(self):
        raise RuntimeError('synthetic frame handler failure')

    def latest_frame3d(self):
        return None


class _StubWorker:
    def __init__(self):
        self.q = queue.Queue()
        self.hooks = _StubHooks()

    def is_alive(self):
        return True


class _LogPanel:
    """Captures on_log lines and progress-bar completion; every other
    panel call is a no-op."""

    def __init__(self):
        self.lines = []
        self.completed = 0

    def on_log(self, text):
        self.lines.append(str(text))

    def mark_complete(self):
        self.completed += 1

    def __getattr__(self, name):
        return lambda *a, **k: None


def chain_feedback_checks(root):
    """QA-23 / T28: the chain refuses BEFORE it creates anything, names
    the offending stage in the dialog, and brings that stage's form to
    the front. OUT-1: what must not appear is the model folder (the
    workspace box is gone, owner decision 14)."""
    import tempfile, shutil
    from blastlab.gui import chain_panel as cp

    seen = []
    real = cp.messagebox.showerror
    cp.messagebox.showerror = lambda title, msg: seen.append(msg)
    tmp = tempfile.mkdtemp(prefix='blastlab_chain_')
    ws = os.path.join(tmp, 'CHAINMODEL')     # the model folder, absent
    launched = []
    try:
        panel = cp.ChainPanel(
            root, on_run_chain=lambda st: (seen.append('RAN'),
                                           launched.append(st)),
            model_source=lambda: (tmp, 'CHAINMODEL'))
        for d in (1, 2, 3):
            panel.use[d].set(d in (1, 2))
        panel.focus_stage(1)
        panel.forms[2].v['Lx'].set('abc')     # a parse error in stage 2
        panel._run()
        check("chain parse error names the stage",
              bool(seen) and seen[-1].startswith('Stage 2 (2D):'),
              seen[-1] if seen else '<no dialog>')
        # T34: the stage stack holds a wrapper (solver switch + form)
        check("chain switches to the offending stage",
              panel._current is panel._stage_wrap[2]
              and panel.forms[2].winfo_manager() == 'pack')
        check("chain does not create the model folder when it refuses",
              not os.path.exists(ws))
        check("chain did not start", 'RAN' not in seen)

        # OUT-1: no workspace box; the Run tab's model boxes are checked
        check("chain has no workspace box any more",
              not hasattr(panel, 'ws_var'))
        empty = cp.ChainPanel(root, on_run_chain=lambda *a: seen.append(
            'RAN'), model_source=lambda: ('', 'CHAINMODEL'))
        for d in (1, 2, 3):
            empty.use[d].set(d in (1, 2))
        check("an empty Runs folder refuses, naming the box",
              empty._run() is False and seen[-1].startswith(
                  'Runs folder is empty') and 'RAN' not in seen,
              seen[-1] if seen else '<no dialog>')

        # a chain that is handed on: the hand-off wired at the model root
        panel.forms[2].v['Lx'].set('4')
        started = panel._run()
        stages = dict(launched[-1]) if launched else {}
        hand = os.path.join(ws, 'handoff_1d_to_2d.txt')
        check("a valid 1 -> 2 chain is handed on",
              started is True and sorted(stages) == [1, 2],
              seen[-1] if seen else '')
        check("with the hand-off at the model root as the 1D profile and "
              "the 2D input",
              stages and stages[1].profile_file == hand
              and stages[2].profile_file_in == hand
              and stages[2].init_mode == 'profile1d')
        check("and the panel itself wrote nothing (the app creates the "
              "folder)", not os.path.exists(ws))
    finally:
        cp.messagebox.showerror = real
        shutil.rmtree(tmp, ignore_errors=True)


def live_view_checks(root):
    """G7 / T38: the live view says how fast it can move, and its colour
    range can be pinned for the run."""
    import numpy as np
    from blastlab.core.constants import P_AIR
    from blastlab.solvers.hooks import Progress
    from blastlab.gui.run_panel import RunPanel

    rp = RunPanel(root, on_run=lambda: None, on_stop=lambda: None,
                  on_init=lambda: None, on_refresh=lambda: None)
    x_face = np.linspace(0.0, 1.0, 5)
    y_face = np.linspace(0.0, 1.0, 5)
    solid = np.zeros((4, 4), bool)
    info = dict(dim=2, x_face=x_face, y_face=y_face, solid=solid,
                xlabel='x [m]', ylabel='y [m]', title='y = 1.25 m')
    field = P_AIR + 1e3 * np.arange(16, dtype=float).reshape(4, 4)

    # a native run: no cadence is claimed
    rp.set_running(True)
    rp.on_run_started(info)
    rp.on_frame(field, 1.23e-4)
    check("native live title has no cadence hint",
          'frames every' not in rp._title.get_text(),
          rp._title.get_text())

    # a foam run without a live sample: writeInterval drives the view
    rp.set_running(True)
    rp.on_run_started(info)
    rp.set_cadence(dt=5e-5)
    rp.on_frame(field, 1.23e-4)
    txt = rp._title.get_text()
    check("foam live title carries t and the cadence",
          't = 0.123 ms' in txt and 'frames every ~0.05 ms' in txt, txt)
    rp.on_frame(field, 2.0e-4)
    check("the cadence suffix is not duplicated frame after frame",
          rp._title.get_text().count('frames every') == 1,
          rp._title.get_text())
    rp.set_cadence(dt=1e-4)           # the adaptive controller moved it
    rp.on_frame(field, 3.0e-4)
    check("a changed writeInterval updates the hint",
          'frames every ~0.1 ms' in rp._title.get_text(),
          rp._title.get_text())
    rp.set_cadence(dt=1e-6)
    rp.on_frame(field, 3.0e-4)
    check("a sub-microsecond-scale cadence reads in microseconds",
          'frames every ~1 µs' in rp._title.get_text(),
          rp._title.get_text())

    # with a live sample the cadence is N solver steps; the newest dt
    # turns that into the time the user actually asked for
    rp.set_cadence(steps=5)
    check("no solver dt yet: the hint falls back to steps",
          rp.cadence_text() == 'frames every ~5 solver steps',
          rp.cadence_text())
    rp.on_progress(Progress(step=10, t=1e-4, dt=2e-8, p_max=P_AIR, frac=0.1))
    check("a step cadence is reported as a time once dt is known",
          rp.cadence_text() == 'frames every ~0.1 µs', rp.cadence_text())
    rp.set_cadence(steps=50)          # "Refresh every 50 steps"
    check("changing the refresh policy moves the hint",
          rp.cadence_text() == 'frames every ~1 µs', rp.cadence_text())
    rp.set_running(True)
    check("a new run drops the previous run's cadence",
          rp._cadence == 0.0)

    # colour range: auto by default, pinned on demand, and it holds
    rp.set_running(True)
    rp.on_run_started(info)
    check("the live pane autoscales by default", rp.live_clim() is None)
    check("the Min/Max boxes are inert while Auto is on",
          all(str(e.cget('state')) == 'disabled' for e in rp._clim_entries))
    rp.auto_clim_var.set(False)
    rp.clim_min.set('0')
    rp.clim_max.set('250')
    rp._clim_changed()
    check("the Min/Max boxes wake up with Auto off",
          all(str(e.cget('state')) == 'normal' for e in rp._clim_entries))
    check("a manual range is used", rp.live_clim() == (0.0, 250.0))
    rp.on_frame(field, 1e-4)
    check("the frame is drawn in the manual range",
          tuple(rp._mesh.get_clim()) == (0.0, 250.0),
          str(rp._mesh.get_clim()))
    rp.clim_max.set('abc')
    check("an unusable range falls back to autoscale, not a frozen one",
          rp.live_clim() is None)
    rp.clim_max.set('40')
    rp._clim_changed()
    check("editing the range redraws the frame already on screen",
          tuple(rp._mesh.get_clim()) == (0.0, 40.0),
          str(rp._mesh.get_clim()))
    rp.destroy()


def main():
    from blastlab.gui.app import App

    root = tk.Tk()
    root.withdraw()
    app = App.__new__(App)          # skip full GUI construction
    app.root = root
    app.worker = _StubWorker()
    app.run_panel = _LogPanel()
    app.results = _LogPanel()
    app.chain = _LogPanel()         # the drain re-enables Run chain (G5)
    app._stage_dims = [2]
    app._run_count = 1

    # T1: a message whose handler raises must not kill the drain pass
    app.worker.q.put(('frame',))            # latest_frame raises
    app.worker.q.put(('log', 'still alive'))
    app.worker.q.put(('done',))
    app._drain()

    logged = '\n'.join(app.run_panel.lines)
    check("handler exception logged",
          'synthetic frame handler failure' in logged)
    check("later messages still dispatched", 'still alive' in logged)
    check("'done' still finalizes", '[run finished]' in logged)

    # T2: a clean pass with no exceptions stays clean
    app.worker = _StubWorker()
    app.run_panel = _LogPanel()
    app.worker.q.put(('log', 'ok line'))
    app.worker.q.put(('done',))
    app._drain()
    check("clean pass logs normally",
          'ok line' in '\n'.join(app.run_panel.lines))
    check("no spurious ui-error", 'ui error' not in
          '\n'.join(app.run_panel.lines))

    # T3: B22 - the failure dialog must show the exception headline, not
    # the last line of the solver log tail the message carries
    import blastlab.gui.app as appmod
    shown = []

    class _Box:
        @staticmethod
        def showerror(title, text):
            shown.append((title, text))

    real_box = appmod.messagebox
    appmod.messagebox = _Box
    try:
        app.worker = _StubWorker()
        app.run_panel = _LogPanel()
        app._run_stopped_early = app._run_errored = False
        app.worker.q.put(('error', (
            'Traceback (most recent call last):\n'
            '  File "app.py", line 1, in <module>\n'
            '    solve(case)\n'
            'RuntimeError: blastFoam failed (exit 1) - case kept at '
            r'\\wsl.localhost\Ubuntu\root\blastlab_runs\x_3d' '\n'
            'Create time = 0.01 s\n'
            'End\n')))
        app.worker.q.put(('done',))
        app._drain()
        text = shown[-1][1] if shown else ''
        check("failure dialog leads with the exception headline",
              text.startswith('RuntimeError: blastFoam failed (exit 1)'),
              text.splitlines()[0] if text else '(no dialog shown)')
        check("failure dialog points at the log",
              'See the run log for details.' in text)
        check("full traceback still reaches the log pane",
              'Create time = 0.01 s' in '\n'.join(app.run_panel.lines))
        check("a failed run does not fill the progress bar",
              app.run_panel.completed == 0)
    finally:
        appmod.messagebox = real_box

    # T4: G6 - a run that reached its own end fills the bar (the final
    # progress message is usually throttled away); a stopped one doesn't
    app.worker = _StubWorker()
    app.run_panel = _LogPanel()
    app._run_stopped_early = app._run_errored = False
    app.worker.q.put(('done',))
    app._drain()
    check("completed run fills the progress bar",
          app.run_panel.completed == 1)

    class _StoppedResult:
        stopped_early = True
        stop_reason = 'stopped by user'
        meta = {}

    app.worker = _StubWorker()
    app.run_panel = _LogPanel()
    app._run_stopped_early = app._run_errored = False
    app.worker.q.put(('result', 0, _StoppedResult()))
    app.worker.q.put(('done',))
    app._drain()
    check("stopped run leaves the bar where the run stopped",
          app.run_panel.completed == 0)

    chain_feedback_checks(root)
    live_view_checks(root)

    root.destroy()
    print("\n" + "=" * 50)
    if FAIL:
        print(f"GUI DRAIN: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("GUI DRAIN: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
