# GUI-14 Part A - implementation report

Batch `docs/batches/2026-10-11-gui-14-backlog.md`, Part A (A1-A7) plus A8 (owner Q2, 2026-10-11).
Worktree `C:\Users\rotem.ofek\blastlab-worktrees\gui-14`, branch `gui-14`, base `2f947c4`.
Commits `7a2f8a0..cb00fb1` (eight tasks, in the order below; commit order was A1, A7, A2, A3, A6, A4, A5, A8).

## Tasks

### A1 - (c) Where names the wall the solver drops the gauge for - DONE (`7a2f8a0`)
`ui/scaled_distance.where_text` takes the wall from `dropped(point)` when the gauge is dropped and
measures gap and side against it (`where(case, point, wall=)`); a kept gauge still names the nearest
wall. Files: `ui/scaled_distance.py`, `tests/test_ui_setup_strip.py`.
- Crit 1 PASS: new check, gauge at x 1.245 with two walls within a cell (blastFoam snapping): the
  nearest as entered is Wall 2, `drop_wall` = 1, the Checks warning = Wall 1, Where reads
  `3 cm behind Wall 1 (dropped)`.
- Crit 2 PASS: `test_ui_setup_strip.py` exit 0; no existing `where_text` literal edited.

### A2 - (d) A dropped gauge is marked in the table and on the tree - DONE (`4bf8857`)
`scaled_distance.outside_domain` (the one closed test, also used by `run_gauges._drop_reason`),
`is_dropped`, `any_dropped`; Where reads `outside the domain (dropped)`; Setup's table paints `G<n>`
and Where `warn` for a dropped gauge; the `gauges` node is `warn` while any gauge is dropped (Setup
and chain stage, computed from the rule). Files: `ui/scaled_distance.py`, `setup_panel.py`,
`chain_stage.py`, `run_gauges.py`, tests `test_ui_setup_strip.py`, `test_ui_chain_screen.py`.
- Crit 1 PASS: new checks (x = Lx + 1 reads outside, x == Lx does not; warn cells for the dropped
  gauge only; node warn then ok, in Setup and on stage 2).
- Crit 2 PASS: `test_ui_setup_strip`, `test_ui_setup_form`, `test_ui_chain_screen`,
  `test_ui_run_screen` exit 0.
- Fixture edit (not a literal): the "3D boxes: '10 cm in front of Wall 1'" check built `Case3D` with the
  default 1.5 m cube, so its gauge at x 1.9 was outside the domain and now reads dropped. The
  fixture gets `Lx = Ly = Lz = 4.0`; the asserted literal is unchanged.

### A3 - (e) Run card header - DONE (`37940f7`)
`run_gauges.py`: `Qt.ElideRight`; `selected` removed; Z written `Z 1.23 m/kg^1/3` (unit from
`scaled_distance.LABEL`). Named layout-pin edit: `test_ui_run_screen.py:959` (`... · Wall 1 · selected`
-> `Z <z> m/kg^1/3 · Wall 1`), reason UX F4.
- Crit 1 PASS: `test_ui_run_screen.py` exit 0; the forced-elide check passes and a new check shows the
  elided text `Z 2.99 m…` starts with `Z `.
- Crit 2 PASS: no `'selected']` left in `run_gauges.py` (Grep: 0 matches).

### A4 - (f) Results' drop line in the warn style - DONE (`79f5236`)
`results_gauges.py` objectName `gaugedrop`; `theme.py` `QLabel#gaugedrop` (12.5 px, 600, `warn`).
- PASS: `test_ui_results_screen.py` exit 0; new check: polished label foreground = `warn`, weight
  DemiBold (600), in dark (`#f5d061`) and light (`#926800`).

### A5 - (b) Tk Gauges table - DONE (`8935fc8`)
`gui/results_panel.py`: `_fit_summary` sets the gauge column's width/minwidth from the longest label
(Treeview font, +24 px), other columns minwidth 72, a horizontal scrollbar only when the Complete
cell is still clipped (checked after layout and on `<Map>`).
- Crit 1 PASS: real-platform scratch `a5_tk.py` (based on `harness_tk.py`; native 2D, snapped gauge,
  1100 x 720 logical): scaling 1.0 PASS (gauge col 288 px vs widest 264; complete right edge 842 <= table
  844) and 1.5 PASS (338 vs 264; 1264 <= 1266; the app's min size makes the window 1650 x 1080 physical
  there). No scrollbar was needed. Screenshots (PrintWindow fallback) in the scratchpad:
  `a5_tk_scaling_1.0.png`, `a5_tk_scaling_1.5.png`.
- Crit 2 PASS: `gate.py --for blastlab/gui/results_panel.py` 10/10 green.
- Found on the way: a first version called `update_idletasks()` in the clip check, which redrew the
  figure canvas on every fill and made `test_gui_char_results_meta` run 13+ min (137 s at base). Fixed
  (no `update_idletasks`; 137 s again).

