# GUI-12 Part A - implementation report

Plan: `docs/batches/2026-10-04-gui-12-backlog.md` Part A. Base `f4d9426` (master).
Branch `gui-12`, created in the main folder (no worktree; a temporary probe worktree
was made for A1 and removed). Owner decisions applied as given: all items in order;
A1 re-records only explained drift; A4 and A6 may edit `test_case_validate.py`; A2
order-preserving pairing approved. Commits `d7332df`..`f56076f` (7 commits).
Machine: the office PC (i7-14700, 128 GB, numpy 2.4.4, scipy 1.17.1); every heavy
suite ran alone.

## A1 - (f) the stale char goldens - DONE (step 2 not applicable)

All fourteen char suites are **green at `eb7b58c` and `f4d9426`** on this machine:
the nine the plan names, plus `test_gui_char_case_form`, both results-meta suites,
`test_char_summary`, `test_char_validation`. I ran them in three configurations: the
main folder, a worktree outside OneDrive at `eb7b58c`, and that worktree with TEMP / TMP
redirected. The HD13 end value computes to -45.3645 kPa, as committed. So no golden is
stale against the code and nothing was re-recorded. The note gives the details.

- Files: `docs/batches/2026-10-04-gui-12.goldens.md`.
- Tests: `run_suites.ps1` (scratch) = `python -u <suite>.py`, one at a time.
- Criteria:
  1. The note lists every red check at `eb7b58c` with its moving commit and class:
     **PASS**. There are no red checks here. The note records this, and that only
     `ce988f7` (owner-approved) moved a golden after `ee9a4b5`.
  2. Re-recorded suites pass, and the diff is only `char_golden/` plus the note:
     **PASS** (vacuous). `git diff --stat d7332df~1 d7332df` shows the note alone.
  3. `test_regression.py` byte-identical: **PASS** (final run).
- Commit `d7332df`.

## A2 - (g) Q1 order-preserving pairing - DONE

There is now one helper, `output/gauge_summary.pair_in_order(pts, want, dist, tol)`,
written as a dynamic programme over points × entered gauges. It pairs the points with
an increasing subsequence of the entered list: most pairs first, then the least summed
Euclidean distance, with ties going to the earlier gauge. Two places use it:
- `gauge_labels`' drop branch, through `_nearest_entered`;
- `ui/run_gauges._match`, which keeps its one-cell `tol` and the x-only distance
  (`_match_dist`).

The points >= entered branch of `gauge_labels` is unchanged. This closes D230's P4.

- Files: `blastlab/output/gauge_summary.py`, `blastlab/ui/run_gauges.py`,
  `blastlab/tests/test_gauge_summary.py` (+5), `blastlab/tests/test_ui_run_screen.py`
  (R5b +1).
- Criteria:
  1. G2 and G3 entered 0.4 cell apart, G2 dropped, survivor at G3's cell → `G3`:
     **PASS**. Case: dx 0.1; entered (1.106, 0.694), (1.201, 0.69), (1.201, 0.65);
     points (1.15, 0.65), (1.25, 0.65).
     - The greedy rule gives `G3, G2`, and an in-test check shows it.
     - Mutation (scratch `mut_a2.py`, the old greedy put back): exactly the new label
       check goes red.
  2. `test_char_summary`, `test_gui_gauge_summary`, `test_ui_results_screen` (S5g) and
     the export char suites pass unedited: **PASS**.
  3. `test_ui_run_screen` passes (218 checks), and `numbering` gives `G1, G3`, the same
     as `gauge_labels`: **PASS**.
- Commit `8fda245`.

## A3 - (a) exported gauge-trace titles - DONE

`plots.figure_gauges_nd` now titles each panel with
`gauge_summary.entered_numbers(points, meta['gauges'])`. That is new, and uses the same
numbering as `gauge_labels`. The title format `Gauge <k>  (cell x, y) m` is unchanged.
With no drop the result is the panel index, byte-identical. `figure_gauges_1d` and
`blastlab/gui/` are not edited; the Tk Gauges tab draws the same figure.

- Files: `blastlab/output/gauge_summary.py`, `blastlab/output/plots.py`,
  `blastlab/tests/test_plots_gauge_titles.py` (new, 3 checks).
- Criteria:
  1. G1-G5 entered, G2 and G3 dropped → `Gauge 1`, `Gauge 4`, `Gauge 5`. With no drop,
     the titles equal a literal of today's strings: **PASS**.
  2. `test_char_exports`, `test_ui_char_results_exports`, `test_gui_char_exports`,
     `test_gui_char_results_meta` and `test_gui_title_preview1d` pass unedited:
     **PASS**.
  3. All 16 `test_gui_*` pass, and `_qa_gui_harness.py --scenario D02` exits 0 (run
     after A3 and again at the end): **PASS**.
