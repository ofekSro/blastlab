# Model folder, VTK output options, and the WSL disk — the approved plan

**Status:** approved by the owner on 2026-09-26, in a design conversation that
settled every open question below. **Priority: highest — the `OUT` track sits
above `HD1` in `TODO.md`.** Nothing in this file has been implemented yet.

**How to use this file.** `TODO.md` holds one entry per id (`OUT-1` … `OUT-5`)
and points here; this file is the specification the task planner, implementer
and verifier work from. Every decision here is the owner's; a change to one of
them is an owner decision, not an implementation detail. Cite the ids in commits
(`out-1: refuse to run without a model folder`).

Order of execution: **`OUT-1` → `OUT-2` → owner acceptance of the software →
`OUT-5`**, then `OUT-3` and `OUT-4` in the order the owner chooses.

---

## 0. The problem this solves

Two things came together on 2026-09-26:

1. **The WSL disk is 481 GB** and cannot be shrunk in place (see
   [wsl-disk-reclaim-plan.md](wsl-disk-reclaim-plan.md)). 428 GB of it is eleven
   blastFoam runs, three of which are 421 GB. The run corpus grows because every
   written time directory stays inside WSL, and the disk file never gives space
   back.
2. **A run's outputs are scattered.** The OpenFOAM case lives in WSL under a
   timestamp name, the VTK export is a manual button after the run, every other
   export goes through a file dialog, and the HD1.3 report lands beside the case
   file. Viper::Blast, which the owner uses as the reference for how a blast tool
   should present its outputs, has one *Output Options* tab per dimension and one
   model folder per run.

The plan: a **mandatory model folder on Windows** that receives everything a run
produces (`OUT-1`); a Viper-style **VTK output card** whose files go into that
folder while the OpenFOAM time directories are deleted as they are converted
(`OUT-2`); **only the newest fields kept in WSL** for every run (`OUT-3`); the
**rest of the Viper matrix** (`OUT-4`); and, once the software is accepted, the
one-time **rebuild of the WSL disk** (`OUT-5`).

---

## 1. Decisions (owner, 2026-09-26)

| # | Topic | Decision |
|---|---|---|
| 1 | VTK export | Optional. Off by default. Modes: off / surfaces and obstacles / volumes. A per-case checklist of fields. |
| 2 | Cadence | Both units selectable — simulated milliseconds or solver steps — set before the run, separately for surfaces and for volumes. |
| 3 | Quantities in the first version | Only what blastFoam already produces (ten fields, §3.2). |
| 4 | Gauges column | Shown, locked (p, rho, U), until `OUT-4` extends it. |
| 5 | Follow-ups | `OUT-3` and `OUT-4` are **mandatory**, not optional. |
| 6 | Scope of VTK | blastFoam only; native solvers untouched. |
| 7 | Sections in 3D | The live-slice plane always, plus a table of extra planes (axis, position). |
| 8 | Model folder | A runs folder and a model name are **mandatory before any run**. `<runs>\<MODEL>\` holds everything of that run and nothing else does. |
| 9 | Re-running an existing model | Overwrite, after a confirmation dialog. |
| 10 | Which runs | All of them: blastFoam, native, the 1D→2D→3D chain, the HD1.3 assessment, and the command line (required arguments). |
| 11 | Outputs written | All of them, always, no choice — except that an output which is itself a choice (the animation needs "Record replay frames") is written only when that choice was made; the manifest says when it is missing. |
| 12 | WSL scratch | The solver keeps running inside WSL. Deleted after a successful run once the copy is verified; kept when the run failed or was stopped. |
| 13 | Latest fields only (`OUT-3`) | Always on for every blastFoam run, with a "keep all fields" box for debugging. |
| 14 | Chain workspace box | Removed; the model folder replaces it. |
| 15 | Disk rebuild (`OUT-5`) | Only after the owner has run and accepted `OUT-1` + `OUT-2`. Its own six decisions are in `wsl-disk-reclaim-plan.md` §3. |
| 16 | Vocabulary | Hebrew replies say **רגשים** for gauges. |

---

## 2. `OUT-1` — the model folder

### 2.1 Behaviour

On the **Run** tab, next to the existing run-name box:

- **Runs folder** — path box + *Browse*. Remembered across sessions in the
  settings file as `runs_dir`. Example: `C:\Users\rotem.ofek\BLASTLAB_RUNS`.
- **Model name** — the existing run-name box (`run_panel.run_name`, today
  optional, "names this run in the Results picker"), now mandatory. Example:
  `MODEL`. Rules: trimmed; non-empty; a valid Windows folder name (no
  `\ / : * ? " < > |`, no trailing dot or space, not a reserved device name);
  at most 100 characters.
