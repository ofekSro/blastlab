"""Matplotlib embedding for Tkinter.

The GUI never imports pyplot: pyplot's global figure manager fights the
app mainloop and leaks figures. All figures are OO `Figure` objects
rendered into a FigureCanvasTkAgg that lives inside a Tk frame.

Every figure shown here is restyled by theme.style_figure to match the
current appearance mode (export paths build separate figures and are
unaffected); instances register with the theme so a dark/light toggle
re-themes whatever is on screen.
"""

import tkinter as tk

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg,
                                               NavigationToolbar2Tk)
from matplotlib.figure import Figure

from . import theme


class EmbeddedFigure(ctk.CTkFrame):
    """A frame holding one matplotlib canvas (+ optional toolbar).

    `set_figure(fig)` swaps in a new Figure by rebuilding the canvas;
    `figure` returns the current one. Call only from the Tk main thread.
    (Attributes are prefixed _mpl_: CTkFrame keeps its own `_canvas`.)
    """

    def __init__(self, parent, figsize=(6, 5), toolbar=True):
        super().__init__(parent, fg_color='transparent', corner_radius=0)
        self._want_toolbar = toolbar
        self._mpl_canvas = None
        self._mpl_toolbar = None
        theme.register_embedded(self)
        self.set_figure(Figure(figsize=figsize))

    @property
    def figure(self):
        return self._mpl_canvas.figure if self._mpl_canvas else None

    def set_figure(self, fig):
        self._teardown()
        theme.style_figure(fig)
        self._mpl_canvas = FigureCanvasTkAgg(fig, master=self)
        w = self._mpl_canvas.get_tk_widget()
        w.configure(background=theme.cur('card'), highlightthickness=0,
                    borderwidth=0)
        w.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        if self._want_toolbar:
            self._mpl_toolbar = NavigationToolbar2Tk(self._mpl_canvas, self,
                                                     pack_toolbar=False)
            self._mpl_toolbar.update()
            self._mpl_toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self._style_chrome()
        self._mpl_canvas.draw_idle()

    def retheme(self):
        """Restyle the current figure for the active appearance mode."""
        if self._mpl_canvas is None:
            return
        theme.style_figure(self._mpl_canvas.figure)
        self._style_chrome()
        self._mpl_canvas.draw_idle()

    def _style_chrome(self):
        bg = theme.cur('card')
        if self._mpl_canvas is not None:
            self._mpl_canvas.get_tk_widget().configure(background=bg)
        if self._mpl_toolbar is not None:  # plain tk widgets: best effort
            try:
                self._mpl_toolbar.configure(background=bg)
                for child in self._mpl_toolbar.winfo_children():
                    try:
                        child.configure(background=bg)
                    except tk.TclError:
                        pass
                    try:
                        child.configure(foreground=theme.cur('muted'))
                    except tk.TclError:
                        pass
                    # matplotlib >= 3.5 re-tints button icons from the
                    # button background's luminance (private, so guarded)
                    try:
                        self._mpl_toolbar._set_image_for_button(child)
                    except Exception:
                        pass
            except tk.TclError:
                pass

    def draw(self):
        if self._mpl_canvas is not None:
            self._mpl_canvas.draw_idle()

    def _teardown(self):
        if self._mpl_toolbar is not None:
            self._mpl_toolbar.destroy()
            self._mpl_toolbar = None
        if self._mpl_canvas is not None:
            self._mpl_canvas.get_tk_widget().destroy()
            self._mpl_canvas = None

    def close(self):
        self._teardown()
