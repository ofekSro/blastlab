# Batch 2026-09-27 · out-2-vtk-output

**Goal (one sentence):** a blastFoam run can write VTK files for ParaView (sections and obstacles, volumes, or both) straight into `<MODEL>\vtk\`. The fields and the cadence (simulated ms or solver steps) are chosen per case on a Viper-style card, and each WSL time directory is deleted once its conversion has been copied and verified (`OUT-2`, [model-folder-and-vtk-plan.md](../model-folder-and-vtk-plan.md) §3).

- **Branch:** `out-2-vtk-output` in the OneDrive copy, based on master `c73d4fc` (OUT-1 is merged and accepted).
  - Do not touch `C:\Users\rotem.ofek\blastlab-worktrees`.
  - `docs/references/INDEX.md` (modified) and `ViperTheoryManual_Client.*` (untracked) belong to another session. Stage files by name; never `git add -A`.
  - git is the MinGit path in CLAUDE.md §3, run with `-c gc.auto=0`. Commit, never push.
- **Binding:** plan §1 (decisions 1-7, 11, 12), §3, §7 (gates), §8 (what is not changed), §9 (the Viper screens).
- **Built on OUT-1:** `services/model_folder.stage_solve` / `write_all` / `new_manifest` (already carries `vtk: null`) / `copy_foam_skeleton` / `verify_and_release_scratch`; `jobs.register_stage_folder`; the `('folder', …)` queue message.
- **References:** **blastfoam-guide** (`docs/references/BlastFoam_User_Guide.txt`).
  - sec. 15 p. 122: the `functions` entry; the sampling library is loaded by default.
  - 15.2 p. 123: fieldMinMax.
  - **15.5 p. 124: the vtkTimeSeries surface writer.**
  - 15.10-15.12 p. 126: overpressure, impulse, timeOfArrival.
  - 16.2 p. 132 and 16.3 p. 133: blastToVTK and createTimeSeries, i.e. the `.vtk.series` format.
  - 16.9 p. 136: parallel AMR cannot be reconstructed.
  - The tutorial `building3DWorkshop/system/controlDict` was read in WSL, read-only.
  - Cite "blastFoam User Guide v6.0, sec. 15.5 (p. 124)" in the writer comments.
- **Total size: XL** (3 × S, 7 × M, 3 × L).
  - Checkpoint 1 after Step 3: keys and writer only, nothing deleted.
  - Checkpoint 2 after Step 7: everything headless.

---

## 0. Pre-flight (before any step that builds a GUI) · CLAUDE.md §8.2

1. `python -c "from blastlab.core import settings as s; d=s.load(); print(s.config_path(), d['auto_cleanup'])"` must print `False`. Do **not** call `env.auto_cleanup(...)` as a check: it deletes.
2. Offscreen suites keep `BLASTLAB_SETTINGS` pointing at the throwaway file from `ui/testing.private_settings`, which has its own private `runs_dir`.
3. `cd blastlab/tests; python test_regression.py` must be green **before the first commit**. That run is the byte-identical baseline.

## 0a. Where the plan and the code disagree (resolution proposed, plan not edited)

| # | Plan says | Code says | Resolution in this batch |
|---|---|---|---|
| D1 | §3.5: the Results snapshots are "taken from memory during ingest - 1D from the `store`, 3D under the explicit memory bound", so a deleted time dir never removes a snapshot | **Only 1D snapshots are in memory** (`backend.py:1131-1139`). `finalize_1d` still re-reads the final dir and the arrival-pin dir from disk (`:1097-1128`). `finalize_2d` re-reads **every snapshot dir** (`:1548-1553`), the final dir (`:1542`), the pin (`:1627-1634`) and the trigger dir (`:1645-1650`). Its pin search reads `p` from each write of the quiet prefix (`arrived_2d :1614-1625`, `_arrival_pin :554-563`), so a missing dir makes it hand the **last** write to the chain without a word. `finalize_3d` is a "two-pass snapshot re-read" (`:2162-2163`) of every snapshot dir (`:2189-2194`) and the final dir (`:2183`). `_final_read` falls back to the previous write (`:480-505`). | The deletion plan takes a **`protected`** set, which the backend fills during ingest (Step 7). It holds the snapshot dirs, the 1D/2D arrival-pin candidate, the 2D trigger dir, and the **two** newest writes. For 2D, an `arrived` cache is filled in `on_frame` from the `p` that is already read, and it is consulted **only when a dir is gone**, so a run without VTK behaves exactly as today. This file:line table goes into the `VtkExport` docstring (the V3 criterion). |
| D2 | §3.6: `sections\<plane>\t_<time>.vtk`, one file per time holding all fields | blastFoam's `vtkTimeSeriesSurfaceWriter.C` writes **one file per field per surface**, `postProcessing/<fo>/<time>/<field>_<surface>.vtk`, plus `<field>_<surface>.vtk.series` beside the time dirs. OF-9's plain `vtk` writer does the same. | Layout `vtk\sections\<plane>\<field>\t_<time>.vtk`, with one `<plane>_<field>.vtk.series` per field. Obstacles likewise. Volumes (`foamToVTK`) keep one file per time with all fields, as in §3.6. **Q1** |
| D3 | §3.2: separate *Sections* and *Obstacles* columns | §3.3 has one `vtk_surfaces.fields` list, and §3.4 has one `surfaces` function object, which has one `fields` list | The keys follow §3.3 exactly. The matrix has one column: *Sections & obstacles* in 3D, *Obstacles* in 2D. **Q2** |
| D4 | §3.2: every quantity in every dimension | `overpressure`, `impulse`, `pMax` and `timeOfArrival` are emitted only for `dim >= 2` (`writer.py:847,873`). `impulse` and `pMax` are also absent on a resumed AMR leg (`fo_accumulators`). A real 1D time dir holds `T U alpha.expl p rho rhoE …`; a 3D one holds all ten. | 1D shows six rows. Validation refuses the other four in 1D. The writer drops `pMax` / `impulse` when `fo_accumulators` is off, and logs one line. |
| D5 | §3.4: surfaces in Time mode use `writeControl adjustableRunTime` | OF-9 `timeControlFunctionObject.C:154-166`: a function object with `adjustableRunTime` **clips the solver's deltaT** to land on its own times, which changes the solve | Surfaces in Time mode use `writeControl runTime`, which samples at the first step past each multiple and leaves dt alone. Step mode uses `timeStep`. Surfaces never alter the solve. |
| D6 | V6: gauges, snapshots and animation "identical to the same run without export" | The volumes cadence **is** the solver's write schedule (§3.4). Snapshots, frames and the Python accumulators are built from the writes, and `adjustableRunTime` writes clip dt. | V6 is split (Step 11). (a) Surfaces only vs no export: byte-identical. (b) Volumes with deletion vs the same keys with deletion disabled, serial, adaptive off (B23 makes that bit-reproducible): byte-identical. (c) Volumes vs no export: peak, positive-phase impulse **and** arrival against a pre-registered threshold (**Q7**). |
| D7 | §3.1: the plane table is "the `points`-style field the form already renders" | `PointList` accepts numbers only (`ui/fieldform.py:108-227`, `_is_number`), and so does the Tk `_PointList`. The axis is a letter. | `PointList(..., kinds=('axis','float'))`, an optional per-column parser. Existing callers are unchanged, and the Tk twin gets the same. |
| D8 | §3.5 step 3: delete `<scratch>/<t>` and its `processor*/<t>` through `purge_paths` / `delete_decomposed` | `purge_paths` builds **only** `processor<N>/<t>` paths and refuses `n_procs < 2` (`runloop.py:242-265`) | New `time_dir_paths(case_posix, n_procs, names)`: the root `<t>` plus every `processor<N>/<t>`, with the same guards. `rm_scripts` chunking is reused. `purge_paths` is untouched, so `test_write_budget` is unchanged. |
| D9 | (gap) | Serial AMR writes a `polyMesh/` into the time dirs where the mesh changed, and a later write without one resolves to the newest older instance | A dir holding `polyMesh/` is deleted only if the next newer kept dir also holds one. |
| D10 | (gap) | `resume_run` "replays every write already on disk" to rebuild accumulators, snapshots and frames (`backend.py:769-777`), and so does the W3 auto-resume (`:901-916`) | Protected dirs survive, so snapshots survive. Frames from before a resume, and on AMR the Python peak/impulse, cover only the writes that are left. The log and `vtk\manifest.json` say so (`replay_incomplete`). **Q5** |
| D11 | (gap) | `model_folder.skeleton_script` hashes all of `postProcessing/` (`model_folder.py:767-781`) | Prune `postProcessing/vtkSurfaces` from the listing and from `in_skeleton`. The sweep owns those files, and blastFoam's own series is not copied. |
| D12 | (gap) | The run loop is in `solvers/`, and `test_layering` forbids solvers → services, so it does not know the model folder | `RunHooks.vtk_dir = None`, next to `scratch_posix` (`hooks.py:104`). `stage_solve` sets it to `<stage>\vtk`. With no folder (`stage_dir=None`, the headless tests) the export is **inactive**: one log line, nothing converted, nothing deleted. |
| D13 | (gap) | One lap of `_ingest_ready` already takes up to ~12 s and starves the live view (`runloop.py:1037-1048`). A blocking `foamToVTK` per write would make that worse. | An **asynchronous** converter: one `foamToVTK` at a time over several times (`-time 't1,t2'`), run as `Popen` plus a pump thread like `runner.run_stage_stoppable`, polled once per lap. The final sweep waits for it with a bound. |
| D14 | §3.5: `foamToVTK -time t -fields (…) -poly -useTimeName` | Without extra flags `foamToVTK` also writes a file per **patch** and point-interpolated copies of every field (`foamToVTK -help`) | Add `-noFunctionObjects -noFaceZones -noPointValues -excludePatches '(".*")'`. The exact argv is pinned by a test and checked on the machine (§7). The Results button (`export_vtk.VTK_CMD`) is **not** changed (§8). **Q6** |
| D15 | "a new **Output** card" | The Setup tab already has an **Outputs** card | Title the new card **VTK output (ParaView)**. |

---

## 1. Tasks, in order

Commit style: `out-2: <what changed>`. Each step leaves the app runnable. **Nothing is deleted in WSL before Step 6.** Until then the keys change only the dictionaries.

### Step 1 · V1a · Case keys, save / load · **S**

- `models/case.py` gets `vtk_volumes: dict = None` on `Case1D`, `Case2D` and `Case3D`, and `vtk_surfaces: dict = None` on 2D and 3D only. 1D has no sections or obstacles, so a 1D file carrying `vtk_surfaces` is refused with "Unknown case keys", the same way `write_budget` is.
- `case_to_dict` drops a key that is `None` or `{"on": false}`, next to the `write_budget` pop (`:358`). `VERSION` stays 13.
- `case_from_dict` normalises `planes` to `[[axis, float]]` and `fields` to a list of str. `value` is **ms** in Time mode (§3.3/§3.4, **Q3**) and an int in Step mode.
- **Tests:** new `tests/test_vtk_case.py`, part A.
  - Default `Case1D/2D/3D()` save byte-identical to files written at `c73d4fc`.
  - An `on` round trip keeps every key.
  - `on: false` is not written.
  - `Case1D` refuses `vtk_surfaces`.
  - `test_char_case_json`, `test_write_budget` and `test_case_validate` pass unchanged.

### Step 2 · V1b · Validation · **M**

- `services/validation._validate_vtk(case, rep, ctx)` runs at the end of `_validate_1d`, and after `_validate_caps` for 2D/3D, where `rep.run_plan` gives the effective ranks (`:1143`).
- **Errors**, each naming its family:
  - `value <= 0`, or a Step value that is not a whole number;
  - `mode` not in `time|step`;
  - a field the dimension does not have (D4), or an unknown field;
  - a plane axis not in `x y z`, or a position not strictly inside `(0, L_axis)`;
  - two planes that snap to one cell layer;
  - planes in 2D;
  - 2D surfaces on a case without obstacles ("nothing to sample");
  - `vtk_volumes.on` together with `write_budget > 0` ("both pin the write interval - clear one");
  - volumes on a parallel AMR case (the same test as `:453`, with the §3.5 text).
- **Notes:**
  - Native mode: "VTK output is a blastFoam setting - the native solver ignores it", as at `:423-426`.
  - Time-mode volumes: the write count and a disk estimate (`t_end / value × BYTES_PER_CELL_WRITE × cells`), and a reminder that every write is ingested, so a dense cadence slows the live view.
- **Tests:**
  - `test_vtk_case.py` part B: one case per refusal, plus the native note.
  - `test_case_validate`, `test_char_validation` and `test_write_budget` pass unchanged.
  - The pre-existing `test_hd13_starter_case` failure is recorded, not fixed.

### Step 3 · V2 · Writer · **M**

- `writer.CaseSpec` gains `vtk_surfaces`, `vtk_volumes` and `write_steps=0`. `_apply_vtk(spec, case)` runs in `plan_case` after `_apply_budget`; in 1D it runs before the early `return` (`:409-411`). It acts only when `solver == 'blastfoam'`.
- **Volumes** (`_controldict_time`):
  - Time mode: `writeControl adjustableRunTime` (`runTime` when `fixed_dt` is set, `:787-791`), `writeInterval = value / 1000`.
  - Step mode: `writeControl timeStep`, `writeInterval N`, `spec.write_steps = N`.
  - Both: `spec.adaptive_write = False`; the `writeTimes` function object (T62) is kept.
  - The backend's "Write interval" log lines (`:635`, `:1304`, `:1907`) and `hooks.cadence` report the steps in Step mode.
- **Surfaces:** `_controldict_vtk_surfaces(spec, case)` is the **last** `functions` entry, after the probes, so every accumulating function object has already run in that step. It writes `vtkSurfaces { type surfaces; libs ("libsampling.so"); surfaceFormat vtkTimeSeries; writeControl runTime|timeStep; writeInterval <s>|<N>; interpolationScheme cell; fields (…); surfaces (…); }`.
  - The live-slice plane comes first (`slice_axis` / `slice_pos`, or the burst point when blank), then the table rows.
  - Each plane is `slice_<axis>_<pos:.2f> { type plane; planeType pointAndNormal; pointAndNormalDict {…}; interpolate false; triangulate false; }`. The type is `plane`, the sampler the live slice already runs on this build (`:956-962`), not the tutorial's `cuttingPlane`.
  - Positions are **snapped to the nearest cell-centre layer** with the live slice's own code (`:933-947`). That code moves into a helper that the live slice then calls, so its output is unchanged. The plane name keeps the position the user asked for (**Q6**).
  - `obstacles { type patch; patches (obstacles); triangulate false; }` is written only when `('obstacles', 'wall')` is in `spec.patches`.
- **Tests** (`test_foam_writer.py` additions):
  - Every existing golden stays byte-identical.
  - A 3D case with both families on is checked line by line against the dictionary above, guide §15.5 and the tutorial:
    - the entry is last;
    - Time-mode (seconds) and Step-mode controls;
    - snapped planes;
    - the obstacles entry, present and absent;
    - the top-level volumes controls;
    - `writeTimes` still there.
  - 1D volumes.
  - `fo_accumulators=False` drops `pMax` / `impulse`.
  - `test_write_budget` passes unchanged.

**Checkpoint 1:** run the §3 fast gates. A case without the keys is byte-identical everywhere.

### Step 4 · V3a · The pure deletion plan · **M**

- New `solvers/foam/vtk_export.py`: no Qt, no services, no `backend` import.
- `vtk_purge_plan(done, converted, copied_ok, newest_complete, start_dir, reconstructed, protected=(), n_procs=1, mesh_dirs=frozenset(), ordered=())` returns the names to delete, sorted by time. It is **pure**. A name is deletable only when all of these hold:
  - it is in `done ∩ converted ∩ copied_ok`;
  - in parallel, it is also in `reconstructed`;
  - it is not `'0'`, not `start_dir` and not in `protected`;
  - it is older than the two newest complete writes;
  - the D9 rule allows it.
- **Helpers:**
  - `time_dir_paths` (D8);
  - `vtk_argv_script(names, fields)`, the D14 command line;
  - `surface_sweep_plan(listing, final)`: every `postProcessing/vtkSurfaces/<t>/` except the newest, which may be mid-write, during the run, and all of them at the final sweep;
  - `dest_name(kind, surface, field, time)`: the D2 layout, with OpenFOAM's own time names (`t_0.0005.vtk`), never reformatted.
- **Tests:** new `tests/test_vtk_export_plan.py`, part A.
  - The full decision table: every exclusion alone and together.
  - A failed copy deletes nothing.
  - The two newest writes, `0`, a resume's start dir and a protected name all survive.
  - A parallel time that is not reconstructed survives.
  - The D9 AMR chain.
  - `time_dir_paths` refuses the runs root, `..`, a nested path, `constant` and `-1`, and builds the root plus `processor0..N-1`.
  - `rm_scripts` chunking at 60 writes × 13 ranks.

### Step 5 · V4 · `.vtk.series` and `vtk\manifest.json` · **S**

- New `output/vtk_series.py`. Every file export goes through `output/`, and solvers → output is allowed.
  - `write_series(folder, name, entries)` writes ParaView's `{"file-series-version": "1.0", "files": [{"name": "t_0.0005.vtk", "time": 0.0005}, …]}`: sorted by time, relative names, UTF-8 without BOM, `\n`, written atomically (tmp + `os.replace`) so ParaView never reads half a file.
  - `write_vtk_manifest(vtk_dir, state)` writes `{fields, cadence{mode,value,unit}, families{volumes|sections|obstacles: {count, times, series}}, not_converted: [{time, why}], deleted_in_wsl, replay_incomplete}`.
- `model_folder.write_all` fills the root manifest's existing `vtk` key with `{dir: "vtk", counts, not_converted}`. It is additive, and stays `null` without export.
- **Tests:** new `tests/test_vtk_series.py`.
  - A `json.load` round trip.
  - Ordering by float time (`1e-05` before `0.0001`).
  - A rewrite after one more time keeps the earlier entries.
  - No BOM.
  - An interrupted write leaves the old file whole.
  - `test_model_folder` passes unchanged (`vtk: null`).

### Step 6 · V3b · The `VtkExport` executor in the run loop · **L**

- `vtk_export.VtkExport(spec, hooks, fields, delete=None, runner=None)` is active only when a key is on **and** `hooks.vtk_dir` is set (D12).
- On construction it reads the existing `<vtk_dir>\manifest.json` and the listing, so a W3 auto-resume (a new loop with the same hooks) never exports a time twice.
- `run(done, final)`, in order:
  1. Start or poll the async converter (D13) for ingested times that are not yet converted.
  2. Copy `VTK/<case>_<t>.vtk` to `vtk\volumes\t_<t>.vtk`, check size > 0, and delete the WSL file.
  3. Delete the planned time dirs through `time_dir_paths` + `rm_scripts`.
  4. Sweep the surface files: copy, verify, delete in WSL.
  5. Rewrite the series and the manifest.
- **Failures:** a `foamToVTK` or copy failure logs **one** line per kind, keeps the time dir and is retried once. After that the time goes into `not_converted`. Nothing raises, and the run is never stopped by its export (§3.5).
- **The final sweep** converts everything ingested, protected writes included, but deletes only what the plan allows. It waits for the converter up to `max(600 s, n_cells / 1e3 s)`, with one log line per minute.
- **`FoamRunLoop`:** `self.vtk = VtkExport(...)` next to `self.purge` (`runloop.py:957`). `_ingest_ready` calls it after `_purge_decomposed()`, so it runs after every pass and on the final sweep (`:1112`). A class default `vtk = None` keeps loops built with `__new__` working, as `purge` does (`:918-920`).
- **Hooks:** `solvers/hooks.RunHooks.vtk_dir = None`. `model_folder.stage_solve` sets `hooks.vtk_dir = <stage_dir>\vtk` before `make_solve` for a blastFoam case with a key on, and restores it in `finally`.
- **Model folder:** the D11 prune. `write_all` adds each `not_converted` time to `manifest['failed']` (`{name: 'vtk', path, why}`), so `release_decision` **keeps the scratch** (**Q4**). A stopped or failed run keeps its scratch anyway (§2.3).
- **Tests:** `test_vtk_export_plan.py` part B, on a fake scratch tree in a temp dir, with the converter, copy and delete injected.
  - The happy path: files in place, series listing them, exactly the planned dirs deleted.
  - A converter failure or a 0-byte copy deletes nothing, and `not_converted` names the time.
  - Inactive without `vtk_dir`: no converter call and no delete.
  - A second `VtkExport` on the same folder does not convert twice.
  - The newest surface dir is left until the final sweep.
  - `test_model_folder` part D gets two cases: `not_converted` keeps the scratch, and the skeleton omits `postProcessing/vtkSurfaces`.
  - `test_foam_resume`, `test_write_budget`, `test_char_meta` and `test_char_native_api` pass unchanged.

### Step 7 · V3c · The backend protects what finalize reads (D1, D10) · **M**

- **1D** `on_frame`: `loop.vtk.protect(name)` for the arrival-pin candidate. That is the newest write with `p[-1] <= ARRIVAL_P`, the same predicate `finalize_1d` uses (`:1119`), frozen at the write before the first written arrival. The previous candidate is unprotected.
- **2D** `on_frame` (`:1397-1418`):
  - `protect` every name appended to `snap_names`;
  - `protect` the pin candidate, using `arrived_2d`'s boundary test on the `p` already in hand;
  - `protect` the trigger's `time_dir` when the action contains `remap`;
  - store `arrived_cache[name]`. `arrived_2d` reads the cache **only if the dir no longer exists**.
- **3D** `on_frame` (`:2040-2044`): `protect` each `snap_names` entry. 3D has no pin and no remap state (`:2165-2166`).
- **Resume:** when `resume_run` finds fewer writes than the `vtk` manifest converted, it logs one line and sets `replay_incomplete` (D10).
- **Tests:** new `tests/test_vtk_protect.py`, on a fake finalize tree (as the postmortem tests build).
  - Delete every **unprotected** dir, then run `finalize_1d/2d/3d`. The snapshot labels and arrays, the pin time and `final_state` must equal those of the same tree with nothing deleted.
  - Without deletion, the output equals the output before the change.
  - `test_regression` is byte-identical.

**Checkpoint 2:** everything so far is headless. Run the §3 fast gates plus all 14 `test_gui_*` (`solvers/`, `services/` and `output/` changed).

### Step 8 · V5a · Qt card · **L**

- `ui/setup_spec._vtk_card(dim)` returns `CardSpec('VTK output (ParaView)', col=1, scope='blastfoam')`, placed right after `_outputs(dim)`.
- **Families (§3.1):** 1D *Whole domain* (volumes). 2D *Whole domain* (volumes) and *Obstacles* (surfaces). 3D *Sections and obstacles* (surfaces) and *Volumes*.
- **Per family:** `vtk_<s|v>_on` (bool), `vtk_<s|v>_mode` (new kind `'radio'`, Time / Step), `vtk_<s|v>_ms` (`Every [ms]`) and `vtk_<s|v>_steps` (`Every [steps]`).
- **3D only:** `vtk_planes`, kind `points`, cols `('axis', 'position [m]')`, kinds `('axis', 'float')` (D7), 3 rows. The caption says the live-slice plane is always included.
- **The matrix** (new kind `'matrix'`):
  - rows are the dimension's quantities (D4);
  - columns are `Gauges | Sections & obstacles (3D) / Obstacles (2D) | Volumes` (D3);
  - the value is `{'surf': [...], 'vol': [...]}`;
  - the Gauges column shows p / rho / U ticked and disabled (decision 4).
- **`ui/fieldform.py`:** the `'radio'` and `'matrix'` widgets, and `PointList(kinds=…)`. `set_enabled` greys the inactive cadence box (as Viper does); this card is the one place where greying is right. The whole card is hidden, never greyed, in native mode (`apply_scope`).
- **`ui/case_form.py` hooks:**
  - a mode change greys the other box;
  - the first tick of a family fills its defaults (surfaces `p`, `pMax`; volumes `p`, `rho`, `U`, per §3.1);
  - unticking a family keeps its ticks.
- **`models/fields.py`:** `case_from_fields` reads the keys only in blastFoam mode with the family on, and gives `None` otherwise (the hidden-in-native rule, `:352-354`). A bad `ms` / `steps` value is reported only for the active mode. `fields_from_case` restores everything, including the planes and the mode.
- **Tests:** new `tests/test_ui_output_card.py` (offscreen).
  - The card shows the right families and matrix cells in each dimension.
  - Native mode hides the card, and the case has no key.
  - Time / Step greys the other box.
  - The first tick fills the defaults.
  - A plane row `q, 1` is refused and `y, 1.4` is accepted.
  - Form → case → JSON → form is identical.
  - A bad value in the inactive box never blocks a run.
  - `test_ui_setup_form` passes. `test_ui_parity` passes once Step 9 has landed.
  - `test_ui_char_case_form.py --update` goes in **its own commit**. Read the diff line by line: added rows only (decision 1 authorises the card).

### Step 9 · V5b · Tk card (CLAUDE.md §9) · **M**

- `gui/forms.py` builds the same card imperatively after the Outputs card. In 1D it is the first right-column output card, because 1D has had no Outputs card since OUT-1 (`:569-570`).
- Widgets:
  - a `CTkCheckBox` per family;
  - a `CTkRadioButton` pair sharing one `StringVar`;
  - the two entries, the inactive one at `state='disabled'`;
  - a `_PointList` with an axis column;
  - the matrix as a grid of `CTkCheckBox`es, with the Gauges column disabled.
- The card is registered in `_scoped['blastfoam']`, and the values go through the same `models.fields` mapping.
- **Tests:**
  - `test_gui_char_case_form.py --update` in its own commit, added rows only.
  - `test_ui_parity` green: the same field names in both toolkits.
  - All **14** `test_gui_*.py`. `P2-8` may hang `test_gui_run_browser`: record it, do not fix it.

### Step 10 · V5c · Harness scenarios · **M**

- `_qa_ui_harness.py`, new group `V`:
  - `V01` the 1D card in blastFoam mode;
  - `V02` 2D with and without obstacles (the strip says "nothing to sample");
  - `V03` the 3D matrix, plane table and Time/Step greying;
  - `V04` native mode hides the card, and a saved case has no `vtk_` key;
  - `V05` a finished, **stubbed** foam stage with a fake `vtk\` tree gives a root manifest with a `vtk` summary.
- `_qa_gui_harness.py`: `V01`-`V04` for Tk.
- Run offscreen here. The real-window runs are in §7.

### Step 11 · V6 · Real tiny 3D run · **M** · needs the machine free (§7)

New `tests/_e2e_vtk_3d.py`: 3D, a few thousand cells, one obstacle box, one gauge, `t_end` ≈ 1 ms, serial, adaptive off. The pre-registered rules go into the script header **before** the first run.

1. **Surfaces only, Step mode, vs the same case without keys:** gauges **byte-identical**, snapshot arrays identical, animation frames identical.
2. **Both families on, vs the same keys with deletion disabled** (`BLASTLAB_VTK_NO_DELETE=1`, a test-only switch read by `VtkExport`):
   - gauges, snapshots and animation byte-identical, file by file;
   - file count per family = expected ± 1;
   - every `.vtk` > 0 bytes, and the series parse;
   - `not_converted == []`;
   - during the run WSL holds at most the protected dirs plus the two newest;
   - after release the scratch is gone and `foam\SHA256SUMS` verifies.
3. **Volumes vs no export:** peak, positive-phase impulse **and** arrival per gauge, within the Q7 threshold. Never peak alone.
4. **A stopped run:** the scratch is kept, the converted files are in place, and the series are valid.

### Step 12 · V7 · Gates and GUI QA · **M**

Run §3 in full. Then `gui-qa-tester` (the owner's agent, not a stand-in), with screenshots of:
- the Qt card in 1D, 2D and 3D, in Time mode and in Step mode;
- native mode, where the card is hidden;
- the Tk card in 3D;
- the finished run's `vtk\` folder listing.

### Step 13 · V8 · Docs · **S** · editor tools only (§4)

- `blastlab/README.md`, "Where a run's files go": the `vtk\` layout (D2), the card, the cadence units, what is deleted in WSL and when, the parallel-AMR limit, and how to open a series in ParaView.
- `DONE.md`: an `OUT-2` entry in the §0c style.
- `TODO.md`: the `OUT-2` row ticked, marked "owner acceptance pending".
- Never rewrite either file wholesale.

### Step 14 · V9 · Owner acceptance

The owner runs a real case, opens the series in ParaView, and says "fixed and approved". Fixes go in `out-2: fix …` commits, each re-verified by the step that owns it. `OUT-5` waits until then.

---

## 2. GUI screens touched

| Screen | Change | Toolkit |
|---|---|---|
| Setup → new card **VTK output (ParaView)**, blastFoam mode only | families per dimension, enable boxes, Time/Step radios with greying, ms / steps boxes, plane table (3D), quantity matrix with a locked Gauges column | Qt + Tk |
| Setup → validation strip | the new VTK refusals and notes | Qt + Tk |
| Run log | export lines (converted / copied / deleted / not converted), at most one per kind per lap | both, through the hooks |

## 3. Gates (CLAUDE.md §6/§9, plan §7)

- **Regression:** `cd blastlab/tests; python test_regression.py` must be **byte-identical**. Run it first and after every step. No native path changes, so any difference means stop.
- **Writer:** `python test_foam_writer.py`. Every existing golden is unchanged; only the new VTK assertions are added.
- **The fast matrix:**
  - validation: `test_case_validate`, `test_char_validation`, `test_char_case_json`, `test_write_budget`;
  - foam and exports: `test_foam_env`, `test_foam_resume`, `test_char_exports`, `test_char_meta`, `test_char_native_api`;
  - OUT-1: `test_model_folder`, `test_run_preflight`;
  - Qt: `test_ui_setup_form`, `test_ui_parity`, `test_ui_char_case_form`, `test_ui_results`, `test_ui_drain`;
  - layering: `test_layering`, `test_ui_no_vtk_in_main`, `test_ui_no_mpl_pyplot`. The new modules copy bytes and never `import vtk` / `pyvista`.
  - new: `test_vtk_case`, `test_vtk_export_plan`, `test_vtk_series`, `test_vtk_protect`, `test_ui_output_card`.
- **Tk:** all **14 `test_gui_*.py`** and `_qa_gui_harness.py`, because `models/`, `services/`, `solvers/` and `output/` change.
- **Harness:** Qt `V01`-`V05` and Tk `V01`-`V04`, then `gui-qa-tester` with screenshots.
- **Pre-existing failures** (not this batch's): `test_foam_wsl_resume.py` (`init_state` on the fake spec) and `test_char_validation::test_hd13_starter_case`. Re-check them at the start and record them; do not fix them.
- **Re-pins:** only `test_ui_char_case_form` and `test_gui_char_case_form`, each in its own commit, whose diff shows added rows and nothing else.

## 4. Rules for the implementer (CLAUDE.md §8.1)

- **Never route a file's content through PowerShell strings.** Every edit uses Read/Edit/Write, including `TODO.md`, `DONE.md`, `README.md` and anything with `·`, `→`, `—`, `≥` or Hebrew. PowerShell may list, move and hash files.
- **Damage check:** `rg 'ג€|ג”'` over the touched files must come back empty.
- **Commit messages** containing `"` go to a file first, then `git commit -F msg.txt`.
- **WSL:** a bash script goes in a file in the scratchpad and runs with `wsl -d Ubuntu -e bash <path>`. Inline `$(…)` and `2>/dev/null` break inside PowerShell.
- **New Python** writes UTF-8 without BOM, `newline='\n'`.
- Never change a solver default, and never edit a committed test to make it pass.

