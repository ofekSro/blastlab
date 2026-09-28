# QA report - OUT-4c (Volumes decimation card)

Branch `out-4c-decimation`, tip `c650cb5`. Repo:
`C:\Users\rotem.ofek\OneDrive - Technion\BlastFoam`.

## 1. Environment

- Python 3.12.10 (Microsoft Store build), PySide6 6.11.2, pillow 12.2.0.
- OS: Windows 11 Enterprise 10.0.26200. This session's console (session id 2,
  user rotem.ofek) is **disconnected** (`query session` shows `Disc`), so
  `PIL.ImageGrab.grab()` raises `OSError: screen grab failed` for any Tk
  capture taken outside the repo's own harness (a known, already-documented
  limitation - see `_qa_ui_harness.py`'s own docstring on P5-7, and
  `_qa_gui_harness.py`'s PrintWindow fallback).
- Qt app: offscreen platform (`QT_QPA_PLATFORM=offscreen`), `QWidget.grab()`
  - unaffected by the disconnected session.
- Tk app: driven on `ctk.CTk()`; screenshots via the repo's own
  `_qa_gui_harness.py`, which falls back from `ImageGrab` to Win32
  `PrintWindow` and succeeded for every shot (see `qa_report.md`'s harness
  runs below). My own throwaway manual driver (no PrintWindow fallback)
  could not capture screenshots in this session; its functional/text checks
  still ran and passed (Tk lays out widgets and reports geometry regardless
  of desktop compositing).
- Cleanup trap (CLAUDE.md 8.2): all drivers used
  `blastlab.ui.testing.private_settings()` / `ensure_qapp()` (Qt) or called
  `private_settings()` directly before building the Tk root, which writes
  `auto_cleanup: false` and a private `runs_dir` under a throwaway settings
  file - verified in `qt_harness/settings.json`. No WSL solves were run; the
  only "run" was V05's native 1D stage (numpy only, no WSL, writes into the
  harness's own private runs folder).
- No app code was edited. Two throwaway driver scripts were written to the
  scratchpad (outside the repo) for items 1-4; the pre-existing repo
  harnesses `blastlab/tests/_qa_ui_harness.py` (V group, Qt) and
  `blastlab/tests/_qa_gui_harness.py` (V group, Tk) were run as-is.

## 2. Result table

| # | Item | Qt | Tk | Evidence |
|---|------|----|----|----------|
| 1 | 3D Volumes: "Keep 1 layer in k" spin box (1..16) + warning line, readable/not clipped | PASS | PASS | `shots/qt_01_3d_card_default.png`, `shots/qt_08_card_k1.png`, `qt_harness/sheets/contact_V10.png`; `tk_harness/sheets/contact_V09.png` |
| 2a | k=2 -> validation strip shows the warning note | PASS | PASS | `shots/qt_02_3d_k2_strip.png`; Tk strip text logged in `_qa_gui_harness.py` V09 log and my driver's output |
| 2b | k=2 -> case saves `decimate: 2` | PASS | PASS | case dict `{'...,'decimate': 2}` printed by both drivers |
| 2c | reload restores k=2 | PASS | PASS | `shots/qt_03_3d_k2_reloaded.png`; Tk box read back `'2'` |
| 2d | k=1 -> saves no `decimate` key | PASS | PASS | both drivers checked `'decimate' not in vtk_volumes` |
| 3 | Hand-edited case, `decimate: 17` -> validation error naming it | PASS | PASS | `shots/qt_04_3d_decimate17_error.png` (`"VTK volumes: the decimation must be at most 16 (the card's range), not 17"`); Tk strip text carried the identical message |
| 4a | 2D: no decimation box | PASS | PASS | `shots/qt_05_2d_no_box.png`; functional check (`'vtk_v_decimate' not in form.v`) |
| 4b | 1D: no decimation box | PASS | PASS | `shots/qt_06_1d_no_box.png`; functional check |
| 4c | Native mode: card (and box) hidden | PASS | PASS | `shots/qt_07_3d_native_hidden.png`; functional check (`winfo_manager() == ''`) |
| 5 | `_qa_ui_harness.py` V group (V01-V10) | PASS (10/10, exit 0, no findings) | n/a | `qt_harness/checkpoint.json`, `qt_harness/sheets/contact_V*.png` |
| 6 | `_qa_gui_harness.py` V group (V01-V09) | n/a | PASS (9/9, exit 0, no findings) | `tk_harness/checkpoint.json`, `tk_harness/sheets/contact_V*.png` |
| 7 | Core decimation function (`vtk_export.decimate`) | PASS | - | `test_vtk_decimate.py`: 22/22 |
| 8 | Existing GUI unit suites (`test_ui_output_card.py` C13, `test_gui_output_card.py` K13) | PASS | PASS | full suite output captured in this session's log, both end `... : PASS` |

