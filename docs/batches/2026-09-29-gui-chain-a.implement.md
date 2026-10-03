# Implementer report — batch 2026-09-29-gui-chain, part 9a (GUI-9a)

- Plan: [`2026-09-29-gui-chain.md`](2026-09-29-gui-chain.md), T0-T3.
- Branch `gui-redesign`, from base `4b28007` (GUI-7 closed). HEAD at the
  start was `e58d21e`, which differs from the base only in `TODO.md` and the
  plan, so "at base" and "at the start" are the same code.
- 9b (T4-T6: the chain strip in 02 Run, one 03 Results entry with stage
  tabs, the §10 verification) is a separate run. Nothing of 9b was started.
- Measurements and screenshots:
  [`docs/qa/2026-09-29-gui-chain/measurements-9a.md`](../qa/2026-09-29-gui-chain/measurements-9a.md).

## The gates

- **Numbers.** No number, default, case key, file format, hand-off file,
  export byte or solver changed. `test_regression.py` was byte-green at the
  start, after T2 and twice in T3 (the baseline files are unmodified).
- **What a chain launches.** T0's golden (`test_ui_char_chain_wiring`) was
  recorded at base and committed alone first. It is byte-equal after T1
  (`set_route` instead of the checkboxes, the wiring moved into
  `chain_route.wire`), after T2 (the stage forms moved to `'nodes'`) and
  after T3.
- **Frozen modules.** `git diff --stat 4b28007` over `core/`, `services/`,
  `models/`, `solvers/`, `output/`, `viz3d/`, `gui/` (Tk),
  `ui/view3d_host.py`, `ui/run_controller.py` and the three fixture folders
  is empty, so the Tk suites were not triggered. `setup_panel.py`,
  `setup_tree.py`, `components.py` and `case_form.py` got only the additive
  parameters the plan names (`pill_text(ok_text=)`, `add_footer`,
  `HandoffCard(tinted=)`, `set_fed`).
- **Imports.** `chain_route.py` imports no Qt (checked in a subprocess,
  S1); no VTK or pyplot in the GUI process (`test_ui_no_vtk_in_main`,
  `test_ui_no_mpl_pyplot`, and the last check of `test_ui_chain_screen`).
