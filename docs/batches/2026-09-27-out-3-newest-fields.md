# Batch 2026-09-27 · out-3-newest-fields

**Goal (one sentence):** every blastFoam run deletes each written time directory in WSL once the app has ingested it and nothing will read it again, so a run in progress holds only the newest writes plus what finalize and a resume need; a "Keep all fields in WSL" box turns it off per run (`OUT-3`, [model-folder-and-vtk-plan.md](../model-folder-and-vtk-plan.md) §4).

- **Branch:** `out-3-newest-fields` from master `22081a2`. Stage files by name; `docs/references/*` and `docs/qa/2026-09-27-viewer-polish/` belong to other sessions. git = the MinGit path (CLAUDE.md §3), `-c gc.auto=0`, commit, never push. Commit style `out-3: <what changed>`.
- **Binding:** plan §4, §7 (gates), §8; the OUT-2 batch plan [2026-09-27-out-2-vtk-output.md](2026-09-27-out-2-vtk-output.md) §0a (D1, D8, D9, D10, D12) and §6 owner decisions (P9, P11, P16).
- **Owner decision (2026-09-27, binding, relayed by the coordinator):** OUT-3 applies to **every** blastFoam run, not only runs with VTK export. It is **on by default**, and a **"Keep all fields in WSL"** box turns it off per run. This settles the earlier "OUT-3 always on" note: the purge is always on unless the box is ticked.
- **Built on OUT-2:** `vtk_export.vtk_purge_plan` (pure; `KEEP_NEWEST = 2`, the D9 AMR mesh rule), `time_dir_paths` + `runloop.rm_scripts`, `VtkExport.protect/unprotect/protected` (already filled by the backend for every run: `backend.py:597-601` pin/arrival, `:1486`, `:1516` 2D snapshots/trigger, `:2139` 3D snapshots, `restart_dir`), the 2D `arrived_cache` (`:1457-1470`, `:1696`), `note_resume` / `deleted_note` (P11), `FoamRunLoop._ingest_ready` → `_purge_decomposed` → `_export_vtk` (`runloop.py:1077-1101`). `DecomposedPurge` (HD1-15) is left unchanged.
- **References:** blastfoam-guide (`docs/references/BlastFoam_User_Guide.txt`) sec. 16.9, p. 136 (parallel AMR cannot be reconstructed, which is why decomposed runs are read per rank). The guide does not mention `purgeWrite`, and it is not used, for the reason given in the `DecomposedPurge` docstring (`runloop.py:342-345`).
- **Total size: XL** (2 × S, 6 × M, 2 × L). Checkpoint 1 after Step 4, when the headless purge is complete. Checkpoint 2 after Step 6, when the GUI is done.

---

## 0. Pre-flight

1. CLAUDE.md §8.2: `python -c "from blastlab.core import settings as s; d=s.load(); print(s.config_path(), d['auto_cleanup'])"` must print `False`. Never call `env.auto_cleanup` as a check.
2. `cd blastlab/tests; python test_regression.py` must be green, byte-identical, before the first commit.
3. Record the pre-existing failures (`test_foam_wsl_resume.py` `init_state`, `test_char_validation::test_hd13_starter_case`) and do not fix them.
4. Plan §7 and CLAUDE.md §8.1: edit only with Read/Edit/Write; `rg 'ג€|ג”'` over the touched files must come back empty.

## 0a. Where the plan and the code disagree (resolution proposed, plan not edited)

