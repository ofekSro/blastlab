# Implementer report — batch 2026-09-29-gui-setup-b (GUI-5b)

Branch `gui-redesign`, base `2641602`. Plan copied from the GUI-5a hand-off
into [`2026-09-29-gui-setup-b.md`](2026-09-29-gui-setup-b.md) (`b20461b`).
T1-T4 DONE, one commit each (T4 has a code-fix commit and a docs commit).
`test_regression.py` byte-green before the batch and after every task. No
numerical surface, case key, default, parser or file format changed; no shared
neutral module (`core/`, `services/`, `models/`, `solvers/`, `output/`) edited,
so the Tk gate was not triggered; `output/preview_draw.py` untouched.

## T1 · The live-number strip · DONE · `20b0518`

- New `ui/setup_strip.py`: `tiles(case, rep)` (no QApplication needed) gives
  each tile's value / unit / caption / bar from the `ValidationReport` and
  `RunPlan` the debounced `_validate` produced - `r_exp`, `n_cells`,
  `effective_dx` / `dx_fine`, `run_plan.ranks` / `requested` / `clamped_from`
  / `ram_gb` / `reason` - and Z from `ui/scaled_distance.py`. The one product
  formed is the hand-off's `n_cells × BYTES_PER_CELL`, in validation's GB
  (2^30 B). `LiveStrip`: five `StatTile`s + the board's Run F5 button (play
  mark, display-face `Run`, mono `F5` cap inside one QPushButton) and
  Initialise.
- Hidden, never greyed, when the report does not carry the number: no
  `run_plan` (native, 1D) → no MPI ranks / Memory; profile start → no Charge /
  Z; planar or no gauges → no Z; 0-D → no tile, no Initialise.
- One row from ~1400 px; below that two rows with the captions in the
  tooltips (the centre is 432 px at 1100 × 720) - D29.
- `SetupPanel.refresh` feeds it; `run_requested` / `init_requested` wired in
  `app.py` to `_run_single` / `_init_model` (the F5 / Run-tab actions). Run is
  enabled while the last report has no errors.
- Test: new `test_ui_setup_strip.py` S1 - every tile compared with the report
  field formatted in the test (sample case; measured VM → bar over
  `ram_gb`; requested / clamped ranks; native, planar, profile, AMR, 1D, 3D,
  0-D), the MainWindow wiring (patched actions), one row at 1600, wrapped at
  1100.

## T2 · Model view: toolbar, Z rings, highlight, hover · DONE · `99e304e`

- Toolbar over the view: plane caption · **Z rings** (default on) · **Mesh**
  (the old `show_mesh`, now a checkable toolbar button, same
  `setChecked`/`isChecked`/`toggled` API) · **Fit** (new `fit` glyph).
- New `ui/model_overlay.py`: Qt-side artists on the preview's matplotlib axis,
  drawn through a new `_MplPreview.overlay` hook right after `preview_draw`
  returns (and on every replay): dashed Z rings at Z = 1, 2, 3, radius
  `scaled_distance.ring_radius` (new: `Z · W^(1/3)`), in 1D as arcs in the
  sector; the 01 charge highlight (two rings + `Charge · 1 kg TNT` tag); the 05
  gauge halos with charge → gauge lines labelled `R 3.31` / `R 2.99`. Every
  artist carries a gid, stays out of `tight_layout`, and is removed before the
  next set (no leak over replays / theme switches - tested).
- Hover readout `r · z · R · Z` (planar `x · y · R`, 1D `r · R · Z`) from
  `motion_notify_event`, in the caption slot (D33). A wheel notch zooms the
  1D/2D view; Fit replays it at the whole domain; in 3D Fit sends the viewer
  its existing `reset_view`, and the Z rings button is hidden (D32).
