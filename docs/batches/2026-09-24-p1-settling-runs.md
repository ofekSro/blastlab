# Batch 2026-09-24 - `p1-settling-runs`

**Goal:** close the two P1 audit questions that already have a "one run that settles
it" written down (N5-11 `RHO_MIN`, the residual ~2 % parallel-vs-serial offset), and
finish the documentation residue of the audit corrections. No solver default, no
golden and no GUI changes.

Planned on branch `hd1-band-cost` at `1c9b238`. Sources read: `CLAUDE.md`, `TODO.md`,
`DONE.md` §0, `docs/references/INDEX.md`, `docs/verification/blastfoam-claims.md`
§§1, 5, 6, 7, `docs/archive/TODO.md` (the P1/P2 status banners), and the code named
below.

---

## Why this batch and not another

1. **HD1 sits above P0, but it has no task that can be pinned down right now.** The
   `HD1-3d` "3D answer" row still reads *open*. But commits `5ff0c20` ("HD1-3d, the 3D
   answer") and `64b2a31` exist, `blastlab/tests/_e2e_vent_3d.py` is written, and
   `hd13_vent_jet_3d.mp4` sits untracked in the root. The 24-cell `Cd` point is marked
   *"Optional, not done"*. `HD1-4`'s blockers were bypassed by the chamber route
   (`writer._chamber_phaseproperties`, `init_mode='chamber'`). Closed-vessel data is
   an action for the owner, not code. All four are under "Needs clarification".
2. **P0 is empty.**
3. **P1 is the next rank.** Most of its visible text is stale (see "Needs
   clarification"). What is really open is three WSL experiments, each with a settling
   run already specified in `docs/verification/blastfoam-claims.md`, plus a small
   documentation residue. Two of the experiments are small or medium and can share
   one WSL session. The third, Claim 3, needs the vendor tutorial and three runs, so
   it is the next batch.
4. None of the three tasks changes a number any run produces. The only code added is
   a new manual `_e2e_` script.

**GUI screens touched: none.** `blastlab/ui/`, `blastlab/gui/` and `blastlab/viz3d/` are
not edited, so the Tk suites and the Qt harness do not need to run for this batch.

---

## Tasks in order

### 1. T9 - the audit corrections, the part that is still open  (size S)

**Original TODO text (P1, "Corrections the audit implies, not yet applied"):**
> - **`adjustLocations` is a no-op for every interior probe.** `core/case.py:90`,
>   `:202`, `:310` and `writer.py:107-111` all state that it "snaps each gauge onto
>   the centre of the cell holding it". **That is wrong for every interior gauge**,
>   which is all of them. The comments need correcting.
> - **The Claim 4 write-up names the wrong function.** It is
>   `fluxScheme::snGradAlpha`, not `fluxScheme::AD` - fix it before the finding is
>   quoted anywhere, because `::AD` sends a reader to a clean four-line function.
> - **Prefer `sum(lambda)` over `count(lambda >= 0.99)`** in any future ignition
>   measurement; the count is valid only at the first write.

**Interpretation, from what the code already shows:**
- Bullet 1 is **already done in code.** `core/case.py:91`, `:205` and `:337` now say
  "A no-op for every gauge we write", and `writer.py:107-119` explains
  `nBadProbes`/`movePts` and cites T40. What remains is documentation that still
  describes the old comments in the present tense. These are
  `docs/verification/blastfoam-claims.md` §6 (lines 778-781: "blastlab's own
  comments ... state that it snaps"), audit list item 2 (line 39), and the docstring
  of `blastlab/tests/_e2e_foam_probe_study.py` (lines 5-9), which states the refuted
  hypothesis without saying it was refuted.
- Bullet 2 is **already done in the audit's own body.** §2 (lines 123-201) names
  `snGradAlpha`. `fluxScheme::AD` survives only at line 856, inside "Appendix - the
  claims as originally stated", which is preserved on purpose. **Do not edit the
  appendix.** The only change is to mark audit list item 3 (line 42) as applied.
- Bullet 3 has **no code to change.** No script in `blastlab/` counts
  `lambda >= 0.99` (grep of `0\.99` finds no such measurement). It is a rule, so it
  belongs in `docs/verification/physics-anchors.md` §7 "Measurement discipline".

**Files:** `docs/verification/blastfoam-claims.md` (§"What this audit changed", §6),
`docs/verification/physics-anchors.md` §7, `blastlab/tests/_e2e_foam_probe_study.py`
(docstring only).

**Acceptance criteria:**
- `rg -n "snaps each gauge|centre of the cell holding" blastlab docs --glob '!docs/archive/**'`
  returns only lines that are explicitly marked as quoting the old, corrected wording.
  The Appendix is left untouched.
- `docs/verification/physics-anchors.md` §7 contains a rule stating that ignition is
  measured as `sum(lambda)`, not `count(lambda >= 0.99)`, and why (the count is valid
  only at the first write). It cites `blastfoam-claims.md` §3.5.
- `python blastlab/tests/test_regression.py` and `python blastlab/tests/test_foam_writer.py`
  are still green. This is a docstring and markdown change only, so both must be
  byte-identical.

**Dependency:** none. It goes first because it touches only docs and leaves the tree
runnable.

**References:** blastfoam-guide, sec. 15.1 blastProbes, pp. 122-123
(`=== page 123 ===`, "adjustLocations Can probes be moved into the mesh (default
no)"). Activation and `lambda`: sec. 5.6.1, pp. 70-71.

---

### 2. T6 - N5-11, the `RHO_MIN` settling run  (size M, WSL)

**Original TODO text (P1):**
> ### N5-11 · Remove `RHO_MIN`? · **not done, and do not do it on one run**
> ...
> > **The one run that settles it.** Re-run the chain's stage 2 from
> > `attempt_10/stage2_case.json` byte-for-byte on the current tree, changing exactly
> > one field — `t_end` from 0.0 to **5.0e-3**, so the terminate BC cannot stop it at
> > 0.6 ms — serially, and report `min(rho)` and `count(rho < 1e-3)` at the hand-off
> > instant and at `t_end`. That separates "the fix worked" from "the clean runs
> > stopped too early".
>
> **Until then the floor stays**, as a safety net.

**Interpretation (stated, not guessed):**
- The task is **the run and its report only.** `RHO_MIN` (`writer.py:1586`) is **not**
  removed or changed in this batch, whatever the numbers say. TODO says "do not do it
  on one run".
- The case file is `night_artifacts/NIGHT2/chain/attempt_10/stage2_case.json`. It is a
  2D axisymmetric case, 0.5 x 1.0 m, `cell_size_m 0.02` (25 x 50 cells), blastFoam,
  `init_mode profile1d`, schema `version 11`.
- **"Exactly one field" means one physics field.** The JSON also holds two absolute
  **paths**, and they must be redirected, which does not count as a physics change:
  - `profile_file_in` points at `blastlab/tests/_chain_study/gui_foam/stage1_profile.txt`.
    Before running, hash that file against `attempt_10/stage1_profile.txt`. If they
    differ, point it at the `attempt_10` copy. The input has to be the one attempt 10
    used.
  - `profile_file` would **overwrite** `_chain_study/gui_foam/stage2_profile.npz`, and
    the audit's §7 reads that file ("`stage2_profile.npz` is still on disk"). Redirect
    it to a scratch path.
  - Record both redirections, with hashes, in the report.
- "The hand-off instant" is the stage-2 end time of attempt 10, from
  `attempt_10/stdout.log` (~0.6 ms). Read `min(rho)` / `count(rho < 1e-3)` there from
  the blastFoam time directory nearest that instant. `n_snapshots` stays 1, so this
  reading does not come from the profile. At `t_end` read both the time directory and
  the saved `.npz`, and state which one each number came from.

**Pre-registration (commit this first, before the run).** Write the decision rule
with its numeric thresholds into `blastfoam-claims.md` §7 and commit it. Only then
start the solve. Proposed wording, for the implementer to adopt or tighten. It must
not be loosened after the numbers are in:
- **"The fix worked"** (the post-B0 path is clean beyond 0.75 ms):
  `count(rho < 1e-3) == 0` at **both** instants **and** `min(rho) >= 1e-2` at `t_end`.
- **"The clean runs stopped too early"**: `count(rho < 1e-3) == 0` at the hand-off
  instant **and** `> 0` at `t_end`.
- Anything else is **inconclusive** and is reported as such.
- In every outcome the floor stays until the owner decides.

**Files:** new script `blastlab/tests/_e2e_foam_rhomin_settle.py` (manual, WSL, prints
the table). It must not live under `test_*`. Report lands in
`docs/verification/blastfoam-claims.md` §7. No production code is touched.

**Acceptance criteria:**
- The commit that holds the pre-registered rule comes **before** the commit that holds
  the result. `git log` shows the order.
- The report states, for both instants: the time, `min(rho)`,
  `count(rho < 1e-3)`, and the source of each number (time dir or `.npz`). It also
  gives the verdict under the pre-registered rule, and the gauge `(0.3, 0.5)` peak,
  positive-phase impulse **and** arrival time. That follows the measurement
  discipline, even though the question is about density.
- `python -u blastlab/tests/_e2e_foam_rhomin_settle.py` runs serially (`n_procs 1`)
  and prints that table. Before starting, `wsl -d Ubuntu -- pgrep -a blastFoam` is
  empty. The finished run directory is copied out of `/root/blastlab_runs` before
  the session ends.
- `writer.py` is unchanged: `git diff --stat blastlab/solvers` is empty.

**Dependency:** none on T9. It shares the WSL session with T7 and must run **alone**
(CLAUDE.md §8.6). Run it before T7: it is ~1,250 cells and finishes quickly.

**References:** blastfoam-guide, sec. 5.9 Initialization, from p. 79 (`=== page 79 ===`,
guide line ~3188). This is how a written start-time state is decoded, which is the
seam `profile_state` feeds. Sec. 15.4 conservedQuantities, p. 124: its first reading
is the independent check on what blastFoam decoded from the hand-off fields
(`writer.py:753-775`, N5-5). Quote that first reading in the report.

---

### 3. T7 - the residual ~2 % parallel-vs-serial offset, the fixed-timestep run  (size L, WSL)

**Original TODO text (P1):**
> ### The residual ≈2 % parallel-vs-serial peak offset · **open, and narrowed**
> ...
> > **The settling run.** Take the `det_radii` arm exactly as it is and pin the
> > timestep: `adjustTimeStep no` with a fixed `deltaT` below the smallest adaptive
> > step either run took, everything else byte-identical, np = 1 vs np = 2. If the
> > offset collapses, it is temporal aliasing and the fix belongs in **how blastlab
> > samples the gauge**, not in the solver. If it survives at a fixed timestep,
> > aliasing is excluded and the next cut is the probe-cell election under
> > decomposition.

**Interpretation:**
- "The `det_radii` arm" is **arm C** of `blastfoam-claims.md` §5, "The discriminating
  run". Its setup: 1 m cube, `cell_size_m = 0.025` refined to `dx = L/76`, 8 kg TNT at
  the centre, `adaptive_write = False`, mirror gauges on exact cell centres at
  Z = 0.175, `t_end = 4.0e-4`, 438,976 cells, `method scotch`, default `det_radii`.
  **No script for it exists in the repo** (grep for `R2.2`/`arm C` finds only docs).
  The implementer rebuilds it from that paragraph. `test_foam_3d_smoke.py:106-147`
  is the nearest template: same box, charge and mirror-gauge alignment, but its
  gauges are at Z = 0.075, not 0.175.
- **No new writer wiring is needed.** `Case3D.fixed_dt` (`core/case.py:255`) already
  writes `deltaT <dt>; adjustTimeStep no; writeControl runTime;`
  (`writer.py:747-751`). This also covers the fixed-step half of `P3-3`. The
  `maxDeltaT` half of P3-3 is not needed here and is not done.
- The run needs four solves, not two:
  1. **Adaptive arm C, np = 1 and np = 2, on the current tree.** This is the sanity
     gate: it must reproduce the recorded per-gauge offsets (x −1.890 %, y −1.786 %)
     before a fixed-step comparison means anything. The adaptive logs also supply the
     smallest `deltaT`.
  2. **Fixed step, np = 1 and np = 2,** with `fixed_dt = 0.9 x min(deltaT)` over both
     adaptive runs. Everything else is byte-identical, which you check with a
     `diff -r` of the two written case directories: only `controlDict` may differ.

**Pre-registration (commit before any fixed-step solve).** Add a rule table to
`blastfoam-claims.md` §5, under "Verdict and the one run that settles what is left".
It must be read **per gauge, never on the mean**. §5's own note records how the mean
hid an antisymmetric defect. Proposed thresholds:

| # | Rule | Threshold |
|---|---|---|
| R2.3a | sanity gate: adaptive np2 vs np1, each gauge, against the recorded −1.890 / −1.786 % | within **±0.5 pp**, else stop: the tree has moved and the comparison is not interpretable |
| R2.3b | fixed step, np2 vs np1, **each** gauge, peak | **both < 0.5 %** → the offset collapsed → temporal aliasing |
| R2.3c | same | **either ≥ 1.5 %** → it survives → aliasing excluded; next cut is probe-cell election |
| R2.3d | same | anything between → inconclusive, reported as such |

**Files:** new `blastlab/tests/_e2e_foam_fixed_dt_offset.py` (manual, WSL, one solve
per invocation plus `--report`, the same pattern as `_e2e_foam_probe_study.py`).
Results go in `blastfoam-claims.md` §5. No production code is touched.

**Acceptance criteria:**
- The rule table is committed **before** the first fixed-step solve.
- The report table gives, for each of the four solves and each gauge: peak, positive-
  phase impulse, arrival time, and the np2-vs-np1 delta of each. It also gives the
  `fixed_dt` used, the minimum adaptive `deltaT` it came from, and the step count per
  run. Finally it states the verdict under R2.3a-d.
- `validate_case` accepts the fixed-step case with no error. Its Courant check is
  known to be weak here (see Risks). The report also states the Courant number
  computed by hand from the refined `dx = L/76` and the peak `|u| + c` in the adaptive
  run's log. It must be at most the case `cfl` (0.4 by default).
- The np = 2 runs really used 2 ranks: the log shows `nProcs : 2`. This guards
  against the P2-7 trap, where the rank count gets clamped.
- `git diff --stat blastlab/solvers blastlab/core` is empty.

**Dependency:** runs after T6 in the same WSL session (T6 is quick, and it frees the
VM). It has no code dependency on T6 or T9.

**References:** blastfoam-guide. Sec. 10.3 Time integration, p. 101
(`=== page 101 ===`): the RK scheme is what a fixed step feeds. Sec. 11.2 Dynamic
Load Balancing and the 11.3 example, pp. 112-113 (`method scotch;` at guide line
~4398): the decomposition method under test. Sec. 15.1 blastProbes, pp. 122-123:
how a probe samples, which bears on the "probe-cell election" branch of R2.3c.

---

**Batch total:** S + M + L. That is about one long working session plus unattended
WSL time. Four 439k-cell 3D solves dominate the time: `python -u`, no timeout, in the
foreground (TODO standing rules).

---

## Risks

- **Numerical results: none should move.** No solver default, EOS constant,
  activation, afterburn or golden is changed. Guard: `test_regression.py` and
  `test_foam_writer.py` byte-green at the start and at the end of the batch, with both
  tails pasted into the report. **If either one needs `--update`, the batch has
  strayed out of scope. Stop.**
- **Arguing after the numbers come in.** Both runs are judged by rules committed
  first (T6 pre-registration, R2.3a-d). The proposed thresholds above are a proposal.
  Tightening them before the run is fine. Loosening them after is not.
- **The fixed-step Courant guard is weaker than it looks for T7.**
  `validate_case` (`core/case.py:652-679`) estimates the Courant number from
  `cell_size_m` (0.025) and **ambient** `|u| + c ≈ 680 m/s`. Arm C refines to
  `dx = 0.0132`, and a detonation's products and shocked air are several times faster.
  A step that passes validation can therefore be unstable. Deriving `fixed_dt` from
  0.9 x the smallest **adaptive** step covers this. Do not pick it any other way, and
  report the hand-computed Courant number.
- **The run corpus.** Nothing in this batch builds the GUI, so the §8.2 auto-cleanup
  should not fire. Still, check that `env.auto_cleanup(settings.load())` returns
  `(0, 0)` first, and copy every finished run directory out of `/root/blastlab_runs`.
  The T7 3D snapshots are large: keep `n_snapshots` low and watch C: (CLAUDE.md §8.5).
- **Overwriting audit evidence.** `stage2_case.json` writes to
  `_chain_study/gui_foam/stage2_profile.npz` by default, and the audit cites that
  file. T6 redirects the output path.
- **WSL teardown** (CLAUDE.md §8.3): if a 3D solve dies with `Input/output error`, W3
  resumes it. A resumed run is still a valid sample only if its step history is
  continuous. Say so in the report if a resume happened.
- **Tk / GUI:** not touched, so no `test_gui_*` run is required. Say so explicitly in
  the finish report.

---

## Needs clarification (excluded from this batch)

1. **`HD1-3d` "the 3D answer" (TODO row: *open, needs WSL*).** Commits `5ff0c20` and
   `64b2a31` and `blastlab/tests/_e2e_vent_3d.py` exist, and
   `hd13_vent_jet_3d.mp4` / `hd13_report.html` are untracked in the root. `DONE.md` has
   no entry. *Question:* did `_e2e_vent_3d.py` run to PASS on WSL? If yes, should the
   row be ticked and a `DONE.md` §0 entry written? Should the two `.mp4` files and the
   report be committed, moved under `docs/`, or ignored?
2. **The optional third `Cd` point, 24 cells across on a shrunken room (HD1-3).** It
   is marked *"Optional, not done"*. It would turn `DEFAULT_CD_RANGE = (0.72, 0.90)`
   (`core/sensitivity.py:108`) from a two-point extrapolation into a measurement.
   *Question:* do you want it scheduled? If so, it is the next HD1 batch, and its
   convergence threshold must be registered before it runs.
3. **`HD1-4` blockers.** The route chosen on 2026-09-21 (room inside the mesh, inert
   `type basic` chamber phase via `writer._chamber_phaseproperties`) needs none of the
   four listed blockers. *Question:* close `HD1-4` as "not needed by the chamber
   route", or keep it for the `AbelNobel` fallback?
4. **Items TODO.md lists as open that the code and the archive show as closed.**
   `docs/archive/TODO.md` line 1820 says "P1 closed 2026-09-09", and it names P1-4.
   Line 1970 says "P2-1, P2-2, P2-7, P2-8, P2-9 closed". The code agrees: P1-4 is in
   `core/case.py:493,741`. P2-1 is in `solver1d.py:307`. P2-2 is in
   `viz3d/viewer.py:66-74` (`approx_title`). P2-7 is in `test_foam_parallel.py:69-80`.
   P2-8 is `warner=` in `gui/run_browser.py:39,55` and `test_gui_run_browser.py:84`.
   These P3 items also look done: P3-16 (`conservedQuantities`, `writer.py:774`),
   P3-17 (`timeOfArrival`, `writer.py:824`), P3-19 (`beginUnrefine` /
   `allowableImbalance`, `writer.py:1359-1374`), and the fixed-step half of P3-3
   (`fixed_dt`). *Question:* were these entries carried over by mistake in the
   2026-09-21 English consolidation? May they be struck, with a pointer to the closing
   commit?
5. **`P3-11` "the semantics of `n_snapshots` differ between 1D and 2D/3D".** No target
   behaviour is stated. *Question:* which semantics should win? Unifying them changes
   native stdout and needs a re-baseline.
6. **`P3-8` "Log contours apply only to slice planes".** It is unclear which layers
   should also follow the log flag (isosurface? volume?). *Question:* which layers,
   and is it the same fix as `P3-25`?
7. **Owner decisions already tabled in TODO** (not work until decided): the `amr2d`
   thresholds, `scotch` vs a symmetric decomposition, and P4-1 / P4-2.

---

## Remaining backlog - suggested future batches

- **Next: Claim 3 experiments** (P1): R3.1b (vendor `mappedBuilding3D/wedge`, 1° +
  AMR + `densityGradient`), R3.2 (with vs without the `profile1d` hand-off), R3.3
  (1° vs 5°, ≤ 1 % pre-registered). WSL, L. Refs: guide sec. 11.1 error estimators,
  pp. 107-111. Sec. 5.9, p. 79.
- **HD1 bookkeeping and Cd point** (after clarifications 1-3): tick the 3D row, add
  the DONE entry, and optionally run the 24-cell `Cd` convergence point. Ref:
  UFC 3-340-02 para. 2-15 (vented, leakage pressure) for the vent-load wording.
- **Viewer colour-scale honesty:** P3-25 (surface-loads bar ignores the log flag,
  `viz3d/viewer.py:1149-1230`), P3-8 once clarified, and P3-7 (blit renders twice).
  GUI, S-M. `test_viz3d_*` and the Qt harness.
- **Remap-chain honesty:** P3-15 (the obstacle drop at `core/profiles.py:204-206`
  becomes a validation warning), P3-10 ("0 kg TNT", `profiles.py:213`, `solver3d.py:387-390`,
  needs a **re-baseline** of `transcript.txt` / `b3r`), P3-9 (the 2D animation's
  `xlabel` is still hard-coded `'x [m]'` at `output/animation.py:184`). S each, with
  the Tk suites (shared `core/`, `output/`).
- **Detonation-point GUI tables:** N5-12 (per-point delays/radii table) together
  with P3-21 (initiation delays; `programmedIgnition` is already in
  `ui/setup_spec.py:78`) and P3-13 (planar-2D extra charges table). GUI, M-L, parity
  with Tk.
- **blastFoam writer options:** P3-3 remainder (`maxDeltaT` override), P3-24
  Schlieren/shadowgraph (guide 15.6-15.7, pp. 124-125), P3-23 `DoanNickel` (guide
  sec. 5.1-5.2), and P3-4 HLLC comparison (guide sec. 10.1). Goldens are updated via
  `--update` with an eyeballed diff.
- **Charge-mass exactness:** P3-18 `volScalarFieldMassIntegrated`. It needs the KB
  anchor first and an afterburn refit afterwards (CLAUDE.md §7). This is its own
  batch because it moves calibrated numbers. Ref: UFC 3-340-02 Figure 2-7 (printed
  p. 83) and the guide sec. 5.6.2.
- **Mesh and remap capabilities (large, on request):** P3-1, P3-5, P3-12, P3-14, P3-20.
- **Performance (on request):** P3-6, P3-22.
- **Manual, needs a person at the screen:** P2-5 (ParaView, volume Min/Max, DPI,
  second monitor).
