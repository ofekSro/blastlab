> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [docs/SCOPE.md](docs/SCOPE.md)

# DONE — the completed record

Open work is in [TODO.md](TODO.md).

> **§5 (the identifier index) and §7 ("verified correct — do not fix") must not be
> deleted.** Code comments cite them by id. Every identifier line in §5 is carried
> here byte-for-byte from the original; only the surrounding prose was translated.
> The untranslated original is in [docs/archive/DONE.md](docs/archive/DONE.md).

**Where the long-form records live now:**

| Topic | File |
|---|---|
| The PySide6 migration (Q1 / M0–M7) and the Tk decision | [docs/history/ui-migration.md](docs/history/ui-migration.md) |
| The three QA nights and the UX review | [docs/history/qa-nights.md](docs/history/qa-nights.md) |
| The independent audit of the blastFoam defect claims | [docs/verification/blastfoam-claims.md](docs/verification/blastfoam-claims.md) |
| The solver-options review against the official guide | [docs/verification/solver-options-review.md](docs/verification/solver-options-review.md) |
| Physics anchors and every measured number | [docs/verification/physics-anchors.md](docs/verification/physics-anchors.md) |
| §0-§0k: the HD1.3 track and the batches of 2026-09-20 … 09-28 | [docs/history/done-2026-09.md](docs/history/done-2026-09.md) |

---

## 0-0k. 2026-09-20 … 09-28 — moved

§0 (the HD1.3 track) and §0a-§0k (the engineering review, HD1-16, OUT-1..5, viewer
polish, P0-5) are in [docs/history/done-2026-09.md](docs/history/done-2026-09.md),
verbatim and with the same section numbers.

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

---

## 1. The timeline — T0–T70

**71 tasks, all closed.** T0–T24 through 2026-09-05, T25–T48 on 09-07 (the QA round and
closing the roadmap), T46–T61 on 09-08, T62–T70 on 09-09.