### A6 - (h) `test_ui_status_cells` S2 polls - DONE (`65f431c`)
Local `wait_for(pred, ms=5000)` (50 ms steps) replaces both `pump(600)`.
- PASS: ten sequential runs exit 0 (`0 x10`); `git diff` shows no `check(` line changed.

### A7 - (i) harness `latest_out()` by mtime - DONE (`38610d6`)
`_qa_ui_harness.py`, `_qa_gui_harness.py`: sort by `(os.path.getmtime, name)`.
- PASS: scratch `a7check.py` imports both modules, `QA_ROOT` at a folder with `20261001-1200` and
  `out1_x`: the newer-mtime folder is returned in both orders, both modules (4/4). Harnesses not run.

### A8 - (a) the default chain seeds the 1D radius at 1.5 m - DONE (`cb00fb1`)
`ui/chain_panel.py`: `CHAIN_SEED = {1: {'radius_m': '1.5'}}`, applied once, quietly, at the end of
`__init__` (stage 1 untouched). Stage 3 `Lz` stays 1.5; 01 Setup's default (10 m) unchanged.
- Stop rule PASS (scratch `a8_stop.py`, real `MainWindow`, route 1->2->3, form and wired cases of
  stages 1 and 2, native and blastFoam, unprobed and `env.hardware(probe=True)`): 1.5 m brings no error
  or warning that 10 m does not. At 10 m stage 2 has the S2-1 line in all four combinations; at 1.5 m
  neither stage has any message.
- Golden `char_golden/ui_chain_wiring.json` re-recorded with `--update`; diff is exactly three lines
  (:161, :378, :743) `"radius_m": "10.0"` -> `"1.5"`. `test_ui_char_chain_wiring.py` PASS.
- Named behaviour-pin edits in `test_ui_chain_screen.py` (all consequences of the default radius):
  1. S1 out-text check: `Outer (10.0 m)` -> `Outer (1.5 m)` (it pins the default radius).
  2. S5: the S2-1 / F45 / B2 checks pin card 2's warning on the default route; they now set stage 1's
     radius to `10.0` first (the warning is still tested, with its own trigger).
  3. "untouched stage {d}: ... the rest the spec default": expects `CHAIN_SEED` for stage 1's radius.
- New checks: default route card 2 is `● case OK`, no `hands off` line, radius 1.5, stage 1 untouched;
  a route change does not bring 10 m back; `setup_spec.by_name(1)['radius_m'].default == 10.0`.
- Acceptance PASS: `test_ui_chain_screen`, `test_ui_char_chain_wiring`, `test_ui_setup_form` exit 0.

## Closing matrix
- `gate.py --changed 2f947c4 --deep`: 71/71 suites green (23.4 min).
- `gate.py --only regression` (last): green, byte-for-byte.
- `python -m blastlab` started and ran 12 s (stopped by PID).

## Files touched
`blastlab/ui/`: `scaled_distance.py`, `setup_panel.py`, `chain_stage.py`, `run_gauges.py`,
`results_gauges.py`, `theme.py`, `chain_panel.py`. `blastlab/gui/results_panel.py` (Tk, named by A5).
Tests: `test_ui_setup_strip.py`, `test_ui_chain_screen.py`, `test_ui_run_screen.py`,
`test_ui_results_screen.py`, `test_ui_status_cells.py`, `_qa_ui_harness.py`, `_qa_gui_harness.py`,
`char_golden/ui_chain_wiring.json`. Not touched: `fieldform.py`, `TODO.md`, `DONE.md`, `services/`.

## GUI screens touched (for QA)
Setup Gauges tab and the `05 Gauges` tree node (warn marks); a chain stage's Gauges node; Run screen
enlarged-gauge card header; Results Gauges drop line (both themes); Tk Results Gauges table at 1100 px
(scaling 1.0 and 1.5); Chain screen, default route (card 2 clean).

## Numerical changes
None. The only value moved is a UI seed (stage 1 `radius_m` 10.0 -> 1.5 in the chain editors; golden
`ui_chain_wiring.json` re-recorded, three lines; owner Q2 2026-10-11).

## Engineering issues noticed
- The first `gate.py --for` (the starting-state run) was left running while I edited and was stopped by
  the 30 min background limit; the starting state was not recorded. Every later gate was clean.
- `test_gui_char_results_meta.py` takes ~137 s at base: any `update_idletasks()` in the Tk results
  panel is expensive because it redraws the matplotlib canvases.
- `PointList.set()` does not fire `on_change` (documented), so a chain-stage gauge edit by script needs
  `_on_change()` to revalidate; the new chain check does that.
- The existing forced-elide check's name still says "the middle is elided"; its condition is unchanged
  (left as is, no prose edits).

## Open questions for the owner
- None blocking. Recommendation: have the verifier run `_e2e_ui_chain_foam.py` (RESUME item 2) with the
  new 1.5 m seed, since a blastFoam stage-1 at 1.5 m is a different (smaller) 1D solve than the 10 m one.
