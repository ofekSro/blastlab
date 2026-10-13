"""GUI-5 (plan §5.3): the scaled distance of a gauge, for display only.

    Z = R / W^(1/3)

UFC 3-340-02 (2008), para. 2-13.1 (Free Air Burst), printed p. 44 (PDF
page 120 of docs/references/ufc_3_340_02.pdf): the blast-wave parameters
of a spherical TNT explosion "are given in Figure 2-7 versus the scaled
distance (Z = R/W1/3)". The document writes Z in ft/lb^1/3; the app
shows it in SI, m/kg^1/3 (plan §5.3) - R in metres, W in kilograms.

R is the distance from the burst point to the gauge in the plane of the
case: 1D spherical, the gauge radius r; 2D axisymmetric, (r, z) with the
burst on the axis; 3D, (x, y, z). W is the charge mass AS ENTERED in the
form - kilograms of the selected material, not a TNT equivalent (TODO
P1-9), so Z changes with W only, never with the material. 3D extra
charges are not part of W.

Z is None (the GUI hides it) for planar 2D (the charge is per metre of
depth, so R/W^(1/3) is not the spherical scaled distance), for a case
that starts from a profile (no charge is placed), for 0-D, and for
W <= 0. Nothing here is exported or written to any file; the one number
the Setup screen shows beside it, the charge radius, is read from the
validation report, never recomputed.

One source for GUI-5a (the Derived card) and GUI-5b (the strip tile,
the gauge table, the rings). The gauge table's Where column (the
nearest obstacle face within 0.5 m) is here too: plain geometry of the
case as entered, display only.
"""

import math
from types import SimpleNamespace

#: the column / tile label everywhere (plan §5.3)
LABEL = 'Z [m/kg^1/3]'
#: UXR-15 (D221): the tooltip wherever a Z value is shown without its
#: unit. UFC 3-340-02 (2008), para. 2-13.1, printed p. 44: Z = R/W^1/3
UNIT_TIP = ('Z = R / W^(1/3): the scaled distance, in m/kg^1/3 '
            '(UFC 3-340-02, para. 2-13.1). R in m from the burst, W the '
            'charge in kg as entered.')


def case_from_meta(meta, dim, gauge_out=None):
    """A case-like view of a finished result, for its Z on the Results
    screen (GUI-7 T5): display only, no new formula - the functions below
    read it exactly as they read a Case.

    Read from `meta`: `charge` (2D/3D) or `charge_kg` (1D),
    `charge_center`, `geometry` (2D), `from_profile` and `gauges` (the
    positions as entered). A 1D meta keeps no gauge list, so the radii of
    the result's own `gauge_out` stand in for it. `dx` (when present) is
    the snapping tolerance of `run_gauges.match_gauges`.

    None when any of those is missing: Z is then hidden, never guessed."""
    meta = meta or {}
    try:
        if dim == 1:
            radii = (gauge_out or {}).get('radii')
            if 'charge_kg' not in meta or radii is None:
                return None
            return SimpleNamespace(
                dim=1, charge_kg=meta['charge_kg'], init_mode='charge',
                gauge_radii=[float(r) for r in radii], cell_size_m=0.0,
                trigger_gauge=meta.get('trigger_gauge'))
        if dim not in (2, 3):
            return None
        need = ('charge', 'charge_center', 'from_profile', 'gauges')
        if dim == 2:
            need += ('geometry',)
        if any(k not in meta for k in need):
            return None
        return SimpleNamespace(
            dim=dim, charge=meta['charge'],
            center=tuple(meta['charge_center']),
            geometry=meta.get('geometry'),
            init_mode='profile' if meta['from_profile'] else 'charge',
            gauges=[tuple(g) for g in (meta['gauges'] or [])],
            cell_size_m=float(meta.get('dx') or 0.0),
            trigger_gauge=meta.get('trigger_gauge'))
    except (TypeError, ValueError):
        return None


def charge_mass(case):
    """W [kg] as entered: Case1D.charge_kg, Case2D/3D.charge."""
    if case.dim == 1:
        return float(case.charge_kg)
    return float(case.charge)


def burst_point(case):
    """The burst point in the case's own coordinates: 1D (0,); 2D
    axisymmetric (0, z) - the burst sits on the axis; planar (x, y);
    3D (x, y, z)."""
    if case.dim == 1:
        return (0.0,)
    if case.dim == 2:
        x0 = 0.0 if case.geometry == 'axisymmetric' else case.center[0]
        return (float(x0), float(case.center[1]))
    return tuple(float(c) for c in case.center[:3])


