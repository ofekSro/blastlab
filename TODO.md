> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [docs/SCOPE.md](docs/SCOPE.md)

# TODO — open work

**The single work-management file.** Everything still open lives here.
Completed work is in [DONE.md](DONE.md), which also holds the identifier index
that code comments cite.

**Order.** P0 → P4, most severe first; within a level, in the order written.
Every item carries a stable id (`P2-3`, `N5-11`, `HD1-3`) — **cite it in commits
and in discussion.**

**The exception to the order: `HD1` sits above P0.** It is an owner directive of
2026-09-20 and is not part of the P ranking.

---

## HD1 · ⭐ First priority — HD1.3 effects on a structure

**What was asked:** compute the effects of an **HD1.3 — non-detonating** material
on a structure.

**Why this is a new track and not a parameter.** HD1.3 is **deflagration**:
subsonic, pressure-dependent burning (Vieille, `r = a·p^n`, `n ≈ 0.7–1.0` for
double-base). There is no detonation front, no `vDet`, no CJ state. The entire
blastFoam path in this repository is built on the opposite assumption.

> **Feeding HD1.3 in as "equivalent TNT" gives a wrong answer in the
> dangerous-in-reverse direction:** rise time too short, peak too high, duration
> too short — i.e. an impulsive load instead of a quasi-static one, which is
> exactly the distinction that decides the structural response.

### The three loads of 1.3, and which belongs to blastFoam

| Load | Standing | blastFoam? |
|---|---|---|
| **Fireball / thermal radiation** | Usually the **governing** harm in 1.3 | **No** — `radiationModel none`, and there is no radiation solver on the path |
| **QSP — quasi-static pressure under confinement** | The real structural load | Yes, but not through a reacting JWL phase |
| **Venting / jetting out of an opening** | Pressurised gas through an orifice | **Yes** — classical gas dynamics |

The physics that distinguishes 1.3: in the open the gas is produced slowly enough
to expand quasi-statically and barely makes a wave. **Under confinement it is a
positive feedback loop** — pressure ↑ → faster burning ↑ → pressure ↑. That is
why the same material is negligible outdoors and dangerous in a magazine, and why
**confinement is the first input**.

### Status (2026-09-21)

**The computational track is complete and tested**: `HD1-1`, `HD1-2`, `HD1-2b`,
`HD1-5`, `HD1-6`, `HD1-7`, `HD1-8`, `HD1-9`, `HD1-10`, `HD1-11a`, `HD1-11b` and
`HD1-11c`. A full HD1.3 assessment runs today via
`python -m blastlab --hd13 case.json` — quasi-static pressure, comparison with the
unconfined case, structural response, heat and a report — with no WSL and no Qt.
`HD1-11c` landed on 2026-09-21 and the track is complete end to end, from the GUI
form to the report. Details in [DONE.md](DONE.md).

**Three silent-failure bugs were found and fixed on 2026-09-21, and they share a
shape worth naming.** Each was correct in the regime the code was *verified* in
and wrong in the regime it is *applied* to, and none of them announced itself:

| | Verified where | Applied where | Cost |
|---|---|---|---|
| Fixed-step RK4 | `C/V` 0.5–5 | closed vessel, `C/V` 50–200 | peak 2700× low, `stop_reason='t_end'` |
| No chamber air | closed vessel, air <3 % of products | magazine, air ≈ products | pressure under-stated |
| Cohort staircase | fast fires (spread ≲ 2 s) | magazine fires (spread ≳ 10 s) | peak 62 % high at the usual `n = 20` |

The answer in all three cases was the same: **make the run check itself.** A
conservation residual, an air-to-product ratio, and a cohort refinement pass now
come back with every result, and `assessment.validate` turns each into a warning
next to the number rather than a footnote. Heat loss to the walls (`h_c`,
`Q_wall`) is also in the forward model as of the same day — `core/calibration.py`
had been inverting for a loss that `simulate` never applied.

### `HD1-3` · The venting, in blastFoam — **THE ONE REMAINING TASK**

Requires WSL. The three owner decisions that blocked it **have all been answered**
(2026-09-20), so it is open.

**What it will give that does not exist today:** the **jet leaving the opening** —
its propagation, what it does to structures **outside**, and the flow field in the
3D viewer. **The pressure *inside* the room does not need CFD:** slow burning mixes
well, the pressure is uniform, and 0D is the correct physics there, not a shortcut.

**The route — changed 2026-09-21, and the change deletes most of the work.** The
original plan put the chamber **outside** the mesh and drove `p(t)` in at the
opening as a time-varying boundary condition. Investigation found the repo has
**nothing** time-varying — no `Function1`, no `uniformFixedValue`, no `tableFile`
— and the guide documents exactly one such condition (`codedFixedValue`, §20.1)
while warning (§5.9) that the boundary *builds* the conserved quantities, so `p`,
`T` **and** `rho` would all have to be driven together or the face state is wrong.

