> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [docs/SCOPE.md](../SCOPE.md)

# blastFoam solver options — the code against the official guide

Review date **2026-09-17**. Every dictionary blastlab generates, compared
line-by-line against the *blastFoam Theory and User Guide* v6.0 (Synthetik,
188 pp., text extracted and read in full), against the shipped tutorials, and
against the blastFoam C++ source itself.

**Sources reviewed**

- `BlastFoam_Basic_Info/BlastFoam_User_Guide.pdf` — the official guide.
- The code: `blastlab/solvers/foam/` (mainly `writer.py`, `dicts.py`,
  `materials.py`, `backend.py`) and `blastlab/core/` (`case.py`, `eos.py`,
  `profiles.py`, `constants.py`).
- **The vendor source, not only the guide**: `/root/blastfoam` in WSL —
  blastFoam 6.2.0 (commit `4e6ee07`), including tutorials and the built
  libraries.

> ### ⚠ Identifier warning — these IDs are local to this document
>
> This review numbers its own findings **B0–B2** and **N1–N4**. Those labels
> **collide with the global identifier index in [DONE.md](../../DONE.md)**,
> where `B1` and `B2` are entirely different bugs (a truncated `uniform`
> internalField `AttributeError`, and a kill-escalated stop crashing finalize —
> both closed under T1) and where `N5`, `N7`, `N11` etc. are the global
> feature/finding series.
>
> The labels are kept unchanged because `TODO.md` cites "B0" meaning *this*
> document's B0. **When citing them anywhere, write "solver review B0", never
> a bare "B0".**

---

## 1. Findings

| # | Finding | Severity | Verification |
|---|---|---|---|
| **B0** | A profile-fed chain stage **loses the entire fireball** — pressure is erased to `pRef` | 🔴🔴 **Blocking** | **Verified by a real blastFoam run** |
| **B1** | A profile-fed chain stage writes `0/p` wrong by **+33.3 %** in every products cell | 🔴 **Critical** (dormant behind B0) | **Verified numerically** on a real fixture |
| **B2** | Even after B1 — the JWL parameters selected are always TNT's (up to 20 % error for C4) | 🟠 High | Verified numerically |
| **N1** | `reconstructParAll` exists and solves exactly the limitation the code documents as unsolvable | 🟡 Medium | Verified (the binary is built) |
| **N2** | A ~6–15 % charge-mass deficit, handled today by expensive extra resolution (4.1× cells in 3D) | 🟡 Medium | Documented in code; a solution exists in the guide |
| **N3** | `adjustLocations yes` as the default — the guide specifies `no` | 🟢 Low | The code already documents the risk |
| **N4** | `libs ("libblastFunctionObject.so")` in the guide — **a guide error, not a code error** | ℹ️ Info | The code is right |

**B0 has since been fixed.** `TODO.md` records the measured effect of the fix on
the chain hand-off: `min(rho)` went from 1.711e-04 with 20 sub-floor cells to
7.360e-02 with **zero**.

---

## 2. The option surface the code generates today

| Area | What the code fixes | Where |
|---|---|---|
| Solver | `blastFoam` | `writer._controldict` |
| Phases | `(expl air)` — `detonating` + `basic` | `writer._phaseproperties` |
| Products EOS | `JWL` (6 materials) | `materials.MATERIALS` |
| Reactants EOS | `Murnaghan` (`K0 0`, `Gamma 0.25`) | `writer._phaseproperties` |
| Air EOS | `idealGas`, `gamma 1.4` | constant |
| Activation | `linear` \| `none` only | `case.activation` |
| Afterburn | `Miller` \| `none` only | `case.afterburn` |
| Flux scheme | `Kurganov` — **module constant, not selectable** | `dicts.FLUX_SCHEME` |
| Time integrator | `RK2SSP` (no stage count) — **fixed** | `writer._fvschemes` |
| AMR | `adaptiveFvMesh` + `densityGradient` \| `Lohner` | `writer._dynamicmeshdict` |
| Function objects | `impulse`, `fieldMinMax`, `blastProbes`, `writeCellCentres`, `surfaces`, `sets` | `writer._controldict` |
| Open-pressure BC | `pressureWaveTransmissive` (no `fieldInf`/`lInf`) | `dicts.P_OPEN_BC` |

---

## 3. B0 — the profile stage loses the fireball: `lambda.expl` is never written

**This is the root, and B1 sits underneath it.**

**The mechanism.** The `detonating` phase blends between the unreacted and
reacted states by the progress variable `λ` (guide §5.6.1, eq. 5.87):

```
x = λ^ℓ · x_reacted + (1 − λ^ℓ) · x_unreacted
```

In blastFoam the field `lambda.<phase>` is constructed `READ_IF_PRESENT` with a
default of **0** (`activationModel.C:236-249`). The code **never writes
`0/lambda.expl`** — verified: a grep across all of `blastlab/` finds `lambda`
only in `fvSchemes` (`writer.py:818, 836`), never as a field.

