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
the gauge table, the rings).
"""

import math

#: the column / tile label everywhere (plan §5.3)
LABEL = 'Z [m/kg^1/3]'


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


def nearest_gauge(case):
    """(number, R, Z) of the gauge with the smallest Z - the smallest R
    when Z is hidden (Z is then None); None without gauges."""
    rows = gauges(case)
    if not rows:
        return None
    key = (lambda r: r[2]) if z_shown(case) else (lambda r: r[1])
    return min(rows, key=key)
