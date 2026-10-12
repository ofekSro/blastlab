# Implementation report - P1-23 ignition radius, Part A (A1-A6)

Branch `final-gui`, base `39eac24`. Part B (B1) not done here, by instruction. Owner
decisions applied: Q1 (A2's run-time fit) and Q2 (A5, blastFoam's trigger disabled on a
dropped gauge).

## Per task

### A1 - DONE - `4812689`
New fast suite `blastlab/tests/test_foam_ignition.py` pins today's written radius for the
P1-23 case (9.0 mm), F05 (11.25 mm), F06 (11.25 mm), and the P1-23 `dx_charge` (0.01 m).
Committed alone, before any code change.
- Test: `cd blastlab/tests; python test_foam_ignition.py`.
- Criterion "exits 0, committed alone": PASS (run before the commit; the commit holds
  only the test).

### A2 - DONE - `41f52ba`
`writer.fit_det_radii` (`writer.py:1506`, with `written_det_radii` / `with_det_radii`
and `FOAM_SMALL`) refits a radius that lights no centre to (d1 + d2)/2 over the nearest
two shells (shell tolerance 1e-6 relative). `backend._fit_ignition` (`backend.py:331`),
called from `_preflight` after the stage loop and before `build_remap` when
`spec.lmax or spec.amr`, reads `0/C`, rewrites only the `radii` line in `spec.files` and
on disk, and logs one `[note]` per fitted point. Docstrings cite guide 5.6.1 (p. 71) and
`activationModel.C:111-137` (read in WSL, read only).
- Files: `solvers/foam/writer.py`, `solvers/foam/backend.py`, `tests/test_foam_ignition.py`.
- Tests: `test_foam_ignition.py`, `test_foam_writer.py`, `test_foam_amr_ingest.py`;
  `gate.py --changed HEAD` 21/21 green.
- Criterion 1 (synthetic centres: P1-23 radius in (20.39, 34.87) mm, 1 cell; F05 4; F06 8;
  a lighting radius unchanged; only the radii line differs): PASS (27.64 / 49.55 /
  63.11 mm on the synthetic sets).
- Criterion 2 (writer, amr_ingest exit 0; `foam_golden/` byte-identical): PASS (the golden
  compare in `test_foam_writer.py`, `git status` clean on `foam_golden/`).

### A3 - DONE - `1c49104`
`validation._validate_det_radii` (`validation.py:1349`), called at the end of
`_validate_refinement` once `ctx.plan` is known: for a blastFoam charge case with explicit
`det_radii`, per point an error when r <= the nominal nearest-centre distance (level from
new `core/refine.level_at`, `refine.py:383`, for static zones; `plan.amr` for AMR; 0
uniform, base cell rebuilt as the writer does). A zero radius (blastFoam's findCell
branch) is not checked. `_fit_ignition` raises before blastFoam for an explicit radius
that lights no real centre (point, nearest centre in mm, `case kept at`), file untouched.
- Files: `services/validation.py`, `core/refine.py`, `solvers/foam/backend.py`,
  `tests/test_case_validate.py` (new `det_radius_reach_checks` only),
  `tests/test_foam_ignition.py`.
- Tests: `test_case_validate.py`, `test_foam_ignition.py`, `test_char_validation.py`;
  `gate.py --changed HEAD` 28/28 green.
- Criterion 1 (F05 5 mm: error naming point 1 and 8.8 mm; 20 mm validates; `:89` case
  validates): PASS ("8.84 mm away (level 3, 12.5 mm cells)").
- Criterion 2 (explicit radius lighting nothing raises, file unchanged): PASS (18 mm on
  P1-23: passes the nominal check, refused at run time naming 20.4 mm).
- Criterion 3 (`test_char_validation.py` exit 0): PASS.

### A4 - REVERTED by its pre-registered rule - `35b145d`, revert `83b6a7c`
`CaseSpec.dx_charge` used the level at the charge centre for static refined cases, the
validation mirror followed, and `vtk_export` took the finest cell explicitly. Criterion 1
(P1-23 `dx_charge` 0.02 m, radius still 9.0 mm, goldens identical) and criterion 2
(suites green, including the deep gate) PASSED. Criterion 3, the rule: both mesh-stage
runs set 48.88 kg of 100 (0.4888 both); |1 - after| = |1 - before|, not smaller, so the
commit was reverted as the plan requires. The A1 pin is back at 0.01 m with the revert.

