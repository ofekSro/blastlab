# QA report - batch gui-15-backlog (master f1f9dd4)

Date 2026-10-11/12. Real platform (QT_QPA_PLATFORM unset) for my drivers; the big harness native pass ran offscreen, the blastFoam pass with `--window`.

## 1. Environment

- Python 3.12.10, PySide6 (Qt), Windows 11 Enterprise 10.0.26300, repo at master f1f9dd4, tree clean.
- Before the GUI: CLAUDE.md 8.2 dry run printed `auto_cleanup False`. Before the foam pass: `wsl -d Ubuntu -- pgrep -a blastFoam` empty (and empty again after). Nothing deleted in `/root/blastlab_runs` (F07 added one kept scratch run, `20261012-013608_2d_p61436-00`).
- Drivers (kept here, not committed to tests/): `driver_qt.py` (Setup/Chain/Run/Results, 2D and 1D native), `driver_anim.py` (animation export), `driver_foam_setup.py` (Setup Checks in blastFoam mode, no solve).
- Deviation: the harness `--out` is the scratchpad, not the QA dir, see Finding 6. Harness logs and contact sheets are copied to `ui_harness_native/` and `ui_harness_foam/`.

## 2. Result table

| # | Item | Result | Evidence |
|---|---|---|---|
| H1 | Big harness, native (`--solver native`), 80 scenarios | PASS: 68 done, 12 skipped (F00-F11, skip reason "keeps the harness off WSL"), 0 crashes, 2 S2 findings both already in GUI-14 QA (Q03, I02), 0 new | `ui_harness_native/` |
| H2 | blastFoam pass `F00,F07` | PASS: 2 done, 0 findings. F07 stop during blockMesh returned in 2.1 s, no "Run failed" dialog, no Results entry | `ui_harness_foam/shots/001..002_F07*.png` |
| H3 | F05/F06 exit 134 | NOT RUN (not in the requested pass); known P1-23/P2-22 | - |
| S1 | Setup Checks: `within a cell of Wall 1` (native, G2 at 1.195, wall face 1.2) | PASS, no `on the face of` | `01_setup_checks_near_1100x720.png` |
| S2 | Setup Checks: `inside Wall 1` (G2 at 1.4) | PASS | `01_setup_checks_inside_1100x720.png` |
| S3 | Setup Checks: trigger-disabled warning (trigger on dropped G2) | PASS: "Trigger disabled: trigger gauge G2 is dropped (see above), so the run ends by its normal stop" | `01_setup_checks_trigdrop_1100x720.png` (but see Finding 2) |
| S4 | Setup Checks, 1D beyond radius (native and blastFoam) | PASS: "G2 (r 2.00 m) outside the domain - will be dropped" | `05_setup_checks_1d_1100x720.png`, `17_foam_setup_checks_1d_1100x720.png` |
| S5 | Setup Gauges node: warn, caption ` · G2 dropped`, G2 child warn and G1 not | PASS in data (tooltip `4 · in front of Wall 1 · G2 dropped · trigger G3`), caption visibly cut, see Finding 1 | `02_setup_gauges_node_1100x720/1600x1000.png` |
| S6 | Setup Gauges node, 1D (`3 gauges · G2 dropped`, G2 child warn) | PASS, not elided | `06_setup_gauges_node_1d_1100x720.png` |
| C1 | Chain stage 2 Gauges node warn, G2 child warn | PASS (caption elided as in Setup) | `04_chain_stage2_gauges_node_*.png` |
| C2 | Chain stage 1 (1D) Gauges node warn, `3 gauges · G2 dropped` | PASS | `08_chain_stage1_gauges_1d_1100x720.png` |
| R1 | Run, drop line from Start before any gauge data | PASS: rows G3 G1 G4 (sorted by R), no G2 row, "G2 dropped by the solver (inside Wall 1)." | `09_run_start_pre_payload_1100x720.png` |
| R2 | Run log names the wall | PASS: `[warn] G2 (1.40, 0.30) m inside Wall 1 - dropped`, then `Trigger gauge 3 (0.6031, 0.5036) m reached at t = 0.091 ms` | `10_run_live_1_1100x720.png`, status bar |
| R3 | Live markers G1 G3 G4, trigger star on G3 | PASS: `G3*`, G2 not drawn | `10_run_live_1_1100x720.png` |
| R4 | Run 1D: drop line pre-payload, gauge column G1 G3, log line | PASS: "G2 dropped by the solver (outside the domain)", log `[warn] G2 (r 2.00 m) outside the domain - dropped` | `13_run_1d_start_1100x720.png`, `14_run_1d_after_*.png` |
| Z1 | Results Gauges 2D: rows G1 G3 G4, drop line, default row is the trigger's (G3) | PASS (selected row 2 = G3, plot titled G3) | `12_results_gauges_2d_*.png` |
| Z2 | Results Gauges 1D: rows G1 G3, drop line names G2 | PASS | `15_results_gauges_1d_*.png` |
| A1 | Exported 2D animation, G2 dropped before the trigger | PASS: bold `G3*`, mp4 written, 126 frames | `16_animation_frame5.png` |
| T1 | Trigger numbering result: stops on G3's point, `meta trigger_gauge` 3 | PASS (log: reached gauge 3 at 0.091 ms, the control value in the batch plan) | log lines above |
| D1 | 3D Detach | known failure, not exercised | - |
| W1 | Resize 1100x720 and 1600x1000 for touched screens | PASS, no overlap; only Finding 1 | `*_1600x1000.png` |

