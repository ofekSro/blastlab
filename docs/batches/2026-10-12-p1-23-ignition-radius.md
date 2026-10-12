# Batch P1-23 - every detonation point lights a cell at t = 0, and a radius that cannot is refused

- **Name:** `p1-23-ignition-radius` (base `67cf281`, `master`; work branch `p1-23-ignition-radius`).
- **Goal:** a default ignition radius always lights a cell of the real t = 0 mesh (static zones
  and AMR), an explicit one that cannot is refused before blastFoam starts, blastFoam's trigger
  on a dropped gauge behaves as the native one, and then the closed rows leave TODO.md.
- **Risk: high.** Part A `risk: high` (`solvers/foam/writer.py`, `backend.py`, `vtk_export.py`,
  `services/validation.py`, `core/refine.py`; a seed value; WSL solves). Part B `risk: none`
  (TODO.md, `docs/history/todo-closed.md`).
- **track-end: no.** P1 and P2 keep many open items (P1-4, P1-8 …, P2-1 …).
- **Rules:** `CLAUDE.md` §6, §8, §9 and `docs/agent-rules.md`. One commit per task,
  `area: what changed (P1-23)` / `(P2-22)` / `(P1-23, P1-24)` / `(TODO)`. A1 is its own
  characterisation commit, before A2.
- **Owner approval:** `TODO.md:34-37` (RESUME 1: this batch, ahead of HD1-18/19, plus the
  housekeeping), `:642-647` (fix and acceptance), `:649-654` (measure the t = 0 level first; the
  blastFoam trigger). This plan departs from `:642-643`'s mechanism, on measured numbers: **Q1**.
- **Sources:** TODO.md P1-23 (`:630-654`), P2-22 (`:828`), P1-24 (`:656-661`);
  `docs/qa/2026-10-03-gui-qa/findings.md:69`; GUI-15 plan, probe (h).
- **References:** blastFoam User Guide v6.0, sec. 5.6.1 (p. 71), `radii`: "the cells within the
  charge with the radii specified are set to full activated"; sec. 16.1 setRefinedFields
  (pp. 127-131), `refineInternal` (Q1's alternative). Also the installed source,
  `activationModel.C:96-148` (WSL, read only): a centre test `mag(C - pt) < radius`, a fatal error
  when no cell (or no mass) is found, run at start-up, a restart included.

## Feasibility probes run while planning (agent-rules "Do it once")

Read only: run folders in `/root/blastlab_runs` (`0/C`, `0/polyMesh/cellLevel`, logs) and
`writer.render_case`. Scripts in the session scratchpad; nothing written to the repo or WSL.

- **The P1-23 case** (`20261011-081913_2d_p61324-00`: axisymmetric 10 × 10 m, cell 0.04 m,
  100 kg C4 at (0, 0), zones level 1 + level 2, static). Written radius 9.0 mm (lmax 2). The
  charge sits in level-1 cells, and refineMesh cuts the axis cell at its centroid (x-centres
  17.78 / 33.77 / 50.66 mm, i.e. faces 0 / 26.7 / 40 mm). Nearest centre (17.78, 10.0) mm =
  **20.39 mm**, next 34.87 mm. The TODO's fix, 0.9 × the level-1 cell = **18.0 mm, still lights
  0 cells**, so `:645`'s acceptance would fail.
- **F05** (`20261011-140510_2d_p10740-01`: planar, dx 0.1, AMR 3, 100 kg/m at (2, 2)). At t = 0
  the point sits in **level-1** cells (setRefinedFields refines where the estimator flags, the
  charge interior stays coarse). Cells per level 1576 / 40 / 104 / 480. 4 centres at 35.36 mm,
  next 63.74 mm. Written radius 11.25 mm lights 0.
- **F06** (`20261011-141055_3d_p50100-00`: dx 0.05, AMR 2, 20 kg at (0.75, 0.75, 0.75)).
  **Level 0** at the point, 8 centres at 43.30 mm. Written radius 11.25 mm lights 0.
- **Goldens.** 15 `foam_golden/*/constant/phaseProperties` carry `radii`. A2, A3 and A5 change
  no written file. A4 changes `scale` only for a static charge outside the deepest zone; none in
  `foam_golden` (planar_refine and 3d_refine: charge at lmax 4; axi_refine: lmax 1) nor in
  `char_golden/validation_blast_cases.json` (lmax 0, or AMR). `baseline/` is native, untouched.
- **dx_charge** on the P1-23 case, modelled on a uniform 0.02 m lattice (`core.refine._staircase`):
  deposit 0.9788 of the request with today's scale (searched at 0.01 m), 0.9842 searched at 0.02 m
  (vendor raw 0.9778).
- **Explicit radii.** The only committed case, `test_case_validate.py:89` (10 / 20 mm), has its
  nominal nearest centre at 3.35 mm (fine dx 6.58 mm), so it stays valid under A3.
- **blastFoam trigger** (`backend._trigger_cells`, 2D and 3D). A dropped gauge strictly inside the
  snapped wall samples a carved display cell. That cell holds the `P_AIR` fill
  (`backend.py:1263-1264`), so `p > 1.001 P_AIR` (`runloop.py:60`) never holds: 2D 5/5, 3D 3/3.
  A gauge exactly on a snapped **low** face samples the fluid cell in front (argmin tie, lower
  index) and **can fire**. On a high face it samples the wall. "Never fires" is false: **Q2**.
- **Stage list.** `test_foam_amr_ingest.py:140,153` evaluates `'noRefine' in c` /
  `'refineMesh' in c` on every `_mesh_stages` entry, and a callable stage would raise TypeError
  there. So A2 runs in `_preflight`, after the stage loop, not as a stage; no committed test edit.

---

## Part A - risk: high (ignition seed, validation, trigger, WSL)

Order A1 → A6. Per task: `gate.py --for <files>` before, `--changed HEAD` after (agent-rules).
New checks pin meaning (point number, radius and distance in mm, cell count), not prose.

### A1 - P1-23: characterise the seed before touching it (S)

- **What:** a new fast test `blastlab/tests/test_foam_ignition.py` (no WSL). It pins today's
  written radius for the P1-23 case (9.0 mm), F05 (11.25 mm) and F06 (11.25 mm, the cases of
  `_qa_ui_harness.py:1995-2011`), and the P1-23 case's `dx_charge` (0.01 m). The golden `radii`
  are already pinned byte for byte by `test_foam_writer.py`; do not pin them twice.
- **Files:** the new test. **References:** none (characterisation).
- **Acceptance:** `python test_foam_ignition.py` exits 0 on `67cf281`, committed alone.

### A2 - P1-23: a default radius that lights no cell is fitted to the t = 0 mesh (M)

- **TODO text:** "take the level from `spec.levels` at each detonation point (the deepest cell
  touching it), max with `amr` … first measure the level actually present at the charge at t = 0
  on F05's case and base the radius on it".
