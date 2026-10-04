# GUI-13 Part A - verification report

Batch `docs/batches/2026-10-04-gui-13-backlog.md`, Part A, depth **full**. Branch `gui-13`,
base `b618cdb`, implementer commits `1e9e853..155142b`, verify fix `434b60f`. Owner
decisions 2026-10-04 applied as given: D1, Q1, Q2, Q3. Nothing re-recorded, no golden
touched, no blastFoam solve run (`pgrep -a blastFoam` empty before the one WSL hardware probe).

## Verdicts

| Task | Verdict | Commit |
|---|---|---|
| A1 reseed chain Lz / Q1 radius | **SKIPPED** (justified, left for the owner) | none |
| A2 F45 wording | VERIFIED | `1e9e853` |
| A3 G<n> warnings | VERIFIED | `6f28bea` |
| A4 one drop-wall rule | **FIXED** (test strength) | `492609f`, `ed2715a`, fix `434b60f` |
| A5 exported gauge grid footnote | VERIFIED | `73a0e20` |
| A6 top-face ties | VERIFIED | `62e0e39` |

## A1 - SKIPPED, the stop is justified

- Scratch `v_a1_seed.py` builds a real `ChainPanel` (throwaway settings) and validates its
  stage-3 case at Lz 1.5 and 4.0. Native, unprobed and probed: clean for both. blastFoam
  probed: clean for both. **blastFoam unprobed: Lz 4.0 gives the error `~1,227,303 cells
  exceeds the blastFoam cap of 1,113,510 ...`; Lz 1.5 gets none.** Acceptance 2 fails, so
  D2's stop rule applies, as the implementer reported.
- Q1's radius seed: `blastlab/tests/char_golden/ui_chain_wiring.json:161,378,743` pin stage
  1's `"radius_m": "10.0"`. The plan does not name that golden, so the seed cannot land
  without a re-record the owner has not approved. Confirmed.
- Working tree carries no A1 leftovers (`chain_panel.py` unchanged since base).

## A2 - VERIFIED

- C1: `test_ui_chain_screen.py` exit 0 (233). The equal case (Lz 2.0) still warns (S5r).
- C2: `rg "burst is at z|burst height, z" blastlab/ui` finds nothing.
- Labels checked against `ui/setup_spec.py:559-563` (`AXISYM_LABELS`: cy `Burst z [m]`,
  Ly `Height H [m]`) and `:461-503` (3D `Lz [m]`, `Burst z [m]`). The deviation from D3's
  literal (`Burst y` / `Ly`) is reasoned and the planar branch keeps D3 exactly; owner
  question 1 below.
- Mutations (worktree, restored): trigger `<` -> `<=` fails S5r; advice using the burst
  height instead of Ly fails three checks.

## A3 - VERIFIED

- C1: `test_case_validate.py`, `test_char_validation.py`, `test_ui_chain_screen.py` exit 0.
- C2: `rg "Gauge \{tuple|Gauge \(" blastlab/services` finds nothing. Remaining `Gauge (...)
  outside domain` strings are the solver logs (`solvers/solver2d.py:284`, `solver3d.py:342`),
  outside the task.
- C3: all 16 `test_gui_*` exit 0.
- Test diffs read: the A4 regex at `test_case_validate.py:773` and S5f `warned()` skip a
  warning whose coordinates do not match, but the count check `len(walls) == len(got)` and
  S5f's exact lists still catch that, so nothing is loosened. `test_char_validation.py:240`
  is the Q2-approved wording change only.
- Mutations: 0-based `G<n>` fails `test_case_validate`; `:.1f` coordinates fail
  `test_char_validation`.

## A4 - FIXED (`434b60f`)

