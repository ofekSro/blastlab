# OUT-4 · The rest of the Viper matrix: batch plan (2026-09-28)

**Goal:** finish the Viper output matrix on top of OUT-2/OUT-3 (master `6af6a11`).
That means gauge quantities, dynamic pressure, peak impulse, obstacle IDs and volume
decimation. Every addition is opt-in, so default cases, writer goldens and the
native regression stay byte-identical.

Spec: `docs/model-folder-and-vtk-plan.md` §5 (and §3.2, §7, §9). Layout rules:
`docs/batches/2026-09-27-out-2-surface-layout.md` (binding owner decisions 1-6).
TODO entry (verbatim): `OUT-4` | **The rest of the Viper matrix**: gauge quantities,
dynamic pressure, peak impulse, per-obstacle ids, decimation. Mandatory. Plan §5 | 5

References: blastfoam-guide v6.0: sec. 15 intro (p. 122), 15.1 blastProbes (pp. 122-123),
15.2 fieldMinMax (p. 123), 15.5 vtkTimeSeries (p. 124), 15.9 dynamicPressure (p. 125),
15.10-15.12 overpressure / impulse / timeOfArrival (p. 126). The viper-theory manual
was also checked: it has **nothing** on dynamic pressure, peak impulse, obstacle IDs,
arrival time or decimation, so their definitions are owner questions (§6).

## 0. Findings before planning (code vs guide vs plan: report, do not silently change)

| # | Finding | Evidence | Handling |
|---|---|---|---|
| F1 | **`timeOfArrival` is the time of PEAK pressure, not first arrival.** The card tooltip says "Arrival time (first arrival)". The gauge summary's arrival is first arrival at 10 % of peak. | Guide 15.12 p. 126 ("records the time when the maximum pressure is reached"). Source `/root/blastfoam/src/functionObjects/timeOfArrival/timeOfArrival.C` `execute()`: sets the time whenever `p > pMax`. Code: `models/fields.py:161`, `output/gauge_summary.py:23` (`ARRIVAL_FRAC = 0.10`), writer comment N5-9 (`writer.py:917-919`). | Owner Q1. Step B1. |
| F2 | **Peak impulse IS available as a blastFoam field.** Plan §5 says "not a blastFoam field; derived at the end of the run". | Guide 15.2 p. 123: fieldMinMax exists "allowing for quantities such as maximum impulse ... to be visualized", `fields (rho U p impulse)`. Source `fieldMinMax.C:92`: the result is `<field>` + `Max`, so `impulseMax`. The owner's Viper sample has `Peak_Impulse` as an array in every surface file (surface-layout doc, table). | Plan text disagrees with the guide. Recommended: the FO route (exact per step, not limited by cadence). Owner Q2. |
| F3 | The guide does not name dynamicPressure's result field. | Source `dynamicPressure.C:66-68,83`: `fieldExpression` with default result **`dynamicP`**, a **volVectorField** `0.5*rho*mag(U)*U`, `store`d. Keywords `rhoName`, `UName` (guide 15.9). | Documented in the writer's comment. Its magnitude is q (guide eq. 15.1). Owner Q5. |
| F4 | The guide's sec. 15 example writes `libs ("libblastFunctionObject.so")` (singular). The code writes `libblastFunctionObjects.so`. | `writer.py:854`, already verified against `Make/files` (`writer.py:1115-1117`). | Guide typo. No change. |
| F5 | One patch per obstacle (plan §5 "Touches") needs `createPatch` (subsetMesh takes one `-patch`). That contradicts the committed pin `test_foam_chamber.py:259` ("no createPatch ... no new mesh stage") and the design of `core/room.py:14-20`. It would also rename the BC entries in `0/*` of every obstacle case, which means goldens and fixtures to re-pin. | `backend.py:84-91`, `writer.py:701-725`. | Owner Q3. Recommended interim: tag faces in the Windows post-pass and leave the mesh alone. |

## 1. Split: three sub-batches, in this order

