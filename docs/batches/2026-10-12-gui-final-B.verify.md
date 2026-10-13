# Verification report - batch final-gui-and-ignition, Part B (B1-B11)

- **Plan:** `docs/batches/2026-10-12-gui-final.md`, Part B (+ B11, Clarifications). Depth **full**.
- **Branch** `final-gui`, part base `934028f`, implemented `934028f..9ae0ee4`, verifier fix `f183a4f`.
- **Implementer's report:** `docs/batches/2026-10-12-gui-final-B.implement.md`.
- Own scratch checks (scratchpad): `verify_partB_direct.py` (B1, B3-B7, B9-B11 on own cases),
  `verify_b8_b5_foam.py` (B8 + B5 blastFoam half on written specs, no WSL), `verify_arrow_reverse.py`
  (B4, reverse direction), `verify_amr_hang.py` / `verify_amr_sweep.py` / `verify_amr_defaults.py`
  (the reported hang), `verify_b1_edge.py`.

## Per task

| Task | Verdict | Criterion -> check used |
|---|---|---|
| B1 | **FIXED** (`f183a4f`) | (1) own planar case, wall 1.8-2.2 m, native and blastFoam: trigger on dropped G2 -> one `Trigger disabled` naming G2, no trigger note; kept G3 -> `... reaches G3`. (2) `trigger_disabled` 2 / None. (3) `test_char_validation` green in the gate, unedited. Defect found and fixed: see D1. |
| B2 | **PARTIAL** (as reported) | (1) the four suites green in the gate; `git diff -U0` of the pin files: only the table's lines edited (+ new checks). (2) one hit left, `solvers/hooks.py:84` (`Trigger gauge {k + 1} was dropped`). Confirmed held for the right reason: `test_foam_trigger_drop.py:126` asserts `f'Trigger gauge {n} was dropped' in h.msgs[0]`, which `G2` would turn red, and that pin is not in the plan's table. Not edited (owner, Stage 6). No production code parses the old wording (`_stopped_early` is a set lookup; no `startswith('trigger')` outside tests). (3) regression byte-identical. |
| B3 | VERIFIED | own 1D case: `numbers_1d(2, [2]) == [1, 3]`, titles `Gauge 1`/`Gauge 3`, footnote `G2 dropped by the solver`; `numbers=None` -> today's titles, no footnote. `test_export_numbers_1d` + the four char suites green, unedited. |
| B4 | VERIFIED | (1) `check_b4_goldens.py` re-run on `0667564..690ae45` and on `934028f..9ae0ee4`: 49 arrow lines in 8 files, every number unchanged, + 212 `ok <hash>` lines. **212 hash lines independently confirmed arrow-only, the other direction:** the PRE-B4 code (worktree at `0667564`) with only the label arrow swapped to `→` (CSV kept `->`) reproduces HEAD's goldens byte for byte in all six char suites; negative control (no swap) fails in each (summary_2d/3d, ui/gui_results_meta, exports_can/qt). So no number, and nothing but the arrow, moved. (2)/(3) pin suites and all char suites green in the gate. Own check: snapped label uses U+2192; the summary CSV stays ASCII with `->`. |
| B5 | VERIFIED | own: `add_gauge_markers` `dropped=None` same artist count; one dropped -> +2 artists, `x` at the entered point, `#ff922b`, text `G2`, unstarred. blastFoam `_live_gauges` on own 2D spec: kept G1 G4, dropped `[(2, 2.0, 0.5), (3, 3.5, 1.0)]`; 1D kept G1 G3, dropped `[(2, 9.0, 0.0)]`. 3D uses `spec.grid`/`spec.dx`, the same arrays `slice_geom_3d` used before. Regression byte-identical. |
| B6 | VERIFIED | own: valid 2D with a wall -> `failed == ''`, rule names Wall 1; display grid refused by `plan_levels` -> `failed = 'the refinement plan stopped: AMR display grid ...'`, every gauge kept; no obstacles -> `''`. |
| B7 | VERIFIED | `release_decision(True, False, v, stopped=True) == (False, 'the run was stopped before it finished')`; `stopped=False` keeps "it raised"; `:1074-1083` pins green unedited (`test_model_folder` in the gate). |
| B8 | VERIFIED | own written specs (no WSL): 2D `[warn] G2 (2.00, 0.50) m inside Wall 1 - dropped` + G3 `outside the domain`; nothing dropped -> no line; 3D G2 inside Wall 1; 1D `G2 (r 9.00 m) outside the domain`. `test_foam_writer` green; `foam_golden/` unchanged. Citation checked: guide v6.0 sec. 15.1 (pp. 122-123) is blastProbes, `probeLocations`; the comment's claim is about the writer, consistent. |
| B9 | VERIFIED | own temp runs dir: not found -> None, chain `2d` stage found, two models -> newest manifest wins. No production caller yet (Qt half is C10, by plan). |
| B10 | VERIFIED | own 1D/2D TSV round trip: radii/points exact, values rel 1e-6. `test_model_load` green. |
| B11 | VERIFIED | own planar case: control refuses 1 mm on a 50 mm cell; `_faces_shared` raising -> one `Ignition radii not checked` warning naming `ZeroDivisionError`, no refusal. A warning, not an error, per the owner's wording. |