- The Qt previews paint gauges `gauge` cyan (`_pal()`), D34.
- Test S2: ring radii asserted against `ring_radius` (1.00/2.00/3.00, 8 kg
  doubled, 1D arcs), off/planar/profile none, highlights, R labels ==
  `scaled_distance.gauges`, hover `r 2.95 · z 0.50 · R 3.31 · Z 3.31`, Mesh,
  zoom + Fit, 3D / 0-D toolbars.

## T3 · The dock Gauges · Checks · Log, Where, 05 summary · DONE · `eeda187`

- The 5a interim report card retires into a `DockTabs` dock (212 px; 150-212
  on short windows, D35): **Gauges** = the board table (Gauge · r · z · R from
  charge · Z [m/kg^1/3] · Where; axes per geometry; Z hidden where Z is; Where
  hidden in 1D; a row click selects the gauge in 05), **Checks** = the report
  (`show_report` / `report_rows` unchanged; two columns from a 560 px tab),
  **Log** = the panel's `log_fn` feed via a queued signal (the window sink
  still gets every line). Tab labels carry the counts and shorten when the
  centre is too narrow (D35). `DockTabs` gained `set_label`, `set_tooltip`,
  `set_tab_visible`.
- Dock follows the selection: 05 → Gauges, 01 → Checks (board script), the
  pill → Checks; 0-D hides the Gauges tab.
- `scaled_distance.where` / `where_text` / `walls_in_front`: the gap to the
  nearest obstacle box in the case plane, named within 0.5 m (`5 cm in front
  of Wall 1`, `on the face of`, `inside`) - D37. `setup_nodes.summaries` 05 →
  `2 · in front of Wall 1`.
- Measured on the way: the Setup previews cut `r [m]` off at 1100 × 720 once
  the strip and dock took height → they re-run `tight_layout` on canvas
  resize; an unwrapped "No gauges yet" hint set the dock minimum at 280 px and
  held a 1000 px window wide (P3 narrow sweep) → wrapped; at 1100 px the table
  gives way (`R [m]`, then the coordinate columns) - D36.
- Test S3: Where rules, the sample table (`G1 2.95 0.50 3.31 3.31 5 cm in front
  of Wall 1`, `G2 2.95 1.50 2.99 2.99 …`) against the helpers, planar / 1D /
  3D / empty, Checks order + counts + cap + columns, dock-follows, the Log from
  a worker thread, dock height, narrow table.

## T4 · Verification, screenshots, report · DONE · `29f096a` + docs commit

- Code fixes the shots found (`29f096a`, D38): light Z-tile caps 4.28 →
  `accent_soft` 4.65; 1D gauge highlight = halos only; Checks rows
  top-aligned; Where takes the table's slack (Z no longer stretched in 1D).
- `docs/qa/2026-09-29-gui-setup-b/`: 24 PNGs (dark + light, 1100 × 720 and
  1600 × 1000: 2d-threat, 2d-gauges, 2d-native, 1d, 3d, 0d),
  `measurements.md` (vs the board, contrast table), `shots_measure.json`,
  `viewer_measure.json`.
- **3D viewer placement (§8.7), real platform, Win32 ctypes: 1511 samples
  (1231 with a viewer window), 0 wrong, longest wrong stretch 0 ms** - over
  Setup↔Run↔Results, node changes (07 widening the properties to 459 px), dim
  and solver switches, the dock's tabs, Fit, Mesh, a long report, the strip
  going 2 rows ↔ 1 and the dock 170 ↔ 212, theme, detach / re-attach.
- `python -m blastlab` (throwaway settings, real platform) stayed up 15 s,
  then stopped by its PID.

## Tests run (final, from `blastlab/tests`)

