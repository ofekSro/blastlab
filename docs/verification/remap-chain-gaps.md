# Remap-chain gaps — the map (2026-10-11)

A read-only survey of how a solution is planted from one stage into the next:
1D→2D, 2D→3D, 1D→3D, and the missing 3D→3D. Tree `976f72c` (`master`). No solve
was run; every claim below is from the code, `TODO.md`, `DONE.md` and
[physics-anchors.md](physics-anchors.md), with the evidence named.

The items have stable ids in `TODO.md` (one line each there; the detail is here).
Owner decisions of 2026-10-11: record them in the existing P1-P4 numbering by
severity; include the hemispherical option and several charges through 1D;
**expand `P3-14` (3D→3D) and raise it to P1**.

| Route | State | The worst gap |
|---|---|---|
| 1D→2D | works, both solvers | the only route with an accuracy test, and it checks peak and arrival only |
| 2D→3D | works | obstacles dropped; blastFoam takes the burst height from the 3D form |
| 1D→3D | works, Qt only | no blastFoam accuracy test |
| 3D→3D | **does not exist** | no format, no remap, and the chain allows one stage per dimension |

---

## 1. Already tracked before this survey

| Id | What | Note |
|---|---|---|
| `P3-14` | No 3D remap format | **Expanded and raised to P1 here** (§3) |
| `P3-15` | Obstacles do not survive 2D→3D | Still a stdout print only (`core/profiles.py:204-206`) |
| `P3-12` | No static refinement zones on a profile stage | `services/validation.py:173-177` |
| `P3-10` | "0 kg TNT" in a chained 3D init line | Cosmetic half of `P2-26` |
| `N5-11` | `RHO_MIN` floor in `writer.profile_state` | One settling run designed, not run |
| `P3-16` | `conservedQuantities` on every run | Not a source-vs-target remap check (`P2-30`) |
| `P3-20` | `rotateFields` instead of the Python remap | Also the natural foam→foam route for 3D→3D |
| RESUME 2 | `_e2e_ui_chain_foam.py` (1→2→3 on blastFoam) not completed | Office machine |

## 2. Decided — not gaps

- **native → blastFoam is refused** (`services/chain.py:29-47`, N5-4 in `DONE.md`): the
  native hand-off is an ideal-gas state and blastFoam would re-derive +33 % energy in the
  product cells. A mixed chain runs blastFoam → native only.
- **1D feeds axisymmetric 2D only; only axisymmetric 2D feeds 3D.** Geometry: a planar 2D
  field is an infinite cylinder.
- **A profile stage starts on the AMR base mesh** (T70); the banner warns above 2× the
  source cell.
- **Tk has no 1D→3D route** ("Stages must be consecutive", `gui/chain_panel.py:233-235`):
  the GUI redesign is Qt only and Tk stays as it is. Not recorded as a task (owner,
  2026-10-11).

---

## 3. P1 — silent wrong numbers, and the raised 3D→3D

### `P1-20` · Gauges inside the hand-off radius

**What.** A later stage's gauge histories start at the hand-off time `t0`. A gauge closer
to the burst than the shock radius at hand-off has already seen the incident peak in the
stage before, so its peak, positive impulse and arrival in this stage are not the
event's. Nothing says so: no validation note, no run-banner line, no mark in Results
(searched: no gauge-vs-hand-off-radius check anywhere outside `tests/`). There is also no
stitched pressure history across stages.

**Evidence.** The shock radius at hand-off is already computed at run start by the native
solvers (`solvers/solver2d.py:204-205`, `solvers/solver3d.py:240-256`) and is known before
the run when the 1D stage ends at a terminating Outer with no End time
(`ui/chain_route.py:286-289`).

**Why it matters.** The wall gauge is the design output. A wall inside the hand-off
radius reads low with no warning.

**Before fixing.** One shared shock-radius function (see `P2-27`). Then: a warning per
gauge (`G<n>`) at validation when the radius is known, otherwise in the run banner; the
Results row marked. Option for the stitched history: add each later-stage gauge as a
probe to the stage before (a 3D gauge maps to (r, z) in 2D, a 2D or 3D one to a radius
in 1D) and join the two records at `t0`.

### `P1-21` · 2D→3D: the two solvers disagree on the burst height

**What.** The 2D→3D remap maps the 2D `z` straight onto the 3D `z`, so the burst height
*is* the 2D stage's.
- native: `z0 = profile2d['y0']`, and a burst at or above `Lz` raises
  (`solvers/solver3d.py:136-142`);
- blastFoam: `spec.center` is the 3D form's `(x0, y0, z0)` (`solvers/foam/writer.py:522`);
  `burst_points` returns it for a profile stage (`writer.py:165-170`) and the timing uses
  it per open side (`writer.py:568-572`). Nothing refuses `y0 >= Lz`.

