> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [docs/SCOPE.md](../SCOPE.md)

# The QA nights — three unattended runs, 2026-09-09 to 2026-09-14

Three long unattended QA sessions, each with a written mandate and a rule that
nothing in `blastlab/` may be edited without permission. They produced most of
what is now known about this application's behaviour under load.

> ## ⚠ Chain results from Nights 2 and 3 are NOT valid
>
> Anything in those nights that depends on the **fireball** — impulse,
> positive-phase duration, secondary shock, late behaviour — ran before the
> **solver-review B0** fix, where `lambda.<phase>` was never written for a
> profile-fed stage. blastFoam blended the products back into the unreacted
> Murnaghan reactants and reset them to `pRef`: 4.43 MPa in, 101,298 Pa out.
>
> **The shock front itself is reasonable** — it is carried in air cells that
> initialised correctly — but every quantity that depends on the fireball's
> energy is invalid.
>
> Additionally, every **parallel near-field** number in those nights carries the
> ignition-seed defect: `method scotch` overestimated by 7 % at Z = 0.175 and
> 13–28 % at Z = 0.075.
>
> **The valid reference point** is the foam→foam reference chain in
> [physics-anchors.md §5](../verification/physics-anchors.md). Background:
> [solver-options-review.md](../verification/solver-options-review.md),
> [blastfoam-claims.md](../verification/blastfoam-claims.md).

---

## The three lessons worth keeping

**1. Running the matrix is half the work.** Night 2's 58 GUI scenarios produced
only six `qa.check` findings, and four of those were **bugs in the tests** — the
product answered correctly and the test could not accept the answer. Anyone who
stopped there would have concluded "the product is clean". The five real S2
defects came from somewhere else entirely:

| How it was found | What |
|---|---|
| Chasing one S3 finding to its root | **N2-07** — the preview draws a different mesh from the one that will be built |
| Looking at the pixels of a screenshot | **N2-09** — the gauge summary table is not on screen at all |
| Reporting on `checkpoint['timing']` that was saved for free | **N2-12** — 11.3 s of frozen UI |
| Comparing five runs of the same fixture | **N2-13** — stop time is set by ingest speed, not physics |
| Counting cells in the chain's initial condition | **N2-14** — every hand-off is non-physical |

The material was there. Nobody had read it.

**2. A conclusion from one case is not a generalisation.** Night 1 concluded
"AMR causes the SIGFPE" from a clean four-way reduction. Night 2 hit the
identical stack signature **in a case with no AMR at all**. Both were right about
their own case; the common denominator is `decode()` dividing `rhoU/rho` when
`rho` reaches zero. AMR is one route there; a chain hand-off is another.

**3. Record refutations as refutations.** Three hypotheses were tested and
killed, and are written down as killed rather than quietly dropped:

- *"A bad hand-off causes the crash"* — the run that crashed had one of the
  **cleanest** initial conditions of the eight (24 vacuum cells against 572 in a
  run that survived). The correlation is **inverted**.
- *"AMR is the cause of the SIGFPE"* — see above.
- *"Processor boundaries explain the excess cell count"* — the excess is
  621/630/654 cells while the number of internal boundaries grows 1 → 3 → 7.
  A boundary effect would not behave that way.

---

## Night 1 — 2026-09-09/10, the heavy runs

Machine: i7-14700, 20 physical / 28 logical cores, 127.7 GB RAM, WSL2 VM at
62 GiB (no `.wslconfig`), Windows 11 build 26200. Tree `caea639`.

**Nothing existing was edited and no state-changing git command was run.**

### Results

**39 PASS · 2 FAIL · 3 BLOCKED · 2 not run · 2 deliberately stopped.** Fast
matrix 29/29; WSL suites 8/8; `test_regression` byte-identical across all eight
items. Plus 11 measurement runs whose output is *a number or a diagnosis*, not a
pass/fail.

| Item | Outcome |
|---|---|
| R1 — full-size 2D default | **Not runnable.** 4.6–8.8 *days* of wall time |
| R2 — `_e2e_foam_obstacle2d axi` | **INCOMPLETE**, stopped ~55 min from the end |
| R3 — `_e2e_foam_refine2d` / `_e2e_foam_amr2d` | **PASS** / **FAIL (2 accuracy checks)** |
| R4 — `test_blast3d` | Not run, out of time |
| R5 — `_e2e_solver_viewer` | Not run, and BLOCKED (needs a real desktop) |
| R6 — cell-memory ceiling | **`BYTES_PER_CELL` verified** |
| R7 — parallel AMR at 4 and 8 ranks | **The measurement that was impossible on the dev machine** |
| R8 — `_e2e_gui_chain_foam` | **FAIL, twice — and it had never run before** |
| R9 — eye-check material | **BLOCKED** (environment, not code) |

### R1 — the pre-existing 2D default is not runnable, even on 128 GB

The full case (10 × 10 m, 0.025 m cell) validates here, where it is rejected on
the development machine. That looks like evidence for a hardware-dependent
default. **It is not.**

