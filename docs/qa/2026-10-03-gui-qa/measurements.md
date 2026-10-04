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

Run 2026-10-03, 21:02-21:05 (verify10b: this read "21:15", a typo; the
three raw sampler outputs are stamped 21:03, 21:04 and 21:05, and these
results were committed at 21:06), at **`8585aa6`** (the 10b HEAD after F29, D190,
F34 and the F08 harness fix), real platform (`windows`), one sampler at a
time, 1.0 GB free physical memory and 13.9 GB free commit before the
first. Each sampler's self-test saw the deliberate 60 px / 150 ms
displacement (149.8-149.9 ms, 60 px), so it can see a wrong place. Each
stopped its own viewer child. The numbers are in
[`viewer_measure_gui10.json`](viewer_measure_gui10.json).

Changes near a viewer since 10a's HEAD: F29 (the top bar's spacing and
the case button, above every screen), D190 (the tree's hover colour,
QSS only) and F34 (the Run strip tiles' value face; their height is
held, so nothing below them moves). `git diff fab0ebc..HEAD --
blastlab/ui/view3d_host.py` is empty.

**R10-PLACE** (longest wrong-place stretch, samples with a viewer window):

| Surface | Action | Repeats (ms) | With window | Verdict |
|---|---|---|---|---|
| results | tabs | 0, 0, 0, 0, 0 | 1751 | PASS |
| results | theme | 0, 0, 0, 0, 0 | 20481 | PASS |
| run | tabs | 0, 0, 0, 0, 0 | 1751 | PASS |
| run | theme | 0, 0, 0, 0, 0 | 20251 | PASS |
| setup | chaintab | 0, 0, 0, 0, 0 | 1773 | PASS |

**R10-RESIZE** (longest wrong stretch per repeat, 1600 ↔ 1100):

| Surface | Repeats (ms) | Median | Max | Worst offset | Verdict |
|---|---|---|---|---|---|
| results | 9.8, 26.0, 14.8, 15.3, 28.4 | 15.3 | 28.4 | 472 px | PASS (≤ 50, ≤ 80) |
| run | 44.0, 45.2, 44.8, 42.2, 44.7 | 44.7 | 45.2 | 476 px | PASS (≤ 50, ≤ 80) |
| setup | 30.3, 30.4, 26.9, 27.6, 40.9 | 30.3 | 40.9 | 468 px | PASS (≤ 50, ≤ 80) |

**Verdict: R10 passes on every surface, so GUI-10 did not regress F13.**
No A/B at `fab0ebc` was needed. F13 itself stays open: the resize
stretches (up to 45 ms, about 470 px) are the pre-existing lag the
future viewer-host batch is to bring to ≤ 17 ms.
