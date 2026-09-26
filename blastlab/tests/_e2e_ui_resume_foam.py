"""Stop a blastFoam run from the Qt window, then resume it.

`RunController.resume_foam_run` has existed since M3 and had never been
run: the run browser's suite proves the refusals against a fake lister,
and nothing exercised the path that actually continues a solve. It is
also the one place where the Qt port can silently lose a day of compute
- a resume that quietly restarts from zero looks exactly like a resume
that worked, until the times are compared.

So the times are compared. The run is stopped partway, the stopped
result's gauge span is recorded, and after the resume the merged result
must still start at t = 0 (the replay rebuilt the accumulators) and end
LATER than the stop (the solver really carried on).

Needs WSL with blastFoam; SKIPs cleanly without it. Several minutes.

Run:  cd blastlab/tests && python _e2e_ui_resume_foam.py
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')
_dir = tempfile.mkdtemp(prefix='blastlab_ui_resume_')
_settings = os.path.join(_dir, 'settings.json')
with open(_settings, 'w', encoding='utf-8') as _f:
    _f.write('{"auto_cleanup": false}')
os.environ['BLASTLAB_SETTINGS'] = _settings

#: let it get properly under way before stopping, so there is a real
#: state to continue from and not just the initial write
RUN_BEFORE_STOP_S = 45
STOP_TIMEOUT_S = 300
RESUME_TIMEOUT_S = 900

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def gauge_span(result):
    g = getattr(result, 'gauges', None) or {}
    ts = g.get('times')
    if ts is None or not len(ts):
        return None
    return float(ts[0]), float(ts[-1])


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f'  [SKIP] blastFoam unavailable: {detail}')
        return 0
    print(f'blastFoam: {detail}')

    from blastlab.ui.testing import ensure_qapp, pump, use_model
    ensure_qapp(offscreen='--window' not in sys.argv)
    from blastlab.core.case import Case2D
    from blastlab.ui.app import MainWindow

    case = Case2D(geometry='axisymmetric', Lx=0.6, Ly=1.2,
                  cell_size_m=0.015, charge=1.0, center=(0.0, 0.6),
                  gauges=[(0.35, 0.6)], n_snapshots=2,
                  record_frames=0, anim_file=None,
                  bcs=dict(x_lo='reflect', x_hi='terminate',
                           y_lo='terminate', y_hi='terminate'),
                  solver='blastfoam', material='TNT')

    win = MainWindow()
    first = use_model(win)  # OUT-1: Run needs a runs folder and a model
    win.show()
    pump(200)
    win.setup.set_case(case)
    win._schedule_validate()
    pump(400)

    print('\nR1: start it, then stop it partway')
    win._run_single()
    t0 = time.time()
    while win.ctrl.running and time.time() - t0 < RUN_BEFORE_STOP_S:
        pump(100)
    check('it was still running when we asked it to stop',
          win.ctrl.running,
          '' if win.ctrl.running
          else 'it finished on its own - the case needs to be bigger')
    win.ctrl.stop()                     # what the Stop button does
    t1 = time.time()
    while win.ctrl.running and time.time() - t1 < STOP_TIMEOUT_S:
        pump(100)
    pump(300)
    print(f'    ran {t1 - t0:.0f} s, stopped in {time.time() - t1:.0f} s')
    log = win.run_panel.log_text()
    check('the stop was honoured', not win.ctrl.running)
    check('and it said so', 'stop requested' in log)
    check('nothing broke while draining', '[ui error handling' not in log)

    entries = win.results.entries()
    check('the stopped run still produced a result', len(entries) == 1,
          str([e.label for e in entries]))
    if not entries:
        return 1
    stopped = entries[0]
    check('labelled as stopped', 'stopped' in stopped.label.lower(),
          stopped.label)
    span = gauge_span(stopped.result)
    check('with a gauge trace to compare against', span is not None,
          str(span))
    if span is None:
        return 1
    print(f'    stopped run spans t = {span[0]:.6e} .. {span[1]:.6e} s')

    path = (stopped.result.meta or {}).get('case_dir')
    check('and it recorded the case directory to resume from',
          bool(path), str(path))
    if not path:
        return 1

    print('\nR2: resume it, the way the run browser does')
    second = use_model(win, 'QA_RESUME')   # OUT-1: the resume's own folder
    started = win._resume_foam_run(path)   # the run browser's callback
    check('the resume was accepted', started is True, str(started))
    if started is not True:
        return 1
    t2 = time.time()
    while win.ctrl.running and time.time() - t2 < RESUME_TIMEOUT_S:
        pump(100)
    pump(300)
    print(f'    the resume took {time.time() - t2:.0f} s')
    log2 = win.run_panel.log_text()
    check('the resumed run finished', '[run finished]' in log2,
          log2[-300:])
    check('nothing broke while draining it either',
          '[ui error handling' not in log2)

    print('\nR3: it CONTINUED the run - it did not start over')
    entries = win.results.entries()
    check('a second result arrived', len(entries) == 2,
          str([e.label for e in entries]))
    if len(entries) != 2:
        return 1
    resumed = entries[1]
    span2 = gauge_span(resumed.result)
    check('the resumed result has a gauge trace', span2 is not None,
          str(span2))
    if span2 is None:
        return 1
    print(f'    resumed run spans t = {span2[0]:.6e} .. {span2[1]:.6e} s')
    check('it reaches further in time than the stop did',
          span2[1] > span[1],
          f'{span[1]:.6e} -> {span2[1]:.6e}')
    check('and it still starts where the original did, so the replay '
          'rebuilt the whole history',
          abs(span2[0] - span[0]) <= max(1e-9, 1e-6 * abs(span[0])),
          f'{span[0]:.6e} vs {span2[0]:.6e}')
    check('the merged trace is longer, not just later',
          len((getattr(resumed.result, 'gauges', {}) or {})
              .get('times', []))
          > len((getattr(stopped.result, 'gauges', {}) or {})
                .get('times', [])),
          '')

    print('\nR4: OUT-1 - the stop kept its scratch; the resume wrote its '
          'model folder and released it')
    import json
    import subprocess

    def manifest(folder):
        try:
            with open(os.path.join(folder, 'manifest.json'),
                      encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}
    m1, m2 = manifest(first), manifest(second)
    s1, s2 = m1.get('wsl_scratch') or {}, m2.get('wsl_scratch') or {}
    check('the stopped run kept its scratch, and says why',
          s1.get('deleted') is False and s1.get('kept_because')
          == 'the run ended before its end time', str(s1))
    got = sorted(os.listdir(second)) if os.path.isdir(second) else []
    check('the resume wrote a complete model folder',
          {'MODEL.json', 'run.log', 'report.html', 'gauges', 'foam',
           'manifest.json'} <= set(got) and m2.get('failed') == [],
          f'{got} failed={m2.get("failed")}')
    check('and released the scratch after a verified copy',
          s2.get('deleted') is True
          and s2.get('posix') == s1.get('posix'), str(s2))
    if s2.get('posix'):
        rc = subprocess.run(env.wsl_plain_argv(
            f"test -d '{s2['posix']}'"), capture_output=True,
            stdin=subprocess.DEVNULL).returncode
        check('WSL agrees: the scratch is gone', rc != 0, s2['posix'])
    check('the Results VTK button now explains the release',
          resumed.result.meta.get('scratch_released') is True)

    win.close()
    pump(200)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'UI RESUME FOAM: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
