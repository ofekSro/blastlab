# GUI-12 Part B - implementation report

Branch `gui-12`, base HEAD `a946b71`. Commits `5ef5f4e`, `c66a12f`, `5ab203e`.

## B1 - DONE - `5ef5f4e`
`chain_route.handoff_reach` now handles prev = 2, d = 3 through `_burst_above_3d`: warns when
the 2D `center[1]` is at or above the 3D `Lz` (text as in the plan). Warning only; `run()`
and the seed unchanged. Files: `blastlab/ui/chain_route.py`, `blastlab/tests/test_ui_chain_screen.py`,
`docs/qa/2026-10-04-gui-12/b1-chain-stage3-1100x720.png`.
Tests: `python test_ui_chain_screen.py` (230 checks PASS).
- Criterion 1 PASS: default seed warns on card 3 (`1 warning`, line in Checks); `Lz` 2.5 m silent;
  plus text, boundary (at Lz warns) and None-stage checks in S5r.
- Criterion 2 PASS: the 1D to 2D / 3D reach checks are unedited. Three existing S5 checks
  (cards 1 and 3 do not warn / all three cards start case OK) failed because the default seed
  now warns on card 3 by design. Edited: the first no longer claims card 3 is clean; the other two
  pass unedited because the new F45 check sets Lz to 2.5 m first (same idea as the existing
  1.5 m radius fixture step). Please confirm that fixture edit.
- Criterion 3 PASS: real platform, 1100 x 720, stage 3 selected, Checks scrolled into view:
  the line wraps in three rows, unclipped (screenshot above).

## B2 - DONE - `c66a12f`
`_qa_gui_harness.py`: the dialog stub stores its last answer (`qa.last_answer`); E03 checks
that path; the field-CSV export (answers a directory) checks `*p_peak.csv` inside it.
Cause: the app prefixes the suggested name with the model name (`QA_`; the plan called it
`save1_`). Command: `_qa_gui_harness.py --only D01,D02,E03` (E03 alone has no cached 1D/2D results
in a fresh output folder, so its buttons are disabled; that is a harness dependency, not new).
- Criterion 1 PASS: exit 0, `findings.jsonl` empty, four exports checked at the paths written.

## B3 - DONE - `5ab203e`
`ui/results_fields.py`: the 1D canvas tooltip `Exports use the full title: <title>` is read back
from the builder's axes title before the on-screen title replaces it; cleared on 2D/3D views.
`screen_title_1d` docstring lists the three styles. Tests: two new S6b checks in
`test_ui_results_screen.py` (220 checks PASS).
- Criterion 1 PASS: tooltip contains the exported string (also with a user title).
- Criterion 2 PASS: `test_ui_char_results_meta`, `test_gui_char_results_meta` unedited, green.

## Closing matrix
`test_ui_chain_screen`, `test_ui_run_screen`, `test_ui_results_screen`, `test_ui_char_results_exports`,
`test_ui_char_results_meta`, `test_gui_char_results_meta`, `test_case_validate`: PASS.
`test_regression.py` last: PASS (byte-identical). App constructs (MainWindow built in every suite and the screenshot script).

## Summary lists
- GUI screens for QA: Chain stage 3 Checks (default seed warning); Results 1D Field tooltip.
- Numerical changes: none.
- Engineering issues: the default chain now opens with a warning on stage 3 and stage 2 (seed:
  2D burst z 2.0 m vs 3D Lz 1.5 m). Owner chose warning-only, default unchanged.
  `git commit` prints `failed to delete .git/worktrees/gui-12-probe: Permission denied` (a stale
  probe worktree entry from Part A; commits succeed).
- Open questions: (1) reseed the 3D box to Lz 2.5 m to silence the default warning? Recommend no
  until the owner decides, as instructed. (2) Fixture edit in S5 as above.
