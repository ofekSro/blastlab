"""The parameter form for one dimension: the spec-driven widgets plus
the behaviour that cannot be declared.

Three imperative hooks, exactly the ones the Tk form had:
  - the solver mode hides the other solver's rows and cards (T34),
  - the AMR coefficient rows exist only while AMR is on, and the
    charge-refinement row only while it is off,
  - a 2D axisymmetric case relabels r/z and pins the burst to the axis.

`get_case()` reports EVERY bad numeric field rather than the first, and
never reads a field the active solver hides - that solver's default goes
into the case instead, so what you see is what runs and saves.
"""

import math

from ..core.bc import normalize_bc, normalize_bcs
from ..core.case import Case1D, Case2D, Case3D
from ..core.constants import ANIM_SCALE_LABELS, anim_scale_from_label
from ..core import mode as mode_mod
from . import setup_spec
from .fieldform import FieldForm


# ── parsers (ported from the Tk form) ────────────────────────────────────
def _f(var, name):
    """Parse a float field with a helpful error.

    'nan'/'inf'/'1e400' parse as floats but are not usable geometry: they
    used to reach validation and produce messages like "r_exp = inf m
    pokes through the boundary" instead of being refused."""
    try:
        val = float(var.get())
    except ValueError:
        raise ValueError(f"'{name}' is not a number: {var.get()!r}")
    if not math.isfinite(val):
        raise ValueError(f"'{name}' must be a finite number: {var.get()!r}")
    return val


def _i(var, name):
    """Parse an integer field. A fractional entry is refused rather than
    silently truncated (n_snapshots = 2.7 used to become 2)."""
    raw = var.get()
    try:
        val = float(raw)
    except ValueError:
        raise ValueError(f"'{name}' is not an integer: {raw!r}")
    if not math.isfinite(val) or val != int(val):
        raise ValueError(f"'{name}' must be a whole number: {raw!r}")
    return int(val)


def _trig(var):
    """The trigger-gauge box as a 1-based gauge number, or None when it
    is blank/zero. A non-numeric entry is treated as off here and caught
    by validate_case, which reports it with the other field errors."""
    raw = str(var.get()).strip()
    if not raw:
        return None
    try:
        n = int(float(raw))
    except ValueError:
        return None
    return n or None


