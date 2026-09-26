# blastlab - UX review of the Qt GUI

Reviewed: 2026-09-24, branch `hd1-band-cost`, read-only. The GUI was not launched,
because building it can start the run-corpus auto-cleanup (CLAUDE.md 8.2). All flows
below come from reading the code, and each finding cites the file and line it rests on.

Scope: the PySide6 GUI in `blastlab/ui/`. The Tkinter GUI in `blastlab/gui/` is the
permanent fallback behind `--tk` (CLAUDE.md 9). It is in scope for nothing here
except where a shared module (`core/`, `solvers/`, `output/`) affects both.

These are documented, intentional behaviours and are **not** reported as defects:
- The app-wide solver switch hides, and never greys out, controls that do not apply.
- The 3D viewer colours pressure logarithmically by default.
- Displayed impulse is net overpressure impulse, including the negative phase.
- Near-field arrival times differ between native and blastFoam (activation model).

No recommendation here changes a computed number or a file format. The one place
where a fix could change numbers (finding 3) is marked as an owner decision.

---

## 1. Framework and screens

Framework: **PySide6** (Qt 6). Entry point `python -m blastlab` -> `blastlab/ui/app.py:main`.
Plots are pyqtgraph on screen, plus matplotlib `Figure` objects (never `pyplot`) for
figures shared with exports. The 3D view is a pyvista child process.

| Screen | Where | Purpose |
|---|---|---|
| Main window + sidebar | `ui/app.py` | Navigation (Setup, Run, Results, Chain), Open/Save case, solver switch (native or blastFoam), WSL status, dark mode, status line |
| Setup tab | `ui/setup_panel.py`, `case_form.py`, `fieldform.py`, `setup_spec.py` | Dimension selector 0D/1D/2D/3D, the case form, the validation report, the live model preview |
| Run tab | `ui/run_panel.py`, `run_controller.py` | Start, stop, stepped execution, progress chips, log, live slice, live gauges, embedded 3D view |
| Results tab | `ui/results_panel.py`, `results_fields.py`, `results_gauges.py`, `results_anim.py`, `exports.py` | Result picker, Fields/Gauges/Animation/3D views, eight exports, a custom title line |
| Chain tab | `ui/chain_panel.py` | 1D -> 2D -> 3D staged run with automatic profile hand-off |
| blastFoam runs dialog | `ui/run_browser.py` | List, load, resume and delete WSL run directories |
| 3D viewer | `viz3d/viewer.py` (child process), `ui/view3d_host.py` | Embedded pyvista scene |

---

## 2. User flows (reconstructed)

### 2.1 Start-up
1. `crashlog.install()`, then `QApplication` and the theme (default dark) (`app.py:748-761`).
2. `MainWindow` restores the solver mode, geometry and refresh policy from `core/settings`.
   Minimum size is 1100 x 720 (`app.py:50`).
3. **A WSL run-directory cleanup starts at once on a daemon thread** (`app.py:131`,
   `solvers/foam/env.py:824-878`). The default policy is 20 GB, 14 days, keep 3
   (`core/settings.py:29`). It asks for no confirmation. Its one log line goes to the
   Run-tab log.
4. The window opens on Setup, 2D. In blastFoam mode the sidebar shows
   "WSL: checking blastFoam..." and then "ready · N cores · M GB VM".

### 2.2 Setup tab: inputs in the order a user meets them
Header: "Case Setup" and the segmented control `0D | 1D | 2D | 3D` (default 2D). The form
has two columns of cards, or one column when the viewport is narrower than about 628 px.
The preview card sits on the right. Every numeric field is a `QLineEdit`. Units appear
inside the caption text (`[m]`, `[kg TNT]`, `[s]`).

**1D** (col 0 first, then col 1)
- Domain: Domain radius [m] 10; Cell size [m] 0.001
- Charge: Charge [kg TNT] 1.0; Material (choice, TNT). **Shown in both modes.**
- Numerics: EOS idealGas/JWL *(native)*; Order 1 (Godunov)/2 (MUSCL) *(native)*;
  Detonation linear/programmedIgnition/none *(blastFoam)*; Afterburn none/miller
  *(blastFoam)*; Snapshots 5; CFL 0.5; End time [s] (0 = auto) 0
- Boundaries: Outer boundary (r = R) terminate
- Gauge radii [m]: point list (r)
- Outputs: Gauge TSV `gauges.txt`; Profile out (.txt) `blast_profile.txt`

**2D**
- Domain: Geometry axisymmetric/planar; Lx [m] / "Radius R [m]" 4; Ly [m] / "Height Z [m]" 4; Cell size [m] 0.025
- Initialization: Initialize from charge/profile1d; Charge [kg TNT] 1.0 (becomes [kg TNT/m] when planar);
  Material TNT; Profile file (picker); Burst x/r [m] 0 (disabled and pinned to 0 in
  axisymmetric); Burst y/z [m] 2.0
- Numerics: as for 1D, plus Charge refinement global/zone *(blastFoam, AMR off)* and MPI ranks (0 = auto) *(blastFoam)*
- Dynamic refinement (AMR) *(blastFoam)*: AMR levels 0..max; while above 0 it also shows
  Error estimator Lohner, Refine above 0.4, Unrefine below 0.2, Refine every [steps] 2,
  Buffer layers 2, Max cells 0, Display level auto
- Boundaries (2 x 2 grid): x_lo reflect (locked in axisymmetric), x_hi terminate, y_lo reflect, y_hi transmit
- Col 1: Gauges [m] (x y); Obstacles [m] (x0 x1 y0 y1); Refinement zones [m, level] *(blastFoam)*;
  Detonation points [m] *(blastFoam)*
- Outputs: Gauge TSV `gauges_2d.txt`; Animation `blast_2d_animation.mp4|.gif`; Video colours
  (run / frame / manual; manual shows Video min/max [kPa] 0/500); Record replay frames on;
  Mesh overlay off; Profile out (.npz) blank
- Trigger gauge: Gauge number (blank = off); On arrival terminate/...; Remap file

**3D**: as for 2D with Lx/Ly/Lz 1.5 m, Charge 25 kg, Charge resolution resolve/smear *(native)*,
Burst x/y/z 0.75, Live slice normal y, Slice position [m] (blank = burst), Extra charges [m, kg] *(blastFoam)*,
six boundary sides, and no Remap file.

**0D (HD 1.3 deflagration assessment)** (`setup_spec.py:230-334`)
- Col 0: Material (Propellant; Vieille n, Vieille a, Burn rate at 1 atm [mm/s], Web [mm],
  Extinction limit [MPa], Secondary heat [MJ/kg], all blank = table; "overrides are measured");
  Charge and chamber (Charge [kg] 5, Chamber volume [m3] 1, Vent area [m2] 0.02,
  Discharge coefficient 0.8, Igniter pressure [MPa] 0, Air in the room [MPa] 0.101325,
  Assess both); Ignition (How it catches, Cohorts 20, Time to light it all [s] 30,
  Spread through a area. The three spread rows are disabled for "uniform".);
  Vent stage (blastFoam) (Room outer [m] "Lx,Ly,Lz" text, Room corner, Wall thickness [m] 0.2,
  Opening in, Opening [m] "a0,a1,b0,b1" text, How it opens, Panel bursts at [MPa] 0.3,
  CFD domain [m] text, Base cell [m] 0.1, CFD window [s] 0.02, Snapshots 20); Vent gauges [m]
