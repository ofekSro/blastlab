"""The Results screen's Gauges view (GUI-7 T5, board Results lines
107-189): every gauge on ONE pyqtgraph plot, the selected one in `gauge`
cyan with its positive phase shaded, a readout of it, and the summary
table - Gauge · Z · the per-gauge numbers - which can be copied.

Numbers are never re-derived here:

- each curve is the trace `plots.GAUGE_FIELDS[field]` names: x = times x
  1e3 [ms], y = the field's own transform ((p - P_AIR) / 1e3 for p). These
  are exactly the arrays the exported matplotlib grid
  (`figure_gauges_1d` / `figure_gauges_nd`) plots;
- every cell but Gauge and Z is `gauge_summary.table_rows(...)`'s string,
  unchanged. The impulse is the same number the export writes: 1 Pa·s =
  1 kPa·ms, so only the header's unit differs from the CSV's `_Pa_s`
  columns, which are not touched;
- Z is `scaled_distance.scaled_distance` (UFC 3-340-02 para. 2-13.1, as
  cited there) of the entered gauge each row belongs to, found by
  `run_gauges.match_gauges` (D61 / D73): the Run screen's Z.

The shading is the positive phase and the caption says the net impulse
includes the negative one: UFC 3-340-02 (2008), para. 2-12, printed
p. 43 - the incident pressure decays to ambient in the positive phase
duration, then a negative phase follows; the impulse of each is the area
under its part of the curve. `gauge_summary` computes both (CLAUDE.md 7).

Screen and file differ by design (the on-screen rule, CLAUDE.md 5): the
exported gauge figure (All plots, Report) is still the matplotlib grid,
one panel per gauge. The plot header's tooltip says so.

Two layout rules from the view this replaces still hold: the Trace
selector's row is hidden when pressure is the only trace, and the table
is capped (MAX_ROWS_SHOWN rows, TABLE_MAX_SHARE of the view) so the plot
keeps the stretch.
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFrame,
                               QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QSizePolicy, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ..output import gauge_summary, plots
from . import scaled_distance as sd
from . import theme
from .run_gauges import match_gauges
from .widgets import Segmented, WrapRow, hbox, label

#: the table, left to right. 'gauge' and 'z' are this view's; the rest
#: are `gauge_summary.COLUMNS[1:]`, in that order
COLUMNS = ('gauge', 'z', 'peak', 'arrival', 't_peak', 'pos_dur', 'pos_imp',
           'net_imp', 'complete')
#: board lines 161-169. The impulses are in kPa·ms on screen: the same
#: number as the Pa·s the exported CSV keeps (1 Pa·s = 1 kPa·ms)
HEADERS = ('Gauge', sd.LABEL, 'Peak [kPa]', 'Arrival [ms]', 't peak [ms]',
           'Pos. phase [ms]', 'Pos. impulse [kPa·ms]',
           'Net impulse [kPa·ms]', 'Phase ended')
#: the same headers on two lines, used when the table is too narrow for
#: one (the copied text always uses HEADERS)
HEADERS_WRAPPED = ('Gauge', 'Z\n[m/kg^1/3]', 'Peak\n[kPa]', 'Arrival\n[ms]',
                   't peak\n[ms]', 'Pos. phase\n[ms]',
                   'Pos. impulse\n[kPa·ms]', 'Net impulse\n[kPa·ms]',
                   'Phase\nended')
HEADER_HELP = {
    'gauge': 'Gauge number, in the order the solver reports them. The '
             'tooltip of each cell says where you asked for it and, when '
             'the solver had to snap it, the cell centre it reads.',
    'z': 'Scaled distance Z = R / W^(1/3) of the gauge as entered, W the '
         'charge mass as entered (UFC 3-340-02, para. 2-13.1). Hidden for '
         'planar 2D and for a run started from a profile.',
    'peak': 'Highest overpressure seen at this gauge.',
    'arrival': 'First time the overpressure crossed the arrival '
               'threshold.',
    't_peak': 'Time of the peak overpressure.',
    'pos_dur': 'Length of the positive phase, from arrival to the first '
               'return to ambient.',
    'pos_imp': 'Overpressure impulse of the positive phase only. '
               '1 kPa·ms = 1 Pa·s: the same number the exported CSV '
               'writes in Pa·s.',
    'net_imp': 'Overpressure impulse over the whole record, negative '
               'phase included (1 kPa·ms = 1 Pa·s).',
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

#: board lines 112 and 154
PLOT_CAPTION = ('selected gauge in colour, the others grey · shaded: '
                'positive phase')
TABLE_CAPTION = ('click a row to plot it · net impulse includes the '
                 'negative phase')
PLOT_TIP = ('On screen, every gauge on one plot. The exported gauge '
            'figure (All plots .png, Report .html) is the grid of '
            'matplotlib panels, one per gauge.')
COPY_TIP = ('Copy the table as tab-separated text with its headers '
            '(Ctrl+C while the table has focus)')

#: the unselected curves (board: #4a4a50). The board's grey is 2.09:1 on
#: the dark `tile`, under the 3:1 a non-text line needs (plan §2.2), so it
#: is lightened just enough; the light value is derived the same way.
GREY = {'dark': '#626268', 'light': '#89898f'}
SELECTED_W, OTHER_W = 2.4, 1.2
#: the positive phase's shading: `gauge` at 16 % (board line 131)
SHADE_ALPHA = 0.16


def field_name(field):
    """`Overpressure` for 'p': the y-label of GAUGE_FIELDS without its
    unit, so the header and the axis cannot disagree."""
    return plots.GAUGE_FIELDS[field][1].split(' [')[0]


def traces(gauge_out, field='p'):
    """[(x [ms], y)] per gauge, in gauge order: the arrays the matplotlib
    builders plot (`figure_gauges_1d` / `figure_gauges_nd`)."""
    key, _ylabel, tr = plots.GAUGE_FIELDS[field]
    times = gauge_out.get('times')
    where = gauge_out.get('radii')
    if where is None:
        where = gauge_out.get('points')
    series = gauge_out.get(key) or gauge_out.get('pressures')
    if times is None or where is None or series is None:
        return []
    x = np.asarray(times) * 1e3
    return [(x, tr(p)) for p, _pos in zip(series, where)]


def z_values(res, dim):
    """{G number: Z} for the gauges of `res`, or None when Z is hidden
    (planar 2D, a profile start, a meta missing a key). Z of the ENTERED
    gauge each series belongs to (D61), the snapped position only when no
    entered gauge is within a cell."""
    case = sd.case_from_meta(res.meta, dim, res.gauges)
    if case is None or not sd.z_shown(case):
        return None
    positions = res.gauges.get('radii')
    if positions is None:
        positions = res.gauges.get('points')
    if positions is None:
        return None
    positions = [tuple(np.ravel(p).astype(float)) for p in
                 ([[r] for r in positions] if dim == 1 else positions)]
    entered = sd.gauge_points(case)
    match = match_gauges(case, res.gauges)
    out = {}
    burst = len(sd.burst_point(case))
    for k, pos in enumerate(positions):
        j = match[k] if k < len(match) else None
        point = entered[j] if j is not None else pos
        if len(point) != burst:
            continue
        try:
            out[k + 1] = sd.scaled_distance(case, point)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    return out


class _Table(QTableWidget):
    """The summary table. Ctrl+C with the table focused copies the whole
    table: the key is caught here, before the item view's own copy (the
    current cell's text). Only a focused table sees it, so Ctrl+C in any
    text box keeps its own copy, and no QShortcut is added to the window
    (test_ui_frame F5 pins the window's five keys; D105)."""

    copy_requested = Signal()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class GaugesView(QWidget):
    #: a gauge was selected (its G number): a row click, or select()
    gauge_selected = Signal(int)

    #: said in place of a bare empty axis before any run exists
    NO_RESULT = ('Add gauges to a case and its traces appear here, with '
                 'the per-gauge numbers below.')
    NO_GAUGES = 'This result has no gauges.'

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ent = None
        self._title_extra = None
        self._field = 'p'
        self._summary = []          # summary_rows(res), gauge order
        self._strings = []          # table_rows of those, gauge order
        self._z = None              # {number: Z} or None (hidden)
        self._order = []            # G numbers, top to bottom
        self._sel = None            # the selected G number
        self._wrapped = False
        self._syncing = False
        self.curves = {}            # G number -> PlotDataItem

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # ── the plot card (board 109-149) ────────────────────────────────
        card = QFrame()
        card.setObjectName('gaugeplotcard')
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 8)
        cl.setSpacing(6)
        head = QHBoxLayout()
        head.setContentsMargins(4, 0, 0, 0)
        head.setSpacing(10)
        self.head_lbl = QLabel('Overpressure at the gauges')
        self.head_lbl.setObjectName('gaugehead')
        self.head_lbl.setToolTip(PLOT_TIP)
        head.addWidget(self.head_lbl, 0, Qt.AlignBaseline)
        self.head_caption = QLabel(PLOT_CAPTION)
        self.head_caption.setObjectName('gaugecaption')
        self.head_caption.setMinimumWidth(0)
        self.head_caption.setSizePolicy(QSizePolicy.Ignored,
                                        QSizePolicy.Preferred)
        self.head_caption.setToolTip(PLOT_CAPTION)
        head.addWidget(self.head_caption, 1, Qt.AlignBaseline)
        # the selector and its caption live in one widget, shown and
        # hidden together (UX-05)
        self._bar = QWidget()
        bar = hbox(self._bar)
        bar.addWidget(label('Trace', 'muted'))
        self.field_seg = Segmented(['p'], height=26, small=True)
        self.field_seg.setFixedWidth(200)
        self.field_seg.changed.connect(self._field_changed)
        bar.addWidget(self.field_seg)
        self._bar.setVisible(False)
        head.addWidget(self._bar, 0)
        cl.addLayout(head)

        self.plot_stack = QStackedWidget()
        self.plot_w = pg.PlotWidget()
        self.plot_w.setMenuEnabled(False)
        self.plot_w.hideButtons()
        self.plot_w.setFocusPolicy(Qt.NoFocus)
        self.plot_w.setMinimumHeight(60)
        self.plot = self.plot_w.getPlotItem()
        self.plot.setLabel('bottom', 'time [ms]')
        self.plot.setLabel('left', plots.GAUGE_FIELDS['p'][1])
        self.plot.showGrid(x=False, y=True, alpha=0.25)
        self.plot_stack.addWidget(self.plot_w)             # 0: the plot
        self.hint = label('', 'muted', wrap=True, align=Qt.AlignCenter)
        self.plot_stack.addWidget(self.hint)               # 1: nothing
        cl.addWidget(self.plot_stack, 1)
        # the positive phase: filled between the selected curve's window
        # and zero (two data-only curves, never drawn themselves)
        self._fill_top = pg.PlotCurveItem(pen=None)
        self._fill_zero = pg.PlotCurveItem(pen=None)
        self.fill = pg.FillBetweenItem(self._fill_top, self._fill_zero)
        self.fill.setZValue(1)
        self._fill_span = None
        self._zero = pg.InfiniteLine(pos=0.0, angle=0, movable=False)
        self._zero.setZValue(0.5)
        self.plot.addItem(self._zero)

        # the readout of the selected gauge (board 144-148), under the
        # plot rather than over it; its three parts wrap onto a second
        # line on a narrow window instead of holding the centre wide
        self.readout = [QLabel(''), QLabel(''), QLabel('')]
        self.readout[0].setObjectName('gaugereadsel')
        for w in self.readout[1:]:
            w.setObjectName('gaugeread')
        self._readout_row = WrapRow(spacing=16)
        self._readout_row.setContentsMargins(4, 0, 0, 0)
        for w in self.readout:
            self._readout_row.add(w)
        cl.addWidget(self._readout_row)
        root.addWidget(card, 1)
        self.plot_card = card

        # ── the table card (board 151-188) ───────────────────────────────
        tcard = QFrame()
        tcard.setObjectName('gaugetablecard')
        tl = QVBoxLayout(tcard)
        tl.setContentsMargins(1, 1, 1, 1)
        tl.setSpacing(0)
        thead = QWidget()
        thead.setObjectName('gaugetablehead')
        th = QHBoxLayout(thead)
        th.setContentsMargins(14, 6, 12, 6)
        th.setSpacing(10)
        ttl = QLabel('Summary')
        ttl.setObjectName('gaugesumtitle')
        th.addWidget(ttl)
        self.table_caption = QLabel(TABLE_CAPTION)
        self.table_caption.setObjectName('gaugecaption')
        self.table_caption.setMinimumWidth(0)
        self.table_caption.setSizePolicy(QSizePolicy.Ignored,
                                         QSizePolicy.Preferred)
        self.table_caption.setToolTip(TABLE_CAPTION)
        th.addWidget(self.table_caption, 1)
        self.copy_btn = QPushButton('Copy table')
        self.copy_btn.setObjectName('gaugecopy')
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setToolTip(COPY_TIP)
        bl = QHBoxLayout(self.copy_btn)
        bl.setContentsMargins(0, 0, 10, 0)
        bl.addStretch(1)
        self.copy_key = QLabel('Ctrl+C')
        self.copy_key.setObjectName('gaugecopykey')
        self.copy_key.setAttribute(Qt.WA_TransparentForMouseEvents)
        bl.addWidget(self.copy_key)
        self.copy_btn.clicked.connect(lambda *_: self.copy_table())
        th.addWidget(self.copy_btn)
        tl.addWidget(thead)
        self._table_head = thead
        self.table_card = tcard

        self.table = _Table(0, len(COLUMNS))
        self.table.setObjectName('gaugetable')
        self.table.setHorizontalHeaderLabels(list(HEADERS))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # the selected gauge is painted by the view (gauge_bg), so the
        # cells keep their own colours; a click or the arrow keys move
        # the current row, which selects the gauge
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.StrongFocus)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        head = self.table.horizontalHeader()
        head.setStretchLastSection(True)
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setDefaultAlignment(Qt.AlignRight | Qt.AlignVCenter)
        head.setHighlightSections(False)
        for i, col in enumerate(COLUMNS):
            self.table.horizontalHeaderItem(i).setToolTip(HEADER_HELP[col])
        for i in (0, len(COLUMNS) - 1):
            self.table.horizontalHeaderItem(i).setTextAlignment(
                Qt.AlignLeft | Qt.AlignVCenter)
        # the plot takes the stretch; the table takes what it needs up to
        # MAX_ROWS_SHOWN and no more
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.table.currentCellChanged.connect(self._current_moved)
        # Ctrl+C while the table has focus (never window-wide)
        self.table.copy_requested.connect(self.copy_table)
        tl.addWidget(self.table)
        root.addWidget(tcard, 0)
        self._cap_height()
        theme.signals.changed.connect(self._retheme)
        self._retheme()
        self.clear()

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

    def clear(self):
        self._ent = None
        self._summary, self._strings, self._z = [], [], None
        self._order, self._sel = [], None
        self._drop_curves()
        self.hint.setText(self.NO_RESULT)
        self.plot_stack.setCurrentIndex(1)
        self.table.setRowCount(0)
        self._set_readout(None)
        self._cap_height()
        self._bar.setVisible(False)

    def set_result(self, ent):
        """Adopt a result; the selection goes back to its default."""
        self._ent = ent
        self._sel = None
        if ent is None:
            self.clear()
            return
        self.redraw()

    def page(self):
        """'plot' | 'empty' - what the plot area shows."""
        return ('plot', 'empty')[self.plot_stack.currentIndex()]

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
        self._summary = self.summary_rows(res)
        self._strings = gauge_summary.table_rows(self._summary)
        try:
            self._z = z_values(res, ent.dim)
        except Exception:
            self._z = None
        self._draw_curves(res)
        self.fill_summary(res)
        if self._sel not in self._order:
            self._sel = self._default_gauge(res)
        self._apply_selection(emit=False)

    def _drop_curves(self):
        for c in self.curves.values():
            self.plot.removeItem(c)
        self.curves = {}
        if self.fill.scene() is not None:
            self.plot.removeItem(self.fill)
        self._fill_span = None

    def _draw_curves(self, res):
        self._drop_curves()
        try:
            data = traces(res.gauges, self._field)
        except Exception:
            data = []
        ylabel = plots.GAUGE_FIELDS[self._field][1]
        self.plot.setLabel('left', ylabel)
        self.head_lbl.setText(f'{field_name(self._field)} at the gauges')
        self.plot.setTitle(self._title_extra)
        if not data:
            self.hint.setText(self.NO_GAUGES)
            self.plot_stack.setCurrentIndex(1)
            return
        for k, (x, y) in enumerate(data, start=1):
            c = pg.PlotDataItem(x, y)
            self.plot.addItem(c)
            self.curves[k] = c
        self.plot.addItem(self.fill)
        self.plot.enableAutoRange()
        self.plot_stack.setCurrentIndex(0)

    def summary_rows(self, res):
        from .exports import summary_rows
        return summary_rows(res)

    def _default_gauge(self, res):
        """The trigger gauge when the run had one, else the first row."""
        trig = res.meta.get('trigger_gauge')
        if trig in self._order:
            return trig
        return self._order[0] if self._order else None

    # ── the table ────────────────────────────────────────────────────────
    def z_shown(self):
        return self._z is not None

    def _z_text(self, number):
        z = None if self._z is None else self._z.get(number)
        return '' if z is None else f'{z:.2f}'

    def fill_summary(self, res):
        """The rows, sorted by Z (ties by number, D61) - by number when Z
        is hidden. Every numeric cell is `table_rows`' own string."""
        numbers = list(range(1, len(self._strings) + 1))
        if self._z is not None:
            inf = float('inf')
            numbers.sort(key=lambda n: (
                inf if self._z.get(n) is None else self._z[n], n))
        self._order = numbers
        self.table.setColumnHidden(1, self._z is None)
        self.table.setRowCount(len(numbers))
        for r, n in enumerate(numbers):
            row = self._strings[n - 1]
            cells = [f'G{n}', self._z_text(n)] + list(row[1:])
            for c, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignVCenter | (
                    Qt.AlignLeft if c in (0, len(COLUMNS) - 1)
                    else Qt.AlignRight))
                if c == 0:
                    item.setToolTip(str(row[0]))
                self.table.setItem(r, c, item)
        self._paint_rows()
        self._fit_headers()
        self._cap_height()

    def _paint_rows(self):
        """Cell colours (board 174-183) and the selected row's fill."""
        p = theme.pal()
        colours = {0: p['gauge'], 1: p['accent_soft'], 7: p['text2']}
        for r, n in enumerate(self._order):
            sel = (n == self._sel)
            bg = QBrush(QColor(p['gauge_bg'])) if sel else QBrush()
            ended = self._strings[n - 1][-1]
            for c in range(len(COLUMNS)):
                item = self.table.item(r, c)
                if item is None:
                    continue
                if c == len(COLUMNS) - 1:
                    fg = p['muted'] if ended == 'yes' else p['warn']
                else:
                    fg = colours.get(c, p['text'])
                item.setForeground(QBrush(QColor(fg)))
                item.setBackground(bg)
                f = item.font()
                f.setBold(c in (0, 2))
                item.setFont(f)

    def _fit_headers(self):
        """One-line headers when they fit the table, else two lines; the
        table scrolls sideways rather than clip what still does not fit."""
        fm = self.table.horizontalHeader().fontMetrics()
        cfm = self.table.fontMetrics()
        need = 0
        for c in range(len(COLUMNS)):
            if self.table.isColumnHidden(c):
                continue
            w = fm.horizontalAdvance(HEADERS[c])
            for r in range(self.table.rowCount()):
                item = self.table.item(r, c)
                if item is not None:
                    w = max(w, cfm.horizontalAdvance(item.text()))
            need += w + 20
        wrap = need > self.table.viewport().width() > 0
        if wrap != self._wrapped:
            self._wrapped = wrap
            self.table.setHorizontalHeaderLabels(
                list(HEADERS_WRAPPED if wrap else HEADERS))
            for i, col in enumerate(COLUMNS):
                it = self.table.horizontalHeaderItem(i)
                it.setToolTip(HEADER_HELP[col])
                if i in (0, len(COLUMNS) - 1):
                    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def headers_wrapped(self):
        return self._wrapped

    def _cap_height(self):
        """Hold the table to header + at most MAX_ROWS_SHOWN rows AND at
        most TABLE_MAX_SHARE of the panel, so a run with twenty gauges
        scrolls instead of squeezing the traces out."""
        head = self.table.horizontalHeader().sizeHint().height()
        n = self.table.rowCount()
        row = (self.table.rowHeight(0) if n
               else self.table.verticalHeader().defaultSectionSize())
        frame = 2 * self.table.frameWidth() + 2
        # a table narrower than its columns scrolls sideways, and that
        # bar takes its height from the rows (GUI-7: the Results centre
        # sits between two side columns, 412 px wide at 1100 x 720)
        hdr = self.table.horizontalHeader()
        if hdr.length() > self.table.viewport().width():
            frame += self.table.horizontalScrollBar().sizeHint().height()
        floor = head + row + frame                    # header + one row
        want = head + max(1, min(n, MAX_ROWS_SHOWN)) * row + frame
        h = self.height()
        # the share holds the whole table card: its Summary / Copy row
        # comes out of it too
        share = (int(h * TABLE_MAX_SHARE)
                 - self._table_head.sizeHint().height()) if h > 0 else want
        cap = max(floor, min(want, share))
        self.table.setMinimumHeight(min(floor, cap))
        self.table.setMaximumHeight(cap)

    def resizeEvent(self, event):
        # the cap and the header wrap depend on the panel's size, so
        # neither is a build-time decision
        super().resizeEvent(event)
        self._fit_headers()
        self._cap_height()

    # ── selection ────────────────────────────────────────────────────────
    def _current_moved(self, row, _col, _prow, _pcol):
        if self._syncing or not 0 <= row < len(self._order):
            return
        self.select(self._order[row])

    def selected(self):
        """The selected gauge's G number, or None."""
        return self._sel

    def arrival(self, number):
        """`summarize_trace`'s arrival [ms] of G`number`, NaN when it has
        none or there is no such gauge (the Field view's tick, T6)."""
        if number is None or not 1 <= number <= len(self._summary):
            return float('nan')
        return self._summary[number - 1]['arrival_ms']

    def select(self, number):
        """Select G`number`: recolour the curves, move the shading and the
        readout, and say so (`gauge_selected`)."""
        if number not in self._order:
            return
        self._sel = number
        self._apply_selection(emit=True)

    def _apply_selection(self, emit):
        p = theme.pal()
        grey = GREY[theme.mode()]
        for n, c in self.curves.items():
            on = (n == self._sel)
            c.setPen(pg.mkPen(p['gauge'] if on else grey,
                              width=SELECTED_W if on else OTHER_W))
            c.setZValue(3 if on else 2)
        self._shade()
        self._set_readout(self._sel)
        self._paint_rows()
        if self._sel in self._order:
            self._syncing = True
            try:
                self.table.setCurrentCell(self._order.index(self._sel), 0)
            finally:
                self._syncing = False
        if emit and self._sel is not None:
            self.gauge_selected.emit(self._sel)

    def _shade(self):
        """The positive phase of the selected gauge, pressure only:
        [arrival, arrival + positive duration] from summarize_trace, between
        the curve and zero. No shading without an arrival."""
        self._fill_span = None
        c = self.curves.get(self._sel)
        row = (self._summary[self._sel - 1]
               if self._sel and self._sel <= len(self._summary) else None)
        a = row['arrival_ms'] if row else float('nan')
        d = row['pos_duration_ms'] if row else float('nan')
        if (c is None or self._field != 'p' or not np.isfinite(a)
                or not np.isfinite(d)):
            self.fill.setVisible(False)
            return
        x, y = c.getData()
        b = a + d
        inside = x[(x > a) & (x < b)]
        xs = np.concatenate(([a], inside, [b]))
        ys = np.interp(xs, x, y)
        self._fill_top.setData(xs, ys)
        self._fill_zero.setData(xs, np.zeros_like(xs))
        col = QColor(theme.cur('gauge'))
        col.setAlphaF(SHADE_ALPHA)
        self.fill.setBrush(QBrush(col))
        self.fill.setVisible(True)
        self._fill_span = (float(xs[0]), float(xs[-1]))

    def fill_span(self):
        """(x0, x1) [ms] of the shaded positive phase, or None."""
        return self._fill_span if self.fill.isVisible() else None

    def _set_readout(self, number):
        """`G2 · Z 2.99`, `peak 231.4 kPa at 4.180 ms`, `pos. impulse
        112.35 kPa·ms`: the table's own strings, so the two cannot
        disagree."""
        if number is None or number > len(self._strings):
            for w in self.readout:
                w.setText('')
            return
        row = self._strings[number - 1]
        z = self._z_text(number)

        def s(text):
            return text if text else '—'
        self.readout[0].setText(f'G{number} · Z {z}' if z else f'G{number}')
        self.readout[1].setText(f'peak {s(row[1])} kPa at {s(row[3])} ms')
        self.readout[2].setText(f'pos. impulse {s(row[5])} kPa·ms')
        # the texts' widths changed: re-plan the lines
        self._readout_row._relayout()

    def readout_text(self):
        return [w.text() for w in self.readout]

    # ── reading it (tests, the harness, Copy) ────────────────────────────
    def rows(self):
        """The summary strings per gauge, in gauge order - exactly
        `gauge_summary.table_rows(summary_rows(res))`, the numbers every
        cell but Gauge and Z shows."""
        return [tuple(r) for r in self._strings]

    def order(self):
        """The G numbers, top to bottom."""
        return list(self._order)

    def visible_columns(self):
        return [c for c in range(len(COLUMNS))
                if not self.table.isColumnHidden(c)]

    def headers(self):
        """The visible column headers, on one line each."""
        return [HEADERS[c] for c in self.visible_columns()]

    def cells(self):
        """The visible cells as displayed, one list per on-screen row."""
        cols = self.visible_columns()
        return [[(self.table.item(r, c).text()
                  if self.table.item(r, c) is not None else '')
                 for c in cols] for r in range(self.table.rowCount())]

    def table_text(self):
        """What Copy table puts on the clipboard: the visible headers, then
        one line per row in on-screen order, cells joined by a tab and
        lines by a newline, no trailing newline (UX-14)."""
        lines = ['\t'.join(self.headers())]
        lines += ['\t'.join(row) for row in self.cells()]
        return '\n'.join(lines)

    def copy_table(self):
        if not self._order:
            return
        QApplication.clipboard().setText(self.table_text())

    def ylabel(self):
        """The plot's left-axis label (the OUT-4a y-labels)."""
        return self.plot.getAxis('left').labelText

    def traces(self):
        """{G number: (x, y)} as the curves hold them."""
        return {n: c.getData() for n, c in self.curves.items()}

    def pen_of(self, number):
        """(colour '#rrggbb', width) of G`number`'s curve."""
        pen = self.curves[number].opts['pen']
        return pen.color().name(), pen.widthF()

    # ── theme ────────────────────────────────────────────────────────────
    def _retheme(self, _mode=None):
        p = theme.pal()
        self.plot_w.setBackground(p['tile'])
        for name in ('bottom', 'left'):
            ax = self.plot.getAxis(name)
            ax.setPen(pg.mkPen(p['border2']))
            ax.setTextPen(pg.mkPen(p['faint']))
        self.plot.titleLabel.setAttr('color', p['text'])
        self._zero.setPen(pg.mkPen(p['entry_border'], width=1,
                                   style=Qt.DashLine))
        if self._order:
            self._apply_selection(emit=False)
