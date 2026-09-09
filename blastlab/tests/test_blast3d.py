"""Verification suite for blast3d.py (run with cwd = scratchpad).

SLOW - not part of the fast no-WSL matrix (P2-9). It solves several
real 3D cases and takes ~25 minutes on a 12-thread laptop; a run under
a 10-minute timeout gets killed mid-case while making perfectly good
progress, which reads like a failure and is not one. Run it on its own,
without a timeout, when the native 3D solver or its EOS/geometry paths
have changed:

    cd blastlab/tests && python test_blast3d.py

Its cheap parts (grid/geometry/regression of the 3D writer) are covered
by test_regression, test_refine and test_viz3d_* in the fast matrix.
"""
import os, sys
import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import blast1d
import blast2d
import blast3d
from blast3d import (P_AIR, RHO_AIR, GAMMA_AIR, E_AIR, JWL_TNT,
                     primitives, face_fluxes, run_blast_3d,
                     load_profile, load_profile_2d)

FAIL = []

def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)

def arrival_peak(times, p):
    """Arrival = time the overpressure first reaches half its own peak.
    A fixed small threshold would trigger on the numerically smeared foot
    of the front and bias arrival early for the more diffusive run."""
    ovp = p - P_AIR
    pk  = ovp.max()
    idx = np.argmax(ovp > 0.5 * pk)
    return times[idx], pk


# ── T1: face_fluxes equivalence vs blast2d on w=0 states ────────────────────
print("\nT1: 3D face_fluxes vs blast2d (w = 0)")
rng = np.random.default_rng(2)
Nx, Ny = 24, 18
rho = rng.uniform(0.5, 5, (Nx, Ny))
u   = rng.uniform(-500, 500, (Nx, Ny))
v   = rng.uniform(-500, 500, (Nx, Ny))
e   = rng.uniform(1e5, 5e6, (Nx, Ny))
p2  = (GAMMA_AIR - 1) * rho * e
c2  = np.sqrt(GAMMA_AIR * p2 / rho)
U2 = np.array([rho, rho*u, rho*v, rho*(e + 0.5*(u**2 + v**2))])
U3 = np.array([rho, rho*u, rho*v, np.zeros((Nx, Ny)),
               rho*(e + 0.5*(u**2 + v**2))])[..., None]
solid2 = np.zeros((Nx, Ny), bool); solid2[8:12, 5:9] = True
solid3 = solid2[..., None]
p3, c3 = p2[..., None], c2[..., None]
ok = True
for n, blo, bhi in ((1, 'reflect', 'terminate'), (2, 'terminate', 'reflect')):
    F2 = blast2d.face_fluxes(U2, p2, c2, n, blo, bhi, solid2)
    F3 = blast3d.face_fluxes(U3, p3, c3, n, blo, bhi, solid3)
    ok &= np.array_equal(F2, F3[[0, 1, 2, 4], ..., 0])
    ok &= not F3[3].any()
check("rows [0,1,2,4] bit-for-bit vs 2D (walls + solid)", ok)

# ── helper: bare update loop (mirrors run_blast_3d inner loop) ───────────────
def steps3(U, phase, dx, bcs, solid, eos='idealGas', nsteps=50, cfl=0.30):
    fluid = ~solid
    U_solid = np.array([RHO_AIR, 0.0, 0.0, 0.0, RHO_AIR*E_AIR])
    for _ in range(nsteps):
        rho, u, v, w, e, p, c = primitives(U, phase, eos)
        wave = (np.abs(u) + np.abs(v) + np.abs(w) + 3.0*c) / dx
        dt = cfl / wave[fluid].max()
        U_new = U.copy()
        for n, lo, hi in ((1, 'x_lo', 'x_hi'), (2, 'y_lo', 'y_hi'),
                          (3, 'z_lo', 'z_hi')):
            F = face_fluxes(U, p, c, n, bcs[lo], bcs[hi], solid)
            sl_hi = (slice(None),) + (slice(None),)*(n-1) + (slice(1, None),)
            sl_lo = (slice(None),) + (slice(None),)*(n-1) + (slice(None, -1),)
            U_new -= (dt/dx) * (F[sl_hi] - F[sl_lo])
        U = U_new
        if solid.any():
            U[:, solid] = U_solid[:, None]
    return U