| Sub-batch | Content | Size | Why this order |
|---|---|---|---|
| **OUT-4a** Gauge quantities + dynamic pressure | new FO, probe fields, case key, Gauges column unlocks, TSV/Results in Qt and Tk | L | Unlocks the Gauges column and adds the matrix's per-cell availability table, which 4b and 4c both need. |
| **OUT-4b** Peak impulse + obstacle IDs (+ arrival label) | surface/volume arrays, post-pass tagging | M | Both are export-side additions to the files OUT-2 writes. They share one e2e. |
| **OUT-4c** Volume decimation | a volumes-only post-pass and one card box | M | Independent and last: its semantics wait on owner Q4. |

Each sub-batch ends runnable and gated (§3). Suggested TODO sub-ids are `OUT-4a/b/c`.
Coordinate WSL and screen use with the parallel HD1 work before any solve or GUI QA.

## 2. Tasks in order

Design rules that hold for all steps:
- **New `VTK_FIELDS` entries are appended at the end** (`models/case.py:24`).
  `vtk_matrix` canonicalises in `VTK_FIELDS` order (`models/fields.py:236-243`), so
  reordering would change the saved JSON of existing cases.
- New case keys are **omitted when at default**, following the `write_budget` / P15
  pattern. `VERSION` stays 13, and the keys are hidden and not written in native mode.
- A new function object is emitted **only when something ticks it**. The default
  controlDict does not change, so no golden is re-pinned. If a golden does move, stop
  and report.

### OUT-4a: gauge quantities + dynamic pressure

**A1. Characterisation first (S).** Record green runs of `test_regression.py`,
`test_foam_writer.py`, `test_vtk_case.py`, `test_foam_reader.py` and `test_gauge_summary.py`
on master before any edit.
- AC: all five are green, and the log is kept in the batch notes as the baseline.

**A2. Model: the per-cell availability table + the `vtk_gauges` key (M).**
Files: `models/case.py` (VTK_FIELDS, VTK_FO_FIELDS, VTK_ARRAY_NAMES), `models/fields.py`
(VTK_GAUGE_FIELDS, captions/tips, `vtk_matrix`), `services/validation.py`.
- Append `dynamicP` → array `Dynamic_Pressure`. Add a table `VTK_CELLS[field] -> columns`.
  Today every field sits in every destination column. From now on a cell exists only
  where it means something (plan §3.2, §9).
- Gauges column: `p`, `rho`, `U` stay ticked and locked, because wallload and the plots
  consume them. `T`, `overpressure`, `impulse` and `dynamicP` become tickable.
  `overpressure`/`impulse` at gauges are 2D/3D only, the same as D4.
- Case key `"vtk_gauges": {"fields": [...]}` holds only the extras. It is omitted when
  empty.
- AC: `test_vtk_case.py` gains these checks. A case without the key saves byte-identical.
  Round-trip restores the ticks. Validation refuses `impulse`/`overpressure` at gauges in
  1D, a field not in `VTK_CELLS` for its column, and a locked field listed as an extra.
  Each refusal has a test.
- AC: `test_legacy_vtk.py`'s literal `VTK_ARRAY_NAMES` pin is **extended** by
  `dynamicP: Dynamic_Pressure`. This is a spec addition, not a change made to pass. Say
  so in the commit.

**A3. Writer: dynamicPressure FO + probe fields (M).** Files: `solvers/foam/writer.py`
(`_controldict_function_objects` 846, `_controldict_probes` 1064, `vtk_surface_fields`
1092).
- Emit `dynamicPressure { type dynamicPressure; libs (libblastFunctionObjects);
  writeControl writeTime; }` only when `dynamicP` is ticked in any column (gauges
  included). It must come **before** `gauges` and the VTK surfaces in the dict, so the
  stored field exists when they sample it. Cite guide 15.9 p. 125 and `dynamicPressure.C`.
- Probe fields become `['p', 'U', 'rho'] + extras`, with `dynamicP` for q. The default
  list is unchanged. On a resumed AMR leg (`fo_accumulators` off), `impulse` is dropped
  with one log line, as `vtk_surface_fields` already does.
