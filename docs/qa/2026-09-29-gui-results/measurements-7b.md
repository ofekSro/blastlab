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

The rules above were committed first (`416dc25`). Everything below was
measured after that commit, on this 8 GB PC (1920 × 1080 screen), with a
foreign `python -m blastlab` (PID 29568) left running, idle.

### R-VIEWER: PASS (0 ms for every action)

Two full runs of the sampler, both 0 ms for all seven actions. The first
ran at `416dc25` (T5 + T6 code), the second at `7e623ba` (the T7 fixes,
among them the panel's re-fit on `LayoutRequest`, D117). The numbers
below are the second run (`viewer_measure_7b.json`). The self-test read
149.9 ms / 60 px.

| Action | Samples | With a window | Longest wrong | Worst | Longest mismatch |
|---|---|---|---|---|---|
| open3d | 1104 | 1054 | 0.0 ms | 0 px | 0.0 ms |
| views (Field → Gauges → 3D) | 3197 | 1053 | 0.0 ms | 0 px | 0.0 ms |
| select | 2264 | 2264 | 0.0 ms | 0 px | 0.0 ms |
| busy | 2112 | 2112 | 0.0 ms | 0 px | 0.0 ms |
| stage | 2127 | 2127 | 0.0 ms | 0 px | 27.2 ms |
| tabs | 3207 | 1057 | 0.0 ms | 0 px | 0.0 ms |
| theme | 11706 | 11706 | 0.0 ms | 0 px | 0.0 ms |

`stage`'s mismatch is `shrink_ahead` making the window smaller than its
card on purpose (D93); it is never outside the card. The first run
(`416dc25`) had ≥ 1057 samples with a window for each action.

### R-VIEWER-RESIZE (F13): the judged pair FAILS by 1.9 ms

`resize` = 1600 → 1100 → 1600, three repeats. Median of the longest
wrong-place stretch per run (`viewer_resize_7b.json`):

| Pair | Base `c8a04d2` | HEAD | HEAD − base | Rule (≤ +5 ms) |
|---|---|---|---|---|
| **1 (judged)** | 18.5 ms | 25.4 ms (`416dc25`) | +6.9 ms | **FAIL** |
| 2 | 17.5 ms | 18.1 ms (`416dc25`) | +0.6 ms | pass |
| 3 | 30.3 ms | 24.1 ms (`416dc25`) | −6.2 ms | pass |
| 4 | 22.8 ms | 21.8 ms (`7e623ba`) | −1.0 ms | pass |
| 5 | 17.5 ms | 30.8 ms (`7e623ba`) | +13.3 ms | fail |

- The pre-registered rule judges one back-to-back pair: pair 1, run
  straight after the first full sampler run. It fails: HEAD's median is
  25.4 ms against the 23.5 ms allowed.
- Pairs 2-5 are diagnostics, run afterwards, and do not replace pair 1.
  The single-run medians move by up to 13 ms from run to run at the same
  commit (base: 17.5-30.3 ms). Pooled over the 15 repeats of each side,
  the median is 19.6 ms at base and 24.1 ms at HEAD (+4.5 ms). The
  longest single stretch is 32.0 ms at base and 31.3 ms at HEAD.
- The full runs read 21.2 ms (`416dc25`) and 29.4 ms (`7e623ba`).
- The lag is F13's: the window stands up to 472 px past its card (500 at
  base) on the shrink step, for 17-32 ms, at base as at HEAD. Nothing in
  7b touches `view3d_host.py`, and on a resize the Field and Gauges pages
  are hidden stack pages (not laid out).
- **Action (plan §11):** reported, not fixed. The fix belongs to F13 and
  F5 (`view3d_host.py`, the CLAUDE.md 8.7 zone): shrink the child window
  ahead of a window resize, as `shrink_ahead` does for the banner and the
  stage strip. A resize rule that judges one pair of three-repeat medians
  cannot tell ±5 ms from this noise. More repeats per side (say 15) would
  make it a fair gate.
