# GUI redesign — the approved design and how to build it

**Status:** approved by the owner on 2026-09-28, screen by screen, on a Claude Design
canvas. This document is the specification. `TODO.md` → track `GUI` only orders it.
Owner's words: *"In principle yes, implement everything."*

**Scope.** The PySide6 GUI in `blastlab/ui/` only. Layout, look, navigation and the
small behaviours listed here. **Nothing numerical changes**: no solver, no default,
no file format, no export content, no case JSON key. One piece of wiring is new
(the 1D → 3D chain route, §8.3); the engine already supports it.

**Out of scope, on purpose.**

- `blastlab/gui/` (Tkinter) stays exactly as it is, behind `--tk`, forever
  (CLAUDE.md §9). It keeps its own palette in `gui/theme.py` and its `logo.gif`.
  Do not describe it as deprecated anywhere. Run its `test_gui_*` suites whenever a
  task touches a shared neutral module (`core/`, `services/`, `models/`, `solvers/`,
  `output/`).
- The 3D viewer's own look (`blastlab/viz3d/viewer.py`, child process).
- The HD 1.3 report and the SBEDS export content.

---

## 1. Where the design lives

- **The boards, copied from the canvas**, are in
  [`docs/design/gui-redesign/boards/`](design/gui-redesign/boards/). They are
  HTML with inline styles. Read them as the visual source of truth: exact colours,
  sizes, spacing, copy. They do not run offline (they need the canvas runtime), so
  read the source; do not try to open them in a browser.

  | Board file | Screen |
  |---|---|
  | `Logo_Final.dc.html` | Logo, app icon, pixel-drawn 16/32, colours, rules |
  | `BC_Combined.dc.html` | **01 Setup** (interactive: tree selection, AMR, trigger, init mode) |
  | `Run.dc.html`, `Run_Finished.dc.html` | **02 Run**, while running and when finished |
  | `Run_Chain.dc.html` | 02 Run while a chain runs (stage strip) |
  | `Results.dc.html` | **03 Results** (Field / Gauges / 3D) |
  | `Results_Chain.dc.html` | 03 Results for a chain (stage tabs) |
  | `Chain.dc.html` | **Chain** (routes, pipeline, stage editor) |

- The canvas itself (owner only, private): https://claude.ai/artifact/EbHt1TkBAqXKPv8gYM1nxq
- The usability findings the design answers: [`docs/UX_REVIEW.md`](UX_REVIEW.md)
  (findings 1-27 and L1-L14 are cited below as UX-n).

**Mockup values are samples.** Every number shown during a run, every gauge peak
and every result value on the boards is illustrative. The app shows its real values.
The sample case on the boards is 2D axisymmetric, blastFoam, 1 kg TNT at z = 2 m,
4 × 4 m, cell 0.025 m, Wall 1 at r 3.0-3.2 m, gauges G1 (2.95, 0.50), G2 (2.95, 1.50).

---

## 2. Design system

### 2.1 Colours — dark (the default)

Keep every existing key of `ui/theme.py` (`bg card card2 border entry accent
accent_hover text muted view danger danger_hover error warn ok seg`) so no widget
breaks, re-pointed to the new values, and **add** the new keys below.

