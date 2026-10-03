# Verification — batch 2026-09-29-gui-chain, part 9a (GUI-9a, T0-T3)

Plan: [`2026-09-29-gui-chain.md`](2026-09-29-gui-chain.md), T0-T3 only (9b,
T4-T6, is not built yet and is out of scope). Report checked:
[`2026-09-29-gui-chain-a.implement.md`](2026-09-29-gui-chain-a.implement.md).
Range reviewed: `e58d21e..aa9b417` (five commits, after the F19 reword:
T0 `3e9ed58`, T1 `56c8014`, T2 `a789bbb`, T3 `15fe5f9`, report `aa9b417`),
against the base `4b28007` (`e58d21e` differs from it only in `TODO.md` and
the plan). Branch `gui-redesign`. Verifier run: 2026-10-03, the 8 GB home PC.

**Verdict: ready for QA.** Every T0-T3 criterion reproduces, on the
offscreen platform and on the real one. Review fixed two small things in two
commits (a broad `except` and two unused imports) and updated the hashes of
the F19 reword. One plan criterion is met through a documented amendment
(D138, the native material seed) that the owner should look at. Two decision
rows (D155, D156) and two F-rows (F23, F24) are added for the owner.

## Ground rules kept

- CLAUDE.md §8.2 dry run first: `<repo>\settings.json False []`.
- No python process was running at the start (no foreign PIDs). At the end
  none of mine was left; the launch probe (PID 27452) was stopped through
  its own `Popen` handle.
- Throwaway settings for every MainWindow: `ensure_qapp()` (it calls
  `private_settings()`), the e2e's own `BLASTLAB_SETTINGS`, the harness's
  own settings file, a temp settings file for the launch probe
  (`auto_cleanup: False`, unchanged after the run).
- Heavy suites one at a time (a sequential runner script; probes only
  between suites). Free physical memory about 2.0 GB, free commit about
  16 GB at the start. No `MemoryError` anywhere.
