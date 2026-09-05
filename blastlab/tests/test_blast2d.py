"""Verification suite for blast2d.py (run with cwd = scratchpad)."""
import os, sys
import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import blast1d
import blast2d
from blast2d import (P_AIR, RHO_AIR, GAMMA_AIR, E_AIR, primitives, hll_fluxes,
                     make_geometry, solid_mask, face_fluxes, run_blast_2d,
                     load_profile, remap_profile)

FAIL = []

def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


# ── T1: primitives on uniform ambient air ────────────────────────────────────
print("\nT1: primitives ambient")
U = np.zeros((4, 5, 4))
U[0] = RHO_AIR
U[3] = RHO_AIR * E_AIR
phase = np.zeros((5, 4), int)
rho, u, v, e, p, c = primitives(U, phase, 'idealGas')
check("p = P_AIR", np.allclose(p, P_AIR))
check("c ~ 340.3", np.allclose(c, np.sqrt(GAMMA_AIR * P_AIR / RHO_AIR)))

# ── T2: x-sweep HLL matches blast1d bit-for-bit when v=0 ─────────────────────
print("\nT2: HLL vs blast1d (v = 0)")
rng = np.random.default_rng(1)
M = 200
rhoL = rng.uniform(0.5, 5, M); rhoR = rng.uniform(0.5, 5, M)
uL   = rng.uniform(-500, 500, M); uR = rng.uniform(-500, 500, M)
eL   = rng.uniform(1e5, 5e6, M);  eR = rng.uniform(1e5, 5e6, M)
pL   = (GAMMA_AIR-1)*rhoL*eL; pR = (GAMMA_AIR-1)*rhoR*eR
cL   = np.sqrt(GAMMA_AIR*pL/rhoL); cR = np.sqrt(GAMMA_AIR*pR/rhoR)
U1L = np.array([rhoL, rhoL*uL, rhoL*(eL+0.5*uL**2)])
U1R = np.array([rhoR, rhoR*uR, rhoR*(eR+0.5*uR**2)])
F1  = blast1d.hll_fluxes(U1L, U1R, pL, pR, cL, cR)
U2L = np.array([rhoL, rhoL*uL, np.zeros(M), rhoL*(eL+0.5*uL**2)])
U2R = np.array([rhoR, rhoR*uR, np.zeros(M), rhoR*(eR+0.5*uR**2)])
F2  = hll_fluxes(U2L, U2R, pL, pR, cL, cR, n=1)
check("rows (rho, rho*u, E) identical",
      np.array_equal(F1, F2[[0, 1, 3]]))
check("transverse flux = 0", np.array_equal(F2[2], np.zeros(M)))

# mirrored pair -> wall flux [0, p*, 0, 0]
Um = U2L[:, :1].copy(); Umr = Um.copy(); Umr[1] = -Umr[1]
Fw = hll_fluxes(Um, Umr, pL[:1], pL[:1], cL[:1], cL[:1], n=1)
check("wall flux: zero mass/energy/transverse",
      abs(Fw[0, 0]) < 1e-8 and abs(Fw[2, 0]) < 1e-8 and abs(Fw[3, 0]) < 1e-3,
      f"(F={Fw[:,0]})")

# ── helper: bare update loop (mirrors run_blast_2d inner loop) ───────────────
def steps(U, phase, geom, bcs, solid, geometry, eos='idealGas',
          nsteps=200, cfl=0.4):
    A_xf, A_yf, V = geom['A_xf'], geom['A_yf'], geom['V']
    dx, dy = geom['dx'], geom['dy']
    x_c = geom['x_c']
    fluid = ~solid
    U_solid = np.array([RHO_AIR, 0.0, 0.0, RHO_AIR*E_AIR])
    for _ in range(nsteps):
        rho, u, v, e, p, c = primitives(U, phase, eos)
        wave = (np.abs(u)+c)/dx + (np.abs(v)+c)/dy
        dt = cfl / wave[fluid].max()
        Fx = face_fluxes(U, p, c, 1, bcs['x_lo'], bcs['x_hi'], solid)
        Fy = face_fluxes(U, p, c, 2, bcs['y_lo'], bcs['y_hi'], solid)
        div = ((A_xf[1:]*Fx[:, 1:, :] - A_xf[:-1]*Fx[:, :-1, :])
               + A_yf*(Fy[:, :, 1:] - Fy[:, :, :-1])) / V
        U = U - dt*div
        if geometry == 'axisymmetric':
            U[1] += dt * p / x_c[:, None]
        if solid.any():
            U[:, solid] = U_solid[:, None]
    return U

