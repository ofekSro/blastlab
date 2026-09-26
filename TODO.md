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

**Two exceptions sit above P0, in this order: `OUT`, then `HD1`.** Both are owner
directives (2026-09-26 and 2026-09-20) and are not part of the P ranking.

---

## OUT · ⭐ Highest priority (owner, 2026-09-26) — model folder, VTK output, disk

**The whole plan, approved on 2026-09-26, is
[docs/model-folder-and-vtk-plan.md](docs/model-folder-and-vtk-plan.md).** This
entry only orders it; the specification, the decisions and every acceptance
criterion live there. Owner's words: first the VTK export; once it works, is
fixed and approved — the disk.

| Id | What | Order |
|---|---|---|
| `OUT-1` | ✅ **Model folder** — done 2026-09-26 (DONE.md §0c); `gui-qa-tester` screenshots and owner acceptance pending. Plan §2 | 1 |
| `OUT-2` | **VTK output options** (Viper-style Output card, blastFoam only): off / sections and obstacles / volumes, a per-case field checklist, cadence in simulated ms or solver steps, files into `<MODEL>\vtk\`, time directories deleted as they are converted. Plan §3 | 2, then owner acceptance |
| `OUT-5` | **Reclaim the 481 GB WSL disk** — [docs/wsl-disk-reclaim-plan.md](docs/wsl-disk-reclaim-plan.md); the six owner decisions in its §3. Only after the owner accepts `OUT-1` + `OUT-2`. Plan §6 | 3 |
| `OUT-3` | **Only the newest fields kept in WSL**, every blastFoam run, default on, with a "keep all fields" box. Mandatory. Plan §4 | 4 |
| `OUT-4` | **The rest of the Viper matrix**: gauge quantities, dynamic pressure, peak impulse, per-obstacle ids, decimation. Mandatory. Plan §5 | 5 |

---

## HD1 · ⭐ Owner directive 2026-09-20 (second to `OUT` since 2026-09-26) — HD1.3 effects on a structure

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

**2026-09-24: `HD1-3`, the venting in blastFoam, is closed** and its record moved to
[DONE.md](DONE.md) §0 — the 3-D answer passed all thirteen checks committed before
its run. The same day `HD1-13` closed too: the wall load, with reflection and
stagnation, is delivered as a trace in `docs/hd13/`, and it is an upper bound on the
load. Each wall is judged by its own criterion. `HD1-15` added a disk-saving write
budget. What stays open on HD1: `HD1-14` (the optional third `Cd` point), `HD1-4`, and
closed-vessel data, which needs no code.

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

### `HD1-16` · No SDOF in the app — export the wall load for SBEDS · **owner decision 2026-09-25**

**Decision (owner):** blastlab gives the load, not the structural response. The
response is solved outside, in SBEDS. Replaces two open questions in
`docs/ENGINEERING_QUESTIONS.md`: phase 0 #1 (the band's ends bracket everything but
the nominal μ, 0.0509 / 0.1049 against 0.1164) and hd1-wall-load #1 (the envelope
gives a lower μ than G1 alone). Both come from judging the response at the ends of
the *load*. With no SDOF in the app, both close. The worst case is found in SBEDS
over every exported trace.

**Step 1 is ✅ closed 2026-09-26** (batch `hd1-16-load-export`). The record is in
[DONE.md](DONE.md) §0b: the SBEDS CSVs, the wall traces with optional clearing, and no
μ or verdict in any output. The questions it raised are in
`docs/ENGINEERING_QUESTIONS.md` under `hd1-16-load-export`.

**Step 2 (after the owner has run one case through SBEDS):** delete `core/sdof.py`,
`structural_verdict` and their tests. Mark the μ values in the HD1-3d / HD1-13
records (C10's "survives") as historical, produced by the removed in-app SDOF.

### `HD1-17` · The HD 1.3 starter case is a weak check, and two texts overstate · **owner decision 2026-09-25**

Both report flags are **correct as coded**: "blast negligible: False" at Mach 0.0917
is above `MACH_QUASI_STATIC = 0.05` (`core/unconfined.py:85`), and "the whole burn
outside the calibration window" is the real HD1-3 limitation (a burn law measured in
a closed vessel at tens-hundreds of MPa, applied at ~0.1 MPa). What is wrong is
around them. Source: `docs/ENGINEERING_QUESTIONS.md` phase 7 #1-#2, phase 0 #3.

**(a) Texts: ✅ closed 2026-09-26** (batch `hd1-16-load-export`, `658fb4c`); see
[DONE.md](DONE.md) §0b.

**(b) A representative starter case.** Today's peaks at 102.35 kPa absolute (~1 kPa
over), μ 0.12, so it exercises nothing. **The owner supplies the design-basis scenario**
(room, vent, material and mass, from the standard / QD tables / advisor). The
implementer builds the JSON, documents where each value came from, and replaces the
characterisation goldens that pin the old case **as part of this decision** (§9), with a
before/after note. Blocked on the owner's input.

### `HD1-18` · Picking a material fills its fields with the severe preset · **owner decision 2026-09-26**

**Why.** The HD 1.3 form is hard to use: the Material card's override rows are blank
("blank = table") and the user has to know what goes in them. **Decision (owner):**
choosing a material fills every material field with the value that gives the **most
severe load on the structure**, with a grey note beside each field giving the range and
its standing. The user may edit any field. Done **together with `P1-15`** (the form
takes `a` in mm/s/MPaⁿ).

1. **Qt and Tk** (§9). Selecting a propellant fills `ov_n`, `ov_a`, `ov_r_atm`,
   `ov_web`, `ov_p_ext`, `ov_secondary`. Changing the material re-fills them. **Loading
   a case file never re-fills**: the file's values stand, or a saved case stops
   reproducing.
2. **The severe direction, and the pivot (owner, 2026-09-26).** `n` is varied about the
   pressure it was **measured** at, `p_piv = p_valid_min`, holding the burn rate there
   fixed, not about 1 Pa. With `dn = sensitivity.DEFAULT_DN` and
   `fa = sensitivity.DEFAULT_A_FACTOR` (one source for the widths):
   `n_s = n0 - dn`, `a_s = fa · a0 · p_piv^dn` (SI). Below `p_piv` a lower `n` burns
   faster, and the gun propellants spend the whole storage-room burn below it. The
   composite's window starts at 1 MPa, inside the 0.1-2 MPa storage-room range, so its
   direction is **measured, not assumed**: run both signs on the starter case and take
   the higher peak. Record which one won. `p_extinction` = 0 (never goes out), which is
   already the table value.
3. **No invented ranges.** `r_atm`, `secondary_heat` and `web` have no range in the
   repo. They are filled with the table value, and the note says "no range defined".
   (`web` enters only as `a/w`, which the `a` range already covers.)
4. **The grey note** per field: the range, the preset's end, and the standing, e.g.
   "n 0.75-1.05 · preset 0.75 · class judgement, no source". It comes from the same
   numbers the preset used.
5. **Standing.** Filled values are **not measured**: `uncalibrated` does not shrink and
   the `measured` box stays off. The report says the material is "severe preset (class
   ranges, unsourced)", not "user override". `core/fuels.py` stays nominal, so no case
   without overrides moves and no characterisation golden moves except the form's own.
   Pin those with a before/after table.

Acceptance: picking each of the three materials fills the six fields and the notes, in
Qt and Tk; the preset's peak ≥ every corner of a band taken with the same pivot, on
the starter case, for each material; a saved case reloads with its own values; P1-15's
own acceptance; goldens unchanged except the form's; Qt and Tk GUI QA.

### `HD1-14` · A third `Cd` convergence point — optional, not done

24 cells across the opening, on a geometrically shrunken room: `Cd` depends on the
opening's local geometry (wall thickness to width, pressure ratio) rather than on the
room's size, so a small room with a minimal domain would give it affordably. It would
turn `DEFAULT_CD_RANGE = (0.72, 0.90)` (`core/sensitivity.py`) from a two-point
extrapolation into a measurement. Register the convergence threshold before the run.
**Disk, measured 2026-09-24:** `n_snapshots` does not bound it — the adaptive write
interval made 748 writes in the 3-D answer's 30 ms, each kept reconstructed and again
decomposed, **172.96 GiB**. Run it with `HD1-15`'s `write_budget` (e.g. 60, about
8 GB). If a run with a meshed wall is ever wanted (HD1-13's route (a)), it needs the
same budget and a window longer than 30 ms: every T1 peak fell after the record ended.

### `HD1-4` · Removing the blockers

*(2026-09-24: `HD1-3` closed on the chamber route, which needed none of these. Close
`HD1-4`, or keep it for the `AbelNobel` fallback recorded with `HD1-3` in
[DONE.md](DONE.md) §0 — an owner decision.)*

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

### `HD1-12` · ✅ closed 2026-09-21 — moved to [DONE.md](DONE.md) §0 on 2026-09-26

### Scope decision — pyrotechnics are out

*(The vent verification that used to sit here closed with `HD1-3`; its record,
`Cd` as the fifth band axis and the ≥ 12-cell rule are in [DONE.md](DONE.md) §0.)*

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

P0-1, P0-2 and P0-3 closed 2026-09-09 (`e344d17`); P0-4 closed 2026-09-17. See
[DONE.md](DONE.md).

### P0-5 · The app reads a settings file nobody else sees · **owner decision 2026-09-25**

Microsoft Store Python virtualises `%APPDATA%`: `core/settings.py:64-71` resolves to
`%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\Roaming\blastlab\settings.json`,
while editors, PowerShell and the Read tool see the 27 B `%APPDATA%` file
(`auto_cleanup: false`). The virtual copy had `auto_cleanup: true` (150 GB / 14 d /
keep 10) and was rewritten by a GUI start on 2026-09-25 10:22. Set to `false` by hand
the same day as a stop-gap. Source: `docs/ENGINEERING_QUESTIONS.md`, hd1-3d-close #3.

**Decision (owner):** the settings file lives **in the repo**, at one explicit path
that no virtualisation can redirect.

1. `settings.default_path()` returns a repo-local file (e.g. `<repo>/settings.json`,
   next to `blastlab/`), added to `.gitignore` - it carries machine-specific `hw_*`
   fields and must never be committed.
2. One-time migration: if the repo file is missing, seed it from the virtual copy (or
   the `%APPDATA%` one), and **force `auto_cleanup: false`** in the result. Log which
   source was used. Never delete the old files.
3. A dry run: `env.cleanup_plan(settings)` returns what the policy *would* delete
   (names, sizes, mtimes) and deletes nothing; `auto_cleanup` is built on it.
4. CLAUDE.md §8.2, the P0-4 note below and P4-3 point at the dry run and the new path.
   Replace the "check" `env.auto_cleanup(settings.load())`, which deletes.
5. Tests: `default_path()` is inside the repo and ignored by git; migration forces
   cleanup off; `cleanup_plan` touches no file. Tk and Qt both read the same file
   (run the `test_gui_*` suites - §9).

Acceptance: `python -c "from blastlab.core import settings; print(settings.default_path())"`
prints the repo path under Store Python, and the Read tool sees the same bytes the app
loads.

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

### P1-7 · blastlab cannot read the `0/` fields it writes itself · **found 2026-09-24**

`writer._nonuniform` / `_render_fields` close a nonuniform list with `);`, but
`reader._nonuniform_body` requires a bare `)`. **Consequences:**
`backend._initial_frame` / `_initial_frame3d` silently skip the t = 0 frame for chamber
and profile stages, and `_time_is_whole` fails on such a start dir. Found by
hd1-wall-load A3 (see `docs/batches/2026-09-24-hd1-wall-load.*.md`), which worked
around it locally in `_e2e_vent_wall.read_start`.

**Decision (owner, 2026-09-25): fix the reader.** `reader._nonuniform_body` accepts both
`)` and `);`. Both are valid OpenFOAM, and OpenFOAM already reads the writer's `);`. The
writer and its goldens stay byte-identical. Add a test that writes a chamber / profile
`0/` field with `writer`, reads it with `reader`, and checks the t = 0 frame is present.
Once the reader handles it, remove the local workaround in
`_e2e_vent_wall.read_start`. Qt GUI QA: the player now shows frame 0 for a chamber and
a chained (1D → 2D) run.

### P1-8 · The GUI turns AMR on with the stale 0.4/0.2 thresholds · **owner decision 2026-09-25**

`models/case.py:135-149` re-tuned the defaults to `amr_refine`/`amr_unrefine` =
0.2/0.1 on 2026-09-10 (sweep: 0.4/0.2 gave -11.8 % gauge error, 0.2/0.1 gave -3.9 %).
The old 0.4/0.2 is still used in `ui/setup_spec.py:118-119`, `gui/forms.py:505-506`, the
AMR-off / `set_case` fallback in `models/fields.py`, and the `getattr` fallback in
`core/refine.py:1053-1054`. A GUI user who switches AMR on gets ~12 % gauge error.
Also, loading a case with AMR off rewrites its AMR fields (`native_2d_small.json`:
`densityGradient` → `Lohner`, 0.2/0.1 → 0.4/0.2), so a file saved from the GUI no longer
matches the one loaded. Source: `docs/ENGINEERING_QUESTIONS.md`, phase 5a #1-#2.

**Decision (owner):**
1. One source: every place above reads the defaults from the constants in
   `models/case.py` (0.2/0.1, `Lohner`). No literal thresholds left in `ui/`, `gui/`,
   `models/fields.py` or `core/refine.py`.
2. A form that loads a case with AMR off keeps the case's AMR fields and saves them back
   unchanged.

Acceptance: a grep finds no `0.4`/`0.2` AMR literal outside `models/case.py`; a
load→save round trip of `native_2d_small.json` through both forms is identical in its
AMR fields; `test_regression.py` stays byte-identical (AMR is off in every baseline,
so confirm this rather than assume it); the phase 5a characterisation test that pins
0.4/0.2 is updated **as part of this owner decision** (§9); Qt and Tk GUI QA.

### P1-9 · The charge field is the material's mass, but everything says "kg TNT" · **owner decision 2026-09-25**

`core/case.py:494-498` sizes the charge with the selected material's `rho0`, so the
field is the **material mass**. Yet the form (`setup_spec.py:371,384,459,462`), the
figure titles (`output/plots.charge_label`, `plots.py:56-57`) and the report say
"kg TNT". The native form always sends `'TNT'` (`case_form.py:468/506`), against the
comment at `core/case.py:548-566`. The preview circle uses TNT density
(`output/preview_draw.py:117`, `viz3d/geometry.py:54`; ANFO's radius is 24 % larger).
No gauge table shows Z. blastFoam 1D meta hard-codes `eos='JWL'` and titles never
name the material. Source: `docs/ENGINEERING_QUESTIONS.md` UX E1/E2/E5, architecture
#2, phase 8 #1-#2.

**Decision (owner):** the field stays the material mass.
1. Labels say "kg ‹material›" (e.g. "5 kg ANFO"; "kg/m" in planar 2D) everywhere:
   form, figure titles, report, 1D meta titles. Tk and Qt both.
2. The preview (2D and 3D) sizes the charge with the material's `rho0`.
3. TNT equivalence per UFC 3-340-02 §2-9 **Eq. 2-1**, W_E = (H_d^EXP / H_d^TNT) ·
   W_EXP, with H_d from **Table 2-1** (printed p. 311, `docs/references/ufc_3_340_02.pdf`).
   Read the values off the PDF page itself, add an `h_d` field (with the table cited) to
   each row of `core/materials.py`, and list any material Table 2-1 does not carry, for
   the owner. Eq. 2-1 is for unconfined shock effects only (§2-9, last paragraph); say so
   next to the number.
4. The gauge table and the report gain a Z column computed with W_E. The KB comparison
   uses W_E too.
5. Native mode hides the material choice (TNT only), and the `core/case.py:548-566`
   comment is corrected to match. No native number moves.

Acceptance: no "kg TNT" string is left except for a TNT case; `test_regression.py` is
byte-identical; for TNT, W_E = W and Z matches R/W^(1/3); Qt and Tk GUI QA with an ANFO
case (label, preview radius, Z).

### P1-10 · The report compares a ground burst with free-air KB · **owner decision 2026-09-25**

`output/report.py:96-124` `kb_rows` compares gauge peaks with `KB_FREE_AIR`. It skips
obstacles, extra charges and planar 2D, but never looks at the boundary conditions. So
an axisymmetric case with `y_lo='reflect'`, or a 3D case with a reflecting side near
the charge, sets a reflected or Mach-stem peak against a free-air one, and the ratio
reads as a solver error. Source: `docs/ENGINEERING_QUESTIONS.md`, phase 6 #1.

**Decision (owner):** classify the geometry and compare only against the matching curve.
1. **Free air** (no reflecting boundary within reach of the charge): KB free-air, UFC
   3-340-02 Figure 2-7, as today.
2. **Charge on the ground** (centre within ~1 charge radius of a reflecting boundary):
   KB hemispherical surface burst, UFC 3-340-02 **Figure 2-15** (text sidecar line
   ~7041; read the values off the PDF page). `test_foam_kb_anchor.py` already carries a
   10 kg hemispherical table; take it from there or from the figure, and cite which.
3. **Elevated HOB, or anything else**: no comparison. The report prints one line
   saying why. The HOB / Mach-region curves (Figs 2-9 to 2-13) are a separate item,
   on request.
4. W is W_E from `P1-9`. Pre-register the "on the ground" distance rule, in charge
   radii, in the code comment before any case is judged by it.

Acceptance: free-air cases give byte-identical report rows; an axisymmetric
`y_lo='reflect'` surface-burst case is compared with Fig. 2-15; an elevated-HOB case
prints the skip line; a planar 2D case is unchanged.

### P1-11 · HD 1.3 inputs: a typo, a blank and an explicit 0 all become the default silently · **owner decision 2026-09-25**

`models/case.py` (blast cases) refuses unknown keys, but `models/hd13_case.case_from_dict`
drops them and never checks `version`. A misspelled wall or vent field gives an
assessment of a different case with no warning. In the HD 1.3 form, a blank Samples
or Cohorts box is an error (`'Samples' is not an integer: ''`) although the code's
`or 1000` / `or 1` suggests a default. Meanwhile an explicit 0 in discharge coefficient,
wall temperature, collapse rotation, cohorts or samples silently becomes the default.
Source: `docs/ENGINEERING_QUESTIONS.md` phase 2 #1, phase 5a #4, UX E4.

**Decision (owner):**
1. The HD 1.3 reader refuses unknown keys as the blast reader does. The error names the
   field and suggests the closest known one (difflib). `version` is checked.
2. **Blank means default; an explicit 0 means 0**, or a validation error naming the
   field if 0 is not physical. No `x or default` on a value the user typed. Qt and Tk
   forms both.
3. The HTML report and the CLI print the value **actually used** for every
   defaultable field, marked "(default)" where it was not given.
4. First load every HD 1.3 JSON in the repo (the starter case, `docs/hd13/`, test
   fixtures) under the new reader. Any that fails is a real typo: record it and fix the
   file, not the reader.

Acceptance: a typo'd key raises with the suggestion; a blank Samples box runs with 1000;
Cd = 0 is refused, not replaced; the report shows used values; `test_regression.py`
and the HD 1.3 characterisation tests are unchanged for valid inputs; Qt and Tk GUI QA.

### P1-12 · The user sets the write interval, and sees the disk it will take · **owner decision 2026-09-25**

Today the writer picks the interval itself (the adaptive controller, clamp
[interval0/4, 8·interval0]), and it cannot hold its own band: HD1-3d made **748 writes,
172.96 GiB** in 30 ms. `HD1-15`'s `write_budget` fixes the count, but it defaults to 0,
is not in the GUI, and the Qt form drops it on save. A write is a full OpenFOAM time
directory (every field in every cell, ~130 MB per write in 3D, kept reconstructed and
decomposed). Gauge histories are written every step and do **not** depend on it.
Animation frames, resume points, chain hand-off and whole-field traces (plane-max) do.
Source: `docs/ENGINEERING_QUESTIONS.md` hd1-3d-close #2, hd1-wall-load #8, phase 3 #4.

**Decision (owner):** the run setup takes the write interval as an input, in one of two
modes chosen by the user:
- **every N time steps**, written as `writeControl timeStep; writeInterval N;`
- **every Δt seconds**, written as `writeControl adjustableRunTime; writeInterval Δt;`

Next to the field, the form shows a live **estimate**: number of writes and disk in GB.
- by time: n = end_time / Δt;
- by steps: n = (end_time / Δt_est) / N, with Δt_est from the CFL condition
  (CFL · dx_min / (|u| + c) at the expected peak). Label it as an estimate, because
  the step is adaptive;
- disk ≈ n × cells × `BYTES_PER_CELL_WRITE` (155 B, measured HD1-3d), × 2 when the
  decomposed copies are kept; for AMR use the max cell count. Resolve the "~60 B per
  cell" AMR note against 155 (phase 3 #4) first.
- Warn above a threshold (proposed 50 GB; owner to confirm).

Details for the implementer:
1. Qt and Tk forms both (§9), blastFoam mode only (hidden, not greyed, in native). The
   value is saved in the case JSON and survives load→save.
2. The GUI default is an interval that gives ~60 writes (end_time / 60). A headless
   case that does not set it keeps today's behaviour, so the goldens and
   `test_regression.py` stay byte-identical.
3. When the user sets an interval, the adaptive controller and `write_budget` are off
   for that run. Keep `write_budget` for headless use. `write_budget_of` returns 0 for
   anything that is not a positive whole number (hd1-wall-load #8), with one new test.
4. The live view / 3D viewer / plane-max traces sample at writes. Say so in the field's
   tooltip.
5. Ref: blastFoam user guide, `controlDict` `writeControl` (check the section in
   `docs/references/INDEX.md` and cite it).

Acceptance: both modes render the right `controlDict` lines (writer test); a 3D case at
Δt = end_time/60 makes 60 ± 1 writes in a real WSL run, and its disk agrees with the
estimate within 25 %; the estimate updates as the fields change; Qt and Tk GUI QA.

### P1-14 · The material table against its primary source · **owner decision 2026-09-25: must be 100 % sourced**

**Source found and read, 2026-09-25:** Dobratz & Crawford, *LLNL Explosives Handbook*,
UCRL-52997 (1985), **Table 8-7**, pp. 8-22 / 8-23. The PDF is at
`https://archive.org/download/LLNLExplosivesHandbook/LLNL%20Explosives%20Handbook.pdf`
(PDF pages 229-230). Values were read off the page **images**, not the OCR text layer.
Units there: ρ0 g/cm³, P and A/B/C Mbar, D cm/µs, E0 Mbar·cm³/cm³ (= 100 GPa, per
unit volume, so e0 [J/kg] = E0 / ρ0). Footnote b = "estimated quantities".

