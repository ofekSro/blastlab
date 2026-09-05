"""Embedded 3D blast view for the Tkinter GUI (VIPER-style controls).

Hosts a BlastScene on an off-screen pyvista plotter in-process and blits
rendered frames into a Tk label (via VtkTkHost). The control column is
a small segmented stack:

  Display : displayed field (pressure / density / energy / peak
            overpressure / impulse), auto or manual min/max colour
            range, log contours, isosurface / surface loads / volume
            layers
  Planes  : six cross-section planes - enable, axis, position, opacity
  View    : axis-aligned camera presets + parallel projection

Everything runs on the Tk main thread except Feed3D.make_payload, which
the solver worker thread calls to decimate fields before handing them
over (coalesced latest-wins slot in GuiHooks).
"""

import tkinter as tk

import customtkinter as ctk

from ..viz3d import MISSING_MSG, pyvista_available
from ..viz3d.sampling import build_payload, build_scene_init
from . import theme
from .theme import GAP, c
from .vtk_host import VtkTkHost
from ..viz3d.viewer import FIELDS

N_PLANES = 6
#: radio-button fields, straight from the viewer's FIELDS table
FIELD_LABELS = [(key, spec['label']) for key, spec in FIELDS.items()]


class Feed3D:
    """Solver-thread side: turns full-resolution fields into viewer
    payloads. Read-only after construction, so thread-safe."""

    def __init__(self, scene_info):
        self.init, self._stride, self._specs = build_scene_init(scene_info)

    def make_payload(self, fields):
        return build_payload(fields, self._stride, self._specs)


