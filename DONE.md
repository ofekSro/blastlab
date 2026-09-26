> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [docs/SCOPE.md](docs/SCOPE.md)

# DONE — the completed record

Open work is in [TODO.md](TODO.md).

> **§5 (the identifier index) and §7 ("verified correct — do not fix") must not be
> deleted.** Code comments cite them by id. Every identifier line in §5 is carried
> here byte-for-byte from the original; only the surrounding prose was translated.
> The untranslated original is in [docs/archive/DONE.md](docs/archive/DONE.md).

**Where the long-form records live now:**

| Topic | File |
|---|---|
| The PySide6 migration (Q1 / M0–M7) and the Tk decision | [docs/history/ui-migration.md](docs/history/ui-migration.md) |
| The three QA nights and the UX review | [docs/history/qa-nights.md](docs/history/qa-nights.md) |
| The independent audit of the blastFoam defect claims | [docs/verification/blastfoam-claims.md](docs/verification/blastfoam-claims.md) |
| The solver-options review against the official guide | [docs/verification/solver-options-review.md](docs/verification/solver-options-review.md) |
| Physics anchors and every measured number | [docs/verification/physics-anchors.md](docs/verification/physics-anchors.md) |

---

## 0. 2026-09-20/24 — the HD1.3 track

An owner directive of 2026-09-20: compute the effects of an **HD1.3
(non-detonating, deflagrating)** material on a structure. The computational track
was built and tested in two days; **`HD1-3`, the venting in blastFoam, closed on
2026-09-24** (below). What is still open on HD1 is in [TODO.md](TODO.md).

A full assessment runs today via `python -m blastlab --hd13 case.json` — quasi-static
pressure, comparison with the unconfined case, structural response, heat and a
report — with no WSL and no Qt.

**`HD1-1` · the 0D gas-production model** — `core/deflagration.py` +
`tests/test_deflagration.py`. Three states (`Z`, `m`, `E`) with Noble-Abel for the
EOS, Vieille's law with a form function (neutral / degressive / progressive), and
choked-flow-aware discharge through the opening.

The analytic verification passed exactly: a closed vessel converges to
`p_max = λ·C/(V − b·C)` with an error of **0.0000 %** across all nine combinations
(three materials × three sizes), `Z = 1.000000`, `T = T_flame` exactly, and an exact
mass balance `m_end = C`.

> **That verification caught two real integrator bugs**, which is why it is worth
> what it costs:
> 1. The step never grew beyond its initial value, so a slow composite burn was
>    choked off at 2 s of 5 and reported a peak **87 % low** — no error, just a
>    wrong number.
> 2. RK4 overshot past `Z = 1` and the overshoot was clipped, but `m` and `E` had
>    already integrated a `dZ` taken after the burn ended: `m_end` came out
>    `1.00066·C` — **more gas than there was propellant.**
>
> Both are pinned by tests, along with a third: a large opening "drained" the room
> to 0.58 bar against an ambient of 1.01 (a mass step too long; there is no inflow
> in the model).

**`HD1-2` · the propellant table** — `core/fuels.py`. `Propellant` / `PROPELLANTS` /
`form_factor` extracted from `deflagration.py` as a pure move (the existing test ran
**unchanged** — that is the proof the move was neutral). Same pattern as
`solvers/foam/materials.py`, and for the same reason: the table has four consumers
and only one of them is the solver, and the GUI should not import an integrator to
fill a combo box.

Added: `p_valid_min`/`p_valid_max` (the window in which the Vieille pair was
measured), `p_extinction`, and `uncalibrated` — **a flag per field, not per row**,
because they do not become known together: a closed-vessel test fixes `a` and `n`
and says nothing about the extinction threshold.

*Still missing:* `gas_yield`, condensed residue (`Cp_condensed`), `r_atm`,
`secondary_heat`, and five grain geometries instead of three form classes.

**`HD1-2b` · extinction threshold, ignition, and a validity window**

> **A real bug fixed:** `_derivs` computed the rate as `max(p, p_amb)**n`. That
> floor made extinction impossible — a magazine that had vented to ambient kept
> burning forever at the ambient rate and consumed the whole charge, no matter how
> large the opening. The pressure is now raw, and below the threshold the burn stops
> with `stop_reason='extinction'`. With the threshold active, a 0.2 m² opening
> leaves **79 % of the charge unburnt** — a result the previous model could not
> produce.

**Extinction does not exist without ignition:** with the threshold active the burn
cannot light itself, because a seed of a droplet of gas leaves the room at ambient,
which is below the threshold. `ignition_fraction` inverts Noble-Abel in closed form
and takes the ignition gas **from the charge itself**, so the closed-vessel analytic
limit — which is the model's verification — stays intact.

**`p_extinction = 0.0` on every row, and that is a physical decision, not an
omission.** The easy number — ~0.5 MPa for double-base — was measured on a **single
strand** in a strand burner at ambient temperature. A magazine fire is a hot pile
with radiative feedback and sustains far below that; that is why HD1.3 fires exist.
The strand number was tried and gives the obviously false answer that nothing burns:
with a realistic igniter of 1 % of the charge no configuration sustains, and forcing
sustainment needs an "igniter" that burns 95 % of the charge — at which point the
result is an artefact of the seed. The capability is wired and off; enabling it is a
conscious act per scenario. **It is binary for the answer and therefore first in the
sensitivity band.**

A configuration that cannot sustain a burn is reported as
`stop_reason='cannot sustain'` rather than as an exception — *"1 kg in a 2 m³ room
ignites and goes out"* is a useful answer about a magazine.

**`HD1-5` · the load on the structure** — `core/sdof.py` + `tests/test_sdof.py`. No
WSL, no Qt, ~8 s.

> **It turned out not to depend on `HD1-3` at all.** The original plan saw it as
> exporting `p(t)` to an external SDOF/FE tool and therefore blocked on the venting.
> In fact the module is **fully independent**: it takes `(times, p)` — exactly the
> pair `gauge_summary.summarize_trace` takes — so it already works today on any trace
> from an existing detonation run, and on an obstacle face via
> `viz3d.sampling.extract_loads`. That is why it was built first: it is the only
> thing on the HD1 track that delivers value even if everything else stalls on owner
> decisions.

An equivalent SDOF in the style of UFC 3-340-02: `K_LM` from table 3-12,
elastic-perfectly-plastic resistance with elastic unloading (so rebound and permanent
set come out of the same expression), and UFC §3-19's own recursive integration
scheme — **deliberately the procedure from the book**, because the whole value is
that it reproduces the published curves.

**The verification is entirely against closed-form solutions computed inside the test
file, not typed off a graph:** a step load gives `DLF = 2` to **1e-12**; a triangular
pulse over `td/Tn ∈ [0.1, 10]` against the closed form, worst case **1.1e-6**; a
rectangular pulse against `2·sin(π td/Tn)`; the impulsive limit `y = I/(Mω)` to
2.7e-5; and two pressure-impulse diagram asymptotes, which are closed in this
normalisation — `I_bar → √(2μ−1)`, `P_bar → 1 − 1/(2μ)` — to 1.3e-3.

> **Why `DLF = 2` comes out to 1e-12 and not 1e-2, for a structural reason worth
> knowing:** for the UFC scheme the *amplitude* is exact for a step load
> (`y_n = y*(1 − cos ω_num·n·dt)`), and only the frequency is shifted by `O(dt²)`.
> The samples simply miss the peak, so a three-point parabolic interpolation returns
> it almost exactly.

**What the test caught — two wrong claims of mine, not bugs in the module:**

1. *"Equal impulse → opposite ends of the diagram"* — logically wrong: if the
   impulse is equal then `I_bar` is **identical** (2.262741700 in both). The strong
   claim is that at exactly the same `I_bar`, `P_bar` differs by a factor of 3900 and
   the verdicts are opposite.
2. *"A quasi-static load at 0.8·Ru fails because `DLF → 2`"* — **physically wrong.**
   `DLF → 2` belongs to a load applied **suddenly**; a load that rises gradually,
   which is exactly what a confined deflagration does, tends to `DLF → 1`. The model
   returned `μ = 0.859` (`DLF = 1.073`) and that is the right answer. The
   quasi-static danger is not amplification — it is that there is no short duration
   to save the wall the way an impulsive load does.

**HD1's claim as a number, and this is the central test:** the same peak pressure,
`1.1·Ru`, gives `μ = 186.6` when it is quasi-static and `μ = 0.048` when it is
impulsive. At exactly the same impulse, one fails and the other does not. **Neither
the peak alone nor the impulse alone decides the damage — the regime decides**, which
is why substituting "equivalent TNT" for HD1.3 is not merely inaccurate but wrong in
the wrong corner of the diagram.

**`HD1-6` · the ignition scenario** — `core/scenario.py`. `Z` became an array of
cohorts, and the system non-autonomous. **Convolution does not work**: every cohort
burns at a rate set by the room pressure and they all share one room, so a cohort
that lights late burns *faster* than the first one did at the same age. The step lands
exactly on every ignition time, so a cohort never lights **inside** an RK4 step that
would smear precisely the drift the scenario exists for.

> **The effect is larger than any other input in the model** — 5 kg double-base,
> 1 m³, a 0.02 m² opening: uniform **3.99 MPa** · 0.5 s spread **1.43** · 2 s
> **0.31** · 10 s **0.12**. A factor of **32**.
>
> **And the error direction is not the simple one:** uniform *over*-estimates the
> peak, so on a pressure check it looks conservative — but it *under*-estimates the
> **duration**, and HD1-5 showed that duration is what decides whether the wall is in
> the impulsive or the quasi-static regime, i.e. which check even applies.
> **Conservative in the number and wrong in the regime is not conservative.** Every
> run therefore reports `scenario_kind` and `calibration_only_scenario`.

The gate: cohorts that light together **are** uniform ignition. Two reproduce a
single-cohort run to `0.00e+00` — byte for byte, the same step count — and 17 to
`1e-16`. A known limit caught a real bug immediately: `out['burnt_out']` read a
**leaked loop variable** and reported that a run which had finished had not.

**`spread_time` is an input, not a prediction.** Predicting flame spread needs pile
geometry, packing and a radiation field — the code has none of them.

