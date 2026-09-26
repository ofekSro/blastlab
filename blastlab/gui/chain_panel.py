"""Remap-chaining panel: run 1D -> 2D -> 3D as one workflow.

OUT-1, as the Qt Chain tab: the chain writes into the Run tab's model
folder (the workspace box is gone, owner decision 14) - each stage into
`<MODEL>\\1d`, `2d`, `3d` with its own MODEL.json, the profile hand-offs
at the model root. The folder is created by the app, only once the run
is certain to start."""

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from ..core.case import save_case, validate_case  # noqa: F401
# moved to core/chain.py (shared with the Qt front-end); re-exported
from ..core.chain import handoff_conflicts, stage_errors  # noqa: F401
from ..services import model_folder
from . import mode as mode_mod
from . import theme
from .forms import CaseForm
from .theme import GAP, PAD, Card, c, icon

HINT = ('The chain runs the checked stages in order, into the model folder '
        'set on the Run tab (Runs folder and Model): each stage writes '
        '<MODEL>\\1d, 2d or 3d. The profile hand-offs are wired '
        'automatically at the model root: 1D writes handoff_1d_to_2d.txt, '
        'the 2D stage remaps it (axisymmetric) and writes '
        'handoff_2d_to_3d.npz, and the 3D stage remaps that. The 2D burst '
        'height is taken from the 2D form; the 3D burst height comes from '
        'the 2D profile.')

#: added to a model-folder refusal: the boxes live on another tab
WHERE_BOXES = 'The Runs folder and Model boxes are on the Run tab.'


