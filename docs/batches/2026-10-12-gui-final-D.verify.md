# Verify report - gui-final Part D (D1-D6), depth full (risk: high)

Plan `docs/batches/2026-10-12-gui-final.md` Part D. Base `872c7de`, branch `final-gui`, HEAD `9746d1d`
(the merged result of groups D-g1 `5dfacca`/`65e1aaf`/`852472b`, D-g2 `728e08a`/`125850d`, D-g3
`dd192de`). Office PC (128 GB). Cleanup dry run `False` before any window; `pgrep -a blastFoam` empty
before every WSL use. No fix was needed: no commit other than this report. Logs: session scratchpad
`d-verify\`.

## Per task

**D1 GUI-16 (g) - VERIFIED.**
- `_e2e_ui_view3d.py` on the real platform (QT_QPA_PLATFORM unset, Win32 `GetParent`/`IsWindowVisible`
  every 50 ms): exit 0. Detach: top-level after 0.09 s, parent 0 and visible for 40 samples / 2 s, no
  re-embed; Re-attach: parent = mount after 0.12 s; WM_CLOSE on the floating window re-attaches after 0.20 s.
- `test_ui_view3d_host.py` green (gate). Negative control (Part D source reverted in a scratch worktree):
  V10/V11 fail 3 checks (`re-reported handle is NOT re-embedded`, `closing the floating window re-attaches`,
  `handle ... embedded again`).
- Diff read: the early return in `on_window` while `_floating` is safe on the container path too (there
  `_embed` was already a no-op with a container); the failed-embed path no longer re-tries in a loop.

**D2 G14Q - VERIFIED.**
- `_e2e_ui_viewer_noise.py` real platform: `External WM_DESTROY messages: 0`, other Qt messages 0, exit 0.
- Negative control: the same script against the reverted source prints **2** (`viewWindow` and
  `QWidgetClassWindow` at `close`, parent `QStackedWidgetClassWindow`), exit 1 - the count the docstring records.
- `_e2e_ui_view3d.py` exit 0 (above); `_e2e_ui_viewer_place.py` exit 0 (run with cwd in the scratchpad so
  `viewer_place.json` stays out of the repo). Its ungated `resize` row read 305.2 ms (implementer 228.6 ms);
  not touched by this part.
- `test_ui_close_guard.py` C5 green; reverted source: C5 fails (`['run', 'results']`).

**D3 I02 - VERIFIED.**
- `_e2e_ui_close_during_run.py` real platform: **5.08, 4.36, 5.12 s** (rule < 12.0 s, 3 of 3); stop->join
  2.01 s each; worker gone at 11.3 / 10.8 / 16.6 s inside `write_animation` / `run_export` / report figures
  (no time in a native step - stop rule not triggered); every model folder `finished`, `report.html`, 0 failed.
- The merged `ui.app.main()` path itself (the e2e calls `finish_writes` by hand): scratch probe
  `main_probe.py` runs the real `main()`, starts N3D, closes 2 s into the solve. `close()` returned in 4.1 s
  with the window hidden (Win32 `IsWindowVisible` False); `main()` returned at 15.0 s after one stderr line,
  worker gone, manifest `finished`, report present, 0 failed. Exec code 0.
- `test_ui_drain.py` T9 green; reverted source: `AttributeError ... CLOSE_JOIN_S`.
- `solvers/` untouched by D3; `gui/app.py` not edited (diff stat: nothing under `blastlab/gui/`).

**D4 G15Q-5a - VERIFIED.**
- WSL repro `_e2e_ui_stop_in_mesh.py`: `percent tile '0 %'`, bar 0 of 1000, `Stopped after 1 s`,
  0 progress posts / 0 `mark_complete`, log `[stopped during 'blockMesh']`, PASS.
- Fast check R6 in `test_ui_run_screen.py` green; reverted source: R6 fails with `'100 %' 1000`. The
  implementer's deviation (replays the real sequence instead of a fake mesh-stage 1.0) is sound: no mesh
  stage posts progress (`runloop.py` posts only on solver lines), and the control (`100 %` on a normal end) holds.
- `test_foam_stop.py` (WSL) PASS.

**D5 owner decision 4 - VERIFIED.**
- `test_ui_chain_screen.py` and `test_ui_char_chain_wiring.py` green (gate). Golden diff `872c7de..HEAD`:
  exactly 6 lines `"Lz": "1.5"` -> `"Lz": "2.5"`, nothing else. Reverted source: both D5 checks fail
  (card 3 `1 warning`) and the char golden differs.
- The probed probe the implementer could not run (WSL was busy): run now (`probed`, VM 14 cores / 63 GB,
  measured). Stage 3 opens at Lz 2.5; 1->2->3 native and blastFoam at 2.5: cards 1-3 `case OK`, 7 ranks,
  360,000 cells; at 1.5 card 3 warns F45; burst 1.0 trades it for S2-1 on card 2. Unprobed re-run: the cap
  1,113,510 cells the comment cites, 360,000 cells / 7 ranks. Table reproduced.

**D6 owner 2026-10-13 - VERIFIED.**
- `test_ui_live_gauges_1d.py` 20/20 (gate); reverted source: 12 checks fail (1D and 2D: no `on_frame` /
  `tail_live` gauges, no ndarray, not quiet, no draw). `test_ui_live_gauges.py`, `test_ui_run_screen.py`,
  `test_foam_live_due.py`, `test_foam_reader.py` green; reverted reader: `TypeError ... 'quiet'`.
- WSL `_e2e_ui_live_gauges_foam1d.py`: 83 live payloads (first at 5.6 s, 4 samples, then 54, 104, 154 ...
  4264), final at 104.4 s of 106.3 s, no `[ui error handling 'gauges']`, PASS. An accidental first run
  that loaded the pre-D6 backend (see Process note) gave **0 live payloads, 1 final** - the owner's symptom.
- WSL suites over the touched solve path: `test_foam_1d_vs_native.py` PASS (90 s), `test_foam_2d.py` PASS
  (463 s), `test_foam_stop.py` PASS.
- Diff read: `_emit_gauges` runs in the worker thread and posts through the hooks queue; the throttle stamp
  is reset per solve; `quiet` defaults False so the final read and its pinned stderr line are unchanged;
  `FoamRunLoop.gauges` is a class-default attribute, so `test_vtk_protect.py`'s stand-in keeps its signature.

## Part-wide

- `gate.py --changed 872c7de --deep`: **96/96 suites green**, 21.8 min (Tk `test_gui_*` skipped by gate).
- `gate.py --only regression` last: **byte-for-byte PASS**.
- `foam_golden/`, `foam_fixtures/`, `baseline/`, `blastlab/gui/`: no diff `872c7de..HEAD`.
- Merged `ui/app.py` read as a whole: `on_finished` (D4), `closeEvent` (D2) and `main()` (D3) do not
  interact; the hooks queue is unbounded and the worker has no GUI round-trip, so `finish_writes` after
  `app.exec()` cannot deadlock.

## Defects

None introduced by Part D. Pre-existing, not fixed (out of the D4 acceptance):
1. `ui/app.py:1412-1416` (medium): a chain stopped during a later stage's meshing (or between stages) ends
   `how = 'done'` - the earlier stage's result sets `_run_got_result`, the controller's `stopped_early` is
   False - so the bar keeps stage 1's 100 % and the banner says Done. Raised by the D-g2 implementer; same
   before Part D.

## Engineering questions

1. D3 `FINISH_S = 300` s: after the window closes during a run, the process may stay up to 5 min with no
   window (one stderr line; nothing visible under `pythonw`). Keep, or show a small "finishing" notice?
2. The chain `how` above: count a Stop as `stopped` whenever the last stage posted no result? (owner call)

## WSL / process notes

- Scratch dirs kept in `/root/blastlab_runs` (nothing deleted): D4 repro `20261013-140958_2d_p63184-00`,
  plus D-g2's three. The D6 runs' own scratch was released by the app's OUT-1 flow, as designed.
- Process slip, repaired: one `git checkout 872c7de -- <8 source files>` meant for the scratch worktree ran
  in the main tree (a failed `cd` on the 8.3 path). Restored with `git checkout HEAD --` within ~30 s; the
  deep gate that overlapped it was stopped by PID and re-run; the D6 e2e that overlapped it was let
  finish (the 0-payload run above) and re-run. `git status`
  clean afterwards (only the untracked `docs/vv-plan.md`).
- The scratch worktree was removed; git could not delete its admin dir `.git/worktrees/wt` (Permission
  denied, like the stale ones); `git worktree list` no longer shows it.

## GUI screens for QA

- Run tab 3D: Detach / Re-attach / closing the detached window on the native mount.
- Closing the main window with the Setup 3D preview open, and during a native 3D run.
- 02 Run: bar and percent tile after a Stop during meshing; live gauge column during blastFoam 1D / 2D.
- Chain screen: stage 3 opens at Lz 2.5.

Verdict: Part D holds on the merged branch - all six tasks VERIFIED, no fix needed.

## Status

- D1 GUI-16 (g): VERIFIED
- D2 GUI-16: VERIFIED
- D3 GUI-16: VERIFIED
- D4 GUI-16: VERIFIED
- D5 GUI-16: VERIFIED
- D6 GUI-16: VERIFIED
