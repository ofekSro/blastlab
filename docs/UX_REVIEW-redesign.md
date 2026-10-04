# blastlab - UX review of the redesigned Qt GUI

Reviewed 2026-10-03 on branch `gui-redesign` at HEAD `c94917d`. Read-only. The GUI
was not launched, because building it can start the run-corpus cleanup (CLAUDE.md
§8.2) and a QA agent was running the app at the time. The flows below come from
reading `blastlab/ui/` and the board sources, plus the GUI-10 real-platform
screenshots in `docs/qa/2026-10-03-gui-qa/`. Each finding cites a file and line.

This file sits beside the earlier review, `docs/UX_REVIEW.md`, and does not
replace it (decision D199). The earlier findings are cited as `UX_REVIEW.md` §3 /
UX-n. The new findings are numbered **UXR-1 … UXR-26**, so they cannot be confused
with UX-n, the D-rows, the F-rows or the `DONE.md` ids.

The approved layout is not re-opened here. Owner-approved D-rows (owner review,
2026-10-03) are treated as settled. Where a finding touches one, it says so.

These behaviours are intentional and are **not** reported as defects:
- the solver switch hides controls that do not apply;
- the displayed impulse is net overpressure impulse;
- near-field arrival times differ between native and blastFoam;
- Run chain stays enabled with a stage error (D137);
- the Viper-style greying of the VTK interval boxes (`case_form.py:443-450`);
- the 0-D spread rows and the wall H/W are greyed on purpose (`case_form.py:460-480`).

Audience: the owner, who is the only user and works from the boards. Priorities
follow what costs that user time or produces a wrong number in a thesis.

---

## 1. Framework and screens

Framework: **PySide6 (Qt 6)**. Entry point: `python -m blastlab` → `ui/app.py:main`.
Plots on screen are pyqtgraph. The Setup previews are matplotlib `Figure`s, never
`pyplot`. The 3D view is a pyvista child process embedded by `view3d_host.py`.

- **Window frame** (`app.py`, `topbar.py`): the top bar holds the workflow pills, the
  Chain link, the case menu, the solver chip and the dimension control. Below it are
  the screen stack and the 28 px status bar.
- **01 Setup** (`setup_panel.py`, `setup_tree.py`, `setup_strip.py`, `setup_nodes.py`,
  `case_form.py`, `fieldform.py`, `setup_spec.py`, `model_overlay.py`): the case in
  three columns (model tree, centre with the strip, the model view and a dock, and
  properties).
- **02 Run** (`run_panel.py`, `run_controller.py`, `run_dock.py`, `run_gauges.py`,
  `run_clock.py`, `chain_strip.py`): start, stop and step a run, and watch it.
- **03 Results** (`results_panel.py`, `results_list.py`, `results_method.py`,
  `results_field.py`, `results_gauges.py`, `export_column.py`, `results_stages.py`):
  read and export a result.
- **Chain** (`chain_panel.py`, `chain_pipeline.py`, `chain_stage.py`,
  `chain_route.py`): a 1D → 2D → 3D staged run.
- **Dialogs**:
  - the runs browser (`run_browser.py`, blastFoam only);
  - Show case (read-only), Stop the run, Long run, Model folder overwrite;
  - the file pickers (`dialogs.py`);
  - the crash dialog (`crashlog.py`);
  - the Windows notification (`dialogs.notify_desktop`).

---

## 2. User flows (reconstructed)

### 2.1 Frame and start-up

1. `crashlog.install()`, then `QApplication`, the theme and the app icon
   (`app.py:1481-1505`).
2. `MainWindow` restores the solver mode, the window geometry, the refresh policy and
   the runs folder (`app.py:515-531`). The start size is 1280 × 840 and the minimum
   is 1100 × 720.
3. The auto-cleanup runs only if it is on (the default is off, owner 2026-09-27).
   The disk check only warns, on the status line and in the log
   (`app.py:212-217, 1444-1448`).
4. The window opens on 01 Setup, 2D.
5. Keyboard (`app.py:504-513`): Ctrl+O, Ctrl+S (save in place), Ctrl+Shift+S
   (Save as), F5 run and Shift+Esc stop. All five are window-wide QShortcuts.
6. Case menu (`app.py:285-316`): Open…, Save, Save as…, Recent ▸ (8 entries),
   Dark mode, and a disabled credit line.
7. Title: `[Chain k/n ·] [pct % ·] [✓ Done ·] [● ]<case> · BlastLab`
   (`app.py:744-757`).

### 2.2 01 Setup: what the user meets, in order

- **Tree** (left). The nodes are 01 Threat, 02 Domain & mesh, 03 Boundaries,
  04 Structure (one child row per obstacle), 05 Gauges (one child row per gauge),
  06 Solver and 07 Output. Each row has a mono summary and a ✓/✗ mark. Under the
  tree are + Gauge, + Obstacle and the case pill (`Case OK · N notes` or
  `N errors`). The 0-D tree has one node per card.
- **Centre**:
  - the live strip: Charge, Cells, MPI ranks, Memory and Z at gauges, then Run F5
    and Initialise. A tile hides when the report lacks its number (D31).
  - the model view toolbar: the plane caption (the hover readout while the pointer is
    on the model), then Z rings, Mesh and Fit.
  - the preview: 1D/2D in matplotlib, 3D in the embedded viewer.
  - the dock: Gauges (Gauge · coordinates · R · Z · Where), Checks (errors, then
    warnings, then notes) and Log.
- **Properties** (right): the selected node's cards only, from the `FieldForm`
  engine.
  - Every number is a `QLineEdit`, and its unit is in the caption (`[m]`, `[kg TNT]`,
    `[s]`; D15 deferred the in-box suffix).
  - Point lists are a table plus one entry line with + and −.
