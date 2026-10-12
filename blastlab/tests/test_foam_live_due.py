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


def w2_note_checks():
    """W2 (P1-2): a run that was stopped says its gauge tail may be short.

    Owner decision 2026-09-09: document it rather than chase a foam-side
    flush knob. The note must appear for every stop that goes through
    `stopAt writeNow` - the user's Stop, a terminate boundary, the trigger
    gauge - and must stay quiet when the solver reached its own endTime,
    where the function-object destructors do run and nothing is lost.
    """
    from blastlab.solvers.foam import backend

    print("")
    print("W2: a stopped run says the gauge tail may be short")

    class _Log:
        def __init__(self):
            self.lines = []

        def log(self, msg):
            self.lines.append(str(msg))

    def note_for(reason):
        rec = _Log()
        backend.note_gauge_tail(rec, reason)
        return ' '.join(rec.lines)

    for reason in ('safety cap', 'end time reached'):
        check(f'natural end ({reason}): silent', note_for(reason) == '')

    from blastlab.solvers.foam.runloop import STOP_UNSTABLE
    for reason in ('stopped by user',
                   'trigger gauge G2 reached',
                   'shock arrived at a terminate boundary (r = 4.0 m)',
                   STOP_UNSTABLE):
        txt = note_for(reason)
        check(f'{reason}: one note', txt.count('[note]') == 1, txt)
        check(f'{reason}: names the cause and the consequence',
              'gauge' in txt and 'graceful End' in txt and 'impulse' in txt,
              txt)

    check('the note does not claim peaks are wrong',
          'unaffected' in note_for('stopped by user'))
    # finalize_1d / _2d / _3d each call it; the `def` line must not count
    check('every finalizer calls it (1D, 2D, 3D)', _call_sites() == 3,
          f'{_call_sites()} call sites')


def _call_sites():
    from blastlab.solvers.foam import backend
    with open(backend.__file__, encoding='utf-8') as fh:
        return sum(1 for ln in fh
                   if ln.strip() == 'note_gauge_tail(hooks, stop_reason)')


def instability_checks(_st):
    """A run whose deltaT collapses must be stopped and named, not left
    to spin until blastFoam divides rhoU by a zero density.

    Calibrated against a real crash (profile+AMR 3D, 13 ranks): deltaT
    fell 6.4e-06 -> 1e-08 -> 7.5e-12 across ~43 steps with the solver
    clock frozen, then SIGFPE in compressibleBlastSystem::decode().
    """
    from blastlab.solvers.foam import runloop, backend

    print("")
    print("A8: a collapsing deltaT is caught before the SIGFPE")

    class _Log:
        def __init__(self):
            self.lines = []

        def log(self, msg):
            self.lines.append(str(msg))

        def progress(self, p):
            pass

    def feed(rec, st, pairs):
        """One solver step is a deltaT line then a Time line, in the
        order blastFoam prints them."""
        for dt, t in pairs:
            runloop.progress_line(f'deltaT = {dt:.6e}', st, rec, 1e-3)
            runloop.progress_line(f'Time = {t:.9e}', st, rec, 1e-3)

    def ramp(n=60, cap=6.4e-6, dt=1e-7, t=0.0):
        out = []
        for _ in range(n):
            dt = min(cap, dt * 1.2)
            t += dt
            out.append((dt, t))
        return out, t

    # a healthy start: deltaT is tiny AND growing, which is the normal
    # opening of every blastFoam run - it must never look unstable
    rec, st = _Log(), _st()
    grow, _ = ramp(200, cap=1e30)
    feed(rec, st, grow)
    check('a growing deltaT never trips the guard',
          not st.get('unstable') and not rec.lines, str(rec.lines[:1]))

    # adjustTimeStep off: a small FIXED deltaT prints a clock that looks
    # stalled at OpenFOAM's 6-significant-digit precision. Without the
    # deltaT conjunct this is a false positive.
    rec, st = _Log(), _st()
    feed(rec, st, [(1e-7, 100.0)] * 200)
    check('a fixed small deltaT with a print-stalled clock is not '
          'instability', not st.get('unstable'), str(rec.lines[:1]))

    # the measured collapse
    rec, st = _Log(), _st()
    pairs, t = ramp()
    feed(rec, st, pairs + [(7.5e-12, t)] * 20)
    check('the measured collapse is caught',
          st.get('unstable') == runloop.STOP_UNSTABLE, str(st.get('unstable')))
    check('it says so exactly once', len(rec.lines) == 1, str(len(rec.lines)))
    txt = rec.lines[0] if rec.lines else ''
    check('the message names deltaT, the value and the consequence',
          'deltaT' in txt and '7.50e-12' in txt and 'unstable' in txt
          and 'SIGFPE' in txt, txt[:120])
    feed(rec, st, [(7.5e-12, t)] * 100)
    check('latched: still one line however long it lasts',
          len(rec.lines) == 1, str(len(rec.lines)))

    # a dip that recovers is not a collapse
    rec, st = _Log(), _st()
    pairs, t = ramp()
    dip = [(7.5e-12, t)] * 10
    back = []
    for _ in range(5):
        t += 6.4e-6
        back.append((6.4e-6, t))
    feed(rec, st, pairs + dip + back + [(7.5e-12, t)] * 10)
    check('a transient dip that recovers resets the streak',
          not st.get('unstable'), str(rec.lines[:1]))

    # never before the run has really started
    rec, st = _Log(), _st()
    feed(rec, st, [(1e-6, 1e-6), (1e-12, 1e-6)]
         + [(1e-12, 1e-6)] * (runloop.MIN_STABLE_STEPS - 3))
    check('never fires before MIN_STABLE_STEPS',
          not st.get('unstable'), str(rec.lines[:1]))

    # the A6 canary feeds Courant lines as filler: the guard must not see
    # them, which is why it keys off deltaT and Time only
    rec, st = _Log(), _st()
    for k in range(runloop.TIME_CANARY_LINES - 1):
        runloop.progress_line(f'Courant Number mean: {k}', st, rec, 1e-4)
    check('Courant filler lines are invisible to the guard',
          not st.get('unstable') and st.get('dt_low', 0) == 0)

    # the reason-string contract
    check('the reason is not the user-stop string',
          runloop.STOP_UNSTABLE != 'stopped by user')
    check('an instability stop counts as stopped early',
          backend._stopped_early(runloop.STOP_UNSTABLE)
          and backend._stopped_early('stopped by user'))
    check('a run that achieved what it was asked does not',
          not backend._stopped_early('end time reached')
          and not backend._stopped_early('safety cap')
          and not backend._stopped_early('trigger gauge G1 reached'))

    # wiring: the loop asks for the stop, and the user's stop still wins
    with open(runloop.__file__, encoding='utf-8') as fh:
        src = fh.readlines()
    mine = [i for i, ln in enumerate(src)
            if ln.strip() == 'self.request_stop(STOP_UNSTABLE)']
    user = [i for i, ln in enumerate(src)
            if ln.strip() == "self.request_stop('stopped by user')"]
    check('the run loop requests the stop exactly once',
          len(mine) == 1, f'{len(mine)} call sites')
    check("the user's stop is checked first, so it keeps its own reason",
          bool(mine) and bool(user) and user[0] < mine[0])