`wire()` does not copy the 2D burst height into the 3D case (`ui/chain_route.py:142-143`).
The Qt chain warns on `burst >= Lz` only (`chain_route.py:225-254`, GUI-12 B1 — an owner
decision for a *warning*).

**Before fixing.** List every consumer of `spec.center` / `burst_points` on a 3D profile
stage (timing, snapshot radii, banner, anything else) and what each one reads wrong
today. Owner call: blastFoam refuses like native, or both warn like the GUI.

### `P1-22` · Afterburn across a hand-off

**What.** With `afterburn = miller`, blastFoam transports a burn fraction `c.expl`
(`writer.py:1292-1323`). No hand-off format carries it (TSV columns
`r rho u e p phase`; the npz keys in `core/profiles.py:208-216`), a profile stage writes
no `0/c.expl` (`writer.py:2191-2219`), and nothing checks that the stages agree on
afterburn.

**Open, verify first.** What `c` blastFoam 6.2.0's Miller model starts from when the file
is absent (`/root/blastfoam`, the afterburn model source). If it is 0 and afterburn is on
in both stages, the products that already burned burn again — energy counted twice. On in
stage 1 only: afterburn stops at the seam. Native after blastFoam: same, the native solver
has no afterburn. The Miller calibration (CLAUDE.md §7) was fitted on single-stage runs.

**Before fixing.** Carry `c` in the hand-off (absent = unknown, as with the solver stamp),
write it into `0/`, and refuse or warn on mismatched afterburn across stages. Judge it with
a pre-registered chain-vs-direct run with afterburn on: peak, impulse, arrival.

### `P3-14` · 3D→3D — expanded, raised to P1 (owner 2026-10-11)

Missing at every layer:
1. **Format.** No save/load for a 3D field; `core/profiles.py` has 1D (TSV) and 2D (npz).
2. **Remap.** No 3D→3D kernel and no `init_mode 'profile3d'` (`models/case.py:440`,
   `writer.profile_state` at `writer.py:1874`, `solvers/solver3d.py:629-642`).
3. **Stage output.** A 3D stage writes no hand-off (`solvers/jobs.py:192-196`); neither
   solver builds a 3D final state (foam: "3D is terminate-only", `backend.py:2293`,
   `:2381`); validation refuses a `remap` trigger in 3D (`validation.py:879-882`).
4. **The chain is keyed by dimension.** `wire()` takes `{dim: case}`
   (`ui/chain_route.py:102`), `handoff_paths` names files `<a>d_to_<b>d`
   (`services/model_folder.py:353-363`), stage folders are `1d/2d/3d`, `ROUTES` has four
   fixed routes (`chain_route.py:37-40`), `stage_errors` and Results tabs are per dim. Two
   3D stages cannot coexist without changing this.
5. **GUI, validation, tests** for all of the above.

