# Batch 2026-09-26 · out-1-model-folder

**Goal (one sentence):** no run starts without a runs folder and a model name,
and every file a run produces lands in `<runs>\<MODEL>\`, with the blastFoam
scratch in WSL deleted only after a verified copy (`OUT-1`,
[model-folder-and-vtk-plan.md](../model-folder-and-vtk-plan.md) §2).

- Branch: `out-track` (worktree `C:\Users\rotem.ofek\blastlab-worktrees\out-track`),
  base `d2f5cb1`. Work only here, never in the OneDrive copy.
- Order source: `TODO.md` §`OUT` (above `HD1`, owner 2026-09-26). `OUT-1` is
  planned **alone**: no `OUT-2` (VTK), `OUT-3` (purge) or anything else.
- Binding: plan §1 (decisions 8-12, 14), §7 (gates), §8 (not changed).
- **Merge-sensitive** = a file the parallel `hd1-16-load-export` session also
  edits: `services/hd13.py`, `output/cli_hd13.py`, `ui/app.py`, `TODO.md`, `DONE.md`.
  Its batch plan also edits `output/load_csv.py` and `ui/setup_spec.py`, so treat those
  the same way. Keep edits there small and local, and **merge `hd1-16-load-export`
  into `out-track` before Step 7 and again before the final gates**.
- References: none of `docs/references/INDEX.md` applies. This batch is file I/O. The
  `foam\` skeleton is the case layout `writer.write_case` already produces.
- Total size: **XL** (2 × S, 7 × M, 2 × L). This is more than one sitting. The natural
  checkpoint is after Step 4: everything up to there is headless, with no GUI and no
  form change.

---

## 0. Pre-flight (before any step that builds a GUI) · CLAUDE.md §8.2

1. `python -c "from blastlab.core import settings as s; d=s.load(); print(s.config_path(), d['auto_cleanup'])"`
   must print `False`. Do **not** call `env.auto_cleanup(settings.load())` as a "check";
   it deletes when the flag is on (TODO `P0-5`).
2. Offscreen suites keep `BLASTLAB_SETTINGS` pointing at a throwaway file
   (`ui/testing.private_settings`). This batch extends that helper (Step 5); do not unset it.
3. `cd blastlab/tests; python test_regression.py` is green **before the first
   commit**. That run is the baseline for "byte-identical".

## 0a. Where the plan and the code disagree (resolution proposed, plan not edited)

| # | Plan says | Code says | Resolution in this batch |
|---|---|---|---|
| D1 | `core/case.py`, `core/chain.py` | Both are re-export shims. `save_case` is in `models/case.py`, the chain helpers in `services/chain.py`, and the **workspace logic is only in `ui/chain_panel.py` and `gui/chain_panel.py`**. | Edit the real modules. The Tk chain panel has its own workspace box, which the plan does not list; it goes too (decision 14, `CLAUDE.md` §9 parity). |
| D2 | HD1.3 report is `<case>_hd13.html` beside the case (`default_report_path`) | That is the **CLI only**. The Qt Run writes to the form's `report_file` field (`ui/setup_spec.py:344`, default `hd13_report.html`, relative, so it lands in the CWD) (`ui/app.py:575`). `--report FILE` overrides the CLI. `--hd13-wall-export` writes `<case>_wall_loads/`. | `report_file` leaves the form. `--report` is removed (argparse rejects it). `default_report_path` and `load_csv.wall_loads_dir` stop being used for output. The wall export goes to `<MODEL>\wall_loads\`. |
| D3 | §2.2 lists only exports | The Setup **Outputs** card already has `gauge_file`, `anim_file`, `profile_out` and (2D/3D) `trigger_file`. `jobs.solve_stage` writes them **relative to the CWD** (`jobs.py:108-130`), so every GUI run today drops `gauges_2d.txt` wherever the process started. | The stage binds these paths into the stage folder under the §2.2 names (`bind_case`, Step 2), and the four filename fields are **hidden**. Their values still pass through load→save. See Q1. |
| D4 | Pre-flight "in the same place the case validation refuses" | `services/validation.validate_case` is case-only and knows no folder. The refusal it feeds is in `ui/app._run_single` / `gui/app._run_single`. | The folder check is `model_folder.check()`, called right after `validate_case` at every entry point. The Setup validation strip does not show it. |
| D5 | `backend.py`: expose scratch and file list ("mostly in `meta`") | `meta['case_dir']` (UNC) exists **only on success**. A run that raises has no Result. `n_cells`, `n_procs` and `n_steps` are not in `meta`. | Add `hooks.scratch_posix = spec.case_posix` in `backend._preflight` and `resume_run` (two lines). For the manifest, `n_cells` and `n_procs` come from the pre-flight `ValidationReport` (`rep.n_cells`, `rep.run_plan`) and `n_steps` from the last `Progress`. **No key is added to native `meta`**, because `test_char_native_api.py` pins it. |
| D6 | `solvers/foam/runloop.py` in the touch list | `OUT-1` needs nothing there. It is `OUT-2`'s. | Not touched. |
| D7 | "the HD1-3d evidence-copy pattern" | There is no production helper. It exists only as `tests/_e2e_vent_wall.py` (`read_sums`, a `sha256sum` listing). | New code in `model_folder`, in the same `SHA256SUMS` format (`<hex>  <relpath>`). |
| D8 | "the nine `test_gui_*` suites" | There are **14** `test_gui_*.py`. | Run all 14. `test_gui_run_browser` can hang on a modal (`P2-8`): record it and do not fix it here. |
| D9 | manifest `git_commit` | git is **not on PATH** (CLAUDE.md §3). | Read `.git/HEAD` and the ref files directly. A worktree's `.git` is a `gitdir:` file. If none can be read, the value is `null`. |
| D10 | R4: "`test_ui_chain.py` … green" | `test_ui_chain.py`, `test_gui_drain.py` and `_qa_ui_harness.py` G01-G03 pin `ws_box` / `default_workspace`. `test_ui_char_hd13_run.py` pins `report_file`. Every test that presses Run through a window has no model name. | They cannot stay green unchanged. Owner decisions 8 and 14 authorise the edit: the same invariants are rewritten against the model folder ("nothing created on refusal", "created only once it runs"). Each goes in its **own commit** citing `OUT-1`, and no numeric assertion changes. |
| D11 | new `rm -rf` through `wsl_plain_argv` | `env.delete_runs(case_dirs)` already does exactly that. | Reuse `env.delete_runs`. |
| D12 | `write_all` runs "every export" | `services/exports.run_export` calls `os.startfile` after `report` and `vtk` (`_open`). | Add `run_export(..., open_after=True)`. The default is unchanged, so `test_char_exports.py` stays green, and `write_all` passes `False`. |
| D13 | `--cli` "required" **and** "the prompt asks for both" | Contradictory for the same entry. | `python -m blastlab --cli` without them exits 2. `cli.main(dim, solver, runs_dir=None, model=None)`, the importable entry, **prompts** for whichever is missing before its first question. |
| D14 | CLI output = the whole §2.2 table | Native `--cli` runs the byte-pinned `legacy/blast*d._main()`. It returns no Result and writes the filenames it prompts for, relative to the CWD. | Prepare the folder, `chdir` into it for the flow, and write a manifest that lists what landed. `missing` names the rows the prompt flow does not write. `legacy/` is not edited. The foam `--cli` path (`cli_run.py`) does have a Result and gets the full table. See Q2. |
| D15 | `<MODEL>\hd13_loads\` | `load_csv.export_hd13(out, report_path)` derives `<report stem>_loads`, which would give `hd13_report_loads`. | Add an optional `out_dir=` kwarg (merge-sensitive, 2 lines). |

---

## 1. Tasks, in order

Each step leaves the app runnable. Commit style: `out-1: <what changed>`. Commit
messages containing quotes go through a file and `git commit -F` (§4).

### Step 1 · R1a · `runs_dir` setting and the name rule · **S**

- `core/settings.py`: `runs_dir=''` in `DEFAULTS`.
- New `blastlab/services/model_folder.py` (no Qt, no pyplot, no VTK):
  - `validate_name(name) -> str | None` returns an error or None. The name is trimmed and
    must be non-empty and at most 100 chars. Refused: any of `\ / : * ? " < > |` and
    control chars, a trailing dot or space, reserved device names (`CON PRN AUX NUL
    COM1-9 LPT1-9`, case-insensitive, with or without an extension).
  - `check(runs_dir, model) -> list[str]`. Each message names its box: "Runs folder is
    empty", "Runs folder does not exist: …", "Model name: …".
  - `folder_for(runs_dir, model)`. An existing folder that differs only in case
    counts as the same model (Windows).