class ChainPanel(ctk.CTkFrame):
    def __init__(self, parent, on_run_chain, mode=None, model_source=None):
        super().__init__(parent, fg_color='transparent')
        #: on_run_chain([(dim, case), ...]) -> False when the app did not
        #: start it (it said why); anything else = started
        self._on_run_chain = on_run_chain
        #: () -> (runs_dir, model): the Run tab's two boxes (OUT-1)
        self._model_source = model_source or (lambda: ('', ''))
        # T34: every stage starts on the app-level solver mode and can be
        # overridden per stage (a native 2D stage can follow a blastFoam
        # 1D one); a global change presets all three again
        self._mode = mode if mode is not None else mode_mod.SolverMode()

        head = ctk.CTkFrame(self, fg_color='transparent')
        head.pack(fill='x', pady=(0, PAD - 4))
        ctk.CTkLabel(head, text='Chain', font=theme.F_H1,
                     text_color=c('text')).pack(side='left')

        # ── stages card ──────────────────────────────────────────────────
        top = Card(self)
        top.pack(fill='x', pady=(0, PAD - 4))
        bar = ctk.CTkFrame(top.body, fg_color='transparent')
        bar.pack(fill='x')

        self.use = {d: tk.BooleanVar(value=True) for d in (1, 2, 3)}
        ctk.CTkLabel(bar, text='Stages', font=theme.F_BODY,
                     text_color=c('muted')).pack(side='left',
                                                 padx=(0, GAP))
        for d in (1, 2, 3):
            self.use[d].trace_add('write',
                                  lambda *a: self._refresh_compat())
            ctk.CTkCheckBox(bar, text=f'{d}D', variable=self.use[d],
                            width=52, font=theme.F_BODY, corner_radius=6,
                            border_color=c('border'), fg_color=c('accent'),
                            hover_color=c('accent_hover')).pack(
                side='left', padx=(0, GAP))
        self.run_btn = ctk.CTkButton(
            bar, text='Run chain', image=icon('play', 14, color='white'),
            compound='left', width=130, height=36,
            font=theme.F_BODY, corner_radius=theme.RADIUS,
            fg_color=c('accent'), hover_color=c('accent_hover'),
            text_color='white', command=self._run)
        self.run_btn.pack(side='right')

        hint = HINT
        hrow = ctk.CTkFrame(top.body, fg_color='transparent')
        hrow.pack(fill='x', pady=(GAP, 0))
        ctk.CTkLabel(hrow, text='', width=18,
                     image=icon('info', 13,
                                color=theme.DARK['muted'])).pack(
            side='left', padx=(0, 6), anchor='n')
        ctk.CTkLabel(hrow, text=hint, font=theme.F_SMALL,
                     text_color=c('muted'), wraplength=860,
                     justify='left', anchor='w').pack(
            side='left', fill='x', expand=True)

        # N5-4: parity with ui/chain_panel - the refusal always lands
        # here, whatever happens to the dialog. The Tk panel had no
        # status line at all, so a modal that failed took the reason
        # with it.
        self.status = ctk.CTkLabel(self, text='', font=theme.F_SMALL,
                                   text_color=c('error'), wraplength=860,
                                   justify='left', anchor='w')
        self.status.pack(fill='x', padx=PAD, pady=(0, GAP))

        # ── stage forms behind a segmented switcher ──────────────────────
        stages = Card(self, pad=12)
        stages.pack(fill='both', expand=True)
        self._stage_seg = theme.segmented(
            stages.body, ['Stage 1D', 'Stage 2D', 'Stage 3D'],
            command=self._stage_selected)
        self._stage_seg.pack(anchor='w', pady=(0, GAP))

        stack = ctk.CTkScrollableFrame(
            stages.body, fg_color='transparent',
            scrollbar_button_color=c('card2'),
            scrollbar_button_hover_color=c('border'))
        stack.pack(fill='both', expand=True)
        self.forms, self._stage_wrap = {}, {}
        self._stage_solver_seg, self.stage_solver = {}, {}
        self._compat, self._compat_bad = {}, False
        self._running = False
        for d in (1, 2, 3):
            wrap = ctk.CTkFrame(stack, fg_color='transparent')
            row = ctk.CTkFrame(wrap, fg_color='transparent')
            row.pack(fill='x', pady=(0, GAP))
            ctk.CTkLabel(row, text='Solver for this stage',
                         font=theme.F_BODY, text_color=c('muted')).pack(
                side='left', padx=(0, GAP))
            seg = theme.segmented(
                row, [mode_mod.label(m) for m in mode_mod.MODES],
                height=28, font=theme.F_SMALL,
                command=lambda lbl, d=d: self.set_stage_solver(
                    d, mode_mod.from_label(lbl)))
            seg.pack(side='left')
            ctk.CTkLabel(row, text='preset from the sidebar - override '
                                   'per stage',
                         font=theme.F_SMALL, text_color=c('muted')).pack(
                side='left', padx=(GAP, 0))
            # N5-4: the hand-off refusal, said where the choice is made
            self._compat[d] = ctk.CTkLabel(
                wrap, text='', font=theme.F_SMALL, text_color=c('error'),
                wraplength=860, justify='left', anchor='w')
            self.forms[d] = CaseForm(wrap, d, mode=self._mode.get())
            self.forms[d].pack(fill='both', expand=True)
            self._stage_wrap[d], self._stage_solver_seg[d] = wrap, seg
            self.stage_solver[d] = self._mode.get()
            seg.set(mode_mod.label(self.stage_solver[d]))
        self._stack = stack
        self._current = None
        self._stage_seg.set('Stage 1D')
        self._stage_selected('Stage 1D')
        self._mode.subscribe(self._on_global_mode)
        self._refresh_compat()

    def checked(self):
        """Stages switched on, as dims. Mirrors ui/chain_panel.checked
        so the shared chain helpers take the same argument on both
        front-ends."""
        return [d for d in (1, 2, 3) if self.use[d].get()]

    # ── hand-off compatibility (N5-4) ────────────────────────────────────
    def _refresh_compat(self):
        """Show/clear the native -> blastFoam refusal per stage.

        Reads `self.stage_solver` and `checked()`, never `get_case()`:
        a half-typed field makes get_case raise, which is exactly when
        the user is most likely to be clicking around.
        """
        bad = dict(handoff_conflicts(self.checked(), self.stage_solver))
        for d in (1, 2, 3):
            msg = bad.get(d, '')
            lbl = self._compat.get(d)
            if lbl is None:
                continue
            lbl.configure(text=msg)
            if msg:
                lbl.pack(fill='x', pady=(0, GAP), before=self.forms[d])
            else:
                lbl.pack_forget()
        self._compat_bad = bool(bad)
        if bad:
            self.status.configure(
                text=f'Stage {min(bad)}: {bad[min(bad)]}')
        elif str(self.status.cget('text')).startswith('Stage '):
            self.status.configure(text='')
        self._sync_run_btn()

    def _sync_run_btn(self):
        """The ONE owner of the Run button's state. Two owners
        (set_running and the compat check) would fight, and whichever
        ran last would win."""
        ok = not self._running and not self._compat_bad
        self.run_btn.configure(state='normal' if ok else 'disabled')

    # ── T34: per-stage solver ────────────────────────────────────────────
    def set_stage_solver(self, d, m):
        m = mode_mod.normalize(m)
        self.stage_solver[d] = m
        self._stage_solver_seg[d].set(mode_mod.label(m))   # no command
        self.forms[d].set_mode(m)
        self._refresh_compat()

    def set_stage_case(self, d, case):
        """Fill stage `d` from a Case, adopting its solver."""
        self.set_stage_solver(d, getattr(case, 'solver', 'native'))
        self.forms[d].set_case(case)

    def _on_global_mode(self, m):
        for d in (1, 2, 3):
            self.set_stage_solver(d, m)
        self._refresh_compat()      # after the loop: mid-loop the set
        #                             is transiently mixed

    def focus_stage(self, d):
        """Bring stage `d`'s form to the front (a dialog naming 'Stage 2'
        used to leave the switcher wherever it was)."""
        try:
            self._stage_seg.set(f'Stage {d}D')
            self._stage_selected(f'Stage {d}D')
        except Exception:
            pass

    def _stage_selected(self, value):
        d = int(value.split()[1][0])
        if self._current is not None:
            self._current.pack_forget()
        self._current = self._stage_wrap[d]
        self._current.pack(fill='both', expand=True)

    def _run(self):
        """Validate, wire and hand on. True only if the chain was started;
        every refusal says why and returns False."""
        stages = [d for d in (1, 2, 3) if self.use[d].get()]
        if not stages:
            messagebox.showerror('Chain', 'No stages selected.')
            return False
        if stages != list(range(stages[0], stages[-1] + 1)):
            messagebox.showerror('Chain', 'Stages must be consecutive.')
            return False

        # OUT-1: the Run tab's model folder, checked (nothing is written
        # yet) before the forms are read, so the hand-off paths are known
        runs_dir, model = self._model_source()
        problems = model_folder.check(runs_dir, model)
        if problems:
            messagebox.showerror('Chain', '\n'.join(problems + [WHERE_BOXES]))
            return False
        target = model_folder.Target(
            runs_dir=str(runs_dir).strip(), model=str(model).strip(),
            folder=model_folder.folder_for(runs_dir, model))
        hand = model_folder.handoff_paths(target, stages)
        p1, p2 = hand.get((1, 2)), hand.get((2, 3))

        cases = {}
        for d in stages:
            try:
                cases[d] = self.forms[d].get_case()
            except ValueError as exc:
                # name the stage (a bare "'Lx' is not a number" gave no
                # clue which of the three forms it came from) and switch
                # to it so the offending field is on screen
                self.focus_stage(d)
                messagebox.showerror('Chain', '\n'.join(
                    f'Stage {d} ({d}D): {ln}'
                    for ln in str(exc).splitlines() if ln.strip()))
                return False

        # N2-13: a chain must be reproducible, so every stage runs on a
        # PINNED write schedule. The adaptive-writeInterval controller
        # rewrites writeInterval mid-run from what the ingest has managed
        # to keep up with - wall clock - so with it on, the set of write
        # times differs between identical runs, and the arrival-pinned
        # hand-off lands on a different write each time (measured: stage
        # ends spread +/-7% / 2.3x over five identical chains).
        for c in cases.values():
            c.adaptive_write = False

        # auto-wire profile hand-offs, at the model root (plan sec. 2.2);
        # a single stage has none and writes its own profile
        if 1 in cases and 2 in cases:
            cases[1].profile_file = p1
            cases[2].init_mode = 'profile1d'
            cases[2].profile_file_in = p1
        if 2 in cases:
            if cases[2].geometry != 'axisymmetric' and 3 in cases:
                self.focus_stage(2)          # the dialog names stage 2
                messagebox.showerror(
                    'Chain', 'Stage 2 (2D): must be axisymmetric to '
                             'feed the 3D stage.')
                return False
            if 3 in cases:
                cases[2].profile_file = p2
        if 3 in cases and 2 in cases:
            cases[3].init_mode = 'profile2d'
            cases[3].profile_file_in = p2

        errors = stage_errors(stages, cases)
        if errors:
            for d in stages:                     # jump to the first bad one
                if any(e.startswith(f'Stage {d} ') for e in errors):
                    self.focus_stage(d)
                    break
            messagebox.showerror('Chain', '\n'.join(errors))
            return False

        # the app creates the model folder (after asking, for an existing
        # one) only now; each stage writes its own MODEL.json
        return self._on_run_chain([(d, cases[d]) for d in stages]) \
            is not False

    def set_running(self, running):
        """Mirror the Run button's state: a second start while a run is
        live would orphan the drain loop and drop the finished result."""
        self._running = bool(running)
        self._sync_run_btn()
