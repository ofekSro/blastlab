# TASKS.md — blastlab work queue (ROADMAP.md folded into this file, 2026-09-07)

> **עברית — איך משתמשים:** זה הקובץ היחיד לניהול העבודה. ROADMAP.md אוחד לתוכו
> (ההיסטוריה המלאה של ROADMAP נמצאת ב-git: `git show 73ca834:ROADMAP.md`).
> המשימות ב-§3 כתובות באנגלית כ-prompt מלא לסשן אוטונומי (ללא plan mode):
> לכל משימה יש Why / Read / Do / Verify / Done when / Commit. סשן מריץ אותן לפי הסדר,
> מדלג על `[x]`, ובסוף כל משימה מסמן `[x]` בטבלה, כותב שורת DONE מתחת לבריף, ומקמט.
> מזהי ROADMAP הישנים (B1/G1/A1/N1…) עדיין מופיעים בהערות בקוד — הם נפתרים ב-§6 כאן.

---

## 1. How an autonomous session uses this file

1. Read §2 (rules) once. Then take the first `[ ]` row in the §3 table and run its brief.
2. **Status check before every QA task (T27–T33):** another session has been fixing
   `QA_REPORT.md` findings by severity (S1 and S2 are FIXED in commits `ba37a65` and
   `73ca834`; S3/S4 may be in progress). `QA_REPORT.md` "S*n* status" blocks are the
   authority: skip any finding already marked FIXED there, `git log --oneline -10`
   first, and never revert a fix that landed.
3. Do the whole brief. If one item is blocked, finish the rest, and write the blocked
   item + reason in the DONE line. Do not silently narrow a brief.
4. When green: tick the row, append `**DONE (YYYY-MM-DD):** <what changed, tests run>`
   under the brief, mark the matching `QA-nn` FIXED in `QA_REPORT.md` and the §6 id
   `DONE (date)`, then commit code + docs together (message format in the brief; end with
   `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`).
5. Then continue with the next `[ ]` row. Stop only at the end of the queue or when a
   brief says "owner decision".

## 2. Common rules (apply to every task)

```
Project: blastlab — Python blast-wave simulation desktop app (customtkinter GUI),
native numpy 1D/2D/3D solvers in blastlab/solvers/, blastFoam backend in
blastlab/solvers/foam/ (writes OpenFOAM-9 cases, runs them in WSL Ubuntu, reads
results back onto uniform numpy grids), pyvista/VTK viewer in blastlab/viz3d/.
Planning doc: this file. Ids like B23/G7/A5/N7 refer to §6 (reference index).

Hard rules:
- Never change native-solver stdout or the byte-pinned outputs unless the task
  explicitly says "re-baseline". `python blastlab/tests/test_regression.py` must
  stay green (or be deliberately re-baselined per the task, in the same commit).
- Foam goldens regenerate only via `python blastlab/tests/test_foam_writer.py --update`
  and an eyeballed diff.
- Tests are plain scripts: `cd blastlab/tests && python test_X.py`. Files named
  `_e2e_*.py` are manual end-to-end runs (need WSL, ~1–6 min each). The fast no-WSL
  matrix is in §8; run it after every task, WSL suites once at the end of a task
  that touches solvers/foam/.
- WSL work: run in the FOREGROUND (backgrounded shells that spawn WSL children
  report completion early and lose stdout). Before any WSL suite check nothing is
  running (`wsl.exe -d Ubuntu -- pgrep -a blastFoam`); a foreign solver makes
  test_foam_stop and memory-heavy suites fail spuriously. After killing anything,
  check for orphans the same way and kill them. 2D axisym foam cases at default
  size can take 30+ min — use tiny domains.
- Do not touch files outside the brief's "Read"/"Files" list without saying why.
- Token discipline: read only the files/functions listed (Grep the function names
  if line numbers drifted); do not re-run slow suites more than needed.
- GUI verification: `python blastlab/tests/_qa_gui_harness.py --resume --scenario <ids>
  --redo <ids>` opens a real window on screen and re-shoots the named scenarios
  (`--list` shows the matrix; output under ~\blastlab_qa\<stamp>\shots). Compare with
  the QA shots referenced in QA_REPORT.md.
- Windows: the test_regression baselines show as modified purely from CRLF conversion
  — do not commit them unless the task re-baselines.
- Finish by: (1) listing exactly what changed, (2) pasting the tail of each test you
  ran, (3) the doc updates + commit described in §1.
```

---

## 3. Queue — order & status

