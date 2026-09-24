"""Characterisation: the validation helpers and the chain hand-off (Phase 3).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 3 moves the validation code
out of `core/case.py` into `services/validation.py`, and `core/chain.py`
into `services/chain.py`, leaving shims at the old paths.
`test_char_validation.py` already pins what `validate_case` says; this
pins, from the code as it was BEFORE the move, the pieces it does not:

  * `HANDOFF_MSG`, word for word (the chain panels and the writer show it);
  * `handoff_conflicts` on five stage/solver combinations;
  * `_charge_radius` with its default density (TNT) and an explicit one,
    sphere and 2D planar;
  * `C_AMB_AIR`, `BYTES_PER_CELL_WRITE`, `cap_distance`, `safety_cap_s`;
  * after the move: the old paths hand out the very objects (`is`) that
    `services/` owns, underscore names included, and importing the old
    `core.case` imports nothing from `solvers/`.

The values are literals rather than a golden file.

Run:  cd blastlab/tests && python test_char_services.py   (or under pytest)
"""
import sys

import pytest

import char_common as cc
from blastlab.core import case as core_case                # noqa: E402
from blastlab.core import chain as core_chain              # noqa: E402

REL = 1e-12

HANDOFF_TEXT = (
    'a blastFoam stage cannot be fed a profile produced by the native '
    'solver: the native hand-off carries an ideal-gas state and '
    'blastFoam re-derives internal energy from its pressure with the '
    'JWL products EOS, injecting ~33 % extra energy into the product '
    'cells. Run the stage before it on blastFoam, or run this stage on '
    'the native solver.')

#: (stages, {dim: solver}) -> the dims handoff_conflicts flags
HANDOFF_CASES = (
    ([1, 2, 3], {1: 'native', 2: 'blastfoam', 3: 'blastfoam'}, [2]),
    ([1, 2, 3], {1: 'blastfoam', 2: 'native', 3: 'blastfoam'}, [3]),
    ([2, 3], {2: 'native', 3: 'native'}, []),
    ([2], {2: 'native'}, []),
    ([1, 3], {1: 'native'}, []),
)

#: (dim, geometry, charge kg) -> (radius at default rho0, at rho0 = 850)
RADIUS_CASES = (
    (2, 'planar', 1.0, 0.013974338580521863, 0.0193515430661163),
    (2, 'planar', 25.0, 0.0698716929026093, 0.09675771533058149),
    (2, 'axisymmetric', 1.0, 0.052711809956185275, 0.0654883660769944),
    (3, None, 100.0, 0.24466654849214844, 0.3039700687145231),
    (3, None, 1e-3, 0.005271180995618528, 0.006548836607699442),
)


def _case(dim, geometry, charge):
    if dim == 2:
        return core_case.Case2D(geometry=geometry, charge=charge)
    return core_case.Case3D(charge=charge)


def test_handoff_msg_text():
    assert core_chain.HANDOFF_MSG == HANDOFF_TEXT


def test_handoff_conflicts():
    for stages, solvers, want in HANDOFF_CASES:
        got = core_chain.handoff_conflicts(stages, solvers)
        assert [d for d, _ in got] == want, (stages, solvers, got)
        assert all(m is core_chain.HANDOFF_MSG for _, m in got)


def test_charge_radius():
    for dim, geometry, charge, r_default, r_850 in RADIUS_CASES:
        c = _case(dim, geometry, charge)
        assert core_case._charge_radius(c) == pytest.approx(
            r_default, rel=REL), (dim, geometry, charge)
        assert core_case._charge_radius(c, None) == pytest.approx(
            r_default, rel=REL), (dim, geometry, charge)
        assert core_case._charge_radius(c, 850.0) == pytest.approx(
            r_850, rel=REL), (dim, geometry, charge)


def test_stop_time_helpers():
    assert core_case.C_AMB_AIR == pytest.approx(340.29399054347107, rel=REL)
    assert core_case.BYTES_PER_CELL_WRITE == 155
    c1 = core_case.Case1D(radius_m=2.0)
    c3 = core_case.Case3D(Lx=1.6, Ly=0.8, Lz=1.2)
    assert core_case.cap_distance(c1) == 2.0
    assert core_case.cap_distance(c3) == 1.6
    assert core_case.safety_cap_s(c1) == pytest.approx(
        20.0 / 340.29399054347107, rel=REL)
    assert core_case.safety_cap_s(c3) == pytest.approx(
        16.0 / 340.29399054347107, rel=REL)


#: every name the old core.case held that came from the validation code
VALIDATION_NAMES = (
    'validate_case', 'cap_distance', 'safety_cap_s', 'long_run_note',
    'C_AMB_AIR', 'BYTES_PER_CELL_WRITE', '_charge_radius', '_validate_solver',
    '_warn_long_end_time', '_validate_write_budget', '_hardware',
    'ValidationReport', 'MIN_EXP_CELLS', 'FOAM_EXP_CELLS', 'CELLS_2D_WARN',
    'CELLS_2D_MAX', 'CELLS_WARN', 'CELLS_REFUSE', 'FOAM_CELLS_WARN',
    'FOAM_CELLS_REFUSE', 'FOAM_VM_GB_ASSUMED', 'BYTES_PER_CELL',
    'ANIM_SCALES', 'JWL_TNT', 'BC_KINDS', 'normalize_bc', 'normalize_bcs')
CHAIN_NAMES = ('HANDOFF_MSG', 'handoff_conflicts', 'stage_errors',
               'validate_case')


def test_shims_reexport_services():
    """The old paths hand out the very objects services/ owns."""
    from blastlab.services import chain as s_chain
    from blastlab.services import validation as s_val
    bad = [n for n in VALIDATION_NAMES
           if getattr(core_case, n) is not getattr(s_val, n)]
    assert not bad, f'core.case copies, not re-exports: {bad}'
    bad = [n for n in CHAIN_NAMES
           if getattr(core_chain, n) is not getattr(s_chain, n)]
    assert not bad, f'core.chain copies, not re-exports: {bad}'


def test_core_case_import_pulls_no_solvers():
    """Importing the old path must not drag in the WSL backend: its
    imports of solvers.foam stay deferred inside the functions."""
    import subprocess
    code = ('import sys, blastlab.core.case, blastlab.core.chain; '
            'print(sorted(m for m in sys.modules '
            "if m.startswith(('blastlab.solvers', 'blastlab.output'))))")
    out = subprocess.run([sys.executable, '-c', code], cwd=cc.REPO,
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == '[]', out.stdout + out.stderr


def main():
    return cc.run_main('CHAR SERVICES', [
        test_handoff_msg_text, test_handoff_conflicts, test_charge_radius,
        test_stop_time_helpers, test_shims_reexport_services,
        test_core_case_import_pulls_no_solvers])


if __name__ == '__main__':
    sys.exit(main())
