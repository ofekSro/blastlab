"""HD1-3a: a room, as obstacle boxes.

THE DECISION THIS MODULE RESTS ON
---------------------------------
The original route for `HD1-3` put the chamber OUTSIDE the mesh and
drove `p(t)` from the 0-D model in at the opening as a time-varying
boundary condition. That needed machinery this repository has none of -
no `Function1`, no `uniformFixedValue`, no `tableFile` anywhere - and
the guide documents exactly one time-varying condition, `codedFixedValue`,
while warning that the boundary is used to BUILD the conserved
quantities, so `p`, `T` and `rho` would all have to be driven together
and consistently or the reconstructed face state is wrong.

Putting the room INSIDE the mesh deletes all of it. blastFoam computes
the blowdown itself, and the 0-D model's only remaining job is the
state at the instant the vent opens. No new boundary kind, no separate
patch for the opening, no `createPatch`, no `createBaffles`, no mesh
stage: **the opening is a hole between wall boxes, which is to say
fluid**, and the walls are ordinary obstacles carved by the existing
`topoSet` + `subsetMesh -patch obstacles` path.

So this module writes boxes. That is the whole of it.

WHY THE SNAPPED NUMBERS ARE THE ONLY ONES WORTH HAVING
------------------------------------------------------
`refine.snap_obstacles` moves every obstacle edge OUTWARD onto a
base-cell face, so the carve and foam's `boxToCell` agree cell-for-cell
rather than by float luck. For a room that has a consequence the entered
numbers do not show: every wall grows outward, so **the cavity shrinks
and the opening shrinks**, both by up to one base cell per face. On a
5 m room at `dx = 0.1` that is around 10 % of the volume - five times
the 2 % tolerance `check_handoff_energy` runs at, so a hand-off built on
the entered volume would fail, or worse, pass carrying the wrong energy.

Hence `measure`: the volume and the vent area are read back from the
SNAPPED boxes, and the difference from what was asked for is reported
rather than absorbed.

AND REPORTING IT IS NOT ENOUGH, which is why `align` exists. A 27.6 %
error in the vent area means the CFD is solving a DIFFERENT HOLE from
the one that was asked for, and `_e2e_vent_2d.py` compares its mass flow
against `deflagration._vent_mdot` at a pre-registered 15 %. An error
almost twice the threshold does not get argued about - it gets absorbed
into the discharge coefficient, which is an estimate anyway, and is
never seen again. So every edge goes onto a base-cell face BEFORE the
boxes are built, snapping has nothing left to move, and the area that
gets solved is the area reported.

**The 0-D side of that comparison must use the POST-ALIGNMENT vent area
and cavity volume**, which `measure` returns. Running it against the
numbers typed into the case would either fail the check for a reason
that has nothing to do with the physics, or pass it while measuring the
wrong thing. The hand-off that follows conserves mass and
energy and lets pressure come out of the EOS on the real volume - a
cavity 10 % smaller simply arrives at a higher pressure, which is what
the physics requires.

The snapped interior is computed from the snapped wall boxes directly
rather than by labelling a mask: each wall snaps outward, so the cavity
is exactly the box between their inner faces. Exact, and it costs
nothing.
"""

import math

from . import refine as _refine

#: Faces a vent can be cut in, and the two in-plane axes of each.
FACES = {
    'x_lo': (1, 2), 'x_hi': (1, 2),
    'y_lo': (0, 2), 'y_hi': (0, 2),
    'z_lo': (0, 1), 'z_hi': (0, 1),
}
AXIS_NAME = ('x', 'y', 'z')

#: A jet needs this many base cells across the opening before its mass
#: flow is worth anything. Six is the documented floor and it buys the
#: FLOW RATE, not the jet structure: an orifice passes the right mass at
#: a coarse resolution, while the shear layers and shock cells in the
#: near field need far more. So a load on a distant structure is valid
#: at six and the picture near the opening is qualitative. Enforced here
#: rather than at run time, because discovering it after a 4M-cell mesh
#: has been built is discovering it too late.
MIN_VENT_CELLS = 6

