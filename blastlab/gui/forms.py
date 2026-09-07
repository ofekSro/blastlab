"""Case setup forms: one CaseForm widget per dimension + a container
that switches between them and produces/consumes Case objects.

Layout language (see theme.py): related parameters live in titled
Cards on a two-column grid; the SetupPanel pairs the scrollable form
column with a live model-preview card and a validation status card.
"""

import math
import tkinter as tk
from tkinter import filedialog, ttk

import customtkinter as ctk

from ..core.case import Case1D, Case2D, Case3D
from ..solvers.foam.materials import MATERIAL_NAMES
from . import theme
from .theme import GAP, PAD, Card, c, icon

_ROW_PAD = dict(padx=(0, GAP), pady=4)

#: caption wrap width and the minimum width reserved for the input column
#: of a parameter card, so a value is always readable at the 1100x720
#: minimum window size (see _row_lbl / _card)
LABEL_WRAP = 132
INPUT_MIN = 146


def _row_lbl(frame, r, label, widget):
    """Like _row, but also returns the label widget (for rows whose
    caption changes with the geometry, e.g. axisymmetric r/z).

    Long captions wrap instead of squeezing the input: a label like
    "Charge refinement (blastFoam)" used to take the whole card and left
    its combo ~40 px wide, showing one character of the value."""
    lbl = ctk.CTkLabel(frame, text=label, font=theme.F_BODY,
                       text_color=c('muted'), anchor='w',
                       wraplength=LABEL_WRAP, justify='left')
    lbl.grid(row=r, column=0, sticky='w', **_ROW_PAD)
    widget.grid(row=r, column=1, sticky='we', pady=4)
    return r + 1, lbl


def _row(frame, r, label, widget):
    return _row_lbl(frame, r, label, widget)[0]


def _entry(frame, var, width=150):
    ent = ctk.CTkEntry(frame, textvariable=var, width=width,
                       font=theme.F_BODY, corner_radius=8,
                       fg_color=c('entry'), border_color=c('border'))
    # keyboard focus was invisible: nothing showed which box Tab landed in
    ent.bind('<FocusIn>',
             lambda e, w=ent: w.configure(border_color=c('accent')))
    ent.bind('<FocusOut>',
             lambda e, w=ent: w.configure(border_color=c('border')))
    return ent


def _combo(frame, var, values, width=176):
    return ctk.CTkComboBox(frame, variable=var, values=list(values),
                           state='readonly', width=width,
                           font=theme.F_BODY, corner_radius=8,
                           fg_color=c('entry'), border_color=c('border'),
                           button_color=c('card2'),
                           button_hover_color=c('border'),
                           dropdown_font=theme.F_BODY)


def _f(var, name):
    """Parse a float StringVar with a helpful error.

    'nan'/'inf'/'1e400' parse as floats but are not usable geometry: they
    used to reach validation and produce messages like "r_exp = inf m
    pokes through the boundary" instead of being refused."""
    try:
        val = float(var.get())
    except ValueError:
        raise ValueError(f"'{name}' is not a number: {var.get()!r}")
    if not math.isfinite(val):
        raise ValueError(f"'{name}' must be a finite number: {var.get()!r}")
    return val


def _i(var, name):
    """Parse an integer StringVar. A fractional entry is refused rather
    than silently truncated (n_snapshots = 2.7 used to become 2)."""
    raw = var.get()
    try:
        val = float(raw)
    except ValueError:
        raise ValueError(f"'{name}' is not an integer: {raw!r}")
    if not math.isfinite(val) or val != int(val):
        raise ValueError(f"'{name}' must be a whole number: {raw!r}")
    return int(val)


class _PointList(ctk.CTkFrame):
    """Treeview of fixed-arity numeric tuples (gauges, obstacles)."""

    def __init__(self, parent, columns, on_change=None, height=4):
        super().__init__(parent, fg_color='transparent')
        self._arity = len(columns)
        self._columns = list(columns)
        self._on_change = on_change
        self.tree = ttk.Treeview(self, columns=columns, show='headings',
                                 height=height)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=58, anchor='e')
        self.tree.grid(row=0, column=0, columnspan=3, sticky='nsew',
                       pady=(0, GAP))
        self.columnconfigure(0, weight=1)

        self.entry_var = tk.StringVar()
        ent = ctk.CTkEntry(self, textvariable=self.entry_var,
                           font=theme.F_BODY, corner_radius=8,
                           fg_color=c('entry'), border_color=c('border'),
                           placeholder_text=' '.join(columns))
        ent.grid(row=1, column=0, sticky='we', padx=(0, GAP))
        ent.bind('<Return>', lambda e: self._add())
        self._entry = ent
        for col, name, cmd in ((1, 'plus', self._add),
                               (2, 'minus', self._remove)):
            ctk.CTkButton(self, text='', image=icon(name, 14), width=34,
                          height=30, corner_radius=theme.RADIUS,
                          fg_color=c('card2'), hover_color=c('border'),
                          command=cmd).grid(row=1, column=col,
                                            padx=(0, GAP if col == 1 else 0))
        # a rejected row used to vanish in silence: the text stayed in the
        # box, nothing was added and nothing said why
        self._hint = ctk.CTkLabel(self, text='', font=theme.F_SMALL,
                                  text_color=theme.c('error'), anchor='w',
                                  justify='left', wraplength=240)
        self._hint.grid(row=2, column=0, columnspan=3, sticky='we',
                        pady=(2, 0))

    def _reject(self, msg):
        self._hint.configure(text=msg)
        try:
            self._entry.configure(border_color=theme.c('error'))
        except Exception:
            pass

    def _accept(self):
        self._hint.configure(text='')
        try:
            self._entry.configure(border_color=c('border'))
        except Exception:
            pass

    def _add(self):
        text = self.entry_var.get().strip()
        raw = text.replace(',', ' ').split()
        if not raw:
            return self._reject('enter ' + ' '.join(self._columns))
        try:
            vals = [float(v) for v in raw]
        except ValueError:
            return self._reject(f'not numbers: {text!r} - expected '
                                + ' '.join(self._columns))
        if len(vals) != self._arity:
            return self._reject(
                f'expected {self._arity} numbers ('
                + ' '.join(self._columns) + f'), got {len(vals)}')
        self.tree.insert('', 'end', values=[f'{v:g}' for v in vals])
        self.entry_var.set('')
        self._accept()
        if self._on_change:
            self._on_change()

    def _remove(self):
        sel = self.tree.selection()
        if not sel:
            return self._reject('select a row in the list first')
        for item in sel:
            self.tree.delete(item)
        self._accept()
        if self._on_change:
            self._on_change()

    def get(self):
        return [tuple(float(v) for v in self.tree.item(i)['values'])
                for i in self.tree.get_children()]

    def set(self, tuples):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for tup in tuples or []:
            self.tree.insert('', 'end', values=[f'{v:g}' for v in tup])


