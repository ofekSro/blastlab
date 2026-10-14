# Does MPI help a 1D blastFoam run? (probe, 2026-10-13)

Owner question 2026-10-13. Today a 1D blastFoam run is always serial
(`foam/backend.py:289-295`, `env.py:528` "1D runs are a single wedge", since T48).

## Decision rule - written before any run

Pre-registered 2026-10-13 (CLAUDE.md §6), before the first solve below.

Cases (1 kg TNT, JWL, auto everything else, fixed `t_end` so serial and parallel solve
the same interval; same written case, only `decomposeParDict` differs):
- **A** - the default size: R = 5 m, dx = 1 mm (≈ 5 000 cells), gauges 1/2/3/4 m, t_end 10 ms.
- **B** - large: R = 20 m, dx = 1 mm (≈ 20 000 cells), gauges 2/5/8/12 m, t_end 35 ms.

Each at np = 1, 2, 4 (scotch, as the writer does for 2D/3D). Wall time counted from
`blastFoam` start to the end of `reconstructPar` (decomposePar included for np > 1);
mesh and charge init are serial in both and are left out.

**MPI for 1D becomes a TODO task only if both hold on case B:**
1. np = 4 wall time ≤ 0.6 × serial;
2. at every gauge, peak overpressure and positive-phase impulse within 1 % of serial,
   and arrival time (first crossing of 1.1 × ambient) within 1 % of serial.

If (1) holds and (2) does not: an engineering question, not a task. If case A at np = 2
or 4 is not at least 1.25× faster than serial, record that MPI does not matter at the
default size, whatever B shows.

### Amendment, before any parallel gauge data

Case A serial reached only t = 3.4 ms of 10 ms in 30 min (113 ms per step at 5 000 cells),
so the full cases would take hours. Changed before any np > 1 gauge result existed:
- **Speed** is measured as ms per step over the same 263 steps (t = 0-20 µs) at np 1, 2,
  4, 8, function objects as written. Rule 1 is read on that, decompose/reconstruct
  measured separately.
- **Accuracy** is case A cut to t_end = 3 ms, gauges at 1 m and 2 m (both reached),
  serial vs np 4; rule 2 unchanged (1 % on peak, positive impulse inside the window,
  arrival).
- Case B is dropped: at ~4× the cells it would take ~4× as long per step, and serial
  alone would run for hours.

## Results

Speed, case A (5 000 cells), 263 steps:

| np | ms / step | speed-up |
|---|---|---|
| 1 | 112.8-115.7 (function objects on / off: no difference) | 1.00 |
| 2 | 64.7 | 1.75 |
| 4 | 39.3 | 2.94 |
| 8 | 27.5 | 4.10 |

**Accuracy: not measured.** The owner stopped the probe on 2026-10-13 after the speed
numbers ("no need to measure more"); the 3 ms serial / np 4 runs were killed before
finishing. Rule 1 holds by a wide margin (np 4 = 0.35 × serial per step); rule 2 is open,
so the gauge check moves into the task as its acceptance criterion.

Side finding: a 1D step costs ~113 ms at 5 000 cells (~23 µs per cell-step), with or
without the function objects, so a full 1D run at dx = 1 mm to 10 ms is over an hour
serial. Where that time goes was not examined.

Probe cases left in `/root/mpi1d_probe` (outside the run corpus; safe to delete).

## Gauge check (P1-25 step 1, batch 1d-mpi task A2)

### Decision rule - written 2026-10-14 09:50, before the first run of this section

Case A as the current writer writes it, `t_end = 3e-3`, gauges 1 m and 2 m; written twice to
`/root/p125_gauge/np1` (`n_procs=1`) and `/root/p125_gauge/np4` (`n_procs=4`, scotch); the trees
differ only by `system/decomposeParDict`. Stages: blockMesh, `setRefinedFields -noRefine`, then
for np 4 `decomposePar -force`, `mpirun --allow-run-as-root -np 4 blastFoam -parallel`,
`reconstructPar`. Both run side by side (timing is not judged here).

