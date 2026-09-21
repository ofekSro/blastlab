# Prompt: independent re-verification of every blastFoam bug we think we found

Copy everything below this line into a fresh Claude Code session on the strong
machine, from the repo root.

---

You are on a machine considerably stronger than the one where this repo's
findings were produced. Your job is to **re-verify, from scratch and
adversarially, every defect this project has attributed to blastFoam itself**.
The working hypothesis you must actively try to prove is: **the mistake is
ours** — in blastlab's writer, mesh construction, decomposition choices,
measurement harnesses, or interpretation — and not in blastFoam. Only a claim
that survives your genuine attempt to break it may be marked CONFIRMED.

Rules of engagement:

- **Do not contact or report anything to Synthetik / the blastFoam project or
  anyone else.** Local analysis only. This is an explicit owner decision.
- Do not change solver behaviour, defaults, or committed tests. Your only
  repo output is a new file `REVERIFY_RESULTS.md` (plus scratch harness
  scripts under a scratch directory). Work on a branch `reverify`.
- **Pre-register every decision rule** in `REVERIFY_RESULTS.md` *before* the
  runs that it will judge, with the numeric threshold written down. This
  repo was once burned by arguing after the numbers came in.
- **Never measure peak alone.** Every comparison records peak, positive-phase
  impulse, and arrival. A 3.7 % impulse shift once passed every peak-only
  anchor in this suite.
- Long runs: `python -u`, no timeout, run in background. Before any WSL run,
  confirm no foreign solver is running (`pgrep -a blastFoam` inside WSL must
  be empty) — a busy VM corrupts memory-sensitive tests.
- Verdicts: **CONFIRMED** (blastFoam defect reproduced independently),
  **REFUTED** (our mistake — name it and say what in blastlab must change),
  **INCONCLUSIVE** (say exactly what run would settle it).

## Environment

- Windows + WSL Ubuntu, OpenFOAM-9 and blastFoam **6.2.0** built at
  `/root/blastfoam` (sourced from the WSL bashrc). blastlab talks to it via
  `blastlab/solvers/foam/` (see `env.py` for the availability check).
- Sanity gate before anything else: `cd blastlab/tests` and run
  `python test_foam_writer.py`, then `python -u test_foam_1d_vs_native.py`
  and `python -u test_foam_kb_anchor.py` (WSL). All must pass before you
  trust any measurement you make.
- Background reading in this repo: `TODO.md` sections N5-7 (root cause,
  verdict, archive), P1-6, N5-11, and the 13–14.09 QA-night observation on
  fixed-mesh parallel symmetry. They state our claims and our evidence.
  Read them as *claims under audit*, not as facts. `BLASTFOAM_SOLVER_REVIEW.md`
  may exist locally (untracked) — same status.

## Claim 1 — parallel double ignition when the detonation point sits on a
## processor-boundary cell corner (`activationModel.C`)

**Our claim.** blastlab's writer places the detonation point exactly on an
interior cell corner (the domain centre, with `effective_dx` dividing the
domain evenly) — a configuration no official tutorial uses. In
`activationModel.C` (~lines 124–131) each rank runs its own `findCell`; the
code checks `returnReduce(nCells) == 0` but never `> 1`, so a corner point on
a partition plane is claimed by multiple ranks and ignites more than once.
Because `ESource = ddtLambda*e0` (~lines 537–539) is energy per reacted
*mass*, the result is a symmetry/field asymmetry, **not** an energy-conservation
violation. Serial reference (planar 4×4 m, 400 kg/m TNT at (2,2), uniform
dx = 0.025, gauge (3.2, 2.0), impulse integrated on the common window
t ≤ 0.369 ms): impulse 983.4 Pa·s. Parallel scotch runs deviate by a few %
near-field (archived worst case +7 % at Z = 0.175 for np = 2).

**How to attack it.**
1. Re-read the current `activationModel.C` in `/root/blastfoam` yourself.
   Confirm the missing `> 1` guard is really there in the build you have.
2. Reproduce the deviation: same case, np = 1 vs 2, 4, 8 (scotch). Then go
   heavier than we could: np = 16 and, memory permitting, np = 32.
3. **Direct observation, not inference** (we never did this): after the first
   written time, read `lambda.expl` per processor directory and count which
   ranks hold activated cells around the det point. Two ranks igniting = the
   mechanism is real. One rank = our attribution is wrong; find the true
   source of the parallel deviation.
4. Falsification lever A: move the charge centre by +dx/2 so the det point is
   strictly inside one cell (tutorial-style). If the parallel deviation does
   **not** collapse to ≲0.3 %, the corner story is wrong or incomplete.
5. Falsification lever B: `det_radii=[dx]` (the `Case2D.det_radii` field,
   guide §5.6.1 mechanism) selects ignition cells by distance per rank and
   should be partition-invariant. We measured np-invariance ±0.1 % with a
   +3.1 % serial offset at dx = 0.025. Re-measure both.
6. Mesh convergence, one level deeper than we managed: corner and radii at
   dx = 0.025, 0.0125, **0.00625** (we never ran the last one — ~8 h on the
   old machine). We claim both extrapolate first-order to a common limit
   919 ± 2 Pa·s (corner: 983.4 → 950.3; radii: 1014.0 → 967.8). Check the
   observed convergence order is actually ~1, and whether the common limit
   holds. If the two configurations extrapolate to *different* limits, our
   whole N5-7 verdict ("corner stays, it's plain discretization error")
   falls, and you should say what replaces it.

