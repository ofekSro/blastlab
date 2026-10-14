# Where a 1D blastFoam step goes (P1-26, batch 1d-mpi, task A1)

Owner question 2026-10-14 (`TODO.md:675-682`): a 1D step costs ~113 ms at 5 000 cells
(`1d-mpi-probe.md`). Measure what it is spent on, then decide. Measurement only: no code, no
default, no number changes. OpenFOAM-9 has no `-profiling` option (`blastFoam -help`), so the
method is ablation timing plus a size sweep; no profiler is installed (owner 2026-10-14, Q3).

## Decision rule - written 2026-10-14 09:35, before the first timed run

Case A as the current writer writes it (`Case1D(solver='blastfoam', charge_kg=1.0,
material='TNT', radius_m=5.0, cell_size_m=0.001, gauge_radii=[1,2,3,4])`, `n_procs=1`), meshed
and charge-initialised once (`/root/p126_step_cost/base`); every variant is a copy with ONE
`foamDictionary -set` change (scripts: scratchpad `partA/`, copied to `/root/p126_step_cost/`).

- **Metric:** ms per step = median of the per-step `ExecutionTime` deltas in `log.blastFoam`
  (D6). Early window = steps 1-263 from t = 0 (the 2026-10-13 window; the run is stopped by
  PID once step 264 starts). Late window = 200 steps restarted from the `0.0025` state of
  `/root/mpi1d_probe/acc_np1` (D5). Two repeats; if they differ by > 3 %, a third; report the
  median of the repeats. Nothing else heavy runs on the machine; note: batch part B1-B4 fast
  tests (Python only, no WSL) may have run concurrently in a separate worktree.
- **Fixed vs per-cell:** dx 2 / 1 / 0.5 mm (2 500 / 5 000 / 10 000 cells), early window; fit
  ms/step = a + b n. Fixed per-step overhead is a **lead** if a >= 20 % of the 5 000-cell step.
  Cross-check with the probe's np 1/2/4/8 numbers (Amdahl serial fraction).
- **Ablations** (one change each, early window unless noted): M1 `activationModel none`;
  M2 `timeIntegrator Euler` (1 stage vs RK2SSP's 2); M3 `gradSchemes default Gauss linear`
  (vs `cellMDLimited leastSquares 1.0`); M4 `interpolationSchemes default linear` (vs `cubic`);
  M5 `fluxScheme HLLC` (vs `Kurganov`); M6 one phase vs two: single-phase air on the same mesh,
  a high-pressure sphere of the charge radius, laid out as a single-phase blastFoam tutorial
  (read only); M7 late window as written. Function objects on vs off is already measured
  (112.8 vs 115.7 ms, `1d-mpi-probe.md`) - cited, not rerun.
  A change is a **lead** if |delta ms/step| >= 15 % of the baseline.
- `strace -c -f` over 50 steps of the baseline: syscall share of wall time.
- **Done** when the leads explain >= 50 % of the step, or all of M1-M7 ran. If < 50 % is
  explained: "not localised" goes to the owner with the numbers; no profiler install.
- Resolution note (added with the rule, before any run): `ExecutionTime` is printed to 10 ms,
  so a single ~110 ms delta is quantised to about 9 %. The median over 263 deltas is reported
  as the plan says, next to the mean (last `ExecutionTime` / steps), which has no such
  quantisation; the lead test uses the median, and the mean is cited where the two disagree.

## Results (2026-10-14, office machine, alone on WSL; B1-B4 fast tests may have run concurrently)

Every run: 263 steps (early) or 200 steps (late) of case A as the current writer writes it,
function objects as written. `mean` = last `ExecutionTime` / steps, `median` = median of the
per-step deltas, both per repeat; "ms/step" in the lead test = the median over the repeats
of the mean (the 10 ms quantisation of `median` flips between 50 and 60 ms on a 56 ms step:
dx 2 mm gave 60 / 50 / 60, so the mean carries the numbers; every lead / not-lead verdict
below is the same on the medians). Repeats differing by > 3 % got a third: base (1.9 %, third
run anyway for the fit), dx 2 mm (2.7 % on the mean, 18 % on the median), M5 (3.7 %), M7 (3.8 %).
Run dirs and logs: `/root/p126_step_cost/runs/` (safe to delete, D4); results lines:
`/root/p126_step_cost/results_r12.txt`, `results_r3.txt`, `results_r4.txt`.

| variant | change (one each) | repeats: mean ms/step | median-of-deltas | ms/step | delta vs base | lead |
|---|---|---|---|---|---|---|
| base | case A, 5 000 cells | 114.18 / 112.02 / 115.48 | 110 / 110 / 110 | 114.2 | - | - |
| size 2 500 | dx 2 mm | 56.62 / 55.13 / 56.50 | 60 / 50 / 60 | 56.5 | - | - |
| size 10 000 | dx 0.5 mm | 224.18 / 223.88 | 220 / 220 | 224.0 | - | - |
| M1 | `activationModel none` | 109.77 / 110.23 | 110 / 110 | 110.0 | -3.7 % | no |
| M2 | `timeIntegrator Euler` | 62.78 / 62.85 | 60 / 60 | 62.8 | -45.0 % | **yes** |
| M3 | `gradSchemes default Gauss linear` | 88.82 / 87.53 | 90 / 90 | 88.2 | -22.8 % | **yes** |
| M4 | `interpolationSchemes default linear` | 100.68 / 100.27 | 100 / 100 | 100.5 | -12.0 % | no (< 15 %) |
| M5 | `fluxScheme HLLC` | 114.79 / 119.13 / 114.64 | 110 / 120 / 110 | 114.8 | +0.5 % | no |
| M6 | one phase (air only, ideal gas, hot sphere r = 0.0527 m, same mesh) | 64.33 / 65.29 / 64.30 | 60 / 60 / 60 | 64.3 | -43.7 % | **yes** |
| M7 | late window, 200 steps from t = 0.0025 s | 116.15 / 120.60 / 115.35 | 120 / 120 / 110 | 116.2 | +1.7 % | no (step cost does not move with time) |
| C1 (post hoc) | M2 + M3 together | 52.13 / 52.47 | 50 / 50 | 52.3 | -54.2 % | - |
| C2 (post hoc) | M2 + M3 + M4 | 45.21 / 46.01 | 40 / 40 | 45.6 | -60.1 % | - |

C1 and C2 are post hoc: the rule did not name them. They were run after the table above to
answer "do the leads explain >= 50 %", because the leads overlap (M2 removes a stage, M3 and M4
cost per stage), so their deltas do not simply add.

**Fixed vs per-cell** (mean ms/step over the three sizes, 2 500 / 5 000 / 10 000 cells:
56.1 / 113.9 / 224.0): fit ms/step = 1.0 + 0.0223 n, i.e. a = 1.0 ms = 0.9 % of the 5 000-cell
step (rule: lead if >= 20 %) and b = 22.3 us per cell-step. **No fixed per-step overhead**: the
cost is per cell, linear to 0.5 %. Cross-check with the probe's np scaling (`1d-mpi-probe.md`,
113 / 64.7 / 39.3 / 27.5 ms at np 1 / 2 / 4 / 8): Amdahl serial fraction f = 0.143 / 0.120 /
0.136 at np 2 / 4 / 8, a stable ~13 % (about 15 ms), which is MPI exchange and imbalance, not a
fixed solver cost (the single-process fit says a is 1 ms).

