# GUI-11 part 11d — verification report (T16-T22, F43, F40, F46)

Plan: `docs/batches/2026-10-03-gui-polish.md`, part 11d.
Implementer's report: `docs/batches/2026-10-03-gui-polish-d.implement.md`.
Commits checked: `4d0fb1c..4b99271` (15 commits). Branch `gui-redesign`.
Verifier fixes: none needed. This report adds F50 and F51.

Method:
- Every criterion was re-run, not read.
- Probes are in the session scratchpad:
  - `v11d_contrast.py`: T17, contrast recomputed from scratch;
  - `v11d_offscreen.py`: F43, F46, F40, T20;
  - `v11d_real.py`: real platform (`__main__` guard,
    `QT_QPA_PLATFORM` unset): T16, T17, T18, F38, F40.
- The CLAUDE.md §8.2 dry run read `False`, before and at the end.
- Every MainWindow ran on `private_settings()` (`auto_cleanup` read
  `False` in each throwaway file).
- No WSL solve. `pgrep -a blastFoam` was empty before and after.
- Heavy processes ran one at a time. No worktree was created.

## Verdict per task

| Task | Status |
|---|---|
| T16 · `●` when the name is elided | VERIFIED |
| T17 · dark tree hover | VERIFIED |
| T18 · Run strip and live view | VERIFIED |
| T19 · F17 short 1D title | NOT DONE (owner) |
| T20 · method card | VERIFIED (F51) |
| T21 · Results 3D placeholder | VERIFIED |
| F43 · notification gauge number | VERIFIED |
| F40 · Show Details | VERIFIED (F50) |
| F46 · refusal re-worded | VERIFIED |
| T22 · harness, passes, R10 | VERIFIED |

---

## T16 · D191 — VERIFIED

- PASS. `test_ui_frame` F10b: 1100 px, 30 characters, dirty → `●`;
  1600 px, `wall_A` → `● unsaved`; elided and clean → no marker
  (suite 86/86).
- PASS. Real platform, `v11d_real.py t16`: 168 states.
  - 3 widths (1100 × 720, 1280 × 840, 1600 × 1000) × 4 names
    (6 to 60 characters).
  - Each name goes through Save as (dialog stubbed), dirty, Open,
    rename, three chips × Setup/Run ✓, a theme switch both ways, and an
    app font change +2 px and back.
  - In every state:
    - a dirty, elided name reads `●` with the tooltip
      `Unsaved changes`;
    - the accessible name is the whole name;
    - `0D · HD 1.3` is ≥ 94 px at 1100;
    - the harness clip check finds nothing on the bar;
    - nothing sits outside the bar.
  - 0 bad.

## T17 · D192 — VERIFIED

Recomputed with an independent WCAG luminance script (not the test's
helper):

- Dark hover `#1c1c1f` against panel `#0e0e10`: 1.134 (> 1.02).
- Dark roles on it: num_dim 4.059, text 14.81, text2 10.43, faint 4.96,
  ok 10.18, warn 11.40, danger 5.72, gauge 8.84.
- Light hover `#f4f3f0`: num_dim 4.548, text 13.98, text2 9.51, faint
  4.74, ok 4.66, warn 4.503, danger 4.55, gauge 4.71.
- Only dark `num_dim` is under 4.5, and it is ≥ 4.0. PASS.
- `test_ui_theme` T6 prints the same values. PASS.
- Real platform: the screen pixel of an unhovered row is `#0e0e10`; with
  the real cursor on `03 Boundaries` it is `#1c1c1f` and
  `underMouse()` is True. PASS.

## T18 · S3-1, S3-2, S3-7 — VERIFIED

- PASS. Criterion 1 (offscreen): `test_ui_run_screen` R12, after
  `theme.apply` both ways at 1100 × 720 with a chain and a banner, no
  tile is under its minimum (suite 214/214).
- PASS. Criterion 2: R12's 1100-1600 px sweep in 20 px steps.
- PASS. Criterion 3, real platform:
  - 1280 × 840 with `5.818e+05 kPa`: two rows, label 175 px against
    145 px rendered.
  - Chain strip and banner at 1100 × 720: view 236 px, dock tucked
    (room 28 < 42).
- PASS. Theme switch, then resize to 1280, 1600 and 1100, in light and in
  dark:
  - the view is ≥ 200 px at every step;
  - P MAX is whole (1600: 147 / 146 px, 1100: 115 / 112 px);
  - no tile is squeezed;
  - the dock is shown exactly when there is room for it (≥ 42 px), and
    it never overlaps the view.
- PASS. **D213's restore, on the real platform:**
  - the dock comes back at 1280 × 840 (dock 131, view 217) and at
    1100 × 900 (dock 140, view 268);
  - it steps aside again at 1100 × 720.
- PASS. Chain, then a single run at 1100 × 720: the dock is back
  (110 px, view 200); with no banner it is 110 px and the view 270 px.
