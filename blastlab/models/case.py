"""Case definitions: the three blast-case dataclasses and their versioned
JSON form (used by the GUI, the chain workflow, and scripting).

Moved verbatim from `core/case.py` in Phase 2 of docs/ARCHITECTURE_REVIEW.md
(section 5). `core/case.py` re-exports every name here, so the old import
path keeps returning the same objects. This module imports only `core`.
"""

import json
import os
from dataclasses import dataclass, field, asdict

from ..core.bc import normalize_bcs

#: T51 trigger-gauge actions (2D/3D only - T63 removed the 1D trigger).
#: 'remap' writes the remap file at the arrival instant and lets the run
#: continue; the other two end it.
TRIGGER_ACTIONS = ('terminate', 'remap', 'remap+terminate')

#: OUT-2: the fields a VTK family may export - what blastFoam already
#: writes (docs/model-folder-and-vtk-plan.md sec. 3.2). The four
#: function-object fields exist for dim >= 2 only: writer.py emits
#: impulse / pMax / timeOfArrival / overpressure for 2D/3D alone.
#: OUT-4a: `dynamicP` (blastFoam's dynamicPressure function object,
#: blastFoam User Guide v6.0, sec. 15.9, p. 125) is APPENDED - vtk_matrix
#: canonicalises in this order, so reordering would change saved JSON.
#: OUT-4b (owner Q2): `impulseMax`, the per-cell running max of the net
#: impulse (fieldMinMax on impulse, guide sec. 15.2, p. 123), appended.
VTK_FIELDS = ('p', 'overpressure', 'impulse', 'pMax', 'timeOfArrival',
              'rho', 'U', 'T', 'alpha.expl', 'rhoE', 'dynamicP',
              'impulseMax')
VTK_FO_FIELDS = ('overpressure', 'impulse', 'pMax', 'timeOfArrival',
                 'impulseMax')
#: OUT-4a: the matrix columns each field has a cell in (plan sec. 3.2,
#: sec. 9). Every field is written to every file family; at the gauges
#: (blastProbes, guide sec. 15.1) only what a trace means: p/rho/U (always
#: recorded, locked) and the four extras T, overpressure, impulse, q.
_FAMILIES = ('sections', 'obstacles', 'volumes')
VTK_CELLS = {f: (('gauges',) if f in ('p', 'overpressure', 'impulse', 'rho',
                                      'U', 'T', 'dynamicP') else ())
             + _FAMILIES for f in VTK_FIELDS}
#: the gauge fields every blastFoam run records (wallload and the plots
#: consume them): shown ticked and locked, never listed in `vtk_gauges`
VTK_GAUGE_LOCKED = ('p', 'rho', 'U')
#: cadence units: 'time' = simulated SECONDS, like every other time in
#: the case (owner decision P22, 2026-09-27, reversing Q3's ms), 'step' =
#: solver steps
VTK_MODES = ('time', 'step')
#: the keys of each family, in the order they are written
VTK_VOLUME_KEYS = ('on', 'mode', 'value', 'fields')
#: Q2 (owner, 2026-09-26): sections and obstacles keep separate field
#: lists - `fields` for the section planes, `obstacle_fields` for the
#: obstacle walls
VTK_SURFACE_KEYS = ('on', 'mode', 'value', 'fields', 'obstacle_fields',
                    'planes')
#: the array name each field gets inside the exported .vtk files, the same
#: in every family (owner decision 5, docs/batches/2026-09-27-out-2-
#: surface-layout.md, after the Viper samples' `pressure` /
#: `Peak_Ovepressure`, spelled "Overpressure"). `pMax` is written as the
#: peak OVERPRESSURE, pMax - ambient (owner decision 4). OUT-4b (owner
#: Q1, 2026-09-27): blastFoam's timeOfArrival is the time of PEAK pressure
#: (blastFoam User Guide v6.0, sec. 15.12, p. 126), so it is written as
#: `Time_Of_Peak`, not `Arrival_Time`.
VTK_ARRAY_NAMES = {'p': 'pressure', 'pMax': 'Peak_Overpressure',
                   'impulse': 'Impulse', 'overpressure': 'Overpressure',
                   'timeOfArrival': 'Time_Of_Peak', 'rho': 'density',
                   'U': 'velocity', 'T': 'temperature',
                   'alpha.expl': 'Products_Fraction', 'rhoE': 'Energy',
                   'dynamicP': 'Dynamic_Pressure',
                   'impulseMax': 'Peak_Impulse'}


