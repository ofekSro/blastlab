"""Results panel: browse snapshots/gauges of finished runs, replay
recorded animation frames, and export artifacts."""

import os
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import numpy as np
from matplotlib.figure import Figure

from ..core.constants import P_AIR
from ..output import gauge_summary, plots
from ..output.animation import write_animation
from ..output.gauges import save_gauges_1d, save_gauges_2d, save_gauges_3d
from ..core.profiles import save_profile, save_profile_2d
from ..viz3d import MISSING_MSG, pyvista_available
from . import theme
from .mpl import EmbeddedFigure
from .theme import GAP, PAD, Card, c, icon
from .view3d_panel import View3DPanel


def _combo(parent, values=(), width=200, command=None):
    return ctk.CTkComboBox(parent, state='readonly', width=width,
                           height=32, values=list(values),
                           font=theme.F_BODY, corner_radius=8,
                           fg_color=c('entry'), border_color=c('border'),
                           button_color=c('card2'),
                           button_hover_color=c('border'),
                           dropdown_font=theme.F_BODY, command=command)


#: longest label the 250 px picker shows in full; anything longer is
#: ellipsised there and kept whole in the combo's tooltip (QA-24)
PICKER_MAX = 34


class ResultEntry:
    def __init__(self, label, dim, result):
        self.label = label
        self.display = label
        self.dim = dim
        self.result = result


def _set_solver_mode(panel, m):
    """ResultsPanel.set_solver_mode body (kept module-level so the
    class below stays readable): show the blastFoam-only launchers in
    blastFoam mode, hide them in native mode. Per-result gating of the
    VTK button (`_sync_export_buttons`) is unchanged - configuring a
    hidden button is harmless. Post-mortem loads still work in native
    mode; only the launcher button is out of the way."""
    foam = (m == 'blastfoam')
    panel._solver_mode = m
    vtk = panel._export_btns['vtk']
    if foam:
        if panel._foam_runs_btn.winfo_manager() != 'pack':
            panel._foam_runs_btn.pack(side='left')
        if vtk.winfo_manager() != 'pack':
            vtk.pack(side='left', padx=(0, GAP),
                     after=panel._export_btns['gif'])
    else:
        panel._foam_runs_btn.pack_forget()
        vtk.pack_forget()


