# Verification — batch 2026-09-29-gui-results (GUI-7, parts 7a and 7b, and F14)

Plan: [`2026-09-29-gui-results.md`](2026-09-29-gui-results.md). Reports checked:
[7a](2026-09-29-gui-results-a.implement.md), [7b](2026-09-29-gui-results-b.implement.md).
Range reviewed: `b8bc577..8b5bfea` (7a `bb065fc..6b12a38`, 7b `f38351f..8b5bfea`),
against the base `c8a04d2`. Branch `gui-redesign`. Verifier run: 2026-09-29,
the 8 GB home PC.

**Verdict: ready for QA.** Every task meets its criteria. Review fixed seven
things in seven commits; one pre-registered rule (R-VIEWER-RESIZE, F13) stays
failed and reported, as the batch instruction says. Six decision rows
(D125-D130) and one F-row (F17) are for the owner.

## Ground rules kept

- CLAUDE.md §8.2 dry run first: `<repo>\settings.json False []`.
- Throwaway settings for every MainWindow: `ensure_qapp` (it calls
  `private_settings()`), the harness's own `BLASTLAB_SETTINGS`, the e2e's
  and the sampler's.
- Heavy suites one at a time. Free commit was 1.7-2.3 GB during the run.
  No run hit a `MemoryError`, so nothing had to be re-run for memory.