def vtk_fields_for(dim):
    """The VTK fields a case of dimension `dim` has (D4)."""
    return tuple(f for f in VTK_FIELDS
                 if dim >= 2 or f not in VTK_FO_FIELDS)


def vtk_gauge_extras_for(dim):
    """OUT-4a: the fields that may be ticked at the gauges of a case of
    dimension `dim` - VTK_CELLS' gauge cells minus the locked three;
    overpressure / impulse are 2D/3D only, like every function-object
    field (D4)."""
    return tuple(f for f in vtk_fields_for(dim)
                 if 'gauges' in VTK_CELLS[f] and f not in VTK_GAUGE_LOCKED)


def normalize_vtk_gauges(d):
    """OUT-4a: `vtk_gauges` in canonical form, {'fields': [str, ...]}, or
    None. An unknown key or a non-object is refused; the field names are
    kept as given, for validation to name."""
    if d is None:
        return None
    if not isinstance(d, dict):
        raise ValueError(f"vtk_gauges must be an object, not "
                         f"{type(d).__name__}")
    unknown = set(d) - {'fields'}
    if unknown:
        raise ValueError(f"Unknown vtk_gauges keys: {sorted(unknown)}")
    names = d.get('fields') or []
    if not isinstance(names, (list, tuple)):
        # a bare string would iterate as letters ("impulse" -> 'i', 'm'...)
        raise ValueError(f"vtk_gauges.fields must be a list, not "
                         f"{type(names).__name__}")
    return {'fields': [str(f) for f in names]}


def vtk_gauge_fields(case):
    """OUT-4a: the extra gauge fields a blastFoam case asks for, in
    VTK_FIELDS order (unknown names dropped - validation refuses them);
    () for a native case or none ticked."""
    if getattr(case, 'solver', 'native') != 'blastfoam':
        return ()
    try:
        d = normalize_vtk_gauges(getattr(case, 'vtk_gauges', None))
    except ValueError:
        return ()
    names = (d or {}).get('fields') or ()
    return tuple(f for f in VTK_FIELDS if f in names)


def _num(v):
    """float(v), or v itself when it is not a number (validation says so)."""
    if isinstance(v, bool):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def normalize_vtk(d, key):
    """One VTK family (`key` is 'vtk_surfaces' or 'vtk_volumes') in its
    canonical form: every key present, in file order, `fields` a list of
    str, `planes` a list of [axis, float], `value` a float in Time mode
    (s) and an int in Step mode when it is whole. None stays None. A
    value that cannot be converted is kept as given, for validation to
    name; an unknown key or a non-object is refused."""
    if d is None:
        return None
    if not isinstance(d, dict):
        raise ValueError(f"{key} must be an object, not {type(d).__name__}")
    keys = VTK_SURFACE_KEYS if key == 'vtk_surfaces' else VTK_VOLUME_KEYS
    unknown = set(d) - set(keys)
    if unknown:
        raise ValueError(f"Unknown {key} keys: {sorted(unknown)}")
    mode = d.get('mode', 'time')
    value = _num(d.get('value'))
    if mode == 'step' and isinstance(value, float) and value.is_integer():
        value = int(value)
    out = dict(on=bool(d.get('on', False)), mode=mode, value=value,
               fields=[str(f) for f in (d.get('fields') or [])])
    if key == 'vtk_surfaces':
        out['obstacle_fields'] = [str(f) for f in
                                  (d.get('obstacle_fields') or [])]
        out['planes'] = [[str(p[0]), _num(p[1])]
                         if isinstance(p, (list, tuple)) and len(p) == 2
                         else p for p in (d.get('planes') or [])]
    return out


def vtk_written(d):
    """Does case_to_dict write this VTK family? When it is on, or when it
    is off but still has a field ticked (owner decision P15)."""
    if not isinstance(d, dict):
        return False
    return bool(d.get('on') or d.get('fields') or d.get('obstacle_fields'))


def vtk_family(case, key):
    """The case's VTK family `key`, normalised, when it is switched on;
    else None."""
    d = getattr(case, key, None)
    if not isinstance(d, dict) or not d.get('on'):
        return None
    return normalize_vtk(d, key)

