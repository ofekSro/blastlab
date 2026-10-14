# gui-final-round1 - UX review, clean loop round 1 (read-only)

- **Date:** 2026-10-13. **Tree:** branch `final-gui` at `159ece1`, batch range `00465a5..159ece1`.
- **Plan:** `docs/batches/2026-10-13-gui-final-round1.md`, QA brief at lines 101-118. Verify reports
  `-A.verify.md` (R1) and `-B.verify.md` (R2) next to it.
- **Scope:** the Qt GUI `blastlab/ui/` only. Tk (`blastlab/gui/`) is frozen and out of scope.
- **Method:** I read the batch diff, its call sites, the worker and backend message order and the
  brief's screens. I ran no window and no solve, so this review makes no geometry or on-screen-timing
  claim (CLAUDE.md §8.7).
- **Clean-loop rule** (`2026-10-12-gui-final.md:315-322`): every finding at any severity goes into
  round 2, so there is no parking section.

**Short answer.** R2 does what the user asked for. R1 fixes the word `Done`, but the chain screen
around it still describes the wrong stage. The cause is in the code before R1: on blastFoam, a later
stage counts as started only when its solver starts, not when its meshing starts. **0 critical,
0 high, 2 medium, 4 low.**

## 1. Framework and screens

PySide6 with pyqtgraph plots. The 3D viewer runs as its own process. The solver runs on a
`threading.Thread` (`solvers/worker.py`) and talks to the GUI through a `queue.Queue`, which a
QTimer drains (`run_controller._drain`). Results loads go through a `ThreadBridge`.

| Screen | Purpose (as far as this review goes) |
|---|---|
| 01 Setup, Checks | The live validation list. It covers trigger notes, gauge drops and the unchecked-radii warning, plus the Where column and the trigger dropdown |
| Chain 1D → 2D → 3D | Route, stage cards 01..03, a per-stage editor with its own Checks, and Run chain |
| 02 Run | Bar, percent tile, time line, finish banner, chain strip, gauge column, log and Messages dock, Stop with a confirm after 30 s |
| 03 Results | Entries list (a chain is one entry with STAGE tabs), Field, Gauges, 3D, method card, exports, Open a model folder, run browser |

## 2. User flows (evidence)

**F1 - a blastFoam 1D → 2D chain, Stop pressed while stage 2 is meshing (the R1 case).**
1. The worker queues `('stage', 1, label)` before it calls stage 2's solve (`worker.py:328`). The
   controller only writes `=== Stage … ===` to the log (`run_controller.py:347-348`).
2. The blastFoam stage then runs the WSL probe and the mesh pipeline: blockMesh, topoSet,
   refineMesh, setRefinedFields (`backend.py:62-84`, `:87-120`). It sends `run_started` only after
   that (`backend.py:1531`, `:2263`). `_chain_k` and the strip move only on `run_started`
   (`app.py:1231`, `:1238`).
3. What the window shows during stage 2's meshing:
   - the bar and the percent tile stay at stage 1's `100 %`;
   - the time line reads `… elapsed · about 0 s left`, because `eta_s(1.0)` is `0.0`
     (`run_clock.py:129-130`, `run_panel.py:1446-1449`);
   - the title reads `Chain 1/2 · 100 % · …` (`app.py:820-823`);
   - pill 1 is `done`, pill 2 is `waiting`, and the caption is still `Stage 1 of 2 · the 2D stage
     starts from …`.
4. Stop after 30 s asks `Stop <model> (stage 1 of 2) at 100 %?` (`app.py:1199-1201`).
5. The stop raises `StoppedBeforeStart` (`backend.py:56-59`), and the worker breaks with no result
   (`worker.py:331-336`). `on_finished(False, False)` then works like this:
   - `_stop_asked` is set and `_run_n_results` (1) is below `_chain_n` (2), so `how = 'stopped'`;
   - `_chain_k` (1) is at most `_run_n_results` (1), so `reset_bar()` sets `0 %` (`app.py:1416-1424`);
   - the strip's `finish('stopped')` uses `_current = 0`. Pill 2 becomes `not run`, and the caption
     reads `Chain stopped at stage 1 of 2` (`chain_strip.py:412-427`);
   - `_finish_notice` shows the banner from `_last_result`, which is stage 1's result. It reads
     `Result ready: <model> · <stage 1's stop_reason>.`, and the time line reads `Stopped after
     19 s · <stage 1's stop_reason>` (`app.py:1448-1454`, `run_panel.py:1185-1186`, `:1457-1459`).
