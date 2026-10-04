# GUI-7a measurements — pre-registered rules, then the numbers

Batch [`2026-09-29-gui-results`](../../batches/2026-09-29-gui-results.md), T4.
The rules below were written **before the first sampled run** of the
committed sampler `blastlab/tests/_e2e_ui_viewer_place.py` (the time of this
section's commit is the proof: the numbers are added in a later commit).

## The sampler

- Real platform (`QT_QPA_PLATFORM` unset), throwaway settings, the real
  MainWindow, the real viewer child process.
- A tiny native 3D result (the Phase 0 3D case of `test_char_native_api`,
  1 m cube, 25 mm cells) in Results → 3D, twice in the list (`viewer A`
  with a model folder, so its method card has more rows; `viewer B`
  without).
- Every ≤ 2 ms (1.5 ms sleep plus the event pump): Win32 `GetWindowRect`,
  `GetParent`, `IsWindowVisible` of the viewer's HWND against
  `GetWindowRect` of its card (the host's native container). Both rects
  are physical pixels from Win32; Qt's own geometry is not used.
- **Wrong place** = the viewer window is visible and reaches outside its
  card by more than 2 px on any side. The number judged is the **longest
  unbroken wrong-place stretch** in ms. A window smaller than its card
  (`shrink_ahead` makes one on purpose) is reported as `mismatch`, not
  judged.
- Each step of an action is watched for 700 ms. Three repeats per action
  (`--repeat 3`).

## Rules (binding)

- **R-VIEWER:** on the native 3D result in the Results 3D view, the
  longest wrong-place stretch is **0 ms** over **≥ 500 samples with a
  viewer window** (summed over the repeats) for each of:
  - `open3d` — Open the 3D viewer (from the Fields view);
  - `select` — a result selection change (the method card changes
    height: B ↔ A);
  - `busy` — an export busy strip up and down (the right column);
  - `stage` — `set_stage_strip` show / hide (above the view);
  - `tabs` — Setup ↔ Run ↔ Results;
  - `theme` — a theme toggle (light, then dark).
  An action whose samples with a window fall under 500 is re-run with
  more repeats before it is judged; `tabs` counts only the samples with
  the Results screen on top.
- **R-VIEWER-RESIZE (F13):** `resize` = 1600 → 1100 → 1600, three
  repeats. The **median of the longest stretch** at HEAD is **≤ the same
  sampler's median at base `c8a04d2` + 5 ms**. Base and HEAD are run back
  to back on this machine, base in a `git worktree` of `c8a04d2` (the
  sampler file copied in; nothing else changed there).
- Above either threshold: fix it in this batch (the `shrink_ahead`
  pattern of D70 for anything that appears above the host) and re-measure
  under the same rule, or report the number and the action. Never "it
  ends up in the right place".
- A `MemoryError` or a viewer child that never reports a window is
  environment: re-run alone and say so; it is neither pass nor fail.

## Results

The rules above were committed first (`20c31c5`). Everything below was
measured after that commit. The resize A/B and the "before" JSONs record
`20c31c5`, but they were taken on the working tree that `042b386` then
committed: the stage fix and the sampler itself. They were taken on this 8 GB PC, 1920 × 1080 screen, with
about 2.4-2.7 GB of commit free, one run at a time. Only PID 29568 (a
`python -m blastlab` that is not ours) was running besides; it was left
alone. Every viewer child and sampler process was ours and was gone after
each run (checked).

### The sampler had to be fixed before its numbers meant anything

1. **First version (GUI-thread loop):** every action read 0 ms,
   including `resize`, where F13 had measured 22-49 ms. A loop on the
   GUI thread only sees the window between two passes of the event loop,
   so a wrong state that lives inside one pass is invisible. Not used.
2. **Second version (a sampling thread):** a self-test was added. It
   moves the render window 60 px inside its card with `SetWindowPos` and
   holds it about 150 ms. That thread read it correctly, 150.7 ms and
   60 px. But the GIL starved the thread for up to 355 ms during a theme
   toggle and 57 ms on a selection change, so a wrong stretch there could
   hide.
3. **Committed version (a sampling process, `--child`):** it shares no
   GIL with the GUI. Its self-test read 149.0-150.6 ms and 60 px in every
   run. The largest gap between two samples in any action was 7.5 ms.
   Every number judged below comes from this version.

The rules themselves were not changed.

### R-VIEWER — PASS (after one fix)

The final run is `viewer_measure_7a.json`, on the committed code
`042b386`: process sampler, 3 repeats, 700 ms watched per step. The same
run on the working tree just before that commit gave the same verdict
(all six 0 ms, largest gap 7.5 ms).

| action | samples | with window | longest wrong | worst | largest gap |
|---|---|---|---|---|---|
| open3d | 1089 | 1059 | **0 ms** | 0 px | 3.2 ms |
| select | 2267 | 2267 | **0 ms** | 0 px | 3.1 ms |
| busy | 2108 | 2108 | **0 ms** | 0 px | 2.7 ms |
| stage | 2130 | 2130 | **0 ms** | 0 px | 3.5 ms |
| tabs | 3206 | 1060 | **0 ms** | 0 px | 2.7 ms |
| theme | 11930 | 11930 | **0 ms** | 0 px | 3.4 ms |

In the same run, `resize` read 25.9 ms longest (median 21.8). That is
F13, judged below.

- `not_child` was 0 everywhere: the window stayed a Win32 child of its
  card.
- `stage` showed a **mismatch** of 28-32 ms. That is the window made
  shorter than its card on purpose, by `shrink_ahead`, and it is inside
  the card.
- **The failure, and its fix.** Before the fix, the thread sampler
  (`viewer_measure_7a_before_stage_fix.json`) read `stage` at **29.2 ms**
  longest (median 23.8), with the window **44 px** below its card. 44 px
  is the 32 px strip plus the 12 px layout spacing.
- `set_stage_strip` now shrinks the viewer's window by exactly that
  height before it shows the strip. This is D70's `shrink_ahead`, used
  only when the 3D view is on screen. Re-measured under the same rule
  (5 repeats): **0 ms**, with the mismatch at 30.4 ms. Final run: see the
  table.
- `test_ui_results_screen` pins the call: `shrink_ahead(44)` once over
  the 3D view, never over Fields, and not when the strip goes.

### R-VIEWER-RESIZE (F13) — PASS

1600 → 1100 → 1600, three repeats, process sampler. Base `c8a04d2` ran in
a `git worktree` with only the sampler copied in, then HEAD ran right
after:

| | longest per repeat (ms) | median | worst |
|---|---|---|---|
| base `c8a04d2` | 24.6 / 16.2 / 23.7 | **23.7** | 500 px |
| HEAD | 18.8 / 20.7 / 24.2 | **20.7** | 472 px |

- Rule: 20.7 ≤ 23.7 + 5. **PASS.**
- The per-repeat values are in `viewer_resize_7a_base.json` and
  `viewer_resize_7a_head.json`.
- The thread sampler gave the same verdict earlier: base 34.1 ms, HEAD
  35.1 ms. It reads longer because GIL delays lengthen its stretches.
- The lag itself is F13 (it predates GUI-7) and is unchanged.

### Widths and heights (offscreen suite S2/S3; the real-platform shots)

- Columns: **280 / 968 / 320** at 1600 × 1000 and **280 / 468 / 320** at
  1100 × 720, in both modes.
- The side columns do not need to narrow at 1100 × 720. The centre's
  minimum is 373 px with Fields on screen and 434 px with 3D, because
  the view stack is sized by the page on screen.
- The standalone panel cannot be narrower than 280 + centre + 320. At
  900 × 600 it lays out at 973 px, and nothing is clipped.
- Measured heights:
  - view-tab strip 38, tabs 32;
  - result rows 44;
  - Load a run… 34, ✕ 34 × 34;
  - Show case / Load into 01 Setup 32;
  - title box 36;
  - export buttons 40;
  - busy strip 48;
  - Open the 3D viewer 42.

### Screenshots (real platform, dark)

- `gui7a-dark-1600x1000-results.png` and `gui7a-dark-1100x720-results.png`
  show three results, with wall_A selected: a native 2D result with a
  model folder and its method card.
- `gui7a-dark-1600x1000-export-busy.png` and
  `gui7a-dark-1100x720-export-busy.png` show a real threaded Animation
  export in progress, with its busy strip.
- The small stray colour bar at the top left of the Fields plot is
  **pre-existing**: base `c8a04d2` shows the same, as found by an A/B
  grab. It is F15.
