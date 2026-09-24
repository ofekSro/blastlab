"""HD1-15: the per-case write budget for blastFoam runs (no WSL, no GUI).

`write_budget = N` on a 2D/3D blastFoam case with an explicit end time
pins writeInterval to t_end / N and turns the adaptive controller off
(B1); the run loop then keeps the decomposed copy of the latest write
only (B2). Default 0: nothing changes. Pinned here:

  B1  * a default case serialises without the key, and the HD1-3d
        evidence case.json still equals the script's CFD case key for key;
      * t_end = 0.03 s with N = 60 renders the top-level writeInterval
        0.0005, the end-time write once, a pinned spec whose adaptive
        controller makes zero controlDict rewrites, and the banner's
        own label; save_case / load_case keep N;
      * the solvers' adaptive expression honours the budget.
  B2  * the purge planner never lists the newest complete common time,
        the start dir, a time not ingested or not reconstructed, or one
        newer than the newest complete time (a torn write), and lists
        nothing without a budget, in serial or on a decomposed AMR run;
      * the deleter builds <case>/processor<N>/<time> and nothing else;
      * a fake 2-rank run - 0 plus four times, three reconstructed and
        ingested, the fourth partial on rank 1 - keeps {constant, 0, t3,
        t4} per rank and an untouched root; _n_procs_on_disk still says 2,
        _resume_start_time still picks the latest root time, and a second
        purge is a no-op;
      * through a whole fake ingest a spy deleter is called zero times
        without a budget and exactly for the older times with one; a
        failing delete is logged once, retried, and never raises; a
        resumed run's earlier root writes count as reconstructed.

Run:  cd blastlab/tests && python test_write_budget.py
"""
import json
import os
import random
import re
import shutil
import sys
import tempfile
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)

from blastlab.core.case import (Case1D, Case2D, Case3D,        # noqa: E402
                                case_to_dict, load_case, save_case)
from blastlab.solvers.foam import backend, runloop, writer     # noqa: E402

FAILS = []
EVIDENCE = os.path.join(os.environ.get('USERPROFILE')
                        or os.path.expanduser('~'), 'blastlab_evidence',
                        '20260923-195308_3d_p31468-00')


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def case3(**kw):
    base = dict(solver='blastfoam', Lx=0.6, Ly=0.6, Lz=0.6,
                cell_size_m=0.025, charge=8.0, center=(0.3, 0.3, 0.3),
                gauges=[(0.45, 0.3, 0.3)], n_snapshots=4)
    base.update(kw)
    return Case3D(**base)


def case2(**kw):
    base = dict(solver='blastfoam', geometry='axisymmetric', Lx=1.0,
                Ly=1.0, cell_size_m=0.01, charge=1.0, center=(0.0, 0.5),
                n_snapshots=4)
    base.update(kw)
    return Case2D(**base)


def top_write_interval(control):
    """The controlDict's top-level writeInterval (the function objects
    carry their own, indented)."""
    m = re.search(r'^writeInterval\s+([^;]+);', control, re.M)
    return m.group(1).strip() if m else None


def test_defaults():
    print('\nB1: a case without a budget is exactly what it was')
    for cls in (Case1D, Case2D, Case3D):
        check(f'{cls.__name__}(): no write_budget key in case_to_dict',
              'write_budget' not in case_to_dict(cls()))
    check('Case1D has no write_budget field at all',
          not hasattr(Case1D(), 'write_budget'))
    for mk in (case2, case3):
        spec = writer.render_case(mk())
        check(f'{mk.__name__}: spec write_budget 0, adaptive on, the '
              f'transit-sized interval',
              spec.write_budget == 0 and spec.adaptive_write is True
              and top_write_interval(spec.files['system/controlDict'])
              == writer.fmt(spec.write_interval))
    cj = os.path.join(EVIDENCE, 'case.json')
    if not os.path.isfile(cj):
        print('  [SKIP] the HD1-3d evidence copy is not on this machine')
        return
    import _e2e_vent_3d as ev
    from blastlab.core import assessment as asm
    with open(cj, encoding='utf-8') as f:
        saved = json.load(f)
    want = json.loads(json.dumps(case_to_dict(
        asm.build_vent_case(ev.build())[0])))
    differ = sorted(k for k in set(saved) | set(want)
                    if saved.get(k) != want.get(k))
    check('the HD1-3d evidence case.json still equals the CFD case, key '
          'for key (VERSION 13, no write_budget key)',
          not differ and saved.get('version') == 13 and len(want) == 56,
          str(differ))


