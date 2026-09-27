# Batch 2026-09-27 · p0-5-settings-reader-save

**Goal (one sentence):** move the settings file into the repo, where no Store-Python
virtualisation can hide it, and give cleanup a dry run (`P0-5`). Then fix the two
file-format bugs that make blastlab refuse its own files: the reader rejects the `);`
the writer emits (`P1-7`), and the Qt 0-D Save writes a file the app cannot reopen
(`P1-18`). Last, repair the two committed tests that pytest cannot run or cannot fail
(`P2-13` items 3 and 4).

- Worktree at planning time: `C:\Users\rotem.ofek\blastlab-worktrees\todo`, branch
  `todo-batch`, BASE `c73d4fc` (master, OUT-1 merged).
- Order source: `TODO.md`. The OUT section is skipped (another session owns it). HD1 has
  no implementable item that avoids the excluded files: `HD1-18` touches
  `ui/setup_spec.py` / `gui/forms.py`, and `HD1-14`, `HD1-4`, `HD1-16` step 2 and
  `HD1-17(b)` are WSL runs or owner-gated. So the batch starts at P0.
- **No WSL solve. No on-screen GUI QA is required.** Two optional checks are marked
  **[DEFERRED: WSL + screen]** and **[OPTIONAL: screen]**. All required gates are
  offscreen or script tests.
- **No numerical result moves.** No solver, coefficient, default or golden is touched.
  `test_regression.py` must stay byte-identical.
- Total size: **L**, made of 1 × M and 7 × S. It fits one uninterrupted session.

## Owner amendments, 2026-09-27 (answers to §4 Q1-Q4) - these OVERRIDE the text below

- **Q1 → new Step 7b (`P2-14` item 7), S.** `reader.read_probes` aligns `rho` / `U`
  with `p` **by the time column**, not by row count. If the times do not match (same
  count but different times, or a torn tail), it does **not raise**: it drops `rho` /
  `U`, keeps `p`, and emits one warning (stderr line
  `[blastlab] probes: <field> times do not match p - using p only (<reason>)`, and a
  `warnings` key in the returned dict listing the reason). A finished run is never
  failed by this. `backend.py` is not edited. The committed check
  `test_foam_reader.py:157-166` ("torn U file degrades to p-only, never misaligns")
  keeps its name and expectation. **Add** a check: equal row count but shifted times →
  p-only plus a warning; and a check: identical times → rho/U attached exactly as
  today (byte-identical arrays). No number of a normal run moves.
  Files: `blastlab/solvers/foam/reader.py` (`read_probes` only),
  `blastlab/tests/test_foam_reader.py` (checks added only).
- **Q2 → `P2-7` is already done** in the code (`test_foam_parallel.py:69-83` skips
  explicitly below 2 ranks). No edit. Close it in Step 8 bookkeeping with the commit
  that added it (`git log -S "rank_ceiling" -- blastlab/tests/test_foam_parallel.py`).
- **Q3 → new Step 2b, S.** `core/settings.DEFAULTS['auto_cleanup']` becomes `False`
  (owner decision 2026-09-27: deletion inside WSL is final, a full disk is
  recoverable; the sweep runs only when the file says `true`). **Plus a warning:** at
  GUI start (Qt `ui/app.py` and Tk `gui/app.py`, where `start_auto_cleanup` is
  called now), when `auto_cleanup` is off, a background thread (never the GUI thread,
  never blocking startup, silent when WSL is unreachable) computes the runs root size;
  if it exceeds `cleanup_max_gb`, the app shows one non-modal warning (Qt: status bar
  / log line; Tk: its equivalent) naming the size, the limit, and how many runs
  `cleanup_plan` would delete, and pointing to `--clean-foam-runs`. It deletes
  nothing. Build it in `env.py` next to `start_auto_cleanup` (e.g.
  `start_disk_warning(settings, warn)`), with the message text built by a pure
  function that is unit-tested. Test with stubs in `test_settings_path.py`: over the
  limit → one warning, under → none, WSL error → none, `delete_runs` never called.
  Update the comment/docstrings that say the default is on, and the "Cleanup is now
  on" note in TODO P4-3. Files: `core/settings.py`, `solvers/foam/env.py`,
  `ui/app.py`, `gui/app.py`, `test_settings_path.py`. Run all `test_gui_*` (§9).
- **Q4 → Step 7 is replaced by a sweeping fix in `blastlab/tests/conftest.py`.**
  A pytest hook (e.g. `pytest_runtest_call` hookwrapper, or an autouse fixture in
  conftest) records, for the test's module, the length of every module-level failure
  list the suites use (find the names: `FAIL`, `FAILS`, `FAILED`, `FAILURES`, ... -
  grep `def check(` in blastlab/tests and read what each appends to) before the test
  and fails the test after it if any grew, naming the new failing checks. **No test
  file needs editing for this**, so Steps 5 and 7 drop their per-file fixture;
  `test_refine.py` is then not edited at all unless its own `check()` needs it. Script
  mode is unchanged. Then run `python -m pytest -q -p no:cacheprovider` over the whole
  `blastlab/tests` directory (conftest already excludes unsafe files) before and after.
  **Every test that newly fails is a FINDING: record it (test, check name, output) in
  the implement report and in `docs/ENGINEERING_QUESTIONS.md`; never loosen, skip or
  edit the check, and do not stop the batch for it.** The P2-13 permission covers the
  mechanism; it does not cover changing any check. Prove the mechanism on a scratch
  copy as described in Step 7. Add a new TODO note under P2-13 only if findings exist.
  Tell the other session (blastfoam-24) the commit hash, because conftest affects
  their suites under pytest.

### Files this batch touches (to check against the other session's list)

