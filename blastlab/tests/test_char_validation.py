"""Characterisation: pre-flight validation messages (Phase 0).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 0. Pins what
`core.case.validate_case` says about ten cases - native and blastFoam in
1D/2D/3D, an AMR case, a profile-initialised chain stage with
`pending_inputs=True`, a native case over the cell cap - and what
`core.assessment.validate` says about the HD 1.3 starter case: the
errors, warnings and notes VERBATIM and IN ORDER, and every numeric field
of the ValidationReport (the blastFoam RunPlan included). Phases 3 and 4
split `validate_case` by concern; the messages and their order must come
out the same.

The hardware the caps are computed against is pinned the way
`test_case_validate.py` pins it (8-core / 512 GB WSL VM, 64 GB host, all
MEASURED), and the WSL availability state is pinned at its import-time
value, so the goldens do not depend on this machine or on what else ran
in the process. Both are restored afterwards. Nothing here touches WSL:
`validate_case` only reads caches.

Run:  cd blastlab/tests && python test_char_validation.py [--update]
"""
import contextlib
import dataclasses
import sys

import char_common as cc
from blastlab.core import assessment, hardware            # noqa: E402
from blastlab.core.case import (Case1D, Case2D, Case3D,   # noqa: E402
                                validate_case)
from blastlab.core.constants import MIN_EXP_CELLS        # noqa: E402
from blastlab.models.result import ValidationReport      # noqa: E402
from blastlab.services import validation as sv           # noqa: E402
from blastlab.solvers.foam import env                    # noqa: E402

_ENV_ATTRS = ('_cores', '_slots', '_ram_gb',
              '_cores_src', '_slots_src', '_ram_src',
              '_cores_tried', '_slots_tried', '_ram_tried',
              '_state', '_detail', '_last_fail')
_HOST_ATTRS = ('_host_ram_gb', '_host_ram_src', '_host_probed')


@contextlib.contextmanager
def pinned_hardware():
    old_env = {a: getattr(env, a) for a in _ENV_ATTRS}
    old_host = {a: getattr(hardware, a) for a in _HOST_ATTRS}
    try:
        env.forget_hardware()
        env.prime_hardware(cores=8, ram_gb=512, source=hardware.MEASURED)
        hardware.forget_host()
        hardware.prime_host(64, hardware.MEASURED)
        # the import-time WSL state: never probed, so validate_case says
        # "will be verified at run start" rather than whatever a probe
        # earlier in this process found
        env._state, env._detail, env._last_fail = 'unchecked', '', 0.0
        yield
    finally:
        for a, v in old_env.items():
            setattr(env, a, v)
        for a, v in old_host.items():
            setattr(hardware, a, v)


# ── the ten cases ────────────────────────────────────────────────────────
_BCS_2D = dict(x_lo='reflect', x_hi='terminate',
               y_lo='reflect', y_hi='terminate')
_BCS_3D = dict(x_lo='terminate', x_hi='terminate', y_lo='terminate',
               y_hi='terminate', z_lo='reflect', z_hi='terminate')