| # | Task | Ids | Size | Completed |
|---|------|-----|--------|--------|
| T0 | Commit untracked work | A9 | 10 min | 2026-09-02 |
| T1 | Harden the foam stop/ingest path | B1, B2, B15 | S–M | ✔ |
| T2 | Wrong-data display: 3D replay slice + viewer final frame + thinning | B3, B4, B20 | S | ✔ |
| T3 | Units & labels: kPa everywhere, impulse naming | B8, B9 | S | ✔ |
| T4 | Runs-dir safety: unique dirs, live-run guard, orphan reaping | B13, B14 | S | ✔ |
| T5 | Papercuts bundle | B7, G1, B22, G6a | S | ✔ |
| T6 | Chain validation + visible/stoppable foam preflight | B5, B6, G5 | M | ✔ |
| T7 | Native solver warnings through hooks | B11 | M | ✔ |
| T8 | Native fixes with ONE re-baseline | B10, B12, B18 | S | ✔ |
| T9 | Extract the shared foam run loop | A1, A2, A3, A4(foam) | M | ✔ |
| T10 | Foam accumulator correctness | B16, B17, B21 | S–M | ✔ |
| T11 | Peak-overpressure / impulse views in Results | N1 | M | ✔ |
| T12 | Per-gauge engineering summary + CSV | N2, B9 | S–M | ✔ |
| T13 | 3D viewer colour-range plumbing + viz3d dead code | B19, A4(viz), A8 | S | ✔ |
| T14 | Foam run browser + auto-cleanup | N8 | M | ✔ |
| T15 | VTK/ParaView export | N4 | S | ✔ |
| T16 | Afterburn model | N3 | M | ✔ |
| T17–T19 | Local (static) refinement: core → foam → 3D viewer | N15 | M–L | ✔ |
| T20–T24 | Dynamic AMR: core → ingest → GUI → 3D viewer → live slice/wedge fix | N16, B25 | M–L | 2026-09-05 |
| T25 | QA S1: validation/preview memory safety, defaults, finite input | QA-01..04, 14, 15; B27, G10 | M | 2026-09-07 |
| T26 | QA S1: chain feed3d lifecycle + profile-stage validation | QA-05, 06; B26 | S | 2026-09-07 |
| T27 | QA: layout — Run-tab 3D viewport, status card height, truncations | QA-17, 25, 27; G11 | S–M | 2026-09-07 |
| T28 | QA: chain feedback (stage select, workspace, stage prefix) | QA-23; G12 | S | 2026-09-07 |
| T29 | QA: validation & feedback bundle | G3, QA-16, 22 | M | 2026-09-07 |
| T30 | QA: user-named runs + loaded-run replay | N9, QA-24; G2 | S–M | 2026-09-07 |
| T31 | QA: UI stalls + preview extras + viewer field availability | G4, G8, QA-18, 21, 17 | M | 2026-09-07 |
| T32 | QA: theme/affordance + accelerators + persistence | G9, G13, QA-19, 28, 29 | S–M | 2026-09-07 |
| T33 | QA: papercuts | QA-20, 26, 30..35 | S | 2026-09-07 |
| T34 | GUI: global solver mode (sidebar selector; hide, don't grey) | — | L | 2026-09-07 |
| T35 | `test_foam_parallel` determinism check | B23 | S | 2026-09-07 |
| T36 | Mass/energy-conserving resolved-charge init in 2D/3D | B24 | S | 2026-09-07 |
| T37 | Hardening bundle: dead code, shared constants, stdout canaries | A4, A5, A6, A7 | S | 2026-09-07 |
| T38 | Live-view niceties: foam cadence hint, 2D live Min/Max | G7 | S | 2026-09-07 |
| T39 | Charge-mass rasterisation deficit (foam) | N5 | S–M | 2026-09-07 |
| T40 | Arrival-time characterisation: AMR probe cell + foam near-field lag | N16-a, W1 | M | 2026-09-07 |
| T41 | Chains INTO blastFoam (profile-initialised foam stages) | N7 | M–L | 2026-09-07 |
| T48 | Hardware-aware run plan: cores + RAM → MPI ranks and a cell cap | N17 | S–M | 2026-09-07 |
| T42 | Parallel AMR (direct `processor*/` reads) | N16-b | M | 2026-09-07 |
| T43 | Resume a stopped foam run | N6 | M | 2026-09-07 |
| T44 | Gauge fields beyond p (foam) | N12 | S–M | 2026-09-07 |
| T45 | CSV export of field maps + one-click HTML report | N14, N13 | M | 2026-09-07 |
| T46 | Materials beyond TNT for the native solvers | N11 | M | 2026-09-08 |
| T47 | MUSCL second-order native reconstruction (opt-in) | N10 | L | 2026-09-08 |
| T49 | Mesh overlay on the animation a run writes | N15 | S | 2026-09-08 |
| T50 | Boundary kinds: transmit / reflect / terminate | N18 | M | 2026-09-08 |
| T51 | Trigger gauge: terminate and/or remap on arrival | N19 | M | 2026-09-08 |
| T52 | An end time for 1D and 2D runs too | N18 | S | 2026-09-08 |
| T53 | Gauges drawn in the live view and the animation | N19 | S | 2026-09-08 |
| T54 | AMR mesh in the exported video | N15 | S | 2026-09-08 |
| T55 | Bound the replay-frame record's memory | N15 | S | 2026-09-08 |
| T56 | MP4 export reachable (label, dialog, default, ffmpeg) | N15 | S | 2026-09-08 |
| T57 | Loading a PARALLEL AMR run (post-mortem) | N16-b | S | 2026-09-08 |
| T58 | A title line of your own on the Results figures | N20 | S | 2026-09-08 |
| T59 | 1D model preview: the spherical sector | N20 | S | 2026-09-08 |
| T60 | A boundary kind for the end of the 1D sector | N18 | S | 2026-09-08 |
| T61 | The 1D live pane was pinned to 10 kPa | G14 | S | 2026-09-08 |
| T62 | A 1D→3D remap could never run on blastFoam | N7 | S | 2026-09-09 |
| T63 | The trigger gauge leaves 1D (both solvers) | N19 | S | 2026-09-09 |
| T64 | Hardware honesty: per-field measured/cached/unknown, /proc/meminfo, no sticky cache | N21 | S–M | 2026-09-09 |
| T65 | Unknown hardware tightens the caps instead of loosening them | N21 | S | 2026-09-09 |
| T66 | Machine fingerprint + TTL for persisted hardware; settings write bugs | N21 | S–M | 2026-09-09 |
| T67 | Native cell caps from the Windows host's RAM (ctypes) | N21 | M | 2026-09-09 |
| T68 | An explicit `n_procs` is a ceiling, not a command | N21 | S | 2026-09-09 |
| T69 | Frame budgets derived from host RAM; cores beat MAX_AUTO_PROCS | N21 | S | 2026-09-09 |
| T70 | Dynamic AMR for profile-initialised stages | N7, N16 | S–M | 2026-09-09 |
| T71 | The heavy-run night of 2026-09-09/10 and the fixes it produced | P5 | L | 2026-09-10 |

**Dependencies that were live at the time** (for the record): T27–T33 were independent
of each other and came before T34 (which re-laid out the GUI); T35 before any task that
runs `test_foam_parallel`; T40 before T42; T48 before T42.

---

## 2. T0–T26 — the foundation, the fixes and the first capabilities

Full briefs for T0–T26 live in git history (`git show 73ca834:ROADMAP.md`, and commits
`ba37a65`, `73ca834`, `3cb800c`, `a6c7463`). What was done, by group:

**Bugs on the foam path (T1, T2, T10).** Closed: a truncated `uniform` internalField
that raised `AttributeError`; a stop that escalated to a kill and broke finalize; an
unhandled `TimeoutExpired` in the stop paths; a 3D replay that hard-coded the x-z plane;
the final frame vanishing from playback; FrameStore thinning; out-of-order ingest; stale
peak/impulse from the function object; stop distances in a multi-charge case.

**Run-directory safety and hygiene (T4).** Unique run names, a guard against deleting a
live run, orphan reaping.

**Units and labels (T3).** kPa everywhere, and net impulse separated from positive-phase
impulse.

**Native solvers (T7, T8).** Warnings routed through hooks instead of stdout; a
duplicated last gauge row; 1D snapshot scheduling; grids that silently shrank by one
cell. **One re-baseline**, batched.

**Architecture (T9, T13).** The foam run loop, which existed in triplicate, was unified;
geometry logic, which existed in quadruplicate, became `core/geometry.py`; private
imports in postmortem; colour-range plumbing in the 3D viewer; dead code in viz3d;
control-message delivery in viz3d.

**Capabilities (T11–T16).** Peak-pressure and impulse maps in Results; a per-gauge
engineering summary + CSV; a foam run browser with automatic cleanup; VTK/ParaView
export; the afterburn model (`none | miller`).

**Static refinement (T17–T19)** and **dynamic AMR (T20–T24)** — `adaptiveFvMesh`,
`densityGradient` as the then-default estimator, AMR and static zones being mutually
exclusive, the display level bounding the display grid, serial in v1. An unbounded 3D AMR
case once killed the 4 GB VM — the 3D e2e is capped at 300k cells.

**T25–T26 (QA S1).** Memory safety in validation and preview, defaults that pass
validation, non-finite input rejected, the feed3d lifecycle in a chain, and validation for
a profile stage. Detail in §6.

---

## 3. T27–T71 — the detail

### T27–T33 · the QA round's fixes (2026-09-07)

**T27 — layout.** The Run tab parks the ttk sash after the first real layout; the status
card is height-bounded and scrolls; truncated headings fixed.
**T28 — chain feedback:** stage selection, the workspace, the stage prefix.
**T29 — validation and feedback bundle** (G3): no more split-brain validation or silent
swallowing; file-open errors say what happened.
**T30 — user-named runs** and replay for a loaded run.
**T31 — UI stalls, preview extras, viewer field availability.** `feed_result`
**2364 ms → 259 ms**; a preview cache; the worst gap in a native 3D run 3544 → 1100 ms.
**T32 — theme/affordance, accelerators, persistence.**
**T33 — papercuts** (QA-20, 26, 30…35).

### T34 — a global solver mode

One app-wide native | blastFoam switch in the sidebar. Every tab re-lays itself out for
the chosen mode and **hides — never greys — the controls that do not apply.** Hidden
values stay in the form but are not written to the case.

### T35 — determinism in `test_foam_parallel` (B23) · owner decision

### T36 — mass/energy-conserving charge initialisation in 2D/3D (B24)

Energy exact to 4e-16; clipped volumes verified to 2e-16 against closed forms and 1.7e-6
against a 1200³ brute-force count. Mass keeps the staircase deficit by design.

### T37 — the hardening bundle (A4, A5, A6, A7)

Dead code removed; guard-rail constants that had been duplicated as literals shared;
a canary on the `Time =` regex; `_decode_surface` no longer degrades silently.

### T38 — live-view refinements (G7)

### T39 — the charge-mass rasterisation deficit (N5)

`constants.FOAM_EXP_CELLS = 8` now drives every blastFoam charge target (1D/2D/3D global
refine, the automatic zone level, the AMR level check, the validation notes) through
`refine.exp_cells(case)`; **native keeps `MIN_EXP_CELLS = 5` and test_regression stays
byte-identical**. `refine.set_mass_fraction` predicts what `sphericalMassToCell` will
deposit; `validate_case` reports "Charge cells: N at dx → ~F of the M kg set by
blastFoam"; `backend._scan_set_mass` forwards blastFoam's own line as a `[note]`.

> **The original "~0.85 of requested mass" premise did not reproduce.** Measured against
> blastFoam's own set-volume line the deposit is 0.979 (3D, 5 cells) / 1.027 (3D, 8
> cells) / 0.995 (1D, both). Over 400 random burst offsets 8 cells mainly cuts the
> SPREAD — 3D RMS 1.00 % → 0.41 %, axisym 3.67 % → 2.95 % — for 1.6×/2.6×/4.1× the cells
> in 1D/2D/3D. **The real gain is the resolved detonation:** KB anchor 0.72–0.77 →
> 0.85–0.89; foam-vs-native arrival gap 13.7/7.3/5.5/3.8 % → 4.5/1.5/1.3/0.7 %.

