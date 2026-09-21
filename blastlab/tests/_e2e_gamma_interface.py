"""HD1-3d, FIRST: does blastFoam hold a gamma interface still?

THIS IS A STOPPING POINT, and it runs before the 2-D verification
rather than alongside it. If either case below fails, every number in
the vented jet is contaminated and there is no point measuring a mass
flow against anything.

THE TWO CASES, AND WHY THE SECOND IS THE IMPORTANT ONE

  1. A STEP IN GAMMA. A room at AMBIENT pressure and temperature, full
     of combustion products (gamma 1.24, M 22.7), with an opening onto
     ambient air (1.40, 28.97). Same p, same T, everything at rest, and
     a jump in the equation of state across the opening. Nothing should
     happen. This is Abgrall's problem (1996): multi-material schemes
     routinely manufacture pressure oscillations at a contact
     discontinuity where gamma jumps, and a scheme that does will
     produce a jet out of a room that was not pressurised.

  2. UNIFORM MIXED CELLS. A SEALED room whose every cell holds BOTH
     phases at once - 0 < alpha < 1 - at uniform p and T, at rest. This
     is exactly the chamber's initial state after HD1-3-pre, and case 1
     does not test it at all: a sharp step exercises the INTERFACE, not
     a cell with two phases inside it. Nothing should happen here
     either, and if it does, every chamber this track initialises is
     ringing before the panel even bursts.

PRE-REGISTERED, before the run that will be judged by it (CLAUDE.md 6):
**0.5 % of ambient on every gauge, for the whole window, in both
cases.** Not a fitted tolerance - both cases are exactly "nothing
happens", so the only correct answer is round-off, and half a per cent
is a generous allowance for the wall boundaries. Anything larger is the
scheme inventing a wave.

Run:  cd blastlab/tests && python _e2e_gamma_interface.py
      (WSL; confirm `wsl -d Ubuntu -- pgrep -a blastFoam` is empty first)
"""

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import deflagration as d                   # noqa: E402
from blastlab.core import room as _room                       # noqa: E402
from blastlab.core.case import Case3D, validate_case          # noqa: E402
from blastlab.core.constants import P_AIR                     # noqa: E402

#: Pre-registered, above. Fraction of ambient.
TOL = 0.005

#: Long enough for several acoustic crossings of the domain, which is
#: when an oscillation would have grown and shown itself.
T_END = 0.010

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def chamber_at_rest(prop, volume, alpha, p=P_AIR, T=288.0):
    """A ChamberState-shaped dict for a mixture that is going nowhere.

    Built by hand rather than through `vent.handoff`, because the
    question here is about the SOLVER and not about the hand-off: the
    hand-off derives p and T from a burn, and what is needed is a state
    chosen to make nothing happen.
    """
    rho_expl = p / (prop.R * T)
    rho_air = p / (d.AIR_R * T)
    m_p = alpha * rho_expl * volume
    m_a = (1.0 - alpha) * rho_air * volume
    _R, cv_mix, _cp, _g = d.mixture(prop, m_p, m_a)
    return {
        'p': p, 'T': T, 'm_p': m_p, 'm_a': m_a,
        'E': (m_p + m_a) * cv_mix * T, 'volume': volume,
        'alpha_expl': alpha, 'alpha_air': 1.0 - alpha,
        'rho_expl': rho_expl, 'rho_air': rho_air,
        'rho_mix': (m_p + m_a) / volume, 'e_mix': cv_mix * T,
        'R_p': prop.R, 'gamma_p': prop.gamma,
        'mol_weight_p': 8314.46261815324 / prop.R,
        't_open': 0.0, 'mode': 'open', 'first_front_is_artefact': False,
        'volume_0d': volume, 'p_0d': p,
        'pressure_from_volume_shift': 0.0, 'pressure_from_eos_shift': 0.0,
        'adiabatic_source': False, 'wall_loss_fraction': 0.0,
        'warnings': [],
    }


