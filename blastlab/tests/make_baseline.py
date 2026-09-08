"""Capture deterministic baseline outputs from the blast solvers.

Runs a fixed set of small cases through the public (legacy) API and saves
gauge TSVs and profile files into tests/baseline/. Run once BEFORE a
refactor and again AFTER; test_regression.py compares the two.

Usage:  python make_baseline.py [outdir]     (default: ./baseline)
"""
import os, sys
import contextlib
import io

import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, REPO)

import blast1d, blast2d, blast3d   # noqa: E402


def run(outdir):
    os.makedirs(outdir, exist_ok=True)
    transcript = io.StringIO()

    def path(name):
        return os.path.join(outdir, name)

    with contextlib.redirect_stdout(transcript):
        # ── 1D: JWL charge, gauges, profile ────────────────────────────────
        snaps, gauges, prof = blast1d.run_blast(
            2.0, 1.0, 0.02, eos='JWL', n_snapshots=2,
            gauge_radii=[0.5, 1.0, 1.5])
        blast1d.save_gauges(gauges, path('b1_gauges.txt'))
        blast1d.save_profile(prof, path('b1_profile.txt'))

        # ── 2D axisym: charge + ground wall + obstacle, gauges ─────────────
        snaps2, gauges2, meta2 = blast2d.run_blast_2d(
            'axisymmetric', 1.2, 1.6, 0.02, charge=1.0,
            charge_center=(0.0, 0.7),
            bcs=dict(x_lo='reflect', x_hi='terminate',
                     y_lo='reflect', y_hi='terminate'),
            obstacles=[(0.7, 0.9, 0.2, 0.5)],
            eos='idealGas', n_snapshots=2,
            gauges=[(0.5, 0.7), (0.4, 0.2)])
        blast2d.save_gauges(gauges2, path('b2_gauges.txt'))

        # ── 2D axisym profile run (small: shock stops at r = 0.5) ──────────
        _, _, meta2p = blast2d.run_blast_2d(
            'axisymmetric', 0.5, 1.6, 0.02, charge=1.0,
            charge_center=(0.0, 0.7),
            bcs=dict(x_lo='reflect', x_hi='terminate',
                     y_lo='reflect', y_hi='terminate'),
            eos='idealGas', n_snapshots=1, gauges=[])
        blast2d.save_profile_2d(meta2p, path('b2_profile.npz'))

        # ── 2D planar from nothing + 2D axisym from the 1D profile ─────────
        prof1 = blast2d.load_profile(path('b1_profile.txt'))
        _, gauges2r, _ = blast2d.run_blast_2d(
            'axisymmetric', 3.0, 6.0, 0.02, profile=prof1,
            charge_center=(0.0, 3.0), eos='JWL', n_snapshots=1,
            # was the pre-T50 default (all 'open' = transmit + terminate)
            bcs=dict(x_lo='terminate', x_hi='terminate',
                     y_lo='terminate', y_hi='terminate'),
            gauges=[(2.4, 3.0)])
        blast2d.save_gauges(gauges2r, path('b2r_gauges.txt'))

        # ── 3D: small charge box + obstacle ─────────────────────────────────
        _, gauges3, _ = blast3d.run_blast_3d(
            1.0, 1.0, 1.0, 0.025, charge=8.0, charge_center=(0.5, 0.5, 0.5),
            obstacles=[(0.62, 0.72, 0.4, 0.6, 0.3, 0.7)],
            eos='idealGas', n_snapshots=1,
            # was the pre-T50 default (all 'open' = transmit + terminate)
            bcs=dict(x_lo='terminate', x_hi='terminate',
                     y_lo='terminate', y_hi='terminate',
                     z_lo='reflect', z_hi='terminate'),
            gauges=[(0.85, 0.5, 0.5), (0.5, 0.85, 0.5)])
        blast3d.save_gauges(gauges3, path('b3_gauges.txt'))

        # ── 3D from the 2D profile ──────────────────────────────────────────
        prof2 = blast3d.load_profile_2d(path('b2_profile.npz'))
        _, gauges3r, _ = blast3d.run_blast_3d(
            1.6, 1.6, 1.6, 0.02, profile2d=prof2, charge_center=(0.8, 0.8),
            bcs=dict(x_lo='terminate', x_hi='terminate',
                     y_lo='terminate', y_hi='terminate',
                     z_lo='reflect', z_hi='terminate'),
            eos='idealGas', n_snapshots=1,
            gauges=[(1.35, 0.8, 0.7), (1.2, 0.8, 0.2)])
        blast3d.save_gauges(gauges3r, path('b3r_gauges.txt'))

    # Normalize the output directory out of the transcript so regression
    # runs (which use a temp dir) compare byte-identical.
    text = transcript.getvalue().replace(outdir, '<OUT>')
    with open(path('transcript.txt'), 'w') as f:
        f.write(text)
    print(f"Baseline written to {outdir}")
    for name in sorted(os.listdir(outdir)):
        print(f"  {name}  ({os.path.getsize(os.path.join(outdir, name)):,} B)")


if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv) > 1
        else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'baseline'))
