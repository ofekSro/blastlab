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
| C1.6 mesh convergence at dx = 0.00625 | **Not run.** 640×640 = 409,600 cells at 4× the step count ≈ 64× the base case; the prompt itself costs it at ~8 h here |
| C1.2 np = 16 / np = 32 | **np = 16 run.** See §6 — the host is an i7-14700, 20 physical / 28 logical cores, 128 GB (CLAUDE.md §3), so this was never core-limited. np = 32 would oversubscribe 28 logical cores and was skipped as meaningless, not as impossible |
| C2 mesh refined 2× and 4× | **Not run** — the serial-solver budget went to Claim 1 |
| C3.2 "much finer base mesh, lower CFL" | **Not run** |
| Everything static (C1.1, C4, C3.1) | **Run in full** |
| C1.3 direct per-rank observation | **Run in full** — and it is the step the original work never did |

*(An earlier draft of this table claimed the machine "does not have the cores"
for np = 16. That was wrong — CLAUDE.md §3 records 28 logical cores. Corrected,
and np = 16 was then actually run.)*

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
| `pgrep -a blastFoam` in WSL before every run | empty (scripted guard, aborts on a hit) |
| `test_foam_1d_vs_native.py` | see §8 |
| `test_foam_kb_anchor.py` | see §8 |

---

## 2a. How the static claims were attacked

Reading code and agreeing with yourself is not verification. Each of the three
static verdicts was handed to **three independent skeptics**, each given a
different lens and instructed to *refute* it, to default to `refuted = true`
under genuine uncertainty, and to cite `file:line` with quoted code. Nine
skeptics, no shared context, all read-only and forbidden from running any solver
(a busy VM would have corrupted the measurement running at the time).

| Verdict | Lenses | Refuted |
|---|---|---|
| Claim 4 — `snGradAlpha` bug, dead, misnamed | is-the-bug-real / is-it-really-dead / function-naming | **0 / 3** |
| Claim 1 static — missing `> 1` guard, mechanism corrected | cell-ownership / findcell-behaviour / energy-accounting | **0 / 3** |
| Claim 3 static — wedge angle is ours and causal | geometry-math / is-1deg-actually-wrong / tutorial-equivalence | **3 / 3** |

The pass earned its keep by **destroying one of my own findings** (§5) rather
than by confirming the other two. It also materially sharpened the two that
survived — the `blastProbes` owner-election evidence in §4 and the
out-of-bounds-write severity in §3 both came from skeptics, not from me.

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

**The indexing really is raw internal-field access.** `GeometricField` and
`DimensionedField` declare **no** `operator[]`, so `snGradAlpha[facei]` resolves
`GeometricField → DimensionedField → Field → List → UList` to
`UList<scalar>::operator[]` (`UListI.H:167-173`), a bare `return v_[i];` into
internal storage whose size for a `surfaceScalarField` is
`surfaceMesh::size(mesh) = mesh.nInternalFaces()`. And `facei` cannot secretly be
global: `forAll(gradAlphaOwn, facei)` iterates a field that
`fvPatch::patchInternalField` allocates at `Field<Type>(size())` — patch size —
and the *same* `facei` indexes `gradAlphaNei[facei]` and `pSf[facei]` in the same
statement, so it cannot be patch-local on the right and global on the left.

**The author's own correct idiom sits next door.** `HLLFluxScheme.C:174-197` is
the structurally identical coupled-patch loop and writes `pD[facei]` — the patch
field — never `D[facei]`. That is exactly the `psnGradAlpha[facei]` this function
fails to write.

**Two ways it is worse than first stated.** `coupledFvPatch::coupled()` is true
for **cyclic** patches in serial too (`coupledFvPatch.H:98-101`), so this is not
purely a parallel-run concern. And the build is
`linux64GccDPInt32Opt` — `FULLDEBUG` off, `checkIndex` compiled out — so on any
mesh where a coupled patch has more faces than `nInternalFaces`, this is an
**unchecked out-of-bounds heap write**, not merely field corruption.

