# GUI-7b measurements against the board

Batch [`2026-09-29-gui-results`](../../batches/2026-09-29-gui-results.md), T7.
Board: `docs/design/gui-redesign/boards/Results.dc.html`. The viewer rules
are in [`measurements-7b.md`](measurements-7b.md); 7a's are in
[`measurements-7a.md`](measurements-7a.md).

## How it was measured

- `blastlab/tests/_e2e_ui_results.py --with-3d --shots DIR` at `7e623ba`,
  on the real platform (Windows, 1920 × 1080, 100 %), throwaway settings.
- Three tiny native runs through Run: the Phase 0 1D case, the Phase 0 2D
  axisymmetric case with `record_frames = 12`, and that case planar. A
  tiny native 3D result goes into the embedded viewer.
- The numbers are the widgets' own geometry, written to `measure-7b.json`
  per mode and size. The contrast ratios come from the script at the foot
  of this file. The screenshots are `win.grab()`; the 3D one is a screen
  grab, because the viewer is a native child window.

## Geometry (dark and light identical)

| What | Board | 1600 × 1000 | 1100 × 720 |
|---|---|---|---|
| Columns: results · centre · export | 280 · flex · 320 | 280 · 968 · 320 | 280 · 468 · 320 |
| View tabs (in a 38 px strip) | 32 | 32 | 32 |
| Export buttons | 40 | 40 | 40 |
| Export busy strip | ≥ 40 | 48 | 48 |
| Open the 3D viewer | 42 | 42 | 42 |
| Field controls row | one line | 1 line | 3 lines: Field · Colours · Show mesh |
| Time bar | one line, 64 | one line, 61 px | two lines, 101 px |
| Play | 40 × 40 round | 40 × 40 | 40 × 40 |
| Speed, This frame .png | 32 | 32 · 32 | 32 · 32 |
| Time-bar slider | flex | 366 px | 230 px |
| Arrival tick (G1 of the 2D run) | cyan | frame 44 of 97 | frame 44 of 97 |
| Gauges plot · table height | flex · 6 rows | 545 · 119 px | 222 · 129 px |
| Gauges table width | full | 906 px | 406 px |
| Table headers | one line | two lines (the one-line set needs more than 906 px, D102) | two lines |
| Table scrolls sideways / down | – | 0 / 0 px | 500 / 0 px (every row on screen) |
| Planar result: Z column | – | hidden | hidden |

- **The time bar** is one line from 620 px of its own width. That is a
  centre of about 682 px, or a window of about 1310 px (measured with the
  2D run). Below that, Play, the time and the slider keep the first line,
  and `0.38 ms · 97 frames`, the speed and This frame .png go under it
  (D113).
- **The controls row** wraps by groups (D114). At 1600 all five fit on one
  line. At 1100 they take three lines. The map is then 406 × 210 px, and
  the plot's own box 262 × 121 px (906 × 646 and 762 × 557 at 1600 ×
  1000). See the 1100 × 720 shots and suspected issue 2 of the report.