| Key | Dark | Use |
|---|---|---|
| `bg` | `#0b0b0c` | window background |
| `panel` | `#0e0e10` | side panels, docks |
| `card` | `#111113` | cards |
| `card2` / `tile` | `#141416` | stat tiles, plot backgrounds |
| `view` | `#0d0d0f` | the model / live-view area |
| `hover` | `#1c1c1f` | hover, small buttons |
| `seg` | `#2a2a2f` | selected segment |
| `border` | `#1f1f23` | dividers |
| `border2` | `#242428` | card borders |
| `entry` | `#0b0b0c` | input background |
| `entry_border` | `#2c2c31` | input border |
| `text` | `#f2efe9` | primary text (warm white) |
| `text2` | `#cfcac2` | secondary text |
| `muted` | `#a8a39b` | labels |
| `faint` | `#8f8a82` | captions, units |
| `num_dim` | `#6f6a63` | unselected step numbers |
| `accent` | `#ff6a2b` | brand orange: primary buttons, selection, the front |
| `accent_hover` | `#ff7f47` | |
| `on_accent` | `#1a0d06` | text/icons on orange (never white) |
| `accent_text` | `#ff8a55` | orange text on dark |
| `accent_soft` | `#ffb896` | Z values, hand-off names |
| `accent_bg` | `#1d1511` | selected row / tinted card |
| `accent_border` | `#5a3522` | border of tinted cards |
| `gauge` | `#4cc9f0` | gauges everywhere (cyan: told apart from orange by hue *and* lightness) |
| `gauge_bg` | `#0f1a1f` | selected gauge row |
| `ok` | `#7ddc9a` | case OK, ✓ |
| `ok_bg` / `ok_border` | `#121814` / `#24302a` | the "Case OK" pill |
| `warn` | `#f5d061` | unsaved dot, warnings (yellow, lighter than the orange) |
| `danger` | `#ff5c7a` | errors |
| `stop_bg` / `stop_border` / `stop_text` | `#26141a` / `#6b2a37` / `#ff9aac` | the Stop button |
| `title_bar` | `#202024` | (drawn by Windows; listed for the mockups only) |

### 2.2 Colours — light

Not drawn on the canvas; derive it with the same roles. Proposed:
`bg #f4f3f0`, `panel #faf9f7`, `card #ffffff`, `tile #f1efeb`, `view #ecebe7`,
`hover #e9e6e1`, `seg #dcd8d1`, `border #e2ded7`, `border2 #d8d3cb`,
`entry #ffffff`, `entry_border #cdc7be`, `text #1f2430`, `text2 #3a3f4a`,
`muted #5f6368`, `faint #7a7e85`, `accent #ff6a2b` (buttons keep `on_accent`
dark text), `accent_text #c7430f`, `accent_soft #b4461c`, `accent_bg #fbe9df`,
`gauge #0e7fa6`, `ok #2f9e44`, `warn #b07d00`, `danger #d6336c`.
Every text colour must reach 4.5:1 on its background (3:1 at 24 px and up). Check it
with a script, not by eye, and write the ratios in the task report.

### 2.3 Type

| Role | Family | Weight / size |
|---|---|---|
| display: step titles, numbers in stat tiles, the wordmark | **Space Grotesk** | 600-700; 15-26 px |
| body, labels, buttons | **IBM Plex Sans** | 400-600; 12.5-14 px |
| values, units, paths, the log, tables | **IBM Plex Mono** | 400-600; 11.5-14 px |

All three are SIL OFL fonts. **Bundle the TTF files** under `blastlab/ui/fonts/`
with their `OFL.txt`, load them with `QFontDatabase.addApplicationFont` at start-up,
and fall back to `Segoe UI` / `Consolas` if a file is missing (never crash). Source:
the `google/fonts` repository (`ofl/spacegrotesk`, `ofl/ibmplexsans`,
`ofl/ibmplexmono`). Keep the download small: only the weights used.

### 2.4 Shapes and spacing

Radius 7-8 px on inputs and small buttons, 9-10 px on segmented controls and cards,
12 px on large cards, pill (height / 2) on the workflow steps. Input height 34-36 px,
tree rows ≥ 44 px, primary buttons 44-56 px. Gaps 8 / 12 / 16 / 20 px. No shadows,
no gradients, no blur (QSS cannot do them and the design does not use them).

### 2.5 Components (build each once, in `ui/widgets.py` or a new `ui/components.py`)

- **Segmented control** (exists: `Segmented`) — restyle: `seg` background for the
  selected segment, `muted` text for the others.
- **Toggle switch** — a `QCheckBox` subclass painted as a 42-46 × 24-26 track with a
  white knob; `accent` when on, `#3a3a40` when off. Keyboard and screen-reader
  behaviour of a checkbox.
- **Stat tile** — caps label 10.5 px letter-spaced, value in Space Grotesk 21-26 px,
  a caption line; optional thin bar (memory). Variant `accent_bg` for the Z tile.
- **Tree row** — number (Space Grotesk 12.5, `num_dim` or `accent_text` when
  selected) · title · a mono caption under it · a status mark at the right
  (✓ `ok`, ! `warn`, ✗ `danger`). Selected row: `accent_bg` fill.
