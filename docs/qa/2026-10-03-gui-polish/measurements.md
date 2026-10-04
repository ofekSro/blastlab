# GUI-11 measurements: F13 no-regression (R10)

Batch [`2026-10-03-gui-polish`](../../batches/2026-10-03-gui-polish.md), part 11d,
T22. This file is committed **before the first sampled run**, with the rule copied
unchanged. The results section is added after the runs, and the rule above it is
not edited.

## The rule

**From the GUI-11 plan, T22 (verbatim):** "R10, unchanged from GUI-10:
`_e2e_ui_viewer_place.py --repeat 5` on the results, run and setup surfaces.
R10-PLACE is 0 ms over ≥ 500 samples. R10-RESIZE has a median ≤ 50 ms with no
repeat > 80 ms. Copy the rule into `measurements.md` and commit it first."

**The GUI-10 rule it refers to** (verbatim from
[`../2026-10-03-gui-qa/measurements.md`](../2026-10-03-gui-qa/measurements.md)):

> **R10 — F13 no-regression rule (pre-registered here, before any sampled run).**
> Real platform, the committed `_e2e_ui_viewer_place.py`, HEAD after 10a, `--repeat 5`:
> - `--surface results --actions tabs,theme,resize`, `--surface run --actions
>   tabs,theme,resize`, `--surface setup --actions chaintab,resize`.
> - **R10-PLACE:** `tabs`, `theme`, `chaintab`: the longest wrong-place stretch is
>   **0 ms** over **≥ 500 samples with a viewer window**. Under 500 counts as
>   inconclusive and is re-run, never passed.
> - **R10-RESIZE:** per surface, the **median over 5 repeats of the longest wrong
>   stretch ≤ 50 ms** (the worst recorded median, 45.1 ms on the run surface in 9b,
>   + 5 ms; the run surface is bimodal at about 26 / 45 ms), and **no single repeat >
>   80 ms**.
> - Over the rule: run an A/B against a `git worktree` at `fab0ebc` with the same
>   sampler and repeats. GUI-10 has regressed F13 only if the **HEAD median > the
>   `fab0ebc` median + 5 ms** on that surface. The setup surface is then checked first,
>   because T3's heights are the only 10a change near a viewer. The cause is found and
>   T3 reworked; `view3d_host.py` still stays as it is.

**How it maps onto GUI-11 (written before the runs, no threshold changed):**
- "HEAD after 10a" is the 11d HEAD at the time of the runs, named with its hash in
  the results.
- The A/B base, needed only if a surface is over the rule, is GUI-11's base
  **`116ea96`** (the GUI-10 HEAD that `~\blastlab_qa\gui10-head` and
  `viewer_measure_gui10.json` were measured at), in a temporary `git worktree`,
  removed afterwards. GUI-11 has regressed F13 on a surface only if the HEAD median
  is over the `116ea96` median + 5 ms there.
- The GUI-11 changes near a viewer: T18 (the Run centre: the strip's one-row rule,
  the 200 px `runview` minimum and the dock giving way) on the run surface, and
  T21 (the Results placeholder text) on the results surface. If the run surface is
  over the rule, T18 is checked first. `view3d_host.py` stays as it is.
- "≥ 500 samples with a viewer window" is summed over the 5 repeats, the reading of
  7a, 7b, 9b and GUI-10.

## How it is run here

- One sampler process at a time, nothing else heavy running, free memory checked
  first. `QT_QPA_PLATFORM` unset. Throwaway settings (the sampler's own
  `private_settings()`).
- From `blastlab/tests`:
  - `python -u _e2e_ui_viewer_place.py --surface results --actions tabs,theme,resize --repeat 5 --out <scratch>/r10_results.json`
  - `python -u _e2e_ui_viewer_place.py --surface run --actions tabs,theme,resize --repeat 5 --out <scratch>/r10_run.json`
  - `python -u _e2e_ui_viewer_place.py --surface setup --actions chaintab,resize --repeat 5 --out <scratch>/r10_setup.json`
- The three outputs are merged into `viewer_measure_gui11.json` in this folder.

## Results

Run 2026-10-04, 05:52-05:56, at **`c171f6f`** (the 11d HEAD after T16-T21, F43,
F40, F46 and the harness fixes; the rule above was committed at 05:16:17 in
`49f9a75`, and the three raw sampler outputs are stamped 05:53:48, 05:55:21 and
05:56:03). Real platform (`windows`), one sampler at a time, 2.6 / 2.4 / 3.1 GB
free physical memory before each. Each sampler's self-test saw the deliberate
60 px / 150 ms displacement (149.5-149.8 ms, 60 px), and each closed its own
viewer child with its window. The numbers are in
[`viewer_measure_gui11.json`](viewer_measure_gui11.json).

Changes near a viewer since GUI-10 (`116ea96`): T18 on the run surface (the
strip's one-row rule, the 200 px `runview` minimum, the dock giving way) and T21
on the results surface (the placeholder text). `git diff 116ea96..HEAD --
blastlab/ui/view3d_host.py` is empty.

**R10-PLACE** (longest wrong-place stretch, samples with a viewer window, summed
over the 5 repeats):

| Surface | Action | Repeats (ms) | With window | Verdict |
|---|---|---|---|---|
| results | tabs | 0, 0, 0, 0, 0 | 1758 | PASS |
| results | theme | 0, 0, 0, 0, 0 | 19973 | PASS |
| run | tabs | 0, 0, 0, 0, 0 | 1753 | PASS |
| run | theme | 0, 0, 0, 0, 0 | 20965 | PASS |
| setup | chaintab | 0, 0, 0, 0, 0 | 1761 | PASS |

**R10-RESIZE** (longest wrong stretch per repeat, 1600 ↔ 1100):

| Surface | Repeats (ms) | Median | Max | Worst offset | Verdict |
|---|---|---|---|---|---|
| results | 20.7, 18.2, 17.6, 28.5, 17.7 | 18.2 | 28.5 | 472 px | PASS (≤ 50, ≤ 80) |
| run | 42.5, 43.3, 43.1, 44.6, 43.8 | 43.3 | 44.6 | 476 px | PASS (≤ 50, ≤ 80) |
| setup | 29.4, 26.2, 28.5, 32.9, 28.3 | 28.5 | 32.9 | 468 px | PASS (≤ 50, ≤ 80) |

GUI-10's medians for comparison: results 15.3, run 44.7, setup 30.3 ms.

**Verdict: R10 passes on every surface, so GUI-11 did not regress F13.** No A/B
at `116ea96` was needed. F13 itself stays open for the viewer-host batch (≤ 17 ms).
