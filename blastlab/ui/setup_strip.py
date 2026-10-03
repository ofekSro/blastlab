"""GUI-5b (plan §5.3, board BC_Combined lines 125-159): the Setup centre's
live-number strip - Charge · Cells · MPI ranks · Memory · Z at gauges, and
the big Run F5 button with Initialise under it.

Every number is READ from what the debounced validation already produced
(`services/validation.validate_case` -> `ValidationReport`, its
`run_plan` from `solvers/foam/env.plan_run`) or, for the charge and Z,
from the case as entered through `ui/scaled_distance.py`. Nothing is
re-derived here with a second formula. The one product the strip forms is
the memory figure, `rep.n_cells * core.constants.BYTES_PER_CELL` - the
measured per-cell RSS of blastFoam that `plan_run` sizes its cell caps
with - shown in the same GB (2^30 B) as validation's own messages.

A tile whose number is not available is hidden, never greyed (plan
§5.3): the MPI and memory tiles need a `run_plan` (blastFoam 2D/3D), the
charge needs a charge (not a profile start), Z needs `z_shown` and a
gauge, and a 0-D case has no tile at all.

`tiles(case, rep)` needs no QApplication, so the test can compare it
field by field with the report; `LiveStrip` only lays it out.
"""

import math
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from ..core.constants import BYTES_PER_CELL
from . import scaled_distance, theme
from .components import StatTile

#: the tiles, left to right (board lines 126-150)
NAMES = ('charge', 'cells', 'ranks', 'memory', 'z')
TITLES = {'charge': 'Charge', 'cells': 'Cells', 'ranks': 'MPI ranks',
          'memory': 'Memory', 'z': 'Z at gauges'}

#: bytes in the "GB" validation prints (services/validation.py ram_hint:
#: `cap_refuse * BYTES_PER_CELL / 2 ** 30`)
GB = 2 ** 30


@dataclass(frozen=True)
class Tile:
    """What one tile shows: `value` in the display face, a smaller
    `unit` after it, the `caption` line, the memory bar's fill `frac`
    (None = no bar) and a tooltip with the unabbreviated numbers."""
    value: str
    unit: str = ''
    caption: str = ''
    frac: float = None
    tip: str = ''


def fmt_count(n):
    """A cell count the way the board writes it: `368 k`, `1.11 M`."""
    n = int(n)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f'{n / 1e3:.0f} k'
    return f'{n / 1e6:.3g} M'


def fmt_length(m):
    """A cell size in mm below a metre (`6.59 mm`, `25 mm`), else m."""
    m = float(m)
    return f'{m * 1e3:.3g} mm' if m < 1.0 else f'{m:.3g} m'


def fmt_radius(r_exp):
    """The charge radius exactly as the Derived card formats it."""
    return f'{r_exp * 1e3:.1f} mm'


def _n1(v):
    """One decimal at least ('1.0'), more when the value has them."""
    v = float(v)
    s = f'{v:.1f}'
    return s if abs(float(s) - v) < 1e-9 else f'{v:g}'


def memory_bytes(rep):
    """`rep.n_cells * BYTES_PER_CELL` (the hand-off spec's product), or
    None without a cell count."""
    n = getattr(rep, 'n_cells', None)
    return None if not n else int(n) * BYTES_PER_CELL


