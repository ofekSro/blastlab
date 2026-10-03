# GUI-9b measurements — the embedded 3D viewer under the chain's new widgets

Batch [`2026-09-29-gui-chain`](../../batches/2026-09-29-gui-chain.md), T6.
Report: [`2026-09-29-gui-chain-b.implement.md`](../../batches/2026-09-29-gui-chain-b.implement.md).

## Pre-registered rules (written 2026-10-03, before the first sampled run)

This section was written and committed together with the sampler's new
actions, **before any of them was run**. It is not edited after the
measurements; the results go in the section below it, judged by these rules
as they stand. (D129 b's precedent: an added measurement, not a changed
assertion.)

**The instrument.** The committed Win32 sampler
`blastlab/tests/_e2e_ui_viewer_place.py` (GUI-7 T4): the real `MainWindow`
with throwaway settings, the real viewer child, a sampling **process** of its
own reading `GetWindowRect` / `GetParent` / `IsWindowVisible` of the
viewer's render window against its card every ≤ 2 ms, real platform
(`QT_QPA_PLATFORM` unset), its own self-test first (a 60 px displacement held
~150 ms must read ≥ 100 ms and ≥ 50 px, else the run is void). A sample is
*wrong* when the viewer window is visible and reaches outside its card by more
than 2 px on any side; the measure is the **longest unbroken wrong stretch**
(ms), never where the window ends up. Each action: 3 repeats, 700 ms watched
after each step.

**The actions added for GUI-9** (in the sampler's own pattern; a code base
without the widget reports them `unavailable`):

| Action | Surface | Steps |
|---|---|---|
| `chainsel` | results | from the plain 3D entry A (no tabs) select a 1 → 3 chain entry whose 3D stage is selected (the STAGE tabs appear above the 3D view), then entry A again (they go) |
| `stagetabs` | results | the chain selected on its 3D stage: click the tab 1D, then 3D |
| `chainstrip` | run | the run surface's 3D view on: `set_chain_strip(ChainStrip)` (appears), `stage_started(1)`, `set_chain_strip(None)` (goes) |
| `chaintab` | setup | Setup with its 3D preview: Chain, then Setup |
| `chainresize` | results | `resize` (1600 × 1000 → 1100 × 720 → 1600 × 1000) with the chain selected on its 3D stage (the tabs shown) |
| `stripresize` | run | `resize` with a chain strip shown (one row at 1600, two rows at 1100) |

**R-VIEWER (pre-registered).** For each of `chainsel`, `stagetabs`,
`chainstrip`, `chaintab`, and for the existing `stage`, `tabs` and `theme` on
the results and the run surfaces (`stage` is a results-surface action only;
on the run surface its counterpart is `chainstrip`): the longest wrong-place
stretch is **0 ms**
over **≥ 500 samples with a viewer window** (summed over the 3 repeats). A
sample count under 500 with a window makes the action *inconclusive* (re-run
it), never a pass.

**R-VIEWER-RESIZE (F13, pre-registered).** `chainresize` (results) and
`stripresize` (run) at HEAD: the **median over 3 repeats of the longest wrong
stretch** must be **≤ the median of the same sampler's `resize` at base
`4b28007`** (a `git worktree`, the same action without the new widgets) **+ 5
ms**, surface by surface. F13 is handled explicitly: it predates GUI-7, and
`view3d_host.py` is not edited in this batch. A result over the rule gets an
A/B at HEAD with the new widget hidden (`resize` at HEAD on the same surface)
to say whether the widget adds to it, and is reported with its number and
action. "It ends up in the right place" is never the bar.

**Order of runs.** HEAD: `--surface results --actions
stage,tabs,theme,chainsel,stagetabs,chainresize,resize`; `--surface run
--actions stage,tabs,theme,chainstrip,stripresize,resize`; `--surface setup
--actions chaintab`. Base worktree (`4b28007`, its own committed sampler):
`--surface results --actions resize`, `--surface run --actions resize`. One
process at a time, free commit checked first; each process stops only its own
viewer child, by handle.

## Results

Run 2026-10-03 on the 8 GB home PC, Qt platform `windows`, 1920 × 1080
screen, one sampler process at a time (free commit 13.8 GB, free physical
about 1.5 GB). HEAD = `5ebd616` (the rules' commit `771a00e` plus the strip's
fit fix); base = `4b28007` in a `git worktree`, its own committed sampler.
Every run's self-test saw the displaced window (148.2-149.2 ms, 60 px), so
none is void. No viewer window ever left its card as a parent (`not child` 0
everywhere). The numbers: `viewer_measure_9b.json` (all five runs, every
repeat, and the verdicts).

