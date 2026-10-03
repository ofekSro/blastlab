# Batch 2026-10-03-gui-polish — GUI-11 · polish of the redesigned Qt GUI (parts 11a-11d)

**Goal in one sentence:** close the owner-approved GUI-11 items (a)-(g), plus the High
UX-review findings, both QA S2 failures and the small UI-only Medium / S3 items the
two agents found after GUI-10, in four uninterrupted runs. No number, solver default,
case key, file format or export byte changes.

**TODO.md text (verbatim, GUI track, line 58):** *"`GUI-11` | **Polish, owner-approved
2026-10-03** (`docs/gui-redesign-decisions.md`, owner-review rows) — (a) D191: `● unsaved`
shortens to `●` (tooltip) whenever the case name is elided (D198 does it only when a
control would be squeezed); F38: the harness clip check sees tool-button elision, then
K02 `--window` again; F36: harness F02/F10 expect the VTK export disabled with its
reason; (b) D192: tree-row hover visible in dark, dark `num_dim` at 4.06:1 on hover
accepted; (c) F28: clear the previous stage's progress at a stage start, one line in
`solvers/worker.py` — own commit, `test_regression` + the Tk suites; (d) F12: at 0-D
hide the Run view toolbar, show a 0-D note; (e) F16: keep a case file's hidden-row value
(`amr_refine` / `amr_unrefine`), solver defaults untouched; (f) F17: a shorter on-screen
1D figure title, exports byte-identical; (g) P2-18 and P2-24; (h) whatever the
`gui-qa-tester` / `gui-ux-reviewer` pass after GUI-10 finds | M | 11"*. The RESUME note
lists GUI-11 as step 2, after the two agents (done: `16ce0f2`, `116ea96`).

**Inputs:**
- `docs/gui-redesign-decisions.md`, § "Owner review, 2026-10-03" (binding) and D199;
- `docs/UX_REVIEW-redesign.md` (UXR-1 … UXR-26);
- `docs/qa/2026-10-03-gui-final/QA_REPORT.md` (S2-1, S2-2, S3-1 … S3-7, S4-a … S4-k);
- `docs/qa/2026-10-03-gui-qa/findings.md` (P2-18 and P2-24 still reproduce);
- `docs/gui-redesign-plan.md` §9; `DONE.md` §0l-§0s.

New decision rows start at **D200** and new findings at **F39**.

**Branch:** `gui-redesign`, base **`116ea96`**.

**References:** only T14 touches a standard's term. The scaled-distance unit
`m/kg^1/3` follows UFC 3-340-02 (2008), para. 2-13.1, printed p. 44 (PDF p. 120). That is
already cited in `ui/scaled_distance.py` (D24). Nothing in GUI-11 computes a blast
quantity. The S2-1 check (T9) re-states a rule the solvers already apply
(`solvers/solver2d.py` 199-213, `solver3d.py` 252-259) and cites those lines, not a
document.

---

## Interpretations (written down, not guessed)

1. **Which (h) items are in scope:**
   - every High UXR (1-5) and both QA S2 failures;
   - the Medium UXR and QA S3 items that are UI-only and small, meaning about 60
     changed lines or fewer in non-frozen `ui/`, with no new capability.

   Everything else goes to the backlog with one line each.
2. **Merged duplicates:**
   - QA S2-2 = UXR-1;
   - QA S3-3 = UXR-8 + F12 (GUI-11 d) + the chain half of P2-18 (GUI-11 g);
   - QA S4-a (x/y in axisymmetric) = UXR-11 + F4;
   - QA S3-1 = F34 not holding at 1280 × 840;
   - QA S4-k = D192 (GUI-11 b).
3. **UXR-3 cannot be done the way the review proposes.** The review gives the Material
   row `scope='blastfoam'`. Plan §9 pins every spec scope, and the Qt char golden
   `char_golden/ui_case_form.json` pins the hidden rows. The batch instead adds a UI-side
   Checks warning (D210). Hiding the row is an owner call and goes to the backlog.
4. **S2-1 is checked only where the hand-off radius is known before the run.** That is a
   1D stage whose Outer boundary terminates it, which covers the QA failure and the
   board's 1D → 2D and 1D → 3D routes. The 2D → 3D prediction (trigger gauge or
   terminate side) is fuzzier and goes to the backlog (D200).
5. **F16 changes a behaviour golden, with the owner's approval.** The Qt golden
   `ui_case_form.json` pins today's F16 behaviour: a loaded 0.2 / 0.1 reads back as
   0.4 / 0.2 with AMR off. Fixing F16 changes exactly those `/get` entries. The owner
   approved the change, so the entries are re-recorded in T11's own commit with the
   diff in the report. The Tk golden `gui_case_form.json` is unchanged, because
   `models/fields.py` is not touched.
6. **UXR-14 (reopen a native result after a restart) is a new capability.** It is not
   in the batch. It goes to the backlog as a proposed separate **TODO P2** item (session
   default; the owner places it).
7. **S3-6 is split by file.** Its black bands (38 / 15 px) belong to the frozen
   `view3d_host.py` and go to the viewer-host batch with F5 / F9 / F13 / F30. Its
   misleading placeholder text can be changed outside that file, so it is in the
   batch (T21).

---

## Split: four parts, each one uninterrupted run on the 8 GB home PC

Each part ends with the app runnable and `test_regression` byte-identical. Heavy
suites run one at a time.

- **11a — correctness in the frame** (T1-T6): crash dialog, discard prompts, Save as,
  F5 on Chain, the 0-D run flow, dialog titles and tooltips. Only `ui/` and tests.
- **11b — the shared-module part** (T7-T9): F28 in `solvers/worker.py`, the
  dropped-gauge warning in `services/validation.py`, and the cross-stage hand-off check.
  **The Tk gate runs here and only here.**
- **11c — Setup, forms and Chain wording** (T10-T15).
- **11d — Run, Results, top bar, and the real-platform close** (T16-T22): the harness
  fixes (F38, F36), then K01-K03 and B06 with `--window`, R10, and the final matrix.

Reports: `docs/batches/2026-10-03-gui-polish-{a,b,c,d}.implement.md`. Screenshots and
measurements go to `docs/qa/2026-10-03-gui-polish/`. D200+ rows, F39+ rows and the
Outcomes on F12, F16, F17, F28, F36 and F38 go into `docs/gui-redesign-decisions.md`.
`TODO.md` and `DONE.md` are left to `/todo`.

---

## Constraints for every part

- **No numerical change.** Nothing changes in a solver, a solver default, a case key, a
  file format, an export byte or a hand-off file. `python
  blastlab/tests/test_regression.py` must be byte-identical after every task. CRLF-only
  baseline changes are never committed.
- **Frozen:**
  - `blastlab/gui/` (Tk) and `customtkinter`;
  - `core/`, `models/`, `output/`, `viz3d/`;
  - `solvers/`, except the one line of T7;
  - `services/`, except `validation.py` in T8;
  - `ui/view3d_host.py`, `ui/run_controller.py`, `ui/viewer_link.py`;
  - `tests/baseline/`, `foam_fixtures/`, `foam_golden/`;
  - `char_golden/`, except T11's `ui_case_form.json` `/get` entries.

  At the end of each part, `git diff 116ea96..HEAD` over these paths shows only the
  listed exceptions.