- **Interpretation (Q1, D1-D4):** measured above, the writer cannot know the level at the point
  (AMR: it depends on the estimator; static: on the axis cut). So the written radius stays as it
  is, and the run checks it against the real mesh.
  - Where: `backend._preflight`, after the stage loop and before `build_remap` (`:308-322`).
  - When: the case has detonation points with default radii, and a `0/C` exists
    (`spec.lmax or spec.amr`, `:136-140`).
  - How: read `reader.read_cell_centres(spec.case_unc, spec.start_dir)`. If no centre lies within
    a point's written radius, use r = (d1 + d2) / 2, d1 the nearest shell of centres and d2 the
    next (D1). Replace only the `radii` entry of `spec.files['constant/phaseProperties']` and
    write it with `writer._write_files`. Log one `[note]` per fitted point: point number, old and
    new radius, cells lit.
  - Code: a pure `writer.fit_det_radii(points, radii, centres)` next to `default_det_radius`. Its
    docstring cites guide 5.6.1 (p. 71) and `activationModel.C:111-137`.
  - Uniform meshes keep 0.9 dx, because the docstring's analysis holds there: the axis first cell
    is at hypot(2/3, 1/2) = 0.83 dx and the 1D first cell at 0.75 dx.
- **Files:** `solvers/foam/writer.py`, `solvers/foam/backend.py`, `test_foam_ignition.py`.
- **Acceptance:**
  1. `test_foam_ignition.py`, on synthetic centres that reproduce the three probes: P1-23 fits a
     radius in (20.39, 34.87) mm lighting 1 cell, F05 lights 4 and F06 8. A radius that already
     lights a cell comes back unchanged. The rewritten text differs only on the `radii` line.
  2. `python test_foam_writer.py` and `python test_foam_amr_ingest.py` exit 0, and `foam_golden/`
     is byte-identical.
- **Depends:** A1. **References:** guide sec. 5.6.1 (p. 71).

### A3 - P2-22: an explicit radius that lights no cell is refused (S)

- **TODO text:** P2-22 "Validation accepts a detonation point that activates no cell; blastFoam
  then dies at t = 0"; P1-23 "Validation should refuse an explicit `det_radii` below the corner
  distance."
