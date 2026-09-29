# GUI-7b measurements — pre-registered viewer rules, then the numbers

Batch [`2026-09-29-gui-results`](../../batches/2026-09-29-gui-results.md), T7.
The rules below were written **before the first sampled run** of 7b (the
commit that adds this section is the proof; the numbers come in a later
commit). The sampler is 7a's committed
`blastlab/tests/_e2e_ui_viewer_place.py` (D95), with one action added in
the same commit as these rules: `views`.

## The sampler (unchanged from 7a)

- Real platform (`QT_QPA_PLATFORM` unset), throwaway settings, the real
  MainWindow, the real viewer child process.
- The tiny native 3D result (the Phase 0 3D case of `test_char_native_api`)
  in Results → 3D, twice in the list (`viewer A` with a model folder,
  `viewer B` without).
- Every ≤ 2 ms, from a sampling process of its own: Win32
  `GetWindowRect`, `GetParent`, `IsWindowVisible` of the viewer's HWND
  against `GetWindowRect` of its card.
- **Wrong place** = the viewer window is visible and reaches outside its
  card by more than 2 px on any side. The number judged is the **longest
  unbroken wrong-place stretch** in ms. A window smaller than its card is
  `mismatch`, reported, not judged.
- Each step is watched for 700 ms; three repeats per action. A self-test
  (a 60 px displacement held ~150 ms) must read ≥ 100 ms and ≥ 50 px, or
  the run is void.

## Rules (binding)

- **R-VIEWER:** on the native 3D result in the Results 3D view, the
  longest wrong-place stretch is **0 ms** over **≥ 500 samples with a
  viewer window** (summed over the repeats) for each of:
  - `open3d` — Open the 3D viewer (from the Field view);
  - `views` — the view tabs Field → Gauges → 3D (new in 7b: the viewer
    is back on screen at the last step);
  - `select` — a result change (B ↔ A, the method card changes height);
  - `busy` — an export busy strip up and down (the right column);
  - `stage` — `set_stage_strip` show / hide;
  - `tabs` — Setup ↔ Run ↔ Results;
  - `theme` — a theme toggle (light, then dark).
  An action with fewer than 500 samples with a window is re-run with more
  repeats before it is judged.
- **R-VIEWER-RESIZE (F13):** `resize` = 1600 → 1100 → 1600, three
  repeats. The **median of the longest stretch** at HEAD is **≤ the same
  sampler's median at base `c8a04d2` + 5 ms**, base and HEAD run back to
  back on this machine, base in a `git worktree` of `c8a04d2` with this
  sampler file copied in (nothing else changed there).
- Above either threshold: fix it in this batch (D70's `shrink_ahead` for
  anything appearing above the host) and re-measure under the same rule,
  or report the number and the action (plan §11). Never "it ends up in
  the right place".
- A `MemoryError` or a viewer child that never reports a window is
  environment: re-run alone and say so; neither pass nor fail.

## Results

(Added after the runs, in a later commit.)
