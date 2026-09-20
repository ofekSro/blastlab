# REVERIFY_RESULTS.md — independent audit of the blastFoam defect claims

Branch `reverify`. Working hypothesis under test, per the prompt: **the mistake
is ours.** A claim is CONFIRMED only if it survived a genuine attempt to break it.

No contact was made with Synthetik, the blastFoam project, or any external party.
Local analysis only.

---

## 0. Scope — read this before the verdicts

**This audit did not run on the strong machine the prompt was written for.** It
ran on the same machine that produced the original findings. That is a material
limitation and it is stated up front rather than buried:

| Prompt step | Status here |
|---|---|
| C1.6 mesh convergence at dx = 0.00625 | **Not run.** The prompt itself costs it at ~8 h on this machine |
| C1.2 np = 16 / np = 32 | **Not run.** This machine does not have the cores |
| C2 mesh refined 2× and 4× | **2× only**, where it fit in budget |
| C3.2 "much finer base mesh, lower CFL" | **Not run** |
| Everything static (C1.1, C4, C3.1) | **Run in full** |
| C1.3 direct per-rank observation | **Run in full** — and it is the step the original work never did |

The static analysis is complete and is where the sharpest results are. Three of
the five claims turned out to be decidable without any large run at all.

---

## 1. Pre-registered decision rules

Written and committed **before** the runs they judge. This repo was once burned
by arguing after the numbers came in; the git history is the proof of order.

Every comparison records **peak, positive-phase impulse, and arrival** — never
peak alone. A 3.7 % impulse shift once passed every peak-only anchor in this suite.

| # | Rule | Threshold fixed in advance |
|---|---|---|
| **R1.2** | Count cells with `lambda >= 0.99` at the first written time, per processor directory, np = 1 vs np = 2 | `n(np=2) > n(np=1)` → mechanism CONFIRMED. `n(np=2) == n(np=1)` → attribution REFUTED |
| **R1.3** | Lever A: charge centre moved +dx/2 (strictly inside one cell) | parallel impulse deviation must fall to **≤ 0.3 %** for the corner story to hold |
| **R1.4** | Lever B: `det_radii=[dx]` | np-invariance within **±0.1 %** |
| **R1.5** | Convergence order from dx = 0.025 → 0.0125 | observed order in **[0.7, 1.3]** counts as first-order |
| **R2.1** | np-spread in peak at base mesh vs 2× refined | shrinks by **≥ 1.5×** → under-resolution artefact, REFUTED as solver defect; stays within **±20 %** of coarse → CONFIRMED |
| **R3.1** | Vendor `axisymmetricCharge` (wedge + AMR + densityGradient, 5°, maxRefinement 4) run **unmodified** | completes to its own endTime → Claim 3 REFUTED **as stated**; SIGFPE → CONFIRMED on vendor-authored input |
| **R3.2** | Our reproducer at 1° vs 5° half-angle, all else identical | 5° survives and 1° dies → our wedge angle is the cause, REFUTED as a solver defect |
| **R5.1** | Heavy 2D→3D chain hand-off | `n_floored == 0` and `min(rho) > 1e-2` → clean |

**R3.1 is the load-bearing one.** If the vendor's own shipped tutorial exercises
the exact combination we call fatal and it runs, the claim cannot stand in the
form it was written, whatever our reproducer does.

---

## 2. Sanity gate

| Check | Result |
|---|---|
| `test_foam_writer.py` (goldens, no WSL) | **PASS** — all 16 goldens byte-identical |
| `pgrep -a blastFoam` in WSL before every run | empty |
| `test_foam_1d_vs_native.py` | see §8 |
| `test_foam_kb_anchor.py` | see §8 |

---

## 3. Claim 4 — indexing bug in `fluxScheme.C` — **CONFIRMED (bug real, unreachable), CLAIM MISNAMES THE FUNCTION**

Static, no simulation, as the prompt specified.

**The bug is real, and it is not where the claim says it is.** The claim names
`fluxScheme::AD` at ~line 194. `fluxScheme::AD` is lines 98–102:

```cpp
Foam::fluxScheme::AD(const volScalarField& alpha) const
{
    return mag((this->Uf_() & alpha.mesh().Sf())/alpha.mesh().magSf());
}
```

That is a single field expression with **no indexing of any kind** — there is
nothing there to be wrong. Line 194 is inside a different function,
`fluxScheme::snGradAlpha` (definition starts line 105), in its coupled-patch
branch:

```cpp
if (patch.coupled())
{
    vectorField gradAlphaOwn(pgradAlpha.patchInternalField());
    vectorField gradAlphaNei(pgradAlpha.patchNeighbourField());
    forAll(gradAlphaOwn, facei)
    {
        snGradAlpha[facei] =                      // <-- internal field
            minMagSqrOp<vector>()(gradAlphaOwn[facei], gradAlphaNei[facei])
          & pSf[facei];
    }
}
else
{
    psnGradAlpha = pgradAlpha & pSf;              // <-- patch field, correct
}
```

`facei` here runs over the **patch's** faces, but it indexes `snGradAlpha`, the
**internal** surface field. The `else` branch three lines later shows the
intended target: `psnGradAlpha`, the patch field reference bound at line 186.
Two consequences, if it ever executed:

1. The coupled patch's own boundary values are never assigned — they keep the
   `fvc::snGrad(alpha)` values set at line 132.
2. Internal faces `0 .. nPatchFaces-1` — arbitrary faces at the head of the face
   list, geometrically unrelated to the patch — are overwritten with values built
   from patch-local gradients and patch face-area vectors.

The fix is one identifier: `snGradAlpha[facei]` → `psnGradAlpha[facei]`.