def test_pinned():
    print('\nB1: the option on')
    c = case3(t_end=0.03, write_budget=60)
    spec = writer.render_case(c, n_procs=2)
    ctl = spec.files['system/controlDict']
    check('t_end 0.03 s, budget 60 -> top-level writeInterval 0.0005',
          top_write_interval(ctl) == '0.0005', top_write_interval(ctl))
    check('the spec carries the budget and a pinned schedule',
          spec.write_budget == 60 and spec.adaptive_write is False
          and spec.write_interval == 0.03 / 60)
    times = re.search(r'writeTimes\s*\{[^}]*times\s*\(([^)]*)\)', ctl, re.S)
    check('the end-time write is still planted, once',
          times is not None and times.group(1).split() == ['0.03'],
          times.group(1) if times else ctl[:200])
    check('the banner says so, in its own words',
          backend._interval_label(spec) == '(pinned: write budget 60)')
    plain = writer.render_case(case3(t_end=0.03))
    check('and a default spec keeps the banner\'s two old phrasings',
          backend._interval_label(plain) == '(initial, adaptive)')
    plain.adaptive_write = False
    check('   (the pinned-schedule one too)',
          backend._interval_label(plain) == '(pinned schedule)')
    c2 = case2(t_end=0.01, write_budget=20)
    s2 = writer.render_case(c2)
    check('2D: t_end 0.01 s, budget 20 -> writeInterval 0.0005',
          top_write_interval(s2.files['system/controlDict']) == '0.0005'
          and s2.write_budget == 20 and s2.adaptive_write is False)
    nob = writer.render_case(case3(write_budget=60))
    check('without an end time the budget does not take effect (validation '
          'refuses it; the writer never pins to the cap)',
          nob.write_budget == 0 and nob.adaptive_write is True
          and nob.write_interval != nob.end_time / 60)

    # the adaptive controller: zero controlDict rewrites on the budget
    # spec (the test_adaptive_interval idiom)
    class _Run:
        stop_requested = False

    class _Hooks:
        def log(self, *_a, **_k):
            pass

        def cadence(self, *_a, **_k):
            pass

    rewrites = []
    real = runloop.runner.rewrite_control_entry
    runloop.runner.rewrite_control_entry = (
        lambda *a, **k: rewrites.append(a) or True)
    try:
        adapt = dict(interval=spec.write_interval, since=0)
        for _ in range(4 * runloop.ADAPT_EVERY):
            runloop.maybe_adapt(spec, dict(frac=0.10), adapt, _Run(),
                                _Hooks(), 40)
        check('runloop.maybe_adapt makes zero controlDict rewrites',
              not rewrites and adapt['interval'] == spec.write_interval,
              f'{len(rewrites)} rewrites')
    finally:
        runloop.runner.rewrite_control_entry = real

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'case.json')
        save_case(c, path)
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
        back = load_case(path)
    check('save_case / load_case keep write_budget = 60',
          raw.get('write_budget') == 60 and back.write_budget == 60
          and raw.get('version') == 13)