| File | Steps |
|---|---|
| `blastlab/core/settings.py` | 1 |
| `blastlab/gui/settings.py` (re-export line only) | 1 |
| `.gitignore` | 1 |
| `blastlab/solvers/foam/env.py` (`cleanup_plan` added, `auto_cleanup` rebuilt on it; lines ~796-878 only) | 2 |
| `CLAUDE.md` §8.2, `docs/heavy-runs.md` (line ~123) | 3 |
| `blastlab/solvers/foam/reader.py` (`_nonuniform_body` only) | 4 |
| `blastlab/tests/_e2e_vent_wall.py` (`read_start` only) | 4 |
| `blastlab/tests/test_vent_wall.py` | 4, 5 |
| `blastlab/ui/app.py` (`_save_case` only) | 6 |
| `blastlab/tests/test_open_case.py` (checks added) | 6 |
| `blastlab/tests/test_refine.py` | 7 |
| new `blastlab/tests/test_settings_path.py` | 1, 2 |
| new `blastlab/tests/test_foam_start_frame.py` | 4 |
| `TODO.md`, `DONE.md` (ticks and records, `/todo` style, Edit tool only) | 3, 8 |

**None of these is on the excluded list.** Not touched: `writer.py`, `runloop.py`,
`backend.py`, `vtk_export.py`, `services/{model_folder,exports,validation}.py`,
`models/{case,fields}.py`, `ui/{setup_spec,fieldform,case_form,results_panel}.py`,
`gui/{forms,results_panel}.py`, `output/{vtk_series,animation}.py`,
`solvers/{jobs,hooks}.py`, and either `README.md`. Step 4 **reads** `writer._nonuniform` /
`writer._render_fields` and **calls** `backend._initial_frame` from a test, but edits
neither file.

> **Coordination check before Step 1 (caller or implementer).** The other session's
> branch `out-2-vtk-output` has commits the planner did not inspect. One of them is
> `5237e51`, "readers of a finished run warn…". Before starting, run
> `git diff --stat master...out-2-vtk-output` and confirm it does not touch
> `solvers/foam/{env,reader}.py`, `core/settings.py`, `ui/app.py`,
> `tests/{test_vent_wall,_e2e_vent_wall,test_open_case,test_refine}.py`, `.gitignore`
> or `docs/heavy-runs.md`. If it touches any of them, move that step to the end and
> keep its diff minimal. `TODO.md` / `DONE.md` / `CLAUDE.md` will conflict at merge
> whatever happens, so keep those edits small and local.

---

## 0. Pre-flight · CLAUDE.md §8.2 / §8.1

1. **Before Step 1** (the old path is still in force), run
   `python -c "from blastlab.core import settings as s; print(s.config_path(), s.load()['auto_cleanup'])"`
   from the worktree root with `BLASTLAB_SETTINGS` unset. It must print `False`. Open
   the virtual copy
   `%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\Roaming\blastlab\settings.json`
   with the Read tool and confirm `"auto_cleanup": false`. **Do not** call
   `env.auto_cleanup(settings.load())` as a check, because it deletes (TODO `P0-5` item 4).
2. `cd blastlab/tests; python test_regression.py` is green **before** the first commit.
   That run is the baseline for "byte-identical".
3. Every offscreen `test_ui_*` / `test_gui_*` suite uses `ui/testing.private_settings()`.
   Do not unset `BLASTLAB_SETTINGS` inside a GUI test.
4. State measured at planning time (c73d4fc): `python test_refine.py` gives REFINE: PASS, and
   `python test_vent_wall.py` gives VENT WALL: PASS.
   `python -m pytest test_vent_wall.py test_refine.py -q -p no:cacheprovider` gives
   **16 passed, 3 errors**. The three errors are `test_evidence`, `test_tails` and
   `test_step2_driver`, all "fixture not found".
5. Every edit to `CLAUDE.md` (it has Hebrew in it), `TODO.md` and `DONE.md` is made with
   Edit/Write, never through PowerShell strings (§8.1). Afterwards,
   `rg 'ג€|ג”'` over every touched file must come back empty. Commit messages go through
   `git commit -F <file>`.

---

## 1. Tasks, in order

Each step leaves the app runnable. Commit style is `area: what changed (ID)`.

### Step 1 · `P0-5` items 1, 2 and 5 · The settings file lives in the repo, seeded once with cleanup off · **M**

Original TODO text, verbatim:

> **Decision (owner):** the settings file lives **in the repo**, at one explicit path
> that no virtualisation can redirect.
>
> 1. `settings.default_path()` returns a repo-local file (e.g. `<repo>/settings.json`,
>    next to `blastlab/`), added to `.gitignore` - it carries machine-specific `hw_*`
>    fields and must never be committed.
> 2. One-time migration: if the repo file is missing, seed it from the virtual copy (or
>    the `%APPDATA%` one), and **force `auto_cleanup: false`** in the result. Log which
>    source was used. Never delete the old files.
> 5. Tests: `default_path()` is inside the repo and ignored by git; migration forces
>    cleanup off; `cleanup_plan` touches no file. Tk and Qt both read the same file
>    (run the `test_gui_*` suites - §9).
>
> Acceptance: `python -c "from blastlab.core import settings; print(settings.default_path())"`
> prints the repo path under Store Python, and the Read tool sees the same bytes the app
> loads.

**Found in the code:** `core/settings.py:66-74` `config_path()` returns
`BLASTLAB_SETTINGS` or `%APPDATA%\blastlab\settings.json`. Under Store Python, a read
or write of that path is redirected to the `LocalCache\Roaming` copy. The callers are
`load` / `save` (`settings.py:93,115`), `ui/crashlog.py:50` (the crash log goes in the
same directory), `gui/settings.py:6` (re-export for Tk) and
`tests/_qa_gui_harness.py:273` (asserts `config_path() == BLASTLAB_SETTINGS`). blastlab
is **not** pip-installed (checked: `find_spec('blastlab')` from a neutral directory
returns None), so the repo root is three `dirname`s above `core/settings.py`.

**Interpretation chosen (write each point into the module docstring):**
- **Names.** Add `default_path()`, which returns `<repo>\settings.json` with `<repo>` =
  the parent of the `blastlab/` package directory. Keep `config_path()`: it returns
  `BLASTLAB_SETTINGS` when set, and `default_path()` otherwise. None of the three
  callers changes, and the harness assertion still holds.