Metrics: `reader.read_probes` on each run dir, `output.gauge_summary.summarize_trace`
(arrival = first sample above 1.1 x ambient, `ARRIVAL_FRAC = 0.10`, P1-13). At the 1 m and 2 m
gauges: |peak4 - peak1| <= 1 % of peak1, |I4 - I1| <= 1 % of I1 (positive-phase impulse inside
the 3 ms window; at 2 m the window may truncate it, identically in both runs), |ta4 - ta1| <=
1 % of ta1. All six must hold.
- Pass with scotch: Part B goes ahead unchanged.
- Fail with scotch: rerun np 4 with `method simple; simpleCoeffs { n (4 1 1); }` (the 1D mesh
  runs along +x, `writer.py:613-630`; D7). If `simple` passes, Part B writes `simple` for 1D only.
  If the failure is in peak only, also run the open-research settling variant (`adjustTimeStep
  no`, fixed `deltaT` below the smallest adaptive step, np 1 vs np 4) as a diagnostic: reported,
  not a pass.
- Fail with both: STOP; Part B is not started; the six numbers per method go to the owner.
- Reported, not judged: step count and ms/step of each run.

### Result (2026-10-14; run side by side on the office machine)

`/root/p125_gauge/np1`, `/root/p125_gauge/np4` (4 `processor*` dirs, `nProcs : 4`; both safe to
delete, D4). Table reproduced by the scratch script `gauge_table.py` (session scratchpad
`partA/`: `python gauge_table.py /root/p125_gauge/np1 /root/p125_gauge/np4`; `gauge_detail.py`
gives the sample-level differences). Probe `p` at 13 523 samples to t = 3 ms in both, the sample
times identical.

| gauge | metric | np 1 | np 4 (scotch) | delta |
|---|---|---|---|---|
| 1 m | peak overpressure [kPa] | 916.545 | 916.545 | < 0.001 % |
| 1 m | positive impulse [Pa s] (complete) | 123.163 | 123.163 | < 0.001 % |
| 1 m | arrival [ms] | 0.515789 | 0.515789 | 0 (same sample) |
| 2 m | peak overpressure [kPa] | 169.358 | 169.358 | < 0.001 % |
| 2 m | positive impulse [Pa s] (truncated at 3 ms in both) | 70.3752 | 70.3752 | < 0.001 % |
| 2 m | arrival [ms] | 1.97718 | 1.97718 | 0 (same sample) |

The two traces are not byte-identical: 3 614 of 13 523 samples differ at 1 m and 140 at 2 m,
by at most 7 Pa (7.6e-6 of the 1 m peak) and 3 Pa (1.8e-5 of the 2 m peak): last-digit
floating-point order in the rank-boundary exchange, three to four orders below the 1 % rule.
Both runs took 13 522 steps. Reported, not judged (side by side, so timing is contended): np 1
117.8 ms/step (ExecutionTime 1592.71 s), np 4 44.1 ms/step (595.65 s), ratio 2.67;
`decomposePar` + `reconstructPar` of np 4: reconstructPar 14.4 s.

**Verdict: PASS-scotch.** All six numbers are within 1 % (they are within 0.001 %). Part B
goes ahead unchanged with the writer's scotch `decomposeParDict`; the `simple` fallback and the
settling diagnostic were not needed. Caveat: this is a 1 m / 2 m, 3 ms, 5 000-cell check of the
unforced case; the ~2 % parallel-vs-serial peak offset seen on 2D/3D (`open-research.md:8-21`)
did not appear here.

## End to end through the app (P1-25, batch 1d-mpi task B5)

### Decision rule - written 2026-10-14 10:53, before either run of this section

`blastlab/tests/_e2e_foam_1d_mpi.py` (same rule in its docstring). Case A cut to 1 ms: 1 kg TNT,
R = 5 m, dx = 1 mm (5 000 cells), gauges 0.5 / 1 / 2 / 4 m, `t_end = 1e-3`, run through
`backend.solve_1d_foam(adaptive_write=False)` at `n_procs = 1`, then `n_procs = 4` (scotch), one
after the other, nothing else on WSL. In 1 ms the shock reaches the 0.5 m and 1 m gauges only.
1. At 0.5 m and 1.0 m, from the Result's gauge traces with `summarize_trace` (arrival = first
   sample above 1.1 x ambient, `ARRIVAL_FRAC = 0.10`): peak, positive impulse (inside the 1 ms
   window; at 1 m the window may cut it, identically in both) and arrival each within 1 % of
   serial. All six must hold.