def gauge_points(case):
    """The gauges as tuples in the same coordinates as burst_point."""
    if case.dim == 1:
        return [(float(r),) for r in (case.gauge_radii or [])]
    return [tuple(float(c) for c in g) for g in (case.gauges or [])]


def outside_domain(case, point):
    """True when `point` lies outside the closed domain 0 <= v <= L on
    any axis - the solvers' own test (solver2d.py 283, solver3d.py 341,
    validation `_validate_closing`). 1D: outside 0 < r <= radius_m, the
    solvers' own test too (solver1d.py, foam/writer.py; GUI-15 (f), D9).
    False for a case without extents (the Results screen's meta view).
    One test for Setup's Where column and Run's dropped-gauge note
    (GUI-14 d, D2)."""
    if getattr(case, 'dim', None) == 1:
        radius = getattr(case, 'radius_m', None)
        try:
            return radius is not None and not (
                0.0 < float(point[0]) <= float(radius))
        except (TypeError, ValueError, IndexError):
            return False
    dims = [getattr(case, k, None) for k in ('Lx', 'Ly', 'Lz')[:len(point)]]
    try:
        return (all(d is not None for d in dims) and any(
            not 0.0 <= float(v) <= float(d) for v, d in zip(point, dims)))
    except (TypeError, ValueError):
        return False


def z_shown(case):
    """True when Z means something for this case (see the module
    docstring for when it does not)."""
    dim = getattr(case, 'dim', None)
    if dim not in (1, 2, 3):
        return False
    if dim == 2 and case.geometry != 'axisymmetric':
        return False
    if dim > 1 and getattr(case, 'init_mode', 'charge') != 'charge':
        return False
    try:
        return charge_mass(case) > 0
    except (TypeError, ValueError):
        return False


def distance(case, point):
    """R [m] from the burst point to `point`."""
    b = burst_point(case)
    if case.dim == 1:
        return abs(float(point[0]))
    return math.sqrt(sum((float(p) - q) ** 2 for p, q in zip(point, b)))


def scaled_distance(case, point):
    """Z [m/kg^1/3] of `point`, or None when Z is hidden."""
    if not z_shown(case):
        return None
    return distance(case, point) / charge_mass(case) ** (1.0 / 3.0)


def ring_radius(case, z):
    """R [m] at which the scaled distance is `z`: R = Z · W^(1/3), W as
    entered (the model view's dashed Z rings, GUI-5b)."""
    return float(z) * charge_mass(case) ** (1.0 / 3.0)


def gauges(case):
    """[(number, R, Z or None)] per gauge, 1-based as the case numbers
    them."""
    return [(i, distance(case, g), scaled_distance(case, g))
            for i, g in enumerate(gauge_points(case), start=1)]


# ── Where: the nearest obstacle face (GUI-5b, plan §5.3) ─────────────────
#: a gauge names the nearest obstacle face only when it is this close [m]
#: (plan §5.3: "only when within 0.5 m")
WHERE_MAX = 0.5


def obstacle_boxes(case):
    """The obstacles as (lo, hi) pairs per axis, in the gauge
    coordinates: 2D (x0, x1, y0, y1) -> ((x0, x1), (y0, y1)); 3D adds
    (z0, z1). 1D has none."""
    if getattr(case, 'dim', None) not in (2, 3):
        return []
    n = case.dim
    return [tuple((float(o[2 * k]), float(o[2 * k + 1])) for k in range(n))
            for o in (case.obstacles or [])]


def _shadowed(box, a, b):
    """True when the straight segment a -> b passes through the inside of
    `box` ((lo, hi) per axis). Grazing a face or an edge does not count."""
    t0, t1 = 0.0, 1.0
    for (lo, hi), p, q in zip(box, a, b):
        p, q = float(p), float(q)
        d = q - p
        if abs(d) < 1e-12:
            if not lo < p < hi:
                return False
            continue
        ta, tb = sorted(((lo - p) / d, (hi - p) / d))
        t0, t1 = max(t0, ta), min(t1, tb)
        if t1 - t0 <= 1e-9:
            return False
    return True