- **Interpretation (D3, D5):** two checks.
  - Validation (`services/validation.py`, the N5-12 block `:304-319`), for a blastFoam charge case
    with explicit `det_radii`: per point, an error when r ≤ the nominal nearest-centre distance at
    the deepest level that can be at the point. The level: static, the deepest fine cell of
    `ctx.plan.levels` touching the point (new `core/refine.level_at`); AMR, `plan.amr`; uniform, 0.
    The lattice of that level: centres at (k + ½)h, the axisymmetric axis cell's radial centre at
    ⅔h. This check is necessary, not sufficient.
  - Run time: A2's hook refuses the rest. An explicit radius that lights no cell of the t = 0 mesh
    raises before blastFoam with the point, the nearest-centre distance in mm and `case kept at`.
    The radius is never altered.
- **Files:** `services/validation.py`, `core/refine.py`, `solvers/foam/backend.py`,
  `test_case_validate.py` (new checks only), `test_foam_ignition.py`.
- **Acceptance:**
  1. `test_case_validate.py`: F05's case with `det_points=[(2.0, 2.0)]`. `det_radii=[0.005]`
     gives an error naming detonation point 1 and 8.8 mm (level 3, h 12.5 mm, a node); `[0.02]`
     validates; the `:89` case still validates.
  2. `test_foam_ignition.py`: an explicit radius that lights nothing raises, naming the point, and
     `phaseProperties` on disk is unchanged.
  3. `python test_char_validation.py` exits 0 (`validation_blast_cases.json` unchanged).
- **Depends:** A2. **References:** guide sec. 5.6.1 (p. 71).

### A4 - P1-23: the charge's mass scale uses the level at the charge (S)

- **TODO text:** "check `dx_charge`, which has the same `lmax` assumption".
- **Interpretation (D5):**
  - `CaseSpec.dx_charge` (`writer.py:253-261`): a static refined case uses dx_base /
    2**`level_at`(charge centre); AMR and uniform are unchanged. The mirror at
    `validation.py:1300-1307` uses the same helper, so `Charge cells: …` agrees with the writer.
  - `vtk_export.py:1644` uses `dx_charge` as a "finest cell" tolerance; it gets the finest cell
    explicitly instead, the same number for every case.
- **Pre-registered rule:** A6 runs the P1-23 case's mesh stages twice, with the pre-A4
  `dx_charge` (a script-local override) and as committed, and reads the `[note] blastFoam set … of
  the 100 kg requested` ratio (`backend._scan_set_mass`) from each. A4 stays only if
  |1 − after| < |1 − before| (model: 0.979 → 0.984); otherwise revert A4's commit and record both.
- **Files:** `solvers/foam/writer.py`, `services/validation.py`, `solvers/foam/vtk_export.py`;
  `test_foam_writer.py` (a new non-golden check); `test_foam_ignition.py`, where this plan names
  the change to A1's `dx_charge` pin.
- **Acceptance:**
  1. `test_foam_writer.py`: the P1-23 case has `dx_charge` 0.02 m and its written radius is still
     9.0 mm; the goldens are byte-identical.
  2. `test_char_validation.py`, `test_refine.py` and the `test_vtk_*` suites exit 0.
  3. The A6 output prints both ratios, and the rule is applied.