- **Run** refuses, with one clear message in the existing error dialog, when
  the folder box is empty, the folder does not exist, or the name is invalid.
  The refusal happens in the pre-flight, before anything is written anywhere
  (the same place the case validation refuses today).
- If `<runs>\<MODEL>\` already exists: a Yes/No dialog — *"MODEL already
  exists in <runs>. Overwrite? The previous run's files will be deleted."* Yes
  deletes the folder and starts; No cancels with nothing changed. A folder that
  cannot be deleted (a file open in ParaView) refuses with the OS error.
- The same rule applies everywhere a run starts:
  - the Qt Run tab (`ui/run_panel.py`, `ui/run_controller.py`);
  - the Tk Run tab (`gui/run_panel.py`, `gui/app.py`) — it already has the name
    box; the folder box is added; the Tk GUI stays a full equivalent
    (`CLAUDE.md` §9);
  - the chain panel (`ui/chain_panel.py`) — its *workspace* box is removed;
    the stages go under the model folder (§2.2);
  - the HD1.3 assessment panel and `--hd13`;
  - the command line: `--runs-dir DIR --model NAME` are **required** by
    `--cli`, `--hd13`, `--hd13-wall-export` and any other entry that produces
    output; the interactive prompt workflow asks for both before its first
    question. `--load-foam-run` and `--clean-foam-runs` do not start a run and
    take neither.

### 2.2 What lands in `<runs>\<MODEL>\`

Written at the end of every run, in this order, all through the existing
writers in `services/exports.py` and `output/` (nothing new is invented for a
format that already exists):

| Path | Content | Existing source |
|---|---|---|
| `MODEL.json` | the case exactly as run (after hidden-field stripping) | `core.case.save_case` |
| `run.log` | the console log of the run, as the Run tab showed it | the hooks log |
| `manifest.json` | see below | new |
| `gauges\gauges_<d>d.txt` | gauge TSV | export `tsv` |
| `gauges\gauges_<d>d_summary.csv` | per-gauge peak, arrival, impulse | export `summary` |
| `figures\*.png` | one PNG per snapshot, the full grid | export `pngs` |
| `fields\*.csv` | field CSVs | export `fieldcsv` |
| `report.html` | the HTML report | export `report` |
| `animation.mp4` or `.gif` | only when replay frames were recorded (decision 11) | export `gif` |
| `profile.txt` / `profile_2d.npz` | 1D / 2D profile | export `profile` |
| `foam\` (blastFoam only) | `system\`, `constant\` (with `polyMesh`), `0\`, `log.blastFoam`, `postProcessing\` (probes and live samplers), `SHA256SUMS` | the HD1-3d evidence-copy pattern, now automatic |
| `vtk\` (blastFoam only, `OUT-2`) | volumes, sections, obstacles | `OUT-2` |

Chain runs: `<MODEL>\1d\`, `<MODEL>\2d\`, `<MODEL>\3d\`, each with the table
above, plus the hand-off profiles at the model root (`handoff_1d_to_2d.*`,
`handoff_2d_to_3d.*`), replacing today's `chain_workspace`.

HD1.3 assessment: `<MODEL>\hd13_report.html` and `<MODEL>\hd13_loads\` (the
SBEDS CSVs), replacing today's `<case>_hd13.html` beside the case file.
`services/hd13.default_report_path` goes away; the model folder is the path.

`manifest.json` (one per run; stable keys, additive only):

```json
{
  "model": "MODEL", "runs_dir": "C:\\Users\\rotem.ofek\\BLASTLAB_RUNS",
  "created": "2026-09-26T14:30:00", "finished": "2026-09-26T15:55:12",
  "solver": "blastfoam", "dim": 3, "case_file": "MODEL.json",
  "git_commit": "01ab997", "stop_reason": "t_end",
  "n_cells": 864000, "n_procs": 13, "n_steps": 2311,
  "wsl_scratch": {"posix": "/root/blastlab_runs/20260926-143000_3d_p3756-00",
                  "deleted": true, "deleted_at": "2026-09-26T15:55:40"},
  "outputs": [{"path": "gauges/gauges_3d.txt", "bytes": 190240}],
  "missing": [{"name": "animation", "why": "replay frames were not recorded"}],
  "vtk": null
}
```

### 2.3 The WSL scratch

- The solver still runs in `/root/blastlab_runs/<stamp>_<dim>d_p<pid>-NN`
  (`env.new_case_dir`, unchanged): writing thousands of small files over the
  9p mount would be tens of times slower, and the W3 crash-resume, the live
  samplers and the decomposed-copy purge all assume the WSL path.
- **Success:** after every row of §2.2 is written, each file is verified
  (exists, size > 0) and the `foam\` skeleton is verified against the hashes
  taken in WSL (`sha256sum` inside WSL, compared on the Windows side). Only then
  is the scratch deleted (`rm -rf` through `env.wsl_plain_argv`, no OpenFOAM
  environment needed). The manifest records the deletion.
- **Failure or Stop:** the scratch stays. The manifest records its path with
  `"deleted": false`. The run browser, `--load-foam-run`, the manual VTK button
  and the post-mortem loader keep working on it exactly as today.
- The startup cleanup sweep (`env.auto_cleanup`, settings-driven) is not
  changed; it will simply find fewer directories.
- A run whose copy fails (disk full on Windows, a file locked) keeps its
  scratch and reports the failure in the dialog and the manifest; nothing is
  deleted on a partial copy. This is the `ux(2)` rule already in the tree: a
  finished solve is never lost to a failed write.

### 2.4 Code touch points

| Where | What |
|---|---|
| `core/settings.py` | `runs_dir=''` in `DEFAULTS` |
| new `services/model_folder.py` | `validate_name`, `prepare(runs_dir, model, confirm)` (create / overwrite-after-confirm), `write_all(result, folder, log)` (runs every export of §2.2 off the GUI thread, collects the manifest), `verify_and_release_scratch(meta, folder)` |
| `ui/run_panel.py`, `gui/run_panel.py` | the folder box + Browse; the name box mandatory; tooltips |
| `ui/run_controller.py` (`start_stages`, `resume_foam_run`, `_launch`), `gui/app.py` | pre-flight refusal; pass `(runs_dir, model)` into the stage; on finish call `model_folder.write_all` then `verify_and_release_scratch` |
| `ui/chain_panel.py`, `core/chain.py` | workspace box removed; stage folders under the model |
| `services/hd13.py`, the HD1.3 panel, `output/cli_hd13.py` | report and loads into the model folder |
| `__main__.py`, `cli.py`, `solvers/foam/cli_run.py` | `--runs-dir`, `--model` required; prompts |
| `solvers/foam/backend.py` | expose the scratch path and the probe/log file list for the `foam\` copy (mostly exists in `meta`) |

### 2.5 Tasks and acceptance criteria

| # | Task | Acceptance criterion |
|---|---|---|
| R1 | `runs_dir` setting; `validate_name`; pre-flight refusal in the Qt and Tk run panels, the chain panel, the HD1.3 panel and the CLI | unit tests for `validate_name` (empty, separators, reserved names, length); a run with an empty box never starts and the message names the missing box; CLI without the arguments exits 2 with usage |
| R2 | `services/model_folder.py`: prepare / overwrite-after-confirm / `write_all` / manifest | unit test on a temp folder with a native 1D result: every row of §2.2 that applies exists; a second `prepare` of the same name asks and, on yes, the old files are gone; on no, untouched |
| R3 | blastFoam: `foam\` skeleton with `SHA256SUMS`; scratch released on success only | unit test with a fake scratch tree (hash mismatch → scratch kept, dialog text); a real tiny WSL run: scratch gone after success, present after a forced failure (kill the solver) |
| R4 | Chain and HD1.3 into the model folder; workspace box removed | `test_ui_chain.py`, `test_hd13*` green; a real chain run lands in `MODEL\1d`, `2d`, `3d` with hand-offs at the root |
| R5 | Tk parity | the nine `test_gui_*` suites and `_qa_gui_harness.py` green |
| R6 | Gates | `test_regression.py` byte-identical; writer goldens unchanged; new `_qa_ui_harness.py` scenarios (refusal, overwrite dialog, finished folder); `gui-qa-tester` screenshots |
| R7 | Docs | `blastlab/README.md` section "Where a run's files go"; `DONE.md` entry; `TODO.md` ticked |

New tests: `test_model_folder.py`, `test_run_preflight.py`, `_e2e_model_folder.py`
(WSL, tiny 3D), scenarios in `_qa_ui_harness.py`.

---

## 3. `OUT-2` — VTK output options

### 3.1 The card

A new **Output** card in the Setup tab, `scope='blastfoam'` (hidden in native
mode like every other blastFoam-only control), laid out per dimension as
Viper's 1D / 2D / 3D tabs are:

| Dimension | Families shown |
|---|---|
| 1D | *Whole domain* (the radial line) |
| 2D | *Whole domain*, *Obstacles* (the 2D domain is its own section, as in Viper's 2D tab) |
| 3D | *Sections and obstacles*, *Volumes* |

Per family: an enable box; a **Time / Step** radio pair; one value box per
mode, the other greyed out (exactly Viper's *VTKs and Framerates* block).
Time is **simulated time in seconds** — the label says `[s]`, like the rest of
the form, and one line on the card says that the files and ParaView show time
in seconds (*owner decision P22, 2026-09-27*, reversing the earlier `[ms]`,
batch plan Q3: a typed 0.5 ms reappeared as 0.0005 in the files). Step is
solver steps, the unit the live-view refresh already uses.

Sections (3D): the live-slice plane (`slice_axis`, `slice_pos`, already on the
form) is always included; a small table below it adds planes as (axis,
position [m]) rows — the `points`-style field the form already renders.

Defaults when a family is switched on, mirroring Viper: sections and obstacles
= pressure + peak pressure (`pMax`, absolute); volumes = pressure, density, velocity.

### 3.2 The quantity matrix

A checkbox grid; a cell exists only where blastFoam has the field.

| Quantity | Field | Gauges | Sections | Obstacles | Volumes |
|---|---|---|---|---|---|
| Pressure | `p` | locked ✓ | ✓ | ✓ | ✓ |
| Overpressure | `overpressure` | | ✓ | ✓ | ✓ |
| Impulse | `impulse` | | ✓ | ✓ | ✓ |
| Peak pressure (absolute; subtract ambient for overpressure) | `pMax` | | ✓ | ✓ | ✓ |
| Arrival time | `timeOfArrival` | | ✓ | ✓ | ✓ |
| Density | `rho` | locked ✓ | ✓ | ✓ | ✓ |
| Velocity | `U` | locked ✓ | ✓ | ✓ | ✓ |
| Temperature | `T` | | ✓ | ✓ | ✓ |
| Products fraction | `alpha.expl` | | ✓ | ✓ | ✓ |
| Energy | `rhoE` | | ✓ | ✓ | ✓ |

`overpressure`, `impulse`, `pMax`, `timeOfArrival` are the function objects the
writer already emits (`_controldict_function_objects`); the rest are solver
fields. The Gauges column is display only until `OUT-4`.

### 3.3 Case keys and validation

```json
"vtk_surfaces": {"on": true, "mode": "time", "value": 0.0005,
                 "fields": ["p", "pMax"],
                 "planes": [["y", 1.4], ["z", 0.5]]},
