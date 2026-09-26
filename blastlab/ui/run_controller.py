"""Runs solves for the Qt front-end and hands their messages to the
window.

`RunController` owns the `SolverWorker` (solvers/worker.py) and drains
its queue on a 50 ms QTimer - the queue and its latest-wins frame slots
are kept exactly as the Tk app used them; per-emit Qt signals from the
solver thread would undo that coalescing. Every message is dispatched
under an exception guard: a bad frame or a broken panel must never kill
the polling loop mid-run (the worker is still solving and the
'result' / 'done' messages must still arrive).

The window passes a `handlers` object with the panel-facing methods
(`on_log`, `on_run_started`, ...); tests drive `_drain()` with stubs.
3D frames never come through here: the solver thread publishes them into
a shared-memory ring the viewer child polls (see `view3d_host`).
"""

import queue
import sys
import traceback

from PySide6.QtCore import QObject, QTimer

# imported before any solve_stage(stage_dir=...): it registers the
# model-folder writer with solvers.jobs (OUT-1)
from ..services import model_folder
from ..solvers.jobs import resume_stage, solve_stage
from ..solvers.worker import SolverWorker
from ..viz3d import MISSING_MSG, pyvista_available
from . import dialogs

_TB_HEADER = 'Traceback (most recent call last):'
_TB_CHAIN = (
    'During handling of the above exception, another exception occurred:',
    'The above exception was the direct cause of the following exception:')


def error_headline(text):
    """The exception headline out of a traceback: the first non-empty
    line that is not the traceback header, a chaining separator, or an
    indented frame/source line (a foam failure carries a multi-line
    message, so the LAST line is arbitrary solver output)."""
    lines = [ln.rstrip() for ln in str(text).splitlines() if ln.strip()]
    for line in lines:
        if (line.startswith((' ', '\t')) or line.strip() == _TB_HEADER
                or line.strip() in _TB_CHAIN):
            continue
        return line
    return lines[-1] if lines else str(text).strip()


def parse_refresh(text, mode):
    """The Run tab's "Refresh every" box -> ('seconds', s) | ('steps', n)
    | None (blank/0 = automatic); raises ValueError when unusable."""
    text = str(text or '').strip()
    if not text:
        return None
    val = float(text)
    if val < 0:
        raise ValueError('negative')
    if val == 0:
        return None
    if mode == 'steps':
        n = int(round(val))
        if n < 1:
            raise ValueError('steps < 1')
        return ('steps', n)
    return ('seconds', val)


class _NoHandlers:
    """Every panel call is a no-op (the controller can run headless)."""

    def __getattr__(self, name):
        return lambda *a, **k: None