Driver checks: 14 of 16 PASS; the 2 FAIL were my own bad checks (Run column is sorted by R, so G3 G1 G4 is correct; and the model-folder overwrite prompt was auto-answered yes). `results_qt.json`.

## 3. Findings (all low; no medium, no high)

1. **low** - The Setup and chain-stage Gauges node caption loses the new text in 2D with a wall. The tree column is capped, so `4 · in front of Wall 1 · G2 dropped · trigger G3` shows as `4 · in front of Wall 1 ·…` at both 1100x720 and 1600x1000. The text is only in the tooltip. The warn-coloured G2 child row and the `!` still say it, so the intent holds. The 1D caption (`3 gauges · G2 dropped`) fits. Order is D11 (count, then dropped, then trigger), so the dropped part is always the tail that is cut. Shots: `02_setup_gauges_node_1600x1000.png`, `04_chain_stage2_gauges_node_1600x1000.png`. Origin: `blastlab/ui/setup_nodes.py` `summaries`, rendered by `setup_tree.py`.
2. **low** - With the trigger on a dropped gauge, Checks shows both `Trigger disabled: ... so the run ends by its normal stop` and, a line below, the note `The run ends when the wave reaches gauge 2`. The two contradict each other. Shot `01_setup_checks_trigdrop_1100x720.png`. Origin: the trigger note in `services/validation.py` is not suppressed when the new warning fires.
3. **low** (known, D13/Q2) - blastFoam mode, trigger on a dropped gauge: no trigger warning, only the drop warning plus the "run ends at gauge 2" note (`17_foam_setup_checks_trigdrop_1100x720.png`). The foam trigger path was not measured here. A native-near gauge (1.195 against a wall face at 1.2) was not dropped at dx 0.05, as the foam rule intends.
4. **low** - The exported animation still draws the dropped G2 (at its entered place inside the wall), while the Run live slice leaves it out. Consistent with entered numbering, but the two surfaces differ (`16_animation_frame5.png`, `10_run_live_1_1100x720.png`).
5. **low** - After a deliberate stop during blockMesh (F07) the Run card shows `100 %` with "Stopped after 1 s", and the log says `WSL scratch kept (the run did not finish (it raised))`. A stop is not a raise, and the native harness check "progress bar NOT filled after a stop" (D05) failed once on GUI-14 QA too. Shot `ui_harness_foam/shots/002_F07_run_after_stop_dark.png`. Not new in this batch.
6. **low** (process) - Running the harness with `--out` inside the OneDrive repo folder poisons the pass: `Could not delete the previous run ... [WinError 5] Access is denied ...\runs\QA\fields`, so D03-D06, H02, I01, I02 fail ("the run started" etc.), and the cut-off delete leaves a model folder without MODEL.json, so the next `--resume` crashes at boot (`use_model: ... is not a blastlab model folder`). I discarded that first pass (`invalid_first_native_pass/`) and re-ran with `--out` in the scratchpad (non-OneDrive): clean. Suggest the harness refuse or warn when `--out` is under OneDrive. This is also why the foam pass `--out` was not the QA dir.
7. **known, not new** - Q03 "no result labelled 'QA native2d'" and I02 "closing during a native run returned in 13.1 s" (S2): both in the GUI-14 QA findings (13.2 s). No new S1 or S2.

## 4. Visual notes

- Dark theme only was exercised by my drivers; the harness K03 covers light (all ok).
- Trigger field in Gauges properties (`G3 · x 0.60, y 0.`) is clipped at 1100x720 and 1600x1000; not part of this batch.
- F07 shots 001 and 002 are identical (the first was taken after the stop had landed).

## 5. Numbers check

Native 2D case (planar 2.4 x 1.6 m, 20 kg/m, wall x 1.2-1.6, gauges G1 (0.3,0.8) G2 (1.4,0.3) G3 (0.6,0.5) G4 (1.0,1.0), trigger 3, dx 0.04):

| Quantity | GUI shows | Expected | OK |
|---|---|---|---|
| Dropped gauge | G2, inside Wall 1 (Checks, Run drop line, log, Results drop line) | `validate_case` reason `inside Wall 1` | yes |
| Trigger | gauge 3 at t = 0.091 ms | 0.091 ms (batch plan B3 acceptance, same control) | yes |
| Results labels | G1 G3 G4, default row G3 | entered numbers, trigger row | yes |
| 1D | G2 (r 2.00 m) dropped, rows G1 G3 (Z 1.00, 1.20; peaks 934.0 and 603.1 kPa) | radius 1.5 m | rows by number; peak values not re-derived here |

I did not recompute the peak pressures against the core function in this pass; the batch's own suites cover that.

## 6. Not covered

- blastFoam Run drop line, live markers and Results Gauges on a real foam run (only F07 was requested), 3D Detach (known failure), F05/F06 (known 134).
- Setup Checks for foam `within a cell of Wall n` could not be shown at dx 0.05 with a 5 mm offset, as the foam rule keeps that gauge.
