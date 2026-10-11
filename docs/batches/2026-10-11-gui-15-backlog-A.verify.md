# GUI-15 Part A - verification (light)

Range 4d3513e..9763bab, worktree gui-15.

- A1 (a) VERIFIED. Diff read: pre_payload/rows/_geometry use the one drop_rule. Covered by the gate's test_ui_run_screen (new e2e and tie fixtures).
- A2 (e) VERIFIED. Caption ` · G2 dropped` before trigger; warn child rows via property rule; pins in setup_strip / setup_tree untouched and green.
- A3 (c) VERIFIED. Stamp in RunController 'result' tag, read by results_gauges; test_ui_drain T5b is a real native run.
- A4 (h) VERIFIED. `--list --solver native --out <scratch>`: F00/F05 show `skipped`, 68 pending; `--solver blastfoam`: F05 `-`, 80 pending. Harnesses not run.

Checks: `gate.py --changed 4d3513e` 19/19 green (10.8 min); `gate.py --only regression` byte-for-byte PASS.

Judgement on the flagged points:
- R5b pin edit: correct and required. D1 changes the pre-payload rows (G2 dropped, card by lowest Z); the old pin asserted the opposite. Meaning change is the one the plan asks for; new assertions pin the note, wall name and rows.
- `--solver native` also skips an explicit `--scenario F07`: accept (the F group runs blastFoam solves).
- `gauges_dropped` only when non-empty: accept; memory only, no file or number change.

Defects: none. Fixes: none. Engineering questions: none.
GUI screens for QA: Run gauge column (pre-start drop line, card), Setup and chain-stage Gauges caption and warn child rows, Results Gauges drop wording.

Verdict: Part A VERIFIED.
