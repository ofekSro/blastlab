# blastFoam Backend — Suggestions & Roadmap

Status snapshot (2026-08-16): the `solver='blastfoam'` option is live for 1D/2D/3D
with GUI + CLI + 3D-viewer integration, validated against the native solvers
(1D peaks within 8%, arrivals 3–11%). This file collects everything worth
checking, adding, changing, or watching next.

---

## 1. Things to CHECK (verification still worth doing)

| What | How | Why |
|---|---|---|
| **Real GUI session, 3D blastfoam run** | `python -m blastlab` → 3D form → Solver=blastfoam → Run; watch live slice + embedded 3D view, press Interrupt/Exec/Stop | All paths were verified headlessly (worker tokens, Feed3D payloads, SIGSTOP pause); nobody has *looked* at a full interactive session yet |
| Results panel field views for a foam run | After a run: snapshots combo, overpressure/density/speed views, isosurface tab, animation replay, all Export buttons | Shapes are contract-identical, but visual sanity (colour scales, slice orientation) deserves one pass |
| Chain: foam 1D → native 2D → native 3D | Chain tab with stage 1 solver=blastfoam | `final_profile` export was verified programmatically; the full chain UI flow wasn't |
| Long/large 3D run behaviour | e.g. 10 m box, 1 kg, dx auto (~1M cells, expect hours serial) | Ingest cost per write (~1–3 s), disk (~2–6 GB), progress smoothness at scale are extrapolated, not measured |
| Gauge overpressure vs published TNT curves | Compare foam gauge peaks at scaled distances Z = R/W^(1/3) against Kingery-Bulmash | Both solvers agree with *each other*; anchoring to literature data would validate absolutely |
| Multi-material sanity | Run the same case with C4 vs TNT; C4 peaks should be ~1.2–1.4× TNT | Materials beyond TNT/C4 (RDX/HMX/PETN/ANFO params from the toolkit docs) have not been exercised in anger |
| blastProbes `adjustLocations` behaviour near walls | Gauge exactly on the ground plane (z=0) | Header-vs-column fallback exists in `reader.read_probes`, but snapping at boundaries wasn't probed |

## 2. Things to ADD (deferred features, in rough priority order)

1. **Parallel runs** (biggest speed win — 3D is serial today, ~0.4 s/step at 100k cells):
   - `n_procs` case field → write `system/decomposeParDict` (scotch), pipeline becomes
     `blockMesh → decomposePar → mpirun -np N setRefinedFields -parallel → mpirun -np N blastFoam -parallel`.
   - Reader options: `reconstructPar -newTimes` per poll (simple, adds latency) or read
     `processor*/` dirs directly + stitch (faster, more code).
   - Watch out: blastProbes output may need `mergeProbes`; `.run.pid` becomes mpirun's pid (kill semantics still fine — TERM to the process group).
2. **Binary `writeFormat`** — halves write size and Python parse time for 3D
   (`reader` gains: ascii header + `List<scalar>` count + `(` + raw little-endian doubles + `)`);
   flip `writeFormat` in `writer._controldict` once the reader handles both.
3. **Foam-side profile input (chains INTO blastfoam)** — write `nonuniform` internalFields
   (p/T/U/alpha/rho per cell) directly from a loaded 1D/2D profile and skip
   `setRefinedFields`; remove the `init_mode != 'charge'` validation block. T from
   e/Cv per phase (inverse of the export path already in `backend`).
4. **Obstacles** (the headline deferred feature):
   - Boxes → STL (trivial to emit) → `surfaceFeatures` + `snappyHexMesh` (template: `building3D` tutorial).
   - The mesh stops being uniform ⇒ the F-order reshape contract breaks. Needs a
     **resampling layer** (foamToVTK/pyvista `vtkResampleToImage` onto the uniform grid)
     between reader and viewer. Do this *before* AMR — same resampler unblocks both.
5. **AMR** (`adaptiveFvMesh` + `refineInternal`/`level` in setFieldsDict) — big accuracy/speed
   win for large domains; blocked on the same resampler as obstacles.
6. Smaller additions:
   - `overpressure`/`impulse`/`fieldMinMax` function objects instead of (or validating) the backend's Python accumulators.
   - Detonation point ≠ charge centre (blastFoam supports arbitrary `points`; expose in the form).
   - Multiple charges (list of spheres in setFieldsDict + multiple initiation points) — blastFoam makes this nearly free.
   - `activationModel` choice (`none` = instant, closer to native early-time behaviour; `pressureBased`).
   - Per-case `maxDeltaT`/`deltaT` overrides for stiff cases.
   - Reattach/post-mortem mode: load a finished WSL case dir into the Results panel without re-running (`meta['case_dir']` is already recorded).

