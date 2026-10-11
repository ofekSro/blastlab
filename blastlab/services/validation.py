"""Pre-flight validation of blast cases.

`validate_case` is the GUI's pre-flight check: it mirrors the guard rails
the solvers enforce at run start (which remain authoritative) so problems
surface while editing a form instead of at launch. The activation and
afterburn checks follow the blastFoam User Guide v6.0, sec. 5.6.1 and
5.6.2.

Moved verbatim from `core/case.py` (Phase 3 of
docs/ARCHITECTURE_REVIEW.md), so that `core/` no longer imports
`solvers.foam.backend` or `solvers.foam.env`; only the relative imports
were retargeted. The old path re-exports every name here, underscore
names included. The imports of the WSL backend, the materials table, the
refinement planner, the chain and the profile reader stay deferred
inside the functions, exactly where they were. `solvers.foam.env` and
`core.hardware` are held as module references on purpose: the tests
patch attributes on those modules.

Phase 4 split `validate_case` by concern into `_validate_common`,
`_validate_1d`, `_validate_domain_and_charge` (+ `_validate_charge`),
`_validate_profile_init`, `_validate_refinement`, `_validate_caps` and
`_validate_closing`, which append to one `ValidationReport` in the order
the single function did and share a per-call `_Ctx`. The bodies moved
unchanged; a later readability pass pulled pure helpers out of them
(`_validate_trigger`, `_validate_extra_charges`, `_validate_det_points`,
`_plan_static_zones`, `_note_charge_cells`, `_check_amr_growth`,
`_check_display_grid`, `_warn_thin_obstacle`), each called at the point
its code used to run, so messages and side effects keep their order.
"""

import math
import os

import numpy as np

from ..core.bc import BC_KINDS, normalize_bc, normalize_bcs
from ..core.constants import (ANIM_SCALES, JWL_TNT, MIN_EXP_CELLS,
                              FOAM_EXP_CELLS,
                              CELLS_2D_WARN, CELLS_2D_MAX,
                              CELLS_WARN, CELLS_REFUSE,
                              FOAM_CELLS_WARN, FOAM_CELLS_REFUSE,
                              FOAM_VM_GB_ASSUMED,
                              BYTES_PER_CELL)
from ..core import hardware as _hardware
# GUI-15 (d): the dropped-gauge tests and wording live in core, where the
# native solvers share them; imported back so every caller is unchanged
from ..core.geometry import (OUTSIDE_DOMAIN, gauge_drop_reason,  # noqa: F401
                             _in_box_closed, _in_obstacle_open)
from ..models.case import TRIGGER_ACTIONS, fmt_cells
from ..models.case import VTK_FIELDS as _VTK_FIELDS
from ..models.case import VTK_MODES as _VTK_MODES
from ..models.case import vtk_family as _vtk_family
from ..models.case import vtk_fields_for as _vtk_fields_for
from ..models.case import VTK_CELLS as _VTK_CELLS
from ..models.case import VTK_DECIMATE_MAX, VTK_DECIMATE_WARNING
from ..models.case import VTK_POST_FIELDS as _VTK_POST_FIELDS
from ..models.case import VTK_GAUGE_LOCKED as _VTK_GAUGE_LOCKED
from ..models.case import normalize_vtk_gauges as _normalize_vtk_gauges
from ..models.case import vtk_gauge_extras_for as _vtk_gauge_extras_for
from ..models.result import ValidationReport


# ── Pre-flight validation (mirror of the solvers' run-time guard rails) ─────


def _charge_radius(case, rho0=None):
    rho0 = JWL_TNT['rho0'] if rho0 is None else rho0
    if case.dim == 2 and case.geometry == 'planar':
        return np.sqrt(case.charge / (np.pi * rho0))
    return (3.0 * case.charge / (4.0 * np.pi * rho0)) ** (1.0 / 3.0)


def _unknown_material(material):
    """The refusal for a material not in the table - with the reason when
    the row was taken out on purpose (core.materials.REMOVED)."""
    from ..core.materials import REMOVED
    why = REMOVED.get(material)
    if why:
        return f"Charge material '{material}' {why}"
    return f"Unknown charge material '{material}'"


