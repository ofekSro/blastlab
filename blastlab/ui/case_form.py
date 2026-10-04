"""The parameter form for one dimension: the spec-driven widgets plus
the behaviour that cannot be declared.

Three imperative hooks, exactly the ones the Tk form had:
  - the solver mode hides the other solver's rows and cards (T34),
  - the AMR coefficient rows exist only while AMR is on, and the
    charge-refinement row only while it is off,
  - a 2D axisymmetric case relabels r/z and pins the burst to the axis.
OUT-2 adds the VTK card's two: the Time / Step choice greys the other
interval box, and the first tick of a family fills its default fields.

`get_case()` reports EVERY bad numeric field rather than the first, and
never reads a field the active solver hides - that solver's default goes
into the case instead, so what you see is what runs and saves. The
mapping itself (parsing, defaults, which fields each solver reads) is
`models/fields.py`, shared with no toolkit; this class only collects the
widget values, marks the bad fields and raises.
"""

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QVBoxLayout, QWidget)

from ..core.constants import anim_scale_from_label
from ..core import mode as mode_mod
from ..models import fields
from . import setup_spec, theme
from .components import ToggleSwitch
from .fieldform import FieldForm
from .setup_nodes import AXISYM_SIDES
from .setup_spec import INPUT_MIN, LABEL_WRAP
from .theme import GAP
from .widgets import label

#: the trigger switch's texts (board BC_Combined lines 359-383)
TRIGGER_SWITCH = 'End the run at a gauge'
TRIGGER_SUB = 'Stop, or hand the field on, when the wave arrives.'
TRIGGER_REMAP_NOTE = 'remap writes the field for the next stage of a Chain.'
#: the dropdown's entry while the switch is on and no gauge is chosen
TRIGGER_CHOOSE = '(choose a gauge)'
TRIGGER_NONE = '(no gauges yet - add one above)'


class _GaugeCombo(QComboBox):
    """The trigger dropdown: its entries are rebuilt from the gauge list
    each time it opens, so a gauge added a moment ago is offered."""

    def __init__(self, refresh, parent=None):
        super().__init__(parent)
        self._refresh = refresh

    def showPopup(self):
        self._refresh()
        super().showPopup()


