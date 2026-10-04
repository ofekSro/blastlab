# GUI-11 part 11a — implementation report (T1-T6)

Batch plan: `docs/batches/2026-10-03-gui-polish.md`, part 11a only.
Branch `gui-redesign`, from `8bf158a`. One commit per task, then this
report. 11b-11d are later runs.

Before starting:
- CLAUDE.md §8.2 dry run: `auto_cleanup` reads `False`.
- Baseline, the 11a close list, one suite at a time: all green.
- Working tree: only the six never-stage paths were dirty.

During the run, someone else committed `305a351` (TODO.md only) on
this branch. The work continued on top of it. An untracked `.claude/`
also appeared. Neither was staged.

---

## T1 · UXR-4: the crash dialog only on the GUI thread — DONE

**What was done.** `crashlog._report` still writes the log file and
stderr on the raising thread. The QMessageBox is now built only on the
main thread. A worker's crash reaches it through a module-level relay:
a `QObject` with a queued `Signal(object)`, made in `install()`.
Offscreen there is still no box. `ThreadBridge.post` does nothing once
`shiboken6.isValid(self)` is False.

**Files:** `blastlab/ui/crashlog.py`, `blastlab/ui/bridge.py`,
`blastlab/tests/test_ui_crashlog.py`.

**Tests:** `cd blastlab/tests && python test_ui_crashlog.py`. It now
has 14 checks. The 10 old checks are unedited.

**Criteria**
- PASS. An exception in a `threading.Thread` writes the log and builds
  no QMessageBox on that thread. The box class is replaced by a
  recording subclass, and the offscreen suppression is lifted for the
  check. After a pump, the box was built once, on the main thread.
- PASS. `bridge.post` on a deleted `ThreadBridge` raises nothing.
- PASS. Real platform: `app.main()` was started once, with throwaway
  settings. The relay is created before the QApplication, and it lives
  on the GUI thread (`relay.thread() is app.thread()`).

**Commit:** `73ee673`.

## T2 · UXR-1 = QA S2-2: ask before discarding a run or edits — DONE

**What was done.** New `MainWindow._confirm_discard(action)`. Every
question goes through the new `dialogs.ask_discard(kind, text,
parent, title)`.
- **Close** asks first about a live run: `Stop <model> at N % and
  quit?`, from `_stop_question`, with `Stop and quit` / `Keep
  running`. For a busy HD 1.3 assessment it asks `An HD 1.3
  assessment is still writing <model>. Quit anyway?`.
- **Then, if dirty:** `Save the changes to <file>?`, with Save /
  Discard / Cancel. A Save that writes nothing cancels the action.
- **Open and Recent** ask about unsaved edits only, before the file
  dialog or the read.
- **For tests:** `testing.ensure_qapp()` installs `answer_discard()`,
  a recorder that answers "proceed" (D202).

**Files:**
- `blastlab/ui/app.py`, `dialogs.py`, `testing.py`;
- new `blastlab/tests/test_ui_close_guard.py`;
- `blastlab/tests/_e2e_ui_viewer_place.py` and `_qa_ui_perf.py`:
  both close a dirty window, so they call `answer_discard()`;
- `docs/qa/2026-10-03-gui-polish/gui11-close-dirty.png`.

Two of the four window builders without `ensure_qapp` are unchanged:
- `_e2e_ui_view3d.py` closes a clean, idle window that was opened from
  a file;
- `test_settings_path.py` builds no window.

**Tests:** `python test_ui_close_guard.py` (offscreen, 18 checks).

**Criteria**
- PASS: C1, a dirty window on Close.
  - Cancel: the window stays and the case is unchanged.
  - Discard: it closes, and the file is untouched.
  - Save, with a path: the file is written, then it closes.
  - Save on an untitled case, with Save as cancelled: it stays open.
- PASS: C2, a dirty window and Open.
  - Cancel: no file dialog opens (the patched `open_file` is not
    called), and the case and the path are unchanged.
  - The same holds for a Recent action.
  - Discard on that Recent action opens wall_B.