| Metric | Value |
|---|---|
| Cells | 2,301,289 (177,073 per rank, 13 ranks) |
| Wall time to deliberate stop | 2,914 s (48.6 min) |
| Physical time reached | **t = 0.105 ms of 294 ms — 0.036 % of the run** |
| Peak RSS, all ranks | 11,006,420 KB ≈ **10.5 GB** of a 62 GiB VM |
| Bytes per cell (13 ranks, 2D) | ≈ 4,900 |
| Time per step | ≈ 10.3 s, and **constant** — the mesh is fixed |
| Courant max | 0.398 of `maxCo = 0.4` — `deltaT` is already maximal |

Extrapolating: **~4.6 days** at the absolute lower bound, **~8.8 days**
realistically.

> **This is the answer to the "should the 2D default be hardware-dependent"
> question.** The reduction in the default was not compensation for a weak
> machine — **it was correct.**
>
> And more importantly: **the binding constraint is computation, not memory.**
> The run used less than 17 % of the VM. The application's own ceiling model
> (`BYTES_PER_CELL` × cells against RAM) would have approved a case **six times
> larger**, which would have run for two months.
>
> **So `Case2D` must not be made RAM-dependent.** A ceiling derived from RAM
> alone approves unrunnable cases. A hardware-dependent default would have to be
> derived from **throughput** (cells × steps per second) and a target run time.
> The number now exists: **~4.5 µs per cell per step at 13 ranks** on an
> i7-14700.

**A real bug caught on the way: a headless run is rejected on a 128 GB machine.**
The documented command failed immediately in a clean process:

```
ValueError: Invalid blastFoam case:
  ~2,301,289 cells exceeds the blastFoam cap of 1,134,519 (~2.8 GB of an
  assumed 4 GB WSL VM at ~2.6 KB/cell - the real size is unknown)
```

The machine gets a 62 GiB VM and the application decided it was 4 GB. The
hardware probe result is **process-local**; only the GUI persists it to
`settings.json` and primes it back. Every non-GUI path — script, CLI, test —
never seeds the cache and falls back to the conservative "assumed 4 GB VM"
ceiling. The proposed fix is to move the priming out of the GUI and into `env`,
so it happens once on load.

### R3 — AMR smooths the front, and the test measures exactly that

`_e2e_foam_amr2d` reached the solver for the first time ever and failed two
accuracy checks:

| Metric | AMR | uniform 0.025 m | Deviation | Threshold |
|---|---|---|---|---|
| Gauge peak | 17,633 kPa | 19,989 kPa | **−11.8 %** | 10 % |
| Arrival | 0.210 ms | 0.189 ms | **+11.1 %** | 10 % |
| Impulse (common window) | 1027.1 Pa·s | 998.0 Pa·s | +2.9 % | 15 % ✓ |
| Wall time | 56 s | 66 s | **1.19× for AMR** | — |

A peak 12 % low and an arrival 11 % late is the classic signature of a front
spread over more cells than the uniform mesh gives. Impulse passes because it is
an integral and insensitive to peak smoothing. **There is no bug in the AMR code
here** — the finding is that dynamic refinement in this test's configuration does
not keep up with the uniform mesh, and the test measures precisely that.

Note also that the time saving is only **1.19×** on a 25,600-cell case. Dynamic
refinement barely pays at that size.

### R6 — `BYTES_PER_CELL` does not need measuring per machine

