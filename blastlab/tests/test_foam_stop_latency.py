"""WHEN the foam run loop reads the user's Stop flag, not whether.

`test_foam_stop.py` proves a stopped run ends through `stopAt writeNow`
with a clean partial Result, but it cannot see the latency: it asserts
on the outcome, and the outcome is the same however long the loop took
to notice.

The loop used to consult `hooks.should_stop()` once per lap, AFTER
`_ingest_ready()` - and that method is the expensive one, holding up to
four `reconstructPar` runs plus a full-field read per pending write.
Measured on a real parallel 3D run: mean 0.09 s per lap but 3.92 s at
worst, and about 12 s on a big one (T61). So pressing Stop bought a wait
of anywhere between zero and one whole lap before blastFoam was even
told - pure latency, and invisible to a test that only checks the end
state. Whether the owner saw 0.1 s or 12 s was down to where in the lap
they happened to click.

No WSL: the loop is built without `__init__` (which would start a real
solver) and driven against stubs, so this pins the ORDER of operations
deterministically rather than racing a real run.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.solvers.foam import runloop as RL                 # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


class FakeFoam:
    def __init__(self, running=True, stop_requested=False):
        self.running = running
        self.stop_requested = stop_requested
        self.write_now_calls = 0

    def request_write_now(self):
        self.write_now_calls += 1
        self.stop_requested = True
        return True


class FakeHooks:
    def __init__(self, stop=False):
        self._stop = stop
        self.logs = []

    def should_stop(self):
        return self._stop

    def log(self, line):
        self.logs.append(line)


class FakeOrder:
    def __init__(self, names):
        self.names = list(names)

    def pending(self, done, final):
        return [(n, f'/case/{n}') for n in self.names]

    def unreadable(self, name):
        return True

    def skip(self, name):
        pass


def build_loop(pending=('0.1', '0.2', '0.3', '0.4'), stop=False,
               running=True, stop_requested=False):
    """A FoamRunLoop with everything `_ingest_ready` touches, and
    nothing else. `__new__` on purpose: `__init__` starts a solver."""
    loop = RL.FoamRunLoop.__new__(RL.FoamRunLoop)
    # n_procs = 1 makes maybe_reconstruct return on its first line, so
    # this test says nothing about reconstruction - only about ordering
    # n_cells only feeds stop_grace (the writeNow -> kill window)
    loop.spec = type('Spec', (), {'n_procs': 1, 'decomposed': False,
                                  'n_cells': 100_000})()
    loop.fields = ()
    loop.done = {}
    loop.live_set = None            # makes _ingest_live a no-op
    loop.order = FakeOrder(pending)
    loop.hooks = FakeHooks(stop=stop)
    loop.foam = FakeFoam(running=running, stop_requested=stop_requested)
    loop.stop_reason = 'safety cap'
    loop.stop_deadline = None
    loop.ingested = []

    def read_dir(name, dpath):
        return {'name': name}

    def on_frame(name, dpath, payload):
        loop.ingested.append(name)
        return True

    loop.read_dir = read_dir
    loop.on_frame = on_frame
    return loop


def instrument(loop):
    """Record how many frames had been ingested when the stop went out."""
    real = loop.request_stop

    def request_stop(reason):
        loop.at_request = len(loop.ingested)
        loop.stop_reasons = getattr(loop, 'stop_reasons', [])
        loop.stop_reasons.append(reason)
        return real(reason)
    loop.request_stop = request_stop
    return loop


def run(name, **kw):
    loop = instrument(build_loop(**kw))
    loop._ingest_ready(final=kw.pop('final', False))
    return loop


def main():
    print('FOAM STOP LATENCY')

    # 1 - the stop goes out at the TOP of the ingest, not after it
    loop = instrument(build_loop(stop=True))
    loop._ingest_ready()
    check('a pending Stop is requested before any frame is ingested',
          getattr(loop, 'at_request', None) == 0,
          f'frames ingested first = {getattr(loop, "at_request", "never")}')
    check('the writeNow actually went to the solver',
          loop.foam.write_now_calls == 1,
          f'{loop.foam.write_now_calls} call(s)')
    check("the reason is the user's",
          getattr(loop, 'stop_reasons', []) == ['stopped by user'],
          repr(getattr(loop, 'stop_reasons', [])))

    # 2 - and the ingest is NOT truncated: a stop must still drain what
    #     is already on disk, or the last writes are lost
    check('every pending write is still ingested after the stop',
          loop.ingested == ['0.1', '0.2', '0.3', '0.4'],
          repr(loop.ingested))

    # 3 - a stop arriving mid-ingest is seen within one frame, not at
    #     the end of the lap. `should_stop` flips after frame 2.
    loop = instrument(build_loop())
    seen = {'n': 0}
    _on_frame = loop.on_frame

    def on_frame(name, dpath, payload):
        r = _on_frame(name, dpath, payload)
        seen['n'] += 1
        if seen['n'] == 2:
            loop.hooks._stop = True
        return r
    loop.on_frame = on_frame
    loop._ingest_ready()
    check('a Stop raised mid-ingest goes out on the next frame',
          getattr(loop, 'at_request', None) == 2,
          f'frames ingested first = {getattr(loop, "at_request", "never")}')

    # 4 - the final sweep must not ask a dead solver to write
    loop = instrument(build_loop(stop=True, running=False))
    loop._ingest_ready(final=True)
    check('the final sweep sends no writeNow',
          loop.foam.write_now_calls == 0
          and getattr(loop, 'at_request', None) is None)
    check('the final sweep still ingests everything',
          loop.ingested == ['0.1', '0.2', '0.3', '0.4'],
          repr(loop.ingested))

    # 5 - an exited solver is never asked, even on an ordinary lap
    loop = instrument(build_loop(stop=True, running=False))
    loop._ingest_ready()
    check('an exited solver is not sent a writeNow',
          loop.foam.write_now_calls == 0,
          f'{loop.foam.write_now_calls} call(s)')

    # 6 - and a stop already in flight is not re-sent per frame, which
    #     would rewrite controlDict four times over
    loop = instrument(build_loop(stop=True, stop_requested=True))
    loop._ingest_ready()
    check('a stop already requested is not sent again',
          loop.foam.write_now_calls == 0,
          f'{loop.foam.write_now_calls} call(s)')

    # 7 - no Stop, no interference
    loop = instrument(build_loop(stop=False))
    loop._ingest_ready()
    check('an unstopped run is untouched',
          loop.foam.write_now_calls == 0
          and loop.ingested == ['0.1', '0.2', '0.3', '0.4']
          and loop.stop_reason == 'safety cap')

    print('\nFOAM STOP LATENCY: ' + ('FAIL - ' + ', '.join(FAIL)
                                    if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
