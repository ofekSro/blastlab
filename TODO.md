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

**Three exceptions sit above P0, in this order: `GUI`, `OUT`, then `HD1`.** All are
owner directives (2026-09-28, 2026-09-26 and 2026-09-20) and are not part of the P
ranking.

---

## GUI · ⭐ Highest priority (owner, 2026-09-28) — the redesigned Qt GUI

**The whole specification, approved screen by screen on 2026-09-28, is
[docs/gui-redesign-plan.md](docs/gui-redesign-plan.md)**, with the design boards in
[docs/design/gui-redesign/boards/](docs/design/gui-redesign/boards/). This entry only
orders it; every rule, value and acceptance criterion lives there. Qt only
(`blastlab/ui/`): the Tk app, the solvers, the defaults and every file format stay as
they are. Owner: *"implement everything"*, then run the QA and UX agents on the result.

> **▶ RESUME HERE — the first thing to do from this list.** Branch `master`
> (`gui-redesign` merged in on 2026-10-04, `58911bd`);
> GUI-1..14 done (GUI-14 2026-10-11, branch `gui-14`; DONE.md §0x). Next, in order:
> 1. **`GUI-15`** — what GUI-14's QA/UX left (row below).
> 2. **Office machine:** `blastlab/tests/_e2e_ui_chain_foam.py` ran 2026-10-11: stages 1-2
>    pass, but stage 3 gets no `t_end`, so the app's default `endTime` 29.6 ms (vs a 0.187 ms
>    hand-off) outlives 1800 s on any machine (3.25 ms in 29 min) — give stage 3 a short
>    `t_end` (committed test; owner approved 2026-10-11). Harness F07 (over the home VM's cell cap),
>    `_e2e_ui_view3d.py` (F6). `pgrep -a blastFoam` empty first.
>
> The owner reviewed the open calls on 2026-10-03 and 2026-10-04 ("approve all"):
> [docs/gui-redesign-decisions.md](docs/gui-redesign-decisions.md) § Owner review.
> F1: an agent once ran a broad `taskkill`.
>
> Run agents on Opus 5.5 (`model: "opus"`) if Fable 5 credits run out, as happened on
> 2026-09-29. Heavy suites one at a time: the home PC has 8 GB RAM, and the machine
> GUI-11e ran on (2026-10-04) 15.7 GB with C: nearly full, so test temp files went to D:.

| Id | What | Size | Order |
|---|---|---|---|
| `GUI-1..13` | ✅ all done 2026-09-29 … 10-05 (DONE.md §0l-§0w); the closed rows are in [docs/history/todo-closed.md](docs/history/todo-closed.md) | – | – |
| `GUI-14` | ✅ 2026-10-11 (a)-(i), DONE.md §0x; **(j) still open** (home PC). Original row: **Left by GUI-13** (2026-10-05; `docs/qa/2026-10-05-gui-13-ux.md` F1-F6, `docs/qa/2026-10-05-gui-13-qa/` #1-4, `…-gui-13-backlog-A.verify.md`) — (a) **owner call:** A1 skipped (4 m box over the unprobed cap); recommended: keep Lz 1.5 m and re-record `char_golden/ui_chain_wiring.json` (3 × `radius_m` 10.0 → 1.5) so the 1D radius seed lands; (b) Tk Gauges column still cut at 1100 px (`gui/results_panel.py:281-284`, minwidth 250 < ~287 needed; QA #1, UX F6); (c) Where column can name a different wall than Checks when two walls are within a cell (UX F2); (d) dropped gauge not marked where gauges are edited — warn colour on the cells and the Gauges tree node (F3); (e) Run card header: drop `selected`, elide right, Z unit (F4); (f) Results drop line in the warn style, as on Run (F5); (g) solver logs still say `Gauge (x, y) inside an obstacle` without `G<n>` (`solver2d.py:284,289`, `solver3d.py:342`; 3 tests pin it); (h) `test_ui_status_cells` S2 flaky (fixed `pump(600)`, poll instead); (i) harness `latest_out()` picks folders by name — sort by mtime; (j) home PC: HD13 char drift, carried from GUI-13 (i). Low items parked in the UX report §6 | M | 14 |
| `GUI-15` | **Left by GUI-14** (2026-10-11; `docs/qa/2026-10-11-gui-14-ux.md` F1-F6, `docs/qa/2026-10-11-gui-14-qa/QA_REPORT.md` F1, `…-gui-14-backlog-B.verify.md`) — **owner 2026-10-11: all approved**, incl. the (b)/(g) pin edits and (d)'s wording — (a) Run: from Start to the first gauge data a dropped gauge is an ordinary `waiting` row, can be the enlarged card, and its header can name another wall than Setup (UX F1); (b) the native log names no wall (`inside an obstacle`) and says "inside" for a gauge Setup calls "in front"; the solver has the obstacle list (UX F2; pin edit needs the owner); (c) Results on blastFoam runs says `inside Wall n` where Run said `on the face of` — the meta stores the face-snapped walls (UX F3); (d) Setup: Checks `on the face of Wall 1` vs Where `3 cm behind Wall 1 (dropped)` on one row; proposed `within a cell of Wall n`, wording is the owner's (UX F4); (e) the Gauges node turns warn but its caption and children do not name the gauge; a chain stage has no gauge table (UX F5); (f) 1D: a gauge beyond the radius is dropped silently — no Checks warning, no log, Results renumbers (`solver1d.py:146`, `foam/writer.py:445`; UX F6 = QA F1; the 1.5 m chain seed makes it easier to hit); (g) owner approval: `_e2e_gui_native_warn.py:63-64` can no longer fail (old `Gauge (` text) — pin `G1 (0.30, 0.80) m`; add a fast 2D/3D solver-log pin; (h) `_qa_ui_harness`'s F group switches to blastFoam despite `--solver native` and ran WSL solves (GUI-14 QA) — make it respect the flag; its F05/F06 blastFoam runs died with exit 134 under AMR (perhaps P1-23, unverified). Low items parked in both reports | M | 15 |

---

## OUT · ⭐ Highest priority (owner, 2026-09-26) — model folder, VTK output, disk

**The whole plan, approved on 2026-09-26, is
[docs/model-folder-and-vtk-plan.md](docs/model-folder-and-vtk-plan.md).** This
entry only orders it; the specification, the decisions and every acceptance
criterion live there. Owner's words: first the VTK export; once it works, is
fixed and approved — the disk.

| Id | What | Order |
|---|---|---|
| `OUT-1..5` | ✅ all done 2026-09-26 … 09-28 (DONE.md §0c-§0k); the closed rows are in [docs/history/todo-closed.md](docs/history/todo-closed.md) | – |

---

## HD1 · ⭐ Owner directive 2026-09-20 (second to `OUT` since 2026-09-26) — HD1.3 effects on a structure

**What was asked:** compute the effects of an **HD1.3 — non-detonating** material
on a structure. HD1.3 is deflagration (Vieille `r = a·p^n`), not detonation, so it is a
new track, not a parameter; "equivalent TNT" gives an impulsive load where the real one
is quasi-static. The background text and the table of the three loads (fireball, QSP,
venting) are in [docs/history/todo-closed.md](docs/history/todo-closed.md) (2026-10-05).

### Status

Open on HD1: `HD1-16` step 2, `HD1-17` (b), `HD1-18`, `HD1-19`, `HD1-14`, `HD1-4`, and
closed-vessel data (no code). The 2026-09-21/24 status record and the three
silent-failure bugs are in [docs/history/todo-closed.md](docs/history/todo-closed.md).

### `HD1-16` · No SDOF in the app — export the wall load for SBEDS · **owner decision 2026-09-25**

**Decision (owner):** blastlab gives the load, not the structural response. The
response is solved outside, in SBEDS. Replaces two open questions in
`docs/ENGINEERING_QUESTIONS.md`: phase 0 #1 (the band's ends bracket everything but
the nominal μ, 0.0509 / 0.1049 against 0.1164) and hd1-wall-load #1 (the envelope
gives a lower μ than G1 alone). Both come from judging the response at the ends of
the *load*. With no SDOF in the app, both close. The worst case is found in SBEDS
over every exported trace.

