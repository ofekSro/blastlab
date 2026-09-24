"""Characterisation: the explosive material table (Phase 1).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 1 moves the table from
`solvers/foam/materials.py` to `core/materials.py` and leaves a shim at
the old path. This pins, from the code as it was BEFORE the move:

  * every `Material` and `Afterburn` row, field by field, and the
    `MATERIAL_NAMES` order (the combo/prompt order);
  * `E0` and `charge_radius` (sphere and 2D planar) on five masses;
  * `core.eos.material_jwl` for every name - 'TNT' (and the empty name)
    must return the `constants.JWL_TNT` OBJECT itself, because byte
    identity of the default run depends on it;
  * after the move: the shim re-exports the very same objects (`is`) as
    `core.materials`, so the importers that keep the old path see no
    difference.

The values are literals rather than a golden file: they are the table.

Run:  cd blastlab/tests && python test_char_materials.py   (or under pytest)
"""
import dataclasses
import sys

import pytest

import char_common as cc
from blastlab.core import constants                        # noqa: E402
from blastlab.core.eos import material_jwl                 # noqa: E402
from blastlab.solvers.foam import materials as old         # noqa: E402

REL = 1e-12

#: (A, B, R1, R2, omega, rho0, e0, vDet, Cv_products, Cv_reactants,
#:  Gamma_reactants, molWeight, Pcj)
MATERIAL_ROWS = {
    'TNT':  (3.712e11, 3.23e9, 4.15, 0.95, 0.30, 1630.0, 4.29e6, 6930.0,
             1400.0, 815.0, 0.25, 55.0, 2.1e10),
    'C4':   (6.0977e11, 1.295e10, 4.50, 1.40, 0.25, 1601.0, 5.56e6, 8193.0,
             1400.0, 815.0, 0.25, 55.0, 2.8e10),
    'RDX':  (7.78e11, 7.07e9, 4.485, 1.068, 0.30, 1770.0, 5.15e6, 8750.0,
             1400.0, 815.0, 0.25, 55.0, 3.4e10),
    'HMX':  (7.783e11, 7.071e9, 4.20, 1.00, 0.30, 1890.0, 5.50e6, 9100.0,
             1400.0, 815.0, 0.25, 55.0, 3.9e10),
    'PETN': (6.17e11, 1.69e10, 4.40, 1.20, 0.25, 1770.0, 5.81e6, 8400.0,
             1400.0, 815.0, 0.25, 55.0, 3.1e10),
    'ANFO': (4.95e10, 1.89e9, 3.90, 1.10, 0.35, 850.0, 3.80e6, 4500.0,
             1400.0, 815.0, 0.25, 55.0, 5.0e9),
}

#: (Q0, a, n, m, pMin)
AFTERBURN_ROWS = {
    'TNT':  (2.00e6, 1.45e-5, 1.0, 0.5, 1.5e5),
    'C4':   (0.57e6, 1.45e-5, 1.0, 0.5, 1.5e5),
    'RDX':  (0.58e6, 1.45e-5, 1.0, 0.5, 1.5e5),
    'HMX':  (0.58e6, 1.45e-5, 1.0, 0.5, 1.5e5),
    'PETN': (0.27e6, 1.45e-5, 1.0, 0.5, 1.5e5),
    'ANFO': (0.10e6, 1.45e-5, 1.0, 0.5, 1.5e5),
}

E0_VALUES = {
    'TNT': 6992700000.0, 'C4': 8901560000.0, 'RDX': 9115500000.0,
    'HMX': 10395000000.0, 'PETN': 10283700000.0, 'ANFO': 3230000000.0,
}

#: (mass, planar) -> radius [m], per material
RADIUS_INPUTS = ((1e-3, False), (1.0, False), (100.0, False),
                 (1.0, True), (25.0, True))
RADII = {
    'TNT':  (0.005271180995618528, 0.052711809956185275, 0.24466654849214844,
             0.013974338580521863, 0.0698716929026093),
    'C4':   (0.005302817566152793, 0.05302817566152792, 0.2461349880174049,
             0.014100333922620886, 0.07050166961310443),
    'RDX':  (0.005128370281018356, 0.05128370281018356, 0.23803786231006427,
             0.013410298053702882, 0.06705149026851441),
    'HMX':  (0.005017451642478435, 0.05017451642478435, 0.23288947516919997,
             0.012977593351533746, 0.06488796675766872),
    'PETN': (0.005128370281018356, 0.05128370281018356, 0.23803786231006427,
             0.013410298053702882, 0.06705149026851441),
    'ANFO': (0.006548836607699442, 0.0654883660769944, 0.3039700687145231,
             0.0193515430661163, 0.09675771533058149),
}

#: every name the shim must keep importable from the old path
SHIM_NAMES = ('Material', 'MATERIALS', 'MATERIAL_NAMES', 'Afterburn',
              'AFTERBURN', 'E0', 'charge_radius')


def test_material_rows():
    assert old.MATERIAL_NAMES == ('TNT', 'C4', 'RDX', 'HMX', 'PETN', 'ANFO')
    assert tuple(old.MATERIALS) == old.MATERIAL_NAMES
    for name, row in MATERIAL_ROWS.items():
        assert dataclasses.astuple(old.MATERIALS[name]) == row, name


def test_afterburn_rows():
    assert tuple(old.AFTERBURN) == old.MATERIAL_NAMES
    for name, row in AFTERBURN_ROWS.items():
        assert dataclasses.astuple(old.AFTERBURN[name]) == row, name


def test_e0():
    for name, want in E0_VALUES.items():
        assert old.E0(old.MATERIALS[name]) == pytest.approx(want, rel=REL)


def test_charge_radius():
    for name, radii in RADII.items():
        m = old.MATERIALS[name]
        for (mass, planar), want in zip(RADIUS_INPUTS, radii):
            got = old.charge_radius(mass, m, planar=planar)
            assert got == pytest.approx(want, rel=REL), (name, mass, planar)


def test_material_jwl():
    assert material_jwl('TNT') is constants.JWL_TNT
    assert material_jwl('') is constants.JWL_TNT
    assert material_jwl(None) is constants.JWL_TNT
    for name in old.MATERIAL_NAMES[1:]:
        row = MATERIAL_ROWS[name]
        assert material_jwl(name) == dict(
            A=row[0], B=row[1], R1=row[2], R2=row[3], omega=row[4],
            rho0=row[5], e0=row[6]), name


def test_shim_reexports_core():
    """The old path hands out the very objects core.materials owns."""
    from blastlab.core import materials as new
    for name in SHIM_NAMES:
        assert getattr(old, name) is getattr(new, name), name


def main():
    return cc.run_main('CHAR MATERIALS', [
        test_material_rows, test_afterburn_rows, test_e0,
        test_charge_radius, test_material_jwl, test_shim_reexports_core])


if __name__ == '__main__':
    sys.exit(main())