def test_solver_expression():
    print('\nB1: the solvers\' own adaptive expression')

    class _Stop(Exception):
        pass

    class _Hooks:
        def cadence(self, *_a, **_k):
            raise _Stop()                 # right after the expression

        def __getattr__(self, _name):
            return lambda *a, **k: None

    for solve, mk, dim in ((backend.solve_3d_foam, case3, 3),
                           (backend.solve_2d_foam, case2, 2)):
        for budget, want in ((0, True), (10, False)):
            c = mk(t_end=0.01, write_budget=budget)
            spec = writer.render_case(c)
            try:
                solve(c, hooks=_Hooks(), adaptive_write=True, spec=spec)
            except _Stop:
                pass
            check(f'{dim}D, budget {budget}: adaptive_write {want}',
                  spec.adaptive_write is want)


# ── B2: the decomposed copy of the latest write only ───────────────────

FIELDS = ('p', 'rho', 'U', 'alpha.expl')
N = 8                                      # cells per rank / at the root


def field(name, vector=False):
    rows = (['(1 2 3)'] * N) if vector else ['101325'] * N
    kind = 'vector' if vector else 'scalar'
    return ('FoamFile { format ascii; object ' + name + '; }\n'
            f'internalField   nonuniform List<{kind}>\n{N}\n(\n'
            + '\n'.join(rows) + '\n)\n;\nboundaryField { }\n')


def write_time(d, t, fields=FIELDS):
    os.makedirs(os.path.join(d, 'uniform'), exist_ok=True)
    with open(os.path.join(d, 'uniform', 'time'), 'w') as f:
        f.write(f'value {t};\ndeltaT 1e-07;\n')
    for name in fields:
        with open(os.path.join(d, name), 'w') as f:
            f.write(field(name, vector=(name == 'U')))


def fake_run(root, times, partial=None, reconstructed=()):
    """2 ranks: processorN/{constant, 0, times...}; `partial` is a time
    that is complete on rank 0 only. The root holds the writer's 0 and
    `reconstructed`."""
    for r in range(2):
        pr = os.path.join(root, f'processor{r}')
        os.makedirs(os.path.join(pr, 'constant', 'polyMesh'))
        write_time(os.path.join(pr, '0'), 0, fields=('p',))  # not "ready"
        for t in times:
            write_time(os.path.join(pr, t), t)
        if partial:
            write_time(os.path.join(pr, partial), partial,
                       fields=FIELDS if r == 0 else ('p', 'rho'))
    write_time(os.path.join(root, '0'), 0, fields=('p', 'U'))
    for t in reconstructed:
        write_time(os.path.join(root, t), t)


def local_delete(root, calls):
    """A deleter for a local fake run: the same path guard as the WSL
    one (purge_paths), then shutil on the local mirror of each path."""
    def delete(spec, names):
        calls.append(list(names))
        for p in runloop.purge_paths(spec.case_posix, spec.n_procs, names):
            rel = p[len(spec.case_posix) + 1:]
            shutil.rmtree(os.path.join(root, *rel.split('/')),
                          ignore_errors=True)
        return True
    return delete


def listing(root):
    return {d: sorted(os.listdir(os.path.join(root, d)))
            for d in sorted(os.listdir(root)) if d.startswith('processor')}


