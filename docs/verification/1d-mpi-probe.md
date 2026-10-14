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