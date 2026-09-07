"""Foam live-refresh gating tests: _due_sparse must honor the GUI
refresh policy for the sporadically-polled ingest paths. Regression
for the 3D live view never updating in steps mode: the old gate used
RunHooks._due's `step % n == 0`, which a caller that only runs when a
time directory lands (at arbitrary step counts) almost never hits.

Also covers _progress_line's t/end_time fallback (B7): the progress
bar must move from the first solver step, not sit at 0 until the first
written time directory lands.

Pure python - no WSL required.

Run:  python test_foam_live_due.py
"""

import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.solvers.foam.runloop import (due_sparse as _due_sparse, new_live as _new_live, progress_line as _progress_line)  # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402
from blastlab.solvers.hooks import RunHooks                    # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def main():
    # fresh state: the very first frame is due immediately in both modes
    check('first frame due (steps)',
          _due_sparse(('steps', 50), 0, _new_live()))
    check('first frame due (seconds)',
          _due_sparse(('seconds', 10.0), 0, _new_live()))

    # steps mode gates on steps SINCE the last emitted frame, not on
    # step % n - the ingest paths run at arbitrary step counts
    last = dict(step=103, draw=time.time())
    check('steps: below threshold not due',
          not _due_sparse(('steps', 50), 137, last))
    check('steps: threshold reached due (odd step values)',
          _due_sparse(('steps', 50), 153, last))
    check('steps: non-divisible step still due',
          _due_sparse(('steps', 50), 999, last))
    check('steps: val<1 clamps to every step',
          _due_sparse(('steps', 0), last['step'] + 1, last))

    # seconds mode gates on wall time since the last emitted frame
    now = time.time()
    check('seconds: within interval not due',
          not _due_sparse(('seconds', 30.0), 5, dict(step=0, draw=now)))
    check('seconds: interval elapsed due',
          _due_sparse(('seconds', 0.2), 5, dict(step=0,
                                                draw=now - 1.0)))

    # ── B7: the t/end_time fallback must actually be armed ────────────
    class _Rec(RunHooks):
        def __init__(self):
            self.fracs = []

        def progress(self, p):
            self.fracs.append(p.frac)

        def log(self, msg):
            pass

    def _st():
        """Exactly what the three solve loops build (backend.py)."""
        return dict(step=0, t=0.0, dt=0.0, p_max=float(P_AIR),
                    frac=None, t_frame=-1.0)

    rec, st = _Rec(), _st()
    for t in ('1e-05', '2e-05', '3e-05'):
        _progress_line(f'Time = {t}', st, rec, end_time=1e-4)
    check('first solver step already reports progress (B7)',
          rec.fracs and rec.fracs[0] > 0.0,
          f'first frac = {rec.fracs[0] if rec.fracs else None}')
    check('fallback tracks t/end_time',
          rec.fracs == [0.1, 0.2, 0.3], str(rec.fracs))

    # once a written frame gives a real front fraction it takes over
    st['frac'] = 0.42
    _progress_line('Time = 4e-05', st, rec, end_time=1e-4)
    check('an ingested front fraction overrides the estimate',
          rec.fracs[-1] == 0.42, str(rec.fracs[-1]))

    # the estimate is clamped, never past 100%
    rec2, st2 = _Rec(), _st()
    _progress_line('Time = 5e-04', st2, rec2, end_time=1e-4)
    check('estimate clamps at 1.0', rec2.fracs == [1.0], str(rec2.fracs))

    # ── "Refresh every N steps" drives the live-sample cadence ─────────
    print("\nrefresh policy -> live-sample function object cadence")
    import shutil
    import tempfile
    from types import SimpleNamespace
    from blastlab.core.case import Case2D
    from blastlab.solvers.foam import runloop, runner, writer

    check('live_steps_for: steps N -> N, seconds/auto -> per-dim default',
          writer.live_steps_for(('steps', 20), 2) == 20
          and writer.live_steps_for(('steps', 0), 2) == 1
          and writer.live_steps_for(('seconds', 0.05), 2) == 5
          and writer.live_steps_for(('seconds', 1.0), 1) == 10
          and writer.live_steps_for(('seconds', 1.0), 3) == 1)

    case = Case2D(geometry='planar', Lx=2.0, Ly=2.0, cell_size_m=0.1,
                  charge=1.0, center=(1.0, 1.0), solver='blastfoam')
    cd0 = writer.render_case(case).files['system/controlDict']
    cd7 = writer.render_case(case, live_steps=7).files['system/controlDict']

    def fo_interval(text, name):
        m = re.search(rf'^    {name}\n    \{{\n(.*?)^    \}}', text,
                      flags=re.M | re.S)
        m2 = m and re.search(r'^        writeInterval\s+([^;]+);',
                             m.group(1), flags=re.M)
        return m2 and m2.group(1)

    top = re.search(r'^writeInterval\s+([^;]+);', cd0, flags=re.M).group(1)
    check('render_case: default live slice every 5 steps, live_steps=7 '
          'writes 7', fo_interval(cd0, 'liveSlice') == '5'
          and fo_interval(cd7, 'liveSlice') == '7',
          f"{fo_interval(cd0, 'liveSlice')} {fo_interval(cd7, 'liveSlice')}")
    check('... the run writeInterval and other FOs untouched',
          re.search(r'^writeInterval\s+([^;]+);', cd7, flags=re.M).group(1)
          == top and fo_interval(cd7, 'impulse') is None
          and cd7.replace('writeInterval   7;', 'writeInterval   5;') == cd0)

    new = runner.rewrite_entry_text(cd0, 'writeInterval', 12,
                                    within='liveSlice')
    check('rewrite_entry_text(within=liveSlice): only that block changes',
          fo_interval(new, 'liveSlice') == '12'
          and re.search(r'^writeInterval\s+([^;]+);', new,
                        flags=re.M).group(1) == top
          and new.count('writeInterval') == cd0.count('writeInterval'))
    check('... absent block: text unchanged',
          runner.rewrite_entry_text(cd0, 'writeInterval', 12,
                                    within='nope') == cd0)
    check('rewrite_entry_text top level still rewrites the run entry',
          re.search(r'^writeInterval\s+([^;]+);',
                    runner.rewrite_entry_text(cd0, 'writeInterval', 0.5),
                    flags=re.M).group(1) == '0.5'
          and fo_interval(runner.rewrite_entry_text(
              cd0, 'writeInterval', 0.5), 'liveSlice') == '5')

    # tail_live in steps mode: once the FO cadence equals N every
    # complete sample is shown (the stdout step gate would drop them:
    # "Time =" lines run ahead of the sample on disk)
    tmp = tempfile.mkdtemp(prefix='blastlab_tail_')
    for tdir in ('1e-06', '2e-06'):
        os.makedirs(os.path.join(tmp, 'postProcessing', 'liveSlice', tdir))
    spec = SimpleNamespace(case_unc=tmp, case_posix='/tmp/x', dim=2)
    got = []

    class _H(RunHooks):
        refresh = ('steps', 5)

        def frame(self, field, t, levels=None):
            got.append((field, t, levels))
    h = _H()
    st = dict(step=12, t_frame=-1.0)
    live = _new_live()
    live['step'] = 12                    # due_sparse says "not yet"
    live['fo_steps'] = 5
    runloop.tail_live(spec, h, st, live, 'liveSlice',
                      lambda tdir: ('F', tdir))
    check('steps mode + matching FO cadence: newest sample emitted',
          len(got) == 1 and got[0][0] == 'F' and got[0][1] == 2e-06
          and got[0][2] == '2e-06', str(got))
    check('... consumed dirs deleted',
          not os.path.isdir(os.path.join(tmp, 'postProcessing', 'liveSlice',
                                         '1e-06')))
    os.makedirs(os.path.join(tmp, 'postProcessing', 'liveSlice', '3e-06'))
    live['fo_steps'] = None              # rewrite failed: step gate again
    runloop.tail_live(spec, h, st, live, 'liveSlice',
                      lambda tdir: ('F', tdir))
    check('... without the FO cadence the step gate still holds',
          len(got) == 1)
    shutil.rmtree(tmp, ignore_errors=True)

    # _sync_live_steps: one rewrite per policy change, none for
    # seconds/auto, fall back to the step gate when the rewrite fails
    calls = []
    orig = runner.rewrite_control_entry

    def fake_rewrite(case_posix, case_unc, key, value, log=None,
                     within=None):
        calls.append((key, value, within))
        return fake_rewrite.ok
    fake_rewrite.ok = True
    runner.rewrite_control_entry = fake_rewrite
    try:
        logs = []
        hh = SimpleNamespace(refresh=('seconds', 0.05), log=logs.append)
        obj = SimpleNamespace(live_set='liveSlice', hooks=hh,
                              spec=SimpleNamespace(dim=2, case_posix='/c',
                                                   case_unc='C:\\c'),
                              live_steps=5, live=dict(fo_steps=5))
        runloop.FoamRunLoop._sync_live_steps(obj)
        check('seconds/auto policy: no rewrite', calls == [])
        hh.refresh = ('steps', 20)
        runloop.FoamRunLoop._sync_live_steps(obj)
        runloop.FoamRunLoop._sync_live_steps(obj)
        check('steps 20: one rewrite of liveSlice.writeInterval',
              calls == [('writeInterval', 20, 'liveSlice')]
              and obj.live_steps == 20 and obj.live['fo_steps'] == 20
              and any('every 20 solver step' in s for s in logs),
              f'{calls} {logs}')
        hh.refresh = ('seconds', 2.0)
        runloop.FoamRunLoop._sync_live_steps(obj)
        check('back to seconds: the per-dim default is restored',
              calls[-1] == ('writeInterval', 5, 'liveSlice')
              and obj.live['fo_steps'] == 5)
        fake_rewrite.ok = False
        hh.refresh = ('steps', 3)
        runloop.FoamRunLoop._sync_live_steps(obj)
        runloop.FoamRunLoop._sync_live_steps(obj)
        check('failed rewrite: no FO cadence (step gate), not retried',
              obj.live['fo_steps'] is None and len(calls) == 3)
        obj.live_set = None
        hh.refresh = ('steps', 9)
        runloop.FoamRunLoop._sync_live_steps(obj)
        check('no live set: nothing to sync', len(calls) == 3)
    finally:
        runner.rewrite_control_entry = orig

    print()
    if FAIL:
        print(f"FOAM LIVE DUE: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM LIVE DUE: PASS")


if __name__ == '__main__':
    main()
