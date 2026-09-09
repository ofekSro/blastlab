"""P1-5: resuming a run whose newest write is internally inconsistent.

Stopping a profile-initialised AMR stage and resuming it (T70) killed the
solver before its first step:

    --> FOAM FATAL IO ERROR:  size 5138 is not equal to the given value
    of 5189
    file: .../<t_last>/pMax

`pMax` and `impulse` are accumulating function objects: a restart READS
them and carries on from where they were, which is what keeps the
peak/impulse maps continuous across a resume (N6/T43). They write at
`writeTime` like everything else, but on a dynamic-AMR run one that
missed a mesh update lands at the PREVIOUS cell count - and then that
whole time directory is unusable as a restart point, because the very
first read aborts.

`resume_run` therefore no longer says `startFrom latestTime` blindly. It
asks each write, newest first, whether every field in it matches that
write's own mesh (its `C`, written per time dir on an AMR run), and
restarts from the newest one that is whole - re-solving an interval the
run was going to re-solve anyway. Deleting the offending fields instead
would have been worse than the crash: the accumulators would silently
restart from zero, and the run would report a peak map that had lost
everything before the stop.

No WSL: the time dirs are faked on the local disk, exactly as
test_foam_amr_ingest and test_foam_postmortem_decomposed do.

Run:  cd blastlab/tests && python test_foam_resume.py
"""
import os
import shutil
import sys
import tempfile

import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core.case import Case2D                            # noqa: E402
from blastlab.core.constants import P_AIR                        # noqa: E402
from blastlab.solvers.foam import backend, reader, writer        # noqa: E402
from test_foam_amr_ingest import (block_centres, field_text,     # noqa: E402
                                  write_time)

FAILS = []
TIMES = ('1e-05', '2e-05', '3e-05')


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


class Log:
    def __init__(self):
        self.lines = []

    def log(self, msg):
        self.lines.append(str(msg))

    def __getattr__(self, _name):        # every other hook is a no-op
        return lambda *a, **k: None


def build(root, n_procs=1):
    """Three written times of a 1 x 1 m AMR run, plus the spec that
    addresses them (decomposed when n_procs > 1, like a real one)."""
    case = Case2D(geometry='planar', Lx=1.0, Ly=1.0, cell_size_m=0.5,
                  charge=100.0, center=(0.5, 0.5), solver='blastfoam',
                  amr_levels=2, n_snapshots=2, n_procs=n_procs)
    C0 = block_centres(0, 0, 0.5, 2)
    C1 = np.vstack([C0[:3], block_centres(0.5, 0.5, 0.25, 2)])
    C2 = np.vstack([C1[:6], block_centres(0.75, 0.75, 0.125, 2)])
    lv1 = [0, 0, 0, 1, 1, 1, 1]
    lv2 = [0, 0, 0, 1, 1, 1, 2, 2, 2, 2]

    for name, t, C, lv in (('1e-05', 1e-5, C1, lv1),
                           ('2e-05', 2e-5, C2, lv2),
                           ('3e-05', 3e-5, C2, lv2)):
        p = P_AIR + 1000.0 * np.arange(len(C))
        if n_procs == 1:
            write_time(root, name, t, C, lv, p)
            continue
        cut = 3
        for i, sl in enumerate((slice(0, cut), slice(cut, len(C)))):
            pu = os.path.join(root, f'processor{i}')
            os.makedirs(pu, exist_ok=True)
            write_time(pu, name, t, C[sl], list(lv)[sl], p[sl])

    spec = writer.render_case(case, n_procs=n_procs)
    spec.case_unc = spec.case_posix = root
    return spec


def shorten(root, name, field='pMax', drop=2, part=None):
    """Rewrite one field with fewer values than its mesh has cells -
    what an FO that missed a mesh update leaves behind."""
    d = os.path.join(root, part, name) if part else os.path.join(root, name)
    n = len(reader.read_vector(os.path.join(d, 'C'), None))
    vals = P_AIR + np.arange(n - drop, dtype=float)
    with open(os.path.join(d, field), 'w') as fh:
        fh.write(field_text('volScalarField', field, vals))
    return n, n - drop


