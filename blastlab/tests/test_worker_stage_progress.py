"""F28 (GUI-11 c, D209): a chain stage start forgets the last stage's
progress.

In a held chain (Initialise, Exec or Pause in force when a stage
starts), `GuiHooks.step_gate` calls `flush_progress` at the new stage's
first step. Before F28 that re-posted `_last_p`, the PREVIOUS stage's
final Progress, so the Run tiles showed its step, time, p max and
100 % again until the held stage stepped. `run_started` now clears
`_last_p`.

Drives `GuiHooks` directly, no Qt and no solver. Run:
    cd blastlab/tests && python test_worker_stage_progress.py
"""
import os
import queue
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.solvers.hooks import Progress            # noqa: E402
from blastlab.solvers.worker import GuiHooks            # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def tags(msgs):
    """(tag, step) per message; step only for 'progress'."""
    return [(m[0], m[1].step if m[0] == 'progress' else None)
            for m in msgs]


INFO = dict(dim=2, shape=(10, 10))
P201 = Progress(step=201, t=2.5e-4, dt=1.45e-6, p_max=3.1e5, frac=1.0)
P3 = Progress(step=3, t=1e-6, dt=1e-7, p_max=1e5, frac=0.01)


print('\nW1: flush_progress after run_started carries no stage-1 step')
q = queue.Queue()
hk = GuiHooks(q, threading.Event())
hk.progress(P201)                     # stage 1's last step
hk.flush_progress()                   # stage 1 ends (worker.run)
before = drain(q)
check('stage 1 posts its final progress (step 201)',
      [s for t, s in tags(before) if t == 'progress'][-1:] == [201],
      str(tags(before)))
hk.run_started(dict(INFO))            # stage 2 starts
hk.flush_progress()                   # what step_gate does when held
after = tags(drain(q))
check('after run_started the queue holds no progress with step 201',
      not any(t == 'progress' and s == 201 for t, s in after), str(after))
check('run_started is still posted', ('run_started', None) in after,
      str(after))

print('\nW2: the real step_gate, held at stage 2\'s first step')
q = queue.Queue()
stop = threading.Event()
hk = GuiHooks(q, stop)
hk.progress(P201)
hk.flush_progress()
drain(q)
hk.set_exec('pause')                  # Initialise / Pause in force
hk.run_started(dict(INFO))
gate = threading.Thread(target=hk.step_gate, daemon=True)
gate.start()
seen = []
t_end = time.monotonic() + 5.0
while time.monotonic() < t_end and ('paused', True) not in [
        (m[0], m[1]) for m in seen if m[0] == 'paused']:
    try:
        seen.append(q.get(timeout=0.05))
    except queue.Empty:
        pass
held = tags(seen)
check('the gate holds (paused True posted)',
      any(m[0] == 'paused' and m[1] is True for m in seen), str(held))
check('no progress with step 201 after run_started while held',
      not any(t == 'progress' and s == 201 for t, s in held), str(held))
hk.set_exec('run')                    # release
gate.join(2.0)
check('the gate releases', not gate.is_alive())
stop.set()

print('\nW3: stage 2\'s own progress still flushes')
q = queue.Queue()
hk = GuiHooks(q, threading.Event())
hk.progress(P201)
hk.run_started(dict(INFO))
hk._last_progress = time.monotonic()  # inside the 10 Hz throttle
hk.progress(P3)                       # dropped by the throttle ...
drain(q)
hk.flush_progress()                   # ... and re-posted by the flush
flushed = [s for t, s in tags(drain(q)) if t == 'progress']
check('flush after stage 2\'s first progress posts step 3', flushed == [3],
      str(flushed))

print()
if FAIL:
    print(f'WORKER STAGE PROGRESS: FAIL ({len(FAIL)}): {FAIL}')
    sys.exit(1)
print('WORKER STAGE PROGRESS: PASS')