- **Migration trigger.** The migration runs inside `load()` only when the path in use
  is `default_path()`, i.e. `BLASTLAB_SETTINGS` is unset, and that file does not
  exist. Under the test override it never runs, so no test can seed or touch the
  owner's file.
- **Source order.** The first existing file among these is the source:
  1. `%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3*_*\LocalCache\Roaming\blastlab\settings.json`
     (glob; newest mtime if several). This is the file the app actually read until now.
  2. `%APPDATA%\blastlab\settings.json`.

  Both are read with plain `open(..., encoding='utf-8')`. The source must be a JSON
  dict, and an unreadable source is skipped.
- **Result.** The new file is the source dict with `auto_cleanup` forced to `False`
  and a `migrated_from` key holding the source path. It is written through the
  existing atomic `save()`. The process prints one stderr line:
  `[blastlab] settings: created <repo>\settings.json from <source> (auto_cleanup forced off)`.
  The source files are never written, renamed or deleted.
- **No source.** Nothing is created. `load()` returns DEFAULTS with
  `auto_cleanup=False`, as it does today for a missing file. The first `update()`
  then writes the file with `auto_cleanup: false`.
- **An existing repo file is never overwritten** by the migration.
- **Every checkout has its own file.** That covers this worktree, the out-track
  worktree and the OneDrive checkout. Each one is seeded from the same source on its
  first run. This is a consequence of "in the repo", and it is recorded here, not
  treated as a bug.
- **The crash log follows the settings file.** `ui/crashlog.log_path()` is
  `dirname(config_path())`, so after this step `blastlab-crash.log` lands in the repo
  root. `crashlog.py` stays as it is, and `.gitignore` gains `/blastlab-crash.log`
  next to `/settings.json`. Both entries are anchored to the root, so they cannot
  match a fixture.
- `gui/settings.py` re-exports `default_path` as well, so Tk and Qt resolve the same
  function.

