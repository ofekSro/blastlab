"""HD1-5: equivalent single-degree-of-freedom response of a structural
component to a pressure-time history (UFC 3-340-02 style).

WHY THIS MODULE EXISTS, AND WHY IT IS THE FIRST PIECE OF HD1
------------------------------------------------------------
The repo can already say what pressure arrives at a wall. It has never
been able to say what the wall *does* about it. That gap is what makes an
HD1.3 answer impossible to state, because the whole point about a
deflagrating charge is not the size of its load but the REGIME of it:

    HD1.1 detonation      t_d ~ 1-10 ms,  T_n of a wall ~ 10-100 ms
                          -> t_d/T_n << 1, the IMPULSIVE regime.
                          The response is set by the impulse alone; the
                          peak pressure is nearly irrelevant.

    HD1.3 confined burn   the quasi-static rise and vent decay are
                          10-1000 ms
                          -> t_d/T_n >= 1, the QUASI-STATIC regime.
                          The response is set by the peak pressure alone;
                          the impulse is nearly irrelevant, and the
                          dynamic load factor tends to 2.

Those are opposite corners of the pressure-impulse diagram. Entering an
HD1.3 charge as a "TNT equivalent" does not merely get the magnitude
wrong - it puts the answer in the wrong corner, which is why TODO.md HD1
calls the error "dangerous in reverse".

The quasi-static asymptote makes the HD1.3 punchline closed-form. As the
ductility mu -> infinity,

    P_asym = Ru * (1 - 1/(2 mu))  ->  Ru

i.e. **a confined quasi-static pressure that merely reaches the element's
ultimate unit resistance fails it, however slowly it arrives.** No
impulse argument, no dynamic amplification, no duration. That single line
is what this module exists to turn into a number.

It is deliberately built before any of the deflagration work: it is
independent of all of it, it verifies against closed-form textbook
solutions rather than against anything this repo calibrates, and it is
useful immediately on the detonation traces the repo already produces.

WHAT IT SOLVES
--------------
The equivalent one-way system, per unit area of the component:

    K_LM * m * y'' + c * y' + R(y) = F(t)

with an elastic-perfectly-plastic resistance (elastic unloading, so
rebound and permanent set come out of the same expression):

    R(y) = clip(kE * (y - y_p), -Ru, +Ru)

where y_p is the accumulated plastic offset. Integration is UFC
3-340-02 Sec. 3-19's own acceleration-explicit recurrence

    y_{n+1} = 2 y_n - y_{n-1} + y''_n * dt^2

started from rest with y_1 = y''_0 dt^2 / 2. That scheme is chosen
*because* it is the textbook procedure: the entire value of this module
is that it reproduces the published charts, and a better integrator would
need its own defence. For a step load it is not merely close to the
analytic answer - it is exactly

    y_n = y* (1 - cos(w_num n dt)),     w_num = (2/dt) asin(w dt / 2)

so the amplitude is exact and only the frequency is shifted by O(dt^2).
That is why `_peak` refines the sampled maximum parabolically: with the
amplitude already exact, interpolation recovers DLF = 2 to ~1e-6 instead
of the ~1 % a raw sample maximum would give.

THE TRACE CONTRACT
------------------
`response(times, p, comp)` takes exactly the `(times, p)` pair that
`output.gauge_summary.summarize_trace` takes, so one trace feeds both the
engineering table and the structural answer with no adapter. Three
sources, all thin:

    gauge_trace(res, k)        a native / blastFoam / 0-D gauge
    face_trace(frames, id)     an obstacle face from viz3d.sampling
    (times, pressures[0])      a 0-D chamber history, already this shape

Pure numpy, no Qt, no WSL, no matplotlib.
"""

import numpy as np

from .constants import P_AIR

