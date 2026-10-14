# Batch gui-final-round2, Part A - implement report

Base `63d66e1`, branch `final-gui`. Commits `187f832`, `b9775cf`, `9c8b723` (never pushed).
Tasks A1, A2, A3, A5 share one commit (`9c8b723`): `app.py`, `run_panel.py` and `run_controller.py`
carry hunks of all four, and `git add -p` is interactive. A4 and A6 have their own commits.

## Tasks

### A1 - DONE (`9c8b723`)
A later stage owns the Run screen from the worker's `stage` message.
- `run_controller._dispatch` forwards `stage` to `handlers.on_stage(k)`, guarded by `getattr`,
  because `test_ui_drain` handlers have none.
- `app.on_stage`:
  - does nothing for k == 0;
  - otherwise sets `_chain_k = k + 1` and `_run_pct = None`, empties the bar, and writes the time line
    `meshing|starting stage N · … elapsed`;
  - sets pill N to `meshing|starting`: foam stage -> `meshing`, otherwise `starting` (D-R7);
  - drops the percent from the title and adds `, meshing` to the Stop question.
- `on_run_started` after an announced stage does not count again and only calls
  `RunClock.restart_eta()`. D-R6 needed a separate ETA origin, so the stage time keeps counting from
  `stage()` while the ETA restarts. That is a new method in `ui/run_clock.py`, which the plan's file list
  did not name.
- `chain_strip.stage_started(k, value)` and `VALUE_SAMPLES += ('meshing', 'starting')`. The widest sample
  is still `59 min 59 s`, so no pill width moved.
