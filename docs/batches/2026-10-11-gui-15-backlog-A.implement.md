# GUI-15 Part A - implementation report

Worktree `blastlab-worktrees/gui-15`, branch `gui-15`, base `4d3513e`. All four tasks DONE.

## Tasks

### A1 - GUI-15 (a) - DONE - `48a2784`
`run_gauges.pre_payload(case, rule)` splits the entered gauges into kept and dropped with
`sd.is_dropped`. `rows(case, None, rule)` leaves the dropped ones out, numbers the kept ones 1..k
and labels them `G<entered>`. `GaugeColumn.set_case` builds `drop_rule(case)` once and `_render`
sets the drop line from the same rule before any payload. `_geometry` passes the rule's wall to
`sd.where`, as `where_text` does. Files: `ui/run_gauges.py`, `tests/test_ui_run_screen.py`.
Test: `python test_ui_run_screen.py` (225 checks PASS) and gate `--changed HEAD`.
- AC1 PASS: e2e case plus a kept G3 - before a payload the rows are G1, G3, the drop line names G2
  and Wall 1, the card is G1; after a payload the card and order are unchanged.
- AC2 PASS: GUI-14 A1 tie fixture - the drop line names Wall 1, no row header names Wall 2.
- Pin edit (not named in the plan, forced by D1): `test_ui_run_screen.py` R5b "before a payload:
  G1 G2 G3 by Z, no note" now expects G3, G1 and the note. Same meaning change the plan asks for.

### A2 - GUI-15 (e) - DONE - `9713ad0`
`scaled_distance.dropped_numbers(case)` (one `drop_rule`); `any_dropped` is now built on it.
`setup_nodes.summaries` inserts ` · G2 dropped` before ` · trigger Gn`. `_ChildRow` takes `warn`
(marker and name get the `warn` colour through a `warn` property rule in `theme.py`);
`set_children` accepts `(name, value[, warn])` and its no-flicker compare includes the flag. Setup
and `chain_stage` compute the dropped numbers once and pass them to `_sync_children` and the
node status. Files: `ui/setup_nodes.py`, `setup_tree.py`, `setup_panel.py`, `chain_stage.py`,
`theme.py`, `scaled_distance.py`; tests in `test_ui_setup_strip.py`, `test_ui_chain_screen.py`.
- AC1 PASS: e2e fixture caption `2 gauges · G2 dropped`, G2 child warn and G1 not (Setup); a chain
  stage's G1 (x outside) warn with the caption; both clear when moved.
- AC2 PASS: pins `test_ui_setup_strip.py:645-653`, `test_ui_setup_tree.py:361` unchanged;
  setup_strip (142), setup_tree (260), chain_screen all exit 0.

### A3 - GUI-15 (c) - DONE - `e66a6c1`
`run_gauges.drops(case)` returns `[[n, reason], ...]`. `RunController.start_stages` keeps it per
stage and stamps it into `res.meta['gauges_dropped']` on the `'result'` tag (only when non-empty,
memory only). `results_gauges.labels_and_dropped` uses the stamped reason when present. Files:
`ui/run_gauges.py`, `run_controller.py`, `results_gauges.py`; tests in `test_ui_results_screen.py`
and `test_ui_drain.py` (T5b, a real tiny native 2D run).
- AC1 PASS: D5 near fixture - without the key `inside Wall 1`, with it Results equals Run's
  `dropped_text` (`G2 dropped by the solver (on the face of Wall 1)`), also on screen. Without the
  key the text is unchanged.
- AC2 PASS: native 2D through `start_stages`: `meta['gauges_dropped'] == [[2, 'inside Wall 1']]`.
  `test_ui_results_screen.py` (231 checks) exits 0.

### A4 - GUI-15 (h) - DONE - `4863c9d`
Module-level `skip_reason(sid, group, solver_seed)` in both harnesses. `main()` records F scenarios
as `status='skipped'` (reason in `err`) under `--solver native`, so they are not pending and
`--list` shows `skipped`. `_foam_run` returns False with a note first. Files:
`tests/_qa_ui_harness.py`, `tests/_qa_gui_harness.py`. Harnesses not run.
- AC1 PASS: scratch script `skip_reason('F05','F','native')` non-empty; `blastfoam`, `None`, and
  `('B06','B','native')` give `''` (both modules).
- AC2 PASS: `--list --solver native --out <scratch>` exits 0 in both; F00-F11 show `skipped`,
  pending 68 (Qt) / 59 (Tk) against 80 / 71 with `--solver blastfoam`.

## Closing matrix
- `gate.py --changed 4d3513e`: 19/19 suites green (10.7 min).
- `gate.py --only regression`: byte-for-byte PASS (last).
- App starts (offscreen MainWindow, private settings; section 8.2 dry run printed `False`).

## Files touched
`ui/run_gauges.py`, `run_controller.py`, `results_gauges.py`, `setup_nodes.py`, `setup_tree.py`,
`setup_panel.py`, `chain_stage.py`, `theme.py`, `scaled_distance.py`; tests `test_ui_run_screen.py`,
`test_ui_setup_strip.py`, `test_ui_chain_screen.py`, `test_ui_drain.py`, `test_ui_results_screen.py`,
`_qa_ui_harness.py`, `_qa_gui_harness.py`.

## GUI screens touched (for QA)
Run (gauge list from Start, drop line, enlarged card), Setup tree (Gauges caption and child rows),
Chain stage tree (same), Results Gauges (drop line wording after a run through Run).

## Numerical changes
None.

## Notes for the verifier / owner
- `test_ui_run_screen` R5b pin edit above; with a drop the pre-payload card is the lowest-Z kept
  gauge, not the trigger-less first entered one (D1 says "enlarged card is G1" for the e2e case,
  which holds).
- A pre-payload gauge that `drop_rule` cannot lay out (1D, no obstacles, unparsable) is kept, as
  before; 1D is B5.
- `--scenario F07 --solver native` is also skipped (the flag wins over an explicit scenario).
  Recommendation: keep; QA's F07 pass uses `--solver blastfoam`.
- The stamp is only written when non-empty, so a no-drop Result carries no key; B5 relies on that.
- Pre-existing: the drop warning in Setup/Results still says `on the face of` until B1.
