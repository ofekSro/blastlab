# Implement report: Part D, group 2 (D4, D6) of the final-gui batch

- **Plan:** `docs/batches/2026-10-12-gui-final.md` Part D, tasks D4 and D6 only (risk: high).
- **Base:** `872c7de` on `final-gui`. The worktree branch started at `a4a8f4d`, an ancestor, and was
  fast-forwarded to `872c7de` before any work.
- **Parallel:** D1-D3 (viewer, close) and D5 (seed) ran in other worktrees. This group owned WSL and
  ran everything offscreen. No 3D viewer child was started.
- **WSL hygiene:** `pgrep -a blastFoam` was empty before every WSL run. The CLAUDE.md §8.2 dry run read
  `False`. Every run used throwaway settings and a runs folder under `%TEMP%`, outside OneDrive.

## D4 - G15Q-5a: `0 %` after a Stop during blockMesh - DONE

- **Source of the 1.0:** `MainWindow.on_finished` called `run_panel.mark_complete()` for any
  `(stopped_early=False, errored=False)`.
  - A Stop during blockMesh raises `StoppedBeforeStart`. The worker posts no result and no
    progress, so the controller reports `(False, False)`.
  - Measured with counters in the repro: 0 progress posts and 1 `mark_complete` call. No mesh
    stage posts progress: the only `hooks.progress` call is `runloop.py:528`, on solver lines.
- **Fix:** `ui/app.py:1419`. The bar is filled only when `how == 'done'`, which means a result
  landed and the run was not stopped and did not fail. The change sits in the run-progress code
  only.
- **Files:** `blastlab/ui/app.py`, `blastlab/tests/test_ui_run_screen.py` (R6),
  `blastlab/tests/_e2e_ui_stop_in_mesh.py` (new, WSL).
- **Tests:**
  - `gate.py --changed HEAD`: 42/42 green.
  - `cd blastlab/tests && python -u _e2e_ui_stop_in_mesh.py`.
- **Criteria:**
  1. Fast check: **PASS**. R6 in `test_ui_run_screen.py` runs: start, Stop recorded, no progress,
     no result, then `on_finished(False, False)`. It expects `0 %`, bar 0 and `Stopped after`. A
     control checks that a run ending on its own still reads `100 %` and bar 1000.
     - Deviation: the plan said "fake progress 1.0 from a mesh stage". No mesh stage posts
       progress (measured), so the check reproduces the real sequence instead.
  2. WSL repro: **PASS**. Harness F07's case was used (axisymmetric 5 x 5 m at 4 mm). Stop was
     pressed 0.3 s after the blockMesh line, and the run ended 1.3 s later.

     | | Percent tile | Bar | Time line | Progress posts / `mark_complete` calls |
     |---|---|---|---|---|
     | Before | `100 %` | 1000 | `Stopped after 1 s` | 0 / 1 |
     | After | `0 %` | 0 | `Stopped after 1 s` | 0 / 0 |
- **Commit:** `728e08a`

## D6 - 1D (and 2D) live gauges update live, both solvers - DONE

- **What changed:**
  - `backend.py`: `_emit_gauges` is now called from the 1D `on_frame` (`:1150`) and the 2D
    `on_frame` (`:1597`), next to the frame it rides.
  - `backend.py` (`:1174`, `:1660`, `:2435`): each solve sets `loop.gauges`. `runloop.tail_live`
    calls the new `gauges` callback with each live frame it emits, for 1D, 2D and 3D.
  - `_reset_gauge_live()` (`:707`) runs at the start of each solve.
  - `ui/live_gauges.py` now uses explicit `None` checks for `times` and `pressures`.
- **Already in place:**
  - The trailing-edge redraw: `GaugeColumn._cool`, a single-shot timer with `_cooled`, since
    `dc39a3e`.
  - Numbering by entered number in the 1D `run_started` (GUI-16 (f), `_live_gauges`).
  - Neither was changed. The new test pins both. `REFRESH_MS` is still 500.
- **Added beyond the plan's file list:**
  - `reader.read_probes(quiet=True)`, used only for the live read. The first real WSL run printed
    `probes: rho/U times do not match p` to stderr on almost every live read: 154 lines in 100 s.
    A torn tail is the normal state of a file mid-write.
  - The final read is unchanged and keeps its stderr line. That line is pinned in
    `test_foam_reader.py`, which gains one additive check for `quiet`.
- **Design note:**
  - The first version passed `gauges=` as a `FoamRunLoop` constructor argument. That broke
    `test_vtk_protect.py`, whose `FakeLoop` stand-in has the 8-argument signature.
  - The committed test was not edited. `gauges` became a class-default attribute set after
    construction.
- **Files:**
  - `blastlab/solvers/foam/backend.py`, `runloop.py`, `reader.py`
  - `blastlab/ui/live_gauges.py`
  - `blastlab/tests/test_ui_live_gauges_1d.py` (new), `test_foam_reader.py` (+1 check),
    `_e2e_ui_live_gauges_foam1d.py` (new, WSL)
- **Tests:**
  - `gate.py --changed HEAD`: 42/42 green. This included `test_ui_live_gauges.py`,
    `test_ui_run_screen.py`, `test_foam_live_due.py`, `test_foam_reader.py` and `test_vtk_protect.py`.
  - `python -u test_ui_live_gauges_1d.py`: 20/20.
  - `python -u _e2e_ui_live_gauges_foam1d.py` on WSL.