#: AND SIX IS NOT ENOUGH FOR A DISCHARGE COEFFICIENT, which is a
#: stronger requirement than the flow rate above and was MEASURED rather
#: than argued. `_e2e_vent_verify.py` compared the 0-D orifice law
#: against blastFoam on one opening at two meshes:
#:
#:     6 cells across    Cd_eff = 0.7227
#:     12 cells across   Cd_eff = 0.8102
#:
#: 12.1 % apart, past the 10 % registered before the run. The coarse
#: mesh passes LESS, which is numerical dissipation in the opening. So a
#: run that reports a load on a structure needs twelve, and
#: `assessment.validate` refuses fewer. Even at twelve the CFD's flow
#: may still be up to ~10 % below the converged value, and the direction
#: is known: less out, so a slightly weak jet.
MIN_VENT_CELLS_LOAD = 12

#: A wall thinner than one base cell cannot be carved at all - it would
#: snap to a single cell layer or vanish. Also enforced here.
MIN_WALL_CELLS = 1


def _box(lo, hi):
    """(x0,x1,y0,y1,z0,z1) from two corner triples."""
    return (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])


def _round(v, dx):
    return round(v / dx) * dx


def align(origin, size, wall, dx, vent=None):
    """Move the room onto the mesh BEFORE building it, not after.

    THE REASON THIS EXISTS. `measure` reports what snapping costs, and on
    an off-grid 5 m room at dx = 0.1 that is 10.5 % of the cavity and
    27.6 % of the opening. Reporting it is necessary and not sufficient:
    a 27.6 % error in the vent area means the CFD is solving a DIFFERENT
    HOLE from the one that was asked for, and the 2-D verification is
    pre-registered at 15 %, so the difference would be argued into the
    discharge coefficient and never seen again.

    Measuring a problem is not the same as not having it. So every edge -
    the outer faces, the wall thickness and the vent - is put on a
    base-cell face first. `snap_obstacles` then has nothing left to move,
    the area that gets solved IS the area reported, and what changed is
    reported once, here, against what was typed.

    Returns (origin, size, wall, vent, report). `report` carries the
    per-quantity shifts and any `errors` that rounding could not fix.
    """
    dx = float(dx)
    if dx <= 0:
        raise ValueError('base cell size must be positive')
    o_in = [float(v) for v in origin]
    s_in = [float(v) for v in size]
    w_in = float(wall)

    o = [_round(v, dx) for v in o_in]
    hi = [_round(o_in[i] + s_in[i], dx) for i in range(3)]
    # a room must not round away to nothing
    for i in range(3):
        if hi[i] - o[i] < 3.0 * dx:
            hi[i] = o[i] + 3.0 * dx
    s = [hi[i] - o[i] for i in range(3)]
    w = max(_round(w_in, dx), dx)       # never thinner than one cell
    while any(s[i] <= 2.0 * w + dx for i in range(3)) and w > dx:
        w -= dx

    report = {
        'dx': dx,
        'origin_shift': tuple(o[i] - o_in[i] for i in range(3)),
        'size_shift': tuple(s[i] - s_in[i] for i in range(3)),
        'wall_shift': w - w_in,
        'vent_shift': (0.0, 0.0),
        'vent_area_entered': 0.0,
        'vent_area_aligned': 0.0,
        'vent_area_shift': 0.0,
        'errors': [],
        'moved': False,
    }
    v_out = None
    if vent is not None:
        face, a0, a1, b0, b1 = vent
        if face not in FACES:
            raise ValueError(f'face must be one of {tuple(FACES)}, '
                             f'not {face!r}')
        ia, ib = FACES[face]
        report['vent_area_entered'] = (float(a1) - float(a0)) \
            * (float(b1) - float(b0))
        edges = []
        for idx, c0, c1 in ((ia, float(a0), float(a1)),
                            (ib, float(b0), float(b1))):
            e0, e1 = _round(c0, dx), _round(c1, dx)
            # at least MIN_VENT_CELLS across, grown about the centre so
            # the opening stays where it was asked to be
            if e1 - e0 < MIN_VENT_CELLS * dx - 1e-9:
                mid = _round(0.5 * (e0 + e1), dx)
                half = MIN_VENT_CELLS * dx / 2.0
                e0, e1 = _round(mid - half, dx), _round(mid + half, dx)
            # strictly inside the face, with a cell of wall left either
            # side - a vent that reaches an edge cuts the wall through
            lo_lim, hi_lim = o[idx] + dx, o[idx] + s[idx] - dx
            if e0 < lo_lim:
                e1 += lo_lim - e0
                e0 = lo_lim
            if e1 > hi_lim:
                e0 -= e1 - hi_lim
                e1 = hi_lim
            if e0 < lo_lim or e1 - e0 < MIN_VENT_CELLS * dx - 1e-9:
                report['errors'].append(
                    f'the opening cannot be fitted into the {face} face '
                    f'at dx = {dx:g}: it needs {MIN_VENT_CELLS} cells '
                    f'across plus a cell of wall either side, which is '
                    f'{(MIN_VENT_CELLS + 2) * dx:g} m, and that face is '
                    f'{s[idx]:g} m in {AXIS_NAME[idx]}.')
            edges.append((e0, e1))
        (na0, na1), (nb0, nb1) = edges
        v_out = (face, na0, na1, nb0, nb1)
        report['vent_area_aligned'] = (na1 - na0) * (nb1 - nb0)
        report['vent_shift'] = (
            (na1 - na0) - (float(a1) - float(a0)),
            (nb1 - nb0) - (float(b1) - float(b0)))
        if report['vent_area_entered'] > 0:
            report['vent_area_shift'] = (report['vent_area_aligned']
                                         / report['vent_area_entered'] - 1.0)

    report['moved'] = (
        any(abs(v) > 1e-12 for v in report['origin_shift'] + report['size_shift'])
        or abs(report['wall_shift']) > 1e-12
        or any(abs(v) > 1e-12 for v in report['vent_shift']))
    return tuple(o), tuple(s), w, v_out, report