BLAST_CASES = {
    'native_1d': (Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.02,
                         eos='JWL', gauge_radii=[0.5, 1.0, 1.5]), False),
    'native_2d': (Case2D(geometry='axisymmetric', Lx=1.2, Ly=1.6,
                         cell_size_m=0.02, charge=1.0, center=(0.0, 0.7),
                         bcs=dict(_BCS_2D),
                         obstacles=[(0.7, 0.9, 0.2, 0.5)],
                         n_snapshots=2, gauges=[(0.5, 0.7), (0.4, 0.2)]),
                  False),
    'native_3d': (Case3D(Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.025,
                         charge=8.0, center=(0.5, 0.5, 0.5),
                         obstacles=[(0.62, 0.72, 0.4, 0.6, 0.3, 0.7)],
                         n_snapshots=1, bcs=dict(_BCS_3D),
                         gauges=[(0.85, 0.5, 0.5), (0.5, 0.85, 0.5)]),
                  False),
    'foam_1d': (Case1D(radius_m=5.0, charge_kg=1.0, cell_size_m=0.005,
                       solver='blastfoam', afterburn='miller',
                       gauge_radii=[1.0, 2.0, 4.0]), False),
    'foam_2d': (Case2D(solver='blastfoam', gauges=[(1.0, 2.0), (2.0, 0.5)],
                       activation='programmedIgnition'), False),
    'foam_3d': (Case3D(solver='blastfoam', material='C4', n_procs=4,
                       gauges=[(1.2, 0.75, 0.75)], t_end=2e-3,
                       write_budget=8), False),
    # the AMR case `test_case_validate.py` shows validating clean
    'foam_3d_amr': (Case3D(solver='blastfoam', Lx=4.0, Ly=4.0, Lz=4.0,
                           cell_size_m=0.1, charge=8.0,
                           center=(2.0, 2.0, 2.0), amr_levels=4,
                           gauges=[(3.0, 2.0, 2.0)]), False),
    'native_2d_profile_pending': (
        Case2D(geometry='axisymmetric', Lx=3.0, Ly=6.0, cell_size_m=0.02,
               init_mode='profile1d', profile_file_in='stage1_profile.txt',
               center=(0.0, 3.0), eos='JWL', gauges=[(2.4, 3.0)]), True),
    'native_3d_over_cap': (Case3D(Lx=10.0, Ly=10.0, Lz=10.0,
                                  cell_size_m=0.01, charge=25.0,
                                  center=(5.0, 5.0, 5.0)), False),
}


def report_dict(rep):
    d = {f.name: getattr(rep, f.name) for f in dataclasses.fields(rep)}
    if d['run_plan'] is not None:
        d['run_plan'] = dataclasses.asdict(d['run_plan'])
    return d


def test_blast_cases():
    with pinned_hardware():
        got = {name: report_dict(validate_case(case, pending_inputs=pend))
               for name, (case, pend) in BLAST_CASES.items()}
    cc.check_json('validation_blast_cases.json', got)


def test_hd13_starter_case():
    case = cc.hd13_starter_case()
    with pinned_hardware():
        rep = assessment.validate(case)
    cc.check_json('validation_hd13_starter.json', report_dict(rep))


# ── Phase 4: the blocks validate_case is split into ─────────────────────
# One case per extracted function. Each runs the blocks in
# validate_case's order and checks against the golden above or against
# literal messages - no new golden.
GOLDEN_BLAST = 'validation_blast_cases.json'


def _upto(case, last, pending=False, hw=None):
    """Run the blocks of validate_case in order through `last` (a
    function name); returns (report, ctx, what `last` returned)."""
    rep = ValidationReport()
    ctx = sv._validate_common(case, rep)
    if last == '_validate_common' or ctx is None:
        return rep, ctx, ctx
    if case.dim == 1:
        return rep, ctx, sv._validate_1d(case, rep, ctx)
    steps = (('_validate_domain_and_charge',
              lambda: sv._validate_domain_and_charge(case, rep, ctx)),
             ('_validate_profile_init',
              lambda: sv._validate_profile_init(case, rep, ctx, pending)),
             ('_validate_refinement',
              lambda: sv._validate_refinement(case, rep, ctx)),
             ('_validate_caps',
              lambda: sv._validate_caps(case, rep, ctx, hw)),
             ('_validate_closing',
              lambda: sv._validate_closing(case, rep, ctx)))
    for name, step in steps:
        out = step()
        if name == last or out is False:
            return rep, ctx, out
    raise AssertionError(f'no block named {last}')


def _golden(name):
    return cc.load_json(GOLDEN_BLAST)[name]


def _same_as_golden(rep, name):
    return cc.dumps(report_dict(rep)) == cc.dumps(_golden(name))