- Processes: PID 29568 (`python -m blastlab`, not mine) was there at the
  start and was left alone. I stopped no process by hand. The sampler's viewer
  child (PID 43140) and the e2e's closed with their windows. **PID 29568
  was no longer running at the end.** It was still there at my memory
  check just before the lone I01 re-run (about 20:05); after that I ran
  I01 and two e2e passes, none of which stops anything but its own viewer
  child by its handle. I did not stop it, and nothing in those scripts
  targets another process (`grep` for kill / taskkill / single-instance
  code finds only the sampler's own child). It may have been closed by the
  owner, or died of the same memory pressure that broke the first I01 run
  (a native 3D solve on an 8 GB PC with about 2.3 GB of free commit).
  Worth a look if it was not closed on purpose. At the end no python process of mine was left.
- Base worktree `<scratch>\vbase` at `c8a04d2` for the F14 and T0 base
  runs and the e2e cross-check; removed at the end (`git worktree list`
  shows only the main tree).
- Not staged: `docs/references/INDEX.md`, the Viper manual files,
  `viper_vtk_sample/`, `docs/qa/2026-09-27-*`. Staged by explicit path.
- Tk untouched. No shared neutral module was edited by the batch or by
  review: `git diff --stat c8a04d2..HEAD` over `core/ services/ models/
  solvers/ output/ viz3d/ gui/` and the three fixture folders is empty, so
  the Tk gate did not trigger.
- Every repo edit went through Edit/Write. One slip, caught and repaired:
  my first commit picked up a stale `msg1.txt` from an earlier session in
  the scratch dir (the Write of the new message had failed), so it carried
  a GUI-6 message; I amended my own, unpushed commit with the right one
  (`10ed2ca`). Every later message file has a unique `g7v_` name.

## References (UFC 3-340-02, the only one that applies)

- **Para. 2-12, printed p. 43** (`=== page 119 ===`): "the incident
  pressure decays to the ambient value in time to, which is the positive
  phase duration. This is followed by a negative phase ... The incident
  impulse density ... is the integrated area under the pressure-time curve
  and is denoted as is for the positive phase and is- for the negative
  phase." That is exactly what `results_gauges.py`'s docstring cites it
  for (the shading, and "net impulse includes the negative phase").
  Citation correct.
- **Para. 2-13.1, printed p. 44** (`=== page 120 ===`): "versus the scaled
  distance (Z = R/W1/3)". `HEADER_HELP['z']` cites 2-13.1; the value comes
  from `scaled_distance.scaled_distance`, the helper of D24 (no new
  formula: `case_from_meta` only builds a case-like object from meta).
  Correct.
- The Z column is display only; no Kingery-Bulmash curve is evaluated, so
  Figure 2-7's range (Z 0.136-100 ft/lb^1/3) does not bind it.
- Units through the chain: the table's impulses are `gauge_summary`'s
  Pa·s numbers, unchanged, under a kPa·ms header. 1 Pa·s = 10⁻³ kPa ×
  10³ ms = 1 kPa·ms, so the number is right (my probe: G1 pos. impulse
  130.7286 Pa·s shown `130.73` [kPa·ms]). Overpressure curves and maps are
  `(p − P_AIR)/1e3` [kPa] through `GAUGE_FIELDS` / `frame_clim`, the
  exporters' own transforms.

## Fixes made in review

| Commit | Task | What |
|---|---|---|
| `10ed2ca` | T2 | The results list stayed at its two-row minimum with the column half empty, so from the third result on the newest (selected) row was below the fold (every 7b screenshot shows the fourth row cut). The list now takes its rows' height when it can, scrolls only when it cannot, and keeps the selected row in view. The selected row's caption is `muted`: `faint` on `accent_bg` was 4.47:1 in light mode. D125. |
| `e5de7ed` | T5 | S5f's "the table scrolls sideways rather than clip" tested `maximum() >= 0`, always true. Now `> 0` (384 px). |
| `fbb5ef5`, `f7cb4fc` | T6 | The hover readout was cut off near the right/top edge of the map (`overpressure 1944 kP` in the 1100 × 720 shot). My first fix chose a side by the view's midpoint; re-shot on the real platform, it was still cut (a narrow map has room on neither side). The second places it like a tooltip, slid to stay 2 px inside the view box; the real-platform re-shot reads `overpressure 1944 kPa` in full. D126. |
| `b4cad6e` | T6 | The on-screen 1D profiles at 1100 × 720: 15 texts outside the 406 px canvas. The on-screen copy is re-laid out at every draw (`tight` engine); exports unchanged. D127, F17. |
| `db5657c` | T2 | Load into 01 Setup left the last run's `✓ Done ·` in the title (D68 clears it when a case is opened). D128. |
| `d7b614d` | T5 | A failure to build the gauge curves read "This result has no gauges.", a silent failure dressed as data. It now says `Could not draw the gauges: <why>`. D130. |

Each fix has a check in `test_ui_results_screen.py` that fails on the
code before it (shown by stashing the fix): S2b list 3/3 rows need no
scroll (before: scroll range 34 px), S6f corner readouts `[True, True,
False, False]` → all True and the middle-row sweep at 900 × 600 (cut at
cells 44-64 under the midpoint rule → none), S6b 1D ticks (4 outside →
0), S2d Done mark, S5e failure text. S5f is itself the test fix. The one
exception is the list's selected-caption colour, checked by value.

## Per task

### T0 · Pin the Results panel exports — VERIFIED

- `bb065fc` holds only the test and its golden. The golden and `drive()`
  are unchanged since (`git diff bb065fc..HEAD` over both is empty; the
  test only gained `drive_visible` and its test).
- **At base:** the `bb065fc` test and golden copied into a `c8a04d2`
  worktree: `CHAR UI RESULTS EXPORTS: PASS` (both tests). So the golden
  is the base's output.
- **At HEAD:** `CHAR UI RESULTS EXPORTS: PASS` with `drive`, with
  `drive_visible` (not a writer) and `test_same_bytes_as_exports_qt`
  (summary / tsv / fieldcsv / profile equal to `exports_qt.json`).
- `test_char_exports`: PASS. `test_regression`: PASS (byte).

### T1 · F14 — VERIFIED

- `test_ui_fieldform_viewport.py` in the base worktree: `FAILED: 8 of 11`,
  with F14's exact `RuntimeError: ... showEvent(): libshiboken: Internal
  C++ object (PySide6.QtWidgets.QWidget) already deleted.` At HEAD: PASS
  (11 checks).
- **R-F14:** `test_ui_run_screen` 10 of 10 PASS (168 checks each),
  sequential, nothing else running. No MemoryError.
- The fix: the `isValid` guard, the `destroyed` hook with its disconnect
  on a move, `eventFilter` compares identity only. The cause was not found
  (D88); the report says so honestly. The guard covers both candidates.
- Setup suites green and unchanged (matrix below).

### T2 · Three columns, list, method card, stage hook — FIXED

Criteria, re-run (S2 of `test_ui_results_screen`, now 181 checks, and my
probes):

- 280 / 968 / 320 at 1600 × 1000, 280 / 468 / 320 at 1100 × 720; nothing
  clipped at 1100 × 720 in both modes with 12 results, nor on the
  900 × 600 panel: PASS (and my own probe after the list fix: `clipped`
  empty in all four cases, the left column never scrolls as a whole).
- `run`, `run #2`, the combo surface, `latest` on the newest only, the
  middle elision with the full ToolTipRole: PASS.
- **The list's height: FAIL at 8b5bfea, fixed in `10ed2ca`** (see above).
  Probe before: 3 rows → list 106 px, scroll range 34, selected row not
  visible; after: 161 px, no scroll, visible; 12 rows at 1100 × 720 →
  331 px, scrolls, the selected row visible.
- `method_rows`: the three fixtures equal rows built in the test; no
  `None` / `nan` / `?`. Reviewed the rule line by line in
  `results_method.py`: every row is read from `res.meta`,
  `res.stop_reason`, `MODEL.json` / `case.json` (raw JSON, so no dataclass
  default leaks in) or `manifest.json`; Detonation / Afterburn only for a
  blastFoam result whose case file holds the key; nothing is guessed. The
  real foam meta does carry `refine` with `lmax` and `dx_base`
  (`writer.refine_meta`), so reading it from meta (D90) is right. The
  native Charge row's material comes from MODEL.json, and the native
  solvers do use it (`solve_2d(... material=case.material)`).
- Show case: non-modal, text = the file's bytes as UTF-8, Copy: PASS.
  Disabled with the why-not tooltip without a case file: PASS.
- Load into 01 Setup: Setup = `load_case(MODEL.json)`, no path, dirty,
  `MODEL.json` sha256 unchanged after Ctrl+S (Save as cancelled), asked
  once when dirty, Keep editing changes nothing, a relative
  `profile_file_in` resolves against the model folder: PASS. Save as
  offers no start path, so nothing steers the user into the model folder.
  **The `✓ Done` title mark was not cleared: fixed in `db5657c`.**
- Stage hook: hidden at 0 px, shown above the tabs, hidden again; the
  `shrink_ahead` call over the 3D view: PASS.
- `ResultEntry` positional plus `kind`, `stages`: PASS.

### T3 · Export column, busy state, no double start — VERIFIED

- S3 (re-run): order and grouping, suffixes (`profile` .txt/.npz,
  `gif` = `default_ext()`), 40 / 42 px, labels fit, `clipped` empty,
  VTK hidden in native.
- No double start with a blocking `run_export`: the strip is up, a second
  `export('summary')` returns `''` with no new writer and logs `Summary is
  already being written.`, `tsv` still starts, Remove works, both come back
  enabled, `_export_done` ran on the GUI thread twice, a cancelled dialog
  shows nothing, `run_export` restored: PASS.
- Thread safety, read in the code: the worker only calls `on_done`, which
  posts `_export_done` through the `ThreadBridge` (a queued connection);
  `on_error` is posted the same way (D85, S3 checks the GUI thread); the
  strip goes up after `exports.export` returned a target, and the queued
  done cannot overtake it. `run_export` itself is untouched
  (`services/exports.py` not in the diff).
- Open the 3D viewer's why-not tooltips; E09's title checks: PASS.

### T4 · 7a verification, sampler — VERIFIED

- The sampler is committed, runs real-platform only, samples from a child
  process with a self-test, and stops its own viewer child by handle.
- **Re-run by me on the final tree** (real platform, `--surface results
  --actions open3d,views,select,busy,stage,tabs,theme --repeat 3`): the
  self-test read 148.9 ms / 60 px for a 150 ms / 60 px displacement, and
  **R-VIEWER holds: 0.0 ms longest wrong-place stretch for all seven
  actions**, with 1055 / 1050 / 2266 / 2126 / 2140 / 1065 / 11693 samples
  with a viewer window, never not-a-child, largest sample gap 3.2 ms.
  `stage` shows a 27 ms *mismatch* (the window deliberately smaller than
  its card: `shrink_ahead`), not a wrong place. So the list fix
  (`10ed2ca`, the left column) moved nothing around the viewer.
- Rules pre-registered in `20c31c5` before the first sampled run; the
  stage `shrink_ahead` fix and its S2e pin are in `042b386`.
- 7a screenshots and measurements are in the folder.

### T5 · Gauges view — FIXED

- S5 re-run: every curve `np.array_equal` to `(times·1e3,
  GAUGE_FIELDS['p'][2](p_k))`; Z = `scaled_distance(case, entered)`
  (G1 3.31, G2 2.99 for the sample geometry); every numeric cell equals
  `table_rows` by gauge number; pens 2.4 px `gauge` / 1.2 px grey; the
  fill spans [arrival, arrival + positive duration] and follows a real row
  click; no fill for |U|; planar and profile start hide Z (eight columns);
  1D Z = r / W^(1/3); the plot stays taller than the table at 1100 × 720
  and 900 × 600: PASS.
- **Exact Copy text**, my own probe on `test_char_exports.result('2d')`,
  built from `HEADERS`, `table_rows` and `scaled_distance`: equal for the
  button and for Ctrl+C on the focused table, no trailing newline:

  ```text
  Gauge	Z [m/kg^1/3]	Peak [kPa]	Arrival [ms]	t peak [ms]	Pos. phase [ms]	Pos. impulse [kPa·ms]	Net impulse [kPa·ms]	Phase ended
  G1	0.50	2707.4	0.135	0.163	0.104	130.73	121.77	yes
  G2	0.64	1894.4	0.230	0.258	0.145	143.00	143.02	no
  ```

  It is the text 7b's report prints.
- **Ctrl+C scope:** the table catches the key in its own `keyPressEvent`
  (D105), so only a focused table sees it; S5 checks that Ctrl+C in the
  title box leaves the clipboard alone and that the panel has no Ctrl+C
  `QShortcut`; `test_ui_frame` F5 (five window keys) is green.
- **Migration proof re-run** by my own script (old golden from
  `c8a04d2`, new from HEAD): (a) 28 curves over 13 fixtures, every
  `traces[k]` equal to the old `figure.axes[k].lines[0]`, rows and field
  unchanged; (b) 0 changed paths outside `<fixture>/gauges/figure|traces`
  and `missing/*/<key>/gauges`; 130 missing-key entries, 0 class changes.
  `CHAR UI RESULTS META: PASS`.
- Fixes: S5f's always-true assertion (`e5de7ed`); the silent "no gauges"
  on a failure (`d7b614d`).

### T6 · Field view — FIXED

- S6 re-run: three tabs and the aliases; Field / Plane compose exactly
  `field_options` (set and bijection) for 2D with frames, 2D without, 3D
  and 1D; the time bar (max n−1, one `show_frame` per move, Density →
  `N snapshots` at the nearest time, back to the nearest frame, no bar on
  Peak / Impulse / 1D / isosurface); the snapshot scales (each frame
  (1.2, 2.2); whole-run density = the (min, max) computed in the test;
  manual density not in the export, per-field memory); hover = the
  displayed cell, `solid`, hidden outside; ticks follow the selected
  gauge; This frame .png (one panel, > 5 kB, QuadMesh clim = the on-screen
  range, threaded busy strip, cancel writes nothing); F15 one colour bar:
  PASS.
- **The colour scale reaches the animation export**, my probe through
  the visible Colours control and typed Min/Max: `manual (0, 50)` →
  `{'anim_scale': 'manual', 'anim_clim': (0.0, 50.0)}`, `each frame` →
  `('frame', None)`, `whole run` → `('run', None)`. And
  `test_ui_char_results_exports` with `drive_visible` reproduces T0's base
  golden byte for byte (that golden includes the gif `manual` and `frame`
  variants).
- **Hidden legacy widgets still wired**, read in the code and exercised
  by S6 (both directions) and by the unchanged R-checks that drive them:
  `FieldsView.controls` (`snap_sel`, `field_sel`) and `AnimView.controls`
  (`play_btn`, `slider`, `speed_sel`, `scale_sel`, `min_box`, `max_box`).
  `drive()` in the T0 test sets the old widgets and still gives the base
  golden.
- `This frame .png` under "each frame" passes no range (`resolve_clim`
  gives None), so the builder keeps its own, as planned.
- Fixes: the hover readout at the edges (`fbb5ef5`, `f7cb4fc`); the 1D profiles at
  1100 × 720 (`b4cad6e`).

### T7 · 7b verification — VERIFIED, with R-VIEWER-RESIZE reported

- §10 (1)-(4): S5, S6, the T0 golden with both drivers, `test_char_exports`,
  and **the e2e re-run by me** on the real platform with the base worktree
  (`_e2e_ui_results.py --base-worktree <scratch>\vbase`, without
  `--with-3d`): `E2E UI RESULTS: PASS (39 checks)`. Three real native runs
  through Run; Field (every field, 1 s of replay, the real pointer's hover,
  This frame .png), Gauges (a row click, Copy on the real clipboard) and
  the 3D placeholder on 1D and 2D; no uncaught exception, no error
  dialog. Summary, Gauge traces, Field snapshot and Profile of the real 1D
  and 2D results, written through the new buttons, **equal the base
  `c8a04d2`'s export of the same pickled Result, byte for byte** (1D: 1 +
  1 + 10 + 1 files; 2D: 1 + 1 + 8 files and the `.npz` array by array).