- **Validation.** Every edit restarts a 300 ms debounce (`app.py:79-82, 719-723`).
  `get_case()` collects every parse error and the bad fields get a red border.
  `validate_case()` then adds range errors, warnings and notes. The report feeds the
  pill, the Checks tab, the strip's Run button, the Run screen's `Setup:` link and
  the Setup ✓ on the pill (`app.py:763-816`). Tree ✗ comes **only** from parse
  errors (`setup_panel.py:603-605`).
- **Run F5 from Setup.** A blast case is validated, the long-run question is asked if
  needed, the model folder is checked (it asks before overwriting), and the window
  switches to 02 Run (`app.py:819-850`). A 0-D case goes to `_run_hd13`, which
  stays on Setup (§2.6).

### 2.3 02 Run

- **Controls** (left): Runs folder (+ browse) and Model, with the resolved path
  under them. Then Stop (Shift+Esc), or Run / Run again, and the 3D button. Then
  Step through (folded: Initialise model, +1 … +1000, To the end, Pause), Live view
  (Refresh every, the Colour range: auto switch, Min/Max only when it is off), and
  at the bottom the `Setup: Case OK · N cells` link.
- **Centre**:
  - the chain slot, used only for a chain;
  - the progress tile (`% · elapsed · about X left`, the ETA from 5 %), then Time
    [ms], Step (dt in s in its caption), P max [kPa], and Cells (AMR only);
  - the finish banner with `Open in 03 Results →`;
  - the view toolbar (Live slice · Gauges · 3D view, Show mesh), the view itself,
    and the dock (Log · Messages · Earlier runs, Copy, Save log…).
- **Live gauges** (right): the selected gauge enlarged, then the list sorted by Z
  (R when Z is hidden) with sparklines and the peak so far, or `waiting`.
- **Threading.** `SolverWorker` is a thread. A `queue.Queue` is drained by a 50 ms
  `QTimer` (`run_controller.py:367-401`); frames are latest-wins.
- **Stop.** Under 30 s of run time it stops at once. After that it asks first
  (`app.py:1080-1122`).
- **End of run.** The banner appears, and if the run ended on its own, `✓ Done` in
  the title and a desktop notification (`app.py:1338-1372`). An error gives
  `Run failed` and a dialog (`run_controller.py:366-371`).

### 2.4 03 Results

- **Left column.** The results list (a chain is one entry with STAGE tabs), Load a
  run… (blastFoam only), ✕ Remove, the HOW IT WAS COMPUTED card with Show case and
  Load into 01 Setup, and the model-folder path.
- **Centre: Field.** Overpressure / Density / Speed / Peak / Impulse (/ Isosurface);
  Colours (whole run / each frame / manual, Min/Max only when manual); Show mesh; a
  pyqtgraph map with a colour bar and a hover readout; the time bar (Play, time,
  slider, arrival ticks, frames, speed, This frame .png).
- **Centre: Gauges.** One plot (the selected gauge in cyan with its positive phase
  shaded) and a readout. The table has Gauge · Z · Peak · Arrival · t peak ·
  Pos. phase · Pos. impulse · Net impulse · Phase ended, with Copy table (Ctrl+C
  inside the table).
- **Centre: 3D.** The embedded viewer.
- **Export column.**
  - Data: Summary .csv, Gauge traces .txt, Field snapshot .csv, Profile, and VTK
    (blastFoam only).
  - Figures: All plots .png, Report .html, Animation.
  - Title on figures, and Open the 3D viewer.
  - A busy strip replaces the button while it writes.
- **Writing.** The file dialog runs on the GUI thread. The writing runs on a
  `threading.Thread` and the busy strip comes down through the bridge
  (`exports.py:97-125`).

### 2.5 Chain