## 3. Things to CHANGE / TUNE (known compromises in v1)

| Item | Current state | Suggested change |
|---|---|---|
| **writeInterval sizing** | `1.5·est_dist/(2·c_amb)/n_writes` — near-field runs still get few frames (3D smoke: ~4 pre-arrival writes) | Runtime-adaptive: controlDict is runTimeModifiable, so the backend could *raise* writeInterval once the front slows, or start dense and back off |
| Live-frame granularity | Frames only exist at write times (vs native per-step) | Document in README; the real fix is the adaptive interval above |
| `e` in viewer payloads | Ideal-gas approximation `p/((γ−1)ρ)` (blastFoam writes no `e` field); wrong inside the fireball | Read `T` per 3D frame and reconstruct per-phase (costs one more field parse per frame), or drop Energy from the field selector for foam runs |
| Flux scheme | `Kurganov` (tutorial-validated default) | `dicts.FLUX_SCHEME = 'HLLC'` is a one-line flip; the 1D comparison test doubles as the A/B harness |
| Wedge half-angle | 1° (sector + axisym) | Uncontroversial, but if axisym accuracy is ever questioned, test 2.5°/5° (the shipped tutorial uses 5°) |
| Arrival-gate in `test_foam_2d.py` | 45% (near-field activation-model lag) | If instant detonation matters, add `activationModel none` and tighten the gate |
| Reactant thermo | Murnaghan Γ=0.25, Cv 815/1400, molWeight 55 for *all* materials (freeField defaults) | Fine for airblast; refine per material if reactant-phase details ever matter |
| `np.fromstring` in reader | Deprecated (warning suppressed), C-fast | Migrate to the binary reader (item 2 above) rather than chasing a text replacement |
| Duplicated run-loop | 1D/2D/3D each carry the drain/ingest/stop skeleton (~30 lines × 3) | Extract a shared `_drive()` once the loop stops evolving (post-parallel) |
| Probe NaN fallback | Header/column mismatch pads with requested locations | Never observed in practice; revisit if parallel probes change the format |

## 4. Things to WATCH (operations / maintenance)

- **Disk**: every run stays in `/root/blastlab_runs/` for post-mortem (a big 3D run is 2–6 GB).
  `python -m blastlab --clean-foam-runs` lists + deletes. Consider auto-cleanup of runs older than N days.
- **WSL flakiness**: cold starts can time out (`Wsl/Service/CreateInstance/0x800705b4`) — the env
  probe retries 3×; if WSL wedges completely (every start times out), run `wsl --shutdown` and retry.
- **Regression discipline**: `tests/baseline/transcript.txt` byte-pins ALL native-solver stdout.
  Never add/alter a `print()` in `solvers/solver*.py`, `output/gauges.py`, `core/profiles.py`, `legacy/*`.
  The foam backend must log via `hooks.log` only. Run `python test_regression.py` before every commit.
- **Golden files**: any intentional change to generated case text ⇒ `python test_foam_writer.py --update`,
  then eyeball the diff before committing. `.gitattributes` keeps golden/fixture/baseline bytes safe from EOL conversion.
- **Version coupling**: templates target blastFoam **v6.2.0** / OpenFOAM-9 as installed. Upgrading the
  WSL install may change stdout tokens (`Time =`, `max(p):`), probe file layout, or dict keys —
  the reader/runner regexes and `test_foam_reader` fixtures are the canary.
- **Stop latency**: graceful stop ≈ write-completion + `fileModificationSkew 1` detection (~1–3 s
  observed); the 60 s kill escalation covers hangs. If stops ever feel slow on huge meshes, the
  wait is blastFoam finishing the current step + final write, not the mechanism.

## 5. Test matrix (what exists, how to run)

```
cd blastlab/tests
python test_regression.py         # native byte-parity - MUST stay green
python test_foam_writer.py        # case generation goldens (no WSL)
python test_foam_env.py           # WSL probe/caching (+live probe)
python test_foam_reader.py        # parsers vs real fixtures (no WSL)
python test_foam_1d_vs_native.py  # physics gates, ~1 min (WSL)
python test_foam_2d.py            # axisym comparison + planar smoke, ~3 min (WSL)
python test_foam_3d_smoke.py      # full 3D contract, ~2-3 min (WSL; --tiny for ~1 min)
```

Suggested additions: a stop/pause regression script (currently verified ad hoc), a
multi-material spot check, and once parallel lands — an np=1 vs np=4 equivalence test.
