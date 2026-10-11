> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [docs/SCOPE.md](../../docs/SCOPE.md)

# DONE, part 2 — the GUI-redesign batches §0l-§0w (2026-09-28 … 10-05)

Moved verbatim out of [DONE.md](../../DONE.md) on 2026-10-11 to keep it under the
1000-line cap. Section numbers are unchanged, so `DONE.md §0t` and the like resolve here.

---

## 0l. 2026-09-28/29 — batch `gui-foundation` (GUI-1, GUI-2, GUI-4)

Plan: `docs/batches/2026-09-28-gui-foundation.md`; spec `docs/gui-redesign-plan.md`
§2, §2.5, §3. Reports: `…gui-foundation.implement.md` (verification: all three
VERIFIED, no fixes needed).

- **What:** `GUI-1` — the Qt palette rewritten to the redesign (warm black, orange
  `#ff6a2b` accent, cyan `#4cc9f0` gauges; every old key kept, 21 new), light palette
  with six values darkened to pass 4.5:1 (decision D1); Space Grotesk (variable),
  IBM Plex Sans and Mono bundled under `blastlab/ui/fonts/` with their OFL, loaded
  from the package with a Segoe UI / Consolas fallback; no white text on orange
  anywhere. `GUI-2` — the stepped-front mark drawn with QPainter at 64/32/16
  (`theme.logo_pixmap`), the app icon (16…256) on the window, QApplication and taskbar
  (AppUserModelID `blastlab`), the BLASTLAB wordmark in place of the ELSL gif in the Qt
  window; Tk and `logo.gif` untouched. `GUI-4` — `ui/components.py`: ToggleSwitch,
  StatTile, TreeRow, DockTabs, Banner, HandoffCard; Segmented restyled.
- **Tests:** new `test_ui_theme` (keys, contrast table, fonts, fallback),
  `test_ui_logo` (pixel colours at 64/32/16, icon sizes), `test_ui_components`; all
  PASS. `test_regression` byte-identical; the Qt fast gates green; no committed
  assertion changed. Real-platform screenshots in `docs/qa/2026-09-28-gui-foundation/`.
- **Deviations from /todo:** no simplifier pass (UI code, no calculations) and the full
  QA + UX agents deferred to the end of the GUI track, as the owner asked.
- **Open, non-blocking:** `docs/gui-redesign-decisions.md` D1-D6.
- **Commits:** `f553014`, `3dda85e`, `2f64601`, `d9191b9` and the commit of this entry.

## 0m. 2026-09-29 — batch `gui-frame` (GUI-8, GUI-3)

Plan: `docs/batches/2026-09-29-gui-frame.md`; spec `docs/gui-redesign-plan.md` §4, §8.3.
Report: `…gui-frame.implement.md`. Verification: GUI-8 VERIFIED, GUI-3 FIXED.

- **What:** `GUI-8` — the Chain runs 1D → 3D: `ChainPanel.run()` no longer refuses
  {1, 3} as non-consecutive and wires `handoff_1d_to_3d.txt` into a 3D stage with
  `init_mode 'profile1d'` (the engine already supported it). `GUI-3` — the sidebar is
  gone: new `ui/topbar.py` with the workflow pills 01 Setup → 02 Run → 03 Results,
  the Chain link, the case menu (Open, Save in place, Save as, Recent, Dark mode), the
  solver chip (native / blastFoam, WSL status, Re-detect) and the dimension control;
  a 28 px status bar; the window title carries the case, `●` when dirty, the run's %
  and `Chain k/n`; **Esc no longer stops a run, Shift+Esc does** (UX-7).
- **Tests:** `test_ui_chain` 78 (C6b wiring, C12 a tiny native 1D → 3D chain end to end,
  first 3D frame non-ambient); new `test_ui_frame` 50; the fast matrix green;
  `test_regression` byte-identical; `_e2e_ui_embed` 24/24 with the 3D viewer never
  misplaced (and a 514-sample Win32 measurement, 0 wrong); `_e2e_hd13_gui` PASS after
  the verifier's fix. Layout-pin assertions updated per plan §9: parity P6
  (Esc → Shift+Esc) and P3, `test_ui_logo` wording, chain C2, harness B01.