**`HD1-7` · calibration from closed-vessel data** — `core/calibration.py`. **Two traps
in the same class, both implemented and pinned.** The naive reduction on a degressive
grain returns `n = 0.236` instead of `0.80` — and for `n = 0.55` it returns
**`−0.052`, a negative pressure exponent**, i.e. a propellant that burns *slower* when
you squeeze it. That does not exist. The corrected reduction returns all three to
**0.01 %**. Heat correction: adiabatic `0.823` against a truth of `0.85`, convective
`0.850`. The report gives three values of `n`.

**What a closed vessel cannot determine**: it finds `n` and the **ratio** `a/w` only
(pinned: claiming a web 3× larger changes `a` by `3.000000000` and leaves `a/w`
identical).

**`HD1-9` · the unconfined branch** — `core/unconfined.py`, a separate module. `a` and
`n` **do not participate at all** (pinned: changing `a` by 25× and `n` by 4× moves the
answer by less than `1e-12`). The claim "no blast" is **computed**: the Mach number of
the expansion — and the surprise is that it is **conditional**: uniform `0.315`, 10 s
spread `0.159`, 60 s `0.035`, 300 s `0.016`. **"No blast from unconfined 1.3" is not a
property of the material but of the fire being slow.**

**`HD1-8` · heat** — `core/thermal.py`. Two **serial** paths, and a test verifies that
`core/sdof.py` **does not import** the module at all. Secondary burning in air:
`17.5 MJ` against `22.9 MJ` anaerobic.

> **A bug caught by a sanity range:** `M^(1/3)` correlations are calibrated for
> hydrocarbons, and the real variable behind them is energy; feeding them propellant
> mass gave an SEP of `51 kW/m²` against the measured `200–350`. Moving to an
> energy-equivalent mass gives `290 kW/m²` — **a consistency check that passes**, not
> an assumption.

**`HD1-10` · report and curves** — `output/hd13.py` + five curves. The contract is that
**the warning travels with the number**: nine "uncalibrated" labels **beside** the
values, the extrapolation fraction beside the peak, and the ignition scenario always. A
test verifies that a spread run does **not** carry the uniform-ignition warnings — a
warning that always prints is decoration.

**`HD1-11a` · the case model** — `core/assessment.py`. The plan assumed
`DeflagrationCase` and `validate()` existed; they did not, and without them there was
nothing to connect a form to. `dim = 0`, a schema, save/load, and a `validate` that
returns `core.case.ValidationReport` itself. **`overrides`/`measured`** close a gap
against the "generic-parametric" decision: an override without a measurement
declaration stays an estimate and is flagged. It is also the only way to enable the
extinction threshold — until they existed, `sustains()` was unreachable.

**`HD1-11b` · the CLI** — `python -m blastlab --hd13[-new]`. No WSL, no Qt, under a
second.

> **The first end-to-end run exposed a real flaw:** `μ = 1,205,392` and `θ = 89.99°`.
> The mechanics are correct — a quasi-static load above `Ru` never reaches equilibrium
> — but the answer is useless. A support-rotation limit was added (12° by default) and
> the result now says **collapse**, with the time. A light panel collapses after **6.7
> seconds** in the quasi-static regime; that is the HD1.3 story in one number.

**`HD1-11c` · the Qt form (2026-09-21)** — a **0D** dimension in the selector beside
1D/2D/3D. `setup_spec.cards(0)` (8 cards), two-way conversion in `case_form`, and four
edits in `app.py`. **The validation needed no new plumbing** because
`assessment.validate` returns `ValidationReport` itself — that is why that type was
chosen in HD1-11a. **Inline execution**: a 0D case finishes in under a second, and
routing it through `RunController` would add a worker thread, progress, cancel and
resume to buy nothing. The solver switch is **hidden** (not greyed) at dimension 0, via
the long-declared `dim_changed` signal that nobody had connected.

**Units are why a round-trip test exists:** the form speaks kPa, MPa, mm and mm/s
because that is what an engineer writes, and the case is entirely SI. A factor of 1000
in the wrong direction is invisible on screen and fatal in the answer.

**A pinned test was changed, deliberately:** `test_ui_parity` asserted three forms.
Replaced by a reference to the panel's own dictionary. And more importantly — the suite
exists to catch **layout clipping**, and its docstring records that the forms share a
`QStackedWidget` whose minimum is the **widest page**. A new page can clip the others
without anyone looking at it — which is exactly how this form arrived. The parity check
now runs over all four dimensions at 1100×720. All clean.

**`HD1-3` · the venting, in blastFoam — closed 2026-09-24** (moved from TODO.md). What
it gives that nothing else does: the jet leaving the opening, what it does to a
structure outside, and the flow field in the 3D viewer. The pressure *inside* the room
needs no CFD — slow burning mixes well, and 0D is the correct physics there.

**The route changed on 2026-09-21, and the change deleted most of the work.** The plan
put the chamber outside the mesh and drove `p(t)` in at the opening as a time-varying
boundary. The repo has nothing time-varying (no `Function1`, `uniformFixedValue`,
`tableFile`); the guide documents one such condition (`codedFixedValue`, §20.1) and
warns (§5.9) that the boundary builds the conserved quantities, so `p`, `T` and `rho`
would all have to be driven together. **With the room inside the mesh none of it is
needed:** blastFoam computes the blowdown, the 0D model supplies only the state at the
instant the vent opens, and the opening is a hole between wall boxes on the existing
`topoSet` + `subsetMesh -patch obstacles` path. The chamber gas is an inert `type basic`
phase with the `Propellant`'s `gamma`/`molWeight` — not air (γ 1.25 against 1.40, M ≈ 23
against 29). *The fallback, never needed:* `AbelNobel` with `Arrhenius`/`pressureBased`
in `phaseProperties` (the guide lists `AbelNobel` under solid propellants) — neither is
Vieille with a form function, so it would need closed-vessel calibration (`HD1-4`).

| Step | Result |
|---|---|
| `HD1-3-pre` · the chamber's own air in the 0D model | done |
| `HD1-3a` · `core/room.py`, the geometry | an off-grid 5 m room at `dx=0.1` loses **10.5 %** of its cavity and **27.6 %** of its opening to snapping |
| `HD1-3c` · `core/vent.py`, the hand-off and its validity metrics | at burst the room is **`alpha_expl` = 0.115** — nine times more air than product gas; air-vs-products **+17.9 %** on the choked flow |
| `HD1-3b` · `init_mode='chamber'` in the writer | per-phase mass exact to 9 digits; **no `lambda.expl`**, so bug B0 cannot occur |
| `HD1-3d` · the γ-interface stopping point | WSL, 2026-09-21: 0.024 % across a γ step, 0.000 % on uniform mixed cells, against a pre-registered 0.5 % |
| `HD1-3d` · the vent verification | WSL, 2026-09-22 — below |
| `HD1-3d` · the 3D answer | **13/13 PASS**, run 2026-09-23, judged 2026-09-24 — below |
| `HD1-3e` · `core/qd.py` | ships with an empty table: `CRITERIA = {}`, and a row without a `source` is an **error** |
| `HD1-3f` · validation, GUI card, report section | `b33947f` — `build_vent_case` aligns the room and re-runs the 0D at the aligned cavity; the Vent card is in the dim-0 form |

> **Measuring the snapping is not the same as not having it** (owner, 2026-09-21). A
> 27.6 % error in the vent area means the CFD solves a *different hole*, and it would
> have vanished into `Cd`. `room.align` (default on) puts every edge — outer faces, wall
> thickness, vent — onto a base-cell face **before** the boxes are built, so the area
> solved **is** the area reported. The hand-off conserves **mass and energy** and lets
> pressure follow from the EOS; a golden pinning `p == p_0D` would have pinned the bug.

**The vent verification** (`_e2e_vent_verify.py`, WSL, 2026-09-22, every threshold
registered before the run, the 0D comparison at the post-alignment area and volume):
the 0D isentropic orifice law and blastFoam on one opening. **The main result is the
good one** — with the discharge coefficient divided out, the blowdown curves agree to
**2.27 % RMS** of the initial overpressure against a registered 5 %: the lumped model is
right about the *shape*. **The coefficient did not converge:** `Cd_eff` 0.7227 at 6 cells
across the opening (`dx = 0.05`), 0.8102 at 12 (`dx = 0.025`) — **12.1 % apart against a
registered 10 %**, numerical dissipation in the opening; still recorded as a failure of
that check. Owner decisions of 2026-09-22: `Cd` is **not calibrated** (a declared 0.8);
`Cd` is the **fifth band axis, 0.72–0.90** (the coarse floor and a first-order Richardson
ceiling — two points cannot establish an order, so the order is an assumption); and
**≥ 12 cells across the opening** for any run that reports a load, an error in
`assessment.validate` (`room.MIN_VENT_CELLS` = 6 stays the geometry floor).

**`HD1-3d` · the 3D answer — run 2026-09-23, judged post-mortem 2026-09-24: 13/13 PASS.**
`tests/_e2e_vent_3d.py`, run `20260923-195308_3d_p31468-00`: 864,000 cells (841,704
fluid), dx 0.10 m, 12 × 12 × 6 m, 13 ranks; commit `4975705` plus the `n_snapshots`
30 → 6 edit committed in `1c9b238`. A 40 kg double-base magazine behind a burst panel at
3·P_AIR, a wall 4 m out. Hand-off at t_open = 13.115 s: 0.3063 MPa, 647 K, alpha_expl
0.2573; the opening 12 × 12 cells. Target face, from the probes:

| Gauge | Peak kPa | t_peak ms | Arrival ms | +impulse Pa·s | Net impulse Pa·s |
|---|---|---|---|---|---|
| (10, 6, 1.4) | 41.47 | 19.080 | 10.319 | 322.78 | 82.61 |
| (10, 5, 1.4) | 26.75 | 12.905 | 10.709 | 200.52 | −84.48 |
| (10, 6, 2.6) | 24.78 | 14.109 | 10.792 | 172.55 | −59.01 |