- **Defect (medium, fixed):** acceptance 1's check (`test_ui_setup_strip.py:569-579`,
  gauge x 1.628 between Walls 1.2-1.61 / 1.64-2.0) names Wall 1 under the old
  "first wall within a cell" heuristic too, so it passed with `run_gauges._drop_reason` not
  calling `drop_wall` at all (scratch `v_a4_discrim.py`: "run w/o rule on the face of
  Wall 1"). Added a case where they disagree: Wall 1 x 1.0-1.22, Wall 2 x 1.26-1.6, gauge x
  1.252, blastFoam 0.05 m cells - warning, `drop_wall` and `_drop_reason` all say Wall 2;
  the heuristic says Wall 1. Mutation `wall = 0` in `_drop_reason` now fails the suite.
- C1 PASS (with the fix). C2 PASS: `4 cm in front of Wall 1 (dropped)`; mutating the suffix
  away fails `test_ui_setup_strip`. C3 PASS: `rg "outside domain" blastlab/services
  blastlab/ui` finds nothing; A3 suites and `test_ui_run_screen.py` exit 0.
- `drop_rule` on Results meta views (scratch `v13a_meta_rule.py`, 2D/3D, profile or
  charge, with and without solver / eos, a bad eos): returns 0, never raises.
  Mutation "rule always keeps" fails `test_case_validate`.

## A5 - VERIFIED

- C1: `test_plots_gauge_titles.py` exit 0. Mutations "no footnote" and "footnote without a
  drop" each fail two checks. Saved PNG (scratch `v13a_gauges_drop.png`): footnote below
  the grid, not clipped; titles `G1 (0.83, 0.61) m → cell (0.82, 0.62)`.
- C2: 21 char suites exit 0, unedited except the Q2 line in `test_char_validation.py`;
  `char_golden/` untouched.
- C3: 16 `test_gui_*` exit 0. Mutation "Qt note not passed" (`ui/exports.py`) fails
  `test_ui_results_screen` S5g.
- `export_drop_note` runs in `ui/exports.export` before the worker starts (GUI thread);
  it reads no widget.

## A6 - VERIFIED

- C1: `test_case_validate.py` exit 0.
- C2: implementer's `gui13_a6_perturb.py` re-run (it patches `core.grid._faces_shared`,
  which both `grid.py` and `validation.py:1674` resolve at call time): HEAD 0 / 0 / 0
  failures at +1e-12 / 0 / -1e-12; pre-change test (`62e0e39^`) 0 / 0 / **2** (2D and 3D
  native top-face rows). Both tie pins kept (`got in ([], face(...))` and warned <=> drops).

## Tests run (all exit 0)

`test_case_validate`, `test_char_validation`, `test_plots_gauge_titles`,
`test_ui_chain_screen` (233), `test_ui_chain`, `test_ui_char_chain_wiring`,
`test_ui_setup_strip` (135), `test_ui_setup_form`, `test_ui_run_screen`,
`test_ui_results_screen` (221), `test_ui_results`, `test_foam_writer`, `test_refine`,
`test_out1_qa_polish`, 16 `test_gui_*`, 21 char suites, then `test_regression.py`:
REGRESSION PASS, byte-identical. `_qa_gui_harness.py` not re-run (the implementer ran it;
the Tk path is covered by the 16 suites).

## Defects

1. `blastlab/tests/test_ui_setup_strip.py:569-579` - A4 check could not fail for its claim.
   Medium. Fixed `434b60f`.
2. `blastlab/services/validation.py:1631-1633` - `drop_rule` swallows Arithmetic / Attribute /
   Index / Type / Value errors and returns "keeps". Deliberate (meta views fall back), low;
   not fixed.
3. `.git/worktrees/v13a_wt` - the verify worktree is removed and pruned from `git worktree
   list`, but its admin folder cannot be deleted (Permission denied, same as
   `gui-12-probe`). Harmless; the owner can delete both folders.

## Engineering questions (owner)

1. **A2 labels:** keep the axisymmetric form's `Burst z` / `Height H` (what the user sees)
   over D3's literal `Burst y` / `Ly`? Verifier agrees with the implementer: keep.
2. **A1:** choose among the implementer's options (a)-(c); the Q1 radius seed needs approval
   to re-record `char_golden/ui_chain_wiring.json` (three `radius_m` strings 10.0 -> 1.5).
3. **Where vs drop wall** (implementer issue 2): for x 1.628 between Walls 1 / 2, Where says
   `1 cm in front of Wall 2 (dropped)` while Checks and Run say Wall 1.

## GUI screens for QA

Chain stage 3 Checks and card (longer F45 sentence - wrapping), 02/03 hand-off IN captions;
01 Setup Checks strip (`G<n> (x, y) m ...`) and Gauges Where column `(dropped)`; 02 Run
dropped-gauge caption; exported PNG / HTML report gauge grid with a drop; Tk Setup warnings.

**Verdict:** Part A is sound - A2, A3, A5, A6 verified, A4 fixed (one test-strength gap), A1
correctly skipped under D2 and left for the owner.
