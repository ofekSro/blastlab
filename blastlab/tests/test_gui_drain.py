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
    """Captures on_log lines; every other panel call is a no-op."""

    def __init__(self):
        self.lines = []

    def on_log(self, text):
        self.lines.append(str(text))

    def __getattr__(self, name):
        return lambda *a, **k: None


def main():
    from blastlab.gui.app import App

    root = tk.Tk()
    root.withdraw()
    app = App.__new__(App)          # skip full GUI construction
    app.root = root
    app.worker = _StubWorker()
    app.run_panel = _LogPanel()
    app.results = _LogPanel()
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

    root.destroy()
    print("\n" + "=" * 50)
    if FAIL:
        print(f"GUI DRAIN: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("GUI DRAIN: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