def _validate_solver(case, rep):
    """Solver-backend gating. Returns the unreacted charge density used
    to size r_exp (material-aware for blastfoam), or None on a fatal
    backend error."""
    err, note = rep.errors.append, rep.notes.append
    warn = rep.warnings.append          # P1-4: the uncalibrated afterburn
    solver = getattr(case, 'solver', 'native')
    material = getattr(case, 'material', 'TNT')
    n_procs = getattr(case, 'n_procs', 0)
    if n_procs < 0:
        err("MPI ranks must be >= 0 (0 = auto)")
    # T47/N10: reconstruction order is a native-solver knob
    _order = int(getattr(case, 'order', 1) or 1)
    if _order not in (1, 2):
        err("Reconstruction order must be 1 or 2")
    elif _order == 2:
        if solver == 'blastfoam':
            note("Reconstruction order is a native-solver setting - "
                 "blastFoam uses its own schemes (ignored)")
        else:
            note("Order 2 (MUSCL): sharper fronts at the same grid; "
                 "keep CFL at or below 0.4 (limiter falls back to "
                 "order 1 where a slope would go unphysical)")
    # the exported animation's colour range (1D has no animation)
    if hasattr(case, 'anim_scale'):
        a_scale = getattr(case, 'anim_scale', 'run') or 'run'
        if a_scale not in ANIM_SCALES:
            err(f"Unknown animation colour scale '{a_scale}' "
                f"(use {', '.join(ANIM_SCALES)})")
        elif a_scale == 'manual':
            a_clim = getattr(case, 'anim_clim', None)
            try:
                lo, hi = float(a_clim[0]), float(a_clim[1])
            except (TypeError, ValueError, IndexError):
                lo = hi = None
            if lo is None:
                err("A manual animation colour range needs a minimum "
                    "and a maximum in kPa")
            elif not (np.isfinite(lo) and np.isfinite(hi)):
                err("The animation colour range must be finite")
            elif hi <= lo:
                err(f"The animation colour maximum ({hi:g} kPa) must be "
                    f"above the minimum ({lo:g} kPa)")
        elif a_scale == 'frame':
            note("The animation rescales its colours on every frame, so "
                 "the colour bar means something different in each one "
                 "and the shock will not appear to decay")
    if solver == 'native':
        # N11/T46: the native solvers take their JWL set from the same
        # material table as blastFoam
        from ..core.materials import MATERIALS as _MATS
        if material not in _MATS:
            err(_unknown_material(material))
            return None
        if n_procs > 1:
            note("MPI ranks are ignored by the native solver")
        if getattr(case, 'charges', None) or \
                getattr(case, 'det_points', None):
            err("Multiple charges / detonation points require the "
                "blastFoam solver")
        if getattr(case, 'afterburn', 'none') not in ('none', None):
            err("The afterburn model requires the blastFoam solver")
        if getattr(case, 'amr_levels', 0):
            err("Dynamic mesh refinement (AMR) requires the blastFoam "
                "solver")
        return _MATS[material].rho0
    if solver != 'blastfoam':
        err(f"Unknown solver backend '{solver}'")
        return None
    from ..core.materials import MATERIALS
    if material not in MATERIALS:
        err(_unknown_material(material))
        return None
    from ..solvers.foam import backend as foam_backend
    if case.dim not in foam_backend.IMPLEMENTED:
        err(f"The blastFoam backend for {case.dim}D cases is not "
            f"implemented yet")
    if getattr(case, 'obstacles', None):
        note("Obstacles: cells inside each box are carved out of "
             "the mesh (rigid walls)")
    if getattr(case, 'init_mode', 'charge') != 'charge':
        # N7: the stage's state is written straight into the start time
        # dir as nonuniform internalFields, in the mesh's cell order.
        # That order is only known ahead of time on a mesh blockMesh
        # alone builds - the uniform grid, or an AMR case's base grid
        # (which is the same thing at t0; T70). refineMesh renumbers,
        # so static zones stay out.
        if case.dim == 1:
            err("blastFoam 1D stages cannot start from a profile "
                "(a 1D profile IS the 1D state - run the next stage "
                "in 2D or 3D)")
        # Applies to a chamber case for the same reason it applies to a
        # profile one: the state is written into 0/ in the mesh's cell
        # order, and refineMesh renumbers.
        if (getattr(case, 'refine_zones', None)
                or getattr(case, 'charge_refine', 'global') == 'zone'):
            err("A profile-initialised blastFoam stage cannot use "
                "refinement zones yet - the remapped state is written "
                "on the uniform base mesh")
    if getattr(case, 'init_mode', 'charge') == 'chamber':
        # HD1-3b. A chamber case carries its own state rather than
        # loading one from a file, and the two halves have to agree
        # about which room they describe.
        room = getattr(case, 'room', None) or {}
        cs = getattr(case, 'chamber_state', None) or {}
        if not room:
            err("init_mode 'chamber' needs the room geometry - pass what "
                "core.room.measure() returned, which is the ALIGNED "
                "room and not the numbers that were typed")
        if not cs:
            err("init_mode 'chamber' needs a chamber_state - see "
                "core.vent.handoff()")
        if room and not room.get('ok', True):
            for e in room.get('errors', ()):
                err(f'Room: {e}')
        if room and cs:
            v_mesh = float(room.get('volume') or 0.0)
            v_state = float(cs.get('volume') or 0.0)
            if v_mesh > 0 and v_state > 0 and \
                    abs(v_state / v_mesh - 1.0) > 0.02:
                # NOT a rounding complaint - room.align makes snapping a
                # no-op, so a gap here means the hand-off was computed
                # for a different room than the one about to be meshed,
                # and the pressure written into the cells is wrong by
                # that ratio.
                err(f"The chamber state was computed at "
                    f"{v_state:.4f} m3 but the meshed cavity is "
                    f"{v_mesh:.4f} m3 ({v_state / v_mesh - 1.0:+.1%}). "
                    f"Re-run core.vent.handoff with volume_cfd set to "
                    f"the meshed cavity - it conserves mass and energy, "
                    f"so the pressure follows, but only if it is told "
                    f"the right volume.")
            # Defaults to True when the key is absent, because
            # `simulate` is adiabatic by default: a hand-written case
            # that simply omits the field must not be the quiet way past
            # this warning. Absence of evidence is the adiabatic case.
            if cs.get('adiabatic_source', True):
                warn("The chamber state came from an ADIABATIC 0-D run. "
                     "At a burst pressure the effect of that is NOT in T "
                     "- the pressure is fixed by the trigger, so T is "
                     "nearly set by the composition. It is in WHEN the "
                     "panel bursts and HOW MUCH has burnt by then: "
                     "measured at h_c = 200 on a 20 kg magazine, the "
                     "burst comes 9.5 % later with 12.4 % more mass "
                     "burnt and alpha_expl 10.8 % higher, while T moves "
                     "1.4 %. Set h_c and wall_area on the 0-D run, or "
                     "state that this is the adiabatic bound.")
            if cs.get('first_front_is_artefact'):
                warn("Opened-from-the-start: the first front out of the "
                     "opening is an artefact of initialising a "
                     "pressurised room against ambient. No peak or "
                     "impulse may be read from it - only steady-jet "
                     "quantities after it has passed.")
        if getattr(case, 'charge', None):
            note("Charge is ignored for a chamber case: the gas is "
                 "already made, and the 0-D model is what made it")
    # A PRESCRIBED STEP HAS NO CFL GUARD, which is the whole point and
    # also the whole risk. `adjustTimeStep no` means blastFoam will take
    # this step whatever the flow does, so a case that is not quiescent
    # can sail past the stability limit without a word - the run does
    # not stop, it produces a wrong answer. Estimated here against the
    # acoustic speed of ambient air, which is a LOWER bound on the wave
    # speed in a chamber case: hot products are faster, so a step that
    # is already marginal on this estimate is worse in reality.
    _dt = float(getattr(case, 'fixed_dt', 0.0) or 0.0)
    _dx = float(getattr(case, 'cell_size_m', 0.0) or 0.0)
    if _dt > 0.0 and _dx > 0.0:
        # THE SPEED HAS TO COME FROM THE GAS IN THE CASE, not from
        # ambient air. Ambient is a LOWER bound and a lower bound is the
        # wrong end to check a stability limit against: it makes a step
        # look safe that is not. A chamber case carries its own T and
        # gamma, so use them - and the wave that matters is |u| + c, not
        # c, so the estimate is doubled for the jet the opening makes.
        cs = getattr(case, 'chamber_state', None) or {}
        if cs.get('T') and cs.get('gamma_p') and cs.get('R_p'):
            c_gas = math.sqrt(float(cs['gamma_p']) * float(cs['R_p'])
                              * float(cs['T']))
            speed = 2.0 * c_gas
            basis = (f'|u| + c in the chamber gas, ~{speed:.0f} m/s at '
                     f'{float(cs["T"]):.0f} K')
        else:
            speed = 2.0 * 340.3
            basis = ('|u| + c in ambient air, ~680 m/s - a LOWER bound, '
                     'since this case declares no gas state to read')
        co = _dt * speed / _dx
        if co > case.cfl:
            err(f"A fixed time step of {_dt:g} s implies a Courant "
                f"number of {co:.2f} on a {_dx:g} m cell, against "
                f"{basis} - past the {case.cfl:g} this case asks for. "
                f"`adjustTimeStep` is off with a fixed step, so nothing "
                f"will catch this at run time: the run will not stop, it "
                f"will produce a wrong answer.")
        else:
            warn(f"Fixed time step {_dt:g} s: the Courant limiter is OFF, "
                 f"so this run will take that step whatever the flow "
                 f"does. It sits at Co = {co:.3f} against {basis}. This "
                 f"exists for QUIESCENT verification cases, where a "
                 f"Courant-controlled step divides by a zero flux - "
                 f"anything that actually moves should leave it at 0.")
    if getattr(case, 'charge_resolution', 'resolve') == 'smear':
        note("Charge resolution 'smear' is ignored by the blastFoam "
             "backend (the grid is refined to resolve the charge)")
    if getattr(case, 'eos', 'idealGas') != 'idealGas':
        # only worth saying when someone actually picked a non-default
        # EOS (the GUI hides the row in blastFoam mode, T34)
        note("EOS setting is ignored by blastFoam (material JWL products "
             "+ ideal-gas air)")
    activation = getattr(case, 'activation', 'linear')
    if activation not in ('linear', 'none', 'programmedIgnition'):
        err(f"Unknown activation model '{activation}' "
            f"(use 'linear', 'programmedIgnition' or 'none')")
    elif activation == 'programmedIgnition':
        # N5-12, guide 5.6.1.3 (Giroux): a cell reacts at a rate set by
        # vDet and the LOCAL grid size instead of flipping whole when
        # the front line crosses it - the better near-field model.
        note("programmedIgnition (Giroux): cells burn at "
             "vDet/(1.5 dx) from their ignition time instead of "
             "switching whole (guide 5.6.1.3)")
    elif activation == 'none':
        note("Instant detonation ('none'): the whole charge reacts "
             "at t = 0")
    # N5-12: per-point delays/radii must line up with the points
    # they time. `det_points or 1`: with no explicit points the charge
    # centre is the single implicit point.
    npts = len(getattr(case, 'det_points', None) or []) or 1
    for name in ('det_delays', 'det_radii'):
        vals = getattr(case, name, None)
        if vals is None:
            continue
        if activation == 'none':
            err(f"{name} needs detonation points, and activation "
                f"'none' has none (the whole charge reacts at t = 0)")
        elif len(vals) != npts:
            err(f"{name} has {len(vals)} value(s) for {npts} "
                f"detonation point(s) - one per point")
        elif any(float(v) < 0 for v in vals):
            err(f"{name} must be >= 0")

    afterburn = getattr(case, 'afterburn', 'none') or 'none'
    if afterburn not in ('none', 'miller'):
        err(f"Unknown afterburn model '{afterburn}' "
            f"(use 'none' or 'miller')")
    elif afterburn == 'miller':
        from ..core.materials import AFTERBURN
        ab = AFTERBURN.get(material)
        if ab is None:
            err(f"No afterburn parameters for '{material}'")
        elif material == 'TNT':
            note(f"Afterburn (Miller): up to {ab.Q0/1e6:g} MJ/kg released "
                 f"as the products burn with atmospheric oxygen - "
                 f"calibrated against Kingery-Bulmash (DONE.md N3: the "
                 f"anchor reads 1.02-1.20 of KB with this model on)")
        else:
            # P1-4 (owner decision 2026-09-09): only TNT was ever
            # calibrated. Every other material's Q0 comes from its oxygen
            # balance alone - the right order of magnitude, but nothing
            # was fitted to data, and the note used to claim otherwise.
            warn(f"Afterburn for {material} is NOT calibrated: "
                 f"Q0 = {ab.Q0/1e6:g} MJ/kg is derived from the oxygen "
                 f"balance alone (only TNT is calibrated, against "
                 f"Kingery-Bulmash). The order of magnitude is right - do "
                 f"not quote these numbers without a source of your own.")
    if n_procs > 1 and case.dim == 1:
        note("1D cases always run serial (MPI ranks ignored)")
    from ..solvers.foam import env as foam_env
    st, detail = foam_env.status()
    if st == 'fail':
        err(f"blastFoam/WSL not available: {detail}")
    elif st == 'checking':
        note("Checking WSL blastFoam availability...")
    elif st == 'ok':
        note(detail)
    else:
        note("WSL blastFoam availability will be verified at run start")
    return MATERIALS[material].rho0


#: ambient sound speed the stop conditions are scaled by [m/s]
C_AMB_AIR = float(np.sqrt(1.4 * 101325.0 / 1.225))


def cap_distance(case):
    """The domain length the automatic stop time is measured across:
    the radius in 1D, the longest side otherwise. Mirrors
    `solver{1,2,3}d.py` and `foam/writer._plan_*`."""
    if getattr(case, 'dim', 0) == 1:
        return float(getattr(case, 'radius_m', 0.0) or 0.0)
    Ls = [getattr(case, n, 0.0) or 0.0 for n in ('Lx', 'Ly', 'Lz')]
    return float(max(Ls))


def safety_cap_s(case):
    """The automatic end time [s]: ten domain crossings at ambient sound
    speed. This is what "End time 0 = auto" resolves to, and what
    bounds a run with no terminate boundary and no end time."""
    return 10.0 * cap_distance(case) / C_AMB_AIR


def long_run_note(case):
    """`(t_end, cap, ratio)` when an explicit end time runs past the
    automatic one, else None.

    Until 2026-09-18 such an end time was silently DISCARDED: every stop
    condition read `cap_is_end = bool(t_end) and t_end < cap`, so typing
    a bigger number changed nothing at all. Measured on a real native 2D
    run in a 1 m domain (cap 29.4 ms): t_end = 3 ms and 10 ms both
    stopped with `end time reached`, while t_end = 40 ms stopped with
    `safety cap` at 29.4 ms.

    The owner's decision is that an explicit end time wins - the cap is
    the automatic stop for when nothing was said, not a ceiling on what
    can be said - so the number is now honoured and this reports the
    cost instead, because ten times the simulated span is roughly ten
    times the wall clock.
    """
    t_end = float(getattr(case, 't_end', 0.0) or 0.0)
    cap = safety_cap_s(case)
    if t_end <= 0.0 or cap <= 0.0 or t_end <= cap:
        return None
    return t_end, cap, t_end / cap


def _warn_long_end_time(case, warn):
    """Warning, not error: the case is runnable and the result sound, it
    simply runs for longer than the automatic stop would have."""
    info = long_run_note(case)
    if info is None:
        return
    t_end, cap, ratio = info
    warn(f"End time {t_end * 1e3:.4g} ms is {ratio:.1f}x the automatic "
         f"stop time (~{cap * 1e3:.0f} ms = 10 domain crossings at "
         f"{C_AMB_AIR:.0f} m/s). It will be honoured, so expect roughly "
         f"{ratio:.0f}x the wall clock; the wave will have left the "
         f"domain long before the end.")


#: HD1-15: disk one written time costs per cell on a blastFoam 3D run -
#: measured on HD1-3d, 130,677,089 B over 841,704 cells (14 fields)
BYTES_PER_CELL_WRITE = 155


