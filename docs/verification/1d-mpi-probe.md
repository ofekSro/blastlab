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
