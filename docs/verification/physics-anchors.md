> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [docs/SCOPE.md](../SCOPE.md)

# Physics anchors and measured numbers

What this code has been checked against, what the numbers came out at, and the
handful of physics facts that change how the code should be read.

---

## 1. The accuracy anchor: Kingery-Bulmash

`blastlab/tests/test_foam_kb_anchor.py` compares a free-air 1 kg TNT solve
against the published Kingery-Bulmash free-air curves. It is the repository's
primary claim to being right about anything.

| Stage | KB ratio at Z = 1–4 |
|---|---|
| Before the charge-rasterisation fix | 0.72–0.77 |
| With the 8-cell charge | **0.85–0.89** |
| **With `afterburn = miller`** | **1.02–1.20** (1.20 at Z = 1, 1.02–1.04 at Z = 2–4) |

The acceptance band in the test is **0.80–1.35**. At r = 1.5 m with second-order
MUSCL reconstruction: 0.75 → 0.90 of KB.

### Why a pure JWL detonation reads ~13 % low

A pure JWL detonation carries only the material's own **anaerobic** energy. That
lands a free-air 1 kg TNT anchor roughly **13 % below** Kingery-Bulmash, and that
is physically correct, not a bug: the published KB curves are measurements of real
events in real air, where the reaction products continue to burn with atmospheric
oxygen after the initial release.

`afterburn = miller` models that second energy release and brings the anchor to
1.02–1.20 KB at Z = 1–4.

> **Only the TNT row is calibrated against data.** The other materials scale by
> oxygen balance and are *ordered estimates*, not measurements. Refit only after a
> change to what the charge deposits or to `FOAM_EXP_CELLS` — never before, or it
> gets calibrated twice. The long comment in `blastlab/solvers/foam/materials.py`
> is the authoritative version.

---

## 2. Physics facts that change how you read the code

### Activation model — near-field arrival differs by design

The native solvers detonate the whole charge at t = 0. blastFoam's default
`linear` activation burns it at the detonation velocity. Near-field arrival times
therefore differ by **tens of per cent at 1–2 charge radii** and converge within a
few metres. **Expected, not a bug.**

Measured near-field lag (foam against native):

| | r = 0.6 m | r = 1.0 m |
|---|---|---|
| `activation = linear` | **+36.7 %** | **+23.6 %** |
| `activation = none` | +23.1 % | +12.8 % — but overshoots peaks by 1.43× / 1.36× |

### Displayed impulse is net, not positive-phase

The impulse the application displays is the **net overpressure impulse over the
whole record, negative phase included** — *not* the positive-phase impulse that
Kingery-Bulmash tables report. It therefore reads systematically low against
published data. This is intentional and documented; it is not a calibration
error.

**In any comparison, record peak, positive-phase impulse *and* arrival.** Never
peak alone — a 3.7 % impulse shift once passed every peak-only anchor in this
suite.

### Pressure is coloured logarithmically by default

A blast spans four decades of pressure in a single frame. On a linear colour bar
the entire shocked field collapses into the bottom fraction of a per cent, so the
3D viewer defaults to log colouring.

### AMR runs are serial in this version

`reconstructPar` cannot follow a changing mesh. **`Lohner` is the default error
estimator** — `densityGradient` starved the axis in axisymmetric cases and was
implicated in a class of SIGFPE failures (see
[blastfoam-claims.md §4](blastfoam-claims.md)).

### Memory models exist because a native overrun kills the window

`core/constants.py` carries a measured ~2700 B/cell for blastFoam inside WSL and
an analytic per-cell model for the native solvers — because a native run that does
not fit raises `MemoryError` and takes the GUI window with it.
`core/hardware.py` turns both into cell caps.

---

## 3. Measured numbers

### Native against blastFoam

foam peaks **1.10–1.16×** native at r = 1–4 m with arrivals within **0.7–4.5 %**,
both monotonic (`test_foam_1d_vs_native`). With second-order MUSCL the foam/native
peak ratios collapse to **0.97–1.01**.

### Mass and energy conservation

- Energy exact to **4e-16**.
- Clipped volumes verified to **2e-16** against closed forms and **1.7e-6**
  against a 1200³ brute-force count.
- Mass keeps the staircase deficit **by design** (see §4 below).
- 2D-vs-1D arrival at r = 1.5 m: 5.21 % → **3.92 %** (gate tightened 6 % → 5 %).
- 2D→3D remap peaks: 11.9–13.6 % → **7.6–9.4 %**.

### Charge mass actually deposited

| Configuration | Deposited / requested |
|---|---|
| 3D, 5 cells across the charge radius | 0.979 |
| 3D, 8 cells | 1.027 |
| 1D | 0.995 |

Over 400 random burst offsets, moving from 5 to 8 cells cut the RMS spread from
**1.00 % → 0.41 %** (3D) and **3.67 % → 2.95 %** (axisymmetric).

### AMR

- 3D AMR gauge arrival **+18 %** against a static mesh, with peak within 2.7 % — a
  real resolution difference at the gauge, **not** an `adjustLocations` artefact.
- Parallel vs serial AMR: arrivals 0.3–0.5 %, point peaks 0.15–4 %, impulse 4–9 %
  late, peak-map median **0.605 %**.
- Speed at np=2: **340 s → 237 s (1.43×)**.

