# GUI-9b measurements — 02 Run's chain strip and 03 Results' STAGE tabs against the boards

Batch [`2026-09-29-gui-chain`](../../batches/2026-09-29-gui-chain.md), T6.
Report: [`2026-09-29-gui-chain-b.implement.md`](../../batches/2026-09-29-gui-chain-b.implement.md).
The embedded-viewer measurements are in [`measurements-9b.md`](measurements-9b.md);
9a's (the Chain screen) in [`measurements-9a.md`](measurements-9a.md).

## How

- **Real platform** (`QT_QPA_PLATFORM` unset, `ensure_qapp(offscreen=False)`,
  Qt platform `windows`), the real `MainWindow` with throwaway settings,
  1920 × 1080 screen, this 8 GB PC, at HEAD `5ebd616`.
- The Run and Results scenes are driven through the window's **own** run
  callbacks (`on_running`, `on_run_started`, `on_progress`, `on_result`,
  `on_finished`) with a fake run clock (stage 1 lands at 9 s, stage 2 at
  78 %, the chain done in 41 min) and the real native Phase 0 1D / 2D / 3D
  results of `test_char_native_api`, each given a stage folder with a
  manifest (created / finished) so the list caption has its duration. A real
  run's shots: the e2e's `e2e9b_*` (native 1D → 2D from the Chain screen,
  1280 × 840, dark).
- Widths and heights are the widgets' own, read after 700 ms of event
  pumping per scene; `measure-9b.json` holds every number of the 36 scenes.
- Clipping: `test_ui_parity.clipped(win)` on every scene: **empty in all 36**.
- Contrast: WCAG 2.x relative luminance of the palette colours
  (`ui/theme.py` `DARK` / `LIGHT`, `theme.chain_tint()`), computed by script.
- Screenshots: `QWidget.grab()` (no viewer child in these scenes),
  `gui9b-<mode>-<size>-<scene>.png`: the Chain screen re-shot at HEAD (route
  123 on stage 2's 00 Stage, route 13 on stage 3, a stage error, stage 2 on
  05 Gauges), 02 Run with stage 2 running and after the end (strip + banner),
  03 Results with the chain on each STAGE tab; dark and light, 1100 × 720 and
  1600 × 1000.

## 02 Run — the chain strip vs board Run_Chain (lines 60-70)

| Element | Board | 1600 × 1000 | 1100 × 720 |
|---|---|---|---|
| Where | full width under the top bar | the Run centre's `chain_slot` (D157), 932 px | the same, 432 px |
| Strip height | 30 + 2 × 10 = 50 | 50 (one row) | 74 (two rows: eyebrow + caption, then the pills) |
| Height across stage changes | — | 50 throughout | 74 throughout (S7 asserts it) |
| Pill height | 30, radius 15 | 30 | 30 |
| Pill widths mid-run (`01 1D ✓ 9 s`, `02 2D 78 %`, `03 3D waiting`) | content | 111 / 105 / 125 | 111 / 105 / 125 |
| Pill widths at the end (9 s, 19 min 51 s, 21 min 0 s) | — | 111 / 168 / 161 | 88 / 108 / 108 (fit level 2: `1D ✓ 9 s`, `2D ✓ 19 min`, `3D ✓ 21 min`; the whole pill in its tooltip, D164) |
| Caption | right, 12 px, muted | whole | elided mid-run (`… handoff_2d_to_…`), whole text as its tooltip; whole at the end |
| Eyebrow | `CHAIN · wall_A_chain`, 11 px 600, accent_text | `CHAIN · wall_A` | same |

Notes:

- The strip is a rounded `panel` card, not the board's full-width tinted band
  (it sits in the centre column, D157; D165): `warn` and `faint` stay ≥ 4.5:1
  on it in light mode, which they would not on the tint.
- The light-mode running pill's edge is `accent_text` (D165): `accent` is
  2.72:1 on the light panel, under the 3:1 of a graphic. Dark is the board's.
- One row or two is decided from the widest value each pill can take
  (`59 min 59 s`, `1 h 59 min`), so a stage change never moves the strip
  between forms; the fit level (D164) changes widths only.