**Putting the room INSIDE the mesh removes the need for any of it.** blastFoam
computes the blowdown itself; the 0D model's only job becomes the state at the
instant the vent opens. Deleted from the plan: the time-varying BC, a separate
patch for the opening, `createPatch`, `createBaffles`, a new mesh stage, a new BC
kind, a reacting phase, and `fvModels`. **The opening is a hole between wall
boxes — fluid** — and the walls are ordinary obstacles on the existing
`topoSet` + `subsetMesh -patch obstacles` path.

| Step | State |
|---|---|
| `HD1-3-pre` · the chamber's own air in the 0D model | ✅ done |
| `HD1-3a` · `core/room.py`, the geometry | ✅ done — measured: an off-grid 5 m room at `dx=0.1` loses **10.5 %** of its cavity and **27.6 %** of its opening to snapping |
| `HD1-3c` · `core/vent.py`, the hand-off and its validity metrics | ✅ done — measured: at burst the room is **`alpha_expl` = 0.115**, i.e. nine times more air than product gas, and air-vs-products is **+17.9 %** on the choked flow |
| `HD1-3b` · `init_mode='chamber'` in the writer | ✅ done — inert `type basic` phase with the propellant's `gamma`/`molWeight`; per-phase mass exact to 9 digits; **no `lambda.expl`**, so bug B0 cannot occur |
| `HD1-3d` · the 2D verification and the 3D answer | open, **needs WSL** — see the pre-registered condition below |
| `HD1-3e` · `core/qd.py` — ships with an empty table | ✅ done — `CRITERIA = {}`, and a row without a `source` is an **error**, not a blank column |
| `HD1-3f` · validation, GUI card, report section | open |

> **The number `HD1-3a` was built to produce.** `refine.snap_obstacles` moves
> every obstacle edge outward onto a base-cell face, so a room's walls grow and
> its cavity and opening shrink. At `dx=0.1` on a 5 m room that is **−10.5 %**
> volume and **−27.6 %** vent area. The volume shift is five times the 2 %
> `check_handoff_energy` runs at; the vent shift is nearly twice the 15 % the 2D
> verification is pre-registered at, so it would have been absorbed into `Cd` and
> disappeared. Both are now measured off the **snapped** boxes and reported.
> This is why the hand-off must conserve **mass and energy** and let pressure
> follow from the EOS — a cavity 10 % smaller simply arrives at a higher
> pressure, and a golden that pinned `p == p_0D` would pin the bug.

> **And measuring it is not the same as not having it** (owner, 2026-09-21). A
> 27.6 % error in the vent area means the CFD solves a *different hole* from the
> one that was asked for. So `room.align` now puts every edge — outer faces, wall
> thickness, vent — onto a base-cell face **before** the boxes are built. Snapping
> then has nothing left to move, the area that gets solved **is** the area
> reported, and the rounding is stated once against what was typed. Default on.

> **Pre-registered condition on `HD1-3d`, before the run that will be judged by
> it.** `_e2e_vent_2d.py` compares the CFD's mass flow through the opening against
> `deflagration._vent_mdot`. **That 0D comparison must be run at the
> post-alignment vent area and cavity volume, not at the numbers typed into the
> case.** The threshold is 15 % and the geometry error it would otherwise carry is
> 27.6 %, so running it against the entered numbers would fail the check for a
> reason that has nothing to do with the physics being tested — or, if alignment
> is on and the comparison is not updated, pass it while measuring the wrong
> thing. `measure()` returns both numbers; use them.

**The alternative, only if the above proves inadequate:** `phaseProperties` with
`AbelNobel` instead of JWL and `Arrhenius`/`pressureBased` instead of `linear`. The
guide documents both, and lists `AbelNobel` explicitly under **solid propellants**.
**But** neither is Vieille with a form function, so it would require calibration
against a closed-vessel test, exactly like the afterburn model against
Kingery-Bulmash. **Not needed while the room is inside the mesh:** the gas in the
chamber is combustion products that have finished reacting, so the phase is
inert — `type basic` with `idealGas`, `gamma` and `molWeight` from the
`Propellant`, and **not** air (γ 1.25 against 1.40, M ≈ 23 against 29).

### `HD1-4` · Removing the blockers

Only what `HD1-3` actually needs, from this list:

| Blocker | Location |
|---|---|
| `MATERIALS` is six JWL explosives only, no fuel row | `solvers/foam/materials.py:36` |
| `_phaseproperties` hard-codes `Murnaghan → JWL` | `solvers/foam/writer.py:1050` |
| Refuses to write a case with no detonation points | `solvers/foam/writer.py:1067-1073` |
| `validate_case` limits activation to `linear`/`none`/`programmedIgnition` | `core/case.py:564` |

*(The end-time safety cap is **no longer** a blocker: an explicit end time overrides
it in both directions since `e05ab22`, with a validator warning and a Run
confirmation. That is the fix that opened the way to this task.)*

### Deviations from the HD1 plan — recorded, not scheduled

