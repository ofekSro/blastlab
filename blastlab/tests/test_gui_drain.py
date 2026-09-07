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
    the front."""
    import tempfile, shutil
    from blastlab.gui import chain_panel as cp

    seen = []
    real = cp.messagebox.showerror
    cp.messagebox.showerror = lambda title, msg: seen.append(msg)
    tmp = tempfile.mkdtemp(prefix='blastlab_chain_')
    ws = os.path.join(tmp, 'workspace')      # deliberately absent
    try:
        panel = cp.ChainPanel(root, on_run_chain=lambda *a: seen.append(
            'RAN'))
        panel.ws_var.set(ws)
        for d in (1, 2, 3):
            panel.use[d].set(d in (1, 2))
        panel.focus_stage(1)
        panel.forms[2].v['Lx'].set('abc')     # a parse error in stage 2
        panel._run()
        check("chain parse error names the stage",
              bool(seen) and seen[-1].startswith('Stage 2 (2D):'),
              seen[-1] if seen else '<no dialog>')
        check("chain switches to the offending stage",
              panel._current is panel.forms[2])
        check("chain does not create the workspace when it refuses",
              not os.path.exists(ws))
        check("chain did not start", 'RAN' not in seen)

        # a default under the user profile, not the process CWD
        home = os.path.expanduser('~')
        check("chain workspace defaults under the user profile",
              cp.ChainPanel(root, on_run_chain=lambda *a: None)
              .ws_var.get().startswith(home))
    finally:
        cp.messagebox.showerror = real
        shutil.rmtree(tmp, ignore_errors=True)


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

    root.destroy()
    print("\n" + "=" * 50)
    if FAIL:
        print(f"GUI DRAIN: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("GUI DRAIN: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
