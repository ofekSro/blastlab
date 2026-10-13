# Implement report - Part D, group 1 (D1, D2, D3), batch final-gui-and-ignition, risk high

Worktree branch `worktree-agent-a8a5fa568af9d8790`, base `872c7de` (the worktree started at `a4a8f4d`, an
ancestor; fast-forwarded to `872c7de` before any edit). Three commits, one per task. Qt only: nothing in
`blastlab/gui/` (Tk), `solvers/`, `services/`, `output/` or a golden was touched; no number moved. WSL not
used. Real platform for every e2e (`QT_QPA_PLATFORM` unset, private settings, cleanup dry run `False`
first). Script logs: session scratchpad `d-g1\`.

Commands. Per task `gate.py --changed HEAD`: D1 5/5 green (6.9 min), D2 20/20 (20.9 min), D3 21/21 (13.0 min).
Closing matrix: `gate.py --changed 872c7de` = **23/23 suites green** (13.5 min); `gate.py --only regression`
= byte-for-byte **PASS** (last); the three real-platform scripts exit 0 (above); the app starts
(`python -m blastlab`, throwaway settings, alive after 12 s, stopped by PID). The starting-state `gate.py --for <plan files>` was stopped by the 30-min background
limit before it printed (it covers every suite importing `ui/app.py`); the per-task gates above cover it.

## Tasks

**D1 - DONE - `852472b`.** GUI-16 (g). `View3DHost.on_window` only stores the handle while `_floating`
(the child re-reports it on every `detach`, and with the native mount dropped that report re-embedded the
window at once). A native detach sets `_native_float`; `on_closed` (the child's `closed` reply, i.e. the
floating window's own close button) then calls `set_floating(False)`, which re-attaches through the
existing `on_window` -> `_embed` path. Measuring on the real platform found a second fault the plan did not
name: the detached window never appeared - `_release_native` hides it with Win32 only, so the child's Qt
still believes it visible and its `show()` is a no-op. New `_show_detached` shows it (SetWindowPos,
SWP_SHOWWINDOW) where the card was. Files: `ui/view3d_host.py`, `tests/_e2e_ui_view3d.py` (G3 split into
`g3_native` / `g3_container`, Win32 helpers as in `_e2e_ui_viewer_place.py`), `tests/test_ui_view3d_host.py`
(V10, V11). Before: G3 failed 3 checks and crashed (`_float_win` None). Criteria:
- `python blastlab/tests/_e2e_ui_view3d.py` exits 0 - PASS (sampled every 50 ms with `GetParent` /
  `IsWindowVisible`: the window appears as a top-level after 0.08 s, then parent 0 and visible for all 40
  samples of 2 s; Re-attach: parent = mount `winId` after 0.12 s; WM_CLOSE posted to the floating window
  re-attaches after 0.14 s).
- `test_ui_view3d*` exit 0 - PASS (`test_ui_view3d_host.py`, offscreen).

**D2 - DONE - `65e1aaf`.** G14Q. New `tests/_e2e_ui_viewer_noise.py`: a Qt message handler over Setup
preview -> native 3D run -> Results 3D -> tab round -> close, recording message, window and step. Before:
**2**, both at `close` - `viewWindow` (a host's `_holder`) and `QWidgetClassWindow` (its native mount),
parent the host's `QStackedWidget`, the exact pair every QA round logged. `MainWindow.closeEvent` shut down
the Run and Results hosts but never the Setup preview's, so its card still held the viewer's render window
at teardown. Fix in `ui/app.py` `closeEvent` (one tuple entry plus a None guard), not in `view3d_host.py` /
`viewer.py` as the plan guessed: `shutdown()` already releases the HWND first. After: **0**. Test:
`test_ui_close_guard.py` C5 (Close calls shutdown on all three hosts). Criteria:
- the script prints the count before (recorded in its docstring: 2) and 0 after - PASS (exit 0).
- `_e2e_ui_view3d.py` and `_e2e_ui_viewer_place.py` exit 0 - PASS (both, after D2; viewer_place's own
  numbers: 0 ms wrong everywhere except `resize` 228.6 ms / `chainresize` 32.3 ms, which it reports and
  does not gate on; not touched by this batch).

**D3 - DONE - `5dfacca`.** I02, Qt only. New `tests/_e2e_ui_close_during_run.py`: three trials, each its own
process, harness I02's N3D case, close timed as I02 does (`close()` + 1 s pump), split into stop -> join,
worker exit, the three hosts' shutdown and the viewer child's exit, the worker's stack sampled every 50 ms.
Before (1 trial): close 11.57 s, join hit its 10.0 s timeout, the worker ended 17.2 s after the close
began, inside `write_animation`, `run_export` and the report's field figures - the stop itself landed
within a step (stop rule not triggered: no time is spent in a native step). So the window waited 10 s for
the model-folder writes and then the real app exited under a half-written folder (the worker is a daemon
thread). Fix: `RunController.shutdown` waits `CLOSE_JOIN_S = 2.0` s; new `RunController.finish_writes()`
(bounded `FINISH_S = 300` s, one stderr line) is called by `ui.app.main()` after `app.exec()` returns, so the
folder is finished with the window already gone. Files: `ui/run_controller.py`, `ui/app.py` (`main()` only),
`tests/test_ui_drain.py` (T9), the new script. Criteria:
- the script prints 3 Qt times and exits 0 - PASS: **3.54, 5.20, 5.15 s** (rule < 12.0 s, 3 of 3); each
  trial's model folder after `finish_writes`: `manifest.json` `finished`, `report.html` present, 0 failed rows.
- `test_regression.py` byte-identical when `solvers/` changed - `solvers/` not changed; run anyway last: PASS.
- Tk not measured, `gui/app.py` not edited - PASS.

## Files touched

`blastlab/ui/view3d_host.py`, `blastlab/ui/app.py` (`closeEvent` host tuple; `main()` tail),
`blastlab/ui/run_controller.py`; tests `test_ui_view3d_host.py`, `test_ui_close_guard.py`, `test_ui_drain.py`,
`_e2e_ui_view3d.py`; new `_e2e_ui_viewer_noise.py`, `_e2e_ui_close_during_run.py`; this report.

## GUI screens touched (for QA)

- Run tab 3D view: Detach / Re-attach / closing the detached window on the native mount (the detached
  window now opens where the card was, framed, and stays).
- Closing the main window: with a 3D Setup preview open (no Qt warnings), and during a run (window gone in
  2.5-4.2 s; the process stays until the stopped run's folder is written).

## Numerical changes

None.

## Engineering issues noticed

1. `git commit` in this worktree ran `gc --auto`, which tried to prune other worktrees' admin folders
   (`.git/worktrees/wt-final-gui`, `.git/worktrees/agent-a705b372cf00bfc67`); it failed with "Permission
   denied", so nothing was lost. My last commit used `-c gc.auto=0`. Recommendation: set `gc.auto 0` (or
   `gc.worktreePruneExpire never`) in the main repo's config while parallel worktrees are in use.
2. In D3 trials 2-3 `viewer_link.close()` took 2.1 s instead of 0.5 s (the child did not exit at once and
   was waited for). Inside the budget; not investigated further.
3. `_e2e_ui_viewer_place.py` writes `viewer_place.json` into the repo root (cwd); I deleted my copy. A
   `--out` default in the scratch/temp folder would keep worktrees clean.

## Open questions for the owner

1. `FINISH_S = 300` s: after the window closes during a run, the process waits up to 5 minutes for the
   stopped run's folder (a big 3D case's figures, or a blastFoam stop that copies `foam\`). Recommendation:
   keep 300 s; a smaller bound brings back the half-written folder this fixes.
2. Closing the window during a run still writes the full model folder (animation, figures, report) after
   the window is gone. Recommendation: keep it - it is the same folder a Stop writes; skipping figures on
   quit would be a behaviour change the plan did not ask for.
