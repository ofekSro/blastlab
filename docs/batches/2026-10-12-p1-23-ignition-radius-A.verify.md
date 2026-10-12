# Verification report - P1-23 ignition radius, Part A (A1-A6)

- Branch `final-gui`, range `39eac24..40167eb` (`7e7f0d4`, the Parts B-F plan, not verified).
- Depth: **full** (plan `risk: high`). Verifier: fresh session, 2026-10-12.
- Owner decisions taken as given: Q1 (the run-time fit) and Q2 (blastFoam's trigger disabled
  on a dropped gauge) approved, and text-only pin edits approved.
- **No fixes were needed.** No verifier commit touches code; the only commit is this report.

## Per task

| Task | Verdict | Commits |
|---|---|---|
| A1 seed characterisation | VERIFIED | `4812689` |
| A2 run-time fit of a dark default radius | VERIFIED | `41f52ba` |
| A3 explicit radius refused (validation + run time) | VERIFIED | `1c49104` |
| A4 charge-level mass scale | VERIFIED as REVERTED by its rule | `35b145d`, revert `83b6a7c` |
| A5 blastFoam trigger on a dropped gauge | VERIFIED | `cf7e520` |
| A6 real solves | VERIFIED | `1a504e7` |

### A1
- Exits 0, committed alone: `git show --stat 4812689` holds only the new test. The pins
  (9.0 / 11.25 / 11.25 mm, `dx_charge` 0.01 m) pass in the deep gate.

### A2
- Criterion 1 (synthetic centres; P1-23 in (20.39, 34.87) mm with 1 cell, F05 4, F06 8; a lit
  radius unchanged; only the `radii` line differs): `test_foam_ignition.py` green. **Mutation:**
  with `fit_det_radii` made a no-op (in a throwaway worktree), 12 checks fail, so the test can fail.
- Criterion 2 (`test_foam_writer`, `test_foam_amr_ingest` green, `foam_golden/` byte-identical):
  deep gate green; `git diff --stat 39eac24..40167eb -- foam_golden baseline char_golden
  foam_fixtures` is empty.
- References checked: the guide, sec. 5.6.1 (`BlastFoam_User_Guide.txt:2905-2908`, p. 71), reads
  "the cells within the charge with the radii specified are set to full activated". The installed
  `activationModel.C:111-137` (read in WSL, read only) has `radius_ > small`, then
  `mag(C - pt) < radius_` with a global `returnReduce`, the "No cells will be activated" fatal, and
  the `findCell` branch for a zero radius. The docstrings cite both correctly.
- Resume safety: `resume_run` and `postmortem.load_run` set `spec.files = None` and never rewrite
  the case, so a fitted `phaseProperties` survives a W3 restart (`backend.py:910-924`).

### A3
- Criterion 1 (F05 5 mm refused naming point 1 and 8.84 mm, level 3; 20 mm validates; the `:89`
  case validates): `test_case_validate.py` green. **Mutation:** with `_validate_det_radii`
  disabled, its 2 refusal checks fail.
- Criterion 2 (explicit 18 mm on P1-23 refused at run time, naming point 1 and 20.4 mm,
  `case kept at`, file unchanged): `test_foam_ignition.py` explicit checks green.
- Criterion 3 (`test_char_validation.py`): green in the deep gate.

### A4 - the revert, ruled
- Rule (pre-registered): keep only if |1 - after| < |1 - before|. Re-run (A6 case 5): before
  0.4888 (`20261012-123829_2d_p50436-06`), after 0.4888 (`-123855_2d_p50436-07`), 48.88 kg set in
  both. Equal is not smaller: **the revert is correct**. `git diff 39eac24 83b6a7c` on
  `vtk_export.py` and `test_foam_writer.py` is empty, so the revert is complete.
- **Ruling: accept the A1 9.0 mm pin standing in** for the TODO's "pin the radius of a charge
  outside the deepest zone". The A1 pin is exactly that case (P1-23: charge in the level-1 zone,
  lmax 2), and the plan's A4 criterion 1 asked for the same 9.0 mm. Nothing left with the revert
  that A1 does not pin.

### A5
- Criterion 1 (no kept list: the low-face cell is fluid; with it every dropped trigger gives
  `(None, None)` plus a `dropped` log; a kept gauge is unchanged; 2D and 3D):
  `test_foam_trigger_drop.py` green. **Mutation:** with the `kept` branch disabled, the 6
  "disabled" checks fail.
- Criterion 2 (`Trigger disabled` naming `G<n>` for blastFoam): green. **Mutation:** with
  `not foam` restored in `validation.py`, the 6 validate checks fail.
- Criterion 3 (`test_bc_trigger`, `test_trigger_numbering`): green.
- Kept-list matching: `spec.gauge_ids` holds the case's own gauge tuples (`writer.py:500-503`,
  `:561-564`), so the float-tuple match in `_trigger_cells` is exact, not a tolerance.
- **Ruling: accept the edit at `test_trigger_numbering.py:170`.** The old check pinned "blastFoam
  gets no such warning (D13, native only)", the exact behaviour Q2 replaces, so it could not stay.
  The new check is stronger (exactly one warning, naming G2), not weaker. **Mutation:** restoring
  `not foam` makes it fail in 2D and 3D, so it still fails when it should.