class _FilePicker(ctk.CTkFrame):
    def __init__(self, parent, var, save=False, filetypes=None,
                 title=None):
        super().__init__(parent, fg_color='transparent')
        self.var = var
        # every dialog says what it is for - a bare "Open" gave no clue
        # which of the file fields had opened it (QA-16)
        self._dlg_title = title or ('Save file' if save else 'Open file')
        ctk.CTkEntry(self, textvariable=var, font=theme.F_BODY,
                     corner_radius=8, fg_color=c('entry'),
                     border_color=c('border')).grid(
            row=0, column=0, sticky='we', padx=(0, GAP))
        self.columnconfigure(0, weight=1)
        kind = filedialog.asksaveasfilename if save \
            else filedialog.askopenfilename
        ctk.CTkButton(self, text='', image=icon('folder', 14), width=34,
                      height=30, corner_radius=theme.RADIUS,
                      fg_color=c('card2'), hover_color=c('border'),
                      command=lambda: self._pick(kind, filetypes)).grid(
            row=0, column=1)

    def _pick(self, kind, filetypes):
        fn = kind(title=self._dlg_title,
                  filetypes=filetypes or [('All files', '*.*')])
        if fn:
            self.var.set(fn)


class CaseForm(ctk.CTkFrame):
    """Parameter form for one dimension (1, 2 or 3), as a two-column
    grid of titled cards."""

    def __init__(self, parent, dim, on_change=None):
        super().__init__(parent, fg_color='transparent')
        self.dim = dim
        self._on_change = on_change or (lambda: None)
        self.v = {}   # name -> tk variable
        self._wmap = None            # textvariable name -> widget (lazy)
        self._bad = set()            # currently red-bordered fields
        self._build()

    def _var(self, name, value=''):
        var = tk.StringVar(value=str(value))
        var.trace_add('write', lambda *a: self._on_change())
        self.v[name] = var
        return var

    def _bool(self, name, value=True):
        var = tk.BooleanVar(value=value)
        var.trace_add('write', lambda *a: self._on_change())
        self.v[name] = var
        return var

    # ── layout ───────────────────────────────────────────────────────────
    def _card(self, col, title):
        """A titled card appended to the given column; returns its grid
        body (label column 0, input column 1)."""
        card = Card(self, title=title, pad=PAD)
        card.grid(row=self._next_row[col], column=col, sticky='nwe',
                  padx=(0 if col == 0 else GAP, GAP if col == 0 else 0),
                  pady=(0, PAD - 4))
        self._next_row[col] += 1
        body = card.body
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1, minsize=INPUT_MIN)
        return body

    def _build(self):
        self.columnconfigure(0, weight=1, uniform='cols')
        self.columnconfigure(1, weight=1, uniform='cols')
        self._next_row = {0: 0, 1: 0}

        # ── Domain ─────────────────────────────────────────────────────
        dom = self._card(0, 'Domain')
        r = 0
        if self.dim == 1:
            r = _row(dom, r, 'Domain radius [m]',
                     _entry(dom, self._var('radius_m', 10.0)))
            r = _row(dom, r, 'Cell size [m]',
                     _entry(dom, self._var('cell', 0.001)))
        else:
            if self.dim == 2:
                r = _row(dom, r, 'Geometry',
                         _combo(dom, self._var('geometry', 'axisymmetric'),
                                ['axisymmetric', 'planar']))
                self.v['geometry'].trace_add(
                    'write', lambda *a: self._sync_enabled())
            # 3D starts from a case that actually validates: the old
            # 10 m / 0.1 m / 1 kg default auto-refined to 0.0105 m and
            # showed ~852 M cells (over the 15 M cap) on a fresh tab.
            # 8 kg in a 3 m box keeps the 2 cm cell as typed (3.4 M cells).
            L0 = 10.0 if self.dim == 2 else 3.0
            r, lx_lbl = _row_lbl(dom, r, 'Lx [m]',
                                 _entry(dom, self._var('Lx', L0)))
            r, ly_lbl = _row_lbl(dom, r, 'Ly [m]',
                                 _entry(dom, self._var('Ly', L0)))
            if self.dim == 2:
                self._dyn_labels = {'Lx': lx_lbl, 'Ly': ly_lbl}
            if self.dim == 3:
                r = _row(dom, r, 'Lz [m]',
                         _entry(dom, self._var('Lz', L0)))
            r = _row(dom, r, 'Cell size [m]',
                     _entry(dom, self._var('cell',
                                           0.025 if self.dim == 2 else 0.02)))

        # ── Charge / initialization ────────────────────────────────────
        chg = self._card(0, 'Charge' if self.dim == 1 else 'Initialization')
        r = 0
        if self.dim == 1:
            r = _row(chg, r, 'Charge [kg TNT]',
                     _entry(chg, self._var('charge', 1.0)))
            self._mat_combo = _combo(chg, self._var('material', 'TNT'),
                                     MATERIAL_NAMES)
            r = _row(chg, r, 'Material (blastFoam)', self._mat_combo)
        else:
            modes = (['charge', 'profile1d'] if self.dim == 2
                     else ['charge', 'profile1d', 'profile2d'])
            r = _row(chg, r, 'Initialize from',
                     _combo(chg, self._var('init_mode', 'charge'), modes))
            self.v['init_mode'].trace_add(
                'write', lambda *a: self._sync_enabled())
            r = _row(chg, r, 'Charge [kg TNT]' + (' or kg/m' if
                                                  self.dim == 2 else ''),
                     _entry(chg, self._var('charge',
                                           1.0 if self.dim == 2 else 8.0)))
            self._mat_combo = _combo(chg, self._var('material', 'TNT'),
                                     MATERIAL_NAMES)
            r = _row(chg, r, 'Material (blastFoam)', self._mat_combo)
            if self.dim == 3:
                r = _row(chg, r, 'Charge resolution',
                         _combo(chg, self._var('charge_res', 'resolve'),
                                ['resolve', 'smear']))
            r = _row(chg, r, 'Profile file',
                     _FilePicker(chg, self._var('profile_in', ''),
                                 title='Open profile file',
                                 filetypes=[('Profiles', '*.txt *.npz'),
                                            ('All files', '*.*')]))
            c0 = 5.0 if self.dim == 2 else 1.5      # centre of L0
            cx_ent = _entry(chg, self._var('cx', 0.0 if self.dim == 2
                                           else c0))
            r, cx_lbl = _row_lbl(chg, r, 'Burst x [m]', cx_ent)
            r, cy_lbl = _row_lbl(chg, r, 'Burst y [m]',
                                 _entry(chg, self._var('cy', c0)))
            if self.dim == 2:
                self._dyn_labels.update(cx=cx_lbl, cy=cy_lbl)
                self._burst_x_entry = cx_ent
            if self.dim == 3:
                r = _row(chg, r, 'Burst z [m]',
                         _entry(chg, self._var('cz', c0)))

        # ── Numerics ───────────────────────────────────────────────────
        num = self._card(0, 'Numerics')
        r = 0
        r = _row(num, r, 'Solver',
                 _combo(num, self._var('solver', 'native'),
                        ['native', 'blastfoam']))
        self.v['solver'].trace_add(
            'write', lambda *a: self._sync_enabled())
        self._eos_combo = _combo(num, self._var('eos', 'idealGas'),
                                 ['idealGas', 'JWL'])
        r = _row(num, r, 'EOS', self._eos_combo)
        self._act_combo = _combo(num, self._var('activation', 'linear'),
                                 ['linear', 'none'])
        r = _row(num, r, 'Detonation (blastFoam)', self._act_combo)
        self._ab_combo = _combo(num, self._var('afterburn', 'none'),
                                ['none', 'miller'])
        r = _row(num, r, 'Afterburn (blastFoam)', self._ab_combo)
        if self.dim > 1:
            # 'global' = today's rule (the whole grid is refined to resolve
            # the charge); 'zone' keeps the base cell and adds automatic
            # nested refinement zones around the charge (blastFoam only)
            self._cref_combo = _combo(num, self._var('charge_refine',
                                                     'global'),
                                      ['global', 'zone'])
            r = _row(num, r, 'Charge refinement (blastFoam)',
                     self._cref_combo)
        r = _row(num, r, 'Snapshots',
                 _entry(num, self._var('n_snapshots',
                                       5 if self.dim == 1 else 6)))
        r = _row(num, r, 'CFL',
                 _entry(num, self._var('cfl', {1: 0.5, 2: 0.4,
                                               3: 0.30}[self.dim])))
        if self.dim > 1:
            # blastFoam MPI ranks; 1D always runs serial so no field
            self._nproc_entry = _entry(num, self._var('n_procs', 0))
            r = _row(num, r, 'MPI ranks (0 = auto)', self._nproc_entry)
        if self.dim == 3:
            r = _row(num, r, 'End time [s] (0 = auto)',
                     _entry(num, self._var('t_end', 0.0)))
            r = _row(num, r, 'Live slice normal',
                     _combo(num, self._var('slice_axis', 'y'),
                            ['x', 'y', 'z']))
            r = _row(num, r, 'Slice position [m]\n(blank = burst)',
                     _entry(num, self._var('slice_pos', '')))

        # ── Dynamic refinement (blastFoam adaptiveFvMesh, N16) ─────────
        if self.dim > 1:
            from ..core.refine import AMR_ESTIMATORS, MAX_AMR_LEVEL
            amr = self._card(0, 'Dynamic refinement (blastFoam)')
            r = 0
            self._amr_levels_combo = _combo(
                amr, self._var('amr_levels', '0'),
                [str(i) for i in range(MAX_AMR_LEVEL + 1)])
            r = _row(amr, r, 'AMR levels (0 = off)', self._amr_levels_combo)
            self.v['amr_levels'].trace_add(
                'write', lambda *a: self._sync_enabled())
            self._amr_est_combo = _combo(
                amr, self._var('amr_estimator', 'densityGradient'),
                list(AMR_ESTIMATORS))
            r = _row(amr, r, 'Error estimator', self._amr_est_combo)
            self._amr_entries = []
            for key, label, default in (
                    ('amr_refine', 'Refine above', 0.4),
                    ('amr_unrefine', 'Unrefine below', 0.2),
                    ('amr_interval', 'Refine every [steps]', 2),
                    ('amr_buffer', 'Buffer layers', 2),
                    ('amr_max_cells', 'Max cells (0 = default)', 0)):
                w = _entry(amr, self._var(key, default))
                r = _row(amr, r, label, w)
                self._amr_entries.append(w)
            self._amr_disp_combo = _combo(
                amr, self._var('amr_display_level', 'auto'),
                ['auto'] + [str(i) for i in range(MAX_AMR_LEVEL + 1)])
            r = _row(amr, r, 'Display level', self._amr_disp_combo)
            if 'charge_refine' in self.v:
                # picking 'zone' while AMR is on snaps back to 'global'
                self.v['charge_refine'].trace_add(
                    'write', lambda *a: self._sync_enabled())

        # ── Boundaries ─────────────────────────────────────────────────
        if self.dim > 1:
            bcf = self._card(0, 'Boundaries')
            for col in (1, 3):
                bcf.columnconfigure(col, weight=1)
            bcf.columnconfigure(2, minsize=GAP * 2)
            sides = (['x_lo', 'x_hi', 'y_lo', 'y_hi'] if self.dim == 2 else
                     ['x_lo', 'x_hi', 'y_lo', 'y_hi', 'z_lo', 'z_hi'])
            defaults = (dict(x_lo='wall', x_hi='open', y_lo='wall',
                             y_hi='open') if self.dim == 2 else
                        dict(x_lo='open', x_hi='open', y_lo='open',
                             y_hi='open', z_lo='wall', z_hi='open'))
            self._bc_combos = {}
            for i, side in enumerate(sides):
                ctk.CTkLabel(bcf, text=side, font=theme.F_BODY,
                             text_color=c('muted'), anchor='w').grid(
                    row=i // 2, column=(i % 2) * 2, sticky='w',
                    padx=(0, GAP), pady=4)
                cb = _combo(bcf, self._var(f'bc_{side}', defaults[side]),
                            ['open', 'wall'], width=96)
                cb.grid(row=i // 2, column=(i % 2) * 2 + 1, sticky='we',
                        padx=(0, GAP if i % 2 == 0 else 0), pady=4)
                self._bc_combos[side] = cb

        # ── right column: gauges / obstacles / outputs ─────────────────
        if self.dim == 1:
            gf = self._card(1, 'Gauge radii [m]')
            self.gauges = _PointList(gf, ['r'], self._on_change)
            self.gauges.grid(row=0, column=0, columnspan=2, sticky='nsew')
        else:
            cols = ['x', 'y'] if self.dim == 2 else ['x', 'y', 'z']
            gf = self._card(1, 'Gauges [m]')
            self.gauges = _PointList(gf, cols, self._on_change)
            self.gauges.grid(row=0, column=0, columnspan=2, sticky='nsew')

            ocols = (['x0', 'x1', 'y0', 'y1'] if self.dim == 2
                     else ['x0', 'x1', 'y0', 'y1', 'z0', 'z1'])
            of = self._card(1, 'Obstacles [m]')
            self.obstacles = _PointList(of, ocols, self._on_change)
            self.obstacles.grid(row=0, column=0, columnspan=2,
                                sticky='nsew')

            # blastFoam local refinement zones: a box + a level (1 = base
            # cell / 2, 2 = / 4, ...); validation blocks them on native
            zf = self._card(1, 'Refinement zones [m, level]')
            self.zones = _PointList(zf, ocols + ['level'], self._on_change,
                                    height=3)
            self.zones.grid(row=0, column=0, columnspan=2, sticky='nsew')

            # blastFoam-only extras (validation blocks them on native)
            if self.dim == 3:
                xc = self._card(1, 'Extra charges [m, kg]')
                self.extra_charges = _PointList(
                    xc, ['x', 'y', 'z', 'kg'], self._on_change, height=3)
                self.extra_charges.grid(row=0, column=0, columnspan=2,
                                        sticky='nsew')
            dcols = ['x', 'y'] if self.dim == 2 else ['x', 'y', 'z']
            dc = self._card(1, 'Detonation points [m]')
            self.det_pts = _PointList(dc, dcols, self._on_change,
                                      height=3)
            self.det_pts.grid(row=0, column=0, columnspan=2,
                              sticky='nsew')

        out = self._card(1, 'Outputs')
        orow = 0
        orow = _row(out, orow, 'Gauge TSV',
                    _entry(out, self._var('gauge_file',
                                          f'gauges_{self.dim}d.txt'
                                          if self.dim > 1 else 'gauges.txt')))
        if self.dim > 1:
            orow = _row(out, orow, 'Animation (gif)',
                        _entry(out, self._var(
                            'anim_file', f'blast_{self.dim}d_animation.gif')))
            ctk.CTkCheckBox(out, text='Record replay frames',
                            variable=self._bool('record', True),
                            font=theme.F_BODY, corner_radius=6,
                            border_color=c('border'),
                            fg_color=c('accent'),
                            hover_color=c('accent_hover')).grid(
                row=orow, column=0, columnspan=2, sticky='w', pady=(GAP, 4))
            orow += 1
        if self.dim == 1:
            orow = _row(out, orow, 'Profile out (.txt)',
                        _entry(out, self._var('profile_out',
                                              'blast_profile.txt')))
        elif self.dim == 2:
            orow = _row(out, orow, 'Profile out (.npz)',
                        _entry(out, self._var('profile_out', '')))

        self._sync_enabled()

    def _sync_enabled(self):
        if self.dim == 2 and 'geometry' in self.v:
            axisym = self.v['geometry'].get() == 'axisymmetric'
            if hasattr(self, '_bc_combos'):
                self._bc_combos['x_lo'].configure(
                    state='disabled' if axisym else 'readonly')
                if axisym:
                    self.v['bc_x_lo'].set('wall')
            # axisym: the domain is the (r, z) half-plane revolved about
            # the axis - relabel, and pin the burst to the axis (r = 0)
            texts = (dict(Lx='Radius R [m]', Ly='Height Z [m]',
                          cx='Burst r [m]', cy='Burst z [m]') if axisym
                     else dict(Lx='Lx [m]', Ly='Ly [m]',
                               cx='Burst x [m]', cy='Burst y [m]'))
            for key, lbl in getattr(self, '_dyn_labels', {}).items():
                lbl.configure(text=texts[key])
            if hasattr(self, '_burst_x_entry'):
                if axisym:
                    self.v['cx'].set('0')
                    self._burst_x_entry.configure(state='disabled')
                else:
                    self._burst_x_entry.configure(state='normal')
        # blastfoam: material choice applies, EOS is fixed (JWL products
        # + ideal-gas air); native: TNT-only, EOS choice applies
        if 'solver' in self.v and hasattr(self, '_mat_combo'):
            foam = self.v['solver'].get() == 'blastfoam'
            self._eos_combo.configure(
                state='disabled' if foam else 'readonly')
            self._mat_combo.configure(
                state='readonly' if foam else 'disabled')
            if not foam and self.v['material'].get() != 'TNT':
                self.v['material'].set('TNT')
            if hasattr(self, '_nproc_entry'):
                self._nproc_entry.configure(
                    state='normal' if foam else 'disabled')
            self._act_combo.configure(
                state='readonly' if foam else 'disabled')
            if not foam and self.v['activation'].get() != 'linear':
                self.v['activation'].set('linear')
            if hasattr(self, '_ab_combo'):
                self._ab_combo.configure(
                    state='readonly' if foam else 'disabled')
                if not foam and self.v['afterburn'].get() != 'none':
                    self.v['afterburn'].set('none')
            if hasattr(self, '_cref_combo'):
                self._cref_combo.configure(
                    state='readonly' if foam else 'disabled')
                if not foam and self.v['charge_refine'].get() != 'global':
                    self.v['charge_refine'].set('global')
            if hasattr(self, '_amr_disp_combo'):
                # dynamic AMR: blastFoam only; its coefficients apply only
                # while it is on, and it excludes the static zones / the
                # 'zone' charge mode (validation refuses the combination)
                self._amr_levels_combo.configure(
                    state='readonly' if foam else 'disabled')
                if not foam and self.v['amr_levels'].get() != '0':
                    self.v['amr_levels'].set('0')
                amr_on = foam and self.v['amr_levels'].get().strip() \
                    not in ('', '0')
                for w in self._amr_entries:
                    w.configure(state='normal' if amr_on else 'disabled')
                for w in (self._amr_est_combo, self._amr_disp_combo):
                    w.configure(state='readonly' if amr_on else 'disabled')
                if hasattr(self, '_cref_combo'):
                    self._cref_combo.configure(
                        state='readonly' if foam and not amr_on
                        else 'disabled')
                    if amr_on and self.v['charge_refine'].get() != 'global':
                        self.v['charge_refine'].set('global')

    # ── Case conversion ─────────────────────────────────────────────────
    def _widget_for(self, name):
        """The entry/combo bound to a variable name, for the red-border
        marking. Built lazily by walking the form once and matching each
        widget's `textvariable` against the vars in self.v."""
        var = self.v.get(name)
        if var is None:
            return None
        if self._wmap is None:
            self._wmap = {}
            stack = [self]
            while stack:
                w = stack.pop()
                stack.extend(w.winfo_children())
                try:
                    tv = w.cget('textvariable')
                except Exception:
                    tv = None
                if tv:
                    self._wmap[str(tv)] = w
        return self._wmap.get(str(var))

    def mark_fields(self, names):
        """Red-border exactly `names` (and clear any previous marks), so a
        parse error points at the field it came from instead of only
        naming it in the status strip."""
        names = set(names or ())
        for name in self._bad | names:
            w = self._widget_for(name)
            if w is None:
                continue
            try:
                w.configure(border_color=(theme.c('error') if name in names
                                          else c('border')))
            except Exception:
                pass
        self._bad = names

    def get_case(self):
        """Build the Case. EVERY bad numeric field is reported, not just
        the first one: the strip used to show a single message and the
        user fixed them one reload at a time."""
        v = self.v
        errs, bad = [], []

        def _F(name, label):
            try:
                return _f(v[name], label)
            except ValueError as exc:
                errs.append(str(exc))
                bad.append(name)
                return 0.0

        def _I(name, label):
            try:
                return _i(v[name], label)
            except ValueError as exc:
                errs.append(str(exc))
                bad.append(name)
                return 0

        def _done(case):
            self.mark_fields(bad)
            if errs:
                raise ValueError('\n'.join(errs))
            return case

        if self.dim == 1:
            return _done(Case1D(
                radius_m=_F('radius_m', 'radius'),
                charge_kg=_F('charge', 'charge'),
                cell_size_m=_F('cell', 'cell size'),
                eos=v['eos'].get(), cfl=_F('cfl', 'cfl'),
                n_snapshots=_I('n_snapshots', 'snapshots'),
                gauge_radii=[g[0] for g in self.gauges.get()],
                gauge_file=v['gauge_file'].get(),
                profile_file=v['profile_out'].get() or None,
                solver=v['solver'].get(), material=v['material'].get(),
                activation=v['activation'].get(),
                afterburn=v['afterburn'].get()))

        bcs = {side: v[f'bc_{side}'].get()
               for side in (['x_lo', 'x_hi', 'y_lo', 'y_hi'] if self.dim == 2
                            else ['x_lo', 'x_hi', 'y_lo', 'y_hi',
                                  'z_lo', 'z_hi'])}
        common = dict(
            Lx=_F('Lx', 'Lx'), Ly=_F('Ly', 'Ly'),
            cell_size_m=_F('cell', 'cell size'),
            init_mode=v['init_mode'].get(),
            charge=_F('charge', 'charge'),
            profile_file_in=v['profile_in'].get() or None,
            eos=v['eos'].get(), bcs=bcs,
            obstacles=self.obstacles.get(), cfl=_F('cfl', 'cfl'),
            n_snapshots=_I('n_snapshots', 'snapshots'),
            gauges=self.gauges.get(),
            gauge_file=v['gauge_file'].get(),
            anim_file=v['anim_file'].get() or None,
            record_frames=150 if v['record'].get() else 0,
            solver=v['solver'].get(), material=v['material'].get(),
            activation=v['activation'].get(),
            afterburn=v['afterburn'].get(),
            n_procs=_I('n_procs', 'MPI ranks'),
            det_points=self.det_pts.get() or None,
            refine_zones=[(*z[:-1], int(round(z[-1])))
                          for z in self.zones.get()],
            charge_refine=v['charge_refine'].get(),
            amr_levels=_I('amr_levels', 'AMR levels'),
            amr_estimator=v['amr_estimator'].get(),
            amr_refine=_F('amr_refine', 'AMR refine threshold'),
            amr_unrefine=_F('amr_unrefine', 'AMR unrefine threshold'),
            amr_interval=_I('amr_interval', 'AMR refine interval'),
            amr_buffer=_I('amr_buffer', 'AMR buffer layers'),
            amr_max_cells=_I('amr_max_cells', 'AMR max cells'),
            amr_display_level=(
                None if v['amr_display_level'].get().strip() in ('', 'auto')
                else _I('amr_display_level', 'AMR display level')),
        )
        if self.dim == 2:
            return _done(Case2D(geometry=v['geometry'].get(),
                                center=(_F('cx', 'burst x'),
                                        _F('cy', 'burst y')),
                                profile_file=v['profile_out'].get() or None,
                                **common))
        slice_raw = v['slice_pos'].get().strip()
        return _done(Case3D(Lz=_F('Lz', 'Lz'),
                            center=(_F('cx', 'burst x'),
                                    _F('cy', 'burst y'),
                                    _F('cz', 'burst z')),
                            charge_resolution=v['charge_res'].get(),
                            t_end=_F('t_end', 'end time'),
                            slice_axis=v['slice_axis'].get(),
                            slice_pos=(_F('slice_pos', 'slice position')
                                       if slice_raw else None),
                            charges=self.extra_charges.get() or None,
                            **common))

    def set_case(self, case):
        v = self.v
        if self.dim == 1:
            v['radius_m'].set(f'{case.radius_m:g}')
            v['charge'].set(f'{case.charge_kg:g}')
            v['solver'].set(getattr(case, 'solver', 'native'))
            v['material'].set(getattr(case, 'material', 'TNT'))
            v['activation'].set(getattr(case, 'activation', 'linear'))
            v['afterburn'].set(getattr(case, 'afterburn', 'none') or 'none')
            v['cell'].set(f'{case.cell_size_m:g}')
            v['eos'].set(case.eos)
            v['cfl'].set(f'{case.cfl:g}')
            v['n_snapshots'].set(str(case.n_snapshots))
            self.gauges.set([(g,) for g in case.gauge_radii])
            v['gauge_file'].set(case.gauge_file)
            v['profile_out'].set(case.profile_file or '')
            return
        if self.dim == 2:
            v['geometry'].set(case.geometry)
        v['Lx'].set(f'{case.Lx:g}')
        v['Ly'].set(f'{case.Ly:g}')
        if self.dim == 3:
            v['Lz'].set(f'{case.Lz:g}')
        v['cell'].set(f'{case.cell_size_m:g}')
        v['init_mode'].set(case.init_mode)
        v['charge'].set(f'{case.charge:g}' if case.charge is not None else '')
        if self.dim == 3:
            v['charge_res'].set(getattr(case, 'charge_resolution', 'resolve'))
            v['t_end'].set(f'{getattr(case, "t_end", 0.0):g}')
            v['slice_axis'].set(getattr(case, 'slice_axis', 'y'))
            sp = getattr(case, 'slice_pos', None)
            v['slice_pos'].set('' if sp is None else f'{sp:g}')
        v['profile_in'].set(case.profile_file_in or '')
        v['cx'].set(f'{case.center[0]:g}')
        v['cy'].set(f'{case.center[1]:g}')
        if self.dim == 3 and len(case.center) > 2:
            v['cz'].set(f'{case.center[2]:g}')
        v['solver'].set(getattr(case, 'solver', 'native'))
        v['material'].set(getattr(case, 'material', 'TNT'))
        v['activation'].set(getattr(case, 'activation', 'linear'))
        v['afterburn'].set(getattr(case, 'afterburn', 'none') or 'none')
        v['charge_refine'].set(getattr(case, 'charge_refine', 'global'))
        v['amr_levels'].set(str(int(getattr(case, 'amr_levels', 0) or 0)))
        v['amr_estimator'].set(getattr(case, 'amr_estimator',
                                       'densityGradient') or 'densityGradient')
        for key, default in (('amr_refine', 0.4), ('amr_unrefine', 0.2),
                             ('amr_interval', 2), ('amr_buffer', 2),
                             ('amr_max_cells', 0)):
            v[key].set(f'{getattr(case, key, default):g}')
        dl = getattr(case, 'amr_display_level', None)
        v['amr_display_level'].set('auto' if dl is None else str(int(dl)))
        v['n_procs'].set(str(getattr(case, 'n_procs', 0)))
        v['eos'].set(case.eos)
        v['cfl'].set(f'{case.cfl:g}')
        v['n_snapshots'].set(str(case.n_snapshots))
        for side, val in case.bcs.items():
            v[f'bc_{side}'].set(val)
        self.gauges.set(case.gauges)
        self.obstacles.set(case.obstacles)
        self.zones.set(getattr(case, 'refine_zones', None) or [])
        if self.dim == 3:
            self.extra_charges.set(getattr(case, 'charges', None) or [])
        self.det_pts.set(getattr(case, 'det_points', None) or [])
        v['gauge_file'].set(case.gauge_file)
        v['anim_file'].set(case.anim_file or '')
        v['record'].set(case.record_frames > 0)
        if self.dim == 2:
            v['profile_out'].set(case.profile_file or '')


