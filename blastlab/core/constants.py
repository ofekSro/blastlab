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
# blastFoam charge target (N5/T39). blastFoam's sphericalMassToCell sets
# alpha = 1 in the cells whose CENTRES fall inside r_exp, so the mass it
# actually deposits is the staircase volume: ~0.85 of the request at 5
# cells across the radius, and the deficit falls roughly as 1/n. 8 cells
# brings it to ~0.94 for a 2.6x (2D) / 4.1x (3D) cell-count cost. Native
# stays at MIN_EXP_CELLS = 5 - its outputs are byte-pinned, and T36
# rescales the products' energy instead.
FOAM_EXP_CELLS = 8
CELLS_2D_WARN  = 2_000_000
CELLS_2D_MAX   = 8_000_000
CELLS_WARN     = 4_000_000     # 3D
CELLS_REFUSE   = 15_000_000    # 3D

# blastFoam backend caps: the solve runs in WSL (C++, disk-backed);
# Python only ingests a few float64 grids per written frame (~32 B/cell),
# so the limits reflect ingest RAM + wall time + disk, not solver memory.
FOAM_CELLS_WARN   = 8_000_000
FOAM_CELLS_REFUSE = 120_000_000

# ── hardware-aware run plan (N17/T48) ───────────────────────────────────────
# The blastFoam solve runs inside the WSL VM, so the limits that matter are
# the VM's cores and RAM, not the Windows host's. `foam.env.plan_run` turns
# them into an MPI rank count and a pair of cell caps.

#: measured 2026-09-07 on this build (OpenFOAM-9 + blastFoam 6.2.0, serial,
#: 3D uniform hex mesh, /usr/bin/time -v peak RSS): 59,319 cells -> 305.1 MB
#: and 262,144 cells -> 843.3 MB, i.e. ~2.65 KB per cell at the margin on
#: top of a ~148 MB fixed cost. The per-cell figure is what scales, so it is
#: what the caps use; the fixed cost is inside the 30 % headroom below.
BYTES_PER_CELL = 2650

#: a rank below this many cells spends more time in decompose/reconstruct
#: and halo exchange than it saves
CELLS_PER_RANK = 50_000

#: RAM each rank needs to be worth starting (the mesh is split, but every
#: rank still carries the OpenFOAM runtime and its halos)
RAM_GB_PER_RANK = 2

#: fraction of VM RAM a run may claim before validation refuses / warns
RAM_REFUSE_FRACTION = 0.70
RAM_WARN_FRACTION = 0.35        # = 0.5 x the refuse cap
