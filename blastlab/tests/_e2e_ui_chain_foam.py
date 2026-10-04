"""A real 1D -> 2D -> 3D blastFoam chain through the Qt window.

`_e2e_ui_chain.py` runs a native chain and `_e2e_gui_chain_foam.py` runs
a foam one through the Tk app; this is the missing corner, and the one
that matters, because blastFoam is the owner's solver and a chain is
where the port has the most to get wrong: three per-stage forms, a
profile handed over on disk between two different solvers' runs, and
three results finding their way back.

What it actually proves, rather than assumes:

- each stage really continued the previous one - the gauge time of a
  stage matches the time written into the profile it was handed;
- the chain is reproducible - `adaptive_write` is False on every saved
  case, so a re-run lands on the same write schedule (N2-13);
- the hand-off files exist and are not empty.

Deliberately small: the point is the hand-off, not the physics. Needs
WSL with blastFoam and takes several minutes; SKIPs cleanly without it.

Run:  cd blastlab/tests && python _e2e_ui_chain_foam.py
      python _e2e_ui_chain_foam.py --window
"""
import json
import os
import sys
import tempfile
import time
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')
_dir = tempfile.mkdtemp(prefix='blastlab_ui_chain_foam_')
_settings = os.path.join(_dir, 'settings.json')
with open(_settings, 'w', encoding='utf-8') as _f:
    _f.write('{"auto_cleanup": false}')
os.environ['BLASTLAB_SETTINGS'] = _settings