- **Verifier fix:** `35d8cb4` — a status message hides the shortcuts hint while it
  shows (D13), so the HD 1.3 summary is not clipped by the narrower status bar.
- **Open, non-blocking:** decisions D7-D13; `_e2e_ui_view3d.py` fails on the home PC
  identically before the batch (re-run on the office machine).
- **Commits:** `fbbc698`, `25a031d`, `067123d`, `35d8cb4` and the commit of this entry.

## 0n. 2026-09-29 — batch `gui-setup` (GUI-5, part a)

Plan: `docs/batches/2026-09-29-gui-setup.md` (splits GUI-5 into 5a and 5b; this is 5a);
spec `docs/gui-redesign-plan.md` §5. Report `…gui-setup.implement.md`. Verification:
T1, T3, T4, T5 FIXED; T2 PARTIAL (a 27 ms viewer resize lag, pre-existing mechanism,
recorded as F5 in `docs/gui-redesign-decisions.md`).

- **What:** 01 Setup in three columns — a numbered model tree (01 Threat … 07 Output,
  gauges and obstacles as child rows, ✓/✗, + Gauge / + Obstacle, the Case OK pill), the
  preview in the centre, and the selected node's cards only on the right.
  `FieldForm(placement='nodes')` splits placement, not parsing (`ui/setup_nodes.py`,
  `ui/setup_tree.py`); the Chain editor keeps `'columns'`. The trigger becomes a switch
  *End the run at a gauge* with a gauge dropdown, writing the same `trigger_gauge`
  values; Profile file only in a profile mode; a Derived card (charge radius from the
  report's `r_exp`, height of burst, nearest gauge with Z). `ui/scaled_distance.py`,
  display only: Z = R / W^1/3 (UFC 3-340-02 para. 2-13.1), None for planar, profile,
  0D.
- **Tests:** new `test_ui_setup_tree` (238); `test_regression` byte-identical;
  `test_ui_setup_form`, all char goldens and `test_ui_output_card` unchanged and green;
  18 committed and edge-case JSONs load → save byte-identically, HEAD = base; the
  viewer never top-level or outside the window over 8,988 samples. Parity P3/P4 became a
  no-clip sweep of every node (layout pins, plan §9).
- **Verifier fixes:** `7f19bb4` (test under cp1252 stdout), `684f572` (the trigger switch
  on with no gauge chosen was silent — now a red dropdown, D27), `953d608`
  (`DerivedCard.update` shadowed `QWidget.update`), `9b7172f` (harness screenshots
  from the right node).
- **Open, non-blocking:** decisions D14-D28 and findings F1-F8 in
  `docs/gui-redesign-decisions.md` (F1: an agent ran a broad `taskkill` once).
- **Commits:** `887072c`..`c76d6e0`, `7f19bb4`..`9b7172f` and the commit of this entry.

---

## 0o. 2026-09-29 — batch `gui-setup-b` (GUI-5, part b; GUI-5 closed)

Plan: `docs/batches/2026-09-29-gui-setup-b.md` (the 5a plan's hand-off); report
`…gui-setup-b.implement.md`. Verification: T1-T3 FIXED, T4 VERIFIED.

- **What:** the Setup centre. A live-number strip (`ui/setup_strip.py`: Charge, Cells,
  MPI ranks, Memory, Z at gauges; Run F5 and Initialise), every number taken from the
  report and run plan `_validate` already produced; tiles hide when the report has no
  such number. Model-view overlays (`ui/model_overlay.py`): Z rings at 1-3, charge and
  gauge highlights with R labels, hover readout `r · z · R · Z`, toolbar Z rings / Mesh /
  Fit, wheel zoom; gauges cyan. The dock Gauges · Checks · Log replaces the report card
  and follows the selected node; the gauge table has Z and Where (nearest obstacle face
  within 0.5 m, "in front of" or "behind" by the burst line); the 05 summary reads
  `2 · in front of Wall 1`.
- **Tests:** new `test_ui_setup_strip` (tiles equal report fields across 8 case kinds;
  ring radii, R labels, hover; dock and Where); the fast matrix (33 suites) green;
  `test_regression` byte-identical; harness B/C/V 20 scenarios, no findings; viewer
  never misplaced (1530 samples). Layout pins changed: tree T2c summary text,
  `STATUS_MAX_H` 132 → 170.
- **Verifier fixes:** `2c20503` (a probe race in a strip test), `f975da3` (28 px
  Initialise and toolbar buttons were 17-18 px under QSS), `e7f97f9` (overlay artists
  shared between the 1D and 2D previews), `0ae5e50` (a gauge behind a wall read
  "in front of" — now "behind", D39), `75655a7` (shots).
- **Open, non-blocking:** D29-D41 (D40: the AMR Memory tile shows t = 0).
- **Commits:** `b20461b`..`129a2e7`, `2c20503`..`75655a7` and the commit of this entry.

---

## 0p. 2026-09-29 — batch `gui-run` (GUI-6, parts a and b)

Plan: `docs/batches/2026-09-29-gui-run.md`; reports `…gui-run-a.implement.md`,
`…gui-run-b.implement.md`, `…gui-run.verify.md` (T1, T2, T5, T7, T8, T9 VERIFIED;
T3, T4, T6 FIXED).

- **What:** 02 Run in three columns. Controls: where the files go (the resolved model
  folder), Stop (Shift+Esc) / Run again, 3D, *Step through* folded (Initialise,
  +1 … +1000, To the end, Pause), Live view with the auto colour-range switch (Min/Max
  only when off), a link back to Setup. A progress strip with `% · elapsed · about X
  left` (after 5 %; `ui/run_clock.py`, paused time excluded). The dock Log · Messages ·
  Earlier runs with Copy and Save log (the previous run's log is kept). A live-gauge
  column (`ui/run_gauges.py`): the selected gauge enlarged with peak and now line, a
  list sorted by Z with sparklines, peak so far or `waiting`. Stop asks after 30 s of
  run time (blastFoam: "you can resume it later"). At the end: a green banner,
  `✓ Done` in the title, a Windows notification (`dialogs.notify_desktop`, tray icon
  created on demand and removed). A hidden `chain_slot` for GUI-9.
- **Tests:** `test_ui_run_screen` (168); new real-run e2e `_e2e_ui_run_finish.py` (19,
  the toast captured on screen); `test_regression` byte-identical; gauge arrays
  identical with the new collection rule, cost 1.07 (rule ≤ 1.10, pre-registered; the
  first design measured 1.15 and was changed per the plan's fallback, D69); the 3D
  viewer 0 ms wrong under the banner. Allowed layout-pin changes: run_panel U-checks,
  `_e2e_ui_native_warn`, harness B06 (plain Esc) and F07 (count error dialogs only).
- **Verifier fixes:** `8eadde1` (blastFoam 3D live payload carries x only — the column
  matched nothing and showed wrong Z; D73), `5b0a5f5` (Save log to an unwritable path
  raised), `61bfd56` (B06 could never fail; a test swallowed its tracebacks).
- **Known:** commit `b31df5d` (T2) carries a stale GUI-5 message; the real one is in its
  git note. Open, non-blocking: D42-D75, F9-F14 (F13 viewer resize lag ~44 ms,
  pre-existing; F14 an intermittent `removeEventFilter` on a deleted viewport in
  `fieldform.py`).
- **Commits:** `6362cec`..`90d2718`, `90d2718`..`3c885fd`, `8eadde1`..`2609024` and the
  commit of this entry.

---

## 0q. 2026-09-29 — batch `gui-results` (GUI-7, parts a and b; F14)

Plan: `docs/batches/2026-09-29-gui-results.md`; reports `…gui-results-a.implement.md`,
`…gui-results-b.implement.md`, `…gui-results.verify.md` (T0, T1, T3, T4, T7 VERIFIED;
T2, T5, T6 FIXED).

- **What:** 03 Results in three columns. A results list with `latest` / `chain` badges
  and a caption; "How it was computed" read only from the result's meta and record
  files, with Show case and **Load into 01 Setup** (loads without a path, so Ctrl+S can
  never overwrite `MODEL.json`); a hidden `stage_slot` for GUI-9. Views **Field**
  (the old Fields and Animation in one: field, colour scale whole run / each frame /
  manual driving the animation export as before, hover readout, time bar with Play,
  arrival tick, speed, This frame .png) · **Gauges** (one pyqtgraph plot, the selected
  gauge cyan with its positive phase shaded, a table with Z and impulse in kPa·ms on
  screen only, sorted by Z, Copy table / Ctrl+C inside the table) · 3D. Exports grouped
  Data / Figures with a busy strip and no double start; the VTK error dialog now on the
  GUI thread. F14 made harmless (`fieldform` forgets destroyed viewports). F15 (stale
  colour bars) fixed. No KB columns, no run overlay (owner).
- **Tests:** an export golden recorded at base first (`test_ui_char_results_exports`,
  26 exports) — green after every task; real exports of 1D and 2D runs byte-identical
  to a base worktree; `test_regression` byte-identical; new `test_ui_results_screen`
  (186), `test_ui_fieldform_viewport`, `_e2e_ui_results`, the committed Win32 sampler
  `_e2e_ui_viewer_place.py` (R-VIEWER 0 ms on 7 actions). The pre-registered
  R-VIEWER-RESIZE failed its judged pair (18.5 → 25.4 ms, limit 23.5) — F13, pre-existing,
  `view3d_host.py` untouched; reported, not fixed. The `ui_results_meta.json` gauges
  entry migrated under a curve-by-curve hash proof.
- **Verifier fixes:** `10ed2ca` (list hid the newest row; light caption contrast),
  `db5657c` (title kept `✓ Done` after Load), `e5de7ed`, `d7b614d`, `fbb5ef5`, `f7cb4fc`
  (hover readout inside the map), `b4cad6e` (1D profiles cropped at 1100 × 720).
- **Open, non-blocking:** D76-D130, F13-F17.
- **Commits:** `bb065fc`..`8b5bfea`, `10ed2ca`..`9233a98` and the commit of this entry.

---

## 0r. 2026-10-03 — batch `gui-chain` (GUI-9, parts a and b)

Plan: `docs/batches/2026-09-29-gui-chain.md`; reports `…gui-chain-a.implement.md`,
`…gui-chain-a.verify.md`, `…gui-chain-b.implement.md`, `…gui-chain-b.verify.md`
(T0, T1, T3, T6 VERIFIED; T2, T4, T5 FIXED). Screenshots and measurements in
`docs/qa/2026-09-29-gui-chain/`.

- **What:** the Chain screen. Four route buttons (1D→2D→3D, 1D→3D, 1D→2D, 2D→3D)
  replace the stage checkboxes; the wiring moved verbatim from `ChainPanel.run()` into
  the toolkit-free `ui/chain_route.py`. A pipeline of stage cards with the hand-off file
  on each arrow (`chain_pipeline.py`); the selected stage edited in the Setup layout
  (`chain_stage.py`, forms on `'nodes'`) with per-stage live checks equal to `run()`'s
  refusals, Copy from 01 Setup, Load case…, new stages seeded from the Setup case. In
  02 Run a chain strip, one pill per stage with its time and the hand-off caption
  (`chain_strip.py`, in the existing `chain_slot`; `run_controller.py` untouched); the
  title reads `Chain 2/3 · 78 %`. In 03 Results a chain with a model is one entry with
  STAGE tabs; per-stage views and exports byte-equal to a plain entry's.
- **Tests:** a launch golden recorded at base first (`test_ui_char_chain_wiring`,
  16 scenarios: 4 routes × 2 variants, 8 refusals) — green after every task;
  `test_regression` byte-identical; `test_ui_chain` C13 per route; new
  `test_ui_chain_screen` (187); `_e2e_ui_chain_screen.py` on the real platform (23).
  Viewer sampler: R-VIEWER 0 ms on all 9 actions incl. the four new ones;
  R-VIEWER-RESIZE within its pre-registered limit on both surfaces (F13 stays open).
- **Verifier fixes:** `45760ce` (a broken Setup source was swallowed as "Setup has
  errors"), `80d2c03`, `2f58395` (F25: a stage started with the previous stage's 100 %),
  `1a83437` (a chain removed while running came back at the next stage).
- **Not run here:** `_e2e_ui_chain_foam.py` — the 3D blastFoam stage outlived 1800 s on
  the home PC (25/31; the 6 failures all follow from it). Run it on the office machine.
- **History:** T0's commit first carried GUI-7's message (F19); reworded by rebase
  before push, tree unchanged.
- **Open, non-blocking:** D131-D170, F20-F27.
- **Commits:** `3e9ed58`..`024e799` and the commit of this entry.

---

## 0s. 2026-10-03 — batch `gui-qa` (GUI-10, parts a and b)

Plan: `docs/batches/2026-10-03-gui-qa.md`; reports `…gui-qa-a.implement.md`,
`…gui-qa-a.verify.md`, `…gui-qa-b.implement.md`, `…gui-qa-b.verify.md`. Findings,
measurements and screenshots in `docs/qa/2026-10-03-gui-qa/` (`findings.md`).

- **What:** the QA harness drives the new frame (pills, dimension control, solver chip,
  Dark-mode action, each click checked), B06 real-platform aware, `wait_log` by run
  generation (F22), utf-8 output (F24), chain stages selectable by label, `press()`
  refuses a hidden control (F33), new scenarios K01 (frame), K02 (nothing clipped at
  1100 × 720, both modes), K03 (light mode) — 81 scenarios — and `_qa_findings_diff.py`.
  UI fixes: Setup pill / + buttons at the board's heights (F21), tree-number contrast
  (F8), clean path copy without U+200B (F23), chain-stage readouts reset (F27), top bar
  at 1100 px (F29, F37: spacing, an elided case name with its tooltip and accessible
  name, a compact `●` marker when a control would be squeezed), tree-row hover at
  ≥ 4.5:1 (D190), P MAX fits its tile (F34).
- **Passes:** base `0605522` (pre-redesign) 66 scenarios, 1 finding; HEAD 69, after the
  fixes no new finding beyond the intended changes; real platform 10/10; F group in WSL
  12/12, all findings dispositioned (pre-existing P2-22, F36; F07 needs the office
  machine). R10 (viewer placement 0 ms, resize median ≤ 50 ms) passed on every surface;
  F13 stays open for a viewer-host batch. P2-21 gone; P2-18, P2-24 still reproduce.
- **Tests:** every `test_ui_*` suite one at a time, the real-platform e2e scripts;
  `test_regression` byte-identical; `test_ui_char_chain_wiring` green; frozen paths
  (`gui/`, `core/`, `solvers/`, `output/`, `view3d_host.py`, `run_controller.py`) 0 lines.
- **Verifier fixes:** `a99872b` (findings diff read a path past a later slash, F31),
  `0c39004` (F37: 0-D segment squeezed by the longest chip).
- **Owner review (2026-10-03):** all open calls approved with the session's
  recommendations; the work items are TODO GUI-11.
- **Commits:** `950a34a`..`3b029ca` and the commit of this entry.

---

## 0t. 2026-10-04 — batch `gui-polish` (GUI-11, parts a-d; 11e awaits the owner)

Plan: `docs/batches/2026-10-03-gui-polish.md`; implement and verify reports
`…gui-polish-{a,b,c,d}.{implement,verify}.md`. Inputs: the owner review of 2026-10-03,
`docs/UX_REVIEW-redesign.md` (UXR-1..26, written after GUI-10) and
`docs/qa/2026-10-03-gui-final/QA_REPORT.md` (the final real-platform QA: every on-screen
number matched the core). Shots in `docs/qa/2026-10-03-gui-polish/`.

- **11a, correctness in the frame:** the crash dialog only on the GUI thread (UXR-4);
  Close / Open / Recent ask before dropping a live run, an HD 1.3 assessment or unsaved
  edits (UXR-1, QA S2-2); Save as reports a write failure (UXR-5); F5 on Chain runs the
  chain (UXR-7); the 0-D run goes to 02 Run with Run greyed and a 0-D note (UXR-8, F12,
  P2-18); refusals titled after the action, paths kept whole, long tooltips wrapped
  (P2-24 Qt half).
- **11b, shared modules (Tk gate run, 16 suites + the Tk harness):** `solvers/worker.py`
  one line — a stage start clears the previous stage's progress (F28, owner-approved);
  `services/validation.py` warns of a gauge inside an obstacle, and Run / Results keep
  the entered gauge numbers (UXR-2); the Chain warns when a 1D hand-off already reaches
  the next stage's boundary (QA S2-1, D200).
- **11c, Setup and Chain:** Material hidden in native mode (owner, UXR-3; the native
  case still writes TNT, 48 case files byte-identical); a loaded case keeps its hidden
  AMR values (F16); removing a gauge keeps the trigger on its gauge (UXR-9); r / z and
  `Height H` in axisymmetric (UXR-11, F4); kPa·ms, `= N ms`, Z-unit tooltips citing
  UFC 3-340-02 para. 2-13.1 (UXR-15); Chain route tooltips and hints (UXR-12).
- **11d, Run / Results / top bar:** `●` whenever the case name is elided (D191);
  visible dark tree hover (D192); P MAX fits at 1280, strip and live view keep their
  minimums (QA S3-1, S3-2, S3-7); method card units (UXR-10); Results 3D placeholder;
  finish notification by entered gauge number (F43); Show Details for a shortened path
  (F40); refusal re-worded after a geometry toggle (F46); harness F38 / F36.
- **Goldens re-recorded (owner-approved, own commits):** `ui_case_form.json` — `material`
  hidden in 4 native entries (UXR-3), `amr_refine` / `amr_unrefine` in 3 `/get` entries
  (F16). Tk goldens untouched.
- **Tests:** every `test_ui_*` suite one at a time, the char goldens, the real-platform
  e2e scripts, the Tk suites in 11b; harness vs GUI-10: 0 new S1 / S2; R10 passes (viewer
  placement 0 ms, resize median ≤ 44 ms); `test_regression` byte-identical after every
  part; `test_ui_char_chain_wiring` unedited and green.
- **Verifier fixes:** `41404bd` (quoted path broke mid-line), `9d83f5b` (blastFoam 3D
  x-only payload named the wrong dropped gauge), `3487c8b` (typed hidden AMR values were
  saved), `79fcd4c` (Z-unit tooltip could never be seen).
- **Not done — 11e, awaiting the owner:** T19 / F17 (needs the on-screen title entries
  of `ui_results_meta.json` re-recorded), F42 (exported gauge labels after a dropped
  gauge — `output/`, changes export bytes only for runs with a drop), F44, F45, D213's
  two layout calls.
- **Commits:** `73ee673`..`d25255f` and the commit of this entry.

---

## 0u. 2026-10-04 — batch `gui-11e` (GUI-11 part e; GUI-11 closed)

Plan: `docs/batches/2026-10-04-gui-11e.md`; reports `…gui-11e.{implA,verifyA,implB,verifyB}.md`;
QA and UX in `docs/qa/2026-10-04-gui-11e/`. Inputs: the owner review of 2026-10-04
(`docs/gui-redesign-decisions.md`, "approve all"), C1 widened by the owner to 24 golden
entries, defaults P1-P5 (D230-D232). Worked in a worktree on D: (`D:\blastlab_wt\gui-11e`).

- **A1, F42 (`output/gauge_summary.gauge_labels`):** after a dropped gauge each point is
  paired with its nearest entered gauge and labelled by the entered number and position
  (Summary .csv, HTML report, Qt Gauge tooltip, Tk summary table). Without a drop, byte-
  identical (3000 random inputs, 0 differences). Tk gate run.
- **A2, F44 (`services/validation.py`):** the drop warning follows each solver's own rule —
  native nearest cell centre on its own auto-refined grid, blastFoam's outward snap
  (`core.refine.snap_obstacles`). New line `on an obstacle face - will be dropped`; four
  `test_case_validate` "face gets none" checks flipped (owner row 2). Verifier probe: 13
  cases, 509 gauges vs `solve_2d` / `solve_3d` / `writer.plan_case`, 0 mismatches.
- **A3, T19 / F17:** the short on-screen 1D title (`1D spherical · 1.0 kg TNT · JWL`) back
  (`git revert` of `0d71956`'s revert); `char_golden/ui_results_meta.json` re-recorded in
  its own commit — exactly 24 entries (10 titles, 10 figure-page and 4 empty-page `fields`
  hashes). Exports byte-identical. Real platform: title x 107-364 of a 405 px canvas.
- **B1, D213 (b) (`ui/run_panel._RunStrip`):** one-row widths from the tiles' needs
  (`PROGRESS_MIN_1ROW` 160); one row from 1220 px, two at 1100 × 720 (D232).
- **Stand as they are (owner):** D200, native TNT-only, D211 / D223, D213 (a).
- **Tests:** Part A suites, 14/16 `test_gui_*`, `_e2e_ui_results.py` (32), `test_ui_run_screen`
  (217), harness D02 / K02; `test_regression` byte-identical after each part. Four char
  suites red identically at base `ee9a4b5` (GUI-12 f). QA (real platform, Qt + Tk, native):
  every item PASS, the Chain 2D face warning PARTIAL (GUI-12 c).
- **Verifier fixes:** none needed (A1-A3, B1 all VERIFIED).
- **Open → `GUI-12`:** gauge-trace subplot titles, wall name in the warning, Chain face
  warning, F45, harness E03, stale char goldens, pairing edge cases, title styles.
- **Commits:** `4c0a834`..`b4f50fc` and the commit of this entry. `7fc34c0` carries git's
  default revert message.

---

## 0v. 2026-10-04 — batch `gui-12-backlog` (GUI-12; branch `gui-12`, fast-forwarded into `master`)

Plan: `docs/batches/2026-10-04-gui-12-backlog.md`; reports `…-backlog-{A,B}.{implement,verify}.md`;
QA `docs/qa/2026-10-04-gui-12-qa/`, UX `docs/qa/2026-10-04-gui-12-ux.md`. Owner: "approve all"
(all items, re-record only explained drift, `test_case_validate` edits, order-preserving pairing).
Decision rows D233-D236.

- **A1 (f), goldens:** all 14 char suites green at `eb7b58c`, `f4d9426` and HEAD here, in three
  setups; HD13 end value -45.3645 = committed. Nothing re-recorded; the home PC's -45.3536 stays
  unexplained (`docs/batches/2026-10-04-gui-12.goldens.md`, GUI-13 i).
- **A2 (g Q1):** `gauge_summary.pair_in_order` pairs survivors with the entered list in order;
  `run_gauges._match` uses it. Verifier: brute force over 3000 random cases, 0 mismatches.
- **A3 (a):** exported gauge-trace titles use the entered number (`Gauge 1/3/4` after a drop),
  Tk Gauges tab too without touching `gui/`; no-drop titles unchanged. `test_plots_gauge_titles.py`.
- **A4 (b):** the drop warning reads `inside Wall i` / `on the face of Wall i`, one helper
  `gauge_drop_reason` shared with Run.
- **A5 (c):** correct as is — a fed Chain stage is not auto-refined, so its warnings follow its
  own dx. Verifier's own probe: 18 rows vs the real solvers, 0 mismatches. Pinned in
  `test_ui_chain_screen`.
- **A6 (g Q2):** the 2D and 3D native face rows moved off the exact x ties; ±1e-12 flips nothing.
- **B1 (d) F45:** `chain_route.handoff_reach` warns when the 2D burst height ≥ the 3D `Lz`;
  warning only, so the default chain now shows "1 warning" on stage 3. Two S5 checks in
  `test_ui_chain_screen` adjusted (verifier: nothing loosened).
- **B2 (e):** harness E03 checks the path the dialog stub answered with.
- **B3 (h):** 1D Field tooltip "Exports use the full title: …"; `screen_title_1d` docstring
  lists the three title styles.
- **Tests:** fast + 14 char suites, Qt screen suites, all 16 `test_gui_*`, harness D02 and
  D01/D02/E03; `test_regression` byte-identical after each part. QA (real platform, Qt + Tk,
  native): 5/5 PASS, 27/27 + 4/4 checks.
- **Verifier fixes:** `644afd9` (D233's check count). Part B: none.
- **Open → `GUI-13`:** default-chain warning (owner call), F45 wording, `G<n>` in the drop
  warning, export footnote, y/z face ties, layout lows at 1100 × 720, HD13 on the home PC.
- **Commits:** `d7332df`..`39e0cb7` and the commit of this entry, on branch `gui-12`.

## 0w. 2026-10-05 — batch `gui-13-backlog` (GUI-13; branch `gui-13`)

Plan `docs/batches/2026-10-04-gui-13-backlog.md`; reports `…-backlog-{A,B,C}.*.md`; QA
`docs/qa/2026-10-05-gui-13-qa/`, UX `docs/qa/2026-10-05-gui-13-ux.md`. Owner "approve all" (D1 keep
the burst ≥ Lz trigger, Q1-Q3). **A1 (Lz 4 m + 1D radius 1.5 m) SKIPPED** under the plan's stop rule:
unprobed blastFoam refuses the 4 m box (~1.23 M > 1.11 M cells); the radius is pinned by
`char_golden/ui_chain_wiring.json` → GUI-14 (a).
- **A2-A6:** F45 names the form's own fields ("Burst z / Height H" for the axisymmetric stage),
  "at or above", advises Lz ≥ the 2D height; drop/outside warnings name `G<n> (x, y) m`; one
  `validation.drop_rule`/`drop_wall` for Setup and Run, Where adds "(dropped)"; export footnote
  only when a gauge is dropped; top-face rows off exact y/z ties.
- **B1-B5:** 1100 × 720 clipping (Run header elides, Results drop note wraps, Tk gauge column
  310/250 px); `!` glyph on the stage-tree row; Run drop note first in warn colour; export-title
  hint on the export buttons; Results labels fall back to the entered numbers.
- **C1:** TODO.md 1079 → 978 lines; records to `docs/history/todo-closed.md`.
- **Tests:** per-task suites, 21 char + 16 `test_gui_*`, `test_regression` byte-identical; Part A
  mutation-tested (10/10 caught). QA real platform: all PASS but the Tk column (still cut at
  1100); `_qa_ui_harness` 1543 ok.
- **Verifier fixes:** `434b60f` (A4 check could not fail), `d4fa2f7` (typo).
- **Commits:** `1e9e853`..`00a3b8e` and this entry, branch `gui-13`.
