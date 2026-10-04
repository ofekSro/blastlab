# Batch 2026-09-29-gui-results — GUI-7 · 03 Results (parts 7a and 7b), plus F14

**Goal in one sentence:** rebuild the Qt Results tab as the board's 03 Results
screen, with three columns (results + method · centre · export), one **Field** view
that replaces Fields and Animation, a **Gauges** view with one plot and a Z / kPa·ms
table that can be copied, and grouped exports that show a busy state and cannot be
started twice. First, fix the intermittent `removeEventFilter` crash in
`fieldform.py` (F14). No number, default, case key, file format, export byte or
solver changes anywhere.

**Spec:** [docs/gui-redesign-plan.md](../gui-redesign-plan.md) §7 (03 Results), §4
(Ctrl+C), §9 (rules), §10 (GUI-7 acceptance), §11 (the embedded viewer after GUI-7).
**Boards:** `docs/design/gui-redesign/boards/Results.dc.html`. Read the source; the
trailing `<script>` holds the state rules (`sel`, `view`, `scale` → `manualScale`,
`play`). Lines: left column 57-94 (list 59-78, method 79-92, path 93), view tabs
96-105, Gauges view 107-189 (plot 110-145, readout 146-150, table 151-188), Field view
191-286 (controls 193-215, map 216-259, time bar 262-283, caption 285), 3D 288-296,
export column 298-331 (Data 304-311, Figures 313-321, busy strip 317-320, title
323-326, 3D button 329), footer 333-337. `Results_Chain.dc.html` differs only by the
`chain` badge (lines 61-62) and the **STAGE 1D | 2D | 3D** tablist (lines 98-103):
**GUI-9, not here** — only a hook (T2).
**Branch:** `gui-redesign`, base **`c8a04d2`** (GUI-6 closed).
**UX findings answered:** UX-13 (busy export, no double start), UX-14 (Copy table),
UX-15 (how it was computed).

**Built by earlier GUI batches and reused here.** Tokens `panel`, `tile`, `accent_bg`,
`accent_soft`, `accent_text`, `gauge`, `gauge_bg`, `faint`, `text2`, `border2`,
`entry_border`, `on_accent` (GUI-1); fonts through `theme.font('display'|'body'|'mono')`.
`ui/components.py`: `ToggleSwitch`, `StatTile`, `DockTabs`, `Banner`, `Collapsible`
(GUI-4/6). `widgets.ScrollColumn` and `Segmented`. The frame `ui/topbar.py` (GUI-3).
`ui/scaled_distance.py` is the one source of Z (GUI-5a, D24). `ui/run_gauges.py`
matches a solver's snapped gauge positions to the entered gauges (D61, D73).
`output.gauge_summary` is the one source of peak, arrival, phase and impulse.
`ui/run_clock.fmt_duration` formats durations (D53). The finish banner's
`Open in 03 Results →` and the toast call `MainWindow._open_results`, which selects
the newest entry through `self.results.sel` (GUI-6).

**Findings from earlier batches that bind this one:**
- The app-wide QSS rule overrides a QFont family or size set in code (D6). Set fonts
  through per-widget style sheets or `#objectName` QSS rules, as `components.py` does.
- A QSS `min-height: 0px` silently beats `setFixedHeight` (D41). Pin every board
  height in the QSS: export buttons 40 px, busy strip ≥ 40 px, title input 36, view
  tabs 32 (in a 38 px strip), Play 40 × 40 round, speed and *This frame .png* 32,
  Open the 3D viewer 42, result rows ≥ 44.
- `ui.testing.ensure_qapp()` forces the offscreen platform unless `offscreen=False`
  is passed or `QT_QPA_PLATFORM` is already set. Use `ensure_qapp(offscreen=False)`
  for every geometry measurement and screenshot.
- The embedded 3D viewer is a real Win32 child of its card (`_e2e_ui_embed.py`); any
  sibling that appears, disappears or resizes above it moves it (CLAUDE.md §8.7). F13:
  a window **resize** leaves it outside its card for 22-49 ms at base; this predates
  GUI-7 and is handled by its own rule (T4, T7).
- The Win32 samplers of GUI-6 were implementers' scratch and are lost (F13). This
  batch **commits** its sampler (T4) so the verifier can re-run it.
- **This PC has 8 GB.** Commit charge sat at 0.4-2.2 GB free through GUI-6: lone
  suites died of `MemoryError` / exit 127 / a segfault and passed once memory freed;
  a native 3D solve with the viewer child ran out of memory. Run heavy suites **one
  at a time**, check free memory before a real-platform or 3D run, and treat a
  `MemoryError` as "environment, re-run", never as pass or fail. Record every such
  rerun in the report (A/B at base when it repeats).

---

## Split: 7a then 7b (one plan, two runs back to back)

GUI-7 is L, the size GUI-5 and GUI-6 were when they had to be split (D14, D42). One
uninterrupted run cannot build **and** verify it on the real platform. So:

- **7a (T0-T4):** pin the exports before anything changes, fix F14, the three-column
  screen with the results list and the method card (Show case, Load into 01 Setup),
  the chain stage hook, and the export column (grouped, busy, no double start, title,
  Open the 3D viewer). The centre keeps today's four sub-views under the new view
  tab strip, so at the end of 7a the app is fully usable.
- **7b (T5-T7):** the Gauges view (one plot, selection, positive phase, readout,
  table with Z and kPa·ms, Copy / Ctrl+C), the Field view (Fields + Animation merged,
  colour scale, time bar with arrival ticks, hover readout, *This frame .png*), and
  the final §10 verification.

Start 7b straight after T4 commits, if the run has budget (the owner wants the
track done without stopping). Reports: `docs/batches/2026-09-29-gui-results-a.implement.md`
and `…-b.implement.md`, one verification `…gui-results.verify.md`.

---

## Tasks, in order

