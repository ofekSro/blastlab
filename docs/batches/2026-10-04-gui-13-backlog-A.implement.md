# GUI-13 Part A - implementation report

Batch `docs/batches/2026-10-04-gui-13-backlog.md`, Part A. Branch `gui-13` from `b618cdb`
(master). Owner decisions 2026-10-04 applied: D1 (trigger kept, advice only), Q1 (stage-1
radius seed), Q2 (char wording pin), Q3 ("the 2D stage"). Commits `1e9e853..73a0e20`.

## A1 - (a) reseed the default chain - SKIPPED (stopped under D2)

Implemented a `CHAIN_SEED = {1: {'radius_m': '1.5'}, 3: {'Lz': '4.0'}}` in
`ui/chain_panel.py` (applied once when the editors are built, quiet, untouched) and the
named test edits; `test_ui_chain_screen.py` went green (232 checks). Acceptance 2 then
failed, and the plan says stop and report, so both files were reverted (no commit).

- **Criterion 2 FAIL** (scratch `a1_validate.py`, validate_case on `forms[3].get_case()`,
  Lz 4.0 vs the 1.5 m box):
  - native, unprobed and probed: clean, same as 1.5 m.
  - blastFoam, probed (63 GB VM): clean.
  - **blastFoam, unprobed ("assumed 4 GB"): ERROR** `~1,227,303 cells exceeds the blastFoam
    cap of 1,113,510 ... resolving the 0.308 m charge forces a 0.01927 m cell across the
    whole 4 m domain`. The 1.5 m box gets no error.
  - The WIRED stage-3 case the live check validates (a profile start, no charge
    resolution) gets no error, but unprobed it gets a new warning
    `Large grid: ~576,000 cells - expect hours of wall time ...` on routes 123, 23 and 13
    (1.5 x 1.5 x 4 m at 0.025 m). Probed it is clean.
- **The Q1 radius seed alone could not land either:** `test_ui_char_chain_wiring.py`
  failed. Its golden `char_golden/ui_chain_wiring.json` pins `"radius_m": "10.0"` for the
  untouched stage 1 in three chain dumps. The plan does not name that golden, so it was
  not re-recorded.
- Criterion 1 (card 3 clean, Lz 4.0) was PASS in the reverted version; criterion 3
  (`test_ui_setup_form.py` exit 0, Setup 3D Lz still 1.5) PASS.
- Files: none committed.

## A2 - (b) F45 wording - DONE (`1e9e853`)

`ui/chain_route._burst_above_3d` now says: `The 2D stage's Burst z (2.0 m) is at or above
this stage's Lz (1.5 m): the 3D box cuts the 2D field off above 1.5 m, burst included.
Raise Lz to at least 4.0 m (the 2D stage's Height H) or lower the 2D stage's Burst z.`
If Ly cannot be read, it ends `Raise Lz above 2.0 m.` The trigger is unchanged (D1).
`in_text` names the burst height by its form label: `(Burst z, 2.0 m)`.

- **Deviation from D3's literal: the labels.** D3 says `Burst y` and `Ly`. The 2D form
  that feeds 3D is always axisymmetric (a planar one is refused, `AXISYM_REFUSAL`), and
  that form labels cy **`Burst z [m]`** and Ly **`Height H [m]`** (`setup_spec.AXISYM_LABELS`;
  measured on the chain's stage-2 form: `axisymmetric Burst z [m] Height H [m]`). The UX
  review read `setup_spec.py:501` without the axisymmetric relabel. So the text uses the
  form's own labels: `Burst y` / `Ly` for planar (D3's literal exactly, pinned by a test)
  and `Burst z` / `Height H` for axisymmetric. This is the TODO's stated aim ("uses the
  form labels").
- Files: `blastlab/ui/chain_route.py`, `blastlab/tests/test_ui_chain_screen.py`. The named
  wording pins were changed: the F45 literal in S5 and S5r, and the in-text pin `:363`,
  `'z 2.0 m'` -> `'Burst z, 2.0 m'`. New checks: planar labels, the unreadable-Ly ending,
  `in_text` 2D/3D.
- Tests: `python test_ui_chain_screen.py` (233 PASS), `test_ui_chain.py`,
  `test_ui_char_chain_wiring.py`.
- C1 PASS: suite exits 0 with the new literal; the equal case `Lz 2.0` still warns (S5r
  check unchanged). C2 PASS: `rg "burst is at z|burst height, z" blastlab/ui` finds 0.

## A3 - (c) drop / outside warnings name G<n> - DONE (`6f28bea`)

`services/validation._validate_closing` names a gauge `G<n> (x.xx, y.xx) m`, n from
`enumerate(start=1)`: `G1 (1.40, 0.30) m inside Wall 1 - will be dropped` and
`G1 (5.00, 5.00) m outside the domain - will be dropped`.

- Files: `blastlab/services/validation.py`. Named test edits: `test_case_validate.py`
  (face/inside helpers, two literals, the A4 regex at ~`:740`, which now also checks the
  printed coordinates against the entered point), `test_char_validation.py:239` (Q2,
  wording only), and the S5f `warned()` regex in `test_ui_chain_screen.py` (same
  literals; it now also checks the coordinates). No assertion was loosened.