class ResultsPanel(ctk.CTkFrame):
    def __init__(self, parent, log_fn=print, mode=None, on_resume=None):
        super().__init__(parent, fg_color='transparent')
        self._entries = []
        self._log = log_fn
        self._on_resume = on_resume     # N6/T43: app-level resume runner
        self._anim_job = None
        # T34: blastFoam-only launchers ("Foam runs…", VTK) are hidden in
        # native mode; a standalone panel (tests) shows everything
        self._solver_mode = 'blastfoam'

        head = ctk.CTkFrame(self, fg_color='transparent')
        head.pack(fill='x', pady=(0, PAD - 4))
        ctk.CTkLabel(head, text='Results', font=theme.F_H1,
                     text_color=c('text')).pack(side='left')

        # ── header card: result picker + exports ─────────────────────────
        top = Card(self)
        top.pack(fill='x', pady=(0, PAD - 4))
        bar = ctk.CTkFrame(top.body, fg_color='transparent')
        bar.pack(fill='x')
        ctk.CTkLabel(bar, text='Result', font=theme.F_BODY,
                     text_color=c('muted')).pack(side='left',
                                                 padx=(0, GAP))
        self.sel = _combo(bar, width=250,
                          command=lambda v: self._refresh())
        self.sel.pack(side='left')

        self._remove_btn = ctk.CTkButton(
            bar, text='Remove', image=icon('minus', 14), compound='left',
            width=104, height=32, font=theme.F_BODY,
            corner_radius=theme.RADIUS, fg_color=c('card2'),
            hover_color=c('border'), text_color=c('text'),
            command=self._remove_current)
        self._remove_btn.pack(side='left', padx=(GAP, 0))
        self._view3d_btn = ctk.CTkButton(
            bar, text='3D Viewer', image=icon('cube', 15),
            compound='left', width=120, height=32,
            font=theme.F_BODY, corner_radius=theme.RADIUS,
            fg_color=c('accent'), hover_color=c('accent_hover'),
            text_color='white', command=self._open_3d)
        self._view3d_btn.pack(side='left', padx=PAD)
        self._foam_runs_btn = ctk.CTkButton(
            bar, text='Foam runs…', image=icon('folder', 14),
            compound='left', width=136, height=32,
            font=theme.F_BODY, corner_radius=theme.RADIUS,
            fg_color=c('card2'), hover_color=c('border'),
            text_color=c('text'), command=self._open_run_browser)
        self._foam_runs_btn.pack(side='left')

        # Second row: the six export buttons never fitted beside the picker
        # (at 1280 px "Gauges TSV" and "PNGs" were packed clean off the
        # window and could not be reached at all), so they get their own.
        bar2 = ctk.CTkFrame(top.body, fg_color='transparent')
        bar2.pack(fill='x', pady=(GAP, 0))
        ctk.CTkLabel(bar2, text='Export', font=theme.F_BODY,
                     text_color=c('muted')).pack(side='left', padx=(0, GAP))
        self._export_btns = {}
        for label, name, kind in (('Profile', 'curve', 'profile'),
                                  ('GIF', 'film', 'gif'),
                                  ('VTK', 'cube', 'vtk'),
                                  ('Summary CSV', 'table', 'summary'),
                                  ('Gauges TSV', 'table', 'tsv'),
                                  ('PNGs', 'image', 'pngs')):
            b = ctk.CTkButton(bar2, text=label, image=icon(name, 14),
                              compound='left', width=104, height=32,
                              font=theme.F_BODY, corner_radius=theme.RADIUS,
                              fg_color=c('card2'), hover_color=c('border'),
                              text_color=c('text'),
                              command=lambda k=kind: self._export(k))
            b.pack(side='left', padx=(0, GAP))
            self._export_btns[kind] = b
        self._sync_export_buttons(None)   # nothing selected yet
        if mode is not None:
            mode.subscribe(self.set_solver_mode)
            self.set_solver_mode(mode.get())

        # ── sub-views: Fields / Gauges / Animation / 3D ──────────────────
        views = Card(self, pad=12)
        views.pack(fill='both', expand=True)
        self._view_seg = theme.segmented(
            views.body, ['Fields', 'Gauges', 'Animation', '3D'],
            command=self._view_selected)
        self._view_seg.pack(anchor='w', pady=(0, GAP))

        stack = ctk.CTkFrame(views.body, fg_color='transparent')
        stack.pack(fill='both', expand=True)
        stack.grid_columnconfigure(0, weight=1)
        stack.grid_rowconfigure(0, weight=1)

        # Fields view
        ftab = ctk.CTkFrame(stack, fg_color='transparent')
        fbar = ctk.CTkFrame(ftab, fg_color='transparent')
        fbar.pack(fill='x', pady=(0, GAP))
        ctk.CTkLabel(fbar, text='Snapshot', font=theme.F_BODY,
                     text_color=c('muted')).pack(side='left',
                                                 padx=(0, GAP))
        self.snap_sel = _combo(fbar, width=200,
                               command=lambda v: self._draw_field())
        self.snap_sel.pack(side='left', padx=(0, PAD))
        ctk.CTkLabel(fbar, text='Field', font=theme.F_BODY,
                     text_color=c('muted')).pack(side='left',
                                                 padx=(0, GAP))
        self.field_sel = _combo(fbar, width=180,
                                command=lambda v: self._draw_field())
        self.field_sel.pack(side='left')
        # cell edges over the field / replay plots (true cells of a
        # refined blastFoam run, every face otherwise)
        self.show_mesh_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            fbar, text='Show mesh', variable=self.show_mesh_var,
            command=self._mesh_toggled, font=theme.F_BODY,
            corner_radius=6, checkbox_width=19, checkbox_height=19,
            border_width=2, border_color=c('border'),
            fg_color=c('accent'), hover_color=c('accent_hover')).pack(
            side='left', padx=(PAD, 0))
        self.field_canvas = EmbeddedFigure(ftab, figsize=(6, 5))
        self.field_canvas.pack(fill='both', expand=True)

        # Gauges view: the traces + the per-gauge engineering summary
        # (peak, arrival, positive-phase duration/impulse, net impulse)
        gtab = ctk.CTkFrame(stack, fg_color='transparent')
        self.gauge_canvas = EmbeddedFigure(gtab, figsize=(7, 5))
        self.gauge_canvas.pack(fill='both', expand=True)
        cols = ('gauge', 'peak', 'arrival', 't_peak', 'pos_dur', 'pos_imp',
                'net_imp', 'complete')
        # headers used to be clipped ("Pos. impulse [Pa" ...) and
        # "Complete" never said complete WHAT
        heads = ('Gauge (cell)', 'Peak ovp [kPa]', 'Arrival [ms]',
                 't peak [ms]', 'Pos. phase [ms]', 'Pos. imp [Pa·s]',
                 'Net imp [Pa·s]', 'Phase ended')
        self.summary_table = ttk.Treeview(gtab, columns=cols, show='headings',
                                          height=4)
        # abbreviated headers ("Pos. imp [Pa*s]") say what they mean on
        # hover; ttk headings take no tooltip, so the table carries one
        # tip whose text follows the pointer's column (QA-33)
        self._head_help = {
            'gauge': 'Gauge number, where you asked for it and, when the '
                     'solver had to snap it, the cell centre it reads.',
            'peak': 'Highest overpressure seen at this gauge.',
            'arrival': 'First time the overpressure crossed the arrival '
                       'threshold.',
            't_peak': 'Time of the peak overpressure.',
            'pos_dur': 'Length of the positive phase, from arrival to the '
                       'first return to ambient.',
            'pos_imp': 'Overpressure impulse of the positive phase only.',
            'net_imp': 'Overpressure impulse over the whole record, '
                       'negative phase included.',
            'complete': 'Whether the positive phase ended inside the run '
                        '- "no" means the run stopped first, so the '
                        'impulses are lower bounds.',
        }
        for col, head in zip(cols, heads):
            self.summary_table.heading(col, text=head)
            self.summary_table.column(
                col, width=150 if col == 'gauge' else 104, stretch=True,
                minwidth=90 if col != 'gauge' else 120,
                anchor='e' if col != 'gauge' else 'w')
        self.summary_table.pack(fill='x', pady=(GAP, 0))
        self._head_tip = theme.tooltip(self.summary_table, '')
        self.summary_table.bind('<Motion>', self._table_hover, add='+')

        # Animation view
        atab = ctk.CTkFrame(stack, fg_color='transparent')
        abar = ctk.CTkFrame(atab, fg_color='transparent')
        abar.pack(fill='x', pady=(0, GAP))
        self.play_btn = ctk.CTkButton(
            abar, text='Play', image=icon('play', 13, color='white'),
            compound='left', width=90, height=32, font=theme.F_BODY,
            corner_radius=theme.RADIUS, fg_color=c('accent'),
            hover_color=c('accent_hover'), text_color='white',
            command=self._toggle_play)
        self.play_btn.pack(side='left', padx=(0, GAP))
        self.frame_var = tk.IntVar(value=0)
        self.frame_slider = theme.Slider(
            abar, from_=0, to=1, height=18,
            progress_color=c('accent'), fg_color=c('card2'),
            button_color=c('accent'), button_hover_color=c('accent_hover'),
            command=self._slider_moved)
        self.frame_slider.set(0)
        self.frame_slider.pack(side='left', fill='x', expand=True,
                               padx=GAP)
        self.anim_canvas = EmbeddedFigure(atab, figsize=(6, 5),
                                          toolbar=False)
        self.anim_canvas.pack(fill='both', expand=True)
        self._anim_mesh = None
        self._anim_solid = None
        self._anim_title = None
        self._anim_levels = None    # AMR: per-frame level maps
        self._anim_lines = None     # the per-frame overlay
        self._anim_geom = None
        self._anim_plane = ''
        self._playing = False

        # 3D view (embedded viewer, snapshot playback)
        self.view3d = View3DPanel(stack, log_fn=self._log)

        self._views = {'Fields': ftab, 'Gauges': gtab,
                       'Animation': atab, '3D': self.view3d}
        for w in self._views.values():
            w.grid(row=0, column=0, sticky='nsew')
        self._view_seg.set('Fields')
        ftab.tkraise()

    def _view_selected(self, value):
        self._views[value].tkraise()

    # ── entries ──────────────────────────────────────────────────────────
    def _unique_label(self, label):
        """Number a duplicate label. The picker matches entries by their
        text, so two identical labels made the second one unreachable -
        selecting it always returned the first (loading the same foam run
        twice did exactly that)."""
        taken = {e.label for e in self._entries}
        if label not in taken:
            return label
        n = 2
        while f'{label} #{n}' in taken:
            n += 1
        return f'{label} #{n}'

    def _displays(self):
        """Picker texts: ellipsised labels, still unique."""
        taken, out = set(), []
        for ent in self._entries:
            d = ent.label
            if len(d) > PICKER_MAX:
                # elide the MIDDLE: the tail carries the dimension, the
                # "(stopped)" note and the " #2" de-duplication marker,
                # which a trailing ellipsis would eat
                keep = PICKER_MAX - 1
                head, tail = (keep + 1) // 2, keep // 2
                d = d[:head] + '…' + d[len(d) - tail:]
            base, n = d, 2
            while d in taken:
                d = f'{base} ({n})'
                n += 1
            taken.add(d)
            ent.display = d
            out.append(d)
        return out

    def add_result(self, label, dim, result):
        label = self._unique_label(label)
        self._entries.append(ResultEntry(label, dim, result))
        self.sel.configure(values=self._displays())
        self.sel.set(self._entries[-1].display)
        self._refresh()

    def _remove_current(self):
        """Drop the selected result (results used to accumulate for the
        whole session with no way to free their frames)."""
        ent = self._current()
        if ent is None:
            self._log('Remove: select a result first.')
            return
        self._stop_play()
        self._entries.remove(ent)
        labels = self._displays()
        self.sel.configure(values=labels)
        if labels:
            self.sel.set(labels[-1])
            self._refresh()
        else:
            self.sel.set('')
            self._clear_views()
        self._log(f'Removed result: {ent.label}')

    def _clear_views(self):
        """Blank every sub-view (no results left to show)."""
        for canvas, size in ((self.field_canvas, (6, 5)),
                             (self.gauge_canvas, (7, 5))):
            fig = Figure(figsize=size)
            fig.add_subplot().axis('off')
            canvas.set_figure(fig)
        self._anim_placeholder('')
        for iid in self.summary_table.get_children():
            self.summary_table.delete(iid)
        for combo in (self.snap_sel, self.field_sel):
            combo.configure(values=[])
            combo.set('')
        self._sync_export_buttons(None)

    def _current(self):
        label = self.sel.get()
        for ent in self._entries:
            if label in (ent.label, ent.display):
                return ent
        return None

    # ── views ────────────────────────────────────────────────────────────
    def _refresh(self):
        ent = self._current()
        if ent is None:
            # a picker text that matches nothing (a cleared combo, a
            # label typed by a test) used to leave the export row exactly
            # as the previous result had left it, so every button stayed
            # enabled and did nothing when pressed (QA-16)
            self._sync_export_buttons(None)
            theme.tooltip(self.sel, '')
            return
        # the picker is 250 px: a long name is ellipsised there and whole
        # on hover (QA-24)
        theme.tooltip(self.sel, ent.label if ent.label != ent.display
                      else '')
        self._stop_play()
        self._sync_export_buttons(ent)
        snaps = list(ent.result.snapshots.keys())
        self.snap_sel.configure(values=snaps)
        if snaps:
            self.snap_sel.set(snaps[-1])
        # whole-run peak overpressure / net impulse maps: native 2D/3D
        # and foam 2D/3D carry them; runs loaded from older results may
        # not, so the entries appear only when the maps exist
        peak = plots.has_peak_maps(ent.result.meta)
        if ent.dim == 1:
            fields = ['profiles']
        elif ent.dim == 2:
            fields = ['overpressure', 'density', 'speed']
            if peak:
                fields += ['peak overpressure', 'net ovp impulse']
        else:
            fields = ['overpressure (x-z)', 'overpressure (x-y)',
                      'density (x-z)', 'density (x-y)']
            if peak:
                fields += ['peak overpressure (x-z)',
                           'peak overpressure (x-y)',
                           'net ovp impulse (x-z)', 'net ovp impulse (x-y)']
            fields.append('isosurface')
        self.field_sel.configure(values=fields)
        self.field_sel.set(fields[0])
        self._draw_field()
        self._draw_gauges()
        self._setup_anim()

    def set_solver_mode(self, m):
        """T34: hide the blastFoam-only launchers in native mode."""
        _set_solver_mode(self, m)

    def _sync_export_buttons(self, ent):
        """Only offer an export that can actually run for this result.
        Every button used to stay enabled: with nothing selected they were
        silent no-ops, and Profile on a planar 2D result opened a file
        dialog and then failed in the log."""
        if ent is None:
            for kind, b in self._export_btns.items():
                b.configure(state='disabled')
                theme.tooltip(b, 'Select a result first.')
            return
        res, dim = ent.result, ent.dim
        meta = res.meta
        from ..solvers.foam.export_vtk import can_export
        has_gauges = bool(res.gauges.get('pressures'))
        ok = dict(
            vtk=can_export(meta),
            gif=bool(meta.get('frames')),
            summary=has_gauges,
            tsv=has_gauges,
            pngs=bool(res.snapshots),
            profile=(dim == 1 or (dim == 2 and meta.get('geometry')
                                  == 'axisymmetric')),
        )
        # a greyed button has to say why it is greyed - "Profile" in
        # particular is off for every 3D and planar-2D result (QA-16)
        why = dict(
            vtk='Only a blastFoam run whose case directory still exists '
                'can be written as VTK.',
            gif='This result has no recorded frames - tick "Record replay '
                'frames" before the run.',
            summary='This result has no gauges.',
            tsv='This result has no gauges.',
            pngs='This result has no field snapshots.',
            profile=('3D results have no profile export.' if dim == 3 else
                     'Only axisymmetric 2D fields can be remapped into 3D.'),
        )
        for kind, b in self._export_btns.items():
            good = ok.get(kind, True)
            b.configure(state='normal' if good else 'disabled')
            theme.tooltip(b, '' if good else why.get(kind, ''))

    def _mesh_toggled(self):
        self._draw_field()
        self._setup_anim()

    def _draw_field(self):
        ent = self._current()
        if ent is None or not ent.result.snapshots:
            return
        res, dim = ent.result, ent.dim
        label = self.snap_sel.get() or list(res.snapshots)[-1]
        snap = res.snapshots.get(label)
        if snap is None:
            return
        field = self.field_sel.get()

        if dim == 1:
            fig = plots.figure_results_1d(
                res.snapshots, res.meta['eos'], res.meta['charge_kg'],
                res.meta['radius_m'])
            self.field_canvas.set_figure(fig)
            return

        meta = res.meta
        if dim == 3 and field == 'isosurface':
            fig = plots.figure_isosurfaces_3d(res.snapshots, meta)
            self.field_canvas.set_figure(fig)
            return

        # whole-run maps are not per snapshot: one panel labelled so
        is_peak = field.startswith('peak overpressure')
        is_imp = field.startswith('net ovp impulse')
        if is_peak or is_imp:
            label = 'whole run'

        if dim == 2:
            if is_peak or is_imp:
                (pk_lbl, pk), (im_lbl, im) = plots.peak_items(meta)
                data = pk if is_peak else im
                unit = plots.PEAK_LABEL if is_peak else plots.IMPULSE_LABEL
            else:
                data = {'overpressure': (snap['p'] - P_AIR) / 1e3,
                        'density': snap['rho'],
                        'speed': snap['speed']}[field]
                unit = {'overpressure': 'Overpressure [kPa]',
                        'density': 'Density [kg/m³]',
                        'speed': 'Speed [m/s]'}[field]
            solid_sl, xf, yf = meta['solid'], meta['x_face'], meta['y_face']
            xl = 'r [m]' if meta['geometry'] == 'axisymmetric' else 'x [m]'
            yl = 'z [m]' if meta['geometry'] == 'axisymmetric' else 'y [m]'
            aspect = meta['Lx'] / meta['Ly']
        else:
            j0, k0 = meta['j0'], meta['k0']
            is_ovp = field.startswith('overpressure')
            if '(x-z)' in field:
                sl = np.s_[:, j0, :]
                solid_sl = meta['solid'][sl]
                xf, yf = meta['x_face'], meta['z_face']
                xl, yl = 'x [m]', 'z [m]'
                aspect = meta['Lx'] / meta['Lz']
                plane, pos = 'x-z', f"y = {meta['y_c'][j0]:.2f} m"
                raw = (snap['p'][sl] - np.float32(P_AIR)
                      if is_ovp else snap['rho_xz'])
            else:
                sl = np.s_[:, :, k0]
                solid_sl = meta['solid'][sl]
                xf, yf = meta['x_face'], meta['y_face']
                xl, yl = 'x [m]', 'y [m]'
                aspect = meta['Lx'] / meta['Ly']
                plane, pos = 'x-y', f"z = {meta['z_c'][k0]:.2f} m"
                raw = (snap['p'][sl] - np.float32(P_AIR)
                      if is_ovp else snap['rho_xy'])
            if is_peak or is_imp:
                (pk_lbl, pk), (im_lbl, im) = plots.peak_items(meta, sl)
                data = pk if is_peak else im
                unit = (f"{plots.PEAK_LABEL if is_peak else plots.IMPULSE_LABEL}"
                        f" — {plane} slice at {pos}")
            elif is_ovp:
                data = raw / np.float32(1e3)
                unit = f"Overpressure [kPa] — {plane} slice at {pos}"
            else:
                data = raw
                unit = f"Density [kg/m³] — {plane} slice at {pos}"

        mesh = None
        if self.show_mesh_var.get():
            mesh = plots.mesh_for(meta, xf, yf, sl if dim == 3 else None)
        fig = plots._panel_grid_figure(
            [(label, data)], solid_sl, xf, yf, xl, yl,
            f"{field} - {plots.charge_label(meta)}", unit, aspect,
            mesh=mesh, robust=(is_peak or is_imp))
        self.field_canvas.set_figure(fig)

    def _draw_gauges(self):
        ent = self._current()
        if ent is None:
            return
        res = ent.result
        if ent.dim == 1:
            fig = plots.figure_gauges_1d(res.gauges, res.meta['charge_kg'],
                                         res.meta['eos'])
        else:
            fig = plots.figure_gauges_nd(res.gauges, res.meta)
        if fig is not None:
            self.gauge_canvas.set_figure(fig)
        self._fill_summary(res)

    def _table_hover(self, event):
        """Point the shared tooltip at the column under the pointer."""
        tbl = self.summary_table
        try:
            if tbl.identify_region(event.x, event.y) != 'heading':
                self._head_tip.set_text('')
                return
            col = tbl.identify_column(event.x)
            name = tbl['columns'][int(col[1:]) - 1]
        except (ValueError, IndexError, tk.TclError):
            return
        self._head_tip.set_text(self._head_help.get(name, ''))

    def summary_rows(self, res):
        """Per-gauge engineering rows for a Result (output.gauge_summary)."""
        # meta['gauges'] is what the USER asked for; gauges['points']
        # is where the solver put them (QA-33)
        return gauge_summary.summarize_gauges(
            res.gauges, requested=res.meta.get('gauges'))

    def _fill_summary(self, res):
        tbl = self.summary_table
        for iid in tbl.get_children():
            tbl.delete(iid)
        for row in gauge_summary.table_rows(self.summary_rows(res)):
            tbl.insert('', 'end', values=row)

    # ── animation replay ─────────────────────────────────────────────────
    def _anim_placeholder(self, text):
        """Blank the replay canvas. Without this the previously selected
        result's frame stayed on screen under a result that has no
        animation at all (a 1D run, or a post-mortem loaded run), which
        reads as this result's data."""
        fig = Figure(figsize=(6, 5))
        ax = fig.add_subplot()
        ax.axis('off')
        if text:
            ax.text(0.5, 0.5, text, transform=ax.transAxes, ha='center',
                    va='center', fontsize=10, color=theme.cur('muted'))
        self._anim_mesh = None
        self._anim_title = None
        self._anim_lines = None
        self._anim_levels = None
        self._anim_geom = None
        self.anim_canvas.set_figure(fig)
        self.play_btn.configure(state='disabled')
        self.frame_slider.configure(to=1, number_of_steps=1)
        self.frame_slider.set(0)

    def _setup_anim(self):
        ent = self._current()
        self._stop_play()
        self._anim_mesh = None
        if ent is None or ent.dim == 1:
            self._anim_placeholder(
                '1D results have no animation frames.' if ent is not None
                else '')
            return
        frames = ent.result.meta.get('frames')
        if not frames or not len(frames['pressures']):
            self._anim_placeholder(
                'No recorded frames for this result.\n'
                'Tick "Record frames" before the run; runs loaded from the\n'
                'foam run browser carry snapshots but no replay frames.')
            return
        meta = ent.result.meta
        n = len(frames['pressures'])
        self.play_btn.configure(state='normal')
        self.frame_slider.configure(to=max(1, n - 1),
                                    number_of_steps=max(1, n - 1))

        fig = Figure(figsize=(6, 5))
        ax = fig.add_subplot()
        if 'z_face' in meta:      # 3D slice: mirror output/animation.py
            s_ax = meta.get('slice_axis', 'y')
            s0 = meta.get('s0', meta['j0'])
            faces = {'x': (meta['y_face'], meta['z_face']),
                     'y': (meta['x_face'], meta['z_face']),
                     'z': (meta['x_face'], meta['y_face'])}[s_ax]
            labels = {'x': ('y [m]', 'z [m]'), 'y': ('x [m]', 'z [m]'),
                      'z': ('x [m]', 'y [m]')}[s_ax]
            sl = tuple(s0 if a == 'xyz'.index(s_ax) else slice(None)
                      for a in range(3))
            xf, yf = faces
            xlabel, ylabel = labels
            self._anim_solid = meta['solid'][sl]
            self._anim_plane = f"{s_ax} = {meta[f'{s_ax}_c'][s0]:.2f} m  "
        else:
            xf, yf = meta['x_face'], meta['y_face']
            self._anim_solid = meta['solid']
            sl = None
            xlabel = 'x [m]'
            ylabel = ('z [m]' if meta.get('geometry') == 'axisymmetric'
                     else 'y [m]')
            self._anim_plane = ''
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        # dynamic AMR: the recorded per-frame level maps drive a
        # per-frame overlay (see _show_frame); static runs keep the one
        # predicted-mesh overlay
        self._anim_levels = frames.get('levels')
        self._anim_geom = (meta, xf, yf, sl)
        self._anim_lines = None
        self._anim_mesh = plots.overpressure_panel(
            ax, xf, yf, self._anim_solid.shape,
            mesh=(plots.mesh_for(meta, xf, yf, sl)
                  if self.show_mesh_var.get() and self._anim_levels is None
                  else None))
        self._anim_title = ax.set_title('')
        fig.colorbar(self._anim_mesh, ax=ax, label='Overpressure [kPa]',
                     shrink=0.85)
        fig.tight_layout()
        self.anim_canvas.set_figure(fig)
        self._show_frame(0)

    def _show_frame(self, k):
        ent = self._current()
        if ent is None or self._anim_mesh is None:
            return
        frames = ent.result.meta['frames']
        k = max(0, min(int(k), len(frames['pressures']) - 1))
        plots.set_frame(self._anim_mesh, frames['pressures'][k],
                        self._anim_solid)
        if self._anim_levels is not None and self.show_mesh_var.get():
            meta, xf, yf, sl = self._anim_geom
            if self._anim_lines is not None:
                self._anim_lines.remove()
            lv = self._anim_levels[min(k, len(self._anim_levels) - 1)]
            self._anim_lines = plots.add_mesh_lines(
                self._anim_mesh.axes,
                plots.mesh_for(meta, xf, yf, sl, levels=lv))
        self._anim_title.set_text(
            f"{self._anim_plane}t = {frames['times'][k]*1e3:.3f} ms")
        self.anim_canvas.draw()

    def _slider_moved(self, value):
        if not self._playing:
            self._show_frame(float(value))

    def _toggle_play(self):
        if self._playing:
            self._stop_play()
        else:
            self._playing = True
            self.play_btn.configure(text='Pause',
                                    image=icon('pause', 13, color='white'))
            self._tick(int(float(self.frame_slider.get())))

    def _tick(self, k):
        if not self._playing:
            return
        ent = self._current()
        if ent is None or self._anim_mesh is None:
            self._stop_play()
            return
        n = len(ent.result.meta['frames']['pressures'])
        self.frame_slider.set(k)
        self._show_frame(k)
        self._anim_job = self.after(66, self._tick, (k + 1) % n)

    def _stop_play(self):
        self._playing = False
        self.play_btn.configure(text='Play',
                                image=icon('play', 13, color='white'))
        if self._anim_job is not None:
            self.after_cancel(self._anim_job)
            self._anim_job = None

    # ── embedded 3D viewer (playback of snapshots) ───────────────────────
    def _open_3d(self):
        ent = self._current()
        if ent is None:
            return
        if ent.dim != 3:
            self._log('3D Viewer: select a 3D result.')
            return
        if not pyvista_available():
            self._log(MISSING_MSG)
            return
        if not ent.result.snapshots:
            self._log('3D Viewer: this result has no snapshots.')
            return
        try:
            if self.view3d.feed_result(ent.result):
                self._view_seg.set('3D')
                self.view3d.tkraise()
                self._log(f'3D view loaded: {ent.label} '
                          f'({len(ent.result.snapshots)} snapshots)')
        except Exception as exc:
            self._log(f'3D view failed: {exc}')

    # ── post-mortem load of a finished blastFoam case dir ────────────────
    def _open_run_browser(self):
        """The WSL run browser (N8): list / load / delete run dirs."""
        from .run_browser import FoamRunBrowser
        win = getattr(self, '_run_browser', None)
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus()
            win.refresh()
            return
        self._run_browser = FoamRunBrowser(
            self, on_load=self.load_foam_run_path, log=self._log,
            on_resume=self._on_resume)

    def load_foam_run_path(self, path):
        """Post-mortem load of one run dir (UNC/posix/name) off-thread,
        then add it to the results list."""
        if not path:
            return
        self._log(f'Loading foam run {path} ...')

        def work():
            try:
                from ..solvers.foam.postmortem import load_run
                res = load_run(path)
            except Exception as exc:
                self._log(f'Load failed: {exc}')
                return
            dim = 1 if 'radius_m' in res.meta else \
                (3 if 'z_c' in res.meta else 2)
            name = (str(res.meta.get('name') or '').strip()
                    or os.path.basename(str(path).rstrip('/' + os.sep)))
            res.meta.setdefault('name', name)
            label = f'{name} (loaded, {dim}D)'
            # Tk objects must be touched on the main thread
            self.after(0, self.add_result, label, dim, res)
            self._log(f'Loaded: {label} '
                      f'({len(res.snapshots)} snapshots)')

        threading.Thread(target=work, daemon=True).start()

    # ── exports ──────────────────────────────────────────────────────────
    @staticmethod
    def _name_prefix(res):
        """"<run name>_" for the suggested export file names, so three
        runs do not all propose gauges_2d.txt (N9)."""
        name = str(res.meta.get('name') or '').strip()
        slug = re.sub(r'[^0-9A-Za-z._-]+', '_', name).strip('_')
        return f'{slug[:40]}_' if slug else ''

    def _export(self, kind):
        ent = self._current()
        if ent is None:
            self._log('Select a result before exporting.')
            return
        res, dim = ent.result, ent.dim
        pre = self._name_prefix(res)
        show_mesh = bool(self.show_mesh_var.get())

        # File dialogs must run on the Tk main thread; only the heavy
        # figure building / writing goes to the worker thread.
        target = None
        if kind == 'pngs':
            target = filedialog.askdirectory(title='Save PNGs into')
        elif kind == 'tsv':
            target = filedialog.asksaveasfilename(
                title='Save gauges TSV', defaultextension='.txt',
                initialfile=f'{pre}gauges_{dim}d.txt')
        elif kind == 'vtk':
            from ..solvers.foam.export_vtk import can_export
            if not can_export(res.meta):
                self._log('VTK export needs a blastFoam run whose case '
                          'directory still exists.')
                return
            target = res.meta['case_dir']
        elif kind == 'summary':
            if not res.gauges.get('pressures'):
                self._log('No gauges in this result.')
                return
            target = filedialog.asksaveasfilename(
                title='Save gauge summary CSV', defaultextension='.csv',
                initialfile=f'{pre}gauges_{dim}d_summary.csv')
        elif kind == 'gif':
            if not res.meta.get('frames'):
                self._log('No recorded frames in this result.')
                return
            target = filedialog.asksaveasfilename(
                title='Save animation GIF', defaultextension='.gif',
                initialfile=f'{pre}blast_{dim}d_animation.gif')
        elif kind == 'profile':
            if dim == 3:
                self._log('3D results have no profile export.')
                return
            target = filedialog.asksaveasfilename(
                title='Save profile',
                defaultextension='.txt' if dim == 1 else '.npz',
                initialfile=(f'{pre}blast_profile.txt' if dim == 1
                             else f'{pre}blast_profile_2d.npz'))
        if not target:
            return

        def work():
            try:
                if kind == 'pngs':
                    outdir = target
                    figs = []
                    if dim == 1:
                        figs = [('blast_1d_results.png',
                                 plots.figure_results_1d(
                                     res.snapshots, res.meta['eos'],
                                     res.meta['charge_kg'],
                                     res.meta['radius_m'])),
                                ('blast_1d_gauges.png',
                                 plots.figure_gauges_1d(
                                     res.gauges, res.meta['charge_kg'],
                                     res.meta['eos']))]
                    elif dim == 2:
                        figs = plots.figures_fields_2d(res.snapshots, res.meta,
                                                       include_peak=True,
                                                       show_mesh=show_mesh)
                        figs.append(('blast_2d_gauges.png',
                                     plots.figure_gauges_nd(res.gauges,
                                                            res.meta)))
                    else:
                        figs = plots.figures_fields_3d(res.snapshots, res.meta,
                                                       include_peak=True,
                                                       show_mesh=show_mesh)
                        figs.append(('blast_3d_gauges.png',
                                     plots.figure_gauges_nd(res.gauges,
                                                            res.meta)))
                        figs.append(('blast_3d_isosurface.png',
                                     plots.figure_isosurfaces_3d(
                                         res.snapshots, res.meta)))
                    for name, fig in figs:
                        if fig is None:
                            continue
                        name = pre + name       # <run name>_... (N9)
                        fig.savefig(os.path.join(outdir, name), dpi=150,
                                    bbox_inches='tight')
                        self._log(f'Saved {name}')
                elif kind == 'tsv':
                    {1: save_gauges_1d, 2: save_gauges_2d,
                     3: save_gauges_3d}[dim](res.gauges, target)
                    self._log(f'Saved {target}')
                elif kind == 'summary':
                    gauge_summary.save_gauge_summary(
                        self.summary_rows(res), target)
                    self._log(f'Saved {target}')
                elif kind == 'vtk':
                    from ..solvers.foam.export_vtk import export_vtk
                    try:
                        out = export_vtk(target, log=self._log)
                    except RuntimeError as exc:
                        self._log(f'VTK export failed: {exc}')
                        self.after(0, messagebox.showerror, 'VTK export',
                                   str(exc)[:600])
                        return
                    self._log(f'VTK export done: {out}')
                    try:
                        os.startfile(out)
                    except OSError as exc:
                        self._log(f'(could not open the folder: {exc})')
                elif kind == 'gif':
                    write_animation(res.meta, target, show_mesh=show_mesh)
                    self._log(f'Saved {target}')
                elif kind == 'profile':
                    if dim == 1:
                        save_profile(res.meta['final_profile'], target)
                    else:
                        save_profile_2d(res.meta, target)
                    self._log(f'Saved {target}')
            except Exception as exc:               # surfaced to the log
                self._log(f'Export failed: {exc}')

        threading.Thread(target=work, daemon=True).start()