## 5. Risks

1. **Deleting the record while a run is live.** Nothing in the repo does this today. Protection:
   - the pure, fully tabled `vtk_purge_plan` and the `time_dir_paths` guards;
   - a delete only after a size-checked copy;
   - `0`, the start dir, the two newest writes and every protected name are always kept;
   - the export is inactive without a model folder;
   - the Step 11 A/B with deletion disabled.
2. **Numbers must not move.** Cases without the keys are byte-identical (goldens, `test_regression`, `test_char_case_json`). With surfaces only the solve is untouched (D5). With volumes the write schedule is the user's choice, so it is compared on peak, impulse and arrival together.
3. **The chain hand-off (N2-13).** Deleting pre-arrival writes would move the 2D pin to the last write without a word. Protection: the pin candidate is protected, plus the `arrived` cache, and `test_vtk_protect` checks the pin time.
4. **Ingest and live-view latency.** Dense volumes mean many full-field ingests, and `foamToVTK` competes with the solver ranks. Protection: the async converter, one conversion at a time, and the validation note on the write count.
5. **The Windows disk.** Each volume file is roughly 100 B per cell per field. The Time-mode note gives an estimate. A copy that fails for a full disk keeps the WSL dir and the scratch (Q4).
6. **The run corpus (§8.2).** New tests use the private `runs_dir` and fake scratch trees. Only `_e2e_vtk_3d.py` makes a real run, and it makes its own.