- C1 PASS: the three suites exit 0. C2 PASS: `rg "Gauge \{tuple|Gauge \(" blastlab/services`
  finds 0. C3 PASS: all 16 `test_gui_*` suites exit 0 (the repo has 16, not 9).

## A4 - (e) one drop-wall rule - DONE (`492609f`, follow-up `ed2715a`)

- `services/validation`: new `drop_rule(case, pending_inputs=False)`. It builds the
  warning's own `_gauge_drop_rule` on the context `validate_case` builds through
  `_validate_refinement`. It returns 0 outside the domain, and 0 when the case cannot be
  laid out. New `drop_wall(case, point)`, and `OUTSIDE_DOMAIN`. `gauge_drop_reason(...,
  outside=True)` now carries "outside the domain", and both callers use it.
- `ui/run_gauges._drop_reason`: outside test first, then the open-box inside wall, then
  `drop_wall`. Follow-up `ed2715a`: when neither names a wall (the Results screen's
  `case_from_meta` SimpleNamespace, which the rule cannot lay out), it falls back to the
  old first wall within a cell. Without that, a face drop on Results would have lost its
  reason.
- `ui/scaled_distance.where_text(case, point, dropped=None)`: appends ` (dropped)` to
  `N cm in front of / behind Wall i` when the rule drops the gauge (D5).
  `ui/setup_panel.py` builds the rule once per gauge-table refresh. That file is not named
  by the plan; it was added for cost (a rule takes about 0.17 ms to build).
- New checks: `test_case_validate.py` (two walls 0.03 m apart under 0.05 m blastFoam
  snapping: the warning says Wall 1 and `drop_wall` says 1; `drop_rule` drops exactly the
  warned set of 7 points; outside / 1D give 0). `test_ui_setup_strip.py` (Setup warning ==
  `drop_wall` == Run `_drop_reason` == Wall 1; `4 cm in front of Wall 1 (dropped)` at
  x 1.252 against a wall entered at 1.29 that snaps to 1.25; the native twin reads
  without the suffix; Run says "outside the domain"; the meta-view fallback).
- C1 PASS, C2 PASS (the commands above). C3 PASS: `rg "outside domain" blastlab/services
  blastlab/ui` finds 0. The A3 suites and `test_ui_run_screen.py` (218) exit 0.

## A6 - (f) top-face native rows off their ties - DONE (`62e0e39`)

The native fixed-verdict rows now sit a quarter cell above the face: 2D `(1.4, 1.0026)`
and 3D `(1.6, 1.0, 1.0026)`, verdict none. 2D y = 1.0 is a native cell face (dx 4/380)
and 3D z = 1.0 is too (dx 2/190). blastFoam keeps its on-face rows. Each tie is pinned
once as `warned <=> its solver drops it` with `got in ([], face(...))`.

- Files: `blastlab/tests/test_case_validate.py` only.
- C1 PASS (suite exit 0). C2 PASS: scratch `gui13_a6_perturb.py` shifts every non-first
  axis's faces in `core.grid._faces_shared` (solver and validator alike) and runs
  `gauge_in_obstacle_checks`. New test: +1e-12 / 0 / -1e-12 give 0 / 0 / 0 failures.
  Pre-change test (HEAD before `62e0e39`): 0 / 0 / **2** failures (the 2D and 3D native
  top-face rows).

## A5 - (d) + UX #9 exported gauge grid - DONE (`73a0e20`)

`output/plots.figure_gauges_nd(..., drop_note=None)`. When a gauge was dropped, the figure
gets a footnote (a `supxlabel`, so constrained layout makes room for it): the caller's
note, else `Not shown: G2, G3 - dropped by the solver`. The default comes from a new
`output/gauge_summary.dropped_numbers`, which returns [] when the pairing is short (P1).
Only then do the titles read `G4 (2.01, 0.88) m → cell (2.02, 0.88)`. Without a drop
nothing changes.