def canary_checks(_st):
    """A6/A7: the two silent-degradation paths must say something once.

    `_RE_TIME` drives step counting, the progress bar and the live-frame
    cadence, and the live-slice face-count gate can refuse every sample
    forever - both used to fail in complete silence.
    """
    from blastlab.solvers.foam import runloop, backend, writer

    print("")
    print("A6: a solver that never prints 'Time =' is reported once")

    class _Log(RunHooks):
        def __init__(self):
            self.lines = []

        def log(self, msg):
            self.lines.append(str(msg))

        def progress(self, p):
            pass

    rec, st = _Log(), _st()
    for k in range(runloop.TIME_CANARY_LINES - 1):
        runloop.progress_line(f'Courant Number mean: {k}', st, rec, 1e-4)
    check('quiet until the threshold', not rec.lines, str(rec.lines))
    for k in range(3):
        runloop.progress_line('smoothSolver: solving for p', st, rec, 1e-4)
    warn = [ln for ln in rec.lines if 'Time =' in ln]
    check('one warning after the threshold', len(warn) == 1, str(rec.lines))
    check('the warning says what breaks',
          'live cadence and progress' in warn[0], warn[0] if warn else '')

    rec2, st2 = _Log(), _st()
    for k in range(runloop.TIME_CANARY_LINES + 50):
        runloop.progress_line('Time = 1e-05' if k == 3 else f'line {k}',
                              st2, rec2, 1e-4)
    check('a solver that IS stepping never triggers it',
          not any('Time =' in ln for ln in rec2.lines), str(rec2.lines))

    print("")
    print("A7: a live slice that can never decode is reported once")
    spec = writer.CaseSpec(dim=2, material='TNT', nx=4, ny=4, dx=0.1)
    spec.hooks = _Log()
    for _ in range(backend.SURFACE_CANARY_TRIES - 1):
        backend._surface_refused(spec, 15, 16)
    check('quiet while it still looks like a mid-write race',
          not spec.hooks.lines, str(spec.hooks.lines))
    backend._surface_refused(spec, 15, 16)
    check('one line once the refusals are persistent',
          len(spec.hooks.lines) == 1, str(spec.hooks.lines))
    check('the line gives both counts',
          '15 faces' in spec.hooks.lines[0]
          and 'expected 16' in spec.hooks.lines[0], spec.hooks.lines[0])
    for _ in range(3 * backend.SURFACE_CANARY_TRIES):
        backend._surface_refused(spec, 15, 16)
    check('and only one line, however long it lasts',
          len(spec.hooks.lines) == 1, str(len(spec.hooks.lines)))

    spec2 = writer.CaseSpec(dim=2, material='TNT', nx=4, ny=4, dx=0.1)
    spec2.hooks = _Log()
    for _ in range(3 * backend.SURFACE_CANARY_TRIES):
        backend._surface_refused(spec2, 15, 16)
        backend._surface_ok(spec2, 'decoded')   # a good sample every other poll
    check('a sample that decodes clears the streak',
          not spec2.hooks.lines, str(spec2.hooks.lines))