#: UFC 3-340-02 Table 3-12 / Biggs Table 5.1 - load-mass factors K_LM for
#: one-way elements under a uniformly distributed load. K_LM = K_L / K_M.
KLM_TABLE = {
    ('simple', 'elastic'): 0.78,        # K_L 0.64 / K_M 0.50
    ('simple', 'plastic'): 0.66,        # K_L 0.50 / K_M 0.33
    ('fixed', 'elastic'): 0.77,         # K_L 0.53 / K_M 0.41
    ('fixed', 'plastic'): 0.66,         # K_L 0.50 / K_M 0.33
    ('cantilever', 'elastic'): 0.65,    # K_L 0.40 / K_M 0.26
    ('cantilever', 'plastic'): 0.66,    # K_L 0.50 / K_M 0.33
}

SUPPORTS = ('simple', 'fixed', 'cantilever')
KLM_MODES = ('average', 'elastic', 'plastic')

#: Regime boundaries in t_d / T_n. The usual blast-engineering split
#: (Baker et al.): below the first the response is impulse-controlled and
#: the peak pressure barely matters; above the second it is
#: pressure-controlled and the impulse barely matters.
IMPULSIVE_MAX = 0.1
QUASI_STATIC_MIN = 10.0

#: Steps per natural period. UFC 3-340-02 asks for dt <= T_n/10; this
#: module defaults finer because its verification suite compares against
#: closed forms at the 0.5 % level, and the central-difference period
#: error is O((w dt)^2) - 0.41 % at T_n/20, which would eat most of that
#: budget before the physics is even reached. At T_n/50 it is 0.066 %.
STEPS_PER_PERIOD = 50

#: Free vibration appended after the record ends, in natural periods. An
#: impulsive peak happens AFTER the load is gone; without this the
#: default answer for a short pulse would silently be the value at the
#: end of the record instead of the maximum.
FREE_PERIODS = 1.5


class Component:
    """One structural element, reduced to its equivalent SDOF properties.

    span            L [m], the clear span
    mass_per_area   m [kg/m^2] of the real element
    Ru              r_u [Pa], ultimate unit resistance
    kE              k_E [Pa/m], elastic unit stiffness
    support         'simple' | 'fixed' | 'cantilever'
    damping         fraction of critical. UFC neglects damping for blast
                    (the peak arrives within the first quarter cycle), so
                    the default is 0.0 and anything else is the caller's
                    explicit choice.
    klm_mode        'average' (UFC's recommendation for one-way elements:
                    one K_LM for the whole response, avoiding a mass
                    discontinuity at yield), 'elastic', or 'plastic'.
    """

    def __init__(self, span, mass_per_area, Ru, kE, support='simple',
                 damping=0.0, klm_mode='average'):
        if span <= 0 or mass_per_area <= 0 or Ru <= 0 or kE <= 0:
            raise ValueError('span, mass_per_area, Ru and kE must all be '
                             'positive')
        if support not in SUPPORTS:
            raise ValueError(f'support must be one of {SUPPORTS}, '
                             f'not {support!r}')
        if klm_mode not in KLM_MODES:
            raise ValueError(f'klm_mode must be one of {KLM_MODES}, '
                             f'not {klm_mode!r}')
        if not 0.0 <= damping < 1.0:
            raise ValueError('damping is a fraction of critical, in [0, 1)')
        self.span = float(span)
        self.mass_per_area = float(mass_per_area)
        self.Ru = float(Ru)
        self.kE = float(kE)
        self.support = support
        self.damping = float(damping)
        self.klm_mode = klm_mode

    @property
    def y_el(self):
        """Yield deflection [m]."""
        return self.Ru / self.kE

    @property
    def KLM(self):
        el = KLM_TABLE[(self.support, 'elastic')]
        pl = KLM_TABLE[(self.support, 'plastic')]
        if self.klm_mode == 'elastic':
            return el
        if self.klm_mode == 'plastic':
            return pl
        return 0.5 * (el + pl)

    @property
    def mass_eq(self):
        """Equivalent mass per unit area [kg/m^2]."""
        return self.KLM * self.mass_per_area

    @property
    def omega(self):
        """Natural circular frequency [rad/s]."""
        return np.sqrt(self.kE / self.mass_eq)

    @property
    def Tn(self):
        """Natural period [s]."""
        return 2.0 * np.pi / self.omega

    def rotation_deg(self, y):
        """Support rotation [deg] for a deflection y [m]. One-way elements
        hinge about mid-span; a cantilever about its root."""
        arm = self.span if self.support == 'cantilever' else 0.5 * self.span
        return float(np.degrees(np.arctan(abs(y) / arm)))

    def __repr__(self):
        return (f'Component(span={self.span:g}, '
                f'mass_per_area={self.mass_per_area:g}, Ru={self.Ru:g}, '
                f'kE={self.kE:g}, support={self.support!r}, '
                f'Tn={self.Tn * 1e3:.2f} ms)')