- **Qt path deviation:** `ui/results_gauges.py` has no figure export call. Qt exports go
  through `ui/exports.export` -> `services/exports.run_export`. So `results_gauges` gained
  `export_drop_note(res, dim)` (the screen's `dropped_text`), and `ui/exports.export` puts
  it in `opts['gauge_drop_note']` for `pngs` / `report`. `services/exports.run_export`
  passes it on through `png_figures` / `report_figures` (new keyword, default None).
  `ui.exports` still re-exports the same objects (char pin passes).
- Files: `blastlab/output/plots.py`, `blastlab/output/gauge_summary.py`,
  `blastlab/services/exports.py`, `blastlab/ui/exports.py`, `blastlab/ui/results_gauges.py`.
  Tests: `test_plots_gauge_titles.py` (a named edit of the drop-case title literals, plus
  footnote present / absent / Qt note and `dropped_numbers`), and `test_ui_results_screen.py`
  S5g (the PNG export passes the note and a TSV does not; the figure's footnote is the note).
- C1 PASS: suite exit 0; with a drop the footnote and new titles are there, without one
  `_supxlabel is None` and `fig.texts` holds only the suptitle. C2 PASS: all 21
  `test_char_* / test_ui_char_* / test_gui_char_*` exit 0, unedited. C3 PASS: 16
  `test_gui_*` exit 0.

## Closing

- Matrix, each exit 0: `test_ui_chain_screen` (233), `test_ui_chain` (114),
  `test_case_validate`, `test_char_validation`, `test_ui_setup_strip` (134),
  `test_ui_setup_form`, `test_ui_run_screen` (218), `test_ui_results_screen` (221),
  `test_plots_gauge_titles`, `test_foam_writer`, `test_refine`, `test_ui_results` (130),
  `test_out1_qa_polish`, and all char suites and `test_gui_*`.
- `_qa_gui_harness.py` (Tk), out dir `C:\Users\rotem.ofek\blastlab_qa\20261004-2141`:
  every B, C, D, E, G, M, V, H and I scenario reports `done`. I02 ("close the window 2 s
  into a native 3D run") prints 11 teardown tracebacks and still ends `done`; that
  scenario is not touched by this batch. **The F group (F00-F11, real blastFoam solves of
  about 8 min each) was skipped** for time; this batch changes no foam path.
  - Mishap: `--resume` without `--out` picks the lexicographically last folder, which is
    `out1_20260926_191440` (`o` sorts after `2`). It ran 7 invocations into that old
    folder, ending with a STOP file I created and then removed. That folder's checkpoint
    now holds fresh B-F03 entries. Nothing was deleted.
- `python -u test_regression.py`: REGRESSION PASS, byte-identical (run last).
- App start: `python -m blastlab` was alive after 20 s with an empty stderr, then stopped
  by its PID. The §8.2 dry run beforehand gave `False []`.

## Files touched

`blastlab/ui/chain_route.py`, `blastlab/services/validation.py`, `blastlab/ui/run_gauges.py`,
`blastlab/ui/scaled_distance.py`, `blastlab/ui/setup_panel.py`, `blastlab/output/plots.py`,
`blastlab/output/gauge_summary.py`, `blastlab/services/exports.py`, `blastlab/ui/exports.py`,
`blastlab/ui/results_gauges.py`. Tests: `test_ui_chain_screen.py`, `test_case_validate.py`,
`test_char_validation.py`, `test_ui_setup_strip.py`, `test_plots_gauge_titles.py`,
`test_ui_results_screen.py`.

## GUI screens touched (for QA)

- Chain: stage cards and Checks (F45 text); 02/03 hand-off IN captions (Burst z wording).
- 01 Setup: Checks strip (G<n> drop / outside warnings); Gauges tab Where column
  (`(dropped)` suffix).
- 02 Run: dropped-gauge caption reason, now from the solver's rule.
- Results: Gauges caption, unchanged. Exported PNG / HTML-report gauge grid: footnote and
  titles when a gauge is dropped. Tk: Setup warnings text, and the Tk gauge figure
  footnote.

## Numerical changes

None. No solver, validation threshold or golden changed. Validation text only; which
gauges warn is unchanged (the A4 rule is the existing `_gauge_drop_rule`).

## Engineering issues noticed

1. **A1 / D2:** the 4 m 3D box does not fit the "assumed 4 GB" blastFoam cap as a charge
   start (1.23 M vs 1.11 M cells), and as a fed stage it draws "Large grid" until the
   probe finishes. Probed on this machine it is clean.
2. **Where vs Checks, two walls within a cell:** a gauge at x 1.628 between Wall 1
   (snaps to 1.65) and Wall 2 (snaps to 1.60) is dropped for Wall 1 (the first snapped
   box), but Where names the nearer Wall 2: `1 cm in front of Wall 2 (dropped)`. D5's
   suffix makes the drop visible but does not make the wall agree.
3. The Results meta view (`case_from_meta`) cannot run the drop rule (no solver or
   material fields), so Results still names a face-drop wall by the within-a-cell
   heuristic.
4. `_qa_gui_harness.latest_out()` sorts folder names, so a non-timestamp folder
   (`out1_...`) always wins `--resume`. *Recommendation:* sort by mtime, or only match
   `YYYYMMDD-HHMM` names.

## Open questions for the owner

1. **A1 - how to seed the chain.** Options: (a) seed `Lz 4.0` and accept the unprobed
   cap error / "Large grid" warning; (b) also seed stage 3 coarser, or with a smaller
   Lx/Ly (a numbers decision, D2); (c) keep Lz 1.5 and let F45's new advice do the work.
   *Recommendation:* (c) for Lz, and approve re-recording `ui_chain_wiring.json` (three
   `radius_m` strings, 10.0 -> 1.5) so Q1's 1D seed can land and card 2 opens clean.
2. **A2 labels:** confirm `Burst z` / `Height H` (what the axisymmetric form shows) over
   D3's `Burst y` / `Ly`. *Recommendation:* keep the form labels; planar keeps D3's
   literal.
3. **Where vs drop wall (issue 2):** should Where name the drop wall when the rule drops
   a gauge that is in front of a different, nearer wall? *Recommendation:* yes, in a
   later small task: use the drop wall's number when dropped.