- **R-VIEWER-RESIZE (F13): FAIL in the judged pair, reported, not fixed**,
  per the batch instruction: base 18.5 ms, HEAD 25.4 ms, rule ≤ 23.5 ms.
  `view3d_host.py` is not in the diff (`git diff --stat c8a04d2..HEAD --
  blastlab/ui/view3d_host.py` is empty), so the lag is F13's own; the
  report's four extra pairs and pooled medians (19.6 vs 24.1 ms) are in
  `measurements-7b.md`.
- Harness, re-run by me offscreen with its own settings
  (`--scenario B01,D01,D02,E01,E02,E03,E04,E07,E08,E09,I01`): exit 0, 39
  `ok`. B01-E09: no finding. **I01 hit a `MemoryError`**: the native 3D
  run failed with `_ArrayMemoryError: Unable to allocate 5.47 MiB`, and
  the 17 `qt-message` findings (QPainter not active, a null QImage) and one
  black capture that followed come from the same exhausted memory (free
  commit about 2.3 GB, a foreign `python -m blastlab` resident). **I01
  re-run alone: clean** — the run finished (10 min 31 s), largest UI gap
  1.8 s, no `findings.jsonl`. Environment, per the plan's memory rule. The
  implementer's D04 / E05 / E06 run (the 3D view with the viewer) was not
  repeated; the sampler run above exercised the embedded viewer on a 3D
  result.