- **Committed tests.**
  - Behaviour and number assertions are never weakened.
  - Layout pins may change per plan §9. An owner-approved behaviour change (D191 in T16,
    D192 in T17, F16 in T11) may update its own pin.
  - A new warning may change an expectation that read "OK" on a case it now warns about
    (T8, T9).
  - Every changed assertion is listed in the part's report with its reason.
  - `test_ui_char_chain_wiring`, `test_ui_char_results_exports`,
    `test_ui_char_results_meta`, `test_char_exports`, `test_char_validation` and
    `test_ui_char_hd13_run` stay green and unedited.
  - No new `QShortcut`: `test_ui_frame` F5 pins exactly five.
- **Settings:** the CLAUDE.md §8.2 dry run first (expect `False`). Every MainWindow uses
  `ensure_qapp()` / `private_settings()` or a temporary `BLASTLAB_SETTINGS`. Harness
  runs use `--out ~\blastlab_qa\gui11-<part>-<what>` with `PYTHONIOENCODING=utf-8`.
- **Real platform** (CLAUDE.md §8.7) for every geometry, clipping, embedding or shortcut
  claim: `QT_QPA_PLATFORM` unset and Win32 through ctypes. Offscreen results are never
  the evidence.
- **Processes:** never a broad kill (F1). Stop only your own processes, by PID. Before
  and after any WSL step, `wsl -d Ubuntu -- pgrep -a blastFoam` must be empty.
- **8 GB:** one heavy process at a time (harness, sampler, e2e, `test_blast*`, the Tk
  harness, anything in WSL). Check free physical memory first. A `MemoryError` is re-run
  alone before it counts.
- **Git:**
  - Stage by explicit path only.
  - Never stage `docs/references/INDEX.md`,
    `docs/references/ViperTheoryManual_Client.pdf`,
    `docs/references/ViperTheoryManual_Client.txt`, `docs/references/viper_vtk_sample/`,
    `docs/qa/2026-09-27-out-3/` or `docs/qa/2026-09-27-viewer-polish/`.
  - Each message goes in a **new** file named `gui11<part>_msg_NN_<slug>.txt` (F19) and
    is committed with `git commit -F`.
  - Style: `ui: … (GUI-11)`, `tests: … (GUI-11)`, `solvers: … (GUI-11, F28)`,
    `services: … (GUI-11, UXR-2)`. Never push.
- Every edit goes through Edit / Write, never PowerShell strings (CLAUDE.md §8.1).
  Markdown files are capped at 1000 lines.
- After each task, run the Qt suites it touches plus `test_ui_no_vtk_in_main.py` and
  `test_ui_no_mpl_pyplot.py`.

---

## Part 11a — correctness in the frame

#### T1 · UXR-4: the crash dialog only on the GUI thread — S

*UXR-4: "The crash handler builds and runs a QMessageBox on whatever thread raised."*

**Files:** `blastlab/ui/crashlog.py`, `blastlab/ui/bridge.py`,
`blastlab/tests/test_ui_crashlog.py`.

- `_dialog` shows nothing unless the current thread is the main thread. Off the main
  thread, `_report` still writes the log file and stderr, then emits a module-level
  `QObject` signal (created in `install()`, `Qt.QueuedConnection`). The signal shows the
  same box on the GUI thread. Offscreen behaviour is unchanged: no box.
- `ThreadBridge.post` does nothing when `shiboken6.isValid(self)` is False. This is the
  HD 1.3 worker posting after the window closed, the reachable case in UXR-4. (D203)
- **Acceptance:** `python test_ui_crashlog.py` passes, with these new checks:
  1. An exception raised in a `threading.Thread` writes the log and **does not**
     construct a `QMessageBox` on that thread. Patch `QMessageBox.__init__` to record
     `threading.current_thread()`; the recorded thread is the main thread, after a
     `pump`.
  2. `bridge.post` on a deleted `ThreadBridge` raises nothing.

  The existing checks stay unedited.

#### T2 · UXR-1 = QA S2-2: ask before discarding a live run or unsaved edits — M

*UXR-1: "Closing the window, Open and Recent all discard a live run or unsaved edits
without asking."*

**Files:** `blastlab/ui/app.py` (`closeEvent`, `_open_case`, `_fill_recent_menu`, a new
`_confirm_discard`), `blastlab/ui/dialogs.py` (new `ask_discard`), `blastlab/ui/testing.py`
(the default answer), new `blastlab/tests/test_ui_close_guard.py`.

- `_confirm_discard(action)` runs on the GUI thread and returns True to proceed.
  - **A run is live** (`ctrl.running`): it asks `Stop <model> at N % and quit?`. The
    text and the blastFoam resume sentence come from `_stop_question`. The buttons are
    `Stop and quit` / `Keep running` (the default and the Escape answer).
  - **An HD 1.3 assessment is busy:** `An HD 1.3 assessment is still writing <model>.
    Quit anyway?`, with `Quit` / `Keep running`.
  - **Then, if `_dirty`:** `Save the changes to <case>?`, with `Save` / `Discard` /
    `Cancel`. Save calls `_save_case_inplace`. If that falls through to Save as and the
    user cancels the dialog, the action is cancelled.
- `closeEvent` calls `event.ignore()` and returns when the answer is no. Open (the menu,
  Ctrl+O) and every Recent entry ask **before** the file dialog or the read. Open asks
  about the dirty state only: a live run is not affected by Open.
- **Load into 01 Setup keeps its own pinned question** (`Replace` / `Keep editing`;
  `test_ui_results_screen`).
- The `ctrl.shutdown()` join is unchanged. UXR-1's point 3, the "Stopping the solver…"
  modal, needs `run_controller.py` and goes to the backlog.
- Every close and Open question goes through **one** function, `dialogs.ask_discard(kind,
  text, parent)`. `testing.ensure_qapp()` replaces it with a recorder that answers
  "proceed", so the 32 suites and the harness that close dirty or running windows keep
  today's behaviour and never block on a modal. The recorder's calls are readable
  (`testing.DISCARD_ASKED`). Four files build a MainWindow without `ensure_qapp`
  (`_e2e_ui_view3d`, `_e2e_ui_viewer_place`, `_qa_ui_perf`, `test_settings_path`). Check
  each, and add the same hook if it closes a dirty or running window. (D202)