- **Dock with tabs** — tab strip with a 2 px `accent` underline on the active tab.
- **Banner** (finished run) and **Hand-off card** (tinted `accent_bg`).
- **Icons** — keep drawing them with `QPainter` in `theme.py` (no asset files), as
  thin stroked outlines, 1.75 px at 24 px.

---

## 3. Logo and app icon (board `Logo_Final`)

A front stepping across a regular 8 × 8 grid, with a faint wake behind it; the
wordmark **BLASTLAB** in Space Grotesk Bold, capitals, tracking +8 %, `LAB` orange.

Draw it with `QPainter` from the rectangles below (no image files), in
`theme.py` next to the other icons. Three hand-tuned sizes; never scale one down
below 24 px.

- **64 (and larger):** frame `rect(8, 8, 48, 48)` stroke 2.5, radius 3; grid lines
  every 6 units from 14 to 50, stroke 0.75 (`#353a41` dark / `#d3d8df` light);
  front cells (5 × 5 with a 0.5 inset, radius 1) at
  (8,20) (14,20) (20,20) (20,26) (26,26) (32,26) (32,32) (32,38) (38,38) (38,44) (38,50);
  wake cells, same size at 35 % opacity, at
  (8,26) (14,26) (20,32) (26,32) (26,38) (32,44) (32,50).
- **32:** view box 32; frame `rect(3, 3, 26, 26)` stroke 2; 3 × 3 cells; front at
  (4,10) (7,10) (10,10) (10,13) (13,13) (16,13) (16,16) (16,19) (19,19) (19,22) (19,25);
  wake at (4,13) (7,13) (10,16) (13,16) (13,19) (16,22) (16,25); grid lines at
  7.5 … 25.5, 1 px, `#2c3137`.
- **16:** view box 16; frame `rect(1.5, 1.5, 13, 13)` stroke 1; no grid, no wake;
  steps (2,4,3,2) (5,5,2,3) (7,7,2,2) (8,9,3,2) (10,11,2,3). Crisp edges.
- **App icon:** the 64 mark on a `#1f1c1b` rounded square (radius ≈ 20/88).
  Build one `QIcon` with 16, 24, 32, 48, 64, 128, 256 pixmaps and set it on the
  `QApplication` and the main window. Windows taskbar grouping: set an explicit
  AppUserModelID (`blastlab`) so the icon, not Python's, shows on the taskbar.
- Colours: front `#ff6a2b` on dark, `#e0501a` on light; frame and text `#e7eaee` /
  `#1f2430`; `LAB` on light `#c7430f`.
- **The ELSL logo leaves the Qt window.** It stays in the Tk app (`logo.gif`).

---

## 4. The window frame (all screens)

Board `BC_Combined` shows it; `Run`, `Results`, `Chain` repeat it.

- **No sidebar.** A 64 px top bar, left to right: mark (30 px) + BLASTLAB wordmark ·
  the workflow as pills **01 Setup → 02 Run → 03 Results** (selected = light pill,
  `bg` text; a ✓ after a step that is done) · a divider · **Chain 1D → 2D → 3D** ·
  (spacer) · the case name (Space Grotesk 17) with `● unsaved` in `warn` when
  dirty · the solver chip **blastFoam · WSL ready** (status dot `ok` / `warn` /
  `danger`) · the dimension segmented control **0D · HD 1.3 | 1D | 2D | 3D**.
- **The solver switch** is the chip: clicking it opens a small menu with
  *native / blastFoam*, the WSL line (`ready · 14 cores · 63 GB VM`), and
  *Re-detect*. Same behaviour as the sidebar switch today (`MainWindow.set_solver`).
- **File actions** live on the case name: it is a button that opens a menu —
  Open… (Ctrl+O), Save (Ctrl+S), Save as… (Ctrl+Shift+S), Recent ▸, Dark mode.
  (UX-8. Save in place when the case has a path; Save as otherwise.)
- **Status bar** (28 px): WSL status · a context line · the shortcuts
  `Ctrl+S save · F5 run · Shift+Esc stop · v1.0.0`.
- **Window title:** `<case> · BlastLab`; while a run goes, `<pct> % · <case> ·
  BlastLab` (UX-19); a chain adds `Chain 2/3 ·`. Mirror the progress on the taskbar
  button if it is cheap (`QWinTaskbarProgress` is gone in Qt 6 — the title is enough).