| Row | Field | `core/materials.py` | LLNL Table 8-7 | Gap |
|---|---|---|---|---|
| TNT | all 9 | - | 1.630 / 0.210 / 0.693 / 0.07 / 3.712 / 0.03231 / 4.15 / 0.95 / 0.30 | **matches** |
| C4 | e0 | 5.56e6 | E0 0.090 → 9.0e9 / 1601 = **5.62e6** | -1.1 % |
| C4 | other 8 | - | 1.601 / 0.280 / 0.8193 / 6.0977 / 0.1295 / 4.5 / 1.4 / 0.25 | matches |
| HMX | ρ0, D | 1890, 9100 | 1.891, 0.911 | -0.05 %, -0.1 % |
| HMX | e0 | 5.50e6 | E0 0.1050 → 1.05e10 / 1891 = **5.553e6** | -1.0 % |
| HMX | Pcj | 3.9e10 | 0.420ᵇ (estimated) → 4.2e10 | -7 % |
| HMX | A, B, R1, R2, ω | - | 7.783 / 0.07071 / 4.20 / 1.00 / 0.30 | matches |
| PETN (ρ0 1.770) | D | 8400 | 0.830 → **8300** | +1.2 % |
| PETN | e0 | 5.81e6 | E0 0.1010 → 1.01e10 / 1770 = **5.706e6** | +1.8 % |
| PETN | Pcj | 3.1e10 | 0.335 → 3.35e10 | -7 % |
| PETN | A, B, R1, R2, ω | - | 6.170 / 0.16926 / 4.40 / 1.20 / 0.25 | matches (B rounded) |
| **RDX** | all | *(removed 2026-09-26)* | **not in Table 8-7** | removed, see 2 |
| **ANFO** | all | A 4.95e10, B 1.89e9, R1 3.90 ... | **not in Table 8-7** | unsourced |