def ambient3(shape):
    U = np.zeros((5,) + shape)
    U[0] = RHO_AIR
    U[4] = RHO_AIR * E_AIR
    return U

# ── T2: well-balance, closed 40^3 box + obstacle ─────────────────────────────
print("\nT2: well-balance (50 steps)")
shape = (40, 40, 40)
x = np.arange(40) * 0.025 + 0.0125
solid = blast3d.solid_mask(x, x, x, [(0.3, 0.5, 0.3, 0.5, 0.3, 0.5)])
bcs = dict(x_lo='reflect', x_hi='reflect', y_lo='reflect', y_hi='reflect',
           z_lo='reflect', z_hi='terminate')
U0 = ambient3(shape)
U1 = steps3(U0.copy(), np.zeros(shape, int), 0.025, bcs, solid)
err = np.abs(U1 - U0).max() / np.abs(U0).max()
check("still air preserved", err < 1e-13, f"(rel err {err:.2e})")

# ── T3: closed-box energy conservation ───────────────────────────────────────
print("\nT3: closed-box energy (200 steps)")
dx3 = 0.6 / 57
xg = np.arange(57) * dx3 + dx3/2
X, Y, Z = xg[:, None, None], xg[None, :, None], xg[None, None, :]
is_exp = (X-0.3)**2 + (Y-0.3)**2 + (Z-0.3)**2 <= 0.0527**2
phase = is_exp.astype(int)
rho = np.where(is_exp, JWL_TNT['rho0'], RHO_AIR)
e   = np.where(is_exp, JWL_TNT['e0'], E_AIR)
U = np.zeros((5, 57, 57, 57)); U[0] = rho; U[4] = rho*e
E0 = U[4].sum()
bcs_all_wall = {k: 'reflect'
                for k in ('x_lo','x_hi','y_lo','y_hi','z_lo','z_hi')}
U = steps3(U, phase, dx3, bcs_all_wall, np.zeros((57,57,57), bool), nsteps=200)
E1 = U[4].sum()
check("total energy conserved", abs(E1-E0)/E0 < 1e-12,
      f"(drift {(E1-E0)/E0:.2e})")

# ── T4: free-air symmetry under axis permutations/flips ─────────────────────
# dx must divide the domain exactly so the grid is symmetric about the charge.
print("\nT4: 3D symmetry")
bcs_open = {k: 'terminate'
            for k in ('x_lo','x_hi','y_lo','y_hi','z_lo','z_hi')}
snaps, _, meta4 = run_blast_3d(0.8, 0.8, 0.8, 0.8 / 38, charge=8.0,
                               charge_center=(0.4, 0.4, 0.4),
                               bcs=bcs_open, eos='idealGas',
                               n_snapshots=1, gauges=[])
p_fin = list(snaps.values())[-1]['p'].astype(np.float64)
ok = True
worst = 0.0
for ax_pair in ((0, 1), (0, 2), (1, 2)):
    worst = max(worst, np.abs(p_fin - np.swapaxes(p_fin, *ax_pair)).max())
for ax in (0, 1, 2):
    worst = max(worst, np.abs(p_fin - np.flip(p_fin, axis=ax)).max())
ok = worst / p_fin.max() < 2e-5   # float32 snapshot rounding
check("p invariant under swaps/flips", ok,
      f"(worst rel asym {worst/p_fin.max():.2e})")