- **No new QShortcut** (`test_ui_frame` F5 still five). **One timer** on
  the screen, the 300 ms debounce; S5 asserts no timer is active on the
  idle screen. Idle CPU after settling, offscreen, 10 s: Chain 1.09 %,
  Setup 1.72 % (the pump loop's own cost); harness B02 0.9 % (base 0.3 %;
  B02's 5 s window starts right after the first show).
- **App launch.** `python -m blastlab` with throwaway settings ran 25 s
  with empty stderr after T1 and T2 (offscreen) and after T3 (real
  platform); stopped by its own process handle each time.
- **Session safety.** The §8.2 dry run at the start printed
  `<repo>\settings.json False []`. Every MainWindow ran with throwaway
  settings (`ensure_qapp()` / `private_settings()`, the harness's own).
  `use_model()` for every real run. No WSL run.
- **Process hygiene.** No `python` process was running at the start (no
  foreign PIDs to protect), and none was left at the end. The processes I
  started were the suites, the launch probes (killed through their own
  `Popen` handle, e.g. PID 10208) and the harness runs; all exited. The
  Chain screen embeds no viewer child.
- **Worktree.** `gui9a_base_wt` (`4b28007`) for the harness A/B, removed;
  `git worktree list` shows only the main tree. `git worktree remove` left
  its record under `.git/worktrees/` ("Permission denied"); deleting it a
  moment later worked (F20).
- **Memory.** This 8 GB PC had 0.6-1.5 GB free physical memory and
  13-16 GB free commit. Suites ran one at a time; no `MemoryError`.

## Commits (`e58d21e..`)

- `e57672f` T0: the test and the golden, alone, first. **Its message is
  GUI-7's T0 message** (a same-named file left in the shared scratch dir;
  F19). The real message is attached as a git note (`git log --notes -1
  e57672f`). Not amended.
- `795a846` T1: routes, `chain_route`, the top-bar link, the pins.
- `d97e48a` T2: the Chain screen.
- `a5c423d` T3: the real-platform fixes (board heights, wrapped paths) and
  the 9a e2e.
- this report's commit: report, measurements, screenshots, decisions
  D131-D154, F18-F22.

Every message (except F19's) was written to a new `gui9a_msg_*` file in the
scratch dir and committed with `git commit -F`, staging by explicit path.
The six foreign paths were never staged.

---

## T0 · Pin what a chain launches · DONE · `e57672f`

- New `blastlab/tests/test_ui_char_chain_wiring.py` and its golden
  `char_golden/ui_chain_wiring.json` (16 scenarios).
- A standalone `ChainPanel` built as `test_ui_chain.main()` builds it, a
  fresh one per scenario. One route setter, `drive_route()`:
  `set_route(key)` when the panel has it, else the checkboxes.
- Recorded per scenario: `run()`'s return, the launched `[(dim,
  asdict(case))]` (floats as `repr`, the model root as `<MODEL>`, the runs
  folder as `<RUNS>`), the sink's calls, the log lines, the runs folder's
  contents (always empty).
- Scenarios: the four routes on the default forms and on one variant
  (stage 2 with a gauge and `trigger_gauge` 1, stage 1 radius 2 m); the
  refusals Lx `abc`, planar stage 2 with 3D, cy 99, native 1D → blastFoam
  2D (route 123), native 1D → blastFoam 3D (route 13), and C2b's three
  model-box refusals.
- `test_route13_is_c6b` checks the golden's (1,3) entry against C6b's
  expectations, so the two pins cannot drift.

Criteria: PASS at base (`--update` wrote it, then `CHAR UI CHAIN WIRING:
PASS`), and after T1, T2 and T3 byte-for-byte. Run: `cd blastlab/tests &&
python test_ui_char_chain_wiring.py`.

## T1 · Routes replace the checkboxes; the wiring in one pure module · DONE · `795a846`

- New `blastlab/ui/chain_route.py`, toolkit-free:
  - `ROUTES` (board order), `route_dims` / `route_key` / `route_label`
    (ValueError for anything else);
  - `handoff_name(a, b)`: the basename of `model_folder.handoff_paths`;
  - `wire(dims, cases, hand)` → `(cases, refusal)`: `run()`'s wiring moved
    verbatim (N2-13 pinned schedule, hand-offs at the model root, the
    axisymmetric refusal returned, GUI-8's 1 → 3). A stage whose form does
    not parse may be `None` (the live checks); its key still says it is in
    the route, so the others are wired as at run time;
  - `stage_checks(dims, sources, hand)` → `{d: StageCheck}`: parse, wire,
    `validate_case(case, pending_inputs=(d != dims[0]))`, the
    native → blastFoam rule; nothing written, no later hand-off looked up;
  - the texts: `NONE_IN`, `LAST_OUT`, `in_text`, `out_text`, `key_line`,
    `stage_summary`, `stage_title` (D143: the code says when the hand-off is
    written; `solvers/jobs.py` and the solvers' profile writes were read,
    not edited).
- `ChainPanel`: the three `QCheckBox`es and `use` are gone. A checkable,
  exclusive route group (`#chainroute`), `set_route` / `route` / `checked`
  / `route_changed`; `run()` keeps its order and every refusal text and
  calls `chain_route.wire`; `No stages selected.` stays as a defence.
- `TopBar.set_chain_label`; `MainWindow` connects the route to it.

Tests: `test_ui_chain` C13 (new), `test_ui_chain_screen` S1 (new).