### A6
- Re-run once: `python -u _e2e_foam_ignition.py`, after the VM was confirmed free; exit 0,
  `IGNITION E2E: PASS`, nothing deleted.
  - Criterion 1: P1-23 serial and np4 both fit 9 -> 27.63 mm, 1 cell (nearest 20.39 mm). F05 fits
    11.25 -> 49.55 mm, 4 cells; F06 11.25 -> 54.13 mm, 8 cells. All write 1.8e-05 ... 2e-05. These
    are the implementer's numbers, reproduced exactly.
  - Criterion 2: neither control logs a fit, and each `phaseProperties` on disk equals the
    rendered file.
  - Criterion 3: both ratios are printed (above), and the rule is applied.
  - Wall times [s]: 693 / 232 / 19 / 144 / 23 / 108; mesh stages ~26 each.
  - Folders: `/root/blastlab_runs/20261012-121809_2d_p50436-00` (P1-23 serial), `-122942_..-01`
    (np4), `-123334_..-02` (F05), `-123353_3d_..-03` (F06), `-123617_2d_..-04` /
    `-123642_3d_..-05` (controls), `-123829_..-06` / `-123855_..-07` (A4).
- **Ruling: accept the control swap.** `validate_case` refuses `case2d_planar_amr` (it "needs AMR
  level 4"), measured, so that run could never start. The verifier's extra probe (below) shows the
  one AMR golden that validates, `case3d_amr`, is itself dark at t = 0, so no AMR golden could
  have served as a lit control. The two static-zone goldens are the right stand-ins.

## The `case2d_axi_refine` note - confirmed dark, and the fit covers it

Verifier probe (scratchpad `v_preflight.py`): mesh stages only, through `backend._preflight`, with
validation bypassed in the script only, since validation refuses this golden (N5-8). Run
`/root/blastlab_runs/20261012-124118_2d_p65068-00`.
- The written 45 mm lights nothing. The real nearest shell is **50.99 mm**: the refined axis
  cell's centroid is at 4/9 of the base cell (44.44 mm), 25 mm off in y. This matches the
  analytic value. The next shell is 87.18 mm.
- A2 fits it to **69.08 mm, 2 cells lit**, and only the `radii` line differs on disk.
- The golden is untouched (`foam_golden/case2d_axi_refine/constant/phaseProperties:87` is still
  `radii (0.045);`, and `test_foam_writer` is green).
- Extra finding, same probe: **`case3d_amr`** (`-124124_3d_p65068-01`, it validates) is dark too.
  The written 11.25 mm faces a nearest shell of 21.65 mm, and the fit gives 31.55 mm, 8 cells.

## Checks run

- `gate.py --changed 39eac24 --deep`: **119/119 green**, 27.9 min, the 9+ Tk `test_gui_*` suites
  included (CLAUDE.md §9). The eight WSL solve suites are skipped by the gate by design. None of
  them uses `det_radii` or `trigger_gauge`, and A6 covers the hook on real solves (serial, np4,
  static, AMR, 2D, 3D).
- Mutation checks: one throwaway worktree, four mutations, every new or changed check failed as
  it should. The worktree is removed.
- `_e2e_foam_ignition.py`: PASS (above). `v_preflight.py` probe: as above.
- `gate.py --only regression`, run last: **PASS, byte for byte**.

## Defects

None that needed a fix. Low items, not fixed (out of scope or pre-existing):

1. Low, pre-existing. `backend._scan_set_mass` prints a ratio for an intermediate
   setRefinedFields stage: "13.04 kg (1.63 of the 8 kg requested)" on `case3d_amr`, then 7.997 kg
   at the end. The first note reads like a 63 % over-deposit. Same family as implementer issue 3.
2. Low. `services/validation.py`, `_validate_det_radii`: it returns silently on
   `ArithmeticError` / `ValueError` / `TypeError` / `IndexError`, which would skip a necessary
   check without saying so. It is defensible, because the backend refuses on the real mesh anyway.
3. Low, doc. The `_e2e_foam_ignition.py` docstring and the plan say `case2d_planar_amr` "lights a
   cell today". The probe suggests AMR default seeds are generally dark (`case3d_amr` is), so that
   claim is unproven. The control swap makes it moot.

## Engineering questions (owner)

1. The default AMR seed (0.9 x the finest cell) lit nothing on every AMR case measured: F05, F06
   and `case3d_amr`. setRefinedFields leaves the charge interior coarse, so in practice the fit
   now sets every AMR seed. The fitted kernels are 49.55 / 54.13 / 31.55 mm, against charge radii
   of about 140 mm. With `linear` activation that is a few microseconds of near-field arrival
   (54 mm / vDet ~ 8 µs). Owner approved D1; it is recorded here so it is a known effect, not a
   surprise.
2. The implementer's open issues 2 (2D "stop: safety cap" at an explicit `t_end`; seen again on
   both 2D cases) and 5 (3D extra charges against `det_radii` count) stand. Both predate the batch.

## GUI screens that need QA

No widget code changed. Text only:
- Setup > Checks: the new "Detonation point k: ignition radius ..." error, and "Trigger disabled"
  now also in blastFoam mode.
- Run log: the `[note] detonation point k: ... fitted to ...` line and the run-time refusal of an
  explicit radius.

## Verdict

Part A VERIFIED: A1-A3, A5 and A6 as committed, A4 correctly reverted by its pre-registered rule.
The three implementer decisions are accepted, and regression is byte-identical.
