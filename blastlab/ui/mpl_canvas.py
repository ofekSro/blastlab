"""Host for the matplotlib figures the Qt front-end still shows.

pyqtgraph draws the interactive views; matplotlib keeps the figures whose
builders are shared with the file exports and would be pointless to
re-author for the screen: the Setup previews, the Results gauge traces,
the 1D profile set and the 3D isosurface page.

As in the Tk app, the GUI never imports pyplot - its global figure
manager fights the event loop and leaks figures. Callers build an OO
`matplotlib.figure.Figure` (usually through `blastlab/output/plots.py`)
and hand it over with `set_figure`.
"""

from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from . import theme

#: the Qt binding must be settled before matplotlib's Qt backend loads,
#: or it can pick a different one that is also installed
import os                                                    # noqa: E402
os.environ.setdefault('QT_API', 'PySide6')

from matplotlib.backends.backend_qtagg import (               # noqa: E402
    FigureCanvasQTAgg, NavigationToolbar2QT)


class MplCanvas(QWidget):
    """A matplotlib canvas in a Qt layout. `set_figure(fig)` adopts a
    figure (restyling it for the current appearance mode first), `draw()`
    schedules a repaint, `retheme()` re-runs the restyle after a
    dark/light switch.

    Call only from the GUI thread.
    """

    def __init__(self, toolbar=False, parent=None):
        super().__init__(parent)
        self._want_toolbar = bool(toolbar)
        self._canvas = None
        self._toolbar = None
        self._figure = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._lay = lay
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        theme.signals.changed.connect(self._on_theme)

    # ── figure ───────────────────────────────────────────────────────────
    @property
    def figure(self):
        return self._figure

    def set_figure(self, fig):
        """Show `fig` (None clears the canvas). The canvas is rebuilt, as
        the Tk host did: a figure swap changes the artist tree wholesale
        and reusing one canvas across figures leaks the old one."""
        self._teardown()
        self._figure = fig
        if fig is None:
            return None
        theme.style_figure(fig)
        self._canvas = FigureCanvasQTAgg(fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding,
                                   QSizePolicy.Expanding)
        if self._want_toolbar:
            self._toolbar = NavigationToolbar2QT(self._canvas, self)
            self._lay.addWidget(self._toolbar)
        self._lay.addWidget(self._canvas, 1)
        self._canvas.draw_idle()
        return fig

    def blank(self, text='', figsize=(6, 5)):
        """An empty axis, optionally carrying one muted line of text.

        Results panels need this on every switch: without it the
        PREVIOUS result's figure stays on screen under a result that has
        none, which reads as this result's data."""
        from matplotlib.figure import Figure
        fig = Figure(figsize=figsize)
        ax = fig.add_subplot()
        ax.axis('off')
        if text:
            ax.text(0.5, 0.5, str(text), transform=ax.transAxes,
                    ha='center', va='center', fontsize=10,
                    color=theme.cur('muted'))
        return self.set_figure(fig)

    def draw(self):
        if self._canvas is not None:
            self._canvas.draw_idle()

    def retheme(self):
        if self._figure is not None:
            theme.style_figure(self._figure)
            self.draw()

    def _on_theme(self, _mode=None):
        self.retheme()

    # ── lifetime ─────────────────────────────────────────────────────────
    def _teardown(self):
        for w in (self._toolbar, self._canvas):
            if w is None:
                continue
            self._lay.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._toolbar = self._canvas = None
        self._figure = None

    def close_figure(self):
        self._teardown()
