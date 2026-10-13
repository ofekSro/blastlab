# gui-final-round2 - UX review, clean loop round 2 (read-only)

- **Date:** 2026-10-14. **Tree:** branch `final-gui` at `5b0f603`, batch range `9cc172d..5b0f603`
  (code commits `187f832`, `b9775cf`, `9c8b723`, `17b5747`, `1ea0dce`, `612e5d3`).
- **Plan:** `docs/batches/2026-10-13-gui-final-round2.md`, with owner answers Q1-Q4 and rows D-R5..D-R10.
  Verify reports `-A.verify.md` and `-B.verify.md` sit next to it. Previous review:
  `docs/qa/2026-10-13-gui-final-round1/ux-review.md` (U1..U6).
- **Scope:** the Qt GUI `blastlab/ui/` only. The Tk GUI (`blastlab/gui/`) is frozen and out of scope.
- **Method:** I read the batch diff, its call sites, and the worker and model-folder message order. I ran no
  window and no solve, so this review makes no geometry or on-screen-timing claim (CLAUDE.md §8.7). Where the
  Part A verifier's live screenshots (`A1_mesh.png`, `A2_stopped.png`, `A4_card.png`) settle a point, I cite them.
- **Clean-loop rule** (`2026-10-12-gui-final.md:315-322`): every finding at any severity goes into the next
  round, so there is no parking section.
- **Not findings:** a point that repeats an answered decision. U6 is "by design (D66, D4)" (Q2). The trailing
  `(detail: …)` is D-R10. A title that says TNT while the method card names the case's material on an old
  meta with no `material` follows D-R9.

**Short answer.** Round 2 closes U1, U2, U4 and U5, and most of U3. The Run screen now belongs to the stage
being meshed, and a stopped chain explains itself. Four small leftovers remain, all low, and two of them sit
next to the round-2 fixes. **0 high, 0 medium, 4 low.**

## 1. Framework and screens

PySide6 with pyqtgraph plots. The 3D viewer runs as its own process. The solver runs on a `threading.Thread`
(`solvers/worker.py`) and talks to the GUI through a `queue.Queue`, which a QTimer drains
(`run_controller._drain`). Results loads go through a `ThreadBridge`. No widget is touched from the worker.

| Screen | Purpose (as far as this review goes) |
|---|---|
| 01 Setup, Checks | The live validation list, including the "Ignition radii not checked" warning (B2) |
| Chain 1D → 2D → 3D | Route, stage cards, per-stage editors and Checks, refusal dialogs, compat line (A5) |
| 02 Run | Bar, percent tile, time line, title, chain strip, finish banner, gauge column with the enlarged card, log and Messages dock, Stop question (A1-A4) |
| 03 Results | Entries, Field (1D canvas title, 2D/3D map titles), Gauges, 3D, method card, exports (B1) |

The other Qt screens (topbar, run browser, viewer host, HD 1.3) have no change in this batch. Round 1 raised
nothing on them, and I found nothing new.

## 2. User flows (evidence)

**F1 - a blastFoam 1D → 2D chain while stage 2 meshes (A1).**
1. The worker queues `('stage', 1, label)` before stage 2's solve (`worker.py:328`). The controller logs it
   and calls `on_stage(1)` (`run_controller.py:346-353`).
2. `on_stage` (`app.py:1231-1251`) does the following:
   - it picks `meshing` for a blastFoam stage and `starting` for a native one (D-R7);
   - it restarts the stage clock (D-R6) and sets `_chain_k = 2` and `_run_pct = None`;
   - it calls `run_panel.begin_stage('meshing stage 2')`, which sets the bar and the tile to `0 %` and the
     time line to `meshing stage 2 · … elapsed` with no ETA (`run_panel.py:1597-1606`, `:1450-1451`);
   - the title becomes `Chain 2/2 · …` with no percent (`app.py:823-826`);
   - pill 2 shows `running · meshing` (`chain_strip.py:370-386`).
3. A Stop now asks `Stop <model> (stage 2 of 2, meshing)?` (`app.py:1204-1207`).
4. `on_run_started` restarts only the ETA (`run_clock.restart_eta`), leaves `_chain_k` as it is, and resets the
   STEP/TIME/dt/P MAX tiles and the live pane. Only then does the gauge column take stage 2's case
   (`app.py:1253-1275`, `run_panel.py:1608-1642`).
5. **What stays on screen from stage 1 during the mesh:** the STEP/TIME/dt/P MAX tiles, the live slice, and the
   gauge column with stage 1's case and final traces. The verifier saw the first two live (`-A.verify.md:23-24`)
   → finding N1.

**F2 - Stop during stage 2's mesh (A2).** `on_finished` gives `how = 'stopped'`. The `reset_bar` branch
(`app.py:1459-1461`) is now never taken, because `_chain_k` (2) is above `_run_n_results` (1). It is dead code,
but harmless. `_finish_notice` (`app.py:1490-1502`) writes:
- banner: `Result ready: M · stage 1 of 2 finished; stopped by user during stage 2.`
- time line: `Stopped after 30 s · stopped by user during stage 2 of 2`