- **Criteria:**
  1. Native 1D draws more than one series length before `final`: **PASS**. A real 3 m / 5 mm run
     drew `[26, 349, 672, 1032, …, 2135]` before the final 2227.
     - Native already did this once a run outlasts `REFRESH_MS`. The negative control, run on the
       pre-D6 code, passes L1 too. The owner's symptom was the blastFoam path.
  2. blastFoam 1D and 2D with stubbed probes: **PASS**.
     - `on_frame` reaches `hooks.gauges` 3/3 times. The first one gets through even with the
       previous run's stamp set a moment earlier, which shows the per-run reset works.
     - `tail_live` reaches it 2/2 times. Every payload has `ndarray` times.
     - Through the real `GuiHooks` queue and `RunController._drain`, no
       `[ui error handling 'gauges']` appears.
     - Negative controls in a scratch copy:
       - The pre-D6 backend, runloop and live_gauges fail 10 checks.
       - The fixed backend with the old `live_gauges.py` logs `[ui error handling 'gauges']` for
         1D and 2D.
  3. `test_ui_live_gauges.py`, `test_ui_run_screen.py` and `test_foam_live_due.py` exit 0:
     **PASS** (gate).
  4. One short real 1D blastFoam run on WSL: **PASS**.
     - The case: 500 cells, 1 kg, 5 m, 4 gauges.
     - 79 live payloads arrived, the first at 5.4 s (3 samples), then 64, 116, 174 … 4255. The
       final arrived at 99.9 s of a 101.8 s run.
     - No UI error, and no stderr noise after the `quiet` change.
     - An extra 2D planar check (a scratch script, not committed) gave 170 live payloads in 412 s.
- **Commit:** `125850d`

## Closing

- `gate.py --only regression` (`test_regression.py`, run last after both commits): 1/1 green,
  `regression (byte-for-byte): PASS`.
- The closing matrix for D4+D6 is the `--changed HEAD` gate above (42/42). The part-wide
  `--changed 872c7de --deep` gate is the verifier's, after the orchestrator merges the groups.
- App start: a `MainWindow` was built offscreen, every tab was visited, and the window closed
  cleanly (`APP START: OK`).

## Files touched

- `blastlab/ui/app.py`, `blastlab/ui/live_gauges.py`
- `blastlab/solvers/foam/backend.py`, `runloop.py`, `reader.py`
- `blastlab/tests/test_ui_run_screen.py`, `test_foam_reader.py`, `test_ui_live_gauges_1d.py` (new),
  `_e2e_ui_stop_in_mesh.py` (new), `_e2e_ui_live_gauges_foam1d.py` (new)

## GUI screens touched (for QA)

- 02 Run: the progress bar and percent tile after a Stop during meshing.
- 02 Run: the live-gauge column and the Gauges view during a blastFoam 1D or 2D run.

## Numerical changes

None. No solver arithmetic changed. The live probe read is display only, and the final
`read_probes` is unchanged (`quiet` defaults to False).

## Engineering issues noticed

1. **A Stop at stage 2's meshing in a chain reads `Done`.** In `on_finished`, `_run_got_result` is
   True from stage 1, so `how` becomes `'done'`. The bar also keeps stage 1's 100 %, because
   stage 2 never posts `run_started`. This was not changed, since it is out of D4's scope.
   **Recommendation:** treat `_stop_asked` as `stopped` whenever the last stage posted no result.
2. **WSL scratch dirs left by the D4 repro.** Each Stop during meshing keeps its scratch, as
   designed: `20261013-122030_2d_p53244-00`, `-122107_2d_p53524-00` and `-123509_2d_p34496-00`
   in `/root/blastlab_runs`, each a few MB of mesh-stage files. Nothing was deleted.
   - The three completed D6 runs (`123544_1d`, `123915_1d`, `124211_2d`) had their scratch
     released by the app's normal OUT-1 model-folder flow, which copies to the temp model folder
     and then deletes the run's own scratch. No pre-existing run was touched.
3. **Git maintenance warning.** Every fast-forward and commit printed `failed to delete
   '.git/worktrees/wt-final-gui': Permission denied`. Git's worktree prune hits a stale or locked
   admin dir from another session. It is harmless here. **Recommendation:** the orchestrator
   checks `git worktree list` after merging.
4. **The 1D live probe read costs a full re-read of `postProcessing/gauges` per second** over 9p.
   On the owner's 7,500-cell run that is cheap next to 0.176 s/step, but it grows with run length,
   as 3D already did. **Recommendation:** none now. Revisit with the P1 parallel-1D measurement.

## Open questions for the owner

- None blocking. Proposed decision rows, left unnumbered so they do not clash with the parallel
  implementers' rows:
  - **D4:** fill the bar only for `how == 'done'`. A run with no result and no Stop (`ended`) also
    stays unfilled.
  - **D6:** the live gauge callback is a `FoamRunLoop` attribute, not a constructor argument, so
    test stand-ins keep their signature. 3D gains `tail_live` gauges too, under the same 1 s
    throttle.