6. Results: one chain entry, one `1D` tab, captioned `1D → 2D · 1 of 2 stages`
   (`results_method.py:292-293`). This is correct.

**F2 - a native chain stopped during stage 2's solve.** `run_started` has already fired, so
`_chain_k` is 2. Stage 2 posts a partial result with `stopped_early`, which gives `stopped` with
no `reset_bar`. Pill 2 is `stopped`, and the caption reads `Chain stopped at stage 2 of 2`. The
reason is `stopped by user`. Everything agrees (the second case of the new test,
`test_ui_chain_screen.py:1504-1524`).

**F3 - blastFoam 2D with "Keep all fields in WSL" ticked (R2).** The tooltip says the scratch stays
(`models/fields.py:280-283`). At the end, `verify_and_release_scratch` writes
`[note] WSL scratch kept (Keep all fields in WSL was ticked): /root/blastlab_runs/…` and returns no
notice (`model_folder.py:1283-1288`). `run_controller.py:354` then shows no dialog. The `[note]`
line is not coloured (`run_panel.py:1496`), and Messages takes only `[warn]` and `[error]`
(`app.py:1222-1223`). The finish banner names the model folder, not the scratch. Keep all with a
failed copy still warns (`test_model_folder.py:1483-1501`).

**F4 - Chain screen, route 1D → 3D or 2D → 3D.** The cards and editors number stages by position:
`01` and `02` (`chain_panel.py:455`, `:470`, `:695-697`). The strip does too: `Stage 1 of 2`
(`chain_strip.py:380`). The refusal and Checks prefixes number them by dimension:
- `Stage 3 (3D): …` (`services/chain.py:58`, `:70`, `chain_route.py:156-158`,
  `chain_panel.py:794`);
- the compat status line `Stage 3: …` (`chain_panel.py:358`);
- the long-run dialog `Stage 3D: …` (`app.py:1122`).

**F5 - Results, Open a model folder.** The folder is read off the GUI thread, the entry is posted
through the bridge, and a failure reaches the log and the status bar as `Open failed: …`
(`results_panel.py:1207-1231`, `app.py:1591-1600`). C12 holds here too: a reloaded blastFoam result
gets `eos = 'JWL'` before any title or export (`results_panel.py:1250-1255`), and live results carry
`JWL` from the backend (`backend.py:1299`, `:1310`, `:1760`, `:2530`). The screen title goes
through `display_eos` (`results_fields.py:71-80`). I found no path that titles a blastFoam 1D
result `idealGas`.

**Brief items not covered here** because they need a live window or a solve: live gauges during
blastFoam 1D/2D, Detach and Re-attach on native 3D, Close with the Setup 3D preview open, GIF `x`
markers, and the `m/kg¹ᐟ³` glyph rendering. The code holds the glyph with an ASCII fallback
(`scaled_distance.py:37-39`, `:69`). These belong to gui-qa-tester's live pass.

## 3. Findings

**U1 - medium - 02 Run and the chain strip - while a later blastFoam stage meshes, the screen
describes the previous stage, which has already finished.**
- **Where:**
  - `run_controller.py:347-348`: the `stage` message is only logged;
  - `app.py:1225-1238`: `_chain_k`, `_run_pct`, the clock's `stage()` and `stage_started` all move
    on `run_started`;
  - `backend.py:1531`, `:2263`: `run_started` comes after the mesh pipeline;
  - `run_clock.py:129-130`;
  - `app.py:1199-1201` (the Stop question), `:820-823` (the title).