- **Acceptance:** `python test_ui_close_guard.py` (offscreen), with the hook patched per
  check:
  1. A dirty window: Cancel → the window stays, the case is unchanged. Discard → it
     closes. Save with a path → the file is written and then it closes.
  2. A dirty window and Open: Cancel → the case and the path are unchanged, and no file
     dialog opens (patched `open_file` not called). The same holds for a Recent action.
  3. A clean window closes and Opens without asking (the recorder's list is empty).
  4. Running (a fake `ctrl.running`): Keep running → `event.isAccepted()` is False and no
     stop is sent.

  Also green: `test_ui_frame`, `test_ui_results_screen`, `test_ui_run_screen` and the
  harness `--scenario B01,B02,K01`. On the real platform, a dirty window closed by a
  real `WM_CLOSE` shows the question (screenshot `gui11-close-dirty.png`), and Cancel
  keeps it open.

#### T3 · UXR-5: Save as reports a write failure and starts in a useful folder — S

*UXR-5: "Save as… lets an `OSError` escape to the crash dialog."*

**Files:** `blastlab/ui/app.py` (`_save_case`), `blastlab/ui/dialogs.py` (`save_file`
start path), `blastlab/tests/test_ui_frame.py` (new checks).

- The write is wrapped as Save does: `Could not write <path>: <reason>`. The path, the
  dirty flag and Recent are left unchanged on failure.
- The dialog starts in the current case's folder, else the folder of the newest Recent
  entry, else the Runs folder. The name is `<case stem>.json`, or `<Model box>.json` for
  an untitled case. (D204)
- **Acceptance:** `test_ui_frame` gains:
  1. `save_file` patched to a path in a read-only temporary folder → one `show_error`
     titled `Save case`, no crashlog entry (`crashlog.last_crash` unchanged), and the
     window still dirty.
  2. The `start` argument passed to `save_file` equals the expected folder and name.

#### T4 · UXR-7: F5 on the Chain screen runs the chain — S

*UXR-7: "On the Chain screen, F5 runs 01 Setup's case, not the chain."*

**Files:** `blastlab/ui/app.py` (`_bind_accelerators`), `blastlab/ui/chain_panel.py`
(the Run chain tooltip), `blastlab/tests/test_ui_frame.py`.

- The F5 slot is `self.chain.run()` when `current_tab() == 'chain'`, else
  `_run_single()`. There are still exactly five shortcuts. The Run chain tooltip gains
  `F5`. (D205)
- **Acceptance:** `test_ui_frame` gains these checks:
  1. On Chain, triggering the F5 shortcut's `activated` calls a patched `chain.run` once
     and `_run_single` never.
  2. On Setup, the reverse.

  F5 (five shortcuts) is still green. On the real platform, harness `--window --scenario
  B06` passes.

#### T5 · UXR-8 + F12 (GUI-11 d) + QA S3-3: the 0-D run flow — M

*UXR-8: "The 0-D run (F12, owner-approved as GUI-11 d) leaves the user on Setup with an
armed Run button and a blast view."* *TODO (d): "F12: at 0-D hide the Run view toolbar,
show a 0-D note."*

**Files:** `blastlab/ui/app.py` (`_run_hd13`, `_set_hd13_busy`, `_run_single`),
`blastlab/ui/run_panel.py` (`set_dim`, `set_busy`), `blastlab/ui/setup_strip.py` (Run
F5 / Initialise enablement), `blastlab/ui/chain_panel.py` (`_sync_run_btn`),
`blastlab/tests/test_ui_run_screen.py`, `blastlab/tests/test_ui_char_hd13_run.py` (read
only: it must stay green).

- `_run_hd13` switches to 02 Run once the thread has started.
- While busy, Setup's Run F5 and Initialise and the Chain's Run chain are disabled.
  These are state greys, like Run during a run, not mode hiding. This is P2-18's first
  half.
- F5 while busy puts `An HD 1.3 assessment is running.` on the status line (`notify`,
  level info) instead of returning silently.
- At 0-D, `set_dim` hides the view toolbar row (Live slice · Gauges · 3D view, Show mesh)
  and the `runview` frame. One note takes their place: `An HD 1.3 assessment has no
  field to show. When it ends, its report and load files are listed in the log below.`
  The gauge column keeps D63's sentence.
- At an assessment start, the previous run's finish banner hides (D166: an assessment is
  a run start).
- When the assessment ends, the progress tile reads `—`, not the last blast run's
  percent. (D206)
- **Acceptance:** `test_ui_run_screen` gains these checks, with `assessment.run` patched
  to block on an Event:
  1. After Run on 0-D, `current_tab() == 'run'`, `setup.strip.run_btn.isEnabled()` is
     False, `chain.run_btn.isEnabled()` is False, the toolbar row and `runview` are
     hidden (`isVisibleTo`), the note is visible, and the banner is hidden.
  2. F5 while busy gives that status text.
  3. After release, the tile text is `—` and Run F5 is enabled again.

  Back on 2D, the toolbar and the view are visible.

  `test_ui_char_hd13_run` and `test_ui_frame` stay green unedited. Real platform:
  `python -u _e2e_hd13_gui.py` passes, with screenshot `gui11-0d-run-busy.png`.

#### T6 · P2-18 (dialog half) + P2-24 (Qt half): titles, paths, tooltips — S

*TODO: "`P2-18` … Run chain stays enabled during an HD 1.3 assessment and its refusal is
titled "Run". The Qt refusal and overwrite dialogs break a path after "C:"."*
*"`P2-24` Qt: the Keep all fields tooltip is one ~1000 px line - wrap it. Tk light mode:
…"*

**Files:** `blastlab/ui/app.py` (`_model_target`), `blastlab/ui/chain_panel.py`,
`blastlab/ui/dialogs.py`, `blastlab/ui/fieldform.py` (row tooltips), and a helper in
`blastlab/ui/widgets.py`.

- `_model_target(title)` uses `title` for the in-progress refusal too, and the Chain
  passes `'Run chain'`.
- The message boxes keep a path on one line. The default: `dialogs` sets the text
  label's minimum width to the advance of the longest path token, capped at 70 % of the
  available screen width, so Qt breaks only at spaces. A longer path elides in the
  middle, and the whole text is selectable. Measure on the real platform before
  choosing; if this fails, record why and use the elide. (D207)
- `widgets.wrap_tip(text)` turns a tooltip over 60 characters into rich text that Qt
  word-wraps at about 420 px. It is applied where `FieldForm` sets a row tooltip, so
  every long spec tooltip wraps. The tooltip text is unchanged in `models/`. **The Tk
  half of P2-24 is not touched** (`blastlab/gui/`) and goes to the backlog. (D208)
- **Acceptance:**
  1. Offscreen: the Keep all fields widget's `toolTip()` starts with `<` (rich text),
     and its plain text equals `KEEP_ALL_TIP`.
  2. Patched `show_info`: a Chain run during a busy assessment is impossible (T5). The
     `_model_target('Run chain')` refusal is titled `Run chain`.
  3. Real platform: the overwrite question for a model under a 70-character
     `C:\…\…` runs folder shows the path on one line (Win32 grab, screenshot
     `gui11-dialog-path.png`). The Keep all fields tooltip renders under 450 px wide.

  Then re-check P2-18 and P2-24 as in GUI-10 T11 and record *gone* for both Qt halves.

**11a closes with:** these suites, one at a time: `test_ui_frame`,
`test_ui_run_screen`, `test_ui_results_screen`, `test_ui_chain_screen`, `test_ui_chain`,
`test_ui_crashlog`, `test_ui_close_guard`, `test_ui_setup_tree`, `test_ui_parity`,
`test_ui_char_*`. Then harness `--solver native --scenario S00,B01,B02,B04,B06,B07,K01`
offscreen, `test_regression`, the frozen diff (empty), and the report.