### T40 — arrival-time characterisation: the AMR probe cell (N16-a) + near-field lag (W1)

Both studies run; **the `adjustLocations` hypothesis is REFUTED** — switching it off moves
the AMR-vs-static arrival by 0.15 percentage points (blastProbes reports the containing
cell's value either way), so the default stays `yes`. The +18 % is a real resolution
difference at the gauge: the AMR mesh follows the shock and is at its finest level there,
while the static `zone` reference refines only around the charge. Measured with
`_e2e_foam_probe_study.py`: +4.2 % at a cell corner, −11.5 % at a base-cell centre, point
peaks 57–171 % apart.

**W1 characterised:** foam lags native +36.7 % / +23.6 % at r = 0.6 / 1.0 m with the
default `linear` activation and +23.1 % / +12.8 % with `none` — roughly half the lag is
the activation model burning the charge at vDet, the rest is the resolved charge's
expansion. `none` overshoots the peaks (1.43× / 1.36× native), so **`linear` stays the
default** and the tolerances stay as they are.

### T41 — chains INTO blastFoam (N7)

A blastFoam stage can start from a 1D or 2D profile. `writer.profile_state` runs the SAME
remap the native solvers use onto the case grid, and `_profile_fields` emits p, T, U,
`alpha.expl`, `rho.expl`, `rho.air` as `nonuniform List<scalar|vector>` internalFields in
the mesh's cell order (`ravel(order='F')`, fluid cells only on a carved mesh — the exact
inverse of `reader.to_grid`). The two-phase split is sharp (alpha is 0 or 1), which makes
the mass transfer exact.

> **The one physical clock:** the state is emitted into a time directory named for the
> profile's t0 and picked up with `startFrom latestTime` — **without that the chained
> gauges read 53 %/34 % early.** Measured against the same domain initialised directly
> from the charge: arrivals +2.31 %/+3.36 %, peaks +4.87 %/+3.37 %; emitted mass/energy
> match the profile to 1e-11.