The plan and the code diverged in places. Three of those divergences were bugs
and are fixed (see DONE.md); the rest are below. **Nothing here is scheduled.**
They are written down so that the next person does not rediscover them, and so
that "the plan said X" is never quietly read as "the code does X".

| Deviation | What the plan asked | What the code does | Why it is not urgent |
|---|---|---|---|
| `psi` / `G'(z)` | Carry the form function as an array `psi` and invert with the corrected `G'(z)` | `form_factor()` returns a scalar per call; the correction is folded into `reduce_closed_vessel` | Same answer for the three analytic forms shipped; only a tabulated grain would need the array |
| Grain geometries | Five forms | Three: `degressive`, `neutral`, `progressive` (θ) | The missing two are multi-perforated grains, which need a web-regression law rather than another `theta` |
| `hooks.Result` | The HD 1.3 assessment reaches the Results panel as a `Result` like a blast run | Its own bundle, rendered by `output/hd13.py` | Nothing downstream consumes it as a `Result` yet; `HD1-3` is what will |

**Closed 2026-09-21 — `governing_confined` no longer guesses.** It used to flip
at 2× ambient, so a sealed magazine at ~94 kPa **quasi-static** came back
labelled `'thermal'` because 94 < 101. Replacing it with a better round number
would mean typing a threshold out of a safety standard from memory, which is why
`core/qd.py` ships its table empty. The label is now **derived** from the element
when `compare(..., component=...)` is given one — the pressure is run through
`core/sdof.py` and `'pressure'` means it actually yielded — and **`'undetermined'`**
when it is not, with the ratio and the overpressure handed back. The same 94 kPa
yields a light panel (μ = 32.1) and does not yield a 200 mm reinforced wall
(μ = 0.118): one pressure, two answers, which is the point.

> **The sensitivity band has four axes, not three** (owner, 2026-09-21): `a`, `n`,
> `p_extinction` and **`h_c`**. Nothing here calibrates the wall coefficient, and
> it moves the answer by more than any burn-law parameter does. Measured on a
> closed vessel, where the peak is a thermodynamic limit the burn law does not
> enter: the band over `a`, `n`, `p_extinction` is **×1.000000** — a number that
> looks exact — and **×4.4** once `h_c` is an axis. On a sealed magazine, ×1.02
> against ×1.37. Which parameter dominates is a property of the *case*, which is
> why an axis may not be dropped for being usually small. An adiabatic case cannot
> perturb `h_c` at all, so the band reports `spans_heat_loss=False` rather than
> inventing one.

### `HD1-12` · ✅ closed 2026-09-21 — it was the discretisation, not the speed

Opened as "the 0-D model is too slow at the cohort count it needs", with
vectorising the Cash-Karp loop as the proposed fix. **The owner proposed the
better one: ramp the ignition across each cohort's interval instead of lighting
it in an instant.** That was right, and it removed the need for the speed work
entirely.

| `n` | staircase | ramp |
|---|---|---|
| 10 | 2.84 | **1.0223** |
| 20 | 1.57 | 1.0101 |
| 40 | 1.19 | 1.0054 |
| 160 | 1.040 | 1.0028 |

`n = 10` now lands within 2 % of converged, where the staircase was **still 1.2 %
out at n = 160**. So the converged answer was never 1.04 either — a realistic
magazine reaches **1.003× ambient**.

**And the mechanism is not the one that sounds right.** The ramp is *not* higher
order: measured, its entrainment error still falls as 1/n, the same as the
staircase, because the cohort edges sit at `T(i/n)^(1/d)` and the first interval
is `T/√n` wide. What it buys is **continuity** — the staircase jumps by a full
`1/n` at every edge and each jump shock-loads the chamber, while a slope does
not. Two wrong explanations were written into the code before that one, and
`test_deflagration.py` caught both; the measured sequences are pinned there.

Vectorising is no longer needed for correctness. Left undone.

**One finding that is a scope decision, not a deviation:**

- **Pyrotechnics are out of scope by decision** (owner, 2026-09-21). `gas_yield`
  and `Cp_condensed` are not modelled: every kilogram burnt is treated as gas,
  so pressure is over-predicted and the heat retained in solid residue ignored.
  `assessment.validate` now says so on any row that declares residue, rather than
  computing quietly.

### The highest-value next step needs no code at all

**There is no closed-vessel data for a real material.** `core/calibration.py` is
ready to receive it, and every row carries `uncalibrated` until it arrives.

Nothing in `PROPELLANTS` is calibrated, and that is **enforced by a test**
(`calibrated=False` on every row). The numbers are digit-ranges for material
classes, not product data — exactly the standing of the non-TNT afterburn rows.
**Without a closed-vessel experiment on the real material, no number from here can
be cited.**

**Three fields the existing data cannot determine**, which will recur at every
stage: the low-pressure extinction threshold, the heat capacity of condensed
residue, and the atmospheric burn rate. Each carries **its own** `calibrated`
flag, not one flag per row. This is a permanent property of a model calibrated in
a closed vessel (50–300 MPa) and applied at magazine pressures (0.1–2 MPa) — an
extrapolation of 2–3 orders of magnitude, in which the dominant error is in `n`,
not in `a`.

