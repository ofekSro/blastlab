"""I02 (TODO.md GUI-16 batch, task D3): closing the Qt window during a
native 3D run must take under 12 s.

Real platform (QT_QPA_PLATFORM unset: the viewer child embeds a real
window, as in the app). Each trial is a process of its own, so every
close starts from a fresh app, exactly like harness scenario I02: the
N3D case, Run, wait for the solver's banner, two seconds of solving,
then `close()`.

The close is timed the way I02 times it - `close()` plus one second of
event pumping - and split into its steps: the stop request, the worker
thread's exit, the two 3D hosts' shutdown and the viewer child's exit.
While the worker winds down, its stack is sampled every 50 ms, so a
slow exit names the function it spent the time in.

Pre-registered rule (plan D3): every trial < 12.0 s, 3 of 3. And the
stopped run's model folder is complete once `finish_writes` (what
`ui.app.main()` calls after the window is gone) returns: manifest.json
says `finished` and report.html exists - the close must not get under
12 s by cutting the writes short.

Measured before the fix (2026-10-13, office PC, 1 trial): close 11.57 s,
the stop->join wait hit its 10.0 s timeout, the worker ended 17.2 s after
the close began - inside write_animation, run_export and the report's
field figures - so the real app exited under a half-written folder.

    python blastlab/tests/_e2e_ui_close_during_run.py [--trials N]
"""
import json
import os
import subprocess
import sys
import threading
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

LIMIT_S = 12.0
TRIALS = 3


def n3d_case():
    """Harness I02's case (`_qa_ui_harness.cases()['N3D']`)."""
    from blastlab.core.case import Case3D
    return Case3D(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.05,
                  charge=50.0, center=(1.0, 1.0, 0.7),
                  obstacles=[(1.4, 1.7, 0.7, 1.3, 0.0, 0.6)],
                  gauges=[(1.7, 1.0, 0.7), (1.0, 1.7, 0.7)],
                  n_snapshots=3, record_frames=40, live=True,
                  anim_file='blast_3d_animation.gif')


class StackSampler(threading.Thread):
    """The innermost blastlab frames of one thread, every 50 ms."""

    def __init__(self, ident):
        super().__init__(daemon=True)
        self.target = ident
        self.hits = Counter()
        self.halt = threading.Event()

    def run(self):
        import traceback
        while not self.halt.is_set():
            frame = sys._current_frames().get(self.target)
            if frame is None:
                break
            ours = [f for f in traceback.extract_stack(frame)
                    if 'blastlab' in f.filename]
            if ours:
                f = ours[-1]
                self.hits[f'{os.path.basename(f.filename)}:'
                          f'{f.name}'] += 1
            self.halt.wait(0.05)


def timed(marks, key, fn):
    def wrapper(*a, **kw):
        t0 = time.perf_counter()
        try:
            return fn(*a, **kw)
        finally:
            # the first call is the close's (finish_writes joins again)
            marks.setdefault(key, (t0, time.perf_counter()))
    return wrapper