The strip reads `02 2D stopped`, with the caption `Chain stopped at stage 2 of 2`. This matches
`A2_stopped.png` and D-R8. A failed mesh in stage 2 now marks pill 2 `failed`, because `_current` has moved
on to it.

**F3 - blastFoam run with Keep all (A3).** Inside the stage's `solve`, `model_folder` calls
`hooks.folder_written` (`model_folder.py:1457`), which happens before the worker queues `('result', …)`
(`worker.py:356`). The drain then runs two steps in one pass:
1. `folder` → `notify('WSL scratch kept (Keep all fields): /root/…', 'info')` (`run_controller.py:358-367`);
2. `result` → `notify('Result ready: <label>')` (`app.py:1446`).

The status line is overwritten within the same drain. The path stays in Messages (`run_dock.py:206-217`), which
has no unread marker, and in the log as a `[note]` line that is now muted (`run_panel.py:1503-1504`) → N2, N3.

**F4 - Chain screen, route 1D → 3D (A5).** `chain_route.by_position` (`chain_route.py:164-178`) rewrites
`Stage 3 (3D):` to `Stage 2 (3D):` in `_refuse` (`chain_panel.py:328`). The compat line uses the position
(`chain_panel.py:359-361`), and so does the long-run dialog (`app.py:1126`). The cards, strip, refusals and
dialogs now agree. U4 is closed.

**F5 - Results, C4 blastFoam 1D and 2D (B1).** `plots.charge_material` (`plots.py:50-55`) feeds `charge_label`
(2D/3D maps, animation) and the 1D builders. The 1D canvas title (`results_fields.py:90-103`, `:447-464`), the
PNG and report exports (`exports.py:199-208`, `:230-238`) and the CLI pop-ups (`cli_run.py:392-395`) all read
`kg C4`. A TNT result, or a meta with no material, is byte-identical. The Gauges screen title carries no
charge, as before (`results_gauges.py:601`).

**F6 - Setup Checks, incomputable layout (B2).** `_det_radii_unchecked` (`validation.py:1460-1495`) reads:
`Ignition radii not checked - the cell layout could not be computed from the domain size (2 x 2 m) and cell
size (6.579 mm). The run still refuses … (detail: ZeroDivisionError: …)`. Without a plan, the `dx` it names is
the charge-refined `effective_dx` (`validation.py:1415-1420`), not the form's cell size → N4.

**F7 - Live gauge card, early peak (A4).** When the peak lies in the left half of `0..t[-1]`, the anchor flips
to `(-0.05, 0.5)` (`run_gauges.py:657-661`). The x-range is that same `0..t[-1]` (`:671-683`), so the test and
the view agree. `A4_card.png` shows the label whole. Its box overhangs the top by about 4 px, but the text is not
clipped, so this is not a finding.

## 3. Round 1 items - status

| Round 1 | Status at `5b0f603` | Evidence |
|---|---|---|
| U1 - the screen shows the finished stage while the next one meshes | **Closed**. Bar, time line, title, pill and Stop question belong to stage 2. Leftover tiles, pane and gauge column → N1 | `app.py:1231-1251`; `A1_mesh.png` |
| U2 - `Stopped` followed by stage 1's own ending | **Closed** | `app.py:1490-1502`; `A2_stopped.png` |
| U3 - the Keep-all scratch is announced only in the log | **Mostly closed**. Messages has it. The status line loses it at once → N2 | `run_controller.py:358-367` |
| U4 - stages numbered by dimension | **Closed** (Q1, A5) | `chain_route.py:164-178`, `chain_panel.py:328`, `:359-361`, `app.py:1126` |
| U5 - a Python exception leads the radii warning | **Closed** (D-R10 keeps the trailing detail). Cell-size wording → N4 | `validation.py:1460-1495` |
| U6 - Pa stop reasons, three coordinate precisions | **By design** (Q2: D66, D4) | owner 2026-10-13 |

## 4. Findings

**N1 - low - 02 Run, a later chain stage's mesh - the readout tiles, the live slice and the gauge column still
show stage 1.**
- **Where:**
  - `app.py:1231-1251`: `on_stage` does not reset the readouts and does not hand the gauge column the new case;
  - `run_panel.py:1597-1606`: `begin_stage` resets only the bar, the tile and the time line;
  - the resets live in `on_run_started` (`run_panel.py:1620`, `app.py:1275`).
- **What the user sees:** for the minutes of blockMesh, the header says `meshing stage 2` at `0 %`. Below it,
  STEP, TIME and P MAX still give stage 1's final values, the slice shows stage 1's last frame, and the gauge
  column lists stage 1's radii and peaks. This is a weaker form of U1: the headline is right, the detail
  is not.