**Reachability — CONFIRMED unreachable**, by two independent methods.
Source: an unfiltered tree-wide grep finds `snGradAlpha` in exactly two files
(`fluxScheme.C`, `fluxScheme.H`) plus one unrelated *comment* at
`multiCritRefinement.C:422`, whose actual code calls `fvc::snGrad(fld)`. None of
the eight derived flux schemes overrides it.
Link level: the mangled symbol is defined (`T`) only in `libblastFiniteVolume.so`
and has **zero undefined references** across all 19 libraries and 21 executables —
while the same sweep as a control *does* surface `fluxScheme::update`, `Uf()`,
`energyFlux()`, `NewSingle` and `NewMulti` as undefined refs, proving the method
would have caught a real reference.

**One qualification to my own correction.** `fluxScheme::AD` *is* virtual and *is*
overridden by `fluxSchemes::HLL::AD` (`HLLFluxScheme.C:143-201`), which is 59
lines and full of indexing — correct indexing, and by coincidence *its* file's
line 194 also falls inside it. So the original report's "`fluxScheme::AD`" was
probably aiming at the override rather than being pure nonsense. It is still the
wrong qualified name in the wrong file, and still needs fixing before the finding
is quoted — but "AD contains no indexing at all" is true of the **base** only.

**What must change in blastlab:** nothing in the solver path. The *report* needs
the name corrected to `fluxScheme::snGradAlpha`, coupled-patch branch, line 194,
`fluxScheme.C`.

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
(line 286), and `ESource` is **mass-weighted before it reaches the energy
equation, in two stages** (`*rho_` at the phase thermo, `*alpha` at the mixture
thermo), so each ignited cell deposits exactly `α_i·ρ_i·V_i·e0·Δλ_i` — that
cell's **own** explosive mass worth of energy. That is why the bug cannot mint
energy: **it ignites extra cells, it does not create mass.** Under `linear`
activation `tIgn_` is set geometrically for *every* cell and `correct()` uses
`max()`, so a prematurely forced cell simply stays at 1 — the extra cell is
energy released **earlier and off-axis**, not extra energy over the run.
"Symmetry/field asymmetry, not an energy-conservation violation" is therefore
the right conclusion.

### Three things the adversarial pass added that make this claim stronger

**1. The inclusive tolerance is deliberate, and documented as such.**
`mesh.findCell(pt)` defaults to `CELL_TETS` → `cellTree().findInside(p)` →
`treeDataCell::contains` → `polyMesh::pointInCell` →
`polyMeshTetDecomposition::findTet` → `tetrahedron::inside(pt)`, whose own
comment says it assumes *"the point is in the tet unless 'definitively' shown
otherwise by obtaining a positive dot product greater than a tolerance of
small"*. The normal is unit-normalised, so the rejection threshold is an absolute
distance of `small` ≈ 2.22e-16 m. The roundoff residual for a point sitting
exactly on a shared face is ~(cell size)×ε ≈ 1e-18 for cm-scale cells —
comfortably **inside** the tolerance. Each rank's octree is built only over its
own local points, so each rank returns its own distinct local cell.

**2. blastFoam's own code already implements the fix, elsewhere.** This is the
strongest evidence in the whole audit and it is not an inference:
`blastProbes::findElements` does exactly the arbitration `activationModel`
omits — it elects a single owning rank via `reduce(proc, maxOp<label>())` and
clears `celli` on every other rank. Upstream OpenFOAM's `probes` does the same.
**The same authors wrote owner-election for probes and not for detonation
points.** Code that only makes sense if `findCell` returns `>= 0` on multiple
ranks for one point.

**3. The trigger is broader than "corner", and the `radii` branch is immune
by construction.** Any detonation point lying on a processor patch *face, edge
or vertex* produces the multi-rank hit, since the inside-test is inclusive on the
shared plane; a corner is merely where the most ranks can hit. And the whole
effect is confined to the `radius_ <= small` branch — the `radius_ > small`
branch tests cell **centres** (`mag(mesh.C()[celli] - pt) < radius_`), and every
cell centre lives on exactly one rank, so that path is **partition-invariant by
construction**. That is a code-level explanation for why lever B (`det_radii`)
was measured np-invariant to ±0.1 %, and it converts R1.4 from an empirical
observation into a prediction.