## 6. Owner questions (each with the interpretation used if there is no answer)

**Owner answers, 2026-09-26 (binding):** Q1 - one series per field, each named after
its field (e.g. `p.vtk.series`, `pMax.vtk.series`), laid out so that in ParaView the
series load as a group per family and each field can be isolated. Q3, Q4, Q5, Q6, Q7 -
accepted as written below. Q2 - **separate field lists for sections and for obstacles**,
as Viper's Sections and Obstacles columns (spec §3.2): the matrix keeps two columns, the
case carries `fields` (sections) and `obstacle_fields` (obstacles), and the writer emits
two surface function objects (one per list, same cadence) so each list is honoured.

- **Q1 · One file per field (D2).**
  - *Used:* `sections\<plane>\<field>\t_*.vtk`, one series per field.
  - *Alternative:* merge the per-field files into one file per time on Windows (legacy VTK parsing, ~100 lines, more risk).
- **Q2 · One field list for sections and obstacles (D3).**
  - *Used:* the §3.3 keys unchanged, and one merged matrix column.
  - *Alternative:* an additive `obstacle_fields` key and two function objects, giving separate Viper columns (fits `OUT-4`).
- **Q3 · Units in the case JSON.** *Used:* the Time-mode `value` is stored in **ms**, as §3.3/§3.4 say, although every other time in the case is in seconds.
- **Q4 · A time that could not be converted keeps the WSL scratch.** *Used:* yes. It goes into `manifest.failed`, so `release_decision` keeps the scratch for a manual export.
- **Q5 · Resume after deletion (D10).**
  - *Used:* allowed. Snapshots survive. Frames, and on AMR the Python peak/impulse, cover only the remaining writes, as logged and recorded in the manifest.
  - *Alternative:* never delete on AMR runs.
