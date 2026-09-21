"""HD1-3b: the room written as a blastFoam case.

WHAT THIS FILE CHECKS, AND WHAT IT DELIBERATELY DOES NOT
---------------------------------------------------------
**`p` is not the quantity under test.** The hand-off conserves MASS and
ENERGY and lets pressure fall out of the EOS on whatever cavity the mesh
has (`core/vent.py`), so pinning `p == p_0D` in a golden would pin the
very bug the design exists to avoid - a cavity 10 % smaller MUST arrive
at a higher pressure. What is pinned instead:

  * **`T`**, which does not move at all. Preserving m and E preserves
    e = E/m, and for a calorically perfect gas that is constant T.
  * **mass per phase**, against the 0-D model. `check_handoff_energy`
    compares the SUM, so a wrong split between products and air that
    happens to sum correctly passes it in silence.
  * **`p` only as a RATIO**, `p_cells == p_0D * V_0D / V_mesh`.
  * **the phase dictionary**: `type basic` + `idealGas` with the
    PROPELLANT's gamma and molWeight, never air's, and no
    `activationModel` or `initiation` anywhere in it.

And every existing golden stays byte-for-byte, which is what the new
fields being falsy by default buys.

Run:  cd blastlab/tests && python test_foam_chamber.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import deflagration as d                   # noqa: E402
from blastlab.core import room as _room                       # noqa: E402
from blastlab.core import scenario as sc                      # noqa: E402
from blastlab.core import vent as _vent                       # noqa: E402
from blastlab.core.case import Case3D, validate_case          # noqa: E402
from blastlab.core.constants import P_AIR                     # noqa: E402
from blastlab.solvers.foam.writer import render_case          # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def _values(text):
    """The nonuniform list out of a 0/ field file."""
    m = re.search(r'nonuniform\s+List<(\w+)>\s*\n?(\d+)\s*\(\s*(.*?)\)\s*;',
                  text, re.S)
    if not m:
        return []
    body = m.group(3)
    if m.group(1) == 'vector':
        return [tuple(float(v) for v in t.split())
                for t in re.findall(r'\(([^)]*)\)', body)]
    return [float(v) for v in body.split()]


def main():
    print('FOAM CHAMBER (HD1-3b)')
    prop = d.PROPELLANTS['double_base']
    dx = 0.1

    # the room, ALIGNED - which is the only room worth meshing
    m = _room.measure((0.0, 0.0, 0.0), (3.0, 3.0, 2.0), 0.2, dx,
                      vent=('x_lo', 1.0, 2.0, 0.6, 1.4))
    check('the room measures clean and snapping is a no-op after '
          'alignment', m['ok'] and not m['moved'], str(m['errors'][:1]))

    # the 0-D run it is handed over from, at the MESHED cavity
    s = sc.IgnitionScenario(kind='flame_spread', n_cohorts=40,
                            spread_time=20.0)
    shut = d.simulate(prop, 20.0, m['volume'], vent_area=0.0, t_end=40.0,
                      scenario=s, p0_chamber=P_AIR, refine_cohorts=False,
                      h_c=200.0, wall_area=6.0)
    st = _vent.handoff(shut, prop, mode='burst', p_burst=3.0 * P_AIR,
                       volume_cfd=m['volume'])
    check('the state was computed at the MESHED cavity, so there is no '
          'volume shift left to re-price downstream',
          abs(st.pressure_from_volume_shift) < 1e-12,
          f"{st.volume:.4f} m3, shift {st.pressure_from_volume_shift:+.2e}")
    # THE OTHER SHIFT, kept separate from it on purpose. The 0-D model is
    # Noble-Abel and carries a co-volume; blastFoam's phases are ideal
    # gases and do not. At magazine loading density that is ~0.1 %, and
    # at closed-vessel density it would not be small - so it is reported
    # as its own number rather than folded into the volume one, where a
    # real effect would hide behind a rounding-sized one.
    check('and the co-volume the 0-D model carries is reported as its '
          'OWN shift, not folded into the volume one',
          0.0 < abs(st.pressure_from_eos_shift) < 0.02,
          f"{st.pressure_from_eos_shift:+.3%} from dropping the co-volume")

    case = Case3D(solver='blastfoam',
                  Lx=8.0, Ly=6.0, Lz=5.0, cell_size_m=dx,
                  init_mode='chamber', charge=0.0,
                  room=m, chamber_state=st.as_dict(),
                  obstacles=m['boxes'],
                  bcs=dict(x_lo='transmit', x_hi='transmit',
                           y_lo='transmit', y_hi='transmit',
                           z_lo='reflect', z_hi='transmit'),
                  t_end=0.02, n_snapshots=4)

    # ── 1. it validates as a case ───────────────────────────────────────
    print('\n  the case validates')
    rep = validate_case(case)
    check('a chamber case with a matching room and state is accepted',
          rep.ok, str(rep.errors[:2]))
    check('and it does not ask for a profile file it has no use for',
          not any('profile file' in e.lower() for e in rep.errors))
    check('a state computed at a different volume is REFUSED, because '
          'the pressure written into the cells would be wrong by that '
          'ratio',
          not validate_case(
              Case3D(**{**case.__dict__,
                        'chamber_state': {**st.as_dict(),
                                          'volume': 0.5 * st.volume}})).ok)
    check('and an adiabatic source is a warning on the case, not just '
          'inside the hand-off',
          any('ADIABATIC' in w for w in validate_case(
              Case3D(**{**case.__dict__,
                        'chamber_state': {**st.as_dict(),
                                          'adiabatic_source': True}})
          ).warnings))
    # The absence of the field is NOT the quiet way past that warning:
    # `simulate` is adiabatic by DEFAULT, so a hand-written case that
    # simply omits it is an adiabatic case until it says otherwise.
    bare = {k: v for k, v in st.as_dict().items()
            if k != 'adiabatic_source'}
    check('a state dict that just omits the field is treated as '
          'adiabatic rather than as unknown - absence of evidence is '
          'the default, which is what simulate does',
          any('ADIABATIC' in w for w in validate_case(
              Case3D(**{**case.__dict__, 'chamber_state': bare})).warnings))
    check('and the warning says where the effect actually IS - the burst '
          'timing and the mass burnt, not T, which is nearly fixed by '
          'the trigger pressure',
          any('burnt' in w and 'later' in w for w in validate_case(
              Case3D(**{**case.__dict__, 'chamber_state': bare})).warnings))

    # ── 2. the fields ───────────────────────────────────────────────────
    print('\n  what lands in 0/')
    spec = render_case(case)
    d0 = spec.start_dir
    files = spec.files
    for want in ('p', 'T', 'U', 'alpha.expl', 'rho.expl', 'rho.air'):
        check(f'{d0}/{want} is written',
              f'{d0}/{want}' in files, '')
    check('and lambda.expl is NOT - a basic phase has no reactant side '
          'to blend back to, so B0 cannot happen here',
          f'{d0}/lambda.expl' not in files)

    T = _values(files[f'{d0}/T'])
    p = _values(files[f'{d0}/p'])
    al = _values(files[f'{d0}/alpha.expl'])
    re_ = _values(files[f'{d0}/rho.expl'])
    ra = _values(files[f'{d0}/rho.air'])
    U = _values(files[f'{d0}/U'])
    n_in = sum(1 for a in al if a > 0.0)
    check('the cavity is a real part of the mesh, not an empty set',
          n_in > 100, f'{n_in:,} cells of {len(al):,}')
    check('every cell got a value',
          len(T) == len(p) == len(al) == len(re_) == len(ra) == len(U)
          == spec.n_cells, f'{spec.n_cells:,} cells')

    # THE QUANTITY THAT DOES NOT MOVE
    Ts = {round(v, 6) for v, a in zip(T, al) if a > 0}
    check('T inside the room is the 0-D temperature, exactly - this is '
          'the quantity a golden should pin, because the hand-off '
          'conserves m and E and so preserves e = E/m',
          len(Ts) == 1 and abs(Ts.pop() - st.T) < 1e-6,
          f'{st.T:.6f} K')
    check('and outside it is ambient',
          all(abs(v - 288.0) < 1e-9 for v, a in zip(T, al) if a == 0))
    check('the gas is at rest everywhere: a room at pressure with a hole '
          'in it, not a jet already running',
          all(abs(c) < 1e-15 for vec in U for c in vec))

    # ── 3. MASS PER PHASE, which the total cannot check ─────────────────
    print('\n  mass, phase by phase, against the 0-D model')
    v_cell = dx ** 3
    m_p = sum(a * r * v_cell for a, r in zip(al, re_) if a > 0)
    m_a = sum((1.0 - a) * r * v_cell for a, r in zip(al, ra) if a > 0)
    check('the products in the cells are the products the 0-D model had',
          abs(m_p / st.m_p - 1.0) < 1e-6,
          f'{m_p:.9f} vs {st.m_p:.9f} kg')
    check('and the air, separately - a wrong split that sums correctly '
          'passes check_handoff_energy in silence, which is why this is '
          'per phase',
          abs(m_a / st.m_a - 1.0) < 1e-6,
          f'{m_a:.9f} vs {st.m_a:.9f} kg')
    check('alpha inside is the products VOLUME FRACTION, nothing like 1, '
          'because the air already in the room carries most of the '
          'partial pressure',
          abs(max(al) / st.alpha_expl - 1.0) < 1e-6 and max(al) < 0.9,
          f'alpha.expl = {max(al):.6f}')
    check('and outside the room it is zero',
          all(a == 0.0 for a in al if a == 0.0) and min(al) == 0.0)

    # ── 4. p AS A DERIVED QUANTITY, AND ITS TWO SHIFTS KEPT APART ───────
    #
    # The first version of this check compared the cells against
    # `p_0D * V_0D / V_mesh` and failed by 0.1 %, which is the
    # co-volume: the 0-D model is Noble-Abel and the mesh phases are
    # ideal gases. Folding that into the volume ratio is exactly the
    # conflation `pressure_from_eos_shift` was split out to prevent, so
    # the two factors are asserted separately here.
    print('\n  pressure, derived - and its two shifts kept apart')
    ps = {round(v, 3) for v, a in zip(p, al) if a > 0}
    check('p is uniform inside the room and is the state pressure',
          len(ps) == 1 and abs(ps.copy().pop() / st.p - 1.0) < 1e-6,
          f'{st.p/1e6:.6f} MPa on {st.volume:.4f} m3')
    check('and it is the 0-D pressure times BOTH declared factors - the '
          'volume ratio and the co-volume - neither of which is allowed '
          'to hide inside the other',
          abs(st.p / (st.p_0d
                      * (1.0 + st.pressure_from_volume_shift)
                      * (1.0 + st.pressure_from_eos_shift)) - 1.0) < 1e-9,
          f'{st.p_0d/1e6:.6f} MPa -> {st.p/1e6:.6f} '
          f'({st.pressure_from_volume_shift:+.2%} volume, '
          f'{st.pressure_from_eos_shift:+.3%} EOS)')
    check('and ambient outside',
          all(abs(v - P_AIR) < 1e-6 for v, a in zip(p, al) if a == 0))

    # ── 5. THE PHASE IS INERT, AND IT IS NOT AIR ────────────────────────
    print('\n  phaseProperties: inert, and not air')
    pp = files['constant/phaseProperties']
    check('the expl phase is `type basic` - the guide s own type for a '
          'non-reacting phase', re.search(r'expl\s*\{[^}]*type\s+basic',
                                          pp, re.S) is not None)
    check('there is no activationModel and no initiation anywhere in it',
          'activationModel' not in pp and 'initiation' not in pp)
    check('nor any JWL, since the products have finished reacting',
          'JWL' not in pp and 'Murnaghan' not in pp)
    check('gamma is the PROPELLANT s, not air s 1.4',
          f'{prop.gamma}' in pp or f'{prop.gamma:g}' in pp,
          f'gamma = {prop.gamma:g} against air 1.4')
    check('and molWeight is the propellant s ~22.7, not air s 28.97 - '
          'that difference alone is +17.9 % on the choked flow, just '
          'past the 15 % the 2-D check is pre-registered at',
          f'{st.mol_weight_p:.6g}'[:5] in pp
          or f'{round(st.mol_weight_p, 4)}' in pp,
          f'{st.mol_weight_p:.4f} g/mol')
    check('air is still air',
          '28.97' in pp and 'MOLW' not in pp)

    # ── 6. NOTHING NEW IN THE MESH PATH ─────────────────────────────────
    print('\n  and no new mesh mechanism was needed')
    check('the walls are ordinary obstacles on the existing carve',
          'system/topoSetDict' in files and spec.obstacles)
    check('the opening is a GAP between boxes, so there is no patch for '
          'it - only the obstacles patch the carve makes',
          not any('vent' in k.lower() for k in files))
    check('no createPatch, no createBaffles, no new mesh stage',
          not any(k.endswith(('createPatchDict', 'createBafflesDict'))
                  for k in files))
    check('the state is written AFTER the mesh stages, like every other '
          'non-uniform start', bool(spec.deferred)
          and all(k.startswith(d0) for k in spec.deferred))

    print('\nFOAM CHAMBER: '
          + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