- PASS. Criterion 4, R10 (below).

The plan said the dock gives way "first (D35's 150 px floor)". The code
goes below the run dock's 110 px `DOCK_MIN`, down to the 42 px tab
strip, and then hides the dock. D213 records this, and the implementer's
open question 2 puts it to the owner. It is not a defect.

## T19 · F17 — NOT DONE, owner question

- The revert is complete:
  - `git diff 022aedb 0d71956` is empty, so the tree is exactly as it
    was before `02024f6`;
  - `screen_title_1d` and `1D spherical ·` appear nowhere under
    `blastlab/`;
  - `results_fields.py`, `_e2e_ui_results.py` and `char_golden/` have no
    diff over `4d0fb1c..HEAD`;
  - the PNG was removed.
- The golden still holds the old title
  (`1D Spherical Blast - 1.0 kg TNT - EOS: JWL`).
  `test_ui_char_results_meta` and `test_ui_char_results_exports` are
  green and unedited.
- D214 and F17's Outcome say it is blocked.
- **Owner question (unchanged):** approve re-recording the on-screen
  `title` entries and the `fields` hash of
  `char_golden/ui_results_meta.json`. Then `git revert 0d71956` plus the
  re-record in its own commit.

## T20 · UXR-10 small half — VERIFIED

- PASS. `test_ui_results_screen` S2c (suite 213/213).
- PASS. Probe on result-shaped metas:
  - planar 2D reads `2.5 kg/m TNT`;
  - axisymmetric, 3D and 1D read `kg`;
  - `miller` gets the caveat only for a known non-TNT material (C4: yes;
    TNT, unknown, `none`: no);
  - dx 0.0124352 reads `cell 12.4 mm`.
- `kg/m` is checked against the solvers:
  - `solver2d.py` 134 / 308 ("kg TNT per metre");
  - `core/materials.charge_radius(planar=True)`, the cylinder per unit
    depth that `foam/writer.py` 456 uses.
  - Both solvers read the planar charge as kg/m, so the label is right
    on both paths.
- The caveat restates CLAUDE.md §7. No coefficient was touched.
- PASS. `test_ui_char_results_meta` is green and unedited.
- **F51 (cosmetic):** `{:.3g}` gives `cell 1.23e+03 mm` for a cell of
  1 m or more.

## T21 · S3-6 text half — VERIFIED

- PASS. S3e: the holder text is new; `isinstance(…, View3DHost)` holds.
- PASS. The minimum width is unchanged at 1100 × 720 (S3e).
- `view3d_host.py` has no diff.
- Nothing else reads `View3DHost.PLACEHOLDER`.
- The button the text names exists: `export_column.py` 213, `Open the
  3D viewer`.
- The screenshot was checked.
- The three-line break instead of the plan's two lines follows the plan's
  own longest-line rule (D215).

## F43 — VERIFIED (two dropped gauges)

- Case: four gauges, G2 inside Wall 1 and G3 inside Wall 2, so two
  series are left.
- Highest peak on series 2: `Highest peak: G4, 296 kPa`. The Run column
  labels the series `['G1', 'G4']` and names the drops G2 and G3.
- Highest peak on series 1: `G1`.
- With no case: the payload number, as before.
- R6 in `test_ui_run_screen` passes.

## F40 — VERIFIED

- Offscreen, `Show Details…` holds exactly the shortened paths:
  - bare, quoted (OSError repr, backslashes halved back), bracketed and
    double-quoted paths;
  - a short path beside a long one;
  - a UNC path.
- A box whose paths fit has no details.
- Real platform:
  - the `Show Details...` button is there and the pane starts hidden;
  - a real click shows the pane;
  - Ctrl+A, Ctrl+C copies both paths whole (493 characters, the
    clipboard was restored afterwards);
  - the shown text is still elided.
- **F50 (low, predates 11d):** a path with spaces is never treated as one
  token, so it is wrapped by Qt instead of elided. It never gets details,
  but its copy is whole.

## F46 — VERIFIED

- PASS. `test_ui_setup_form` S8b (suite PASS).
- PASS. Probe:
  - an arity refusal is re-worded with the new columns;
  - after an accepted Add, the idle hint follows;
  - `not numbers: b` is kept;
  - a later `select a row…` replaces the callable;
  - the typed table's `values` refusal works.
- `_refusal` is set in `__init__` through `_accept()`.

## T22 — VERIFIED

**F38, calibration.** Real platform. For each button, its painted ink
(column profile of `grab()`) was compared with the whole text drawn wide,
against `_clipped_labels`:

| Button | Elided | Reported |
|---|---|---|
| `0D · HD 1.3` | 68-84 | 68-84 |
| dock tab | 81-110 | 81-110 |
| built Segmented | 141-174 | 141-174 |

