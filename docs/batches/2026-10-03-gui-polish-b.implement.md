# GUI-11 part 11b — implementation report (T7-T9)

Batch plan: `docs/batches/2026-10-03-gui-polish.md`, part 11b only.
Branch `gui-redesign`, from `2753eb6` (11a done and verified). One
commit per task, plus one small `ui:` commit for T7's badge half, then
this report. 11c and 11d are later runs.

Before starting:
- CLAUDE.md §8.2 dry run: `auto_cleanup` reads `False`.
- Baseline: `test_case_validate` PASS.
- Working tree: only the never-stage paths were dirty. None was staged.
- No WSL step was needed (the T8 blastFoam question was answered from
  the writer's code), so no WSL command was run.

---

## T7 · F28 (GUI-11 c): a stage start forgets the last stage's progress — DONE

**What was done.** `GuiHooks.run_started` sets `_last_p = None` inside
its existing `with self._lock:`. That is the one line in
`solvers/worker.py`, in its own commit (D209). On the real platform a
second, UI-side leftover showed up: the held stage read
`PAUSED at step 201` and `held at step 201`. These come from
`RunPanel._last_step`, which `on_run_started` did not reset. That line
went into a separate `ui:` commit (D217), so the `solvers/` commit
stays one line.

**Files:**
- `blastlab/solvers/worker.py` (one line);
- new `blastlab/tests/test_worker_stage_progress.py` (no Qt);
- `blastlab/ui/run_panel.py` (one line, D217);
- `blastlab/tests/test_ui_chain_screen.py` (a new F28 check beside F27);
- `docs/qa/2026-10-03-gui-polish/gui11-f28-held-stage2.png` (after) and
  `gui11-f28-held-stage2-before.png` (before T7).

**Tests:**
- `cd blastlab/tests && python test_worker_stage_progress.py` (7
  checks). W1 posts step 201, then `run_started`, then
  `flush_progress`. W2 holds the real `step_gate` on a thread. W3
  checks that stage 2's own progress still flushes.
- `python test_ui_chain_screen.py`: the F28 check. It fails without
  D217's line, reading `'PAUSED at step 201'`.

**The probe without the line** (the unmodified `worker.py`, run before
the edit; output kept in the session scratchpad):

```
[FAIL] after run_started the queue holds no progress with step 201 [('run_started', None), ('progress', 201)]
[FAIL] no progress with step 201 after run_started while held [('run_started', None), ('progress', 201), ('paused', None)]
WORKER STAGE PROGRESS: FAIL (2)
```

**Criteria**
- PASS. The new test passes, and fails without the line (above).
- PASS. `test_regression` is byte-identical: run after T7, and again
  last.
- PASS. `test_ui_chain_screen` is green: 196 checks with S7, then 197
  with the F28 check. `test_ui_run_screen` is green (194).
- PASS. Real platform: `_e2e_ui_chain_screen.py` passes (23).
- PASS. A held chain's stage-2 shot shows `—`, not `STEP 201`.
  - The probe is a native 1D → 2D chain from the Chain screen, with
    Pause in force as stage 2 starts. It is the state a user reaches by
    stepping stage 1 to its end with Exec 1.
  - STEP, TIME and P MAX read `—`, the percent `0 %`, and the strip
    `02 2D 0 %`.
  - Before T7: `201`, `0.300 ms`, `1,246 kPa`, `100 %` and
    `02 2D 100 %`.
  - After D217 the badge reads `PAUSED` and the time line `held · 1 s
    elapsed`.
  - The window was visible according to Win32 `IsWindowVisible`.

**Commits:** `bd8878d` (`solvers:`, the one line), `65c741f` (`ui:`,
D217).

## T8 · UXR-2: a gauge inside an obstacle is warned, and keeps its number — DONE

**The blastFoam question, answered first** (from the code; no WSL
solve):
- `solvers/foam/writer.py` (`_in_obstacle2` for 2D, `_in_obstacle` for
  3D) drops such a gauge before it writes the probes, with no log line.
- It drops it from `spec.obstacles`: the boxes snapped outward onto
  base-cell faces (`core/refine.snap_obstacles`), tested closed
  (`<=`).
- So blastFoam drops a gauge strictly inside the box, and the warning
  text has **no** "the native solver drops it" tail.
- blastFoam also drops a gauge on a face, or within the outward snap
  margin of up to one base cell. Natively, the nearest-cell rule
  (`solver2d.py` / `solver3d.py`, gauge setup) can drop a gauge within
  half a cell of a face.
- **That half-cell / snap zone is not predicted** by the new warning,
  as the plan says.

**What was done**
- **Validation** (`services/validation.py`, `_validate_closing` and a
  new helper `_in_obstacle_open`): a gauge strictly inside an obstacle
  box (the open-box test of `scaled_distance.where`) warns
  `Gauge (1.4, 0.3) inside an obstacle - will be dropped`.
  - It is a warning, so the case stays valid.
  - The Chain stage checks and the Tk app get it through
    `validate_case`.
- **On screen:** new toolkit-free `run_gauges.numbering(case,
  gauge_out)`, built on `match_gauges`.
  - When the solver dropped a gauge, the 02 Run live column and the 03
    Results Summary table (and its readout) label each row with the
    **entered** number.
  - The captions name the dropped gauge:
    `G2 dropped by the solver (inside Wall 1)`.
  - A drop is named only when the count adds up. Otherwise, and
    whenever nothing is dropped, every label is the payload number, as
    before. So no golden moved.
  - Row keys, the selection, `rows()`, the headers and every export
    are unchanged (D201, which amends D61).

**Files:**
- `blastlab/services/validation.py`;
- `blastlab/ui/run_gauges.py`, `blastlab/ui/results_gauges.py`. The
  Gauge header's help text now says "as entered in Setup";
- `blastlab/tests/test_case_validate.py`, `test_ui_run_screen.py`,
  `test_ui_results_screen.py`;
- `docs/qa/2026-10-03-gui-polish/gui11-dropped-gauge-checks.png`.

**Tests:**
- `python test_case_validate.py`: 22 new checks, in 2D and 3D, native
  and blastFoam.
- `python test_ui_run_screen.py`: R5b, 7 checks, 201 in all.
- `python test_ui_results_screen.py`: S5g, 6 checks, 192 in all.

**Criteria**
- PASS. `test_case_validate`: a gauge inside Wall 1 gets **exactly**
  the new warning, compared with the same case without the gauge.
  - 2D gives `Gauge (1.4, 0.3) inside an obstacle - will be dropped`.
  - 3D gives `Gauge (1.6, 1.0, 0.5) inside …`.
  - The errors are unchanged.
  - A gauge on a face, on the top face, in front of, above or behind
    the box gets none.
  - All of this holds for both solvers.
- PASS. `test_char_validation` is green **unedited**. No golden case
  changed.
- PASS. `test_ui_results_screen` S5g, on a fixture with three entered
  gauges, the second inside Wall 1, and two payload points:
  - the cells read `G3` then `G1`;
  - the caption reads `G2 dropped by the solver (inside Wall 1) ·
    click a row to plot it · …`;
  - `rows()` equals `table_rows(summary_rows(res))`, and the headers
    are unchanged;
  - the keys stay `[2, 1]`, and the readout reads `G3 · Z 2.99`.
- PASS. `test_ui_run_screen` R5b, the same in the live column:
  - the labels read `G3`, `G1`;
  - the caption reads `… Click a row to enlarge it. G2 dropped by the
    solver (inside Wall 1).`;
  - the card reads `G3`, and the keys stay D61's.
  - With nothing dropped, every label is `G<payload number>`.
- PASS. `test_ui_char_results_meta`, `test_ui_char_results_exports` and
  `test_char_exports` are green unedited.
- PASS. Real platform: the sample case with G2 moved into Wall 1, at
  (3.1, 1.0).
  - Checks tab: `Gauge (3.1, 1.0) inside an obstacle - will be
    dropped`, and the pill reads `Case OK · 2 warnings · 2 notes`.
  - Shot: `gui11-dropped-gauge-checks.png`. The window was
    Win32-visible.

Also green: `test_ui_results` (130), `test_ui_setup_strip` (110),
`test_ui_setup_tree` (238), `test_ui_setup_form`, `test_ui_no_vtk_in_main`,
`test_ui_no_mpl_pyplot` (19).

**Commit:** `f02f65a`.

## T9 · QA S2-1: the 1D hand-off radius is checked against the next stage — DONE, with one deviation

**What was done.** New toolkit-free `chain_route.handoff_reach(dims,
cases)`. `stage_checks` adds its result as a **warning** on the
receiving stage (D200).
- **When:** the stage before is 1D, its Outer boundary terminates it,
  and it has no End time. R = `radius_m`.
- **The rule** is the solvers' own remap warning:
  - 2D: R > Lx, cy − R < 0, cy + R > Ly, or an obstacle closer than R
    to (0, cy);
  - 3D: min(x0, Lx−x0, y0, Ly−y0, z0, Lz−z0) < R.
- **The texts** are the plan's two, with the largest R that stays
  silent as the suggested limit.
- No seed, default, wiring or `run()` refusal changed. Run chain stays
  enabled.

**Deviation from the plan: the End-time condition**
- `solvers/solver1d.py` (lines 130-133 and 214-216) stops at the End
  time when one is set, or at the shock's arrival at a terminating
  Outer, whichever comes first. With an End time, the hand-off radius
  is not known before the run. The plan's interpretation 4 limits the
  check to exactly the case where the radius is known.
- The plan's E3 case has stage 1 at R 1.0 m with End time 0.3 ms, into
  a 0.6 × 1.2 m stage. On the real platform it hands off at t = 0.300
  ms with the shock at **0.70 m** (`handoff_1d_to_2d.txt … t = 0.300
  ms`, and the run's own `[warn] … (0.70 m)`). So the plan's "beyond
  this stage's whole domain: this stage would start after the wave has
  left it" would have been **false** there.
- So `_e2e_ui_chain_screen` E3 is **not changed**: card 2 still reads
  `● case OK`, and the run passes its 23 checks.
- The default seed has End time 0 and R 10 m, and it warns as the plan
  says. S5r pins the End-time case.

**Files:**
- `blastlab/ui/chain_route.py`;
- `blastlab/tests/test_ui_chain_screen.py`;
- `docs/qa/2026-10-03-gui-polish/gui11-chain-handoff-warning.png`.

`test_ui_chain.py` needed no change (green unedited).

**Tests:** `python test_ui_chain_screen.py` (213 checks):
- S5r: 13 checks, without Qt;
- S5: 3 new checks.

**Criteria**
- PASS. `test_ui_char_chain_wiring` is green **unedited**.
- PASS. `test_ui_chain_screen` (213) and `test_ui_chain` (114,
  unedited) are green.
- PASS. Unit checks of `handoff_reach`:
  - **1 → 2, the QA case** (10 m, 4 × 4, cy 2) gives exactly `The 1D
    stage hands off when its shock is at 10.0 m, beyond this stage's
    whole 4.0 × 4.0 m domain: this stage would start after the wave has
    left it. Set stage 1's radius below 2.0 m.`
  - **1 → 2, the QA control** (1.5 m) gives nothing.
  - **A wall 1.2 m from the burst, at 1.5 m**, gives the second text,
    with `below 1.2 m`.
  - **1 → 2, 3 m** gives the second text. At exactly 2.0 m it is
    silent.
  - **1 → 3** (6 × 6 × 4, z 2): at 10 m the first text; at 2.5 m the
    second; at 1.5 m nothing.
  - **Nothing is said for:** 1 → 2 → 3 (only stage 2 is checked),
    2 → 3, Outer not terminating, an End time, and an unparsed stage.
- PASS. S5, on the default 1 → 2 → 3 seed with stage 1 at 10 m:
  - card 2 reads `● 1 warning`, and the pill `Stage OK · 1 warning`;
  - the message is in its Checks;
  - cards 1 and 3 read `● case OK`, and Run chain is enabled;
  - at 1.5 m the warning is gone.
- PASS. Real platform: `_e2e_ui_chain_screen.py` passes (23). The
  Chain shot of the default 1D → 2D route (`gui11-chain-handoff-warning.png`)
  shows:
  - `● 1 warning` on card 2;
  - `Stage OK · 1 warning`;
  - the message under CHECKS.
- Not met as written: the plan's E3 expectation (`● 1 warning`). The
  reason is the deviation above.

**Commit:** `1b1ed01`.

---

## The 11b close

**Tk gate** (CLAUDE.md §9; `solvers/` and `services/` changed). All 16
`test_gui_*` suites, one at a time, all rc 0 with no `[FAIL]`. CLAUDE.md
and the plan say "nine"; the folder holds 16.

| Suite | Result |
|---|---|
| `test_gui_amr_form` | PASS |
| `test_gui_char_case_form` | PASS |
| `test_gui_char_exports` | PASS |
| `test_gui_char_results_meta` | PASS |
| `test_gui_char_write_failure` | PASS |
| `test_gui_drain` | PASS |
| `test_gui_gauge_summary` | PASS |
| `test_gui_output_card` | PASS |
| `test_gui_refine_preview` | PASS |
| `test_gui_results_anim` | PASS |
| `test_gui_results_fields` | PASS |
| `test_gui_results_vtk_folder` | PASS |
| `test_gui_run_browser` | PASS |
| `test_gui_solver_mode` | PASS |
| `test_gui_status_cells` | PASS |
| `test_gui_title_preview1d` | PASS |

**Tk harness.** `python -u _qa_gui_harness.py --solver native --only
B,C,D,E,G,M,V,H,I`, on the real platform with its own scratch settings
(`~\blastlab_qa\gui11-b-tk`), re-invoked with `--resume` (6 passes).
- All 59 scenarios ended `done`, with no Tk callback exception.
- Group F (real blastFoam solves in WSL) was not run. Nothing in 11b
  touches the foam path beyond validation, which `test_foam_writer`
  and `test_case_validate` cover, and a WSL solve is too heavy for
  this 8 GB PC.

There were five S2 findings. Each was compared with a run at
`116ea96` (a temporary worktree, removed afterwards), and **all five
predate GUI-11**:
- **E03 (×4)**, `summary / tsv / fieldcsv / report export wrote …`:
  - The files were written, but under the harness's dialog interceptor
    prefix (`save1_gauges_2d_summary.csv`, …).
  - The check looks for the name without the prefix.
  - `--only D,E` gives the identical four findings at base
    (`gui11-b-tk-DE-base`) and at HEAD (`gui11-b-tk-DE-head`).
- **D05**, `stopped run labelled "(stopped)"`:
  - The evidence is `['QA - 3D (stopped)', 'QA - 3D (stopped) #2']`.
    An earlier scenario's stopped 3D run makes the second label `#2`.
  - It passes in the D,E-only runs at both commits.
  - `--only B,C,D` at base (`gui11-b-tk-BCD-base`) gives the same
    finding with the same evidence.
- These are harness expectations, not app regressions. A harness fix
  is for a later QA batch.

**Shared suites**, one at a time, all rc 0 with no `[FAIL]`:
- `test_case_validate`;
- `test_char_validation` (unedited);
- `test_char_case_json`;
- `test_foam_writer`;
- `test_blast2d`;
- `test_blast3d`.

**Qt suites touched**, all rc 0:

| Suite | Checks |
|---|---|
| `test_ui_chain_screen` | 213 |
| `test_ui_chain` | 114 |
| `test_ui_run_screen` | 201 |
| `test_ui_results_screen` | 192 |
| `test_ui_run_panel` | PASS |
| `test_ui_results` | 130 |
| `test_ui_setup_strip` | 110 |
| `test_ui_setup_tree` | 238 |
| `test_ui_setup_form` | PASS |
| `test_ui_no_vtk_in_main` | PASS (after T9) |
| `test_ui_no_mpl_pyplot` | PASS (after T9) |
| `test_ui_char_chain_wiring` | PASS, unedited |
| `test_ui_char_results_meta` | PASS, unedited |
| `test_ui_char_results_exports` | PASS, unedited |
| `test_char_exports` | PASS, unedited |
| `test_worker_stage_progress` | 7 |

**Real platform:**
- `_e2e_ui_chain_screen.py`: 23 checks, after T7 and again after T9;
- the scratch probes (not committed): the held chain (T7), the Checks
  tab (T8) and the Chain warning (T9);
- `ui.app.main()` started once with throwaway native settings: the
  `windows` platform, the window Win32-visible on 01 Setup, and main
  returned 0.

**Regression, last.** `test_regression` **PASS**, byte-identical:
seven files byte-identical, and `b2_profile.npz` arrays equal. No
baseline file shows as modified in `git status`.

**Frozen paths.** `git diff 116ea96..HEAD` over the plan's frozen list
shows only:
- `blastlab/solvers/worker.py`, 1 line (D209);
- `blastlab/services/validation.py`, 23 lines (D201).

`blastlab/gui/`, `core/`, `models/`, `output/` and `viz3d/` are
untouched, and so are `view3d_host.py`, `run_controller.py`,
`viewer_link.py`, the baselines and every golden.

**Never-stage list.** None of the seven paths is in any 11b commit.
Every commit was staged by explicit path.

## Changed committed assertions (plan §"Committed tests")

1. **`test_ui_chain_screen` S5.** Before its first check (`all three
   cards start ● case OK`), S5 now sets stage 1's radius to the board's
   1.5 m.
   - Reason: the default seed now warns on card 2 (T9). This is a
     fixture change, so the error-path checks test what they tested.
   - No check was removed or weakened. The default seed's warning is
     asserted separately, just before.

There are no other changed assertions. Everything else is new checks:
- `test_worker_stage_progress` (new suite, 7);
- `test_ui_chain_screen`: F28 (1), S5r (13), S5 (3);
- `test_case_validate` (22);
- `test_ui_run_screen` R5b (7);
- `test_ui_results_screen` S5g (6).

`_e2e_ui_chain_screen` E3 is unchanged (see T9's deviation).
`test_ui_char_chain_wiring`, `test_ui_char_results_exports`,
`test_ui_char_results_meta`, `test_char_exports`, `test_char_validation`
and `test_ui_char_hd13_run` are unedited.

## All files touched in 11b

- `blastlab/solvers/worker.py`
- `blastlab/services/validation.py`
- `blastlab/ui/run_panel.py`, `run_gauges.py`, `results_gauges.py`,
  `chain_route.py`
- `blastlab/tests/test_worker_stage_progress.py` (new),
  `test_ui_chain_screen.py`, `test_case_validate.py`,
  `test_ui_run_screen.py`, `test_ui_results_screen.py`
- `docs/qa/2026-10-03-gui-polish/`: `gui11-f28-held-stage2.png`,
  `gui11-f28-held-stage2-before.png`, `gui11-dropped-gauge-checks.png`,
  `gui11-chain-handoff-warning.png`
- `docs/gui-redesign-decisions.md`: D200, D201, D209, D217, F42, F43,
  and the Outcome on F28
- this report

## GUI screens touched (for QA)

- **02 Run, a chain held at a stage start:** the tiles read `—`, the
  percent `0 %`, the badge `PAUSED` and the time line `held · …`.
- **02 Run, live gauges:** after a dropped gauge, the rows carry the
  entered numbers, and the caption names the dropped one.
- **03 Results ▸ Gauges:** the same in the Summary table, the readout
  and the caption (note first). The Gauge header's tooltip text
  changed.
- **01 Setup ▸ Checks, the Chain stage Checks and the Tk app's
  validation:** the new `inside an obstacle` warning.
- **Chain:** a hand-off reach warning on the receiving card, its pill
  and its Checks.

## Numerical changes

None. No solver value, solver default, case key, file format, export
byte or hand-off file changed. `test_regression` is byte-identical (run
after T7 and last). T7 changes which queued Progress is re-posted, not
any value. T8 and T9 add warnings and display labels.

## D / F rows added

In `docs/gui-redesign-decisions.md`:
- **D200** (T9), with the End-time deviation;
- **D201** (T8, amends D61);
- **D209** (T7);
- **D217** (new, T7's badge half; the next free number after D216);
- **F42:** after a dropped gauge, `output/gauge_summary.gauge_labels`
  pairs entered positions with the snapped ones **by index**. With G2
  dropped, G3's exported label reads `G2 (1.200, 0.600) -> cell (2.975,
  1.525) m`. This is in the exported Summary .csv / report and the
  Gauge cell's tooltip. It predates GUI-11 and is not fixed, because
  the exports are pinned (owner call).
- **F43:** the finish notification's `Highest peak: G<n>` still numbers
  by payload order.
- **The Outcome on F28.**

D210-D215 stay reserved for 11c / 11d.

## Suspected engineering issues noticed, not changed

1. **F42, the more serious one.** A design calculation that reads the
   exported Summary .csv of a run with a dropped gauge gets wrong
   positions beside the later gauges' numbers. D201's Setup warning is
   the guard until the owner decides.
2. **blastFoam drops gauges silently.** blastFoam drops a gauge on or
   near an obstacle face (the outward snap, a closed test) with no log
   line, while the native solver logs its drops. The new warning
   covers only "strictly inside". This is recorded in D201.
3. **F43.** The finish notification can name a different G than the
   screens after a drop.

## Open questions for the owner

- **D200's End-time condition.** It departs from the plan's E3
  expectation; see T9. Is warning only when the hand-off radius is
  known the reading you want? The alternative would need the shock
  position at the End time, which is a blast calculation GUI-11 does
  not make.
- **F42.** Should the exported labels pair by match, which changes
  export bytes for runs with a dropped gauge?