- **Q6 · File content.** *Used:*
  - volumes with cell data only (`-noPointValues`) and no per-patch files;
  - section planes of type `plane` with `interpolate false`, so raw cell values and peaks are not smeared;
  - planes snapped to the nearest cell layer and named by the position asked for.
- **Q7 · The pre-registered threshold for Step 11 rule 3.** *Used:* per gauge, |Δpeak| ≤ 1 %, |Δ positive-phase impulse| ≤ 1 %, |Δarrival| ≤ 0.5 %. It is written into the script before the first run and never changed afterwards.

### Parked for the owner (2026-09-27, Steps 4-7; none blocks)

Each is the interim the code uses now; a different answer is a small change in `solvers/foam/vtk_export.py`.

- **P1 · Volumes keep one series.** `vtk\volumes\volumes.vtk.series` over `t_<time>.vtk`, each file holding every chosen field (D2, §3.6). Q1's one-series-per-field applies to the surfaces, where each file is one field; in ParaView each volume field is an array of the one series.
- **P2 · Where a surface series sits.** `vtk\sections\<plane>\<field>.vtk.series` and `vtk\obstacles\<field>.vtk.series`, listing `<field>/t_<time>.vtk` (a name relative to the series file). To confirm in the Step 14 ParaView check.
- **P3 · Per-family `fields` and `cadence` in `vtk\manifest.json`.** `fields: {volumes, sections, obstacles}`, `cadence: {volumes, surfaces}` (each `{mode, value, unit}`), because the two families have separate cadences. `not_converted` entries also carry `family` and `path` (additive).
- **P4 · The root manifest's `outputs` lists every file under `vtk\`.** `list_outputs` is unchanged, so a long run adds thousands of rows. The alternative is to leave `vtk/` out and rely on the `vtk` summary.
- **P5 · The final VTK sweep also runs after a failed solve** (converting what was ingested, with the bounded wait). The alternative is to skip it when the solver failed.
- **P6 · Surface samples at t = 0 are exported.** The surface function objects sample the initial state too (measured on this build).
- **P7 · A failed foamToVTK call over several writes is split.** The writes are converted one per call before attempts are counted, so one bad write does not give up a whole batch.
- **P8 · Export cadence.** Outside the final sweep, the export looks at the disk at most once a second (`EVERY_S`), and each foamToVTK call takes at most 8 writes (50 at the final sweep).