One scoping refinement: "succeeds on each rank whose partition touches that
corner" is marginally stronger than the code guarantees — each rank's hit depends
on its own tets clearing the 2.22e-16 m threshold, so the code guarantees only
that **two or more** ranks can succeed, not that every touching rank does.

The runtime half of this claim (R1.2–R1.5) is in §6.

---

## 5. Claim 3 — static half: **my own first verdict here was wrong, and was refuted**

I originally wrote that blastlab's 1° wedge half-angle (vs the vendor
`axisymmetricCharge`'s 5°) made our axis cells "5× more slivered", that this was
"a quantitative, untested-for contribution to the exact failure mode, and it is
ours, not blastFoam's", and that `writer.py:543` "cites a source it does not
match".

**Three independent skeptics refuted that, all at high confidence, and they are
right.** The audit's own working hypothesis — *the mistake is ours* — turned out
to apply to my finding as much as to the original report. Recording it in full,
because a re-verification that only ever overturns other people's work is not a
re-verification.

### What survives: the arithmetic only

| | half-angle | axis-cell volume | `1/sin θ` |
|---|---|---|---|
| vendor `axisymmetricCharge` | 5° | — | 11.5 |
| blastlab (`writer.py:47`) | 1° | **4.976× smaller** | 57 |

The golden vertices are exactly `4·cos 1°` and `4·sin 1°`, the hex topology is
identical to the vendor's, and the volume ratio is right. Everything I built on
top of those numbers was wrong.

### Refutation 1 — 1° is not a deviation; it is the OpenFOAM norm

- The **OpenFOAM-9 User Guide** (§5.2.1) uses **1°** as its own worked wedge
  example; Figure 5.2 prints `< 5°` as a **ceiling**, not a target.
- `wedgePolyPatch.C:113` names the reference half-angle as **"~2.5deg"**, and the
  only hard check is a degeneracy test (`sin θ < ~1e-15`) that 1° clears by
  13 orders of magnitude. No warning, no error.
- OpenFOAM-9's own wedge tutorials run at **0.100 / 0.504 / 1.000 / 2.500 /
  2.500 / 2.500 / 5.711°**. Not one uses 5.0. `coldEngineFoam/freePiston` sits
  at exactly 1.000.
- **blastFoam itself ships 1° wedges**: `mappedBuilding3D/wedge`
  (`blockMeshDict:22-24`) and `mappedBuilding3D/sector` (`:20-24`), both
  `cos/sin(pi/180)`, both collapsed hexes with wedge patches.

So the 5× gap is **internal to the vendor's own tree** (`axisymmetricCharge` and
`movingCone` at 5°, the two `mappedBuilding3D` cases at 1°). blastlab copied one
of the vendor's own two values. If anything the deviation points the safe way:
wedge geometric error is `1 − sin(2θ)/(2θ)`, which is `2.0e-4` at 1° against
`5.1e-3` at 5° — the 1° mesh is ~25× more faithful to true axisymmetry, and to
`writer.py:1356-7`'s own per-radian volume normalisation.

**My `writer.py:543` accusation was a misreading.** `writer.py:14` explicitly
names `mappedBuilding3D/sector` — the **1°** tutorial — as the sector template,
and `writer.py:47` shares `HALF_ANGLE_DEG` across "1D sector, 2D axisym".
`writer.py:15` cites `axisymmetricCharge` only for "2D wedge orientation and
face sets", which match exactly. The docstring is accurate. I withdraw the charge.

### Refutation 2 — the drain mechanism cannot depend on the wedge angle

This is the one that actually matters, and it is a clean piece of physics I got
backwards. My argument assumed "a fifth of the mass drains in a fifth of the time
**under the same outflow flux**". The flux is not the same.