- AC: `test_foam_writer.py` goldens are unchanged. A new check renders a case with all
  extras ticked and verifies, line by line against guide 15.1/15.9: FO order, `fields`,
  `libs`, `writeControl`, and the 1D/resumed-AMR drops.

**A4. Reader → gauge_out → TSV → plots (M).** Files: `solvers/foam/reader.py:475`
(`read_probes`), `solvers/foam/backend.py:631,1664,2330`, `output/gauges.py`
(save_gauges_2d/3d, the 1D writer if foam 1D uses it), `output/plots.py:347`
(`GAUGE_FIELDS`).
- New keys `overpressures`, `impulses`, `temperatures` and `dyn_pressures`. For q,
  `dynamicP` is a vector: store its magnitude, plus the vector as `dyn_pressure_vecs`,
  the same way `speeds`/`velocities` are handled.
- Each key is attached only under the P2-14 item 7 time-column rule (`fits`). A mismatch
  drops the field with a `warnings` entry and never raises.
- TSV: one column per extra, with units in the header (`p_over [Pa]`, `impulse [Pa s]`,
  `T [K]`, `q [Pa]`).
- AC: `test_foam_reader.py` covers aligned files (keys present), a shifted time column
  (dropped with a warning) and absent files (the dict equals today's).
  `test_gauge_summary.py` is unchanged.
- AC: a run with no extras writes a TSV byte-identical to today's.

**A5. The card: the Gauges column unlocks, in Qt and Tk (M).** Files: `ui/fieldform.py:189`,
`gui/forms.py:286`, `models/fields.py:213,226` (the column tip and
`VTK_MATRIX_CAPTION`, which say "fixed").
- The Dynamic pressure row appears in every column. A cell exists only per `VTK_CELLS`.
  p/rho/U are ticked and greyed at gauges.
- AC: `test_ui_output_card.py` and `test_gui_output_card.py` check these points:
  - the cells present per dimension;
  - locked p/rho/U;
  - a ticked T at gauges appears in `vtk_gauges`;
  - save/reload restores the tick;
  - native mode hides the card, and the key is not written.
- AC: there is one new `_qa_ui_harness.py` scenario and one new `_qa_gui_harness.py`
  scenario per dimension. Run `gui-qa-tester` with screenshots, per CLAUDE.md §8.7.

**A6. The Results tab trace selector, in Qt and Tk (S).** Both use
`plots.gauge_fields_available` (`ui/results_gauges.py:151`, `gui/results_panel.py:633`),
so the new `GAUGE_FIELDS` entries show up in both toolkits.
- AC: `test_ui_results.py` and `test_gui_results_fields.py` show each recorded extra in
  the selector, a p-only result shows only `p`, and switching redraws with the right
  y-label and units.

**A7. Small real e2e with pre-registered rules (M).** New `_e2e_out4_gauges.py`, reusing
the tiny 3D case of `_e2e_vtk_3d.py` (serial, activation as that harness uses, ~1 min).
It makes two runs:
- **R0**: no new ticks.
- **R1**: gauges ticked for T, overpressure, impulse and dynamicP, and dynamicP ticked in
  sections, obstacles and volumes.

The rules are **fixed before the run**. On any failure: stop and report. Never widen a
tolerance afterwards.
- A-R1 (the solve is untouched): for every gauge, the R1 p trace against R0 gives equal
  **peak, positive-phase impulse (gauge_summary) and arrival (10 %)**, |Δ| = 0.
- A-R2: the overpressure trace equals p − 101325, within max(1 Pa, 1e-5·|p|).
- A-R3: the blastFoam impulse trace against the Python cumulative ∫(p − p_amb) dt on the
  same samples:
  - the max of the trace is within 2 %;
  - the time of that max is within 2 samples;
  - the arrival read from the overpressure trace equals the arrival read from p.
- A-R4: the q trace against ½ρ|U|² from the probed ρ and U:
  - relative error ≤ 1e-4 wherever q ≥ 1 % of its peak;
  - the time of peak q is identical.
- A-R5: T is finite and > 0, and T at t = 0 is within 1 K of ambient.
- A-R6: the per-family file counts equal R0's ± 1. `Dynamic_Pressure` is in every
  sections, obstacles and volumes file. At each gauge's cell in the last volume file it
  matches the probe's q at that time within 1e-4 relative.

**A8. Gates + docs (S).** Run the gates in §3. Update the README output section,
`DONE.md` (existing style), and `TODO.md` (4a closed).

### OUT-4b: peak impulse, obstacle IDs, arrival label (depends on 4a's `VTK_CELLS`)

**B1. Arrival-time label (S). Apply owner Q1.** Interim if the owner has not answered:
correct only the tooltip (`models/fields.py:161`, and the matrix row tip) to "time of
peak pressure (blastFoam timeOfArrival, guide 15.12)". Keep the array name
`Arrival_Time`, which the owner accepted in ParaView.
- AC: `test_ui_output_card.py` and `test_gui_output_card.py` assert the tip text, and no
  file content changes.

**B2. Peak impulse (M). Apply owner Q2.** Interim route: append `impulseMax` → array
`Peak_Impulse` for sections, obstacles and volumes, 2D/3D only.
- Writer: a **separate** fieldMinMax entry on `impulse` (`fields (impulse); minMax
  max;`), emitted only when ticked. The existing `pMax` FO dict stays untouched, which
  keeps the goldens. Add it to `_FO_ACCUMULATED`, so it is dropped on a resumed AMR leg.
  Cite guide 15.2 p. 123.
- `vtk_export.readable_arrays`: the same addendum as pMax. The running max includes the
  current value, `max(impulseMax, impulse)` when `impulse` is in the file.
- AC: `test_foam_writer.py` has a line-by-line check and unchanged goldens.
- AC: `test_legacy_vtk.py` checks the `Peak_Impulse` name and the max rule.
- AC: `test_vtk_case.py` checks that 1D and gauges are refused.

**B3. Obstacle ID (M). Apply owner Q3.** Interim route: a pseudo-field `obstacleID` in
the **obstacles column only**, the same as Viper's row. When the obstacles are merged on
Windows (`vtk_export`, after the per-field merge), a pure function
`obstacle_ids(points, polys, boxes, tol)` tags each face by its centroid lying on
snapped box *i*'s surface (1-based, in the order of the Obstacles table). Faces on
coplanar touching boxes go to the lowest index. It writes `Obstacle_ID` (int
cell data). There is no mesh, BC or goldens change.
- AC: a unit test on a synthetic 2-box surface checks the counts per ID, the coplanar
  tie, and that every face is tagged. A face that matches no box raises instead of
  being silently set to 0.
- AC: `test_foam_chamber.py` is untouched and green.

**B4. e2e (M).** Extend `_e2e_out4_gauges.py` to a run R2 with 2 obstacles, reusing the
`_e2e_foam_obstacle3d.py` geometry pattern. The rules are fixed before the run.
- B-R1: the solve is untouched against a run with the same geometry and no ticks.
  Peak, positive-phase impulse and arrival give |Δ| = 0 at every gauge.
- B-R2: per cell, `Peak_Impulse` never decreases along each series (tolerance 0) and is
  ≥ `Impulse` in the same file.
- B-R3: at each gauge's cell, `Peak_Impulse` in the last volume file is within 1 % of
  max_t of the gauge's impulse trace.
- B-R4: every face has an ID in 1..N. The face count for each ID equals the
  Python-predicted exposed faces of that snapped box. If Q3 chooses split files, their
  union is the whole file.

**B5. Gates + docs (S).**

### OUT-4c: volume decimation (after owner Q4)

**C1. Key + card (S-M).** Add `vtk_volumes.decimate` (int k ≥ 1). It is omitted when
k = 1 and appended after the existing `VTK_VOLUME_KEYS`. One spin box on the Volumes
family goes in the Qt and Tk cards, 3D only in the interim.
- AC: `test_vtk_case.py`: k = 1 saves byte-identical, and k < 1 or a non-integer is
  refused.
- AC: the Qt and Tk output-card tests plus one harness scenario each.

**C2. Pure post-pass (M).** `legacy_vtk`/`vtk_export`: `decimate(vd, k, origin, dx_base)`
works on the rewritten UNSTRUCTURED_GRID volume file. It keeps the cells whose centroid
lies in every k-th base-cell layer on each axis, then re-indexes the points. It is
AMR-safe (no cellSet per time) and does not touch WSL. `manifest.json` records k.
- AC: a unit test on a synthetic grid checks the cell count, the byte-equality of kept
  values, a valid point re-index (a strict `legacy_vtk.parse` round trip), and that
  k = 1 changes nothing.

**C3. e2e (S).** Run the same tiny 3D case with k = 1 and k = 2.
- AC: the gauge TSVs are byte-identical (post-pass only).
- AC: the volume cell count matches the prediction.
- AC: kept cell values are byte-equal to k = 1's.

**C4. Gates + docs (S).**

## 3. Gates (each sub-batch)

- `test_regression.py` byte-identical first (native untouched), and
  `test_foam_writer.py` goldens unchanged.
- `test_case_validate.py`, `test_vtk_case.py`, `test_vtk_export_plan.py`,
  `test_vtk_series.py`, `test_legacy_vtk.py`, `test_vtk_readers.py`, `test_vtk_protect.py`,
  `test_foam_reader.py`, `test_gauge_summary.py`, `test_write_budget.py`, and
  `test_foam_chamber.py` (4b).
- Qt: `test_ui_output_card.py`, `test_ui_results.py`, `test_ui_no_vtk_in_main.py`,
  `test_ui_no_mpl_pyplot.py`, `_qa_ui_harness.py`.
- **Tk:** the nine `test_gui_*` suites plus `_qa_gui_harness.py`, because `models/`,
  `output/` and `solvers/` change.
- WSL: `wsl -d Ubuntu -- pgrep -a blastFoam` must be empty. Run `python -u` in the
  background with no timeout. `_e2e_vtk_3d.py` must still pass 41/41.
- `gui-qa-tester` with screenshots after 4a and 4c (card changes), then owner acceptance
  in ParaView, the same as V9.

## 4. Risks

- **Numerical results:** none of the FOs write state (dynamicPressure,
  fieldMinMax(impulse) and the extra probe fields only read). A-R1 and B-R1 prove it
  with a zero tolerance on peak, impulse and arrival. The `pMax` addendum pattern now
  also applies to `impulseMax`. Its t = 0 behaviour needs the same test as pMax.
- **FO order:** a field sampled before it is computed gives a one-step lag, or a
  "cannot find" error on the first step. A3 pins the order.
- **Saved-case compatibility:** appending to `VTK_FIELDS` and omitting defaults keeps
  old JSON byte-identical. A case file with the new keys is refused by an older
  blastlab ("Unknown case keys"), which is accepted per the P15 precedent.
- **AMR resume:** `impulse`/`impulseMax` do not exist on a resumed AMR leg. They are
  dropped with a log line and must never crash the probe reader (the A4 alignment rule).
- **Goldens / fixtures:** no re-pin is expected. The only pinned test edit is the literal
  `VTK_ARRAY_NAMES` map in `test_legacy_vtk.py` (A2, B2). It is an extension, and the
  commit says so. Choosing Q3 (b) would add re-pins for every obstacle golden, plus a
  conflict with `test_foam_chamber.py`.

## 5. Out of scope (plan §5, unchanged)

ASII / HVEL / RISK, ignition time, and the whole-domain energy/density outputs
(`conservedQuantities` already logs them).

## 6. Owner questions (only the owner can decide), each with a recommended interim

| # | Question | Recommended interim |
|---|---|---|
| Q1 | blastFoam's "arrival time" is the **time of peak pressure** (F1). Viper has two rows: *Arrival time (initial)* and *(peak overpressure)*. Should the row be relabelled "Time of peak overpressure"? Should a first-arrival field be added? Adding it would need a Python derivation at the VTK cadence, because blastFoam has no FO for it. | Fix the tooltip to state the guide's definition, keep the array name `Arrival_Time`, and add no new field. |
| Q2 | Peak impulse = the per-cell running **max over time of blastFoam's net impulse** (∫(p − p_amb) dt from t_start; for a classic waveform this equals the positive-phase impulse). Should it be written as a `Peak_Impulse` array in every file, the way Viper does? The alternative is plan §5's single end-of-run VTK per family. | Use the FO route (fieldMinMax, per step) as an array in every file. The last file carries the final peak. |
| Q3 | Obstacle IDs: (a) an `Obstacle_ID` array on the one obstacles file, the Viper row, with no mesh change; (b) (a) plus one split file/series per obstacle, from the post-pass; (c) one mesh patch per obstacle (plan §5), which needs createPatch, goldens re-pins and a reversal of the chamber "no createPatch" pin. | (a), numbered 1..N in the order of the Obstacles table. |
| Q4 | What does the decimate ratio k mean? (a) Subsample: keep every k-th cell per axis, values untouched, so a peak between kept cells is not shown. (b) Coarsen: average k³ cells, which smears peaks. (c) Keep 1 of every k cells in total. Should it apply to 3D volumes only? | (a), per axis, 3D volumes only, default 1. |
| Q5 | Dynamic pressure: should it be the scalar magnitude ½ρ\|U\|² (guide eq. 15.1, "the standard dynamic pressure")? The alternative is the vector, or its component normal to a wall. | The magnitude in the files and TSV. Keep the vector in the gauge result dict (as `velocities` is kept, HD1-13). |
| Q6 | Viper ticks *Impulse at gauges* by default. Should blastlab do the same? That would change the default controlDict and re-pin the writer goldens. | No new default ticks. p/rho/U stay locked. |

**Owner decision Q1 (2026-09-27):** relabel the blastFoam `timeOfArrival` output as
time of peak ("Time of peak" on the card, array `Time_Of_Peak`; data unchanged). Add a
true first-arrival field `Arrival_Time` (10 % threshold, like the gauge summary) ONLY if
it can be computed exactly during the run; feasibility is checked in 4b, not now. The
relabel belongs to 4b (B1). **Q2-Q6:** use the interims above; do not ask again.

**Owner decisions Q2-Q6 (2026-09-27), all matching the interims:**
- **Q2** yes: the per-cell running max of the net impulse, written as `Peak_Impulse`
  in every file (4b).
- **Q3** option 1: an `Obstacle_ID` array, no mesh change (4b).
- **Q4** subsample per axis, 3D volumes only, plus a card warning line "decimated
  files are for viewing only; peaks may be missed" (4c, now unblocked).
- **Q5** the magnitude only, q = ½ρ|U|².
- **Q6** impulse at the gauges is NOT ticked by default.

## 7a. Batch notes

**A1 baseline (2026-09-27, branch `out-4a-gauges` from `6af6a11`, before any code
edit):** `test_regression.py` REGRESSION: PASS (byte-identical);
`test_foam_writer.py` FOAM WRITER: PASS; `test_vtk_case.py` VTK CASE: PASS;
`test_foam_reader.py` FOAM READER: PASS; `test_gauge_summary.py` GAUGE SUMMARY: PASS.
Also green: `test_legacy_vtk.py` (11/11), `test_case_validate.py`.

**A7 e2e (`_e2e_out4_gauges.py`, rules committed in `3273d74` before any run):**
- Run 1 FAILED: no `dynamicP` anywhere ("Cannot find registered field matching
  dynamicP"). Cause: OF-9 `fieldExpression` takes dynamicPressure.C's "dynamicP" as
  the *default field name*, so the result is named `dynamicPressure`
  (fieldExpression.C:47-60). F3 above is wrong on this. Fixed in `38f067c`
  (`result dynamicP;`); no rule changed.
- Run 2: 26/28 PASS. A-R1 |d| = 0 on peak / impulse / arrival (p arrays identical,
  972 steps both); A-R2, A-R3a (0.14 %), A-R3b (1 sample), A-R4a (worst 1.3e-5),
  A-R4b, A-R5, A-R6a/b pass. **Two FAIL, both in how the script reads the numbers,
  not in the recorded data; per the rules, stopped and reported, script not changed:**
  - A-R3c: the same sample on both sides (t = 1.69987e-05 s), but the p side went
    through gauge_summary's ms and back (1.6998700000000004e-05 vs 1.69987e-05).
  - A-R6c: the probe time column has 6 significant digits (blastProbes
    writePrecision), so no row matches the last volume time 0.00099946659 s to
    1e-9; the nearest row is 0.000999467. The value comparison never ran.
  Owner decision needed: re-register A-R3c (compare sample indices) and A-R6c
  (match the row to the probe file's printed precision), then rerun.
- **Re-registered (owner, 2026-09-28), committed before run 3:** A-R3c compares
  the arrival SAMPLE INDEX from p_over and from p (gauge_summary's criterion);
  A-R6c takes the probe row whose time equals the file time printed at the probe
  file's precision (6 significant digits). Thresholds unchanged.
- **Run 3 (after `825d553`): PASS, 29/29.** A-R1 |d| = 0 (peak 106962.675 kPa,
  impulse 6865.5066, arrival 0.0169987 ms, 972 steps both); A-R2 worst 675 Pa
  (within its bound); A-R3a 0.14 %; A-R3b 1 sample; A-R3c sample 43 = 43;
  A-R4a worst 1.3e-5; A-R4b 111 = 111; A-R5 T(0) = 288.002 K; A-R6a counts equal
  (39/39/39/10); A-R6b 127/127 files; A-R6c rel 1.8e-6.

**4b (2026-09-28, branch `out-4b-peaks-ids` from `b32279e`).** Baseline:
every §3 suite green (`test_vtk_series` once hit a transient Windows
`PermissionError` in `test_rewrite_keeps_earlier`; green on three reruns).
- **Q1 Arrival_Time feasibility: NOT added.** The owner's definition (first
  time p exceeds 10 % of the cell's PEAK overpressure, as gauge_summary) is
  not causal: the threshold depends on the final peak, so no per-step
  running state can fix the crossing time exactly (a later, larger
  reflected shock raises the threshold after the first shock already
  crossed the old one). blastFoam 6.2 has no function object for it (the
  list in `src/functionObjects/`: blastProbes, fieldMinMax, impulse,
  overpressure, timeOfArrival, dynamicPressure, ...), and a Python
  derivation from the written files is limited to their cadence - not
  exact. A fixed absolute threshold would be causal, but only through an
  OF-9 `coded` function object (run-time compilation) and it is not the
  owner's definition. So only the relabel (B1) was done.
- **F6 (new, needs the owner): `Time_Of_Peak` is all t_start in every
  default 2D/3D run.** `timeOfArrival.C` shares the registered `pMax`
  field with the `pMax` fieldMinMax (`lookupOrCreate`) and updates the
  time only when `p > pMax`. The writer emits `pMax` BEFORE `arrival`,
  so each step fieldMinMax has already raised pMax to p and the test is
  never true. Measured: every `timeOfArrival` in `/root/blastlab_runs`
  (13 runs, newest write) is `uniform 0`, or `uniform 0.000187338` on two
  3D runs (one value over the whole field, presumably a leg's start time -
  not checked), and R2 below writes
  Time_Of_Peak = 0.0 on every obstacle face. With `fo_accumulators` off
  (no pMax FO) it would work. Fix = emit `arrival` before `pMax` - that
  reorders the default controlDict and re-pins every writer golden, so it
  is not done here.
- **B4 e2e (`_e2e_out4_gauges.py --only 4b`, rules committed in `e4ac578`
  before the run): run 1 PASS, 14/14.** B-R1 |d| = 0 (peak 114695.675 kPa,
  impulse 7108.7627, arrival 0.0169987 ms; p arrays identical, 981 steps
  both); B-R2 a/b/c pass over 130 files (obstacles, two planes, volumes);
  B-R3 rel 4.4e-7; B-R4 counts 624 / 576 = predicted in all 40 obstacles
  files.

- **Owner decision F6 (2026-09-28): fix it inside 4b.** The writer emits
  `arrival` (timeOfArrival) before `pMax`; the writer goldens are re-pinned
  (a pure block reorder). Rules F-R1..F-R4, pre-registered in
  `_e2e_out4_gauges.py` (`--only f6`) in the commit that records this
  decision, before the fix and before any run: R3 (fixed) vs R3pre (the
  pre-fix order, a test-only spy) - solve untouched (peak, positive-phase
  impulse, arrival |d| = 0, p arrays and times identical, same step
  count); Time_Of_Peak not uniform, not 0 on every obstacle face, every
  value in [0, t_file]; at each gauge cell Time_Of_Peak = the probe time
  of peak p within 2e-5 relative; Peak_Overpressure, Peak_Impulse and
  Impulse identical to R3pre (tolerance 0).
- **F6 fixed in `e592f48`** (arrival before pMax; 17 foam + 4 char goldens
  re-pinned, checked by script to be a pure block reorder). **F6 e2e run 1
  (rules `769df4a`): PASS, 21/21.** F-R1 |d| = 0 (peak 114695.675 kPa,
  impulse 7108.7627, arrival 0.0169987 ms), p arrays and times identical,
  981 steps both; F-R2 Time_Of_Peak 263 distinct values on the obstacles
  (2.34e-5 .. 2.41e-4 s) and 446 in the volumes, all within [0, t_file];
  F-R3 gauge cell 3.42649e-5 s vs probe peak 3.42649e-5 s, rel 1.2e-6;
  F-R4 Peak_Overpressure, Peak_Impulse, Impulse identical. R3pre (old
  order) shows the symptom: 1 distinct Time_Of_Peak value. Gates after the
  fix: all sec. 3 suites, the 16 Tk test_gui_*, test_regression
  byte-identical - PASS.

**4c (2026-09-28, branch `out-4c-decimation` from `d1402bf`).** Baseline:
every sec. 3 suite and the Tk test_gui_* green before the first edit
(test_gui_solver_mode was caught mid-edit by the new form key; green once
the Tk card had it).
- **C1** `9176385`: `vtk_volumes.decimate` (after VTK_VOLUME_KEYS, only
  when k != 1), validation (whole number >= 1; > 1 is 3D only; a note with
  the owner's warning), the Qt QSpinBox / Tk ttk.Spinbox 1..16 on the 3D
  Volumes family with the warning line under it; char case-form goldens
  re-pinned (only the new form key added).
- **C2** `6ee0479`: `vtk_export.decimate` on the Windows copy of each
  volume file; manifest `decimate: {volumes: k}`.
- **C3 e2e (`_e2e_out4_gauges.py --only 4c`, rules committed in
  `6139d96` before the run): run 1 PASS, 15/15.** C-R0 dx_base 0.017647 m
  (34 base cells per axis: the charge refinement is global, so not the
  case's 0.04 m - the rule text was corrected to that in a dry check,
  before the rules commit and before any run); C-R1 |d| = 0 (peak
  106962.675 kPa, impulse 6865.5066, arrival 0.0169987 ms, 972 steps
  both); C-R2 gauges\ byte-identical; C-R3 10 = 10 volume files; C-R4
  counts = prediction in all 10; C-R5 values, coordinates, TIME equal
  (tolerance 0); C-R6 manifest k = 1 / 2. Cells kept 47690 / 382960 =
  0.1245 (the obstacle's cells lie outside the domain's mesh), bytes
  0.25.

## 7. Remaining backlog after OUT-4

The OUT track is then complete except OUT-1's pending `gui-qa-tester` screenshots and
owner acceptance, and OUT-3's parked Q1-Q7. Next is the `HD1` track (`TODO.md` §HD1),
then P0 → P4 in `TODO.md` order.