> **`extrapolated_fraction` is the number-one risk, and it is now measured rather
> than asserted.** Both gun propellants return **1.000**: a closed vessel is
> calibrated at 50–300 MPa and a magazine sits at a few MPa, so **all** of the burn
> is a two-decade extrapolation. The composite, characterised in a strand burner at
> motor pressures, returns **0.430**.

---

## P0 — Urgent: risk of losing work / broken repo

**Nothing open.** P0-1, P0-2 and P0-3 closed 2026-09-09 (`e344d17`); P0-4 closed
2026-09-17. See [DONE.md](DONE.md).

> **But P0-4's trap is permanent and worth re-reading before any session that
> matters:** every code path that builds the GUI can delete the run corpus, and
> `_e2e_gui_*` and the QA harnesses build one. Verify
> `env.auto_cleanup(settings.load())` returns `(0, 0)`, and copy out any run you
> care about. Deletion inside WSL is not reversible.

---

## P1 — Hurts the user or correctness

### P1-4 · Afterburn parameters for non-TNT materials are uncalibrated · **owner decision**

The afterburn model is calibrated for **TNT only**, against Kingery-Bulmash. For
C4, RDX, HMX, PETN and ANFO, `Q0` is derived from **oxygen balance alone** — right
order of magnitude, no calibration against data. The default is `none`, so nothing
run so far has been affected.

**Decide:** if you intend to cite numbers for a non-TNT material, it needs
calibration or a source. Otherwise label it in the interface —
*"uncalibrated (oxygen balance)"* — next to the material selector when afterburn is
on.

### N5-11 · Remove `RHO_MIN`? · **not done, and do not do it on one run**

The floor in `writer.profile_state` is **two guards in one**: a density floor and a
NaN/Inf guard on the divided quantities `u = rhoU/rho`, `e = rhoE/rho − ke`.

**The case for removing it:** after the fireball fix, the 2D stage no longer hands
off vacuum — `min(rho)` went from 1.711e-04 with 20 sub-floor cells to 7.360e-02
with **zero**, a rise of three orders of magnitude. No currently-tested hand-off
path produces such cells (`n_floored = 0` everywhere).

**The case against:** the independent audit found the evidence **confounded** — the
"clean" runs stopped at `t ≤ 0.75 ms` while the affected ones reached `t ≥ 2.07 ms`,
so the clean runs never entered the regime that produces the pathology. And the
floored cell is **not ambient**: `rho = 1e-3` with products/JWL/TNT gives
**p = 120.96 Pa** beside neighbours at 101,324 Pa — a 1225:1 density jump at a cell
face. **The floor does not remove the pathology; it trades it for a milder one.**

> **The one run that settles it.** Re-run the chain's stage 2 from
> `attempt_10/stage2_case.json` byte-for-byte on the current tree, changing exactly
> one field — `t_end` from 0.0 to **5.0e-3**, so the terminate BC cannot stop it at
> 0.6 ms — serially, and report `min(rho)` and `count(rho < 1e-3)` at the hand-off
> instant and at `t_end`. That separates "the fix worked" from "the clean runs
> stopped too early".

**Until then the floor stays**, as a safety net. It costs nothing when it does not
fire.

### The residual ≈2 % parallel-vs-serial peak offset · **open, and narrowed**

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

### Claim 3 — three experiments designed and not run

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

### Corrections the audit implies, not yet applied

- **`adjustLocations` is a no-op for every interior probe.** `core/case.py:90`,
  `:202`, `:310` and `writer.py:107-111` all state that it "snaps each gauge onto
  the centre of the cell holding it". **That is wrong for every interior gauge**,
  which is all of them. The comments need correcting.
- **The Claim 4 write-up names the wrong function.** It is
  `fluxScheme::snGradAlpha`, not `fluxScheme::AD` — fix it before the finding is
  quoted anywhere, because `::AD` sends a reader to a clean four-line function.
- **Prefer `sum(lambda)` over `count(lambda >= 0.99)`** in any future ignition
  measurement; the count is valid only at the first write.

---

## P2 — Misleading display and missing test coverage

### P2-1 · The 1D progress bar is ~10× misleading

`solver1d.py:242` computes progress as `t / safety_cap`, while 2D/3D use the front
radius relative to R. The safety cap is ~10× the real run length, so a 1D run looks
as if it is barely moving.

> **Note:** if the fix touches the solver's stdout it requires an explicit
> re-baseline, in the same commit.

### P2-2 · "Energy [J/kg]" in foam runs is an approximation shown as truth

In the viewer, the Energy field for a foam run is computed as an ideal-gas
approximation `p / 0.4ρ`. Either hide it for foam runs or label it
*"Energy [J/kg] (approx)"*.

### P2-5 · What has never been checked by eye

Four things that need a person at a screen. Full instructions in
[docs/heavy-runs.md](docs/heavy-runs.md).

- Opening the VTK files the application exports, **in ParaView** — confirm they
  really load.
