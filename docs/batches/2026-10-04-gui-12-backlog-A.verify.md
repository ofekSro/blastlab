# GUI-12 Part A - verification report

Plan `docs/batches/2026-10-04-gui-12-backlog.md` Part A, depth **full** (risk high).
Implementer report `2026-10-04-gui-12-backlog-A.implement.md`. Branch `gui-12`,
commits `d7332df`..`45fe2d9`, base `f4d9426`. Office PC (128 GB, numpy 2.4.4, scipy
1.17.1, matplotlib 3.10.8); every suite run alone, `python -u`, own scratch runner.
Cleanup dry run before any GUI build: `False`, empty plan.

## Verdicts

| Task | Verdict | One line |
|---|---|---|
| A1 | VERIFIED | Every char suite green at HEAD on this machine; no golden touched since `ce988f7`; nothing re-recorded. |
| A2 | FIXED | Pairing correct (brute-force 3000 cases, 0 mismatches); one doc count fixed in D233. |
| A3 | VERIFIED | Titles carry the entered number on a real native drop; no-drop literal unchanged. |
| A4 | VERIFIED | `Wall i` wording, Wall 2 and `where` checks red under two mutations. |
| A5 | VERIFIED | Independent probe: 18 rows, solver dx = validator dx, dropped = warned, 0 mismatches. |
| A6 | VERIFIED | x faces +-1e-12: 0 failures (pre-A6 test: 2). |

## Per criterion

### A1
1. Note lists red checks with moving commit and class: the note says none are red on
   this machine. Reproduced: all 14 char suites listed in the note pass at HEAD (logs
   below). `git diff eb7b58c f4d9426` = the plan file only, so HEAD's code = `eb7b58c`'s
   for these suites. `git log ee9a4b5..HEAD -- blastlab/tests/char_golden` = `ce988f7`
   only.
2. `git diff f4d9426 HEAD --stat -- char_golden baseline foam_golden foam_fixtures
   blastlab/gui` is empty: nothing was re-recorded (vacuous pass, as the report says).
3. `test_regression.py`: REGRESSION PASS, byte-identical (run last).

### A2
1. `test_gauge_summary` passes; mutation (`_nearest_entered` set back to greedy,
   scratch `v_mutate.py a2`) turns exactly `A2: order-preserving pairing labels the
   survivor at G3's cell G3, not G2` red.
   - Extra: scratch `v_dp_brute.py` compares `pair_in_order` with a brute force over
     every order-preserving partial matching (3000 random cases, with and without
     `tol`): most pairs and least summed distance agree in every case.
2. `test_char_summary`, `test_gui_gauge_summary`, `test_ui_results_screen`, and the
   export char suites pass. The diff does not touch any of them.
3. `test_ui_run_screen` passes, including the new R5b check `numbering` = `gauge_labels`.

### A3
1. `test_plots_gauge_titles` passes. Mutation (`entered_numbers` made plain): both drop
   checks go red. On a real native 2D run (scratch `v_a3_real.py`: G2 inside Wall 1 is
   dropped by `solve_2d`), the result is:
   - titles `Gauge 1`, `Gauge 3`, `Gauge 4`;
   - `meta['gauges']` is present;
   - `gauge_labels` gives the same G1, G3, G4.
2. `test_char_exports`, `test_ui_char_results_exports`, `test_gui_char_exports`,
   `test_gui_char_results_meta` and `test_gui_title_preview1d` all pass, unedited.
3. All 16 `test_gui_*` pass. `_qa_gui_harness.py --scenario D02` exits 0 with
   `pending: []`. `blastlab/gui/` is not edited.

### A4
1. `test_case_validate` passes. Mutations (scratch `v_mutate.py a4`, `a4b`) and what
   goes red:
   - wording forced to `Wall 1`: the four Wall-2 / `where` checks and two more (6 red);
   - index discarded in `_in_box_closed` and `_in_obstacle_open`: the same 6 red;
   - reversed box order with the index remapped (a sanity control): 0 red.
2. The `where` equality check is part of the six above. I checked
   `snap_obstacles` (`core/refine.py:328`): it keeps the order and never filters, so the
   index is the case's index.
3. `test_char_validation`, `test_char_case_json`, `test_char_services`,
   `test_foam_writer`, `test_ui_run_screen`, `test_layering` and the Tk gate all pass.
   `_qa_ui_harness.py:2150` reads `inside an obstacle` from the solver log line, and
   that line is untouched (`solver2d.py:289`), so the harness is unaffected.