SCHEMA = 'blastlab-case'
VERSION = 13    # v2: n_procs, activation, charges, det_points (foam)
                # v3: refine_zones, charge_refine (foam local refinement)
                # v4: afterburn (foam Miller afterburn model)
                # v5: amr_* (foam dynamic mesh refinement, N16)
                # v6: anim_mesh (cell-edge overlay in the run's
                #     exported animation)
                # v7: boundary kinds transmit|reflect|terminate
                #     (T50; 'open'/'wall' still read and mapped)
                # v8: t_end on 1D/2D as well (T52)
                # v9: trigger_gauge / trigger_action / trigger_file (T51)
                # v10: bc_outer on Case1D (T60)
                # v11: the 1D trigger gauge is gone (T63); the keys are
                #      dropped from older 1D files rather than refused
                # v12: anim_scale / anim_clim (the exported animation's
                #      colour range: one for the whole video by default,
                #      per frame as before, or a range you pin)
                # v13: adaptive_write. The chain has always pinned it to
                #      False for reproducibility (N2-13), but as an
                #      ad-hoc attribute, which asdict() does not see - so
                #      the stage JSONs it saved "for reproducibility"
                #      lost exactly the flag that made them reproducible


@dataclass
class Case1D:
    dim = 1
    radius_m: float = 10.0
    charge_kg: float = 1.0
    cell_size_m: float = 0.001
    eos: str = 'idealGas'
    #: T60: the far end of the spherical sector - the same three kinds
    #: the 2D/3D sides take. 'terminate' is what 1D always did.
    bc_outer: str = 'terminate'
    cfl: float = 0.5
    t_end: float = 0.0                # stop at t_end [s]; 0 = auto (T52)
    n_snapshots: int = 5
    gauge_radii: list = field(default_factory=list)
    gauge_file: str = 'gauges.txt'
    profile_file: str = None          # save final field for 2D/3D remap
    #: T63: 1D has no trigger gauge. The whole 1D run is the hand-off
    #: (`profile_file` is written at the end) and `bc_outer='terminate'`
    #: already stops it at the sector's end, so a per-gauge trigger only
    #: ever duplicated those two - in blastFoam 1D it did nothing at all.
    solver: str = 'native'            # 'native' | 'blastfoam' (WSL)
    material: str = 'TNT'             # blastFoam charge material
    activation: str = 'linear'        # blastFoam detonation model:
                                      # 'linear' (burn at vDet) |
                                      # 'none' (instant)
    #: optional, aligned with det_points (N5-12): per-point ignition
    #: delay [s] and initiation radius [m]. None = all zero, blastFoam's
    #: own defaults. Guide 5.6.1: valid for any activation model.
    det_delays: list = None
    det_radii: list = None
    afterburn: str = 'none'           # blastFoam afterburn model:
                                      # 'none' | 'miller' (products
                                      # burning with atmospheric oxygen)
    #: native reconstruction order (T47/N10): 1 = the pinned Godunov
    #: path, 2 = opt-in limited MUSCL (native solvers only)
    order: int = 1
    #: blastProbes `adjustLocations`. A no-op for every gauge we write:
    #: it relocates only probes found in NO cell (blastProbes.C:218),
    #: and ours are interior. T40 measured it - arrival moves 0.15 pp
    #: with it off - and DONE.md records the old reading as REFUTED.
    probe_adjust: bool = True
    #: B23/N2-13: False pins writeInterval for the whole run. The
    #: adaptive controller rewrites it mid-run from what the ingest has
    #: kept up with - wall clock - so the set of write times differs
    #: between identical runs. The Chain tab pins it on every stage.
    adaptive_write: bool = True
    n_procs: int = 0                  # blastFoam MPI ranks (0 = auto;
                                      # 1D always runs serial)
    #: OUT-2: VTK volumes (the whole radial line) for ParaView,
    #: {on, mode, value, fields}; None or on = False is not written
    #: (case_to_dict). 1D has no sections or obstacles, so no
    #: vtk_surfaces: a 1D file carrying one is refused as an unknown key.
    vtk_volumes: dict = None
    #: OUT-4a: the extra gauge fields, {'fields': [...]} (only the extras;
    #: p, rho, U are always recorded). None or empty is not written.
    vtk_gauges: dict = None
    #: OUT-3: keep every written time in WSL, and the scratch after the
    #: run (blastFoam only). False (the default) is not written.
    keep_all_fields: bool = False