- Volume render with manual Min/Max in the 3D viewer.
- DPI other than 100 % (Windows display settings). *(Now partly covered by harness
  scenario Q04.)*
- A second monitor.

*(The rest of the manual checklist — static refinement, Show mesh, the gauge table,
the run browser, post-mortem loading, Stop at every stage — was confirmed by eye in
the 2026-09-07 QA round. No need to repeat.)*

### P2-7 · `test_foam_parallel` can compare np1 against np1 without saying so

An explicit rank count is clamped to the machine's ceiling (cores minus headroom,
and RAM divided by `RAM_GB_PER_RANK = 2`). On a small VM the ceiling is 1, and the
test will run np1 against np1, **pass, and test nothing**. This is a weakness in the
test, not in the code.

**Fix:** have it call `env.rank_ceiling` at the start and skip explicitly
(`[SKIP] VM too small for 2 ranks`) rather than passing silently.

### P2-8 · `test_gui_run_browser` hangs on a modal dialog

`run_browser.delete_selected` (`:295`) calls `messagebox.showwarning(..., parent=self)`
when refusing to delete a live run. The test does not patch `messagebox`, so it
hangs there until timeout. Verified to exist independently of any recent change: the
test hangs on the same line in two consecutive runs, and passed once in the same
round — i.e. the behaviour depends on window focus, and the test is
non-deterministic.

**Fix:** inject a `warner=` alongside the existing `confirm=` (the test already
injects `lister`, `sizer`, `deleter`, `confirm`, `on_resume`) and let the test
supply a stub.

> This is on the Tk side. It stays as long as `--tk` does — see the standing owner
> decision in [docs/history/ui-migration.md](docs/history/ui-migration.md).

### The `_e2e_foam_amr2d` accuracy thresholds · **owner decision**

AMR reads **−11.8 % on peak** and **+11.1 % on arrival** against the uniform
reference, on thresholds of 10 %. The impulse passes (+2.9 % of 15 %). **The test
is correct — it measures a real thing:** AMR spreads the front over more cells than
the uniform mesh.

**Decide between:** relaxing both thresholds to 15 % and documenting that as AMR's
accuracy at this configuration, or tightening the test's AMR configuration (more
levels / smaller `amr_interval` / larger `amr_buffer`) until it keeps up.

### MPI decomposition breaks x/y symmetry · **document, do not touch**

On a perfectly fixed mesh with no AMR, with mirror gauges at exact cell centres and
a pinned write schedule: np=1 → **0.10 %**, np=2 → **0.26 %**, np=8 → **4.85 %**,
deterministic to the digit at every rank count. The absolute peak also moves between
rank counts (8277 / 8872 / 8517 kPa) — **a ±7 % parallel deviation in the near field
on a fixed mesh.**

`test_foam_3d_smoke` now pins np=2 so the gate is not machine-dependent.

> **This is physical accuracy — record it and leave it alone.** If it is ever worth
> reducing, the next direction is the decomposition method (`scotch` is not
> symmetric; try `simple` with symmetric coefficients) — **an owner decision**,
> because it changes the physics and the wall time of every parallel run.

**And a warning against the obvious move:** `hierarchical`/planar decomposition was
tried and **reverted**. In the 2D parallel case `scotch` reproduces serial almost
exactly (impulse 188.5 against 188.5 Pa·s) and the planar cut **broke np1↔np2
equivalence entirely**. Two cases, opposite answers, and no mechanism that explains
both. **That is not enough to change what every parallel run does.**

### N5-12 follow-up · a per-point GUI table for delays/radii

`det_delays` / `det_radii` are wired through the API, the JSON and `validate_case`,
and the activation dropdown is wired in both front ends. **What is missing is the
GUI table**: it changes the data shape of the `det_points` widget and needs a parity
design of its own.

---

## P3 — Capabilities and improvements, on request

*(None of these blocks anything.)*

**Physics**

- `P3-1` Non-box obstacles (STL → snappyHexMesh) — needs the same resampler as AMR.
- `P3-2` Enable `pressureBased` activation — per-material rate constants; only if
  ignition physics matters.
- `P3-3` Per-case override of `maxDeltaT`/`deltaT` — trivial wiring in the writer.
- `P3-4` HLLC comparison: `dicts.FLUX_SCHEME = 'HLLC'` is a one-line flip;
  `test_foam_1d_vs_native.py` is the harness. *(HLLC is sharper at contact surfaces —
  the products/air interface — than Kurganov.)*
- `P3-5` Axisymmetric smear option in 2D (3D has it; 2D refines only).
- `P3-12` Static refinement zones for a profile-initialised stage. `refineMesh`
  renumbers cells, so `writeCellCentres` + `build_remap` must move before
  `write_deferred` and the fields must be written through `spec.remap` — the
  machinery exists, only the order is wrong.