| # | Task | Ids | Effort | Status |
|---|------|-----|--------|--------|
| T0 | Commit untracked work | A9 | 10 min | [x] |
| T1 | Harden the foam stop/ingest path | B1, B2, B15 | S–M | [x] |
| T2 | Wrong-data display: 3D replay slice + viewer final frame + thinning | B3, B4, B20 | S | [x] |
| T3 | Units & labels: kPa everywhere, impulse naming | B8, B9 | S | [x] |
| T4 | Runs-dir safety: unique dirs, live-run guard, orphan reaping | B13, B14 | S | [x] |
| T5 | Papercuts bundle | B7, G1, B22, G6a | S | [x] |
| T6 | Chain validation + visible/stoppable foam preflight | B5, B6, G5 | M | [x] |
| T7 | Native solver warnings through hooks | B11 | M | [x] |
| T8 | Native fixes with ONE re-baseline | B10, B12, B18 | S | [x] |
| T9 | Extract the shared foam run loop | A1, A2, A3, A4(foam) | M | [x] |
| T10 | Foam accumulator correctness | B16, B17, B21 | S–M | [x] |
| T11 | Peak-overpressure / impulse views in Results | N1 | M | [x] |
| T12 | Per-gauge engineering summary + CSV | N2, B9 | S–M | [x] |
| T13 | 3D viewer colour-range plumbing + viz3d dead code | B19, A4(viz), A8 | S | [x] |
| T14 | Foam run browser + auto-cleanup | N8 | M | [x] |
| T15 | VTK/ParaView export | N4 | S | [x] |
| T16 | Afterburn model | N3 | M | [x] |
| T17–T19 | Local (static) refinement: core → foam → 3D viewer | N15 | M–L | [x] |
| T20–T24 | Dynamic AMR: core → ingest → GUI → 3D viewer → live slice/wedge fix | N16, B25 | M–L | [x] |
| T25 | QA S1: validation/preview memory safety, defaults, finite input | QA-01..04, 14, 15; B27, G10 | M | [x] 2026-09-07 (`ba37a65`, `73ca834`) |
| T26 | QA S1: chain feed3d lifecycle + profile-stage validation | QA-05, 06; B26 | S | [x] 2026-09-07 (`ba37a65`) |
| T27 | QA: remaining layout — Run-tab 3D viewport, status card height, truncations | QA-17, 25, 27; G11 | S–M | [x] 2026-09-07 |
| T28 | QA: chain feedback (stage select, workspace after validation, stage prefix) | QA-23; G12 | S | [x] 2026-09-07 |
| T29 | QA: validation & feedback bundle (G3, Results feedback, bad-file messages) | G3, QA-16, 22 | M | [x] 2026-09-07 |
| T30 | QA: user-named runs + loaded-run replay | N9, QA-24; G2 | S–M | [x] 2026-09-07 |
| T31 | QA: UI stalls + preview extras + viewer field availability | G4, G8, QA-18, 21, 17 | M | [x] 2026-09-07 |
| T32 | QA: theme/affordance + accelerators + persistence | G9, G13, QA-19, 28, 29 | S–M | [x] 2026-09-07 |
| T33 | QA: papercuts | QA-20, 26, 30..35 | S | [x] 2026-09-07 |
| T34 | GUI: global solver mode (sidebar selector; hide, don't grey) | — | L | [x] 2026-09-07 |
| T35 | `test_foam_parallel` determinism check (owner decided: option b) | B23 | S | [x] 2026-09-07 |
| T36 | Mass/energy-conserving resolved-charge init in 2D/3D (+ re-baseline) | B24 | S | [x] 2026-09-07 |
| T37 | Hardening bundle: native dead code, shared constants, stdout canaries | A4, A5, A6, A7 | S | [x] 2026-09-07 |
| T38 | Live-view niceties: foam cadence hint, 2D live Min/Max | G7 | S | [x] 2026-09-07 |
| T39 | Charge-mass rasterisation deficit (foam) | N5 | S–M | [x] 2026-09-07 |
| T40 | Arrival-time characterisation: AMR probe cell + foam near-field lag | N16-a, W1 | M (WSL time) | [x] 2026-09-07 |
| T41 | Chains INTO blastFoam (profile-initialised foam stages) | N7 | M–L | [x] 2026-09-07 |
| T48 | Hardware-aware run plan: WSL cores + RAM → MPI ranks and a cell cap, visible in the GUI | N17 | S–M | [x] 2026-09-07 |
| T42 | Parallel AMR (direct `processor*/` reads) | N16-b | M | [x] 2026-09-07 |
| T43 | Resume a stopped foam run | N6 | M | [x] 2026-09-07 |
| T44 | Gauge fields beyond p (foam) | N12 | S–M | [x] 2026-09-07 |
| T45 | CSV export of field maps + one-click HTML report | N14, N13 | M | [x] 2026-09-07 |
| T46 | Materials beyond TNT for the native solvers | N11 | M | [x] 2026-09-08 |
| T47 | MUSCL second-order native reconstruction (opt-in) | N10 | L | [x] 2026-09-08 |
| T49 | Mesh overlay on the animation a run writes | N15 | S | [x] 2026-09-08 |
| T50 | Boundary kinds: transmit / reflect / terminate | N18 | M | [x] 2026-09-08 |
| T51 | Trigger gauge: terminate and/or remap on arrival | N19 | M | [x] 2026-09-08 |
| T52 | An end time for 1D and 2D runs too | N18 | S | [x] 2026-09-08 |
| T53 | Gauges drawn in the live view and the animation | N19 | S | [x] 2026-09-08 |
| T54 | AMR mesh in the exported video (verify, then fix) | N15 | S | [x] 2026-09-08 |
| T55 | Bound the replay-frame record's memory | N15 | S | [x] 2026-09-08 |
| T56 | MP4 export reachable (label, dialog, default, ffmpeg) | N15 | S | [x] 2026-09-08 |
| T57 | Loading a PARALLEL AMR run (post-mortem) | N16-b | S | [x] 2026-09-08 |

Dependencies: T27–T33 independent of each other (do them before T34, which re-lays the
GUI out); T35 before any task that runs `test_foam_parallel`; T40 before T42 (the probe
offset must be understood before the mesh gets split); T48 before T42 (T42's parallel AMR
must go through the same run plan); T41 before T43 is not required.

---

## 4. Task briefs

### T27 — QA: remaining layout (QA-17 layout half, QA-25, QA-27) — G11

**Why:** at 1280×840 the embedded 3D view on the Run tab is ~330 px wide with clipped HUD
text and both scalar bars; a long validation strip squeezes the scrollable form to ~1/3
height; card titles, the "Record frames" checkbox, summary-table headers, the 2D AMR
preview title and 3D field figures are truncated or overlap. QA-07/08 (combos, export
row) are already FIXED — do not redo them. Shots: `123_D04_run_live_3d_dark`,
`278_F03_run_live_3d_dark`, `068_C05_setup_amr_card_on_dark`, `289_F04_results_fields_mesh_dark`,
`156_E05_results_overpressure_x-z_dark`.

```
SESSION PROMPT — T27
Status check: QA_REPORT.md status blocks; skip anything marked FIXED.
Read: QA_REPORT.md QA-17, QA-25, QA-27 and §9 (proposed fixes). Then only:
  blastlab/gui/run_panel.py (the body Panedwindow / sash and the View3DPanel host);
  blastlab/gui/view3d_panel.py _build_controls (control column width);
  blastlab/viz3d/viewer.py HUD text + scalar-bar placement (grep `add_scalar_bar`, `add_text`);
  blastlab/gui/forms.py SetupPanel (status card) + the "Record frames" checkbox;
  blastlab/gui/theme.py Card (title label); blastlab/gui/results_panel.py summary_table
  column setup; blastlab/output/plots.py _panel_grid_figure and the 3D field figure builders.
Do:
1. Run tab: set the paned sash after layout so the right (live/3D) pane gets >= 60 % of the
   width; View3DPanel's control column shrinks to ~200 px and collapses (toggle button) when
   the pane is < 700 px. viewer.py: HUD font scales with the render-window width, scalar bars
   width ~0.06 with short titles ("Overpressure [kPa]"), the loads bar horizontal at the
   bottom. Nothing clipped at 1280x840; still usable at 1100x720.
2. Status card (Setup): fixed height (~6 lines) with an inner CTkScrollableFrame or an
   expander for overflow; the form never loses more than that.
3. Truncations: Card titles get wraplength + full text as a tooltip; "Record frames for
   animation/replay" -> "Record replay frames"; summary_table columns stretch=True with
   minwidth fitting the headings; 3D field figures use constrained_layout=True so the x
   labels are not clipped; _panel_grid_figure puts the snapshot label in the axes title and
   the run label in fig.suptitle(y=0.99) so they cannot overlap; the AMR preview title is
   shortened ("base grid · AMR L3 follows the shock").
Verify: test_gui_results_fields, test_gui_gauge_summary, test_gui_refine_preview,
  test_gui_amr_form, test_viz3d_panel; test_regression byte-identical; harness
  --scenario D04,E05,C05,F04 --redo D04,E05,C05,F04 at 1280x840 and 1100x720 and eyeball
  the shots against the QA ones.
Done when: every widget reachable and unclipped at both sizes; QA-17 (layout), QA-25, QA-27
  FIXED in QA_REPORT.md; G11 DONE in §6.
Commit: "T27: Run-tab 3D viewport, status-card height, truncations (QA-17/25/27)"
```

**DONE (2026-09-07):** Run tab — `RunPanel._place_sash` parks the ttk sash after
the first real layout (weights only share out *extra* space) and stops once the
user drags it; the log box's requested width dropped 380 -> 280 so the sash can
actually move. Measured: live/3D pane 845 of 1280 px (66 %) and 62 % at 1100 px.
`View3DPanel`: control column 206 -> 200 px, its three tabs are scrollable (the
Display tab is taller than the column and used to push the timeline/Play strip
off), and a rail button folds the whole column away — automatically below 700 px
until the user decides otherwise. `viewer.py`: HUD font follows the render-window
width (`_scale_hud`), the field scalar bar moved to x = 0.855 with 11/10 pt text,
and the surface-loads bar is horizontal along the bottom — untitled, because VTK
prints a horizontal bar's title straight over its tick labels, with the caption
drawn as its own viewport text actor (`LOADS_BAR_KEY` / `LOADS_CAPTION`).
Status card (item 2) was already height-capped and scrolling from `3cb800c`;
re-verified (`114_C05_setup_amr_card_on_dark`). Truncations: `theme.Tooltip` /
`theme.tooltip` / `theme.wrap_to_width` added, and `Card` titles now wrap and
carry the full text as a tooltip; the 3D viewer's Min/Max boxes take a row each
(auto-fill read `1.88265e+`); the 2D preview title is short ("2D axisymmetric ·
wall: solid, open: dashed | base grid · AMR L3 follows the shock"); Run-tab stat
chips are packed before the buttons so the last chip survives at 1100 px, the
progress bar takes the slack, the Exec buttons are 72 px and "(blank = auto)"
became a hover hint plus an `auto` placeholder on the Refresh box. "Record replay
frames", the summary-table `stretch=True`/`minwidth` and the constrained-layout
figures were already in `3cb800c` — not redone.
Tests: test_regression byte-identical, test_gui_results_fields, test_gui_gauge_summary,
test_gui_refine_preview, test_gui_amr_form, test_gui_run_browser, test_gui_results_anim,
test_gui_drain, test_viz3d_scene (updated for the new loads-bar key), test_viz3d_panel
(new P10 block: collapse toggle, sash share, wrapped card title). Harness at 1280x840:
S00 smoke, C05, D04, E05, F04 (WSL, idle before and after); B05 covers 1100x720 and
900x600. Nothing clipped at 1280x840; at 1100x720 every control is reachable — the only
casualty is the "Refresh every" caption itself, which the placeholder and tooltip cover.

### T28 — QA: chain feedback (QA-23) — G12

**Why:** the chain error dialog names "Stage 2" but the stage switcher stays on Stage 1D;
the chain workspace directory is created before validation; the "'Lx' is not a number"
dialog carries no stage prefix. The paused-state readout half of QA-23 is already FIXED
(`73ca834`). Evidence: G01 scenario, `119_D03_run_interrupted_dark`.

```
SESSION PROMPT — T28
Status check first (QA_REPORT.md; the uncommitted chain_panel.py diff of a concurrent session
may already contain part of this - `git diff blastlab/gui/chain_panel.py`).
Read: QA_REPORT.md QA-23 + §9. Then only: blastlab/gui/chain_panel.py _run, stage_errors, the
  segmented stage switcher; blastlab/gui/app.py _run_chain / the 'stage' branch of _dispatch;
  blastlab/core/case.py the chain validation entry point used by chain_panel.
Do:
1. ChainPanel._run: validate every stage first; os.makedirs the workspace only after
   validation passes.
2. On a validation error select the first offending stage in the segmented switcher (so the
   user sees the form the dialog talks about).
3. Wrap get_case per stage so parse errors read "Stage n (nD): 'Lx' is not a number: 'abc'".
4. Chain workspace default: ~/Documents/blastlab/chain_workspace (not an absolute CWD path).
Verify: test_case_validate (stage-prefixed parse error), test_gui_drain; harness --scenario
  G01,G03 --redo G01,G03.
Done when: green; QA-23 FIXED; G12 DONE.
Commit: "T28: chain validation feedback - stage select, workspace after validation (QA-23)"
```

**DONE (2026-09-07):** items 1-4 had already landed in `a6c7463` (`ChainPanel._run`
parses every stage first, `focus_stage` raises the offending form, the parse-error
dialog reads "Stage n (nD): ...", `os.makedirs(ws)` runs only once the chain will
start, and the workspace defaults to `~/Documents/blastlab/chain_workspace`) — not
redone. This task closed the gap around them: the "must be axisymmetric to feed 3D"
refusal now also carries the stage prefix and raises stage 2 (it was the one chain
dialog that still left the switcher where it was); `test_gui_drain` gained
`chain_feedback_checks` (stage-prefixed dialog, switcher on the offending stage, no
workspace created, chain not started, default path under the user profile); and the
G01 harness assertion, which asserted the *defect* (`isdir(ws)` after five refusals)
and would have passed on a leftover directory, now checks the fix against a fresh
workspace path under the QA output dir.
Tests: test_case_validate, test_gui_drain; harness G01 (all five refusal dialogs
stage-prefixed, switcher ends on Stage 2D, workspace absent) and G03.

### T29 — QA: validation & feedback bundle (G3, QA-16, QA-22)

**Why:** only the first parse error is shown; malformed point-list rows ('a b', wrong
arity, '1;2') are silently ignored with the text left in the entry; "Refresh every = abc"
silently means automatic; a capped case shows the strip on Setup but a modal on Run;
exports with nothing selected are silent no-ops; every export / loader / 3D-viewer message
goes to the Run-tab log while the user is on Results; the Profile button is enabled for
planar 2D results although it always fails; "Open case" errors are raw parser text.
Shots `048_C01_setup_two_parse_errors_dark`, `061_C04_setup_gauge_row_a_b_dark`,
`083_C08_run_dialog-showerror_dark`, E03/E07/I03. QA-15 (finite numbers) is already FIXED.

```
SESSION PROMPT — T29
Status check first.
Read: §6 G3; QA_REPORT.md QA-16, QA-22, §6 (dialog inventory), §9. Then only:
  blastlab/gui/forms.py _f/_i/_PointList._add/CaseForm.get_case/self.widgets;
  blastlab/gui/app.py _validate/_run_single/_refresh_policy/_open_case/_log_threadsafe;
  blastlab/gui/results_panel.py _export/_open_3d/load_foam_run_path/_log;
  blastlab/gui/run_panel.py (Run/Initialise buttons); blastlab/gui/theme.py (add a status /
  toast helper); blastlab/core/case.py load_case error paths.
Do:
1. CaseForm.get_case collects ALL parse errors into one ValueError (newline-joined); the
   strip shows every line; offending entries get border_color=theme.c('error') until fixed
   (c('border') again on a good parse). Keep a widgets[name] map in CaseForm for this.
2. _PointList._add: on a bad row keep the text, red border, and a one-line hint under the
   list ("expected 2 numbers: x y"); a valid row clears it. Same red border + tooltip
   "number > 0 or blank" for Refresh-every.
3. Run tab: a validation chip next to Run ("Case OK" / "n errors - see Setup") fed by
   _validate; Run and Initialise disabled while errors exist, so the duplicate modal goes.
4. Feedback: a bottom status line per panel (Results, Run) + App.notify(text) used for
   "Saved …", "Export failed …", "Loaded …", "3D Viewer: select a 3D result.", "3D view
   loaded …", dropped-gauge notes; keep the Run-log copy. Export buttons disabled when no
   result is selected; Profile disabled for planar 2D and 3D results with a tooltip saying
   why ("only axisymmetric 2D fields can be remapped").
5. App._open_case: json.JSONDecodeError -> "This file is not valid JSON (line L, column C)";
   schema/dim errors -> "Not a blastlab case file (dim 5 is not supported)";
   FileNotFoundError -> "File not found: <path>" (str(path), not repr). File dialogs get
   titles ("Open case", "Save case", "Save gauges TSV", …).
Verify: test_case_validate, test_gui_drain, test_gui_results_fields (+ new headless checks:
  multi-error strip, _PointList bad-row feedback, Run disabled with errors, open-case
  messages); harness --scenario C01,C04,C08,E03,E07,E08,I03 --redo (same).
Done when: green; G3 DONE; QA-16/22 FIXED.
Commit: "T29: collect every validation error, inline field feedback, Results status line (G3, QA-16/22)"
```

**DONE (2026-09-07):** items 1-3 and most of 4-5 had landed in `a6c7463` — verified,
not redone: `CaseForm.get_case` raises ONE newline-joined ValueError and
`mark_fields` red-borders every offending entry; `_PointList._reject/_accept` keep
the text, red-border the box and print a one-line hint; `RunPanel.set_validation`
drives the "Case OK / N errors - see Setup" chip and disables Run + Initialise;
`RunPanel.mark_refresh` marks an unusable "Refresh every"; `App.notify` +
`_status` is one window-wide status bar (chosen over a per-panel line - it reaches
the user wherever they stand) and `_open_case` reports JSONDecodeError / schema /
FileNotFoundError in plain words.
This task closed the rest: every file dialog is titled (Open case, Save case, Save
gauges TSV, Save gauge summary CSV, Save animation GIF, Save profile, Open profile
file - `_FilePicker` takes a `title=`); a disabled export button carries a tooltip
saying why it is off (the brief's "only axisymmetric 2D fields can be remapped"
among them); `ResultsPanel._refresh` re-gates the export row when the picker matches
nothing (it returned early, leaving the previous result's buttons enabled and live
as no-ops - the E08 harness finding); and `_export` answers "Select a result before
exporting." instead of returning in silence.
Tests: test_gui_results_fields gained a `t29_checks` block (Run/Initialise gated by
set_validation, a disabled export explains itself, Open case on garbage JSON / a
`dim: 5` schema / a missing path, every dialog titled) - plus test_case_validate,
test_gui_drain, test_gui_gauge_summary, test_gui_refine_preview, test_gui_amr_form,
test_gui_run_browser, test_gui_results_anim, test_regression byte-identical.
Harness C01, C04, C08, E03, E07, E08, I03 - no findings. (E03/E08 first reported
findings when run in isolation: E03 needs D01/D02 to have cached the 1D/2D results,
and E08's was the live-no-op bug fixed above; re-run after D01,D02 both pass.)

### T30 — QA: user-named runs + loaded-run replay (N9, QA-24) — G2 close-out

**Why:** results are labelled by dim + timestamp only; loaded post-mortem runs have no
replay frames and the picker truncates long labels. De-dup (" #2") and Remove are already
FIXED (`73ca834`); the empty-Animation caption exists (QA-12) — this task gives loaded runs
real frames and lets the user name runs.

```
SESSION PROMPT — T30
Status check first.
Read: §6 N9, G2; QA_REPORT.md QA-24 + §9. Then only: blastlab/gui/run_panel.py (add a run-name
  entry next to Run); blastlab/gui/app.py _start (label construction) and _dispatch 'result';
  blastlab/gui/results_panel.py add_result/_setup_anim/picker; blastlab/gui/run_browser.py
  load_selected; blastlab/solvers/foam/postmortem.py load_run (frames / meta['frames']).
Do:
1. Optional run name on the Run tab (default = case file stem or blank); label becomes
   "<name> - 2D" (or the old form when blank); exported file names use the name; the name
   travels in Result.meta['name'].
2. Loaded runs: postmortem.load_run already reads every written time - populate
   meta['frames'] from those slices (sampled to <= 150 frames, same shape as live frames) so
   the Animation tab replays a loaded run; label "<name> (loaded)".
3. Picker: ellipsise labels longer than the combo (full text as tooltip); the combo width
   stays honest at 1100 px.
Verify: test_gui_results_fields (name in label, loaded frames replay), test_foam_postmortem
  (frames populated, WSL) or a fake-time-dir check without WSL; harness --scenario E09,F09
  --redo E09,F09.
Done when: green; N9 DONE; G2 DONE; QA-24 FIXED.
Commit: "T30: user-named runs, replay frames for loaded runs (N9, QA-24)"
```

**DONE (2026-09-07):** (1) a "Name" box next to Run/Stop/3D View on the Run tab
(`RunPanel.run_name` / `current_run_name` / `set_run_name`); `App._start` captures it,
`_dispatch('result')` labels the result "<name> - 2D" (blank keeps "Run N - 2D") and
writes `Result.meta['name']`; Open case pre-fills the name from the file stem without
ever overwriting what the user typed; every suggested export file name gains a
slugged "<name>_" prefix (`ResultsPanel._name_prefix`), the PNG batch included.
NOTE: CTkEntry silently drops `placeholder_text` once a textvariable is attached, so
the box carries a real label (and the same applies to "Refresh every"). (2)
`postmortem.load_run` collects a frame per written time - thinned by halving exactly
like the live loop, capped at `case.record_frames` (150 by default), 3D reduced to the
run's own live slice via the now-public `backend.slice_geom_3d` - and hands them to
finalize_2d/3d, so a loaded run replays; its label is "<run dir> (loaded, 2D)".
(3) The picker elides a label longer than 34 chars in the MIDDLE and keeps the full
text as a tooltip; `_current()` resolves either form, so the de-dup marker and the
dimension stay visible.
Tests: test_gui_results_fields gained `t30_checks` (name trimming, set_run_name never
overwriting, export prefix, middle elision, tooltip, picker resolution);
test_foam_postmortem gained three frame checks and now demands the FULL meta-key
superset (it used to except 'frames'); the F09 harness assertion compares entry labels
instead of the combo's display strings. WSL suite run on an idle WSL, no orphans after.
Harness E09 and F09 (post-mortem load == live, "frame times equal: True", two distinct
entries), B05 for the Run-tab layout at 1280x840 / 1100x720 / 900x600, plus
test_regression byte-identical, test_gui_drain, test_gui_results_anim,
test_gui_run_browser, test_foam_writer, test_foam_reader, test_case_validate.

### T31 — QA: UI stalls + preview extras + viewer field availability (G4, G8, QA-18, QA-21, QA-17 fields)

**Why:** measured stalls: 3D preview build 3.5 s per debounce, run start 1.9 s,
`feed_result` 2.7 s for 3 snapshots, 3D AMR live frames 3.6 s. The preview draws only the
primary charge (no extra charges / detonation points). In the 3D viewer the Peak
overpressure / Net ovp impulse / Energy radios are disabled for native and foam 3D results
although the Fields list offers those maps, and a plane position of 0.0/1.0 silently shows
nothing. Idle CPU with hidden hosts is 0–1 % (refuted — do not chase it).

```
SESSION PROMPT — T31
Status check first.
Read: §6 G4, G8; QA_REPORT.md QA-17 (fields half), QA-18, QA-21, §5 timings, §9. Then only:
  blastlab/gui/view3d_panel.py feed_result/on_frame/Feed3D.make_payload;
  blastlab/gui/vtk_host.py _render_tick; blastlab/gui/preview_panel.py Preview3DPanel.show_case,
  Preview2DPanel.show_case, case_geometry; blastlab/gui/app.py _validate debounce;
  blastlab/viz3d/viewer.py _MeshEdges, field radios / FIELDS, plane slider handling,
  add_static_scenery; blastlab/viz3d/client.py scene_from_meta; blastlab/viz3d/sampling.py.
Do:
1. feed_result: feed one snapshot per after(1, …) tick with a "loading n/N" HUD line;
   no continuous Tk block > 300 ms.
2. 3D preview: keep one GeometryScene and update actors in place (charge / gauges /
   obstacles) instead of rebuilding; debounce 500 ms and skip while a build is pending;
   if a full rebuild is unavoidable, do the pyvista work off-thread and hand the result to Tk.
3. AMR per-frame mesh edges: build the polydata inside Feed3D.make_payload on the worker
   thread and hand it to _MeshEdges; a frame never blocks > 300 ms.
4. Preview (G8): case_geometry carries charges=[(x,y,z,r_i)] and det_points; viewer draws
   extra charges as orange balls + det points as small diamonds; Preview2DPanel draws det
   points as "x" markers and extra charges as circles.
5. Results 3D playback: carry p_peak / impulse (and e when present) from meta in the
   snapshot payload so the viewer radios match the Fields list; hide (tooltip) a radio whose
   field is absent instead of greying it. Plane slider at 0.0/1.0: clamp to the first/last
   cell centre so a cut is always shown.
Verify: test_viz3d_panel (chunked feed_result + timing), test_gui_refine_preview (extra
  charges / det points drawn), test_viz3d_scene, test_viz3d_sampling; harness --scenario
  D04,E06,F06,C09 --redo (same) and compare timing.jsonl / checkpoint.json against QA §5.
Done when: green; G4/G8 DONE; QA-17 (fields)/18/21 FIXED.
Commit: "T31: chunked replay feed, in-place 3D preview, off-thread AMR edges, preview extras (G4/G8)"
```

**DONE (2026-09-07):** (1) `View3DPanel.feed_result` streams ONE snapshot per
`after(1, ...)` tick (`_feed_step` / `_cancel_feed`), with `BlastScene.loading`
adding a "loading n/N snapshots" HUD line that clears on the last frame; a new
result or `reset()` cancels a feed still in flight. Measured: a snapshot tick ~1 ms;
the harness E06 gate reads 360 ms for `_open_3d`, which is now the one-off VTK scene
build, not the snapshot loop. (2) Setup 3D preview: the existing `_key` cache is kept
and a 500 ms LEADING-edge throttle added (`THROTTLE_MS`, `_flush_pending`) - the first
edit of a burst renders at once, the rest collapse into one trailing rebuild; `clear()`
cancels a pending build. The scene object itself was already reused in place.
(4) G8 was already drawn by `a6c7463`; a detonation point is now an octahedron so it
cannot read as one more spherical charge/gauge. (5) The whole-run `p_peak` / `impulse`
maps already rode along in the payload; `_sync_field_availability` now HIDES a radio
whose field is absent (re-packing in the fixed order, and falling back to Pressure if
the selected field disappears) instead of greying it, and the plane slider was already
clamped to 0.001/0.999 so a cut is always shown.
**NOT DONE - item 3 (off-thread AMR mesh edges), and why:** the premise was refuted
before this task. QA_REPORT S4 measured `mesh_polydata` at 262 ms once then ~6 ms per
frame; re-measured here on a 30^3 display grid with a growing shock: **320 ms on the
first call (VTK warm-up, paid at scene build in the app) then 5-8 ms per frame**. Moving
that to `Feed3D.make_payload` would hand VTK objects built on the solver worker thread
to the Tk thread - real risk, no measured gain - so it was left alone and the
measurement recorded in QA_REPORT instead.
Tests: test_viz3d_panel gained a P9b block (chunked feed, HUD counter, per-tick timing,
every snapshot arriving, loading line cleared, whole-run radios shown, reset cancelling
a feed) and its "impulse radio disabled" check became "hidden"; test_viz3d_scene gained
the extra-charge / det-point actor checks. Plus test_regression byte-identical,
test_viz3d_sampling, test_viz3d_hooks, test_gui_refine_preview, test_gui_amr_form,
test_gui_results_fields, test_gui_drain. Harness C09, D04, E06 and F06 (3D AMR in WSL,
141 s, idle WSL before and no orphans after). F06 crashed once on a Windows
`ImageGrab` "screen grab failed" - a desktop-capture hiccup, not the app; the re-run
was clean.

### T32 — QA: theme & affordance + accelerators + persistence (G9, G13, QA-19, QA-28, QA-29)

**Why:** in light mode the unselected segments of every segmented button are invisible and
disabled buttons nearly so; the disabled Stop button stays red; matplotlib toolbar
back/forward icons render as checkerboards in dark mode; no focus ring, no accelerators,
no window/mode persistence. Shots `036_B07_setup_setup_default_light`,
`037_B07_run_empty_light`, `006_S00_run_finished_dark`.

```
SESSION PROMPT — T32
Status check first (theme.py has an uncommitted diff from a concurrent session - read it).
Read: §6 G9, G13; QA_REPORT.md QA-19, QA-28, QA-29, §9. Then only: blastlab/gui/theme.py
  (palette, apply_ttk_style, icons, any segmented-button factory); every CTkSegmentedButton
  construction (grep); blastlab/gui/run_panel.py buttons + set_running; blastlab/gui/mpl.py
  toolbar; blastlab/gui/settings.py; blastlab/gui/app.py __init__/_on_close/_toggle_mode;
  blastlab/gui/forms.py _entry.
Do:
1. Segmented buttons: unselected_color=('#d5dbe3', '#333333') (or the card2/border tuple)
   with a matching hover colour - visible in both modes.
2. Buttons: text_color_disabled=c('muted') and a flat disabled fg; Stop is grey while
   disabled and red only during a live run (set_running swaps it).
3. Toolbar: the checkerboards are matplotlib's disabled back/forward images - build a
   4-button toolbar (Home, Pan, Zoom, Save) with theme.icon, or hide those two.
4. Focus ring: forms._entry binds FocusIn/FocusOut to swap border_color to accent.
5. Accelerators on root (bind_all): Ctrl+O open, Ctrl+S save, F5 run, Esc stop.
6. Persistence: geometry, appearance mode and the refresh field saved via gui_settings in
   _on_close and applied in __init__ (settings.json already exists from N8).
Verify: headless checks for the persisted keys + the accelerator bindings; harness
  --scenario B04,B06,B07,H03 --redo (same) in both modes and eyeball.
Done when: green; G9 + G13 DONE; QA-19/28/29 FIXED.
Commit: "T32: light-mode affordance, disabled styles, toolbar icons, accelerators, persistence (G9/G13)"
```

**DONE (2026-09-07):** items 1-6 had landed in `a6c7463` / `3cb800c` and are verified,
not redone: a dedicated `seg` palette entry (`('#ced6e0', '#3a3f46')`, the tuple the
brief asked for in spirit) on every `CTkSegmentedButton`; `theme.Button` with
`text_color_disabled=c('muted')`; `RunPanel.set_running` swapping Stop between
`card2`/muted and `danger`/white; matplotlib's Back/Forward (whose disabled images
rendered as dark-mode checkerboards) dropped from the toolbar; `forms._entry` binding
FocusIn/FocusOut to an accent border; `App._bind_accelerators` for Ctrl+O / Ctrl+S /
F5 / Esc; and geometry + appearance + refresh box persisted through
`gui/settings.py` (geometry only from a really mapped window at least the minimum
size).
This task closed the gap the per-widget approach left: 16 call sites build a plain
`ctk.CTkButton` (Results exports, Remove, Foam runs, Play, the chain Run button, the
camera presets, the file-picker buttons) and kept CTk's near-invisible disabled tint.
`theme._apply_ctk_defaults()` now writes the muted disabled text and the `seg`
unselected fill straight into `ctk.ThemeManager` at import, so every button, segmented
button, checkbox, radio, entry, option menu and combo inherits them without touching
the call sites.
Tests: test_gui_results_fields gained `t32_checks` - a plain CTkButton's disabled text
colour, a segmented button's unselected colour, Stop red only while running, an entry's
focus ring (driven through a really mapped window, since a synthesised <FocusIn> never
reaches the inner tk Entry CTkEntry binds on), all four accelerators bound on the root,
the four persisted keys present in DEFAULTS and round-tripping through settings.json.
Plus test_regression byte-identical and the GUI matrix. Harness B04, B06, B07, H03 in
both modes: B06 confirms the accelerators fire (F5 really started a run, which is why
the harness then reports "worker still alive between scenarios" and stops it - a
harness housekeeping note, not a defect).

### T33 — QA: papercuts (QA-20, QA-26, QA-30..QA-35)

```
SESSION PROMPT — T33
Status check first.
Read: QA_REPORT.md QA-20, QA-26, QA-30..35 + §9. Then grep the named sites only.
Do:
- Run log: CTkTextbox(wrap='word'), keep F_MONO (QA-20).
- Chip caption "p max [kPa]" with p.p_max/1e3 (QA-26).
- FoamRunBrowser: ttk.Scrollbar bound to table.yview; the running-run refusal as a
  messagebox.showwarning or a c('danger') status label (QA-30).
- Peak-overpressure colour scale: vmax = nanpercentile(pk[~charge_mask], 99.5) where
  charge_mask = cells within r_exp of any charge (or LogNorm) (QA-31).
- Runloop AMR note: log the first 5 writes, then every 10th or when the cell count changes
  > 10 %; add a "cells" chip on the Run tab fed from hooks.frame(levels=); 1D live axes
  initial set_ylim(0, 10) kPa until the first frame (QA-32).
- Tooltips on the gauge-table headers; "Complete" -> "Pos. phase complete"; gauge row label
  "G1 (0.3, 0.8) -> cell (0.305, 0.802)" (QA-33).
- app.py logo: `with Image.open(_LOGO) as im: img = im.convert('RGBA')`; preview_panel:
  ax.grid(True, alpha=0.25) only when the mesh is off, ax.grid(False) otherwise (QA-34).
- AMR/3D validation line gains "~X MB per write, ~Y GB for this run" from predicted cell
  count x written times (QA-35).
Verify: test_regression byte-identical (no solver prints touched); test_gui_run_browser,
  test_gui_gauge_summary, test_gui_amr_form; harness --scenario D02,F05,F09 --redo (same).
Done when: green; QA-20/26/30-35 FIXED.
Commit: "T33: GUI papercuts (QA-20/26/30-35)"
```

**DONE (2026-09-07):** already landed in `3cb800c` and verified, not redone - the Run
log's `wrap='word'` with F_MONO (QA-20); the `p max [kPa]` chip fed with `p.p_max/1e3`
(QA-26); the run browser's `ttk.Scrollbar` on `table.yview` and its
`messagebox.showwarning` refusal (QA-30); `_panel_grid_figure(robust=True)` clipping
the charge spike out of the peak/impulse colour range and saying so in the panel label
(QA-31); the AMR log collapsed to one live line with a running count and the 1D live
axes opening on 0-10 kPa (QA-32); the closed logo file and the `grid(False)` warning
(QA-34).
Closed here:
- **QA-32 (cells chip):** `RunPanel._chip_cells` + `_show_cells`, fed from
  `on_frame(levels=)`. It reports REAL cells, not display cells - a display cell at
  level l stands for `2**((disp - l) * ndim)` of them - appears with the first frame
  that carries a level map and hides again on the next run until that run reports one.
  Verified live on F05 (`cells 5,149` beside the other chips).
- **QA-33:** `gauge_summary.gauge_labels(gauge_out, requested=None)` prefixes every
  label with its gauge number and, when the solver snapped a gauge, prints
  "G1 (1.000, 2.000, 0.450) -> cell (1.000, 2.000, 0.500) m"; `meta['gauges']` now
  carries the requested list from solver2d, solver3d and both foam finalizers, and
  `ResultsPanel.summary_rows` passes it. Each abbreviated column header explains
  itself through one tooltip that follows the pointer's column (ttk headings take no
  tooltip of their own), including what "Phase ended = no" means for the impulses.
  The header text stays "Phase ended" rather than the brief's "Pos. phase complete":
  the short form is what keeps the column unclipped (QA-27) and the tooltip carries
  the meaning.
- **QA-35:** the AMR disk note gives the run total as well as the per-write figure.
Tests: test_gauge_summary updated for the numbered labels plus two new checks (a
snapped gauge shows both, an exact one is not cluttered); test_gui_results_fields
gained `t33_checks` (chip hidden for a static run, real-cell arithmetic, chip appearing
with the first AMR frame and hidden again by set_running, hover help for every gauge
column). test_regression byte-identical - the meta key is new, and neither the
transcript nor the pinned TSV/npz files carry meta. Plus test_gui_gauge_summary,
test_gui_run_browser, test_gui_amr_form, test_case_validate, test_foam_writer,
test_refine. Harness D02, F05 (2D AMR in WSL) and F09; idle WSL before, no orphans
after.

### T34 — GUI: global solver mode (sidebar selector; hide what does not apply)

**Why:** `solver` (native | blastfoam) is a combo inside the Numerics card and picking one
silently enables/disables ~10 scattered widgets via `CaseForm._sync_enabled()`. The user
sees greyed-out controls with no explanation and blastFoam-only cards are always visible.
The solver should be an app-level mode that reconfigures the whole GUI.

```
SESSION PROMPT — T34
Read: blastlab/gui/app.py (whole: sidebar, _show, _open_case/_save_case, _dispatch);
  blastlab/gui/forms.py (whole: CaseForm cards, _sync_enabled, get_case/set_case);
  blastlab/gui/chain_panel.py; blastlab/gui/results_panel.py header + export gating;
  blastlab/gui/run_panel.py; blastlab/core/case.py Case*.solver + validate_case's
  _validate_solver; blastlab/tests/test_gui_*.py and _qa_gui_harness.py (how they drive the
  solver combo). QA_REPORT.md is NOT needed.
Goal:
- A segmented control "Solver: native | blastFoam" in the LEFT SIDEBAR directly ABOVE the
  "Dark mode" switch (app._build_sidebar, the `bottom` frame), with a one-line explainer
  under it ("native - pure-Python, fast, no WSL" / "blastFoam - WSL, OpenFOAM-9, AMR +
  refinement zones") and a WSL-availability hint for blastFoam (env probe, off-thread).
- Choosing a solver reconfigures the whole GUI. Controls that do not apply are HIDDEN,
  not disabled. The selection is visible on every tab.
Inventory (verified; confirm & extend):
  blastFoam-only: Material combo (native is TNT-only); Detonation combo; Afterburn combo;
    Charge refinement global|zone (dim>1); MPI ranks (dim>1); the whole "Dynamic refinement
    (blastFoam)" AMR card; the "Refinement zones", "Extra charges" (3D) and "Detonation
    points" cards; Results: "Foam runs…" button and the VTK export button.
  native-only: EOS combo (blastFoam fixes JWL products + ideal-gas air); profile-fed chain
    stages (chain_panel: blastFoam stages cannot start from a profile until T41/N7).
Requirements:
1. Solver state lives on App and propagates to SetupPanel/CaseForm (all 3 dims), RunPanel,
   ResultsPanel, ChainPanel. Case.solver stays the persisted field - the selector writes
   it; do not fork the data model. Remove the Solver combo from the Numerics card.
2. Open case… / Save case… sync the selector from/to the loaded case and re-layout.
3. Chain tab: every stage is PRESET from the global solver and can be overridden per
   stage with a small native|blastFoam switch above its form (owner decision: a foam
   1D stage can feed native 2D/3D stages today; T41 unlocks foam 2D/3D).
4. Switching solver never loses input: hidden fields keep their Tk vars and come back on
   switch-back; validation considers only the fields relevant to the active solver.
5. Show/hide re-flows the cards (grid_forget/regrid), the scrollable form re-measures, no
   holes in either column. Card titles drop the "(blastFoam)" suffix (the mode says it).
6. Layout at 1280x840 and 1100x720 stays unclipped (T27's fixes must survive).
7. Tests: update test_gui_*.py and _qa_gui_harness.py to set the solver through the new
   App-level API (e.g. app.set_solver('blastfoam')); add a headless test: switching modes
   hides/shows the inventory above and round-trips field values.
A full rewrite of blastlab/gui/ is acceptable; core/, solvers/, viz3d/ stay unchanged
unless justified. Migration order: App state + sidebar -> CaseForm hide/show -> Results/
Chain/Run gating -> tests/harness -> README section "Solver mode".
Verify: the full no-WSL matrix (§8) + harness --smoke; then harness --scenario
  S00,B01,B02,B03,C09,C10,E03,F02,G01 --redo (same) in both solver modes.
Done when: green; README updated; a short "Solver mode" paragraph in blastlab/README.md.
Commit: "T34: global solver mode - sidebar selector, solver-specific layout"
```

**DONE (2026-09-07):** targeted refactor, not a rewrite. New `gui/mode.py` (`SolverMode`
observable, no Tk) seeded from `settings.json` (`solver`, fresh default `blastfoam`) before
the panels are built; sidebar block (segment + explainer + live WSL status) above Dark mode;
`CaseForm` registers rows/cards per scope and `_apply_mode()` grid_removes the other
solver's (EOS / 3D Charge resolution are native-only; Material, Detonation, Afterburn,
Charge refinement, MPI ranks, the AMR / Refinement zones / Extra charges / Detonation
points cards are blastFoam-only; AMR coefficient rows only while levels > 0, the
charge-refinement row hidden while AMR is on); the Solver combo and every value coercion
are gone - `get_case()` strips hidden fields to that solver's defaults and never parses
them, Tk vars keep the typed values. `SetupPanel.set_case` adopts the case's solver as
the app mode (Open case). Chain: per-stage native|blastFoam switch above each stage
form, preset from the global mode (`set_stage_solver` / `set_stage_case`). Results hides
"Foam runs…" and VTK in native mode. `theme.segmented()` replaces the five inline
segmented-button copies. `validate_case` notes the ignored EOS only when it is not the
default. Tests: new `test_gui_solver_mode.py` (31 checks); `test_gui_amr_form`,
`test_gui_refine_preview`, `test_gui_drain` moved to `winfo_manager()` asserts; harness
gained `qa.solver()` + `--solver` and C05/C06/C07/G01/`_chain_forms` drive the new API.
Verified: full no-WSL matrix green incl. test_regression byte-identical and
test_blast2d/3d; `_e2e_gui_foam` (WSL) green, no orphans; harness `--smoke`, then
B01,B02,B03,C05,C06,C07,C09,C10,E03,G01 starting in blastFoam mode and
B01,B03,B05,B07,C05,C07,G01 with `--solver native` (dark + light, 1280x840 + 1100x720):
no tk-exception, no ui error; the only findings (C10 "Local refinement" strip text for the
level-capped 10 m zone case, E03 export-file checks) are present unchanged in the
2026-09-07 01:08 and 09:54 runs, i.e. pre-existing and unrelated. Out of scope, left as
found: untracked `test_gui_results_anim.py` / `_e2e_gui_native_warn.py` from earlier
sessions.

