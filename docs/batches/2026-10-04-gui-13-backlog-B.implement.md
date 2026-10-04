# GUI-13 backlog, Part B - implementation report

Branch `gui-13`, on top of Part A (`00ff860`). Commits `6c88eea` .. `87c62a2`.
Part A's A1 stays SKIPPED and untouched; no golden re-recorded; no WSL solve.

## B1 - the 1100 x 720 clippings (QA #2-#4) - DONE - `6c88eea`

- QA #2: the Run card's `meta` label is now `results_list.ElidedLabel` (middle
  elide, whole text as tooltip); `card_texts()` reads `full_text()`.
- QA #3: the Results drop note has its own wrapped line (`drop_caption`) under
  the Summary caption, which stays one elided line. A fully wrapped caption
  (first attempt) took table height at 1100 x 720 and broke the committed
  "every row on screen" pin, so only the drop note wraps; `_cap_height` counts
  that line. `caption_text()` still returns `<note> · <caption>`.
- QA #4: Tk Gauges `gauge` column 150 -> 310 px (min 120 -> 250). Measured with
  Tk's default font: the 2D label is 207 px, the 3D label 273 px.
- Files: `ui/run_gauges.py`, `ui/results_gauges.py`, `gui/results_panel.py`,
  `tests/test_ui_run_screen.py` (new check), `tests/test_ui_results_screen.py`
  (new check). No layout pin was changed.
- Criteria: 1 PASS - real platform (`QT_QPA_PLATFORM` unset, 1100 x 720
  MainWindow, scenarios 3 and 4a): Run caption `heightForWidth` 15 <= height 31;
  header rect (1840-1972) and peak rect (1980-2092) do not overlap; Results drop
  line `heightForWidth` 21 <= height 21. 2 PASS - `test_ui_run_screen.py` (220
  at the end), `test_ui_results_screen.py`, 16 `test_gui_*` suites all exit 0.

## B2 - Domain & mesh row shows warn (UX #12) - DONE - `b333eb8`

`StageCheck.reach` carries the F45 / S2-1 line; `chain_stage.show_check` sets the
stage's `domain` row to `warn` (`!`) instead of the tick, errors still win.
D8: the stage editor has no row-focus API, so the click-to-focus link is
deferred. Files: `ui/chain_route.py`, `ui/chain_stage.py`,
`tests/test_ui_chain_screen.py` (two new checks). PASS: warn at Lz 1.5 (and
stage 2 at the 10 m seed), ok at Lz 4.0; suite exits 0 (235 checks).

## B3 - Run caption puts the drop note first, in warn (UX #11) - DONE - `89fe680`

New `drop` label above the caption in `run_gauges`, styled `warn`;
`caption_text()` = note then caption. Named pin edit in `test_ui_run_screen.py`:
the string moved from the caption's end to its start. New check on the warn
colour. PASS: starts `G2 dropped by the solver`, warn colour; suite exits 0.

## B4 - export-title hint to the Export buttons (UX #10) - DONE - `c34d05c`

`FieldsView.export_hint` signal; `ResultsPanel` puts the text ahead of the
usual tooltip on the figure exports (`pngs` = All plots, `report`; there is no
PDF button), cleared on 2D/3D/no result. Canvas tooltip removed. Named edit of
the two GUI-12 B3 pins in `test_ui_results_screen.py`. PASS: 1D PNG button
tooltip starts `Exports use the full title:`; canvas tooltip empty; 2D/3D carry
none.

## B5 - Results labels fall back to entered numbers (UX #8) - DONE - `87c62a2`

`results_gauges.labels_and_dropped`, when `case_from_meta` is None, uses
`gauge_summary.entered_numbers` / `dropped_numbers` (reason unknown, so none is
printed). Three new checks. PASS: meta without `charge_center` and a drop reads
G1 G3 on screen, caption names G2.

## Closing matrix

See the end of the final message; results below.

All `test_ui_*` (incl. run, results, chain screens), all `test_char_*`,
`test_case_validate.py`, `test_plots_gauge_titles.py`, `test_gauge_summary.py`
(50 suites): exit 0, except `test_ui_status_cells.py` which exited 1 once in the
sequential pass and exits 0 when rerun alone (flaky under the long pass; no
related change). 16 `test_gui_*` Tk suites exit 0 (run after B1; B2-B5 touch no
Tk file or shared module). `test_regression.py` PASS, byte-identical, run last.
App starts (MainWindow shown, offscreen). Not run: `_qa_ui_harness.py`,
`_qa_gui_harness.py` (not reached; the caption string and tooltip moves of B3 and
B4 are the pins it might hold - recommend one QA pass).

## Touched

`blastlab/ui/`: `run_gauges.py`, `results_gauges.py`, `results_fields.py`,
`results_panel.py`, `chain_route.py`, `chain_stage.py`; `blastlab/gui/results_panel.py`
(one column width); tests `test_ui_run_screen.py`, `test_ui_results_screen.py`,
`test_ui_chain_screen.py`.

GUI screens for QA: Run (live gauge column, card header at 1100 px), Results
(Gauges drop line, export buttons' tooltips on a 1D result), Chain stage editor
(Domain & mesh tree row), Tk Results Gauges table.

Numerical changes: none.

## Notes for the owner

- The Results drop note is now a separate line; the elided Summary caption no
  longer carries it. Recommendation: keep.
- B4 touched `PNG/PDF` as `All plots` and `Report` (the buttons that exist).
- Chain card 3 and card 2 still open with warnings because A1 was skipped; B2's
  glyph will therefore show on the default chain until A1 is decided.
