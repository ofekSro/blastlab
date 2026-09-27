"""Case setup forms: one CaseForm widget per dimension + a container
that switches between them and produces/consumes Case objects.

Layout language (see theme.py): related parameters live in titled
Cards on a two-column grid; the SetupPanel pairs the scrollable form
column with a live model-preview card and a validation status card.
"""

import tkinter as tk
from tkinter import filedialog, ttk

import customtkinter as ctk

from ..core.bc import BC_KINDS
from ..core.case import TRIGGER_ACTIONS
from ..core.constants import ANIM_SCALE_LABELS, anim_scale_from_label
from ..models import fields
from ..solvers.foam.materials import MATERIAL_NAMES
from . import mode as mode_mod
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


# The parsers live in models/fields.py (docs/ARCHITECTURE_REVIEW.md
# section 5, Phase 5b); these take a tk variable, as they always did.
def _trig(var):
    """`models.fields.parse_trigger` of a tk variable."""
    return fields.parse_trigger(var.get())


def _f(var, name):
    """`models.fields.parse_float` of a tk variable."""
    return fields.parse_float(var.get(), name)


def _i(var, name):
    """`models.fields.parse_int` of a tk variable."""
    return fields.parse_int(var.get(), name)


def _parse_cell(kind, value):
    """One table cell by its column kind (OUT-2, batch plan D7): 'axis'
    -> 'x' | 'y' | 'z', anything else -> float. Raises ValueError."""
    if kind == 'axis':
        return fields.parse_plane_axis(value)
    return float(value)


def _fmt_cell(kind, value):
    return str(value) if kind == 'axis' else f'{float(value):g}'


class _PointList(ctk.CTkFrame):
    """Treeview of fixed-arity numeric tuples (gauges, obstacles).
    `kinds` gives a column its own parser, as the Qt PointList: 'axis'
    (x / y / z) or 'float' (the default) - the VTK plane table."""

    def __init__(self, parent, columns, on_change=None, height=4,
                 kinds=()):
        super().__init__(parent, fg_color='transparent')
        self._arity = len(columns)
        self._columns = list(columns)
        self._kinds = tuple(kinds) or ('float',) * self._arity
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
        # UX-03: placeholder_text is dead with a textvariable bound -
        # CTkEntry 6.0 compares the StringVar OBJECT to "" and never
        # activates it - so the format hint lives in the label below
        # instead (muted when idle, red when a row is refused)
        ent = ctk.CTkEntry(self, textvariable=self.entry_var,
                           font=theme.F_BODY, corner_radius=8,
                           fg_color=c('entry'), border_color=c('border'))
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
        # box, nothing was added and nothing said why. At rest the same
        # label carries the format hint (UX-03).
        self._hint_rest = 'add a row: ' + '  '.join(columns)
        self._hint = ctk.CTkLabel(self, text=self._hint_rest,
                                  font=theme.F_SMALL,
                                  text_color=c('muted'), anchor='w',
                                  justify='left', wraplength=240)
        self._hint.grid(row=2, column=0, columnspan=3, sticky='we',
                        pady=(2, 0))

    def _reject(self, msg):
        self._hint.configure(text=msg, text_color=theme.c('error'))
        try:
            self._entry.configure(border_color=theme.c('error'))
        except Exception:
            pass

    def _accept(self):
        self._hint.configure(text=self._hint_rest, text_color=c('muted'))
        try:
            self._entry.configure(border_color=c('border'))
        except Exception:
            pass

    def _add(self):
        text = self.entry_var.get().strip()
        raw = text.replace(',', ' ').split()
        if not raw:
            return self._reject('enter ' + ' '.join(self._columns))
        if any(k != 'float' for k in self._kinds):
            if len(raw) != self._arity:
                return self._reject(
                    f'expected {self._arity} values ('
                    + ' '.join(self._columns) + f'), got {len(raw)}')
            try:
                vals = [_parse_cell(k, x) for k, x in zip(self._kinds, raw)]
            except ValueError as exc:
                return self._reject(str(exc))
        else:
            try:
                vals = [float(v) for v in raw]
            except ValueError:
                return self._reject(f'not numbers: {text!r} - expected '
                                    + ' '.join(self._columns))
        if len(vals) != self._arity:
            return self._reject(
                f'expected {self._arity} numbers ('
                + ' '.join(self._columns) + f'), got {len(vals)}')
        self.tree.insert('', 'end', values=[
            _fmt_cell(k, v) for k, v in zip(self._kinds, vals)])
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
        return [tuple(_parse_cell(k, v) for k, v in
                      zip(self._kinds, self.tree.item(i)['values']))
                for i in self.tree.get_children()]

    def set(self, tuples):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for tup in tuples or []:
            self.tree.insert('', 'end', values=[
                _fmt_cell(k, v) for k, v in zip(self._kinds, tup)])
        # P21, as the Qt PointList: a refused row does not survive a load
        self.entry_var.set('')
        self._accept()


