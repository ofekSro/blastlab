# Batch p0-5-settings-reader-save · implement report

Worktree `C:\Users\rotem.ofek\blastlab-worktrees\todo`, branch `todo-batch`, `8aa08bc` → `25ce709`,
9 commits (one per task), tree clean. No push, merge or branch switch.

No real WSL solve and no real window, with one exception: the `foam_7b` script run
included `test_foam_postmortem.py`, which started a real blastFoam 2D solve at 10:41.
The orchestrator killed it; it is not a finding.

**Not run:**
- Held, screen busy: `test_gui_solver_mode`, `test_gui_status_cells`,
  `test_gui_title_preview1d` in the final gate run. All 14 `test_gui_*` passed at the
  Step 2b commit, but these three were not re-run after the later commits.
- Needs WSL: `test_foam_postmortem`, `test_foam_2d`, `test_foam_kb_anchor`,
  `test_foam_1d_vs_native`, `test_foam_parallel`, `test_foam_chamber`,
  `test_foam_features`, `test_foam_3d_smoke`, `test_foam_stop*`, every `_e2e_*`.

**Pre-flight:** with `BLASTLAB_SETTINGS` unset the old path gave `auto_cleanup False`;
the virtual copy read `"auto_cleanup": false`; `test_regression.py` PASS before the
first commit; `master...out-2-vtk-output` touches none of this batch's files.

## Tasks

**Step 1 · P0-5 items 1, 2, 5 · settings file in the repo · DONE `d702f90`**
- `core/settings.py` gains `REPO_ROOT` and `default_path()` (`<repo>\settings.json`).
  `config_path()` returns `BLASTLAB_SETTINGS` when set, otherwise `default_path()`.
- One-time migration inside `load()`, only when the override is unset and the repo
  file is missing:
  - Source order: the Store-Python virtual copy (newest mtime), then `%APPDATA%`.
  - `auto_cleanup` forced to `False`, a `migrated_from` key added, one stderr line.
  - No source is ever touched and an existing repo file is never overwritten.
- `gui/settings.py` re-exports `default_path`. `.gitignore` gains `/settings.json`,
  `/settings.json.*.tmp` and `/blastlab-crash.log`.
- Acceptance, all PASS:
  - Both paths print the worktree `settings.json`, and `git check-ignore` matches it.
  - Cases (a)-(g) pass.
  - A `settings.load()` from the worktree created the file from the virtual copy, and
    it holds `"auto_cleanup": false`. The "same bytes" check prints True.
  - `test_foam_env` and `test_hardware` pass unchanged.

**Step 2 · P0-5 item 3 · `env.cleanup_plan` dry run · DONE `3bf7da7`**
- `cleanup_plan(settings, now)` returns `[dict(dir, name, bytes, mtime)]`, oldest
  first. It ignores the flag and never deletes.
- `auto_cleanup` deletes exactly the plan. Its log lines and return value are
  unchanged.
- The test adds three fresh runs, because `keep_recent=3` protects them.
- Acceptance, all PASS: the plan returns the two old non-alive runs while a raising
  `delete_runs` is in place; with the flag on the sweep returns `(2, 7 GB)`; with the
  flag off it returns `(0, 0)` and makes no stub calls.

**Step 2b · Q3 · cleanup off by default, disk warning · DONE `15f3352`**
- `DEFAULTS['auto_cleanup'] = False`.
- `env.disk_warning_text` is a pure function. `env.disk_warning` and
  `env.start_disk_warning` run on a daemon thread and delete nothing.
  - The message names the size, the limit, the plan's run count and
    `--clean-foam-runs`.
  - Silent when WSL is unreachable.
- Wired in Qt `ui/app.py` (Run-log line plus `notify` warn) and Tk `gui/app.py`
  (log line plus `after(0, notify)`).
- The TODO P4-3 "Cleanup is now on" note is rewritten.
- Implementer's addition: the warning is skipped when `BLASTLAB_SETTINGS` is set,
  unless `private_ok=True`.
- Acceptance, all PASS: over the limit gives one warning; under the limit, a WSL error
  or empty info gives none; `delete_runs` is never called; the Qt and Tk sink checks
  pass; all 14 `test_gui_*` pass at this commit.
- One `test_ui_status_cells` failure, while the Tk suites ran in parallel, passed on
  two solo re-runs here and on the pre-batch tree: timing flake.

**Step 3 · P0-5 item 4, P4-3 · docs · DONE `5d11686`**
- `CLAUDE.md` §8.2 now carries the dry-run one-liner; the file is 432 lines.
- `docs/heavy-runs.md`, the TODO P0-4 note and P4-3 are updated.
- Acceptance:
  - PASS: the dry run prints `…\todo\settings.json False [4 run names]`.
  - PASS: the mojibake check is clean.
  - PARTIAL: one match remains, in the P0-5 task text itself; bookkeeping moves it.

**Step 4 · P1-7 · reader accepts `);` · DONE `806d81d`**
- `reader._nonuniform_body` accepts `)` or `);`. The docstring cites the owner
  decision; the guide (sec. 20, p. 144) does not define the terminator.
- `_e2e_vent_wall.read_start` is now the one-line reader call.
- One committed expectation flips, as P1-7 authorises: `test_vent_wall` "reader alone
  refuses it…" becomes "reader reads the writer's \");\" framing itself". It is the
  only changed `[PASS]` line out of 82.