| # | Plan §4 says | Code says | Resolution |
|---|---|---|---|
| E1 | "It is the OUT-2 machinery with the conversion step skipped" | `VtkExport.active` requires a VTK family **and** `hooks.vtk_dir` (`vtk_export.py:623-624`). Time dirs are deleted only under `volumes_on`, after `converted ∩ copied` (`:872-883`, `:1102-1114`). | New mode **`fields_purge`**. It is active when `hooks.purge_fields` is true, whatever the families. `vtk_purge_plan` gets `require_copy=True`; the purge passes `False` when volumes are off, so `converted`/`copied` are not required. With volumes on, a time is still deleted only after its copy. |
| E2 | "ends with at most two time directories in WSL besides `0/`" | The D1 protected set keeps the 2D/3D snapshot dirs, the pin, the arrival write, the remap trigger and the restart dir. Finalize re-reads them. | Keep them. The registered rule (Step 7) is: the times left besides `0` ⊆ two newest ∪ protected ∪ `start_dir`. **Q4** |
| E3 | "every blastFoam run" | Owner decision P9 (OUT-2): a 1D run never deletes a time dir (`keep_time_dirs`, `:631`, `:879`). 1D snapshots on a **resumed** run are picked from disk (`backend._pick_snapshots`, `:1195`). | P9 carries over: 1D purges nothing and logs one line saying so. **Q1** |
| E4 | "every blastFoam run" | A run with no model folder (the headless scripts and `_e2e_*` that call `solve_*` directly, and a run-browser resume, P2-17) has no record to write what was deleted into. | Active only when `stage_solve` sets `hooks.purge_fields`, as for D12. Without a folder, nothing changes. **Q2** |
| E5 | (gap) | A finished run's scratch is released anyway (`verify_and_release_scratch`, `model_folder.py:960`), and `foam\` never holds a time dir (`:782`). So after a finished run, "keep all fields" would keep nothing. | A ticked box also **keeps the scratch** of a finished run: `release_decision` returns `(False, 'Keep all fields in WSL was ticked')`. **Q3** |
| E6 | (gap) | Decomposed (parallel AMR) runs are read per rank. `vtk_purge_plan` requires `reconstructed` when `n_procs > 1`, so nothing would ever be deleted, and these are the largest runs (HD1-3d). | New branch in the plan: "ready on every rank" (`common_ready_times`) replaces "reconstructed". The D9 mesh rule is applied per rank and conservatively (mesh = the union over ranks; the next kept time counts as a mesh time only if **every** rank holds `polyMesh/` there). **Q5** |
| E7 | (gap) | `deleted_note` / `note_resume` read only `vtk\manifest.json`, which does not exist for a run without VTK | Record the deletions in the root manifest, key `wsl_fields` (additive), and teach both helpers to read it. **Q6** |
| E8 | (gap) | OUT-2's own deletions would still run with the box ticked | The box stops **every** time-dir delete. Volumes are still converted and copied. `VTK/<case>_<t>.vtk` and the swept surface dirs are copies and are still removed after verification. |

---

## 1. Tasks, in order

Each step leaves the app runnable. **No time dir is deleted before Step 3**, and before Step 6 nothing is deleted without the hook, so the GUI behaves as before until then.

### Step 1 · Case key and validation · **S**
- `models/case.py`: `keep_all_fields: bool = False` on `Case1D/2D/3D`. `case_to_dict` drops it when `False`, next to the `vtk_*` pops. `VERSION` stays as it is.
- `services/validation`:
  - native mode: a note that the setting is blastFoam-only (the same pattern as the VTK note);
  - 1D: a note "1D keeps its written times until the scratch is released (P9)";
  - ticked: a note "every write stays in WSL and the scratch is kept after the run; disk estimate N GB" (`BYTES_PER_CELL_WRITE × cells × writes`).
- **Acceptance:**
  - default `Case1D/2D/3D()` save byte-identical;
  - a `True` round trip;
  - `test_vtk_case`, `test_case_validate`, `test_char_case_json`, `test_char_validation` and `test_write_budget` unchanged;
  - `test_foam_writer.py` goldens unchanged (no dictionary change).

### Step 2 · The pure plans · **M**
- `vtk_purge_plan(..., require_copy=True)`: with `False`, the `converted ∩ copied_ok` condition is dropped. Every other exclusion stays (`0`, `start_dir`, `protected`, the two newest, D9, `reconstructed` in reconstructed parallel).
- `vtk_purge_plan(..., per_rank_ready=None, rank_mesh=None)` (E6): the decomposed branch.
- **Acceptance** (`test_vtk_export_plan.py` part C, new): the full decision table again with `require_copy=False`:
  - `0`, `start_dir`, each protected reason, the two newest, an un-ingested time and an unreconstructed parallel time all survive;
  - the D9 chain;
  - the E6 cases: a time not ready on one rank survives; a rank-mixed mesh keeps the older time;
  - existing parts A/B unchanged.