def ambient(Nx, Ny):
    U = np.zeros((4, Nx, Ny))
    U[0] = RHO_AIR
    U[3] = RHO_AIR * E_AIR
    return U

# ── T3: well-balance (planar & axisym), incl. obstacle ──────────────────────
print("\nT3: well-balance, 200 steps")
for geometry in ('planar', 'axisymmetric'):
    geom = make_geometry(geometry, 1.0, 1.0, 0.02)
    Nx, Ny = geom['Nx'], geom['Ny']
    solid = solid_mask(geom['x_c'], geom['y_c'], [(0.4, 0.6, 0.4, 0.6)])
    bcs = dict(x_lo='wall' if geometry == 'axisymmetric' else 'open',
               x_hi='open', y_lo='wall', y_hi='open')
    U0 = ambient(Nx, Ny)
    U1 = steps(U0.copy(), np.zeros((Nx, Ny), int), geom, bcs, solid, geometry)
    err = np.abs(U1 - U0).max() / np.abs(U0).max()
    check(f"{geometry}: still air preserved", err < 1e-11, f"(rel err {err:.2e})")

# ── T4: energy conservation, closed planar box ───────────────────────────────
print("\nT4: closed-box energy conservation")
geom = make_geometry('planar', 1.0, 1.0, 0.02)
Nx, Ny = geom['Nx'], geom['Ny']
solid = np.zeros((Nx, Ny), bool)
U = ambient(Nx, Ny)
blob = ((geom['x_c'][:, None]-0.5)**2 + (geom['y_c'][None, :]-0.5)**2) < 0.1**2
U[3][blob] *= 20.0        # hot spot
E0 = (U[3] * geom['V'][:, 0][:, None]).sum()
bcs = dict(x_lo='wall', x_hi='wall', y_lo='wall', y_hi='wall')
U = steps(U, np.zeros((Nx, Ny), int), geom, bcs, solid, 'planar', nsteps=500)
E1 = (U[3] * geom['V'][:, 0][:, None]).sum()
check("total energy conserved", abs(E1-E0)/E0 < 1e-3,
      f"(drift {(E1-E0)/E0:.2e})")

# ── T5: planar free-air symmetry (x<->y) via run_blast_2d ────────────────────
print("\nT5: planar symmetry")
snaps, _, meta = run_blast_2d('planar', 2.0, 2.0, 0.02,
                              charge=60.0, charge_center=(1.0, 1.0),
                              eos='idealGas', n_snapshots=1, gauges=[])
p_fin = list(snaps.values())[-1]['p']
check("x<->y transpose symmetry", np.allclose(p_fin, p_fin.T, rtol=1e-9))
check("x-mirror symmetry", np.allclose(p_fin, p_fin[::-1, :], rtol=1e-9))

# ── T6: wall mirror = half of free-air run ───────────────────────────────────
print("\nT6: wall mirror test")
snapsA, _, _ = run_blast_2d('planar', 2.0, 2.0, 0.02,
                            charge=60.0, charge_center=(1.0, 1.0),
                            eos='idealGas', n_snapshots=1, gauges=[])
snapsB, _, _ = run_blast_2d('planar', 2.0, 1.0, 0.02,
                            charge=60.0, charge_center=(1.0, 1.0),
                            bcs=dict(x_lo='open', x_hi='open',
                                     y_lo='open', y_hi='wall'),
                            eos='idealGas', n_snapshots=1, gauges=[])
pA = list(snapsA.values())[-1]['p']
pB = list(snapsB.values())[-1]['p']
Ny_half = pB.shape[1]
err = np.abs(pB - pA[:, :Ny_half]).max() / P_AIR
check("half-domain wall == lower half of free air", err < 1e-6,
      f"(rel err {err:.2e})")

# ── T7: obstacle reflection ──────────────────────────────────────────────────
print("\nT7: obstacle reflection")
gauge = [(0.55, 1.0)]                     # just in front of the block face
free_s, free_g, _ = run_blast_2d('planar', 2.0, 2.0, 0.02,
                                 charge=60.0, charge_center=(1.0, 1.0),
                                 eos='idealGas', n_snapshots=1, gauges=gauge)
