# GUI QA - P0-5 disk warning + P1-18 HD 1.3 Save/Open (2026-09-27)

Worktree `C:\Users\rotem.ofek\blastlab-worktrees\todo`, branch `todo-batch`, HEAD `37106b8`.
No application code was edited. No WSL solve was started. The disk-warning WSL touch points were stubbed, and `delete_runs` was stubbed to raise.

## Environment

- Python 3.12.10 (Store build), PySide6 6.11.2, customtkinter 6.0.0, Pillow 12.2.0, Windows 11 26200 over RDP.
- The Qt platform was the real one: `QT_QPA_PLATFORM` was unset, and `app.platformName() == 'windows'`.
- Settings were private. `BLASTLAB_SETTINGS` pointed at a temp file written by `ui.testing.private_settings()` before any window was built, with `auto_cleanup: false` and a temp `runs_dir`. The harness asserted `env.auto_cleanup(settings.load()) == (0, 0)` first.
- Screenshots are Win32 `PrintWindow(PW_RENDERFULLCONTENT)` captures of the app's own top-level HWND.
  - A desktop grab was not possible at first. The RDP session had no grabbable desktop, and `ImageGrab` raised `screen grab failed`.
  - Later the session came back, and two grabs caught the owner's other windows. Those images were deleted, and every shot was re-taken with PrintWindow. The harness never forces the window to the foreground.
- Harnesses:
  - `harness_p0_5.py qt|tk|launch`
  - `harness_p0_5_tk.py [early]`: the Tk disk warning driven inside a real `root.mainloop()`.

## Results

| # | Check | Result | Screenshots |
|---|---|---|---|
| 1a | Qt, HD 1.3: the starter opens into the 0-D form. Save case… writes `"schema": "blastlab-hd13"`. The form is moved to 2D, then the saved file is reopened. It lands in the 0-D form with `case_to_dict` equal to the starter's (empty diff). No error dialog, no modal. | **PASS** | `q01_hd13_starter_opened.png`, `q02_form_moved_to_2d.png`, `q03_hd13_reopened.png`, saved file `hd13_saved.json` |
| 1b | Qt, 2D blast: Save case… writes `blastlab-case`, byte-identical to `models.case.save_case`. The file reopens as 2D, byte-identical when saved again. No dialog. | **PASS** | `q04_blast2d_reopened.png` |
| 2a | Qt disk warning. `start_disk_warning(st, win._disk_warning, private_ok=True)` was run with 15 GB of stubbed runs against `cleanup_max_gb = 10`. Result: exactly 1 `notify(..., 'warn')`, the status line shows the warning, exactly 1 Run-log line, no modal widget, `delete_runs` called 0 times. | **PASS** | `q05_disk_warning_status.png`, `q06_disk_warning_runlog.png` |
| 2b | Tk disk warning, same stubs, run under a real `mainloop`. It was tried two ways: the thread started from inside the loop, and started before `mainloop()` as `App.__init__` does. Both gave 1 warn notification, 1 status line, 1 log line, no messagebox, no Toplevel, and `delete_runs` 0 times. | **PASS** | `t01_disk_warning_status.png`, `t02_disk_warning_runlog.png` |
| 3 | `python -m blastlab` and `python -m blastlab --tk` launched as real processes. Each window appeared (Qt 4.6 s, Tk 7.3 s), titled `blastlab 1.0.0`, 1296x879. `WM_CLOSE` ended each process with rc 0, empty stderr and no leftover window. The in-process windows also closed cleanly. No stray python processes remained. | **PASS** | `l_qt_window.png`, `l_tk_window.png`, `q00_start.png`, `t00_start.png` |

Totals: Qt 19/19, Tk 7/7 (inside mainloop) and 7/7 (before mainloop), launch 6/6.

## Odd things

1. **The status line cuts the warning before its action.** The warning is about 260 characters. Both toolkits truncate the status line to `text[:200]`, so it ends at "…would delete 2 ru" in Qt and "…(7.0 GB). To free spa" in Tk. The command `python -m blastlab --clean-foam-runs` is only reachable in the Run log, and in Qt also in the status tooltip. Tk has no tooltip. See `q05` and `t01`. The cut happens in `ui/app.py:885` and `gui/app.py:1072` (`notify`), and the wording comes from `solvers/foam/env.py:917` `disk_warning_text`. A shorter text, or putting the action first, would fix it.
2. **Tk drops the warning when the event loop is pumped instead of run.** A driver that pumps `root.update()` instead of running `mainloop()` never receives it. `root.after()` called from the warning thread then raises `RuntimeError: main thread is not in main loop`, and `App._log_threadsafe` / `_disk_warning` swallow it (`gui/app.py:1091-1106`). Neither the log line nor the status line appears, with no trace. This is what my first `harness_p0_5.py tk` run showed (3 FAILs); they are a harness artefact, not an app bug. The real app runs `mainloop()`, and tkinter waits up to 1 s for it, so the real path passes even when the thread finishes before `mainloop()` starts (the `early` variant). A future Tk test of this path must run a real mainloop.
3. **Visual, probably not new to this batch.** At the default launch size of 1296x879, the Qt Setup form's left card clips its input boxes at the right edge: the Geometry box and the Profile-file browse button (`l_qt_window.png`). At 1400x900 it lays out fine (`q00_start.png`).
4. For information: opening a blast case sets the sidebar solver to the case's `solver` field. The test 2D case was `native`, so the mode moved from blastFoam to native after it was opened. This is expected.