- **What the user sees:** blockMesh, refinement and setRefinedFields for the 2D/3D stage can take
  minutes. All that time the screen shows `100 %`, `about 0 s left`, `Chain 1/2`, pill 2 `waiting`
  and a caption about stage 1. A Stop then asks "stage 1 of 2 at 100 %?". The run looks finished,
  or hung. This is also why R1 needed `reset_bar` and why the chain ends `at stage 1` (U2).
- **Fix:**
  - Forward the `stage` message to a new `handlers.on_stage(k)`, and set `_chain_k = k + 1` there,
    not in `on_run_started`.
  - In `on_stage`, for `k > 0`:
    - set `_run_pct = None`;
    - call `run_panel` to set the bar to 0, `_frac` to None and the time line to
      `meshing stage k+1 · … elapsed` with no ETA;
    - call `chain_strip.stage_started(k)` with the pill value `meshing`.
  - `on_run_started` then only restarts the stage's ETA.
  - Whether the stage clock (`stage()`) moves to the `stage` message, so that a pill's time
    includes its meshing, is a decision row (D50/D59 semantics).
  - Afterwards, R1's `reset_bar` branch (`app.py:1422-1424`) is no longer needed: the in-flight
    stage owns the bar. Keep the existing pins: the F25 bar reset (`run_panel.py:1589-1595`) and
    G15Q-5a.

**U2 - medium - 02 Run banner, time line and chain strip after an R1 Stop - "Stopped" is followed
by stage 1's own ending, and the strip names the stage that finished.**
- **Where:**
  - `app.py:1448-1454`: the banner reason is `_last_result.stop_reason`, which is stage 1's;
  - `run_panel.py:1457-1459`: the time line appends the same reason;
  - `chain_strip.py:412-427`: `finish('stopped')` with `_current` still on stage 1 marks pill 2
    `not run`, and the caption reads `Chain stopped at stage 1 of 2`.
- **What the user sees:**
  - with a native 1D stage 1, `Stopped after 19 s · shock arrived at outer boundary (p_last = …
    Pa)` and `Result ready: M · shock arrived at outer boundary …`;
  - with blastFoam, `… · end time reached`.
  - The line therefore says the run stopped and that it reached its end. The strip says stage 1
    stopped although its pill says `done`, and that stage 2 never ran although its mesh was being
    built.
- **Fix:**
  - In `on_finished`, when `how == 'stopped'` and the last result is not `stopped_early`, pass
    `_finish_notice` a reason of its own, `stopped by user before stage k+1 of n finished`, with
    `k = _run_n_results`. Use it for the banner and the time line, and keep stage 1's reason in
    the method card, where it belongs.
  - With U1 fixed, `_current` is the meshing stage, so pill 2 reads `stopped` and the caption
    `Chain stopped at stage 2 of 2`.
  - Without U1, `finish()` needs the index of the first stage that did not land.
  - Pin: extend the new R1 check to assert that the reason has no `end time reached` and that
    `strip.texts()[-1]` names stage 2.

**U3 - low - 02 Run, Keep all fields (R2) - the kept scratch is announced only by an uncoloured
log line.**
- **Where:**
  - `model_folder.py:1284`: the `[note]` line;
  - `run_panel.py:1496`: `_LOG_TAGS` has no `[note]`;
  - `app.py:1222-1223`: Messages takes only `[warn]` and `[error]`;
  - `run_panel.py:1181-1190`: the banner names the model folder only.
- **What the user sees:** removing the dialog was right, because the user asked for this outcome.
  But a Keep-all scratch is the largest thing a run leaves behind, and `ext4.vhdx` never shrinks
  (CLAUDE.md §8.5). Nothing outside the scrolled log says where the scratch is.
- **Fix:** add one `info` `notify()` (status bar and Messages, not modal): `WSL scratch kept (Keep
  all fields): /root/blastlab_runs/<run>`. Optionally give `[note]` the theme's muted colour in
  `_LOG_TAGS`. No services change.