### A5
1. I wrote my own probe (scratch `v_probe_a5.py`). It runs the real `solve_2d` /
   `solve_3d` up to `run_started`, which comes after gauge setup. It reads the solver dx
   from `x_face`. The validator dx is taken from `_faces_shared` inside
   `_gauge_drop_rule`. Real profiles feed the fed stages: a real `solve_1d` for p1, and
   a real short 2D run for p2.
   - Cases: the QA case (planar) and its axisymmetric twin at cells 0.0125 / 0.025 /
     0.03 / 0.05, plus a fed 3D stage with an obstacle at cells 0.1 / 0.05.
   - Routes: Setup; 1D → 2D (fed stage); 2D → 3D (the feeding stage); 2D → 3D (the fed
     3D stage).
   - Result: 18 rows, **0 mismatches**.
   - Examples: Setup axisym at cell 0.05 refines to 0.0285714 and drops (1.4,0.3)
     (1.4,0.6). The same case as the fed 1D → 2D stage keeps dx 0.05 and drops
     (1.4,0.3) (1.4,0.6) (1.6,0.3). In every row the warned list equals the dropped
     list.
2. `test_ui_chain_screen` (S5f) passes, and so does `test_case_validate`.
   `test_char_validation` passes unedited.

### A6
1. Scratch `v_perturb.py` shifts the x faces in `core.grid._faces_shared` by +1e-12, 0
   and -1e-12. This moves the solver side of `solver_drops` and the validator together.
   - New test: 0 failures for all three shifts.
   - Pre-A6 test (`f56076f~1`) at -1e-12: 2 failures, so the check bites.
   - Both tie pins require `got in ([], face(...))` and warned <=> dropped, so neither
     tie pin was loosened.

## Fixes

- `644afd9` fix(verify): D233 counted "+6" new `test_gauge_summary` checks; the A2
  commit adds 5 (`docs/gui-redesign-decisions.md:70`).

## Defects

| # | Where | Severity | State |
|---|---|---|---|
| 1 | `docs/gui-redesign-decisions.md:70` D233 check count | low (doc) | fixed `644afd9` |
| 2 | `blastlab/services/validation.py:1576`: a face warning names the first containing (snapped) box, while `scaled_distance.where` names the nearest box by gap. They can differ only when two walls sit within a cell of each other (blastFoam snapping). | low | not fixed; outside the plan |
| 3 | `blastlab/tests/test_case_validate.py`: the top-face rows still sit on exact y / z ties. Faces shifted -1e-12 in y flip `2D native: a gauge on the top face`; shifted in z, they flip `3D native: ... top face`. | low (test fragility) | not fixed; outside A6's x_c criterion (implementer Q2) |

No silent excepts were added, no widgets are touched off the GUI thread, and no
numbers, units or signs changed. Every caller of `figure_gauges_nd` (Qt exports, Tk
results panel, legacy) passes a meta that carries `gauges`, or else falls back to the
index.

## Engineering questions

1. A1: the home-PC drift in HD13 (-45.3536 against the committed -45.3645 kPa) is still
   unexplained, and this machine reproduces the golden. Two options: run the nine char
   suites once on the home PC from `gui-12`, or pin a tolerance. Do not re-record.
2. A6 follow-up (defect 3): move the two top-face native rows off their y / z ties in
   the same way?

## Tests run (all exit 0, one at a time)

- Fast: `test_gauge_summary`, `test_plots_gauge_titles`, `test_char_summary`,
  `test_case_validate`, `test_char_validation`, `test_char_case_json`,
  `test_char_services`, `test_foam_writer`, `test_layering`.
- Char: `test_char_exports`, `test_ui_char_results_exports`, `test_char_hd13`,
  `test_char_hd13_cli`, `test_ui_char_case_form`, `test_ui_char_chain_wiring`,
  `test_ui_char_hd13_run`, `test_ui_char_results_meta`.
- Qt: `test_ui_run_screen`, `test_ui_results_screen`, `test_ui_results`,
  `test_ui_chain_screen`, `test_ui_setup_strip`, `test_ui_setup_form`,
  `test_ui_no_vtk_in_main`, `test_ui_no_mpl_pyplot`.
- Tk gate: all 16 `test_gui_*`, plus `_qa_gui_harness.py --scenario D02` (exit 0,
  output in `C:\Users\rotem.ofek\blastlab_qa\20261004-1836`).
- Last: `test_regression.py`, PASS, byte-identical.

## GUI screens that need QA

- Setup ▸ Checks and Chain stage Checks: the drop warning now names `Wall i`. Check
  that the longer line is not clipped at 1100 × 720.
- 03 Results ▸ Gauges, Export ▸ Report / Gauges .png, and Tk Results ▸ Gauges: the
  panel titles after a drop.
- 02 Run live-gauge column: the labels in the close-pair drop case.

**Verdict:** Part A holds. All six tasks meet their criteria. There was one doc fix, and
two low test or edge items are left for the owner.
