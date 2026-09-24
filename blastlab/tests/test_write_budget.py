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

Run:  cd blastlab/tests && python test_write_budget.py
"""
import json
import os
import re
import sys
import tempfile

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


def main():
    test_defaults()
    test_pinned()
    test_solver_expression()


if __name__ == '__main__':
    main()
    print()
    print('WRITE BUDGET: ' + ('PASS' if not FAILS else
                              f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