@dataclass
class Case2D:
    dim = 2
    geometry: str = 'axisymmetric'    # 'planar' | 'axisymmetric'
    # 4 m, not 10: resolving the default 1 kg charge with blastFoam's 8
    # cells across the radius (T39) makes a 10 m domain 2.3M cells,
    # which is ~6 GB inside the solver - more than a default 4 GB WSL VM
    # holds (T48 measured ~2.65 KB/cell). 4 m is 368k cells: valid and
    # warning-free out of the box on the smallest supported machine.
    Lx: float = 4.0
    Ly: float = 4.0
    cell_size_m: float = 0.025
    init_mode: str = 'charge'         # 'charge' | 'profile1d'
    charge: float = 1.0               # kg (axisym) / kg per m (planar)
    profile_file_in: str = None       # 1D profile to remap
    center: tuple = (0.0, 2.0)        # (x0, y0); axisym forces x0 = 0
    eos: str = 'idealGas'
    #: T50: 'transmit' (wave leaves, run carries on) | 'reflect' (wall)
    #: | 'terminate' (wave leaves AND ends the run - the pre-T50 'open')
    bcs: dict = field(default_factory=lambda: dict(
        x_lo='reflect', x_hi='transmit',
        y_lo='reflect', y_hi='transmit'))
    obstacles: list = field(default_factory=list)   # (x0,x1,y0,y1)
    refine_zones: list = field(default_factory=list)  # blastFoam local
                                      # refinement: (x0,x1,y0,y1,level),
                                      # level l = base cell / 2**l
    charge_refine: str = 'global'     # 'global': refine the whole grid to
                                      # resolve the charge (native rule) |
                                      # 'zone': keep the base cell, add
                                      # automatic nested zones (blastFoam)
    amr_levels: int = 0               # blastFoam dynamic refinement
                                      # (adaptiveFvMesh): levels below the
                                      # base cell the mesh may reach, 0 = off
    amr_estimator: str = 'Lohner'     # 'Lohner' | 'densityGradient'.
                                      # Default flipped 2026-09-20 (P1-6,
                                      # owner decision): densityGradient
                                      # holds the near-axis charge crater
                                      # refined until wedge cells drain to
                                      # vacuum -> SIGFPE (axisym); Lohner
                                      # (on p) ran the same case clean.
                                      # An explicit choice is honoured.
    amr_refine: float = 0.2           # lowerRefineLevel (refine above);
                                      # RE-TUNED 2026-09-10. 0.4/0.2 was
                                      # chosen for ~3.6 % gauge error, but
                                      # T39 (5 -> 8 cells across the charge
                                      # radius) moved the case underneath
                                      # it and the same sweep now measures
                                      # -11.8 %. Re-running that sweep:
                                      #   0.4/0.2  -11.8 %  55 s  17,425
                                      #   0.2/0.1   -3.9 %  54 s  20,224
                                      #   0.1/0.05  -2.9 %  54 s  20,377
                                      # 0.2/0.1 restores the accuracy the
                                      # default was picked for, at no wall
                                      # -time cost (the tutorials' 0.1/0.1
                                      # refines nearly everything)
    amr_unrefine: float = 0.1         # unrefineLevel (unrefine below)
    amr_interval: int = 2             # refineInterval [steps]
    amr_buffer: int = 2               # nBufferLayers
    amr_max_cells: int = 0            # maxCells, 0 = FOAM_CELLS_WARN
    amr_display_level: int = None     # display grid level (None = deepest
                                      # level under the display cap)
    cfl: float = 0.4
    t_end: float = 0.0                # stop at t_end [s]; 0 = auto (T52)
    n_snapshots: int = 6
    gauges: list = field(default_factory=list)      # (x, y)
    gauge_file: str = 'gauges_2d.txt'
    #: T51 trigger gauge: 1-based index into `gauges`, None = off. When
    #: the wave reaches it the run ends and/or the remap file is written
    #: at THAT instant - the chain hand-off that used to be possible
    #: only at the end of a run. 2D/3D only (T63).
    trigger_gauge: int = None
    trigger_action: str = 'terminate'
    trigger_file: str = None
    anim_file: str = None
    anim_mesh: bool = False           # overlay the cell edges on the
                                      # animation written after the run
    #: the animation's overpressure colour range: 'run' pins one range
    #: for the whole video (default), 'frame' rescales every frame,
    #: 'manual' uses anim_clim. See output/animation.SCALES.
    anim_scale: str = 'run'
    anim_clim: tuple = None           # (vmin, vmax) kPa for 'manual'
    record_frames: int = 150
    live: bool = True
    profile_file: str = None          # save .npz for 3D remap (axisym only)
    solver: str = 'native'            # 'native' | 'blastfoam' (WSL)
    material: str = 'TNT'             # blastFoam charge material
    activation: str = 'linear'        # blastFoam detonation model:
                                      # 'linear' (burn at vDet) |
                                      # 'none' (instant)
    #: optional, aligned with det_points (N5-12): per-point ignition
    #: delay [s] and initiation radius [m]. None = all zero, blastFoam's
    #: own defaults. Guide 5.6.1: valid for any activation model.
    det_delays: list = None
    det_radii: list = None
    afterburn: str = 'none'           # blastFoam afterburn model:
                                      # 'none' | 'miller' (products
                                      # burning with atmospheric oxygen)
    #: native reconstruction order (T47/N10): 1 = the pinned Godunov
    #: path, 2 = opt-in limited MUSCL (native solvers only)
    order: int = 1
    #: blastProbes `adjustLocations`. A no-op for every gauge we write:
    #: it relocates only probes found in NO cell (blastProbes.C:218),
    #: and ours are interior. T40 measured it - arrival moves 0.15 pp
    #: with it off - and DONE.md records the old reading as REFUTED.
    probe_adjust: bool = True
    adaptive_write: bool = True       # see Case1D.adaptive_write (B23)
    #: HD1-15: N > 0 pins blastFoam's writeInterval to t_end / N (an
    #: explicit t_end is required) and keeps the decomposed copy of the
    #: latest write only. 0 = off, and then the key is not even written
    #: (case_to_dict), so every case without one is byte for byte as before.
    write_budget: int = 0
    n_procs: int = 0                  # blastFoam MPI ranks (0 = auto)
    det_points: list = None           # blastFoam: detonation points
                                      # [(x, y), ...] (axisym: x = 0);
                                      # None = charge centre
    #: OUT-2: VTK output for ParaView, blastFoam only. `vtk_surfaces` =
    #: {on, mode, value, fields, obstacle_fields, planes} (2D: obstacles
    #: only), `vtk_volumes` = {on, mode, value, fields}; `value` is seconds
    #: in Time mode (P22), solver steps in Step mode. None or on = False is not
    #: written (case_to_dict), so a case without them is byte-identical.
    vtk_surfaces: dict = None
    vtk_volumes: dict = None
    vtk_gauges: dict = None           # see Case1D.vtk_gauges (OUT-4a)
    keep_all_fields: bool = False     # see Case1D.keep_all_fields (OUT-3)


