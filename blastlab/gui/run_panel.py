"""Run panel: start/stop controls, progress readouts, scrolled log and
the embedded live overpressure view."""

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk
import numpy as np
from matplotlib.figure import Figure

from ..core import refine
from ..core.constants import P_AIR
from ..output.plots import add_mesh_lines, overpressure_panel, set_frame
from . import theme
from .mpl import EmbeddedFigure
from .theme import GAP, PAD, Card, c, icon
from .view3d_panel import View3DPanel


def _chip(parent, caption):
    """Small stat chip: muted caption over a value label; returns the
    value label."""
    box = ctk.CTkFrame(parent, fg_color=c('card2'), corner_radius=8)
    box.pack(side='left', padx=(0, GAP))
    ctk.CTkLabel(box, text=caption, font=theme.F_SMALL,
                 text_color=c('muted'), height=12).pack(
        anchor='w', padx=10, pady=(5, 0))
    val = ctk.CTkLabel(box, text='—', font=(theme.FONT, 12, 'bold'),
                       text_color=c('text'), height=16)
    val.pack(anchor='w', padx=10, pady=(0, 5))
    return val


class RunPanel(ctk.CTkFrame):
    def __init__(self, parent, on_run, on_stop, on_view3d=None,
                 on_init=None, on_exec=None, on_refresh=None):
        super().__init__(parent, fg_color='transparent')

        head = ctk.CTkFrame(self, fg_color='transparent')
        head.pack(fill='x', pady=(0, PAD - 4))
        ctk.CTkLabel(head, text='Run', font=theme.F_H1,
                     text_color=c('text')).pack(side='left')

        # ── control card ─────────────────────────────────────────────────
        ctl = Card(self)
        ctl.pack(fill='x', pady=(0, PAD - 4))
        bar = ctk.CTkFrame(ctl.body, fg_color='transparent')
        bar.pack(fill='x')
        self.run_btn = theme.Button(
            bar, text='Run', image=icon('play', 15, color='white'),
            compound='left', width=110, height=38, font=theme.F_BODY,
            corner_radius=theme.RADIUS, fg_color=c('accent'),
            hover_color=c('accent_hover'), text_color='white',
            command=on_run)
        self.run_btn.pack(side='left', padx=(0, GAP))
        # starts inert: a disabled danger-red button reads as armed
        self.stop_btn = theme.Button(
            bar, text='Stop', image=icon('stop', 14, color='white'),
            compound='left', width=100, height=38, font=theme.F_BODY,
            corner_radius=theme.RADIUS, fg_color=c('card2'),
            hover_color=c('border'), text_color=c('muted'),
            state='disabled', command=on_stop)
        self.stop_btn.pack(side='left', padx=(0, GAP))
        self.view3d_btn = theme.Button(
            bar, text='3D View', image=icon('cube', 15), compound='left',
            width=110, height=38, font=theme.F_BODY,
            corner_radius=theme.RADIUS, fg_color=c('card2'),
            hover_color=c('border'), text_color=c('text'),
            state='disabled', command=on_view3d or (lambda: None))
        self.view3d_btn.pack(side='left', padx=(0, PAD))

        # results used to be labelled by dim + a counter only, so three
        # runs of different cases read "Run 1 - 2D", "Run 2 - 2D" ... (N9)
        # (CTkEntry drops its placeholder as soon as a textvariable is
        # attached, so the box gets a real label instead)
        self.run_name = tk.StringVar(value='')
        ctk.CTkLabel(bar, text='Name', font=theme.F_BODY,
                     text_color=c('muted')).pack(side='left',
                                                 padx=(0, 6))
        self._name_entry = ctk.CTkEntry(
            bar, textvariable=self.run_name, width=130, height=32,
            font=theme.F_BODY, corner_radius=8, fg_color=c('entry'),
            border_color=c('border'))
        self._name_entry.pack(side='left', padx=(0, GAP))
        theme.tooltip(self._name_entry,
                      'Names this run in the Results picker and in the '
                      'exported file names; blank falls back to '
                      '"Run N - 2D".')

        self.progress = ctk.CTkProgressBar(
            bar, width=120, height=8, corner_radius=4,
            progress_color=c('accent'), fg_color=c('card2'))
        self.progress.set(0.0)
        # takes the slack so the readouts on the right keep their width
        self.progress.pack(side='left', padx=(0, GAP), fill='x',
                           expand=True)
        # stepped execution used to be visible only as a "[interrupted]"
        # line in the log; say it where the run state is read
        self._paused_lbl = ctk.CTkLabel(bar, text='', font=theme.F_SMALL,
                                        text_color=c('warn'))
        self._paused_lbl.pack(side='left', padx=(0, GAP))
        # the Setup strip is on another tab, so the Run tab used to give
        # no hint that the case was invalid until a modal appeared
        self._valid_lbl = ctk.CTkLabel(bar, text='', font=theme.F_SMALL,
                                       text_color=c('muted'))
        self._valid_lbl.pack(side='left', padx=(0, PAD))

        chips = ctk.CTkFrame(bar, fg_color='transparent')
        # packed BEFORE the buttons: pack hands out requested widths in
        # packing order, so the chips used to be the row that lost its
        # last box at 1100 px (QA-27)
        chips.pack(side='right', before=self.run_btn)
        self._chip_step = _chip(chips, 'step')
        self._chip_t = _chip(chips, 't [ms]')
        self._chip_dt = _chip(chips, 'dt [s]')
        # kPa like every plot and colorbar (the chip used to be the one
        # readout in Pa, a 1000x mismatch against the live view beside it)
        self._chip_pmax = _chip(chips, 'p max [kPa]')
        # dynamic AMR moves the cell count every write; it was only ever
        # visible as a log line (QA-32). Packed on the first frame that
        # carries a level map, so a static run keeps its four chips.
        self._chip_cells = _chip(chips, 'cells')
        self._chip_cells.master.pack_forget()

        # ── stepped execution row (VIPER-style) ──────────────────────────
        on_exec = on_exec or (lambda cmd: None)
        ebar = ctk.CTkFrame(ctl.body, fg_color='transparent')
        ebar.pack(fill='x', pady=(GAP + 2, 0))
        self.init_btn = theme.Button(
            ebar, text='Initialise Model', image=icon('flag', 14),
            compound='left', width=150, height=32, font=theme.F_BODY,
            corner_radius=theme.RADIUS, fg_color=c('card2'),
            hover_color=c('border'), text_color=c('text'),
            command=on_init or (lambda: None))
        self.init_btn.pack(side='left', padx=(0, GAP))
        self._exec_btns = []

        def exec_btn(text, cmd, image=None, pad=(0, 4)):
            b = theme.Button(
                ebar, text=text, image=image, compound='left', width=72,
                height=32, font=theme.F_BODY, corner_radius=theme.RADIUS,
                fg_color=c('card2'), hover_color=c('border'),
                text_color=c('text'), state='disabled', command=cmd)
            b.pack(side='left', padx=pad)
            self._exec_btns.append(b)
            return b

        for n in (1, 10, 100, 1000):
            exec_btn(f'Exec {n}', lambda n=n: on_exec(n))
        exec_btn('END', lambda: on_exec('run'), image=icon('end', 13))
        exec_btn('Interrupt', lambda: on_exec('pause'),
                 image=icon('pause', 13), pad=(GAP, 0))

        # live-view refresh rate (2D slice + 3D view); blank = automatic
        on_refresh = on_refresh or (lambda: None)
        self.refresh_mode = ctk.CTkComboBox(
            ebar, state='readonly', width=104, height=32,
            values=('seconds', 'steps'), font=theme.F_BODY,
            corner_radius=8, fg_color=c('entry'),
            border_color=c('border'), button_color=c('card2'),
            button_hover_color=c('border'), dropdown_font=theme.F_BODY,
            command=lambda v: on_refresh())
        self.refresh_mode.set('seconds')
        self.refresh_mode.pack(side='right', padx=GAP)
        self.refresh_val = tk.StringVar(value='')
        ent = ctk.CTkEntry(ebar, textvariable=self.refresh_val, width=64,
                           height=32, font=theme.F_BODY, corner_radius=8,
                           fg_color=c('entry'), border_color=c('border'))
        ent.pack(side='right')
        ent.bind('<Return>', lambda e: on_refresh())
        ent.bind('<FocusOut>', lambda e: on_refresh())
        self._refresh_entry = ent
        # the "(blank = auto)" caption cost 73 px of a row that does not
        # fit at 1100 px - it is a hover hint now (QA-27)
        theme.tooltip(ent, 'How often the live view redraws; '
                           'leave blank (or 0) for automatic.')
        ctk.CTkLabel(ebar, text='Refresh every', font=theme.F_BODY,
                     text_color=c('muted')).pack(side='right',
                                                 padx=(0, GAP))

        # ── body: log | live view ────────────────────────────────────────
        body = ttk.Panedwindow(self, orient='horizontal')
        body.pack(fill='both', expand=True)

        logcard = Card(body, title='Log', pad=12)
        self.log = ctk.CTkTextbox(
            # requested width kept small: ttk clamps the sash to the panes'
            # requested sizes, so a wide box pinned the log pane open
            logcard.body, state='disabled', wrap='word', width=280,
            font=theme.F_MONO, corner_radius=8, fg_color=c('entry'),
            text_color=c('text'), border_width=0,
            scrollbar_button_color=c('card2'),
            scrollbar_button_hover_color=c('border'))
        self.log.pack(fill='both', expand=True)
        body.add(logcard, weight=2)

        right = Card(body, pad=12)
        vbar = ctk.CTkFrame(right.body, fg_color='transparent')
        vbar.pack(fill='x', pady=(0, GAP))
        self._view_seg = ctk.CTkSegmentedButton(
            vbar, values=['Live slice', '3D view'],
            font=theme.F_BODY, corner_radius=theme.RADIUS, height=32,
            fg_color=c('card2'), unselected_color=c('seg'),
            unselected_hover_color=c('border'),
            selected_color=c('accent'),
            selected_hover_color=c('accent_hover'),
            command=self._view_selected)
        self._view_seg.pack(side='left')
        # cell edges over the live slice (true cells of a refined run)
        self.show_mesh_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            vbar, text='Show mesh', variable=self.show_mesh_var,
            command=self._rebuild_overlay, font=theme.F_BODY,
            corner_radius=6, checkbox_width=19, checkbox_height=19,
            border_width=2, border_color=c('border'),
            fg_color=c('accent'), hover_color=c('accent_hover')).pack(
            side='left', padx=(PAD, 0))
        # manual colour range for the 2D live pane, mirroring the 3D
        # viewer's Min/Max: a late weak frame used to rescale the whole
        # picture, so nothing could be compared across a run (G7)
        self.auto_clim_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            vbar, text='Auto', variable=self.auto_clim_var,
            command=self._clim_changed, font=theme.F_BODY,
            corner_radius=6, checkbox_width=19, checkbox_height=19,
            border_width=2, border_color=c('border'),
            fg_color=c('accent'), hover_color=c('accent_hover')).pack(
            side='left', padx=(PAD, GAP))
        self.clim_min = tk.StringVar(value='0')
        self.clim_max = tk.StringVar(value='')
        self._clim_entries = []
        for lbl, var in (('Min', self.clim_min), ('Max', self.clim_max)):
            ctk.CTkLabel(vbar, text=lbl, font=theme.F_SMALL,
                         text_color=c('muted')).pack(side='left',
                                                     padx=(0, 4))
            ent = ctk.CTkEntry(vbar, textvariable=var, width=64, height=28,
                               font=theme.F_SMALL, corner_radius=8,
                               fg_color=c('entry'), border_color=c('border'))
            ent.pack(side='left', padx=(0, GAP))
            ent.bind('<Return>', lambda e: self._clim_changed())
            ent.bind('<FocusOut>', lambda e: self._clim_changed())
            self._clim_entries.append(ent)
        ctk.CTkLabel(vbar, text='kPa', font=theme.F_SMALL,
                     text_color=c('muted')).pack(side='left')
        self._sync_clim_state()
        stack = ctk.CTkFrame(right.body, fg_color='transparent')
        stack.pack(fill='both', expand=True)
        stack.grid_columnconfigure(0, weight=1)
        stack.grid_rowconfigure(0, weight=1)
        slice_tab = ctk.CTkFrame(stack, fg_color='transparent')
        self.canvas = EmbeddedFigure(slice_tab, figsize=(5.5, 5.5),
                                     toolbar=False)
        self.canvas.pack(fill='both', expand=True)
        self.view3d = View3DPanel(stack, log_fn=self.on_log)
        for w in (self.view3d, slice_tab):
            w.grid(row=0, column=0, sticky='nsew')
        self._slice_tab = slice_tab
        # Tk stacking follows creation order (view3d was created last),
        # so raise the slice explicitly; seg.set() fires no callback.
        self._view_seg.set('Live slice')
        slice_tab.tkraise()
        body.add(right, weight=3)

        # ttk pane weights only share out EXTRA space, so the sash opened
        # where the log's requested width put it and the embedded 3D view
        # was ~330 px wide with a clipped HUD (QA-17). Park the sash after
        # the first real layout, and stop once the user drags it.
        self._body = body
        self._sash_user = False
        body.bind('<Configure>', self._place_sash, add='+')
        body.bind('<ButtonRelease-1>', self._sash_dragged, add='+')

        self._mesh = None
        self._line = None
        self._solid = None
        self._mesh_geom = None      # (x_face, y_face, mesh_src) of the run
        self._mesh_lines = None     # the overlay LineCollection
        self._title = None
        self._last_step = None      # newest step, for the PAUSED readout
        self._amr_run = 0           # consecutive AMR log lines collapsed
        self._cadence = 0.0         # foam: seconds between live frames
        self._cadence_steps = 0     # foam: solver steps between live frames
        self._last_dt = 0.0         # newest solver time step [s]
        self._last_field = None     # newest 2D frame, for a clim redraw
        self._running = False
        self._case_ok = True        # latest validation verdict (Setup tab)

    def set_run_name(self, name):
        """Pre-fill the run name (Open case uses the file stem)."""
        if not self.run_name.get().strip():
            self.run_name.set(str(name or ''))

    def current_run_name(self):
        return self.run_name.get().strip()

    # ── body sash ────────────────────────────────────────────────────────
    #: share of the Run-tab width given to the log; the live/3D pane keeps
    #: the rest (>= 60 %, the QA-17 target)
    LOG_FRAC = 0.34
    LOG_MIN = 240
    VIEW_MIN = 420

    def _sash_dragged(self, _e=None):
        self._sash_user = True

    def _place_sash(self, _e=None):
        if self._sash_user:
            return
        w = self._body.winfo_width()
        if w <= 1:
            return
        want = max(self.LOG_MIN, min(int(w * self.LOG_FRAC),
                                     w - self.VIEW_MIN))
        try:
            if abs(self._body.sashpos(0) - want) > 4:
                self._body.sashpos(0, want)
        except tk.TclError:
            pass

    # ── live-view sub-tab switching ──────────────────────────────────────
    def _view_selected(self, value):
        (self.view3d if value == '3D view' else self._slice_tab).tkraise()

    def show_3d_tab(self):
        self._view_seg.set('3D view')
        self.view3d.tkraise()

    def show_slice_tab(self):
        self._view_seg.set('Live slice')
        self._slice_tab.tkraise()

    # ── event handlers (called from the app's queue drainer) ─────────────
    def set_running(self, running):
        self._running = bool(running)
        if running:
            # the cadence belongs to the run: a native run after a foam
            # one must not inherit "frames every ~0.05 ms" (G7)
            self._cadence = 0.0
            self._cadence_steps = 0
            self._last_dt = 0.0
            self._last_field = None
        start_ok = (not running) and self._case_ok
        self.run_btn.configure(state='normal' if start_ok else 'disabled')
        self.init_btn.configure(state='normal' if start_ok else 'disabled')
        # a disabled Stop used to stay danger-red, reading as armed
        self.stop_btn.configure(
            state='normal' if running else 'disabled',
            fg_color=c('danger') if running else c('card2'),
            hover_color=c('danger_hover') if running else c('border'),
            text_color='white' if running else c('muted'))
        for b in self._exec_btns:
            b.configure(state='normal' if running else 'disabled')
        self.set_paused(False)
        if running:
            self.progress.set(0.0)
            self._clear_log()
            # Everything below belongs to the PREVIOUS run: the chips and
            # the live plot used to keep its step/time/field until the new
            # run's first frame, which on a blastFoam cold start is minutes
            # of a stale picture (and, after Initialise Model, a t = 0 plot
            # beside the last run's step count).
            self._reset_readouts()
        else:
            # live attach only during a run; Results tab covers afterwards
            self.view3d_btn.configure(state='disabled')

    def _reset_readouts(self):
        """Chips back to '-', live plot to a waiting placeholder, 3D view
        dropped: nothing on the Run tab may still describe the last run."""
        self._last_step = None
        self._chip_cells.master.pack_forget()
        for chip in (self._chip_step, self._chip_t, self._chip_dt,
                     self._chip_pmax, self._chip_cells):
            chip.configure(text='—')
        self._mesh = self._line = self._solid = None
        self._mesh_geom = self._mesh_lines = None
        self._title = None
        fig = Figure(figsize=(5.5, 5.5))
        ax = fig.add_subplot()
        ax.axis('off')
        ax.text(0.5, 0.5, 'waiting for the solver…', transform=ax.transAxes,
                ha='center', va='center', fontsize=11,
                color=theme.cur('muted'))
        self.canvas.set_figure(fig)
        try:
            self.view3d.reset()
        except Exception:
            pass

    def set_validation(self, ok, n_errors=0):
        """Mirror the Setup validation strip on the Run tab and gate the
        start buttons, so an invalid case is visible here instead of only
        as a modal after pressing Run."""
        self._case_ok = bool(ok)
        if ok:
            self._valid_lbl.configure(text='Case OK', text_color=c('ok'))
        else:
            n = max(int(n_errors), 1)
            self._valid_lbl.configure(
                text=f'{n} error{"s" if n != 1 else ""} - see Setup',
                text_color=c('error'))
        if not self._running:
            state = 'normal' if ok else 'disabled'
            self.run_btn.configure(state=state)
            self.init_btn.configure(state=state)

    def mark_refresh(self, ok):
        """Red-border the 'Refresh every' box when its value is unusable
        (it used to fall back to automatic in silence)."""
        try:
            self._refresh_entry.configure(
                border_color=c('border') if ok else theme.c('error'))
        except Exception:
            pass

    def set_paused(self, paused):
        self._paused_lbl.configure(
            text=('PAUSED at step '
                  f'{self._last_step}' if self._last_step is not None
                  else 'PAUSED') if paused else '')

    def enable_view3d(self, enabled):
        self.view3d_btn.configure(state='normal' if enabled else 'disabled')

    #: a dynamic-AMR run logs one of these per written time - 60+ lines for
    #: half a millisecond of simulation, which buried every other message.
    #: They are collapsed HERE rather than in the solver: the text itself
    #: is the e2e drivers' instrumentation (cells per write) and must keep
    #: reaching stdout and the transcript unchanged.
    _AMR_MARK = '[blastfoam] AMR t = '

    def on_log(self, text):
        line = str(text)
        self.log.configure(state='normal')
        if self._AMR_MARK in line and self._amr_run:
            # replace the previous (also collapsed) AMR line in place
            self.log.delete('end-2l linestart', 'end-1l linestart')
            self._amr_run += 1
            line = f'{line}   [{self._amr_run} AMR writes so far]'
        elif self._AMR_MARK in line:
            self._amr_run = 1
        else:
            self._amr_run = 0
        self.log.insert('end', line + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def _clear_log(self):
        self._amr_run = 0
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')

    def mark_complete(self):
        """Run reached its own end: fill the bar. The worker throttles
        progress messages to ~10 Hz, so the final one is usually dropped
        and the last frac this panel ever saw is short of 1.0."""
        self.progress.set(1.0)

    def on_progress(self, p):
        self.progress.set(max(0.0, min(1.0, p.frac)))
        self._last_step = p.step
        self._chip_step.configure(text=str(p.step))
        self._chip_t.configure(text=f'{p.t*1e3:.3f}')
        self._chip_dt.configure(text=f'{p.dt:.2e}')
        self._last_dt = float(p.dt)     # turns a step cadence into a time
        self._chip_pmax.configure(text=f'{p.p_max / 1e3:,.4g}')

    def on_run_started(self, info):
        self._last_field = None
        fig = Figure(figsize=(5.5, 5.5))
        ax = fig.add_subplot()
        self._mesh = self._line = None
        self._mesh_geom = self._mesh_lines = None
        if info['dim'] == 1:
            (self._line,) = ax.plot([], [], lw=1.4,
                                    color=theme.cur('accent'))
            ax.set_xlim(0, info['radius_m'])
            # before the first frame an empty autoscaled axis showed a
            # meaningless -0.04..0.04 kPa range
            ax.set_ylim(0, 10)
            ax.set_xlabel('r [m]')
            ax.set_ylabel('Overpressure [kPa]')
            ax.grid(True, alpha=0.3)
            self._title = ax.set_title('t = 0.000 ms')
        else:
            self._solid = info['solid']
            self._mesh = overpressure_panel(
                ax, info['x_face'], info['y_face'], info['solid'].shape)
            # mesh_src: the plane's source-cell ids for a refined foam
            # run (absent/None = uniform: every face)
            self._mesh_geom = (info['x_face'], info['y_face'],
                               info.get('mesh_src'))
            # dynamic AMR: frames carry their level map; display_level
            # sizes the blocks (the display grid sits at that level)
            self._disp_level = info.get('display_level')
            self._mesh_levels = None
            self._rebuild_overlay(draw=False)
            ax.set_xlabel(info['xlabel'])
            ax.set_ylabel(info['ylabel'])
            self._title = ax.set_title(info.get('title', ''))
            fig.colorbar(self._mesh, ax=ax, label='Overpressure [kPa]',
                         shrink=0.85)
        fig.tight_layout()
        self.canvas.set_figure(fig)

    # ── live colour range (2D pane) ──────────────────────────────────────
    def _sync_clim_state(self):
        state = 'disabled' if self.auto_clim_var.get() else 'normal'
        for ent in self._clim_entries:
            ent.configure(state=state)

    def live_clim(self):
        """(vmin, vmax) in kPa for the live pane, or None for autoscale.
        A blank or unparsable box falls back to autoscale rather than
        pinning the picture to a nonsense range."""
        if self.auto_clim_var.get():
            return None
        try:
            lo = float(self.clim_min.get().strip() or 0.0)
            hi = float(self.clim_max.get().strip())
        except ValueError:
            return None
        if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
            return None
        return (lo, hi)

    def _clim_changed(self):
        self._sync_clim_state()
        if self._mesh is not None and self._last_field is not None:
            set_frame(self._mesh, self._last_field, self._solid,
                      clim=self.live_clim())
            self.canvas.draw()

    def set_cadence(self, dt=None, steps=None):
        """How often live frames arrive: `steps` solver steps (the live
        sample) or `dt` seconds (writeInterval, when there is no live
        sample). Either may be None for "unchanged" - the adaptive
        controller reports one, the refresh policy the other."""
        if dt is not None:
            try:
                self._cadence = max(0.0, float(dt))
            except (TypeError, ValueError):
                self._cadence = 0.0
        if steps is not None:
            try:
                self._cadence_steps = max(0, int(steps))
            except (TypeError, ValueError):
                self._cadence_steps = 0

    @staticmethod
    def _fmt_dt(seconds):
        ms = seconds * 1e3
        return f'{ms * 1e3:.3g} µs' if ms < 0.01 else f'{ms:.3g} ms'

    def cadence_text(self):
        """"frames every ~X" for the live-view title, or '' when the run
        emits whenever it likes (native)."""
        if self._cadence_steps > 0:
            if self._last_dt > 0.0:
                return ('frames every ~'
                        + self._fmt_dt(self._cadence_steps * self._last_dt))
            return f'frames every ~{self._cadence_steps} solver steps'
        if self._cadence > 0.0:
            return 'frames every ~' + self._fmt_dt(self._cadence)
        return ''

    def _rebuild_overlay(self, draw=True):
        """Add/remove the cell-edge overlay per the checkbox."""
        if self._mesh is None or self._mesh_geom is None:
            return
        if self._mesh_lines is not None:
            self._mesh_lines.remove()
            self._mesh_lines = None
        if self.show_mesh_var.get():
            xf, yf, src = self._mesh_geom
            lv = getattr(self, '_mesh_levels', None)
            if lv is not None:
                lv = np.asarray(lv)
                src = refine.fine_src(
                    np.maximum(lv, 0),
                    int(getattr(self, '_disp_level', None) or lv.max()),
                    solid_fine=(lv < 0) if (lv < 0).any() else None)
            from ..output.plots import MESH_MAX_LINES
            self._mesh_lines = add_mesh_lines(
                self._mesh.axes,
                refine.mesh_segments_2d(src, xf, yf,
                                        max_lines=MESH_MAX_LINES),
                color=theme.cur('muted'))
        if draw:
            self.canvas.draw()

    def _show_cells(self, levels):
        """Live cell count of a dynamic-AMR mesh (QA-32).

        `levels` is a level map on the DISPLAY grid (the finest displayed
        level), so a cell at level l stands for 2**((disp - l) * ndim)
        display cells - count each of them once. A 3D run hands over the
        live plane, not the whole mesh; the tooltip says so.
        """
        try:
            lv = np.asarray(levels)
            disp = float(lv.max())
            n = int(round(float(np.power(
                2.0, -(disp - lv.astype(np.float64)) * lv.ndim).sum())))
        except (ValueError, TypeError, AttributeError):
            return
        box = self._chip_cells.master
        if box.winfo_manager() == '':
            box.pack(side='left', padx=(0, GAP))
            theme.tooltip(box, 'Cells of the dynamic (AMR) mesh on the '
                               'live plane - a 3D run counts the slice, '
                               'not the whole mesh.')
        self._chip_cells.configure(text=f'{n:,}')

    def on_frame(self, field, t, levels=None):
        # Frames are coalesced in a single slot shared across chain stages,
        # so a frame may briefly belong to the NEXT stage while this panel
        # is still configured for the previous one - guard by shape.
        if self._mesh is not None:
            if self._solid is None or field.shape != self._solid.shape:
                return
            self._last_field = field
            set_frame(self._mesh, field, self._solid,
                      clim=self.live_clim())
            if levels is not None and np.shape(levels) == field.shape:
                self._mesh_levels = levels
                self._show_cells(levels)
                if self.show_mesh_var.get():
                    self._rebuild_overlay(draw=False)
        elif self._line is not None:
            if field.ndim != 2 or field.shape[0] != 2:
                return
            r, p = field
            ovp = (p.astype(np.float64) - P_AIR) / 1e3
            self._line.set_data(r, ovp)
            ax = self._line.axes
            ax.relim()
            ax.autoscale_view(scalex=False)
        else:
            return
        if self._title is not None:
            # everything before the LAST 't =' is the pane's own label;
            # the cadence suffix is re-appended each frame (G7)
            base = self._title.get_text().rsplit('t =', 1)[0].strip()
            txt = f'{base}  t = {t*1e3:.3f} ms'.strip()
            hint = self.cadence_text()
            if hint:
                txt += f'  ·  {hint}'
            self._title.set_text(txt)
        self.canvas.draw()