def where(case, point, wall=None):
    """(wall number, gap [m], inside, behind) for the obstacle nearest to
    `point`, or None when none is within WHERE_MAX. The gap is the
    distance from the point to the box (0 on a face or inside); `behind`
    is True when the straight line from the burst point to `point`
    passes through that obstacle - the gauge is on its far side, in its
    shadow. Walls are numbered 1-based as the tree names them
    (`Wall n`). `wall` (1-based) measures against that wall instead of
    the nearest one: the wall the solver drops a gauge for (GUI-14 c)."""
    best = None
    for i, box in enumerate(obstacle_boxes(case), start=1):
        if wall is not None and i != wall:
            continue
        d = [max(lo - float(p), 0.0, float(p) - hi)
             for p, (lo, hi) in zip(point, box)]
        gap = math.sqrt(sum(x * x for x in d))
        inside = all(lo < float(p) < hi for p, (lo, hi) in zip(point, box))
        if best is None or gap < best[1]:
            best = (i, gap, inside, box)
    if best is None or best[1] > WHERE_MAX:
        return None
    i, gap, inside, box = best
    behind = not inside and _shadowed(box, burst_point(case), point)
    return i, gap, inside, behind


def where_text(case, point, dropped=None):
    """The Where cell: `5 cm in front of Wall 1`, `5 cm behind Wall 1`
    (the wall stands between the burst and the gauge), `on the face of
    Wall 1`, `inside Wall 1`, or '' (no obstacle within WHERE_MAX).

    GUI-13 (e), D5: a gauge in front of or behind a wall that the
    solver's drop rule still drops (it is within a cell of a face) reads
    `4 cm in front of Wall 1 (dropped)`, so the column agrees with the
    Checks warning. `dropped` is `services.validation.drop_rule(case)`,
    built once per table by the caller; None builds it here.

    GUI-14 (c), D1: a dropped gauge names the wall the rule drops it for
    (`dropped(point)`, as the Checks warning does), and the gap and the
    side are measured against that wall - with two walls within a cell
    the nearest as entered can be the other one. GUI-14 (d), D2: a gauge
    outside the domain reads `outside the domain (dropped)`."""
    if outside_domain(case, point):
        from ..services.validation import gauge_drop_reason
        return gauge_drop_reason(0, False, outside=True) + ' (dropped)'
    w = where(case, point)
    if w is None:
        return ''
    if dropped is None:
        from ..services.validation import drop_rule
        dropped = drop_rule(case)
    wall = dropped(point)
    if wall and wall != w[0]:
        w = where(case, point, wall=wall) or w
    i, gap, inside, behind = w
    if inside:
        return f'inside Wall {i}'
    cm = int(round(gap * 100.0))
    if cm == 0:
        return f'on the face of Wall {i}'
    text = f'{cm} cm {"behind" if behind else "in front of"} Wall {i}'
    return text + (' (dropped)' if wall else '')


def is_dropped(case, point, dropped=None):
    """True when the solver drops gauge `point`: outside the domain, or
    `dropped(point)` (`services.validation.drop_rule(case)`) names a
    wall. The rule, not the warning text (GUI-14 d)."""
    if outside_domain(case, point):
        return True
    if dropped is None:
        from ..services.validation import drop_rule
        dropped = drop_rule(case)
    return bool(dropped(point))


def dropped_numbers(case):
    """The 1-based numbers (entered order) of the gauges the solver drops
    - `is_dropped`, the rule built once. 1D: the radii beyond the domain
    (GUI-15 (f)). [] for 0D (no gauges) and for a case that cannot say.
    GUI-15 (e): the Gauges node's caption and warn child rows."""
    return drop_state(case)[0]


def drop_state(case):
    """(dropped numbers, disabled trigger) with the rule built once.
    The trigger is `services.validation.trigger_disabled`'s number - the
    entered trigger gauge when the solver drops that gauge, so the
    trigger never fires - else None (GUI-16 (a), C1)."""
    if getattr(case, 'dim', None) not in (1, 2, 3):
        return [], None
    from ..services.validation import drop_rule, trigger_disabled
    dropped = drop_rule(case)
    try:
        gone = [k for k, p in enumerate(gauge_points(case), start=1)
                if is_dropped(case, p, dropped)]
        return gone, trigger_disabled(case, dropped)
    except (AttributeError, TypeError, ValueError):
        return [], None


def any_dropped(case):
    """True when some gauge of `case` is dropped - the `gauges` tree
    node's warn state."""
    return bool(dropped_numbers(case))


def walls_in_front(case):
    """The walls some gauge stands in front of (not inside it, not
    behind it), sorted - the 05 Gauges tree summary names them."""
    out = set()
    for g in gauge_points(case):
        w = where(case, g)
        if w is not None and not w[2] and not w[3]:
            out.add(w[0])
    return sorted(out)


def nearest_gauge(case):
    """(number, R, Z) of the gauge with the smallest Z - the smallest R
    when Z is hidden (Z is then None); None without gauges."""
    rows = gauges(case)
    if not rows:
        return None
    key = (lambda r: r[2]) if z_shown(case) else (lambda r: r[1])
    return min(rows, key=key)