@dataclass
class Case3D:
    dim = 3
    # P1-1: the same rule the 2D default follows, and the values the GUI's
    # 3D form has opened with since QA-14 - there is one shipped 3D default
    # now, not two. `resolve` forces dx = r_charge / 8 (blastFoam, T39)
    # across the WHOLE domain, so the domain a charge allows is set by the
    # charge: 1 kg in 10 m is 3.5 BILLION cells and is refused on every
    # backend, while 25 kg (r = 0.154 m -> dx = 0.0193 m) in 1.5 m is 474k
    # cells on blastFoam and 116k native - valid and warning-free out of
    # the box on the smallest supported machine. Keeping 1 kg here would
    # have meant a 0.74 m domain, which is not a free-air case at all.
    Lx: float = 1.5
    Ly: float = 1.5
    Lz: float = 1.5
    cell_size_m: float = 0.025
    init_mode: str = 'charge'         # 'charge' | 'profile1d' | 'profile2d'
                                      # | 'chamber' (HD1-3b)
    #: HD1-3b, both falsy by default so every existing golden is
    #: byte-identical. `room` is what `core/room.py:measure` returned -
    #: the ALIGNED geometry, not the numbers someone typed - and
    #: `chamber_state` is `core/vent.py:ChamberState.as_dict()`. The two
    #: must describe the same room: the state's volume is what the 0-D
    #: model ran at, and validation compares it with the cavity the
    #: boxes actually leave.
    room: dict = field(default_factory=dict)
    chamber_state: dict = field(default_factory=dict)
    #: Run at a PRESCRIBED time step instead of a Courant-controlled
    #: one. 0 = adaptive, which is what every real case wants and what
    #: every golden is written against.
    #:
    #: It exists for verification cases that are deliberately QUIESCENT.
    #: blastFoam takes its Courant number from the face fluxes, so a
    #: field that is exactly uniform and exactly at rest has Co = 0 and
    #: `Time::adjustDeltaT` divides by it - measured, a SIGFPE on the
    #: first step of `_e2e_gamma_interface.py`. A real chamber case is
    #: pressurised and gets a flux immediately, so this is not a
    #: limitation anyone else meets.
    fixed_dt: float = 0.0
    charge: float = 25.0
    charge_resolution: str = 'resolve'  # 'resolve' (refine grid to charge)
                                        # | 'smear' (keep cell size,
                                        #   energy-conserving source ball)
    profile_file_in: str = None
    center: tuple = (0.75, 0.75, 0.75)  # z ignored for profile2d
    eos: str = 'idealGas'
    #: see Case2D.bcs
    bcs: dict = field(default_factory=lambda: dict(
        x_lo='transmit', x_hi='transmit', y_lo='transmit',
        y_hi='transmit', z_lo='reflect', z_hi='transmit'))
    obstacles: list = field(default_factory=list)   # (x0,x1,y0,y1,z0,z1)
    refine_zones: list = field(default_factory=list)  # blastFoam local
                                      # refinement: (x0,x1,y0,y1,z0,z1,level)
    charge_refine: str = 'global'     # 'global' | 'zone' (see Case2D)
    amr_levels: int = 0               # blastFoam dynamic refinement
                                      # (adaptiveFvMesh): levels below the
                                      # base cell the mesh may reach, 0 = off
    amr_estimator: str = 'Lohner'     # 'Lohner' | 'densityGradient'.
                                      # Default flipped 2026-09-20 (P1-6,
                                      # owner decision): densityGradient
                                      # holds the near-axis charge crater
                                      # refined until wedge cells drain to
                                      # vacuum -> SIGFPE (axisym); Lohner
                                      # (on p) ran the same case clean.
                                      # An explicit choice is honoured.
    amr_refine: float = 0.2           # lowerRefineLevel (refine above);
                                      # RE-TUNED 2026-09-10. 0.4/0.2 was
                                      # chosen for ~3.6 % gauge error, but
                                      # T39 (5 -> 8 cells across the charge
                                      # radius) moved the case underneath
                                      # it and the same sweep now measures
                                      # -11.8 %. Re-running that sweep:
                                      #   0.4/0.2  -11.8 %  55 s  17,425
                                      #   0.2/0.1   -3.9 %  54 s  20,224
                                      #   0.1/0.05  -2.9 %  54 s  20,377
                                      # 0.2/0.1 restores the accuracy the
                                      # default was picked for, at no wall
                                      # -time cost (the tutorials' 0.1/0.1
                                      # refines nearly everything)
    amr_unrefine: float = 0.1         # unrefineLevel (unrefine below)
    amr_interval: int = 2             # refineInterval [steps]
    amr_buffer: int = 2               # nBufferLayers
    amr_max_cells: int = 0            # maxCells, 0 = FOAM_CELLS_WARN
    amr_display_level: int = None     # display grid level (None = deepest
                                      # level under the display cap)
    cfl: float = 0.30
    t_end: float = 0.0                # stop at t0 + t_end [s]; 0 = auto
    slice_axis: str = 'y'             # live-slice normal: 'x' | 'y' | 'z'
    slice_pos: float = None           # slice position [m]; None = burst point
    n_snapshots: int = 6
    gauges: list = field(default_factory=list)      # (x, y, z)
    gauge_file: str = 'gauges_3d.txt'
    #: see Case2D.trigger_gauge ('remap' is refused in 3D)
    trigger_gauge: int = None
    trigger_action: str = 'terminate'
    trigger_file: str = None
    anim_file: str = None
    anim_mesh: bool = False           # overlay the cell edges on the
                                      # animation written after the run
    #: see Case2D.anim_scale
    anim_scale: str = 'run'
    anim_clim: tuple = None           # (vmin, vmax) kPa for 'manual'
    record_frames: int = 150
    live: bool = True
    solver: str = 'native'            # 'native' | 'blastfoam' (WSL)
    material: str = 'TNT'             # blastFoam charge material
    activation: str = 'linear'        # blastFoam detonation model:
                                      # 'linear' (burn at vDet) |
                                      # 'none' (instant)
    #: optional, aligned with det_points (N5-12): per-point ignition
    #: delay [s] and initiation radius [m]. None = all zero, blastFoam's
    #: own defaults. Guide 5.6.1: valid for any activation model.
    det_delays: list = None
    det_radii: list = None
    afterburn: str = 'none'           # blastFoam afterburn model:
                                      # 'none' | 'miller' (products
                                      # burning with atmospheric oxygen)
    #: native reconstruction order (T47/N10): 1 = the pinned Godunov
    #: path, 2 = opt-in limited MUSCL (native solvers only)
    order: int = 1
    #: blastProbes `adjustLocations`. A no-op for every gauge we write:
    #: it relocates only probes found in NO cell (blastProbes.C:218),
    #: and ours are interior. T40 measured it - arrival moves 0.15 pp
    #: with it off - and DONE.md records the old reading as REFUTED.
    probe_adjust: bool = True
    adaptive_write: bool = True       # see Case1D.adaptive_write (B23)
    write_budget: int = 0             # see Case2D.write_budget (HD1-15)
    n_procs: int = 0                  # blastFoam MPI ranks (0 = auto)
    charges: list = None              # blastFoam: ADDITIONAL charges
                                      # [(x, y, z, mass_kg), ...] on top
                                      # of the primary charge/center
    det_points: list = None           # blastFoam: detonation points
                                      # [(x, y, z), ...]; None = every
                                      # charge centre
    #: see Case2D.vtk_surfaces; in 3D the sections are the live-slice
    #: plane plus the `planes` rows [[axis, position m], ...]
    vtk_surfaces: dict = None
    vtk_volumes: dict = None
    vtk_gauges: dict = None           # see Case1D.vtk_gauges (OUT-4a)
    keep_all_fields: bool = False     # see Case1D.keep_all_fields (OUT-3)