- Col 1: Run (End time [s] 60, Samples 1000); Heat (Wall heat transfer [W/m2K] 200,
  Wall area [m2] 6, Wall temperature [K] 300); Radiation standoffs [m]; Structure (Span [m] 3,
  Mass [kg/m2] 480, Ultimate resistance [kPa] 400, Elastic stiffness [MPa/m] 30,
  Supports simple, Collapse rotation [deg] 12); Outputs (Run name, Report file `hd13_report.html`)

**Validation flow.** Every keystroke restarts a 300 ms debounce (`app.py:58-61`).
`get_case()` parses every field and collects *every* parse error. Bad fields get a red
border (`fieldform.py:538-548`). `validate_case()` adds range and consistency errors,
warnings and notes, plus a cell-count line. These appear in a fixed-height 132 px
scrolling report card (`setup_panel.py:25`). The Run tab mirrors "N errors - see Setup"
and disables Run and Initialise (`run_panel.py:411-426`). Point lists refuse a bad row
inline, with a red hint.

**Actions.** Sidebar: Open case... (Ctrl+O), Save case... (Ctrl+S). Global shortcuts:
F5 runs, Esc stops (`app.py:348-352`). There is no menu bar.

### 2.3 Run tab
- Controls: Run (primary), Stop (turns danger-red while running), 3D View, Name; an 8 px
  progress bar with no text; a PAUSED label; the validation label; chips for step,
  t [ms], dt [s], p max [kPa], and cells (AMR only).
- Stepped row: Initialise Model, Exec 1/10/100/1000, END, Interrupt; "Refresh every"
  [value] seconds/steps (red border when unusable).
- Body splitter: Log (monospace, cleared at every run start, `run_panel.py:374`) | live view
  (Live slice / Gauges / 3D view; Show mesh; Auto; Min, Max kPa).
- **Threading:** `SolverWorker` is a `threading.Thread`. Messages go through a `queue.Queue`
  drained by a 50 ms `QTimer` (`run_controller.py:96-98, 346-381`). Frames are latest-wins.
  Other threads post through `ThreadBridge` (queued signal). No widget is touched from a worker.
- **Error path:** the worker posts `('error', traceback)`. The drain shows a
  `QMessageBox.critical` "Run failed" with the headline plus "See the run log". Setup inputs
  are untouched.
- **0D path:** `_run_hd13` runs inline on the GUI thread (`app.py:532-561`). See finding 1.

### 2.4 Results tab
- Top card: Result picker, Remove, 3D Viewer, Foam runs... (blastFoam only). Export row:
  Profile, Animation, VTK (blastFoam only), Summary CSV, Gauges TSV, Field CSV, Report, PNGs.
  Disabled buttons carry a "why not" tooltip. Title line (optional).
- Views: **Fields**: Snapshot, Field, Show mesh, one pyqtgraph map with a colour bar,
  axis labels and title (context menu disabled). **Gauges**: a matplotlib trace figure
  with no toolbar, above a `QTableWidget` summary (peak kPa, arrival/t_peak/pos. phase ms,
  pos/net impulse Pa·s, phase ended), showing at most 4 rows before it scrolls.
  **Animation**: Play, slider, speed, colour scale. **3D**: embedded viewer.
- Exports: the file dialog runs on the GUI thread and writing happens on a daemon thread
  (`exports.py:298-313`). Success and failure go to the log and the status line
  (red if the text contains "fail" or "error"). Only VTK failures raise a dialog.
- Results live in memory for the session. Nothing asks before they are discarded.

### 2.5 Chain tab
Workspace path (default `~/Documents/blastlab/chain_workspace`), stage checkboxes
1D/2D/3D, Run chain. Per stage: a solver override and a full `CaseForm`. **The forms have
no `on_change`**, so they are validated only when Run chain is pressed (`chain_panel.py:138`).
On Run chain the panel writes `stageN_case.json` and the profiles into the workspace,
overwriting any earlier ones, and launches through the normal RunController.

### 2.6 blastFoam runs dialog
A table of name, dims, size, started and state. Buttons: Browse..., Refresh, Resume
(stopped runs only), Load (also double-click), Delete (danger, with a confirmation that
includes the size), Close. Listing and sizing run in a thread.

### 2.7 Case files
Open: `QFileDialog` -> `load_case`. JSON, missing-field, OS and other errors each get a
specific message. On success it sets the solver mode and dimension, fills the form and
pre-fills the run name. Save: `get_case()` (a parse error gives a dialog) -> save dialog
-> `save_case`. No confirmation, no default name or folder, no title change
(`app.py:446-455`).

---

## 3. Findings

Severity rule: threading and data-loss issues are always **high**. The review counts
27 findings: 6 high, 12 medium and 9 low.

What already works well, and should be kept: threading on the Run path (worker, queue,
`QTimer` drain, `ThreadBridge`); live validation that reports every bad field at once
with red borders; the Run button gated by validation; disabled export buttons that say
why; the reasoned tab order on the Run tab; and Qt 6 default high-DPI handling
(no deprecated attributes set).

### High

**1. The HD 1.3 assessment runs on the GUI thread, twice, with no progress or cancel.**
- Screen: Setup 0D -> Run / F5. `ui/app.py:532-561`; `output/cli_hd13.py:58-68`; `core/assessment.py:571-630`.
- What the user sees: the window freezes ("Not responding") after Run. `_run_hd13`
  calls `run_hd13(case)` "to fail before touching disk", then `run_and_report()`, which
  reloads the case and runs the whole assessment again. The docstring says the run takes
  "well under a second". The spec comment says the default 20 cohorts cost about 14 s
  (`setup_spec.py:279-280`), and `run()` also does the cohort-doubling check and the
  sensitivity band. So the freeze is likely tens of seconds.
- Fix: run the assessment once, on a `QRunnable` in `QThreadPool` or on the existing
  worker, and post the bundle back through `ThreadBridge`. Write the report from that
  same bundle, so `run_and_report` gets a variant that accepts a finished `out`. Show an
  indeterminate `QProgressBar` or the Run-tab bar, disable Run while it works, and offer
  Cancel if the band is running. The report file stays byte-identical.

**2. A finished solve is thrown away if writing one of its output files fails.**
- Screen: Run. `solvers/jobs.py:48-72`; `solvers/worker.py:314-329`.
- What the user sees: the stage callable writes the gauge TSV, the animation and the
  profile *inside* `solve()`. If any of these raises (ffmpeg problem, file open in a
  video player, OneDrive lock, bad path), the worker takes the `except Exception`
  branch. It posts `error`, and `('result', k, res)` is never sent. After a 40-minute
  native 3D run the user gets "Run failed" and nothing in Results, even though the
  solution was complete.