- **Tests:** new `tests/test_model_folder.py` part A: empty, whitespace only,
  every forbidden char, `CON`, `con.txt`, `LPT9`, trailing dot and space, 100 vs 101 chars,
  a missing folder, `MODEL` vs `model`. `python test_foam_env.py` (settings) unchanged.

### Step 2 · R2 · `prepare`, `bind_case`, `write_all`, the manifest · **L**

In `services/model_folder.py`:
- `prepare(runs_dir, model, confirm) -> path | None`. If the folder is absent it is
  created. If it exists, `confirm(text)` is called with exactly *"MODEL already exists in
  <runs>. Overwrite? The previous run's files will be deleted."*. Yes → `shutil.rmtree`,
  then recreate. No → None, and nothing is touched. An rmtree `OSError` (a file open in
  ParaView) raises `ModelFolderError` carrying the OS text, and nothing is recreated.
- `bind_case(case, stage_dir) -> case copy`. `gauge_file` → `gauges\gauges_<d>d.txt`,
  `anim_file` → `animation<ext>` (ext = `setup_spec._anim_ext()` logic moved to
  `output/animation`, so no `ui` import), `profile_file` → `profile.txt` /
  `profile_2d.npz` where `can('profile')`, and `trigger_file` → `trigger_remap.npz`. Chain
  hand-offs override `profile_file` (Step 6).
