# Implementer report — batch 2026-09-29-gui-results, part 7b (GUI-7b)

- Plan: [`2026-09-29-gui-results.md`](2026-09-29-gui-results.md), T5-T7.
- Branch `gui-redesign`, from `6b12a38` (7a closed). One implementer run.
- 7a's report: [`…-results-a.implement.md`](2026-09-29-gui-results-a.implement.md).
- Measurements:
  [`measurements.md`](../qa/2026-09-29-gui-results/measurements.md) (the
  board, contrast) and
  [`measurements-7b.md`](../qa/2026-09-29-gui-results/measurements-7b.md)
  (the embedded viewer, pre-registered).

## The gates

- **Numbers.** No number, default, case key, file format or solver
  changed. `test_regression.py` was byte-green before T5 and after every
  task. No run hit a `MemoryError`.
- **Export bytes.** `services/exports.py` and `output/` are unchanged.
  - `test_ui_char_results_exports` (T0's golden, recorded at base) passes
    with `drive` **and** with T6's new `drive_visible`.
  - `test_char_exports` passes.
  - The real-platform e2e exports Summary, Gauge traces, Field snapshot
    and Profile of real 1D and 2D runs through the new buttons. It
    compares them with `ui.exports.export(kind, ent, threaded=False)` run
    in a `c8a04d2` worktree on the same pickled Result objects. Text is
    compared by sha256, `.npz` array by array (D124). Every file was
    equal, in each of the seven e2e runs (8 of 8 comparisons each).
- **Frozen modules.** `git diff --stat 6b12a38` is empty over these:
  - `core/`, `services/`, `models/`, `solvers/`, `output/`, `viz3d/`;
  - `gui/` (Tk);
  - the regression fixtures.

  So the Tk suites were not triggered.
- **Imports.** No VTK or pyplot in the GUI process
  (`test_ui_no_vtk_in_main`, `test_ui_no_mpl_pyplot`, which now also
  plays the snapshots and writes This frame .png).
- **App launch.** `python -m blastlab` with a throwaway
  `BLASTLAB_SETTINGS`, offscreen, after T5 and after T6. Each time it was
  still up when `timeout` stopped it at 25 s, with empty stderr. The
  e2e ran the real MainWindow on the real platform after T7.
- **Session safety.** The §8.2 dry run at the start printed
  `<repo>\settings.json False []`. Every MainWindow ran with throwaway
  settings: `ensure_qapp`, the e2e's, the sampler's and the harness's
  own.
- **Process hygiene.**
  - Foreign at the start and throughout: PID 29568 (`python -m
    blastlab`), left alone.
  - I stopped no process by hand. Every viewer child closed with its
    window (the sampler and the e2e print it). Each `timeout` stopped
    only its own child.
  - The base worktree (`<scratch>\g7b\base_wt`, `c8a04d2`) served the
    resize A/B and the export cross-check. It was removed at the end
    (`git worktree remove`).
- **Edits.** Every repo file went through Edit or Write. One-off scratch
  scripts (the grey contrast search, `contrast.py`) were written in the
  scratch folder; two of them by a Bash heredoc, which touched no repo
  file.

## Commits (`6b12a38..`)

- `f38351f` T5: the Gauges view.
- `c0303c6` T6: the Field view.
- `416dc25` T7: the viewer rules, pre-registered before any sampled run,
  and the sampler's `views` action.
- `7e623ba` T7: eight fixes found on the real platform, and the e2e.
- this report's commit: the measurements, the screenshots, the report.

Every message was written to a new file in the scratch dir and committed
with `git commit -F`, staging by explicit path. The six foreign paths
were never staged.

**One commit was not green.** `f38351f` (T5) gave the table a Ctrl+C
`QShortcut`, as the plan asked. `test_ui_frame` F5 pins the window's
shortcuts to exactly five keys and finds the table's too, so F5 was red
at that commit. I ran `test_ui_frame` only in T6, found it, and moved
Ctrl+C into the table's own `keyPressEvent` (`c0303c6`, D105). The app
ran at every commit.

---

## T5 · Gauges view · DONE · `f38351f` (+ fixes in `c0303c6`, `7e623ba`)

**What was built** (`ui/results_gauges.py`, rewritten):

- One pyqtgraph plot. Every gauge is one curve of
  `plots.GAUGE_FIELDS[field]`: x = `times × 1e3`, y = the field's own
  transform, the arrays the matplotlib grid plots.
- The selected curve is `gauge` at 2.4 px, the others grey at 1.2 px
  (`#626268` / `#89898f`, D97).
- The positive phase is shaded (`FillBetweenItem`, `gauge` at 16 %) over
  `[arrival, arrival + duration]` from `summarize_trace`, for p only.
- The readout under the plot uses the table's own strings.
- The table: `Gauge · Z [m/kg^1/3] · Peak [kPa] · Arrival · t peak ·
  Pos. phase · Pos. impulse [kPa·ms] · Net impulse [kPa·ms] · Phase
  ended`.
  - Every numeric cell is `table_rows`' string, unchanged.
  - `G<n>` has the old label as its tooltip.
  - Z comes from `scaled_distance` of the entered gauge
    (`run_gauges.match_gauges`, now public).
  - Z is hidden for planar, a profile start or a missing key
    (`scaled_distance.case_from_meta`, display only).
  - Rows are sorted by Z, ties by number.
  - `Phase ended` "no" is in `warn`.
- Header wrapping (D102) and the height caps are kept (D100, D123).
- **Copy table** and Ctrl+C with the table focused (D105) copy the
  visible headers and cells, tab-separated, with no trailing newline.
- The selection defaults to the trigger gauge, else the first row. It
  persists across the view tabs and resets on a result change. The
  panel's API is `selected_gauge()` / `select_gauge(n)`.

**Tests**: `test_ui_results_screen.py` S5 (39 checks). Run with `cd
blastlab/tests && python test_ui_results_screen.py`.

- Every curve is `np.array_equal` to (times·1e3, the transform).
- Z equals `scaled_distance` computed in the test: sample geometry G1
  3.31 / G2 2.99, and the char 2D result.
- Every numeric cell equals `table_rows` by gauge number.
- Pens, and the fill span, before and after a real row click.
- There is no fill for |U|.
- The readout strings.
- Copy and Ctrl+C give exactly the text built in the test: nine columns
  with Z, eight without (planar, profile start). Ctrl+C in the title box
  leaves the clipboard alone.
- 1D: Z = r / W^(1/3).
- The plot is taller than the table at 1100 × 720 and on the 900 × 600
  panel; twelve gauges scroll.

**The char-golden migration** (`ui_results_meta.json`, the plan's
allowance). `gauges.figure` became `gauges.traces`, the sha1 of each
curve's `column_stack((x, y))` as float64. The `missing/*/<key>/gauges`
short hashes changed with it. The proof ran before `--update` was
committed, with the script
`<scratch>\g7b\migrate_meta_golden.py`:

- (a) every `traces[k]` equals the old golden's
  `figure.axes[k].lines[0]`;
- (b) the flattened JSON diff has no changed path outside
  `<fixture>/gauges/figure|traces` and `missing/*/<key>/gauges`, and
  every missing-key entry keeps its class.

```text
(a) 28 curves over 13 fixtures; mismatches: 0
(b) changed paths outside the allowed set: 0
(b) missing/*/<key>/gauges entries: 130; class changes: 0
MIGRATION PROOF: PASS
```

The numbers on screen are bit for bit the ones the old figure plotted.
The golden was not touched again by T6 or T7 (`CHAR UI RESULTS META:
PASS` on each).

## T6 · Field view · DONE · `c0303c6` (+ fixes in `7e623ba`)

**What was built** (new `ui/results_field.py`, placement not engines):

- `FieldView` puts the board's controls over the two engines, which it
  hides and drives.
- A Field `Segmented` (+ Plane in 3D) composes exactly one
  `field_options` string into `field_sel`.
- Colours (`whole run · each frame · manual`) drives `scale_sel`, the
  export's option as before, and the new `FieldsView.set_scale`.
  - `whole run` on the snapshot maps: `frame_clim` for overpressure, and
    the finite min..max for density and speed.
  - Min / Max only in manual, with the field's unit, remembered per
    field. The overpressure range is the replay's boxes (D109, D110).
- Show mesh is a checkable button: the same widget, the same API.
- The **time bar**:
  - the recorded frames for overpressure (in 3D only for the recorded
    plane, D106), else the snapshots;
  - Play at the same tick and speed rules;
  - switching keeps the time (D107);
  - the arrival tick of the selected gauge;
  - `0.38 ms · 97 frames`, the speed (`0.25× … 4×`);
  - This frame .png, threaded, with a busy strip (D112).

  No bar on whole-run maps, 1D or the isosurface, and the caption says
  why.
- The **hover readout**: `ScalarImage.value_at` reads the displayed cell
  with no interpolation. A solid cell reads `solid`; outside the domain
  it hides (D111, D118).
- Views are `Field · Gauges · 3D`. `show_view('Fields' | 'Animation')`
  selects Field. `ResultsPanel.set_colour_scale(scale, clim)`.
- **F15 fixed:** `ScalarImage.remove` now takes the colour bar off the
  scene (3 bars after 3 results before, 1 after), and the bar is
  labelled once (D115).

**Hidden legacy widgets** (still alive as the engines' state, for
GUI-10 or the simplifier):

- `FieldsView.controls` (its WrapRow): `snap_sel`, `field_sel` and their
  `Snapshot` / `Field` labels. `show_mesh` moved to the Field row.
- `AnimView.controls`: `play_btn`, `slider`, `speed_sel` and the `Speed`
  label; `scale_sel`, `min_box`, `max_box` and the `Colours` label.

**Tests**: `test_ui_results_screen.py` S6 (47 checks, plus the suite's
closing "nothing raised" and "no VTK / pyplot").

- Three tabs; the aliases; the hidden engine rows; Show mesh is the same
  checkable widget.
- For 2D with frames, 2D without, 3D and 1D, the choices compose exactly
  `field_options`, as a set and as a bijection, through real clicks.
- The time bar:
  - max `n − 1`, one `show_frame` per move;
  - Density switches to `… · 2 snapshots` at the nearest snapshot, and
    back to the nearest frame;
  - Play follows the replay; the speed goes both ways; the snapshots
    play;
  - Peak and Impulse have no bar, and the caption says why;
  - 40 / 32 / 32 px.
- Manual (0, 50) typed into the visible boxes gives `export_opts() ==
  {…, 'anim_scale': 'manual', 'anim_clim': (0.0, 50.0)}`, and the replay
  levels follow.
- The scale on the maps:
  - `each frame` gives (1.2, 2.2);
  - `whole run` on density gives the (min, max) computed in the test;
  - a manual density range is not in the export, and is remembered per
    field.
- Hover at a cell centre gives the displayed value, formatted. A solid
  cell reads `solid`; outside, it hides; the scene signal drives it; the
  replay reads in kPa.
- Ticks: the frame nearest the selected gauge's arrival; they follow
  `select_gauge`; on the snapshots too; none for a NaN arrival.
- This frame .png:
  - one PNG > 5 kB with one panel, named after the field and the time;
  - the QuadMesh clim is the on-screen range (manual and whole run);
  - threaded, with its busy strip;
  - a cancelled dialog writes nothing.
- F15: one colour bar in the scene after three 2D results. A probe
  counted 3 with the base `remove`.
- `drive_visible` reproduces T0's golden (`CHAR UI RESULTS EXPORTS:
  PASS`, both drivers).

## T7 · Verification · DONE except one pre-registered rule · `416dc25`, `7e623ba`, this commit

**Plan §10, all four:**

1. **The three views work on a native 1D and a native 2D result.** S5
   and S6, and the new real-platform `_e2e_ui_results.py`: `E2E UI
   RESULTS: PASS (40 checks)`.
   - Three tiny native runs go through Run.
   - On 1D and 2D it walks Field: every field drawn, 1 s of replay
     (frames 0 → 12), the real pointer's hover, This frame .png.
   - Gauges: a row click, Copy on the real clipboard.
   - 3D: the placeholder, no scene.
   - No uncaught exception and no error dialog.
   - A native 3D result in the embedded viewer (`--with-3d`; memory
     allowed it: about 2.4 GB of free commit).
2. **Field replaces both old tabs, and the export uses its colour
   scale.** S6 (the export options), and `drive_visible` against T0's
   golden.
3. **Copy table puts tab-separated text with headers on the
   clipboard.** S5, and the e2e on the real clipboard. The exact text
   for the 2D run:

   ```text
   Gauge	Z [m/kg^1/3]	Peak [kPa]	Arrival [ms]	t peak [ms]	Pos. phase [ms]	Pos. impulse [kPa·ms]	Net impulse [kPa·ms]	Phase ended
   G1	0.50	2707.4	0.135	0.163	0.104	130.73	121.77	yes
   G2	0.64	1894.4	0.230	0.258	0.145	143.00	143.02	no
   ```

4. **Exported CSV/TSV are byte-identical to before.**
   - `test_ui_char_results_exports` with `drive` and `drive_visible`,
     and `test_char_exports`.
   - The e2e's base cross-check: all four data kinds, 1D and 2D, equal.
     1D: 1 + 1 + 10 + 1 files; 2D: 1 + 1 + 8 files and one `.npz` of 15
     arrays.

**Screenshots**: 40 shots in `docs/qa/2026-09-29-gui-results/`,
`gui7b-<dark|light>-<1600x1000|1100x720>-<what>.png`:

- field-replay, field-manual-hover;
- gauges-2d, gauges-planar;
- field-1d, gauges-1d;
- method-native, method-foam;
- export-busy (a real Animation export);
- view3d.

`measurements.md` has the geometry against the board and the contrast of
32 pairs in both modes, all at or above the minimum after D121.

**Found on the real platform and fixed** (`7e623ba`, D117-D124):

- The hover readout never painted.
- Two segment rows were drawn over each other.
- A stale wrap plan squeezed the Field controls.
- F15's doubled bar label.
- The gauge time axis read `(x0.001)`.
- Cut captions.
- The last table row was 1 px short.
- The side columns stayed narrow after a 3D result.
- Two light-mode contrast pairs were under 4.5:1.

**The embedded viewer** (the committed sampler; rules pre-registered in
`416dc25`):

- **R-VIEWER: PASS.** 0 ms for open3d, views (new), select, busy, stage,
  tabs and theme, each with ≥ 1053 samples with a window. It passed at
  `416dc25` and again at `7e623ba`.
- **R-VIEWER-RESIZE (F13): FAIL in the judged pair, by 1.9 ms.** Base
  18.5 ms, HEAD 25.4 ms; the rule allows 23.5.
  - Four diagnostic pairs: 3 pass, 1 fails (+0.6, −6.2, −1.0, +13.3 ms).
  - Pooled over 15 repeats a side: 19.6 ms base, 24.1 ms HEAD.
  - The longest stretch is 32.0 base and 31.3 HEAD.
  - It is F13's pre-existing lag, in the same shape at base.
  - **Action: reported, not fixed** (plan §11). The fix belongs in
    `view3d_host.py` (F13, F5). The rule's one pair of three-repeat
    medians cannot resolve 5 ms in this noise.

**Harness** (offscreen, its own settings): no finding. See "Harness"
below; it covers D04's one environmental 29.6 s gap and its A/B.

**Fast matrix**: 35 suites, all green. See "Test tails" below.

---

## Harness

Offscreen, the harness's own settings, one run at a time. The only
harness edit is E03's `canvas` → `plot_w`; the old view names reach Field
through the aliases.

- **`B01,D01,D02,E01,E02,E03,E04,E07,E08,E09,I01`**
  (`~\blastlab_qa\20260929-gui7b-E1`): exit 0, all eleven done, 39 `ok`,
  and **no `findings.jsonl`: no finding**.
  - E01: 3D asked of a 1D result explains itself.
  - E02: every 2D field and snapshot drew.
  - E03: the table has its rows and the plot is taller than it; four
    exports wrote files.
  - E04: the replay (engine) keeps one range over the video.
  - E07: PNGs wrote the whole grid, and the video was written.
  - E08: Remove.
  - E09: the title reaches the figure.
  - I01: switching tabs and views during a native 3D run; the run
    finished (10 min 25 s). Longest UI gap 2.3 s, during the solve.
- **`D04,E05,E06`** alone (`…-gui7b-E2`): exit 0, no finding.
  - D04: the native 3D run with the 3D view finished in 10 min 28 s.
  - E05: all nine 3D fields drew.
  - E06: the viewer opened in 54 ms, and every control was exercised.
  - **But D04 logged one 29.6 s UI gap**, right after Run: the 3D page
    came forward 36 s after the click. I ran an A/B, one run at a time:
    - D04 at base `c8a04d2`: largest gap 1.6 s, page forward after 6 s;
    - D04 at HEAD again: largest gap 1.7 s, page forward after 6 s.

    So it was the environment (the first native 3D start in that session,
    about 0.5 GB of physical memory free), not the code. GUI-6 recorded
    1.6 s.
- **Against GUI-6's run** (`20260929-1157` smoke, `-1252` D04, `-1323`
  I01), the findings are the same: none in these scenarios. GUI-6's one
  smoke finding, B06 (F10), is not in this list, and 7a's E smoke had
  none. GUI-6's D04 / I01 `MemoryError`s did not recur.

## Test tails

The T4 matrix, one suite at a time, from `blastlab/tests`, on the tree of
`7e623ba`. The docs commit changes no code.

```text
test_ui_results_screen       UI RESULTS SCREEN: PASS (174 checks)
test_ui_results              UI RESULTS: PASS (130 checks)
test_ui_results_vtk_folder   UI RESULTS VTK FOLDER: PASS
test_ui_char_results_meta    CHAR UI RESULTS META: PASS
test_ui_char_results_exports CHAR UI RESULTS EXPORTS: PASS   (drive and drive_visible)
test_char_exports            CHAR EXPORTS: PASS
test_ui_run_screen           UI RUN SCREEN: PASS (168 checks)
test_ui_run_panel            All Qt run-panel checks passed.
test_ui_live_gauges          UI LIVE GAUGES: PASS (20 checks)
test_ui_frame                UI FRAME: PASS (50 checks)
test_ui_parity               UI PARITY: PASS (41 checks)
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
test_ui_crashlog             UI CRASHLOG: PASS
test_ui_fieldform_viewport   UI FIELDFORM VIEWPORT: PASS (11 checks)
test_regression              REGRESSION: PASS
test_foam_writer             FOAM WRITER: PASS
test_case_validate           CASE VALIDATE: PASS
test_gauge_summary           GAUGE SUMMARY: PASS
test_report                  REPORT: PASS
test_anim_scale              ANIM SCALE: PASS (68 checks)
```

Real platform, at `7e623ba`:

- `_e2e_ui_results.py --base-worktree … --with-3d --shots …`: `E2E UI
  RESULTS: PASS (40 checks)`.
- `_e2e_ui_viewer_place.py`: R-VIEWER 0 ms for seven actions.
- `python -m blastlab`: up at 25 s with empty stderr (the last launch,
  on the real platform).

## Committed assertions changed

All are on the plan's allowed list, except two marked "not listed",
each with its reason.

- **`test_ui_results.py` R4:**
  - `len(RG.COLUMNS) == len(RG.HEADERS) == 8 == columnCount() ==
    len(gauge_summary.COLUMNS)` became `… == 9 == columnCount() ==
    len(gauge_summary.COLUMNS) + 1 and RG.COLUMNS[1] == 'z'`.
  - `RG.HEADERS[1] == 'Peak ovp [kPa]'` became `RG.HEADERS[2] == 'Peak
    [kPa]'`.
  - `g.canvas.height()` became `g.plot_w.height()`, three times, with
    the same rules.
  - `fig.axes[0].get_ylabel()` became `g.ylabel()` (the pyqtgraph left
    axis), with the same strings.
  - "The rows are the shared summary formatting" is **unchanged**
    (`rows()` keeps its meaning, D98). A new check was added: every
    numeric cell on screen is `table_rows`' string, by gauge number.
- **`test_ui_results.py` R8 (not listed).** `p.gauges.canvas.figure is
  not None` became `p.gauges.page() == 'empty' and 'appear here' in
  p.gauges.hint.text()`. The matplotlib canvas that carried the "nothing
  yet" message is gone from the screen (T5), so the check reads the same
  behaviour on the new page, more strictly: the text itself.
- **`test_ui_results.py` R3 and R5: unchanged.**
  - R3's `(1.2, 2.2)` holds as written, because `whole run` on a uniform
    density gives the same levels.
  - R5 reaches Field through the `Animation` alias.
- **`test_ui_parity.py` P5.** "All eight summary headers" became "all
  nine (Z included)", with `== 9` added.
- **`test_ui_no_mpl_pyplot.py`.** The view names are now `('Field',
  'Gauges', '3D')`, and three new checks were added (the replay on the 2D
  result, the snapshot play, This frame .png). The pyplot rule is
  unchanged.
- **`test_ui_char_results_meta.py` + its golden.** `gauges.figure`
  became `gauges.traces`, and the missing-key gauge hashes changed, under
  the proof above.
- **`test_ui_char_results_exports.py`.** `drive_visible` and
  `test_panel_exports_visible` were added. `drive` and the golden are
  unchanged.
- **`_qa_ui_harness.py` E03.** `rs.gauges.canvas.height()` became
  `rs.gauges.plot_w.height()`. No scenario logic changed, and the view
  names go through the aliases.
- **`test_ui_results_screen.py`.** S5 and S6 were added; S2e keeps
  `show_view('Fields')` (the alias).
- **`_e2e_ui_viewer_place.py` (not listed; 7a's own file).** The `views`
  action was added, committed with the rules before any run.

## Decisions and F-rows (`docs/gui-redesign-decisions.md`)

- D96 Gauges layout · D97 grey · D98 `rows()` · D99 1D Z · D100 table
  share · D101 no gauges · D102 header wrap · D103 → D105 Ctrl+C · D104
  plot title.
- D106 3D frames plane · D107 keep the time · D108 recorded scale · D109
  whole run · D110 Min / Max · D111 hover · D112 This frame .png · D113
  time bar · D114 controls row · D115 F15 · D116 engine signals.
- D117 column re-fit · D118 hover transform · D119 segment rows · D120
  SI prefix · D121 light contrast · D122 captions · D123 table cap · D124
  npz comparison.
- F15's outcome filled in.

## Suspected issues (noticed, not changed)

1. **F13 and R-VIEWER-RESIZE.** See T7. The resize lag is 17-32 ms at
   base and at HEAD.
2. **The map at 1100 × 720 is small.** The controls take three lines
   and the time bar two, so the plot is short. Owner's call: put Show
   mesh on the Colours line, or shorten the Field segment labels.
3. **The planar e2e run takes about 3-4 min** (the 1 kg/m charge refines
   to 2.8 mm). It is only a fixture, but a slow one.
4. **`frames_plane` for a y-z recording** (an x slice) shows the replay
   under both Field planes (D106). Such a recording can be reached in no
   other way.
5. The headers wrap even at 1600 × 1000 (D102). The board's own table
   would too at its width.
6. The stale worktree record `.git/worktrees/gui6a_base_wt` (7a's
   suspected issue 5) still makes each commit print `failed to delete …
   Permission denied`. Left alone.

## GUI screens touched

- **03 Results → Field** (new): 2D, 3D, 1D, both modes, 1100 × 720 and
  1600 × 1000.
- **03 Results → Gauges** (rebuilt): axisymmetric, planar, 1D, and the
  Trace selector for foam extras.
- **03 Results → 3D**: unchanged; the tab strip has three tabs.
- The Run tab's live pane shares `ScalarImage` (F15's fix and the bar
  label).
