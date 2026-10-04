# GUI-11 part 11a — verification report (T1-T6)

Plan: `docs/batches/2026-10-03-gui-polish.md`, part 11a.
Implementer's report: `2026-10-03-gui-polish-a.implement.md`.
Commits verified: `73ee673`, `4d696c2`, `2ed1ef4`, `8042d5d`, `6c22c40`,
`edc1154`, `f9a205e`. `305a351` (TODO.md only) is not part of 11a.

**Verdict:** ready for QA. One defect was found and fixed (`41404bd`).
Two findings are recorded and not fixed: F40 needs an owner call, and F41
predates GUI-11.

Setup:
- The CLAUDE.md §8.2 dry run read `auto_cleanup` = `False`.
- Every window ran on throwaway settings in native mode, so there was no
  WSL probe. No WSL solve was run.
- Suites ran one at a time.
- The scratch probes (`v_*.py`) are in the session scratchpad. They are
  not committed.

---

## Per task

### T1 · crash dialog only on the GUI thread — VERIFIED

- PASS. `test_ui_crashlog`: 14 checks, rc 0. The old checks are
  unedited.
- PASS. Real platform, a real QMessageBox (`v_t1_real.py`):
  - **One worker crash:** no box is built on the worker thread. After a
    pump there is exactly one box, built on MainThread. It has GUI-thread
    affinity, its text is `RuntimeError: worker A`, and the log grew.
  - **A slot that raises on the GUI thread:** one box, on MainThread.
    This path is unchanged.
  - **Two worker crashes at once:** two boxes, both on MainThread.
- PASS. Shutdown (`v_t1_shutdown.py`): a non-daemon thread raises 1 s
  after `app.exec()` returned. This was run once with the QApplication
  still alive and once with it deleted. Both times the log was written,
  there was no hang and no recursion, and the exit was rc 0.
  - A third variant deleted the relay by hand after the app was gone,
    and it crashed (rc 139). faulthandler puts the crash in the probe's
    own `shiboken6.delete` call, not in the code. The app never deletes
    the relay.
- PASS. `ui.app.main()` on the real platform (`v_main_real.py`):
  - a worker crash 1.5 s in showed exactly one box, on the GUI thread;
  - the clean window closed with no discard question;
  - main returned 0 after 4.7 s.

### T2 · ask before discarding a run or edits — VERIFIED

- PASS. `test_ui_close_guard` (C1-C4): 18 checks, rc 0. Each check
  patches the hook with the answer it needs.
- PASS. Real platform, with the **real** `dialogs.ask_discard`
  (`v_t2_real.py`, a real `WM_CLOSE` through `PostMessageW`):
  - **A dirty window:** one question, `Save the changes to wall_A.json?`,
    titled `Quit BlastLab`. The buttons are Save / Discard / Cancel, with
    Save the default and Cancel the Escape answer.
    - Escape keeps the window open: Win32 `IsWindowVisible` is True, it
      is still dirty, and Lx is still 5.5.
    - The Cancel button does the same.
    - Discard closes it, and the file is untouched.
  - **Open (Ctrl+O path) on a dirty window, Cancel:** one question,
    titled `Open case`. No file dialog opens.
  - **A live run:** `Stop QA_RUN and quit?`, with Stop and quit / Keep
    running, and Keep running both the default and the Escape answer.
    - Escape keeps the window, and no stop or shutdown is sent.
    - Stop and quit, then Cancel on the edits: the window stays open, and
      still no stop is sent.
  - **`--case` at startup** (`MainWindow(case_file=…)`): no question, and
    the window is clean.
- PASS. No other path drops data silently:
  - In `ui/`, the case can only be replaced through `_open_case` (menu,
    Ctrl+O, Recent, `--case`) and `_load_case_from_result`.
  - Load into 01 Setup keeps its pinned `Replace` / `Keep editing`
    question (`test_ui_results_screen` green).
  - `ui/` has no drag and drop (no `dropEvent`).
- PASS. The test hook cannot reach the real app:
  - no non-test module imports `ui.testing`;
  - `main()` does not call `ensure_qapp`;
  - `_e2e_ui_viewer_place.py` and `_qa_ui_perf.py` call
    `answer_discard()` inside their own `main()`.
  - Also checked: every test file that builds a MainWindow either goes
    through `ensure_qapp` or is one of the plan's four. Of those four,
    `_e2e_ui_view3d.py` closes a clean window.
- Accepted, per the plan. Stop and quit still runs the unchanged
  `ctrl.shutdown()`, whose join can take up to 10 s. The "Stopping…"
  modal is in the backlog.
- PASS. Harness offscreen `--solver native --scenario
  S00,B01,B02,B04,B06,B07,K01` (`~\blastlab_qa\verify11a-close`): all
  seven scenarios done, no finding.

### T3 · Save as reports a write failure — VERIFIED

