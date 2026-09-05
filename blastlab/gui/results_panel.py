"""Results panel: browse snapshots/gauges of finished runs, replay
recorded animation frames, and export artifacts."""

import os
import threading
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
import numpy as np
from matplotlib.figure import Figure

from ..core.constants import P_AIR
from ..output import plots
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


class ResultEntry:
    def __init__(self, label, dim, result):
        self.label = label
        self.dim = dim
        self.result = result


class ResultsPanel(ctk.CTkFrame):
    def __init__(self, parent, log_fn=print):
        super().__init__(parent, fg_color='transparent')
        self._entries = []
        self._log = log_fn
        self._anim_job = None

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

        ctk.CTkButton(bar, text='3D Viewer', image=icon('cube', 15),
                      compound='left', width=120, height=32,
                      font=theme.F_BODY, corner_radius=theme.RADIUS,
                      fg_color=c('accent'), hover_color=c('accent_hover'),
                      text_color='white',
                      command=self._open_3d).pack(side='left', padx=PAD)
        ctk.CTkButton(bar, text='Load foam run…', image=icon('folder', 14),
                      compound='left', width=136, height=32,
                      font=theme.F_BODY, corner_radius=theme.RADIUS,
                      fg_color=c('card2'), hover_color=c('border'),
                      text_color=c('text'),
                      command=self._load_foam_run).pack(side='left')

        for label, name, kind in (('Profile', 'curve', 'profile'),
                                  ('GIF', 'film', 'gif'),
                                  ('Gauges TSV', 'table', 'tsv'),
                                  ('PNGs', 'image', 'pngs')):
            ctk.CTkButton(bar, text=label, image=icon(name, 14),
                          compound='left', width=104, height=32,
                          font=theme.F_BODY, corner_radius=theme.RADIUS,
                          fg_color=c('card2'), hover_color=c('border'),
                          text_color=c('text'),
                          command=lambda k=kind: self._export(k)).pack(
                side='right', padx=(GAP, 0))
        ctk.CTkLabel(bar, text='Export', font=theme.F_BODY,
                     text_color=c('muted')).pack(side='right',
                                                 padx=(0, GAP))

        # ── sub-views: Fields / Gauges / Animation / 3D ──────────────────
        views = Card(self, pad=12)
        views.pack(fill='both', expand=True)
        self._view_seg = ctk.CTkSegmentedButton(
            views.body, values=['Fields', 'Gauges', 'Animation', '3D'],
            font=theme.F_BODY, corner_radius=theme.RADIUS, height=32,
            fg_color=c('card2'), unselected_color=c('card2'),
            unselected_hover_color=c('border'),
            selected_color=c('accent'),
            selected_hover_color=c('accent_hover'),
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
        self.field_canvas = EmbeddedFigure(ftab, figsize=(6, 5))
        self.field_canvas.pack(fill='both', expand=True)

        # Gauges view
        gtab = ctk.CTkFrame(stack, fg_color='transparent')
        self.gauge_canvas = EmbeddedFigure(gtab, figsize=(7, 5))
        self.gauge_canvas.pack(fill='both', expand=True)

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
    def add_result(self, label, dim, result):
        self._entries.append(ResultEntry(label, dim, result))
        self.sel.configure(values=[e.label for e in self._entries])
        self.sel.set(label)
        self._refresh()

    def _current(self):
        label = self.sel.get()
        for ent in self._entries:
            if ent.label == label:
                return ent
        return None

    # ── views ────────────────────────────────────────────────────────────
    def _refresh(self):
        ent = self._current()
        if ent is None:
            return
        self._stop_play()
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

        fig = plots._panel_grid_figure(
            [(label, data)], solid_sl, xf, yf, xl, yl,
            f"{field} - {plots.charge_label(meta)}", unit, aspect)
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

    # ── animation replay ─────────────────────────────────────────────────
    def _setup_anim(self):
        ent = self._current()
        self._stop_play()
        self._anim_mesh = None
        if ent is None or ent.dim == 1:
            return
        frames = ent.result.meta.get('frames')
        if not frames or not len(frames['pressures']):
            return
        meta = ent.result.meta
        n = len(frames['pressures'])
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
            xlabel = 'x [m]'
            ylabel = ('z [m]' if meta.get('geometry') == 'axisymmetric'
                     else 'y [m]')
            self._anim_plane = ''
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        self._anim_mesh = plots.overpressure_panel(
            ax, xf, yf, self._anim_solid.shape)
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
    def _load_foam_run(self):
        from ..solvers.foam import env as foam_env
        initial = foam_env.unc(foam_env.RUNS_ROOT)
        path = filedialog.askdirectory(
            title='Load a finished blastFoam run directory',
            initialdir=initial if os.path.isdir(initial) else None)
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
            label = f'Loaded - {os.path.basename(path)} ({dim}D)'
            # Tk objects must be touched on the main thread
            self.after(0, self.add_result, label, dim, res)
            self._log(f'Loaded: {label} '
                      f'({len(res.snapshots)} snapshots)')

        threading.Thread(target=work, daemon=True).start()

    # ── exports ──────────────────────────────────────────────────────────
    def _export(self, kind):
        ent = self._current()
        if ent is None:
            return
        res, dim = ent.result, ent.dim

        # File dialogs must run on the Tk main thread; only the heavy
        # figure building / writing goes to the worker thread.
        target = None
        if kind == 'pngs':
            target = filedialog.askdirectory(title='Save PNGs into')
        elif kind == 'tsv':
            target = filedialog.asksaveasfilename(
                defaultextension='.txt', initialfile=f'gauges_{dim}d.txt')
        elif kind == 'gif':
            if not res.meta.get('frames'):
                self._log('No recorded frames in this result.')
                return
            target = filedialog.asksaveasfilename(
                defaultextension='.gif',
                initialfile=f'blast_{dim}d_animation.gif')
        elif kind == 'profile':
            if dim == 3:
                self._log('3D results have no profile export.')
                return
            target = filedialog.asksaveasfilename(
                defaultextension='.txt' if dim == 1 else '.npz',
                initialfile=('blast_profile.txt' if dim == 1
                             else 'blast_profile_2d.npz'))
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
                                                       include_peak=True)
                        figs.append(('blast_2d_gauges.png',
                                     plots.figure_gauges_nd(res.gauges,
                                                            res.meta)))
                    else:
                        figs = plots.figures_fields_3d(res.snapshots, res.meta,
                                                       include_peak=True)
                        figs.append(('blast_3d_gauges.png',
                                     plots.figure_gauges_nd(res.gauges,
                                                            res.meta)))
                        figs.append(('blast_3d_isosurface.png',
                                     plots.figure_isosurfaces_3d(
                                         res.snapshots, res.meta)))
                    for name, fig in figs:
                        if fig is None:
                            continue
                        fig.savefig(os.path.join(outdir, name), dpi=150,
                                    bbox_inches='tight')
                        self._log(f'Saved {name}')
                elif kind == 'tsv':
                    {1: save_gauges_1d, 2: save_gauges_2d,
                     3: save_gauges_3d}[dim](res.gauges, target)
                    self._log(f'Saved {target}')
                elif kind == 'gif':
                    write_animation(res.meta, target)
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
