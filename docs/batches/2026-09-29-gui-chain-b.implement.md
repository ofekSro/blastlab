# Implementer report — batch 2026-09-29-gui-chain, part 9b (GUI-9b)

- Plan: [`2026-09-29-gui-chain.md`](2026-09-29-gui-chain.md), T4-T6.
- Branch `gui-redesign`, from HEAD `772c542` (9a done and verified:
  [`…-a.implement.md`](2026-09-29-gui-chain-a.implement.md),
  [`…-a.verify.md`](2026-09-29-gui-chain-a.verify.md)).
- Measurements and screenshots: [`measurements.md`](../qa/2026-09-29-gui-chain/measurements.md)
  (the strip and the tabs against the boards, contrast),
  [`measurements-9b.md`](../qa/2026-09-29-gui-chain/measurements-9b.md)
  (the embedded viewer: the pre-registered rules, then the results),
  `measure-9b.json`, `viewer_measure_9b.json`, 36 + 4 `gui9b-*.png`,
  7 `e2e9b_*.png`.

## The gates

- **Numbers.** No number, default, case key, file format, hand-off file,
  export byte or solver changed. `test_regression.py` byte-green at the
  start, in the T5 re-run, in the T6 matrix and at the end. S8 proves the
  export bytes of a chain stage equal a plain entry's (summary, tsv,
  fieldcsv, profile, report by `describe_dir`; the e2e's Summary .csv by
  sha256).
