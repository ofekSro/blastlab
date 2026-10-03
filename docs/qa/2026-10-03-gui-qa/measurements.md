# GUI-10 measurements: F13 no-regression (R10)

Batch [`2026-10-03-gui-qa`](../../batches/2026-10-03-gui-qa.md), part 10b, T12.
This file was committed **before the first sampled run**, with the rule copied
from the plan unchanged. The results section is added after the runs, and the
rule above it is not edited.

## The rule (copied verbatim from the plan)

**R10 — F13 no-regression rule (pre-registered here, before any sampled run).**
Real platform, the committed `_e2e_ui_viewer_place.py`, HEAD after 10a, `--repeat 5`:
- `--surface results --actions tabs,theme,resize`, `--surface run --actions
  tabs,theme,resize`, `--surface setup --actions chaintab,resize`.
- **R10-PLACE:** `tabs`, `theme`, `chaintab`: the longest wrong-place stretch is
  **0 ms** over **≥ 500 samples with a viewer window**. Under 500 counts as
  inconclusive and is re-run, never passed.
- **R10-RESIZE:** per surface, the **median over 5 repeats of the longest wrong
  stretch ≤ 50 ms** (the worst recorded median, 45.1 ms on the run surface in 9b,
  + 5 ms; the run surface is bimodal at about 26 / 45 ms), and **no single repeat >
  80 ms**.
- Over the rule: run an A/B against a `git worktree` at `fab0ebc` with the same
  sampler and repeats. GUI-10 has regressed F13 only if the **HEAD median > the
  `fab0ebc` median + 5 ms** on that surface. The setup surface is then checked first,
  because T3's heights are the only 10a change near a viewer. The cause is found and
  T3 reworked; `view3d_host.py` still stays as it is.

## How it is run here

- One sampler process at a time, nothing else heavy running, free memory
  checked first. `QT_QPA_PLATFORM` unset. Throwaway settings (the sampler's own
  `private_settings()`).
- The three invocations, from `blastlab/tests`:
  - `python -u _e2e_ui_viewer_place.py --surface results --actions tabs,theme,resize --repeat 5 --out <scratch>/r10_results.json`
  - `python -u _e2e_ui_viewer_place.py --surface run --actions tabs,theme,resize --repeat 5 --out <scratch>/r10_run.json`
  - `python -u _e2e_ui_viewer_place.py --surface setup --actions chaintab,resize --repeat 5 --out <scratch>/r10_setup.json`
- The three outputs are merged into `viewer_measure_gui10.json` in this folder.
- "HEAD after 10a" is the 10b HEAD at the time of the runs; it is named with
  its hash in the results. Its only changes near a viewer since 10a are listed
  there.

## Results

(Added after the runs.)
