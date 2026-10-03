"""validate_case cell-cap gating per solver backend (no WSL needed -
the env probe is never started by validate_case itself)."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import Case2D, Case3D, validate_case          # noqa: E402
from blastlab.core.constants import (CELLS_REFUSE, FOAM_CELLS_WARN,   # noqa: E402
                                     FOAM_CELLS_REFUSE)

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def cells_err(rep):
    return [e for e in rep.errors if 'cells exceeds' in e]


def amr_cap_checks():
    """N16: AMR caps apply to maxCells (the mesh grows) and to the
    display grid, never to the t=0 base count.

    Pins a large VM (N21): these rows assert against FOAM_CELLS_WARN /
    FOAM_CELLS_REFUSE, which are the ceiling only when the measured RAM
    is at least that big. Unpinned, the conservative caps would turn the
    'warned' row into a refusal."""
    from blastlab.solvers.foam import env
    from blastlab.core import hardware
    old = tuple(getattr(env, a) for a in _HW_ATTRS)
    try:
        env.forget_hardware()
        env.prime_hardware(cores=8, ram_gb=512, source=hardware.MEASURED)
        _amr_cap_checks()
    finally:
        for a, v in zip(_HW_ATTRS, old):
            setattr(env, a, v)


def _amr_cap_checks():
    amr = dict(Lx=4.0, Ly=4.0, Lz=4.0, cell_size_m=0.1, charge=8.0,
               center=(2.0, 2.0, 2.0), solver='blastfoam', amr_levels=4)
    rep = validate_case(Case3D(**amr))
    check('amr: 64k base cells, no cell-cap error, display level auto = 2',
          not cells_err(rep) and not rep.errors and rep.display_level == 2
          and rep.n_cells == 64_000, f'{rep.errors} {rep.display_level}')
    rep = validate_case(Case3D(amr_max_cells=FOAM_CELLS_REFUSE + 1, **amr))
    check('amr: maxCells above the blastFoam cap refused',
          any('AMR max cells' in e for e in rep.errors), str(rep.errors))
    rep = validate_case(Case3D(amr_max_cells=FOAM_CELLS_WARN + 1, **amr))
    check('amr: maxCells above the warn level warned',
          any('AMR may grow' in w for w in rep.warnings), str(rep.warnings))
    rep = validate_case(Case3D(amr_display_level=4, **amr))
    check('amr: display grid over the 3D cap refused with the AMR hint',
          any('lower the AMR display level' in e for e in rep.errors),
          str(rep.errors))
    rep = validate_case(Case3D(solver='native', Lx=4.0, Ly=4.0, Lz=4.0,
                               cell_size_m=0.1, charge=8.0,
                               center=(2.0, 2.0, 2.0), amr_levels=2))
    check('amr on the native solver refused',
          any('AMR' in e for e in rep.errors), str(rep.errors))


def programmed_ignition_checks():
    """N5-12: programmedIgnition activation and per-point delays/radii."""
    print()
    print("N5-12: programmedIgnition + delays/radii")
    base = dict(geometry='axisymmetric', Lx=2.0, Ly=2.0, cell_size_m=0.02,
                charge=1.0, center=(0.0, 1.0), solver='blastfoam',
                material='TNT', gauges=[(1.0, 1.0)])

    r = validate_case(Case2D(activation='programmedIgnition', **base))
    check('programmedIgnition validates', r.ok, str(r.errors))
    check('and says what it does',
          any('Giroux' in n for n in r.notes), str(r.notes))

    r = validate_case(Case2D(activation='beta', **base))
    check('an unknown model is refused',
          any('Unknown activation' in e for e in r.errors), str(r.errors))

    two = dict(base, det_points=[(0.0, 0.95), (0.0, 1.05)])
    r = validate_case(Case2D(det_delays=[0.0, 5e-5],
                             det_radii=[0.01, 0.02], **two))
    check('matched delays+radii validate', r.ok, str(r.errors))

    r = validate_case(Case2D(det_delays=[0.0], **two))
    check('a length mismatch is refused',
          any('one per point' in e for e in r.errors), str(r.errors))

    r = validate_case(Case2D(det_delays=[0.0, -1e-5], **two))
    check('a negative delay is refused',
          any('>= 0' in e for e in r.errors), str(r.errors))

    r = validate_case(Case2D(activation='none', det_delays=[1e-5], **base))
    check('delays with activation none are refused',
          any('needs detonation points' in e for e in r.errors),
          str(r.errors))

    # native mode never carries any of it
    from blastlab.core.case import Case1D
    r = validate_case(Case1D(radius_m=2.0, charge_kg=1.0,
                             cell_size_m=0.02))
    check('native case: silent on all of it',
          not any('Giroux' in n for n in r.notes)
          and not any('point' in e for e in r.errors), str(r.errors))


def chain_stage_checks():
    """B5: an auto-wired chain must be validated per stage BEFORE it
    starts - a foam stage fed by a profile used to reach the backend and
    die there with a traceback."""
    from blastlab.core.chain import stage_errors
    from blastlab.core.case import Case1D

    def wired(solver2, solver1=None):
        """The 1D -> 2D wiring ChainPanel._run performs.

        N5-4: `solver1` defaults to `solver2` so the pair is a legal
        same-solver chain. It used to be left at Case1D's 'native'
        default, which made every check below a native -> blastFoam
        hand-off - the exact combination now refused.
        """
        c1 = Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.02,
                    solver=solver1 or solver2, profile_file='p1.txt')
        c2 = Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                    cell_size_m=0.02, charge=1.0, center=(0.0, 1.0),
                    solver=solver2, init_mode='profile1d',
                    profile_file_in='p1.txt')
        return [1, 2], {1: c1, 2: c2}

    # N7 (T41): a blastFoam stage fed by a profile is accepted - the
    # remapped state is written into 0/ as nonuniform internalFields
    errs = stage_errors(*wired('blastfoam'))
    check('chain: foam stage fed by a profile is accepted',
          errs == [], str(errs))
    z = wired('blastfoam')
    z[1][2].charge_refine = 'zone'
    check('chain: profile + refinement zones is still refused',
          any('refinement zones' in e for e in stage_errors(*z)),
          str(stage_errors(*z)))
    # T70: AMR, unlike static zones, IS available to a profile stage -
    # the t = 0 mesh under AMR is the uniform base mesh, which is
    # exactly the one the remapped state is written on
    a = wired('blastfoam')
    a[1][2].amr_levels = 2
    check('chain: profile + AMR is accepted',
          stage_errors(*a) == [], str(stage_errors(*a)))
    rep_a = validate_case(a[1][2], pending_inputs=True)
    check('chain: profile + AMR says the state lands on the base mesh',
          rep_a.amr_levels == 2
          and any('base mesh and the AMR refines' in n
                  for n in rep_a.notes), str(rep_a.notes))
    az = wired('blastfoam')
    az[1][2].amr_levels = 2
    az[1][2].refine_zones = [(0.0, 0.5, 0.5, 1.5, 1)]
    check('chain: profile + AMR + zones is refused (mutually exclusive)',
          any('mutually exclusive' in e for e in stage_errors(*az)),
          str(stage_errors(*az)))

    check('chain: the same wiring is fine on the native solver',
          stage_errors(*wired('native')) == [],
          str(stage_errors(*wired('native'))))

    # N5-4: a blastFoam stage may not be fed a NATIVE profile. The
    # native solvers normally run eos='idealGas'; blastFoam always runs
    # JWL products and back-derives internal energy from the pressure
    # field it is handed (guide 5.9), so the hand-off silently inflates
    # the product cells by (gamma_air - 1) / omega = 33 %. Invisible
    # until B0 was fixed, because blastFoam used to throw that pressure
    # away and reset the products to pRef.
    mixed = stage_errors(*wired('blastfoam', solver1='native'))
    check('chain: native -> foam hand-off is refused',
          len(mixed) == 1, str(mixed))
    check('chain: the refusal names the stage that is fed',
          mixed and mixed[0].startswith('Stage 2 (2D):'), str(mixed))
    check('chain: the refusal says why and what to do',
          mixed and 'JWL' in mixed[0] and '33' in mixed[0]
          and 'Run the stage before it on blastFoam' in mixed[0],
          str(mixed))
    # the other direction carries `e` straight through - no EOS
    # inversion anywhere - so it must stay allowed
    check('chain: foam -> native hand-off is still allowed',
          stage_errors(*wired('native', solver1='blastfoam')) == [],
          str(stage_errors(*wired('native', solver1='blastfoam'))))

    # the pending-input waiver must stay narrow: outside a chain a
    # missing profile is still an error, and it waives nothing else
    lone = Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                  cell_size_m=0.02, charge=1.0, center=(0.0, 1.0),
                  init_mode='profile1d', profile_file_in='nope.txt')
    check('missing profile refused by default',
          any('not found' in e for e in validate_case(lone).errors))
    check('pending_inputs waives only the existence check',
          not any('not found' in e for e in
                  validate_case(lone, pending_inputs=True).errors))
    check('pending_inputs does not waive a missing filename',
          any('required for remap' in e for e in validate_case(
              Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                     cell_size_m=0.02, charge=1.0, center=(0.0, 1.0),
                     init_mode='profile1d', profile_file_in=''),
              pending_inputs=True).errors))

    # ordinary per-stage errors are surfaced too, stage-prefixed
    stages, cases = wired('native')
    cases[2] = Case2D(geometry='axisymmetric', Lx=40.0, Ly=40.0,
                      cell_size_m=0.002, charge=1000.0,
                      center=(0.0, 20.0), solver='native')
    errs = stage_errors(stages, cases)
    check('chain: a plain validation error is stage-prefixed',
          bool(errs) and all(e.startswith('Stage ') for e in errs),
          str(errs))


def shared_constant_checks():
    """A5: validate_case and the solvers must gate on the SAME numbers.

    MIN_EXP_CELLS and the 2D caps used to be re-typed as literals in
    solver1d/2d/3d, so the strip could accept a case the solver then
    refused (or the other way round) after any edit to constants.py.
    """
    import inspect
    from blastlab.core import constants
    from blastlab.core import case as case_mod
    from blastlab.solvers import solver1d, solver2d, solver3d

    print("")
    print("A5: guard-rail constants are shared, not re-typed")
    for name in ('MIN_EXP_CELLS', 'CELLS_2D_WARN', 'CELLS_2D_MAX',
                 'CELLS_WARN', 'CELLS_REFUSE'):
        want = getattr(constants, name)
        check(f'{name} reaches validate_case unchanged',
              getattr(case_mod, name, None) == want)
    for mod, names in ((solver1d, ('MIN_EXP_CELLS',)),
                       (solver2d, ('MIN_EXP_CELLS', 'CELLS_2D_WARN',
                                   'CELLS_2D_MAX')),
                       (solver3d, ('MIN_EXP_CELLS', 'CELLS_WARN',
                                   'CELLS_REFUSE'))):
        for name in names:
            check(f'{mod.__name__.split(".")[-1]} uses '
                  f'constants.{name}',
                  getattr(mod, name, None) == getattr(constants, name))
        src = inspect.getsource(mod)
        check(f'{mod.__name__.split(".")[-1]} has no re-typed '
              f'MIN_EXP_CELLS literal', 'MIN_EXP_CELLS = ' not in src)
    src2 = inspect.getsource(solver2d)
    check('solver2d has no re-typed 2D cap literals',
          '8_000_000' not in src2 and '2_000_000' not in src2)




def run_plan_checks():
    """N17/T48: the cell caps follow the WSL VM's RAM once a probe has
    run. N21: when it has not, they assume a small VM rather than
    falling back to the fixed constants."""
    from blastlab.solvers.foam import env
    print("\nT48/N21: memory-derived cell caps")

    def case(dx):
        return Case3D(Lx=4.0, Ly=4.0, Lz=4.0, cell_size_m=dx,
                      charge=4000.0, center=(2.0, 2.0, 2.0),
                      gauges=[(3.0, 2.0, 2.0)], solver='blastfoam')

    old = tuple(getattr(env, a) for a in _HW_ATTRS)
    try:
        # (a) no probe yet -> conservative caps. This check INVERTS at
        # N21: it used to assert that an unprobed machine still allowed
        # 8M cells, which is the permissive-on-ignorance bug itself.
        env.forget_hardware()
        rep = validate_case(case(0.02))          # 8M cells
        check('no hardware probe -> conservative caps refuse 8M cells',
              bool(cells_err(rep)), str(rep.errors))
        check('no hardware probe -> the refusal says the size is unknown '
              'and how to fix it',
              any('assumed' in e and 'Re-detect' in e
                  for e in cells_err(rep)), str(rep.errors))
        check('no hardware probe -> a warning, not just an error',
              any('WSL hardware not detected' in w for w in rep.warnings),
              str(rep.warnings))
        check('no hardware probe -> the rank note still explains itself',
              any(n.startswith('Parallel run: ') for n in rep.notes),
              str(rep.notes))

        # (a2) a case that fits the assumption still validates: an
        # unknown machine must be cautious, not unusable
        rep = validate_case(case(0.05))          # 512k cells
        check('no hardware probe -> a small case still runs',
              not cells_err(rep), str(rep.errors))

        # (a3) values restored from settings are CACHED: usable, and
        # said out loud, so the caps are not silently a week old
        env.forget_hardware()
        env.prime_hardware(cores=8, ram_gb=64)   # source defaults to CACHED
        rep = validate_case(case(0.02))
        check('cached hardware -> 8M cells allowed, with a note saying '
              'the numbers are from an earlier session',
              not cells_err(rep)
              and any('earlier session' in n for n in rep.notes),
              str(rep.notes))

        # (b) a 4 GB VM cannot hold 8M cells at ~2.7 KB each
        env.forget_hardware()
        env.prime_hardware(cores=8, ram_gb=4)
        rep = validate_case(case(0.02))
        errs = cells_err(rep)
        check('4 GB VM -> 8M cells refused', bool(errs), str(rep.errors))
        check('the refusal names the VM, the per-cell cost and the fix',
              any('GB WSL VM' in e and 'KB/cell' in e
                  and '.wslconfig' in e for e in errs), str(errs))
        # re-baselined 2026-09-10 with BYTES_PER_CELL 2650 -> 2700
        check('the memory cap is ~1.1M cells, not the fixed 120M',
              any('1,113,510' in e for e in errs), str(errs))

        # (c) the same VM is fine with a grid that fits
        rep = validate_case(case(0.05))          # 512k cells
        check('4 GB VM -> 512k cells allowed', not cells_err(rep),
              str(rep.errors))
        check('rank count is RAM-limited on a 4 GB VM',
              any('2 MPI ranks' in n and 'GB at' in n
                  for n in rep.notes), str(rep.notes))

        # (d) a big VM lifts both the cap and the rank count
        env.forget_hardware()
        env.prime_hardware(cores=8, ram_gb=64)
        rep = validate_case(case(0.02))
        check('64 GB VM -> 8M cells allowed again', not cells_err(rep),
              str(rep.errors))
        check('rank count is core-limited on a big VM',
              any('physical cores' in n for n in rep.notes),
              str(rep.notes))
    finally:
        for a, v in zip(_HW_ATTRS, old):
            setattr(env, a, v)


def main():
    run_plan_checks()
    # N21: these cases test the CAPS, so the hardware they are capped
    # against must be pinned. Before N21 they ran against whatever the
    # ambient env cache happened to hold - which was "unknown" here, and
    # "unknown" used to mean the most permissive caps in the app. Now it
    # means the most conservative ones, so an unpinned run would refuse
    # every case below and the suite would silently invert.
    from blastlab.solvers.foam import env
    from blastlab.core import hardware
    old = tuple(getattr(env, a) for a in _HW_ATTRS)
    old_host = (hardware._host_ram_gb, hardware._host_ram_src,
                hardware._host_probed)
    try:
        env.forget_hardware()
        env.prime_hardware(cores=8, ram_gb=512, source=hardware.MEASURED)
        # N21: the NATIVE caps follow the Windows host's RAM, so pin that
        # too - otherwise this suite passes or fails by which machine
        # runs it (a 7 GB laptop derives a 7.2M-cell 3D cap).
        hardware.forget_host()
        hardware.prime_host(ram_gb=256, source=hardware.MEASURED)
        _cap_checks()
    finally:
        for a, v in zip(_HW_ATTRS, old):
            setattr(env, a, v)
        (hardware._host_ram_gb, hardware._host_ram_src,
         hardware._host_probed) = old_host

    programmed_ignition_checks()
    chain_stage_checks()
    shared_constant_checks()
    amr_cap_checks()
    axisym_pin_note_checks()
    thin_obstacle_warn_checks()
    write_budget_checks()
    gauge_in_obstacle_checks()

    if FAIL:
        print(f"\nCASE VALIDATE: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("\nCASE VALIDATE: PASS")
    return 0


#: env hardware-cache attributes to save/restore around a pinned block
_HW_ATTRS = ('_cores', '_slots', '_ram_gb',
             '_cores_src', '_slots_src', '_ram_src',
             '_cores_tried', '_slots_tried', '_ram_tried')


def _cap_checks():
    # ~64M cells: 40 m cube at 0.1 m with a large charge. The charge is
    # big enough (r_exp = 0.85 m) that the 0.1 m cell already gives the
    # 8 cells across the radius blastFoam wants (T39), so these cases
    # test the CAPS and not the charge auto-refinement.
    big3 = dict(Lx=40.0, Ly=40.0, Lz=40.0, cell_size_m=0.1,
                charge=4000.0, center=(20.0, 20.0, 20.0))

    # T1: native 3D refuses above CELLS_REFUSE
    rep = validate_case(Case3D(solver='native', **big3))
    check('native 3D big refused', bool(cells_err(rep)),
          f'errors={rep.errors}')
    check('native cap constant sane', rep.n_cells > CELLS_REFUSE)

    # T2: same grid on blastfoam is allowed (warn only)
    rep = validate_case(Case3D(solver='blastfoam', **big3))
    check('foam 3D big allowed', not cells_err(rep),
          f'errors={rep.errors}')
    check('foam 3D big warns', any('Large grid' in w for w in rep.warnings)
          and rep.n_cells > FOAM_CELLS_WARN)

    # T3: blastfoam still refuses beyond its own (much higher) cap
    huge3 = dict(big3, cell_size_m=0.05)          # ~512M cells
    rep = validate_case(Case3D(solver='blastfoam', **huge3))
    check('foam 3D huge refused', bool(cells_err(rep)))
    check('foam refuse names its cap',
          any(f'{FOAM_CELLS_REFUSE:,}' in e for e in cells_err(rep)))

    # T4: 2D - grid over the native 8M cap allowed on blastfoam
    big2 = dict(geometry='planar', Lx=80.0, Ly=80.0, cell_size_m=0.025,
                charge=1000.0, center=(40.0, 40.0))   # ~10.2M cells
    rep = validate_case(Case2D(solver='native', **big2))
    check('native 2D big refused', bool(cells_err(rep)))
    rep = validate_case(Case2D(solver='blastfoam', **big2))
    check('foam 2D big allowed', not cells_err(rep),
          f'errors={rep.errors}')

    # T6: obstacles on blastfoam - allowed in 3D, refused in 2D
    small3 = dict(Lx=5.0, Ly=5.0, Lz=5.0, cell_size_m=0.1,
                  charge=100.0, center=(2.5, 2.5, 2.5))
    rep = validate_case(Case3D(solver='blastfoam',
                               obstacles=[(3.5, 4.0, 2.0, 3.0, 0.0, 2.0)],
                               **small3))
    check('foam 3D obstacle allowed',
          not any('Obstacle' in e for e in rep.errors),
          f'errors={rep.errors}')
    check('foam 3D obstacle noted',
          any('carved out of the mesh' in n for n in rep.notes))
    rep = validate_case(Case2D(solver='blastfoam', geometry='planar',
                               Lx=5.0, Ly=5.0, cell_size_m=0.1,
                               charge=10.0, center=(2.5, 2.5),
                               obstacles=[(3.5, 4.0, 2.0, 3.0)]))
    check('foam 2D obstacle allowed',
          not any('Obstacle' in e for e in rep.errors)
          and any('carved out of the mesh' in n for n in rep.notes),
          f'errors={rep.errors}')
    rep = validate_case(Case3D(solver='blastfoam',
                               obstacles=[(2.4, 3.0, 2.4, 3.0, 2.4, 3.0)],
                               **small3))
    check('foam 3D charge-overlap still refused',
          any('overlaps obstacle' in e for e in rep.errors),
          f'errors={rep.errors}')

    # T5: small case unaffected on both backends (100 kg -> r_exp 0.245,
    # refined dx 0.049 -> ~1.1M cells, under every warn threshold)
    small = dict(Lx=5.0, Ly=5.0, Lz=5.0, cell_size_m=0.1,
                 charge=100.0, center=(2.5, 2.5, 2.5))
    for solver in ('native', 'blastfoam'):
        rep = validate_case(Case3D(solver=solver, **small))
        check(f'{solver} small clean', not cells_err(rep)
              and not any('Large grid' in w for w in rep.warnings))

    afterburn_calibration_checks()


def afterburn_calibration_checks():
    """P1-4 (owner decision 2026-09-09): only TNT's afterburn is
    calibrated. The note used to claim 'calibrated against
    Kingery-Bulmash' for every material, including the five whose Q0 is
    an oxygen-balance estimate - so a user could quote an uncalibrated
    number believing it was fitted to data."""
    print()
    print("P1-4: afterburn says which materials are calibrated")

    def msgs(mat, ab='miller'):
        rep = validate_case(Case2D(solver='blastfoam', material=mat,
                                   afterburn=ab))
        return ([w for w in rep.warnings if 'fterburn' in w],
                [n for n in rep.notes if 'fterburn' in n])

    warns, notes = msgs('TNT')
    check('TNT: a note, no warning', not warns and len(notes) == 1, notes)
    check('TNT: still says it is calibrated',
          notes and 'calibrated against Kingery-Bulmash' in notes[0])

    for mat in ('C4', 'HMX', 'PETN', 'ANFO'):
        warns, notes = msgs(mat)
        check(f'{mat}: warned, not quietly noted',
              len(warns) == 1 and not notes, (warns, notes))
        check(f'{mat}: says NOT calibrated and why',
              warns and 'NOT calibrated' in warns[0]
              and 'oxygen balance' in warns[0], warns)
        check(f'{mat}: does not claim a KB calibration',
              warns and 'calibrated against Kingery-Bulmash' not in warns[0])

    for mat in ('TNT', 'C4'):
        warns, notes = msgs(mat, ab='none')
        check(f'{mat}: silent while afterburn is off',
              not warns and not notes, (warns, notes))


def axisym_pin_note_checks():
    """UX-04: axisym pins the burst to the axis (by design), but the pin
    used to be silent - a case file carrying x != 0 was recentred
    without a word."""
    print()
    print("UX-04: axisym says when it ignores burst x")

    rep = validate_case(Case2D(geometry='axisymmetric',
                               center=(1.0, 2.0)))
    check('axisym with x != 0: a note says x is ignored',
          any('burst x = 1 is ignored' in n for n in rep.notes),
          str(rep.notes))
    rep = validate_case(Case2D(geometry='axisymmetric',
                               center=(0.0, 2.0)))
    check('axisym with x = 0: no such note',
          not any('is ignored' in n for n in rep.notes), str(rep.notes))
    rep = validate_case(Case2D(geometry='planar', center=(2.0, 2.0)))
    check('planar keeps its burst x, no note',
          not any('is ignored' in n for n in rep.notes), str(rep.notes))


def gauge_in_obstacle_checks():
    """UXR-2 / D201 (GUI-11 T8): a gauge strictly inside an obstacle box
    is dropped by both solvers, so Setup warns - exactly one new warning,
    and the case stays valid. A gauge on the face or outside the box gets
    none (open-box test, as scaled_distance.where's `inside`)."""
    print()
    print("gauge inside an obstacle: warned, not refused")

    def new_warnings(rep, ref):
        return [w for w in rep.warnings if w not in ref.warnings]

    for solver in ('native', 'blastfoam'):
        two = dict(geometry='axisymmetric', Lx=4.0, Ly=4.0,
                   cell_size_m=0.05, charge=1.0, center=(0.0, 1.0),
                   obstacles=[(1.2, 1.6, 0.0, 1.0)], solver=solver)
        ref = validate_case(Case2D(gauges=[], **two))
        rep = validate_case(Case2D(gauges=[(1.4, 0.3)], **two))
        got = new_warnings(rep, ref)
        check(f'2D {solver}: a gauge inside Wall 1 gets exactly the new '
              f'warning', got == ['Gauge (1.4, 0.3) inside an obstacle - '
                                  'will be dropped'], str(got))
        check(f'2D {solver}: it is a warning, not an error',
              rep.errors == ref.errors, str(rep.errors))
        for pt, where in (((1.2, 0.3), 'on the face'),
                          ((1.4, 1.0), 'on the top face'),
                          ((1.0, 0.3), 'in front of it'),
                          ((1.4, 1.5), 'above it')):
            got = new_warnings(validate_case(Case2D(gauges=[pt], **two)),
                               ref)
            check(f'2D {solver}: a gauge {where} gets none', got == [],
                  str(got))

        three = dict(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.1, charge=1.0,
                     center=(1.0, 1.0, 1.0),
                     obstacles=[(1.5, 1.8, 0.5, 1.5, 0.0, 1.0)],
                     solver=solver)
        ref = validate_case(Case3D(gauges=[], **three))
        rep = validate_case(Case3D(gauges=[(1.6, 1.0, 0.5)], **three))
        got = new_warnings(rep, ref)
        check(f'3D {solver}: a gauge inside Wall 1 gets exactly the new '
              f'warning', got == ['Gauge (1.6, 1.0, 0.5) inside an '
                                  'obstacle - will be dropped'], str(got))
        check(f'3D {solver}: it is a warning, not an error',
              rep.errors == ref.errors, str(rep.errors))
        for pt, where in (((1.5, 1.0, 0.5), 'on the face'),
                          ((1.6, 1.0, 1.0), 'on the top face'),
                          ((1.9, 1.0, 0.5), 'behind it')):
            got = new_warnings(validate_case(Case3D(gauges=[pt], **three)),
                               ref)
            check(f'3D {solver}: a gauge {where} gets none', got == [],
                  str(got))


def thin_obstacle_warn_checks():
    """A wall carved a single cell thick is a numerical hazard (run
    20260915-090553: 0.3 m wall on a 0.5 m base mesh -> deltaT collapse
    -> SIGFPE in decode). Setup must say so before the run."""
    print()
    print("thin obstacle: single-cell wall warns in Setup")

    def rep_for(cell, wall_hi, **kw):
        return validate_case(
            Case2D(geometry='axisymmetric', Lx=10.0, Ly=10.0,
                   cell_size_m=cell, init_mode='profile1d',
                   profile_file_in='missing_ok.txt',
                   obstacles=[(5.0, wall_hi, 0.0, 5.0)], **kw),
            pending_inputs=True)

    def thin_warns(rep):
        return [w for w in rep.warnings if 'one cell thick' in w]

    # the incident: blastfoam + AMR (plan.dx_base path)
    rep = rep_for(0.5, 5.3, solver='blastfoam', amr_levels=2)
    w = thin_warns(rep)
    check('0.3 m wall on 0.5 m foam+AMR base mesh warns', bool(w),
          str(rep.warnings))
    check('the warning names the fix (cell <= 0.15 m)',
          bool(w) and '0.15' in w[0], w[0] if w else '')
    check('foam: says AMR levels do not help (carve is base-mesh)',
          bool(w) and 'AMR levels do not help' in w[0],
          w[0] if w else '')
    # same geometry, native solver (plan is None -> effective-dx path)
    rep = rep_for(0.5, 5.3)
    w = thin_warns(rep)
    check('native solver warns too', bool(w), str(rep.warnings))
    check('native: no AMR clause (no AMR to reach for)',
          bool(w) and 'AMR' not in w[0], w[0] if w else '')
    # controls: a 2-cell wall and a refined base are both silent
    rep = rep_for(0.5, 6.0, solver='blastfoam', amr_levels=2)
    check('1.0 m wall (2 cells): silent', not thin_warns(rep),
          str(rep.warnings))
    rep = rep_for(0.1, 5.3, solver='blastfoam', amr_levels=2)
    check('0.1 m base cell (3-cell wall): silent', not thin_warns(rep),
          str(rep.warnings))

    _fixed_dt_checks()


def _fixed_dt_checks():
    """A PRESCRIBED STEP HAS NO CFL GUARD, which is the point and the
    risk both. `adjustTimeStep no` means blastFoam takes that step
    whatever the flow does, so a case that is not quiescent can sail
    past the stability limit without a word - the run does not stop, it
    produces a wrong answer.

    It exists for verification cases that are deliberately at rest:
    blastFoam takes its Courant number from the face fluxes, so an
    exactly uniform field at exactly zero velocity has Co = 0 and
    `Time::adjustDeltaT` divides by it (a SIGFPE, measured, in
    `_e2e_gamma_interface.py`). Anything that actually moves should
    leave it at 0.
    """
    from blastlab.core.case import Case3D, validate_case

    def rep_dt(dt, dx=0.05, cfl=0.3):
        return validate_case(Case3D(
            solver='blastfoam', Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=dx,
            charge=0.5, center=(0.5, 0.5, 0.5), charge_refine='zone',
            cfl=cfl, t_end=0.01, fixed_dt=dt))

    # The guard's OWN messages, not `rep.ok`: this throwaway geometry
    # has charge-resolution complaints of its own, and a check that
    # reads the whole report would be measuring those instead.
    def warned(rep):
        return [m for m in rep.warnings if 'Courant limiter' in m]

    def refused(rep):
        return [m for m in rep.errors if 'Courant number' in m]

    print('\n  a fixed time step turns the Courant limiter off')
    check('an adaptive case says nothing about it',
          not warned(rep_dt(0.0)) and not refused(rep_dt(0.0)))
    # 2e-6 s on a 0.05 m cell is Co = 0.014 at the ambient sound speed:
    # the step the gamma-interface case runs at, and comfortably inside
    # the limit. It still warns, because the limiter is off either way.
    ok = rep_dt(2.0e-6)
    check('a safe fixed step is allowed and STILL warns that the '
          'limiter is off - being inside the limit today is not the '
          'same as being protected',
          warned(ok) and not refused(ok), str(warned(ok))[:80])
    check('and the warning says this is for quiescent verification '
          'cases, so nobody reaches for it to speed a real run up',
          any('QUIESCENT' in m for m in warned(ok)))
    # 1e-4 s on the same cell is Co = 0.68 at AMBIENT sound speed alone,
    # and a chamber holds gas far hotter and faster than ambient.
    bad = rep_dt(1.0e-4)
    check('a step past the CFL limit is an ERROR, not a warning - '
          'nothing downstream will catch it, because the limiter that '
          'would have is the thing being switched off',
          refused(bad) and not warned(bad), str(refused(bad))[:100])
    check('and it scales with the CELL, not just the step: the same '
          'step on a ten-times coarser mesh is a warning again',
          warned(rep_dt(1.0e-4, dx=0.5))
          and not refused(rep_dt(1.0e-4, dx=0.5)))

    # THE SPEED COMES FROM THE GAS IN THE CASE, and that correction
    # matters in the direction that hurts: ambient air is a LOWER bound
    # on the wave speed in a chamber, and checking a stability limit
    # against a lower bound makes an unsafe step look safe. A chamber
    # case carries its own T and gamma, and the wave that matters is
    # |u| + c rather than c, so the estimate is doubled for the jet.
    print('\n  and the speed it checks against comes from the gas')
    hot = validate_case(Case3D(
        solver='blastfoam', Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.05,
        charge=0.5, center=(0.5, 0.5, 0.5), charge_refine='zone',
        cfl=0.3, t_end=0.01, fixed_dt=2.0e-6,
        chamber_state=dict(T=2400.0, gamma_p=1.24, R_p=366.67)))
    check('a case that declares a hot gas is judged against THAT, not '
          'against ambient air',
          warned(hot) and any('chamber gas' in m for m in warned(hot)),
          str(warned(hot))[:100])
    check('and a case that declares none says its bound is a LOWER one, '
          'rather than presenting it as the answer',
          any('LOWER bound' in m for m in warned(rep_dt(2.0e-6))))
    # 2e-6 s is safe at 288 K and NOT safe at 2400 K, on the same mesh:
    # c goes as sqrt(T), so the hot gas is nearly three times faster.
    scald = validate_case(Case3D(
        solver='blastfoam', Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.01,
        charge=0.5, center=(0.5, 0.5, 0.5), charge_refine='zone',
        cfl=0.3, t_end=0.01, fixed_dt=2.0e-6,
        chamber_state=dict(T=2400.0, gamma_p=1.24, R_p=366.67)))
    cool = validate_case(Case3D(
        solver='blastfoam', Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.01,
        charge=0.5, center=(0.5, 0.5, 0.5), charge_refine='zone',
        cfl=0.3, t_end=0.01, fixed_dt=2.0e-6,
        chamber_state=dict(T=288.0, gamma_p=1.24, R_p=366.67)))
    check('so a step that passes at 288 K is REFUSED at 2400 K on the '
          'same mesh - which is the whole reason not to use ambient',
          refused(scald) and not refused(cool),
          f'hot: {len(refused(scald))} error(s), '
          f'cool: {len(refused(cool))}')


def write_budget_checks():
    """HD1-15: the write budget's rules, one case each. The messages are
    matched by their own words - the throwaway geometry has complaints of
    its own, which a check on `rep.ok` would be measuring instead."""
    print('\n  HD1-15: the write budget')

    def rep_for(dim=3, **kw):
        base = dict(solver='blastfoam', t_end=0.01, n_snapshots=6)
        if dim == 3:
            base.update(Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.05,
                        charge=0.5, center=(0.5, 0.5, 0.5),
                        charge_refine='zone')
            base.update(kw)
            return validate_case(Case3D(**base))
        base.update(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                    cell_size_m=0.02, charge=1.0, center=(0.0, 1.0))
        base.update(kw)
        return validate_case(Case2D(**base))

    def said(rep, words, where=('errors', 'warnings', 'notes')):
        return [m for w in where for m in getattr(rep, w) if words in m]

    off = rep_for(write_budget=0)
    check('budget 0: not one word about it',
          not said(off, 'rite budget') and not said(off, 'budget'),
          str(said(off, 'budget')))
    for bad in (-1, 2.5, True, '60'):
        check(f'budget {bad!r} is refused: a whole number, 0 or more',
              said(rep_for(write_budget=bad), 'whole number of writes',
                   ('errors',)))
    check('a budget without an explicit end time is an error (the '
          'automatic end is a 10x cap)',
          said(rep_for(write_budget=60, t_end=0.0), 'explicit end time',
               ('errors',)))
    check('a budget of 1 is an error: at least 2 writes',
          said(rep_for(write_budget=1), 'at least 2 writes', ('errors',)))
    ok = rep_for(write_budget=60)
    check('a budget of 60 with t_end raises no budget error',
          not said(ok, 'budget', ('errors',)), str(ok.errors))
    check('the native solver notes that it ignores the budget',
          said(rep_for(write_budget=60, solver='native'),
               'native solver ignores it', ('notes',)))
    check('below 4 x n_snapshots is a warning, not an error',
          said(rep_for(write_budget=10), 'below 4 x n_snapshots',
               ('warnings',))
          and not said(rep_for(write_budget=10), 'budget', ('errors',)))
    check('and at 4 x n_snapshots it is silent',
          not said(rep_for(write_budget=24), 'below 4 x n_snapshots'))
    term = dict(x_lo='transmit', x_hi='transmit', y_lo='terminate',
                y_hi='transmit', z_lo='reflect', z_hi='transmit')
    check('a terminate side normal to the live slice gets a note: '
          'arrival there is seen at writes only',
          said(rep_for(write_budget=60, bcs=term, slice_axis='y'),
               'normal to the live slice', ('notes',))
          and not said(rep_for(write_budget=60, bcs=term, slice_axis='z'),
                       'normal to the live slice'))
    check('a parallel AMR case gets a note: no purge',
          said(rep_for(write_budget=60, amr_levels=1,
                       charge_refine='global'), 'no purge', ('notes',)))
    check('and every budget case is told the disk it will take',
          said(ok, 'on the WSL disk', ('notes',))
          and said(rep_for(dim=2, write_budget=20), 'on the WSL disk',
                   ('notes',)))


if __name__ == '__main__':
    sys.exit(main())