**Owner questions before planning.** What 3D→3D is for: a fine near-field box handed to a
larger coarse box; the same box continued on a coarser mesh; or a box moved along with
the front. Whether obstacles carry over (unlike 2D→3D they can). Size: ~7 fields × 8 B per
cell, ≈ 0.5 GB per 10 M cells before compression. foam→foam could use OpenFOAM's own
mapping (`mapFields` / `P3-20`'s `rotateFields`) — the guide warns it is not
conservative.

---

## 4. P2 — misleading output and missing coverage

### `P2-26` · Charge mass and Z are lost after the first stage

- `ui/scaled_distance.py:118` hides Z for every profile stage.
- A blastFoam 2D stage fed by a profile records `charge=case.charge` — whatever the form
  last held — and `from_profile=False` (`solvers/foam/backend.py:1690-1692`);
  `save_profile_2d` then writes that stale value as the 3D stage's `charge_kg`.
- Native records `None` → `0.0` (`core/profiles.py:213`), hence `P3-10`'s "0 kg TNT".

**Direction.** Take W (and the material) from the hand-off file, never the form, at
every seam; show Z on profile stages from the carried W. Mind `P1-9` (the field is the
material's mass, not TNT).

### `P2-27` · blastFoam says nothing when the hand-off already touches a boundary, the ground or an obstacle

- Native warns at run time (`solvers/solver2d.py:202-213`, `solvers/solver3d.py:237-259`,
  obstacles `:302-310`); the blastFoam path has no such line.
- `writer.py:1777-1778` says "validate_case warns when the shock already reaches a
  boundary". It does not — fix the comment or make it true.
- The Qt pre-run check covers only a 1D stage ending at Outer with no End time
  (`chain_route.py:286-289`), and for 2D→3D only the burst height.
- The 1D stage's radius is not derived from the next stage's geometry; the user has to
  match them by hand.

**Direction.** One shared function for the shock radius at hand-off and what it reaches,
used by both solvers, the foam banner, `validate_case` (when the file exists) and the
chain checks. Also feeds `P1-20`.

### `P2-28` · Accuracy coverage of the chain

What exists:
- `_e2e_foam_chain.py` (1D→2D on blastFoam vs a direct run): peak ±10 %, arrival ±5 %,
  **no impulse** — against CLAUDE.md §6 ("never measure peak alone").
- Native 2D→3D remap peaks 7.6-9.4 % ([physics-anchors.md](physics-anchors.md) §3), peaks
  only.
- The foam→foam reference chain (physics-anchors.md §5): one run, hand-off energy
  −0.02 % / +0.0001 %, but its 3D stage stopped on numerical instability (25 kg in
  1 × 1 × 0.6 m); "a fully clean reference run needs a less confined 3D case".

What is missing: a blastFoam chain-vs-direct comparison for 2D→3D and 1D→3D; impulse in
every chain comparison; a `test_foam_writer` golden for `profile2d` (only `profile1d` is
pinned). Thresholds registered before the runs that are judged by them.

### `P2-29` · 2D→3D: ambient air in the 3D layer nearest the ground (latent)

`remap_profile_2d_to_3d` marks as outside — ambient air, at rest — every 3D cell with
`z < z_c[0]` of the 2D grid (`core/profiles.py:274-275`). When the 3D cells near the
ground are finer than the 2D ones, the first 3D layer is wiped — where the Mach stem is.
Not triggered by any known case; shared by both solvers. The same test at `r > r_c[-1]`
and `z > z_c[-1]` costs half a cell at the far edges.

**Direction.** Outside = beyond the 2D domain's faces, not its first/last centres; hold
the edge value inside. A unit test with `dz_3D = dz_2D / 2`. Check whether any baseline
moves.

### `P2-30` · Hand-off fidelity — measure before changing anything

1. **The contact surface is sharpened.** blastFoam's export cuts at `alpha > 0.5`
   (`backend.py:1634`, and the 1D `read_final`); a mixed cell gets `e = Cv(phase) T`; the
   next stage recomputes `p` from the EOS (`writer.py:2176`) instead of using the source
   `p`. Pressure is not continuous across the interface after the seam.
2. **Conservation is not checked source-vs-target.** The remap interpolates at cell
   centres. N5-5 compares the energy the writer put on the mesh with blastFoam's first
   reading (`backend.py:1156-1175`) — the decode, not the remap. physics-anchors.md §3
   records "mass and energy match the profile to 1e-11" for chains into blastFoam; find out
   what that compared. Momentum is never compared.
3. **AMR source.** A 2D AMR stage exports at the display level
   (`reader.to_grid` → `MeshMap.gather`), not its finest cells.

**Measurement.** Per seam: source vs target integrals of mass, energy and radial momentum;
a census of the pressure jump at `alpha = 0.5`. Rule and thresholds written before.

---

## 5. P3 — capabilities (owner asked for both)

### `P3-27` · A hemispherical surface burst through the chain

A burst at or near the ground in 1D→3D (and 1D→2D) places a free-air sphere and the ground
cuts it; the reflection that happened during the 1D stage is missing. Standard practice is
a hemispherical charge with an enhanced equivalent mass. Owner decision needed: the factor
(ideal rigid ground vs the standard's value — cite UFC 3-340-02 from
`docs/references/INDEX.md`, not memory). Related: `P1-10` (the report compares a ground
burst with free-air KB; UFC Fig. 2-15).

### `P3-28` · Several charges with a hand-off

Today a profile stage has no charge list (`writer.py:530-531`, `:469-470`) and the native
3D solver takes exactly one of charge / profile / profile2d (`solver3d.py:122-124`).
Wanted (owner): extra charges beside a remapped field, and **several 1D hand-offs placed
into one 2D/3D stage**.

Constraints to design around:
- Each 1D field is a lone charge in free air, so it is valid only while the fields have
  not met: the shocked spheres must not overlap, nor reach the ground or a wall, at the
  hand-off (`P2-27`).
- All placed fields must be at **one** physical time. Identical, simultaneous charges can
  reuse one 1D run; different masses or delays need each 1D run stopped at a common time —
  a hand-off by time, not by radius as today.
- Axisymmetric 2D: charges on the axis only.
- blastFoam has one explosive phase per case (`MATERIALS[spec.material]`): one material.
- A profile stage writes `lambda.expl uniform 1` (B0, `writer.py:2202-2218`). A fresh,
  not-yet-detonated charge beside it needs `lambda = 0` in its cells and a working
  activation — the profile stage forces `linear` with an empty point list today.