The documented sweep varies `cell_size_m`, but **all three settings produce the
same mesh**: the charge, not the cell size, sets the cell size (25 kg TNT at "8
cells across the radius" gives 0.01927 m in all three cases). The sweep was
redone by varying the **domain** with the charge held fixed, all three serial.

| L [m] | Cells built | Peak RSS |
|---|---|---|
| 0.6 | 32,768 (32³) | 224.9 MiB |
| 0.8 | 74,088 (42³) | 326.2 MiB |
| 1.0 | 140,608 (52³) | 501.5 MiB |

Linear regression `RSS = a·cells + b`:

```
slope     = 2696.1 B/cell     intercept = 138.8 MiB     R^2 = 0.999638
```

| | B/cell |
|---|---|
| The constant in the application | **2,650** |
| Measured here (i7-14700, R² = 0.9996) | **2,696** — a **+1.7 %** gap |
| Re-derived from the original two points | 2,782 |

> **The constant is valid and does not need measuring per machine** — it is a
> property of blastFoam and the five-equation model, not of the hardware. One
> note: both independent estimates come out **above** 2,650, so the current value
> is slightly *optimistic* — it under-estimates memory and therefore approves
> slightly-too-large cases. **2,700 would be a better number than 2,650.**

*Caveat stated explicitly: the three runs were cut off after 400 s. That is valid
for peak RSS, which is reached in the first minute, but **full wall time was not
measured and is not reported.***

### R7 — parallel AMR at 4 and 8 ranks

Every rank count was run to the **same physical time** (`t = 6.0e-04 s`) rather
than "to the end", because with no terminate boundary "the end" is a ~117 ms
safety cap — hours per rank count.

| ranks | wall to t=6e-04 | speedup | cells (AMR) | gauge peak r=1.0 m | vs np=1 | peak RSS |
|---|---|---|---|---|---|---|
| **1** | 1,992.5 s | 1.00× | 66,284 | **2,569.13 kPa** | — | 438 MiB |
| **2** | 1,126.4 s | **1.77×** | 66,905 | **2,597.58 kPa** | **+1.11 %** | 594 MiB |
| **4** | 822.6 s | **2.42×** | 66,914 | **2,597.53 kPa** | **+1.11 %** | 915 MiB |
| **8** | 698.9 s | **2.85×** | 66,938 | **2,597.50 kPa** | **+1.11 %** | 1.54 GiB |

**(1) The gain runs out around 4 ranks.** 1→2 is 1.77× (88 % efficiency), 2→4 is
1.37×, 4→8 is only 1.18×. At np=8 that is ~8,000 cells per rank, well under
where MPI pays, and with AMR synchronising every 2 steps.

**(2) The peaks exceed the 1 % equivalence threshold — but not between rank
counts.** 2, 4 and 8 agree with each other to **0.003 %**. There is exactly one
step, between serial and parallel, and it is 1.11 % at every rank count. The
explanation is in the cell column: 66,284 serial against 66,905/66,914/66,938
parallel — **the decomposition changes the refinement decisions** (the
`densityGradient` criterion is evaluated per sub-domain, and a 2-cell buffer
behaves differently near internal boundaries), so the parallel mesh comes out
slightly finer and the peak slightly higher.

> This is not a regression — it is behaviour that had never been measured above
> 2 ranks. *(Night 2 later measured **0.042 %** on the same case after an
> unrelated fix; see below.)*

**(3) Memory grows faster than useful parallelism.** 8 ranks cost 3.6× the memory
and return 2.85× the speed on the same mesh. This supports `RAM_GB_PER_RANK = 2`
as correctly conservative, and suggests stopping at 4 for small cases.

**Load imbalance, measured without touching code.** The SIGFPE run was a 13-rank
AMR run with `balance no`, and its actual partition was:

```
processor0   2,071      processor7  31,650
processor1   5,457      processor8  36,642
processor2   2,251      processor9  10,558
processor3  28,403      processor10    594
processor4  30,457      processor11    586
processor5  36,697      processor12 10,696
processor6  37,230   <- the rank that crashed
```

**A 1:64 ratio between the busiest and the emptiest rank.** `scotch` splits the
**base** mesh evenly, then AMR refines only near the wave, so all the refinement
lands on a few ranks and the rest wait. **At 13 ranks with asymmetric refinement,
`balance no` wastes most of the machine.**

### R8 — the chain e2e failed, and both failures were real

First time this script had ever run. Two failures:

1. **The 3D stage never reached the Results panel** — 2 results instead of 3,
   although the run directory exists with 109 time directories, so **the solver
   did run**. The suspicion is the ingest/registration side, not the solver.
2. **A bug in the test script itself**, at line 142:
   `ts = list(g.get('times') or [])`. `g.get('times')` returns a numpy array, and
   `or` on an array of length > 1 raises `ValueError`. This fires **before** the
   two checks that are the whole point of the script — "stage N starts where
   stage N−1 ended, not at 0". The script was written and never run, so the bug
   survived. (`or` on an ndarray is wrong everywhere; worth grepping for.)

### The SIGFPE investigation — solved

> **In one line: dynamic refinement produces a cell where `rho = 0`, and then
> `decode()` computes `U = rhoU / rho` and divides by zero.** Not a decomposition
> problem, and not a timestep problem.

`deltaT` reconstructed from the crashed run's gauge file collapses three orders
of magnitude in a single step (6.38e-06 → 1.00e-08) and then repeats at the same
time for 43 consecutive steps.

Four reduction runs, criterion "survived" = passed `t = 6.0e-03` without an FPE:

| # | Run | Change | Result | Last `t` |
|---|---|---|---|---|
| 0 | **base** | — | crashed (`deltaT` collapse) | 0.00515532 |
| a | **serial** | `n_procs = 1` | **crashed — SIGFPE, same stack** | 0.0051419 |
| b | **cfl** | 0.4 → 0.2 | crashed | 0.00527242 |
| c | **noamr** | `amr_levels = 0` | ✅ **survived** | 0.00962512 |

Against the pre-registered decision tree: (a) crashed → **not decomposition**;
(b) crashed → **not the timestep**; (c) survived → **it is the dynamic
refinement**. **`rank 6` in the original was pure coincidence** — the serial run
raises the same FPE at the same physical time with the same stack. rank 6 merely
held the refined region (37,230 of 233,292 cells, the most of all 13).

**The mechanism end to end:**

1. `dynamicRefineFvMesh` refines/coarsens every **2 steps** around the wave and
   near the obstacle's sharp corner.
2. In one of those mappings a cell's `rho` drops to zero or denormal. The gauge
   nearest the corner shows `rho = 0.0909 kg/m³` — **7.5 % of atmospheric** — so
   that region is already near-vacuum, in a 0.125 m cell.
3. `c = sqrt(γp/ρ) → ∞` there → Courant explodes → the `deltaT` controller
   collapses from 6.4e-06 to 1e-08 and then to 7.5e-12.
4. `T` explodes: `max(T) = 1.35e+15`, `min(T) = 0`.
5. `decode()` computes `U = rhoU / rho`, divides by zero → **SIGFPE**.

**This is not a bug in blastlab's code.** It is blastFoam's AMR lacking
robustness to a near-vacuum state beside a sharp corner in a relatively coarse
cell (0.5 m base = 0.125 m at level 2). **The case is under-refined for an
obstacle with a corner.**

Three mitigation directions, in order of likelihood: ensure
`residualRho`/`residualAlpha` are configured in the EOS; raise `amr_interval`
above 2 (every mapping is a chance to create a bad cell); use a finer base mesh.

**Also worth a guard on the blastlab side:** the run agonised for **43 steps**
before the FPE, with `deltaT` collapsed three orders of magnitude and time not
advancing. `runloop` could detect that and stop with a comprehensible message
instead of letting blastFoam die in a SIGFPE after the user has waited.

### ⚠ The auto-cleanup incident

**Opening the GUI in R8 triggered blastlab's automatic cleanup, which deleted 34
runs — including the original SIGFPE run directory.** No `--clean-foam-runs` was
ever run that night. blastlab cleans automatically **on every GUI start** when
the run directory exceeds its threshold; it was 56 GB, over the limit, so the
cleanup ran and kept only the last few.

| | Night start | Peak (06:04) | Night end (06:20) |
|---|---|---|---|
| `/root/blastlab_runs` | 10 GB (2 runs) | **56 GB (40 runs)** | **12 GB (6 runs)** |

**What survived, and why the conclusion holds:** the copied `crashed_case.json`,
every number extracted into the report, and — most importantly — the **serial
reproduction**, which is the directory that actually carries the full SIGFPE
stack; the original never saved a log at all.

> **The operational lesson:** anyone who wants to keep a foam run for analysis
> **must** set `auto_cleanup: false` before opening the GUI, or copy the
> directory out. It runs without asking, and `_e2e_gui_*` triggers it. This was
> documented as a *feature*; in the context of "do not delete the runs before you
> have documented them" it is a **trap**.

*(This was fixed in two layers on 2026-09-17: `core.settings.load()` returns
`auto_cleanup=False` for a missing or corrupt file, and
`ui.testing.private_settings()` now actually writes the flag.)*

### Cross-cutting finding: every time estimate in the project is stale

The docstring for `_e2e_foam_obstacle2d.py` says *"planar ~5 min, axisym ~30 min
wall"*. On a **much stronger** machine the axisymmetric case takes **~105
minutes** — 3.5× over.

The cause: the charge resolution target went from 5 cells to 8 across the radius.
In 2D that multiplies cells by (8/5)² = **2.56** and shrinks `deltaT` by 1.6
(CFL) — **~4.1× in total cost.** The same change that broke two e2e fixtures also
invalidated every time estimate in these files, and nobody updated the headers.

---

## Night 2 — 2026-09-12, the first full GUI matrix

| | |
|---|---|
| GUI scenarios | **58/58** · 340+ screenshots · 118 characterisation notes |
| WSL suites | **8/8 PASS** |
| Fast matrix | **30/30 PASS** |
| Regression | **byte-identical at the gate and at close** |
| Crash hunt | **1 of 17 ≈ 6 %**, case preserved |
| Cleanup canary | 83 → 153 runs — **only ever increased** |
| Commits | 9, all green; tree clean; 0 untracked |

### Why the GUI matrix had never run

`_qa_gui_harness.py:412` did not catch the `OSError` from `ImageGrab`. In a
disconnected RDP session `ImageGrab.grab(all_screens=True)` always raises
`OSError('screen grab failed')`, so the exception escaped the scenario, was
logged as an S1 `harness-crash`, and the scenario was marked `crashed`.

> `--resume` replays `deferred` scenarios but **never `crashed` ones**. One night
> would burn 55 of 59 scenarios permanently, recoverable only by re-running the
> entire matrix. **That is why the GUI QA matrix had never run.**

The cure was already in the file and nobody had reached it: `print_window()` uses
`PrintWindow(PW_RENDERFULLCONTENT)`, which renders from the window's own device
context rather than the screen. It sat behind a condition requiring `ImageGrab`
to have **succeeded** and returned luminance < 6 — dead code in exactly the
session where it is needed.

**Verified in pixels, not by eye:** 7/7 real screenshots, `capture: printwindow`
in every sidecar, and **1,059–1,788 distinct colours per screenshot**. The colour
count is the only meaningful test — a `PrintWindow` that draws only the frame
gives uniform grey that passes a luminance check and teaches nothing.

### Two environment traps neutralised before they did damage

**1. A user-level environment variable does not reach new shells.** The tool's
shell host was created before the variable was set, so every child inherits the
old block. **The consequence if this had not been caught:** any script that builds
an `App` without pointing `BLASTLAB_SETTINGS` somewhere safe starts the automatic
cleanup — **one unprotected `App()` deletes ~80 of 83 runs.** It had already
happened once (34 runs / 56 GB on Night 1).

**The fix was structural, not instructional:** a `qa.ps1` wrapper. Every python
call that night goes through it, and it sets the variable and does the `cd`. It
cannot be forgotten, because it *is* how python gets started.

**2. Commas in PowerShell.** `--redo B06,I05` without quotes arrives at argparse
as one bad value, and the harness prints `nothing to do` and **exits 0** — a
silent failure that looks like success. Every argument with a comma is quoted now.

### Findings

| id | sev | Title | Class | Commit |
|---|---|---|---|---|
| N2-01 | S1 | `shot()` did not catch `OSError` and permanently crashed 55 scenarios | fixed | `a5ef729` |
| N2-02 | S1 | `I05` crashed **because the product rejected bad input correctly** | fixed | `75a9e9e` |
| N2-03 | S1 | `B06` leaked a live solver into the next scenario (F5 is bound to `_run_single`) | fixed | `75a9e9e` |
| N2-04 | S2 | `C10` asserted on a label its own case **cannot** produce | fixed | `62984c7` |
| **N2-05** | S3 | `set_case` blocks 3.2–5.6 s; `plan_levels` runs twice × `level_map` over 32.8 M cells | fixed (afternoon) | batch |
| **N2-07** | **S2** | **The preview always plans with TNT's `rho0` — it draws a different mesh from the one that will be built, for every non-TNT material** | fixed (afternoon) | batch |
| N2-08 | S3 | `feed_result` (3D viewer) blocks 2,183 ms against a 1,000 ms budget | diagnosed, not fixed | — |
| **N2-09** | **S2** | **The gauge summary table is not on screen below 960 px of height; usable only from 1060 (the screen is 1080)** | fixed | `5afe1ca` |
| N2-06 | S4 | A 20-digit cell count in the blocking message | fixed | `2fa79f2` |
| N2-10 | S4 | The "Summary CSV" button label is truncated — shows "ummary CSV" | fixed | `2fa79f2` |
| N2-11 | S3/S4 | Y-axis labels collide in the multi-panel 1D gauge plot | fixed | `2fa79f2` |
| **N2-12** | **S2** | **`click Run` on a 3D case freezes the UI for 11,279 ms; `set_case` 7,836 ms** | fixed | batch |
| **N2-13** | **S2** | **A run's stop time is set by ingest speed, not by physics — the same case ends at different times; a chain is not reproducible** | fixed (afternoon) | `b343d89`+ |
| **N2-14** | **S2** | **Every hand-off into stage 3 is non-physical** — 12 to 572 vacuum cells of 9,375 | fixed with N2-13 | — |
| **N2-15** | **S2** | **R2 cannot finish on this machine** — the 2D arrival stop drowns in ingest | fixed | `c130210` |
| **N2-16** | **S2** | The live path was completely dead for obstacle-carved cases | fixed | `c130210` |

### N2-07 — two contradicting sources of truth on one screen

`gui/preview_panel.py:42` calls `refine.plan_levels(case)` **without `rho0`**, so
`refine.py:123` fills in the default `JWL_TNT['rho0'] = 1630`. Meanwhile
`validate_case` and `writer.py` both pass the **selected material's** `rho0`.

`rho0` sets the charge radius, and the charge radius is what `required_level()`
turns into a refinement level. **So the two can only agree when the material is
TNT.**

| Case | Material | rho0 | The preview draws | What is actually built |
|---|---|---|---|---|
| 2D | **ANFO** | 850 | `lmax=4`, finest **0.005 m**, **5,757** cells | `lmax=3`, finest **0.01 m**, **4,197** cells |
| 2D | RDX / PETN / HMX | 1770–1890 | 5,757 cells | **5,457** cells |
| 3D | **ANFO** | 850 | 9 zones, `auto_level=7` | 8 zones, `auto_level=6` |
| any | TNT | 1630 | — | **identical** (it is the default) |

**The real severity:** for ANFO the preview draws **a whole refinement level more
than will be built**, with the worst cell 2× smaller than reality. And at the same
time the **validation strip shows the correct number**. On one screen, the strip
says 4,197 cells and the picture shows a 5,757-cell mesh with an extra level.

**Why it survived:** `test_gui_refine_preview.py:149` — the only preview test in
the project — itself calls `refine.plan_levels(c2)` **without `rho0`**. It does
not test the behaviour; it **reproduces the bug and confirms it against itself.**
Every test in the file uses the TNT default, the one material with no gap.

**A neat convergence:** the fix for N2-07 — pass the plan already computed by
`validate_case` to the preview instead of recomputing it without `rho0` — **also
fixes N2-05**, because it removes the second 1.93 s call. Two findings, one fix.

### N2-05 — where the 5.5 s UI freeze actually was

Splitting the gap in two was what made it tractable:

```
SYNCHRONOUS set_case :       14 ms
WORST GAP while settling:  5,374 ms
```

**The call itself is cheap.** All the blocking is in a scheduled callback, so a
profile wrapping only the call shows 0.174 s and **misses the entire problem**.

Profiled over the whole event loop, the "rendering" hypothesis died in the
numbers — all VTK/pyvista together is ~0.6 s, most of it one-time construction.
**`plan_levels` alone is 3.87 s of ~5.5.** Two independent causes, each worth
about a factor of 2:

1. **`plan_levels` is computed twice per `set_case`** — once from `validate_case`
   and once from `preview_panel.py:42`, at 1.93 s each.
2. **`level_map` builds the full fine mesh, separately for every zone.** With
   `lmax` capped at 4, that is dx = 0.03125 m over a 10 m cube = **320³ ≈ 32.8
   million cells**; per zone it allocates `np.ones(shape, bool)` (32.8 MB),
   compares on three axes, then `np.where(...).astype(np.int8)` (another 32.8 MB).
   **The cost is proportional to the whole domain's volume, not to the zones'.**

Fixed by evaluating `level_map` on a sub-block via `searchsorted` per zone:
**1,445 → 245 ms**, byte-identical against a baseline captured beforehand.

### N2-12 — the 11-second freeze was not what it looked like

`checkpoint['timing']` stores `max_gap_ms`, `p99_gap_ms` and `big_gaps` for every
scenario, for free. Nobody had ever produced a report from it. When produced:

| ms | Scenario | Action |
|---|---|---|
| **11,279** | `D04` | **`click Run`** |
| 7,836 | `D04` | `set_case` |
| 4,246 | `C10` | `set_case` |
| 3,151 | `G02` | — |

`C10` was not the worst — `D04` was, by 2.7×. Outside those two, no scenario
crossed 3.2 s and most were under one second, so overall responsiveness is fine
and these are genuine outliers, both on the 3D path.

**The diagnosis:** `_run_single` itself is **57 ms**. The freeze is an avalanche
of ~120 pyvista/VTK C extension modules importing mid-run and choking the GIL.
Fixed by warming the import in a daemon one second after startup: **13,266 →
2,643 ms** through the product.

### N2-13 — a run's stop time is set by ingest speed, not physics

Five runs of the same fixture, same machine, back to back:

| Attempt | Stage 1 ended at | Stage 2 ended at |
|---|---|---|
| 01 | 0.199 ms | 3.395 ms |
| 02 | 0.217 ms | 3.626 ms |
| 03 | 0.200 ms | **4.725 ms** |
| 04 | **0.190 ms** | **2.065 ms** |
| 05 | 0.194 ms | 2.358 ms |

**Stage 1 spreads ±7 %. Stage 2 spreads by a factor of 2.3.** Independent
confirmation from a completely different source — the count of time directories
the solver wrote for those same five stage-1 runs: **169 · 175 · 174 · 184 ·
207**, a 22 % spread. The solver really did run different lengths.

**The mechanism, read from the code.** `backend.py:818` checks arrival **on every
ingested frame**, and `runloop.py:578` implements the stop as `stopAt writeNow` —
*"stop wherever you are now"*, not *"stop at the time the arrival happened"*. But
the ingest runs **behind** the solver: the Python loop scans `postProcessing` at
its own rate, with a per-poll batch quota, **through WSL's 9p filesystem**. A 1D
solver on 100 cells is orders of magnitude faster than that IO.

> **So the end time is wherever the solver had got to when the Python ingest
> caught up to the arrival frame.** That is wall-clock, not physics. Fast ingest
> → small overshoot → short run. Slow ingest → large overshoot.

Consequences: a chain is not reproducible; the same case returns different peak
and impulse maps; and it is a good candidate explanation for why the stage-3
failure is intermittent — stage 3 receives a different initial condition every
run.

**N2-15 is the same mechanism at a pathological scale.** `_e2e_foam_obstacle2d
axi` ran 8.7 hours to t = 20.5 ms without stopping, on a **171,604-cell**
globally-refined mesh, with **2,193 live samples queued** — the ingest hours
behind the solver. The 2D arrival check runs only on *ingested* directories, and
each ingest is a 171k-cell field read through 9p. **The solver writes faster than
the ingest reads, so the gap only grows and the stop never arrives.** The contrast
with 1D is the direction of the fix: in 1D the arrival check runs on the live
sample (~100 values, cheap); in 2D it runs on full time directories.

### N2-14 — every hand-off into stage 3 is non-physical

Independent of the crash:

- The 2D→3D initial condition contains **12 to 572 vacuum cells** of 9,375
  (0.13 %–6.10 %) — **in all eight runs examined**.
- In **3 of 8** it contains zero or negative pressures and temperatures, up to
  **108 cells**. A negative pressure is not round-off on a valid value.
- `T_max` in the initial condition reaches **9.0 × 10⁸ K**.
- The count varies by a factor of **48** between identical runs (12 → 572) — a
  direct expression of N2-13.

### The crash hunt

| Source | Attempts | Failures |
|---|---|---|
| Night 1 | 5 | 0 |
| Night 2, attempts 01–12 | 12 | **1** |
| **Total** | **17** | **1** — ≈ **6 %** |

The signature is identical to Night 1's — but **with no AMR**:

```
#1  Foam::sigFpe::sigHandler(int)
#3  Foam::operator/<Foam::Vector<double>, Foam::volMesh>(...)
#4  Foam::compressibleBlastSystem::decode()
max(p): 103094, min(p): 83434.6          <- pressures entirely healthy
max(T): 1.47468e+10, min(T): 0           <- temperature meaningless
```

Healthy pressures beside `T = 1.5e10` is the fingerprint: `T = p/(ρR)`, so
`ρ → 0`. The crash happens **20.7 µs after stage 3 begins** — almost immediately
from the handed-off state.

**Later that day it was made reproducible on demand** (2 minutes per run, same
stack, same time), and the `min(rho)` trajectory was extracted: it falls ~2 orders
of magnitude per write, 2.4e-8 → 2.8e-17 — below `DBL_EPSILON`, which is
blastFoam's internal `rho.air` floor. A healthy run dives to 2.5e-4 and
**recovers**. The mechanism is a runaway drain.

### Four layers to a deterministic chain

Each layer was only visible once the previous one was handled:

1. **The clock-dependent stop** (N2-13): `stopAt writeNow` after ingest lag.
   Isolated measurement: detection at t = 5.2e-5, stop at 1.16e-4 — **half a run
   of tail**. The detection itself was always deterministic: `p_last = 2.212e+06
   Pa`, identical to the digit across runs.
2. **The write schedule is clock-dependent too:** `maybe_adapt` rewrites
   `writeInterval` based on how many frames the ingest managed. Fixed by pinning
   the schedule for chain stages (`case.adaptive_write = False`).
3. **The anchor is the last write before arrival.** The crossing falls between
   mesh writes; the write before it sits on the fixed mesh, is identical in every
   run, and is the state the chain wants anyway — shock inside the domain, before
   boundary interaction. **Only the hand-off surface is pinned**; gauges, maps and
   snapshots stay the full run's record.
4. **Scan forward, not back.** In the long tail the boundary cell vents back below
   the threshold, so the criterion is not monotone and walking backwards broke
   silently.

**Verification: 4 full chains, `s1 = 0.050 ms`, `s2 = 0.194 ms`, stage-3
`t0 = 0.00019422544` — identical to the digit**, zero failures.

> **The insight that unified the night:** the old hand-off was a **late state** —
> the shock hits the boundary at 0.194 ms and the old code handed off 2–4.7 ms,
> after venting. **That is where N2-14's vacuum cells came from** (rho 1.6e-6,
> a fabricated |U| of 36 km/s, T 8.3e6). The pinned hand-off is free of them by
> construction: rho.expl ≥ 0.198, T ≤ 2,149 K, **zero floored cells**. The floor
> stays as a safety net.

