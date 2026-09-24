"""HD1-13: the load a wall takes from the free-air flow at a point.

WHAT THIS IS FOR
----------------
A gauge in free air records the SIDE-ON pressure: the static pressure of
the gas flowing past it. A wall standing where that gauge is would not
see that number. UFC 3-340-02 para 2-15.3.1 (printed p. 64, sidecar
`=== page 140 ===`) splits the load on a structure into the incident
pressure, the dynamic pressure, the reflection of the incident pressure
and the negative phase; para 2-15.3.2 (p. 65, `=== page 141 ===`) loads
a front wall with the normal reflected pressure Pr (Fig. 2-15, p. 90,
`=== page 166 ===`; Fig. 2-193 at alpha = 0, p. 268, `=== page 344 ===`)
and, once it has cleared, with `P = Ps + C_D q` (Eq. 2-9, C_D = 1 on a
front wall). This module turns a flow state (p, rho, U) into those two
terms, made compressible, and takes the larger:

    R  the normal reflection of the front (Rankine-Hugoniot, ideal gas):
           R = ps [2 + (g+1) ps / ((g-1) ps + 2 g p_amb)]   for ps > 0
           R = ps                                           otherwise
       -> 2 ps for a weak front and (3g-1)/(g-1) ps (8 at g = 1.4) for a
       strong one. No clearing: the wall is taken as unbounded, which
       Eq. 2-8 would relieve and this does not, so R is the larger.
    S  the stagnation overpressure of the flow INTO the wall, p0 - p_amb:
           isentropic               below M = 1
           Rayleigh pitot           at and above M = 1 (a normal shock
                                    stands ahead of the wall)
       As M -> 0 it is exactly Eq. 2-9 with C_D = 1: S -> ps + rho u^2/2.
    E  = max(R, S), the wall load at the point, over ambient.

The Rayleigh pitot and normal-shock relations are standard compressible
flow; they are not in a registered reference (docs/references/INDEX.md),
so `tests/test_wallload.py` checks them against an independent
derivation (normal-shock jump, then the isentropic relation behind it)
rather than against a cited table.

WHEN E AT A POINT IS AN UPPER BOUND ON THE WALL LOAD, and when it is not.
Applied uniformly over a panel, E at one point bounds the real,
non-uniform load only if (P1) the point sits where the wall load is
largest - a jet core can drift, so a probe on the geometric axis is an
assumption until a maximum over the whole plane replaces it - and (P2)
the stagnation load is quasi-steady: a jet whose velocity arrives
abruptly loads a wall with a reflected-shock transient that can be
about twice the pitot value, and the pitot pressure bounds the wall
only when the stagnation region has had time to form, i.e. at least
one acoustic transit of the opening width during the rise. Neither
premise is checked here; the HD1-13 decision rule
(docs/hd13/vent3d_wall_rule.txt) checks both.

Pure numpy, no Qt, no WSL, no matplotlib. Imported by no GUI module.
"""

import numpy as np

from .constants import P_AIR


def _result(x, scalar):
    """A float back for a scalar input, the array otherwise."""
    return float(x) if scalar else x


# ── the reflected front ────────────────────────────────────────────────

def reflected_overpressure(ps, gamma=1.4, p0=P_AIR):
    """Normal reflected overpressure R [Pa] of a front of side-on
    overpressure `ps` [Pa] running into ambient `p0` [Pa].

    Rankine-Hugoniot for an ideal gas of ratio `gamma`, the relation
    behind UFC 3-340-02 Fig. 2-15's Pr and Fig. 2-193 at alpha = 0.
    `ps <= 0` (no front) comes back unchanged. NaN in gives NaN out."""
    scalar = np.ndim(ps) == 0
    ps = np.asarray(ps, dtype=float)
    g = float(gamma)
    with np.errstate(divide='ignore', invalid='ignore'):
        r = ps * (2.0 + (g + 1.0) * ps / ((g - 1.0) * ps + 2.0 * g * p0))
    return _result(np.where(ps > 0.0, r, ps), scalar)


# ── stagnation ─────────────────────────────────────────────────────────

def stagnation_ratio_isentropic(M, gamma):
    """p0/p for an isentropic stop from Mach `M`."""
    M = np.asarray(M, dtype=float)
    g = float(gamma)
    return (1.0 + 0.5 * (g - 1.0) * M * M) ** (g / (g - 1.0))


