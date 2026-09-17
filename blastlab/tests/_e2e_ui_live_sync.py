"""Is the live 3D view in step with the run, or just moving?

"It updates" and "it is in sync" are different claims, and only the
first one had been measured. This measures the second, on a real
blastFoam 3D run through the real window:

  solver time   what the run has reached, from the Run tab's own chip
  volume time   the frame the viewer child says it is SHOWING
  plane time    the newest burst plane handed to it

and reports the three things that decide whether a live view can be
trusted:

  LAG      solver time minus the time on screen. A bounded lag is a
           pipeline; a growing one is a backlog, and the picture is
           drifting further from the run the longer it goes.
  ORDER    the displayed time must never go backwards. A latest-wins
           ring drops frames on purpose - dropping is fine, going back
           in time is not.
  AHEAD    the sampled plane may lead the volume (that is the point of
           M6b) but must never trail it, or the scene would be showing
           an older plane over a newer volume.

Needs WSL with blastFoam and a real platform. ~5 minutes.

Run:  cd blastlab/tests && python _e2e_ui_live_sync.py
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.pop('QT_QPA_PLATFORM', None)
os.environ.setdefault('MPLBACKEND', 'Agg')
_dir = tempfile.mkdtemp(prefix='blastlab_sync_')
_settings = os.path.join(_dir, 'settings.json')
with open(_settings, 'w', encoding='utf-8') as _f:
    _f.write('{"auto_cleanup": false}')
os.environ['BLASTLAB_SETTINGS'] = _settings

RUN_TIMEOUT_S = 900
#: the lag may not grow by more than this factor from the first half of
#: the run to the second - a pipeline holds roughly steady, a backlog
#: does not
LAG_GROWTH_MAX = 2.5

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f'  [SKIP] blastFoam unavailable: {detail}')
        return 0
    from blastlab.viz3d import pyvista_available
    if not pyvista_available():
        print('  [SKIP] pyvista is not installed')
        return 0

    from PySide6.QtWidgets import QApplication
    from blastlab.ui.testing import ensure_qapp, pump
    ensure_qapp(offscreen=False)
    app = QApplication.instance()
    if app.platformName() == 'offscreen':
        print('  [SKIP] the offscreen platform has no render window')
        return 0
    from blastlab.core.case import Case3D
    from blastlab.ui.app import MainWindow

    case = Case3D(Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.03,
                  charge=8.0, center=(0.5, 0.5, 0.5),
                  gauges=[(0.85, 0.5, 0.5)],
                  bcs=dict(x_lo='terminate', x_hi='terminate',
                           y_lo='terminate', y_hi='terminate',
                           z_lo='terminate', z_hi='terminate'),
                  n_snapshots=3, record_frames=0,
                  solver='blastfoam', material='TNT')

    win = MainWindow()
    win.resize(1280, 860)
    win.show()
    pump(200)
    win.setup.set_case(case)
    win._schedule_validate()
    pump(400)
    win._show('run')
    pump(150)
    host = win.run_panel.view3d
    check('the Run tab owns a 3D host', host is not None)
    if host is None:
        return 1
    win.run_panel.show_3d_tab()
    pump(150)

    print('\nS1: run it, and watch the three clocks')
    # count the 2D live frames too: `tail_live` emits the 2D frame and
    # the 3D plane from the same branch, so if one stalls and the other
    # does not, the gate between them is the cause - and if both stall,
    # the Run tab's own live view is freezing as well
    n2d = {'n': 0}
    real_on_frame = win.run_panel.on_frame

    def counting_on_frame(field, t, levels=None):
        n2d['n'] += 1
        return real_on_frame(field, t, levels)

    win.run_panel.on_frame = counting_on_frame
    win._run_single()
    # three counters along the plane's path, so a stall names its own
    # link instead of being guessed at: emitted by the solver thread,
    # drained by the GUI, handed to the host
    hooks = win.ctrl.worker.hooks
    emitted = {'n': 0, 'gate': 0}
    real_surf3d = hooks.surf3d
    real_wants = hooks.wants_surf3d

    def counting_surf3d(t, field2d):
        emitted['n'] += 1
        return real_surf3d(t, field2d)

    def counting_wants():
        ok = real_wants()
        if ok:
            emitted['gate'] += 1
        return ok

    hooks.surf3d = counting_surf3d
    hooks.wants_surf3d = counting_wants
    drained = {'n': 0}
    real_latest = hooks.latest_surf3d

    def counting_latest():
        drained['n'] += 1
        return real_latest()

    hooks.latest_surf3d = counting_latest
    # producer or consumer? count what blastFoam actually leaves on disk
    # for the live slice, so "the samples stopped" and "we stopped
    # reading them" cannot be confused for each other
    from blastlab.solvers.foam import reader as _reader
    produced = {'calls': 0, 'seen': set()}
    real_list = _reader.list_sample_times

    produced['newest'] = ''
    produced['present'] = 0

    def counting_list(case_unc, name):
        out = real_list(case_unc, name)
        produced['calls'] += 1
        produced['present'] = len(out)
        for _t, n in out:
            produced['seen'].add(n)
            if n > produced['newest']:
                produced['newest'] = n
        return out

    _reader.list_sample_times = counting_list
    decoded = {'ok': 0, 'none': 0}
    real_read = _reader.read_surface_sample

    def counting_read(case_unc, name, tdir):
        out = real_read(case_unc, name, tdir)
        decoded['none' if out is None else 'ok'] += 1
        return out

    _reader.read_surface_sample = counting_read
    # and inside the tail itself: entries seen, already-consumed, fresh.
    # The gate that stops the live view has to name itself.
    from blastlab.solvers.foam import runloop as _rl
    tail = {'calls': 0, 'nofresh': 0, 'notdue': 0, 'last': ''}
    real_tail = _rl.tail_live

    def watching_tail(spec, hooks, st, live, set_name, decode):
        tail['calls'] += 1
        entries = _reader.list_sample_times(spec.case_unc, set_name)
        fresh = [(t, n) for t, n in entries if n not in live['seen']]
        tail['last'] = (f"policy={hooks.refresh} entries={len(entries)} "
                        f"seen={len(live['seen'])} fresh={len(fresh)} "
                        f"step={st.get('step')} "
                        f"live_step={live.get('step')} "
                        f"t_frame={st.get('t_frame')} "
                        f"fo_steps={live.get('fo_steps')} "
                        f"newest_fresh_t={fresh[-1][0] if fresh else None}")
        if not fresh:
            tail['nofresh'] += 1
        elif not _rl.due_sparse(hooks.refresh, st['step'], live):
            tail['notdue'] += 1
        return real_tail(spec, hooks, st, live, set_name, decode)

    _rl.tail_live = watching_tail
    win.ctrl.worker.hooks._tail_watch = tail
    samples = []                       # (wall, solver_t, vol_t, plane_t)
    t0 = time.time()
    last_poll = 0.0
    while win.ctrl.running and time.time() - t0 < RUN_TIMEOUT_S:
        pump(20)
        now = time.time()
        if now - last_poll < 0.5:
            continue
        last_poll = now
        solver_t = _solver_time(win)
        vol_t = host.displayed_time()
        plane_t = host.sampled_time()
        if solver_t is None or vol_t is None:
            continue
        samples.append((now - t0, solver_t, vol_t, plane_t,
                        int(getattr(host, '_n_sampled', 0)),
                        int(host._n_frames), int(n2d['n']),
                        len(produced['seen']), produced['newest'],
                        produced['present'],
                        (tail['calls'], tail['nofresh'], tail['notdue'])))
    pump(300)
    took = time.time() - t0
    print(f'    the run took {took:.0f} s, {len(samples)} observations')
    check('the run finished', not win.ctrl.running)
    check('there is something to judge', len(samples) >= 8,
          f'{len(samples)} observations')
    if len(samples) < 8:
        return 1

    print('\nS1b: did either stream ever stop?')
    # A stream that dies mid-run looks exactly like one that is merely
    # slow, until the counts are plotted against the clock.
    quarter = max(1, len(samples) // 6)
    for i in list(range(0, len(samples), quarter)) + [len(samples) - 1]:
        (w, _st, _vt, _pt, npl, nfr, n2, ndirs, _newest, present,
         tc) = samples[i]
        print(f'    t+{w:6.1f}s  planes={npl:4d} volumes={nfr:4d} '
              f'2D={n2:4d} | dirs ever={ndirs:4d} on disk={present:3d} '
              f'| tail calls={tc[0]:4d} nofresh={tc[1]:4d} '
              f'notdue={tc[2]:3d}')
    print(f'    along the path: gate open {emitted["gate"]}x, '
          f'emitted {emitted["n"]}, drained {drained["n"]}, '
          f'reached the host {samples[-1][4]}')
    print(f'    blastFoam left {len(produced["seen"])} live-slice sample '
          f'dirs on disk, polled {produced["calls"]} times')
    print(f'    decode attempts: {decoded["ok"]} returned data, '
          f'{decoded["none"]} returned nothing')
    print(f'    inside the tail: {tail["calls"]} calls, '
          f'{tail["nofresh"]} found nothing fresh, '
          f'{tail["notdue"]} were not due')
    print(f'    the tail last saw: {tail["last"]}')
    still = 0.0
    run_gap = 0.0
    for i in range(1, len(samples)):
        if samples[i][4] == samples[i - 1][4]:
            run_gap += samples[i][0] - samples[i - 1][0]
            still = max(still, run_gap)
        else:
            run_gap = 0.0
    print(f'    longest stretch with NO new plane: {still:.1f} s')
    check('the plane stream never stalls for a large part of the run',
          still < max(30.0, 0.25 * took), f'{still:.1f} s of {took:.0f} s')
    # the backend's own canary, not every line that says "live slice"
    canary = [ln for ln in win.run_panel.log_text().splitlines()
              if 'live slice disabled' in ln.lower()
              or 'stop updating' in ln.lower()]
    if canary:
        print('    the backend said: ' + ' / '.join(c.strip()
                                                    for c in canary[-2:]))
    check('the backend did not disable the live slice', not canary,
          ' / '.join(c.strip() for c in canary[:2]))
    n2_end = samples[-1][6]
    print(f'    2D live frames delivered: {n2_end}')
    check('the Run tab\'s own 2D live view kept arriving too',
          n2_end > 0 and samples[-1][6] > samples[len(samples) // 2][6],
          f'{samples[len(samples) // 2][6]} at half time -> {n2_end}')

    print('\nS2: ORDER - the time on screen never goes backwards')
    vols = [s[2] for s in samples]
    back = [(i, vols[i - 1], vols[i]) for i in range(1, len(vols))
            if vols[i] < vols[i - 1] - 1e-12]
    check('the displayed frame time is monotonic', not back,
          str(back[:3]))
    planes = [s[3] for s in samples if s[3] is not None]
    pback = [(i, planes[i - 1], planes[i]) for i in range(1, len(planes))
             if planes[i] < planes[i - 1] - 1e-12]
    check('and so is the sampled plane', not pback, str(pback[:3]))

    print('\nS3: AHEAD - the plane leads the volume')
    # It leads almost always, and when it does not the reason is
    # structural rather than a fault: an ingested WRITE jumps the volume
    # to its own time, which can pass the last sample consumed. The
    # scene drops a superseded plane the moment that happens
    # (`_display`, pinned in test_viz3d_sampled_plane P5), so nothing
    # older is ever drawn over something newer. What is worth asserting
    # here is that the condition is transient, not that it never occurs.
    pairs = [(s[0], s[3], s[2]) for s in samples if s[3] is not None]
    trailing = [p for p in pairs if p[1] < p[2] - 1e-12]
    frac = len(trailing) / max(1, len(pairs))
    run = worst_run = 0
    for _w, pt, vt in pairs:
        run = run + 1 if pt < vt - 1e-12 else 0
        worst_run = max(worst_run, run)
    print(f'    trailing in {len(trailing)} of {len(pairs)} observations '
          f'({frac * 100:.1f} %), longest stretch {worst_run} '
          f'(~{worst_run * 0.5:.1f} s)')
    check('the plane leads the volume nearly all of the time',
          frac < 0.05, f'{frac * 100:.1f} %')
    check('and never trails it for long - a write hand-over, not a '
          'stall', worst_run <= 4, f'{worst_run} observations')
    leads = [p[1] - p[2] for p in pairs]
    if leads:
        print(f'    the plane leads by {min(leads):.3e} .. '
              f'{max(leads):.3e} s')

    print('\nS4: LAG - how far the picture is behind the run')
    lags = [s[1] - s[2] for s in samples]
    half = len(lags) // 2
    first, second = lags[:half], lags[half:]
    a = sum(first) / max(1, len(first))
    b = sum(second) / max(1, len(second))
    print(f'    lag: first half {a:.3e} s, second half {b:.3e} s, '
          f'worst {max(lags):.3e} s')
    span = samples[-1][1] - samples[0][1]
    print(f'    the run advanced {span:.3e} s of simulated time while '
          f'watching')
    check('the picture is behind the run, never ahead of it',
          min(lags) >= -1e-12, f'{min(lags):.3e} s')
    chip = _chip_time(win)
    if chip is not None:
        print(f'    for the record, the chip the user reads shows '
              f'{chip * 1e3:.3f} ms')
    check('and the lag does not grow away as the run goes on',
          b <= max(a * LAG_GROWTH_MAX, a + 1e-9) or b <= 1e-9,
          f'{a:.3e} -> {b:.3e} s')
    if span > 0:
        worst_frac = max(lags) / span
        print(f'    worst lag is {worst_frac * 100:.1f} % of the '
              f'simulated span')
        check('the worst lag is a small part of what the run covered',
              worst_frac < 0.5, f'{worst_frac * 100:.1f} %')

    print('\nS5: the plane really did arrive more often than the volume')
    n_planes = int(getattr(host, '_n_sampled', 0))
    n_frames = int(host._n_frames)
    print(f'    {n_planes} planes, {n_frames} volumes '
          f'({n_planes / max(1, n_frames):.1f}x)')
    check('more plane updates than written frames', n_planes > n_frames,
          f'{n_planes} vs {n_frames}')

    try:
        win.close()
    except Exception:
        pass
    pump(100)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'UI LIVE SYNC: PASS ({len(RAN)} checks, run {took:.0f} s)')
    return 0


def _solver_time(win):
    """The run's own clock [s], from the newest Progress.

    NOT from the chip. The chip reads `f'{p.t*1e3:.3f}'` - a microsecond
    of resolution - and the first version of this file compared a
    microsecond-quantised label against an exact frame time, then
    reported the 1.5 us disagreement as the picture running ahead of the
    run. The label is what the user reads; it is not what a synchronisation
    measurement may be built on.
    """
    try:
        p = win.ctrl.worker.hooks._last_p
        return None if p is None else float(p.t)
    except AttributeError:
        return None


def _chip_time(win):
    """What the user actually sees, for the record [s]."""
    try:
        return float(str(win.run_panel.chip_texts().get('t [ms]', ''))
                     .replace(',', '')) / 1e3
    except (TypeError, ValueError):
        return None


if __name__ == '__main__':
    sys.exit(main())