### A5 - DONE - `cf7e520`
`backend._trigger_cells(case, coords, shape, kept=None, hooks=None)` (`backend.py:1835`).
When it gets the writer's kept list (`spec.gauge_ids`), it disables a trigger on a dropped
gauge through `hooks.trigger_index`, so the native warn line is logged. Both solve paths
pass it. In `validation.py` (was `:1605`) the `not foam` guard is gone, so "Trigger
disabled" now covers both solvers.
- Files: `solvers/foam/backend.py`, `services/validation.py`, new
  `tests/test_foam_trigger_drop.py`, and `tests/test_trigger_numbering.py` (one check
  inverted, see the open questions).
- Tests: `test_foam_trigger_drop.py`, `test_bc_trigger.py`, `test_trigger_numbering.py`;
  `gate.py --changed HEAD` 23/23 green.
- Criterion 1 (without the kept list the low-face cell is fluid; with it every dropped
  trigger gives (None, None) plus a `dropped` log and a kept gauge's cell is unchanged,
  2D and 3D): PASS.
- Criterion 2 (`validate_case` warns `Trigger disabled` naming `G<n>`, blastFoam): PASS.
- Criterion 3 (`test_bc_trigger`, `test_trigger_numbering` exit 0): PASS.

### A6 - DONE - `1a504e7`
New `blastlab/tests/_e2e_foam_ignition.py`, run with `python -u` in the background. The
VM was checked free before every solve and nothing was deleted. The second full run
exited 0. The first run stopped at the control (see the open questions).
- Criterion 1 (cases 1-3 log the fit and write after t = 0; 1 and 2 fit the same): PASS.
  P1-23 9 -> 27.63 mm, 1 cell (nearest 20.39 mm), the same serial and np4. F05 11.25 ->
  49.55 mm, 4 cells. F06 11.25 -> 54.13 mm, 8 cells. All write 1.8e-05 ... 2e-05.
- Criterion 2 (the control logs no fit, and its `phaseProperties` on disk equals the
  rendered file): PASS for `case2d_planar_refine` and `case3d_refine` (deviation, below).
