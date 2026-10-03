"""Where the embedded 3D viewer really is while the window changes around
it: a Win32 sampler, committed so the verifier can re-run it.

Batch 2026-09-29-gui-results T4 (GUI-7), after F13: the Win32 samplers of
GUI-6 were implementers' scratch and were lost. CLAUDE.md 8.7: measure
with the real component on a real platform, and measure the longest
unbroken stretch during which a visible window is somewhere wrong - "it
ends up in the right place" is not the bar.

It builds the real MainWindow (throwaway settings), solves a tiny native
3D case (the Phase 0 3D case of test_char_native_api, 64 k cells), feeds
it to the chosen surface's embedded viewer - the REAL viewer child
process - and then, for each action, samples every <= 2 ms with ctypes,
from a sampling process of its own (`--child`; a thread was starved by
the GIL for up to 355 ms, and a GUI-thread loop never sees a state that
lives inside one event-loop pass - it read 0 ms for a 36 ms resize lag):
`GetWindowRect` / `GetParent` / `IsWindowVisible` of the viewer's HWND
against `GetWindowRect` of its card (the host's native container). A
sample is WRONG when the viewer window is visible and reaches outside
its card by more than TOL px on any side (both rects in physical
pixels, from Win32); `mismatch` also counts a window smaller than its
card (View3DHost.shrink_ahead makes one on purpose).

Per action it writes: samples, samples with a viewer window, the longest
wrong-place stretch (ms), the worst offset (px past each card edge), the
longest mismatch stretch, and whether the window stayed a child of its
card.

  --surface results|run|setup   which embedded viewer (default results)
  --actions a,b,...             open3d, views (the Results view tabs,
                                every one in turn, 3D last), select,
                                busy, stage, tabs, theme, resize
                                (default: all that apply); an
                                action the code under test lacks (a base
                                worktree) is reported as unavailable.
                                GUI-9 (batch 2026-09-29-gui-chain T6, the
                                rules in docs/qa/2026-09-29-gui-chain/
                                measurements-9b.md): chainsel (results:
                                a chain whose 3D stage is selected <-> a
                                plain 3D entry, the STAGE tabs appear and
                                go), stagetabs (results: the tabs 3D ->
                                1D -> 3D), chainstrip (run: the chain
                                strip shown / stage_started(1) / hidden),
                                chaintab (setup: Chain -> Setup),
                                chainresize (results, a chain selected)
                                and stripresize (run, the strip shown):
                                `resize` with the new widget on screen
  --repeat N                    repeats per action (default 3)
  --out file.json               where to write the numbers

Real platform only: offscreen it prints SKIP and exits 0. At the end it
stops ITS OWN viewer child, by PID.

Run:  cd blastlab/tests && python -u _e2e_ui_viewer_place.py --out v.json
"""
import argparse
import ctypes
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))

#: px a window may stand past its card before a sample counts as wrong
TOL = 2
#: how long each step of an action is watched
WATCH_MS = 700
#: the sampling period (<= 2 ms, plan T4)
PERIOD_S = 0.0015

ACTIONS = ('open3d', 'views', 'select', 'busy', 'stage', 'tabs', 'theme',
           'resize', 'chainsel', 'stagetabs', 'chainstrip', 'chaintab',
           'chainresize', 'stripresize')


class _RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


def win32_rect(hwnd):
    r = _RECT()
    ctypes.windll.user32.GetWindowRect(ctypes.c_void_p(hwnd),
                                       ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def win32_parent(hwnd):
    return ctypes.windll.user32.GetParent(ctypes.c_void_p(hwnd))


def win32_visible(hwnd):
    return bool(ctypes.windll.user32.IsWindowVisible(ctypes.c_void_p(hwnd)))


def git_head():
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                              cwd=REPO, capture_output=True, text=True,
                              timeout=10).stdout.strip() or '?'
    except Exception:
        return '?'


def private_settings():
    d = tempfile.mkdtemp(prefix='blastlab_vplace_')
    path = os.path.join(d, 'settings.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'auto_cleanup': False,
                   'runs_dir': os.path.join(d, 'runs')}, f)
    os.environ['BLASTLAB_SETTINGS'] = path
    return d