### A floating-point tie that broke every count-dependent reader

The root of N2-16: an obstacle edge at y = 1.0 sat **exactly** on a cell centre
line (`120.5 · (4/482) = 1.0`), and Python and foam broke the tie in opposite
directions — **171,580 against 171,604 cells**. That broke every count-dependent
reader, including the write ingest. The fixture moved to 0.996 (half a cell of
clearance) and the two counts became identical to the digit. **The structural
remedy — snapping obstacles to cell faces, as refinement zones already do — is a
design item.**

### P5-3 was solved by an unrelated fix, and nobody knew

Three runs on the current tree, same case as R7, same physical time:

| | cells | peak G1 | wall |
|---|---|---|---|
| np=1 | 78,434 | **2,413.96 kPa** | 2,198 s |
| np=4, balance **on** | 79,724 | **2,412.94 kPa** | **699 s** |
| np=4, balance **off** | 79,715 | 2,412.94 kPa | 930 s |

**Serial↔parallel peak deviation = 0.042 %.** Night 1 measured **1.11 %** — a
factor of 26. The threshold is 1 %, so what had been logged as needing an owner
decision now sits with **24× margin**. The cause was an unrelated commit that
moved `amr_refine` 0.4 → 0.2.

Three honest notes recorded alongside:

1. **It contradicts Night 1's inference.** Earlier notes state that tightening
   `amr_refine` to 0.2 *raised* the mismatch from 0.6 % to 1.453 % on a different
   case. Here the same tightening *lowered* it to 0.042 %. Two cases, two opposite
   answers. **Reported as a measurement, not reconciled.** *(It was later resolved
   as no contradiction at all: the A/B measures a peak-map median on an
   axisymmetric case, R7 measures point gauge peaks on a different case. Both
   gates pass; there is no decision to make.)*