def room_parts(origin, size, wall, vent=None, floor=False):
    """`room_boxes`, but keyed by which part of the shell each box is.

    The names are what makes `measure` exact. The cavity after snapping
    is the box between the INNER faces of the six walls, and knowing
    which box is the `x_lo` wall is the whole of that - reading it off
    the geometry does not work, because the `x_lo` wall spans the entire
    y and z range and so touches y = 0 exactly as the `y_lo` wall does.
    """
    return _parts(origin, size, wall, vent=vent, floor=floor)


def room_boxes(origin, size, wall, vent=None, floor=False):
    """Obstacle boxes whose union is the SHELL of a room.

    `origin`  outer corner (x0, y0, z0) [m]
    `size`    outer extent (Lx, Ly, Lz) [m]
    `wall`    wall thickness [m], the same on every face
    `vent`    None, or (face, a0, a1, b0, b1) - a rectangular hole in
              `face`, given in that face's two in-plane axes in
              increasing axis order (see FACES). The wall it is cut in
              splits into four pieces around it.
    `floor`   include a floor slab. Usually False: the ground is a
              reflecting boundary (`z_lo='reflect'`) and a slab under the
              room would only be cells that never do anything.

    Returns a list of (x0,x1,y0,y1,z0,z1), ready for `case.obstacles`.
    Nothing here knows about meshes - see `measure` for what the mesh
    does to these numbers.
    """
    return list(_parts(origin, size, wall, vent=vent, floor=floor).values())


