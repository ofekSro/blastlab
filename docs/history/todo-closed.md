> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [docs/SCOPE.md](../../docs/SCOPE.md)

# TODO — closed track rows

Moved verbatim out of [TODO.md](../../TODO.md) on 2026-10-04 (1000-line cap).

## GUI

| Id | What | Size | Order |
|---|---|---|---|
| `GUI-1` | ✅ done 2026-09-29 (DONE.md §0l) · **Design tokens and fonts** — warm-black palette + light, orange accent, cyan gauges; Space Grotesk / IBM Plex Sans / IBM Plex Mono bundled (OFL). Plan §2 | M | 1 |
| `GUI-2` | ✅ done 2026-09-29 (DONE.md §0l) · **Logo and app icon** — the stepped front on an 8 × 8 grid, drawn with QPainter at 16/32/64; BLASTLAB wordmark; window + taskbar icon. Plan §3 | S | 2 |
| `GUI-3` | ✅ done 2026-09-29 (DONE.md §0m) · **Window frame** — top bar with 01 Setup → 02 Run → 03 Results + Chain, solver chip, case menu (Open / Save / Save as / Recent / Dark), status bar, title with progress, Shift+Esc stop. No sidebar. Plan §4 | L | 3 |
| `GUI-4` | ✅ done 2026-09-29 (DONE.md §0l) · **Shared components** — toggle switch, stat tile, tree row, dock tabs, banner. Plan §2.5 | M | 4 |
| `GUI-5` | ✅ done 2026-09-29 (DONE.md §0n part a, §0o part b) · **01 Setup** — numbered model tree + properties of the selected node + live-number strip, Z rings, gauge table with Z; dependent settings open only when switched on. Plan §5 | L | 5 |
| `GUI-6` | ✅ done 2026-09-29 (DONE.md §0p) · **02 Run** — controls / progress strip with ETA / live view / log dock / live-gauge list sorted by Z; Stop confirms after 30 s; finish banner + Windows notification. Plan §6 | L | 6 |
| `GUI-7` | ✅ done 2026-09-29 (DONE.md §0q) · **03 Results** — results list + "how it was computed"; views Field (= Fields + Animation) · Gauges · 3D; table with Z and Copy; impulse in kPa·ms on screen only; exports grouped. No KB columns, no run overlay. Plan §7 | L | 7 |
| `GUI-8` | ✅ done 2026-09-29 (DONE.md §0m) · **Chain 1D → 3D wiring** — `handoff_1d_to_3d.txt`; the engine already supports it, only `ChainPanel.run()` misses it; with tests. Plan §8.3 | S | 8 |
| `GUI-9` | ✅ done 2026-10-03 (DONE.md §0r) · **Chain screen** — route buttons, pipeline with hand-off files, stage editor in the Setup layout, per-stage live validation, Copy from Setup / Load case; chain strip in Run, one result with stage tabs in Results. Plan §8 | L | 9 |
| `GUI-10` | ✅ done 2026-10-03 (DONE.md §0s) · **QA pass** — harness navigation on the new frame, all 63 scenarios, light mode, 1100 × 720. Plan §10 | M | 10 |
| `GUI-11` | ✅ done 2026-10-04 (DONE.md §0t parts a-d, §0u part e) · **Polish, owner-approved 2026-10-03** (`docs/gui-redesign-decisions.md`, owner-review rows) — (a) D191: `● unsaved` shortens to `●` (tooltip) whenever the case name is elided (D198 does it only when a control would be squeezed); F38: the harness clip check sees tool-button elision, then K02 `--window` again; F36: harness F02/F10 expect the VTK export disabled with its reason; (b) D192: tree-row hover visible in dark, dark `num_dim` at 4.06:1 on hover accepted; (c) F28: clear the previous stage's progress at a stage start, one line in `solvers/worker.py` — own commit, `test_regression` + the Tk suites; (d) F12: at 0-D hide the Run view toolbar, show a 0-D note; (e) F16: keep a case file's hidden-row value (`amr_refine` / `amr_unrefine`), solver defaults untouched; (f) F17: a shorter on-screen 1D figure title, exports byte-identical; (g) P2-18 and P2-24; (h) whatever the `gui-qa-tester` / `gui-ux-reviewer` pass after GUI-10 finds. Plan: `docs/batches/2026-10-03-gui-polish.md` (11a-11d). Owner 2026-10-03: UXR-3 → **hide** the Material row in native mode (not the plan's warning; the hidden-rows pin changes with that reason); UXR-14 → `P2-25`, not here | L | 11 |
| `GUI-12` | ✅ done 2026-10-04 (DONE.md §0v; branch `gui-12`, merged into `master` 2026-10-04) · **Backlog left by GUI-11e** (2026-10-04; `docs/qa/2026-10-04-gui-11e/`, `docs/batches/2026-10-04-gui-11e.verifyA.md`) — (a) QA, medium: the exported gauge-trace subplot titles (`output/plots.py` `figure_gauges_1d` / `_nd`) and the Tk Gauges tab number by survivor index (`Gauge 1/2/3`), not the entered G as the table beside them does (F42's sibling; export bytes change for runs with a drop); (b) UX, medium: the F44 warning names no wall, while Run and Setup's Where column say `Wall 1` (the index is in `_gauge_drop_rule`'s loop); (c) QA, low: the Chain 2D stage's Checks show `inside an obstacle` but not `on an obstacle face` for the case Setup warns on (the stage's auto-refined dx differs); (d) F45: a 2D → 3D reach check (the default chain's burst at z 2.0 m above the 1.5 m box); (e) harness E03 looks for `<file>` where the app writes `save1_<file>` (4 false findings); (f) the stale char goldens red at base `ee9a4b5` (`test_char_exports`, `test_ui_char_results_exports`, `test_gui_char_case_form`, `test_gui_char_exports`; the owner's session also lists `test_char_hd13`, `_cli`, `test_ui_char_case_form`, `_chain_wiring`, `_hd13_run`): check that the HD13 drift (-45.3645 vs -45.3536) is expected, then re-record, owner-approved; (g) low: the nearest-entered pairing can mislabel when two gauges sit within about a cell and the earlier one is dropped (verifyA Q1); the (1.2, 0.3) native face check sits on an exact cell-face tie (Q2); (h) UX, low: the short on-screen 1D title differs from the exported one with no hint; a third title style on Results | M | 12 |
| `GUI-13` | ✅ 2026-10-05, DONE.md §0w. Original row: **Backlog left by GUI-12** (2026-10-04; `docs/qa/2026-10-04-gui-12-ux.md`, `docs/qa/2026-10-04-gui-12-qa/`, `docs/batches/2026-10-04-gui-12-backlog-A.verify.md`) — (a) **owner 2026-10-04: reseed** the default chain's 3D Lz to ≥ stage 2's Ly (≥ 4 m) so it opens without the F45 warning (decision row 2 reopened; own task); still to judge whether "burst ≥ Lz" is the right F45 trigger; (b) UX, medium: F45 wording uses the form labels (`Burst y`, `Lz`), says "at or above", advises Lz ≥ stage 2's Ly (`chain_route.py:234-238`, same y/z at `:413`); (c) UX, medium: the drop warning names the gauge by a raw tuple, not `G<n>` + unit (`validation.py:1565,1575`; edits `test_case_validate`); (d) UX, medium: the gauge export PNG says nothing about the missing numbers - a footnote only when a gauge is dropped; (e) low: `validation.py:1576` names the first containing wall, `scaled_distance.where` the nearest (touching walls only); Where column vs Checks disagree at a face; "outside domain" vs "outside the domain"; (f) low: `test_case_validate` 2D/3D top-face native rows still on exact y/z ties (A6 treatment); (g) QA, low, 1100 × 720: Chain stage 3 / Setup Wall 2 warnings below the fold; Run gauge card header and Results drop caption elided; Tk Gauges table first column truncated; (h) UX, low: the rest of the UX report (#8-#13); (i) home PC: rerun the char suites and compare numpy/scipy - the HD13 -45.3536 vs committed -45.3645 is not reproduced on the work machine (`docs/batches/2026-10-04-gui-12.goldens.md`); do not re-record | M | 13 |

## OUT

| Id | What | Order |
|---|---|---|
| `OUT-1` | ✅ **Model folder** — done and accepted by the owner 2026-09-26 (DONE.md §0c). Plan §2 | 1 |
| `OUT-2` | ✅ **VTK output options** — done and accepted by the owner in ParaView 2026-09-27 (DONE.md §0d, Viper-style layout, P14 closed). Plan §3 | 2 |
| `OUT-5` | ✅ **Reclaim the 481 GB WSL disk** — done 2026-09-27 (DONE.md §0f): vhdx 481 → 8.6 GB. Delete the backup tar after 2026-10-27 (D5). Plan §6 | 3 |
| `OUT-3` | ✅ **Only the newest fields kept in WSL** — done 2026-09-27 (DONE.md §0h); parked Q1-Q7 in the batch plan §6. Plan §4 | 4 |
| `OUT-4` | ✅ **The rest of the Viper matrix** — done 2026-09-28: 4a gauge quantities + dynamic pressure (DONE.md §0i), 4b Peak_Impulse, Obstacle_ID, Time_Of_Peak + F6 (§0j), 4c decimation (§0k). Owner ParaView look at decimated files pending. Plan §5; batch plan `docs/batches/2026-09-28-out-4-viper-matrix.md` | 5 |

## HD1 — the status record of 2026-09-21/24


**The computational track is complete and tested**: `HD1-1`, `HD1-2`, `HD1-2b`,
`HD1-5`, `HD1-6`, `HD1-7`, `HD1-8`, `HD1-9`, `HD1-10`, `HD1-11a`, `HD1-11b` and
`HD1-11c`. A full HD1.3 assessment runs today via
`python -m blastlab --hd13 case.json` — quasi-static pressure, comparison with the
unconfined case, structural response, heat and a report — with no WSL and no Qt.
`HD1-11c` landed on 2026-09-21 and the track is complete end to end, from the GUI
form to the report. Details in [DONE.md](../../DONE.md).

**2026-09-24: `HD1-3`, the venting in blastFoam, is closed** and its record moved to
[DONE.md](../../DONE.md) §0 — the 3-D answer passed all thirteen checks committed before
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

## HD1 — deviations from the plan, and HD1-12


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

### `HD1-12` · ✅ closed 2026-09-21 — moved to [DONE.md](../../DONE.md) §0 on 2026-09-26

## Records moved out of TODO.md on 2026-10-05 (GUI-13 backlog, C1; 1000-line cap)

Moved verbatim. Each has a pointer left in `TODO.md`.

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

### HD1 background: what was asked, and the three loads of 1.3

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

#### The three loads of 1.3, and which belongs to blastFoam

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

### Scope decision — pyrotechnics are out

*(The vent verification that used to sit here closed with `HD1-3`; its record,
`Cd` as the fifth band axis and the ≥ 12-cell rule are in [DONE.md](../../DONE.md) §0.)*

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

### `N5-7` · ✅ closed 2026-09-20 — `det_radii` is now the default (closed body)

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
[docs/verification/blastfoam-claims.md](../verification/blastfoam-claims.md).


## Records moved out of TODO.md on 2026-10-11 (GUI-14 backlog, C2; 1000-line cap)

Moved verbatim. The GUI-13 row is in the GUI table above; the pointers and item 7 follow.

### The pointers that stood in the HD1 block

### Deviations from the HD1 plan, and `HD1-12` — moved

The recorded, unscheduled deviations (`psi`, grain forms, `hooks.Result`), the
`governing_confined` fix and the four-axis band note are in
[docs/history/todo-closed.md](docs/history/todo-closed.md) (2026-10-04).

### Scope decision and the next step — moved

Pyrotechnics are out of scope (owner, 2026-09-21); the record is in
[docs/history/todo-closed.md](docs/history/todo-closed.md) (2026-10-05).

The highest-value next step is closed-vessel data for a real material, no code (`HD1-3`);
its text is in the same file.

### P2-14 item 7

7. ✅ 2026-09-27 ([DONE.md](DONE.md) §0g): `read_probes` aligns by time; on a mismatch
   it keeps p only and warns (owner: never raise).