2. **Cell count and physics deviation are decoupled.** The cell excess is +1.64 %
   while the peaks agree to 4 parts in 10,000.
3. **The processor-boundary hypothesis weakens on Night 1's own data** — the
   excess is 621/630/654 cells while internal boundaries grow 1 → 3 → 7.

**Load balancing gives throughput without changing the answer:** 79,724 against
79,715 cells (0.011 %), peaks identical to two digits, and 699 s against 930 s —
**1.33× throughput.** Together, np=4 is **3.1× faster than np=1**.

> **A trap avoided:** `writer.py:40` does `from .dicts import AMR_LOAD_BALANCE` —
> a *from*-import. Setting `dicts.AMR_LOAD_BALANCE = False` alone **would not have
> changed the case written**, and the experiment would have returned "no
> difference" for entirely the wrong reason.

---

## Night 3 — 2026-09-13/14, regression and UX review

| | |
|---|---|
| Fast matrix ×3 | **89/90** → the deterministic failure fixed (`eb49bba`) → ×3 green |
| WSL suites | **7/8** — the one is N3-01 (bimodal, root known) |
| GUI matrix | **58/58**, 3 findings — all fixed or classified |
| Chain signature | **s1 = 0.050, s2 = 0.194 — identical to the digit**, surviving every edit that night |
| UX review | 20+ screenshots, two themes, three widths; **6 findings** + four documented strengths |
| Final gate | report / results-fields / regression green; canary 303 (only rose); settings hash unchanged |