- `P3-13` Extra charges exist only in 3D. In **planar 2D** it is feasible — a 2D
  charge is an infinite cylinder, and `spec.charges` is already a list on the 2D
  path. Missing: the setFieldsDict, overlap/boundary checks and the GUI table.
  Axisymmetric stays a single charge on the axis — that is geometry, not a gap.
- `P3-14` There is no 3D remap format, so **a 3D stage is always the end of a
  chain**. Large work (format + remap + validation + GUI); only if continuing a 3D
  run into a further stage is really wanted.
- `P3-15` Obstacles do not survive the 2D→3D remap — they would become rings around
  the axis, so `save_profile_2d` drops them with a warning only. The 3D stage
  continues a state that evolved around obstacles that are no longer there.
  **Minimum:** raise it to a validation warning in the GUI instead of a stdout print.

**From the solver-options review** — full detail and dict snippets in
[docs/verification/solver-options-review.md](docs/verification/solver-options-review.md).

- `P3-16` **`conservedQuantities` on every run**, checked in `postmortem`. Both
  hand-off bugs were energy non-conservation, and this function object would have
  caught both automatically. *Small.*
- `P3-17` **`timeOfArrival` + `overpressure store yes`.** Arrival time is the third
  standard output of blast engineering and the repo already produces the other two.
  *Small.*
- `P3-18` **`volScalarFieldMassIntegrated`** for charge mass — sets alpha so the
  deposited mass equals the request **exactly**, which would let the charge
  resolution drop from 8 cells back to 5 and save 4.1× the cells in 3D. **Validate
  against the KB anchor first:** the afterburn calibration was fitted with the
  present deficit baked in and would need refitting. *Medium.*
- `P3-19` **`beginUnrefine`** (the guide recommends it explicitly for explosives) and
  **`allowableImbalance`** in `dynamicMeshDict`. *Small.*
- `P3-20` **`rotateFields`** as a replacement for the Python remap. Operates on
  fields rather than interpolated conserved quantities, rotates vectors correctly,
  and `-refine` lifts the "no refinement zones on a profile stage" restriction.
  **The guide warns the mapping is not conservative** — validate against the
  baselines, do not swap blindly. *Large.*
- `P3-21` Expose `activation programmedIgnition` and `initiation delays` in the GUI.
  *Medium.*
- `P3-22` **`reconstructParAll`** for the parallel AMR path — the entire
  post-processing path would work directly instead of through the special Python
  ingest. The existing workaround works and is cheaper, so this is an opportunity,
  not a bug. *Medium.*
- `P3-23` **`DoanNickel` EOS for air** — accounts for dissociation at high shock
  temperatures, where constant γ overestimates pressure. Directly relevant to the KB
  anchor at small Z, and a one-word change. *Small, research value.*
- `P3-24` **Schlieren / shadowgraph** fields for animations — the standard
  visualisation for shock waves, one extra field per time directory. *Small.*

**Performance**

- `P3-6` Read `processor*/` directly for uniform MPI runs too (skip reconstructPar) —
  only if the ~3 s per write is annoying. The mechanism already exists for AMR.
- `P3-7` The viewer's blit path renders twice and allocates ~1.3 MB per frame.

**Viewer polish**

- `P3-8` Log contours apply only to slice planes.
- `P3-25` The **"Surface loads" colour bar stays linear** while the field bar is
  logarithmic — the loads layer holds its own range and does not receive the log
  flag.

**Cosmetic** *(anything touching solver stdout needs a re-baseline)*

- `P3-9` The x-axis label on an axisymmetric animation: `x [m]` → `r [m]`.
- `P3-10` A chained run prints "0 kg TNT" in the 3D initialisation line.
- `P3-11` The semantics of `n_snapshots` differ between 1D and 2D/3D.

---

## P4 — Environment, disk, personal

### P4-1 · The repository sits inside OneDrive

`git worktree remove` failed once with "Permission denied" — a sync lock on `.git`.
Consider excluding `.git` from syncing, or moving the repository out of OneDrive.

### P4-2 · Disk cleanup — low urgency

Candidates, all of them calm decisions rather than pressure: a 13.4 GB zip that
duplicates an unpacked folder beside it; `C:\OneDriveTemp` (~6 GB of upload
temporaries, recreated if deleted); a ~45 GB reference-model duplication; and the
large win without deleting anything — **Files On-Demand ("Free up space")** on the
biggest archive folders. `hiberfil.sys` is 3.1 GB and `powercfg /h off` removes it
if Hibernate is unused.

> **Never touch `~\Desktop`** — about 930 GB of thesis data.

### P4-3 · WSL run cleanup, and the trap inside it

`python -m blastlab --clean-foam-runs` (also `--older-than N` / `--keep-gb N`).
Automatic cleanup runs on GUI start; disable with `auto_cleanup: false` in
`%APPDATA%\blastlab\settings.json`.

**The `ext4.vhdx` does not shrink by itself.** Reclaim with `wsl --shutdown` then
`wsl --manage Ubuntu --set-sparse true`.

> The corpus once reached **374 GB and filled C:**. Cleanup is now on with a 150 GB
> ceiling and 10 runs kept.

