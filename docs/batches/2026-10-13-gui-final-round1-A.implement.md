# gui-final-round1 Part A - implement report

## R1 - DONE
A chain Stop in a later stage now ends `stopped`. `ui/app.py`: new `_run_n_results` (reset where
`_run_got_result` is, counted in `on_result` only while `_running_ui`); `on_finished` calls a run
`stopped` when `stopped_early`, or `_stop_asked` and fewer than `max(1, _chain_n)` results (D-R4). When
the Stop landed between stages (no stage in flight, not `stopped_early`), `RunPanel.reset_bar()`
(`ui/run_panel.py`) empties the bar so stage 1's 100 % does not stand. A Stop in stage 2's blockMesh
already shows 0 % (`on_run_started` resets).

Files: `blastlab/ui/app.py`, `blastlab/ui/run_panel.py`, `blastlab/tests/test_ui_chain_screen.py`.
Tests: `python .claude/skills/neat/gate.py --changed HEAD`: 21/22 green; the one red,
`test_ui_chain_screen`, exited 0xC0000005 while two gate runs overlapped (my mistake); rerun alone
`python blastlab/tests/test_ui_chain_screen.py` exit 0, all checks PASS. Earlier gate run (before
the between-stages bar fix) was 20/21, with the new check red, as expected.
`test_ui_run_screen` and `test_ui_drain` green in the gate.

- Acceptance 1 (Stop in stage 2 blockMesh and between stages: `Stopped after`, strip caption
  "Chain stopped at stage N of 3", bar `0 %`): PASS, two new checks.
- Acceptance 2 (control, 3 results + late Stop = `Done in`, `Chain done in`; gate green): PASS.
- Acceptance 3 (live blastFoam repro): not run, the verifier's job (needs WSL).
Commit: see git log (`ui: ... (GUI-16)`).

## Summary
- GUI screens for QA: Run (Stop during a chain, bar and banner), Chain strip.
- Numerical changes: none. Open questions: none.
- Engineering note: do not run two `gate.py` at once on this PC (an access violation resulted).