## Fixes

- `f183a4f` fix(verify): no trigger note beside a trigger number with no gauge (GUI-16) - D1.

## Defects

| # | Where | Severity | State |
|---|---|---|---|
| D1 | `services/validation.py:898-921` `_trigger_note` | low | **fixed** `f183a4f`. Checks said `The run ends when the wave reaches G5` beside the error `Trigger gauge G5: the case has 3 gauge(s)`, and `... reaches G0` beside `Trigger gauge must be a gauge number`. Pre-existing words (`gauge 5`), carried into B1's `_trigger_note`; B1's point is that a trigger that cannot fire is not described. New check in `test_case_validate.trigger_drop_checks`. |
| D2 | `output/plots.py` `figure_gauges_1d` (own footnote fallback) | low | not fixed (design limit, no wrong output today). With only `numbers`, the figure footnotes the gaps. A **trailing** drop (`numbers_1d(2, [3]) == [1, 2]`), the usual 1D case (the farthest radius past the domain), gets no footnote. Qt is right because it always passes `drop_note` (`export_drop_note` covers dim 1). Tk passes neither today. **For E1:** pass `drop_note` as well as `numbers=`. |
| D3 | `services/validation.py` `drop_rule` | note | `_validate_refinement` can append an error and still return True (AMR + zones), so the rule is built from the uniform grid with `failed == ''`. The case is refused anyway; not a B6 failure. |

## The reported `validate_case` hang - not reproduced, not caused by Part B

The case was a 2D blastFoam AMR case, 4 m, 0.05 m base, 8 levels, display level 8. At HEAD and at `934028f` (worktree),
`validate_case` returns in 0.06-0.55 s. It does not hang: `plan_levels` refuses the 419,430,400-cell display grid,
and the error names it. `amr_levels > 5` is refused (`AMR levels must be 1..5`), and so is `display > levels`. I swept
about 30 variants: axisymmetric and planar, with and without a wall, gauges, a trigger and `det_radii`, levels 3/5/8, display
default to 8, bases 0.05/0.03/0.02/0.01 m (up to a 163,840,000-cell display grid), `env.hardware` probed and unprobed,
plus `drop_rule` and `trigger_disabled`. Each one returned in under 0.1 s. B11 only wraps the existing arithmetic in
try/except, and B6 only adds an attribute; neither has a loop that could hang. The stall in the implementer's
probe is most likely outside `validate_case`, for example the WSL `env.hardware(probe=True)` call. Nothing to fix.

## Gates

- `gate.py --changed 934028f --deep` on `9ae0ee4`: **114/114 green, 27.1 min**, all 16 `test_gui_*` (Tk) included.
  WSL solve suites not run (gate rule).
- Fix: `gate.py --changed HEAD` (uncommitted fix): 8/8 green (test_case_validate, test_char_validation,
  test_trigger_numbering, test_ui_setup_tree/strip, ...).
- `gate.py --only regression` last, on `f183a4f`: **PASS, byte-for-byte**.
- `foam_golden/`, `baseline/`, `foam_fixtures/`: no change in `934028f..HEAD`; working tree clean.
- Worktrees made for the A/B (`verifyB-base`, `verifyB-pre4`) removed.

## Engineering / owner questions

1. **B2's held line** (implementer's Q1). Recommend **yes**: approve the text-only edit of
   `test_foam_trigger_drop.py:126` with `test_trigger_numbering.py:110, :198` so `hooks.py:84` reads
   `Trigger gauge G2 was dropped - trigger disabled`. It is the same owner-3 wording edit, and the pin was simply not
   yet in the table when the plan was written.
2. **B4's 212 hash lines** (implementer's Q2). Recommend **accept**. They are proved arrow-only in both directions
   (above), inside the already-approved re-record of `gui_results_meta.json` / `ui_results_meta.json`.

## GUI screens that need QA (Stage 4)

Setup / Checks trigger notes (B1, D1) and the unchecked-radii warning (B11). The Results Gauges table and every
export: the `→` labels, the 3-decimal drop titles with ` m`, the footnote one line per gauge, and 1D exports numbered by
the entered gauge (B3, B4). Run log `G3` trigger lines and the blastFoam `[warn] ... - dropped` lines (B2, B8). GIF
export: the orange `x` (B5). The live panes do not draw `gauges_dropped` yet (C/E tasks).

**Verdict:** Part B verified. B1 had one low defect, fixed in `f183a4f`. B2 stays PARTIAL until the owner rules on
one pin. No number moved.

**Owner ruling 2026-10-13:** questions 1 and 2 approved. B2 finished in `200573b` (the log line and the three pins,
text only; `gate --changed` 31/31 green). B2 is now **FIXED**, B4's 212 hash lines accepted.