### T42 — parallel AMR: direct `processor*/` reads (N16-b)

The ingest reads `processor*/` directly and concatenates per rank (cell-for-cell identical
to the serial read, unit-pinned); `maybe_reconstruct` skips decomposed runs.
**340 s → 237 s (1.43×) at np=2.**

Serial-vs-parallel AMR are two self-consistent discretisations: arrivals agree 0.3–0.5 %,
point peaks fluctuate 0.15–4 %, impulse drifts 4–9 % late. **Acceptance (owner
decision):** per-gauge arrival ≤ 1 % and loading-region peak-map median ≤ 1 %
(**0.605 % measured**), point values characterised ungated. `balance no` stays the
default; revisit balancing only for asymmetric refinement or 4+ ranks.

### T43 — resuming a stopped foam run (N6)

`backend.resume_run(case_dir, hooks)` rebuilds the spec the way postmortem does, refuses a
run whose solver is still alive (or whose state WSL cannot report), resets the
`stopAt writeNow` a stop left in the controlDict, flips `startFrom → latestTime`, and
re-enters the ORDINARY `solve_Xd_foam` with that spec. **No other special-casing was
needed** — the shared run loop's ingest is disk-driven and ordered, so it first replays the
times the stopped run wrote and then follows the new writes. Prefix-identical gauges, peak
map within 0.5 %, a Resume button in the run browser.

### T44 — gauge fields beyond p (N12, foam only)

`read_probes` attaches `speeds` and `rhos` **ONLY when their rows align sample-for-sample
with p's** — a torn or missing extra degrades to p-only rather than ever misaligning
(pinned by a torn-U fixture test). **Native stays p-only and byte-pinned.**

### T45 — CSV export of field maps (N14) + a one-click HTML report (N13)

`blastlab/output/report.py`, pure writers shared by two Results-tab buttons. The HTML
report is one self-contained file: banner, gauge table, inlined PNGs, the case JSON, and
the KB free-air comparison when applicable.

### T46 — materials beyond TNT for the native solvers (N11)

`eos.material_jwl(name)` — **'TNT' returns the byte-pinned `constants.JWL_TNT` OBJECT
itself**, everything else comes from the shared materials table as a dict with the same
keys. **test_regression is byte-identical, which is the whole point of the TNT-object fast
path.** C4 1D peak ×1.24 over TNT.

### T47 — second-order MUSCL reconstruction, opt-in (N10)

Opt-in via `case.order == 2` (default 1; **test_regression stays byte-identical**).
**r = 1.5 m: 0.75 → 0.90 of KB; anchor sweep 0.74–0.81 → 0.85–0.89; with order 2 the
foam/native peak ratios collapse to 0.97–1.01.**

### T48 — a hardware-aware run plan (N17)

`env.plan_run(...)` is a pure function returning `RunPlan(...)`. **`hardware()` returns
cached values only — it is called on every keystroke by `validate_case` and must never
touch WSL.** An 11-row pinned decision table and a 432-case invariant sweep.

**Measured `BYTES_PER_CELL = 2650`**; headroom 1 (was an unjustified 2),
`CELLS_PER_RANK = 50_000`, `RAM_GB_PER_RANK = 2`, caps at 0.70/0.35 of VM RAM.

### T49 — a mesh overlay on the animation a run writes (N15)

New case field `anim_mesh` (file version 5 → 6). **No solver code touched.**

### T50–T54 — boundary kinds, end time, trigger gauge, gauge markers (N18, N19)

**Why (owner request):** `open` did two jobs at once — it was the transmissive ghost-copy
AND it ended the run the moment `p > 1.001·P_air` reached it. There was no way to let a
wave leave and keep solving.