def build(alpha, vent, gauges):
    prop = d.PROPELLANTS['double_base']
    dx = 0.05
    m = _room.measure((0.4, 0.1, 0.0), (1.0, 0.4, 0.4), 0.1, dx, vent=vent)
    if not m['ok']:
        raise RuntimeError('the probe room does not mesh: '
                           + '; '.join(m['errors']))
    cs = chamber_at_rest(prop, m['volume'], alpha)
    case = Case3D(
        solver='blastfoam', Lx=2.0, Ly=0.6, Lz=0.6, cell_size_m=dx,
        init_mode='chamber', charge=0.0,
        room=m, chamber_state=cs, obstacles=m['boxes'],
        bcs=dict(x_lo='transmit', x_hi='transmit', y_lo='transmit',
                 y_hi='transmit', z_lo='reflect', z_hi='transmit'),
        t_end=T_END, n_snapshots=4, gauges=list(gauges),
        # A PRESCRIBED STEP, because these cases are deliberately
        # quiescent and blastFoam takes its Courant number from the face
        # fluxes: exactly uniform and exactly at rest means Co = 0, and
        # `Time::adjustDeltaT` divides by it. The first attempt at this
        # file died with a SIGFPE there on step one - after printing
        # max(p) = min(p) = 101325, which is the answer this file was
        # written to get. A real chamber case is pressurised and has a
        # flux immediately, so nothing else needs this.
        fixed_dt=2.0e-6)
    rep = validate_case(case)
    if not rep.ok:
        raise RuntimeError('; '.join(rep.errors))
    return case, m


def worst(res):
    """Largest departure from ambient over every gauge and sample, as a
    fraction. Reported whatever it is - the threshold is applied by the
    caller, so a near-miss is visible rather than rounded to pass."""
    out = 0.0
    where = ''
    for i, p in enumerate(res.gauges['pressures']):
        a = np.asarray(p, dtype=float)
        a = a[np.isfinite(a)]
        if not len(a):
            continue
        dev = float(np.max(np.abs(a - P_AIR))) / P_AIR
        if dev > out:
            out, where = dev, f'gauge {i}'
    return out, where


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f'  [SKIP] blastFoam unavailable: {detail}')
        print('\nGAMMA INTERFACE: SKIP')
        return 0
    from blastlab.solvers import get_solver

    print('GAMMA INTERFACE (HD1-3d, the stopping point)')
    print(f'  pre-registered: every gauge within {TOL:.1%} of ambient for '
          f'{T_END * 1e3:.0f} ms, in both cases')

    # gauges: inside the room, at the opening, and out in the free air
    g_in = [(0.8, 0.3, 0.2), (1.1, 0.3, 0.2)]
    g_out = [(0.3, 0.3, 0.2), (1.6, 0.3, 0.2)]

    # ── 1. a step in gamma, at uniform p and T ──────────────────────────
    print('\n  1. products inside, air outside, same p and T, at rest')
    case, m = build(1.0, ('x_hi', 0.2, 0.4, 0.15, 0.35), g_in + g_out)
    check('the room meshes and the case validates', True,
          f"cavity {m['volume']:.4f} m3, opening {m['vent_area']:.4f} m2")
    res = get_solver(3, 'blastfoam')(case)
    dev, where = worst(res)
    check(f'pressure stays within {TOL:.1%} of ambient across the gamma '
          f'interface - Abgrall oscillations would show here', dev < TOL,
          f'worst {dev:.3%} at {where}')
    check('and the run finished rather than dying',
          not getattr(res, 'failed', False), str(res.stop_reason))

    # ── 2. UNIFORM MIXED CELLS, which case 1 does not test ──────────────
    print('\n  2. a sealed room whose every cell holds both phases')
    case2, m2 = build(0.30, None, g_in + g_out)
    check('the sealed room meshes', True,
          f"cavity {m2['volume']:.4f} m3, alpha_expl 0.30 throughout")
    res2 = get_solver(3, 'blastfoam')(case2)
    dev2, where2 = worst(res2)
    check(f'a cell with two phases inside it stays put to within '
          f'{TOL:.1%} - this is the chamber s own initial state, and a '
          f'sharp step does not exercise it', dev2 < TOL,
          f'worst {dev2:.3%} at {where2}')
    check('and that run finished too',
          not getattr(res2, 'failed', False), str(res2.stop_reason))

    print('\n' + ('GAMMA INTERFACE: PASS - the 2-D verification may '
                  'proceed' if not FAIL else
                  'GAMMA INTERFACE: FAIL - ' + ', '.join(FAIL)
                  + '\n  STOP. Every number in the vented jet would be '
                    'contaminated; do not run the 2-D comparison until '
                    'this passes.'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