- Criteria:
  - 1, new check `s7_round2` in `test_ui_chain_screen.py` (bar 0, no `left`, `_chain_k == 2`, pill 2
    `meshing`, Stop question names stage 2; native control; k == 0 no-op; ETA 10 s while stage time is
    22 s): PASS.
  - 2, gate green on `test_ui_chain_screen`, `test_ui_run_screen`, `test_ui_drain`: PASS.
  - 3, live blastFoam check: NOT RUN (verifier's).
- Deviation: R1's `reset_bar` branch in `on_finished` stays. R1's "between stages" check
  (`test_ui_chain_screen.py:1506`, unedited) has no `stage` message to reset the bar, so removing it
  fails that check. After A1 the branch is dead for the in-flight case, because
  `_chain_k > _run_n_results` there.

### A2 - DONE (`9c8b723`)
`_finish_notice`: when `how == 'stopped'`, the chain has more stages than results and the last result is
not `stopped_early`, the banner reads `stage K of N finished; stopped by user during stage K+1` and the
time line reads `stopped by user during stage K+1 of N` (D-R8). `show_finish(..., time_reason=None)` is
the new keyword. The method card keeps `stop_reason` verbatim.
- Criteria:
  - 1, new check: time line `Stopped after 5 s · stopped by user during stage 2 of 2`; no `end time reached`
    or `outer boundary`; strip `Chain stopped at stage 2 of 2`; pills `done`, `stopped`; native control
    keeps `stopped by the user`: PASS.
  - 2: PASS.
  - 3, live: NOT RUN (verifier's).

### A3 - DONE (`9c8b723`)
On the `folder` message with `kept_because == model_folder.KEEP_ALL_WHY` (and no notice), the controller
calls `handlers.notify('WSL scratch kept (Keep all fields): <posix>', 'info')`. `_LOG_TAGS` gets
`('[note]', 'muted')`. Nothing changed in `services/`.
- Criteria: 1 new check `r13_keep_all_note` in `test_ui_run_screen.py` (exactly one info row naming the
  path, no dialog; none for another or empty manifest; `[note]` muted, `[warn]` and `[error]` keep theirs):
  PASS. 2: PASS. 3, live: NOT RUN.

### A4 - DONE (`187f832`)
`run_gauges._SelectedCard.set_row`: the label anchors at `(-0.05, 0.5)` (to the right of the peak) when
the peak is in the left half of the time range, else `(1.05, 0.5)`.
- Criteria: 1 new `G2b` in `test_ui_live_gauges.py` (peak at 2 %: label 36..74 inside view 22..335.5,
  anchor < 0; peak at 80 %: anchor unchanged): PASS. 2 gate green: PASS. 3, screenshot: NOT RUN.

### A5 - DONE (`9c8b723`)
`chain_route.by_position(lines, stages)` rewrites `Stage <d> (<d>D): ` to `Stage <position> (<d>D): `.
It is applied in `chain_panel._refuse`, which covers the form-error, hand-off and validation lines. The
compat status line (`chain_panel._refresh_compat`) and the long-run dialog (`app._confirm_long_run`) also
number by position. `services/chain.py` is unchanged.
- Goldens: exactly `ui_chain_wiring.json:75` and `:83` changed (`Stage 3 (3D):` -> `Stage 2 (3D):`).
  `test_ui_char_chain_wiring` is green, so no other line moved.
- New checks (3) in `s7_round2`: route 1->3 renumbers, 1->2->3 and 1->2 keep every byte, 2->3 numbers 2D
  as stage 1.
- Note: the long-run dialog line changes from `Stage 2D:` to `Stage 2 (2D):` on every chain, not only on
  1->3. Q1 said the bytes were identical on 1->2 and 1->2->3. That held for the `Stage n (nD)` lines but
  not for this dialog. No test pins it (grepped `automatic stop`, `Long run`).

### A6 - DONE (`b9775cf`)
`_qa_ui_harness.py` (the foam stop check, formerly `:3197`) now uses
`re.search(r'\(stopped\)( #\d+)?$', labels[-1])`, with `import re` added. `py_compile` is OK. The harness
was not run (the QA stage runs it).

## Tests run
- Starting state: `gate.py --for <Part A UI files>` 24/24 green, 15.0 min.
- After the edits: `gate.py --changed HEAD` 24/24 green, 14.1 min. This includes `test_ui_chain_screen`
  (268 checks), `test_ui_run_screen` (235), `test_ui_drain`, `test_ui_live_gauges` and
  `test_ui_char_chain_wiring`.
- `gate.py --only regression`: byte-for-byte PASS (last).
- App start: `MainWindow` constructed and shown offscreen with private settings, OK.
- Not run, because they belong to the verifier or QA: live blastFoam checks, screenshots, the big harness.

## Files touched
`blastlab/ui/`: `app.py`, `run_controller.py`, `run_panel.py`, `chain_strip.py`, `run_gauges.py`,
`run_clock.py` (not in the plan's list), `chain_panel.py`, `chain_route.py` (these two for A5).
`blastlab/tests/`: `test_ui_chain_screen.py`, `test_ui_run_screen.py`, `test_ui_live_gauges.py`,
`_qa_ui_harness.py`, `char_golden/ui_chain_wiring.json` (2 lines).

## GUI screens touched (for QA)
- 02 Run during a chain's stage 2 mesh: bar, time line, title, pill, caption, Stop question.
- 02 Run after a Stop there: banner, time line, strip.
- The log and Messages with Keep all ticked.
- The enlarged gauge card with an early peak.
- Chain screen refusal dialogs and status line on route 1->3; the long-run dialog on any chain.

## Numerical changes
None.

## Layout pins
None changed. The pill width is set by `59 min 59 s`, and `meshing` and `starting` are narrower.

## Engineering issues and open questions
- Commit subjects of all three commits start with a BOM character (`Set-Content -Encoding utf8` in
  PowerShell 5.1). Amending is forbidden, so they stay. Recommendation: leave them. The text is
  readable, and a later squash fixes it.
- A1/A2/A3/A5 are in one commit instead of four (shared hunks). Recommendation: accept it.
- `RunClock` now has `_eta0`. Any caller that fakes a clock through `RunClock.now` is unaffected.
