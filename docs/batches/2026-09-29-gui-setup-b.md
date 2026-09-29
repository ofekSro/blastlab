# Batch 2026-09-29-gui-setup-b — GUI-5 · 01 Setup, part 5b (centre)

**Goal in one sentence:** finish the 01 Setup screen's centre column of board
`BC_Combined` — the live-number strip over the model view, the model-view
overlays (Z rings, selection highlight, hover readout, toolbar) and the dock
**Gauges · Checks · Log** — with every number read off what validation already
computed and no numerical, case or file-format change anywhere.

**Source:** the hand-off section "GUI-5b — specification hand-off" at the end of
[`2026-09-29-gui-setup.md`](2026-09-29-gui-setup.md), copied out here task by
task, plus what GUI-5a's report left for it
([`2026-09-29-gui-setup.implement.md`](2026-09-29-gui-setup.implement.md),
"Left for GUI-5b").
**Spec:** [docs/gui-redesign-plan.md](../gui-redesign-plan.md) §5.3 (the
centre), §9 (rules for every GUI task), §10 (GUI-5 acceptance), §11 (risks).
**Board:** `docs/design/gui-redesign/boards/BC_Combined.dc.html` lines 123-266
(strip, model view, dock) and its trailing `<script>` (dock-follows-selection:
`pickThreat` → Checks, `pickGauges` → Gauges; the pill → Checks).
**Branch:** `gui-redesign`, base `2641602` (GUI-5a closed).
**Built by 5a, reused here:** `ui/setup_panel.py` (three columns,
`refresh(case, rep)` called once per debounced `_validate`), `ui/setup_tree.py`,
`ui/setup_nodes.py` (`summaries`), `ui/scaled_distance.py` (the one Z source),
`ui/components.py` (`StatTile`, `DockTabs`, from GUI-4), `DerivedCard`.

---

## Tasks, in order

### T1 · The live-number strip — size M

**Files:** new `blastlab/ui/setup_strip.py` (the tile texts as a toolkit-free
function of `(case, rep)` + the strip widget), `blastlab/ui/setup_panel.py`
(the strip on top of the centre column), `blastlab/ui/app.py` (wire Run /
Initialise to the existing `_run_single` / `_init_model`), `blastlab/ui/theme.py`
(QSS object-name rules only), `blastlab/ui/components.py` (only if a tile needs
a knob).

- `StatTile`s **Charge · Cells · MPI ranks · Memory · Z at gauges**, then the
  big **Run F5** button with **Initialise** under it (board lines 125-159).
