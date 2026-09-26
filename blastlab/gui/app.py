"""blastlab GUI main window: left sidebar (Setup | Run | Results |
Chain) + content stack, built with CustomTkinter."""

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .. import __version__
from ..core import hardware
from ..core.case import load_case, save_case, validate_case
from ..models.case import load_any_case
from ..solvers.foam import env as foam_env
# imported before any solve_stage(stage_dir=...): it registers the
# model-folder writer with solvers.jobs (OUT-1)
from ..services import model_folder
# moved to solvers/jobs.py (shared with the Qt front-end); the old names
# stay importable from here for the tests that use them
from ..solvers.jobs import resume_stage
from ..solvers.jobs import solve_stage as _solve_stage  # noqa: F401
from ..solvers.jobs import write_trigger_remap as _write_trigger_remap  # noqa: F401
from ..viz3d import MISSING_MSG, pyvista_available
from . import mode as mode_mod
from . import settings as gui_settings
from . import theme
from .chain_panel import ChainPanel
from .forms import SetupPanel
from .mode import SolverMode
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


def _warm_pyvista():
    """Import pyvista once, off the critical path (N2-12). Python caches
    the import forever after, so whichever code path touches pyvista
    next - the worker's auto3d, the embedded viewer, an export - finds
    it warm instead of paying the VTK avalanche mid-run."""
    try:
        import pyvista                                     # noqa: F401
    except Exception:
        pass          # viewer paths handle a missing pyvista themselves


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
    #: How a failed run is reported. Injectable for the same reason
    #: `run_browser` takes `confirm=`: `messagebox.showerror` is MODAL,
    #: so an unattended driver (_e2e_gui_*, _qa_gui_harness) that reaches
    #: it stops dead until someone clicks OK. A headless caller replaces
    #: this with a recorder and keeps going.
    #: Resolved through the module at CALL time, not bound here, so
    #: swapping `app.messagebox` wholesale still works - that is how
    #: test_gui_drain.py:241-242 stubs the dialog.
    show_error = staticmethod(
        lambda title, msg: messagebox.showerror(title, msg))
    #: OUT-1: the model-folder overwrite question; injectable like
    #: show_error, and resolved through the module at call time. No is
    #: the default button, as in the Qt dialog: Enter must not delete
    ask_yes_no = staticmethod(
        lambda title, msg: messagebox.askyesno(title, msg, default='no'))
    #: OUT-1: the run's model folder and its stages' manifests
    _model = None
    _folders = {}

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
        self._wsl_job = None

        # T34: the solver is an app-level mode. It is seeded from the
        # persisted settings BEFORE the sidebar and the panels exist, so
        # everything is built laid out for it (no flash, no double layout)
        st = gui_settings.load()
        self.solver_mode = SolverMode(st.get('solver', mode_mod.DEFAULT))
        # N17/T48: show last session's WSL hardware immediately; the
        # live probe (started with blastFoam mode) overwrites it.
        # N21: only when those numbers belong to THIS machine and are not
        # stale. A rejected cache leaves the hardware UNKNOWN, which now
        # means conservative caps until the probe lands - seconds, and
        # far better than sizing a run against another machine.
        self._prime_hardware_from(st)

        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)
        self._build_sidebar(root)

        content = ctk.CTkFrame(root, fg_color='transparent')
        content.grid(row=0, column=1, sticky='nsew',
                     padx=(0, PAD), pady=PAD)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self.setup = SetupPanel(content, on_change=self._schedule_validate,
                                mode=self.solver_mode)
        self.run_panel = RunPanel(content, on_run=self._run_single,
                                  on_stop=self._stop,
                                  on_view3d=self._open_view3d,
                                  on_init=self._init_model,
                                  on_exec=self._exec,
                                  on_refresh=self._apply_refresh,
                                  on_runs_dir=self._save_runs_dir)
        self.results = ResultsPanel(content, log_fn=self._result_msg,
                                    mode=self.solver_mode,
                                    on_resume=self._resume_foam_run)
        # N8: sweep old/large WSL run dirs per the persisted settings,
        # off-thread (WSL round trips must never block the window)
        self._cleanup_thread = foam_env.start_auto_cleanup(
            st, self._log_threadsafe)
        self.chain = ChainPanel(content, on_run_chain=self._run_chain,
                                mode=self.solver_mode,
                                model_source=lambda: (
                                    self.run_panel.current_runs_dir(),
                                    self.run_panel.current_run_name()))

        self._panels = {'setup': self.setup, 'run': self.run_panel,
                        'results': self.results, 'chain': self.chain}
        for panel in self._panels.values():
            panel.grid(row=0, column=0, sticky='nsew')
        # one status line for the whole window: exports, loads and solver
        # warnings used to land only in the Run tab's log, invisible to a
        # user standing on Results or Setup
        self._status = ctk.CTkLabel(root, text='', font=theme.F_SMALL,
                                    text_color=c('muted'), anchor='w')
        self._status.grid(row=1, column=1, sticky='we',
                          padx=(0, PAD), pady=(0, 6))
        self._status_job = None
        self._show('setup')
        self._restore_ui_state()
        self._bind_accelerators(root)

        # the panels are all built; from here on a mode change re-lays
        # them out. The first call fills the sidebar hints and schedules
        # the first validation.
        self.solver_mode.subscribe(self._on_solver_mode)
        self._on_solver_mode(self.solver_mode.get())

        if case_file:
            self._open_case(case_file)

        # N2-12: the first pyvista import is an avalanche of ~120 dynamic
        # C modules (VTK). It used to land mid-run - the worker's auto3d
        # path or the first viewer build triggered it - and C-extension
        # init holds the GIL, so the WINDOW froze for 11-13 s right after
        # the user clicked Run on a 3D case (D04 11.3 s, F06 10.9 s;
        # _run_single itself measured 57 ms). Warm it in a daemon thread
        # a second after launch instead: measured 652 ms when idle, and
        # the same click's worst event-loop gap drops 13,266 -> 2,795 ms
        # (the remainder is the viewer's own first build - N2-08).
        if pyvista_available():
            root.after(1000, lambda: threading.Thread(
                target=_warm_pyvista, name='pyvista-warm',
                daemon=True).start())
            # N2-08, stage two: the first pv.Plotter in a process pays
            # the cold GL-context / VTK-DLL cost (~1.3 s here - an RDP
            # session renders software GL). VTK rendering is main-thread
            # only, so this cannot ride the daemon; instead a throwaway
            # off-screen plotter is built and dropped at idle, ~3.5 s
            # after launch, while the user is still looking at the
            # window. Measured: the first real 3D feed then drops
            # 1,683 -> 980 ms, under the harness's 1,000 ms G4 budget
            # (the remainder is the per-result scene build; repeats are
            # ~165 ms).
            root.after(3500, self._prewarm_gl)
            # E06, stage three: the ~1 s "per-result scene build" the
            # stage-two note points at is NOT per-result - profiled, it
            # is the process-FIRST BlastScene.__init__ (809 of 924 ms:
            # first volume mapper / iso / lut construction under
            # software GL; the second scene costs 14 ms). An empty
            # plotter never touches those mappers, so stage two cannot
            # absorb it. Stage three builds a throwaway 4x4x4 BlastScene
            # at idle; the first real feed then drops ~980 -> ~130 ms.
            root.after(5200, self._prewarm_scene)

    def _prewarm_gl(self):
        """N2-08 stage two (see __init__): pay the process-first GL/VTK
        cost on a throwaway off-screen plotter at idle. Never competes
        with a live run, and any failure is silently irrelevant - the
        real viewer path pays its own way exactly as before."""
        if self.worker is not None and self.worker.is_alive():
            return
        try:
            import pyvista as pv
            pl = pv.Plotter(off_screen=True, window_size=(64, 64))
            pl.render()
            pl.screenshot(return_img=True)
            pl.close()
        except Exception:
            pass

    def _prewarm_scene(self):
        """E06 stage three (see __init__): pay the process-first
        BlastScene cost on a throwaway 4x4x4 scene at idle. Skipped when
        a run is live or a real scene already paid it."""
        if self.worker is not None and self.worker.is_alive():
            return
        view3d = getattr(getattr(self, 'results', None), 'view3d', None)
        if view3d is not None and getattr(view3d, '_scene', None) \
                is not None:
            return
        try:
            import numpy as np
            import pyvista as pv
            from ..viz3d.viewer import BlastScene
            from .view3d_panel import Feed3D, N_PLANES
            n = 4
            c = np.linspace(0.1, 0.7, n)
            feed = Feed3D(dict(
                x_c=c, y_c=c, z_c=c, dx=0.2,
                solid=np.zeros((n, n, n), dtype=bool), obstacles=[],
                Lx=0.8, Ly=0.8, Lz=0.8, charge_center=(0.4, 0.4, 0.4),
                r_exp=0.1, bcs={}, refine=None, solver=None))
            pl = pv.Plotter(off_screen=True, window_size=(64, 64))
            BlastScene(pl, feed.init, embedded=True, n_planes=N_PLANES)
            pl.render()
            pl.screenshot(return_img=True)
            pl.close()
        except Exception:
            pass

    # ── T34: app-level solver mode ───────────────────────────────────────
    @property
    def solver(self):
        return self.solver_mode.get()

    def set_solver(self, mode):
        """Public entry point (tests, the QA harness): the same as
        clicking the sidebar segment."""
        self.solver_mode.set(mode)

    def _solver_picked(self, label):
        self.solver_mode.set(mode_mod.from_label(label))

    def _on_solver_mode(self, m):
        # .set() on a CTkSegmentedButton does not fire its command, so
        # mirroring the mode into the segment cannot re-enter
        self._solver_seg.set(mode_mod.label(m))
        self._solver_hint.configure(text=mode_mod.EXPLAIN[m])
        self._cancel_wsl_poll()
        if m == 'blastfoam':
            # warm the cached WSL availability check off-thread and show
            # its outcome under the selector
            foam_env.ensure_check_started()
            self._probe_hw_async()
            self._poll_wsl()
        else:
            self._wsl_hint.configure(text='')
            theme.tooltip(self._wsl_hint, '')
        try:
            self._wsl_redetect.pack_configure()
            if m != 'blastfoam':
                self._wsl_redetect.pack_forget()
        except Exception:
            pass
        self._schedule_validate()

    def _hw_suffix(self):
        """" · 8 cores · 16 GB" from the cached probe (N17/T48). Empty
        while nothing is known - the line must never invent numbers."""
        hw = foam_env.hardware() or {}
        bits = []
        if hw.get('cores'):
            bits.append(f"{hw['cores']} cores")
        if hw.get('ram_gb'):
            bits.append(f"{hw['ram_gb']} GB VM")
        if not bits:
            return ' \u00b7 hardware unknown'
        if hw.get('ram_source') == hardware.CACHED:
            bits.append('cached')
        return ' \u00b7 ' + ' \u00b7 '.join(bits)

    def _hw_tooltip(self):
        """The long form of the same thing, for the hint's tooltip."""
        hw = foam_env.hardware() or {}
        if not hw.get('ram_gb') and not hw.get('cores'):
            return ('WSL has not answered the hardware probe. Cell caps '
                    'are conservative until it does - click Re-detect.')
        bits = [f"WSL VM: {hw.get('cores') or '?'} physical cores, "
                f"{hw.get('ram_gb') or '?'} GB"]
        host_ram = hardware.host().get('ram_gb')
        if host_ram:
            bits.append(f"Windows host: {host_ram} GB")
        stamp = gui_settings.load().get('hw_stamp')
        if stamp:
            bits.append(f"measured {str(stamp).replace('T', ' ')}")
        return '. '.join(bits) + '.'

    def _prime_hardware_from(self, st):
        """Seed the hardware caches from settings, but only when the
        saved numbers belong to this machine and are inside the TTL.

        Delegates: the CLI and plain scripts need the same thing, and
        when this lived only here every non-GUI caller sized its cases
        against the assumed 4 GB VM."""
        return foam_env.prime_from_settings(st)

    def _persist_hardware(self, hw):
        """Save ONLY what was measured this session.

        The old version wrote whatever `hardware()` returned, so a failed
        probe overwrote a good measurement with `hw_ram_gb=0` and a
        fabricated 4-core count - a plausible lie is worse than a gap.

        Delegates for the same reason as _prime_hardware_from."""
        return foam_env.persist_hardware(hw)

    def _probe_hw_async(self):
        """Probe the WSL VM's cores + RAM off-thread and persist them, so
        the next session can show the numbers before WSL is warm."""
        def work():
            try:
                hw = foam_env.hardware(probe=True) or {}
                hardware.detect_host_ram_gb()
            except Exception:
                return
            try:
                self._persist_hardware(hw)
            except Exception:
                pass
            try:
                self.root.after(0, self._poll_wsl)
                self.root.after(0, self._schedule_validate)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _redetect_hw(self):
        """Re-detect button: drop the cached probe, ask again, revalidate
        (the cell caps and the rank count both follow the hardware)."""
        foam_env.forget_hardware()
        try:
            self._wsl_hint.configure(text='WSL: detecting hardware\u2026',
                                     text_color=c('muted'))
        except Exception:
            pass
        self._probe_hw_async()

    def _poll_wsl(self):
        self._wsl_job = None
        try:
            st = foam_env.status()
            state, detail = (st if isinstance(st, tuple) else (st, ''))[:2]
        except Exception as exc:
            state, detail = 'fail', str(exc)
        detail = str(detail or '')
        if state == 'checking':
            text, colour = 'WSL: checking blastFoam…', c('muted')
        elif state == 'ok':
            suffix = self._hw_suffix()
            # N21: hardware still unknown while blastFoam itself is
            # ready is not an "all good" state - the caps are an
            # assumption, so the line says so in the warning colour
            colour = c('warn') if 'unknown' in suffix else c('ok')
            text = 'WSL: blastFoam ready' + suffix
        elif state == 'fail':
            text, colour = 'WSL: unavailable - ' + detail[:60], c('warn')
        else:
            text, colour = 'WSL: verified at run start', c('muted')
        try:
            self._wsl_hint.configure(text=text, text_color=colour)
            theme.tooltip(self._wsl_hint,
                          detail if state == 'fail'
                          else (self._hw_tooltip() if state == 'ok' else ''))
        except Exception:
            return
        if state == 'checking':
            self._wsl_job = self.root.after(1000, self._poll_wsl)

    def _cancel_wsl_poll(self):
        if self._wsl_job is not None:
            try:
                self.root.after_cancel(self._wsl_job)
            except Exception:
                pass
            self._wsl_job = None

    # ── G9: keyboard + persisted window state ────────────────────────────
    def _bind_accelerators(self, root):
        """Ctrl+O / Ctrl+S / F5 / Esc did nothing at all before."""
        for seq, fn in (('<Control-o>', lambda e: self._open_case()),
                        ('<Control-O>', lambda e: self._open_case()),
                        ('<Control-s>', lambda e: self._save_case()),
                        ('<Control-S>', lambda e: self._save_case()),
                        ('<F5>', lambda e: self._run_single()),
                        ('<Escape>', lambda e: self._stop())):
            try:
                root.bind_all(seq, fn)
            except Exception:
                pass

    def _restore_ui_state(self):
        """Window size, appearance mode and the refresh box, from the same
        json the foam cleanup policy lives in (they reset every launch)."""
        try:
            st = gui_settings.load()
            geo = str(st.get('geometry') or '')
            if 'x' in geo:
                self.root.geometry(geo)
            if str(st.get('appearance', 'dark')).lower() == 'light':
                if self._mode_switch.get():
                    self._mode_switch.deselect()
                self._toggle_mode()
            self.run_panel.refresh_val.set(str(st.get('refresh_value', '')))
            mode = str(st.get('refresh_mode', 'seconds'))
            if mode in ('seconds', 'steps'):
                self.run_panel.refresh_mode.set(mode)
            self.run_panel.set_runs_dir(st.get('runs_dir', ''))
        except Exception:
            pass

    def _save_runs_dir(self):
        """OUT-1: the Runs folder box is remembered across sessions."""
        try:
            gui_settings.update(runs_dir=self.run_panel.current_runs_dir())
        except Exception:
            pass

    def _save_ui_state(self):
        try:
            state = dict(
                appearance=('dark' if self._mode_switch.get() else 'light'),
                refresh_value=self.run_panel.refresh_val.get(),
                refresh_mode=self.run_panel.refresh_mode.get(),
                solver=self.solver_mode.get(),
                runs_dir=self.run_panel.current_runs_dir())
            # only a real, mapped window has a meaningful geometry: a
            # minimised or never-shown one reports the placeholder size
            geo = self.root.geometry()
            try:
                size = geo.split('+')[0]
                w, h = (int(v) for v in size.split('x'))
                mapped = (self.root.winfo_ismapped()
                          and self.root.state() == 'normal')
            except Exception:
                w = h = 0
                mapped = False
            if mapped and w >= 1100 and h >= 720:
                state['geometry'] = geo
            gui_settings.update(**state)
        except Exception:
            pass

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
            with Image.open(_LOGO) as _logo_file:   # else a ResourceWarning
                img = _logo_file.convert('RGBA')
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

        # T34: the solver is chosen here, once, for the whole app; every
        # tab hides what does not apply to it. Directly above Dark mode.
        blk = ctk.CTkFrame(bottom, fg_color='transparent')
        blk.pack(fill='x', padx=12, pady=(10, 2))
        ctk.CTkLabel(blk, text='Solver', font=theme.F_SMALL,
                     text_color=c('muted'), anchor='w').pack(fill='x',
                                                             padx=12)
        self._solver_seg = theme.segmented(
            blk, [mode_mod.label(m) for m in mode_mod.MODES],
            command=self._solver_picked, height=30, font=theme.F_SMALL)
        self._solver_seg.set(mode_mod.label(self.solver_mode.get()))
        self._solver_seg.pack(fill='x', padx=12, pady=(2, 4))
        # 216 px sidebar - 2 x (12 + 12) px padding = 168 px of text
        self._solver_hint = ctk.CTkLabel(
            blk, text='', font=theme.F_SMALL, text_color=c('muted'),
            anchor='w', justify='left', wraplength=160)
        self._solver_hint.pack(fill='x', padx=12)
        self._wsl_hint = ctk.CTkLabel(
            blk, text='', font=theme.F_SMALL, text_color=c('muted'),
            anchor='w', justify='left', wraplength=160)
        self._wsl_hint.pack(fill='x', padx=12, pady=(0, 2))
        # N17/T48: the hardware behind the rank/cap decisions, and a way
        # to re-probe it without restarting (a .wslconfig edit or a
        # `wsl --shutdown` changes both numbers under a running GUI)
        self._wsl_redetect = ctk.CTkButton(
            blk, text='Re-detect', width=70, height=18,
            font=theme.F_SMALL, fg_color='transparent',
            text_color=c('accent'), hover_color=c('card'),
            command=self._redetect_hw)
        self._wsl_redetect.pack(anchor='w', padx=12, pady=(0, 2))

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
            title='Open case',
            filetypes=[('blastlab case', '*.json'), ('All files', '*.*')])
        if not path:
            return
        try:
            # the same reader as the Qt app: a blast or an HD 1.3 case
            case = load_any_case(path)
        except FileNotFoundError:
            messagebox.showerror('Open case', f'File not found: {path}')
            return
        except json.JSONDecodeError as exc:
            messagebox.showerror(
                'Open case', f'This file is not valid JSON '
                             f'(line {exc.lineno}, column {exc.colno}).')
            return
        except (KeyError, TypeError) as exc:
            messagebox.showerror(
                'Open case', f'Not a blastlab case file: unsupported or '
                             f'missing field {exc}.')
            return
        except OSError as exc:
            messagebox.showerror(
                'Open case',
                f'Could not read the file: {exc.strerror or exc}')
            return
        except Exception as exc:
            msg = str(exc)
            messagebox.showerror(
                'Open case', msg if 'case file' in msg.lower()
                else f'Not a blastlab case file: {msg}')
            return
        if not case.dim:
            # QA F2: this app has no HD 1.3 (0-D) form; say what the file
            # is rather than "not a case file"
            messagebox.showerror(
                'Open case', f'{path} is an HD 1.3 case file. This window '
                             f'has no HD 1.3 form: open it in the Qt GUI '
                             f'(python -m blastlab).')
            return
        self.setup.set_case(case)
        # a run started from this case is named after the file (N9) - the
        # model it came from, replacing the last name (GUI QA C1: the next
        # Run offered to overwrite the PREVIOUS model)
        self.run_panel.set_run_name(
            model_folder.model_for_case_file(path), replace=True)
        self._show('setup')

    def _save_case(self):
        try:
            case = self.setup.get_case()
        except ValueError as exc:
            messagebox.showerror('Save case', str(exc))
            return
        path = filedialog.asksaveasfilename(
            title='Save case', defaultextension='.json',
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
            lines = [ln for ln in str(exc).splitlines() if ln.strip()]
            self.setup.show_report(errors=lines)
            self.run_panel.set_validation(False, len(lines))
            self.setup.update_preview(None)
            return
        if getattr(case, 'solver', 'native') == 'blastfoam':
            # warm the cached WSL availability check off-thread so the
            # validation report can show it without ever blocking
            foam_env.ensure_check_started()
        rep = validate_case(case)
        extra = []
        if rep.n_cells:
            from ..core.case import fmt_cells
            line = (f'~{fmt_cells(rep.n_cells)} cells '
                    f'at dx = {rep.effective_dx:g} m')
            if getattr(rep, 'amr_levels', 0):
                line += (f' at t = 0; AMR up to level {rep.amr_levels} '
                         f'(finest {rep.dx_fine:g} m), displayed at level '
                         f'{rep.display_level} ({rep.n_fine:,} cells)')
            elif getattr(rep, 'lmax', 0):
                line += (f' (finest {rep.dx_fine:g} m, {rep.n_fine:,} '
                         f'display cells)')
            extra.append(line)
        self.setup.show_report(rep.errors, rep.warnings, rep.notes + extra)
        self.run_panel.set_validation(not rep.errors, len(rep.errors))
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
        model = self._model_target()
        if model is None:
            return
        self._start([(case.dim, case)], paused=paused, model=model,
                    reports=[rep])

    def _init_model(self):
        """VIPER-style 'Initialise Model': start the run held at step 0
        so the initial field is visible; Exec buttons advance it."""
        self._run_single(paused=True)

    def _running(self):
        """A run is live, or its 'done' is not drained yet (G5)."""
        return self._drain_pending or (self.worker is not None
                                       and self.worker.is_alive())

    def _model_target(self, title='Run'):
        """OUT-1 pre-flight, as the Qt window's: after the case validation
        and before anything is written, refuse with one message naming
        the box, refuse a folder blastlab did not create, ask before an
        overwrite, and return the prepared `model_folder.Target` - or
        None, having said why (or the user said No)."""
        if self._running():
            # before prepare: an overwrite could hit the running model
            messagebox.showinfo('Run', 'A run is already in progress.')
            return None
        runs, name = (self.run_panel.current_runs_dir(),
                      self.run_panel.current_run_name())
        errors = model_folder.check(runs, name)
        if errors:
            self.show_error(title, '\n'.join(errors))
            return None
        try:
            return model_folder.prepare_target(
                runs, name,
                confirm=lambda text: self.ask_yes_no('Model folder', text))
        except model_folder.ModelFolderError as exc:
            self.show_error(title, str(exc))
            return None

    def _run_chain(self, dim_cases):
        """The Chain panel has validated and wired the stages into the
        model folder's paths; the folder itself is created here, only
        now (OUT-1). False when it did not start."""
        model = self._model_target('Chain')
        if model is None:
            return False
        reports = [validate_case(c, pending_inputs=k > 0)
                   for k, (_d, c) in enumerate(dim_cases)]
        if not self._start(dim_cases, model=model, reports=reports):
            return False
        self._show('run')
        return True

    def _resume_foam_run(self, path):
        """Resume a stopped blastFoam run (N6/T43) through the ordinary
        worker pipeline, so the Run tab, live view, Stop and Results all
        behave exactly as in a fresh run - and, OUT-1, into a model
        folder like one."""
        from .run_browser import dims_from_case_json
        from ..solvers.foam import env as _env
        try:
            _p, unc = _env.case_paths(path)
            dim = int((dims_from_case_json(unc) or '?').rstrip('D'))
            case = load_case(os.path.join(unc, 'case.json'))
        except (ValueError, OSError, TypeError, KeyError) as exc:
            self._log(f'  [runs] cannot resume {path}: {exc}')
            return False
        model = self._model_target('Resume')
        if model is None:
            return False
        stage = resume_stage(dim, path, case, stage_dir=model.folder,
                             run_info=model_folder.run_info(model, case))
        return self._launch([stage], [dim], model=model)

    def _start(self, dim_cases, paused=False, model=None, reports=None):
        """Run [(dim, case), ...] on a worker. OUT-1: with a `model`
        (the prepared model folder) every stage writes into it
        (`model_folder.make_stages`); `model=None` is the headless /
        test path. False when a run is already in progress."""
        if model is None:
            stages = [_solve_stage(dim, case) for dim, case in dim_cases]
        else:
            stages = model_folder.make_stages(model, dim_cases, reports)
        return self._launch(stages, [dim for dim, _ in dim_cases],
                            paused=paused, model=model)

    def _launch(self, stages, dims, paused=False, model=None):
        # `is_alive()` alone leaves a ~50 ms window after the worker exits
        # but before the drain sees its 'done': starting there would
        # orphan the old queue and drop its finished result (G5)
        if self._running():
            messagebox.showinfo('Run', 'A run is already in progress.')
            return False
        self._drain_pending = True
        self._run_count += 1
        # the name the user typed on the Run tab labels every result of
        # this run (and its exports) - blank keeps the old "Run N - 2D"
        self._run_name = self.run_panel.current_run_name()
        self._run_stopped_early = self._run_errored = False
        self._stage_dims = list(dims)
        self._model = model
        self._folders = {}
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
        return True

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
        pol = self._refresh_policy()
        raw = self.run_panel.refresh_val.get().strip()
        # an unusable value silently meant 'automatic'; say so
        self.run_panel.mark_refresh(not raw or pol is not None)
        w = self.worker
        if w is None:
            return
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
            line = ' '.join(str(msg[1]).split())
            if '[warn]' in line or '[error]' in line:
                self.notify(line, 'warn')
        elif tag == 'run_started':
            self.run_panel.on_run_started(msg[1])
            is3d = msg[1].get('scene3d') is not None
            if is3d and not pyvista_available():
                self.run_panel.on_log(f'  [{MISSING_MSG}]')
                is3d = False
            self.run_panel.enable_view3d(is3d)
            if is3d:
                self._attach_view3d_auto()
        elif tag == 'cadence':
            self.run_panel.set_cadence(msg[1], msg[2])
        elif tag == 'progress':
            self.run_panel.on_progress(msg[1])
        elif tag == 'paused':
            self.run_panel.set_paused(bool(msg[1]))
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
        elif tag == 'folder':
            # OUT-1: the stage's model folder is written; a finished
            # blastFoam run whose WSL scratch had to be kept says why
            self.__dict__.setdefault('_folders', {})[msg[1]] = msg[2]
            if msg[3]:
                self.show_error('Model folder', msg[3])
        elif tag == 'result':
            k, res = msg[1], msg[2]
            dim = self._stage_dims[k]
            name = getattr(self, '_run_name', '')
            label = ((f'{name} - {dim}D' if name
                      else f'Run {self._run_count} - {dim}D')
                     + (' (stopped)' if res.stopped_early else ''))
            if name:
                res.meta['name'] = name
            self._run_stopped_early |= bool(res.stopped_early)
            self.results.add_result(label, dim, res)
            # the live viewer belongs to this stage: hand it its playback
            # mode (window stays open). In a chain, only the LAST stage
            # finalizes it - finalizing an earlier stage would tear the
            # view down just as the next stage rebuilds it (the drain can
            # see this 'result' after the worker already started the next
            # stage and reset feed3d), so the 3D stage of a 1->2->3 chain
            # never got a live view. The final 'done' finalizes whatever
            # is left (idempotent).
            if k == len(self._stage_dims) - 1:
                self._finish_view3d(res.stop_reason)
        elif tag == 'error':
            self._run_errored = True
            self.run_panel.on_log(msg[1])
            self.show_error(
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
            # finalize the embedded 3D view if the last stage's 'result'
            # did not (idempotent: no-op when there is no live feed)
            self._finish_view3d('run complete')
            # OUT-1: a chain's root manifest.json, once every stage is in
            if self._model is not None and len(self._stage_dims) > 1:
                err = model_folder.write_chain_root(
                    self._model, self._stage_dims, self._folders)
                if err:
                    self.run_panel.on_log(f'  [warn] model folder: could '
                                          f'not write the chain '
                                          f'manifest.json: {err}')
            self.run_panel.set_running(False)
            self.chain.set_running(False)
            if not (self._run_stopped_early or self._run_errored):
                # the last progress message is often throttled away, so
                # a completed run would otherwise rest below 100%
                self.run_panel.mark_complete()
            self.run_panel.on_log('  [run finished]')
        else:
            self.root.after(50, self._drain)

    def notify(self, text, level='info'):
        """Show a short-lived line in the window's status bar."""
        text = ' '.join(str(text).split())
        if not text:
            return
        colour = {'error': c('error'), 'warn': c('warn')}.get(level,
                                                              c('muted'))
        try:
            self._status.configure(text=text[:200], text_color=colour)
        except Exception:
            return
        if self._status_job is not None:
            try:
                self.root.after_cancel(self._status_job)
            except Exception:
                pass
        self._status_job = self.root.after(
            12000, lambda: self._status.configure(text=''))

    def _result_msg(self, text):
        """Results-panel messages (exports, post-mortem loads, viewer
        hints) go to the run log AND the status bar."""
        self._log_threadsafe(text)
        low = str(text).lower()
        level = ('error' if 'fail' in low or 'error' in low else 'info')
        self.root.after(0, self.notify, text, level)

    def _log_threadsafe(self, text):
        try:
            self.root.after(0, self.run_panel.on_log, str(text))
        except (tk.TclError, RuntimeError):
            # window already closed (worker tail), or a thread reaching
            # Tk while no mainloop runs (headless drivers pump update())
            pass

    # ── shutdown ─────────────────────────────────────────────────────────
    def _on_close(self):
        self._save_ui_state()
        self._cancel_wsl_poll()
        for job in (self._validate_job, self._status_job):
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
        self._validate_job = self._status_job = None
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