Added by the Checkpoint 2 verification (2026-09-27; none blocks):

- **P9 · 1D snapshots after a resume that follows deletion.** 1D picks its snapshots at finalize from the writes it holds (`backend._pick_snapshots`), so no write can be protected for them during the run. A resumed 1D run picks them from the writes that are left, and the log says so. Q5's "snapshots survive" holds for 2D/3D only. The alternative is to never delete time dirs on a 1D run (1D writes are small).
- **P10 · The final sweep after WSL went away (W3).** The loop learns that WSL died only after its final sweep. That sweep then tries foamToVTK against the dead distribution for up to `final_wait_s` before the auto-resume, and lists what it gives up on as not converted. The resumed export never retries a not-converted volume, so those times stay unexported. Nothing is lost: the scratch is kept (Q4). The alternatives are to skip the final conversion when the solver's tail shows the EIO signature, or to let a resumed export retry them once.
- **P11 · Readers of a finished run after deletion.** `postmortem.load_run` (`--load-foam-run`), the run browser's resume (see `P2-17`) and the Results "Export VTK" button read only the writes left in WSL. Frames, 1D snapshots and a manual foamToVTK cover fewer times. The pin, the arrival write and the 2D/3D snapshots are kept. The alternative is to have them read `vtk\manifest.json` and say how many writes are gone.