- `write_all(res, case, dim, stage_dir, run_info, log) -> manifest dict`, on the
  **worker thread**. Order: `MODEL.json` (the bound case, with paths written **relative
  to the folder**, so `load_case` resolves them), then verify the files `jobs` already wrote
  (tsv, animation, profile), then `summary`, `pngs`, `fieldcsv` and `report` through
  `services.exports.run_export(..., open_after=False)` (D12). Last comes `manifest.json`.
  Every output is checked to exist with size > 0. A failure goes to
  `manifest['failed']` and the log, and never raises (the `ux(2)` rule).
- `manifest.json` has the keys of plan §2.2 exactly, plus `failed` (additive). `stop_reason`,
  `created`/`finished` (local ISO-8601 to the second) and `git_commit` (D9) are filled in.
  `missing` entries: `animation` → "replay frames were not recorded"; `profile` →
  "3D / planar 2D has no profile export" (the `why_not` texts).
- `run.log`: a line sink. `GuiHooks.log` (and `ConsoleHooks.log`) also appends to
  `hooks.log_file` when one is set, UTF-8, `\n`. It holds the solver-side log, which is
  what the Run tab shows minus the UI-only lines such as `[run finished]`. That scope is
  written in the docstring.
- **Tests (`test_model_folder.py` part B):** a native 1D result and a native 2D axisym
  result (tiny, a few hundred steps, as `test_char_write_failure.case1d/2d`).
  - Every applicable §2.2 row exists with size > 0.
  - `manifest.json` parses and its `outputs` list equals the files on disk.
  - `missing` names the animation when `record_frames=0`.
  - `MODEL.json` round-trips through `load_case`.
  - A second `prepare`: No leaves every file's mtime and bytes identical, Yes leaves an
    empty folder.
  - A locked file (simulate with an open handle on Windows) raises `ModelFolderError`
    naming the file.
- `python test_char_exports.py` passes unchanged (default `open_after=True`).

### Step 3 · R2 · wire it into the worker · **M**