| Criterion | Result |
|---|---|
| Per route: `checked() == dims`, `run()` True with no sink call, dims in order, every edge's `profile_file == profile_file_in == <root>\handoff_name(a, b)`, `init_mode` profile1d / profile2d, the first stage's `init_mode` and the last stage's `profile_file` its form's own, `adaptive_write is False`, `stage_errors == []`, nothing on disk | PASS (C13, 4 routes) |
| `set_route('')`, `'1'`, `'32'` raise ValueError, route and buttons unchanged; exactly four buttons, one checked | PASS (C13) |
| `test_ui_char_chain_wiring` PASS through `set_route` | PASS |
| `test_ui_chain` green with only the listed pins changed; C2b-C12 behaviour unchanged | PASS (113 checks) |
| The top-bar link reads `Chain 1D → 3D` after `set_route('13')`; navigation works (`test_ui_frame` F2) | PASS (S1; frame 50) |

**Committed assertions changed (plan §9: layout the owner replaced):**

- `test_ui_chain` C1: `all three stages start checked` (`checked() ==
  [1, 2, 3]`) → `the route starts on 1D -> 2D -> 3D, all three stages`
  (`route() == '123' and checked() == [1, 2, 3]`). In T2:
  `stage_seg.changed.emit('Stage 3D')` → `QTest.mouseClick(cards[3])`;
  `stage_seg.get() == 'Stage 1D'` → `cards[1].selected() and not
  cards[3].selected()`. Reason: the checkboxes and the stage switcher are
  gone.
- C2: `no stages selected -> refused` and `and the status line says it
  too` removed (no route can be empty; C13 pins the invalid routes). `the
  model folder was NOT created by a refused run` moved onto C3's refusal.
