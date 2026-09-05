# פרומפט להוספת AMR (עידון רשת דינמי) — לשיחה חדשה

**איך להשתמש:** פותחים שיחה חדשה של Claude Code בתיקיית הפרויקט עם מודל **Fable**,
נכנסים ל-**plan mode** (Shift+Tab עד שכתוב "plan mode on"), ומדביקים את כל הבלוק שלמטה.
הסשן יחקור, ישאל שאלות, יציג תוכנית לאישור — ורק אחרי שתאשר יתחיל לכתוב קוד.

הפרומפט באנגלית בכוונה (הקוד, ה-ROADMAP והבדיקות באנגלית — חוסך טוקנים ומונע תרגום שגוי).

---

```
Plan and then implement DYNAMIC mesh refinement (AMR) for the blastFoam
backend of this project: the mesh follows the shock during the run
(blastFoam's `adaptiveFvMesh`), instead of today's static per-zone
refinement which is fixed before the run starts.

Work in plan mode first: explore, ask me the questions listed at the end,
write the plan, and get my approval before changing any code.

## Project

blastlab - a Python blast-wave simulation desktop app (customtkinter GUI),
native numpy 1D/2D/3D solvers in `blastlab/solvers/`, and a blastFoam
backend in `blastlab/solvers/foam/` that writes OpenFOAM-9 cases, runs them
in WSL (Ubuntu) and reads the results back onto uniform numpy grids; a
pyvista/VTK viewer in `blastlab/viz3d/`. Planning docs: `ROADMAP.md`
(item ids like B1/N1/A1 refer to it) and `TASKS.md` (one session per task).
Read ONLY the ROADMAP items named below, not the whole file.

Hard rules (same as every session in TASKS.md):
- Never change native-solver stdout or the byte-pinned outputs.
  `python blastlab/tests/test_regression.py` must stay byte-identical.
- Foam goldens regenerate only via `python blastlab/tests/test_foam_writer.py
  --update` plus an eyeballed diff. With AMR off, every existing golden must
  stay byte-identical.
- Tests are plain scripts: `cd blastlab/tests && python test_X.py`. Files
  named `_e2e_*.py` are manual end-to-end runs (WSL, 1-10 min each).
- WSL work runs in the FOREGROUND (backgrounded shells that spawn WSL
  children report completion early and lose stdout). After killing anything:
  `wsl.exe -d Ubuntu -- pgrep -a blastFoam`, and kill leftovers.
- Do not commit until the work is verified; then one commit with a message
  that says what was measured.

## What already exists (do not rebuild it)

Static local refinement landed as ROADMAP N15 (sessions T17-T19). Read
`ROADMAP.md` item N15 and `blastlab/core/refine.py` in full first. Key APIs:

- `core/refine.py` - the predicted mesh structure, pure numpy:
  `plan_levels(case, rho0)` -> `Plan(dx_base, base, fine, levels, lmax,
  zones, solid_base, n_pred, n_fine)`; `fine_src(levels, lmax, solid_fine)`
  -> int32 id per fine cell; `slice_src(...)` for one plane;
  `mesh_segments_2d(src2d, u_face, v_face)` -> cell-edge segments for the
  "Show mesh" overlays; `match_cells(C, fine, fine_ids)` -> `remap`, the
  fine-grid gather map, raising loudly on any structural mismatch;
  `n_cells_from_levels`, `expand`, `snap_zone`, `validate_zones`.
- `solvers/foam/writer.py` - `CaseSpec` carries `dx_base`, `nb` (base counts
  for blockMesh), `levels`, `lmax`, `zones`, `solid_base`, `remap`,
  `n_cells_actual`; `grid/nx/ny/nz/dx/solid` are the FINE display grid.
  `_refine_dicts` emits one `system/topoSetDict.refine{l}` +
  `system/refineMeshDict.{l}` per level. `_dynamicmeshdict()` currently
  always writes `dynamicFvMesh staticFvMesh;` - that is the file AMR
  replaces.
- `solvers/foam/backend.py` - `_mesh_stages` (blockMesh -> obstacle carve ->
  per-level topoSet/refineMesh -> setRefinedFields -> `postProcess -func
  writeCellCentres -time 0` -> decomposePar); `build_remap(spec, hooks)`
  reads `0/C` once and matches it against the predicted structure;
  `_decode_surface(..., remap_sl)` decodes the live slice through the remap.
- `solvers/foam/reader.py` - `to_grid(vals, spec, fill)` has a remap branch
  (gather per fine cell, -1 = carved); `read_cell_centres(case_unc)`;
  `read_vector(path, n_cells=None)` accepts any count.
- `solvers/foam/runloop.py` - `FoamRunLoop` (the shared run loop),
  `OrderedIngest`, `PeakImpulse`.
- Display: `meta['refine'] = dict(levels, lmax, dx_base, zones)`;
  `plots.mesh_for/add_mesh_lines`; `viz3d/viewer._MeshEdges`; "Show mesh"
  checkboxes in the setup preview, the live run plot, the Results panel and
  the 3D viewer's Display tab.

## Facts already verified against the installed blastFoam (do not re-derive)

Sourcing `/root/OpenFOAM/OpenFOAM-9/etc/bashrc` in WSL (that is what
`env.wsl_argv` does):

- `libblastDynamicFvMesh.so` provides `adaptiveFvMesh` and
  `dynamicRefineFvMesh`; refiners `hexRefiner` and `polyRefiner`
  (`libblastDynamicMesh.so`).
- Coefficient keys present in that library: `refineInterval`,
  `maxRefinement`, `nBufferLayers`, `lowerRefineLevel`, `upperRefineLevel`,
  `unrefineLevel`, `maxCells`, `correctFluxes`, `dumpLevel`, `field`,
  `fields`.
- Error estimators live in `liberrorEstimate.so`: `Lohner`, `delta`,
  `scaledDelta`, `densityGradient`.
- `refineMesh` (the static path) writes NO `cellLevel`; cell centres come
  from `postProcess -func writeCellCentres` -> `0/C`. Whether
  `adaptiveFvMesh` writes `cellLevel`/`polyMesh` per time dir is UNKNOWN and
  is the first thing to establish.
- `boxToCell` selects by cell CENTRE, inclusive - the same criterion as
  `core/bc.solid_mask_*`.
- OpenFOAM only re-reads a `runTimeModifiable` controlDict when its mtime
  exceeds the last seen one by more than `fileModificationSkew` (10 s);
  `runner.rewrite_control_entry` bumps the mtime by 40 s for that reason
  (ROADMAP B25). Keep that in mind for anything that edits controlDict.
- Empirical probing works well and is cheap: write a tiny case, add the
  dictionary entry, run the solver, and read the FATAL error - it names each
  missing keyword in turn. That is how the afterburn model's key set
  (`Q0/a/n/m/pMin`) was established (ROADMAP N3).

## The hard part - what AMR breaks

Everything downstream assumes a mesh whose structure is known in advance and
CONSTANT for the whole run. With AMR the cell count and cell ordering change
every `refineInterval` steps, so:

1. `spec.remap` is built once from `0/C`. Under AMR it must be rebuilt PER
   WRITTEN TIME. Establish where the per-time structure comes from -
   candidates: a `writeCellCentres` function object firing every write (then
   each time dir carries its own `C`); `dumpLevel` writing a `cellLevel`
   field per write (then the structure follows from the base grid plus that
   field, which is much cheaper); or the `polyMesh` OpenFOAM writes per time
   for a changing mesh. Measure the cost of each per write - this is the
   decision the whole design hangs on.
2. `reader.to_grid` takes the remap from `spec`; it needs a per-time remap.
3. `_decode_surface` (live slice) uses `spec.remap[live_sl]` - same problem,
   and the sample's row count changes per write.
4. `runloop.PeakImpulse` accumulates p_peak/impulse on the DISPLAY grid, so
   it keeps working - but verify blastFoam's own `pMax`/`impulse` function
   objects survive mesh changes (OpenFOAM maps fields on refinement; check
   whether the values are mapped or reset).
5. `postmortem.load_run` rebuilds the remap from `0/C`; it needs the same
   per-time path, from whatever the run left on disk.
6. Snapshots/frames live on the finest uniform grid
   (`dx_base / 2**maxRefinement`) - the memory cap that `validate_case`
   already applies to static refinement must apply here too, using
   `maxRefinement` instead of the zone levels.
7. Parallel runs: AMR redistributes cells; check whether `reconstructPar`
   still yields the serial ordering the ingest assumes, and whether load
   balancing needs any of the keys above.
8. "Show mesh": with a static mesh the overlay is predicted before the run.
   Under AMR the mesh differs per frame, so the overlay must come from the
   frame being displayed (the per-time structure of item 1), or be disabled
   for AMR runs. Decide and say which.
9. Case schema + GUI: new fields (AMR on/off, `maxRefinement`,
   `refineInterval`, estimator + its thresholds, `maxCells`,
   `nBufferLayers`), `validate_case` rules (blastFoam-only, caps on the
   display grid, interaction with the existing `refine_zones` /
   `charge_refine` - can a case have both? decide), the Numerics form, and
   the validation notes.
10. Everything must be inert when AMR is off: same goldens, same baseline,
    same logs.

## Deliverables

A plan (then, after approval, the implementation) split into sessions in the
TASKS.md style, each ending green, with:
- the per-time structure mechanism decided and MEASURED (cost per write on a
  real case, not an estimate);
- writer/backend/reader/runloop/postmortem changes;
- case schema + validation + GUI + display decisions;
- tests: unit tests for whatever replaces `match_cells` per time, writer
  goldens for an AMR case, a headless GUI check, and a WSL e2e
  (`_e2e_foam_amr3d.py`) comparing an AMR run against a uniform-fine
  reference: gauge peaks and arrival times within a stated tolerance, cell
  count over time logged, wall-time saving reported;
- ROADMAP: N15's AMR follow-up and the "Nice-to-have" AMR bullet updated
  with the measured numbers; TASKS.md rows.

## Questions to ask me before finalising the plan

1. Which error estimator should be the default (`Lohner` on pressure is the
   usual choice for blast) and what thresholds - or should the plan pick by
   measurement on a test case?
2. Should AMR and the existing static zones be mutually exclusive, or should
   zones set a refinement FLOOR that AMR may add to?
3. Is a wall-time saving the goal, or accuracy at equal cost? That decides
   what the e2e compares against.
4. How much memory may the display grid take (today's cap is the native
   solver cap, and it is what limits `maxRefinement`)?
5. Should the run report AMR activity in the log (cells per write, refine
   events), and should "Show mesh" follow the frame or be disabled for AMR?

Start by reading ROADMAP N15 and `core/refine.py`, then probe the WSL
install for the per-time structure question (item 1) - that answer shapes
everything else.
```
