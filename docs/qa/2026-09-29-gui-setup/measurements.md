# GUI-5a Setup (tree + properties) - real-platform measurements (2026-09-29)

Machine: the home PC (WSL VM 4 cores / 5 GB, not the office i7 of CLAUDE.md §3).
`QT_QPA_PLATFORM` unset for everything here; throwaway settings
(`BLASTLAB_SETTINGS` in a temp dir, `auto_cleanup` off). Scripts: session
scratchpad `shots_gui5.py`, `measure_viewer_gui5.py` (the GUI-3 sampler
`measure_viewer.py` extended).

## Screenshots

`gui5-<state>-<W>x<H>-<mode>.png`, dark and light, 1100 × 720 and 1600 × 1000
(28 files):

| State | What is on screen |
|---|---|
| `2d-threat` | the boards' sample case (2D axisymmetric, blastFoam, 1 kg TNT at z = 2 m, 4 × 4 m, 25 mm, Wall 1 r 3.0-3.2, G1 (2.95, 0.50), G2 (2.95, 1.50)); 01 Threat selected, Derived card |
| `2d-gauges-trigger-on` | the same case with `trigger_gauge = 2`; 05 Gauges; switch on, Gauge = G2, On arrival, remap note |
| `2d-gauges-trigger-off` | after one click on the switch: rows hidden, "Off: the run ends at the Outer side or at the end time." |
| `2d-native` | the sample case in native mode (no Detonation points, no VTK) |
| `1d` | Case1D, blastFoam, gauges r = 1, 2, 3 (no 04 Structure, no trigger; Nearest gauge G1 · Z 1.00) |
| `3d` | `tests/cases/native_3d_small.json` with the embedded 3D viewer in the centre (screen grab, so the native child window is in it) |
| `0d` | the HD 1.3 form: one node per visible card, 01-10 |

The 3D shot uses the committed native case: a default `Case3D(solver='blastfoam')`
preview does not embed on this PC within 60-120 s - **identically at the base
commit `e84da3f`** (A/B in a temporary worktree, same script), so it is not
this batch. Shots after the first `_open_case` show `native_3d_small` as the
case name because `set_case` (what the script uses) does not reset the file
path - a script artefact, not a defect.

## Against board `BC_Combined.dc.html`

From `shots_measure.json` (sampled by the script from `win.grab()` pixels and
the widgets' own style sheets), identical at both sizes:

| Item | Board | Measured dark | Measured light |
|---|---|---|---|
| tree column | 280 px (line 58) | 280 | 280 |
| properties column | 340 px (line 268) | 340 on every page; 07 Output with the VTK matrix 432 (2D) / 459 (3D) / 354 (1D), 0-D Loaded wall 388 (decision D19) | same |
| tree row height | min 46 px (plan ≥ 44) | 44 | 44 |
| selected row fill | `accent_bg` #1d1511 | #1d1511 | #fbe9df (= light `accent_bg`) |
| unselected row | transparent on `panel` | #0e0e10 (`panel`) | #faf9f7 (`panel`) |
| selected number | `accent_text` #ff8a55 | #ff8a55 | #c5420f |
| unselected number | `num_dim` #6f6a63 | #6f6a63 | #9b958c |
| pill fill / border | `ok_bg` #121814 / `ok_border` #24302a | #121814 / #24302a | #e7f3ea / #c4dccb |
| pill text | `Case OK · 4 notes` | `Case OK · 6 notes` (the real report: 6 notes for this case) | same |
| summaries | `1.0 kg TNT · z 2.0 m`, `4 × 4 m · 25 mm`, `the run ends at Outer`, `1 obstacle`, `2 · in front of Wall 1`, `linear · no afterburn · CFL 0.4`, `.mp4 · VTK off` | identical, except 05 `2 gauges` (the "in front of" part is GUI-5b's Where helper) | same |
| Derived | `52.7 mm`, `2.00 m`, `G2 · Z 2.99` | identical (the radius is the report's `r_exp`) | same |

Intended differences from the board: no live-number strip, Z rings, hover
readout, toolbar or dock yet (GUI-5b, decision D14); the validation report
card sits at the bottom of the centre until the dock's Checks tab replaces it;
the three columns sit inside the window's 16 px frame margin (the board runs
them edge to edge); units stay in the captions (D15); the pill's text is
`text2` with the state colour on its icon (D23); the closed trigger dropdown
elides `G2 · r 2.95, z 1.50` at 1100 px (the open list shows it whole).

## Contrast of the text pairs this batch introduced (WCAG ratio)

| Pair | dark | light |
|---|---|---|
| pill text `text2` on `ok_bg` | 11.04 | 9.25 |
| pill error text `stop_text` on `stop_bg` | 8.74 | 5.31 |
| tree eyebrow / child position `faint` on `panel` | 5.63 | 5.00 |
| child name, add buttons `text2` on `panel` | 11.83 | 10.03 |
| gauge marker `gauge` on `panel` | 10.03 | 4.96 |
| properties caption `muted` on `panel` | 7.69 | 5.75 |
| heading number `accent_text` on `panel` | 8.28 | 4.80 |
| Derived key `muted` on `card` / value `text` on `card` | 7.52 / 16.43 | 6.05 / 15.52 |

Below 4.5:1, all in the GUI-4 `TreeRow` component's existing tokens (not
changed here, reported): `num_dim` on `panel` 3.60 dark / 2.82 light (the
unselected step numbers); light `accent_text` on `accent_bg` 4.28 (the
selected number); light `faint` on `accent_bg` 4.47 (the selected row's
summary).

## 3D viewer placement (CLAUDE.md §8.7)

Win32 through ctypes (`GetWindowRect` / `GetParent` / `IsWindowVisible`),
never Qt's `geometry()`. Wrong = a visible top-level viewer window while
embedded, or an embedded one outside the host container's Win32 rect (8 px
pad). Driven after loading `native_3d_small.json`: Setup → Run → Results × 3;
blastFoam on, tree nodes 07 → 05 → 07 → 01 → 02 → 01 (07 widens the
properties column to 459 px, so the centre and the host shrink and grow);
native; dimension 2 → 3; window 1100 × 720 → 1600 × 1000 → 1280 × 840; light →
dark; detach → re-attach. `viewer_measure.json`:

**1083 samples (801 with a viewer window on screen), 0 wrong, longest
unbroken wrong stretch 0 ms** - GUI-3's bar. Same result at the T2 commit
(1083 / 0 / 0 ms).

The same run first walked every dimension × solver mode × node: no empty
properties page anywhere, no dead column (`layout` in the JSON).