- **Top.** The route (1D→2D→3D, 1D→3D, 1D→2D, 2D→3D) and the caption `New stages
  take the charge, material and solver from 01 Setup.` Then the pipeline cards,
  with the hand-off file named on each arrow, and Run chain with `N stages · into
  \<model>\` under it. A refusal line runs full width under the pipeline.
- **Stage editor.** It uses the Setup layout. A `00 Stage` node holds the solver for
  the stage, HAND-OFF IN, HAND-OFF OUT and the stage's Checks. The 1D/2D stages have
  a matplotlib preview; a 3D stage has a text hint instead (D134). Copy from 01 Setup
  and Load case… sit under the tree.
- **Live checks.** They use the 300 ms debounce and wait while the screen is hidden
  (D150).
- **Run chain.** It wires the hand-offs, re-checks everything, and then runs through
  `MainWindow._run_chain`. The model folder is the **Run screen's** Runs folder and
  Model (`chain_panel.py:61`).

### 2.6 0-D (HD 1.3) assessment

- Setup 0-D has one tree node per card. There is no strip tile and no Initialise
  (D31).
- Pressing Run F5 validates the case, checks the model folder, and starts a daemon
  thread that runs `hd13_service.run_into_model_folder`. The thread posts
  `_hd13_done` through the bridge (`app.py:901-950`).
- While it runs, the Run screen's bar is indeterminate and its Run button is off
  (`run_panel.py:1216-1245`). **The window stays on Setup.** The status line says
  `HD 1.3 assessment running…`.
- When it ends, the log lists the report and the SBEDS CSV paths and the status line
  shows a one-line summary. Nothing opens and no Results entry is made.

### 2.7 Errors

- **Parse errors.** Red borders, and the Checks rows. Run is refused with a dialog.
- **Validation errors.** The pill shows `N errors` and Run F5 is greyed. The tree
  stays ✓ (F7).
- **A run exception.** The worker posts the traceback, and `Run failed` shows the
  headline.
- **Export failures.** They go to the log and the status line. A VTK failure also
  gets a dialog (D85).
- **Open errors.** Specific messages for a missing file, bad JSON, a missing key,
  and an OS error (`app.py:567-589`).
- **Anything uncaught.** It goes to `crashlog` (see UXR-4).

---

## 3. Findings

Severity rule: threading and data-loss issues are always **high**. There are 26
findings: 5 high, 12 medium and 9 low.

What works well and should be kept:
- the three-column screens are as drawn;
- every Setup number is read from the validation report, never computed again;
- the hand-off texts come from the wired case, so they cannot drift from the run;
- the run worker, queue and bridge (no widget is touched by the solver thread);
- the busy strips on exports;
- the Stop rule;
- the per-run logs;
- the Copy table output;
- Load into 01 Setup refuses to overwrite `MODEL.json`.

### High

**UXR-1. Closing the window, Open and Recent all discard a live run or unsaved edits without asking.**
This is UX-4 (still open) plus the part of UX-8 that is left.
- Where: Main window. `app.py:1462-1478` (`closeEvent`), `app.py:591-612`
  (`_open_case`, which Recent also calls at `app.py:315-316`), and
  `run_controller.py:425-429`.
- What the user experiences:
  - **Clicking ✕ during an hours-long blastFoam run** stops it with no question. The
    GUI then blocks for up to 10 s in `worker.join`.
  - **Closing during an HD 1.3 assessment** kills its daemon thread in the middle of
    the model-folder write.
  - **Unsaved edits.** The new `●` dirty state is tracked, but neither ✕ nor Open
    nor Recent consults it.
  - **The odd one out.** Load into 01 Setup does ask (`app.py:623-627`), so the app
    is inconsistent with itself.
- Fix: one `_confirm_discard(action)` helper on the GUI thread, called from
  `closeEvent`, `_open_case` and the Recent actions.
  1. If `ctrl.running` or `_hd13_busy`, ask `Stop <model> at N % and quit?`, add the
     resume sentence for blastFoam (reuse `_stop_question`), and on No call
     `event.ignore()`.
  2. If `_dirty`, ask Save / Discard / Cancel, where Save calls
     `_save_case_inplace`.
  3. Replace the bare join with a short modal "Stopping the solver…" that keeps the
     event loop alive.

**UXR-2. A gauge dropped by the solver renumbers the later gauges between Setup and Results, and Setup does not warn.**
- Where: Setup → Run → Results. The solver drops a gauge that lies inside an obstacle
  with only a log line (`solvers/solver2d.py:289`). Validation warns only about a
  gauge outside the domain (`services/validation.py:1560-1564`). The live column and
  the Results table number gauges in payload order (D61; `results_gauges.py:526`,
  `run_gauges.py:454`).
- What the user experiences: in Setup, G3 is the gauge at the wall face. One run
  later, Results shows it as **G2**, and the Results table has no coordinates to
  catch the shift. The GUI-10 shot `gui10-light-1100x720-run-running.png` shows
  `[warn] Gauge (1.4, 0.3) inside an obstacle - dropped` on the status line while
  the case pill had said `Case OK`. A peak can be attributed to the wrong position
  in a design calculation.
- Fix, in the UI only (display, no file changes):
  1. In `SetupPanel.refresh`, turn every gauge whose `scaled_distance.where()`
     returns `inside=True` (`scaled_distance.py:184-204` already computes it) into a
     Checks **warning**: `G3 (1.40, 0.30) is inside Wall 1 - the solver will drop
     it`. Put ! on 05 Gauges.
  2. In 02 Run and 03 Results, label each row with the **entered** gauge number.
     `run_gauges.match_gauges` already maps payload points to entered gauges for Z
     (D61, D99).

**UXR-3. In native mode the Material choice is shown and then silently replaced by TNT.**
This is UX-3, still open.
- Where: Setup → 01 Threat, native mode. `setup_spec.py:472-475, 484-487` (the row
  has no scope) and `models/fields.py:749-756` (native sends `material='TNT'`).
- What the user experiences: they pick ANFO, but the tree summary, the Charge tile,
  the run and `MODEL.json` all say TNT. In blastFoam mode the same row is honoured.
  This is a visible input that is silently overridden.
- Fix: the owner's D138 answer ("the native solver only knows TNT") settles the
  question. Give the row `scope='blastfoam'` so that native hides it (hide, never
  grey). Every value is kept, as for any hidden row. No number changes.

**UXR-4. The crash handler builds and runs a QMessageBox on whatever thread raised.**
- Where: all screens. `crashlog.py:122-131` (`threading.excepthook` → `_report` →
  `_dialog`, which constructs `QMessageBox()` and calls `exec()` on that thread).
- What the user experiences: nothing today. Every worker in `ui/` catches its own
  errors (export, frame PNG, foam load, probe, HD 1.3, runs browser). The first
  unforeseen exception in a worker would put a widget and a nested event loop on a
  non-GUI thread. That is undefined behaviour in Qt and can take the window down. One
  path is easy to reach: closing the window while an HD 1.3 assessment runs. The
  worker's `finally: self.bridge.post(...)` (`app.py:945-946`) then raises
  `RuntimeError` on a deleted `ThreadBridge`, which goes straight into this hook.
- Fix: in `_dialog`, show nothing unless `threading.current_thread() is
  threading.main_thread()`. Off the main thread, keep the log file and stderr. Hand
  the dialog to the GUI thread through a module-level `QObject` with a queued
  `Signal(object)`, created in `install()`. Also guard `ThreadBridge.post` with
  `shiboken6.isValid(self)`.

**UXR-5. Save as… lets an `OSError` escape to the crash dialog.**
- Where: the case menu → Save as…, and Ctrl+S on a case that has no path.
  `app.py:664-680`; the write at `app.py:675` has no try. Save in place catches it
  (`app.py:693-698`).
- What the user experiences: a read-only folder, a OneDrive lock or a full disk gives
  "unexpected error … the application may now be in an inconsistent state - save
  anything you care about and restart" for an ordinary save failure. The dialog
  also opens in the working directory with an empty name (`dialogs.py:59-68`;
  part of UX-8).
- Fix: wrap the write as Save does (`Could not write <path>: <reason>`). Start the
  dialog in the last case folder, with `<model>.json` as the name.

### Medium

**UXR-6. F7: a validation error leaves every tree node ✓, and a Checks row cannot take you to the field.**
- Where: Setup and the Chain stage editor. `setup_panel.py:603-605` (✗ only from
  `form.bad`), `setup_panel.py:717-744` (rows are selectable text, not links), and
  `chain_stage.py:463-466`.
- What the user experiences:
  - The pill says `1 error`, but all seven nodes show ✓. The user must open Checks,
    read e.g. `AMR max cells 2,000,000 exceeds…`, and guess which node holds it.
  - The same happens on the D27 trigger state: the dropdown is red while Checks says
    `Case OK`.
  - And with UXR-2's dropped gauge.
- Fix: a small `(regex → field name)` table in `setup_nodes.py`. Validation messages
  already start with the field's words (`Cell size`, `MPI ranks`, `AMR …`,
  `VTK sections:`, `Gauge (…)`, `Refinement zone`, `End time`; see
  `services/validation.py`). Map a match to `node_of_field`. Put ✗ on errors and !
  on warnings, and make a click on a Checks row select that node. An unmatched
  message still counts in the pill. Report D27's pending trigger as a Checks
  warning, `End the run at a gauge is on, but no gauge is chosen`.

**UXR-7. On the Chain screen, F5 runs 01 Setup's case, not the chain.**
- Where: Chain. `app.py:504-513` binds F5 to `_run_single` on every screen.
- What the user experiences: they set up three stages, press F5 (the status bar says
  `F5 run`), and a single run of a different case starts. If the Model name is the
  same, the model folder overwrite question then names the chain's folder.
- Fix: `('F5', lambda: self.chain.run() if self.current_tab() == 'chain' else
  self._run_single())`. Put `F5` on the Run chain button's tooltip.

**UXR-8. The 0-D run (F12, owner-approved as GUI-11 d) leaves the user on Setup with an armed Run button and a blast view.**
- Where: Setup 0-D and Run 0-D.
  - `app.py:901-950`: `_run_hd13` never calls `_show('run')`.
  - `app.py:952-980`: the busy state does not reach `setup.strip`.
  - `app.py:819-822`: F5 while busy returns silently.
  - `run_panel.py:973-985`: `set_dim` keeps the view toolbar, the view and the gauge
    column.
  - `run_panel.py:1235-1239`: when busy ends, the tile goes back to the *previous
    blast run's* percent.
- What the user experiences:
  1. They press Run on 0-D. Setup stays, and only the status line changes for about
     40 s (about 20 min with the band). Run F5 still looks armed, and pressing it
     does nothing and says nothing.
  2. If they go to Run, they see Live slice · Gauges · 3D view, Show mesh and the
     last blast field. That is F12.
  3. After the assessment, the Progress tile reads e.g. `100 %` beside `HD 1.3
     assessment · done in 41 s`.
- Fix:
  1. `_run_hd13` → `self._show('run')` after the thread starts.
  2. `_set_hd13_busy` → `self.setup.strip.set_run_enabled(not busy and …)`.
  3. At 0-D, `set_dim` also hides the toolbar row and the `runview` frame and shows a
     one-line 0-D note in their place. This is the owner's GUI-11 (d).
  4. When busy ends, set the tile to `—` rather than restoring the old percent.

**UXR-9. Removing a gauge silently re-targets the trigger gauge.**
- Where: Setup → 05 Gauges, and a Chain 2D stage. `fieldform.py:336-344`
  (`remove`), and `case_form.py:336-367`, where the dropdown refresh "never writes".
- What the user experiences: the trigger is G3. They remove G1. `trigger_gauge` stays
  `3`, which is now the old G4, so the run ends (or the chain hands off,
  `chain_route.out_text`) at a different gauge. The only clue is the coordinates in
  the dropdown text.
- Fix: in `CaseForm`, listen to the gauge list's removals.
  - Removing a row before the trigger decrements `trigger_gauge`.
  - Removing the trigger row itself blanks it and leaves D27's red pending state.
  - Loaded files are untouched: this applies only to an edit made in the session.

**UXR-10. "How it was computed" has one wrong unit and is missing rows the result already holds.**
- Where: Results, left column. `results_method.py:130-152, 196-224` and
  `results_panel.py:300-306`.
- What the user experiences (the GUI-10 shot `gui10-light-1100x720-results-2d-field.png`):
  1. **Planar charge.** `Charge 20 kg TNT · x 0.6, y 0 m` for a **planar** case,
     whose charge is kg per metre. The Setup tile and the tree say `kg/m`
     (`setup_strip.py:113`, `setup_nodes.py:218`).
  2. **Precision.** `Mesh cell 12.4352 mm`, because `{dx*1000:g}` prints 6
     significant figures.
  3. **Missing method rows.** No row for the EOS or the reconstruction order of a
     native run. `meta['eos']` is in the result (`solvers/solver2d.py:526`) and
     `order` is in `MODEL.json`.
  4. **No profile start.** No row says a stage started from a hand-off. `init_mode`
     and `profile_file_in` are in `MODEL.json`, and native `meta['from_profile']`.
  5. **Afterburn caveat.** `Afterburn miller` does not say that only TNT is
     calibrated (CLAUDE.md §7).
  6. **Ended row.** The validity statement is the row that gets elided at 280 px
     (`shock arrived at a term…`).
- Fix:
  1. `kg/m` when `meta['geometry'] == 'planar'`.
  2. `{:.3g}`.
  3. Add `EOS`, `Order` and `Started from` (`1D profile · handoff_1d_to_2d.txt`)
     rows, read from the same sources and shown only when present.
  4. Show `miller (calibrated for TNT only)` when the material is not TNT.
  5. Let the Ended value word-wrap onto two lines.

**UXR-11. Axis and quantity labels contradict each other (F4 and two siblings).**
- Where: Setup 2D axisymmetric and the Chain 2D stage.
  - **F4.** `setup_spec.py:515-535`: the Gauges, Obstacles, Refinement zones and
    Detonation points columns stay `x y` / `x0 x1 y0 y1`, and the entry hint reads
    `add a row: x  y`. Meanwhile the tree says `r 3.0–3.2`, the gauge table says
    `r [m] z [m]`, and the case form relabels only Lx, Ly, cx, cy and charge
    (`case_form.py:428-436`).
  - **Preview axis.** `output/preview_draw.py:146` labels the vertical axis `y [m]`
    in axisymmetric (see the Chain shot), next to an `r [m]` horizontal axis and the
    caption `r–z plane`.
  - **`Height Z [m]`** (`setup_spec.py:558`) sits on the same screen as the scaled
    distance `Z [m/kg^1/3]`, the Z rings and `Z at gauges`.
  - **The charge caption** says `Charge [kg TNT]` (`setup_spec.py:471, 484, 560`),
    while the strip, the tree and the method card print `kg <material>`. The board
    writes `Charge mass [kg]` with Material beside it. This is the E1 question in
    `UX_REVIEW.md` §6.
- Fix:
  1. Extend the axisymmetric hook to the point-list headers (`r z`, `r0 r1 z0 z1`)
     and to the hint.
  2. Relabel the preview's y axis Qt-side after `preview_draw`, as `model_overlay`
     already draws Qt-side, or change line 146 (shared `output/`; run the Tk gate).
  3. Rename to `Height H [m]`.
  4. Use `Charge mass [kg]` (`[kg/m]` planar). Plan §9 allows a caption pin the
     board renames to be updated.

**UXR-12. The Chain screen hides the knowledge needed to use it.**
- Where: Chain.
  - `chain_panel.py:49-61, 189-197`: the whole route explanation (`HINT`) is a
    tooltip on the route group, and the route buttons have none of their own.
  - `chain_stage.py:44-46, 175-180`: the 3D stage's hint.
  - The board's overlays are in `Chain.dc.html` script lines 297-300.
- What the user experiences:
  1. **No hand-off overlay.** The board draws on each stage's model what the
     hand-off means (`1D field, r ≤ 1.5 m` over the 2D domain,
     `Outer: ends the stage → handoff_1d_to_2d.txt`, `burst height from this
     stage's form`). The build draws the plain Setup preview, so the user cannot see
     whether the 1D field covers the 2D region they care about.
  2. **Misleading 3D hint.** It says the 3D view "is shown in 01 Setup", but 01
     Setup shows a different case.
  3. **Folder on another screen.** The model folder is set on 02 Run (refusal:
     `The Runs folder and Model boxes are on the Run tab.`), so a chain shares the
     single run's Model name by default and meets the overwrite question.
