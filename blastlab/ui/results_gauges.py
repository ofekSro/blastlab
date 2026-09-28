"""The Results tab's Gauges view: the traces plus the per-gauge
engineering summary (peak, arrival, positive-phase duration and
impulse, net impulse).

Two layout rules are load-bearing and were each paid for once in Tk:

- The field selector's whole row is hidden when there is nothing to
  choose. An empty container kept its requested height and painted a
  200 px dead band above the figure for every pressure-only result.
- The table gets a fixed minimum height and the canvas takes the
  stretch, never the other way round. The table is the ONLY place the
  peak / arrival / phase / impulse numbers appear in the UI, and under
  the old packing order it was simply not on screen below ~1060 px.

The traces stay on matplotlib: `figure_gauges_1d` / `figure_gauges_nd`
are shared with the PNG and report exports, and re-authoring them in
pyqtgraph would be two builders to keep in step instead of one.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QSizePolicy,
                               QTableWidget, QTableWidgetItem, QWidget)

from ..models.meta import charge_label
from ..output import gauge_summary, plots
from . import theme
from .mpl_canvas import MplCanvas
from .widgets import Segmented, hbox, label, vbox

#: the summary table, in `gauge_summary.COLUMNS` order. The headers are
#: abbreviated to fit, so each one carries a tooltip saying what it is.
COLUMNS = ('gauge', 'peak', 'arrival', 't_peak', 'pos_dur', 'pos_imp',
           'net_imp', 'complete')
HEADERS = ('Gauge (cell)', 'Peak ovp [kPa]', 'Arrival [ms]', 't peak [ms]',
           'Pos. phase [ms]', 'Pos. imp [Pa·s]', 'Net imp [Pa·s]',
           'Phase ended')
HEADER_HELP = {
    'gauge': 'Gauge number, where you asked for it and, when the solver '
             'had to snap it, the cell centre it reads.',
    'peak': 'Highest overpressure seen at this gauge.',
    'arrival': 'First time the overpressure crossed the arrival '
               'threshold.',
    't_peak': 'Time of the peak overpressure.',
    'pos_dur': 'Length of the positive phase, from arrival to the first '
               'return to ambient.',
    'pos_imp': 'Overpressure impulse of the positive phase only.',
    'net_imp': 'Overpressure impulse over the whole record, negative '
               'phase included.',
    'complete': 'Whether the positive phase ended inside the run - "no" '
                'means the run stopped first, so the impulses are lower '
                'bounds.',
}

#: the table shows at most this many rows and scrolls beyond, exactly as
#: the Tk Treeview's `height=4` did. Without a cap the table's own size
#: hint grows with the gauge count and starves the traces: measured at
#: 900x600 with three gauges, table 192 px against canvas 136 px.
MAX_ROWS_SHOWN = 4

#: and never more than this share of the panel. Four rows is a small
#: table until the panel itself is small: measured at 900x600 with
#: twelve gauges and a wrapped export row, the table took 156 px against
#: 128 px of traces, which inverts the rule it exists to serve.
TABLE_MAX_SHARE = 0.42


class GaugesView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ent = None
        self._title_extra = None
        self._field = 'p'

        root = vbox(self)
        # the selector and its caption live in one widget, shown and
        # hidden together (UX-05)
        self._bar = QWidget()
        bar = hbox(self._bar)
        bar.addWidget(label('Trace', 'muted'))
        self.field_seg = Segmented(['p'], height=26, small=True)
        self.field_seg.setFixedWidth(200)
        self.field_seg.changed.connect(self._field_changed)
        bar.addWidget(self.field_seg)
        bar.addStretch(1)
        self._bar.setVisible(False)
        root.addWidget(self._bar)

        self.canvas = MplCanvas()
        root.addWidget(self.canvas, 1)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(HEADERS))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        head = self.table.horizontalHeader()
        head.setStretchLastSection(True)
        for i, col in enumerate(COLUMNS):
            head.setSectionResizeMode(
                i, QHeaderView.Interactive if col == 'gauge'
                else QHeaderView.Stretch)
            self.table.horizontalHeaderItem(i).setToolTip(HEADER_HELP[col])
        self.table.setColumnWidth(0, 150)
        # the traces take the stretch; the table takes what it needs up
        # to MAX_ROWS_SHOWN and no more
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root.addWidget(self.table, 0)
        self._cap_height()
        theme.signals.changed.connect(lambda *_: self.canvas.retheme())

    # ── state ────────────────────────────────────────────────────────────
    def set_title_extra(self, text):
        self._title_extra = text or None

    def field(self):
        return self._field

    def selector_visible(self):
        """Whether the row is part of the layout. Deliberately not
        `isVisible()`, which is False for every widget on a stack page
        that is not the current one."""
        return not self._bar.isHidden()

    #: said in place of a bare empty axis before any run exists
    NO_RESULT = ('Add gauges to a case and its traces appear here, with '
                 'the per-gauge numbers below.')

    def clear(self):
        self._ent = None
        self.canvas.blank(self.NO_RESULT)
        self.table.setRowCount(0)
        self._cap_height()
        self._bar.setVisible(False)

    def set_result(self, ent):
        self._ent = ent
        if ent is None:
            self.clear()
            return
        self.redraw()

    # ── drawing ──────────────────────────────────────────────────────────
    def _field_changed(self, value):
        self._field = value or 'p'
        self.redraw()

    def _sync_selector(self, ent):
        """Offer the trace fields this result actually recorded; hide the
        row entirely when pressure is the only one."""
        fields = plots.gauge_fields_available(ent.result.gauges)
        if len(fields) > 1 and ent.dim != 1:
            if self.field_seg.values() != list(fields):
                new = Segmented(list(fields), height=26, small=True)
                # OUT-4a: up to seven traces; 200 px holds the T44 three
                new.setFixedWidth(200 if len(fields) <= 3
                                  else 80 * len(fields))
                new.changed.connect(self._field_changed)
                lay = self._bar.layout()
                lay.replaceWidget(self.field_seg, new)
                self.field_seg.deleteLater()
                self.field_seg = new
            if self._field not in fields:
                self._field = 'p'
            self.field_seg.set(self._field)
            self._bar.setVisible(True)
        else:
            self._field = 'p'
            self.field_seg.set('p')
            self._bar.setVisible(False)

    def redraw(self):
        ent = self._ent
        if ent is None:
            return
        self._sync_selector(ent)
        res = ent.result
        try:
            if ent.dim == 1:
                c = charge_label(res.meta, radius=False)
                fig = plots.figure_gauges_1d(
                    res.gauges, c.charge_kg, c.eos,
                    title_extra=self._title_extra)
            else:
                fig = plots.figure_gauges_nd(
                    res.gauges, res.meta, field=self._field,
                    title_extra=self._title_extra)
        except Exception:
            fig = None
        # a result with no gauges returns None: keep whatever was on
        # screen rather than blanking to a bare axis
        if fig is not None:
            self.canvas.set_figure(fig)
        self.fill_summary(res)

    def summary_rows(self, res):
        from .exports import summary_rows
        return summary_rows(res)

    def _cap_height(self):
        """Hold the table to header + at most MAX_ROWS_SHOWN rows AND at
        most TABLE_MAX_SHARE of the panel, so a run with twenty gauges
        scrolls instead of squeezing the traces out."""
        head = self.table.horizontalHeader().sizeHint().height()
        n = self.table.rowCount()
        row = (self.table.rowHeight(0) if n
               else self.table.verticalHeader().defaultSectionSize())
        frame = 2 * self.table.frameWidth() + 2
        floor = head + row + frame                    # header + one row
        want = head + max(1, min(n, MAX_ROWS_SHOWN)) * row + frame
        h = self.height()
        share = int(h * TABLE_MAX_SHARE) if h > 0 else want
        cap = max(floor, min(want, share))
        self.table.setMinimumHeight(min(floor, cap))
        self.table.setMaximumHeight(cap)

    def resizeEvent(self, event):
        # the cap depends on the panel's height, so it is not a
        # build-time decision
        super().resizeEvent(event)
        self._cap_height()

    def fill_summary(self, res):
        rows = gauge_summary.table_rows(self.summary_rows(res))
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignVCenter | (
                    Qt.AlignLeft if c == 0 else Qt.AlignRight))
                self.table.setItem(r, c, item)
        self._cap_height()

    def rows(self):
        """The table as it stands, for tests and the QA harness."""
        return [tuple((self.table.item(r, c).text()
                       if self.table.item(r, c) is not None else '')
                      for c in range(self.table.columnCount()))
                for r in range(self.table.rowCount())]