- Fix: in `solve_stage`, put each output write in its own try/except. On failure, log
  `[warn] could not write <file>: <reason>` and still return `res`, so the result arrives
  and the user can export again from Results. The file formats do not change.

**3. In native mode the visible Material choice is silently replaced by TNT.**
- Screen: Setup 1D/2D/3D, native mode. `ui/case_form.py:468` and `:506`
  (`material=v['material'].get() if foam else 'TNT'`); `ui/setup_spec.py:371-387`
  (the row has no scope, and a comment says it shows in both modes because the native
  solvers share the table, N11/T46); `core/case.py:548-566`.
- What the user sees: they choose ANFO in native mode. The preview, validation, run,
  result title and saved JSON all say TNT. The same form in blastFoam mode honours the
  choice. A visible input is overridden with no message. This breaks the rule the form
  states for itself: "what you see is what runs and saves".
- Fix: this needs an owner decision, because one option changes numbers. Either
  (a) pass the selected material in native mode too, which the validator and N11/T46
  already support, or (b) give the row `scope='blastfoam'` so native mode hides it,
  following the hide-don't-grey rule. Until then, add a validation note in native mode:
  "Material: native runs use TNT". See also Suspected engineering issue E2.

**4. Closing the window during a run kills the run without asking, and can freeze for 10 s.**
- Screen: Main window. `ui/app.py:731-745`; `ui/run_controller.py:384-388`.
- What the user sees: clicking the window's X during an hours-long solve stops the
  worker, then `join(timeout=10)` blocks the GUI thread. Unexported in-memory results
  of earlier runs are also lost without a prompt.
- Fix: in `closeEvent`, if `self.ctrl.running`, ask "A run is in progress (step N,
  t = X ms). Stop it and quit?" and call `event.ignore()` on No. For blastFoam, say
  that the run can be resumed from the runs dialog. If results exist that were not
  exported, say so as well. Put the join behind a small modal "Stopping solver..." that
  keeps the event loop alive, rather than a bare blocking join.

**5. The start-up cleanup deletes WSL run directories without confirmation, and its notice is easy to miss.**
- Screen: start-up (all tabs). `ui/app.py:129-132`; `solvers/foam/env.py:824-878`; `core/settings.py:29`.
- What the user sees: nothing. Runs older than 14 days, or over 20 GB, are removed
  while the Setup tab is showing. The one log line goes to the Run-tab log, and the
  next Run clears that log (`run_panel.py:374`). The policy cannot be seen or changed
  anywhere in the GUI. CLAUDE.md 8.2 records a real loss of 44 GB of runs, including
  the one under investigation.
- Fix: keep the sweep off the GUI thread, but make it *propose* rather than act. Compute
  the victims, then post a non-modal banner on the status line: "Cleanup would remove
  N runs (X GB): [Review] [Remove] [Not now]". Review opens the runs dialog with those
  rows pre-selected. Add the three thresholds and the on/off switch to a small Settings
  dialog. Always send the outcome to the status line, not only to the log.

**6. Every run silently overwrites its output files in the process working directory.**
- Screen: Setup Outputs -> Run. `ui/setup_spec.py:169-192` (defaults `gauges_2d.txt`,
  `blast_2d_animation.mp4`, `blast_profile.txt`); `solvers/jobs.py:56-71`.
- What the user sees: the default output names are relative, so they resolve against
  the working directory. For the `.bat` launcher that is the install folder, which is
  the OneDrive repo (`chain_panel.py:48-49` says so). Run 2 overwrites run 1's gauges
  and video with no warning. The run name typed on the Run tab prefixes the *export*
  file names but not these automatic outputs.
- Fix: resolve relative output names against a per-run folder, for example
  `Documents/blastlab/runs/<run name or timestamp>/`, and say the full path in the
  Outputs card ("writes to ...") and in the "Result ready" status. If the target
  exists, add a suffix or ask. The file contents do not change.

### Medium

**7. Esc stops the run from anywhere without confirmation, and no shortcut is discoverable.**
- `ui/app.py:348-352`. Esc is a window-wide `QShortcut`. Pressing Esc to leave a text
  field on any tab stops a live solve. F5, Ctrl+O and Ctrl+S appear in no menu or tooltip.
- Fix: bind stop to Shift+Esc or Ctrl+Break, or ask for confirmation when the run has
  gone past about 30 s. Put the shortcuts in the button tooltips ("Run (F5)",
  "Save case (Ctrl+S)"). Consider a minimal File / Run / Help menu bar.

**8. Case files have no Save / Save As split, no dirty state, no recent files and no feedback.**
- `ui/app.py:397-455`; `ui/dialogs.py:30-50`.
- What the user sees: Ctrl+S always opens a dialog in the working directory with an
  empty name. Nothing confirms that a save happened. The title never shows the case
  name or a `*` for unsaved changes. Closing with unsaved edits gives no prompt. There
  is no recent-files list. A failure inside `save_case` (for example a OneDrive lock)
  is not caught locally and ends up in the crash handler.
- Fix: keep `_case_path`. Ctrl+S saves in place when a path exists, and Ctrl+Shift+S is
  Save As, starting from the last folder with the run name as the default file name.
  Use `setWindowTitle(f'{name}[*] - blastlab')` with `setWindowModified` driven by the
  form's change callback. On save, show "Saved <path>" in the status line and catch
  `OSError` in a dialog. Keep a list of 8 recent files in `core/settings`, and show them
  under the Open button as a `QMenu`.

**9. The 0D form silently replaces some typed zeros with defaults.**
- `ui/case_form.py:249-303`. The `num(...) or default` pattern turns an explicit `0` in
  Discharge coefficient into 0.8, Wall temperature into 300 K, Collapse rotation into
  12 deg, Cohorts into 1 and Samples into 1000. The form shows the user's 0, while the
  run and the report use the substitute.
- Fix: tell blank apart from zero, as `p0_chamber` already does (`blank=P_AIR`, no `or`).
  Blank takes the default. An explicit non-positive value becomes a field error
  ("Discharge coefficient must be > 0"), shown with a red border.

**10. A 0D coordinate triplet with the wrong count is treated as blank.**
- `ui/case_form.py:192-210`, used for Room outer, Room corner, Opening and CFD domain.
- What the user sees: "3,4" in Room outer gives no red border. If the other geometry is
  blank, the vent stage is silently left out. If it is filled, the message is the generic
  "half filled in" and does not name the field that was mistyped.
- Fix: when the text is not blank but does not parse as n numbers, add an error such as
  "Room outer: expected 3 numbers Lx,Ly,Lz, got 2" and mark the field. Better still, use
  three numeric boxes, or a PointList with a single row.

**11. Units are inconsistent within and across screens.**
- 0D (`setup_spec.py:240-305`): pressure is entered in both kPa (Ultimate resistance)
  and MPa (Igniter, Extinction, Air in the room = 0.101325, Burst), next to MPa/m,
  mm, mm/s and MJ/kg. Blast forms: End time is typed in **s** (`setup_spec.py:98`), while
  every readout, chip, plot and table on Run and Results is in **ms**. Ambient air in MPa
  (0.101325) is easy to mistype by 10x.