def _validate_write_budget(case, rep, n_cells, foam, amr):
    """HD1-15: the rules of the per-case write budget. `n_cells` is
    validate_case's own cell estimate."""
    err, warn, note = rep.errors.append, rep.warnings.append, rep.notes.append
    b = getattr(case, 'write_budget', 0)
    b = 0 if b is None else b
    if isinstance(b, bool) or not isinstance(b, (int, np.integer)) or b < 0:
        err("Write budget must be a whole number of writes, 0 or more "
            "(0 = off)")
        return
    b = int(b)
    if not b:
        return
    if not foam:
        note(f"Write budget {b} is a blastFoam setting - the native solver "
             f"ignores it")
        return
    t_end = float(getattr(case, 't_end', 0.0) or 0.0)
    if t_end <= 0.0:
        err(f"A write budget needs an explicit end time: the automatic end "
            f"is a 10x safety cap (~{safety_cap_s(case) * 1e3:.0f} ms), so "
            f"t_end / {b} would space the writes for a run far longer than "
            f"the one that happens")
    if b < 2:
        err("A write budget needs at least 2 writes")
    n_snap = int(getattr(case, 'n_snapshots', 0) or 0)
    if b < 4 * n_snap:
        warn(f"Write budget {b} is below 4 x n_snapshots = {4 * n_snap}, "
             f"the writer's own rule for how many writes the {n_snap} "
             f"snapshots are picked from - they will be picked from fewer, "
             f"coarser writes")
    if case.dim == 3 and t_end > 0.0:
        # the live-slice rim sees the four in-plane sides every step
        # (N3-01); a side NORMAL to the slice is only seen in a write
        ax = getattr(case, 'slice_axis', 'y') or 'y'
        bcs = normalize_bcs(dict(case.bcs or {}))
        sides = [s for s in (f'{ax}_lo', f'{ax}_hi')
                 if bcs.get(s) == 'terminate']
        if sides:
            note(f"{' and '.join(sides)} is a terminate side normal to the "
                 f"live slice: shock arrival there is checked at written "
                 f"times only, so with the budget the stop can come up to "
                 f"t_end / {b} = {t_end / b * 1e3:.4g} ms late")
    if amr and int(getattr(case, 'n_procs', 0) or 0) != 1:
        note("A parallel AMR run is read from its per-rank copies, so the "
             "write budget keeps every one of them (no purge); it still "
             "pins the write times")
    if t_end > 0.0 and b >= 2:
        per = BYTES_PER_CELL_WRITE * n_cells
        note(f"Write budget: {b} writes, one every {t_end / b * 1e3:.4g} ms, "
             f"pinned (no adaptive interval). Expect ~{b * per / 1e9:.1f} GB "
             f"of written times on the WSL disk (~{BYTES_PER_CELL_WRITE} B "
             f"per cell per write, measured on HD1-3d), plus one "
             f"decomposed write (~{per / 1e9:.2f} GB) kept for a resume "
             f"when the run is parallel")


#: OUT-2: the name each VTK family goes by in a message
_VTK_LABELS = dict(vtk_surfaces='VTK sections/obstacles',
                   vtk_volumes='VTK volumes')


def _vtk_grid(case, ctx):
    """The grid the writer snaps a VTK plane onto (writer.plan_case takes
    `refine.plan_levels(case, rho0).fine` for every 3D case): the refined
    plan's when validation built one, else the same call here. A uniform
    grid rebuilt from `ctx.dx` is NOT it - the writer sizes the charge
    cell with `refine.effective_dx`, which lands on other layers (out-2
    verify: 0.1534 and 0.1554 m were refused as one layer that the writer
    puts on two). An AMR case shifts every layer by the same offset
    (writer.snap_plane), so equal layers here are equal layers there.
    None when the plan cannot be built (validation says why elsewhere)."""
    if ctx.plan is not None:
        return ctx.plan.fine
    from ..core.refine import plan_levels
    try:
        return plan_levels(case, ctx.rho0).fine
    except ValueError:
        return None


def _validate_vtk_cadence(label, fam, err):
    """mode and value of one VTK family. True when both are usable."""
    mode, value = fam['mode'], fam['value']
    if mode not in _VTK_MODES:
        err(f"{label}: mode '{mode}' - expected 'time' or 'step'")
        return False
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value)):
        # finite too: NaN passed `<= 0` and then broke int() below (and
        # the write-count note) with a ValueError out of validate_case
        err(f"{label}: the interval must be a number "
            f"({'s' if mode == 'time' else 'solver steps'})")
        return False
    if value <= 0:
        err(f"{label}: the interval must be > 0 "
            f"({'s' if mode == 'time' else 'solver steps'})")
        return False
    if mode == 'step' and float(value) != int(value):
        err(f"{label}: a Step interval must be a whole number of solver "
            f"steps, not {value:g}")
        return False
    return True


def _validate_vtk_fields(label, names, dim, err, col=None):
    """Every name a field the dimension has (D4), with a cell in matrix
    column `col` (VTK_CELLS; OUT-4b: obstacleID is an obstacles field
    alone)."""
    have = _vtk_fields_for(dim)
    for f in names:
        if col and f in _VTK_CELLS and col not in _VTK_CELLS[f]:
            err(f"{label}: '{f}' has no {col} cell - it is written to the "
                f"{' and '.join(_VTK_CELLS[f])} files only")
            continue
        if f in have:
            continue
        if f in _VTK_FIELDS:
            err(f"{label}: '{f}' is not written in 1D - blastFoam emits it "
                f"for 2D and 3D only")
        else:
            err(f"{label}: unknown field '{f}' (expected one of "
                f"{', '.join(have)})")


def _validate_vtk_planes(case, rep, ctx, fam):
    """3D section planes: axis, position strictly inside the domain, and
    no two planes (the live slice included) on one cell layer."""
    err = rep.errors.append
    label = _VTK_LABELS['vtk_surfaces']
    L = dict(x=case.Lx, y=case.Ly, z=case.Lz)
    planes, ok = [], True
    for row in fam['planes']:
        if not (isinstance(row, (list, tuple)) and len(row) == 2):
            err(f"{label}: plane {row!r} - expected [axis, position m]")
            ok = False
            continue
        ax, pos = row
        if ax not in ('x', 'y', 'z'):
            err(f"{label}: plane axis '{ax}' - expected x, y or z")
            ok = False
        elif isinstance(pos, bool) or not isinstance(pos, (int, float)):
            err(f"{label}: plane {ax} position {pos!r} is not a number")
            ok = False
        elif not 0.0 < pos < L[ax]:
            err(f"{label}: plane {ax} = {pos:g} m is not inside the "
                f"domain (0..{L[ax]:g} m, ends excluded)")
            ok = False
        else:
            planes.append((ax, float(pos)))
    if not ok or not fam['fields'] or ctx.dx is None or ctx.dx <= 0:
        return
    grid = _vtk_grid(case, ctx)
    if grid is None:
        return
    # the live-slice plane is always a section (plan sec. 3.1)
    s_ax = getattr(case, 'slice_axis', 'y') or 'y'
    if s_ax in ('x', 'y', 'z'):
        s_pos = getattr(case, 'slice_pos', None)
        target = (float(case.center['xyz'.index(s_ax)]) if s_pos is None
                  else float(s_pos))
        planes.insert(0, (s_ax, target, 'the live slice'))
    seen = {}
    for p in planes:
        ax, pos = p[0], p[1]
        what = p[2] if len(p) > 2 else f'{ax} = {pos:g} m'
        c = np.asarray(grid[f'{ax}_c'])
        layer = float(c[int(np.argmin(np.abs(c - pos)))])
        key = (ax, layer)
        name = (ax, f'{pos:.2f}')
        clash = seen.get(key) or seen.get(name)
        if clash:
            err(f"{label}: {clash} and {what} snap to one cell layer "
                f"({ax} = {layer:.4g} m) or share a name "
                f"(slice_{ax}_{pos:.2f}) - remove one")
        else:
            seen[key] = seen[name] = what


def _validate_vtk_decimate(label, vol, dim, err, note):
    """OUT-4c (owner Q4, 2026-09-27): the volumes' decimation k - a whole
    number 1..VTK_DECIMATE_MAX (the card's spin-box range), and > 1 only
    in 3D. k > 1 gets the owner's warning."""
    k = vol.get('decimate', 1)
    if (isinstance(k, bool) or not isinstance(k, (int, float))
            or not math.isfinite(k) or k != int(k) or k < 1):
        err(f"{label}: the decimation must be a whole number >= 1 (1 = "
            f"every cell), not {k!r}")
        return
    k = int(k)
    if k == 1:
        return
    if k > VTK_DECIMATE_MAX:
        # a loaded value above the box's range: the Qt box shows it
        # clamped, so it must be named here, never run as loaded
        err(f"{label}: the decimation must be at most {VTK_DECIMATE_MAX} "
            f"(the card's range), not {k}")
        return
    if dim != 3:
        err(f"{label}: decimation is 3D only - the {dim}D domain is written "
            f"whole (set it to 1)")
        return
    note(f"{label}: decimated - one base-cell layer in {k} is kept on each "
         f"axis (about 1/{k ** 3} of the cells); {VTK_DECIMATE_WARNING}")


def _validate_vtk_gauges(case, rep, ctx):
    """OUT-4a: the extra gauge fields (`vtk_gauges`). Each must have a
    gauge cell in VTK_CELLS, must not be one of the locked p/rho/U, and
    overpressure / impulse need a 2D/3D case (D4). True when the case
    carries any extra (a native case gets the one VTK note)."""
    err = rep.errors.append
    try:
        d = _normalize_vtk_gauges(getattr(case, 'vtk_gauges', None))
    except ValueError as exc:
        err(str(exc))
        return True
    names = (d or {}).get('fields') or []
    if not names:
        return False
    if not ctx.foam:
        rep.notes.append("VTK output is a blastFoam setting - the native "
                         "solver ignores it")
        return True
    label = 'VTK gauges'
    have = _vtk_fields_for(case.dim)
    for f in names:
        if f in _VTK_GAUGE_LOCKED:
            err(f"{label}: '{f}' is always recorded at the gauges - it is "
                f"not an extra")
        elif f not in _VTK_CELLS:
            err(f"{label}: unknown field '{f}' (expected one of "
                f"{', '.join(_vtk_gauge_extras_for(case.dim))})")
        elif 'gauges' not in _VTK_CELLS[f]:
            err(f"{label}: '{f}' has no gauge cell - it is written to the "
                f"VTK files only")
        elif f not in have:
            err(f"{label}: '{f}' is not written in 1D - blastFoam emits it "
                f"for 2D and 3D only")
    if not (getattr(case, 'gauges', None) or getattr(case, 'gauge_radii',
                                                     None)):
        rep.notes.append(f"{label}: the case has no gauges - the extra "
                         f"fields record nothing")
    return True


