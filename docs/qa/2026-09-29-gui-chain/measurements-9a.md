# GUI-9a measurements — the Chain screen against board Chain

Batch [`2026-09-29-gui-chain`](../../batches/2026-09-29-gui-chain.md), T3.
Report: [`2026-09-29-gui-chain-a.implement.md`](../../batches/2026-09-29-gui-chain-a.implement.md).

## How

- **Real platform** (`QT_QPA_PLATFORM` unset, `ensure_qapp(offscreen=False)`,
  Qt platform `windows`), the real `MainWindow` with throwaway settings,
  1920 × 1080 screen, this 8 GB PC. Default 01 Setup case (2D, blastFoam), so
  every stage is seeded on blastFoam; Model box `CHAIN_SHOTS`.
- Widths and heights are the widgets' own (`width()` / `height()`), read after
  700 ms of event pumping per scene; `measure-9a.json` holds every number.
- Clipping: `test_ui_parity.clipped(win)` on every scene (both modes, both
  sizes): **empty in all 24**.
- Contrast: WCAG 2.x relative luminance of the two palette colours
  (`ui/theme.py` `DARK` / `LIGHT`, plus `theme.chain_tint()` for the selected
  card and the tinted hand-off card), computed by script.
- The screenshots are `QWidget.grab()` of the window on the real platform
  (the Chain screen embeds no viewer child, D134).

## Widths and heights vs the board

| Element | Board | 1600 × 1000 | 1100 × 720 |
|---|---|---|---|
| Stage tree | 272 | 272 | 272 |
| Properties | 340 | 340 | 340 |
| Centre | flex | 940 | 440 |
| Stage card (route 123) | 308 | 308 × 95 | 248 × 95 (gives way, D151) |
| Hand-off link (route 123) | 118 | 118 | 64 (gives way first, D151) |
| Hand-off link (two stages) | 200 | 200 | — |
| Route group / buttons | 38 / 32 (plan) | 38 / 32 | 38 / 32 |
| Run chain | 176 × 56 | 176 × 56 | 176 × 56 |
| Copy from 01 Setup / Load case… | 36 | 136 × 36 / 104 × 36 | same |
| Stage pill | 40 | 40 | 40 |
| Tree row | ≥ 44 | 44 | 44 |
| View tools (Mesh, Fit) | 28 | 28 | 28 |
| Hand-off cards (00 Stage) | 304 inside 340 | 322 × 106 | 312 × 106 |

Notes:

- The route group is 38 px as the plan asks (32 px buttons, 2 px inner margin,
  1 px border); the board's own padding of 3 px would make it 40.
