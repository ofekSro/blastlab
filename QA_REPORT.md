# blastlab GUI — overnight UX/UI + QA pass (2026-09-07)

> **תקציר בעברית.** הרצתי את ה-GUI האמיתי על המסך (חלון 1280×840, מצב כהה ואז בהיר), נהגתי בו דרך
> הפקודות של הווידג'טים עצמם וצילמתי 367 צילומי מסך ב-59 תרחישים: ארבעת הטאבים, ולידציה, ריצות
> נייטיביות 1D/2D/3D, שרשרת, 11 ריצות blastFoam אמיתיות ב-WSL (כולל עידון סטטי, AMR דו-ממדי
> ותלת-ממדי, Stop בזמן ה-mesh ובזמן הפתרון, דפדפן ריצות, VTK, טעינה post-mortem, סגירת חלון תוך
> ריצה), החלפת ערכת נושא ורובוסטיות. **6 ממצאי S1** (קריסות/MemoryError בוולידציה ובתצוגה
> המקדימה, קריסת שלב 3D בשרשרת, שלב עם מטען מחוץ לתחום שרץ), **9 ממצאי S2** (קומבו-בוקסים
> חתוכים, כפתורי ייצוא שנדחקים מחוץ לחלון, טאב Display בצופה 3D שמציג תוכן של טאב אחר, נתונים
> ישנים בצ'יפים/בתצוגה החיה), ועוד 10 ממצאי S3 ו-11 S4. כל ממצא מפנה לצילום מסך.
> המשימות לתיקון: **T25–T33** ב-`TASKS.md` (פורמט SESSION PROMPT הרגיל).
> מה שעובד טוב ואומת בעין: כל רשימת הבדיקה הידנית של `tasksforofek.md` §2 סעיפים 5–10 ו-§3
> T11–T15 (עידון סטטי + Show mesh בכל המקומות, AMR per-frame, טבלת גייג'ים + CSV, דפדפן ריצות,
> VTK, טעינה זהה לריצה חיה), Stop בכל שלב, ואין סולברים יתומים.

## 0. How to read this / environment

- **Output dir (screenshots, logs, evidence):** `C:\Users\Ofek Rotem\blastlab_qa\20260907-0108\`
  - `shots/NNN_<scenario>_<tab>_<state>_<mode>.png` (+ `.json` sidecar) — 367 full-window captures
  - `sheets/contact_<scenario>.png` — one contact sheet per scenario (start here)
  - `key/` — the 32 decisive shots referenced below
  - `observations.md` — what the judging session saw in every sheet, scenario by scenario
  - `findings.jsonl`, `dialogs.jsonl`, `notes.jsonl`, `timing.jsonl`, `checkpoint.json`, `logs/<scenario>.log` (Run-tab log per scenario)
- **Harness:** `blastlab/tests/_qa_gui_harness.py` (visible window, real `App`, widgets driven by their own commands, dialogs intercepted and answered by script, nested Tk mainloop so worker threads behave as in production). Re-run any scenario: `python blastlab/tests/_qa_gui_harness.py --resume --scenario C10 --redo C10`; `--list` shows the matrix.
- **Environment:** Windows 11, Store Python 3.12.10, customtkinter 6.0.0, matplotlib 3.10.8, pyvista 0.47.3 / VTK 9.4.2, Pillow 12.2, screen 1920×1080 @ 100 %, window 1280×840 (the app default). WSL Ubuntu, OpenFOAM-9 blastFoam ready. 617 GB free on C:; `/root/blastlab_runs` 78 runs / 26.5 GB before, 86 runs / 27.8 GB after (auto-cleanup disabled for the harness via `BLASTLAB_SETTINGS`).
- **Working tree under test:** commit `7e9a5d7` + the uncommitted changes present at the time (another session was landing "T24 — AMR live slice + wedge remap" concurrently: `chain_panel.py`, `refine.py`, foam `backend/runloop/runner/writer.py`, goldens, `TASKS.md`, `ROADMAP.md`). The GUI was tested as it was on disk.
- **Foreign WSL solvers:** 3 solvers from that other session were running at planning time and 1 at the smoke; none during group F, so foam timings are clean.
- **Not done by this pass:** nothing was fixed; no source file was modified. The repo gained `QA_REPORT.md`, the harness, and T25–T33 briefs in `TASKS.md` + a QA block in `ROADMAP.md`.

Severity scale: **S1** crash / data loss / unhandled exception in a callback / orphan; **S2** wrong or stale data shown, controls unreachable; **S3** blocked or confusing flow, missing feedback; **S4** polish.

## 1. Executive summary

| Severity | Count | Headline |
|---|---|---|
| S1 | 6 | 3D preview/validation allocates the full fine grid (6–75 GB) → MemoryError/blank preview; 2D preview IndexError with obstacle+zone; chain 3D stage crashes / never gets a 3D view; profile stage with burst outside the domain runs |
| S2 | 9 | Combos clipped to a few px; Gauges TSV / PNGs export buttons pushed out of the window; 3D panel opens on the wrong tab; stale chips/live view after Initialise Model and during WSL preflight; Animation tab shows another result; duplicate result labels; nan/inf accepted |
| S3 | 10 | G3 validation feedback (one error, silent list rejects, modal vs strip, exports only log to the Run tab); 3D viewport 330 px wide on the Run tab; UI stalls 2–5 s; light-mode invisible segments; log lines cut; G8 preview; bad-file dialogs |
| S4 | 11 | Units chip in Pa, truncated headers/titles, figure clipping, log flood, no scrollbar in the run browser, warnings, defaults |

**Top 5 to fix first:** QA-01 (T25), QA-05 (T26), QA-07/QA-08 (T27), QA-09/QA-10 (T28), QA-16 (T29).

## 2. Baseline suites (group A)

The fast no-WSL suites were **not** re-run by this pass: another session was running the WSL suites concurrently and the working tree was changing under it (T24), so the results would not have been attributable. The GUI-driving e2e coverage below (D–I) is the pass's own evidence. `test_gui_drain.py` (modified in the tree) is the only automated coverage of the uncommitted chain change; G01 verified that change by execution.

## 3. Findings (ranked)

### S1

**QA-01 [S1] The 3D Setup preview/validation builds the full fine grid on the Tk thread; the default 3D case tries to allocate 6.4 GB.**
- Area: Setup (3D). Shots: `016_B03_setup_form3d_top_dark`, `085_C08_setup_3d_large_warning_dark`; stdout `3D preview error: Unable to allocate 6.37 GiB for an array with shape (949, 949, 949) and data type int64`, then `815 MiB (int8)` on every later keystroke (C02).
- Repro: Setup → 3D. The default case (10×10×10 m, cell 0.1, 1 kg) is auto-refined to 0.0105 m → 949³ cells → validation says it exceeds the cap (correct), then the preview still tries to rasterise 949³. Each field edit repeats it.
- Expected: no allocation once the case is over the cap; a message in the preview card. Actual: 3.5–5.5 s UI stall per edit, blank dark preview, error only on stdout.
- Suspected: `preview_panel.Preview3DPanel.show_case` / `core/refine` fine-grid construction not gated by `ValidationReport.n_cells` vs the cap. Also QA-14: the default 3D case is invalid out of the box.
- Task: T25.

**QA-02 [S1] `validate_case` on the owner's checklist zone case raises MemoryError (50.9 GiB, 3796³) inside the Tk callback; strip and preview go stale.**
- Shots: `089_C10_setup_3d_zones_preview_dark` (strip/preview still show the previous 2D case). Evidence: `findings.jsonl` C10 tk-exception.
- Repro: 3D, blastFoam, 10 m box, cell 0.5, 1 kg, charge refinement `zone`, zones `4 6 4 6 4 6 1` and `4.5 5.5 4.5 5.5 4.5 5.5 2` (tasksforofek §2.2–4).
- Cause: the 1 kg charge needs ~5 auto levels below 0.5 m; `plan_levels` builds an int8 display grid of (10/0.0026)³ before any cap check.
- Task: T25.

**QA-03 [S1] Tiny cell size → MemoryError (74.5 GiB, arange of 1e10) in validation; cell = 0 leaks a ZeroDivisionError.**
- Evidence: I05 tk-exception for `cell = 1e-9` (the strip afterwards shows the cap error, but the exception already escaped); C02 tk-exception `ZeroDivisionError: float division by zero` while the strip shows "Cell size must be > 0".
- Suspected: `core/grid.py` axis construction called (preview or validation) before the cap/positivity check. Task: T25.

**QA-04 [S1] 2D preview IndexError (boolean axis 642 vs 641) for a planar refinement case with an obstacle.**
- Shots: `326_H01_setup_preview_dark_dark` (first H01 run: stale axisym preview), evidence H01 tk-exception ×3.
- Repro: 2D planar 3.0×2.0 m, cell 0.05, 5 kg/m at (1.0, 0.5), obstacle (1.5, 1.8, 0, 0.6), gauge (2, 1), solver blastfoam, zone (0.5, 1.5, 0, 1.0, 1), Show mesh on. Also with Lx = 3.0001.
- Suspected: `preview_panel.Preview2DPanel.show_case` → `plots.mesh_for`/`refine.mesh_segments_2d` vs the solid mask: off-by-one on the fine axis when Lx/dx_fine rounds. Task: T25.

**QA-05 [S1] Chain: the 3D stage reuses the 2D stage's revolved 3D feed → IndexError crash when the 2D stage is short; in every chain the 3D live view never attaches.**
- Shots: `255_G02_run_stage3_3d_dark` (placeholder shown for the 3D stage), dialog `Run failed: IndexError: boolean index did not match indexed array along axis 0; size of axis is 40 but size of corresponding boolean axis is 128`; traceback in `logs/G02.log` (first attempt): `viz3d/sampling.py:115 extract_loads`.
- Mechanism: `GuiHooks.run_started` keeps `self.feed3d` when not None (worker thread); `App._finish_view3d` sets it to None only when the Tk drain processes the previous stage's `'result'`. Stage 3 starts before that → stale 2D `Feed3D` (128-decimated revolved cylinder) is used for a 40³ field → crash; or, once the drain nulls it, `_attach_view3d_auto` finds `feed3d is None` → no 3D view for the whole 3D stage.
- Task: T26.

**QA-06 [S1] Chain validation lets a profile-initialised 2D stage with its burst point outside the domain start.**
- Evidence: G01 — 2D stage `cy = 99` (domain 2×2), fed by the 1D profile: no dialog, the chain started and produced "Run 1 - 2D (stopped)". `case.py:451` "Charge centre is outside the domain" is skipped for `init_mode != 'charge'`.
- Task: T26.

### S2

**QA-07 [S2] Combo boxes in the Initialization and Numerics cards are clipped to 40–60 px at the default 1280×840; at the 1100×720 minimum size entries show one character.**
- Shots: `001_S00_setup_coldstart_dark` (Solver shows "r", EOS "i"), `021_B05_setup_geom1100x720_dark` (Charge entry "1.", combos = arrow only). 1D form is fine; 2D/3D left column is too narrow for label "Charge refinement (blastFoam)" + a 176 px combo. Task: T27.

**QA-08 [S2] Results header: "Gauges TSV" and "PNGs" export buttons (and the "Export" caption) are pushed out of the window at 1280 px; only GIF/Profile survive at 1100 px.**
- Shots: `003_S00_results_empty_dark` ("ummary CS" clipped), `023_B05_results_geom1100x720_dark`. Six 104 px buttons + 3D Viewer + Foam runs… + a 250 px combo do not fit; `pack(side='right')` silently drops the last ones. Task: T27.

**QA-09 [S2] The embedded 3D panel opens with "Display" highlighted but shows the View tab's content; the field/colour/layer controls are unreachable until another tab is clicked.**
- Shots: `123_D04_run_live_3d_dark`, `167_E06_results_viewer_default_dark` (CAMERA PRESETS under "Display") vs `184_E06_results_time_first_dark` (after an explicit tab switch). `view3d_panel._build_controls` grids three frames and `_tab_seg.set('Display')` fires no callback; Tk stacks by creation order (viewtab last). `results_panel` does `ftab.tkraise()` for the same situation. Task: T28.

**QA-10 [S2] Stat chips show stale data: after Initialise Model they still show the previous run (step 628, t 0.460 ms) while the plot says t = 0; a paused model shows the step/time of the last throttled progress message (chip step 1 vs plot t = 0.010 ms after Exec 10).**
- Shots: `117_D03_run_initialised_dark`, `118_D03_run_exec10_dark`. `RunPanel.set_running` clears the log and bar but not the chips; `GuiHooks.progress` throttles to 10 Hz and the final message before the pause gate is dropped. Task: T28.

**QA-11 [S2] During a blastFoam preflight/meshing the live view and chips still show the previous run.**
- Shots: `266_F02_run_foam2d_checking_wsl_dark` (previous 1D plot at t = 4.243 ms shown while "checking WSL" for a 2D run), `285_F04_run_refine2d_checking_wsl_dark` (previous 3D slice + its chips). On a WSL cold start this lasts minutes. Task: T28.

**QA-12 [S2] Selecting a 1D result leaves the Animation sub-tab showing the previously selected result's frame.**
- Shot: `131_E01_results_1d_animation_dark` (a 3D slice with its obstacle under a 1D result). `_setup_anim` returns early for dim 1 without clearing the canvas. Task: T28.

**QA-13 [S2] Duplicate result labels make entries unreachable; results accumulate with no removal (G2 confirmed).**
- Evidence: E09 (programmatic), F09 (loading the same run twice → two "Loaded - 20260907-021103_2d_p20208-01 (2D)" entries, `_current()` returns the first); label truncated in the 250 px combo. Task: T30.

**QA-14 [S2] The default 3D case (10 m box, 0.1 m, 1 kg) is invalid out of the box (851 M cells over the 15 M cap) and the Cell size field is effectively ignored for small charges under `resolve`.**
- Shots: `016_B03_setup_form3d_top_dark`, `085_C08_setup_3d_large_warning_dark` (cell 0.06 → same 851 M). Task: T25 (defaults) / T29 (explain).

**QA-15 [S2] `nan`, `inf`, `1e400` are accepted as a charge (validation prints "r_exp = inf m pokes through…"); `n_snapshots = 2.7` silently becomes 2.**
- Evidence: I05 notes; matplotlib RuntimeWarnings from the nan preview. Task: T29.

### S3

**QA-16 [S3] Validation and feedback (G3 confirmed in full).** Only the first parse error is shown (`048_C01_setup_two_parse_errors_dark`); malformed point-list rows ('a b', wrong arity, '1;2') are silently ignored with the text left in the entry (`061_C04_setup_gauge_row_a_b_dark`); "Refresh every = abc" silently means automatic; a capped case shows the strip on Setup but a modal on Run (`083_C08_run_dialog-showerror_dark`); exports with nothing selected are silent no-ops; every export / loader / 3D-viewer message ("Saved …", "3D Viewer: select a 3D result.", "Export failed: save_profile_2d: only axisymmetric fields can be remapped into 3D", "3D view loaded …") goes to the **Run-tab log** while the user is on Results; the Profile button is enabled for planar 2D results although it always fails; a dropped gauge is only a log line. Task: T29.

**QA-17 [S3] The embedded 3D view on the Run tab is ~330 px wide at 1280×840; HUD text and both scalar bars are clipped; "Peak overpressure / Net ovp impulse / Energy" radios are disabled in the viewer for native and foam 3D results although the Fields list offers those maps; plane position 0.0/1.0 silently shows nothing.**
- Shots: `123_D04_run_live_3d_dark`, `278_F03_run_live_3d_dark`, `167_E06_results_viewer_default_dark`, `179/180_E06_results_plane1_pos_*`. Task: T27 (layout) / T31 (fields).

**QA-18 [S3] UI stalls: 3D preview build 3.5 s per debounce (D04 set_case), run start 1.9 s, `feed_result` 2.7 s for 3 snapshots (G4 confirmed), 3D AMR live frames 3.6 s, C02 5.5 s (QA-01).**
- Evidence: `checkpoint.json` timing, `timing.jsonl`. Idle CPU on every tab with no scene: 0–1 % (the G4 "hidden hosts burn CPU" hypothesis is refuted). Task: T31.

**QA-19 [S3] Light mode: unselected segments of every segmented button (1D/2D/3D, Stage 1D/2D/3D, Live slice/3D view, Fields/Gauges/Animation/3D) are invisible; disabled Exec/Interrupt/3D View buttons are nearly invisible; the disabled Stop button stays red in both modes.**
- Shots: `036_B07_setup_setup_default_light`, `037_B07_run_empty_light`, `006_S00_run_finished_dark`. Task: T32.

**QA-20 [S3] The Run log has `wrap='none'`: notes and warnings are cut at the pane edge ("[note] Charge is truncated by the y_lo wall (surface", "[auto] Cell size reduced to 0.01244 m (5 cells acros").** Shot `113_D02_run_live_mesh_dark`. Task: T33.

**QA-21 [S3] Preview draws only the primary charge; extra charges and detonation points are absent (G8 confirmed).** Shot `087_C09_setup_overflow_dark`. Task: T31.

**QA-22 [S3] "Open case" errors are raw parser text: "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)", "Expecting value: line 1 column 1 (char 0)", a wrong dim gives just "5", a missing file gives an Errno line with doubled backslashes.** Evidence: I03 dialogs. Task: T29.

**QA-23 [S3] Paused state is visible only as "[interrupted]" in the log; the Chain error dialog names "Stage 2" but the stage switcher stays on Stage 1D; the chain workspace directory is created before validation; the Chain "'Lx' is not a number" dialog has no stage prefix.** Shots `119_D03_run_interrupted_dark`, G01. Task: T28/T33.

**QA-24 [S3] Post-mortem loaded runs have no recorded frames → the Animation tab is empty for them with no explanation; a loaded label is truncated in the combo.** Evidence F09. Task: T30.

**QA-25 [S3] The validation status card grows with the number of lines and squeezes the scrollable form (8 lines → the form keeps ~1/3 of its height).** Shot `068_C05_setup_amr_card_on_dark`. Task: T27.

### S4

**QA-26** Chip caption "p max [Pa]" while every plot/colorbar is in kPa (`006_S00_run_finished_dark`). **QA-27** Truncated text: card title "Refinement zones (blastFoam) [m, l", checkbox "Record frames for animation/repla", table headers "Pos. impulse [Pa" / "Net impulse [Pa", 2D AMR preview title clipped both ends, Fields figure title/subtitle overlap (`289_F04_results_fields_mesh_dark`), 3D field figures clip the x-axis labels at the bottom (`156_E05_results_overpressure_x-z_dark`), 3D HUD "run ended: …" clipped. **QA-28** Matplotlib toolbar back/forward icons render as checkerboards in dark mode. **QA-29** No focus ring on entries, Tab order invisible, no accelerators, no window/mode persistence (G9 confirmed); Chain workspace default is an absolute CWD path. **QA-30** Run browser table (85 rows) has no scrollbar; the running-run refusal is a small muted status line. **QA-31** Peak-overpressure map colour scale is dominated by the charge cells (single dot). **QA-32** 62 "[blastfoam] AMR t = …" lines for a 0.5 ms run flood the log; 1D live axes show an empty −0.04…0.04 kPa range during meshing. **QA-33** "Complete" column and snapped gauge coordinates "(0.305, 0.802) m" are unexplained. **QA-34** ResourceWarning: `logo.gif` never closed (app.py:164); UserWarning `grid(False)` with line properties (preview_panel.py:199). **QA-35** Foreign-solver note: a 2-minute 3D AMR run wrote 937 MB.

## 4. Confirm / refute table

| Item | Verdict | Evidence |
|---|---|---|
| G2 results accumulate / duplicate labels | **Confirmed** | E09, F09 (`317_F09_results_duplicate_loaded_dark`) |
| G3 validation split-brain / silent swallowing | **Confirmed** (all five sub-items) | C01, C04, D02, C08, E08 |
| G4 hidden 3D hosts burn CPU / replay blocks Tk | **Partly**: idle CPU 0–1 % (refuted); `feed_result` 2.7 s + preview/run-start stalls (confirmed) | B01/B02, E06, D04 |
| G6 theme half (stale artists) | **Refuted for the preview** (re-themes without a redraw); live-plot mesh overlay keeps its colour (cosmetic) | H01 redo `364–367`, H02 |
| G7a foam cadence hint in live title | Still open (title shows only "t = …") | F02 shots |
| G7b fixed Min/Max in the 2D live pane | Still open (no control exists) | D02 |
| G8 extra charges / det points in preview | **Confirmed** | `087_C09_setup_overflow_dark` |
| G9 accelerators / persistence | **Confirmed** (Ctrl+O/S, F5 do nothing; 1280×840 dark every start) | B06 |
| tasksforofek §2.1–4 (3D 10 m, base 0.5, zones) | **FAILS** — MemoryError (QA-02) | C10 |
| §2.5 2D planar refine preview + mesh | OK | `091_C10_setup_2d_refine_mesh_dark` |
| §2.6 live slice shows coarse cells as blocks | OK | `287_F04_run_refine2d_first_write_dark` |
| §2.7 Results Show mesh (fields, peak, impulse, replay, PNG) | OK | F04 |
| §2.8 3D viewer Show mesh + plane follows | OK | E06 `176/177`, F03 `283` |
| §2.9 reload identical | OK (snapshots, gauges, p_peak equal) | F09 |
| §2.10 axisym level-2 zone on the axis refused with an explanation | OK | C06 |
| §3 T12 gauge table + Summary CSV | OK | E03, F01 |
| §3 T13 density in 3D viewer with a separate loads bar / manual Min-Max | OK for planes+loads (`168_E06_results_field_rho_dark`, `170` manual clim); volume + manual clim not exercised | E06 |
| §3 T14 Foam runs… load / delete / refresh / refuse running | OK | F08, F09 |
| §3 T15 VTK export + folder | OK (50 files; ParaView open not tested) | F02, F10 |
| §3 T16 afterburn run | Not exercised (form + strip only, C09) | — |
| §3 T11 peak/impulse fields native 2D/3D | OK; "old result without maps" not exercised | E02, E05 |
| B6/B7 preflight visibility, progress > 0 | OK | F01–F05 |
| B14/B15 no orphans after Stop / close | OK (`pgrep -a blastFoam` empty) | F07, F08, F11 |
| Uncommitted `chain_panel.stage_errors` + Run-chain disable | Works (N7 refusal dialog, button disabled during a run) | G01, G02, G03 |

## 5. Timings

| What | Value |
|---|---|
| App construction / first paint | 1.9 s / 1.85 s |
| Idle CPU (no scene) Setup / Run / Results / Chain | 0.2 / 0.6 / 0.3 / 0.3 % of a core |
| 3D preview build (set_case, 2 m box @ 0.05) | 3.5 s UI stall |
| Native 3D run start (scene build) | 1.9 s |
| `feed_result` (3 snapshots) | 2.7 s |
| Volume render toggle + blit | 95 ms |
| Native 3D 140k cells (D04) | 43 s wall |
| Foam 1D / 2D / 3D tiny / 2D refine / 2D AMR / 3D AMR | 10 / 14 / 14 / 12 / 40 / 124 s |
| Stop during blockMesh / during solve (foam) / native 3D | 1.8 s / 2.1–2.6 s / 5.3 s |
| Close window mid foam run → worker joined | 74 s scenario incl. run; no orphan |
| Post-mortem load of a 50-write 2D run | ~3 s |
| Rapid tab switching during a 3D run | max gap 0.86 s, no errors |

## 6. Dialog inventory (wording verdicts)

- `Run: 'cell size' is not a number: 'abc'` — OK but field-level highlight would be better.
- `Run: ~100,000,000 cells exceeds the 2D cap of 8,000,000` — fine; duplicated with the strip (QA-16).
- `Run: A run is already in progress.` — fine.
- `Chain: No stages selected.` / `Stages must be consecutive.` / `Stage 2 must be axisymmetric to feed 3D.` — fine.
- `Chain: Stage 2 (2D): blastFoam stages cannot start from a profile yet (ROADMAP N7) - run this stage with the native solver, or drop the stage that feeds it` — good, actionable (references an internal id).
- `Chain: 'Lx' is not a number: 'abc'` — missing "Stage n (nD):" prefix (QA-23).
- `Run failed: IndexError: boolean index did not match …` — internal (QA-05).
- `Delete run: Delete <name> (61.7 MB) from the WSL disk? This cannot be undone.` — good.
- `Open case: Expecting property name enclosed in double quotes …` / `5` / `[Errno 2] …` — not user-grade (QA-22); `Not a blastlab case file` — good.
- File dialogs: no title on Save case / Open case / most exports ("Save PNGs into" and "Load a finished blastFoam run directory" do have one).

## 7. Not exercised / skipped

- Fast test suites (group A) — see §2. `test_blast3d` and WSL suites untouched.
- Afterburn `miller` run (T16), native "old result without peak maps", volume render + manual Min/Max, ParaView opening the VTK files, DPI scaling other than 100 %, a second monitor.
- H04 automatic dark/light pixel diff — replaced by visual judgement (H01 redo, H03).
- Foam 2D axisymmetric at default size (30+ min) — deliberately avoided.

## 8. Orphan / disk / cleanup evidence

- Final `wsl.exe -d Ubuntu -- pgrep -a blastFoam`: **empty** (exit 1). `env.reap_orphans()`: nothing to reap.
- `/root/blastlab_runs`: 86 runs, 27.8 GB (8 new runs from this pass, names `*_p<pid>-NN`; F09 deleted one of them via the browser). Cleanup is the owner's call (`python -m blastlab --clean-foam-runs`).
- Power plan: DC display/sleep timeouts were set to 0 for the night and restored to 3 min / 10 min; AC values were already "never" and untouched.
- Repo: no source file touched; new files `QA_REPORT.md`, `blastlab/tests/_qa_gui_harness.py`; `TASKS.md`/`ROADMAP.md` gained the QA rows/briefs (next to the other session's uncommitted T24 hunks). Scratch outputs (gauges, GIFs, case JSONs) went to the QA output dir, not the repo.
