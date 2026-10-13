# P3 - capabilities and improvements, on request

Moved out of [`TODO.md`](../../TODO.md) on 2026-10-13 (owner-approved split, TODO.md at its
1000-line cap; `docs/batches/2026-10-13-todo-split-proposal.md`). Ids unchanged.

*(None of these blocks anything.)*

**Physics**

- `P3-1` Non-box obstacles (STL → snappyHexMesh) — needs the same resampler as AMR.
- `P3-2` Enable `pressureBased` activation — per-material rate constants; only if
  ignition physics matters.
- `P3-3` Per-case override of `maxDeltaT`/`deltaT` — trivial wiring in the writer.
- `P3-4` HLLC comparison: `dicts.FLUX_SCHEME = 'HLLC'` is a one-line flip;
  `test_foam_1d_vs_native.py` is the harness. *(HLLC is sharper at contact surfaces —
  the products/air interface — than Kurganov.)*
- `P3-5` Axisymmetric smear option in 2D (3D has it; 2D refines only).
- `P3-12` Static refinement zones for a profile-initialised stage. `refineMesh`
  renumbers cells, so `writeCellCentres` + `build_remap` must move before
  `write_deferred` and the fields must be written through `spec.remap` — the
  machinery exists, only the order is wrong.
- `P3-13` Extra charges exist only in 3D. In **planar 2D** it is feasible — a 2D
  charge is an infinite cylinder, and `spec.charges` is already a list on the 2D
  path. Missing: the setFieldsDict, overlap/boundary checks and the GUI table.
  Axisymmetric stays a single charge on the axis — that is geometry, not a gap.
- `P3-14` 3D→3D remap — **moved to P1** ("Remap-chain gaps", owner 2026-10-11).
- `P3-15` Obstacles do not survive the 2D→3D remap — they would become rings around
  the axis, so `save_profile_2d` drops them with a warning only. The 3D stage
  continues a state that evolved around obstacles that are no longer there.
  **Minimum:** raise it to a validation warning in the GUI instead of a stdout print.
- `P3-27` A hemispherical surface burst through the chain (1D→3D / 1D→2D near the ground); the factor is an owner call, cited from UFC 3-340-02. Detail: `docs/verification/remap-chain-gaps.md` §5.
- `P3-28` Several charges with a hand-off: extra charges beside a remapped field, and several 1D hand-offs placed in one 2D/3D stage (one common hand-off time, fields not yet met). Same doc §5.

**From the solver-options review** — full detail and dict snippets in
[docs/verification/solver-options-review.md](docs/verification/solver-options-review.md).

- `P3-16` **`conservedQuantities` on every run**, checked in `postmortem`. Both
  hand-off bugs were energy non-conservation, and this function object would have
  caught both automatically. *Small.*
- `P3-17` **`timeOfArrival` + `overpressure store yes`.** Arrival time is the third
  standard output of blast engineering and the repo already produces the other two.
  *Small.*
- `P3-18` **`volScalarFieldMassIntegrated`** for charge mass — sets alpha so the
  deposited mass equals the request **exactly**, which would let the charge
  resolution drop from 8 cells back to 5 and save 4.1× the cells in 3D. **Validate
  against the KB anchor first:** the afterburn calibration was fitted with the
  present deficit baked in and would need refitting. *Medium.*
- `P3-19` **`beginUnrefine`** (the guide recommends it explicitly for explosives) and
  **`allowableImbalance`** in `dynamicMeshDict`. *Small.*
- `P3-20` **`rotateFields`** as a replacement for the Python remap. Operates on
  fields rather than interpolated conserved quantities, rotates vectors correctly,
  and `-refine` lifts the "no refinement zones on a profile stage" restriction.
  **The guide warns the mapping is not conservative** — validate against the
  baselines, do not swap blindly. *Large.*
- `P3-21` Expose `activation programmedIgnition` and `initiation delays` in the GUI.
  *Medium.*
- `P3-22` **`reconstructParAll`** for the parallel AMR path — the entire
  post-processing path would work directly instead of through the special Python
  ingest. The existing workaround works and is cheaper, so this is an opportunity,
  not a bug. *Medium.*
- `P3-23` **`DoanNickel` EOS for air** — accounts for dissociation at high shock
  temperatures, where constant γ overestimates pressure. Directly relevant to the KB
  anchor at small Z, and a one-word change. *Small, research value.*
- `P3-24` **Schlieren / shadowgraph** fields for animations — the standard
  visualisation for shock waves, one extra field per time directory. *Small.*

**Performance**

- `P3-6` Read `processor*/` directly for uniform MPI runs too (skip reconstructPar) —
  only if the ~3 s per write is annoying. The mechanism already exists for AMR.
- `P3-7`, `P3-8`, `P3-25` ✅ closed 2026-09-27 (batch `viewer-polish`) — [DONE.md](DONE.md) §0e.

**Cosmetic** *(anything touching solver stdout needs a re-baseline)*

- `P3-9` The x-axis label on an axisymmetric animation: `x [m]` → `r [m]`.
- `P3-10` A chained run prints "0 kg TNT" in the 3D initialisation line.
- `P3-11` The semantics of `n_snapshots` differ between 1D and 2D/3D.

**Architecture** *(owner decision 2026-09-26, during `OUT-1`)*

- `P3-26` **A command-line layer outside `solvers/`.** `solvers/foam/cli_run.py` and the
  prompt flows in `cli.py` are command-line code that lives in the solver layer, so
  `test_layering` (solvers must not import services) forces the model folder to reach
  them through a registration hook (`jobs.register_stage_folder`, `OUT-1` Steps 3 and 8).
  The owner chose the hook for now and **the proper fix as a task**: move the
  command-line flows into a `cli/` (or `output/`) layer that may import `services/`,
  delete the hook, and leave `test_layering` untouched. Do it after the `OUT` track;
  byte-identity of `test_regression.py` and the `legacy/` pins are the gates.
