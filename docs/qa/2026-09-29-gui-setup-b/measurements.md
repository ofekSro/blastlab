# GUI-5b Setup centre (strip, model view, dock) - real-platform measurements (2026-09-29)

Machine: the home PC (8 GB RAM, WSL VM 4 cores / 5 GB - not the office i7 of
CLAUDE.md §3). `QT_QPA_PLATFORM` unset for everything here; throwaway settings
(`BLASTLAB_SETTINGS` in a temp dir, `auto_cleanup` off; the CLAUDE.md §8.2 dry
run printed `<repo>\settings.json False []` before the session). Scripts:
session scratchpad `shots_gui5b.py` and `measure_viewer_gui5b.py` (5a's
scripts, extended). Both set `OPENBLAS_NUM_THREADS=1`: on the first attempt
this PC had ~250 MB of RAM free (other applications) and the 3D viewer child
died with `OpenBLAS error: Memory allocation still failed`, which left "The 3D
viewer process stopped" in the 3D shots; with one OpenBLAS thread it embeds.

## Screenshots

`gui5b-<state>-<W>x<H>-<mode>.png`, dark and light, 1100 × 720 and
1600 × 1000 (24 files):

| State | What is on screen |
|---|---|
| `2d-threat` | the boards' sample case (2D axisymmetric, blastFoam, 1 kg TNT at z = 2 m, 4 × 4 m, 25 mm, Wall 1 r 3.0-3.2 z 0-2.5, G1 (2.95, 0.50), G2 (2.95, 1.50)); 01 Threat selected: charge highlight, Z rings, the dock on Checks |
| `2d-gauges` | the same case, 05 Gauges selected: gauge halos, charge → gauge R lines, the dock on Gauges (the board table) |
| `2d-native` | the sample case in native mode: no MPI ranks / Memory tiles (no run plan) |
| `1d` | Case1D, blastFoam, gauges r = 1, 2, 3; 05 selected (halos only, D38) |
| `3d` | `tests/cases/native_3d_small.json` with the embedded 3D viewer (screen grab, so the native child window is in it; a corporate VPN notification sits over the right edge of the 1600 px grabs - not the app) |
| `0d` | the HD 1.3 form: no tiles, Run only, dock Checks · Log |

The case name reads `native_3d_small` after the first 3D shot because
`set_case` (what the script uses) does not reset the file path - a script
artefact, as in 5a.

## Against board `BC_Combined.dc.html`

From `shots_measure.json` (sampled from `win.grab()` pixels and the widgets):

| Item | Board | 1600 × 1000 (dark / light) | 1100 × 720 (dark / light) |
|---|---|---|---|
| tree / properties | 280 / 340 (lines 58, 268) | 280 / 340 | 280 / 340 |
| strip | one row: 5 tiles + 148 px Run (lines 125-159) | one row, 87 px high; tiles 144-145 px, Z 166 px (flex 1.15); Run 148 × 64 | two rows (D29), 134-141 px (141 with the memory bar; the first dark shot was taken while the WSL probe was still running, so no VM size and no bar); tiles 138-139 px; Run 139 × 40-47 |
| tile fill | `tile` #141416 / Z `accent_bg` #1d1511 | #141416 / #1d1511 · #f1efeb / #fbe9df | same |
| Run fill | `accent` #ff6a2b, `on_accent` text | #ff6a2b | #ff6a2b |
| tile texts | `1.0 kg TNT` · `radius 52.7 mm`; `368 k` · `6.59 mm at the charge`; `7` · `auto · 50 k cells each`; `1.0 GB` · of 63; `2.99–3.31` · m/kg^1/3 | `1.0 kg TNT` · `radius 52.7 mm`; `368 k` · `cell 6.59 mm`; `2` · `auto · 184 k cells each`; `0.9 GB` · `of 5 GB VM` (bar); `2.99–3.31` · `m/kg^1/3` | same numbers; captions in the tooltips (D29) |
| Z rings | dashed `accent`, Z 1/2/3 (lines 171-176) | 3 rings, #ff6a2b, radii 1.00 / 2.00 / 3.00 m | same |
| charge highlight | two rings + `Charge · 1 kg TNT` tag | present on 01 | present |
| gauge highlight | halos + dashed lines, `R 3.31` / `R 2.99` | 2 halos, `R 3.31`, `R 2.99` on 05 | same |
| dock | 212 px, tabs 40 px, 2 px `accent` underline | 212 px; underline #ff6a2b | 170 px (D35) |
| dock tabs | `Gauges 2`, `Checks 0 · 0 · 4`, `Log` | `Gauges   2`, `Checks   0 · 0 · 6`, `Log` (the real report has 6 notes) | same |
| dock follows | Threat → Checks, Gauges → Gauges | Checks on 01, Gauges on 05 | same |
| Checks layout | two columns (line 258) | two columns | one column (a 404 px tab, D35) |
| gauge table | Gauge · r · z · R from charge · Z · Where; G1 2.95 0.50 3.31 3.31 `5 cm in front of Wall 1`; G2 2.95 1.50 2.99 2.99 same | identical | `Gauge · R [m] · Z · Where` (D36), same numbers and Where |
| 05 summary | `2 · in front of Wall 1` | identical | identical |
| native | - | tiles Charge, Cells, Z | same |
| 3D toolbar | - | Mesh, Fit (no Z rings, D32) | same |
| 0-D dock | - | Checks, Log (no Gauges) | same |