**Decision (owner):** every row must trace to a primary source, value for value.
1. The rows LLNL carries (TNT, C4, HMX, PETN) take **exactly** the Table 8-7 values,
   with the table and page cited per row. C4's `E0` comment (9.0e9) was the handbook's
   number, and it is `e0` that was off.
2. **RDX and ANFO: owner-gated. Do not search, choose or change these rows without
   an explicit owner decision** (owner, 2026-09-25). No agent picks a source. Candidates
   may be listed for the owner, but the owner chooses. ANFO is non-ideal: its JWL
   depends on diameter and density, so the choice is an engineering one. Until the owner
   decides, the row is marked **unsourced** in the code and in the GUI list, and its
   values stay as they are.
   - **RDX: ✅ removed, owner 2026-09-26.** No primary source found a cylinder-test JWL
     set for *pure* RDX: LLNL Table 8-7 and Lee, Hornig & Kury 1968 (UCRL-50422) give
     only Comp B / cyclotol; Liu et al., *FirePhysChem* 6 (2026) 51-60, Table 1 gives
     only aluminised / waxed RDX, KHT-computed. The old row was HMX's with ρ0 1770.
     C4 (91 % RDX) stays. `core/materials.REMOVED` makes a saved RDX case fail
     validation with the reason. ConWep (heats only) and the Viper theory manual (no
     material data) were checked and carry nothing usable.
   - **ANFO: source chosen, owner 2026-09-26, not yet applied.** The owner accepts the
     blastFoam 6.2.0 set in `validation/blastFoam/rateStick/*/constant/phaseProperties`,
     which cites Souers et al. (2000), *JWL++* (and Guilkey et al. 2007): products
     **JWLC** A 2.9867e11, B 4.11706e9, R1 4.95, R2 1.15, C 7.206147e8, ω 0.35,
     ρ0 1160; E0 4.0e9 J/m³ (e0 ≈ 3.45 MJ/kg); reactants Murnaghan n 7.4, κ 3.9e11,
     Γ 0.35. Open before applying: (a) it is **JWLC** (a `C` term), not the table's JWL,
     so `Material`, the writer and the native EOS need the C term or a documented
     reason to drop it; (b) it has **no D and no Pcj**; (c) ρ0 1160 against today's
     850. Changing it moves every ANFO result; re-baseline in its own commit.
