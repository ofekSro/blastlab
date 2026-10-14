# Batch gui-final-round2, Part A - verify report

Light depth. Base `63d66e1`, HEAD `7442152` (commits `187f832`, `b9775cf`, `9c8b723`, `7442152`).
Checks run: `gate.py --changed 63d66e1` 24/24 green (14.0 min); `gate.py --only regression` byte-for-byte PASS
(last); live runs on the real platform (`QT_QPA_PLATFORM` unset, platform `windows`, `__main__` guard).
§8.2 dry run: `auto_cleanup False` before the live runs. `pgrep -a blastFoam` empty before and after both runs.
No fixes were needed.

## Tasks

- **A1 VERIFIED.**
  - Gate: `test_ui_chain_screen`, `test_ui_run_screen` and `test_ui_drain` green, with round 1's R1 checks.
  - Diff read: `on_stage` is a no-op for `k <= 0`, so a single run is unchanged. `_chain_k` moves once, because
    `on_run_started` skips `+= 1` after an announced stage.
  - Live, blastFoam 1D -> 2D (stage 2 = 5 x 5 m at 4 mm, so a long blockMesh), screenshot `A1_mesh.png`
    (scratchpad). During stage 2's mesh:
    - `0 %`, bar 0, time line `meshing stage 2 · 19 s elapsed` (no `left`);
    - pill 2 `02 2D meshing`, pill 1 `done`;
    - caption `Stage 2 of 2 · the last stage`;
    - title `Chain 2/2 · …`.
  - The Stop question was not shown live: the run was under `STOP_CONFIRM_S`. It is pinned by the A1 unit check
    (`s7_round2`, which I read).
  - Cosmetic, not A1: the live slice plot and the TIME/STEP tiles still show stage 1's last frame during stage 2's
    mesh. That is outside U1/F-3 and the plan.
- **A2 VERIFIED.** Live Stop in stage 2's mesh (`A2_stopped.png`):
  - time line `Stopped after 30 s · stopped by user during stage 2 of 2`;
  - banner `Result ready: VER_A1 · stage 1 of 2 finished; stopped by user during stage 2.`;
  - strip `01 1D ✓ 14 s` / `02 2D stopped` / `Chain stopped at stage 2 of 2`. The stage-1 ending is gone.
  - The native control is in `test_ui_chain_screen` and green.
- **A3 VERIFIED.** Live 1D blastFoam with Keep all: Messages has exactly one `info  WSL scratch kept (Keep all
  fields): /root/blastlab_runs/…` row. No modal dialog (`show_info` / `show_error` hooks recorded none). The log has
  the `[note]` line. `r13_keep_all_note` is green.
- **A4 VERIFIED.** Live enlarged card (`A4_card.png`): `0.52 ms` is whole, and its anchor is `(-0.05, 0.5)` (peak in
  the left half). The label's horizontal extent lies inside the view box (44..92 against 24..275). Its box overhangs
  the top by about 4 px (padding at an auto-scaled peak), and the text is not clipped. The unit check `G2b` is green.
  The `0.09 ms` case is covered by that check; the live peak was `0.52 ms`.
- **A5 VERIFIED (judged).** Q1 asked for `Stage <position> (<d>D)`, used by `chain_panel._refuse`, the compat line
  and the long-run dialog (`app.py:1122` in the plan).
  - The long-run dialog was `Stage 2D:`, which is not that format. It is now `Stage 2 (2D): `, which is the plan's
    format. The plan names this dialog as a user of the format, so I judged it correct and left it.
  - Q1's "bytes identical on 1->2" held for the `Stage n (nD)` lines but not for this dialog line. Nothing pins the
    dialog (the implementer grepped and the gate is green).
  - Engineering note, not a defect: the owner approved "re-record exactly two golden lines". The dialog line is a
    third visible change, though no golden holds it.
  - Goldens: `git diff` shows exactly `ui_chain_wiring.json` `:75` and `:83` moved, `Stage 3` -> `Stage 2`.
    `test_ui_char_chain_wiring` is green.
- **A6 VERIFIED.** The `_qa_ui_harness.py` regex accepts `( #\d+)?$`, and `import re` is added. It compiles. The
  harness was not run (the QA stage runs it).
- **`RunClock.restart_eta()` (outside the file list).** Read in full: it is a small addition that only moves the
  ETA origin (`_eta0`, `_eta_held0`).
  - `stage_s()` is untouched, and `eta_s` now uses the solve time from `_eta0`.
  - `start()` and `stage()` set `_eta0` too, so a single run and a native chain give the same ETA as before.
  - A hold during the mesh is subtracted correctly. The unit check pins ETA 10 s while stage time is 22 s.
  - Accepted, with no fix. It is the minimal way to meet D-R6, and the touch is in a `ui/` file, so Part A stays Qt-only.

## Defects

None found in scope. Low, not fixed (out of the plan): stage 1's last live frame and tiles stay up during stage 2's
mesh (see A1).

## Engineering questions

- The long-run dialog now reads `Stage 2 (2D):` on every chain (A5). It follows the plan's format. Say if you want the
  old `Stage 2D:` kept on 1->2 and 1->2->3.
- The three Part A commit subjects begin with a BOM, and A1/A2/A3/A5 share one commit (both are in the implement
  report). Left as they are, since amending is forbidden.

## GUI screens that need QA

02 Run in a chain's stage-2 mesh and after a Stop there; the log, Messages and the `[note]` colour with Keep all; the
enlarged gauge card with an early peak; the Chain screen's route 1->3 refusals and the long-run dialog.

Verdict: Part A is verified, with no fixes and one engineering note (A5's dialog wording).

## Status

- A1 GUI-16: VERIFIED
- A2 GUI-16: VERIFIED
- A3 GUI-16: VERIFIED
- A4 GUI-16: VERIFIED
- A5 GUI-16: VERIFIED
- A6 GUI-16: VERIFIED