- PASS: C3. A clean window Opens and closes; the recorder's list stays
  empty.
- PASS: C4, a live run (a patched `running`).
  - Keep running: `event.isAccepted()` is False, and no stop or
    shutdown is sent.
  - The question reads `Stop QA_RUN and quit?`.
  - A busy HD 1.3 assessment gets its own question.
- PASS. Also green: `test_ui_frame`, `test_ui_results_screen` and
  `test_ui_run_screen`. Harness `--solver native --scenario
  B01,B02,K01`, offscreen: no finding (`~\blastlab_qa\gui11-a-t2`).
- PASS. Real platform: a real `WM_CLOSE` (PostMessageW) on a dirty
  window shows `Save the changes to untitled?` with Save / Discard /
  Cancel. Cancel keeps the window open: Win32 `IsWindowVisible` is
  True, the window is still dirty, and Lx is still 5.5. Screenshot:
  `gui11-close-dirty.png`.

**Commit:** `4d696c2`.

## T3 · UXR-5: Save as reports a write failure — DONE

**What was done.** `_save_case` catches `OSError` the way Save does:
one `Save case` error, `Could not write <path>: <reason>`. The path,
the dirty flag and Recent are unchanged.

The new `_save_as_start()` passes `start` to `save_file`:
- the case's folder;
- else the newest Recent entry's folder;
- else the Runs folder.

It takes the first of these that exists. The name is `<stem>.json`,
or `<Model box>.json` for an untitled case (D204).

**Files:** `blastlab/ui/app.py`, `blastlab/tests/test_ui_frame.py`
(F11). `dialogs.save_file` already took `start`, so it is unchanged.

**Tests:** `python test_ui_frame.py`, F11 (6 checks).

**Criteria**
- PASS. Read-only target, through the Ctrl+Shift+S shortcut: one
  `show_error` titled `Save case`, `crashlog.last_crash` unchanged,
  the window still dirty, and the path and Recent unchanged.
  - Note: Windows ignores a folder's read-only flag when a new file is
    created. So the target file itself is read-only, inside a
    temporary folder.
- PASS. The `start` argument equals `<case folder>\parity.json`.
- PASS. The untitled fallbacks: the newest Recent entry's folder, then
  the Runs folder, with `QA_MODEL.json`.

**Commit:** `2ed1ef4`.

## T4 · UXR-7: F5 on the Chain screen runs the chain — DONE

**What was done.** The F5 shortcut calls `MainWindow._f5`:
`chain.run()` on the Chain screen, `_run_single()` elsewhere. There
are still exactly five shortcuts. The Run chain button's tooltip
reads `Run the chain (F5)` (D205).

**Files:** `blastlab/ui/app.py`, `blastlab/ui/chain_panel.py`,
`blastlab/tests/test_ui_frame.py` (F12).

**Tests:** `python test_ui_frame.py`, F12 (4 checks).

**Criteria**
- PASS. On Chain, the F5 `activated` calls a patched `chain.run`
  once and `_run_single` never.
- PASS. On Setup, the reverse.
- PASS. The F5 pin (exactly five shortcuts) is green.
- PASS. Real platform: harness `--window --solver native --scenario
  B06` passed every check (Ctrl+O, Ctrl+S, F5, plain Esc, Shift+Esc),
  with no finding (`~\blastlab_qa\gui11-a-t4-b06w`).

**Commit:** `8042d5d`.

## T5 · UXR-8 + F12 (GUI-11 d) + QA S3-3: the 0-D run flow — DONE

**What was done**
- `_run_hd13` shows 02 Run once its worker thread has started.
- While the assessment works, these are greyed (state greys):
  - Setup's Run F5 and Initialise (`SetupStrip.set_busy`), so a live
    validation cannot re-arm them meanwhile;
  - Run chain (`ChainPanel.set_busy`).
- F5 while busy shows `An HD 1.3 assessment is running.` (notify,
  info).