---

## Owner decisions waiting for you

| # | The decision | Recommendation |
|---|---|---|
| **HD1-3** | Is there closed-vessel data for a real material? Without it no HD1.3 number can be cited | Get the data — it is the highest-value step and needs no code |
| P1-4 | Afterburn for non-TNT materials — calibrate, or label as uncalibrated | Label; calibrate only if you will cite numbers |
| amr2d | Relax the AMR accuracy thresholds to 15 %, or tighten the test's AMR configuration | Relax and document — the deviation is real AMR behaviour, not a bug |
| decomposition | Leave `scotch`, or investigate a symmetric decomposition for the ±7 % near-field parallel deviation | Leave it. Two cases gave opposite answers and no mechanism explains both |
| P4-1 | Move the repository out of OneDrive | Yes |
| P4-2 | What to delete from disk | Not urgent |

---

## Closed items that code comments still cite

These are **done**. They stay named here because comments in the source point at
this file by id, and a reference that resolves to nothing is worse than a long file.

### `N5-7` · ✅ closed 2026-09-20 — `det_radii` is now the default

Cited by `solvers/foam/writer.py:1308` and `tests/test_foam_writer.py:599`.

`writer.default_det_radius` now **always** writes `initiation.radii`, at a radius of
0.9 cells of the mesh *at the detonation point* (it follows `lmax` and AMR, otherwise
a base-cell radius would ignite dozens of refined cells).

**Why it works:** the `radius_ > small` branch tests **cell centres**, and every cell
centre belongs to exactly one rank — so it is partition-invariant **by construction**,
not by measurement.

**Acceptance measurements:** the seed goes from 1-vs-4 to `sum(lambda) = 4.000000` in
both serial and the worst-case parallel; at an engineering-range gauge **+0.006 %** on
peak and **0.000 %** on impulse and arrival, against +1.5 % for the `findCell` path;
the Kingery-Bulmash anchor **did not move at all** (0.89/0.85/0.86/0.87), so the
afterburn calibration needs no refit; `test_regression.py` stayed byte-green.

> **The cost, stated explicitly:** foam results from before 2026-09-20 are not
> byte-comparable. The serial peak in the measured case went 19914 → 19607 kPa
> (−1.5 %), because a ball of radius ~dx around a corner point ignites the 4 cells
> meeting there instead of the one cell `findCell` chose arbitrarily. 15 goldens were
> updated — one `radii` line in each, zero deletions.

**What is still open from it** is the residual ≈2 % parallel offset in P1 above — the
+7 % at `scotch np=2` is **not** this mechanism. Full history:
[docs/verification/blastfoam-claims.md](docs/verification/blastfoam-claims.md).

---

## Standing rules for every task

```
Project: blastlab - Python blast-wave simulation desktop app, native numpy
1D/2D/3D solvers in blastlab/solvers/, blastFoam backend in
blastlab/solvers/foam/ (writes OpenFOAM-9 cases, runs them in WSL Ubuntu, reads
results back onto uniform numpy grids), pyvista/VTK viewer in blastlab/viz3d/.
GUI: PySide6 in blastlab/ui/ is THE GUI (`python -m blastlab`). The
customtkinter original in blastlab/gui/ is kept as the way back
(`python -m blastlab --tk`) and must not be deleted.
Ids like B23/G7/A5/N7/W2 refer to DONE.md section 5 (the reference index).

Hard rules:
- Never change native-solver stdout or the byte-pinned outputs unless the task
  explicitly says "re-baseline". `python blastlab/tests/test_regression.py` must
  stay green (or be deliberately re-baselined per the task, in the same commit).
- Foam goldens regenerate only via `python blastlab/tests/test_foam_writer.py --update`
  and an eyeballed diff.
- Tests are plain scripts: `cd blastlab/tests && python test_X.py`. Files named
  `_e2e_*.py` are manual end-to-end runs (need WSL, ~1-6 min each). Run the fast
  no-WSL matrix after every task; WSL suites once at the end of a task that
  touches solvers/foam/.
- WSL work: run in the FOREGROUND (backgrounded shells that spawn WSL children
  report completion early and lose stdout). Before any WSL suite check nothing is
  running (`wsl.exe -d Ubuntu -- pgrep -a blastFoam`); a foreign solver makes
  test_foam_stop and memory-heavy suites fail spuriously. After killing anything,
  check for orphans the same way and kill them. 2D axisym foam cases at default
  size can take 30+ min - use tiny domains.
- Do not touch files outside the task's scope without saying why.
- GUI verification: `python blastlab/tests/_qa_ui_harness.py --resume --scenario <ids>
  --redo <ids>` opens a real Qt window on screen - 63 scenarios (`--list` shows the
  matrix; output under ~\blastlab_qa\<stamp>\shots), plus `test_ui_*.py` (offscreen)
  and `_e2e_ui_*.py`. `_qa_gui_harness.py` is the same protocol against the Tk app
  and stays as long as `--tk` does; run it only when a change touches blastlab/gui/.
- Qt work: `blastlab/ui/` must never import pyvista/VTK - the 3D scenes live in
  the viewer child process (`blastlab/viz3d/process.py`). `test_ui_no_vtk_in_main.py`
  pins this.
- Windows: the test_regression baselines show as modified purely from CRLF
  conversion - do not commit them unless the task re-baselines.
- Markdown here is edited with editor tools only, never through PowerShell
  strings - PowerShell 5.1 mojibakes any file with a non-ASCII character.
- Finish by: (1) listing exactly what changed, (2) pasting the tail of each test
  you ran, (3) ticking the item here + a one-line note of what was done.
```