_CASE_TYPES = {1: Case1D, 2: Case2D, 3: Case3D}


def case_to_dict(case):
    """The case as a JSON-ready dict, stamped with schema, version and dim."""
    d = asdict(case)
    # HD1-15: an unset write budget is not written at all. A case without
    # one then serialises byte for byte as it always has and VERSION stays
    # 13 - which keeps every saved case.json, and the HD1-3d evidence
    # identity check that compares one key for key, as they were. (An
    # older blastlab refuses a file that HAS a budget: "Unknown case keys".)
    if not d.get('write_budget'):
        d.pop('write_budget', None)
    # OUT-2: the same for the VTK families - None, or switched off with
    # no field ticked, is not written, so VERSION stays 13 and every case
    # without them is byte-identical (an older blastlab refuses one that
    # has them). A family switched OFF that still has ticked fields IS
    # written, `on: false` and all (owner decision P15, 2026-09-27), so
    # a reload restores the card's ticks; the solver ignores it
    # (vtk_family reads `on`).
    for key in ('vtk_surfaces', 'vtk_volumes'):
        if key in d and not vtk_written(d[key]):
            d.pop(key)
    # OUT-4a: the gauge extras, the same way - omitted when none is ticked
    g = d.get('vtk_gauges')
    if not (isinstance(g, dict) and g.get('fields')):
        d.pop('vtk_gauges', None)
    # OUT-3: the same for the "Keep all fields in WSL" box
    if not d.get('keep_all_fields'):
        d.pop('keep_all_fields', None)
    d['schema'] = SCHEMA
    d['version'] = VERSION
    d['dim'] = case.dim
    return d