**N3-01 — the 3D copy of N2-13/15.** `test_foam_3d_smoke`'s symmetry gate is
**bimodal**: it alternates PASS/FAIL with failure numbers identical to the digit
(8579/8084). The 3D arrival-stop overshoot quantises to two possible final writes,
so the function-object map accumulates to a different time. Documented, priority
raised — not patched at midnight, because it is the same design item.

**A process incident recorded honestly:** editing `TODO.md` through PowerShell
corrupted the Hebrew encoding and the corruption was committed. It was recovered
from the parent commit, and a permanent rule was set: **Hebrew markdown files are
edited only with editor tools, never through PowerShell strings.**

### The UX review

Method: a real user journey — *"a new engineer wants the pressure at 5 m from
10 kg"* — captured end to end through the live application, in two colour themes
and three widths (1280/1600/1900), plus a full inventory of validation messages.
Every finding was observed in pixels or read verbatim.

**What works, and deserves recording:**

1. **The money screen answers the question.** After a 30-second run, the Results
   tab shows in one table: peak 104.4 kPa, arrival 5.676 ms, phase duration, both
   impulses — exactly what the user asked. *(This is also the visible payoff of
   fixing N2-09: that table was not on screen at all two days earlier.)*
2. **The theme system is complete and consistent.** Through the real switch, light
   mode replaces everything including ttk tables and the preview. *(A first version
   of the screenshot tool bypassed the switch and produced fake "findings" —
   documented so it does not recur.)*