class CaseForm(FieldForm):
    def __init__(self, dim, on_change=None, mode=mode_mod.DEFAULT,
                 parent=None):
        self._mode = mode_mod.normalize(mode)
        super().__init__(dim, on_change=on_change, mode=self._mode,
                         parent=parent)
        # the reactive rules, registered once the widgets exist
        if self.dim == 2:
            self.on_field('geometry', self._sync_geometry)
        if 'amr_levels' in self.v:
            self.on_field('amr_levels', self._apply_mode)
        if 'anim_scale' in self.v:
            self.on_field('anim_scale', self._apply_mode)
        self._sync_geometry()
        self._apply_mode()

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

    # ── Case conversion ──────────────────────────────────────────────────
    def get_case(self):
        """Build the Case. EVERY bad numeric field is reported, not just
        the first one: the strip used to show a single message and the
        user fixed them one reload at a time.

        Fields hidden by the solver mode are STRIPPED, not read: the case
        carries that solver's defaults for them, and a stale bad value in
        a hidden box can never block a run. The form keeps the values for
        a later switch back."""
        v = self.v
        errs, bad = [], []
        foam = self._mode == 'blastfoam'

        def _F(name, label):
            try:
                return _f(v[name], label)
            except ValueError as exc:
                errs.append(str(exc))
                bad.append(name)
                return 0.0

        def _I(name, label):
            try:
                return _i(v[name], label)
            except ValueError as exc:
                errs.append(str(exc))
                bad.append(name)
                return 0

        def _ORD():
            """The reconstruction order out of '1 (Godunov)'. A native
            knob: blastFoam uses its own schemes and validate_case says
            so, so in blastFoam mode the dataclass default goes in and
            the box is not read at all. Guarded, unlike the Tk form,
            where a mangled value raised IndexError out of get_case."""
            if foam:
                return 1
            raw = str(v['order'].get())
            try:
                return int(raw.split()[0] or 1)
            except (IndexError, ValueError):
                errs.append(f"'order' is not a reconstruction order: "
                            f"{raw!r}")
                bad.append('order')
                return 1

        def _eos():
            # likewise ignored by blastFoam (validate_case notes it)
            return v['eos'].get() if not foam else 'idealGas'

        def _done(case):
            self.mark_fields(bad)
            if errs:
                raise ValueError('\n'.join(errs))
            return case

        if self.dim == 1:
            return _done(Case1D(
                radius_m=_F('radius_m', 'radius'),
                charge_kg=_F('charge', 'charge'),
                cell_size_m=_F('cell', 'cell size'),
                eos=_eos(), cfl=_F('cfl', 'cfl'),
                order=_ORD(),
                bc_outer=v['bc_outer'].get(),
                n_snapshots=_I('n_snapshots', 'snapshots'),
                t_end=_F('t_end', 'end time'),
                gauge_radii=[g[0] for g in self.gauges.get()],
                gauge_file=v['gauge_file'].get(),
                profile_file=v['profile_out'].get() or None,
                solver=self._mode,
                material=v['material'].get() if foam else 'TNT',
                activation=v['activation'].get() if foam else 'linear',
                afterburn=v['afterburn'].get() if foam else 'none'))

        bcs = {side: v[f'bc_{side}'].get()
               for side in (('x_lo', 'x_hi', 'y_lo', 'y_hi') if self.dim == 2
                            else ('x_lo', 'x_hi', 'y_lo', 'y_hi',
                                  'z_lo', 'z_hi'))}
        amr_levels = _I('amr_levels', 'AMR levels') if foam else 0
        amr_on = foam and amr_levels > 0
        # the two range boxes are read only while the scale is manual,
        # so a stale value in a hidden box cannot block a run
        _anim_scale = anim_scale_from_label(v['anim_scale'].get())
        common = dict(
            Lx=_F('Lx', 'Lx'), Ly=_F('Ly', 'Ly'),
            cell_size_m=_F('cell', 'cell size'),
            init_mode=v['init_mode'].get(),
            charge=_F('charge', 'charge'),
            profile_file_in=v['profile_in'].get() or None,
            eos=_eos(), bcs=bcs,
            order=_ORD(),
            obstacles=self.obstacles.get(), cfl=_F('cfl', 'cfl'),
            n_snapshots=_I('n_snapshots', 'snapshots'),
            gauges=self.gauges.get(),
            gauge_file=v['gauge_file'].get(),
            t_end=_F('t_end', 'end time'),
            trigger_gauge=_trig(v['trigger_gauge']),
            trigger_action=v['trigger_action'].get(),
            trigger_file=(v['trigger_file'].get() or None
                          if self.dim < 3 else None),
            anim_file=v['anim_file'].get() or None,
            anim_mesh=bool(v['anim_mesh'].get()),
            anim_scale=_anim_scale,
            anim_clim=((_F('anim_clim_min', 'video colour min'),
                        _F('anim_clim_max', 'video colour max'))
                       if _anim_scale == 'manual' else None),
            record_frames=150 if v['record'].get() else 0,
            solver=self._mode,
            material=v['material'].get() if foam else 'TNT',
            activation=v['activation'].get() if foam else 'linear',
            afterburn=v['afterburn'].get() if foam else 'none',
            n_procs=_I('n_procs', 'MPI ranks') if foam else 0,
            det_points=(self.det_pts.get() or None) if foam else None,
            refine_zones=([(*z[:-1], int(round(z[-1])))
                           for z in self.zones.get()] if foam else []),
            charge_refine=(v['charge_refine'].get()
                           if foam and not amr_on else 'global'),
            amr_levels=amr_levels,
            amr_estimator=(v['amr_estimator'].get() if amr_on
                           else 'densityGradient'),
            amr_refine=(_F('amr_refine', 'AMR refine threshold')
                        if amr_on else 0.4),
            amr_unrefine=(_F('amr_unrefine', 'AMR unrefine threshold')
                          if amr_on else 0.2),
            amr_interval=(_I('amr_interval', 'AMR refine interval')
                          if amr_on else 2),
            amr_buffer=(_I('amr_buffer', 'AMR buffer layers')
                        if amr_on else 2),
            amr_max_cells=(_I('amr_max_cells', 'AMR max cells')
                           if amr_on else 0),
            amr_display_level=(
                None if not amr_on
                or v['amr_display_level'].get().strip() in ('', 'auto')
                else _I('amr_display_level', 'AMR display level')),
        )
        if self.dim == 2:
            return _done(Case2D(geometry=v['geometry'].get(),
                                center=(_F('cx', 'burst x'),
                                        _F('cy', 'burst y')),
                                profile_file=v['profile_out'].get() or None,
                                **common))
        slice_raw = v['slice_pos'].get().strip()
        return _done(Case3D(Lz=_F('Lz', 'Lz'),
                            center=(_F('cx', 'burst x'),
                                    _F('cy', 'burst y'),
                                    _F('cz', 'burst z')),
                            charge_resolution=(v['charge_res'].get()
                                               if not foam else 'resolve'),
                            slice_axis=v['slice_axis'].get(),
                            slice_pos=(_F('slice_pos', 'slice position')
                                       if slice_raw else None),
                            charges=((self.extra_charges.get() or None)
                                     if foam else None),
                            **common))

    def set_case(self, case):
        v = self.v
        if self.dim == 1:
            v['radius_m'].set(f'{case.radius_m:g}')
            v['charge'].set(f'{case.charge_kg:g}')
            v['material'].set(getattr(case, 'material', 'TNT'))
            v['activation'].set(getattr(case, 'activation', 'linear'))
            v['afterburn'].set(getattr(case, 'afterburn', 'none') or 'none')
            v['cell'].set(f'{case.cell_size_m:g}')
            v['eos'].set(case.eos)
            v['order'].set(_order_label(case))
            v['cfl'].set(f'{case.cfl:g}')
            v['bc_outer'].set(normalize_bc(
                getattr(case, 'bc_outer', 'terminate')))
            v['n_snapshots'].set(str(case.n_snapshots))
            v['t_end'].set(f'{getattr(case, "t_end", 0.0):g}')
            self.gauges.set([(g,) for g in case.gauge_radii])
            v['gauge_file'].set(case.gauge_file)
            v['profile_out'].set(case.profile_file or '')
            return
        if self.dim == 2:
            v['geometry'].set(case.geometry)
        v['Lx'].set(f'{case.Lx:g}')
        v['Ly'].set(f'{case.Ly:g}')
        if self.dim == 3:
            v['Lz'].set(f'{case.Lz:g}')
        v['cell'].set(f'{case.cell_size_m:g}')
        v['init_mode'].set(case.init_mode)
        v['charge'].set(f'{case.charge:g}' if case.charge is not None else '')
        v['t_end'].set(f'{getattr(case, "t_end", 0.0):g}')
        if self.dim == 3:
            v['charge_res'].set(getattr(case, 'charge_resolution', 'resolve'))
            v['slice_axis'].set(getattr(case, 'slice_axis', 'y'))
            sp = getattr(case, 'slice_pos', None)
            v['slice_pos'].set('' if sp is None else f'{sp:g}')
        v['profile_in'].set(case.profile_file_in or '')
        v['cx'].set(f'{case.center[0]:g}')
        v['cy'].set(f'{case.center[1]:g}')
        if self.dim == 3 and len(case.center) > 2:
            v['cz'].set(f'{case.center[2]:g}')
        v['material'].set(getattr(case, 'material', 'TNT'))
        v['activation'].set(getattr(case, 'activation', 'linear'))
        v['afterburn'].set(getattr(case, 'afterburn', 'none') or 'none')
        v['charge_refine'].set(getattr(case, 'charge_refine', 'global'))
        v['amr_levels'].set(str(int(getattr(case, 'amr_levels', 0) or 0)))
        v['amr_estimator'].set(
            getattr(case, 'amr_estimator', 'densityGradient')
            or 'densityGradient')
        for key, default in (('amr_refine', 0.4), ('amr_unrefine', 0.2),
                             ('amr_interval', 2), ('amr_buffer', 2),
                             ('amr_max_cells', 0)):
            v[key].set(f'{getattr(case, key, default):g}')
        dl = getattr(case, 'amr_display_level', None)
        v['amr_display_level'].set('auto' if dl is None else str(int(dl)))
        v['n_procs'].set(str(getattr(case, 'n_procs', 0)))
        v['eos'].set(case.eos)
        v['order'].set(_order_label(case))
        v['cfl'].set(f'{case.cfl:g}')
        v['n_snapshots'].set(str(case.n_snapshots))
        # a case built in code (not loaded through case_from_dict) can
        # still carry the pre-T50 spellings; the combos only offer the
        # three canonical ones
        for side, val in normalize_bcs(dict(case.bcs)).items():
            v[f'bc_{side}'].set(val)
        self.gauges.set(case.gauges)
        self.obstacles.set(case.obstacles)
        self.zones.set(getattr(case, 'refine_zones', None) or [])
        if self.dim == 3:
            self.extra_charges.set(getattr(case, 'charges', None) or [])
        self.det_pts.set(getattr(case, 'det_points', None) or [])
        v['gauge_file'].set(case.gauge_file)
        v['anim_file'].set(case.anim_file or '')
        v['anim_mesh'].set(bool(getattr(case, 'anim_mesh', False)))
        scale = anim_scale_from_label(getattr(case, 'anim_scale', 'run'))
        v['anim_scale'].set(ANIM_SCALE_LABELS[scale])
        clim = getattr(case, 'anim_clim', None)
        if clim:
            v['anim_clim_min'].set(f'{float(clim[0]):g}')
            v['anim_clim_max'].set(f'{float(clim[1]):g}')
        v['record'].set(case.record_frames > 0)
        self._set_trigger(case)
        if self.dim == 2:
            v['profile_out'].set(case.profile_file or '')

    def _set_trigger(self, case):
        """T51 trigger rows out of a case (2D/3D - 1D has no trigger card
        since T63)."""
        n = getattr(case, 'trigger_gauge', None)
        self.v['trigger_gauge'].set('' if n in (None, 0) else str(int(n)))
        self.v['trigger_action'].set(
            getattr(case, 'trigger_action', 'terminate') or 'terminate')
        if 'trigger_file' in self.v:
            self.v['trigger_file'].set(
                getattr(case, 'trigger_file', None) or '')


def _order_label(case):
    return ('2 (MUSCL)' if int(getattr(case, 'order', 1) or 1) == 2
            else '1 (Godunov)')
