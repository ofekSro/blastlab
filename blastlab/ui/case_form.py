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

from ..core.constants import anim_scale_from_label
from ..core import mode as mode_mod
from ..models import fields
from . import setup_spec
from .fieldform import FieldForm


class CaseForm(FieldForm):
    def __init__(self, dim, on_change=None, mode=mode_mod.DEFAULT,
                 parent=None):
        self._mode = mode_mod.normalize(mode)
        super().__init__(dim, on_change=on_change, mode=self._mode,
                         parent=parent)
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
                                      'aclim': self._anim_manual()})

    def _anim_manual(self):
        """True while the animation's colour range is typed by hand - the
        two min/max rows exist only then."""
        return ('anim_scale' in self.v
                and anim_scale_from_label(self.v['anim_scale'].get())
                == 'manual')

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
            self.set_enabled(f'vtk_{fam}_ms', not step)
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
        a later switch back."""
        case, errs, bad = fields.case_from_fields(
            self.dim, self.field_values(), self._mode)
        self.mark_fields(bad)
        if errs:
            raise ValueError('\n'.join(errs))
        return case

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
