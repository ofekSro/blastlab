"""Characterisation: a run stage whose output write fails (UX 2).

docs/UX_REVIEW.md section 3, finding 2. `solvers/jobs.solve_stage`
writes the case's own output files (gauge TSV, animation, remap profile,
trigger remap) after the solve, and both GUIs run it through
`solvers/worker.SolverWorker`. This suite makes ONE of those writes fail
at a time - the writer name in `solvers.jobs` is patched to raise
PermissionError for that one path, as a file locked by a video player or
by OneDrive would - on a small real native solve, runs the worker on this
thread, and pins:

  * the worker's queue, reduced to the messages the GUIs act on:
    ('stage', k), ('result', k), ('error', first line, last line),
    ('done',), plus every run-log line that starts with '[warn] could
    not write';
  * which of the case's output files exist afterwards;
  * `worker.results` / `worker.error_stage`.

Scenarios: the gauge TSV, the animation and the profile of a 2D run; the
gauge TSV and the profile of a 1D run; the profile of stage 1 of a 1D -> 2D
chain, with no file at the hand-off path and with a STALE one there from
an earlier chain (the next stage must never start from it); the 2D
trigger-remap file; and a control where nothing fails.

The expectations are the behaviour of the code as it stands; a change to
them is a change in what the user sees and must be deliberate.

Run:  cd blastlab/tests && python test_char_write_failure.py
      (also collected by pytest)
"""
import contextlib
import os
import shutil
import sys
import tempfile

import char_common  # noqa: F401  (private settings, auto_cleanup off)

from blastlab.models.case import Case1D, Case2D     # noqa: E402
from blastlab.solvers import jobs                    # noqa: E402
from blastlab.solvers.worker import SolverWorker     # noqa: E402

WARN = '[warn] could not write'

#: the writers `solve_stage` calls, by the name it looks them up under
WRITERS = ('save_gauges_1d', 'save_gauges_2d', 'save_gauges_3d',
           'write_animation', 'save_profile', 'save_profile_2d')


def case1d(tmp, **kw):
    """A 1 m sphere, 1 cm cells: a few hundred steps."""
    kw.setdefault('gauge_file', os.path.join(tmp, 'g1.txt'))
    return Case1D(radius_m=1.0, charge_kg=0.5, cell_size_m=0.01,
                  n_snapshots=1, t_end=3e-4, gauge_radii=[0.5], **kw)


def case2d(tmp, **kw):
    """The 0.6 x 1.2 m axisymmetric case of test_bc_trigger, 3 cm cells."""
    kw.setdefault('bcs', dict(x_lo='reflect', x_hi='transmit',
                              y_lo='reflect', y_hi='transmit'))
    kw.setdefault('gauge_file', os.path.join(tmp, 'g2.txt'))
    kw.setdefault('t_end', 2e-4)
    kw.setdefault('record_frames', 3)
    return Case2D(Lx=0.6, Ly=1.2, cell_size_m=0.03, charge=0.5,
                  center=(0.0, 0.6), n_snapshots=1,
                  gauges=[(0.25, 0.6), (0.5, 0.6)], **kw)


def _norm(text, tmp):
    """Messages with the temp directory replaced, in both the plain and
    the repr (doubled backslash) spelling."""
    text = str(text)
    for spelled in (tmp.replace('\\', '\\\\'), tmp):
        text = text.replace(spelled, '<tmp>')
    return text.replace('\\\\', '/').replace('\\', '/')


@contextlib.contextmanager
def failing_writes(fail_path):
    """Every writer `solve_stage` uses raises PermissionError for
    `fail_path` (None: nothing fails) while the block runs. Shared with
    the two GUI scripts (test_ui_/test_gui_char_write_failure.py)."""
    real = {name: getattr(jobs, name) for name in WRITERS}

    def failing(name):
        def write(obj, path, *a, **kw):
            if fail_path is not None and os.path.abspath(str(path)) \
                    == os.path.abspath(fail_path):
                raise PermissionError(13, 'Permission denied', str(path))
            return real[name](obj, path, *a, **kw)
        return write

    for name in WRITERS:
        setattr(jobs, name, failing(name))
    try:
        yield
    finally:
        for name, fn in real.items():
            setattr(jobs, name, fn)