**Measurement discipline** — the full list is in
[docs/verification/physics-anchors.md §7](docs/verification/physics-anchors.md).
The two that matter most: **never measure peak alone** (peak, positive-phase
impulse *and* arrival, every time), and **pre-register the decision rule with its
numeric threshold before the run that will be judged by it.**

---

## The test matrix

```
cd blastlab/tests

# Fast, no WSL - run after every task
python test_regression.py         # native byte-parity - MUST stay green
python test_foam_writer.py        # case-generation goldens
python test_foam_reader.py        # ascii+binary parsers, probes merge
python test_case_validate.py      # cap gating per backend
python test_foam_env.py           # WSL env probe parse, cleanup policy, settings
python test_hardware.py           # machine identity, cache TTL, host RAM, native caps
python test_adaptive_interval.py  # writeInterval controller
python test_foam_live_due.py      # live-frame cadence gate
python test_refine.py             # refined-mesh plan + AMR remap + validation guards
python test_bc_trigger.py         # boundary kinds, end time, trigger gauge, markers
python test_foam_postmortem_decomposed.py   # loading a parallel AMR run
python test_foam_resume.py        # restart points + the AMR FO disable
python test_gauge_summary.py      # per-gauge peak/arrival/impulse
python test_report.py             # field CSVs + HTML report
python test_foam_ingest_order.py  # ordered ingest + accumulators
python test_foam_amr_ingest.py    # AMR per-time ingest on fake time dirs
python test_deflagration.py       # HD1: the 0D burn model
python test_sdof.py               # HD1: the SDOF structural response
python test_unconfined.py         # HD1: the unconfined branch
python test_sensitivity.py        # HD1: the band around an uncalibrated peak
python test_room.py               # HD1-3a: a room as boxes, and what snapping does
python test_vent.py               # HD1-3c: the 0D -> CFD hand-off, phase by phase
python test_foam_chamber.py       # HD1-3b: the room as a blastFoam case
python test_qd.py                 # HD1-3e: siting, as a mechanism with no numbers
python test_ui_crashlog.py        # a raising Qt slot must not kill the process
python test_revolve3d.py          # (belongs in this matrix - fast, native, green)
python test_viz3d_sampling.py / test_viz3d_hooks.py / test_viz3d_scene.py
python test_viz3d_panel.py / test_viz3d_protocol.py
python test_ui_drain.py / test_ui_run_panel.py / test_ui_view3d_host.py
python test_ui_setup_form.py / test_ui_preview.py / test_ui_results.py
python test_ui_chain.py / test_ui_run_browser.py / test_ui_parity.py
python test_ui_three_surfaces.py / test_anim_scale.py
python test_ui_no_vtk_in_main.py  # no VTK in the GUI process
python test_ui_no_mpl_pyplot.py   # no pyplot in the GUI process
python test_gui_*.py              # the Tk suites - run when blastlab/gui/ or a
                                  # shared neutral module changes
python test_blast2d.py            # 2D native physics (the matrix bottleneck, ~47%)

# Slow, no WSL - run on its own, WITHOUT a timeout
python test_blast3d.py            # 3D native physics, ~12 min

# WSL (first confirm it is free: wsl.exe -d Ubuntu -- pgrep -a blastFoam is empty)
python test_foam_1d_vs_native.py  # physics gates (~2 min)
python test_foam_2d.py            # axisym + planar (~3 min)
python test_foam_3d_smoke.py --tiny
python test_foam_parallel.py      # np1 vs np2 + determinism (~5 min)
python test_foam_postmortem.py    # live-vs-loaded round trip
python test_foam_features.py      # multi-charge + activation none
python test_foam_kb_anchor.py     # KB free-air + C4/TNT (~2 min)
python test_foam_kb_anchor.py --impulse    # the impulse anchor
python test_foam_stop.py          # SIGSTOP/writeNow regression
python test_foam_wsl_resume.py    # the EIO / distro-teardown resume path
python _e2e_foam_*.py             # manual end-to-end, one at a time
python _e2e_ui_*.py               # real Qt window, real runs
```

> **A foreign blastFoam process makes `test_foam_stop` and the memory-heavy suites
> fail falsely. Check before blaming the code.**
>
> **Harness exit 0 is not "passed".** A failed `qa.check` records a finding and the
> scenario continues, and checks that passed are not recorded anywhere. The truth is
> in `findings.jsonl`.
