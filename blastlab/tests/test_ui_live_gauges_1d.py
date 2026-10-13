"""D6 (owner 2026-10-13, batch 2026-10-12 gui-final): 1D and 2D live
gauges update DURING the run, on both solvers.

The owner watched a 1 kg / 30 m / 4 mm 1D blastFoam run whose gauge
column stayed empty until the end. Read-only diagnosis: blastFoam called
`backend._emit_gauges` only from the 3D `on_frame`, so the 1D and 2D
traces arrived with the Result; and the Run tab's ndarray-unsafe
`payload.get('times') or []` would have raised on the first one that did
arrive (`[ui error handling 'gauges']`).

 L1  native 1D, a real solve in a MainWindow: the live-gauge column draws
     more than one distinct series length before the final Result's;
 L2  blastFoam 1D and 2D, no WSL: the case is rendered, not written, and
     the run loop and the probe reader are stubbed. `_emit_gauges` reaches
     `hooks.gauges` from `on_frame` (the first time despite the previous
     run's throttle stamp: the per-run reset) and from `tail_live`, with an
     ndarray `times`; the real GuiHooks queue drained into the window
     raises no `[ui error handling 'gauges']`;
 L3  the 1D `run_started` names the kept gauges by their entered numbers.

Offscreen, throwaway settings and runs folder.
    cd blastlab/tests && python test_ui_live_gauges_1d.py
"""
import os
import queue
import shutil
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

FAIL = []
RAN = []
UI_ERR = "[ui error handling 'gauges']"


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def l1_native_1d(win, pump):
    from blastlab.core.case import Case1D
    print('\nL1: native 1D, the column draws while the run goes')
    rp = win.run_panel
    col = rp.gauge_col
    drawn = []                      # (series length, final?)
    state = dict(final=False)
    real_render, real_set = col._render, col.set_payload

    def render():
        p = col._payload
        n = len(p.get('times', ())) if p else 0
        drawn.append((n, state['final']))
        real_render()

    def set_payload(payload, final=False):
        state['final'] = bool(final)
        real_set(payload, final=final)
    col._render, col.set_payload = render, set_payload
    try:
        # a few seconds of solving: longer than REFRESH_MS, so the
        # trailing-edge redraw has room to show the run moving
        win.setup.set_case(Case1D(radius_m=3.0, charge_kg=1.0,
                                  cell_size_m=0.005,
                                  gauge_radii=[1.0, 2.0, 2.5],
                                  gauge_file=None, n_snapshots=2))
        win._schedule_validate()
        pump(400)
        win._show('run')
        pump(100)
        check('the gauge column on screen turns collection on',
              bool(getattr(win.ctrl, '_live_gauges', False)))
        t0 = time.time()
        win._run_single()
        while win.ctrl.running and time.time() - t0 < 300:
            pump(20)
        pump(300)
        live = sorted({n for n, fin in drawn if not fin and n > 0})
        print(f'    the run took {time.time() - t0:.1f} s; series lengths '
              f'drawn before final: {live[:4]} ... {live[-2:]}')
        check('the run finished', not win.ctrl.running)
        check('more than one distinct series length drawn before final',
              len(live) > 1, str(live))
        check('and the final Result drew last',
              bool(drawn) and drawn[-1][1], str(drawn[-1:]))
    finally:
        col._render, col.set_payload = real_render, real_set