**Files:** `blastlab/core/settings.py`, `blastlab/gui/settings.py`, `.gitignore`, new
`blastlab/tests/test_settings_path.py`. This is a plain script with `check()` / `FAILS`
like its siblings. It is also collectable by pytest, and each `test_*` function must
fail under pytest when a check fails (see Step 7's mechanism).
**GUI screens:** none.
**References:** none. No standard or solver keyword is involved.
**Depends on:** nothing.

**Acceptance:**
- From the worktree root with `BLASTLAB_SETTINGS` unset,
  `python -c "from blastlab.core import settings; print(settings.default_path()); print(settings.config_path())"`
  prints `C:\Users\rotem.ofek\blastlab-worktrees\todo\settings.json` twice.
- `git check-ignore -v settings.json blastlab-crash.log` names a `.gitignore` rule for
  both. After a GUI or CLI start, `git status --short` shows neither file.
- `python test_settings_path.py` passes. It covers these cases, with `LOCALAPPDATA`,
  `APPDATA` and the repo root pointed at temp dirs through a module-level hook or
  monkeypatch:
  - (a) `default_path()` is `<root>\settings.json`, and `<root>` holds `blastlab\`.
  - (b) The source is a virtual copy with `auto_cleanup: true`, `cleanup_max_gb: 150`,
    `cleanup_keep_recent: 10` and a `runs_dir`. The created file has
    `auto_cleanup is False`, every other source key identical, and `migrated_from` =
    the source path. The source file's bytes and mtime are unchanged. The stderr line
    names the source.
  - (c) With only the `%APPDATA%` file present, the file is seeded from it.
  - (d) With no source, no file is created, and `load()['auto_cleanup'] is False`.
  - (e) With `BLASTLAB_SETTINGS` set, no migration runs and nothing under `<root>` is
    created.
  - (f) An existing `<root>\settings.json` is left byte-identical.
  - (g) `blastlab.gui.settings.config_path() == blastlab.core.settings.config_path()`.
- After the first real start in this worktree, the Read tool on `<repo>\settings.json`
  shows `"auto_cleanup": false`. Also,
  `python -c "import json; from blastlab.core import settings as s; d=json.load(open(s.default_path(), encoding='utf-8')); print(all(s.load()[k]==v for k,v in d.items()))"`
  prints `True`: the app loads the bytes the Read tool sees.
- `python test_foam_env.py` and `python test_hardware.py` pass unchanged.

### Step 2 · `P0-5` item 3 · `env.cleanup_plan`, a dry run that `auto_cleanup` is built on · **S**

Original TODO text, verbatim:

> 3. A dry run: `env.cleanup_plan(settings)` returns what the policy *would* delete
>    (names, sizes, mtimes) and deletes nothing; `auto_cleanup` is built on it.

**Found in the code:** `solvers/foam/env.py:824-860` `auto_cleanup` does four things
in one function: flag check, listing (`run_dirs`, `run_info`, `runs_alive`), policy
(`cleanup_policy`, pure, `:796`) and `delete_runs`. `cli_run.py:157-180` (the
`--clean-foam-runs` path) uses `cleanup_policy` directly and is left alone.

**Interpretation chosen:**
- `cleanup_plan(settings=None, now=None)` returns a list of
  `dict(dir, name, bytes, mtime)` in `cleanup_policy`'s order (oldest first). It uses
  the same thresholds as today, **regardless of the `auto_cleanup` flag**, so the owner
  can see what switching the sweep on would delete. The docstring says so. When WSL
  cannot be reached or there are no runs, it returns `[]`. It never calls
  `delete_runs`.
- `auto_cleanup(settings, log, now)` returns `(0, 0)` without listing anything when the
  flag is off, as it does today. Otherwise it calls `cleanup_plan`, then `delete_runs`
  on exactly those dirs. Its log lines and return value are unchanged.
- The plan and the sweep use the same settings merge (`DEFAULTS` updated with
  `settings`), so they cannot disagree.

**Files:** `blastlab/solvers/foam/env.py` (this function pair only),
`blastlab/tests/test_settings_path.py` (the cleanup section).
**GUI screens:** none. The GUI startup call `start_auto_cleanup` does not change.
**Depends on:** nothing. It is ordered after Step 1 so that the Step 3 docs describe
both.

**Acceptance:**
- In `test_settings_path.py`, stub `env.run_dirs`, `env.run_info` and `env.runs_alive`
  (four fake runs: one alive, one unknown, two old), and replace `env.delete_runs` with a
  function that **raises**. `env.cleanup_plan(dict(auto_cleanup=False, cleanup_max_age_days=14))`
  returns the two old, non-alive runs with their bytes and mtimes, and does not raise.
- With `delete_runs` replaced by a recorder and the flag on, `env.auto_cleanup(...)`
  deletes exactly the dirs `cleanup_plan` returned and returns `(2, <their bytes>)`.
  With the flag off it returns `(0, 0)` and calls none of the four stubs.
- `python test_foam_env.py` passes unchanged. That includes "auto_cleanup honours the
  opt-out without touching WSL".

### Step 3 · `P0-5` item 4, and `P4-3` · Docs point at the new path and the dry run · **S**

Original TODO text, verbatim:

> 4. CLAUDE.md §8.2, the P0-4 note below and P4-3 point at the dry run and the new path.
>    Replace the "check" `env.auto_cleanup(settings.load())`, which deletes.

**Found:** the deleting "check" is written in 4 live places: `CLAUDE.md:368`,
`docs/heavy-runs.md:123`, `TODO.md` P0-4 note (~line 325) and `TODO.md` P4-3 (~line
1097, which also names `%APPDATA%\blastlab\settings.json`). `docs/wsl-disk-reclaim-plan.md`
line 127 (its pre-check P3) also names the `%APPDATA%` file. That document belongs to
`OUT-5`, which the other session owns, so it is **not** edited here. It is listed for
that session in §5. Old batch plans, QA reports and `docs/archive/` are records and
stay as written.

**Interpretation chosen:** the new check is
`python -c "from blastlab.core import settings as s; from blastlab.solvers.foam import env; d=s.load(); print(s.config_path(), d['auto_cleanup'], [r['name'] for r in env.cleanup_plan(d)])"`.
It must print `False`, and the list shows what the sweep *would* take if it were on.
`CLAUDE.md` is at 429 lines and capped at 500, so §8.2 is rewritten in place with net
growth of at most 3 lines.

**Files:** `CLAUDE.md` (§8.2 only), `docs/heavy-runs.md` (the one line), `TODO.md`
(P0-4 note and P4-3 text only; ticking `P0-5` waits until Step 8).
**Depends on:** Steps 1 and 2.

**Acceptance:**
- `rg -n "auto_cleanup\(settings\.load" CLAUDE.md docs/heavy-runs.md TODO.md` returns
  nothing.
- `(Get-Content CLAUDE.md).Count` is ≤ 500, and `rg 'ג€|ג”' CLAUDE.md TODO.md docs/heavy-runs.md`
  is empty.
- The new check, run from the worktree, prints `<worktree>\settings.json False [...]`.

### Step 4 · `P1-7` · The reader accepts the `);` the writer emits · **S**

Original TODO text, verbatim:

> `writer._nonuniform` / `_render_fields` close a nonuniform list with `);`, but
> `reader._nonuniform_body` requires a bare `)`. **Consequences:**
> `backend._initial_frame` / `_initial_frame3d` silently skip the t = 0 frame for chamber
> and profile stages, and `_time_is_whole` fails on such a start dir. Found by
> hd1-wall-load A3 (see `docs/batches/2026-09-24-hd1-wall-load.*.md`), which worked
> around it locally in `_e2e_vent_wall.read_start`.
>
> **Decision (owner, 2026-09-25): fix the reader.** `reader._nonuniform_body` accepts both
> `)` and `);`. Both are valid OpenFOAM, and OpenFOAM already reads the writer's `);`. The
> writer and its goldens stay byte-identical. Add a test that writes a chamber / profile
> `0/` field with `writer`, reads it with `reader`, and checks the t = 0 frame is present.
> Once the reader handles it, remove the local workaround in
> `_e2e_vent_wall.read_start`. Qt GUI QA: the player now shows frame 0 for a chamber and
> a chained (1D → 2D) run.

**Found in the code:** `reader.py:110-113` has the check
`if lines[k].strip() == ')'`. `_nonuniform_body` feeds `scalar_size`, `read_scalar`
and `read_vector`, so all three are fixed at once. Binary files are not affected,
because `_binary_internal` checks the byte after the data (`b')'`). The one committed
check that pins the bug is `tests/test_vent_wall.py:535-541`, "reader alone refuses
it - the mismatch Step 2 works around". `_e2e_vent_wall.read_start`
(`_e2e_vent_wall.py:810-840`) is used by `start_state` (`:851-860`) and by
`test_vent_wall.test_start_reader`. No "frozen" block exists in `_e2e_vent_wall.py`
(checked; the frozen C6-C13 block is in `_e2e_vent_3d.py`, which is not touched).

**Interpretation chosen:**
- The list terminator is a line whose `strip()` is `')'` or `');'`. A vector entry is
  `(a b c)` on one line and can never equal either. A torn file with no terminator
  still raises `unterminated internalField list`.
- `read_start(path, n, vector=False)` keeps its signature, so `start_state` does not
  change. Its body becomes the one-line call to `reader.read_vector` /
  `reader.read_scalar`, and the fallback parse is deleted. Its docstring cites `P1-7`.
- In `test_vent_wall.test_start_reader`, the check "reader alone refuses it…" becomes
  "reader reads the writer's `);` framing itself", which asserts
  `np.array_equal(reader.read_scalar(paths['p'], 3), [...])`. **This changes the
  expected value of a committed test.** The owner decision `P1-7` authorises it: the
  check pinned the bug the decision fixes, and removing the workaround is part of the
  decision text. It goes in its own commit citing `P1-7`. Every other check in that
  function keeps its name and expectation (the count mismatch and the torn file are
  still refused, and an OpenFOAM-framed file still reads).
- The "t = 0 frame is present" test runs without WSL. It builds a temp case dir whose
  start dir holds `p` written by `writer._render_fields(writer._nonuniform(...))`,
  with a `SimpleNamespace` spec (`case_unc`, `start_dir`, `n_cells`, `t_start`, `dim`,
  `grid`, `mesh0=None`, `remap=None`, `solid=None`, as `test_foam_amr_ingest.py:198` does)
  and a stub `hooks.frame`. It covers a 1D profile start (`start_dir='t0'`-style name,
  `t_start > 0`) and a 2D chamber start.

**Files:** `blastlab/solvers/foam/reader.py` (`_nonuniform_body` and its docstring),
`blastlab/tests/_e2e_vent_wall.py` (`read_start` only),
`blastlab/tests/test_vent_wall.py` (`test_start_reader` only), new
`blastlab/tests/test_foam_start_frame.py`.
**References:** `blastfoam-guide`, sec. 20 (double Mach reflection example, printed
p. 144, sidecar line ~5290). It is the guide's only field-file listing and shows only
`internalField uniform`. **The guide does not define the nonuniform-list terminator.**
The authority for "`);` is valid" is the owner decision and the fact that blastFoam
has read the writer's `0/` files in every chamber and profile run. Say so in the
docstring, and do not cite the guide for it.
**Depends on:** nothing. Step 5 edits the same test file afterwards.

**Acceptance:**
- `python test_foam_start_frame.py` (new) passes and covers the following:
  - (a) Scalar and vector fields framed by the writer read back with `np.array_equal`
    to the values written.
  - (b) `reader.scalar_size` of such a file returns its count.
  - (c) `backend._initial_frame` emits exactly one frame at `spec.t_start` for the 1D
    profile start and for the 2D chamber start, with values equal to what was written.
  - (d) The same file with its `);` line removed still raises `ValueError` containing
    `unterminated`.
- `python test_vent_wall.py` passes. The diff of its `[PASS]` lines against
  pre-flight item 4 differs only in the one renamed check.
- `python test_foam_reader.py`, `test_foam_resume.py`, `test_foam_amr_ingest.py` and
  `test_foam_postmortem_decomposed.py` pass unchanged. `python test_foam_writer.py`
  passes with **no golden touched** (the writer is not edited).
- `rg -n "unterminated internalField list" blastlab/tests/_e2e_vent_wall.py` returns
  nothing.
- **[DEFERRED: WSL + screen]** The TODO's own QA: "the player shows frame 0 for a
  chamber and a chained (1D → 2D) run". This needs a real blastFoam run and a real
  window. It is not part of this batch's gate. Record it in the `P1-7` DONE entry as
  "offscreen equivalent passed (test_foam_start_frame), on-screen QA pending", so the
  owner can schedule it with the next WSL session (§8.6 first).

### Step 5 · `P2-13` item 3 · `test_vent_wall.py`: pytest collects only real tests · **S**

Original TODO text, verbatim:

> **The owner explicitly permits editing these four committed tests (§9), and only
> these.** The rule is: **fix the test's mechanism, never its threshold or its expected
> value.** One commit per test, each citing this decision.
> 3. `test_vent_wall.py`: `test_evidence` / `test_tails` / `test_step2_driver` take
>    arguments, so pytest reports 3 "fixture not found" errors. Rename the helpers or
>    give them fixtures so pytest collects only real tests, with the same checks.

**Found:** `test_vent_wall.py:147` `test_evidence(case, cfd, info)`, `:240`
`test_tails(case)` and `:571` `test_step2_driver(case)`. `main()` (`:733-744`) builds
`case = ew.build()` and `cfd, info = asm.build_vent_case(case)` and passes them in.
The error was reproduced at planning time (pre-flight item 4).

**Interpretation chosen:** rename the three to `_check_evidence`, `_check_tails` and
`_check_step2_driver`, which pytest does not collect. Add one zero-argument
`test_built_case()` that does exactly what `main()` does for them: build once, then
call the three in the same order. Under pytest the same checks therefore still run.
`main()` calls the renamed functions directly, so the script's output order and check
names do not change. No check, threshold or expected value changes. The failing-check
mechanism from Step 7 is applied here too, so `test_built_case` and the others fail
under pytest when a check fails. That is also mechanism, and it is inside the owner's
permission for this file.

**Files:** `blastlab/tests/test_vent_wall.py`.
**Depends on:** Step 4 (same file; do it second to keep each commit to one purpose).

**Acceptance:**
- `cd blastlab/tests; python -m pytest test_vent_wall.py -q -p no:cacheprovider` reports
  **0 errors**. `test_built_case` is among the passed tests, and the check names it
  prints (`-s`) include the evidence, tails and Step 2 driver checks.
- `python test_vent_wall.py` gives VENT WALL: PASS with the same `[PASS]` lines as after
  Step 4, in the same order.

### Step 6 · `P1-18` (the Save half) · The Qt 0-D form saves an HD 1.3 case file · **S**

Original TODO text, verbatim:

> "Open case..." refuses every HD 1.3 JSON, including the `--hd13-new` starter, with "Not
> a blastlab case file". "Save case..." on the 0-D form writes a **blast** case
> (`schema "blastlab-case"`, version 13, dim 0), which the app then also refuses to open.
> The values survive; the schema does not. The cause: `ui/app.py:19` imports only the
> blast `load_case` / `save_case`, and `models/case.py:372-377` rejects the HD 1.3
> schema and has no dim 0. This was already so at `01ab997`, before HD1-16. The HD 1.3
> reader and writer (`models/hd13_case`) round-trip byte-identically at form level, so
> the fix is to dispatch on the schema in Open and on the solver mode in Save. Evidence:
> `docs/qa/2026-09-26-hd1-16/QA_REPORT.md` F1, screenshots `F1_*`, `F2_reopen_*`.
> Acceptance: Open loads the starter and a clearing case into the 0-D form; Save → Open
> round-trips byte-identically; blast cases are unchanged; Qt GUI QA.

**Found in the code:** **the Open half is already done.** `13f78e2` (OUT-1 QA F2) added
`models.case.load_any_case`, and `ui/app.py:430` uses it. `tests/test_open_case.py`
covers an HD 1.3 `MODEL.json`, blast cases and a foreign file in Qt and Tk. The Save
half is still open: `ui/app.py:475-484` `_save_case` always calls the blast
`save_case` (`core.case` re-export of `models/case.save_case`). For the 0-D form,
`setup.get_case()` returns a `models.hd13_case.DeflagrationCase` (`dim = 0`), and
`hd13_case.save_case` (`hd13_case.py:220`) writes `schema 'blastlab-hd13'`.

**Interpretation chosen:**
- Dispatch happens in `ui/app.py` only. When `getattr(case, 'dim', None) == 0`, the
  save calls `hd13_case.save_case(case, path)`; every other case calls the blast
  `save_case` as today. **`models/case.py` is not edited** (it is on the excluded
  list), so no `save_any_case` is added there. The dialog filter text may say
  "blastlab case (*.json)" for both.
- "Save → Open round-trips byte-identically" is pinned like this. Open the starter
  (`hd13_case.write_starter_case` or the existing HD 1.3 fixture in `test_open_case.py`)
  and save it to B. Open B and save it to C. **B and C must be byte-identical**, and
  `case_to_dict(load(B)) == case_to_dict(load(starter))`. A clearing case
  (`clearing=True, wall_H_m=3, wall_W_m=4`) passes the same round trip.
- The Tk app has no HD 1.3 form (owner Q4, 2026-09-26), so there is nothing to change on
  the Tk side, and `blastlab/gui/` is not touched.

**Files:** `blastlab/ui/app.py` (`_save_case` and one import), `blastlab/tests/test_open_case.py`
(new checks in `part_qt`, patching `ui.app.dialogs.save_file` as
`test_char_exports.py:217-238` does).
**GUI screens:** Qt main window, Save case… (Ctrl+S) with the 0-D form active.
**Depends on:** nothing.

**Acceptance:**
- `python test_open_case.py` passes with new Qt checks for the following:
  - (a) Save from the 0-D form writes JSON whose `schema` is `blastlab-hd13`.
  - (b) `win._open_case(B)` gives no error, `setup.dim == 0`, and the case equals the
    starter's `case_to_dict`.
  - (c) B and C are byte-identical, for the starter and for a clearing case.
  - (d) Saving a 2D blast case writes bytes identical to `models.case.save_case` of the
    same case into a second temp file.
- `python test_ui_char_hd13_run.py`, `test_ui_parity.py`, `test_ui_setup_form.py` and
  `test_ui_char_case_form.py` pass **unchanged**, with no golden touched.
- **[OPTIONAL: screen]** A real-window check (`_e2e_hd13_gui.py`-style, private
  settings) of Save → Open on the starter. The offscreen test drives the same slot,
  so this is not required.

### Step 7 · `P2-13` item 4 · `test_refine.py`: a failing check fails under pytest too · **S**

Original TODO text, verbatim:

> 4. `test_refine.py`: `check()` only appends to a list, so its 10 pytest functions
>    cannot fail. Make a failing check fail, both under pytest and as a script. **Any
>    real failure this uncovers is reported to the owner as a finding.** Do not loosen it
>    to pass.

**Found:** `test_refine.py:22-29` has `check()` appending to `FAILS`, and `:661-674`
has the script `main`, which already exits 1 on any FAIL. Under pytest, each of the 10
`test_*` functions returns normally whatever `FAILS` holds. At planning time both
modes pass (REFINE: PASS; pytest 10 passed).

**Interpretation chosen:** no repo-wide helper, because the owner's permission covers
these tests only. Inside `test_refine.py`, an autouse function-scoped pytest fixture
records `len(FAILS)` before each test and asserts after it that no new name was
appended. The failure message lists the new failing check names. The fixture is
defined only when `pytest` imports cleanly (guarded `try: import pytest`), so the
plain script needs no pytest. Script mode stays as it is: it prints every check and
exits 1 if any failed. No check, threshold or expected value changes. Step 5 applies
the same mechanism, in the same few lines, to `test_vent_wall.py`, and Step 1 to the
new `test_settings_path.py`.

**Files:** `blastlab/tests/test_refine.py`.
**Depends on:** nothing. Step 5 reuses its pattern, so if the steps are done in
number order, write this pattern first and paste it into Step 5.

**Acceptance:**
- `python -m pytest test_refine.py -q -p no:cacheprovider` gives 10 passed, and
  `python test_refine.py` gives REFINE: PASS.
- The mechanism is proven on a **scratch copy** (in the session scratchpad, never
  committed) with one `check(..., False)` inserted: pytest reports exactly 1 failed,
  naming that check, and `python <copy>` exits 1. Delete the copy afterwards.
- If the real file shows any FAIL in either mode, stop and report it to the owner as a
  finding (TODO `P2-13` item 4). Do not change the check.

### Step 8 · Gates and bookkeeping · **S**

Run these and paste the tail of each (TODO "Standing rules"):
- `cd blastlab/tests; python test_regression.py`: **byte-identical**, with no baseline
  touched. Nothing in this batch is on a native-solver path, so any difference means stop.
- The foam group, no WSL: `test_foam_writer.py` (no golden touched), `test_foam_reader.py`,
  `test_foam_env.py`, `test_foam_resume.py`, `test_foam_amr_ingest.py`,
  `test_foam_postmortem_decomposed.py`, `test_foam_start_frame.py` (new), and
  `test_foam_wsl_resume.py`. The last one covers W3 without WSL, per its own
  docstring.
- `test_settings_path.py` (new), `test_hardware.py`, `test_case_validate.py`,
  `test_refine.py`, `test_vent_wall.py`, `test_vent3d_load.py`, `test_layering.py`.
- Qt, offscreen: `test_open_case.py`, `test_run_preflight.py`, `test_ui_status_cells.py`,
  `test_ui_parity.py`, `test_ui_setup_form.py`, `test_ui_char_hd13_run.py`,
  `test_ui_char_case_form.py`, `test_ui_no_vtk_in_main.py`, `test_ui_no_mpl_pyplot.py`.
- Tk (§9, because `core/settings.py` is a shared neutral module): every
  `python test_gui_*.py`. `test_gui_run_browser.py` already injects `warner=`
  (`test_gui_run_browser.py:84`, see below), so the `P2-8` hang should not happen. If
  it does, record it and do not "fix" it here.
- pytest: `python -m pytest test_vent_wall.py test_refine.py test_settings_path.py -q -p no:cacheprovider`
  gives 0 errors and 0 failures.

**Bookkeeping in `TODO.md` / `DONE.md`** (Edit tool only, `/todo` style, stable IDs
kept). Tick and record `P0-5`, `P1-7` (on-screen QA pending), `P1-18` (Open half by
`13f78e2`, Save half here), and `P2-13` items 3 and 4. The planner also found **two
TODO entries that the code already closes**. Confirm each and then move it to DONE.md
with its commit:
- **`P2-8`** (Tk run browser modal): `gui/run_browser.py:37-39,55` takes `warner=`, and
  `test_gui_run_browser.py:84` injects it with a `P2-8` comment. Find the commit with
  `git log -S "warner" -- blastlab/gui/run_browser.py`.
- **`P2-10`, which is `P2-13` item 1** (`test_foam_wsl_resume.py` stub spec):
  `f8f57f9` added `init_state=None` (`test_foam_wsl_resume.py:145`). Its commit message
  says every W3 check passes. The TODO's "run it for real in WSL" does not apply, because
  the file's docstring says all three pieces are covered without WSL. Confirm by running
  it in this step, then close the entry.
- **`P2-7`**: already fixed in `test_foam_parallel.py:69-83` (owner confirmed
  2026-09-27). Close it with its commit.
Also tick `P2-14` item 7 and record the Q3 default change + disk warning.
Add the two new suites to TODO's test matrix.

---

## 2. GUI screens touched

| Screen | Change | Toolkit |
|---|---|---|
| Qt main window, Save case… (Ctrl+S) with the 0-D form active | writes an HD 1.3 file, which then reopens | Qt only (Tk has no HD 1.3 form) |
| None other | Settings move, and nothing on screen names the path | n/a |

---

## 3. Risks

1. **The run corpus (§8.2) is the risk that matters most.** Step 1 creates the file
   that decides whether the startup sweep deletes WSL runs. A migration that carried
   `auto_cleanup: true` across would switch the sweep back on in the app's real file.
   Protection:
   - `test_settings_path.py` (b) seeds from a source that says **true** and requires
     **False**.
   - The migration never runs under `BLASTLAB_SETTINGS`.
   - Right after Step 1, read `<repo>\settings.json` with the Read tool before
     anything builds a real window.
   - The deleting "check" is removed from the docs in Step 3 and replaced by the dry
     run.
   - Before any real-window session, copy out any run you care about
     (`/root/blastlab_runs`).
2. **`DEFAULTS['auto_cleanup']` stays `True`.** A hand-made settings file that lacks the
   key (e.g. `{}`) still enables the sweep. The migration always writes the key, so
   Step 1 cannot create such a file, but the owner may want the default flipped (Q3).
   This batch does not change it: it is a default, and it was not asked for.
3. **The settings file lives inside a checkout.** In the OneDrive checkout it will sync,
   and a sync lock can make the atomic `os.replace` in `save()` fail (the `P4-1`
   symptom). `save()` already catches `OSError` and warns once. The cost is a lost
   hardware cache, so the next headless run is capped as a 4 GB VM (CLAUDE.md §4). This
   worktree is outside OneDrive. The note goes into the P4-3 text in Step 3.
4. **Every checkout has its own settings.** Runs folder, hardware cache and window
   state are per checkout from now on. This is intended (pinned in Step 1), and the owner
   should know it.
5. **No number moves, but the foam path's frame list does (Step 4).** After `P1-7`, a
   chamber or profile stage emits its t = 0 frame, and `_time_is_whole` accepts such a
   start dir as a restart point. Both are the fix's intent. They affect future runs'
   live view, animation frame count and resume walk-back, and no committed golden.
   Protection: the writer goldens (`test_foam_writer.py`) are untouched and must stay
   green. `test_foam_resume.py` and `test_foam_amr_ingest.py` pass unchanged.
   `test_regression.py` is byte-identical.
6. **Committed tests change (§9).** Three are affected:
   - `test_vent_wall.py`: one expected value flips, and three helpers are renamed. The
     flip is authorised by `P1-7`, the renames by `P2-13` item 3.
   - `test_refine.py`: mechanism only, authorised by `P2-13` item 4.
   - `test_open_case.py`: checks are added only.

   Protection: one commit per test and per purpose, each citing its decision. The
   `[PASS]`-line diff before and after is shown in the implement report. No threshold
   moves anywhere.
7. **Collision with the other session.** See the coordination check at the top. Keep
   the `TODO.md` / `DONE.md` / `CLAUDE.md` edits small and local, because they will
   conflict at merge regardless.
8. **Encoding (§8.1).** `CLAUDE.md` has Hebrew in §2, and TODO/DONE are full of `·`, `→`
   and `μ`. Edit them with the editor tools only, and run the `rg 'ג€|ג”'` check
   afterwards.

---

## 4. Needs clarification (excluded from this batch; questions for the owner)

- **Q1 · `P2-14` item 7, `read_probes`: "raise if the times differ".** Today
  `reader.read_probes` (`reader.py:474-490`) attaches `rho` / `U` only when their row
  count equals `p`'s. Otherwise it **degrades to p-only**, and a committed check pins
  that: `test_foam_reader.py:157-166`, "torn U file degrades to p-only, never
  misaligns". Its callers are the run finalisers in `backend.py:584,1577,2225`, which is
  on the excluded list, so no `try` can be added there. A raise would fail the
  post-processing of a finished run. *Question:* should the rule be "align on time;
  raise only when rows present in both files carry different times, and keep degrading
  to p-only for a torn tail (fewer rows, same times)"? Or should any mismatch raise,
  even though that fails a finished run's finalise and flips the committed torn-tail
  check?
- **Q2 · `P2-7`, `test_foam_parallel.py` skip.** The TODO proposes the fix (call
  `env.rank_ceiling`, then skip explicitly), but `P2-13` says only four committed tests
  may be edited, and this is not one of them. *Question:* does the `P2-7` text itself
  permit this edit?
- **Q3 · `DEFAULTS['auto_cleanup']`.** Should the built-in default become `False`, so
  that only a file which says `true` turns the sweep on (see Risk 2)? That is a
  one-word change, but it changes a default, so it waits for the owner.
- **Q4 · The same pytest blind spot in every script suite.** Most `test_*.py` files use
  the same `check()` → `FAILS.append` pattern, and pytest collects the ones
  `conftest.py` does not ignore. So under pytest they cannot fail either. Steps 5 and 7
  fix only the tests the owner named. *Question:* apply the same few lines to every
  pytest-collected script suite (or once in `conftest.py`), and treat any failure it
  uncovers as a finding? Not in this batch.
- **Owner decisions still open from TODO** (unchanged, not planned): `P1-4`, `P1-17`,
  the `_e2e_foam_amr2d` thresholds, decomposition, `HD1-4` (close or keep), `HD1-16`
  step 2 (after an SBEDS run), `HD1-17(b)` (the scenario), the ANFO row of `P1-14`
  (the JWLC `C` term, D, Pcj, ρ0), `P1-12`'s 50 GB threshold, and `P4-1` / `P4-2`.
- **For the OUT session (not a question):** `docs/wsl-disk-reclaim-plan.md` line 127
  (pre-check P3) reads `%APPDATA%\blastlab\settings.json`. After this batch it should
  read `<repo>\settings.json` or use the Step 3 dry-run check.

---

## 5. Remaining backlog, grouped into future batches

**Blocked by the excluded files** (the other session is editing them). Revisit after
OUT-2 merges:
- **amr-defaults:** `P1-8`. Needs `ui/setup_spec.py`, `gui/forms.py`,
  `models/fields.py` and `core/refine.py`.
- **material-labels:** `P1-9`, then `P1-10`. Needs `ui/setup_spec.py`,
  `ui/case_form.py` and `models/case.py` (the charge sizing). `P1-10` needs `P1-9`'s
  W_E, per UFC 3-340-02 §2-9 Eq. 2-1 / Table 2-1 and Fig. 2-15.
- **hd13-inputs:** `P1-11` + `P1-15` + `HD1-18`. The Qt HD 1.3 form lives in
  `ui/setup_spec.py` / `models/fields.py`.
- **write-interval:** `P1-12`. Needs `writer.py`, `setup_spec.py`, `gui/forms.py`,
  the blastFoam guide `controlDict` section, and a WSL acceptance run.
- **grid-one-source:** `P1-16`. Needs `services/validation.py` and `writer.py`.
- **hygiene, excluded part:** `P2-14` items 2 (`models/fields.py`), 3 and 5
  (`services/validation.py`), 4 (`services/validation.py`, `models/case.py`), and 6
  (`runloop.py`).
- **audit comment fixes:** the `adjustLocations` comments (`models/case.py`,
  `writer.py:107-111`).
- **det-points table:** `N5-12` (the setup form).
- **writer-side P3:** `P3-3`, `P3-16`, `P3-17`, `P3-19`, `P3-23` and `P3-24`, all
  `writer.py`.
- **resume and model:** `P2-17` (`services/model_folder.py`, `solvers/jobs.py`).
- **materials, partly blocked:** `P1-14`. The TNT/C4/HMX/PETN values in
  `core/materials.py` are free, but item 5 edits `services/validation.py` and the
  "unsourced" GUI marker sits in the forms. It moves C4/HMX/PETN results and needs its
  own re-baseline commit.

**Free of the excluded files, in suggested order:**
- **hygiene-free:** `P2-14` items 1, 8 and 9:
  - Item 1: the negative-charge preview (`core/refine.py`, `ui/setup_panel.py`, the Tk
    preview; GUI QA).
  - Item 8: `_e2e_foam_write_budget.du_sb`, which needs a WSL rerun.
  - Item 9: `_e2e_vent_3d.evaluate` with no probes. The frozen C6-C13 block stays
    untouched.
- **gauge-arrival:** `P1-13` (`output/gauge_summary.py`, `output/report.py`, the gauge
  CSV header). This is a calculation change with its own re-baseline commit and a
  before/after table.
- **qt-hd13-polish:** `P2-18` (Run chain enabled during HD 1.3; dialogs break a path
  after `C:`). Qt, `ui/app.py` / `ui/run_panel.py`, on-screen QA needed.
- **docs-only:** `P2-15` (the notes a-e on the HD1-3d / HD1-13 records in DONE.md §0),
  and the Claim 4 write-up name (`fluxScheme::snGradAlpha`, not `::AD`) in
  `docs/verification/blastfoam-claims.md`.
- **display:** `P2-2` (viewer "Energy (approx)" for foam), `P3-25`, `P3-9`, and
  `P3-10` (stdout, so a re-baseline), plus `P2-1` (native 1D progress; the native path
  is secondary per the owner, so keep it byte-identical).
- **GUI-only / manual:** `P1-19` (the intermittent Tk VTK crash), `P2-5` (by eye),
  `P2-16` (Tk `root.update()` stall).
- **research runs (WSL, owner go, thresholds pre-registered):** `N5-11`, the ≈2 %
  parallel offset fixed-Δt run, Claim 3 R3.1b / R3.2 / R3.3, `HD1-14`, the `P2-11`
  investigation (`P2-13` item 2), and the deferred on-screen QA of `P1-7`.
- **P3 / P4 on request:** `P3-1` … `P3-24` not listed above, `P3-26` after the OUT
  track, `P4-1` … `P4-3`.
