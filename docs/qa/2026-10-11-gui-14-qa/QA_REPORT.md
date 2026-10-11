# GUI-14 QA report (2026-10-11)

Worktree `C:\Users\rotem.ofek\blastlab-worktrees\gui-14`, branch `gui-14`, diff `2f947c4..HEAD` (HEAD a55b80b).

## 1. Environment
- Python 3.12 (Store build), PySide6 (real platform, `QT_QPA_PLATFORM` unset, `platformName` = windows), customtkinter for `--tk`, Windows 11, 3840x1018 desktop (maximised = 1920x1009 on the primary screen).
- CLAUDE.md 8.2 dry run first: `auto_cleanup` = `False` (the sweep list was non-empty, as expected; the flag is off, nothing was deleted).
- Harnesses: `_qa_ui_harness.py --window --solver native`, `_qa_gui_harness.py --solver native`, each with its own `--out` under this folder, resumed through the harness's own budget exits (exit 75), `PYTHONIOENCODING=utf-8`, `python -u`.
- Own drivers (kept here): `driver_qt.py`, `driver_qt2.py`, `driver_tk.py`; logs `log_qt.txt`, `log_qt2.txt`, `log_tk_1.0.txt`, `log_tk_1.5.txt`; results `results_qt*.json`, `results_tk_s*.json`.
- Disclosure, WSL: `--solver native` only seeds the start mode. The Qt harness F group (F00-F05) switches to blastFoam itself and ran real WSL solves (about 14:00-14:10) before I noticed; this broke the "no WSL solves" rule. I then skipped F06-F11 in the Qt harness and F00-F11 in the Tk harness. `pgrep blastFoam` was empty afterwards. The first harness launch was also stopped by my own background timeout during D04 (processes killed by PID, then resumed).
- Cleanup: the harness run trees (1.3 GB: cache, runs, exports, shots) were deleted. Kept: checkpoints, logs, findings, contact sheets, curated shots.

## 2. Result table