**U4 - low - Chain screen - stages are numbered by position on the cards and the strip, but by
dimension in the Checks prefixes, refusals and dialogs.**
- **Where:**
  - by dimension: `services/chain.py:58`, `:70`, `chain_route.py:158`, `chain_panel.py:794`, `:358`
    (`Stage 3:` with no `D`), `app.py:1122`;
  - by position: `chain_panel.py:455`, `:470`, `chain_strip.py:380`.
- **What the user sees:** on route 1D → 3D or 2D → 3D, card `02 3D` sits beside `Stage 3 (3D): …`,
  and the status line reads `Stage 3: …` in a two-stage chain.
- **Fix:** name stages one way on the UI side. `chain_panel._refuse` and the compat line should
  rewrite `Stage d (dD)` to `Stage 0k · dD` with `_number(d)` (and `app.py:1122` the same). The
  services prefix stays as it is, because the live checks strip it with `stage_prefix`.

**U5 - low - 01 Setup / Chain Checks - the unchecked-radii warning shows a Python exception to the
engineer.**
- **Where:** `validation.py:1457-1467`, `(ZeroDivisionError: float division by zero)` and similar.
- **What the user sees:** a warning that names an exception class instead of the input that made
  the cell layout incomputable.
- **Fix:** say `the cell layout could not be computed from the domain size and cell size`, name the
  fields where they are known, and send the exception text to the log only.

**U6 - low - Checks, Run and Results - one gauge position appears at three precisions, and two stop
reasons give pressure in Pa.**
- **Where:**
  - Checks `G2 (1.40, 0.30) m`, 2 decimals (`validation.py:1704`);
  - native stop reason `trigger gauge G2 reached (1.4000, 0.3000) m`, 4 decimals
    (`solver2d.py:415-416`, `solver3d.py:489`);
  - Results drop titles, 3 decimals (`plots.py:455`, D10);
  - `p_last = 1.234e+05 Pa` (`solver1d.py:225`) and `p_edge = … Pa` (`solver2d.py:425-426`), shown
    verbatim in the banner, the time line and the method card's Ended row (`run_panel.py:1185`,
    `results_method.py:202-204`), while every other screen uses kPa.
- **Fix:** keep the solver strings as they are (native stays byte-identical). Add one display
  formatter, used by `show_finish` and `_ended`, that rewrites `(p_… = x Pa)` to `x/1e3 kPa` with 3
  significant figures and coordinates to 3 decimals. The Checks precision to 3 decimals is the
  owner's call, since GUI-13 D4 pinned 2.

## 4. Proposed layout - 02 Run during a chain (one state per stage)

```
CHAIN · wall_A   (01 1D ✓ 19 s) → (02 2D meshing) → (03 3D waiting)
                 Stage 2 of 3 · meshing (blockMesh) · the 3D stage starts from …
[▯▯▯▯▯▯▯▯▯▯▯▯]  0 %    meshing stage 2 · 41 s elapsed          <- U1: no ETA, no 100 %
title: Chain 2/3 · BlastLab        Stop → "Stop wall_A (stage 2 of 3, meshing)?"

after Stop:
CHAIN · wall_A   (01 1D ✓ 19 s) → (02 2D stopped) → (03 3D not run)
                 Chain stopped at stage 2 of 3                          <- U2
Stopped after 43 s · stopped by user before stage 2 of 3 finished
Banner: Result ready: wall_A · stage 1 of 3 landed; stopped during stage 2.  Files in …\wall_A\
```

## 5. Quick wins

1. **U2 reason:** a stop reason of its own for a chain stopped after a landed stage (about 6 lines
   in `on_finished` / `_finish_notice`, plus asserts in the new R1 check).
2. **U3:** one `notify(..., 'info')` for the Keep-all scratch path (2 lines, no services change).
3. **U1:** forward the existing `stage` message to `on_stage(k)`. The worker already sends it, so
   this is about 20 lines in `run_controller` and `app`, and it removes the `reset_bar` special
   case.
4. **U4:** one display mapping from `Stage d (dD)` to the card number in `chain_panel._refuse`, the
   compat line and the long-run dialog.
5. **U5:** a plain-language unchecked-radii warning, with the exception moved to the log.