In a wedge, **every flux-carrying face area scales with `sin θ` exactly as the
cell volume does** — radial face `2·r·sin θ·Δy`, axial faces `V/Δy` — and the two
wedge constraint faces carry **identically zero** scalar flux
(`wedgeFvPatchScalarField.C:37-40`: `snGrad() == 0`). blastFoam advances density
as `rho_ -= dT*fvc::div(rhoPhi_)`, and `fvc::surfaceIntegrate` ends in
`ivf /= mesh.Vsc()`. The drain rate is therefore `Σφ_f / V`, **in which `sin θ`
cancels outright**. The only residual is `1/cos θ`:

    cos(1°)/cos(5°) = 1.0037   →   a 0.37 % difference, not 5×

The timestep half of the argument dies the same way: `compressibleSystem::CoNum`
forms `0.5·Δt·Σ|amaxSf|/V` and **explicitly zeroes the wedge patches**. Identical
drain rate and identical step size means identical drain time. The wedge angle is
a pure scale factor on the third dimension of a 2-D axisymmetric discretisation.

My aspect-ratio figures were also **2× overstated**: 57 and 11.5 are `1/sin 1°`
and `1/sin 5°`, i.e. radial extent over *half* the azimuthal width; the full-width
numbers are 28.6 and 5.7. And `checkMesh` never reports them for this mesh anyway —
`polyMesh::calcDirections` knocks wedge directions out of `solutionD`, and
`primitiveMeshTools::cellClosedness` restricts aspect ratio to directions with
`meshD[dir] == 1`.

### Refutation 3 — and this invalidates my own pre-registered rule R3.1

`mappedBuilding3D/wedge` is a **1° half-angle** wedge case whose `dynamicMeshDict`
is **line-for-line identical** to `axisymmetricCharge`'s: `adaptiveFvMesh` +
`errorEstimator densityGradient` + `maxRefinement 4`. **The vendor ships 1° wedge
+ AMR + densityGradient, at the very aspect ratio I called pathological.**

Worse for my rule: **neither vendor wedge case contains the failure mechanism's
stated trigger.** Both are live charge cases run through `setRefinedFields` from
`t = 0` with uniform `p = 101298` and uniform `rho.air = 1.225`. The blastlab
reproducer in TODO P1-6 is a **`profile1d` hand-off** that arrives *already
reacted* (`lambda` uniform 1, empty detonation points) carrying cells the remap
already floored at `RHO_MIN = 1e-3`, with a steep density gradient co-located
with perfectly flat `p = 101325` (blastlab's `P_AIR`, **not** blastFoam's
ambient `101298`).

Therefore **R3.1 as I pre-registered it is an invalid rule.** I wrote:

> R3.1 — vendor `axisymmetricCharge` run unmodified → completes to its own
> endTime → Claim 3 **REFUTED as stated**.

That inference does not follow. A tutorial that does not contain the trigger
proves nothing by completing. **R3.1 is a one-way test only:** a SIGFPE would be
strong CONFIRMED evidence; completion is null. I am not quietly repairing this —
the rule was pre-registered and it was wrong, and the honest record is that the
*equivalence analysis*, not the run outcome, is what killed it.

The `maxRefinement 4` comparison must also be dropped: levels are relative to
base cell size. The vendor's base is 1 m over 20×20 m, so its finest cell is
0.0625 m — **coarser** than four of the nine failing blastlab combinations
(base 0.5/0.25/0.15 m over 10×10 m).

### What replaces it

The wedge angle is out as a causal hypothesis. The differentiator between the
vendor's working wedge+AMR+densityGradient cases and our nine dead runs is the
**`profile1d` hand-off state**, not the mesh. Revised rules in §5a.

---

## 5a. Revised rules for Claim 3 (pre-registered before the §7 runs)

| # | Rule | Threshold |
|---|---|---|
| **R3.1** *(demoted)* | vendor `axisymmetricCharge`, 5°, unmodified | **one-way only**: SIGFPE → CONFIRMED on vendor input. Completion → **null result**, proves nothing |
| **R3.1b** *(new)* | vendor `mappedBuilding3D/wedge`, **1°** + AMR + densityGradient, unmodified | same one-way logic, but at *our* half-angle — removes the angle as a variable from the vendor side |
| **R3.2** *(reframed)* | our reproducer, `densityGradient`, **with vs without** the `profile1d` hand-off, wedge angle held fixed at 1° | hand-off dies and live-charge survives → the trigger is the hand-off state (ours), not blastFoam's AMR → **REFUTED as a solver defect** |
| **R3.3** *(new)* | our reproducer at 1° vs 5°, all else identical | pre-registered prediction from Refutation 2: **difference ≤ 1 %** in time-to-failure. A large difference would refute the `sin θ` cancellation argument |

