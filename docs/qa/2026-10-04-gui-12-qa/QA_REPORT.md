# GUI-12 QA - render-and-drive, real platform

Branch `gui-12`, HEAD `e3e8325`, batch `docs/batches/2026-10-04-gui-12-backlog.md`.
No application code was edited. Harnesses: `harness_qt.py`, `harness_tk.py` (copies of
the scratchpad scripts; not part of `tests/`); raw output `log_qt.txt`, `log_tk.txt`,
`results_qt.json`, `results_tk.json`, `run_values.json`.

## 1. Environment

- Python 3.12.10, PySide6 6.11.2, customtkinter, Pillow; Windows 11 Enterprise
  10.0.26300, real desktop (`QT_QPA_PLATFORM` unset, platform `windows`; Tk on the
  real desktop, window-bbox grabs only).
- Throwaway settings via `ui/testing.private_settings()` (`auto_cleanup: false`,
  private runs dir); CLAUDE.md 8.2 dry run before the first launch: `False`, `[]`.
  Native solver only, no WSL. 1D / 2D native runs of 3-7 s each.
- Qt: a real `MainWindow`, real `win._run_single()` runs; Tk: real
  `blastlab.gui.app.App`, real `_run_single()`, nested mainloop pumps. Dialogs stubbed
  to recorders. Windows closed, no python process left.

## 2. Result table

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | Setup Checks: `inside Wall i` / `on the face of Wall i` | PASS | `01_setup_checks_1100x720.png`, `01b_setup_checks_scrolled_1100x720.png`, `01_setup_checks_1600x1000.png` |
| 2a | Chain stage 3: reach warning on the default seed (burst z 2.0 >= Lz 1.5) | PASS | `02_chain_stage3_lz1p5_{1100x720,1600x1000}.png`, `02b_..._scrolled_1100x720.png` |
| 2b | Chain stage 3: silent at Lz 2.5 | PASS | `03_chain_stage3_lz2p5_{1100x720,1600x1000}.png` |
| 3 | Run live-gauge column, two close gauges, earlier one dropped | PASS | `04_run_live_gauges_mid_1100x720.png`, `05_run_live_gauges_final_{1100x720,1600x1000}.png` |
| 4a | Results: labels after a drop (screen) | PASS | `06_results_gauges_{1100x720,1600x1000}.png` |
| 4b | Results: gauge-trace titles in the export figures | PASS | `07_export_gauge_traces.png` |
| 4c | 1D Field tooltip `Exports use the full title: ...` | PASS | `08_results_field_1d_*.png`, `09_field_1d_tooltip.png` |
| 5 | Tk Gauges tab titles after a drop | PASS | `10_tk_gauges_tab_{1100x720,1280x840,1600x1000}.png` |

Checks: 27/27 Qt, 4/4 Tk, each backed by a value read from a live widget or a figure.

## 3. Failures

None.

## 4. Details per item

**1. Setup.** Case: planar 2.4 x 1.6 m, 20 kg/m, Wall 1 (1.2-1.6, 0-0.6), Wall 2
(1.8-2.0, 0.9-1.3), six gauges. Checks tab reads, verbatim:
`Gauge (1.4, 0.3) inside Wall 1 - will be dropped`,
`Gauge (1.2, 0.3) on the face of Wall 1 - will be dropped`,
`Gauge (1.9, 1.1) inside Wall 2 - will be dropped`,
`Gauge (2.0, 1.2) on the face of Wall 2 - will be dropped`. The second obstacle gives
`Wall 2`; the old `inside an obstacle` wording is gone. No check label is clipped
(`heightForWidth <= height` at 1100x720 and 1600x1000).

**2. Chain.** Default seed, route 1D -> 2D -> 3D: stage 3 Checks read `The 2D stage's
burst is at z 2.0 m, above this stage's 1.5 m height: the remapped field misses the
burst. Raise this stage's height above 2.0 m.` Card 3 reads `1 warning`, the pill
`Stage OK · 1 warning`, Run chain stays enabled (D200). Lz 2.5: `Stage OK`, card
`case OK`, no burst line. Boundary: Lz = 2.0 (equal to the burst z) still warns (the
"at or above" rule). The line wraps to three lines and is not clipped.