---

## Part 11b — the shared-module part (the Tk gate runs here)

#### T7 · F28 (GUI-11 c): a stage start forgets the last stage's progress — S · own commit

*TODO (c): "F28: clear the previous stage's progress at a stage start, one line in
`solvers/worker.py` — own commit, `test_regression` + the Tk suites."*

**Files:** `blastlab/solvers/worker.py` (`GuiHooks.run_started`: `self._last_p = None`,
inside the existing `with self._lock:`), new `blastlab/tests/test_worker_stage_progress.py`
(no Qt).

- The test drives `GuiHooks` directly. It posts stage 1 progress (step 201), then
  `run_started(stage 2)`, then `flush_progress()` the way `step_gate` does when held. The
  queue after `run_started` must hold **no** `progress` message carrying step 201. A
  probe without the line must fail that check: run once on a scratch copy and record the
  output in the report. (D209)
- Commit this alone: `solvers: a stage start clears the last stage's progress (GUI-11,
  F28)`.
- **Acceptance:**
  1. The new test passes, and fails without the line.
  2. `test_regression` is byte-identical.
  3. `test_ui_chain_screen` (S7) and `test_ui_run_screen` are green.
  4. Real platform: `_e2e_ui_chain_screen.py` passes (23). A held chain's stage-2 shot
     shows `—`, not `STEP 201`.

  The Tk gate is run once for T7 and T8 together, at the end of the part.

#### T8 · UXR-2: a gauge inside an obstacle is warned, and keeps its number on screen — M

*UXR-2: "A gauge dropped by the solver renumbers the later gauges between Setup and
Results, and Setup does not warn."*

**Files:** `blastlab/services/validation.py` (`_validate_closing`),
`blastlab/ui/run_gauges.py` (row numbers), `blastlab/ui/results_gauges.py` (the `cells()`
Gauge column and the readout), `blastlab/tests/test_case_validate.py` (new cases),
`blastlab/tests/test_ui_run_screen.py`, `blastlab/tests/test_ui_results_screen.py`.