**Totals: 0 FAIL.** Every check above passed, cross-checked three ways per
platform (my own manual driver against the real `MainWindow`/`App`, the
repo's own pre-registered `_qa_ui_harness.py`/`_qa_gui_harness.py` V
scenarios, and the repo's own `test_ui_output_card.py`/`test_gui_output_card.py`
unit drivers).

## 3. Failures

None found.

## 4. Visual findings (non-blocking)

- At a narrow 460 px card width (`shots/qt_10_card_k2_narrow.png`), the
  spin box's native up/down arrow control sits flush against the card's
  right edge - the "-" arrow is visible, the "+" arrow is essentially at
  the boundary. Cosmetic only: the label, the value and the warning line
  stay fully readable, and the repo's own `test_ui_output_card.py` C1
  already asserts nothing is cut at 460 px across the whole card (still
  green on this branch). Not filed as a failure.
- A one-off `[blastlab] could not write settings ... [WinError 5] Access is
  denied ... .tmp -> settings.json` appeared once during the Qt V group run
  (at V03's start). Transient - almost certainly an OneDrive file-sync lock
  on the repo folder, not reproducible-looking, and the scenario completed
  with a clean `ok` result immediately after. Not an app bug; flagged here
  only for visibility.
- This session's console is disconnected, so plain `PIL.ImageGrab` cannot
  capture Tk (documented, pre-existing limitation, not caused by this
  branch). The repo's harness already works around it with a `PrintWindow`
  fallback; a throwaway driver without that fallback does not. Anyone
  re-running ad-hoc Tk screenshots outside the harness on a similarly
  disconnected session should reuse `_qa_gui_harness.py`'s `shot()` helper
  rather than bare `ImageGrab`.

## 5. Numbers check

OUT-4c is a UI/validation feature (a post-processing decimation flag), not
a physics calculation, so there is no "core function returns a number, GUI
displays the same number" comparison to make. The nearest equivalent - the
actual decimation post-pass (`blastlab/solvers/foam/vtk_export.py:decimate`)
that the GUI's `k` value drives - was exercised directly against a synthetic
grid in `test_vtk_decimate.py`: cell count, byte-exact cell/point values, a
valid point re-index (including polyhedra), a strict VTK round trip, and the
refusal paths (bad k, k beyond the grid, an origin/decimation that keeps no
cell). Result: **22/22 PASS**, unchanged from the pre-registered rules in
`6139d96`.

## 6. Artifacts in this folder

- `shots/qt_*.png` - my own Qt driver's screenshots (items 1-4).
- `qt_harness/` - full `_qa_ui_harness.py --only V` output (checkpoint,
  log, per-scenario `sheets/contact_V##.png` contact sheets, individual
  shots, `settings.json` proving `auto_cleanup: false`).
- `tk_harness/` - full `_qa_gui_harness.py --only V` output, same shape;
  `sheets/contact_V09.png` is the Tk twin of the Qt V10 decimation scenario.
- No `shots/tk_*.png`: see the ImageGrab note in `sec. 1`/`sec. 4` above -
  the Tk manual driver's functional checks (10/10 PASS) ran and are logged
  in this session's transcript, but it could not capture images itself in
  this disconnected session. Visual evidence for Tk item 1/2/4 is instead
  in `tk_harness/sheets/*.png` (captured via the harness's PrintWindow
  fallback, so it did succeed); item 3 (decimate:17) for Tk has functional/
  text evidence only (the exact validation-strip error text was captured
  and matches the Qt message word for word).