- Fix, without changing stored values or the JSON: use one pressure prefix per screen,
  preferably kPa for the chamber and structure pressures, converting in `_HD13_UNITS`
  exactly as now. Offer End time in ms, or show the ms equivalent next to it
  ("= 12.0 ms"). Put units in a separate suffix label or `QLineEdit` trailing action
  rather than in the wrapped caption, so they line up in one column.

**12. HD 1.3 results bypass the Results tab, and the report lands in the working directory.**
- `ui/app.py:547-561`.
- What the user sees: the only output is an HTML file, by default `hd13_report.html`
  relative to the working directory, overwritten on every run. It is not opened. The
  status line shows the path for 12 s. Post-run warnings, such as "peak moved X % when
  cohorts doubled", exist only inside the report.
- Fix: resolve the default path next to the saved case, or in the per-run folder
  (finding 6), open it with `os.startfile` as the blast Report export already does, and
  copy the run's warnings into the Setup report card. Optionally, add an HD 1.3 entry to
  the Results picker that shows the key numbers: peak pressure, verdict, SDOF rotation
  and the band.

**13. Exports show no busy state and can be started twice.**
- `ui/exports.py:298-313`; `ui/results_panel.py:349-352`.
- What the user sees: after the file dialog nothing appears to happen until "Saved"
  shows up in the status line, which can take minutes for an MP4 of a 3D run. The button
  stays enabled, so a second click starts a second thread writing the same file. Failures
  other than VTK appear only in the status line, which clears after 12 s.
- Fix: disable the clicked button, show a spinner or "Writing animation..." with a
  busy `QProgressBar` in the status line, and re-enable when the thread posts back through
  `ThreadBridge`. Report failures through `dialogs.show_error` with the path and the reason.

**14. The key engineering plots cannot be zoomed, read off or copied.**
- `ui/results_gauges.py:87` (`MplCanvas()`, no toolbar); `ui/results_fields.py:174`,
  `ui/pg_plots.py:384` (`setMenuEnabled(False)`); `ui/results_gauges.py:90`
  (a `QTableWidget` without copy).
- What the user sees: an engineer cannot zoom into the positive phase of a gauge trace,
  read a value at the cursor, or copy the peak/impulse table into a calculation sheet.
  Field maps give no value under the cursor.
- Fix: `MplCanvas(toolbar=True)` on the Gauges view; the toolbar exists in
  `mpl_canvas.py:66-68`. On pyqtgraph maps, add a hover readout (x, y, value + unit) in
  the title or a label. Add Ctrl+C / "Copy table" on the summary table, as tab-separated
  text with headers.

**15. Results do not say how they were computed.**
- `ui/results_fields.py:129-131`; `output/plots.py:49-57`; Results top card.
- What the user sees: the title says "overpressure - 5 kg TNT". Nothing on the Results
  tab shows the solver, material, afterburn, activation model, cell size, AMR, or whether
  the run stopped early. The result's Setup case cannot be recalled.
- Fix: add a one-line "method" strip under the picker, built from `res.meta`, such as
  "blastFoam · ANFO · afterburn miller (uncalibrated) · dx 25 mm, AMR 2 · stopped at
  t = 12 ms". Add a "Show case" or "Load into Setup" action for the result's case. These
  are display-only and change no file.

**16. The Chain tab validates late, cannot load stage cases, and overwrites the workspace.**
- `ui/chain_panel.py:138` (no `on_change`); `:205` (`set_stage_case` is never wired to
  any control); `:322-324` (writes `stageN_case.json` and the profiles without checking).
- What the user sees: three forms are filled blind and every error arrives only on
  Run chain. A stage cannot be loaded from a saved case or copied from Setup. A second
  chain in the same workspace overwrites the first chain's cases and profiles.
- Fix: wire each stage form to the same debounced validator and report card that Setup
  uses. Add "Load case..." and "Copy from Setup" per stage, both calling `set_stage_case`.
  If the workspace already has stage files, offer a timestamped sub-folder or confirm the
  overwrite.

**17. The minimum window size exceeds a common laptop screen.**
- `ui/app.py:50` (`setMinimumSize(1100, 720)`); `:360` (the restore clamps to the same values).
- What the user sees: a 1920 x 1080 laptop at the Windows default of 150 % gives a work
  area of about 1280 x 690 logical pixels. The window cannot fit, so its bottom (the
  status line and the lower cards) sits under the taskbar.
- Fix: lower the minimum to about 1024 x 640, and rely on the existing single-column
  fallback and scroll areas. When restoring, clamp the geometry to
  `QScreen.availableGeometry()`.

**18. Messages are short-lived and have no history.**
- `ui/app.py:93-96, 706-713` (12 s status line, cut to 200 characters);
  `ui/run_panel.py:374` (log cleared at each run start); there is no log export.
- What the user sees: an export failure, a cleanup notice or a solver warning disappears
  before it is read. The previous run's log, which is the record of what the solver
  said, is wiped when the next run starts.
- Fix: keep errors on the status line until clicked. Clicking the status line opens a
  "Messages" panel with the session history. Add "Save log..." and "Copy" to the Log
  card. Keep the previous run's log reachable (one per result), or append a separator
  instead of clearing.

### Low

**19. The progress feedback is minimal.** `run_panel.py:81-88`. An 8 px bar with no
text, no elapsed time and no ETA. Fix: show "37 % · 4 min 12 s elapsed · ~7 min left"
next to the bar, and mirror it in the window title while minimised.

**20. Error dialogs have no parent.** `ui/app.py:44`, `ui/run_controller.py:81`,
`ui/dialogs.py:11-16`. `QMessageBox.critical(None, ...)` can open on another monitor or
behind the window. Fix: pass `self.window()` as the parent.

**21. Restored window position can land off-screen.** `ui/app.py:354-363`. A saved
position on a disconnected monitor is only clamped to be at least 0. Fix: use
`saveGeometry()` / `restoreGeometry()`, or check the position against
`QGuiApplication.screens()`.

**22. Point-list rows cannot be edited or pasted.** `ui/fieldform.py:108-224`. Fixing
one coordinate means removing the row and retyping it, and ten gauges cannot be pasted
from a spreadsheet. Fix: allow in-place editing (`Qt.ItemIsEditable`, validated on
commit) and accept multi-line paste into the entry.

**23. The 0D selector and the active solver are not self-explanatory on Setup.**
`ui/setup_panel.py:61`. "0D" gives no hint that it is the HD 1.3 deflagration
assessment. The solver mode, which decides which cards exist, is shown only in the
sidebar. Fix: add a tooltip, or the label "0D · HD 1.3", and a small "Solver: blastFoam"
badge in the Setup header next to the dimension selector.

