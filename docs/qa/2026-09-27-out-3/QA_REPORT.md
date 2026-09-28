# OUT-3 GUI QA - "Keep all fields in WSL" box (plan Step 8)

Worktree `blastlab-worktrees/out-3`, Python 3.12.10, PySide6 (real Windows platform) and customtkinter, Windows 11.
Private settings (`auto_cleanup: false`); WSL fully stubbed (no probe, no solve). Harnesses in the session scratchpad, not committed.
Screens grabbed with `QWidget.grab()` (Qt) and Win32 `PrintWindow` (Tk): `ImageGrab` fails on this desktop ("screen grab failed").

| Check | Qt 1D | Qt 3D dark | Qt 3D light | Tk 1D | Tk 3D dark | Tk 3D light |
|---|---|---|---|---|---|---|
| Box shown in blastFoam mode | PASS | PASS | PASS | PASS | PASS | PASS |
| Box hidden in native mode (whole VTK card) | PASS | PASS | PASS | PASS | PASS | PASS |
| Tooltip set and readable | PASS | PASS | PASS | PASS | PASS | PASS |
| Tick -> case -> Save JSON `keep_all_fields: true` -> untick -> Open -> ticked | PASS | PASS | PASS | PASS | PASS | PASS |
| Not clipped at default 1280x840 | PASS | PASS | PASS | PASS | PASS | PASS |
| Not clipped at 1100 px wide | - | PASS | - | - | PASS | - |

Result: 22/22 checks PASS in Qt and 22/22 in Tk. No defects.

Screenshots: `qt_{1d,3d}_blastfoam_*.png`, `qt_*_native_*.png`, `qt_3d_tooltip_{dark,light}.png`, `qt_3d_blastfoam_1100.png`, and the same `tk_*` set. The saved cases are `qt_case_{1d,3d}.json` and `tk_case_{1d,3d}.json`.

Visual notes (none blocking):
1. The Qt tooltip is a single unwrapped line, 1008 px wide (`qt_3d_tooltip_dark.png`). It is readable, but it is wide. The Tk tooltip wraps to 4 lines at 320 px.
2. The orange "WSL hardware not detected" warning in the screenshots comes from the harness stub, not from the app.
3. This predates OUT-3: in Tk light mode the unselected sidebar and dim segments ("native", "1D", "2D") are very faint (`tk_3d_blastfoam_1100.png`).