class SetupPanel(ctk.CTkFrame):
    """Dimension selector + the three CaseForms + validation card,
    with a live model preview on the right (2D matplotlib drawing or
    3D pyvista render)."""

    _PREV_HINT = 'Select 2D or 3D to preview the model here.'

    def __init__(self, parent, on_change=None):
        super().__init__(parent, fg_color='transparent')
        self._on_change = on_change or (lambda: None)

        # the form column carries two cards of label+input side by side and
        # is the one that runs out of room first; the preview only loses
        # some empty margin (weights were 11:9)
        self.columnconfigure(0, weight=13, uniform='main')
        self.columnconfigure(1, weight=7, uniform='main')
        self.rowconfigure(1, weight=1)

        # header: title + dimension selector
        head = ctk.CTkFrame(self, fg_color='transparent')
        head.grid(row=0, column=0, columnspan=2, sticky='we',
                  pady=(0, PAD - 4))
        ctk.CTkLabel(head, text='Case Setup', font=theme.F_H1,
                     text_color=c('text')).pack(side='left')
        self.dim_var = tk.IntVar(value=2)
        self._dim_seg = ctk.CTkSegmentedButton(
            head, values=['1D', '2D', '3D'], font=theme.F_BODY,
            corner_radius=theme.RADIUS, height=34,
            fg_color=c('card'), unselected_color=c('seg'),
            unselected_hover_color=c('card2'),
            selected_color=c('accent'),
            selected_hover_color=c('accent_hover'),
            command=self._dim_selected)
        self._dim_seg.set('2D')
        self._dim_seg.pack(side='right')

        # left: scrollable form column
        self._form_host = ctk.CTkScrollableFrame(
            self, fg_color='transparent',
            scrollbar_button_color=c('card2'),
            scrollbar_button_hover_color=c('border'))
        self._form_host.grid(row=1, column=0, sticky='nsew',
                             padx=(0, GAP))

        # left bottom: validation status card
        self._status_card = Card(self, title=None)
        self._status_card.grid(row=2, column=0, sticky='we',
                               padx=(0, GAP), pady=(GAP, 0))
        # a long report (AMR + zones + foam notes can be 8 lines) used to
        # grow the card until the form above it had a third of its height;
        # cap it and scroll instead
        self._status_body = ctk.CTkScrollableFrame(
            self._status_card.body, fg_color='transparent', height=104,
            scrollbar_button_color=c('card2'),
            scrollbar_button_hover_color=c('border'))
        self._status_body.pack(fill='both', expand=True)
        self._status_rows = []

        # right: preview card
        prev_card = Card(self, title='Model Preview')
        prev_card.grid(row=1, column=1, rowspan=2, sticky='nsew',
                       padx=(GAP, 0))
        host = prev_card.body
        self._last_case = None
        self.show_mesh_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            prev_card, text='Show mesh', variable=self.show_mesh_var,
            command=self._mesh_toggled, font=theme.F_BODY, corner_radius=6,
            checkbox_width=19, checkbox_height=19, border_width=2,
            border_color=c('border'), fg_color=c('accent'),
            hover_color=c('accent_hover')).pack(
            anchor='w', padx=PAD, pady=(0, 2), before=host)
        self._prev_msg = ctk.CTkLabel(host, text=self._PREV_HINT,
                                      font=theme.F_BODY,
                                      text_color=c('muted'))
        from .preview_panel import Preview2DPanel
        self.preview2d = Preview2DPanel(host)
        self.preview = None                      # the 3D panel
        from ..viz3d import MISSING_MSG, pyvista_available
        if pyvista_available():
            from .preview_panel import Preview3DPanel
            self.preview = Preview3DPanel(host)
        self._missing3d = MISSING_MSG
        self._prev_current = None
        self._show_preview_widget(self._prev_msg)

        self._forms = {d: CaseForm(self._form_host, d, self._changed)
                       for d in (1, 2, 3)}
        self._current = None
        self._swap()

    def _dim_selected(self, value):
        self.dim_var.set(int(value[0]))
        self._swap()

    def _swap(self):
        if self._current is not None:
            self._current.pack_forget()
        self._current = self._forms[self.dim_var.get()]
        self._current.pack(fill='both', expand=True)
        self._changed()

    def _changed(self):
        self._on_change()

    def _show_preview_widget(self, widget):
        if self._prev_current is widget:
            return
        if self._prev_current is not None:
            self._prev_current.pack_forget()
        self._prev_current = widget
        widget.pack(fill='both', expand=True)

    def update_preview(self, case):
        """Refresh the model preview (case is a parsed Case, or None
        when the form doesn't parse - the last good preview is kept).
        Called via the App's debounce."""
        if case is None:
            if self.dim_var.get() == 1:
                self._prev_msg.configure(text=self._PREV_HINT)
                self._show_preview_widget(self._prev_msg)
            return
        self._last_case = case
        show_mesh = bool(self.show_mesh_var.get())
        if case.dim == 2:
            self.preview2d.show_case(case, show_mesh=show_mesh)
            self._show_preview_widget(self.preview2d)
        elif case.dim == 3:
            if self.preview is None:
                self._prev_msg.configure(text=self._missing3d)
                self._show_preview_widget(self._prev_msg)
                return
            self.preview.show_case(case, show_mesh=show_mesh)
            self._show_preview_widget(self.preview)
        else:
            self._prev_msg.configure(text=self._PREV_HINT)
            self._show_preview_widget(self._prev_msg)

    def _mesh_toggled(self):
        if self._last_case is not None:
            self.update_preview(self._last_case)

    @property
    def form(self):
        return self._forms[self.dim_var.get()]

    def get_case(self):
        return self.form.get_case()

    def set_case(self, case):
        self.dim_var.set(case.dim)
        self._dim_seg.set(f'{case.dim}D')
        self._swap()
        self.form.set_case(case)

    def show_report(self, errors=(), warnings=(), notes=()):
        # destroy only the rows we created: the body is a scrollable frame
        # whose own canvas/scrollbar must survive
        for row in self._status_rows:
            row.destroy()
        self._status_rows = []
        rows = ([('error', 'error', m) for m in errors]
                + [('warning', 'warn', m) for m in warnings]
                + [('info', 'muted', m) for m in notes])
        if not rows:
            rows = [('check', 'ok', 'Case OK')]
        for name, colorkey, msg in rows:
            row = ctk.CTkFrame(self._status_body, fg_color='transparent')
            self._status_rows.append(row)
            row.pack(fill='x', pady=1)
            ctk.CTkLabel(row, text='', width=18,
                         image=icon(name, 13,
                                    color=theme.DARK[colorkey])).pack(
                side='left', padx=(0, 6))
            ctk.CTkLabel(row, text=msg, font=theme.F_BODY, justify='left',
                         anchor='w', wraplength=520,
                         text_color=(theme.LIGHT[colorkey],
                                     theme.DARK[colorkey])).pack(
                side='left', fill='x', expand=True)
