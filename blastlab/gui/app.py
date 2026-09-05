"""blastlab GUI main window: left sidebar (Setup | Run | Results |
Chain) + content stack, built with CustomTkinter."""

import os
import queue
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .. import __version__
from ..core.case import load_case, save_case, validate_case
from ..core.profiles import save_profile, save_profile_2d
from ..output.animation import write_animation
from ..output.gauges import save_gauges_1d, save_gauges_2d, save_gauges_3d
from ..viz3d import MISSING_MSG, pyvista_available
from . import theme
from .chain_panel import ChainPanel
from .forms import SetupPanel
from .results_panel import ResultsPanel
from .run_panel import RunPanel
from .theme import GAP, PAD, Card, c, icon
from .worker import SolverWorker

_LOGO = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), 'logo.gif')

_TB_HEADER = 'Traceback (most recent call last):'
_TB_CHAIN = (
    'During handling of the above exception, another exception occurred:',
    'The above exception was the direct cause of the following exception:')


def _error_headline(text):
    """The exception headline out of a traceback: the first non-empty
    line that is not the traceback header, a chaining separator, or an
    indented frame/source line.

    Deliberately not `splitlines()[-1]`: a foam failure carries its own
    multi-line message (FoamStageError appends the solver log tail), so
    the last line is an arbitrary line of blastFoam output instead of
    the "RuntimeError: blastFoam failed (exit 1) - case kept at ..."
    the user actually needs."""
    lines = [ln.rstrip() for ln in str(text).splitlines() if ln.strip()]
    for line in lines:
        if (line.startswith((' ', '\t')) or line.strip() == _TB_HEADER
                or line.strip() in _TB_CHAIN):
            continue
        return line
    return lines[-1] if lines else str(text).strip()


def _solve_stage(dim, case):
    """Return (label, solve_callable(hooks) -> Result) for a case; the
    callable also writes the case's own output files (gauges, animation,
    profile) exactly like the CLI flow does."""
    backend = getattr(case, 'solver', 'native')

    def solve(hooks):
        from ..solvers import get_solver
        res = get_solver(dim, backend)(case, hooks)
        if dim == 1:
            if case.gauge_radii:
                save_gauges_1d(res.gauges, case.gauge_file)
            if case.profile_file:
                save_profile(res.meta['final_profile'], case.profile_file)
        elif dim == 2:
            if case.gauges:
                save_gauges_2d(res.gauges, case.gauge_file)
            if case.anim_file and res.meta.get('frames'):
                write_animation(res.meta, case.anim_file)
            if case.profile_file:
                save_profile_2d(res.meta, case.profile_file)
        else:
            if case.gauges:
                save_gauges_3d(res.gauges, case.gauge_file)
            if case.anim_file and res.meta.get('frames'):
                write_animation(res.meta, case.anim_file)
        return res
    label = f'{dim}D' + (' blastFoam' if backend == 'blastfoam' else '')
    return (label, solve)