#: case_from_dict's refusal of another schema (`load_any_case` keys on it)
NOT_A_CASE = "Not a blastlab case file"


def case_from_dict(d):
    """Case1D/2D/3D from a `case_to_dict` dict (or its JSON round trip).

    Refuses another schema, a newer version and unknown keys; restores
    the tuples JSON turned into lists and normalises boundary kinds."""
    d = dict(d)
    if d.pop('schema', SCHEMA) != SCHEMA:
        raise ValueError(NOT_A_CASE)
    if d.pop('version', VERSION) > VERSION:
        raise ValueError("Case file from a newer blastlab version")
    dim = d.pop('dim')
    cls = _CASE_TYPES[int(dim)]
    if int(dim) == 1:
        # T63: the 1D trigger gauge was removed. Case files written
        # before that still carry the three keys, and refusing to load
        # them would strand every saved 1D case and run (post-mortem
        # reads case.json) - drop them instead.
        for _k in ('trigger_gauge', 'trigger_action', 'trigger_file'):
            d.pop(_k, None)
    fields = {f for f in cls.__dataclass_fields__}
    unknown = set(d) - fields
    if unknown:
        raise ValueError(f"Unknown case keys: {sorted(unknown)}")
    case = cls(**d)
    if hasattr(case, 'center') and case.center is not None:
        case.center = tuple(case.center)
    if getattr(case, 'bcs', None):
        case.bcs = normalize_bcs(case.bcs)
    if hasattr(case, 'obstacles'):
        case.obstacles = [tuple(o) for o in case.obstacles]
    if getattr(case, 'refine_zones', None):
        case.refine_zones = [(*[float(v) for v in z[:-1]],
                              int(round(float(z[-1]))))
                             for z in case.refine_zones]
    for fld in ('amr_levels', 'amr_interval', 'amr_buffer', 'amr_max_cells'):
        if hasattr(case, fld):
            setattr(case, fld, int(getattr(case, fld) or 0))
    if getattr(case, 'amr_display_level', None) is not None:
        case.amr_display_level = int(case.amr_display_level)
    if hasattr(case, 'gauges'):
        case.gauges = [tuple(g) if isinstance(g, (list, tuple)) else g
                       for g in case.gauges]
    for fld in ('charges', 'det_points'):
        if getattr(case, fld, None):
            setattr(case, fld, [tuple(v) for v in getattr(case, fld)])
    # JSON has no tuples: the animation colour range comes back a list
    if getattr(case, 'anim_clim', None) is not None:
        case.anim_clim = tuple(float(v) for v in case.anim_clim)
    for key in ('vtk_surfaces', 'vtk_volumes'):
        if hasattr(case, key):
            setattr(case, key, normalize_vtk(getattr(case, key), key))
    case.vtk_gauges = normalize_vtk_gauges(case.vtk_gauges)
    case.keep_all_fields = bool(case.keep_all_fields)
    return case