---

## 6. Claim 1 — runtime: **CONFIRMED by direct observation, with one part of the attribution REFUTED**

This is the step the prompt flagged as never having been done: *"Direct observation,
not inference (we never did this): read `lambda` per processor directory and count
which ranks hold activated cells around the det point."* It has now been done.

### Setup, verified before running

Planar 4×4 m, 400 kg/m TNT, `charge_refine='global'`, AMR off. The writer was
asked what mesh it would produce **before** any solver ran: `nx=ny=160`,
`dx=0.025`, `n_cells=25600`, `refine_zones=None` — a genuinely **uniform** mesh,
as Claim 1 specifies. (Worth checking: `FOAM_EXP_CELLS=8` needs `r_exp/8 = 0.035 m`
and `dx=0.025` is already finer, so the charge-resolution rule correctly declines
to refine. Had it refined, the whole comparison would have been silently invalid.)

`det_points` comes back **empty**, so ignition falls back to the charge centre
(`writer.py:1067`): the point is `(2.0, 2.0)`. With 160 even cells over 0–4 m,
`2.0/0.025 = 80` exactly — **the point sits precisely on an interior cell corner**,
the configuration the claim is about. Confirmed independently, not assumed.

### R1.2 — activated cells at the first written time (`t = 1.2e-07`)

| decomposition | planes through (2,2)? | activated cells | per rank |
|---|---|---|---|
| **serial** | — | **1** | — |
| scotch np=2 | no | **1** | `p0:0 p1:1` |
| scotch np=8 | no | **1** | `p7:1`, rest 0 |
| scotch np=4 | yes | **4** | `p0:1 p1:1 p2:1 p3:1` |
| `simple (2 1 1)` — plane on x=2.0 | 2-way | **2** | `p0:1 p1:1` |
| `simple (2 2 1)` — planes on x=2.0 **and** y=2.0 | 4-way | **4** | `p0:1 p1:1 p2:1 p3:1` |

**The mechanism is real, and the dose-response is exact: an N-way partition
boundary on the detonation point ignites N cells where serial ignites 1.**

Two details that matter more than the headline:

1. **Never two on one rank.** Every hit is `1` per rank, never `2`. That is the
   direct confirmation of the corrected mechanism in §4 — OpenFOAM cannot ignite
   one cell twice; it ignites *N distinct cells, one per rank*. The original
   report's "ignites more than once" phrasing described the right symptom with
   the wrong physics.
2. **I had to construct the trigger; hoping for it is not a test.** `scotch` at
   np=2 does **not** put a boundary through the domain centre — it ignites 1 cell,
   identical to serial. So the first attempt measured *nothing*, and only the
   forced `simple` decompositions exposed the effect.

### The part of the attribution that is REFUTED

The claim states: *"Parallel scotch runs deviate by a few % near-field (archived
worst case **+7 % at Z = 0.175 for np = 2**)."* — attributing that deviation to
this double-ignition mechanism.

**At scotch np = 2 the detonation point ignites exactly one cell, the same as
serial.** There is no over-ignition there at all. Whatever produced the archived
+7 % at np = 2, **it is not this mechanism.** That deviation belongs to Claim 2's
separate channel and still needs a cause.

So Claim 1 splits:

- **The mechanism: CONFIRMED** — reproduced independently, with a dose-response
  the original work never measured, and now explained at code level.
- **The attribution of the np = 2 near-field deviation to it: REFUTED.**

### R1.3 / R1.4 — the two levers, tested against the worst case

Rather than re-run the levers against a decomposition that never triggered the
bug, both were tested against `simple (2 2 1)` np=4, where the untreated case
ignites 4 cells instead of 1:

