"""GUI-9 T4 (plan §6 "Chain running", board Run_Chain lines 60-70): the
02 Run screen's chain strip - `CHAIN · <model>`, one pill per stage
joined by arrows, and a caption on the right.

    CHAIN · wall_A  (01 1D ✓ 9 s) → (02 2D 78 %) → (03 3D waiting)
                         Stage 2 of 3 · the 3D stage starts from …

It sits in `RunPanel.chain_slot` (D-row: the top of the Run centre, not
full width under the top bar as the board draws it). `MainWindow` drives
it from the existing run callbacks only (`on_running`, `on_run_started`,
`on_progress`, `on_result`, `on_finished`); `run_controller.py` is not
touched. Display only: no number here feeds a solver.

One row when it fits, else two (the eyebrow and the caption on the
first, the pills on the second). The choice is made on a resize only
(`arrange`), from the widest text each pill can take, so the strip's
height never changes on a stage change and the embedded 3D viewer below
it never moves mid-run (CLAUDE.md 8.7). Colours through object-name QSS
rules (D6); the arrows are painted.
"""

import re

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import chain_route, theme
from .results_list import ElidedLabel
from .run_clock import fmt_duration
from .setup_tree import _letter_space

#: the strip's padding (board line 60: 10 px top / bottom; 14 at the
#: sides inside its card, the board's 20 is the window edge)
PAD_V, PAD_H = 10, 14
#: a pill (board lines 62-68: 30 px, radius 15, 12 px side padding)
PILL_H = 30
#: the first row's height in the two-row form (eyebrow and caption)
ROW_A_H = 18
ROW_GAP = 6
#: the strip's height, one row and two rows
H_ONE = PAD_V + PILL_H + PAD_V
H_TWO = PAD_V + ROW_A_H + ROW_GAP + PILL_H + PAD_V
#: what the caption keeps in one row before the strip goes to two
CAPTION_MIN = 200
#: what a pill's value can read; the widest sets the row decision, so a
#: stage change never moves the strip between one and two rows
VALUE_SAMPLES = ('waiting', 'not run', 'stopped', 'failed', '100 %',
                 '59 min 59 s', '1 h 59 min', 'meshing', 'starting')

#: pill states (the `state` QSS property) and what the value says
STATES = ('waiting', 'running', 'done', 'stopped', 'failed', 'notrun')
_STATE_WORD = {'waiting': 'waiting', 'stopped': 'stopped',
               'failed': 'failed', 'notrun': 'not run'}