def run_stages(dim_cases, fail_path, tmp):
    """Run solve_stage for each (dim, case) on a SolverWorker, on this
    thread, with every writer raising PermissionError for `fail_path`
    (None: nothing fails). Returns the reduced record."""
    with failing_writes(fail_path):
        w = SolverWorker([jobs.solve_stage(d, c) for d, c in dim_cases])
        w.run()                        # on this thread: deterministic

    events, warns = [], []
    while not w.q.empty():
        msg = w.q.get_nowait()
        tag = msg[0]
        if tag in ('stage', 'result'):
            events.append([tag, msg[1]])
        elif tag == 'error':
            lines = [ln for ln in str(msg[1]).splitlines() if ln.strip()]
            events.append(['error', _norm(lines[0], tmp),
                           _norm(lines[-1], tmp)])
        elif tag == 'done':
            events.append(['done'])
        elif tag == 'log' and str(msg[1]).lstrip().startswith(WARN):
            warns.append(_norm(msg[1], tmp))
    return dict(events=events, warns=warns,
                files=sorted(os.listdir(tmp)),
                results=[r is not None for r in w.results],
                error_stage=w.error_stage)


def scenario(name):
    """Build and run one scenario in a fresh temp directory."""
    tmp = tempfile.mkdtemp(prefix='blastlab_char_wfail_')
    try:
        p = lambda f: os.path.join(tmp, f)        # noqa: E731
        if name in ('2d_ok', '2d_gauges', '2d_anim', '2d_profile'):
            target = {'2d_ok': None, '2d_gauges': 'g2.txt',
                      '2d_anim': 'a.gif', '2d_profile': 'p2.npz'}[name]
            return run_stages([(2, case2d(tmp, anim_file=p('a.gif'),
                                          profile_file=p('p2.npz')))],
                              None if target is None else p(target), tmp)
        if name in ('1d_gauges', '1d_profile'):
            target = {'1d_gauges': 'g1.txt', '1d_profile': 'p1.txt'}[name]
            return run_stages([(1, case1d(tmp, profile_file=p('p1.txt')))],
                              p(target), tmp)
        if name in ('chain_ok', 'chain_profile', 'chain_profile_stale'):
            if name == 'chain_profile_stale':
                # an earlier chain's hand-off, left in the workspace
                with open(p('p1.txt'), 'w') as f:
                    f.write('stale\n')
            c1 = case1d(tmp, profile_file=p('p1.txt'))
            c2 = case2d(tmp, init_mode='profile1d',
                        profile_file_in=p('p1.txt'))
            return run_stages([(1, c1), (2, c2)],
                              None if name == 'chain_ok' else p('p1.txt'),
                              tmp)
        if name == '2d_trigger':
            c = case2d(tmp, trigger_gauge=1, trigger_action='remap',
                       trigger_file=p('trig.npz'), t_end=5e-3,
                       record_frames=0)
            return run_stages([(2, c)], p('trig.npz'), tmp)
        raise KeyError(name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_PERM = "PermissionError: [Errno 13] Permission denied: '<tmp>/{}'"
_WARN = "[warn] could not write <tmp>/{0}: [Errno 13] Permission " \
        "denied: '<tmp>/{0}'"
#: the 'error' a failed hand-off write posts: first line, last line
_HANDOFF = ["Could not write the hand-off file <tmp>/{0}: [Errno 13] "
            "Permission denied: '<tmp>/{0}'",
            'The result of this stage is kept in Results. The run stopped '
            'here, so no later stage starts from a stale or missing '
            'profile.']


def _handoff(f):
    return ['error'] + [line.format(f) for line in _HANDOFF]


#: Since UX 2. Before it, every failure below posted ('error', traceback
#: ending in the PermissionError) and never 'result', and the writes
#: after the failing one never happened (commit "ux(2): characterise ...").
#: Now: every write is attempted and a failure is logged as '[warn] could
#: not write'; a gauge TSV or animation failure still posts the result
#: and nothing else; a profile / trigger-remap (hand-off) failure posts
#: the result, THEN an error, and stops the chain before the next stage -
#: also when a stale hand-off file sits at the path.
EXPECTED = {
    '2d_ok': dict(
        events=[['stage', 0], ['result', 0], ['done']], warns=[],
        files=['a.gif', 'g2.txt', 'p2.npz'], results=[True],
        error_stage=None),
    '2d_gauges': dict(
        events=[['stage', 0], ['result', 0], ['done']],
        warns=[_WARN.format('g2.txt')],
        files=['a.gif', 'p2.npz'], results=[True], error_stage=None),
    '2d_anim': dict(
        events=[['stage', 0], ['result', 0], ['done']],
        warns=[_WARN.format('a.gif')],
        files=['g2.txt', 'p2.npz'], results=[True], error_stage=None),
    '2d_profile': dict(
        events=[['stage', 0], ['result', 0], _handoff('p2.npz'), ['done']],
        warns=[_WARN.format('p2.npz')],
        files=['a.gif', 'g2.txt'], results=[True], error_stage=0),
    '1d_gauges': dict(
        events=[['stage', 0], ['result', 0], ['done']],
        warns=[_WARN.format('g1.txt')],
        files=['p1.txt'], results=[True], error_stage=None),
    '1d_profile': dict(
        events=[['stage', 0], ['result', 0], _handoff('p1.txt'), ['done']],
        warns=[_WARN.format('p1.txt')],
        files=['g1.txt'], results=[True], error_stage=0),
    'chain_ok': dict(
        events=[['stage', 0], ['result', 0], ['stage', 1], ['result', 1],
                ['done']], warns=[],
        files=['g1.txt', 'g2.txt', 'p1.txt'], results=[True, True],
        error_stage=None),
    'chain_profile': dict(
        events=[['stage', 0], ['result', 0], _handoff('p1.txt'), ['done']],
        warns=[_WARN.format('p1.txt')],
        files=['g1.txt'], results=[True, False], error_stage=0),
    'chain_profile_stale': dict(
        events=[['stage', 0], ['result', 0], _handoff('p1.txt'), ['done']],
        warns=[_WARN.format('p1.txt')],
        files=['g1.txt', 'p1.txt'], results=[True, False], error_stage=0),
    '2d_trigger': dict(
        events=[['stage', 0], ['result', 0], _handoff('trig.npz'),
                ['done']],
        warns=[_WARN.format('trig.npz')],
        files=['g2.txt'], results=[True], error_stage=0),
}


def gui_log_line(line):
    """The run-log lines the two GUI scripts pin."""
    return (WARN in line or line.startswith('PermissionError')
            or 'hand-off' in line or 'no later stage' in line
            or line.strip() == '[run finished]')


#: What BOTH GUIs show (test_ui_/test_gui_char_write_failure.py) since
#: UX 2. Before it: no result, a "Run failed" dialog with the
#: PermissionError, the traceback in the run log. Now a failed animation
#: is a warning in the run log and the result is in Results, with no
#: dialog; a failed chain hand-off puts stage 1's result in Results, then
#: "Run failed" names the file, and stage 2 never starts.
EXPECTED_GUI = {
    '2d_anim': dict(
        results=['Run 1 - 2D'],
        dialogs=[],
        log=[_WARN.format('a.gif'), '[run finished]'],
        running=False, stop_enabled=False, run_back_to_idle=True),
    'chain_profile': dict(
        results=['Run 2 - 1D'],
        dialogs=[['Run failed', _HANDOFF[0].format('p1.txt')
                  + '\n\nSee the run log for details.']],
        log=[_WARN.format('p1.txt'), _HANDOFF[0].format('p1.txt'),
             _HANDOFF[1], '[run finished]'],
        running=False, stop_enabled=False, run_back_to_idle=True),
}


def _check(name):
    got = scenario(name)
    assert got == EXPECTED[name], f'{name}:\n got      {got}\n expected ' \
                                  f'{EXPECTED[name]}'


def test_2d_ok():
    _check('2d_ok')


def test_2d_gauges():
    _check('2d_gauges')


def test_2d_anim():
    _check('2d_anim')


def test_2d_profile():
    _check('2d_profile')


def test_1d_gauges():
    _check('1d_gauges')


def test_1d_profile():
    _check('1d_profile')


def test_chain_ok():
    _check('chain_ok')


def test_chain_profile():
    _check('chain_profile')


def test_chain_profile_stale():
    _check('chain_profile_stale')


def test_2d_trigger():
    _check('2d_trigger')


def main():
    fails = []
    for name in EXPECTED:
        got = scenario(name)
        ok = got == EXPECTED[name]
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            print(f'      got      {got}\n      expected {EXPECTED[name]}')
            fails.append(name)
    print()
    print('WRITE FAILURE: ' + ('PASS' if not fails
                               else f'FAIL ({len(fails)}): '
                               + ', '.join(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