obs_s, obs_g, obs_m = run_blast_2d('planar', 2.0, 2.0, 0.02,
                                   charge=60.0, charge_center=(1.0, 1.0),
                                   obstacles=[(0.3, 0.5, 0.6, 1.4)],
                                   eos='idealGas', n_snapshots=1, gauges=gauge)
pk_free = free_g['pressures'][0].max() - P_AIR
pk_obs  = obs_g['pressures'][0].max() - P_AIR
check("finite fields", np.isfinite(list(obs_s.values())[-1]['p']).all())
check("reflected peak > incident peak", pk_obs > 1.5 * pk_free,
      f"(free {pk_free:.3e} Pa, reflected {pk_obs:.3e} Pa, "
      f"ratio {pk_obs/pk_free:.2f})")

# ── T8: axisymmetric free-air vs blast1d gauges ──────────────────────────────
print("\nT8: axisym vs 1D spherical (this takes a minute)")
charge, cell = 8.0, 0.05
g1d = [1.5, 2.5, 3.5]
_, gauges1d, _ = blast1d.run_blast(4.0, charge, cell, eos='idealGas',
                                   n_snapshots=1, gauge_radii=g1d)
snap2, gauges2d, meta2 = run_blast_2d(
    'axisymmetric', 4.0, 8.0, cell, charge=charge, charge_center=(0.0, 4.0),
    eos='idealGas', n_snapshots=1,
    gauges=[(r, 4.0) for r in g1d])

def arrival_peak(times, p, thresh=0.05):
    ovp = p - P_AIR
    idx = np.argmax(ovp > thresh * P_AIR)
    return times[idx], ovp.max()

print("    r      arr_1d     arr_2d    darr%   peak_1d    peak_2d   dpk%")
ok_arr = ok_pk = True
for k, r in enumerate(g1d):
    a1, p1 = arrival_peak(gauges1d['times'], gauges1d['pressures'][k])
    a2, p2 = arrival_peak(gauges2d['times'], gauges2d['pressures'][k])
    da = abs(a2 - a1) / a1 * 100
    dp = abs(p2 - p1) / p1 * 100
    print(f"   {r:4.1f}  {a1*1e3:8.3f}  {a2*1e3:8.3f}  {da:6.2f}  "
          f"{p1:9.3e}  {p2:9.3e}  {dp:6.2f}")
    # 6%: a 5-cell-radius charge is a stair-stepped sphere whose cell count
    # (and so its initial energy) swings ~3% with where the centre falls
    # relative to the faces - the exact-domain grids (B18) put y0 = 4.0 on a
    # face and moved r = 1.5 m from 4.3% to 5.2%. See ROADMAP B24.
    ok_arr &= da < 6.0
    ok_pk  &= dp < 15.0
check("arrival times within 6%", ok_arr)
check("peak overpressure within 15%", ok_pk)

# ── T9: 1D -> 2D remap round trip ────────────────────────────────────────────
print("\nT9: 1D -> 2D remap")
_, _, prof = blast1d.run_blast(2.5, charge, cell, eos='idealGas',
                               n_snapshots=1, gauge_radii=[])
blast1d.save_profile(prof, 'test_profile.txt')
loaded = load_profile('test_profile.txt')
check("profile round-trip (rho)", np.allclose(loaded['rho'], prof['rho']))
check("profile metadata", loaded['eos'] == 'idealGas'
      and abs(loaded['t'] - prof['t']) < 1e-12)

snapR, gaugesR, metaR = run_blast_2d(
    'axisymmetric', 4.0, 8.0, prof['r'][1] - prof['r'][0],
    profile=loaded, charge_center=(0.0, 4.0),
    eos='idealGas', n_snapshots=1, gauges=[(3.5, 4.0)])
aR, pR = arrival_peak(gaugesR['times'], gaugesR['pressures'][0])
a1, p1 = arrival_peak(gauges1d['times'], gauges1d['pressures'][2])  # r=3.5 straight 1D
da = abs(aR - a1) / a1 * 100
dp = abs(pR - p1) / p1 * 100
check("remap arrival within 3% of straight 1D", da < 3.0, f"({da:.2f}%)")
check("remap peak within 15% of straight 1D", dp < 15.0,
      f"({dp:.2f}%: 1D {p1:.3e}, remap {pR:.3e})")

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 50)
if FAIL:
    print(f"FAILURES ({len(FAIL)}): " + ", ".join(FAIL))
    sys.exit(1)
print("ALL CHECKS PASSED")