3. Changing C4 / HMX / PETN moves the results of runs with those materials, but **not
   TNT**, so the KB anchor and every TNT golden stay put. Check whether any golden uses
   another material, and if so re-baseline it in its own commit.
4. *(Done 2026-09-25: the handbook is registered as `llnl-explosives-handbook` in
   `docs/references/INDEX.md`, with Table 8-7 pre-rendered as PNGs.)*
5. Same pass, text fixes: the `Pcj` comment's "~7 % of every row" (ANFO is 14 %), the
   `Afterburn` docstring's "~25 %" (the TNT ratios give 11-15 %, CLAUDE.md §7 says
   ~13 %), the dead "ROADMAP N3" references (the docstring and the report footnote), and
   the AMR "runs in parallel" comments in `services/validation.py` against CLAUDE.md §7
   (serial). Check the code and fix whichever is stale.
6. `blastfoam_toolkit/docs/jwl_parameters.md` gets the same corrections, or a note that
   `core/materials.py` supersedes it.

Source: `docs/ENGINEERING_QUESTIONS.md` architecture #1, phase 1 #1-#2, phase 4 #1,
phase 6 #2.

### P1-16 · Two grid mismatches: validation's cell count, and extra charges in 'zone' mode · **owner decision 2026-09-26, high priority**