- Criterion 3 (A4's ratios printed, rule applied, wall times and folders recorded): PASS.
  Before 0.4888, after 0.4888, so A4 was reverted.
- Wall times [s]: P1-23 serial 693, np4 231, F05 21, F06 148, controls 26 / 110, mesh
  stages ~30 each.
- Folders (`/root/blastlab_runs/`): `20261012-113515_2d_p64456-00` (P1-23 serial),
  `-114648_2d_p64456-01` (np4), `-115039_2d_p64456-02` (F05), `-115100_3d_p64456-03`
  (F06), `-115329_2d_p64456-04` / `-115355_3d_p64456-05` (controls),
  `-115545_2d_p64456-06` / `-115612_2d_p64456-07` (A4 before / after). Run 1 left
  `20261012-111516_2d_p27792-00` to `-113009_3d_p27792-03`.

## Closing matrix
- `gate.py --changed 39eac24 --deep`: 119/119 green in 28.1 min, including the nine Tk
  `test_gui_*` suites (run with A4 still in).
- After the revert, `gate.py --changed 35b145d`: 31/31 green.
- `gate.py --only regression`, run last: PASS, byte for byte.
- The app starts. A `MainWindow` was built offscreen under `private_settings` and
  showed `untitled · BlastLab`. The §8.2 dry run printed `auto_cleanup False` first.
- The planner's `docs/batches/2026-10-12-gui-final*.md` files were never staged.

## Files touched
`blastlab/solvers/foam/writer.py`, `blastlab/solvers/foam/backend.py`,
`blastlab/services/validation.py`, `blastlab/core/refine.py`; tests
`test_foam_ignition.py` (new), `test_foam_trigger_drop.py` (new),
`_e2e_foam_ignition.py` (new), `test_case_validate.py` (new checks),
`test_trigger_numbering.py` (one check inverted). `vtk_export.py` and
`test_foam_writer.py` were changed by A4 and are back as they were after the revert.

## GUI screens touched (for QA)
There is no widget code. Setup's Checks strip gains the new `Detonation point k: ignition
radius ...` error (explicit `det_radii`) and the blastFoam `Trigger disabled` warning. The
Run log gains the `[note] detonation point k: ... fitted to ...` line and, for a refused
explicit radius, the run-time error.

## Numerical changes
- The seed radius, only where the default lit no cell (those runs used to abort at t = 0):
  P1-23 9 -> 27.63 mm, F05 11.25 -> 49.55 mm, F06 11.25 -> 54.13 mm (measured, A6).
  Source: plan D1/D2 and guide 5.6.1. Every run that ignited before keeps a byte-identical
  `phaseProperties` (both controls).
- A4's scale (P1-23 0.9967187227 -> 0.9805418327) was reverted, so no net change.
- Goldens, `char_golden/` and `baseline/` are unchanged.

## Engineering issues noticed
1. Every axisymmetric case with refinement at the charge probably needs the fit. The
   refined axis cell's centre sits at about 0.89 h (17.78 mm at h = 20 mm), not 0.75 h.
   So the default 0.9 h only lights it when the point is at a cell centre in y.
   `case2d_axi_refine`'s seed (45 mm at h = 50 mm, the point on a y face) looks dark too.
   A2 now covers this at run time.
2. 2D blastFoam runs that end at an explicit `t_end` report `stop: safety cap`, while 3D
   reports `end time reached` (A6, all 2D cases). The label looks wrong; I did not touch
   it.
3. `_scan_set_mass` prints the ratio to 2 decimals against the full request. A
   wall-truncated charge reads 0.49, and 0.979 against 0.984 cannot be told apart in that
   note, so A6 parses the mass instead.
4. The ratio is identical across scale 0.9967 / 0.9805 on P1-23. The 0.02 m model
   predicted 0.979 -> 0.984, but on the real mesh the mass scale is insensitive there.
5. A 3D case with extra charges, no `det_points` and `det_radii` has a mismatch. The
   N5-12 block demands 1 radius, while the writer lights every charge centre with the
   radii given. This predates the batch and I did not touch it.
6. The trigger on a low face is an argmin tie, settled by rounding: it sampled the wall on
   a 0.05 m 3D grid and the fluid on a binary-exact 1/16 m one. This supports Q2.

## Deviations and open questions for the owner
1. **A5 edited a committed test.** `test_trigger_numbering.py:170` asserted "blastFoam gets
   no such warning (D13, native only)". That is the exact behaviour Q2 replaces, so A5's
   own criterion 3 could not pass without the edit. The check now asserts the same warning
   for blastFoam. Recommendation: accept (it is a direct consequence of Q2).
2. **The A6 control was swapped.** The plan's `case2d_planar_amr` is text-only as a golden
   and `validate_case` refuses it (the charge needs AMR level 4), so it never starts. I
   used `case2d_planar_refine` and `case3d_refine` instead (static zones, charge on a node
   of the deepest zone). Recommendation: accept.
3. **`test_case_validate.py :89` case.** The plan gave its nearest centre as 3.35 mm. With
   the 2/3 h axis rule it computes as 4.44 mm. Both radii (10 / 20 mm) still validate.
   Recommendation: none needed.
4. **A4 reverted.** The P1-23 `dx_charge` stays at the global fine 0.01 m (and the
   `Charge cells` note at 475 cells, ~1.00). This is a modelling mismatch only, with no
   effect on the deposited mass measured here. Recommendation: leave it unless a case
   shows a mass difference.
5. **TODO acceptance on test coverage.** The TODO wanted a new `test_foam_writer.py` case
   that pins the radius of a charge outside the deepest zone. That pin left with the A4
   revert, and `test_foam_ignition.py` A1 still pins 9.0 mm. Recommendation: treat A1 as
   that pin.