class SdofResult:
    """What `response` produces. `y`/`v`/`R` are on the uniform solver
    grid `times`, not on the caller's input grid."""

    __slots__ = ('times', 'y', 'v', 'R', 'load', 'y_max', 't_ymax',
                 'ductility', 'support_rotation_deg', 'dlf', 'Tn', 'td',
                 'td_over_Tn', 'regime', 'p_peak', 'impulse', 'P_bar',
                 'I_bar', 'yielded', 'y_residual')

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}

    def __repr__(self):
        return (f'SdofResult(y_max={self.y_max * 1e3:.3f} mm, '
                f'mu={self.ductility:.3f}, '
                f'theta={self.support_rotation_deg:.3f} deg, '
                f'regime={self.regime!r}, td/Tn={self.td_over_Tn:.3g})')


# ── the resistance function ────────────────────────────────────────────

def _resistance(y, y_p, kE, Ru):
    """(R, y_p) - elastic-perfectly-plastic with elastic unloading.

    `y_p` is the plastic offset carried between steps: the deflection at
    which the element would now be at zero resistance. Yielding in either
    direction drags it along, which is what makes rebound and permanent
    set fall out of one expression instead of a state machine.
    """
    r = kE * (y - y_p)
    if r > Ru:
        return Ru, y - Ru / kE
    if r < -Ru:
        return -Ru, y + Ru / kE
    return r, y_p


def _peak(y, times):
    """(y_max, t at the maximum), the sampled maximum refined by a
    parabola through its two neighbours.

    Worth the six lines: the central-difference amplitude is exact for a
    step load but the SAMPLES straddle the crest, so a raw maximum reads
    ~1 % low at T_n/50 while the parabola recovers it to ~1e-6.
    """
    i = int(np.argmax(y))
    if i == 0 or i == len(y) - 1:
        return float(y[i]), float(times[i])
    a, b, c = float(y[i - 1]), float(y[i]), float(y[i + 1])
    denom = a - 2.0 * b + c
    if denom >= 0.0:          # not a crest (flat or convex) - take it as is
        return b, float(times[i])
    off = 0.5 * (a - c) / denom
    dt = float(times[1] - times[0])
    return b - 0.25 * (a - c) * off, float(times[i]) + off * dt


# ── the solver ─────────────────────────────────────────────────────────