class _FakeLoop:
    """FoamRunLoop's surface for the solve_*_foam callbacks, no solver:
    `run()` feeds three written times to `on_frame`, then two live
    samples through the real `runloop.tail_live`."""
    phase = []                  # the phase the next gauges() call is in
    frames = []                 # [(on_frame args)] built by the test
    gauges = None               # set by the backend, as on FoamRunLoop

    def __init__(self, spec, hooks, fields, done, live_set, decode,
                 read_dir, on_frame):
        from blastlab.core.constants import P_AIR
        from blastlab.solvers.foam import runloop
        self.spec, self.hooks, self.live_set = spec, hooks, live_set
        self.on_frame = on_frame
        self.st = dict(step=0, t=0.0, dt=0.0, p_max=float(P_AIR),
                       frac=None, t_frame=-1.0)
        self.live = runloop.new_live()
        self.stop_requested = False

    def protect(self, *a):
        pass

    unprotect = protect
    maybe_adapt = note_pause = gated_step = request_stop = protect

    def _decode(self, _tdir):
        """A live sample as the real decoders return it."""
        last = self.frames[-1][1]
        if self.spec.dim == 1:
            import numpy as np
            return np.array([self.spec.grid['r'], last['p']])
        return last[1]

    def run(self):
        from blastlab.solvers.foam import backend, runloop
        for name, payload in self.frames:
            self.phase[:] = ['on_frame']
            self.st['step'] += 10
            self.on_frame(name, os.path.join(self.spec.case_unc, name),
                          payload)
            backend.GAUGE_LIVE_S = 0.0      # the rest unthrottled
        self.phase[:] = ['tail_live']
        for tdir in ('0.0004', '0.0005'):
            os.makedirs(os.path.join(self.spec.case_unc, 'postProcessing',
                                     self.live_set, tdir))
            self.st['step'] += 10
            # as FoamRunLoop._ingest_live does (no keyword without a
            # callback, so the check also runs against the pre-D6 tail)
            kw = {} if self.gauges is None else dict(gauges=self.gauges)
            runloop.tail_live(self.spec, self.hooks, self.st, self.live,
                              self.live_set, self._decode, **kw)
        return 'safety cap'