2. ms/step np 1 / ms/step np 4 >= 2.0, ms/step = the median per-step `ExecutionTime` delta of
   each run's `log.blastFoam` over the same first N steps (N = the smaller step count; D6).
- Reported, not judged: app-path wall time np 4 / np 1 (preflight, `decomposePar` and the
  per-write `reconstructPar` included). If > 0.6 while rule 2 passes, the ingest is the
  bottleneck: owner question, no tuning in this batch.
- Also checked (machinery): 4 `processor*` dirs, every rank time reconstructed at the root, >= 1
  live frame with a full-length profile in both runs, the 4 gauges in the Result, the banner
  names `MPI ranks : 4` only at np 4 (D2), both runs end at t_end.
- A failed rule is reported with its numbers, never tuned.

### Result (2026-10-14, office machine, the two runs alone on WSL)

`python -u blastlab/tests/_e2e_foam_1d_mpi.py` -> `FOAM 1D MPI E2E: PASS` (exit 0), every
machinery check and both rules. Runs `/root/blastlab_runs/20261014-105507_1d_p26716-00` (np 1)
and `…/20261014-110320_1d_p26716-01` (np 4), 111 MB and 217 MB (`du -sh`; np 4 keeps every
write twice, root and ranks, as there is no write budget), safe to delete (not deleted here). Both
stop at t_end (`safety cap`), 4 121 steps each, gauge times identical (4 122 samples).

| gauge | metric | np 1 | np 4 (scotch) | delta |
|---|---|---|---|---|
| 0.5 m | peak overpressure [kPa] | 3592.76 | 3592.76 | < 0.0001 % |
| 0.5 m | positive impulse [Pa s] (complete) | 133.329 | 133.329 | < 0.0001 % |
| 0.5 m | arrival [ms] | 0.151719 | 0.151719 | 0 (same sample) |
| 1 m | peak overpressure [kPa] | 903.345 | 903.345 | < 0.0001 % |
| 1 m | positive impulse [Pa s] (cut at 1 ms in both) | 118.770 | 118.770 | < 0.0001 % |
| 1 m | arrival [ms] | 0.519408 | 0.519408 | 0 (same sample) |
| - | ms/step, median (mean) of 4 121 steps | 120.0 (118.1) | 40.0 (41.5) | ratio 3.00 (2.85) |
| - | app-path wall [s] (reported) | 492 | 215 | np 4 / np 1 = 0.44 |

Sample level (scratch `gauge_detail.py`, session scratchpad `partB5/`): 275 of 4 122 samples
differ at 0.5 m, 55 at 1 m, by at most 20 Pa (5.6e-6 of the peak) and 8 Pa (8.9e-6); the 2 m and
4 m gauges, not yet reached, are identical. `ExecutionTime` is printed to 0.01 s, so per-step
deltas come in 10 ms steps and the medians land on 120 / 40; the means give the finer ratio,
2.85, also above 2.0. Live view: 569 (np 1) and 111 (np 4) live frames, all full length; np 4
reconstructed all 161 rank times at the root. The wall ratio 0.44 is below 0.6, so the
per-write `reconstructPar` ingest is not the bottleneck at this size: no owner question.

**Verdict B5: PASS.** Through the app path, a 1D blastFoam run on 4 ranks gives the serial
gauge numbers to < 0.0001 % and runs 2.85-3.0x faster per step (2.3x end to end).

## Closing verdict (batch 1d-mpi, P1-25)

The gauge check (A2, 3 ms, 1 m / 2 m) and the app-path check (B5, 1 ms, 0.5 m / 1 m) both pass
with the writer's scotch `decomposeParDict`, unchanged; 1D now takes the run plan's ranks like
2D/3D (B2/B3). Default behaviour is unchanged (D1): auto stays serial below 200 000 cells, so
ranks are used when typed (case file / CLI; the Qt field is B4, held for the owner).