"vtk_volumes":  {"on": true, "mode": "step", "value": 25,
                 "fields": ["p", "rho", "U"]}
```

- Both groups are omitted from the JSON when off (the `write_budget` pattern):
  default files stay byte-identical, `VERSION` stays 13, an older blastlab
  refuses a file that has them with the existing "Unknown case keys".
- Validation refuses: `value <= 0`; `mode` not in `time|step`; a field the
  dimension does not have; a plane axis not in `x y z` or a position outside
  the domain; `vtk_volumes.on` together with `write_budget > 0` (both pin the
  write interval — the message says which to clear); volumes on a parallel AMR
  case (§3.5).
- Hidden-in-native rule: the keys stay in the form but are not written when
  the solver mode is native, like every other blastFoam-only field.

### 3.4 Writer

**Sections and obstacles** — one `surfaces` function object with blastFoam's
`vtkTimeSeries` writer (blastFoam User Guide v6.0 §15.5; the pattern in
`tutorials/blastFoam/building3DWorkshop/system/controlDict`). Sketch, to be
checked against the guide by the implementer:

```
vtkSurfaces
{
    type            surfaces;
    writeControl    timeStep;            // or runTime for Time mode (D5)
    writeInterval   25;                  // or value [s] (P22)
    surfaceFormat   vtkTimeSeries;
    interpolationScheme cellPoint;
    fields          (p pMax);
    surfaces
    (
        slice_y_1.40 { type cuttingPlane; planeType pointAndNormal;
                       pointAndNormalDict { point (0 1.4 0); normal (0 1 0); }
                       interpolate false; }
        obstacles    { type patch; patches (obstacles); triangulate false; }
    );
}
```

Its cadence is independent of the solver's writes; the files land under
`postProcessing/vtkSurfaces/<time>/` with a `.vtk.series` index next to them.
The obstacles entry is emitted only when the case has obstacles (the
`obstacles` wall patch exists only then — `writer.py`, "obstacle boxes are
carved out … exposed faces -> 'obstacles' wall patch").

**Volumes** — the cadence becomes the solver's own write schedule: Time →
`writeControl runTime; writeInterval value` (seconds, P22); Step →
`writeControl timeStep; writeInterval N`. The adaptive interval controller is
switched off for the run (`spec.adaptive_write = False`, as `_apply_budget`
does) and the exact end-time write (`writeTimes`, T62) is kept.

*Owner decision P14 (b), 2026-09-27:* Time mode uses `runTime`, not
`adjustableRunTime`. `adjustableRunTime` shortens the time step to land each
write exactly on its time, which changed the solve (batch plan P14: +4.2 %
peak at a Z ≈ 0.07 gauge). With `runTime` each write lands on the first solver
step past its interval and the time step is never touched.

### 3.5 Run loop: the `VtkExport` stage

Sits where the HD1-15 `DecomposedPurge` sits — after each ingest pass and on
the final sweep — and is a no-op when `vtk_volumes` is off.

1. For every time `t` the ingest has read (`done`) and, in parallel, a
   successful `reconstructPar` has covered: run
   `foamToVTK -time t -fields (<fields>) -poly -useTimeName` in the scratch
   (serial; the case is already reconstructed by `maybe_reconstruct`).
2. Copy the resulting file to `<MODEL>\vtk\volumes\t_<time>.vtk`; verify
   size > 0.
3. Only then delete the WSL time directory `<scratch>/<t>` (and its
   `processor*/<t>` copies through the existing `purge_paths` /
   `delete_decomposed` chunked `rm`). **Never deleted:** `0/`, the start
   directory of a resume, the newest complete write (W3 resumes from it),
   `postProcessing/`, logs, dictionaries, `constant/`.
4. Sweep new files from `postProcessing/vtkSurfaces/` to
   `<MODEL>\vtk\sections\<plane>\` and `<MODEL>\vtk\obstacles\` (copy, verify,
   delete the WSL copy).
5. Write `<MODEL>\vtk\<family>\<name>.vtk.series` (ParaView's JSON file series:
   `{"file-series-version": "1.0", "files": [{"name": "t_0.0005.vtk",
   "time": 0.0005}, …]}`) and `<MODEL>\vtk\manifest.json` (fields, cadence,
   times, count per family).

The deletion decision is a **pure function** with its own unit test:
`vtk_purge_plan(done, converted, copied_ok, newest_complete, start_dir,
reconstructed) -> names`, in the style of `decomposed_purge_plan`.

Verified in code before deletion is enabled (acceptance criterion of V3, not an
assumption): the Results snapshots are taken from memory during ingest — 1D
from the `store`, 3D under the explicit memory bound in `backend.py` — so a
deleted time directory never removes a snapshot. The implementer confirms the
same for 2D (`finalize_2d` receives `ingested`, `snap_names`).

Declared limit: a **parallel AMR run** (`spec.decomposed`, not reconstructable
— the same limit HD1-15 has) cannot export volumes; validation says so before
the run. Surfaces work there, because the function object writes them itself.

Failure handling: a `foamToVTK` failure or a copy failure logs one line, keeps
the time directory, and continues; the run is never stopped by its export. The
final manifest lists every time that was not converted and why.

### 3.6 Layout on Windows

```
<runs>\<MODEL>\vtk\
  manifest.json
  volumes\    t_0.0005.vtk  t_0.0010.vtk  …  volumes.vtk.series
  sections\   slice_y_1.40\  t_….vtk  …  slice_y_1.40.vtk.series
              slice_z_0.50\  …
  obstacles\  t_….vtk  …  obstacles.vtk.series