- Fix, without changing the approved layout:
  1. Draw the board's three annotations with `ModelOverlay` (a dashed circle of the
     1D domain radius about the burst point, and a text label). They are display
     only, from the wired case.
  2. Reword the 3D hint: `This 3D stage has no preview here. Its domain is
     6 × 6 × 4 m, burst at z 2.0 m (from the 2D profile).`
  3. Put a one-line tooltip on each route button (`1D → 3D: the 1D profile is placed
     around the 3D burst point; no 2D stage`).
  4. Make `3 stages · into \QA\` a link that opens 02 Run with the Model box focused.

**UXR-13. Point lists cannot be pasted or edited in place, which is a departure from the board.**
This is UX-22 in `UX_REVIEW.md`.
- Where: 05 Gauges, 04 Structure, Refinement zones, VTK planes (`fieldform.py:226-344`).
  The board BC_Combined Gauges page has a **Paste rows** button.
- What the user experiences: runs usually have 5+ gauges (owner, plan §6). Each is
  typed into one line and added with +. A typo means removing the row and typing it
  again. There is no Delete key and no paste from a spreadsheet.
- Fix:
  - **Paste rows…**: a multi-line entry that parses each line with the existing
    `add()` rules and rejects the whole block with the line number of the first bad
    row.
  - **In-place edit**: `ItemIsEditable` on the tree items, validated by the same
    parser on commit.
  - **Delete** removes the selected row. Combine it with UXR-9.

**UXR-14. A native result cannot be reopened in 03 Results after the session ends.**
- Where: Results. `results_panel.py:381, 890`: `Load a run…` is the WSL runs browser
  and is hidden in native mode.
- What the user experiences: every native run now has a complete model folder
  (OUT-1), but once the app closes, its Field and Gauges views are gone. The only
  ways back are to rerun or to open the files by hand. A blastFoam run whose WSL
  scratch was released cannot be reloaded either (F36).
- Fix (owner decision; there is no TODO id yet): `Open a model folder…` in both
  modes. It should read `MODEL.json`, the gauge TSV and the saved profile or frames,
  where the folder holds them, into a Results entry. This is a capability, not
  polish, so it belongs in TODO, P3.

**UXR-15. Units on screen still disagree in four places.**
This is the rest of UX-11.
- Where and what:
  - **Impulse.** The Field view's Impulse map and its Min/Max read `Pa·s`
    (`results_field.py:66` takes `output/plots.py:464`), while the Gauges table on
    the next tab reads `kPa·ms`. They are the same number with two labels.
  - **End time.** Typed in **s** (`setup_spec.py:122`), while every readout is in ms.
  - **P max.** Shown as `2.038e+05 kPa` (`run_panel.py:1398`, `,.4g`) in every
    blast run (GUI-10 shots). That is hard to read at a glance.
  - **Missing units.** The live-gauge `Z` header (`run_gauges.py:573`), the Setup
    hover readout and the Derived card's `Z 2.99` carry no unit.
- Fix:
  - Map the Field's Impulse unit to `kPa·ms` on screen only, as the table does. The
    exports stay unchanged.
  - Show `= 12.0 ms` beside End time.
  - Show P max in MPa from 10 MPa on (`203.8 MPa`). U4 pins the readout strings, so
    this is a layout pin the owner may release.
  - Add the `m/kg^1/3` unit as tooltips.

**UXR-16. The 0-D form still swaps typed zeros and wrong-count triplets for defaults.**
These are UX-9 and UX-10, open.
- Where: Setup 0-D.
  - `models/fields.py:531-532` (`Discharge coefficient` 0 → 0.8), `:548`
    (`Wall temperature` 0 → 300 K), `:517-518` (Cohorts, Samples), and `:559`
    (Collapse rotation).
  - `models/fields.py:100-118`: `parse_csv` returns blank for `3,4` in `Room, outer`.
- What the user experiences: the form shows 0 and the report uses 0.8. A two-number
  room size gives no red border.
- Fix: as `UX_REVIEW.md` §3 findings 9-10. Blank takes the default; an explicit 0 or
  a wrong count is a field error that names the field. This touches `models/` (the
  Tk gate).

**UXR-17. The properties column's text is about 17 px, larger than the board, so captions wrap and combos clip.**
- Where: Setup and Chain properties. `theme.py:256` (`QWidget { font-size: 13pt }`)
  is the D6 rule that was never swept.
- What the user experiences (the GUI-10 shots):
  - `Animation` / `format` and `Every [s]` / `(simulated time)` wrap onto two lines;
  - the Video colours box shows `fixed (whole vid`;
  - the tree, the strip and the dock use the board's 12.5-14 px, so the column looks
    as if it came from another app.
- Fix: a `QFrame#setupprops QLabel, QLineEdit, QComboBox { font-size: 13px; }` rule,
  plus `#stageprops` for the Chain, then re-run the parity sweep (D19 widths).

### Low

**UXR-18. Plots zoom with the mouse wheel but have no visible way back.**
This is UX-14, the part that is left.
- Where: `results_gauges.py:255-256`, `results_fields.py:232-233` and
  `pg_plots.py:422-423` (the menu is disabled and the auto-range button hidden).
- What the user experiences: an accidental wheel notch on the Gauges plot stays until
  another result is selected. Setup has a Fit button; Results and Run do not.
- Fix: the same `fit` tool button in each plot header, or `autoRange()` on a
  double-click.

**UXR-19. Stale or misleading copy.**
- `run_panel.py:487`: the folded card says `Exec 1 … 1000` beside buttons now named
  `+1 … +1000` (D49).
- The note `When the run ends, its full traces … open in 03 Results → Gauges` stays
  after the run has ended (GUI-10 finished shot). It should become a link.
- A gauge the wave never reached still says `waiting` after the end. D71's
  suggestion, `no arrival` in `faint`, is a one-line change in `run_gauges.py`.
- The stop reason quotes `p_edge = 1.015e+05` in Pa on a kPa screen. It is verbatim
  by design (D66), so the fix is in the solver's text, not the GUI.

**UXR-20. A dimension clicked away from Setup changes Setup out of sight.**
- Where: `app.py:121`. On Results, Run or Chain, clicking `3D` in the top bar
  switches 01 Setup's form and nothing else visible. It can look like a filter on
  the results list.
- Fix: navigate to 01 Setup when the dimension changes from another screen.

**UXR-21. Status-line messages vanish in 12 s, and their history lives only on the Run dock.**
- Where: `app.py:1416-1438`. An export failure seen on Results disappears. The
  Messages tab is two screens away.
- Fix: make the status label clickable, opening 02 Run · Messages. Keep `error`-level
  messages until clicked (the rest of UX-18).

**UXR-22. The drain loop can re-enter itself through a modal.**
- Where: `run_controller.py:343-348, 366-371`. `show_error('Model folder' / 'Run
  failed')` opens a nested event loop inside `_dispatch`, and the 50 ms timer then
  calls `_drain` again before the first call returns.
- What the user experiences: nothing visible today. `done` and `on_running(False)`
  can run behind an open error dialog, before the user has read it. It is a latent
  ordering hazard.
- Fix: a `_draining` guard, or post the dialog with `QTimer.singleShot(0, …)`.

**UXR-23. Error dialogs have no parent.**
This is `UX_REVIEW.md` finding 20.
- Where: `app.py:62`, `run_controller.py:84` and `dialogs.py:20-21`. They can open
  on another monitor or behind the window.
- Fix: pass `self.window()`.

**UXR-24. A restored window position can land off-screen.**
This is `UX_REVIEW.md` finding 21, and the clamp half of UX-17.
- Where: `app.py:515-524` clamps only to ≥ 0.
- Fix: `saveGeometry()` / `restoreGeometry()`, or check against
  `QGuiApplication.screens()`.

**UXR-25. Fixed heights the QSS may beat (D41 / F21 mechanism).**
- Measured fine in the GUI-10 screenshots: the top-bar pills (40), the case button
  and the chip (32).
- Not pinned in QSS and not measured:
  - the Banner's action button (`components.py:532`, `setFixedHeight(36)`, no object
    name, so the generic `QPushButton { padding: 6px 14px; min-height: 24px }`
    applies);
  - the PointList +/- buttons (`fieldform.py:266-270` → `widgets.button(height=30)`).