def handoff_energy_checks():
    """N5-5: blastFoam's own volume integral of rhoE at the first
    execute, against the energy the writer put on the mesh.

    The one check in the codebase that sees ACROSS the file boundary.
    Python knows what it meant to write; the FO says what blastFoam
    decoded after the EOS inversion (guide 5.9) and the lambda blend
    (5.87). B0 and B1 both broke in that gap and neither was visible
    from either side on its own.

    The log wording below is verbatim from blastFoam 6.2.0.
    """
    from blastlab.solvers.foam.runloop import progress_line, HANDOFF_E_TOL
    print()
    print('N5-5: the hand-off energy check')

    class _H:
        def __init__(self):
            self.msgs = []

        def log(self, m):
            self.msgs.append(str(m))

        def progress(self, *a):
            pass

    def feed(lines, E_expect):
        st = dict(step=0, t=0.0, dt=0.0, p_max=101325.0, frac=None,
                  t_frame=-1.0, cons0=None, cons=None, cons_field=None,
                  cons_noted=False, E_expect=E_expect)
        h = _H()
        for ln in lines:
            progress_line(ln, st, h, 1.0)
        return st, h

    BLOCK = ['rho [1 -3 0 0 0 0 0] :',
             '    Original = 0.000124828',
             '    Current = 0.000124828',
             '    difference (abs/rel) = 0, 0',
             'rhoE [1 -1 -2 0 0 0 0] :',
             '    Original = {v!r}',
             '    Current = {v!r}',
             '    difference (abs/rel) = 0, 0']

    def block(v):
        return [ln.format(v=v) for ln in BLOCK]

    # the real calibration pair: 2.856593e4 J written, 28560.1 read
    st, h = feed(block(28560.1), 2.856593e4)
    check('parses the FO block as blastFoam prints it',
          st['cons0'] == {'rho': 0.000124828, 'rhoE': 28560.1},
          str(st['cons0']))
    check('the measured pair is inside tolerance',
          abs(st['cons_rel']) < HANDOFF_E_TOL,
          f"{st['cons_rel']:+.5f}")
    check('and it says so without crying wolf',
          len(h.msgs) == 1 and h.msgs[0].startswith('  [note]'),
          str(h.msgs))

    # B1's signature: products mispriced by 33 %, which is 5.6 % of the
    # domain total on the fixture it was measured on
    st, h = feed(block(2.856593e4 * 1.056), 2.856593e4)
    check('a B1-sized mismatch warns',
          any(m.startswith('  [warn]') for m in h.msgs), str(h.msgs))
    check('and the warning carries both numbers and the ratio',
          h.msgs and '2.8566e+04' in h.msgs[0] and '+5.6%' in h.msgs[0],
          str(h.msgs))

    # B0's signature: the fireball reset to pRef
    _st, h = feed(block(2.856593e4 * 0.55), 2.856593e4)
    check('a B0-sized mismatch warns',
          any(m.startswith('  [warn]') for m in h.msgs), str(h.msgs))

    # a charge case has no hand-off to check - and rhoE there is not
    # conserved anyway (E0 arrives as lambda goes 0 -> 1: measured
    # +1169 % before the open boundary drains it), so it must be silent
    st, h = feed(block(28560.1), None)
    check('a charge case says nothing', not h.msgs, str(h.msgs))
    check('but still parses the block', st['cons0'] is not None)

    # latched: only the FIRST reading is judged
    st, h = feed(block(28560.1) + block(28560.1 * 12.7), 2.856593e4)
    check('only the first reading is judged',
          len(h.msgs) == 1 and st['cons0']['rhoE'] == 28560.1
          and st['cons']['rhoE'] != 28560.1,
          f"{len(h.msgs)} msg(s), cons0={st['cons0']['rhoE']}, "
          f"cons={st['cons']['rhoE']}")

    # the block must not disturb the lines the rest of the loop needs
    st, h = feed(block(28560.1) + ['deltaT = 1.19781e-07',
                                   'Time = 1.1978134e-07'], 2.856593e4)
    check('deltaT and Time still parse around it',
          st['dt'] == 1.19781e-07 and st['step'] == 1,
          f"dt={st['dt']} step={st['step']}")


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
        cad = []
        hh = SimpleNamespace(refresh=('seconds', 0.05), log=logs.append,
                             cadence=lambda dt=None, steps=None:
                             cad.append((dt, steps)))
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
        # G7: the live-view title follows the cadence it was given
        check('the new cadence is reported to the live view',
              cad == [(None, 20)], str(cad))
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

    canary_checks(_st)
    instability_checks(_st)
    w2_note_checks()
    handoff_energy_checks()

    print()
    if FAIL:
        print(f"FOAM LIVE DUE: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM LIVE DUE: PASS")


if __name__ == '__main__':
    main()