| # | Item | Result | Evidence |
|---|---|---|---|
| 0 | Dry run 8.2 | PASS | `False` |
| 1 | `_qa_ui_harness.py` (Qt) | PASS | 74 scenarios run, 6 skipped (F06-F11, WSL); 1598 `ok:` checks, 0 FAIL; `ui_harness/harness.log`, `findings.jsonl` |
| 2 | `_qa_gui_harness.py` (Tk) | PASS | 59 scenarios run, 12 skipped (F00-F11, WSL); 101 `ok:` lines, 0 FAIL; `gui_harness/harness.log` |
| 3 | Chain default route, cards 1-3, stage 1 R 1.5 m | PASS (see F3) | `01_chain_default_cards_1100x720.png`, `_1600x1000.png` |
| 4 | Chain stage 1 Gauges node | PASS | `02_chain_stage1_gauges_node_*.png` (no gauges, ok) |
| 5 | Chain stage 2 Gauges node, wall + outside gauge: warn; ok again after the gauge moves inside (after `_on_change()`, as an edit does) | PASS | `03_chain_stage2_gauges_dropped_*.png` |
| 6 | Chain stage 3 Gauges node warn with an outside 3D gauge | PASS | `10_chain_stage3_gauges_dropped_1100x720.png` |
| 7 | Setup Gauges table: G2 (wall) and G3 (outside) warn-coloured, G1/G4 not; `outside the domain (dropped)`; G4 at x == Lx not outside | PASS | `04_setup_gauges_table_*.png`; item colours in `log_qt.txt` |
| 8 | Setup `05 Gauges` node warn (`!`) | PASS | `05_setup_gauges_node_*.png` |
| 9 | Run enlarged-gauge card header: no `selected`, elides at the end, tooltip = full text; R mode and Z mode (`Z 0.27 m/kg^1/3`) | PASS | `07_run_log_and_gauges_*`, `08_run_card_forced_elide_1100x720.png`, `12_run_card_Zmode_*`, `13_run_card_forced_elide_Z_1100x720.png`, `14_run_Zmode_maximised.png` |
| 10 | Results Gauges drop line, both themes (objectName `gaugedrop`, weight 600, warn colour dark #f5d061 / light #926800) | PASS | `09_results_gauges_dark_*`, `09_results_gauges_light_*` |
| 11 | Tk Results Gauges table at ctk scaling 1.0 and 1.5 (gauge column fits, `complete` cell inside the table, all columns have a bbox) | PASS (see F2) | `tk_results_gauges_s1p0_*`, `tk_results_gauges_s1p5_*` |
| 12 | Native solver log lines | PASS | 2D planar and axisym runs both log `[warn] G2 (1.12, 0.73) m inside an obstacle - dropped` and `[warn] G3 (3.00, 0.50) m outside the domain - dropped` (axisym: G3 inside, G4 outside); `log_qt.txt`, `log_qt2.txt` |
| 13 | No modal dialogs in the drivers | PASS | |

Driver totals: `driver_qt` 21/21, `driver_qt2` 5/5, `driver_tk` 4/4 at 1.0 and 4/4 at 1.5. The first `driver_qt` pass had 4 FAILs. All four were my driver's mistakes, not app defects: it assumed a silent `PointList.set()` revalidates (it does not, by design), expected a `(dropped)` suffix on `inside Wall 1`, and expected `Z` in a planar case (Z is shown for axisym/3D only). Corrected and rerun.

Not covered at 1100 px real width with scaling 1.5: ctk scales the geometry, so `1100x720` became 1650x1080 logical (`tk_results_gauges_s1p5_1100x720.png`). A true 1100-px-wide window at 150 % was not tested.

## 3. Question: does stage 1 of the default 1 -> 2 -> 3 route hold a gauge beyond 1.5 m?
No. The gauge list is empty on all three stages: stage 1 `gauges = []` (1D `gauge_radii = []`, radius 1.5 m), stage 2 `[]`, stage 3 `[]`. Nothing is dropped. Evidence: `log_qt.txt` ("CHAIN gauges per stage"), `02_chain_stage1_gauges_node_1100x720.png` ("no gauges"), cards 1 and 2 `case OK`.

Caveat (F1): if the user adds a stage-1 radius beyond 1.5 m, it is dropped silently.

## 4. Findings

| ID | Severity | Finding |
|---|---|---|
| F1 | medium | A 1D stage drops gauge radii beyond its radius with no warning on any surface. Repro: Chain, route 1->2->3, stage 1, add gauge radii `1.0` and `2.0` (R = 1.5 m). The Gauges node stays `ok`, the card reads `case OK`, Checks reads `Stage OK`. Cause: `solvers/solver1d.py:146` (`[g for g in gauge_radii if 0 < g <= radius_m]`) and no matching rule in `services/validation.py`. This is UX F6, now easier to hit because the seed went from 10 m to 1.5 m. I did not run the 1D solver, so I checked no run log line (the filter has none). Plain Setup 1D (R 10 m) has the same filter; I did not drive it. |
| F2 | low | Tk Results Gauges table at scaling 1.0, 1100 px: the gauge column and all 8 columns are visible, but 7 headers are clipped at the 72 px minwidth: `Peak ovp`, `Arrival [m`, `t peak [m`, `Pos. phas`, `Pos. imp [`, `Net imp [`, `Phase end`. Units are cut. At scaling 1.5 (1650 px wide) all fit. `tk_results_gauges_s1p0_1100x720.png`. Likely `gui/results_panel.py` `_fill_summary` (minwidth 72). I did not check the header tooltips. |
| F3 | low (known, owner Q2) | The default route's card 3 reads `1 warning`: F45, Burst z 2.0 m >= Lz 1.5 m. Cards 1 and 2 are clean, as GUI-14 (a) intended. `01_chain_default_cards_1100x720.png`. |
| F4 | low | Setup Where reads `inside Wall 1` for a gauge the solver drops, but `outside the domain (dropped)` for another. The row is warn-coloured either way. Not a defect against the plan (A1 keeps the wording). |
| F5 | low | Results (light, 1100 px): the subtitle `selected gauge in colou...` is elided. Cosmetic, probably older. `09_results_gauges_light_1100x720.png`. |
| F6 | info, outside the batch | Qt harness F05 had 2 S2 findings (mesh did not adapt; no per-frame level map) and `blastFoam failed (exit 134)` in F05 and F06 (WSL, AMR). Nothing in the diff touches this, but I did not run the base, so it is unverified whether it is old. |

Unchanged S2 findings, identical to the 2026-10-05 harness run:
- Qt Q03 (`no result labelled 'QA native2d'`).
- Qt I02 (close during a native run took 13.2 s; 13.3 s before).
- Tk I02 (15.7 s).

16 S3 findings in the Qt harness are Qt `External WM_DESTROY` messages from the 3D viewer child, the same noise as before.

The harness F00-F11 coverage (blastFoam) for this batch is untested by design: the batch changes nothing in `solvers/foam`.

## 5. Visual notes
- Setup Gauges table: dropped rows are amber on `G<n>` and Where only (spec). The tree's child rows `G2`/`G3` under node 05 are not coloured. The node's `!` is.
- Run Z-mode header `Z 0.27 m/kg^1/3` uses a literal `^`. It fits at 1100 px (146 px wide, no overlap with `peak`).
- Run live-slice preview: labels `G1G2` collide in the tiny axisym slice. Cosmetic.
- Results drop line: bold warn in both themes, wraps to two lines at 1100 px, fits on one at 1600.

## 6. Numbers
Not a calculation batch. B1 touches log strings only. The kept-gauge values shown (G1 peak 280753.3 kPa, arrival 0.068 ms) are the Results table's own; they were not recompared with the core (`test_regression` is the gate for that, and the Part B verify report records it byte-identical).