class RunController(QObject):
    DRAIN_MS = 50

    #: How a failed run is reported; injectable for the same reason the
    #: Tk app made it a static method - a modal stops an unattended
    #: driver dead. Resolved through `dialogs` at call time.
    show_error = staticmethod(lambda title, msg: dialogs.show_error(title, msg))

    def __init__(self, handlers=None, view3d=None, parent=None):
        super().__init__(parent)
        self.handlers = handlers if handlers is not None else _NoHandlers()
        self.view3d = view3d
        self.worker = None
        self._run_count = 0
        self._run_name = ''
        self._stage_dims = []
        self._run_stopped_early = False
        self._run_errored = False
        self._drain_pending = False
        self._done_seen = True
        self._refresh = None            # last accepted refresh policy
        self._model = None              # OUT-1: the run's model folder
        self._folders = {}              # stage_dir -> manifest
        self._timer = QTimer(self)
        self._timer.setInterval(self.DRAIN_MS)
        self._timer.timeout.connect(self._drain)

    # ── state ────────────────────────────────────────────────────────────
    @property
    def running(self):
        """True from the launch until the drain has consumed the worker's
        'done'. `_drain_pending` alone closes the ~50 ms window after the
        thread exits but before the drain sees 'done' (starting there
        would orphan the old queue and drop its finished result, G5);
        `is_alive()` is only the safety net for a worker that never got
        to post 'done', and it must not outvote a 'done' already seen -
        the thread can still be winding down for a few microseconds."""
        if self._drain_pending:
            return True
        if self._done_seen or self.worker is None:
            return False
        return self.worker.is_alive()

    # ── starting / stopping ──────────────────────────────────────────────
    def start_stages(self, dim_cases, paused=False, run_name='', model=None,
                     reports=None):
        """Run [(dim, case), ...] sequentially on a worker thread.
        Returns False when a run is already in progress.

        OUT-1: `model` is the prepared model folder
        (`model_folder.Target`); every stage writes into it - the folder
        itself for one stage, `<MODEL>\\<d>d` for a chain - and
        `reports` (the pre-flight ValidationReports, one per stage) feed
        its manifest. `model=None` is the headless / test path, which
        writes what it always did."""
        # `is_alive()` alone leaves a ~50 ms window after the worker
        # exits but before the drain sees its 'done': starting there
        # would orphan the old queue and drop its finished result (G5)
        if self.running:
            dialogs.show_info('Run', 'A run is already in progress.')
            return False
        dims = [dim for dim, _ in dim_cases]
        if model is None:
            stages = [solve_stage(dim, case) for dim, case in dim_cases]
        else:
            reports = list(reports or [None] * len(dim_cases))
            last = len(dim_cases) - 1
            # a chain stage before the last writes its hand-off, which
            # the Chain tab wired as its profile_file
            stages = [solve_stage(dim, case, stage_dir=sd,
                                  run_info=model_folder.run_info(
                                      model, case, rep,
                                      handoff=(case.profile_file
                                               if k < last else None)))
                      for k, ((dim, case), sd, rep) in enumerate(zip(
                          dim_cases, model_folder.stage_dirs(model, dims),
                          reports))]
        return self._launch(stages, dims, paused=paused, run_name=run_name,
                            model=model)

    def resume_foam_run(self, path, dim, run_name='', model=None, case=None):
        """Resume a stopped blastFoam run through the ordinary worker
        pipeline, so the Run tab, live view, Stop and Results all behave
        exactly as in a fresh run. With a `model` (and the run's own
        `case`) the resume writes the model folder and releases the WSL
        scratch like a fresh run (OUT-1)."""
        if self.running:
            dialogs.show_info('Run', 'A run is already in progress.')
            return False
        if model is None:
            stage = resume_stage(dim, path)
        else:
            stage = resume_stage(dim, path, case, stage_dir=model.folder,
                                 run_info=model_folder.run_info(model, case))
        return self._launch([stage], [dim], run_name=run_name, model=model)

    def _launch(self, stages, dims, paused=False, run_name='', model=None):
        self._drain_pending = True
        self._done_seen = False
        self._run_count += 1
        self._model = model
        self._folders = {}              # stage_dir -> manifest (OUT-1)
        # the name the user typed on the Run tab labels every result of
        # this run (and its exports) - blank keeps the old "Run N - 2D"
        self._run_name = str(run_name or '').strip()
        self._run_stopped_early = self._run_errored = False
        self._stage_dims = list(dims)
        self.worker = SolverWorker(stages)
        # 3D runs attach the embedded 3D view automatically at run start
        self.worker.hooks.auto3d = pyvista_available() and self.view3d is not None
        self.worker.hooks.live_gauges = getattr(self, '_live_gauges', False)
        self._push_refresh(self.worker.hooks)
        if paused:
            self.worker.hooks.set_exec('pause')
        self.handlers.on_running(True)
        # after on_running: it clears the log pane, which used to wipe
        # this hint the instant it was written
        if paused:
            self.handlers.on_log('  [model initialised - use the Exec '
                                 'buttons to advance]')
        self.worker.start()
        self._timer.start()
        return True

    def set_live_gauges(self, on):
        """Collect live gauge traces, or stop collecting them.

        Off by default and off again the moment the view is left: on a
        native run this copies the whole series on every live frame, and
        on a foam run it re-reads blastProbes' output from the disk WSL
        is solving on. Neither is worth paying for a pane nobody is
        looking at.
        """
        self._live_gauges = bool(on)
        if self.worker is not None:
            self.worker.hooks.live_gauges = self._live_gauges

    def stop(self):
        if self.worker is not None:
            self.worker.stop()
            self.handlers.on_log('  [stop requested - finishing the '
                                 'current step]')

    def exec_cmd(self, cmd):
        """Stepped execution: 1/10/100/1000 steps, 'run', 'pause'."""
        w = self.worker
        if w is None or not w.is_alive():
            return
        w.hooks.set_exec(cmd)
        self.handlers.on_log(
            '  [model held - Exec n / END continue it]' if cmd == 'pause'
            else '  [running to the end]' if cmd == 'run'
            else f'  [executing {int(cmd)} step(s)]')

    # ── live-view refresh policy ─────────────────────────────────────────
    def apply_refresh(self, text, mode):
        """Parse and push the refresh policy; returns True when the box
        was usable (blank = automatic)."""
        try:
            self._refresh = parse_refresh(text, mode)
            ok = True
        except ValueError:
            self._refresh = None
            ok = False
        w = self.worker
        if w is not None:
            self._push_refresh(w.hooks)
        return ok

    def _push_refresh(self, hooks):
        pol = self._refresh
        if pol is None:
            hooks.refresh = type(hooks).refresh
            hooks.refresh3d = type(hooks).refresh3d
        else:
            hooks.refresh = pol
            hooks.refresh3d = pol

    # ── embedded 3D view ─────────────────────────────────────────────────
    def open_view3d(self):
        """'3D View' button: attach if auto-attach didn't; True when a
        scene is (now) attached."""
        w = self.worker
        v = self.view3d
        if v is None:
            return False
        if w is not None and w.is_alive() and w.hooks.scene3d is not None \
                and w.hooks.feed3d is None:
            got = v.prepare_live(w.hooks.scene3d)
            if got is not None:
                feed, ring = got
                w.hooks.ring = ring
                w.hooks.feed3d = feed
                self.handlers.on_log('  [3D view active - frames stream '
                                     'while the solver runs]')
        return v.has_scene

    def _attach_view3d_auto(self, info):
        """Auto-attach at run start: GuiHooks already built the Feed3D on
        the solver thread; build the ring and hand the viewer the scene.
        Frames that landed in the slot before the ring existed are
        flushed into it."""
        w = self.worker
        v = self.view3d
        if w is None or v is None or w.hooks.feed3d is None:
            return
        try:
            from .view3d_host import make_ring
            ring = make_ring(w.hooks.feed3d, info.get('scene3d'))
            if not v.adopt_feed(w.hooks.feed3d, ring):
                ring.close(unlink=True)
                w.hooks.feed3d = None
                return
            w.hooks.ring = ring
            fr = w.hooks.latest_frame3d()
            if fr is not None:
                ring.write(fr[0], fr[1], final=fr[2])
            self.handlers.on_log('  [3D view active - frames stream '
                                 'while the solver runs]')
        except Exception as exc:
            w.hooks.feed3d = None
            w.hooks.ring = None
            self.handlers.on_log(f'  [3D view failed: {exc}]')

    def _finish_view3d(self, reason):
        w = self.worker
        if w is not None and w.hooks.feed3d is not None:
            w.hooks.feed3d = None
            w.hooks.ring = None
            if self.view3d is not None:
                self.view3d.on_done(reason)

    # ── queue drain ──────────────────────────────────────────────────────
    def _dispatch(self, w, msg):
        """Handle one worker-queue message. Raises propagate to _drain,
        which logs them and keeps draining."""
        h = self.handlers
        tag = msg[0]
        if tag == 'log':
            h.on_log(msg[1])
        elif tag == 'run_started':
            info = msg[1]
            h.on_run_started(info)
            is3d = info.get('scene3d') is not None
            if is3d and not pyvista_available():
                h.on_log(f'  [{MISSING_MSG}]')
                is3d = False
            h.on_view3d_available(is3d)
            if is3d:
                self._attach_view3d_auto(info)
        elif tag == 'cadence':
            h.on_cadence(msg[1], msg[2])
        elif tag == 'progress':
            h.on_progress(msg[1])
        elif tag == 'paused':
            h.on_paused(bool(msg[1]))
        elif tag == 'frame':
            fr = w.hooks.latest_frame()
            if fr is not None:
                h.on_frame(*fr)
        elif tag == 'surf3d':
            got = w.hooks.latest_surf3d()
            if got is not None and self.view3d is not None:
                self.view3d.on_sampled_plane(*got)
        elif tag == 'gauges':
            payload = w.hooks.latest_gauges()
            if payload is not None:
                h.on_gauges(payload)
        elif tag == 'frame3d':
            # Tk-era token: only reached when no ring exists (e.g. the
            # viewer was refused); the slot is simply drained
            w.hooks.latest_frame3d()
        elif tag == 'stage':
            h.on_log(f'=== Stage {msg[2]} ===')
        elif tag == 'folder':
            # OUT-1: the stage's model folder is written; a finished
            # blastFoam run whose WSL scratch had to be kept says why
            stage_dir, manifest, notice = msg[1], msg[2], msg[3]
            self._folders[stage_dir] = manifest
            if notice:
                self.show_error('Model folder', notice)
        elif tag == 'result':
            k, res = msg[1], msg[2]
            dim = self._stage_dims[k] if k < len(self._stage_dims) else 0
            name = self._run_name
            label = ((f'{name} - {dim}D' if name
                      else f'Run {self._run_count} - {dim}D')
                     + (' (stopped)' if res.stopped_early else ''))
            if name:
                res.meta['name'] = name
            self._run_stopped_early |= bool(res.stopped_early)
            h.on_result(k, dim, label, res)
            # the live viewer belongs to this stage: hand it its playback
            # mode. In a chain, only the LAST stage finalizes it - an
            # earlier stage would tear the view down just as the next
            # stage rebuilds it. The final 'done' finalizes whatever is
            # left (idempotent).
            if k == len(self._stage_dims) - 1:
                self._finish_view3d(res.stop_reason)
        elif tag == 'error':
            self._run_errored = True
            h.on_log(msg[1])
            self.show_error('Run failed', error_headline(msg[1])
                            + '\n\nSee the run log for details.')
            self._finish_view3d('run failed')

    def _drain(self):
        w = self.worker
        if w is None:
            self._timer.stop()
            return
        done = False
        try:
            while True:
                msg = w.q.get_nowait()
                if msg[0] == 'done':
                    done = True
                    continue
                try:
                    self._dispatch(w, msg)
                except Exception:
                    # keep draining: the worker is still solving and the
                    # 'result'/'done' messages must still be received
                    err = traceback.format_exc(limit=6)
                    try:
                        self.handlers.on_log(
                            f"  [ui error handling '{msg[0]}']\n{err}")
                    except Exception:
                        print(err, file=sys.stderr)
        except queue.Empty:
            pass
        if done:
            self._timer.stop()
            self._drain_pending = False
            self._done_seen = True
            # finalize the embedded 3D view if the last stage's 'result'
            # did not (idempotent: no-op when there is no live feed)
            self._finish_view3d('run complete')
            self._write_chain_manifest()
            self.handlers.on_running(False)
            self.handlers.on_finished(self._run_stopped_early,
                                      self._run_errored)
            self.handlers.on_log('  [run finished]')

    def _write_chain_manifest(self):
        """A chain's root manifest.json, at 'done' (OUT-1, plan sec.
        2.2): the stages that wrote a folder and the hand-offs at the
        model root."""
        model = getattr(self, '_model', None)
        if model is None or len(self._stage_dims) < 2:
            return
        err = model_folder.write_chain_root(model, self._stage_dims,
                                            self._folders)
        if err:
            self.handlers.on_log(f'  [warn] model folder: could not write '
                                 f'the chain manifest.json: {err}')

    # ── shutdown ─────────────────────────────────────────────────────────
    def shutdown(self, join_s=10.0):
        self._timer.stop()
        if self.worker is not None and self.worker.is_alive():
            self.worker.stop()
            self.worker.join(timeout=join_s)