- Fix: give each an object name and a `min-height = max-height` QSS pin, as D179
  did. Measure them with the `--real` probe of `test_ui_setup_tree.py`.

**UXR-26. The 3D controls on a 1D/2D run are greyed, not hidden.**
- Where: `run_panel.py:1036, 1328`. The square 3D button is disabled for every
  non-3D run, and the `3D view` segment leads to a placeholder.
- What the user experiences: this is a dimension (not solver) case of hide, never
  grey. The board draws the segment for its 2D sample, so the segment stays.
- Fix: hide the 3D button when the running case is not 3D (`enable_view3d(False)` →
  `setVisible(False)`).

### Threading and lifetimes: what was checked

| Thread (file:line) | What it touches | Verdict |
|---|---|---|
| The solver worker (`run_controller.py`) | It posts to a queue that a `QTimer` drains | OK |
| HD 1.3 (`app.py:933-950`) | It posts through `bridge` | OK, but see UXR-4 for posting after close |
| The hardware probe (`app.py:441-453`) | It posts through `bridge` | OK |
| Export (`exports.py:111-120`) | `run_export` catches everything; `on_done` and `on_error` are posted | OK |
| This frame .png (`results_field.py:1150-1170`) | It builds the figure from a spec read on the GUI thread, logs through the bridge, and posts `set_busy` | OK. If `_bridge` is None, the busy strip never clears, but only a standalone panel has no bridge. |
| Foam load (`results_panel.py:1035-1055`) | `add_result` is posted | OK |
| The runs browser (`run_browser.py:129-141, 271-275`) | It posts | OK. If `_deleter` raises, `_busy` stays True; `env.delete_runs` catches, so this is latent. |
| `crashlog` thread hook | A **QMessageBox on the raising thread** | Not OK: UXR-4 |