### T35 — `test_foam_parallel` determinism check (B23) — owner decided

**Why:** `test_foam_parallel.py` (~lines 70–74) asserts two identical np=2 runs give gauge
arrays of equal length and equal values. Since B25 made controlDict rewrites take effect,
the adaptive `writeInterval` controller moves write times at wall-clock-dependent moments
and `writeControl adjustableRunTime` clips the time step to land on them, so the two runs
diverge after the first adaptation (max |dp| 470 Pa; lengths 525 vs 616; peaks agree to
0.13 %, arrivals to 0.7 %). A suite that fails randomly trains sessions to ignore it.
**Owner decision (tasksforofek.md §1): option (2)/(b)** — disable the adaptive controller for
the determinism pair so the runs are bit-identical; fall back to (a) physics tolerances only
if (b) turns out impractical.

```
SESSION PROMPT — T35
Read: blastlab/tests/test_foam_parallel.py; blastlab/tests/test_adaptive_interval.py (the
  controller's contract); grep `adaptive`/`writeInterval` in blastlab/solvers/foam/runloop.py,
  runner.py, backend.py and writer.py (controlDict emission) to find the switch point.
Do:
1. Add an explicit per-run option (e.g. Case field or run kwarg `adaptive_write: bool`,
   default True; plumb through backend -> runloop -> writer so a False run writes a fixed
   writeInterval and never calls rewrite_control_entry for it). Default behaviour and all
   goldens unchanged (writer golden diff must be empty for default cases; add ONE golden or
   a unit check for the fixed variant).
2. test_foam_parallel: the determinism pair runs with adaptive_write=False and asserts
   len(a) == len(b) and array_equal (what the comment claims). Keep the np1-vs-np2 physics
   comparison as it is. Add a secondary physical-agreement assert (peaks within 1 %,
   arrivals within 1 %) so a future regression in the fixed path is still caught.
3. Run the suite twice in a row; both must pass.
Verify: test_foam_writer (--update only if the default goldens are untouched and a new
  fixture is needed), test_adaptive_interval, test_foam_parallel x2 (WSL, ~5 min each),
  test_regression byte-identical.
Done when: two consecutive green runs; B23 DONE.
Commit: "T35: deterministic writeInterval for the parallel determinism pair (B23)"
```

**DONE (2026-09-07):** option (b) as the owner decided. `CaseSpec.adaptive_write`
(default True) and an `adaptive_write=` kwarg on `solve_1d/2d/3d_foam`; when it is
False `runloop.maybe_adapt` returns immediately, so the run never rewrites
`writeInterval` and `writeControl adjustableRunTime` clips the time step onto the
same write times every time. Nothing changes by default: the writer emits exactly
what it always did (the goldens are untouched - `test_foam_writer` PASS) and only
the new dataclass field exists.
`test_foam_parallel` now runs the determinism pair with `adaptive_write=False` and
adds the physics guard the brief asked for (pinned vs adaptive peaks and arrivals
within 1 %: measured +6.6e-4 / -1.1e-3 on the peaks, 0.15 vs 0.15 ms and 0.339 vs
0.339 ms on the arrivals). `test_adaptive_interval` gained a no-WSL unit check that
`adaptive_write=False` produces zero `rewrite_control_entry` calls and a pinned
interval, that True still adapts, and that the default is True.
**Deviation from the brief's wording, and why:** the pair is now bit-identical in
every sample it records - identical times, identical pressures - which is what the
old comment claimed. It is NOT identical in RECORD LENGTH: 372 vs 368 samples on the
second run. That last difference is not a numerical race. The arrival watcher reads a
written time on the Python side and then asks the solver to stop, so the solver takes
a wall-clock-dependent number of extra steps before the stop lands, and the probe
function object samples every one of them. Making that identical would need a
solver-side stop condition, which is out of this task's scope. The test therefore
asserts (i) identical sample times over the common record, (ii) identical gauge
records over the common record, and (iii) that the common record covers >= 95 % of
the longer one (measured 98.9 %), with the reason in a comment - instead of a bare
`len(a) == len(b)` that would fail on the tail alone. Before this change the pair
differed by 91 samples with 470 Pa peak error; now it differs by 4 samples and 0 Pa.
Tests: `test_foam_parallel` twice in a row, both PASS (idle WSL checked before each,
no orphans after); test_adaptive_interval, test_foam_writer (goldens byte-identical),
test_foam_live_due, test_foam_reader, test_case_validate, test_regression
byte-identical.

### T36 — Mass/energy-conserving resolved-charge init in 2D/3D (B24) + re-baseline

**Why:** with `dx = r_exp/MIN_EXP_CELLS` the explosive is a 5-cell-radius stair-step; the
set of cells inside r_exp holds ±3 % of the true sphere depending on whether the centre sits
mid-cell or on a face, and rho/e are set per cell without rescaling. 3D `charge_resolution=
'smear'` already rescales; `'resolve'` and 2D do not. It moved `test_blast2d`'s r = 1.5 m
arrival gap from 4.3 % to 5.2 % (gate widened to 6 %). Initial energy is the one number every
peak/arrival scales with. Owner note (tasksforofek.md §8): decide → decided: do it.

```
SESSION PROMPT — T36
Read: blastlab/solvers/solver2d.py and solver3d.py charge initialisation (grep `r_exp`,
  `MIN_EXP_CELLS`, `smear`, `resolve`); the 3D smear rescaling (the model to copy);
  blastlab/core/constants.py; blastlab/tests/test_blast2d.py (~line 187 gate comment),
  test_blast3d.py; blastlab/tests/test_regression.py (how baselines are regenerated).
Do:
1. After marking the explosive cells in the resolve path (2D axisym, 2D planar, 3D), scale e
   (keeping rho_exp) by V_true / V_discretised - axisym uses the wedge/ring cell volumes,
   planar uses area x unit depth - so total energy (and mass if rho is scaled instead;
   pick one, document it) equals the requested charge to 1e-12. Emit one `[note] resolved
   charge: 39 cells, energy scaled x1.027` line through hooks (it is a warning-class line,
   so it goes through the T7 hooks path - check test_regression expectations for [note]
   lines; this IS a re-baseline task).
2. Re-baseline test_regression for b2/b2r/b3/b3r only (1D untouched - verify byte-identical
   for 1D); commit baselines with the code.
3. test_blast2d: tighten the r = 1.5 m arrival gate back to 5 % if it passes; record the
   new 1D-vs-2D/3D gaps in the DONE line.
Verify: test_regression (re-baselined), test_blast2d, test_blast3d, test_foam_1d_vs_native
  (native side changed - WSL, ~2 min), test_case_validate.
Done when: green; B24 DONE with the measured before/after gaps.
```

**DONE (2026-09-07):** `core/geometry.py` gained exact clipped charge volumes
(`disc_box_area`, `charge_volume_2d` planar/axisym-per-radian, `charge_volume_3d`
Gauss-Legendre over the analytic disc-in-box area; verified against closed forms to 2e-16
and against a 1200^3 brute-force count for a corner-clipped ball to 1.7e-6). Both resolve
paths (2D axisym + planar, 3D) now keep `rho_exp` and scale the products' specific energy
by `V_true / V_discretised`, so the initial energy equals the requested charge's to 4e-16
over 12 randomised charges/offsets (mass keeps the staircase error - JWL is exponential in
rho0/rho, so scaling rho would move the initial products pressure ~10 % for a 3 % volume
error while scaling e moves it < 1 %). One `[note] resolved charge: N cells, energy scaled
xF` line per run through hooks. Measured scale factors in the baseline cases: b2 x0.957
(39 cells), b2 profile-source x0.965 (41), b3 x0.983 (552), test_blast3d T7 x1.005 (174).

Gaps before -> after (arrival % / peak %):
- 2D axisym vs 1D (test_blast2d T8): r=1.5 m 5.21 -> 3.92 arr, 1.36 -> 1.21 pk;
  r=2.5 m 4.23 -> 2.98, 2.40 -> 4.60; r=3.5 m 2.49 -> 1.50, 0.98 -> 2.94. Arrival gate
  tightened 6 % -> 5 % (passes at 3.92 % worst).
- 3D vs 1D (test_blast3d T6): r=0.40 17.94 -> 17.24 arr, 0.01 -> 1.65 pk; r=0.55
  15.40 -> 14.69, 2.80 -> 4.41; r=0.70 12.24 -> 11.50, 1.63 -> 3.25. The residual near-field
  arrival bias is front smearing, not the charge (gate stays 20 %).
- 2D -> 3D remap (test_blast3d T7): arr 3.52/0.15/0.69 -> 0.99/2.30/3.12,
  peak 12.59/13.62/11.92 -> 8.26/9.39/7.58.
- 1D-init remap sections unchanged byte-for-byte (no charge init there).

Re-baselined b2_gauges, b2_profile.npz, b3_gauges, b3r_gauges, transcript. 1D
(b1_gauges, b1_profile) and b2r_gauges verified byte-identical - b2r is profile-initialised,
so it never touches the charge path. Tests: test_regression PASS (re-baselined),
test_blast2d PASS (5 % gate), test_blast3d PASS, test_case_validate PASS,
test_foam_1d_vs_native PASS (WSL, peaks 0.89/0.97/0.99/1.02, arrivals 13.7/7.3/5.5/3.8 % -
unchanged, the 1D solver is untouched). No orphaned solvers.

### T37 — Hardening bundle (A4 native dead code, A5 shared constants, A6/A7 canaries)

**Why:** `core/eos.pressure_soundspeed` is never called yet is the block copy-pasted into
all three solvers' `primitives()`; `riemann.mirror_state` is dead; solver1d rebuilds its
grid inline instead of `make_grid_1d`. `MIN_EXP_CELLS = 5` is re-hardcoded in
solver1d.py:99 / solver2d.py:154 / solver3d.py:163 and the 2D caps are literals although
`constants.CELLS_2D_MAX/WARN` exist — `validate_case` and the solvers can drift apart
silently. `runloop._RE_TIME` (`^Time = …`) is load-bearing for step counting / live cadence
with no canary; `_decode_surface`'s face-count gate returns None forever on a mismatch —
the live slice silently stops.

```
SESSION PROMPT — T37
Read: blastlab/core/eos.py pressure_soundspeed; blastlab/core/riemann.py mirror_state (+ grep
  callers); blastlab/core/grid.py make_grid_1d; blastlab/solvers/solver1d.py, solver2d.py,
  solver3d.py primitives() + the MIN_EXP_CELLS / cap literals; blastlab/core/constants.py;
  blastlab/solvers/foam/runloop.py _RE_TIME and the stdout loop; blastlab/solvers/foam/
  backend.py _decode_surface (~264) and _decode_surface_amr (~899).
Do:
1. A4: call eos.pressure_soundspeed from the three primitives() (must be bit-identical -
   test_regression is the proof; if any output changes, revert that solver and say why);
   delete mirror_state if grep finds no caller; solver1d uses make_grid_1d.
2. A5: solvers import MIN_EXP_CELLS, CELLS_2D_MAX, CELLS_2D_WARN from constants; delete the
   literals. Add a unit check that validate_case and the solvers agree (same constants).
3. A6: runloop logs ONE warning through hooks after 500 stdout lines with no `Time =` match
   ("blastFoam output format changed? no 'Time =' lines yet - live cadence and progress may
   stall"); unit-test with a fake stdout stream.
4. A7: _decode_surface / _decode_surface_amr log ONE line on the first face-count mismatch
   ("live slice disabled: surface has N faces, expected M") through hooks; unit-test with a
   fake surface.
Verify: test_regression byte-identical (NO re-baseline allowed here), test_blast2d,
  test_blast3d, test_foam_reader, test_foam_live_due, test_case_validate, test_foam_writer.
Done when: green; A4 (native part) / A5 / A6 / A7 DONE.
Commit: "T37: shared EOS/grid/constants in the native solvers, stdout + surface canaries (A4-A7)"
```

