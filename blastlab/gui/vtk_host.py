"""Shared Tk host for off-screen pyvista scenes.

VtkTkHost owns the blit loop: an off-screen plotter is screenshotted
into a Tk label as a PPM PhotoImage (~20 fps when dirty), with mouse
orbit / pan / zoom forwarded to the hosted scene's camera ops. Both the
run-time 3D view (View3DPanel) and the Setup preview extend this.

pyvista is only imported lazily inside methods, guarded by
`pyvista_available()` at the call sites.
"""

import time
import tkinter as tk

import customtkinter as ctk

from . import theme


class VtkTkHost(ctk.CTkFrame):
    """A frame displaying an off-screen VTK render.

    Subclasses set `self._scene` to an object with the _CameraOps API
    (orbit/pan/zoom_view/reset_view) and call `self._mark_dirty()` when
    the scene changed; `self._plotter` is created via `_make_plotter`.
    The viewport stays dark in both appearance modes (like a video
    player), so it uses plain hex colors rather than mode tuples.
    """

    PLACEHOLDER = ''

    def __init__(self, parent, log_fn=print, view_size=(760, 560)):
        super().__init__(parent, fg_color='transparent', corner_radius=0)
        self._log = log_fn
        self._scene = None
        self._plotter = None
        self._dirty = False
        self._photo = None
        self._drag = None
        self._view_size = view_size
        self._last_resize = 0.0
        self._build_view()
        self.after(50, self._render_tick)

    # ── plotter / view ────────────────────────────────────────────────────
    def _make_plotter(self):
        """(Re)create the off-screen plotter at the current view size."""
        import pyvista as pv
        if self._plotter is not None:
            try:
                self._plotter.close()
            except Exception:
                pass
        self._plotter = pv.Plotter(off_screen=True,
                                   window_size=list(self._view_size))
        return self._plotter

    def _build_view(self):
        self.view = tk.Label(self, background=theme.DARK['view'],
                             foreground=theme.DARK['muted'],
                             anchor='center', font=(theme.FONT, 12),
                             borderwidth=0, highlightthickness=0,
                             text=self.PLACEHOLDER)
        self.view.pack(side='left', fill='both', expand=True,
                       padx=(2, 4), pady=4)
        self.view.bind('<ButtonPress-1>', self._mouse_down)
        self.view.bind('<B1-Motion>', lambda e: self._mouse_drag(e, 'orbit'))
        self.view.bind('<ButtonPress-3>', self._mouse_down)
        self.view.bind('<B3-Motion>', lambda e: self._mouse_drag(e, 'pan'))
        self.view.bind('<MouseWheel>', self._mouse_wheel)
        self.view.bind('<Double-Button-1>', lambda e: self._reset_view())
        self.view.bind('<Configure>', self._resized)

    def _mark_dirty(self):
        self._dirty = True

    # ── mouse camera control ─────────────────────────────────────────────
    def _mouse_down(self, e):
        self._drag = (e.x, e.y)

    def _mouse_drag(self, e, mode):
        if self._scene is None or self._drag is None:
            return
        dx, dy = e.x - self._drag[0], e.y - self._drag[1]
        self._drag = (e.x, e.y)
        if mode == 'orbit':
            self._scene.orbit(-0.4 * dx, 0.4 * dy)
        else:
            h = max(1, self.view.winfo_height())
            self._scene.pan(dx / h, dy / h)
        self._dirty = True

    def _mouse_wheel(self, e):
        if self._scene is None:
            return
        self._scene.zoom_view(1.1 if e.delta > 0 else 1 / 1.1)
        self._dirty = True

    def _reset_view(self):
        if self._scene is None:
            return
        self._scene.reset_view()
        self._dirty = True

    # ── rendering ────────────────────────────────────────────────────────
    def _resized(self, e):
        w, h = max(200, e.width), max(200, e.height)
        if abs(w - self._view_size[0]) < 12 and \
           abs(h - self._view_size[1]) < 12:
            return
        self._view_size = (w, h)
        self._last_resize = time.monotonic()

    def _render_tick(self):
        try:
            if self._scene is not None and self._plotter is not None:
                # debounced resize: apply once the size has settled
                if self._last_resize and \
                        time.monotonic() - self._last_resize > 0.4:
                    self._last_resize = 0.0
                    self._plotter.window_size = list(self._view_size)
                    self._dirty = True
                if self._dirty:
                    self._dirty = False
                    self._blit()
        except Exception as exc:      # never kill the Tk timer loop
            self._log(f'3D view render error: {exc}')
        self.after(50, self._render_tick)

    def _blit(self):
        # pyvista's screenshot() only renders on its FIRST call; without
        # an explicit render every blit would show a stale frame.
        self._plotter.render()
        img = self._plotter.screenshot(return_img=True)
        h, w = img.shape[:2]
        ppm = b'P6\n%d %d\n255\n' % (w, h) + img.tobytes()
        self._photo = tk.PhotoImage(data=ppm, format='PPM')
        self.view.configure(image=self._photo, text='')