Object lifetimes: rebuilt rows are unparented and `deleteLater`'d (Checks rows,
gauge rows, method rows, chain strips). F14's viewport guard is in place. No
per-run widget growth was found.

---

## 4. Status of the earlier findings UX-1 … UX-19

- **UX-1** (HD 1.3 on the GUI thread): **Resolved.** It runs once, on a worker, with
  an indeterminate bar (`app.py:901-980`). There is no Cancel (documented). The flow
  gaps are UXR-8.
- **UX-2** (a write failure loses the result): **Resolved.** `solvers/jobs.py:42-48`
  logs `[warn] could not write`, pinned by the `*_char_write_failure` tests.
- **UX-3** (native Material becomes TNT): **Open.** See UXR-3. The owner's D138
  answer now points to hiding the row.
- **UX-4** (closing during a run): **Open.** See UXR-1.
- **UX-5** (start-up cleanup): **Resolved.** It is off by default and warns only
  (2026-09-27). There is no GUI switch, which is acceptable for one user.
- **UX-6** (outputs overwrite the working directory): **Resolved** by OUT-1. The
  model folder asks before overwriting.
- **UX-7** (Esc stops a run): **Resolved.** Stop is Shift+Esc, it asks after 30 s,
  and the shortcuts are in the tooltips and the status bar.
