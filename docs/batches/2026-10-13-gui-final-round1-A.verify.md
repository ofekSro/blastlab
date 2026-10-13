# gui-final-round1 Part A - verify report

## R1 - VERIFIED
- Acceptance 1 (Stop in stage 2 blockMesh / between stages ends Stopped, caption, bar 0 %): the two new
  checks in `test_ui_chain_screen.py` pass in the gate.
- Acceptance 2 (control: 3 results + late Stop = Done): passes in the gate.
- Acceptance 3 (live blastFoam 1D->2D chain, Stop after stage 1): run with a scratchpad script
  (offscreen window, throwaway settings, real WSL). Stage 1 result at 18.9 s, Stop clicked, log
  `[stopped during 'blockMesh']`; time line `Stopped after 19 s ...`, percent tile `0 %`, bar 0. PASS.
  Pre-checks: cleanup dry run `auto_cleanup False`; `pgrep -a blastFoam` empty.
- Diff read (02e7fb0..cdbce68): no number or sign changes, no swallowed errors, no off-thread widget
  access; `reset_bar` only on the GUI thread via `on_finished`. The new tests fail without the fix (the
  implementer saw them red before it).
- Gate: `gate.py --changed 02e7fb0`: 25/25 suites green (13.7 min). `--only regression` not run: the diff
  touches only `ui/` and one UI test, no numerics.

Defects: none. Engineering questions: none. Fixes: none.
Note: the live Stop left WSL scratch `/root/blastlab_runs/20261013-191411_2d_p26396-01` (kept by design for
a stopped run; rules forbid deleting it).
GUI screens for QA: Run tab (Stop during a chain, bar and banner), Chain strip.

## Status

- R1 GUI-16: VERIFIED