def l2_foam(win, pump, dim):
    import numpy as np
    from blastlab.core.case import Case1D, Case2D
    from blastlab.core.constants import P_AIR
    from blastlab.solvers.foam import backend, writer
    from blastlab.solvers.worker import GuiHooks
    print(f'\nL2: blastFoam {dim}D, stubbed run loop and probes')
    if dim == 1:
        case = Case1D(radius_m=5.0, charge_kg=1.0, cell_size_m=0.01,
                      gauge_radii=[1.5, 3.0, 9.0], gauge_file=None,
                      solver='blastfoam')
    else:
        case = Case2D(geometry='planar', Lx=2.0, Ly=1.2, cell_size_m=0.04,
                      charge=8.0, center=(0.4, 0.6),
                      gauges=[(1.0, 0.4), (1.6, 0.2)], gauge_file=None,
                      n_snapshots=2, record_frames=0, anim_file=None,
                      solver='blastfoam')
    spec = writer.render_case(case)
    tmp = tempfile.mkdtemp(prefix='blastlab_d6_')
    spec.case_unc, spec.case_posix = tmp, '/tmp/blastlab_d6'

    n_cells = spec.n_cells
    if dim == 1:
        _FakeLoop.frames = [
            (f'{t:g}', dict(t=t, p=np.full(n_cells, P_AIR),
                            rho=np.ones(n_cells), u=np.zeros(n_cells)))
            for t in (1e-4, 2e-4, 3e-4)]
    else:
        grid = np.full((spec.nx, spec.ny), P_AIR)
        _FakeLoop.frames = [(f'{t:g}', (t, grid, None))
                            for t in (1e-4, 2e-4, 3e-4)]
    _FakeLoop.phase = []
    pts = [tuple(float(v) for v in p) for p in spec.probe_pts]
    where = (dict(radii=[p[0] for p in pts]) if dim == 1
             else dict(points=[p[:2] for p in pts]))
    calls = dict(n=0)

    def fake_probes(_spec, quiet=False):
        """_gauges_from_probes' shape: reader.read_probes' ndarray
        times, a list of per-probe arrays. The live read is quiet."""
        calls['n'] += 1
        calls['loud'] = calls.get('loud', 0) + (not quiet)
        k = 5 * calls['n']                  # the series grows per read
        return dict(times=np.linspace(0.0, 1e-4 * calls['n'], k),
                    pressures=[np.full(k, P_AIR + 1e3 * (i + 1))
                               for i in range(len(pts))], **where)

    q = queue.Queue()
    hooks = GuiHooks(q, threading.Event())
    hooks.live_gauges = True
    hooks.refresh = ('steps', 1)
    got = []
    real_gauges = hooks.gauges

    def gauges(payload):
        got.append((_FakeLoop.phase[0] if _FakeLoop.phase else '?',
                    payload))
        real_gauges(payload)
    hooks.gauges = gauges

    saved = (backend.FoamRunLoop, backend._gauges_from_probes,
             backend.finalize_1d, backend.finalize_2d, backend.GAUGE_LIVE_S)
    backend.FoamRunLoop = _FakeLoop
    backend._gauges_from_probes = fake_probes
    backend.finalize_1d = backend.finalize_2d = lambda *a, **k: 'result'
    # the previous run emitted a moment ago: without the per-run reset
    # its stamp would hold back this run's first payload
    backend._gauge_live['at'] = time.time()
    try:
        solve = backend.solve_1d_foam if dim == 1 else backend.solve_2d_foam
        out = solve(case, hooks=hooks, spec=spec)
    finally:
        (backend.FoamRunLoop, backend._gauges_from_probes,
         backend.finalize_1d, backend.finalize_2d,
         backend.GAUGE_LIVE_S) = saved
        shutil.rmtree(tmp, ignore_errors=True)
    phases = [ph for ph, _p in got]
    check(f'{dim}D: the stubbed solve ran to its finalize', out == 'result')
    check(f'{dim}D: on_frame reached hooks.gauges at every written time, '
          f'the first despite the last run\'s stamp',
          phases.count('on_frame') == 3, str(phases))
    check(f'{dim}D: tail_live reached hooks.gauges with each live frame',
          phases.count('tail_live') == 2, str(phases))
    check(f'{dim}D: the payload times are an ndarray',
          bool(got) and all(isinstance(p['times'], np.ndarray)
                            for _ph, p in got))
    check(f'{dim}D: every live probe read is quiet (no stderr per read)',
          calls['n'] > 0 and calls.get('loud', 0) == 0, str(calls))
    if dim == 1:
        info = next((m[1] for m in list(q.queue)
                     if m[0] == 'run_started'), {})
        check('1D run_started: the kept gauges by entered number, the '
              'dropped one apart (L3)',
              [g[0] for g in info.get('gauges', [])] == [1, 2]
              and [g[0] for g in info.get('gauges_dropped', [])] == [3],
              f"{info.get('gauges')} {info.get('gauges_dropped')}")

    # the real GuiHooks queue, drained into the window: only its gauge
    # posts (the rest belongs to a run the window did not start)
    keep = []
    while True:
        try:
            m = q.get_nowait()
        except queue.Empty:
            break
        if m[0] == 'gauges':
            keep.append(m)
    for m in keep:
        q.put(m)
    rp = win.run_panel
    rp.set_gauge_case(case)             # the column reads this stage's case
    rp.show_gauges_tab()                # the pane that raised on ndarrays
    pump(30)
    before = rp.log_text()
    ctrl = win.ctrl
    saved_w = ctrl.worker
    ctrl.worker = type('W', (), dict(q=q, hooks=hooks))()
    try:
        ctrl._drain()
    finally:
        ctrl.worker = saved_w
    pump(50)
    new = rp.log_text()[len(before):]
    check(f'{dim}D: drained into the window with no `{UI_ERR}` log',
          bool(keep) and UI_ERR not in new, repr(new[:200]))
    check(f'{dim}D: the Gauges page drew the ndarray payload',
          rp.gauges.n_points() == len(got[-1][1]['times']) if got else False,
          f'{rp.gauges.n_points()}')
    rp.show_slice_tab()
    pump(20)


def main():
    from blastlab.ui.testing import ensure_qapp, pump, use_model
    ensure_qapp()
    from blastlab.ui.app import MainWindow
    crashes = []
    sys.excepthook = lambda *a: crashes.append(a)
    win = MainWindow()
    use_model(win, name='D6_live_gauges')
    win.show()
    pump(200)
    try:
        l1_native_1d(win, pump)
        l2_foam(win, pump, 1)
        l2_foam(win, pump, 2)
    finally:
        check('nothing raised', not crashes, str(crashes[:1]))
        sys.excepthook = sys.__excepthook__
        win.close()
        pump(100)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'UI LIVE GAUGES 1D: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