- **Fix:**
  - In `begin_stage`, call `_reset_readouts_text()`, so the tiles read `—`.
  - In `on_stage`, call `run_panel.set_gauge_case(cases[k])`, so the column shows stage 2's gauges as
    `waiting`.
  - Give the live pane a caption `stage 1 final frame` until `start_1d` / `start_2d`, or clear it.
  - Pin: extend `s7_round2` to assert that the tiles read `—` after `stage` 1.

**N2 - low - 02 Run, Keep all (A3) - the status-line half of the notice is overwritten in the same drain.**
- **Where:** `model_folder.py:1457` (`folder_written` inside the solve), then `worker.py:356` (`result`);
  `run_controller.py:358-367` → `app.py:1446` `notify('Result ready: …')`; `run_dock.py:206-217`, where
  Messages has no unread marker.
- **What the user sees:** the status line goes straight to `Result ready: …`. The scratch path, the largest
  thing a run leaves in a vhdx that never shrinks (CLAUDE.md §8.5), is only in a dock page the user has to open.
- **Fix:** hold the kept path in `on_stage`/`folder` state and say it after the result:
  - add a second line to the finish banner, `WSL scratch kept (Keep all fields): /root/blastlab_runs/<run>`; or
  - call `notify` from `_finish_notice` after the result's notice, so the last status text is the scratch path.

  A count badge on the Messages tab for `info` rows added since it was last shown would also do.

**N3 - low - 02 Run log - `[note]` in the muted colour dims every note, not only the kept-scratch line.**
- **Where:** `run_panel.py:1503-1504`. `muted` is also the theme's disabled-text colour (`theme.py:202`,
  `:280`, `:315`). The other `[note]` lines are:
  - `solver2d.py:149` and `solver3d.py:174`: charge truncated by a wall;
  - `solver3d.py:187`: charge under-resolved;
  - `solver1d.py:74`, `solver2d.py:182`, `solver3d.py:210`: cell size adjusted;
  - `backend.py:369`: the ignition radius;
  - `backend.py:400`: `blastFoam set … kg of explosive`;
  - `backend.py:1210`: stopped before the end time.
- **What the user sees:** physics notes that an engineer should read, for example the mass blastFoam actually
  set or a truncated charge, now show fainter than ordinary step lines. The priority is inverted. Round 1 (U3)
  suggested this colour without checking the other `[note]` users.
- **Fix:** give `[note]` a readable neutral that is not the disabled colour (`text2` or the accent), or mute
  only the `WSL scratch kept` line. Update the A3 pin (`test_ui_run_screen.py:2024-2032`) to match.

**N4 - low - Setup / Checks (B2) - the warning names a cell size the user did not type.**
- **Where:** `validation.py:1415-1420`, where `dx` is the charge-refined `effective_dx` or the plan's `dx_base`,
  then `:1493-1494`, where it is called `cell size`. The Part B verifier noted the same (`-B.verify.md:71-74`).
- **What the user sees:** a user who typed 20 mm reads `cell size (6.579 mm)`. Nothing on the form shows
  6.579 mm, so the warning points at the wrong input.
- **Fix:** say `base cell (6.579 mm, from the 20 mm cell size refined for the charge)`. Pass `case.cell_size_m`
  as a second value, and give only the entered one when the two match. Wording only: the B11 pins
  (`test_case_validate.py:170`, `:194`) and `test_det_radii_text.py` stay green if it still starts with the
  domain size.

## 5. Proposed layout - 02 Run during a chain stage's mesh (after N1)

```
CHAIN · wall_A   (01 1D ✓ 14 s) → (02 2D meshing)
                 Stage 2 of 2 · the last stage
[▯▯▯▯▯▯▯▯▯▯▯▯]  0 %    meshing stage 2 · 19 s elapsed
STEP —   TIME —   dt —   P MAX —                         <- N1: no stage-1 numbers
[live pane: "stage 1 final frame" caption, or empty]     <- N1
Gauges column: stage 2's gauges, all "waiting"           <- N1

after the run, Keep all ticked:
Banner: Result ready: wall_A · end time reached.  Files in …\wall_A\
        WSL scratch kept (Keep all fields): /root/blastlab_runs/<run>   <- N2
```

## 6. Quick wins

1. **N3:** change one tuple in `_LOG_TAGS` (`muted` → `text2`, or match `WSL scratch kept` only) and one pin.
2. **N1 (tiles):** one `_reset_readouts_text()` call in `begin_stage`, plus one assert in `s7_round2`.
3. **N1 (gauges):** one `set_gauge_case(cases[k])` call in `on_stage`.
4. **N2:** keep the kept posix on the controller and add it to the banner in `show_finish`, or re-notify it from
   `_finish_notice`. About 6 lines, no `services/` change.
5. **N4:** add the form's cell size to the B2 sentence (one more keyword argument, the same pins).