All three positive phases close inside the 30 ms window; impulse and arrival carry no
verdict (no threshold was registered for them). From the first trace, not the 0-D
pressure: μ = 0.3027, θ = 0.154°, dynamic — C10, "the 200 mm panel survives", passes. C8
(no boundary return after t_peak + 4 ms): later maximum −21.35 kPa against 41.47. The
run is **one sample** in the band, at Cd ≈ 0.81 (50 % up the axis), and does not close
an undetermined verdict.

> **What the PASS does not establish.** Only the room is meshed, so C10's "survives" was
> judged on the **side-on** pressure at a free-air gauge. It carries no reflection and no
> drag (UFC 3-340-02 para. 2-15.3.2, printed p. 65). The wall load is `HD1-13`, below.

> **Disk: `n_snapshots` does not bound it.** 748 writes, each kept reconstructed
> (~130 MB) and again decomposed: **172.96 GiB** (the 30-snapshot attempt: 191.63 GiB).
> Fixed by `HD1-15`, below.

Judged with **no new solve and nothing written into the run** (size, file count and a
path+size+mtime hash identical before and after), by a `--load` path that reads only
case.json and the probes through the live `read_probes` → `finalize_3d` packing. The
thirteen `check(` calls are unchanged (AST-compared); an independent numpy pass
reproduced G1 to every printed digit.
- Files: `tests/_e2e_vent_3d.py`, `tests/test_vent3d_load.py`, `docs/hd13/vent3d_postmortem.txt`, `vent3d_gauges_3d.txt`
- Tests: `test_vent3d_load.py` 15/15; `_e2e_vent_3d.py --load 20260923-195308_3d_p31468-00` → `VENT 3D: PASS`; 17/17 gates
- Commits: `9b5212f`, `94a56e4`, `3798cec`, `119b59e` · QA: n/a — no GUI change
- Evidence: `docs/hd13/` (`hd13_vent_jet_3d.mp4` is tied to this run by its frame labels; the
  `.html` and the other `.mp4` are owner trials); a sha256-checked 101 MB copy of the dicts,
  logs and probes in `%USERPROFILE%\blastlab_evidence\`; batch `docs/batches/2026-09-24-hd1-3d-close*.md`

**`HD1-13` · the wall load, route (b) — closed 2026-09-24: BOUND.**
- What: from the HD1-3d run's own files, with no new solve, the wall load E(t) = max(the
  front's normal reflection, the compressible stagnation of the flow into the wall) is
  delivered with units, for γ 1.24 and 1.40, in `docs/hd13/vent3d_wall_load_G1.txt` and
  `vent3d_wall_plane.txt`. It is **the load, not a verdict** (owner: each wall has its own
  criterion). At γ 1.24, G1 peaks at **153.67 kPa** (23.815 ms) with ≥ 2030.6 Pa·s positive
  impulse, against the side-on 41.47 kPa and 322.8 Pa·s that C10 used; the plane maximum
  is 155.27 kPa. The rule was registered before any number (`vent3d_wall_rule.txt`,
  `bf8d89d`) and printed `BOUND - P2 and P3 hold and Step 2 is trusted`. E bounds the
  **load** during the 30 ms record, **not an SDOF response**, so run the SDOF on each
  delivered trace and take the worst: the plane-max trace gave the 200 mm example panel
  μ 0.450, against G1's 0.467 (UFC 2° = μ 3.93).
- Files: `core/wallload.py`, `solvers/foam/reader.py`, `tests/test_wallload.py`,
  `tests/_e2e_vent_wall.py`, `tests/test_vent_wall.py`; record `docs/hd13/vent3d_wall_load.txt`
- Tests: `test_wallload.py`, `test_vent_wall.py`, `test_foam_reader.py` PASS; the
  verifier reproduced E with its own parses of the probes and of three plane writes
- Commits: `0e8583a`, `bf8d89d`, `46ca1fe`, `fb017ad`, `53f87ad`, `0703d75`, `9889c54`, `92a52ac`
- QA: n/a — no GUI change

**`HD1-15` · a per-case write budget — done 2026-09-24.**
- What: `write_budget = N` pins `writeInterval` to t_end/N. In parallel, it keeps a
  decomposed copy only of the newest time that is complete on every rank and
  reconstructed. The default 0 changes nothing: no JSON key, `VERSION` 13, goldens
  byte-identical. A real tiny run and a stop-and-resume kept the schedule. The verifier
  caught and fixed two purge defects (`b87f76f`): it could delete a resume's walk-back
  target, and its `rm` could exceed Windows' command-line limit. A run like HD1-3d at
  N = 60 costs ~8 GB instead of ~190 GB. The Qt form does not expose the field yet, and
  drops it on save.
- Files: `core/case.py`, `solvers/foam/writer.py`, `backend.py`, `runloop.py`,
  `tests/test_write_budget.py`, `tests/_e2e_foam_write_budget.py`
- Tests: `test_write_budget.py` and `_e2e_foam_write_budget.py` (WSL) PASS; goldens and
  regression unchanged
- Commits: `6960902`, `5507069`, `a038c16`, `919870e`, `0ac8217`, `b87f76f`, `59d9de8`
- QA: n/a — no GUI screen; final gate 45/45 rc=0

**The decisions that closed on 2026-09-20:**

| Question | Decision |
|---|---|
| Confinement | **Both, for comparison** — hence two declared models, not one model at two `A_vent` values |
| Material | **Generic-parametric** — representative rows marked as ranges, the user enters their own |
| Output | Load **and** heat — which cancels "thermal radiation is out of scope" |
| Calibration | **There is closed-vessel data** — so calibration is an acceptance condition, not a later stage |

The heat decision is the large change: in 1.3 the heat is usually the governing harm,
so a tool that gives only pressure answers the wrong question. blastFoam does not solve
radiation (`radiationModel none`), so this is a **declared empirical/standards path**,
not CFD.

### `HD1-12` · ✅ closed 2026-09-21 — it was the discretisation, not the speed

*(Moved from TODO.md on 2026-09-26, unchanged.)*

Opened as "the 0-D model is too slow at the cohort count it needs", with
vectorising the Cash-Karp loop as the proposed fix. **The owner proposed the
better one: ramp the ignition across each cohort's interval instead of lighting
it in an instant.** That was right, and it removed the need for the speed work
entirely.

| `n` | staircase | ramp |
|---|---|---|
| 10 | 2.84 | **1.0223** |
| 20 | 1.57 | 1.0101 |
| 40 | 1.19 | 1.0054 |
| 160 | 1.040 | 1.0028 |

`n = 10` now lands within 2 % of converged, where the staircase was **still 1.2 %
out at n = 160**. So the converged answer was never 1.04 either — a realistic
magazine reaches **1.003× ambient**.

**And the mechanism is not the one that sounds right.** The ramp is *not* higher
order: measured, its entrainment error still falls as 1/n, the same as the
staircase, because the cohort edges sit at `T(i/n)^(1/d)` and the first interval
is `T/√n` wide. What it buys is **continuity** — the staircase jumps by a full
`1/n` at every edge and each jump shock-loads the chamber, while a slope does
not. Two wrong explanations were written into the code before that one, and
`test_deflagration.py` caught both; the measured sequences are pinned there.

Vectorising is no longer needed for correctness. Left undone.

---

## 0a. 2026-09-25/26 — the engineering-questions review

The owner went through every open question in `docs/ENGINEERING_QUESTIONS.md` (the
`/todo` batches of 09-24 and `/refactor` phases 0-8) in order of urgency. Each
decision is noted under its question there, and the work is in TODO.md: `P0-5`,
`HD1-16`, `HD1-17`, `P1-7` (side chosen), `P1-8` … `P1-16`, `P2-13`, `P2-14`,
`P2-15`. Decisions of note:
- **No SDOF in the app** (`HD1-16`). blastlab delivers the wall load as CSV, and the
  structural response is solved in SBEDS. Only what was computed is exported, with no
  tail rule.
- **Every material row must be 100 % sourced** (`P1-14`). RDX and ANFO are owner-gated.
- The settings file moves into the repo (`P0-5`). The write interval becomes a user
  input with a disk estimate (`P1-12`).

**Done in the session itself (the rest is open in TODO.md):**
- *Stop-gap for `P0-5`:* `auto_cleanup` set to `false` in the virtualised settings
  file the app actually reads
  (`%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\Roaming\blastlab\settings.json`),
  which a GUI start had rewritten on 2026-09-25 10:22 with cleanup on.
- *The primary source for the JWL table* was found and read. It is Dobratz & Crawford,
  LLNL Explosives Handbook, UCRL-52997 (1985), Table 8-7 (pp. 8-22/8-23), from the
  Internet Archive, read off the page images. It is registered as
  `llnl-explosives-handbook` in `docs/references/INDEX.md`, with the two table pages as
  PNGs. The row-by-row comparison is in TODO `P1-14`: TNT matches, C4 `e0` is
  1.1 % low, HMX and PETN differ, and RDX and ANFO are not in the handbook.

---

## 0b. 2026-09-26 — batch `hd1-16-load-export` (HD1-16 step 1, HD1-17(a))

Plan and reports are in `docs/batches/2026-09-26-hd1-16-load-export{,.implement,.verify}.md`,
QA is in `docs/qa/2026-09-26-hd1-16/QA_REPORT.md`, and the UX review is in `docs/UX_REVIEW.md` §"2026-09-26 ·
hd1-16-load-export". Owner decisions of 2026-09-26, taken during planning:
- The SBEDS file is **two columns, t [ms] and overpressure [kPa], with no header and nothing else**, and suction is kept.
- Metadata goes in a sidecar `.txt`.
- Clearing is a user choice, taking the wall's H and W.
- Residual capacity stays.
- No Tk HD 1.3 form.

### `HD1-16` step 1 · No SDOF in the app — the load goes to SBEDS as CSV

- **What:**
  - `output/load_csv.py` writes every computed chamber trace (the nominal and every band run) to `<report>_loads/` as SBEDS CSVs with sidecars.
  - The "record ends while the load is still active" rule is 1 % of peak over the last 1 ms. It goes to the sidecar, the CLI, the Qt status line (as a warning) and the Run log.
  - `--hd13-wall-export` exports the HD1-13 traces (G1 and plane-max, γ 1.24 and 1.40) from `docs/hd13/`. With optional clearing on G1 only, it applies UFC 3-340-02 §2-15.3.2 Eq. 2-8 / 2-9. C_r comes from Rankine-Hugoniot, which is within 1.09 % of Fig. 2-192 at 15 points.
  - μ, support rotation and the verdict are gone from the report, CLI and Qt. The Structure card is hidden, and its keys pass through. `core/sdof.py` stays until step 2.
- **Files:**
  - `__main__.py`
  - `core/`: `assessment`, `sensitivity` (the `'traces'` key), `thermal`, `unconfined`, `wallload` (new functions only)
  - `models/`: `fields`, `hd13_case`
  - `output/`: `cli_hd13`, `hd13`, `load_csv` (new)
  - `services/hd13`
  - `ui/`: `app`, `case_form`, `setup_spec`
  - New tests `test_load_csv.py` and `test_wall_clearing.py`, with 7 goldens re-pinned, one commit each.
- **Tests:** `test_regression` byte-identical. The HD1 matrix, Qt and Tk suites and the real-window `_e2e_hd13_gui.py` (31/31) all PASS at 50ad65b.
- **Commits:**
  - implementation: `7c681ca`, `385047b`, `13648b0`, `a11cf27`, `a9a9309`, `9a7e80e`, `ab5a7ae`, `f1cb45b`, `e339a38`, `2d65b8f`, `1fe4a1f`, `4a3e712`
  - verify fix: `95a62ce` (stale `_cleared` files)
  - simplify: `a3b3c7b`
  - QA fix: `1b7817d`, `50ad65b`
- **QA:** first pass 16 PASS / 3 FAIL. F2 (the status line was clipped and never logged) was caused by this batch; it was fixed and re-run with 5/5 PASS. F1 existed before the batch and is now `P1-18`.

### `HD1-17(a)` · The HD 1.3 texts that overstate

- **What:**
  - The `MACH_QUASI_STATIC` comment now states what was seen: the starter case reaches Mach 0.092, 1.8× the threshold. The threshold stays 0.05.
  - The CLI Mach line says "(upper bound)".
  - The docstrings give the ~20 min band-on time.
- **Files:** `core/unconfined.py`, `output/cli_hd13.py`, `ui/app.py`, golden `hd13_cli.json`.
- **Tests:** `test_unconfined` and `test_char_hd13` are unchanged. The CLI golden diff is one line.
- **Commits:** `658fb4c`, `5e0752d`.
- **QA:** n/a (text only).

*(Not part of the batch, though on the same branch: `a9c49ca` (P1-14, RDX removed) and `d2f5cb1` (the OUT track docs), from other sessions.)*

---

## 0c. 2026-09-26 — batch `out-1-model-folder` (OUT-1)

Plan: `docs/batches/2026-09-26-out-1-model-folder.md`, specification
`docs/model-folder-and-vtk-plan.md` §2. Owner answers of 2026-09-26: Q1 the output
file-name boxes hidden, the .gif/.mp4 choice kept; Q2 the native `--cli` keeps its
legacy prompts; Q3 export dialogs start in the model folder; Q4 only a folder blastlab
created (or an empty one) is ever overwritten; the foam CLI reaches the model-folder
writer through the `jobs` registration hook.

### `OUT-1` · The model folder

- **What:**
  - No run starts without a **Runs folder** and a **Model** name (Qt and Tk Run tabs,
    Initialise Model, resume, Chain, HD 1.3, `--cli` / `--hd13` / `--hd13-wall-export`).
    A refusal names its box; nothing is written before it.
  - Everything a run produces lands in `<runs>\<MODEL>\`: `MODEL.json`, `run.log`,
    `manifest.json`, gauges, figures, fields, report, animation, profile, and for
    blastFoam `foam\` with `SHA256SUMS`. The WSL scratch is deleted only after a
    finished run's rows and hashes verify; a failed or stopped run keeps it, and the
    manifest says why.
  - Overwrite asks first, and only for a folder holding the `.blastlab-model` marker
    or an empty one. The Desktop (or a model folder holding it) is refused.
  - Chain: `<MODEL>\1d`, `2d`, `3d`, hand-offs and a root manifest at the model root;
    the workspace box is gone. HD 1.3: `hd13_report.html`, `hd13_loads\`, `MODEL.json`
    (replacing the leaked temp case file); `--report` is gone.
  - The stage writer is `services/model_folder.stage_solve`, registered with
    `solvers/jobs` (solvers never import services); its outcome reaches the GUIs in a
    `('folder', …)` queue message.
  - Found on the way: the Tk resume never started its worker. Fixed with the rest.
- **Files:** `services/model_folder.py` (new), `services/{exports,hd13}.py`,
  `solvers/{jobs,hooks,worker}.py`, `solvers/foam/{backend,cli_run}.py`,
  `models/fields.py`, `output/{cli_hd13,load_csv,animation}.py`, `core/settings.py`,
  `cli.py`, `__main__.py`, `ui/{app,run_panel,run_controller,chain_panel,exports,
  fieldform,setup_spec,testing}.py`, `gui/{app,run_panel,chain_panel,forms,
  results_panel}.py`.
- **Tests:** new `test_model_folder.py` (A–D), `test_run_preflight.py` (Qt, CLI, Tk),
  `_e2e_model_folder.py` (WSL: OK / KILLED / STOP, 26/26); `_qa_ui_harness.py` M01–M05
  and `_qa_gui_harness.py` M01–M04 new, G01–G03 rewritten. D10 setup edits and golden
  re-pins each in their own commit, no number moved. `test_regression` byte-identical.
- **Commits:** Steps 1–4 `30f3e04` `313f087` `90c7419` `8a29628`, verify `b409af6`
  `2ea3948` `2ce2c0b`; 4b `649b911`; 5 `ce603b9` `3d02565` `83f6cb6`; 6 `b7703b4`
  `ccb3999`; 7 `0aa1f85` `9e125cf` `a59bced`; 8 `889d47f`; 9 `4d3b39f` `abf051c`;
  10 `3b16825`; 11 the commit of this entry.
- **Real runs (2026-09-26):** `_e2e_model_folder.py` 26/26, `_e2e_ui_resume_foam.py`
  21/21, `_e2e_hd13_gui.py` PASS, harness M/G scenarios without a finding (Qt
  offscreen + real window, Tk). `_e2e_ui_chain_foam.py` / `_e2e_gui_chain_foam.py`:
  1D and 2D stages as specified (folders, root hand-offs, verified copies, scratches
  released); the 3D stage was still solving at each script's own limit (30 / 40
  min). It needs ~55 min here, and a 240 s A/B showed the model-folder path solving
  at the plain path's rate (ratio 1.004), so the limit, not `OUT-1`, is short.
- **QA:** `gui-qa-tester` screenshots pending (not run by the implementer).

---

## 0d. 2026-09-27 — batch `out-2-vtk-output` (OUT-2)

Plan: `docs/batches/2026-09-27-out-2-vtk-output.md` (§0a D1–D15, owner answers Q1–Q7,
parked P1–P13), specification `docs/model-folder-and-vtk-plan.md` §3.

### `OUT-2` · VTK output for ParaView

- **What:** the Setup card **VTK output (ParaView)** in both GUIs (blastFoam only;
  families per dimension, Time [ms] / Step with the other box greyed, 3D extra planes,
  a quantity matrix with a locked Gauge column and separate Sections / Obstacles /
  Volumes columns, Q2); case keys `vtk_surfaces` / `vtk_volumes`, omitted while off;
  validation of every refusal in §3.3; the writer's `vtkTimeSeries` surface function
  objects (never alter dt) and the volumes write cadence; `VtkExport` in the run loop
  (async foamToVTK, copy + size check, `.vtk.series` + `vtk\manifest.json`, then the
  WSL delete that the pure `vtk_purge_plan` allows); the backend protects every write
  finalize re-reads (D1). Layout `<MODEL>\vtk\volumes|sections\<plane>\<field>|
  obstacles\<field>`, one series per field (Q1).
- **Tests:** new `test_vtk_case`, `test_vtk_export_plan`, `test_vtk_series`,
  `test_vtk_protect`, `test_ui_output_card`, `test_gui_output_card`; `test_foam_writer`
  and `test_model_folder` additions; harness group V (Qt V01–V05, Tk V01–V04);
  `_e2e_vtk_3d.py` (WSL, rules pre-registered in `6328bbd`). Goldens: only the two
  char case-form re-pins, added rows only. `test_regression` byte-identical.
- **Real run (2026-09-27):** `_e2e_vtk_3d.py` 36/38. Surfaces alone and deletion vs
  none are byte-identical; counts, series, the protected set on 331 passes, the
  release and a stopped run all pass. Rule 3 (volumes vs no export) fails at a
  Z ≈ 0.07 gauge: peak +4.2 %, impulse +4.8 %, against a 1 % limit. A write budget
  of 10 without export reproduces the export run byte for byte, so the cause is the
  write schedule's dt clipping. Parked as P14. `_e2e_model_folder.py` 26/26.
- **Commits:** Steps 1–7 and their verification up to `06c272b`; 8 `d0c4a57` `87ff5da`;
  9 `3d1feae` `c675829`; 10 `96bcff3`; 11 `6328bbd` `7382e6a`; 12 `8557bf2`; 13 the
  commit of this entry.
- **Open:** owner acceptance in ParaView (Step 14); `gui-qa-tester` pass (the
  implementer took real-window screenshots, `docs/qa/2026-09-27-out-2/`).

---

## 1. The timeline — T0–T70

**71 tasks, all closed.** T0–T24 through 2026-09-05, T25–T48 on 09-07 (the QA round and
closing the roadmap), T46–T61 on 09-08, T62–T70 on 09-09.

| # | Task | Ids | Size | Completed |
|---|------|-----|--------|--------|
| T0 | Commit untracked work | A9 | 10 min | 2026-09-02 |
| T1 | Harden the foam stop/ingest path | B1, B2, B15 | S–M | ✔ |
| T2 | Wrong-data display: 3D replay slice + viewer final frame + thinning | B3, B4, B20 | S | ✔ |
| T3 | Units & labels: kPa everywhere, impulse naming | B8, B9 | S | ✔ |
| T4 | Runs-dir safety: unique dirs, live-run guard, orphan reaping | B13, B14 | S | ✔ |
| T5 | Papercuts bundle | B7, G1, B22, G6a | S | ✔ |
| T6 | Chain validation + visible/stoppable foam preflight | B5, B6, G5 | M | ✔ |
| T7 | Native solver warnings through hooks | B11 | M | ✔ |
| T8 | Native fixes with ONE re-baseline | B10, B12, B18 | S | ✔ |
| T9 | Extract the shared foam run loop | A1, A2, A3, A4(foam) | M | ✔ |
| T10 | Foam accumulator correctness | B16, B17, B21 | S–M | ✔ |
| T11 | Peak-overpressure / impulse views in Results | N1 | M | ✔ |
| T12 | Per-gauge engineering summary + CSV | N2, B9 | S–M | ✔ |
| T13 | 3D viewer colour-range plumbing + viz3d dead code | B19, A4(viz), A8 | S | ✔ |
| T14 | Foam run browser + auto-cleanup | N8 | M | ✔ |
| T15 | VTK/ParaView export | N4 | S | ✔ |
| T16 | Afterburn model | N3 | M | ✔ |
| T17–T19 | Local (static) refinement: core → foam → 3D viewer | N15 | M–L | ✔ |
| T20–T24 | Dynamic AMR: core → ingest → GUI → 3D viewer → live slice/wedge fix | N16, B25 | M–L | 2026-09-05 |
| T25 | QA S1: validation/preview memory safety, defaults, finite input | QA-01..04, 14, 15; B27, G10 | M | 2026-09-07 |
| T26 | QA S1: chain feed3d lifecycle + profile-stage validation | QA-05, 06; B26 | S | 2026-09-07 |
| T27 | QA: layout — Run-tab 3D viewport, status card height, truncations | QA-17, 25, 27; G11 | S–M | 2026-09-07 |
| T28 | QA: chain feedback (stage select, workspace, stage prefix) | QA-23; G12 | S | 2026-09-07 |
| T29 | QA: validation & feedback bundle | G3, QA-16, 22 | M | 2026-09-07 |
| T30 | QA: user-named runs + loaded-run replay | N9, QA-24; G2 | S–M | 2026-09-07 |
| T31 | QA: UI stalls + preview extras + viewer field availability | G4, G8, QA-18, 21, 17 | M | 2026-09-07 |
| T32 | QA: theme/affordance + accelerators + persistence | G9, G13, QA-19, 28, 29 | S–M | 2026-09-07 |
| T33 | QA: papercuts | QA-20, 26, 30..35 | S | 2026-09-07 |
| T34 | GUI: global solver mode (sidebar selector; hide, don't grey) | — | L | 2026-09-07 |
| T35 | `test_foam_parallel` determinism check | B23 | S | 2026-09-07 |
| T36 | Mass/energy-conserving resolved-charge init in 2D/3D | B24 | S | 2026-09-07 |
| T37 | Hardening bundle: dead code, shared constants, stdout canaries | A4, A5, A6, A7 | S | 2026-09-07 |
| T38 | Live-view niceties: foam cadence hint, 2D live Min/Max | G7 | S | 2026-09-07 |
| T39 | Charge-mass rasterisation deficit (foam) | N5 | S–M | 2026-09-07 |
| T40 | Arrival-time characterisation: AMR probe cell + foam near-field lag | N16-a, W1 | M | 2026-09-07 |
| T41 | Chains INTO blastFoam (profile-initialised foam stages) | N7 | M–L | 2026-09-07 |
| T48 | Hardware-aware run plan: cores + RAM → MPI ranks and a cell cap | N17 | S–M | 2026-09-07 |
| T42 | Parallel AMR (direct `processor*/` reads) | N16-b | M | 2026-09-07 |
| T43 | Resume a stopped foam run | N6 | M | 2026-09-07 |
| T44 | Gauge fields beyond p (foam) | N12 | S–M | 2026-09-07 |
| T45 | CSV export of field maps + one-click HTML report | N14, N13 | M | 2026-09-07 |
| T46 | Materials beyond TNT for the native solvers | N11 | M | 2026-09-08 |
| T47 | MUSCL second-order native reconstruction (opt-in) | N10 | L | 2026-09-08 |
| T49 | Mesh overlay on the animation a run writes | N15 | S | 2026-09-08 |
| T50 | Boundary kinds: transmit / reflect / terminate | N18 | M | 2026-09-08 |
| T51 | Trigger gauge: terminate and/or remap on arrival | N19 | M | 2026-09-08 |
| T52 | An end time for 1D and 2D runs too | N18 | S | 2026-09-08 |
| T53 | Gauges drawn in the live view and the animation | N19 | S | 2026-09-08 |
| T54 | AMR mesh in the exported video | N15 | S | 2026-09-08 |
| T55 | Bound the replay-frame record's memory | N15 | S | 2026-09-08 |
| T56 | MP4 export reachable (label, dialog, default, ffmpeg) | N15 | S | 2026-09-08 |
| T57 | Loading a PARALLEL AMR run (post-mortem) | N16-b | S | 2026-09-08 |
| T58 | A title line of your own on the Results figures | N20 | S | 2026-09-08 |
| T59 | 1D model preview: the spherical sector | N20 | S | 2026-09-08 |
| T60 | A boundary kind for the end of the 1D sector | N18 | S | 2026-09-08 |
| T61 | The 1D live pane was pinned to 10 kPa | G14 | S | 2026-09-08 |
| T62 | A 1D→3D remap could never run on blastFoam | N7 | S | 2026-09-09 |
| T63 | The trigger gauge leaves 1D (both solvers) | N19 | S | 2026-09-09 |
| T64 | Hardware honesty: per-field measured/cached/unknown, /proc/meminfo, no sticky cache | N21 | S–M | 2026-09-09 |
| T65 | Unknown hardware tightens the caps instead of loosening them | N21 | S | 2026-09-09 |
| T66 | Machine fingerprint + TTL for persisted hardware; settings write bugs | N21 | S–M | 2026-09-09 |
| T67 | Native cell caps from the Windows host's RAM (ctypes) | N21 | M | 2026-09-09 |
| T68 | An explicit `n_procs` is a ceiling, not a command | N21 | S | 2026-09-09 |
| T69 | Frame budgets derived from host RAM; cores beat MAX_AUTO_PROCS | N21 | S | 2026-09-09 |
| T70 | Dynamic AMR for profile-initialised stages | N7, N16 | S–M | 2026-09-09 |
| T71 | The heavy-run night of 2026-09-09/10 and the fixes it produced | P5 | L | 2026-09-10 |

**Dependencies that were live at the time** (for the record): T27–T33 were independent
of each other and came before T34 (which re-laid out the GUI); T35 before any task that
runs `test_foam_parallel`; T40 before T42; T48 before T42.

---

## 2. T0–T26 — the foundation, the fixes and the first capabilities

Full briefs for T0–T26 live in git history (`git show 73ca834:ROADMAP.md`, and commits
`ba37a65`, `73ca834`, `3cb800c`, `a6c7463`). What was done, by group:

**Bugs on the foam path (T1, T2, T10).** Closed: a truncated `uniform` internalField
that raised `AttributeError`; a stop that escalated to a kill and broke finalize; an
unhandled `TimeoutExpired` in the stop paths; a 3D replay that hard-coded the x-z plane;
the final frame vanishing from playback; FrameStore thinning; out-of-order ingest; stale
peak/impulse from the function object; stop distances in a multi-charge case.

**Run-directory safety and hygiene (T4).** Unique run names, a guard against deleting a
live run, orphan reaping.

**Units and labels (T3).** kPa everywhere, and net impulse separated from positive-phase
impulse.

**Native solvers (T7, T8).** Warnings routed through hooks instead of stdout; a
duplicated last gauge row; 1D snapshot scheduling; grids that silently shrank by one
cell. **One re-baseline**, batched.

**Architecture (T9, T13).** The foam run loop, which existed in triplicate, was unified;
geometry logic, which existed in quadruplicate, became `core/geometry.py`; private
imports in postmortem; colour-range plumbing in the 3D viewer; dead code in viz3d;
control-message delivery in viz3d.

**Capabilities (T11–T16).** Peak-pressure and impulse maps in Results; a per-gauge
engineering summary + CSV; a foam run browser with automatic cleanup; VTK/ParaView
export; the afterburn model (`none | miller`).

**Static refinement (T17–T19)** and **dynamic AMR (T20–T24)** — `adaptiveFvMesh`,
`densityGradient` as the then-default estimator, AMR and static zones being mutually
exclusive, the display level bounding the display grid, serial in v1. An unbounded 3D AMR
case once killed the 4 GB VM — the 3D e2e is capped at 300k cells.

**T25–T26 (QA S1).** Memory safety in validation and preview, defaults that pass
validation, non-finite input rejected, the feed3d lifecycle in a chain, and validation for
a profile stage. Detail in §6.

---

## 3. T27–T71 — the detail

### T27–T33 · the QA round's fixes (2026-09-07)

**T27 — layout.** The Run tab parks the ttk sash after the first real layout; the status
card is height-bounded and scrolls; truncated headings fixed.
**T28 — chain feedback:** stage selection, the workspace, the stage prefix.
**T29 — validation and feedback bundle** (G3): no more split-brain validation or silent
swallowing; file-open errors say what happened.
**T30 — user-named runs** and replay for a loaded run.
**T31 — UI stalls, preview extras, viewer field availability.** `feed_result`
**2364 ms → 259 ms**; a preview cache; the worst gap in a native 3D run 3544 → 1100 ms.
**T32 — theme/affordance, accelerators, persistence.**
**T33 — papercuts** (QA-20, 26, 30…35).

### T34 — a global solver mode

One app-wide native | blastFoam switch in the sidebar. Every tab re-lays itself out for
the chosen mode and **hides — never greys — the controls that do not apply.** Hidden
values stay in the form but are not written to the case.

### T35 — determinism in `test_foam_parallel` (B23) · owner decision

### T36 — mass/energy-conserving charge initialisation in 2D/3D (B24)

Energy exact to 4e-16; clipped volumes verified to 2e-16 against closed forms and 1.7e-6
against a 1200³ brute-force count. Mass keeps the staircase deficit by design.

### T37 — the hardening bundle (A4, A5, A6, A7)

Dead code removed; guard-rail constants that had been duplicated as literals shared;
a canary on the `Time =` regex; `_decode_surface` no longer degrades silently.

### T38 — live-view refinements (G7)

### T39 — the charge-mass rasterisation deficit (N5)

`constants.FOAM_EXP_CELLS = 8` now drives every blastFoam charge target (1D/2D/3D global
refine, the automatic zone level, the AMR level check, the validation notes) through
`refine.exp_cells(case)`; **native keeps `MIN_EXP_CELLS = 5` and test_regression stays
byte-identical**. `refine.set_mass_fraction` predicts what `sphericalMassToCell` will
deposit; `validate_case` reports "Charge cells: N at dx → ~F of the M kg set by
blastFoam"; `backend._scan_set_mass` forwards blastFoam's own line as a `[note]`.

> **The original "~0.85 of requested mass" premise did not reproduce.** Measured against
> blastFoam's own set-volume line the deposit is 0.979 (3D, 5 cells) / 1.027 (3D, 8
> cells) / 0.995 (1D, both). Over 400 random burst offsets 8 cells mainly cuts the
> SPREAD — 3D RMS 1.00 % → 0.41 %, axisym 3.67 % → 2.95 % — for 1.6×/2.6×/4.1× the cells
> in 1D/2D/3D. **The real gain is the resolved detonation:** KB anchor 0.72–0.77 →
> 0.85–0.89; foam-vs-native arrival gap 13.7/7.3/5.5/3.8 % → 4.5/1.5/1.3/0.7 %.

### T40 — arrival-time characterisation: the AMR probe cell (N16-a) + near-field lag (W1)

Both studies run; **the `adjustLocations` hypothesis is REFUTED** — switching it off moves
the AMR-vs-static arrival by 0.15 percentage points (blastProbes reports the containing
cell's value either way), so the default stays `yes`. The +18 % is a real resolution
difference at the gauge: the AMR mesh follows the shock and is at its finest level there,
while the static `zone` reference refines only around the charge. Measured with
`_e2e_foam_probe_study.py`: +4.2 % at a cell corner, −11.5 % at a base-cell centre, point
peaks 57–171 % apart.

**W1 characterised:** foam lags native +36.7 % / +23.6 % at r = 0.6 / 1.0 m with the
default `linear` activation and +23.1 % / +12.8 % with `none` — roughly half the lag is
the activation model burning the charge at vDet, the rest is the resolved charge's
expansion. `none` overshoots the peaks (1.43× / 1.36× native), so **`linear` stays the
default** and the tolerances stay as they are.

### T41 — chains INTO blastFoam (N7)

A blastFoam stage can start from a 1D or 2D profile. `writer.profile_state` runs the SAME
remap the native solvers use onto the case grid, and `_profile_fields` emits p, T, U,
`alpha.expl`, `rho.expl`, `rho.air` as `nonuniform List<scalar|vector>` internalFields in
the mesh's cell order (`ravel(order='F')`, fluid cells only on a carved mesh — the exact
inverse of `reader.to_grid`). The two-phase split is sharp (alpha is 0 or 1), which makes
the mass transfer exact.

> **The one physical clock:** the state is emitted into a time directory named for the
> profile's t0 and picked up with `startFrom latestTime` — **without that the chained
> gauges read 53 %/34 % early.** Measured against the same domain initialised directly
> from the charge: arrivals +2.31 %/+3.36 %, peaks +4.87 %/+3.37 %; emitted mass/energy
> match the profile to 1e-11.

### T42 — parallel AMR: direct `processor*/` reads (N16-b)

The ingest reads `processor*/` directly and concatenates per rank (cell-for-cell identical
to the serial read, unit-pinned); `maybe_reconstruct` skips decomposed runs.
**340 s → 237 s (1.43×) at np=2.**

Serial-vs-parallel AMR are two self-consistent discretisations: arrivals agree 0.3–0.5 %,
point peaks fluctuate 0.15–4 %, impulse drifts 4–9 % late. **Acceptance (owner
decision):** per-gauge arrival ≤ 1 % and loading-region peak-map median ≤ 1 %
(**0.605 % measured**), point values characterised ungated. `balance no` stays the
default; revisit balancing only for asymmetric refinement or 4+ ranks.

### T43 — resuming a stopped foam run (N6)

`backend.resume_run(case_dir, hooks)` rebuilds the spec the way postmortem does, refuses a
run whose solver is still alive (or whose state WSL cannot report), resets the
`stopAt writeNow` a stop left in the controlDict, flips `startFrom → latestTime`, and
re-enters the ORDINARY `solve_Xd_foam` with that spec. **No other special-casing was
needed** — the shared run loop's ingest is disk-driven and ordered, so it first replays the
times the stopped run wrote and then follows the new writes. Prefix-identical gauges, peak
map within 0.5 %, a Resume button in the run browser.

### T44 — gauge fields beyond p (N12, foam only)

`read_probes` attaches `speeds` and `rhos` **ONLY when their rows align sample-for-sample
with p's** — a torn or missing extra degrades to p-only rather than ever misaligning
(pinned by a torn-U fixture test). **Native stays p-only and byte-pinned.**

### T45 — CSV export of field maps (N14) + a one-click HTML report (N13)

`blastlab/output/report.py`, pure writers shared by two Results-tab buttons. The HTML
report is one self-contained file: banner, gauge table, inlined PNGs, the case JSON, and
the KB free-air comparison when applicable.

### T46 — materials beyond TNT for the native solvers (N11)

`eos.material_jwl(name)` — **'TNT' returns the byte-pinned `constants.JWL_TNT` OBJECT
itself**, everything else comes from the shared materials table as a dict with the same
keys. **test_regression is byte-identical, which is the whole point of the TNT-object fast
path.** C4 1D peak ×1.24 over TNT.

### T47 — second-order MUSCL reconstruction, opt-in (N10)

Opt-in via `case.order == 2` (default 1; **test_regression stays byte-identical**).
**r = 1.5 m: 0.75 → 0.90 of KB; anchor sweep 0.74–0.81 → 0.85–0.89; with order 2 the
foam/native peak ratios collapse to 0.97–1.01.**

### T48 — a hardware-aware run plan (N17)

`env.plan_run(...)` is a pure function returning `RunPlan(...)`. **`hardware()` returns
cached values only — it is called on every keystroke by `validate_case` and must never
touch WSL.** An 11-row pinned decision table and a 432-case invariant sweep.

**Measured `BYTES_PER_CELL = 2650`**; headroom 1 (was an unjustified 2),
`CELLS_PER_RANK = 50_000`, `RAM_GB_PER_RANK = 2`, caps at 0.70/0.35 of VM RAM.

### T49 — a mesh overlay on the animation a run writes (N15)

New case field `anim_mesh` (file version 5 → 6). **No solver code touched.**

### T50–T54 — boundary kinds, end time, trigger gauge, gauge markers (N18, N19)

**Why (owner request):** `open` did two jobs at once — it was the transmissive ghost-copy
AND it ended the run the moment `p > 1.001·P_air` reached it. There was no way to let a
wave leave and keep solving.

**T50 — the vocabulary.** `core/bc.py` owns
`BC_KINDS = (transmit, reflect, terminate)`, `BC_LEGACY = {open: transmit, wall: reflect}`
and `normalize_bc(s)`, which every reader goes through, so pre-T50 case files still load
(with one `[note]` naming the mapping — a silent `open → transmit` would quietly drop a
run's stop condition). Two different questions are asked of `bcs` and they no longer have
the same answer: `geometry.terminate_edge_mask` feeds the stop condition and counts ONLY
terminate sides, while `stop_dists_2d/3d` size the snapshot radii off EVERY non-reflecting
side. `_patch_type` / `_bc_entry` map the new kinds onto the SAME OpenFOAM patch types, so
the writer goldens are byte-identical.

> **Owner decision, and its cost:** legacy `open` maps to `transmit` and the shipped
> defaults are `transmit`, so a default run is no longer ended by the wave leaving — it
> runs to the safety cap or `t_end`. **That is up to ~10× more solver time, worst on
> blastFoam.** Mitigations in the same commit: `validate_case` warns when a case has no
> terminate side and no end time (naming the cap in ms), the run banner says
> `safety cap (no terminate boundaries)`, and T52 gives every dimension an end time.

**T51 — the trigger gauge.** `trigger_gauge` (1-based, None = off), `trigger_action`
(`terminate` | `remap` | `remap+terminate`) and `trigger_file`. The check sits in the
gauge-sampling block each solver already had, so it costs one comparison per step and fires
once. 3D is terminate-only — there is no 3D remap format.
> **A bug found by the owner mid-task:** a stopped blastFoam run died with
> `NameError: name 'trig_k' is not defined` — the trigger is armed inside
> `solve_2d/3d_foam` but the meta is assembled in `finalize_2d/3d`, also called by
> `postmortem.load_run`, which never watched the run. Both now take `trig_k`/`trigger` as
> keyword arguments defaulting to None.

**T52 — end time.** `t_end` on `Case1D`/`Case2D`. Deliberately transcript-neutral at
`t_end = 0`. Precedence: whichever comes first — a terminate boundary, the trigger gauge,
or the end time.
**T53 — gauge markers.** A ringed dot plus `G<n>` per gauge, the trigger gauge heavier and
starred. 3D keeps only the gauges the plotted plane actually cuts.
**T54 — AMR in the exported video**, the real defect, found by the owner.

### T55–T61 — the 2026-09-08 bundle

**T55** bounds the replay record's memory (**614 MB → 199 MB**). **T56** makes MP4 export
reachable. **T57** loads a parallel AMR run post-mortem. **T58** a title line of your own on
the Results figures. **T59** the 1D model preview — the spherical sector. **T60** a boundary
kind for the end of the 1D sector. **T61** the 1D live pane had been pinned to 10 kPa (G14).

### T62 — a 1D→3D remap could never run on blastFoam (N7)

### T63 — the trigger gauge leaves 1D (N19) · owner decision

### T64–T69 — a robust cross-machine hardware model (N21)

Honest per-field sources (measured / cached / unknown); unknown hardware **tightens** the
caps instead of loosening them; a machine fingerprint + TTL for persisted hardware; native
cell caps derived from the Windows host's RAM via ctypes; an explicit `n_procs` is a
**ceiling, not a command**; frame budgets derived from host RAM.

### T70 — dynamic AMR for a profile-initialised stage (N7 + N16) · owner request

### T71 — the heavy-run night of 2026-09-09/10, and the fixes it produced

Full record: [docs/history/qa-nights.md](docs/history/qa-nights.md). The four commits that
landed from it: `c2b661a`, `4e8c075`, `c66eae8`, `b368046`.

---

## 4. The measured numbers

**Moved to [docs/verification/physics-anchors.md](docs/verification/physics-anchors.md)**,
which is now the single place for them. The headline figures:

- **Native vs blastFoam:** foam peaks 1.10–1.16× native at r = 1–4 m, arrivals within
  0.7–4.5 %. With MUSCL order 2 the ratios collapse to **0.97–1.01**.
- **Kingery-Bulmash anchor:** 0.72–0.77 before T39 → **0.85–0.89** with the 8-cell charge →
  **1.02–1.20 with afterburn `miller`**. The band in the test is 0.80–1.35.
- **Hardware:** `BYTES_PER_CELL = 2650` in the application; **2,696 measured** on an
  i7-14700 (R² = 0.9996), a 1.7 % gap — the constant does **not** need measuring per
  machine.

---

## 5. Identifier index (B / G / A / N / W)

> **Code comments cite these identifiers. Do not delete this section.**

**Bugs (B)**
- B1 truncated `uniform` internalField AttributeError — DONE (T1)
- B2 kill-escalated stop crashed finalize — DONE (T1)
- B3 3D replay hardcoded the x-z plane — DONE (T2)
- B4 final frame missing from 3D viewer playback — DONE (T2)
- B5 chains bypassed validate_case — DONE (T6)
- B6 Stop could not interrupt foam preflight — DONE (T6)
- B7 foam progress bar at 0 until first write — DONE (T5)
- B8 Pa/kPa inconsistency — DONE (T3)
- B9 net vs positive-phase impulse naming — DONE (T3/T12)
- B10 duplicated last gauge row — DONE (T8)
- B11 native warnings bypassed hooks — DONE (T7)
- B12 1D snapshot scheduling — DONE (T8)
- B13 run-dir name collision — DONE (T4)
- B14 `--clean-foam-runs` live-run guard + orphan reaping — DONE (T4)
- B15 uncaught TimeoutExpired in stop paths — DONE (T1)
- B16 out-of-order ingest — DONE (T10)
- B17 stale FO peak/impulse — DONE (T10)
- B18 grids silently shrank one cell — DONE (T8)
- B19 3D viewer colour-range plumbing — DONE (T13)
- B20 FrameStore thinning — DONE (T2)
- B21 multi-charge stop distances — DONE (T10)
- B22 'Run failed' dialog text — DONE (T5)
- B23 `test_foam_parallel` determinism fails randomly — DONE (2026-09-07, T35)
- B24 resolved-charge init not mass/energy conserving (±3 %) — DONE (2026-09-07, T36)
- B25 controlDict rewrites inside fileModificationSkew ignored — DONE (2026-09-05, T18)
- B26 chain 3D stage reused the 2D revolved feed — DONE (2026-09-07, QA-05)
- B27 validation/preview allocated the full fine grid — DONE (2026-09-07, QA-01..04)

**GUI (G)**
- G1 "Initialise Model" hint erased — DONE (T5)
- G2 results accumulate / duplicate labels — de-dup + Remove DONE (QA-13); user-named runs DONE (T30)
- G3 validation split-brain / silent swallowing — DONE (2026-09-07, T29)
- G4 replay / preview stalls (idle-CPU half refuted) — DONE (2026-09-07, T31)
- G5 chain start race — DONE (T6)
- G6 progress < 100 % (DONE, T5); theme half refuted by QA (mesh overlay colour cosmetic) — closed
- G7 live-view niceties (cadence hint, 2D Min/Max) — DONE (2026-09-07, T38)
- G8 preview lacks extra charges / det points — DONE (2026-09-07, QA-21 + T31)
- G9 accelerators / persistence / focus — DONE (2026-09-07, T32)
- G10 default 3D case invalid, nan/inf accepted — DONE (2026-09-07, QA-14/15)
- G11 layout at 1280×840 / 1100×720 — DONE (QA-07/08 + T27)
- G12 stale state — DONE (QA-09..12 + T28)
- G13 light-mode affordance — DONE (2026-09-07, T32)
- G14 1D live pane pinned to 10 kPa — DONE (2026-09-08, T61)

**Architecture (A)**
- A1 foam run loop triplicated — DONE (T9)
- A2 geometry logic quadruplicated — DONE (T9, `core/geometry.py`)
- A3 postmortem private imports — DONE (T9)
- A4 dead code — foam + viz3d DONE (T9/T13); native DONE (2026-09-07, T37)
- A5 guard-rail constants duplicated as literals — DONE (2026-09-07, T37)
- A6 `Time =` regex needs a canary — DONE (2026-09-07, T37)
- A7 `_decode_surface` silent degrade — DONE (2026-09-07, T37)
- A8 viz3d control-message delivery — DONE (T13)
- A9 commit hygiene — DONE (2026-09-02) · **re-opened, then closed 2026-09-09 (`e344d17`)**
- A10 regression discipline — standing rule

**New capabilities (N)**
- N1 peak/impulse views — DONE (T11) · N2 per-gauge summary + CSV — DONE (T12)
- N3 afterburn (`none | miller`) — DONE (T16); non-TNT Q0 from oxygen balance only, uncalibrated
- N4 VTK export — DONE (T15) · N5 charge-mass rasterisation — DONE (T39)
- N6 resume a stopped run — DONE (T43; a profile+AMR stage does NOT resume — closed, see P1-5 history)
- N7 chains INTO blastFoam — DONE (T41, fixed T62, AMR opened up in T70; static zones still refused)
- N8 foam run browser + auto-cleanup — DONE (T14) · N9 user-named runs — DONE (T30)
- N10 MUSCL second order — DONE (T47) · N11 native materials beyond TNT — DONE (T46)
- N12 gauge fields beyond p — DONE (T44) · N13 HTML report / N14 CSV field maps — DONE (T45)
- N15 local (static) refinement + show-mesh — DONE (T17–T19); mesh on the run's own animation (T49);
  AMR in the video (T54); replay memory (T55); MP4 (T56)
- N16 dynamic AMR — DONE (T20–T24); N16-a probe cell DONE (T40); N16-b parallel DONE (T42, load fixed T57)
- N17 hardware-aware run plan — DONE (T48)
- N18 boundary kinds + per-run end time — DONE (T50, T52, T60)
- N19 trigger gauge + gauge markers — DONE (T51, T53); **2D/3D only since T63**
- N20 Results title line + 1D model preview — DONE (T58, T59)
- N21 cross-machine hardware model: honest sources, conservative-on-unknown
  caps, machine fingerprint + TTL, host-RAM native caps, n_procs clamp — DONE
  (T64–T69)

**Watch items (W)**
- **W1** foam near-field arrival lag — CHARACTERISED (T40), no action; `linear` stays the default
- **W2** blastProbes flushes buffered gauge samples only at a graceful End — **REFUTED by
  measurement (2026-09-14)**; see §7b. `OSstream::endl()` is write+flush per sample line, and
  a `kill -9` mid-step lost zero rows.

**Later identifier series**

- **N5-4 … N5-12** — the chain hand-off and parallel-ignition investigation of 2026-09-18/20.
  `N5-6` (rotateFields spike, negative result), `N5-7` (`det_radii` is now the default),
  `N5-11` (`RHO_MIN`), `N5-12` (`programmedIgnition` + delays/radii).
- **N2-01 … N2-16**, **N3-01**, **UX-01 … UX-06** — the QA nights and the UX review.
  See [docs/history/qa-nights.md](docs/history/qa-nights.md).
- **HD1-1 … HD1-11c** — the HD1.3 track. See §0.
- **P0-x … P5-x** — the priority queue. Closed items are in §7b and in the history files;
  what remains open is in [TODO.md](TODO.md).
- **B0 / B1 / B2 / N1–N4 of the solver-options review** are a **separate, document-local
  numbering** that collides with the B/N index above. Always write "solver review B0",
  never a bare "B0". See
  [docs/verification/solver-options-review.md](docs/verification/solver-options-review.md).

---

## 6. The QA round of 2026-09-07 (QA-01…QA-35)

**What was done:** the real GUI was driven on screen (1280×840, dark then light) through
the widgets' own commands, **367 screenshots across 59 scenarios**: all four tabs,
validation, native 1D/2D/3D runs, a chain, **11 real blastFoam runs in WSL** (static
refinement, 2D and 3D AMR, Stop during meshing and during the solve, the run browser, VTK,
post-mortem loading, closing the window mid-run), theme switching and robustness. Found
6 S1, 9 S2, 10 S3 and 11 S4 findings — **all fixed** in T25–T33.

**S1 — crashes (fixed, T25/T26).** QA-01/02/03 (B27): `refine.plan_levels`/`_plan_amr`
reject a degenerate or memory-exploding mesh with `ValueError` **before** allocating a full
array; QA-04: `Plan.solid_fine` trims `expand(solid_base)` to the level map's shape (641 vs
642); QA-05 (B26): `GuiHooks.run_started` drops the previous stage's feed/scene; QA-06:
`validate_case` checks the burst centre against the domain in every init mode.

**S2 — wrong data and layout (fixed, T25).** QA-07 a minimum width for the input column
plus label wrapping; QA-08 a two-line Results title; QA-09 `View3DPanel` raises the Display
tab after construction; QA-10 `set_running` resets the chips and reads "PAUSED at step N";
QA-11 the live panel switches to "waiting for the solver…"; QA-12 the replay canvas is
explained and empty when there are no frames; QA-13 repeated-label numbering + a Remove
button; **QA-14 the 3D form opens on a case that passes validation** (8 kg in a 3 m box at
2 cm = 3.4M cells, instead of a default that refined to ~852M); QA-15 non-finite and
fractional input rejected. A cap error now explains the cause.

**S3 (fixed, T27/T29/T31/T32/T33).** QA-16 (G3) validation; QA-17 layout and fields;
**QA-18 performance — `feed_result` 2364 ms → 259 ms**, a preview cache, worst gap in a
native 3D run 3544 → 1100 ms; QA-19 light-mode visibility; QA-20 log line wrapping; QA-21
(G8) extra charges and burst points in the previews; QA-22 file-open error messages; QA-23
chain feedback; QA-24 replay for a loaded run; QA-25 the validation card is height-bounded
and scrolls.

**S4 (fixed, T27/T32/T33).** QA-26 `p max` in kPa; QA-27 truncated headings; QA-28
matplotlib Back/Forward buttons removed; QA-29 (G9) accelerators and persistence; QA-30 a
scrollbar in the run browser; QA-31 clipping the top 0.5 % on peak/impulse maps; QA-32 a
folded AMR log + a `cells` chip; QA-33 gauge table headings; QA-34 the logo file is closed;
QA-35 a disk note for AMR with the run total.

> **QA-18 — a wrong attribution corrected.** The 3.5 seconds attributed to "AMR frames"
> were in fact building the 3D preview in `set_case`, which the cache had already fixed.
> `mesh_polydata` costs 262–320 ms once (VTK warm-up) and then ~5–8 ms per frame. **No
> throttle was needed**, and the original attribution was wrong.

---

## 7. Verified correct — do not "fix"

Axisym momentum source is exactly well-balanced against the face-area metric; `bc.py` mirror
signs are correct; the y/z-sweep moveaxis round trip is index-correct (pinned by T1); smear
init conserves mass/energy to 1e-12 (T10); foam `to_grid` F-order reshape ↔ viewer
`ravel(order='F')` ↔ VTK point order is consistent end-to-end (a transpose trips
`test_viz3d_scene` S2c); obstacle scatter/carve ordering matches boxToCell; the GUI
worker/queue architecture (latest-wins frame slots, exception-hardened drain, Tk-thread-only
widget access) is clean — **treat it as the pattern for new panels.**

**The axis limitation in axisymmetric cases — structural, not a bug:** the wedge's axis
cells are prisms, and hexRef8 does not refine them. So under AMR the charge stays coarse in
the axis column (`validate_amr` warns), and under static refinement only level 1 is possible
on the axis and a zone touching the axis is refused (`validate_zones`). If the field close to
the axis matters — use a finer base cell or planar geometry (which refines everywhere).
**Do not try to "fix" this on the Python side.**

> **⚠ One clause of the above was later measured to be wrong.** In the P1-6 investigation
> (2026-09-15) it was measured directly that **`adaptiveFvMesh` *does* split wedge axis
> cells** — `cellLevel = 1` on the axis column — contrary to the "prisms do not refine"
> folklore. That splitting is the mechanism behind the axis-drain SIGFPE, and it is why
> `Lohner` replaced `densityGradient` as the default estimator. The *practical* advice above
> still holds; the stated reason does not.

Native↔foam physics: foam peaks 1.10–1.16× native at r = 1–4 m with arrivals within
0.7–4.5 %, both monotonic; KB anchor 1.02–1.20 with afterburn `miller`.

**Confirmed by eye in the QA round:** static refinement + Show mesh everywhere, AMR
per-frame, the gauge table + CSV, the run browser, VTK export, post-mortem loading identical
to a live run, Stop at every stage, and no orphaned solvers.

---

## 7a/7b. The QA nights — what landed and was verified

Full analysis: [docs/history/qa-nights.md](docs/history/qa-nights.md). The commits:

| Finding | Commit | The proof |
|---|---|---|
| The GUI matrix ran for the first time ever | `a5ef729` | `--smoke` exit 0, **7/7 real screenshots, 1,059–1,788 distinct colours** each (colour count, not luminance — a PrintWindow that draws only the frame gives uniform grey that passes a luminance check) |
| N2-02 / N2-03 (test bugs) | `75a9e9e` | The product answered correctly in both; the test could not accept the answer |
| N2-04 (`C10` asserted on an impossible label) | `62984c7` | The assertion moved to where it is true; the 3D case got the one that **is** true of it |
| N2-09 the gauge table | `5afe1ca` | `mapped=True` at every height 840–1080 (it had vanished below 960) |
| `wait_log` (a tool fault caught within the hour) | `736c309` | Baseline taken at the moment of the click; E03 15 s, zero findings |
| N2-06/10/11 cosmetics | `2fa79f2` | One screenshot shows all three |
| N2-12 the Run freeze | batch | **13,266 → 2,643 ms** — a VTK import avalanche, warmed in a daemon |
| N2-05 `level_map` | batch | **Byte-identical** against a baseline captured beforehand; 1,445 → 245 ms |
| N2-07 `rho0` in the preview | batch | New ANFO tests; there is **one** materials table, not two |
| **N2-13 + N2-14 — the chain** | `b343d89` + `eeb8853` | **4/4 chains identical to the digit** (s1=0.050, s2=0.194, t0=0.00019422544); stage-3 IC: T ≤ 2,149 K (was 8.3e6), zero floored cells |
| N2-15 — the 2D arrival stop on the live sample | `08ce68d` | R2 had run 8.7 h past arrival because the check was ingest-gated (2,193 samples queued) |
| N2-08 — GL warm-up at idle | `ab8acfd` | First feed 1,683 → **971 ms**; E06's gate passes for the first time |
| N2-16 + the R2 fixture tie | `c130210`, `84c1099` | An obstacle edge sat exactly on a cell-centre line and Python and foam broke the tie opposite ways (171,580 vs 171,604 cells) |
| Obstacle snapping to cell faces | `4e97108` | `refine.snap_obstacles` snaps outward at plan time; N2-16's ties are **structurally** impossible. Goldens: exactly two boxToCell lines |
| N3-01 — live 3D arrival stop + a deterministic symmetry gate | `f5feb93` | Before: 4 FAIL of 6; after: **5/5** |
| UX-01/02/03 · UX-04 · UX-05/06 | `a0dd97d` · `fcf34c2` · `8bc1e19` | All six UX findings closed |
| E06 closed | `04fcbee` | The ~1 s was a **first-in-process** BlastScene (809 of 924 ms); a third idle warm-up takes the first feed 980 → **272 ms** |
| The MPI directional bias root found | `12a255a` | np=1 → 0.10 % · np=2 → 0.26 % · np=8 → 4.85 %, independent of the slice axis. The test pins np=2, giving a machine-independent gate with 19× margin |
| P2-3/P2-4 — the e2e completion round | `b2a67ef`, `406810d` | obstacle3d, refine3d, amr3d, chain, chain_amr all PASS. **The whole `_e2e_foam_*` family is covered by a real run** |
| P5-1 closed — "intermittently crashes" is not structural | — | 25/25 runs, full PASS, signature identical to the digit. The instrumentation stays armed |
| W2/P1-2 refuted by measurement | — | Source: `OSstream::endl()` is write+flush per sample line. Measurement: `kill -9` mid-step — 208 rows in ext4 = 208 through 9p, immediately and after 30 s. **Zero loss** |

> **The chain took four layers to become deterministic** (a clock-dependent stop → a
> clock-dependent write schedule → anchoring to the write before arrival → scanning forward
> because the tail vents back), each locked by measurement. **The key insight:** the old
> hand-off was a post-venting state (2–4.7 ms instead of 0.194 ms) — that is where the vacuum
> states came from.

---

## 8. Baselines, file versions and commits

**`test_regression` policy:** must stay green byte-for-byte. Re-baseline only when a task
says so explicitly, and in the same commit. Foam goldens regenerate only through
`python blastlab/tests/test_foam_writer.py --update` plus an eyeballed diff.

**Re-baselines performed:** T8 (the native fix bundle — the single batched run); T36 (the
conserving charge initialisation); T50–T54 (`transcript.txt` only — 30 lines of wording, every
numeric baseline byte-identical); T60 (`transcript.txt` only — one `Outer boundary` line, an
addition only).

**Goldens updated for `det_radii` (2026-09-20):** 15 goldens, **one `radii` line in each, zero
deletions**. The cost is stated explicitly: foam results from before that date are not
byte-comparable. In the measured case the serial peak went 19914 → 19607 kPa (−1.5 %), because
a ball of radius ~dx around a corner point ignites the 4 cells meeting there instead of the one
cell `findCell` picked arbitrarily.

**Goldens updated for `Lohner` (2026-09-20):** three `dynamicMeshDict` files, three lines each
(`errorEstimator Lohner` + `field p` + `epsilon 0.05`).

**`settings.json` (N21):** `hw_fingerprint` and `hw_host_ram_gb` were added; no key was renamed
or removed, and an old file loads normally — it simply lacks a fingerprint, so its stored
numbers are rejected once, until the first probe. **`test_regression` was not affected by N21
and cannot be:** the derived cap only lowers `CELLS_*`, and the solvers keep enforcing the
constants unchanged.

**Case-file versions (`VERSION`):** 5 → 6 `anim_mesh` (T49) … → 10 (T50–T52 boundary kinds,
`t_end`, trigger) → **11** (T63: the three trigger keys are deleted at `dim == 1` before the
unknown-key check, so every saved 1D file and every old run's `case.json` keeps loading) →
**12** (`anim_scale`) → **13** (`adaptive_write` as a declared field on all three Case classes).

**Key commits:** `ba37a65` + `73ca834` (QA S1/S2), `3cb800c` (QA S4), `a6c7463` (validation and
feedback), `c3ce365` (T61), `a7930e3` (T60), `a416630` (T58/T59), `5262277` (T57), `972dca9`
(T56), `e344d17` (P0-1..3), `b18a9cb` + `68d23dc` + `8e107fe` (the PySide6 migration).
The full roadmap history: `git show 73ca834:ROADMAP.md`.