| variant | serial | worst-case np=4 | verdict |
|---|---|---|---|
| base (untreated) | 1 | **4** | 4× over-ignition |
| **lever A** — centre + dx/2 | 1 | **1** (`p3:1`, rest 0) | **works, exactly** |
| **lever B** — `det_radii=[dx]` | 4 | **4** (`p0:1 p1:1 p2:1 p3:1`) | **works, exactly** |

Both levers now have a **code-level explanation, not just a measurement**:

- **Lever A** moves the point strictly inside one cell, so exactly one rank's
  `findCell` can succeed.
- **Lever B** switches `detonationPoint::check`/`setActivated` from the
  `radius_ <= small` branch to the `radius_ > small` branch, which tests cell
  **centres** (`mag(mesh.C()[celli] - pt) < radius_`). Every cell centre lives on
  exactly one rank, so that path is **partition-invariant by construction**. The
  4 cells it selects are the 4 meeting at the corner (centres at `0.707·dx < dx`),
  and under np=4 they are the *same four physical cells*, merely split one per
  rank. This converts the previously-empirical "np-invariant to ±0.1 %" into a
  guarantee that follows from the source.

### What blastlab should do about it

`det_radii` is already wired through `Case2D`/`Case3D` and `validate_case`
(N5-12). Given that lever B is partition-invariant *by construction* and lever A
depends on the user not landing on a cell boundary, **the robust fix is to default
`det_radii` to one base cell for blastFoam cases** rather than to keep relying on
the writer never placing a detonation point on an interior corner — which it does
by default, since `effective_dx` divides the domain evenly and the charge centre
is the domain centre.

---

## 7. Claim 3 — runtime

### R3.1 — vendor `axisymmetricCharge`, 5° wedge + AMR + `densityGradient`

Run unmodified except that the `blockMeshDict`'s `#calc` arithmetic was
pre-evaluated by hand. That substitution was forced, not chosen: OpenFOAM's
`dynamicCode::checkSecurity` **refuses `#calc` when running as root** (it compiles
and `dlopen`s a shared library), and this blastFoam install lives under `/root`.
The half-angle was verified as still exactly 5.000° after the substitution
(`atan(1.7431148549531634/19.92389396183491)`). blastlab's own writer emits
literal vertex numbers, which is why no blastlab case ever hits this.

| | |
|---|---|
| exit code | **0**, `End` marker reached |
| `FOAM FATAL` | **0** |
| SIGFPE | **none** — the one log hit is the startup banner `sigFpe : Enabling floating point exception trapping (FOAM_SIGFPE)`, i.e. **trapping was armed** |
| reached | **t = 19.5 ms**, 40 written time dirs, 829 s wall |
| field health at stop | `max(p) 171.9 kPa`, `min(p) 52.4 kPa`, `max(T) 1185 K` — no vacuum, no runaway |
| mesh | refined to 38,146 cells under AMR |

The run was stopped deliberately at 19.5 ms of its 25 ms target, via
`stopAt writeNow` on the `runTimeModifiable` controlDict, to free the serial
solver slot for R1.2. It was advancing ~0.6 ms per 3 min at that point.

**By the revised rule (§5a) this is a one-way test and it returned the null
branch**: no SIGFPE, therefore no confirmation. It is *not* a refutation of
Claim 3, because §5's Refutation 3 established the tutorial does not contain the
mechanism's trigger.

What it does establish, narrowly and worth stating: **the vendor's 5° wedge +
`adaptiveFvMesh` + `densityGradient` + `maxRefinement 4` configuration ran clean
through 19.5 ms with FPE trapping armed — 2.8–6.5× past the 3–7 ms window in
which all nine blastlab runs died.** So "axisym + AMR + densityGradient" is not
*by itself* sufficient to produce the crash.

### R3.1b / R3.2 / R3.3 — not run

See §9. The revised rules stand as written and are the right next experiments;
the serial-solver budget on this machine went to Claim 1, which was decidable
here and is the claim the prompt said had never been directly observed.

## 8. Claims 2 and 5

*(pending — see §9 for what ran)*

## 9. Verdict table

*(filled in after the runs)*