def _validate_vtk(case, rep, ctx):
    """OUT-2 (plan sec. 3.3): the VTK output families. Runs after the
    caps, where `rep.run_plan` holds the effective ranks. A family that
    is None or off is not looked at, so a case without them is untouched."""
    err, note = rep.errors.append, rep.notes.append
    fams = {}
    for key in ('vtk_surfaces', 'vtk_volumes'):
        try:
            fam = _vtk_family(case, key)
        except ValueError as exc:       # an unknown key inside the family
            err(str(exc))
            continue
        if fam:
            fams[key] = fam
    gauges = _validate_vtk_gauges(case, rep, ctx)
    if not fams:
        return
    if not ctx.foam:
        if not gauges:
            note("VTK output is a blastFoam setting - the native solver "
                 "ignores it")
        return
    surf, vol = fams.get('vtk_surfaces'), fams.get('vtk_volumes')
    if surf:
        label = _VTK_LABELS['vtk_surfaces']
        _validate_vtk_cadence(label, surf, err)
        _validate_vtk_fields('VTK sections', surf['fields'], case.dim, err,
                             'sections')
        _validate_vtk_fields('VTK obstacles', surf['obstacle_fields'],
                             case.dim, err, 'obstacles')
        # OUT-4b: Obstacle_ID tags the faces of a sampled obstacles file -
        # alone, blastFoam writes no file to tag
        if surf['obstacle_fields'] and all(
                f in _VTK_POST_FIELDS for f in surf['obstacle_fields']):
            err("VTK obstacles: Obstacle ID needs at least one more "
                "obstacle field (e.g. Pressure) - it tags the faces of "
                "the obstacle files")
        has_obst = bool(getattr(case, 'obstacles', None))
        if case.dim == 2:
            if surf['planes']:
                err("VTK sections: planes are 3D only - the 2D domain is "
                    "its own section (use VTK volumes)")
            if surf['fields']:
                err("VTK sections: a 2D case has no sections - choose "
                    "obstacle fields, or VTK volumes for the whole domain")
            if not has_obst:
                err("VTK obstacles: the case has no obstacles - nothing to "
                    "sample")
        else:
            _validate_vtk_planes(case, rep, ctx, surf)
            if surf['obstacle_fields'] and not has_obst:
                if surf['fields']:
                    note("VTK obstacles: the case has no obstacles - only "
                         "the sections are written")
                else:
                    err("VTK obstacles: the case has no obstacles - nothing "
                        "to sample")
        if not surf['fields'] and not surf['obstacle_fields']:
            err(f"{label}: no field selected - nothing to write")
    if vol:
        label = _VTK_LABELS['vtk_volumes']
        good = _validate_vtk_cadence(label, vol, err)
        _validate_vtk_fields(label, vol['fields'], case.dim, err, 'volumes')
        if not vol['fields']:
            err(f"{label}: no field selected - nothing to write")
        if int(getattr(case, 'write_budget', 0) or 0) > 0:
            err("VTK volumes and the write budget both pin the write "
                "interval - clear one")
        ranks = (rep.run_plan.ranks if rep.run_plan is not None
                 else int(getattr(case, 'n_procs', 0) or 0))
        if ctx.amr and ranks != 1:
            # plan sec. 3.5: a parallel AMR run keeps its writes per rank
            # (CaseSpec.decomposed), which foamToVTK cannot convert
            err("VTK volumes cannot be exported from a parallel AMR run: "
                "its writes stay per rank, because reconstructPar cannot "
                "follow a changing mesh - run it on 1 MPI rank, or export "
                "sections/obstacles only")
        per = BYTES_PER_CELL_WRITE * (rep.n_cells or 0)
        if good and vol['mode'] == 'time':
            t_end = float(getattr(case, 't_end', 0.0) or 0.0)
            upto = '' if t_end > 0 else 'up to '
            t_end = t_end if t_end > 0 else safety_cap_s(case)
            # the value is in seconds (owner decision P22)
            # (1e-9: 0.002 / 0.0001 is 20.000000000000004 in floats)
            n_w = max(1, int(math.ceil(t_end / vol['value'] - 1e-9)))
            # owner decision P14 (b): Time-mode writes use runTime, so
            # they never clip dt; each lands on the first solver step
            # past its interval (writer._controldict_time)
            note(f"VTK volumes: one write every {vol['value']:g} s, "
                 f"{upto}{n_w} writes (~{n_w * per / 1e9:.1f} GB of written "
                 f"times on the WSL disk at ~{BYTES_PER_CELL_WRITE} B per "
                 f"cell per write, before conversion). Every write is also "
                 f"ingested for the live view, so a dense cadence slows it. "
                 f"This cadence becomes the solver's write schedule, and "
                 f"each write time is the first solver step past its "
                 f"interval (the time step is never shortened to land on "
                 f"it)")
        elif good:
            # Step mode: the write count is the solver's step count / N,
            # which is not known before the run (confusion 6)
            note(f"VTK volumes: one write every {int(vol['value'])} solver "
                 f"steps, ~{per / 1e9:.2f} GB per write on the WSL disk at "
                 f"~{BYTES_PER_CELL_WRITE} B per cell per write, before "
                 f"conversion. The number of writes depends on the run's "
                 f"step count, which is not known before the run - a small "
                 f"step interval on a large case can mean thousands of "
                 f"full-field writes. Every write is also ingested for the "
                 f"live view")
        _validate_vtk_decimate(label, vol, case.dim, err, note)


#: the writer's adaptive write band tops out here (solvers/foam/writer.py
#: N_WRITES_MAX); the keep-all disk estimate's write count without a budget
_N_WRITES_MAX = 60


def _validate_keep_all(case, rep, ctx):
    """OUT-3: the "Keep all fields in WSL" box. Says nothing when it is
    not ticked, so a case without it is untouched."""
    if not getattr(case, 'keep_all_fields', False):
        return
    note = rep.notes.append
    if not ctx.foam:
        note("Keep all fields in WSL is a blastFoam setting - the native "
             "solver ignores it")
        return
    if case.dim == 1:
        note("Keep all fields in WSL: 1D keeps its written times until the "
             "scratch is released anyway (P9); the box also keeps the "
             "scratch after the run")
        return
    budget = int(getattr(case, 'write_budget', 0) or 0)
    n_w, upto = budget, ''
    if n_w <= 0:
        n_w, upto = _N_WRITES_MAX, 'up to '
        try:
            vol = _vtk_family(case, 'vtk_volumes')
        except ValueError:
            vol = None
        t_end = float(getattr(case, 't_end', 0.0) or 0.0)
        if (vol and vol.get('mode') == 'time' and t_end > 0
                and isinstance(vol.get('value'), (int, float))
                and vol['value'] > 0):
            n_w, upto = max(1, int(math.ceil(t_end / vol['value'] - 1e-9))), ''
    gb = n_w * BYTES_PER_CELL_WRITE * (rep.n_cells or 0) / 1e9
    note(f"Keep all fields in WSL: every write stays in WSL and the scratch "
         f"is kept after the run; disk estimate ~{gb:.1f} GB ({upto}{n_w} "
         f"writes at ~{BYTES_PER_CELL_WRITE} B per cell per write)")


class _Ctx:
    """What the blocks of `validate_case` share, one per call (Phase 4 of
    docs/ARCHITECTURE_REVIEW.md). `_validate_common` fills the first
    seven; `_validate_domain_and_charge` sets `dims`, `bcs` and `init`;
    `_validate_charge` updates `dx` and `refined`; `_validate_refinement`
    sets `plan`."""

    def __init__(self, rho0, foam, n_exp, cref, zones, amr, dx):
        self.rho0, self.foam, self.n_exp = rho0, foam, n_exp
        self.cref, self.zones, self.amr = cref, zones, amr
        self.dx = dx
        self.dims = None
        self.bcs = None
        self.init = None
        self.refined = False
        self.plan = None


def _validate_common(case, rep):
    """Every case: the cell size, the solver backend (`_validate_solver`)
    and the trigger gauge (T51). Returns the shared `_Ctx`, or None when
    validation stops here - a bad cell size, or a fatal backend error,
    which ends validation before any geometry check."""
    dx = case.cell_size_m
    if dx <= 0:
        rep.errors.append("Cell size must be > 0")
        return None

    rho0 = _validate_solver(case, rep)
    if rho0 is None:
        return None
    foam = getattr(case, 'solver', 'native') == 'blastfoam'
    # blastFoam wants more cells across the charge than the native
    # solvers: sphericalMassToCell deposits only the staircase mass
    # (N5/T39). Native stays byte-pinned at MIN_EXP_CELLS.
    n_exp = FOAM_EXP_CELLS if foam else MIN_EXP_CELLS
    cref = getattr(case, 'charge_refine', 'global')
    zones = list(getattr(case, 'refine_zones', None) or [])
    amr = int(getattr(case, 'amr_levels', 0) or 0) if foam else 0

    _validate_trigger(case, rep)
    return _Ctx(rho0, foam, n_exp, cref, zones, amr, dx)


def _validate_trigger(case, rep):
    """Trigger gauge (T51), 2D/3D only: the gauge number, the action, and
    what a remap action needs (an axisymmetric 2D case and a filename)."""
    err, note = rep.errors.append, rep.notes.append
    trig = getattr(case, 'trigger_gauge', None)
    action = getattr(case, 'trigger_action', 'terminate') or 'terminate'
    if case.dim < 2 or trig in (None, 0, ''):
        return
    n_g = len(case.gauges)
    try:
        trig_i = int(trig)
    except (TypeError, ValueError):
        trig_i = 0
        err("Trigger gauge must be a gauge number")
    if trig_i and not 1 <= trig_i <= n_g:
        err(f"Trigger gauge {trig_i}: the case has {n_g} gauge(s)")
    if action not in TRIGGER_ACTIONS:
        err(f"Trigger action '{action}': expected one of "
            f"{', '.join(TRIGGER_ACTIONS)}")
    elif 'remap' in action:
        if case.dim == 3:
            err("Trigger action 'remap' is not available in 3D - "
                "there is no 3D remap format; use 'terminate'")
        elif case.dim == 2 and case.geometry != 'axisymmetric':
            err("Trigger action 'remap' needs an axisymmetric 2D "
                "case (only those can be remapped into 3D)")
        elif not (getattr(case, 'trigger_file', None)
                  or case.profile_file):
            err("Trigger action 'remap' needs a remap filename "
                "(trigger file, or the case's profile output)")
        else:
            if 'terminate' in action:
                then = ""
            else:
                then = " (the run then continues)"
            note(f"Gauge {trig_i} will write the remap file when the "
                 f"wave reaches it{then}")
    else:
        note(f"The run ends when the wave reaches gauge {trig_i}")


