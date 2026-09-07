"""Remap-chaining panel: run 1D -> 2D -> 3D as one workflow. Profile
files are auto-wired inside a chosen workspace directory; each stage's
case JSON is saved there for reproducibility."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..core.case import save_case, validate_case
from . import mode as mode_mod
from . import theme
from .forms import CaseForm
from .theme import GAP, PAD, Card, c, icon


def stage_errors(stages, cases):
    """Per-stage validation errors for an auto-wired chain, as
    "Stage <n> (<n>D): <message>" lines (empty = ready to run).

    Must run AFTER the profile hand-offs are wired: the wiring is what
    makes a later stage profile-initialized, so validating the raw forms
    would miss exactly the combination that used to reach the backend
    and die there with a traceback."""
    errors = []
    for d in stages:
        case = cases[d]
        # every stage but the first is fed by the one before it, so its
        # profile input cannot exist on disk yet
        msgs = list(validate_case(
            case, pending_inputs=(d != stages[0])).errors)
        if (getattr(case, 'solver', 'native') == 'blastfoam'
                and getattr(case, 'init_mode', 'charge') != 'charge'):
            # the chain wired this profile init, not the user, so say so
            # instead of repeating validate_case's generic phrasing
            msgs = [m for m in msgs if 'Profile initialization' not in m]
            msgs.insert(0, 'blastFoam stages cannot start from a profile '
                           'yet (ROADMAP N7) - run this stage with the '
                           'native solver, or drop the stage that feeds '
                           'it')
        errors += [f'Stage {d} ({d}D): {m}' for m in msgs]
    return errors


class ChainPanel(ctk.CTkFrame):
    def __init__(self, parent, on_run_chain, mode=None):
        super().__init__(parent, fg_color='transparent')
        self._on_run_chain = on_run_chain
        # T34: every stage starts on the app-level solver mode and can be
        # overridden per stage (a native 2D stage can follow a blastFoam
        # 1D one); a global change presets all three again
        self._mode = mode if mode is not None else mode_mod.SolverMode()

        head = ctk.CTkFrame(self, fg_color='transparent')
        head.pack(fill='x', pady=(0, PAD - 4))
        ctk.CTkLabel(head, text='Chain', font=theme.F_H1,
                     text_color=c('text')).pack(side='left')

        # ── workspace / stages card ──────────────────────────────────────
        top = Card(self)
        top.pack(fill='x', pady=(0, PAD - 4))
        bar = ctk.CTkFrame(top.body, fg_color='transparent')
        bar.pack(fill='x')
        ctk.CTkLabel(bar, text='Workspace', font=theme.F_BODY,
                     text_color=c('muted')).pack(side='left',
                                                 padx=(0, GAP))
        # under Documents rather than whatever the process CWD happens to
        # be (which for blastlab.bat is the install directory)
        _docs = os.path.join(os.path.expanduser('~'), 'Documents')
        _base = _docs if os.path.isdir(_docs) else os.path.expanduser('~')
        self.ws_var = tk.StringVar(
            value=os.path.join(_base, 'blastlab', 'chain_workspace'))
        ctk.CTkEntry(bar, textvariable=self.ws_var, width=380, height=32,
                     font=theme.F_BODY, corner_radius=8,
                     fg_color=c('entry'), border_color=c('border')).pack(
            side='left')
        ctk.CTkButton(bar, text='', image=icon('folder', 14), width=34,
                      height=32, corner_radius=theme.RADIUS,
                      fg_color=c('card2'), hover_color=c('border'),
                      command=self._pick_ws).pack(side='left',
                                                  padx=(GAP, PAD))

        self.use = {d: tk.BooleanVar(value=True) for d in (1, 2, 3)}
        ctk.CTkLabel(bar, text='Stages', font=theme.F_BODY,
                     text_color=c('muted')).pack(side='left',
                                                 padx=(0, GAP))
        for d in (1, 2, 3):
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

        hint = ("The chain runs the checked stages in order. Profile files "
                "are wired automatically: 1D saves stage1_profile.txt, the "
                "2D stage remaps it (axisymmetric), saves "
                "stage2_profile.npz, and the 3D stage remaps that. The 2D "
                "burst height is taken from the 2D form; the 3D burst "
                "height comes from the 2D profile.")
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

    # ── T34: per-stage solver ────────────────────────────────────────────
    def set_stage_solver(self, d, m):
        m = mode_mod.normalize(m)
        self.stage_solver[d] = m
        self._stage_solver_seg[d].set(mode_mod.label(m))   # no command
        self.forms[d].set_mode(m)

    def set_stage_case(self, d, case):
        """Fill stage `d` from a Case, adopting its solver."""
        self.set_stage_solver(d, getattr(case, 'solver', 'native'))
        self.forms[d].set_case(case)

    def _on_global_mode(self, m):
        for d in (1, 2, 3):
            self.set_stage_solver(d, m)

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

    def _pick_ws(self):
        d = filedialog.askdirectory(title='Chain workspace directory')
        if d:
            self.ws_var.set(d)

    def _run(self):
        stages = [d for d in (1, 2, 3) if self.use[d].get()]
        if not stages:
            messagebox.showerror('Chain', 'No stages selected.')
            return
        if stages != list(range(stages[0], stages[-1] + 1)):
            messagebox.showerror('Chain', 'Stages must be consecutive.')
            return

        ws = self.ws_var.get()
        # the workspace used to be created even when the run was refused
        p1 = os.path.join(ws, 'stage1_profile.txt')
        p2 = os.path.join(ws, 'stage2_profile.npz')

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
                return

        # auto-wire profile hand-offs
        if 1 in cases:
            cases[1].profile_file = p1
        if 2 in cases:
            if 1 in cases:
                cases[2].init_mode = 'profile1d'
                cases[2].profile_file_in = p1
            if cases[2].geometry != 'axisymmetric' and 3 in cases:
                self.focus_stage(2)          # the dialog names stage 2
                messagebox.showerror(
                    'Chain', 'Stage 2 (2D): must be axisymmetric to '
                             'feed the 3D stage.')
                return
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
            return

        os.makedirs(ws, exist_ok=True)           # only once it will run
        for d, case in cases.items():
            save_case(case, os.path.join(ws, f'stage{d}_case.json'))

        self._on_run_chain([(d, cases[d]) for d in stages], ws)

    def set_running(self, running):
        """Mirror the Run button's state: a second start while a run is
        live would orphan the drain loop and drop the finished result."""
        self.run_btn.configure(state='disabled' if running else 'normal')