def test_block_common():
    rep, ctx, _ = _upto(Case2D(cell_size_m=0.0), '_validate_common')
    assert ctx is None and rep.errors == ['Cell size must be > 0']
    assert not rep.warnings and not rep.notes
    # a fatal backend error stops before any geometry check
    rep, ctx, _ = _upto(Case2D(solver='nope', Lx=0.0), '_validate_common')
    assert ctx is None and rep.errors == ["Unknown solver backend 'nope'"]
    rep = validate_case(Case2D(solver='nope', Lx=0.0))
    assert rep.errors == ["Unknown solver backend 'nope'"]
    rep, ctx, _ = _upto(BLAST_CASES['native_2d'][0], '_validate_common')
    assert (ctx.foam, ctx.amr, ctx.n_exp) == (False, 0, MIN_EXP_CELLS)


def test_block_1d():
    with pinned_hardware():
        rep, _ctx, _ = _upto(BLAST_CASES['native_1d'][0], '_validate_1d')
    assert _same_as_golden(rep, 'native_1d')


def test_block_domain_and_charge():
    rep, _ctx, ok = _upto(Case3D(Lx=0.0), '_validate_domain_and_charge')
    assert ok is False and rep.errors == ['Domain extents must be > 0']
    rep, ctx, ok = _upto(BLAST_CASES['native_3d'][0],
                         '_validate_domain_and_charge')
    assert ok is True and ctx.init == 'charge'
    assert ctx.dims == (1.0, 1.0, 1.0)
    assert rep.r_exp == _golden('native_3d')['r_exp']


def test_block_profile_init():
    case = BLAST_CASES['native_2d_profile_pending'][0]
    rep, _ctx, _ = _upto(case, '_validate_profile_init', pending=True)
    assert not rep.errors
    rep, _ctx, _ = _upto(case, '_validate_profile_init', pending=False)
    assert rep.errors == [f'Profile file not found: {case.profile_file_in}']


def test_block_refinement():
    with pinned_hardware():
        rep, ctx, ok = _upto(BLAST_CASES['foam_3d_amr'][0],
                             '_validate_refinement')
    g = _golden('foam_3d_amr')
    assert ok is True and ctx.plan is not None and ctx.plan.amr == 4
    assert (rep.amr_levels, rep.lmax, rep.n_fine) == (
        g['amr_levels'], g['lmax'], g['n_fine'])


def test_block_caps_hardware_argument():
    """`hw=None` reads env.hardware() at call time (the golden); an
    explicit dict is used instead of it."""
    case = BLAST_CASES['foam_3d'][0]
    with pinned_hardware():
        rep, _ctx, _ = _upto(case, '_validate_closing')
        assert _same_as_golden(rep, 'foam_3d')
        rep, _ctx, _ = _upto(case, '_validate_closing', hw=env.hardware())
        assert _same_as_golden(rep, 'foam_3d')
        rep, _ctx, _ = _upto(case, '_validate_caps', hw={})
    assert any(w.startswith('WSL hardware not detected')
               for w in rep.warnings)


def test_block_closing():
    case = Case2D(geometry='axisymmetric', Lx=1.2, Ly=1.6, cell_size_m=0.02,
                  charge=1.0, center=(0.0, 0.7), bcs=dict(_BCS_2D),
                  gauges=[(5.0, 5.0)])
    with pinned_hardware():
        rep, ctx, _ = _upto(case, '_validate_caps')
        before = list(rep.warnings)
        sv._validate_closing(case, rep, ctx)
    # GUI-13 (c), owner Q2 2026-10-04: a wording change, no number
    assert rep.warnings == before + [
        'G1 (5.00, 5.00) m outside the domain - will be dropped']


def main():
    return cc.run_main('CHAR VALIDATION', [
        test_blast_cases, test_hd13_starter_case,
        test_block_common, test_block_1d, test_block_domain_and_charge,
        test_block_profile_init, test_block_refinement,
        test_block_caps_hardware_argument, test_block_closing])


if __name__ == '__main__':
    sys.exit(main())