def _validate_1d(case, rep, ctx):
    """1D spherical: the outer boundary, the end time, charge and radius,
    the cell size the charge forces and the cell count. No later block
    runs for a 1D case."""
    err, warn, note = rep.errors.append, rep.warnings.append, rep.notes.append
    rho0, n_exp, dx = ctx.rho0, ctx.n_exp, ctx.dx
    kind = normalize_bc(getattr(case, 'bc_outer', 'terminate'))
    if kind not in BC_KINDS:
        err(f"Outer boundary: unknown kind '{kind}' "
            f"(expected one of {', '.join(BC_KINDS)})")
    elif kind != 'terminate' and not getattr(case, 't_end', 0.0):
        c_air = float(np.sqrt(1.4 * 101325.0 / 1.225))
        warn(f"The outer boundary is '{kind}' and no end time is "
             f"set: the run is bounded only by the safety cap "
             f"(~{10.0 * case.radius_m / c_air * 1e3:.0f} ms).")
    _warn_long_end_time(case, warn)
    if case.charge_kg <= 0:
        err("Charge must be > 0")
    if case.radius_m <= 0:
        err("Domain radius must be > 0")
    if rep.errors:
        return
    r_exp = (3.0 * case.charge_kg
             / (4.0 * np.pi * rho0)) ** (1.0 / 3.0)
    rep.r_exp = r_exp
    if r_exp >= case.radius_m:
        err(f"Explosive radius {r_exp:.3f} m exceeds domain radius")
    if dx > r_exp / n_exp:
        dx = r_exp / n_exp
        note(f"Cell size will be refined to {dx:.5f} m "
             f"({n_exp} cells inside the charge)")
    rep.effective_dx = dx
    rep.n_cells = int(case.radius_m / dx)


def _validate_domain_and_charge(case, rep, ctx):
    """2D/3D: domain extents, end time, boundary kinds (T50) and the live
    slice, then - for a charge-initialised case - the charge itself
    (`_validate_charge`). False when validation stops here."""
    err, warn = rep.errors.append, rep.warnings.append

    # 2D / 3D shared pieces
    dims = ((case.Lx, case.Ly) if case.dim == 2
            else (case.Lx, case.Ly, case.Lz))
    if any(L <= 0 for L in dims):
        err("Domain extents must be > 0")
        return False
    if getattr(case, 't_end', 0.0) < 0:
        err("End time must be >= 0 (0 = automatic stop condition)")
    # ── Boundary kinds (T50) ───────────────────────────────────────────
    bcs = normalize_bcs(dict(case.bcs or {}))
    for side, kind in sorted(bcs.items()):
        if kind not in BC_KINDS:
            err(f"Boundary {side}: unknown kind '{kind}' "
                f"(expected one of {', '.join(BC_KINDS)})")
    ends_itself = any(k == 'terminate' for k in bcs.values())
    if not ends_itself and not getattr(case, 't_end', 0.0):
        c_air = float(np.sqrt(1.4 * 101325.0 / 1.225))
        cap_ms = 10.0 * max(dims) / c_air * 1e3
        warn(f"No terminate boundary and no end time: the run is bounded "
             f"only by the safety cap (~{cap_ms:.0f} ms). Set a side to "
             f"'terminate' to stop when the wave reaches it.")
    _warn_long_end_time(case, warn)
    if case.dim == 3:
        s_ax = getattr(case, 'slice_axis', 'y')
        if s_ax not in ('x', 'y', 'z'):
            err("Live slice normal must be 'x', 'y' or 'z'")
        else:
            s_pos = getattr(case, 'slice_pos', None)
            L_ax = dict(x=case.Lx, y=case.Ly, z=case.Lz)[s_ax]
            if s_pos is not None and not 0 <= s_pos <= L_ax:
                warn(f"Live slice position {s_pos:g} m is outside the "
                     f"domain (0..{L_ax:g} m) - the nearest cell is used")
    ctx.dims, ctx.bcs = dims, bcs

    init = getattr(case, 'init_mode', 'charge')
    ctx.init = init
    if init == 'charge':
        return _validate_charge(case, rep, ctx)
    return True


def _validate_charge(case, rep, ctx):
    """A charge-initialised 2D/3D case: charge mass and resolution,
    containment against the boundaries, obstacle overlap, the cell size
    the charge forces, extra charges and detonation points. Updates
    `ctx.dx` and `ctx.refined`; False when validation stops here."""
    err, note = rep.errors.append, rep.notes.append
    rho0, foam, n_exp = ctx.rho0, ctx.foam, ctx.n_exp
    cref, amr, bcs = ctx.cref, ctx.amr, ctx.bcs
    dx, refined = ctx.dx, ctx.refined
    if case.charge is None or case.charge <= 0:
        err("Charge must be > 0")
        return False
    if getattr(case, 'charge_resolution', 'resolve') \
            not in ('resolve', 'smear'):
        err("Charge resolution must be 'resolve' or 'smear'")
        return False
    r_exp = _charge_radius(case, rho0)
    rep.r_exp = r_exp
    # 3D 'smear' keeps dx and enlarges the source ball instead of
    # refining; use the ball radius for the geometry checks below.
    # (blastfoam always resolves - smear is native-only.)
    smeared = (case.dim == 3 and not foam
               and getattr(case, 'charge_resolution',
                           'resolve') == 'smear'
               and dx > r_exp / MIN_EXP_CELLS)
    if smeared:
        r_exp = max(r_exp, 2.0 * dx)
    center = case.center
    # containment vs open boundaries; walls allow surface bursts
    if case.dim == 2:
        x0 = 0.0 if case.geometry == 'axisymmetric' else center[0]
        y0 = center[1]
        # UX-04: this pin used to be silent - a case file carrying
        # x != 0 was quietly recentred without a word
        if case.geometry == 'axisymmetric' and center[0]:
            note(f"Axisymmetric: the charge sits on the axis - "
                 f"burst x = {center[0]:g} is ignored (r = 0)")
        overhangs = [(r_exp - (case.Lx - x0), 'x_hi'),
                     (r_exp - y0, 'y_lo'),
                     (r_exp - (case.Ly - y0), 'y_hi')]
        if case.geometry == 'planar':
            overhangs.append((r_exp - x0, 'x_lo'))
        inside = 0 <= x0 <= case.Lx and 0 <= y0 <= case.Ly
    else:
        x0, y0, z0 = center
        overhangs = [(r_exp - x0, 'x_lo'), (r_exp - (case.Lx - x0), 'x_hi'),
                     (r_exp - y0, 'y_lo'), (r_exp - (case.Ly - y0), 'y_hi'),
                     (r_exp - z0, 'z_lo'), (r_exp - (case.Lz - z0), 'z_hi')]
        inside = (0 <= x0 <= case.Lx and 0 <= y0 <= case.Ly
                  and 0 <= z0 <= case.Lz)
    if not inside:
        err("Charge centre is outside the domain")
    for over, side in overhangs:
        if over <= 0:
            continue
        if bcs.get(side) == 'reflect':
            note(f"Charge is truncated by the {side} wall (surface burst)")
        else:
            err(f"Charge (r_exp = {r_exp:.4f} m) pokes through the "
                f"open '{side}' boundary")
    # obstacle overlap
    for box in case.obstacles:
        if case.dim == 2:
            ox0, ox1, oy0, oy1 = box
            cx = min(max(x0, ox0), ox1)
            cy = min(max(y0, oy0), oy1)
            d2 = (cx - x0)**2 + (cy - y0)**2
        else:
            ox0, ox1, oy0, oy1, oz0, oz1 = box
            cx = min(max(x0, ox0), ox1)
            cy = min(max(y0, oy0), oy1)
            cz = min(max(z0, oz0), oz1)
            d2 = (cx - x0)**2 + (cy - y0)**2 + (cz - z0)**2
        if d2 < r_exp**2:
            err(f"Charge overlaps obstacle {box}")
    if smeared:
        note(f"Charge under-resolved at dx = {dx:g} m - its mass & "
             f"energy will be smeared into a {r_exp:.3f} m source ball")
    elif dx > r_exp / n_exp and not (foam and cref == 'zone') \
            and not amr:
        dx = r_exp / n_exp
        refined = True
        note(f"Cell size will be refined to {dx:.5f} m "
             f"({n_exp} cells across the charge radius)")

    # blastFoam extra charges (3D only) + detonation points
    extras = getattr(case, 'charges', None) or []
    if extras and case.dim != 3:
        err("Additional charges are only supported for 3D "
            "blastFoam cases")
        extras = []
    # every charge as (x, y, z, r); the main one first, z = 0 in 2D
    spheres = [(x0, y0, (z0 if case.dim == 3 else 0.0), r_exp)]
    dx, refined = _validate_extra_charges(case, rep, ctx, extras, spheres,
                                          dx, refined)
    _validate_det_points(case, rep, spheres)
    ctx.dx, ctx.refined = dx, refined
    return True