**(a) Validation counts a different grid from the one the solver builds.** For the
native 2D case, validation reports dx 0.010542 and 113 × 151 = 17,063 cells (rounded
down). The solver builds 114 × 152 = 17,328 at dx 0.010526. The cell-cap check exists
to stop a `MemoryError` that takes the window down, and it undercounts by ~1.5 % in 2D,
probably more in 3D. **Decision:** validation calls the same grid builder the solver
uses (one source, `core/grid` or wherever the solver's is), in 1D, 2D and 3D, native and
blastFoam. The solvers do not change. Validation messages and the cell-cap verdict may
move slightly: pin the new numbers in the phase 3/4 characterisation tests **as part of
this decision** (§9), with a before/after table.

**(b) Extra charges refine dx when the main charge would not.** In
`services/validation.py` `_validate_refinement`, the main charge skips dx refinement
under `foam and charge_refine == 'zone'`, but extra charges refine dx whenever AMR is
off, even in 'zone' mode. The whole mesh gets finer, and the run more expensive, for
nothing. **Decision:** extra charges follow the main charge's rule. **First verify that
every extra charge gets its own refinement zone** in `setRefinedFieldsDict`
(`solvers/foam/writer.py`). If one does not, add it in the same change, or the charge
ends up under-resolved. Writer test: a two-charge 'zone' case has two zones and the
coarse dx.

Acceptance: validation's reported cell count equals the solver's built count for every
case in `tests/cases/` (a new test); `test_regression.py` byte-identical; a multi-charge
'zone' case gets the main-charge dx and one zone per charge.
Source: `docs/ENGINEERING_QUESTIONS.md` phase 0 #2, phase 4 #2.

### P1-17 · The band varies `n` about 1 Pa, not about where it was measured · **found 2026-09-26, needs owner decision**

`core/sensitivity._perturb` moves `n` and keeps `a` fixed in SI, so it pivots at
p = 1 Pa. At a storage-room 1 MPa, dn = +0.15 then multiplies the burn rate by
(1e6)^0.15 ≈ 7.9. The module docstring (lines 15-18) gives the reason for `n`
dominating as the distance **from where `n` was fitted** (50-300 MPa), which is
about ×1.8 for the same dn, and in the opposite direction: holding the measured rate,
a higher `n` burns **slower** below the window. The band's reported 12.7 spread
probably comes mostly from this. **Nothing changed.** HD1-18 uses the measured-window
pivot (owner, 2026-09-26). Whether the band follows it is open. It moves every band
number and its goldens, so it needs an owner decision and a before/after table first.

### P1-18 · The Qt app cannot open or re-open an HD 1.3 case file · **found 2026-09-26 (QA F1)**

"Open case..." refuses every HD 1.3 JSON, including the `--hd13-new` starter, with "Not
a blastlab case file". "Save case..." on the 0-D form writes a **blast** case
(`schema "blastlab-case"`, version 13, dim 0), which the app then also refuses to open.
The values survive; the schema does not. The cause: `ui/app.py:19` imports only the
blast `load_case` / `save_case`, and `models/case.py:372-377` rejects the HD 1.3
schema and has no dim 0. This was already so at `01ab997`, before HD1-16. The HD 1.3
reader and writer (`models/hd13_case`) round-trip byte-identically at form level, so
the fix is to dispatch on the schema in Open and on the solver mode in Save. Evidence:
`docs/qa/2026-09-26-hd1-16/QA_REPORT.md` F1, screenshots `F1_*`, `F2_reopen_*`.
Acceptance: Open loads the starter and a clearing case into the 0-D form; Save → Open
round-trips byte-identically; blast cases are unchanged; Qt GUI QA.

### P1-15 · The Vieille `a` override has no unit on screen · **owner decision 2026-09-26**

The HD 1.3 form's "Vieille a" override (`ui/setup_spec.py:241`, Tk `gui/case_form.py:184`)
shows no unit. The code expects SI (`core/fuels.py:92`: r in m/s with p in Pa, so `a`
is in m/s/Paⁿ; the report prints `m/s/Pa^n`, `output/hd13.py:109`). Literature quotes `a`
in mm/s/MPaⁿ, and the unit of `a` depends on n. For n = 0.8, 1 mm/s/MPa^0.8 is
1.6e-8 m/s/Pa^0.8, so a pasted literature value is wrong by orders of magnitude with
no warning. Source: `docs/ENGINEERING_QUESTIONS.md` UX E3.

**Decision (owner):**
1. The form takes `a` in **mm/s/MPaⁿ**, labelled "Vieille a [mm/s/MPaⁿ]", in both Qt
   and Tk. It converts to SI internally: a_SI = a · 1e-3 · (1e-6)ⁿ, using the n in
   effect (the override if given, else the table's).
2. Next to the field, a live sanity readout shows the burn rate r at 1 MPa and 10 MPa,
   in mm/s.
3. The case JSON stores it under a unit-named key (`a_mm_s_MPa`). Existing files with
   the old SI key still load, read as SI. Say so in the loader and test it.
4. The report shows `a` in both unit systems.
5. The table values in `core/fuels.py` and the solver stay SI. No number moves for a
   case without an override.

Acceptance: a literature value typed in mm/s/MPaⁿ gives the same assessment as the
same value converted to SI by hand in an old-format JSON; the readout is right for one
worked example; characterisation goldens are unchanged; Qt and Tk GUI QA.

### P1-13 · Arrival is a fixed 1.1 × ambient threshold · **owner decision 2026-09-25**

`output/gauge_summary.py:22-23,53` puts arrival at the first sample above 1.1 × ambient
(~10.13 kPa over), and the positive-phase impulse starts there. A far gauge (Z ≳ 4 for
1 kg) arrives late or `NaN` and gets no impulse. A gradual rise (HD1-3d G1) crosses
1.19 ms after the first disturbance, and the impulse is 1.1-2.1 % low. The CSV does not
say the numbers depend on the threshold. Source: `docs/ENGINEERING_QUESTIONS.md`
hd1-3d-close #6, architecture #4.

**Decision (owner):**
1. Arrival is the first sample above a **fraction of that gauge's own peak
   overpressure** (proposed 5 %; fix the number in the code comment before any output is
   judged by it).
2. The positive phase starts at the last zero crossing of overpressure before arrival,
   i.e. the start of the rise, and ends at the next zero crossing after the peak.
3. The rule is written in the gauge CSV header and in the report.
4. Post-processing only; the solvers are untouched. The byte-pinned gauge summaries that
   move are re-baselined **as part of this owner decision** (§9), in their own commit
   with a before/after table: peak, impulse and arrival for every baseline gauge.

Acceptance: a Z ≈ 6 gauge gets an arrival and a positive impulse; HD1-3d G1's impulse
rises by ~1.1 %; peaks are unchanged everywhere; `test_regression.py` differs only in
the arrival / impulse columns, and the table shows it.

### P1-19 · The Tk process died once in a native 1D→2D chain · **found 2026-09-26 (OUT-1 QA F1)**

1 of 7 Tk chains: after the hand-off, `vtkWin32OpenGLRenderWindow: wglMakeCurrent failed
... error 170` four times, then exit with no Python traceback. The 2D axisymmetric stage
builds a 3D scene inside the Tk process (`gui/app.py _attach_view3d_auto` →
`gui/view3d_panel.py adopt_feed` → `_ensure_scene`). Pre-existing, not OUT-1. Evidence:
`docs/qa/2026-09-26-out-1/tk_timing.out.txt`.

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

### P2-10 · `test_foam_wsl_resume.py` has not run since 2026-09-19 · **found 2026-09-24**

It fails with `AttributeError: 'types.SimpleNamespace' object has no attribute
'init_state'` in `FoamRunLoop.__init__`, identically at `7dd2446` and at HEAD: its stub
spec predates `9b9a039`. **The W3 regression suite has been dark for five days.** That
suite checks the auto-resume after WSL is torn down under a run (CLAUDE.md §8.3).
Fixing it means editing a committed test, so it is the owner's call (§9).

### P2-11 · `test_foam_postmortem.py`: the peak-map check fails deterministically · **found 2026-09-24**

"final peak map within 0.5 %" fails with rel 2.90e-01 (620 against 632 samples),
identically at `7dd2446` and at HEAD. The hd1-wall-load batch is a no-op on that path.
Cause undetermined; two candidates:
- the FO pMax restart loses the state stored at the restart dir;
- the scripted stop has drifted to 0.64 µs, firing after three live-slice frames and
  before the first regular write.

If a resumed run's peak map is really wrong, this is P1.

### P2-13 · Four broken or toothless committed tests · **owner decision 2026-09-26: edit permitted**

**The owner explicitly permits editing these four committed tests (§9), and only
these.** The rule is: **fix the test's mechanism, never its threshold or its expected
value.** One commit per test, each citing this decision.
1. **`P2-10`** `test_foam_wsl_resume.py`: complete the stub spec (`init_state` and
   anything else `FoamRunLoop.__init__` now needs). Run it for real in WSL (§8.6 first).
2. **`P2-11`** `test_foam_postmortem.py`: **find the cause of 620 vs 632 first.** If
   it is a code bug, fix the code and leave the test alone, and it is P1 if a resumed
   run's peak map is wrong. If the test itself is wrong, **stop and bring the evidence to
   the owner** before changing it.
3. `test_vent_wall.py`: `test_evidence` / `test_tails` / `test_step2_driver` take
   arguments, so pytest reports 3 "fixture not found" errors. Rename the helpers or
   give them fixtures so pytest collects only real tests, with the same checks.
4. `test_refine.py`: `check()` only appends to a list, so its 10 pytest functions
   cannot fail. Make a failing check fail, both under pytest and as a script. **Any
   real failure this uncovers is reported to the owner as a finding.** Do not loosen it
   to pass.

Source: `docs/ENGINEERING_QUESTIONS.md` hd1-wall-load #3, phase 0 #4.

### P2-14 · Code hygiene: small silent failures · **owner decision 2026-09-26**

No number a user sees should move. `test_regression.py` stays byte-identical, and the
validation dump over ~100 cases (phase 4) is compared before and after.

1. **A negative charge breaks the 2D preview** (`core/refine.py:115` `effective_dx`,
   from `ui/setup_panel.py:264`: a complex radius, swallowed by the event loop).
   The radius function raises `ValueError` for mass ≤ 0. The preview catches it, draws
   no charge and says "invalid charge mass". Validation already refuses the run.
2. **A profile-initialised 2D case with `charge=None` cannot be read back** (`set_case`
   writes `''`, and `get_case` refuses it). With profile initialisation the charge row
   is hidden (mode-aware, as elsewhere) and a blank reads as `None`. In every other
   mode a blank is still an error. Qt and Tk.
3. **The ambient sound speed is defined four times** (`validate_case` 1D and 2D/3D
   recompute `sqrt(1.4*101325/1.225)`; the fixed-dt Courant check hard-codes
   `2.0*340.3` and says "~680 m/s"). All read `C_AMB_AIR`, and the message formats it.
   Confirm with the validation dump that no warning flips.
4. **Charge radius: one function, no TNT fallback.** Use the one in `core/materials.py`
   everywhere (`services/validation._charge_radius`, `_validate_1d`'s own copy,
   `core/case.py:494`, `core/refine.py:120`). `rho0` is required, and the result is always
   a Python `float` (the planar branch returned `np.float64`). `models` `material_rho0`
   catches only `KeyError`, so a broken import fails loudly.
5. **The "Charge cells" note vanishes** when `set_mass_fraction` raises. Show
   "Charge cells: could not compute (‹error›)" instead.
6. `DecomposedPurge.run` logs "retrying at the next poll" after a failed final sweep, but
   no poll follows. Say "final sweep failed; decomposed copies left at ‹paths›".
7. `read_probes` aligns U and rho with p by row count. Align by the time column, and
   raise if the times differ.
8. `_e2e_foam_write_budget.du_sb`: use `env.WSL_DISTRO`, `stdin=DEVNULL`,
   `CREATE_NO_WINDOW`, and check `returncode` before parsing. Rerun it in WSL (§8.6).
9. `_e2e_vent_3d.evaluate` `traces[0]` raises `IndexError` on a run with no probes.
   **Do not edit the frozen C6-C13 block.** Check before calling it, and raise
   "run has no probes".
10. *(No separate action: the `4 × n_snapshots` warning that ignores the clamp, and the Qt
    form dropping `write_budget`, are resolved by `P1-12`.)*

Source: `docs/ENGINEERING_QUESTIONS.md` phase 5a #3, #5; phase 3 #1, #2, #3, #5;
phase 4 #3; phase 2 #2; architecture #3; hd1-wall-load #8; hd1-3d-close #8.

### P2-15 · Notes on the HD1-3d / HD1-13 record · **owner decision 2026-09-26, docs only**

Add to the records in `DONE.md` §0 (and their batch reports if they cite the same). **No
criterion is re-judged.** C1-C13 were registered before the run and stand as judged.
- **a. C8's scope.** State exactly what it checks and what it does not: G1 only, only
  after t_peak + 4 ms, only at half the peak. It does not look at G1's second rise
  (8.8 ms after arrival), and `x_hi` is 2 m behind G1. Point to the full traces in
  `docs/hd13/vent3d_gauges_3d.txt`.
- **b. Step 2's first attempt.** One line: attempt 1 aborted at t = 0, before any plane
  number existed, because of `P1-7`. The rerun after `53f87ad` changed no rule or
  threshold, and the verifier judged it legitimate.
- **c.** "~141.7 MB each" for the decomposed copies becomes the measured per-write mean,
  ~117.6 MB (corrected 2026-09-26).
- **d. The `writeInterval` judgement is accepted by the owner (2026-09-26).** The
  run's controlDict differs from a fresh render only in `writeInterval`, which is the
  runner's own run-time rewrite (`runner.rewrite_control_entry`, the adaptive 8×
  ceiling). Applying the runner's `sed` reproduces the run's file byte for byte, so it is
  the same case.
- **e.** Commit `1c9b238` gives the wrong cause for the disk use (snapshots). The
  correct one is in `3798cec` and `P1-12`.

Source: `docs/ENGINEERING_QUESTIONS.md` hd1-3d-close #1 (C10), #4, #7, #8;
hd1-wall-load #2.

### P2-16 · Tk: one `root.update()` runs 10-13 s in a chain's later stage · **found 2026-09-26 (OUT-1 QA §6)**

The live-slice matplotlib redraw keeps queueing work (`gui/run_panel.py:712` →
`mpl.py:104`), so the call does not return. The window stays responsive (WM_NULL
≤ 1.3 s): a stall of one call, not a freeze.

### P2-17 · Resume and the run browser do not know the model · **found 2026-09-26 (OUT-1 QA C2)**

A resume writes to whatever the Model box says; the run browser never shows a run's
model; after a resume the original model's manifest still says its scratch was kept.

### P2-18 · Qt: Run chain during HD 1.3, and dialogs that break paths · **found 2026-09-26 (OUT-1 QA V1, V4)**

Run chain stays enabled during an HD 1.3 assessment and its refusal is titled "Run". The
Qt refusal and overwrite dialogs break a path after "C:".

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

**Architecture** *(owner decision 2026-09-26, during `OUT-1`)*

- `P3-26` **A command-line layer outside `solvers/`.** `solvers/foam/cli_run.py` and the
  prompt flows in `cli.py` are command-line code that lives in the solver layer, so
  `test_layering` (solvers must not import services) forces the model folder to reach
  them through a registration hook (`jobs.register_stage_folder`, `OUT-1` Steps 3 and 8).
  The owner chose the hook for now and **the proper fix as a task**: move the
  command-line flows into a `cli/` (or `output/`) layer that may import `services/`,
  delete the hook, and leave `test_layering` untouched. Do it after the `OUT` track;
  byte-identity of `test_regression.py` and the `legacy/` pins are the gates.

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
`%APPDATA%\blastlab\settings.json`. **But under the Microsoft Store Python the app
reads a virtualised copy of that file, not this one**, and the P0 check above
deletes rather than checks. See `docs/ENGINEERING_QUESTIONS.md` (2026-09-24,
hd1-3d-close #3).

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
| P4-2 | What to delete from disk | Not urgent — superseded by `OUT-5` |
| **OUT-5** | The six decisions on the WSL disk rebuild — [docs/wsl-disk-reclaim-plan.md §3](docs/wsl-disk-reclaim-plan.md) | Keep the evidence run as a skeleton, delete the 193 GB and 54 GB runs, keep the tar until the rebuilt install has solved once; decide after `OUT-2` is accepted |

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
python test_vent3d_load.py        # HD1-3d: judging a finished 3-D vent run from its probes
python test_wallload.py           # HD1-13: reflected front + compressible stagnation at a point
python test_vent_wall.py          # HD1-13: the wall-load rule, Step 1 and Step 2's pure parts
python test_write_budget.py       # HD1-15: the write budget and the decomposed-copy purge
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
