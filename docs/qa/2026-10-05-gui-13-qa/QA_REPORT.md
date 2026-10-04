# GUI-13 backlog QA - 2026-10-05

Branch `gui-13` (HEAD 00a3b8e). Plan `docs/batches/2026-10-04-gui-13-backlog.md`.

## 1. Environment

- Python 3.12.10, PySide6 6.11.2, Pillow 12.2.0, Windows 11 (10.0.26300).
- Qt: real platform (`QT_QPA_PLATFORM` unset, platform `windows`), `harness_qt.py`, private settings and
  model folder (`testing.private_settings`, `use_model`); run-corpus dry run before starting printed
  `auto_cleanup False, []` (CLAUDE.md 8.2). Native solver runs only; no blastFoam solve was started.
- Tk (`--tk` GUI, `harness_tk.py`): `ImageGrab` was refused mid-session ("screen grab failed", locked
  desktop), so the Tk shots are Win32 `PrintWindow` renders of the real window.
- `_qa_ui_harness.py --out <scratch>`: run once on a short absolute path, offscreen, with F01-F11 skipped
  (they are real blastFoam solves). A first attempt with `--out` under `docs/qa/` hit the Windows path
  limit ("Could not delete the previous run") and was discarded.
- Windows and processes: all closed, no python left running.

