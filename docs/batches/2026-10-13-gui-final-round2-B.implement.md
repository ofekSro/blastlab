# Batch gui-final-round2, Part B - implement report

Base `fbcc7f3`, branch `final-gui`. Commits `17b5747` (B1), `1ea0dce` (B2), plus this report (never
pushed). The owner's answers in the plan apply: Q4 keeps the trailing `(detail: …)` (D-R10), and D-R5
and D-R9 stand. TNT bytes and every golden are identical.

## Tasks

### B1 - DONE (`17b5747`)
Every figure title now names the charge's material.
- New `plots.charge_material(meta, material=None)` at `output/plots.py:50` returns the argument, else
  `meta['material']`, else `TNT` (D-R9). It reads no case file and writes nothing.
- `charge_label` uses it, so the 2D and 3D field, gauge and isosurface titles, the animation title and
  the Qt 2D/3D map title (`select_field`) all follow.
- `figure_results_1d` (`:296`) and `figure_gauges_1d` (`:331`) take a new keyword, `material=None`.
  `services/exports.py:201`, `:231` pass `res.meta.get('material')` in `png_figures` and
  `report_figures`.
- `ui/results_fields.py`:
  - `screen_title_1d(c, material=None)` at `:90`;
  - `FieldsView._draw_figure` (`:447`) passes the meta's material to the builder and to the short
    title, so the export-hint tooltip quotes the C4 title too.
- Number formats are unchanged (D-R5): 1D keeps `1.0`, 2D/3D keep `:g`.
- Protective pin: a scratch script printed 8 title strings before and after the change (5 `charge_label`
  metas without material or with TNT, the 1D results and gauge figure titles, and the 1D screen title).
  The sha256 matched, `A77DBDF3…`.
- Test: `blastlab/tests/test_title_material.py` (new, 23 checks), run with `cd blastlab/tests && python
  test_title_material.py`.
- Criteria:
  - 1: PASS. The new test covers:
    - C4 1D: the screen title (pure function and a real offscreen `FieldsView`) and both figures from
      `png_figures` and `report_figures`;
    - C4 2D and C4 3D: field and gauge titles, plus the 2D map title on screen;
    - planar C4: `1 kg/m C4`;
    - no material and TNT: today's strings exactly (1D, 2D, 3D, planar).
  - 2: PASS. `gate.py --changed HEAD` was 12/12 green. It did not pick up `test_ui_char_results_exports`
    or `test_char_meta`, so `gate.py --only test_ui_char_results_exports test_char_meta` was run: 2/2
    green. The `:1580` pin is untouched, and `test_ui_results_screen` is green.
  - 3: PASS at part end (see Closing matrix).

### B2 - DONE (`1ea0dce`)
The unchecked-radii warning now leads with its input.
- `_det_radii_unchecked` (`services/validation.py:1460`) takes `dims`, `dx`, `level` and `h`.
- The warning keeps its prefix and `not checked`, then reads `the cell layout could not be computed from
  the domain size (2 x 2 m) and cell size (<n> mm)`. A known level adds `at level L (h mm cells)`.
- Next comes the existing "The run still refuses …" sentence. The exception is the last clause,
  `(detail: <Type>: <msg>)` (D-R10).
- Callers:
  - the base-cell layout at `:1422` passes `ctx.dims` and the cell size it was computing with. That is
    the charge-refined `effective_dx` once that step is reached, else `cell_size_m`, or `plan.dx_base`
    on the plan branch.
  - The per-point layout at `:1447` passes `ctx.dims`, `dx_base`, and `level`/`h` when they were
    reached. `level = h = None` is set at the top of each iteration.
- A value that will not format is left out and never raised on.
- Old text: `… could not be computed (ZeroDivisionError: float division by zero). The run still refuses …`.
- New text: `… could not be computed from the domain size (4 x 4 m) and cell size (17.47 mm). The run
  still refuses … before blastFoam starts (detail: ZeroDivisionError: no level)`.
- Test: `blastlab/tests/test_det_radii_text.py` (new, 8 checks), with the same two failure set-ups as
  `test_case_validate.py:156-196` plus two direct calls (level known; no values). Run with `cd
  blastlab/tests && python test_det_radii_text.py`. It failed before the change and passes after.
- Criteria:
  - 1: PASS. The domain size and cell size come before the exception class, `not checked` is present,
    and the prefix is kept, in both set-ups.
  - 2: PASS. `test_case_validate.py` is unedited and green, including `:170` and `:194`.
    `gate.py --changed HEAD` was 9/9 green (`test_case_validate` and `test_char_validation` among them).
    `test_ui_char_case_form` was not picked, so `--only test_ui_char_case_form` was run: green.
  - 3: PASS at part end.

## Closing matrix
- `gate.py --for` on the 4 plan files at the start: 19/19 green. Note that it ran while the B1 edits were
  being typed. Those edits are label-only, and the pin above is the clean before-picture.
- `gate.py --changed fbcc7f3 --deep`: 100/100 green, 25.5 min. The WSL solve suites were not run
  (CLAUDE.md §8.6, gate default).
- `gate.py --only regression`, run last: green, `regression (byte-for-byte): PASS`.
- The app was started once on the real platform with throwaway settings, after the §8.2 dry run
  (`auto_cleanup False`). The MainWindow showed and closed cleanly.

## Files touched
`blastlab/output/plots.py`, `blastlab/services/exports.py`, `blastlab/ui/results_fields.py`,
`blastlab/services/validation.py`, `blastlab/tests/test_title_material.py` (new),
`blastlab/tests/test_det_radii_text.py` (new), this report.

## GUI screens touched (for QA)
- Results:
  - the 1D profile canvas title, plus the PNG/report export-hint tooltip;
  - the 2D/3D map titles;
  - every PNG, HTML and GIF figure title of a C4 result.
- Setup / Checks: the "Ignition radii not checked" warning text.

## Numerical changes
None. These are labels and warning text only, and regression plus every char golden is byte-identical.

## Engineering issues noticed
1. `solvers/foam/cli_run.py:392-395` (`_show_plots_1d`, the blastFoam CLI's 1D plots) still calls the 1D
   builders without `material`, so a C4 CLI run says `kg TNT` in those pop-up figures. The file is not
   in the plan's list. Recommendation: a one-line follow-up passing `res.meta.get('material')` (or
   `case.material`).
2. The native solvers accept `material` (`solver1d.py:372`, `solver2d.py:579`, `solver3d.py:660`), but
   native metas do not record it. D-R9's "native is TNT" therefore holds only while the form keeps
   material hidden in native mode. Recommendation: record `material` in native metas when P1-9 is taken
   up. That moves goldens, so it needs a probe.
3. The frozen Tk GUI shares `plots.charge_label`, so its 2D/3D titles now also name the material. Its
   1D titles do not, because `gui/results_panel.py` was not edited (frozen). No Tk suite gates this.
4. `git commit` prints `failed to delete '.git/worktrees/agent-…'` (permission denied) for six stale
   worktree entries that are not this batch's. The commits succeed. Recommendation: the owner prunes them
   (`git worktree prune`) when nothing is running.

## Open questions for the owner
None. Every choice here follows a decision row in the plan (D-R5, D-R9, D-R10).

## Status
B1 GUI-16: DONE (`17b5747`)
B2 GUI-16: DONE (`1ea0dce`)