## Claim 2 — a parallel deviation channel that has nothing to do with AMR
## (fixed-mesh symmetry breaking, decomposition-dependent near field)

**Our claim.** On a completely fixed uniform mesh (no AMR), the x/y symmetry
of the solution degrades 0.10 % → 0.26 % → 4.85 % across np = 1/2/8, and the
absolute peak moves ±7 % between np counts in the extreme near field
(Z ≈ 0.075 m/kg^⅓); at engineering ranges (Z ≈ 0.175) scotch np = 2 gave
+7.00 % peak while passing a 0.26 % symmetry gate — i.e. our symmetry gate
cannot see it. Details in the TODO archive section "method scotch".

**How to attack it.** Reproduce at our resolutions, then refine the mesh
2× and 4×: if the np-dependence shrinks systematically with resolution, this
is discretization × decomposition interplay (our "bug" framing is wrong — it
is an under-resolution artefact and REFUTED as a solver defect). If it
persists at fixed magnitude, CONFIRMED. Compare `scotch` against
`simple`/`hierarchical` splits with identical everything else, several seeds
of gauge placement, and both symmetric gauge pairs. Note whether Claim 1's
double ignition explains part of it (run the same matrix with the charge
centre nudged strictly inside a cell to decouple the two).

## Claim 3 — axisym + AMR + densityGradient dies in SIGFPE because split
## wedge axis cells drain to vacuum (P1-6)

**Our claim.** adaptiveFvMesh *does* refine wedge axis cells (measured
cellLevel = 1 on the axis column, contrary to folklore). With the
`densityGradient` estimator, the charge "crater" near the axis (strong
density gradient under perfectly flat p = 101325 Pa) keeps those cells
refined until they drain to rho ≈ 1e-13 (T = 0 next to T = 2e10) and
blastFoam SIGFPEs in `decode()` at 3–7 ms. Nine user runs died across every
combination of base cell (0.5/0.25/0.15), levels (1–3), thresholds, CFL
(0.4/0.25), np (1/10/14). A 10-variant single-change A/B matrix on the kept
serial reproducer: every densityGradient variant (protectedPatches, threshold
changes, unrefinement off, interval/buffer changes) died ~6.3 ms; V8/V9 —
estimator swapped to Lohner on p — ran clean to 9 ms. Since 2026-09-20
Lohner is blastlab's default everywhere; the claim under audit is the
*mechanism* and the implied upstream defect (axis-cell splitting drains mass).

**How to attack it.** The reproducer recipe is in TODO P1-6 (10×10 axisym,
profile1d hand-off, charge at the origin, two obstacles). Rebuild it (or an
equivalent axisym charge case that crashes with
`amr_estimator='densityGradient'` explicitly set — the writer honours the
explicit choice).
1. First suspect **our wedge construction**: compare the writer's
   blockMeshDict (wedge angle, axis handling, cell aspect near the axis)
   against blastFoam's own axisymmetric tutorials. If our wedge geometry or
   mesh quality near the axis differs from the vendor's pattern, fix a local
   copy to match the tutorial pattern and re-run: if the crash disappears,
   this is REFUTED (our mesh, not their AMR).
2. With the strong machine, run the densityGradient case at a much finer
   base mesh and lower CFL: if it survives, the "no knob changes this" part
   of our claim is wrong (it was under-resolution).
3. Check whether the axis mass drain also happens with Lohner, just slower —
   track min(rho) on the axis column over time in both. If Lohner merely
   postpones the same drain past our end times, our "Lohner is clean"
   conclusion is too strong; quantify.
4. Verify the core mechanism directly: dump cellLevel and rho along the axis
   column over time and show the split-then-drain sequence — or show it
   doesn't happen and the SIGFPE originates elsewhere (where?).

## Claim 4 — dead-code indexing bug in `fluxScheme.C` (~line 194,
## `fluxScheme::AD`)

Static claim, never executed at runtime. Re-read the function in your build
and give a two-paragraph verdict: is the indexing actually wrong, and is the
code truly unreachable? No simulation needed.

## Claim 5 (secondary) — blastFoam's own 2D stage produced near-vacuum cells
## (N5-11)

A 2026-09-11 chain artefact had min(rho) = 1.711e-4 with 20 sub-1e-3 cells
*in the 2D stage output itself* (the remap only inherited them). No current
path reproduces it — every hand-off we tested lands min(rho) ≈ 1.2, zero
floored cells. On the strong machine, run one heavy 2D→3D chain at higher
resolution than we could and check `n_floored` and min(rho) at the hand-off.
If clean, recommend removing the `RHO_MIN = 1e-3` floor in
`writer.profile_state` (do not remove it yourself).

## Deliverable

`REVERIFY_RESULTS.md` at the repo root, on branch `reverify`, containing:
per claim — the pre-registered rule, the runs (exact case parameters, np,
dx, wall time), the three quantities (peak / impulse / arrival) for every
comparison, the verdict, and for every REFUTED item the specific blastlab
change it implies. End with a table: claim / verdict / one-line reason.
Commit the report; do not merge, do not push to any remote you were not
told about, and — again — do not send anything to any external party.
