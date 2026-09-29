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

(added after the runs)