Every task leaves the app runnable, `python blastlab/tests/test_regression.py`
byte-green and `python blastlab/tests/test_ui_char_results_exports.py` (T0) green.
The new fast suite is **`blastlab/tests/test_ui_results_screen.py`** (offscreen, plain
script, `check()` style as `test_ui_run_screen.py`, the `sys.excepthook` recorder
re-raising uncaught errors as GUI-6's review fixed in `61bfd56`). Each task adds its
own section S1…S7.

### Part 7a

#### T0 · Pin what the Results panel exports, before any change — size S

**Files:** new `blastlab/tests/test_ui_char_results_exports.py`, new golden
`blastlab/tests/char_golden/ui_results_exports.json`. **No other file.**

- Run it **at base `c8a04d2`**, with no GUI-7 code in the tree, and commit the test and
  its golden **alone, first** (`tests: pin the Results panel exports before GUI-7
  (GUI-7)`). This is the "pre-batch export" of plan §10.
- What it drives: the real `ResultsPanel` (offscreen, `ensure_qapp()`), with the
  native 1D and 2D results of `test_char_exports.result('1d')` / `result('2d')` (the
  Phase 0 1D case and the 2D axisymmetric case with `record_frames=12`, the run names
  of `NAMES`), added with `p.add_result(label, dim, res)`. Dialogs replaced exactly
  as `test_char_exports.qt_export` does (`save_file`, `pick_dir` recorders, the
  `gif_name` rule, `os.startfile` → `Opened`). Every export through
  **`p.export(kind, threaded=False)`**, the panel's own path.
- Kinds: every kind in `exports.KINDS` (vtk on its refusal path). Variants:
  `plain`; `titled` (title box `Char title`, Show mesh on) for `report`, `pngs`,
  `gif`; and for `gif` also `scale=frame` and `scale=manual (0, 50)`.
- Record per case/kind/variant: the dialog calls, the return value, the log lines,
  what was opened, **`p.export_opts()`** (the dict the animation export receives) and
  every written file through `test_char_exports.describe_dir` (text sha256, npz
  array-wise, HTML normalised, PNG pixel size, GIF size + frame count).
- **The state setter is one function**, `drive(p, title=None, mesh=False,
  scale=None, clim=None)`. At base it sets `p.title_box`, `p.fields.show_mesh`,
  `p.anim.scale_sel` (label from `ANIM_SCALE_LABELS`) and `p.anim.min_box/max_box`.
  After T6 it is extended with a **second** function `drive_visible(...)` that sets the
  same state through the new visible controls. Both must produce the same golden.
  `drive` itself is not edited after T0.

**Acceptance:** `python test_ui_char_results_exports.py` prints `CHAR UI RESULTS
EXPORTS: PASS` at base; the golden's text-file hashes for `summary`, `tsv`,
`fieldcsv`, `profile` equal those of `char_golden/exports_qt.json` for the same
kind (a check inside the test, so the two pins cannot drift apart).

#### T1 · F14: `removeEventFilter` on an already-deleted viewport — size S

**Files:** `blastlab/ui/fieldform.py` (`_watch_viewport`, `eventFilter`, a new
`_forget_viewport`), `blastlab/tests/test_ui_setup_form.py` **or** a new
`blastlab/tests/test_ui_fieldform_viewport.py` (additions only).

- **Find the cause before fixing it.** F14 (decisions file): `test_ui_run_screen`
  died at R5's `win._show('setup')` in 2 of 7 runs with `RuntimeError: Internal C++
  object (PySide6.QtWidgets.QWidget) already deleted`, raised from
  `FieldForm._watch_viewport` (line 631) through `SetupPanel.showEvent`. The form
  keeps a Python reference `self._watched` to the viewport of the nearest
  `QScrollArea` ancestor. When that scroll area is deleted while the form lives on
  under another one, the next `showEvent` calls `removeEventFilter` on the dead
  wrapper. Establish **which** scroll area it is. Instrument a local copy (not
  committed): log `type(scrollarea).__name__`, its objectName and the parent chain
  at every install, and connect `vp.destroyed` to a logger that prints a stack. Then
  run `test_ui_run_screen.py` up to 20 times, one at a time. Candidates to check:
  the Setup properties column's per-node scroll pages (`setup_nodes.py`), the Chain
  editor's `'columns'` form, and a parentless `ScrollColumn` collected by Python's GC
  (timing-dependent = GC-dependent is the likeliest). Write the finding into the
  report and into the F14 row's outcome.
- **Fix, whatever the cause:** on install, `vp.destroyed.connect(self._forget_viewport)`
  where `_forget_viewport` sets `self._watched = None` when it is that viewport. In
  `_watch_viewport` guard with `shiboken6.isValid(self._watched)`: a dead one is
  dropped, never called. If the investigation shows a scroll area rebuilt under a
  live form on purpose, fix that site too (and say so).
- `eventFilter` compares `obj is self._watched`. It must not touch a dead wrapper.

**Acceptance (S1 plus a repeat rule, pre-registered):**
- A deterministic test that **fails on base code**. Put a `FieldForm` (placement
  `'nodes'` and `'columns'`) in scroll area A and show it. Take it out
  (`A.takeWidget()`), put it into scroll area B and delete A with
  `shiboken6.delete(A)`. Then hide and show the form. Assert: no exception (a
  `sys.excepthook` recorder is empty), and resizing B's viewport calls
  `_fit_columns` once (a counter) — the filter moved to B. Run the test against base
  (a `git worktree` of `c8a04d2`) and paste its failure in the report.
- **Rule R-F14:** after the fix, `python test_ui_run_screen.py` passes **10 of 10**
  consecutive runs, sequential, nothing else running. A run that dies of
  `MemoryError` is re-run and reported, not counted.
- `test_ui_setup_form`, `test_ui_setup_tree`, `test_ui_setup_strip`, `test_ui_parity`,
  `test_ui_char_case_form` and `test_ui_chain` are green and unchanged.

#### T2 · Three columns, results list, method card, Show case / Load into 01 Setup, stage hook — size L

**Files:** `blastlab/ui/results_panel.py` (layout rebuilt, public API kept — see below),
new `blastlab/ui/results_list.py` (`ResultsList`), new `blastlab/ui/results_method.py`
(toolkit-free `method_rows`, `result_caption`, `case_source`), `blastlab/ui/app.py`
(`_load_case_from_result`, the `add_result` call passes nothing new, `_open_results`
unchanged), `blastlab/ui/dialogs.py` (only if a new dialog helper is needed; resolved
at call time like every dialog), `blastlab/ui/theme.py` (object-name QSS rules only),
`blastlab/tests/test_ui_results_screen.py` (new, S2), `blastlab/tests/test_ui_results.py`
and `blastlab/tests/test_ui_parity.py` (only the pins listed under "Committed
assertions").

What to build (board 57-105, 298-331):
- **Columns:** results + method **280 px** (`panel`, right border) · centre (stretch,
  padding 14/18) · export **320 px** (`panel`, left border). The side columns are
  vertical-only `ScrollColumn`s and may narrow (to 248 and 288) only when the window
  cannot hold all three (the D19 / GUI-6 pattern). Nothing clips at 1100 × 720.
  Record the widths measured.
- **Results list** (`ResultsList`, attribute **`sel`**, board 59-78): a caps
  `RESULTS`, then one row per entry, **newest last** as today. Each row shows the
  **name** (`elide_middle(label, PICKER_MAX)`, the full label in the tooltip),
  a `latest` badge on the newest (`accent_bg`/`accent_soft`), a `chain` badge when
  `entry.kind == 'chain'` (nothing sets it before GUI-9), and the **caption**
  `result_caption(entry)`: `1D spherical` / `2D axisym.` / `2D planar` / `3D` ·
  `native` / `blastFoam` · duration. The selected row has the `accent_bg` fill. The
  list scrolls inside the column when rows do not fit.
  **`ResultsList` keeps the QComboBox surface every caller uses:** `count()`,
  `itemText(i)`, `itemData(i, role)` (ToolTipRole = the full label), `setItemData`,
  `currentIndex()`, `setCurrentIndex(i)`, `currentData()` (the `ResultEntry`),
  `currentIndexChanged`, `addItem(text, data)`, `clear()`, `blockSignals`. The harness
  `select_result`, `test_ui_results` R1, `test_ui_run_screen`, `_e2e_ui_chain` and
  `MainWindow._open_results` then work unchanged.
- **Under the list:** **Load a run…** (`_foam_runs_btn`, today's run browser; the
  text changes from `Foam runs…`) and a square **Remove** (`_remove_btn`, an ✕ icon,
  tooltip `Remove <name> from the list`). The blastFoam-only launcher stays hidden in
  native mode (R2 pins it).
- **How it was computed** (UX-15, board 79-92), from `results_method.method_rows(res,
  dim)` → `[(label, value)]`. A row appears **only when its source holds the value**;
  nothing is defaulted, derived beyond formatting, or guessed.
  - Sources, in order: `res.meta`, `res.stop_reason`, and **the result's own record
    files that `res.meta` names**: `meta['model_dir']` → `MODEL.json` (the case
    exactly as run, OUT-1) and `manifest.json`; for a loaded blastFoam run with no
    model folder, `meta['case_dir']` → its `case.json` (the file the resume path
    reads). A missing or unreadable file drops its rows silently.
  - Rows (board order):
    - **Solver:** `manifest['solver']` or `meta['solver']` → `native` / `blastFoam`.
      No version is recorded anywhere today, so none is shown.
    - **Charge:** `{W:g} kg {material}` + the burst position. W is `meta['charge']`
      (2D/3D) or `meta['charge_kg']` (1D). The material is `meta['material']` (foam) or
      the case file's. The position is `· z {cz:g} m` (2D axisymmetric), `· x, y`
      (planar), `· x, y, z` (3D), and nothing in 1D.
    - **Detonation** and **Afterburn:** the case file's activation / afterburn
      fields, **blastFoam results only** (the native solvers detonate at t = 0,
      CLAUDE.md §7; hide, never grey).
    - **Mesh:** `cell {dx·1000:g} mm` from `meta['dx']`, or the case file's 1D cell
      size; `· finest {dx_base/2^lmax·1000:.3g} mm` when `meta['refine']` has
      `lmax > 0` (D30's word `finest`).
    - **Parallel:** `manifest['n_procs']` → `N MPI ranks`, or `serial` for 1.
    - **Ended:** `res.stop_reason` **verbatim** (D66), then `· t = …` from the final
      snapshot's label, then `· finished HH:MM` from `manifest['finished']`.
  - Values are mono (`text`), labels `faint`. Long values elide with the full text in
    the tooltip.
  - **Show case** and **Load into 01 Setup** sit under the rows.
    `results_method.case_source(entry)` gives the path (`MODEL.json`, else the
    loaded run's `case.json`) or None. With None both buttons are **disabled** with
    the why-not tooltip `This result carries no saved case (no model folder).`
  - **Show case** opens a **non-modal**, read-only mono viewer (title `Case as run ·
    <name>`) holding the file's text, its path, and a Copy button. It is not modal,
    so no unattended driver can hang on it.
  - **Load into 01 Setup** calls `MainWindow._load_case_from_result(path)`, wired
    through a panel signal `load_case_requested(str)`. That method:
    - parses with `load_any_case` (the same errors and dialogs as `_open_case`);
    - asks `dialogs.ask_yes_no('Load into 01 Setup', 'Replace the unsaved changes in
      <case>?', yes='Replace', no='Keep editing')` **only when Setup is dirty**;
    - does `setup.set_case(case)` and sets the run name to the model;
    - sets `_case_path = None`, so Ctrl+S goes to Save as and **never writes into the
      model folder's `MODEL.json`**;
    - marks the case dirty, updates the title and shows Setup.
    A relative `profile_file_in` is resolved against the file's folder by
    `load_case` itself (`models/case.py` ~line 677). Check it with a profile case.
- **Path line** at the column's foot: `meta['model_dir']` in mono `faint`, elided in
  the middle, full text in the tooltip, and hidden when there is none.
- **Centre header:** an empty hidden **`stage_slot`** (zero height, `QHBoxLayout`)
  with `set_stage_strip(widget_or_None)`, exactly as `RunPanel.chain_slot` (GUI-6
  T8). Then the **view tab strip**, restyled to the board (a 38 px strip with 32 px
  tabs), showing today's four views in 7a: `Fields · Gauges · Animation · 3D`. T6
  turns it into `Field · Gauges · 3D`.
- **`ResultEntry`** keeps `ResultEntry(label, dim, result)` positional (the char
  golden builds one) and gains `kind='run'` and `stages=None` (GUI-9's).

**Public API that must survive, with meaning unchanged:** `add_result(text, dim,
result)`, `entries()`, `current()`, `remove_current()`, `clear_views()`, `refresh()`,
`show_view(name)`, `view()`, `title_extra()`, `title_box`, `export(kind,
threaded=True)`, `export_opts()`, `export_enabled(kind)`, `_export_btns` (8 kinds),
`_foam_runs_btn`, `_remove_btn`, `_view3d_btn`, `open_3d()`, `open_run_browser()`,
`load_foam_run_path(path)`, `set_solver_mode(m)`, `shutdown()`, `sel`, `fields`,
`gauges`, `anim`, `view3d`, `stack`, `EXPORT_HELP`, `EXPORT_BUTTONS`, `PICKER_MAX`,
`elide_middle`, `ResultEntry`.

**Acceptance (S2, offscreen):**
- Widths at 1600 × 1000: 280 / centre / 320 (±1 px). At 1100 × 720 and at 900 × 600
  (the panel's own test size), `clipped(win)` from `test_ui_parity` is empty on
  Results in both modes with 12 entries in the list.
- Two results with the same label → `run`, `run #2`; `sel.currentData() is` the
  second; `sel.setCurrentIndex(0)` reaches the first (R1's checks, unchanged). The
  newest row, and only it, carries `latest`. A long label is elided in the middle,
  and `itemData(i, Qt.ToolTipRole)` is the whole label.
- `method_rows` on:
  - a native 2D result with a model folder built by the test (`save_case(case,
    MODEL.json)` plus a `manifest.json` with `solver`, `n_procs`, `created`,
    `finished`);
  - a blastFoam-shaped 2D result (`char_meta_results.foam_shaped('2d')`) with a
    case file holding `activation='linear'`, `afterburn='none'` and
    `refine={'lmax': 2, 'dx_base': 0.025}`;
  - a native 1D result with no model folder.
  For each, the rows equal a list **built in the test** from those same inputs.
  The 1D result has no Solver row (its meta holds no `solver`), no Detonation /
  Afterburn / Parallel row, and an Ended row equal to its `stop_reason`. The
  native 2D result has no Detonation / Afterburn row. No row reads `None`, `nan` or
  `?`.
- Show case / Load into 01 Setup are disabled with the why-not tooltip when
  `case_source` is None. Show case opens a non-modal viewer whose text equals the
  file's bytes decoded as UTF-8.
- Load into 01 Setup (on a `MainWindow` with throwaway settings):
  - `win.current_tab() == 'setup'`;
  - `win.setup.get_case()` equals `load_case(MODEL.json)`;
  - `win._case_path is None` and the case is dirty;
  - `MODEL.json`'s sha256 is unchanged after `win._save_case_inplace()`, with
    `dialogs.save_file` patched to cancel;
  - with Setup dirty beforehand, `ask_yes_no` is asked once, and *Keep editing*
    changes nothing.
- `stage_slot` is hidden at 0 px for a single result. `set_stage_strip(QLabel('x'))`
  shows it above the view tabs, and `None` hides it again.
- `test_ui_results` (with only the allowed pin changes), `test_ui_results_vtk_folder`,
  `test_ui_char_results_meta`, `test_ui_char_results_exports` (T0),
  `test_char_exports` and `test_ui_run_screen` are green.

#### T3 · Export column: Data / Figures, busy state, no double start, title, Open the 3D viewer — size M

**Files:** new `blastlab/ui/export_column.py` (`ExportColumn`, `ExportButton` with
its busy strip), `blastlab/ui/exports.py` (`export(..., on_done=None)`),
`blastlab/ui/results_panel.py`, `blastlab/ui/theme.py` (QSS),
`blastlab/tests/test_ui_results_screen.py` (S3), `blastlab/tests/test_ui_results.py`
(R1's two wrap-row pins only). **`services/exports.py` is not edited.**

- **Layout (board 298-331):** caps `EXPORT` and the caption `Into the model folder,
  or anywhere you choose.`
  - **Data:** `Summary .csv` (`summary`), `Gauge traces .txt` (`tsv`; the file is
    tab-separated `.txt`, and its name is pinned by the golden, so the board's
    `.tsv` would misstate it), `Field snapshot .csv` (`fieldcsv`), `Profile, for a
    Chain .txt|.npz` (`profile`; the suffix follows the result's dimension, the
    same rule as `pick_target`), `VTK for ParaView .vtk` (`vtk`, blastFoam mode
    only).
  - **Figures:** `All plots .png` (`pngs`), `Report .html` (`report`), `Animation
    .mp4|.gif` (`gif`; the suffix is `output.animation.default_ext()`).
  - Then `Title on figures (optional)` with **`title_box`** (the placeholder `added
    above the automatic title`, same `textChanged` behaviour), a stretch, and **Open
    the 3D viewer** (`_view3d_btn`, 42 px, calls `open_3d`).
  - Each button is 40 px: the label in `text` and the suffix in mono `faint` at the
    right.
- **`_export_btns`** maps the same 8 kinds to the new buttons. Enable and tooltip
  logic stays `_sync_export_buttons` (`exports.can` / `why_not` / `vtk_tip` /
  `EXPORT_HELP`). VTK hides in native mode (hide, never grey).
- **Open the 3D viewer** is enabled only for a 3D result with snapshots, pyvista
  present and a viewer link. Otherwise it is disabled with the why-not tooltip
  (`3D results only.` / `MISSING_MSG` / `This result has no snapshots.`). `open_3d()`
  keeps its log lines (harness E01 reads `select a 3D result`).
- **Busy state (UX-13):** `ui.exports.export(kind, ent, opts, log, parent,
  on_error, threaded, on_done=None)`.
  - With `threaded=True`, the worker runs `run_export(...)` and then, in a
    `finally`, calls `on_done(ret)`.
  - With `threaded=False` the call is exactly today's, then `on_done(ret)`.
  - The panel passes an `on_done` that posts, through its `ThreadBridge`, to
    `_export_done(kind)` on the GUI thread.
  - The panel's `on_error` (today `dialogs.show_error`, called **from the worker
    thread** for a VTK failure — a latent bug) is posted through the bridge the
    same way.
  - `test_char_exports` calls `export(..., threaded=False)` with no `on_done`, and
    its golden must stay byte-identical.
  - The busy strip goes up **only after** `pick_target` returned a path, so a
    cancelled dialog shows nothing. While a kind is busy:
    - its button is replaced by the strip: `accent_bg` fill, `accent_border`, the
      name, `writing…` in mono `accent_soft`, and an indeterminate 4 px bar
      (`accent`), all as on the board at 317-320;
    - `export(kind)` returns `''` at once and logs `<Label> is already being
      written.`;
    - other kinds may still start, and Remove still works (the worker holds its
      own references).
  - `_export_done` restores the button and re-syncs its enablement.
  - **No percent.** `run_export` gives the animation writer no progress callback,
    and passing one would edit the shared `services/exports.py` (plan §9's Tk
    gate). That is a decision row with the owner's option.
- The eight `EXPORT_HELP` texts are kept. "Field snapshot" writes one CSV per field
  map, and its tooltip says so.

**Acceptance (S3, offscreen):**
- Button order and grouping: Data = `summary, tsv, fieldcsv, profile, vtk`, Figures
  = `pngs, report, gif`. The suffix of `profile` is `.txt` for 1D and `.npz` for 2D.
  The suffix of `gif` equals `default_ext()`.
- The R2 matrix of `test_ui_results` (enable / why-not per result kind; VTK hidden
  in native) passes unchanged. No label is cut off at 1100 × 720 or 900 × 600: the
  label's advance fits inside the button, and `clipped()` is empty.
- **No double start:** patch `ui.exports.run_export` with a function that blocks on
  a `threading.Event`, and the dialogs with recorders returning a temp path. Then:
  - `p.export('summary')` shows the busy strip (`isHidden()` false, the button
    hidden);
  - a second `p.export('summary')` returns `''`, adds no worker (a counter), and
    logs the sentence;
  - `p.export('tsv')` still starts;
  - after `event.set()` and a pump, both buttons are back and enabled;
  - `_export_done` ran on the GUI thread (`QThread.currentThread() is
    app.thread()`).
  - Restore `run_export` afterwards.
- A cancelled dialog (the recorder returns `''`) shows no strip.
- Open the 3D viewer is disabled with the right tooltip for 1D, 2D and a 3D result
  with no snapshots, and enabled for a 3D result with snapshots under the `FakeLink`.
- `title_box` retitles the figures as before (E09's checks, run offscreen through
  `p.title_box.setText`).
- `test_ui_char_results_exports` (T0) and `test_char_exports` are green: **the bytes
  are unchanged.**

#### T4 · 7a verification, the committed viewer sampler, report — size M

- The fast Qt matrix, **one suite at a time**, from `blastlab/tests`:
  `test_ui_results_screen`, `test_ui_results`, `test_ui_results_vtk_folder`,
  `test_ui_char_results_meta`, `test_ui_char_results_exports`, `test_char_exports`,
  `test_ui_run_screen` (R-F14: 10/10), `test_ui_run_panel`, `test_ui_live_gauges`,
  `test_ui_frame`, `test_ui_parity`, `test_ui_drain`, `test_ui_view3d_host`,
  `test_ui_three_surfaces`, `test_ui_char_hd13_run`, `test_ui_char_write_failure`,
  `test_ui_char_case_form`, `test_ui_components`, `test_ui_theme`,
  `test_ui_setup_strip`, `test_ui_setup_tree`, `test_ui_setup_form`,
  `test_ui_chain`, `test_ui_run_browser`, `test_ui_no_vtk_in_main`,
  `test_ui_no_mpl_pyplot`, `test_ui_status_cells`, `test_ui_crashlog`; always
  `test_regression` (byte), `test_foam_writer`, `test_case_validate`,
  `test_gauge_summary`, `test_report`, `test_anim_scale`.
- **Commit the sampler** `blastlab/tests/_e2e_ui_viewer_place.py`: real platform
  only (it exits with SKIP offscreen); ctypes `GetWindowRect`, `GetParent`,
  `IsWindowVisible` on the viewer's HWND against the card's rect, every ≤ 2 ms, in the
  style of `_e2e_ui_embed.py` E3. `--surface results|run|setup`, `--actions a,b,…`,
  `--repeat N`, `--out file.json`. It writes per action: samples, samples with a
  viewer window, the longest unbroken wrong-place stretch in ms, and the worst
  offset. It stops **its own** viewer child by PID at the end.
- **Pre-registered viewer rules (write them into `measurements-7a.md` before the
  first sampled run):**
  - **R-VIEWER:** on a native 3D result in the Results 3D view, the longest
    wrong-place stretch is **0 ms** over **≥ 500 samples with a viewer window**
    for: Open the 3D viewer; a result selection change (the method card changes
    height); an export busy strip up and down (the right column);
    `set_stage_strip` show / hide (above the view); Setup ↔ Run ↔ Results; a
    theme toggle.
  - **R-VIEWER-RESIZE (F13):** resize 1600 → 1100 → 1600, three repeats. The median
    of the longest stretch at HEAD is ≤ the same sampler's median at base
    `c8a04d2` + 5 ms. Run base and HEAD back to back on the same machine, in a
    `git worktree` of the base.
  - Above either threshold: fix it in this batch (the `shrink_ahead` pattern of
    D70 for anything that appears above the host), or report the number and the
    action. Never "it ends up in the right place".
- Real-platform screenshots of 7a's state (dark, 1600 × 1000 and 1100 × 720): the
  list with three results, the method card of a native 2D result with a model folder,
  and an export busy. Save them to `docs/qa/2026-09-29-gui-results/`.
- Harness smoke, offscreen, own settings: `--scenario B01,D01,D02,E01,E03,E07,E08,E09`
  (D01/D02 cache the native results E reads).
- Report: `2026-09-29-gui-results-a.implement.md`. Append decision rows to
  `docs/gui-redesign-decisions.md` (next id **D76**) and F-rows (next **F15**).
  Update the F14 row's outcome (cause found, fixed in `<commit>`).

### Part 7b

#### T5 · Gauges view: one plot, selection, positive phase, readout, table with Z and kPa·ms, Copy — size L

**Files:** `blastlab/ui/results_gauges.py` (rewritten: pyqtgraph plot, table,
selection, Copy), `blastlab/ui/scaled_distance.py` (a display-only
`case_from_meta(meta, dim)` adapter — no new formula, no new citation),
`blastlab/ui/run_gauges.py` (make the entered-gauge matcher public, for example
`match_gauges(case_like, gauge_out)`; `test_ui_run_screen` R5 stays green),
`blastlab/ui/results_panel.py` (the shared selected gauge),
`blastlab/tests/test_ui_results_screen.py` (S5), `blastlab/tests/test_ui_results.py`
and `blastlab/tests/test_ui_char_results_meta.py` + its golden (only as listed under
"Committed assertions").

- **Plot (board 107-150):** one pyqtgraph plot on screen, the on-screen rule of
  CLAUDE.md §5. The exported gauge figure stays the matplotlib grid of
  `output/plots.py`, untouched; the header tooltip says the file is the grid.
  - Header: `<field> at the gauges` and the caption `selected gauge in colour, the
    others grey · shaded: positive phase`.
  - **Every gauge is one curve** of `plots.GAUGE_FIELDS[field]`: x = `times × 1e3`
    [ms], y = the field's own transform (`(p − P_AIR)/1e3` for `p`). These are
    exactly the arrays the matplotlib builder plots.
  - The selected gauge is drawn in `gauge` at 2.4 px, the others in a grey token
    (`#4a4a50` dark; derive light and check contrast) at 1.2 px.
  - The x label is `time [ms]` and the y label is `plots.GAUGE_FIELDS[field][1]`,
    so the OUT-4a y-labels of R4 hold.
  - The `Trace` selector (`field_seg`, hidden for p-only results) is unchanged.
  - **Positive phase:** for the selected gauge, **only for `p`**, a
    `FillBetweenItem` between the curve and 0 over `[arrival_ms, arrival_ms +
    pos_duration_ms]` from `summarize_trace`, `gauge` at 16 % opacity. There is no
    fill when the arrival is NaN.
  - Readout under the plot: `G2 · Z 2.99`, `peak 231.4 kPa at 4.180 ms`, `pos.
    impulse 112.35 kPa·ms`. The number strings are the table's own (same `_fmt`
    precision), so screen and table cannot disagree.
- **Table (board 151-188):** columns `Gauge · Z [m/kg^1/3] · Peak [kPa] · Arrival
  [ms] · t peak [ms] · Pos. phase [ms] · Pos. impulse [kPa·ms] · Net impulse [kPa·ms] ·
  Phase ended`. Every header has a tooltip (the old `HEADER_HELP`, plus Z).
  - **Values:** every cell except Gauge and Z is `gauge_summary.table_rows(
    summary_rows(res))`'s string for that gauge, **unchanged**. The impulse is the
    same number: 1 Pa·s = 1 kPa·ms, so only the header's unit changes (plan §7:
    "the same number as Pa·s"). The CSV/TSV keep `positive_phase_impulse_Pa_s` —
    no export changes.
  - **Gauge** cell: `G<n>`, with the old label (`G1 (0.300, 0.800) -> cell (…) m`)
    in its tooltip.
  - **Z:** from `scaled_distance.scaled_distance(case_from_meta(meta, dim),
    entered_point)`, where each row's entered gauge is found by the run_gauges
    matcher (D61/D73 rules) and formatted `.2f`.
    - `case_from_meta` reads `charge` / `charge_kg`, `charge_center`, `geometry`,
      `from_profile` and `gauges` (1D: `gauges['radii']`). **Any missing key →
      Z hidden** (never guessed).
    - When Z is not shown (planar 2D, a profile start, 0-D, missing keys), the Z
      **column is hidden** (`setColumnHidden`).
  - **Order:** ascending Z, ties by number (the Run screen's rule, D61). With Z
    hidden, the rows go by number.
  - Caption: `click a row to plot it · net impulse includes the negative phase`
    (CLAUDE.md §7; UFC 3-340-02 para. 2-12, printed p. 43, defines the positive and
    negative phases). `Phase ended` "no" rows in `warn`, as the board's `endColor`.
  - **Selection:** a row click selects that gauge, recolours the curves, moves the
    shading and updates the readout. The default is `meta['trigger_gauge']` when set,
    else the first row. It persists across the Field/Gauges switch (T6's ticks read
    it) and resets on a result change.
    `ResultsPanel.selected_gauge()` / `select_gauge(n)` are the API.
  - Height rules: `MAX_ROWS_SHOWN`, `TABLE_MAX_SHARE` and `_cap_height` are kept.
    The plot takes the stretch.
  - At narrow widths the headers wrap onto two lines, and the table scrolls
    horizontally rather than clip.
- **Copy table** (UX-14): a button `Copy table  Ctrl+C` at the table header's right,
  and **Ctrl+C when the table has focus** (a `QShortcut` with
  `Qt.WidgetWithChildrenShortcut` on the table: never window-wide, so Ctrl+C in any
  text box is untouched).
  - Clipboard text = the visible headers, then one line per row in on-screen order.
  - Cells are joined by `\t` and lines by `\n`, exactly the displayed strings.
  - Hidden columns are left out, and there is no trailing newline.
- **Numbers never re-derived:** the only arithmetic added is the display transform
  of `GAUGE_FIELDS` (already the builder's) and the Z formula of
  `scaled_distance`.

**Acceptance (S5, offscreen; plan §10 "Copy table puts tab-separated text with
headers on the clipboard"):**
- For the 2D axisymmetric native result of `test_char_exports.result('2d')`, and for
  the sample geometry (1 kg at z 2, gauges G1 (2.95, 0.50), G2 (2.95, 1.50)):
  - each curve's `(x, y)` equals `(times*1e3, GAUGE_FIELDS['p'][2](p_k))` by
    `np.array_equal`, for every gauge;
  - Z equals `scaled_distance(case, entered)` computed in the test (G1 3.31, G2
    2.99);
  - every numeric cell equals `table_rows(...)`'s string for that gauge (matched by
    gauge number, not by position).
- The selected curve has the `gauge` pen at 2.4 px and the others the grey pen. The
  fill spans `[arrival_ms, arrival_ms + pos_duration_ms]` of the selected gauge. A
  click on row k moves both. With `field = '|U|'` there is no fill.
- Planar 2D and a profile start: the Z column is hidden and rows go by number.
- **Copy:** `QApplication.clipboard().text()` equals a string **built in the test**
  from the visible headers and `table_rows` + Z. There are nine columns with Z,
  eight without. Ctrl+C with the table focused copies the same text; Ctrl+C in
  `title_box` does not touch the clipboard's table text.
- The OUT-4a y-labels of R4 hold on the pyqtgraph axis. `MAX_ROWS_SHOWN` /
  `TABLE_MAX_SHARE` hold (the plot is taller than the table at 1100 × 720 and at
  900 × 600; 12 gauges scroll).
- 1D (`result('1d')`): one plot, Z = r / W^(1/3), no selector.

#### T6 · Field view = Fields + Animation: controls, colour scale, time bar, hover, This frame .png — size L

**Files:** new `blastlab/ui/results_field.py` (`FieldView`, `TimeBar`, the hover
readout), `blastlab/ui/results_fields.py` and `blastlab/ui/results_anim.py`
(**engines kept**: their own control rows go into one hideable `controls` widget
each; `FieldsView` gains `set_scale(scale, clim)` for snapshot maps; its
`show_mesh` becomes a checkable button with the same `setChecked` / `isChecked` /
`toggled` API), `blastlab/ui/pg_plots.py` (a `ScalarImage.value_at(x, y)` helper only),
`blastlab/ui/results_panel.py` (`VIEWS = ('Field', 'Gauges', '3D')`; `show_view`
accepts the old names `Fields` / `Animation` as aliases of `Field`),
`blastlab/tests/test_ui_results_screen.py` (S6), `blastlab/tests/test_ui_char_results_exports.py`
(adds `drive_visible` only), and the allowed pins below.

**Architecture: placement, not engines** (the GUI-5 rule "split its placement, not
its parsing"). `FieldsView` (snapshot maps, the matplotlib page, the hint) and
`AnimView` (the recorded replay, `resolve_clim`, the play timer) stay the drawing
engines. Their widgets `snap_sel`, `field_sel`, `scale_sel`, `min_box`, `max_box`,
`slider`, `play_btn` and `speed_sel` stay alive, **hidden**, as the state the
engines read. The pinned characterisation (`test_ui_char_results_meta`) and many R-
and E-checks drive them. `FieldView` puts the board's controls on top and keeps both
in step, both ways, with `blockSignals` against loops. **List every hidden legacy
widget in the report**, for GUI-10 or the simplifier.

- **Controls row (board 193-215):**
  - **Field:** a `Segmented` of the base fields for the result.
    - 2D: `Overpressure · Density · Speed`, plus `Peak · Impulse` when
      `has_peak_maps`.
    - 3D: `Overpressure · Density`, plus `Peak · Impulse`, plus `Isosurface`, and a
      second `Segmented` **Plane `x-z | x-y`** (hidden for Isosurface).
    - 1D: the row is hidden (profiles only).
    - The composed choice is **exactly one string of `field_options(res, dim)`**,
      written into `field_sel`.
  - **Colours:** `Segmented` `whole run · each frame · manual` → `scale_sel`
    (`run` / `frame` / `manual`). **Min / Max** appear **only for manual**, with a
    unit suffix that follows the field (`kPa`, `kg/m³`, `m/s`, and the impulse
    map's unit from `plots.IMPULSE_LABEL`).
  - **Show mesh** at the right.
- **Colour scale — one control for both pages.** Default = the run's recorded
  `anim_scale_of(meta)`, as `AnimView` does today.
  - **Frames page** (the replay): exactly today's `AnimView` behaviour
    (`resolve_clim`, memoised, the clip note).
  - **Snapshot maps** (`FieldsView.set_scale`):
    - `each frame` = today's per-snapshot `ScalarImage.set_data(z, robust)`;
    - `whole run` = one range over all snapshots of that field: overpressure
      through `output.animation.frame_clim` (the video's own rule); density and
      speed through the finite min..max with solid cells excluded;
    - `manual` = the typed range in the field's unit.
    - The whole-run peak / impulse maps are single images: `whole run` and `each
      frame` both give today's robust autoscale, and `manual` applies.
  - Manual ranges are **remembered per field**. `min_box` / `max_box` hold the
    **overpressure** range. `export_opts()` is **unchanged**: `anim_scale` from the
    control, and `anim_clim` = the overpressure range only when manual. The
    animation export therefore uses the chosen colour scale, as today (plan §10:
    "assert on the export options").
- **Map area:** a stack showing the `FieldsView` page (image, matplotlib figure or
  hint) or the `AnimView` plot. The colour bar and title come from the engines.
  - **No gauge markers on the map.** R3 pins "Fields draws no gauge markers" (the Tk
    rule), although the board draws two. That is a decision row.
  - The colour bar stays **linear** (the board says `kPa, log`; plan §7 does not ask
    for it). That is a decision row.
- **Hover readout** (board 252-254): over the map, a small `TextItem` reads `r 1.87 ·
  z 1.06 m` over `overpressure 21 kPa`. The axis names follow the page's labels
  (`x · y`, 3D plane axes). The value is the **displayed cell**: `ScalarImage.value_at`
  finds the face interval by `np.searchsorted` on `xf` / `yf` and reads the masked
  array on screen, with no interpolation. A solid cell reads `solid`; outside the
  domain the readout hides. It is not shown on the matplotlib pages.
- **Time bar (board 262-283),** under the map:
  - Play/Pause, a 40 px round `accent` button with an `on_accent` glyph;
  - the time in Space Grotesk 15 (`4.90 ms`);
  - the slider with **cyan ticks**;
  - `6.31 ms · 61 frames` in mono `faint`;
  - the speed `0.25× 0.5× 1× 2× 4×`, today's `SPEED_FACTORS`, default 1×;
  - **This frame .png**.

  The timeline is:
  - **Overpressure with recorded frames** (2D/3D): the **recorded frames**. The
    time bar drives `AnimView` (its `slider`, `start_play` / `stop_play`,
    `speed_sel`). The label counts `frames`, and the time is `frames['times'][k]`.
  - **Otherwise** (Density, Speed, or Overpressure without frames): the
    **snapshots**, in `snap_sel` order. Play steps them with the same tick and
    speed rules. The label counts `snapshots`, and the time comes from the snapshot
    label's `t = … ms` (the label itself when it does not parse).
  - Switching between the two keeps the time: the nearest frame or snapshot is
    chosen.
  - Whole-run maps, 1D profiles and the isosurface have **no time bar** (hidden,
    with the caption saying why).
  - **Ticks:** at the **selected gauge's** arrival (`summarize_trace` `arrival_ms`
    of `ResultsPanel.selected_gauge()`, T5), at the nearest timeline position, in
    `gauge`. There is no tick when the arrival is NaN.
  - The caption under the view (board 285): `Cyan tick on the time bar: arrival at
    G2. The colour choice here is also the one the animation export uses.`
- **This frame .png:** a `save_file` dialog in the model folder proposing
  `<prefix>field_<field>_<t>ms.png`. It builds **one matplotlib panel** with
  `plots._panel_grid_figure([(time label, z)], …)` — the Tk Fields view's own
  single-panel call (`blastlab/gui/results_panel.py` ~line 595), for both frames
  (`z` = the frame's overpressure in kPa) and snapshot maps.
  - The on-screen range (whole run / manual) is set on the panel's `QuadMesh`
    (`set_clim`); `each frame` keeps the builder's own.
  - The title is `plots.titled(...)` with the user's title. Save at dpi 150 with
    `bbox_inches='tight'` (the `pngs` export's settings).
  - It runs on a worker with the T3 busy strip on the button. No pyplot.
- **Views:** `Field · Gauges · 3D`. The 3D view is the embedded host, unchanged.
  `show_view('Fields')` and `show_view('Animation')` select `Field`.

**Acceptance (S6, offscreen):**
- **Field replaces both old tabs:** `VIEWS == ('Field', 'Gauges', '3D')`; the tab
  strip has three tabs; `show_view('Animation')` → `view() == 'Field'`.
- For 2D native with frames (`result('2d')`), 2D with none, 3D (`fake_3d`) and 1D,
  the composed Field / Plane choices give **exactly** `field_options(res, dim)`,
  compared as sets and as a bijection.
- Timeline: on overpressure with frames, the time bar max is `len(frames)-1`, and
  moving it calls `AnimView.show_frame` once per move (R5's rule). Density switches
  to snapshots with the label `… · N snapshots`. Back on overpressure, the frame
  nearest the snapshot's time is chosen. There is no time bar on peak maps, 1D or
  isosurface (`isHidden()`).
- **Colour scale drives the export:** set `manual` with (0, 50) through the
  **visible** control and boxes, and `p.export_opts() == {'show_mesh': …,
  'title_extra': …, 'anim_scale': 'manual', 'anim_clim': (0.0, 50.0)}`. Then run
  `test_ui_char_results_exports` with `drive_visible`: the golden is byte-identical
  to T0's.
- Snapshot scale: `each frame` gives the levels today's `set_data` gives (R3's
  `(1.2, 2.2)` for density). `whole run` on density gives `(min, max)` over the
  snapshots, computed in the test. A manual density range does not change
  `export_opts()['anim_clim']`.
- Hover: at the scene point of a cell centre (i, j), the readout value equals the
  displayed array at (i, j), formatted. A solid cell reads `solid`. Outside, it is
  hidden.
- Ticks: the tick sits at the timeline index nearest `arrival_ms` of the selected
  gauge, and selecting another gauge in Gauges moves it.
- **This frame .png** (dialog patched to a temp path, `threaded=False` path in the
  test): one PNG > 5 kB, whose figure has one axis. The QuadMesh clim equals the
  on-screen range in `manual`.
- `test_ui_no_mpl_pyplot` (with the view names updated) proves no pyplot is imported
  while every view is drawn and the replay plays.

#### T7 · 7b verification: §10 acceptance, screenshots, viewer, harness, report — size M

- **Plan §10 made concrete, all four:**
  1. *"The three views work on a native 1D and a native 2D result"*: S5 and S6 plus
     a real-platform e2e **`blastlab/tests/_e2e_ui_results.py`**. It uses
     throwaway settings (`ensure_qapp(offscreen=False)`, `use_model(win)`) and runs
     a real tiny native 1D case and a native 2D axisymmetric case with
     `record_frames` through the MainWindow. On each result it:
     - walks Field (every field, the time bar played for 1 s, a hover, This frame
       .png), Gauges (a row click, Copy) and 3D (the placeholder for 1D and 2D);
     - asserts no uncaught exception and every page drawn (`page()` in `image` /
       `figure`).
     A native 3D result (the harness's `N3D` size or smaller) is fed to the 3D view
     only if memory allows (check free commit first; if it fails for memory, run it
     alone and say so).
  2. *"Field replaces both old tabs (the animation export still uses the chosen
     colour scale — assert on the export options)"*: S6.
  3. *"Copy table puts tab-separated text with headers on the clipboard"*: S5 and
     the e2e (real clipboard).
  4. *"Exported CSV/TSV are byte-identical to before for the same result"*:
     - `test_ui_char_results_exports` (T0's golden, recorded at base) passes with
       **both** `drive` and `drive_visible`;
     - `test_char_exports` passes;
     - the e2e exports Summary, Gauge traces, Field snapshot and Profile of its
       real 1D and 2D results **through the new buttons** and compares the sha256
       of each file with `ui.exports.export(kind, ent, threaded=False)` run at
       base `c8a04d2` on the **same Result object** (pickled to the scratch dir
       and exported by a base-worktree subprocess). **Equal, byte for byte.**
- **Real-platform screenshots**, dark **and** light, at **1100 × 720** and **1600 ×
  1000**, to `docs/qa/2026-09-29-gui-results/`:
  - Field on a native 2D result: overpressure mid-replay with the time bar and a
    tick, manual scale with Min/Max, and a hover readout (move the mouse with
    `QTest.mouseMove` on the view's viewport);
  - Gauges with a row selected (shading, readout) and a planar result (no Z column);
  - 3D with a native 3D result in the embedded viewer;
  - the export column with a real Animation export busy;
  - 1D Field (profiles) and 1D Gauges;
  - the method card of a native and of a blastFoam-shaped result.
  - Write `measurements.md` against the board: column widths, button and strip
    heights, the time-bar row, the table at 1100 × 720 (header wrap, horizontal
    scroll?), and **contrast ratios by script** for every new text pair in both
    modes (`faint` on `panel`, `accent_soft` on `accent_bg`, grey curve on `tile`,
    `warn` on `card`, the readout on `tile`), each ≥ 4.5 (3.0 for non-text
    curves), per plan §2.2.
- **Embedded 3D viewer re-measured** with the committed sampler (T4), on the real
  platform, a native 3D result in Results → 3D, pre-registered in
  `measurements-7b.md` **before** the run:
  - **R-VIEWER:** 0 ms longest wrong-place stretch over ≥ 500 samples with a
    viewer window, for: Open the 3D viewer; the view tabs Field ↔ Gauges ↔ 3D; a
    result change; an export busy strip; `set_stage_strip` show / hide; Setup ↔
    Run ↔ Results; a theme toggle.
  - **R-VIEWER-RESIZE (F13):** the median over three 1600 → 1100 → 1600 repeats is
    ≤ base + 5 ms (the same A/B as T4).
  - Save `viewer_measure_7b.json`. A failure is fixed or reported with its number
    and action (plan §11).
- **Harness**, offscreen, own settings, one run at a time:
  - `--scenario B01,D01,D02,E01,E02,E03,E04,E07,E08,E09,I01`;
  - then `D04,E05,E06` alone (the native 3D run, about 11 min; check memory
    first; a `MemoryError` gets an A/B at base).
  - The truth is `findings.jsonl`. List every finding against GUI-6's run.
- The full fast matrix of T4 again, one suite at a time.
- Report: `2026-09-29-gui-results-b.implement.md`, decision rows continuing after
  7a's last id.

---

## Committed assertions: what may change (plan §9)

**May be updated, because the owner replaced this layout. List each one in the
report with its reason and the old and new line:**
- `test_ui_results.py`:
  - **R1** `_export_row.rows() > 1` and the WrapRow cut check (the export row is
    gone) → the same "no label cut off" measured in the new column at 1280 × 840
    and 900 × 600. The `'Select a result first.'` tooltip check is unchanged.
  - **R3** `f.image.levels == (1.2, 2.2)` → the same assertion after
    `p.set_colour_scale('frame')` (today's per-snapshot scale is now the explicit
    `each frame`; the default follows the run's recorded scale). Every other R3 check
    is unchanged.
  - **R4**:
    - the column-count check `== 8 == len(gauge_summary.COLUMNS)` → `9 ==
      len(gauge_summary.COLUMNS) + 1`, with the extra column Z;
    - `HEADERS[1] == 'Peak ovp [kPa]'` → the board's `Peak [kPa]`;
    - `g.canvas.height()` → the plot widget's height (same rules);
    - `fig.axes[0].get_ylabel()` → the pyqtgraph left axis label (the **same
      strings**);
    - "the rows are the shared summary formatting" → per gauge number, every
      numeric cell equal to `table_rows` (**not weakened**: every number is still
      compared).
  - **R5** `p.show_view('Animation')` → `'Field'` (or kept through the alias).
- `test_ui_parity.py` P5: "all eight summary headers" → nine (with Z); the 8 export
  buttons check is unchanged.
- `test_ui_no_mpl_pyplot.py`: the view names `('Fields', 'Gauges', 'Animation',
  '3D')` → `('Field', 'Gauges', '3D')` (or kept through the alias). The pyplot rule is
  unchanged.
- `test_ui_char_results_meta.py` + `char_golden/ui_results_meta.json`, **only**:
  - `gauges.figure` (the matplotlib grid, no longer on screen) → `gauges.traces`
    (the sha1 of each curve's `column_stack((x, y))` as float64, by
    `char_meta_results.digest`);
  - the `missing/*/<key>/gauges` short hashes;
  - `anim` / `fields` access paths, if a hidden widget moves (the recorded values
    stay).

  Before overwriting with `--update`, a one-off migration script (kept in the
  scratch dir, pasted into the report) must show two things:
  - **(a)** for every fixture, `traces[k]` equals the **old** golden's
    `figure.axes[k].lines[0]` — the numbers on screen are the numbers the old
    figure plotted;
  - **(b)** a JSON diff of old vs new has **no changed path** outside those listed,
    and every `missing/*/<key>/gauges` keeps its class (`ok …` stays `ok …`, a
    `raises …` text is identical).
- `_qa_ui_harness.py`: navigation and widget-path helpers only.
  - `show_view` names in E01/E04/I01;
  - `rs.gauges.canvas.height()` → the plot's height in E03.
  - No scenario logic changes.

**Must NOT change** (run each before and after):
- `test_regression.py` (byte) and every fixture under `tests/baseline/`,
  `foam_fixtures/`, `foam_golden/`.
- `test_char_exports.py` with `exports_qt.json`, `exports_can.json`,
  `test_ui_exports_reexports_services` (the re-exports stay the same objects — patch
  `ui.exports.run_export` only inside a test and restore it).
- `test_ui_char_results_exports.py` (T0's golden, recorded at base).
- `test_ui_results_vtk_folder.py`, `test_gauge_summary.py`, `test_report.py`,
  `test_anim_scale.py`.
- Every other golden in `tests/char_golden/` and its suite: `test_ui_char_hd13_run`,
  `test_ui_char_write_failure`, `test_ui_char_case_form`, and the Tk `test_gui_char_*`.
- The behaviour halves of `test_ui_results`: R1 duplicate / elide / tooltip; R2
  the enable and why-not matrix and native hiding; R3 field lists, image reuse,
  whole-run title, clip, no gauge markers, mesh; R5 frames, one redraw per move,
  the title edit keeps the frame, speeds, whole-run range, manual, fallback, export
  options, memoisation, recorded scale; R6 prefixes and PNG grid; R7 threading; R8
  Remove; the 3D feed checks.
- `test_ui_run_screen` (168+), `test_ui_frame` (F5, F6, F7, keys label),
  `test_ui_parity` P1 and P6, `test_ui_three_surfaces`, `test_ui_view3d_host`,
  `test_ui_drain`, `test_ui_live_gauges`, `test_ui_chain`, `test_ui_setup_*`.
- `test_ui_no_vtk_in_main.py` and `test_ui_no_mpl_pyplot.py` (the new modules import
  neither).
- Shared neutral modules are **not edited**: `core/`, `services/`, `models/`,
  `solvers/`, `output/`, `viz3d/`. So the Tk suites do not trigger. If one must be
  edited after all, run every `test_gui_*` and say why.

---

## Decision rows to append (the recommended defaults taken; D76 onward)

These are the non-blocking questions. Append them to
`docs/gui-redesign-decisions.md` as they are settled, and add any new ones:

1. **Split** GUI-7 into 7a/7b (as D14, D42).
2. **Method card sources:** `res.meta`, `res.stop_reason`, and the record files
   `res.meta` names (`model_dir` → `MODEL.json` + `manifest.json`; a loaded run's
   `case_dir` → `case.json`). Nothing else, nothing defaulted. No solver version is
   recorded anywhere, so none is shown. Suggested: record `blastFoam 6.2.0` in the
   manifest (an OUT-track change).
3. **Detonation / Afterburn** rows only for blastFoam results (hide, never grey).
4. **List caption duration** = `manifest.finished − manifest.created`, hidden
   without both. It includes the model-folder writes (cf. D59).
5. **Load into 01 Setup** loads a new, unsaved case (no path; Ctrl+S → Save as), so
   the model folder's `MODEL.json` is never overwritten. It asks only when Setup is
   dirty.
6. **Show case** is a non-modal read-only viewer with Copy.
7. **Field architecture:** `FieldsView` / `AnimView` stay the engines with their
   old controls hidden; the new controls drive them (placement, not engines).
8. **Timeline:** recorded frames for Overpressure when the result has them;
   otherwise snapshots. No time bar on whole-run maps, 1D profiles or the
   isosurface.
9. **Colour scale on snapshot maps:** whole run (overpressure through `frame_clim`;
   density and speed min..max), each frame (today's), manual (per field, in its
   unit). Default = the run's recorded scale. The export carries only the
   overpressure choice, as today.
10. **Field control:** a base-field Segmented, plus a Plane Segmented in 3D,
    composing exactly `field_options`.
11. **Arrival ticks:** the selected gauge only (plan §7's text), not the board
    caption's two gauges.
12. **No gauge markers on the Field map** (R3's Tk rule) although the board draws
    them. It is the owner's call to reverse.
13. **Linear colour bar** kept; the board labels its bar `kPa, log`.
14. **Gauges on pyqtgraph** (the on-screen rule); the exported gauge figure is still
    the matplotlib grid. Screen and file differ, and the tooltip says so.
15. **Table order by Z** (D61), `G<n>` with the full label in the tooltip. The Z
    column is hidden when Z is (rows then by number).
16. **Readout strings = the table's** (peak `231.4`, not the board's `231`).
17. **Positive-phase shading only for the pressure trace.**
18. **Copy table** = the on-screen text: tab-separated, `\n`, visible columns and
    headers with units.
19. **Busy state** is an indeterminate `writing…` for every kind. A percent for
    the animation needs a progress hook through `services.exports.run_export` (a
    shared module, the Tk gate) — owner's call. The same kind cannot start twice;
    other kinds may run; Remove is allowed.
20. **Export labels:** `Gauge traces .txt` (the file is tab-separated `.txt`; its
    name is pinned), `Field snapshot .csv` kept, although it writes one CSV per
    field; the Animation suffix follows `default_ext()`.
21. **Open the 3D viewer** is disabled with a why-not for non-3D results (it was
    enabled and only logged).
22. **The VTK `on_error` dialog** is posted to the GUI thread (it was shown from the
    worker thread).
23. **Status-bar footer** is unchanged on Results (the board's `Ctrl+C copy table`
    hint is in the Copy button's tooltip; `test_ui_frame` pins the label).
24. **Narrow widths:** the side columns give way (280 → 248, 320 → 288) only when
    three do not fit, table headers wrap, and the table scrolls horizontally
    rather than clip.
25. **F14:** the cause found (fill in), the guard and the `destroyed` hook.

---

## Risks

1. **Numbers on screen** (the Gauges plot, table, readout, Z, ticks, hover). Guard:
   every value comes from `gauge_summary` (`summarize_trace`, `summarize_gauges`,
   `table_rows`), the `plots.GAUGE_FIELDS` transforms, `scaled_distance`,
   `select_field` and the engines; S5/S6 compare against those functions called in
   the test, never literals; the char-golden migration proves the plotted curves
   equal the old figure's line data; `test_regression` after every commit; no
   `output/`, `services/` or solver file is edited.
2. **Export bytes (§10).** Guard:
   - T0's golden is recorded **at base, before any change**, through the panel's
     own `export()`; `exports_qt.json` stays byte-identical;
   - the busy wrapper calls the same `run_export` with the same arguments;
   - `drive_visible` proves the new controls feed the same `export_opts`;
   - T7 cross-checks real results against a base worktree.
3. **Two sources for one picture.** The hidden legacy widgets and the new controls
   can drift. Guard: sync both ways, and S6 drives the old widgets (as the char
   golden and the harness do) and asserts the new controls follow, and the
   reverse.
4. **The embedded 3D viewer** now sits between a 280 and a 320 px column, under a
   stage hook, beside a right column whose busy strips appear. Guard: the committed
   sampler, twice (T4, T7), 0 ms pre-registered for everything except the
   pre-existing resize lag, which has its own A/B rule (F13).
5. **`Load into 01 Setup` could overwrite the record of a run.** Guard: `_case_path
   = None`, and S2 asserts `MODEL.json`'s sha256 after a save.
6. **Ctrl+C scope.** A window-wide Ctrl+C would break copy in every text box.
   Guard: a widget-scoped shortcut on the table, plus the S5 negative check.
7. **Threads.** The export `on_done` / `on_error` run on a worker. Guard: posted
   through `ThreadBridge`; S3 asserts the GUI thread.
8. **Memory on this 8 GB PC.** `test_ui_char_results_meta`, `test_char_exports`
   and the T0 test each solve native 1D/2D/3D. A 3D run with the viewer child can
   exhaust memory. Guard: one suite at a time, free-commit check before the real
   runs, a `MemoryError` re-run with an A/B at base, all reported.
9. **Modal hazards for unattended drivers.** Show case is non-modal. The
   Load-into-Setup question goes through the already-patched
   `dialogs.ask_yes_no`, and *This frame .png* through `dialogs.save_file`. No new
   unpatched modal is added.
10. **Session safety.** Run the CLAUDE.md §8.2 dry run before building any
    MainWindow (expect `False` and an empty plan). Throwaway settings everywhere
    (`private_settings()`, `ensure_qapp()`), and `use_model()` for every real run. No
    WSL run is needed; if one happens anyway, `wsl -d Ubuntu -- pgrep -a
    blastFoam` must be empty first (§8.6).

## Needs clarification

Nothing blocks. Every open question has a default in "Decision rows" above, for the
owner to review the next day (the owner's 2026-09-28 instruction).

## Implementer rules (binding)

- **Never stage** these six paths: `docs/references/INDEX.md`,
  `docs/references/ViperTheoryManual_Client.pdf`,
  `docs/references/ViperTheoryManual_Client.txt`,
  `docs/references/viper_vtk_sample/`, `docs/qa/2026-09-27-out-3/`,
  `docs/qa/2026-09-27-viewer-polish/`. **Stage by explicit path**, one `git add <file>` each. Never `git add -A`,
  `git add .` or `git commit -a`. Check `git status` before every commit.
- **No PowerShell string round trips** on any file (CLAUDE.md §8.1). Use Read, Edit
  and Write only, even for one-liners.
- **A new commit-message file per commit**, written with Write in the scratch dir
  (never reused, never in the repo), then `git commit -F <file>`. Style `ui: <what
  changed> (GUI-7)` / `tests: … (GUI-7)` / `ui: … (F14)`. The message ends with the
  trailer:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  At least one commit per task. Never push. `TODO.md` and `DONE.md` are updated by
  `/todo`, not here.
- **Throwaway settings for every MainWindow** (`ui.testing.private_settings()` or a
  temp `BLASTLAB_SETTINGS`), the harness and the e2e included. `auto_cleanup` stays
  off. Run the §8.2 dry run first.
- **Real platform for geometry, embedding and screenshots:**
  `ensure_qapp(offscreen=False)` with `QT_QPA_PLATFORM` unset. Win32 through ctypes
  is the ground truth, not Qt's `geometry()`.
- **Heavy suites one at a time on this 8 GB PC.** Check free memory before a
  real-platform run, a 3D solve or the char suites. Never run two MainWindow suites
  in parallel.
- **Process hygiene:** never a broad kill (no `taskkill /FI "WINDOWTITLE eq *"`, no
  kill by image name, no `Stop-Process -Name python`). At the start, list the running
  `python` processes with their command lines and record their PIDs as **foreign**.
  Stop only processes this batch started, by their PID, including viewer children
  and base-worktree subprocesses your scripts spawn. Leave every foreign
  `python -m blastlab` alone. After each real-platform run, check that no viewer
  child or tray icon of yours is left behind.
- **Do not edit** `blastlab/gui/` (Tk), `core/`, `services/`, `models/`, `solvers/`,
  `output/`, `viz3d/`, the regression fixtures, solver defaults, or
  `run_controller.py`'s handler protocol.
- **Base worktree** for A/B runs (T1's failing test, T4/T7 viewer A/B, T7 export
  cross-check): `git worktree add <scratch>\base c8a04d2`. Remove it when done
  (`git worktree remove`). Never check out the base in the main tree.
- **References:** `docs/references/INDEX.md` has been read for this plan. Only
  **ufc-3-340-02** applies:
  - the scaled distance Z = R/W^(1/3), para. 2-13.1, printed p. 44 (PDF p. 120), is
    already cited in `ui/scaled_distance.py` (D24). Reuse the helper and add no new
    formula;
  - the positive and negative phase and their impulses, para. 2-12 (Blast-wave
    phenomena, Figure 2-2), printed p. 43 (PDF p. 119, `=== page 119 ===` in the
    `.txt`), are the meaning behind the shading and the "net impulse includes the
    negative phase" caption. If a comment cites it, use `UFC 3-340-02 (2008), para.
    2-12, printed p. 43`.

  The blastFoam guide, the LLNL handbook and the Viper manual are not needed: no
  case file is written or parsed, no material constant is read, and no solver
  method is compared.

---

## Remaining backlog after this batch (one line each)

- **GUI-9**, the Chain screen: routes, pipeline, stage editor on the Setup layout,
  and per-stage validation. It fills `RunPanel.chain_slot` (GUI-6 T8) and
  `ResultsPanel.stage_slot` (this batch, T2) and makes a chain one result
  (`ResultEntry.kind = 'chain'`, `stages`). L.
- **GUI-10**, the QA pass: the harness on the new frame, all scenarios, light
  mode, 1100 × 720, F8 (`num_dim` contrast), F10 (B06 with `--window`), F12 (the 0-D
  Run toolbar), and removing the hidden legacy Results widgets this batch lists. M.
- Found in earlier batches, not fixed, one small batch after GUI-10: F2 (1 px
  preview column), F3 (point tables too wide), F4 (axisymmetric headers `x y`),
  F5 / F13 (viewer resize lag), F6 (`_e2e_ui_view3d` on the home PC), F7
  (validation errors not mapped to tree nodes), F9 (no viewer on a second 3D
  start), and the owner's answers to D71-D75.
- Other tracks, unchanged by this batch: OUT-4 (the owner's ParaView look is
  pending), HD1-17b (blocked on owner input), HD1-18, P1-15, the owner-decided P1
  fixes P1-8 to P1-14 and P1-16, and the P2 items.
