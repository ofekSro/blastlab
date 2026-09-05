"""Ordered ingest + peak/impulse accumulator (B16, B17) - no WSL.

Builds fake time directories on disk to drive runloop.OrderedIngest and
runloop.PeakImpulse through the paths the live WSL suites never hit: an
earlier dir that is torn while later ones are complete, the final sweep,
an out-of-order write reaching the accumulator, and the stale-FO finalize
policy.

Run:  cd blastlab/tests && python test_foam_ingest_order.py
"""
import os
import shutil
import sys
import tempfile
import types

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core import geometry                              # noqa: E402
from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.solvers.foam import runloop                       # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


class Log:
    def __init__(self):
        self.lines = []

    def log(self, s):
        self.lines.append(s)


FIELDS = ('p', 'rho')


def make_dir(root, name, complete=True):
    """A fake time dir: reader.time_ready wants every field file plus
    uniform/time; an incomplete (mid-write) dir has only `p`."""
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    for f in FIELDS if complete else FIELDS[:1]:
        with open(os.path.join(d, f), 'w') as fh:
            fh.write('x')
    if complete:
        os.makedirs(os.path.join(d, 'uniform'), exist_ok=True)
        with open(os.path.join(d, 'uniform', 'time'), 'w') as fh:
            fh.write('x')
    return d


def names(order, done, final=False):
    return [n for n, _d in order.pending(done, final)]