**Step 1 is ✅ closed 2026-09-26** — [DONE.md](DONE.md) §0b.

**Step 2 (after the owner has run one case through SBEDS):** delete `core/sdof.py`,
`structural_verdict` and their tests. Mark the μ values in the HD1-3d / HD1-13
records (C10's "survives") as historical, produced by the removed in-app SDOF.

### `HD1-17` · The HD 1.3 starter case is a weak check, and two texts overstate · **owner decision 2026-09-25**

Both report flags are **correct as coded**: "blast negligible: False" at Mach 0.0917
is above `MACH_QUASI_STATIC = 0.05` (`core/unconfined.py:85`), and "the whole burn
outside the calibration window" is the real HD1-3 limitation (a burn law measured in
a closed vessel at tens-hundreds of MPa, applied at ~0.1 MPa). What is wrong is
around them. Source: `docs/ENGINEERING_QUESTIONS.md` phase 7 #1-#2, phase 0 #3.

**(a) Texts: ✅ closed 2026-09-26** — [DONE.md](DONE.md) §0b.

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

### `HD1-19` · Three honesty gaps in `core/vent.py` · **owner decision 2026-10-04**

Found by the `/neat` proposal for `core/vent.py` (`docs/tidy/blastlab-core-vent.py.md`);
source `docs/ENGINEERING_QUESTIONS.md`, "`/neat` proposal for `core/vent.py`" #1-#3.
Each changes a reported number or text, so none is tidying.