**Reachability — CONFIRMED unreachable.** Both functions are declared virtual in
`fluxScheme.H` (`snGradAlpha` line 244, `AD` line 250) and defined in
`fluxScheme.C`. A grep across all of `/root/blastfoam/src` and
`/root/blastfoam/applications` finds **no call site for either**:

- `snGradAlpha`: the only other hit in the tree is a *comment* in
  `dynamicFvMesh/dynamicRefineMultiFvMesh/multiCritRefinement.C:422` referring to
  an unrelated hard-coded AMR criterion of the same name. Not a call.
- `AD`: no `->AD(` or `.AD(` anywhere.

So the code is dead in the shipped solvers, and the defect has no runtime effect
in any configuration this project runs.

**What must change in blastlab:** nothing in the solver path. But the *report*
must be corrected before it is quoted anywhere — "a bug in `fluxScheme::AD`"
sends a reader to a clean four-line function and makes the whole finding look
wrong. It is `fluxScheme::snGradAlpha`, coupled-patch branch, line 194.

---

## 4. Claim 1 — parallel double ignition — static half: **CODE READING CONFIRMED, MECHANISM DESCRIPTION IMPRECISE**

**The missing guard is really there, in the build I have.** `activationModel.C`,
`detonationPoint::check`, lines 122–137:

```cpp
else
{
    label celli = mesh.findCell(pt);
    if (celli >= 0) { sumAlphaRho += alphaRho[celli]; nCells++; }
}
if (returnReduce(nCells, sumOp<label>()) == 0)   // == 0 only. Never > 1.
{ FatalErrorInFunction << ... }
```

and the same shape again in `detonationPoint::setActivated`, lines 181–199 —
which is where ignition actually happens:

```cpp
label celli = mesh.findCell(*this);
if (celli >= 0) { lambda[celli] = 1.0; nCells++; }
...
if (returnReduce(nCells, sumOp<label>()) == 0) { FatalErrorInFunction << ... }
```

Each rank calls `findCell` on its own partition; the reduction detects "nobody
found it" and never "more than one rank found it". That part of the claim is
exactly right, including the line numbers.

**But the claim's phrasing — "claimed by multiple ranks and ignites more than
once" — is wrong as physics, and the error is worth fixing before anyone acts
on it.** OpenFOAM's `decomposePar` assigns every cell to exactly one rank;
processor boundaries are shared *faces*, not shared cells. No cell can be
ignited twice. What actually happens at a corner point is that the geometric
inside-test succeeds for a *different* cell on each of the ranks whose partition
touches that corner, so **two or more distinct physical cells are set to
`lambda = 1.0` where serial sets one.** More ignited cells, not a doubly-ignited
cell.

The claim's energy reasoning survives this correction, for a reason it did not
state. `ESource()` is `ddtLambda()*e0_` (lines 537–539) with `e0_` in J/kg
(line 286), so each extra ignited cell releases that cell's own mass worth of
energy. Under `linear` activation the whole charge burns anyway, so the extra
cell is energy released **earlier and off-axis**, not extra energy over the run.
"Symmetry/field asymmetry, not an energy-conservation violation" is therefore
the right conclusion — reached by a different route than the report gives.

The runtime half of this claim (R1.2–R1.5) is in §6.

---

## 5. Claim 3 — static half: **our wedge is 5× more slivered than the vendor's, and the vendor ships the combination we call fatal**

Two static findings, both against the claim.

**(a) The topology is the vendor's; the angle is not.** Our writer's axisymmetric
`blockMeshDict` and the vendor's `axisymmetricCharge` use an identical collapsed
hex, `hex (0 1 2 3 0 4 5 3)`, with axis vertices 0 and 3 repeated, and the same
two `wedge` patches. That much is correct and is not the defect. The half-angle
is not the same:

| | half-angle | axis-cell azimuthal width at radius r | first-cell aspect ratio |
|---|---|---|---|
| vendor `axisymmetricCharge` | **5°** | `2 r sin 5° = 0.174 r` | ~11.5 |
| blastlab (`writer.py:47`, `HALF_ANGLE_DEG = 1.0`) | **1°** | `2 r sin 1° = 0.0349 r` | **~57** |

Our axis cells hold **5× less mass** than the vendor's at the same `dx`, and are
5× more slivered. Claim 3's own symptom is axis cells draining to
`rho ~ 1e-13`. A cell with a fifth of the mass drains in a fifth of the time
under the same outflow flux. This is a quantitative, untested-for contribution
to the exact failure mode, and it is ours, not blastFoam's.

`writer.py:543` documents the wedge as following `axisymmetricCharge` — the
tutorial it differs from by 5× on the one parameter that sets axis-cell volume.
The comment cites a source it does not match.

**(b) The vendor ships wedge + AMR + densityGradient as a working tutorial.**
`tutorials/blastFoam/axisymmetricCharge/constant/dynamicMeshDict`:

```
dynamicFvMesh   adaptiveFvMesh;
errorEstimator  densityGradient;
maxRefinement   4;
nBufferLayers   1;
lowerRefineLevel 0.05;
unrefineLevel    0.05;
```

That is the precise combination Claim 3 calls fatal — axisymmetric wedge,
adaptive mesh, `densityGradient` — at **four** refinement levels, more than any
of the nine runs that died (which used 1–3). If this tutorial runs, the claim
as written cannot stand. That is rule **R3.1**, and it is tested in §7.

---

## 6. Claim 1 — runtime

*(pending — see §9 for what ran)*

## 7. Claim 3 — runtime

*(pending — see §9 for what ran)*

## 8. Claims 2 and 5

*(pending — see §9 for what ran)*

## 9. Verdict table

*(filled in after the runs)*