def test_ordered_ingest():
    print("\nB16: strictly ordered ingest")
    root = tempfile.mkdtemp(prefix='blastlab_ingest_')
    try:
        spec = types.SimpleNamespace(case_unc=root)
        hooks = Log()
        order = runloop.OrderedIngest(spec, FIELDS, hooks)
        make_dir(root, '0')
        make_dir(root, '0.001', complete=False)     # still being written
        make_dir(root, '0.002')
        done = {}
        got = names(order, done)
        check('pass stops at the first not-ready dir', got == ['0'], str(got))
        done['0'] = 0.0
        # 0.001 is the head of the queue while 0.002 is complete -> one stall
        # per poll (the first pass above already counted one)
        check('first pass already counted the stall', order.stalls.get('0.001') == 1, str(order.stalls))
        for _ in range(runloop.STALL_POLLS - 2):
            got = names(order, done)
            check_ok = got == []
            if not check_ok:
                break
        check('later complete dir is never yielded before the gap closes', check_ok, str(got))
        check('no skip logged before the stall limit', not hooks.lines, str(hooks.lines))
        got = names(order, done)
        check('gap skipped after _STALL_POLLS polls', got == ['0.002'], str(got))
        check('skip logged once', len(hooks.lines) == 1 and 'stayed unreadable' in hooks.lines[0], str(hooks.lines))
        got = names(order, done)
        check('skipped dir stays skipped', got == ['0.002'] and len(hooks.lines) == 1, str(got))

        # a torn read (exception in the body) follows the same policy
        hooks2 = Log()
        order2 = runloop.OrderedIngest(spec, FIELDS, hooks2)
        make_dir(root, '0.001')                     # now complete on disk
        done2 = {'0': 0.0}
        seq = []
        for name, _d in order2.pending(done2):
            if name == '0.001':                     # simulate a torn read
                if order2.unreadable(name):
                    continue
                break
            seq.append(name)
        check('torn read ends the pass (retry next poll)', seq == [], str(seq))
        check('torn read counted as a stall', order2.stalls.get('0.001') == 1, str(order2.stalls))

        # the head of the queue being incomplete with NOTHING complete behind it is normal
        hooks3 = Log()
        order3 = runloop.OrderedIngest(spec, FIELDS, hooks3)
        shutil.rmtree(os.path.join(root, '0.002'))
        shutil.rmtree(os.path.join(root, '0.001'))
        make_dir(root, '0.001', complete=False)
        for _ in range(3 * runloop.STALL_POLLS):
            names(order3, {'0': 0.0})
        check('in-progress newest write never counts as a stall', not order3.stalls and not hooks3.lines, str(order3.stalls))

        # final sweep: gaps are skipped at once so later complete dirs are kept
        make_dir(root, '0.002')
        hooks4 = Log()
        order4 = runloop.OrderedIngest(spec, FIELDS, hooks4)
        got = names(order4, {'0': 0.0}, final=True)
        check('final sweep skips a gap immediately', got == ['0.002'], str(got))
        check('final-sweep skip logged', len(hooks4.lines) == 1, str(hooks4.lines))
        check('final-sweep wording', 'after the solver exited' in hooks4.lines[0], str(hooks4.lines))
        # skip(): a dir refused by the accumulator is never yielded again
        order4.skip('0.002')
        got = names(order4, {'0': 0.0}, final=True)
        check('skip() removes a dir from every later pass', got == [] and len(hooks4.lines) == 1, str(got))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_accumulator():
    print("\nB17: peak/impulse accumulator + finalize policy")
    fo = {}                                          # dpath -> (peak, imp) or None
    real = runloop.read_fo_fields
    runloop.read_fo_fields = lambda dpath, spec: fo.get(dpath, (None, None))
    try:
        hooks = Log()
        spec = object()
        p0 = np.full(4, P_AIR)
        p1 = p0 + 1000.0
        p2 = p0 + 500.0
        acc = runloop.PeakImpulse()
        check('first write accepted', acc.add(p0, 0.0, 'd0', spec, hooks))
        check('second write accepted', acc.add(p1, 1e-3, 'd1', spec, hooks))
        check('impulse = sum ovp*dt', np.allclose(acc.impulse, 1000.0 * 1e-3), str(acc.impulse))
        check('peak tracks max', np.allclose(acc.p_peak, p1))
        check('missing-FO note logged once', sum('pMax/impulse fields not found' in l for l in hooks.lines) == 1, str(hooks.lines))
        # out-of-order write is refused and logged (B16 guard)
        n_before = len(hooks.lines)
        check('earlier t refused', not acc.add(p2, 0.5e-3, 'dX', spec, hooks))
        check('refusal logged', len(hooks.lines) == n_before + 1 and 'not accumulated' in hooks.lines[-1], str(hooks.lines[-1:]))
        check('refused write left the accumulator untouched', np.allclose(acc.impulse, 1.0) and acc.t_py == 1e-3)
        check('third write accepted', acc.add(p2, 2e-3, 'd2', spec, hooks))
        check('impulse after third', np.allclose(acc.impulse, 1.0 + 500.0 * 1e-3), str(acc.impulse))

        # finalize policy, no FO anywhere -> python-writes
        pk, imp, src = acc.final(p2, 'd2', 2e-3, spec)
        check("no FO -> 'python-writes'", src == 'python-writes' and pk is acc.p_peak, src)

        # FO present on the final dir -> foam-fo
        fo_pk, fo_im = p1 + 1.0, np.ones(4)
        fo['d2'] = (fo_pk, fo_im)
        pk, imp, src = acc.final(p2, 'd2', 2e-3, spec)
        check("final-dir FO -> 'foam-fo'", src == 'foam-fo' and pk is fo_pk, src)

        # stale FO (last read at t=1 ms) but the final dir's FO read fails -> python-fallback
        acc2 = runloop.PeakImpulse()
        fo.clear()
        fo['e1'] = (fo_pk, fo_im)
        acc2.add(p0, 0.0, 'e0', spec, hooks)
        acc2.add(p1, 1e-3, 'e1', spec, hooks)
        acc2.add(p2, 2e-3, 'e2', spec, hooks)           # no FO for e2
        check('FO time remembered', acc2.t_fo == 1e-3, str(acc2.t_fo))
        pk_live, _ = acc2.live()
        check('live frames prefer FO while it exists', pk_live is fo_pk)
        pk, imp, src = acc2.final(p2, 'e2', 2e-3, spec)
        check("stale FO -> 'python-fallback' with the Python maps", src == 'python-fallback' and pk is acc2.p_peak, src)
        # FO that already covers t_fin (read during ingest) stays authoritative
        pk, imp, src = acc2.final(p1, 'e1', 1e-3, spec)
        check("FO covering t_fin -> 'foam-fo'", src == 'foam-fo' and pk is fo_pk, src)
        # final() folds the final frame into the Python peak even after a _final_read fallback
        acc3 = runloop.PeakImpulse()
        acc3.add(p0, 0.0, 'f0', spec, hooks)
        pk, imp, src = acc3.final(p1, 'f1', 1e-3, spec)
        check('final frame folded into the Python peak', np.allclose(pk, p1) and src == 'python-writes')
    finally:
        runloop.read_fo_fields = real


def dists(case, spec):
    return geometry.stop_dists_3d(case.Lx, case.Ly, case.Lz,
                                  [c for c, _m in spec.charges], case.bcs)


def test_stop_dists():
    print("\nB21: 3D stop/progress distances use the nearest charge")
    case = types.SimpleNamespace(Lx=2.0, Ly=2.0, Lz=2.0,
                                 bcs=dict(x_lo='wall', x_hi='open', y_lo='wall',
                                          y_hi='wall', z_lo='wall', z_hi='open'))
    spec = types.SimpleNamespace(center=(0.7, 1.0, 1.0),
                                 charges=[((0.7, 1.0, 1.0), 4.0), ((1.4, 1.0, 0.5), 2.0)])
    d = dists(case, spec)
    check('x_hi from the secondary charge (0.6), z_hi from the primary (1.0 < 1.5)', np.allclose(sorted(d), [0.6, 1.0]), str(d))
    case.bcs = {k: 'wall' for k in case.bcs}
    d = dists(case, spec)
    check('closed box -> far corner from the primary', np.allclose(d, [np.sqrt(1.3**2 + 1 + 1)]), str(d))


if __name__ == '__main__':
    test_ordered_ingest()
    test_accumulator()
    test_stop_dists()
    print()
    print('FOAM INGEST ORDER: ' + ('PASS' if not FAILS else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