- **Keyboard:** F5 run, **Shift+Esc stop** (not Esc; UX-7), Ctrl+O, Ctrl+S,
  Ctrl+Shift+S, Ctrl+C copies the Results table when it has focus.
- Minimum size stays 1100 × 720. Every screen must still work at that size.

---

## 5. 01 Setup (board `BC_Combined`)

Three columns under the top bar: **model tree** (280 px) · **centre** · **properties**
(340 px).

### 5.1 The model tree

A numbered list with a ✓ per node and a one-line summary. The nodes group the
existing spec cards of `ui/setup_spec.py` (no field is added, removed or renamed):

| Node | Cards (setup_spec) | Summary line example |
|---|---|---|
| 01 Threat | Initialization (or Charge in 1D); Extra charges; Detonation points | `1.0 kg TNT · z 2.0 m` |
| 02 Domain & mesh | Domain; Dynamic refinement (AMR); Refinement zones | `4 × 4 m · 25 mm` |
| 03 Boundaries | Boundaries | `the run ends at Outer` |
| 04 Structure | Obstacles (children: one row per obstacle) | `1 obstacle` |
| 05 Gauges | Gauges (children: one row per gauge); Trigger gauge | `2 · in front of Wall 1` |
| 06 Solver | Numerics | `linear · no afterburn · CFL 0.4` |
| 07 Output | Outputs; VTK output (ParaView) | `.mp4 · VTK off` |

The 0D (HD 1.3) form keeps its own cards; its tree is simply one node per card.
Scope rules stay: a node or card whose rows are all hidden in the current solver mode
is hidden, never greyed. Status mark: ✗ when a field of the node has a parse error
(the form already knows which fields are red), otherwise ✓. Validation warnings and
notes that name no field stay in the Checks tab (§5.3).

Selecting a node shows **only that node's cards** in the properties panel. This is what
makes the forms short (owner's request). Selecting a child (a gauge, an obstacle)
selects its parent node and scrolls to the row.

Under the tree: **+ Gauge**, **+ Obstacle**, and the **Case OK · N notes** pill
(click → the Checks tab). `Case OK` turns into `N errors` in `danger` when invalid.

### 5.2 Properties

The selected node's cards, rendered by the existing `FieldForm` engine (reuse it;
the task is to split its output by node, not to rewrite it). A caption under the
title explains the node in one line, e.g. Threat: *"The design-basis charge the
structure must resist."* Units sit in a suffix inside the input where the engine
allows it (UX-11).