- **(a) Sea-level ambient, stated.** `handoff` ignores its `p_amb` argument and
  `validity` passes a fixed `P_AIR` to `_vent_mdot`. **Owner:** a sea-level ambient is
  an acceptable assumption, but it must be stated in the code (docstrings, and drop or
  document the dead `p_amb`) and in the reports that quote the drain time.
- **(b) The CFD `Cd` is interpolated in 1/N.** It today steps from 0.7227
  to 0.8102 at 9 cells across the opening. **Owner:** interpolate linearly in 1/N (h)
  between the two measured points (in `cfd_point_in_band`), the usual mesh-convergence assumption, and hold the
  end values outside 6-12 cells (no extrapolation from two points). Only the report's
  position-in-band sentence moves; the structural envelope does not. Update the
  comment that `/neat` vent item 5 rewrote. Owner still to check whether the step was
  deliberate before this is implemented.
- **(c) A CFD window past the end of the 0-D record is flagged.** When
  `t_open + t_cfd` is after the last 0-D sample, `validity` silently uses the last
  sample, so `burn_fraction` can read low. **Owner:** no extrapolation; add a line to
  the validity output and the report that the 0-D record ended first and the burn
  fraction is a lower bound.

Acceptance: each with a test; any golden that moves gets a before/after note (§9).

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

### Deviations, `HD1-12`, the scope decision and `HD1-3` — moved

The HD1 deviations, `HD1-12`, the pyrotechnics scope decision and the next step, `HD1-3` (closed-vessel data for a real material, no code), are in [docs/history/todo-closed.md](docs/history/todo-closed.md).

---

## P0 — Urgent: risk of losing work / broken repo

P0-1, P0-2 and P0-3 closed 2026-09-09 (`e344d17`); P0-4 closed 2026-09-17; P0-5
(settings file in the repo, cleanup off by default) closed 2026-09-27. See
[DONE.md](DONE.md) §0g. No P0 item is open.

> **But P0-4's trap is permanent and worth re-reading before any session that
> matters:** every code path that builds the GUI can delete the run corpus, and
> `_e2e_gui_*` and the QA harnesses build one. Run the dry run from CLAUDE.md §8.2
> (`env.cleanup_plan`, which deletes nothing) and expect `<repo>\settings.json False`,
> and copy out any run you care about. Deletion inside WSL is not reversible.

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