- 40 screenshots, looked at against the board (below).

## The two assertion changes outside the plan's list: ruling

Plan §9 lets a layout pin change; behaviour may not weaken.

1. **`test_ui_results` R8** — `p.gauges.canvas.figure is not None` →
   `p.gauges.page() == 'empty' and 'appear here' in p.gauges.hint.text()`.
   At base the check meant "the empty Gauges view shows a message figure,
   not a bare axis" (`canvas.blank(NO_RESULT)`). The canvas is gone from
   the screen (T5); the new check asserts the same behaviour on the page
   that replaced it, and more strictly (the message text itself, which is
   `NO_RESULT`). **Kept.**
2. **The sampler's new `views` action** (`_e2e_ui_viewer_place.py`, 7a's
   own file). No assertion changed: it adds a measured action, and it is
   the action plan T7 lists for R-VIEWER ("the view tabs Field ↔ Gauges ↔
   3D"). It was committed with the rules (`416dc25`) before the first 7b
   sampled run. **Kept.**

Recorded as D129.

## Defects found in the diff

| Where | Severity | What | State |
|---|---|---|---|
| `ui/results_list.py` `ResultsList` | Medium | The list held two rows; the selected newest result hidden below the fold | Fixed `10ed2ca` |
| `ui/theme.py` `rescaption` | Low | `faint` on the selected row 4.47:1 (light) | Fixed `10ed2ca` |
| `tests/test_ui_results_screen.py` S5f | Low | `maximum() >= 0`, always true | Fixed `e5de7ed` |
| `ui/results_field.py` `hover_scene` | Low | Readout cut off at the right / top edge | Fixed `fbb5ef5`, `f7cb4fc` |
| `ui/results_fields.py` 1D page | Low-medium | Profiles cropped in the 468 px centre | Fixed `b4cad6e` |
| `ui/app.py` `_load_case_from_result` | Low | `✓ Done` left in the title | Fixed `db5657c` |
| `ui/results_gauges.py` `_draw_curves` | Low | `except Exception` → "This result has no gauges." | Fixed `d7b614d` |
| `ui/results_gauges.py` `redraw` | Low | `except Exception: self._z = None` hides Z on an unexpected error, unlogged (the view has no log) | Not fixed; D130 |
| `ui/results_field.py` `save_frame_png` | Low | Threaded with no bridge, the busy strip never comes down. The panel always passes its bridge; only a bare `FieldView` in a test could hit it | Not fixed |
| `ui/app.py` `_load_case_from_result` | Low | No 3D viewer pre-warm, unlike Open case | Owner's call, D128 |
| `ui/theme.py` `resrow:hover` | Low | A hovered row's caption 4.23:1 (light), transient | GUI-10, D125 |

No numerical change: no coefficient, unit, sign, range, default, case key
or export byte changed (T0 golden, `exports_qt.json`, `test_regression`
byte parity, the migration proof). No bare `except:`. No debug print, no
TODO left. No renamed public API (`ResultsPanel`'s list in the plan is all
there; `run_gauges._match` is wrapped by `match_gauges`, its callers
unchanged).

## Screenshots against the board

Read with the Read tool: the gauges (2D axisym., planar), field
(replay, manual + hover, 1D), method (native, blastFoam-shaped), export
busy and 3D shots, dark and light, 1600 × 1000 and 1100 × 720.

- Matches the board: three columns and their widths, the view tabs, the
  Gauges plot with the shaded positive phase and grey others, the readout,
  the table headers with Z and kPa·ms, `Copy table  Ctrl+C`, `Phase ended
  no` in `warn`, the Field controls / time bar with the cyan tick /
  `0.38 ms · 97 frames` / speed / This frame .png, the caption, the export
  column with suffixes and the busy strip (indeterminate, no percent, D82),
  Title on figures, Open the 3D viewer at the foot, the method card.
- The list cut at the fourth row in every shot, the readout cut at the
  map's edge, and the cropped 1D profiles at 1100 × 720: fixed above
  (D125-D127).
- Differences already recorded as decisions: no gauge markers on the map
  (R3), a linear colour bar (the board says `kPa, log`), `Gauge traces
  .txt`, the readout under the plot rather than over it (D96), the
  Mesh row's `cell 10.5263 mm` (`:g`, D90; the board shows `25 mm`).
- The 1100 × 720 Field map is small (controls on three lines, time bar on
  two), as the 7b report's suspected issue 2 says; owner's call.

## Test tails (one suite at a time, from `blastlab/tests`, final tree)

The T4 matrix plus `test_ui_preview`, 36 suites, one at a time, on
`db5657c` + the gauges edit. The suites that import the code changed after
that (`d7b614d`, `f7cb4fc`) were re-run on the final tree:
`test_ui_results_screen` (186), `test_ui_results`, `test_ui_no_mpl_pyplot`,
`test_ui_char_results_meta`, `test_ui_char_results_exports`,
`test_ui_parity`, `test_ui_run_screen`, `test_ui_results_vtk_folder`: all
green.

```text
test_ui_results_screen       UI RESULTS SCREEN: PASS (186 checks)
test_ui_results              UI RESULTS: PASS (130 checks)
test_ui_results_vtk_folder   UI RESULTS VTK FOLDER: PASS
test_ui_char_results_meta    CHAR UI RESULTS META: PASS
test_ui_char_results_exports CHAR UI RESULTS EXPORTS: PASS   (drive and drive_visible)
test_char_exports            CHAR EXPORTS: PASS
test_ui_run_screen           UI RUN SCREEN: PASS (168 checks)   (+ R-F14: 10/10 before the fixes)
test_ui_run_panel            All Qt run-panel checks passed.
test_ui_live_gauges          UI LIVE GAUGES: PASS (20 checks)
test_ui_frame                UI FRAME: PASS (50 checks)
test_ui_parity               exit 0 (its last line is a matplotlib tight_layout warning)
test_ui_drain                All Qt run-controller checks passed.
test_ui_view3d_host          All Qt 3D-host checks passed.
test_ui_three_surfaces       UI THREE SURFACES: PASS (35 checks)
test_ui_char_hd13_run        CHAR UI HD13 RUN: PASS
test_ui_char_write_failure   UI WRITE FAILURE: PASS
test_ui_char_case_form       CHAR UI CASE FORM: PASS
test_ui_components           COMPONENTS: PASS
test_ui_theme                THEME: PASS
test_ui_setup_strip          UI SETUP STRIP: PASS (110 checks)
test_ui_setup_tree           UI SETUP TREE: PASS (238 checks)
test_ui_setup_form           All Qt setup-form checks passed.
test_ui_chain                UI CHAIN: PASS (78 checks)
test_ui_run_browser          UI RUN BROWSER: PASS (48 checks)
test_ui_no_vtk_in_main       All 'no VTK in the GUI process' checks passed.
test_ui_no_mpl_pyplot        UI NO PYPLOT: PASS (19 checks)
test_ui_status_cells         UI STATUS CELLS: PASS
test_ui_crashlog             exit 0 (its last line is the deliberate thread error it provokes)
test_ui_fieldform_viewport   UI FIELDFORM VIEWPORT: PASS (11 checks)
test_ui_preview              All preview checks passed.
test_regression              REGRESSION: PASS
test_foam_writer             FOAM WRITER: PASS
test_case_validate           CASE VALIDATE: PASS
test_gauge_summary           GAUGE SUMMARY: PASS
test_report                  REPORT: PASS
test_anim_scale              ANIM SCALE: PASS (68 checks)
```

At base `c8a04d2` (worktree): `test_ui_fieldform_viewport` FAILED 8 of 11
(F14's error); `test_ui_char_results_exports` (the `bb065fc` test and
golden) PASS.

Real platform: `_e2e_ui_viewer_place.py` R-VIEWER 0 ms × 7 and
`_e2e_ui_results.py --base-worktree` PASS (39 checks), both at `d7b614d`;
`_e2e_ui_results.py --shots <scratch>` PASS (31 checks) at `f7cb4fc` (the
last fix moves only the hover label inside the Field page, which is never
on screen with the 3D host). The re-shot 1100 × 720 images show all four
results in the list with the `latest` badge, the 1D profiles inside their
canvas, and the full `overpressure 1944 kPa` readout.

## Decision rows and F-rows added (`docs/gui-redesign-decisions.md`)

- D125 the results list height (amends D94) · D126 the hover readout at
  the edges (amends D111) · D127 the on-screen 1D layout · D128 Load into
  01 Setup vs Open case (Done mark cleared; viewer pre-warm = owner's
  call) · D129 the ruling on the two out-of-list assertion changes ·
  D130 the gauge-curve failure text; Z still hidden silently on an
  unexpected error.
- F17: the 1D profile title overruns a canvas under about 430 px, and
  F2's white column shows there too (shared code this batch may not edit).

## Files touched by review

- `blastlab/ui/results_list.py`, `blastlab/ui/theme.py`,
  `blastlab/ui/results_field.py`, `blastlab/ui/results_fields.py`,
  `blastlab/ui/results_gauges.py`, `blastlab/ui/app.py`
- `blastlab/tests/test_ui_results_screen.py`
- `docs/gui-redesign-decisions.md`, this report

## GUI screens that need QA

- **03 Results**, both modes, 1100 × 720 and 1600 × 1000: the results
  list with 3, 5 and 12 results (height, scroll, the selected row in view,
  the selected caption colour); the method card; Show case; Load into 01
  Setup (clean and dirty, and the title's `✓ Done` after a finished run);
  the export column and its busy strip; Field (every field, the time bar,
  the hover readout near each edge of the map, manual Min/Max, This frame
  .png); 1D Field (profiles fit at 1100 × 720); Gauges (row click, Copy,
  Ctrl+C in the table and in the title box, planar without Z); 3D.
- **01 Setup** as the target of Load into 01 Setup.
- The Run tab's live pane (shares `ScalarImage`, F15's fix).