**Dependent settings open only when switched on** (owner's request). Existing
rules stay; these are added or restated:

- AMR rows only when AMR levels > 0 (exists); *Charge refinement* hidden while AMR is
  on (exists).
- **Profile file** only when *Initialize from* is a profile mode.
- **Trigger gauge**: a switch *End the run at a gauge*. Off = the trigger fields are
  hidden and `trigger_gauge` is blank. On = *Gauge* (a dropdown of the gauges) and
  *On arrival* appear. Same case values as today, only the control changes.
- Animation *Video min/max* only when *Video colours* is manual (exists).
- VTK family settings only when the family is ticked (exists).

A **Derived** card on the Threat node: charge radius, height of burst, nearest gauge
with its Z. Read-only.

### 5.3 Centre

- **Live-number strip** (top): Charge · Cells · MPI ranks · Memory (with a bar of the
  VM) · **Z at gauges** (min–max) · the big **Run F5** button with **Initialise** under
  it. Take every number from what validation already computes
  (`services/validation.py`, `solvers/foam/env.plan_run`, `core/hardware`) — never
  re-derive a number in the GUI. If a value is not available (native mode, 0D), hide
  its tile.
- **Model view:** the existing preview, plus: dashed **Z rings** at Z = 1, 2, 3 around
  the burst point (toggle *Z rings*, default on), the selected node highlighted
  (charge ring when Threat is selected; gauge halos and dashed lines charge → gauge
  when Gauges is selected), a hover readout `r · z · R · Z`. Toolbar: Z rings, Mesh,
  Fit.
- **Dock** (≈ 210 px) with tabs **Gauges · Checks · Log**. *Gauges* is the gauge table
  of board `C_Bold` / `BC_Combined`: Gauge · r · z · R from charge · Z · Where
  (nearest obstacle face, e.g. "5 cm in front of Wall 1", only when within 0.5 m).
  *Checks* is today's validation report (errors first). Selecting 05 Gauges switches
  the dock to *Gauges*.

**Z, stated precisely.** `Z = R / W^(1/3)`, R the distance from the burst point to the
gauge in the plane of the case (2D axisymmetric: r, z; planar: not shown; 3D: x, y,
z; 1D: r), W the charge mass **as entered** in the form (kg of the selected material,
see TODO `P1-9`). Hide Z when the case starts from a profile, for planar 2D, and for
0D. Label the column `Z [m/kg^1/3]`. Display only; nothing is exported.

---

## 6. 02 Run (boards `Run`, `Run_Finished`, `Run_Chain`)

Three columns: **controls** (280) · **centre** · **live gauges** (340).

- **Controls:** *Where the files go* — Runs folder (+ browse), Model, and the
  resolved path `C:\…\<Runs>\<Model>\` in mono (OUT-1 rules unchanged). **Stop**
  (`stop_*` colours, shows `Shift+Esc`) while running; **Run again** (orange) when
  finished; a square **3D view** button. **Step through** — a collapsed section; open
  it for *Initialise model*, **+1 +10 +100 +1000**, *To the end*, *Pause* (today's
  Exec row). **Live view** — Refresh every [auto] seconds/steps; a switch *Colour
  range: auto*; **Min / Max [kPa] appear only when it is off**. At the bottom a link
  back to Setup: `Setup: case OK · 368 k cells`.
- **Progress strip:** Progress (`78 %`, a bar, and `4 min 18 s elapsed · about
  1 min 15 s left`; the estimate appears only after 5 % and is a linear
  extrapolation of the progress fraction) · Time [ms] · Step + dt · p max [kPa] ·
  (Cells, AMR runs only — today's rule).
- **Live view** as today (Live slice | Gauges | 3D view, Show mesh), with a colour bar
  and the time on the plot.
- **Dock under the view** (≈ 140 px): **Log · Messages · Earlier runs**, with **Copy**
  and **Save log…** (UX-18). The log of a finished run is kept per run, not cleared at
  the next start.
- **Live gauges (right):** the selected gauge enlarged (trace, peak marked, a *now*
  line), then a **compact list sorted by Z**: gauge · Z · a 90 px sparkline · peak
  so far, or `waiting` in `faint` before the wave arrives. Click a row to enlarge it.
  Owner: runs usually have 5 or more gauges. Reuse `live_gauges.py` data.
- **Stop confirms after 30 s** of run time: *"Stop <model> at 78 %? It has been
  running for 4 min 18 s. blastFoam keeps what it has written, so you can resume it
  later from the runs list."* [Keep running] [Stop the run]. Under 30 s: stop at once.
  (The resume sentence only for blastFoam.)
- **When a run ends:** a green banner *Result ready: <model> · <how it ended>. Files
  in <path>* with **Open in 03 Results →**; a **Windows notification**
  (`QSystemTrayIcon.showMessage`, tray icon created on demand with the app icon,
  removed after) *"<model> finished in 5 min 31 s. Highest peak: G6, 296 kPa at
  2.21 ms."*, clicking it raises the window on Results; the window title shows
  `✓ Done`. Errors keep today's dialog path.
- **Chain running** (board `Run_Chain`): a strip under the top bar
  `CHAIN · <model> · 01 1D ✓ 9 s → 02 2D 78 % → 03 3D waiting`, and the title
  `Chain 2/3 · 78 % · <model> · BlastLab`.
- The **HD 1.3 (0D) run** keeps its worker path; show it in this screen's progress
  strip as indeterminate, instead of freezing (UX-1 is a separate item; do not widen
  this task to it).

---

## 7. 03 Results (boards `Results`, `Results_Chain`)

Three columns: **results + method** (280) · **centre** · **export** (320).

- **Results list** (not a dropdown): name, a `latest` / `chain` badge, and
  `2D axisym. · blastFoam · 5 min 31 s`. **Load a run…** (today's Foam runs dialog)
  and **Remove**.
- **How it was computed** (UX-15), from `res.meta`: Solver (+ version when known),
  Charge, Detonation, Afterburn, Mesh (cell, refined cell), Parallel, Ended (how and
  when). Buttons **Show case** and **Load into 01 Setup**. Show only what the meta
  holds; never guess.
- **Views: Field · Gauges · 3D** (owner: Fields and Animation become one).
  - **Field:** field **Overpressure | Density | Speed** (today's list; keep the MPL
    kinds such as profiles/isosurface where they exist), colour scale **whole run |
    each frame | manual** (Min/Max only for manual — the same control drives the
    animation export, as today), Show mesh; the map with a colour bar and a hover
    readout `r · z · value`; under it a **time bar**: Play/Pause, the time, a slider
    over the snapshots with cyan ticks at the selected gauge's arrival, `6.31 ms ·
    61 frames`, speed, **This frame .png**.
  - **Gauges:** all gauges on one plot, the selected one in `gauge` colour with its
    **positive phase shaded**, the others grey; a readout of the selected gauge; the
    **summary table**: Gauge · **Z** · Peak [kPa] · Arrival [ms] · t peak [ms] · Pos.
    phase [ms] · Pos. impulse [**kPa·ms**] · Net impulse [kPa·ms] · Phase ended.
    Click a row to plot it. **Copy table** (Ctrl+C, tab-separated with headers;
    UX-14). The caption says *net impulse includes the negative phase* (documented
    behaviour, CLAUDE.md §7).
  - **3D:** the embedded viewer, unchanged.
- **Impulse unit.** Show kPa·ms on screen (the same number as Pa·s). **The CSV/TSV
  exports keep their current columns and units.**
- **No Kingery-Bulmash columns and no run-to-run overlay** — owner decision.
- **Export (right):** **Data** — Summary .csv, Gauge traces .tsv, Field snapshot .csv,
  Profile (for a Chain) .npz/.txt, VTK for ParaView (blastFoam only);
  **Figures** — All plots .png, Report .html, Animation .mp4/.gif. A button that is
  not available hides (mode) or disables with its why-not tooltip (today's rule).
  A running export shows `writing… 42 %` (or an indeterminate bar) in place of its
  button and cannot be started twice (UX-13). *Title on figures* input.
  **Open the 3D viewer** at the bottom.
- **A chain is one result** with a **STAGE 1D | 2D | 3D** tab strip before the view
  tabs; each stage shows its own views and exports.

---

## 8. Chain (board `Chain`)

### 8.1 Layout

- **Route buttons:** **1D → 2D → 3D · 1D → 3D · 1D → 2D · 2D → 3D**. They replace the
  three stage checkboxes; no invalid combination can be chosen. (A single stage is a
  normal run, not a chain.)
- **Pipeline:** one card per stage — number, title (`1D spherical` / `2D
  axisymmetric` / `3D`), the stage's solver chip, a key line, `● case OK` (live), its
  folder `\1d \2d \3d` — joined by orange arrows labelled with the hand-off file.
  Clicking a card selects it. On the right, **Run chain** with `3 stages · into
  \<model>\`.
- **Stage editor** below: the Setup layout (§5) for the selected stage — its tree,
  preview and properties — built from the same components. The properties panel adds
  **Solver for this stage** (today's per-stage override) and two cards: **Hand-off in**
  (file + what it carries) and **Hand-off out**.
- **Copy from 01 Setup** and **Load case…** per stage (UX-16; `set_stage_case`
  exists but was never wired).
- **Live validation per stage**, with the same debounce as Setup (UX-16).
- **A new stage starts from 01 Setup:** charge, material and solver from the open case;
  everything else from the dimension's defaults (owner decision).

### 8.2 Hand-offs (text shown in the cards)

| Route edge | File (at the model root) | Hand-off in text |
|---|---|---|
| 1D → 2D | `handoff_1d_to_2d.txt` | remapped onto the axis; burst height from the 2D form |
| 2D → 3D | `handoff_2d_to_3d.npz` | swept around the burst axis; burst height from the 2D profile |
| **1D → 3D** | **`handoff_1d_to_3d.txt`** (new) | placed around the burst point; burst height from the 3D form |

### 8.3 The new 1D → 3D wiring

Today `ChainPanel.run()` wires only 1→2 and 2→3, so the stage set {1, 3} runs 3D from
its own charge. Both backends already accept a 3D case with
`init_mode = 'profile1d'` (`solvers/solver3d.py`, `solvers/foam/writer.py` →
`profiles.remap_profile_1d_to_3d`). Add, in the same place as the other two:

```
if 1 in cases and 3 in cases and 2 not in cases:
    cases[1].profile_file = <model root>/handoff_1d_to_3d.txt
    cases[3].init_mode = 'profile1d'
    cases[3].profile_file_in = <same path>
```

Then `stage_errors` validates as for the other routes (the native → blastFoam
conflict rule applies unchanged). **Tests:** a new fast test that builds the {1, 3}
chain and asserts the wiring and that `stage_errors` is empty for a valid pair; plus
one tiny **native** 1D → 3D chain run end to end (small domain) asserting the 3D stage
starts from the profile (non-ambient field at t0 around the burst). No WSL run is
required for acceptance; if one is done, check `pgrep` first (CLAUDE.md §8.6).
`test_regression.py` must stay byte-green.

### 8.4 Results and Run

As §6 (stage strip) and §7 (one result, stage tabs).

---

## 9. Rules for every GUI task

- **Numbers:** unchanged, everywhere. `python blastlab/tests/test_regression.py`
  green before and after each task.
- **Forms:** every field key, parser, default, scope and group of
  `ui/setup_spec.py` stays; case JSON load → save round trips byte-identically
  (`test_ui_parity.py`, `test_ui_setup_form.py`).
- **The GUI process never imports VTK or `matplotlib.pyplot`**
  (`test_ui_no_vtk_in_main.py`, `test_ui_no_mpl_pyplot.py`).
- **Hide, never grey,** controls that do not apply to the solver mode.
- **Committed tests.** Owner decision 2026-09-28: a `test_ui_*.py` assertion that pins
  *layout the owner has now replaced* (a card title, the sidebar, a widget's parent,
  a button text that the design renames) may be updated to the new layout. An
  assertion about **behaviour or numbers** may not be weakened. Every changed
  assertion is listed in the task report with the reason. `test_gui_*` (Tk) are not
  touched.
- **The QA harness** (`blastlab/tests/_qa_ui_harness.py`, 63 scenarios) drives the
  sidebar today; update its navigation helpers to the new top bar so every scenario
  still runs. Screenshots go to `~\blastlab_qa\<stamp>\shots`.
- **Before building the GUI in any test or harness:** `auto_cleanup` must be off
  (CLAUDE.md §8.2 — the harness writes private settings; do not bypass that).
- **Measure on the real platform** for anything about geometry, embedding or
  flicker (CLAUDE.md §8.7): `QT_QPA_PLATFORM` unset, Win32 through ctypes.
- **No PowerShell string round trips** on any file (CLAUDE.md §8.1).
- **Commits:** `ui: <what changed> (GUI-n)`; one commit per task at least.
- **Stage only your own files.** Six paths in the working tree belong to other work
  and must never be staged: `docs/references/INDEX.md`,
  `docs/references/ViperTheoryManual_Client.pdf`,
  `docs/references/ViperTheoryManual_Client.txt`, `docs/references/viper_vtk_sample/`,
  `docs/qa/2026-09-27-out-3/`, `docs/qa/2026-09-27-viewer-polish/`.

---

## 10. Tasks, in order

Each is one `TODO.md` id. Sizes: S < 1 h, M ≈ half a day, L ≈ a day or more.

| Id | Task | Size | Depends on |
|---|---|---|---|
| `GUI-1` | Design tokens and fonts (§2) | M | — |
| `GUI-2` | Logo and app icon (§3) | S | GUI-1 |
| `GUI-3` | Window frame: top bar, workflow pills, solver chip, case menu, status bar, title, shortcuts (§4) | L | GUI-1, GUI-2 |
| `GUI-4` | Shared components (§2.5): toggle, stat tile, tree row, dock tabs, banner | M | GUI-1 |
| `GUI-5` | 01 Setup: tree + properties + centre (§5) | L | GUI-3, GUI-4 |
| `GUI-6` | 02 Run (§6), including the Stop confirmation and the finish notification | L | GUI-3, GUI-4 |
| `GUI-7` | 03 Results (§7), including Field = Fields + Animation and the table copy | L | GUI-3, GUI-4 |
| `GUI-8` | Chain wiring 1D → 3D (§8.3), with its tests | S | — |
| `GUI-9` | Chain screen (§8.1, 8.2) + chain in Run and Results (§8.4) | L | GUI-5, GUI-6, GUI-7, GUI-8 |
| `GUI-10` | QA harness navigation on the new frame, full harness pass, light-mode check, 1100 × 720 check | M | all |

### Acceptance, per task

- **GUI-1:** every old key still resolves; new keys exist in dark and light; the three
  font families load (or fall back without error) and `theme.font()` has
  `display`, `body`, `mono` kinds; a script prints the contrast ratio of every text
  role on its background, all ≥ 4.5 (≥ 3 for display ≥ 24 px); fast test matrix green.
- **GUI-2:** the mark renders at 16/32/64 from the rectangles in §3 (a test compares a
  few pixel colours at known coordinates); the window and taskbar show the new icon;
  the ELSL logo is gone from the Qt window and still present in Tk.
- **GUI-3:** no sidebar; the pills switch Setup / Run / Results / Chain; the solver chip
  switches mode exactly as the old switch did (`test_ui_three_surfaces.py`,
  `test_ui_parity.py` green); Open/Save/Save as/Recent work; F5, Shift+Esc (and not
  Esc), Ctrl+O/S/Shift+S work; the title shows the case and `●`/unsaved state;
  screenshots of every screen at 1100 × 720 and 1600 × 1000 in the report.
- **GUI-4:** each component has an offscreen test (toggle state and signal, tile text,
  tree-row selection signal).
- **GUI-5:** every spec field is reachable through exactly one node; load → save of
  every committed case JSON round trips byte-identically; selecting a node shows only
  its cards; the trigger switch writes the same case values as the old blank/number
  field; Z values for the sample case: G1 3.31, G2 2.99 (R = Z for 1 kg); strip numbers
  equal the validation report's numbers for the same case (asserted, not eyeballed).
- **GUI-6:** Stop under 30 s stops at once, over 30 s asks (offscreen test with a fake
  clock); Shift+Esc stops, Esc does not; the list sorts by Z and shows `waiting`
  before arrival; the finish banner and the notification appear on a real short native
  run (screenshot); the log of the previous run is reachable.
- **GUI-7:** the three views work on a native 1D and a native 2D result; Field replaces
  both old tabs (the animation export still uses the chosen colour scale — assert on
  the export options); Copy table puts tab-separated text with headers on the
  clipboard; exported CSV/TSV are byte-identical to before for the same result.
- **GUI-8:** as §8.3.
- **GUI-9:** the four routes wire the right hand-offs (fast test per route); per-stage
  live validation; Copy from Setup and Load case fill the stage; a native 1D → 2D chain
  runs from the new screen and shows as one result with stage tabs.
- **GUI-10:** `_qa_ui_harness.py` runs all scenarios on the new frame; `findings.jsonl`
  has no new finding against the pre-redesign baseline other than intended layout
  changes (list them); light mode screenshots of every screen; nothing clipped at
  1100 × 720.

---

## 11. Risks

- **The Setup split (GUI-5) is the riskiest change:** `FieldForm` builds cards in
  columns today. Split its *placement*, not its parsing — keep one `FieldForm`
  instance per dimension so `get_case` / `set_case` do not change.
- **Qt style sheets** cannot draw everything on the boards (pill fills with borders are
  fine; per-glyph colours are fine; no shadows are used). When something cannot be
  styled, paint it in `paintEvent`; do not add a dependency.
- **Fonts on Windows:** the Microsoft Store Python sandbox — load fonts from the
  package directory, not from `%WINDIR%\Fonts`.
- **The embedded 3D viewer** (`view3d_host.py`) moves when its parent layout changes
  (CLAUDE.md §8.7 lists four wrong fixes). Re-measure its placement on the real
  platform after GUI-3, GUI-6 and GUI-7.