**`strace -c -w -f`, 39 steps of the baseline** (endTime 3.8e-6 s; 50 steps were not reached
at the chosen endTime): 26 741 syscalls = 686 per step, 46 % of the traced syscall time in
`write` (343 per step, the solver's stdout log), 44 % in `brk` (277 per step, heap grow and
shrink: allocation churn per step), the rest `newfstatat`/`openat`. strace charges ~62 us per
call (1.78 s of an 8.2 s traced run), so the traced share (22 %) is an artefact; at a native
cost of about 1 us per call the syscalls are ~0.7 ms of a 114 ms step, **< 1 %**. Consistent
with the 2026-10-13 finding (CPU-bound, ExecutionTime 1796.66 s vs ClockTime 1798 s). Syscalls
are not a lead.

## Verdict

The leads explain **>= 50 % of the step** (rule: done): M2 alone 45 %, M2 + M3 together 54 %
(C1), with M4 60 % (C2). All of M1-M7 ran. So the step is **localised to the numerics, not to
overhead**: ~22 us per cell-step, 45 % of it the second stage of RK2SSP (M2), a further ~9
points the limited least-squares gradient (C1 minus M2); two-phase machinery is the other
large part (M6, 44 %; it overlaps the first two, M6 was not combined with them). The lead test
was applied to the mean ms/step (see the resolution note above: medians quantised), verdicts
identical on the medians. Not a lead:
the activation model (M1, -3.7 %), the flux scheme (M5), the late-time state (M7), syscalls,
fixed per-step cost, function objects (112.8 vs 115.7 ms, `1d-mpi-probe.md`).

Per lead:
- **M2 `timeIntegrator Euler` - changes the results.** One stage instead of RK2SSP's two
  (blastFoam User Guide v6.0 sec. 10.3.4, p. 103): first order in time, a different peak,
  impulse and arrival. Owner question; needs its own peak / impulse / arrival check at the
  gauges (pre-registered, not run here). Not an optimisation to apply silently.
- **M3 `gradSchemes default Gauss linear` - changes the results.** Drops the
  `cellMDLimited leastSquares 1.0` limiter on the gradient used in the reconstruction
  (sec. 10.1.7, p. 99); unlimited gradients can overshoot at the shock. Owner question; same
  check needed.
- **M6 one phase vs two - structural.** blastFoam's two-phase `detonating` model (JWL products
  and air mixture, the activation model `linear`, `lambda`/`alpha` transport; sec. 5.6.1, p. 71)
  costs ~44 % over single-phase air on the same mesh. A charge in air needs both, so this is
  not removable, only a measure of what the second phase costs. The activation model alone is
  M1: no lead.
- **M4 `interpolationSchemes default linear` (-12 %, below the threshold) changes the results**
  (the `cubic` face interpolation); listed for completeness, not a lead.

No numerics-neutral lead was found: nothing here becomes a task that leaves the numbers
unchanged. What speeds a 1D run without touching the answer is MPI (P1-25: np 4 = 2.9x on
this case) or a coarser mesh (cost is linear in cells).

The 20 us early window reaches no gauge, so no accuracy claim is made for any variant, and M6's
sphere (rho 1630, p 1e9) is a timing stand-in, not a charge.

Method caveats: ablation, not a profiler (owner: no install, Q3); `ExecutionTime` resolution
10 ms; one machine, one load state (WSL alone; the parallel worktree's Python tests may have run
concurrently, which the repeats cover: the largest repeat spread was 3.8 %). Scripts:
`partA/` in the session scratchpad, copies in `/root/p126_step_cost/` (`variant.sh`, `drive*.sh`,
`m6_build.sh`, `stats.py`). No `blastlab/` file changed (`git diff --stat 05e099d -- blastlab`
empty); `gate.py --only regression` PASS.