- One base worktree (`<scratch>\v9a_base_wt` at `3e9ed58`, i.e. base code
  plus the T0 test) for T0's at-base run. Removed; `git worktree remove`
  left its record ("Permission denied", F20's mechanism), deleted by hand a
  moment later. `git worktree list` shows only the main tree.
  (`.git/worktrees/gui6a_base_wt` is F20's, not mine, left alone.)
- Never staged: `docs/references/INDEX.md`, the Viper manual files,
  `viper_vtk_sample/`, `docs/qa/2026-09-27-*`. Every commit staged by
  explicit path, its message in a new `verify9a_msg_NN.txt` file, `git
  commit -F`. Not pushed.
- Every repo edit through Edit / Write. No shared neutral module, no Tk
  file, no fixture, no committed behaviour test and no solver default was
  touched by the batch or by review: `git diff --stat e58d21e..HEAD` over
  `core/ services/ models/ solvers/ output/ viz3d/ gui/`,
  `ui/view3d_host.py`, `ui/run_controller.py` and the three fixture folders
  is empty, so the Tk gate does not trigger.

## References

- **viper-theory**, sec. 3.4.1 *Remaps*, p. 6 (`=== page 6 ===` of
  `ViperTheoryManual_Client.txt`): "the simulation can be paused and
  'remapped' onto a higher-order grid by making use of the symmetry of the
  lower-dimension simulation ... No information is lost in the process as
  long as the remapping occurs prior to any symmetry-breaking". That is what
  `chain_route.py`'s docstring cites it for ("background for the texts
  only, not a source for any value"). Citation correct.
- **blastfoam-guide** sec. 5.9 (p. 79): only through
  `services.chain.HANDOFF_MSG`, unchanged; the 00 Stage page shows it
  verbatim (S5).
- **ufc-3-340-02**: only through the reused `scaled_distance` (Z rings,
  Derived card); no new formula. No other standard is touched.
- The hand-off texts against the code (D143): `solvers/jobs.py` writes the
  profile at the stage's end; for a 2D `remap` trigger
  `write_trigger_remap` writes the trigger instant to
  `trigger_file or profile_file`, and a chain stage runs with
  `trigger_file = None` (`services/model_folder.py` line 1168), so the
  hand-off holds the trigger instant. The out-text "The field when the wave
  reaches G1 (trigger gauge, remap), or at the end of the run" is right.

## Fixes made in review

| Commit | Task | What |
|---|---|---|
| `a06d7db` | (F19) | The F19 reword's new hashes: F19's outcome in the decisions file (reworded, the new hashes, the orphaned note on `e57672f` left alone), F18's outcome cites `56c8014`, the 9a report's commit list and headings carry the new hashes. |
| `45760ce` | T2 | `ChainPanel._setup_case` caught every `Exception` and returned None, so a bug in the Setup source read as `01 Setup has errors - fix them first.` and silently stopped seeding. It catches `ValueError` only now (what `get_case()` raises; the one case `MainWindow.current_case` handles). S6 gained two checks; the second fails on the code before the fix (`FAILED: 1 of 125`, shown by restoring the old file), passes after. |
| `80d2c03` | T2 | Leftovers: unused `QSizePolicy` (`chain_panel.py`) and `QStackedWidget` (`chain_stage.py`). |

## Per task

### T0 · Pin what a chain launches — VERIFIED

- `3e9ed58` holds only `test_ui_char_chain_wiring.py` and
  `char_golden/ui_chain_wiring.json`; its parent is `e58d21e` (= base code).
  Neither file changed since (`git diff 3e9ed58..HEAD` over both: empty).
- **At base:** the test in a `3e9ed58` worktree (no GUI-9 code; it drives
  the checkboxes through `drive_route`): `CHAR UI CHAIN WIRING: PASS`
  (both tests). So the golden is the base's output.
- **At HEAD:** `CHAR UI CHAIN WIRING: PASS`, before and after my fixes.
- The golden holds 16 scenarios: the four routes × default / variant
  (stage 2 gauge + `trigger_gauge` 1, stage 1 radius 2 m), all `True` with
  no sink call; the eight refusals with their exact lines (Lx `abc`,
  planar with 3D, cy 99 `Charge centre is outside the domain`, native →
  blastFoam on 2 and on 3 via route 13, the three model-box lines + the
  `WHERE_BOXES` line). The variant's stage 2 carries `trigger_gauge 1`,
  gauges `[1.5, 1.0]`, `profile1d` from `<MODEL>\handoff_1d_to_2d.txt`.
- `test_route13_is_c6b` ties the (1,3) entry to C6b: PASS.

### T1 · Routes; the wiring in one pure module — VERIFIED

- **`wire()` is the base `run()` body, verbatim in effect** (read line by
  line against `git show e58d21e:blastlab/ui/chain_panel.py`): the same
  N2-13 loop, the same three blocks in the same order, the same
  axisymmetric refusal text (returned, and `run()` still focuses stage 2
  and refuses with it), GUI-8's 1 → 3 block (§8.3's code exactly). The only
  addition is `put()`, a no-op for a stage that did not parse (live checks
  only; `run()` never passes None). T0's golden is the proof that nothing
  a chain launches moved.
- C13 (`test_ui_chain`, 113 checks, PASS): per route `checked()` = dims,
  `run()` True with no sink call, dims in order, every edge's
  `profile_file == profile_file_in == <root>\handoff_name(a, b)`,
  `init_mode` profile1d / profile2d, the first stage's `init_mode` and the
  last's `profile_file` its form's own, `adaptive_write False`,
  `stage_errors == []`, nothing on disk: PASS.
- `set_route('')`, `'1'`, `'32'` raise ValueError, route and buttons
  unchanged; four buttons, one checked, board labels: PASS.
- `chain_route` imports no Qt (S1, checked in a subprocess): PASS.
- **Committed pins:** the `test_ui_chain` diff changes exactly what the
  plan lists (C1's two layout pins, C2 removed with its folder check moved
  onto C3, `use[...]` → `set_route` in C2b-C12, C8's refusal → the empty
  Model box with its four assertions unchanged). Every behaviour assertion
  (C2b lines, C3 prefix and focus, C4 text, C5-C6b wiring, C7, C9/C10, C11
  layout and names, C12's non-ambient start) is unchanged. Harness
  `_chain_forms`, G01, M04 and the two e2e `use[...]` lines: as listed.
- Top bar: `Chain 1D → 3D` after `set_route('13')`, `route_changed` once,
  the link still navigates (S1); `test_ui_frame` 50 checks PASS (F2, F5
  five shortcuts, F6).
- No other caller of the removed `use` / `stage_seg`: the only hits are
  Tk (`blastlab/gui/`, its own panel), the Tk harness and the T0 test's
  base fallback.

### T2 · The Chain screen — FIXED (two small review fixes)

`test_ui_chain_screen` PASS, 123 checks at `aa9b417`, 125 after
`45760ce`, **offscreen and on the real Windows platform**
(`QT_QPA_PLATFORM=windows`, the whole suite: 123/123).

- **S2 layout:** at 1600 × 1000 tree 272, properties 340, cards
  `[308, 308, 308]`, links 118 / 200; the board heights hold under the QSS
  (route group 38 / buttons 32, Run chain 176 × 56, Copy / Load 36, pill
  40, tools 28); 270 pages (both modes × 1100 × 720 and 1280 × 840 × every
  route, stage and visible node): `clipped(win)` empty; no text cut
  mid-glyph; the 64 px link wraps `handoff_ / 1d_to_ / 2d.txt`; contrast
  pairs ≥ 4.5 (arrow ≥ 3). PASS on both platforms.
- **S3 cards and arrows:** per route the count, numbers, folders, arrow
  labels = the §8.2 names (also = `model_folder.handoff_paths`, S1), the
  Run chain line `N stages · into \CHAIN\`, HAND-OFF IN / OUT files
  (`none` at the ends) and texts; Outer named with its radius; the trigger
  gauge and action named; the 2D in-text names `z 2.0 m`; a 77-character
  path keeps the column at 340: PASS.
- **S4 stage editor:** tree = `['stage']` + Setup's visible nodes for
  every dim × solver; each node shows only its cards; `'nodes'`; a fed
  stage hides Initialize from / Profile file, `get_case()` equal across
  `set_fed`; header numbers = `header_numbers(setup_strip.tiles(case,
  rep))` for each wired stage; the 3D stage: hint, no canvas, no
  `View3DHost`: PASS. `set_fed` is `'nodes'`-only and Setup's forms are
  never fed; `init_mode` had no spec group, so the new `unfed` row group
  (default on) changes nothing for Setup (Setup suites green, unchanged).
- **S5 live validation:** Lx `abc` → card 2 `● 1 error` in danger, 02
  Domain ✗, pill `1 error`, cards 1 and 3 `● case OK`; fixed → all OK;
  cy 99 → stage 2's errors = `stage_errors`' `Stage 2 (2D): ` lines;
  native 1D → blastFoam 2D → `HANDOFF_MSG` in stage 2's errors and
  `_compat[2]` on its 00 Stage; two edits 100 ms apart → one
  `stage_checks`; 300 ms = `MainWindow._validate_timer`; no active timer
  idle; Run chain enabled through a stage error, `run()` refuses naming
  stage 2 and brings it forward: PASS.
- **My equivalence probe** (`v9a_probe2.py`, not committed): 4 routes ×
  11 perturbations that parse (cy 99, planar, trigger 5 of 0 gauges,
  t_end −1, radius 0.001, the two native → blastFoam mixes, all native,
  stage 2 first on `profile1d` without a file, cz 99), on a shown
  standalone panel: the union of the live errors with the stage prefix
  equals `run()`'s refusal lines in every case but planar-with-3D, where
  the live list also carries the planar case's own validation lines that
  `run()` never reaches (it stops at the refusal) — a superset about the
  same field (D156). A blank Model box gives the same live errors as a
  valid one for every route (D150 holds). A Run-tab model change restarts
  the checks (the Run chain line follows: `\AAA\` → `\BBB\`).
- **S6 Copy / Load / seeding** (MainWindow, throwaway settings): untouched
  stages 1 and 3 get charge 2.5, the Setup case's material, native, the
  rest the spec default; stage 2 Copy = `setup.get_case()` (asdict);
  stage 1 Copy = the seeding rule; a touched stage asks once, Keep changes
  nothing; Setup changed → untouched stage 3 follows, touched 1 and 2 do
  not; on blastFoam the untouched stage takes C4; bad Setup → Copy off with
  `01 Setup has errors - fix them first.`; Load case… 1D = `load_case`, 2D
  into stage 1 → `That case is 2D; stage 01 is 1D.`, stage unchanged:
  PASS. **One amendment (D138):** the plan's S6 example expects the
  untouched stages to get material **C4** from a native Setup; the build
  seeds the Setup **case**, and a native case always carries TNT (the
  hidden material box is not written to the case, `models/fields.py`
  `_charge_model`, UX-E2), so it seeds TNT, and C4 only on blastFoam. That
  is the plan's own build text ("from the Setup case") and the CLAUDE.md §4
  hidden-controls rule, and it agrees with Copy (which sets the whole
  case); the plan's example was written without the native rule. **Owner:**
  confirm D138, or say the hidden box should be seeded instead.
- **Touched flag probe** (`v9a_probe1.py`): route changes, a stage / node
  sweep, a theme round trip and a global solver change leave all three
  stages untouched; one user edit touches only its stage. No uncaught
  exception.
- **Qt lifetime probe** (`v9a_probe3.py`): three panels built, 12 route
  changes each (arrows deleted every time), destroyed; then four theme
  changes on a live panel: no exception (no slot left on a deleted object).
- **Hidden-controls rule:** nothing the batch writes to a case comes from a
  hidden control: the fed rows are hidden by a row group, not a solver
  scope, `get_case()` is unchanged by them (S4) and the wiring overwrites
  both on every fed stage; seeding writes form fields only (charge,
  material, the stage solver) and never the case.
- Every suite the plan names for T2 is green (matrix below).

### T3 · 9a verification and report — VERIFIED

- **The fast matrix**, one suite at a time at `aa9b417` (all 27, rc 0):
  see the table below. After my fixes: the three chain suites,
  `test_ui_frame`, `test_ui_parity`, `test_out1_qa_polish`,
  `test_ui_setup_form` and `test_regression` again: PASS.
- **The 9a e2e** (`_e2e_ui_chain_screen.py`), real platform
  (`QT_QPA_PLATFORM` unset), throwaway settings, `use_model`: the route
  button clicked, stage 1 by **Load case…**, stage 2 by **Copy from 01
  Setup** (both clicked), both `● case OK`, Lx `abc` → `● 1 error` and
  back, **Run chain clicked**, finished in 2.3 s; the model folder is
  `['.blastlab-model', '1d', '2d', 'handoff_1d_to_2d.txt',
  'manifest.json']`; results `CHAIN_E2E - 1D`, `- 2D`; nothing raised:
  `E2E UI CHAIN SCREEN: PASS (15 checks)` at `aa9b417`, and again after
  the fixes (2.5 s). The `loaded_copied` shot of my run (scratch, not
  committed) matches the committed one.
- **App launch:** `python -m blastlab`, real platform, throwaway settings,
  20 s: alive, stderr empty, stopped by its handle.
- **Screenshots and measurements:** 24 real-platform shots + 4 e2e shots
  and `measurements-9a.md` / `measure-9a.json` in
  `docs/qa/2026-09-29-gui-chain/`. My real-platform run of the whole S2
  reproduces its 1600 × 1000 widths and every board height, and finds
  nothing clipped at 1100 × 720 / 1280 × 840.
- **Harness**, offscreen, own settings, `--scenario
  S00,B01,B02,B04,B07,G01,G03,M04,H03` (`~\blastlab_qa\verify9a-20261003*`,
  `findings.jsonl` is the truth):

  | Scenario | My run | Implementer's |
  |---|---|---|
  | S00, B02, B04, B07, G01, M04 | no finding | no finding |
  | B01 | no finding with `PYTHONIOENCODING=utf-8`; my first run (stdout redirected to a cp1252 file) died on `print` of `●` (F24, the harness, not the app) | no finding |
  | G03 | the same 3 findings (`the run started` S1, `Run chain is disabled during a Run-tab run` S2, `and the callback behind it refuses too` S1) | the same 3 |
  | H03 | 2 findings (no `QA native2d` / `QA native3d` cached result) | the same 2 (also at base) |

  **G03 (F22) reproduced as described:** G03 alone and G01 + G03 give no
  finding; the full list gives the three. The log shows the Run-tab run
  started and finished (`QA_G03 finished in 15 s`) before the check's
  40 s wait expired; `wait_log`'s mark (taken before the click as a
  character count) sits past the new run's `2D Blast Solver` line when the
  previous scenario left a log longer than the new run's first lines. The
  next two findings follow from the run having ended. The app is right.
  B02 idle CPU on the Chain screen: 0.9 % and 1.6 % of a core over 5 s
  (Setup 1.4 %, Run 0.3-1.6 % in the same runs; no timer active idle, S5).
- **Report and rows:** the report exists with D131-D154 and F18-F22; its
  claims above all reproduce.

## The matrix (one suite at a time, `aa9b417`, offscreen)

| Suite | Result |
|---|---|
| test_ui_chain_screen | PASS (123; 125 after `45760ce`) |
| test_ui_chain | PASS (113) |
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
| test_regression | PASS (8 files byte-identical / arrays equal), and again at the end |
| test_model_folder | PASS |
| test_case_validate | PASS |
| test_foam_writer | PASS |
| test_out1_qa_polish | PASS |

## Defects found in the diff

| Where | Severity | What | Fixed |
|---|---|---|---|
| `ui/chain_panel.py` `_setup_case` | medium (silent failure) | `except Exception: return None` hid any bug in the Setup source as "01 Setup has errors" | yes, `45760ce` |
| `ui/chain_panel.py`, `ui/chain_stage.py` imports | low (leftover) | unused `QSizePolicy`, `QStackedWidget` | yes, `80d2c03` |
| `ui/chain_stage.py` `_render_checks` (and GUI-6's `run_panel._path_lbl`) | low | selectable text with U+200B after separators: a copied path carries invisible characters | no, F23 (GUI-10; the Run label has it since GUI-6) |
| last stage's HAND-OFF OUT text | low | "as one result with a tab per stage" is true only after 9b T5 | no, D155 (9b follows) |
| live checks, planar stage 2 with a 3D stage | none (by design) | live list is a superset of `run()`'s refusal | no change, D156 |

Nothing else: no numerical change (no coefficient, unit, sign or range
touched; the hand-off texts format the case's own numbers), no new
`QShortcut` (F5 five), no new timer but the debounce, no widget touched
from a thread (the Chain has no worker), no test that asserts nothing (the
S3 text checks compare the shown caption with `chain_route`'s function of
the wired case and are backed by the specific Outer / trigger / burst-height
checks), no TODO or debug print in the diff, no broken caller.

## Engineering questions

None. No number differs anywhere; T0's golden is byte-equal at base and at
HEAD, and `test_regression` is byte-green.

## Files touched by review

- `blastlab/ui/chain_panel.py`, `blastlab/ui/chain_stage.py`,
  `blastlab/tests/test_ui_chain_screen.py`
- `docs/gui-redesign-decisions.md` (F18 / F19 hashes; D155, D156, F23,
  F24; F22's verify note)
- `docs/batches/2026-09-29-gui-chain-a.implement.md` (the new hashes)
- this report

## GUI screens that need QA

- **Chain** (all of it): routes, pipeline, Run chain, the three stage
  editors, 00 Stage, Copy / Load, live checks, both modes, 1100 × 720 and
  1600 × 1000. The review fix changes nothing visible (Copy's why-not only
  for a real parse failure, as before).
- The top bar's Chain link (follows the route).
- **01 Setup** only through the additive parameters (its pill, tree footer,
  hand-off card defaults unchanged); the light-mode `HandoffCard` fill
  (D152) shows only on the Chain.

## Still open

- 9b (T4-T6): the chain strip in 02 Run, one 03 Results entry with stage
  tabs, the §10 verification; D155 becomes moot with T5.
- Owner: D138 (seed TNT from a native Setup, or the hidden box), D137
  (Run chain enabled with stage errors), D155, D156.
- GUI-10: F21 (Setup pill / + buttons 26 px), F22 (`wait_log`), F23
  (U+200B on copy), F24 (harness stdout encoding), and F8.