def tiles(case, rep):
    """{name: Tile or None (hidden)} for a parsed case and its report."""
    out = dict.fromkeys(NAMES)
    dim = getattr(case, 'dim', None)
    if case is None or rep is None or dim not in (1, 2, 3):
        return out
    # ── Charge: the mass as entered, the radius validation sized ─────────
    charged = dim == 1 or getattr(case, 'init_mode', 'charge') == 'charge'
    try:
        w = scaled_distance.charge_mass(case)
    except (TypeError, ValueError):
        w = None
    if charged and w is not None and w > 0:
        planar = dim == 2 and case.geometry == 'planar'
        r_exp = getattr(rep, 'r_exp', None)
        cap = f'radius {fmt_radius(r_exp)}' if r_exp else ''
        extra = (len(getattr(case, 'charges', None) or [])
                 if getattr(case, 'solver', 'native') == 'blastfoam'
                 and dim == 3 else 0)
        if extra:
            cap += f' · +{extra} more'
        out['charge'] = Tile(_n1(w), f'kg{"/m" if planar else ""} '
                             f'{case.material}', cap.strip(' ·'),
                             tip='The design-basis charge as entered; the '
                                 'radius is the one validation sized.')
    # ── Cells: the count and cell size validation computed ───────────────
    n = getattr(rep, 'n_cells', None)
    if n:
        fine = getattr(rep, 'dx_fine', None)
        dx = getattr(rep, 'effective_dx', None)
        if fine:
            cap = f'finest {fmt_length(fine)}'
        elif dx:
            cap = f'cell {fmt_length(dx)}'
        else:
            cap = ''
        amr = int(getattr(rep, 'amr_levels', 0) or 0)
        if amr:
            cap = (cap + ' · ' if cap else '') + 'at t = 0'
        out['cells'] = Tile(fmt_count(n), '', cap,
                            tip=f'{int(n):,} cells' + (
                                f' at t = 0; AMR up to level {amr}'
                                if amr else ''))
    # ── MPI ranks and Memory: blastFoam's run plan ───────────────────────
    plan = getattr(rep, 'run_plan', None)
    if plan is not None and n:
        how = ('auto' if not plan.requested else
               f'clamped from {plan.clamped_from}' if plan.clamped else
               'requested')
        each = (f'{fmt_count(int(n) // plan.ranks)} cells each'
                if plan.ranks > 1 else 'serial')
        out['ranks'] = Tile(str(plan.ranks), '', f'{how} · {each}',
                            tip=plan.reason)
        b = memory_bytes(rep)
        gb = b / GB
        if gb >= 0.1:
            value, unit = (f'{gb:.0f}' if gb >= 10 else f'{gb:.1f}'), 'GB'
        else:
            value, unit = f'{b / 2 ** 20:.0f}', 'MB'
        ram = plan.ram_gb
        cap = (f'of {ram} GB VM' if ram else 'VM size not measured yet')
        if int(getattr(rep, 'amr_levels', 0) or 0):
            cap += ' · at t = 0'
        out['memory'] = Tile(value, unit, cap,
                             frac=(b / (ram * GB)) if ram else None,
                             tip=f'{int(n):,} cells x ~{BYTES_PER_CELL:,} B '
                                 f'per cell (blastFoam, measured; '
                                 f'core/constants.py)')
    # ── Z at gauges: the scaled distance helper ──────────────────────────
    zs = [z for _i, _r, z in scaled_distance.gauges(case) if z is not None]
    if zs and scaled_distance.z_shown(case):
        lo, hi = f'{min(zs):.2f}', f'{max(zs):.2f}'
        out['z'] = Tile(lo if lo == hi else f'{lo}–{hi}', '',
                        'm/kg^1/3',
                        tip=f'{scaled_distance.LABEL} at the gauges: '
                            'R / W^(1/3), W as entered')
    return out


# ── the widget ───────────────────────────────────────────────────────────
#: the Run column (board line 151: 148 px); it may narrow to RUN_MIN when
#: the strip wraps onto two rows
RUN_W = 148
RUN_MIN = 120
#: the tiles' inner padding (StatTile: 12 px each side)
TILE_PAD = 24
STRIP_GAP = 8