### P1-7 · On-screen check only: the player shows frame 0 · **code fixed 2026-09-27**

The reader fix, its test and the workaround removal are done ([DONE.md](DONE.md) §0g).
Left: Qt GUI QA with a real run (WSL + screen) - the player shows frame 0 for a
chamber and a chained (1D → 2D) run.

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

**Source record** (Table 8-7, pp. 8-22 / 8-23, and the per-row gap table): [docs/verification/material-table-sources.md](docs/verification/material-table-sources.md).

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

### Remap-chain gaps · **found 2026-10-11** · detail: [docs/verification/remap-chain-gaps.md](docs/verification/remap-chain-gaps.md)

- `P1-20` Gauges inside the hand-off radius already saw their peak in the stage before; no warning, no mark in Results, no stitched history.
- `P1-21` 2D→3D burst height: native takes the 2D profile's and refuses ≥ Lz; blastFoam takes the 3D form's z (`burst_points`, timing) and refuses nothing.
- `P1-22` Afterburn across a hand-off: `c.expl` is not carried and stages are not checked to agree. Verify blastFoam's starting `c` first.
- `P3-14` **3D→3D, raised from P3 and expanded (owner 2026-10-11)**: no format, no remap, no 3D final state, and the chain is keyed by dimension. Owner questions in the detail doc §3.

### P1-23 · The default ignition radius uses the global `lmax`, not the level at the charge · **found 2026-10-11**

`writer.default_det_radius` (`N5-7`) returns `0.9 · dx_base / 2**max(lmax, amr)`. Its
docstring says the radius follows the mesh *at the charge*, but `lmax` is the deepest
zone anywhere. When the charge sits in a shallower zone the radius falls below the
0.707 · dx corner distance and blastFoam aborts at t = 0 with `No cells will be
activated using the detonation point`. Hit three times on 2026-10-11
(`/root/blastlab_runs/20261011-08*_2d_p61324-0*`): axisymmetric 10 × 10 m, 100 kg C4 at
(0, 0), zones `[0, 7.5, 0, 6, 1]` + `[3.5, 7.5, 0.1, 5.9, 2]` → radius 6.9 mm, nearest
centre 10.8 mm. Validation passes it. Workaround: a small level-`lmax` zone around the
charge.

Fix: take the level from `spec.levels` at each detonation point (the deepest cell
touching it), max with `amr`; check `dx_charge`, which has the same `lmax`
assumption. Validation should refuse an explicit `det_radii` below the corner distance.
Acceptance: the case above runs in serial and parallel; a new `test_foam_writer.py`
case pins the radius for a charge outside the deepest zone; existing fixtures with the
charge in the deepest zone stay byte-identical.

### P1-24 · The native T51 trigger gauge counts only the kept gauges · **found 2026-10-11 (GUI-14 B verify), owner approved the fix 2026-10-11**

`trigger_gauge` indexes the kept list (`solver2d.py:299`, `solver3d.py:359`), though
`hooks.py:60` says it reads like the gauge table; blastFoam uses the gauges as entered
(`foam/backend.py:1785-1814`). Measured: G2 in a wall, trigger 3 → native stops on G4's
point at 0.284 ms instead of G3's at 0.091 ms; `validate_case` says nothing. The live-view
labels (`solver2d.py:337`, `geometry.plane_gauges`) and `meta['trigger_gauge']` shift too.
Fix: carry each gauge's entered number through the native solvers; `_validate_trigger` warns
when the trigger gauge will be dropped. Characterisation test first; changes when a run stops.

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

### The `_e2e_foam_amr2d` accuracy thresholds · **owner decision**

AMR reads **−11.8 % on peak** and **+11.1 % on arrival** against the uniform
reference, on thresholds of 10 %. The impulse passes (+2.9 % of 15 %). **The test
is correct — it measures a real thing:** AMR spreads the front over more cells than
the uniform mesh.