**3. Run live column.** Crafted real native run (planar, dx 0.05581 m, entered
G1 (1.0633, 0.7228), G2 (1.1191, 0.7284) inside Wall 1, G3 (1.1191, 0.6977) 0.03 m from
G2). The solver kept 2 points (1.0884, 0.6977) and (1.1442, 0.6977). The pre-A2 greedy
pairing would have given `[G3, G2]` (indices `[2, 1]`), so the case discriminates; the
order-preserving pairing gives `[0, 2]`. Live column rows `G1`, `G3`; caption `2 gauges,
sorted by R. Click a row to enlarge it. G2 dropped by the solver (inside Wall 1).`
`gauge_summary.gauge_labels` gives `G1`, `G3` too (screen == export).

**4. Results.** Gauges rows `G1`, `G3` (peaks 280753.3 / 145909.0 kPa), caption names G2
inside Wall 1. Export figures (`services.exports.report_figures` and `png_figures`, the
functions the Report and All-plots buttons call): panel titles `Gauge 1  (1.09, 0.70) m`
and `Gauge 3  (1.14, 0.70) m`, no `Gauge 2`. The on-screen Qt Gauges view has no
per-trace title (one plot, selected-gauge readout `G1 ...`), so "screen titles" are
the row labels above. 1D Field: a real 1D run, `fields.canvas.toolTip()` equals
`Exports use the full title: 1D Spherical Blast - 1.0 kg TNT - EOS: idealGas`, identical
to `plots.figure_results_1d(...).axes[0].get_title()`; a `QHelpEvent` on the canvas
makes `QToolTip` visible with that text (`09_field_1d_tooltip.png`, the tip widget alone).

**5. Tk.** Real Tk run of the same case: Gauges tab figure titles `Gauge 1  (1.09, 0.70) m`,
`Gauge 3  (1.14, 0.70) m`; summary table rows `G1 (1.063, 0.723) -> cell ...`,
`G3 (1.119, 0.698) -> cell ...`. Title and table agree (the GUI-11e mismatch is closed).

## 5. Visual findings (all low, none new in this batch's diff)

1. 1100x720: the new warnings sit below the fold. Chain stage 3's right-hand panel shows
   only the `CHECKS` heading at the bottom edge (`02_chain_stage3_lz1p5_1100x720.png`);
   the line appears after scrolling (`02b_...scrolled`). Setup's Checks tab shows the
   three first warnings, the two Wall 2 lines need a scroll
   (`01b_setup_checks_scrolled_1100x720.png`). The card (`1 warning`) and the pill
   signal it without scrolling. B1's "unclipped at 1100x720" holds once scrolled.
2. 1100x720 Run live-gauge card header: `R 0.77 m · Wall 1 · select` is cut by the
   `peak 280,753 kPa` text (`05_run_live_gauges_final_1100x720.png`).
3. 1100x720 Results Summary caption `G2 dropped by the solver...` is elided
   (`06_results_gauges_1100x720.png`); the full text shows at 1600x1000.
4. Tk Gauges table: the first column cuts the label at `-> cell` (width 150 px); the
   label is the correct one, only the cell coordinates are hidden. Tk's window
   minimum is 1100x720 (a 1000x700 request is clamped).

## 6. Numbers check

Run values vs the core (`gauge_summary` on the same `Result`):

| Quantity | Displayed | Core / reference |
|---|---|---|
| Run column labels | G1, G3 | `gauge_labels` -> G1, G3 |
| Export titles | Gauge 1, Gauge 3 | order-preserving `pair_in_order` -> [0, 2] |
| Results table G1 / G3 peak | 280753.3 / 145909.0 kPa | same rows in the Tk table |
| Tk table G1 / G3 peak | 280753.3 / 145909.0 kPa | equal |
| 1D tooltip suptitle | `1D Spherical Blast - 1.0 kg TNT - EOS: idealGas` | `figure_results_1d` title, identical |

## 7. Limits of this run

- Export buttons were not clicked (no file dialogs driven); the export figures were
  built by the same `services/exports` functions the buttons call, and the Tk panel's
  own `_draw_gauges` figure was read live.
- The harness's third run in one model folder raised the stubbed `Model folder`
  overwrite question (answered yes by the recorder): a harness artefact, no app issue.
- The QHelpEvent was sent directly; a physical mouse hover was not synthesised.
- A first full-desktop grab of the tooltip captured the owner's desktop; it was deleted
  and not committed. Only window / widget grabs are kept.