Added by Steps 8-12 (2026-09-27; none blocks - each is a one-line change in `models/fields.py`):

- **P12 · The card's defaults.** Time mode, `Every [ms]` = 1 (Viper's 0.001 s), `Every [steps]` = 25 (Viper's Step value), both families off. Loading a case without VTK keys puts the card back to these; a family that is on shows its own mode and value, and the other box keeps the default.
- **P13 · Short matrix headers.** `Gauge | Sect. | Obst. | Vol.` (1D/2D: `Domain` for the whole-domain volumes), rows `Peak pressure` (was `Peak overpr.`, renamed by the QA fix F1 below: `pMax` is absolute) and `Products`, with the full names as Qt tooltips. The full words did not fit one Setup column at the 1100 px minimum window (the first QA shots showed "Pressu" and "Obstacle"). The alternative is a card spanning both columns.
- **P14 · Step 11 rule 3 failed as registered, and why.** `_e2e_vtk_3d.py` (rules committed in `6328bbd` before the run): 36 of 38 checks pass. Rules 1, 2 and 4 pass in full, byte for byte. Rule 3 (C, VTK volumes every 0.1 ms, against A, no export) fails at the one gauge, 0.20 m from the centre of 20 kg TNT (Z ≈ 0.07 m/kg^1/3, 5.7 cm off the charge surface): peak +4.17 %, positive-phase impulse +4.85 %, arrival +0.43 % (limits 1 / 1 / 0.5 %). An exploratory run afterwards, not judged by any rule, shows the cause. A1 (no export, `write_budget = 10`, the same 10 writes) gives gauges **byte-identical** to C. So the export changes nothing beyond the write schedule it sets, and the difference is the time step that `adjustableRunTime` writes clip. A's default pinned schedule writes every 0.0041 ms (1,500 steps; C and A1 take 991), and the production default (`adaptive_write` on, 1,096 steps) differs from A by +16.6 % peak. The threshold is not changed. Interim: the code stays as plan §3.4 says (Time-mode volumes land exactly on their times and clip dt). Owner: (a) keep it, and accept that choosing a volumes cadence is choosing a write schedule (the validation note could say so); or (b) write Time-mode volumes with `runTime`, as the surfaces do (D5): dt untouched, and the write times become the first step past each multiple. (c) Separately: is a Q7 comparison at Z ≈ 0.07 meaningful, or should rule 3 use a mid-field gauge?

Added by the Steps 8-13 verification (2026-09-27; none blocks):

- **P15 · A family that is off keeps its ticks only until the case is saved.** Unticking a family keeps its matrix column on the card (Step 8), but `case_to_dict` drops a family with `on: false` (Step 1), so after save and reload that column is empty and the next tick fills the defaults again. The alternative is to write `{on: false, fields…}` for a family whose column is not empty, which changes the Step 1 rule that an off family is not written.
- **P16 · Step 11 rule 2e is the registered reading, not the plan's words.** The plan says WSL holds "at most the protected dirs plus the two newest" during the run; the rule committed in `6328bbd` also allows a write that is not yet converted and copied, because the converter runs behind the ingest by design (D13). After the final sweep the plan's stricter bound held (left `0`, the protected `0.0001`, and the two newest). Owner: confirm that reading.

### After the GUI QA pass (2026-09-27, `docs/qa/2026-09-27-out-2/qa-pass/QA_REPORT.md`)

Fixed in the follow-up batch (commits `out-2: qa - ...`; labels, tooltips, notes and docs only, no field, writer or number changed):

- **F1 · `pMax` is peak absolute pressure.** Row `Peak pressure`; the tooltip says it is the running per-cell maximum of the absolute `p` (blastFoam field `pMax`) and to subtract 101.325 kPa for overpressure. README and spec §3.2 row corrected.
- **F2 · Results tab after an OUT-2 export.** When the case dir is gone and `<MODEL>\vtk\manifest.json` exists, the VTK button is live, says "Written during the run: `<MODEL>\vtk` - N files (see vtk\manifest.json)", and opens that folder. Qt and Tk.
- **Confusions 3, 5, 6, 7, 8 and the `Vol.` tooltip (2).** No "OUT-4" on screen ("Gauges: fixed - pressure, density, velocity"); the live-slice note says "when Sections and obstacles is ticked"; the Time-mode volumes note says the cadence is the write schedule and can change the solution slightly (README, P14); Step-mode volumes get a size-per-write note and say the count depends on the step count; Energy / Products tooltips; `Vol.` tooltip "whole-domain output". Short headers unchanged (P13).

Parked (none blocks):

- **P17 · F3, Tk at the 1100x720 minimum: the right column is clipped** (`Ste`, half a `Vol.` column, cut strip rows). Pre-existing: native mode overflows the same way. `gui/forms.py` card widths vs the 13:7 split, fixed `wraplength=520`.
- **P18 · F4, Tk: a dimension switch keeps the old scroll offset, so the form goes blank.** Pre-existing (same on `master`); `SetupPanel._swap` does not reset `yview` / the scrollregion. OUT-2 makes the 3D form 51 % taller.
- **P19 · F5, Qt: the 3D native form has a blank tail** when scrolled to the end (the `QStackedWidget` takes its tallest page's height). Pre-existing; the card makes the tail longer.
- **P20 · Qt locked Gauge column in light mode** (V1): the locked unticked boxes are drawn white, the live ones grey, so the disabled column looks the more active one. Dark mode is weak but right.
- **P21 · Rejected plane text survives Open case** (V3): `ui/fieldform.py` `PointList.set` does not clear the entry, and the hint goes back to idle.
- **P22 · `[ms]` on the card vs seconds in the files and ParaView** (confusion 1): a typed 0.5 reappears as 0.0005. The alternative is one line on the card saying the files use seconds.
- **P23 · The write-budget clash is unreachable from the GUI** (confusion 10): the Qt form has no `write_budget` field and drops it on Open case. Pre-existing; the GUI half belongs to `P1-12`.
- **P24 · 2D column order** (confusion 2): the matrix runs `Obst. | Domain` while the family boxes run *Whole domain*, *Obstacles*.

### Owner decisions on the parked list (2026-09-27 morning, binding)

- **P14 → (b):** Time-mode volumes must NOT clip the solver's time step: write them with
  `writeControl runTime` (as the surfaces), accepting that each file lands on the first
  step past each multiple. Update the card note and README accordingly (the note about
  changing the solution goes; say instead that write times are the first step past each
  interval). Step 11's rules and thresholds stay as registered; re-run it and record.
- **P1 → keep** one volumes series holding all fields (pick the field in ParaView).
- **P9 → no deletion on 1D runs** (the export converts and copies, but 1D time dirs stay
  in WSL until the scratch is released).
- **P15 → keep a switched-off family's ticks in the case file** (write `{on: false, ...}`
  when the family has fields; the solver ignores it).
- **P22 → the cadence field is in SECONDS** (reverses Q3: the case stores seconds, like
  the rest of the form; label `Every [s]`), **plus** one line on the card that the files
  and ParaView show time in seconds.
- **P13 → wide card with full headers** (the card spans both Setup columns; full words
  Gauges / Sections / Obstacles / Volumes, Whole domain in 1D/2D).
- **P24 → align the 2D column order** with the family boxes.
- **P4 → the root manifest keeps only a numeric summary of `vtk\`**; the full list lives
  in `vtk\manifest.json`.
- **P11 → one warning line** in postmortem load, run-browser resume and the manual VTK
  button when writes were deleted after conversion (count + "see vtk\").
- **P20, P21 → fix now.** **P17-P19 → later** (TODO P2-19..21).
- **P5, P6, P7, P8, P12, P16 → accepted as written.**
- **P2 → confirmed or changed at the owner's ParaView check.** P3, P10, P23 stay parked.

## 7. Needs the machine free

**Check that `wsl -d Ubuntu -- pgrep -a blastFoam` is empty, and tell the owner first.** Copy any run you care about out of `/root/blastlab_runs` before anything that builds a GUI. Use `python -u`, no timeout, in the background.

- **A one-off check before Step 6 is finished,** on a throwaway tiny case (never an existing run):
  - the D14 argv writes one `VTK/<case>_<t>.vtk` and no patch dirs;
  - a tiny run with the Step 3 dictionary writes `postProcessing/vtkSurfaces/<t>/<field>_<surface>.vtk`, which confirms D2 on this build.
- `python -u _e2e_vtk_3d.py` (Step 11, rules 1-4).
- `python -u _e2e_model_folder.py` again, to show OUT-1 is unchanged without the keys.
- `python _qa_ui_harness.py --scenario V01,V02,V03,V04,V05` in a real Qt window (`QT_QPA_PLATFORM` unset), and `_qa_gui_harness.py` `V01`-`V04` for Tk.
- `gui-qa-tester` with screenshots (Step 12), then the owner's ParaView check (Step 14).

## 8. Remaining backlog (not in this batch)

- **V9 owner acceptance**, then **`OUT-5`**: the WSL disk rebuild (its six decisions are in `wsl-disk-reclaim-plan.md` §3).
- **`OUT-3`** (newest fields only): the same `vtk_purge_plan` with the conversion skipped, plus a "keep all fields" box on this card.
- **`OUT-4`** (the rest of the Viper matrix): gauge quantities, dynamic pressure, peak impulse, per-obstacle patches, decimation, and Q2's alternative if wanted.
- **`P2-17`** (resume and the run browser do not know the model) interacts with D10. It is not fixed here.
- The rest of `HD1` and P0-P4, in the order `TODO.md` gives.