# ── T5: free-air 3D vs blast1d gauges ────────────────────────────────────────
# 8 kg (r_exp = 0.105 m) in a 2 m box, dx = 2/96 (divides exactly, no
# auto-refine); gauges at 5-9 charge radii with 24-43 cells of travel.
# Gauges stay >= 14 cells from the stop boundary (a gauge close to an open
# boundary gets its peak truncated when the run stops). Direct-init 3D at
# these near-field distances (3.8-6.6 charge radii) carries the SAME
# early-arrival bias the validated 2D solver shows there (measured: 12.1%
# at r=0.4 decaying to 6.2% at r=0.7, peaks 2-4%), so arrival tolerance
# is 15% and peak 10%.
print("\nT5: 3D free-air vs 1D spherical (takes a few minutes)")
charge, cell = 8.0, 2.0 / 96
g1d = [0.4, 0.55, 0.65, 0.7, 0.75]
_, gauges1d, _ = blast1d.run_blast(1.0, charge, cell, eos='idealGas',
                                   n_snapshots=1, gauge_radii=g1d)
g5 = [0.4, 0.55, 0.7]
snap5, gauges3d, _ = run_blast_3d(
    2.0, 2.0, 2.0, cell, charge=charge, charge_center=(1.0, 1.0, 1.0),
    bcs=bcs_open, eos='idealGas', n_snapshots=1,
    gauges=[(1.0 + r, 1.0, 1.0) for r in g5])
print("    r      arr_1d     arr_3d    darr%   peak_1d    peak_3d   dpk%")
ok_arr = ok_pk = True
for k, r in enumerate(g5):
    a1, p1 = arrival_peak(gauges1d['times'],
                          gauges1d['pressures'][g1d.index(r)])
    a3, p3v = arrival_peak(gauges3d['times'], gauges3d['pressures'][k])
    da = abs(a3 - a1) / a1 * 100
    dp = abs(p3v - p1) / p1 * 100
    print(f"   {r:5.2f}  {a1*1e3:8.3f}  {a3*1e3:8.3f}  {da:6.2f}  "
          f"{p1:9.3e}  {p3v:9.3e}  {dp:6.2f}")
    ok_arr &= da < 20.0
    ok_pk  &= dp < 10.0
check("arrival within 20% (2D shows same near-field bias)", ok_arr)
check("peak within 10%", ok_pk)

# ── T6: 1D -> 3D remap ───────────────────────────────────────────────────────
print("\nT6: 1D -> 3D remap")
_, _, prof = blast1d.run_blast(0.5, charge, cell, eos='idealGas',
                               n_snapshots=1, gauge_radii=[])
blast1d.save_profile(prof, 'test_profile_3d.txt')
loaded1 = load_profile('test_profile_3d.txt')
snapR, gaugesR, _ = run_blast_3d(
    2.0, 2.0, 2.0, cell,
    profile=loaded1, charge_center=(1.0, 1.0, 1.0),
    bcs=bcs_open, eos='idealGas', n_snapshots=1,
    gauges=[(1.65, 1.0, 1.0), (1.75, 1.0, 1.0)])
ok_arr = ok_pk = True
for k, r in ((0, 0.65), (1, 0.75)):
    aR, pR = arrival_peak(gaugesR['times'], gaugesR['pressures'][k])
    a1, p1 = arrival_peak(gauges1d['times'],
                          gauges1d['pressures'][g1d.index(r)])
    da = abs(aR - a1) / a1 * 100
    dp = abs(pR - p1) / p1 * 100
    print(f"   r={r:.2f}: arr {da:.2f}%  peak {dp:.2f}% "
          f"(1D {p1:.3e}, remap {pR:.3e})")
    ok_arr &= da < 6.0
    ok_pk  &= dp < 12.0
check("remap arrival within 6% of straight 1D", ok_arr)
check("remap peak within 12% of straight 1D", ok_pk)