- The dock tab is `Earlier runs   0` (bold, 14 px QSS padding).
- The built Segmented is a new one, labelled `Live slice wide label`.
- All three match exactly:
  - 72 px is reported and 94 px is not;
  - 80-84 px are both elided and reported, so nothing is hidden there;
  - no width is falsely reported.
- The `qstylesheetstyle.cpp` 3 px remark could not be read from a local
  Qt source, but the measured behaviour matches it on all three buttons.

**F36.** The F02 / F10 code was read:
- the S2 checks are strict (released AND disabled AND reason in the
  tooltip);
- the Keep all fields step is only skipped as a note.
It was not run, because it needs WSL: office machine.

**K02, `--window --solver native --scenario K02`** (spot check, out
`~\blastlab_qa\verify11d-k02-window`):
- 186 × `nothing clipped` and 186 × `nothing outside`;
- dark and light, native and blastFoam;
- 0 S1 / S2;
- 2 S3, the known F30 `External WM_DESTROY`.

**R10.** The rule section of `measurements.md` is unchanged:
- `git diff 49f9a75 HEAD` only adds `## Results`;
- `49f9a75` (05:16) is before the sampled runs (05:52-05:56).
The committed JSON's per-repeat values match the table.

Re-run here: run surface, `--actions tabs,resize --repeat 5`, real
platform, self-test 149.0 ms / 60 px.
- tabs: 0 ms ×5 over 1757 samples with a window. PASS.
- resize: 42.4, 25.8, 42.9, 42.1, 42.4 ms. Median 42.4 (≤ 50), max
  42.9 (≤ 80). PASS.
- The viewer child closed with its window.

The offscreen harness diff was not re-run (as instructed). Its files
(`gui11-d-head`: 6 findings, `gui11-d-window`: 2 S3) match the report.

---

## Changed committed assertions

All three are still exact:

1. `test_ui_theme` T6: the floor is 4.0 only for `('dark', 'num_dim')`;
   every other pair, and all of light, stay at 4.5. A new check also
   gates hover-to-panel > 1.02.
2. `test_ui_results_screen` S2c: the two Mesh pins compare the whole
   row with `{:.3g}`, as strict as before. A literal `cell 12.4 mm`
   check was added.
3. Harness F02 / F10: F02's old "offered + finishes" checks moved to the
   Keep all fields step, as the plan says (F36). The new
   released-and-disabled check is S2 and strict. F10's old check stays
   in the scratch-kept branch.

## Diff review

- No numerical change.
- The frozen paths (`gui`, `core`, `models`, `output`, `viz3d`,
  `solvers`, `services`, `view3d_host.py`, `run_controller.py`,
  `viewer_link.py`, the baselines, the fixtures, `char_golden/`) have an
  empty diff over `4d0fb1c..HEAD`.
- No never-stage path is in any 11d commit.
- No `print`, TODO, bare `except` or `except Exception` was added. The
  only new `except` (`_peak_label`) names four types and falls back to
  the old label.
- No broken callers: `PointList._reject` keeps its signature (`words`
  is optional), and `View3DHost` is subclassed, not changed.
- Cosmetic: in `docs/gui-redesign-decisions.md` the D-rows are not in
  numeric order (D225 before D212). Left as it is.

## Tests (verifier, one at a time)

- Offscreen, all exit 0:
  - all 35 `test_ui_*` suites, the six Qt char goldens unedited among
    them;
  - `test_ui_frame` 86, `test_ui_run_screen` 214,
    `test_ui_results_screen` 213, `test_ui_chain_screen` 220,
    `test_ui_setup_tree` 260, `test_ui_output_card` 162;
  - `test_case_validate` 140.
- Real platform: the `v11d_real.py` probes, K02 `--window`, and R10 on
  the run surface.
- Last: `test_regression.py` PASS, byte-identical (seven files
  identical, `b2_profile.npz` arrays equal, no baseline dirty). Then
  `test_ui_char_chain_wiring.py` PASS, unedited.

## Findings added

- **F50** (low, predates 11d): a path with spaces is never elided, so it
  never gets D228's details. Its copy is whole.
- **F51** (cosmetic, T20): `cell 1.23e+03 mm` at a cell of 1 m or more.

## Files touched by the verifier

- `docs/gui-redesign-decisions.md` (F50, F51)
- this report

## GUI screens for QA

The implementer's list stands, and the verifier changed no UI:
- top bar `●`;
- dark tree hover;
- point-list refusals after an r z ↔ x y toggle;
- 02 Run: two rows below 1420 px; the dock steps aside at 1100 × 720
  after a chain;
- 03 Results: method card and 3D placeholder;
- `Show Details…`;
- the notification's G number.

## Still open

- T19 / F17: the owner approves the golden re-record, or not.
- D213: the owner decides the dock-hiding trade-off and the two rows at
  1280 × 840 (implementer's questions 2 and 3).
- F36's Keep all fields VTK step, and F02 / F10 in WSL: office machine.

**Verdict:** ready for QA. T19 stays open on the owner's call.