- PASS. `test_ui_frame` F11 (6 checks):
  - one `Save case` error;
  - no crashlog entry;
  - the window still dirty, with its path and Recent unchanged;
  - the start path `<case folder>\parity.json`, then the newest Recent
    entry's folder, then the Runs folder, each with `QA_MODEL.json`.
- PASS. The "no crashlog entry" check is not vacuous
  (`v_t5_offscreen.py`): a `ValueError` raised from the writer through
  the same Ctrl+Shift+S path does reach `crashlog.last_crash`.
- Note: the error text carries the path twice, the second time quoted
  inside the OSError's own text. That second path was the T6 defect
  below.

### T4 · F5 on the Chain screen runs the chain — VERIFIED

- PASS. `test_ui_frame` F12 (4 checks): Chain → `chain.run` once,
  Setup → `_run_single` once, still five shortcuts, and the tooltip
  reads `Run the chain (F5)`.
- PASS. Real platform, the F5 key sent to the window (`v_t46_real.py`):
  - Chain, Setup, Run, Results, Chain gave
    `['chain', 'single', 'single', 'single', 'chain']`.
- PASS. Harness `--window --solver native --scenario B06`
  (`~\blastlab_qa\verify11a-b06w`):
  - Ctrl+O and Ctrl+S reach their dialogs;
  - F5 starts a run;
  - plain Esc does not stop it, and Shift+Esc does;
  - no finding.

### T5 · the 0-D run flow — VERIFIED

- PASS. `test_ui_run_screen` R11: 194 checks in all, rc 0.
- PASS. The greys come back in every way an assessment can end
  (`v_t5_offscreen.py`, with `hd13_service.run_into_model_folder`
  patched and held on an Event):
  - **Success:** while busy, Setup's Run F5 and Initialise, Run chain
    and 02 Run's Run are all off. Afterwards all four are back, and the
    tile reads `—`.
  - **An exception in the assessment:** the same, plus one `HD 1.3
    assessment` error.
  - **A `SystemExit` in the worker:** the same. See F41 for what else
    happens.
  - **A pre-flight refusal** (empty Model box): never busy, nothing
    greyed, and one `Run` error.
- PASS. `test_ui_char_hd13_run` and `test_ui_frame` are green and
  unedited.
- PASS. Real platform: `_e2e_hd13_gui.py` gave 31 PASS, rc 0, with a
  real assessment.
- PASS. The F39 edit does not weaken the e2e:
  - At 0-D, Structure is in `HIDDEN_CARDS_0` and owns no tree node
    (`setup_nodes.nodes(0)`).
  - So `show_card('Heat')` only puts the control card on screen, and the
    Structure assertion is unchanged.
  - The implementer's busy screenshot matches the claim (02 Run, Run
    greyed, the note, no banner).

### T6 · titles, paths, tooltips — FIXED

- PASS. Keep all fields `toolTip()` starts with `<`, and
  `tip_text(...) == KEEP_ALL_TIP` in 1D, 2D and 3D (`test_ui_output_card`
  green).
- PASS. The `Run chain` refusal:
  - offscreen, F13;
  - real platform: a box titled `Run chain`, `A run is already in
    progress.`.
- PASS. Real platform, the overwrite question for `QA_MODEL` under a
  70-character runs folder (1920 px screen):
  - the lines are `QA_MODEL already exists in` / `C:\…\v11a_xxx….` /
    `Overwrite? …`, confirmed by a screenshot;
  - Ctrl+C on the box (focus on a button) copies the whole text with the
    path whole;
  - a selected path copies exactly;
  - the words are unchanged, and only the space before the path became a
    line break.
- **FAIL → FIXED** (`41404bd`). Real platform, the Save case write
  error from T3 broke its second, quoted path mid-way: `…\\Temp\` /
  `\\v11a_…`.
  - Cause: D207's token started at the drive letter, so a path preceded
    by `'` never moved to its own line.
  - Fix: the token takes one opening `'`, `"` or `(` (D216).
  - New check: `test_ui_frame` F13, which fails with the old pattern.
  - After the fix, on the real platform, both paths are whole
    (`docs/qa/2026-10-03-gui-polish/verify11a-save-error-paths.png`).
- PASS. A path past the cap is elided in the middle, with the whole text
  in the tooltip. But copying gives the elided text (F40, an owner call).
- PASS. Real platform: the Keep all fields tooltip is 432 × 78 px
  (Win32 `GetWindowRect`), under 450.
- PASS. `ask_yes_no` was rebuilt from the static `QMessageBox.question`.
  On the real platform (`v_yesno_real.py`):
  - Yes gives True; No and Escape give False;
  - the labelled variant gives Replace = True and Escape = False;
  - `ask_discard` gives Save = `save`, Discard = `proceed`, hd13 Quit =
    `proceed` and Escape = `cancel`.

### The changed assertions (report §"Changed assertions")