def trial():
    from blastlab.ui.testing import (answer_discard, ensure_qapp,
                                     private_settings, pump, use_model)
    private_settings()
    answer_discard()
    app = ensure_qapp(offscreen=False)
    from blastlab.ui import theme
    from blastlab.ui.app import MainWindow
    theme.apply(app, 'dark')
    win = MainWindow()
    folder = use_model(win)
    win.show()
    pump(300)
    win.setup.set_case(n3d_case())
    win._schedule_validate()
    pump(800)
    win._run_single()
    t_wait = time.monotonic() + 40
    while time.monotonic() < t_wait:
        pump(50)
        if '3D Blast Solver' in win.run_panel.log_text():
            break
    started = '3D Blast Solver' in win.run_panel.log_text()
    pump(2000)
    worker = win.ctrl.worker
    marks = {}
    sampler = StackSampler(worker.ident) if worker is not None else None
    if worker is not None:
        stop = worker.stop

        def stop_and_sample():
            marks['stop'] = time.perf_counter()
            stop()
            sampler.start()
        worker.stop = stop_and_sample
        worker.join = timed(marks, 'join', worker.join)
    win.view3d.shutdown = timed(marks, 'view3d', win.view3d.shutdown)
    win.results.shutdown = timed(marks, 'results', win.results.shutdown)
    win.viewer_link.close = timed(marks, 'viewer', win.viewer_link.close)
    win.ctrl.shutdown = timed(marks, 'ctrl', win.ctrl.shutdown)

    t0 = time.perf_counter()
    win.close()
    t_ret = time.perf_counter()
    pump(1000)
    t_end = time.perf_counter()
    alive = worker.is_alive() if worker is not None else False
    # what `ui.app.main()` does once the window is gone
    finished = win.ctrl.finish_writes(timeout_s=60.0)
    worker_exit = None
    if worker is not None:
        worker_exit = time.perf_counter() - t0
        sampler.halt.set()
    manifests = []
    for root, _dirs, files in os.walk(folder):
        if 'manifest.json' in files:
            with open(os.path.join(root, 'manifest.json'),
                      encoding='utf-8') as f:
                m = json.load(f)
            manifests.append(dict(
                stage=os.path.relpath(root, folder),
                finished=bool(m.get('finished')),
                report=os.path.isfile(os.path.join(root, 'report.html')),
                failed=len(m.get('failed') or ())))

    def span(key):
        if key not in marks:
            return None
        a, b = marks[key]
        return round(b - a, 3)
    out = dict(
        started=started,
        close_s=round(t_end - t0, 3),           # I02's own number
        close_call_s=round(t_ret - t0, 3),
        ctrl_shutdown_s=span('ctrl'),
        join_s=span('join'),
        worker_alive_after_close=alive,
        finish_writes=finished,
        worker_exit_s=None if worker_exit is None else round(worker_exit, 3),
        manifests=manifests,
        view3d_shutdown_s=span('view3d'),
        results_shutdown_s=span('results'),
        viewer_close_s=span('viewer'),
        viewer_alive=win.viewer_link.alive,
        worker_stack=(sampler.hits.most_common(6) if sampler else []),
    )
    print('RESULT ' + json.dumps(out), flush=True)


def main():
    n = TRIALS
    if '--trials' in sys.argv:
        n = int(sys.argv[sys.argv.index('--trials') + 1])
    env = dict(os.environ)
    env.pop('QT_QPA_PLATFORM', None)       # CLAUDE.md §8.7: real platform
    env.setdefault('MPLBACKEND', 'Agg')
    times, bad = [], []
    for k in range(n):
        proc = subprocess.run([sys.executable, '-u', __file__, '--trial'],
                              cwd=REPO, env=env, capture_output=True,
                              text=True, encoding='utf-8', errors='replace',
                              timeout=300)
        rows = [ln[7:] for ln in proc.stdout.splitlines()
                if ln.startswith('RESULT ')]
        if not rows:
            print(f'trial {k + 1}: no result (exit {proc.returncode})')
            print(proc.stdout[-2000:], proc.stderr[-2000:])
            bad.append(k + 1)
            continue
        r = json.loads(rows[-1])
        times.append(r['close_s'])
        print(f"trial {k + 1}: close {r['close_s']:.2f} s "
              f"(close() {r['close_call_s']:.2f} s; stop->join "
              f"{r['join_s']} s, worker gone at {r['worker_exit_s']} s; "
              f"view3d {r['view3d_shutdown_s']} s, results "
              f"{r['results_shutdown_s']} s, viewer {r['viewer_close_s']} s)")
        print(f"         worker stack while stopping: {r['worker_stack']}")
        print(f"         model folder after finish_writes "
              f"({r['finish_writes']}): {r['manifests']}")
        # the window under 12 s, AND the stopped run's model folder still
        # complete afterwards (the writes are not cut short to get there)
        complete = r['finish_writes'] and r['manifests'] and all(
            m['finished'] and m['report'] for m in r['manifests'])
        if not r['started'] or r['close_s'] >= LIMIT_S or not complete:
            bad.append(k + 1)
    print('Qt close times (s): ' + ', '.join(f'{t:.2f}' for t in times))
    if bad or len(times) < n:
        print(f'FAILED: trials {bad} (rule: every close < {LIMIT_S} s)')
        sys.exit(1)
    print(f'All {n} closes under {LIMIT_S} s.')


if __name__ == '__main__':
    if '--trial' in sys.argv:
        trial()
    else:
        main()
