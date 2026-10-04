# GUI-6a Run screen - real-platform measurements (2026-09-29)

Batch `docs/batches/2026-09-29-gui-run.md`, T5 (6a verification). Machine: the
home PC (8 GB RAM, 140-230 MB of it free during the session, other
applications). `QT_QPA_PLATFORM` unset for everything here
(`ensure_qapp(offscreen=False)`); throwaway settings through
`ui.testing.private_settings()` (`auto_cleanup` off, a throwaway runs folder).
The CLAUDE.md §8.2 dry run printed `<repo>\settings.json False []` before the
session. Scripts (session scratchpad): `t5_shots.py`, `t5_viewer.py`,
`t5_contrast.py`, `t5_probe.py`, `t5_second_run.py`. Code state: `96f10e6`
(the three T5 fixes below included).

## Screenshots

`gui6a-<state>-<W>x<H>-<mode>.png`, dark and light, 1100 × 720 and
1600 × 1000 (20 files). Case: the boards' sample case in native mode
(2D axisymmetric, 1 kg TNT at z 2 m, 4 × 4 m, Wall 1 r 3.0-3.2 z 0-1.5,
gauges (2.95, 0.5), (2.95, 1.5), (1.5, 0.5), (3.3, 0.5)) at a 12.5 mm cell
(validation refines it to 10.5 mm, 144 k cells), so the run lasts about a
minute.

| State | What is on screen |
|---|---|
| `idle` | before any run: `Run`, the Setup link `Setup: Case OK · 144 k cells`, percent `—` |
| `running` | a real native 2D run at 48-50 %: `30 s elapsed · about 32 s left`, Stop with `Shift+Esc`, tiles `0.428 ms` · `416` / `dt 1.61e-06 s` · `1,150 kPa` |
| `step-open-auto-off` | the same run at 51-52 %, Step through open (the six buttons), colour range off with Min 0 / Max 150 kPa (the live pane at that range) |
| `stopped` | after Stop: `Stopped after 58 s` / `59 s`, Run back |
| `0d-busy` | 0-D: the indeterminate bar, `HD 1.3 assessment · 3 s elapsed`, percent `—`; Step through, Live view, 3D and the three tiles hidden. **Staged**: `_set_hd13_busy(True)` (the call the worker path makes), no assessment run |

