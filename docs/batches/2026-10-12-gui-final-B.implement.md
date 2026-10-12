# Implementation report - batch final-gui-and-ignition, Part B (B1-B11)

- **Plan:** `docs/batches/2026-10-12-gui-final.md`, Part B, plus B11 (owner-approved 2026-10-12,
  Part A verify open item 1). Branch `final-gui`, base `934028f`, commits `da05466`..`fe2abd9`
  (11 task commits) plus this report.
- **Starting state:** `gate.py --for` the 14 Part B files: 61/61 suites green (17.1 min).
- **Order run:** B2, B1, B6, B11, B7, B9, B10, B3, B4, B5, B8 (B2 first so B1's moved notes are written
  once, in the G wording; B4 after B3, B5/B8 last: same functions).
- **Gate per task:** each commit gated with `gate.py --changed <previous>` in a detached worktree
  (`C:\Users\rotem.ofek\blastlab-worktrees\partB-gate`, removed at the end) while the next task was
  written: B2 46/46, B1+B6+B11+B7 13/13, B9+B10 9/9, B3 25/25, B4 19/19 green. Each task's own
  suites were run directly before its commit.

## Tasks

### B2 - G15U-L1: `G<n>` on every trigger line - PARTIAL - `da05466`
Validation's trigger notes and its out-of-range error, `hooks.trigger_index`'s "does not exist" warn
line, the native 2D/3D and blastFoam reach lines and stop reasons now read `G3` (D9). **Not changed:**
`hooks.trigger_index`'s `Trigger gauge 2 was dropped - trigger disabled` line. Its new wording turns
`test_foam_trigger_drop.py:126` red (`f'Trigger gauge {n} was dropped' in h.msgs[0]`), a Part A (A5,
`cf7e520`) pin that is not in the plan's pin table (the plan's line numbers were read before A5 landed),
so by the batch's stop rule that line stays and its two listed pins (`test_trigger_numbering` :110,
:181) were not edited.
- Files: `services/validation.py`, `solvers/hooks.py`, `solvers/solver2d.py`, `solvers/solver3d.py`,
  `solvers/foam/backend.py`; pins `test_trigger_numbering` :134, :157-158, `test_bc_trigger` :197,
  :231, :323, `test_foam_live_due` :69, :197, `test_ui_setup_tree` :474.