- **The hover readout** reads `x 0.41 · z 0.80 m` / `overpressure 1944 kPa`
  on the replay (the page's own axis names, D111). The real pointer put
  it there (`QTest.mouseMove` on the view's viewport).
- **The method card** of the blastFoam-shaped result: Solver blastFoam ·
  Charge 1 kg TNT · z 0.7 m · Detonation linear · Afterburn none · Mesh
  cell 10.5263 mm · finest 2.63 mm · Ended (the stop reason) · t = 0.375
  ms.

## Screenshots (`gui7b-<mode>-<size>-<what>.png`, dark and light, 1600 × 1000 and 1100 × 720)

- `field-replay`: the 2D replay mid-way, whole-run scale, with the tick.
- `field-manual-hover`: manual 0-50 kPa with Min / Max, and the hover
  readout.
- `gauges-2d`: G2 selected, with its positive phase shaded and the
  readout.
- `gauges-planar`: the planar run, with no Z column.
- `field-1d` and `gauges-1d`: the 1D profiles and gauges.
- `method-native` (the model folder's rows) and `method-foam` (the
  blastFoam-shaped copy with a loaded run's `case.json`).
- `export-busy`: a real Animation export being written.
- `view3d`: the native 3D result in the embedded viewer (a screen grab).

## Contrast (WCAG ratio; 4.5 for text, 3.0 for a line or a glyph)

Every new pair, both modes. The two that failed at first were fixed
(D121: the Field caption, and the light selected-row fill).

| Pair | Dark | Light | Min |
|---|---|---|---|
| captions, units, time bar length (faint / panel) | 5.63 | 5.00 | 4.5 |
| Field caption under the view (muted / view) | 7.75 | 5.07 | 4.5 |
| Gauges plot caption (faint / tile) | 5.37 | 4.58 | 4.5 |
| table header, Summary caption, Ctrl+C (faint / card) | 5.50 | 5.26 | 4.5 |
| busy `writing…`, Show mesh on (accent_soft / accent_bg) | 10.75 | 4.65 | 4.5 |
| readout G2 · Z (gauge / tile) | 9.57 | 4.55 | 4.5 |
| readout peak, impulse (text / tile) | 16.03 | 13.51 | 4.5 |
| table Gauge cell (gauge / card) | 9.81 | 5.22 | 4.5 |
| table Z cell (accent_soft / card) | 11.27 | 5.48 | 4.5 |
| table numbers (text / card) | 16.43 | 15.52 | 4.5 |
| table Net impulse (text2 / card) | 11.57 | 10.55 | 4.5 |
| Phase ended yes (muted / card) | 7.52 | 6.05 | 4.5 |
| Phase ended no (warn / card) | 12.64 | 5.00 | 4.5 |
| selected row: Gauge (gauge / its fill) | 9.19 | 4.80 | 4.5 |
| selected row: Z (accent_soft / its fill) | 10.56 | 5.04 | 4.5 |
| selected row: numbers (text / its fill) | 15.40 | 14.28 | 4.5 |
| selected row: Net impulse (text2 / its fill) | 10.84 | 9.71 | 4.5 |
| selected row: yes (muted / its fill) | 7.05 | 5.57 | 4.5 |
| selected row: no (warn / its fill) | 11.85 | 4.60 | 4.5 |
| hover, first line (text / bg) | 17.14 | 13.98 | 4.5 |
| hover, value (accent_soft / bg) | 11.76 | 4.94 | 4.5 |
| time (text / panel) | 16.80 | 14.75 | 4.5 |
| time unit ms (muted / panel) | 7.69 | 5.75 | 4.5 |
| Colours, Min, Max, Plane (muted / panel) | 7.69 | 5.75 | 4.5 |
| segments, not selected (muted / bg) | 7.85 | 5.45 | 4.5 |
| segment selected (text / seg) | 12.44 | 10.93 | 4.5 |
| Copy table, This frame (text2 / card) | 11.57 | 10.55 | 4.5 |
| This frame .png on the time bar (text2 / panel) | 11.83 | 10.03 | 4.5 |
| Play glyph (on_accent / accent), non-text | 6.66 | 6.66 | 3 |
| arrival tick (gauge / panel), non-text | 10.03 | 4.96 | 3 |
| selected curve (gauge / tile), non-text | 9.57 | 4.55 | 3 |
| other curves (grey / tile), non-text | 3.04 | 3.03 | 3 |

The selected row's fill is `gauge_bg` in dark and `#eef7fa` in light
(`gauge_bg` 40 % toward `card`, D121). The grey is `results_gauges.GREY`
(D97).

The script: the WCAG relative luminance of each colour of
`theme.DARK` / `theme.LIGHT`, then `(L1 + 0.05) / (L2 + 0.05)`, the same
formula as `tests/test_ui_theme.py`.