**T50 — the vocabulary.** `core/bc.py` owns
`BC_KINDS = (transmit, reflect, terminate)`, `BC_LEGACY = {open: transmit, wall: reflect}`
and `normalize_bc(s)`, which every reader goes through, so pre-T50 case files still load
(with one `[note]` naming the mapping — a silent `open → transmit` would quietly drop a
run's stop condition). Two different questions are asked of `bcs` and they no longer have
the same answer: `geometry.terminate_edge_mask` feeds the stop condition and counts ONLY
terminate sides, while `stop_dists_2d/3d` size the snapshot radii off EVERY non-reflecting
side. `_patch_type` / `_bc_entry` map the new kinds onto the SAME OpenFOAM patch types, so
the writer goldens are byte-identical.

> **Owner decision, and its cost:** legacy `open` maps to `transmit` and the shipped
> defaults are `transmit`, so a default run is no longer ended by the wave leaving — it
> runs to the safety cap or `t_end`. **That is up to ~10× more solver time, worst on
> blastFoam.** Mitigations in the same commit: `validate_case` warns when a case has no
> terminate side and no end time (naming the cap in ms), the run banner says
> `safety cap (no terminate boundaries)`, and T52 gives every dimension an end time.

**T51 — the trigger gauge.** `trigger_gauge` (1-based, None = off), `trigger_action`
(`terminate` | `remap` | `remap+terminate`) and `trigger_file`. The check sits in the
gauge-sampling block each solver already had, so it costs one comparison per step and fires
once. 3D is terminate-only — there is no 3D remap format.
> **A bug found by the owner mid-task:** a stopped blastFoam run died with
> `NameError: name 'trig_k' is not defined` — the trigger is armed inside
> `solve_2d/3d_foam` but the meta is assembled in `finalize_2d/3d`, also called by
> `postmortem.load_run`, which never watched the run. Both now take `trig_k`/`trigger` as
> keyword arguments defaulting to None.

**T52 — end time.** `t_end` on `Case1D`/`Case2D`. Deliberately transcript-neutral at
`t_end = 0`. Precedence: whichever comes first — a terminate boundary, the trigger gauge,
or the end time.
**T53 — gauge markers.** A ringed dot plus `G<n>` per gauge, the trigger gauge heavier and
starred. 3D keeps only the gauges the plotted plane actually cuts.
**T54 — AMR in the exported video**, the real defect, found by the owner.

### T55–T61 — the 2026-09-08 bundle

**T55** bounds the replay record's memory (**614 MB → 199 MB**). **T56** makes MP4 export
reachable. **T57** loads a parallel AMR run post-mortem. **T58** a title line of your own on
the Results figures. **T59** the 1D model preview — the spherical sector. **T60** a boundary
kind for the end of the 1D sector. **T61** the 1D live pane had been pinned to 10 kPa (G14).

### T62 — a 1D→3D remap could never run on blastFoam (N7)

### T63 — the trigger gauge leaves 1D (N19) · owner decision

### T64–T69 — a robust cross-machine hardware model (N21)

Honest per-field sources (measured / cached / unknown); unknown hardware **tightens** the
caps instead of loosening them; a machine fingerprint + TTL for persisted hardware; native
cell caps derived from the Windows host's RAM via ctypes; an explicit `n_procs` is a
**ceiling, not a command**; frame budgets derived from host RAM.

### T70 — dynamic AMR for a profile-initialised stage (N7 + N16) · owner request

### T71 — the heavy-run night of 2026-09-09/10, and the fixes it produced

Full record: [docs/history/qa-nights.md](docs/history/qa-nights.md). The four commits that
landed from it: `c2b661a`, `4e8c075`, `c66eae8`, `b368046`.

---

## 4. The measured numbers

**Moved to [docs/verification/physics-anchors.md](docs/verification/physics-anchors.md)**,
which is now the single place for them. The headline figures:

- **Native vs blastFoam:** foam peaks 1.10–1.16× native at r = 1–4 m, arrivals within
  0.7–4.5 %. With MUSCL order 2 the ratios collapse to **0.97–1.01**.
- **Kingery-Bulmash anchor:** 0.72–0.77 before T39 → **0.85–0.89** with the 8-cell charge →
  **1.02–1.20 with afterburn `miller`**. The band in the test is 0.80–1.35.
- **Hardware:** `BYTES_PER_CELL = 2650` in the application; **2,696 measured** on an
  i7-14700 (R² = 0.9996), a 1.7 % gap — the constant does **not** need measuring per
  machine.

---

## 5. Identifier index (B / G / A / N / W)

> **Code comments cite these identifiers. Do not delete this section.**

**Bugs (B)**
- B1 truncated `uniform` internalField AttributeError — DONE (T1)
- B2 kill-escalated stop crashed finalize — DONE (T1)
- B3 3D replay hardcoded the x-z plane — DONE (T2)
- B4 final frame missing from 3D viewer playback — DONE (T2)
- B5 chains bypassed validate_case — DONE (T6)
- B6 Stop could not interrupt foam preflight — DONE (T6)
- B7 foam progress bar at 0 until first write — DONE (T5)
- B8 Pa/kPa inconsistency — DONE (T3)
- B9 net vs positive-phase impulse naming — DONE (T3/T12)
- B10 duplicated last gauge row — DONE (T8)
- B11 native warnings bypassed hooks — DONE (T7)
- B12 1D snapshot scheduling — DONE (T8)
- B13 run-dir name collision — DONE (T4)
- B14 `--clean-foam-runs` live-run guard + orphan reaping — DONE (T4)
- B15 uncaught TimeoutExpired in stop paths — DONE (T1)
- B16 out-of-order ingest — DONE (T10)
- B17 stale FO peak/impulse — DONE (T10)
- B18 grids silently shrank one cell — DONE (T8)
- B19 3D viewer colour-range plumbing — DONE (T13)
- B20 FrameStore thinning — DONE (T2)
- B21 multi-charge stop distances — DONE (T10)
- B22 'Run failed' dialog text — DONE (T5)
- B23 `test_foam_parallel` determinism fails randomly — DONE (2026-09-07, T35)
- B24 resolved-charge init not mass/energy conserving (±3 %) — DONE (2026-09-07, T36)
- B25 controlDict rewrites inside fileModificationSkew ignored — DONE (2026-09-05, T18)
- B26 chain 3D stage reused the 2D revolved feed — DONE (2026-09-07, QA-05)
- B27 validation/preview allocated the full fine grid — DONE (2026-09-07, QA-01..04)

**GUI (G)**
- G1 "Initialise Model" hint erased — DONE (T5)
- G2 results accumulate / duplicate labels — de-dup + Remove DONE (QA-13); user-named runs DONE (T30)
- G3 validation split-brain / silent swallowing — DONE (2026-09-07, T29)
- G4 replay / preview stalls (idle-CPU half refuted) — DONE (2026-09-07, T31)
- G5 chain start race — DONE (T6)
- G6 progress < 100 % (DONE, T5); theme half refuted by QA (mesh overlay colour cosmetic) — closed
- G7 live-view niceties (cadence hint, 2D Min/Max) — DONE (2026-09-07, T38)
- G8 preview lacks extra charges / det points — DONE (2026-09-07, QA-21 + T31)
- G9 accelerators / persistence / focus — DONE (2026-09-07, T32)
- G10 default 3D case invalid, nan/inf accepted — DONE (2026-09-07, QA-14/15)
- G11 layout at 1280×840 / 1100×720 — DONE (QA-07/08 + T27)
- G12 stale state — DONE (QA-09..12 + T28)
- G13 light-mode affordance — DONE (2026-09-07, T32)
- G14 1D live pane pinned to 10 kPa — DONE (2026-09-08, T61)

**Architecture (A)**
- A1 foam run loop triplicated — DONE (T9)
- A2 geometry logic quadruplicated — DONE (T9, `core/geometry.py`)
- A3 postmortem private imports — DONE (T9)
- A4 dead code — foam + viz3d DONE (T9/T13); native DONE (2026-09-07, T37)
- A5 guard-rail constants duplicated as literals — DONE (2026-09-07, T37)
- A6 `Time =` regex needs a canary — DONE (2026-09-07, T37)
- A7 `_decode_surface` silent degrade — DONE (2026-09-07, T37)
- A8 viz3d control-message delivery — DONE (T13)
- A9 commit hygiene — DONE (2026-09-02) · **re-opened, then closed 2026-09-09 (`e344d17`)**
- A10 regression discipline — standing rule

**New capabilities (N)**
- N1 peak/impulse views — DONE (T11) · N2 per-gauge summary + CSV — DONE (T12)
- N3 afterburn (`none | miller`) — DONE (T16); non-TNT Q0 from oxygen balance only, uncalibrated
- N4 VTK export — DONE (T15) · N5 charge-mass rasterisation — DONE (T39)
- N6 resume a stopped run — DONE (T43; a profile+AMR stage does NOT resume — closed, see P1-5 history)
- N7 chains INTO blastFoam — DONE (T41, fixed T62, AMR opened up in T70; static zones still refused)
- N8 foam run browser + auto-cleanup — DONE (T14) · N9 user-named runs — DONE (T30)
- N10 MUSCL second order — DONE (T47) · N11 native materials beyond TNT — DONE (T46)
- N12 gauge fields beyond p — DONE (T44) · N13 HTML report / N14 CSV field maps — DONE (T45)
- N15 local (static) refinement + show-mesh — DONE (T17–T19); mesh on the run's own animation (T49);
  AMR in the video (T54); replay memory (T55); MP4 (T56)
- N16 dynamic AMR — DONE (T20–T24); N16-a probe cell DONE (T40); N16-b parallel DONE (T42, load fixed T57)
- N17 hardware-aware run plan — DONE (T48)
- N18 boundary kinds + per-run end time — DONE (T50, T52, T60)
- N19 trigger gauge + gauge markers — DONE (T51, T53); **2D/3D only since T63**
- N20 Results title line + 1D model preview — DONE (T58, T59)
- N21 cross-machine hardware model: honest sources, conservative-on-unknown
  caps, machine fingerprint + TTL, host-RAM native caps, n_procs clamp — DONE
  (T64–T69)

**Watch items (W)**
- **W1** foam near-field arrival lag — CHARACTERISED (T40), no action; `linear` stays the default
- **W2** blastProbes flushes buffered gauge samples only at a graceful End — **REFUTED by
  measurement (2026-09-14)**; see §7b. `OSstream::endl()` is write+flush per sample line, and
  a `kill -9` mid-step lost zero rows.

**Later identifier series**

- **N5-4 … N5-12** — the chain hand-off and parallel-ignition investigation of 2026-09-18/20.
  `N5-6` (rotateFields spike, negative result), `N5-7` (`det_radii` is now the default),
  `N5-11` (`RHO_MIN`), `N5-12` (`programmedIgnition` + delays/radii).
- **N2-01 … N2-16**, **N3-01**, **UX-01 … UX-06** — the QA nights and the UX review.
  See [docs/history/qa-nights.md](docs/history/qa-nights.md).
- **HD1-1 … HD1-11c** — the HD1.3 track. See §0.
- **P0-x … P5-x** — the priority queue. Closed items are in §7b and in the history files;
  what remains open is in [TODO.md](TODO.md).
- **B0 / B1 / B2 / N1–N4 of the solver-options review** are a **separate, document-local
  numbering** that collides with the B/N index above. Always write "solver review B0",
  never a bare "B0". See
  [docs/verification/solver-options-review.md](docs/verification/solver-options-review.md).

---

## 6. The QA round of 2026-09-07 (QA-01…QA-35)

**What was done:** the real GUI was driven on screen (1280×840, dark then light) through
the widgets' own commands, **367 screenshots across 59 scenarios**: all four tabs,
validation, native 1D/2D/3D runs, a chain, **11 real blastFoam runs in WSL** (static
refinement, 2D and 3D AMR, Stop during meshing and during the solve, the run browser, VTK,
post-mortem loading, closing the window mid-run), theme switching and robustness. Found
6 S1, 9 S2, 10 S3 and 11 S4 findings — **all fixed** in T25–T33.

**S1 — crashes (fixed, T25/T26).** QA-01/02/03 (B27): `refine.plan_levels`/`_plan_amr`
reject a degenerate or memory-exploding mesh with `ValueError` **before** allocating a full
array; QA-04: `Plan.solid_fine` trims `expand(solid_base)` to the level map's shape (641 vs
642); QA-05 (B26): `GuiHooks.run_started` drops the previous stage's feed/scene; QA-06:
`validate_case` checks the burst centre against the domain in every init mode.