- (1) PASS - the four suites exit 0 with the listed edits (all but the dropped line's two).
  (2) FAIL, one hit - `rg "[Tt]rigger gauge \{|reaches gauge" blastlab/services blastlab/solvers` finds
  only `hooks.py:84` (the held line). (3) PASS - `test_regression.py` byte-identical (run after B5).

### B1 - GUI-16 (a): a dropped trigger is disabled in Checks - DONE - `301608d`
The note on what the trigger does moved from `_validate_trigger` into `_validate_closing`, after `gone`
is known, through a new `_trigger_note(case)` (same tests, same words); said only when the trigger gauge
is kept. New pure `trigger_disabled(case, rule=None)`: the entered number when the gauge is outside the
domain or `drop_rule` names a wall, else None.
- Files: `services/validation.py`; checks `test_case_validate.trigger_drop_checks`.
- (1) PASS - native and blastFoam, trigger on dropped G2: one `Trigger disabled` warning naming G2 and
  no note naming the trigger; on kept G3: `The run ends when the wave reaches G3`; a remap trigger on a
  kept G1 keeps its note. (2) PASS - `trigger_disabled` 2 / None (and 4 for a trigger outside the
  domain). (3) PASS - `test_char_validation.py` exit 0, unedited.

### B6 - G13U sec. 6: a `drop_rule` that cannot run says so - DONE - `2d27de3`
The rule carries `failed`: '' when it works (no obstacles included), else `<step> stopped: <first
error>` (cell size / solver, domain / charge, refinement plan) or `<Exception>: <text>`; it still keeps
every gauge then (D14: an attribute, not an exception).
- Files: `services/validation.py`; checks `test_case_validate.drop_rule_failed_checks`.
- PASS - a 3D AMR case whose display grid `plan_levels` refuses: `the refinement plan stopped: AMR
  display grid of ~16,777,216,000 cells is too large ...`; a negative charge names `Charge must be > 0`;
  valid 2D native and blastFoam cases with a wall give '' and Wall 1; `test_case_validate` and
  `test_char_validation` exit 0.

### B11 - `_validate_det_radii` reports an unchecked case - DONE - `8de8ede`
An arithmetic / value / type / index error in the base-cell layout no longer returns in silence: one
warning `Ignition radii not checked - the cell layout could not be computed (<error>). The run still
refuses a radius that reaches no cell centre before blastFoam starts`; an error in one point's level
names that point (`Detonation point 1: ignition radius not checked ...`) and the other points are still
checked. A warning, not an error (the backend refuses on the real centres before blastFoam starts).
- Files: `services/validation.py`; checks in `test_case_validate.det_radius_reach_checks`.
- PASS - `_faces_shared` forced to raise: one "Ignition radii not checked" warning naming the error, no
  refusal; `refine.level_at` raising for point 1 of a static-zone case: point 1 named unchecked, point 2
  still refused; a checked case says nothing. `test_case_validate`, `test_char_validation`,
  `test_foam_ignition` exit 0.

### B7 - G15Q-5b: a user stop is not "it raised" - DONE - `4cd18ad`
`release_decision(..., stopped=False)` names `the run was stopped before it finished` first;
`verify_and_release_scratch(..., stopped=False)` passes it and logs it as a note; `stage_solve` passes
`stopped=isinstance(err, StoppedBeforeStart)` (a Stop during blockMesh raises it).
- Files: `services/model_folder.py`; check `test_model_folder.test_d_user_stop_is_not_a_raise`.
- PASS - `release_decision(True, False, v, stopped=True)` -> `(False, 'the run was stopped before it
  finished')`; a stage ending in StoppedBeforeStart reaches the release with `stopped=True`, a
  RuntimeError with False; the manifest's `kept_because` reads the stop. The `:1074-1083` decision-table
  pins pass unedited.

### B9 - P2-17, services half: a run knows its model - DONE - `2419eb0`
`model_of_run(runs_dir, posix)`: the stage folder (a model, or a chain's `1d`/`2d`/`3d`) whose
manifest records `posix` as `wsl_scratch.posix`, else None; the newest manifest (file time) wins.
- Files: `services/model_folder.py`; checks `test_f_model_of_run`,
  `test_f_resume_rewrites_the_original_manifest`.
- PASS - found / None / two models (newest wins, both ways) / a chain stage / unreadable manifests
  skipped; a resume run through `jobs.resume_stage(..., stage_dir=model_of_run(...))` with a fake
  scratch rewrites the original manifest's `wsl_scratch` (deleted, no `kept_because`).
  `test_model_folder` exit 0.

### B10 - P2-25, services half: a model folder loads back into a Result - DONE - `c6b1e02`
`output/gauges.read_gauges(path)` reads any `save_gauges_1d/2d/3d` file back, extras included.
`model_folder.load_result(stage_dir)`: MODEL.json + manifest (dim, stop reason) + gauge TSV; meta with
the case's charge, domain, obstacles, entered gauges, `model_dir`, `loaded_from`, and `gauges_dropped`
recomputed by the drop rules; a field from `profile.txt` / `profile_2d.npz`, else for blastFoam the
`foam\0\p` copy on the display grid (the foam\ copy keeps no written time, so that is the initial
field). No MODEL.json: ValueError naming the folder.
- Files: `output/gauges.py`, `services/model_folder.py`; new `tests/test_model_load.py`.
- (1) PASS - 1D/2D/3D round trips equal to the written precision (values rel 5e-7, points 3 decimals,
  radii 4), a one-row file. (2) PASS - a native 2D run with G2 inside a wall, written by `write_all`:
  same G numbers [1, 3], `gauges_dropped` `[[2, 'inside Wall 1']]`, peaks within rel 5e-7, the end
  field equal to `final_state['p']`; a 1D run likewise. (3) PASS - the ValueError; plus the foam\ field.

### B3 - GUI-16 (b): 1D exports keep the entered numbers - DONE - `0667564`
`numbers=None` on `plots.figure_gauges_1d` (+ `drop_note=None`, the passed note else one `G2 dropped by
the solver` line per gap), `gauge_summary.gauge_labels` / `summarize_gauges`, `report.kb_rows` /
`save_html_report`, `services/exports` (`png_figures`, `report_figures`, `summary_rows(res, opts)`,
`run_export`'s `gauge_numbers`). Pure `gauge_summary.numbers_1d(n_series, dropped)` is now the rule of
`ui/results_gauges.labels_and_dropped`; Qt feeds `opts['gauge_numbers']` from the new
`results_gauges.export_numbers` for pngs / report / summary; `export_drop_note` serves dim 1.
- Files: `output/plots.py`, `output/gauge_summary.py`, `output/report.py`, `services/exports.py`,
  `ui/exports.py`, `ui/results_gauges.py`; new `tests/test_export_numbers_1d.py`.
- (1) PASS - panel titles `Gauge 1`, `Gauge 3`, footnote names G2, rows G1/G3, the HTML tables name G3
  and not G2, the CSV via `run_export`; `numbers=None` gives today's titles and labels exactly.
  (2) PASS - `test_char_exports`, `test_gui_char_exports`, `test_ui_char_results_exports`,
  `test_char_summary` exit 0 unedited.

### B4 - one arrow, 3 decimals, ` m` after the cell, a footnote per line - DONE - `690ae45`
`gauge_labels` writes `→` (`ARROW`); `save_gauge_summary` writes `->` (`CSV_ARROW`) so the CSV stays
ASCII (Q4). The drop-case panel title is `G4 (2.010, 0.880) m → cell (2.025, 0.875) m`; the figure's own
footnote is one `G2 dropped by the solver` line per gauge (D11); `export_drop_note` hands Qt's note one
per line.
- Files: `output/gauge_summary.py`, `output/plots.py`, `ui/results_gauges.py`; pins
  `test_plots_gauge_titles` :73-75, :85 and `test_gauge_summary` :95, :109-123, :156-157 as listed;
  the 8 listed `char_golden` files re-recorded with `--update`.
- (1) PASS - scratch `check_b4_goldens.py` over `git diff -U0 0667564 690ae45 -- char_golden`: **49
  arrow lines** in the 8 files, each differing only by `->`/`-&gt;` -> `\u2192` (the goldens are ASCII
  JSON), every number unchanged. **Plus 212 `"gauges": "ok <hash>"` lines** in `gui_results_meta.json`
  (102) and `ui_results_meta.json` (110): short hashes of the Results gauge view, whose rows carry the
  label. Proved arrow-only: scratch `arrow_only.py` forces `ARROW = '->'` and runs each of the six char
  tests against the goldens of `HEAD~1` - all six reproduce them byte for byte. (2) PASS - both pin
  suites exit 0; new checks: a 5-drop footnote has 5 lines and its window extent lies inside the
  figure; the CSV keeps `->` and is ASCII. (3) PASS - all 22 `test_char_*` / `test_gui_char_*` /
  `test_ui_char_*` exit 0.

### B5 - GUI-16 (f): a dropped gauge drawn the same way on every field plot - DONE - `7918ede`
`plots.add_gauge_markers(..., dropped=None)`: hollow `x` + `G<n>` at the entered point, warn orange
(`GAUGE_DROPPED_COLOR = '#ff922b'`), never starred, after today's artists. `write_animation(...,
dropped=None)` draws the caller's entered numbers as dropped; `services/exports.dropped_gauges(res)`
supplies them for the GIF (stamp, else pairing). Live info gains `gauges_dropped` (native 2D/3D;
blastFoam 1D/2D/3D, whose `gauges` now lists only the writer's kept gauges: new
`backend._split_gauges` / `_live_gauges` on `spec.gauge_ids`).
- Files: `output/plots.py`, `output/animation.py`, `services/exports.py`, `solvers/solver2d.py`,
  `solvers/solver3d.py`, `solvers/foam/backend.py`; checks in `test_bc_trigger` (T53 section) and
  `test_trigger_numbering`.
- (1) PASS - one dropped gauge adds 2 artists (`x` at the entered point, `G3` unstarred even as the
  trigger, the orange); `dropped=None` / `[]` give artists equal to today's (count, positions, marker,
  size, colours, widths, text, weight). (2) PASS - native 2D: `gauges` G1 G3 G4, `gauges_dropped`
  `[(2, 1.4, 0.3)]`; native 3D `[(2, 0.8, 0.6)]`; a written blastFoam spec gives the same split.
  (3) PASS - `test_regression.py` byte-identical (run on this commit's tree); `test_char_exports`
  unedited, green.

### B8 - G15U-L2: the blastFoam log names each dropped gauge - DONE - `fe2abd9`
`backend._log_dropped_gauges`, called next to the banner in `solve_1d_foam` / `solve_2d_foam` /
`solve_3d_foam`: one `[warn] G2 (1.40, 0.30) m inside Wall 1 - dropped` per gauge the writer left out,
the native wording (`within a cell of Wall n`, `outside the domain`, 1D `G2 (r 9.00 m) outside the
domain - dropped`). Cites blastFoam User Guide v6.0, sec. 15.
- Files: `solvers/foam/backend.py`; checks `test_foam_trigger_drop.drop_log_checks` /
  `drop_log_1d_checks`.
- PASS - written 2D and 3D specs: lines for G2 (`inside Wall 1`), G3 and G4 (`within a cell of Wall 1`),
  none when nothing is dropped, `outside the domain` for a far gauge, the 1D line; `test_foam_writer`
  exit 0; `foam_golden/` untouched (`git status` clean there).

## Closing matrix

- `gate.py --changed 934028f --deep` (on `fe2abd9`): **114/114 green, 25.9 min**, the Tk suites
  included (16 `test_gui_*`, the 9 of CLAUDE.md sec. 9 among them). WSL solve suites not run.
- `test_regression.py` last, on `fe2abd9`: **REGRESSION: PASS**, every file byte-identical.
- App start: `MainWindow` on private settings, shown and quit (scratch `app_start.py`): `APP START: OK`,
  visible, title `untitled · BlastLab`. Cleanup dry run before it: `False`.
- `foam_golden/`, `baseline/`, `foam_fixtures/`: no change in `git diff 934028f -- ...`.

## Files touched

`blastlab/services/validation.py`, `services/model_folder.py`, `services/exports.py`,
`output/plots.py`, `output/gauge_summary.py`, `output/report.py`, `output/animation.py`,
`output/gauges.py`, `solvers/hooks.py`, `solvers/solver2d.py`, `solvers/solver3d.py`,
`solvers/foam/backend.py`, `ui/exports.py`, `ui/results_gauges.py`; tests `test_case_validate.py`,
`test_model_folder.py`, `test_trigger_numbering.py`, `test_bc_trigger.py`, `test_foam_live_due.py`,
`test_ui_setup_tree.py`, `test_gauge_summary.py`, `test_plots_gauge_titles.py`,
`test_foam_trigger_drop.py`, new `test_model_load.py`, new `test_export_numbers_1d.py`; 8
`char_golden/*.json` (B4).

## GUI screens touched (for QA)

- Setup / Checks: trigger notes and messages (B1, B2); a new warning for unchecked ignition radii (B11).
- Results > Gauges and every export: `→` labels and table rows; drop-case titles at 3 decimals with
  ` m`; footnote one line per gauge; 1D exports numbered by entered gauge (B3, B4). Tk shares the
  builders (labels, footnote words).
- Run log: `G3` trigger lines; the blastFoam `[warn] ... - dropped` lines (B2, B8).
- Animation / GIF export: dropped gauges as an orange `x` (B5). The live panes do not yet draw
  `gauges_dropped` (Qt C-task / Tk E-task); blastFoam's live `gauges` no longer lists a dropped gauge.

## Numerical changes

None. Labels, titles and log text only; `test_regression` byte-identical; the char goldens' 49 arrow
lines keep every number.

## Engineering issues noticed

- A 2D blastFoam AMR case at 8 levels and display level 8 (4 m, 0.05 m base) did not return from
  `validate_case` within 2 min in a scratch probe (killed by PID); 3D cases of that kind are refused at
  once by `plan_levels`. Not investigated (out of Part B); worth a look in the AMR caps.
- `hooks.trigger_index`'s dropped line still reads `Trigger gauge 2` (B2 above).

## Open questions for the owner

1. **B2's held line.** Approve the text-only edit of `test_foam_trigger_drop.py:126` (A5's pin,
   `Trigger gauge {n} was dropped` -> `Trigger gauge G{n} was dropped`) so `hooks.trigger_index` can
   say `Trigger gauge G2 was dropped - trigger disabled`, with the two listed pins
   (`test_trigger_numbering` :110, :181)? **Recommended: yes** - the same owner-3 wording edit as the
   rest of B2; the planner could not list a pin that landed after the plan was read. Then B2's
   criterion 2 passes.
2. **B4's 212 hash lines.** The plan counted 49 golden lines; the two Results-meta goldens also hold
   short hashes of the gauge view, which moved with the arrow (proved by reproducing the old goldens
   with `->`). **Recommended: accept** as part of the approved re-record of those two files.