- **UX-8** (Save / Save as / dirty / recent): **Mostly resolved.** Open: UXR-1 (no
  prompt on close, Open or Recent) and UXR-5 (Save as error, start folder). There is
  no "Saved <path>" line, but the `●` clearing is visible feedback.
- **UX-9** (0-D zeros become defaults): **Open.** See UXR-16.
- **UX-10** (0-D triplet with the wrong count): **Open.** See UXR-16.
- **UX-11** (units): **Partly resolved.**
  - Done: the visible 0-D pressures are all MPa now (the kPa Ultimate resistance is
    on the hidden Structure card), and impulse is kPa·ms in the Gauges table.
  - Open: End time in s, the Field impulse in Pa·s, units in captions rather than
    suffixes (D15). See UXR-15.
- **UX-12** (HD 1.3 results bypass Results): **Partly resolved.** The report and the
  loads land in the model folder and the log lists them. Still open: nothing opens,
  there is no Results entry, and the Run screen shows a blast view (UXR-8).
- **UX-13** (export busy / double start): **Resolved.** Busy strip, no second start
  of the same kind (D82, no percent).
- **UX-14** (plots cannot be zoomed, read or copied): **Mostly resolved.** The Field
  has a hover readout, the gauges have a readout and a pyqtgraph plot, and Copy
  table works. Zoom-reset is open (UXR-18).
- **UX-15** (results do not say how they were computed): **Resolved**, with gaps
  (UXR-10).
- **UX-16** (Chain validates late, cannot load stages, overwrites): **Resolved.**
  Live checks, Copy / Load per stage, and the model folder asks. Learnability is
  UXR-12.