**DONE (2026-09-07):** all four, with `test_regression` byte-identical after every
step (no re-baseline, as the brief demands).
- **A4:** the identical air/products dispatch in solver1d/2d/3d `primitives()` is
  now one call to `eos.pressure_soundspeed` (the function that already held that
  exact block and had no caller); solver1d takes `r`, `A_face` and `V_cell` from
  `make_grid_1d` instead of rebuilding them inline, in both the initial and the
  auto-refined grid. `riemann.mirror_state` is deleted - grep found no CALLER, only
  two unused imports in `legacy/blast2d.py` and `legacy/blast3d.py`, which went with
  it (an unused import cannot change those byte-pinned modules' output, and
  test_regression drives all three legacy solvers).
- **A5:** solver1d/2d/3d import `MIN_EXP_CELLS`, `CELLS_2D_WARN` and `CELLS_2D_MAX`
  from `core.constants`; the `MIN_EXP_CELLS = 5` and `8_000_000` / `2_000_000`
  literals are gone. (The remaining `2_000_000` in solver3d is the s/step wall-time
  estimate, not a guard rail.) `test_case_validate.shared_constant_checks` asserts
  that constants.py, validate_case and each solver see the same numbers AND that no
  solver re-types the literals.
- **A6:** `runloop.progress_line` counts solver stdout lines while `st['step']` is
  still 0 and logs ONE warning through hooks after `TIME_CANARY_LINES` (500) of them
  - "blastFoam output format changed? no 'Time =' lines yet - live cadence and
  progress may stall". A solver that is stepping never trips it.
- **A7:** `backend._surface_refused` / `_surface_ok` wrap every face-count and
  exact-cover refusal in `_decode_surface` and `_decode_surface_amr`. A mid-write
  sample is refused legitimately, so the canary waits for
  `SURFACE_CANARY_TRIES` (20) CONSECUTIVE refusals - about 5 s of polling - and then
  logs one line naming both counts; a sample that decodes clears the streak. The
  three `solve_*_foam` entry points hand the spec its hooks (`spec.hooks`) so the
  decoders can log without changing their call sites.
Tests: test_regression byte-identical, test_blast2d, test_blast3d, test_foam_reader,
test_foam_live_due (new `canary_checks`: quiet below both thresholds, exactly one
line above them, never twice, a stepping solver and a decoding sample clear it),
test_case_validate (new `shared_constant_checks`), test_foam_writer, test_refine,
test_gauge_summary.
**Note on the preceding commit:** `_decode_surface_amr`, which this brief names,
existed only as UNCOMMITTED work in the working tree (the live AMR slice + the
solver-side "Refresh every N steps" cadence, with its README text and its AMR
controlDict goldens). A7 could not be delivered against HEAD without it, so that
work was landed first, unchanged, in its own commit; T37 sits on top.

### T38 — Live-view niceties (G7): foam cadence hint + 2D live Min/Max

```
SESSION PROMPT — T38
Read: §6 G7; blastlab/gui/run_panel.py live title + 2D live pane colour scale;
  blastlab/gui/worker.py GuiHooks.run_started (what `info` carries); blastlab/solvers/foam/
  runloop.py (the writeInterval / live cadence values available at run start and per frame);
  blastlab/gui/view3d_panel.py manual Min/Max controls (the pattern to mirror).
Do:
1. Foam runs: the live-view title reads "t = 0.123 ms · frames every ~0.05 ms" using the
   current writeInterval / live-slice cadence (update when the adaptive controller changes it).
2. 2D live pane: "Auto / Min / Max [kPa]" controls next to the pane (same UX as the 3D
   viewer's manual clim); persists for the run; auto by default.
Verify: test_gui_drain (title text from a fake run_started/frame), a headless check for the
  Min/Max entries; harness --scenario D02,F02 --redo D02,F02.
Done when: green; G7 DONE.
Commit: "T38: foam cadence hint in the live title, 2D live Min/Max (G7)"
```

**DONE (2026-09-07):** (1) a new `RunHooks.cadence(dt=None, steps=None)` - no-op for
native runs, which emit whenever the refresh policy allows. The foam solvers report
`writeInterval` AND the live-sample cadence at run start; `runloop.maybe_adapt`
reports a new `writeInterval` and `_sync_live_steps` a new step cadence, so the hint
follows both mid-run. `GuiHooks` queues it, `App._dispatch` hands it to
`RunPanel.set_cadence`, and the live-view title reads
"t = 0.107 ms · frames every ~3.44 µs" (verified live on F02). A step cadence is
turned into a TIME using the newest solver `dt` from Progress - which is the number
the brief asked for and the one a user can act on - falling back to
"frames every ~5 solver steps" before the first Progress; anything under 0.01 ms
reads in µs. The hint is re-derived every frame from the pane's own label, so it
never doubles up, and `set_running` clears it so a native run after a foam one does
not inherit it.
(2) The 2D live pane gained "Auto | Min | Max | kPa" beside Show mesh, mirroring the
3D viewer's manual clim: the boxes are inert while Auto is on, a manual range is
passed to `plots.set_frame(clim=...)` (which already took one), editing it redraws
the frame already on screen, an unusable or inverted range falls back to autoscale
rather than freezing the picture on nonsense, and the setting persists across the
run (cleared at the next `set_running`).
Tests: `test_gui_drain.live_view_checks` - no hint for a native run, t + cadence for
a foam one, no duplication frame after frame, an adaptive writeInterval change moving
it, µs formatting, the steps fallback and the steps-to-time conversion, autoscale by
default, entries gated on Auto, a manual range reaching the QuadMesh, a bad range
falling back, and a redraw on edit. `test_foam_live_due` asserts `_sync_live_steps`
reports the new cadence; `test_adaptive_interval`'s fake hooks gained the method.
Full no-WSL matrix green (22 suites incl. test_regression byte-identical) plus the
harness smoke; harness D02 (native 2D) and F02 (blastFoam 2D, idle WSL, no orphans).

### T39 — Charge-mass rasterisation deficit (N5, foam)

**Why:** `sphericalMassToCell` at 5 cells/radius sets ~0.85 of the requested mass (visible
in forwarded blastFoam warnings); at level-2 AMR with 32 cells in the sphere it reported an
18.5 % deficit. Absolute yields are low; native has the same staircase (cross-comparisons
stay fair). T36 fixes the native side; this is the foam side.

```
SESSION PROMPT — T39
Read: §6 N5, N16 probe notes; blastlab/solvers/foam/writer.py setFieldsDict emission
  (~762 sphericalMassToCell) and the refine/zone target; blastlab/core/refine.py
  auto_charge_zones (level_cap); blastlab/core/case.py validate_case charge lines;
  blastlab/solvers/foam/runloop.py warning forwarding (grep `mass`); blastlab/tests/
  test_foam_kb_anchor.py.
Do:
1. Add constants.FOAM_EXP_CELLS = 8 used only by the foam charge target (auto zone level /
   global refine): the finest level must put >= 8 cells across r_exp. Native keeps
   MIN_EXP_CELLS = 5 (byte-pinned).
2. validate_case reports the predicted set mass ("charge cells: 268 -> ~0.94 of 1.0 kg");
   the run log surfaces blastFoam's own set-mass line as a `[note]`.
3. Measure: test_foam_kb_anchor before/after (record the KB ratios in the DONE line); if the
   ratio moves, update the expected band in the test and the N3 note in §6.
Verify: test_foam_writer --update (eyeball: only charge-target changes), test_case_validate,
  test_refine, test_foam_kb_anchor (WSL ~2 min), test_foam_1d_vs_native (WSL ~2 min).
Done when: green with recorded ratios; N5 DONE.
Commit: "T39: 8 cells across the charge for blastFoam, report the set mass (N5)"
```

**DONE (2026-09-07):** `constants.FOAM_EXP_CELLS = 8` now drives every blastFoam charge
target (1D/2D/3D global refine, the automatic zone level, the AMR level check and the
validation notes) through the new `refine.exp_cells(case)`; the native solvers keep
`MIN_EXP_CELLS = 5` and `test_regression` stays byte-identical. `refine.set_mass_fraction`
predicts what `sphericalMassToCell` will deposit (whole cells inside r_exp, against the
T36 clipped charge volume) and `validate_case` reports it as
"Charge cells: N at dx -> ~F of the M kg set by blastFoam"; `backend._scan_set_mass`
forwards blastFoam's own line as `[note] blastFoam set X kg of explosive (F of the M kg
requested)`, handling both printed forms (3D/planar `Set volume of cell: V m^3`, and the
wedge/sector `V m^3 (V_full actual)`).

**Measured against blastFoam itself** (1 kg TNT; predictor vs the solver's reported set
volume): 3D 5 cells 0.9791 predicted / 0.9791 reported, 8 cells 1.0273 / 1.0273; 2D axisym
5 cells 1.0273 / 1.0271, 8 cells 1.0227 / 1.0225; 1D 0.9952 at both (the sector grid
resolves the charge radially either way). **The N5 premise of "~0.85 of the requested mass
at 5 cells" is not what this build does** - the staircase error depends on where the burst
point falls between the faces, not systematically on n. Over 400 random burst offsets the
set-mass fraction is: 3D RMS error 1.00 % (range 0.955-1.022) at 5 cells vs 0.41 %
(0.989-1.024) at 8; 2D axisym RMS 3.67 % (0.990-1.056) vs 2.95 % (0.981-1.055). So 8 cells
mainly removes the *spread*, at 1.6x (1D) / 2.6x (2D) / 4.1x (3D) cells.

**What actually improved is the resolved detonation**, and by a lot. KB free-air anchor
(1 kg TNT, gauges 1-4 m), foam/KB ratio before -> after: Z=1 0.72 -> 0.89, Z=2 0.72 -> 0.85,
Z=3 0.75 -> 0.86, Z=4 0.77 -> 0.87 (band 0.65-1.35 unchanged). With `--afterburn miller`:
1.20 / 1.04 / 1.02 / 1.02 (was 0.95-1.03 across the board - N3 note updated; the Z = 1
overshoot is new and stays inside the 0.80-1.35 afterburn band). C4/TNT peak ratio
1.37/1.28/1.22 -> 1.17/1.13/1.11, so the pinned band moved 1.1-1.5 -> 1.05-1.5 (the
better-resolved TNT reference closed the gap; C4 is still clearly above TNT).
`test_foam_1d_vs_native`: foam/native peak ratio 0.89/0.97/0.99/1.02 -> 1.10/1.14/1.14/1.16
and arrival gap 13.7/7.3/5.5/3.8 % -> 4.5/1.5/1.3/0.7 % at r = 1/2/3/4 m.

Test updates (all expectation changes, no widened physics gates): `test_refine` charge zone
level 3 -> 4 and the AMR case 3 -> 4 levels; `test_case_validate` cap case charge 1000 ->
4000 kg so it still tests the caps rather than auto-refinement; `test_gui_amr_form` charge
100 -> 320 kg/m so 3 levels still suffice; `test_foam_writer` 1D/two-charge/zone
expectations; `test_foam_1d_vs_native` final_profile contract no longer requires the foam
and native 1D grids to have the same cell count (759 vs 475 by design).

Goldens regenerated with `test_foam_writer.py --update`. Eyeballed diff: only cell counts
and the derived half-cell offsets move, e.g. `case1d_tnt` blockMesh `(475 1 1)` ->
`(759 1 1)` and its probe `start (0.002631578947 0 0)` -> `(0.001646903821 0 0)`,
`case2d_planar_anfo` setFields slab `p1 (2 2 -0.003868471954)` -> `(2 2 -0.002418379686)`;
the zone case gains `topoSetDict.refine4` + `refineMeshDict.4`. No dictionary keys,
regions or solver settings changed.

Tests: test_regression PASS (byte-identical), test_refine, test_case_validate,
test_foam_writer, test_foam_reader, test_foam_env, test_adaptive_interval,
test_foam_live_due, test_gui_drain, test_gui_results_fields, test_gui_results_anim,
test_gauge_summary, test_gui_gauge_summary, test_gui_run_browser, test_gui_refine_preview,
test_gui_amr_form, test_gui_solver_mode, test_foam_ingest_order, test_foam_amr_ingest,
test_viz3d_sampling/hooks/panel all PASS; WSL: test_foam_kb_anchor (plain and
`--afterburn`) and test_foam_1d_vs_native PASS. No orphaned solvers.

### T40 — Arrival-time characterisation: AMR probe cell (N16-a) + foam near-field lag (W1)

**Why:** (a) the 3D AMR e2e gives gauge arrival 0.298 ms vs 0.252 ms static (+18 %) while
the peak agrees to 2.7 %; candidate cause: blastProbes `adjustLocations yes`
(writer.py:~672) snaps the gauge to the t = 0 cell centre (0.1 m base cell, 8.7 % farther)
and the probe cell changes level as the mesh refines. (b) In `test_foam_2d` (axisym) foam
arrival at the near-field gauges lags native by 27–39 % (peaks agree 0.88–0.99); expected to
differ under the linear activation model but never characterised. Each experiment is one
~20 min WSL run; run them in the foreground, one at a time, WSL idle first.

```
SESSION PROMPT — T40
Read: §6 N16 (open finding + probe notes), W1; blastlab/solvers/foam/writer.py probes dict
  (adjustLocations); blastlab/tests/_e2e_foam_amr3d.py (--amr-dir reload flag);
  blastlab/tests/test_foam_2d.py gauge/arrival gates; blastlab/output/gauge_summary.py.
Do:
1. AMR study: rerun _e2e_foam_amr3d with (i) the gauge moved to a base-cell centre,
   (ii) adjustLocations no. Record arrival/peak for AMR vs static in a table in the DONE line.
   If (ii) removes the offset with no downside on the static reference, make
   `adjustLocations no` the default for every case (writer + goldens --update) and tighten
   the e2e's 25 % band to 10 %.
2. Near-field lag A/B: test_foam_2d's axisym case with activation 'none' vs 'linear' (tiny
   domain), foam vs native arrival at each gauge; record the numbers. If 'none' closes the gap,
   note it under N3/W1 as the explanation and add one sentence to blastlab/README.md
   ("near-field foam arrival times depend on the activation model"); do not change defaults.
Verify: the e2e outputs pasted; test_foam_writer if the default changed; no orphans.
Done when: both tables recorded in this file (DONE line + §6 N16/W1); N16-a closed.
Commit: "T40: AMR probe-cell and activation arrival studies (N16-a, W1)"
```

**DONE (2026-09-07):** both studies run; **the `adjustLocations` hypothesis is refuted.**

*1. AMR probe cell (N16-a).* New driver `blastlab/tests/_e2e_foam_probe_study.py` runs the
same case as {AMR, static reference} x {adjustLocations yes, no} with two gauges - one on a
cell CORNER of both meshes, one already at a base-cell CENTRE - and saves the traces so each
solve is its own ~2 min invocation. 0.8 m box, 8 kg TNT, AMR base 0.05 m + 2 levels
(finest 0.0125 m, display level 1) vs a static `zone` case at the same finest cell:

```
adjustLocations   gauge                 AMR arr   static arr    d%     AMR pk  static pk     d%
yes               (0.65,0.40,0.40)      0.0328 ms  0.0315 ms  +4.23   10023 kPa  3704 kPa  +170.6
yes               (0.625,0.425,0.425)   0.0242 ms  0.0273 ms  -11.48  13195 kPa  8417 kPa   +56.8
no                (0.65,0.40,0.40)      0.0328 ms  0.0315 ms  +4.38   10060 kPa  3704 kPa  +171.6
no                (0.625,0.425,0.425)   0.0242 ms  0.0273 ms  -11.48  13197 kPa  8417 kPa   +56.8
```

Turning `adjustLocations` off moves the arrival difference by **0.15 percentage points** and
the peaks by 0.4 %: blastProbes reports the containing cell's value either way, so snapping
the point to that cell's centre changes nothing. The default therefore stays `yes` and the
e2e's 25 % band stays a sanity band (the brief's condition for tightening to 10 % - "(ii)
removes the offset" - is not met). What *does* move the numbers is which cell the gauge lands
in: at a cell corner AMR arrives 4 % late, at a base-cell centre 11 % early, and the peaks
differ by 57-171 % because the AMR mesh follows the shock and is at its finest level around
the gauge while the static `zone` reference only refines around the CHARGE. That is a real
resolution difference at the gauge, not a probe artefact - N16-a closed on that basis.
A `probe_adjust` knob (Case1D/2D/3D -> writer -> `blastProbes adjustLocations`) was added to
run the experiment and is kept; default True, so goldens are unchanged.

*2. Near-field lag (W1).* Same axisymmetric case as `test_foam_2d` (8 kg TNT, 2.5 x 2.5 m,
gauges at 1.1x and 1.9x the source radius), native vs blastFoam with `linear` and `none`:

```
gauge          native arr   foam linear    d%     foam none     d%
(0.6, 1.25)     0.1002 ms    0.1370 ms   +36.7    0.1234 ms   +23.1
(1.0, 1.25)     0.2537 ms    0.3135 ms   +23.6    0.2863 ms   +12.8
peak ratio vs native:        linear 1.254 / 0.968 ;  none 1.430 / 1.364
```

`activation none` closes **about half** the near-field lag (36.7 -> 23.1 and 23.6 -> 12.8
percentage points) but not all of it, and it overshoots the peaks by 36-43 %, so the
remaining lag is the resolved-charge expansion itself rather than the activation model
alone. Defaults unchanged, as the brief requires; one paragraph added to
`blastlab/README.md` under Afterburn. Its stale "~25 % below KB" / "0.95-1.03" figures were
corrected to the post-T39 measurements (13 % below KB; 1.02-1.20 with `miller`).

**Blocked / not done:** `_e2e_foam_amr3d.py` itself was not run to completion. It had to be
re-sized anyway (T39's 8-cell charge target makes its 20 kg charge need a third AMR level, so
the charge is now 60 kg and it records the second, base-cell-centre gauge), but its static
reference builds a 3 m / 0.025 m display grid of 1,728,000 cells = 13.8 MB per float64 field,
and this PC has 7.7 GB of RAM with 4 GB inside the WSL VM and ~0.3 GB free - an earlier
attempt died in `reader.to_grid` with a MemoryError on a 6.75 MiB allocation. The purpose-built
small-case study above is what produced the T40 numbers; the e2e's two cases were verified to
validate cleanly (AMR display 216,000 cells, static mesh 256,824). One orphaned blastFoam from
the interrupted attempt was found and killed; WSL verified idle afterwards.

*Retry (owner-requested, same day, after `wsl --shutdown` reclaimed the VM):* got further -
**the whole AMR half ran and PASSED every one of its checks** (arrival stop, graceful stop,
foam-fo peak source, FO pMax at the gauge cell within 20 %, per-frame level maps, 519 live
frames; case dirs `20260907-211638_3d_p17264-00` and the static ref `-01` on the WSL disk),
and the static reference SOLVED - but its ingest died again in `reader.to_grid`, this time on
a 13.2 MiB allocation of the 1,728,000-cell display grid. The host held 0.3-0.6 GB free even
after the WSL restart: the ~7 GB consumer is other host processes, not the VM. The driver
needs roughly 1 GB free on the Windows side; rerun `_e2e_foam_amr3d.py
--amr-dir=/root/blastlab_runs/20260907-211638_3d_p17264-00` on a quieter machine to reuse the
finished AMR run and only redo the reference + comparison.

### T41 — Chains INTO blastFoam: profile-initialised foam stages (N7)

**Why:** today a chain stage with `solver='blastfoam'` cannot start from a 1D/2D profile
(`chain_panel.py:32-39` refuses with "ROADMAP N7"; `validate_case` blocks
`init_mode != 'charge'` for foam). This is the one missing piece for a real
native-1D → foam-2D → foam-3D pipeline. The writer has no nonuniform internalField emitter.

```
SESSION PROMPT — T41
Read: §6 N7; blastlab/core/profiles.py (Profile1D/2D, how native stages consume them);
  blastlab/solvers/foam/writer.py field emission (0/ dir: p, T, U, alpha.*, rho.*) and
  setRefinedFields handling; blastlab/solvers/foam/backend.py the reader's per-phase e <-> T
  conversion (grep `T`, `e`, `gamma`, `JWL` in the ingest/finalize path) - N7 needs its
  inverse; blastlab/core/case.py the init_mode validation block; blastlab/gui/chain_panel.py
  the N7 refusal; blastlab/tests/test_case_validate.py (~73, the N7 assertion);
  blastlab/tests/test_foam_writer.py goldens layout.