def _parts(origin, size, wall, vent=None, floor=False):
    o = [float(v) for v in origin]
    s = [float(v) for v in size]
    w = float(wall)
    if len(o) != 3 or len(s) != 3:
        raise ValueError('origin and size are three numbers each')
    if w <= 0.0:
        raise ValueError('wall thickness must be positive')
    if any(v <= 0.0 for v in s):
        raise ValueError('room size must be positive in every direction')
    if any(v <= 2.0 * w for v in s):
        raise ValueError(
            f'walls {w:g} m thick leave no cavity inside a '
            f'{s[0]:g} x {s[1]:g} x {s[2]:g} m room - the outer size is '
            f'OUTER, so each direction needs more than twice the wall')
    hi = [o[i] + s[i] for i in range(3)]
    inner_lo = [o[i] + w for i in range(3)]
    inner_hi = [hi[i] - w for i in range(3)]

    # The shell, as slabs. Each slab is full-extent in the directions
    # already covered by a previous slab, so the union has no overlap
    # and no gap: x walls take the whole y-z face, y walls take what is
    # left in x, the roof and floor take what is left in both.
    boxes = {
        'x_lo': _box((o[0], o[1], o[2]), (inner_lo[0], hi[1], hi[2])),
        'x_hi': _box((inner_hi[0], o[1], o[2]), (hi[0], hi[1], hi[2])),
        'y_lo': _box((inner_lo[0], o[1], o[2]), (inner_hi[0], inner_lo[1],
                                                 hi[2])),
        'y_hi': _box((inner_lo[0], inner_hi[1], o[2]), (inner_hi[0], hi[1],
                                                        hi[2])),
        'z_hi': _box((inner_lo[0], inner_lo[1], inner_hi[2]),
                     (inner_hi[0], inner_hi[1], hi[2])),
    }
    if floor:
        boxes['z_lo'] = _box((inner_lo[0], inner_lo[1], o[2]),
                             (inner_hi[0], inner_hi[1], inner_lo[2]))

    if vent is None:
        return boxes

    face, a0, a1, b0, b1 = vent
    if face not in FACES:
        raise ValueError(f'face must be one of {tuple(FACES)}, not {face!r}')
    if face not in boxes:
        raise ValueError(
            f"there is no {face!r} wall to cut a vent in - the room was "
            f"built without a floor, so z_lo is open ground already")
    a0, a1, b0, b1 = float(a0), float(a1), float(b0), float(b1)
    if a1 <= a0 or b1 <= b0:
        raise ValueError('a vent needs positive extent in both directions')
    ia, ib = FACES[face]
    # STRICTLY inside the face. A vent that reaches an edge cuts the wall
    # through rather than making a hole in it, and the four-piece split
    # degenerates. Refusing is better than silently emitting a
    # zero-thickness box that the carve will drop.
    for idx, (lo, hi_) in ((ia, (a0, a1)), (ib, (b0, b1))):
        if lo <= o[idx] or hi_ >= o[idx] + s[idx]:
            raise ValueError(
                f'the vent must lie strictly inside the {face} face: '
                f'{AXIS_NAME[idx]} runs {lo:g} to {hi_:g} against a face '
                f'spanning {o[idx]:g} to {o[idx] + s[idx]:g}. A vent that '
                f'touches an edge cuts the wall through instead of making '
                f'a hole in it.')

    # Split that wall into four pieces around the hole: two full-width
    # bands below and above it in axis `ib`, and two side pieces filling
    # the rest of axis `ia` at the hole's own level.
    slab = boxes.pop(face)
    lo = [slab[0], slab[2], slab[4]]
    up = [slab[1], slab[3], slab[5]]

    def piece(**edges):
        p_lo, p_up = list(lo), list(up)
        for k, v in edges.items():
            axis = AXIS_NAME.index(k[0])
            if k.endswith('_lo'):
                p_lo[axis] = v
            else:
                p_up[axis] = v
        return _box(p_lo, p_up)

    na, nb = AXIS_NAME[ia], AXIS_NAME[ib]
    boxes[f'{face}:below'] = piece(**{f'{nb}_hi': b0})
    boxes[f'{face}:above'] = piece(**{f'{nb}_lo': b1})
    boxes[f'{face}:side_lo'] = piece(**{f'{nb}_lo': b0, f'{nb}_hi': b1,
                                        f'{na}_hi': a0})
    boxes[f'{face}:side_hi'] = piece(**{f'{nb}_lo': b0, f'{nb}_hi': b1,
                                        f'{na}_lo': a1})
    return boxes