class _RunButton(QPushButton):
    """The board's Run button (line 152): a play mark, `Run` in the
    display face and a mono `F5` key cap - three labels inside one
    QPushButton, so clicks, focus and the disabled state stay the
    button's."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('runbig')
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('Run the case (F5)')
        self.setAccessibleName('Run')
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(10)
        self.mark = QLabel()
        self.text_lbl = QLabel('Run')
        self.text_lbl.setObjectName('runbigtext')
        self.key = QLabel('F5')
        self.key.setObjectName('runbigkey')
        lay.addStretch(1)
        for w in (self.mark, self.text_lbl, self.key):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            lay.addWidget(w, 0, Qt.AlignVCenter)
        lay.addStretch(1)
        self._paint_mark()
        theme.signals.changed.connect(self._paint_mark)

    def _paint_mark(self, _mode=None):
        self.mark.setPixmap(theme.pixmap(
            'play', 15, color='on_accent' if self.isEnabled() else 'muted'))

    def changeEvent(self, event):
        if event.type() == QEvent.EnabledChange:
            self._paint_mark()
        super().changeEvent(event)

    def minimumSizeHint(self):
        return QSize(RUN_MIN, 40)


class LiveStrip(QFrame):
    """The strip: five `StatTile`s and the Run column, on one row when
    the centre is wide enough (the board), else wrapped onto two rows
    with the captions moved into the tooltips - the centre is 432 px at
    the 1100 x 720 minimum window, where five tiles and Run cannot sit
    side by side."""

    run_clicked = Signal()
    init_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('setupstrip')
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(STRIP_GAP)
        self._grid.setVerticalSpacing(STRIP_GAP)
        self.tiles = {}
        self._data = dict.fromkeys(NAMES)
        for name in NAMES:
            t = StatTile(TITLES[name], variant='accent' if name == 'z'
                         else None, bar=name == 'memory')
            t.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            # the caption elides (full text in the tooltip): its whole
            # text must not set the tile's minimum width
            t.caption.setMinimumWidth(0)
            t.caption.setSizePolicy(QSizePolicy.Ignored,
                                    QSizePolicy.Preferred)
            t.caption.installEventFilter(self)
            # a 10 px caps label's space is ~2 px: 'MPI RANKS' read as one
            # word (measured on the first screenshot)
            f = t.caps.font()
            f.setWordSpacing(3)
            t.caps.setFont(f)
            t.setVisible(False)
            self.tiles[name] = t
        # Run F5 / Initialise: the last report has no errors, and no HD
        # 1.3 assessment is working (set_run_enabled, set_busy)
        self._case_ok, self._busy = True, False
        self.run_col = QWidget()
        rc = QVBoxLayout(self.run_col)
        rc.setContentsMargins(0, 0, 0, 0)
        rc.setSpacing(6)
        self.run_btn = _RunButton()
        self.run_btn.setSizePolicy(QSizePolicy.Expanding,
                                   QSizePolicy.Expanding)
        self.run_btn.clicked.connect(lambda *_: self.run_clicked.emit())
        self.init_btn = QPushButton('Initialise')
        self.init_btn.setObjectName('initbtn')
        self.init_btn.setFixedHeight(28)
        self.init_btn.setCursor(Qt.PointingHandCursor)
        self.init_btn.setToolTip('Start the run held at step 0, to see the '
                                 'initial field (the Run tab steps it on)')
        self.init_btn.clicked.connect(lambda *_: self.init_clicked.emit())
        rc.addWidget(self.run_btn, 1)
        rc.addWidget(self.init_btn)
        self._rows = None
        self._arrange(force=True)
        theme.signals.changed.connect(self._rerender)

    # ── data ─────────────────────────────────────────────────────────────
    def show_values(self, case, rep):
        """Fill the tiles from a parsed case and its report. With no case
        (the form does not parse) the last values stay, as the tree's
        summaries do."""
        if case is None:
            return
        self._data = tiles(case, rep)
        # an HD 1.3 assessment has no step 0 to hold a run at
        self.init_btn.setVisible(getattr(case, 'dim', None) != 0)
        self._rerender()
        self._arrange(force=True)

    def clear(self, dim=None):
        """No numbers (a dimension switch, before its first report)."""
        self._data = dict.fromkeys(NAMES)
        self.init_btn.setVisible(dim != 0)
        self._rerender()
        self._arrange(force=True)

    def _rerender(self, _mode=None):
        # light mode: the Z tile's caps in `accent_text` on `accent_bg`
        # measure 4.28:1, under the plan's 4.5 (§2.2); `accent_soft`
        # gives 4.65. Dark keeps the board's `accent_text` (7.72). Runs
        # after StatTile's own recolour (connected before this slot).
        if theme.mode() == 'light':
            self.tiles['z'].caps.setStyleSheet(
                f'font-size: 10px; font-weight: 600; '
                f'color: {theme.cur("accent_soft")};')
        for name, t in self.tiles.items():
            d = self._data.get(name)
            t.setVisible(d is not None)
            if d is None:
                continue
            value = d.value
            if d.unit:
                value += (f' <span style="font-size: 13px; color: '
                          f'{theme.cur("muted")};">{d.unit}</span>')
            t.set(value, frac=d.frac)
            t.caption._full = d.caption
            self._elide(t.caption)
            t.setToolTip('\n'.join(x for x in (d.caption, d.tip) if x))
            if t.bar is not None:
                t.bar.setVisible(d.frac is not None)

    def tile(self, name):
        """The Tile a tile shows, or None when it is hidden (tests)."""
        return self._data.get(name)

    def shown(self, name):
        """(value, caption) as on screen - the value label's text without
        its markup, the caption's full text - or None when hidden."""
        t = self.tiles[name]
        if t.isHidden():
            return None
        d = self._data[name]
        return (d.value + (f' {d.unit}' if d.unit else ''),
                getattr(t.caption, '_full', t.caption.text()))

    def set_run_enabled(self, ok):
        self._case_ok = bool(ok)
        self._sync_run()

    def set_busy(self, busy):
        """An HD 1.3 assessment is working: Run F5 and Initialise grey
        while it runs - a state grey, like Run during a run (GUI-11 T5,
        D206) - whatever the live checks say meanwhile."""
        self._busy = bool(busy)
        self._sync_run()

    def _sync_run(self):
        ok = self._case_ok and not self._busy
        self.run_btn.setEnabled(ok)
        self.init_btn.setEnabled(ok)

    # ── layout: one row, or wrapped ──────────────────────────────────────
    def _items(self):
        return [self.tiles[n] for n in NAMES
                if not self.tiles[n].isHidden()] + [self.run_col]

    @staticmethod
    def _min_w(w):
        if isinstance(w, StatTile):
            return max(w.caps.sizeHint().width(),
                       w.value.sizeHint().width()) + TILE_PAD
        return RUN_MIN

    def _fit_rows(self, width):
        """The fewest rows (1-3) whose columns fit `width`."""
        items = self._items()
        n = len(items)
        mins = [self._min_w(w) for w in items]
        for rows in (1, 2):
            cols = math.ceil(n / rows)
            per = [max(mins[k] for k in range(c, n, cols))
                   for c in range(cols)]
            if rows == 1:
                per[-1] = max(per[-1], RUN_W)
            if sum(per) + STRIP_GAP * (cols - 1) <= width:
                return rows
        return 3

    def rows(self):
        """How many rows the strip uses now (tests)."""
        return self._rows

    def _arrange(self, force=False):
        width = self.contentsRect().width() or 10 ** 6
        rows = self._fit_rows(width)
        if rows == self._rows and not force:
            return
        self._rows = rows
        g = self._grid
        for w in list(self.tiles.values()) + [self.run_col]:
            g.removeWidget(w)
        for c in range(g.columnCount()):
            g.setColumnStretch(c, 0)
        items = self._items()
        cols = math.ceil(len(items) / rows)
        for k, w in enumerate(items):
            g.addWidget(w, k // cols, k % cols)
        if rows == 1:
            # the board's row: tiles share the width, Z a little more
            # (flex 1.15), the Run column fixed
            for k, w in enumerate(items[:-1]):
                g.setColumnStretch(k, 23 if w is self.tiles['z'] else 20)
            self.run_col.setFixedWidth(RUN_W)
        else:
            for c in range(cols):
                g.setColumnStretch(c, 1)
            self.run_col.setMinimumWidth(RUN_MIN)
            self.run_col.setMaximumWidth(16777215)
        # wrapped: the captions go to the tooltips (the height is short)
        for t in self.tiles.values():
            t.caption.setVisible(rows == 1)
        self.updateGeometry()

    def minimumSizeHint(self):
        """Never hold the window wide: the minimum is the widest single
        item; `_arrange` wraps as the width drops."""
        hint = super().minimumSizeHint()
        widest = max(self._min_w(w) for w in self._items())
        return QSize(widest, hint.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange()
        for t in self.tiles.values():
            self._elide(t.caption)

    @staticmethod
    def _elide(cap):
        full = getattr(cap, '_full', cap.text())
        w = cap.width()
        text = (cap.fontMetrics().elidedText(full, Qt.ElideRight, w)
                if w > 0 else full)
        if text != cap.text():
            cap.setText(text)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Resize, QEvent.FontChange,
                            QEvent.StyleChange) and hasattr(obj, '_full'):
            self._elide(obj)
        return super().eventFilter(obj, event)