- At 0-D, `RunPanel.set_dim` hides the view toolbar row (now its own
  widget, `_view_bar`) and the `runview` frame. One note takes their
  place.
- An assessment start hides the last run's banner. Afterwards the
  percent tile reads `—`.

**Files:**
- `blastlab/ui/app.py`, `run_panel.py`, `setup_strip.py`,
  `chain_panel.py`;
- `blastlab/tests/test_ui_run_screen.py` (R11);
- `blastlab/tests/_e2e_hd13_gui.py` (F39);
- `docs/qa/2026-10-03-gui-polish/gui11-0d-run-busy.png`.

**Tests:** `python test_ui_run_screen.py`. R11 adds 13 checks;
`assessment.run` is blocked on an Event.

**A golden that went red on the first try, and why it is green.**
`test_ui_char_hd13_run` failed once: `status_timer_active` was true
where the golden says false, in the scenario where the assessment
raises. The cause was the new notify on the second, busy press.
- Fix in the app: leaving the busy state now stops that message's
  timer and restores the shortcuts label.
- So `_hd13_done` reports exactly as before.
- The golden was not touched, and it is green.

**Criteria**
- PASS. After Run on 0-D:
  - `current_tab() == 'run'`;
  - `setup.strip.run_btn` and `chain.run_btn` are disabled;
  - the toolbar row and `runview` are hidden (`isVisibleTo`), and the
    note is visible;
  - the banner is hidden.
- PASS. A validation while busy keeps Run F5 grey.
- PASS. F5 while busy gives the status text.
- PASS. After release, the tile reads `—`, and Run F5 and Run chain
  are enabled again.
- PASS. Back on 2D, the toolbar and the view are visible again.
- PASS. `test_ui_char_hd13_run` and `test_ui_frame` are green and
  unedited.
- PASS. Real platform: `_e2e_hd13_gui.py` passes, 31 checks, after
  the F39 fix.
- PASS. The real-platform busy shot `gui11-0d-run-busy.png` was taken
  in a window that Win32 reports visible. It shows:
  - 02 Run, with Run greyed;
  - the note in place of the view;
  - no banner;
  - the tile at `—` after the assessment (`done in 24 s`).

**Commit:** `6c22c40`.

## T6 · P2-18 (dialog half) + P2-24 (Qt half) — DONE

**What was done**
- `_model_target(title)` titles the in-progress refusal with `title`.
  The Chain passes `Run chain`.