- C2b, C3, C6, C6b, C10, C11, C12: `use[d].setChecked(...)` →
  `set_route(key)` with the same dims. C10's `dropping the middle stage
  moves it to 1 -> 3` is now named `the route 1D -> 3D moves it to 1 -> 3`;
  it asserts the same.
- C8: the refusal that proves "the dialog is strictly last" is the empty
  Model box (`source[:] = [ws_root, '']`) instead of "no stages"; its four
  assertions (False, status first, the log, `dialog failed`) unchanged.
- `_qa_ui_harness.py`: `_chain_forms` → `set_route('123')`; G01's
  `no stage checked` and `a gap in the chain (1 and 3)` (stale since
  GUI-8, F18) → "the route control offers exactly the four routes" and
  "an empty route is refused, the route unchanged"; M04 → `set_route('12')`.
- `_e2e_ui_chain.py` (`use[3]` → `set_route('12')`) and
  `_e2e_ui_chain_foam.py` (`use[d]` → `set_route('123')`); their result
  checks are 9b's (T5).

## T2 · The Chain screen · DONE · `d97e48a`

- New `blastlab/ui/chain_pipeline.py`: `RouteBar`, `StageCard` (number,
  title, solver chip, elided mono key line, live state, folder),
  `HandoffArrow` (painted 1.6 px arrow; the file name wraps after an
  underscore and never widens the row), `Pipeline` (308 / 118 or 200 px;
  the links give way to 64 first, then the cards to 200, D151).
- New `blastlab/ui/chain_stage.py`: `StageEditor`, one per stage, built
  once. Tree (`SetupTree`, 272 px) with `00 Stage` first, then Setup's
  nodes, children, ✗ via `node_of_field`; Copy from 01 Setup / Load case…
  (`add_footer`) and the `Stage OK` pill. Centre: title and the numbers
  from `setup_strip.tiles` (`header_numbers`), then the Setup's toolbar
  line (caption / hover, Z rings · Mesh · Fit, D148), the Setup's
  `Preview1D` / `Preview2D` with its own `ModelOverlay`; a 3D stage shows
  the hint (D134). Properties (340, D19): 00 Stage (solver switch, the
  N5-4 refusal, HAND-OFF IN tinted, HAND-OFF OUT neutral, Checks, the
  folder note), or the node's own cards and the Derived card.
- `blastlab/ui/chain_panel.py`: the screen. `forms[d]` are the editors'
  `CaseForm(placement='nodes')`; `_stage_seg_solver`, `_compat`, `run_btn`,
  `status`, `HINT` keep their names. One 300 ms debounce runs
  `chain_route.stage_checks` (form, route, solver and Run-tab model
  changes; at the first show; deferred while off screen, D150). Seeding,
  `copy_from_setup`, `load_case` (D138-D140). `run()` unchanged.
- `case_form.set_fed` (D141), `setup_tree.add_footer`,
  `setup_panel.pill_text(ok_text=)`, `components.HandoffCard(tinted=)`,
  the theme's Chain QSS and `chain_tint` (D152), `app.py`
  (`setup_source=self.current_case`, `case_reader=_read_case_file(...,
  'Load case')`, the Run tab's two boxes → `schedule_checks`).

Tests: `test_ui_chain_screen` S2-S6 (offscreen). Run: `cd blastlab/tests &&
python test_ui_chain_screen.py` → `UI CHAIN SCREEN: PASS (123 checks)`.

| Criterion | Result |
|---|---|
| S2: at 1600 × 1000 tree 272, properties 340, cards 308 (route 123) | PASS (272 / 340 / 308; links 118, two-stage link 200) |
| S2: nothing clipped at 1100 × 720 and 1280 × 840, both modes, every route, stage and visible node | PASS (270 pages) |
| S2: the caption, titles, key lines, states and hand-off labels never cut mid-glyph | PASS (elided with tooltip or wrapped after `_`) |
| S3: per route, cards / numbers / folders / arrow labels / Run chain line / HAND-OFF IN-OUT files (§8.2) / texts = `chain_route`'s for the wired case | PASS (4 routes) |
| S4: tree = `['stage']` + Setup's visible nodes (same dim and solver); a node shows only its cards; `'nodes'`; fed stage hides `init_mode` / `profile_in`, `get_case()` equal before / after `set_fed(True)`; header numbers = `setup_strip.tiles`; 3D: hint, no canvas, no View3DHost | PASS |
| S5: Lx `abc` → card 2 `● 1 error` in danger, 02 Domain ✗, pill `1 error`, cards 1 and 3 `● case OK`; restore → all OK | PASS (native mode: blastFoam's defaults carry a parallel-run warning) |
| S5: cy 99 → stage 2's errors = `stage_errors`' `Stage 2 (2D): ` lines, line for line; no other stage | PASS |
| S5: native 1D → blastFoam 2D → card 2 error, `HANDOFF_MSG` in its Checks, `_compat[2]` on 00 Stage | PASS |
| S5: two edits 100 ms apart → one `stage_checks`; the interval is `MainWindow._validate_timer.interval()` | PASS (1 call; 300 ms) |
| S5: Run chain enabled through a stage error; `run()` refuses naming the stage | PASS |
| S6: Setup 2D (charge 2.5, C4, native) → untouched stages 1 and 3: charge 2.5, the case's material, native, the rest the spec default | PASS, **with D138**: a native case carries TNT (`models/fields.py`, UX-E2), so native seeds TNT; C4 is checked on blastFoam (untouched stage 3 takes C4 and blastFoam) |
| S6: stage 2 Copy = `setup.get_case()` (asdict); stage 1 Copy = seeding; a touched stage asks once, Keep changes nothing; Setup with a bad field → Copy off with the why-not | PASS |
| S6: Load case… a `Case1D` JSON → `get_case()` = `load_case(path)`; a 2D JSON into stage 1 → one `show_error` with the dimension sentence, stage 1 unchanged | PASS |
| S6: a touched stage is not re-seeded when Setup changes; an untouched one is | PASS |
| `test_ui_chain`, `char_chain_wiring`, `setup_form`, `setup_tree`, `setup_strip`, `components`, `char_case_form`, `parity`, `frame` green; Setup suites unchanged | PASS (and `theme`, `no_vtk`, `no_pyplot`) |

## T3 · 9a verification · DONE · `a5c423d` + this commit

**The fast matrix, one suite at a time** (from `blastlab/tests`, after T2;
the T3 fixes re-ran the chain, parity, frame, setup, theme and regression
suites, all green again):

| Suite | Result |
|---|---|
| test_ui_chain_screen | PASS (119; 123 after T3's fixes) |
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
| test_regression | PASS (byte) |
| test_model_folder | PASS |
| test_case_validate | PASS |
| test_foam_writer | PASS |

Also `test_out1_qa_polish` PASS (it drives `win.chain.run()`).

**A native 1D → 2D chain from the new screen** — new
`blastlab/tests/_e2e_ui_chain_screen.py` (the 9a form of T6's e2e; 9b adds
the strip and the one Results entry). Real platform, throwaway settings,
`use_model(win, 'CHAIN_E2E')`: the C11 2D case opened in Setup; Chain; the
`1D → 2D` route button clicked; stage 1 by **Load case…** (clicked,
`dialogs.open_file` patched to the C11 1D case); stage 2 by **Copy from 01
Setup** (clicked); both cards `● case OK`; Lx `abc` → `● 1 error` and back;
**Run chain clicked** (`QTest.mouseClick`); it finished in 2.4 s; the model
folder is `['.blastlab-model', '1d', '2d', 'handoff_1d_to_2d.txt',
'manifest.json']`; results `CHAIN_E2E - 1D`, `CHAIN_E2E - 2D`.
`E2E UI CHAIN SCREEN: PASS (15 checks)`. Run: `cd blastlab/tests && python
_e2e_ui_chain_screen.py [--offscreen] [--shots DIR]`.

**Screenshots and measurements** — 24 real-platform shots (dark / light ×
1100 × 720 / 1600 × 1000 × route 123 stage 2, route 13, a stage error,
stage 2 on 05 Gauges, the trigger hand-off, a 3D stage) and 4 e2e shots in
`docs/qa/2026-09-29-gui-chain/`; `measurements-9a.md` has the widths and
heights against the board and the contrast of 44 text pairs per mode.
`clipped(win)` was empty in all 24. What the first real-platform pass found
and this batch fixed (`a5c423d`):

- the route group was 40, Copy / Load 38 and the stage pill **26** px
  (D41's mechanism) → 38 / 36 / 40, pinned in the QSS, asserted in S2
  (D153). Setup's own pill and + buttons are 26 px too: F21, not changed;
- 00 Stage's column went to ~490 px at 1100 × 720 under a 77-character
  model path in the folder note → the path wraps; 340 px asserted in S3
  (D154);
- light mode: on `accent_bg` five text pairs were 4.24-4.47 and the arrow
  2.58 → the selected / tinted fill and the arrow colour of D152.

The only pair under its rule is F8's `num_dim` (unselected card number,
3.52 dark / 2.97 light), the Setup tree's colour, left for GUI-10.

**Harness** (offscreen, own settings, `--scenario
S00,B01,B02,B04,B07,G01,G03,M04,H03`, `~\blastlab_qa\gui9a-20261003`;
`findings.jsonl` is the truth), against the same list at base (a
`4b28007` worktree, `gui9a-base-20261003`):

| Scenario | HEAD | Base |
|---|---|---|
| S00, B01, B02, B04, B07 | no finding | no finding |
| G01 | no finding (the two new route checks pass) | 4 findings: `a gap in the chain (1 and 3) is refused`, `and the refusal names the stage`, `and the refusal names the Model box`, `no model folder was created while every run was refused` (F18: the gap started a real chain) |
| G03 | 3 findings: `the run started` (S1), `Run chain is disabled during a Run-tab run` (S2), `and the callback behind it refuses too` (S1) | no finding |
| M04 | no finding (1 → 2 chain from `set_route('12')`, C11's layout) | no finding |
| H03 | 2 findings: `no result labelled 'QA native2d' / 'QA native3d' to select` | the same 2 |

- **G03 is a harness race, not the app (F22).** G03 alone passes at HEAD,
  and G01 + G03 pass too; the full list fails it twice in a row. A scratch
  copy of the harness (not committed, deleted) printed why: `click` took
  the log mark at 347 characters (G01's refusal lines), the new run's log
  was already 1,590 characters at the first look, and `2D Blast Solver`
  was at 326, before the mark. At base G01's real chain (F18) left a long
  log, the mark exceeded the new log and was reset, which hid the race.
  After the missed start the run finishes, so Run chain is enabled again
  and the next two checks fail as a consequence.
- **H03** needs results the C / D scenarios cache; none ran in this list.
  Same at base.
- **B02 idle CPU on the Chain tab:** 0.9 % at HEAD (twice), 0.3 % at base,
  over 5 s right after the first show. Settled, 10 s: 1.09 % (Setup 1.72 %,
  the pump's own cost). No polling: S5 asserts no active timer.

---

## All files touched in 9a

- `blastlab/ui/chain_route.py` (new), `chain_pipeline.py` (new),
  `chain_stage.py` (new), `chain_panel.py`, `case_form.py`,
  `setup_tree.py`, `setup_panel.py`, `components.py`, `theme.py`,
  `topbar.py`, `app.py`.
- `blastlab/tests/test_ui_char_chain_wiring.py` (new),
  `char_golden/ui_chain_wiring.json` (new), `test_ui_chain_screen.py`
  (new), `_e2e_ui_chain_screen.py` (new), `test_ui_chain.py`,
  `_qa_ui_harness.py`, `_e2e_ui_chain.py`, `_e2e_ui_chain_foam.py`.
- `docs/gui-redesign-decisions.md` (D131-D154, F18-F22),
  `docs/qa/2026-09-29-gui-chain/` (measurements-9a.md, measure-9a.json,
  28 PNGs), this report.

## GUI screens touched

- **Chain** (all of it). The top bar's Chain link text follows the route.
- **01 Setup** only through the additive parameters: its pill text, tree
  footer and hand-off card defaults are unchanged; the light-mode fill of
  `HandoffCard` changed (D152), and only the Chain uses that card.

## Numerical changes

None.

## Decisions and findings added

- D131-D146: the plan's recommended defaults 1-16, as built (D138 and D143
  amend the plan's rows 8 and 13; see below).
- D147-D154: new — the first stage selected (stage 1, C1 pins it); the
  two-line centre header; the refusal line's place; checks deferred off
  screen; pipeline widths; light-mode contrast; board heights; wrapped
  paths.
- Amended plan rows: **row 8 (seeding)** — the seed is the Setup *case*,
  so a native Setup seeds TNT (the native rule of `models/fields.py`);
  **row 13 (hand-off texts)** — the 2D out-text names the trigger gauge for
  every trigger action, because the code writes the hand-off at the
  stage's end holding the stop instant (terminate) or the trigger instant
  written over it (remap).
- F18 (planner's; fixed in T1), F19 (the stale T0 message), F20 (the
  stale worktree record of GUI-6a), F21 (Setup's 26 px pill and + buttons),
  F22 (harness `wait_log` race).

## Suspected engineering issues (not changed)

- None in the numerics. The native rule that a native case always carries
  material TNT (UX-E2, "keep") means a C4 typed on a native stage is not
  what runs; the Chain inherits that behaviour from the form engine.

## Left for 9b and later

- 9b (T4-T6): the chain strip in 02 Run, one Results entry with stage tabs,
  `_e2e_ui_chain.py` X4 / `_e2e_ui_chain_foam.py` C4, the viewer sampler
  actions, G02 and the rest of §10; its decision rows (the plan's 17-23)
  continue after D154.
- GUI-10: F8, F21, F22 (and the earlier F-rows).
- Process note: one scratch file (the contrast script, never in the repo)
  was edited once through a heredoc'd Python one-liner rather than a
  script file; every repo file went through Edit / Write.