- **What a chain launches.** `test_ui_char_chain_wiring` (T0's golden)
  PASS at the start, after T4, after T5 and in the T6 matrix.
- **Frozen modules.** `git diff --stat 772c542..HEAD` over `core/`,
  `services/`, `models/`, `solvers/`, `output/`, `viz3d/`, `gui/` (Tk),
  `ui/view3d_host.py`, `ui/run_controller.py` and the three fixture folders
  is empty, so the Tk suites were not triggered. `run_panel.py` got only
  `set_chain_strip`'s shrink-ahead and its `_shrink_viewer` helper.
- **Committed tests.** Only the plan §9 pins changed (listed under T5);
  every behaviour and number assertion holds. `test_ui_char_write_failure`
  found a real conflict in T6; the code was changed, not the test (D161).
- **Imports.** No VTK or pyplot in the GUI process (`test_ui_no_vtk_in_main`,
  `test_ui_no_mpl_pyplot`, S-suite's last check). No new `QShortcut`
  (`test_ui_frame` F5 five). No new timer, no polling.
- **App launch.** `python -m blastlab`, throwaway settings, 20 s, stderr
  empty, after T4 (offscreen) and at the end (real platform), stopped by its
  own `Popen` handle; `auto_cleanup` still `False` after.
- **Session safety.** §8.2 dry run first: `<repo>\settings.json False []`.
  Every MainWindow on throwaway settings (`ensure_qapp()` /
  `private_settings()`, the e2e's and the sampler's own files, the
  harness's own). `use_model()` for every real run.
- **Process hygiene.** No `python` process at the start (no foreign PIDs).
  Mine: the suites, the launch probes (PIDs 24656 and 4196, by handle), the samplers (each stopped its own viewer child by handle; all
  reported "closed with the window"), the harness runs, the shot scripts.
  None left at the end. One scratch script lacked the `__main__` guard on its
  first run and the viewer child (multiprocessing spawn) re-ran it; it
  exited with the window, nothing was left, and the re-run had the guard
  (CLAUDE.md §8.7 names this trap).
- **Worktree.** `impl9b_base_wt` at `4b28007` for the F13 A/B, removed;
  `git worktree remove` left its record ("Permission denied", F20's
  mechanism), deleted a moment later. `git worktree list`: the main tree
  only. (`.git/worktrees/gui6a_base_wt` is F20's, not mine.)
- **Memory.** 0.5-1.7 GB free physical, 12.6-14.8 GB free commit. Heavy
  suites one at a time; no `MemoryError`.
- **Never staged:** the six foreign paths. Every commit staged by explicit
  path, its message in a new `impl9b_msg_NN_*.txt`, `git commit -F`.

## Commits (`772c542..`)

| Commit | Task | What |
|---|---|---|
| `eeb466c` | T4 | `ui/chain_strip.py`, the strip in 02 Run, S7 |
| `04c27c8` | T5 | one Results entry with STAGE tabs, S8, C11, X4, C4; also the strip's `set_pct` dedupe fix and the light running edge (T4 code, found by the 9b e2e and the contrast script) |
| `771a00e` | T6 | the sampler's chain actions + **the pre-registered rules** (`measurements-9b.md`) + the 9b e2e, committed before any sampled run |
| `5ebd616` | T6 fix | the strip's pills fit 1100 × 720 with minutes-long stages (D164) |
| `bc25323` | T6 fix | only a chain with a model becomes one entry (D161) |
| (this) | T6 | report, measurements, screenshots, decisions D155 closed, D157-D168, F25-F26 |

---

## T4 · 02 Run: the chain strip · DONE · `eeb466c` (+ fixes in `04c27c8`, `5ebd616`)

- New `blastlab/ui/chain_strip.py`: `ChainStrip` (`CHAIN · <model>` in
  `accent_text`, one `StagePill` per stage joined by painted arrows, a
  right caption) with `set_chain`, `stage_started`, `set_pct`,
  `stage_done`, `finish(how, seconds)`, `texts()`. Pills: done `ok_bg` +
  `✓ 9 s`; running tint + accent edge + `78 %`; waiting / not run `faint`;
  stopped `warn`; failed `danger`. One row (50 px) or two (74 px), decided
  on a resize only from the widest value each pill can take, so a stage
  change never moves the strip (or the viewer below it).
- `run_panel.set_chain_strip`: shrinks the on-screen viewer ahead by the
  strip's height + GAP (D93's pattern). Nothing else in `run_panel.py`.
- `app.py`, from the existing callbacks only: `on_running` (a fresh strip
  for > 1 stage, arranged for the centre's width before insertion; none
  for a single run), `on_run_started`, `on_progress`, `on_result`
  (`stage_s()`, D50 / D59), `on_finished`; an HD 1.3 start empties the slot
  (D166). `run_controller.py` untouched. Title and Stop question unchanged.
- Found later and fixed: the strip's `set_pct` sat behind the title's
  whole-percent dedupe, so a stage 2 whose first percent equalled stage 1's
  last (100 %) stayed `0 %` (the 9b e2e); the light running edge was 2.72:1
  (D165); three minutes-long done pills did not fit 1100 × 720 (D164).

Tests: `test_ui_chain_screen` S7. Run: `cd blastlab/tests && python
test_ui_chain_screen.py` → `UI CHAIN SCREEN: PASS (185 checks)`.

| Criterion (S7, offscreen, fake `RunClock.now`) | Result |
|---|---|
| After stage 1 starts: `01 1D 0 %`, `02 2D waiting`, `03 3D waiting` | PASS (both sizes) |
| Stage 1's result at a fake 9 s, stage 2 at 78 %: `01 1D ✓ 9 s`, `02 2D 78 %`, `03 3D waiting`, caption `Stage 2 of 3 · the 3D stage starts from handoff_2d_to_3d.npz` | PASS |
| After the end: three ✓ pills and `Chain done in …` (`Chain done in 40 s`) | PASS |
| Title `Chain 2/3 · 78 % · ` meanwhile (F6's format) | PASS |
| A stop in stage 2: `02 2D stopped`, `03 3D not run`, `Chain stopped at stage 2 of 3`; an error: `failed` | PASS |
| A single run: `chain_slot` hidden at 0 px (R7 holds) | PASS (and R7 itself green) |
| The strip's height equal across every state change at 1100 × 720 and 1600 × 1000 | PASS (74 ×5, 50 ×5) |
| `set_chain_strip(strip)` with the 3D view on screen calls `shrink_ahead` once with height + spacing; not with the view elsewhere | PASS (`[58]` = 50 + 8; `[]` on the live slice) |
| At 432 px nothing clipped; the caption elides with a tooltip | PASS (`clipped(win)` empty; real platform: caption elided mid-run, tooltip whole) |
| Extra: 20-min stages at 1100 × 720 fit (`9 s`, `20 min`, `21 min`, nothing elided, tooltips whole), whole again at 1600 | PASS |
| Extra: stage 2 starting at stage 1's last percent shows it | PASS |

## T5 · 03 Results: a chain is one entry with STAGE tabs · DONE · `04c27c8` (+ `bc25323`)

- `results_panel.py`: `ChainEntry(ResultEntry)` (kind `chain`, label =
  model, `route`, `stages` = plain `ResultEntry`s with today's labels,
  `index`; `dim` / `result` are the selected stage's); `start_chain`,
  `add_stage`; `current()` = the selected stage's own entry; `stage()`,
  `select_stage(dim)`; the one `StageTabs` instance through
  `set_stage_strip` while a chain is selected (never re-shown between two
  chains); Remove takes the whole chain; labels uniquified across entries
  and stages; the Remove tooltip names the row.
- New `results_stages.py` (`StageTabs`), `results_method.chain_caption`,
  `results_list` (the caption call only), the QSS.
- `app.on_result`: a live chain **with a model** groups (D161); a result fed
  by hand, or a chain with no model (scripts only), stays per stage.
  `_results` per stage.
- D155 is closed: the last stage's `… as one result with a tab per stage`
  is now true.

Tests: S8 (`test_ui_chain_screen`), `test_ui_chain` C11 addition.

| Criterion | Result |
|---|---|
| S8: a 3-stage chain by the handlers: `len(entries()) == 1`, kind chain, stage labels `M - 1D/2D/3D`, `win._results` three, tabs `1D \| 2D \| 3D` with 3D selected, `entries()[0].dim == 3`, the caption by the rule | PASS (`1D → 2D → 3D · 3 stages · 41 min 0 s`; mid-run `… · 1 of 3 stages · 9 s`) |
| `select_stage(2)` → `current().label == 'M - 2D'`; its Field image equals a plain entry's of the same Result | PASS (same title, `np.array_equal` of the map) |
| Exports `summary`, `tsv`, `fieldcsv`, `profile`, `report` from the chain stage = `add_result('M - 2D', 2, same)` by `describe_dir` | PASS (5 of 5; real Phase 0 2D result) |
| Two chains of one model: `M`, `M #2`; stages `M - 2D #2`; its 2D Field its own data | PASS |
| A plain result after a chain: `stage_slot` hidden at 0 px; Remove of a chain removes one row | PASS (`Removed result: M #2`) |
| C11: one chain entry, stages `[1, 2]`, `CHAIN_RUN - 1D`, `CHAIN_RUN - 2D` | PASS (`test_ui_chain` 114) |
| `test_ui_results_screen`, `test_ui_results`, `test_ui_char_results_exports`, `test_ui_char_results_meta`, `test_char_exports` green and unchanged | PASS (186 / 130 / PASS / PASS / PASS) |

**Committed assertions changed (plan §9, the per-stage entries the owner
replaced):**

- `_e2e_ui_chain.py` X4: `two entries` (`len(entries) == 2`) and `one per
  dimension` (`sorted(e.dim …) == [1, 2]`) → `one chain entry` (`len == 1`,
  kind chain) and `with two stages, one per dimension` (`[s.dim …] == [1,
  2]`); `{d}D draws in Fields` per entry → `stage {d}D draws in Field` per
  stage tab (`current() is` the stage and the page `image`/`figure`).
- `_e2e_ui_chain_foam.py` C4: `three entries in the picker` / `one per
  dimension` → `one chain entry in the picker` / `with three stages, one per
  dimension`, plus `stage {d}D draws in Field`; the time-continuity checks
  now iterate the chain's stages and assert exactly what they asserted.
- `test_ui_chain` C11: one check added (no change).
- `test_ui_char_write_failure` is **unchanged**: T5 first grouped its
  nameless chain into `Run 2` (pinned `Run 2 - 1D`, shared with the Tk
  suite); the code now groups only a chain with a model (D161).

## T6 · 9b verification · DONE · `771a00e`, `5ebd616`, `bc25323`, this commit

**Plan §10, all four:**

1. *Four routes wire the right hand-offs*: C13 / S1 / S3 and T0's golden,
   green in the matrix.
2. *Per-stage live validation*: S5 green; the e2e sees card 2 go `● 1
   error` after a typed bad Lx and back.
3. *Copy from Setup and Load case fill the stage*: S6 green; the e2e does
   both through the buttons.
4. *A native 1D → 2D chain runs from the new screen and shows as one result
   with stage tabs*: `_e2e_ui_chain_screen.py`, **real platform**: route
   clicked, Load case… and Copy clicked, `● case OK`, `● 1 error` and back,
   **Run chain clicked**, finished in 2.6 s; the strip sampled at every
   progress message and pump (51 samples) passed through `02 2D NN %` with
   `01 1D ✓ 1 s` before it, the title through `Chain 2/2 · `, the end
   `01 1D ✓ 1 s`, `02 2D ✓ 2 s`, `Chain done in 3 s`; Results: one entry,
   kind chain, badge shown, tabs `1D | 2D`, each tab's Field draws
   (`figure`, `image`); the 2D Summary .csv sha256 equals a plain entry's;
   the model folder is C11's layout; nothing raised. `E2E UI CHAIN
   SCREEN: PASS (23 checks)` (also offscreen). Shots `e2e9b_*.png`.

**Screenshots** (real platform, dark and light, 1100 × 720 and 1600 ×
1000): the Chain screen re-shot at HEAD (4 scenes), 02 Run with stage 2
running and after the end, 03 Results on each STAGE tab: 36 scenes,
`clipped(win)` empty in all; numbers in `measure-9b.json`; contrast of 22
new pairs by script, all ≥ 4.5 (graphics ≥ 3) after D165. **A chain with a
3D stage in the 3D view** (free commit 12.6 GB ≥ 2): the C12 cases run as a
real native 1 → 3 chain from the window (10.2 s; strip `01 1D ✓ 1 s`,
`02 3D ✓ 9 s`, `Chain done in 10 s`; one entry `CHAIN13_SHOT` with stages
1D / 3D), its 3D stage opened in the embedded viewer, screen-grabbed in both
modes and sizes (`gui9b-*-results-chain13-3d-viewer.png`).

**Embedded 3D viewer, the committed sampler** (`_e2e_ui_viewer_place.py`,
new actions `chainsel`, `stagetabs`, `chainstrip`, `chaintab`,
`chainresize`, `stripresize`; rules committed in `771a00e` before any run):

| Rule | Action | Result | Verdict |
|---|---|---|---|
| R-VIEWER | results `stage` / `tabs` / `theme` | 0 ms over 2109 / 1050 / 12263 samples with a window | PASS |
| R-VIEWER | results `chainsel` / `stagetabs` (new) | 0 ms over 2276 / 2337 | PASS |
| R-VIEWER | run `tabs` / `theme` | 0 ms over 1047 / 12157 | PASS |
| R-VIEWER | run `chainstrip` (new) | 0 ms over 3175 | PASS |
| R-VIEWER | setup `chaintab` (new) | 0 ms over 1046 | PASS |
| R-VIEWER-RESIZE (F13) | results `chainresize` vs base `resize` | median 23.5 ms (4.0, 25.2, 23.5) vs base 27.6 (27.9, 27.6, 26.1); limit 32.6 | PASS |
| R-VIEWER-RESIZE (F13) | run `stripresize` vs base `resize` | median 27.5 ms (45.2, 27.5, 25.7) vs base 26.5 (25.4, 26.5, 44.8); limit 31.5 | PASS |

Neither F13 result is over its rule, so the A/B with the widget hidden was
not required; the same runs measured plain `resize` at HEAD too (results
median 21.6 with the chain still selected; run median 45.1, per repeat
45.4 / 26.0 / 45.1). The run surface is bimodal (≈ 26 or ≈ 45 ms) at HEAD and
at base alike (base's own longest 44.8): F13's known 22-49 ms shape. Worst
offsets 472 / 476 px, the same at base. F13 stays open; `view3d_host.py`
was not edited. Every self-test saw the displaced window (148-149 ms, 60
px). `viewer_measure_9b.json` holds all five runs.

**Harness** (offscreen, own settings, `PYTHONIOENCODING=utf-8`; the truth is
each run's `findings.jsonl` under `~\blastlab_qa\gui9b-20261003-*`):

| Run | Findings |
|---|---|
| `S00,B01,B02,B04,B07,G01,G03,M04,H03,D01,D02,E01,E03` | 2: H03 S2 `no result labelled 'QA native3d' to select` (H03 needs D03's cached result; not in this list; 9a had this and the native2d one, which D02 now provides); G01 S3 qt-message `QFontEngineFT: Failed to create FreeType font engine` (F26: G01 alone, twice, gives none) |
| `G02` alone | none: the native 1 → 2 → 3 chain started, stages 2 and 3 started, finished in 12 s wall; results `['QA_CHAIN']` (one chain entry); the model folder's 3 stage folders, 2 hand-offs and root manifest; `chain3d` cached (dim 3 through the chain entry) |
| `B06 --window` | none (F10: F5 starts, plain Esc does not stop, Shift+Esc stops) |

Against GUI-9a's run of the first nine scenarios: S00, B01, B02, B04, B07,
G01 (apart from F26), M04 the same (none); **G03 now passes** (9a's F22 race
did not fire with D01/D02/E01/E03 in between; F22 stays open for the
harness); H03 one finding instead of two.

**The fast matrix**, one suite at a time (from `blastlab/tests`, at
`5ebd616`; the suites touched by `bc25323` re-run after it):

| Suite | Result |
|---|---|
| test_ui_chain_screen | PASS (184; 185 after `bc25323`) |
| test_ui_chain | PASS (114) |
| test_ui_char_chain_wiring | PASS |
| test_ui_parity | PASS (41) |
| test_ui_frame | PASS (50) |
| test_ui_setup_form | PASS |
| test_ui_setup_tree | PASS (238) |
| test_ui_setup_strip | PASS (110) |
| test_ui_char_case_form | PASS |
| test_ui_components | PASS |
| test_ui_theme | PASS |
| test_ui_run_screen | PASS (168) |
| test_ui_run_panel | PASS |
| test_ui_results_screen | PASS (186) |
| test_ui_results | PASS (130) |
| test_ui_three_surfaces | PASS (35) |
| test_ui_drain | PASS |
| test_ui_view3d_host | PASS |
| test_ui_fieldform_viewport | PASS (11) |
| test_ui_no_vtk_in_main | PASS |
| test_ui_no_mpl_pyplot | PASS (19) |
| test_ui_crashlog | PASS |
| test_model_folder | PASS |
| test_case_validate | PASS |
| test_foam_writer | PASS |
| test_ui_live_gauges | PASS (20) |
| test_ui_char_results_exports | PASS |
| test_ui_char_results_meta | PASS |
| test_char_exports | PASS |
| test_ui_char_hd13_run | PASS |
| test_ui_char_write_failure | **FAIL** at `5ebd616` (`chain_profile`), PASS after `bc25323` |
| test_ui_results_vtk_folder | PASS |
| test_gauge_summary | PASS |
| test_report | PASS |
| test_anim_scale | PASS (68) |
| test_out1_qa_polish | PASS |
| _e2e_ui_chain | PASS (16) |
| _e2e_ui_chain_foam | **not completed** (pgrep empty first): the 3D blastFoam stage did not finish inside the script's own 1800 s chain limit on this PC (4-core, 5 GB WSL VM; the office machine ran the whole chain in 614 s, `docs/history/ui-migration.md`). 25 of 31 checks PASS, among them 9b's C4 `one chain entry in the picker` (`CHAIN_FOAM`, kind chain), `stage 1D / 2D draws in Field`, and stage 2's start at 4.95895e-05 s = stage 1's profile time (the historical nine-digit match). The 6 failures all follow from the unfinished 3D stage (`it finished`, the root manifest, `three stages`, stage 3's start time, time order, 3d's SHA256SUMS). No solver left (`pgrep` empty after) |
| test_regression | PASS (byte), and again at the end |

---

## All files touched in 9b

- `blastlab/ui/chain_strip.py` (new), `results_stages.py` (new),
  `run_panel.py`, `results_panel.py`, `results_method.py`,
  `results_list.py`, `app.py`, `theme.py`.
- `blastlab/tests/test_ui_chain_screen.py` (S7, S8), `test_ui_chain.py`
  (C11 addition), `_e2e_ui_chain.py` (X4), `_e2e_ui_chain_foam.py` (C4),
  `_e2e_ui_chain_screen.py` (the 9b form), `_e2e_ui_viewer_place.py` (new
  actions).
- `docs/gui-redesign-decisions.md` (D155 closed, D157-D168, F25-F26),
  `docs/qa/2026-09-29-gui-chain/` (measurements.md, measurements-9b.md,
  measure-9b.json, viewer_measure_9b.json, 40 `gui9b-*.png`, 7
  `e2e9b_*.png`), this report.

## GUI screens touched

- **02 Run**: the chain strip at the top of the centre (one / two rows,
  every state), and the viewer below it.
- **03 Results**: the chain's one list row (badges, caption), the STAGE
  tabs above the view tabs, every view and export of each stage, Remove.
- Chain and Setup: unchanged in 9b (the Chain screen re-shot only).

## Numerical changes

None.

## Decisions and findings added

- **D155 closed** (its row: outcome `04c27c8`).
- D157-D163: the plan's 9b defaults 17-23, as built. **D161 amends row
  21**: only a chain with a model groups.
- D164-D168 new: the strip's narrow fit; its look (panel card, light
  running edge); an HD 1.3 start empties it; how an unfinished chain reads;
  the sampler's F13 action names.
- F25: the title / progress tile keep the previous stage's percent at a
  stage start (pre-existing, GUI-6). F26: one transient offscreen FreeType
  message in G01.

## Suspected engineering issues (not changed)

None in the numerics.

## Left undone / for later

- **`_e2e_ui_chain_foam.py` did not complete here** (its 3D blastFoam stage
  outlived the script's 1800 s limit on the home PC's 4-core WSL VM; see the
  matrix). Its 9b checks that could run passed. It needs a run on the office
  machine (614 s there before). Two WSL scratch folders of today's runs are
  mine and were kept by the app's own rule (a stopped / unfinished run keeps
  its scratch): `/root/blastlab_runs/20261003-150702_3d_p3288-02` (this
  e2e's 3D stage) and `/root/blastlab_runs/20261003-144701_2d_p22544-00`
  (harness B06's F5 run, stopped by Shift+Esc). Not deleted: the owner's
  cleanup decides.
- F13 (the viewer's resize lag, 22-49 ms) stays open: measured, within its
  pre-registered rule, not caused by 9b; `view3d_host.py` is GUI-10's or the
  small batch's.
- F22 (`wait_log` race), F24 (harness stdout), F25, F26: GUI-10.
- Owner: D161's amendment, D157 (strip in the centre column, not full
  width), D159 (tabs on their own row), D160 (`41 min 0 s`), D164, D165.
- Process note: one scratch file (the 3D-shot script's `__main__` wrapper)
  was generated with a heredoc'd Python one-liner rather than a script
  file; every repo file went through Edit / Write.