```

### 3.7 Tasks and acceptance criteria

| # | Task | Acceptance criterion |
|---|---|---|
| V1 | Case keys, save/load, validation (§3.3) | `test_case_validate.py`; a case without the keys saves byte-identical; every refusal in §3.3 has a test |
| V2 | Writer: the `surfaces` function object; the volumes cadence mapping; adaptive off; end-time write kept | `test_foam_writer.py`; goldens unchanged; a case with export on renders a `controlDict` whose dictionary is checked line by line against the guide §15.5 |
| V3 | `VtkExport` stage: `vtk_purge_plan` (pure) + executor; the snapshot-from-memory check for 1D/2D/3D written down with file:line | unit test on a fake tree: what is deleted, what stays, copy failure → nothing deleted, newest write never deleted |
| V4 | `.vtk.series` and `vtk\manifest.json` | unit test; the owner opens a series in ParaView and it plays |
| V5 | The card: `setup_spec` rows, the matrix widget, the plane table, hidden in native mode, Viper-style greying of the inactive cadence box | `test_ui_setup_form.py` and a new `test_ui_output_card.py`; a `_qa_ui_harness.py` scenario per dimension |
| V6 | Real tiny 3D run (a few thousand cells, ~1 min) with both families on | file count = expected ± 1 per family; scratch released at the end (§2.3); gauges, snapshots and animation identical to the same run without export (compared file by file) |
| V7 | Gates | `test_regression.py` byte-identical; `test_write_budget.py`; the Tk suites (a shared module changed); `gui-qa-tester` on the card |
| V8 | Docs | README section; `DONE.md`; `TODO.md` |
| V9 | **Owner acceptance** | the owner runs a real case, opens the files in ParaView, and says "fixed and approved"; fixes as needed |

New tests: `test_vtk_case.py`, additions to `test_foam_writer.py`,
`test_vtk_export_plan.py`, `test_vtk_series.py`, `test_ui_output_card.py`,
`_e2e_vtk_3d.py` (WSL).

---

## 4. `OUT-3` — keep only the newest fields in WSL (mandatory follow-up)

Every blastFoam run, with or without VTK export, deletes each written time
directory once the app has ingested it, keeping only the newest complete write
(and `0/`, the start directory, `postProcessing/`, logs, dictionaries). The run
directory in WSL then never grows past a few writes. **Default: on.** A "Keep
all fields in WSL" box on the Output card turns it off for a run that needs a
post-mortem of the full field history.

It is the `OUT-2` machinery (§3.5) with the conversion step skipped, driven by
the same pure plan function. OpenFOAM's own `purgeWrite` is **not** used, for
the reason recorded in `runloop.py` (`DecomposedPurge` docstring): the solver
would delete a write before the app had read it for the live view, the
snapshots and the resume anchor.

Acceptance: a real tiny run ends with at most two time directories in WSL
besides `0/`; the Results tab shows the same snapshots as before; a
stop-and-resume still works (the anchor is never deleted).

---

## 5. `OUT-4` — the rest of the Viper matrix (mandatory follow-up)

| Item | What | Touches |
|---|---|---|
| Gauges quantities | the gauges may also record temperature, overpressure, impulse and dynamic pressure; the Gauges column unlocks | `writer._controldict_probes`, `reader.read_probes`, the gauge TSV/summary, the Results tab and the Tk equivalent |
| Dynamic pressure | blastFoam's `dynamicPressure` function object, wired into the writer and offered in every column | writer; validated against the guide |
| Peak impulse | not a blastFoam field; derived at the end of the run from the impulse series, per section/obstacle/volume, written as one more VTK per family | `VtkExport` final sweep |
| Obstacle IDs | one patch per obstacle (`obstacle_01`, …) instead of the single `obstacles` patch, so each structure is its own file | the topoSet/subsetMesh carve in `writer.py`; the BC and mask code that assumes one patch |
| Decimation | Viper's *Decimate ratio* for volumes: write every k-th cell | `foamToVTK -cellSet` on a generated set, or a post-pass |

Viper items that do **not** apply and are not planned: ASII / HVEL / RISK
(injury and hazard indices; not a blastFoam quantity), ignition time (a Viper
solver concept), *Whole domain energy / density* (already written by the
`conservedQuantities` function object every write — expose, do not re-implement).

---

## 6. `OUT-5` — reclaim the WSL disk (after owner acceptance of `OUT-1` + `OUT-2`)

The procedure is [wsl-disk-reclaim-plan.md](wsl-disk-reclaim-plan.md), unchanged:
the owner's six decisions (its §3), the pre-flight checks (§4), then prune →
export → trial import under a temporary name → unregister → import → verify
(§5), with rollback at every step (§6). What `OUT-1` and `OUT-3` add is the
reason it will not recur: a successful run leaves nothing in WSL, and a run in
progress holds at most a few writes.

Precondition, owner's words: "only after the export works, is fixed, and I
approve — then the disk."

---

## 7. Gates for every batch

- `python blastlab/tests/test_regression.py` — byte-identical, before anything
  else is trusted.
- `test_foam_writer.py` goldens unchanged for every case that does not use the
  new keys.
- The nine `test_gui_*` suites and `_qa_gui_harness.py` whenever `core/`,
  `solvers/`, `output/` or `services/` change — they do here.
- `_qa_ui_harness.py` scenarios for every new screen state; `gui-qa-tester`
  with screenshots after every GUI batch.
- WSL runs: confirm `wsl -d Ubuntu -- pgrep -a blastFoam` is empty first;
  `python -u`, no timeout, in the background.
- Measurement discipline for V6 and `OUT-3`: gauges compared on peak,
  positive-phase impulse **and** arrival, never peak alone.

---

## 8. What is explicitly not changed

- The Tk GUI stays and gets the same behaviour (`CLAUDE.md` §9).
- The native solvers and their baselines: byte-identical.
- The case JSON version, the writer goldens, the regression fixtures.
- The manual VTK button on the Results tab (still useful for a kept scratch).
- The startup cleanup sweep and its settings.
- The four WSL constraints in `env.py` (distro name, jammy, shim bashrc, `/root`
  paths) and `env.new_case_dir`.
- Solver defaults; no test is changed to make something pass.

---

## 9. Reference: the Viper::Blast screens the owner showed (2026-09-26)

**3D tab — "VTKs and Framerates":** *Cross-sections and surfaces* [box], Time
(radio, `0.001`) / Step (radio, `25`, greyed); *Volumes* [box], the same pair;
*Whole domain volumetric outputs*: whole-domain energy [box], whole-domain
density [box], decimate ratio [1]. **"Output Quantities"** — rows Pressure,
Impulse, Peak overpressure, Peak impulse, Density, Velocity, Mass fractions,
Temperature, Energy, Dynamic pressure, Arrival time (initial), Arrival time
(peak overpressure), Obstacle ID, Ignition time, ASII, HVEL, RISK; columns
Gauges / Sections / Obstacles / Volumes; a checkbox only where the pair is
meaningful (Impulse and Dynamic pressure only for gauges; Arrival times and
Obstacle ID only for obstacles; ASII/HVEL/RISK for sections and volumes).
Default ticks: Pressure at gauges, sections and obstacles; Impulse at gauges;
Peak overpressure and Peak impulse at sections and obstacles.

**2D tab — "Whole domain VTK outputs and framerates":** one Time / Step pair;
quantities Pressure, Impulse, Density, Velocity, Mass fractions, Temperature,
Energy, Dynamic pressure against Gauges / Whole Domain VTKs; Pressure ticked in
both, Impulse at gauges.

That layout — a cadence block per output family, then a quantity × destination
grid with cells only where they mean something — is the pattern §3 follows.