def tree(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        for name in dn + fn:
            p = os.path.join(dp, name)
            st = os.stat(p)
            out[os.path.relpath(p, root)] = (os.path.isdir(p), st.st_size,
                                             st.st_mtime_ns)
    return out


def budget_spec(root, budget=10, n_procs=2, amr=0):
    spec = writer.CaseSpec(dim=3, material='TNT', n_procs=n_procs,
                           write_budget=budget)
    spec.amr = amr
    spec.case_unc = root
    spec.case_posix = '/root/blastlab_runs/20260924-000000_3d_p1-00'
    return spec


class Hooks:
    def __init__(self):
        self.lines = []

    def log(self, s):
        self.lines.append(s)

    def should_stop(self):
        return False


def random_sets(rng):
    """One random case for the planner's property checks: (pool, done,
    reconstructed, common ready), drawn from '0' and twelve times."""
    pool = ['0'] + [f'0.{v:g}' for v in sorted(rng.sample(range(1, 40), 12))]
    done = set(rng.sample(pool, rng.randint(0, len(pool))))
    rec = set(rng.sample(pool, rng.randint(0, len(pool))))
    common = set(rng.sample(pool, rng.randint(0, len(pool))))
    return pool, done, rec, common


def resume_start(spec, root, hooks):
    """backend._resume_start_time over the root's time dirs, filtered as
    backend.resume_run filters them (t > 0, or the dir '0')."""
    times = [n for t, n in backend.reader.list_times(root)
             if float(t) > 0 or n == '0']
    return backend._resume_start_time(spec, times, hooks)


def test_planner():
    print('\nB2: the purge planner')
    rng = random.Random(15)
    bad = []
    for _ in range(3000):
        pool, done, rec, common = random_sets(rng)
        start = rng.choice(['0', pool[3]])
        plan = runloop.decomposed_purge_plan(done, rec, common, start)
        newest = max((float(t) for t in common), default=None)
        if newest is None and plan:
            bad.append(('no common time', plan))
        for t in plan:
            if (t not in done or t not in rec or t == start
                    or float(t) >= newest):
                bad.append((t, done, rec, common, start))
        if plan != sorted(plan, key=float):
            bad.append(('unsorted', plan))
    check('3000 random cases: never the newest complete common time, the '
          'start dir, a time not ingested or not reconstructed, or a newer '
          '(torn) one; sorted', not bad, str(bad[:3]))
    check('nothing complete on every rank -> nothing to purge',
          runloop.decomposed_purge_plan({'0.1'}, {'0.1'}, set(), '0') == [])
    check('the one-line case: t1, t2 go, t3 (newest) stays',
          runloop.decomposed_purge_plan(
              {'0.1', '0.2', '0.3'}, {'0.1', '0.2', '0.3'},
              {'0.1', '0.2', '0.3'}, '0') == ['0.1', '0.2'])
    with tempfile.TemporaryDirectory() as d:
        for kw, want in ((dict(budget=10), True), (dict(budget=0), False),
                         (dict(n_procs=1), False),
                         (dict(amr=1), False)):
            check(f'purge_active with {kw}: {want}',
                  runloop.purge_active(budget_spec(d, **kw)) is want)


def test_paths():
    print('\nB2: the deleter builds nothing but processor<N>/<time>')
    case = '/root/blastlab_runs/20260924-000000_3d_p1-00'
    got = runloop.purge_paths(case, 2, ['0.0005', '1e-05'])
    check('two ranks x two times, exactly',
          got == [f'{case}/processor0/0.0005', f'{case}/processor1/0.0005',
                  f'{case}/processor0/1e-05', f'{case}/processor1/1e-05'],
          str(got))
    for what, args in (
            ('a relative case', ('root/blastlab_runs/x', 2, ['0.1'])),
            ('a case outside the runs root', ('/root/other/x', 2, ['0.1'])),
            ('the runs root itself', ('/root/blastlab_runs', 2, ['0.1'])),
            ('a nested path', (case + '/processor0', 2, ['0.1'])),
            ('a ..', ('/root/blastlab_runs/../x', 2, ['0.1'])),
            ('a quote in the case', ("/root/blastlab_runs/x'y", 2, ['0.1'])),
            ('a serial case', (case, 1, ['0.1'])),
            ('constant', (case, 2, ['constant'])),
            ('a path in the name', (case, 2, ['0.1/../x'])),
            ('a space in the name', (case, 2, ['0.1 0.2'])),
            ('a quote in the name', (case, 2, ["0.1'"])),
            ('a negative time', (case, 2, ['-0.1'])),
            ('a processor dir as a name', (case, 2, ['processor0']))):
        try:
            runloop.purge_paths(*args)
            check(f'refuses {what}', False)
        except ValueError:
            check(f'refuses {what}', True)


def test_fake_run():
    print('\nB2: a fake 2-rank run (no WSL)')
    t1, t2, t3, t4 = '0.001', '0.002', '0.003', '0.004'
    with tempfile.TemporaryDirectory() as root:
        fake_run(root, [t1, t2, t3], partial=t4,
                 reconstructed=[t1, t2, t3])
        spec = budget_spec(root)
        hooks, calls = Hooks(), []
        purge = runloop.DecomposedPurge(spec, FIELDS, hooks,
                                        delete=local_delete(root, calls))
        purge.reconstructed.clear()           # this session's own record
        purge.covered([t1, t2, t3])
        root_before = {k: v for k, v in tree(root).items()
                       if not k.startswith('processor')}
        gone = purge.run({t1: 0.001, t2: 0.002, t3: 0.003})
        check('t1 and t2 are purged', gone == [t1, t2], str(gone))
        want = ['0', t3, t4, 'constant']
        check('each processorN holds {constant, 0, t3, t4 (partial)}',
              listing(root) == {'processor0': want, 'processor1': want},
              str(listing(root)))
        check('the root is untouched',
              {k: v for k, v in tree(root).items()
               if not k.startswith('processor')} == root_before)
        check('backend._n_procs_on_disk still reports 2',
              backend._n_procs_on_disk(root) == 2)
        name, skipped = resume_start(spec, root, hooks)
        check('backend._resume_start_time picks the latest root time',
              name == t3 and not skipped, f'{name}, {skipped}')
        n = len(calls)
        again = purge.run({t1: 0.001, t2: 0.002, t3: 0.003})
        check('a second purge is a no-op', again == [] and len(calls) == n)
        # t4 completes: now t3 may go and t4 is the newest
        write_time(os.path.join(root, 'processor1', t4), t4)
        write_time(os.path.join(root, t4), t4)
        purge.covered([t4])
        gone = purge.run({t1: 0, t2: 0, t3: 0, t4: 0})
        check('once t4 is complete everywhere, t3 goes and t4 stays',
              gone == [t3] and listing(root)['processor1']
              == ['0', t4, 'constant'], f'{gone}, {listing(root)}')
        check('one log line for the purge, not one per time',
              sum('write budget' in s for s in hooks.lines) == 1,
              str(hooks.lines))

    with tempfile.TemporaryDirectory() as root:
        fake_run(root, [t1, t2, t3], reconstructed=[t1, t2, t3])
        hooks, calls = Hooks(), []
        purge = runloop.DecomposedPurge(budget_spec(root), FIELDS, hooks,
                                        delete=local_delete(root, calls))
        check('a resumed run: the root writes already whole count as '
              'reconstructed', purge.reconstructed == {t1, t2, t3},
              str(purge.reconstructed))
        check('and are purged once ingested',
              purge.run({t1: 0, t2: 0, t3: 0}) == [t1, t2])
        n = len(calls)
        again = runloop.DecomposedPurge(budget_spec(root), FIELDS, hooks,
                                        delete=local_delete(root, calls))
        check('a later session does not re-delete what is already gone',
              again.run({t1: 0, t2: 0, t3: 0}) == [] and len(calls) == n,
              str(calls))

    with tempfile.TemporaryDirectory() as root:
        fake_run(root, [t1, t2, t3], reconstructed=[t1, t2, t3])
        hooks, attempts = Hooks(), []

        def failing(spec, names):
            attempts.append(list(names))
            raise OSError('wsl.exe went away')

        purge = runloop.DecomposedPurge(budget_spec(root), FIELDS, hooks,
                                        delete=failing)
        first = purge.run({t1: 0, t2: 0, t3: 0})
        second = purge.run({t1: 0, t2: 0, t3: 0})
        check('a failing delete never raises, is retried at the next pass '
              'and logged once',
              first == [] and second == [] and len(attempts) == 2
              and sum('could not remove' in s for s in hooks.lines) == 1,
              str(hooks.lines))
        check('and leaves every processor time in place',
              listing(root)['processor0'] == ['0', t1, t2, t3, 'constant'])


def test_whole_ingest():
    print('\nB2: through a whole fake ingest (FoamRunLoop._ingest_ready)')
    t1, t2, t3, t4 = '0.001', '0.002', '0.003', '0.004'
    for budget in (0, 10):
        with tempfile.TemporaryDirectory() as root:
            fake_run(root, [t1, t2, t3], partial=t4)
            spec = budget_spec(root, budget=budget)
            hooks, calls = Hooks(), []
            loop = runloop.FoamRunLoop.__new__(runloop.FoamRunLoop)
            loop.spec, loop.hooks, loop.fields, loop.done = (
                spec, hooks, FIELDS, {})
            loop.live_set = None
            loop.read_dir = lambda name, dpath: name
            loop.on_frame = (lambda name, dpath, payload:
                             loop.done.__setitem__(name, float(name)))
            loop.order = runloop.OrderedIngest(spec, FIELDS, hooks)
            loop.foam = SimpleNamespace(stop_requested=False, running=False)
            loop.purge = runloop.DecomposedPurge(
                spec, FIELDS, hooks, delete=local_delete(root, calls))

            def fake_reconstruct(case_posix, cmds, timeout=0):
                (want,) = re.findall(r'-time (\S+)', cmds[0])
                for t in want.split(','):
                    shutil.copytree(os.path.join(root, 'processor0', t),
                                    os.path.join(root, t))
                return ''

            real = runloop.runner.run_stage
            runloop.runner.run_stage = fake_reconstruct
            try:
                loop._ingest_ready(final=True)
            finally:
                runloop.runner.run_stage = real
            ingested = sorted(loop.done, key=float)
            if budget == 0:
                check('budget 0: the ingest read t1..t3 and the spy deleter '
                      'was called zero times',
                      ingested == [t1, t2, t3] and calls == [],
                      f'{ingested}, {calls}')
                check('   and every processor time is still there',
                      listing(root)['processor0']
                      == ['0', t1, t2, t3, t4, 'constant'])
            else:
                check('budget 10: one purge, of t1 and t2, after the ingest',
                      ingested == [t1, t2, t3] and calls == [[t1, t2]],
                      f'{ingested}, {calls}')


def test_purge_anchor():
    print('\nB2 (verify): the purge anchors on the newest time that is '
          'complete on every rank AND reconstructed')
    t1, t2, t3 = '0.001', '0.002', '0.003'
    check('a newest common time whose reconstructPar failed does not '
          'anchor the plan: t2 stays',
          runloop.decomposed_purge_plan({t1, t2}, {t1, t2}, {t1, t2, t3},
                                        '0') == [t1])
    check('   and once that time is reconstructed, it does',
          runloop.decomposed_purge_plan({t1, t2, t3}, {t1, t2, t3},
                                        {t1, t2, t3}, '0') == [t1, t2])
    rng = random.Random(1135)
    bad = []
    for _ in range(3000):
        _pool, done, rec, common = random_sets(rng)
        plan = runloop.decomposed_purge_plan(done, rec, common, '0')
        anchor = max((float(t) for t in common if t in rec), default=None)
        if anchor is None:
            if plan:
                bad.append(('no reconstructed common time', plan))
            continue
        bad += [(t, anchor) for t in plan if float(t) >= anchor]
    check('3000 random cases: never the newest time that is both complete '
          'on every rank and reconstructed, nor anything newer',
          not bad, str(bad[:3]))

    # the P1-5 walk-back: t3's reconstructPar failed and left a root copy
    # without p, so a resume restarts from t2 - whose processor copy the
    # purge must therefore have kept
    with tempfile.TemporaryDirectory() as root:
        fake_run(root, [t1, t2, t3], reconstructed=[t1, t2])
        os.makedirs(os.path.join(root, t3, 'uniform'))
        with open(os.path.join(root, t3, 'uniform', 'time'), 'w') as f:
            f.write(f'value {t3};\n')
        spec = budget_spec(root)
        hooks, calls = Hooks(), []
        purge = runloop.DecomposedPurge(spec, FIELDS, hooks,
                                        delete=local_delete(root, calls))
        purge.reconstructed.clear()
        purge.covered([t1, t2])                 # not t3: it failed
        gone = purge.run({t1: 0.001, t2: 0.002})
        name, skipped = resume_start(spec, root, hooks)
        check('a torn newest root copy: the resume walks back to t2, and '
              't2 is still in every processor dir',
              gone == [t1] and name == t2
              and [s[0] for s in skipped] == [t3]
              and all(os.path.isdir(os.path.join(root, f'processor{i}', t2))
                      for i in range(2)),
              f'purged {gone}, restart {name}, {listing(root)}')


def test_rm_chunks():
    print("\nB2 (verify): the rm never meets Windows' command-line cap")
    import subprocess
    from blastlab.solvers.foam import env
    # a run name of real length that does not exist - strings only here
    case = '/root/blastlab_runs/20260924-999999_3d_p99999-99'
    names = [f'{0.0005 * k:.8g}' for k in range(1, 61)]
    paths = runloop.purge_paths(case, 13, names)            # 780 paths
    one_line = subprocess.list2cmdline(env.wsl_plain_argv(
        'rm -rf -- ' + ' '.join(f"'{p}'" for p in paths)))
    scripts = runloop.rm_scripts(paths)
    longest = max(len(subprocess.list2cmdline(env.wsl_plain_argv(s)))
                  for s in scripts)
    check('60 writes on 13 ranks would be one line over 32,767 characters; '
          'the chunks are each well under it',
          len(one_line) > 32767 and len(scripts) > 1 and longest < 32767
          and all(len(s) <= runloop.RM_CHUNK_CHARS for s in scripts),
          f'one line {len(one_line)}, {len(scripts)} stages, longest '
          f'{longest}')
    named = [a[1:-1] for s in scripts
             for a in s[len('rm -rf -- '):].split(' ')]
    check('   and they name every path exactly once, in order',
          named == paths)
    few = paths[:26]
    check('a normal purge is still one stage, the same line as before',
          runloop.rm_scripts(few)
          == ['rm -rf -- ' + ' '.join(f"'{p}'" for p in few)])
    check('an empty plan is no stage at all', runloop.rm_scripts([]) == [])

    # delete_decomposed through a stub (budget_spec's run does not exist
    # either): one stage per chunk, and False as soon as one fails
    spec = budget_spec(tempfile.gettempdir(), n_procs=13)
    want = len(runloop.rm_scripts(runloop.purge_paths(spec.case_posix, 13,
                                                      names)))
    calls, codes = [], []
    real = subprocess.run

    def stub(argv, **_kw):
        calls.append(argv)
        return SimpleNamespace(returncode=codes.pop(0) if codes else 0)

    subprocess.run = stub
    try:
        ok = runloop.delete_decomposed(spec, names)
        n_ok = len(calls)
        calls.clear()
        codes[:] = [0, 1]
        failed = runloop.delete_decomposed(spec, names)
    finally:
        subprocess.run = real
    check('delete_decomposed runs one WSL stage per chunk and says True',
          ok is True and want > 1 and n_ok == want, f'{n_ok} vs {want}')
    check('   and says False when a stage fails, stopping there',
          failed is False and len(calls) == 2, f'{len(calls)} stages')


def main():
    test_defaults()
    test_pinned()
    test_solver_expression()
    test_planner()
    test_paths()
    test_fake_run()
    test_whole_ingest()
    test_purge_anchor()
    test_rm_chunks()


if __name__ == '__main__':
    main()
    print()
    print('WRITE BUDGET: ' + ('PASS' if not FAILS else
                              f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