def _validate_extra_charges(case, rep, ctx, extras, spheres, dx, refined):
    """The additional blastFoam charges (3D): shape, mass, containment,
    overlap with the charges before them, and the cell size each forces.
    Appends each checked charge to `spheres`; returns `(dx, refined)`."""
    err, note = rep.errors.append, rep.notes.append
    rho0, n_exp, amr, bcs = ctx.rho0, ctx.n_exp, ctx.amr, ctx.bcs
    for ch in extras:
        if len(ch) != 4:
            err(f"Extra charge {tuple(ch)}: need (x, y, z, mass)")
            continue
        ex, ey, ez, mass = ch
        if mass is None or mass <= 0:
            err(f"Extra charge at ({ex:g}, {ey:g}, {ez:g}): "
                f"mass must be > 0")
            continue
        r_i = (3.0 * mass / (4.0 * np.pi * rho0)) ** (1.0 / 3.0)
        if not (0 <= ex <= case.Lx and 0 <= ey <= case.Ly
                and 0 <= ez <= case.Lz):
            err(f"Extra charge centre ({ex:g}, {ey:g}, {ez:g}) is "
                f"outside the domain")
            continue
        for over, side in ((r_i - ex, 'x_lo'),
                           (r_i - (case.Lx - ex), 'x_hi'),
                           (r_i - ey, 'y_lo'),
                           (r_i - (case.Ly - ey), 'y_hi'),
                           (r_i - ez, 'z_lo'),
                           (r_i - (case.Lz - ez), 'z_hi')):
            if over <= 0:
                continue
            if bcs.get(side) == 'reflect':
                note(f"Extra charge at ({ex:g}, {ey:g}, {ez:g}) is "
                     f"truncated by the {side} wall")
            else:
                err(f"Extra charge (r_exp = {r_i:.4f} m) at "
                    f"({ex:g}, {ey:g}, {ez:g}) pokes through the "
                    f"open '{side}' boundary")
        for (px, py, pz, pr) in spheres:
            d = np.sqrt((ex - px) ** 2 + (ey - py) ** 2
                        + (ez - pz) ** 2)
            if d < r_i + pr:
                err(f"Extra charge at ({ex:g}, {ey:g}, {ez:g}) "
                    f"overlaps another charge")
        spheres.append((ex, ey, ez, r_i))
        if dx > r_i / n_exp and not amr:
            dx = r_i / n_exp
            refined = True
            note(f"Cell size will be refined to {dx:.5f} m "
                 f"({n_exp} cells across the smallest "
                 f"charge radius)")
    return dx, refined


def _validate_det_points(case, rep, spheres):
    """Every detonation point must lie inside one of the charges in
    `spheres`. In 2D a point is (x, y), and on the axisymmetric axis its
    x is pinned to 0 as the charge's is."""
    err = rep.errors.append
    for dp in getattr(case, 'det_points', None) or []:
        pt = tuple(dp) + ((0.0,) if case.dim == 2 else ())
        if len(pt) != 3:
            if case.dim == 2:
                need = "(x, y)"
            else:
                need = "(x, y, z)"
            err(f"Detonation point {tuple(dp)}: need " + need)
            continue
        px, py, pz = pt
        if case.dim == 2:
            if case.geometry == 'axisymmetric':
                px = 0.0
            pz = 0.0
            inside = any(np.sqrt((px - sx) ** 2 + (py - sy) ** 2)
                         <= sr for sx, sy, _sz, sr in spheres)
        else:
            inside = any(np.sqrt((px - sx) ** 2 + (py - sy) ** 2
                                 + (pz - sz) ** 2) <= sr
                         for sx, sy, sz, sr in spheres)
        if not inside:
            err(f"Detonation point {tuple(dp)} lies outside every "
                f"charge")


def _validate_profile_init(case, rep, ctx, pending_inputs):
    """The starts that are not a charge: a chamber case (HD1-3b) has
    nothing to check here; a profile-initialised stage needs its input
    file (or `pending_inputs`), a solver stamp that fits (N5-4) and a
    centre inside the domain."""
    err, note = rep.errors.append, rep.notes.append
    foam, dims, init = ctx.foam, ctx.dims, ctx.init
    if init == 'chamber':
        # HD1-3b: nothing to load and nothing to resolve. The gas is
        # already made and the room is a set of obstacle boxes, so the
        # charge-sphere geometry checks above have nothing to say and
        # the profile-file checks below are about a file that does not
        # exist for this mode. Its own checks ran earlier, next to the
        # other blastFoam-specific ones.
        rep.r_exp = 0.0
        return
    if init == 'charge':
        return
    if not case.profile_file_in:
        err("A profile file is required for remap initialization")
    elif not (pending_inputs or os.path.exists(case.profile_file_in)):
        err(f"Profile file not found: {case.profile_file_in}")
    elif foam and not pending_inputs:
        # N5-4: the single-case path, where the user points at a
        # profile that already exists. The CHAIN path never reaches
        # here - its input is written by the stage before it and
        # provably does not exist yet (pending_inputs), which is why
        # chain.handoff_conflicts compares the two solvers directly
        # instead. Guarded this hard because validate_case runs on
        # every keystroke behind a 300 ms debounce: profile_source
        # is a memoised header-only read, one os.stat unless the
        # file actually changed.
        # deferred: services.chain imports this module
        from . import chain as _chain
        from ..core import profiles as _profiles
        src = _profiles.profile_source(case.profile_file_in)
        if src == 'native':
            err(_chain.HANDOFF_MSG[0].upper() + _chain.HANDOFF_MSG[1:])
        elif src == 'unknown':
            note("This profile carries no solver stamp (it predates "
                 "blastlab recording one). If it came from the "
                 "native solver the hand-off over-prices the "
                 "product cells by ~33 % - re-run the stage that "
                 "produced it to get a stamped profile.")
    if case.dim == 2 and init == 'profile1d' \
            and case.geometry != 'axisymmetric':
        err("1D profile remap is only valid in axisymmetric mode")
    # the remapped charge is still placed at `center`, so an out-of-
    # domain centre is just as invalid as for a fresh charge (a chain
    # stage fed a bad burst point used to reach the backend and die)
    if case.dim == 2 and case.geometry == 'axisymmetric':
        cc = (0.0, case.center[1])
    else:
        cc = tuple(case.center)[:case.dim]
    if any(not (0 <= float(v) <= float(L)) for v, L in zip(cc, dims)):
        err("Charge centre is outside the domain")


def _validate_refinement(case, rep, ctx):
    """blastFoam mesh refinement - dynamic AMR (`plan_levels` +
    `validate_amr`) or static zones (`plan_levels` + `validate_zones`) -
    then the charge cells blastFoam will actually deposit at the finest
    spacing the charge sees. Sets `ctx.plan`; False when no AMR plan can
    be made, which ends validation."""
    err, note = rep.errors.append, rep.notes.append
    rho0, foam, n_exp = ctx.rho0, ctx.foam, ctx.n_exp
    cref, zones, amr = ctx.cref, ctx.zones, ctx.amr
    init, dims, dx = ctx.init, ctx.dims, ctx.dx

    # blastFoam local refinement: zones and/or an automatic charge zone
    plan = None
    if amr and (zones or cref == 'zone'):
        err("Dynamic AMR and static refinement zones are mutually "
            "exclusive - clear the zones and set charge refinement to "
            "'global' (the charge is refined at t = 0 by the AMR itself)")
    elif amr:
        # T70: a profile-initialised stage plans exactly the same way -
        # `_plan_amr` never looks at the charge and `validate_amr` skips
        # its "resolve the charge" rule when there is none
        if not rep.errors:
            from ..core.refine import plan_levels, validate_amr
            try:
                plan = plan_levels(case, rho0)
            except ValueError as exc:
                err(str(exc))
                return False
            aerr, awarn, anote = validate_amr(case, plan, rho0)
            rep.errors.extend(aerr)
            rep.warnings.extend(awarn)
            rep.notes.extend(anote)
            if aerr:
                plan = None
            else:
                rep.amr_levels = plan.amr
                rep.display_level = plan.display_level
                rep.lmax = plan.lmax
                rep.dx_fine = plan.dx_base / 2 ** plan.amr
                rep.n_fine = plan.n_fine
                if init != 'charge':
                    note(f"The remapped state is written on the "
                         f"{plan.dx_base:.5g} m base mesh and the AMR "
                         f"refines from there - the base cell, not the "
                         f"AMR level, sets how sharp the hand-off is")
                # T42/N16-b: AMR runs in parallel; the ingest reads
                # processor*/ directly (reconstructPar cannot follow a
                # mesh that changes between writes)
    elif case.dim >= 2 and (zones or cref == 'zone'):
        if not foam:
            err("Local mesh refinement (refinement zones / charge "
                "refinement 'zone') requires the blastFoam solver")
        elif cref not in ('global', 'zone'):
            err(f"Unknown charge refinement mode '{cref}' (use 'global' "
                f"or 'zone')")
        elif init == 'charge' and not rep.errors:
            plan = _plan_static_zones(case, rep, rho0, cref)
    ctx.plan = plan

    # What blastFoam will actually deposit (N5/T39): setFields marks
    # whole cells, so the charge is a staircase whose mass is only
    # approximately the requested one. Reported for foam cases with a
    # direct charge, at the finest spacing the charge will see.
    if foam and init == 'charge' and rep.r_exp and not rep.errors:
        dx_charge = dx
        if plan is not None:
            if plan.amr:
                dx_charge = plan.dx_base / 2 ** plan.amr
            else:
                dx_charge = plan.dx_fine
        _note_charge_cells(case, rep, dx_charge, dims, n_exp)
    return True


def _plan_static_zones(case, rep, rho0, cref):
    """Plan blastFoam's static refinement zones (`plan_levels` +
    `validate_zones`) and say what they give. Returns the plan, or None
    when it cannot be made or does not validate."""
    err, note = rep.errors.append, rep.notes.append
    from ..core.refine import plan_levels, validate_zones
    try:
        plan = plan_levels(case, rho0)
    except ValueError as exc:
        err(str(exc))
        return None
    zerr, zwarn = validate_zones(case, plan)
    rep.errors.extend(zerr)
    rep.warnings.extend(zwarn)
    if zerr:
        return None
    if plan.refined:
        note(f"Local refinement: {plan.lmax} level(s), "
             f"finest cell {plan.dx_fine:.5g} m, "
             f"~{plan.n_pred:,} mesh cells; results are "
             f"resampled to a {plan.n_fine:,}-cell display "
             f"grid")
        rep.lmax = plan.lmax
        rep.dx_fine = plan.dx_fine
        rep.n_fine = plan.n_fine
    if cref == 'zone':
        if plan.auto_level:
            note(f"Charge resolved by automatic level-"
                 f"{plan.auto_level} zones (base cell kept at "
                 f"{plan.dx_base:.5g} m)")
        else:
            note("The base cell already resolves the "
                 "charge - no automatic zone needed")
    return plan