- Acceptance, all PASS:
  - The new `test_foam_start_frame` passes criteria (a)-(d).
  - `test_foam_reader`, `_resume`, `_amr_ingest`, `_postmortem_decomposed` and
    `_writer` pass, with no golden touched.
- DEFERRED (WSL + screen): the player shows frame 0 for a chamber run and a chained
  1D → 2D run.

**Step 5 · P2-13 item 3 · `test_vent_wall` under pytest · DONE `1e0795f`**
- The three helpers become `_check_*`, and one `test_built_case()` calls them in the
  same order.
- Acceptance, all PASS: pytest gives 7 passed and 0 errors; the script output is
  identical.

**Step 6 · P1-18 Save half · DONE `0bb3f1f`**
- `ui/app._save_case` saves a case with `dim == 0` via `hd13_case.save_case`; every
  other case uses the blast save as before.
- Acceptance, all PASS:
  - (a) Saving the 0-D form writes schema `blastlab-hd13`.
  - (b) The saved file reopens into the 0-D form.
  - (c) Save → Open → Save is byte-identical, for the starter and for a clearing case.
  - (d) A 2D blast save is byte-identical to before.
  - The four Qt characterisation suites pass unchanged.
- The optional real-window check was not run.

**Step 7 · P2-13 item 4 amended by Q4 · failing checks fail under pytest · DONE `c944da6`**
- One `pytest_runtest_call` hookwrapper in `conftest.py`. It snapshots every
  `FAIL`/`FAILS`/`FAILED`/`FAILURES` list in the test's module and in every loaded
  `blastlab/tests` module, and fails the test if any grew, naming the checks.
- No test file is edited, and script mode is unchanged.
- Acceptance, all PASS: `test_refine` gives 10 passed under pytest and REFINE: PASS as
  a script. A scratch copy with one failing check gives 1 failed under pytest, and its
  script run exits 1.

**Step 7b · P2-14 item 7 · `read_probes` aligned by time · DONE `25ce709`**
- `rho` and `U` are attached only when their time column equals p's.
- On a mismatch the field is dropped, p is kept, and one stderr line plus a
  `warnings` list are added. It never raises.
- The matched case returns exactly today's dict, with no `warnings` key. A check pins
  the key set, and the result is identical to `8aa08bc` in values and dtypes.
- Acceptance, all PASS: the torn-tail check is unchanged; shifted times give p only
  plus a warning; identical times attach the arrays as before.

**P2-7:** already fixed by `c1f3101`, which also closes P2-8. P2-10 was closed by
`f8f57f9`, and `test_foam_wsl_resume` passes without WSL.

## Test results (final run)
- `test_regression.py`: PASS, byte-identical.
- Foam, no WSL, all PASS: `writer`, `reader`, `env`, `resume`, `amr_ingest`,
  `postmortem_decomposed`, `start_frame`, `wsl_resume`.
- Script suites, all PASS: `settings_path`, `hardware`, `case_validate`, `refine`,
  `vent_wall`, `vent3d_load`, `layering`.
- Qt offscreen, all PASS: `open_case`, `run_preflight`, `ui_status_cells`,
  `ui_parity`, `ui_setup_form`, `ui_char_hd13_run`, `ui_char_case_form`,
  `ui_no_vtk_in_main`, `ui_no_mpl_pyplot`.
- Tk, all PASS: `amr_form`, `char_case_form`, `char_exports`, `char_results_meta`,
  `char_write_failure`, `drain`, `gauge_summary`, `refine_preview`, `results_anim`,
  `results_fields`, `run_browser`. Three are held; see above.
- `pytest test_vent_wall.py test_refine.py test_settings_path.py`: 29 passed.

## pytest over the whole `blastlab/tests` directory
- Before (`8aa08bc`): 158 passed, 11 errors.
- After (`c944da6`): 171 passed, 8 errors.
- **No test newly fails**, so there are no findings.
- The 8 remaining errors predate the batch: "fixture 'tmp' not found" in
  `test_load_csv.py` (4) and `test_wall_clearing.py` (4).

## Files touched
- Repo root and docs: `.gitignore`, `CLAUDE.md`, `TODO.md`, `docs/heavy-runs.md`.
- Code: `blastlab/core/settings.py`, `blastlab/gui/settings.py`, `blastlab/gui/app.py`,
  `blastlab/ui/app.py`, `blastlab/ui/testing.py` (docstring only),
  `blastlab/solvers/foam/env.py`, `blastlab/solvers/foam/reader.py`.
- Tests: `blastlab/tests/conftest.py`, `_e2e_vent_wall.py`, `test_vent_wall.py`,
  `test_open_case.py`, `test_foam_reader.py`, and the new `test_settings_path.py` and
  `test_foam_start_frame.py`.

## Numerical changes
None. Intended behaviour changes:
- The t = 0 frame is now emitted for chamber and profile starts.
- `read_probes` drops shifted `rho`/`U` instead of misaligning them.
- Cleanup is off by default.

## References consulted
- `docs/references/INDEX.md`.
- blastFoam User Guide v6.0 sec. 20, p. 144.

## Open questions
1. The disk warning is skipped under `BLASTLAB_SETTINGS`. Acceptable, or should an
   explicit settings key control it?
2. Each checkout now has its own `settings.json`, and the OneDrive checkout risks sync
   locks.
3. `docs/wsl-disk-reclaim-plan.md:127` still names the `%APPDATA%` path. That file
   belongs to the OUT session.
4. P1-7's on-screen QA and the three held Tk suites are still pending.