def sample(hwnd, card):
    """(visible, px past the card or 0, mismatch, is_child, past) - Win32
    only, so it is safe off the GUI thread."""
    if not hwnd or not card:
        return False, 0, False, False, (0, 0, 0, 0)
    vis = win32_visible(hwnd)
    w, c = win32_rect(hwnd), win32_rect(card)
    # px past each card edge: left, top, right, bottom
    past = (c[0] - w[0], c[1] - w[1], w[2] - c[2], w[3] - c[3])
    worst = max(past)
    mismatch = max(abs(a - b) for a, b in zip(w, c)) > TOL
    return (vis, worst if vis else 0, vis and mismatch,
            win32_parent(hwnd) == card, past)


def child_main(hwnd, card):
    """`--child HWND CARD`: sample in a process of its own until stdin
    says `stop`, then print the rows as JSON. A process, not a thread:
    it shares no GIL with the GUI, so a long call there (a theme switch
    re-polishes every widget for hundreds of ms) cannot starve it - a
    thread measured gaps of 355 ms during a theme toggle."""
    import threading
    stop = []
    threading.Thread(target=lambda: (sys.stdin.readline(),
                                     stop.append(1)), daemon=True).start()
    rows = []
    print('ready', flush=True)
    while not stop:
        rows.append((time.perf_counter(),) + sample(hwnd, card))
        time.sleep(PERIOD_S)
    print(json.dumps(rows), flush=True)
    return 0


