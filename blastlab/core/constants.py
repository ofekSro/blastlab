"""Physical constants and solver limits shared by all solvers."""

GAMMA_AIR = 1.4
RHO_AIR   = 1.225    # kg/m³  ambient air density
P_AIR     = 101325.0  # Pa     ambient pressure

# JWL parameters for TNT (Dobratz & Crawford, LLNL Explosives Handbook, 1985)
JWL_TNT = dict(
    A     = 3.712e11,   # Pa
    B     = 3.23e9,     # Pa
    R1    = 4.15,
    R2    = 0.95,
    omega = 0.30,
    rho0  = 1630.0,     # kg/m³  unreacted TNT density
    e0    = 4.29e6,     # J/kg   specific detonation energy
)

E_AIR = P_AIR / ((GAMMA_AIR - 1.0) * RHO_AIR)   # ambient specific internal energy

# Grid-size guard rails (native solvers: live numpy state ~200 B/cell)
MIN_EXP_CELLS  = 5             # min cells across the charge radius
CELLS_2D_WARN  = 2_000_000
CELLS_2D_MAX   = 8_000_000
CELLS_WARN     = 4_000_000     # 3D
CELLS_REFUSE   = 15_000_000    # 3D

# blastFoam backend caps: the solve runs in WSL (C++, disk-backed);
# Python only ingests a few float64 grids per written frame (~32 B/cell),
# so the limits reflect ingest RAM + wall time + disk, not solver memory.
FOAM_CELLS_WARN   = 8_000_000
FOAM_CELLS_REFUSE = 120_000_000