def stagnation_ratio_pitot(M, gamma):
    """p0/p behind the normal shock that stands ahead of a wall (or a
    pitot tube) in a flow of Mach `M` >= 1 - the Rayleigh pitot formula.
    Equal to the isentropic ratio at M = 1, below it above."""
    M = np.asarray(M, dtype=float)
    g = float(gamma)
    m2 = M * M
    return ((((g + 1.0) ** 2 * m2) / (4.0 * g * m2 - 2.0 * (g - 1.0)))
            ** (g / (g - 1.0))
            * (1.0 - g + 2.0 * g * m2) / (g + 1.0))


def _stagnation(p, rho, un, gamma):
    """(p0, M): absolute stagnation pressure and the Mach number of the
    velocity into the wall. `un < 0` (flow leaving the wall) is 0."""
    p = np.asarray(p, dtype=float)
    rho = np.asarray(rho, dtype=float)
    u = np.maximum(np.asarray(un, dtype=float), 0.0)    # NaN stays NaN
    g = float(gamma)
    with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
        M = u / np.sqrt(g * p / rho)
        ratio = np.where(M < 1.0, stagnation_ratio_isentropic(M, g),
                         stagnation_ratio_pitot(M, g))
    return p * ratio, M


def stagnation_pressure(p, rho, un, gamma):
    """Absolute stagnation pressure [Pa] of gas at pressure `p` [Pa],
    density `rho` [kg/m3] moving at `un` [m/s] into a wall: isentropic
    below M = 1, Rayleigh pitot at and above it. `un < 0` is taken as 0.
    NaN in gives NaN out."""
    scalar = all(np.ndim(v) == 0 for v in (p, rho, un))
    p0, _M = _stagnation(p, rho, un, gamma)
    return _result(p0, scalar)


# ── the wall load ──────────────────────────────────────────────────────

def wall_load(times, p, U, rho, gamma, normal=(1.0, 0.0, 0.0),
              p_amb=P_AIR):
    """The wall load E(t) = max(R, S) at a point, with its parts.

    `p` [Pa, absolute] and `rho` [kg/m3] are the flow state. `U` [m/s]
    is either vectors, shaped like `p` plus a trailing 3, or the speed
    along `normal` already, shaped like `p`. `normal` points INTO the
    wall, i.e. along the flow that loads it; un = max(U . normal, 0).
    Returns dict(t, E, R, S, M, un): E, R and S in Pa over `p_amb`, M
    the Mach number of un. Every output has the shape of `p`, and a NaN
    anywhere in a sample's inputs gives NaN for that sample, never 0."""
    p = np.asarray(p, dtype=float)
    rho = np.asarray(rho, dtype=float)
    U = np.asarray(U, dtype=float)
    n = np.asarray(normal, dtype=float)
    n = n / np.sqrt(float((n * n).sum()))
    if U.ndim == p.ndim + 1 and U.shape[-1] == 3:
        u_n = (U * n).sum(axis=-1)
    elif U.shape == p.shape:
        u_n = U
    else:
        raise ValueError(f'U must be shaped {p.shape} (normal speeds) or '
                         f'{p.shape + (3,)} (vectors), not {U.shape}')
    un = np.maximum(u_n, 0.0)                           # NaN stays NaN
    R = np.asarray(reflected_overpressure(p - p_amb, gamma, p_amb),
                   dtype=float)
    p0, M = _stagnation(p, rho, un, gamma)
    S = p0 - p_amb
    return dict(t=np.asarray(times, dtype=float), E=np.maximum(R, S),
                R=R, S=S, M=M, un=un)


def extend_with_tail(times, load, level, duration):
    """(times, load) with `level` held for `duration` [s] after the
    record ends - the HD1-13 rule's T1 tail.

    The step is the record's LAST sample gap, never a vanishing one:
    `sdof.response` steps at min(Tn/50, smallest sample gap)
    (core/sdof.py, `response`), so a 1e-9 s step here would make its
    pure-Python loop tens of millions of steps long. The load therefore
    ramps from its last value to `level` over one gap and then holds;
    after the extended record `sdof.response` takes it as zero, as it
    does for any record."""
    t = np.asarray(times, dtype=float)
    y = np.asarray(load, dtype=float)
    if len(t) < 2 or len(t) != len(y):
        raise ValueError('a trace needs at least two samples, as many '
                         'loads as times')
    gap = float(t[-1] - t[-2])
    if not gap > 0.0:
        raise ValueError('the last sample gap must be positive')
    k = int(np.ceil(float(duration) / gap)) if duration > 0 else 0
    if k <= 0:
        return t.copy(), y.copy()
    t_add = t[-1] + gap * np.arange(1, k + 1)
    return (np.concatenate([t, t_add]),
            np.concatenate([y, np.full(k, float(level))]))