**S2 — wrong data and layout (fixed, T25).** QA-07 a minimum width for the input column
plus label wrapping; QA-08 a two-line Results title; QA-09 `View3DPanel` raises the Display
tab after construction; QA-10 `set_running` resets the chips and reads "PAUSED at step N";
QA-11 the live panel switches to "waiting for the solver…"; QA-12 the replay canvas is
explained and empty when there are no frames; QA-13 repeated-label numbering + a Remove
button; **QA-14 the 3D form opens on a case that passes validation** (8 kg in a 3 m box at
2 cm = 3.4M cells, instead of a default that refined to ~852M); QA-15 non-finite and
fractional input rejected. A cap error now explains the cause.

**S3 (fixed, T27/T29/T31/T32/T33).** QA-16 (G3) validation; QA-17 layout and fields;
**QA-18 performance — `feed_result` 2364 ms → 259 ms**, a preview cache, worst gap in a
native 3D run 3544 → 1100 ms; QA-19 light-mode visibility; QA-20 log line wrapping; QA-21
(G8) extra charges and burst points in the previews; QA-22 file-open error messages; QA-23
chain feedback; QA-24 replay for a loaded run; QA-25 the validation card is height-bounded
and scrolls.

**S4 (fixed, T27/T32/T33).** QA-26 `p max` in kPa; QA-27 truncated headings; QA-28
matplotlib Back/Forward buttons removed; QA-29 (G9) accelerators and persistence; QA-30 a
scrollbar in the run browser; QA-31 clipping the top 0.5 % on peak/impulse maps; QA-32 a
folded AMR log + a `cells` chip; QA-33 gauge table headings; QA-34 the logo file is closed;
QA-35 a disk note for AMR with the run total.