- The Copy / Load buttons, the pill and the route group first measured 38, 26
  and 40 px: a QSS height is the content box, so the 1 px border adds 2, and
  the generic `QPushButton { min-height: 24px }` beat `setFixedHeight(42)` on
  the pill (D41's mechanism). All three are pinned in the QSS now and asserted
  in `test_ui_chain_screen` S2. **Setup's own case pill and + Gauge / +
  Obstacle buttons are 26 px for the same reason** (board 42 / 36): F21, not
  changed here (Setup's behaviour is frozen in this batch).
- A first real-platform pass showed the 00 Stage properties column at about
  490 px at 1100 × 720: the folder note's model path (77 characters, no space)
  was the page's minimum, and D19 widens the column to it. The path now wraps
  (a zero-width space between its characters; separators in Checks messages
  too), and S3 asserts 340 px with that path.

## Contrast (every new text pair, both modes)

| Pair | Dark | Light | Rule |
|---|---|---|---|
| Route label (#chainfield) | 7.85 | 5.45 | ≥ 4.5 |
| Route caption (#chaincaption) | 5.74 | 4.74 | ≥ 4.5 |
| Route button, unchecked | 7.85 | 5.45 | ≥ 4.5 |
| Route button, checked | 17.14 | 13.98 | ≥ 4.5 |
| Card number, selected (accent_text on the tint) | 7.72 | 4.65 | ≥ 4.5 |
| Card number, not selected (num_dim on card; F8) | 3.52 | 2.97 | ≥ 3.0 **below** |
| Card title on card | 16.43 | 15.52 | ≥ 4.5 |
| Card title on the tint | 15.67 | 14.31 | ≥ 4.5 |
| Solver chip (text2 on hover) | 10.43 | 8.48 | ≥ 4.5 |
| Key line on card | 11.57 | 10.55 | ≥ 4.5 |
| Key line on the tint | 11.03 | 9.73 | ≥ 4.5 |
| State ok on card | 11.29 | 5.17 | ≥ 4.5 |
| State warn on card | 12.64 | 5.00 | ≥ 4.5 |
| State danger on card | 6.34 | 5.05 | ≥ 4.5 |
| State ok on the tint | 10.77 | 4.76 | ≥ 4.5 |
| State warn on the tint | 12.06 | 4.61 | ≥ 4.5 |
| State danger on the tint | 6.05 | 4.66 | ≥ 4.5 |
| Folder (faint on card) | 5.50 | 5.26 | ≥ 4.5 |
| Folder (faint on the tint) | 5.25 | 4.85 | ≥ 4.5 |
| Hand-off file name (accent_soft on bg) | 11.76 | 4.94 | ≥ 4.5 |
| Arrow (accent dark / accent_text light, on bg; graphic) | 6.88 | 4.55 | ≥ 3.0 |
| Run chain (on_accent on accent) | 6.66 | 6.66 | ≥ 4.5 |
| Run chain line (muted on bg) | 7.85 | 5.45 | ≥ 4.5 |
| Refusal line (#small, muted on bg) | 7.85 | 5.45 | ≥ 4.5 |
| Tree eyebrow (faint on panel) | 5.63 | 5.00 | ≥ 4.5 |
| Copy / Load (text2 on panel) | 11.83 | 10.03 | ≥ 4.5 |
| Stage pill (text2 on ok_bg) | 11.04 | 9.25 | ≥ 4.5 |
| Header title (text on card) | 16.43 | 15.52 | ≥ 4.5 |
| Header numbers (text2 on card) | 11.57 | 10.55 | ≥ 4.5 |
| Plane caption (faint on card) | 5.50 | 5.26 | ≥ 4.5 |
| 3D hint (muted on card) | 7.52 | 6.05 | ≥ 4.5 |
| Solver for this stage (muted on panel) | 7.69 | 5.75 | ≥ 4.5 |
| Preset line (faint on panel) | 5.63 | 5.00 | ≥ 4.5 |
| HAND-OFF IN title (accent_text on the tint) | 7.72 | 4.65 | ≥ 4.5 |
| HAND-OFF IN file (text on the tint) | 15.67 | 14.31 | ≥ 4.5 |
| HAND-OFF IN text (text2 on the tint) | 11.03 | 9.73 | ≥ 4.5 |
| HAND-OFF OUT title (faint on card) | 5.50 | 5.26 | ≥ 4.5 |
| HAND-OFF OUT file (text on card) | 16.43 | 15.52 | ≥ 4.5 |
| HAND-OFF OUT text (text2 on card) | 11.57 | 10.55 | ≥ 4.5 |
| Checks note row (muted on panel) | 7.69 | 5.75 | ≥ 4.5 |
| Checks warn row (warn on panel) | 12.93 | 4.75 | ≥ 4.5 |
| Checks error row (error on panel) | 6.49 | 4.80 | ≥ 4.5 |
| Folder note (faint on panel) | 5.63 | 5.00 | ≥ 4.5 |
| Refusal on 00 Stage (error on panel) | 6.49 | 4.80 | ≥ 4.5 |

"The tint" is `accent_bg` in dark (`#1d1511`) and `accent_bg` blended halfway
toward `card` in light (`#fdf4ef`, D152). On the light `accent_bg` itself the
selected card number and the HAND-OFF IN title were 4.28, the states 4.24-4.38,
the folder 4.47, and the board's orange arrow 2.58 on `bg`; all pass now.

Below the rule: only the unselected card number, `num_dim`, which is F8
(the same colour as the Setup tree's numbers; GUI-10).

## Screenshots (real platform)

`gui9a-<mode>-<size>-<scene>.png`, mode `dark` / `light`, size `1100x720` /
`1600x1000`:

| Scene | What it shows |
|---|---|
| `route123-stage2` | route 1D → 2D → 3D, stage 2 selected on 00 Stage: HAND-OFF IN `handoff_1d_to_2d.txt`, OUT `handoff_2d_to_3d.npz` |
| `route13-stage3` | route 1D → 3D: the 200 px link `handoff_1d_to_3d.txt`, the 3D stage's in-text with the 3D form's burst height |
| `stage2-error` | Lx `abc` on stage 2: card `● 1 error`, 02 Domain ✗, the pill `1 error`, the Checks list |
| `stage2-gauges` | stage 2 on 05 Gauges with two gauges and the trigger switch on (remap) |
| `stage2-trigger-handoff` | the same stage on 00 Stage: the out-text names `G2 (trigger gauge, remap)` |
| `stage3-3d` | a 3D stage: the hint, no preview |

`e2e9a_route12.png`, `e2e9a_loaded_copied.png`, `e2e9a_stage_error.png`,
`e2e9a_done.png`: the real-platform run of `_e2e_ui_chain_screen.py` (1280 ×
840, native, Load case… into stage 1, Copy from 01 Setup into stage 2, Run
chain clicked).