## 03 Results — the STAGE tabs and the list row vs board Results_Chain

| Element | Board | 1600 × 1000 | 1100 × 720 |
|---|---|---|---|
| Where | same row as the view tabs, before them | `stage_slot`, the row above the view tabs (D159) | same |
| Group height / tab height | 32 + 2 × 3 + 2 = 40 | 38 / 32 (the plan's 38) | 38 / 32 |
| Group width (three tabs) | content | 203 | 203 |
| Selected tab | `accent`, `on_accent` text | same | same |
| Group fill / frame | `accent_bg` / `accent_border` | the chain tint (= `accent_bg` in dark, D152's blend in light) / `accent_border` | same |
| List row badges | `chain` | `chain` (and `latest` on the newest) | same |
| List row caption | `1D → 2D → 3D · 3 stages · 41 min` | `1D → 2D → 3D · 3 stages · 41 min 0 s` (`fmt_duration`, D160) | same |

The tabs are above the view tabs in every scene (`stage_slot.bottom() <
view tabs.top()`), the slot is 38 px while a chain is selected and hidden at
0 px for a plain result (S8).

## Contrast (every new text and graphic pair, both modes)

| Pair | Colours | Dark | Light | Rule | Pass |
|---|---|---|---|---|---|
| strip eyebrow CHAIN · M | `accent_text` on `panel` | 8.28 | 4.80 | ≥ 4.5 | yes |
| strip caption | `muted` on `panel` | 7.69 | 5.75 | ≥ 4.5 | yes |
| waiting / not run pill (number, name, value) | `faint` on `panel` | 5.63 | 5.00 | ≥ 4.5 | yes |
| stopped pill value | `warn` on `panel` | 12.93 | 4.75 | ≥ 4.5 | yes |
| failed pill value | `danger` on `panel` | 6.49 | 4.80 | ≥ 4.5 | yes |
| stopped / failed pill name | `text` on `panel` | 16.80 | 14.75 | ≥ 4.5 | yes |
| stopped / failed pill number | `muted` on `panel` | 7.69 | 5.75 | ≥ 4.5 | yes |
| done pill name `1D ✓` | `text` on `ok_bg` | 15.69 | 13.60 | ≥ 4.5 | yes |
| done pill duration | `ok` on `ok_bg` | 10.78 | 4.53 | ≥ 4.5 | yes |
| done pill number | `muted` on `ok_bg` | 7.18 | 5.30 | ≥ 4.5 | yes |
| running pill name | `text` on tint | 15.67 | 14.31 | ≥ 4.5 | yes |
| running pill number | `accent_text` on tint | 7.72 | 4.65 | ≥ 4.5 | yes |
| running pill percent | `accent_soft` on tint | 10.75 | 5.05 | ≥ 4.5 | yes |
| strip arrow, lit (graphic) | `accent` dark / `accent_text` light on `panel` | 6.75 | 4.80 | ≥ 3 | yes |
| strip arrow, unlit (graphic) | `faint` on `panel` | 5.63 | 5.00 | ≥ 3 | yes |
| running pill edge (graphic) | `accent` dark / `accent_text` light on `panel` | 6.75 | 4.80 | ≥ 3 | yes |
| running pill edge on its own fill (graphic) | the same on tint | 6.29 | 4.65 | ≥ 3 | yes |
| STAGE eyebrow | `accent_text` on tint | 7.72 | 4.65 | ≥ 4.5 | yes |
| stage tab, unselected | `muted` on tint | 7.17 | 5.58 | ≥ 4.5 | yes |
| stage tab, hovered | `muted` on `hover` | 6.78 | 4.86 | ≥ 4.5 | yes |
| stage tab, selected | `on_accent` on `accent` | 6.66 | 6.66 | ≥ 4.5 | yes |
| chain badge (results list, GUI-7) | `gauge` on `gauge_bg` | 9.19 | 4.52 | ≥ 4.5 | yes |

Before D165 the light running pill's edge was `accent` on `panel`, 2.72:1.

## A chain with a 3D stage in the 3D view

See the report (T6): the tiny native 1 → 3 chain (test_ui_chain C12's
cases) run from the window, its 3D stage opened in the embedded viewer.