`test_regression` REGRESSION: PASS (byte) · `test_ui_setup_strip` PASS (106,
new) · `test_ui_setup_tree` PASS (238) · `test_ui_setup_form` passed ·
`test_ui_parity` PASS (41) · `test_ui_preview` passed (unchanged) ·
`test_ui_components` PASS · `test_ui_frame` PASS (50) ·
`test_ui_three_surfaces` PASS (35) · `test_ui_theme` PASS ·
`test_ui_no_vtk_in_main` PASS · `test_ui_no_mpl_pyplot` PASS (18) ·
`test_ui_chain` PASS (78) · `test_ui_char_case_form` PASS ·
`test_char_case_json` PASS · `test_char_validation` PASS ·
`test_ui_output_card` PASS · `test_ui_results` PASS (129) ·
`test_ui_run_panel` passed · `test_ui_char_hd13_run` PASS ·
`test_ui_char_results_meta` PASS (a first run hit `MemoryError` importing
matplotlib while the shots ran on this 8 GB PC; green on the rerun) ·
`test_ui_run_browser` PASS (48) · `test_ui_logo` PASS ·
`test_ui_live_gauges` PASS (20) · `test_ui_view3d_host` passed ·
`test_ui_hd13_form` PASS · `test_ui_status_cells` PASS · `test_ui_drain`
passed · `test_ui_crashlog` PASS · `test_ui_char_write_failure` PASS ·
`test_ui_results_vtk_folder` PASS · `test_foam_writer` PASS ·
`test_case_validate` PASS. Harness (offscreen, own settings under
`~\blastlab_qa\20260929-0607`): `--scenario B01-B04,C01-C12,V01-V04` → 20
done, 53 ok, no finding, `exit 0`.

## Committed assertions changed (plan §9)

- `test_ui_setup_tree` **T2c**: the 05 summary pin `'2 gauges'` →
  `'2 · in front of Wall 1'` - the board's wording (line 89), which D26 said
  waited for 5b's Where helper. Layout copy, not behaviour.
- `STATUS_MAX_H` (imported by `test_ui_setup_form` S10 and the harness S2
  check) is now the dock's Checks page, 170 px (was the 132 px card). The
  assertions that use it are unchanged and green.
- Nothing else: harness helpers, `test_ui_parity`, `test_ui_output_card`,
  `test_ui_frame` untouched.

## Decisions appended

D29-D38 in `docs/gui-redesign-decisions.md`: strip wrap (D29), strip wording
(D30), hidden tiles and the Run gate (D31), no overlay in 3D (D32), hover slot
and wheel zoom (D33), cyan gauges in the previews (D34), dock behaviour (D35),
narrow gauge table (D36), Where rules (D37), screenshot fixes (D38).

## Suspected issues (not changed)

1. F2 (5a) is more visible now: the white 1 px column at the right edge of
   the dark 2D preview runs the full height of the smaller canvas at
   1100 × 720.
2. The embedded 3D host's control pane, when expanded in the narrower Setup
   centre, elides its own tab labels (`D…y`, `P…s`) - `view3d_host.py`, a
   §8.7 zone, not touched.
3. At 1100 × 720 the 2D preview is ~230 px high (two-row strip + 170 px dock);
   usable, cramped. A collapsible dock would give it back.
4. On this 8 GB PC the viewer child died once with `OpenBLAS error: Memory
   allocation still failed` (other applications held ~7.7 GB); the Setup then
   shows "The 3D viewer process stopped" until a run restarts it. The QA
   scripts set `OPENBLAS_NUM_THREADS=1`; the app's viewer child does not
   (`viz3d/process.py`, out of scope).
5. The 0-D centre still reads "Enter a valid case to preview the model here."
   (5a) although 0-D has no preview.
6. The Memory tile uses `rep.n_cells` at t = 0 for an AMR case (captioned
   `at t = 0`); the peak grows toward `maxCells`.
7. F7 (5a) stands: a validation error that names no parse field leaves every
   tree node ✓.
8. `settings.save` failed once with `WinError 5` renaming its temp file in the
   throwaway settings dir during the shots (an AV / indexer lock); harmless
   there.
9. Process hygiene: two of my debug scripts ended with their 3D viewer child
   orphaned (PIDs 14224, 22544); both stopped by PID. The `python -m blastlab`
   PID 29568 started 2026-09-28 23:49 (not this session) was left alone.