## 2. Result table

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Chain: default chain, Lz 1.5 | FAIL (expected, see F1) | `01_chain_default_card3_*` |
| 1b | Chain: card 3 F45 text wraps, not clipped, 1100x720 and 1600x1000 | PASS | `02_chain_stage3_lz1p5_*`, `02b_...scrolled` |
| 1c | Chain: hand-off captions (`handoff_1d_to_2d.txt` etc.) wrap, not cut | PASS | `02_chain_stage3_lz1p5_1100x720.png` |
| 1d | Chain: "!" on Domain & mesh row at Lz 1.5, back to tick at Lz 4.0 | PASS | `02_...`, `03_chain_lz4_ok_1100x720.png` |
| 1e | Chain: F45 wording (D3), equal case still warns, route toggle does not change an edited Lz | PASS | log_qt.txt |
| 2 | 01 Setup: Checks strip names `G<n> (x, y) m ...` (inside / on the face / outside the domain), Native and Tk-identical | PASS | `04_setup_checks_*`, `06_setup_checks_runcase` |
| 2b | 01 Setup: Where column `(dropped)` (blastFoam-snapped gauge 4 cm in front of Wall 1) | PASS at 1600, truncated at 1100 (see F3) | `05c_setup_where_foam_dropped_*` |
| 3 | 02 Run: drop note first, warn colour (#f5d061), above the caption | PASS | `08_run_final_*` |
| 3b | 02 Run: card header elides + tooltip is full text; header and peak rects do not overlap | PASS (see F4) | `08_run_final_1100x720`, `09_run_card_forced_elide` |
| 4 | 03 Results: drop line is a wrapping label, whole text, not clipped | PASS | `10_results_gauges_*` |
| 4b | 03 Results: labels G1 G3 when G2 dropped | PASS | log_qt.txt |
| 4c | 03 Results: export button tooltips on a 1D result start `Exports use the full title:`; canvas has none; tooltip renders | PASS | `13_results_field_1d_*`, `14_png_button_tooltip.png` |
| 5 | Exported gauge PNG with a drop: footnote visible, inside the figure (Qt note and builder note) | PASS | `11_export_gauge_png_qt_note.png`, `12_export_gauge_png_builder_note.png` |
| 6 | Tk: Setup warnings use `G<n> (x, y) m` wording | PASS | `20_tk_setup_warnings_*` |
| 6b | Tk: Gauges table `gauge` column fits `G<n> (x, y) -> cell (x, y) m` at 1100 px | FAIL (F2) | `21_tk_gauges_tab_1100x720.png` |
| 6c | Tk: exported figure shows `Not shown: G2 - dropped by the solver` | PASS | `21_tk_gauges_tab_1100x720.png` |
| 7 | `_qa_ui_harness.py` (non-foam scenarios) | PASS, 1543 ok, 2 findings unrelated to moved strings (F5, F6) | `log_ui_harness.txt`, `harness_ui/findings.jsonl` |

Qt harness: 37/37 checks pass (`results_qt.json`). Tk harness: 3/4 (the failing one is F2).

## 3. Failures and findings (severity)

**F1 - low, expected, not a regression.** The default chain still opens with card 3 at "1 warning" and
`Lz = 1.5`: batch task A1 (reseed `Lz`) was skipped (`...-A.verify.md`), as the brief says. The warning text
is the new D3 text (axisymmetric labels, shown as written by the form):
`The 2D stage's Burst z (2.0 m) is at or above this stage's Lz (1.5 m): the 3D box cuts the 2D field off above 1.5 m, burst included. Raise Lz to at least 4.0 m (the 2D stage's Height H) or lower the 2D stage's Burst z.`
Card 2 also keeps the S2-1 "1D stage hands off at 10.0 m" warning (Q1 not approved). Typing Lz 4.0 clears
card 3 to `case OK` and the tree row back to a tick.

**F2 - medium. Tk Gauges `gauge` column still cuts the cell text at 1100 px (QA #4 not fixed).**
Steps: `--tk`, run a 2D native case with a gauge snapped to a cell, Results > Gauges, window 1100x720.
Expected: `G1 (1.063, 0.723) -> cell (1.088, 0.698) m` whole. Actual: the cell reads
`G1 (1.063, 0.723) -> cell (1.088, 0.698` (closing `)` and ` m` cut); the column is 250 px wide, the text
needs about 287 px (measured with the Treeview font). The table is stretched to the window, and `stretch=True`
lets Tk shrink the gauge column down to its `minwidth=250`. Other headers ("Peak ovp [k", "Arrival [ms",
"Phase") are also cut, as before. Screenshot `21_tk_gauges_tab_1100x720.png`. Likely origin:
`blastlab/gui/results_panel.py:281-284` (`width=310`, `minwidth=250`, other columns `104`/`90`); raise
`minwidth` to about 300 or give the other columns less.

**F3 - low. The new ` (dropped)` marker is hidden at 1100 px.** In 01 Setup > Gauges the Where column is
elided at the 1100x720 minimum: `4 cm in front of…` - the `(dropped)` suffix, the point of D5, is only in the
tooltip there (`05c_setup_where_foam_dropped_1100x720.png`). At 1600x1000 the full
`4 cm in front of Wall 1 (dropped)` shows. The Checks tab names the same gauge, so nothing is lost, but the
suffix cannot be seen where the table is tightest. Origin: `setup_panel.py` Where column (stretch column
of a 432 px centre).

**F4 - low. Run card header elision drops the useful part.** At 1100x720 the header reads
`R 0.77 m · … · selected`; "Wall 1" goes, "selected" stays (full text only in the tooltip). The geometry
check passes (header and peak do not overlap), so QA #2 is fixed; the elision order is the nit.

**F5 - low, unrelated to this batch. The solver log still uses the old wording.** After a run, the Tk status
line and the Qt log show `[warn] Gauge (1.1191, 0.7284) inside an obstacle - dropped` (raw tuple, no `G<n>`,
no unit): `blastlab/solvers/solver2d.py:284,289`, `solver3d.py:342`. The batch's A3 covers `services/`
only, and these strings are pinned by `_e2e_gui_native_warn.py`, `_qa_gui_harness.py:1597`,
`_qa_ui_harness.py:2150`. Note it if the goal is "every gauge-drop message names the gauge".

**F6 - info. `_qa_ui_harness.py` findings (2), neither from moved strings.**
- Q03 S2 "no result labelled 'QA native2d' to select": scenario depends on a cached result from the D
  scenarios, which run later in a fresh output folder. Harness ordering, not the app.
- I02 S2 "closing during a native run returned in 13.3 s": a timing check on the close-confirm path
  (`299_I02_run_dialog-ask_yes_no_dark.png` in the scratch run). Not touched by this batch; no baseline
  was run, so it is not shown to be pre-existing.
No scenario broke from a moved string: C03 (gauge / obstacle checks), D02 (gauge drop), E03, E07, E09,
G01/G02, K02 (clipping at 1100x720) all pass with the new texts.

## 4. Visual findings

- Chain 1100x720: card 3 meta `1.5 x 1.5 x 1.5 m · 25 mm …` and card 2 `2D axisymm…` are elided (by design,
  tooltips). The checks panel is below the fold at 1100x720 (QA #1, D7): visible only after scrolling
  (`02b_...scrolled`); the card pill, the "!" glyph and the pill `Stage OK · 1 warning` point at it.
- Results 1100x720: the Summary table headers are cut on the right (`Pos. phase`, `[ms]`) - pre-existing.
- Exported PNG footnote (`Not shown: ...` / Qt note) sits in italics under the plots, inside the figure,
  not clipped (footnote bbox y0 4 px, y1 17 px of 400).
- Tk Setup (`20_tk_setup_warnings_*`): five drop lines readable at 1100x720; the sixth row below is cut by
  the panel, scrollable.

## 5. Numbers check

No calculation changed. Texts compared against the values entered / the core:

| Item | Displayed | Core / entered |
|---|---|---|
| Setup warning, run case | `G2 (1.12, 0.73) m inside Wall 1 - will be dropped` | entered G2 = (1.1191, 0.7284), wall x 0.558-1.5 |
| Solver kept points | 2 of 3 (G1, G3) | `res.gauges['points']` has 2 entries |
| Results labels | G1, G3 | `gauge_labels` order-preserving pairing |
| Export titles | `G1 (1.06, 0.72) m → cell (1.09, 0.70)`, `G3 (1.12, 0.70) m → cell (1.14, 0.70)` | cells (1.0884, 0.6977), (1.1442, 0.6977) |
| Peak G1 | 280,753 kPa (Run, Results) | same value from the result |
| F45 numbers | Burst z 2.0, Lz 1.5, advice 4.0 | 2D stage Height H = 4.0, burst z = 2.0 |

## Files

`harness_qt.py`, `harness_tk.py`, `log_qt.txt`, `log_tk.txt`, `results_qt.json`, `results_tk.json`,
`log_ui_harness.txt`, `harness_ui/findings.jsonl`, screenshots as listed above.
Nothing committed; no app code edited.