> **QA-18 — a wrong attribution corrected.** The 3.5 seconds attributed to "AMR frames"
> were in fact building the 3D preview in `set_case`, which the cache had already fixed.
> `mesh_polydata` costs 262–320 ms once (VTK warm-up) and then ~5–8 ms per frame. **No
> throttle was needed**, and the original attribution was wrong.

---

## 7. Verified correct — do not "fix"

Axisym momentum source is exactly well-balanced against the face-area metric; `bc.py` mirror
signs are correct; the y/z-sweep moveaxis round trip is index-correct (pinned by T1); smear
init conserves mass/energy to 1e-12 (T10); foam `to_grid` F-order reshape ↔ viewer
`ravel(order='F')` ↔ VTK point order is consistent end-to-end (a transpose trips
`test_viz3d_scene` S2c); obstacle scatter/carve ordering matches boxToCell; the GUI
worker/queue architecture (latest-wins frame slots, exception-hardened drain, Tk-thread-only
widget access) is clean — **treat it as the pattern for new panels.**

**The axis limitation in axisymmetric cases — structural, not a bug:** the wedge's axis
cells are prisms, and hexRef8 does not refine them. So under AMR the charge stays coarse in
the axis column (`validate_amr` warns), and under static refinement only level 1 is possible
on the axis and a zone touching the axis is refused (`validate_zones`). If the field close to
the axis matters — use a finer base cell or planar geometry (which refines everywhere).
**Do not try to "fix" this on the Python side.**

> **⚠ One clause of the above was later measured to be wrong.** In the P1-6 investigation
> (2026-09-15) it was measured directly that **`adaptiveFvMesh` *does* split wedge axis
> cells** — `cellLevel = 1` on the axis column — contrary to the "prisms do not refine"
> folklore. That splitting is the mechanism behind the axis-drain SIGFPE, and it is why
> `Lohner` replaced `densityGradient` as the default estimator. The *practical* advice above
> still holds; the stated reason does not.

Native↔foam physics: foam peaks 1.10–1.16× native at r = 1–4 m with arrivals within
0.7–4.5 %, both monotonic; KB anchor 1.02–1.20 with afterburn `miller`.

**Confirmed by eye in the QA round:** static refinement + Show mesh everywhere, AMR
per-frame, the gauge table + CSV, the run browser, VTK export, post-mortem loading identical
to a live run, Stop at every stage, and no orphaned solvers.

---

## 7a/7b. The QA nights — what landed and was verified

Full analysis: [docs/history/qa-nights.md](docs/history/qa-nights.md). The commits:

| Finding | Commit | The proof |
|---|---|---|
| The GUI matrix ran for the first time ever | `a5ef729` | `--smoke` exit 0, **7/7 real screenshots, 1,059–1,788 distinct colours** each (colour count, not luminance — a PrintWindow that draws only the frame gives uniform grey that passes a luminance check) |
| N2-02 / N2-03 (test bugs) | `75a9e9e` | The product answered correctly in both; the test could not accept the answer |
| N2-04 (`C10` asserted on an impossible label) | `62984c7` | The assertion moved to where it is true; the 3D case got the one that **is** true of it |
| N2-09 the gauge table | `5afe1ca` | `mapped=True` at every height 840–1080 (it had vanished below 960) |
| `wait_log` (a tool fault caught within the hour) | `736c309` | Baseline taken at the moment of the click; E03 15 s, zero findings |
| N2-06/10/11 cosmetics | `2fa79f2` | One screenshot shows all three |
| N2-12 the Run freeze | batch | **13,266 → 2,643 ms** — a VTK import avalanche, warmed in a daemon |
| N2-05 `level_map` | batch | **Byte-identical** against a baseline captured beforehand; 1,445 → 245 ms |
| N2-07 `rho0` in the preview | batch | New ANFO tests; there is **one** materials table, not two |
| **N2-13 + N2-14 — the chain** | `b343d89` + `eeb8853` | **4/4 chains identical to the digit** (s1=0.050, s2=0.194, t0=0.00019422544); stage-3 IC: T ≤ 2,149 K (was 8.3e6), zero floored cells |
| N2-15 — the 2D arrival stop on the live sample | `08ce68d` | R2 had run 8.7 h past arrival because the check was ingest-gated (2,193 samples queued) |
| N2-08 — GL warm-up at idle | `ab8acfd` | First feed 1,683 → **971 ms**; E06's gate passes for the first time |
| N2-16 + the R2 fixture tie | `c130210`, `84c1099` | An obstacle edge sat exactly on a cell-centre line and Python and foam broke the tie opposite ways (171,580 vs 171,604 cells) |
| Obstacle snapping to cell faces | `4e97108` | `refine.snap_obstacles` snaps outward at plan time; N2-16's ties are **structurally** impossible. Goldens: exactly two boxToCell lines |
| N3-01 — live 3D arrival stop + a deterministic symmetry gate | `f5feb93` | Before: 4 FAIL of 6; after: **5/5** |
| UX-01/02/03 · UX-04 · UX-05/06 | `a0dd97d` · `fcf34c2` · `8bc1e19` | All six UX findings closed |
| E06 closed | `04fcbee` | The ~1 s was a **first-in-process** BlastScene (809 of 924 ms); a third idle warm-up takes the first feed 980 → **272 ms** |
| The MPI directional bias root found | `12a255a` | np=1 → 0.10 % · np=2 → 0.26 % · np=8 → 4.85 %, independent of the slice axis. The test pins np=2, giving a machine-independent gate with 19× margin |
| P2-3/P2-4 — the e2e completion round | `b2a67ef`, `406810d` | obstacle3d, refine3d, amr3d, chain, chain_amr all PASS. **The whole `_e2e_foam_*` family is covered by a real run** |
| P5-1 closed — "intermittently crashes" is not structural | — | 25/25 runs, full PASS, signature identical to the digit. The instrumentation stays armed |
| W2/P1-2 refuted by measurement | — | Source: `OSstream::endl()` is write+flush per sample line. Measurement: `kill -9` mid-step — 208 rows in ext4 = 208 through 9p, immediately and after 30 s. **Zero loss** |

> **The chain took four layers to become deterministic** (a clock-dependent stop → a
> clock-dependent write schedule → anchoring to the write before arrival → scanning forward
> because the tail vents back), each locked by measurement. **The key insight:** the old
> hand-off was a post-venting state (2–4.7 ms instead of 0.194 ms) — that is where the vacuum
> states came from.

---

## 8. Baselines, file versions and commits

**`test_regression` policy:** must stay green byte-for-byte. Re-baseline only when a task
says so explicitly, and in the same commit. Foam goldens regenerate only through
`python blastlab/tests/test_foam_writer.py --update` plus an eyeballed diff.

**Re-baselines performed:** T8 (the native fix bundle — the single batched run); T36 (the
conserving charge initialisation); T50–T54 (`transcript.txt` only — 30 lines of wording, every
numeric baseline byte-identical); T60 (`transcript.txt` only — one `Outer boundary` line, an
addition only).

**Goldens updated for `det_radii` (2026-09-20):** 15 goldens, **one `radii` line in each, zero
deletions**. The cost is stated explicitly: foam results from before that date are not
byte-comparable. In the measured case the serial peak went 19914 → 19607 kPa (−1.5 %), because
a ball of radius ~dx around a corner point ignites the 4 cells meeting there instead of the one
cell `findCell` picked arbitrarily.

**Goldens updated for `Lohner` (2026-09-20):** three `dynamicMeshDict` files, three lines each
(`errorEstimator Lohner` + `field p` + `epsilon 0.05`).

**`settings.json` (N21):** `hw_fingerprint` and `hw_host_ram_gb` were added; no key was renamed
or removed, and an old file loads normally — it simply lacks a fingerprint, so its stored
numbers are rejected once, until the first probe. **`test_regression` was not affected by N21
and cannot be:** the derived cap only lowers `CELLS_*`, and the solvers keep enforcing the
constants unchanged.

**Case-file versions (`VERSION`):** 5 → 6 `anim_mesh` (T49) … → 10 (T50–T52 boundary kinds,
`t_end`, trigger) → **11** (T63: the three trigger keys are deleted at `dim == 1` before the
unknown-key check, so every saved 1D file and every old run's `case.json` keeps loading) →
**12** (`anim_scale`) → **13** (`adaptive_write` as a declared field on all three Case classes).

**Key commits:** `ba37a65` + `73ca834` (QA S1/S2), `3cb800c` (QA S4), `a6c7463` (validation and
feedback), `c3ce365` (T61), `a7930e3` (T60), `a416630` (T58/T59), `5262277` (T57), `972dca9`
(T56), `e344d17` (P0-1..3), `b18a9cb` + `68d23dc` + `8e107fe` (the PySide6 migration).
The full roadmap history: `git show 73ca834:ROADMAP.md`.