class Sampler:
    """Samples one viewer window against its card from a child process
    (Win32 calls only), so a wrong state that exists only inside one
    pass of the GUI thread's event loop - or inside one long call - is
    seen as well; the GUI thread meanwhile runs the action and pumps
    events. The child is ours and exits on `stop`."""

    def __init__(self, app, host):
        self.app = app
        self.host = host

    def card_hwnd(self):
        c = self.host._container
        return int(c.winId()) if c is not None else None

    def run(self, steps):
        """Run each step (a callable) on the GUI thread and watch after
        it, sampling in a child process throughout."""
        child = subprocess.Popen(
            [sys.executable, '-u', os.path.abspath(__file__), '--child',
             str(int(self.host._hwnd)), str(self.card_hwnd())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            child.stdout.readline()                   # 'ready'
            for step in steps:
                step()
                t0 = time.perf_counter()
                while (time.perf_counter() - t0) * 1000.0 < WATCH_MS:
                    self.app.processEvents()
                    time.sleep(0.001)
            child.stdin.write('stop\n')
            child.stdin.flush()
            rows = json.loads(child.stdout.readline())
            child.wait(timeout=10)
        finally:
            if child.poll() is None:
                child.kill()                          # ours, by handle
        return summarise(rows)


def summarise(rows):
    acc = dict(samples=len(rows), with_window=0, not_child=0,
               longest_wrong_ms=0.0, worst_offset_px=0,
               worst_past=[0, 0, 0, 0], longest_mismatch_ms=0.0,
               max_gap_ms=0.0)
    run0 = mrun0 = None
    prev = None
    for t, vis, worst, mism, child, past in rows:
        if prev is not None:
            acc['max_gap_ms'] = max(acc['max_gap_ms'], (t - prev) * 1000)
        prev = t
        if vis:
            acc['with_window'] += 1
            if not child:
                acc['not_child'] += 1
        if vis and worst > TOL:
            run0 = t if run0 is None else run0
            acc['longest_wrong_ms'] = max(acc['longest_wrong_ms'],
                                          (t - run0) * 1000)
            acc['worst_offset_px'] = max(acc['worst_offset_px'], worst)
            acc['worst_past'] = [max(a, b) for a, b in
                                 zip(acc['worst_past'], past)]
        else:
            run0 = None
        if mism:
            mrun0 = t if mrun0 is None else mrun0
            acc['longest_mismatch_ms'] = max(acc['longest_mismatch_ms'],
                                             (t - mrun0) * 1000)
        else:
            mrun0 = None
    for k in ('longest_wrong_ms', 'longest_mismatch_ms', 'max_gap_ms'):
        acc[k] = round(acc[k], 1)
    return acc


def self_test(app, host, sampler):
    """Proof that the sampler sees a misplaced window: move the render
    window 60 px right inside its card for ~150 ms (SetWindowPos, relative
    to the parent card), then let the host put it back. Returns the
    summary of that run; its longest wrong stretch must be ~150 ms."""
    SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x4, 0x10
    hwnd = host._hwnd

    def displace():
        ctypes.windll.user32.SetWindowPos(
            ctypes.c_void_p(hwnd), None, 60, 0, 0, 0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        t0 = time.perf_counter()
        while (time.perf_counter() - t0) < 0.15:
            time.sleep(0.001)                 # no event pump: it stays
        host.sync_foreign_geometry()
    return sampler.run([displace])


def tiny_3d():
    sys.path.insert(0, HERE)
    from test_char_native_api import CASES
    from blastlab.solvers import get_solver
    from blastlab.solvers.hooks import RunHooks
    case = CASES['3d']
    return get_solver(3, 'native')(case, RunHooks())


def tiny_1d():
    """GUI-9: the Phase 0 1D case, for a chain's first stage."""
    sys.path.insert(0, HERE)
    from test_char_native_api import CASES
    from blastlab.solvers import get_solver
    from blastlab.solvers.hooks import RunHooks
    return get_solver(1, 'native')(CASES['1d'], RunHooks())


def model_folder(res, root):
    """A copy of the result's meta pointing at a model folder with a
    MODEL.json and a manifest, so its method card has more rows."""
    import copy
    home = os.path.join(root, 'viewer_A')
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, 'MODEL.json'), 'w', encoding='utf-8') as f:
        json.dump({'schema': 'blastlab-case', 'dim': 3,
                   'solver': 'native', 'material': 'TNT'}, f)
    with open(os.path.join(home, 'manifest.json'), 'w',
              encoding='utf-8') as f:
        json.dump({'solver': 'native', 'n_procs': 1,
                   'created': '2026-09-29T10:00:00',
                   'finished': '2026-09-29T10:00:40'}, f)
    other = copy.copy(res)
    other.meta = dict(res.meta, model_dir=home)
    return other


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--surface', default='results',
                    choices=('results', 'run', 'setup'))
    ap.add_argument('--actions', default=','.join(ACTIONS))
    ap.add_argument('--repeat', type=int, default=3)
    ap.add_argument('--out', default='viewer_place.json')
    args = ap.parse_args()

    sys.path.insert(0, REPO)
    os.environ.pop('QT_QPA_PLATFORM', None)      # a real platform
    os.environ.setdefault('MPLBACKEND', 'Agg')
    root = private_settings()
    from PySide6.QtWidgets import QApplication, QLabel
    app = QApplication(['blastlab-viewer-place'])
    if app.platformName() == 'offscreen':
        print('SKIP: the offscreen platform cannot embed the viewer')
        return 0
    from blastlab.ui import theme
    theme.apply(app, 'dark')
    from blastlab.viz3d import pyvista_available
    if not pyvista_available():
        print('SKIP: pyvista is not installed (no viewer child)')
        return 0
    from blastlab.ui.app import MainWindow

    def settle(ms=300):
        t0 = time.perf_counter()
        while (time.perf_counter() - t0) * 1000 < ms:
            app.processEvents()
            time.sleep(0.005)

    print('solving the tiny native 3D case ...', flush=True)
    res = tiny_3d()
    res_a = model_folder(res, root)
    win = MainWindow()
    win.resize(1600, 1000)
    win.show()
    settle(500)
    rs = win.results
    ent_b = rs.add_result('viewer B (3D)', 3, res)
    ent_a = rs.add_result('viewer A (3D)', 3, res_a)
    settle(200)
    actions = [a.strip() for a in args.actions.split(',') if a]
    # GUI-9: a 1 -> 3 chain entry (a tiny native 1D result + this 3D
    # result) for the chain actions; entry A stays the one selected, as
    # without it. Code without chains (a base worktree): none.
    chain = None
    if args.surface == 'results' and hasattr(rs, 'start_chain') and any(
            a in ('chainsel', 'stagetabs', 'chainresize') for a in actions):
        print('solving the tiny native 1D case ...', flush=True)
        chain = rs.start_chain('viewer chain', [1, 3])
        rs.add_stage(chain, 'viewer chain - 1D', 1, tiny_1d())
        rs.add_stage(chain, 'viewer chain - 3D', 3, res)
        rs.sel.setCurrentIndex(rs.entries().index(ent_a))
        settle(200)

    if args.surface == 'results':
        win._show('results')
        settle(200)
        rs.open_3d()
        host = rs.view3d
    elif args.surface == 'run':
        win._show('run')
        settle(200)
        host = win.run_panel.view3d
        host.feed_result(res)
        win.run_panel._view_seg.set('3D view')
        win.run_panel._view_selected('3D view')
    else:
        win._show('setup')
        settle(200)
        win.setup.set_dim(3)
        win.setup.update_preview(win.setup.get_case())
        host = win.setup.view3d
    print('waiting for the viewer child ...', flush=True)
    for _ in range(9000):                       # pyvista + VTK + GL
        app.processEvents()
        time.sleep(0.01)
        if host is not None and host._hwnd and host._container is not None:
            break
    link = win.viewer_link
    pid = link._proc.pid if link._proc is not None else None
    out = dict(commit=git_head(), surface=args.surface,
               platform=app.platformName(), repeat=args.repeat,
               tol_px=TOL, watch_ms=WATCH_MS, viewer_pid=pid, actions={})
    if host is None or not host._hwnd:
        print('FAILED: the viewer child never reported a window')
        out['error'] = 'no viewer window'
    else:
        print(f'viewer child PID {pid}, render window {host._hwnd}',
              flush=True)
        settle(1500)
        s = Sampler(app, host)
        if args.surface == 'results':
            rs.show_view('3D')
            settle(500)
        st = self_test(app, host, s)
        out['self_test'] = st
        print(f'self-test: a 60 px displacement held ~150 ms reads '
              f'{st["longest_wrong_ms"]} ms / {st["worst_offset_px"]} px '
              f'(samples {st["samples"]}, max gap {st["max_gap_ms"]} ms)',
              flush=True)
        if st['longest_wrong_ms'] < 100 or st['worst_offset_px'] < 50:
            print('FAILED: the sampler did not see the displaced window')
            out['error'] = 'self-test failed'
        settle(500)
        surface = {'results': 'results', 'run': 'run',
                   'setup': 'setup'}[args.surface]

        def show_surface():
            win._show(surface)

        def steps_for(name):
            """The steps of one repeat of `name`, or None if the code
            under test does not have it."""
            if name == 'open3d':
                if args.surface != 'results':
                    return None

                def away():
                    rs.show_view('Fields' if 'Fields' in rs._views
                                 else list(rs._views)[0])
                away()
                settle(300)
                return [lambda: rs._view3d_btn.click()]
            if name == 'views':
                # GUI-7b: Field -> Gauges -> 3D (at base, the four old
                # tabs); the viewer is back on screen at the last step
                if args.surface != 'results':
                    return None
                names = [v for v in rs._views if v != '3D'] + ['3D']
                return [lambda v=v: rs.show_view(v) for v in names]
            if name == 'select':
                if args.surface != 'results':
                    return None
                ia, ib = (rs.entries().index(ent_a),
                          rs.entries().index(ent_b))
                return [lambda: rs.sel.setCurrentIndex(ib),
                        lambda: rs.sel.setCurrentIndex(ia)]
            if name == 'busy':
                if args.surface != 'results' or not hasattr(rs, '_set_busy'):
                    return None
                return [lambda: rs._set_busy('summary', True),
                        lambda: rs._set_busy('summary', False)]
            if name == 'stage':
                if args.surface != 'results' \
                        or not hasattr(rs, 'set_stage_strip'):
                    return None
                strip = QLabel('STAGE  1D | 2D | 3D')
                strip.setFixedHeight(32)
                return [lambda: rs.set_stage_strip(strip),
                        lambda: rs.set_stage_strip(None)]
            if name == 'tabs':
                order = [k for k in ('setup', 'run', 'results')
                         if k != surface] + [surface]
                return [lambda k=k: win._show(k) for k in order]
            if name == 'theme':
                act = win._dark_action
                return [lambda: act.setChecked(False),
                        lambda: act.setChecked(True)]
            if name == 'resize':
                return [lambda: win.resize(1100, 720),
                        lambda: win.resize(1600, 1000)]
            # ── GUI-9 (T6): the chain's new widgets above the viewer ──
            if name in ('chainsel', 'stagetabs', 'chainresize'):
                if args.surface != 'results' or chain is None:
                    return None
                ia = rs.entries().index(ent_a)
                ic = rs.entries().index(chain)
                if name == 'chainsel':
                    # from the plain entry A (no tabs) to the chain on its
                    # 3D stage (the tabs appear) and back (they go)
                    if rs.sel.currentIndex() != ia:
                        rs.sel.setCurrentIndex(ia)
                        settle(600)
                    chain.index = len(chain.stages) - 1
                    return [lambda: rs.sel.setCurrentIndex(ic),
                            lambda: rs.sel.setCurrentIndex(ia)]
                # the chain selected on its 3D stage, the tabs shown
                if rs.sel.currentIndex() != ic:
                    rs.sel.setCurrentIndex(ic)
                    settle(600)
                if rs.select_stage(3):
                    settle(300)
                if name == 'stagetabs':
                    tabs = rs.stage_tabs
                    return [lambda: tabs.button(1).click(),
                            lambda: tabs.button(3).click()]
                return [lambda: win.resize(1100, 720),
                        lambda: win.resize(1600, 1000)]
            if name in ('chainstrip', 'stripresize'):
                if args.surface != 'run':
                    return None
                try:
                    from blastlab.ui.chain_strip import ChainStrip
                except ImportError:
                    return None
                rp = win.run_panel
                strip = ChainStrip()
                strip.set_chain('viewer', [1, 2, 3])
                strip.arrange(rp.column_widths()[1])
                if name == 'chainstrip':
                    if rp.chain_strip() is not None:
                        rp.set_chain_strip(None)
                        settle(600)
                    return [lambda: rp.set_chain_strip(strip),
                            lambda: strip.stage_started(1),
                            lambda: rp.set_chain_strip(None)]
                rp.set_chain_strip(strip)
                settle(600)
                return [lambda: win.resize(1100, 720),
                        lambda: win.resize(1600, 1000)]
            if name == 'chaintab':
                if args.surface != 'setup':
                    return None
                return [lambda: win._show('chain'),
                        lambda: win._show('setup')]
            return None

        for name in actions:
            reps = []
            for _k in range(max(1, args.repeat)):
                show_surface()
                if args.surface == 'results' and name != 'open3d':
                    rs.show_view('3D')
                settle(400)
                steps = steps_for(name)
                if steps is None:
                    break
                reps.append(s.run(steps))
                settle(300)
            if not reps:
                out['actions'][name] = 'unavailable'
                print(f'{name:8s} unavailable here')
                continue
            longest = [r['longest_wrong_ms'] for r in reps]
            summary = dict(
                repeats=reps,
                samples=sum(r['samples'] for r in reps),
                with_window=sum(r['with_window'] for r in reps),
                not_child=sum(r['not_child'] for r in reps),
                longest_wrong_ms=max(longest),
                median_longest_wrong_ms=statistics.median(longest),
                worst_offset_px=max(r['worst_offset_px'] for r in reps),
                longest_mismatch_ms=max(r['longest_mismatch_ms']
                                        for r in reps))
            out['actions'][name] = summary
            print(f'{name:8s} samples {summary["samples"]:5d}  with window '
                  f'{summary["with_window"]:5d}  longest wrong '
                  f'{summary["longest_wrong_ms"]:6.1f} ms (median '
                  f'{summary["median_longest_wrong_ms"]:.1f})  worst '
                  f'{summary["worst_offset_px"]} px  mismatch '
                  f'{summary["longest_mismatch_ms"]:.1f} ms  not child '
                  f'{summary["not_child"]}  max gap '
                  f'{max(r["max_gap_ms"] for r in reps):.1f} ms', flush=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2)
    print(f'wrote {args.out}')
    # our own viewer child: its multiprocessing handle, so nothing but
    # that process can be stopped here (never a kill by name)
    child = getattr(link._proc, '_proc', None) if link._proc else None
    win.close()
    settle(500)
    if child is not None and child.is_alive():
        child.terminate()
        child.join(timeout=5)
        print(f'stopped viewer child {pid}')
    elif pid:
        print(f'viewer child {pid} closed with the window')
    return 1 if out.get('error') else 0


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--child':
        sys.exit(child_main(int(sys.argv[2]), int(sys.argv[3])))
    sys.exit(main())