def _note_charge_cells(case, rep, dx_charge, dims, n_exp):
    """How many whole cells blastFoam's setFields marks as charge at
    `dx_charge` [m], and the fraction of the requested mass they hold."""
    try:
        from ..core.refine import set_mass_fraction
        if case.dim == 2:
            if case.geometry == 'axisymmetric':
                cen = (0.0, case.center[1])
            else:
                cen = (case.center[0], case.center[1])
        else:
            cen = tuple(float(v) for v in case.center[:3])
        n_set, frac = set_mass_fraction(
            case.dim, getattr(case, 'geometry', ''), dx_charge,
            rep.r_exp, cen, dims)
    except (ValueError, ZeroDivisionError, IndexError):
        n_set = 0
    if case.dim >= 2 and n_set:
        rep.charge_cells = n_set
        rep.charge_mass_frac = frac
        rep.notes.append(f"Charge cells: {n_set:,} at {dx_charge:.5g} m -> "
                         f"~{frac:.2f} of the {case.charge:g} kg set by "
                         f"blastFoam (whole cells are marked; "
                         f"{n_exp} cells across the radius)")


def _validate_caps(case, rep, ctx, hw=None):
    """The cell caps - blastFoam's from the WSL VM, the native solvers'
    from this host - the cell count, the write budget, the blastFoam run
    plan and the refined display grid. `hw` is the WSL hardware dict;
    None, the default, reads `solvers.foam.env.hardware()` at call time,
    exactly where validation always read it."""
    err, warn, note = rep.errors.append, rep.warnings.append, rep.notes.append
    foam, amr, dims, dx = ctx.foam, ctx.amr, ctx.dims, ctx.dx
    refined, plan = ctx.refined, ctx.plan

    def scale_hint():
        """Why a modest cell size turned into a huge grid: the charge, not
        the cell-size field, sets the spacing, and it applies to the WHOLE
        uniform domain. Without this the user only saw 'cell size will be
        refined' and a cell count two orders of magnitude off what they
        asked for."""
        if not refined or not rep.r_exp:
            return ""
        return (f" - resolving the {2 * rep.r_exp:.3g} m charge forces a "
                f"{dx:.4g} m cell across the whole {max(dims):g} m domain; "
                f"use a smaller domain, a larger charge"
                + (", or charge resolution 'smear'"
                   if case.dim == 3 and not foam else "")
                + (", or blastFoam charge refinement 'zone'" if foam else ""))

    # N17/T48: the caps come from the WSL VM's measured RAM when a probe
    # has run (BYTES_PER_CELL). N21: when it has NOT, they come from a
    # conservatively assumed VM rather than the fixed FOAM_CELLS_*
    # constants - an unknown machine must not be treated as a large one.
    # `hardware()` never touches WSL, so validation stays instant.
    from ..solvers.foam import env as _env
    _hw = (_env.hardware() or {}) if hw is None else hw
    _caps = _env.plan_run(0, 0, cores=_hw.get('cores'),
                          ram_gb=_hw.get('ram_gb'), dim=case.dim,
                          ram_source=_hw.get('ram_source'),
                          cores_source=_hw.get('cores_source'))
    cap_warn, cap_refuse = _caps.cell_cap_warn, _caps.cell_cap_refuse

    # N21: the native solvers run in THIS process on the host's RAM, so
    # they get their own plan. `host()` is cache-only (ctypes, no I/O on
    # the validation path) and the derived cap can only lower the fixed
    # CELLS_* constants - the solvers keep enforcing those unchanged.
    _nat = _hardware.plan_native(
        dim=case.dim, order=int(getattr(case, 'order', 1) or 1),
        n_snapshots=int(getattr(case, 'n_snapshots', 6) or 6),
        ram_gb=_hardware.host().get('ram_gb'))
    nat_warn, nat_refuse = _nat.cell_cap_warn, _nat.cell_cap_refuse

    def host_hint():
        """Why the native cap is what it is, when RAM set it."""
        if not _nat.from_memory or nat_refuse >= (
                CELLS_2D_MAX if case.dim == 2 else CELLS_REFUSE):
            return ""
        return (f" (~{_nat.est_bytes(nat_refuse) / 2 ** 30:.1f} GB of the "
                f"{_nat.ram_gb} GB this PC has, at "
                f"~{_nat.bytes_per_cell / 1000:.2f} KB/cell) - the native "
                f"solver runs inside this app, so it cannot page out")

    def ram_hint():
        """Why the cap is what it is, in the units the user can act on."""
        gb = f"~{cap_refuse * BYTES_PER_CELL / 2 ** 30:.1f} GB"
        kb = f"~{BYTES_PER_CELL / 1000:.1f} KB/cell"
        if not _caps.from_memory:
            return (f" ({gb} of an assumed {FOAM_VM_GB_ASSUMED} GB WSL VM "
                    f"at {kb} - the real size is unknown) - let the WSL "
                    f"hardware probe finish, or click Re-detect")
        return (f" ({gb} of the {_hw['ram_gb']} GB WSL VM at {kb}) - "
                f"shrink the case, raise `memory=` in "
                f"%USERPROFILE%\\.wslconfig, or use AMR")

    if foam and not _caps.from_memory:
        warn(f"WSL hardware not detected - cell caps assume a "
             f"{FOAM_VM_GB_ASSUMED} GB VM ({cap_refuse:,} cells). A case "
             f"that validated on another machine may be refused here; "
             f"click Re-detect once WSL is up. Headless callers should "
             f"call solvers.foam.env.prime_from_settings() at start-up.")
    elif foam and _caps.ram_source == _hardware.CACHED:
        note(f"Cell caps from hardware measured on this machine in an "
             f"earlier session ({_hw['ram_gb']} GB VM); re-checking in "
             f"the background.")

    rep.effective_dx = dx
    if plan is not None and plan.amr:
        _check_amr_growth(case, rep, plan, cap_warn, cap_refuse, ram_hint)
    if case.dim == 2:
        n = int(case.Lx / dx) * int(case.Ly / dx)
        if plan is not None and (plan.refined or plan.amr):
            n = plan.n_pred
        if plan is not None and plan.amr:
            pass    # AMR: no static cap - maxCells was checked above
        elif foam:
            # blastFoam solves in WSL; Python only ingests written
            # frames, so the cap reflects wall time/disk, not RAM
            if n > cap_refuse:
                err(f"~{fmt_cells(n)} cells exceeds the blastFoam cap of "
                    f"{cap_refuse:,}" + ram_hint() + scale_hint())
            elif n > cap_warn:
                warn(f"Large grid: ~{n:,} cells - expect a long run "
                     f"and GBs of case files on the WSL disk")
        elif n > nat_refuse:
            err(f"~{fmt_cells(n)} cells exceeds the 2D cap of {nat_refuse:,}"
                + host_hint() + scale_hint())
        elif n > nat_warn:
            warn(f"Large grid: ~{n:,} cells - expect a long run"
                 f" and ~{_nat.est_bytes(n) / 2 ** 30:.1f} GB of RAM")
    else:
        n = int(case.Lx / dx) * int(case.Ly / dx) * int(case.Lz / dx)
        if plan is not None and (plan.refined or plan.amr):
            n = plan.n_pred
        if plan is not None and plan.amr:
            pass    # AMR: no static cap - maxCells was checked above
        elif foam:
            if n > cap_refuse:
                err(f"~{fmt_cells(n)} cells exceeds the blastFoam cap of "
                    f"{cap_refuse:,}" + ram_hint() + scale_hint())
            elif n > cap_warn:
                warn(f"Large grid: ~{n:,} cells - expect hours of wall "
                     f"time and GBs of case files on the WSL disk")
        elif n > nat_refuse:
            err(f"~{fmt_cells(n)} cells exceeds the 3D cap of {nat_refuse:,}"
                + host_hint() + scale_hint())
        elif n > nat_warn:
            warn(f"Large grid: ~{n:,} cells - expect a long run and "
                 f"~{_nat.est_bytes(n) / 2 ** 30:.1f} GB of RAM")
    rep.n_cells = n
    _validate_write_budget(case, rep, n, foam, amr)
    if foam:
        # N17/T48: resolve the rank count with the real cell count and
        # say what was decided, for auto (0) as well as an explicit ask.
        # Every argument the RUN will use is passed, so what validation
        # reports is what actually launches (N21: sources and the settings
        # rank limit included - without max_ranks the note would promise
        # more ranks than resolve_nprocs goes on to ask for)
        rep.run_plan = _env.plan_run(
            int(getattr(case, 'n_procs', 0) or 0), n,
            cores=_hw.get('cores'), ram_gb=_hw.get('ram_gb'),
            dim=case.dim, amr=amr, headroom=_env.mpi_headroom(),
            ram_source=_hw.get('ram_source'),
            cores_source=_hw.get('cores_source'),
            max_ranks=_env.mpi_max_ranks())
        if case.dim > 1:
            note("Parallel run: " + rep.run_plan.reason)
    if plan is not None and plan.refined:
        _check_display_grid(case, rep, plan)


def _check_amr_growth(case, rep, plan, cap_warn, cap_refuse, ram_hint):
    """AMR: the blastFoam cell caps against maxCells, and the disk a mesh
    per written time costs. `ram_hint` builds the tail of the refusal."""
    # the mesh grows during the run up to maxCells, so that is the number
    # the blastFoam caps apply to (t = 0 is the base grid)
    n_max = (int(getattr(case, 'amr_max_cells', 0) or 0)
             or cap_warn)
    if n_max > cap_refuse:
        rep.errors.append(f"AMR max cells {n_max:,} exceeds the blastFoam "
                          f"cap of {cap_refuse:,}" + ram_hint())
    elif n_max > cap_warn:
        rep.warnings.append(f"AMR may grow the mesh to {n_max:,} cells - "
                            f"expect a long run and GBs of case files on "
                            f"the WSL disk")
    # every written time keeps its own mesh (cell centres + levels), so
    # an AMR run's disk cost is much larger than a static one's
    n_w = max(int(getattr(case, 'n_snapshots', 6) or 6), 1)
    mb = plan.n_pred * 60 / 1e6            # ~60 B per cell per write
    if mb * n_w > 200:
        rep.notes.append(f"AMR keeps a mesh per written time: roughly "
                         f"{mb:.0f} MB per write, about "
                         f"{mb * n_w / 1000:.1f} GB for this run on the "
                         f"WSL disk - clean old runs with 'Foam runs...' "
                         f"or --clean-foam-runs")