**Decide between:** relaxing both thresholds to 15 % and documenting that as AMR's
accuracy at this configuration, or tightening the test's AMR configuration (more
levels / smaller `amr_interval` / larger `amr_buffer`) until it keeps up.

### N5-12 follow-up · a per-point GUI table for delays/radii

`det_delays` / `det_radii` are wired through the API, the JSON and `validate_case`,
and the activation dropdown is wired in both front ends. **What is missing is the
GUI table**: it changes the data shape of the `det_points` widget and needs a parity
design of its own.

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
Items 1 (`P2-10`), 3, 4 and 5 closed 2026-09-27 - see [DONE.md](DONE.md) §0g. Item 4 is
a `conftest.py` hook for every suite; it uncovered item 6.
2. **`P2-11`** `test_foam_postmortem.py`: **find the cause of 620 vs 632 first.** If
   it is a code bug, fix the code and leave the test alone, and it is P1 if a resumed
   run's peak map is wrong. If the test itself is wrong, **stop and bring the evidence to
   the owner** before changing it.
6. **Finding, 2026-09-27 (OUT-2's test, not edited):** `test_vtk_case.py::test_validation`
   fails under pytest - "two planes the writer cuts on two layers are not refused" - and
   passes as a script. `main()` primes the hardware (8 cores / 512 GB) before calling it,
   and pytest does not, so the case meets the 4 GB fallback cap (CLAUDE.md §4). The check
   was silent under pytest before the item-4 hook. Fix the mechanism (a module fixture that
   primes and restores as `main()` does), not the check. The script gate is green.

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
7. ✅ 2026-09-27 (DONE.md §0g), `read_probes` alignment; text in [docs/history/todo-closed.md](docs/history/todo-closed.md).
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

- `P2-19` Tk at the 1100x720 minimum clips the right column (OUT-2 QA F3; also native) - card widths vs the 13:7 split.
- `P2-20` Tk dimension switch keeps the old scroll offset, form goes blank (OUT-2 QA F4; same on master) - `SetupPanel._swap`.
- `P2-21` Qt 3D form shows a blank tail at the scroll end (OUT-2 QA F5) - the QStackedWidget takes its tallest page's height.
- `P2-22` Validation accepts a detonation point that activates no cell; blastFoam then dies at t = 0 ("No cells will be activated using the detonation point"). Seen in OUT-3 e2e and harness F05.
- `P2-23` A resumed run's gauges lose U: after a restart blastProbes writes only p and rho, so `read_probes` drops U_mag (warns since 25ce709). Pre-existing on master (OUT-3 verifier).
- `P2-24` Qt: the Keep all fields tooltip is one ~1000 px line - wrap it. Tk light mode: unselected sidebar / dimension buttons are very faint (OUT-3 QA).
- `P2-25` Qt: a native result cannot be reopened in 03 Results after a restart, though its files are in the model folder - add `Open a model folder…` to 03 Results (also covers blastFoam runs whose WSL scratch was released). `docs/UX_REVIEW-redesign.md` UXR-14; owner approved as its own item, not GUI-11 (2026-10-03).
- `P2-26` Chain: W and Z lost after the first stage - Z hidden on profile stages; a foam 2D profile stage records the form's stale charge and `from_profile=False`; native records 0 (`P3-10`). Detail: `docs/verification/remap-chain-gaps.md` §4, as for P2-27..30.
- `P2-27` Chain: blastFoam is silent when the hand-off already reaches a boundary, the ground or an obstacle (native warns); `writer.py:1777-1778` claims `validate_case` warns and it does not.
- `P2-28` Chain accuracy coverage: no impulse in `_e2e_foam_chain`; no blastFoam chain-vs-direct test for 2D→3D or 1D→3D; no `profile2d` writer golden.
- `P2-29` 2D→3D remap puts ambient air in the 3D layer below the first 2D cell centre (`core/profiles.py:274-275`) - latent, only when the 3D cells are finer near the ground.
- `P2-30` Hand-off fidelity, measure first: interface cut at alpha 0.5 with `p` recomputed; no source-vs-target mass/energy/momentum check; a 2D AMR source exports at display level.

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
- `P3-14` 3D→3D remap — **moved to P1** ("Remap-chain gaps", owner 2026-10-11).
- `P3-15` Obstacles do not survive the 2D→3D remap — they would become rings around
  the axis, so `save_profile_2d` drops them with a warning only. The 3D stage
  continues a state that evolved around obstacles that are no longer there.
  **Minimum:** raise it to a validation warning in the GUI instead of a stdout print.
- `P3-27` A hemispherical surface burst through the chain (1D→3D / 1D→2D near the ground); the factor is an owner call, cited from UFC 3-340-02. Detail: `docs/verification/remap-chain-gaps.md` §5.
- `P3-28` Several charges with a hand-off: extra charges beside a remapped field, and several 1D hand-offs placed in one 2D/3D stage (one common hand-off time, fields not yet met). Same doc §5.

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
- `P3-7`, `P3-8`, `P3-25` ✅ closed 2026-09-27 (batch `viewer-polish`) — [DONE.md](DONE.md) §0e.

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
Automatic cleanup on GUI start runs only with `auto_cleanup: true` in
`<repo>\settings.json` (P0-5: the file lives in the checkout, git-ignored; every
checkout and worktree has its own). To see what it *would* delete, run the dry run
`env.cleanup_plan` (CLAUDE.md §8.2), never `env.auto_cleanup`, which deletes. In the
OneDrive checkout a sync lock can fail the atomic write in `settings.save()` (the
`P4-1` symptom): it warns once, and the lost `hw_*` cache caps the next headless run
as a 4 GB VM (CLAUDE.md §4).

**The `ext4.vhdx` does not shrink by itself.** Reclaim with `wsl --shutdown` then
`wsl --manage Ubuntu --set-sparse true`.

> The corpus once reached **374 GB and filled C:**. Cleanup is **off by default** since
> 2026-09-27 (owner: deletion inside WSL is final, a full disk is recoverable); it runs
> only when the settings file says `auto_cleanup: true`. With it off, the GUI warns at
> start when the runs root passes `cleanup_max_gb` (150 GB here) and deletes nothing.

---

## Owner decisions waiting for you

| # | The decision | Recommendation |
|---|---|---|
| **HD1-3** | Is there closed-vessel data for a real material? Without it no HD1.3 number can be cited | Get the data — it is the highest-value step and needs no code |
| P1-4 | Afterburn for non-TNT materials — calibrate, or label as uncalibrated | Label; calibrate only if you will cite numbers |
| amr2d | Relax the AMR accuracy thresholds to 15 %, or tighten the test's AMR configuration | Relax and document — the deviation is real AMR behaviour, not a bug |
| decomposition | Leave `scotch`, or investigate a symmetric decomposition for the ±7 % near-field parallel deviation | Leave it. Two cases gave opposite answers and no mechanism explains both. Record: [docs/history/todo-closed.md](docs/history/todo-closed.md) "MPI decomposition breaks x/y symmetry" |
| P4-1 | Move the repository out of OneDrive | Yes |
| P4-2 | What to delete from disk | Not urgent — superseded by `OUT-5` |

---

## Closed items that code comments still cite

These are **done**. They stay named here because comments in the source point at
this file by id, and a reference that resolves to nothing is worse than a long file.

### `N5-7` · ✅ closed 2026-09-20 — `det_radii` is now the default

Cited by `solvers/foam/writer.py:1308` and `tests/test_foam_writer.py:599`.

The body (mechanism, acceptance numbers, the pre-2026-09-20 byte-comparability cost) is
in [docs/history/todo-closed.md](docs/history/todo-closed.md) (2026-10-05). Still open
from it: the residual ≈2 % parallel offset in P1 above.

---

## Standing rules and the test matrix

Moved on 2026-10-04 to [docs/standing-rules-and-tests.md](docs/standing-rules-and-tests.md).