All three tooltip comparisons are still exact. `tip_text` reads
`wrap_tip`'s HTML back through QTextDocument. Whitespace that HTML
collapses would make the compare fail, so it cannot hide a change of
words. The `starts with '<'` check is new.

- **`test_ui_output_card` C11:** still exact.
- **`test_ui_output_card`, the decimation tip:** still exact.
- **Harness V06:** still exact.
- **`_e2e_hd13_gui` F39:** no assertion changed. It only selects the
  control card's node (see T5).

---

## Defects found in the diff

| File | Severity | What | State |
|---|---|---|---|
| `blastlab/ui/dialogs.py` `_PATH_TOKEN` | Medium | A quoted path (an OSError's text) broke mid-path on the real platform. | Fixed, `41404bd` (D216) |
| `blastlab/ui/dialogs.py` `_keep_paths` | Low | An elided path cannot be copied whole; the full text is only in a tooltip. | Not fixed: F40, owner call (the plan asks for the elide) |
| `blastlab/ui/app.py` `_run_hd13` / `_hd13_done` | Low, predates GUI-11 | A `BaseException` in the worker posts `(None, None, None)`. The slot then raises a TypeError, so there is no dialog and no report; the greys do come back. | Not fixed: F41 |
| `blastlab/ui/crashlog.py` 98-101, 164-167 | Info | `except Exception: pass` around the relay emit and the relay creation. | Accepted: the log and stderr were already written, and a crash handler must not crash |

No debug prints, TODOs or commented-out code in the diff. No numerical
change.

## Engineering questions

None. 11a computes no blast quantity.

## Tests run (one at a time, rc 0 for all)

**Qt suites, after the fix unless noted:**

| Suite | Checks |
|---|---|
| `test_ui_frame` | 78 |
| `test_ui_run_screen` | 194 |
| `test_ui_results_screen` | 186 |
| `test_ui_chain_screen` (before the fix) | 196 |
| `test_ui_chain` (before the fix) | 114 |
| `test_ui_crashlog` | 14 |
| `test_ui_close_guard` | 18 |
| `test_ui_setup_tree` (before the fix) | 238 |
| `test_ui_parity` (before the fix) | 41 |
| `test_ui_output_card` (before the fix) | PASS |
| `test_ui_setup_strip` (before the fix) | 110 |
| `test_ui_run_panel` (before the fix) | PASS |
| `test_ui_setup_form` | PASS |
| `test_ui_components` | PASS |
| `test_ui_no_vtk_in_main` | PASS |
| `test_ui_no_mpl_pyplot` | 19 |

"Before the fix" means `dialogs.py` changed afterwards, but only in
`_PATH_TOKEN`. Those suites patch the dialogs.

**Goldens, all PASS and unedited:** `test_ui_char_case_form`,
`_chain_wiring` (again at the end), `_hd13_run`, `_results_exports`,
`_results_meta`, `_write_failure`.

**Real platform:**
- `_e2e_hd13_gui.py`: 31 checks;
- harness `--window` B06;
- the scratch probes `v_t1_real`, `v_t1_shutdown`, `v_t2_real`,
  `v_t46_real`, `v_yesno_real` and `v_main_real`.

**Offscreen:** harness S00, B01, B02, B04, B06, B07 and K01, with no
finding.

**Regression:** `test_regression` **PASS**, byte-identical. It ran after
the fix and again at the end.

**Frozen paths:** `git diff 116ea96..HEAD` over the plan's frozen list
is empty. None of the never-stage paths is in any 11a commit or in the
fix.

## Files touched by the fixes

- `blastlab/ui/dialogs.py`
- `blastlab/tests/test_ui_frame.py`
- `docs/gui-redesign-decisions.md` (D216, F40, F41)
- `docs/qa/2026-10-03-gui-polish/verify11a-save-error-paths.png`
- `docs/qa/2026-10-03-gui-polish/verify11a-elided-path.png`
- this report

## GUI screens that need QA

These are the implementer's list, plus the fix:
- **Window close, Open and Recent:** the Save / Discard / Cancel question
  and the run / HD 1.3 questions.
- **Save as:** the start folder and the error dialog.
  - Now: both paths in `Could not write …: [Errno 13] … 'C:\\…'` stay
    whole.
- **Chain:** F5, the Run chain tooltip, and Run chain greyed during an
  assessment.
- **02 Run at 0-D:** the note, no banner, and `—` after.
- **01 Setup:** Run F5 / Initialise greyed during an assessment, and the
  wrapped field tooltips.
- **Every `ui.dialogs` message box:**
  - selectable text;
  - a path, quoted or not, starts its own line;
  - a very long path is elided (F40).

## Still open

- **F40:** copying an elided path. Owner call.
- **F41:** a `BaseException` in the HD 1.3 worker. Predates GUI-11, low.
- **From the implementer's list, unchanged:**
  - the busy status message clears after 12 s (D206);
  - F5 on Chain while busy reaches the `Run chain` refusal dialog, where
    the Setup path sends a notify instead.
