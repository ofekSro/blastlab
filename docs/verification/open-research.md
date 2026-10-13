# Open verification research (from TODO.md P1)

Moved out of [`TODO.md`](../../TODO.md) on 2026-10-13 (owner-approved split, TODO.md at its
1000-line cap; `docs/batches/2026-10-13-todo-split-proposal.md`). Ids unchanged.
`blastlab/tests/test_foam_3d_smoke.py` says the parallel-vs-serial offset is "tracked in
TODO": its heading stays in TODO.md and points here.

## The residual ≈2 % parallel-vs-serial peak offset · **open, and narrowed**

The x/y symmetry break is closed (it was the ignition seed, and `det_radii` closes
it). What survives both mitigations is a **symmetric ≈2 % offset** that moves both
mirror gauges the same way and **flips sign between arms** — the signature of
temporal aliasing of the peak, not of a physical bias.

> **The settling run.** Take the `det_radii` arm exactly as it is and pin the
> timestep: `adjustTimeStep no` with a fixed `deltaT` below the smallest adaptive
> step either run took, everything else byte-identical, np = 1 vs np = 2. If the
> offset collapses, it is temporal aliasing and the fix belongs in **how blastlab
> samples the gauge**, not in the solver. If it survives at a fixed timestep,
> aliasing is excluded and the next cut is the probe-cell election under
> decomposition.

Full background: [docs/verification/blastfoam-claims.md §5](docs/verification/blastfoam-claims.md).

## Claim 3 — three experiments designed and not run

The wedge half-angle was **withdrawn** as a defect (1° is OpenFOAM's own documented
example, and blastFoam itself ships 1° wedges). What replaces it: the differentiator
between the vendor's working wedge+AMR+densityGradient cases and our nine dead runs
is the **`profile1d` hand-off state**, not the mesh.

| # | Rule | Threshold |
|---|---|---|
| **R3.1b** | vendor `mappedBuilding3D/wedge`, **1°** + AMR + densityGradient, unmodified | One-way: SIGFPE → CONFIRMED on vendor input; completion → null |
| **R3.2** | our reproducer, `densityGradient`, **with vs without** the `profile1d` hand-off, angle fixed at 1° | Hand-off dies and live-charge survives → the trigger is ours → **REFUTED as a solver defect** |
| **R3.3** | our reproducer at 1° vs 5°, all else identical | Prediction: **difference ≤ 1 %** in time-to-failure. A large difference would refute the `sin θ` cancellation argument |

*(`Lohner` is already the default everywhere, so this is a mechanism question, not a
blocker.)*

## Corrections the audit implies, not yet applied

- **`adjustLocations` is a no-op for every interior probe.** `core/case.py:90`,
  `:202`, `:310` and `writer.py:107-111` all state that it "snaps each gauge onto
  the centre of the cell holding it". **That is wrong for every interior gauge**,
  which is all of them. The comments need correcting.
- **The Claim 4 write-up names the wrong function.** It is
  `fluxScheme::snGradAlpha`, not `fluxScheme::AD` — fix it before the finding is
  quoted anywhere, because `::AD` sends a reader to a clean four-line function.
- **Prefer `sum(lambda)` over `count(lambda >= 0.99)`** in any future ignition
  measurement; the count is valid only at the first write.
