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

# Grid-size guard rails. The native per-cell cost is NOT ~200 B - see the
# NATIVE_* model below, which counts the arrays that are actually live.
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

# blastFoam backend CEILINGS: the solve runs in WSL (C++, disk-backed);
# Python only ingests a few float64 grids per written frame (~32 B/cell),
# so these limits reflect ingest RAM + wall time + disk, not solver memory.
# Since N21 they are an upper bound on the RAM-derived cap, never a
# fallback for it - a cap that RISES when the hardware is unknown is
# exactly backwards, and used to let an unprobed session start a run that
# could not fit.
FOAM_CELLS_WARN   = 8_000_000
FOAM_CELLS_REFUSE = 120_000_000

#: VM size assumed when the WSL probe has not answered (N21). WSL hands
#: out about half the host's RAM, so this is roughly the smallest VM a
#: machine that can run the app at all would get. Conservative on
#: purpose: an unknown machine must not be treated as a large one.
FOAM_VM_GB_ASSUMED = 4

# ── hardware-aware run plan (N17/T48) ───────────────────────────────────────
# The blastFoam solve runs inside the WSL VM, so the limits that matter are
# the VM's cores and RAM, not the Windows host's. `foam.env.plan_run` turns
# them into an MPI rank count and a pair of cell caps.

#: measured 2026-09-07 on this build (OpenFOAM-9 + blastFoam 6.2.0, serial,
#: 3D uniform hex mesh, /usr/bin/time -v peak RSS): 59,319 cells -> 305.1 MB
#: and 262,144 cells -> 843.3 MB, i.e. ~2.65 KB per cell at the margin on
#: top of a ~148 MB fixed cost. The per-cell figure is what scales, so it is
#: what the caps use; the fixed cost is inside the 30 % headroom below.
#:
#: Re-measured 2026-09-10 on completely different hardware (i7-14700,
#: 128 GB host, 62 GiB WSL VM) with three serial 3D points - 32,768 cells
#: -> 224.9 MiB, 74,088 -> 326.2 MiB, 140,608 -> 501.5 MiB. Least-squares
#: slope 2,696 B/cell with R^2 = 0.9996, constant 138.8 MiB. So the model
#: holds across machines to under 2 % and does NOT need measuring per
#: machine - but both that fit and a recomputation of T48's own two points
#: land slightly ABOVE 2,650, i.e. the old value under-estimated memory and
#: approved marginally-too-large cases. Rounded up rather than down.
BYTES_PER_CELL = 2700

#: a rank below this many cells spends more time in decompose/reconstruct
#: and halo exchange than it saves
CELLS_PER_RANK = 50_000

#: RAM each rank needs to be worth starting (the mesh is split, but every
#: rank still carries the OpenFOAM runtime and its halos)
RAM_GB_PER_RANK = 2

#: fraction of VM RAM a run may claim before validation refuses / warns
RAM_REFUSE_FRACTION = 0.70
RAM_WARN_FRACTION = 0.35        # = 0.5 x the refuse cap

# ── native solver memory model (N21) ────────────────────────────────────────
# The native solvers run in the GUI's OWN process, on the Windows host's
# RAM, so a grid that does not fit raises MemoryError and takes the window
# with it. Until N21 nothing here consulted any memory figure at all - the
# caps were fixed constants and the docstring claimed ~200 B/cell.
#
# These numbers are ANALYTIC: counted from the arrays each solver actually
# allocates, not measured. That is good enough because the 0.60/0.30
# fractions below swamp a 20 % model error, and because the derived cap can
# only ever lower the fixed caps above (see core.hardware.plan_native).

#: peak transient during one step. 3D: U 40 + primitives 56 + U_new 40 +
#: one sweep's face/flux temporaries (~390, freed per sweep by `del F`) +
#: persistent masks/accumulators. 2D pays a smaller sweep but holds Fx
#: while Fy is built, so the two land close together.
NATIVE_PEAK = {2: 480, 3: 580}

#: order 2 (MUSCL) adds slopes, face states and their primitives
NATIVE_ORDER2_EXTRA = {2: 150, 3: 190}

#: held in the Result for the whole session, independent of snapshots.
#: 2D is far worse than 3D: it keeps final_state (6 float64 grids) and
#: trigger_state (6 more) on top of p_peak/impulse.
NATIVE_HELD_BASE = {2: 113, 3: 17}

#: per retained snapshot. 2D keeps p, rho and speed as float64 (24);
#: 3D keeps one float32 p (4), and solver3d already caps the count.
NATIVE_HELD_PER_SNAP = {2: 24, 3: 4}

#: fraction of TOTAL host RAM a native run may claim. Lower than the VM
#: fractions: this process also holds Tk, matplotlib, the pyvista scene
#: and whatever earlier Results the user has not closed.
NATIVE_RAM_REFUSE_FRACTION = 0.60
NATIVE_RAM_WARN_FRACTION = 0.30

#: the derived cap never falls below this, whatever the machine says -
#: every shipped example and every regression baseline must stay runnable
#: (make_baseline's largest case is 80^3 = 512k cells)
NATIVE_CELLS_FLOOR = {2: 2_000_000, 3: 2_000_000}