3. **Message quality is high.** *"needs AMR level 4 … lower the base cell to at
   most 0.1 m"* — a message that says what to do. Same standard for *"AMR levels
   must be 1..5"* and *"Gauge (5.0, 1.0) outside domain – will be dropped"*.
4. **Clean scaling to 1900 px**, and the exported report is a single self-contained
   HTML with table and images embedded — a real shareable artefact.

**Findings — all six closed on 14.09:**

| id | Severity | Finding | Suggestion |
|---|---|---|---|
| **UX-01** | **S3 · owner decision** | The default greets the first user with a red warning about itself (*"No terminate boundary and no end time…"*) — the first foam 2D/3D screen opens looking broken | Either one terminate side by default, or an info tone while the case is still an untouched default |
| UX-02 | S4 | The label "Charge [kg TNT] or kg/m" crams two units; kg/m applies only to planar | Geometry-conditional label |
| UX-03 | S4 | The list editors (Gauges/Obstacles) give no format hint in the add field | Placeholder `"x y"` / `"x0 x1 y0 y1"` |
| UX-04 | S4 | Axisymmetric silently ignores x ≠ 0 in the charge centre (rightly — the charge is on the axis) without saying so | An info note that x is neutralised on the axis |
| UX-05 | S4 | In Results, a single plot is vertically centred and leaves a large empty band above it (obvious at 1900 px) | Top anchoring or a height cap on the figure |
| UX-06 | S4 | In the HTML report, section headings come from filenames (*"blast 2d pressure"*) and the "Gauges" heading is duplicated | Title-case from the field, not the filename |