**R-VIEWER — PASS on every action.**

| Surface | Action | Samples | With a window | Longest wrong | Longest mismatch | Verdict |
|---|---|---|---|---|---|---|
| results | `stage` | 2109 | 2109 | 0 ms | 29.7 ms | PASS |
| results | `tabs` | 3180 | 1050 | 0 ms | 0 ms | PASS |
| results | `theme` | 12263 | 12263 | 0 ms | 0 ms | PASS |
| results | `chainsel` (new) | 2276 | 2276 | 0 ms | 13.3 ms | PASS |
| results | `stagetabs` (new) | 2337 | 2337 | 0 ms | 0 ms | PASS |
| run | `tabs` | 3181 | 1047 | 0 ms | 0 ms | PASS |
| run | `theme` | 12157 | 12157 | 0 ms | 0 ms | PASS |
| run | `chainstrip` (new) | 3175 | 3175 | 0 ms | 30.3 ms | PASS |
| setup | `chaintab` (new) | 2154 | 1046 | 0 ms | 0 ms | PASS |

A *mismatch* is a window smaller than its card, never outside it: what
`shrink_ahead` makes on purpose when a strip appears above the view
(`stage`, `chainsel`, `chainstrip`), until the layout catches up. `tabs` and
`chaintab` have about a third of their samples with a window because the
viewer is hidden while another screen is shown.

**R-VIEWER-RESIZE (F13) — PASS on both surfaces.** Longest wrong stretch per
repeat (ms) and the median the rule compares:

| Surface | HEAD, widget shown | HEAD median | Base `4b28007` `resize` | Base median | Limit (base + 5) | Verdict |
|---|---|---|---|---|---|---|
| results | `chainresize` 4.0, 25.2, 23.5 | 23.5 | 27.9, 27.6, 26.1 | 27.6 | 32.6 | PASS |
| run | `stripresize` 45.2, 27.5, 25.7 | 27.5 | 25.4, 26.5, 44.8 | 26.5 | 31.5 | PASS |

Neither result is over its rule, so the rule's A/B (the widget hidden at
HEAD) was not required. The same runs did measure plain `resize` at HEAD
after the new actions: results 31.0, 21.3, 21.6 (median 21.6) with the
chain still selected (its tabs shown), run 45.4, 26.0, 45.1 (median 45.1)
with no strip. The run surface's per-repeat values are bimodal at HEAD and
at base alike (about 26 or about 45 ms; base's longest is 44.8): the
known F13 shape (22-49 ms since GUI-6), not something the strip adds - with
the strip shown the median is the low mode. Worst offsets 472 px (results)
and 476 px (run) at HEAD and at base: the shrink step of a 1600 → 1100
resize, F13 as recorded. `view3d_host.py` is not edited in this batch; F13
stays open (GUI-10 / the small batch after it).

## Verifier re-run (9b verify, 2026-10-03)

The rules above are unchanged since `771a00e` (`git diff 771a00e..HEAD` on
this file adds only the Results sections), and every sampled run is
recorded at `5ebd616`, after that commit. Two departures from the
"Order of runs" paragraph, neither a changed rule: the run surface ran
without `stage` (the R-VIEWER paragraph already makes it results-only,
D168), and its plain `resize` ran before `stripresize`, after `chainstrip`
had emptied the slot (the order of `viewer_measure_9b.json`'s actions), so
"run median 45.1 with no strip" above is right.

Re-run by the verifier with the same committed sampler at HEAD (`1a83437`,
the two review fixes in; real platform, one process at a time, each
viewer child closed with its window):

| Surface | Action | Samples (with a window) | Longest wrong | Median | Rule | Verdict |
|---|---|---|---|---|---|---|
| run | `chainstrip` | 3222 (3222) | 0 ms | 0 ms | R-VIEWER 0 ms, ≥ 500 | PASS |
| run | `stripresize` | 2321 (2321) | 29.7 ms | 27.4 ms | ≤ 31.5 ms | PASS |
| results | `chainsel` | 2328 (2328) | 0 ms | 0 ms | R-VIEWER | PASS |
| results | `stagetabs` | 2399 (2399) | 0 ms | 0 ms | R-VIEWER | PASS |
| results | `chainresize` | 2259 (2259) | 26.4 ms | 24.2 ms | ≤ 32.6 ms | PASS |
| setup | `chaintab` | 2169 (1055) | 0 ms | 0 ms | R-VIEWER | PASS |

Self-tests 148.5 / 148.9 / 151.2 ms at 60 px (none void); `not child` 0
everywhere; worst offsets 476 px (run) and 472 px (results), as above.