- **UX-17** (minimum size 1100 × 720): **Kept by the approved plan** (§4; GUI-10 made
  every screen fit it). The geometry clamp is open (UXR-24).
- **UX-18** (messages short-lived, log wiped): **Resolved.** Messages, Earlier runs,
  Copy and Save log. Still open: errors still clear in 12 s and the history is only
  on Run (UXR-21).
- **UX-19** (minimal progress): **Resolved.** `% · elapsed · about X left`, plus the
  title. D75 (an ETA that is not time-like) stays the owner's call.

---

## 5. The redesign against the boards: where the build departs

Only the departures that cost the user something are listed here. Departures that
an approved D-row covers are not listed.

1. **Setup, Gauges properties.** The board has **Paste rows**; the build has none
   (UXR-13).
2. **Setup, Threat properties.** The board has `Charge mass [kg]` with a suffix and
   `Burst point r 0 · axis`. The build has `Charge [kg TNT]` and a greyed
   `Burst r [m]` box. The suffix is deferred by D15; the caption is UXR-11.
3. **Setup preview, 2D axisymmetric.** The board labels the axes `r [m]` and
   `z [m]`; the build labels them `r [m]` and `y [m]` (UXR-11).
4. **Chain, stage previews.** The board has the hand-off annotations and a 3D
   schematic. The build has the plain preview, and text only for 3D (UXR-12; D134
   covers only the 3D viewer).
5. **Run, idle note on the gauge column.** It is kept after the run ends (UXR-19).
6. **Results, method card.** The board's `Mesh 25 mm · 6.59 at charge` becomes
   `cell 12.4352 mm` (UXR-10), and the board's `Solver blastFoam 6.2.0` has no
   version (D77, an OUT-track item).

A flow that stalls: **0-D Run** (UXR-8). A flow that surprises: **F5 on Chain**
(UXR-7).

---

## 6. Hide, never grey: the audit

Mode-driven hiding is consistent:
- the chip and the WSL line at 0-D (`app.py:886-899`);
- the MPI and Memory tiles in native mode (D31);
- `Load a run…` and VTK in native mode (`results_panel.py:890-891`);
- the Detonation and Afterburn method rows for native results (D78);
- the Step through, Live view and 3D button, and the Time / Step / P max tiles at
  0-D (`run_panel.py:973-985`);
- Initialise at 0-D (`setup_strip.py:290, 297`);
- the Gauges dock tab at 0-D (`setup_panel.py:430`).

Where the rule is broken:
- the Material row in native mode (UXR-3, shown but ignored: worse than greyed);
- the Run view toolbar and view at 0-D (UXR-8 / F12);
- the 3D button on 1D/2D runs (UXR-26).

The greyed rows that are deliberate are listed at the top of this file.

---

## 7. Proposed screen layout (01 Setup, the main analysis screen)

The approved three-column layout stays. These additions fit inside it:

```
+------------------------------------------------------------------------------+
| BLASTLAB  01 Setup ✓ > 02 Run > 03 Results | Chain   wall_A ● | chip | 2D   |
+---------------+--------------------------------------+-----------------------+
| MODEL · 2D AX | CHARGE  CELLS  MPI  MEMORY  Z  [Run F5]| PROPERTIES            |
| 01 Threat   ✓ |                                       | 05 Gauges             |
| 02 Domain   ✗ |<- UXR-6: validation error mapped here | [r] [z]  [+] [-]      |
| 03 Bound.   ✓ | model view (r [m] / z [m] axes,       | [Paste rows…] UXR-13  |
| 04 Struct.  ✓ |  UXR-11)                              | table r | z (not x y) |
| 05 Gauges   ! |<- UXR-2: G3 inside Wall 1             | End the run at a gauge|
|   G1 2.95,0.5 |                                       |  (trigger follows a   |
|   G2 2.95,1.5 | Gauges | Checks 1·1·4 | Log           |   deleted row, UXR-9) |
| + Gauge +Obst | ✗ AMR max cells… → click opens 02     |                       |
| [1 error]     | ! G3 is inside Wall 1 → click opens 05|                       |
+---------------+--------------------------------------+-----------------------+
| WSL ready · … | wall_A.json has unsaved changes | (click: Messages) | F5 run |
+------------------------------------------------------------------------------+
```

- Checks rows are links to their node, and the tree marks agree with the pill.
- Properties use the board's 13 px body text (UXR-17), so most captions fit on one
  line in 340 px.
- On Chain, the same layout gains the hand-off overlay on the preview (UXR-12).

---

## 8. Quick wins: best value for least effort

1. **F5 on the Chain screen runs the chain** (UXR-7). One line in
   `app.py:507-511`.
2. **Ask before discarding** (UXR-1). One helper of about 30 lines, called from
   `closeEvent`, `_open_case` and Recent. It mirrors the existing question in
   `_load_case_from_result`.
3. **Method card units and precision** (UXR-10 points 1-2). Two format strings in
   `results_method.py:135, 145`.
4. **The 0-D run goes to 02 Run, and Setup's Run greys while it works** (UXR-8
   points 1-2), plus GUI-11 (d)'s toolbar hide. About 6 lines in `app.py` and
   `run_panel.py`.
5. **Axisymmetric labels** (UXR-11): the `r z` point-list headers through the
   existing hook, `Height H`, and the preview's `z [m]`. These are caption-only
   changes; every value is unchanged.

Next after these: UXR-2 (the dropped-gauge warning and entered numbers), UXR-4 (the
crash handler off the GUI thread) and UXR-3 (hide Material in native mode). Each is
small, and all three are High.