**24. Numeric entry has no typing guard.** `ui/fieldform.py:498-502`. A plain `QLineEdit`
per numeric field. This is mitigated by the live parse, the red border and the per-field
messages, which is good. Fix, optional: attach a `QDoubleValidator` in
`StandardNotation|ScientificNotation` mode for `kind='float'` and a `QIntValidator` for
`int`, so letters cannot be typed. Keep the string round-trip.

**25. Summary precision is fixed rather than significant.** `output/gauge_summary.py:126-134`.
Three decimals on a 12 000 kPa near-field peak prints 12000.000, and on a 0.8 kPa far-field
peak prints 0.800. Pa·s sits next to kPa. Fix, on screen only (the CSV unchanged):
4 significant figures, and a header tooltip saying Pa·s = kPa·ms.

**26. Loading from the runs dialog has little visible feedback.** `ui/results_panel.py:394-418`.
The dialog stays on top while the load runs in the background, and progress shows only in
the status line. Fix: show "Loading <run>..." in the dialog's own status, then close or
focus Results when the entry arrives.

**27. The Setup cards are not ordered by physical meaning.** `ui/setup_spec.py:346-441`.
Order is Domain -> Initialization (the charge) -> Numerics -> AMR -> Boundaries, then
Gauges -> Obstacles -> Outputs. The design-basis threat, which is the given of every case,
is the second card. Solver knobs (CFL, AMR thresholds) sit above the gauges and obstacles
that define the engineering question. Fix, as an order-only change: Threat (charge,
material, burst point) -> Domain & mesh -> Structure (obstacles) -> Gauges -> Boundaries ->
Advanced numerics (collapsible, collapsed by default) -> Outputs.

---

## 4. Proposed screen layout (Setup + Run, the main analysis loop)

The Setup tab keeps its two-part form | preview split. The proposal is about grouping and
about what stays on screen during a run.

```
+--------------+---------------------------------------------------------------+
| sidebar      | Case: wall_A.json *        [0D HD1.3|1D|2D|3D]  Solver: blastFoam |
| Setup  (1)   +--------------------------------+------------------------------+
| Run          | THREAT                         | MODEL PREVIEW                |
| Results      |  Charge [kg] | Material        |  domain, charge, gauges,     |
| Chain        |  Burst x/y/z [m]               |  obstacles; hover = coords   |
|              | DOMAIN & MESH                  |                              |
| Open  Ctrl+O |  Lx Ly (Lz) [m] | Cell [mm]    |                              |
| Save  Ctrl+S |  ~1.2 M cells, dx 25 mm        |                              |
| Recent  >    | STRUCTURE / OBSTACLES  [table] +------------------------------+
|              | GAUGES                 [table] | VALIDATION  (errors first,   |
| Solver       | BOUNDARIES          [2x2 grid] |  click a line -> focus field)|
| [nat|bF]     | > Advanced numerics (collapsed)|                              |
| WSL ready    | > Outputs -> writes to <folder>|  [ Run  F5 ]  [ Initialise ] |
+--------------+--------------------------------+------------------------------+
| status: Saved wall_A.json  ·  2 messages  (click for history)               |
+-----------------------------------------------------------------------------+
```

- Run lives both on the Setup validation card and on the Run tab, so the loop
  "edit, validate, run" never needs a tab switch.
- Run tab: keep the log | live-view split. Add a text progress line
  (% · elapsed · ETA) and a persistent "Result ready -> Open in Results" link when the run finishes.
- Results tab: picker + **method strip** (finding 15) at the top; the view on the left;
  the gauge summary table on the right or below, with Copy; exports grouped as
  "Data (CSV/TSV/Profile/VTK)" and "Figures (PNGs/Report/Animation)".

---

## 5. Quick wins (best value for least effort)

1. **Confirm on close while a run is live.** A dozen lines in `MainWindow.closeEvent`
   (finding 4).
2. **Never lose a solved result to an output-file error.** A try/except around each write
   in `solvers/jobs.py:solve_stage`, logging a `[warn]` (finding 2). This affects Tk
   too, so run its `test_gui_*` suites as well (CLAUDE.md 9).
3. **Turn on the matplotlib toolbar on the Gauges view.** `MplCanvas(toolbar=True)` in
   `results_gauges.py:87`, plus a Copy action on the summary table (finding 14).
4. **Save feedback and a titled window.** Status "Saved <path>", a `[*]` title with the
   case name, and a start folder and default name in the save dialog (part of finding 8).
5. **Make the Material row honest in native mode.** Pending the owner's choice in
   finding 3, at least add a native-mode validation note "Material: native runs use TNT",
   a one-line change in `core/case.py:_validate_solver` or in the form.

---

## 6. Suspected engineering issues (for the owner - not UX fixes)