class CaseForm(FieldForm):
    def __init__(self, dim, on_change=None, mode=mode_mod.DEFAULT,
                 parent=None, placement='columns'):
        self._mode = mode_mod.normalize(mode)
        self._trig = None            # the trigger switch widgets ('nodes')
        self._fed = False            # a Chain stage fed by the one before
        self._loaded_amr = {}        # set_case's AMR values (F16, D223)
        self.t_end_ms = None         # the `= 12.0 ms` line (D221)
        super().__init__(dim, on_change=on_change, mode=self._mode,
                         parent=parent, placement=placement)
        # the reactive rules, registered once the widgets exist. A 0-D
        # deflagration case has no solver mode and no geometry, so it has
        # none of them; the one rule it does have is that a uniform
        # ignition has nothing to spread.
        if self.dim == 0:
            self.on_field('scenario_kind', self._sync_scenario)
            self._sync_scenario()
            self.on_field('clearing', self._sync_clearing)
            self._sync_clearing()
            # HD1-16: built so its values pass through, never shown
            for title in setup_spec.HIDDEN_CARDS_0:
                self.cards[title].setVisible(False)
            return
        if self.dim == 2:
            self.on_field('geometry', self._sync_geometry)
        self._build_t_end_ms()
        if placement == 'nodes':
            # GUI-5 (plan §5.2): the Setup screen's dependent rows. Only
            # the 'nodes' forms get them - a standalone form (the Chain
            # editor, until GUI-9) keeps its rows exactly as they were,
            # which test_ui_char_case_form pins (decision D21).
            self._build_trigger_switch()
            if 'profile_in' in self.v:
                self.set_row_group('profile_in', 'prof')
                self.on_field('init_mode', self._apply_mode)
            if 'init_mode' in self.v:
                # GUI-9: a fed Chain stage hides it (set_fed)
                self.set_row_group('init_mode', 'unfed')
        if 'gauges' in self.points and 'trigger_gauge' in self.v:
            # UXR-9: a removed gauge must not re-target the trigger
            self.points['gauges'].on_remove = self._gauge_removed
        if 'amr_levels' in self.v:
            self.on_field('amr_levels', self._apply_mode)
        if 'anim_scale' in self.v:
            self.on_field('anim_scale', self._apply_mode)
        # OUT-2: the VTK card
        for fam, _caption in fields.VTK_FAMILIES[self.dim]:
            self.on_field(f'vtk_{fam}_on',
                          lambda fam=fam: self._vtk_ticked(fam))
            self.on_field(f'vtk_{fam}_mode', self._sync_vtk)
        self._sync_geometry()
        self._apply_mode()
        self._sync_vtk()

    # ── UXR-15: End time in ms, beside the box typed in s ───────────────
    def _build_t_end_ms(self):
        """End time is typed in seconds while every readout is in ms, so
        a faint `= 12.0 ms` sits under the box when it is non-zero
        (D221). The box stays the row's widget; only its cell gains the
        line, so nothing that reads `widgets['t_end']` changes."""
        self.t_end_ms = None
        w = self.widgets.get('t_end')
        if w is None or 't_end' not in self.rows:
            return
        grid, _r = self.rows['t_end']
        row, col, rows, cols = grid.getItemPosition(grid.indexOf(w))
        grid.removeWidget(w)
        cell = QWidget()
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(w)
        self.t_end_ms = label('', 'small')
        self.t_end_ms.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.t_end_ms)
        grid.addWidget(cell, row, col, rows, cols)
        self.on_field('t_end', self._sync_t_end_ms)
        self._sync_t_end_ms()

    def _sync_t_end_ms(self):
        try:
            ms = float(self.v['t_end'].get()) * 1e3
        except ValueError:
            ms = 0.0
        shown = math.isfinite(ms) and ms > 0
        self.t_end_ms.setText(
            (f'= {ms:.1f} ms' if ms >= 1 else f'= {ms:.3g} ms')
            if shown else '')
        self.t_end_ms.setVisible(shown)

    def t_end_ms_text(self):
        """The `= 12.0 ms` line, '' while hidden (tests)."""
        lbl = self.t_end_ms
        return lbl.text() if lbl is not None and not lbl.isHidden() else ''

    # ── the point lists, under the names the Tk form used ───────────────
    @property
    def gauges(self):
        return self.points['gauges']

    @property
    def obstacles(self):
        return self.points['obstacles']

    @property
    def zones(self):
        return self.points['zones']

    @property
    def det_pts(self):
        return self.points['det_pts']

    @property
    def extra_charges(self):
        return self.points['extra_charges']

    # ── solver mode ──────────────────────────────────────────────────────
    @property
    def mode(self):
        return self._mode

    def set_mode(self, mode):
        m = mode_mod.normalize(mode)
        if m == self._mode:
            return
        self._mode = m
        self._apply_mode()
        self._on_change()

    def _amr_on(self):
        return (self._mode == 'blastfoam' and 'amr_levels' in self.v
                and self.v['amr_levels'].get().strip() not in ('', '0'))

    def _apply_mode(self):
        """Show the rows and cards of the active solver and hide the
        other's; within blastFoam the AMR coefficients exist only while
        AMR is on and the charge-refinement row only while it is off
        (the two are mutually exclusive by validation). Nothing is
        disabled and no value is touched."""
        foam = self._mode == 'blastfoam'
        amr_on = self._amr_on()
        self.apply_scope(self._mode, {'amr': amr_on,
                                      'cref': foam and not amr_on,
                                      'aclim': self._anim_manual(),
                                      # GUI-5, 'nodes' forms only (the
                                      # rows join these groups there)
                                      'trig': self._trigger_on(),
                                      'trig_raw': False,
                                      'prof': (self._profile_mode()
                                               and not self._fed),
                                      'unfed': not self._fed})
        self._sync_trigger_widgets()

    # ── GUI-9: a Chain stage fed by the stage before it ─────────────────
    @property
    def fed(self):
        return self._fed

    def set_fed(self, fed):
        """A Chain stage fed by the one before it: the chain wires
        `init_mode` and `profile_file_in` at run time, so the Initialize
        from and Profile file rows are hidden (never greyed) - their
        values are kept and `get_case()` is unchanged by it. 'nodes'
        forms only; the Setup's forms are never fed (decision D-row)."""
        fed = bool(fed) and self.placement == 'nodes'
        if fed == self._fed:
            return
        self._fed = fed
        self._apply_mode()

    def _profile_mode(self):
        """True while the case starts from a saved profile - the Profile
        file row exists only then (plan §5.2)."""
        return ('init_mode' in self.v and self.v['init_mode'].get()
                in ('profile1d', 'profile2d'))

    def _anim_manual(self):
        """True while the animation's colour range is typed by hand - the
        two min/max rows exist only then."""
        return ('anim_scale' in self.v
                and anim_scale_from_label(self.v['anim_scale'].get())
                == 'manual')

    # ── GUI-5: the trigger switch (plan §5.2, board lines 359-383) ───────
    def _build_trigger_switch(self):
        """A switch *End the run at a gauge* above the Trigger-gauge
        card's rows. Off: the rows are hidden and `trigger_gauge` is
        blank. On: a *Gauge* dropdown (one entry per gauge) and the
        existing *On arrival* choice. The dropdown writes the gauge
        NUMBER into the same `trigger_gauge` Var the old box did, so the
        case values are exactly today's; the old box stays built (and
        hidden) for get_case / set_case."""
        card = self.cards.get('Trigger gauge')
        if card is None or 'trigger_gauge' not in self.v:
            return
        self.set_row_group('trigger_gauge', 'trig_raw')
        self.set_row_group('trigger_action', 'trig')
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(GAP)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = QLabel(TRIGGER_SWITCH)
        title.setObjectName('trigtitle')
        texts.addWidget(title)
        texts.addWidget(label(TRIGGER_SUB, 'small', wrap=True))
        hl.addLayout(texts, 1)
        switch = ToggleSwitch()
        switch.setAccessibleName(TRIGGER_SWITCH)
        switch.setToolTip(TRIGGER_SWITCH)
        switch.clicked.connect(lambda *_a: self._trigger_clicked())
        hl.addWidget(switch, 0, Qt.AlignVCenter)
        off = label('', 'muted', wrap=True)
        pick = QWidget()
        grid = QGridLayout(pick)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(GAP)
        grid.setColumnStretch(1, 1)
        cap = label('Gauge', 'muted', wrap=True)
        cap.setFixedWidth(LABEL_WRAP)
        combo = _GaugeCombo(self.refresh_trigger_choices)
        # an entry ('G2 · 1.20, 0.75, 0.75') must not widen the column:
        # the closed box elides, the open list shows it whole
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(8)
        combo.setMinimumWidth(INPUT_MIN)
        combo.setToolTip('The gauge whose arrival ends the run (its number '
                         'in the Gauges list)')
        combo.activated.connect(self._trigger_picked)
        grid.addWidget(cap, 0, 0)
        grid.addWidget(combo, 0, 1)
        remap = label(TRIGGER_REMAP_NOTE, 'small', wrap=True)
        remap.setVisible(self.dim == 2)
        body = card.body_layout
        body.insertWidget(0, head)
        body.insertWidget(1, off)
        body.insertWidget(2, pick)
        body.addWidget(remap)
        self._trig = dict(switch=switch, off=off, pick=pick, combo=combo,
                          remap=remap, on=False, last='', writing=False)
        self.on_field('trigger_gauge', self._trigger_var_changed)
        for name in self.v:
            if name.startswith('bc_') or name == 'geometry':
                self.on_field(name, self._sync_trigger_widgets)
        self._sync_trigger_from_var()

    def _trigger_on(self):
        return bool(self._trig and self._trig['on'])

    @property
    def trigger_switch(self):
        """The ToggleSwitch ('nodes' forms of 2D / 3D), else None."""
        return self._trig['switch'] if self._trig else None

    @property
    def trigger_combo(self):
        return self._trig['combo'] if self._trig else None

    def _set_trigger_on(self, on):
        t = self._trig
        t['on'] = bool(on)
        sw = t['switch']
        if sw.isChecked() != t['on']:
            sw.blockSignals(True)
            sw.setChecked(t['on'])
            sw.blockSignals(False)
            sw.update()

    def _trigger_write(self, text):
        t = self._trig
        t['writing'] = True
        try:
            self.v['trigger_gauge'].set(text)
        finally:
            t['writing'] = False

    def _trigger_clicked(self):
        """The user flipped the switch. On: the dropdown's gauge (the
        last one chosen, else G1) goes into `trigger_gauge`; off: the Var
        is blanked, the number remembered for the next time on."""
        t = self._trig
        on = t['switch'].isChecked()
        var = self.v['trigger_gauge']
        t['on'] = on
        if on:
            n = len(self.points['gauges'].get()) if 'gauges' in \
                self.points else 0
            want = t['last'] if _gauge_index(t['last'], n) else ''
            if not var.get().strip() and n:
                self._trigger_write(want or '1')
        else:
            if var.get().strip():
                t['last'] = var.get().strip()
            self._trigger_write('')
        self._apply_mode()
        self.refresh_trigger_choices()

    def _trigger_picked(self, index):
        data = self._trig['combo'].itemData(index)
        if data:
            self._trigger_write(str(data))
        self._paint_trigger_combo()

    def _trigger_var_changed(self):
        """The Var changed from outside the switch (set_case, a script,
        the old field's semantics): blank = off, a number = on."""
        if self._trig is None or self._trig['writing']:
            return
        self._sync_trigger_from_var()

    def _sync_trigger_from_var(self):
        if self._trig is None:
            return
        self._set_trigger_on(bool(self.v['trigger_gauge'].get().strip()))
        self._apply_mode()
        self.refresh_trigger_choices()

    def _gauge_removed(self, index):
        """UXR-9 (D219): the user removed gauge row `index` (0-based).
        The trigger follows its gauge: a row before it decrements
        `trigger_gauge`, the trigger row itself blanks it (with the switch
        on, D27's red pending state), a row after it changes nothing. A
        number that named no gauge (D17's `G5 (no such gauge)`) is left
        alone. Only an edit in the session: `set_case` never removes."""
        removed = index + 1
        n_before = self.points['gauges'].count() + 1

        def follow(text):
            k = _gauge_index(text, n_before)
            if not k or removed > k:
                return None
            return '' if removed == k else str(k - 1)

        new = follow(self.v['trigger_gauge'].get().strip())
        if new is not None:
            if self._trig is not None:
                self._trigger_write(new)    # the switch keeps its state
            else:
                self.v['trigger_gauge'].set(new)
        if self._trig is not None:
            # the number the switch restores when turned back on
            last = follow(self._trig['last'])
            if last is not None:
                self._trig['last'] = last
            self.refresh_trigger_choices()

    def _gauge_label(self, i, g):
        if self.dim == 3:
            return f'G{i} · {g[0]:.2f}, {g[1]:.2f}, {g[2]:.2f}'
        r, z = (('r', 'z') if self.v['geometry'].get() == 'axisymmetric'
                else ('x', 'y'))
        return f'G{i} · {r} {g[0]:.2f}, {z} {g[1]:.2f}'

    def refresh_trigger_choices(self):
        """Rebuild the dropdown from the gauge list and select the entry
        of the Var's number. A loaded number that names no gauge is kept
        and shown as `G5 (no such gauge)` (decision D17), so load -> save
        round trips and validation still names the error."""
        if self._trig is None:
            return
        combo = self._trig['combo']
        rows = self.points['gauges'].get()
        text = self.v['trigger_gauge'].get().strip()
        items = [(self._gauge_label(i, g), str(i))
                 for i, g in enumerate(rows, start=1)]
        pick = _gauge_index(text, len(rows))
        if pick:
            cur = pick - 1
        elif text:
            items.append((f'G{text} (no such gauge)' if _is_int(text)
                          else f'{text!r} (not a gauge number)', text))
            cur = len(items) - 1
        else:
            items.insert(0, (TRIGGER_CHOOSE if rows else TRIGGER_NONE, ''))
            cur = 0
        old = [(combo.itemText(i), combo.itemData(i))
               for i in range(combo.count())]
        combo.blockSignals(True)
        try:
            if old != items:
                combo.clear()
                for text_, data in items:
                    combo.addItem(text_, data)
            combo.setCurrentIndex(cur)
        finally:
            combo.blockSignals(False)
        self._paint_trigger_combo()

    def _sync_trigger_widgets(self):
        """Show the dropdown and the remap note with the switch; the off
        line names the side(s) that end the run instead."""
        t = self._trig
        if t is None:
            return
        on = t['on']
        t['pick'].setVisible(on)
        t['remap'].setVisible(on and self.dim == 2)
        t['off'].setVisible(not on)
        axisym = (self.dim == 2
                  and self.v['geometry'].get() == 'axisymmetric')
        sides = [AXISYM_SIDES.get(n[3:], n[3:]) if axisym else n[3:]
                 for n in self.v
                 if n.startswith('bc_')
                 and self.v[n].get() == 'terminate']
        t['off'].setText(
            f'Off: the run ends at the {" or ".join(sides)} side or at '
            f'the end time.' if sides else
            'Off: the run ends at the end time.')
        self._paint_trigger_combo()

    def trigger_pending(self):
        """True while the switch is on but no gauge is chosen: the case
        then has no trigger (`trigger_gauge` blank, decision D17), so the
        dropdown is outlined red until a gauge is picked (D27)."""
        return bool(self._trig and self._trig['on']
                    and not self.v['trigger_gauge'].get().strip())

    def _paint_trigger_combo(self):
        """The trigger dropdown is red with the `trigger_gauge` box it
        stands in for, and while the switch is on with nothing chosen."""
        if self._trig is None:
            return
        combo = self._trig['combo']
        want = ('true' if 'trigger_gauge' in self._bad
                or self.trigger_pending() else 'false')
        if combo.property('bad') != want:
            combo.setProperty('bad', want)
            theme.repolish(combo)

    def mark_fields(self, names):
        """As FieldForm.mark_fields, and the trigger dropdown with it."""
        super().mark_fields(names)
        self._paint_trigger_combo()

    # ── 2D geometry ──────────────────────────────────────────────────────
    def _sync_geometry(self):
        """2D axisymmetric relabels r/z and pins the burst to the axis;
        the x_lo boundary is the axis itself (a wall) - this is the one
        place a control stays disabled, because it is geometry, not a
        solver choice."""
        if self.dim != 2 or 'geometry' not in self.v:
            return
        axisym = self.v['geometry'].get() == 'axisymmetric'
        self.set_enabled('bc_x_lo', not axisym)
        if axisym:
            self.v['bc_x_lo'].set('reflect')
        spec = setup_spec.by_name(2)
        for key in ('Lx', 'Ly', 'cx', 'cy', 'charge'):
            if axisym:
                text = setup_spec.AXISYM_LABELS[key]
            else:
                text = setup_spec.PLANAR_LABELS.get(key, spec[key].label)
            self.set_label(key, text)
        # UXR-11 / F4: the point lists' columns and hints read r / z too
        for name, pl in self.points.items():
            cols = spec[name].cols
            pl.set_columns([setup_spec.AXISYM_COLUMNS.get(c, c)
                            for c in cols] if axisym else cols)
        # axisym: the domain is the (r, z) half-plane revolved about the
        # axis, so the burst sits on r = 0
        if axisym:
            self.v['cx'].set('0')
        self.set_enabled('cx', not axisym)

    # ── OUT-2: the VTK output card ───────────────────────────────────────
    def _sync_vtk(self):
        """Viper's greying: of each family's two interval boxes only the
        one of the chosen mode is live; the other keeps its value. The
        one place on this form where greying, not hiding, is right."""
        for fam, _caption in fields.VTK_FAMILIES.get(self.dim, ()):
            step = self.v[f'vtk_{fam}_mode'].get() == 'step'
            self.set_enabled(f'vtk_{fam}_time', not step)
            self.set_enabled(f'vtk_{fam}_steps', step)

    def _vtk_ticked(self, fam):
        """The first tick of a family fills its default quantities (plan
        sec. 3.1) when its columns are empty; unticking keeps them."""
        if not self.v[f'vtk_{fam}_on'].get():
            return
        var = self.v['vtk_fields']
        var.set(fields.vtk_fill_defaults(var.get(), fam, self.dim))

    # ── HD 1.3, dim 0 (HD1-11c) ──────────────────────────────────────────
    def _sync_scenario(self):
        """Uniform ignition lights everything at t = 0, so the spread
        rows have nothing to say. They are disabled rather than hidden:
        the point of the form is that the user SEES the entrainment
        exists and is choosing not to model it."""
        if self.dim != 0 or 'scenario_kind' not in self.v:
            return
        spread = self.v['scenario_kind'].get() != 'uniform'
        for key in ('n_cohorts', 'spread_time', 'spread_geometry'):
            self.set_enabled(key, spread)

    def _sync_clearing(self):
        """HD1-16: the wall's H and W matter only when clearing is on, so
        they are disabled (not hidden, as the spread rows) while it is
        off; their values are kept."""
        if self.dim != 0 or 'clearing' not in self.v:
            return
        on = bool(self.v['clearing'].get())
        for key in ('wall_H_m', 'wall_W_m'):
            self.set_enabled(key, on)

    # ── Case conversion (models/fields.py) ───────────────────────────────
    def field_values(self):
        """Every field's current value, point lists included, as the
        plain dict `models.fields.case_from_fields` reads."""
        values = {k: var.get() for k, var in self.v.items()}
        values.update({k: pl.get() for k, pl in self.points.items()})
        return values

    def get_case(self):
        """Build the Case. EVERY bad numeric field is reported, not just
        the first one: the strip used to show a single message and the
        user fixed them one reload at a time.

        Fields hidden by the solver mode are STRIPPED, not read: the case
        carries that solver's defaults for them, and a stale bad value in
        a hidden box can never block a run. The form keeps the values for
        a later switch back. One exception, F16: the hidden AMR values of
        a loaded case go back into it (`_keep_loaded_amr`)."""
        case, errs, bad = fields.case_from_fields(
            self.dim, self.field_values(), self._mode)
        self.mark_fields(bad)
        if errs:
            raise ValueError('\n'.join(errs))
        self._keep_loaded_amr(case)
        return case

    def _keep_loaded_amr(self, case):
        """F16 (GUI-11 e, D211, D223): with AMR off, `models.fields` writes
        `AMR_FORM_FALLBACKS` (0.4 / 0.2 ...) into the case, so a file's own
        hidden values (0.2 / 0.1) did not survive Open -> Save. In a form
        that holds a loaded case (`set_case`), each of the five values AS
        LOADED goes back into the case when it is a usable number;
        otherwise the fallback stays. Not the boxes (D223): a value typed
        into a box that is hidden now (AMR switched off again, or native
        mode) is never written (CLAUDE.md §4). A form never loaded keeps
        the fallbacks, so a fresh case is unchanged. `models/` and the
        solver defaults are untouched."""
        if not self._loaded_amr or getattr(case, 'amr_levels', 0):
            return
        for key, fallback in fields.AMR_FORM_FALLBACKS.items():
            if key not in self._loaded_amr or not hasattr(case, key):
                continue
            parse = (fields.parse_float if isinstance(fallback, float)
                     else fields.parse_int)
            try:
                setattr(case, key, parse(str(self._loaded_amr[key]), key))
            except ValueError:
                pass        # not a number in the file: the fallback stays

    def set_case(self, case):
        """Load `case` into the widgets, in the order
        `models.fields.fields_from_case` gives - the hooks each set fires
        (the axisymmetric pin, the AMR sub-group) depend on it. Point
        lists do not fire on_change; the caller revalidates."""
        for name, value in fields.fields_from_case(case, self.dim).items():
            if name in self.points:
                self.points[name].set(value)
            else:
                self.v[name].set(value)
        # F16 (D211, D223): the file's own AMR values, kept as loaded
        self._loaded_amr = {k: getattr(case, k)
                            for k in fields.AMR_FORM_FALLBACKS
                            if hasattr(case, k)}
        # GUI-5: the switch follows the loaded value even when the Var did
        # not change (a blank over a blank fires no trace)
        self._sync_trigger_from_var()


def _is_int(text):
    try:
        int(str(text).strip())
        return True
    except ValueError:
        return False


def _gauge_index(text, n):
    """The 1-based gauge `text` names when it is a whole number in
    1..n, else 0."""
    if not _is_int(text):
        return 0
    k = int(str(text).strip())
    return k if 1 <= k <= n else 0
