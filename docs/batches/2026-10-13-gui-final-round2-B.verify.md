# Batch gui-final-round2, Part B - verify report (full depth)

Range verified: `fbcc7f3..0ea6314` (B1 `17b5747`, B2 `1ea0dce`, implement report `0ea6314`), branch
`final-gui`. Verifier fix: `612e5d3`. Never pushed. No WSL used: Part B needs none, and another
session was running 1D solves under `/root/mpi1d_probe`. `docs/verification/1d-mpi-probe.md` is
theirs and was left alone.

## Tasks

### B1 - FIXED (`612e5d3`)
Every figure title on screen and in exports now names the charge's material.
- Criterion 1 (new `test_title_material.py`): **PASS**. Run on HEAD it is green. A/B in a scratch
  worktree at `fbcc7f3`, with the new test copied in, fails 8 C4 checks: 1D export figures, 2D/3D
  field and gauge titles, the 2D map, planar `kg/m C4`, and the `screen_title_1d` signature. The
  TNT / no-material controls pass there too, so they pin today's strings. The worktree is removed.
- Criterion 2 (byte-identical char suites): **PASS**. `test_ui_char_results_meta`,
  `test_ui_char_results_exports`, `test_char_exports`, `test_char_meta`, `test_export_numbers_1d`,
  `test_ui_results_screen` and `test_ui_results` were all in the deep run, all green. No golden and
  no committed test is in the diff, and the `:1580` pin is untouched.
- Criterion 3: **PASS**. `gate.py --changed fbcc7f3 --deep` was 100/100 green in 20.9 min (WSL solve
  suites skipped by default). It ran after the fix. `gate.py --only regression` ran last:
  `regression (byte-for-byte): PASS`.
- Diff review: the change is labels only. `charge_material` is
  `material or meta.get('material') or 'TNT'`. There are no numbers, units or swallowed errors. No
  meta is written, and the test checks that. The remap labels are unchanged.
- **Fix `612e5d3`** (implementer open item 1): `solvers/foam/cli_run.py:392-398` (`_show_plots_1d`)
  now passes `res.meta.get('material')` to both 1D builders, as `services/exports.py` does. Before
  the fix, a C4 blastFoam CLI run said `kg TNT` in its pop-ups. That broke B1's goal of naming the
  material in every title. The fix is a pass-through, and with no material the default is still
  TNT, so no golden moves. No suite imports `cli_run.py` (`gate.py --for` picks 0), so
  `test_title_material.py` gained `check_cli_1d`. It patches the backend check and `adopt_figure`.
  With the pass-through removed by hand, the check fails (`1.0 kg TNT` on the C4 results figure).
  With it restored, the check passes.
- Grep of `ui/`, `services/`, `output/` and `solvers/` finds no other figure title with a `kg TNT`
  literal. What remains is form labels (`setup_spec.py:471,485,563,570`), native solver logs and
  `cli.py` prompts. Those belong to the rest of P1-9 (the plan's backlog), not to B1.

### B2 - VERIFIED
- Criterion 1 (new `test_det_radii_text.py`): **PASS** on HEAD. On `fbcc7f3` both set-up checks fail
  with the old `(ZeroDivisionError: …)` text, and the direct-call check raises `TypeError`
  (unexpected `dims`), so the test can fail. Printed text: `Ignition radii not checked - the cell
  layout could not be computed from the domain size (2 x 2 m) and cell size (6.579 mm). The run
  still refuses … before blastFoam starts (detail: ZeroDivisionError: float division by zero)`.
- Criterion 2: **PASS**. `test_case_validate.py` is not in the diff, and it, `test_char_validation`
  and `test_ui_char_case_form` were green in the deep run.
- Criterion 3: **PASS** (as for B1).
- Diff review (`services/validation.py:1403-1495`): `dx` and `level`/`h` are initialised before
  each `try`, so the warning cannot raise NameError. A value that does not format is caught by
  `TypeError`/`ValueError` and dropped. That is a choice about display only, and the warning is
  still raised. The B11 pins (`'layout failed' in`, `'ZeroDivisionError' in`) still hold.

## Defects

| Where | Severity | State |
|---|---|---|
| `solvers/foam/cli_run.py:392-395`: CLI 1D pop-ups said `kg TNT` for C4 | low (CLI only) | fixed `612e5d3` |

## Implementer's open items, judged
1. CLI 1D pop-ups: fixed in place (above).
2. Native metas carry no material. This is correct today. The Qt form shows `material` only in
   blastFoam mode (`ui/setup_spec.py:475`, `:488`, `scope='blastfoam'`, D210/D138), so a native
   result is TNT and the TNT fallback is exact. Recording it is P1-9 work and would move goldens,
   so it needs a probe. Nothing to do now.
3. Frozen Tk GUI: through the shared `plots.charge_label`, its 2D/3D titles now name the material,
   while its 1D titles (`gui/results_panel.py:543-544`, `:668-669`) still say `kg TNT`. This is
   acceptable. It follows P1-9 decision 1 (`TODO.md:362-363`, "Tk and Qt both"), it is not a
   regression for TNT, and no Tk suite gates it (CLAUDE.md §9). `blastlab/gui` was not edited.
   The 1D gap in Tk stays as frozen.

## Observations (not defects; for the next QA/UX pass)
- B2 names the cell size the layout was computing with, as the plan asks (`dx` at `:1420`). That
  is the charge-refined `effective_dx` (or the plan's `dx_base`), not the form's cell size. A user
  who typed 20 mm reads `cell size (6.579 mm)`. The wording could say "base cell" or "refined
  cell" if the UX pass flags it.
- D-R9 (owner-approved) takes the material from the meta only, while the method card falls back to
  the case (`ui/results_method.py:131`). A blastFoam result whose stored meta has no `material`
  (an old run, if there is one) would show `kg TNT` in the title and the real material in the
  card. QA can check by loading an older C4 run.
- `git commit` warns `failed to delete '.git/worktrees/…'` for six stale entries that are not from
  this batch, as the implementer noted. My own scratch worktree is removed, metadata included.

## Engineering questions
None.

## GUI screens for QA
- Results: the 1D canvas title and the export-hint tooltip, the 2D/3D map titles, and the
  PNG/HTML/GIF titles, for a C4 blastFoam 1D and 2D result against a TNT result.
- Setup / Checks: the "Ignition radii not checked" warning.

## Verdict
Part B is sound: labels and warning text only, every golden and the regression byte-identical, and
one CLI title gap fixed in place.

## Status

- B1 GUI-16: FIXED 612e5d3
- B2 GUI-16: VERIFIED