- **Depends:** A1. **References:** none applies (the repo's own N5-2 mass scale).

### A5 - P1-23 / P1-24: blastFoam's trigger on a dropped gauge (S)

- **TODO text:** "measure what blastFoam's trigger reads at a gauge the writer drops into a wall
  (`foam/backend.py:1785-1804`); extend P1-24's native-only warning if it never fires."
- **Interpretation (Q2, D7):** measured above, it never fires inside a wall and can fire on a
  low face, so this task follows the native D13 rule.
  - `_trigger_cells` takes the writer's kept list (`spec.gauge_ids`, `writer.py:499-502` / `:560`).
    It disables a trigger whose gauge the writer dropped and logs `hooks.trigger_index`'s warn line
    (`solvers/hooks.py:84-85`).
  - `validation.py:1605` drops `not foam`, so `Trigger disabled` is true for both solvers;
    GUI-16 (a) builds on that.
- **Files:** `solvers/foam/backend.py`, `services/validation.py`, new `test_foam_trigger_drop.py`
  (the probe as a test: inside, low face and high face, in 2D and 3D).
- **Acceptance:**
  1. The new test: called without the kept list, the low-face trigger cell is fluid (the
     measurement). Called with it, every dropped trigger gives `(None, None)` and a `dropped` log,
     and a kept gauge's cell is unchanged.
  2. `validate_case` on a blastFoam case whose trigger gauge is dropped warns `Trigger disabled`
     and names `G<n>`.
  3. `python test_bc_trigger.py` and `python test_trigger_numbering.py` exit 0.
- **References:** none applies (the repo's T51 trigger).

### A6 - P1-23, P2-22: the cases that died at t = 0 run (M, WSL)

- **What:** a new `blastlab/tests/_e2e_foam_ignition.py` that does real solves.
  - Ground rules: `if __name__ == '__main__'`, `env.hardware(probe=True)`, the CLAUDE.md §8.6
    `pgrep` check first, `python -u` in the background, polls ≤ 4 min apart, never delete a run.
  - End time `t_end` 2e-5 s (D6), with the end write as the check.
  - Cases: (1) P1-23, serial; (2) P1-23, `n_procs` 4 (a static refined mesh); (3) F05 and F06,
    the harness cases; (4) control, `test_foam_writer.py`'s `case2d_planar_amr`, which lights a
    cell today; (5) A4's two mesh-stage runs.
- **Acceptance:**
  1. The script exits 0. Cases 1-3 each log the fit note and reach a write after t = 0, and 1 and
     2 fit the same radius.
  2. Case 4 logs no fit, and its `phaseProperties` on disk equals the written file.
  3. A4's two ratios are printed and its rule applied; the report records wall times and folders.
- **Depends:** A2-A4. **References:** guide sec. 5.6.1 (p. 71).

---

## Part B - risk: none (TODO.md housekeeping)

### B1 - owner 2026-10-12: the closed rows leave TODO.md (S)

- **TODO text:** RESUME 1, "the same batch moves the closed GUI-14 / GUI-15 rows and the P1-24
  body to `docs/history/todo-closed.md` (TODO.md at 992 of 1000 lines)". It is 997 lines today.
- **Interpretation (D8):**
  - The GUI-15 row moves verbatim, and `GUI-1..13` becomes `GUI-1..15` (DONE.md §0l-§0y).
  - The GUI-14 row moves verbatim, and a one-line `GUI-14 (j)` row stays open (home PC).
  - The P1-24 section moves verbatim. A 2-line stub, in the N5-7 pattern (`TODO.md:985-991`),
    goes under "Closed items that code comments still cite", because six source files cite P1-24.
  - Edit/Write only (CLAUDE.md §8.1).
- **Files:** `TODO.md`, `docs/history/todo-closed.md`. **References:** none.
- **Acceptance:**
  1. TODO.md is under 997 lines and `todo-closed.md` is ≤ 1000.
  2. `rg -n "P1-24|GUI-14 \(j\)" TODO.md` finds the stub and the row.
  3. `rg 'ג€|ג”'` finds nothing in either file, and every removed TODO line appears in
     `todo-closed.md`.

---

## Verification

- **Part A, full depth:** `gate.py --deep`, including the nine `test_gui_*` Tk suites (CLAUDE.md
  §9: `core/` and `solvers/` change); `test_foam_writer`, `test_foam_amr_ingest`,
  `test_case_validate`, `test_char_validation`, `test_refine`, `test_vtk_*`, `test_bc_trigger`,
  `test_trigger_numbering` and the two new suites; `test_regression.py` last, byte-identical. The
  verifier re-runs `_e2e_foam_ignition.py` once. Optional, not a gate: `_qa_ui_harness.py
  --scenario F05` / `F06` with `--out` outside OneDrive (GUI-15 QA: `WinError 5`).
- **Part B, light:** the line counts and the two `rg` checks.

## Risks and how they are protected

- **A seed change for runs that work today:** the fit fires only when 0 cells light (D2), so
  `phaseProperties` is byte-identical otherwise (A2 acceptance 1, A6 case 4).
- **Parallel runs read the root `constant/phaseProperties`** (decomposePar does not copy it), so a
  rewrite after the stages reaches every rank. A6 case 2 proves it.
- **Resume:** `run_*(spec=…)` skips `_preflight` (`backend.py:1412-1414`), and W3 restarts on the
  same case dir, so the fitted file stays. blastFoam re-checks the point on a restart.
- **"No mass was found"**, the second fatal: the shell is the nearest one to a point that
  `_validate_det_points` keeps inside a charge. A6 cases 1-3 cover it.
- **Numbers that move:** only A4, and only for a static charge outside the deepest zone (no golden
  has one), behind a pre-registered rule. A characterisation commit comes first (A1).
- **Committed tests:** none edited. The hook placement keeps `test_foam_amr_ingest` intact, and
  `test_case_validate` and `test_foam_writer` get new checks only.
- **WSL:** CLAUDE.md §8.6 before each solve, no deletion in `/root/blastlab_runs`, folders recorded.

## Proposed defaults (decision rows)

| # | Choice | Default | Why |
|---|---|---|---|
| D1 | Fitted radius | (d1 + d2)/2: lights exactly the nearest equidistant shell (1 cell on P1-23, 4 on F05, 8 on F06) | Centre-based, so decomposition-invariant as the N5-7 docstring requires. 0.9 × the t = 0 level fails P1-23's axis cell |
| D2 | When to fit | Only when the written radius lights no cell | Every run that ignites today keeps its seed bit for bit |
| D3 | Explicit `det_radii` | Never altered: validation error (nominal) or a run-time refusal before blastFoam | The user's number is the user's |
| D4 | Record of a fit | One `[note]` log line per point. `spec.files` and the case dir agree. No new meta key | No golden or meta pin moves |
| D5 | `level_at` | The deepest fine cell of `plan.levels` touching the point, shared by A3 and A4 | TODO.md:642's own wording |
| D6 | A6 end time | 2e-5 s per case | Tens of steps, past t = 0, minutes in total |
| D7 | Trigger on a dropped blastFoam gauge | Disabled, as native (D13 of GUI-15) | One rule and one Checks line for both solvers (Q2) |
| D8 | B1 layout | GUI-14 (j) keeps a one-line row; the P1-24 stub follows N5-7 | Code cites P1-24; RESUME 3 cites (j) |

## Needs clarification (approving the plan approves the recommendation)

- **Q1 - P1-23's mechanism.** TODO.md:642-643 says to take the level at the point from
  `spec.levels`, max with `amr`. On the measured meshes that does not make the acceptance case
  run: 18.0 mm against a nearest centre of 20.39 mm, because refineMesh cuts the axis cell at its
  centroid. It also cannot see F05's level 1 or F06's level 0 at t = 0. **Recommended:** A2's
  run-time fit, which leaves the written radius and every golden byte-identical. Alternative, not
  recommended: `refineInternal yes` on the charge region (guide 16.1, p. 131) plus the writer
  lookup. That changes the t = 0 mesh of every AMR charge case and three goldens
  (`case2d_planar_amr`, `…_np4`, `case3d_amr`), and still fails the axis cell.
- **Q2 - blastFoam trigger parity.** TODO.md:654 asks to extend the warning "if it never fires".
  It can fire for a gauge exactly on a snapped low face, which is where a wall-load gauge is
  typed. **Recommended:** disable it as native does (A5), so `Trigger disabled` is true for both
  solvers. Alternative: leave the backend alone and warn only where the sampled display cell is
  carved, which validation can compute per gauge. The low-face trigger then stays live, and GUI-16
  (a) needs two rules.

## Remaining backlog (grouped one line per track to fit the 300-line cap; RESUME order first)

- **GUI:** `GUI-16` next (owner: the last GUI batch, findings fixed in place) · `GUI-14 (j)` home PC.
- **HD1:** `HD1-18` preset · `HD1-19` vent.py gaps · `HD1-16` step 2 · `HD1-17 (b)` · `HD1-14`
  third `Cd` point · `HD1-4` blockers · closed-vessel data (owner, no code).
- **P1 physics:** `P1-4` afterburn (owner) · `N5-11` `RHO_MIN` · ≈2 % parallel offset · Claim 3
  experiments · audit corrections not applied.
- **P1 inputs/labels:** `P1-7` frame 0 by eye · `P1-8` AMR thresholds · `P1-9` "kg TNT" ·
  `P1-10` ground vs free-air KB · `P1-11` HD 1.3 silent defaults · `P1-12` write interval/disk.
- **P1 data/grids:** `P1-14` material sources · `P1-16` grid mismatches · `P1-17` band about
  1 Pa · `P1-15` Vieille `a` unit · `P1-13` arrival threshold · `P1-19` Tk chain exit.
- **Remap chain:** `P1-20` · `P1-21` · `P1-22` · `P3-14` 3D→3D · `P2-26` … `P2-30`.
- **P2 accuracy/tests:** `P2-1` 1D progress · `P2-2` energy label · `P2-5` by-eye list · amr2d
  thresholds (owner) · `N5-12` follow-up · `P2-11` · `P2-13` · `P2-14` · `P2-15`.
- **P2 UI:** `P2-16` · `P2-17` · `P2-18` · `P2-19` · `P2-20` · `P2-21` · `P2-23` · `P2-24` · `P2-25`.
- **P3** on request · **P4:** `P4-1` OneDrive · `P4-2` disk · `P4-3` WSL cleanup trap.