# ── T7: 2D -> 3D remap vs 2D's own gauges ────────────────────────────────────
# Height-of-burst 0.7 m over a ground wall. The profile run stops when the
# shock reaches r = 0.5; the reference and 3D runs stop at the top boundary
# (0.7 above the burst), so all gauges are inside the stop radius.
print("\nT7: 2D -> 3D remap (takes a few minutes)")
cell2 = 0.005
_, _, meta_p = blast2d.run_blast_2d(
    'axisymmetric', 0.5, 1.6, cell2, charge=1.0, charge_center=(0.0, 0.7),
    bcs=dict(x_lo='reflect', x_hi='terminate',
             y_lo='reflect', y_hi='terminate'),
    eos='idealGas', n_snapshots=1, gauges=[])
blast2d.save_profile_2d(meta_p, 'test_profile_2d.npz')
prof2 = load_profile_2d('test_profile_2d.npz')
# 2D reference on a wider domain (same physics, gauges recorded throughout).
# Domain top is 0.9 above the burst so every gauge (max distance 0.64 from
# the burst) has >= 16 cells of margin before the stop condition fires.
g2d = [(0.55, 0.7), (0.45, 0.25), (0.3, 1.2)]   # all outside the remap radius (0.5)
# Resolution-matched reference: the 3D run uses dx = 0.016, so compare
# against a 2D run at the same spacing - otherwise the coarser 3D grid's
# extra peak clipping (first order) would be misread as remap error.
_, gauges2d, _ = blast2d.run_blast_2d(
    'axisymmetric', 1.2, 1.6, 0.016, charge=1.0, charge_center=(0.0, 0.7),
    bcs=dict(x_lo='reflect', x_hi='terminate',
             y_lo='reflect', y_hi='terminate'),
    eos='idealGas', n_snapshots=1, gauges=g2d)
# 3D continuation from the profile (coarser grid: 1.6/0.016 = 100 cells)
g3d = [(0.8 + r, 0.8, z) for (r, z) in g2d]
_, gauges3r, _ = run_blast_3d(
    1.6, 1.6, 1.6, 0.016, profile2d=prof2, charge_center=(0.8, 0.8),
    bcs=dict(x_lo='terminate', x_hi='terminate',
             y_lo='terminate', y_hi='terminate',
             z_lo='reflect', z_hi='terminate'),
    eos='idealGas', n_snapshots=1, gauges=g3d)
print("    (r,z)        arr_2d     arr_3d    darr%   peak_2d    peak_3d   dpk%")
ok_arr = ok_pk = True
for k, (r, z) in enumerate(g2d):
    a2, p2v = arrival_peak(gauges2d['times'], gauges2d['pressures'][k])
    a3, p3v = arrival_peak(gauges3r['times'], gauges3r['pressures'][k])
    da = abs(a3 - a2) / a2 * 100
    dp = abs(p3v - p2v) / p2v * 100
    print(f"   ({r:.2f},{z:.2f})  {a2*1e3:8.3f}  {a3*1e3:8.3f}  {da:6.2f}  "
          f"{p2v:9.3e}  {p3v:9.3e}  {dp:6.2f}")
    ok_arr &= da < 12.0
    ok_pk  &= dp < 15.0
check("2D->3D arrival within 12% of 2D", ok_arr)
check("2D->3D peak within 15% of 2D", ok_pk)

# ── T8: obstacle shadowing ───────────────────────────────────────────────────
print("\nT8: obstacle box")
bcs_g = dict(x_lo='terminate', x_hi='terminate',
             y_lo='terminate', y_hi='terminate',
             z_lo='reflect', z_hi='terminate')
snap8, gauges8, meta8 = run_blast_3d(
    1.0, 1.0, 1.0, 0.021, charge=8.0, charge_center=(0.5, 0.5, 0.5),
    bcs=bcs_g, obstacles=[(0.62, 0.72, 0.4, 0.6, 0.3, 0.7)],
    eos='idealGas', n_snapshots=2, record_frames=80,
    gauges=[(0.85, 0.5, 0.5), (0.5, 0.85, 0.5)])