For an ordinary charge stage that is **correct** — the charge really has not
reacted at t = 0, and `linear` burns it from the detonation points. But for a
profile stage the code deliberately writes an empty `points ()` (`writer.py:937`;
the comment explains that otherwise the charge detonates a second time). And
`linearActivation.C:46` only lowers `tIgn` in a loop over detonation points; with
an empty list `tIgn = great` in every cell, so:

> **λ = 0 forever → the material is treated as unreacted solid with a Murnaghan
> EOS.**

And Murnaghan with `K0 0` (the vendor's own pattern) returns `p ≈ pRef`
**independently of density**.

**Verification — a real blastFoam 6.2.0 run on 10³ cells.** A minimal case built
from `freeField` reproducing exactly what a profile stage writes
(`alpha.c4 = 1`, `rho.c4 = 24.6`, `p = 4.43e6`, `points ()`), in four variants:

| variant | `activationModel` | `0/lambda.c4` | measured `max(p)` | |
|---|---|---|---|---|
| **A** | `linear` | not written | **101,298 Pa** | ← **what the code did** |
| **B** | `linear` | `uniform 1` | **4.43e+06** | ✔ correct |
| **C** | `none` | not written | **3.669e+07** | ✘ E0 counted twice (×8.3) |
| **D** | `none` | `uniform 1` | 4.43e+06 | ✔ correct |

Variant A shows the `0/p` the code writes is **discarded entirely** and replaced
by the Murnaghan `pRef` — 101,298 Pa, exactly the tutorial dict's `pRef`.

Variant C explains why `activationModel none` is **not** the fix: with no initial
λ, `dλ/dt` jumps 0 → 1 and blastFoam re-injects `E0`. Check:
`ΔE = E0·ρ/ρ0 = 9.0e9 × 24.6/1601 = 1.38e8 J/m³`, and
`Δp ≈ ω·ΔE = 0.25 × 1.38e8 = 3.46e7` — matching the measured difference
`3.669e7 − 4.43e6 = 3.23e7`.

**The consequence.** In a profile stage the **air** cells (`alpha.expl = 0`)
initialise correctly as ideal gas, so the shock front propagates fine. Only the
**products** cells collapse to ambient. A chain run therefore *looks* plausible —
there is an advancing shock — but the fireball is missing, which damages the long
positive phase, the secondary shock and the impulse.

**Hypothesis (not proven):** this may be the source of the pathology documented
at `writer.py:1140-1156` — a fireball pressure collapse against surrounding
shocked high-pressure air creates a violent inward flow, which is exactly the
"density runaway" signature that required the `RHO_MIN = 1e-3` floor. Worth
checking whether the workaround is still needed after the fix.

---

## 4. B1 — the chain hand-off writes pressure 33 % wrong in every products cell

> **Depends on B0.** This error was **dormant**: blastFoam discarded `0/p` in
> products cells without looking at it. Fixing B0 makes it live — so **both
> fixes had to land together.**

**The code**, `blastlab/solvers/foam/writer.py:1235`:

```python
p, _c = pressure_soundspeed(rho, e, phase, getattr(case, 'eos', 'idealGas'))
```

**The problem — the EOS is taken from the wrong object.** The function receives
the EOS of the **target case**, not of the **source profile**. And for a
blastFoam case, `case.eos` is forced to `'idealGas'`:

- `blastlab/ui/case_form.py:215` — `return v['eos'].get() if not foam else 'idealGas'`
- `blastlab/gui/forms.py:436` — the EOS row is marked `scope='native'`
- `blastlab/core/case.py:529-533` — validation stating explicitly that *"EOS
  setting is ignored by blastFoam (material JWL products + ideal-gas air)"*

So `core/eos.py:71-73` falls into the `else` branch and computes the pressure for
**products** cells with the air formula `p = (γ_air − 1)ρe = 0.4ρe`, instead of
`jwl_pressure` with `ω = 0.30`.

Meanwhile a blastFoam stage 1 exports its profile with `eos='JWL'`
(`backend.py:1117`) — because blastFoam really does run JWL. So **every
foam→foam chain hits this.**

**Verification — the code itself, run on the repo's own fixture**
(`blastlab/tests/_chain_study/gui_foam/stage1_profile.txt`, header `# eos = JWL`,
against a `stage2_case.json` carrying `"eos": "idealGas"`, `"solver": "blastfoam"`):

```
profile eos header : JWL   n = 100   product cells: 85

-- product cells only --
max |p_idealGas / p_blastFoam - 1| = 33.3 %
max |p_JWL      / p_blastFoam - 1| =  9.2 %   (remainder is the products/air contact only)

  rho=  24.6048 e=6.0016e+05 | blastFoam p=4.4300e+06  code writes=5.9067e+06 (+33.3%)
  rho=  24.9312 e=6.0250e+05 | blastFoam p=4.5063e+06  code writes=6.0084e+06 (+33.3%)
  rho=  24.8264 e=6.0194e+05 | blastFoam p=4.4832e+06  code writes=5.9776e+06 (+33.3%)
```

**Why this is especially bad.** Per guide §5.9, for a Mie-Grüneisen-form EOS —
which JWL is — *"by default the pressure and density are used to initialize the
internal energy"*. So blastFoam takes the wrong `0/p` and **inverts JWL** to
recover the energy:

```
energy blastFoam back-derives from the written p (JWL inversion):
  mean e_recovered / e_true = 1.3333   →  +33.3 % energy injected into the fireball
```

The ratio `0.4/0.30 = 1.333` is exactly `(γ_air − 1)/ω_TNT`. This is not an edge
case — it is a systematic injection of a third of the internal energy into all 85
products cells, precisely at the hand-off instant between stages.

**The fix.** `profile_state` already has `prof['eos']` (`load_profile` returns
it); it only needs passing through:

```python
# writer.profile_state — add to the returned dict:
return dict(..., eos=str(prof.get('eos', 'idealGas')))

# writer._profile_fields — use the SOURCE's EOS and the right material:
from ...core.eos import pressure_soundspeed, material_jwl
p, _c = pressure_soundspeed(rho, e, phase,
                            st.get('eos', 'idealGas'),
                            material_jwl(spec.material))
```

**A cleaner alternative, backed by the guide.** Guide §5.9: *"If the internal
energy field is provided in the initial conditions folder, the pressure and
temperature fields are calculated directly from the density and internal
energy."* So `0/e` could be written directly instead of `0/p` — which
**conserves energy exactly** and lets blastFoam derive the pressure with its own
JWL. That removes the whole EOS-matching problem at the root, B2 included.

> **Scope note:** when the source stage is a native run with `eos='idealGas'`,
> the profile's `e` really is consistent with ideal air and the current behaviour
> is correct-by-intent (it preserves pressure). The bug is specifically that the
> code selects by the *target's* EOS rather than the *source's*.

---

## 5. B2 — TNT's JWL parameters applied to every material

The signature at `core/eos.py:49`:

```python
def pressure_soundspeed(rho, e, phase, eos, jwl=JWL_TNT):
```

`writer._profile_fields` calls it with four arguments only — so `jwl` falls back
to the **TNT** default even when the charge is C4 or ANFO. `material_jwl(name)`
exists for exactly this purpose (`core/eos.py:36`) but is not passed.

Error magnitude on the same fixture:

```
C4   : max |p(TNT default) / p(C4)   - 1| = 20.0 %
ANFO : max |p(TNT default) / p(ANFO) - 1| = 14.3 %
RDX  : max |p(TNT default) / p(RDX)  - 1| =  0.0 %   (identical ω)
```

The error comes entirely from `ω` (TNT 0.30, C4 0.25, ANFO 0.35). It is dormant
today because B1 masks it — but fixing B1 alone, without passing
`material_jwl(spec.material)`, simply trades a 33 % error for a 20 % one.

---

## 6. N1 — `reconstructParAll` solves the parallel-AMR limitation

`writer.py:141-147` documents:

> *"Uniform parallel runs are reconstructed back to the root by the run loop; a
> parallel AMR run **cannot be** (the mesh changes under reconstructPar), so its
> times stay per-rank and the ingest concatenates them"*

Guide §16.9 describes a tool for exactly this:

> *"A modified version of the standard OpenFOAM `reconstructPar` and
> `reconstructParMesh` has been added to allow for reconstruction of cases that
> have been **balanced**, something that will cause a fatal error with
> `reconstructPar`. ... This also allows for **reconstruction of blastFoam AMR
> refinement histories** which is not typically supported."*

The binary was verified as built at
`/root/OpenFOAM/root-9/platforms/linux64GccDPInt32Opt/bin/reconstructParAll`.

**The fair qualification:** the existing workaround (`CaseSpec.decomposed` +
concatenating `processor*/`) works and is substantially cheaper than a full
reconstruct. So this is not a bug — it is an opportunity. The value: the entire
post-processing path (`blastToVTK`, ParaView, `foamToVTK`) would work directly on
parallel AMR, instead of through the special Python ingest. Note two caveats from
the guide: `-constant` is needed if the mesh in `processor*/constant` differs from
`constant`, and `-withZero` if the mesh in `0` differs.

---

## 7. N2 — the charge-mass deficit has a direct solution in `setRefinedFields`

`core/constants.py:50-58` documents:

> *"blastFoam's `sphericalMassToCell` sets alpha = 1 in the cells whose CENTRES
> fall inside r_exp, so the mass it actually deposits is the staircase volume:
> ~0.85 of the request at 5 cells across the radius... 8 cells brings it to ~0.94
> **for a 2.6x (2D) / 4.1x (3D) cell-count cost**."*

So the code pays 4.1× the cells in 3D to reduce the mass deficit from 15 % to
6 %, and the deficit is still there.

Guide §16.1 offers a field set type that solves it analytically —
`MassIntegrated`:

> *"**MassIntegrated**: The mass integrated quantity read and is divided by the
> mass (density times volume) of the given cell set to determine the field
> value."*

The guide's example (p. 131) is explicit:

```
// alpha.air = 10 [kg] / sum(V * rho.air) [kg]
volScalarFieldMassIntegrated alpha.air 10
```

**What it means:** instead of `volScalarFieldValue alpha.expl 1` (which pins
alpha = 1 and lets the staircase decide the mass),
`volScalarFieldMassIntegrated alpha.expl <mass_kg>` sets alpha so that
`sum(alpha·ρ·V)` over the cell set **equals the requested mass exactly**. It
compensates for the staircase over/under-shoot by definition.

```python
# writer._setfieldsdict — instead of:
'fieldValues': [Raw(f'volScalarFieldValue {alpha}    1')],
# use:
'fieldValues': [Raw(f'volScalarFieldMassIntegrated {alpha}    {fmt(mass)}')],
```

If this verifies, `FOAM_EXP_CELLS` could go back from 8 to 5 and save 4.1× the
cells in 3D — with **more accurate** mass than today. Validate against
`test_foam_kb_anchor` before switching: the afterburn calibration (`Q0=2.0e6`,
`a=3e-4`) was done with the current deficit baked in and would need refitting.

---

## 8. N3 — `adjustLocations` and `refineProbes`

Guide §15.1 specifies `adjustLocations` — *"Can probes be moved into the mesh
(**default no**)"*. The code sets `'yes'` (`writer.py:110, 799`), and the code
comment already identifies the risk: on a coarse base mesh the probe snaps to a
distant cell centre, and under AMR the cell refines beneath it.

Two things worth knowing:

1. It **matches the tutorials** (`axisymmetricCharge` and `building3DWorkshop`
   both write `adjustLocations yes`), so it is a reasonable decision.
2. Guide §15.1 adds that the AMR jump is already handled: *"This can be
   eliminated by allowing refinement of probes in `dynamicMeshDict`
   (`refineProbes`) (**this is the default option**)."* — verified at
   `errorEstimator.C:139`:
   `refineProbes_(dict.lookupOrDefault("refineProbes", true))`. The code already
   gets the right behaviour from the default; **no action needed.**

> **See also:** the independent audit later found that `adjustLocations` is a
> **no-op for every interior probe** regardless of this setting, which makes
> several blastlab comments wrong. See
> [blastfoam-claims.md §6](blastfoam-claims.md).

---

## 9. N4 — two errors in the guide itself (the code is right)

1. **The library name.** Guide §15 (p. 122) writes
   `libs ("libblastFunctionObject.so")` — singular. The actually-built library is
   `libblastFunctionObjects.so` — **plural**. The code (`writer.py:700, 707`)
   uses the correct form.
2. **`MillerCoeffs`.** The guide (p. 70) shows the Miller parameters in a
   `MillerCoeffs { ... }` sub-dictionary, while the code writes them flat inside
   the phase dict. Checking `newAfterburnModel.C`:
   ```cpp
   const dictionary& modelDict = dict.optionalSubDict(afterburnModelType + "Coeffs");
   ```
   `optionalSubDict` returns the sub-dict if present and otherwise the dict
   itself — **both forms are valid.** The code comment in `materials.py` is right.

---

## 10. What was checked and found correct

Compared line-by-line against `tutorials/blastFoam/freeField` and against the C++
that reads each key:

| Item | Finding |
|---|---|
| `fvSchemes` (fluxScheme, ddt, grad, div, laplacian, interpolation, snGrad) | **Identical to the tutorial**, `reconstruct(...)` included |
| `fvSolution` | **Identical to the tutorial** (`"(rho\|rhoU\|rhoE\|alpha\|.*)"` → `diagonal`) |
| Basic `controlDict` | Matches; `timePrecision 8` instead of 12 — a deliberate choice documented in `dicts.tfmt` |
| `phaseProperties` structure | Matches exactly (reactants/products/activationModel/initiation/residual*) |
| `E0 = rho0 · e0` | ✔ Verified against `freeField`: C4 → 1601 × 5.56e6 = 8.90e9 ≈ `E0 9.0e9` |
| `Murnaghan` with `K0 0` | ✔ **This is the vendor pattern** (`freeField`, `mappedBuilding3D`, `blastFSIFoam/flap`). `Murnaghan.C` handles it: `kappa_ = 1/max(K0_, small)`, and `n` falls back to `K0Prime` default `1+small` — precisely to avoid division by zero |
| `activationModel none` + `initiation { E0 }` only | ✔ Matches `burstingWindow_workshop` |
| `blastProbes` (no `libs`, `adjustLocations`, `append`) | ✔ Matches `axisymmetricCharge` and `building3DWorkshop` |
| `pMax` as the `fieldMinMax` output field name | ✔ Verified at `fieldMinMax.C:92` — `minMaxName_ = "Max"`, `computedName()` = `"p"+"Max"` |
| `maxCells` in `dynamicMeshDict` | ✔ Actually read (`fvMeshRefiner.C:517`) — **although it does not appear in the guide's §11 table** |
| `nBufferLayers` (not `nBufferLayer`) | ✔ `fvMeshRefiner.C:532` reads `nBufferLayers` |
| `field` for Lohner (the guide shows `deltaField`) | ✔ `Lohner.C:55` — `lookupBackwardsCompatible({"deltaField", "field"})` |
| `maxRefinement` at the top level of `setFieldsDict` | ✔ `setRefinedFields.C:858`; zones without `level` inherit it (`:877`) |
| `loadBalance { balance }` as a sub-dict | ✔ Matches the §11.3 example |
| `addEmptyPatch internal internal` before `decomposePar` | ✔ Actually required (`fvMeshBalance.C:112`), matches §11.2 |
| `pressureWaveTransmissive` + `value $internalField` | ✔ Matches `axisymmetricCharge`/`delayedDetonation`/`twoChargeDetonation` |
| `T_AMB` consistency | ✔ 101325/(1.225·0.4·718) = 288.0 K; and `(γ−1)Cv = 287.2` matches `8314/28.97 = 287.0` |
| JWL parameters (TNT, C4) | ✔ TNT matches Dobratz; C4 matches `freeField` **exactly** |

> **A second-order note on the material table.** `RDX` and `HMX` in
> `materials.py` share almost identical `A`/`B` (7.78e11/7.07e9 against
> 7.783e11/7.071e9) while `e0` differs materially (5.15 vs 5.50 MJ/kg). This
> comes from `jwl_parameters.md`, not from any tutorial. **Worth verifying
> against Dobratz before quoting RDX results** — common `e0` values for RDX at
> ρ = 1.77 run higher, ~5.9 MJ/kg.

---

## 11. Recommended features from the guide

Ranked by value/effort.

### 11.1 High value, low effort

**(a) `timeOfArrival` — an arrival-time map (§15.12)**

```
timeOfArrival { type timeOfArrival; libs ("libblastFunctionObjects.so");
                writeControl writeTime; pName p; }
```

Shock arrival time is one of the three standard outputs in blast engineering
(alongside peak pressure and impulse), and the repo already produces the other
two (`pMax`, `impulse`). One dict line and one extra field per time directory —
it completes the set.

**(b) `overpressure` with `store yes` (§15.10)**

```
overpressure { type overpressure; writeControl writeTime; pRef 101325; store yes; }
```

Two gains: (1) `blastProbes` can sample `overpressure` directly instead of `p`,
so `gauge_summary` gets the right quantity at the source; (2) guide §16.5 notes
`calculateImpulse` detects an overpressure file automatically and then zeroes
`pRef`. The tutorials (`burstingWindow_workshop`) already do
`fields (overpressure impulse)` in probes.

**(c) `conservedQuantities` — automatic sanity control (§15.4)**

```
conserved { type conservedQuantities; fields (rho rhoE); }
```

Prints total mass and energy to the log — initial, current, absolute and relative
difference. Given that B1 is **exactly** an energy non-conservation at the stage
hand-off, this FO would have caught it automatically on every chain run. Worth
wiring the output into `postmortem.py` as an automatic per-run check.

**(d) `writeTimeList` — write at an exact time (§15.3)**

```
writeTimes { type writeTimeList; times (1.234e-4); }
```

Today the chain hand-off point is snapped to `tfmt` and relies on
`adjustableRunTime`, which will miss it. This FO guarantees a write at exactly
the requested time — solving a whole class of `startFrom latestTime` problems
directly.

**(e) `fieldInf`/`lInf` on the open boundary (`pressureWaveTransmissive`)**

```
type pressureWaveTransmissive; value $internalField;
fieldInf 101325; lInf <domain size>;
```

Verified at `pressureWaveTransmissiveFvPatchField.C:134` that the fields are
optional and activate when `lInf > small`. Without them the BC is purely
advective and does not relax back to ambient — a source of slow drift and weak
reflections at the boundary, exactly what impulse measurements are sensitive to.
The tutorials do not use it, so check the effect on the KB anchor before enabling.

### 11.2 High value, medium effort

**(f) `rotateFields` — replace the Python remap (§16.7)**

This is the most significant recommendation. The repo currently implements
1D→2D/3D mapping in Python (`profiles.remap_profile_1d_to_3d`) with the pathology
documented at `writer.py:1140-1156`: interpolating **conserved** quantities
produces cells with `rho ~ 1.6e-6` carrying `|U|` up to 3.6e4 m/s and `T` up to
8.3e6 K, which caused SIGFPE in **~6 % of chain runs**. The current mitigation is
the `RHO_MIN = 1e-3` density floor.

Guide §16.7 describes a vendor tool for precisely this purpose:

> *"The `rotateFields` utility can be used to map the fields of a 1-D or 2-D
> solution to that of a 2-D or 3-D solution... The rotation of vector and tensor
> fields are mapped **using the local rotation tensor** to ensure that the
> correct radial components are used. **Iterative refinement** can be used to
> iteratively rotate fields and refine the mesh using the refinement criteria
> found in `dynamicMeshDict`, allowing for easier initialization when using AMR."*

Advantages: (1) it operates on **fields** rather than interpolated conserved
quantities — removing the source of the pathology; (2) vector rotation is
mathematically correct; (3) `-refine` lifts the restriction the code enforces
today (`case.py:521-525` — "A profile-initialised blastFoam stage cannot use
refinement zones yet"); (4) it **eliminates B1 entirely** — no Python EOS
conversion in the middle.

**The fair qualification:** the guide warns *"The mapping is not conservative
currently so only the nearest cell value will be used"* — it preserves local
state but not global integrals. So this needs validation against the existing
baselines, not a blind swap. The `-extend` and `-maxR` flags matter at the edges.

**(g) `errorEstimator multicomponent` for AMR (§11.1.7)**

Today a single estimator is chosen. Blast refinement is driven simultaneously by
the shock front (pressure gradient) **and** the products/air interface (`alpha`).
The guide (p. 111) gives the exact pattern:

```
errorEstimator multicomponent;
errorEstimators
(
    density  { errorEstimator densityGradient; lowerRefineLevel 0.01; unrefineLevel 0.01; maxRefinement 2; }
    pressure { errorEstimator scaledDelta; deltaField p; minValue 1e3;
               lowerRefineLevel 0.1; unrefineLevel 0.01; maxRefinement 2; }
);
```

Note each estimator carries its own `maxRefinement` — so the interface can be
refined less than the front, saving cells.

**(h) `beginUnrefine` — the guide recommends it explicitly for explosives (§11)**

> *"Because the detonation of explosives may not occur when the simulation
> starts, the option to begin unrefinement at a designated time
> (`beginUnrefine`) has been added. This allows the mesh to remain refined in
> specific regions even though the error is initially small."*

This is exactly the scenario the code handles today with a Python-side workaround
(`backup_radius` in `_setfieldsdict`, which inflates the refinement zone to
`0.9 · dx_base` to "catch" the cell containing the centre under AMR).
`beginUnrefine` is the solution the vendor intended. Other unused keys in the
same family: `beginRefine`, `endRefine`, `unrefineInterval`, `upperRefineLevel`,
`upperUnrefineLevel`, `minDx`, `protectedPatches`, `nUnrefinementBufferLayers`.

**(i) Full `loadBalance` (§11.3)**

The code writes only `loadBalance { balance yes; }`. The guide adds
`balanceInterval` (how many refine steps between balances), `allowableImbalance`
(0.2), and `method scotch`. A comment in `backend.py` documents a measured 1:64
imbalance between a loaded and an idle rank — `allowableImbalance` is precisely
the knob for that.

### 11.3 Model extensions (research value)

**(j) `DoanNickel` EOS for air (§5.2.2.10)**

The code fixes `gamma 1.4` for air. The guide: *"The Doan-Nickel EOS includes
changes in the composition of air at high temperatures and the changing specific
heat ratio due to **dissociation of molecules**."* In the near field, shock
temperatures cross the O₂ and N₂ dissociation thresholds, and a constant γ
overestimates pressure there. This bears directly on the Kingery-Bulmash anchor
at small `Z`. All coefficients are hard-coded (they are air-specific), so it is a
one-word change:

```
equationOfState DoanNickel;
```

Limitation from the guide: *"can currently only be used with inviscid fluids and
a constant specific heat at constant volume (eConst)"* — both already hold in the
code (`mu 0`, `eConst`).

**(k) Additional activation models (§5.6.1)**

The code supports `linear`/`none` only. Also available:

- **`programmedIgnition`** (§5.6.1.3) — the Giroux model, with `burnModel` of
  `beta`/`programmed`/`programmedBeta`. Includes compression-dependent energy
  release, and a `λ` that advances at the local `vDet/(1.5·dx)` instead of a
  sharp step. **Clearly preferable to `linear` in the near field**, since
  `linear` activates a cell in full the moment `|x − x_det| < v_det·t`.
- **`pressureBased`** (§5.6.1.4) — the full Lee-Tarver ignition-and-growth model,
  for shock-to-detonation scenarios.
- **`ArrheniusRate`** (§5.6.1.5) — but the guide explicitly marks it *"still in
  development and has not been validated"*, so not recommended.

**(l) `initiation`: `delays`, `radii`, `useCOM` (§5.6.1)**

The code writes only `points` + `vDet`. The guide adds:

- **`delays`** — a per-point delay. There is a dedicated tutorial
  (`delayedDetonation`). This enables multi-stage and multi-point timing, and the
  code **already supports** a `det_points` list, so it is a natural extension.
- **`radii`** / `radius` — an activation radius around each point. Today *"If no
  radii are provided, **only the cell containing the point** will be
  activated"* — i.e. activation is resolution-dependent.
- **`useCOM`** — activation from the charge's centre of mass (used in
  `building3D`, `building3DWorkshop`).
- **`lambdaPow`** — the blending exponent between unreacted and reacted states.

> `radii` was subsequently adopted as the default and is now the principal
> mitigation for the parallel ignition-seed defect. See
> [blastfoam-claims.md §3](blastfoam-claims.md).

**(m) Simple afterburn models (§5.6.2.2–3)**

`materials.py` documents honestly that Miller was calibrated for TNT only and
that the other materials are *"physically ordered estimates"*. For cases wanting
a **deterministic** energy addition without calibration:

- **`constant`** — `Qdot` [J/kg/s].
- **`linear`** — `Q0`, `tStart`, `tEnd`; releases `Q0/Δt` over a given window.

Both allow isolating the energy effect from the model-kinetics effect. Miller
itself also has unused keys: `pScale`, `pUnits`, `tUnits` (verified at
`MillerAfterburn.C:96-103` — they give automatic unit conversion, useful when
citing coefficients from literature working in MPa/μs).

**(n) Schlieren / shadowgraph for animations (§15.6–15.7)**

```
schlieren   { type grad;      field rho; }
shadowgraph { type laplacian; field rho; }
```

The repo already produces animations and images (`output/animation.py`).
Schlieren is the standard visualisation for shock waves and makes weak structures
(contact surfaces, secondary reflections) visible — one extra field per time
directory.

### 11.4 Capabilities not touched at all

| Capability | Section | Relevance |
|---|---|---|
| `mergeProbes` | §16.4 | Merging probe files from interrupted runs — directly relevant to the resume path |
| `calculateImpulse` | §16.5 | Impulse from a probe file — what `gauge_summary.py` does in Python |
| `blastToVTK` | §16.2 | Patch-only VTK + `.vtk.series` — far lighter than full VTK for the 3D viewer |
| `initializeAtmosphere` | §16.6 | Hydrostatic/tabulated atmosphere — for long ranges and altitude |
| Burst patches | §7 | Bursting windows and panels (`pressure`, `impulse`, `pressureAndImpulse`, `field`) |
| Other flux schemes | §10.1 | `HLLC` is sharper at contact surfaces (the products/air interface) than `Kurganov` |
| `RK3SSP` / stage count | §10.3 | `timeIntegrator RK2SSP 3` — three stages for extra stability |
| `limitT no` | §5.1 | Disables temperature limiting (the guide warns: "Caution should be used") |
| `blastEulerFoam` | §19.2 | Cased or dust-laden sources |
| `blastFSIFoam` | §19.3 | Structural deformation under load |

---

## 12. Proposed order of work

| Priority | Action | Effort |
|---|---|---|
| **P0** | Fix **B0 + B1 + B2 in one commit** — see §13 | Small |
| **P0** | Regression test: a profile with `eos=JWL` → verify `0/p` matches the profile's stored `p` column, **and** that `0/lambda.expl` exists | Small |
| **P1** | `conservedQuantities` on every run + a check in `postmortem` — would have caught B1 | Small |
| **P1** | `timeOfArrival` + `overpressure store yes` | Small |
| **P2** | Proof of concept for `volScalarFieldMassIntegrated` (N2), measured against the KB anchor; if it works, drop `FOAM_EXP_CELLS` to 5 | Medium |
| **P2** | `beginUnrefine` + `allowableImbalance` in `dynamicMeshDict` | Small |
| **P3** | Proof of concept for `rotateFields` as a replacement for the Python remap | Large |
| **P3** | Expose `activation programmedIgnition` and `initiation delays` | Medium |
| **P4** | `reconstructParAll` for the parallel AMR path | Medium |

---

## 13. The recommended fix for B0 + B1 + B2

All three touch the same function and **must land together**: fixing B0 alone
turns the 33 % error from dormant to live, and fixing B1 alone does nothing
because the value is discarded either way.

### Step 1 — write `0/lambda.expl` (the root of B0)

In `writer._profile_fields`, add a seventh entry to the `fields` dict:

```python
fields = {
    '0/p':   ('p', 'p', _nonuniform(_cell_order(p, spec)), False),
    '0/T':   ('T', 'T', _nonuniform(_cell_order(T, spec)), False),
    '0/U':   ('U', 'U', _nonuniform(U, vector=True), True),
    f'0/alpha.{PHASE}':  (...),
    f'0/rho.{PHASE}':    (...),
    '0/rho.air':         (...),
    # B0: the profile's explosive is ALREADY reacted - it arrives as
    # expanded JWL products from the previous stage. Without this field
    # blastFoam defaults lambda to 0 (activationModel.C READ_IF_PRESENT),
    # blends the phase back to the UNREACTED Murnaghan reactants, and
    # that EOS returns pRef regardless of density - the whole fireball
    # is silently reset to ambient. Measured: 4.43 MPa -> 101,298 Pa.
    f'0/lambda.{PHASE}': (f'lambda.{PHASE}', 'alpha',
                          Raw(f'uniform 1'), False),
}
```

Implementation notes:

- **The field key `'alpha'`** is deliberate: `_DIMS['alpha']` is
  `[0 0 0 0 0 0 0]` (λ is dimensionless), and `_bc_entry(fld='alpha', ...)` gives
  `zeroGradient` on open boundaries and walls and the correct `wedge`/`empty`.
  No new BC code is needed.
- **`uniform 1`, not the phase mask**: in a profile stage there is no unreacted
  material anywhere in the domain, and in air cells `alpha.expl = 0` so λ is
  meaningless there. The phase mask
  (`_nonuniform(_cell_order(phase.astype(float), spec))`) is also valid — merely
  more verbose without benefit.
- **Keep `activationModel linear` with `points ()`.** Do not switch to `none`:
  variant C in the §3 table shows it re-injects `E0` and multiplies pressure by
  8.3. With an initial λ = 1, `linearActivation` is a no-op
  (`lambda_.ref() = max(..., lambda_())` is monotone, and `tIgn = great`).
- Add `0/lambda.expl` to `spec.deferred` — it is nonuniform-over-final-cells
  exactly like the other profile fields and so must be written after the mesh
  stages. This happens automatically because `render_case` does
  `spec.deferred = tuple(prof)`.

### Step 2 — fix the EOS selection (B1 + B2)

`profile_state` already holds `prof['eos']`; it only needs passing through:

```python
# writer.profile_state - add to the returned dict:
return dict(..., eos=str(prof.get('eos', 'idealGas')))

# writer._profile_fields - use the SOURCE's EOS and the right material:
from ...core.eos import pressure_soundspeed, material_jwl
p, _c = pressure_soundspeed(rho, e, phase,
                            st.get('eos', 'idealGas'),
                            material_jwl(spec.material))
```

Two bugs fixed in two lines: the EOS comes from the **profile** rather than the
target case (B1), and the JWL parameters are the actual material's rather than
the TNT default (B2).

### Step 3 — tests that prevent regression

1. **Golden test** on `_profile_fields`: verify `0/lambda.expl` exists, and that
   for a fixture with `# eos = JWL` the `0/p` values match the profile's `p`
   column (deviation < 1 %). This is a pure text check, no WSL — it belongs in
   `test_foam_writer.py`.
2. **`conservedQuantities`** on every run (§11.1c): prints total mass and energy
   against the initial values. Both bugs are energy non-conservation at the
   hand-off, and this FO would have caught both.
3. **Validation in `case.py`**: if `init_mode != 'charge'` and no
   `lambda.<phase>` is written — raise, do not run.

### What to do with existing results

Every saved foam→foam chain result ran with variant A. The shock front there is
reasonable because it is carried in air cells, but **everything depending on the
fireball — impulse, positive-phase duration, secondary shock, late behaviour — is
invalid.** Mark them as such and re-run one reference point after the fix.

---

## Appendix — how this was verified

1. **Guide extraction**: `pypdf` → 188 pages → `manual.txt` (205 KB). Read in
   full: §5 (thermo/EOS/detonating/activation/afterburn), §6–9, §10 (flux and
   time integration), §11 (AMR), §12, §15 (function objects), §16 (utilities),
   §17–19.
2. **The code**: `writer.py` (1378 lines, in full), `dicts.py`, `materials.py`,
   `constants.py`, `eos.py`, `profiles.py` (remap), `case.py` (validation),
   `backend.py` (mesh stages, profile export).
3. **The blastFoam source in WSL** (`/root/blastfoam`, 6.2.0 / `4e6ee07`) —
   verified directly in the C++: `newAfterburnModel.C` (`optionalSubDict`),
   `MillerAfterburn.C` (keys + `pUnits`/`tUnits`), `Murnaghan.C` (`K0 0`
   handling), `fvMeshRefiner.C` (`maxCells`, `nBufferLayers`, `begin*`/`end*`),
   `errorEstimator.C` (`refineProbes`, `lowerRefineLevel`), `Lohner.C`
   (`deltaField`/`field`), `fieldMinMax.C` + `fieldMinMaxTemplates.C` (output
   field name), `setRefinedFields.C` (`maxRefinement` vs `level`),
   `pressureWaveTransmissiveFvPatchField.C` (`fieldInf`/`lInf`).
4. **Tutorials** — `freeField` (phaseProperties + all system dicts),
   `axisymmetricCharge`, `twoChargeDetonation`, `building3DWorkshop`,
   `burstingWindow_workshop`, `delayedDetonation`, `mappedBuilding3D`.
5. **Built binaries** — verified that `reconstructParAll`, `rotateFields`,
   `blastToVTK`, `createTimeSeries`, `mergeProbes`, `calculateImpulse`,
   `initializeAtmosphere` and `blastEquation` all exist, and that
   `libblastFunctionObjects.so` is the correct name.
6. **Numerical verification of B1/B2** — ran `blastlab.core.eos.pressure_soundspeed`
   and `material_jwl` on
   `blastlab/tests/_chain_study/gui_foam/stage1_profile.txt` (100 points, 85 of
   them products) and compared against the `p` column blastFoam itself wrote.
7. **Verification of B0** — in two stages:
   - *Code level*: `writer.render_case` on the real
     `_chain_study/gui_foam/stage2_case.json` → confirmed an empty `points ();`
     and zero `lambda` fields in the written file list.
   - *Run level*: **a real blastFoam 6.2.0 run** on a 10³-cell case derived from
     `freeField`, in four variants (`activationModel` × `0/lambda`), as tabulated
     in §3. That is what turned the finding from a hypothesis into a measured
     fact.