These are reported, not fixed (CLAUDE.md 6: "if code and document disagree, report it -
never silently change either").

- **E1. The "kg TNT" label on a non-TNT charge.** `setup_spec.py:371, 384, 459, 462` and
  `output/plots.py:56-57` label the charge "[kg TNT]" and title results "N kg TNT". But
  `core/case.py:494-498` sizes the charge with the *selected material's* `rho0`
  (`material_rho0`), so the number is the mass of that material, not a TNT equivalent.
  With material = ANFO, the screen and exported figures say "5 kg TNT" for 5 kg of ANFO.
  Suggest "Charge [kg]" plus the material name in titles. Please confirm the intended meaning.
- **E2. The native solver ignores the material table the validator supports.** The
  consequence of finding 3: `core/case.py:548-566` and the 1D spec comment (N11/T46) say
  the native solvers take their JWL set from the shared table, but the form always sends
  `'TNT'` in native mode. Either the comment or the form is wrong.
- **E3. The "Vieille a" override has no unit.** `setup_spec.py:241` and
  `case_form.py:184` (factor 1.0). In r = a·p^n the unit of `a` depends on the pressure
  and rate units that `n` was fitted in. The neighbouring field is in mm/s. Literature
  values are often in mm/s/MPa^n, so a value copied in could be off by orders of magnitude
  without any warning. The caption should state the unit the code expects, and validation
  could check the result against the tabulated `r_atm`.
- **E4. HD 1.3 zero-substitution** (finding 9). If a zero discharge coefficient or
  wall temperature ever reaches a report, the report shows the substitute value, not
  the input. Worth checking that the HTML report prints the values actually used.
- **E5. No scaled distance next to the gauge results.** The summary table has no
  Z = R/W^(1/3) column, so a user cannot see whether a gauge lies inside the
  Kingery-Bulmash validity range the repo anchors to. This is a display-only suggestion,
  not a change to the CSV. It is listed here because choosing the W (material mass or
  TNT equivalent, see E1) is an engineering decision.

---

## 2026-09-26 · hd1-16-load-export

Reviewed: 2026-09-26, branch `hd1-16-load-export`, HEAD `a3b3c7b`, diff `a0f37e3..HEAD`
without `a9c49ca` (RDX removal) and `d2f5cb1` (OUT-track docs). Read-only, from the code.
The GUI was **not** launched, because another agent is doing on-screen QA. The only thing
executed was the CLI starter case (`--hd13-new` then `--hd13`), in a scratch folder with
no GUI, to read the CSV that an engineer would actually get. Batch plan:
`docs/batches/2026-09-26-hd1-16-load-export.md`. Reference: UFC 3-340-02 (2008) para.
2-15.3.2, Eq. 2-8 / 2-9 (via `docs/references/INDEX.md`). No SBEDS manual is registered,
so nothing below claims what SBEDS accepts beyond the owner's stated format.

Numbering: findings are `L1`-`L14`, so they do not collide with findings 1-27 above.

### A. Screens touched

| Screen | Where | What changed |
|---|---|---|
| Setup → 0D (HD 1.3) form | `ui/setup_spec.py:298-352`, `ui/case_form.py:35-43, 147-155` | "Structure" card built but hidden; new "Loaded wall" card (clearing checkbox, H, W) |
| Main-window status line | `ui/app.py:628-646` | After an HD 1.3 Run it names the `_loads` folder and appends every "still active" message |
| HD 1.3 HTML report | `output/hd13.py:72-317` | Structural response section, verdict table and SDOF figure removed |
| CSV + sidecar `.txt` | `output/load_csv.py` | New: `<report>_loads/nominal.csv` (+ `band_*.csv`), and `<case>_wall_loads/{G1,planemax}_g{124,140}[_cleared].csv` |
| CLI | `__main__.py:64-86`, `output/cli_hd13.py:103-150` | New `--hd13-wall-export CASE`; `--hd13` now lists the load files |

### B. Flows (reconstructed)

**B1. Setup → 0D, the "Loaded wall" card** (column 1, after "Radiation standoffs", before
"Outputs"; `setup_spec.py:314-318`).
- `clearing`: checkbox "Clearing on G1 (UFC 3-340-02 2-15.3.2)", default off.
- `wall_H_m`: "Wall height H [m]", blank. `wall_W_m`: "Wall width W [m]", blank.
- H and W are `setEnabled(False)` while the box is unticked (`case_form.py:147-155`).
  Their values are kept and still saved.
- Parse (`models/fields.py:162-171`): with clearing on, a blank H or W becomes 0.0, and
  non-numeric text is a parse error. With clearing off, any unparsable text silently
  becomes 0.0.
- Validation (`core/assessment.py:46-59`, called from `validate` at `:98-99`): with
  clearing on and H or W ≤ 0 → error "Clearing is on, so the loaded wall needs its
  height H: wall_H_m must be a positive number of metres (got 0.0)". This is the same
  live validator that feeds the Setup report card (`app.py:481-490`), so Run and F5 are
  disabled ("1 error - see Setup").
- What the fields drive: **only** `python -m blastlab --hd13-wall-export case.json`
  (`cli_hd13.py:108-131`). The Qt Run never reads them. There is no Qt action that runs
  the wall export.
- What the wall export reads: the committed HD1-13 CFD traces in `docs/hd13/`
  (`load_csv.py:351-354`). The case contributes only clearing, H and W. Charge, room and
  vent in the same form have no effect on these traces.

**B2. The "Structure" card.** It is built, so its six keys (span, mass, Ru, kE, supports,
rotation limit) load from JSON and save back unchanged. It is hidden with
`setVisible(False)` (`case_form.py:40-43`, `HIDDEN_CARDS_0`). `Ru_pa` from this hidden
card still drives the residual-capacity computation (`assessment.py:555-557`), with a
form default of 400 kPa.

**B3. Qt Run (0D).** Validate on the GUI thread → worker: temp case JSON → `assess` →
`write_report` → `export_hd13` → `bridge.post(_hd13_done, out, err, loads)`
(`app.py:571-606`). This follows the threading rule. On success the status line reads,
verbatim from the golden (`char_golden/ui_hd13_run.json:38`):
`HD 1.3 report written: hd13_report.html; SBEDS loads: 1 CSV in hd13_report_loads;
nominal.csv: record ends while the load is still active: p = -45.3645 kPa at t = 30916.4 ms`.
The label is `label('', 'small')` with no word wrap (`app.py:104`), muted colour, and it
clears after 12 s (`:77-79, 646`). This path does not go through `notify()`, so it gets
no 200-character cap and no warn colour, and nothing is written to the Run log. On
error: `show_error` with `str(err)`, and the form is kept.

**B4. The report.** Banner → "What this is" (pressure-impulse note) → Material →
[Calibration] → Confined (peak pressure in MPa, peak overpressure in kPa, time of peak
in **s**) → Unconfined → Heat → Radiation → Sensitivity ("One envelope over the corners
... not a set of runs to choose from") → Quantity-distance → figures. The report is
written **before** the CSV export (`services/hd13.py:78-85`), and it contains no
reference to the `_loads` folder, to SBEDS, to the "still active" line or to residual
capacity.

**B5. What the starter case actually exports** (run 2026-09-26, scratch folder):
`nominal.csv` has 448 rows, t = 0 to 30 916 ms, **non-uniform** spacing from 4.6 ms to
1200 ms. The first row is `0.0,0.3079875648800953`. The peak overpressure is **+1.01 kPa**
at 7.5 s. The minimum is **-45.36 kPa**, and it is the last sample: the trace plunges
from -16 kPa to -45 kPa in its last 420 ms. The net impulse is -216 204 kPa·ms. The
sidecar carries the NO_INFLOW note, which says that the suction comes from a vent with
no inflow in the 0-D model. The CLI headline says `confined peak 0.102 MPa`.

**B6. CLI.** `--hd13` prints the headline, the report path, then
`loads:  t_hd13_loads   (1 CSV, t [ms], overpressure [kPa], each with a .txt sidecar)`, the
file names, and each "still active" line. `--hd13-wall-export CASE` prints the clearing
state, C_r and t_c per γ, and then the same loads block. Its `--help` text is "write the
HD1-13 wall-load traces (G1, plane-max x gamma 1.24/1.40) as two-column SBEDS CSVs into
<case>_wall_loads/, with clearing if the case asks for it, then exit". A refused case
gives `SystemExit('refusing to export: ...')`. A missing or changed `docs/hd13` file
raises an uncaught `FileNotFoundError` / `ValueError`, so the user gets a traceback.

### C. Findings

#### High

**L1. For the default case, the exported design load is dominated by a suction that
the sidecar itself calls a model artefact. Only the sidecar and the status line say so.**
- `output/load_csv.py:128-133, 298-299` (NO_INFLOW note), `:156-157` (still-active
  rule); `output/hd13.py:156-185` (the report shows the peak only); B5 above.
- What the engineer sees: the report and the CLI say "peak 0.102 MPa" (about +1 kPa
  over ambient). The file they load into SBEDS has a -45 kPa end value, 45 times the
  positive peak, and a strongly negative net impulse. The explanation, "the 0-D chamber
  model has no inflow through the vent", is only in `nominal.txt`, in a line that comes
  after the load-type and γ lines. The status line shows the -45 kPa as "the load is
  still active" and gives no reason. An engineer who opens only the CSV in SBEDS runs a
  wall against an unphysical suction. That is the dangerous direction for a design load:
  batch plan risk 3 is about mislabelling, and this is mis-weighting.
- Fix (UX only, no number changes): (a) put a **"Load summary"** block at the top of the
  report: peak +, peak − (min), end value, net impulse, rows and span, with the NO_INFLOW
  sentence beside the minimum whenever the trace goes below ambient; (b) move the
  caveat lines (NO_INFLOW, still-active) to the **top** of the sidecar under a
  `WARNINGS` heading; (c) in the status line and the CLI, add the reason: "record ends
  at −45.4 kPa (sub-ambient: no inflow through the vent in the 0-D model, see
  nominal.txt)". Whether that suction should be exported at all is an engineering
  question for the owner (see E6 below). It is not a UX decision.

**L2. The "Loaded wall" card suggests that H and W describe this case's wall. They
describe the wall of one fixed, committed CFD run.**
- `ui/setup_spec.py:310-318`; `output/load_csv.py:351-354, 479-485`; B1.
- What the engineer sees: in the 0D form, "Loaded wall" sits under "Heat" (Wall area
  [m2], Wall temperature [K]), which is the **chamber** wall of this case. The natural
  reading is that H × W is that chamber wall, or the wall the chamber pressure
  (nominal.csv, "acts on the inner face of the chamber wall") loads. In fact H and W feed
  only UFC 3-340-02 Eq. 2-8 clearing (t_c = 4S/((1+R)C_r)) applied to probe **G1 at
  (10, 6, 1.4) m** of the HD1-13 run in `docs/hd13/`. Charge, room and vent in the same
  form do not change those traces. "G1" is an internal probe name, and "2-15.3.2" alone
  does not say "front-wall clearing, Eq. 2-8". Nothing on screen says which wall, which
  run, or that this is for the exterior wall facing the vent.
- Fix: rename the card "Exterior wall load export (HD1-13 CFD run, CLI only)". Caption
  the box "Apply front-wall clearing to probe G1 (UFC 3-340-02 para. 2-15.3.2, Eq.
  2-8/2-9)". Caption the fields "Exterior wall height H [m]" and "Exterior wall width W
  [m] (clearing: S = min(H, W/2))". Add a muted two-line hint inside the card: "Used by
  `python -m blastlab --hd13-wall-export case.json` only. The traces come from the
  committed HD1-13 run (docs/hd13), not from this form's charge or room. Plane-max is
  never cleared." Move the card to column 0, directly under "Vent stage (blastFoam)" /
  "Vent gauges", which is the CFD it belongs to.

**L3. The only on-screen record of the export and its warning is a 12-second, unwrapped,
muted status line. It is not logged, and it grows without limit.**
- `ui/app.py:104-106, 639-646`; compare `notify()` at `:788-795`. This aggravates
  findings 12 and 18 above.
- What the engineer sees: an HD 1.3 run takes about 40 s, or about 20 min with the band.
  The user is often away when it ends. The text that names the CSV folder and the
  still-active warning vanishes 12 s later, in the same grey as a routine message. With
  the band on, one "; band_+1-1+1+1+1: record ends while ..." segment is appended per
  flagged trace (up to about 33 segments). The label has no word wrap and no cap, so its
  minimum width, and therefore the window's, grows with the text. That is likely to
  push the window wider than the screen. **This is from reading the code and needs
  confirming on the real window (CLAUDE.md 8.7).** The Run log gets nothing, although
  the batch plan says "the Qt status line / log shows it".
- Fix: route through `notify()` with level `'warn'` when `loads['messages']` is
  non-empty, and summarise ("SBEDS loads: 33 CSV in …; 12 traces end while the load is
  still active, see the sidecars"). Write the full list to the Run log via
  `_log_threadsafe`. Keep warn-level status text until clicked (finding 18). Add an
  "Open folder" link (`QDesktopServices.openUrl(QUrl.fromLocalFile(dir))`) and make the
  paths absolute (finding 12: the default `hd13_report.html` still resolves against the
  process working directory, and so does `hd13_report_loads`).

#### Medium

**L4. Ticking clearing blocks the Qt Run, although the Qt Run does not use it.**
- `core/assessment.py:98-99` (inside `validate`); `ui/app.py:571-574`.
- What the engineer sees: they tick clearing to prepare the case for the CLI export,
  and Run turns grey with "1 error". The error names `wall_H_m`, an internal key, next to
  the caption "Wall height H [m]". "(got 0.0)" is also shown when the box was left blank.
  The H field gets no red border, because this is a validation error and not a parse error.
- Fix: in `assessment.validate`, report missing H or W while clearing is on as a
  **warning** ("Clearing is on but H is blank: `--hd13-wall-export` will refuse this
  case"). Keep the hard error in `cli_hd13.wall_export`, where it matters. Word it with
  the caption: "Wall height H [m] is blank". Whatever the severity, mark the field with
  the red border the parse errors use (`fieldform.py`). If the owner prefers the hard error (the saved case
  is then always exportable), keep it but add the reason to the message.

**L5. The report does not say where the load went, and one of its sentences now
contradicts the export.**
- `services/hd13.py:78-85` (report written before export); `output/hd13.py:252-255, 261-262`.
- What the engineer sees: the report is the document they file. It no longer has a
  structural section and does not mention the SBEDS CSVs at all. The code comment at
  `hd13.py:217` says "the SBEDS CSVs beside this report", but the HTML does not. The
  Sensitivity section still says "One envelope over the corners … not a set of runs to
  choose from", while the export writes **one CSV per band run** with no guidance on
  which to use. The "What this is" note on the pressure-impulse diagram now has no
  structural section after it, but it still reads correctly as a statement about load
  regime. Keep it.
- Fix: export first, then write the report with a final **"Load files for SBEDS"**
  section: folder (absolute, as a `file://` link), a table of file, trace, peak +,
  min, end value, still-active (yes/no), and one sentence: "Two columns, t [ms] and
  overpressure [kPa], no header. Each file has a .txt sidecar." For the band add: "Run
  every band_*.csv and take the governing response. The band is an envelope, and no
  single file is 'the' answer." Put the same links in the CLI "loads:" block.

**L6. Residual capacity is computed from a hidden input and shown nowhere. It never has
been.**
- `core/assessment.py:555-557`; `ui/setup_spec.py:305` (`ru_kpa` default 400, card
  hidden); `services/hd13.py:78-84` passes no `residual`; `output/hd13.py` has no
  parameter for it. `git grep residual a0f37e3 -- blastlab/output blastlab/services
  blastlab/ui` is empty, so it was not displayed before this batch either.
- Why it matters: the owner's Q2 answer reads "residual capacity **stays in the
  report**, unchanged", but it has never been in the report. In the Qt path it is
  computed on every run from Ru = 400 kPa, a value the user can no longer see or edit.
  It has no user-visible effect today, so it misleads no one yet, but the owner's
  decision was based on a report section that does not exist.
- Fix: owner decision. Either (a) add a one-row "Residual capacity (for a later load
  case)" table to the Heat section, only when the case JSON carries `Ru_pa`, and move
  `Ru` out of the hidden card into Heat as "Wall ultimate resistance [kPa] (0 = skip)",
  or (b) drop the computation until HD1-16 step 2. Either is better than a value computed
  from a hidden default.

**L7. The CSV peak and the report peak are different numbers, and nothing says why.**
- `core/deflagration.py:987-989` (`p_max` is taken over every integration step);
  `output/load_csv.py:183-189` (the sidecar peak is the maximum of the sampled rows);
  `setup_spec.py:288-289` ("Samples" 1000).
- What the engineer sees: the report gives the integrator peak, and the sidecar gives
  the peak of the n_out samples. On a sparse 0-D output, 60 ms to 1200 ms apart here,
  these can differ, and the CSV is what SBEDS integrates. "Samples" in the Run card now
  sets the time resolution of the design load, but its caption does not say so.
- Fix: in the sidecar, print both ("peak in this file: X kPa; integrator peak: Y kPa")
  and flag a difference over 1 %. Caption the field "Samples (also the SBEDS load's
  resolution)". Use ms in the report's "Time of peak" row, or add the ms equivalent, so
  report and CSV share a time unit.

**L8. `--hd13-wall-export` is worded for the developer, not the engineer.**
- `__main__.py:64-68`; `cli_hd13.py:108-131`.
- What the engineer sees: the help text says "HD1-13", "G1", "plane-max x gamma" and
  does not say that the traces come from a fixed committed run. The clearing-off line
  says "E = max(R, S)" without defining R and S. A missing `docs/hd13` file (for example
  in an installed copy) or a changed units line ends in a Python traceback.
- Fix: help: "write the exterior-wall load traces of the committed HD1-13 CFD run
  (probe G1 and the wall-plane maximum, γ = 1.24 and 1.40) as SBEDS CSVs (t [ms],
  overpressure [kPa]) into <case>_wall_loads/. The case supplies only the wall H, W and
  whether to apply UFC 3-340-02 front-wall clearing." Print "clearing: off (reflected or
  stagnation pressure, whichever is larger; no clearing; upper bound)". Catch `OSError`
  / `ValueError` in `wall_export` and raise `SystemExit` with the file name.

#### Low

**L9. The sidecar puts the most important lines last.** `load_csv.py:184-199`. The trace
identity is line 8, and the still-active line is the final line. Fix: order it as
file / trace / load type / WARNINGS (NO_INFLOW, still active, clearing not applied to
plane-max) / numbers / provenance.

**L10. Precision in the sidecar is inconsistent.** The net impulse is printed with
`repr` (`-216203.85000140627 kPa*ms`) while the peak uses `.6g`. Fix: `.6g` for display.
The CSV keeps `repr` (the round-trip contract).

**L11. The band file names are cryptic.** `band_+1-1+1+1+1.csv` needs the sidecar to
decode. Fix: keep the names (tests pin them), and write a `README.txt` / `index.csv` in
the `_loads` folder with file, the sign per named axis (n, a, p_ext, h_c, cd), peak and
min.

**L12. Invalid H or W text while clearing is off is silently dropped.**
`models/fields.py:172-177`. If you type "3,5" with clearing on, untick, and save, the
value is saved as 0 and shows blank on reload. Fix: keep the raw text in the form, or
parse-error it regardless of the checkbox. This is minor, because the fields are
disabled while unticked.

**L13. The sidecar has no export timestamp or code version.** Design-load provenance.
Fix: add `exported: <ISO time>, blastlab <git short hash or version>`.

**L14. The first row is non-zero.** `nominal.csv` starts `0.0,0.308` (igniter or initial
state). If SBEDS interpolates from a zero load before t = 0, this is a step. Fix:
state it in the sidecar ("load at t = 0 is 0.308 kPa, not zero"), with no change to the
data. This is for the owner to check against the SBEDS manual when it is registered.

### D. Proposed arrangement of the 0D form (changed cards only)

```
col 0                                   col 1
+-------------------------------+       +-------------------------------+
| Material                      |       | Run                           |
| Charge and chamber            |       |  End time [s] | Samples       |
| Ignition                      |       |  (Samples = SBEDS resolution) |
| Vent stage (blastFoam)        |       | Heat (chamber wall)           |
| Vent gauges [m]               |       |  h_c | Wall area | T_wall     |
| Exterior wall load export     |       |  [Ru for residual, if kept]   |
|  (HD1-13 CFD run, CLI only)   |       | Radiation standoffs [m]       |
|  [ ] Front-wall clearing on   |       | Outputs                       |
|      probe G1 (UFC 2-15.3.2,  |       |  Run name | Report file       |
|      Eq. 2-8/2-9)             |       |  -> loads: <report>_loads/    |
|  H [m] ___  W [m] ___  (grey  |       |     [Open folder]             |
|   until ticked)               |       +-------------------------------+
|  hint: python -m blastlab     |
|   --hd13-wall-export case.json|
+-------------------------------+
```
Report order after the batch: banner → **Load summary + Load files for SBEDS** (L1, L5)
→ Material → Confined → Unconfined → Heat (+ residual if kept, L6) → Radiation →
Sensitivity (with "run every band file") → QD → figures.

### E. Quick wins

1. **Reason and colour on the status line** (L1c, L3): route `_hd13_done` through
   `notify(..., 'warn')` with a summary, and log the full list. About 10 lines in `ui/app.py`.
2. **Relabel the Loaded wall card and add the CLI-only hint** (L2). Captions and one
   muted label in `setup_spec.py`. The keys do not change, so the JSON and goldens hold,
   except `ui_case_form.json` captions.
3. **Load-files section in the report** (L5). Swap two calls in
   `services/hd13.write_report` and add one table in `output/hd13.py`.
4. **Sidecar order: WARNINGS block first** (L9, L10). Reordering in
   `load_csv.write_trace`. The CSV bytes do not change.
5. **Missing H or W while clearing is on becomes a warning in the Qt validator, and
   stays an error in the CLI** (L4). One branch in `assessment.validate`. Owner to confirm.

### F. For the owner (engineering, not UX)

- **E6. The starter case's chamber load ends in a -45 kPa suction that the model says is
  an artefact** (B5, L1). With no vent inflow, cooling drives the chamber far below
  ambient in the last 0.4 s of the record, and that value is exported "as computed"
  (owner, 2026-09-26: SBEDS accepts negatives). Confirming "negative values are exported
  as computed" was a decision about format. Whether an unphysical negative phase belongs
  in a design load is a separate question, and it is not answered yet. Options: export
  as is (current); clip at the first sub-ambient sample and say so; or end the record
  where venting completes. Pre-register the rule before judging any SBEDS response
  (CLAUDE.md 6).
- **E7. Q2 was answered against a section that does not exist** (L6).
- **E8. Which H × W is physically meaningful for G1?** Clearing per Eq. 2-8 assumes the
  whole front wall. G1 is one point at (10, 6, 1.4) m on the HD1-13 wall plane. The UI
  should at least show the HD1-13 wall's extent so that H and W can be checked against
  it. No validation compares them today.