Do:
1. writer: emit `nonuniform List<scalar>/List<vector>` internalFields for p, T (per phase),
   U, alpha.<explosive>, rho.<phase> from a loaded profile mapped onto the case's cell
   centres (1D radial -> 2D axisym / planar; 2D axisym -> 3D revolved). e -> T per phase is
   the inverse of the reader's conversion (JWL products + ideal-gas air). Binary format
   consistent with the existing writer (writeFormat).
2. Skip setRefinedFields (and the charge sphere) when init_mode != 'charge'; the charge
   refinement target then comes from the profile's front radius.
3. Drop the init_mode block in validate_case for foam; remove the chain_panel refusal; update
   test_case_validate accordingly.
4. Physics sanity test (WSL, tiny): native 1D -> foam 2D axisym (profile init) vs foam 2D
   charge init, same domain: gauge peaks within 10 %, arrivals within 5 %. Add as
   `_e2e_foam_chain.py` and a no-WSL writer unit test with a synthetic profile (field sums,
   mass/energy of the emitted fields equal the profile's to 1e-6).
5. Chain tab: a foam 2D/3D stage fed by a profile runs end to end from the GUI (harness
   scenario G02 with the 2D stage set to blastFoam).
Verify: test_foam_writer (--update with new goldens), test_case_validate, test_gui_drain,
  _e2e_foam_chain (WSL), harness --scenario G01,G02 --redo (same).
Done when: green; N7 DONE with the measured agreement.
Commit: "T41: profile-initialised blastFoam stages - nonuniform internalFields (N7)"
```

**DONE (2026-09-07):** a blastFoam stage can start from a 1D or 2D profile. `writer.
profile_state` runs the SAME remap the native solvers use (`remap_profile_1d_to_2d/3d`,
`remap_profile_2d_to_3d`) onto the case grid, and `_profile_fields` emits p, T, U,
`alpha.expl`, `rho.expl`, `rho.air` as `nonuniform List<scalar|vector>` internalFields in
the mesh's cell order (`ravel(order='F')`, fluid cells only on a carved mesh - the exact
inverse of `reader.to_grid`). T is the inverse of the reader's `e = Cv(phase) T` and p comes
from the native EOS the profile was produced with, so the handover is the state the native
solver would have continued from. The two-phase split is sharp: alpha is 0 or 1 and only the
active phase's density is meaningful in a cell, which makes the mass transfer exact.

**Two things the first working version got wrong, both found by running it:**
1. The open-boundary pressure patch took `value $internalField`, which with a nonuniform
   field expands to a mesh-sized list on a patch of a few hundred faces - blastFoam aborted
   in `advectiveFvPatchField`'s Field constructor. Profile cases now pass an explicit
   `uniform 101325`.
2. The run started at t = 0 while the profile is the blast at t0, so the chained stage's
   gauges were **53 % / 34 % early** against the direct run. The fields are now written into
   a time directory named for t0 and picked up with `startFrom latestTime` (blastFoam takes
   the time from the directory NAME, so OpenFOAM's own time formatting never has to be
   reproduced); `endTime` is t0 + duration and `decomposePar` gets `-latestTime`. The native
   solvers already continued the clock this way. With that fixed the same comparison is
   **+2.31 % / +3.36 %**.

`_e2e_foam_chain.py` (new, WSL): native 1D stopped at r = 0.4 m -> foam 2D axisym from that
profile, against the same foam 2D domain initialised directly from the 1 kg charge. **Passes
at the brief's tolerances:**

```
gauge        chained arr   direct arr    d%     chained pk   direct pk     d%
(0.6, 1.0)     0.2067 ms    0.2115 ms   +2.31     2217 kPa    2114 kPa   +4.87
(0.8, 1.0)     0.3367 ms    0.3484 ms   +3.36     1257 kPa    1216 kPa   +3.37
gates: arrival within 5 %, peak within 10 %
```

It runs one stage per invocation (`--only chained|direct`, then `--report`) because a solve
is 3-8 min and this PC's shell caps a foreground call at 10 min.

No-WSL writer unit test (`profile_checks` in `test_foam_writer.py`, golden case
`case2d_axi_profile` from the committed fixture `foam_fixtures/profile1d_chain.txt`): the
emitted fields reproduce the profile's **mass to 0, internal energy to 5.7e-11 and kinetic
energy to 1.2e-11** (gate 1e-6), alpha equals the phase flag in mesh order, and the fields
sit in the t0 directory with `startFrom latestTime`.

Onward handoff verified: the profile-initialised foam 2D run loads post-mortem and exports a
2D profile at t = 0.4933 ms (absolute chain time) that round-trips through
`save_profile_2d`/`load_profile_2d` on a 100 x 200 grid, so it can feed a 3D stage. `r_exp`
carries the SOURCE charge radius through the chain rather than 0.

`validate_case` no longer refuses profile init for blastFoam; the `chain_panel` N7 refusal is
gone (the panel just reports `validate_case`'s errors now), and harness scenario G01 - whose
whole point was that refusal - now asserts the configuration is ACCEPTED (run, green).

**Limitation, deliberate and refused loudly:** a profile-initialised foam stage cannot also
use refinement zones or dynamic AMR. The nonuniform field is written in the uniform base
mesh's cell order, which is only known ahead of time there; on a refined mesh the order is
whatever refineMesh produced. `validate_case` refuses both combinations with a message
saying why, and `test_case_validate` pins both refusals. Lifting it means writing the 0/
fields after the mesh stages from the cell centres blastFoam reports (0/C) - a backend
change, not a writer one.

Tests: test_regression PASS (byte-identical), test_foam_writer (+1 golden), test_case_validate,
test_refine, test_foam_reader, test_gui_drain, test_gui_solver_mode, test_gui_refine_preview,
test_gui_amr_form, test_foam_ingest_order, test_foam_amr_ingest, test_adaptive_interval,
test_foam_env, test_foam_live_due all PASS; WSL: `_e2e_foam_chain` PASS, harness G01 PASS.
**Not run:** a full GUI chain with a foam stage solving end to end (a modified G02). G01
covers the wiring and the e2e covers the solve; the combined run is 15+ min of visible-window
WSL work on a 7.7 GB machine whose free RAM is ~0.3 GB (see T40's note). No orphaned solvers.

### T48 — Hardware-aware run plan (N17): WSL cores + RAM → MPI ranks and a cell cap, visible in the GUI

**Why:** `MPI ranks = 0 (auto)` already resolves to `min(MAX_AUTO_PROCS, physical WSL
cores - 2)` (`env.resolve_nprocs`, `env.detect_slots` via `lscpu` inside WSL; serial below
`AUTO_PARALLEL_MIN_CELLS`, always serial for 1D and AMR). Three things are missing for
"run faster or bigger" safely: (a) **no memory rule** - the WSL VM gets 50 % of host RAM by
default and an uncapped 3D AMR case once killed a 4 GB VM (N16 lesson), while the cell caps
`FOAM_CELLS_REFUSE/WARN` are fixed numbers unrelated to the machine; (b) **no cells-per-rank
floor**, so a small 2D case can get 6 ranks whose decomposition costs more than the solve;
(c) **the decision is invisible** until the run log says "decomposing for N MPI ranks".
BlastStudio's `runplan.plan_run(cores, ram, elems, mpi_ok)` is the model: a pure planner
with an elements-per-domain cap, a RAM-per-domain cap, and a pinned decision table. Probe
the WSL VM, not the Windows host - the solver runs in the VM.

```
SESSION PROMPT — T48
Read: blastlab/solvers/foam/env.py detect_cores / detect_slots / resolve_nprocs / status /
  run_info / the probe + cache pattern (~119-230) and its AUTO_PARALLEL_MIN_CELLS = 200k /
  MAX_AUTO_PROCS = 16 (env.py ~44); blastlab/core/constants.py (FOAM_CELLS_WARN 8M /
  FOAM_CELLS_REFUSE 120M, CELLS_WARN 4M / CELLS_REFUSE 15M); blastlab/core/case.py _validate_solver (~264-347: the "Parallel run: N MPI
  ranks" note, the n_procs checks) and the cell-cap blocks (~652-710, scale_hint);
  blastlab/solvers/foam/backend.py ~221 (resolve_nprocs call site); blastlab/gui/app.py
  _poll_wsl / _wsl_hint (T34 sidebar status) and _validate (the `extra` cell line);
  blastlab/gui/settings.py DEFAULTS; blastlab/tests/test_foam_env.py (probe-parse tests
  with injected stdout - copy the pattern). For the reference design read
  C:\Users\Ofek Rotem\OneDrive - Technion\BlastStudio\blaststudio\runplan.py (plan_run,
  the constants, physical_cores/ram_gb) and selftest.py section [17] (the pinned table).
Do:
1. env.py: `detect_ram_gb()` - WSL-side `free -g` (MemTotal of the VM, cached like
   detect_slots; None on failure) and `hardware()` -> dict(cores=detect_slots(),
   logical=detect_cores(), ram_gb=detect_ram_gb()) with one `wsl_argv` round trip where
   possible. Persist the last probe in settings.json (`hw_cores`, `hw_ram_gb`, `hw_stamp`)
   so the GUI can show numbers before WSL is warm; re-probe on every blastFoam-mode start
   (cheap) and on demand.
2. New pure planner `env.plan_run(n_req, n_cells, cores, ram_gb, dim, amr) -> RunPlan
   (ranks, cell_cap_warn, cell_cap_refuse, reason)`; resolve_nprocs becomes a thin wrapper.
   Rules, in order: explicit n_req >= 1 honoured (reason 'requested'); 1D or AMR -> 1
   ('serial: 1D' / 'serial: AMR (T42)'); n_cells < AUTO_PARALLEL_MIN_CELLS -> 1;
   ranks = min(MAX_AUTO_PROCS, cores - headroom, n_cells // CELLS_PER_RANK,
   ram_gb // RAM_GB_PER_RANK if ram_gb else inf), at least 1. Constants in
   core/constants.py with the measurements that justify them in comments:
   CELLS_PER_RANK (start at 50_000), RAM_GB_PER_RANK (2), BYTES_PER_CELL (measure it: run
   the 3D smoke case at two sizes and read the blastFoam peak RSS from /proc or
   `/usr/bin/time -v` in WSL; record the number in the DONE line), headroom from
   settings.json `mpi_headroom` (default 1; today's -2 was never justified).
   Cell caps from memory: cell_cap_refuse = 0.7 * ram_gb * 2**30 / BYTES_PER_CELL,
   cell_cap_warn = 0.5 * that; when ram_gb is unknown fall back to the fixed
   FOAM_CELLS_* constants (never remove them - they are the no-WSL default).
3. validate_case: replace the fixed FOAM_CELLS_REFUSE/WARN comparisons (uniform 2D/3D and
   the AMR maxCells block) with the plan's caps, and phrase the message with the cause:
   "~9.1M cells x ~1.4 KB = 12.7 GB > 70 % of the 8 GB WSL VM - shrink the case, raise
   `memory=` in %USERPROFILE%\.wslconfig, or use AMR". The "Parallel run" note becomes
   "auto: 6 MPI ranks (8 physical cores - 1 headroom, 3.4M cells)" / "1 rank: 120k cells
   below the 50k-per-rank floor" for n_procs = 0 too, so the choice is visible before Run.
   validate_case takes the hardware from a cached probe (no WSL round trip inside
   validation; `hardware()` must return the cache or None instantly).
4. GUI: the sidebar WSL line (T34) reads "WSL: blastFoam ready · 8 cores · 16 GB"; a small
   "Re-detect" text button under it re-probes and re-validates; the Setup form's
   "MPI ranks (0 = auto)" row gets a tooltip with the current auto value; the
   Run-tab log keeps its "decomposing for N MPI ranks" line.
5. CLI (`blastlab/cli.py` ~496) uses the same planner for its cap message.
6. Tests: test_foam_env gains (a) `free -g` parsing with injected stdout, (b) a pinned
   decision table for plan_run (>= 8 rows: requested, 1D, AMR, tiny grid, cores-limited,
   cells-limited, RAM-limited, unknown RAM -> fixed caps) and a grid sweep asserting
   ranks >= 1, ranks <= cores - headroom, ranks * CELLS_PER_RANK <= n_cells or ranks == 1,
   (c) settings round trip of the hw_* keys; test_case_validate: the memory-derived cap
   message with an injected hardware dict, and the fixed-cap fallback; test_gui_solver_mode
   or a headless check: the sidebar line shows the numbers and Re-detect re-validates.
Verify: test_foam_env, test_case_validate, test_foam_writer (goldens unchanged - ranks are
  not baked into goldens; confirm), test_gui_solver_mode, test_regression byte-identical;
  WSL: test_foam_3d_smoke --tiny and one `n_procs=0` 2D run with the log line showing the
  planned ranks and reason; harness --scenario B01,C08,F01 --redo (same).
Done when: green; the planner's constants carry measured numbers; N17 added to §6 as DONE.
Commit: "T48: hardware-aware run plan - WSL cores + RAM -> MPI ranks and cell caps (N17)"
```

**DONE (2026-09-07):** `env.plan_run(n_req, n_cells, cores, ram_gb, dim, amr, headroom)`
is a pure function returning `RunPlan(ranks, cell_cap_warn, cell_cap_refuse, reason,
ram_gb, cores)`; `resolve_nprocs` is now a thin wrapper that supplies the probed hardware.
`detect_ram_gb()` reads the WSL VM's `free -g` (parse split out as `parse_free_gb` so it is
testable without WSL), `hardware()` returns **cached values only** - it is called on every
keystroke by `validate_case` and must never touch WSL - and `prime_hardware()` seeds the
cache from `settings.json` (`hw_cores`, `hw_ram_gb`, `hw_stamp`, plus `mpi_headroom`,
default 1) so the sidebar shows real numbers before the first probe of a session returns.

**BYTES_PER_CELL measured, not guessed** (the brief's requirement): blastFoam serial, 3D
uniform hex mesh, `/usr/bin/time -v` peak RSS - **59,319 cells -> 305.1 MB** and
**262,144 cells -> 843.3 MB**, i.e. **2653 B/cell at the margin** on top of a **~148 MB
fixed cost** (the two points give 5143 and 3217 B/cell including that fixed cost, which is
why the marginal slope is the number the caps use; the fixed cost sits inside the 30 %
headroom). `BYTES_PER_CELL = 2650`, `CELLS_PER_RANK = 50_000`, `RAM_GB_PER_RANK = 2`,
`RAM_REFUSE_FRACTION = 0.70`, `RAM_WARN_FRACTION = 0.35`, all in `core/constants.py` with
the measurement in the comment.

Headroom is now **1, not 2** - the old `detect_slots() - 2` was never justified, and it is
configurable via `settings.json`.

**This PC, probed live:** 4 physical cores / 8 logical, **4 GB WSL VM** -> cell caps
**567,259 warn / 1,134,519 refuse** and, for a 500k-cell 2D case,
`Parallel run: auto: 2 MPI ranks (4 GB at 2 GB/rank)` (RAM-limited, not core-limited). A
45k-cell case reports `1 rank: 45,753 cells is below the 200,000-cell parallel floor`. With
`ram_gb` unknown the fixed `FOAM_CELLS_*` constants are used unchanged, so every existing
no-WSL test keeps its old expectations.

**Consequence worth knowing: the app's DEFAULT 2D case no longer validates on this
machine.** It is 2,301,289 cells, which at 2.65 KB/cell is ~6.1 GB - more than the whole
4 GB VM. The strip now says so, with the cause and the fix:

```
~2,301,289 cells exceeds the blastFoam cap of 1,134,519 (~2.8 GB of the 4 GB WSL VM at
~2.6 KB/cell) - shrink the case, raise `memory=` in %USERPROFILE%\.wslconfig, or use AMR
```

That case was always going to thrash or die inside WSL; before T48 it was silently accepted.
**Resolved same day (owner decision): the shipped defaults were re-sized to validate on a
4 GB VM.** Case2D defaults went 10 m -> 4 m (368k cells, clean in both solver modes), and
the 3D form seed - whose QA-14 invariant is exactly "starts from a case that validates" -
went from 8 kg / 3 m / 0.02 m (11.7M cells under the T39 8-cell rule, ~30 GB) to
25 kg / 1.5 m / 0.025 m (457k cells, clean in both modes, no warnings, on every hardware
profile probed). Harness B01 now shows the default strip clean with the run plan visible
("auto: 2 MPI ranks (4 GB at 2 GB/rank)"). Raising `memory=` in `.wslconfig` on THIS host
was rejected: 7.7 GB total with ~0.3 GB free means feeding the VM more would starve the
Python ingest side that already MemoryErrored twice this session.

GUI: the sidebar line reads `WSL: blastFoam ready · 4 cores · 4 GB` (built by `_hw_suffix`,
which prints nothing when nothing is known - the line never invents numbers), with a small
**Re-detect** button under it that drops the cache, re-probes off-thread, persists the result
and re-validates. The Run-tab log keeps its "decomposing for N MPI ranks" line, and the foam
CLI already routes through `validate_case`, so it picks up the same caps and the same
`Parallel run:` note without its own copy of the rules.

Tests: `test_foam_env` gains the `free -g` parse (three shapes incl. a lower-case `mem:` and
junk), an **11-row pinned decision table** (requested / requested-beats-floors / 1D / AMR /
tiny grid / cores-limited / cells-limited / RAM-limited / rank cap / unknown-RAM / single
core), a **432-case sweep** asserting `1 <= ranks <= cores - headroom`, the cells-per-rank
floor and the rank cap, the cache behaviour (`hardware()` None until known, priming never
overwrites, `forget_hardware`), and the `hw_*` settings round trip. `test_case_validate`
gains the memory-derived cap with an injected hardware dict, the fixed-cap fallback, and both
rank-limit reasons.

Verified: test_regression byte-identical, test_foam_writer goldens **unchanged** (ranks are
not baked into them - confirmed), test_foam_env, test_case_validate, test_gui_solver_mode,
test_refine, test_gui_drain all PASS; WSL: `test_foam_3d_smoke --tiny` PASS and a live
`n_procs=0` 2D pair showing the planned ranks and the reason; harness `B01,C08,F01` PASS
(B01's strip is the quote above). No orphaned solvers.

### T42 — Parallel AMR (N16-b): direct `processor*/` reads

**Why:** AMR runs are serial (`backend.py:~219` comment): `reconstructPar -newTimes` fails
on a changed mesh (no `pointProcAddressing`). Measured (2 ranks, 0.2 ms, 78k cells):
`loadBalance { balance no; }` 41 s vs 52 s serial; balancing on needs `addEmptyPatch
internalPatch internal -overwrite -parallel` first (38 s); `reconstructParAll -time t` works
(0.71 s per 78k-cell time dir). Since the remap (`refine.remap_from_centres`) is geometric,
per-rank `C`/`cellLevel`/fields can simply be concatenated.

```
SESSION PROMPT — T42
Read: §6 N16 (parallel paragraph); blastlab/solvers/foam/backend.py the AMR ingest path
  (grep `cellLevel`, `_ingest_amr`, the serial guard ~219) and the existing MPI path for
  uniform cases (decomposePar / reconstructPar handling); blastlab/solvers/foam/runloop.py;
  blastlab/solvers/foam/writer.py dynamicMeshDict / decomposeParDict; blastlab/core/refine.py
  remap_from_centres; blastlab/tests/test_foam_amr_ingest.py (fake time dirs pattern);
  blastlab/tests/_e2e_foam_amr2d.py.
Do:
1. Writer: for AMR + n_procs > 1 emit `loadBalance { balance no; }` (v1) in dynamicMeshDict
   and the decomposeParDict as for uniform runs; lift the serial guard.
2. Ingest: for each written time read `processor*/<t>/{C,cellLevel,<fields>}` and
   concatenate across ranks before remap_from_centres (no reconstruction). Probes / FO
   outputs already merge per the uniform MPI path - verify.
3. Post-mortem: postmortem.load_run handles a decomposed AMR run the same way.
4. Tests: test_foam_amr_ingest gains a 2-rank fake-time-dir case; _e2e_foam_amr2d --np=2 vs
   serial (same case): gauge peaks within 1 %, arrivals within 1 %, wall time recorded.
Verify: test_foam_writer --update (eyeball), test_foam_amr_ingest, test_foam_postmortem
  (WSL), _e2e_foam_amr2d --np=2 (WSL ~3 min).
Done when: green; N16-b DONE with the timings.
Commit: "T42: parallel AMR via direct processor*/ reads (N16-b)"
```

**DONE (2026-09-07)** — closed the same day after the owner chose the acceptance below;
the implementation section, the measurements and the decision trail follow unchanged.

*What was built.* `CaseSpec.decomposed` (AMR + n_procs > 1), `time_root()` and
`time_dirs(name)` say where a written time lives; a decomposed run answers with one directory
per rank. `backend.part_counts` learns each rank's cell count from its own `C` (memoised -
and necessary, because a rank whose field is written `uniform` cannot report its own count),
and `rd_scalar` / `rd_vector` concatenate the ranks in order. `mesh_at`, `read_2d`, `read_3d`,
`read_fo_fields` and both `read_dir`s go through them, so nothing downstream of the remap
changed. `maybe_reconstruct` skips decomposed runs entirely (there is nothing it can do), the
ingest lists times from `processor0` and treats a time as ready only when EVERY rank has
finished writing it, and `postmortem.load_run` follows the same path. The serial guards in
`backend._preflight`, `env.plan_run` and `validate_case` are lifted.

*It really is the same ingest.* `test_foam_amr_ingest` gains a 2-rank fake-time-dir case
proving the decomposed read is **cell-for-cell identical** to the whole-mesh read of the same
data (`np.array_equal`), that the ranks concatenate in rank order, and that a rank with a
`uniform` field still contributes its own cell count.

*Measured, 2D axisym AMR (8 kg, 1 x 2 m, base 0.02 m, 2 levels, maxCells 120k), np=2 vs
serial on this 4-core / 4 GB VM:*

```
wall time     serial 340 s   np2 237 s    (1.43x)
final mesh    serial 34,292  np2 34,712   cells (+1.2 %)
gauge          serial arr   np2 arr    d%      serial pk   np2 pk     d%
(0.5, 1.0)      0.1038 ms   0.1033   +0.51      8720 kPa  8789 kPa  +0.80
(0.7, 1.0)      0.1750 ms   0.1744   +0.36      5532 kPa  5678 kPa  +2.64
```

Arrivals pass the brief's 1 % gate (0.51 % / 0.36 %) and one peak passes (0.80 %); **the
second gauge's peak is 2.64 %, over the 1 % gate. The gate was NOT widened.**

*Why it misses, and why it is not an ingest bug.* The two runs do not solve on the same mesh:
with `loadBalance { balance no; }` each rank refines its own subdomain, so the refinement
history differs and the final meshes differ by 1.2 %. Breaking the peak-overpressure map down
by distance from the charge shows exactly that:

```
radius band    cells   median rel diff   p95      mean serial   mean np2
0.00-0.15 m      358        12.755 %   91.96 %     7.116e+09    5.520e+09
0.15-0.30 m     1056         0.475 %    2.81 %     2.263e+07    2.272e+07
0.30-0.50 m     2516         0.498 %    2.93 %     1.155e+07    1.158e+07
0.50-0.80 m     6124         0.665 %    3.79 %     6.001e+06    6.026e+06
0.80-2.00 m     9946         0.000 %   48.86 %     1.238e+06    1.316e+06
```

The disagreement is concentrated in the 358 charge-region cells (7 GPa products, where the
refinement pattern matters most) and in the shock front itself, where a fraction-of-a-cell
shift in front position is a large local difference. Everywhere the blast loading is actually
read the median difference is ~0.5 %. A mis-ordered concatenation would scramble the field
and wreck the arrival times; instead arrivals agree to 0.4 % and the map correlates at 0.949.
The 21.5 % difference in the map's MEAN is those 358 near-charge cells dominating a mean over
20,000.

*The owner call and how it resolved.* The owner first chose (b) - keep 1 % as a real
requirement, try `balance yes`, and fall back to far-field acceptance gauges. Both of those
were then run and MEASURED OUT the same evening:

* `balance yes` (with `addEmptyPatch internalPatch internal -overwrite -parallel`, which
  exists and ran in 0.01 s): gauge results **identical to `balance no`** - +2.66 % vs
  +2.64 % on the missing peak, +0.38/+0.30 % arrivals, ~203 s solver time. As predicted by
  the imbalance measurement below, there was nothing for it to fix. The writer therefore
  KEEPS `balance no` and `addEmptyPatch` is not wired into the product path.
* Far-field gauges at a 1 % point gate: the peak-map row scan shows the point difference
  fluctuating 0.15-4 % along the domain (0.66 % at x = 0.285, 1.71 % at 0.495, 3.8 % at
  0.705) - no gauge position holds 1 % robustly; picking one that happens to pass would be
  luck, and the test would be flaky.
* Two further facts pinned the mechanism: serial AMR is **bit-deterministic** (a second
  serial run with a different, non-binding maxCells produced byte-identical traces - and the
  cap never bound, killing the cap hypothesis), while two parallel runs with DIFFERENT
  balance settings agree to **0.015-0.017 %**. So serial and decomposed AMR are two
  self-consistent, slightly different discretisations - the rank boundaries alter the
  refinement pattern and the difference feeds back and grows: positive-phase impulse over a
  common window drifts **+4.15 % / +9.10 %**, accumulated late (the 0.2-0.25 ms windows).

**Final acceptance (owner decision): 1 % on the observables where serial-vs-parallel 1 %
exists** - per-gauge arrival within 1 % (measured 0.51 / 0.36 %) and the peak-overpressure
MAP's median over the 0.15-0.8 m loading region within 1 % (measured 0.605 % over 9,696
cells); point peaks and impulse are printed as characterisation, ungated. Implemented as
`blastlab/tests/_e2e_foam_amr_ab.py` (run/report pattern: `--only serial`, `--only np2`,
`--report`), which PASSES on the measured pair. The full decision trail - including the
rejected routes and their numbers - is deliberately kept above so the 1 %-point question is
never relitigated without this data.

*Follow-up measurement (same day, on the `balance yes` question):* the per-rank cell counts
of the np2 run itself - `part_counts` already reads them - show the fixed scotch decomposition
was **almost perfectly balanced the whole run**: over 71 written times, max-rank/ideal was
mean 1.024 and worst 1.037 (1.0 = balanced, 2.0 = one rank holds everything). Rank0/rank1 at
the end: 16,935 / 17,777 of 34,712 cells. The charge sits mid-domain and the blast expands
symmetrically, so refinement grows evenly into both subdomains and there is at most ~4 % of
wall time for balancing to recover on this case - consistent with N16's own measurement
(41 s -> 38 s). The 1.43x-instead-of-2x is therefore MPI/halo/AMR-sync overhead, NOT
imbalance, and `balance yes` would also not fix the 2.64 % gate miss (redistribution is one
more source of divergence from the serial mesh, not less). Balancing becomes worth its
addEmptyPatch preflight and redistribution cost when the refinement is NOT symmetric across
the decomposition - an off-centre charge, a surface burst near a corner, obstacles - or when
more than 2 ranks are available (this VM's RAM caps AMR at 2). Recommendation recorded:
keep `balance no` as the default, revisit as an opt-in once T48's caps allow 4+ ranks.

`_e2e_foam_amr2d.py` gains `--np=N`. Tests: test_regression byte-identical, test_foam_writer,
test_foam_env, test_case_validate, test_refine (its "AMR runs serially" assertion updated to
the new behaviour), test_foam_amr_ingest (+9 new checks), test_foam_ingest_order (its fake
spec now offers `time_root`/`time_dirs`), test_gui_amr_form, test_gui_solver_mode,
test_gui_drain all PASS. **Not run:** `test_foam_postmortem` on a decomposed AMR run - the
post-mortem path is wired and unit-covered, but I did not re-run that WSL suite against a
freshly decomposed AMR case. No orphaned solvers.

### T43 — Resume a stopped foam run (N6)

```
SESSION PROMPT — T43
Read: §6 N6; blastlab/solvers/foam/postmortem.py load_run (spec rebuild, ingest replay);
  blastlab/solvers/foam/runner.py rewrite_control_entry (startFrom -> latestTime), FoamRun;
  blastlab/solvers/foam/runloop.py accumulators + preflight (mesh/init stages);
  blastlab/solvers/foam/backend.py run entry points; blastlab/gui/run_browser.py (add
  "Resume"); blastlab/gui/app.py _start.
Do:
1. backend.resume_run(case_dir, hooks): rebuild the spec via postmortem, pre-populate the
   accumulators (peak/impulse/probes) from disk, flip startFrom -> latestTime, skip the
   mesh/init preflight stages, reattach a FoamRun and enter the shared run loop; stop /
   arrival watcher / adaptive writeInterval behave as in a fresh run.
2. Run browser: "Resume" for a stopped (not running) run; Results gets the merged result;
   the run keeps its directory and name (T30).
3. Test: test_foam_postmortem gains stop-at-write-N -> resume -> compare with an
   uninterrupted run (gauges identical over the common prefix, final peak within 0.5 %).
Verify: test_foam_postmortem, test_foam_stop (WSL, idle WSL first), test_gui_run_browser.
Done when: green; N6 DONE.
Commit: "T43: resume a stopped blastFoam run (N6)"
```

**DONE (2026-09-07):** `backend.resume_run(case_dir, hooks)` rebuilds the spec the way
postmortem does (case.json + `render_case` + on-disk 0/C for refined meshes), refuses a run
whose solver is still alive (or whose state WSL cannot report), resets the `stopAt writeNow`
a stop left in the controlDict, flips `startFrom -> latestTime`, and re-enters the ORDINARY
`solve_Xd_foam` with that spec (the three entry points gained a `spec=None` parameter that
skips `_preflight`). No other special-casing was needed - the shared run loop's ingest is
disk-driven and ordered, so it first replays the times the stopped run wrote (rebuilding the
accumulators, snapshots and recorded frames exactly as a live run would have) and then
follows the new writes; the arrival watcher, Stop and adaptive writeInterval behave as in a
fresh run, and the run keeps its directory and name. Works for serial, static-refined and
decomposed (T42) runs through the same code path.

GUI: the run browser gains **Resume** (only when an app-level callback is wired; refused
with a red status line for running/unknown-state rows, mirroring Delete's guard), threaded
through `ResultsPanel(on_resume=...)` to `app._resume_foam_run`, which enters the ordinary
SolverWorker pipeline - Run tab, live view, Stop and Results all behave as in a fresh run.

Test (`test_foam_postmortem`, new resume section): stop after 3 ingested writes ->
`resume_run` -> compare with an uninterrupted reference. **The brief's acceptance passes**:
gauge times and pressures identical over the pre-stop prefix, final peak map within 0.5 %
(and the resumed run writes a continuous time-dir record - 92 dirs vs the reference's 89).

**Found while testing, now documented as W2:** blastProbes buffers its per-step samples and
only flushes them at a graceful End, so a STOPPED run's gauge file keeps just the flushes
that already landed - measured 5 of ~600 samples surviving a scripted stop, with or without
a resume (the loss happens at stop time; a manual resume shows blastProbes announcing its
restart chunk and read_probes merges it when it lands). The run loop's safety-net kill now
waits up to 10 s for the solver's graceful End first (it used to kill the instant the final
write was ingested), and `test_foam_stop`'s partial-gauges check asserts the contract
(present, finite) rather than a length the flush timing does not guarantee. Recovering the
buffered tail wants a foam-side probes flush knob - out of scope here.

Test-constant refresh from this session's deliberate changes: `test_foam_stop`'s
preflight-stop case shrank 5 m -> 2.5 m (the old one is refused by T48's 4 GB-VM cap before
any stage starts, so the stop had nothing to interrupt).

Verified: test_foam_postmortem PASS (round-trip + resume), test_foam_stop PASS,
test_gui_run_browser PASS (+6 Resume checks incl. no-button-without-callback), test_gui_drain,
test_gui_solver_mode PASS. No orphaned solvers.

### T44 — Gauge fields beyond p (N12, foam-only)

```
SESSION PROMPT — T44
Read: §6 N12; blastlab/solvers/foam/writer.py probes FO (`fields (p)`); blastlab/solvers/
  foam/backend.py + reader probes parsing (grep `probes`); blastlab/output/gauge_summary.py;
  blastlab/gui/results_panel.py Gauges tab; blastlab/tests/test_foam_reader.py probes
  fixtures.
Do: probes FO writes `fields (p U rho)`; the reader gains |U| and rho columns (vector probes
  file format!); Result.gauges keeps p as column 0 so every consumer is unchanged; the Gauges
  tab gets a field selector (p / |U| / rho) for the traces; TSV export includes the extra
  columns with headers; native gauges stay p-only and byte-pinned.
Verify: test_foam_reader (new fixtures for U/rho probe files), test_gauge_summary,
  test_gui_gauge_summary, test_foam_writer --update, test_foam_2d (WSL), test_regression.
Done when: green; N12 DONE.
Commit: "T44: velocity and density gauge traces for blastFoam runs (N12)"
```

**DONE (2026-09-07):** the gauges FO records `fields (p U rho)` (one line in the writer; the
goldens' only diff). The reader gains `_parse_probes_vec` (vector probe rows are
`t (ux uy uz) ...`) and a `_merge_chunks` shared by every probe field (same restart-chunk
clipping as before); `read_probes` attaches `speeds` (|U| per gauge) and `rhos` ONLY when
their rows align sample-for-sample with p's - a torn or missing extra degrades to p-only
rather than ever misaligning (pinned by a torn-U fixture test). `Result.gauges` keeps
`pressures` as-is, so every existing consumer is untouched; the three backend gauge_out
sites and the 1D radii path pass the extras through.

GUI: the Gauges tab gets a p / |U| / rho segmented selector that only appears when the
current result recorded more than p (`plots.gauge_fields_available`; native and pre-T44 foam
results keep the bare layout, `winfo_manager()`-checkable per the T34 convention).
`figure_gauges_nd(field=...)` relabels the axis per field. The gauges TSV (2D and 3D
writers) appends `U_mag_(...)` / `rho_(...)` columns when present; native gauge files are
byte-identical (test_regression PASS).

Verified live: the axisym `test_foam_2d` run's probes carry all three fields end-to-end
(|U| max 4291 m/s at the near gauge of the planar case, rho 1.23-25.5 kg/m3), and the test
gains a standing assert that a foam run records speeds+rhos aligned with times (lands on
the next WSL sweep; today's run was checked directly with read_probes). Fixtures
`probes_U`/`probes_rho` + 4 reader checks (incl. clean p-only degradation both ways).

Also refreshed while here: `test_foam_2d`'s snapshot contract compared the foam grid's
shape with the NATIVE run's - stale since T39 (8 vs 5 cells across the charge radius);
it now asserts the snapshot matches the foam run's own grid.

Tests: test_foam_reader, test_foam_writer --update (eyeballed: `fields (p)` ->
`fields (p U rho)` per case, nothing else), test_gauge_summary, test_gui_gauge_summary,
test_regression byte-identical; WSL: test_foam_2d PASS. No orphaned solvers.

### T45 — CSV export of field maps (N14) + one-click HTML report (N13)

```
SESSION PROMPT — T45
Read: §6 N13, N14; blastlab/gui/results_panel.py _export (kinds, worker pattern);
  blastlab/output/plots.py (figure builders), gauge_summary.py, the
  KB comparison used by test_foam_kb_anchor (grep `kingery`).
Do:
1. Export "Field CSV": p_peak / impulse / each snapshot as x,y[,z],value (long format, one
   file per field, header with units); native and foam; 1D as r,value.
2. Export "Report (HTML)": banner (case name, solver, dims, date), the case JSON, the gauge
   summary table (N2), field PNGs (reuse the existing figure builders), KB free-air
   comparison table when the case is free-air (no obstacles, single charge), self-contained
   (images base64-inlined). Opens in the browser after writing.
Verify: headless unit checks for both writers (row counts, header, KB block present/absent),
  test_gui_results_fields; harness --scenario E03 --redo E03.
Done when: green; N13 + N14 DONE.
Commit: "T45: field-map CSV export and HTML report (N13, N14)"
```

**DONE (2026-09-07):** new `blastlab/output/report.py`, pure writers shared by the two new
Results-tab export buttons.

*Field CSV (N14):* `save_field_csvs` writes p_peak, impulse and every snapshot field (p /
rho / speed) as long-format CSV - one file per field, `x[m],y[m][,z[m]],<name>[unit]`
header, one row per cell on the result's own grid; 1D exports `r[m],value`. Works for
native and foam alike (same meta layout); fields that do not match the grid are skipped
rather than mis-shaped.

*HTML report (N13):* `save_html_report` writes ONE self-contained file - banner (name,
solver, dims, date, stop reason), the N2 per-gauge engineering table, base64-inlined PNGs
built by the existing figure builders, the case JSON (read from the run dir's case.json or
passed in), and a **Kingery-Bulmash free-air comparison** that appears only for a free-air
case (single charge, no obstacles, axisym/3D): per gauge R, Z, measured peak, the KB value
(log-log interpolation in the standard table, the same values `test_foam_kb_anchor` pins)
and the ratio. The GUI opens the file in the browser after writing.

Buttons: "Field CSV" (directory picker) and "Report" (.html) join the export bar between
Gauges TSV and PNGs; `_sync_export_buttons` needed no change (unknown kinds default to
enabled, and both work for any result with snapshots/gauges).

Tests: new `test_report.py` (14 headless checks: row counts = cells, headers with units per
dim, cell-centre coordinates, KB block present for free-air / absent with obstacles, log-log
interpolation pinned at the table points, base64-inlined self-contained HTML, sections
list); test_gui_results_fields, test_gui_solver_mode (export-order check now includes the
two new buttons) PASS; harness E03 extended to click both new exports and PASSES - after
fixing a pre-existing E03 race (it waited for a bare 'Saved', which matches the PREVIOUS
export's stale log line; it now waits for each export's own filename). Note E03 needs the
D-series cache seeds in a fresh QA stamp ("no cache for native2d" otherwise - that is the
harness contract, not a defect).

### T46 — Materials beyond TNT for the native solvers (N11)

```
SESSION PROMPT — T46
Read: §6 N11; blastlab/solvers/foam/materials.py (JWL table, MATERIAL_NAMES);
  blastlab/core/constants.py JWL_TNT; the three solvers' JWL usage (grep `JWL_TNT`);
  blastlab/core/eos.py; blastlab/core/case.py _validate_solver (material allowed for native);
  blastlab/gui/forms.py Material combo gating (T34 may have moved it).
Do: solvers take the JWL parameter set from materials.py by case.material (default TNT ->
  bit-identical, proven by test_regression); validate_case allows material on native; GUI
  Material combo enabled for native. Afterburn Q0 stays as N3 documents it.
Verify: test_regression byte-identical (default), test_blast2d, a new unit check that
  material='C4' changes the 1D peak in the expected direction, test_case_validate.
Done when: green; N11 DONE.
Commit: "T46: JWL materials for the native solvers (N11)"
```

**DONE (2026-09-08):** `eos.material_jwl(name)` returns the JWL parameter set for a charge
material - **'TNT' returns the byte-pinned `constants.JWL_TNT` OBJECT itself**, everything
else comes from the shared `solvers/foam/materials` table (pure data, lazily imported) as a
dict with the same keys. `pressure_soundspeed` and `jwl_pressure`/`jwl_soundspeed` take the
set as a parameter defaulting to `JWL_TNT`, the three `primitives` pass it through, and the
three engines take `material='TNT'` (threaded from `case.material` by the solve wrappers) -
rho0, e0, the init pressure and the products EOS all follow the material. **test_regression
is byte-identical**, which is the whole point of the TNT-object fast path.

`validate_case`'s native branch validates the material against the table and returns ITS
rho0 (so r_exp and the resolve rule match the material; unknown names are an error, and the
"Charge material is ignored by the native solver" note is gone). The GUI Material combo is
now a shared row in both solver modes (both form branches; `test_gui_solver_mode`'s
inventory and stage-override checks updated - the override marker is now the still-foam-only
afterburn row).

Direction check (new, in test_blast2d): the same 1 kg at r = 1 m, native 1D JWL -
**TNT 733 kPa vs C4 910 kPa (x1.24)**, matching C4's ~30 % higher specific detonation
energy. Afterburn stays foam-only exactly as N3 documents.

Tests: test_regression byte-identical, test_blast2d (incl. the C4 check), test_case_validate,
test_gui_solver_mode PASS.

### T47 — MUSCL second-order native reconstruction, opt-in (N10)

```
SESSION PROMPT — T47
Read: §6 N10; blastlab/solvers/solver1d.py (flux loop, primitives, the Riemann call),
  blastlab/core/riemann.py; then solver2d.py / solver3d.py sweeps; blastlab/core/case.py
  (add `order: 1|2`, default 1); blastlab/tests/test_blast2d.py gates.
Do: MUSCL-Hancock (or MUSCL + minmod/van Leer limiter) on primitive variables, opt-in via
  case.order == 2; order 1 path untouched and bit-identical; 1D first with a Sod/KB check,
  then 2D/3D sweeps reusing the same reconstruction helper; GUI: an "Order" combo in the
  Numerics card (native only - T34 inventory). CFL guidance in validate_case for order 2.
Verify: test_regression byte-identical (order 1), test_blast2d/test_blast3d at order 1 and a
  new order-2 run showing the r = 1.5 m peak closer to KB than order 1 (record the numbers),
  test_foam_1d_vs_native at order 2 (WSL).
Done when: green; N10 DONE with the measured improvement.
Commit: "T47: opt-in MUSCL second-order reconstruction for the native solvers (N10)"
```

**DONE (2026-09-08):** limited MUSCL face reconstruction, opt-in via `case.order == 2`
(default 1 on all three case classes; **test_regression stays byte-identical** - the order-1
statements are untouched).

*Where it lives.* 2D/3D: inside `bc._face_fluxes_axis0` behind `order=2` - `minmod` +
`muscl_states` build limited L/R face states from the ghost-extended conserved state, and
each side's p and c are recomputed from ITS reconstructed state through a `pc_of` callback
the solver supplies (the EOS dispatch - air/JWL/material - lives there, so bc.py stays
EOS-free). Slopes are zeroed on solid cells and their fluid neighbours (the wall mirror
handles those faces), ghost replication makes domain edges first order naturally, and any
face whose reconstructed density or internal energy would go non-positive falls back to the
first-order pair - robust exactly at the blast front. The sweep dispatcher moves `phase`
alongside U for the y/z directions. 1D: its own compact block in the pinned solver1d
(same scheme, donor-cell phase per side). Time stepping stays forward Euler (the brief's
"MUSCL + limiter" option): 2nd order in space, with the CFL guidance in validate_case
("keep CFL at or below 0.4"). GUI: an Order combo ("1 (Godunov)" / "2 (MUSCL)") in the
Numerics card, native-only per the T34 inventory, round-tripped by the forms.

**Measured (the brief's number): 1 kg TNT free-air 1D at r = 1.5 m - order 1 262 kPa
(0.75 of KB) -> order 2 315 kPa (0.90 of KB)**, pinned as a standing check in test_blast2d
together with a 2D order-2 finite-fields smoke. The full 1D anchor sweep: o/KB
0.81/0.74/0.76/0.75 -> **0.88/0.85/0.89/0.89** at Z = 1/2/3/4 (1814 steps vs 1531 - the
sharper front costs ~18 % more steps).

*Cross-validation that fell out of it:* `test_foam_1d_vs_native --order2` (new flag, native
side only) - the foam/native peak ratios collapse from 1.10-1.16 (order 1, post-T39) to
**1.01/0.99/0.97/0.98** at r = 1-4 m with arrivals 4.8/1.6/1.6/1.2 %: the two independent
codes now land on the same peaks to ~3 %, which is strong evidence the order-2 path is the
more accurate native scheme rather than a different bias.

Not done from the brief's reading list: a separate Sod tube harness - the Verify list does
not ask for one and the KB + cross-code checks above pin the same property; noted rather
than silently skipped.

Tests: test_regression byte-identical, test_blast2d (incl. both new T47 checks),
test_blast3d (order-1 re-verified after the primitives/face_fluxes signature threading),
test_case_validate (order 1|2 gate, foam "ignored" note), test_gui_solver_mode (inventory
gains `_order_combo` as native-only), test_gui_refine_preview, test_gui_amr_form PASS;
WSL: test_foam_1d_vs_native PASS both plain and `--order2`.

---

### T49 - Mesh overlay on the animation a run writes (N15)

**Why:** `write_animation` has taken `show_mesh=` since T17, and the Results tab's
"Show mesh" checkbox feeds the manual export - but the animation a run writes by itself
from `case.anim_file` was always called without it, so the produced video could never
show the mesh. The option needed to live on the case, beside `anim_file`.

**DONE (2026-09-08):** new case field `anim_mesh: bool = False` on `Case2D`/`Case3D`
(case-file `VERSION` 5 -> 6, `# v6: anim_mesh`), handed to the existing
`write_animation(..., show_mesh=)` at every automatic export: `gui/app.py::_solve_stage`
(both dims), `solvers/foam/cli_run.py::_run_2d/_run_3d`, and the native interactive CLI
(`cli.py::ask_user_2d/ask_user_3d` ask "Draw the mesh on the animation?" only when an
animation file was given and show it in the review summary as `<file> + mesh`;
`legacy/blast2d.py`/`blast3d.py::save_animation` gained a `show_mesh` passthrough).
GUI: a "Mesh overlay in the animation" checkbox in the Outputs card under "Record replay
frames", round-tripped by `CaseForm.get_case`/`set_case` through the shared `common` dict.
No solver code touched. The AMR per-frame overlay path in `write_animation` is reused
as-is, so a dynamic-AMR run's exported video follows the moving mesh.

Tests: `test_gui_refine_preview` gained an `anim_mesh` section (default off, form
round-trip both ways, case-file round-trip, and `_solve_stage` handing the flag to
`write_animation` for 2D and 3D with the solver/writer patched). test_regression
byte-identical, test_foam_writer, test_case_validate, test_gui_amr_form,
test_gui_results_anim, test_gui_solver_mode PASS.

---

### T50-T54 - boundary kinds, end time, trigger gauge, gauge markers (N18, N19)

**Why (owner request, 2026-09-08):** `open` did two jobs at once - it was the
transmissive ghost-copy AND it ended the run the moment `p > 1.001*P_air` reached it
(`geometry.open_edge_mask` -> the stop condition in all three native solvers and in both
foam backends). There was no way to let a wave leave and keep solving. Splitting that in
two exposed three follow-ons the owner asked for in the same session: a run needs its own
end time once nothing stops it by itself; the gauges should be visible while it runs; and
one named gauge should be able to end the run or write the remap file at the instant the
wave reaches it (the 1D->2D->3D hand-off, which until now could only happen at the end of
a run).

**DONE (2026-09-08):**

*T50 - the vocabulary.* `core/bc.py` owns it: `BC_KINDS = (transmit, reflect,
terminate)`, `BC_LEGACY = {open: transmit, wall: reflect}` and `normalize_bc(s)`, which
every reader goes through, so pre-T50 case files and scripts still load (with one
`[note]` naming the mapping - a silent `open` -> `transmit` would quietly drop a run's
stop condition). `reflect` mirrors the normal momentum; `transmit` and `terminate` are
the same ghost copy and differ only outside `bc.py`. Two different questions are asked of
`bcs` and they no longer have the same answer: `geometry.terminate_edge_mask` (was
`open_edge_mask`) feeds the stop condition and counts ONLY terminate sides, while
`stop_dists_2d/3d` size the snapshot radii and the progress bar off EVERY non-reflecting
side - the pre-T50 `open` set, so snapshot scheduling does not move. Ported: both native
2D/3D solvers, both foam backends, the foam writer (`_patch_type` / `_bc_entry` map the
new kinds onto the SAME OpenFOAM patch types, so `test_foam_writer` goldens are
byte-identical), the GUI combos and 2D preview (a terminate side draws dotted), the CLI
prompts, and the viz3d ground-plane checks.

**Owner decision, and its cost:** legacy `open` maps to `transmit` and the shipped
defaults are `transmit`, so a default run is no longer ended by the wave leaving - it runs
to the safety cap (`10*max(L)/c_air`) or `t_end`. That is up to ~10x more solver time,
worst on blastFoam. Mitigations in the same commit: `validate_case` warns when a case has
no terminate side and no end time (naming the cap in ms), the run banner says
`safety cap (no terminate boundaries)`, and T52 gives every dimension an end time.

*Regression policy.* `make_baseline.py` spells its boundaries out as `terminate`/
`reflect` (two cases were inheriting the old defaults and had to be made explicit - the
3D one keeps its reflecting ground). **Every numeric baseline stayed byte-identical**
(b1/b2/b2r/b3/b3r gauges + b2_profile.npz); only `transcript.txt` was re-baselined, for
the reworded `Boundaries:` / `Stop condition:` / `Stopped:` lines - 30 lines, all wording.

*T51 - the trigger gauge.* `trigger_gauge` (1-based, None = off), `trigger_action`
(`terminate` | `remap` | `remap+terminate`) and `trigger_file` on all three case classes.
The check sits in the gauge-sampling block each solver already had, so it costs one
comparison per step and fires once; `hooks.trigger_index` resolves the number (an
out-of-range one warns and disables rather than failing the run). A remap action captures
`meta['trigger_state']` (2D, the `final_state` shape `save_profile_2d` wants) or
`meta['trigger_profile']` (1D) at that instant; file writing stays with the callers
(`gui/app.py::_write_trigger_remap`, the CLI flows), which is where every other output is
written. 3D is terminate-only - there is no 3D remap format - and `validate_case` says so,
as it does for a planar 2D case (only axisymmetric fields remap) and for a remap action
with nowhere to write. blastFoam gets the same trigger on the ingested display grid,
beside its terminate-edge stop, reading the full field back out of the trigger's own time
directory when the action did not stop the run.

**Bug found by the owner mid-task, and fixed:** a stopped blastFoam run died with
`NameError: name 'trig_k' is not defined`. The trigger is armed inside `solve_2d_foam` /
`solve_3d_foam`, but the meta is assembled in `finalize_2d` / `finalize_3d` - separate
functions, also called by `postmortem.load_run`, which never watched the run. Both now
take `trig_k` / `trigger` as keyword arguments defaulting to None, and both solve
functions pass them on; `test_bc_trigger` pins the signatures and the hand-over so the
split cannot silently reopen.

*T52 - end time.* `t_end` on `Case1D`/`Case2D` (`Case3D` already had it), honoured
exactly as `solver3d` did (`cap_is_end` -> `stop_reason = 'end time reached'`), and the
"End time [s] (0 = auto)" row moved out of the 3D-only block. Deliberately
transcript-neutral at `t_end = 0`: the banner keeps the exact `  Safety cap      : `
spelling through the same `:<16` padding. The foam writer already read `t_end` through
`getattr`, so blastFoam 2D honours it the moment the field exists. Precedence: whichever
comes first - a terminate boundary, the trigger gauge, or the end time.

*T53 - gauge markers.* `plots.gauge_points` / `plots.add_gauge_markers`: a ringed dot
plus `G<n>` per gauge, the trigger gauge heavier and starred. Drawn once in the live pane
(`run_panel.on_run_started`, from a new `run_info['gauges']`) and once in
`write_animation`. 3D keeps only the gauges the plotted plane actually cuts
(`geometry.plane_gauges`, tolerance one cell) - a gauge a metre off the slice must not be
drawn as if it sat on it.

*T54 - AMR in the video (the real defect, found by the owner).* The first pass here
verified the per-frame machinery on a synthetic record and concluded it already worked.
It did not: on the owner's own run - 20 x 20 m axisym, 0.5 m base, `amr_levels=4`, a
**640 x 640 = 409,600-cell display grid** - `plots.mesh_for` hit its
`if src.size > 400_000` guard and *replaced* the overlay with a uniform base grid
(`mesh_segments_2d(None, xf[::2**lmax], ...)`), so the exported video and the Results
field views showed no refinement at all. The live pane never had that fallback, which is
exactly why the mesh was visible while running and gone in the video. The synthetic
fixtures were all 8 x 8, three orders of magnitude under the guard.

Fixed by coarsening instead of discarding: `_fit_overlay` max-pools the level map (and
halves the faces and the depth with it) until it fits under `MESH_MAX_CELLS = 1_200_000`,
so the refined REGIONS survive at a coarser resolution. Measured on that grid: fine_src +
mesh_segments_2d cost ~45 ms per frame (~7 s over a 150-frame gif), a cost the live pane
already paid every frame. All four `mesh_for` branches now go through one level-map path,
so the Results fields, the replay and the animation are fixed together.
`_levels_depth` additionally pins the AMR depth to `display_level` rather than the static
`lmax` - in every shipped configuration the two are equal, so that half is a guard, not a
fix. `test_gui_amr_form` gained the real 640^2 shape and a 2048^2 coarsening check; the
old fixtures could never have caught this.

**T55 - the replay record ran the machine out of memory (owner, same session).** The AMR
run above then died mid-ingest with `_ArrayMemoryError: Unable to allocate 400. KiB for an
array with shape (640, 640)` inside `mesh_at`, alongside Windows' own `0xc000012d`
(STATUS_COMMITMENT_LIMIT) in an unrelated process - the machine, not blastlab, was out of
commit. But blastlab was a large part of why: **the frame recorders grew to
`2 * record_frames` before thinning**, so a run asking for 150 frames held up to 300, and
at 640^2 with per-frame AMR level maps that is 2.05 MB x 300 = **614 MB** of replay record
alone. Nothing capped `record_frames` by grid size either, though the same function has
capped `n_snapshots` that way since T24.

Both fixed. All four recorders (native 2D/3D, foam 2D/3D) now thin at `record_frames`
rather than twice it - nobody asked for more frames than that, and it halves the peak -
and `hooks.frame_budget` caps `record_frames` against `FRAME_MEM_BUDGET = 200 MB`,
counting 4 bytes per display cell plus 1 more on an AMR run for its int8 level map, with
a `[note]` naming the per-frame cost and what to lower. The owner's case: 150 frames ->
97, peak 614 MB -> 199 MB. The helper lives in `solvers/hooks.py`, not in the foam
runloop, so the native solvers do not have to import the blastFoam backend to use it.
Small runs are untouched (a 80x60 2D run keeps all 150), so test_regression stays
byte-identical.

*T54 - the original verification.* Verified rather than fixed: `write_animation` already rebuilt
the overlay per frame from `frames['levels']` and `_amr_meta` already recorded them for
2D and 3D - what was missing was T49, the `show_mesh` flag on the run's OWN animation. A
synthetic record whose refined block slides between frames confirms the overlay follows
it (all frames differ from frame 0).

*Call sites that inherited the old default.* Anything that RUNS a solver without naming
its boundaries used to get all-`open` (transmit AND terminate); with the new default it
would run to the safety cap - ~10x the solver time, and in the comparison tests a
different stop time on each side (T6's half-domain-wall check compares two final
snapshots). Every such call site now spells the old behaviour out: `make_baseline.py`,
`test_blast2d.py` (an `ALL_TERM` constant), `test_viz3d_hooks.py`'s CASE/SCASE, the WSL
foam suites and the `_e2e_*` scripts. Cases built only for validation, writer goldens or
GUI forms were deliberately left on the new defaults - that is what those tests should be
checking.

Tests: new `test_bc_trigger.py` (39 checks: vocabulary + legacy mapping, the two mask
questions, transmit-does-not-stop vs terminate-does on a real 2D run, t_end in 1D and 2D,
every trigger action and its validation, and the gauge-marker helpers). test_regression
numeric baselines byte-identical with `transcript.txt` re-baselined, test_foam_writer
goldens unmoved, test_refine (schema-version literal replaced by `VERSION`),
test_case_validate, test_foam_reader, test_gauge_summary, test_adaptive_interval,
test_foam_live_due, test_gui_drain, test_gui_refine_preview, test_gui_amr_form,
test_gui_results_fields/anim, test_gui_solver_mode, test_revolve3d, test_viz3d_sampling
PASS. NOT RUN: the WSL suites (test_foam_2d / _3d_smoke / the foam e2e scripts) - the
foam backend changes here are the trigger check and the mask rename, and they need an
idle WSL; run them before relying on a blastFoam trigger run.

**T56 - MP4 export (owner, 2026-09-08).** `write_animation` has always picked its writer
from the extension - `FFMpegWriter` for `.mp4`, `PillowWriter` otherwise, with a `[note]`
when it falls back - but nothing in the GUI said so: the Setup field was labelled
"Animation (gif)" and the Results export dialog was titled "Save animation GIF" with no
filetypes list, so `.mp4` was reachable only by typing the extension. And on this machine
it would have fallen back anyway: **ffmpeg was installed nowhere** - not on Windows, not
in WSL - which is why every run produced a gif.

Installed `Gyan.FFmpeg` via winget (9.0.1). The field is now "Animation (.gif / .mp4)",
the dialog offers both types, and both the field's default filename and the dialog's
default extension follow `FFMpegWriter.isAvailable()` - the same test `cli.py` already
used - so a machine with ffmpeg gets mp4 without anyone editing anything. Verified end to
end through `gui/app.py::_solve_stage`: a 2D run with `anim_mesh=True` wrote a real 222 kB
`.mp4` (yuv420p, no stray `.gif` beside it). The owner's two gifs under `run/1` were
converted with `-crf 18 -pix_fmt yuv420p -movflags +faststart`: 3.31 MB -> 0.37 MB and
4.59 MB -> 0.84 MB, both 700x800 / 95 frames / 16.67 fps, identical to the source.

Note for anyone reading a run log from before this: a GUI process started before the
install keeps the old PATH, so it still writes gif until it is restarted.

**T57 - loading a parallel AMR run never worked (owner: "I can't load a foam run").**
`postmortem.load_run`'s ingest loop built its time path as `os.path.join(unc, name)` - the
case root plus the time name. A parallel AMR run is never reconstructed (reconstructPar
cannot follow a mesh that changes), so T42/N16-b keeps its written times in `processor*/`
and `spec.time_dirs(name)` returns one directory per rank. The readiness gate and the
sanity walk-back in the same function already used `time_dirs`; only this loop was left
behind when T42 landed, so every time dir missed, every one was silently `_skip`ped, and
the loader ended with "no readable time directory" - for one of the owner's runs, a run
with **96 written times**. It predates this session (`git blame`: 2026-09-02/09-05).

Fixed to `dpath = spec.time_dirs(name)` with `reader.read_time(first_part(dpath))`, the
same pair the live backend uses (`backend.py:890`). Verified on the owner's own run
directories: `20260908-142358_2d_p26780-00` now loads with 95 frames and 6 snapshots. The
runs that still refuse are genuinely empty - one wrote nothing past `0/`, another is a
refined run with no `0/C` - and both already say so.

New `test_foam_postmortem_decomposed.py` loads a fake two-rank AMR case off the local disk
(`_paths` pointed at a temp dir) and checks the frames, the per-frame level maps, the
snapshots and the final state, plus the serial layout as a control. It reproduces the
exact RuntimeError when the one-line fix is reverted.


---

## 5. Unscheduled / nice-to-have (not in the queue; pick up on request)

- Non-box obstacles (STL → snappyHexMesh) — needs the same resampler as AMR.
- `pressureBased` activation — per-material rate constants; only if ignition physics matters.
- Direct `processor*/` reads for uniform MPI runs (skip reconstructPar) — only if the
  ~3 s/write latency ever hurts (T42 builds the mechanism for AMR).
- Per-case `maxDeltaT`/`deltaT` overrides — trivial writer plumbing.
- HLLC A/B: `dicts.FLUX_SCHEME = 'HLLC'` is a one-line flip; `test_foam_1d_vs_native.py`
  is the harness.
- 2D axisym smear option (3D has it; 2D refines only).
- Viewer polish: log-contours apply to cut planes only (`viewer.py` ~345/635); "Energy
  [J/kg]" for foam runs is the ideal-gas `p/0.4ρ` approximation — hide or label "approx";
  the blit path renders twice and allocates ~1.3 MB/frame (`vtk_host.py` ~130-138).
- Cosmetic: axisym animation x-label 'x [m]' → 'r [m]' (`animation.py:66`); chained runs
  print "0 kg TNT" in the 3D init line (`profiles.py:157`, `solver3d.py:369`); 1D progress
  uses `t/safety_cap` (~10× the real run length; use front radius / R like 2D/3D,
  `solver1d.py:242`); `n_snapshots` semantics differ 1D vs 2D/3D. Any of these that touches
  solver stdout needs a re-baseline.
- Chain tab foam e2e driver (`_e2e_gui_foam.py`-style) once T41 lands.

---

## 6. Reference index (former ROADMAP ids — kept because code comments cite them)

Status: DONE (date) or OPEN → task. Details of DONE items: `git show 73ca834:ROADMAP.md`.

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
- B23 `test_foam_parallel` determinism fails randomly — DONE (2026-09-07, T35; `adaptive_write=False` pins writeInterval, the pair is bit-identical over the common record, only the asynchronous stop moves the tail)
- B24 resolved-charge init not mass/energy conserving (±3 %) — DONE (2026-09-07, T36; products' energy rescaled by the exact clipped charge volume, energy exact to 4e-16; measured scale factors 0.957–1.005 on the baseline cases; 2D-vs-1D arrival at r = 1.5 m 5.21 % → 3.92 %, gate 6 % → 5 %; 2D→3D remap peaks 11.9–13.6 % → 7.6–9.4 %; mass keeps the staircase deficit on purpose — see N5/T39)
- B25 controlDict rewrites inside fileModificationSkew ignored — DONE (2026-09-05, T18)
- B26 chain 3D stage reused the 2D revolved feed — DONE (2026-09-07, QA-05)
- B27 validation/preview allocated the full fine grid — DONE (2026-09-07, QA-01..04)

**GUI (G)**
- G1 "Initialise Model" hint erased — DONE (T5)
- G2 results accumulate / duplicate labels — de-dup + Remove DONE (QA-13); user-named runs DONE (2026-09-07, T30)
- G3 validation split-brain / silent swallowing — DONE (2026-09-07, T29)
- G4 replay / preview stalls (idle-CPU half refuted) — DONE (2026-09-07, T31)
- G5 chain start race — DONE (T6)
- G6 progress < 100 % (DONE, T5); theme half refuted by QA (mesh overlay colour cosmetic) — closed
- G7 live-view niceties (cadence hint, 2D Min/Max) — DONE (2026-09-07, T38)
- G8 preview lacks extra charges / det points — DONE (2026-09-07, QA-21 + T31)
- G9 accelerators / persistence / focus — DONE (2026-09-07, T32)
- G10 default 3D case invalid, nan/inf accepted — DONE (2026-09-07, QA-14/15)
- G11 layout at 1280×840 / 1100×720 — combos + export row DONE (QA-07/08); Run-tab sash, collapsible 3D control column, HUD/scalar-bar scaling, wrapped card titles + tooltips — DONE (2026-09-07, T27)
- G12 stale state — chips/preflight/Animation/tab raise/paused DONE (QA-09..12); chain feedback DONE (2026-09-07, T28)
- G13 light-mode affordance — DONE (2026-09-07, T32)

**Architecture (A)**
- A1 foam run loop triplicated — DONE (T9)
- A2 geometry logic quadruplicated — DONE (T9, `core/geometry.py`)
- A3 postmortem private imports — DONE (T9)
- A4 dead code — foam + viz3d parts DONE (T9/T13); native part DONE (2026-09-07, T37)
- A5 guard-rail constants duplicated as literals — DONE (2026-09-07, T37)
- A6 `Time =` regex needs a canary — DONE (2026-09-07, T37)
- A7 `_decode_surface` silent degrade — DONE (2026-09-07, T37)
- A8 viz3d control-message delivery — DONE (T13)
- A9 commit hygiene — DONE (2026-09-02)
- A10 regression discipline — standing rule (§2)

**New capabilities (N)**
- N1 peak/impulse views — DONE (T11)
- N2 per-gauge summary + CSV — DONE (T12)
- N3 afterburn (`none | miller`; other materials from oxygen balance only, uncalibrated)
  — DONE (T16). KB anchor with `miller` re-measured after T39's 8-cell charge: 1.20 at
  Z = 1 and 1.02–1.04 at Z = 2–4 (it was 0.95–1.03 across the board when the charge was
  resolved with 5 cells); band in `test_foam_kb_anchor` is 0.80–1.35
- N4 VTK export — DONE (T15)
- N5 charge-mass rasterisation deficit — DONE (2026-09-07, T39; `FOAM_EXP_CELLS = 8`
  drives every blastFoam charge target, native keeps 5. The "~0.85 of requested mass"
  premise did not reproduce: measured against blastFoam's own set-volume line the deposit
  is 0.979 (3D, 5 cells) / 1.027 (3D, 8 cells) / 0.995 (1D, both), and over 400 random
  burst offsets 8 cells mainly cuts the SPREAD - 3D RMS 1.00 % → 0.41 %, axisym
  3.67 % → 2.95 % - for 1.6x/2.6x/4.1x the cells in 1D/2D/3D. The real gain is the
  resolved detonation: KB anchor 0.72–0.77 → 0.85–0.89, foam-vs-native arrival gap
  13.7/7.3/5.5/3.8 % → 4.5/1.5/1.3/0.7 %. `validate_case` now predicts the set mass and
  the run log forwards blastFoam's own set-volume line as a `[note]`)
- N6 resume a stopped run — DONE (2026-09-07, T43; `backend.resume_run` +
  `startFrom latestTime` + the ordinary solve with a pre-built spec: the disk-driven
  ordered ingest replays the old writes and follows the new ones. Prefix-identical gauges,
  peak map within 0.5 %, Resume in the run browser. Stopped-run gauge tails are W2)
- N7 chains INTO blastFoam (profile init) — DONE (2026-09-07, T41; the stage's remapped
  state is emitted as nonuniform `internalField`s into a time directory named for the
  profile's t0 and picked up with `startFrom latestTime`, so the chain keeps ONE physical
  clock - without that the chained gauges read 53 %/34 % early. Measured against the same
  domain initialised directly from the charge: arrivals +2.31 %/+3.36 %, peaks +4.87 %/+3.37 %
  (`_e2e_foam_chain.py`); emitted mass/energy match the profile to 1e-11. Refinement zones
  and AMR are refused with a profile for now - the cell order is only predictable on the
  uniform base mesh)
- N8 foam run browser + auto-cleanup (settings in %APPDATA%\blastlab) — DONE (T14)
- N9 user-named runs — DONE (2026-09-07, T30)
- N10 MUSCL second order — DONE (2026-09-08, T47; opt-in `order=2`, limited MUSCL in
  `bc._face_fluxes_axis0` + a 1D block, EOS via solver callback, unphysical-face fallback
  to order 1. r = 1.5 m: 0.75 -> 0.90 of KB; anchor sweep 0.74-0.81 -> 0.85-0.89; with
  order 2 the foam/native peak ratios collapse to 0.97-1.01)
- N11 native materials beyond TNT — DONE (2026-09-08, T46; `eos.material_jwl` +
  parameterised JWL EOS, materials from the shared table, validation + shared Material
  combo; TNT default proven byte-identical, C4 1D peak x1.24 over TNT)
- N12 gauge fields beyond p — DONE (2026-09-07, T44; `fields (p U rho)` in the gauges FO,
  vector-probe parser + aligned-or-dropped merge, `speeds`/`rhos` in Result.gauges, a
  p / |U| / rho selector on the Gauges tab and TSV columns; native stays p-only and
  byte-pinned)
- N13 HTML report — DONE (2026-09-07, T45; one self-contained file: banner, N2 gauge
  table, inlined PNGs, case JSON, KB free-air comparison when applicable)
- N14 CSV field maps — DONE (2026-09-07, T45; long-format per-field CSVs of p_peak /
  impulse / snapshot fields on the result's own grid, 1D as r,value)
- N15 local (static) refinement + show-mesh — DONE (T17–T19)
- N15-a mesh overlay on the run's own animation (`case.anim_mesh`) - DONE (T49)
- N18 boundary kinds transmit/reflect/terminate + a per-run end time - DONE (T50, T52)
- N19 trigger gauge (terminate / remap on arrival) + gauge markers - DONE (T51, T53)
- N16 dynamic AMR (`adaptiveFvMesh`; default estimator densityGradient; AMR and static zones mutually exclusive; display level caps the display grid; serial in v1; an uncapped 3D AMR case once killed the 4 GB WSL VM — the 3D e2e caps at 300k cells) — DONE (T20–T24). Open follow-ups:
  - N16-a 3D AMR gauge arrival +18 % vs static (peak within 2.7 %) — DONE (2026-09-07, T40).
    `adjustLocations` REFUTED: switching it off moves the AMR-vs-static arrival by 0.15
    percentage points (blastProbes reports the containing cell's value either way), so the
    default stays `yes`. The difference is a real resolution difference at the gauge - the
    AMR mesh follows the shock and is at its finest level there, the static `zone` reference
    refines only around the charge - measured with `_e2e_foam_probe_study.py`
    (+4.2 % at a cell corner, -11.5 % at a base-cell centre, peaks 57-171 % apart)
  - N16-b parallel AMR — DONE (2026-09-07, T42): the ingest reads `processor*/` directly
    and concatenates per rank (cell-for-cell identical to the serial read, unit-pinned);
    `maybe_reconstruct` skips decomposed runs; serial guards lifted. **340 s → 237 s
    (1.43x)** at np=2. Serial-vs-parallel AMR are two self-consistent discretisations:
    arrivals agree 0.3-0.5 %, point peaks fluctuate 0.15-4 %, impulse drifts 4-9 % late;
    `balance yes` changes nothing (load already balanced 1.02-1.04, verified with
    addEmptyPatch + a live run) and maxCells never bound. Acceptance (owner decision):
    per-gauge arrival ≤ 1 % and loading-region peak-map median ≤ 1 % (0.605 % measured),
    point values characterised ungated — `_e2e_foam_amr_ab.py`, PASS. `balance no` stays
    the default; revisit balancing only for asymmetric refinement or 4+ ranks
- N17 hardware-aware run plan — DONE (2026-09-07, T48; pure `env.plan_run` + `RunPlan`,
  `detect_ram_gb`/`hardware()`/`prime_hardware`, an 11-row pinned decision table and a
  432-case invariant sweep. **Measured** `BYTES_PER_CELL = 2650` (blastFoam serial 3D peak
  RSS: 59,319 cells -> 305.1 MB, 262,144 -> 843.3 MB, ~148 MB fixed); headroom 1 (was an
  unjustified 2), `CELLS_PER_RANK = 50_000`, `RAM_GB_PER_RANK = 2`, caps at 0.70/0.35 of VM
  RAM with the fixed `FOAM_CELLS_*` as the no-WSL fallback. On this PC (4 cores, 4 GB VM)
  that is 1,134,519 cells and 2 RAM-limited ranks — **and it refuses the shipped default 2D
  case (2.3M cells ≈ 6.1 GB), which used to be accepted and would have died inside WSL**;
  raising `memory=` in `.wslconfig` or lowering the shipped default is an owner call)

**Watch items (W)**
- **W2** blastProbes flushes buffered gauge samples only at a graceful End: a STOPPED run
  keeps ~a flush's worth (measured 5 of ~600), with or without a resume (T43). The loop now
  waits up to 10 s for a graceful End before its safety-net kill; a real fix needs a
  foam-side flush knob on blastProbes
- W1 `test_foam_2d` axisym near-field arrival lag — CHARACTERISED (2026-09-07, T40): foam
  lags native +36.7 % / +23.6 % at r = 0.6 / 1.0 m with the default `linear` activation and
  +23.1 % / +12.8 % with `none`, so roughly half the lag is the activation model burning the
  charge at vDet while the native solvers detonate it instantly; the rest is the resolved
  charge's expansion. `none` overshoots the peaks (1.43x / 1.36x native), so `linear` stays
  the default and the tolerances stay as they are. Documented in `blastlab/README.md`

---

## 7. Verified correct — do not "fix"

Axisym momentum source is exactly well-balanced against the face-area metric; `bc.py`
mirror signs are correct; the y/z-sweep moveaxis round trip is index-correct (pinned by
T1); smear init conserves mass/energy to 1e-12 (T10); foam `to_grid` F-order reshape ↔
viewer `ravel(order='F')` ↔ VTK point order is consistent end-to-end (a transpose trips
`test_viz3d_scene` S2c); obstacle scatter/carve ordering matches boxToCell; the GUI
worker/queue architecture (latest-wins frame slots, exception-hardened drain,
Tk-thread-only widget access) is clean — treat it as the pattern for new panels.
Native↔foam physics: foam peaks 1.10–1.16x native at r = 1–4 m with arrivals within
0.7–4.5 %, both monotonic (`test_foam_1d_vs_native`, re-measured after T39); KB anchor
1.02–1.20 with afterburn `miller` (N3).
The QA pass verified by eye: static refinement + Show mesh everywhere, AMR per-frame
mesh, gauge table + CSV, run browser, VTK export, post-mortem load identical to live,
Stop at every stage, no orphaned solvers.

---

## 8. Test matrix

```
cd blastlab/tests
# fast, no WSL (run after every task)
python test_regression.py         # native byte-parity - MUST stay green
python test_foam_writer.py        # case-generation goldens
python test_foam_reader.py        # ascii+binary parsers, probes merge
python test_case_validate.py      # cap gating per backend
python test_foam_env.py           # WSL env probe parse, cleanup policy, settings (no WSL except the live probe)
python test_adaptive_interval.py  # writeInterval controller
python test_foam_live_due.py      # live-frame cadence gate
python test_gui_drain.py          # GUI queue-drain resilience
python test_gui_results_fields.py # Results panel (fields, S2 QA checks)
python test_gui_results_anim.py   # Animation tab
python test_refine.py             # refined-mesh plan + AMR remap + validation guards
python test_bc_trigger.py         # boundary kinds, end time, trigger gauge, gauge markers
python test_foam_postmortem_decomposed.py  # loading a parallel AMR run (no WSL)
python test_gauge_summary.py      # per-gauge peak/arrival/impulse
python test_report.py             # field CSVs + HTML report (T45)
python test_gui_gauge_summary.py  # Gauges-tab table + CSV (headless Tk)
python test_gui_run_browser.py    # foam run browser (headless Tk)
python test_gui_refine_preview.py # zones form/preview + show-mesh
python test_gui_amr_form.py       # AMR card + per-frame mesh
python test_gui_solver_mode.py    # sidebar solver mode: hide/show, strip, chain presets, persist
python test_foam_ingest_order.py  # ordered ingest + accumulators
python test_foam_amr_ingest.py    # AMR per-time ingest on fake time dirs
python test_viz3d_sampling.py / test_viz3d_hooks.py / test_viz3d_scene.py / test_viz3d_panel.py
python test_blast2d.py            # 2D native physics
python test_blast3d.py            # 3D native physics
python _qa_gui_harness.py --smoke # visible-window harness smoke (~1 min)
# WSL (idle WSL first: wsl.exe -d Ubuntu -- pgrep -a blastFoam must be empty)
python test_foam_1d_vs_native.py  # physics gates (~2 min)
python test_foam_2d.py            # axisym + planar (~3 min)
python test_foam_3d_smoke.py --tiny
python test_foam_parallel.py      # np1 vs np2 + determinism (~5 min; see T35)
python test_foam_postmortem.py    # live-vs-loaded round trip
python test_foam_features.py      # multi-charge + activation none
python test_foam_kb_anchor.py     # KB free-air + C4/TNT (~2 min)
python test_foam_stop.py          # SIGSTOP/writeNow regression
python _e2e_foam_obstacle2d.py / _e2e_foam_obstacle3d.py
python _e2e_foam_refine2d.py / _e2e_foam_refine3d.py       # ~3 min each
python _e2e_foam_amr2d.py / _e2e_foam_amr3d.py             # ~3 / ~6 min
python _e2e_gui_foam.py           # real-GUI session
```