def _check_display_grid(case, rep, plan):
    """Refined results: Python holds the resampled fine grid per ingested
    write, so the display grid is capped like a native run's grid."""
    if case.dim == 2:
        cap_refuse, cap_warn = CELLS_2D_MAX, CELLS_2D_WARN
    else:
        cap_refuse, cap_warn = CELLS_REFUSE, CELLS_WARN
    if plan.n_fine > cap_refuse:
        if plan.amr:
            fix = "lower the AMR display level or use a coarser base"
        else:
            fix = "use fewer levels or a coarser base"
        rep.errors.append(f"Refined results are resampled to a "
                          f"{plan.n_fine:,}-cell display grid (finest cell "
                          f"{plan.dx_fine:.5g} m), above the "
                          f"{cap_refuse:,} cap - " + fix)
    elif plan.n_fine > cap_warn:
        rep.warnings.append(f"Refined results are resampled to a "
                            f"{plan.n_fine:,}-cell display grid - expect "
                            f"GBs of RAM for frames and snapshots")


def _validate_closing(case, rep, ctx):
    """The closing checks: gauges and obstacles inside the domain,
    obstacle walls at least two base cells thick, and the 2D profile
    export."""
    err, warn = rep.errors.append, rep.warnings.append
    foam, dims, dx, plan = ctx.foam, ctx.dims, ctx.dx, ctx.plan

    # gauges / obstacles sanity
    dropped = None                  # the solver's drop rule, built once
    for k, g in enumerate(getattr(case, 'gauges', []), start=1):
        pt = g if isinstance(g, (list, tuple)) else (g,)
        # GUI-13 (c), D4: the gauge as the screens name it, G<n> (1-based,
        # the entered order) at its coordinates in metres
        name = f"G{k} ({', '.join(f'{float(v):.2f}' for v in pt)}) m"
        if any(not (0 <= v <= L) for v, L in zip(pt, dims)):
            warn(f"{name} {gauge_drop_reason(0, False, outside=True)}"
                 f" - will be dropped")
            continue
        if dropped is None:
            dropped = _gauge_drop_rule(case, ctx)
        wall = dropped(pt)
        if not wall:
            continue
        # GUI-12 A4: named as Run and Setup's Where column name it; the
        # inside / face split is the open-box test
        inside = _in_obstacle_open(pt, case.obstacles)
        warn(f"{name} "
             f"{gauge_drop_reason(inside or wall, bool(inside))}"
             f" - will be dropped")
    for box in case.obstacles:
        lo, hi = box[0::2], box[1::2]
        if any(a >= b for a, b in zip(lo, hi)) or \
           any(b > L or a < 0 for a, b, L in zip(lo, hi, dims)):
            err(f"Obstacle {box} is not a valid in-domain box")
            continue
        dxb = plan.dx_base if plan is not None else dx
        if dxb and dxb > 0:
            _warn_thin_obstacle(rep, box, lo, hi, dxb, foam)

    if case.dim == 2 and case.profile_file and case.geometry != 'axisymmetric':
        err("2D profile export (for 3D remap) requires axisymmetric geometry")


def drop_rule(case, pending_inputs=False):
    """`dropped(pt)`: the 1-based wall for which the case's solver drops
    gauge `pt`, 0 when it keeps it, when `pt` is outside the domain, or
    when the case cannot be laid out. The same rule as the validation
    warning (`_gauge_drop_rule` on the context `validate_case` builds up
    to its refinement block, which is all the rule reads), so Setup's
    warning, Setup's Where column and Run's dropped-gauge note name one
    wall (GUI-13 (e)). Build it once per case, call it per gauge."""
    def none(_pt):
        return 0
    try:
        if case.dim < 2 or not case.obstacles:
            return none
        rep = ValidationReport()
        ctx = _validate_common(case, rep)
        if ctx is None or not _validate_domain_and_charge(case, rep, ctx):
            return none
        _validate_profile_init(case, rep, ctx, pending_inputs)
        if not _validate_refinement(case, rep, ctx):
            return none
        rule, dims = _gauge_drop_rule(case, ctx), ctx.dims
    except (ArithmeticError, AttributeError, IndexError, TypeError,
            ValueError):
        return none

    def dropped(pt):
        pt = tuple(float(v) for v in pt)
        if any(not (0 <= v <= L) for v, L in zip(pt, dims)):
            return 0
        return rule(pt)
    return dropped


def drop_wall(case, point):
    """The 1-based wall for which the case's solver drops gauge `point`,
    0 when it keeps it (`drop_rule`; one call, one gauge)."""
    return drop_rule(case)(point)


def _gauge_drop_rule(case, ctx):
    """`dropped(pt)`: the 1-based index of the obstacle for which the
    case's solver will drop the in-domain gauge `pt`, 0 when it keeps it
    - each solver's own rule, so the warning is exact (F44, GUI-11e A2;
    owner review row 2). Snapping keeps the obstacles' order, so the
    index is the case's (`Wall n`, GUI-12 A4). No solver code runs:

    native      the nearest cell centre per axis is solid, by the closed
                test of core/bc.solid_mask_2d/3d on the raw boxes
                (solvers/solver2d.py and solver3d.py, gauge setup). The
                centres are the solver's own: `case.cell_size_m`, or the
                charge auto-refine of solver2d.py 163-175 / solver3d.py
                186-203 (`refine.effective_dx`, not 'smear', not a
                profile start - P3), fitted by core.grid like
                make_geometry / make_grid. Never `ctx.dx`: the validator
                refines to r_exp / n_exp, which is not the solver's.
    blastFoam   the closed test on the boxes snapped OUTWARD onto
                base-cell faces (core.refine.snap_obstacles;
                solvers/foam/writer.py 495-501 / 555-562), on the plan's
                base spacing - `ctx.plan.dx_base`, or the base cell of
                refine.plan_levels 516-530 when no plan was made.

    Per-axis 1-D centres only, never a full mask (validation runs on
    every keystroke)."""
    from ..core.grid import _faces_shared
    from ..core import refine
    obstacles = [tuple(float(v) for v in b) for b in case.obstacles or []]
    n = case.dim
    if n < 2 or not obstacles:
        return lambda pt: 0
    lengths = tuple(float(L) for L in ctx.dims)
    charged = (getattr(case, 'init_mode', 'charge') == 'charge'
               and case.charge is not None and case.charge > 0)
    dx = float(case.cell_size_m)
    try:
        if ctx.foam:
            plan = ctx.plan
            if plan is not None:
                dx_base = float(plan.dx_base)
            else:
                amr = int(getattr(case, 'amr_levels', 0) or 0)
                if (charged and not amr
                        and getattr(case, 'charge_refine', 'global') != 'zone'):
                    dx = min(refine.effective_dx(dx, r, case.Lx, ctx.n_exp)
                             for _c, r in refine._charges(case, ctx.rho0))
                dx_base = _faces_shared(lengths, dx)[1]
            boxes, _moved = refine.snap_obstacles(obstacles, dx_base, n)
            return lambda pt: _in_box_closed(pt, boxes)
        if charged:
            r_exp = _charge_radius(case, ctx.rho0)
            smear = (n == 3 and getattr(case, 'charge_resolution',
                                        'resolve') == 'smear')
            if not (smear and dx > r_exp / MIN_EXP_CELLS):
                dx = refine.effective_dx(dx, r_exp, case.Lx, MIN_EXP_CELLS)
        if any(L / dx > 1e7 for L in lengths):
            raise ValueError('grid too fine to lay out')
        faces, _dx = _faces_shared(lengths, dx)
    except (ArithmeticError, ValueError, TypeError, IndexError):
        # a case that cannot be gridded is refused elsewhere; the open
        # box still says "inside"
        return lambda pt: _in_obstacle_open(pt, obstacles)
    centres = [0.5 * (f[:-1] + f[1:]) for f in faces]

    def native(pt):
        near = [float(c[int(np.argmin(np.abs(c - float(v))))])
                for c, v in zip(centres, pt)]
        return _in_box_closed(near, obstacles)
    return native


def _warn_thin_obstacle(rep, box, lo, hi, dxb, foam):
    """Warn once, on the first axis along which obstacle `box` is a
    single base cell `dxb` [m] thick.

    A wall carved a single cell thick is a numerical hazard: shock
    diffraction over a one-cell blade collapses deltaT and can end in
    SIGFPE (measured: 0.3 m wall on a 0.5 m base mesh). The carve uses
    base-cell FACES (refine.snap_obstacles outward for foam), so the count
    below is the snapped width, not len/dx."""
    for ax, (a, b) in enumerate(zip(lo, hi)):
        n_side = (int(np.ceil(b / dxb - 1e-6))
                  - int(np.floor(a / dxb + 1e-6)))
        if n_side > 1:
            continue
        # the obvious "just add AMR" does not work, and the crashing run
        # (20260915-090553) proved it: it ran amr_levels = 2 and still
        # hit SIGFPE
        if foam:
            amr_note = (" (AMR levels do not help: obstacles are carved on "
                        "the base mesh, so the wall stays one base cell at "
                        "every level)")
        else:
            amr_note = ""
        rep.warnings.append(
            f"Obstacle {box} is only one cell thick along "
            f"{'xyz'[ax]} ({b - a:g} m wall, {dxb:g} m base "
            f"cell) - shock reflection off a single-cell "
            f"wall tends to go numerically unstable. Use a "
            f"base cell <= {(b - a) / 2:g} m so the wall is "
            f"at least 2 cells thick" + amr_note)
        return


def validate_case(case, pending_inputs=False):
    """Full pre-run report for one case.

    `pending_inputs=True` means the case's profile input is produced by
    an earlier stage of the same chain run, so its absence on disk right
    now is expected rather than an error (everything else is still
    checked). Only the chain panel passes it.

    The checks run in blocks, each appending to one report, in the order
    they always ran; a block that returns False (or None) ends validation
    there, as the early `return rep`s of the single function did."""
    rep = ValidationReport()
    ctx = _validate_common(case, rep)
    if ctx is None:
        return rep
    if case.dim == 1:
        _validate_1d(case, rep, ctx)
        # OUT-2: here rather than inside _validate_1d, whose early return
        # on a charge error would skip it
        _validate_vtk(case, rep, ctx)
        _validate_keep_all(case, rep, ctx)
        return rep
    if not _validate_domain_and_charge(case, rep, ctx):
        return rep
    _validate_profile_init(case, rep, ctx, pending_inputs)
    if not _validate_refinement(case, rep, ctx):
        return rep
    _validate_caps(case, rep, ctx)
    _validate_vtk(case, rep, ctx)
    _validate_keep_all(case, rep, ctx)
    _validate_closing(case, rep, ctx)
    return rep
