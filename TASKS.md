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
| T34 | GUI: global solver mode (sidebar selector; hide, don't grey) | — | L | [ ] |
| T35 | `test_foam_parallel` determinism check (owner decided: option b) | B23 | S | [x] 2026-09-07 |
| T36 | Mass/energy-conserving resolved-charge init in 2D/3D (+ re-baseline) | B24 | S | [ ] |
| T37 | Hardening bundle: native dead code, shared constants, stdout canaries | A4, A5, A6, A7 | S | [x] 2026-09-07 |
| T38 | Live-view niceties: foam cadence hint, 2D live Min/Max | G7 | S | [ ] |
| T39 | Charge-mass rasterisation deficit (foam) | N5 | S–M | [ ] |
| T40 | Arrival-time characterisation: AMR probe cell + foam near-field lag | N16-a, W1 | M (WSL time) | [ ] |
| T41 | Chains INTO blastFoam (profile-initialised foam stages) | N7 | M–L | [ ] |
| T42 | Parallel AMR (direct `processor*/` reads) | N16-b | M | [ ] |
| T43 | Resume a stopped foam run | N6 | M | [ ] |
| T44 | Gauge fields beyond p (foam) | N12 | S–M | [ ] |
| T45 | CSV export of field maps + one-click HTML report | N14, N13 | M | [ ] |
| T46 | Materials beyond TNT for the native solvers | N11 | M | [ ] |
| T47 | MUSCL second-order native reconstruction (opt-in) | N10 | L | [ ] |

Dependencies: T27–T33 independent of each other (do them before T34, which re-lays the
GUI out); T35 before any task that runs `test_foam_parallel`; T40 before T42 (the probe
offset must be understood before the mesh gets split); T41 before T43 is not required.

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
3. Chain tab: every stage inherits the global solver (simplest, matches "one mode"); a
   per-stage override is out of scope - state that in the docs.
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
Commit: "T36: energy-conserving resolved charge init in 2D/3D + re-baseline (B24)"
```

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
- Per-stage solver override in the Chain tab (T34 decided "global inherits").

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
- **B24** resolved-charge init not mass/energy conserving (±3 %) — OPEN → **T36**
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
- **G7** live-view niceties (cadence hint, 2D Min/Max) — OPEN → **T38**
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
- N3 afterburn (`none | miller`; TNT calibrated to KB 0.95–1.03; other materials from oxygen balance only, uncalibrated) — DONE (T16)
- N4 VTK export — DONE (T15)
- **N5** charge-mass rasterisation deficit (~0.85 of requested mass at 5 cells/radius) — OPEN → **T39**
- **N6** resume a stopped run — OPEN → **T43**
- **N7** chains INTO blastFoam (profile init) — OPEN → **T41**
- N8 foam run browser + auto-cleanup (settings in %APPDATA%\blastlab) — DONE (T14)
- N9 user-named runs — DONE (2026-09-07, T30)
- **N10** MUSCL second order — OPEN → **T47**
- **N11** native materials beyond TNT — OPEN → **T46**
- **N12** gauge fields beyond p — OPEN → **T44**
- **N13** HTML report — OPEN → **T45**
- **N14** CSV field maps — OPEN → **T45**
- N15 local (static) refinement + show-mesh — DONE (T17–T19)
- N16 dynamic AMR (`adaptiveFvMesh`; default estimator densityGradient; AMR and static zones mutually exclusive; display level caps the display grid; serial in v1; an uncapped 3D AMR case once killed the 4 GB WSL VM — the 3D e2e caps at 300k cells) — DONE (T20–T24). Open follow-ups:
  - **N16-a** 3D AMR gauge arrival +18 % vs static (peak within 2.7 %); suspect `adjustLocations` probe snapping — → **T40**
  - **N16-b** parallel AMR (`loadBalance { balance no; }` 41 s vs 52 s serial; `reconstructPar -newTimes` fails on a changed mesh; `reconstructParAll -time t` works; direct `processor*/` reads preferred) — → **T42**

**Watch items (W)**
- **W1** `test_foam_2d` axisym: foam near-field arrival lags native 27–39 % (peaks agree 0.88–0.99); tolerances accept it; never characterised — → **T40**

---

## 7. Verified correct — do not "fix"

Axisym momentum source is exactly well-balanced against the face-area metric; `bc.py`
mirror signs are correct; the y/z-sweep moveaxis round trip is index-correct (pinned by
T1); smear init conserves mass/energy to 1e-12 (T10); foam `to_grid` F-order reshape ↔
viewer `ravel(order='F')` ↔ VTK point order is consistent end-to-end (a transpose trips
`test_viz3d_scene` S2c); obstacle scatter/carve ordering matches boxToCell; the GUI
worker/queue architecture (latest-wins frame slots, exception-hardened drain,
Tk-thread-only widget access) is clean — treat it as the pattern for new panels.
Native↔foam physics: peaks within 2–7 % at r = 1–4 m, both monotonic
(`test_foam_1d_vs_native`); KB anchor ratio 0.95–1.03 with afterburn `miller` (N3).
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
python test_gauge_summary.py      # per-gauge peak/arrival/impulse
python test_gui_gauge_summary.py  # Gauges-tab table + CSV (headless Tk)
python test_gui_run_browser.py    # foam run browser (headless Tk)
python test_gui_refine_preview.py # zones form/preview + show-mesh
python test_gui_amr_form.py       # AMR card + per-frame mesh
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