def save_case(case, path):
    """Write the case to `path` as indented JSON."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(case_to_dict(case), f, indent=2)


def load_case(path):
    """Read a case file; a relative `profile_file_in` is taken relative
    to the case file's own folder."""
    with open(path, encoding='utf-8') as f:
        case = case_from_dict(json.load(f))
    # profile paths are stored as given; resolve relative to the case file
    base = os.path.dirname(os.path.abspath(path))
    if getattr(case, 'profile_file_in', None):
        if not os.path.isabs(case.profile_file_in):
            case.profile_file_in = os.path.join(base, case.profile_file_in)
    return case


def load_any_case(path):
    """What Open case reads: a blast case (`load_case`) or, for a file
    that `load_case` refuses as another schema, an HD 1.3 case
    (`models.hd13_case.load_case`, a DeflagrationCase with dim 0). OUT-1
    writes one into every HD 1.3 model folder (GUI QA 2026-09-26 F2). A
    file neither loader reads keeps `load_case`'s error."""
    try:
        return load_case(path)
    except ValueError as exc:
        if str(exc) != NOT_A_CASE:
            raise
        from . import hd13_case
        try:
            return hd13_case.load_case(path)
        except ValueError as exc13:
            if str(exc13).startswith('not an HD 1.3 case file'):
                raise exc from None
            raise


def material_rho0(case):
    """rho0 of the case's material under ITS solver - the same lookup
    validate_case performs, exposed so the setup preview can plan with
    it (N2-07: preview_panel used to call plan_levels with NO rho0,
    which defaults to TNT's 1630 - so for any other material the
    preview drew a different mesh than the one validate_case reported
    and the writer built; measured on ANFO: a whole extra refinement
    level and a finest cell 2x too small, while the strip on the same
    screen showed the correct numbers). Returns None when the material
    is unknown to the table - callers then fall back to plan_levels'
    TNT default, and validation is already erroring about the material
    itself. Both solvers read the same table (N11/T46: the native
    solvers take their JWL set from blastFoam's material table), so one
    lookup serves either."""
    material = getattr(case, 'material', 'TNT') or 'TNT'
    try:
        from ..core.materials import MATERIALS
        return float(MATERIALS[material].rho0)
    except (KeyError, ImportError, AttributeError):
        return None


def fmt_cells(n):
    """Cell counts for messages: thousands separators while the number is
    readable, scientific once it is not. `cell = 1e-9` on a 4 m domain
    used to print ~15,999,999,992,000,000,001 in the middle of a sentence
    (N2-06); nobody counts twenty digits, '1.6e+19' is the information."""
    n = int(n)
    return f'{n:,}' if n < 10 ** 9 else f'{n:.3g}'