def measure(origin, size, wall, dx_base, vent=None, floor=False,
            align_first=True):
    """What the MESH will make of the room asked for.

    `align_first` puts every edge on a base-cell face BEFORE the boxes
    are built, so `snap_obstacles` has nothing left to move and the area
    that gets solved IS the area reported. It defaults ON, because
    reporting a 27.6 % error in the vent area is not the same as not
    having one - see `align`. Pass False to see what the room would have
    cost without it, which is what `test_room.py` does to show why this
    is on.

    Returns a dict with

        boxes             the obstacle boxes, unsnapped, for the case
        snapped           the same after `refine.snap_obstacles`
        volume            cavity volume AFTER snapping [m3] - the number
                          the 0-D model should be run at
        volume_entered    what the outer/wall numbers imply
        volume_shift      snapped/entered - 1, signed
        vent_area         opening area AFTER snapping [m2]
        vent_area_entered
        vent_area_shift
        vent_cells        cells across the snapped opening, per axis
        wall_cells        wall thickness in base cells, rounded down
        errors            constraints a mesh cannot fix, as strings
        warnings          things that moved enough to matter

    `errors` being non-empty means do not build this case: the wall
    cannot be carved or the opening cannot carry a jet. Both are cheap
    to say now and expensive to discover after a 4M-cell mesh.
    """
    dx = float(dx_base)
    if dx <= 0.0:
        raise ValueError('base cell size must be positive')
    asked = ((tuple(float(v) for v in origin),
              tuple(float(v) for v in size), float(wall), vent))
    align_report = None
    if align_first:
        origin, size, wall, vent, align_report = align(
            origin, size, wall, dx, vent=vent)
        if align_report['errors']:
            # Alignment could not fit the room onto this mesh, so there
            # is nothing to build. Return the reason rather than letting
            # `_parts` raise on geometry that alignment already knows is
            # impossible - the caller asked what the mesh would make of
            # this room, and "it cannot" is the answer.
            return {
                'boxes': [], 'parts': {}, 'snapped': [], 'moved': [],
                'aligned': True, 'align': align_report, 'asked': asked,
                'n_boxes': 0, 'n_shell_expected': 0,
                'volume': 0.0, 'volume_entered': 0.0, 'volume_shift': 0.0,
                'cavity_lo': (0.0, 0.0, 0.0), 'cavity_hi': (0.0, 0.0, 0.0),
                'vent_area': 0.0, 'vent_area_entered': 0.0,
                'vent_area_shift': 0.0, 'vent_cells': (),
                'wall_cells': 0, 'dx_base': dx,
                'errors': list(align_report['errors']),
                'warnings': [], 'ok': False,
            }
    parts = _parts(origin, size, wall, vent=vent, floor=floor)
    names = list(parts)
    boxes = [parts[k] for k in names]
    snapped_list, moved = _refine.snap_obstacles(boxes, dx, 3)
    snapped = dict(zip(names, snapped_list))

    o = [float(v) for v in origin]
    s = [float(v) for v in size]
    w = float(wall)

    # THE SNAPPED CAVITY, straight off the snapped walls BY NAME. Each
    # wall snaps outward, so the inner face of the x_lo wall is its
    # snapped x1 and the inner face of the x_hi wall is its snapped x0 -
    # the cavity is exactly the box between them. No mask, no labelling,
    # exact. Reading it off the geometry instead does NOT work: the x_lo
    # wall spans the whole y range, so it touches y = 0 exactly as the
    # y_lo wall does, and "the box at y = 0" is ambiguous.
    n_shell = (6 if floor else 5) + (3 if vent is not None else 0)

    def wall_of(face):
        if face in snapped:
            return snapped[face]
        # the vented wall, split - every piece keeps the wall's own
        # extent in the face-normal direction, so any of them will do
        for k, b in snapped.items():
            if k.startswith(face + ':'):
                return b
        return None

    lo_s, hi_s = [], []
    for axis in range(3):
        lo_b = wall_of(f'{AXIS_NAME[axis]}_lo')
        hi_b = wall_of(f'{AXIS_NAME[axis]}_hi')
        # No floor means open ground: the cavity runs down to the domain
        # boundary, which is a reflecting plane and not a slab of cells.
        lo_s.append(lo_b[2 * axis + 1] if lo_b is not None else o[axis])
        hi_s.append(hi_b[2 * axis] if hi_b is not None
                    else o[axis] + s[axis])
    vol = max(0.0, (hi_s[0] - lo_s[0]) * (hi_s[1] - lo_s[1])
              * (hi_s[2] - lo_s[2]))
    vol_entered = ((s[0] - 2 * w) * (s[1] - 2 * w)
                   * ((s[2] - 2 * w) if floor else (s[2] - w)))

    errors, warnings = [], []
    wall_cells = int(math.floor(w / dx + 1e-9))
    if wall_cells < MIN_WALL_CELLS:
        errors.append(
            f'a {w:g} m wall is under one {dx:g} m base cell, so it cannot '
            f'be carved: it would snap to a single cell layer or vanish. '
            f'Thicken the wall or refine the base mesh.')

    vent_area = vent_area_entered = 0.0
    vent_cells = ()
    if vent is not None:
        face, a0, a1, b0, b1 = vent
        ia, ib = FACES[face]
        a0, a1, b0, b1 = float(a0), float(a1), float(b0), float(b1)
        vent_area_entered = (a1 - a0) * (b1 - b0)
        # The four pieces snap outward INTO the hole, so the opening is
        # bounded by their snapped inner edges and can only shrink. Again
        # by name: `side_lo` gives the low edge in the first in-plane
        # axis, `below` the low edge in the second, and so on.
        side_lo = snapped[f'{face}:side_lo']
        side_hi = snapped[f'{face}:side_hi']
        below = snapped[f'{face}:below']
        above = snapped[f'{face}:above']
        span = (max(0.0, side_hi[2 * ia] - side_lo[2 * ia + 1]),
                max(0.0, above[2 * ib] - below[2 * ib + 1]))
        vent_area = span[0] * span[1]
        vent_cells = tuple(int(round(v / dx)) for v in span)
        if any(c < MIN_VENT_CELLS for c in vent_cells):
            errors.append(
                f'the opening is {vent_cells[0]} x {vent_cells[1]} base '
                f'cells after snapping and needs at least '
                f'{MIN_VENT_CELLS} across each way, or the jet through it '
                f'is not represented. Widen the vent or refine the mesh.')
        elif vent_area_entered > 0 and \
                abs(vent_area / vent_area_entered - 1.0) > 0.05:
            warnings.append(
                f'snapping moved the opening from '
                f'{vent_area_entered:.4f} to {vent_area:.4f} m2 '
                f'({vent_area / vent_area_entered - 1.0:+.1%}). The 0-D '
                f'vent flow must use the SNAPPED area, or the two models '
                f'are solving different holes.')

    shift = (vol / vol_entered - 1.0) if vol_entered > 0 else 0.0
    if abs(shift) > 0.02:
        warnings.append(
            f'snapping moved the cavity from {vol_entered:.4f} to '
            f'{vol:.4f} m3 ({shift:+.1%}) - past the 2 % the hand-off '
            f'energy check runs at. This is not a fault: the hand-off '
            f'conserves mass and energy and lets pressure follow from the '
            f'EOS on the real volume, so a smaller cavity simply arrives '
            f'at a higher pressure. Run the 0-D model at {vol:.4f} m3.')

    if align_report is not None:
        errors.extend(align_report['errors'])
        if align_report['moved']:
            warnings.append(
                f'the room was put on the mesh before it was built: the '
                f'walls moved {max(abs(v) for v in align_report["size_shift"]) * 1e3:.0f} mm '
                f'at most and the opening '
                f'{align_report["vent_area_shift"]:+.1%}. That rounding is '
                f'reported once, here, and nothing moves afterwards - the '
                f'area that gets solved IS the area above. Run the 0-D '
                f'model at this volume and this vent area.')
        if moved:
            errors.append(
                'alignment was asked for and snapping still moved a box, '
                'which means an edge is off the base grid after align(). '
                'That is a bug in align(), not a property of the room.')

    return {
        'boxes': boxes,
        'parts': parts,
        'snapped': snapped,
        'moved': moved,
        'aligned': align_first,
        'align': align_report,
        'asked': asked,
        'n_boxes': len(boxes),
        'n_shell_expected': n_shell,
        'volume': vol,
        'volume_entered': vol_entered,
        'volume_shift': shift,
        'cavity_lo': tuple(lo_s),
        'cavity_hi': tuple(hi_s),
        'vent_area': vent_area,
        'vent_area_entered': vent_area_entered,
        'vent_area_shift': ((vent_area / vent_area_entered - 1.0)
                            if vent_area_entered > 0 else 0.0),
        'vent_cells': vent_cells,
        'wall_cells': wall_cells,
        'dx_base': dx,
        'errors': errors,
        'warnings': warnings,
        'ok': not errors,
    }