**What was NOT found:** no substantive contrast problems, no validation gaps (a
suspected "charge outside the domain" gap was **refuted** — the validator catches
it in every geometry; the confusion was in the tool), no layout breakage at the
widths tested, no unit inconsistency.

**Action feedback:** across all 58 scenarios' timing data, outside the documented
outliers, **no action crossed one second** and the vast majority were under
200 ms.

---

## Decisions taken with nobody to ask

Recorded because each one changed what was measured.

**Night 1:**

1. **No `git pull`** although the brief asked for one — the night's first rule
   forbids it. It was not needed: the fix was already in HEAD.
2. **R1 was run with `env.hardware(probe=True)` in-process.** The documented block
   was rejected immediately; this is not a code change but the same public call
   the validation block already makes. **Both outcomes are documented** — the
   rejection and the run.
3. **R1 and R2 were stopped deliberately**, after full documentation, and marked
   INCOMPLETE rather than FAIL. An 8-hour budget against runs measured in days.
4. **R6's sweep was changed** — vary the domain, not the cell size, because as
   written it produces one point rather than three.
5. **R7 measured to a fixed physical time** rather than "to the end". The second
   gauge never received the wave and therefore **does not participate in the
   comparison** — stated explicitly rather than presented as measured.
6. **`balance yes` was not tried** — it requires editing a tracked file. The diff
   is documented, alongside the measured 1:64 imbalance.
7. **A `base` control run was added** before the three reduction runs. Without it
   they cannot be interpreted.

**Night 2:**

1. **Three findings from the B/C/H/I groups are bugs in the tests, not the
   product.** In all three the product answered correctly and the *test* could not
   accept the answer.
2. **`C10` did not get a new fixture.** The natural move — change the case so it
   passes validation — would change the preview's rendering cost, which is exactly
   the measurement N2-05 came from. Instead the assertion moved to where it is
   true, and the 3D case got the assertion that **is** true of it.
3. **N2-05 was not fixed in the morning session.** The symptom was clear, the root
   was not, and any fix changes product behaviour. Per the rule set in advance:
   document, do not touch. *(It was fixed in the afternoon, after the owner
   granted full freedom at ~15:00.)*

---

## What these nights left open

- **The intermittent stage-3 crash** is reproducible on demand from the preserved
  case but **not explained**. 4/4 healthy on the fixed code — *promising, not
  proven*, and it stays that way until there is a sample.
- **The spatial verification** (`cellLevel` at np=1 against np=4) was never done.
  After the 24× margin appeared it is less urgent — it remains an understanding
  question, not a blocker.
- **Obstacle snapping to cell faces** is a design item, not a patch.
- **UX-01**, the default that warns about itself, is an owner decision.