Two passes: the first pass's light run died of `MemoryError: Unable to
allocate 8.00 MiB` at step 143 (this PC, see above). Its time line correctly
read `Failed after 10 s`. The light states were retaken alone with no error;
the light PNGs are from that pass (`shots_measure.json`, `note`).

## Against boards `Run.dc.html` / `Run_Finished.dc.html`

From `shots_measure.json` (widget sizes, and fills sampled from `win.grab()`):

| Item | Board (line) | 1600 × 1000 | 1100 × 720 |
|---|---|---|---|
| columns controls / centre / gauges | 280 / flex / 340 (62, 259) | 280 / 932 / 340 | 280 / 432 / 340 (no narrowing needed) |
| Stop | 48 px, `stop_*` (85) | 186 × 48, fill `#26141a` = `stop_bg` (dark) | 186 × 48 (176 with Step through open: the column's scroll bar) |
| Run / Run again | 48 px, `accent` (94) | 186 × 48, fill `#ff6a2b` | same; 0-D 250 × 48 (no 3D square beside it) |
| 3D square | 56 × 48 (97) | 56 × 48, icon only | same |
| Runs folder box / browse | 34 / 34 × 34 (70-71) | box 34, browse 34 × 34 | same |
| Step-through buttons | 32 (Exec buttons pinned in QSS, D41) | 32 × 6 | same |
| Setup link | (149) | 250 × 42 | same |
| strip | one row: Progress flex 2.3 + three tiles (157-181) | one row, 81-82 px; Progress 394 × 82, tiles 171-172 × 82 (394 / 171 = 2.3) | two rows (D48): Progress 432 × 81 on top, tiles 138-139 × 80 below; 169-170 px |
| Progress fill | `accent_bg` `#1d1511` (158) | `#1d1511` dark / `#fbe9df` light | same |
| view | - | 932 × 608-609 | 432 × 270-271 (≥ 240, U15 / risk 6) |
| dock | 142 px, tab strip 38 (246-247) | 140, tabs 40 | 110 (gives way, DOCK_MIN) |
| dock tabs | `Log`, `Messages`, `Earlier runs 3` + Copy / Save log… | `Log`, `Messages`, `Earlier runs   0`, Copy, Save log… | same |
| TIME / STEP / P MAX captions | `simulated`, `dt 4.1e-7 s`, `in the field now` | `simulated`, `dt 1.61e-06 s`, `in the field now` (D52: U4's formats) | same |

Intended differences from the board: the view toolbar is a row above the view
(D43); `Setup: Case OK` with a capital C (D44); the strip wraps below about
1260 px (D48); the tab padding is 12 px, not 14 (D56); number formats are U4's
(D52). One small difference remains: the third tile's caps read `PMAX`, where
the board has `P MAX`. The space is there, but at 10 px it renders about
2 px wide (GUI-4's `StatTile`, the same in Setup).

## Contrast (WCAG, plan §2.2), by script

`contrast.json` (`t5_contrast.py`, from `ui/theme.py` DARK / LIGHT and the
Run-screen QSS rules):

| Pair | fg / bg | dark | light |
|---|---|---|---|
| **Stop text and key cap** | `stop_text` / `stop_bg` | **8.74** | **5.31** |
| **Eyebrow caps, the resolved path** | `faint` / `panel` | **5.63** | **5.00** |
| field captions, gauge placeholder, dock tabs, Copy / Save | `muted` / `panel` | 7.69 | 5.75 |
| dock tab active | `text` / `panel` | 16.80 | 14.75 |
| log, Earlier-runs rows | `text2` / `panel` | 11.83 | 10.03 |
| Messages warn / error | `warn` / `danger` on `panel` | 12.93 / 6.49 | 4.75 / 4.80 |
| Run text | `on_accent` / `accent` | 6.66 | 6.66 |
| card title / hints and units | `text` / `faint` on `card` | 16.43 / 5.50 | 15.52 / 5.26 |
| Exec buttons | `text` / `hover` | 14.81 | 12.47 |
| Setup link OK / errors | `text2` / `ok_bg`, `stop_text` / `stop_bg` | 11.04 / 8.74 | 9.25 / 5.31 |
| progress percent / time line | `text`, `text2` / `accent_bg` | 15.67 / 11.03 | 13.17 / 8.96 |
| progress caps | `accent_text` (dark) / `accent_soft` (light) on `accent_bg` | 7.72 | 4.65 |
| tile caps / value / caption | `faint`, `text`, `muted` / `tile` | 5.37 / 16.03 / 7.34 | 4.58 / 13.51 / 5.27 |
| Earlier runs selected | `text` / `accent_bg` | 15.67 | 13.17 |
| Show mesh | `muted` / `card` | 7.52 | 6.05 |
| PAUSED, as T2 built it (on the tile) | `warn` / `accent_bg` | 12.06 | **4.24 - failed** |
| PAUSED badge after the T5 fix (D57) | `warn` / `bg` | 13.19 | 4.50 |

All pairs on screen are at or above 4.5:1 once the fix is in.

## Found by this verification and fixed (one commit each)

1. **`abfa0f8` - the Progress tile was never on screen.** That hid the bar, the
   percent and the elapsed / ETA line. `_RunStrip.arrange()` re-applied the
   `isHidden()` of a parentless frame that had never been shown. R1 now
   asserts the visibility.
2. **`7023702` - Tab order.** Show mesh → log → dock tabs → Copy → Save → the
   controls' scroll area; now Show mesh → the dock's tabs → Copy → Save log… →
   the log, last. The scroll area is no Tab stop. R1 walks the real focus
   chain.
3. **`96f10e6` - the PAUSED readout** (4.24:1 in light on the tile) is a small
   `bg` badge that shows only while held.

## 3D viewer placement (CLAUDE.md §8.7, plan §11)

Win32 through ctypes (`GetWindowRect` / `GetParent` / `IsWindowVisible`),
never Qt's `geometry()`. A sample is wrong when a visible viewer window is a
top-level while embedded, or an embedded one lies outside the Run host
container's Win32 rect (8 px pad). **Pre-registered rule (plan T5): the longest
unbroken wrong stretch is 0 ms over at least 500 samples with a viewer
window.**

Driven on `tests/cases/native_3d_small.json` (native, 216 k cells) with the 3D
view shown:

- (A) Initialise, sampled from the click, through the viewer child's start and
  the auto-attach, then held with the PAUSED badge.
- Step through open / close × 2.
- Dock Messages → Earlier runs → Log → Messages → Log.
- Setup → Run → Results → Run × 2.
- Resize 1600 → 1100 → 1600 → 1100 → 1600: the strip goes 1 ↔ 2 rows and the
  dock 140 ↔ 110 (recorded in the JSON).
- Theme light → dark.
- +100 (frames streaming, the badge hides), streaming at 1100 × 720, and Step
  through opened while streaming.
- To the end (571 samples streaming), then the finished playback at 1100 and
  1600.
- (B) A plain Run start, then Stop.

`viewer_measure.json`: **2032 samples, 1624 with a viewer window, 0 wrong,
longest wrong stretch 0 ms. PASS** (GUI-3 and GUI-5's bar).

Phase B contributed no viewer-window samples. A second native 3D run started
with Run after a finished one leaves the host on its placeholder ("Run a 3D
case - the live view attaches automatically…"). The log still says `[3D view
active - frames stream while the solver runs]` and `has_scene` is True, but no
viewer window is visible: 0 of 638 samples over 40 s at `96f10e6`, and 0 of
128 over 8 s at base `51f4c78`. So it is not caused by GUI-6. It is recorded
as F9 in `docs/gui-redesign-decisions.md` and is not fixed here
(`view3d_host.py`, the §8.7 zone).

The sampler process ended with exit 139 **after** writing the JSON. A
reproduction (`t5_close_repro.py`) got through `win.close()` and the event pump.
The abort then comes in the script's own `os._exit(0)`, while the app's WSL
probe threads (`env.detect_ram_gb`, `_background_probe`) are still inside
`subprocess.communicate`. It is a script-teardown artefact, not the window's
close path. No orphaned process was left: the viewer child PID 34960 was gone
when checked.