CHAIN_TIMEOUT_S = 1800

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def profile_time(path):
    """The time a stage's hand-off profile was taken at."""
    if not path or not os.path.exists(path):
        return None
    if path.endswith('.npz'):
        import numpy as np
        with np.load(path) as z:
            return float(z['t'])
    with open(path, encoding='ascii', errors='replace') as f:
        for line in f:
            if line.startswith('# time_s'):
                return float(line.split('=')[1])
    return None


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f'  [SKIP] blastFoam unavailable: {detail}')
        return 0
    print(f'blastFoam: {detail}')

    caught = []
    warnings.simplefilter('always')
    _orig = warnings.showwarning
    warnings.showwarning = lambda message, category, filename, lineno, \
        *a, **k: caught.append(f'{category.__name__}: {message} '
                               f'({os.path.basename(str(filename))}:'
                               f'{lineno})')

    from blastlab.ui.testing import ensure_qapp, pump, use_model
    ensure_qapp(offscreen='--window' not in sys.argv)
    from blastlab.core.case import Case1D, Case2D, Case3D
    from blastlab.ui.app import MainWindow

    win = MainWindow()
    # OUT-1: the chain writes into the Run tab's model folder
    ws = use_model(win, 'CHAIN_FOAM')
    win.show()
    pump(200)
    ch = win.chain

    # Each stage stops well inside the next one's domain, so every
    # hand-off really continues a state instead of restarting one.
    stages = {
        1: Case1D(radius_m=0.2, charge_kg=0.2, cell_size_m=0.002,
                  gauge_radii=[0.15], n_snapshots=1, solver='blastfoam'),
        2: Case2D(geometry='axisymmetric', Lx=0.5, Ly=1.0,
                  cell_size_m=0.02, center=(0.0, 0.5),
                  gauges=[(0.3, 0.5)], n_snapshots=1,
                  solver='blastfoam', material='TNT',
                  bcs=dict(x_lo='reflect', x_hi='terminate',
                           y_lo='terminate', y_hi='terminate')),
        3: Case3D(Lx=1.0, Ly=1.0, Lz=0.6, cell_size_m=0.04,
                  center=(0.5, 0.5, 0.3), gauges=[(0.8, 0.5, 0.3)],
                  n_snapshots=1, solver='blastfoam', material='TNT'),
    }

    print('\nC1: three stages, all on blastFoam')
    ch.set_route('123')         # GUI-9: was use[d].setChecked(True)
    for d, case in stages.items():
        ch.set_stage_case(d, case)
        pump(200)
        check(f'stage {d} took the case on blastFoam',
              ch.stage_solver.get(d) == 'blastfoam',
              str(ch.stage_solver.get(d)))
    check('all three are checked to run', ch.checked() == [1, 2, 3],
          str(ch.checked()))

    print('\nC2: the chain is accepted and runs')
    refusals = []
    ch.error_sink = lambda title, lines: refusals.append(list(lines))
    started = ch.run()
    check('nothing was refused', started is True and not refusals,
          str(refusals))
    if started is not True:
        warnings.showwarning = _orig
        print('\nUI CHAIN FOAM: FAIL - the chain never started')
        return 1
    check('and the Run tab came forward', win.current_tab() == 'run',
          win.current_tab())
    t0 = time.time()
    while win.ctrl.running and time.time() - t0 < CHAIN_TIMEOUT_S:
        pump(100)
    took = time.time() - t0
    pump(300)
    print(f'    the chain took {took:.1f} s')
    log = win.run_panel.log_text()
    check('it finished', '[run finished]' in log, log[-300:])
    check('nothing broke while draining', '[ui error handling' not in log)
    for d in (1, 2, 3):
        check(f'stage {d} announced itself as blastFoam',
              f'=== Stage {d}D blastFoam ===' in log
              or f'Stage {d}D' in log,
              [ln for ln in log.splitlines() if 'Stage' in ln][:4])

    print('\nC3: the hand-off really happened on disk')
    # OUT-1: MODEL\1d, 2d, 3d with the hand-offs at the model root
    saved = sorted(os.listdir(ws)) if os.path.isdir(ws) else []
    check('the model root holds 1d\\, 2d\\, 3d\\, both hand-offs and the '
          'root manifest',
          saved == ['.blastlab-model', '1d', '2d', '3d',
                    'handoff_1d_to_2d.txt', 'handoff_2d_to_3d.npz',
                    'manifest.json'], str(saved))
    p1 = next((os.path.join(ws, f) for f in saved
               if f.startswith('handoff_1d')), None)
    p2 = next((os.path.join(ws, f) for f in saved
               if f.startswith('handoff_2d')), None)
    check('stage 1 wrote a profile',
          p1 is not None and os.path.getsize(p1) > 100,
          str(saved))
    check('stage 2 wrote one too',
          p2 is not None and os.path.getsize(p2) > 100,
          str(saved))

    print('\nC4: one chain result of three stages, each continuing the last')
    # GUI-9 T5 (plan §7): one chain entry with a stage per dimension
    # (was: three entries in the picker, one per dimension)
    chains = win.results.entries()
    check('one chain entry in the picker', len(chains) == 1
          and chains[0].kind == 'chain',
          str([(e.label, e.kind) for e in chains]))
    entries = list(chains[0].stages or []) if chains else []
    check('with three stages, one per dimension',
          [e.dim for e in entries] == [1, 2, 3],
          str([(e.label, e.dim) for e in entries]))
    win._show('results')
    pump(80)
    for ent in entries:
        win.results.select_stage(ent.dim)
        pump(80)
        page = win.results.fields.page()
        check(f'stage {ent.dim}D draws in Field',
              win.results.current() is ent and page in ('image', 'figure'),
              page)
    times = {}
    for ent in entries:
        # `gauges['times']` is a numpy array, so `x or []` raises on the
        # ambiguous truth value - test against None, as gauge_summary
        # does
        g = getattr(ent.result, 'gauges', None) or {}
        ts = g.get('times')
        times[ent.dim] = None if ts is None or not len(ts) \
            else float(ts[0])
    print(f'    stage start times: {times}')
    for d, src in ((2, p1), (3, p2)):
        t_src = profile_time(src)
        t_stage = times.get(d)
        check(f'stage {d} starts at the profile time stage {d - 1} wrote',
              t_src is not None and t_stage is not None
              and abs(t_stage - t_src) <= max(1e-9, 1e-6 * abs(t_src)),
              f'gauge t0 {t_stage} vs profile {t_src}')
    ordered = [times.get(d) for d in (1, 2, 3)]
    check('and time only moves forward across the chain',
          all(t is not None for t in ordered)
          and ordered[0] < ordered[1] < ordered[2], str(ordered))

    print('\nC5: the chain can be reproduced from what it left behind')
    jsons = [os.path.join(d, 'MODEL.json') for d in ('1d', '2d', '3d')
             if os.path.isfile(os.path.join(ws, d, 'MODEL.json'))]
    check('a case JSON per stage', len(jsons) == 3, str(jsons))
    for name in jsons:
        with open(os.path.join(ws, name), encoding='utf-8') as f:
            d = json.load(f)
        check(f'{name} pins the write schedule and the solver',
              d.get('adaptive_write') is False
              and d.get('solver') == 'blastfoam',
              f"adaptive_write={d.get('adaptive_write')} "
              f"solver={d.get('solver')}")

    print('\nC6: OUT-1 - every stage copied foam\\ and released its scratch')
    for d in ('1d', '2d', '3d'):
        try:
            with open(os.path.join(ws, d, 'manifest.json'),
                      encoding='utf-8') as f:
                m = json.load(f)
        except (OSError, ValueError):
            m = {}
        scratch = m.get('wsl_scratch') or {}
        check(f'{d}: foam\\SHA256SUMS copied, scratch deleted',
              os.path.isfile(os.path.join(ws, d, 'foam', 'SHA256SUMS'))
              and scratch.get('deleted') is True and not m.get('failed'),
              f"{scratch} failed={m.get('failed')}")
        posix = scratch.get('posix')
        if posix:
            import subprocess
            rc = subprocess.run(env.wsl_plain_argv(f"test -d '{posix}'"),
                                capture_output=True,
                                stdin=subprocess.DEVNULL).returncode
            check(f'{d}: the WSL scratch is really gone', rc != 0, posix)

    real = [w for w in caught if 'DeprecationWarning' in w
            or 'UserWarning' in w or 'RuntimeWarning' in w]
    check('no Python warnings during the chain', not real,
          ' | '.join(sorted(set(real))[:5]))

    warnings.showwarning = _orig
    win.close()
    pump(200)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'UI CHAIN FOAM: PASS ({len(RAN)} checks, chain {took:.0f} s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