- Every `dialogs` message box goes through `_keep_paths`.
  - The text label's minimum width is the longest path token's
    advance. It is capped at 70 % of the screen, and under
    QMessageBox's own hard limit.
  - Measured on the real platform first: the minimum width alone did
    **not** work. Qt still broke between `C:` and `\`.
  - Two rich-text variants were also tried: a `white-space: nowrap`
    span and `<nobr>`. Neither helped.
  - So in addition, a path whose line would not fit starts a new line.
    The space before it becomes a line break, and no invisible
    character is added (cf. F23).
  - A path past the cap elides in the middle, with the whole text in
    the label's tooltip. The text is selectable (D207).
- `widgets.wrap_tip` wraps tooltips over 60 characters: rich text in
  a 400 px table, about 432 px on screen. `FieldForm` applies it to
  every spec row tooltip. `models/` text is unchanged (D208).

**Files:**
- `blastlab/ui/app.py`, `dialogs.py`, `widgets.py`, `fieldform.py`;
- `blastlab/tests/test_ui_frame.py` (F13), `test_ui_output_card.py`,
  `_qa_ui_harness.py` (V06);
- three shots in `docs/qa/2026-10-03-gui-polish/`.

The plan's `chain_panel.py` needed no change for T6: `_run_chain` in
`app.py` passes the title.

**Tests:** `python test_ui_frame.py` (F13, 6 checks),
`python test_ui_output_card.py` (162 checks).

**Criteria**
- PASS. Offscreen: the Keep all fields `toolTip()` starts with `<`,
  and its plain text (`tip_text`) equals `KEEP_ALL_TIP`. This is
  checked in 1D, 2D and 3D.
- PASS. A Chain run during a busy assessment is impossible from the
  UI, because Run chain is greyed (T5; real shot
  `gui11-chain-during-hd13.png`).
- PASS. The `_model_target('Run chain')` refusal, with `show_info`
  patched, is titled `Run chain`.
- PASS. Real platform, 1920 px screen: the overwrite question for
  `QA_MODEL` under a 70-character `C:\…` runs folder.
  - The label's text was replayed at its real width. Its lines:
    `QA_MODEL already exists in` / `C:\Users\OFEKRO~1\…\runs_seventyxxx.`
    / `Overwrite? …`. The path is on one line.
  - The box is Win32-visible. Shot: `gui11-dialog-path.png`.
  - The same box without the rule (the base behaviour) breaks the
    path after `C:`.
- PASS. Real platform: the Keep all fields tooltip is 432 px wide
  (Win32 `GetWindowRect`), under 450. Shot:
  `gui11-keepall-tooltip.png`. The first try, with a 420 px table,
  measured 452 px, so the table is now 400 px.
- Re-check as in GUI-10 T11:
  - P2-18, Qt half: **gone**. Run chain is greyed during the
    assessment, the refusal is titled after the action, and the path
    stays whole.
  - P2-24, Qt half: **gone**. The tooltip is wrapped to 432 px; it was
    one 976 px line.
  - The Tk half of P2-24 is untouched (backlog).

**Commit:** `edc1154`.

---

## The 11a close

**Suites**, one at a time. All rc 0; the numbers are checks passed:

| Suite | Checks |
|---|---|
| `test_ui_frame` | 77 |
| `test_ui_run_screen` | 194 |
| `test_ui_results_screen` | 186 |
| `test_ui_chain_screen` | 196 |
| `test_ui_chain` | 114 |
| `test_ui_crashlog` | 14 |
| `test_ui_close_guard` | 18 |
| `test_ui_setup_tree` | 238 |
| `test_ui_parity` | 41 |
| `test_ui_char_case_form` | green |
| `test_ui_char_chain_wiring` | green |
| `test_ui_char_hd13_run` | green |
| `test_ui_char_results_exports` | green |
| `test_ui_char_results_meta` | green |
| `test_ui_char_write_failure` | green |
| `test_ui_output_card` | 162 |
| `test_ui_setup_strip` | 110 |
| `test_ui_run_panel` | 59 |
| `test_ui_no_vtk_in_main` | 9 |
| `test_ui_no_mpl_pyplot` | 19 |

Also green after T6, run then: `test_ui_setup_form` (91) and
`test_ui_components` (34).

**Harness.** `--solver native --scenario S00,B01,B02,B04,B06,B07,K01`
offscreen gave no finding (`~\blastlab_qa\gui11-a-close`).

**Regression.** `test_regression`: **PASS**, byte-identical. Seven
files are byte-identical, and `b2_profile.npz` has equal arrays. No
baseline file shows as modified in `git status`.

**Frozen paths.** `git diff 116ea96..HEAD` over the plan's frozen list
is **empty** (0 lines):
- `blastlab/gui`, `core`, `models`, `output`, `viz3d`, `solvers`,
  `services`;
- `ui/view3d_host.py`, `ui/run_controller.py`, `ui/viewer_link.py`;
- `tests/baseline`, `foam_fixtures`, `foam_golden`, `char_golden`.

**Never-stage list.** None of the six paths is in any 11a commit.

**App start.** `ui.app.main()` was started once on the real platform
with throwaway settings. Result: **PASS**.
- The platform is `windows`, and the window was visible.
- The crash relay exists and lives on the GUI thread.
- After 4 s the app quit with exit code 0.

## Changed assertions (plan §9 listing)

1. `test_ui_output_card` C11, Keep all fields, 1D / 2D / 3D:
   - before: `w.toolTip() == F.KEEP_ALL_TIP`;
   - now: `tip_text(w.toolTip()) == F.KEEP_ALL_TIP`.
   - Reason: P2-24 / D208. The tooltip is now wrapped rich text, and
     its words are unchanged. The comparison is still exact.
   - A new check asserts the rich text.
2. `test_ui_output_card`, the 3D decimation spin box: the same change
   for `F.VTK_DECIMATE_TIP`, which is also over 60 characters.
3. Harness V06: the same change for `KEEP_ALL_TIP`.
4. `_e2e_hd13_gui.py` (F39): the Heat control card's node is selected
   before the Win32 probe. No assertion text changed.

Only new checks were added elsewhere:
- `test_ui_crashlog`: 4 checks;
- `test_ui_frame` F11-F13: 16 checks;
- `test_ui_run_screen` R11: 13 checks;
- `test_ui_close_guard`: new suite.

No behaviour or number assertion was weakened. No golden was edited.

## All files touched in 11a

- `blastlab/ui/`: `app.py`, `bridge.py`, `chain_panel.py`,
  `crashlog.py`, `dialogs.py`, `fieldform.py`, `run_panel.py`,
  `setup_strip.py`, `testing.py`, `widgets.py`.
- `blastlab/tests/`:
  - new: `test_ui_close_guard.py`;
  - changed: `test_ui_crashlog.py`, `test_ui_frame.py`,
    `test_ui_run_screen.py`, `test_ui_output_card.py`,
    `_qa_ui_harness.py`, `_e2e_hd13_gui.py`,
    `_e2e_ui_viewer_place.py`, `_qa_ui_perf.py`.
- `docs/qa/2026-10-03-gui-polish/`: `gui11-close-dirty.png`,
  `gui11-0d-run-busy.png`, `gui11-chain-during-hd13.png`,
  `gui11-dialog-path.png`, `gui11-keepall-tooltip.png`.
- `docs/gui-redesign-decisions.md`: D202-D208, F39, and the Outcome on
  F12.
- This report.

## GUI screens touched (for QA)

- **Window close, Open, Recent:** the new Save / Discard / Cancel
  question and the run / HD 1.3 questions.
- **Save as:** the start folder and the error dialog.
- **Chain:** F5, the Run chain tooltip, and Run chain greyed during an
  HD 1.3 assessment.
- **02 Run at 0-D:** the note in place of the toolbar and the view; no
  banner at an assessment start; `—` after.
- **01 Setup:** Run F5 / Initialise greyed during an assessment; every
  long field tooltip is wrapped.
- **Every message box from `ui.dialogs`:** selectable text, and a path
  starts its own line when its line would not fit.

## Numerical changes

None. No solver, solver default, case key, file format or export
byte was touched. The `test_regression` result is above.

## D / F rows added

In `docs/gui-redesign-decisions.md`:
- D202 (T2), D203 (T1), D204 (T3), D205 (T4), D206 (T5), D207 (T6,
  dialogs), D208 (T6, tooltips);
- F39 (`_e2e_hd13_gui`'s stale Heat control, fixed);
- the Outcome on F12.

D200 and D201 belong to 11b and were not written here.

## Suspected issues noticed, not changed

1. **The busy message clears early.** When F5 is pressed during an
   assessment, its status message clears after the usual 12 s, so the
   status line can be empty for the rest of the assessment. The Run
   screen's bar and time line still show it. Noted in D206.
2. **A blocked F5 on the Chain screen.** F5 on Chain during an
   assessment still reaches `chain.run()`. It validates the stages and
   then meets the window's refusal dialog, titled `Run chain`. The
   button is greyed. The `_run_single` path notifies instead. The two
   could be made the same in a later pass.
3. **The probe started WSL.** The real-platform probes start in
   blastFoam mode, because the private settings have no `solver` key.
   They run the WSL availability check (`foam_env.ensure_check_started`).
   No solve was started.

## Open questions for the owner

None blocking. D202-D208 are defaults and are open to review like the
others.
