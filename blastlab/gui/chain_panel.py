"""Remap-chaining panel: run 1D -> 2D -> 3D as one workflow. Profile
files are auto-wired inside a chosen workspace directory; each stage's
case JSON is saved there for reproducibility."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..core.case import save_case
from . import theme
from .forms import CaseForm
from .theme import GAP, PAD, Card, c, icon


class ChainPanel(ctk.CTkFrame):
    def __init__(self, parent, on_run_chain):
        super().__init__(parent, fg_color='transparent')
        self._on_run_chain = on_run_chain

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
        self.ws_var = tk.StringVar(value=os.path.abspath('chain_workspace'))
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
        ctk.CTkButton(bar, text='Run chain',
                      image=icon('play', 14, color='white'),
                      compound='left', width=130, height=36,
                      font=theme.F_BODY, corner_radius=theme.RADIUS,
                      fg_color=c('accent'), hover_color=c('accent_hover'),
                      text_color='white',
                      command=self._run).pack(side='right')

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
        self._stage_seg = ctk.CTkSegmentedButton(
            stages.body, values=['Stage 1D', 'Stage 2D', 'Stage 3D'],
            font=theme.F_BODY, corner_radius=theme.RADIUS, height=32,
            fg_color=c('card2'), unselected_color=c('card2'),
            unselected_hover_color=c('border'),
            selected_color=c('accent'),
            selected_hover_color=c('accent_hover'),
            command=self._stage_selected)
        self._stage_seg.pack(anchor='w', pady=(0, GAP))

        stack = ctk.CTkScrollableFrame(
            stages.body, fg_color='transparent',
            scrollbar_button_color=c('card2'),
            scrollbar_button_hover_color=c('border'))
        stack.pack(fill='both', expand=True)
        self.forms = {d: CaseForm(stack, d) for d in (1, 2, 3)}
        self._stack = stack
        self._current = None
        self._stage_seg.set('Stage 1D')
        self._stage_selected('Stage 1D')

    def _stage_selected(self, value):
        d = int(value.split()[1][0])
        if self._current is not None:
            self._current.pack_forget()
        self._current = self.forms[d]
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
        os.makedirs(ws, exist_ok=True)
        p1 = os.path.join(ws, 'stage1_profile.txt')
        p2 = os.path.join(ws, 'stage2_profile.npz')

        try:
            cases = {d: self.forms[d].get_case() for d in stages}
        except ValueError as exc:
            messagebox.showerror('Chain', str(exc))
            return

        # auto-wire profile hand-offs
        if 1 in cases:
            cases[1].profile_file = p1
        if 2 in cases:
            if 1 in cases:
                cases[2].init_mode = 'profile1d'
                cases[2].profile_file_in = p1
            if cases[2].geometry != 'axisymmetric' and 3 in cases:
                messagebox.showerror(
                    'Chain', 'Stage 2 must be axisymmetric to feed 3D.')
                return
            if 3 in cases:
                cases[2].profile_file = p2
        if 3 in cases and 2 in cases:
            cases[3].init_mode = 'profile2d'
            cases[3].profile_file_in = p2

        for d, case in cases.items():
            save_case(case, os.path.join(ws, f'stage{d}_case.json'))

        self._on_run_chain([(d, cases[d]) for d in stages], ws)