- Commit `eed757a`.

## A4 - (b) the drop warning names the wall - DONE

`_gauge_drop_rule` returns the 1-based index of the obstacle that drops the gauge, or 0
when it is kept. `snap_obstacles` preserves order, so the index matches the case's
obstacle list. `_in_box_closed` and `_in_obstacle_open` return indices as well.

The warning now reads `Gauge (x, y) inside Wall i - will be dropped` or
`... on the face of Wall i - ...`. The inside/face split is still the open-box test, and
"inside" names the box the gauge is inside.

The wording lives in one helper, `services.validation.gauge_drop_reason`, which
`ui/run_gauges._drop_reason` also uses. The solver's own log line is untouched.
`_qa_ui_harness` 2150 reads that solver line, not the validator's, so it is unaffected.

- Files: `blastlab/services/validation.py`, `blastlab/ui/run_gauges.py`,
  `blastlab/tests/test_case_validate.py` (owner-approved edit).
  - Changed: 2 literals and the `face` / `inside` helpers.
  - New: 10 checks.
- Criteria:
  1. `test_case_validate` passes with the new wording. Gauge in the second of two
     obstacles → `Wall 2`, for both solvers: **PASS**.
  2. For every warned gauge, `Wall i` equals `scaled_distance.where`'s wall, in 2D and
     3D, native and blastFoam (4-5 warnings per case): **PASS**.
  3. `test_char_validation`, `test_char_case_json`, `test_char_services` and
     `test_foam_writer` pass unedited. `test_ui_run_screen`, `test_layering` and the Tk
     gate also pass: **PASS**.
- Commit `78a4ab2`.

## A5 - (c) the Chain 2D stage's face check - DONE (outcome 1)

Probe: scratch `probe_a5.py`, following verifyA's method. It runs the real `solve_2d` /
`solve_3d` up to the first step on cases built by `stage_checks` / `wire()`.
- Cases: the QA case (planar) and its axisymmetric twin, at cells 0.0125 / 0.025 / 0.03
  / 0.05.
- Routes: Setup standalone; 1D → 2D (fed stage); 2D → 3D (the feeding 2D stage); and a
  fed 3D stage with an obstacle.
- 21 rows. In every row the solver's dx equals the validator's dx, and the solver's
  dropped list equals the validator's warned list: **0 mismatches**. Three samples:

| Case / route | solver dx | validator dx | solver dropped = validator warned |
|---|---|---|---|
| Setup 2D planar, cell 0.03 | 0.0124352 | 0.0124352 | (1.2,0.3) (1.4,0.3) (1.6,0.3) |
| Chain 1D→2D axisym, cell 0.05 (fed) | 0.05 | 0.05 | (1.4,0.3) (1.4,0.6) (1.6,0.3) |
| Chain 2D→3D stage 2 axisym, cell 0.05 (feeding) | 0.0285714 | 0.0285714 | (1.4,0.3) (1.4,0.6) |
| Chain 2D→3D stage 3, fed 3D, cell 0.1 | 0.1 | 0.1 | (1.4,1,0.3) (1.4,1,0.6) (1.6,1,0.6) |

- Planar 1D→2D rows: the solver raises `1D profile remap is only valid in axisymmetric
  mode`, and the stage's checks show the same error, so no run exists to disagree with.
- Explanation: a fed stage is a profile start, which the solver does not auto-refine.
  Its warnings therefore follow its own cell, not Setup's refined cell. This is correct
  behaviour and the text is unchanged.
- Recorded as D236; pinned by `test_ui_chain_screen` S5f (+5).
- Files: `blastlab/tests/test_ui_chain_screen.py`; `docs/gui-redesign-decisions.md`
  (D233-D236, commit `4fc9afd`).
- Criteria:
  1. Per case and route, solver dx / validator dx / dropped / warned: **PASS**, 0
     mismatches. The sample is above; the full 21 rows are in scratch `probe_a5.py`'s
     output.
  2. `test_ui_chain_screen` (225 checks) and `test_case_validate` pass;
     `test_char_validation` passes unedited: **PASS**.
- Commit `88b1ed5`.

## A6 - (g) Q2 the exact-tie face check - DONE

2D: native refines the case to dx 4/380, which puts x = 1.2 exactly on a cell face. The
fixed-verdict row moved to (1.1974, 0.3), a quarter cell in front of that face. The
verdicts are unchanged: native gives none, blastFoam gives the face warning.

3D: native refines to dx 2/190, which puts a cell **centre** exactly on the face
x = 1.5. That is a closed-test tie for every gauge within half a cell, and the
-1e-12 run flipped it too. Native's row moved to (1.4921, 1.0, 0.5), three quarters of
a cell in front (verdict: none). The blastFoam row is unchanged.