### Step 3 · The executor: serial and reconstructed parallel · **L**
- **`VtkExport`:**
  - `self.purge_fields = bool(getattr(hooks, 'purge_fields', False)) and not keep_all`;
  - `active` becomes `(family and vtk_dir) or purge_fields`;
  - `_run` deletes `_plan(done)` when `purge_fields` (or `volumes_on`), passing `require_copy=self.volumes_on`;
  - `keep_time_dirs` (1D) and `no_delete` still win;
  - with `keep_all`, no time-dir delete at all (E8);
  - one log line at start (`keeping only the newest writes in WSL` / `keeping all fields`), one per failed delete kind;
  - with no family, no `vtk\` folder is created and no manifest is written. The deleted set is kept for Step 5.
- **`hooks.RunHooks.purge_fields = False`.** `model_folder.stage_solve` sets it for a blastFoam case with `not keep_all_fields`, and restores it in `finally` (as `vtk_dir`, `:1110-1176`).
- **Acceptance** (`test_vtk_export_plan.py` part D, fake scratch tree, deleter injected):
  - no family + `purge_fields` → exactly the planned dirs deleted; no `vtk\` folder;
  - hooks without the flag → no delete (every existing test unchanged);
  - `keep_all` → no delete, even with volumes on;
  - 1D → no delete;
  - a delete failure is retried and never raises;
  - `test_vtk_protect.py`: finalize on the purged tree equals the unpurged tree for 2D/3D (pin time, snapshots, `final_state`);
  - `test_foam_resume`, `test_write_budget`, `test_char_meta` and `test_char_native_api` pass unchanged.

### Step 4 · Decomposed (parallel AMR) runs · **M** · depends on Step 3
- In `_plan`, when `spec.decomposed`: `per_rank_ready = common_ready_times(spec, fields)`, and `rank_mesh` comes from a listing of each `processor<i>/` (cached for ingested times, as `mesh_cache`). The paths come from the existing `time_dir_paths` (root plus `processor*/`).
- The restart anchor: the newest time ready on every rank is never among the deleted, and it is one of the two newest. That also covers the P1-5 walk-back by one write.
- **Acceptance:**
  - a fake 3-rank tree with uneven readiness and AMR meshes: exactly the E6 plan is deleted;
  - `backend._resume_start_time` on the purged tree picks the same time as on the full tree;
  - `DecomposedPurge` tests unchanged.

**Checkpoint 1:** the §3 fast gates plus the 14 `test_gui_*`, because `solvers/` and `services/` changed.

### Step 5 · Record, release, readers · **M** · depends on Step 3
- **`write_all`:** the root manifest gets `wsl_fields = {mode: 'newest'|'keep_all'|'off', deleted: n, first, last}`, where `off` means no model folder (E4) or 1D. It is additive and `null` for native runs.
- **`release_decision(..., keep_all=False)`** (E5): a ticked box keeps the scratch, with `kept_because`, and the folder notice says why.
- **`deleted_note(case_dir, vtk_dir=None)`** also reads the root manifest's `wsl_fields` (found through the scratch, as in P11). `note_resume` likewise. `resume_run`, `postmortem.load_run` and the Results VTK button (Qt `ui/results_panel.py:411`, Tk `gui/results_panel.py:876`) then log the one P11 line for a purged run without VTK.
- **Acceptance:**
  - `test_model_folder`: the manifest key for each mode; `keep_all` keeps a finished run's scratch; a default finished run is released as before;
  - `test_vtk_readers`: the note for a no-VTK purged run, and no note for `keep_all`;
  - `test_vtk_protect` `note_resume` cases extended.

### Step 6 · The box, Qt + Tk parity · **M**
- **Qt:** a `keep_all_fields` bool row on the **VTK output (ParaView)** card (`ui/setup_spec._vtk_card`). It is shown in 1D/2D/3D and hidden with the card in native mode. Tooltip: "Off (default): WSL keeps only the newest writes while the run goes on; the Results tab, gauges and resume are unaffected. On: every write stays, and so does the WSL scratch after the run."
- **Tk:** the same `CTkCheckBox` in `gui/forms.py`, registered in `_scoped['blastfoam']`. `models/fields.py` maps it in blastFoam mode only.
- **Harness:** Qt `_qa_ui_harness.py` scenario `V06`, and Tk `_qa_gui_harness.py` `V05`.
- **Acceptance:**
  - `test_ui_output_card`: the box exists in each dimension, is hidden in native mode, and the form → case → JSON → form round trip holds;
  - `test_ui_parity` green;
  - `test_ui_char_case_form --update` and `test_gui_char_case_form --update`, each in **its own commit**, adding rows only.

**Checkpoint 2:** the full §3 fast gates.

### Step 7 · Real tiny e2e · **M** · needs the machine free (§4)
New `tests/_e2e_fields_purge.py`. The rules below go into the script header and are **committed before the first run**, and are never changed afterwards.
- **Rule 1, serial 2D** (a few thousand cells, one obstacle, one gauge, ~10 writes, `n_snapshots` default, adaptive off):
  - A (box ticked) vs B (default), gauges TSV, snapshot arrays, animation frames, pin time and `final_state` must be **byte-identical**. The purge deletes only after the ingest, so the solve cannot move.
  - During B, WSL is sampled every 2 s. At every sample the dirs besides `0` must be ⊆ two newest ∪ protected ∪ one not yet ingested (the P16 reading).
  - B's scratch is released; A's is kept (E5).
- **Rule 2, stop and resume:** B stopped at about half its end time.
  - The kept scratch holds ⊆ two newest ∪ protected ∪ `0` ∪ `start_dir` (E2).
  - The resume starts from the newest complete write (log line) and finishes without an error.
  - Its gauges vs A: peak, positive-phase impulse **and** arrival within 1 / 1 / 0.5 % (the OUT-2 Q7 thresholds). Never peak alone.
- **Rule 3, 1D → 2D chain, default vs box ticked:** the hand-off profile at the model root is byte-identical (N2-13), and the 1D stage deleted nothing (E3).
- **Rule 4, decomposed AMR 2D on 2 ranks, default vs box ticked:**
  - peak / impulse / arrival within 1 / 1 / 0.5 %;
  - the same snapshot labels;
  - the per-rank dirs left ⊆ the E6 plan.
- **Acceptance:** all rules pass as registered. A failure is recorded in §6, not re-tuned.

### Step 8 · Gates and GUI QA · **M**
- The full §3 gates.
- `gui-qa-tester` (the owner's agent), with screenshots of the box on the card: Qt 1D and 3D, Tk 3D, in dark and light, at 1100 px; native mode with the card hidden; the kept-scratch notice for a ticked finished run.

### Step 9 · Docs · **S** · editor tools only
- README "Where a run's files go": what stays in WSL during a run and why, the box, and E5.
- `DONE.md`: an `OUT-3` entry in the §0c style.
- `TODO.md`: the OUT-3 row ticked, "owner acceptance pending".
- Neither file is rewritten wholesale.

### Step 10 · Owner acceptance
A real case with the default and one with the box ticked. The owner checks the WSL listing and the Results tab, and says "approved".

---

## 2. GUI screens touched
| Screen | Change | Toolkit |
|---|---|---|
| Setup → VTK output (ParaView) card | the "Keep all fields in WSL" box | Qt + Tk |
| Validation strip | the Step 1 notes | Qt + Tk |
| Run log / folder notice | the purge start line; kept-scratch reason (E5); the P11 note for a purged run | both, through hooks |

## 3. Gates
- `test_regression.py` byte-identical first and after every step. The native path is untouched, so any difference means stop.
- `test_foam_writer.py`: goldens unchanged.
- The fast matrix: `test_case_validate`, `test_char_validation`, `test_char_case_json`, `test_write_budget`, `test_foam_env`, `test_foam_resume`, `test_char_exports`, `test_char_meta`, `test_char_native_api`, `test_model_folder`, `test_run_preflight`, `test_vtk_case`, `test_vtk_export_plan`, `test_vtk_series`, `test_vtk_protect`, `test_vtk_readers`, `test_ui_output_card`, `test_ui_setup_form`, `test_ui_parity`, `test_ui_results_vtk_folder`, `test_gui_results_vtk_folder`, `test_layering`, `test_ui_no_vtk_in_main`, `test_ui_no_mpl_pyplot`.
- Tk: all 14 `test_gui_*.py` and `_qa_gui_harness.py` (shared modules change; CLAUDE.md §9).
- `_e2e_vtk_3d.py` re-run once: OUT-2's 41 checks still pass, because the export and the purge share `_run`.
- Re-pins: only the two char case forms, each in its own commit.

## 4. Needs the machine free
`wsl -d Ubuntu -- pgrep -a blastFoam` must be empty; tell the owner first. Copy any run you care about out of `/root/blastlab_runs`. Use `python -u`, no timeout, in the background. Runs: Step 7, the `_e2e_vtk_3d.py` re-run, the real-window harness scenarios, and `gui-qa-tester`.

## 5. Risks
1. **Deleting what finalize, the chain or a resume reads.** Protection:
   - the pure plan with its full table;
   - the existing protected set, now load-bearing for every run, not only VTK runs;
   - `KEEP_NEWEST = 2` (the W3 anchor plus one P1-5 walk-back);
   - Step 3's finalize-equality test;
   - e2e rules 1-3.
2. **Numbers.** The purge acts only after the ingest and never touches a dictionary. Rule 1 is byte-identical, and rule 2 is judged on peak, impulse and arrival together.
3. **Decomposed AMR** is new ground (per-rank readiness and meshes). Protection: the conservative E6 rule, the Step 4 resume-start test and rule 4. If rule 4 fails, the fallback is to leave decomposed AMR out (Q5 alternative), not to loosen the rule.
4. **Loss of post-mortem material by default.** A stopped run keeps only the newest writes plus the protected ones. The box is the way out, and it is shown on the card with a tooltip that says so.
5. **Corpus (§8.2).** The new tests use fake trees and the private `runs_dir`. Only `_e2e_fields_purge.py` makes real runs, and it makes its own.

## 6. Owner decisions and parked questions

**Owner decision (2026-09-27, binding):** OUT-3 is on for every blastFoam run, VTK or not, by default, with a "Keep all fields in WSL" box to turn it off per run. The earlier "always on" note is settled by this.

**Owner decision (2026-09-27, Step 7 re-registration, committed before the re-run):** the first e2e gave 35/41 - rules 2c and 4a compared nothing, because the gauge at (0.35, 0.5) sat 2 cm behind the closed obstacle ring (0.30-0.33, 0.2-0.8) and never left 101325 Pa. The R1/R2/R4 gauge moves to (0.2, 0.5): an unobstructed straight line to the charge, 0.2 m away, inside the ring. Chosen from the geometry, not from any number. Rule text and thresholds unchanged.

**Parked (none blocks; each is the interim the code uses, and a different answer is a small change in `vtk_export.py` / `model_folder.py`):**
- **Q1 · 1D (E3).**
  - *Interim:* P9 carries over; a 1D run deletes nothing until the scratch is released.
  - *Alternative:* purge 1D too. A live 1D run keeps its snapshots in memory, but a resumed 1D run would pick them from fewer writes.
- **Q2 · Runs with no model folder (E4)**, i.e. headless scripts and a run-browser resume (P2-17).
  - *Interim:* they keep all fields.
  - *Alternative:* purge them too, with the record written only to the log.
- **Q3 · A ticked box also keeps the scratch of a finished run (E5).**
  - *Interim:* yes; otherwise the box would keep nothing, since OUT-1 releases the scratch.
  - *Alternative:* the box keeps the writes only while the run lives.
- **Q4 · "At most two time dirs besides `0/`" (E2).**
  - *Interim:* the protected writes (snapshots, pin, arrival, trigger, restart) stay too, because finalize and the chain read them.
  - *Alternative:* copy them into the model folder and delete them (a larger change).
- **Q5 · Decomposed AMR (E6).**
  - *Interim:* included, with the conservative per-rank rule.
  - *Alternative:* declare the limit, as OUT-2 does for volumes.
- **Q6 · The record (E7).**
  - *Interim:* the root manifest `wsl_fields` summary (count, first, last), in line with P4's numbers-only root manifest.
  - *Alternative:* the full list of deleted times.
- **Q7 · With the box ticked and VTK volumes on (E8).**
  - *Interim:* no time dir is deleted; the converted copies are still removed.
  - *Alternative:* OUT-2 keeps deleting after conversion regardless of the box.

## 7. Remaining backlog
- **`OUT-4`**: the rest of the Viper matrix (plan §5).
- **`P2-17`**: resume and the run browser do not know the model. This interacts with Q2.
- **`P2-19..21`**: the OUT-2 layout leftovers (P17-P19).
- The rest of `HD1` and P0-P4, in the order `TODO.md` gives.