class App:
    #: Per-run outcome flags, reset by _start and set from the drained
    #: 'result'/'error' messages: only a run that finished on its own
    #: terms gets its progress bar filled to 100% on 'done'. Class-level
    #: so a partially constructed App (tests drive _drain directly) has
    #: them too.
    _run_stopped_early = False
    _run_errored = False
    #: True from _start until the drain sees the worker's 'done'
    _drain_pending = False

    def __init__(self, root, case_file=None):
        self.root = root
        root.title(f'blastlab {__version__}')
        root.geometry('1280x840')
        try:
            root.minsize(1100, 720)
        except Exception:
            pass
        try:                                   # ctk.CTk root
            root.configure(fg_color=theme.c('bg'))
        except Exception:                      # plain tk.Tk (tests)
            root.configure(bg=theme.cur('bg'))
        root.protocol('WM_DELETE_WINDOW', self._on_close)
        theme.apply_ttk_style(root)

        self.worker = None
        self._run_count = 0
        self._stage_dims = []
        self._validate_job = None

        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)
        self._build_sidebar(root)

        content = ctk.CTkFrame(root, fg_color='transparent')
        content.grid(row=0, column=1, sticky='nsew',
                     padx=(0, PAD), pady=PAD)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self.setup = SetupPanel(content, on_change=self._schedule_validate)
        self.run_panel = RunPanel(content, on_run=self._run_single,
                                  on_stop=self._stop,
                                  on_view3d=self._open_view3d,
                                  on_init=self._init_model,
                                  on_exec=self._exec,
                                  on_refresh=self._apply_refresh)
        self.results = ResultsPanel(content, log_fn=self._log_threadsafe)
        # N8: sweep old/large WSL run dirs per the persisted settings,
        # off-thread (WSL round trips must never block the window)
        from ..solvers.foam import env as foam_env
        from . import settings as gui_settings
        self._cleanup_thread = foam_env.start_auto_cleanup(
            gui_settings.load(), self._log_threadsafe)
        self.chain = ChainPanel(content, on_run_chain=self._run_chain)

        self._panels = {'setup': self.setup, 'run': self.run_panel,
                        'results': self.results, 'chain': self.chain}
        for panel in self._panels.values():
            panel.grid(row=0, column=0, sticky='nsew')
        self._show('setup')

        self._schedule_validate()

        if case_file:
            self._open_case(case_file)

    # ── sidebar / navigation ─────────────────────────────────────────────
    def _build_sidebar(self, root):
        side = ctk.CTkFrame(root, width=216, corner_radius=0,
                            fg_color=c('bg'))
        side.grid(row=0, column=0, sticky='nsw')
        side.grid_propagate(False)
        side.pack_propagate(False)

        # logo (falls back to a text title if the file is missing)
        if os.path.exists(_LOGO):
            from PIL import Image, ImageTk
            img = Image.open(_LOGO).convert('RGBA')
            w = 184
            h = max(1, round(img.height * w / img.width))
            logo = ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
            ctk.CTkLabel(side, image=logo, text='').pack(pady=(PAD, 2))
            try:
                self._icon_img = ImageTk.PhotoImage(
                    img.resize((64, max(1, round(img.height * 64
                                                 / img.width))),
                               Image.LANCZOS))
                root.iconphoto(True, self._icon_img)
            except Exception:
                pass
        else:
            ctk.CTkLabel(side, text='blastlab', font=theme.F_H1,
                         text_color=c('text')).pack(pady=(PAD, 2))
        ctk.CTkLabel(side, text=f'v{__version__}', font=theme.F_SMALL,
                     text_color=c('muted')).pack(pady=(0, PAD))

        self._nav_btns = {}
        for key, label, ic in (('setup', 'Setup', 'sliders'),
                               ('run', 'Run', 'play'),
                               ('results', 'Results', 'chart'),
                               ('chain', 'Chain', 'chain')):
            b = ctk.CTkButton(
                side, text=label, image=icon(ic, 17), compound='left',
                anchor='w', font=theme.F_BODY, corner_radius=theme.RADIUS,
                height=40, fg_color='transparent', hover_color=c('card'),
                text_color=c('text'),
                command=lambda k=key: self._show(k))
            b.pack(fill='x', padx=12, pady=3)
            self._nav_btns[key] = b

        # bottom block: case files, appearance, credit
        bottom = ctk.CTkFrame(side, fg_color='transparent')
        bottom.pack(side='bottom', fill='x', pady=(0, 12))
        for label, ic, cmd in (('Open case…', 'folder',
                                self._open_case),
                               ('Save case…', 'save',
                                self._save_case)):
            ctk.CTkButton(bottom, text=label, image=icon(ic, 15),
                          compound='left', anchor='w', font=theme.F_BODY,
                          corner_radius=theme.RADIUS, height=36,
                          fg_color='transparent', hover_color=c('card'),
                          text_color=c('muted'),
                          command=lambda f=cmd: f()).pack(
                fill='x', padx=12, pady=2)

        self._mode_switch = ctk.CTkSwitch(
            bottom, text='Dark mode', font=theme.F_BODY,
            text_color=c('muted'), progress_color=c('accent'),
            command=self._toggle_mode)
        self._mode_switch.pack(anchor='w', padx=24, pady=(10, 6))
        if ctk.get_appearance_mode() == 'Dark':
            self._mode_switch.select()

        ctk.CTkLabel(bottom, text='By Ofek Rotem', font=theme.F_SMALL,
                     text_color=c('muted')).pack(pady=(4, 2))

    def _show(self, key):
        self._panels[key].tkraise()
        for k, b in self._nav_btns.items():
            active = (k == key)
            b.configure(fg_color=c('card') if active else 'transparent',
                        text_color=c('accent') if active else c('text'))

    def _toggle_mode(self):
        ctk.set_appearance_mode('dark' if self._mode_switch.get()
                                else 'light')
        theme.apply_ttk_style(self.root)
        theme.refresh_embedded()
        try:
            self.root.configure(fg_color=theme.c('bg'))
        except Exception:
            self.root.configure(bg=theme.cur('bg'))

    # ── case files ───────────────────────────────────────────────────────
    def _open_case(self, path=None):
        path = path or filedialog.askopenfilename(
            filetypes=[('blastlab case', '*.json'), ('All files', '*.*')])
        if not path:
            return
        try:
            case = load_case(path)
        except Exception as exc:
            messagebox.showerror('Open case', str(exc))
            return
        self.setup.set_case(case)
        self._show('setup')

    def _save_case(self):
        try:
            case = self.setup.get_case()
        except ValueError as exc:
            messagebox.showerror('Save case', str(exc))
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.json',
            filetypes=[('blastlab case', '*.json')])
        if path:
            save_case(case, path)

    # ── live validation ──────────────────────────────────────────────────
    def _schedule_validate(self):
        if self._validate_job is not None:
            self.root.after_cancel(self._validate_job)
        self._validate_job = self.root.after(300, self._validate)

    def _validate(self):
        self._validate_job = None
        try:
            case = self.setup.get_case()
        except ValueError as exc:
            self.setup.show_report(errors=[str(exc)])
            self.setup.update_preview(None)
            return
        if getattr(case, 'solver', 'native') == 'blastfoam':
            # warm the cached WSL availability check off-thread so the
            # validation report can show it without ever blocking
            from ..solvers.foam import env as foam_env
            foam_env.ensure_check_started()
        rep = validate_case(case)
        extra = []
        if rep.n_cells:
            line = f'~{rep.n_cells:,} cells at dx = {rep.effective_dx:g} m'
            if getattr(rep, 'amr_levels', 0):
                line += (f' at t = 0; AMR up to level {rep.amr_levels} '
                         f'(finest {rep.dx_fine:g} m), displayed at level '
                         f'{rep.display_level} ({rep.n_fine:,} cells)')
            elif getattr(rep, 'lmax', 0):
                line += (f' (finest {rep.dx_fine:g} m, {rep.n_fine:,} '
                         f'display cells)')
            extra.append(line)
        self.setup.show_report(rep.errors, rep.warnings, rep.notes + extra)
        self.setup.update_preview(case)

    # ── running ──────────────────────────────────────────────────────────
    def _run_single(self, paused=False):
        try:
            case = self.setup.get_case()
        except ValueError as exc:
            messagebox.showerror('Run', str(exc))
            return
        rep = validate_case(case)
        if not rep.ok:
            messagebox.showerror('Run', '\n'.join(rep.errors))
            return
        self._start([(case.dim, case)], paused=paused)

    def _init_model(self):
        """VIPER-style 'Initialise Model': start the run held at step 0
        so the initial field is visible; Exec buttons advance it."""
        self._run_single(paused=True)

    def _run_chain(self, dim_cases, workspace):
        self._start(dim_cases)
        self._show('run')

    def _start(self, dim_cases, paused=False):
        # `is_alive()` alone leaves a ~50 ms window after the worker exits
        # but before the drain sees its 'done': starting there would
        # orphan the old queue and drop its finished result (G5)
        if self._drain_pending or (self.worker is not None
                                   and self.worker.is_alive()):
            messagebox.showinfo('Run', 'A run is already in progress.')
            return
        self._drain_pending = True
        self._run_count += 1
        self._run_stopped_early = self._run_errored = False
        self._stage_dims = [dim for dim, _ in dim_cases]
        stages = [_solve_stage(dim, case) for dim, case in dim_cases]
        self.worker = SolverWorker(stages)
        # 3D runs attach the embedded 3D view automatically at run start
        self.worker.hooks.auto3d = pyvista_available()
        self._apply_refresh()
        if paused:
            self.worker.hooks.set_exec('pause')
        self.run_panel.set_running(True)
        self.chain.set_running(True)
        # after set_running: it clears the log pane, which used to wipe
        # this hint the instant it was written (the user saw a held run,
        # an empty log and a 0% bar with no explanation)
        if paused:
            self.run_panel.on_log('  [model initialised - use the Exec '
                                  'buttons to advance]')
        self._show('run')
        self.worker.start()
        self.root.after(50, self._drain)

    def _stop(self):
        if self.worker is not None:
            self.worker.stop()
            self.run_panel.on_log('  [stop requested - finishing the '
                                  'current step]')

    def _exec(self, cmd):
        """Stepped-execution buttons: 'run', 'pause' or a step count."""
        w = self.worker
        if w is None or not w.is_alive():
            return
        w.hooks.set_exec(cmd)
        label = {'run': 'free running', 'pause': 'interrupted'}.get(
            cmd, f'executing {cmd} step(s)')
        self.run_panel.on_log(f'  [{label}]')

    def _refresh_policy(self):
        """Parse the Run tab's refresh input: ('seconds', s) or
        ('steps', n), or None for blank/invalid (= automatic)."""
        raw = self.run_panel.refresh_val.get().strip()
        if not raw:
            return None
        try:
            val = float(raw)
        except ValueError:
            return None
        if val <= 0:
            return None
        if self.run_panel.refresh_mode.get() == 'steps':
            return ('steps', max(1, int(round(val))))
        return ('seconds', val)

    def _apply_refresh(self):
        """Push the refresh policy into the live worker (also called at
        run start). Blank restores the automatic defaults."""
        w = self.worker
        if w is None:
            return
        pol = self._refresh_policy()
        if pol is None:
            w.hooks.refresh = type(w.hooks).refresh
            w.hooks.refresh3d = type(w.hooks).refresh3d
        else:
            w.hooks.refresh = pol
            w.hooks.refresh3d = pol

    # ── embedded 3D view (Run tab) ───────────────────────────────────────
    def _open_view3d(self):
        """'3D View' button: attach if auto-attach didn't, show the tab."""
        w = self.worker
        panel = self.run_panel.view3d
        if w is not None and w.is_alive() and w.hooks.scene3d is not None \
                and w.hooks.feed3d is None:
            try:
                feed = panel.prepare_live(w.hooks.scene3d)
                if feed is not None:
                    w.hooks.feed3d = feed
                    self.run_panel.on_log('  [3D view active - frames '
                                          'stream while the solver runs]')
            except Exception as exc:
                self.run_panel.on_log(f'  [3D view failed: {exc}]')
                return
        self.run_panel.show_3d_tab()

    def _attach_view3d_auto(self):
        """Auto-attach at run start: GuiHooks already built the Feed3D
        on the solver thread; build the Tk-side scene from its init."""
        w = self.worker
        if w is None or w.hooks.feed3d is None:
            return
        try:
            if self.run_panel.view3d.adopt_feed(w.hooks.feed3d):
                self.run_panel.on_log('  [3D view active - frames '
                                      'stream while the solver runs]')
            else:
                w.hooks.feed3d = None
        except Exception as exc:
            w.hooks.feed3d = None
            self.run_panel.on_log(f'  [3D view failed: {exc}]')

    def _finish_view3d(self, reason):
        if self.worker is not None and self.worker.hooks.feed3d is not None:
            self.worker.hooks.feed3d = None
            self.run_panel.view3d.on_done(reason)

    def _dispatch(self, w, msg):
        """Handle one worker-queue message. Raises propagate to _drain,
        which logs them and keeps draining - a bad frame or a broken
        panel must never kill the polling loop mid-run."""
        tag = msg[0]
        if tag == 'log':
            self.run_panel.on_log(msg[1])
        elif tag == 'run_started':
            self.run_panel.on_run_started(msg[1])
            is3d = msg[1].get('scene3d') is not None
            if is3d and not pyvista_available():
                self.run_panel.on_log(f'  [{MISSING_MSG}]')
                is3d = False
            self.run_panel.enable_view3d(is3d)
            if is3d:
                self._attach_view3d_auto()
        elif tag == 'progress':
            self.run_panel.on_progress(msg[1])
        elif tag == 'frame':
            fr = w.hooks.latest_frame()
            if fr is not None:
                self.run_panel.on_frame(*fr)
        elif tag == 'frame3d':
            fr = w.hooks.latest_frame3d()
            if fr is not None:
                self.run_panel.view3d.on_frame(*fr)
        elif tag == 'stage':
            self.run_panel.on_log(f'=== Stage {msg[2]} ===')
        elif tag == 'result':
            k, res = msg[1], msg[2]
            dim = self._stage_dims[k]
            label = (f'Run {self._run_count} - {dim}D'
                     + (' (stopped)' if res.stopped_early else ''))
            self._run_stopped_early |= bool(res.stopped_early)
            self.results.add_result(label, dim, res)
            # the live viewer belongs to this stage: hand it its
            # playback mode (window stays open)
            self._finish_view3d(res.stop_reason)
        elif tag == 'error':
            self._run_errored = True
            self.run_panel.on_log(msg[1])
            messagebox.showerror(
                'Run failed',
                _error_headline(msg[1]) + '\n\nSee the run log for details.')
            self._finish_view3d('run failed')

    def _drain(self):
        w = self.worker
        if w is None:
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
                    import traceback
                    err = traceback.format_exc(limit=6)
                    try:
                        self.run_panel.on_log(
                            f"  [ui error handling '{msg[0]}']\n{err}")
                    except Exception:
                        print(err, file=sys.stderr)
        except queue.Empty:
            pass
        if done:
            self._drain_pending = False
            self.run_panel.set_running(False)
            self.chain.set_running(False)
            if not (self._run_stopped_early or self._run_errored):
                # the last progress message is often throttled away, so
                # a completed run would otherwise rest below 100%
                self.run_panel.mark_complete()
            self.run_panel.on_log('  [run finished]')
        else:
            self.root.after(50, self._drain)

    def _log_threadsafe(self, text):
        self.root.after(0, self.run_panel.on_log, str(text))

    # ── shutdown ─────────────────────────────────────────────────────────
    def _on_close(self):
        if self.worker is not None and self.worker.is_alive():
            self.worker.stop()
            self.worker.join(timeout=10)
        self.root.destroy()


def main(case_file=None):
    ctk.set_appearance_mode('dark')
    root = ctk.CTk()
    App(root, case_file=case_file)
    root.mainloop()


if __name__ == '__main__':
    main()