- Every number read off the `ValidationReport` / `RunPlan` the debounced
  `app._validate` already produced, via the existing `SetupPanel.refresh(case,
  rep)` call — never re-derived:
  - Charge: the mass and material **as entered**, caption `radius <rep.r_exp>`
    (the Derived card's formatting);
  - Cells: `rep.n_cells`, caption the cell size `rep.effective_dx`, or
    `rep.dx_fine` when the mesh is refined / AMR;
  - MPI ranks: `rep.run_plan.ranks`, caption `auto · N cells each`
    (`requested` / `clamped` when the case asked);
  - Memory: `rep.n_cells × core.constants.BYTES_PER_CELL`, in the GB the
    validation messages use (2^30 B), bar over `rep.run_plan.ram_gb`;
  - Z at gauges: min–max through `ui/scaled_distance.py`, `accent` variant.
- A tile whose number is not available is **hidden, never greyed** (plan §5.3):
  MPI ranks and Memory have no `run_plan` in native mode or in 1D; 0-D has no
  tile at all; Charge and Z hide when the case starts from a profile; Z hides
  for planar 2D and without gauges.
- Run F5 / Initialise call the same `MainWindow` actions as the Run tab and the
  F5 key; Initialise hides in 0-D (an HD 1.3 assessment has no step 0). Run is
  enabled while the last report has no errors (the Run tab's own gate).
- The strip must fit the centre column from 1100 × 720 up (P1/P1b/P3 clipping
  sweeps): tiles wrap to a second row rather than clip.

**Acceptance:**
- Offscreen test (`test_ui_setup_strip.py`): for the sample case (2D axisym,
  blastFoam) and a native 2D, a 1D, a 3D and a 0-D case, **every tile's text
  equals the report field formatted** — asserted against `rep.n_cells`,
  `rep.r_exp`, `rep.effective_dx`/`dx_fine`, `rep.run_plan.ranks`,
  `rep.n_cells * BYTES_PER_CELL`, `rep.run_plan.ram_gb`, and the Z helper — not
  literals; hidden tiles exactly as listed above; Run/Initialise emit the
  panel's signals and the `MainWindow` wiring reaches `_run_single` /
  `_init_model` (patched, no run started).
- `test_regression.py` byte-green; `test_ui_setup_form`, `test_ui_setup_tree`,
  `test_ui_parity` green.

### T2 · Model view: toolbar, Z rings, selection highlight, hover readout — size M

**Files:** new `blastlab/ui/model_overlay.py` (Qt-side artists on the preview's
matplotlib axis), `blastlab/ui/preview_panel.py` (an overlay hook called after
`preview_draw` returns, and again after a theme replay),
`blastlab/ui/setup_panel.py` (the toolbar row), `blastlab/ui/scaled_distance.py`
(`ring_radius`), `blastlab/ui/theme.py` (QSS only).
**`output/preview_draw.py` is not edited** (shared with Tk; `test_ui_preview`
must stay untouched).

- **Toolbar** over the view (board lines 162-167): a muted caption at the left
  (`r–z plane · charge on the axis` …), **Z rings** (checkable, default on),
  **Mesh** (the existing `show_mesh`, now a checkable toolbar button with the
  same `setChecked`/`isChecked`/`toggled` API), **Fit** (re-draws the preview
  at the full domain; in 3D, the viewer's `reset_view`).
- **Z rings**: dashed circles at Z = 1, 2, 3 around the burst point, radius
  `Z · W^(1/3)` (W as entered), `accent`, fading opacity, labelled `Z 1`…; in
  1D as arcs inside the sector. Drawn only when Z is shown (not planar, not
  profile, not 0-D) and the toggle is on. The 3D child viewer's scene is out of
  scope (plan §0) — the Z-rings button hides in 3D (decision row).
- **Selection highlight** (board `chargeHi` / `gaugeHi`): 01 Threat selected →
  two rings around the charge and a `Charge · 1 kg TNT` tag; 05 Gauges selected →
  gauge halos in `gauge` cyan and dashed charge → gauge lines labelled `R 3.31`.
- **Hover readout** `r · z · R · Z` (planar `x · y · R`, 1D `r · R · Z`) via
  mpl `motion_notify_event`, cleared on leave.
- The overlay is display-only: nothing exported, no case value read that the
  preview does not already draw.

**Acceptance (offscreen, `test_ui_setup_strip.py` or its own suite):**
- Sample case: three ring artists at radii 1.00, 2.00, 3.00 m around (0, 2) —
  asserted against `scaled_distance.ring_radius`; toggle off → none; planar /
  profile → none; 8 kg → radii doubled.
- Threat selected → the charge highlight artists exist, Gauges selected → one
  halo per gauge and one R label per gauge equal to `scaled_distance.gauges`.
- A synthetic `motion_notify_event` at (2.95, 0.50) reads `r 2.95 · z 0.50 ·
  R 3.31 · Z 3.31`.
- Mesh button toggles `show_mesh` semantics (the preview is replayed);
  `test_ui_preview.py` unchanged and green.

### T3 · The dock Gauges · Checks · Log, the Where column, 05 summary — size M

**Files:** `blastlab/ui/setup_panel.py`, `blastlab/ui/scaled_distance.py` (the
Where helper), `blastlab/ui/setup_nodes.py` (05 summary),
`blastlab/ui/components.py` (a `DockTabs` label setter if needed),
`blastlab/ui/theme.py` (QSS only).

- Dock ≈ 212 px (board line 217), `DockTabs` **Gauges · Checks · Log**:
  - **Gauges** = the board's table: Gauge · r · z · R from charge · Z · Where
    (axis names per geometry; Z column hidden when Z is; Where = the nearest
    obstacle face within 0.5 m, `5 cm in front of Wall 1`); tab label carries
    the count.
  - **Checks** = the `show_report` rows (the T2 interim card of 5a retires
    here); `show_report` / `report_rows` semantics and order (error → warn →
    note, `Case OK` on empty) unchanged; tab label carries the counts
    `E · W · N` and the state icon.
  - **Log** = the panel's `log_fn` feed (thread-safe via a queued signal; the
    original sink still receives every line).
- **Dock follows the selection** (board script): selecting 05 Gauges shows the
  Gauges tab, 01 Threat shows Checks; the case pill shows Checks.
- **05 summary** reads `2 · in front of Wall 1` when a gauge has a Where
  (board line 89), `2 gauges` otherwise, trigger suffix kept.

**Acceptance:**
- Sample case: the table shows G1 `2.95 0.50 3.31 3.31 5 cm in front of Wall 1`
  and G2 `2.95 1.50 2.99 2.99 5 cm in front of Wall 1` (Z via the helper,
  asserted against it); planar hides Z; 1D hides z and Where.
- Selecting 05 → Gauges tab; 01 → Checks; pill → Checks.
- `test_ui_setup_form` S10 (one row per message, order, `Case OK`, a long
  report is capped) green against the dock; `test_ui_setup_tree` T2b green.
- 05 summary reads `2 · in front of Wall 1` for the sample case.

### T4 · Verification, screenshots, report — size M

- Full fast Qt matrix from `blastlab/tests` (as GUI-5a T5, plus the new suite);
  harness smoke `--scenario B01,B02,B03,B04,C01-C12,V01-V04` with its own
  settings.
- **Real platform** (`QT_QPA_PLATFORM` unset): screenshots dark **and** light
  at **1100 × 720** and **1600 × 1000** of 2D Setup with 01 Threat selected
  (Checks tab), with 05 Gauges selected (Gauges tab), native mode, 1D, 3D, 0D;
  `docs/qa/2026-09-29-gui-setup-b/measurements.md` against the board (strip
  tile sizes, dock height 212, tab underline, table columns, ring colours).
- **3D viewer placement re-measured** (CLAUDE.md §8.7; the preview stack gets a
  new sibling above and below it): Win32 ctypes sampler over Setup↔Run↔Results
  switches and a 3D Setup preview; longest unbroken wrong-place stretch.
- Report `docs/batches/2026-09-29-gui-setup-b.implement.md`; decision rows
  appended to `docs/gui-redesign-decisions.md` (next id after D28).

---

## Committed assertions: what may change (plan §9)

**May be updated (layout the design replaces) — list each with its reason:**
- `test_ui_setup_form.py` **S10**: only the `STATUS_MAX_H` value/geometry (the
  report is re-homed into the dock's Checks tab). Its behavioural halves — one
  row per message, error → warn → note, `Case OK` on empty, a long report is
  capped and scrolls — must survive verbatim.
- `test_ui_setup_tree.py` **T2c**: the 05 summary pin `'2 gauges'` becomes the
  board's `'2 · in front of Wall 1'` (the interim wording D26 said would wait
  for 5b).
- `_qa_ui_harness.py`: navigation/widget-path helpers only (`_status_scroll`,
  `show_mesh` if its widget path moves).
- `test_ui_parity.py` P1/P1b/P3: none expected — the strip wraps instead.

**Must NOT change:** `test_regression.py` (byte), `test_char_*` goldens,
`test_ui_char_case_form.py`, `test_ui_preview.py` (preview_draw untouched),
`test_ui_chain.py` (78), `test_ui_no_vtk_in_main.py`, `test_ui_no_mpl_pyplot.py`,
every `test_gui_*` (Tk not touched; no shared neutral module edited — if one
must be, run the Tk suites), S1-S9 of `test_ui_setup_form.py`.

---

## Risks

1. **Numbers on screen.** The strip is the first place the GUI shows cell
   counts, ranks and memory next to each other. Guard: the tile texts come
   from one pure function of `(case, rep)` and the test compares them with the
   report's own fields, formatted in the test; the only arithmetic is the
   product `n_cells × BYTES_PER_CELL` the hand-off spec names.
2. **The 3D host gets new siblings** (strip above, dock below) — CLAUDE.md §8.7:
   measure the embedded viewer on the real platform.
3. **Height at 1100 × 720**: strip + view + 212 px dock in ~600 px. The strip
   wraps and the dock may shrink below 212 px on short windows; P1b/P3 are the
   guard.
4. **Overlay vs replay**: `show_case` clears the axis, and a theme switch
   replays it; the overlay must be re-applied after every draw, never leak
   artists (tests count them).
5. **Session safety**: CLAUDE.md §8.2 dry run before building a MainWindow;
   throwaway `BLASTLAB_SETTINGS` everywhere.

## Implementer rules (binding)

- Never stage: `docs/references/INDEX.md`,
  `docs/references/ViperTheoryManual_Client.pdf`,
  `docs/references/ViperTheoryManual_Client.txt`,
  `docs/references/viper_vtk_sample/`, `docs/qa/2026-09-27-out-3/`,
  `docs/qa/2026-09-27-viewer-polish/`. Stage by explicit path.
- No PowerShell string round trips on files (CLAUDE.md §8.1); commit messages
  via a file and `git commit -F`, ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Throwaway settings for every MainWindow (§8.2); `ui.testing.ensure_qapp()`
  forces offscreen unless `offscreen=False`.
- Real platform for geometry and screenshots (§8.7).
- Process hygiene: stop only processes this batch started, by PID; never a
  broad kill; leave any `python -m blastlab` not started here alone.
- Commit per task, `ui: <what changed> (GUI-5)`. Never push. `TODO.md` /
  `DONE.md` are updated by `/todo`, not here.
- References: `docs/references/INDEX.md` first. Only **ufc-3-340-02** applies
  (scaled distance, already cited in `ui/scaled_distance.py`, D24).