def main():
    print("\nP1-5: a resume must not start from a torn write")

    # ---- the size probe itself -------------------------------------
    root = tempfile.mkdtemp(prefix='blastlab_resume_')
    try:
        spec = build(root)
        d = os.path.join(root, '3e-05')
        n_mesh = len(reader.read_vector(os.path.join(d, 'C'), None))
        check('scalar_size reads a nonuniform field without being told',
              reader.scalar_size(os.path.join(d, 'p')) == n_mesh,
              f'{reader.scalar_size(os.path.join(d, "p"))} vs {n_mesh}')
        check('scalar_size says None for a uniform field (fits any mesh)',
              reader.scalar_size(os.path.join(d, 'rho')) is None)

        # ---- every write whole: latestTime is right ------------------
        for name in TIMES:
            ok, detail = backend._time_is_whole(spec, name)
            check(f'{name} is whole', ok, detail)
        start, skipped = backend._resume_start_time(spec, list(TIMES), Log())
        check('nothing skipped when every write is whole',
              (start, skipped) == ('3e-05', []), f'{start} {skipped}')

        # ---- the newest write torn: walk back one -------------------
        n_mesh, n_fo = shorten(root, '3e-05')
        ok, detail = backend._time_is_whole(spec, '3e-05')
        check('a short pMax makes its write unusable', not ok, detail)
        check('...and the message gives both counts',
              str(n_fo) in detail and str(n_mesh) in detail, detail)
        log = Log()
        start, skipped = backend._resume_start_time(spec, list(TIMES), log)
        check('the resume walks back to the newest whole write',
              start == '2e-05', start)
        check('...and reports exactly what it skipped',
              [n for n, _d in skipped] == ['3e-05'], str(skipped))
        check('...out loud, once',
              sum('cannot restart from t = 3e-05' in ln
                  for ln in log.lines) == 1, str(log.lines))

        # ---- impulse is checked too, and walk-back can be > 1 --------
        shorten(root, '2e-05', field='impulse', drop=1)
        start, skipped = backend._resume_start_time(spec, list(TIMES), Log())
        check('a short impulse is caught as well as a short pMax',
              start == '1e-05', start)
        check('both newer writes reported as skipped',
              [n for n, _d in skipped] == ['3e-05', '2e-05'], str(skipped))

        # ---- nothing whole: refuse with a reason, do not run --------
        shorten(root, '1e-05', drop=3)
        try:
            backend._resume_start_time(spec, list(TIMES), Log())
            ok, detail = False, 'returned a start time anyway'
        except RuntimeError as exc:
            ok, detail = 'internally inconsistent' in str(exc), str(exc)
        check('no whole write at all -> a refusal that says why', ok, detail)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ---- the same, decomposed (a parallel AMR run, T42) -------------
    print("\nP1-5: the check follows a decomposed run into processor*/")
    root = tempfile.mkdtemp(prefix='blastlab_resume_np_')
    try:
        spec = build(root, n_procs=2)
        check('the spec addresses the ranks, not the case root',
              isinstance(spec.time_dirs('3e-05'), list)
              and len(spec.time_dirs('3e-05')) == 2)
        start, skipped = backend._resume_start_time(spec, list(TIMES), Log())
        check('all ranks whole -> latest time', start == '3e-05', start)
        shorten(root, '3e-05', part='processor1')
        start, skipped = backend._resume_start_time(spec, list(TIMES), Log())
        check('one torn RANK is enough to reject the write',
              start == '2e-05', start)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ---- the actual P1-5 fix: no accumulating FOs on a resumed AMR run
    print("\nP1-5: a resumed AMR run runs without the accumulating FOs")
    root = tempfile.mkdtemp(prefix='blastlab_resume_fo_')
    try:
        spec = build(root)
        os.makedirs(os.path.join(root, 'system'), exist_ok=True)
        case = Case2D(geometry='planar', Lx=1.0, Ly=1.0, cell_size_m=0.5,
                      charge=100.0, center=(0.5, 0.5), solver='blastfoam',
                      amr_levels=2, n_snapshots=2)
        before = writer._controldict(spec, case)
        check('a fresh AMR run DOES carry pMax and impulse',
              'pMax' in before and 'impulse' in before)

        log = Log()
        did = backend._disable_fo_accumulators(spec, case, log)
        after = open(os.path.join(root, 'system', 'controlDict'),
                     encoding='ascii').read()
        check('the resume turns them off', did and not spec.fo_accumulators)
        check('...by rewriting the controlDict without them',
              'pMax' not in after and 'impulse' not in after,
              [ln for ln in after.splitlines() if 'Max' in ln])
        check('...and keeps everything else about the run',
              'startFrom' in after and 'writeInterval' in after
              and 'liveSlice' in after or 'functions' in after)
        check('...saying why, and what it costs',
              any('per write' in ln and 'mesh change' in ln
                  for ln in log.lines), str(log.lines))
        check('the written FO fields are left alone for the replay',
              os.path.isfile(os.path.join(root, '3e-05', 'pMax')))

        # a fixed-mesh run restarts its FOs correctly - do not touch it
        spec2 = build(tempfile.mkdtemp(prefix='blastlab_resume_static_'))
        spec2.amr = None
        log2 = Log()
        check('a run without AMR keeps its function objects',
              not backend._disable_fo_accumulators(spec2, case, log2)
              and spec2.fo_accumulators and not log2.lines)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ---- a run with no FO fields at all is not held back ------------
    print("\nP1-5: a run without the function objects still resumes")
    root = tempfile.mkdtemp(prefix='blastlab_resume_nofo_')
    try:
        spec = build(root)
        for name in TIMES:
            for f in ('pMax', 'impulse'):
                os.remove(os.path.join(root, name, f))
        start, skipped = backend._resume_start_time(spec, list(TIMES), Log())
        check('no pMax/impulse -> nothing to be inconsistent with',
              (start, skipped) == ('3e-05', []), f'{start} {skipped}')
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if FAILS:
        print(f"FOAM RESUME: FAIL ({len(FAILS)}): {', '.join(FAILS)}")
        return 1
    print("FOAM RESUME: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