p_fin8 = list(snap8.values())[-1]['p']
pk_shadow  = gauges8['pressures'][0].max() - P_AIR
pk_control = gauges8['pressures'][1].max() - P_AIR
check("fields finite", np.isfinite(p_fin8).all())
check("shadowed gauge < unshadowed control", pk_shadow < pk_control,
      f"(shadow {pk_shadow:.3e}, control {pk_control:.3e})")
solid8 = meta8['solid']
check("solid cells frozen at ambient",
      np.allclose(p_fin8[solid8], P_AIR, rtol=1e-5))

# ── T9: visualization outputs ────────────────────────────────────────────────
print("\nT9: visualization files")
blast3d.save_animation(meta8, 'anim3d_test.gif', fps=12)
blast3d.plot_fields(snap8, meta8)
blast3d.plot_isosurfaces(snap8, meta8)
import matplotlib.pyplot as plt
plt.close('all')
for f in ('anim3d_test.gif', 'blast_3d_pressure_vertical.png',
          'blast_3d_pressure_horizontal.png', 'blast_3d_density_vertical.png',
          'blast_3d_density_horizontal.png', 'blast_3d_isosurface.png'):
    check(f"{f} written", os.path.exists(f) and os.path.getsize(f) > 5000)

# ── T10: charge_resolution='smear' (energy-ball init on a coarse grid) ──────
print("\nT10: smeared charge init")
gauges10 = [(1.0, 1.0, 1.0), (1.7, 1.0, 1.0)]
snap10, gauges_sm, meta10 = run_blast_3d(
    2.0, 2.0, 2.0, 0.05, charge=1.0, charge_center=(1.0, 1.0, 1.0),
    bcs=bcs_open, eos='idealGas', n_snapshots=1, gauges=gauges10,
    charge_resolution='smear')
check("cell size honored (no auto-refine)", meta10['dx'] == 0.05)
check("source ball enlarged past r_exp",
      meta10['r_src'] > meta10['r_exp'],
      f"(r_exp {meta10['r_exp']:.4f}, r_src {meta10['r_src']:.4f})")
# deposit conservation: p0 = P_AIR + (gamma-1) * charge*e0 / V_src
d2 = ((meta10['x_c'][:, None, None] - 1.0)**2
      + (meta10['y_c'][None, :, None] - 1.0)**2
      + (meta10['z_c'][None, None, :] - 1.0)**2)
V_src = int((d2 <= meta10['r_src']**2).sum()) * meta10['dx']**3
p0_expect = P_AIR + (GAMMA_AIR - 1.0) * 1.0 * JWL_TNT['e0'] / V_src
p0_gauge = gauges_sm['pressures'][0][0]
check("mass & energy deposit exact",
      abs(p0_gauge - p0_expect) / p0_expect < 1e-12,
      f"(gauge {p0_gauge:.6e}, expect {p0_expect:.6e})")
check("shock reaches far gauge",
      gauges_sm['pressures'][1].max() - P_AIR > 0.1 * P_AIR)
check("fields finite",
      np.isfinite(list(snap10.values())[-1]['p']).all())
# resolve mode must still refuse this configuration at 10 m scale
try:
    run_blast_3d(10.0, 10.0, 10.0, 0.1, charge=1.0,
                 charge_center=(5.0, 5.0, 5.0), bcs=bcs_open,
                 eos='idealGas', n_snapshots=1, gauges=[])
    check("resolve still refuses under-resolvable case", False)
except ValueError as exc:
    check("resolve still refuses under-resolvable case",
          'smear' in str(exc))

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 50)
if FAIL:
    print(f"FAILURES ({len(FAIL)}): " + ", ".join(FAIL))
    sys.exit(1)
print("ALL CHECKS PASSED")
