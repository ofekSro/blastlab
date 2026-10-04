# Verification — batch 2026-09-29-gui-chain, part 9b (GUI-9b, T4-T6)

Plan: [`2026-09-29-gui-chain.md`](2026-09-29-gui-chain.md), T4-T6. Report
checked: [`2026-09-29-gui-chain-b.implement.md`](2026-09-29-gui-chain-b.implement.md)
(and 9a's [`-a.implement.md`](2026-09-29-gui-chain-a.implement.md) /
[`-a.verify.md`](2026-09-29-gui-chain-a.verify.md)). Range reviewed:
`772c542..8073a1c` (six commits), against 9a's end `772c542` and the batch
base `4b28007`. Branch `gui-redesign`. Verifier run: 2026-10-03, the 8 GB
home PC.

**Verdict: ready for QA.** Every T4-T6 criterion reproduces, offscreen and
on the real platform, except the blastFoam chain e2e, which this PC cannot
finish (left for the office machine, as the implementer reported). Review
found and fixed two defects in two commits (F25, the stale percent at a
chain stage's start; a chain removed while it runs coming back with its
removed stages). Added D169, D170 and F27.

## Ground rules kept

- CLAUDE.md §8.2 dry run first: `<repo>\settings.json False []`.
- No python process was running at the start (no foreign PIDs); none of
  mine was left at the end. Every sampler stopped its own viewer child ("closed
  with the window", PIDs 28744, 13064, 29092).
- Throwaway settings for every MainWindow: `ensure_qapp()` /
  `private_settings()` in the suites and my probe, the e2e's and the
  sampler's own files, the harness's own settings
  (`~\blastlab_qa\verify9b-20261003-*`).
- Heavy suites one at a time (a sequential runner; the harness, G02, the
  samplers and the e2e each alone). Free physical memory 1.3-1.7 GB, free
  commit 13-14 GB. No `MemoryError`.
- No WSL use: the blastFoam e2e was not re-run (instruction), nothing under
  `/root/blastlab_runs` touched. No worktree created (`git worktree list`:
  the main tree only).
- Never staged: `docs/references/INDEX.md`, the Viper manual files,
  `viper_vtk_sample/`, `docs/qa/2026-09-27-*`. Every commit staged by
  explicit path, its message in a new `verify9b_msg_NN_*.txt`, `git commit
  -F`. Not pushed.
- Every repo edit through Edit / Write (one scratch Python script wrote
  `viewer_measure_9b_verify.json`).
- **Frozen modules:** `git diff 4b28007..HEAD` on `ui/run_controller.py`
  and `ui/view3d_host.py` is **empty**; `git diff 772c542..HEAD` over
  `core/ services/ models/ solvers/ output/ viz3d/ gui/` (Tk), the three
  fixture folders and `char_golden/` is empty. The Tk gate does not trigger.

## Fixes made in review

| Commit | Task | What |
|---|---|---|
| `2f58395` | T4 (F25) | At a chain stage's start the title (`Chain 2/2 · 100 % · …`), the Run progress tile (`100 %`) and the Stop question (`… at 100 %?`) kept the previous stage's percent until the new stage's first progress. `MainWindow.on_run_started` clears `_run_pct` before the title is rebuilt; `RunPanel.on_run_started` resets the bar and the tile to `0 %` (what `set_running` does for a first stage). UI only, no frozen module. S7 gained a check; my probe failed all three on the code before (`Chain 2/2 · 100 % · untitled · BlastLab`, tile `100 %`, `Stop M (stage 2 of 2) at 100 %?`). D169; F25's outcome row. |
| `1a83437` | T5 | A chain removed in 03 Results while it still ran came back at the next stage with the stages the user removed: `MainWindow` kept the `ChainEntry` and `add_stage` re-appends an entry that is not in the list. The next stage now starts a new chain entry, as a per-stage entry did before 9b. S8 gained a check; the probe on the code before read `[('R', 'chain', ['R - 1D', 'R - 2D'])]`, after `[('R', ['R - 2D'])]`. D170. |
| (this) | T6 | This report; `measurements-9b.md` gains a "Verifier re-run" section **below** the Results (the pre-registered rules untouched); `viewer_measure_9b_verify.json`; `verify9b_e2e_run_stage2.png` (the post-F25 e2e shot); D169, D170, F25 outcome, F27 in the decisions file. |

## Per task

### T4 · 02 Run: the chain strip — FIXED (`2f58395`)

Checks: `test_ui_chain_screen` S7 (offscreen, fake `RunClock.now`), run by
me at `8073a1c` (185 checks, PASS) and after the fixes (187, PASS); my
probe (`scratchpad\probe_9b.py`) for lifetimes and edge cases.

| Criterion | Verdict | Check |
|---|---|---|
| After stage 1 starts: `01 1D 0 %`, `02 2D waiting`, `03 3D waiting` | PASS | S7 at both sizes: `['01 1D 0 %', '02 2D waiting', '03 3D waiting', 'Stage 1 of 3 · the 2D stage starts from handoff_1d_to_2d.txt']` |
| Stage 1 at a fake 9 s, stage 2 at 78 %: `01 1D ✓ 9 s`, `02 2D 78 %`, `03 3D waiting`, caption `Stage 2 of 3 · the 3D stage starts from handoff_2d_to_3d.npz` | PASS | S7, exact list compare |
| After the end: three ✓ and `Chain done in …` | PASS | S7: `Chain done in 40 s` |
| Title `Chain 2/3 · 78 % · ` meanwhile (F6) | PASS | S7 `Chain 2/3 · 78 % · untitled · BlastLab`; `test_ui_frame` F6 PASS (50) |
| A stop in stage 2: `02 2D stopped`, `03 3D not run`, `Chain stopped at stage 2 of 3`; an error `failed` | PASS | S7; my probe: an error in stage 2 → `['01 1D ✓ 0 s', '02 2D failed', '03 3D not run', 'Chain failed at stage 2 of 3']` |
| A single run: `chain_slot` hidden at 0 px (R7) | PASS | S7 (height 0); `test_ui_run_screen` PASS (168) |
| Strip height equal across every state at 1100 × 720 and 1600 × 1000 | PASS | S7 `[74 ×5]`, `[50 ×5]` |
| `set_chain_strip` with the 3D view on screen calls `shrink_ahead` once with height + spacing; not when the view is elsewhere | PASS | S7 spy `[58]` (50 + GAP 8), `[]` on the live slice, no second call for the same strip |
| At 432 px nothing clipped; caption elides with a tooltip | PASS | S7 `clipped(win)` empty, pills inside the strip, caption whole or tooltip = whole |
| `run_controller.py` not edited | PASS | `git diff 4b28007..HEAD` empty |
| Real platform: the strip during a real chain | PASS | my `_e2e_ui_chain_screen.py` run (below): 41 samples through `02 2D 0 %` with `01 1D ✓ 1 s` before it; end `01 1D ✓ 1 s`, `02 2D ✓ 1 s`, `Chain done in 3 s` |

Qt lifetime (my probe, offscreen): six chains in a row leave exactly one
`ChainStrip` and its two `_StripArrow`s alive (the old strips are
unparented and collected); four theme toggles afterwards raise nothing
(the arrows' `theme.signals.changed` connections die with them). Stop
between two stages reads `01 1D ✓`, `02 2D not run`, `Chain stopped at
stage 1 of 3` (D167's rule: no stage was running). F25 was real: fixed.

### T5 · 03 Results: a chain is one entry with STAGE tabs — FIXED (`1a83437`)

| Criterion | Verdict | Check |
|---|---|---|
| A 3-stage chain by the handlers: one entry, kind chain, stages `M - 1D/2D/3D`, `win._results` three, tabs `1D \| 2D \| 3D` with 3D selected, `entries()[0].dim == 3`, caption by the rule | PASS | S8: `[('M', 'chain')]`, `1D → 2D → 3D · 3 stages · 41 min 0 s` (mid-run `1 of 3 stages · 9 s`), slot 38 px |
| `select_stage(2)` → `current().label == 'M - 2D'`; its Field image equals a plain entry's | PASS | S8: same title, `np.array_equal` of the map |
| Exports summary / tsv / fieldcsv / profile / report of a chain stage = `add_result('M - 2D', 2, same)` by `describe_dir` | PASS | S8 (5 of 5). I read `describe_dir`: sha256 of every byte for csv/txt, per-array sha256 for npz, the HTML with only its timestamp and inlined PNG bytes normalised - a real byte comparison |
| Two chains of one model: `M`, `M #2`, `M - 2D #2`; the second chain's 2D Field its own data | PASS | S8 |
| A plain result after a chain: `stage_slot` hidden at 0 px; Remove of a chain removes one row | PASS | S8 (`Removed result: M #2`) |
| `test_ui_chain` C11: one chain entry, stages `[1, 2]`, `CHAIN_RUN - 1D`, `CHAIN_RUN - 2D` | PASS | `test_ui_chain` PASS (114) |
| `test_ui_results_screen`, `test_ui_results`, `test_ui_char_results_exports`, `test_ui_char_results_meta`, `test_char_exports` green and unchanged | PASS | matrix below; none of the five files is in the diff |
| Real platform: the 2D stage's Summary .csv equals a plain entry's (sha256) | PASS | my e2e: `5d311dd4…` both |

**D161 (only a chain with a model groups).** The ungrouped branch is the
old line verbatim (`self.results.add_result(label_, dim, res)`), taken for
a result outside a live run, a single run, and a chain whose controller
`_run_name` is empty (only `RunController.start_stages` called directly
can do that; `RunController._launch` labels it `Run N - 1D`). The Chain
screen refuses an empty Model box (C2b), so every user chain groups.
`test_ui_char_write_failure` PASS unchanged (its `chain_profile` pins
`['Run 2 - 1D']`); its expectation `EXPECTED_GUI` lives in
`test_char_write_failure.py` and is shared with the Tk suite
`test_gui_char_write_failure.py` (grep), so changing it was not an option;
D161 is the right call and it is documented. S8's last check pins the
nameless case.

Defect found and fixed: removing a running chain resurrected it (D170).

### T6 · 9b verification — VERIFIED (with the blastFoam e2e left open)

**Plan §10, all four:**

1. Four routes wire the right hand-offs: `test_ui_char_chain_wiring` (T0
   golden) PASS, `test_ui_chain` C13 PASS, S1/S3 PASS.
2. Per-stage live validation: S5 PASS; my real-platform e2e: card 2 `● 1
   error` after a typed bad Lx, `● case OK` after the fix.
3. Copy from Setup and Load case fill the stage: S6 PASS; the e2e clicks
   both (`stage 1 holds the loaded 1D case`, `stage 2 holds the Setup
   case`).
4. A native 1D → 2D chain from the new screen as one result with stage
   tabs: `_e2e_ui_chain_screen.py`, **real platform** (`QT_QPA_PLATFORM`
   unset), at HEAD with both fixes: `E2E UI CHAIN SCREEN: PASS (23 checks)`,
   chain 2.3 s; one entry `CHAIN_E2E` kind chain with its badge, tabs
   `1D | 2D`, each tab's Field page draws (`figure`, `image`), the Summary
   .csv sha256 equal, C11's folder layout, nothing raised. The title passed
   through `Chain 2/2 · setup_2d · BlastLab` (no percent at the stage start,
   F25 fixed) and the tile read `0 %` beside `02 2D 0 %`
   (`docs/qa/2026-09-29-gui-chain/verify9b_e2e_run_stage2.png`; the
   implementer's `e2e9b_run_stage2.png` shows the old `100 %`).

**The F13 A/B and the pre-registered rules.** `measurements-9b.md`'s rules
were committed in `771a00e` (14:27:27) together with the sampler's new
actions; every sampled run in `viewer_measure_9b.json` is at `5ebd616`
(14:35:23), after it. `git diff 771a00e..HEAD` on the file only replaces the
`*(filled in after the runs)*` placeholder with the Results sections - the
rules are unaltered. Two harmless departures from the "Order of runs"
paragraph (no `stage` on the run surface, which the R-VIEWER paragraph
itself makes results-only; plain `resize` before `stripresize`), noted in
the file. I re-ran the committed sampler myself at HEAD `1a83437`, real
platform, `__main__`-guarded script, one process at a time:

| Surface | Action | Samples (with a window) | Longest wrong | Median | Rule | Verdict |
|---|---|---|---|---|---|---|
| run | `chainstrip` | 3222 (3222) | 0 ms | 0 | 0 ms over ≥ 500 | PASS |
| run | `stripresize` | 2321 | 29.7 ms | 27.4 | ≤ 31.5 (base 26.5 + 5) | PASS |
| results | `chainsel` | 2328 | 0 ms | 0 | 0 ms | PASS |
| results | `stagetabs` | 2399 | 0 ms | 0 | 0 ms | PASS |
| results | `chainresize` | 2259 | 26.4 ms | 24.2 | ≤ 32.6 (base 27.6 + 5) | PASS |
| setup | `chaintab` | 2169 (1055) | 0 ms | 0 | 0 ms | PASS |

Self-tests 148.5-151.2 ms at 60 px (none void), `not child` 0. The
implementer's numbers reproduce within a few ms. F13 (22-49 ms on a window
resize) stays open; it is base behaviour, `view3d_host.py` untouched. The
base side of the A/B was not re-run (it would need a worktree; the
implementer's base medians are used, as the rule says).

**Screenshots.** The 40 `gui9b-*.png` and 7 `e2e9b_*.png` exist; I looked at
`gui9b-light-1100x720-results-stage2.png` (tabs, `latest` + `chain` badges,
the caption) and my own e2e shots. Contrast recomputed by my own script from
`theme.DARK / LIGHT / chain_tint` for all 16 distinct new pairs in both
modes: every value equals `measurements.md`'s, none under its rule (lowest:
light `ok` on `ok_bg` 4.53, light running pill edge on the tint 4.65 ≥ 3).

**Harness** (offscreen, own settings, `PYTHONIOENCODING=utf-8`,
`findings.jsonl` is the truth):

| Run | My findings | Implementer's |
|---|---|---|
| `S00,B01,B02,B04,B07,G01,G03,M04,H03,D01,D02,E01,E03` (`verify9b-20261003-1554-a`) | 2: G01 S3 `QFontEngineFT: Failed to create FreeType font engine` (F26 reproduces, at the same step); H03 S2 `no result labelled 'QA native3d'` (needs D03's cache) | the same 2 |
| `G02` alone (`verify9b-20261003-1559-g02`) | none: native 1 → 2 → 3 chain in 12 s, results `['QA_CHAIN']` (one chain entry), three stage folders, two hand-offs, root manifest | none |
| `B06 --window` | not re-run (F10 is GUI-10's; it starts a run on the real desktop, and the implementer's run of it left a WSL scratch folder) | none |

G03 passed in the sequence again (F22's race did not fire).

**App launch:** `python -m blastlab`, real platform, throwaway settings,
20 s alive, stderr empty (0 bytes), stopped by its own `Popen` handle,
`auto_cleanup` still `False` after.

## The matrix (one suite at a time, HEAD `1a83437`, offscreen unless noted)

| Suite | Result |
|---|---|
| test_ui_chain_screen | PASS (185 at `8073a1c`; 187 after the two review checks) |
| test_ui_chain | PASS (114) |
| test_ui_char_chain_wiring (T0 golden) | PASS, and again as the very last run |
| test_ui_parity | PASS (41) |
| test_ui_frame | PASS (50) |
| test_ui_run_screen | PASS (168) |
| test_ui_run_panel | PASS |
| test_ui_setup_form / setup_tree / setup_strip | PASS / PASS (238) / PASS (110) |
| test_ui_char_case_form, test_ui_components, test_ui_theme | PASS |
| test_ui_results_screen / test_ui_results | PASS (186) / PASS (130) |
| test_ui_three_surfaces | PASS (35) |
| test_ui_drain, test_ui_view3d_host, test_ui_crashlog | PASS |
| test_ui_fieldform_viewport | PASS (11) |
| test_ui_no_vtk_in_main / test_ui_no_mpl_pyplot | PASS / PASS (19) |
| test_model_folder, test_case_validate, test_foam_writer | PASS |
| test_ui_live_gauges | PASS (20) |
| test_ui_char_results_exports, test_ui_char_results_meta, test_char_exports | PASS (goldens untouched) |
| test_ui_char_hd13_run | PASS |
| test_ui_char_write_failure | PASS (`2d_anim`, `chain_profile`; run at `8073a1c`, before any fix) |
| test_ui_results_vtk_folder, test_gauge_summary, test_report | PASS |
| test_anim_scale | PASS (68) |
| test_out1_qa_polish | PASS |
| _e2e_ui_chain | PASS (16) |
| _e2e_ui_chain_screen (real platform) | PASS (23) |
| _e2e_ui_chain_foam | **not run** - office machine (see Still open) |
| test_regression | PASS: 8 files byte-identical / arrays equal, run last |

The Tk suites were not run: no shared neutral module and no `gui/` file is
in the diff (9b or review).

## Defects found in the diff

| Where | Severity | What | Fixed |
|---|---|---|---|
| `ui/app.py` `on_run_started` / `ui/run_panel.py` `on_run_started` | low-medium (stale display: title, tile, Stop question) | F25: the last stage's percent stood at the next stage's start | yes, `2f58395` (D169) |
| `ui/app.py` `on_result` | medium (removed data resurrected) | a chain removed while running came back with its removed stages and frames | yes, `1a83437` (D170) |
| `ui/run_panel.py` `on_run_started` | low | F27: STEP / TIME / dt / P MAX tiles keep the last stage's values until the next progress | no, F27 (GUI-10; `_reset_readouts` would also drop the live plot / 3D view) |
| `_qa_ui_harness.select_result` | low (harness) | matches list text only, so a chain stage's label (`QA_CHAIN - 3D`) cannot be selected by name; G02 works through `entries()[-1]` | no - harness, GUI-10 |

Nothing else: no numerical change (display only; no coefficient, unit,
sign or range touched), no broad `except` or silent fallback in the diff,
no widget touched from a thread (every handler runs on the GUI thread via
the controller's drain), no new `QShortcut` (F5 five), no new timer, no
debug print or TODO, no unused import (an AST check of the seven touched
modules), no broken caller (`current()` keeps its contract for every
caller; `entries()[-1].dim / .result` answer for a chain). Tests: S7/S8
compare exact texts, sizes and `describe_dir` hashes; none asserts only
"no exception".

## Engineering questions

None. No number is computed or changed; the export bytes of a chain stage
equal a plain entry's (S8, e2e sha256); `test_regression` byte-green; the T0
golden byte-equal.

## Files touched by review

- `blastlab/ui/app.py`, `blastlab/ui/run_panel.py`,
  `blastlab/tests/test_ui_chain_screen.py`
- `docs/gui-redesign-decisions.md` (D169, D170, F25's outcome, F27)
- `docs/qa/2026-09-29-gui-chain/measurements-9b.md` (the verifier section,
  below the Results), `viewer_measure_9b_verify.json`,
  `verify9b_e2e_run_stage2.png`
- this report

## GUI screens that need QA

- **02 Run** during a chain: the strip (one row / two rows, every pill
  state, Stop and an error mid-chain), and - changed in review - the
  progress tile and the title at each stage's start (`0 %`, no percent in
  the title until the first progress), the Stop question then.
- **03 Results**: the chain's row (`chain` / `latest`, caption), the STAGE
  tabs, every view and export per stage, Remove - including Remove while
  the chain still runs (changed in review: the next stage starts a new
  entry).
- The embedded 3D viewer under the strip and the tabs (sampler PASS; F13 on
  resize as before).
- Chain and Setup: unchanged in 9b.

## Still open

- **`_e2e_ui_chain_foam.py` on the office machine** (pgrep empty first): the
  whole blastFoam 1 → 2 → 3 chain, incl. 9b's C4 `one chain entry in the
  picker` with three stages, stage 3's start time and the time order. It did
  not finish on this PC (3D stage > 1800 s); not re-run here, as instructed.
- Owner: D161 (the amendment), D157, D159, D160, D164, D165, D169, D170.
- GUI-10: F13 (resize lag), F22, F24, F26, F27, the harness's
  `select_result` for chain stages, and B06 `--window` (F10).