Intended differences from the board: the strip wraps below ~1400 px (D29); the
dock shrinks on short windows and the table gives up its coordinate columns at
1100 px (D35, D36); captions the board does not pin (D30); the hover readout sits
in the toolbar's caption slot (D33); gauges are cyan in the preview (D34); the
centre's three parts are separate rounded panels inside the window's 16 px frame
(5a's column style), not flush as on the board.

## Contrast of the text pairs this batch introduced (WCAG ratio)

| Pair | fg / bg | dark | light |
|---|---|---|---|
| tile caps | `faint` on `tile` | 5.37 | 4.58 |
| tile value | `text` on `tile` | 16.03 | 13.51 |
| tile caption | `muted` on `tile` | 7.34 | 5.27 |
| Z tile caps | `accent_text` (dark) / `accent_soft` (light, D38) on `accent_bg` | 7.72 | 4.65 |
| Z tile caption | `accent_soft` on `accent_bg` | 10.75 | 4.65 |
| Run text | `on_accent` on `accent` | 6.66 | 6.66 |
| F5 key cap | `on_accent` on `accent` darkened 16 % | 4.84 | 4.84 |
| Initialise | `text2` on `bg` | 12.07 | 9.51 |
| toolbar button | `muted` on `card` | 7.52 | 6.05 |
| toolbar checked | `accent_soft` on `accent_bg` | 10.75 | 4.65 |
| view caption | `faint` on `card` | 5.50 | 5.26 |
| hover readout | `text2` on `card` | 11.57 | 10.55 |
| dock tab / active | `muted` / `text` on `panel` | 7.69 / 16.80 | 5.75 / 14.75 |
| table header | `faint` on `panel` | 5.63 | 5.00 |
| table gauge / R / Z / Where | `gauge` / `text2` / `accent_soft` / `muted` on `panel` | 10.03 / 11.83 / 11.52 / 7.69 | 4.96 / 10.03 / 5.21 / 5.75 |
| selected table row | `text` on `gauge_bg` | 15.40 | 13.44 |
| checks error / warn / note | `error` / `warn` / `muted` on `panel` | 6.49 / 12.93 / 7.69 | 4.80 / 4.75 / 5.75 |

All at or above 4.5:1. (Light `accent_text` on `accent_bg`, 4.28, is the one
pair that failed and is not used any more in the strip; it remains in GUI-4's
`TreeRow` selected number, 5a finding F8.)

## 3D viewer placement (CLAUDE.md §8.7)

Win32 through ctypes (`GetWindowRect` / `GetParent` / `IsWindowVisible`),
never Qt's `geometry()`. Wrong = a visible top-level viewer window while
embedded, or an embedded one outside the host container's Win32 rect (8 px
pad). Driven after loading `native_3d_small.json`: Setup → Run → Results × 3;
blastFoam on, tree nodes 07 → 05 → 07 → 01 → 02 → 01 (07 widens the
properties column to 459 px); native; dimension 2 → 3; window 1100 × 720 →
1600 × 1000 → 1280 × 840; light → dark; **new in 5b:** the dock's tabs
Gauges → Checks → Log → Checks, Fit (the viewer's `reset_view`), Mesh on/off,
a 14-error report in Checks and back, and 1100 × 720 → 1400 × 760 →
1600 × 1000 → 1280 × 840 (the strip changing between two rows and one, the
dock between 170 and 212 px); detach → re-attach. `viewer_measure.json`:

**1511 samples (1231 with a viewer window on screen), 0 wrong, longest
unbroken wrong stretch 0 ms** - GUI-3's bar.

The same run first walked every dimension × solver mode × node on the real
platform: no empty properties page anywhere, no dead column (`layout` in the
JSON; centre 493-612 px at 1280 × 840).

## Verify pass (2026-09-29, after the fix(verify) commits)

Same machine, real platform, throwaway settings (`ui.testing.private_settings`).

- **28 px buttons (D41).** Before the fix, at 1600 × 1000: Initialise 148 × 17 and
  Z rings / Mesh / Fit 18 px tall (Fit 28 × 18). After: 28 / 28 / 28 / 28 and
  Run 148 × 46. At 1100 × 720 the wrapped strip is 145 px (was 134).
- **Where behind a wall (D39).** `verify-2d-gauges-behind-1600x1000-dark.png`:
  the sample case plus G3 (3.30, 0.50) behind Wall 1 reads `10 cm behind Wall 1`.
  G1 / G2 are unchanged. `verify-2d-threat-1600x1000-dark.png`: 01 Threat,
  Initialise at 28 px.
- **3D viewer placement re-measured** (the toolbar above the host is 10 px
  taller). Same sampler plus a Z-rings toggle on the 3D page,
  `verify_viewer_measure.json`: **1530 samples (1252 with a viewer window),
  0 wrong, longest wrong stretch 0 ms.**