class _MatrixVar:
    """The VTK quantity matrix (OUT-2) as a form variable: `get()` gives
    {column: [field, ...]} (models.fields.vtk_matrix), `set()` ticks the
    boxes and fires the traces once, `trace_add('write', cb)` registers a
    callback - the surface the form's `v` dict expects of a tk variable.
    Each cell is a BooleanVar owned by `_MatrixGrid`."""

    def __init__(self, dim):
        self._dim = int(dim)
        self.cells = {}                     # (field, column) -> BooleanVar
        self._traces = []

    def get(self):
        value = {}
        for (f, col), bv in self.cells.items():
            if bv.get():
                value.setdefault(col, []).append(f)
        return fields.vtk_matrix(value, self._dim)

    def set(self, value):
        m = fields.vtk_matrix(value, self._dim)
        for (f, col), bv in self.cells.items():
            bv.set(f in m.get(col, ()))
        self.fire()

    def trace_add(self, _mode, callback):
        self._traces.append(callback)
        return callback

    def fire(self):
        for cb in list(self._traces):
            cb()


class _MatrixGrid(ctk.CTkFrame):
    """Viper's "Output Quantities" grid (plan sec. 3.2), the twin of the
    Qt MatrixGrid: a row per quantity, a tick box per destination column,
    and the Gauges column display only - p, rho, U ticked and disabled
    (decision 4)."""

    def __init__(self, parent, var, dim):
        super().__init__(parent, fg_color='transparent')
        from ..models.case import vtk_fields_for
        cols = fields.VTK_COLUMNS[int(dim)]
        self.locked = []      # the Gauges boxes' vars: a tk variable that
        #                       is garbage-collected unticks its box
        self.columnconfigure(0, weight=1)
        # full-word headers - the card spans both columns (owner decision
        # P13); the longer descriptions are tooltips, as on the Qt grid
        for j, col in enumerate(cols, start=1):
            head = ctk.CTkLabel(self, text=fields.vtk_column_label(dim, col),
                                font=theme.F_SMALL, text_color=c('muted'))
            head.grid(row=0, column=j, padx=2)
            theme.tooltip(head, fields.vtk_column_tip(dim, col))
        for i, f in enumerate(vtk_fields_for(int(dim)), start=1):
            name = ctk.CTkLabel(self,
                                text=fields.VTK_QUANTITY_LABELS.get(f, f),
                                font=theme.F_BODY, text_color=c('muted'),
                                anchor='w')
            name.grid(row=i, column=0, sticky='w')
            theme.tooltip(name, fields.vtk_quantity_tip(f))
            for j, col in enumerate(cols, start=1):
                bv = tk.BooleanVar(value=(col == 'gauges'
                                          and f in fields.VTK_GAUGE_FIELDS))
                box = ctk.CTkCheckBox(
                    self, text='', variable=bv, width=24,
                    checkbox_width=18, checkbox_height=18, border_width=2,
                    corner_radius=5, border_color=c('border'),
                    fg_color=c('accent'), hover_color=c('accent_hover'),
                    command=var.fire)
                box.grid(row=i, column=j, pady=1)
                if col == 'gauges':
                    # CTk draws a disabled tick in the accent colour, so
                    # a locked box looked live: draw it muted
                    box.configure(state='disabled', fg_color=c('muted'))
                    self.locked.append((bv, box))
                else:
                    var.cells[(f, col)] = bv


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
    grid of titled cards.

    The form lays itself out for a solver `mode` (T34): rows and cards
    that only apply to the other solver are hidden (grid_remove), never
    greyed, and their Tk variables keep whatever the user typed so
    switching back restores them. The mode is pushed in by the container
    (`set_mode`); the form itself never subscribes to anything, so it is
    usable standalone."""

    def __init__(self, parent, dim, on_change=None, mode=mode_mod.DEFAULT):
        super().__init__(parent, fg_color='transparent')
        self.dim = dim
        self._on_change = on_change or (lambda: None)
        self.v = {}   # name -> tk variable
        self._wmap = None            # textvariable name -> widget (lazy)
        self._bad = set()            # currently red-bordered fields
        self._mode = mode_mod.normalize(mode)
        # grid-managed widgets (row labels, inputs, whole Cards) that only
        # exist for one solver
        self._scoped = {'native': [], 'blastfoam': []}
        self._amr_rows = []          # (label, widget): shown while AMR > 0
        self._cref_row = None        # (label, widget): hidden while AMR on
        self._aclim_rows = []        # (label, widget): manual video range
        self._build()

    @property
    def mode(self):
        return self._mode

    def set_mode(self, mode):
        m = mode_mod.normalize(mode)
        if m == self._mode:
            return
        self._mode = m
        self._apply_mode()
        self._on_change()

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
    def _card(self, col, title, scope=None):
        """A titled card appended to the given column; returns its grid
        body (label column 0, input column 1). `scope` ('native' |
        'blastfoam') makes the whole card solver-specific."""
        card = Card(self, title=title, pad=PAD)
        card.grid(row=self._next_row[col], column=col, sticky='nwe',
                  padx=(0 if col == 0 else GAP, GAP if col == 0 else 0),
                  pady=(0, PAD - 4))
        self._next_row[col] += 1
        if scope:
            self._scoped[scope].append(card)
        body = card.body
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1, minsize=INPUT_MIN)
        return body

    def _srow(self, frame, r, label, widget, scope=None):
        """_row_lbl plus solver scoping; returns (next row, label,
        widget) so callers can keep the pair for later show/hide."""
        r, lbl = _row_lbl(frame, r, label, widget)
        if scope:
            self._scoped[scope] += [lbl, widget]
        return r, lbl, widget

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
                    'write', lambda *a: self._sync_geometry())
            # Both forms start from a case that actually validates ON A
            # 4 GB WSL VM (QA-14 set the invariant; T48's memory-derived
            # caps re-sized it): 2D is 1 kg in a 4 m box (368k cells with
            # blastFoam's 8-cell charge rule), 3D is 25 kg in a 1.5 m box
            # (457k cells) - clean, no warnings, in both solver modes.
            # The old 3 m / 8 kg 3D seed became 11.7M cells under the
            # 8-cell rule, ~30 GB inside the solver.
            L0 = 4.0 if self.dim == 2 else 1.5
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
                     _entry(dom, self._var('cell', 0.025)))

        # ── Charge / initialization ────────────────────────────────────
        chg = self._card(0, 'Charge' if self.dim == 1 else 'Initialization')
        r = 0
        if self.dim == 1:
            r = _row(chg, r, 'Charge [kg TNT]',
                     _entry(chg, self._var('charge', 1.0)))
            self._mat_combo = _combo(chg, self._var('material', 'TNT'),
                                     MATERIAL_NAMES)
            # N11/T46: the native solvers share the JWL material table,
            # so the row shows in both solver modes
            r = _row(chg, r, 'Material', self._mat_combo)
        else:
            modes = (['charge', 'profile1d'] if self.dim == 2
                     else ['charge', 'profile1d', 'profile2d'])
            r = _row(chg, r, 'Initialize from',
                     _combo(chg, self._var('init_mode', 'charge'), modes))
            # UX-02: the unit follows the geometry - kg for axisym/3D,
            # kg per metre of depth for planar - via _sync_geometry,
            # instead of one label that squeezes both units in
            r, chg_lbl = _row_lbl(chg, r, 'Charge [kg TNT]',
                                  _entry(chg, self._var(
                                      'charge',
                                      1.0 if self.dim == 2 else 25.0)))
            if self.dim == 2:
                self._dyn_labels['charge'] = chg_lbl
            self._mat_combo = _combo(chg, self._var('material', 'TNT'),
                                     MATERIAL_NAMES)
            # N11/T46: the native solvers share the JWL material table,
            # so the row shows in both solver modes
            r = _row(chg, r, 'Material', self._mat_combo)
            if self.dim == 3:
                # blastFoam always resolves the charge (smear is ignored
                # with a note), so the choice is a native row
                self._cres_combo = _combo(
                    chg, self._var('charge_res', 'resolve'),
                    ['resolve', 'smear'])
                r = self._srow(chg, r, 'Charge resolution',
                               self._cres_combo, scope='native')[0]
            r = _row(chg, r, 'Profile file',
                     _FilePicker(chg, self._var('profile_in', ''),
                                 title='Open profile file',
                                 filetypes=[('Profiles', '*.txt *.npz'),
                                            ('All files', '*.*')]))
            c0 = 2.0 if self.dim == 2 else 0.75     # centre of L0
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
        # the solver itself is the app-level mode (sidebar, T34): there
        # is no Solver row any more
        num = self._card(0, 'Numerics')
        r = 0
        # blastFoam fixes the EOS (JWL products + ideal-gas air)
        self._eos_combo = _combo(num, self._var('eos', 'idealGas'),
                                 ['idealGas', 'JWL'])
        r = self._srow(num, r, 'EOS', self._eos_combo, scope='native')[0]
        # T47/N10: opt-in MUSCL reconstruction, native solvers only
        self._order_combo = _combo(num, self._var('order', '1 (Godunov)'),
                                   ['1 (Godunov)', '2 (MUSCL)'])
        r = self._srow(num, r, 'Order', self._order_combo,
                       scope='native')[0]
        self._act_combo = _combo(num, self._var('activation', 'linear'),
                                 ['linear', 'programmedIgnition', 'none'])
        r = self._srow(num, r, 'Detonation', self._act_combo,
                       scope='blastfoam')[0]
        self._ab_combo = _combo(num, self._var('afterburn', 'none'),
                                ['none', 'miller'])
        r = self._srow(num, r, 'Afterburn', self._ab_combo,
                       scope='blastfoam')[0]
        if self.dim > 1:
            # 'global' = today's rule (the whole grid is refined to resolve
            # the charge); 'zone' keeps the base cell and adds automatic
            # nested refinement zones around the charge (blastFoam only;
            # the row also goes away while dynamic AMR is on)
            self._cref_combo = _combo(num, self._var('charge_refine',
                                                     'global'),
                                      ['global', 'zone'])
            r, lbl, w = self._srow(num, r, 'Charge refinement',
                                   self._cref_combo, scope='blastfoam')
            self._cref_row = (lbl, w)
        r = _row(num, r, 'Snapshots',
                 _entry(num, self._var('n_snapshots',
                                       5 if self.dim == 1 else 6)))
        r = _row(num, r, 'CFL',
                 _entry(num, self._var('cfl', {1: 0.5, 2: 0.4,
                                               3: 0.30}[self.dim])))
        if self.dim > 1:
            # blastFoam MPI ranks; 1D always runs serial so no field
            self._nproc_entry = _entry(num, self._var('n_procs', 0))
            r = self._srow(num, r, 'MPI ranks (0 = auto)',
                           self._nproc_entry, scope='blastfoam')[0]
        # T52: every dimension can set an end time; whichever comes
        # first wins - a terminate boundary, the trigger gauge, or this
        r = _row(num, r, 'End time [s] (0 = auto)',
                 _entry(num, self._var('t_end', 0.0)))
        if self.dim == 3:
            r = _row(num, r, 'Live slice normal',
                     _combo(num, self._var('slice_axis', 'y'),
                            ['x', 'y', 'z']))
            r = _row(num, r, 'Slice position [m]\n(blank = burst)',
                     _entry(num, self._var('slice_pos', '')))

        # ── Dynamic refinement (blastFoam adaptiveFvMesh, N16) ─────────
        if self.dim > 1:
            from ..core.refine import AMR_ESTIMATORS, MAX_AMR_LEVEL
            amr = self._card(0, 'Dynamic refinement (AMR)',
                             scope='blastfoam')
            self._amr_card = amr.master
            r = 0
            self._amr_levels_combo = _combo(
                amr, self._var('amr_levels', '0'),
                [str(i) for i in range(MAX_AMR_LEVEL + 1)])
            r = _row(amr, r, 'AMR levels (0 = off)', self._amr_levels_combo)
            # the coefficient rows only exist while AMR is on
            self.v['amr_levels'].trace_add(
                'write', lambda *a: self._apply_mode())
            self._amr_est_combo = _combo(
                amr, self._var('amr_estimator', 'Lohner'),
                list(AMR_ESTIMATORS))
            r, lbl, w = self._srow(amr, r, 'Error estimator',
                                   self._amr_est_combo)
            self._amr_rows.append((lbl, w))
            self._amr_entries = []
            for key, label, default in (
                    ('amr_refine', 'Refine above', 0.4),
                    ('amr_unrefine', 'Unrefine below', 0.2),
                    ('amr_interval', 'Refine every [steps]', 2),
                    ('amr_buffer', 'Buffer layers', 2),
                    ('amr_max_cells', 'Max cells (0 = default)', 0)):
                w = _entry(amr, self._var(key, default))
                r, lbl, w = self._srow(amr, r, label, w)
                self._amr_rows.append((lbl, w))
                self._amr_entries.append(w)
            self._amr_disp_combo = _combo(
                amr, self._var('amr_display_level', 'auto'),
                ['auto'] + [str(i) for i in range(MAX_AMR_LEVEL + 1)])
            r, lbl, w = self._srow(amr, r, 'Display level',
                                   self._amr_disp_combo)
            self._amr_rows.append((lbl, w))

        # ── Boundaries ─────────────────────────────────────────────────
        if self.dim == 1:
            # T60: the far end of the sector - the apex is the symmetry
            # centre, so there is only the one boundary to choose
            bcf = self._card(0, 'Boundaries')
            _row(bcf, 0, 'Outer boundary (r = R)',
                 _combo(bcf, self._var('bc_outer', 'terminate'),
                        list(BC_KINDS)))
        if self.dim > 1:
            bcf = self._card(0, 'Boundaries')
            for col in (1, 3):
                bcf.columnconfigure(col, weight=1)
            bcf.columnconfigure(2, minsize=GAP * 2)
            sides = (['x_lo', 'x_hi', 'y_lo', 'y_hi'] if self.dim == 2 else
                     ['x_lo', 'x_hi', 'y_lo', 'y_hi', 'z_lo', 'z_hi'])
            # UX-01: the FORM defaults give the new user one terminate
            # side (x_hi - the radial outer boundary in axisym, matching
            # the 1D default), so the very first screen validates clean
            # instead of greeting them with the red "No terminate
            # boundary..." warning about its own defaults. The Case2D/3D
            # dataclass defaults stay all-transmit: dozens of tests and
            # programmatic cases rely on them, and a case built in code
            # earns the warning honestly.
            defaults = (dict(x_lo='reflect', x_hi='terminate',
                             y_lo='reflect', y_hi='transmit')
                        if self.dim == 2 else
                        dict(x_lo='transmit', x_hi='terminate',
                             y_lo='transmit', y_hi='transmit',
                             z_lo='reflect', z_hi='transmit'))
            self._bc_combos = {}
            for i, side in enumerate(sides):
                ctk.CTkLabel(bcf, text=side, font=theme.F_BODY,
                             text_color=c('muted'), anchor='w').grid(
                    row=i // 2, column=(i % 2) * 2, sticky='w',
                    padx=(0, GAP), pady=4)
                cb = _combo(bcf, self._var(f'bc_{side}', defaults[side]),
                            list(BC_KINDS), width=112)
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
            # cell / 2, 2 = / 4, ...); the card is hidden on native
            zf = self._card(1, 'Refinement zones [m, level]',
                            scope='blastfoam')
            self._zones_card = zf.master
            self.zones = _PointList(zf, ocols + ['level'], self._on_change,
                                    height=3)
            self.zones.grid(row=0, column=0, columnspan=2, sticky='nsew')

            # blastFoam-only extras (hidden on native)
            if self.dim == 3:
                xc = self._card(1, 'Extra charges [m, kg]',
                                scope='blastfoam')
                self._xc_card = xc.master
                self.extra_charges = _PointList(
                    xc, ['x', 'y', 'z', 'kg'], self._on_change, height=3)
                self.extra_charges.grid(row=0, column=0, columnspan=2,
                                        sticky='nsew')
            dcols = ['x', 'y'] if self.dim == 2 else ['x', 'y', 'z']
            dc = self._card(1, 'Detonation points [m]', scope='blastfoam')
            self._det_card = dc.master
            self.det_pts = _PointList(dc, dcols, self._on_change,
                                      height=3)
            self.det_pts.grid(row=0, column=0, columnspan=2,
                              sticky='nsew')

        # 1D has no visible output row left (OUT-1), so no Outputs card
        out = self._card(1, 'Outputs') if self.dim > 1 else None
        orow = 0
        # OUT-1 (owner Q1), as the Qt form's HIDDEN_ROWS: the output file
        # NAME rows (gauge TSV, animation, profile out, remap file) are
        # variables without a row - a run writes the model folder's own
        # names - and their values still pass through load -> save
        self._var('gauge_file',
                  f'gauges_{self.dim}d.txt' if self.dim > 1 else 'gauges.txt')
        if self.dim > 1:
            # write_animation picks the writer from the extension:
            # .mp4 when ffmpeg is on PATH, .gif otherwise (and it says
            # so in the log when it has to fall back). Default to the one
            # this machine can actually write, as cli.py already does -
            # mp4 is both smaller and free of the gif 256-colour banding.
            from matplotlib import animation as _mplanim
            _ext = '.mp4' if _mplanim.FFMpegWriter.isAvailable() else '.gif'
            self._var('anim_file', f'blast_{self.dim}d_animation{_ext}')
            # OUT-1 (owner Q1): the .gif / .mp4 choice, as in the Qt form
            orow = _row(out, orow, 'Animation format',
                        _combo(out, self._var('anim_format', _ext),
                               ['.mp4', '.gif']))
            # the video's colour range. One range for the whole video by
            # default: the exporter used to rescale every frame, so the
            # colour bar meant something different in each one and the
            # shock never appeared to decay.
            self._ascale_combo = _combo(
                out, self._var('anim_scale', ANIM_SCALE_LABELS['run']),
                list(ANIM_SCALE_LABELS.values()))
            self.v['anim_scale'].trace_add(
                'write', lambda *a: self._apply_mode())
            orow = _row(out, orow, 'Video colours', self._ascale_combo)
            self._aclim_rows = []
            for key, label, default in (('anim_clim_min',
                                         'Video min [kPa]', 0.0),
                                        ('anim_clim_max',
                                         'Video max [kPa]', 500.0)):
                w = _entry(out, self._var(key, default))
                orow, lbl, w = self._srow(out, orow, label, w)
                self._aclim_rows.append((lbl, w))
            ctk.CTkCheckBox(out, text='Record replay frames',
                            variable=self._bool('record', True),
                            font=theme.F_BODY, corner_radius=6,
                            border_color=c('border'),
                            fg_color=c('accent'),
                            hover_color=c('accent_hover')).grid(
                row=orow, column=0, columnspan=2, sticky='w', pady=(GAP, 4))
            orow += 1
            ctk.CTkCheckBox(out, text='Mesh overlay in the animation',
                            variable=self._bool('anim_mesh', False),
                            font=theme.F_BODY, corner_radius=6,
                            border_color=c('border'),
                            fg_color=c('accent'),
                            hover_color=c('accent_hover')).grid(
                row=orow, column=0, columnspan=2, sticky='w', pady=(0, 4))
            orow += 1
        if self.dim == 1:
            self._var('profile_out', 'blast_profile.txt')      # hidden
        elif self.dim == 2:
            self._var('profile_out', '')                        # hidden

        # ── Trigger gauge (T51) ───────────────────────────────────────
        # one gauge that ends the run and/or writes the remap file the
        # moment the wave reaches it. 3D has no remap format, so only
        # the terminate action is offered there. 1D has no trigger at
        # all (T63): its outer boundary already ends the run and the
        # profile it writes at the end IS the hand-off.
        if self.dim > 1:
            trig = self._card(1, 'Trigger gauge')
            trow = _row(trig, 0, 'Gauge number\n(blank = off)',
                        _entry(trig, self._var('trigger_gauge', '')))
            acts = ([a for a in TRIGGER_ACTIONS if 'remap' not in a]
                    if self.dim == 3 else list(TRIGGER_ACTIONS))
            trow = _row(trig, trow, 'On arrival',
                        _combo(trig, self._var('trigger_action',
                                               'terminate'), acts))
            if self.dim < 3:
                # hidden, and non-blank, as in the Qt form (OUT-1): a
                # 'remap' action validates, and the run writes
                # <MODEL>\trigger_remap.npz
                self._var('trigger_file', 'trigger_remap.npz')

        # below both columns, across them (owner decision P13)
        self._build_vtk_card()

        self._sync_geometry()
        self._apply_mode()

    def _build_vtk_card(self):
        """OUT-2: the "VTK output (ParaView)" card, the twin of the Qt one
        (ui/setup_spec._vtk_card; docs/model-folder-and-vtk-plan.md sec.
        3.1-3.2, owner Q2). blastFoam only: the whole card is hidden, never
        greyed, in native mode. It spans both columns, below them (owner
        decision P13): the families and planes on the left, the matrix
        with its full-word headers on the right."""
        card = Card(self, title='VTK output (ParaView)', pad=PAD)
        card.grid(row=max(self._next_row.values()), column=0, columnspan=2,
                  sticky='nwe', pady=(0, PAD - 4))
        self._next_row = {k: max(self._next_row.values()) + 1
                          for k in self._next_row}
        self._scoped['blastfoam'].append(card)
        self._vtk_card = card
        outer = card.body
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        body = ctk.CTkFrame(outer, fg_color='transparent')
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1, minsize=INPUT_MIN)
        right = ctk.CTkFrame(outer, fg_color='transparent')
        right.columnconfigure(0, weight=1)
        self._vtk_panes = (outer, body, right)
        self._vtk_side = None
        self._vtk_place(True)
        outer.bind('<Configure>', lambda e: self._vtk_fit(e.width), add='+')
        self._vtk_entries = {}                    # name -> CTkEntry
        self._vtk_radios = {}                     # family -> radio buttons
        r = 0
        for fam, caption in fields.VTK_FAMILIES[self.dim]:
            box = ctk.CTkCheckBox(body, text=caption,
                                  variable=self._bool(f'vtk_{fam}_on', False),
                                  font=theme.F_BODY, corner_radius=6,
                                  border_color=c('border'),
                                  fg_color=c('accent'),
                                  hover_color=c('accent_hover'))
            box.grid(row=r, column=0, columnspan=2, sticky='w',
                     pady=(GAP if r else 0, 4))
            r += 1
            mode = self._var(f'vtk_{fam}_mode', 'time')
            pair = ctk.CTkFrame(body, fg_color='transparent')
            self._vtk_radios[fam] = []
            for val in ('time', 'step'):
                rb = ctk.CTkRadioButton(pair, text=val.capitalize(),
                                        variable=mode, value=val, width=64,
                                        font=theme.F_BODY,
                                        border_color=c('border'),
                                        fg_color=c('accent'),
                                        hover_color=c('accent_hover'))
                rb.pack(side='left', padx=(0, GAP * 2))
                self._vtk_radios[fam].append(rb)
            r = _row(body, r, 'Cadence', pair)
            # P22 (owner, 2026-09-27): simulated SECONDS, like the rest
            # of the form, the case file and the files ParaView reads
            for key, label, default in (
                    ('time', 'Every [s]\n(simulated time)',
                     fields.VTK_TIME_DEFAULT),
                    ('steps', 'Every [steps]\n(solver steps)',
                     fields.VTK_STEPS_DEFAULT)):
                name = f'vtk_{fam}_{key}'
                ent = _entry(body, self._var(name, f'{default:g}'))
                self._vtk_entries[name] = ent
                r = _row(body, r, label, ent)
            self.v[f'vtk_{fam}_on'].trace_add(
                'write', lambda *a, fam=fam: self._vtk_ticked(fam))
            mode.trace_add('write', lambda *a: self._sync_vtk())
        # P22: the files and ParaView use seconds, as the Time box does
        self._vtk_note = ctk.CTkLabel(
            body, text=fields.VTK_SECONDS_NOTE, font=theme.F_SMALL,
            text_color=c('muted'), anchor='w', justify='left',
            wraplength=LABEL_WRAP + INPUT_MIN)
        self._vtk_note.grid(row=r, column=0, columnspan=2, sticky='w',
                            pady=(GAP, 0))
        r += 1
        if self.dim == 3:
            # decision 7: the live-slice plane is always a section, when
            # the surfaces family is on
            ctk.CTkLabel(body, text=fields.VTK_PLANES_CAPTION,
                         font=theme.F_BODY,
                         text_color=c('muted'), anchor='w', justify='left',
                         wraplength=LABEL_WRAP + INPUT_MIN).grid(
                row=r, column=0, columnspan=2, sticky='w', pady=(GAP, 2))
            self.vtk_planes = _PointList(body, ['axis', 'position [m]'],
                                         self._on_change, height=3,
                                         kinds=('axis', 'float'))
            self.vtk_planes.grid(row=r + 1, column=0, columnspan=2,
                                 sticky='nsew')
            r += 2
        ctk.CTkLabel(right, text=fields.VTK_MATRIX_CAPTION,
                     font=theme.F_BODY, text_color=c('muted'),
                     anchor='w', justify='left',
                     wraplength=LABEL_WRAP + INPUT_MIN).grid(
            row=0, column=0, sticky='w', pady=(0, 2))
        matrix = _MatrixVar(self.dim)
        matrix.trace_add('write', lambda *a: self._on_change())
        self.v['vtk_fields'] = matrix
        self._vtk_grid = _MatrixGrid(right, matrix, self.dim)
        self._vtk_grid.grid(row=1, column=0, sticky='we')
        self._sync_vtk()

    def _vtk_place(self, side):
        """The VTK card's two panes side by side (`side`), or the matrix
        under the families when the card is too narrow for both - at the
        1100 px minimum window its row names were cut ('Peak pressure' at
        59 of 82 px, measured)."""
        if side == self._vtk_side:
            return
        self._vtk_side = side
        outer, body, right = self._vtk_panes
        if side:
            outer.columnconfigure(0, weight=1, uniform='vtk')
            outer.columnconfigure(1, weight=1, uniform='vtk')
            body.grid(row=0, column=0, columnspan=1, sticky='nwe',
                      padx=(0, PAD), pady=0)
            right.grid(row=0, column=1, columnspan=1, sticky='nwe', pady=0)
        else:
            outer.columnconfigure(0, weight=1, uniform='')
            outer.columnconfigure(1, weight=0, uniform='')
            body.grid(row=0, column=0, columnspan=2, sticky='nwe', padx=0,
                      pady=0)
            right.grid(row=1, column=0, columnspan=2, sticky='nwe',
                       pady=(GAP, 0))

    def _vtk_fit(self, width):
        """Side by side when the card body holds both panes' natural
        widths, stacked otherwise (the Qt card's _fit_span)."""
        _outer, body, right = self._vtk_panes
        need = body.winfo_reqwidth() + right.winfo_reqwidth() + PAD
        self._vtk_place(int(width) >= need)

    def _sync_vtk(self):
        """Viper's greying: of each family's two interval boxes only the
        one of the chosen mode is live; the other keeps its value."""
        for fam, _caption in fields.VTK_FAMILIES.get(self.dim, ()):
            step = self.v[f'vtk_{fam}_mode'].get() == 'step'
            for key, on in (('time', not step), ('steps', step)):
                self._vtk_entries[f'vtk_{fam}_{key}'].configure(
                    state='normal' if on else 'disabled',
                    text_color=c('text') if on else c('muted'))

    def _vtk_ticked(self, fam):
        """The first tick of a family fills its default quantities (plan
        sec. 3.1) when its columns are empty; unticking keeps them."""
        if not self.v[f'vtk_{fam}_on'].get():
            return
        var = self.v['vtk_fields']
        new = fields.vtk_fill_defaults(var.get(), fam, self.dim)
        if new != var.get():
            var.set(new)

    def _amr_on(self):
        return (self._mode == 'blastfoam' and 'amr_levels' in self.v
                and self.v['amr_levels'].get().strip() not in ('', '0'))

    def _apply_mode(self):
        """Show the rows/cards of the active solver and hide the other
        solver's; within blastFoam, the AMR coefficient rows exist only
        while AMR is on and the charge-refinement row only while it is
        off (the two are mutually exclusive by validation). Nothing is
        disabled and no value is touched."""
        foam = self._mode == 'blastfoam'
        for w in self._scoped['blastfoam']:
            (w.grid if foam else w.grid_remove)()
        for w in self._scoped['native']:
            (w.grid_remove if foam else w.grid)()
        if self._amr_rows:
            amr_on = self._amr_on()
            for lbl, w in self._amr_rows:
                for x in (lbl, w):
                    (x.grid if amr_on else x.grid_remove)()
            if self._cref_row is not None:
                show = foam and not amr_on
                for x in self._cref_row:
                    (x.grid if show else x.grid_remove)()
        # the video's min/max boxes exist only while its scale is manual
        manual = self._anim_manual()
        for lbl, w in self._aclim_rows:
            for x in (lbl, w):
                (x.grid if manual else x.grid_remove)()

    def _anim_manual(self):
        return ('anim_scale' in self.v
                and anim_scale_from_label(self.v['anim_scale'].get())
                == 'manual')

    def _sync_geometry(self):
        """2D axisymmetric relabels r/z and pins the burst to the axis;
        the x_lo boundary is the axis itself (a wall) - this is the one
        place a control stays disabled, because it is geometry, not a
        solver choice."""
        if self.dim == 2 and 'geometry' in self.v:
            axisym = self.v['geometry'].get() == 'axisymmetric'
            if hasattr(self, '_bc_combos'):
                self._bc_combos['x_lo'].configure(
                    state='disabled' if axisym else 'readonly')
                if axisym:
                    self.v['bc_x_lo'].set('reflect')
            # axisym: the domain is the (r, z) half-plane revolved about
            # the axis - relabel, and pin the burst to the axis (r = 0)
            texts = (dict(Lx='Radius R [m]', Ly='Height Z [m]',
                          cx='Burst r [m]', cy='Burst z [m]',
                          charge='Charge [kg TNT]') if axisym
                     else dict(Lx='Lx [m]', Ly='Ly [m]',
                               cx='Burst x [m]', cy='Burst y [m]',
                               charge='Charge [kg TNT/m]'))
            for key, lbl in getattr(self, '_dyn_labels', {}).items():
                lbl.configure(text=texts[key])
            if hasattr(self, '_burst_x_entry'):
                if axisym:
                    self.v['cx'].set('0')
                    self._burst_x_entry.configure(state='disabled')
                else:
                    self._burst_x_entry.configure(state='normal')

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
        user fixed them one reload at a time.

        Fields hidden by the solver mode are STRIPPED, not read: the case
        carries that solver's defaults for them (what you see is what
        runs and saves), and a stale bad value in a hidden box can never
        block a run. The form keeps the values for a later switch back.

        The mapping itself is `models.fields.case_from_fields`, shared
        with the Qt form (docs/ARCHITECTURE_REVIEW.md section 5, Phase
        5b)."""
        case, errs, bad = fields.case_from_fields(
            self.dim, self.field_values(), self._mode)
        self.mark_fields(bad)
        if errs:
            raise ValueError('\n'.join(errs))
        return case

    def _point_lists(self):
        """The form's point lists under their field names."""
        return {name: getattr(self, name)
                for name in ('gauges', 'obstacles', 'zones', 'det_pts',
                             'extra_charges', 'vtk_planes')
                if hasattr(self, name)}

    def field_values(self):
        """Every field's current value, point lists included, as the
        plain dict `models.fields.case_from_fields` reads."""
        values = {k: var.get() for k, var in self.v.items()}
        values.update({k: pl.get() for k, pl in self._point_lists().items()})
        return values

    def set_case(self, case):
        """Load `case` into the widgets, in the order
        `models.fields.fields_from_case` gives - the trace hooks each set
        fires (the axisymmetric pin, the AMR rows, the video range rows)
        depend on it. Point lists do not fire on_change."""
        points = self._point_lists()
        for name, value in fields.fields_from_case(case, self.dim).items():
            if name in points:
                points[name].set(value)
            else:
                self.v[name].set(value)