- **Validation.** Beside the existing `Gauge … outside domain - will be dropped` line,
  add a warning for a gauge strictly inside an obstacle box (open box, the same test as
  `scaled_distance.where`'s `inside`): `Gauge (1.4, 0.3) inside an obstacle - will be
  dropped`. It is a warning, not an error: the run is still valid.
  - Before wording it, check what the blastFoam path does with such a probe
    (`solvers/foam/backend._gauges_from_probes`, the reader). If blastFoam keeps it, the
    text ends `- the native solver drops it`. Record which in the report.
  - The half-cell zone at a face, where the native nearest-cell rule can also drop a
    gauge, is not predicted. The report states this.
  - Chain stage checks and the Tk app show the warning automatically, because both call
    `validate_case`. (D201)
- **Numbers on screen.** The Run live column and the Results table label each row with
  its **entered** gauge number, using `run_gauges.match_gauges` (D61 / D99; it already
  gives each payload point its entered gauge). A payload point that matches none keeps
  D61's payload numbering. When an entered gauge has no payload point, the column and
  table captions add `G3 dropped by the solver (inside Wall 1)`.
  - `GaugesView.rows()` (D98), `table_text()` headers and every export are unchanged.
    The exported labels carry positions (`output/gauge_summary.gauge_labels`).
  - This amends D61.
- **Acceptance:**
  1. `test_case_validate` gains: a 2D and a 3D case with a gauge inside an obstacle gets
     exactly the new warning, and a gauge on the face or outside it gets none.
  2. `test_char_validation` is green **unedited**. No golden case has a gauge inside an
     obstacle; if one changes, stop and report.
  3. `test_ui_results_screen`: a fixture result whose meta lists three entered gauges,
     with the second inside a wall and two payload points, shows `G1` and `G3`, and the
     caption names G2. `rows()` is equal to before.
  4. `test_ui_run_screen`: the same in the live column.
  5. `test_ui_char_results_meta` and `test_ui_char_results_exports` are green unedited.
  6. Real platform: the sample case with G2 moved into Wall 1 shows the warning in the
     Checks tab (`gui11-dropped-gauge-checks.png`).

#### T9 · QA S2-1: the 1D hand-off radius is checked against the next stage's domain — M

*QA S2-1: "The default 1D → 2D chain hands off after the shock has left the 2D domain,
with every check green."*

**Files:** `blastlab/ui/chain_route.py` (`stage_checks` plus a toolkit-free
`handoff_reach(dims, cases)`), `blastlab/tests/test_ui_chain_screen.py`,
`blastlab/tests/_e2e_ui_chain_screen.py`, `blastlab/tests/test_ui_chain.py` (if a check
reads a default stage as OK).

The choice (D200) is a **cross-stage warning; the seed is not changed.** No seeded
value, solver default or `run()` refusal changes, so `test_ui_char_chain_wiring`
(`route/12/default` pins `radius_m 10.0`) stays green unedited.

- **When:** the stage before is 1D and its Outer boundary terminates the run
  (`setup_nodes.terminate_sides`). The hand-off radius is then `R = radius_m`. In every
  other case no check is made and nothing is said.
- **The rule mirrors the solver's own remap warning:**
  - a 2D receiving stage (`solver2d.py` 204-209): `R > Lx`, `cy − R < 0`,
    `cy + R > Ly`, or an obstacle within R of `(0, cy)`;
  - a 3D receiving stage (`solver3d.py` 256): `min(x0, Lx−x0, y0, Ly−y0, z0, Lz−z0) <
    R`.
- **Wording** (on the receiving stage's Checks, as a warning):
  - The wave has left the whole domain (`R` ≥ the farthest domain point from the
    burst): `The 1D stage hands off when its shock is at 10.0 m, beyond this stage's
    whole 4.0 × 4.0 m domain: this stage would start after the wave has left it. Set
    stage 1's radius below 2.0 m.`
  - Otherwise: `The 1D stage hands off at 10.0 m; that already reaches this stage's
    boundary or a wall, so the remap is not spherical there (the run warns too). Set
    stage 1's radius below 2.0 m to keep it inside.`

  The suggested limit is the largest R that does not trigger the rule.
- The card reads `● 1 warning`, the pill `Stage OK · 1 warning`. Run chain stays enabled
  (D137), and `run()` logs and refuses exactly as before.
- **Test expectations:**
  - `test_ui_chain_screen` S5 starts from the default route, whose seed now warns. S5
    first sets stage 1's radius to the board's 1.5 m, so its error-path checks keep
    testing what they test (a fixture change, listed).
  - A new check asserts that the **default** seed shows the warning on card 2, with
    stage 1 at 10 m, and that the warning is gone at 1.5 m.
  - `_e2e_ui_chain_screen` E3 (a loaded R 1.0 m stage 1 into a 0.6 × 1.2 m stage 2)
    expects `● 1 warning` on card 2, with the message checked (an expectation changed by
    the new warning, listed).
- **Acceptance:**
  1. `test_ui_char_chain_wiring` is green unedited.
  2. `test_ui_chain_screen` and `test_ui_chain` are green.
  3. A unit check of `handoff_reach` covers 1 → 2 and 1 → 3, with the QA case (10 m,
     4 × 4, `cy 2`) giving the "left the whole domain" message and the QA control
     (1.5 m) none. An obstacle within R gives the second message.
  4. Real platform: `_e2e_ui_chain_screen.py` passes, and a Chain screenshot of the
     default 1 → 2 route shows the warning (`gui11-chain-handoff-warning.png`).

**11b closes with:**
- `test_regression` byte-identical;
- the Tk gate, one suite at a time: the nine `test_gui_*` suites, then
  `python -u _qa_gui_harness.py` (the Tk harness, its own settings, CLAUDE.md §9). Any
  Tk finding is compared with a run at `116ea96` before it counts;
- `test_case_validate`, `test_char_validation`, `test_char_case_json`,
  `test_foam_writer`, then the Qt suites touched;
- the frozen diff shows only `solvers/worker.py` (one line) and
  `services/validation.py`.

---

## Part 11c — Setup, forms and Chain wording

#### T10 · UXR-3: native mode says that Material is not used — S

*UXR-3: "In native mode the Material choice is shown and then silently replaced by TNT."*

**Files:** `blastlab/ui/setup_panel.py` (the Checks rows and the pill count), and
`blastlab/ui/chain_stage.py` (the same rule for a stage).

- When the case's solver is native and the Material box is not `TNT`, Setup's Checks
  gain a UI-side warning: `Material ANFO is not used by the native solver: native runs
  use TNT. Switch to blastFoam to run ANFO.` The pill counts it, and nothing else
  changes. The case, the spec scope, D138 and `ui_case_form.json` are untouched. Hiding
  the row is an owner call for the backlog. (D210)
- **Acceptance:** `test_ui_setup_strip`, or the Setup dock checks, gain these checks:
  1. Native with ANFO → the warning, and the pill reads `Case OK · 1 warning …`.
  2. Native with TNT, or blastFoam with ANFO → none.
  3. `get_case().material == 'TNT'` in native mode, unchanged.

#### T11 · F16 (GUI-11 e): a case file's hidden AMR values survive Open → Save — S-M

*TODO (e): "F16: keep a case file's hidden-row value (`amr_refine` / `amr_unrefine`),
solver defaults untouched."*

**Files:** `blastlab/ui/case_form.py` (`get_case`), `blastlab/tests/char_golden/ui_case_form.json`
(re-recorded `/get` entries), `blastlab/tests/test_ui_setup_form.py` (a new check).

- With AMR off, `CaseForm.get_case()` puts back the hidden box's value for each key of
  `models.fields.AMR_FORM_FALLBACKS` (`amr_refine`, `amr_unrefine`, `amr_interval`,
  `amr_buffer`, `amr_max_cells`) when the box parses. Otherwise it keeps the fallback.
  The box holds the file's value since `set_case`.
  - `models/fields.py`, the dataclass defaults and the fallbacks are unchanged, and so is
    the Tk app.
  - A fresh form still sends 0.4 / 0.2. Its boxes hold the spec defaults, so every
    `/fresh` and `/typed` entry and the chain golden (`0.4` throughout) are unchanged.
    (D211)
- Re-record **only** the `/get` entries of `set_c2_axisym`, `set_c2_no_gauge_file` and
  `set_c3` (native, and blastFoam where AMR is off), in their own commit `tests:
  ui_case_form golden keeps a file's hidden AMR values (GUI-11, F16)`. The report shows
  the JSON diff: only those keys, from 0.4 / 0.2 to the file's values.
- **Acceptance:**
  1. A test loads a file with AMR off and 0.2 / 0.1, saves it, and reads 0.2 / 0.1.
  2. A fresh blastFoam form saves 0.4 / 0.2.
  3. `test_ui_char_case_form` is green with the re-recorded golden, and its diff touches
     no other key.
  4. `test_gui_char_case_form` (Tk) is green unedited.
  5. `test_ui_parity` (load → save round trips), `test_ui_char_chain_wiring` and
     `test_regression` are green.

#### T12 · UXR-9: removing a gauge keeps the trigger on the same gauge — S-M

*UXR-9: "Removing a gauge silently re-targets the trigger gauge."*

**Files:** `blastlab/ui/fieldform.py` (`PointList.remove` reports the removed index
through a callback, with no signal change elsewhere), `blastlab/ui/case_form.py`,
`blastlab/tests/test_ui_setup_tree.py`, or the case-form suite.

- Removing a row before the trigger decrements `trigger_gauge`. Removing the trigger row
  itself blanks it and leaves D27's red pending state. A row after it changes nothing.
  This applies only to an edit made in the session: `set_case` never adjusts, so loaded
  files round trip as D17 says. The Chain 2D stage uses the same `CaseForm`.
- **Acceptance:**
  1. Trigger G3, remove G1 → `trigger_gauge == '2'` and the dropdown shows the same
     coordinates as before.
  2. Remove G3 itself → blank, and `trigger_pending()` is True.
  3. Remove G4 → still `3`.
  4. A loaded `G5 (no such gauge)` is untouched.

  `test_ui_char_case_form` is green unedited.

#### T13 · UXR-11 + F4 + QA S4-a: axisymmetric r / z everywhere on screen — M

*UXR-11: "Axis and quantity labels contradict each other (F4 and two siblings)."*

**Files:**
- `blastlab/ui/setup_spec.py` (`AXISYM_LABELS`: `Height Z [m]` → `Height H [m]`);
- `blastlab/ui/case_form.py` (the axisymmetric hook also relabels the Gauges,
  Obstacles, Refinement zones and Detonation points headers `r z` / `r0 r1 z0 z1`, and
  the entry hint);
- `blastlab/ui/preview_panel.py` or `model_overlay.py` (the Setup preview's y label `z
  [m]`, set Qt-side after `preview_draw`; `output/preview_draw.py` is untouched);
- `blastlab/ui/results_field.py` (the axis names and the hover readout read `r · z` on a
  2D axisymmetric map **and** its replay; amends D111);
- the tests whose caption pins change (`test_ui_setup_form` S8 and `AXISYM_LABELS` uses).

- Planar and 3D are unchanged. Values, keys and the case are unchanged, and the
  exported video and figures keep their labels. The charge caption (`[kg TNT]`, E1)
  is **not** changed: it is an open owner question (backlog).
- **Acceptance:**
  1. Offscreen, 2D axisymmetric: every point-list header reads r / z, and the Lx / Ly
     captions read `Radius R [m]` / `Height H [m]`. Switching to planar restores `x y`,
     and back again gives r / z.
  2. The preview axis `get_ylabel() == 'z [m]'`.
  3. A Results axisymmetric fixture: the map's bottom axis label starts with `r`, and
     `value_at` readout text starts `r `.
  4. `test_ui_char_case_form` is green unedited. Captions are not in the golden; if they
     are, stop and report.
  5. Real platform: one screenshot each of Setup and Results Field
     (`gui11-axisym-labels-*.png`).

#### T14 · UXR-15 (the small half): units where they are missing — S

*UXR-15: "Units on screen still disagree in four places."*

**Files:** `blastlab/ui/results_field.py` (the Impulse map's colour-bar label and Min/Max
captions read `kPa·ms` on screen; the values are unchanged because 1 Pa·s = 1 kPa·ms),
`blastlab/ui/case_form.py` (a faint `= 12.0 ms` beside End time when it is non-zero), and
the Z-unit tooltips `m/kg^1/3` (`setup_strip.py` Z tile, `run_gauges.py` Z header,
`setup_nodes.py` Derived card, `model_overlay.py` hover).

- P MAX in MPa is **not** done: U4 / D52 pin the readout strings (backlog).
- **References:** UFC 3-340-02, para. 2-13.1 (printed p. 44), for the Z unit, already
  cited in `ui/scaled_distance.py`.
- **Acceptance:**
  1. Offscreen: the Impulse colour bar's label contains `kPa·ms` and not `Pa·s`.
  2. `test_ui_char_results_exports` is green unedited, so the animation and the frame
     PNG keep their labels.
  3. End time `0.012` shows `= 12.0 ms`; `0` shows nothing.
  4. Each Z tooltip contains `m/kg^1/3`.

#### T15 · UXR-12 (the small half): the Chain screen explains itself — S

*UXR-12: "The Chain screen hides the knowledge needed to use it."*

**Files:** `blastlab/ui/chain_stage.py` (the 3D hint), `blastlab/ui/chain_panel.py`
(route tooltips, the `N stages · into \<model>\` line as a link), and
`blastlab/tests/test_ui_chain_screen.py`.

- **The 3D hint** reads `This 3D stage has no preview here. Its domain is 6 × 6 × 4 m,
  burst at z 2.0 m (from the 2D profile).`, built from the wired case.
- **Each route button** gets a one-line tooltip (`1D → 3D: the 1D profile is placed
  around the 3D burst point; no 2D stage`).
- **The `into \<model>\` line** opens 02 Run with the Model box focused.
- The hand-off overlay on the previews (point 1) goes to the backlog.
- **Acceptance:** `test_ui_chain_screen` gains these checks:
  1. The 3D hint names the wired domain and the burst height.
  2. Four route tooltips are non-empty and distinct.
  3. A click on the line gives `current_tab() == 'run'`, with the Model box having
     focus.

**11c closes with:** `test_ui_setup_form`, `test_ui_setup_tree`, `test_ui_setup_strip`,
`test_ui_parity` (narrow sweep: D19 widths, no clipping), `test_ui_char_case_form`,
`test_ui_char_chain_wiring`, `test_ui_chain_screen`, `test_ui_results_screen`,
`test_ui_output_card`, `test_regression`, harness `--solver native --scenario
C01,C02,C05,G01,G02,K02` offscreen, the frozen diff, and the report.

---

## Part 11d — Run, Results, top bar, and the real-platform close

#### T16 · D191 (GUI-11 a): `●` whenever the case name is elided — S

*TODO (a): "D191: `● unsaved` shortens to `●` (tooltip) whenever the case name is elided
(D198 does it only when a control would be squeezed)."*

**Files:** `blastlab/ui/topbar.py` (`_fit_marker`), `blastlab/tests/test_ui_frame.py`
(F10 / F9; an owner-approved behaviour change, listed).

- `short = need > width or <the case button shows fewer characters than the name>`. The
  ElidedButton already knows the whole name (`case_name()`). The tooltip reads
  `Unsaved changes`.
- **Acceptance:**
  1. `test_ui_frame`: at 1100 px with a 30-character name and dirty → `●`. At 1600 px
     with `wall_A` and dirty → `● unsaved`.
  2. An elided name with a clean case shows no marker.

  On the real platform, the 216-check top-bar probe of verify10b is re-run (or K02,
  T22): `0D · HD 1.3` stays 94 / 94 px in all 32 states.

#### T17 · D192 (GUI-11 b): a visible dark tree hover — S

*TODO (b): "D192: tree-row hover visible in dark, dark `num_dim` at 4.06:1 on hover
accepted."*

**Files:** `blastlab/ui/theme.py` (`TREE_HOVER_BLEND['dark']`),
`blastlab/tests/test_ui_theme.py` (T6: the dark `num_dim`-on-hover floor 4.5 → 4.0,
citing the owner review; every other role keeps 4.5).

- The default is dark t = 0, the global `hover`: the owner accepted exactly D190's
  measured 4.06. Light is unchanged at 0.66. (D212)
- **Acceptance:** `test_ui_theme` prints the dark hover, its contrast against `panel`
  (> 1.02, the D192 value), and every role's ratio. Each role is ≥ 4.5 except dark
  `num_dim` at ≥ 4.0. On the real platform, a hovered row shows in dark
  (`gui11-dark-tree-hover.png`) next to D192's shot.

#### T18 · QA S3-1, S3-2, S3-7: the Run strip and the live view at 1280 and 1100 — M

*QA S3-1: "F34 still clips P MAX at 1280 × 840." S3-2: "After a Dark-mode toggle at 1100 ×
720, the Run strip tiles are squeezed below their minimum." S3-7: "02 Run at 1100 × 720
after a finished chain: the live view collapses."*

**Files:** `blastlab/ui/run_panel.py` (`_RunStrip.arrange` and the centre layout),
`blastlab/ui/components.py` (`StatTile(fit=True)`), and
`blastlab/tests/test_ui_run_screen.py`.

- **S3-1:** the one-row threshold includes P MAX's need at the 14 px floor for the
  widest readout `8.888e+05 kPa`, measured from font metrics as D164 does, never from
  geometry. When one row cannot give it that width, the strip wraps as at 1100. The
  readout string is unchanged (U4 / D52).
- **S3-2:** the strip re-arranges with `force=True` on `StyleChange` / `FontChange`.
- **S3-7:** the `runview` frame gets a minimum height (default 200 px). The dock gives
  way first (D35's 150 px floor), then the banner's two lines stay and the chain strip
  keeps its row form (D157). (D213)
- **Acceptance:**
  1. Offscreen: after `theme.apply` to the other mode, each tile's height ≥ its
     `minimumSizeHint`.
  2. For widths 1100-1600 in 20 px steps, P MAX's value label width ≥ the readout's
     advance at the face it chose.
  3. Real platform, on the run surface: 1280 × 840 with `5.818e+05 kPa` → `kPa` whole
     (screenshot). 1100 × 720 after a finished 2-stage native chain → `runview.height()
     >= 200` (screenshot).
  4. R10 on the run surface (T22), because the embedded viewer lives in that view.

#### T19 · F17 (GUI-11 f): a shorter on-screen 1D figure title — S

*TODO (f): "F17: a shorter on-screen 1D figure title, exports byte-identical."*

**Files:** `blastlab/ui/results_fields.py` (`_draw_figure`: after
`plots.figure_results_1d`, replace the title text on the on-screen figure only) and
`blastlab/tests/test_ui_results_screen.py`.

- The default on-screen title is `1D spherical · 1.0 kg TNT · JWL`, with the user's
  title line kept, using the builder's own charge and material wording (E1 open).
  `output/plots.py` is untouched, so every export is unchanged. (D214)
- **Acceptance:**
  1. `test_ui_char_results_exports` is green unedited.
  2. The on-screen title equals the short form.
  3. Real platform at 1100 × 720: the title's `get_window_extent` lies inside the canvas
     (asserted in `_e2e_ui_results.py` or a new check, plus a screenshot).

#### T20 · UXR-10 (the small half): the method card's unit, precision and caveat — S

*UXR-10: "'How it was computed' has one wrong unit and is missing rows the result
already holds."*

**Files:** `blastlab/ui/results_method.py` (`_charge`, `_mesh`, the Afterburn row) and
`blastlab/ui/results_panel.py` (the Ended value wraps onto two lines).

- Planar charges read `kg/m` (`meta['geometry'] == 'planar'`).
- The cell size uses `{:.3g}` (`cell 12.4 mm`); amends D90.
- Afterburn reads `miller (calibrated for TNT only)` when the material is not TNT
  (CLAUDE.md §7).
- The Ended value word-wraps onto two lines.
- The new EOS / Order / Started-from rows (point 3) go to the backlog.
- **Acceptance:** `test_ui_results_screen` (S2, layout pins updated and listed):
  1. A planar fixture reads `kg/m`.
  2. `dx 0.0124352` reads `cell 12.4 mm`.
  3. A C4 blastFoam fixture with `miller` shows the caveat.
  4. The Ended label `wordWrap()` is True.

  `test_ui_char_results_meta` is green unedited.

#### T21 · QA S3-6 (the text half): the Results 3D placeholder says what to do — S

*QA S3-6: "Results ▸ 3D shows a misleading placeholder."*

**Files:** `blastlab/ui/results_panel.py` only. A small `View3DHost` subclass defined
there overrides the class attribute `PLACEHOLDER`. `view3d_host.py` stays untouched;
`git diff` on it is empty.

- The text: `Select a 3D result, then press Open the 3D viewer\nin the Export column.`
  No line may be longer than today's longest line, so D25's minimum width holds. A
  non-3D result keeps the disabled button's tooltip (D84).
- Opening the viewer automatically and the black bands go to the viewer-host batch.
  (D215)
- **Acceptance:**
  1. Offscreen: `results.view3d._holder.text()` is the new text, and
     `isinstance(results.view3d, View3DHost)` still holds.
  2. `minimumSizeHint().width()` of the Results centre is unchanged at 1100 × 720.
  3. R10-PLACE `tabs` on the results surface is 0 ms (T22).

#### T22 · F38 + F36 (GUI-11 a), then the real-platform passes and the close — M

*TODO (a): "F38: the harness clip check sees tool-button elision, then K02 `--window`
again; F36: harness F02/F10 expect the VTK export disabled with its reason."*

**Files:** `blastlab/tests/_qa_ui_harness.py` (`_clipped_labels`, F02, F10) and
`docs/qa/2026-10-03-gui-polish/measurements.md` (R10, committed before the first
sampled run).

- **F38.** For a `QToolButton` (Segmented, chip), `_clipped_labels` compares the glyph
  width with the content rect: the style's sub-control rect less the QSS padding, or the
  size hint when the size policy lets it shrink. A probe, not committed: force
  `dim_seg`'s `0D · HD 1.3` to 72 px (the F37 state). The check must then report it, and
  report nothing at 94 px.
- **F36.** F02 and F10 expect the VTK export **disabled** with the scratch-released reason
  as its tooltip on a fresh foam result. A second step sets Keep all fields on and
  expects the export offered, then `VTK export done`. This step runs in WSL only when
  `pgrep -a blastFoam` is empty and ≥ 3 GB is free; otherwise it is marked *office
  machine*.
- **Passes, one at a time:**
  1. `--window --solver native --scenario B06,K01,K02,K03` (K02 dark and light, native
     and blastFoam) at 1100 × 720.
  2. `--solver native` offscreen, groups B, C, D, E, G, H and K, diffed with
     `_qa_findings_diff.py` against `gui10-head`. Every `new` line gets a disposition.
  3. F02 and F10 in WSL, under the rule above.
- **R10, unchanged from GUI-10:** `_e2e_ui_viewer_place.py --repeat 5` on the results,
  run and setup surfaces. R10-PLACE is 0 ms over ≥ 500 samples. R10-RESIZE has a median
  ≤ 50 ms with no repeat > 80 ms. Copy the rule into `measurements.md` and commit it
  first.
- **Final matrix:**
  - every `test_ui_*` suite, one at a time;
  - `_e2e_ui_chain_screen.py`, `_e2e_ui_run_finish.py`, `_e2e_ui_results.py` and
    `_e2e_hd13_gui.py` on the real platform;
  - `test_regression` last, byte-identical;
  - the frozen diff and the never-stage list against `git status`.
- **Acceptance:**
  1. K02 on the real platform: 0 clipped and 0 outside in both modes and both solver
     modes, now **including** tool-button elision.
  2. K03 luma ≥ 140.
  3. B06 passes every check.
  4. The diff has no unexplained `new` line.
  5. R10 passes on every surface.
  6. Every GUI-11 item (a)-(g) and each in-scope (h) item has a PASS line with evidence
     in `…gui-polish-d.implement.md`.
  7. `docs/gui-redesign-decisions.md` has D200-D215, any F39+, and the Outcomes on F12,
     F16, F17, F28, F36 and F38.

---

## Proposed decisions (non-blocking defaults; D200 onward)

| # | Question | Default |
|---|---|---|
| D200 | S2-1: change the seed or warn? | Warn on the receiving stage when a 1D stage that ends at Outer hands off a radius that reaches the next stage's boundary or a wall (the solver's own remap rule), with a stronger text when the wave has left the whole domain, plus the largest radius that fits. No seed, default or refusal changes; the chain golden is untouched. 2D → 3D is not predicted (backlog). |
| D201 | UXR-2 | A validation warning `Gauge (x, y) inside an obstacle - will be dropped` (open-box test). Run and Results number rows by the entered gauge and name a dropped one in the caption (amends D61). Exports are unchanged. |
| D202 | UXR-1 | Close, Open and Recent ask through `dialogs.ask_discard`. A live run: `Stop … and quit?`. HD 1.3: `Quit anyway?`. Dirty: Save / Discard / Cancel. `ensure_qapp()` answers "proceed" for tests. Load into 01 Setup is unchanged, and so is the shutdown join. |
| D203 | UXR-4 | The crash box appears only on the GUI thread (a queued signal from workers). `ThreadBridge.post` does nothing once deleted. |
| D204 | UXR-5 | Save as catches `OSError` like Save. It starts in the case folder → the newest Recent → the Runs folder, named `<stem or model>.json`. |
| D205 | UXR-7 | F5 runs the chain on the Chain screen and the single case elsewhere. Still five shortcuts. |
| D206 | UXR-8 / F12 | 0-D Run switches to 02 Run. Run F5, Initialise and Run chain grey while busy. F5 while busy says so. At 0-D the toolbar and the view hide behind one note. The banner hides at the start, and the tile reads `—` after. |
| D207 | P2-18 dialogs | The refusal is titled after the action. A path stays on one line (label minimum width up to 70 % of the screen, else a middle elide). |
| D208 | P2-24 | Qt tooltips over 60 characters are wrapped rich text (about 420 px). `models/` text is unchanged. The Tk half goes to the backlog. |
| D209 | F28 | `_last_p = None` in `GuiHooks.run_started`, under its lock. |
| D210 | UXR-3 | A UI-side Checks warning in native mode when Material ≠ TNT. The row stays (plan §9 scope pin, `ui_case_form.json`). Hiding it is an owner call. |
| D211 | F16 | Qt `CaseForm` keeps the five hidden AMR values from their boxes when AMR is off. `models/` and Tk are unchanged. Three `/get` golden entries are re-recorded (owner-approved). |
| D212 | D192 | Dark tree hover = the global `hover` (t 0); light is unchanged. The dark `num_dim` floor on hover is 4.0 in `test_ui_theme`. |
| D213 | S3-1 / S3-7 | The Run strip's one-row rule counts P MAX's need at the 14 px floor. `runview` has a 200 px minimum, and the dock gives way first. |
| D214 | F17 | On screen `1D spherical · <W> kg <material> · <EOS>`. The builder and exports are unchanged. |
| D215 | S3-6 | Results placeholder `Select a 3D result, then press Open the 3D viewer in the Export column.` comes from a subclass in `results_panel.py`. Auto-open and the black bands go to the viewer-host batch. |

---

## Risks

- **Numbers.** Two tasks touch shared code:
  - T7 changes which queued Progress is re-posted, not any solver value.
  - T8 adds a warning, so no case value, run or file changes.

  The protection is `test_regression` after every task, `test_char_validation`
  unedited, the Tk gate in 11b, and the export / meta / wiring goldens unedited. T14
  relabels Pa·s as kPa·ms. The two are numerically equal, which the test asserts; the
  label is not a conversion.
- **A modal on close can hang every Qt suite** (32 suites and the harness close dirty
  or running windows). T2's single `ask_discard` entry point and `ensure_qapp()`'s
  default answer exist for this. The four files without `ensure_qapp` are checked one by
  one, and a suite that hangs is a T2 defect, not an environment issue.
- **S2-1's warning changes what two committed checks read on the default chain.** The
  changes are listed. The launch golden is the guard that nothing runs differently.
- **F16 re-records a behaviour golden.** It is owner-approved and limited to three
  `/get` entries, in its own commit with the diff in the report. The Tk golden is the
  guard that `models/` did not move.
- **The embedded viewer** (CLAUDE.md §8.7). T18 changes the Run centre's heights and T21
  the Results placeholder's text. R10 on all three surfaces is pre-registered in T22.
  `view3d_host.py` stays untouched.
- **8 GB.** The Tk harness, the offscreen harness pass, R10 and the e2e scripts run one
  at a time with free memory checked first. F36's WSL step is optional by rule.
- **Tests that read "Case OK" on a case that now warns** (UXR-2 or UXR-3 in a fixture):
  each is either a fixture change that keeps the check's meaning or a listed expectation
  change. It is never a deleted check.

---

## Needs clarification

None blocking. Every choice has a default (D200-D215). Three owner calls are written
down and **not** taken here:
- hiding Material in native mode (UXR-3 via scope);
- the `kg TNT` charge caption (E1, UXR-11.4);
- P MAX in MPa (UXR-15; D52 pins the strings).

---

## Remaining backlog (one line each)

- **Proposed TODO P2 (new):** `Open a model folder…` in 03 Results in both modes. It
  reads `MODEL.json`, the gauge TSV and the saved profile or frames into a Results
  entry (UXR-14; also covers F36's released-scratch blastFoam runs).
- **Setup validation mapping:** validation errors and warnings mapped to tree ✗ / !,
  Checks rows as links, and D27's pending trigger as a warning (UXR-6, F7).
- **Point lists:** Paste rows…, in-place edit and Delete (UXR-13, UX-22).
- **Properties type size:** the 13 px body rule for `#setupprops` / `#stageprops`, the
  D6 sweep, and a D19 width re-measure (UXR-17).
- **Chain hand-off overlay** on the stage previews (UXR-12.1), and the **2D → 3D
  hand-off reach check** (D200's remainder).
- **Method card rows** EOS, Order, Started from (UXR-10.3); the solver version in the
  manifest (D77).
- **Owner calls:**
  - Material hidden in native (UXR-3 scope);
  - `Charge [kg TNT]` → `Charge mass [kg]` (E1, UXR-11.4) and units as suffixes (D15,
    S4-h);
  - P MAX in MPa (UXR-15);
  - D71 `no arrival`, D74, D75, D128.
- **Honest progress:** 100 % during post-processing, ETA, and post-processing counted
  as run time (QA S3-4, D59, D75; needs a handler signal, so `run_controller.py`).
- **Gauges table impulse columns hidden at 1280 / 1100**: reflow or reorder (QA S3-5,
  D102).
- **Viewer host** (`view3d_host.py`): F5 / F13 resize sync, F9 re-adopt, F30
  WM_DESTROY, the Results 3D black bands and auto-open (S3-6), with the ≤ 17 ms /
  20-of-20 rule.
- **Close flow:** the "Stopping the solver…" modal instead of the bare 10 s join (UXR-1
  point 3, `run_controller.py`); drain re-entrancy (UXR-22).
- **0-D parsing:** typed zeros and wrong-count triplets (UXR-16, UX-9 / UX-10, E4;
  `models/`, Tk gate).
- **Low UXR:**
  - zoom reset on plots (UXR-18);
  - stale copy `Exec 1 … 1000`, the gauge-note link, and the stop reason in Pa
    (UXR-19);
  - a dimension click from another screen goes to Setup (UXR-20);
  - a clickable status line and sticky errors (UXR-21);
  - dialog parents (UXR-23);
  - an off-screen geometry clamp (UXR-24);
  - QSS pins for the Banner action and the PointList ± buttons (UXR-25);
  - hide the 3D button on 1D / 2D runs (UXR-26).
- **QA S4 notes:**
  - the notification sender reads "Python 3.12" (S4-b, needs a Start-menu shortcut);
  - a stale `✓ Done` after Save as or a dimension switch (S4-c, amend D68);
  - strip captions gone at 1100 (S4-d, D29);
  - the progress caption and the status-bar chain line are clipped (S4-e);
  - 0-D preview text "Enter a valid case…" with Case OK (S4-f);
  - a log colour scale on Field whole run (S4-g);
  - start-up probe flicker (S4-i);
  - the `now` label overlaps the trace (S4-j).
- **Earlier F-rows:** F2 (`MplCanvas` 1 px column), F3 (point tables wider than the
  column), F11 (watch).
- **Tk, owner's decision:** P2-24's Tk half (faint light-mode sidebar and dimension
  buttons, `blastlab/gui/`).
- **Office machine:** `_e2e_ui_chain_foam.py`, harness F07, F6 `_e2e_ui_view3d.py`,
  P1-7's on-screen check, F36's Keep-all-fields variant if not run in T22.
- **Unchanged from GUI-10's backlog:** OUT-4's ParaView look, the HD1 open items, the P1
  owner decisions, the P2 display and test items, P3 / P4.
