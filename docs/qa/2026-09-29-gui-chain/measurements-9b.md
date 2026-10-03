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

*(filled in after the runs; see below)*