class SetupPanel(ctk.CTkFrame):
    """Dimension selector + the three CaseForms + validation card,
    with a live model preview on the right (2D matplotlib drawing or
    3D pyvista render)."""

    _PREV_HINT = 'Enter a valid case to preview the model here.'

    def __init__(self, parent, on_change=None, mode=None):
        super().__init__(parent, fg_color='transparent')
        self._on_change = on_change or (lambda: None)
        # the app-level solver mode (T34); a private one when the panel
        # is built standalone (tests)
        self._mode = mode if mode is not None else mode_mod.SolverMode()

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
        self._dim_seg = theme.segmented(
            head, ['1D', '2D', '3D'], command=self._dim_selected, height=34,
            fg_color=c('card'), unselected_hover_color=c('card2'))
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
        from .preview_panel import Preview1DPanel, Preview2DPanel
        self.preview1d = Preview1DPanel(host)
        self.preview2d = Preview2DPanel(host)
        self.preview = None                      # the 3D panel
        from ..viz3d import MISSING_MSG, pyvista_available
        if pyvista_available():
            from .preview_panel import Preview3DPanel
            self.preview = Preview3DPanel(host)
        self._missing3d = MISSING_MSG
        self._prev_current = None
        self._show_preview_widget(self._prev_msg)

        self._forms = {d: CaseForm(self._form_host, d, self._changed,
                                   mode=self._mode.get())
                       for d in (1, 2, 3)}
        self._current = None
        self._swap()
        self._mode.subscribe(self._mode_changed)

    @property
    def solver(self):
        return self._mode.get()

    def _mode_changed(self, m):
        for f in self._forms.values():
            f.set_mode(m)
        # cards vanished: the scroll region shrinks on its own, but a
        # viewport left past the new end would show nothing
        try:
            self.update_idletasks()
            self._form_host._parent_canvas.yview_moveto(0)
        except Exception:
            pass
        self._changed()

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
            # the form does not parse: keep the last good preview rather
            # than blanking the pane on every keystroke
            return
        self._last_case = case
        show_mesh = bool(self.show_mesh_var.get())
        if case.dim == 1:
            # T59: the spherical sector blastFoam actually meshes, with
            # the charge radius inside it
            self.preview1d.show_case(case, show_mesh=show_mesh)
            self._show_preview_widget(self.preview1d)
        elif case.dim == 2:
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
        # the case's solver becomes the app mode (sidebar, Chain presets,
        # Results) BEFORE the form is filled, so the amr_levels trace and
        # the hide/show logic see the right mode
        self._mode.set(getattr(case, 'solver', 'native'))
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