- `solvers/jobs.solve_stage(dim, case, stage_dir=None, run_info=None)`.
  `stage_dir=None` behaves **byte-for-byte as today**. With a folder, the stage does
  `bind_case`, opens `run.log` on the hooks, solves, writes the jobs files and then calls
  `write_all`. On `StoppedBeforeStart` or an exception it still writes `MODEL.json`,
  `run.log` and `manifest.json` (`stop_reason` = the error headline), then re-raises
  (the worker's 'error' path is unchanged). A `HandoffWriteError` still carries the
  result.
- **Tests:** `python test_char_write_failure.py` and `python test_ui_drain.py` pass
  **unchanged** (they use `stage_dir=None`). `test_model_folder.py` part C runs a
  `SolverWorker` with `stage_dir` on this thread:
  - `('result', 0)` precedes `('done',)`, and the folder is complete by then.
  - A patched `save_gauges_2d` that raises → the run still has a `report.html` and
    `manifest['failed']` names the TSV.
  - A solver that raises → `MODEL.json`, `run.log` and `manifest.json` exist.

### Step 4 · R3 · blastFoam: the `foam\` skeleton and scratch release · **L**

- `backend._preflight` and `backend.resume_run`: `hooks.scratch_posix = spec.case_posix`
  (D5). `RunHooks` gains the attribute, default `None`.
- `model_folder.copy_foam_skeleton(scratch_posix, dest, run=subprocess.run)`:
  1. Inside WSL (`env.wsl_plain_argv`), `cd <scratch> && find system constant 0
     postProcessing log.* -type f -print0 | xargs -0 sha256sum > SHA256SUMS`, without
     `processor*` or time dirs.
  2. Copy those files over the UNC path to `<stage>\foam\`.
  3. Recompute on Windows (`hashlib`) and compare line by line.
  4. Copy `SHA256SUMS` itself.
- `release_decision(errored, stopped_early, verify) -> (bool, why)`, a **pure** function.
  Release only if the run did not raise, `not res.stopped_early` (so not `stopped by
  user` or `STOP_UNSTABLE`), every §2.2 row verified, and the hashes all match.
- `verify_and_release_scratch(...)` calls `env.delete_runs([posix])` (D11) and records
  `wsl_scratch.deleted` / `deleted_at`. On a mismatch or partial copy the scratch is kept,
  the reason goes into the manifest and the log, and a dialog text is returned for the
  GUI.
- **Tests (`test_model_folder.py` part D, no WSL):** a fake scratch tree in a temp dir,
  with the `run` and `delete` callables injected.
  - One byte flipped after hashing → kept, and the text names the file.
  - Stopped → kept.
  - Raised → kept.
  - Clean → the `delete` callable is called once with the posix path.
  - `processor0/` and `0.001/` are never copied.
  - The decision table for `release_decision` covers every combination.
- `python test_foam_writer.py` (goldens unchanged), `test_foam_resume.py`,
  `test_write_budget.py` and `test_foam_env.py` pass unchanged.

**Checkpoint:** everything above is headless. Run the §3 fast gates before continuing.

### Step 5 · R1b · Qt Run tab: folder box, mandatory name, pre-flight · **M** · merge-sensitive (`ui/app.py`)

- `ui/run_panel.py`: **Runs folder** `QLineEdit` + *Browse* (`dialogs.pick_dir`) on the
  control card, before **Model**. `Name` is renamed **Model** and its tooltip now says it is
  required and names the folder. `runs_dir` is loaded from and saved to settings (on edit
  and on close, `_save_ui_state`). It joins the tab order after `run_name`.
- `ui/app.py`: one `_model_target()` used by `_run_single` (and so by `_init_model`),
  `_run_chain` and `_resume_foam_run`. It runs `model_folder.check`, which refuses with one
  `show_error('Run', …)` message naming the box, and then
  `prepare(confirm=dialogs.ask_yes_no)`. This happens after `validate_case` /
  `_confirm_long_run` and before anything is written.
- `ui/run_controller.py`: `start_stages(..., model=None)`,
  `resume_foam_run(..., model=None)` and `_launch` pass `stage_dir` (and `run_info` from the
  pre-flight report) into `solve_stage`. The resume wraps its solve the same way. On
  'error' or a kept scratch, the dialog text from Step 4 is shown through `show_error`.
  `model=None` stays the headless/test path (today's behaviour). Every GUI entry passes a
  model.
- `ui/testing.py`: `private_settings()` also writes a throwaway `runs_dir`, and there is a
  new `use_model(win, name='QA')`. The tests that press Run (D10: `test_ui_char_hd13_run`,
  `test_ui_live_gauges`, `_qa_ui_harness`, `_e2e_ui_*`) call it. That setup edit goes in
  its own commit.
- **Tests:** new `tests/test_run_preflight.py` (offscreen, stubbed dialogs):
  - Empty folder box → one error naming "Runs folder", the worker never starts, and no
    directory is created.
  - A missing folder and a bad name are refused the same way.
  - Existing model + No → nothing changed and no run. Existing model + Yes → the old file
    is gone and the run starts.
  - Initialise Model and a stubbed resume go through the same gate.
  - `runs_dir` survives a window close and reopen.
  `python test_ui_run_panel.py`, `test_ui_drain.py`, `test_ui_results.py` and
  `test_ui_parity.py` pass.

### Step 6 · R4a · Chain into the model folder, workspace box removed (Qt + Tk) · **M**

- `ui/chain_panel.py`: remove `ws_box`, `_pick_ws`, `default_workspace` and `workspace()`.
  `run()` takes the model target from the window (the same `_model_target()`; the chain
  already uses the Run tab's name). Stage folders are `<MODEL>\1d`, `2d`, `3d`. Hand-offs
  are `<MODEL>\handoff_1d_to_2d.txt` and `<MODEL>\handoff_2d_to_3d.npz`. Each stage's
  `MODEL.json` is written by `write_all`, which replaces `stageN_case.json`. There is a
  root `manifest.json` with `{"chain": [1,2,3], "stages": {"1d": …}, "handoffs": […]}`,
  written at 'done'. The load-bearing order is kept: **the folder is created only once
  the run is certain to start** (after `stage_errors`). The `HINT` text is updated.
- `gui/chain_panel.py` and `gui/app._run_chain`: the same (D1).
- **Tests:** `test_ui_chain.py` and `test_gui_drain.py`, workspace assertions rewritten
  (D10, own commit): a refused chain creates no model folder, a started chain creates it
  with `1d/`, `2d/` and `handoff_1d_to_2d.txt` wired as `profile_file` /
  `profile_file_in`. A tiny native 1D→2D chain run offscreen lands both stage folders and
  the root manifest. `python test_char_validation.py` passes unchanged.

### Step 7 · R4b · HD 1.3 into the model folder · **M** · merge-sensitive (`services/hd13.py`, `output/cli_hd13.py`, `output/load_csv.py`, `ui/app.py`, `ui/setup_spec.py`)

**Merge `hd1-16-load-export` first.**
- `ui/app._run_hd13`: pre-flight (Step 5). Report → `<MODEL>\hd13_report.html`, loads →
  `<MODEL>\hd13_loads\`. The case is saved as `<MODEL>\MODEL.json` and read back from
  there, which replaces the leaked `tempfile.mkdtemp('blastlab_hd13_')`. Then a
  `manifest.json` (`solver: "hd13"`, `dim: 0`, `wsl_scratch: null`).
- `ui/setup_spec.py`: the `report_file` row leaves the HD 1.3 **Outputs** card, and
  `name` (the report title) stays.
- `services/hd13.py`: `write_report(bundle, out_path, loads_dir=None)`. Remove
  `default_report_path`.
- `output/load_csv.export_hd13(..., out_dir=None)` (D15).
- `output/cli_hd13.py`: `run_and_report(case_path, runs_dir, model)` and
  `wall_export(case_path, runs_dir, model)`, the latter writing to `<MODEL>\wall_loads\`.
- **Tests:** `test_load_csv.py` and `test_char_hd13.py` pass unchanged (no number
  moves). Re-pin in **one commit citing `OUT-1`**, diff reviewed line by line, and only
  paths and the file listing may change: `test_char_hd13_cli.py --update`,
  `test_ui_char_hd13_run.py --update` (the "blank report field" scenario becomes
  "report in the model folder"), and `test_ui_char_case_form.py --update` (`report_file`
  gone).

### Step 8 · R1c · Command line · **M** · merge-sensitive (`output/cli_hd13.py`)

- `__main__.py`: `--runs-dir DIR --model NAME`. Missing on `--cli`, `--hd13` or
  `--hd13-wall-export` → `ap.error(...)`, which exits 2 with usage. `--report` is removed
  (D2). `--hd13-new` (writes an input, not a run), `--load-foam-run`, `--clean-foam-runs`
  and `--reap-foam-runs` take neither.
- `cli.main(dim, solver, runs_dir=None, model=None)` prompts for a missing one first
  (D13), then `prepare` with a `y/N` console confirm. Native: `chdir` for the legacy flow
  plus the manifest scan (D14). Foam (`solvers/foam/cli_run.py`): `write_all` +
  `verify_and_release_scratch` after `_show_plots_*`.
- **Tests:** `test_run_preflight.py` part B uses `subprocess` `python -m blastlab --cli 1d`
  / `--hd13 x.json` / `--hd13-wall-export x.json` without the arguments → return code 2,
  and stderr names `--runs-dir`. `--hd13-new t.json` still works without them.
  `test_char_hd13_cli.py` (re-pinned in Step 7) passes with the arguments.

### Step 9 · R5 · Tk Run tab parity · **M**

- `gui/run_panel.py`: a Runs folder `CTkEntry` + folder button, and the name relabelled
  **Model** with the same tooltip. `gui/app.py`: the same `_model_target()` in
  `_run_single`, `_start`, `_resume_foam_run` and `_run_chain`, with `messagebox`
  refusals / `askyesno`, and `stage_dir` into `_solve_stage`. There is no Tk HD 1.3 form,
  so no HD 1.3 work here (HD1-16 Q4).
- The Setup filename fields hidden (D3) in `gui/forms.py`, in parity with Qt (the Qt
  hiding is done in Step 5's commit). The values pass through.
- **Tests:** all 14 `test_gui_*.py` (D8). `test_gui_char_case_form.py --update` changes
  only the hidden filename rows (own commit, diff reviewed), and so does
  `test_ui_char_case_form.py`.

### Step 10 · R6 · The gates and the new harness scenarios · **M**

- `_qa_ui_harness.py`: new group `M`:
  - `M01` refusal: empty folder, then bad name. Each message names its box, and there is
    no folder.
  - `M02` overwrite dialog: No leaves the folder untouched, Yes replaces it.
  - `M03` finished native 2D run: the folder listing equals the §2.2 rows, and `run.log`
    is non-empty.
  - `M04` chain: `1d\`, `2d\` and hand-offs at the root.
  - `M05` HD 1.3: report and `hd13_loads\` in the folder.
  Existing scenarios get `use_model`, and G01-G03 are rewritten for the model folder
  (D10). `_qa_gui_harness.py` gets the same `M01`-`M04`.
- Run §3 in full.

### Step 11 · R7 · Docs · **S** · merge-sensitive (`TODO.md`, `DONE.md`)

- `blastlab/README.md`: section "Where a run's files go": the §2.2 table, the chain and
  HD 1.3 layouts, the scratch rule, and the CLI arguments. Remove the chain-workspace text
  and the `--report` text. `docs/00-INDEX.md` gets a link if the README section is new.
- `DONE.md`: an `OUT-1` entry in the existing style. `TODO.md`: tick `OUT-1`, one line.
  Edit both with editor tools only (§4). Never rewrite them wholesale.

---

## 2. GUI screens touched

| Screen | Change | Toolkit |
|---|---|---|
| Run tab, control card | Runs folder box + Browse; Name → **Model**, mandatory | Qt + Tk |
| Run pre-flight | refusal message naming the box; overwrite Yes/No; kept-scratch message | Qt + Tk |
| Chain tab | workspace box and folder button removed; hint text | Qt + Tk |
| Setup → Outputs card | gauge / animation / profile / trigger filename rows hidden (D3, Q1) | Qt + Tk |
| Setup → 0-D (HD 1.3) Outputs card | `report_file` row removed | Qt |

## 3. Gates (CLAUDE.md §6/§9, plan §7)

- `cd blastlab/tests; python test_regression.py` must be **byte-identical before anything
  else is trusted**. It is run first and again after every step. No native path
  changes, so any difference is a stop.
- `python test_foam_writer.py`: goldens unchanged (no writer change in `OUT-1`).
- The fast matrix: `test_case_validate`, `test_foam_env`, `test_foam_resume`,
  `test_write_budget`, `test_char_exports`, `test_char_write_failure`, `test_char_meta`,
  `test_char_native_api`, `test_ui_run_panel`, `test_ui_chain`, `test_ui_results`,
  `test_ui_drain`, `test_ui_parity`, `test_ui_setup_form`, `test_layering`,
  `test_ui_no_vtk_in_main`, `test_ui_no_mpl_pyplot`, plus the new `test_model_folder` and
  `test_run_preflight`.
- **All 14 `test_gui_*.py`**, because `core/`, `solvers/`, `services/` and `output/` change
  (`CLAUDE.md` §9). `P2-8` may hang `test_gui_run_browser`: record it, do not fix.
- New `_qa_ui_harness.py` scenarios `M01`-`M05`, then **`gui-qa-tester` with
  screenshots** at the end (the owner's agent, not a stand-in).
- Goldens: re-pinned only where D10 or Step 7 names them. Each re-pin is its own commit,
  the diff is read line by line, and no number moves.

## 4. Rules for the implementer (CLAUDE.md §8.1)

- **Never route a file's content through PowerShell strings.** Every edit uses
  Read/Edit/Write. That includes `TODO.md`, `DONE.md` and anything with `·`, `→`, `—` or
  Hebrew. PowerShell may list, move and hash files. Damage check: `rg 'ג€|ג”'` over the
  touched files must come back empty.
- Commit messages containing `"` go to a file first: `git commit -F msg.txt`. git is at
  the MinGit path in CLAUDE.md §3. Commit, never push.
- New Python writes text as UTF-8 without BOM, `newline='\n'`.
- Never change a solver default, and never edit a committed test to make it pass. The
  D10 edits are authorised by owner decisions 8 and 14 and change setup, not verdicts.

## 5. Risks

1. **Deleting data.** `prepare(Yes)` runs `rmtree` on a user folder, and scratch release
   runs `rm -rf` in WSL. Protection: the `rmtree` target must be `folder_for(runs_dir,
   model)` with `runs_dir` an existing directory and the model name validated. A name like
   `..` or `C:` is refused by Step 1. The runs folder itself is never deleted, and a unit
   test asserts that `prepare` refuses when the resolved target equals `runs_dir` or lies
   outside it. Release happens only through the pure `release_decision` (fully tabled in
   tests) and only on the posix path recorded by this run's hooks. Never touch
   `~\Desktop` (CLAUDE.md §8.5): refuse a runs folder that *is* the Desktop root.
2. **Numbers must not move.** No solver, EOS, writer or coefficient is touched. Protection:
   `test_regression.py`, the foam goldens, `test_char_hd13.py` rel 1e-9 and
   `test_char_native_api` all unchanged.
3. **Losing a finished solve to a failed copy** (the `ux(2)` rule). Protection: `write_all`
   never raises, a failed row goes into `manifest['failed']`, and a partial copy keeps the
   scratch (Step 4 tests).
4. **GUI freeze.** `write_all` runs on the worker thread and the 3D figures take seconds.
   `prepare`'s `rmtree` runs on the GUI thread after the dialog; a folder with a big old
   `foam\` can take a while. That is acceptable for `OUT-1` (no VTK yet). If it is measured
   above ~1 s, move it into the stage.
5. **Test churn hiding a regression.** The D10 edits are many. Protection: those are
   separate commits touching setup lines only, and a reviewer diff shows no changed `check(`
   verdict.
6. **Run corpus** (§8.2). Tests that now create real folders use the private `runs_dir`
   from `ui/testing.private_settings`, never the owner's.
7. **Merge conflicts with HD1-16.** Protection: small edits in the merge-sensitive files,
   the merge before Step 7 and before the final gates, and the HD 1.3 goldens re-pinned
   **after** the merge.

## 6. Needs clarification — **answered by the owner, 2026-09-26 (binding)**

- **Q1 → hide the four filename fields; write the §2.2 names into the model folder; the
  `.gif` / `.mp4` animation-format choice stays visible.**
- **Q2 → enough.** The native `--cli` writes what it has into the model folder and lists
  the absent rows in `manifest.missing`; `legacy/` is not touched.
- **Q3 → yes.** The Results-tab manual export dialogs default to the result's model
  folder (when the result has one; otherwise as today). Small: `ui/exports.pick_target`
  and its Tk twin get a start directory. Add it to Step 5 (Qt) and Step 9 (Tk).
- **Q4 (raised by the Step 1-4 verifier, answered 2026-09-26) → overwrite only a folder
  blastlab created, or an empty one.** `prepare` writes a marker file
  (`.blastlab-model`, containing the model name and the creation time) the moment it
  creates the folder, before anything else. The overwrite question is asked only when
  the existing folder holds that marker or is empty; any other folder is refused before
  any dialog, with "<folder> was not created by blastlab - choose another model name".
  A run aborted at any point still carries the marker, so it can be overwritten. This is
  **Step 4b**, its own commit, done before Step 5; `test_model_folder.py` gets the three
  cases (marker → asked; empty → asked; foreign → refused, nothing deleted).
- **Step 8 (owner, 2026-09-26):** `solvers/foam/cli_run.py` reaches the model-folder
  service through the registration hook, exactly as Step 3 does — `test_layering` is
  not edited. The proper fix (a CLI layer outside `solvers/`) is a separate TODO item.
- **Also from the verifier, for Steps 5-11:** `ui/run_controller`, `gui/app` and `cli`
  must import `blastlab.services.model_folder` before calling `solve_stage(stage_dir=...)`;
  wrap `resume_foam_run` with `model_folder.stage_solve` so the jobs files are written
  and the release runs; carry `hooks.stage_manifest` / `hooks.folder_notice` in the queue
  message (a chain's next stage overwrites them); pass `n_cells` / `n_procs` from the
  pre-flight `ValidationReport` in `run_info`; after a release `meta['case_dir']` is gone,
  so the Results-tab VTK button needs a clearer "scratch released after a verified copy"
  text; the Desktop refusal also covers the model name; `validate_name` may also refuse
  `COM¹`-`COM³` / `LPT¹`-`LPT³` (Windows reserves them too). Pre-existing failures that are
  NOT this batch's: `test_foam_wsl_resume.py` (`init_state` on the fake spec, fails at
  d2f5cb1) and `test_char_validation.py::test_hd13_starter_case` (HD1-16 track; re-check
  after the master merge 139255b).

The original questions, for the record:

- **Q1 · The Setup filename fields (D3).** With decision 11 ("all outputs, always, no
  choice") the Gauge TSV, Animation, Profile out and trigger-remap filename boxes can no
  longer mean anything. This batch **hides** them and writes the §2.2 names. The animation
  format follows this machine: mp4 when ffmpeg is present, else gif. *Question:* should
  the `.gif` / `.mp4` choice stay as a visible option?
- **Q2 · Native `--cli` (D14).** The historical prompt flow is byte-pinned `legacy/` code
  and returns no Result. This batch puts its files into the model folder and lists the
  absent rows in `manifest.missing`. *Question:* is that enough, or should the native CLI
  get the full table, which means routing it through `solve_stage` instead of
  `legacy/_main`?
- **Q3 · Results-tab manual exports.** These still open a file dialog. `OUT-1` does not
  change them. *Question:* should the dialog default to the result's model folder? (A
  small follow-up.)

## 7. Needs the machine free

**Needs the machine free: check `wsl -d Ubuntu -- pgrep -a blastFoam` is empty and tell
the owner first.** Copy any run you care about out of `/root/blastlab_runs` before
anything that builds a GUI. Use `python -u`, no timeout, in the background.

- `python -u _e2e_model_folder.py` (new, WSL, tiny 3D of a few thousand cells):
  - Success: `foam\SHA256SUMS` verifies and the scratch is gone
    (`wsl -d Ubuntu -- test -d <posix>` fails).
  - Forced failure (kill `blastFoam` mid-run): the scratch is kept and the manifest says
    `"deleted": false`.
  - Stop: the scratch is kept.
- `python -u _e2e_ui_resume_foam.py`: a resumed run writes the folder and releases the
  scratch.
- `python -u _e2e_ui_chain_foam.py` / `_e2e_gui_chain_foam.py`: a real chain lands
  `MODEL\1d`, `2d` and `3d` with the hand-offs at the root.
- `python _e2e_hd13_gui.py`: HD 1.3 in a real window, with the report and loads in the
  folder.
- `python _qa_ui_harness.py --scenario M01,M02,M03,M04,M05` and the updated G01-G03 (real
  Qt window, `QT_QPA_PLATFORM` unset). `_qa_gui_harness.py` `M01`-`M04` for Tk.
- `gui-qa-tester` with screenshots of the Run tab (both toolkits), the refusal, the
  overwrite dialog and the Chain tab without the workspace box.

## 8. Remaining backlog (not in this batch)

- **`OUT-2`**, VTK output options (plan §3): next, on top of this folder.
- Owner acceptance of `OUT-1` + `OUT-2`, then **`OUT-5`** (the WSL disk rebuild).
- **`OUT-3`** (newest fields only) and **`OUT-4`** (the rest of the Viper matrix), in the
  owner's order.
- `HD1-16` / `HD1-17(a)`: finishing in the other session. Merge before Step 7.
- `P0-5` (settings file in the repo): independent, and makes every GUI batch safer.
- The rest of the HD1 and P1-P4 groupings are as in
  [2026-09-26-hd1-16-load-export.md §5](2026-09-26-hd1-16-load-export.md).