class _StripArrow(QWidget):
    """The 14 px arrow between two pills (board: an SVG path), orange
    once the stage before it is done, `faint` before."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._lit = False
        theme.signals.changed.connect(self.update)

    def set_lit(self, on):
        if bool(on) != self._lit:
            self._lit = bool(on)
            self.update()

    def lit(self):
        return self._lit

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # chain_pipeline._Arrow's rule: `accent` is 2.58:1 on the light
        # background, so the darker accent_text there (D152)
        key = (('accent' if theme.mode() == 'dark' else 'accent_text')
               if self._lit else 'faint')
        pen = QPen(theme.qcolor(key), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        y = self.height() / 2.0
        w = self.width()
        p.drawLine(QPointF(1.5, y), QPointF(w - 2, y))
        p.drawPolyline([QPointF(w - 7, y - 5), QPointF(w - 1.5, y),
                        QPointF(w - 7, y + 5)])
        p.end()


def compact_duration(text):
    """`20 min 41 s` -> `20 min` (the strip's narrow form); anything else
    unchanged (`9 s`, `1 h 02 min`, `78 %`, `waiting`)."""
    m = re.fullmatch(r'(\d+ min) \d+ s', text)
    return m.group(1) if m else text


class StagePill(QFrame):
    """`01 1D ✓ 9 s` / `02 2D 78 %` / `03 3D waiting`: the stage's
    position, its dimension and its value. Narrow (`set_fit`, the strip
    decides): level 1 drops the seconds of a minutes-long duration, level
    2 also the position; past that a long value elides. `text()` and the
    tooltip are always the whole pill."""

    def __init__(self, pos, dim, parent=None):
        super().__init__(parent)
        self.setObjectName('chainpill')
        self.setFixedHeight(PILL_H)
        self.dim = int(dim)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(8)
        self.num = QLabel(f'{int(pos):02d}')
        self.num.setObjectName('chainpillnum')
        self.name = QLabel(f'{self.dim}D')
        self.name.setObjectName('chainpillname')
        self.value = ElidedLabel('', Qt.ElideRight)
        self.value.setObjectName('chainpillval')
        # its natural width when there is room, less when not (a short
        # value never: the minimum set in _show_value)
        self.value.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        for w in (self.num, self.name, self.value):
            lay.addWidget(w, 0, Qt.AlignVCenter)
        self._state = None
        self._value = ''            # the whole value, whatever is shown
        self._fit = 0
        self.set_state('waiting')

    def set_state(self, state, value=None):
        """`state` in STATES; `value` the text after the name (a running
        stage's `78 %`, a done stage's duration), else the state's word."""
        if state not in STATES:
            raise ValueError(f'unknown pill state {state!r}')
        name = f'{self.dim}D ✓' if state == 'done' else f'{self.dim}D'
        if self.name.text() != name:
            self.name.setText(name)
        self._value = value if value is not None \
            else _STATE_WORD.get(state, '')
        if state != self._state:
            self._state = state
            for w in (self, self.num, self.name, self.value):
                w.setProperty('state', state)
                theme.repolish(w)
        self._show_value()

    def set_fit(self, level):
        """0 the whole pill, 1 a minutes-long duration without its
        seconds, 2 also without the position number."""
        level = max(0, min(2, int(level)))
        if level != self._fit:
            self._fit = level
            self.num.setVisible(level < 2)
            self._show_value()

    def _shown_value(self, level=None):
        level = self._fit if level is None else level
        return compact_duration(self._value) if level >= 1 else self._value

    def _show_value(self):
        text = self._shown_value()
        if self.value.full_text() != text:
            self.value.setText(text)
        # past level 2 a long value gives way (elided, as a narrow stage
        # card's title does, D151); a short one (`9 s`, `78 %`) never
        self.value.ensurePolished()
        fm = self.value.fontMetrics()
        self.value.setMinimumWidth(min(fm.horizontalAdvance(text) + 1,
                                       fm.horizontalAdvance('00 %') + 1))
        self.setToolTip(self.text())

    def state(self):
        return self._state

    def value_text(self):
        """The whole value (`78 %`, `20 min 41 s`, `waiting`)."""
        return self._value

    def text(self):
        """The whole pill as one line: `01 1D ✓ 9 s` (whatever is shown)."""
        return ' '.join(t for t in (self.num.text(), self.name.text(),
                                    self._value) if t)

    def natural(self, level):
        """The pill's width at fit `level`, from the font metrics (never
        from its geometry, so the strip's fit cannot oscillate)."""
        for w in (self.num, self.name, self.value):
            w.ensurePolished()
        m = self.layout().contentsMargins()
        sp = self.layout().spacing()
        parts = [self.name.fontMetrics().horizontalAdvance(self.name.text()),
                 self.value.fontMetrics().horizontalAdvance(
                     self._shown_value(level))]
        if level < 2:
            parts.append(self.num.fontMetrics().horizontalAdvance(
                self.num.text()))
        return m.left() + m.right() + sp * (len(parts) - 1) + sum(parts) + 2

    def widest(self):
        """The pill's width with its widest possible value (the row
        decision; `VALUE_SAMPLES`)."""
        for w in (self.num, self.name, self.value):
            w.ensurePolished()
        m = self.layout().contentsMargins()
        sp = self.layout().spacing()
        name_w = self.name.fontMetrics().horizontalAdvance(f'{self.dim}D ✓')
        val_w = max(self.value.fontMetrics().horizontalAdvance(s)
                    for s in VALUE_SAMPLES)
        return (m.left() + m.right() + 2 * sp + 2
                + self.num.fontMetrics().horizontalAdvance(self.num.text())
                + name_w + val_w)


class ChainStrip(QFrame):
    """The chain's stages while it runs and after it ends (plan §6).

    `set_chain(model, dims)`; `stage_started(k)`; `set_pct(k, pct)`;
    `stage_done(k, seconds, how)`; `finish(how, seconds=None)`; `texts()`
    for the tests. `k` is the 0-based stage index, as the controller's
    `on_result(k, ...)` gives it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('chainstrip')
        self._dims = []
        self._model = ''
        self._current = -1
        self._two = False
        self.pills = []
        self.arrows = []
        root = QVBoxLayout(self)
        root.setContentsMargins(PAD_H, PAD_V, PAD_H, PAD_V)
        root.setSpacing(ROW_GAP)
        self._row_a = QWidget()
        self._lay_a = QHBoxLayout(self._row_a)
        self._lay_a.setContentsMargins(0, 0, 0, 0)
        self._lay_a.setSpacing(10)
        self._row_b = QWidget()
        self._lay_b = QHBoxLayout(self._row_b)
        self._lay_b.setContentsMargins(0, 0, 0, 0)
        self._lay_b.setSpacing(8)
        self._row_b.hide()
        root.addWidget(self._row_a)
        root.addWidget(self._row_b)
        self.eyebrow = ElidedLabel('', Qt.ElideMiddle)
        self.eyebrow.setObjectName('chaineyebrow')
        self.eyebrow.setSizePolicy(QSizePolicy.Preferred,
                                   QSizePolicy.Preferred)
        _letter_space(self.eyebrow)
        self.caption = ElidedLabel('', Qt.ElideRight)
        self.caption.setObjectName('stripcaption')
        self.caption.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._place()
        self.setFixedHeight(H_ONE)

    # ── size: one row or two, decided on a resize only ───────────────────
    def sizeHint(self):
        return QSize(super().sizeHint().width(), self.height_now())

    def minimumSizeHint(self):
        return QSize(0, self.height_now())

    def height_now(self):
        """The strip's height in its current form (50 or 74 px)."""
        return H_TWO if self._two else H_ONE

    def two_rows(self):
        return self._two

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange(self.width())

    def need_one_row(self):
        """The width one row needs: the eyebrow, every pill at its widest
        value, the arrows, and CAPTION_MIN for the caption."""
        self.eyebrow.ensurePolished()
        eb = self.eyebrow.fontMetrics().horizontalAdvance(
            self.eyebrow.full_text()) + 2
        pills = sum(p.widest() for p in self.pills)
        arrows = sum(a.width() for a in self.arrows)
        n_items = 2 + len(self.pills) + len(self.arrows)
        return (2 * PAD_H + eb + pills + arrows + CAPTION_MIN
                + self._lay_a.spacing() * (n_items - 1))

    def arrange(self, width):
        """One row when `width` holds it, else two. Called on a resize,
        and by the window before the strip is shown (so it appears at
        its final height)."""
        if width <= 0:
            return
        two = width < self.need_one_row()
        if two != self._two:
            self._two = two
            self._place()
            self.setFixedHeight(self.height_now())
            self.updateGeometry()
        self._fit_pills(width)

    def _fit_pills(self, width=None):
        """In the two-row form the pills have the whole row; when they do
        not fit it at their natural width (three done pills of minutes
        each at 1100 x 720), the narrowest fit level that does (see
        StagePill.set_fit) applies to every pill. Widths only - the
        strip's height is not touched. One row is never narrowed: it is
        chosen only when the widest values fit."""
        width = self.width() if width is None else width
        if not self.pills or width <= 0:
            return
        level = 0
        if self._two:
            avail = width - 2 * PAD_H - 2
            gaps = self._lay_b.spacing() * (len(self.pills)
                                            + len(self.arrows) - 1)
            fixed = gaps + sum(a.width() for a in self.arrows)
            while level < 2 and fixed + sum(
                    p.natural(level) for p in self.pills) > avail:
                level += 1
        for p in self.pills:
            p.set_fit(level)

    def fit_level(self):
        """The pills' fit level now (tests)."""
        return self.pills[0]._fit if self.pills else 0

    def _place(self):
        """Put the widgets in the rows of the current form."""
        for lay in (self._lay_a, self._lay_b):
            while lay.count():
                lay.takeAt(0)
        self._lay_a.addWidget(self.eyebrow, 0, Qt.AlignVCenter)
        row = self._lay_b if self._two else self._lay_a
        for i, pill in enumerate(self.pills):
            if i:
                row.addWidget(self.arrows[i - 1], 0, Qt.AlignVCenter)
            row.addWidget(pill, 0, Qt.AlignVCenter)
        if self._two:
            self._lay_b.addStretch(1)
        self._lay_a.addWidget(self.caption, 1, Qt.AlignVCenter)
        self._row_a.setFixedHeight(ROW_A_H if self._two else PILL_H)
        self._row_b.setFixedHeight(PILL_H)
        self._row_b.setVisible(self._two)

    # ── the chain ────────────────────────────────────────────────────────
    def set_chain(self, model, dims):
        """A new chain of `dims` into `model`: every stage waiting."""
        for w in self.pills + self.arrows:
            w.setParent(None)
            w.deleteLater()
        self._dims = [int(d) for d in dims]
        self._model = str(model or '')
        self._current = -1
        self.pills = [StagePill(i + 1, d) for i, d in enumerate(self._dims)]
        self.arrows = [_StripArrow() for _d in self._dims[1:]]
        self.eyebrow.setText(f'CHAIN · {self._model}' if self._model
                             else 'CHAIN')
        # the model name may elide, never the word CHAIN
        self.eyebrow.setMinimumWidth(min(
            self.eyebrow.fontMetrics().horizontalAdvance(
                self.eyebrow.full_text()) + 2, 180))
        self._set_caption('')
        self._place()

    def dims(self):
        return list(self._dims)

    def stage_started(self, k, value='0 %'):
        """Stage `k` (0-based) is running, at 0 % - or, from its `stage`
        message to its first solve, `meshing` / `starting` (GUI-16
        round 2)."""
        if not 0 <= k < len(self.pills):
            return
        self._current = k
        self.pills[k].set_state('running', value)
        n = len(self._dims)
        if k < n - 1:
            nxt = self._dims[k + 1]
            self._set_caption(
                f'Stage {k + 1} of {n} · the {nxt}D stage starts from '
                f'{chain_route.handoff_name(self._dims[k], nxt)}')
        else:
            self._set_caption(f'Stage {k + 1} of {n} · the last stage')
        self._sync_arrows()

    def set_pct(self, k, pct):
        """The running stage's progress, a whole percent."""
        if 0 <= k < len(self.pills) and self.pills[k].state() == 'running':
            text = f'{int(pct)} %'
            if self.pills[k].value_text() != text:
                self.pills[k].set_state('running', text)
                self._fit_pills()

    def stage_done(self, k, seconds, how='done'):
        """Stage `k` landed its result after `seconds` of run time (held
        time excluded, D50); `how` is 'done' or 'stopped'."""
        if not 0 <= k < len(self.pills):
            return
        if how == 'done':
            self.pills[k].set_state('done', fmt_duration(seconds))
        else:
            self.pills[k].set_state('stopped' if how == 'stopped'
                                    else 'failed')
        self._sync_arrows()

    def finish(self, how, seconds=None):
        """The chain ended: `how` is MainWindow's ('done' | 'stopped' |
        'failed' | 'ended'). A stage still running takes `how`, a stage
        never started reads `not run`; the caption says how it ended.
        `seconds` is the chain's run time (default: the stage times are
        not summed here, the caption then has no duration)."""
        k = self._current
        for i, pill in enumerate(self.pills):
            if pill.state() not in ('running', 'waiting'):
                continue
            if i == k and how in ('stopped', 'failed'):
                pill.set_state(how)
            else:
                pill.set_state('notrun')
        n = len(self._dims)
        at = f'at stage {max(k, 0) + 1} of {n}'
        if how == 'done':
            self._set_caption('Chain done' + (
                f' in {fmt_duration(seconds)}' if seconds is not None
                else ''))
        elif how in ('stopped', 'failed'):
            self._set_caption(f'Chain {how} {at}')
        else:
            self._set_caption(f'Chain ended {at}')
        self._sync_arrows()

    def _sync_arrows(self):
        """After every state change: the arrows' colour, and the pills'
        fit for their new texts (widths only)."""
        for i, a in enumerate(self.arrows):
            a.set_lit(self.pills[i].state() == 'done')
        self._fit_pills()

    def _set_caption(self, text):
        self.caption.setText(text)

    # ── tests ────────────────────────────────────────────────────────────
    def texts(self):
        """[each pill's text, ..., the caption] - whole, never elided."""
        return [p.text() for p in self.pills] + [self.caption.full_text()]

    def states(self):
        return [p.state() for p in self.pills]