def response(times, p, comp, p_ref=P_AIR, dt=None, t_end=None,
             free_periods=FREE_PERIODS):
    """SDOF response of `comp` to the pressure history `(times, p)`.

    `p_ref` is subtracted to give the net driving pressure: pass `P_AIR`
    for an absolute gauge trace (the default, matching
    `gauge_summary.summarize_trace`) and `0.0` when the caller already
    holds net overpressure.

    The load is linearly interpolated onto a uniform step
    `dt = T_n / STEPS_PER_PERIOD`, further limited so it never steps over
    an input sample. After the record ends the load is taken as ZERO and
    the solve continues for `free_periods` natural periods, because an
    impulsive peak occurs after the load is gone; the record is assumed
    to end at ambient, which is what `p_ref` already asserts.
    """
    t_in = np.asarray(times, dtype=float)
    p_in = np.asarray(p, dtype=float)
    n_in = min(len(t_in), len(p_in))
    if n_in < 2:
        raise ValueError('a trace needs at least two samples')
    t_in, p_in = t_in[:n_in], p_in[:n_in]
    if not np.all(np.diff(t_in) > 0):
        order = np.argsort(t_in)
        t_in, p_in = t_in[order], p_in[order]
    F_in = p_in - p_ref

    Tn = comp.Tn
    if dt is None:
        dt = Tn / STEPS_PER_PERIOD
        gaps = np.diff(t_in)
        dt = min(dt, float(np.min(gaps)))
    dt = float(dt)
    if dt <= 0:
        raise ValueError('dt must be positive')
    if t_end is None:
        t_end = float(t_in[-1]) + free_periods * Tn
    n = max(int(np.ceil((t_end - t_in[0]) / dt)) + 1, 3)
    t = t_in[0] + dt * np.arange(n)
    # zero outside the record: the trace is net pressure and it ended
    F = np.interp(t, t_in, F_in, left=0.0, right=0.0)

    M = comp.mass_eq
    kE, Ru = comp.kE, comp.Ru
    c = 2.0 * comp.damping * M * comp.omega

    y = np.zeros(n)
    v = np.zeros(n)
    R = np.zeros(n)
    y_p = 0.0

    R[0], y_p = _resistance(y[0], y_p, kE, Ru)
    acc = (F[0] - R[0]) / M
    if n > 1:
        y[1] = 0.5 * acc * dt * dt
        v[1] = acc * dt
        R[1], y_p = _resistance(y[1], y_p, kE, Ru)
    # UFC Sec. 3-19: y_{n+1} = 2 y_n - y_{n-1} + acc_n dt^2. Damping uses
    # the backward velocity so the step stays explicit; with the default
    # damping = 0 it contributes nothing at all.
    for i in range(1, n - 1):
        acc = (F[i] - R[i] - c * v[i]) / M
        y[i + 1] = 2.0 * y[i] - y[i - 1] + acc * dt * dt
        v[i + 1] = (y[i + 1] - y[i]) / dt
        R[i + 1], y_p = _resistance(y[i + 1], y_p, kE, Ru)

    y_max, t_ymax = _peak(y, t)
    y_el = comp.y_el
    mu = y_max / y_el

    # load descriptors, taken from the INPUT trace so they mean the same
    # thing the gauge table means
    ovp = np.clip(F_in, 0.0, None)
    p_peak = float(np.max(F_in))
    impulse = float(np.trapezoid(ovp, t_in)) if hasattr(np, 'trapezoid') \
        else float(np.trapz(ovp, t_in))
    td = _positive_duration(t_in, F_in)
    ratio = td / Tn if td > 0 else np.nan
    if not np.isfinite(ratio):
        regime = 'unknown'
    elif ratio <= IMPULSIVE_MAX:
        regime = 'impulsive'
    elif ratio >= QUASI_STATIC_MIN:
        regime = 'quasi-static'
    else:
        regime = 'dynamic'

    return SdofResult(
        times=t, y=y, v=v, R=R, load=F,
        y_max=y_max, t_ymax=t_ymax,
        ductility=mu,
        support_rotation_deg=comp.rotation_deg(y_max),
        dlf=(y_max * kE / p_peak) if (p_peak > 0 and mu <= 1.0) else np.nan,
        Tn=Tn, td=td, td_over_Tn=ratio, regime=regime,
        p_peak=p_peak, impulse=impulse,
        P_bar=p_peak / Ru,
        I_bar=impulse / (M * comp.omega * y_el),
        yielded=bool(mu > 1.0),
        y_residual=float(y_p))


def _positive_duration(t, F):
    """Duration of the first positive phase [s] - from the first sample
    above zero net pressure to the first crossing back, linearly
    interpolated. Mirrors `gauge_summary.summarize_trace`.

    NOTE, and it must stay documented rather than "fixed": this is a
    SHOCK rule. On a slow quasi-static build-up it returns something much
    closer to a rise time than to a blast duration, and a 400 ms
    "duration" for a magazine burn is the rule behaving as designed, not
    a bug. `td_over_Tn` inherits that caveat.
    """
    hit = np.flatnonzero(F > 0.0)
    if not len(hit):
        return 0.0
    i = int(hit[0])
    j = i
    while j < len(F) and F[j] > 0.0:
        j += 1
    if j >= len(F):
        return float(t[-1] - t[i])
    a, b = F[j - 1], F[j]
    frac = a / (a - b) if a != b else 0.0
    return float(t[j - 1] + frac * (t[j] - t[j - 1]) - t[i])