Each tie is pinned once as "warned <=> its solver drops it". No check is loosened.

- Files: `blastlab/tests/test_case_validate.py` (owner-approved edit).
- Criterion 1, perturbing x_c by 1e-12 flips no check: **PASS**. Scratch
  `a6_perturb.py` shifts every x face in `core.grid._faces_shared`, which moves the
  solver side and the validator together, then runs `gauge_in_obstacle_checks`.
  - New test: +1e-12, 0 and -1e-12 all give 0 failures.
  - Pre-A6 test at -1e-12: 2 failures, `2D native ... on the face` and
    `3D native ... on the face`.
- Commit `f56076f`.

## Closing matrix (one at a time, after all six tasks)

All passed, exit 0:
- **Fast suites:** `test_gauge_summary`, `test_plots_gauge_titles`, `test_char_summary`,
  `test_case_validate`, `test_char_validation`, `test_char_case_json`,
  `test_char_services`, `test_foam_writer`, `test_layering`.
- **Char suites:** `test_char_exports`, `test_ui_char_results_exports`, `test_char_hd13`,
  `test_char_hd13_cli`, `test_ui_char_case_form`, `test_ui_char_chain_wiring`,
  `test_ui_char_hd13_run`, `test_ui_char_results_meta`.
- **Qt screens:** `test_ui_run_screen`, `test_ui_results_screen`, `test_ui_results`,
  `test_ui_chain_screen`, `test_ui_setup_strip`, `test_ui_setup_form`.
- **Tk gate:** all 16 `test_gui_*`, plus `_qa_gui_harness.py --scenario D02` (exit 0).
- **Last:** `test_regression.py`, byte-identical. Then `python -m blastlab` started and
  ran for 12 s with empty stderr; it was stopped by PID.

## Files touched

- Code: `blastlab/output/gauge_summary.py`, `blastlab/output/plots.py`,
  `blastlab/services/validation.py`, `blastlab/ui/run_gauges.py`.
- Tests: `blastlab/tests/test_gauge_summary.py`,
  `blastlab/tests/test_plots_gauge_titles.py` (new), `blastlab/tests/test_ui_run_screen.py`,
  `blastlab/tests/test_case_validate.py`, `blastlab/tests/test_ui_chain_screen.py`.
- Docs: `docs/batches/2026-10-04-gui-12.goldens.md` (new),
  `docs/gui-redesign-decisions.md` (D233-D236), this report.

## GUI screens touched (for QA)

- Setup ▸ Checks, and Chain stage Checks: the drop warning text now names `Wall i`.
- 02 Run live-gauge column: labels change only in the rare close-pair drop case. The
  caption wording is unchanged, but its reason now comes from the shared helper.
- 03 Results ▸ Gauges and Export ▸ Report / Gauges .png: the gauge-trace panel titles
  change after a drop.
- Tk Results ▸ Gauges plots: the same titles. Tk code is unchanged.

## Numerical changes

None. Only labels and wording changed. `test_regression` is byte-identical, and no
golden was re-recorded.

## Engineering issues noticed

1. **The A1 red goldens are environment-dependent.** They reproduce neither here nor
   in a non-OneDrive worktree. The likely causes are the home PC's library builds or
   TEMP on D:. The -45.3536 HD13 value stays unexplained.
2. **The top-face rows still sit on exact y / z ties.** These are 2D native (1.4, 1.0)
   and 3D native (1.6, 1.0, 1.0). Shifting y_c or z_c by -1e-12 flips each of them.
   This is outside A6's literal x_c criterion, so they are left as they were.
3. **Stale worktree admin folder.** `git` prints
   `failed to delete '.git/worktrees/gui-12-probe': Permission denied` on every commit:
   OneDrive locks the folder. The worktree itself is gone and `git worktree list` is
   clean. The same happened in GUI-11e.
4. **Harness output left on disk.** `_qa_gui_harness` D02 wrote its output to
   `C:\Users\rotem.ofek\blastlab_qa\20261004-*`, its standard location. I left it there.

## Open questions for the owner

1. **A1:** run the nine char suites once on the home PC from `gui-12`, and post
   `pip freeze` for numpy and scipy?
   - *Recommendation:* yes. If only the home PC differs, either pin the library
     versions, or give the HD13 float leaves a tolerance in their suites. Do not
     re-record on either machine before then.
2. **A6 follow-up:** move the two top-face rows off their y / z ties in the same way
   (native rows off the tie, the ties pinned as validator == solver)?
   - *Recommendation:* yes, as a small test-only item; it is the same owner-approved
     pattern.
3. **Branch:** Part A is on `gui-12` in the main folder, not merged into `master`.
   - *Recommendation:* merge after Part B, and after the verifier's pass.