class View3DPanel(VtkTkHost):
    PLACEHOLDER = ('Run a 3D case - the live view attaches\n'
                   'automatically. Finished 3D results replay\n'
                   'here from the Results tab.')

    def __init__(self, parent, log_fn=print):
        self._playing = False
        self._syncing_slider = False
        self._built = False
        super().__init__(parent, log_fn=log_fn)
        self._build_controls()
        self._built = True

    # ── UI construction ──────────────────────────────────────────────────
    def _build_controls(self):
        ctl = ctk.CTkFrame(self, width=248, fg_color='transparent')
        ctl.pack(side='left', fill='y', padx=(0, GAP), pady=0,
                 before=self.view)
        ctl.pack_propagate(False)
        self._vars = {}

        def small_label(parent, text):
            ctk.CTkLabel(parent, text=text, font=(theme.FONT, 11, 'bold'),
                         text_color=c('muted'), height=16,
                         anchor='w').pack(fill='x', pady=(GAP, 2))

        def checkbox(parent, label, key, default, command):
            var = tk.BooleanVar(value=default)
            self._vars[key] = var
            ctk.CTkCheckBox(parent, text=label, variable=var,
                            font=theme.F_BODY, corner_radius=5,
                            checkbox_width=19, checkbox_height=19,
                            border_width=2, border_color=c('border'),
                            fg_color=c('accent'),
                            hover_color=c('accent_hover'),
                            command=command).pack(anchor='w', pady=3)
            return var

        def slider(parent, from_, to, command=None):
            return theme.Slider(
                parent, from_=from_, to=to, height=16,
                progress_color=c('accent'), fg_color=c('card2'),
                button_color=c('accent'),
                button_hover_color=c('accent_hover'), command=command)

        self._tab_seg = ctk.CTkSegmentedButton(
            ctl, values=['Display', 'Planes', 'View'],
            font=theme.F_SMALL, corner_radius=theme.RADIUS, height=28,
            fg_color=c('card2'), unselected_color=c('card2'),
            unselected_hover_color=c('border'),
            selected_color=c('accent'),
            selected_hover_color=c('accent_hover'),
            command=self._tab_selected)
        self._tab_seg.pack(fill='x')
        stack = ctk.CTkFrame(ctl, fg_color='transparent')
        stack.pack(fill='both', expand=True, pady=(GAP, 0))
        stack.grid_columnconfigure(0, weight=1)
        stack.grid_rowconfigure(0, weight=1)
        disp = ctk.CTkFrame(stack, fg_color='transparent')
        planes = ctk.CTkFrame(stack, fg_color='transparent')
        viewtab = ctk.CTkFrame(stack, fg_color='transparent')
        self._tabs = {'Display': disp, 'Planes': planes, 'View': viewtab}
        for w in (viewtab, planes, disp):
            w.grid(row=0, column=0, sticky='nsew')
        self._tab_seg.set('Display')

        # ── Display tab ────────────────────────────────────────────────
        small_label(disp, 'FIELD')
        self._vars['field'] = tk.StringVar(value='p')
        self._field_btns = {}
        for key, label in FIELD_LABELS:
            rb = theme.RadioButton(
                disp, text=label, value=key,
                variable=self._vars['field'], font=theme.F_BODY,
                radiobutton_width=18, radiobutton_height=18,
                border_width_checked=5, border_color=c('border'),
                fg_color=c('accent'), hover_color=c('accent_hover'),
                command=self._field_changed)
            rb.pack(anchor='w', pady=2)
            self._field_btns[key] = rb

        small_label(disp, 'COLOUR SCALE')
        checkbox(disp, 'Auto colour scale', 'auto_scale', True,
                 self._auto_changed)
        row = ctk.CTkFrame(disp, fg_color='transparent')
        row.pack(fill='x', pady=2)
        self._vars['vmin'] = tk.StringVar(value='0')
        self._vars['vmax'] = tk.StringVar(value='500')
        for lbl, key in (('Min', 'vmin'), ('Max', 'vmax')):
            ctk.CTkLabel(row, text=lbl, font=theme.F_SMALL,
                         text_color=c('muted')).pack(side='left',
                                                     padx=(0, 4))
            ent = ctk.CTkEntry(row, textvariable=self._vars[key],
                               width=70, height=26, font=theme.F_SMALL,
                               corner_radius=6, fg_color=c('entry'),
                               border_color=c('border'))
            ent.pack(side='left', padx=(0, GAP))
            ent.bind('<Return>', lambda e: self._clim_changed())
            ent.bind('<FocusOut>', lambda e: self._clim_changed())
        checkbox(disp, 'Log contours', 'log', False, self._log_changed)

        small_label(disp, 'LAYERS')
        checkbox(disp, 'Shock isosurface', 'iso', True,
                 lambda: self._toggle_layer('iso'))
        ctk.CTkLabel(disp, text='Iso level (frac of peak)',
                     font=theme.F_SMALL, text_color=c('muted'),
                     height=14, anchor='w').pack(fill='x', pady=(2, 2))
        iso = slider(disp, 0.02, 0.9, command=self._iso_changed)
        iso.set(0.10)
        iso.pack(fill='x', pady=(0, 2))
        self._vars['iso_frac'] = iso
        checkbox(disp, 'Surface loads', 'loads', True,
                 lambda: self._toggle_layer('loads'))
        checkbox(disp, 'Volume render', 'volume', False,
                 lambda: self._toggle_layer('volume'))
        checkbox(disp, 'Show mesh', 'mesh', False,
                 lambda: self._toggle_layer('mesh'))

        # ── Planes tab (VIPER-style cross-sections) ────────────────────
        small_label(planes, 'CROSS-SECTION PLANES')
        defaults = {1: ('y', True), 2: ('z', False)}
        for k in range(1, N_PLANES + 1):
            key = f'plane{k}'
            axis0, on0 = defaults.get(k, ('x', False))
            row = ctk.CTkFrame(planes, fg_color='transparent')
            row.pack(fill='x', pady=2)
            var = tk.BooleanVar(value=on0)
            self._vars[key] = var
            ctk.CTkCheckBox(row, text='', width=20, variable=var,
                            corner_radius=5, checkbox_width=19,
                            checkbox_height=19, border_width=2,
                            border_color=c('border'), fg_color=c('accent'),
                            hover_color=c('accent_hover'),
                            command=lambda k=key: self._toggle_layer(k)
                            ).pack(side='left')
            axis = ctk.CTkOptionMenu(
                row, values=('x', 'y', 'z'), width=48, height=24,
                font=theme.F_SMALL, corner_radius=6,
                fg_color=c('entry'), button_color=c('card2'),
                button_hover_color=c('border'), text_color=c('text'),
                dropdown_font=theme.F_SMALL,
                command=lambda v, k=key: self._plane_changed(k))
            axis.set(axis0)
            axis.pack(side='left', padx=(0, 4))
            pos = slider(row, 0.0, 1.0,
                         command=lambda v, k=key: self._plane_changed(k))
            pos.set(0.5)
            pos.pack(side='left', fill='x', expand=True, padx=(0, 4))
            op = ctk.CTkOptionMenu(
                row, values=[str(x) for x in range(10, 101, 10)],
                width=56, height=24, font=theme.F_SMALL, corner_radius=6,
                fg_color=c('entry'), button_color=c('card2'),
                button_hover_color=c('border'), text_color=c('text'),
                dropdown_font=theme.F_SMALL,
                command=lambda v, k=key: self._opacity_changed(k))
            op.set(100)
            op.pack(side='left')
            self._vars[f'{key}_axis'] = axis
            self._vars[f'{key}_pos'] = pos
            self._vars[f'{key}_op'] = op
        ctk.CTkLabel(planes, text='Each row: on, axis, position, opacity %',
                     font=theme.F_SMALL, text_color=c('muted'),
                     wraplength=220, justify='left', anchor='w').pack(
            fill='x', pady=(GAP, 0))

        # ── View tab ───────────────────────────────────────────────────
        small_label(viewtab, 'CAMERA PRESETS')
        grid = ctk.CTkFrame(viewtab, fg_color='transparent')
        grid.pack(fill='x', pady=4)
        grid.columnconfigure((0, 1), weight=1, uniform='v')
        for i, name in enumerate(('top', 'bottom', 'front',
                                  'back', 'left', 'right')):
            ctk.CTkButton(grid, text=name.capitalize(), height=30,
                          font=theme.F_BODY, corner_radius=theme.RADIUS,
                          fg_color=c('card2'), hover_color=c('border'),
                          text_color=c('text'),
                          command=lambda n=name: self._view_preset(n)).grid(
                row=i // 2, column=i % 2, padx=3, pady=3, sticky='we')
        checkbox(viewtab, 'Parallel projection', 'parallel', False,
                 self._parallel_changed)
        ctk.CTkButton(viewtab, text='Reset view', height=30,
                      font=theme.F_BODY, corner_radius=theme.RADIUS,
                      fg_color=c('card2'), hover_color=c('border'),
                      text_color=c('text'),
                      command=self._reset_view).pack(fill='x', pady=6)

        # ── always visible: follow / timeline / play ───────────────────
        bottom = ctk.CTkFrame(ctl, fg_color='transparent')
        bottom.pack(side='bottom', fill='x')
        checkbox(bottom, 'Follow live', 'follow', True,
                 self._follow_changed)
        ctk.CTkLabel(bottom, text='Time', font=theme.F_SMALL,
                     text_color=c('muted'), height=14, anchor='w').pack(
            fill='x', pady=(4, 2))
        self.time_slider = slider(bottom, 0, 1, command=self._time_moved)
        self.time_slider.set(0)
        self.time_slider.pack(fill='x')
        row = ctk.CTkFrame(bottom, fg_color='transparent')
        row.pack(fill='x', pady=(6, 2))
        self.play_btn = ctk.CTkButton(
            row, text='Play', image=theme.icon('play', 12, color='white'),
            compound='left', width=84, height=28, font=theme.F_BODY,
            corner_radius=theme.RADIUS, fg_color=c('accent'),
            hover_color=c('accent_hover'), text_color='white',
            command=self._toggle_play)
        self.play_btn.pack(side='left')
        ctk.CTkLabel(bottom, text='Drag: rotate   Right-drag: pan\n'
                                  'Wheel: zoom   Double-click: reset',
                     font=theme.F_SMALL, text_color=c('muted'),
                     justify='left', anchor='w').pack(
            fill='x', pady=(6, 0))

    def _tab_selected(self, value):
        self._tabs[value].tkraise()

    # ── scene lifecycle ──────────────────────────────────────────────────
    def _ensure_scene(self, init):
        """(Re)create the off-screen scene for a new run/result."""
        if not pyvista_available():
            self._log(MISSING_MSG)
            return False
        from ..viz3d.viewer import BlastScene
        self._make_plotter()
        self._scene = BlastScene(self._plotter, init, embedded=True,
                                 n_planes=N_PLANES)
        self._playing = False
        self.play_btn.configure(text='Play',
                                image=theme.icon('play', 12, color='white'))
        self._set_time_range(0)
        self._apply_all_controls()
        self._dirty = True
        return True

    def prepare_live(self, scene_info):
        """New live 3D run: build the scene; returns the Feed3D whose
        make_payload the solver thread will call (or None)."""
        feed = Feed3D(scene_info)
        if not self._ensure_scene(feed.init):
            return None
        return feed

    def adopt_feed(self, feed):
        """Attach to a Feed3D that was already built (auto-attach at run
        start: GuiHooks constructs the feed on the solver thread)."""
        return self._ensure_scene(feed.init)

    def feed_result(self, result):
        """Playback of a finished 3D Result's snapshots."""
        from ..viz3d.client import scene_from_meta
        feed = Feed3D(scene_from_meta(result.meta))
        if not self._ensure_scene(feed.init):
            return False
        names = list(result.snapshots.keys())
        for i, name in enumerate(names):
            snap = result.snapshots[name]
            payload = feed.make_payload(dict(p=snap['p']))
            rho3 = snap.get('rho3')   # stored pre-decimated, same stride rule
            if rho3 is not None and rho3.shape == payload['p'].shape:
                payload['rho'] = rho3
            self.on_frame(float(snap.get('t', 0.0)), payload,
                         final=(i == len(names) - 1))
        self.on_done(result.stop_reason)
        return True

    # ── frame flow (Tk thread) ───────────────────────────────────────────
    def on_frame(self, t, payload, final=False):
        if self._scene is None:
            return
        self._scene.on_message(('frame', t, payload, final))
        self._set_time_range(len(self._scene.store))
        if self._scene.follow_live:
            self._sync_slider(self._scene.index)
        self._sync_field_availability()
        self._sync_clim_entries()
        self._dirty = True

    def on_done(self, reason):
        if self._scene is None:
            return
        self._scene.on_message(('done', reason))
        self._vars['follow'].set(False)
        self._dirty = True

    # ── control callbacks ────────────────────────────────────────────────
    def _toggle_layer(self, key):
        if self._scene is None:
            return
        self._scene.layers[key].set_visible(self._vars[key].get())
        self._dirty = True

    def _field_changed(self):
        if self._scene is None:
            return
        self._scene.set_field(self._vars['field'].get())
        self._sync_clim_entries(force=True)
        self._dirty = True

    def _plane_changed(self, key):
        if self._scene is None:
            return
        axis = self._vars[f'{key}_axis'].get()
        frac = float(self._vars[f'{key}_pos'].get())
        self._scene.set_plane(key, axis, frac)
        self._dirty = True

    def _opacity_changed(self, key):
        if self._scene is None:
            return
        try:
            op = float(self._vars[f'{key}_op'].get()) / 100.0
        except (ValueError, tk.TclError):
            return
        self._scene.set_plane_opacity(key, op)
        self._dirty = True

    def _iso_changed(self, v):
        if self._scene is None:
            return
        self._scene._set_iso_frac(float(v))
        self._dirty = True

    def _auto_changed(self):
        if self._scene is None:
            return
        on = self._vars['auto_scale'].get()
        self._scene._set_auto_scale(on)
        if not on:
            self._clim_changed()
        self._dirty = True

    def _clim_changed(self):
        """Manual Min/Max entries applied (turns auto scale off)."""
        if self._scene is None:
            return
        try:
            vmin = float(self._vars['vmin'].get())
            vmax = float(self._vars['vmax'].get())
        except ValueError:
            return
        if vmax <= vmin:
            return
        if self._vars['auto_scale'].get():
            self._vars['auto_scale'].set(False)
        self._scene.set_clim(vmin, vmax)
        self._dirty = True

    def _log_changed(self):
        if self._scene is None:
            return
        self._scene.set_log_scale(self._vars['log'].get())
        self._dirty = True

    def _follow_changed(self):
        if self._scene is None:
            return
        self._scene._set_follow(self._vars['follow'].get())
        self._dirty = True

    def _view_preset(self, name):
        if self._scene is None:
            return
        self._scene.view_preset(name)
        self._dirty = True

    def _parallel_changed(self):
        if self._scene is None:
            return
        self._scene.set_parallel(self._vars['parallel'].get())
        self._dirty = True

    # ── control <-> scene sync ───────────────────────────────────────────
    def _sync_field_availability(self):
        for key, rb in self._field_btns.items():
            avail = self._scene is not None \
                and self._scene.field_available(key)
            rb.configure(state='normal' if avail or key == 'p'
                         else 'disabled')

    def _sync_clim_entries(self, force=False):
        """While auto scale is on, show the live range in the entries
        (skipped when an entry has keyboard focus)."""
        s = self._scene
        if s is None or not (self._vars['auto_scale'].get() or force):
            return
        focus = self.focus_get()
        if isinstance(focus, tk.Entry) and not force:
            return
        self._vars['vmin'].set(f'{s.vmin:g}')
        self._vars['vmax'].set(f'{s.cmax:g}')

    def _set_time_range(self, n):
        self._syncing_slider = True
        try:
            hi = max(1, n - 1)
            self.time_slider.configure(to=hi, number_of_steps=hi)
        finally:
            self._syncing_slider = False

    def _sync_slider(self, k):
        self._syncing_slider = True
        try:
            self.time_slider.set(k)
        finally:
            self._syncing_slider = False

    def _time_moved(self, v):
        if self._syncing_slider or self._scene is None:
            return
        if self._vars['follow'].get():
            self._vars['follow'].set(False)
            self._scene._set_follow(False)
        self._scene.show_frame(int(float(v)))
        self._dirty = True

    def _toggle_play(self):
        if self._scene is None or len(self._scene.store) < 2:
            return
        self._playing = not self._playing
        self.play_btn.configure(
            text='Pause' if self._playing else 'Play',
            image=theme.icon('pause' if self._playing else 'play',
                             12, color='white'))
        if self._playing:
            if self._vars['follow'].get():
                self._vars['follow'].set(False)
                self._scene._set_follow(False)
            self._play_tick()

    def _play_tick(self):
        if not self._playing or self._scene is None:
            return
        n = len(self._scene.store)
        if n > 1:
            k = (self._scene.index + 1) % n
            self._scene.show_frame(k)
            self._sync_slider(k)
            self._dirty = True
        self.after(120, self._play_tick)

    def _apply_all_controls(self):
        """Push current Tk control state into a freshly built scene."""
        s = self._scene
        for key in (['iso', 'loads', 'volume', 'mesh']
                    + [f'plane{k}' for k in range(1, N_PLANES + 1)]):
            s.layers[key].set_visible(self._vars[key].get())
        s.set_field(self._vars['field'].get())
        s._set_iso_frac(float(self._vars['iso_frac'].get()))
        s._set_auto_scale(self._vars['auto_scale'].get())
        s.set_log_scale(self._vars['log'].get())
        if not self._vars['auto_scale'].get():
            self._clim_changed()
        s._set_follow(self._vars['follow'].get())
        s.set_parallel(self._vars['parallel'].get())
        for k in range(1, N_PLANES + 1):
            self._plane_changed(f'plane{k}')
            self._opacity_changed(f'plane{k}')
        self._sync_field_availability()