### Chains into blastFoam

With the shared clock: arrivals **+2.31 % / +3.36 %**, peaks **+4.87 % / +3.37 %**;
mass and energy match the profile to **1e-11**. *Without* the shared clock the
gauges read 53 % / 34 % early — which is what the shared clock exists to prevent.

### Hardware

`BYTES_PER_CELL = 2650` measured. 59,319 cells → 305.1 MB; 262,144 cells →
843.3 MB; ~148 MB fixed overhead. On the development machine that allows
**1,134,519 cells at 2 ranks**.

### Memory and interface

- Replay record: 614 MB → **199 MB**.
- `feed_result`: 2364 ms → 259 ms → **~1 ms** per snapshot tick.
- `mesh_polydata`: 320 ms warm-up, then **5–8 ms/frame**.
- AMR mesh overlay: ~45 ms/frame at 640².

---

## 4. The charge-mass staircase, and why the deficit is kept

blastFoam's `sphericalMassToCell` sets `alpha = 1` in the cells whose **centres**
fall inside the charge radius, so the mass actually deposited is the staircase
volume: ~0.85 of the request at 5 cells across the radius. Eight cells brings it
to ~0.94 — at a **2.6× (2D) / 4.1× (3D) cell-count cost**.

The deficit is therefore a deliberate accuracy/cost trade, not an oversight. An
analytic alternative exists in the guide (`volScalarFieldMassIntegrated`) and is
written up in
[solver-options-review.md §7](solver-options-review.md) — with the warning that
the afterburn calibration was fitted with the present deficit baked in and would
need refitting.

---

## 5. The foam→foam reference chain

**What it is.** One reference run of the `gui_foam` chain (1D→2D→3D, the same
`stageN_case.json` files that ran the second QA night), on the tree **after** all
the hand-off fixes. It replaces the numbers marked invalid in the earlier QA
nights.

Tree `5553f08`, branch `n5-parallel-and-handoff`, 2026-09-19, np = 1 (serial).

| Stage | Stopped by | Gauge | Peak | Arrival | Hand-off energy (rel) |
|---|---|---|---|---|---|
| 1D | Shock at boundary | r = 0.15 | 7055.9 kPa | 0.0326 ms | — (source) |
| 2D | Shock at terminate boundary | (0.3, 0.5) | 1867.2 kPa | 0.0760 ms | **−0.0203 %** |
| 3D | **numerical instability** | (0.8, 0.5, 0.3) | 22137.4 kPa | 0.1873 ms | **+0.0001 %** |

### What it establishes

1. **The hand-off energy check passes at every seam** — −0.02 % and +0.0001 %.
   Both EOS/λ hand-offs are accurate. This is exactly what the solver-review
   B0/B1 defects broke, and it is now monitored automatically.
2. **The 2D export's vacuum census: zero cells below 1e-3** (min ρ = 9.17e-02),
   against **20 cells** in the earlier artefact (min 1.711e-04). The 2D stage no
   longer hands off vacuum.

### The qualification — stage 3 is still unstable

The 3D stage stopped on `numerical instability`, both **with and without**
`fieldInf`/`lInf` (an A/B pair: same arrival, same energy, same stop). So:

- **It is not a regression** from the hand-off work — the `lInf` added in that
  round is cleared.
- It is a property of this specific case: **25 kg in 1 × 1 × 0.6 m** — extreme
  confinement. The 22 GPa peak speaks for itself.

**A fully clean reference run needs a less confined 3D case.** This does not block
the hand-off work — the hand-off itself, which is the thing that was fixed, is
accurate at both seams.

---

## 6. Test gates

```
cd blastlab/tests
python test_regression.py        # reruns baseline cases, byte-compares output
python test_foam_writer.py       # OpenFOAM case generation (no WSL needed)
python test_case_validate.py     # case validation rules
python test_blast2d.py           # 2D physics suite
python test_blast3d.py           # 3D physics suite
python test_foam_env.py          # finds WSL and blastFoam
python -u test_foam_1d_vs_native.py   # real solve, WSL
python -u test_foam_kb_anchor.py      # the Kingery-Bulmash accuracy anchor, WSL
```

**`test_regression.py` must be green byte-for-byte before any other measurement
is trusted.**

Naming convention: `test_*.py` are fast and safe to run at any time; `_e2e_*.py`
do real solves and open real windows; `_qa_*.py` are the large interactive
harnesses.

---

## 7. Measurement discipline — learned the hard way

1. **Never measure peak alone.** Every comparison records peak, positive-phase
   impulse *and* arrival time. A 3.7 % impulse shift once passed every peak-only
   anchor in this suite.
2. **Pre-register the decision rule, with its numeric threshold, before the run
   that will be judged by it.** This repository was burned once by arguing after
   the numbers came in.
3. **A symmetric average is blind to an antisymmetric defect.** Gauge pairs placed
   to test symmetry must be read individually, never as a mean — a mirror-pair
   mean once cancelled precisely the effect it was written to detect.
4. **Read each arm against its own reference**, never across arms, when the
   treatment is known to move the reference itself.
5. Long runs: `python -u`, no timeout, in the background. Confirm the WSL VM is
   free first — `wsl -d Ubuntu -- pgrep -a blastFoam` must come back empty.