# ── trace feeders ──────────────────────────────────────────────────────

def gauge_trace(res, k=0):
    """`(times, p)` for gauge k of a native, blastFoam or 0-D Result."""
    g = res.gauges if hasattr(res, 'gauges') else res
    return np.asarray(g['times'], float), np.asarray(g['pressures'][k], float)


def face_trace(frames, face_id):
    """`(times, p)` for one obstacle face, area-averaged.

    `frames` is a sequence of `(t, loads)` where `loads` is what
    `viz3d.sampling.extract_loads` returns. Every cell on a face carries
    the same dx^2, so the area average is a plain mean; buried cells are
    NaN and drop out of it.
    """
    ts, ps = [], []
    for t, loads in frames:
        arr = loads.get(face_id)
        if arr is None:
            continue
        arr = np.asarray(arr, float)
        if not np.isfinite(arr).any():
            continue
        ts.append(float(t))
        ps.append(float(np.nanmean(arr)))
    if len(ts) < 2:
        raise ValueError(f'face {face_id!r} gave {len(ts)} usable frame(s) '
                         f'- need at least two')
    return np.asarray(ts), np.asarray(ps)


# ── the pressure-impulse diagram ───────────────────────────────────────

def pi_asymptotes(mu):
    """(I_bar, P_bar) asymptotes of the iso-damage curve at ductility mu,
    in this module's normalisation.

        P_bar = P / Ru                     I_bar = I / (M w y_el)

    With an elastic-perfectly-plastic resistance both are closed form:

        P_bar -> 1 - 1/(2 mu)              I_bar -> sqrt(2 mu - 1)

    Sanity: at mu = 1 they are 0.5 and 1, which are exactly the elastic
    quasi-static (mu = 2 P_bar) and elastic impulsive (mu = I_bar)
    limits. These two lines are what `tests/test_sdof.py` pins the swept
    curve against.
    """
    if mu < 1.0:
        raise ValueError('ductility asymptotes are defined for mu >= 1')
    return float(np.sqrt(2.0 * mu - 1.0)), float(1.0 - 1.0 / (2.0 * mu))


def pi_point(res):
    """The (I_bar, P_bar) coordinates of one computed response."""
    return res.I_bar, res.P_bar


def _shape(kind, t, td):
    if kind == 'triangular':
        return np.clip(1.0 - t / td, 0.0, None)
    if kind == 'rectangular':
        return np.where(t <= td, 1.0, 0.0).astype(float)
    raise ValueError(f'unknown pulse shape {kind!r}')


def pi_curve(comp, mu_limit, shape='triangular', n=40,
             ratios=None, tol=1e-4, max_iter=60):
    """Iso-damage curve: the (I_bar, P_bar) loci that just reach
    `mu_limit`, swept over t_d/T_n.

    The peak response is monotone in load amplitude, so each point is a
    bisection on amplitude - safe, derivative-free and pure numpy.
    """
    if mu_limit < 1.0:
        raise ValueError('mu_limit must be at least 1')
    if ratios is None:
        ratios = np.logspace(-2, 2, n)
    y_target = mu_limit * comp.y_el
    I_bar, P_bar = [], []
    for r in np.asarray(ratios, float):
        td = r * comp.Tn
        t = np.linspace(0.0, td, 400)
        base = _shape(shape, t, td)
        lo, hi = 1e-6 * comp.Ru, 1e6 * comp.Ru
        for _ in range(max_iter):
            mid = np.sqrt(lo * hi)
            res = response(t, mid * base, comp, p_ref=0.0)
            if res.y_max > y_target:
                hi = mid
            else:
                lo = mid
            if hi / lo - 1.0 < tol:
                break
        amp = np.sqrt(lo * hi)
        res = response(t, amp * base, comp, p_ref=0.0)
        I_bar.append(res.I_bar)
        P_bar.append(res.P_bar)
    return np.asarray(I_bar), np.asarray(P_bar)
